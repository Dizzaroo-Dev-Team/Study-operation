/**
 * Warm-load the OnlyOffice editor api.js as early as possible during the app
 * boot, so that the first time a user opens a document the script and its
 * dependent assets are already parsed and cached.
 *
 * The OnlyOffice document-server base URL is environment-specific (production
 * vs. staging vs. local), so we don't hard-code it. Instead, after the first
 * successful /onlyoffice-config call we persist the editor URL to
 * localStorage; on the next page load we reuse that URL to prime the script.
 *
 * First visit: no-op (no cached URL yet) — same speed as before.
 * Subsequent visits: api.js is preloaded → editor opens in ~1-2 s instead of
 * 5-10 s.
 */

let preloadStarted = false

function findExistingScript(): HTMLScriptElement | undefined {
  const scripts = Array.from(document.scripts)
  return scripts.find(
    (s) =>
      typeof s.src === 'string' &&
      s.src.length > 0 &&
      (s.src.includes('web-apps/apps/api/documents/api.js') ||
        s.src.includes('documents/api.js')),
  )
}

export function preloadOnlyOfficeApi(): void {
  if (preloadStarted) return
  preloadStarted = true

  let cachedUrl: string | null = null
  try {
    cachedUrl = window.localStorage.getItem('onlyoffice:editorUrl')
  } catch {
    return
  }
  if (!cachedUrl) return

  // If a script tag is already in the DOM (HMR, prior mount), skip.
  if (findExistingScript()) return

  // Defer to idle time so the preload never competes with first paint.
  const inject = () => {
    if (findExistingScript()) return
    const script = document.createElement('script')
    script.src = cachedUrl!
    // Loading async is fine here — the editor component's own bootstrap waits
    // for `window.DocsAPI` to be defined before instantiating the editor.
    script.async = true
    script.defer = true
    script.setAttribute('data-onlyoffice', 'api')
    script.setAttribute('data-preloaded', 'true')
    document.head.appendChild(script)
  }

  const ric = (window as unknown as { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void })
    .requestIdleCallback
  if (typeof ric === 'function') {
    ric(inject, { timeout: 2000 })
  } else {
    window.setTimeout(inject, 250)
  }
}
