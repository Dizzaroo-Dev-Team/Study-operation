export type SiteOperationalStatus =
  | 'not-started'
  | 'active'
  | 'on-hold'
  | 'closed'

// Primary backend-driven clinical site status
export type PrimarySiteStatus =
  | 'UNDER_EVALUATION'
  | 'STARTUP'
  | 'INITIATING'
  | 'INITIATED_NOT_RECRUITING'
  | 'RECRUITING'
  | 'ACTIVE_NOT_RECRUITING'
  | 'COMPLETED'
  | 'SUSPENDED'
  | 'TERMINATED'
  | 'WITHDRAWN'
  | 'CLOSED'

// Dashboard study-level summary
export interface StudyStatusSummary {
  study_id: string
  study_name: string
  study_status?: PrimarySiteStatus | null
  total_sites: number
  recruiting_sites: number
  status_counts: Record<PrimarySiteStatus, number>
  countries: CountryStatusSummary[]
}

export interface CountryStatusSummary {
  country: string
  status?: PrimarySiteStatus | null
  total_sites: number
  recruiting_sites: number
  status_counts: Record<PrimarySiteStatus, number>
}

export interface SiteStatusHistoryEntry {
  status: PrimarySiteStatus
  previous_status?: PrimarySiteStatus | null
  metadata?: Record<string, any>
  changed_at: string
  triggering_event?: string | null
  reason?: string | null
}

export interface SiteStatusDetail {
  site_id: string
  site_external_id?: string | null
  study_id?: string | null
  name: string
  country?: string | null
  current_status?: PrimarySiteStatus | null
  previous_status?: PrimarySiteStatus | null
  secondary_statuses?: Record<string, any> | null
  history: SiteStatusHistoryEntry[]
}

// Frontend-computed operational / logistics status (existing)
export interface SiteStatus {
  siteId: string
  siteName: string
  location?: string // city/country or whatever is available

  // Overall operational status
  operationalStatus: SiteOperationalStatus
  lastUpdatedAt?: string | Date

  // Monitoring
  lastMonitoringVisitDate?: string | Date
  nextMonitoringVisitDate?: string | Date
  openMonitoringIssuesCount: number
  openMonitoringTasksCount: number // tasks tied to monitoring for this site

  // Logistics
  totalPatients?: number
  activePatients?: number
  drugRemaining?: number
  isDrugLow?: boolean
  amountPaid?: number
  amountDue?: number

  // Optional consolidated risk flag
  riskLevel?: 'low' | 'medium' | 'high'
}

// ---------------------------------------------------------------------------
// Control Tower Types (UI-Level Status Mapping)
// ---------------------------------------------------------------------------

/**
 * Control Tower stages - UI-level workflow stages mapped from raw statuses
 */
export type ControlStage =
  | 'under_consideration'
  | 'startup_site_selection'
  | 'enrollment_initiation'
  | 'initiated_post_siv'
  | 'open_for_recruitment'
  | 'active_not_recruiting'
  | 'on_hold'
  | 'closed_final'

/**
 * Stage progress information
 */
export interface StageProgress {
  currentStage: ControlStage
  completedStages: ControlStage[]
  isOnHold: boolean
  stageOrder: number
}

/**
 * Milestone definition and state
 */
export interface Milestone {
  id: string
  label: string
  completionRule: (metadata: Record<string, any> | null, workflowSteps?: any[] | null) => boolean
  blocking?: boolean
  description?: string
}

/**
 * Activity definition for a stage
 */
export interface Activity {
  id: string
  label: string
  type: 'button' | 'form' | 'link'
  action?: () => void | Promise<void>
  enabledRule: (stage: ControlStage, metadata?: Record<string, any> | null) => boolean
  tooltip?: string
  icon?: string
}

/**
 * Readiness rule for a stage
 */
export interface ReadinessRule {
  stage: ControlStage
  requiredMilestones?: string[] // Milestone IDs that must be completed
  blockingMilestones?: string[] // Milestone IDs that block progression
}

/**
 * Control Tower stage configuration
 */
export interface ControlTowerStage {
  id: ControlStage
  label: string
  order: number
  milestones: Milestone[]
  activities: Activity[]
  readinessRules: ReadinessRule[]
  description?: string
  definition?: string // READ-ONLY definition text shown near stage header
}

