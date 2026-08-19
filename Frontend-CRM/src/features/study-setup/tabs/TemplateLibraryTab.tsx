import React, { useEffect, useState } from 'react'
import StudyTemplateLibrary from '@/components/StudyTemplateLibrary'
import ClauseLibraryManager from '@/features/agreements/components/ClauseLibraryManager'
import { useStudySite } from '@/contexts/StudySiteContext'

type Props = {
  apiBase?: string
}

type SubTab = 'templates' | 'clauses'

const SUBTAB_PREFIX = 'template-library:'

const TemplateLibraryTab: React.FC<Props> = ({ apiBase = '/api' }) => {
  const { lastSubTab, setLastSubTab } = useStudySite()

  // Deep-link support: activate the sub-tab named in lastSubTab (e.g. the
  // assistant's "open clause library" sets 'template-library:clauses'). Read on
  // mount (initializer) and react to later changes (effect).
  const initialSub: SubTab = (() => {
    if (lastSubTab && lastSubTab.startsWith(SUBTAB_PREFIX)) {
      const id = lastSubTab.slice(SUBTAB_PREFIX.length)
      if (id === 'templates' || id === 'clauses') return id
    }
    return 'templates'
  })()
  const [subTab, setSubTab] = useState<SubTab>(initialSub)

  useEffect(() => {
    if (!lastSubTab || !lastSubTab.startsWith(SUBTAB_PREFIX)) return
    const id = lastSubTab.slice(SUBTAB_PREFIX.length)
    if ((id === 'templates' || id === 'clauses') && id !== subTab) setSubTab(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastSubTab])

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Sub-tab bar */}
      <div className="flex shrink-0 border-b border-gray-200 bg-white px-6" data-testid="template-library-subtabs">
        {([
          { key: 'templates', label: 'Templates' },
          { key: 'clauses',   label: 'Clause Library' },
        ] as { key: SubTab; label: string }[]).map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setSubTab(key)
              setLastSubTab(`${SUBTAB_PREFIX}${key}`)
            }}
            className={[
              'px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px',
              subTab === key
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {subTab === 'templates' ? (
          <StudyTemplateLibrary apiBase={apiBase} />
        ) : (
          <ClauseLibraryManager />
        )}
      </div>
    </div>
  )
}

export default TemplateLibraryTab
