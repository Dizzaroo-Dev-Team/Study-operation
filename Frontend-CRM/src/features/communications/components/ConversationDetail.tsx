import React, { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useRealtime } from '@/lib/realtime'
import { appendRealtimeMessage, mergeServerMessages } from '@/features/communications/utils/messageMerge'
import MessageList from './MessageList'
import NoticeBoardView from './NoticeBoardView'
import SendMessageForm from './SendMessageForm'
import CreateThreadFromConversation from './CreateThreadFromConversation'
import PrivilegedActions from '@/components/PrivilegedActions'
import TaskFormModal from '@/features/operations/components/TaskFormModal'
import ConversationRightSidebar from './ConversationRightSidebar'
import InlineAISummary from '@/features/ai/components/InlineAISummary'
import { Conversation, Message } from '@/types'


// Shared outline-style class used by every secondary header button so the
// toolbar reads as a single coherent group rather than a row of mismatched
// pills. Exported as a constant (not inline) so tweaks land in one place.
export const TOOLBAR_BTN_CLASS =
  'inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-300 ' +
  'text-gray-700 rounded-lg text-xs font-medium hover:bg-gray-50 hover:border-gray-400 ' +
  'disabled:opacity-50 disabled:cursor-not-allowed transition whitespace-nowrap'

const iconBaseProps = {
  width: 14,
  height: 14,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

const SparkleIcon: React.FC = () => (
  <svg {...iconBaseProps} aria-hidden="true">
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
  </svg>
)

const SearchIcon: React.FC = () => (
  <svg {...iconBaseProps} aria-hidden="true">
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </svg>
)

const CheckboxIcon: React.FC = () => (
  <svg {...iconBaseProps} aria-hidden="true">
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M9 12l2 2 4-4" />
  </svg>
)

const PlusIcon: React.FC = () => (
  <svg {...iconBaseProps} aria-hidden="true">
    <path d="M12 5v14M5 12h14" />
  </svg>
)

const CloseIcon: React.FC = () => (
  <svg {...iconBaseProps} aria-hidden="true">
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
)

const SidebarIcon: React.FC = () => (
  <svg {...iconBaseProps} aria-hidden="true">
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M15 3v18" />
  </svg>
)


interface ConversationDetailProps {
  conversation: Conversation
  onRefresh: () => void
  apiBase: string
  currentUserId?: string
}

const ConversationDetail: React.FC<ConversationDetailProps> = ({
  conversation,
  onRefresh,
  apiBase,
  currentUserId
}) => {
  // Local mirror of the conversation so the inline state chips can apply
  // optimistic updates without round-tripping the parent.
  const [localConversation, setLocalConversation] = useState<Conversation>(conversation)
  // Re-sync local mirror whenever the parent passes a meaningfully different
  // conversation. Depending only on `updated_at` was fragile — a missing /
  // unchanged timestamp left this mirror stale even when other fields
  // (status, participants) shifted on the parent. Re-syncing on every new
  // reference is cheap and keeps the optimistic-update story intact (the
  // optimistic write happens via `setLocalConversation`, which doesn't bump
  // the parent prop).
  useEffect(() => {
    setLocalConversation(conversation)
  }, [conversation])
  const [messages, setMessages] = useState<Message[]>([])
  const [wsConnected, setWsConnected] = useState(false)
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([])
  const [showCreateThreadModal, setShowCreateThreadModal] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [taskModalData, setTaskModalData] = useState<{
    message: Message | null
  } | null>(null)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true)
  const [liveAiSummary, setLiveAiSummary] = useState<string | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  // Scroll container ref — handed to MessageList so its virtualizer can
  // observe scroll position. The container has other content above/below
  // the virtual list (banners, AI summary, etc.); the virtualizer's
  // scrollMargin handles the offset.
  const messagesScrollRef = useRef<HTMLDivElement>(null)
  const { user, token } = useAuth()
  // Prefer the explicit prop, but fall back to the authenticated user rather
  // than a magic 'current_user' string that could silently mask an auth gap.
  const effectiveUserId = currentUserId || user?.user_id

  // Fetch messages when conversation changes
  useEffect(() => {
    const fetchMessages = async () => {
      if (!conversation?.id) {
        setMessages([])
        return
      }

      try {
        setError(null)

        const response = await api.get(
          `${apiBase}/conversations/${conversation.id}?limit=200&offset=0`
        )

        if (response.data && response.data.messages) {
          // Backend returns messages sorted by created_at DESCENDING (latest first)
          // We need to sort them ASCENDING (oldest first) for display
          const rawMessages = response.data.messages || []
          
          // Filter out any invalid messages
          const validMessages = rawMessages.filter((msg: any) => 
            msg && msg.id && msg.body !== undefined && msg.direction && msg.channel
          )
          
          const sortedMessages = [...validMessages].sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          )

          const uniqueMessages = sortedMessages.reduce((acc: Message[], msg: Message) => {
            if (!acc.find((m: Message) => m.id === msg.id)) {
              acc.push(msg)
            }
            return acc
          }, [] as Message[])

          setMessages(uniqueMessages)
        } else {
          setMessages([])
        }
      } catch (error: any) {
        console.error('Failed to fetch messages:', error)
        if (error.response?.status === 403) {
          setError('You do not have access to this conversation.')
          setMessages([])
        } else {
          setError(error.response?.data?.detail || 'Failed to load messages')
          setMessages([])
        }
      }
    }

    fetchMessages()
  }, [conversation?.id, apiBase, currentUserId, token])

  // Self-heal for the panel. The conversation LIST recovers via React Query's
  // refetchOnWindowFocus; the panel's locally-held `messages` had no equivalent,
  // so a missed/late realtime event (reconnect gap, panel mounted after the
  // event) left it stale while the list refreshed — the "list updates, panel
  // doesn't" symptom. Reconcile by re-pulling messages on (re)subscribe and on
  // window focus. mergeServerMessages dedupes by id so nothing can appear twice.
  const reloadMessages = useCallback(async () => {
    if (!conversation?.id) return
    try {
      const response = await api.get(
        `${apiBase}/conversations/${conversation.id}?limit=200&offset=0`,
      )
      const raw = (response.data && response.data.messages) || []
      const valid = raw.filter(
        (msg: any) => msg && msg.id && msg.body !== undefined && msg.direction && msg.channel,
      )
      setMessages((prev) => mergeServerMessages(prev, valid as Message[]))
    } catch {
      // Best-effort catch-up — the next focus / realtime event retries.
    }
  }, [conversation?.id, apiBase])

  // Catch up when the tab regains focus (mirrors the list's refetchOnWindowFocus).
  useEffect(() => {
    const onVisible = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        void reloadMessages()
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [reloadMessages])

  useEffect(() => {
    if (messagesEndRef.current && messages.length > 0) {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 300)
    }
  }, [messages])

  // Real-time conversation events via the shared RealtimeClient. Replaces
  // ~240 lines of inline WebSocket setup / message-routing / reconnect /
  // cleanup logic. The client de-dupes connections (two components asking
  // for the same conversation share one socket) and handles reconnect with
  // exponential backoff + visibility awareness internally.
  useRealtime('conversation', conversation?.id, (data) => {
    setWsConnected(true)
    if (data.status === 'subscribed') {
      // Fresh (re)subscription — reconcile in case events were missed while the
      // socket was down. mergeServerMessages dedupes, so this is safe.
      void reloadMessages()
      return
    }
    if (data.error) return
    const type = data.type

    if (type === 'new_message') {
      const eventConvId =
        (data as any).conversation_id ||
        ((data as any).message && (data as any).message.conversation_id)
      const eventConvIdNorm = eventConvId ? String(eventConvId).toLowerCase() : ''
      const currentConvIdNorm = conversation?.id ? String(conversation.id).toLowerCase() : ''
      if (eventConvIdNorm && eventConvIdNorm !== currentConvIdNorm) return
      const m = (data as any).message
      if (!m || !conversation?.id) return

      const newMessage: Message = {
        id: m.id,
        conversation_id: conversation.id,
        body: m.body,
        channel: m.channel,
        direction: m.direction,
        status: m.status || 'delivered',
        author_id: m.author_id,
        author_name: m.author_name,
        created_at: m.created_at,
        sent_at: m.sent_at,
        delivered_at: m.delivered_at,
        provider_message_id: m.provider_message_id,
        is_decision: m.is_decision,
      }

      setMessages((prev) => appendRealtimeMessage(prev, newMessage))

      setTimeout(() => {
        if (onRefresh) onRefresh()
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
      return
    }

    if (type === 'status_update') {
      const m = (data as any).message
      if (m && m.id) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === m.id
              ? {
                  ...msg,
                  status: m.status,
                  ...(m.sent_at && { sent_at: m.sent_at }),
                  ...(m.delivered_at && { delivered_at: m.delivered_at }),
                }
              : msg,
          ),
        )
      }
      return
    }

    if (type === 'ai_conversation_update') {
      const summary = (data as any).ai_summary
      if (typeof summary === 'string' && summary.length > 0) {
        setLiveAiSummary(summary)
      }
      return
    }

    if (type === 'message_flags_update') {
      const m = (data as any).message
      if (m && m.id) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === m.id
              ? {
                  ...msg,
                  ...(m.is_decision !== undefined && { is_decision: m.is_decision }),
                }
              : msg,
          ),
        )
      }
      return
    }

    if (type === 'ai_message_update') {
      const m = (data as any).message
      if (m && m.id) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === m.id
              ? {
                  ...msg,
                  ...(m.ai_tone !== undefined && { ai_tone: m.ai_tone }),
                  ...(m.ai_delta_summary !== undefined && {
                    ai_delta_summary: m.ai_delta_summary,
                  }),
                }
              : msg,
          ),
        )
      }
    }
  })

  const handleUploadFile = async (file: File) => {
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await api.post(
      `${apiBase}/conversations/${conversation.id}/attachments`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      }
)


      return response.data
    } catch (error: any) {
      console.error('Failed to upload file:', error)
      throw new Error(error.response?.data?.detail || 'Failed to upload file')
    }
  }

  const [aiDrafts, setAiDrafts] = useState<{
    professional?: string
    short?: string
    detailed?: string
    summary?: string
    facts?: string[]
  } | null>(null)
  const [aiDraftVariant, setAiDraftVariant] = useState<
    'professional' | 'short' | 'detailed'
  >('professional')
  const [aiLoading, setAiLoading] = useState(false)

  useEffect(() => {
    setAiDrafts(null)
    setAiDraftVariant('professional')
    setAiLoading(false)
  }, [conversation?.id])

  const handleGenerateAiDraft = async () => {
    if (!conversation?.id) return
    try {
      setAiLoading(true)

      const resp = await api.post(
        `${apiBase}/ai/compose-reply`,
        { conversation_id: conversation.id }
      )


      const { drafts, summary, facts } = resp.data || {}
      setAiDrafts({
        professional: drafts?.professional || '',
        short: drafts?.short || '',
        detailed: drafts?.detailed || '',
        summary: summary || '',
        facts: facts || []
      })
      setAiDraftVariant('professional')
    } catch (e) {
      console.error('Failed to generate AI drafts', e)
      alert('Failed to generate AI drafts. Please try again.')
    } finally {
      setAiLoading(false)
    }
  }

  const handleApplyDraftToEditor = (draft: string) => {
    const textarea = document.querySelector<HTMLTextAreaElement>(
      'textarea[placeholder="Type your message here..."]'
    )
    if (textarea) {
      textarea.value = draft
      const event = new Event('input', { bubbles: true })
      textarea.dispatchEvent(event)
      textarea.focus()
    }
  }

  const handleSendMessage = async (messageData: { channel: string; body: string; files?: File[] }) => {
    try {
      // 1) AI pre-send check for email
      if (messageData.channel === 'email' && messageData.body.trim()) {
        try {

          const checkResp = await api.post(
            `${apiBase}/ai/check-message`,
            {
              conversation_id: conversation.id,
              draft_body: messageData.body,
              attachments: (messageData.files || []).map((f) => f.name)
            }
)

          const check = checkResp.data as {
            issues: { type: string; message: string }[]
            okToSend: boolean
          }
          if (check.issues && check.issues.length > 0 && !check.okToSend) {
            const messagesText = check.issues.map((i) => `- ${i.message}`).join('\n')
            const proceed = window.confirm(
              `AI noticed some possible issues before sending:\n\n${messagesText}\n\nPress OK to send anyway, or Cancel to edit the message.`
            )
            if (!proceed) {
              return
            }
          }
        } catch (e) {
          console.warn('AI pre-send check failed, sending anyway', e)
        }
      }

      // 2) Upload files (no message_id yet)
      if (messageData.files && messageData.files.length > 0) {
        for (const file of messageData.files) {
          await handleUploadFile(file)
        }
      }

      // 3) Optimistic UI
      const currentAuthorId = user?.user_id || ''
      const currentAuthorName = user?.name || user?.email || currentAuthorId

      const tempId = `temp-${Date.now()}`
      const optimisticMessage: Message = {
        id: tempId,
        conversation_id: conversation.id,
        body: messageData.body,
        channel: messageData.channel as 'sms' | 'whatsapp' | 'email',
        direction: 'outbound',
        status: 'queued',
        author_id: currentAuthorId,
        author_name: currentAuthorName,
        created_at: new Date().toISOString(),
        sent_at: undefined,
        delivered_at: undefined,
        provider_message_id: undefined,
        is_decision: false
      }

      setMessages((prev) => {
        const updated = [...prev, optimisticMessage].sort(
          (a, b) =>
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        )
        return updated
      })

      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)

      // 4) Send to server
      const response = await api.post(
        `${apiBase}/conversations/${conversation.id}/messages`,
        { channel: messageData.channel, body: messageData.body }
)


      // 5) Link files to real message
      if (messageData.files && messageData.files.length > 0 && response.data.id) {
        for (const file of messageData.files) {
          const formData = new FormData()
          formData.append('file', file)
          formData.append('message_id', response.data.id)

          await api.post(
          `${apiBase}/conversations/${conversation.id}/attachments`,
          formData,
          {
            headers: {
              'Content-Type': 'multipart/form-data'
            }
          }
        )

        }
      }

      const realMessage: Message = {
        id: response.data.id,
        conversation_id: conversation.id,
        body: response.data.body,
        channel: response.data.channel,
        direction: response.data.direction,
        status: response.data.status,
        author_id: response.data.author_id || currentAuthorId,
        author_name: response.data.author_name || currentAuthorName,
        created_at: response.data.created_at,
        sent_at: response.data.sent_at,
        delivered_at: response.data.delivered_at,
        provider_message_id: response.data.provider_message_id,
        is_decision: response.data.is_decision ?? false
      }

      setMessages((prev) => {
        if (prev.some((m) => m.id === realMessage.id)) {
          return prev
            .filter((m) => m.id !== tempId)
            .sort(
              (a, b) =>
                new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
            )
        }

        const filtered = prev.filter((m) => m.id !== tempId)
        const updated = [...filtered, realMessage].sort(
          (a, b) =>
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        )
        return updated
      })

      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)

      setTimeout(() => {
        onRefresh()
      }, 500)
    } catch (error) {
      setMessages((prev) => prev.filter((m) => !m.id.startsWith('temp-')))
      throw error
    }
  }

  const handleMessageSelect = (messageId: string, selected: boolean) => {
    if (selected) {
      setSelectedMessageIds((prev) => [...prev, messageId])
    } else {
      setSelectedMessageIds((prev) => prev.filter((id) => id !== messageId))
    }
  }

  const handleToggleSelectionMode = () => {
    setSelectionMode(!selectionMode)
    if (selectionMode) {
      setSelectedMessageIds([])
    }
  }

  const handleCreateThread = () => {
    if (selectedMessageIds.length > 0) {
      setShowCreateThreadModal(true)
    }
  }

  const handleThreadCreated = () => {
    setSelectionMode(false)
    setSelectedMessageIds([])
    onRefresh()
  }

  const handleCreateTaskFromMessage = (message: Message) => {
    setTaskModalData({ message })
    setShowTaskModal(true)
  }

  // Pin / unpin a message as a decision of record. Optimistic — the realtime
  // `message_flags_update` event reconciles other viewers.
  const handleToggleDecision = async (message: Message) => {
    const next = !message.is_decision
    setMessages((prev) =>
      prev.map((m) => (m.id === message.id ? { ...m, is_decision: next } : m)),
    )
    try {
      await api.patch(
        `${apiBase}/conversations/${conversation.id}/messages/${message.id}/decision`,
        { is_decision: next },
      )
    } catch (err: any) {
      // Roll back on failure.
      setMessages((prev) =>
        prev.map((m) => (m.id === message.id ? { ...m, is_decision: !next } : m)),
      )
      alert(err.response?.data?.detail || 'Failed to update decision')
    }
  }

  // Jump the scroll container to a specific message (used by the Decisions
  // panel and search). Falls back silently if the row isn't mounted.
  const scrollToMessage = (messageId: string) => {
    const el = document.querySelector<HTMLElement>(`[data-message-id="${messageId}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // Conversation-state mutations shared by the compose slash-commands and the
  // right-rail "Suggested actions" buttons, so both paths do the same thing.
  const patchConversationState = async (patch: Record<string, any>) => {
    try {
      const res = await api.patch(`${apiBase}/conversations/${conversation.id}/state`, patch)
      setLocalConversation(res.data)
      onRefresh()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Action failed')
    }
  }

  const handleSnoozeConversation = () => {
    const until = new Date()
    until.setDate(until.getDate() + 1)
    until.setHours(9, 0, 0, 0)
    return patchConversationState({ status: 'snoozed', snooze_until: until.toISOString() })
  }
  const handleResolveConversation = () => patchConversationState({ status: 'resolved' })
  const handleEscalateConversation = () => patchConversationState({ priority: 'urgent' })

  // In-conversation search runs over the full messages array (not the rendered
  // DOM) because the list is virtualized — off-screen rows aren't in the DOM.
  const trimmedQuery = searchQuery.trim().toLowerCase()
  const visibleMessages = trimmedQuery
    ? messages.filter((m) => (m.body || '').toLowerCase().includes(trimmedQuery))
    : messages

  // Decisions of record — explicitly pinned by a user (replaces the old regex).
  const decisions = messages.filter((m) => m.is_decision)

  return (
    <div className="flex flex-col h-full bg-white" style={{ height: '100%', overflow: 'hidden' }}>
      {/* 2px brand-gradient accent strip — gives the canvas a clear page edge. */}
      <div
        className="h-0.5 flex-shrink-0"
        style={{ background: 'linear-gradient(90deg, #168AAD 0%, #76C893 100%)' }}
        aria-hidden="true"
      />
      {/* Header — soft brand-tinted top, fades to white. */}
      {/* Sticky header.
          - `bg-white` (solid, NOT a semi-transparent gradient) so the
            scrolling AI summary / message list never bleeds through and
            covers up the toolbar buttons (Refresh / Hide context, etc.).
          - `z-30` to sit confidently above the InlineAISummary band that
            renders right below and can grow as the AI streams more text.
          - Subtle top accent stripe via `before:` keeps the brand-blue
            visual cue without the transparency that caused the overlap. */}
      <div
        className="relative border-b border-slate-200 bg-white px-6 py-3 flex-shrink-0 shadow-sm sticky top-0 z-30 before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:bg-[#168AAD]/30 before:content-['']"
      >
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-4 flex-1 min-w-0">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 min-w-0">
                <h2 className="text-ui-h1 text-slate-900 truncate">
                  {localConversation.subject || 'Conversation'}
                </h2>
              </div>
              <div className="flex items-center gap-3 text-ui-caption text-slate-500 mt-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    wsConnected ? 'bg-accent-500' : 'bg-danger-500'
                  }`}
                  aria-hidden="true"
                />
                <span>{wsConnected ? 'Connected' : 'Connecting…'}</span>
                {conversation.tracker_code && (
                  <span className="font-mono">{conversation.tracker_code}</span>
                )}
                {conversation.participant_phone && (
                  <span className="truncate">phone {conversation.participant_phone}</span>
                )}
                {conversation.participant_emails && conversation.participant_emails.length > 0 ? (
                  <span className="truncate">to {conversation.participant_emails.join(', ')}</span>
                ) : conversation.participant_email ? (
                  <span className="truncate">to {conversation.participant_email}</span>
                ) : null}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {!selectionMode ? (
              <>
                {effectiveUserId && (
                  <PrivilegedActions
                    conversation={localConversation}
                    currentUserId={effectiveUserId}
                    apiBase={apiBase}
                    onUpdate={onRefresh}
                  />
                )}
                {/* AI Draft + Select are chat-only — drafting a reply or
                    bundling messages into a thread doesn't make sense on a
                    notice board, so hide them on that conversation_type. */}
                {localConversation.conversation_type !== 'notice_board' && (
                  <>
                    {/* AI Summary moved out of the toolbar — it now lives as an
                        always-on InlineAISummary band below the header. */}
                    <button
                      className={TOOLBAR_BTN_CLASS}
                      onClick={handleGenerateAiDraft}
                      disabled={aiLoading}
                      title="Let AI draft a reply for this email thread"
                      aria-label="Generate AI reply draft"
                    >
                      {aiLoading ? (
                        <span className="w-3.5 h-3.5 inline-block border-2 border-current border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <SparkleIcon />
                      )}
                      <span className="hidden sm:inline">{aiLoading ? 'Generating…' : 'AI Draft'}</span>
                    </button>
                    <button
                      className={TOOLBAR_BTN_CLASS}
                      onClick={handleToggleSelectionMode}
                      title="Select messages to create thread"
                      aria-label="Toggle message selection mode"
                    >
                      <CheckboxIcon />
                      <span className="hidden sm:inline">Select</span>
                    </button>
                  </>
                )}
                {localConversation.conversation_type !== 'notice_board' && (
                  <button
                    className={`${TOOLBAR_BTN_CLASS} ${searchOpen ? 'bg-slate-100 border-slate-400' : ''}`}
                    onClick={() => {
                      setSearchOpen((o) => {
                        if (o) setSearchQuery('')
                        return !o
                      })
                    }}
                    title="Search messages in this conversation"
                    aria-label="Search messages"
                    aria-pressed={searchOpen}
                  >
                    <SearchIcon />
                    <span className="hidden sm:inline">Search</span>
                  </button>
                )}
                <button
                  className={TOOLBAR_BTN_CLASS}
                  onClick={() => setRightSidebarOpen((o) => !o)}
                  title={rightSidebarOpen ? 'Hide context panel' : 'Show context panel'}
                  aria-label={rightSidebarOpen ? 'Hide context panel' : 'Show context panel'}
                  aria-pressed={rightSidebarOpen}
                >
                  <SidebarIcon />
                  <span className="hidden sm:inline">{rightSidebarOpen ? 'Hide context' : 'Context'}</span>
                </button>
              </>
            ) : (
              <>
                <button
                  className="px-3 py-1.5 bg-[#168AAD] text-white rounded-lg text-xs font-medium hover:bg-[#1E73BE] disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 whitespace-nowrap transition"
                  onClick={handleCreateThread}
                  disabled={selectedMessageIds.length === 0}
                  title="Create thread from selected messages"
                >
                  <PlusIcon />
                  <span>Create Thread ({selectedMessageIds.length})</span>
                </button>
                <button
                  className={TOOLBAR_BTN_CLASS}
                  onClick={handleToggleSelectionMode}
                  title="Cancel selection"
                >
                  <CloseIcon />
                  <span className="hidden sm:inline">Cancel</span>
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* In-conversation search bar. Operates over the full message array
          (the list is virtualized, so browser find-in-page can't reach
          off-screen rows). */}
      {searchOpen && localConversation.conversation_type !== 'notice_board' && (
        <div className="flex items-center gap-2 px-6 py-2 border-b border-slate-200 bg-white flex-shrink-0">
          <div className="text-slate-400">
            <SearchIcon />
          </div>
          <input
            autoFocus
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setSearchQuery('')
                setSearchOpen(false)
              }
            }}
            placeholder="Search messages…"
            className="flex-1 text-sm bg-transparent focus:outline-none text-slate-900 placeholder-slate-400"
          />
          <span className="text-ui-caption text-slate-500 tabular-nums">
            {trimmedQuery ? `${visibleMessages.length} match${visibleMessages.length !== 1 ? 'es' : ''}` : ''}
          </span>
          <button
            onClick={() => {
              setSearchQuery('')
              setSearchOpen(false)
            }}
            className="text-slate-400 hover:text-slate-600 p-1 rounded hover:bg-slate-100 transition"
            title="Close search"
            aria-label="Close search"
          >
            <CloseIcon />
          </button>
        </div>
      )}

      {/* Always-on AI summary band — replaces the old modal.
          Skipped on notice boards: an LLM-generated "what's this thread
          about" line is meaningless on a stream of system events. */}
      {localConversation.conversation_type !== 'notice_board' && (
        <InlineAISummary
          conversationId={conversation.id}
          apiBase={apiBase}
          messageCount={messages.length}
          initialSummary={localConversation.ai_summary || null}
          liveSummary={liveAiSummary}
        />
      )}

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden min-h-0">
        <div
          ref={messagesScrollRef}
          className="flex-1 overflow-y-auto p-6 min-h-0"
          // Soft warm-cool gradient so the chat canvas reads alive, not clinical.
          // Same palette stops as the app body; just tilted differently.
          style={{
            background:
              'linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%), radial-gradient(at 100% 0%, rgba(118,200,147,0.06), transparent 60%)',
            WebkitOverflowScrolling: 'touch',
          } as any}
        >
          <div className="w-full">
            {error && (
              <div className="mb-4 p-3 bg-red-50 border-2 border-red-200 rounded-lg">
                <p className="text-sm text-red-800 font-semibold">{error}</p>
              </div>
            )}
            {selectionMode && (
              <div className="mb-4 p-3 bg-blue-50 border-2 border-dizzaroo-deep-blue/20 rounded-xl">
                <p className="text-sm text-dizzaroo-deep-blue font-semibold">
                  Selection Mode: Click messages to select them. {selectedMessageIds.length}{' '}
                  message{selectedMessageIds.length !== 1 ? 's' : ''} selected.
                </p>
              </div>
            )}
            {/* Notice board gets its own activity-feed renderer. Regular
                conversations keep the chat-bubble MessageList. Routing here
                (rather than picking a different parent component) keeps
                header / sidebar / refresh / context-toggle behaviour shared
                between the two views. */}
            {localConversation.conversation_type === 'notice_board' ? (
              <NoticeBoardView messages={messages} />
            ) : (
              <>
                {messages.length > 0 && (
                  <div className="mb-2 text-xs text-gray-500">
                    {trimmedQuery
                      ? `${visibleMessages.length} of ${messages.length} message${messages.length !== 1 ? 's' : ''} match`
                      : `Showing ${messages.length} message${messages.length !== 1 ? 's' : ''}`}
                  </div>
                )}
                {trimmedQuery && visibleMessages.length === 0 ? (
                  <div className="text-center py-10 text-sm text-gray-500">
                    No messages match “{searchQuery.trim()}”.
                  </div>
                ) : (
                  <MessageList
                    messages={visibleMessages}
                    onMessageSelect={handleMessageSelect}
                    selectedMessageIds={selectedMessageIds}
                    selectionMode={selectionMode}
                    apiBase={apiBase}
                    conversationId={conversation.id}
                    scrollParentRef={messagesScrollRef}
                    onCreateTask={handleCreateTaskFromMessage}
                    onToggleDecision={handleToggleDecision}
                  />
                )}
              </>
            )}

            {/* AI drafts panel */}
            {aiDrafts && (aiDrafts.professional || aiDrafts.short || aiDrafts.detailed) && (
              <div className="mt-4">
                <div className="bg-white border border-dizzaroo-deep-blue/20 rounded-xl p-3 shadow-sm">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                      <span>🤖 AI Drafts</span>
                    </h3>
                    <div className="flex items-center gap-2">
                      <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden text-xs">
                        <button
                          type="button"
                          className={`px-2 py-1 font-semibold ${
                            aiDraftVariant === 'professional'
                              ? 'bg-dizzaroo-deep-blue text-white'
                              : 'bg-white text-gray-700'
                          }`}
                          onClick={() => setAiDraftVariant('professional')}
                        >
                          Professional
                        </button>
                        <button
                          type="button"
                          className={`px-2 py-1 font-semibold border-l border-gray-200 ${
                            aiDraftVariant === 'short'
                              ? 'bg-dizzaroo-blue-green text-white'
                              : 'bg-white text-gray-700'
                          }`}
                          onClick={() => setAiDraftVariant('short')}
                        >
                          Short
                        </button>
                        <button
                          type="button"
                          className={`px-2 py-1 font-semibold border-l border-gray-200 ${
                            aiDraftVariant === 'detailed'
                              ? 'bg-dizzaroo-soft-green text-white'
                              : 'bg-white text-gray-700'
                          }`}
                          onClick={() => setAiDraftVariant('detailed')}
                        >
                          Detailed
                        </button>
                      </div>
                      <button
                        type="button"
                        className="ml-2 text-xs px-2 py-1 rounded-md bg-gray-100 text-gray-600 hover:bg-gray-200"
                        onClick={() => setAiDrafts(null)}
                        title="Hide AI drafts for this conversation"
                      >
                        ✕ Close
                      </button>
                    </div>
                  </div>
                  <div className="border-t border-gray-200 pt-2 text-sm text-gray-800 whitespace-pre-line">
                    {aiDraftVariant === 'professional' && aiDrafts.professional}
                    {aiDraftVariant === 'short' && aiDrafts.short}
                    {aiDraftVariant === 'detailed' && aiDrafts.detailed}
                  </div>
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      className="px-3 py-1.5 bg-dizzaroo-deep-blue text-white rounded-lg text-xs font-semibold hover:bg-dizzaroo-blue-green"
                      onClick={() => {
                        const draft =
                          aiDraftVariant === 'professional'
                            ? aiDrafts.professional
                            : aiDraftVariant === 'short'
                            ? aiDrafts.short
                            : aiDrafts.detailed
                        handleApplyDraftToEditor(draft || '')
                      }}
                    >
                      Use this draft in editor
                    </button>
                  </div>
                  {/* Key facts that informed the draft. The summary itself is
                      intentionally NOT repeated here — it already lives in the
                      always-on InlineAISummary band above the messages. */}
                  {aiDrafts.facts && aiDrafts.facts.length > 0 && (
                    <div className="mt-3 border-t border-gray-200 pt-2">
                      <h5 className="text-xs font-semibold text-gray-700 mb-1">Key facts used</h5>
                      <ul className="list-disc list-inside space-y-0.5 text-xs text-gray-700">
                        {aiDrafts.facts.map((f, idx) => (
                          <li key={idx}>{f}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        <ConversationRightSidebar
          conversation={localConversation}
          messages={messages}
          apiBase={apiBase}
          conversationId={conversation.id}
          isOpen={rightSidebarOpen}
          onToggle={() => setRightSidebarOpen(!rightSidebarOpen)}
          decisions={decisions}
          onUnpinDecision={(m) => handleToggleDecision(m)}
          onJumpToMessage={scrollToMessage}
          actions={{
            onFollowUp: handleGenerateAiDraft,
            onCreateTask: () =>
              handleCreateTaskFromMessage(messages[messages.length - 1]),
            onSnooze: handleSnoozeConversation,
            onResolve: handleResolveConversation,
            onEscalate: handleEscalateConversation,
          }}
        />
      </div>

      {/* Send form — the Public Notice Board is a system-only activity feed,
          so swap the compose box for a read-only banner. Backend also rejects
          POST /messages on a notice_board conversation, so this is purely
          a UX affordance — server is the source of truth. */}
      {localConversation.conversation_type === 'notice_board' ? (
        <div className="bg-gray-50 border-t border-gray-200 flex-shrink-0">
          <div className="px-6 py-3 w-full text-center text-sm text-gray-500 italic">
            This is the Public Notice Board — system updates appear here automatically. Posting is disabled.
          </div>
        </div>
      ) : (
      <div className="bg-white border-t border-gray-200 shadow-lg flex-shrink-0">
        <div className="px-6 py-4 w-full">
          <SendMessageForm
            onSend={handleSendMessage}
            onUploadFile={handleUploadFile}
            participantName={
              localConversation.participant_emails?.[0]?.split('@')[0] ||
              localConversation.participant_email?.split('@')[0]
            }
            // Static AI hint — Phase-2. A real streaming completion would
            // replace this with a debounced model call. For now we surface the
            // first 120 chars of the persisted AI summary as a one-tap accept.
            aiHint={(() => {
              const src = liveAiSummary || localConversation.ai_summary
              if (!src) return null
              const firstLine = src.split('\n').find((l) => l.trim().length > 0) || ''
              return firstLine.length > 160 ? firstLine.slice(0, 160) + '…' : firstLine
            })()}
            onSlashCommand={async (cmd) => {
              try {
                if (cmd.kind === 'snooze') {
                  await handleSnoozeConversation()
                } else if (cmd.kind === 'resolve') {
                  await handleResolveConversation()
                } else if (cmd.kind === 'escalate') {
                  await handleEscalateConversation()
                } else if (cmd.kind === 'task') {
                  // Open the task creation modal pre-filled from the latest message.
                  setTaskModalData({ message: messages[messages.length - 1] || null })
                  setShowTaskModal(true)
                } else if (cmd.kind === 'summary') {
                  // Already rendered as the inline band — nothing to do here.
                }
              } catch (err: any) {
                console.error('Slash command failed:', err)
                alert(err.response?.data?.detail || 'Command failed')
              }
            }}
          />
        </div>
      </div>
      )}

      {/* Create Thread Modal */}
      {showCreateThreadModal && (
        <CreateThreadFromConversation
          conversationId={conversation.id}
          messages={messages}
          selectedMessageIds={selectedMessageIds}
          onClose={() => setShowCreateThreadModal(false)}
          onSuccess={handleThreadCreated}
          apiBase={apiBase}
        />
      )}

      {/* Task Form Modal */}
      {showTaskModal && taskModalData && (
        <TaskFormModal
          isOpen={showTaskModal}
          onClose={() => {
            setShowTaskModal(false)
            setTaskModalData(null)
          }}
          onTaskCreated={(task) => {
            console.log('Task created:', task)
            setShowTaskModal(false)
            setTaskModalData(null)
          }}
          initialTitle={taskModalData.message ? truncate(taskModalData.message.body, 80) : ''}
          initialDescription={taskModalData.message?.body || ''}
          defaultLinks={{
            conversationId: conversation.id,
            messageId: taskModalData.message?.id,
            siteId: conversation.site_id
          }}
          apiBase={apiBase}
        />
      )}
    </div>
  )
}

// Helper function to truncate text
function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength - 3) + '...'
}

export default ConversationDetail