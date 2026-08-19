import { useEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react'
import axios from 'axios'
import { api } from '../lib/api'

/** Path after /api/ only, e.g. agreements/{id}/onlyoffice-config?token=… */
function normalizeOnlyofficeConfigPath(params: {
  configEndpoint?: string
  agreementId?: string
  templateId?: string
}): string {
  const { configEndpoint, agreementId, templateId } = params
  if (configEndpoint) {
    const s = configEndpoint.trim()
    const withoutLeading = s.startsWith('/') ? s.slice(1) : s
    return withoutLeading.replace(/^api\//, '')
  }
  if (templateId) {
    return `templates/${templateId}/onlyoffice-config`
  }
  if (agreementId) {
    return `agreements/${agreementId}/onlyoffice-config`
  }
  throw new Error('Either agreementId, templateId, or configEndpoint must be provided')
}

/**
 * Public (no JWT) fetches need an absolute or origin-relative URL with exactly one `/api` segment.
 */
function absoluteUrlForPublicApi(apiBase: string, pathAfterApi: string): string {
  const path = pathAfterApi.replace(/^\//, '')
  const base = (apiBase || '/api').replace(/\/$/, '')
  if (base.startsWith('http://') || base.startsWith('https://')) {
    if (base.endsWith('/api')) {
      return `${base}/${path}`
    }
    return `${base}/api/${path}`
  }
  if (base === '/api' || base.endsWith('/api')) {
    return `${base}/${path}`
  }
  return `/api/${path}`
}

function isOnlyofficeEditorConfigShape(obj: unknown): boolean {
  if (!obj || typeof obj !== 'object') return false
  const o = obj as Record<string, unknown>
  return (
    typeof o.document === 'object' &&
    o.document != null &&
    typeof o.editorConfig === 'object' &&
    o.editorConfig != null
  )
}

function extractOnlyofficeConfigResponse(raw: unknown): { editorUrl: string; config: any } {
  if (typeof raw === 'string') {
    const t = raw.trim()
    if (t.startsWith('<!DOCTYPE') || t.toLowerCase().startsWith('<html')) {
      throw new Error(
        'ONLYOFFICE config URL returned HTML instead of JSON. Confirm VITE_API_BASE includes /api and that requests to /api/* reach the backend.',
      )
    }
    throw new Error('ONLYOFFICE configuration response is not JSON.')
  }
  if (raw == null || typeof raw !== 'object') {
    throw new Error('ONLYOFFICE configuration response is empty or invalid.')
  }
  const o = raw as Record<string, unknown>
  const nested = o.data != null && typeof o.data === 'object' ? (o.data as Record<string, unknown>) : null

  let editorUrlRaw = (o.editorUrl ?? o.editor_url) as string | undefined
  let editorConfig = o.config as unknown
  if (nested) {
    editorUrlRaw = (nested.editorUrl ?? nested.editor_url ?? editorUrlRaw) as string | undefined
    if (editorConfig == null) {
      editorConfig = nested.config ?? (isOnlyofficeEditorConfigShape(nested) ? nested : undefined)
    }
  }
  if (editorConfig == null && isOnlyofficeEditorConfigShape(raw)) {
    editorConfig = raw
  }
  if (editorConfig == null && typeof o.detail === 'string') {
    throw new Error(`ONLYOFFICE configuration failed: ${o.detail}`)
  }
  if (editorConfig == null || !isOnlyofficeEditorConfigShape(editorConfig)) {
    throw new Error(
      'ONLYOFFICE configuration response is missing config. The onlyoffice-config endpoint should return JSON with editorUrl and config.',
    )
  }
  if (editorUrlRaw == null || String(editorUrlRaw).trim() === '') {
    throw new Error('ONLYOFFICE configuration response is missing editor URL')
  }
  return { editorUrl: String(editorUrlRaw).trim(), config: editorConfig }
}

interface OnlyOfficeEditorProps {
  agreementId?: string  // For agreements
  templateId?: string   // For templates
  apiBase?: string
  canEdit: boolean
  onSave?: () => void
  configEndpoint?: string  // Optional: custom config endpoint path
  /** DOM id for the DocEditor mount node (must be unique if multiple editors exist). */
  editorContainerId?: string
  /**
   * Use unauthenticated fetch for onlyoffice-config (no Bearer from localStorage).
   * Required for public routes (sign/review links) when the user is also logged into the CRM.
   */
  publicSession?: boolean
}

/**
 * Methods exposed to parent components via ref.
 * Usage:
 *   const editorRef = useRef<OnlyOfficeEditorHandle>(null)
 *   editorRef.current?.requestSave()  // triggers OO force-save → callback
 */
export interface OnlyOfficeEditorHandle {
  /**
   * Ask OnlyOffice to flush its in-memory document (including unsaved comments)
   * to the backend via the callback endpoint (status = 6 force-save).
   * Returns true if the request was sent, false if the editor is not ready.
   */
  requestSave: () => boolean
  /**
   * Best-effort text insertion into the document.
   * Returns true if a command was dispatched to OnlyOffice.
   */
  insertText: (text: string) => boolean
}

const OnlyOfficeEditor = forwardRef<OnlyOfficeEditorHandle, OnlyOfficeEditorProps>(
  function OnlyOfficeEditor(
    {
      agreementId,
      templateId,
      apiBase = '/api',
      canEdit,
      onSave,
      configEndpoint,
      editorContainerId = 'onlyoffice-editor',
      publicSession = false,
    },
    ref,
  ) {
  const editorRef = useRef<HTMLDivElement | null>(null)
  const editorInstanceRef = useRef<any>(null)

  // ── Expose requestSave() to parent components ─────────────────────────────
  // Calling docEditor.requestSave() triggers an OnlyOffice force-save which
  // sends a callback to the backend with status=6.  The backend downloads
  // the latest DOCX (including all in-memory comments) and writes it to disk,
  // then calls _upsert_comments_from_docx.  The caller should wait ~4 seconds
  // after requestSave() returns before reading comment data from the API.
  useImperativeHandle(ref, () => ({
    requestSave: (): boolean => {
      const instance = editorInstanceRef.current
      if (!instance) {
        console.warn('OnlyOfficeEditor.requestSave: editor not ready')
        return false
      }
      try {
        if (typeof instance.requestSave === 'function') {
          instance.requestSave()
          console.log('OnlyOfficeEditor.requestSave: force-save requested')
          return true
        }
        // Fallback: some OO versions expose it differently
        if (instance.asc_requestSave && typeof instance.asc_requestSave === 'function') {
          instance.asc_requestSave()
          return true
        }
        console.warn('OnlyOfficeEditor.requestSave: requestSave() not found on editor instance')
        return false
      } catch (e) {
        console.warn('OnlyOfficeEditor.requestSave: error calling requestSave()', e)
        return false
      }
    },
    insertText: (text: string): boolean => {
      const instance = editorInstanceRef.current
      if (!instance) {
        console.warn('OnlyOfficeEditor.insertText: editor not ready')
        return false
      }
      const payload = String(text || '')
      if (!payload) return true
      try {
        // Preferred: DocEditor.executeCommand(command, ...args)
        if (typeof instance.executeCommand === 'function') {
          // Try to move cursor to end first (best-effort)
          try {
            instance.executeCommand('goToEnd')
          } catch {
            // ignore
          }
          instance.executeCommand('insertText', payload)
          return true
        }
        // Fallback: some builds expose commands differently
        if (typeof instance.serviceCommand === 'function') {
          instance.serviceCommand('insertText', payload)
          return true
        }
        console.warn('OnlyOfficeEditor.insertText: no supported command API found on editor instance')
        return false
      } catch (e) {
        console.warn('OnlyOfficeEditor.insertText: error inserting text', e)
        return false
      }
    },
  }))
  // ─────────────────────────────────────────────────────────────────────────
  const scriptRef = useRef<HTMLScriptElement | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [config, setConfig] = useState<any>(null)
  const [docsApiLoaded, setDocsApiLoaded] = useState(false)
  const [containerEl, setContainerEl] = useState<HTMLDivElement | null>(null)
  const onSaveRef = useRef<typeof onSave>(onSave)
  const initializeEditorRef = useRef<((editorConfig: any) => void) | null>(null)
  // Note: Frontend locking hacks removed - structural DOCX-level locking is now used
  // Locked fields are protected via content controls in the DOCX itself

  const handleContainerRef = (el: HTMLDivElement | null) => {
    editorRef.current = el
    setContainerEl(el)
  }

  useEffect(() => {
    onSaveRef.current = onSave
  }, [onSave])

  useEffect(() => {
    const loadEditor = async () => {
      // Declare configUrl outside try block so it's accessible in catch block
      let configUrl: string = ''
      
      try {
        setLoading(true)
        setError(null)

        // Path under /api only (avoids /api/api/... when apiBase is already /api)
        const pathAfterApi = normalizeOnlyofficeConfigPath({
          configEndpoint,
          agreementId,
          templateId,
        })
        configUrl = pathAfterApi

        const requestUrl = publicSession
          ? absoluteUrlForPublicApi(apiBase, pathAfterApi)
          : pathAfterApi

        // Public signing/review pages must not send CRM JWT: backend chooses token-in-query path.
        const response = publicSession
          ? await axios.get(requestUrl)
          : await api.get(requestUrl)

        const { editorUrl, config: editorConfig } = extractOnlyofficeConfigResponse(response.data)

        // Persist the resolved editor URL so a small preloader at app boot can
        // inject the api.js <script> tag before the user ever opens an editor.
        // By the time they click "Open document", the script is already cached
        // (or fully parsed if they've used the app for a few seconds).
        try {
          window.localStorage.setItem('onlyoffice:editorUrl', editorUrl)
        } catch {
          // localStorage may be unavailable in private/locked-down browsers; non-fatal.
        }

        setConfig(editorConfig)
        
        // Note: Field-level locking is handled entirely at DOCX level via content controls
        // Frontend does not inspect or manage locked fields at all.

        const docsApiReady = () =>
          typeof window !== 'undefined' &&
          !!(window as unknown as { DocsAPI?: { DocEditor?: unknown } }).DocsAPI?.DocEditor

        /** Script URL match is fragile (query strings, redirects). Prefer DocsAPI + loose src match. */
        const findExistingOnlyOfficeScript = (): HTMLScriptElement | undefined => {
          const scripts = Array.from(document.scripts)
          const exact = scripts.find((s) => s.src === editorUrl)
          if (exact) return exact
          return scripts.find(
            (s) =>
              typeof s.src === 'string' &&
              s.src.length > 0 &&
              (s.src.includes('web-apps/apps/api/documents/api.js') ||
                s.src.includes('documents/api.js')),
          )
        }

        /**
         * Wait until DocsAPI exists (script may already be in <head> from a prior visit).
         */
        const waitForDocsApi = (maxMs: number): Promise<void> => {
          const start = Date.now()
          return new Promise((resolve, reject) => {
            const tick = () => {
              if (docsApiReady()) {
                resolve()
                return
              }
              if (Date.now() - start > maxMs) {
                reject(new Error('ONLYOFFICE DocsAPI did not become available in time'))
                return
              }
              window.setTimeout(tick, 50)
            }
            tick()
          })
        }

        const loadOnlyOfficeScript = (src: string) => {
          const script = document.createElement('script')
          // IMPORTANT: Do NOT add a query-string cache-buster here.
          // ONLYOFFICE's api.js derives its own base URL by scanning
          // <script> tags for a src matching
          // "/web-apps/apps/api/documents/api.js". Any extra query params
          // can break that self-location detection on some versions,
          // causing the editor iframe to be rendered with a RELATIVE src
          // (e.g. "/documenteditor/main/index.html?...") which the browser
          // then resolves against the host page origin (our SPA), producing
          // a 404 that the SPA falls back to render — i.e. the CRM UI ends
          // up inside the editor container instead of the editor.
          script.src = src
          // Load synchronously-ish so document.currentScript / the script
          // src-scan logic inside api.js reliably sees this tag.
          script.async = false
          script.defer = false
          try {
            script.setAttribute('data-onlyoffice', 'api')
          } catch {
            /* ignore */
          }
          scriptRef.current = script
          script.onload = () => {
            // DocsAPI readiness is handled below; initialization is driven by container mount + effect.
          }
          script.onerror = () => {
            setError('Failed to load ONLYOFFICE editor script')
            setLoading(false)
            scriptRef.current = null
          }
          document.head.appendChild(script)
        }

        // 1) Ensure api.js is loaded; 2) wait for DocsAPI; 3) mark DocsAPI ready.
        const existing = findExistingOnlyOfficeScript()
        if (existing) {
          try {
            await waitForDocsApi(20000)
            setDocsApiLoaded(true)
          } catch (e) {
            console.error('ONLYOFFICE script in DOM but DocsAPI missing; reloading script once:', e)
            try {
              if (existing.parentNode?.contains(existing)) {
                existing.parentNode.removeChild(existing)
              }
            } catch {
              // ignore stale node cleanup issues
            }
            loadOnlyOfficeScript(editorUrl)
          }
          return
        }

        // Load api.js without a cache-buster so the browser can reuse the cached
        // script across editor opens (the script is ~700 KB; busting it on every
        // open added 1-2s to load time). The comment on loadOnlyOfficeScript
        // above also notes that extra query params can break OnlyOffice's own
        // <script>-src self-location scan and corrupt the iframe URL.
        loadOnlyOfficeScript(editorUrl)

        try {
          await waitForDocsApi(20000)
          setDocsApiLoaded(true)
        } catch (e) {
          console.error('ONLYOFFICE DocsAPI did not become available after script load:', e)
          setError('ONLYOFFICE editor API not loaded. Please refresh the page.')
          setLoading(false)
        }
      } catch (err: any) {
        console.error('Failed to load ONLYOFFICE config:', err)
        const errorMessage = err.response?.data?.detail || err.message || 'Failed to load editor configuration'
        console.error('ONLYOFFICE config load failed:', {
          errorMessage,
          agreementId,
          templateId,
          statusCode: err.response?.status,
          url: configUrl || 'not set',
          configEndpoint
        })
        setError(errorMessage)
        setLoading(false)
      }
    }

    const initializeEditor = (editorConfig: any) => {
      try {
        // Prevent duplicate initialization (React StrictMode can cause double renders)
        if (editorInstanceRef.current) {
          console.log('Editor already initialized, skipping duplicate initialization')
          setLoading(false) // Make sure loading is hidden if editor is already initialized
          return
        }
        
        if (!editorRef.current) {
          console.error('Editor ref is not available')
          return
        }

        if (!window.DocsAPI || !window.DocsAPI.DocEditor) {
          console.error('ONLYOFFICE DocsAPI not available')
          setError('ONLYOFFICE editor API not loaded. Please refresh the page.')
          setLoading(false)
          return
        }

        // Destroy existing editor instance if any (shouldn't happen due to check above, but just in case)
        if (editorInstanceRef.current) {
          try {
            if (typeof editorInstanceRef.current.destroy === 'function') {
              editorInstanceRef.current.destroy()
            }
          } catch (e) {
            console.debug('Error destroying previous editor:', e)
          }
          editorInstanceRef.current = null
        }

        // Log the config for debugging (without sensitive data)
        const configForLog = { ...editorConfig }
        if (configForLog.token) {
          configForLog.token = '[REDACTED]'
        }
        console.log('Initializing ONLYOFFICE editor', {
          containerId: editorRef.current?.id,
          documentUrl: editorConfig.document?.url,
          documentKey: editorConfig.document?.key,
          configKeys: Object.keys(editorConfig),
          hasToken: !!editorConfig.token
        })
        
        // Verify document URL is accessible
        if (editorConfig.document?.url) {
          console.log('Document URL for ONLYOFFICE:', editorConfig.document.url)
        }

        // Initialize ONLYOFFICE editor
        let docEditor: any
        try {
          const domId = editorRef.current.id || editorContainerId
          if (!editorRef.current.id) {
            editorRef.current.id = domId
          }
          
          // Store editor instance reference for locking functionality
          
          // Log the full config before creating editor (for debugging)
          console.log('Creating editor with config:', {
            containerId: domId,
            documentUrl: editorConfig.document?.url,
            documentKey: editorConfig.document?.key,
            documentType: editorConfig.documentType,
            mode: editorConfig.editorConfig?.mode,
            hasToken: !!editorConfig.token,
            configString: JSON.stringify(editorConfig).substring(0, 500)
          })
          
          try {
            // Use the ref directly - it's more reliable than getElementById
            const containerElement = editorRef.current
            if (!containerElement) {
              throw new Error(`Container element ref is null`)
            }
            
            if (!containerElement.isConnected) {
              console.error('ONLYOFFICE init aborted: container not mounted')
              setError('Editor container not ready. Please refresh.')
              setLoading(false)
              return
            }

            // Ensure element has an ID (ONLYOFFICE requires it)
            if (!containerElement.id) {
              containerElement.id = domId
            }
            
            const containerRect = containerElement.getBoundingClientRect()
            console.log('Container element check:', {
              exists: !!containerElement,
              isConnected: containerElement.isConnected,
              id: containerElement.id,
              width: containerRect.width,
              height: containerRect.height,
              hasDimensions: containerRect.width > 0 && containerRect.height > 0,
              domId,
            })
            
            if (containerRect.width === 0 || containerRect.height === 0) {
              console.warn('⚠️ Container has zero dimensions - ONLYOFFICE may not render!')
            }
            
            // Log full config for debugging (redact token)
            const configForDebug = JSON.parse(JSON.stringify(editorConfig))
            if (configForDebug.token) {
              configForDebug.token = '[REDACTED]'
            }
            console.log('Creating ONLYOFFICE editor with config:', JSON.stringify(configForDebug, null, 2))
            
            docEditor = new window.DocsAPI.DocEditor(domId, editorConfig)
            editorInstanceRef.current = docEditor
            
            console.log('✅ Editor instance created successfully', {
              hasEvents: !!docEditor?.events,
              hasDestroy: typeof docEditor?.destroy === 'function',
              editorType: typeof docEditor,
              editorKeys: docEditor ? Object.keys(docEditor) : [],
              editorValue: docEditor
            })
            
            // Set loading to false after editor creation to hide loading spinner
            // This ensures loading is hidden even if events aren't available
            setTimeout(() => {
              if (editorRef.current) {
                const iframes = editorRef.current.querySelectorAll('iframe')
                if (iframes.length > 0 || editorRef.current.children.length > 0) {
                  console.log('✅ Editor iframe/content detected immediately - hiding loading')
                }
              }
              console.log('Hiding loading after editor creation')
              setLoading(false)
            }, 500)
            
            // Check for errors in the editor object
            if (docEditor && typeof docEditor === 'object') {
              // Check if there's an error property
              const errorProps = Object.keys(docEditor).filter((key) => {
                const k = typeof key === 'string' ? key : String(key)
                return (
                  k.toLowerCase().includes('error') ||
                  k.toLowerCase().includes('fail') ||
                  k.toLowerCase().includes('message')
                )
              })
              if (errorProps.length > 0) {
                console.warn('Editor object has potential error properties:', errorProps)
                errorProps.forEach(prop => {
                  console.warn(`  ${prop}:`, docEditor[prop])
                })
              }
            }
          } catch (editorError: any) {
            console.error('Error during editor creation:', editorError)
            console.error('Editor error details:', {
              message: editorError?.message,
              stack: editorError?.stack,
              name: editorError?.name
            })
            setError(`Failed to create editor: ${editorError?.message || 'Unknown error'}`)
            setLoading(false)
            return
          }
          
          // Check if editor container has content after initialization
          // Check multiple times to catch delayed rendering
          const checkRendering = (attempt: number) => {
            if (editorRef.current) {
              const iframes = editorRef.current.querySelectorAll('iframe')
              const hasContent = editorRef.current.children.length > 0 || editorRef.current.innerHTML.trim().length > 0
              const hasIframe = iframes.length > 0
              
              console.log(`Editor container check (attempt ${attempt}):`, {
                hasChildren: editorRef.current.children.length,
                iframeCount: iframes.length,
                hasIframe: hasIframe,
                innerHTML: editorRef.current.innerHTML.substring(0, 200),
                hasContent: hasContent,
                containerDimensions: {
                  width: editorRef.current.offsetWidth,
                  height: editorRef.current.offsetHeight,
                  clientWidth: editorRef.current.clientWidth,
                  clientHeight: editorRef.current.clientHeight
                }
              })
              
              if (hasIframe) {
                console.log('✅ Editor iframe detected - editor is rendering!')
                setLoading(false)
              } else if (attempt < 5) {
                // Check again after delay
                setTimeout(() => checkRendering(attempt + 1), 1000)
              } else {
                console.warn('⚠️ No iframe detected after multiple checks - editor may not be rendering')
                setLoading(false) // Still hide loading to show container
              }
            }
          }
          
          // Start checking after initial delay
          setTimeout(() => checkRendering(1), 1000)
        } catch (initError: any) {
          console.error('Error creating editor instance:', initError)
          setError(`Failed to create editor: ${initError.message || 'Unknown error'}`)
          setLoading(false)
          return
        }

        // Check if editor was created
        if (!docEditor) {
          console.error('Editor instance is null or undefined')
          setError('Failed to create editor instance')
          setLoading(false)
          return
        }

        // Try to set up events immediately, with fallback
        const setupEvents = () => {
          // Check if events are available - try different ways to access events
          let events = docEditor.events
          
          // Some versions of ONLYOFFICE might have events in a different location
          if (!events && docEditor.constructor && docEditor.constructor.prototype) {
            events = docEditor.constructor.prototype.events
          }
          
          // Check if events are available
          if (events && typeof events.on === 'function') {
            try {
              events.on('documentReady', () => {
                setLoading(false)
                console.log('ONLYOFFICE editor ready')
              })

              events.on('documentStateChange', (event: any) => {
                console.log('Document state changed', event)
                // Status 1 = document ready for editing
                // Status 2 = document is being saved (autosave)
                // Status 6 = document is being force saved (manual save)
                // Status 7 = document save error
                
                // Trigger refresh when document is saved (status 2 or 6)
                if (event && (event === 2 || event === 6)) {
                  console.log('Document saved, triggering refresh')
                onSaveRef.current?.()
                }
              })

              events.on('onRequestSave', (event: any) => {
                console.log('Save requested', event)
                onSaveRef.current?.()
              })

              events.on('onError', (event: any) => {
                console.error('ONLYOFFICE error:', event)
                setError(`Editor error: ${event}`)
                setLoading(false)
              })
              
              console.log('Editor events registered successfully')
            } catch (eventError: any) {
              console.warn('Error registering editor events:', eventError)
              // Continue anyway - editor might still work
              setTimeout(() => setLoading(false), 2000)
            }
          } else {
            console.warn('Editor events not available', {
              hasEvents: !!docEditor.events,
              eventsType: typeof docEditor.events,
              eventsKeys: docEditor.events ? Object.keys(docEditor.events) : [],
              fullEditorKeys: Object.keys(docEditor),
              editorPrototype: Object.getPrototypeOf(docEditor) ? Object.keys(Object.getPrototypeOf(docEditor)) : []
            })
            
            // Check if editor is rendering even without events
            // The editor might still work, just without event callbacks
            setTimeout(() => {
              // Check if iframe or content was created
              if (editorRef.current) {
                const iframes = editorRef.current.querySelectorAll('iframe')
                const hasIframe = iframes.length > 0
                console.log('Editor rendering check:', {
                  hasIframe: hasIframe,
                  iframeCount: iframes.length,
                  containerHTML: editorRef.current.innerHTML.substring(0, 200)
                })
                
                if (hasIframe) {
                  console.log('✅ Editor iframe detected - editor is rendering!')
                  // Loading already set to false above, but set it again to be sure
                  setLoading(false)
                } else {
                  console.warn('⚠️ No iframe detected - but loading already hidden')
                  // Loading already set to false above
                }
              }
              // Loading already set to false above, no need to set here
            }, 2000)
          }
        }

        // Try to set up events immediately
        setupEvents()
        
        // Also try after a short delay in case events become available later
        setTimeout(setupEvents, 500)
      } catch (err: any) {
        console.error('Failed to initialize ONLYOFFICE editor:', err)
        setError(`Failed to initialize editor: ${err.message || 'Unknown error'}`)
        setLoading(false)
      }
    }

    initializeEditorRef.current = initializeEditor

    loadEditor()

    return () => {
      initializeEditorRef.current = null
      // Cleanup editor instance
      if (editorInstanceRef.current) {
        try {
          editorInstanceRef.current.destroy()
          editorInstanceRef.current = null
        } catch (e) {
          console.debug('Error destroying editor:', e)
        }
      }

      // IMPORTANT: Do NOT remove the ONLYOFFICE api.js <script> tag on unmount.
      //
      // ONLYOFFICE's api.js derives the Document Server base URL at the moment
      // you call `new DocsAPI.DocEditor(...)` by scanning
      // `document.getElementsByTagName('script')` for a src matching
      // `/api/documents/api.js`. If the script tag has been removed from the
      // DOM (but `window.DocsAPI` is still cached), that scan returns no
      // match and ONLYOFFICE falls back to an EMPTY base URL. The editor
      // iframe is then created with a RELATIVE src
      // (e.g. `/documenteditor/main/index.html?...`) which the browser
      // resolves against the host page origin (our SPA) instead of the
      // ONLYOFFICE server. The SPA then serves `index.html` for that path,
      // and the entire CRM app ends up rendered inside the editor container
      // instead of the real editor.
      //
      // Leaving the script in <head> is safe — it's idempotent across
      // mounts and matches the pattern used by agreements/templates flows.
      scriptRef.current = null

      // Note: we intentionally do NOT manually clear editorRef children here.
      // ONLYOFFICE manages the DOM inside this container, and React should not
      // try to reconcile or manipulate those child nodes.
    }
  }, [agreementId, templateId, configEndpoint, apiBase, publicSession, editorContainerId])
  // NOTE: onSave is intentionally NOT in dependencies to prevent remounting
  // The onSave callback is stable and doesn't need to trigger editor reload

  useEffect(() => {
    if (!config) return
    if (!docsApiLoaded) return
    if (!containerEl) return
    if (editorInstanceRef.current) return

    const raf = requestAnimationFrame(() => {
      if (containerEl && containerEl.isConnected) {
        initializeEditorRef.current?.(config)
      } else {
        console.warn('Skipping ONLYOFFICE init: container not ready')
      }
    })

    return () => cancelAnimationFrame(raf)
  }, [config, docsApiLoaded, containerEl])

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="text-center">
          <div className="text-red-600 mb-2">⚠️ Error</div>
          <div className="text-sm text-gray-600">{error}</div>
        </div>
      </div>
    )
  }

  return (
    <div
      className="flex flex-col h-full w-full"
      // Ensure the editor area has enough vertical space and can scroll
      style={{ minHeight: '700px' }}
    >
      {loading && (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
            <div className="text-sm text-gray-600">Loading editor...</div>
          </div>
        </div>
      )}
      {!canEdit && (
        <div className="border-b border-yellow-200 p-2 bg-yellow-50 text-xs text-yellow-800 text-center">
          Editor is in read-only mode. Editing is not allowed for this status.
        </div>
      )}
      {/* ONLYOFFICE container - React should not manage children */}
      <div
        className="flex-1 w-full"
        style={{ 
          minHeight: '600px', 
          height: '100%',
          width: '100%', 
          position: 'relative', 
          display: 'flex', 
          flexDirection: 'column' 
        }}
      >
        <div
          id={editorContainerId}
          ref={handleContainerRef}
          style={{ 
            width: '100%', 
            height: '100%', 
            minHeight: '600px',
            flex: '1 1 auto',
            position: 'relative',
            display: 'block',
            overflow: 'hidden'
          }}
        />
      </div>
    </div>
  )
  } // end forwardRef render function
) // end forwardRef

// Extend Window interface for ONLYOFFICE
declare global {
  interface Window {
    DocsAPI: {
      DocEditor: new (id: string, config: any) => {
        events: {
          on: (event: string, callback: (data?: any) => void) => void
        }
      }
    }
  }
}

export default OnlyOfficeEditor
