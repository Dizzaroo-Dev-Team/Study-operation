import React, { useState, useEffect, useMemo } from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'
import SiteRequiredPrompt from '@/components/SiteRequiredPrompt'
import { useSites } from '@/lib/queries/useStudies'
import {
  useMonitoringIssues,
  useMonitoringVisits,
} from '@/lib/queries/useMonitoring'
import { useLogisticsList } from '@/lib/queries/useLogistics'
import { useTasksList } from '@/lib/queries/useTasks'
import { MonitoringVisit, MonitoringIssue } from '@/types'
import { SiteLogistics } from '@/types'
import { MonitoringTask } from '@/types'
import {
  SiteOperationalStatus,
  PrimarySiteStatus,
  SiteStatusDetail,
} from '@/features/sites/types/siteStatus'
import {
  buildSiteStatusList,
  fetchSiteStatusDetail,
} from '@/features/sites/services/siteStatusService'
import SiteHeaderBanner from './SiteHeaderBanner'
import QuestionnaireActions from '@/features/feasibility/components/QuestionnaireActions'

interface Site {
  id: string
  site_id?: string
  siteId?: string
  name?: string
  siteName?: string
  location?: string
  study_id?: string
  studyId?: string
  status?: string
}

interface SiteStatusTabProps {
  apiBase?: string
}

const DEFAULT_PRIMARY_STATUS: PrimarySiteStatus = 'UNDER_EVALUATION'

const formatPrimaryStatusLabel = (status?: PrimarySiteStatus | null): string => {
  // UI must always show a valid lifecycle status; default to UNDER_EVALUATION
  if (!status) return 'Under Evaluation'
  switch (status) {
    case 'UNDER_EVALUATION':
      return 'Under Evaluation'
    case 'STARTUP':
      return 'Under Start-up'
    case 'INITIATING':
      return 'Initiating'
    case 'INITIATED_NOT_RECRUITING':
      return 'Initiated – Not Yet Recruiting'
    case 'RECRUITING':
      return 'Open for Recruitment'
    case 'ACTIVE_NOT_RECRUITING':
      return 'Active – Not Recruiting'
    case 'SUSPENDED':
      return 'Suspended'
    case 'TERMINATED':
      return 'Terminated'
    case 'WITHDRAWN':
      return 'Withdrawn'
    case 'COMPLETED':
      return 'Completed'
    case 'CLOSED':
      return 'Closed (Site Close-out Completed)'
    default:
      return String(status).replace(/_/g, ' ')
  }
}

const primaryStatusClinicalDescription = (status?: PrimarySiteStatus | null): string => {
  const effectiveStatus: PrimarySiteStatus =
    (status as PrimarySiteStatus | null) || DEFAULT_PRIMARY_STATUS

  switch (effectiveStatus) {
    case 'UNDER_EVALUATION':
      return 'Feasibility and pre‑selection phase – site identified, CDA/SFQ/SQV in progress.'
    case 'STARTUP':
      return 'Contracting and regulatory start‑up – CTA and ethics approvals, essential documents collection.'
    case 'INITIATING':
      return 'Site initiation activities – SIV kit dispatch, training, and readiness checks.'
    case 'INITIATED_NOT_RECRUITING':
      return 'Initiation complete; site activated but not yet opened for patient recruitment.'
    case 'RECRUITING':
      return 'Site is authorised to start screening and enrolling subjects.'
    case 'ACTIVE_NOT_RECRUITING':
      return 'Enrollment closed; subjects remain on treatment or in follow‑up.'
    case 'SUSPENDED':
      return 'Temporary pause of study activities at this site (may resume to previous status).'
    case 'TERMINATED':
      return 'Permanent stop of the study at this site – no further enrollment or follow‑up.'
    case 'WITHDRAWN':
      return 'Site will not participate in the study (e.g. not selected or withdrawn before enrollment).'
    case 'COMPLETED':
      return 'All protocol‑required activities and follow‑up have been completed at this site.'
    case 'CLOSED':
      return 'Site close‑out visit completed and all close‑out activities finalised.'
    default:
      return ''
  }
}

const SiteStatusTab: React.FC<SiteStatusTabProps> = ({ apiBase = '/api' }) => {
  const { selectedStudyId, selectedSiteId } = useStudySite()

  const [selectedStatusSiteDetail, setSelectedStatusSiteDetail] = useState<SiteStatusDetail | null>(null)
  const [error] = useState<string | null>(null)

  // Same five data sources as SiteControlTower — sharing the cache means
  // switching tabs is now free.
  const sitesQuery = useSites(selectedStudyId)
  const visitsQuery = useMonitoringVisits()
  const issuesQuery = useMonitoringIssues({
    study_id: selectedStudyId ?? null,
    site_id: selectedSiteId ?? null,
  })
  const logisticsQuery = useLogisticsList({
    study_id: selectedStudyId ?? null,
    site_id: selectedSiteId ?? null,
  })
  const tasksQuery = useTasksList()

  const sites: Site[] = (sitesQuery.data ?? []) as unknown as Site[]
  const visits: MonitoringVisit[] = (visitsQuery.data ?? []) as MonitoringVisit[]
  const issues: MonitoringIssue[] = (issuesQuery.data ?? []) as MonitoringIssue[]
  const logistics: SiteLogistics[] = logisticsQuery.data ?? []
  const tasks: MonitoringTask[] = tasksQuery.data ?? []

  const loading =
    sitesQuery.isLoading ||
    visitsQuery.isLoading ||
    issuesQuery.isLoading ||
    logisticsQuery.isLoading ||
    tasksQuery.isLoading

  const handleStatusUpdate = async () => {
    // Reload site status detail after action
    if (selectedSiteId) {
      try {
        const detail = await fetchSiteStatusDetail(apiBase, selectedSiteId)
        setSelectedStatusSiteDetail(detail)
      } catch (err: any) {
        console.warn('Failed to refresh site status detail:', err)
      }
    }
  }

  // Load detailed status timeline for the selected site
  useEffect(() => {
    const loadDetail = async () => {
      if (!selectedSiteId) {
        setSelectedStatusSiteDetail(null)
        return
      }
      try {
        const detail = await fetchSiteStatusDetail(apiBase, selectedSiteId)
        setSelectedStatusSiteDetail(detail)
      } catch (err: any) {
        console.warn('Failed to fetch site status detail:', err)
        setSelectedStatusSiteDetail(null)
      }
    }

    loadDetail()
  }, [apiBase, selectedSiteId])

  // Build aggregated site status list - ONLY for selected site
  const siteStatusList = useMemo(() => {
    if (!selectedStudyId || !selectedSiteId) return []
    if (sites.length === 0) return []
    
    // Filter sites to only the selected site
    const selectedSite = sites.find(
      (s) => 
        (s.site_id || s.siteId || s.id) === selectedSiteId ||
        s.id === selectedSiteId
    )
    
    if (!selectedSite) return []
    
    // Build status for only the selected site
    return buildSiteStatusList({ 
      sites: [selectedSite], 
      visits, 
      issues, 
      logistics, 
      tasks 
    })
  }, [sites, visits, issues, logistics, tasks, selectedStudyId, selectedSiteId])

  // For single site, no need for filtering/sorting - just use the first (and only) item
  const siteStatus = siteStatusList.length > 0 ? siteStatusList[0] : null

  // Summary statistics - not needed for single site operational view, but kept for future use

  const formatDate = (date: string | Date | undefined) => {
    if (!date) return '–'
    try {
      return new Date(date).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    } catch {
      return '–'
    }
  }

  const formatCurrency = (amount: number | undefined) => {
    if (amount === undefined || amount === null) return 'N/A'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount)
  }

  const getStatusBadgeColor = (status: SiteOperationalStatus) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-800 border-green-300'
      case 'on-hold':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300'
      case 'not-started':
        return 'bg-gray-100 text-gray-800 border-gray-300'
      case 'closed':
        return 'bg-blue-100 text-blue-800 border-blue-300'
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300'
    }
  }

  const getRiskBadgeColor = (riskLevel?: 'low' | 'medium' | 'high') => {
    switch (riskLevel) {
      case 'high':
        return 'bg-red-100 text-red-800 border-red-300'
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300'
      case 'low':
        return 'bg-green-100 text-green-800 border-green-300'
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300'
    }
  }


  if (!selectedStudyId || !selectedSiteId) {
    return <SiteRequiredPrompt fullPage feature="Site Status" />
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-dizzaroo-deep-blue mb-4"></div>
          <p className="text-gray-600">Loading site status data...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="text-center">
          <div className="text-6xl mb-4">⚠️</div>
          <h2 className="text-xl font-semibold text-red-600 mb-2">Error</h2>
          <p className="text-gray-600">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-lg hover:bg-dizzaroo-blue-green transition"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">
      {/* Fixed Site Header Banner */}
      <SiteHeaderBanner 
        apiBase={apiBase}
        currentStatus={selectedStatusSiteDetail?.current_status || null}
      />

      <div className="flex-1 overflow-y-auto p-6" style={{ minHeight: 0 }}>
        {/* Page Header */}
        <div className="mb-6" data-testid="site-status-header">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Site Status</h1>
          <p className="text-gray-600">
            Backend‑driven clinical status overview with operational, monitoring, and logistics context
            for this site.
          </p>
        </div>


        {/* Site Status Details Card – clinical lifecycle (primary + breakdown + timeline) */}
        {siteStatus ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <div className="p-6">
              {/* PRIMARY status display */}
              <div className="mb-6 pb-4 border-b border-gray-200">
                <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 inline-block" data-testid="site-status-primary">
                  <div className="text-xs uppercase font-semibold text-blue-700 tracking-wide">
                    Current Site Status (Primary – Excel Column A)
                  </div>
                  <div className="mt-1 text-lg font-bold text-blue-900">
                    {formatPrimaryStatusLabel(
                      selectedStatusSiteDetail?.current_status || DEFAULT_PRIMARY_STATUS,
                    )}
                  </div>
                  <div className="mt-1 text-xs text-blue-800/80">
                    {primaryStatusClinicalDescription(selectedStatusSiteDetail?.current_status)}
                  </div>
                </div>
              </div>

              {/* SECONDARY: Status Breakdown (Sub‑statuses / checkpoints, Excel columns B–D) */}
              <div className="mb-8 border-t border-gray-200 pt-6">
                <h3 className="text-base font-semibold text-gray-900 mb-2">
                  Status Breakdown (Excel Columns B–D)
                </h3>
                <p className="text-xs text-gray-600 mb-4">
                  Read‑only view of key clinical milestones that explain why the site is in its
                  current Primary Site Status.
                </p>
                {!selectedStatusSiteDetail ? (
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                    <div className="text-sm text-gray-600">
                      <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></span>
                      Loading status breakdown...
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-4">
                    {/* TEST: Always show this to verify changes are loaded */}
                    <div className="border-4 border-red-500 rounded-lg p-4 bg-yellow-100 mb-4">
                      <p className="text-sm font-bold text-red-700">
                        🔧 DEBUG: Site Status Tab Loaded - Current Status: {selectedStatusSiteDetail?.current_status || 'NULL'}
                      </p>
                      <p className="text-xs text-gray-600 mt-1">
                        Selected Site ID: {selectedSiteId || 'NONE'} | Status Detail exists: {selectedStatusSiteDetail ? 'YES' : 'NO'} | 
                        Is UNDER_EVALUATION? {selectedStatusSiteDetail?.current_status === 'UNDER_EVALUATION' ? 'YES ✓' : 'NO ✗'}
                      </p>
                    </div>
                    
                    {/* UNDER EVALUATION */}
                    {selectedStatusSiteDetail?.current_status === 'UNDER_EVALUATION' && (
                      <div className="space-y-4">
                        {/* Legacy CDA/Questionnaire sections (keeping for backward compatibility) */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">

                        {/* CDA Workflow Section */}
                        <div className="border border-gray-200 rounded-lg p-4 bg-white">
                          <h4 className="text-xs font-semibold text-gray-700 uppercase mb-3">
                            CDA (Confidentiality Disclosure Agreement)
                          </h4>
                          {(() => {
                            const m = (selectedStatusSiteDetail.secondary_statuses ||
                              {}) as Record<string, any>
                            // Map backend status to component status
                            let cdaStatus = m.cda_status || 'NOT_CREATED'
                            if (cdaStatus === 'SIGNED') cdaStatus = 'SIGNED'
                            else if (cdaStatus === 'SENT') cdaStatus = 'SENT'
                            else cdaStatus = 'NOT_CREATED'

                            // The site CDA now runs on the general workflow engine as an
                            // agreement (no more legacy /sites/{id}/cda actions). This panel
                            // shows readiness (marked by the engine→site-readiness bridge when
                            // the CDA is executed) and points the user to the Agreements tab.
                            const badge =
                              cdaStatus === 'SIGNED'
                                ? { t: 'Executed', c: 'bg-green-100 text-green-800' }
                                : cdaStatus === 'SENT'
                                ? { t: 'In progress', c: 'bg-blue-100 text-blue-800' }
                                : { t: 'Not started', c: 'bg-gray-100 text-gray-700' }
                            return (
                              <div className="space-y-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-semibold text-gray-600 uppercase">Status:</span>
                                  <span className={`px-2 py-1 rounded text-xs font-semibold ${badge.c}`}>{badge.t}</span>
                                </div>
                                <p className="text-xs text-gray-600 leading-relaxed">
                                  The CDA runs on the workflow engine as an agreement. Open the{' '}
                                  <span className="font-semibold">Agreements</span> tab to create it and send for
                                  signature (or attach an executed copy if signed offline). This site’s CDA
                                  readiness updates automatically once it’s executed.
                                </p>
                              </div>
                            )
                          })()}
                        </div>

                        {/* Questionnaire Section */}
                        <div className="border border-gray-200 rounded-lg p-4 bg-white">
                          <h4 className="text-xs font-semibold text-gray-700 uppercase mb-3">
                            Site Feasibility Questionnaire (SFQ)
                          </h4>
                          {(() => {
                            const m = (selectedStatusSiteDetail.secondary_statuses ||
                              {}) as Record<string, any>
                            // Map backend status to component status
                            let sfqStatus = m.sfq_status || 'NOT_SENT'
                            if (sfqStatus === 'RECEIVED') sfqStatus = 'RECEIVED'
                            else if (sfqStatus === 'SENT') sfqStatus = 'SENT'
                            else sfqStatus = 'NOT_SENT'

                            return (
                              <QuestionnaireActions
                                siteId={selectedSiteId || ''}
                                apiBase={apiBase}
                                questionnaireStatus={sfqStatus}
                                questionnaireMetadata={{
                                  sent_at: m.sfq_sent_at,
                                  sent_by: m.sfq_sent_by,
                                  received_at: m.sfq_received_at,
                                }}
                                onUpdate={handleStatusUpdate}
                              />
                            )
                          })()}
                        </div>

                        {/* Read-only SQV Status */}
                        <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                          <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                            Site Qualification Visit (SQV)
                          </h4>
                          {(() => {
                            const m = (selectedStatusSiteDetail.secondary_statuses ||
                              {}) as Record<string, any>
                            return (
                              <ul className="space-y-1 text-sm">
                                <li className="flex items-center justify-between">
                                  <span>SQV Status</span>
                                  <span className="text-xs font-semibold text-gray-800">
                                    {m.sqv_status || m.svq_status || 'Not recorded'}
                                  </span>
                                </li>
                                <li className="flex items-center justify-between">
                                  <span>SQV Outcome</span>
                                  <span className="text-xs font-semibold text-gray-800">
                                    {m.sqv_outcome || 'Not recorded'}
                                  </span>
                                </li>
                              </ul>
                            )
                          })()}
                        </div>
                        </div>
                      </div>
                    )}

                    {/* STARTUP */}
                    {selectedStatusSiteDetail.current_status === 'STARTUP' && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          Under Start‑up
                        </h4>
                        {(() => {
                          const m = (selectedStatusSiteDetail.secondary_statuses ||
                            {}) as Record<string, any>
                          return (
                            <ul className="space-y-1 text-sm">
                              <li className="flex items-center justify-between">
                                <span>CTA (Clinical Trial Agreement)</span>
                                <span className="text-xs font-semibold text-gray-800">
                                  {m.cta_status || 'Not recorded'}
                                </span>
                              </li>
                              <li className="flex items-center justify-between">
                                <span>Ethical Approval</span>
                                <span className="text-xs font-semibold text-gray-800">
                                  {m.ethics_status || 'Not recorded'}
                                </span>
                              </li>
                              <li className="flex items-center justify-between">
                                <span>Essential Documents Collected</span>
                                <span
                                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                    m.essential_documents_collected
                                      ? 'bg-green-100 text-green-800'
                                      : 'bg-gray-100 text-gray-500'
                                  }`}
                                >
                                  {m.essential_documents_collected ? 'Yes' : 'No'}
                                </span>
                              </li>
                            </ul>
                          )
                        })()}
                      </div>
                    )}

                    {/* INITIATING */}
                    {selectedStatusSiteDetail.current_status === 'INITIATING' && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          Initiating
                        </h4>
                        {(() => {
                          const m = (selectedStatusSiteDetail.secondary_statuses ||
                            {}) as Record<string, any>
                          return (
                            <ul className="space-y-1 text-sm">
                              <li className="flex items-center justify-between">
                                <span>Dispatch of SIV Kits</span>
                                <span
                                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                    m.siv_kit_dispatched
                                      ? 'bg-green-100 text-green-800'
                                      : 'bg-gray-100 text-gray-500'
                                  }`}
                                >
                                  {m.siv_kit_dispatched ? 'Completed' : 'Pending'}
                                </span>
                              </li>
                              <li className="flex items-center justify-between">
                                <span>Study Materials Available</span>
                                <span
                                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                    m.study_material_available
                                      ? 'bg-green-100 text-green-800'
                                      : 'bg-gray-100 text-gray-500'
                                  }`}
                                >
                                  {m.study_material_available ? 'Yes' : 'No'}
                                </span>
                              </li>
                              <li className="flex items-center justify-between">
                                <span>IP Available</span>
                                <span
                                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                    m.ip_available
                                      ? 'bg-green-100 text-green-800'
                                      : 'bg-gray-100 text-gray-500'
                                  }`}
                                >
                                  {m.ip_available ? 'Yes' : 'No'}
                                </span>
                              </li>
                              <li className="flex items-center justify-between">
                                <span>Non‑IP Available</span>
                                <span
                                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                    m.non_ip_available
                                      ? 'bg-green-100 text-green-800'
                                      : 'bg-gray-100 text-gray-500'
                                  }`}
                                >
                                  {m.non_ip_available ? 'Yes' : 'No'}
                                </span>
                              </li>
                              <li className="flex items-center justify-between">
                                <span>Fixing of SIV Date</span>
                                <span className="text-xs text-gray-800">
                                  {m.siv_date ? formatDate(m.siv_date) : 'Not scheduled'}
                                </span>
                              </li>
                              <li className="flex items-center justify-between">
                                <span>SIV Completion</span>
                                <span
                                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                    m.siv_completed
                                      ? 'bg-green-100 text-green-800'
                                      : 'bg-gray-100 text-gray-500'
                                  }`}
                                >
                                  {m.siv_completed ? 'Completed' : 'Pending'}
                                </span>
                              </li>
                            </ul>
                          )
                        })()}
                      </div>
                    )}

                    {/* INITIATED NOT YET RECRUITING */}
                    {selectedStatusSiteDetail.current_status === 'INITIATED_NOT_RECRUITING' && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          Initiated – Not Yet Recruiting
                        </h4>
                        {(() => {
                          const m = (selectedStatusSiteDetail.secondary_statuses ||
                            {}) as Record<string, any>
                          return (
                            <ul className="space-y-1 text-sm">
                              <li className="flex items-center justify-between">
                                <span>Initiation Completed</span>
                                <span className="text-xs text-gray-800">
                                  {m.initiation_completed_at
                                    ? formatDate(m.initiation_completed_at)
                                    : 'Not recorded'}
                                </span>
                              </li>
                              <li>
                                <span className="block text-xs font-semibold text-gray-600">
                                  Recruitment Blockers
                                </span>
                                {Array.isArray(m.recruitment_blockers) &&
                                m.recruitment_blockers.length > 0 ? (
                                  <ul className="mt-1 list-disc list-inside text-xs text-gray-700 space-y-0.5">
                                    {m.recruitment_blockers.map((b: string, idx: number) => (
                                      <li key={idx}>{b}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <span className="text-xs text-gray-500">
                                    No blockers recorded.
                                  </span>
                                )}
                              </li>
                            </ul>
                          )
                        })()}
                      </div>
                    )}

                    {/* RECRUITING */}
                    {selectedStatusSiteDetail.current_status === 'RECRUITING' && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          Open for Recruitment
                        </h4>
                        {(() => {
                          const m = (selectedStatusSiteDetail.secondary_statuses ||
                            {}) as Record<string, any>
                          return (
                            <ul className="space-y-1 text-sm">
                              <li className="flex items-center justify-between">
                                <span>Recruitment Enabled On</span>
                                <span className="text-xs text-gray-800">
                                  {m.recruitment_enabled_at
                                    ? formatDate(m.recruitment_enabled_at)
                                    : 'Not recorded'}
                                </span>
                              </li>
                              <li className="text-xs text-gray-600">
                                Ready to start screening after closure of SIV action items.
                              </li>
                            </ul>
                          )
                        })()}
                      </div>
                    )}

                    {/* ACTIVE NOT RECRUITING */}
                    {selectedStatusSiteDetail.current_status === 'ACTIVE_NOT_RECRUITING' && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          Active – Not Recruiting
                        </h4>
                        {(() => {
                          const m = (selectedStatusSiteDetail.secondary_statuses ||
                            {}) as Record<string, any>
                          return (
                            <ul className="space-y-1 text-sm">
                              <li className="flex items-center justify-between">
                                <span>Enrollment Closed On</span>
                                <span className="text-xs text-gray-800">
                                  {m.enrollment_closed_at
                                    ? formatDate(m.enrollment_closed_at)
                                    : 'Not recorded'}
                                </span>
                              </li>
                              <li className="text-xs text-gray-600">
                                Enrollment closed; patients under treatment or follow‑up.
                              </li>
                            </ul>
                          )
                        })()}
                      </div>
                    )}

                    {/* COMPLETED */}
                    {selectedStatusSiteDetail.current_status === 'COMPLETED' && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          Completed
                        </h4>
                        {(() => {
                          const m = (selectedStatusSiteDetail.secondary_statuses ||
                            {}) as Record<string, any>
                          return (
                            <ul className="space-y-1 text-sm">
                              <li className="flex items-center justify-between">
                                <span>All Subjects Completed At</span>
                                <span className="text-xs text-gray-800">
                                  {m.all_subjects_completed_at
                                    ? formatDate(m.all_subjects_completed_at)
                                    : 'Not recorded'}
                                </span>
                              </li>
                              <li className="text-xs text-gray-600">
                                Finished all study activities at the site.
                              </li>
                            </ul>
                          )
                        })()}
                      </div>
                    )}

                    {/* CLOSED */}
                    {selectedStatusSiteDetail.current_status === 'CLOSED' && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          Closed
                        </h4>
                        {(() => {
                          const m = (selectedStatusSiteDetail.secondary_statuses ||
                            {}) as Record<string, any>
                          return (
                            <ul className="space-y-1 text-sm">
                              <li className="flex items-center justify-between">
                                <span>Site Close‑out Visit Date</span>
                                <span className="text-xs text-gray-800">
                                  {m.close_out_visit_date
                                    ? formatDate(m.close_out_visit_date)
                                    : 'Not recorded'}
                                </span>
                              </li>
                              <li className="text-xs text-gray-600">
                                Site close‑out done and all activities closed.
                              </li>
                            </ul>
                          )
                        })()}
                      </div>
                    )}

                    {/* SUSPENDED / TERMINATED / WITHDRAWN – summarise state */}
                    {['SUSPENDED', 'TERMINATED', 'WITHDRAWN'].includes(
                      selectedStatusSiteDetail.current_status || '',
                    ) && (
                      <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">
                          {formatPrimaryStatusLabel(selectedStatusSiteDetail.current_status)}
                        </h4>
                        <p className="text-sm text-gray-600">
                          {primaryStatusClinicalDescription(selectedStatusSiteDetail.current_status)}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* TERTIARY: Operational / Monitoring / Risk / Logistics (supporting context) */}
              <h3 className="mt-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Operational & Monitoring Context
              </h3>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* Status Grid (operational / risk / monitoring / tasks – derived from monitoring/logistics) */}
                {/* Operational Status */}
                {/* Operational Status */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-2">
                    System Operational State
                  </h3>
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-semibold border ${getStatusBadgeColor(
                        siteStatus.operationalStatus,
                      )}`}
                    >
                      {siteStatus.operationalStatus === 'not-started'
                        ? 'Not Started'
                        : siteStatus.operationalStatus === 'on-hold'
                        ? 'On Hold'
                        : siteStatus.operationalStatus.charAt(0).toUpperCase() +
                          siteStatus.operationalStatus.slice(1)}
                    </span>
                  </div>
                </div>

                {/* Risk Level */}
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-purple-600 uppercase tracking-wide mb-2">
                    Risk Level
                  </h3>
                  {siteStatus.riskLevel ? (
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-semibold border ${getRiskBadgeColor(
                        siteStatus.riskLevel,
                      )}`}
                    >
                      {siteStatus.riskLevel.charAt(0).toUpperCase() +
                        siteStatus.riskLevel.slice(1)}
                    </span>
                  ) : (
                    <span className="text-sm text-gray-400">N/A</span>
                  )}
                </div>

                {/* Monitoring Summary */}
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-green-600 uppercase tracking-wide mb-2">
                    Monitoring
                  </h3>
                  <div className="space-y-1 text-sm">
                    <div className="text-gray-700">
                      <span className="font-semibold">Last Visit:</span>{' '}
                      {formatDate(siteStatus.lastMonitoringVisitDate)}
                    </div>
                    <div className="text-gray-700">
                      <span className="font-semibold">Next Visit:</span>{' '}
                      {formatDate(siteStatus.nextMonitoringVisitDate)}
                    </div>
                    <div className="text-gray-700">
                      <span className="font-semibold">Open Issues:</span>{' '}
                      {siteStatus.openMonitoringIssuesCount}
                    </div>
                  </div>
                </div>

                {/* Tasks Summary */}
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-orange-600 uppercase tracking-wide mb-2">
                    Tasks
                  </h3>
                  <div className="text-2xl font-bold text-orange-800">
                    {siteStatus.openMonitoringTasksCount}
                  </div>
                  <div className="text-xs text-orange-600 mt-1">Open Tasks</div>
                </div>
              </div>

              {/* Logistics & Financial (tertiary clinical context) */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
                {/* Patients */}
                <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-2">
                    Patients
                  </h3>
                  {siteStatus.activePatients !== undefined &&
                  siteStatus.totalPatients !== undefined ? (
                    <div className="space-y-1">
                      <div className="text-2xl font-bold text-indigo-800">
                        {siteStatus.activePatients} / {siteStatus.totalPatients}
                      </div>
                      <div className="text-xs text-indigo-600">Active / Total</div>
                    </div>
                  ) : (
                    <span className="text-sm text-gray-400">N/A</span>
                  )}
                </div>

                {/* Drug Inventory */}
                <div
                  className={`border rounded-lg p-4 ${
                  siteStatus.isDrugLow 
                    ? 'bg-red-50 border-red-200' 
                    : 'bg-emerald-50 border-emerald-200'
                  }`}
                >
                  <h3
                    className={`text-xs font-semibold uppercase tracking-wide mb-2 ${
                    siteStatus.isDrugLow ? 'text-red-600' : 'text-emerald-600'
                    }`}
                  >
                    Drug Inventory
                  </h3>
                  {siteStatus.drugRemaining !== undefined ? (
                    <div className="space-y-1">
                      <div
                        className={`text-2xl font-bold ${
                        siteStatus.isDrugLow ? 'text-red-800' : 'text-emerald-800'
                        }`}
                      >
                        {siteStatus.drugRemaining}
                      </div>
                      {siteStatus.isDrugLow && (
                        <div className="text-xs text-red-600 font-semibold">
                          ⚠️ Low Inventory
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-sm text-gray-400">N/A</span>
                  )}
                </div>

                {/* Financial */}
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                  <h3 className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-2">
                    Financial
                  </h3>
                  <div className="space-y-1 text-sm">
                    {siteStatus.amountPaid !== undefined && (
                      <div className="text-gray-700">
                        <span className="font-semibold">Paid:</span>{' '}
                        {formatCurrency(siteStatus.amountPaid)}
                      </div>
                    )}
                    {siteStatus.amountDue !== undefined ? (
                      <div
                        className={`${
                          siteStatus.amountDue > 10000
                            ? 'text-orange-600 font-semibold'
                            : 'text-gray-700'
                        }`}
                      >
                        <span className="font-semibold">Due:</span>{' '}
                        {formatCurrency(siteStatus.amountDue)}
                      </div>
                    ) : (
                      <div className="text-gray-400">Due: N/A</div>
                    )}
                  </div>
                </div>
              </div>

              {/* SECONDARY: Site Status Timeline (PrimarySiteStatus over time) */}
              <div className="mt-8 border-t border-gray-200 pt-6">
                <h3 className="text-base font-semibold text-gray-900 mb-3">
                  Site Status Timeline
                </h3>
                {(() => {
                  if (!selectedStatusSiteDetail) {
                    return (
                      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                        <div className="text-sm text-gray-600">
                          <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></span>
                          Loading status timeline...
                        </div>
                      </div>
                    )
                  }
                  if (selectedStatusSiteDetail.history.length === 0) {
                    return (
                      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                        <div className="text-sm text-gray-600">
                          No status history recorded yet.
                        </div>
                      </div>
                    )
                  }
                  return (
                    <ol className="relative border-l border-gray-200 ml-2">
                      {selectedStatusSiteDetail.history.map((entry, idx) => {
                        const isCurrent =
                          entry.status === selectedStatusSiteDetail.current_status &&
                          idx === selectedStatusSiteDetail.history.length - 1
                        return (
                          <li key={idx} className="mb-4 ml-4">
                            <div
                              className={`absolute w-3 h-3 rounded-full mt-1.5 -left-1.5 border ${
                                isCurrent
                                  ? 'bg-dizzaroo-deep-blue border-dizzaroo-deep-blue'
                                  : 'bg-white border-gray-300'
                              }`}
                            />
                            <time className="mb-1 text-xs font-normal leading-none text-gray-400">
                              {formatDate(entry.changed_at)}
                            </time>
                            <h4
                              className={`text-sm font-semibold ${
                                isCurrent ? 'text-dizzaroo-deep-blue' : 'text-gray-900'
                              }`}
                            >
                              {formatPrimaryStatusLabel(entry.status as PrimarySiteStatus)}
                              {entry.previous_status && (
                                <span className="text-xs text-gray-500 ml-2">
                                  (from {formatPrimaryStatusLabel(entry.previous_status)})
                                </span>
                              )}
                              {isCurrent && (
                                <span className="ml-2 text-[10px] uppercase tracking-wide text-dizzaroo-deep-blue/80">
                                  Current
                                </span>
                              )}
                            </h4>
                            {entry.metadata && Object.keys(entry.metadata).length > 0 && (
                              <p className="mt-1 text-xs text-gray-600">
                                {Object.entries(entry.metadata)
                                  .slice(0, 4)
                                  .map(([k, v]) => `${k}: ${String(v)}`)
                                  .join(' • ')}
                                {Object.keys(entry.metadata).length > 4 && ' • …'}
                              </p>
                            )}
                            {(entry as any).triggering_event || (entry as any).reason ? (
                              <p className="mt-1 text-xs text-gray-500">
                                {(entry as any).triggering_event && (
                                  <span className="font-semibold">
                                    Event: {(entry as any).triggering_event}
                                  </span>
                                )}
                                {(entry as any).triggering_event && (entry as any).reason && ' – '}
                                {(entry as any).reason && (
                                  <span>Reason: {(entry as any).reason}</span>
                                )}
                              </p>
                            ) : null}
                          </li>
                        )
                      })}
                    </ol>
                  )
                })()}
              </div>

              {/* KPI examples – future‑ready clinical metrics */}
              {selectedStatusSiteDetail && selectedStatusSiteDetail.history && (
                <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="border border-dashed border-gray-200 rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-gray-700 uppercase mb-1">
                      Days from SIV Completion → Recruitment Start
                    </h4>
                    {(() => {
                      const history = selectedStatusSiteDetail.history
                      let sivDate: Date | null = null
                      let recruitDate: Date | null = null

                      for (let i = history.length - 1; i >= 0; i--) {
                        const h = history[i] as any
                        if (h.status === 'INITIATING' && h.metadata && h.metadata.siv_completed) {
                          const raw = h.metadata.siv_date || h.changed_at
                          try {
                            sivDate = new Date(raw as any)
                          } catch {
                            sivDate = new Date(h.changed_at as any)
                          }
                          break
                        }
                      }

                      for (const hRaw of history as any[]) {
                        if (hRaw.status === 'RECRUITING') {
                          const raw = hRaw.metadata?.recruitment_enabled_at || hRaw.changed_at
                          try {
                            recruitDate = new Date(raw as any)
                          } catch {
                            recruitDate = new Date(hRaw.changed_at as any)
                          }
                          break
                        }
                      }

                      if (!sivDate || !recruitDate) {
                        return (
                          <p className="text-xs text-gray-500">
                            Not enough data yet to calculate – requires SIV completion and
                            recruitment enabled dates.
                          </p>
                        )
                      }
                      const diffMs = recruitDate.getTime() - sivDate.getTime()
                      const days = Math.max(0, Math.round(diffMs / (1000 * 60 * 60 * 24)))
                      return (
                        <p className="text-sm text-gray-800">
                          <span className="font-semibold">{days}</span> days between SIV
                          completion and recruitment start.
                        </p>
                      )
                    })()}
                  </div>
                  <div className="border border-dashed border-gray-200 rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-gray-700 uppercase mb-1">
                      Days from Initiation → First Recruitment
                    </h4>
                    <p className="text-xs text-gray-500">
                      This KPI will be populated once subject‑level enrollment data is available
                      (future integration with enrollment / EDC systems).
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
            <div className="text-4xl mb-2">📭</div>
            <p className="text-gray-600">No site status data available</p>
            <p className="text-sm text-gray-500 mt-1">
              Site status data will appear here once available
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default SiteStatusTab
