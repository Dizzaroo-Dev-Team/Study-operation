import React, { useState, useEffect, useMemo } from 'react'
import { useConversationSummary } from '@/lib/queries/useConversations'

interface InlineAISummaryProps {
  conversationId: string
  apiBase: string
  /** Total messages — used to decide whether the band auto-fetches. */
  messageCount: number
  /** Persisted AI summary from the conversation doc, if any. */
  initialSummary?: string | null
  /** Optional live summary text pushed via WebSocket. */
  liveSummary?: string | null
  /** Minimum message count before the band auto-fetches. */
  minMessages?: number
}

/**
 * Always-visible AI summary strip that sits on top of the conversation
 * canvas. Replaces the modal-based AI Summary button: it auto-fetches when
 * the thread has enough messages, accepts WebSocket updates, and offers
 * collapse + refresh affordances rather than a full-screen overlay.
 */
const InlineAISummary: React.FC<InlineAISummaryProps> = ({
  conversationId,
  messageCount,
  initialSummary,
  liveSummary,
  minMessages = 4,
}) => {
  const [revealed, setRevealed] = useState(false)
  const [collapsed, setCollapsed] = useState(true)

  // Reset to hidden when switching conversations.
  useEffect(() => {
    setRevealed(false)
    setCollapsed(true)
  }, [conversationId])

  // Fetch only after the user reveals the band (and there's enough content).
  // queryKey is keyed on conversationId so a different conversation resets
  // the cache slot without manual clearing.
  const summaryQuery = useConversationSummary(conversationId, {
    enabled: revealed && messageCount >= minMessages,
  })

  const loading = summaryQuery.isFetching
  const errorMessage = useMemo(() => {
    if (!summaryQuery.isError) return null
    const err = summaryQuery.error as any
    return err?.response?.data?.detail || err?.message || 'Failed to generate summary'
  }, [summaryQuery.isError, summaryQuery.error])

  // Display priority: live WS push > server fetch > initial doc seed.
  const liveTrimmed =
    typeof liveSummary === 'string' && liveSummary.trim().length > 0 ? liveSummary : null
  const summary: string | null =
    liveTrimmed !== null
      ? liveTrimmed
      : summaryQuery.isSuccess
        ? (summaryQuery.data ?? null)
        : (initialSummary ?? null)

  const handleRefresh = () => {
    void summaryQuery.refetch()
  }

  const handleReveal = () => {
    setRevealed(true)
    setCollapsed(false)
  }

  // Whether the conversation has enough content for a summary to be useful.
  const hasContent = messageCount >= minMessages || Boolean(summary)

  // Before the user asks for it, show a compact trigger instead of the
  // summary itself — nothing is fetched or displayed until they click.
  if (!revealed) {
    if (!hasContent) return null
    return (
      <div
        className="border-b border-brand-200/60 bg-brand-50/50 flex-shrink-0"
        role="region"
        aria-label="AI summary"
      >
        <div className="px-5 py-1.5">
          <button
            onClick={handleReveal}
            className="inline-flex items-center gap-1.5 text-ui-caption font-semibold uppercase tracking-wide text-brand-700 hover:text-brand-800 px-1.5 py-0.5 -ml-1.5 rounded hover:bg-brand-100/60 transition focus:outline-none focus:ring-2 focus:ring-brand-500/40"
            title="Generate an AI summary of this conversation"
          >
            <span aria-hidden="true" className="inline-flex items-center justify-center w-4 h-4 text-brand-600">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
              </svg>
            </span>
            {summary ? 'Show AI summary' : 'Generate AI summary'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      className="border-b border-brand-200/60 bg-brand-50/50 flex-shrink-0"
      role="region"
      aria-label="AI summary"
    >
      <div className="px-5 py-2 flex items-start gap-3">
        <span
          className="mt-0.5 inline-flex items-center justify-center w-5 h-5 rounded bg-brand-500/10 text-brand-600 flex-shrink-0"
          aria-hidden="true"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
          </svg>
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <span className="text-ui-caption uppercase tracking-wide text-brand-700 font-semibold">
              AI summary
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={handleRefresh}
                disabled={loading}
                className="text-ui-caption text-brand-600 hover:text-brand-700 disabled:opacity-50 px-1.5 py-0.5 rounded hover:bg-brand-100/60 transition"
                title="Regenerate summary"
                aria-label="Regenerate summary"
              >
                {loading ? 'Refreshing…' : 'Refresh'}
              </button>
              <button
                onClick={() => setCollapsed((c) => !c)}
                className="text-ui-caption text-slate-500 hover:text-slate-700 px-1.5 py-0.5 rounded hover:bg-slate-100 transition"
                title={collapsed ? 'Expand summary' : 'Collapse summary'}
                aria-label={collapsed ? 'Expand summary' : 'Collapse summary'}
              >
                {collapsed ? 'Show' : 'Hide'}
              </button>
            </div>
          </div>
          {!collapsed && (
            <div className="text-ui-body text-slate-700 leading-relaxed max-h-36 overflow-y-auto pr-1">
              {loading && !summary ? (
                <span className="inline-flex items-center gap-2 text-slate-500">
                  <span className="w-3 h-3 inline-block border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                  Generating summary…
                </span>
              ) : errorMessage ? (
                <span className="text-danger-600">
                  {errorMessage}{' '}
                  <button
                    onClick={handleRefresh}
                    className="underline hover:no-underline ml-1"
                  >
                    Try again
                  </button>
                </span>
              ) : summary ? (
                <p className="whitespace-pre-wrap">{summary}</p>
              ) : (
                <span className="text-slate-500">No summary yet.</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default InlineAISummary
