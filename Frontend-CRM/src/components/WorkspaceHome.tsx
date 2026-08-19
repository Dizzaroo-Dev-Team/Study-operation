import React, { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { useStudySite } from '../contexts/StudySiteContext'
import SiteRequiredPrompt from './SiteRequiredPrompt'
import { useConversationsList } from '@/lib/queries/useConversations'
import { useTasksList } from '@/lib/queries/useTasks'
import { useMyAssignments } from '@/lib/queries/useAgreements'
import { Conversation, MonitoringTask, Message } from '../types'
import {
  deriveConversationStatus,
  formatAge,
} from '@/features/communications/hooks/useConversationStatus'

interface WorkspaceHomeProps {
  apiBase: string
  onSelectConversation: (id: string) => void
  onModeChange: (mode: string) => void
}

/**
 * Operational landing surface that replaces the old "Select a conversation"
 * placeholder. Shows today's priorities so the user has something to do the
 * moment they pick a study + site, rather than a wall of whitespace.
 */
const WorkspaceHome: React.FC<WorkspaceHomeProps> = ({
  onSelectConversation,
  onModeChange,
}) => {
  const { user } = useAuth()
  const { selectedStudyId, selectedSiteId, studies, filteredSites } = useStudySite()

  const study = selectedStudyId ? studies.find((s) => s.id === selectedStudyId) : undefined
  const site = selectedSiteId ? filteredSites.find((s) => s.site_id === selectedSiteId) : undefined

  const myAssignmentsQuery = useMyAssignments()
  const myAssignments = myAssignmentsQuery.data ?? []

  const conversationsQuery = useConversationsList(
    {
      study_id: selectedStudyId ?? null,
      site_id: selectedSiteId ?? null,
      limit: 100,
    },
    { enabled: Boolean(selectedStudyId && selectedSiteId) },
  )
  const tasksQuery = useTasksList(
    { siteId: selectedSiteId ?? null, limit: 100 },
    { enabled: Boolean(selectedStudyId && selectedSiteId) },
  )

  const conversations: Conversation[] = (conversationsQuery.data ?? []) as Conversation[]
  const tasks: MonitoringTask[] = (tasksQuery.data ?? []) as MonitoringTask[]

  // Per-conversation last-message lookup, used to derive "needs reply".
  // Kept as a single batched query rather than fanning out useConversation()
  // calls so the queryKey shape doesn't collide with ConversationDetail's
  // full-history cache entry for the same id.
  const convIds = useMemo(() => conversations.map((c) => c.id), [conversations])
  const lastMessagesQuery = useQuery<Record<string, Message | undefined>>({
    queryKey: ['workspace-last-messages', selectedStudyId ?? null, selectedSiteId ?? null, convIds],
    queryFn: async () => {
      const lm: Record<string, Message | undefined> = {}
      await Promise.all(
        convIds.map(async (id) => {
          try {
            const r = await api.get(`/conversations/${id}`, { params: { limit: 1 } })
            lm[id] = (r.data?.messages || [])[0]
          } catch {
            /* swallow per-row failures, matches legacy behavior */
          }
        }),
      )
      return lm
    },
    enabled: convIds.length > 0,
    staleTime: 15_000,
  })
  const lastMessages = lastMessagesQuery.data ?? {}

  const loading =
    conversationsQuery.isLoading ||
    tasksQuery.isLoading ||
    (convIds.length > 0 && lastMessagesQuery.isLoading)

  const needsAttention = useMemo(() => {
    return conversations
      .map((c) => ({
        conv: c,
        info: deriveConversationStatus(lastMessages[c.id], c.updated_at, c),
      }))
      .filter((x) => x.info.status === 'needs-reply' || x.info.status === 'stale')
      .sort((a, b) => {
        // needs-reply first, then by age
        if (a.info.status !== b.info.status) {
          return a.info.status === 'needs-reply' ? -1 : 1
        }
        return (b.info.hoursSinceLastMessage || 0) - (a.info.hoursSinceLastMessage || 0)
      })
      .slice(0, 5)
  }, [conversations, lastMessages])

  const overdueTasks = useMemo(() => {
    const now = Date.now()
    return tasks
      .filter((t) => t.status !== 'done' && t.status !== 'cancelled')
      .filter((t) => {
        if (!t.dueDate) return false
        return new Date(t.dueDate).getTime() < now
      })
      .slice(0, 5)
  }, [tasks])

  const upcomingTasks = useMemo(() => {
    const now = Date.now()
    return tasks
      .filter((t) => t.status !== 'done' && t.status !== 'cancelled')
      .filter((t) => {
        if (!t.dueDate) return false
        const due = new Date(t.dueDate).getTime()
        return due >= now && due < now + 7 * 24 * 3600_000
      })
      .slice(0, 5)
  }, [tasks])

  if (!selectedStudyId || !selectedSiteId) {
    return <SiteRequiredPrompt fullPage feature="your workspace" />
  }

  const greeting = (() => {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 18) return 'Good afternoon'
    return 'Good evening'
  })()
  const name = user?.name || user?.email || 'there'

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Hero — soft brand gradient banner so the workspace feels alive. */}
        <header
          className="rounded-2xl p-6 border border-brand-500/15 shadow-card relative overflow-hidden"
          style={{
            background:
              'linear-gradient(135deg, rgba(22,138,173,0.10) 0%, rgba(118,200,147,0.10) 60%, rgba(30,115,190,0.06) 100%)',
          }}
        >
          <div
            aria-hidden="true"
            className="absolute -top-12 -right-12 w-48 h-48 rounded-full"
            style={{ background: 'radial-gradient(circle, rgba(22,138,173,0.18), transparent 70%)' }}
          />
          <div className="flex items-end justify-between gap-4 relative">
            <div>
              <h1 className="text-ui-h1 text-slate-900">
                {greeting}, {name}
              </h1>
              <p className="text-ui-body text-slate-600 mt-1">
                <span className="font-medium text-slate-800">{study?.name || 'No study'}</span>
                <span className="text-slate-400 mx-1.5">·</span>
                <span className="font-medium text-slate-800">{site?.name || 'No site'}</span>
                <span className="text-slate-400 mx-1.5">·</span>
                {loading ? (
                  'loading…'
                ) : (
                  <>
                    <span className="text-danger-600 font-medium">{needsAttention.length}</span>{' '}
                    needing attention,{' '}
                    <span className="text-warning-600 font-medium">{overdueTasks.length}</span>{' '}
                    overdue
                  </>
                )}
              </p>
            </div>
            <button
              onClick={() => onModeChange('tasks')}
              className="px-3 py-1.5 bg-brand-500 hover:bg-brand-600 text-white rounded-lg text-ui-body-sm font-medium transition shadow-sm"
            >
              View all tasks
            </button>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Needs attention — danger tint */}
          <DashCard title="Needs your attention" count={needsAttention.length} accent="danger">
            {needsAttention.length === 0 ? (
              <EmptyMsg>Inbox zero. Nothing requires your reply right now.</EmptyMsg>
            ) : (
              <ul className="divide-y divide-slate-100">
                {needsAttention.map(({ conv, info }) => (
                  <li
                    key={conv.id}
                    onClick={() => onSelectConversation(conv.id)}
                    className="px-3 py-2 cursor-pointer hover:bg-slate-50 rounded transition"
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${info.dotClass}`}
                        aria-hidden="true"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-2">
                          <p className="truncate text-ui-body font-medium text-slate-900">
                            {conv.subject || 'Untitled'}
                          </p>
                          <span className="text-ui-caption text-slate-400 tabular-nums">
                            {formatAge(info.hoursSinceLastMessage)}
                          </span>
                        </div>
                        <p className="text-ui-caption text-slate-500 mt-0.5">{info.label}</p>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </DashCard>

          {/* Overdue tasks — warning tint */}
          <DashCard title="Overdue tasks" count={overdueTasks.length} accent="warning">
            {overdueTasks.length === 0 ? (
              <EmptyMsg>No overdue tasks. Nice.</EmptyMsg>
            ) : (
              <ul className="divide-y divide-slate-100">
                {overdueTasks.map((t) => (
                  <li
                    key={t.id}
                    onClick={() => onModeChange('tasks')}
                    className="px-3 py-2 cursor-pointer hover:bg-slate-50 rounded transition"
                  >
                    <div className="flex items-start gap-2">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-danger-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-2">
                          <p className="truncate text-ui-body font-medium text-slate-900">
                            {t.description || t.title || 'Untitled task'}
                          </p>
                          {t.dueDate && (
                            <span className="text-ui-caption text-danger-600 tabular-nums">
                              {new Date(t.dueDate).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                            </span>
                          )}
                        </div>
                        {t.assignedTo && (
                          <p className="text-ui-caption text-slate-500 mt-0.5">→ {t.assignedTo}</p>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </DashCard>

          {/* Upcoming this week */}
          <DashCard title="Due this week" count={upcomingTasks.length} accent="brand">
            {upcomingTasks.length === 0 ? (
              <EmptyMsg>Nothing scheduled this week.</EmptyMsg>
            ) : (
              <ul className="divide-y divide-slate-100">
                {upcomingTasks.map((t) => (
                  <li
                    key={t.id}
                    onClick={() => onModeChange('tasks')}
                    className="px-3 py-2 cursor-pointer hover:bg-slate-50 rounded transition"
                  >
                    <div className="flex items-start gap-2">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-warning-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-2">
                          <p className="truncate text-ui-body font-medium text-slate-900">
                            {t.description || t.title || 'Untitled task'}
                          </p>
                          {t.dueDate && (
                            <span className="text-ui-caption text-warning-600 tabular-nums">
                              {new Date(t.dueDate).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                            </span>
                          )}
                        </div>
                        {t.assignedTo && (
                          <p className="text-ui-caption text-slate-500 mt-0.5">→ {t.assignedTo}</p>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </DashCard>

          {/* My CTA Reviews & Signatures */}
          <DashCard title="My CTA Reviews & Signatures" count={myAssignments.length} accent="brand">
            {myAssignments.length === 0 ? (
              <EmptyMsg>No pending reviews or signatures.</EmptyMsg>
            ) : (
              <ul className="divide-y divide-slate-100">
                {myAssignments.map((a) => (
                  <li key={a.agreement_id}>
                    <button
                      type="button"
                      onClick={() => {
                        try {
                          if (a.study_id) {
                            localStorage.setItem('crm.lastStudyId', a.study_id)
                            localStorage.setItem('dizzaroo_selected_study', a.study_id)
                          }
                          if (a.site_id) {
                            localStorage.setItem('dizzaroo_selected_site', a.site_id)
                          }
                          // Strong intent consumed once by StudySiteContext —
                          // selects study + site post-load and surfaces an
                          // access-denied banner if the user can't see them.
                          localStorage.setItem(
                            'crm.openAgreementIntent',
                            JSON.stringify({
                              study_id: a.study_id ?? null,
                              site_id: a.site_id ?? null,
                              agreement_id: a.agreement_id,
                            }),
                          )
                          localStorage.setItem('crm.lastModule', 'study-setup')
                          localStorage.setItem('crm.lastTab', 'study-setup:agreements')
                          // One-shot intent: survives auth bootstrap's
                          // "force dashboard" effect; consumed once by App.tsx.
                          localStorage.setItem('crm.landOn', 'study-setup')
                          // Avoid the fresh-tab dashboard-force path too.
                          sessionStorage.setItem('crm.sessionOpened', '1')
                        } catch {
                          /* ignore storage errors */
                        }
                        window.location.assign('/')
                      }}
                      className="w-full text-left px-3 py-2 flex items-start gap-2 hover:bg-slate-50 rounded transition focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-2">
                          <p className="truncate text-ui-body font-medium text-slate-900">
                            {a.study_name || 'Untitled CTA'}
                          </p>
                          <span
                            className={`shrink-0 px-2 py-0.5 rounded text-xs font-semibold ${
                              a.role === 'reviewer'
                                ? 'bg-purple-100 text-purple-700'
                                : 'bg-blue-100 text-blue-700'
                            }`}
                          >
                            {a.role === 'reviewer' ? 'Reviewer' : 'Sponsor Head'}
                          </span>
                        </div>
                        {a.site_name && (
                          <p className="text-ui-caption text-slate-500 mt-0.5">{a.site_name}</p>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </DashCard>

          {/* Quick actions — accent (green) tint */}
          <DashCard title="Quick actions" accent="accent">
            <div className="grid grid-cols-1 gap-2">
              <QuickAction
                label="Open ⌘K palette"
                hint="Search anything"
                onClick={() => {
                  const evt = new KeyboardEvent('keydown', { key: 'k', metaKey: true })
                  document.dispatchEvent(evt)
                }}
              />
              <QuickAction
                label="Go to Conversations"
                hint="All inbound + outbound"
                onClick={() => onModeChange('conversations')}
              />
              <QuickAction
                label="Go to Tasks"
                hint="See every open task"
                onClick={() => onModeChange('tasks')}
              />
              <QuickAction
                label="Site Status board"
                hint="Trial overview"
                onClick={() => onModeChange('site-status')}
              />
            </div>
          </DashCard>
        </div>
      </div>
    </div>
  )
}

type DashAccent = 'brand' | 'accent' | 'warning' | 'danger' | undefined

const DASH_ACCENT_STYLE: Record<Exclude<DashAccent, undefined>, { border: string; headerBg: string; titleClass: string; countClass: string }> = {
  brand:   { border: 'border-brand-500/20',   headerBg: 'bg-brand-50/60',   titleClass: 'text-brand-700',   countClass: 'bg-brand-100 text-brand-700' },
  accent:  { border: 'border-accent-500/20',  headerBg: 'bg-accent-50/60',  titleClass: 'text-accent-600',  countClass: 'bg-accent-50 text-accent-600' },
  warning: { border: 'border-warning-500/25', headerBg: 'bg-warning-50/60', titleClass: 'text-warning-600', countClass: 'bg-warning-50 text-warning-600' },
  danger:  { border: 'border-danger-500/25',  headerBg: 'bg-danger-50/60',  titleClass: 'text-danger-600',  countClass: 'bg-danger-50 text-danger-600' },
}

const DashCard: React.FC<{
  title: string
  count?: number
  accent?: DashAccent
  children: React.ReactNode
}> = ({ title, count, accent, children }) => {
  const style = accent ? DASH_ACCENT_STYLE[accent] : undefined
  return (
    <section
      className={`bg-white rounded-xl shadow-card crm-card-hover border ${
        style ? style.border : 'border-slate-200'
      }`}
    >
      <header
        className={`px-4 py-3 border-b border-slate-100 flex items-center justify-between rounded-t-xl ${
          style ? style.headerBg : ''
        }`}
      >
        <h2 className={`text-ui-h2 ${style ? style.titleClass : 'text-slate-800'}`}>{title}</h2>
        {typeof count === 'number' && count > 0 && (
          <span
            className={`text-ui-caption tabular-nums px-1.5 py-0.5 rounded-full font-semibold ${
              style ? style.countClass : 'text-slate-500'
            }`}
          >
            {count}
          </span>
        )}
      </header>
      <div className="p-2">{children}</div>
    </section>
  )
}

const EmptyMsg: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="px-3 py-6 text-center text-ui-body-sm text-slate-500">{children}</p>
)

const QuickAction: React.FC<{ label: string; hint: string; onClick: () => void }> = ({
  label,
  hint,
  onClick,
}) => (
  <button
    onClick={onClick}
    className="px-3 py-2 text-left rounded hover:bg-slate-50 transition flex items-center justify-between gap-2"
  >
    <div>
      <p className="text-ui-body text-slate-900">{label}</p>
      <p className="text-ui-caption text-slate-500">{hint}</p>
    </div>
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-slate-300"
      aria-hidden="true"
    >
      <path d="M9 18l6-6-6-6" />
    </svg>
  </button>
)

export default WorkspaceHome
