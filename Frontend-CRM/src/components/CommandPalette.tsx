import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useStudySite } from '../contexts/StudySiteContext'
import { useConversationsList } from '@/lib/queries/useConversations'
import { useTasksList } from '@/lib/queries/useTasks'
import { Conversation, MonitoringTask } from '../types'

interface CommandPaletteProps {
  apiBase: string
  onSelectConversation?: (id: string) => void
  onModeChange?: (mode: string) => void
}

interface PaletteResult {
  kind: 'conversation' | 'task' | 'action'
  id: string
  title: string
  subtitle?: string
  badge?: string
  onPick: () => void
}

const MODE_ACTIONS: { id: string; title: string; subtitle?: string }[] = [
  { id: 'dashboard', title: 'Go to Dashboard' },
  { id: 'conversations', title: 'Go to Conversations' },
  { id: 'threads', title: 'Go to Threads' },
  { id: 'site-status', title: 'Go to Site status' },
  { id: 'monitoring', title: 'Go to Monitoring' },
  { id: 'documents', title: 'Go to Documents' },
  { id: 'study-setup', title: 'Go to Study setup' },
  { id: 'tasks', title: 'Go to Tasks' },
]

/**
 * Global search palette. Opens on Cmd/Ctrl+K, searches conversations + tasks
 * scoped to the current study/site, and lets the user jump to top-level pages.
 * Keyboard model: arrow keys move highlight, Enter selects, Esc closes.
 */
const CommandPalette: React.FC<CommandPaletteProps> = ({
  onSelectConversation,
  onModeChange,
}) => {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const { selectedStudyId, selectedSiteId } = useStudySite()

  // Lazy-fire queries only when the palette is open. The shared cache means
  // the typical case (open → close → reopen) is an instant cache hit.
  const conversationsQuery = useConversationsList(
    {
      study_id: selectedStudyId ?? null,
      site_id: selectedSiteId ?? null,
      limit: 50,
    },
    { enabled: open },
  )
  const tasksQuery = useTasksList(
    { siteId: selectedSiteId ?? null, limit: 50 },
    { enabled: open },
  )
  const conversations: Conversation[] = (conversationsQuery.data ?? []) as Conversation[]
  const tasks: MonitoringTask[] = (tasksQuery.data ?? []) as MonitoringTask[]

  // Global hotkey: Cmd+K / Ctrl+K to toggle.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isModK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k'
      if (isModK) {
        e.preventDefault()
        setOpen((o) => !o)
      } else if (e.key === 'Escape' && open) {
        e.preventDefault()
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  // Focus + reset highlight when the palette opens.
  useEffect(() => {
    if (!open) return
    setActiveIndex(0)
    inputRef.current?.focus()
  }, [open])

  // Reset highlight when query changes.
  useEffect(() => setActiveIndex(0), [query])

  const results = useMemo<PaletteResult[]>(() => {
    const q = query.trim().toLowerCase()
    const convResults: PaletteResult[] = conversations
      .filter(
        (c) =>
          !q ||
          (c.subject || '').toLowerCase().includes(q) ||
          (c.tracker_code || '').toLowerCase().includes(q) ||
          (c.participant_email || '').toLowerCase().includes(q),
      )
      .slice(0, 8)
      .map((c) => ({
        kind: 'conversation',
        id: c.id,
        title: c.subject || 'Untitled conversation',
        subtitle: c.tracker_code || c.participant_email || undefined,
        badge: 'Conversation',
        onPick: () => onSelectConversation?.(c.id),
      }))

    const taskResults: PaletteResult[] = tasks
      .filter((t) => {
        if (!q) return true
        const hay = `${t.title || ''} ${t.description || ''} ${t.assignedTo || ''} ${t.requestedBy || ''}`.toLowerCase()
        return hay.includes(q)
      })
      .slice(0, 8)
      .map((t) => ({
        kind: 'task',
        id: t.id,
        title: t.description || t.title || 'Untitled task',
        subtitle: t.assignedTo ? `→ ${t.assignedTo}` : undefined,
        badge: 'Task',
        onPick: () => onModeChange?.('tasks'),
      }))

    const actionResults: PaletteResult[] = MODE_ACTIONS.filter(
      (a) => !q || a.title.toLowerCase().includes(q),
    ).map((a) => ({
      kind: 'action',
      id: `action:${a.id}`,
      title: a.title,
      badge: 'Action',
      onPick: () => onModeChange?.(a.id),
    }))

    return [...convResults, ...taskResults, ...actionResults]
  }, [conversations, tasks, query, onSelectConversation, onModeChange])

  const pick = (r: PaletteResult) => {
    r.onPick()
    setOpen(false)
    setQuery('')
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, Math.max(results.length - 1, 0)))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const r = results[activeIndex]
      if (r) pick(r)
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[300] flex items-start justify-center pt-24 px-4 bg-black/40 backdrop-blur-sm"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="w-full max-w-xl bg-white rounded-xl shadow-popover border border-slate-200 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-200">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search conversations, tasks, or jump to…"
            className="flex-1 outline-none text-ui-body text-slate-900 placeholder:text-slate-400 bg-transparent"
            aria-label="Search"
          />
          <kbd className="text-ui-caption text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">
            Esc
          </kbd>
        </div>
        <ul className="max-h-96 overflow-y-auto py-1" role="listbox">
          {results.length === 0 && (
            <li className="px-4 py-8 text-center text-ui-body-sm text-slate-500">
              No matches.
            </li>
          )}
          {results.map((r, idx) => (
            <li
              key={`${r.kind}:${r.id}`}
              role="option"
              aria-selected={idx === activeIndex}
              onMouseEnter={() => setActiveIndex(idx)}
              onClick={() => pick(r)}
              className={`px-4 py-2 cursor-pointer flex items-center gap-3 ${
                idx === activeIndex ? 'bg-brand-50' : 'hover:bg-slate-50'
              }`}
            >
              <span
                className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide ${
                  r.kind === 'conversation'
                    ? 'bg-brand-100 text-brand-700'
                    : r.kind === 'task'
                      ? 'bg-warning-50 text-warning-600'
                      : 'bg-slate-100 text-slate-600'
                }`}
              >
                {r.badge}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-ui-body text-slate-900 truncate">{r.title}</div>
                {r.subtitle && (
                  <div className="text-ui-caption text-slate-500 truncate">{r.subtitle}</div>
                )}
              </div>
              {idx === activeIndex && (
                <kbd className="text-ui-caption text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">
                  ↵
                </kbd>
              )}
            </li>
          ))}
        </ul>
        <div className="border-t border-slate-200 px-4 py-2 flex items-center justify-between text-ui-caption text-slate-500">
          <span>
            <kbd className="border border-slate-200 rounded px-1.5 py-0.5">↑</kbd>{' '}
            <kbd className="border border-slate-200 rounded px-1.5 py-0.5">↓</kbd> navigate
          </span>
          <span>
            <kbd className="border border-slate-200 rounded px-1.5 py-0.5">↵</kbd> select
          </span>
        </div>
      </div>
    </div>
  )
}

export default CommandPalette
