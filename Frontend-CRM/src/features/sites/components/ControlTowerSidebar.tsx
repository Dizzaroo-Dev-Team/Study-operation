import React from 'react'
import { ControlStage, ControlTowerStage } from '@/features/sites/types/siteStatus'
import { getStagesInOrder } from '@/features/sites/config/controlTowerConfig'

interface ControlTowerSidebarProps {
  currentStage: ControlStage
  stages: ControlTowerStage[]
  onStageSelect: (stageId: ControlStage) => void
  isOnHold: boolean
  completedStages: ControlStage[]
}

const ControlTowerSidebar: React.FC<ControlTowerSidebarProps> = ({
  currentStage,
  onStageSelect,
  isOnHold,
  completedStages,
}) => {
  const orderedStages = getStagesInOrder()

  const getStageStatus = (stage: ControlTowerStage): 'completed' | 'current' | 'future' => {
    if (completedStages.includes(stage.id)) {
      return 'completed'
    }
    if (stage.id === currentStage || (isOnHold && stage.id === 'on_hold')) {
      return 'current'
    }
    return 'future'
  }

  const getStageClassName = (stage: ControlTowerStage): string => {
    const status = getStageStatus(stage)
    const baseClasses =
      'w-full text-left px-4 py-3 mb-2 rounded-lg transition-all cursor-pointer border-l-4'
    
    switch (status) {
      case 'completed':
        return `${baseClasses} bg-green-50 border-green-500 text-green-900 hover:bg-green-100`
      case 'current':
        return `${baseClasses} bg-blue-50 border-blue-600 text-blue-900 font-semibold hover:bg-blue-100`
      case 'future':
        return `${baseClasses} bg-gray-50 border-gray-300 text-gray-500 hover:bg-gray-100`
      default:
        return baseClasses
    }
  }

  return (
    <div className="w-64 bg-white border-r border-gray-200 h-full overflow-y-auto">
      <div className="p-4 border-b border-gray-200 bg-gradient-to-r from-dizzaroo-deep-blue to-dizzaroo-blue-green">
        <h2 className="text-lg font-bold text-white">Activation Stages</h2>
        <p className="text-xs text-white/80 mt-1">Site activation workflow</p>
      </div>

      <div className="p-2">
        {orderedStages.map((stage) => {
          const status = getStageStatus(stage)
          const isSelected = stage.id === currentStage

          return (
            <div key={stage.id} className="relative">
              <button
                onClick={() => onStageSelect(stage.id)}
                className={getStageClassName(stage)}
                type="button"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="text-sm font-medium">{stage.label}</div>
                    {stage.description && (
                      <div className="text-xs mt-1 opacity-75 line-clamp-2">
                        {stage.description}
                      </div>
                    )}
                  </div>
                  {status === 'completed' && (
                    <div className="ml-2 flex-shrink-0">
                      <svg
                        className="w-5 h-5 text-green-600"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </div>
                  )}
                  {isSelected && status === 'current' && (
                    <div className="ml-2 flex-shrink-0">
                      <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
                    </div>
                  )}
                </div>
              </button>
            </div>
          )
        })}

        {/* On Hold Badge Overlay */}
        {isOnHold && (
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
            <div className="flex items-center">
              <svg
                className="w-5 h-5 text-yellow-600 mr-2"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <div className="text-sm font-semibold text-yellow-800">On Hold</div>
                <div className="text-xs text-yellow-700">Site activities are paused</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default ControlTowerSidebar

