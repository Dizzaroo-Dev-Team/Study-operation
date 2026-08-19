import React, { useState, FormEvent, ChangeEvent } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useStudySite } from '@/contexts/StudySiteContext'
import UserPicker from '@/components/UserPicker'

interface CreateThreadModalProps {
  onClose: () => void
  onSubmit: (data: {
    conversation_id: string  // Required: all threads must belong to a conversation
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
    participants_emails?: string[]  // New: email-based participants
    visibility_scope?: 'private' | 'site'
  }) => void
  loading: boolean
  conversations: Array<{ id: string; subject?: string; study_id?: string }>  // List of conversations to choose from
  defaultConversationId?: string  // Pre-select a conversation if provided
}

const CreateThreadModal: React.FC<CreateThreadModalProps> = ({ onClose, onSubmit, loading, conversations = [], defaultConversationId }) => {
  const { user } = useAuth()
  const { selectedSiteId } = useStudySite()
  const currentUserId = user?.user_id || ''
  const currentUserEmail = user?.email?.toLowerCase() || ''
  
  const [formData, setFormData] = useState({
    conversation_id: defaultConversationId || '',
    title: '',
    description: '',
    thread_type: 'general',
    related_patient_id: '',
    related_study_id: '',
    priority: 'medium',
    created_by: currentUserId, // Set from auth context
    participants: [],
    participants_emails: [] as string[],  // New: email-based participants
    visibility_scope: 'private' as 'private' | 'site'  // Default to private
  })

  const handleChange = (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    })
  }

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!formData.conversation_id) {
      alert('Please pick a conversation for this thread')
      return
    }
    if (!formData.title.trim()) {
      alert('Title is required')
      return
    }
    
    // Ensure current user is always included in participants_emails
    const finalParticipantsEmails = [
      ...new Set([
        currentUserEmail,
        ...formData.participants_emails
      ].filter(Boolean))
    ]
    
    const submitData = {
      ...formData,
      participants_emails: finalParticipantsEmails,
    }
    onSubmit(submitData)
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Create New Thread</h2>
          <button 
            className="text-2xl text-gray-500 hover:text-gray-700"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {conversations && conversations.length > 0 && (
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">
                Conversation (Optional)
              </label>
              <select
                name="conversation_id"
                value={formData.conversation_id}
                onChange={handleChange}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                disabled={loading}
              >
                <option value="">None (Independent Thread)</option>
                {conversations.map(conv => (
                  <option key={conv.id} value={conv.id}>
                    {conv.subject || 'Untitled conversation'}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">Link to a conversation (optional)</p>
            </div>
          )}

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Title *</label>
            <input
              type="text"
              name="title"
              value={formData.title}
              onChange={handleChange}
              required
              placeholder="Thread title"
              className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Description</label>
            <textarea
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="Describe the issue or topic..."
              rows={4}
              className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue resize-y"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Type</label>
              <select 
                name="thread_type" 
                value={formData.thread_type} 
                onChange={handleChange}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
              >
                <option value="general">General</option>
                <option value="issue">Issue</option>
                <option value="patient">Patient</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Priority</label>
              <select 
                name="priority" 
                value={formData.priority} 
                onChange={handleChange}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Visibility</label>
            <select 
              name="visibility_scope" 
              value={formData.visibility_scope} 
              onChange={handleChange}
              className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
            >
              <option value="private">🔐 Private</option>
              <option value="site">🌐 Visible to All</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              {formData.visibility_scope === 'private' 
                ? 'Only selected participants can view this thread' 
                : 'All users in this study and site can view this thread'}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Patient ID</label>
              <input
                type="text"
                name="related_patient_id"
                value={formData.related_patient_id}
                onChange={handleChange}
                placeholder="Optional"
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Study ID</label>
              <input
                type="text"
                name="related_study_id"
                value={formData.related_study_id}
                onChange={handleChange}
                placeholder="Optional"
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
              />
            </div>
          </div>

          {/* Created By is automatically set from auth context - no need to show input */}

          {formData.visibility_scope === 'private' && (
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Select Participants</label>
              <p className="text-xs text-gray-500 mb-2">
                Search and select users from your site. You (the creator) will always have access.
              </p>
              <UserPicker
                selectedUserEmails={formData.participants_emails}
                onSelectionChange={(emails) => setFormData({ ...formData, participants_emails: emails })}
                siteId={selectedSiteId || undefined}
                excludeEmails={[]}  // Don't exclude current user - creator is handled automatically on backend
                placeholder="Search users by name or email..."
                className="w-full"
              />
            </div>
          )}

          <div className="flex gap-3 justify-end pt-2">
            <button 
              type="button" 
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition"
              onClick={onClose}
            >
              Cancel
            </button>
            <button 
              type="submit" 
              className="px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl hover:bg-dizzaroo-blue-green disabled:opacity-50 transition"
              disabled={loading}
            >
              {loading ? 'Creating...' : 'Create Thread'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateThreadModal

