import React, { useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useStudySite } from '@/contexts/StudySiteContext'
import { Message } from '@/types'
import UserPicker from '@/components/UserPicker'

interface CreateThreadFromConversationProps {
  conversationId: string
  messages: Message[]
  selectedMessageIds: string[]
  onClose: () => void
  onSuccess: () => void
  apiBase: string
}

const CreateThreadFromConversation: React.FC<CreateThreadFromConversationProps> = ({
  conversationId,
  messages,
  selectedMessageIds,
  onClose,
  onSuccess,
}) => {
  const { user } = useAuth()
  const { selectedStudyId, selectedSiteId } = useStudySite()
  const currentUserEmail = user?.email?.toLowerCase() || ''
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [threadType, setThreadType] = useState<'issue' | 'patient' | 'general'>('general')
  const [visibilityScope, setVisibilityScope] = useState<'private' | 'site'>('private')
  const [participantsEmails, setParticipantsEmails] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedMessages = messages.filter(msg =>
    selectedMessageIds.includes(msg.id)
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!title.trim()) {
      setError('Title is required')
      return
    }

    if (selectedMessageIds.length === 0) {
      setError('Please select at least one message')
      return
    }

    setLoading(true)
    setError(null)

    try {
      // Ensure current user is always included in participants_emails
      const finalParticipantsEmails = [
        ...new Set([
          currentUserEmail,
          ...participantsEmails
        ].filter(Boolean))
      ]
      
      await api.post(
        `/conversations/${conversationId}/create-thread`,
        {
          title: title.trim(),
          description: description.trim() || undefined,
          thread_type: threadType,
          message_ids: selectedMessageIds,
          created_by: user?.user_id || '',
          related_study_id: selectedStudyId || undefined,
          visibility_scope: visibilityScope,
          participants_emails: finalParticipantsEmails,
        }
      )

      onSuccess()
      onClose()
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          err.message ||
          'Failed to create thread'
      )
    } finally {
      setLoading(false)
    }
  }

  const formatTime = (dateString: string): string => {
    const date = new Date(dateString)
    return date.toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }


  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="bg-dizzaroo-deep-blue text-white px-6 py-4 rounded-t-2xl">
          <h2 className="text-xl font-bold">Create Thread from Messages</h2>
          <p className="text-sm opacity-90 mt-1">
            {selectedMessageIds.length} message{selectedMessageIds.length !== 1 ? 's' : ''} selected
          </p>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Title */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Thread Title *
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-4 py-2 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue"
                placeholder="e.g., Patient Issue - Heart Attack"
                required
                disabled={loading}
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Description (Optional)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-4 py-2 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue resize-none"
                rows={3}
                placeholder="Add a description for this thread..."
                disabled={loading}
              />
            </div>

            {/* Thread Type */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Thread Type *
              </label>
              <select
                value={threadType}
                onChange={(e) => setThreadType(e.target.value as 'issue' | 'patient' | 'general')}
                className="w-full px-4 py-2 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue"
                required
                disabled={loading}
              >
                <option value="general">General</option>
                <option value="issue">Issue</option>
                <option value="patient">Patient</option>
              </select>
            </div>

            {/* Visibility */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Visibility
              </label>
              <select
                value={visibilityScope}
                onChange={(e) => setVisibilityScope(e.target.value as 'private' | 'site')}
                className="w-full px-4 py-2 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue"
                disabled={loading}
              >
                <option value="private">🔐 Private</option>
                <option value="site">🌐 Visible to All</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">
                {visibilityScope === 'private' 
                  ? 'Only selected participants can view this thread' 
                  : 'All users in this study and site can view this thread'}
              </p>
            </div>

            {/* Participants (only for private threads) */}
            {visibilityScope === 'private' && (
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Select Participants
                </label>
                <p className="text-xs text-gray-500 mb-2">
                  Search and select users from your site. You (the creator) will always have access.
                </p>
                <UserPicker
                  selectedUserEmails={participantsEmails}
                  onSelectionChange={setParticipantsEmails}
                  siteId={selectedSiteId || undefined}
                  excludeEmails={[]}  // Don't exclude current user - creator is handled automatically on backend
                  placeholder="Search users by name or email..."
                  className="w-full"
                />
              </div>
            )}

            {/* Selected Messages Preview */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Selected Messages ({selectedMessageIds.length})
              </label>
              <div className="border-2 border-gray-200 rounded-lg p-4 max-h-64 overflow-y-auto bg-gray-50">
                {selectedMessages.length === 0 ? (
                  <p className="text-gray-500 text-sm">No messages selected</p>
                ) : (
                  <div className="space-y-3">
                    {selectedMessages.map((msg) => (
                      <div
                        key={msg.id}
                        className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm"
                      >
                        <div className="flex justify-between items-start mb-1">
                          <span className="text-xs font-semibold text-gray-600">
                            {msg.direction === 'outbound' ? 'You' : msg.channel.toUpperCase()}
                          </span>
                          <span className="text-xs text-gray-500">{formatTime(msg.created_at)}</span>
                        </div>
                        <p className="text-sm text-gray-800 line-clamp-3">{msg.body}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="bg-red-50 border-2 border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 border-2 border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50 transition disabled:opacity-50"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl font-semibold hover:bg-dizzaroo-blue-green transition shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={loading || !title.trim()}
              >
                {loading ? 'Creating...' : 'Create Thread'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

export default CreateThreadFromConversation

