/**
 * Visual-only horizontal progress stepper for the agreement lifecycle.
 * Stage detection stays in agreementWorkflow (getAgreementStage); this component only renders.
 */

import React from 'react'
import type { AgreementStage } from '@/features/agreements/services/agreementWorkflow'
import { getStageLabel } from '@/features/agreements/services/agreementWorkflow'

const STEPS: AgreementStage[] = ['PREPARATION', 'REVIEW', 'SIGNATURE', 'COMPLETED']

export interface AgreementWorkflowStepperProps {
  /** Conceptual stage from getAgreementStage(agreement.status) — no backend values changed here */
  currentStage: AgreementStage
  className?: string
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden
    >
      <path
        fillRule="evenodd"
        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
        clipRule="evenodd"
      />
    </svg>
  )
}

export const AgreementWorkflowStepper: React.FC<AgreementWorkflowStepperProps> = ({
  currentStage,
  className = '',
}) => {
  const currentIndex = STEPS.indexOf(currentStage)
  const safeIndex = currentIndex >= 0 ? currentIndex : 0
  const total = STEPS.length
  const progressPct =
    total > 1 ? (safeIndex / (total - 1)) * 100 : 0

  const currentStageLabel = getStageLabel(currentStage)

  return (
    <div
      className={`w-full ${className}`}
      role="group"
      aria-label={`Agreement workflow progress, step ${safeIndex + 1} of ${total}: ${currentStageLabel}`}
    >
      <div className="relative px-1 sm:px-2">
        {/* Track: spans between first and last step centers (≈75% width, inset 12.5%) */}
        <div
          className="pointer-events-none absolute left-[12.5%] top-[0.875rem] z-0 h-1 w-[75%] -translate-y-1/2 rounded-full bg-gray-200"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute left-[12.5%] top-[0.875rem] z-0 h-1 max-w-[75%] -translate-y-1/2 rounded-full bg-gradient-to-r from-emerald-500 to-emerald-600 transition-[width] duration-500 ease-out"
          style={{ width: `${(progressPct / 100) * 75}%` }}
          aria-hidden
        />

        <div className="relative z-10 flex w-full justify-between">
          {STEPS.map((stage, index) => {
            const isCompleted = index < safeIndex
            const isCurrent = index === safeIndex
            const label = getStageLabel(stage).replace(/^Agreement /, '')

            const circleBase =
              'flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold transition-all duration-300 sm:h-8 sm:w-8 sm:text-sm'

            let circleClass = circleBase
            if (isCompleted) {
              circleClass += ' border-emerald-600 bg-emerald-600 text-white shadow-sm'
            } else if (isCurrent) {
              circleClass +=
                ' scale-110 border-blue-600 bg-blue-600 text-white shadow-md ring-2 ring-blue-300 ring-offset-2 ring-offset-gray-50'
            } else {
              circleClass += ' border-gray-300 bg-white text-gray-400'
            }

            let labelClass =
              'mt-2 max-w-[5.5rem] text-center text-[10px] leading-tight sm:max-w-none sm:text-xs '
            if (isCompleted) {
              labelClass += 'font-semibold text-gray-900'
            } else if (isCurrent) {
              labelClass += 'font-bold text-gray-900'
            } else {
              labelClass += 'font-medium text-gray-400'
            }

            return (
              <div
                key={stage}
                className="flex flex-1 flex-col items-center"
              >
                <div className={circleClass}>
                  {isCompleted ? (
                    <CheckIcon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </div>
                <span className={labelClass}>{label}</span>
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-3 text-xs text-gray-500">
        Current stage:{' '}
        <span className="font-semibold text-gray-800">{currentStageLabel}</span>
      </div>
    </div>
  )
}

export default AgreementWorkflowStepper
