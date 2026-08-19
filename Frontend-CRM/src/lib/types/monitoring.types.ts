/**
 * Single source of truth for monitoring domain types (Phase 6).
 * Re-exported by hooks and services — prefer importing from here.
 */
import type { VisitOverviewPayload } from '@/components/mon/types'
import type { ReviewComment } from '@/components/mon/services/monitorService'

export type VisitStatus =
  | 'Scheduled'
  | 'Site Confirmed'
  | 'Visit Confirmed'
  | 'In Progress'
  | 'Post-Visit Action'
  | 'In Review'
  | 'Approved'
  | 'Rejected'
  | 'Completed'
  | 'Closed'
  | 'Cancelled'
  | 'Archived'
  | string

export type FindingStatus =
  | 'Open'
  | 'In Review'
  | 'Resolved'
  | 'Archived'
  | string

export type ReportStatus = 'Draft' | 'In Review' | 'Approved' | 'Rejected'

export interface MonitoringVisit {
  id: number
  siteId?: string
  studyId?: string
  date: string
  dateIso?: string
  site: string
  study: string
  type: string
  status: VisitStatus
  findings: number | null
  visitSeq?: number
}

export interface MonitoringFinding {
  id: string
  visitId?: string
  subjectId?: string
  reference?: string
  category: string
  description: string
  severity: string
  status: FindingStatus
  site: string
  assignee: { initials: string; name: string; color: string }
  dueDate: string
  dueColor: string
  resolution?: string
  actionItems?: Array<{
    id?: string
    assignee: { initials: string; name: string; color: string }
    dueDate: string
    closedDate?: string
    resolution?: string
  }>
  isOverdue?: boolean
}

export type { ReviewComment }

export interface VisitWorkflowState {
  visitReportStatus: ReportStatus | string
  preVisitReportStatus: string
  isFollowUpAcknowledged: boolean
  confirmationLetterConfirmedAt: string | null
}

export type VisitOverview = VisitOverviewPayload

export interface PaginatedDashboardResponse {
  items: import('@/components/mon/services/monitorService').DashboardVisitRow[]
  total: number
  page: number
  page_size: number
  findings: import('@/components/mon/services/monitorService').DashboardFindingRow[]
  overdue_count: number
}
