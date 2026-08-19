/**
 * Agreement-domain query hooks.
 *
 * Scope of this module today
 * --------------------------
 * Phase 1 of the AgreementTab → TanStack Query migration. Covers the three
 * read paths that are NOT entangled with the document-editing lifecycle:
 *
 *   * `useAgreementTemplates(studyId)`
 *   * `useAgreementChanges(agreementId)`
 *   * `useAgreementReviewTokens(agreementId)`
 *
 * The hottest read — the "active agreement for this study+site" lookup —
 * stays as a manual fetch in AgreementTab for now because it is coupled to
 * OnlyOffice editor lifecycle, ref-based polling diffs, and the edit-lock
 * check. Migrating it requires re-thinking the polling loop and the
 * `agreementRef` mechanism, which is its own focused task.
 *
 * Mutation invalidation pattern
 * -----------------------------
 * Each consuming component holds the queryClient (via useQueryClient) and
 * invalidates the right query key on a successful mutation:
 *
 *     queryClient.invalidateQueries({ queryKey: QK.agreement(id) })
 *
 * Centralizing the keys in `@/lib/queryClient::QK` keeps invalidations
 * grep-able and consistent across files.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryClient'
// The CTA-specific service was retired (2026-06-18) with the legacy type module.
// Only the reviewer/sponsor-head assignment inbox survived — its lightweight
// shape lives here now (see `useMyAssignments` below).
export type AssignmentRole = 'reviewer' | 'sponsor_head'

export interface MyAssignmentItem {
  agreement_id: string
  study_id: string | null
  site_id: string | null
  study_name: string
  site_name: string
  role: AssignmentRole
  status: string
  assigned_at: string | null
}

// -----------------------------------------------------------------------------
// Agreement comments (review panel)
// -----------------------------------------------------------------------------
// Loose typing — the consumer (AgreementCommentPanel) defines the tight
// Comment / CommentReply shapes locally.
export type AgreementComment = any

export interface AgreementCommentsResponse {
  comments: AgreementComment[]
  total: number
}

export function useAgreementComments(
  agreementId: string | null | undefined,
  options?: { reviewDocumentId?: string | null; enabled?: boolean },
) {
  const reviewDocumentId = options?.reviewDocumentId ?? null
  return useQuery<AgreementCommentsResponse>({
    queryKey: ['agreement-comments', agreementId, reviewDocumentId],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (reviewDocumentId) params.review_document_id = reviewDocumentId
      const res = await api.get<AgreementCommentsResponse>(
        `/agreements/${agreementId}/comments`,
        { params: Object.keys(params).length ? params : undefined },
      )
      return res.data
    },
    enabled: Boolean(agreementId) && (options?.enabled ?? true),
    staleTime: 15_000,
  })
}

export function useAgreementCommentReply(agreementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { commentId: string; replyText: string }) => {
      const res = await api.post(
        `/agreements/${agreementId}/comments/${payload.commentId}/reply`,
        { reply_text: payload.replyText },
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-comments', agreementId] })
    },
  })
}

export function useAgreementCommentStatus(agreementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { commentId: string; status: string }) => {
      const res = await api.put(
        `/agreements/${agreementId}/comments/${payload.commentId}/status`,
        { status: payload.status },
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-comments', agreementId] })
    },
  })
}

// -----------------------------------------------------------------------------
// Study template library mutations + helpers
// -----------------------------------------------------------------------------
// Backs StudyTemplateLibrary. The list itself comes from useAgreementTemplates
// (`activeOnly: false` for the library view); these mutations invalidate that
// key so the table refreshes after each action.
export function useUploadTemplate(studyId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: {
      templateName: string
      templateType: string
      templateFile: File
      siteId?: string | null
    }) => {
      const formData = new FormData()
      formData.append('template_name', payload.templateName)
      formData.append('template_type', payload.templateType)
      formData.append('template_file', payload.templateFile)
      if (payload.siteId) formData.append('site_id', payload.siteId)
      const res = await api.post(`/studies/${studyId}/templates`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-templates', studyId] })
    },
  })
}

export function useCreateClauseTemplate(studyId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { templateName: string; templateType: string }) => {
      const res = await api.post(`/studies/${studyId}/templates/clause-template`, {
        template_name: payload.templateName,
        template_type: payload.templateType,
      })
      return res.data as { id: string; template_name: string; composition_mode: string }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-templates', studyId] })
    },
  })
}

export function useDeactivateTemplate(studyId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (templateId: string) => {
      const res = await api.patch(`/templates/${templateId}/deactivate`)
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-templates', studyId] })
    },
  })
}

export function useSavePlaceholderConfig(studyId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: {
      templateId: string
      placeholderConfig: Record<string, { editable: boolean }>
    }) => {
      const res = await api.put(
        `/templates/${payload.templateId}/placeholder-config`,
        { placeholder_config: payload.placeholderConfig },
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-templates', studyId] })
    },
  })
}

export function useSaveFieldMappings(studyId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: {
      templateId: string
      fieldMappings: Record<string, string>
    }) => {
      const res = await api.put(
        `/templates/${payload.templateId}/field-mappings`,
        { field_mappings: payload.fieldMappings },
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-templates', studyId] })
    },
  })
}

export interface TemplateFieldOption {
  field: string
  label: string
}

export interface TemplateFieldMappingOptions {
  site_profile: TemplateFieldOption[]
  agreement: TemplateFieldOption[]
}

export function useTemplateFieldMappingOptions(options?: { enabled?: boolean }) {
  return useQuery<TemplateFieldMappingOptions>({
    queryKey: ['template-field-mapping-options'],
    queryFn: async () => {
      const res = await api.get<TemplateFieldMappingOptions>(
        '/templates/field-mapping-options',
      )
      return res.data ?? { site_profile: [], agreement: [] }
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60_000,
    retry: 0,
  })
}

export interface TemplateAiSuggestion {
  placeholder: string
  suggested_source: string  // e.g. 'site_profile.pi_email'
  confidence: number        // 0-1
  reasoning: string
}

export function useTemplateAiSuggestions(
  templateId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<{ suggestions: TemplateAiSuggestion[] }>({
    queryKey: ['template-ai-suggestions', templateId],
    queryFn: async () => {
      const res = await api.get(`/templates/${templateId}/ai-suggestions`)
      return res.data
    },
    enabled: Boolean(templateId) && (options?.enabled ?? false),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

// -----------------------------------------------------------------------------
// Authenticated agreement document download
// -----------------------------------------------------------------------------
// Used by the review page's "Download" button — fetches the DOCX blob for a
// specific agreement version. Returns the raw Blob so the caller can wire it
// up to a download anchor.
export function useDownloadAgreementDocument() {
  return useMutation<Blob, unknown, { agreementId: string; version: number | string }>({
    mutationFn: async ({ agreementId, version }) => {
      const res = await api.get(`/agreements/${agreementId}/document-file`, {
        params: { version },
        responseType: 'blob',
      })
      return res.data as Blob
    },
  })
}

export function useReExtractAgreementComments(agreementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await api.post(
        `/agreements/${agreementId}/re-extract-comments`,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agreement-comments', agreementId] })
    },
  })
}

// -----------------------------------------------------------------------------
// Active agreement for a (site, study)
// -----------------------------------------------------------------------------
// Replaces the AgreementTab `loadAgreement` + `refreshAgreementOnce` +
// hand-rolled 30s setInterval polling block from Hunt 1. The query polls at
// 30s with refetchIntervalInBackground=false (Vite/RT-Query equivalent of
// the visibilityState-gated poller), and refetchOnWindowFocus=true gives
// the "catch up on tab return" behavior for free.
//
// Loose typing for the same reason as Template / AgreementChange — the
// consumer (AgreementTab) has its own Agreement interface; lifting a
// canonical Agreement type into @/types is a follow-up task.
export type Agreement = any

export type AgreementWorkflowType = 'CDA' | 'CTA' | 'BUDGET'

function agreementMatchesType(
  agreement: Agreement,
  agreementType: AgreementWorkflowType,
  templates?: Template[],
): boolean {
  const raw = agreement?.agreement_type
  if (raw) {
    return String(raw).toUpperCase() === agreementType
  }
  const templateId = agreement?.documents?.[0]?.created_from_template_id
  if (!templateId || !templates?.length) return false
  const template = templates.find((t) => String(t.id) === String(templateId))
  return template
    ? String(template.template_type || '').toUpperCase() === agreementType
    : false
}

export function useAgreementForSite(
  siteId: string | null | undefined,
  studyId: string | null | undefined,
  options?: {
    enabled?: boolean
    refetchInterval?: number | false
    agreementType?: AgreementWorkflowType
    templates?: Template[]
  },
) {
  const agreementType = options?.agreementType ?? 'CDA'
  return useQuery<Agreement | null>({
    queryKey: ['agreement-for-site', siteId, studyId, agreementType],
    queryFn: async () => {
      if (!siteId || !studyId) return null
      const res = await api.get<Agreement[]>(
        `/sites/${siteId}/agreements?study_id=${studyId}`,
      )
      const list = res.data ?? []
      const match = list.find((a) =>
        agreementMatchesType(a, agreementType, options?.templates),
      )
      return match ?? null
    },
    enabled: Boolean(siteId && studyId) && (options?.enabled ?? true),
    // 30s polling, paused when the tab is hidden so we don't hammer the
    // backend for a closed-laptop user. Override via `refetchInterval` if a
    // caller wants to disable polling (e.g. a read-only viewer).
    refetchInterval: options?.refetchInterval ?? 30_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    // TanStack Query v5 default `structuralSharing: true` keeps the
    // returned object reference stable when the response is deeply equal,
    // so unchanged polls won't trigger downstream re-renders. That replaces
    // the manual `agreementRef.current` diffing in the legacy code.
    staleTime: 5_000,
  })
}

// -----------------------------------------------------------------------------
// Templates list for a study
// -----------------------------------------------------------------------------
// The legacy `loadTemplates` had a fallback: when selectedStudyId was missing,
// it derived the study from selectedSiteId via an extra `/sites/{id}` call.
// That edge case is rare in practice (the StudySiteContext almost always
// populates selectedStudyId before any agreement view renders). We do NOT
// reimplement that fallback here — callers that hit it can resolve the study
// id themselves before passing it in, keeping this hook's queryFn pure.
//
// Active-only filter is on by default to match the legacy behavior.
// Typed as `any` to match the legacy `availableTemplates: any[]` shape — the
// JSX consumer reads fields beyond what a tight interface would cover, and
// the existing Template type isn't formally defined elsewhere. A follow-up
// task should add a real Template type and tighten this.
export type Template = any

export function useAgreementTemplates(
  studyId: string | null | undefined,
  options?: { activeOnly?: boolean; enabled?: boolean },
) {
  const activeOnly = options?.activeOnly ?? true
  return useQuery<Template[]>({
    queryKey: ['agreement-templates', studyId, activeOnly],
    queryFn: async () => {
      if (!studyId) return []
      const url = `/studies/${studyId}/templates${activeOnly ? '?active_only=true' : ''}`
      const res = await api.get<Template[]>(url)
      return res.data ?? []
    },
    enabled: Boolean(studyId) && (options?.enabled ?? true),
    // Templates change on admin actions only — cache them for 5 minutes.
    staleTime: 5 * 60_000,
  })
}

// -----------------------------------------------------------------------------
// Changes (track-changes log) for an agreement
// -----------------------------------------------------------------------------
// Same `any` strategy as Template — the consumer (AgreementTab) defines a
// local AgreementChange interface with more fields, and tightening the hook
// shape to match would require importing/re-declaring it here. Loose typing
// keeps the hook decoupled. Follow-up: lift a canonical type into
// `@/types/agreement.ts`.
export type AgreementChange = any

export function useAgreementChanges(
  agreementId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<{ all: AgreementChange[]; pending: AgreementChange[] }>({
    queryKey: QK.agreement(agreementId ?? '').concat(['changes']) as readonly unknown[] as any,
    queryFn: async () => {
      if (!agreementId) return { all: [], pending: [] }
      const res = await api.get<{ changes: AgreementChange[] }>(
        `/agreements/${agreementId}/changes`,
      )
      const all = res.data?.changes ?? []
      // Pending = external changes that haven't been accepted (matches the
      // legacy AgreementTab filter).
      const pending = all.filter((c) => c.is_external_change && !c.is_accepted)
      return { all, pending }
    },
    enabled: Boolean(agreementId) && (options?.enabled ?? true),
    staleTime: 30_000,
  })
}

// -----------------------------------------------------------------------------
// Review tokens for an agreement
// -----------------------------------------------------------------------------
export type ReviewToken = any

export function useAgreementReviewTokens(
  agreementId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<ReviewToken[]>({
    queryKey: QK.agreement(agreementId ?? '').concat(['review-tokens']) as readonly unknown[] as any,
    queryFn: async () => {
      if (!agreementId) return []
      const res = await api.get<{ tokens: ReviewToken[] }>(
        `/agreements/${agreementId}/review-tokens`,
      )
      return res.data?.tokens ?? []
    },
    enabled: Boolean(agreementId) && (options?.enabled ?? true),
    // Review tokens get created/revoked by user action; let the user-driven
    // refetches (mutation invalidation) drive freshness after mutations.
    staleTime: 60_000,
  })
}

// =============================================================================
// CTA reviewer / sponsor-head assignment inbox
// =============================================================================
// The CTA *workflow* moved to the general workflow engine (2026-06-18); the only
// CTA-specific hook that survived is the assignment inbox below, which backs the
// Navbar bell + WorkspaceHome "My CTA Reviews & Signatures" card. It reads the
// preserved /agreements/cta/my-assignments endpoint (cta_assignments table).

/**
 * Agreements where the logged-in user is the assigned internal reviewer or
 * sponsor head. Used by the WorkspaceHome inbox widget and Navbar bell.
 */
export function useMyAssignments(options?: { enabled?: boolean }) {
  return useQuery<MyAssignmentItem[]>({
    queryKey: QK.myAssignments(),
    queryFn: async () => {
      const res = await api.get<MyAssignmentItem[]>('/agreements/cta/my-assignments')
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  })
}

