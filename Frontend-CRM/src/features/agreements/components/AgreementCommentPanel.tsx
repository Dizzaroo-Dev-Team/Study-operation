/**
 * AgreementCommentPanel
 * =====================
 * Side panel displayed inside the Agreement editor for INTERNAL users.
 *
 * Shows all comments left by the external site reviewer (added via
 * OnlyOffice comment-only mode).  Internal users can:
 *   • Read the comment and the quoted document text
 *   • Reply to a comment (stored as an internal reply row)
 *   • Set the comment status: Accepted / Rejected / Modified
 *
 * The panel is read-only for site users (they see comments + replies but
 * cannot change statuses – that is enforced by the backend).
 *
 * Usage (internal view):
 *   <AgreementCommentPanel
 *     agreementId="..."
 *     apiBase="/api"
 *     isInternal={true}
 *   />
 *
 * Usage (site review page – read-only thread view):
 *   <AgreementCommentPanel
 *     agreementId="..."
 *     apiBase="/api"
 *     isInternal={false}
 *   />
 */

import React, { useEffect, useMemo, useState } from 'react'
import {
  useAgreementComments,
  useAgreementCommentReply,
  useAgreementCommentStatus,
  useReExtractAgreementComments,
} from '@/lib/queries/useAgreements'

// ── Types ─────────────────────────────────────────────────────────────────────

interface CommentReply {
  id: string
  author_email: string
  comment_text: string
  status: string
  is_internal_reply: boolean
  created_at: string | null
}

interface Comment {
  id: string
  comment_id: string
  author_email: string
  comment_text: string
  referenced_text: string
  oo_date: string | null
  status: 'pending' | 'accepted' | 'rejected' | 'modified'
  is_internal_reply: boolean
  created_at: string | null
  replies: CommentReply[]
}

interface AgreementCommentPanelProps {
  agreementId: string
  apiBase?: string
  /** True = internal CRM user; can reply and change status.
   *  False = site user; read-only thread display. */
  isInternal?: boolean
  /**
   * For external site users we must filter comments to the current review
   * round (AgreementReviewDocument) so old comments never show up.
   */
  reviewDocumentId?: string | null
  /**
   * Triggers a re-fetch of comments (useful after "Save Document" on the
   * external review page).
   */
  reloadNonce?: number
  /**
   * Optional hook for internal screens: when user clicks "Refresh" we can
   * re-initialize the ONLYOFFICE editor without reloading the whole page.
   */
  onRefreshOnlyOffice?: () => void
  onCommentCountChange?: (count: number) => void
}

// ── Status badge colours ──────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  pending:  'bg-yellow-100 text-yellow-800 border-yellow-300',
  accepted: 'bg-green-100  text-green-800  border-green-300',
  rejected: 'bg-red-100    text-red-800    border-red-300',
  modified: 'bg-blue-100   text-blue-800   border-blue-300',
}

const STATUS_LABELS: Record<string, string> = {
  pending:  'Pending',
  accepted: '✔ Accepted',
  rejected: '✘ Rejected',
  modified: '✎ Modified',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | null) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

const AgreementCommentPanel: React.FC<AgreementCommentPanelProps> = ({
  agreementId,
  isInternal = true,
  reviewDocumentId = null,
  reloadNonce = 0,
  onRefreshOnlyOffice,
  onCommentCountChange,
}) => {
  const [replyText, setReplyText]     = useState<Record<string, string>>({})
  const [submitting, setSubmitting]   = useState<Record<string, boolean>>({})
  const [openReply, setOpenReply]     = useState<string | null>(null)  // comment id with open reply box
  const [mutationError, setMutationError] = useState<string | null>(null)

  // External-review UI is cycle-scoped — without a reviewDocumentId, skip
  // the fetch entirely so we don't leak comments from previous cycles.
  const commentsEnabled = isInternal || Boolean(reviewDocumentId)

  const commentsQuery = useAgreementComments(agreementId, {
    reviewDocumentId,
    enabled: commentsEnabled,
  })
  const replyMutation = useAgreementCommentReply(agreementId)
  const statusMutation = useAgreementCommentStatus(agreementId)
  const reExtractMutation = useReExtractAgreementComments(agreementId)

  const comments: Comment[] = useMemo(() => {
    if (!commentsEnabled) return []
    return (commentsQuery.data?.comments ?? []) as Comment[]
  }, [commentsEnabled, commentsQuery.data])

  const loading =
    commentsEnabled && (commentsQuery.isLoading || reExtractMutation.isPending)
  const fetchError = commentsEnabled && commentsQuery.isError
    ? (commentsQuery.error as any)?.response?.data?.detail || 'Failed to load comments'
    : null
  const error = mutationError ?? fetchError

  const substantiveCommentCount = useMemo(
    () =>
      comments.filter(
        (c) => !c.is_internal_reply && (c.comment_text || '').trim().length > 0,
      ).length,
    [comments],
  )

  // Mirror substantive comment count (empty OO placeholders must not block OTP sign).
  useEffect(() => {
    if (!commentsEnabled) {
      onCommentCountChange?.(0)
      return
    }
    if (commentsQuery.isSuccess) {
      onCommentCountChange?.(substantiveCommentCount)
    }
    if (commentsQuery.isError) {
      onCommentCountChange?.(0)
    }
    // onCommentCountChange intentionally omitted — parent callback identity
    // is typically unstable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commentsEnabled, substantiveCommentCount, commentsQuery.isSuccess, commentsQuery.isError])

  // Legacy `reloadNonce` external trigger → manual refetch.
  useEffect(() => {
    if (commentsEnabled) {
      void commentsQuery.refetch()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadNonce])

  // ── Re-extract comments from DOCX (internal users only) ────────────────────
  const handleReExtract = async () => {
    setMutationError(null)
    try {
      await reExtractMutation.mutateAsync()
    } catch (err: any) {
      setMutationError(err?.response?.data?.detail || 'Re-extraction failed')
    }
  }

  // ── Refresh comments (and optionally refresh ONLYOFFICE) ────────────────
  const handleRefresh = async () => {
    setMutationError(null)
    await commentsQuery.refetch()
    onRefreshOnlyOffice?.()
  }

  // ── Reply handler ───────────────────────────────────────────────────────────
  const handleReply = async (commentId: string) => {
    const text = (replyText[commentId] || '').trim()
    if (!text) return
    setSubmitting(prev => ({ ...prev, [commentId]: true }))
    setMutationError(null)
    try {
      await replyMutation.mutateAsync({ commentId, replyText: text })
      setReplyText(prev => ({ ...prev, [commentId]: '' }))
      setOpenReply(null)
    } catch (err: any) {
      setMutationError(err?.response?.data?.detail || 'Failed to post reply')
    } finally {
      setSubmitting(prev => ({ ...prev, [commentId]: false }))
    }
  }

  // ── Status change handler ───────────────────────────────────────────────────
  const handleStatusChange = async (commentId: string, newStatus: string) => {
    setSubmitting(prev => ({ ...prev, [`status-${commentId}`]: true }))
    setMutationError(null)
    try {
      await statusMutation.mutateAsync({ commentId, status: newStatus })
    } catch (err: any) {
      setMutationError(err?.response?.data?.detail || 'Failed to update status')
    } finally {
      setSubmitting(prev => ({ ...prev, [`status-${commentId}`]: false }))
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Review Comments
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {isInternal
              ? 'Site reviewer comments — reply or set status below'
              : 'Your comments and internal team replies'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isInternal && (
            <button
              onClick={handleReExtract}
              className="text-xs text-purple-600 hover:text-purple-800"
              title="Re-extract referenced text from the saved DOCX"
            >
              ⟳ Re-extract
            </button>
          )}
          <button
            onClick={handleRefresh}
            className="text-xs text-blue-600 hover:text-blue-800"
            title="Refresh comments"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mr-2" />
            <span className="text-sm text-gray-500">Loading comments…</span>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {!loading && !error && comments.length === 0 && (
          <div className="text-center py-10 text-gray-400 text-sm">
            <div className="text-3xl mb-2">💬</div>
            <p>No comments yet.</p>
            {!isInternal && (
              <p className="mt-1 text-xs">
                Select text in the document and click the comment icon to add a comment.
              </p>
            )}
          </div>
        )}

        {!loading && comments.map(comment => (
          <div
            key={comment.id}
            className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden"
          >
            {/* Comment header */}
            <div className="px-3 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <div className="h-6 w-6 rounded-full bg-indigo-100 text-indigo-700 text-xs flex items-center justify-center font-semibold flex-shrink-0">
                  {(comment.author_email || '?')[0].toUpperCase()}
                </div>
                <span className="text-xs font-medium text-gray-700 truncate">
                  {comment.author_email}
                </span>
                <span className="text-xs text-gray-400 flex-shrink-0">
                  {formatDate(comment.oo_date || comment.created_at)}
                </span>
              </div>

              {/* Status badge + change control */}
              <div className="flex items-center gap-1 flex-shrink-0">
                <span
                  className={`text-xs px-2 py-0.5 rounded border font-medium ${STATUS_STYLES[comment.status] || STATUS_STYLES.pending}`}
                >
                  {STATUS_LABELS[comment.status] || comment.status}
                </span>
                {isInternal && (
                  <select
                    disabled={submitting[`status-${comment.id}`]}
                    value={comment.status}
                    onChange={e => handleStatusChange(comment.id, e.target.value)}
                    className="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400"
                    title="Change status"
                  >
                    <option value="pending">Pending</option>
                    <option value="accepted">Accepted</option>
                    <option value="rejected">Rejected</option>
                    <option value="modified">Modified</option>
                  </select>
                )}
              </div>
            </div>

            {/* Quoted text — the document text the reviewer selected */}
            {comment.referenced_text ? (
              <div className="mx-3 mt-2 px-2 py-1.5 bg-yellow-50 border-l-2 border-yellow-400 rounded text-xs text-yellow-900 italic">
                "{comment.referenced_text}"
              </div>
            ) : (
              <div className="mx-3 mt-2 px-2 py-1 text-xs text-gray-400 italic">
                (no text selected)
              </div>
            )}

            {/* Comment body */}
            <div className="px-3 py-2 text-sm text-gray-800 whitespace-pre-wrap">
              {comment.comment_text}
            </div>

            {/* Replies */}
            {comment.replies.length > 0 && (
              <div className="border-t border-gray-100 mx-3 mb-2 mt-1 space-y-2 pt-2">
                {comment.replies.map(reply => (
                  <div
                    key={reply.id}
                    className={`rounded px-2 py-1.5 text-xs ${
                      reply.is_internal_reply
                        ? 'bg-blue-50 border border-blue-100'
                        : 'bg-gray-50 border border-gray-100'
                    }`}
                  >
                    <div className="flex items-center gap-1 mb-0.5">
                      <span className="font-medium text-gray-700">
                        {reply.is_internal_reply ? '🏢 ' : ''}{reply.author_email}
                      </span>
                      <span className="text-gray-400">
                        {formatDate(reply.created_at)}
                      </span>
                    </div>
                    <p className="text-gray-800 whitespace-pre-wrap">{reply.comment_text}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Reply box (internal only) */}
            {isInternal && (
              <div className="px-3 pb-3">
                {openReply === comment.id ? (
                  <div className="mt-2 space-y-2">
                    <textarea
                      rows={2}
                      value={replyText[comment.id] || ''}
                      onChange={e =>
                        setReplyText(prev => ({ ...prev, [comment.id]: e.target.value }))
                      }
                      placeholder="Type your reply…"
                      className="w-full text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none"
                    />
                    <div className="flex gap-2">
                      <button
                        disabled={submitting[comment.id] || !replyText[comment.id]?.trim()}
                        onClick={() => handleReply(comment.id)}
                        className="px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
                      >
                        {submitting[comment.id] ? 'Sending…' : 'Send Reply'}
                      </button>
                      <button
                        onClick={() => setOpenReply(null)}
                        className="px-3 py-1 bg-gray-100 text-gray-700 text-xs rounded hover:bg-gray-200"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setOpenReply(comment.id)}
                    className="mt-1 text-xs text-blue-600 hover:text-blue-800 hover:underline"
                  >
                    ↩ Reply
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer info */}
      <div className="px-4 py-2 border-t border-gray-200 bg-gray-50 text-xs text-gray-400">
        {comments.length} comment{comments.length !== 1 ? 's' : ''}
        {comments.reduce((n, c) => n + c.replies.length, 0) > 0
          ? ` · ${comments.reduce((n, c) => n + c.replies.length, 0)} repl${
              comments.reduce((n, c) => n + c.replies.length, 0) === 1 ? 'y' : 'ies'
            }`
          : ''}
      </div>
    </div>
  )
}

export default AgreementCommentPanel
