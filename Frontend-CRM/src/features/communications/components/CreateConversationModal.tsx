import React, { useState, FormEvent, ChangeEvent } from 'react'

interface CreateConversationModalProps {
  onClose: () => void
  onSubmit: (data: {
    participant_phone?: string
    participant_email?: string
    participant_emails?: string[]
    subject?: string
    study_id?: string
    site_id?: string
  }) => void
  loading: boolean
  studyName?: string
  siteName?: string
}

const CreateConversationModal: React.FC<CreateConversationModalProps> = ({ onClose, onSubmit, loading, studyName, siteName }) => {
  // Email recipients now flow from @email mentions inside the first message,
  // so this modal only collects a subject. Study + site come from the global
  // selector and are stamped on the conversation server-side.
  const [formData, setFormData] = useState({
    subject: '',
    study_id: '',
  })

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    })
  }

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (loading) return

    // New conversations no longer require participant email/phone.
    // Email delivery is driven by @email mentions in message bodies.
    onSubmit({
      subject: formData.subject,
      study_id: formData.study_id
    })
  }

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={() => { if (!loading) onClose() }}
    >
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 relative" onClick={(e) => e.stopPropagation()}>
        {loading && (
          <div className="absolute inset-0 bg-white/70 rounded-lg flex items-center justify-center z-10">
            <div className="flex flex-col items-center gap-2">
              <span className="w-8 h-8 border-2 border-dizzaroo-deep-blue border-t-transparent rounded-full animate-spin" />
              <span className="text-sm font-medium text-gray-700">Creating conversation…</span>
            </div>
          </div>
        )}
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Create New Conversation</h2>
          <button
            type="button"
            className="text-2xl text-gray-500 hover:text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={onClose}
            disabled={loading}
          >
            ×
          </button>
        </div>

        {/* data-testid: registered as an Orbit fillable form (fill-only — Orbit
            never clicks Create; the user submits). See features/assistant/demo/forms.ts */}
        <form onSubmit={handleSubmit} className="space-y-4" data-testid="conversation-create-form">
          {studyName && siteName && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
              <p className="text-sm text-blue-800">
                <strong>Creating conversation for:</strong><br />
                📊 {studyName} → 🏥 {siteName}
              </p>
            </div>
          )}
          {/* Study ID hidden - automatically using selected study from global selector */}

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Subject</label>
            <input
              type="text"
              name="subject"
              value={formData.subject}
              onChange={handleChange}
              placeholder="Conversation subject"
              disabled={loading}
              data-testid="conversation-field-subject"
              className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue disabled:bg-gray-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Participant phone / email inputs were removed because email delivery now relies on @email mentions
              inside message bodies, not on static participant fields at conversation creation time. */}

          <div className="flex gap-3 justify-end pt-2">
            <button
              type="button"
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl hover:bg-dizzaroo-blue-green disabled:opacity-50 disabled:cursor-not-allowed transition inline-flex items-center gap-2"
              disabled={loading}
            >
              {loading && (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              {loading ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateConversationModal

