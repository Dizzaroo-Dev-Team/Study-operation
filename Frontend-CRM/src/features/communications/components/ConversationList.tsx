import React, { useState, useEffect, useMemo } from 'react'
import { api } from '@/lib/api'
import { Conversation, Message } from '@/types'
import {
  DerivedStatus,
  deriveConversationStatus,
  formatAge,
} from '@/features/communications/hooks/useConversationStatus'

interface ConversationListProps {
  conversations: Conversation[]
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
  deletingId?: string | null
  selectedId?: string
  apiBase: string
}

/**
 * Section ordering follows the operational triage hierarchy — what the user
 * owes a reply to comes first, then what they're waiting on, then stale, etc.
 */
// `notice-board` is intentionally excluded — it renders as a pinned card
// above the section list rather than as a collapsible section.
const SECTION_ORDER: DerivedStatus[] = [
  'needs-reply',
  'awaiting-reply',
  'no-messages',
  'stale',
  'snoozed',
  'resolved',
  'closed',
]

const SECTION_TITLES: Record<DerivedStatus, string> = {
  'notice-board': 'Notice board',
  'needs-reply': 'Needs your reply',
  'awaiting-reply': 'Awaiting their reply',
  'no-messages': 'Just created',
  'stale': 'No update in 7 days',
  'snoozed': 'Snoozed',
  'resolved': 'Resolved',
  'closed': 'Closed',
}

const ConversationList: React.FC<ConversationListProps> = ({
  conversations,
  onSelect,
  onDelete,
  deletingId,
  selectedId,
  apiBase,
}) => {
  const [lastMessages, setLastMessages] = useState<Record<string, Message | undefined>>({})
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({
    // Noisy sections collapsed by default so triage focus stays at the top.
    stale: true,
    closed: true,
  })

  useEffect(() => {
    const load = async () => {
      const next: Record<string, Message | undefined> = {}
      await Promise.all(
        conversations.map(async (conv) => {
          try {
            const response = await api.get(`${apiBase}/conversations/${conv.id}?limit=1`)
            const messages: Message[] = response.data.messages || []
            next[conv.id] = messages[0]
          } catch (err: any) {
            if (err.response?.status !== 403) {
              console.error(`Failed to load last message for ${conv.id}:`, err)
            }
          }
        }),
      )
      setLastMessages(next)
    }
    if (conversations.length > 0) load()
  }, [conversations, apiBase])

  const grouped = useMemo(() => {
    const buckets: Record<DerivedStatus, Conversation[]> = {
      'notice-board': [],
      'needs-reply': [],
      'awaiting-reply': [],
      'no-messages': [],
      'stale': [],
      'snoozed': [],
      'resolved': [],
      'closed': [],
    }
    for (const conv of conversations) {
      const info = deriveConversationStatus(lastMessages[conv.id], conv.updated_at, conv)
      buckets[info.status].push(conv)
    }
    for (const key of Object.keys(buckets) as DerivedStatus[]) {
      buckets[key].sort((a, b) => {
        const ta = new Date(lastMessages[a.id]?.created_at || a.updated_at).getTime()
        const tb = new Date(lastMessages[b.id]?.created_at || b.updated_at).getTime()
        return tb - ta
      })
    }
    return buckets
  }, [conversations, lastMessages])

  const toggleSection = (key: DerivedStatus) =>
    setCollapsedSections((prev) => ({ ...prev, [key]: !prev[key] }))

  if (conversations.length === 0) {
    return (
      <div className="p-8 text-center text-slate-500">
        <p className="text-ui-body-sm mb-1">No conversations yet</p>
        <p className="text-ui-caption">Create a new one to get started</p>
      </div>
    )
  }

  const noticeBoards = grouped['notice-board']

  return (
    <div className="py-1" role="listbox" aria-label="Conversations">
      {/* Pinned public notice board(s) — always at the top, no section header,
          no chevron, no count. There's typically only one per study+site. */}
      {noticeBoards.length > 0 && (
        <div className="px-1 mb-2">
          {noticeBoards.map((conv) => (
            <PinnedNoticeRow
              key={conv.id}
              conversation={conv}
              isSelected={selectedId === conv.id}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}

      {SECTION_ORDER.map((key) => {
        const items = grouped[key]
        if (items.length === 0) return null
        const isCollapsed = !!collapsedSections[key]
        return (
          <div key={key} className="mb-1">
            <button
              type="button"
              onClick={() => toggleSection(key)}
              className="w-full flex items-center justify-between px-3 py-1.5 text-ui-caption uppercase tracking-wide text-slate-500 hover:text-slate-700 transition"
              aria-expanded={!isCollapsed}
            >
              <span className="flex items-center gap-2">
                <Chevron open={!isCollapsed} />
                <span>{SECTION_TITLES[key]}</span>
                <span className="text-slate-400">{items.length}</span>
              </span>
            </button>
            {!isCollapsed && (
              <div className="space-y-0.5 px-1">
                {items.map((conv) => (
                  <ConversationRow
                    key={conv.id}
                    conversation={conv}
                    lastMessage={lastMessages[conv.id]}
                    isSelected={selectedId === conv.id}
                    onSelect={onSelect}
                    onDelete={onDelete}
                    isDeleting={deletingId === conv.id}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

const Chevron: React.FC<{ open: boolean }> = ({ open }) => (
  <svg
    width="10"
    height="10"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`transition-transform ${open ? 'rotate-90' : ''}`}
    aria-hidden="true"
  >
    <path d="M9 18l6-6-6-6" />
  </svg>
)

interface ConversationRowProps {
  conversation: Conversation
  lastMessage: Message | undefined
  isSelected: boolean
  isDeleting?: boolean
  // Receives the conversation id so the parent can pass a single stable
  // callback for the whole list instead of constructing a fresh
  // `() => onSelect(conv.id)` arrow per row (which would break React.memo
  // every render and defeat the entire optimization).
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
}

const ConversationRowImpl: React.FC<ConversationRowProps> = ({
  conversation,
  lastMessage,
  isSelected,
  isDeleting,
  onSelect,
  onDelete,
}) => {
  const info = deriveConversationStatus(lastMessage, conversation.updated_at, conversation)
  const subject = conversation.subject || conversation.title || 'Untitled conversation'
  const preview = lastMessage?.body ?? '—'
  const previewTrim = preview.length > 70 ? `${preview.slice(0, 70)}…` : preview

  const handleClick = () => onSelect(conversation.id)
  const handleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect(conversation.id)
    }
  }

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isDeleting || !onDelete) return
    const subject = conversation.subject || conversation.title || 'this conversation'
    if (!window.confirm(`Delete "${subject}"? This cannot be undone.`)) return
    onDelete(conversation.id)
  }

  return (
    <div
      role="option"
      aria-selected={isSelected}
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKey}
      style={
        isSelected
          ? {
              background:
                'linear-gradient(90deg, rgba(22,138,173,0.16) 0%, rgba(22,138,173,0.04) 60%, transparent 100%)',
            }
          : undefined
      }
      className={`group relative pl-3 pr-2 py-2 rounded cursor-pointer transition outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
        isSelected ? 'border-l-2 border-brand-500' : 'border-l-2 border-transparent hover:bg-slate-50/70'
      }`}
    >
      <div className="flex items-start gap-2">
        <span
          className={`mt-1.5 inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${info.dotClass}`}
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between gap-2">
            <h3
              className={`truncate text-ui-body ${
                isSelected ? 'text-brand-700 font-semibold' : 'text-slate-900 font-medium'
              }`}
            >
              {subject}
            </h3>
            <div className="flex items-center gap-1 flex-shrink-0">
              {onDelete && (
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={isDeleting}
                  title="Delete conversation"
                  aria-label="Delete conversation"
                  className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isDeleting ? (
                    <span className="w-3.5 h-3.5 inline-block border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      <path d="M10 11v6M14 11v6" />
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                    </svg>
                  )}
                </button>
              )}
              <span className="text-ui-caption text-slate-400 tabular-nums">
                {formatAge(info.hoursSinceLastMessage)}
              </span>
            </div>
          </div>
          <p className="truncate text-ui-body-sm text-slate-500 mt-0.5">{previewTrim}</p>
          <div className="flex items-center gap-1.5 mt-1">
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium border ${info.pillClass}`}
            >
              {info.label}
            </span>
            {conversation.is_confidential === 'true' && (
              <span
                className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-danger-50 text-danger-600 border border-danger-500/30"
                title="Confidential"
              >
                Confidential
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Memoized — re-render only when this row's own fields, its preview-driving
// last message, or the selection state changed. With several dozen rows in
// a typical inbox, the unmemoized version re-rendered every row on every
// parent state tick (e.g. new message arriving for some other conversation).
const ConversationRow = React.memo(ConversationRowImpl, (prev, next) => {
  if (prev.isSelected !== next.isSelected) return false
  if (prev.isDeleting !== next.isDeleting) return false
  if (prev.onSelect !== next.onSelect) return false
  if (prev.onDelete !== next.onDelete) return false
  if (prev.conversation.id !== next.conversation.id) return false
  if (prev.conversation.subject !== next.conversation.subject) return false
  if (prev.conversation.title !== next.conversation.title) return false
  if (prev.conversation.updated_at !== next.conversation.updated_at) return false
  if (prev.conversation.is_confidential !== next.conversation.is_confidential) return false
  if ((prev.lastMessage?.id || null) !== (next.lastMessage?.id || null)) return false
  if ((prev.lastMessage?.body || '') !== (next.lastMessage?.body || '')) return false
  return true
})

/**
 * Pinned public notice board — distinct visual treatment so it reads as a
 * persistent broadcast surface rather than a regular conversation row.
 */
const PinnedNoticeRowImpl: React.FC<{
  conversation: Conversation
  isSelected: boolean
  onSelect: (id: string) => void
}> = ({ conversation, isSelected, onSelect }) => {
  const subject = conversation.subject || conversation.title || 'Public notice board'
  const handleClick = () => onSelect(conversation.id)
  const handleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect(conversation.id)
    }
  }
  return (
    <div
      role="option"
      aria-selected={isSelected}
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKey}
      style={{
        background: isSelected
          ? 'linear-gradient(135deg, rgba(22,138,173,0.18) 0%, rgba(118,200,147,0.12) 100%)'
          : 'linear-gradient(135deg, rgba(22,138,173,0.08) 0%, rgba(118,200,147,0.06) 100%)',
      }}
      className={`group relative px-3 py-2 rounded-lg cursor-pointer transition outline-none focus-visible:ring-2 focus-visible:ring-brand-500 border ${
        isSelected ? 'border-brand-500 shadow-card' : 'border-brand-500/30 hover:border-brand-500/50'
      }`}
    >
      <div className="flex items-start gap-2">
        <span
          className="mt-0.5 inline-flex items-center justify-center w-5 h-5 rounded bg-brand-500/15 text-brand-700 flex-shrink-0"
          aria-hidden="true"
          title="Pinned notice board"
        >
          {/* Pin icon */}
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m12 17 .002 5" />
            <path d="M9 10V4h6v6l4 5H5l4-5z" />
          </svg>
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between gap-2">
            <h3
              className={`truncate text-ui-body font-semibold ${
                isSelected ? 'text-brand-700' : 'text-slate-900'
              }`}
            >
              {subject}
            </h3>
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-brand-100 text-brand-700 border border-brand-500/30 flex-shrink-0">
              Pinned
            </span>
          </div>
          <p className="text-ui-caption text-slate-500 mt-0.5">
            Persistent public board for everyone on this site
          </p>
        </div>
      </div>
    </div>
  )
}

const PinnedNoticeRow = React.memo(PinnedNoticeRowImpl, (prev, next) => {
  if (prev.isSelected !== next.isSelected) return false
  if (prev.onSelect !== next.onSelect) return false
  if (prev.conversation.id !== next.conversation.id) return false
  if (prev.conversation.subject !== next.conversation.subject) return false
  if (prev.conversation.title !== next.conversation.title) return false
  return true
})

export default ConversationList
