import React, { useMemo, useState } from 'react'
import { SOAImport } from './SOAImport'
import { ElementsResolved } from './ElementsResolved'
import { VisitMatrix } from './VisitMatrix'
import { Milestones } from './Milestones'
import { NotesSection } from './NotesSection'
import { PolicyDocs } from './PolicyDocs'
import { PlannedEnrollment } from './PlannedEnrollment'
import { RollupBudget } from './RollupBudget'

type Section =
  | 'soa'
  | 'elements'
  | 'visits'
  | 'milestones'
  | 'notes'
  | 'simulation'
  | 'policy'
  | 'planned'
  | 'rollup'

type Props = {
  templateId: string
  level: 'TRIAL' | 'COUNTRY' | 'SITE'
  countryCode?: string | null
  trialId?: string
}

export const BudgetConfiguration: React.FC<Props> = ({ templateId, level, countryCode, trialId }) => {
  const TABS: { id: Section; label: string }[] = useMemo(
    () => (
      level === 'TRIAL'
        ? [
            { id: 'soa', label: 'SOA Import' },
            { id: 'elements', label: 'Elements' },
            { id: 'visits', label: 'Visit Matrix' },
            { id: 'milestones', label: 'Milestones' },
            { id: 'notes', label: 'Notes' },
            { id: 'simulation', label: 'Simulation' },
            { id: 'policy', label: 'Policy Docs' },
            { id: 'planned', label: 'Planned Enrollment' },
            { id: 'rollup', label: 'Rollup Budget' },
          ]
        : [
            { id: 'elements', label: 'Elements' },
            { id: 'visits', label: 'Visit Matrix' },
            { id: 'milestones', label: 'Milestones' },
            { id: 'notes', label: 'Notes' },
            { id: 'simulation', label: 'Simulation' },
          ]
    ),
    [level]
  )

  const [activeTab, setActiveTab] = useState<Section>(level === 'TRIAL' ? 'soa' : 'elements')
  const [refreshKey, setRefreshKey] = useState(0)

  const readOnly = level !== 'TRIAL'
  const handleChanged = () => setRefreshKey((k) => k + 1)

  return (
    <div className="flex flex-col min-h-0">
      {/* Pill-style inner tab bar */}
      <div className="flex border border-slate-200 bg-slate-50 rounded-lg overflow-x-auto shrink-0 p-1 gap-1 mb-4">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            data-testid={`budget-config-tab-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors rounded-md ${
              activeTab === tab.id
                ? 'bg-white text-indigo-700 shadow-sm border border-slate-200'
                : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="min-h-0">
        {activeTab === 'soa' && level === 'TRIAL' && (
          <SOAImport
            templateId={templateId}
            selectedStudyId={trialId ?? ''}
            onImported={handleChanged}
          />
        )}
        {activeTab === 'elements' && (
          <ElementsResolved
            key={refreshKey}
            templateId={templateId}
            level={level}
            countryCode={countryCode ?? null}
          />
        )}
        {activeTab === 'visits' && (
          <VisitMatrix
            templateId={templateId}
            onChanged={handleChanged}
            readOnly={readOnly}
            level={level}
            countryCode={countryCode ?? null}
          />
        )}
        {activeTab === 'milestones' && (
          <Milestones
            templateId={templateId}
            onChanged={handleChanged}
            readOnly={level === 'SITE'}
            level={level}
            countryCode={countryCode ?? null}
          />
        )}
        {activeTab === 'notes' && (
          <NotesSection templateId={templateId} readOnly={readOnly} />
        )}
        {activeTab === 'simulation' && (
          <div className="py-12 text-center text-sm text-slate-400 italic">
            Simulation placeholder — no changes required.
          </div>
        )}
        {activeTab === 'policy' && level === 'TRIAL' && trialId && (
          <PolicyDocs trialId={trialId} />
        )}
        {activeTab === 'planned' && level === 'TRIAL' && trialId && (
          <PlannedEnrollment trialId={trialId} />
        )}
        {activeTab === 'rollup' && level === 'TRIAL' && trialId && (
          <RollupBudget trialId={trialId} />
        )}
      </div>
    </div>
  )
}
