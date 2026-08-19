import { useMemo } from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'

/** Value stored in global site state and used in `<select>` options. */
export function siteSelectValue(site: { id: string; site_id: string }): string {
  return (site.site_id || site.id || '').trim()
}

/**
 * Read global study + site context for site-scoped tabs.
 *
 * @example
 * const { isReady, guard } = useWorkspaceContext()
 * if (!isReady) return guard({ title: 'Monitoring' })
 */
export function useWorkspaceContext() {
  const ctx = useStudySite()
  const {
    studies,
    sites,
    filteredSites,
    selectedStudyId,
    selectedSiteId,
  } = ctx

  const selectedStudy = useMemo(
    () => studies.find((s) => s.id === selectedStudyId) ?? null,
    [studies, selectedStudyId],
  )

  const selectedSite = useMemo(() => {
    if (!selectedSiteId) return null
    const pool = filteredSites.length > 0 ? filteredSites : sites
    return (
      pool.find((s) => s.id === selectedSiteId || s.site_id === selectedSiteId) ?? null
    )
  }, [filteredSites, sites, selectedSiteId])

  const missingStudy = !selectedStudyId
  const missingSite = Boolean(selectedStudyId && !selectedSiteId)

  const isReady = Boolean(selectedStudyId && selectedSiteId)

  /** e.g. "St John Hospital – MK-6482" */
  const contextLabel = useMemo(() => {
    if (!selectedSite) return ''
    const siteName = selectedSite.name?.trim() || selectedSite.site_id || 'Site'
    const studyName =
      selectedStudy?.name?.trim() ||
      selectedStudy?.study_id?.trim() ||
      ''
    return studyName ? `${siteName} – ${studyName}` : siteName
  }, [selectedSite, selectedStudy])

  return {
    ...ctx,
    selectedStudy,
    selectedSite,
    missingStudy,
    missingSite,
    isReady,
    contextLabel,
  }
}
