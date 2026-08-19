import React, { createContext, useCallback, useContext, useState, useEffect, useMemo, useRef } from 'react'
import { api } from '../lib/api'
import { useAuth } from './AuthContext'

// ── localStorage helpers ────────────────────────────────────────────────────
const STORAGE_STUDY_KEY = 'dizzaroo_selected_study'
const STORAGE_SITE_KEY  = 'dizzaroo_selected_site'

function lsRead(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function lsWrite(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* storage quota / private mode — ignore */ }
}
function lsClear(key: string): void {
  try { localStorage.removeItem(key) } catch { /* ignore */ }
}

interface Study {
  id: string
  study_id: string
  name: string
  description?: string
  status?: string
}

interface Site {
  id: string
  site_id: string
  study_id: string
  name: string
  code?: string
  location?: string
  principal_investigator?: string
  address?: string
  city?: string
  country?: string
  status?: string
}

const LS = {
  lastStudyId: 'crm.lastStudyId',
  lastModule: 'crm.lastModule',
  lastTab: 'crm.lastTab',
  lastSubTab: 'crm.lastSubTab',
} as const

interface StudySiteContextValue {
  studies: Study[]
  sites: Site[]
  selectedStudyId: string | null
  selectedSiteId: string | null
  setSelectedStudyId: (id: string | null) => void
  setSelectedSiteId: (id: string | null) => void
  filteredSites: Site[]
  loading: boolean
  refreshSites: () => Promise<void>
  lastModule: string | null
  setLastModule: (mode: string) => void
  lastTab: string | null
  setLastTab: (tabId: string) => void
  // Deep-link a sub-view inside a tab, e.g. 'template-library:clauses'. Consumed
  // by the parent tab component to activate its sub-tab.
  lastSubTab: string | null
  setLastSubTab: (v: string) => void
  accessError: string | null
  dismissAccessError: () => void
}

const StudySiteContext = createContext<StudySiteContextValue | undefined>(undefined)

export const useStudySite = () => {
  const context = useContext(StudySiteContext)
  if (!context) {
    throw new Error('useStudySite must be used within StudySiteProvider')
  }
  return context
}

// interface StudySiteProviderProps {
//   children: React.ReactNode
//   apiBase: string
// }
interface StudySiteProviderProps {
  children: React.ReactNode
}


export const StudySiteProvider: React.FC<StudySiteProviderProps> = ({ children }) => {
  // Gate study + site loading on `user`, not `token`. Under SSO the session
  // cookie carries identity and `token` is always null in AuthContext, so a
  // token-gated effect would never fire and studies would silently stay
  // empty (the symptom: "no studies appear in the dropdown after login").
  // `user` is the cross-mode signal — set by /auth/me success in both
  // local-password and SSO flows.
  const { user } = useAuth()
  const [studies, setStudies] = useState<Study[]>([])
  const [sites, setSites] = useState<Site[]>([])
  const [selectedStudyId, setSelectedStudyIdState] = useState<string | null>(null)
  const [selectedSiteId, setSelectedSiteIdState] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [autoSelectDone, setAutoSelectDone] = useState(false)
  const [lastModule, setLastModuleState] = useState<string | null>(
    () => (typeof window !== 'undefined' ? localStorage.getItem(LS.lastModule) : null)
  )
  const [lastTab, setLastTabState] = useState<string | null>(
    () => (typeof window !== 'undefined' ? localStorage.getItem(LS.lastTab) : null)
  )
  const [lastSubTab, setLastSubTabState] = useState<string | null>(
    () => (typeof window !== 'undefined' ? localStorage.getItem(LS.lastSubTab) : null)
  )

  // Setters are useCallback-stable so the memoized context value below does
  // not invalidate on every render of StudySiteProvider. Every consumer of
  // useStudySite() would otherwise re-render on every parent tick.
  const setSelectedStudyId = useCallback((id: string | null) => {
    setSelectedStudyIdState(id)
    if (typeof window !== 'undefined') {
      if (id) {
        localStorage.setItem(LS.lastStudyId, id)
        lsWrite(STORAGE_STUDY_KEY, id)
      } else {
        localStorage.removeItem(LS.lastStudyId)
        lsClear(STORAGE_STUDY_KEY)
      }
    }
  }, [])

  const setSelectedSiteId = useCallback((id: string | null) => {
    setSelectedSiteIdState(id)
    if (id) lsWrite(STORAGE_SITE_KEY, id)
    else lsClear(STORAGE_SITE_KEY)
  }, [])

  const setLastModule = useCallback((mode: string) => {
    setLastModuleState(mode)
    if (typeof window !== 'undefined') localStorage.setItem(LS.lastModule, mode)
  }, [])

  const setLastTab = useCallback((tabId: string) => {
    setLastTabState(tabId)
    if (typeof window !== 'undefined') localStorage.setItem(LS.lastTab, tabId)
  }, [])

  const setLastSubTab = useCallback((v: string) => {
    setLastSubTabState(v)
    if (typeof window !== 'undefined') localStorage.setItem(LS.lastSubTab, v)
  }, [])

  // Guard: only attempt site hydration on the very first loadSites call
  const hasHydratedSite = useRef(false)

  // One-shot access error banner — set when a deep-link intent points at a
  // study/site the current user can't see. Auto-clears after ~6 seconds.
  const [accessError, setAccessError] = useState<string | null>(null)
  useEffect(() => {
    if (!accessError) return
    const t = setTimeout(() => setAccessError(null), 6000)
    return () => clearTimeout(t)
  }, [accessError])

  // Has the openAgreementIntent already been consumed? (Prevents the intent
  // re-firing on every loadSites call as the user switches studies later.)
  const hasConsumedIntent = useRef(false)

  // ── load triggers ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (user) {
      loadStudies()
    } else {
      setStudies([])
      setSelectedStudyId(null)
      setAutoSelectDone(false)
    }
  }, [user])

  // Auto-select study once after studies finish loading.
  // 1 study → auto. Multiple → restore last (from localStorage). Else → first available.
  useEffect(() => {
    if (loading || autoSelectDone || studies.length === 0) return
    const stored = typeof window !== 'undefined' ? localStorage.getItem(LS.lastStudyId) : null
    let pick: string | null = null
    if (studies.length === 1) {
      pick = studies[0].id
    } else if (stored && studies.some((s) => s.id === stored)) {
      pick = stored
    } else {
      pick = studies[0].id
    }
    if (pick && pick !== selectedStudyId) {
      setSelectedStudyId(pick)
    }
    setAutoSelectDone(true)
  }, [loading, studies, autoSelectDone, selectedStudyId])

  useEffect(() => {
    if (user && selectedStudyId) {
      void loadSites(selectedStudyId)
    } else {
      setSites([])
      setSelectedSiteId(null)
    }
  }, [user, selectedStudyId])

  // ── data fetchers ─────────────────────────────────────────────────────────
  const loadStudies = async () => {
    try {
      setLoading(true)
      const response = await api.get<Study[]>('/studies')
      setStudies(response.data)

      // Deep-link intent (from CTA notification inbox click): if it names a
      // study the user CAN'T see, surface the access error here and clear the
      // intent so we don't keep retrying.
      try {
        const raw = typeof window !== 'undefined' ? localStorage.getItem('crm.openAgreementIntent') : null
        if (raw) {
          const intent = JSON.parse(raw) as { study_id?: string; site_id?: string }
          if (intent.study_id) {
            const studyMatch = response.data.some(
              (s) => s.id === intent.study_id || (s as any).study_id === intent.study_id,
            )
            if (!studyMatch) {
              setAccessError('You do not have access to the study linked from that notification.')
              localStorage.removeItem('crm.openAgreementIntent')
              hasConsumedIntent.current = true
            } else {
              // Force the study match so the rest of the flow picks it up,
              // even if a different lastStudyId is stored.
              setSelectedStudyId(intent.study_id)
              // Intent only consumed once site selection also resolves; do
              // NOT clear localStorage here.
            }
          }
        }
      } catch (exc) {
        console.warn('openAgreementIntent: failed to parse intent', exc)
      }

      // Hydrate: restore last-used study from localStorage (skip if intent
      // already picked one above).
      if (!hasConsumedIntent.current) {
        const savedStudyId = lsRead(STORAGE_STUDY_KEY)
        if (savedStudyId && response.data.some(s => s.id === savedStudyId)) {
          setSelectedStudyId(savedStudyId)
        }
      }
    } catch (error) {
      console.error('Error loading studies:', error)
      setStudies([])
    } finally {
      setLoading(false)
    }
  }

  const loadSites = async (studyId: string) => {
    try {
      setLoading(true)

      const fetchSitesForStudyParam = async (param: string) => {
        const response = await api.get<Site[]>('/sites', {
          params: { study_id: param },
        })
        return response.data
      }

      // `/studies` uses IAM resource IDs; `/sites` resolves Postgres `studies` by UUID or
      // external `study_id`. When IAM `_id` ≠ Postgres PK, first call returns [] — retry
      // with the roster's `study_id` (name / resourceExternalId / code).
      let data = await fetchSitesForStudyParam(studyId)
      if (data.length === 0) {
        const meta = studies.find((s) => s.id === studyId)
        const alt = meta?.study_id?.trim()
        if (alt && alt !== studyId) {
          data = await fetchSitesForStudyParam(alt)
        }
      }

      setSites(data)

      // Deep-link intent: if the notification names a specific site, try to
      // select it. If it isn't in the user's accessible site list, raise an
      // access error and clear the intent.
      try {
        const raw = typeof window !== 'undefined' ? localStorage.getItem('crm.openAgreementIntent') : null
        if (raw) {
          const intent = JSON.parse(raw) as { study_id?: string; site_id?: string }
          if (intent.site_id) {
            const siteMatch = data.find(
              (s) => s.id === intent.site_id || s.site_id === intent.site_id,
            )
            if (siteMatch) {
              const sitePick = siteMatch.id || siteMatch.site_id
              if (sitePick) setSelectedSiteId(sitePick)
              hasHydratedSite.current = true
              hasConsumedIntent.current = true
              localStorage.removeItem('crm.openAgreementIntent')
              return
            } else {
              setAccessError('You do not have access to the site linked from that notification.')
              localStorage.removeItem('crm.openAgreementIntent')
              hasConsumedIntent.current = true
              // Fall through to normal hydration below
            }
          }
        }
      } catch (exc) {
        console.warn('openAgreementIntent: failed to parse intent in loadSites', exc)
      }

      // Hydrate: restore last-used site from localStorage (first call only)
      if (!hasHydratedSite.current) {
        hasHydratedSite.current = true
        const savedSiteId = lsRead(STORAGE_SITE_KEY)
        if (savedSiteId && data.some((s) => s.id === savedSiteId || s.site_id === savedSiteId)) {
          setSelectedSiteId(savedSiteId)
          return
        }
      }

      // Validate: clear current site if it no longer belongs to the new list
      if (selectedSiteId) {
        const stillValid = data.some((s) => s.id === selectedSiteId || s.site_id === selectedSiteId)
        if (!stillValid) {
          setSelectedSiteId(null)
          lsClear(STORAGE_SITE_KEY)
        }
      }
    } catch (error) {
      console.error('Error loading sites:', error)
      setSites([])
    } finally {
      setLoading(false)
    }
  }

  // Sites are study-scoped server-side: `/api/sites?study_id=…` joins through
  // `study_sites` and only returns rows linked to the active study. The list
  // here mirrors what Study Setup → Site Setup shows for the same study.
  const filteredSites = useMemo(() => {
    if (!selectedStudyId) return []
    return sites
  }, [sites, selectedStudyId])

  // Refetch the site roster for the active study without forcing the user to
  // toggle studies. Wired into Site Setup so a fresh create/update/delete is
  // visible everywhere (navbar, conversations, monitoring, …) immediately.
  //
  // `loadSites` is intentionally NOT in the dep list — it's a closure over
  // component state that would force a new identity every render, which is
  // exactly what useCallback exists to prevent. `selectedStudyId` is the only
  // value we actually need to react to.
  const refreshSites = useCallback(async () => {
    if (selectedStudyId) {
      await loadSites(selectedStudyId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStudyId])

  // Memoize the context value so consumers don't re-render every tick. New
  // object identity only when one of these values actually changes. NOTE: a
  // future task should split this into two contexts — a stable {studies, sites}
  // list context and a fast-changing {selectedStudyId, selectedSiteId} one —
  // so dropdown consumers don't invalidate on selection changes and vice-versa.
  const dismissAccessError = useCallback(() => setAccessError(null), [])

  const value = useMemo<StudySiteContextValue>(
    () => ({
      studies,
      sites,
      selectedStudyId,
      selectedSiteId,
      setSelectedStudyId,
      setSelectedSiteId,
      filteredSites,
      loading,
      refreshSites,
      lastModule,
      setLastModule,
      lastTab,
      setLastTab,
      lastSubTab,
      setLastSubTab,
      accessError,
      dismissAccessError,
    }),
    [
      studies,
      sites,
      selectedStudyId,
      selectedSiteId,
      setSelectedStudyId,
      setSelectedSiteId,
      filteredSites,
      loading,
      refreshSites,
      lastModule,
      setLastModule,
      lastTab,
      setLastTab,
      lastSubTab,
      setLastSubTab,
      accessError,
      dismissAccessError,
    ],
  )

  return (
    <StudySiteContext.Provider value={value}>
      {accessError && (
        <div className="fixed top-4 right-4 z-50 max-w-md bg-red-50 border border-red-300 text-red-800 rounded-lg shadow-lg p-3 flex items-start gap-2">
          <span className="font-bold leading-none mt-0.5">!</span>
          <div className="flex-1 text-sm">
            <p className="font-semibold">Access denied</p>
            <p className="mt-0.5">{accessError}</p>
          </div>
          <button
            type="button"
            onClick={dismissAccessError}
            className="text-red-700 hover:text-red-900 focus:outline-none focus:ring-2 focus:ring-red-300 rounded text-xs"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
      {children}
    </StudySiteContext.Provider>
  )
}

