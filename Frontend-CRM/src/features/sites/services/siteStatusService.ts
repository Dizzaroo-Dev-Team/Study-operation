import {
  SiteStatus,
  SiteOperationalStatus,
  PrimarySiteStatus,
  StudyStatusSummary,
  SiteStatusDetail,
} from '@/features/sites/types/siteStatus'
import { MonitoringVisit, MonitoringIssue } from '@/types'
import { SiteLogistics } from '@/types'
import { MonitoringTask } from '@/types'
import { api } from '@/lib/api'

// Site interface matching API response
interface Site {
  id: string
  site_id?: string // API may return site_id
  siteId?: string // Or siteId
  name?: string // API returns 'name'
  siteName?: string // Or siteName
  location?: string
  study_id?: string
  studyId?: string
  status?: string
}

export function buildSiteStatusList(args: {
  sites: Site[]
  visits: MonitoringVisit[]
  issues: MonitoringIssue[]
  logistics: SiteLogistics[]
  tasks: MonitoringTask[]
}): SiteStatus[] {
  const { sites, visits, issues, logistics, tasks } = args

  return sites.map((site) => {
    // Normalize site identifiers
    const siteId = site.site_id || site.siteId || site.id
    const siteName = site.name || site.siteName || 'Unknown Site'
    
    // Find logistics for this site
    const siteLogistics = logistics.find((l) => l.siteId === siteId || l.siteId === site.id)

    // Find visits for this site
    const siteVisits = visits.filter(
      (v) => v.siteId === siteId || v.siteId === site.id
    )

    // Find issues for this site
    const siteIssues = issues.filter(
      (i) => i.siteId === siteId || i.siteId === site.id
    )

    // Find tasks for this site
    const siteTasks = tasks.filter(
      (t) =>
        t.links?.siteId === siteId ||
        t.links?.siteId === site.id ||
        t.siteId === siteId ||
        t.siteId === site.id
    )

    // Derive operational status
    let operationalStatus: SiteOperationalStatus = 'not-started'
    if (site.status) {
      // Map existing status field if available
      const statusLower = site.status.toLowerCase()
      if (statusLower.includes('not') || statusLower.includes('pending')) {
        operationalStatus = 'not-started'
      } else if (statusLower.includes('active') || statusLower.includes('open')) {
        operationalStatus = 'active'
      } else if (statusLower.includes('hold') || statusLower.includes('pause')) {
        operationalStatus = 'on-hold'
      } else if (statusLower.includes('close') || statusLower.includes('complete')) {
        operationalStatus = 'closed'
      }
    } else {
      // Derive from data
      const hasPatients = (siteLogistics?.activePatients || 0) > 0
      const hasVisits = siteVisits.length > 0

      if (!hasPatients && !hasVisits) {
        operationalStatus = 'not-started'
      } else {
        operationalStatus = 'active'
      }
    }

    // Last monitoring visit date
    let lastMonitoringVisitDate: Date | undefined
    if (siteVisits.length > 0) {
      const dates = siteVisits
        .map((v) => {
          if (v.actualDate) return new Date(v.actualDate)
          if (v.plannedDate) return new Date(v.plannedDate)
          return null
        })
        .filter((d): d is Date => d !== null)
        .sort((a, b) => b.getTime() - a.getTime())

      if (dates.length > 0) {
        lastMonitoringVisitDate = dates[0]
      }
    }

    // Next monitoring visit date
    let nextMonitoringVisitDate: Date | undefined
    if (siteVisits.length > 0) {
      const futureDates = siteVisits
        .map((v) => {
          if (v.plannedDate) {
            const planned = new Date(v.plannedDate)
            if (planned > new Date()) return planned
          }
          return null
        })
        .filter((d): d is Date => d !== null)
        .sort((a, b) => a.getTime() - b.getTime())

      if (futureDates.length > 0) {
        nextMonitoringVisitDate = futureDates[0]
      }
    }

    // Open monitoring issues count
    const openMonitoringIssuesCount = siteIssues.filter(
      (i) => i.status !== 'resolved' && i.status !== 'dismissed'
    ).length

    // Open monitoring tasks count
    const openMonitoringTasksCount = siteTasks.filter(
      (t) => t.status !== 'done' && t.status !== 'cancelled'
    ).length

    // Risk level calculation
    let riskLevel: 'low' | 'medium' | 'high' | undefined = 'low'
    const highRiskThreshold = 3 // Configurable threshold

    if (
      openMonitoringIssuesCount >= highRiskThreshold ||
      siteLogistics?.isDrugLow === true ||
      (siteLogistics?.amountDue && siteLogistics.amountDue > 10000) // High amount due
    ) {
      riskLevel = 'high'
    } else if (openMonitoringIssuesCount > 0 || openMonitoringTasksCount > 0) {
      riskLevel = 'medium'
    }

    return {
      siteId: siteId,
      siteName: siteName,
      location: site.location,
      operationalStatus,
      lastUpdatedAt: new Date(), // Could be derived from latest data update
      lastMonitoringVisitDate,
      nextMonitoringVisitDate,
      openMonitoringIssuesCount,
      openMonitoringTasksCount,
      totalPatients: siteLogistics?.totalPatients,
      activePatients: siteLogistics?.activePatients,
      drugRemaining: siteLogistics?.drugRemaining,
      isDrugLow: siteLogistics?.isDrugLow,
      amountPaid: siteLogistics?.amountPaid,
      amountDue: siteLogistics?.amountDue,
      riskLevel,
    }
  })
}

// ---------------------------------------------------------------------------
// Mock Data for Development
// ---------------------------------------------------------------------------

const mockStudyStatusSummary: StudyStatusSummary = {
  study_id: 'STUDY-001',
  study_name: 'Clinical Trial Study',
  study_status: 'RECRUITING',
  total_sites: 5,
  recruiting_sites: 2,
  status_counts: {
    UNDER_EVALUATION: 1,
    STARTUP: 1,
    INITIATING: 0,
    INITIATED_NOT_RECRUITING: 1,
    RECRUITING: 2,
    ACTIVE_NOT_RECRUITING: 0,
    COMPLETED: 0,
    SUSPENDED: 0,
    TERMINATED: 0,
    WITHDRAWN: 0,
    CLOSED: 0,
  },
  countries: [
    {
      country: 'United States',
      status: 'RECRUITING',
      total_sites: 3,
      recruiting_sites: 2,
      status_counts: {
        UNDER_EVALUATION: 0,
        STARTUP: 0,
        INITIATING: 0,
        INITIATED_NOT_RECRUITING: 1,
        RECRUITING: 2,
        ACTIVE_NOT_RECRUITING: 0,
        COMPLETED: 0,
        SUSPENDED: 0,
        TERMINATED: 0,
        WITHDRAWN: 0,
        CLOSED: 0,
      },
    },
    {
      country: 'Canada',
      status: 'STARTUP',
      total_sites: 2,
      recruiting_sites: 0,
      status_counts: {
        UNDER_EVALUATION: 1,
        STARTUP: 1,
        INITIATING: 0,
        INITIATED_NOT_RECRUITING: 0,
        RECRUITING: 0,
        ACTIVE_NOT_RECRUITING: 0,
        COMPLETED: 0,
        SUSPENDED: 0,
        TERMINATED: 0,
        WITHDRAWN: 0,
        CLOSED: 0,
      },
    },
  ],
}

const mockSiteStatusDetail: SiteStatusDetail = {
  site_id: 'SITE-001',
  site_external_id: 'SITE-001',
  study_id: 'STUDY-001',
  name: 'City General Hospital',
  country: 'United States',
  current_status: 'UNDER_EVALUATION',
  previous_status: null,
  secondary_statuses: {
    identified: true,
    cda_status: 'SIGNED',
    sfq_status: 'RECEIVED',
    sqv_status: 'COMPLETED',
    sqv_outcome: 'SELECTED',
  },
  history: [
    {
      status: 'UNDER_EVALUATION',
      previous_status: null,
      metadata: {
        identified: true,
        cda_status: 'SENT',
      },
      changed_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(), // 30 days ago
    },
    {
      status: 'UNDER_EVALUATION',
      previous_status: 'UNDER_EVALUATION',
      metadata: {
        identified: true,
        cda_status: 'SIGNED',
        sfq_status: 'SENT',
      },
      changed_at: new Date(Date.now() - 20 * 24 * 60 * 60 * 1000).toISOString(), // 20 days ago
    },
    {
      status: 'UNDER_EVALUATION',
      previous_status: 'UNDER_EVALUATION',
      metadata: {
        identified: true,
        cda_status: 'SIGNED',
        sfq_status: 'RECEIVED',
        sqv_status: 'SCHEDULED',
      },
      changed_at: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(), // 10 days ago
    },
    {
      status: 'UNDER_EVALUATION',
      previous_status: 'UNDER_EVALUATION',
      metadata: {
        identified: true,
        cda_status: 'SIGNED',
        sfq_status: 'RECEIVED',
        sqv_status: 'COMPLETED',
        sqv_outcome: 'SELECTED',
      },
      changed_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(), // 5 days ago
    },
  ],
}

const mockSitesByStatus: {
  site_id: string
  site_external_id?: string
  name: string
  country?: string
  current_status?: PrimarySiteStatus | null
  previous_status?: PrimarySiteStatus | null
}[] = [
  {
    site_id: 'SITE-001',
    site_external_id: 'SITE-001',
    name: 'City General Hospital',
    country: 'United States',
    current_status: 'UNDER_EVALUATION',
    previous_status: null,
  },
  {
    site_id: 'SITE-002',
    site_external_id: 'SITE-002',
    name: 'Metro Medical Center',
    country: 'United States',
    current_status: 'RECRUITING',
    previous_status: 'INITIATED_NOT_RECRUITING',
  },
  {
    site_id: 'SITE-003',
    site_external_id: 'SITE-003',
    name: 'Regional Health Clinic',
    country: 'United States',
    current_status: 'RECRUITING',
    previous_status: 'INITIATED_NOT_RECRUITING',
  },
]

// ---------------------------------------------------------------------------
// Backend‑driven Site Status API helpers (with mock fallback)
// ---------------------------------------------------------------------------

export async function fetchStudyStatusSummary(apiBase: string, studyId: string): Promise<StudyStatusSummary> {
  try {
    const response = await api.get<StudyStatusSummary>(
      `${apiBase}/site-status/summary?study_id=${encodeURIComponent(studyId)}`
    )
    return response.data
  } catch (error: any) {
    // For any non-200 response (401, 404, 500, etc.), use mock data
    console.warn(`Using mock study status summary (backend returned ${error.response?.status || 'error'}):`, error.message)
    return { ...mockStudyStatusSummary, study_id: studyId }
  }
}

export async function fetchSitesByPrimaryStatus(
  apiBase: string,
  studyId: string,
  status?: PrimarySiteStatus,
): Promise<
  {
    site_id: string
    site_external_id?: string
    name: string
    country?: string
    current_status?: PrimarySiteStatus | null
    previous_status?: PrimarySiteStatus | null
  }[]
> {
  try {
    const params: any = { study_id: studyId }
    if (status) {
      params.status = status
    }
    const response = await api.get(`${apiBase}/site-status/sites`, { params })
    return response.data
  } catch (error: any) {
    // For any non-200 response, use mock data
    console.warn(`Using mock sites by status (backend returned ${error.response?.status || 'error'}):`, error.message)
    if (status) {
      return mockSitesByStatus.filter((s) => s.current_status === status)
    }
    return mockSitesByStatus
  }
}

export async function fetchSiteStatusDetail(
  apiBase: string,
  siteId: string,
): Promise<SiteStatusDetail> {
  try {
    const response = await api.get<SiteStatusDetail>(`${apiBase}/site-status/sites/${encodeURIComponent(siteId)}`)
    return response.data
  } catch (error: any) {
    // For any non-200 response, use mock data
    console.warn(`Using mock site status detail (backend returned ${error.response?.status || 'error'}):`, error.message)
    const mockSite = mockSitesByStatus.find((s) => s.site_id === siteId)
    return {
      ...mockSiteStatusDetail,
      site_id: siteId,
      name: mockSite?.name || 'City General Hospital',
      country: mockSite?.country || 'United States',
      current_status: mockSite?.current_status || 'UNDER_EVALUATION',
      previous_status: mockSite?.previous_status || null,
    }
  }
}

