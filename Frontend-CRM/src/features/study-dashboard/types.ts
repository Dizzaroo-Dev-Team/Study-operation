// Shared types for the Study Dashboard feature — mirror Pydantic schemas in
// Backend-CRM/app/modules/study_dashboard/schemas.py.

export type CellStatus = 'done' | 'missed' | 'due' | 'na'

export interface PlannedVisit {
  visitnum: number
  visit: string
}

export interface MatrixCell {
  status: CellStatus
  date?: string | null
}

export interface SubjectRow {
  usubjid: string
  siteid?: number | null
  arm?: string | null
  disposition?: string | null
  cells: MatrixCell[]
}

export interface PatientVisitMatrixSummary {
  total_subjects: number
  total_visits_planned: number
  visits_done: number
  visits_missed: number
  visits_due: number
}

export interface PatientVisitMatrixResponse {
  study_id: string
  visits: PlannedVisit[]
  subjects: SubjectRow[]
  summary: PatientVisitMatrixSummary
}

// ─── Enrollment ─────────────────────────────────────────────────────────────
export interface EnrollmentFunnelBucket {
  label: string
  count: number
  tone?: 'success' | 'danger' | 'warning' | null
}

export interface EnrollmentMonthlyPoint {
  month: string
  monthly: number
  cumulative: number
}

export interface EnrollmentResponse {
  study_id: string
  target: number | null
  enrolled: number
  rate_per_month: number
  projected_lpi: string | null
  funnel: EnrollmentFunnelBucket[]
  monthly: EnrollmentMonthlyPoint[]
}

// ─── Disposition ────────────────────────────────────────────────────────────
export interface DispositionStatusCounts {
  active: number
  completed: number
  screen_failed: number
  discontinued: number
  total_screened: number
}

export interface DispositionBreakdownItem {
  label: string
  count: number
}

export interface DispositionResponse {
  study_id: string
  counts: DispositionStatusCounts
  discontinuation_reasons: DispositionBreakdownItem[]
  screen_failure_reasons: DispositionBreakdownItem[]
  median_tt_screen_fail_days: number | null
  median_time_on_study_days: number | null
  median_tt_withdrawal_days: number | null
  discontinuation_rate_pct: number | null
}

// ─── Visit compliance ───────────────────────────────────────────────────────
export interface VisitComplianceRow {
  visitnum: number
  visit: string
  performed: number
  missed: number
  upcoming: number
}

export interface VisitComplianceResponse {
  study_id: string
  rows: VisitComplianceRow[]
  total_performed: number
  total_expected: number
  compliance_pct: number
}

// ─── Deviations ─────────────────────────────────────────────────────────────
export interface DeviationsWeeklyPoint {
  week_start: string
  count: number
}

export interface DeviationsCategoryRow {
  label: string
  count: number
  major_count: number
}

export interface DeviationsResponse {
  study_id: string
  total: number
  critical: number
  major: number
  minor: number
  pd_rate_per_subject: number
  weekly: DeviationsWeeklyPoint[]
  top_categories: DeviationsCategoryRow[]
}

// ─── Milestones ─────────────────────────────────────────────────────────────
export type MilestoneTone = 'success' | 'warning' | 'danger' | 'secondary'

export interface MilestoneItem {
  key: string
  label: string
  date: string | null
  tone: MilestoneTone
}

export interface MilestonesResponse {
  study_id: string
  milestones: MilestoneItem[]
}

// ─── AI Assistant ───────────────────────────────────────────────────────────
export type ChartType = 'kpi' | 'table' | 'bar' | 'line' | 'pie' | 'stacked_bar'
export type AssistantStatus = 'ok' | 'no_data' | 'rejected' | 'execution_error'

export interface ChartSpec {
  type: ChartType
  title: string
  x_field?: string | null
  y_field?: string | null
  series_field?: string | null
  value_field?: string | null
}

export interface AssistantData {
  columns: string[]
  rows: (string | number | boolean | null)[][]
}

export interface AssistantResponse {
  status: AssistantStatus
  narrative?: string | null
  sql?: string | null
  chart?: ChartSpec | null
  data?: AssistantData | null
  row_count?: number | null
  elapsed_ms?: number | null
  reason?: string | null
}

export interface AssistantHistoryTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface AssistantQueryRequest {
  question: string
  history?: AssistantHistoryTurn[]
}

// ─── Study Registry (Data Platform) ─────────────────────────────────────────
export type StudySource = 'local' | 'registry'

// Uniform study descriptor for the dashboard's study selector. The hardcoded
// study_db_01 study and Data Platform registry studies share this shape.
// `connectionString` is always null in the browser — database credentials
// stay on the backend, which resolves them from `studyId` per request.
export interface DashboardStudy {
  studyId: string
  studyName: string
  databaseName: string | null
  connectionString: string | null
  source: StudySource
}

// Item as returned by the backend /study-dashboard/study-registry proxy.
export interface StudyRegistryItem {
  studyId: string
  studyName: string
  databaseName: string | null
  activeFlag: boolean
}

// Stored in localStorage. `id` is a uuid so cards can be removed individually.
export interface PinnedInsight {
  id: string
  question: string
  pinned_at: string // ISO timestamp
  response: AssistantResponse
}
