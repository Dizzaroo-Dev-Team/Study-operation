import React, { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Conversation, Message, MonitoringTask, Attachment } from '@/types'
import {
  deriveConversationStatus,
  formatAge,
} from '@/features/communications/hooks/useConversationStatus'

export interface ConversationActions {
  onFollowUp: () => void
  onCreateTask: () => void
  onSnooze: () => void | Promise<void>
  onResolve: () => void | Promise<void>
  onEscalate: () => void | Promise<void>
}

interface ConversationRightSidebarProps {
  conversation: Conversation
  messages: Message[]
  apiBase: string
  conversationId: string
  isOpen: boolean
  onToggle: () => void
  /** Messages explicitly pinned as decisions (server-backed is_decision flag). */
  decisions?: Message[]
  onUnpinDecision?: (message: Message) => void
  onJumpToMessage?: (messageId: string) => void
  /** Real, one-click actions wired by the parent — replaces the old read-only text. */
  actions?: ConversationActions
}

/**
 * Right-rail intelligence panel. Replaces the previous tabbed layout
 * (Summary / Changes / Tone) with stacked, contextual cards that mirror the
 * Linear / Figma / Front design-system convention. Each card is
 * independently collapsible and loads its own data — no global tab state.
 */
const ConversationRightSidebar: React.FC<ConversationRightSidebarProps> = ({
  conversation,
  messages,
  apiBase,
  conversationId,
  isOpen,
  onToggle,
  decisions = [],
  onUnpinDecision,
  onJumpToMessage,
  actions,
}) => {
  if (!isOpen) {
    // Floating reopen handle. Pinned to the right edge of the viewport at a
    // high z-index so it stays visible above the Ask-Me-Anything dock and any
    // other fixed UI. Larger surface + visible label so users actually find it.
    return (
      <button
        onClick={onToggle}
        className="fixed right-0 top-24 z-[60] flex items-center gap-1.5 pl-2 pr-2.5 py-2 rounded-l-lg shadow-popover hover:shadow-card-hover transition text-white text-ui-body-sm font-semibold"
        style={{
          background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)',
        }}
        title="Open context panel"
        aria-label="Open context panel"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        <span>Context</span>
      </button>
    )
  }

  const statusInfo = deriveConversationStatus(
    messages[messages.length - 1],
    conversation.updated_at,
    conversation,
  )
  const participantEmails =
    conversation.participant_emails && conversation.participant_emails.length > 0
      ? conversation.participant_emails
      : conversation.participant_email
        ? [conversation.participant_email]
        : []

  return (
    <aside
      className="w-[340px] border-l border-slate-200 flex flex-col h-full"
      style={{
        background:
          'linear-gradient(180deg, rgba(22,138,173,0.04) 0%, rgba(248,250,252,1) 35%, rgba(248,250,252,1) 100%)',
      }}
    >
      <div
        className="px-4 py-3 border-b border-brand-500/15 flex items-center justify-between"
        style={{
          background:
            'linear-gradient(135deg, rgba(22,138,173,0.10) 0%, rgba(118,200,147,0.06) 100%)',
        }}
      >
        <h3 className="text-ui-h2 text-slate-800">Context</h3>
        <button
          onClick={onToggle}
          className="text-slate-400 hover:text-slate-600 p-1 rounded hover:bg-slate-100 transition"
          title="Close panel"
          aria-label="Close panel"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        <SuggestedActionsCard
          messages={messages}
          statusLabel={statusInfo.label}
          nextBestAction={conversation.ai_next_best_action}
          actions={actions}
        />

        <Card title="Status">
          <div className="space-y-1.5">
            <Row label="Status">
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${statusInfo.pillClass}`}>
                {statusInfo.label}
              </span>
            </Row>
            <Row label="Last activity">
              <span className="text-ui-body-sm text-slate-700 tabular-nums">
                {formatAge(statusInfo.hoursSinceLastMessage)}
              </span>
            </Row>
            <Row label="Messages">
              <span className="text-ui-body-sm text-slate-700 tabular-nums">{messages.length}</span>
            </Row>
            {conversation.tracker_code && (
              <Row label="Tracker">
                <span className="font-mono text-[11px] text-slate-700">{conversation.tracker_code}</span>
              </Row>
            )}
          </div>
          {(conversation.is_confidential === 'true' || conversation.is_restricted === 'true') && (
            <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-slate-100">
              {conversation.is_confidential === 'true' && (
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-danger-50 text-danger-600 border border-danger-500/30">
                  Confidential
                </span>
              )}
              {conversation.is_restricted === 'true' && (
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-warning-50 text-warning-600 border border-warning-500/30">
                  Restricted
                </span>
              )}
            </div>
          )}
          <SlaIndicator
            hoursSinceLastMessage={statusInfo.hoursSinceLastMessage}
            statusLabel={statusInfo.label}
            dueAt={conversation.due_at}
            onFollowUp={actions?.onFollowUp}
          />
        </Card>

        <LinkageCard conversation={conversation} />

        <ParticipantsCard emails={participantEmails} phone={conversation.participant_phone} />

        <LinkedTasksCard conversationId={conversationId} apiBase={apiBase} />

        <RelatedDocumentsCard conversationId={conversationId} apiBase={apiBase} />

        <DecisionsCard
          decisions={decisions}
          onUnpin={onUnpinDecision}
          onJump={onJumpToMessage}
        />

        <ActivityTimelineCard messages={messages} />
      </div>
    </aside>
  )
}

// ─── Generic card primitives ──────────────────────────────────────────────────

interface CardProps {
  title: string
  count?: number
  defaultCollapsed?: boolean
  action?: React.ReactNode
  children: React.ReactNode
}

const Card: React.FC<CardProps> = ({ title, count, defaultCollapsed = false, action, children }) => {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  return (
    <section className="bg-white border border-slate-200 rounded-lg shadow-card">
      <header
        className="flex items-center justify-between px-3 py-2 cursor-pointer select-none"
        onClick={() => setCollapsed((c) => !c)}
      >
        <div className="flex items-center gap-1.5">
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`text-slate-400 transition-transform ${collapsed ? '' : 'rotate-90'}`}
            aria-hidden="true"
          >
            <path d="M9 18l6-6-6-6" />
          </svg>
          <h4 className="text-ui-h2 text-slate-700">{title}</h4>
          {typeof count === 'number' && (
            <span className="text-ui-caption text-slate-400 tabular-nums">{count}</span>
          )}
        </div>
        {action && <div onClick={(e) => e.stopPropagation()}>{action}</div>}
      </header>
      {!collapsed && <div className="px-3 pb-3 pt-1">{children}</div>}
    </section>
  )
}

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center justify-between gap-2">
    <span className="text-ui-body-sm text-slate-500">{label}</span>
    {children}
  </div>
)

// ─── Cards ────────────────────────────────────────────────────────────────────

interface SuggestedAction {
  label: string
  onClick?: () => void | Promise<void>
}

const SuggestedActionsCard: React.FC<{
  messages: Message[]
  statusLabel: string
  nextBestAction?: string
  actions?: ConversationActions
}> = ({ messages, statusLabel, nextBestAction, actions }) => {
  const suggestions = computeSuggestedActions(messages, statusLabel, actions)
  // Render nothing only when there's neither an AI recommendation nor any action.
  if (!nextBestAction && suggestions.length === 0) return null
  return (
    <section
      className="rounded-lg border border-brand-500/30 shadow-card overflow-hidden"
      style={{
        background:
          'linear-gradient(135deg, rgba(22,138,173,0.10) 0%, rgba(118,200,147,0.06) 100%)',
      }}
    >
      <header className="px-3 py-2 flex items-center justify-between border-b border-brand-500/20">
        <div className="flex items-center gap-1.5">
          <span className="inline-flex items-center justify-center w-4 h-4 rounded bg-brand-500 text-white">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
            </svg>
          </span>
          <h4 className="text-ui-h2 text-brand-700">Suggested actions</h4>
          {suggestions.length > 0 && (
            <span className="text-ui-caption text-brand-700 bg-brand-100 px-1.5 py-0.5 rounded-full tabular-nums font-semibold">
              {suggestions.length}
            </span>
          )}
        </div>
      </header>
      {/* AI's free-text recommendation, when the backend classified one. */}
      {nextBestAction && (
        <p className="px-3 pt-2 text-ui-body-sm text-slate-700 italic">“{nextBestAction}”</p>
      )}
      <ul className="px-2 py-2 space-y-1">
        {suggestions.map((s, idx) => (
          <li key={idx}>
            <button
              type="button"
              onClick={s.onClick}
              disabled={!s.onClick}
              className="w-full text-left text-ui-body-sm text-slate-800 px-2 py-1.5 rounded bg-white/70 hover:bg-white border border-brand-500/15 flex items-center gap-2 transition disabled:opacity-60 disabled:cursor-default"
            >
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0" />
              <span className="flex-1">{s.label}</span>
              {s.onClick && (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-brand-500 flex-shrink-0" aria-hidden="true">
                  <path d="M9 18l6-6-6-6" />
                </svg>
              )}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * Build a clickable action list from the conversation state. Each action is
 * wired to a real handler supplied by the parent (follow-up draft, task,
 * snooze, resolve, escalate) — no more dead text.
 */
const computeSuggestedActions = (
  messages: Message[],
  statusLabel: string,
  actions?: ConversationActions,
): SuggestedAction[] => {
  const out: SuggestedAction[] = []
  const last = messages[messages.length - 1]
  const body = (last?.body || '').toLowerCase()

  if (/(task|todo|action item|please|kindly)\b/.test(body) && actions?.onCreateTask) {
    out.push({ label: 'Create a task from the latest message', onClick: actions.onCreateTask })
  }
  if (statusLabel === 'Awaiting reply' && actions?.onFollowUp) {
    out.push({ label: 'Draft a follow-up nudge', onClick: actions.onFollowUp })
  }
  if (statusLabel === 'No update 7d+') {
    if (actions?.onFollowUp) out.push({ label: 'Draft a follow-up', onClick: actions.onFollowUp })
    if (actions?.onResolve) out.push({ label: 'Mark conversation resolved', onClick: actions.onResolve })
    if (actions?.onSnooze) out.push({ label: 'Snooze until tomorrow', onClick: actions.onSnooze })
  }
  // Always offer escalate as a fallback when nothing else surfaced.
  if (out.length === 0 && actions?.onEscalate) {
    out.push({ label: 'Escalate (mark urgent)', onClick: actions.onEscalate })
  }
  return out
}

const ParticipantsCard: React.FC<{ emails: string[]; phone?: string }> = ({ emails, phone }) => {
  if (emails.length === 0 && !phone) return null
  return (
    <Card title="Participants" count={emails.length + (phone ? 1 : 0)}>
      <ul className="space-y-1">
        {phone && (
          <li className="text-ui-body-sm text-slate-700 truncate" title={phone}>
            <span className="text-slate-400">phone </span>
            {phone}
          </li>
        )}
        {emails.map((e) => (
          <li key={e} className="text-ui-body-sm text-slate-700 truncate" title={e}>
            <span className="text-slate-400">email </span>
            {e}
          </li>
        ))}
      </ul>
    </Card>
  )
}

const LinkedTasksCard: React.FC<{ conversationId: string; apiBase: string }> = ({
  conversationId,
  apiBase,
}) => {
  const [tasks, setTasks] = useState<MonitoringTask[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .get(`${apiBase}/tasks`, { params: { conversationId, limit: 25 } })
      .then((res) => {
        if (!cancelled) setTasks(res.data || [])
      })
      .catch(() => {
        if (!cancelled) setTasks([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [conversationId, apiBase])

  return (
    <Card title="Linked tasks" count={tasks.length} defaultCollapsed={tasks.length === 0}>
      {loading ? (
        <p className="text-ui-caption text-slate-500">Loading…</p>
      ) : tasks.length === 0 ? (
        <p className="text-ui-caption text-slate-500 italic">No tasks linked yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {tasks.map((t) => (
            <li key={t.id} className="text-ui-body-sm text-slate-700 flex items-start gap-2">
              <input
                type="checkbox"
                readOnly
                checked={t.status === 'done'}
                className="mt-1 w-3 h-3 accent-brand-500"
                aria-label="Task status"
              />
              <span className={t.status === 'done' ? 'line-through text-slate-400' : ''}>
                {t.description || t.title || 'Untitled task'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

const RelatedDocumentsCard: React.FC<{ conversationId: string; apiBase: string }> = ({
  conversationId,
  apiBase,
}) => {
  const [docs, setDocs] = useState<Attachment[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .get(`${apiBase}/conversations/${conversationId}/attachments`)
      .then((res) => {
        if (!cancelled) setDocs(res.data || [])
      })
      .catch(() => {
        if (!cancelled) setDocs([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
  }, [conversationId, apiBase])

  return (
    <Card title="Related documents" count={docs.length} defaultCollapsed={docs.length === 0}>
      {loading ? (
        <p className="text-ui-caption text-slate-500">Loading…</p>
      ) : docs.length === 0 ? (
        <p className="text-ui-caption text-slate-500 italic">No attachments.</p>
      ) : (
        <ul className="space-y-1">
          {docs.map((d: any) => (
            <li
              key={d.id}
              className="text-ui-body-sm text-slate-700 flex items-center gap-2 truncate"
              title={d.file_name || d.file_path}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400 flex-shrink-0">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
              </svg>
              <span className="truncate">{d.file_name || d.file_path?.split(/[\\/]/).pop() || 'file'}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/**
 * Decisions of record — messages a user has explicitly pinned (server-backed
 * `is_decision` flag). Replaces the old regex heuristic, which guessed from
 * words like "agreed"/"approved" and produced false positives.
 */
const DecisionsCard: React.FC<{
  decisions: Message[]
  onUnpin?: (message: Message) => void
  onJump?: (messageId: string) => void
}> = ({ decisions, onUnpin, onJump }) => {
  const sorted = [...decisions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )
  return (
    <Card title="Decisions" count={sorted.length} defaultCollapsed={sorted.length === 0}>
      {sorted.length === 0 ? (
        <p className="text-ui-caption text-slate-500 italic">
          None yet. Pin any message as a decision with the 📌 button to record it here.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {sorted.map((m) => (
            <li
              key={m.id}
              className="text-ui-body-sm text-slate-700 bg-accent-50 border border-accent-500/30 rounded p-2"
            >
              <button
                type="button"
                onClick={() => onJump?.(m.id)}
                className="text-left w-full"
                title="Jump to this message"
              >
                <p className="line-clamp-2">{m.body}</p>
                <p className="text-ui-caption text-slate-500 mt-1">
                  {new Date(m.created_at).toLocaleString([], {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </button>
              {onUnpin && (
                <div className="mt-1 flex justify-end">
                  <button
                    type="button"
                    onClick={() => onUnpin(m)}
                    className="text-ui-caption text-slate-500 hover:text-danger-600 transition"
                    title="Unpin this decision"
                  >
                    Unpin
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/**
 * SLA / response-time indicator. Surfaces an overdue treatment when the
 * conversation is awaiting our reply and has gone quiet, with a one-click
 * follow-up. Uses the same `hoursSinceLastMessage` the status pill derives.
 */
const SlaIndicator: React.FC<{
  hoursSinceLastMessage: number | null
  statusLabel: string
  dueAt?: string | null
  onFollowUp?: () => void
}> = ({ hoursSinceLastMessage, statusLabel, dueAt, onFollowUp }) => {
  const hours = hoursSinceLastMessage ?? 0
  const dueOverdue = !!dueAt && new Date(dueAt).getTime() < Date.now()
  const staleAwaiting =
    (statusLabel === 'Awaiting reply' || statusLabel === 'No update 7d+') &&
    hours >= 48
  if (!dueOverdue && !staleAwaiting) return null
  return (
    <div className="mt-2 pt-2 border-t border-slate-100">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-danger-500" aria-hidden="true" />
        <span className="text-ui-caption font-semibold text-danger-600">
          {dueOverdue ? 'Past due' : 'Awaiting reply — going stale'}
        </span>
      </div>
      <p className="text-ui-caption text-slate-500 mb-2">
        {dueOverdue
          ? `Due ${new Date(dueAt as string).toLocaleDateString()}.`
          : `No reply in ${formatAge(hours)}.`}
      </p>
      {onFollowUp && (
        <button
          type="button"
          onClick={onFollowUp}
          className="w-full px-2 py-1 text-ui-caption font-semibold rounded bg-danger-50 text-danger-600 border border-danger-500/30 hover:bg-danger-100 transition"
        >
          Draft a follow-up
        </button>
      )}
    </div>
  )
}

/**
 * Cross-links the conversation to the Study / Site / tracker it belongs to —
 * the linkage that makes this a CRM record, not just an inbox thread.
 */
const LinkageCard: React.FC<{ conversation: Conversation }> = ({ conversation }) => {
  const hasLinkage =
    !!conversation.study_id || !!conversation.site_id || !!conversation.tracker_code
  if (!hasLinkage) return null
  return (
    <Card title="Linked to">
      <div className="space-y-1.5">
        {conversation.study_id && (
          <Row label="Study">
            <span className="text-ui-body-sm text-slate-700 truncate" title={conversation.study_id}>
              {conversation.study_id}
            </span>
          </Row>
        )}
        {conversation.site_id && (
          <Row label="Site">
            <span className="font-mono text-[11px] text-slate-700 truncate" title={conversation.site_id}>
              {conversation.site_id}
            </span>
          </Row>
        )}
        {conversation.tracker_code && (
          <Row label="Tracker">
            <span className="font-mono text-[11px] text-slate-700">{conversation.tracker_code}</span>
          </Row>
        )}
      </div>
    </Card>
  )
}

const ActivityTimelineCard: React.FC<{ messages: Message[] }> = ({ messages }) => {
  const recent = [...messages]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 6)
  return (
    <Card title="Activity" count={messages.length}>
      {recent.length === 0 ? (
        <p className="text-ui-caption text-slate-500 italic">No activity yet.</p>
      ) : (
        <ol className="space-y-2 border-l-2 border-slate-200 pl-3 ml-1">
          {recent.map((m) => {
            const direction = String(m.direction || '').toLowerCase()
            return (
              <li key={m.id} className="relative">
                <span
                  className={`absolute -left-[14px] top-1.5 w-2 h-2 rounded-full ring-2 ring-white ${
                    direction === 'inbound' ? 'bg-warning-500' : 'bg-brand-500'
                  }`}
                  aria-hidden="true"
                />
                <p className="text-ui-body-sm text-slate-700 line-clamp-2">{m.body}</p>
                <p className="text-ui-caption text-slate-400 mt-0.5">
                  {direction === 'inbound' ? 'Inbound' : 'Outbound'} ·{' '}
                  {new Date(m.created_at).toLocaleString([], {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </li>
            )
          })}
        </ol>
      )}
    </Card>
  )
}

export default ConversationRightSidebar
