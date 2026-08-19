import React, { useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'

type QuestionnaireStatus = 'NOT_SENT' | 'SENT' | 'RECEIVED'

interface QuestionnaireActionsProps {
  siteId: string
  apiBase?: string
  questionnaireStatus?: QuestionnaireStatus | string | null
  questionnaireMetadata?: {
    sent_at?: string
    sent_by?: string
    received_at?: string
  } | null
  onUpdate?: () => void
}

const QuestionnaireActions: React.FC<QuestionnaireActionsProps> = ({
  siteId,
  apiBase = '/api',
  questionnaireStatus,
  questionnaireMetadata,
  onUpdate,
}) => {
  const { user } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const currentStatus: QuestionnaireStatus = (questionnaireStatus as QuestionnaireStatus) || 'NOT_SENT'

  const formatDate = (dateString?: string) => {
    if (!dateString) return '–'
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return '–'
    }
  }

  const handleSendQuestionnaire = async () => {
    setLoading(true)
    setError(null)

    try {
      // TODO: Create API endpoint POST /sites/{site_id}/questionnaire/send
      // This endpoint should:
      // 1. Update questionnaire status to 'SENT'
      // 2. Update site status metadata with sfq_status: 'SENT', sfq_sent_at, sfq_sent_by
      // 3. Return updated metadata
      await api.post(`${apiBase}/sites/${siteId}/questionnaire/send`, {
        sent_by: user?.user_id,
      })

      if (onUpdate) {
        onUpdate()
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to send questionnaire'
      setError(errorMsg)
      console.error('Failed to send questionnaire:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleReceiveQuestionnaire = async () => {
    setLoading(true)
    setError(null)

    try {
      // TODO: Create API endpoint POST /sites/{site_id}/questionnaire/receive
      // This endpoint should:
      // 1. Update questionnaire status to 'RECEIVED'
      // 2. Update site status metadata with sfq_status: 'RECEIVED', sfq_received_at
      // 3. Return updated metadata
      await api.post(`${apiBase}/sites/${siteId}/questionnaire/receive`, {
        received_by: user?.user_id,
      })

      if (onUpdate) {
        onUpdate()
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to receive questionnaire'
      setError(errorMsg)
      console.error('Failed to receive questionnaire:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      {/* Status Display */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-600 uppercase">Status:</span>
        <span
          className={`px-2 py-1 rounded text-xs font-semibold ${
            currentStatus === 'RECEIVED'
              ? 'bg-green-100 text-green-800'
              : currentStatus === 'SENT'
              ? 'bg-blue-100 text-blue-800'
              : 'bg-gray-100 text-gray-800'
          }`}
        >
          {currentStatus === 'NOT_SENT' ? 'Not Sent' : currentStatus}
        </span>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <div className="text-sm text-red-800">{error}</div>
        </div>
      )}

      {/* Actions based on status */}
      {currentStatus === 'NOT_SENT' && (
        <button
          onClick={handleSendQuestionnaire}
          disabled={loading}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium transition"
        >
          {loading ? 'Sending...' : 'Send Questionnaire'}
        </button>
      )}

      {currentStatus === 'SENT' && (
        <div className="space-y-2">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <div className="text-xs text-blue-800">
              {questionnaireMetadata?.sent_at && (
                <div>
                  <span className="font-semibold">Sent:</span> {formatDate(questionnaireMetadata.sent_at)}
                </div>
              )}
              {questionnaireMetadata?.sent_by && (
                <div>
                  <span className="font-semibold">By:</span> {questionnaireMetadata.sent_by}
                </div>
              )}
            </div>
          </div>
          <button
            onClick={handleReceiveQuestionnaire}
            disabled={loading}
            className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium transition"
          >
            {loading ? 'Processing...' : 'Mark as Received'}
          </button>
        </div>
      )}

      {currentStatus === 'RECEIVED' && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <div className="text-sm font-semibold text-green-900 mb-1">✓ Questionnaire Received</div>
          <div className="text-xs text-green-800 space-y-1">
            {questionnaireMetadata?.received_at && (
              <div>
                <span className="font-semibold">Received:</span> {formatDate(questionnaireMetadata.received_at)}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default QuestionnaireActions

