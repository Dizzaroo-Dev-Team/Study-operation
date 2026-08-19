import React, { useMemo, useState } from 'react'
import { Message } from '@/types'

/**
 * NoticeBoardView — replaces the generic chat MessageList when the
 * conversation is the per-(study, site) Public Notice Board.
 *
 * Why a custom view: the notice board is an activity feed, not a chat.
 * Each item carries an `event_type` (site_created, agreement_status_changed,
 * monitoring_visit_scheduled, workflow_*_completed, ...) emitted by the
 * backend hooks in `app/utils/system_notices.py`. Rendering those as plain
 * chat bubbles loses the structure. This component groups events by day,
 * colour-codes them by category, and lets the user filter and search.
 *
 * Pure presentational — takes the same `messages` array the chat view
 * uses, reads `event_type` (top-level or from `metadata`), and renders.
 */

type Category = 'site' | 'agreement' | 'monitoring' | 'workflow' | 'conversation' | 'task' | 'feasibility' | 'other'

interface EventStyle {
  category: Category
  /** Single-word label that appears at the top-left of every card */
  label: string
  /** Inline emoji used as the card's avatar circle */
  icon: string
  /** Tailwind classes for the left border + icon background tint */
  accent: string
  /** Tailwind classes for the colored label chip */
  chip: string
}

// Drives both the rendered card style and the filter chip palette.
// Keep in sync with the event_type strings the backend hooks emit
// (`app/utils/system_notices.py` + the per-domain call sites).
const EVENT_STYLE: Record<string, EventStyle> = {
  site_created:                    { category: 'site',          label: 'New Site',           icon: '🏥', accent: 'border-l-blue-500 bg-blue-50 text-blue-900',                 chip: 'bg-blue-100 text-blue-800' },
  site_status_changed:             { category: 'site',          label: 'Status Change',      icon: '📊', accent: 'border-l-indigo-500 bg-indigo-50 text-indigo-900',           chip: 'bg-indigo-100 text-indigo-800' },
  agreement_created:               { category: 'agreement',     label: 'Agreement',          icon: '📄', accent: 'border-l-purple-500 bg-purple-50 text-purple-900',           chip: 'bg-purple-100 text-purple-800' },
  agreement_status_changed:        { category: 'agreement',     label: 'Agreement Status',   icon: '📑', accent: 'border-l-purple-500 bg-purple-50 text-purple-900',           chip: 'bg-purple-100 text-purple-800' },
  status_update:                   { category: 'agreement',     label: 'CDA Update',         icon: '✍️', accent: 'border-l-amber-500 bg-amber-50 text-amber-900',              chip: 'bg-amber-100 text-amber-800' },
  conversation_created:            { category: 'conversation',  label: 'New Conversation',   icon: '💬', accent: 'border-l-sky-500 bg-sky-50 text-sky-900',                    chip: 'bg-sky-100 text-sky-800' },
  task_created:                    { category: 'task',          label: 'Task',               icon: '✅', accent: 'border-l-emerald-500 bg-emerald-50 text-emerald-900',       chip: 'bg-emerald-100 text-emerald-800' },
  monitoring_visit_created:        { category: 'monitoring',    label: 'Visit Scheduled',    icon: '📅', accent: 'border-l-rose-500 bg-rose-50 text-rose-900',                 chip: 'bg-rose-100 text-rose-800' },
  monitoring_visit_closed:         { category: 'monitoring',    label: 'Visit Closed',       icon: '🔒', accent: 'border-l-slate-500 bg-slate-50 text-slate-900',              chip: 'bg-slate-100 text-slate-800' },
  monitoring_visit_rescheduled:    { category: 'monitoring',    label: 'Rescheduled',        icon: '🔄', accent: 'border-l-orange-500 bg-orange-50 text-orange-900',           chip: 'bg-orange-100 text-orange-800' },
  monitoring_finding_created:      { category: 'monitoring',    label: 'Finding',            icon: '⚠️', accent: 'border-l-red-500 bg-red-50 text-red-900',                    chip: 'bg-red-100 text-red-800' },
  monitoring_visit_report_approved:{ category: 'monitoring',    label: 'Report Approved',    icon: '✓',  accent: 'border-l-green-500 bg-green-50 text-green-900',              chip: 'bg-green-100 text-green-800' },
  monitoring_visit_report_rejected:{ category: 'monitoring',    label: 'Report Rejected',    icon: '✗',  accent: 'border-l-red-500 bg-red-50 text-red-900',                    chip: 'bg-red-100 text-red-800' },
  feasibility_request_sent:        { category: 'feasibility',   label: 'Feasibility Sent',   icon: '📧', accent: 'border-l-cyan-500 bg-cyan-50 text-cyan-900',                 chip: 'bg-cyan-100 text-cyan-800' },
  feasibility_submitted:           { category: 'feasibility',   label: 'Feasibility Done',   icon: '📨', accent: 'border-l-teal-500 bg-teal-50 text-teal-900',                 chip: 'bg-teal-100 text-teal-800' },
  workflow_site_identification_completed: { category: 'workflow', label: 'Workflow · Step 1', icon: '🎯', accent: 'border-l-violet-500 bg-violet-50 text-violet-900',        chip: 'bg-violet-100 text-violet-800' },
  workflow_cda_execution_completed:       { category: 'workflow', label: 'Workflow · Step 2', icon: '🎯', accent: 'border-l-violet-500 bg-violet-50 text-violet-900',        chip: 'bg-violet-100 text-violet-800' },
  workflow_feasibility_completed:         { category: 'workflow', label: 'Workflow · Step 3', icon: '🎯', accent: 'border-l-violet-500 bg-violet-50 text-violet-900',        chip: 'bg-violet-100 text-violet-800' },
  workflow_site_selection_completed:      { category: 'workflow', label: 'Workflow · Step 4', icon: '🎯', accent: 'border-l-violet-500 bg-violet-50 text-violet-900',        chip: 'bg-violet-100 text-violet-800' },
  workflow_step_completed:                { category: 'workflow', label: 'Workflow Step',     icon: '🎯', accent: 'border-l-violet-500 bg-violet-50 text-violet-900',        chip: 'bg-violet-100 text-violet-800' },
}

const DEFAULT_STYLE: EventStyle = {
  category: 'other',
  label: 'System Update',
  icon: '📋',
  accent: 'border-l-slate-400 bg-slate-50 text-slate-800',
  chip: 'bg-slate-100 text-slate-700',
}

// Filter chip definitions — categories the user can quickly narrow to.
const FILTER_CHIPS: { id: 'all' | Category; label: string; dot: string }[] = [
  { id: 'all',          label: 'All',           dot: 'bg-slate-400' },
  { id: 'site',         label: 'Sites',         dot: 'bg-blue-500' },
  { id: 'agreement',    label: 'Agreements',    dot: 'bg-purple-500' },
  { id: 'monitoring',   label: 'Monitoring',    dot: 'bg-rose-500' },
  { id: 'workflow',     label: 'Workflow',      dot: 'bg-violet-500' },
  { id: 'conversation', label: 'Conversations', dot: 'bg-sky-500' },
  { id: 'task',         label: 'Tasks',         dot: 'bg-emerald-500' },
  { id: 'feasibility',  label: 'Feasibility',   dot: 'bg-cyan-500' },
  { id: 'other',        label: 'Other',         dot: 'bg-slate-400' },
]

// "5m ago", "2h ago", "Yesterday at 14:32", or full date for older.
function relativeTime(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const diffSec = Math.round((Date.now() - t) / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)}h ago`
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// "Today", "Yesterday", or a localised date — used for the day-section headers.
function dayLabel(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfMessage = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const dayDiff = Math.round((startOfToday - startOfMessage) / 86400000)
  if (dayDiff === 0) return 'Today'
  if (dayDiff === 1) return 'Yesterday'
  if (dayDiff < 7) {
    return d.toLocaleDateString(undefined, { weekday: 'long' })
  }
  return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

interface NoticeBoardViewProps {
  messages: Message[]
}

const NoticeBoardView: React.FC<NoticeBoardViewProps> = ({ messages }) => {
  const [filter, setFilter] = useState<'all' | Category>('all')
  const [search, setSearch] = useState('')

  // Normalise every message into a (style, displayable event) once so the
  // render path stays cheap. event_type can live in two places depending on
  // when the backend was deployed — top-level OR inside metadata — read
  // both to stay robust against older docs.
  const items = useMemo(() => {
    return messages.map((m) => {
      const event_type =
        m.event_type ||
        (m.metadata && (m.metadata.event_type as string)) ||
        ''
      const style = EVENT_STYLE[event_type] || DEFAULT_STYLE
      return { msg: m, event_type, style }
    })
  }, [messages])

  // Visible-after-filter list. Newest first — readers want recent activity
  // at the top, opposite of the chat view's chronological order.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return items
      .filter(({ style }) => filter === 'all' || style.category === filter)
      .filter(({ msg, style, event_type }) => {
        if (!q) return true
        return (
          (msg.body || '').toLowerCase().includes(q) ||
          style.label.toLowerCase().includes(q) ||
          event_type.toLowerCase().includes(q)
        )
      })
      .sort((a, b) => new Date(b.msg.created_at).getTime() - new Date(a.msg.created_at).getTime())
  }, [items, filter, search])

  // Counts per category for the filter-chip badges.
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items.length }
    for (const { style } of items) {
      c[style.category] = (c[style.category] || 0) + 1
    }
    return c
  }, [items])

  // Group the filtered list by day, preserving the newest-first order.
  const grouped = useMemo(() => {
    const acc: { day: string; items: typeof filtered }[] = []
    let currentDay = ''
    for (const it of filtered) {
      const d = dayLabel(it.msg.created_at)
      if (d !== currentDay) {
        acc.push({ day: d, items: [] })
        currentDay = d
      }
      acc[acc.length - 1].items.push(it)
    }
    return acc
  }, [filtered])

  return (
    <div className="w-full max-w-5xl mx-auto">
      {/* Hero — gives the board a real identity, not just "another conversation". */}
      <div
        className="relative overflow-hidden rounded-2xl border border-slate-200 shadow-sm mb-5"
        style={{
          background: 'linear-gradient(135deg, #168AAD 0%, #1E73BE 60%, #76C893 100%)',
        }}
      >
        <div className="absolute inset-0 opacity-10" aria-hidden="true">
          {/* Faint repeating dot pattern for the corkboard vibe. */}
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.6) 1px, transparent 1px)',
              backgroundSize: '14px 14px',
            }}
          />
        </div>
        <div className="relative px-6 py-5 flex items-center gap-4">
          <div className="h-12 w-12 rounded-full bg-white/15 backdrop-blur flex items-center justify-center text-2xl ring-1 ring-white/30">
            📢
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-white text-lg font-bold tracking-tight">Public Notice Board</h2>
            <p className="text-white/80 text-xs">
              Auto-curated activity feed for this study + site. New events appear here in real time —
              site changes, agreements, monitoring visits, workflow milestones, and more.
            </p>
          </div>
          <div className="text-right hidden sm:block">
            <div className="text-3xl font-bold text-white tabular-nums">{items.length}</div>
            <div className="text-[10px] uppercase tracking-wide text-white/70">events</div>
          </div>
        </div>
      </div>

      {/* Toolbar — filter chips + search */}
      <div className="mb-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex flex-wrap gap-1.5 flex-1">
          {FILTER_CHIPS.map((chip) => {
            const isActive = filter === chip.id
            const count = counts[chip.id] || 0
            // Hide categories with zero items (except "All") so the toolbar
            // doesn't clutter with empty filters on small/young boards.
            if (chip.id !== 'all' && count === 0) return null
            return (
              <button
                key={chip.id}
                type="button"
                onClick={() => setFilter(chip.id)}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border transition ${
                  isActive
                    ? 'bg-slate-900 text-white border-slate-900 shadow-sm'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                }`}
                aria-pressed={isActive}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${chip.dot}`} aria-hidden="true" />
                <span>{chip.label}</span>
                <span className={`text-[10px] tabular-nums ${isActive ? 'text-white/80' : 'text-slate-400'}`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>
        <div className="relative shrink-0">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search events…"
            className="pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#168AAD] focus:border-[#168AAD] min-w-[200px]"
          />
        </div>
      </div>

      {/* Body */}
      {grouped.length === 0 ? (
        items.length === 0 ? (
          <EmptyState />
        ) : (
          <NoMatchState onClear={() => { setFilter('all'); setSearch('') }} />
        )
      ) : (
        <div className="space-y-6 pb-6">
          {grouped.map((group) => (
            <section key={group.day}>
              <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2 sticky top-[3px] z-10">
                <span className="bg-slate-50 pl-1 pr-2 py-0.5 rounded">{group.day} · {group.items.length}</span>
              </h3>
              <ol className="space-y-2.5">
                {group.items.map(({ msg, style }) => (
                  <li
                    key={msg.id}
                    className={`relative rounded-lg border border-slate-200 border-l-4 ${style.accent.split(' ').filter((c) => c.startsWith('border-l-')).join(' ')} bg-white px-4 py-3 shadow-sm hover:shadow-md hover:border-slate-300 transition`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`h-9 w-9 rounded-full flex items-center justify-center text-lg flex-shrink-0 ${style.accent.split(' ').filter((c) => c.startsWith('bg-') || c.startsWith('text-')).join(' ')}`}>
                        {style.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide ${style.chip}`}>
                            {style.label}
                          </span>
                          <span className="text-[11px] text-slate-400" title={new Date(msg.created_at).toLocaleString()}>
                            {relativeTime(msg.created_at)}
                          </span>
                          {msg.metadata?.backfill && (
                            <span
                              className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wide bg-amber-100 text-amber-700"
                              title="This entry was backfilled from historical data, not posted live."
                            >
                              backfill
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap break-words">
                          {msg.body}
                        </p>
                        {msg.author_name && msg.author_name.toLowerCase() !== 'system' && (
                          <p className="mt-1 text-[11px] text-slate-500">— {msg.author_name}</p>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

const EmptyState: React.FC = () => (
  <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-white px-6 py-16 text-center">
    <div className="text-5xl mb-3">📭</div>
    <h3 className="text-base font-semibold text-slate-800">Nothing on the board yet</h3>
    <p className="mt-1 text-sm text-slate-500 max-w-md mx-auto">
      System events will land here automatically as they happen — site updates, agreement changes,
      monitoring visits, workflow milestones, and more. Try creating a site, scheduling a visit, or
      completing a workflow step.
    </p>
  </div>
)

const NoMatchState: React.FC<{ onClear: () => void }> = ({ onClear }) => (
  <div className="rounded-2xl border border-slate-200 bg-white px-6 py-12 text-center">
    <div className="text-4xl mb-2">🔍</div>
    <h3 className="text-sm font-semibold text-slate-800">No events match your filter</h3>
    <button
      type="button"
      onClick={onClear}
      className="mt-3 text-xs font-semibold text-[#168AAD] hover:underline"
    >
      Clear filter + search
    </button>
  </div>
)

export default NoticeBoardView
