import React, { useState, useEffect, useRef, FormEvent } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useStudySite } from '@/contexts/StudySiteContext'
import { api } from '@/lib/api'
import { useRealtime } from '@/lib/realtime'
import AISummary from '@/features/ai/components/AISummary'
import AttachmentDisplay from '@/components/AttachmentDisplay'
import UserPicker from '@/components/UserPicker'
import { Thread, ThreadMessage, ThreadParticipant, ThreadAttachment } from '@/types'

interface ThreadDetailProps {
  thread: Thread
  onRefresh: () => void
  apiBase: string
  currentUserId?: string
  currentUserName?: string
}

const ThreadDetail: React.FC<ThreadDetailProps> = ({
  thread,
  onRefresh,
  apiBase,
  currentUserId: propCurrentUserId,
  currentUserName: propCurrentUserName
}) => {
  const { user } = useAuth()
  const { selectedSiteId } = useStudySite()
  const currentUserId = propCurrentUserId || user?.user_id || ''
  const currentUserName =
    propCurrentUserName || user?.name || user?.email || currentUserId
  const currentUserEmail = (user?.email || '').toLowerCase()

  // Check if current user is the creator (created_by can be user_id, email, or display name)
  const createdByLower = String(thread.created_by || '').toLowerCase()
  const isCreator =
    !!thread.created_by &&
    (
      // Match by email
      createdByLower === currentUserEmail ||
      createdByLower === String(user?.email || '').toLowerCase() ||
      // Match by user ids
      createdByLower === String(currentUserId).toLowerCase() ||
      createdByLower === String(user?.user_id || '').toLowerCase() ||
      // Match by display name (e.g. "001")
      createdByLower === String(user?.name || '').toLowerCase() ||
      createdByLower === String(propCurrentUserName || '').toLowerCase()
    )

  // Human-readable label for who started the thread — resolve created_by to a
  // name/email and NEVER render a raw user id.
  const createdByLabel = (() => {
    if (!thread.created_by) return null
    if (isCreator) return 'you'
    const cb = String(thread.created_by)
    const match = (thread.participants || []).find(
      (p) =>
        String(p.participant_id || '') === cb ||
        String(p.participant_email || '').toLowerCase() === cb.toLowerCase(),
    )
    if (match?.participant_name) return match.participant_name
    if (match?.participant_email) return match.participant_email
    if (cb.includes('@')) return cb // an email is already human-readable
    return 'a team member' // raw id → generic label, never shown raw
  })()

  // Normalize visibility scope. Any non-"site" value is treated as private.
  const visibilityScope = (thread.visibility_scope || '').toLowerCase().trim()
  const isSiteThread = visibilityScope === 'site'
  const isPrivateThread = !isSiteThread

  const [messages, setMessages] = useState<ThreadMessage[]>([])
  const [newMessage, setNewMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [participants, setParticipants] = useState<ThreadParticipant[]>(
    thread.participants || []
  )
  const [participantsEmails, setParticipantsEmails] = useState<string[]>(
    thread.participants_emails || []
  )
  const [showParticipantSettings, setShowParticipantSettings] = useState(false)
  const [attachmentsMap, setAttachmentsMap] = useState<
    Record<string, ThreadAttachment[]>
  >({})
  const [tmfFiling, setTmfFiling] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  // Sync TMF filing state when thread prop changes
  useEffect(() => {
    if (thread?.tmf_filed !== undefined) {
      setTmfFiling(thread.tmf_filed)
    }
  }, [thread?.tmf_filed])

  // Sync participants_emails when thread prop changes
  useEffect(() => {
    if (thread?.participants_emails) {
      setParticipantsEmails(thread.participants_emails)
    }
  }, [thread?.participants_emails])

  useEffect(() => {
    const fetchMessages = async () => {
      if (!thread?.id) {
        setLoadingMessages(false)
        setMessages([])
        setParticipants([])
        return
      }

      setMessages([])
      setLoadingMessages(true)

      try {
        const response = await api.get(
          `/threads/${thread.id}?limit=200&offset=0`
        )

        if (Array.isArray(response.data?.messages)) {
          const sortedMessages = [...response.data.messages].sort(
            (a, b) =>
              new Date(a.created_at).getTime() -
              new Date(b.created_at).getTime()
          )
          setMessages(sortedMessages)
        } else {
          setMessages([])
        }

        if (Array.isArray(response.data?.participants)) {
          setParticipants(response.data.participants)
        } else {
          setParticipants([])
        }

        // Update participants_emails
        if (Array.isArray(response.data?.participants_emails)) {
          setParticipantsEmails(response.data.participants_emails)
        } else {
          setParticipantsEmails([])
        }

        // Update TMF filing status
        if (response.data?.tmf_filed !== undefined) {
          setTmfFiling(response.data.tmf_filed)
        }
      } catch (error) {
        console.error('Failed to fetch thread messages:', error)
        setMessages([])
        setParticipants([])
      } finally {
        setLoadingMessages(false)
      }
    }

    const fetchAttachments = async () => {
      if (!thread?.id) return

      try {
        const response = await api.get(`/threads/${thread.id}/attachments`)
        const threadAttachments: ThreadAttachment[] = response.data || []

        const grouped: Record<string, ThreadAttachment[]> = {}
        threadAttachments.forEach(att => {
          if (att.thread_message_id) {
            if (!grouped[att.thread_message_id]) {
              grouped[att.thread_message_id] = []
            }
            grouped[att.thread_message_id].push(att)
          }
        })

        setAttachmentsMap(grouped)
      } catch (error) {
        console.error('Failed to fetch thread attachments:', error)
      }
    }

    fetchMessages()
    fetchAttachments()
  }, [thread?.id])

  // Live updates: subscribe to the thread channel via the shared
  // RealtimeClient. One socket, deduped across components, automatic
  // reconnect with exponential backoff + visibility awareness. Replaces
  // ~100 lines of inline WebSocket setup / message-handling / cleanup.
  useRealtime('thread', thread?.id, (data) => {
    if ((data as any).error) {
      console.error('Thread WebSocket error:', (data as any).error)
      return
    }
    if (data.type !== 'new_thread_message') return
    const m = (data as any).message
    if (!m || !thread?.id) return

    const eventThreadId = (data as any).thread_id
      ? String((data as any).thread_id).toLowerCase()
      : ''
    const currentThreadId = thread.id ? String(thread.id).toLowerCase() : ''
    if (eventThreadId && eventThreadId !== currentThreadId) return

    const incoming: ThreadMessage = {
      id: m.id,
      thread_id: thread.id,
      body: m.body,
      author_id: m.author_id,
      author_name: m.author_name,
      created_at: m.created_at,
    } as ThreadMessage

    setMessages((prev) => {
      if (prev.some((p) => p.id === incoming.id)) return prev
      return [...prev, incoming].sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
    })
  })

  useEffect(() => {
    if (messagesEndRef.current && messages.length > 0) {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 300)
    }
  }, [messages])

  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedFiles(prev => [...prev, ...Array.from(e.target.files!)])
    }
  }

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleUploadFile = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post(
      `/threads/${thread.id}/attachments`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    return response.data
  }

  const handleSendMessage = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!newMessage.trim() && selectedFiles.length === 0) return

    const messageText = newMessage.trim()
    const filesToUpload = [...selectedFiles]

    setNewMessage('')
    setSelectedFiles([])
    if (fileInputRef.current) fileInputRef.current.value = ''

    try {
      setLoading(true)

      for (const file of filesToUpload) {
        await handleUploadFile(file)
      }

      const response = await api.post(`/threads/${thread.id}/messages`, {
        body: messageText || '📎 File attached',
        author_id: currentUserId,
        author_name: currentUserName
      })

      const newMsg: ThreadMessage = {
        id: response.data.id,
        thread_id: thread.id,
        body: response.data.body,
        author_id: response.data.author_id,
        author_name: response.data.author_name || currentUserName,
        created_at: response.data.created_at
      }

      setMessages(prev =>
        [...prev, newMsg].sort(
          (a, b) =>
            new Date(a.created_at).getTime() -
            new Date(b.created_at).getTime()
        )
      )

      setTimeout(onRefresh, 1000)
    } catch (error) {
      console.error('Failed to send message:', error)
      alert('Failed to send message. Please try again.')
      setNewMessage(messageText)
      setSelectedFiles(filesToUpload)
    } finally {
      setLoading(false)
    }
  }

  const handleParticipantsChange = async (emails: string[]) => {
    // Only creator can manage participants
    if (!isCreator) {
      alert('Only the thread creator can manage participants.')
      return
    }
    
    // Only allow participant management for private threads
    if (!isPrivateThread) {
      alert('Participant management is only available for private threads. Site-visible threads are accessible to all site users.')
      return
    }

    // Ensure current user (creator) cannot be removed
    const finalEmails = [
      ...new Set([
        currentUserEmail,
        ...emails
      ].filter(Boolean))
    ]

    try {
      // Get current participants_emails
      const currentEmails = participantsEmails || []
      
      // Find emails to add and remove
      const toAdd = finalEmails.filter(e => !currentEmails.includes(e))
      const toRemove = currentEmails.filter(e => !finalEmails.includes(e) && e !== currentUserEmail)
      
      // Add new participants
      for (const email of toAdd) {
        await api.post(`/threads/${thread.id}/participants/emails`, { email })
      }
      
      // Remove participants
      for (const email of toRemove) {
        await api.delete(`/threads/${thread.id}/participants/emails/${encodeURIComponent(email)}`)
      }
      
      onRefresh()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to update participants. Please try again.')
    }
  }

  const handleRemoveParticipantEmail = async (email: string) => {
    // Only creator can remove participants
    if (!isCreator) {
      alert('Only the thread creator can remove participants.')
      return
    }
    
    // Only allow participant management for private threads
    if (!isPrivateThread) {
      alert('Participant management is only available for private threads.')
      return
    }

    if (!confirm(`Remove ${email} from this thread?`)) return

    try {
      await api.delete(`/threads/${thread.id}/participants/emails/${encodeURIComponent(email)}`)
      onRefresh()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to remove participant email. Please try again.')
    }
  }

  const handleStatusChange = async (newStatus: string) => {
    await api.patch(`/threads/${thread.id}/status`, { status: newStatus })
    onRefresh()
  }

  // The "File in TMF" UI control was removed: the backend TMF integration is a
  // placeholder (no real filing), so surfacing a compliance action it doesn't
  // perform is misleading. The backend route stays dormant for the future real
  // integration; the `tmf_filed` badge below remains as a read-only indicator.

  // --- helpers unchanged below ---



  const formatTime = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    
    return date.toLocaleString([], { 
      month: 'short', 
      day: 'numeric', 
      hour: '2-digit', 
      minute: '2-digit' 
    })
  }

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    if (date.toDateString() === today.toDateString()) {
      return 'Today'
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday'
    } else {
      return date.toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' })
    }
  }

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'open': return 'bg-green-500'
      case 'in_progress': return 'bg-blue-500'
      case 'resolved': return 'bg-gray-500'
      case 'closed': return 'bg-red-500'
      default: return 'bg-gray-500'
    }
  }

  const getPriorityColor = (priority: string): string => {
    switch (priority) {
      case 'urgent': return 'bg-red-500'
      case 'high': return 'bg-orange-500'
      case 'medium': return 'bg-yellow-500'
      case 'low': return 'bg-green-500'
      default: return 'bg-gray-500'
    }
  }

  const mentionEmailRegex = /@([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g

  const extractMentionedEmails = (message: ThreadMessage): string[] => {
    const fromField = (message.mentioned_emails || [])
      .map((e) => String(e).trim().toLowerCase())
      .filter(Boolean)
    const fromBodyMatches = Array.from((message.body || '').matchAll(mentionEmailRegex))
      .map((m) => (m[1] || '').trim().toLowerCase())
      .filter(Boolean)
    return Array.from(new Set([...fromField, ...fromBodyMatches]))
  }

  const getDisplayBody = (message: ThreadMessage): string => {
    const cleaned = (message.body || '')
      .replace(mentionEmailRegex, '')
      .replace(/[ \t]{2,}/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
    return cleaned || 'Message sent'
  }

  // Generate a consistent color for each user based on their ID (same as MessageList)
  const getUserColor = (authorId: string | undefined): string => {
    if (!authorId) return '#667eea' // Default color if no author
    
    // Hash function to convert user_id to a number
    let hash = 0
    for (let i = 0; i < authorId.length; i++) {
      hash = authorId.charCodeAt(i) + ((hash << 5) - hash)
    }
    
    // Generate a color from the hash
    // Using a palette of distinct, vibrant colors that work well with white text
    const colors = [
      '#667eea', // Indigo
      '#f093fb', // Pink
      '#4facfe', // Blue
      '#43e97b', // Green
      '#fa709a', // Rose
      '#f6a523', // Orange (darker for contrast)
      '#30cfd0', // Cyan
      '#00cec9', // Teal
      '#ff6b6b', // Coral Red
      '#feca57', // Yellow Orange
      '#c471ed', // Purple
      '#12c2e9', // Sky Blue
      '#ffd93d', // Gold (darker)
      '#4ecdc4', // Turquoise
      '#a1c4fd', // Periwinkle
      '#ff8a80', // Light Red
      '#84fab0', // Mint
      '#a8caba', // Sage
      '#ff6b9d', // Pink Red
      '#c44569', // Deep Pink
      '#6c5ce7', // Purple Blue
      '#00b894', // Green Teal
      '#e17055', // Orange Red
      '#0984e3', // Blue
      '#2d3436', // Dark Gray (for contrast)
    ]
    
    // Use modulo to select a color from the palette
    const colorIndex = Math.abs(hash) % colors.length
    return colors[colorIndex]
  }

  // Generate a darker shade for gradient (better contrast)
  const getDarkerColor = (color: string): string => {
    // Convert hex to RGB
    const hex = color.replace('#', '')
    if (hex.length !== 6) return color // Fallback if invalid hex
    
    const r = parseInt(hex.substring(0, 2), 16)
    const g = parseInt(hex.substring(2, 4), 16)
    const b = parseInt(hex.substring(4, 6), 16)
    
    // Darken by 25% for better gradient effect
    const darkerR = Math.max(0, Math.floor(r * 0.75))
    const darkerG = Math.max(0, Math.floor(g * 0.75))
    const darkerB = Math.max(0, Math.floor(b * 0.75))
    
    // Convert back to hex
    return `#${darkerR.toString(16).padStart(2, '0')}${darkerG.toString(16).padStart(2, '0')}${darkerB.toString(16).padStart(2, '0')}`
  }

  // Group messages by date
  const groupedMessages: Record<string, ThreadMessage[]> = {}
  messages.forEach(msg => {
    const dateKey = new Date(msg.created_at).toDateString()
    if (!groupedMessages[dateKey]) {
      groupedMessages[dateKey] = []
    }
    groupedMessages[dateKey].push(msg)
  })

  return (
    <div className="flex flex-col h-full bg-white" style={{ height: '100%', overflow: 'hidden' }}>
      {/* Action Ribbon - Clean, Compact Header (matching ConversationDetail) */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex-shrink-0 shadow-sm sticky top-0 z-10">
        <div className="flex items-center justify-between w-full">
          {/* Left: Thread Title & Info */}
          <div className="flex items-center gap-4 flex-1 min-w-0">
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-gray-900 truncate">
                {thread.title}
              </h2>
              <div className="flex items-center gap-2 flex-wrap text-xs text-gray-500 mt-0.5">
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold text-white ${getStatusColor(thread.status)}`}>
                  {thread.status}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold text-white ${getPriorityColor(thread.priority)}`}>
                  {thread.priority}
                </span>
                {(tmfFiling || thread.tmf_filed) && (
                  <span className="px-2 py-0.5 rounded-full text-xs font-bold text-white bg-purple-600">
                    📁 Filed in TMF
                  </span>
                )}
                {thread.related_patient_id && (
                  <span>👤 {thread.related_patient_id}</span>
                )}
                {createdByLabel && (
                  <span>🧵 Started by {createdByLabel}</span>
                )}
                {isSiteThread ? (
                  <span className="px-2 py-0.5 rounded-full text-xs font-bold text-white bg-blue-500">
                    🌐 Site
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-full text-xs font-bold text-white bg-gray-600">
                    🔐 Private
                  </span>
                )}
              </div>
            </div>
          </div>
          
          {/* Right: Action Buttons */}
          <div className="flex items-center gap-2.5 flex-shrink-0">
            {/* Participant Management - Only show for creator on private threads */}
            {isCreator && isPrivateThread && (
              <button
                onClick={() => setShowParticipantSettings(!showParticipantSettings)}
                className="px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded-lg transition text-xs font-medium hover:bg-gray-50 hover:border-gray-400 whitespace-nowrap"
                title="Manage participants (Creator only - Private threads)"
              >
                👥 <span className="hidden sm:inline">Manage Access</span>
              </button>
            )}
            <AISummary
              threadId={thread.id}
              apiBase={apiBase}
              type="thread"
            />
            <select
              value={thread.status} 
              onChange={(e) => handleStatusChange(e.target.value)}
              className="px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded-lg transition text-xs font-medium hover:bg-gray-50 hover:border-gray-400 focus:outline-none whitespace-nowrap"
            >
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
          </div>
        </div>
      </div>

      {/* MESSAGES AREA - TAKES MOST SPACE */}
      <div className="flex-1 flex flex-col overflow-hidden bg-white" style={{ minHeight: 0 }}>
        <div className="px-4 py-2 border-b border-gray-200 bg-gray-50 flex-shrink-0">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-700">
              💬 Messages {loadingMessages ? '(Loading...)' : `(${messages.length})`}
            </h3>
            {(participants.length > 0 || participantsEmails.length > 0) && (
              <span className="text-xs text-gray-500">
                👥 {participants.length + participantsEmails.length} participant{participants.length + participantsEmails.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>

        {/* Participant Settings Panel */}
        {showParticipantSettings && (
          <div className="px-4 py-3 border-b border-gray-200 bg-white flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-gray-700">Manage Participants</h4>
              <button
                onClick={() => setShowParticipantSettings(false)}
                className="text-gray-500 hover:text-gray-700 text-sm"
              >
                ✕
              </button>
            </div>
            
            {/* Current Participant Emails */}
            {participantsEmails.length > 0 && (
              <div className="mb-3">
                <label className="text-xs font-medium text-gray-600 mb-1 block">Participant Emails:</label>
                <div className="flex flex-wrap gap-2">
                  {participantsEmails.map((email, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-1 px-2 py-1 bg-gray-100 rounded text-xs text-gray-700"
                    >
                      <span>{email}</span>
                      {/* Only creator can remove participants (for private threads only) */}
                      {isCreator && isPrivateThread && email.toLowerCase() !== currentUserEmail && (
                        <button
                          onClick={() => handleRemoveParticipantEmail(email)}
                          className="text-red-600 hover:text-red-800 font-bold"
                          title="Remove participant"
                        >
                          ×
                        </button>
                      )}
                      {email.toLowerCase() === currentUserEmail && (
                        <span className="text-xs text-gray-500 italic">(Creator)</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Add/Remove Participants - Only creator can manage (for private threads only) */}
            {isCreator && isPrivateThread && (
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Add or Remove Participants:</label>
                <UserPicker
                  selectedUserEmails={participantsEmails}
                  onSelectionChange={handleParticipantsChange}
                  siteId={selectedSiteId || undefined}
                  excludeEmails={[currentUserEmail]}  // Exclude current user from picker (they're auto-included)
                  placeholder="Search users by name or email..."
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Only you (the creator) can add or remove participants from this private thread.
                </p>
              </div>
            )}
            
            {/* Info for site-visible threads */}
            {isCreator && thread.visibility_scope === 'site' && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-xs text-blue-800">
                  <strong>Site-Visible Thread:</strong> All users in this study/site can view this thread. 
                  Participant management is not available for site-visible threads.
                </p>
              </div>
            )}
          </div>
        )}
        
        <div 
          ref={messagesContainerRef}
          className="flex-1 overflow-y-auto p-4 bg-gradient-to-b from-gray-50 to-white"
          style={{ 
            minHeight: 0,
            overflowY: 'auto',
            WebkitOverflowScrolling: 'touch'
          }}
        >
          {loadingMessages ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="animate-spin text-5xl mb-4">⏳</div>
                <p className="text-lg font-semibold text-gray-600">Loading messages...</p>
              </div>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex items-center justify-center h-full min-h-[500px]">
              <div className="text-center">
                <div className="text-8xl mb-6">💬</div>
                <p className="text-2xl font-bold text-gray-700 mb-2">No messages yet</p>
                <p className="text-base text-gray-500">Start the conversation below!</p>
        </div>
            </div>
          ) : (
            <div className="max-w-5xl mx-auto pr-4 space-y-6">
              {Object.entries(groupedMessages).map(([dateKey, dateMessages]) => (
                <div key={dateKey} className="space-y-3">
                  <div className="text-center py-2">
                    <span className="px-4 py-1.5 bg-white border-2 border-gray-300 text-gray-600 text-xs font-bold uppercase tracking-wider rounded-full shadow-sm">
                      {formatDate(dateMessages[0].created_at)}
                    </span>
                  </div>
                  {dateMessages.map((message, idx) => {
                    const isSystemMessage = message.message_type === 'system' || message.author_id === 'system'
                    const isCurrentUser = message.author_id === currentUserId
                    const showAvatar = idx === 0 || dateMessages[idx - 1].author_id !== message.author_id
                    // Check if this message came from a merged thread
                    const isFromMergedThread = (message as any).original_thread_id && (message as any).original_thread_id !== thread.id
                    // Check if this is the first message from a merged thread (initial message)
                    const isFirstFromMergedThread = isFromMergedThread && (
                      idx === 0 || 
                      !(dateMessages[idx - 1] as any).original_thread_id || 
                      (dateMessages[idx - 1] as any).original_thread_id !== (message as any).original_thread_id
                    )
                    
                    // System messages are displayed centered with special styling
                    if (isSystemMessage) {
                      return (
                        <div key={message.id} className="flex justify-center my-4">
                          <div className="bg-purple-100 border-2 border-purple-300 rounded-lg px-4 py-2 max-w-md text-center">
                            <div className="text-xs font-semibold text-purple-800 mb-1">📁 System</div>
                            <div className="text-sm text-purple-900">{message.body}</div>
                            <div className="text-xs text-purple-600 mt-1">{formatTime(message.created_at)}</div>
                          </div>
                        </div>
                      )
                    }
                    
                    return (
                      <div 
                        key={message.id} 
                        className={`flex gap-3 ${isCurrentUser ? 'flex-row-reverse' : 'flex-row'}`}
                      >
                        {/* Avatar */}
                        {showAvatar && (
                          <div 
                            className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-md"
                            style={{ backgroundColor: getUserColor(message.author_id) }}
                          >
                            {message.author_name?.[0]?.toUpperCase() || '👤'}
                          </div>
                        )}
                        {!showAvatar && <div className="w-10 flex-shrink-0"></div>}
                        
                        {/* Message Bubble */}
                        <div className={`flex-1 max-w-[70%] ${isCurrentUser ? 'items-end' : 'items-start'} flex flex-col`}>
                          {/* Show indicator for merged thread initial messages */}
                          {isFirstFromMergedThread && (
                            <div className={`text-xs font-semibold mb-1 px-2 py-1 bg-blue-100 text-blue-800 rounded-lg border border-blue-300 ${isCurrentUser ? 'text-right ml-auto' : 'text-left'}`}>
                              🔗 Initial message from merged thread
                            </div>
                          )}
                          {showAvatar && (
                            <div className={`text-xs font-semibold mb-1 px-1 ${isCurrentUser ? 'text-right' : 'text-left'}`}>
                              {isCurrentUser ? 'You' : (message.author_name || 'Unknown')}
                            </div>
                          )}
                          <div 
                            className={`rounded-2xl px-4 py-3 shadow-lg ${
                              isCurrentUser 
                                ? 'text-white rounded-br-sm' 
                                : 'bg-white text-gray-800 border-2 border-gray-200 rounded-bl-sm'
                            } ${isFromMergedThread ? 'border-l-4 border-l-blue-400' : ''}`}
                            style={isCurrentUser ? {
                              background: `linear-gradient(135deg, ${getUserColor(message.author_id)} 0%, ${getDarkerColor(getUserColor(message.author_id))} 100%)`
                            } : {}}
                          >
                            <div className={`text-base leading-relaxed whitespace-pre-wrap break-words ${
                              isCurrentUser ? 'text-white' : 'text-gray-800'
                            }`}>
                              {getDisplayBody(message)}
                            </div>
                            {extractMentionedEmails(message).length > 0 && (
                              <div className={`mt-1 text-xs ${isCurrentUser ? 'text-white/80' : 'text-gray-600'}`}>
                                Sent to: {extractMentionedEmails(message).join(', ')}
                              </div>
                            )}
                            {/* Display attachments */}
                            {attachmentsMap[message.id] && attachmentsMap[message.id].length > 0 && (
                              <div className="mt-2 space-y-2">
                                {attachmentsMap[message.id].map((ta) => {
                                  if (ta.attachment) {
                                    return (
                                      <AttachmentDisplay
                                        key={ta.id}
                                        attachment={ta.attachment}
                                        apiBase={apiBase}
                                        isOutbound={isCurrentUser}
                                      />
                                    )
                                  }
                                  return null
                                })}
                              </div>
                            )}
                            {/* Also check message.attachments if available from API */}
                            {message.attachments && message.attachments.length > 0 && (
                              <div className="mt-2 space-y-2">
                                {message.attachments.map((ta) => {
                                  if (ta.attachment) {
                                    return (
                                      <AttachmentDisplay
                                        key={ta.id}
                                        attachment={ta.attachment}
                                        apiBase={apiBase}
                                        isOutbound={isCurrentUser}
                                      />
                                    )
                                  }
                                  return null
                                })}
                              </div>
                            )}
                            <div className={`text-xs mt-2 ${isCurrentUser ? 'text-white/70' : 'text-gray-500'}`}>
                              {formatTime(message.created_at)}
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* SEND MESSAGE FORM - FIXED AT BOTTOM */}
      <div className="bg-white border-t-2 border-gray-300 shadow-2xl flex-shrink-0">
        <div className="px-4 py-3 max-w-5xl mx-auto pr-8">
          <form onSubmit={handleSendMessage} className="flex gap-3 items-end">
            <div className="flex-1">
              {selectedFiles.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
                  {selectedFiles.map((file, index) => (
                    <div key={`${file.name}-${file.size}-${file.lastModified}-${index}`} className="flex items-center gap-2 bg-dizzaroo-deep-blue/10 border border-dizzaroo-deep-blue/30 rounded-xl px-3 py-1.5 text-sm">
                      <span className="text-dizzaroo-deep-blue">📎 {file.name}</span>
                      <button
                        type="button"
                        onClick={() => removeFile(index)}
                        className="text-dizzaroo-deep-blue hover:text-dizzaroo-blue-green font-bold"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
          <textarea
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
                placeholder="Type your message here..."
                className="w-full px-4 py-3 border-2 border-gray-300 rounded-xl text-base focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue resize-none shadow-sm transition"
                rows={2}
            disabled={loading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSendMessage(e as any)
                  }
                }}
              />
            </div>
            <div className="flex-shrink-0">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                id="thread-file-upload"
              />
              <label
                htmlFor="thread-file-upload"
                className="px-4 py-3 bg-gray-100 hover:bg-gray-200 rounded-xl cursor-pointer transition flex items-center justify-center"
                title="Upload file"
              >
                📎
              </label>
            </div>
          <button 
            type="submit" 
              className={`px-6 py-3 rounded-xl font-bold text-sm uppercase tracking-wide shadow-lg transition-all transform flex-shrink-0 ${
                loading || (!newMessage.trim() && selectedFiles.length === 0)
                  ? 'bg-gray-400 text-gray-200 cursor-not-allowed'
                  : 'bg-dizzaroo-deep-blue text-white hover:bg-dizzaroo-blue-green hover:shadow-xl hover:scale-105 active:scale-95'
              }`}
              disabled={loading || (!newMessage.trim() && selectedFiles.length === 0)}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="animate-spin">⏳</span>
                  <span className="hidden sm:inline">Sending...</span>
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <span className="text-lg">📤</span>
                  <span className="hidden sm:inline">Send</span>
                </span>
              )}
          </button>
        </form>
        </div>
      </div>
    </div>
  )
}

export default ThreadDetail
