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
import {
  PrimarySiteStatus,
  SiteStatusDetail,
  ControlStage,
} from '@/features/sites/types/siteStatus'
import { fetchSiteStatusDetail } from '@/features/sites/services/siteStatusService'
import {
  mapRawStatusToControlStage,
  getStageProgress,
  isOnHold,
} from '@/features/sites/services/controlTowerMapping'
import { getStageConfig, controlTowerStages } from '@/features/sites/config/controlTowerConfig'
import ControlTowerSidebar from './ControlTowerSidebar'
import ControlTowerGraphs from './ControlTowerGraphs'
import ControlTowerMilestones from './ControlTowerMilestones'
import SiteHeaderBanner from './SiteHeaderBanner'
import UnderConsiderationWorkflow from '@/features/under-consideration/components/UnderConsiderationWorkflow'

interface SiteControlTowerProps {
  apiBase?: string
}

const formatPrimaryStatusLabel = (status?: PrimarySiteStatus | null): string => {
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
      // Exhaustive above for known statuses; fall back for unexpected values.
      return String(status).replace(/_/g, ' ')
  }
}

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


const SiteControlTower: React.FC<SiteControlTowerProps> = ({ apiBase = '/api' }) => {
  const { selectedStudyId, selectedSiteId } = useStudySite()

  const [selectedStatusSiteDetail, setSelectedStatusSiteDetail] = useState<SiteStatusDetail | null>(null)
  const [selectedStage, setSelectedStage] = useState<ControlStage | null>(null)
  const [error] = useState<string | null>(null)

  // Pull all five lists in parallel via shared caches — sibling components
  // (LogisticsTab, TasksTab, etc.) hit the same query keys, so this view
  // re-uses warm data instead of re-firing the request.
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

  const loading =
    sitesQuery.isLoading ||
    visitsQuery.isLoading ||
    issuesQuery.isLoading ||
    logisticsQuery.isLoading ||
    tasksQuery.isLoading

  // Load detailed status for selected site
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

  // Calculate Control Tower progress
  const progress = useMemo(() => {
    return getStageProgress(selectedStatusSiteDetail)
  }, [selectedStatusSiteDetail])

  // Determine current stage for display
  const currentStage = useMemo(() => {
    if (selectedStage) {
      return getStageConfig(selectedStage)
    }
    if (selectedStatusSiteDetail?.current_status) {
      const stage = mapRawStatusToControlStage(
        selectedStatusSiteDetail.current_status,
        selectedStatusSiteDetail.secondary_statuses || null
      )
      return getStageConfig(stage)
    }
    return getStageConfig('under_consideration')
  }, [selectedStage, selectedStatusSiteDetail])

  // Handle stage selection (UI-only, doesn't change backend)
  const handleStageSelect = (stageId: ControlStage) => {
    setSelectedStage(stageId)
  }

  // Initial stage selection when site detail changes
  // For this CRM, we want the "Under Consideration" workflow to show by default
  useEffect(() => {
    if (!selectedStage && selectedStatusSiteDetail) {
      setSelectedStage('under_consideration')
    }
  }, [selectedStatusSiteDetail, selectedStage])

  if (!selectedStudyId || !selectedSiteId) {
    return <SiteRequiredPrompt fullPage feature="the Site Activation Workflow" />
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-dizzaroo-deep-blue mb-4"></div>
          <p className="text-gray-600">Loading activation workflow...</p>
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

  const onHold = selectedStatusSiteDetail?.current_status
    ? isOnHold(selectedStatusSiteDetail.current_status)
    : false

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">
      {/* Site Summary Banner - displays site context, remains constant when switching stages */}
      <SiteHeaderBanner 
        apiBase={apiBase}
        currentStatus={selectedStatusSiteDetail?.current_status || null}
      />

      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        {/* Left Sidebar */}
        <ControlTowerSidebar
          currentStage={selectedStage || progress.currentStage}
          stages={controlTowerStages}
          onStageSelect={handleStageSelect}
          isOnHold={onHold}
          completedStages={progress.completedStages}
        />

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto p-6" style={{ minHeight: 0 }}>
          {/* Page Header */}
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Site Activation Workflow</h1>
            <p className="text-gray-600">
              Track activation milestones, complete required actions, and identify blockers for site activation.
            </p>
          </div>



        {/* Graphs Section */}
        {currentStage && selectedStatusSiteDetail && (
          <div className="mb-6">
            <ControlTowerGraphs
              progress={progress}
              currentStage={currentStage}
              metadata={selectedStatusSiteDetail.secondary_statuses || null}
              summary={null}
              stages={controlTowerStages}
              showPortfolio={false}
            />
          </div>
        )}

        {/* Under Consideration Workflow - Show ONLY when "Under Consideration" stage/tab is selected */}
        {selectedStage === 'under_consideration' && selectedSiteId && (
          <div className="mb-6">
            <UnderConsiderationWorkflow
              siteId={selectedSiteId}
              apiBase={apiBase}
              onUpdate={async () => {
                // Refresh site status detail after update
                if (selectedSiteId) {
                  try {
                    const detail = await fetchSiteStatusDetail(apiBase, selectedSiteId)
                    setSelectedStatusSiteDetail(detail)
                  } catch (err) {
                    console.error('Failed to refresh site status detail:', err)
                  }
                }
              }}
            />
          </div>
        )}

        {/* Milestones & Activities */}
        {currentStage && selectedStatusSiteDetail && (
          <div className="mb-6">
            <ControlTowerMilestones
              stage={currentStage}
              metadata={selectedStatusSiteDetail.secondary_statuses || null}
              siteDetail={selectedStatusSiteDetail}
              apiBase={apiBase}
              onUpdate={async () => {
                // Refresh site status detail after update
                if (selectedSiteId) {
                  try {
                    const detail = await fetchSiteStatusDetail(apiBase, selectedSiteId)
                    setSelectedStatusSiteDetail(detail)
                  } catch (err) {
                    console.error('Failed to refresh site status detail:', err)
                  }
                }
              }}
            />
          </div>
        )}

        {/* Activation Events Timeline */}
        {selectedStatusSiteDetail && selectedStatusSiteDetail.history.length > 0 && (() => {
          // Track seen milestone events to avoid duplicates
          // Use a combination of event type and status to identify unique milestone completions
          const seenMilestoneEvents = new Set<string>()
          const uniqueEvents: Array<{ entry: typeof selectedStatusSiteDetail.history[0], idx: number, description: string }> = []

          selectedStatusSiteDetail.history.forEach((entry, idx) => {
            // Extract meaningful event description from triggering_event, metadata, or status change
            const getEventDescription = (): { description: string | null, eventKey: string | null } => {
              // Prefer triggering_event if available
              if (entry.triggering_event) {
                return { description: entry.triggering_event, eventKey: entry.triggering_event }
              }

              const m = entry.metadata || {}
              const prevStatus = entry.previous_status
              const currStatus = entry.status

              // Extract milestone completion events - use eventKey to track unique completions
              // Check previous entry to see if this is a transition
              const prevEntry = idx > 0 ? selectedStatusSiteDetail.history[idx - 1] : null
              const prevM = prevEntry?.metadata || {}

              // Only show milestone events when they transition (e.g., NOT_CREATED -> SENT -> SIGNED)
              if (m.cda_status === 'SIGNED' && prevM.cda_status !== 'SIGNED') {
                return { description: 'CDA signed', eventKey: 'cda_signed' }
              }
              if (m.sfq_status === 'RECEIVED' && prevM.sfq_status !== 'RECEIVED') {
                return { description: 'SFQ received', eventKey: 'sfq_received' }
              }
              if ((m.sqv_status === 'COMPLETED' || m.svq_status === 'COMPLETED') && 
                  prevM.sqv_status !== 'COMPLETED' && prevM.svq_status !== 'COMPLETED') {
                return { description: 'SQV completed', eventKey: 'sqv_completed' }
              }
              if (m.cta_status === 'SIGNED' && prevM.cta_status !== 'SIGNED') {
                return { description: 'CTA signed', eventKey: 'cta_signed' }
              }
              if (m.ethics_status === 'APPROVED' && prevM.ethics_status !== 'APPROVED') {
                return { description: 'Ethics approved', eventKey: 'ethics_approved' }
              }
              if (m.siv_completed && !prevM.siv_completed) {
                return { description: 'SIV completed', eventKey: 'siv_completed' }
              }
              if (m.recruitment_enabled_at && !prevM.recruitment_enabled_at) {
                return { description: 'Recruitment enabled', eventKey: 'recruitment_enabled' }
              }

              // Only show status change if it's a real transition (different from previous)
              if (prevStatus && prevStatus !== currStatus) {
                const statusKey = `status_${currStatus}`
                return { 
                  description: `Status changed to ${formatPrimaryStatusLabel(currStatus as PrimarySiteStatus)}`,
                  eventKey: statusKey
                }
              }
              
              // Skip entries that don't represent a real transition
              return { description: null, eventKey: null }
            }

            const { description, eventKey } = getEventDescription()
            
            // Only add if we have a meaningful event and haven't seen this exact milestone before
            // This ensures one entry per unique milestone completion
            if (description && eventKey && !seenMilestoneEvents.has(eventKey)) {
              seenMilestoneEvents.add(eventKey)
              uniqueEvents.push({ entry, idx, description })
            }
          })

          if (uniqueEvents.length === 0) {
            return null
          }

          return (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h3 className="text-base font-semibold text-gray-900 mb-3">Activation Events</h3>
              <ol className="relative border-l border-gray-200 ml-2">
                {uniqueEvents.map(({ entry, idx, description }) => {
                  const isCurrent =
                    entry.status === selectedStatusSiteDetail.current_status &&
                    idx === selectedStatusSiteDetail.history.length - 1

                  return (
                    <li key={idx} className="mb-3 ml-4">
                      <div
                        className={`absolute w-2 h-2 rounded-full mt-1.5 -left-1.5 ${
                          isCurrent
                            ? 'bg-dizzaroo-deep-blue border-2 border-dizzaroo-deep-blue'
                            : 'bg-gray-300'
                        }`}
                      />
                      <time className="mb-1 text-xs font-normal leading-none text-gray-500">
                        {formatDate(entry.changed_at)}
                      </time>
                      <div className={`text-sm ${isCurrent ? 'font-semibold text-dizzaroo-deep-blue' : 'text-gray-900'}`}>
                        {description}
                        {isCurrent && (
                          <span className="ml-2 text-xs text-gray-500">(Current)</span>
                        )}
                      </div>
                      {entry.reason && (
                        <p className="mt-1 text-xs text-gray-600">{entry.reason}</p>
                      )}
                    </li>
                  )
                })}
              </ol>
            </div>
          )
        })()}
        </div>
      </div>
    </div>
  )
}

export default SiteControlTower

