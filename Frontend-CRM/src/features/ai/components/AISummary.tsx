import React, { useState } from 'react'
import { api } from '@/lib/api'   // ✅ use centralized axios instance
import ReactMarkdown from 'react-markdown'

interface AISummaryProps {
  conversationId?: string
  threadId?: string
  apiBase: string
  type: 'conversation' | 'thread'
}

const AISummary: React.FC<AISummaryProps> = ({ conversationId, threadId, apiBase, type }) => {
  const [summary, setSummary] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSummary, setShowSummary] = useState(false)

  const fetchSummary = async () => {
    if (!conversationId && !threadId) return

    setLoading(true)
    setError(null)
    setShowSummary(true)

    try {
      const url =
        type === 'conversation'
          ? `${apiBase}/conversations/${conversationId}/summary`
          : `${apiBase}/threads/${threadId}/summary`

      const response = await api.get(url)   // ✅ auth header auto-attached
      setSummary(response.data.summary)
    } catch (err: any) {
      const errorMsg =
        err.response?.data?.detail || err.message || 'Failed to generate summary'
      setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg))
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Button - Always visible. Matches TOOLBAR_BTN_CLASS in ConversationDetail. */}
      <button
        onClick={fetchSummary}
        disabled={loading}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded-lg text-xs font-medium hover:bg-gray-50 hover:border-gray-400 disabled:opacity-50 disabled:cursor-not-allowed transition whitespace-nowrap flex-shrink-0"
        title="Generate AI summary of this conversation"
        aria-label="Generate AI summary"
      >
        {loading ? (
          <span className="w-3.5 h-3.5 inline-block border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M14 4v4h4" />
            <path d="M4 4h10l6 6v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
            <path d="M7 13h7M7 17h5" />
          </svg>
        )}
        <span className="hidden sm:inline">{loading ? 'Generating…' : 'AI Summary'}</span>
      </button>

      {/* Modal - Only shown when showSummary is true */}
      {showSummary && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowSummary(false)}>
      <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="bg-dizzaroo-deep-blue text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
          <h2 className="text-xl font-bold">🤖 AI Summary</h2>
          <button
            onClick={() => setShowSummary(false)}
            className="text-white hover:text-gray-200 text-2xl font-bold"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="animate-spin text-4xl mb-4">🤖</div>
              <p className="text-gray-600 font-medium">Generating summary...</p>
              <p className="text-sm text-gray-500 mt-2">This may take a few seconds</p>
            </div>
          ) : error ? (
            <div className="bg-red-50 border-2 border-red-200 text-red-700 px-4 py-3 rounded-lg">
              <p className="font-semibold mb-1">Error generating summary</p>
              <p className="text-sm">{error}</p>
            </div>
          ) : summary ? (
            <div className="prose max-w-none">
              <div className="bg-dizzaroo-deep-blue/5 border-2 border-dizzaroo-deep-blue/20 rounded-xl p-6">
                <div className="text-gray-800 leading-relaxed">
                  <ReactMarkdown
                    components={{
                      // Customize heading styles
                      h1: ({...props}) => <h1 className="text-2xl font-bold mb-4 text-gray-900" {...props} />,
                      h2: ({...props}) => <h2 className="text-xl font-bold mb-3 text-gray-900" {...props} />,
                      h3: ({...props}) => <h3 className="text-lg font-bold mb-2 text-gray-900" {...props} />,
                      // Bold text - this will render **text** as bold
                      strong: ({...props}) => <strong className="font-bold text-gray-900" {...props} />,
                      // Paragraphs
                      p: ({...props}) => <p className="mb-3 text-gray-800" {...props} />,
                      // Lists
                      ul: ({...props}) => <ul className="list-disc list-inside mb-3 space-y-1 text-gray-800" {...props} />,
                      ol: ({...props}) => <ol className="list-decimal list-inside mb-3 space-y-1 text-gray-800" {...props} />,
                      li: ({...props}) => <li className="ml-4" {...props} />,
                    }}
                  >
                    {summary}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="border-t-2 border-gray-200 px-6 py-4 flex justify-end gap-3">
          <button
            onClick={() => {
              setShowSummary(false)
              setSummary(null)
              setError(null)
            }}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-semibold hover:bg-gray-300 transition"
          >
            Close
          </button>
          {summary && (
            <button
              onClick={fetchSummary}
              className="px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl font-semibold hover:bg-dizzaroo-blue-green transition"
            >
              🔄 Regenerate
            </button>
          )}
        </div>
      </div>
    </div>
      )}
    </>
  )
}

export default AISummary

