import React from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'
import { siteSelectValue, useWorkspaceContext } from '@/hooks/useWorkspaceContext'

interface GlobalSiteSelectorProps {
  /** navbar = top bar; drawer = mobile side menu; default = full-width form field */
  variant?: 'navbar' | 'drawer' | 'default'
  className?: string
}

/**
 * Global site picker — lives in the top navigation so the choice persists
 * across tab changes (Monitoring, Documents, Site Status, etc.).
 */
const GlobalSiteSelector: React.FC<GlobalSiteSelectorProps> = ({
  variant = 'navbar',
  className = '',
}) => {
  const {
    selectedStudyId,
    selectedSiteId,
    setSelectedSiteId,
    filteredSites,
    loading,
  } = useStudySite()
  const { contextLabel } = useWorkspaceContext()

  const disabled = !selectedStudyId || loading || filteredSites.length === 0

  const selectClass =
    variant === 'navbar'
      ? 'px-2 py-1.5 bg-white/15 hover:bg-white/25 text-white text-xs font-medium rounded-lg transition-all border border-white/30 focus:outline-none focus:ring-2 focus:ring-white/50 disabled:opacity-50 disabled:cursor-not-allowed w-[7.5rem] sm:w-[8.5rem] xl:w-[9.5rem] max-w-[9.5rem] appearance-none cursor-pointer truncate shrink-0'
      : variant === 'drawer'
        ? 'w-full px-3 py-2 rounded-lg bg-white/15 border border-white/30 text-white text-sm disabled:opacity-50 appearance-none cursor-pointer'
        : 'w-full px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-[#168AAD] focus:border-[#168AAD] disabled:bg-gray-50 disabled:cursor-not-allowed'

  const labelClass =
    variant === 'navbar'
      ? 'sr-only'
      : variant === 'drawer'
        ? 'block text-xs font-semibold text-white/80 uppercase tracking-wide'
        : 'text-xs font-medium text-gray-600'

  const onGradient = variant === 'navbar' || variant === 'drawer'

  return (
    <div
      className={`${
        variant === 'navbar' ? 'shrink-0' : 'flex flex-col gap-0.5 min-w-0'
      } ${className}`}
    >
      <span className={labelClass}>Site</span>
      <select
        value={selectedSiteId || ''}
        onChange={(e) => setSelectedSiteId(e.target.value || null)}
        disabled={disabled}
        className={selectClass}
        style={onGradient ? { color: 'white' } : undefined}
        title={contextLabel || 'Select site'}
        aria-label="Select site for workspace"
      >
        <option value="" style={onGradient ? { color: '#1f2937' } : undefined}>
          {!selectedStudyId
            ? 'Select study first'
            : filteredSites.length === 0
              ? 'No sites for study'
              : '— Select site —'}
        </option>
        {filteredSites.map((site) => {
          const value = siteSelectValue(site)
          return (
            <option
              key={site.id}
              value={value}
              style={onGradient ? { color: '#1f2937', backgroundColor: 'white' } : undefined}
            >
              {site.name || site.site_id}
            </option>
          )
        })}
      </select>
    </div>
  )
}

export default GlobalSiteSelector
