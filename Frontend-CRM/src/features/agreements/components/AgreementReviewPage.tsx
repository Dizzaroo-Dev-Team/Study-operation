/**
 * Agreement Review Page
 *
 * Public page for external site users to review an agreement.
 * Accessed via secure token link: /agreement/review/[agreementId]?token=...
 *
 * The reviewer reads + comments on the document in OnlyOffice (comment-only mode)
 * and then returns it to the internal team with the workflow actions in the header:
 *   • Approve            → the workflow engine takes the forward exit
 *   • Send back          → the engine loops back to editing for the owner's revision
 *
 * These actions are driven entirely by the unified workflow engine (see
 * GET/POST /agreements/{id}/review/{context,respond}). The old standalone
 * "Submit Review" / "Sign & Send Back" buttons were removed — review is always
 * workflow-driven now.
 */

import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { useDownloadAgreementDocument } from '@/lib/queries/useAgreements'
import OnlyOfficeEditor, { type OnlyOfficeEditorHandle } from '@/components/OnlyOfficeEditor'
import AgreementCommentPanel from './AgreementCommentPanel'

interface AgreementReviewData {
  agreement: {
    id: string
    title: string
    status: string
  }
  site: {
    id: string | null
    site_id: string | null
    name: string | null
  }
  document: {
    id: string | null
    version_number: number | null
    document_file_path: string | null
  } | null
  token: string
  reviewer_email?: string | null
}

const AgreementReviewPage: React.FC = () => {
  // Extract agreementId from URL path: /agreement/review/{agreementId}
  const pathParts = window.location.pathname.split('/')
  const agreementId = pathParts[pathParts.length - 1]

  // Extract token from URL query params
  const urlParams = new URLSearchParams(window.location.search)
  const token = urlParams.get('token')
  /** Same base as other public axios calls; must be full backend URL in dev (e.g. http://localhost:8000/api) when Vite has no /api proxy. */
  const publicApiBase = (import.meta as any).env.VITE_API_BASE || '/api'

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reviewData, setReviewData] = useState<AgreementReviewData | null>(null)

  // Ref to the OnlyOffice editor so we can force-save comments before responding.
  const ooEditorRef = useRef<OnlyOfficeEditorHandle>(null)

  // Unified review: the workflow engine tells us whether this reviewer can Approve
  // or Send-back on the current step (token-gated). `loaded` distinguishes "still
  // checking" from "checked — no action available for you right now".
  const [unifiedReview, setUnifiedReview] = useState<{ active: boolean; can_approve?: boolean; can_send_back?: boolean }>({ active: false })
  const [unifiedLoaded, setUnifiedLoaded] = useState(false)
  const [unifiedBusy, setUnifiedBusy] = useState(false)
  const [unifiedDone, setUnifiedDone] = useState<string | null>(null)

  useEffect(() => {
    if (!agreementId || !token) return
    let alive = true
    axios.get(`${publicApiBase}/agreements/${agreementId}/review/context`, { params: { token }, headers: {} })
      .then((r) => { if (alive) setUnifiedReview(r.data || { active: false }) })
      .catch(() => { if (alive) setUnifiedReview({ active: false }) })
      .finally(() => { if (alive) setUnifiedLoaded(true) })
    return () => { alive = false }
  }, [agreementId, token, publicApiBase])

  const respondUnified = async (decision: 'approve' | 'send_back') => {
    if (!agreementId || !token) return
    setUnifiedBusy(true)
    setError(null)
    try {
      // Best-effort, NON-BLOCKING nudge for OnlyOffice to flush its session. The old
      // 4-second timer was removed: the backend /review/respond now force-saves the OO
      // session and upserts the reviewer's comments synchronously, in the SAME
      // transaction that advances the engine. Persistence is therefore guaranteed
      // server-side and no longer depends on a client-side wait that could fire before
      // the comments landed.
      try { ooEditorRef.current?.requestSave() } catch { /* best-effort only */ }
      await axios.post(`${publicApiBase}/agreements/${agreementId}/review/respond`, { token, decision }, { headers: {} })
      setUnifiedDone(decision)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to submit your review response.')
    } finally {
      setUnifiedBusy(false)
    }
  }

  useEffect(() => {
    if (!agreementId || !token) {
      setError('Missing agreement ID or token')
      setLoading(false)
      return
    }

    const fetchReviewData = async () => {
      try {
        // Use direct axios call without auth headers for public endpoint
        const response = await axios.get(`${publicApiBase}/agreement/review/${agreementId}`, {
          params: { token },
          // Don't send Authorization header for public endpoint
          headers: {},
        })
        setReviewData(response.data)
        setLoading(false)
      } catch (err: any) {
        console.error('Failed to load review agreement:', err)
        const errorMessage = err.response?.data?.detail || err.message || 'Failed to load agreement'
        setError(errorMessage)
        setLoading(false)
      }
    }

    fetchReviewData()
  }, [agreementId, token, publicApiBase])

  const downloadMutation = useDownloadAgreementDocument()

  const handleDownloadDocument = async () => {
    if (!reviewData?.document?.document_file_path) {
      setError('Document file not available')
      return
    }

    try {
      const blob = await downloadMutation.mutateAsync({
        agreementId: reviewData.agreement.id,
        version: reviewData.document.version_number ?? 0,
      })
      const url = window.URL.createObjectURL(new Blob([blob]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${reviewData.agreement.title}_v${reviewData.document.version_number}.docx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch {
      setError('Failed to download document')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Loading agreement...</p>
        </div>
      </div>
    )
  }

  if (error && !reviewData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
          <div className="text-center">
            <div className="text-red-600 text-5xl mb-4">⚠️</div>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h1>
            <p className="text-gray-600">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!reviewData) {
    return null
  }

  // Unified review response recorded — short success screen.
  if (unifiedDone) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6 text-center">
          <div className="text-green-600 text-5xl mb-4">✓</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            {unifiedDone === 'approve' ? 'Review approved' : 'Sent back with comments'}
          </h1>
          <p className="text-gray-600">
            {unifiedDone === 'approve'
              ? 'Thank you — the workflow has moved forward.'
              : 'Thank you — your comments were saved and the document was returned for revision.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50" style={{ height: '100vh', overflowY: 'auto' }}>
      {/* Header */}
      <div className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{reviewData.agreement.title}</h1>
              <p className="text-sm text-gray-600 mt-1">
                Site: {reviewData.site.name || reviewData.site.site_id || 'N/A'}
              </p>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={handleDownloadDocument}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Download Document
              </button>
              {/* Workflow review actions — comment in the document, then choose. */}
              {unifiedReview.active && unifiedReview.can_send_back && (
                <button
                  onClick={() => respondUnified('send_back')}
                  disabled={unifiedBusy}
                  className="px-4 py-2 text-sm font-medium text-amber-800 bg-amber-50 border border-amber-300 rounded-md hover:bg-amber-100 disabled:opacity-50"
                >
                  {unifiedBusy ? 'Submitting…' : 'Send back with comments'}
                </button>
              )}
              {unifiedReview.active && unifiedReview.can_approve && (
                <button
                  onClick={() => respondUnified('approve')}
                  disabled={unifiedBusy}
                  className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50"
                >
                  {unifiedBusy ? 'Submitting…' : 'Approve'}
                </button>
              )}
              {/* Checked, but this reviewer has no pending action (e.g. already
                  responded, or the document has moved on). */}
              {unifiedLoaded && !unifiedReview.active && (
                <span className="text-sm text-gray-500">No review action is pending for you.</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Editor Section */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 pb-20">
        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        {reviewData.document ? (
          <div className="bg-white shadow-sm rounded-lg overflow-hidden">
            {/* ── Header ─────────────────────────────────────────── */}
            <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Document Review</h2>
                <p className="text-sm text-gray-600 mt-1">
                  Version {reviewData.document.version_number}
                </p>
              </div>
              {/* Review mode badge */}
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-300">
                💬 Comment-Only Mode
              </span>
            </div>

            {/* ── Instructions banner ──────────────────────────── */}
            <div className="p-4 bg-blue-50 border-b border-blue-200">
              <p className="text-sm text-blue-900 font-semibold mb-1">How to review this document:</p>
              <ol className="text-sm text-blue-800 space-y-1 list-decimal list-inside">
                <li>
                  <strong>Select text</strong> in the document that you want to comment on.
                </li>
                <li>
                  Click the <strong>comment icon</strong> (speech bubble) that appears, or use
                  the <kbd className="px-1 py-0.5 bg-blue-100 border border-blue-300 rounded text-xs">Insert → Comment</kbd> menu.
                </li>
                <li>Type your comment and click <strong>Add Comment</strong>.</li>
                <li>
                  Repeat for every section you want to flag. You <em>cannot</em> edit the document
                  text — only comments are allowed.
                </li>
                <li>
                  When finished, use <strong>Approve</strong> or <strong>Send back with comments</strong> at
                  the top right to return the document to the internal team.
                </li>
              </ol>
            </div>

            {/* ── Editor + Comment panel side-by-side ─────────── */}
            <div className="flex" style={{ minHeight: '65vh' }}>
              {/* OnlyOffice editor (comment-only permissions set by backend) */}
              <div className="flex-1 min-w-0 border-r border-gray-200">
                <OnlyOfficeEditor
                  ref={ooEditorRef}
                  agreementId={reviewData.agreement.id}
                  apiBase={publicApiBase}
                  canEdit={false}   // visual hint – actual lock is in OnlyOffice permissions
                  publicSession
                  editorContainerId={`onlyoffice-review-${reviewData.agreement.id}`}
                  configEndpoint={`/agreements/${reviewData.agreement.id}/onlyoffice-config?version=${reviewData.document.version_number}&token=${token}`}
                />
              </div>

              {/* Comment thread panel — shows the site user their own comments
                  plus any replies / statuses from the internal team */}
              <div className="w-72 flex-shrink-0 overflow-hidden">
                <AgreementCommentPanel
                  agreementId={reviewData.agreement.id}
                  apiBase={publicApiBase}
                  isInternal={false}  // site user — read-only thread view
                  reviewDocumentId={reviewData.document?.id ?? null}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white shadow-sm rounded-lg p-6 text-center">
            <p className="text-gray-600">No document available for review</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default AgreementReviewPage
