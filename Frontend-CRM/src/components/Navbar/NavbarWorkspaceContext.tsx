import React from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'
import GlobalSiteSelector from '../workspace/GlobalSiteSelector'

type Layout = 'toolbar' | 'drawer'

interface NavbarWorkspaceContextProps {
  layout: Layout
}

/** Study + site selectors shared by the navbar toolbar and mobile drawer. */
const NavbarWorkspaceContext: React.FC<NavbarWorkspaceContextProps> = ({ layout }) => {
  const { selectedStudyId, setSelectedStudyId, studies, loading } = useStudySite()

  const studyClass =
    layout === 'drawer'
      ? 'w-full px-3 py-2 rounded-lg bg-white/15 border border-white/30 text-white text-sm disabled:opacity-50'
      : 'px-2 py-1.5 bg-white/15 hover:bg-white/25 text-white text-xs font-medium rounded-lg border border-white/30 focus:outline-none focus:ring-2 focus:ring-white/50 disabled:opacity-50 disabled:cursor-not-allowed w-[7.5rem] sm:w-[8.5rem] xl:w-[9.5rem] max-w-[9.5rem] appearance-none cursor-pointer truncate shrink-0'

  return (
    <>
      {layout === 'drawer' && (
        <label className="block text-xs font-semibold text-white/80 uppercase tracking-wide">
          Study
        </label>
      )}
      <select
        value={selectedStudyId || ''}
        onChange={(e) => setSelectedStudyId(e.target.value || null)}
        disabled={loading || studies.length === 0}
        className={studyClass}
        style={layout === 'toolbar' ? { color: 'white' } : undefined}
        aria-label="Select study"
        title="Select study"
      >
        {studies.map((study) => (
          <option
            key={study.id}
            value={study.id}
            style={layout === 'toolbar' ? { color: '#1f2937', backgroundColor: 'white' } : { color: '#1f2937' }}
          >
            {study.name}
          </option>
        ))}
      </select>
      <GlobalSiteSelector variant={layout === 'drawer' ? 'drawer' : 'navbar'} />
    </>
  )
}

export default NavbarWorkspaceContext
