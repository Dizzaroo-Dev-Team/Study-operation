/**
 * Monitoring-domain query hooks.
 *
 * Backs the monitoring visit-detail tabs (PreVisit, FollowUpLetter, …) that
 * each used to roll their own `useEffect + api.get` per fetch. Centralising
 * the queries lets sibling tabs share one cache for the same visit.
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ChecklistItem, Finding, VisitOverviewPayload } from '@/components/mon/types'
import type { MvrTemplateDto } from '@/components/mon/types/mvrTemplate'
import type {
  DashboardPayload,
  DashboardVisitRow,
  Notification,
  NotificationsResponse,
  ReviewComment,
  VisitRescheduleRequestItem,
} from '@/components/mon/services/monitorService'
import {
  addVisitFinding,
  closeVisit,
  createVisit,
  decideVisitRescheduleRequest,
  deleteVisitFinding,
  deleteVisit,
  resolveVisitFinding,
  saveConfirmationLetter,
  saveFollowUpLetter,
  saveVisitReport,
  markPreVisitReviewed,
  sendConfirmationLetter,
  sendPreVisitSummary,
  submitReportForReview,
  updateVisit,
  updateVisitFinding,
} from '@/components/mon/services/monitorService'
import type { SiteStatusDetail } from '@/features/sites/types/siteStatus'

/** Shared query keys — use for invalidateQueries across the monitoring module. */
export const monitoringQueryKeys = {
  dashboard: () => ['monitoring', 'dashboard'] as const,
  preVisit: (visitId: string | null | undefined) =>
    ['monitoring', 'pre-visit', visitId] as const,
  visitOverview: (visitId: string | null | undefined) =>
    ['monitoring', 'visit-overview', visitId] as const,
  visitReport: (visitId: string | null | undefined) =>
    ['monitoring', 'visit-report', visitId] as const,
  followUpLetter: (visitId: string | null | undefined) =>
    ['monitoring', 'follow-up-letter', visitId] as const,
  confirmationLetter: (visitId: string | null | undefined) =>
    ['monitoring', 'confirmation-letter', visitId] as const,
  visitFindings: (visitId: string | null | undefined) =>
    ['monitoring', 'visit-findings', visitId] as const,
  notifications: () => ['monitoring', 'notifications'] as const,
  reportComments: (visitId: string | null | undefined) =>
    ['monitoring', 'report-comments', visitId] as const,
  pendingRescheduleRequest: (visitId: string | null | undefined) =>
    ['monitoring', 'pending-reschedule-request', visitId] as const,
}

interface MonitoringQueryOpts {
  staleTime?: number
  refetchOnWindowFocus?: boolean
  refetchInterval?: number | false
  enabled?: boolean
}

export interface PreVisitData {
  checklist?: ChecklistItem[]
  preVisitReportStatus?: string
  preVisitReviewedAt?: string | null
  previousVisit?: {
    id: string
    label: string
    siteVisitNumber?: number | null
    visitDate?: string
    visitDateIso?: string
    visitType?: string
    openFindings?: Finding[]
    openFindingCount?: number
  } | null
}

export interface FollowUpLetterPayload {
  content: string
  updated_at?: string | null
  ack_status?: string | null
  acknowledged_at?: string | null
  last_sent?: string | null
  delivery_status?: string | null
}

export interface ConfirmationLetterPayload {
  content: string
  last_sent?: string | null
  delivery_status?: string | null
  confirmed_at?: string | null
  confirmed_by_role?: string | null
  confirmed_by_name?: string | null
}

export interface VisitReportQueryData {
  payload: Record<string, unknown>
  updated_at?: string | null
  activeTemplate?: MvrTemplateDto | null
  templateSynced?: boolean
}

export interface MonitoringDashboardParams {
  page?: number
  page_size?: number
  site_id?: string | null
  study_id?: string | null
  status?: string | null
}

export function useMonitoringDashboard(
  params: MonitoringDashboardParams = {},
  options?: { enabled?: boolean },
) {
  return useQuery<DashboardPayload>({
    queryKey: [...monitoringQueryKeys.dashboard(), params] as const,
    queryFn: async () => {
      const query: Record<string, string | number> = {
        page: params.page ?? 1,
        page_size: params.page_size ?? 25,
      }
      if (params.site_id) query.site_id = params.site_id
      if (params.study_id) query.study_id = params.study_id
      if (params.status) query.status = params.status
      const res = await api.get<DashboardPayload>('/monitor/dashboard', { params: query })
      const data = res.data
      const items = data.items ?? data.visits ?? []
      return { ...data, items, visits: items }
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
  })
}

export function usePreVisitData(
  visitId: string | null | undefined,
  options?: MonitoringQueryOpts,
) {
  return useQuery<PreVisitData>({
    queryKey: monitoringQueryKeys.preVisit(visitId),
    queryFn: async () => {
      const res = await api.get<PreVisitData>(
        `/monitor/visits/${visitId}/pre-visit`,
      )
      return res.data
    },
    enabled: Boolean(visitId) && (options?.enabled ?? true),
    staleTime: options?.staleTime ?? 60_000,
    refetchOnWindowFocus: options?.refetchOnWindowFocus ?? true,
    refetchInterval: options?.refetchInterval ?? false,
  })
}

export function useVisitOverview(
  visitId: string | null | undefined,
  options?: MonitoringQueryOpts,
) {
  return useQuery<VisitOverviewPayload>({
    queryKey: monitoringQueryKeys.visitOverview(visitId),
    queryFn: async () => {
      const res = await api.get<VisitOverviewPayload>(
        `/monitor/visits/${visitId}/overview`,
      )
      return res.data
    },
    enabled: Boolean(visitId) && (options?.enabled ?? true),
    staleTime: options?.staleTime ?? 60_000,
    refetchOnWindowFocus: options?.refetchOnWindowFocus ?? true,
    refetchInterval: options?.refetchInterval ?? false,
  })
}

export function useVisitReport(
  visitId: string | null | undefined,
  options?: MonitoringQueryOpts,
) {
  return useQuery<VisitReportQueryData>({
    queryKey: monitoringQueryKeys.visitReport(visitId),
    queryFn: async () => {
      const res = await api.get<VisitReportQueryData>(
        `/monitor/visits/${visitId}/visit-report`,
      )
      return res.data
    },
    enabled: Boolean(visitId) && (options?.enabled ?? true),
    staleTime: options?.staleTime ?? 60_000,
    refetchOnWindowFocus: options?.refetchOnWindowFocus ?? true,
    refetchInterval: options?.refetchInterval ?? false,
  })
}

export function useFollowUpLetter(
  visitId: string | null | undefined,
  options?: MonitoringQueryOpts,
) {
  return useQuery<FollowUpLetterPayload>({
    queryKey: monitoringQueryKeys.followUpLetter(visitId),
    queryFn: async () => {
      const res = await api.get<FollowUpLetterPayload>(
        `/monitor/visits/${visitId}/follow-up-letter`,
      )
      return res.data
    },
    enabled: Boolean(visitId) && (options?.enabled ?? true),
    staleTime: options?.staleTime ?? 60_000,
    refetchOnWindowFocus: options?.refetchOnWindowFocus ?? true,
    refetchInterval: options?.refetchInterval ?? false,
  })
}

export function useConfirmationLetter(
  visitId: string | null | undefined,
  options?: MonitoringQueryOpts,
) {
  return useQuery<ConfirmationLetterPayload>({
    queryKey: monitoringQueryKeys.confirmationLetter(visitId),
    queryFn: async () => {
      const res = await api.get<ConfirmationLetterPayload>(
        `/monitor/visits/${visitId}/confirmation-letter`,
      )
      return res.data
    },
    enabled: Boolean(visitId) && (options?.enabled ?? true),
    staleTime: options?.staleTime ?? 60_000,
    refetchOnWindowFocus: options?.refetchOnWindowFocus ?? true,
    refetchInterval: options?.refetchInterval ?? false,
  })
}

export function useVisitFindings(
  visitId: string | null | undefined,
  options?: MonitoringQueryOpts,
) {
  return useQuery<Finding[]>({
    queryKey: monitoringQueryKeys.visitFindings(visitId),
    queryFn: async () => {
      const res = await api.get<Finding[]>(`/monitor/visits/${visitId}/findings`)
      return res.data ?? []
    },
    enabled: Boolean(visitId) && (options?.enabled ?? true),
    staleTime: options?.staleTime ?? 60_000,
    refetchOnWindowFocus: options?.refetchOnWindowFocus ?? true,
  })
}

export function useNotifications(options?: {
  enabled?: boolean
  refetchInterval?: number | false
}) {
  return useQuery<NotificationsResponse>({
    queryKey: monitoringQueryKeys.notifications(),
    queryFn: async () => {
      const res = await api.get<NotificationsResponse>('/monitor/notifications')
      return res.data
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
    refetchInterval: options?.refetchInterval ?? false,
  })
}

export function useReportComments(
  visitId: string | null | undefined,
  enabled: boolean,
) {
  return useQuery<ReviewComment[]>({
    queryKey: monitoringQueryKeys.reportComments(visitId),
    queryFn: async () => {
      const res = await api.get<{ comments: ReviewComment[] }>(
        `/monitor/visits/${visitId}/visit-report/comments`,
      )
      return res.data.comments ?? []
    },
    enabled: Boolean(visitId) && enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  })
}

export function usePendingVisitRescheduleRequest(visitId: string | null | undefined) {
  return useQuery<VisitRescheduleRequestItem | null>({
    queryKey: monitoringQueryKeys.pendingRescheduleRequest(visitId),
    queryFn: async () => {
      const res = await api.get<{ request: VisitRescheduleRequestItem | null }>(
        `/monitor/visits/${visitId}/reschedule-requests/pending`,
      )
      return res.data.request ?? null
    },
    enabled: Boolean(visitId),
    staleTime: 30_000,
  })
}

// -----------------------------------------------------------------------------
// Workflow cache helpers
// -----------------------------------------------------------------------------

export function patchDashboardVisitStatus(
  queryClient: QueryClient,
  visitId: string,
  status: string,
): void {
  queryClient.setQueriesData<DashboardPayload>(
    { queryKey: monitoringQueryKeys.dashboard() },
    (old) => {
      if (!old) return old
      const patchRows = (rows: DashboardVisitRow[] | undefined) =>
        (rows ?? []).map((v) =>
          String(v.id) === String(visitId) ? { ...v, status } : v,
        )
      const items = patchRows(old.items ?? old.visits)
      return { ...old, items, visits: items }
    },
  )
}

export async function refetchVisitWorkflowQueries(
  queryClient: QueryClient,
  visitId: string,
): Promise<void> {
  await Promise.all([
    queryClient.refetchQueries({ queryKey: monitoringQueryKeys.visitOverview(visitId) }),
    queryClient.refetchQueries({ queryKey: monitoringQueryKeys.confirmationLetter(visitId) }),
    queryClient.refetchQueries({ queryKey: monitoringQueryKeys.preVisit(visitId) }),
    queryClient.refetchQueries({ queryKey: monitoringQueryKeys.visitReport(visitId) }),
    queryClient.refetchQueries({ queryKey: monitoringQueryKeys.followUpLetter(visitId) }),
    queryClient.refetchQueries({ queryKey: monitoringQueryKeys.reportComments(visitId) }),
  ])
}

// -----------------------------------------------------------------------------
// Monitoring mutations — invalidate related query keys on success
// -----------------------------------------------------------------------------

export function useSaveVisitReport(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => saveVisitReport(visitId, payload),
    onSuccess: async () => {
      await refetchVisitWorkflowQueries(queryClient, visitId)
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
    },
  })
}

export function useSubmitReportForReview(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (args: { reviewerEmail: string; message: string; authorEmail: string }) =>
      submitReportForReview(visitId, args.reviewerEmail, args.message, args.authorEmail),
    onSuccess: async () => {
      await refetchVisitWorkflowQueries(queryClient, visitId)
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.reportComments(visitId) })
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
    },
  })
}

export function useSaveConfirmationLetter(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content: string) => saveConfirmationLetter(visitId, content),
    onSuccess: async () => {
      await refetchVisitWorkflowQueries(queryClient, visitId)
    },
  })
}

export function useSendConfirmationLetter(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (args: { content: string; ccEmails?: string }) =>
      sendConfirmationLetter(visitId, args.content, args.ccEmails),
    onSuccess: async () => {
      await refetchVisitWorkflowQueries(queryClient, visitId)
    },
  })
}

export function useSaveFollowUpLetter(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content: string) => saveFollowUpLetter(visitId, content),
    onSuccess: async () => {
      await refetchVisitWorkflowQueries(queryClient, visitId)
    },
  })
}

export function useSendPreVisitSummary(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (args: { content: string; ccEmails?: string }) =>
      sendPreVisitSummary(visitId, args.content, args.ccEmails),
    onSuccess: async () => {
      await refetchVisitWorkflowQueries(queryClient, visitId)
    },
  })
}

export function useMarkPreVisitReviewed(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => markPreVisitReviewed(visitId),
    onSuccess: async (data) => {
      const reviewedAt = data.preVisitReviewedAt ?? new Date().toISOString()
      queryClient.setQueryData<PreVisitData>(
        monitoringQueryKeys.preVisit(visitId),
        (old) => ({ ...(old ?? {}), preVisitReviewedAt: reviewedAt }),
      )
      await refetchVisitWorkflowQueries(queryClient, visitId)
    },
  })
}

export function useCloseVisit(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => closeVisit(visitId),
    onSuccess: async () => {
      patchDashboardVisitStatus(queryClient, visitId, 'Closed')
      await refetchVisitWorkflowQueries(queryClient, visitId)
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
      await queryClient.refetchQueries({ queryKey: monitoringQueryKeys.dashboard() })
    },
  })
}

export function useAddVisitFinding(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => addVisitFinding(visitId, payload),
    onSuccess: (createdFinding) => {
      queryClient.setQueryData<Finding[]>(
        monitoringQueryKeys.visitFindings(visitId),
        (old) => {
          if (!old) return createdFinding ? [createdFinding] : old
          if (!createdFinding?.id || old.some((finding) => finding.id === createdFinding.id)) return old
          return [...old, createdFinding]
        },
      )
      void queryClient.invalidateQueries({
        queryKey: monitoringQueryKeys.visitFindings(visitId),
        refetchType: 'inactive',
      })
      void queryClient.invalidateQueries({ queryKey: ['monitoring', 'pre-visit'] })
      void queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
      // Finding action items spawn global Tasks rows in the background.
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}

export function useUpdateVisitFinding(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (args: { findingId: string; payload: Record<string, unknown> }) =>
      updateVisitFinding(visitId, args.findingId, args.payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.visitFindings(visitId) })
      await queryClient.invalidateQueries({ queryKey: ['monitoring', 'pre-visit'] })
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
    },
  })
}

export function useResolveVisitFinding(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (findingId: string) => resolveVisitFinding(visitId, findingId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.visitFindings(visitId) })
      await queryClient.invalidateQueries({ queryKey: ['monitoring', 'pre-visit'] })
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
    },
  })
}

export function useDeleteVisitFinding(visitId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (findingId: string) => deleteVisitFinding(visitId, findingId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.visitFindings(visitId) })
      await queryClient.invalidateQueries({ queryKey: ['monitoring', 'pre-visit'] })
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
    },
  })
}

export function useCreateVisit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => createVisit(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['monitoring', 'pre-visit'] })
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
    },
  })
}

export function useUpdateVisit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (args: { visitId: string; payload: Record<string, unknown> }) =>
      updateVisit(args.visitId, args.payload),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
      await queryClient.invalidateQueries({
        queryKey: monitoringQueryKeys.visitOverview(variables.visitId),
      })
    },
  })
}

export function useDeleteVisit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (visitId: string) => deleteVisit(visitId),
    onSuccess: async (_data, visitId) => {
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
      await queryClient.removeQueries({ queryKey: monitoringQueryKeys.visitOverview(visitId) })
      await queryClient.removeQueries({ queryKey: monitoringQueryKeys.preVisit(visitId) })
      await queryClient.removeQueries({ queryKey: monitoringQueryKeys.visitReport(visitId) })
      await queryClient.removeQueries({ queryKey: monitoringQueryKeys.followUpLetter(visitId) })
      await queryClient.removeQueries({ queryKey: monitoringQueryKeys.confirmationLetter(visitId) })
      await queryClient.removeQueries({ queryKey: monitoringQueryKeys.visitFindings(visitId) })
    },
  })
}

export function useDecideVisitRescheduleRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (args: {
      visitId: string
      requestId: string
      decision: 'approved' | 'rejected'
      reason?: string
      selectedSlotIndex?: number
    }) =>
      decideVisitRescheduleRequest(args.visitId, args.requestId, args.decision, args.reason, args.selectedSlotIndex),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() })
      await refetchVisitWorkflowQueries(queryClient, variables.visitId)
      await queryClient.invalidateQueries({
        queryKey: monitoringQueryKeys.pendingRescheduleRequest(variables.visitId),
      })
    },
  })
}

export type { Notification, ReviewComment, VisitRescheduleRequestItem, DashboardVisitRow }

// -----------------------------------------------------------------------------
// Token-gated CRA visit-report review page
// -----------------------------------------------------------------------------
// Backs VisitReportReviewPage. The review is a single-session token flow so
// refetch-on-focus and retries stay off.
export function useVisitReportReview(visitId: string | null, token: string) {
  return useQuery<any>({
    queryKey: ['visit-report-review', visitId, token],
    queryFn: async () => {
      const res = await api.get(
        `/monitor/visits/${visitId}/visit-report/review`,
        { params: { token } },
      )
      return res.data
    },
    enabled: Boolean(visitId && token),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 0,
  })
}

export function usePostVisitReportComment(visitId: string | null) {
  return useMutation<{ status: string; id: string }, unknown, Record<string, unknown>>({
    mutationFn: async (body) => {
      const res = await api.post(
        `/monitor/visits/${visitId}/visit-report/review/comments`,
        body,
      )
      return res.data
    },
  })
}

export function usePatchVisitReportComment(visitId: string | null) {
  return useMutation<{ status: string }, unknown, { commentId: string; token: string; comment_text: string }>({
    mutationFn: async ({ commentId, token, comment_text }) => {
      const res = await api.patch(
        `/monitor/visits/${visitId}/visit-report/review/comments/${commentId}`,
        { token, comment_text },
      )
      return res.data
    },
  })
}

export function useSaveAuthorCommentReply(visitId: string | null) {
  const queryClient = useQueryClient()
  return useMutation<
    { status: string; comment: ReviewComment },
    unknown,
    { commentId: string; author_reply: string }
  >({
    mutationFn: async ({ commentId, author_reply }) => {
      const res = await api.patch(
        `/monitor/visits/${visitId}/visit-report/comments/${commentId}/reply`,
        { author_reply },
      )
      return res.data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: monitoringQueryKeys.reportComments(visitId),
      })
    },
  })
}

export function useDeleteVisitReportComment(visitId: string | null) {
  return useMutation<{ status: string }, unknown, { commentId: string; token: string }>({
    mutationFn: async ({ commentId, token }) => {
      const res = await api.delete(
        `/monitor/visits/${visitId}/visit-report/review/comments/${commentId}`,
        { params: { token } },
      )
      return res.data
    },
  })
}

export function useApproveVisitReport(visitId: string | null) {
  return useMutation<{ status: string }, unknown, { token: string }>({
    mutationFn: async ({ token }) => {
      const res = await api.post(
        `/monitor/visits/${visitId}/visit-report/review/approve`,
        { token },
      )
      return res.data
    },
  })
}

export function useRejectVisitReport(visitId: string | null) {
  return useMutation<{ status: string }, unknown, { token: string; reason: string }>({
    mutationFn: async ({ token, reason }) => {
      const res = await api.post(
        `/monitor/visits/${visitId}/visit-report/review/reject`,
        { token, reason },
      )
      return res.data
    },
  })
}

// -----------------------------------------------------------------------------
// Token-gated visit reschedule page (public)
// -----------------------------------------------------------------------------
export interface RescheduleVisitPayload {
  visit: {
    id: string
    site_visit_number?: number | null
    visit_date: string
    visit_date_iso: string
    visit_end_date?: string
    visit_end_date_iso?: string
    location: string
    visit_type: string
    status: string
  }
  actor_role: string
  actor_label: string
}

export function useVisitReschedule(
  visitId: string | null,
  token: string | null,
) {
  return useQuery<RescheduleVisitPayload>({
    queryKey: ['visit-reschedule', visitId, token],
    queryFn: async () => {
      const res = await api.get<RescheduleVisitPayload>(
        `/monitor/visits/${encodeURIComponent(visitId as string)}/reschedule`,
        { params: { token } },
      )
      return res.data
    },
    enabled: Boolean(visitId && token),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 0,
  })
}

// -----------------------------------------------------------------------------
// Monitoring visits + issues (cross-site / cross-study lists)
// -----------------------------------------------------------------------------
// Loose typing — the consumer (SiteControlTower) already defines tighter
// MonitoringVisit / MonitoringIssue types in @/types.
export function useMonitoringVisits(options?: { enabled?: boolean }) {
  return useQuery<unknown[]>({
    queryKey: ['monitoring', 'visits'],
    queryFn: async () => {
      const res = await api.get<unknown[]>('/monitoring/visits')
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
    retry: 0,
  })
}

export function useMonitoringIssues(
  filters: { study_id?: string | null; site_id?: string | null } = {},
  options?: { enabled?: boolean },
) {
  return useQuery<unknown[]>({
    queryKey: ['monitoring', 'issues', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = {}
      if (filters.study_id) params.study_id = filters.study_id
      if (filters.site_id) params.site_id = filters.site_id
      const res = await api.get<unknown[]>(
        '/monitoring/issues',
        Object.keys(params).length ? { params } : undefined,
      )
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
    retry: 0,
  })
}

export function useSubmitVisitReschedule(visitId: string | null) {
  return useMutation({
    mutationFn: async (payload: {
      token: string
      proposed_datetime_iso: string
      proposed_end_datetime_iso?: string
      proposed_slots?: Array<{
        proposed_datetime_iso: string
        proposed_end_datetime_iso?: string
      }>
      reason: string
    }) => {
      const res = await api.post<{
        status: string
        request_id?: string
        cra_notified?: boolean
      }>(
        `/monitor/visits/${encodeURIComponent(visitId as string)}/reschedule`,
        payload,
      )
      return res.data
    },
  })
}

/**
 * Site Status detail for a CRM site id. Used by the Pre-Visit Status Board
 * to render the primary status card from the live Site Status API rather
 * than the static demo tile.
 */
export function useSiteStatusDetail(
  siteKey: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<SiteStatusDetail>({
    queryKey: ['site-status', 'detail', siteKey],
    queryFn: async () => {
      const res = await api.get<SiteStatusDetail>(
        `/site-status/sites/${encodeURIComponent(siteKey as string)}`,
      )
      return res.data
    },
    enabled: Boolean(siteKey) && (options?.enabled ?? true),
    staleTime: 60_000,
    retry: 0,
  })
}

export type {
  MonitoringVisit,
  MonitoringFinding,
  PaginatedDashboardResponse,
  VisitWorkflowState,
  VisitStatus,
  FindingStatus,
  ReportStatus,
} from '@/lib/types/monitoring.types'
