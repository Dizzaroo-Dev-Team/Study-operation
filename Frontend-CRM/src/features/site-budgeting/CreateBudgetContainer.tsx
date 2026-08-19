import React, { useState } from 'react'
import { StudyColumn } from './StudyColumn'
import { CountryColumn } from './CountryColumn'
import { SiteColumn } from './SiteColumn'

type MainTab = 'study' | 'country' | 'site'

type Props = {
  studyId: string
}

export const CreateBudgetContainer: React.FC<Props> = ({ studyId }) => {
  const [activeTab, setActiveTab] = useState<MainTab>('study')
  // Track which tabs have been visited so we only mount them once they're first shown,
  // then keep them alive (CSS hidden) so sub-tab state is preserved on return.
  const [mountedTabs, setMountedTabs] = useState<Set<MainTab>>(new Set(['study']))
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null)
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null)

  const switchTab = (tab: MainTab) => {
    setActiveTab(tab)
    setMountedTabs((prev) => new Set([...prev, tab]))
  }

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Main tab bar */}
      <div className="bg-white border-b border-slate-200 px-6 shrink-0">
        <div className="flex items-end gap-0.5 pt-3" data-testid="budget-level-tabs">
          <button
            data-testid="budget-tab-study"
            onClick={() => switchTab('study')}
            className={`px-6 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 -mb-px transition-colors ${
              activeTab === 'study'
                ? 'border-blue-600 text-blue-700 bg-blue-50'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            Study
          </button>

          <button
            data-testid="budget-tab-country"
            onClick={() => switchTab('country')}
            className={`px-6 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 -mb-px transition-colors flex items-center gap-2 ${
              activeTab === 'country'
                ? 'border-emerald-600 text-emerald-700 bg-emerald-50'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            Country
            {selectedCountry && (
              <span className="text-xs font-normal text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                {selectedCountry}
              </span>
            )}
          </button>

          <button
            data-testid="budget-tab-site"
            onClick={() => switchTab('site')}
            className={`px-6 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 -mb-px transition-colors ${
              activeTab === 'site'
                ? 'border-violet-600 text-violet-700 bg-violet-50'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            Site
          </button>
        </div>
      </div>

      {/* Tab content — lazy-mount then keep alive via CSS to preserve sub-tab state */}
      <div className="flex-1 overflow-y-auto">
        {mountedTabs.has('study') && (
          <div style={{ display: activeTab === 'study' ? undefined : 'none' }}>
            <StudyColumn trialId={studyId} />
          </div>
        )}
        {mountedTabs.has('country') && (
          <div style={{ display: activeTab === 'country' ? undefined : 'none' }}>
            <CountryColumn
              trialId={studyId}
              selectedCountry={selectedCountry}
              onCountryChange={(code) => {
                setSelectedCountry(code || null)
                setSelectedSiteId(null)
              }}
            />
          </div>
        )}
        {mountedTabs.has('site') && (
          <div style={{ display: activeTab === 'site' ? undefined : 'none' }}>
            <SiteColumn
              trialId={studyId}
              selectedCountry={selectedCountry}
              selectedSiteId={selectedSiteId}
              onSiteChange={(id) => setSelectedSiteId(id || null)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
