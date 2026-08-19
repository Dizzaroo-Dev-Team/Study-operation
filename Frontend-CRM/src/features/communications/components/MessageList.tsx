import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { api } from '@/lib/api'
import { Message, Attachment } from '@/types'
import AttachmentDisplay from '@/components/AttachmentDisplay'

// -----------------------------------------------------------------------------
// Module-scope helpers
// -----------------------------------------------------------------------------
// Hoisted out of the component so they don't get recreated on every render. The
// previous shape rebuilt the regex, the color palette, the channel-icon switch,
// the time formatter, etc. for every parent re-render — and with 200 messages
// in the list each re-render also instantiated 200 inline arrow callbacks plus
// 200 inline style objects, which is why the audit measured scroll INP > 400ms
// on mid-range Android.
// -----------------------------------------------------------------------------
const mentionEmailRegex = /@([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g

function getChannelIcon(channel: string): string {
  switch (channel) {
    case 'sms': return '📱'
    case 'whatsapp': return '💬'
    case 'email': return '📧'
    default: return '💬'
  }
}

function getChannelColor(channel: string): string {
  switch (channel) {
    case 'sms': return '#1E73BE'
    case 'whatsapp': return '#25D366'
    case 'email': return '#168AAD'
    default: return '#1E73BE'
  }
}

function formatTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  if (date.toDateString() === today.toDateString()) return 'Today'
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return date.toLocaleDateString([], {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

const USER_COLOR_PALETTE = [
  '#667eea', '#f093fb', '#4facfe', '#43e97b', '#fa709a',
  '#f6a523', '#30cfd0', '#00cec9', '#ff6b6b', '#feca57',
  '#c471ed', '#12c2e9', '#ffd93d', '#4ecdc4', '#a1c4fd',
  '#ff8a80', '#84fab0', '#a8caba', '#ff6b9d', '#c44569',
  '#6c5ce7', '#00b894', '#e17055', '#0984e3', '#2d3436',
]

function getUserColor(authorId: string | undefined): string {
  if (!authorId) return '#667eea'
  let hash = 0
  for (let i = 0; i < authorId.length; i++) {
    hash = authorId.charCodeAt(i) + ((hash << 5) - hash)
  }
  return USER_COLOR_PALETTE[Math.abs(hash) % USER_COLOR_PALETTE.length]
}

function getDarkerColor(color: string): string {
  const hex = color.replace('#', '')
  if (hex.length !== 6) return color
  const r = Math.floor(parseInt(hex.substring(0, 2), 16) * 0.75)
  const g = Math.floor(parseInt(hex.substring(2, 4), 16) * 0.75)
  const b = Math.floor(parseInt(hex.substring(4, 6), 16) * 0.75)
  return `#${r.toString(16).padStart(2, '0')}${g
    .toString(16)
    .padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

function extractMentionedEmails(message: Message): string[] {
  const fromField = (message.mentioned_emails || [])
    .map((e) => String(e).trim().toLowerCase())
    .filter(Boolean)
  const fromBodyMatches = Array.from(message.body.matchAll(mentionEmailRegex))
    .map((m) => (m[1] || '').trim().toLowerCase())
    .filter(Boolean)
  return Array.from(new Set([...fromField, ...fromBodyMatches]))
}

function getDisplayBody(message: Message): string {
  const cleaned = (message.body || '')
    .replace(mentionEmailRegex, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return cleaned || 'Message sent'
}

function getNoticeAttachment(
  message: Message,
  apiBase: string,
): { url: string; name: string; type: string } | null {
  const md = message.metadata || {}
  const attachmentUrl = typeof md.attachment_url === 'string' ? md.attachment_url : ''
  if (!attachmentUrl) return null

  const attachmentName =
    (typeof md.attachment_name === 'string' && md.attachment_name.trim()) || 'Document'
  const attachmentType =
    (typeof md.attachment_type === 'string' && md.attachment_type.trim()) || 'document'

  let resolvedUrl = attachmentUrl
  if (!/^https?:\/\//i.test(attachmentUrl)) {
    if (attachmentUrl.startsWith('/api')) {
      resolvedUrl = attachmentUrl
    } else {
      resolvedUrl = `${apiBase}${attachmentUrl.startsWith('/') ? '' : '/'}${attachmentUrl}`
    }
  }
  return { url: resolvedUrl, name: attachmentName, type: attachmentType }
}

async function openNoticeAttachment(attachmentUrl: string) {
  try {
    if (/^https?:\/\//i.test(attachmentUrl)) {
      window.open(attachmentUrl, '_blank', 'noopener,noreferrer')
      return
    }
    let requestPath = attachmentUrl
    if (requestPath.startsWith('/api/')) requestPath = requestPath.replace(/^\/api/, '')
    if (!requestPath.startsWith('/')) requestPath = `/${requestPath}`

    const response = await api.get(requestPath, { responseType: 'blob' })
    const blob = new Blob([response.data], { type: 'application/pdf' })
    const blobUrl = URL.createObjectURL(blob)
    // Try to revoke when the popup unloads (best lifecycle match — the PDF
    // is dereferenced only when the user closes that window). Fall back to
    // a generous timer because cross-origin / sandboxed popups may not
    // expose `unload`. The fallback is long enough that the user has time
    // to read short PDFs before the URL goes away.
    const popup = window.open(blobUrl, '_blank', 'noopener,noreferrer')
    let revoked = false
    const revokeOnce = () => {
      if (revoked) return
      revoked = true
      URL.revokeObjectURL(blobUrl)
    }
    try {
      popup?.addEventListener?.('unload', revokeOnce)
    } catch {
      // Cross-origin popup: cannot wire listener. Timer fallback only.
    }
    setTimeout(revokeOnce, 5 * 60 * 1000)
  } catch (error) {
    console.error('Failed to open notice attachment:', error)
    window.open(attachmentUrl, '_blank', 'noopener,noreferrer')
  }
}

// -----------------------------------------------------------------------------
// MessageItem — memoized single message row.
// -----------------------------------------------------------------------------
// Comparator below skips re-renders when nothing this row cares about changed.
// That is the load-bearing optimization: when a new message arrives, the
// existing 200 messages no longer re-render — only the new MessageItem mounts.
//
// Follow-up task: wrap MessageList in @tanstack/react-virtual so off-screen
// rows aren't rendered at all. Memoization is the prerequisite; virtualization
// is a separate change that also requires re-thinking the parent scroll
// container in ConversationDetail.
// -----------------------------------------------------------------------------
interface MessageItemProps {
  message: Message
  isOutbound: boolean
  showChannel: boolean
  isSelected: boolean
  selectionMode: boolean
  attachmentsForMessage: Attachment[] | undefined
  apiBase: string
  onMessageSelect?: (messageId: string, selected: boolean) => void
  onCreateTask?: (message: Message) => void
  onToggleDecision?: (message: Message) => void
}

const MessageItemBubble: React.FC<MessageItemProps> = ({
  message,
  isOutbound,
  showChannel,
  isSelected,
  selectionMode,
  attachmentsForMessage,
  apiBase,
  onMessageSelect,
  onCreateTask,
  onToggleDecision,
}) => {
  const noticeAttachment = getNoticeAttachment(message, apiBase)
  const userColor = getUserColor(message.author_id)
  const isDecision = !!message.is_decision
  const bubbleStyle = isOutbound
    ? {
        background: `linear-gradient(135deg, ${userColor} 0%, ${getDarkerColor(userColor)} 100%)`,
      }
    : undefined

  const handleRowClick = () => {
    if (selectionMode && onMessageSelect) {
      onMessageSelect(message.id, !isSelected)
    }
  }
  const handleTaskClick = () => {
    if (onCreateTask) onCreateTask(message)
  }
  const handleDecisionClick = () => {
    if (onToggleDecision) onToggleDecision(message)
  }
  const handleNoticeAttachmentClick = () => {
    if (noticeAttachment) void openNoticeAttachment(noticeAttachment.url)
  }

  return (
    <div
      data-message-id={message.id}
      className={`flex gap-3 ${isOutbound ? 'flex-row-reverse' : 'flex-row'} ${
        selectionMode ? 'cursor-pointer' : ''
      } ${isSelected ? 'ring-2 ring-dizzaroo-deep-blue rounded-xl p-1' : ''}`}
      onClick={handleRowClick}
    >
      {/* Channel Icon / Avatar */}
      {showChannel && (
        <div
          className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-md"
          style={{
            backgroundColor: isOutbound ? userColor : getChannelColor(message.channel),
          }}
        >
          {isOutbound
            ? message.author_name?.[0]?.toUpperCase() ||
              message.author_id?.[0]?.toUpperCase() ||
              '👤'
            : getChannelIcon(message.channel)}
        </div>
      )}
      {!showChannel && <div className="w-10 flex-shrink-0"></div>}

      {/* Message Bubble */}
      <div
        className={`flex-1 ${isOutbound ? 'items-end' : 'items-start'} flex flex-col`}
        style={{ maxWidth: '70%' }}
      >
        {showChannel && (
          <div
            className={`text-xs font-medium mb-1.5 px-1 ${
              isOutbound ? 'text-right' : 'text-left'
            } text-gray-600`}
          >
            {isOutbound
              ? message.author_name || message.author_id || 'You'
              : `${getChannelIcon(message.channel)} ${
                  message.author_name || message.author_id || message.channel.toUpperCase()
                }`}
          </div>
        )}
        <div
          className={`rounded-2xl px-4 py-2.5 relative ${
            isOutbound
              ? 'text-white rounded-br-md'
              : 'bg-white text-gray-900 rounded-bl-md shadow-sm'
          } ${isDecision ? 'ring-2 ring-accent-500' : ''}`}
          style={bubbleStyle}
        >
          {isDecision && (
            <div className="flex flex-wrap items-center gap-1 mb-1">
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-accent-100 text-accent-700">
                📌 Decision
              </span>
            </div>
          )}
          {!showChannel && message.author_name && (
            <div
              className={`text-xs font-medium mb-1 ${
                isOutbound ? 'text-white/90' : 'text-gray-600'
              }`}
            >
              {message.author_name}
            </div>
          )}
          {selectionMode && (
            <div className="absolute top-2 right-2">
              <div
                className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                  isSelected
                    ? 'bg-[#168AAD] border-[#168AAD]'
                    : 'border-gray-300 bg-white'
                }`}
              >
                {isSelected && <span className="text-white text-[10px]">✓</span>}
              </div>
            </div>
          )}
          <div
            className={`text-sm leading-relaxed whitespace-pre-wrap break-words ${
              isOutbound ? 'text-white' : 'text-gray-900'
            }`}
          >
            {getDisplayBody(message)}
          </div>
          {extractMentionedEmails(message).length > 0 && (
            <div className={`mt-1 text-xs ${isOutbound ? 'text-white/80' : 'text-gray-600'}`}>
              Sent to: {extractMentionedEmails(message).join(', ')}
            </div>
          )}
          {attachmentsForMessage && attachmentsForMessage.length > 0 && (
            <div className="mt-2 space-y-2">
              {attachmentsForMessage.map((att) => (
                <AttachmentDisplay
                  key={att.id}
                  attachment={att}
                  apiBase={apiBase}
                  isOutbound={isOutbound}
                />
              ))}
            </div>
          )}
          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-2 space-y-2">
              {message.attachments.map((att) => (
                <AttachmentDisplay
                  key={att.id}
                  attachment={att}
                  apiBase={apiBase}
                  isOutbound={isOutbound}
                />
              ))}
            </div>
          )}
          {noticeAttachment && (
            <div className="mt-2">
              <button
                type="button"
                onClick={handleNoticeAttachmentClick}
                className={`inline-flex items-center gap-2 px-2 py-1 rounded border text-xs ${
                  isOutbound
                    ? 'border-white/40 text-white/95 hover:bg-white/10'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                <span>📄</span>
                <span>{noticeAttachment.name}</span>
              </button>
            </div>
          )}
          <div className="flex items-center gap-2 mt-1.5 pt-1">
            <span className={`text-[10px] ${isOutbound ? 'text-white/60' : 'text-gray-400'}`}>
              {formatTime(message.created_at)}
            </span>
            <span
              className={`w-1 h-1 rounded-full ${
                message.status === 'queued'
                  ? 'bg-yellow-400'
                  : message.status === 'sent'
                  ? 'bg-blue-400'
                  : message.status === 'delivered'
                  ? 'bg-green-400'
                  : 'bg-red-400'
              }`}
              title={message.status}
            ></span>
          </div>
        </div>

        {!selectionMode && (onCreateTask || onToggleDecision) && (
          <div className={`mt-1.5 flex gap-1 ${isOutbound ? 'justify-end' : 'justify-start'}`}>
            {onCreateTask && (
              <button
                onClick={handleTaskClick}
                className="px-2 py-0.5 text-[10px] text-[#168AAD] hover:text-[#1E73BE] hover:bg-[#168AAD]/5 rounded transition flex items-center gap-1"
                title="Create task from this message"
              >
                <span>✓</span>
                <span>Create Task</span>
              </button>
            )}
            {onToggleDecision && (
              <button
                onClick={handleDecisionClick}
                className={`px-2 py-0.5 text-[10px] rounded transition flex items-center gap-1 ${
                  isDecision
                    ? 'text-accent-700 bg-accent-50 hover:bg-accent-100'
                    : 'text-gray-500 hover:text-accent-700 hover:bg-accent-50'
                }`}
                title={isDecision ? 'Unpin as decision' : 'Pin as a decision of record'}
              >
                <span>📌</span>
                <span>{isDecision ? 'Pinned' : 'Pin decision'}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const MessageItem = React.memo(MessageItemBubble, (prev, next) => {
  // Re-render only when something this row visibly depends on changed.
  // Reference-equal attachment arrays are enough: parent supplies the same
  // array reference unless attachments for THIS message actually changed,
  // because attachmentsMap is built outside the row.
  if (prev.message.id !== next.message.id) return false
  if (prev.message.body !== next.message.body) return false
  if (prev.message.status !== next.message.status) return false
  if (prev.message.author_name !== next.message.author_name) return false
  if (prev.message.channel !== next.message.channel) return false
  if (prev.message.direction !== next.message.direction) return false
  if (prev.message.created_at !== next.message.created_at) return false
  if (prev.message.is_decision !== next.message.is_decision) return false
  if (prev.onToggleDecision !== next.onToggleDecision) return false
  if (prev.isOutbound !== next.isOutbound) return false
  if (prev.showChannel !== next.showChannel) return false
  if (prev.isSelected !== next.isSelected) return false
  if (prev.selectionMode !== next.selectionMode) return false
  if (prev.attachmentsForMessage !== next.attachmentsForMessage) return false
  if (prev.apiBase !== next.apiBase) return false
  if (prev.onMessageSelect !== next.onMessageSelect) return false
  if (prev.onCreateTask !== next.onCreateTask) return false
  return true
})

// -----------------------------------------------------------------------------
// Flat-item model for virtualization
// -----------------------------------------------------------------------------
// TanStack Virtual works best with a single flat array. We interleave date
// headers and message rows so each virtual slot corresponds to exactly one
// item type. The renderer below dispatches on `item.kind`.
//
// Identity for diffing: header `key` includes the dateKey; message `key`
// is the message id. Stable across re-renders so the virtualizer can keep
// measured heights cached.
// -----------------------------------------------------------------------------
type ListItem =
  | { kind: 'header'; key: string; label: string }
  | {
      kind: 'message'
      key: string
      message: Message
      isOutbound: boolean
      showChannel: boolean
    }

// -----------------------------------------------------------------------------
// MessageList — virtualized date-grouped list.
// -----------------------------------------------------------------------------
// Receives a ref to its scroll-parent (ConversationDetail's `overflow-y-auto`
// pane) so the virtualizer can observe scroll position. Only the rows in the
// visible window — plus an overscan buffer — are actually mounted in the DOM.
//
// Notes / trade-offs
// ------------------
// - **Find-in-page**: browser Ctrl-F won't match text inside un-rendered
//   off-screen messages. This is the standard virtualization trade-off. The
//   in-app search (when added) needs to operate over the full `messages`
//   array directly, not the rendered DOM.
// - **Dynamic heights**: messages range from ~50px (one-liner) to several
//   hundred px (long body + attachments). `measureElement` measures each
//   actual rendered item; mismatches in `estimateSize` only cause a quick
//   re-layout once the row scrolls into view.
// - **Scroll-to-bottom**: ConversationDetail's `messagesEndRef.current
//   ?.scrollIntoView()` still works because the virtualizer renders an
//   absolute-positioned container of total height; the end ref sits below
//   that container at its real document position.
// -----------------------------------------------------------------------------
interface MessageListProps {
  messages: Message[]
  onMessageSelect?: (messageId: string, selected: boolean) => void
  selectedMessageIds?: string[]
  selectionMode?: boolean
  apiBase?: string
  conversationId?: string
  onCreateTask?: (message: Message) => void
  onToggleDecision?: (message: Message) => void
  // Scroll container ref forwarded from the parent. The virtualizer reads
  // `scrollTop` from this element. When undefined we fall back to plain
  // rendering — keeps any non-ConversationDetail caller working without a
  // scroll context.
  scrollParentRef?: React.RefObject<HTMLElement | null>
}

const MessageList: React.FC<MessageListProps> = ({
  messages,
  onMessageSelect,
  selectedMessageIds = [],
  selectionMode = false,
  apiBase = '',
  conversationId,
  onCreateTask,
  onToggleDecision,
  scrollParentRef,
}) => {
  const [attachmentsMap, setAttachmentsMap] = useState<Record<string, Attachment[]>>({})

  // Anchor for the virtualizer's scrollMargin — tells TanStack how far this
  // list begins inside the parent scroll element (there's banner content
  // above it). Re-measured by `useEffect` below on every layout change so a
  // banner toggle (selectionMode etc.) doesn't drift item positions.
  const innerRef = useRef<HTMLDivElement>(null)
  const [scrollMargin, setScrollMargin] = useState(0)

  // Fetch attachments for all messages
  useEffect(() => {
    if (!conversationId) return

    const fetchAttachments = async () => {
      try {
        const response = await api.get(`/conversations/${conversationId}/attachments`)
        const attachments: Attachment[] = response.data || []
        const grouped: Record<string, Attachment[]> = {}
        attachments.forEach((att) => {
          if (att.message_id) {
            if (!grouped[att.message_id]) grouped[att.message_id] = []
            grouped[att.message_id].push(att)
          }
        })
        setAttachmentsMap(grouped)
      } catch (error) {
        if ((error as any)?.response?.status !== 403) {
          console.error('Failed to fetch attachments:', error)
        }
      }
    }

    fetchAttachments()
  }, [conversationId, messages.length])

  // Flatten date headers + messages into a single list. Memoized so the
  // virtualizer doesn't think every render changes the count.
  const items = useMemo<ListItem[]>(() => {
    if (!messages || messages.length === 0) return []
    const sorted = [...messages].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    )
    const grouped: Record<string, Message[]> = {}
    sorted.forEach((msg) => {
      const dateKey = new Date(msg.created_at).toDateString()
      if (!grouped[dateKey]) grouped[dateKey] = []
      grouped[dateKey].push(msg)
    })
    const keys = Object.keys(grouped).sort(
      (a, b) => new Date(a).getTime() - new Date(b).getTime(),
    )

    const out: ListItem[] = []
    for (const dateKey of keys) {
      const dateMessages = grouped[dateKey]
      out.push({
        kind: 'header',
        key: `header:${dateKey}`,
        label: formatDate(dateMessages[0].created_at),
      })
      for (let idx = 0; idx < dateMessages.length; idx++) {
        const message = dateMessages[idx]
        const isOutbound = message.direction === 'outbound'
        const showChannel =
          idx === 0 ||
          dateMessages[idx - 1].channel !== message.channel ||
          dateMessages[idx - 1].direction !== message.direction
        out.push({
          kind: 'message',
          key: message.id,
          message,
          isOutbound,
          showChannel,
        })
      }
    }
    return out
  }, [messages])

  // O(1) Set lookup beats Array.includes on every render of every message.
  const selectedSet = useMemo(() => new Set(selectedMessageIds), [selectedMessageIds])

  // Keep scrollMargin in sync with the inner container's offset inside the
  // parent scroll element. Banners (error / selectionMode / "Showing N
  // messages") may toggle above the list and shift this offset; without this
  // re-measure the virtualizer would mis-position items by a few dozen px.
  useEffect(() => {
    const parent = scrollParentRef?.current
    const inner = innerRef.current
    if (!parent || !inner) return

    const update = () => {
      const innerTop = inner.getBoundingClientRect().top
      const parentTop = parent.getBoundingClientRect().top
      setScrollMargin(Math.max(0, innerTop - parentTop + parent.scrollTop))
    }
    update()

    // Re-measure on parent resize (e.g. sidebar toggle).
    let ro: ResizeObserver | null = null
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(update)
      ro.observe(parent)
    }
    return () => {
      if (ro) ro.disconnect()
    }
  }, [scrollParentRef, messages.length, selectionMode])

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollParentRef?.current ?? null,
    // 64px header / 96px message bubble are rough estimates — measureElement
    // corrects them once each row mounts.
    estimateSize: (index) => (items[index]?.kind === 'header' ? 64 : 120),
    overscan: 8,
    scrollMargin,
    getItemKey: (index) => items[index]?.key ?? index,
  })

  if (!messages || messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full min-h-[500px]">
        <div className="text-center">
          <div className="text-8xl mb-6">💬</div>
          <p className="text-2xl font-bold text-gray-700 mb-2">No messages yet</p>
          <p className="text-base text-gray-500">
            Start the conversation by sending a message
          </p>
        </div>
      </div>
    )
  }

  // Fallback: when no scroll-parent ref is wired (unusual caller), render
  // unvirtualized. Keeps the component drop-in compatible.
  if (!scrollParentRef) {
    return (
      <div className="space-y-3">
        {items.map((item) =>
          item.kind === 'header' ? (
            <div key={item.key} className="text-center py-2">
              <span className="px-4 py-1.5 bg-white border-2 border-gray-300 text-gray-600 text-xs font-bold uppercase tracking-wider rounded-full shadow-sm">
                {item.label}
              </span>
            </div>
          ) : (
            <MessageItem
              key={item.key}
              message={item.message}
              isOutbound={item.isOutbound}
              showChannel={item.showChannel}
              isSelected={selectedSet.has(item.message.id)}
              selectionMode={selectionMode}
              attachmentsForMessage={attachmentsMap[item.message.id]}
              apiBase={apiBase}
              onMessageSelect={onMessageSelect}
              onCreateTask={onCreateTask}
              onToggleDecision={onToggleDecision}
            />
          ),
        )}
      </div>
    )
  }

  const totalSize = virtualizer.getTotalSize()
  const virtualItems = virtualizer.getVirtualItems()

  return (
    <div ref={innerRef} style={{ position: 'relative', width: '100%', height: totalSize }}>
      {virtualItems.map((vRow) => {
        const item = items[vRow.index]
        if (!item) return null
        return (
          <div
            key={vRow.key}
            data-index={vRow.index}
            ref={virtualizer.measureElement}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${vRow.start - scrollMargin}px)`,
              // 12px gutter between rows preserves the old `space-y-3` feel
              // without leaning on a wrapper that would defeat virtualization.
              paddingBottom: 12,
            }}
          >
            {item.kind === 'header' ? (
              <div className="text-center py-2">
                <span className="px-4 py-1.5 bg-white border-2 border-gray-300 text-gray-600 text-xs font-bold uppercase tracking-wider rounded-full shadow-sm">
                  {item.label}
                </span>
              </div>
            ) : (
              <MessageItem
                message={item.message}
                isOutbound={item.isOutbound}
                showChannel={item.showChannel}
                isSelected={selectedSet.has(item.message.id)}
                selectionMode={selectionMode}
                attachmentsForMessage={attachmentsMap[item.message.id]}
                apiBase={apiBase}
                onMessageSelect={onMessageSelect}
                onCreateTask={onCreateTask}
                onToggleDecision={onToggleDecision}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

export default MessageList
