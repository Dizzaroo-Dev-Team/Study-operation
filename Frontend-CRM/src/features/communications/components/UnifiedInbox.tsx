import React, { useCallback, useMemo, useState, useEffect, Suspense, lazy } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useStudySite } from '@/contexts/StudySiteContext'
import {
  useConversationsList,
  useCreateConversation,
  useDeleteConversation,
} from '@/lib/queries/useConversations'
import { useThreadsList, useCreateThread } from '@/lib/queries/useThreads'
import ConversationList from './ConversationList'
import ConversationDetail from './ConversationDetail'
import CreateConversationModal from './CreateConversationModal'
import ThreadList from './ThreadList'
import ThreadDetail from './ThreadDetail'
import CreateThreadModal from './CreateThreadModal'
import ThreadCombinationSuggestions from './ThreadCombinationSuggestions'
// Heavy, conditionally-rendered tabs are lazy-loaded so they no longer bloat
// the main entry chunk. WorkspaceHome stays eager because it is the empty
// state of the conversations panel and is shown on first paint.
//
// IRBAdministrativeInfo is rendered with `hidden` CSS rather than conditional
// JSX so its draft state survives subtab switches. Lazy() still works: once
// Suspense resolves on first reveal the module is cached, and the kept-mounted
// instance remains in the tree thereafter.
const SiteControlTower      = lazy(() => import('@/features/sites/components/SiteControlTower'))
const MonitoringTab         = lazy(() => import('@/features/monitoring/components/MonitoringTab'))
const ISFModule             = lazy(() => import('@/modules/isf/ISFModule'))
const SiteProfileTab        = lazy(() => import('@/features/sites/components/SiteProfileTab'))
const SiteStaffDetailsTab   = lazy(() => import('@/features/sites/components/SiteStaffDetailsTab'))
const IRBAdministrativeInfo = lazy(() => import('@/features/sites/forms/IRBAdministrativeInfo'))
const Dashboard             = lazy(() => import('@/features/sites/components/Dashboard'))
const StudySetup            = lazy(() => import('@/features/study-setup/StudySetup'))
const TasksTab              = lazy(() => import('@/features/operations/components/TasksTab'))
import WorkspaceHome from '@/components/WorkspaceHome'
import ResizableSidebar from '@/components/ResizableSidebar'
import SiteRequiredPrompt from '@/components/SiteRequiredPrompt'
import { FORMS_NAV_ITEMS } from '@/components/Navbar/FormsDropdown'
import { Conversation, Thread } from '@/types'

// Tiny shared fallback. Intentionally not a spinner — feature panes already
// surface their own loading states; a passive skeleton avoids fallback flash.
const TabFallback: React.FC = () => (
  <div className="flex-1 h-full bg-slate-50 animate-pulse" aria-busy="true" />
)

interface UnifiedInboxProps {
  apiBase: string
  onNavigateToUsers?: () => void
  currentMode?: string
  onModeChange?: (mode: string) => void
}

const UnifiedInbox: React.FC<UnifiedInboxProps> = ({
  apiBase,
  currentMode: externalMode,
  onModeChange,
}) => {
  const { user } = useAuth()
  const {
    selectedStudyId,
    selectedSiteId,
    studies,
    filteredSites,
  } = useStudySite()

  const currentUserId = user?.user_id || ''
  const [internalMode] = useState<
    'conversations' | 'threads' | 'users' | 'sites' | 'ask' | 'site-status' | 'logistics' | 'monitoring'
  >('conversations')

  const [conversationsTab, setConversationsTab] =
    useState<'conversations' | 'threads'>('conversations')

  const [sitesTab, setSitesTab] =
    useState<'site-status' | 'logistics' | 'monitoring' | 'documents' | 'agreements' | 'study-setup' | 'site-profile' | 'site-staff-details' | 'irb-administrative-info'>('site-status')

  useEffect(() => {
    const currentMode = externalMode || internalMode

    if (currentMode === 'threads') {
      setConversationsTab('threads')
    } else if (currentMode === 'conversations') {
      setConversationsTab('conversations')
    } else if (
      currentMode === 'site-status' ||
      currentMode === 'logistics' ||
      currentMode === 'monitoring' ||
      currentMode === 'documents' ||
      currentMode === 'agreements' ||
      currentMode === 'study-setup' ||
      currentMode === 'site-profile' ||
      currentMode === 'site-staff-details' ||
      currentMode === 'irb-administrative-info'
    ) {
      setSitesTab(currentMode as any)
    }
  }, [externalMode, internalMode])

  let topLevelMode = externalMode || internalMode
  if (topLevelMode === 'threads') topLevelMode = 'conversations'
  else if (
    topLevelMode === 'site-status' ||
    topLevelMode === 'logistics' ||
    topLevelMode === 'monitoring' ||
    topLevelMode === 'documents' ||
    topLevelMode === 'agreements' ||
    topLevelMode === 'study-setup' ||
    topLevelMode === 'site-profile' ||
    topLevelMode === 'site-staff-details' ||
    topLevelMode === 'irb-administrative-info'
  ) {
    topLevelMode = 'sites'
  }

  let activeTab: string
  if (topLevelMode === 'conversations') activeTab = conversationsTab
  else if (topLevelMode === 'sites') activeTab = sitesTab
  else activeTab = topLevelMode

  // Track selections by ID; derive the full object from the cached list.
  // Previously this stored the whole conversation/thread object and re-
  // fetched its detail on click. ConversationDetail / ThreadDetail re-fetch
  // their own data (messages, etc.) on mount, so the pre-fetch was redundant
  // — dropping it removes one round-trip per click.
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)

  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showCreateThreadModal, setShowCreateThreadModal] = useState(false)

  const [filters, setFilters] = useState({ search: '' })

  // List queries — replace the old `useEffect + loadConversations + setInterval(30s)`
  // pattern. TanStack Query handles:
  //   * One in-flight request per unique key (sidebar + command palette no longer race)
  //   * Refetch on window focus (covers the "user came back to the tab" case
  //     the 30s timer was approximating)
  //   * Background refetch when staleTime elapses
  //   * WS-pushed updates invalidate via `realtime.subscribe` consumers
  //
  // `enabled` is gated on selected study+site so we don't fire a
  // study-less list query at boot.
  const baseFilters = useMemo(
    () => ({ study_id: selectedStudyId, site_id: selectedSiteId, limit: 100, offset: 0 }),
    [selectedStudyId, selectedSiteId],
  )
  const conversationsQuery = useConversationsList(baseFilters, {
    enabled: Boolean(selectedStudyId && selectedSiteId) && activeTab === 'conversations',
  })
  const threadsQuery = useThreadsList(baseFilters, {
    enabled: Boolean(selectedStudyId && selectedSiteId) && activeTab === 'threads',
  })

  const allConversations: Conversation[] = conversationsQuery.data ?? []
  const allThreads: Thread[] = threadsQuery.data ?? []

  // Client-side search filter on the list — same shape as the old code.
  const conversations: Conversation[] = useMemo(() => {
    const s = filters.search.trim().toLowerCase()
    if (!s) return allConversations
    return allConversations.filter(
      (c) =>
        c.participant_phone?.toLowerCase().includes(s) ||
        c.participant_email?.toLowerCase().includes(s) ||
        c.subject?.toLowerCase().includes(s),
    )
  }, [allConversations, filters.search])

  const threads: Thread[] = allThreads
  const isLoading = conversationsQuery.isFetching || threadsQuery.isFetching

  // Derive selected objects from the cached lists. If the list doesn't have
  // the selected id yet (race between selection and list refetch), pass null
  // — the detail components handle that by showing their own loader.
  const selectedConversation: Conversation | null = useMemo(
    () =>
      selectedConversationId
        ? allConversations.find((c) => c.id === selectedConversationId) ?? null
        : null,
    [allConversations, selectedConversationId],
  )
  const selectedThread: Thread | null = useMemo(
    () =>
      selectedThreadId ? allThreads.find((t) => t.id === selectedThreadId) ?? null : null,
    [allThreads, selectedThreadId],
  )

  // Stable selection callbacks so memoized rows (ConversationRow / ThreadRow)
  // don't churn on every parent render.
  const handleSelectConversation = useCallback((id: string) => {
    setError(null)
    setSelectedConversationId(id)
  }, [])
  const handleSelectThread = useCallback((id: string) => {
    setError(null)
    setSelectedThreadId(id)
  }, [])

  // Deselect the open conversation/thread so the WorkspaceHome landing surface
  // comes back. Without this the only way back to the home page was a full
  // browser refresh (which clears selection via the study/site reset effect).
  const handleBackToHome = useCallback(() => {
    setError(null)
    setSelectedConversationId(null)
    setSelectedThreadId(null)
  }, [])

  // Reset selection when the study/site changes.
  useEffect(() => {
    setSelectedConversationId(null)
    setSelectedThreadId(null)
  }, [selectedStudyId, selectedSiteId])

  // Listen for `crm:select-conversation` events dispatched by the global
  // ⌘K palette so users can jump straight to a conversation by ID.
  useEffect(() => {
    const onSelect = (e: Event) => {
      const detail = (e as CustomEvent<{ id?: string }>).detail
      if (detail?.id) handleSelectConversation(detail.id)
    }
    window.addEventListener('crm:select-conversation', onSelect)
    return () => window.removeEventListener('crm:select-conversation', onSelect)
  }, [handleSelectConversation])

  // Mutations — invalidations live in the hooks; here we just wire success
  // into local UI (close modal, select the new row, surface errors).
  const createConvMutation = useCreateConversation()
  const deleteConvMutation = useDeleteConversation()
  const isCreatingConversation = createConvMutation.isPending

  const handleCreateConversation = useCallback(
    async (data: {
      participant_phone?: string
      participant_email?: string
      participant_emails?: string[]
      subject?: string
      study_id?: string
    }) => {
      if (createConvMutation.isPending) return
      setError(null)
      try {
        const newConv = await createConvMutation.mutateAsync({
          ...data,
          study_id: selectedStudyId || data.study_id,
          site_id: selectedSiteId,
        })
        setSelectedConversationId(newConv?.id ?? null)
        setShowCreateModal(false)
      } catch (err: any) {
        const errorMsg =
          err?.response?.data?.detail || err?.message || 'Failed to create conversation'
        setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg))
      }
    },
    [createConvMutation, selectedStudyId, selectedSiteId],
  )

  const handleDeleteConversation = useCallback(
    async (conversationId: string) => {
      if (deleteConvMutation.isPending) return
      setError(null)
      try {
        await deleteConvMutation.mutateAsync(conversationId)
        if (selectedConversationId === conversationId) {
          setSelectedConversationId(null)
        }
      } catch (err: any) {
        const errorMsg =
          err?.response?.data?.detail || err?.message || 'Failed to delete conversation'
        setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg))
      }
    },
    [deleteConvMutation, selectedConversationId],
  )

  const createThreadMutation = useCreateThread()
  const handleCreateThread = useCallback(
    async (data: {
      conversation_id?: string
      title: string
      description?: string
      thread_type: string
      related_patient_id?: string
      related_study_id?: string
      priority: string
      created_by?: string
      participants?: Array<{
        participant_id: string
        participant_name?: string
        participant_email?: string
        role?: string
      }>
    }) => {
      setError(null)
      try {
        const newThread = await createThreadMutation.mutateAsync({
          ...data,
          related_study_id: selectedStudyId || data.related_study_id,
          site_id: selectedSiteId,
        })
        setSelectedThreadId(newThread?.id ?? null)
        setShowCreateThreadModal(false)
      } catch (err: any) {
        const errorMsg =
          err?.response?.data?.detail || err?.message || 'Failed to create thread'
        setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg))
      }
    },
    [createThreadMutation, selectedStudyId, selectedSiteId],
  )

  // Refresh — replaces the manual loadConversations / loadThreads chain.
  // Triggers a refetch on the active list; the detail panes are responsible
  // for their own data so a list refetch is enough.
  const handleRefresh = useCallback(() => {
    if (activeTab === 'conversations') {
      void conversationsQuery.refetch()
    } else {
      void threadsQuery.refetch()
    }
  }, [activeTab, conversationsQuery, threadsQuery])




  // Top-level modes that do not require site context — render directly.
  // Each tab below is lazy-loaded; Suspense fences off the load while keeping
  // the rest of the app responsive.
  if (externalMode === 'dashboard') {
    return (
      <Suspense fallback={<TabFallback />}>
        <Dashboard />
      </Suspense>
    )
  }
  if (externalMode === 'study-setup') {
    return (
      <Suspense fallback={<TabFallback />}>
        <StudySetup apiBase={apiBase} />
      </Suspense>
    )
  }
  if (externalMode === 'tasks') {
    return (
      <Suspense fallback={<TabFallback />}>
        <TasksTab apiBase={apiBase} />
      </Suspense>
    )
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {(!selectedStudyId || !selectedSiteId) ? (
        // Selectors moved to the navbar (see Navbar.tsx). This view just
        // tells the user what to do — the dropdowns are one click away in
        // the top bar.
        <div className="flex-1 flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
          <SiteRequiredPrompt fullPage feature="the inbox" />
        </div>
      ) : (
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">

      {(activeTab === 'conversations' || activeTab === 'threads') && (
        <div className="bg-white border-b border-gray-200 px-6 pt-3 flex items-end justify-between gap-3 flex-shrink-0">
          <div className="flex items-end gap-1">
            {[
              { id: 'conversations', label: 'Conversations' },
              { id: 'threads', label: 'Threads' },
            ].map((t) => {
              const active = activeTab === t.id
              return (
                <button
                  key={t.id}
                  onClick={() => onModeChange?.(t.id)}
                  className={`px-5 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 -mb-px transition-colors ${
                    active
                      ? 'border-dizzaroo-deep-blue text-dizzaroo-deep-blue bg-blue-50'
                      : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {t.label}
                </button>
              )
            })}

            {/* Search — sits right beside the Threads tab. */}
            <div className="relative ml-2 mb-1.5">
              <svg
                className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
              <input
                type="text"
                value={filters.search}
                onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                placeholder={activeTab === 'threads' ? 'Search threads…' : 'Search conversations…'}
                className="pl-8 pr-3 py-1.5 bg-white border border-gray-300 rounded-lg text-xs font-medium text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue hover:bg-slate-50 transition-colors min-w-[200px] max-w-[260px]"
              />
            </div>
          </div>

          {/* Site switcher used to live here — now lives in the navbar so the
              operator can swap sites once and have every gated module follow. */}
        </div>
      )}

      {(activeTab === 'site-profile' || activeTab === 'site-staff-details' || activeTab === 'irb-administrative-info') && (
        <div className="bg-white border-b border-gray-200 px-6 pt-3 flex items-end gap-1 flex-shrink-0">
          {FORMS_NAV_ITEMS.map((t) => {
            const active = activeTab === t.id
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => onModeChange?.(t.id)}
                className={`px-5 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 -mb-px transition-colors ${
                  active
                    ? 'border-dizzaroo-deep-blue text-dizzaroo-deep-blue bg-blue-50'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                }`}
              >
                {t.label}
              </button>
            )
          })}
        </div>
      )}

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 mx-5 mt-3 rounded">
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      {topLevelMode === 'sites' ? (
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden h-full">
          {/*
            All Sites subtabs are lazy-loaded — one Suspense wrapper covers
            the kept-mounted IRB pane plus whichever subtab is currently
            displayed. Sharing a single Suspense means we don't get
            cascading fallback flashes when the user tab-hops.
          */}
          <Suspense fallback={<TabFallback />}>
            {/* Keep IRB mounted while switching Sites subtabs so draft values are not lost */}
            <div
              className={
                activeTab === 'irb-administrative-info'
                  ? 'flex-1 overflow-hidden h-full flex flex-col min-h-0'
                  : 'hidden'
              }
              aria-hidden={activeTab !== 'irb-administrative-info'}
            >
              <IRBAdministrativeInfo />
            </div>
            {activeTab === 'site-status' ? (
              <div className="flex-1 overflow-hidden">
                <SiteControlTower apiBase={apiBase} />
              </div>
            ) : activeTab === 'monitoring' ? (
              <div className="flex-1 overflow-hidden min-h-0 h-full">
                <MonitoringTab />
              </div>
            ) : activeTab === 'documents' ? (
              <div className="flex-1 overflow-hidden h-full">
                <ISFModule apiBase={apiBase} />
              </div>
            ) : activeTab === 'site-profile' ? (
              <div className="flex-1 flex flex-col min-h-0 overflow-hidden h-full">
                <SiteProfileTab apiBase={apiBase} />
              </div>
            ) : activeTab === 'site-staff-details' ? (
              <div className="flex-1 flex flex-col min-h-0 overflow-hidden h-full">
                <SiteStaffDetailsTab />
              </div>
            ) : activeTab === 'irb-administrative-info' ? null : (
              <div className="flex-1 overflow-hidden">
                <SiteControlTower apiBase={apiBase} />
              </div>
            )}
          </Suspense>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden w-full">
          <ResizableSidebar defaultWidth={280} minWidth={200} maxWidth={400}>
            <div
              className="border-r border-slate-200 flex flex-col overflow-hidden h-full w-full"
              style={{
                background:
                  'linear-gradient(180deg, rgba(22,138,173,0.04) 0%, rgba(248,250,252,1) 35%, rgba(248,250,252,1) 100%)',
              }}
            >
            <div
              className="px-4 py-3 border-b border-brand-500/15 flex-shrink-0 flex items-center justify-between"
              style={{
                background:
                  'linear-gradient(135deg, rgba(22,138,173,0.10) 0%, rgba(118,200,147,0.06) 100%)',
              }}
              data-testid="inbox-header"
            >
              <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-brand-500/15 text-brand-700">
                  {activeTab === 'conversations' ? (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  ) : (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M4 6h16M4 12h10M4 18h7" />
                    </svg>
                  )}
                </span>
                <span>
                  {activeTab === 'conversations' ? 'Conversations' : 'Threads'}
                </span>
                <span className="text-brand-700 bg-brand-100 px-1.5 py-0.5 rounded-full text-[10px] font-semibold tabular-nums">
                  {activeTab === 'conversations' ? conversations.length : threads.length}
                </span>
              </h2>
              {activeTab === 'conversations' && (
                <button
                  type="button"
                  onClick={() => setShowCreateModal(true)}
                  disabled={isCreatingConversation || showCreateModal}
                  className="inline-flex items-center justify-center w-7 h-7 text-xs font-medium rounded-lg bg-brand-500 text-white hover:bg-brand-600 shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  title="New Conversation"
                  aria-label="New conversation"
                  data-testid="inbox-new-conversation"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                </button>
              )}
            </div>
          {isLoading && (
              <div className="p-2 text-center text-gray-500 text-sm">Loading...</div>
          )}
            <div className="flex-1 overflow-y-auto min-h-0" data-testid="inbox-list">
            {activeTab === 'conversations' ? (
                conversations.length > 0 ? (
              <ConversationList
                conversations={conversations}
                onSelect={handleSelectConversation}
                onDelete={handleDeleteConversation}
                deletingId={deleteConvMutation.isPending ? deleteConvMutation.variables ?? null : null}
                selectedId={selectedConversation?.id}
                apiBase={apiBase}
              />
            ) : (
                  <div className="p-4 text-center text-gray-500 text-sm">
                    <p>No conversations found</p>
                    <p className="text-xs mt-1">Create a new conversation to get started</p>
                  </div>
                )
              ) : (
                <>
                  <div className="mb-4 px-2">
                    <ThreadCombinationSuggestions apiBase={apiBase} onCombined={() => { void threadsQuery.refetch() }} />
                  </div>
                  {threads.length > 0 ? (
                    <ThreadList
                      threads={threads}
                      onSelect={handleSelectThread}
                      selectedId={selectedThread?.id}
                    />
                  ) : (
                    <div className="p-4 text-center text-gray-500 text-sm">
                      <p>No threads found</p>
                      <p className="text-xs mt-1">Create a new thread to get started</p>
                    </div>
                  )}
                </>
            )}
          </div>
            </div>
          </ResizableSidebar>

          <div className="flex-1 flex flex-col overflow-hidden bg-gray-50 pr-4">
          {activeTab === 'conversations' ? (
            selectedConversation ? (
                <div className="h-full flex flex-col bg-white rounded-l-lg shadow-sm overflow-hidden">
                  <HomeBackBar onBack={handleBackToHome} />
                  <div className="flex-1 min-h-0">
              <ConversationDetail
                conversation={selectedConversation}
                onRefresh={handleRefresh}
                apiBase={apiBase}
                    currentUserId={currentUserId}
              />
                  </div>
                </div>
            ) : (
                <div className="flex-1 overflow-hidden bg-white rounded-l-lg shadow-sm">
                  <WorkspaceHome
                    apiBase={apiBase}
                    onSelectConversation={handleSelectConversation}
                    onModeChange={(m) => onModeChange?.(m)}
                  />
                </div>
            )
          ) : (
            selectedThread ? (
                <div className="h-full flex flex-col bg-white rounded-l-lg shadow-sm overflow-hidden">
                  <HomeBackBar onBack={handleBackToHome} />
                  <div className="flex-1 min-h-0">
              <ThreadDetail
                thread={selectedThread}
                onRefresh={handleRefresh}
                apiBase={apiBase}
                    currentUserId={currentUserId}
                    currentUserName={user?.name || user?.email || currentUserId}
              />
                  </div>
                </div>
            ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-500 p-8 bg-white rounded-l-lg shadow-sm">
                <h2 className="text-2xl font-semibold mb-2">Select a thread</h2>
                <p>Choose a thread from the list to view messages, or create a new one.</p>
              </div>
            )
          )}
        </div>
      </div>
      )}
        </div>
      )}

      {showCreateModal && (
        <CreateConversationModal
          onClose={() => {
            if (!isCreatingConversation) setShowCreateModal(false)
          }}
          onSubmit={handleCreateConversation}
          loading={isCreatingConversation}
          studyName={studies.find(s => s.id === selectedStudyId)?.name}
          siteName={filteredSites.find(s => s.site_id === selectedSiteId)?.name}
        />
      )}

      {showCreateThreadModal && (
        <CreateThreadModal
          onClose={() => setShowCreateThreadModal(false)}
          onSubmit={handleCreateThread}
          loading={isLoading}
          conversations={conversations}
          defaultConversationId={selectedConversation?.id}
        />
      )}
    </div>
  )
}

/**
 * Slim breadcrumb bar shown above an open conversation/thread so the user can
 * return to the WorkspaceHome landing page without a full browser refresh.
 */
const HomeBackBar: React.FC<{ onBack: () => void }> = ({ onBack }) => (
  <div className="flex-shrink-0 px-3 py-2 border-b border-slate-100">
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-1.5 px-2 py-1 -ml-1 rounded-lg text-ui-body-sm font-medium text-brand-700 hover:bg-brand-50 transition focus:outline-none focus:ring-2 focus:ring-brand-500/40"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M15 18l-6-6 6-6" />
      </svg>
      Back to home
    </button>
  </div>
)

export default UnifiedInbox

