import type {
  ConfirmationLetterPayload,
  FollowUpLetterPayload,
  PreVisitData,
  VisitReportQueryData,
} from '@/lib/queries/useMonitoring'
import type { VisitOverviewPayload } from '../types'

export const WORKFLOW_POLL_MS = 5_000

/** Stable key for report review state — use in effect deps so rejection/comments sync without hard refresh. */
export function reportWorkflowSyncKey(
  report: VisitReportQueryData | null | undefined,
): string {
  if (!report) return ''
  const pl = report.payload ?? {}
  return [
    report.updated_at ?? '',
    String(pl.reportStatus ?? ''),
    String(pl.rejectionReason ?? ''),
  ].join('|')
}

export function computeWorkflowPollIntervalMs(input: {
  overview: VisitOverviewPayload | null | undefined
  confirmationLetter: ConfirmationLetterPayload | null | undefined
  preVisit: PreVisitData | null | undefined
  followUp: FollowUpLetterPayload | null | undefined
  report: VisitReportQueryData | null | undefined
}): number | false {
  const visitStatus = String(input.overview?.visitDetails?.status ?? '').trim().toLowerCase()
  const siteConfirmed =
    Boolean(input.confirmationLetter?.confirmed_at?.trim()) ||
    visitStatus === 'site confirmed' ||
    visitStatus === 'visit confirmed'

  if (!siteConfirmed) {
    const delivery = String(input.confirmationLetter?.delivery_status ?? '').trim().toLowerCase()
    if (delivery === 'delivered' || delivery === 'sent') {
      return WORKFLOW_POLL_MS
    }
    return false
  }

  const preVisitStatus = String(input.preVisit?.preVisitReportStatus ?? '').trim().toUpperCase()
  const preVisitReviewed = Boolean(String(input.preVisit?.preVisitReviewedAt ?? '').trim())
  if (preVisitStatus === 'SENT' && !preVisitReviewed) {
    return WORKFLOW_POLL_MS
  }

  const reportStatus = String(input.report?.payload?.reportStatus ?? '').trim().toLowerCase()
  if (reportStatus === 'in review' || reportStatus === 'rejected') {
    return WORKFLOW_POLL_MS
  }

  const ackStatus = String(input.followUp?.ack_status ?? '').trim().toLowerCase()
  const followUpHasContent = Boolean(String(input.followUp?.content ?? '').trim())
  if (reportStatus === 'approved' && followUpHasContent && ackStatus !== 'acknowledged') {
    return WORKFLOW_POLL_MS
  }

  return false
}
