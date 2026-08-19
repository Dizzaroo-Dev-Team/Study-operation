export interface CRA {
  initials: string;
  name: string;
  color: string;
  role?: string;
  email?: string;
  sites?: number;
  visits?: number;
  open?: number;
}

export interface Visit {
  id: number | string;
  siteId?: string;
  studyId?: string;
  date: string;
  /** ISO date prefix from API (YYYY-MM-DD) for edit forms */
  dateIso?: string;
  endDate?: string;
  endDateIso?: string;
  duration?: string;
  estimatedDurationDays?: number | null;
  site: string;
  study: string;
  cra: CRA;
  type: string;
  priority?: string;
  status: string;
  findings: number | null;
  findingsColor?: string;
  /** 1-based per site for display labels; URLs still use opaque `id`. */
  visitSeq?: number;
}

export type TaskMode = "remote" | "on-site";

export interface FindingActionItem {
  id?: string;
  assignee: CRA;
  dueDate: string;
  closedDate?: string;
  resolution?: string;
  taskMode?: TaskMode;
  taskId?: string;
}

export interface Finding {
  id: string;
  /** Parent visit when loaded from dashboard/API */
  visitId?: string;
  /** Subject / participant identifier when applicable */
  subjectId?: string;
  /** Protocol section / ICF ref / etc. */
  reference?: string;
  category: string;
  description: string;
  severity: string;
  status: string;
  site: string;
  /** Primary assignee — mirrors the first action item for backward compatibility */
  assignee: CRA;
  dueDate: string;
  dueColor: string;
  resolution?: string;
  /** Multiple corrective actions per finding */
  actionItems?: FindingActionItem[];
  /** Server-computed flag: true when due_date is in the past and finding is not resolved */
  isOverdue?: boolean;
}

export interface ChecklistItem {
  id: number;
  text: string;
  done: boolean;
  tagType: string;
}

export interface VisitOverviewActivity {
  initials: string;
  color: string;
  text: string;
  time: string;
}

export interface VisitOverviewPayload {
  visitDetails: {
    /** Current workflow status from monitoring_visits (e.g. after site confirms via email link). */
    status?: string;
    visitType: string;
    visitDate: string;
    visitDateIso?: string;
    /** Saved visit end date display string (e.g. "May 12, 2026 · 5:00 PM") */
    endDate?: string;
    /** Saved visit end date ISO UTC (e.g. "2026-05-12T17:00:00Z") */
    endDateIso?: string;
    duration: string;
    estimatedDurationDays?: number | null;
    protocol: string;
    indNumber: string;
    sponsor: string;
    riskLevel: string;
    priority?: string;
    /** Assigned CRA from monitoring_visits */
    craName?: string;
    /** External / clinical site identifier for letters and tables */
    siteId?: string;
    siteVisitNumber?: number | null;
    craEmail?: string;
  };
  siteContact: {
    institutionName?: string;
    principalInvestigator: string;
    piEmail: string;
    piDesignation?: string;
    piDepartment?: string;
    addressLine1?: string;
    addressCityRegionPostal?: string;
    addressCountry?: string;
    studyCoordinator: string;
    coordinatorEmail?: string;
    coordinatorPhone: string;
    siteAddress: string;
    irbApproval: string;
  };
  sdvProgress: {
    verifiedSubjects: number;
    totalSubjects: number;
    percent: number;
    subjectsEnrolled: string;
    crfCompletion: string;
    queryRate: string;
    lastSdvDate: string;
  };
  lastModified?: string | null;
  closedAt?: string | null;
  actionRequiredCount: number;
  objectives: ChecklistItem[];
  recentActivity: VisitOverviewActivity[];
}

export interface Toast {
  id: number;
  msg: string;
  type: string;
}

export interface BreadcrumbItem {
  label: string;
  view?: string;
}
