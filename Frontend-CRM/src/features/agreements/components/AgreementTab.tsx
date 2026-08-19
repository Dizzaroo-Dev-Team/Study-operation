import React, { useState, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useStudySite } from '@/contexts/StudySiteContext'
import {
  useAgreementChanges,
  useAgreementForSite,
  useAgreementReviewTokens,
  useAgreementTemplates,
  type AgreementWorkflowType,
} from '@/lib/queries/useAgreements'
import OnlyOfficeEditor, { type OnlyOfficeEditorHandle } from '@/components/OnlyOfficeEditor'
import SiteSelectionPrompt from '@/components/workspace/SiteSelectionPrompt'
// NEW: Review-comment panel shown alongside the OnlyOffice editor for internal users
import AgreementCommentPanel from './AgreementCommentPanel'
import AgreementWorkflowStepper from './AgreementWorkflowStepper'
// Unified template-driven workflow page (always on).
import { UnifiedAgreementWorkflow } from '@/features/agreements/components/UnifiedAgreementWorkflow'
import SourceDriftPanel from './SourceDriftPanel'
import {
  AgreementStage,
  AgreementTimelineItem,
  buildAgreementTimeline,
  canResendReviewInvitation,
  getAgreementStage,
  getPrimaryWorkflowAction,
  getStageLabel,
  isNegotiationStage,
} from '@/features/agreements/services/agreementWorkflow'
// NOTE: buildVersionHistory is available in agreementWorkflow if needed for a
// standalone version list, but Version History already renders agreement.documents
// directly in the UI so it is not imported here.

// Component to display signed PDF with authentication
const SignedPDFViewer: React.FC<{
  agreementId: string
  signedDocumentId: string
}> = ({ agreementId, signedDocumentId }) => {
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let blobUrl: string | null = null
    let isMounted = true
    
    const loadPDF = async () => {
      try {
        setLoading(true)
        setError(null)
        
        // Fetch PDF with authentication via axios
        const response = await api.get(
          `/agreements/${agreementId}/signed-document/${signedDocumentId}`,
          { responseType: 'blob' }
        )
        
        if (!isMounted) return
        
        // Create blob URL
        const blob = new Blob([response.data], { type: 'application/pdf' })
        blobUrl = URL.createObjectURL(blob)
        setPdfBlobUrl(blobUrl)
      } catch (err: any) {
        if (!isMounted) return
        console.error('Failed to load signed PDF:', err)
        setError(err.response?.data?.detail || 'Failed to load signed PDF')
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    loadPDF()

    // Cleanup blob URL on unmount or when dependencies change
    return () => {
      isMounted = false
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl)
      }
      // Also cleanup if state has a blob URL
      setPdfBlobUrl((prev) => {
        if (prev) {
          URL.revokeObjectURL(prev)
        }
        return null
      })
    }
  }, [agreementId, signedDocumentId])

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center p-8">
        <p className="text-gray-600">Loading signed document...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="w-full h-full flex items-center justify-center p-8">
        <div className="text-center">
          <p className="text-red-600 font-medium mb-2">Failed to load signed PDF</p>
          <p className="text-sm text-gray-600">{error}</p>
        </div>
      </div>
    )
  }

  if (!pdfBlobUrl) {
    return (
      <div className="w-full h-full flex items-center justify-center p-8">
        <p className="text-gray-600">No PDF available</p>
      </div>
    )
  }

  return (
    <div className="w-full h-full flex flex-col">
      <div className="border-b border-gray-200 p-2 bg-green-50 text-xs text-green-800 text-center">
        ✓ Signed Document - Viewing final executed version with signatures
      </div>
      <div className="flex-1 overflow-hidden">
        <iframe
          src={pdfBlobUrl}
          className="w-full h-full border-0"
          title="Signed Agreement PDF"
          style={{ minHeight: '600px' }}
        />
      </div>
      <div className="border-t border-gray-200 p-2 bg-gray-50 text-xs text-gray-600 text-center">
        Read-only mode - This is the final legacy signed document
      </div>
    </div>
  )
}

interface AgreementVersion {
  id: string
  agreement_id: string
  version_number: number
  file_path: string | null
  document_html: string | null
  uploaded_by: string | null
  uploaded_at: string
  is_signed_version: string
  is_external_visible: string
}

interface AgreementComment {
  id: string
  agreement_id: string
  version_id: string | null
  comment_type: string
  content: string
  created_by: string | null
  created_at: string
}

interface AgreementDocument {
  id: string
  agreement_id: string
  version_number: number
  document_content: any // TipTap JSON (legacy)
  document_file_path?: string | null // Path to DOCX file
  created_from_template_id: string | null
  created_by: string | null
  created_at: string
  updated_at?: string | null // ISO string; changes whenever the callback overwrites the DOCX
  is_signed_version: string
}

/**
 * AgreementChange field reference (kept as documentation — the JSX reads
 * these fields off objects returned by useAgreementChanges, which is loosely
 * typed as `any` at the hook boundary). Lift this into `@/types/agreement.ts`
 * as a follow-up task; that will let the hook be tightly typed too.
 *
 *   interface AgreementChange {
 *     id: string
 *     change_type: 'ADDED' | 'DELETED' | 'MODIFIED'
 *     old_text: string | null
 *     new_text: string | null
 *     section_reference: string | null
 *     paragraph_index: number | null
 *     table_index: number | null
 *     row_index: number | null
 *     cell_index: number | null
 *     created_by: string | null
 *     created_at: string
 *     is_external_change: boolean
 *     is_accepted: boolean
 *     accepted_by: string | null
 *     accepted_at: string | null
 *     document_version_id: string
 *   }
 */

interface Agreement {
  id: string
  site_id: string
  title: string
  agreement_type?: string | null
  status: string
  created_by: string | null
  created_at: string
  updated_at: string
  current_version_id: string | null
  is_legacy: string
  versions: AgreementVersion[]
  documents: AgreementDocument[]
  comments: AgreementComment[]
  can_upload_new_version: boolean
  can_edit: boolean
  can_comment: boolean
  can_save: boolean
  can_move_status: boolean
  is_locked: boolean
  zoho_request_id?: string | null
  signature_status?: string | null
  signature_source?: 'ZOHO' | 'INTERNAL' | null
  signing_stage?: string | null
  signing_progress?: {
    reviewerSigned: boolean
    siteSigned: boolean
  }
  signed_documents?: Array<{
    id: string
    file_path: string
    signed_at: string | null
    downloaded_from_zoho_at: string
  }>
}

interface AgreementTabProps {
  apiBase?: string
}

/** Visual only — maps backend AgreementStatus to badge styles for the status bar */
function agreementStatusBadgeClass(status: string): string {
  const base =
    'inline-flex max-w-full items-center rounded-md border px-2 py-0.5 text-xs font-mono font-semibold uppercase tracking-wide'
  const s = status.toUpperCase()
  switch (s) {
    case 'DRAFT':
      return `${base} border-slate-200 bg-slate-100 text-slate-800`
    case 'UNDER_REVIEW':
    case 'UNDER_NEGOTIATION':
      return `${base} border-amber-200 bg-amber-50 text-amber-900`
    case 'REVIEWED_AND_SIGNED':
      return `${base} border-violet-200 bg-violet-50 text-violet-900`
    case 'FULLY_SIGNED':
      return `${base} border-emerald-200 bg-emerald-50 text-emerald-900`
    case 'READY_FOR_SIGNATURE':
      return `${base} border-blue-200 bg-blue-50 text-blue-900`
    case 'SENT_FOR_SIGNATURE':
      return `${base} border-indigo-200 bg-indigo-50 text-indigo-900`
    case 'EXECUTED':
      return `${base} border-emerald-200 bg-emerald-50 text-emerald-900`
    case 'CLOSED':
      return `${base} border-gray-300 bg-gray-100 text-gray-800`
    default:
      return `${base} border-gray-200 bg-gray-100 text-gray-800`
  }
}

// Engine gate for the primary CDA actions. Keyed by the SAME primaryAction id the
// status ladder uses (getPrimaryWorkflowAction), each entry tests an engine
// available action by its transition destination step — exactly how send-for-review
// matched to==='under_review'. This is the single source for "is this button
// available per the engine"; status still decides what each button DOES + labels.
const AgreementTab: React.FC<AgreementTabProps> = ({ apiBase = '/api' }) => {
  // `studies` used to be destructured here for the loadTemplates fallback
  // path (derive study from site). That path is gone — the hook reacts to
  // selectedStudyId directly. Drop the unused binding to silence the
  // TS6133 warning.
  const { selectedSiteId, selectedStudyId } = useStudySite()
  const [agreement, setAgreement] = useState<Agreement | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [newAgreementTitle, setNewAgreementTitle] = useState('')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('')
  // WORKFLOW_UNIFIED: when on, the whole tabbed page is replaced by the unified
  // template-driven workflow view. Fail-safe false -> today's CDA/CTA tabs.
  const [unified, setUnified] = useState(false)
  // Gate the whole page on the config probe so we never flash the WRONG path: until
  // the flags resolve we render a light loading state, then render the correct path
  // directly (no old CDA/CTA flash before unified:true arrives). Fail-safe: set true
  // even on error so the page still renders (as today's CDA/CTA).
  const [configLoaded, setConfigLoaded] = useState(false)

  // The unified template-driven Agreement page is the permanent product behavior
  // (the WORKFLOW_UNIFIED flag was removed) — always on.
  useEffect(() => {
    setUnified(true)
    setConfigLoaded(true)
  }, [])
  // availableTemplates now comes from useAgreementTemplates() below.
  const [showCompleteReviewModal, setShowCompleteReviewModal] = useState(false)
  const [changingStatus, setChangingStatus] = useState(false)
  // REMOVED: Reset workflow state - not part of production workflow
  // const [resetting, setResetting] = useState(false)
  // const [showResetConfirmModal, setShowResetConfirmModal] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [pinnedOnlyOfficeDocumentId, setPinnedOnlyOfficeDocumentId] = useState<string | null>(null)
  const [editorRefreshTick, setEditorRefreshTick] = useState(0)
  const [hasUnsavedEdits, setHasUnsavedEdits] = useState(false)
  const editorRef = useRef<OnlyOfficeEditorHandle | null>(null)
  const agreementRef = useRef<Agreement | null>(null)
  const lastCheckedAgreementIdRef = useRef<string | null>(null)
  const [resettingWorkflow, setResettingWorkflow] = useState(false)
  const [showReviewModal, setShowReviewModal] = useState(false)
  const [reviewRecipientEmail, setReviewRecipientEmail] = useState('')
  const [reviewMessage, setReviewMessage] = useState('')
  const [sendingForReview, setSendingForReview] = useState(false)
  // `changes`, `allChanges`, `loadingChanges` now come from useAgreementChanges() below.
  const [showChangesPanel, setShowChangesPanel] = useState(false)
  // `reviewTokens` now comes from useAgreementReviewTokens() below.
  const [showReviewConfirmation, setShowReviewConfirmation] = useState(false)
  const [sendingForSignature, setSendingForSignature] = useState(false)
  const [showSignatureModal, setShowSignatureModal] = useState(false)
  const [siteSignerEmail, setSiteSignerEmail] = useState('')
  const [siteProfile, setSiteProfile] = useState<any>(null)
  const lastSendForReviewCallRef = useRef<number>(0)
  const [editLock, setEditLock] = useState<{
    locked: boolean
    locked_by_user_id: string | null
    locked_by_user_name: string | null
    locked_at: string | null
    is_expired: boolean
    can_acquire: boolean
  } | null>(null)
  const [checkingLock, setCheckingLock] = useState(false)
  const [activeTab, setActiveTab] = useState<'cda' | 'cta'>('cda')
  const workflowAgreementType: AgreementWorkflowType = activeTab === 'cta' ? 'CTA' : 'CDA'
  const workflowTabLabel = workflowAgreementType

  // -----------------------------------------------------------------------
  // TanStack Query — Phase 1 of the AgreementTab migration.
  // Replaces three manual `loadX()` fetchers + their hand-rolled state:
  //   * useAgreementTemplates  ← loadTemplates  + availableTemplates state
  //   * useAgreementChanges    ← loadChanges    + (changes, allChanges, loadingChanges)
  //   * useAgreementReviewTokens ← loadReviewTokens + reviewTokens state
  //
  // Hooks auto-refetch on dependency change and on window focus. Mutations
  // below explicitly invalidate the query key on success (see queryClient
  // usage). The deeper `loadAgreement` + `refreshAgreementOnce` polling
  // loop and `checkEditLock` are NOT migrated yet — they're entangled with
  // the OnlyOffice editor lifecycle and agreementRef diffing, which need
  // their own focused refactor.
  // -----------------------------------------------------------------------
  const queryClient = useQueryClient()
  const templatesQuery = useAgreementTemplates(selectedStudyId, {
    enabled: Boolean(selectedStudyId),
  })
  const availableTemplates = templatesQuery.data ?? []
  // The CDA tab below only accepts CDA-typed templates — picking a CTA template
  // here would create an agreement with agreement_type='CTA' that the CDA tab
  // can't drive. Filter at the source so the dropdowns and the empty-state
  // copy stay in sync. CTAWorkflowPanel does its own equivalent filter for CTA.
  const cdaTemplates = availableTemplates.filter(
    (t: any) => t?.template_type === 'CDA'
  )

  const changesQuery = useAgreementChanges(agreement?.id, {
    enabled: Boolean(agreement?.id) && agreement?.status === 'UNDER_REVIEW',
  })
  const changes = changesQuery.data?.pending ?? []
  const allChanges = changesQuery.data?.all ?? []
  const loadingChanges = changesQuery.isFetching

  const reviewTokensQuery = useAgreementReviewTokens(agreement?.id, {
    enabled: Boolean(agreement?.id) && agreement?.status === 'UNDER_REVIEW',
  })
  const reviewTokens = reviewTokensQuery.data ?? []

  // -----------------------------------------------------------------------
  // Phase 2 migration — active agreement is now driven by useAgreementForSite.
  // The hook polls at 30s (paused when tab hidden) which replaces the
  // hand-rolled visibilityState setInterval block that used to live below.
  // The local `agreement` state continues to exist so the rest of the
  // component (and existing mutation handlers) keeps working unchanged;
  // we just sync it from the query result instead of from `loadAgreement`.
  // -----------------------------------------------------------------------
  const agreementQuery = useAgreementForSite(selectedSiteId, selectedStudyId, {
    enabled: workflowAgreementType != null,
    agreementType: workflowAgreementType ?? 'CDA',
    templates: availableTemplates,
  })

  // Reset workflow UI when switching CDA / CTA (separate agreements per type).
  useEffect(() => {
    setAgreement(null)
    setSelectedTemplateId('')
    setShowCreateForm(false)
    setError(null)
    setSelectedVersion(null)
    setPinnedOnlyOfficeDocumentId(null)
    setShowChangesPanel(false)
    setShowReviewModal(false)
    setShowCompleteReviewModal(false)
    setShowSignatureModal(false)
    setShowReviewConfirmation(false)
  }, [activeTab])

  // Sync query → local state. Skips when the query data is the same
  // reference as current state (TanStack Query v5 structural-sharing keeps
  // refs stable when payloads are deeply equal, so identical polls don't
  // cause a state update / re-render).
  useEffect(() => {
    const queryData = agreementQuery.data ?? null
    setAgreement((prev) => (prev === queryData ? prev : queryData))
  }, [agreementQuery.data])

  // The query hook auto-fetches whenever (selectedSiteId, selectedStudyId)
  // change — no explicit loadAgreement() needed on mount or site switch.
  // This effect now only resets ancillary local state when site clears.
  useEffect(() => {
    if (!selectedSiteId) {
      lastCheckedAgreementIdRef.current = null
      setAgreement(null)
    }
  }, [selectedSiteId])

  // Release lock on component unmount or when agreement changes
  useEffect(() => {
    return () => {
      if (agreement) {
        releaseEditLock().catch(console.error)
      }
    }
  }, [agreement?.id])

  // (The legacy engine-gated CDA primary-action probe — gated on the removed
  // WORKFLOW_DRIVES_CDA flag — was deleted. The CDA tab uses the status ladder.)

  useEffect(() => {
    if (agreement) {
      
      // Validate selectedVersion: if it doesn't exist in current documents, reset it
      if (selectedVersion !== null) {
        const hasVersion = agreement.documents?.some(d => d.version_number === selectedVersion)
        if (!hasVersion) {
          setSelectedVersion(null)
        }
      }
      
      // Templates / changes / review-tokens are now driven by the
      // useAgreementTemplates / useAgreementChanges / useAgreementReviewTokens
      // hooks at the top of the component. Their `enabled` flags react to
      // selectedStudyId / agreement.id / agreement.status, so explicit
      // load*() calls here are no longer needed — TanStack Query refetches
      // automatically when those dependencies change.

      // Check edit lock only when agreement ID changes (not on every update)
      if (agreement.documents && agreement.documents.length > 0) {
        if (lastCheckedAgreementIdRef.current !== agreement.id) {
          lastCheckedAgreementIdRef.current = agreement.id
          checkEditLock()
        }
      }

      // Update ref with current agreement — still used by some places
      // (e.g. editor save-callback closures) that read `.current` to avoid
      // capturing a stale `agreement` in their closure.
      agreementRef.current = agreement

      // The hand-rolled visibility-gated 30s setInterval that used to live
      // here is gone. useAgreementForSite() polls every 30s, pauses when
      // the tab is hidden (refetchIntervalInBackground=false), and fires a
      // fresh fetch on focus return (refetchOnWindowFocus=true). Version-
      // change detection (reset selectedVersion when a new version lands)
      // is handled by a separate useEffect below that watches the document
      // list shape.
    } else {
      setSelectedVersion(null)
      agreementRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agreement, selectedStudyId])

  // Version-change detection — formerly inline inside the polling loop.
  // When a new document version lands (count up or max version_number up),
  // reset selectedVersion to null so the UI shows the latest. We track the
  // previous shape in a ref so we can diff against it without forcing the
  // effect to re-run when selectedVersion changes.
  const prevDocsShapeRef = useRef<{ count: number; max: number }>({ count: 0, max: 0 })
  useEffect(() => {
    if (!agreement?.documents || agreement.documents.length === 0) {
      prevDocsShapeRef.current = { count: 0, max: 0 }
      return
    }
    const count = agreement.documents.length
    const max = Math.max(...agreement.documents.map((d) => d.version_number))
    const prev = prevDocsShapeRef.current
    if (count > prev.count || max > prev.max) {
      // Only reset if we already had docs (avoid resetting on the very
      // first load when prev is {0,0} and that's not a "new version", just
      // initial population).
      if (prev.count > 0 && prev.max > 0) {
        setSelectedVersion(null)
      }
    }
    prevDocsShapeRef.current = { count, max }
  }, [agreement])

  // Templates are now fetched via useAgreementTemplates(selectedStudyId)
  // earlier in the component. The hook auto-refetches when selectedStudyId
  // changes, replacing the old "Load templates when study is selected"
  // useEffect + loadTemplates() function. The legacy fallback that derived
  // study_id from selectedSiteId is intentionally dropped — it only ever
  // fired when selectedStudyId was null but selectedSiteId was set, which
  // never happens once StudySiteContext has hydrated (see context
  // bootstrap in src/contexts/StudySiteContext.tsx).

  // Lightweight refresh used after OnlyOffice save and other in-place
  // updates. Does NOT touch the global loading flag — the editor stays
  // mounted while data refreshes silently in the background.
  //
  // Phase 2 migration: this is now a thin wrapper around the TanStack
  // Query refetch. Structural sharing in useQuery keeps the agreement
  // object reference stable when the payload is deeply equal, so the
  // manual ref-based diffing the legacy code did is no longer necessary
  // to suppress redundant renders.
  const refreshAgreementOnce = async (): Promise<Agreement | null> => {
    if (!selectedSiteId || !selectedStudyId) return null
    const result = await agreementQuery.refetch()
    if (result.error) {
      console.error('Failed to refresh agreement after save:', result.error)
      return null
    }
    return result.data ?? null
  }

  // When the comment panel's "Refresh" is clicked, re-init OnlyOffice
  // without doing a full browser refresh.
  const handleCommentPanelRefreshOnlyOffice = async () => {
    setPinnedOnlyOfficeDocumentId(null)
    setSelectedVersion(null)
    await refreshAgreementOnce()
    setEditorRefreshTick(t => t + 1)
  }

  // Phase 2 migration: loadAgreement is now a thin wrapper around the
  // TanStack Query refetch. Keeps the existing call sites (10+ mutation
  // handlers do `await loadAgreement()` after a write) working unchanged —
  // the data flow underneath is now query-driven, not state-driven.
  //
  // Why keep this wrapper at all? Two responsibilities the bare refetch
  // can't take on:
  //   1. Toggling the visible `loading` flag for the "spinner during
  //      explicit refetch" UX. The query's own isFetching is also true
  //      during polls — that's intentionally NOT a spinner.
  //   2. Resetting `lastCheckedAgreementIdRef` so the edit-lock check
  //      runs again when the agreement id changes.
  const loadAgreement = async (skipLoadingState: boolean = false): Promise<Agreement | null> => {
    if (!selectedSiteId || !selectedStudyId) return null
    if (!skipLoadingState) setLoading(true)
    setError(null)
    try {
      const result = await agreementQuery.refetch()
      const data = (result.data ?? null) as Agreement | null
      if (result.error) {
        const err = result.error as any
        if (err?.response?.status !== 404) {
          setError(err?.response?.data?.detail || 'Failed to load agreement')
          console.error('Failed to load agreement:', err)
        }
        return null
      }
      // Reset lock-check ref so a subsequent agreement id change re-triggers
      // the edit-lock probe in the useEffect that watches `agreement`.
      if (data) {
        if (lastCheckedAgreementIdRef.current !== data.id) {
          lastCheckedAgreementIdRef.current = null
        }
      } else {
        lastCheckedAgreementIdRef.current = null
      }
      return data
    } finally {
      if (!skipLoadingState) setLoading(false)
    }
  }

  const handleCreateAgreement = async () => {
    if (!selectedSiteId || !selectedStudyId || !selectedTemplateId) {
      setError('Please select a template')
      return
    }

    setCreating(true)
    setError(null)
    try {
      const title =
        newAgreementTitle.trim() ||
        (workflowAgreementType ? `${workflowAgreementType} Agreement` : 'Agreement')
      const result = await api.post<Agreement>(
        `/sites/${selectedSiteId}/agreements?study_id=${selectedStudyId}`,
        {
          site_id: selectedSiteId,
          title,
          status: 'DRAFT',
          template_id: selectedTemplateId,
        }
      )
      setNewAgreementTitle('')
      setSelectedTemplateId('')
      setShowCreateForm(false)
      // Backend returns either a newly created or existing agreement — open it directly.
      if (result.data) {
        setAgreement(result.data)
      } else {
        await loadAgreement()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create agreement')
      console.error('Failed to create agreement:', err)
    } finally {
      setCreating(false)
    }
  }

  // Unified page: create an agreement for an explicit template id, then refresh so
  // the parent's `agreement` state updates (the unified view then binds + runs the
  // workflow on tpl:<templateId>). Thin wrapper over the same POST as create.
  const createAgreementWithTemplate = async (templateId: string): Promise<void> => {
    if (!selectedSiteId || !selectedStudyId || !templateId) {
      setError('Please select a template')
      return
    }
    setCreating(true)
    setError(null)
    try {
      const result = await api.post<Agreement>(
        `/sites/${selectedSiteId}/agreements?study_id=${selectedStudyId}`,
        { site_id: selectedSiteId, title: 'Agreement', status: 'DRAFT', template_id: templateId },
      )
      // Backend returns the newly created OR existing agreement — open it DIRECTLY
      // (same as handleCreateAgreement). loadAgreement() only refetches the query and
      // returns the data; it does NOT setAgreement, so relying on it here can race and
      // leave the unified view stuck on "Use the previous workflow" (nothing renders).
      if (result.data) {
        setAgreement(result.data)
      } else {
        await loadAgreement()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create agreement')
    } finally {
      setCreating(false)
    }
  }

  // Create document from template for existing agreement (after reset)
  const handleCreateDocumentFromTemplate = async () => {
    if (!agreement || !selectedTemplateId) {
      setError('Please select a template')
      return
    }

    setCreating(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('template_id', selectedTemplateId)
      
      await api.post(`/agreements/${agreement.id}/create-from-template`, formData)
      
      setSelectedTemplateId('')
      
      // Reload agreement to get updated documents
      await loadAgreement()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create document from template')
      console.error('Failed to create document from template:', err)
    } finally {
      setCreating(false)
    }
  }

  // DISABLED: Manual file upload temporarily disabled during workflow restructuring
  const handleUploadVersion = async () => {
    // ⚠️ DISABLED DURING WORKFLOW RESTRUCTURING
    // Manual file upload is temporarily disabled.
    // For new agreements, use template-based creation and the document editor.
    alert('Manual file upload is temporarily disabled during workflow restructuring. Use template-based creation and the document editor instead.')
    return
    if (!agreement || !selectedFile) return

    setUploading(true)
    setError(null)
    try {
      const agreementId = agreement!.id
      const formData = new FormData()
      formData.append('file', selectedFile as File)

      await api.post(`/agreements/${agreementId}/versions`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      
      // Reload agreement to get updated versions
      await loadAgreement()
      setSelectedFile(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload version')
      console.error('Failed to upload version:', err)
    } finally {
      setUploading(false)
    }
  }

  /**
   * Linear workflow: REVIEW → SIGNATURE (backend: UNDER_REVIEW → READY_FOR_SIGNATURE).
   * Reuses PATCH /agreements/{id}/status — server enforces ALLOWED_TRANSITIONS.
   */
  const handleCompleteReviewClick = () => {
    if (!agreement) return
    if (hasUnsavedEdits) {
      const ok = window.confirm(
        'You have unsaved changes. Save your document before completing review?\n\n' +
          'Click OK to stay on this page and save first, or Cancel to continue without saving.'
      )
      if (ok) {
        setError('Please save your changes before completing review.')
        return
      }
    }
    setShowCompleteReviewModal(true)
  }

  const confirmCompleteReview = async () => {
    if (!agreement) return

    setChangingStatus(true)
    setError(null)
    try {
      const response = await api.patch<Agreement>(
        `/agreements/${agreement.id}/status`,
        { status: 'READY_FOR_SIGNATURE' }
      )
      setAgreement(response.data)
      setShowCompleteReviewModal(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to complete review')
      console.error('Failed to complete review:', err)
      setShowCompleteReviewModal(false)
    } finally {
      setChangingStatus(false)
    }
  }

  // REMOVED: Reset workflow handlers - not part of production workflow
  // const handleResetWorkflow = () => { ... }
  // const confirmResetWorkflow = async () => { ... }


  // Check edit lock status
  const checkEditLock = async () => {
    if (!agreement) return null

    setCheckingLock(true)
    try {
      const response = await api.get<{
        locked: boolean
        locked_by_user_id: string | null
        locked_by_user_name: string | null
        locked_at: string | null
        is_expired: boolean
        can_acquire: boolean
      }>(`/agreements/${agreement.id}/edit-lock`)
      const data = response.data
      setEditLock(data)
      return data
    } catch (err: any) {
      console.error('Failed to check edit lock:', err)
      // On error, assume no lock
      const fallback = {
        locked: false,
        locked_by_user_id: null,
        locked_by_user_name: null,
        locked_at: null,
        is_expired: false,
        can_acquire: true,
      }
      setEditLock(fallback)
      return fallback
    } finally {
      setCheckingLock(false)
    }
  }

  // Release edit lock
  const releaseEditLock = async () => {
    if (!agreement) return
    
    try {
      await api.post(`/agreements/${agreement.id}/edit-lock/release`)
      setEditLock({
        locked: false,
        locked_by_user_id: null,
        locked_by_user_name: null,
        locked_at: null,
        is_expired: false,
        can_acquire: true,
      })
    } catch (err: any) {
      console.error('Failed to release edit lock:', err)
      // Continue anyway - lock may have expired
    }
  }

  // Handle save from ONLYOFFICE editor.
  //
  // Versioning policy (mirrors backend logic):
  //   DRAFT / UNDER_REVIEW  → the backend overwrites the existing draft file
  //                           in-place. No new AgreementDocument is created.
  //                           We simply reload the agreement data so the UI
  //                           reflects the latest file content.
  //   Other statuses        → a new version IS created by the backend
  //                           (only reachable via accept_change in practice).
  //
  // Because DRAFT/UNDER_REVIEW saves do not bump the version count, we no
  // longer poll for a version number increase.  Instead we wait a fixed
  // short delay for OnlyOffice to finish writing, then do a lightweight refresh.
  const handleSaveDocument = async () => {
    if (!agreement) return

    try {
      // Release edit lock after saving
      await releaseEditLock()

      // Allow OnlyOffice a moment to finish the callback write before we refresh
      await new Promise(resolve => setTimeout(resolve, 1500))

      // IMPORTANT: Avoid full reloads that can replace document pointers and
      // inadvertently remount the OnlyOffice iframe after save (causing scroll
      // jumps and interaction breaks). This refresh updates state only if the
      // agreement meaningfully changed (e.g., new version created).
      await refreshAgreementOnce()
      setHasUnsavedEdits(false)
    } catch (err: any) {
      console.error('[Save] Failed to refresh after save:', err)
    }
  }
  
  // Reset unsaved edits when version changes
  useEffect(() => {
    setHasUnsavedEdits(false)
  }, [selectedVersion])

  useEffect(() => {
    const loadSiteProfile = async () => {
      if (showSignatureModal && selectedSiteId) {
        try {
          const response = await api.get(`/sites/${selectedSiteId}/profile`)
          setSiteProfile(response.data)
          if (response.data?.authorized_signatory_email) {
            setSiteSignerEmail(response.data.authorized_signatory_email)
          }
        } catch (err: any) {
          console.log('Site profile not found:', err)
          setSiteProfile(null)
        }
      }
    }
    loadSiteProfile()
  }, [showSignatureModal, selectedSiteId])

  const handleSendForSignature = async () => {
    if (!agreement) {
      setError('Agreement not found')
      return
    }

    setSendingForSignature(true)
    setError(null)
    try {
      const formData = new FormData()
      if (siteSignerEmail.trim()) {
        formData.append('site_signer_email', siteSignerEmail.trim())
      }
      const response = await api.post<{
        status: string
        message: string
        sign_link: string
        expires_at: string
        email: string
      }>(`/agreements/${agreement.id}/send-for-signature`, formData)

      setShowSignatureModal(false)
      setSiteSignerEmail('')
      await loadAgreement()
      alert(`Signature link sent to ${response.data.email}\n\nExpires: ${new Date(response.data.expires_at).toLocaleString()}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send for signature')
      console.error('Failed to send for signature:', err)
    } finally {
      setSendingForSignature(false)
    }
  }

  const handleDownloadSignedPDF = async (signedDoc: { id: string; file_path: string }) => {
    try {
      // Use the signed document endpoint
      const response = await api.get(
        `/agreements/${agreement?.id}/signed-document/${signedDoc.id}`,
        { responseType: 'blob' }
      )
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      // Extract file name from path
      const fileName = signedDoc.file_path.split('/').pop() || 'signed_agreement.pdf'
      link.setAttribute('download', fileName)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setError('Failed to download signed PDF')
      console.error('Failed to download signed PDF:', err)
    }
  }

  const handleViewSignedPDF = async (signedDoc: { id: string; file_path: string }) => {
    try {
      // Use the signed document endpoint to get PDF blob
      const response = await api.get(
        `/agreements/${agreement?.id}/signed-document/${signedDoc.id}`,
        { responseType: 'blob' }
      )
      const blob = new Blob([response.data], { type: 'application/pdf' })
      const blobUrl = URL.createObjectURL(blob)
      window.open(blobUrl, '_blank', 'noopener,noreferrer')
      // Clean up after 30 seconds
      setTimeout(() => URL.revokeObjectURL(blobUrl), 30000)
    } catch (err: any) {
      setError('Failed to view signed PDF')
      console.error('Failed to view signed PDF:', err)
    }
  }

  // Legacy signed PDFs are served from storage if present.

  // Changes (track-changes log) are now fetched via useAgreementChanges()
  // at the top of the component. To force a refresh after a mutation,
  // invalidate its query key:
  //
  //   queryClient.invalidateQueries({
  //     queryKey: ['agreement', agreement.id, 'changes'],
  //   })
  //
  // Pending vs all filtering happens inside the hook's queryFn so consumers
  // get { all, pending } back in one shape.
  const refreshChanges = () => {
    if (!agreement?.id) return
    queryClient.invalidateQueries({ queryKey: ['agreement', agreement.id, 'changes'] })
  }

  const handleAcceptChange = async (changeId: string) => {
    if (!agreement) return

    try {
      const response = await api.post<{
        status: string
        message: string
        new_version: number | null
        new_document_id: string | null
      }>(`/agreements/${agreement.id}/changes/${changeId}/accept`)

      // Reload changes list so accepted change disappears from pending panel
      refreshChanges()

      // If a new document version was created, reload the agreement and switch
      // the editor to show the new version so users immediately see the merged result.
      if (response.data.new_version != null) {
        await loadAgreement()
        // Switch editor to the newly created version
        setSelectedVersion(response.data.new_version)
      } else {
        // No new version (text not found in doc) — just refresh agreement state
        await loadAgreement()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to accept change')
      console.error('Failed to accept change:', err)
    }
  }

  const handleRejectChange = async (changeId: string) => {
    if (!agreement) return

    try {
      await api.post(`/agreements/${agreement.id}/changes/${changeId}/reject`)
      // Reload changes
      refreshChanges()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reject change')
      console.error('Failed to reject change:', err)
    }
  }

  // Review tokens are fetched via useAgreementReviewTokens() at the top of
  // the component. To force a refresh after a mutation (create or revoke
  // token) call refreshReviewTokens() — it invalidates the query key, and
  // any active component holding the data gets a fresh fetch.
  const refreshReviewTokens = () => {
    if (!agreement?.id) return
    queryClient.invalidateQueries({
      queryKey: ['agreement', agreement.id, 'review-tokens'],
    })
  }

  const openSendReviewModal = async () => {
    // Trigger a fresh fetch in case the user just regenerated a token in a
    // different tab; await the refetch so the modal opens with the latest
    // list rather than a stale snapshot.
    if (agreement?.id) {
      await reviewTokensQuery.refetch()
    }
    setShowReviewModal(true)
  }

  const handleSendForReview = async () => {
    if (!agreement) {
      setError('Agreement not found')
      return
    }

    if (!reviewRecipientEmail.trim()) {
      setError('Recipient email is required')
      return
    }

    // Debounce: prevent rapid double clicks (2-3 second cooldown)
    const now = Date.now()
    const timeSinceLastCall = now - lastSendForReviewCallRef.current
    if (timeSinceLastCall < 2500) {
      setError('Please wait a moment before sending again')
      return
    }
    lastSendForReviewCallRef.current = now

    // Check if already UNDER_REVIEW with valid token
    if (agreement.status === 'UNDER_REVIEW') {
      const hasValidToken = reviewTokens.some(
        (token) => token.is_active && !token.is_expired
      )
      if (hasValidToken && !showReviewConfirmation) {
        // Show confirmation dialog
        setShowReviewConfirmation(true)
        return
      }
    }

    // If user confirmed or no valid token exists, proceed
    setSendingForReview(true)
    setError(null)
    setShowReviewConfirmation(false)
    
    try {
      const formData = new FormData()
      formData.append('recipient_email', reviewRecipientEmail.trim())
      if (reviewMessage.trim()) {
        formData.append('message', reviewMessage.trim())
      }

      const response = await api.post<{ status: string; message: string; review_link: string; token: string; expires_at: string }>(
        `/agreements/${agreement.id}/send-for-review`,
        formData
      )
      
      // Reload agreement to get updated status
      await loadAgreement()
      // Invalidate review-tokens cache so the modal + any consumer refetches
      refreshReviewTokens()
      
      setShowReviewModal(false)
      setReviewRecipientEmail('')
      setReviewMessage('')
      
      // Show success message
      alert(`Review link sent successfully!\n\nReview Link: ${response.data.review_link}\n\nToken expires: ${new Date(response.data.expires_at).toLocaleString()}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send for review')
      console.error('Failed to send for review:', err)
    } finally {
      setSendingForReview(false)
    }
  }

  const handleResetWorkflow = async () => {
    if (!agreement) return

    const confirmed = window.confirm(
      'This will completely reset the agreement workflow:\n\n' +
      '- Reset status to DRAFT\n' +
      '- Delete ALL comments\n' +
      '- Delete ALL document versions\n' +
      '- Delete ALL legacy versions\n' +
      '- Clear signature fields\n' +
      '- Delete signed documents\n\n' +
      'You will need to select a template again to start fresh.\n\n' +
      'Do you want to continue?'
    )
    if (!confirmed) return

    setResettingWorkflow(true)
    setError(null)
    try {
      const response = await api.delete<{ status: string; message: string; agreement: Agreement }>(
        `/agreements/${agreement.id}/reset`
      )
      // Reload agreement to ensure we have the latest state
      await loadAgreement()
      setSelectedVersion(null) // Reset selected version to null (will show latest or nothing)
      setShowCreateForm(false) // Hide create form if shown
      setSelectedTemplateId('') // Reset template selection
      setHasUnsavedEdits(false) // Clear unsaved edits flag

      // Force a fresh templates fetch after reset — the cached list may be
      // stale if an admin updated templates between mounts. Awaits so the
      // success alert below shows after the list is back.
      if (selectedStudyId) {
        await templatesQuery.refetch()
      }
      
      // Show success message
      alert(response.data.message || 'Agreement workflow reset successfully. Please select a template to start fresh.')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset agreement workflow')
      console.error('Error resetting agreement workflow:', err)
    } finally {
      setResettingWorkflow(false)
    }
  }


  const preferSignedDocumentStatuses = new Set([
    'REVIEWED_AND_SIGNED',
    'FULLY_SIGNED',
    'EXECUTED',
  ])

  /** Match backend _extract_blob_seq: newest file wins on refresh (e.g. after review submit). */
  const extractBlobSeq = (path: string | null | undefined) => {
    if (!path) return 0
    const m = path.match(/_v(\d{3})_/)
    return m ? parseInt(m[1], 10) : 0
  }

  // Get current document content
  const getCurrentDocument = () => {
    if (!agreement || !agreement.documents || agreement.documents.length === 0) {
      return null
    }

    const byFreshness = (a: AgreementDocument, b: AgreementDocument) => {
      const seqDiff = extractBlobSeq(b.document_file_path) - extractBlobSeq(a.document_file_path)
      if (seqDiff !== 0) return seqDiff
      const aTs = new Date(a.updated_at || a.created_at || 0).getTime()
      const bTs = new Date(b.updated_at || b.created_at || 0).getTime()
      return bTs - aTs
    }

    const lockToLatestStatuses = new Set([
      'REVIEWED_AND_SIGNED',
      'FULLY_SIGNED',
      'READY_FOR_SIGNATURE',
      'SENT_FOR_SIGNATURE',
      'EXECUTED',
      'CLOSED',
    ])
    const forceLatest = lockToLatestStatuses.has(String(agreement.status))
    const preferSigned = preferSignedDocumentStatuses.has(String(agreement.status))

    const pickNewestSigned = () => {
      const signed = agreement.documents.filter((d) => d.is_signed_version === 'true')
      if (!signed.length) return null
      return [...signed].sort((a, b) => {
        const v = (b.version_number || 0) - (a.version_number || 0)
        if (v !== 0) return v
        return byFreshness(a, b)
      })[0]
    }

    if (forceLatest || selectedVersion === null) {
      if (preferSigned) {
        const signedDoc = pickNewestSigned()
        if (signedDoc) return signedDoc
      }
      return [...agreement.documents].sort(byFreshness)[0] || agreement.documents[0]
    }

    const sameVersionDocs = agreement.documents
      .filter(d => d.version_number === selectedVersion)
      .sort((a, b) => {
        if (a.is_signed_version === 'true' && b.is_signed_version !== 'true') return -1
        if (b.is_signed_version === 'true' && a.is_signed_version !== 'true') return 1
        return byFreshness(a, b)
      })

    if (sameVersionDocs.length > 0) {
      return sameVersionDocs[0]
    }

    return [...agreement.documents].sort(byFreshness)[0] || agreement.documents[0]
  }
  
  // Get latest version number
  const getLatestVersionNumber = () => {
    if (!agreement || !agreement.documents || agreement.documents.length === 0) {
      return null
    }
    if (preferSignedDocumentStatuses.has(String(agreement.status))) {
      const signed = agreement.documents
        .filter((d) => d.is_signed_version === 'true')
        .sort((a, b) => b.version_number - a.version_number)
      if (signed.length > 0) {
        return signed[0].version_number
      }
    }
    return Math.max(...agreement.documents.map(d => d.version_number))
  }
  
  // Check if current selected version is the latest (and thus editable)
  // Uses backend permission flags - no hardcoded status checks
  const isCurrentVersionEditable = () => {
    if (!agreement) return false
    const currentDoc = getCurrentDocument()
    const latestVersion = getLatestVersionNumber()
    if (!currentDoc || !latestVersion) {
      return false
    }
    const isLatest = currentDoc.version_number === latestVersion
    // Use backend can_edit flag (no hardcoded status logic)
    const canEdit = agreement.can_edit
    // Only latest version can be edited, and only if backend says can_edit
    return isLatest && canEdit
  }
  
  // Check if current version can be saved (creates new version)
  // Uses backend can_save flag - no hardcoded status checks
  const canSaveCurrentVersion = () => {
    if (!agreement) return false
    const currentDoc = getCurrentDocument()
    const latestVersion = getLatestVersionNumber()
    if (!currentDoc || !latestVersion) return false
    const isLatest = currentDoc.version_number === latestVersion
    // Use backend can_save flag (no hardcoded status logic)
    const canSave = agreement.can_save
    // Only latest version can be saved
    return isLatest && canSave
  }

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleString()
    } catch {
      return dateString
    }
  }

  if (!selectedStudyId || !selectedSiteId) {
    return (
      <SiteSelectionPrompt
        title="Agreements"
        message={
          !selectedStudyId
            ? 'Please select a study from the top navigation, then choose a site to manage agreements.'
            : 'Please select a site from the top navigation to load or create agreements for this site.'
        }
      />
    )
  }

  const currentStage: AgreementStage = agreement ? getAgreementStage(agreement.status) : 'PREPARATION'
  const currentStageLabel = getStageLabel(currentStage)

  // Activity Timeline shows ONLY workflow-level events (Agreement created,
  // Sent for review, Sent for signature, etc.).
  // Document version events live in the Version History section below the editor.
  // Negotiation events (external changes, accepted/rejected) live in the
  // External Changes panel. No changes or documents are passed here.
  const timeline: AgreementTimelineItem[] = agreement
    ? buildAgreementTimeline(agreement)
    : []

  // Compute latest external review info for negotiation visibility
  const externalChanges = allChanges.filter((c) => c.is_external_change)
  const latestExternalChange =
    externalChanges.length > 0
      ? externalChanges.reduce((latest, current) =>
          new Date(current.created_at).getTime() > new Date(latest.created_at).getTime()
            ? current
            : latest
        )
      : null
  const externalChangeCount = externalChanges.length

  const primaryAction = agreement ? getPrimaryWorkflowAction(agreement.status) : 'none'
  // The CDA tab's primary buttons follow the status ladder (the legacy engine-gated
  // override was removed with WORKFLOW_DRIVES_CDA).
  const showAction = (key: string) => primaryAction === key

  const signingProgress = agreement?.signing_progress ?? { reviewerSigned: false, siteSigned: false }
  const hasLegacySignedPdf = Boolean(agreement?.signed_documents && agreement.signed_documents.length > 0)

  return (
    <div className="flex flex-col h-full bg-gray-50 p-6 overflow-y-auto" data-testid="agreements-workflow">
      {/* Header — only for the legacy CDA/CTA tabs. In the UNIFIED runner the big
          title + subtitle wasted vertical space (the slim runner header already
          shows the workflow name + status), so we drop it there and let the
          document/panels start near the top. */}
      {configLoaded && !unified && (
        <div className="mb-4">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Agreement Workflow</h1>
          <p className="text-gray-600">Follow the agreement from preparation through signature to completion.</p>
        </div>
      )}

      {/* Until the workflow config resolves we render NEITHER path — a brief loading
          state — so the old CDA/CTA UI never flashes before unified:true arrives. */}
      {!configLoaded && (
        <div className="flex items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white p-10 text-sm text-gray-500 shadow-sm">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
          Loading workflow…
        </div>
      )}

      {/* WORKFLOW_UNIFIED: one template-driven flow replaces the CDA/CTA tabs.
          The type is a read-only label; it does not branch logic. Flag OFF -> the
          tabs below render byte-for-byte as today (the unified block is hidden and
          every tab block is gated on !unified). Gated on configLoaded so the correct
          path renders directly with no flash. */}
      {configLoaded && unified && (
        <>
          {/* #6: unobtrusive warn surface — source-backed fields that drifted from their
              source. Renders nothing unless this agreement has drift. */}
          {agreement?.id && <SourceDriftPanel agreementId={agreement.id} />}
          <UnifiedAgreementWorkflow
            agreement={agreement as any}
            templates={availableTemplates as any}
            creating={creating}
            onCreateAgreement={createAgreementWithTemplate}
            onAfterReset={async () => { await loadAgreement() }}
            siteId={selectedSiteId}
            studyId={selectedStudyId}
          />
        </>
      )}

      {/* Tab navigation: CDA | CTA */}
      {configLoaded && !unified && (
      <div className="mb-4 border-b border-gray-200">
        <nav className="-mb-px flex gap-x-4">
          {(['cda', 'cta'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`py-2 px-1 border-b-2 text-sm font-semibold uppercase tracking-wide transition-colors
                ${activeTab === tab
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
            >
              {tab.toUpperCase()}
            </button>
          ))}
        </nav>
      </div>
      )}

      {/* CTA workflow — REMOVED (dead): the legacy CTAWorkflowPanel only rendered in the
          !unified branch, and `unified` is permanently true (WORKFLOW_UNIFIED removed), so
          this never rendered. The CTA agreement page now runs on the generic engine via
          UnifiedAgreementWorkflow above. (The remaining !unified scaffolding below is also
          dead; left untouched in this narrow cleanup.) */}

      {/* CDA content — the hardcoded CDA panel (the legacy engine-driven runner-in-
          CDA-tab path was removed with WORKFLOW_DRIVES_CDA). */}
      {configLoaded && !unified && activeTab === 'cda' && <>

      {/* Linear workflow stepper (visual only; status from getAgreementStage) */}
      {agreement && (
        <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <AgreementWorkflowStepper currentStage={currentStage} />
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      {/* Create Agreement Form */}
      {!agreement && !loading && !agreementQuery.isFetching && (
        <div className="mb-6 p-4 bg-white border border-gray-200 rounded-lg">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Create New {workflowTabLabel} Agreement
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            New {workflowTabLabel} agreements must be created from a {workflowTabLabel} template.
            Please select a template to proceed.
          </p>
          {!showCreateForm ? (
            <button
              onClick={() => setShowCreateForm(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              data-testid="agreement-create-from-template"
            >
              Create from Template
            </button>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Template <span className="text-red-500">*</span>
                </label>
                <select
                  value={selectedTemplateId}
                  onChange={(e) => setSelectedTemplateId(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                  required
                >
                  <option value="">Select a template...</option>
                  {cdaTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.template_name}
                    </option>
                  ))}
                </select>
                {cdaTemplates.length === 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    No active CDA templates found. Upload a template with Type = CDA in the Template Library first.
                  </p>
                )}
              </div>
              {/* Agreement Title field removed as per requirement */}
              {/* Create (the legacy engine-driven CDA workflow chooser/builder was
                  removed with WORKFLOW_DRIVES_CDA). */}
              <div className="flex gap-2">
                <button
                  onClick={handleCreateAgreement}
                  disabled={creating || !selectedTemplateId}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
                >
                  {creating ? 'Creating...' : 'Create'}
                </button>
                <button
                  onClick={() => {
                    setShowCreateForm(false)
                    setNewAgreementTitle('')
                  }}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Loading State */}
      {(loading || agreementQuery.isFetching) && !agreement && (
        <div className="text-center p-8">
          <p className="text-sm text-gray-600 mt-2">Loading {workflowTabLabel} agreement...</p>
        </div>
      )}

      {/* Agreement Display */}
      {agreement && (
        <div className="space-y-6">
          {/* Agreement Status */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <div className="flex items-start justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-900">Agreement Status</h2>
              <button
                type="button"
                onClick={handleResetWorkflow}
                disabled={resettingWorkflow}
                className="inline-flex items-center rounded-md border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 shadow-sm hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {resettingWorkflow ? 'Resetting...' : 'Reset Workflow'}
              </button>
            </div>
            <div className="space-y-4">
              <div
                className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-gray-100 pb-4 md:justify-between md:gap-x-8"
                role="group"
                aria-label="Agreement summary"
              >
                <div className="info-item flex min-w-0 max-w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 md:max-w-[min(100%,28rem)]">
                  <span className="shrink-0 text-sm text-gray-500">Title:</span>
                  <span className="min-w-0 font-semibold text-gray-900" title={agreement.title}>
                    {agreement.title}
                  </span>
                </div>

                <div className="info-item flex min-w-0 max-w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 md:border-l md:border-gray-200 md:pl-8">
                  <span className="shrink-0 text-sm text-gray-500">Current Stage:</span>
                  <span className="font-semibold text-blue-900">{currentStageLabel}</span>
                </div>

                <div className="info-item flex min-w-0 max-w-full flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-x-2 md:border-l md:border-gray-200 md:pl-8">
                  <span className="shrink-0 text-sm text-gray-500">System status:</span>
                  <span className={agreementStatusBadgeClass(agreement.status)}>
                    {agreement.status.replace(/_/g, ' ')}
                  </span>
                </div>

                <div className="info-item flex min-w-0 max-w-full flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-x-2 md:border-l md:border-gray-200 md:pl-8">
                  <span className="shrink-0 text-sm text-gray-500">Signature flow:</span>
                  <span className="font-semibold text-gray-900">{agreement.signature_source || 'ZOHO'}</span>
                </div>
              </div>

              {/* Linear workflow: exactly one primary action per conceptual stage (see agreementWorkflow.ts). */}
              {agreement.documents && agreement.documents.length > 0 && (
                <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4" data-testid="agreement-next-step">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">
                    Next step
                  </p>

                  {showAction('mark_ready_send_review') && (
                    <div>
                      <button
                        type="button"
                        onClick={openSendReviewModal}
                        disabled={sendingForReview}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:bg-gray-400 disabled:cursor-not-allowed"
                      >
                        {sendingForReview ? 'Sending…' : 'Mark as Ready & Send for Review'}
                      </button>
                      <p className="text-xs text-gray-600 mt-2">
                        Emails a secure link and moves the agreement into review (same behavior as the former
                        &quot;Send for Review&quot; action).
                      </p>
                    </div>
                  )}

                  {showAction('complete_review') && (
                    <div className="space-y-3">
                      <div>
                        <button
                          type="button"
                          onClick={handleCompleteReviewClick}
                          disabled={changingStatus}
                          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium disabled:bg-gray-400 disabled:cursor-not-allowed"
                        >
                          {changingStatus ? 'Processing…' : 'Complete Review'}
                        </button>
                        <p className="text-xs text-gray-600 mt-2">
                          Closes the review round and advances to the internal signing stage.
                        </p>
                      </div>
                      {canResendReviewInvitation(agreement.status) && (
                        <div>
                          <button
                            type="button"
                            onClick={openSendReviewModal}
                            disabled={sendingForReview}
                            className="text-sm text-blue-700 underline hover:text-blue-900 disabled:opacity-50"
                          >
                            Resend review invitation (same email flow)
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {showAction('send_signature') && (
                    <div>
                      <button
                        type="button"
                        onClick={() => setShowSignatureModal(true)}
                        className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-medium"
                      >
                        Send for Signature
                      </button>
                      <p className="text-xs text-gray-600 mt-2">
                        Sends a secure email link to the signer. OTP verification is required before signing.
                      </p>
                    </div>
                  )}

                  {primaryAction === 'sync_signature' && (
                    <div>
                      <p className="text-sm text-blue-900 font-medium mb-2">Waiting for signature</p>
                      <p className="text-xs text-gray-600">
                        A secure signing link has been sent. The document remains signable until the agreement reaches `FULLY_SIGNED`.
                      </p>
                    </div>
                  )}

                  {primaryAction === 'none' && currentStage === 'COMPLETED' && (
                    <p className="text-sm text-gray-600">No workflow actions — this agreement is finished.</p>
                  )}

                  {primaryAction === 'none' && currentStage !== 'COMPLETED' && (
                    <p className="text-sm text-gray-600">
                      No primary workflow action for this system status. If something looks wrong, use Activity
                      Timeline below or contact support.
                    </p>
                  )}
                </div>
              )}

              <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-xs text-blue-800 font-medium mb-2">Signing progress</p>
                <div className="flex flex-wrap gap-2">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${signingProgress.reviewerSigned ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
                    Reviewer: {signingProgress.reviewerSigned ? 'Signed' : 'Pending'}
                  </span>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${signingProgress.siteSigned ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
                    Site: {signingProgress.siteSigned ? 'Signed' : 'Pending'}
                  </span>
                  {agreement.signing_stage && (
                    <span className="px-2 py-1 rounded text-xs font-medium bg-slate-100 text-slate-800">
                      Stage: {agreement.signing_stage.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
              </div>

              {/* Show message when no documents exist */}
              {(!agreement.documents || agreement.documents.length === 0) && (
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm font-semibold text-blue-900 mb-1">
                    📄 No document versions found
                  </p>
                  <p className="text-sm text-blue-800">
                    Please select a template below to create the initial document version.
                  </p>
                </div>
              )}

              {/* While out for signature, signed PDF may appear after sync (non-primary document actions). */}
              {agreement.status === 'SENT_FOR_SIGNATURE' &&
                agreement.signed_documents &&
                agreement.signed_documents.length > 0 && (
                  <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <p className="text-xs text-blue-800 font-medium mb-2">Signed document available</p>
                    {agreement.signed_documents.map((doc) => (
                      <div key={doc.id} className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleViewSignedPDF(doc)}
                            className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 font-medium"
                          >
                            View Signed PDF
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDownloadSignedPDF(doc)}
                            className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                          >
                            Download Signed PDF
                          </button>
                        </div>
                        {doc.signed_at && (
                          <p className="text-xs text-gray-600">
                            Signed: {new Date(doc.signed_at).toLocaleString()}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

              {/* Executed Status - Show signed documents */}
              {agreement.status === 'EXECUTED' && agreement.signed_documents && agreement.signed_documents.length > 0 && (
                <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
                  <p className="text-sm text-green-800 font-medium mb-2">
                    ✓ Agreement Executed
                  </p>
                  {agreement.signed_documents.map((doc) => (
                    <div key={doc.id} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleViewSignedPDF(doc)}
                          className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 font-medium"
                        >
                          View Signed PDF
                        </button>
                        <button
                          onClick={() => handleDownloadSignedPDF(doc)}
                          className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                        >
                          Download Signed PDF
                        </button>
                      </div>
                      {doc.signed_at && (
                        <p className="text-xs text-gray-600">
                          Signed: {new Date(doc.signed_at).toLocaleString()}
                        </p>
                      )}
                      <p className="text-xs text-gray-500">
                        Stored at: {new Date(doc.downloaded_from_zoho_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              
              {/* REMOVED: Reset Workflow Button - not part of production workflow */}
            </div>
          </div>

          {/* Conditional Rendering: Legacy vs New Agreement */}
          {/* Auto-detect legacy: if has versions but no documents, treat as legacy */}
          {(() => {
            // Auto-detect legacy status (fallback if backend flag is incorrect)
            const hasVersions = agreement.versions && agreement.versions.length > 0
            const hasDocuments = agreement.documents && agreement.documents.length > 0
            const isLegacyByData = hasVersions && !hasDocuments
            const effectiveIsLegacy = agreement.is_legacy === 'true' || isLegacyByData

            // Render legacy vs new agreement flows without a ternary to avoid JSX parsing issues
            if (effectiveIsLegacy) {
              /* LEGACY AGREEMENT: Show file-based workflow */
              return (
                <div className="bg-white border border-gray-200 rounded-lg p-6">
              <h2 className="text-xl font-bold text-gray-900 mb-4">Versions (Legacy)</h2>
              
              {/* Upload New Version - Only for legacy agreements */}
              {agreement.can_upload_new_version && (
                <div className="mb-4 p-4 bg-gray-50 rounded-lg">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Upload New Version</h3>
                  {/* Use backend is_locked flag instead of hardcoded status check */}
                  {agreement.is_locked ? (
                    <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                      <p className="text-sm text-yellow-800">
                        Version uploads are locked. Agreement is locked.
                      </p>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <input
                        type="file"
                        onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                        className="px-4 py-2 border border-gray-300 rounded-lg"
                        disabled={uploading}
                      />
                      <button
                        onClick={handleUploadVersion}
                        disabled={!selectedFile || uploading}
                        className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400"
                      >
                        {uploading ? 'Uploading...' : 'Upload Version'}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Legacy Versions List */}
              {agreement.versions.length === 0 ? (
                <p className="text-gray-600">No versions uploaded yet.</p>
              ) : (
                <div className="space-y-2">
                  {agreement.versions.map((version) => {
                    let badgeLabel = 'Draft'
                    let badgeColor = 'bg-gray-100 text-gray-800'

                    if (version.is_signed_version === 'true') {
                      badgeLabel = 'Signed'
                      badgeColor = 'bg-green-100 text-green-800'
                    } else if (version.is_external_visible === 'true') {
                      badgeLabel = 'Shared'
                      badgeColor = 'bg-blue-100 text-blue-800'
                    }

                    return (
                      <div
                        key={version.id}
                        className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50"
                      >
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="flex items-center gap-2 mb-2">
                              <p className="font-semibold text-gray-900">
                                Version {version.version_number}
                              </p>
                              <span className={`px-2 py-1 ${badgeColor} text-xs rounded font-medium`}>
                                {badgeLabel}
                              </span>
                            </div>
                            <p className="text-sm text-gray-600">
                              Uploaded by: {version.uploaded_by || 'System'}
                            </p>
                            <p className="text-sm text-gray-600">
                              Uploaded at: {formatDate(version.uploaded_at)}
                            </p>
                            {version.file_path && (
                              <p className="text-sm text-gray-600">
                                File: {version.file_path.split('/').pop()}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
              )
            }

            // NEW AGREEMENT: Show template-based document workflow
            return (
              <div
                className="bg-white border border-gray-200 rounded-lg p-6 flex flex-col"
                style={{ minHeight: '700px', height: '100%' }}
              >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-gray-900">Document Editor</h2>
                  {isNegotiationStage(agreement.status) && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                      Negotiation in Progress
                    </span>
                  )}
                  {isNegotiationStage(agreement.status) && changes.length > 0 && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      External Changes Pending ({changes.length})
                    </span>
                  )}
                </div>
                {/* Show Changes Panel Button - Only for negotiation stage */}
                {isNegotiationStage(agreement.status) && changes.length > 0 && (
                  <button
                    onClick={() => setShowChangesPanel(!showChangesPanel)}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium flex items-center gap-2"
                  >
                    {showChangesPanel ? 'Hide Changes' : 'Show Changes'}
                  </button>
                )}
              </div>

              {/* Latest External Review Summary */}
              {agreement.status === 'UNDER_REVIEW' && latestExternalChange && (
                <div className="mb-4 p-3 bg-blue-50 border border-blue-100 rounded-md text-xs text-blue-900 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                  <div>
                    <span className="font-semibold">Last external update:</span>{' '}
                    {formatDate(latestExternalChange.created_at)}
                  </div>
                  <div>
                    <span className="font-semibold">Changes detected:</span>{' '}
                    {externalChangeCount} submitted by external reviewer
                    {latestExternalChange.created_by
                      ? ` (${latestExternalChange.created_by})`
                      : '.'}
                  </div>
                </div>
              )}

              {/* Document Editor */}
              {(() => {
                const docCount = agreement.documents?.length || 0

                // No documents - show template selection to start fresh
                if (!docCount) {
                  return (
                    <div className="space-y-4">
                      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                        <p className="text-sm font-semibold text-blue-900 mb-2">
                          📄 No document versions found
                        </p>
                        <p className="text-sm text-blue-800">
                          Please select a template to create the initial document version.
                        </p>
                      </div>

                      {/* Template Selection Form */}
                      <div className="p-4 border border-gray-200 rounded-lg bg-gray-50">
                        <h3 className="text-sm font-semibold text-gray-700 mb-3">Select Template</h3>
                        {cdaTemplates.length === 0 ? (
                          <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                            <p className="text-sm text-yellow-800 font-medium mb-2">
                              ⚠️ No CDA templates available
                            </p>
                            <p className="text-sm text-yellow-700">
                              Upload a template with Type = CDA in the Template Library first.
                              {selectedStudyId ? (
                                <span> Templates are loaded for study: {selectedStudyId}</span>
                              ) : (
                                <span> No study selected. Please select a study first.</span>
                              )}
                            </p>
                            <button
                              onClick={() => templatesQuery.refetch()}
                              className="mt-2 px-3 py-1 bg-yellow-600 text-white text-sm rounded hover:bg-yellow-700"
                            >
                              🔄 Retry Loading Templates
                            </button>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            <select
                              value={selectedTemplateId}
                              onChange={(e) => setSelectedTemplateId(e.target.value)}
                              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                            >
                              <option value="">-- Select Template --</option>
                              {cdaTemplates.map((template) => (
                                <option key={template.id} value={template.id}>
                                  {template.template_name}
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={handleCreateDocumentFromTemplate}
                              disabled={!selectedTemplateId || creating}
                              className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
                            >
                              {creating ? 'Creating Document...' : 'Create Document from Template'}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                }

                // Has documents - show editor, changes, and history
                return (
                  <div className="space-y-4">
                    {/* Version Selector (internal audit; latest is default) */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Document Version:
                      </label>
                      <select
                        value={selectedVersion ?? getLatestVersionNumber() ?? ''}
                        onChange={(e) => {
                          const version = e.target.value ? parseInt(e.target.value) : null
                          setSelectedVersion(version)
                        }}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm"
                      >
                        {agreement.documents
                          .sort((a, b) => {
                            const v = b.version_number - a.version_number
                            if (v !== 0) return v
                            return extractBlobSeq(b.document_file_path) - extractBlobSeq(a.document_file_path)
                          })
                          .map((doc) => {
                            const latestSigned = agreement.documents
                              .filter((d) => d.is_signed_version === 'true')
                              .sort((a, b) => b.version_number - a.version_number)[0]
                            const isNewestSigned =
                              preferSignedDocumentStatuses.has(String(agreement.status)) &&
                              latestSigned?.id === doc.id
                            const label =
                              isNewestSigned || doc.version_number === getLatestVersionNumber()
                                ? 'Current version'
                                : `Version ${doc.version_number}`
                            return (
                              <option key={doc.id} value={doc.version_number}>
                                {label} {doc.is_signed_version === 'true' ? '(Signed)' : ''}
                              </option>
                            )
                          })}
                      </select>
                      {(() => {
                        const currentVersion = selectedVersion ?? getLatestVersionNumber()
                        const latestVersion = getLatestVersionNumber()
                        if (currentVersion && latestVersion && currentVersion !== latestVersion) {
                          return (
                            <p className="text-xs text-yellow-700 mt-1 bg-yellow-50 border border-yellow-200 rounded px-2 py-1">
                              Viewing older version (read-only)
                            </p>
                          )
                        }
                        return null
                      })()}
                    </div>

                    {/* Document Editor or Signed PDF Viewer */}
                    <div
                      className={`flex-1 border border-gray-200 rounded-lg bg-white overflow-hidden flex ${
                        showChangesPanel ? 'flex-row' : 'flex-col'
                      }`}
                      style={{ minHeight: '600px', height: '100%' }}
                    >
                      {/* Changes Panel - Sidebar */}
                      {showChangesPanel && (
                        <div className="w-80 border-r border-gray-200 bg-gray-50 overflow-y-auto flex flex-col">
                          <div className="p-4 border-b border-gray-200 bg-white">
                            <h3 className="text-lg font-semibold text-gray-900">External Changes</h3>
                            <p className="text-xs text-gray-600 mt-1">
                              Review changes submitted by external site
                            </p>
                          </div>
                          <div className="flex-1 p-4 space-y-3">
                            {loadingChanges ? (
                              <div className="text-center py-8">
                                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                                <p className="text-sm text-gray-600 mt-2">Loading changes...</p>
                              </div>
                            ) : changes.length === 0 ? (
                              <div className="text-center py-8">
                                <p className="text-sm text-gray-600">No pending external changes</p>
                              </div>
                            ) : (
                              changes.map((change) => {
                                const getChangeTypeColor = (type: string) => {
                                  switch (type) {
                                    case 'ADDED':
                                      return 'bg-green-100 text-green-800 border-green-200'
                                    case 'DELETED':
                                      return 'bg-red-100 text-red-800 border-red-200'
                                    case 'MODIFIED':
                                      return 'bg-yellow-100 text-yellow-800 border-yellow-200'
                                    default:
                                      return 'bg-gray-100 text-gray-800 border-gray-200'
                                  }
                                }

                                const getChangeTypeIcon = (type: string) => {
                                  switch (type) {
                                    case 'ADDED':
                                      return '+'
                                    case 'DELETED':
                                      return '−'
                                    case 'MODIFIED':
                                      return '~'
                                    default:
                                      return '•'
                                  }
                                }

                                return (
                                  <div
                                    key={change.id}
                                    className={`p-3 border rounded-lg ${getChangeTypeColor(change.change_type)}`}
                                  >
                                    <div className="flex items-start justify-between mb-2">
                                      <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1">
                                          <span className="font-bold text-sm">
                                            {getChangeTypeIcon(change.change_type)}
                                          </span>
                                          <span className="text-xs font-semibold uppercase">
                                            {change.change_type}
                                          </span>
                                          {change.section_reference && (
                                            <span className="text-xs font-medium opacity-75">
                                              {change.section_reference}
                                            </span>
                                          )}
                                        </div>
                                        {change.old_text && change.change_type !== 'ADDED' && (
                                          <div className="mb-2">
                                            <p className="text-xs font-medium mb-1 opacity-75">Old:</p>
                                            <p className="text-xs line-through bg-white bg-opacity-50 p-2 rounded">
                                              {change.old_text.substring(0, 100)}
                                              {change.old_text.length > 100 ? '...' : ''}
                                            </p>
                                          </div>
                                        )}
                                        {change.new_text && change.change_type !== 'DELETED' && (
                                          <div>
                                            <p className="text-xs font-medium mb-1 opacity-75">New:</p>
                                            <p className="text-xs bg-white bg-opacity-50 p-2 rounded">
                                              {change.new_text.substring(0, 100)}
                                              {change.new_text.length > 100 ? '...' : ''}
                                            </p>
                                          </div>
                                        )}
                                        <p className="text-xs opacity-75 mt-2">
                                          {new Date(change.created_at).toLocaleString()}
                                        </p>
                                      </div>
                                    </div>
                                    <div className="flex gap-2 mt-2">
                                      <button
                                        onClick={() => handleAcceptChange(change.id)}
                                        className="flex-1 px-2 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700 font-medium"
                                      >
                                        Accept
                                      </button>
                                      <button
                                        onClick={() => handleRejectChange(change.id)}
                                        className="flex-1 px-2 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 font-medium"
                                      >
                                        Reject
                                      </button>
                                    </div>
                                  </div>
                                )
                              })
                            )}
                          </div>
                        </div>
                      )}

                      {/* Document Editor Container */}
                      <div className={`flex-1 flex flex-col ${showChangesPanel ? '' : 'w-full'}`}>
                        {(() => {
                          const currentDoc = getCurrentDocument()
                          const isSigned = currentDoc?.is_signed_version === 'true'

                          // Legacy signed PDFs remain viewable; internal signed DOCX versions
                          // continue through the normal OnlyOffice read-only path.
                          if (isSigned && hasLegacySignedPdf) {
                            if (agreement.signed_documents && agreement.signed_documents.length > 0) {
                              const signedDoc = agreement.signed_documents[0]
                              return (
                                <SignedPDFViewer
                                  agreementId={agreement.id}
                                  signedDocumentId={signedDoc.id}
                                />
                              )
                            }

                            return (
                              <div className="w-full h-full flex flex-col items-center justify-center p-8">
                                <div className="text-center">
                                  <p className="text-yellow-800 font-medium mb-2">
                                    ⚠️ Signed version selected, but signed PDF is not yet available
                                  </p>
                                  <p className="text-sm text-gray-600 mb-4">
                                    The signed PDF was not stored for this legacy version, so it cannot be displayed.
                                  </p>
                                </div>
                              </div>
                            )
                          }

                          // If no current document, show message to create one
                          if (!currentDoc) {
                            return (
                              <div className="w-full h-full flex items-center justify-center p-8">
                                <div className="text-center">
                                  <p className="text-gray-600 mb-4">
                                    No document available. Please select a template to create a new document.
                                  </p>
                                </div>
                              </div>
                            )
                          }

                          // Check if document has DOCX file path
                          if (currentDoc.document_file_path) {
                            // Check edit lock before rendering editor
                            if (checkingLock) {
                              return (
                                <div className="w-full h-full flex items-center justify-center p-8">
                                  <div className="text-center">
                                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                                    <p className="text-gray-600 mt-2">Checking edit lock...</p>
                                  </div>
                                </div>
                              )
                            }

                            // If locked by another user and not expired, show lock message
                            if (
                              editLock &&
                              editLock.locked &&
                              !editLock.can_acquire &&
                              isCurrentVersionEditable()
                            ) {
                              const lockedAt = editLock.locked_at
                                ? new Date(editLock.locked_at).toLocaleString()
                                : 'Unknown'
                              return (
                                <div className="w-full h-full flex items-center justify-center p-8">
                                  <div className="text-center max-w-md">
                                    <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                                      <p className="text-yellow-800 font-semibold mb-2">
                                        Document Currently Being Edited
                                      </p>
                                      <p className="text-sm text-yellow-700 mb-1">
                                        This document is currently being edited by another user.
                                      </p>
                                      {editLock.locked_by_user_name && (
                                        <p className="text-sm text-yellow-700 mb-1">
                                          Editor: <strong>{editLock.locked_by_user_name}</strong>
                                        </p>
                                      )}
                                      <p className="text-xs text-yellow-600">Locked at: {lockedAt}</p>
                                    </div>
                                    <div className="flex gap-2 justify-center">
                                      <button
                                        onClick={async () => {
                                          // Manual refresh should not keep any stale forced document pin.
                                          setPinnedOnlyOfficeDocumentId(null)
                                          // Re-resolve document to latest selection logic after refresh.
                                          setSelectedVersion(null)
                                          await checkEditLock()
                                          await loadAgreement()
                                          // In-app Refresh must re-init OnlyOffice even if doc id/path is unchanged.
                                          setEditorRefreshTick((t) => t + 1)
                                        }}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                                      >
                                        Refresh
                                      </button>
                                      <button
                                        onClick={async () => {
                                          setPinnedOnlyOfficeDocumentId(null)
                                          setSelectedVersion(null)
                                          const latest = await checkEditLock()
                                          if (latest?.can_acquire) {
                                            // We can now acquire the lock; refresh agreement data
                                            await loadAgreement()
                                            setEditorRefreshTick((t) => t + 1)
                                          }
                                        }}
                                        disabled={!editLock?.can_acquire}
                                        className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                                      >
                                        Request Editing Access
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              )
                            }

                            const currentVersionNumber = currentDoc.version_number
                            if (!currentVersionNumber) {
                              return (
                                <div className="w-full h-full flex items-center justify-center p-8">
                                  <div className="text-center">
                                    <p className="text-red-600 mb-2">
                                      Error: Document version number is missing
                                    </p>
                                  </div>
                                </div>
                              )
                            }
                            const lockToLatestStatuses = new Set([
                              'REVIEWED_AND_SIGNED',
                              'READY_FOR_SIGNATURE',
                              'SENT_FOR_SIGNATURE',
                              'EXECUTED',
                              'CLOSED',
                            ])
                            const forceLatest = lockToLatestStatuses.has(String(agreement.status))
                            const configEndpoint = pinnedOnlyOfficeDocumentId
                              ? `/agreements/${agreement.id}/onlyoffice-config?document_id=${pinnedOnlyOfficeDocumentId}`
                              : forceLatest
                                ? `/agreements/${agreement.id}/onlyoffice-config`
                                : `/agreements/${agreement.id}/onlyoffice-config?version=${currentVersionNumber}`
                            // Remount ONLY when the *document identity* changes (different AgreementDocument id),
                            // agreement status changes (permission/mode changes), or when we explicitly request it
                            // via editorRefreshTick (e.g. user clicks "Refresh").
                            //
                            // IMPORTANT: Do NOT key off document_file_path. In production, a save can produce a new
                            // blob path, which would force an iframe remount and break interaction / scroll position
                            // even though the editor session can continue showing the updated content.
                            const editorKey = `editor-${currentDoc.id}-${agreement.status}-${editorRefreshTick}`

                            // Show comment panel alongside the editor when the
                            // agreement is in UNDER_REVIEW / UNDER_NEGOTIATION status
                            // (i.e. a site reviewer has been sent the review link).
                            const showCommentPanel =
                              agreement.status === 'UNDER_REVIEW' ||
                              agreement.status === 'UNDER_NEGOTIATION'

                            return (
                              <div
                                key={editorKey}
                                className="flex w-full h-full"
                                style={{ minHeight: '700px' }}
                              >
                                {/* OnlyOffice editor takes remaining width */}
                                <div className={showCommentPanel ? 'flex-1 min-w-0' : 'w-full'}>
                                  <OnlyOfficeEditor
                                    ref={editorRef}
                                    key={editorKey}
                                    agreementId={agreement.id}
                                    apiBase={apiBase}
                                    canEdit={isCurrentVersionEditable()}
                                    onSave={canSaveCurrentVersion() ? handleSaveDocument : undefined}
                                    configEndpoint={configEndpoint}
                                  />
                                </div>

                                {/* Review Comment Panel — visible to internal users during review */}
                                {showCommentPanel && (
                                  <div
                                    className="w-80 flex-shrink-0 border-l border-gray-200 overflow-hidden"
                                    style={{ minHeight: '700px' }}
                                  >
                                    <AgreementCommentPanel
                                      agreementId={agreement.id}
                                      apiBase={apiBase}
                                      isInternal={true}
                                      onRefreshOnlyOffice={handleCommentPanelRefreshOnlyOffice}
                                    />
                                  </div>
                                )}
                              </div>
                            )
                          }

                          if (currentDoc.document_content) {
                            return (
                              <div className="w-full h-full flex items-center justify-center p-8">
                                <div className="text-center">
                                  <p className="text-gray-600 mb-2">Legacy document format detected</p>
                                  <p className="text-sm text-gray-500">
                                    This document uses the old JSON format. Please create a new version
                                    from template to use ONLYOFFICE editor.
                                  </p>
                                </div>
                              </div>
                            )
                          }

                          return (
                            <div className="w-full h-full flex items-center justify-center p-8">
                              <div className="text-center">
                                <p className="text-gray-600">No document content available</p>
                              </div>
                            </div>
                          )
                        })()}
                      </div>
                    </div>

                    {/* Document History */}
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 mb-2">Version History</h3>
                      <div className="space-y-2">
                        {agreement.documents.map((doc) => (
                          <div
                            key={doc.id}
                            className="p-3 border border-gray-200 rounded-lg hover:bg-gray-50"
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <p className="font-medium text-gray-900">
                                  Version {doc.version_number}
                                  {doc.is_signed_version === 'true' && (
                                    <span className="ml-2 px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                                      Signed
                                    </span>
                                  )}
                                </p>
                                <p className="text-xs text-gray-600">
                                  Created: {formatDate(doc.created_at)} by {doc.created_by || 'System'}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )
              })()}
              </div>
            )
          })()}

          {/* Activity Timeline — WORKFLOW events only.
               Version creation events are shown in the Version History section.
               Negotiation events (external changes, accept/reject) are shown
               in the External Changes panel above. */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Activity Timeline</h2>

            {timeline.length === 0 ? (
              <p className="text-xs text-gray-500">No workflow activity recorded yet.</p>
            ) : (
              <ol className="space-y-3 text-xs">
                {timeline.map((event) => (
                  <li key={event.id} className="flex items-start gap-2">
                    {/* All events in this timeline are workflow milestones — use a
                        consistent indigo dot so the list looks clean. */}
                    <div className="mt-1 h-2 w-2 rounded-full bg-indigo-500 flex-shrink-0" />
                    <div>
                      <div className="font-medium text-gray-900">{event.label}</div>
                      <div className="text-gray-500">{formatDate(event.timestamp)}</div>
                      {event.description && (
                        <div className="text-gray-400 mt-0.5 text-xs leading-snug line-clamp-2">
                          {event.description}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}

      {/* Complete Review — advances linear workflow to READY_FOR_SIGNATURE (Signature stage). */}
      {showCompleteReviewModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Complete review</h3>
            <p className="text-gray-700 mb-2">
              Move this agreement to <strong>Ready for signature</strong>? External review links will be
              deactivated when you continue.
            </p>
            <p className="text-sm text-gray-500 mb-6">
              This action is logged. Use &quot;Resend review invitation&quot; first if the site still needs
              another review round.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setShowCompleteReviewModal(false)}
                disabled={changingStatus}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 disabled:bg-gray-200"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmCompleteReview}
                disabled={changingStatus}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400"
              >
                {changingStatus ? 'Processing…' : 'Complete review'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send for Review Confirmation Modal */}
      {showReviewConfirmation && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Confirm Send Review Request</h3>
            <p className="text-gray-700 mb-6">
              This agreement is already under review. A valid review link already exists.
              <br /><br />
              Do you want to send another review request?
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setShowReviewConfirmation(false)
                  setShowReviewModal(false)
                  setReviewRecipientEmail('')
                  setReviewMessage('')
                }}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
              >
                Cancel
              </button>
              <button
                onClick={handleSendForReview}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Yes, Send Another
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send for Review Modal */}
      {showReviewModal && !showReviewConfirmation && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Review invitation</h2>
            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded">
                {error}
              </div>
            )}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Recipient Email <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  value={reviewRecipientEmail}
                  onChange={(e) => setReviewRecipientEmail(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                  placeholder="site.contact@example.com"
                  required
                  disabled={sendingForReview}
                />
                <p className="text-xs text-gray-500 mt-1">
                  Email address of the site contact who will review the agreement
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Optional Message
                </label>
                <textarea
                  value={reviewMessage}
                  onChange={(e) => setReviewMessage(e.target.value)}
                  rows={4}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                  placeholder="Add any additional instructions or notes..."
                  disabled={sendingForReview}
                />
                <p className="text-xs text-gray-500 mt-1">
                  This message will be included in the review email
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button
                onClick={() => {
                  setShowReviewModal(false)
                  setReviewRecipientEmail('')
                  setReviewMessage('')
                  setShowReviewConfirmation(false)
                }}
                disabled={sendingForReview}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 disabled:bg-gray-200 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                onClick={handleSendForReview}
                disabled={sendingForReview}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {sendingForReview ? 'Sending…' : 'Send invitation'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showSignatureModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Send for Signature</h3>
            <p className="text-sm text-gray-600 mb-4">
              A secure email link will be sent to the signer. OTP verification is required before the signature is applied.
            </p>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Signer Email
              </label>
              <input
                type="email"
                value={siteSignerEmail}
                onChange={(e) => setSiteSignerEmail(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                placeholder="Auto-filled from Site Profile"
              />
              {siteProfile?.authorized_signatory_email && (
                <p className="text-xs text-gray-500 mt-1">
                  From Site Profile: {siteProfile.authorized_signatory_email}
                </p>
              )}
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button
                onClick={() => {
                  setShowSignatureModal(false)
                  setSiteSignerEmail('')
                }}
                disabled={sendingForSignature}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 disabled:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleSendForSignature}
                disabled={sendingForSignature}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400"
              >
                {sendingForSignature ? 'Sending...' : 'Send Link'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REMOVED: Reset Workflow Confirmation Modal - not part of production workflow */}

      </>}
    </div>
  )
}

export default AgreementTab
