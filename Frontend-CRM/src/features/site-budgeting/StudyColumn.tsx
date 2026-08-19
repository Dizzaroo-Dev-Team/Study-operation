import React, { useEffect, useState } from 'react'
import { createTemplate, fetchTemplatesForTrial } from './services/budgeting.api'
import type { BudgetTemplateRow } from './services/budgeting.api'
import { CostElementsList } from './CostElementsList'
import { FactorSelector } from './FactorSelector'
import { BudgetConfiguration } from './BudgetConfiguration'

type SubTab = 'elements' | 'factors' | 'configuration'

const SUB_TABS: { id: SubTab; label: string }[] = [
  { id: 'elements', label: 'Cost Master Elements' },
  { id: 'factors', label: 'Factors' },
  { id: 'configuration', label: 'Budget Configuration' },
]

type Props = {
  trialId: string
}

export const StudyColumn: React.FC<Props> = ({ trialId }) => {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('elements')
  const [template, setTemplate] = useState<BudgetTemplateRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const init = async () => {
      try {
        const templates = await fetchTemplatesForTrial(trialId)
        let trial = templates.find((t) => t.template_level === 'TRIAL' || (!t.country_code && !t.site_id))
        if (!trial) {
          const created = await createTemplate({
            trial_id: trialId,
            name: 'Study Budget',
            template_level: 'TRIAL',
            target_currency_code: 'USD',
          })
          trial = { ...(created as any) } as BudgetTemplateRow
        }
        if (!cancelled) setTemplate(trial)
      } catch {
        if (!cancelled) setError('Failed to load study template')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    init()
    return () => { cancelled = true }
  }, [trialId])

  if (loading) return (
    <div className="flex items-center gap-2 py-10 justify-center text-sm text-slate-500">
      <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
      </svg>
      Loading study budget…
    </div>
  )

  if (error) return <div className="p-6 text-sm text-red-500">{error}</div>
  if (!template) return <div className="p-6 text-sm text-slate-500">No template.</div>

  return (
    <div className="flex flex-col min-h-0">
      <div className="bg-white border-b border-slate-200 px-6 shrink-0">
        <div className="flex items-end gap-1 overflow-x-auto">
          {SUB_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveSubTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-all whitespace-nowrap ${
                activeSubTab === tab.id
                  ? 'border-blue-500 text-blue-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 p-6">
        {activeSubTab === 'elements' && (
          <CostElementsList studyId={trialId} />
        )}
        {activeSubTab === 'factors' && (
          <FactorSelector scope="TRIAL" trialId={trialId} />
        )}
        {activeSubTab === 'configuration' && (
          <BudgetConfiguration templateId={template.id} level="TRIAL" countryCode={null} trialId={trialId} />
        )}
      </div>
    </div>
  )
}
