import React, { useMemo } from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'
import { useRoleAssignments } from '@/lib/queries/useUsers'
import { PrimarySiteStatus } from '@/features/sites/types/siteStatus'

interface SiteHeaderBannerProps {
  apiBase?: string
  currentStatus?: PrimarySiteStatus | null
}

interface SiteUser {
  user_id: string
  name?: string
  email?: string
  role: string
}

const formatPrimaryStatusLabel = (status?: PrimarySiteStatus | null): string => {
  if (!status) return 'Under Evaluation'
  switch (status) {
    case 'UNDER_EVALUATION':
      return 'Under Evaluation'
    case 'STARTUP':
      return 'Under Start-up'
    case 'INITIATING':
      return 'Initiating'
    case 'INITIATED_NOT_RECRUITING':
      return 'Initiated – Not Yet Recruiting'
    case 'RECRUITING':
      return 'Open for Recruitment'
    case 'ACTIVE_NOT_RECRUITING':
      return 'Active – Not Recruiting'
    case 'SUSPENDED':
      return 'Suspended'
    case 'TERMINATED':
      return 'Terminated'
    case 'WITHDRAWN':
      return 'Withdrawn'
    case 'COMPLETED':
      return 'Completed'
    case 'CLOSED':
      return 'Closed (Site Close-out Completed)'
    default:
      // Exhaustive above for known statuses; fall back for unexpected values.
      return String(status).replace(/_/g, ' ')
  }
}

const SiteHeaderBanner: React.FC<SiteHeaderBannerProps> = ({
  currentStatus
}) => {
  const { selectedStudyId, selectedSiteId, studies, filteredSites } = useStudySite()

  const selectedStudy = studies.find(s => s.id === selectedStudyId)
  const selectedSite = filteredSites.find(s => s.site_id === selectedSiteId || s.id === selectedSiteId)

  const roleAssignmentsQuery = useRoleAssignments(
    { site_id: selectedSite?.id ?? null },
    { enabled: Boolean(selectedSite?.id) },
  )
  const siteUsers: SiteUser[] = useMemo(() => {
    const assignments = roleAssignmentsQuery.data ?? []
    return assignments.map((assignment: any) => ({
      user_id: assignment.user_id,
      name: assignment.user?.name || assignment.user_name,
      email: assignment.user?.email || assignment.user_email,
      role: assignment.role,
    }))
  }, [roleAssignmentsQuery.data])

  if (!selectedStudyId || !selectedSiteId || !selectedStudy || !selectedSite) {
    return null
  }

  const craUsers = siteUsers.filter(u => u.role === 'CRA')
  const siteManagerUsers = siteUsers.filter(u => u.role === 'STUDY_MANAGER')

  return (
    <div className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10">
      <div className="px-6 py-3">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          {/* Left: Study and Site Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-base font-semibold text-gray-700 truncate">
                {selectedStudy.name}
              </span>
              <span className="text-gray-400 text-sm">→</span>
              <span className="text-base font-bold text-gray-900 truncate">
                {selectedSite.name}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-600">
              {selectedSite.country && (
                <span>
                  {selectedSite.country}
                  {selectedSite.city && <span>, {selectedSite.city}</span>}
                </span>
              )}
              {selectedSite.principal_investigator && (
                <span>
                  <span className="font-semibold">PI:</span> {selectedSite.principal_investigator}
                </span>
              )}
            </div>
          </div>

          {/* Right: Team and Status */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            {craUsers.length > 0 && (
              <span className="text-gray-700">
                <span className="font-semibold">CRA:</span>{' '}
                <span className="text-gray-900">
                  {craUsers.map(u => u.name || u.email || u.user_id).join(', ')}
                </span>
              </span>
            )}
            {siteManagerUsers.length > 0 && (
              <span className="text-gray-700">
                <span className="font-semibold">Site Manager:</span>{' '}
                <span className="text-gray-900">
                  {siteManagerUsers.map(u => u.name || u.email || u.user_id).join(', ')}
                </span>
              </span>
            )}
            {/* Current Status Badge */}
            <span className="ml-auto md:ml-0">
              <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-50 border border-blue-200">
                <span className="text-xs font-semibold text-blue-700 uppercase tracking-wide mr-2">
                  Status:
                </span>
                <span className="text-sm font-bold text-blue-900">
                  {formatPrimaryStatusLabel(currentStatus)}
                </span>
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SiteHeaderBanner
