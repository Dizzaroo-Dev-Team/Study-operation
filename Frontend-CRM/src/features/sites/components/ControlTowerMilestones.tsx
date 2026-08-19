import React from 'react'
import { ControlTowerStage, Milestone, Activity } from '@/features/sites/types/siteStatus'
import { useReadinessGating } from '@/features/sites/hooks/useReadinessGating'
import { SiteStatusDetail } from '@/features/sites/types/siteStatus'
import { useSiteWorkflowSteps } from '@/lib/queries/useStudies'
import { useStudySite } from '@/contexts/StudySiteContext'

interface ControlTowerMilestonesProps {
  stage: ControlTowerStage
  metadata: Record<string, any> | null
  siteDetail: SiteStatusDetail | null
  onActivityClick?: (activityId: string) => void
  onUpdate?: () => void
  apiBase?: string
}

const ControlTowerMilestones: React.FC<ControlTowerMilestonesProps> = ({
  stage,
  metadata,
  siteDetail,
  onActivityClick,
}) => {
  const { selectedStudyId } = useStudySite()
  const readiness = useReadinessGating(siteDetail, 'open_for_recruitment')

  // Only poll when this card is showing the Under Consideration stage AND
  // we have a site + study to scope the query to.
  const isUnderConsideration = stage.id === 'under_consideration'
  const workflowQuery = useSiteWorkflowSteps(
    siteDetail?.site_id ?? null,
    selectedStudyId ?? null,
    {
      enabled: isUnderConsideration && Boolean(siteDetail?.site_id && selectedStudyId),
    },
  )
  // Legacy behavior: a fetch failure returned null (distinct from "no
  // steps yet"). Preserve that signal so completionRule helpers can branch.
  const workflowSteps = workflowQuery.isError ? null : workflowQuery.data ?? null

  const isMilestoneCompleted = (milestone: Milestone): boolean => {
    return milestone.completionRule(metadata, workflowSteps)
  }

  const isActivityEnabled = (activity: Activity): boolean => {
    return activity.enabledRule(stage.id, metadata)
  }

  const handleActivityClick = (activity: Activity) => {
    if (!isActivityEnabled(activity)) {
      return
    }

    if (activity.action) {
      activity.action()
    }

    if (onActivityClick) {
      onActivityClick(activity.id)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">{stage.label}</h3>
        {stage.definition && (
          <p className="text-sm text-gray-700 italic mb-2">{stage.definition}</p>
        )}
        {stage.description && (
          <p className="text-sm text-gray-600">{stage.description}</p>
        )}
      </div>

      {/* Milestones Section */}
      {stage.milestones && stage.milestones.length > 0 && (
        <div className="mb-8">
          <h4 className="text-base font-semibold text-gray-800 mb-4">
            Required Milestones
            {stage.milestones.filter(m => m.blocking && !isMilestoneCompleted(m)).length > 0 && (
              <span className="ml-2 text-xs text-red-600 font-normal">
                ({stage.milestones.filter(m => m.blocking && !isMilestoneCompleted(m)).length} blocking)
              </span>
            )}
          </h4>
          <div className="space-y-2">
            {stage.milestones.map((milestone) => {
              const completed = isMilestoneCompleted(milestone)
              const isBlocking = milestone.blocking && !completed

              return (
                <div
                  key={milestone.id}
                  className={`flex items-start p-3 rounded-lg border ${
                    completed
                      ? 'bg-green-50 border-green-200'
                      : isBlocking
                      ? 'bg-red-50 border-red-200'
                      : 'bg-gray-50 border-gray-200'
                  }`}
                >
                  {/* Checkbox/Status Icon */}
                  <div className="flex-shrink-0 mr-3 mt-0.5">
                    {completed ? (
                      <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center">
                        <svg
                          className="w-4 h-4 text-white"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path
                            fillRule="evenodd"
                            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                    ) : (
                      <div
                        className={`w-6 h-6 rounded-full border-2 ${
                          isBlocking
                            ? 'border-red-500 bg-red-100'
                            : 'border-gray-300 bg-white'
                        }`}
                      ></div>
                    )}
                  </div>

                  {/* Milestone Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div
                          className={`text-sm font-medium ${
                            completed ? 'text-green-900' : isBlocking ? 'text-red-900' : 'text-gray-900'
                          }`}
                        >
                          {milestone.label}
                          {isBlocking && (
                            <span className="ml-2 text-xs text-red-600 font-semibold">(Blocking)</span>
                          )}
                        </div>
                        {milestone.description && (
                          <div className="text-xs text-gray-600 mt-1">{milestone.description}</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Activities Section */}
      {stage.activities && stage.activities.length > 0 && (() => {
        // Filter activities to only show those that are enabled or have milestone-based blocking
        const activitiesWithStatus = stage.activities.map((activity) => {
          const enabled = isActivityEnabled(activity)
          const isReadinessBlocked =
            (activity.id === 'initiate_econsent' || activity.id === 'start_screening') &&
            !readiness.isReady

          const isDisabled = !enabled || isReadinessBlocked
          
          // Determine tooltip based on why it's disabled
          let tooltip = ''
          if (isReadinessBlocked) {
            tooltip = readiness.reason ?? ''
          } else if (!enabled) {
            // Check if disabled due to missing milestones
            const blockingMilestones = stage.milestones?.filter(m => m.blocking && !isMilestoneCompleted(m)) || []
            if (blockingMilestones.length > 0) {
              tooltip = `Complete required milestones: ${blockingMilestones.map(m => m.label).join(', ')}`
            } else {
              tooltip = activity.tooltip || 'This action is not yet available'
            }
          } else {
            tooltip = activity.tooltip || ''
          }

          return { activity, enabled, isReadinessBlocked, isDisabled, tooltip }
        })

        // Get blocking milestones for guidance
        const blockingMilestones = stage.milestones?.filter(m => m.blocking && !isMilestoneCompleted(m)) || []
        const hasBlockingMilestones = blockingMilestones.length > 0
        const hasReadinessBlock = !readiness.isReady && activitiesWithStatus.some(a => a.isReadinessBlocked)

        return (
          <div>
            <h4 className="text-base font-semibold text-gray-800 mb-4">Next Actions</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {activitiesWithStatus.map(({ activity, isDisabled, tooltip }) => {
                return (
                  <button
                    key={activity.id}
                    onClick={() => handleActivityClick(activity)}
                    disabled={isDisabled}
                    className={`p-4 rounded-lg border text-left transition-all ${
                      isDisabled
                        ? 'bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed'
                        : 'bg-blue-50 border-blue-200 text-blue-900 hover:bg-blue-100 hover:border-blue-300'
                    }`}
                    title={tooltip}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="text-sm font-medium">{activity.label}</div>
                        {activity.type === 'link' && (
                          <div className="text-xs text-gray-600 mt-1">Click to view</div>
                        )}
                        {isDisabled && tooltip && (
                          <div className="text-xs text-gray-500 mt-1">{tooltip}</div>
                        )}
                      </div>
                      {activity.type === 'link' && (
                        <svg
                          className="w-5 h-5 text-gray-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 5l7 7-7 7"
                          />
                        </svg>
                      )}
                      {isDisabled && (
                        <svg
                          className="w-5 h-5 text-gray-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                          />
                        </svg>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Show milestone-based guidance only if there are blocking milestones and no actions are available */}
            {hasBlockingMilestones && !hasReadinessBlock && activitiesWithStatus.every(a => a.isDisabled) && (
              <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-start">
                  <svg
                    className="w-5 h-5 text-blue-600 mr-2 flex-shrink-0 mt-0.5"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                      clipRule="evenodd"
                    />
                  </svg>
                  <div className="text-sm text-blue-800">
                    <div className="font-semibold">Complete required milestones to enable actions</div>
                    <div className="mt-1">
                      {blockingMilestones.map(m => m.label).join(', ')}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Show readiness warning only if specific actions are blocked */}
            {hasReadinessBlock && (
              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <div className="flex items-start">
                  <svg
                    className="w-5 h-5 text-yellow-600 mr-2 flex-shrink-0 mt-0.5"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                      clipRule="evenodd"
                    />
                  </svg>
                  <div className="text-sm text-yellow-800">
                    <div className="font-semibold">Action Restrictions</div>
                    <div className="mt-1">{readiness.reason}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}

export default ControlTowerMilestones

