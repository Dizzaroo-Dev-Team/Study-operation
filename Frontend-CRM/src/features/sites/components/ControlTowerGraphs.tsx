import React, { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { StageProgress, StudyStatusSummary, ControlTowerStage } from '@/features/sites/types/siteStatus'
import { getStageOrder } from '@/features/sites/services/controlTowerMapping'
import { getStagesInOrder } from '@/features/sites/config/controlTowerConfig'

interface StageProgressTimelineProps {
  progress: StageProgress
  stages: ControlTowerStage[]
}

/**
 * Stage Progress Timeline - Horizontal progress bar showing current stage
 */
export const StageProgressTimeline: React.FC<StageProgressTimelineProps> = ({ progress, stages }) => {
  const orderedStages = getStagesInOrder()
  const currentOrder = getStageOrder(progress.currentStage)

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Stage Progress Timeline</h3>
      <div className="relative">
        {/* Progress bar container */}
        <div className="flex items-center space-x-2">
          {orderedStages.map((stage, index) => {
            const stageOrder = getStageOrder(stage.id)
            const isCompleted = progress.completedStages.includes(stage.id)
            const isCurrent = stage.id === progress.currentStage
            const isFuture = stageOrder > currentOrder

            return (
              <div key={stage.id} className="flex-1 relative">
                {/* Stage segment */}
                <div
                  className={`h-8 rounded-lg flex items-center justify-center text-xs font-medium transition-all ${
                    isCompleted
                      ? 'bg-green-500 text-white'
                      : isCurrent
                      ? 'bg-blue-500 text-white ring-2 ring-blue-300 ring-offset-2'
                      : isFuture
                      ? 'bg-gray-200 text-gray-500'
                      : 'bg-gray-300 text-gray-600'
                  }`}
                  title={stage.label}
                >
                  <span className="truncate px-1">{index + 1}</span>
                </div>
                {/* Stage label */}
                <div className="mt-2 text-xs text-center text-gray-600 truncate" title={stage.label}>
                  {stage.label.split(' ')[0]}
                </div>
              </div>
            )
          })}
        </div>

        {/* Current stage indicator */}
        {progress.currentStage !== 'on_hold' && (
          <div className="mt-4 text-sm text-gray-700">
            <span className="font-semibold">Current Stage:</span>{' '}
            {stages.find((s) => s.id === progress.currentStage)?.label || progress.currentStage}
          </div>
        )}
      </div>
    </div>
  )
}

interface MilestoneCompletionGraphProps {
  stage: ControlTowerStage
  metadata: Record<string, any> | null
}

/**
 * Milestone Completion Graph - Shows progress of milestones for current stage
 */
export const MilestoneCompletionGraph: React.FC<MilestoneCompletionGraphProps> = ({ stage, metadata }) => {
  const milestoneData = useMemo(() => {
    if (!stage.milestones || stage.milestones.length === 0) {
      return { completed: 0, total: 0 }
    }

    const completed = stage.milestones.filter((m) => m.completionRule(metadata)).length
    const total = stage.milestones.length

    return { completed, total }
  }, [stage.milestones, metadata])

  // Simplified progress indicator - just show count, no charts
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 mb-4">
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600">Milestones completed:</span>
        <span className="font-semibold text-gray-900">
          {milestoneData.completed} of {milestoneData.total}
        </span>
      </div>
    </div>
  )
}

interface PortfolioSummaryGraphProps {
  summary: StudyStatusSummary | null
  stages: ControlTowerStage[]
}

/**
 * Portfolio Summary Graph - Shows sites by Control Stage (study-level view)
 */
export const PortfolioSummaryGraph: React.FC<PortfolioSummaryGraphProps> = ({ summary, stages }) => {
  const chartData = useMemo(() => {
    if (!summary) return []

    const orderedStages = getStagesInOrder()
    const stageLabelMap: Record<string, string> = {
      UNDER_EVALUATION: 'under_consideration',
      STARTUP: 'startup_site_selection',
      INITIATING: 'enrollment_initiation',
      INITIATED_NOT_RECRUITING: 'initiated_post_siv',
      RECRUITING: 'open_for_recruitment',
      ACTIVE_NOT_RECRUITING: 'active_not_recruiting',
      CLOSED: 'closed_final',
      COMPLETED: 'closed_final',
    }

    return orderedStages.map((stage) => {
      // Aggregate counts for this stage
      let count = 0
      Object.entries(summary.status_counts).forEach(([rawStatus, statusCount]) => {
        const mappedStage = stageLabelMap[rawStatus]
        if (mappedStage === stage.id) {
          count += statusCount
        }
      })

      return {
        stage: stage.label,
        sites: count,
      }
    })
  }, [summary, stages])

  if (!summary) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Portfolio Summary</h3>
        <div className="text-sm text-gray-500">No study data available</div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Portfolio Summary</h3>
      <p className="text-sm text-gray-600 mb-4">
        Sites by Control Tower Stage (Study: {summary.study_name})
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="stage"
            angle={-45}
            textAnchor="end"
            height={100}
            tick={{ fontSize: 12 }}
          />
          <YAxis />
          <Tooltip />
          <Legend />
          <Bar dataKey="sites" fill="#3b82f6" name="Number of Sites" />
        </BarChart>
      </ResponsiveContainer>

      {/* Summary stats */}
      <div className="mt-4 grid grid-cols-3 gap-4 pt-4 border-t border-gray-200">
        <div>
          <div className="text-2xl font-bold text-gray-900">{summary.total_sites}</div>
          <div className="text-xs text-gray-600">Total Sites</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-green-600">{summary.recruiting_sites}</div>
          <div className="text-xs text-gray-600">Recruiting Sites</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-blue-600">
            {chartData.find((d) => d.stage.includes('Recruitment'))?.sites || 0}
          </div>
          <div className="text-xs text-gray-600">Open for Recruitment</div>
        </div>
      </div>
    </div>
  )
}

/**
 * Combined graphs component
 */
interface ControlTowerGraphsProps {
  progress: StageProgress
  currentStage: ControlTowerStage | undefined
  metadata: Record<string, any> | null
  summary: StudyStatusSummary | null
  stages: ControlTowerStage[]
  showPortfolio?: boolean
}

const ControlTowerGraphs: React.FC<ControlTowerGraphsProps> = ({
  currentStage,
  metadata,
}) => {
  return (
    <div className="space-y-6">
      {currentStage && (
        <MilestoneCompletionGraph stage={currentStage} metadata={metadata} />
      )}
    </div>
  )
}

export default ControlTowerGraphs

