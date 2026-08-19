import React, { useEffect, useState } from 'react'
import { useStudySite } from '../../contexts/StudySiteContext'
import StudyDetails from './tabs/StudyDetails'
import SiteSetup from './tabs/SiteSetup'
import StudyTeam from './tabs/StudyTeam'
import TemplateLibraryTab from './tabs/TemplateLibraryTab'
import AgreementsTab from './tabs/AgreementsTab'
import BudgetTab from './tabs/BudgetTab'
import { MvrTemplateStudio } from '../../components/mon/components/views/MvrTemplateStudio'
import { useToast, ToastContainer } from '../../components/mon/components/ui/Toast'
import globalStyles from '../../components/mon/styles/globalStyles'

type TabId =
  | 'study-details'
  | 'site-setup'
  | 'study-team'
  | 'template-library'
  | 'agreements'
  | 'budget'
  | 'mvr-template'

const TAB_PREFIX = 'study-setup:'

export const tabs: { id: TabId; label: string }[] = [
  { id: 'study-details', label: 'Study Details' },
  { id: 'site-setup', label: 'Site Setup' },
  { id: 'study-team', label: 'Users / Study Team' },
  { id: 'template-library', label: 'Template Library' },
  { id: 'agreements', label: 'Agreements' },
  { id: 'budget', label: 'Budget Builder' },
  { id: 'mvr-template', label: 'MVR Template' },
]

type Props = {
  apiBase?: string
}

const StudySetup: React.FC<Props> = ({ apiBase = '/api' }) => {
  const { lastTab, setLastTab } = useStudySite()
  const { toasts, showToast, removeToast } = useToast()

  const initial: TabId = (() => {
    if (lastTab && lastTab.startsWith(TAB_PREFIX)) {
      const id = lastTab.slice(TAB_PREFIX.length) as TabId
      if (tabs.some((t) => t.id === id)) return id
    }
    return 'study-details'
  })()

  const [activeTab, setActiveTab] = useState<TabId>(initial)
  const [mountedTabs, setMountedTabs] = useState<Set<TabId>>(new Set([initial]))

  const switchTab = (tab: TabId) => {
    setActiveTab(tab)
    setMountedTabs((prev) => new Set([...prev, tab]))
    setLastTab(`${TAB_PREFIX}${tab}`)
  }

  // React to `lastTab` changes so deep-links (e.g. the assistant's "open site
  // setup") switch the active tab even when Study Setup is already mounted —
  // the useState initializer above only runs on first mount.
  useEffect(() => {
    if (!lastTab || !lastTab.startsWith(TAB_PREFIX)) return
    const id = lastTab.slice(TAB_PREFIX.length) as TabId
    if (tabs.some((t) => t.id === id) && id !== activeTab) {
      setActiveTab(id)
      setMountedTabs((prev) => new Set([...prev, id]))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastTab])

  return (
    <>
    <div className="flex flex-col h-full bg-slate-50">
      <div className="bg-white border-b border-slate-200 px-6 shrink-0">
        <div className="flex items-end gap-0.5 pt-3 overflow-x-auto" data-testid="study-setup-tabs">
          {tabs.map((t) => {
            const active = activeTab === t.id
            return (
              <button
                key={t.id}
                data-testid={`study-setup-tab-${t.id}`}
                onClick={() => switchTab(t.id)}
                className={`px-5 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 -mb-px transition-colors whitespace-nowrap ${
                  active
                    ? 'border-blue-600 text-blue-700 bg-blue-50'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                }`}
              >
                {t.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {mountedTabs.has('study-details') && (
          <div style={{ display: activeTab === 'study-details' ? undefined : 'none' }}>
            <StudyDetails />
          </div>
        )}
        {mountedTabs.has('site-setup') && (
          <div style={{ display: activeTab === 'site-setup' ? undefined : 'none' }}>
            <SiteSetup />
          </div>
        )}
        {mountedTabs.has('study-team') && (
          <div style={{ display: activeTab === 'study-team' ? undefined : 'none' }}>
            <StudyTeam />
          </div>
        )}
        {mountedTabs.has('template-library') && (
          <div className="h-full min-h-0" style={{ display: activeTab === 'template-library' ? undefined : 'none' }}>
            <TemplateLibraryTab apiBase={apiBase} />
          </div>
        )}
        {mountedTabs.has('agreements') && (
          <div className="h-full min-h-0" style={{ display: activeTab === 'agreements' ? undefined : 'none' }}>
            <AgreementsTab apiBase={apiBase} />
          </div>
        )}
        {mountedTabs.has('budget') && (
          <div style={{ display: activeTab === 'budget' ? undefined : 'none' }}>
            <BudgetTab />
          </div>
        )}
        {mountedTabs.has('mvr-template') && (
          <div
            className="bg-white min-h-full"
            style={{ display: activeTab === 'mvr-template' ? undefined : 'none' }}
            data-testid="mvr-template-root"
          >
            <style dangerouslySetInnerHTML={{ __html: globalStyles }} />
            <div className="px-6 py-4 max-w-[1280px] mx-auto">
              <MvrTemplateStudio showToast={showToast} />
            </div>
          </div>
        )}
      </div>
    </div>
    <ToastContainer toasts={toasts} removeToast={removeToast} />
    </>
  )
}

export default StudySetup
