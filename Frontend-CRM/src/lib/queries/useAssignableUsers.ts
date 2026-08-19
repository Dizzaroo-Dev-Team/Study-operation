import { useMemo } from 'react'
import type { AppUser } from '@/features/operations/components/TaskFormModal'
import { useStudyTeam } from '@/lib/queries/useStudies'
import {
  mergeAssigneeUsers,
  studyTeamRowsToAppUsers,
} from '@/lib/users/assignableUsers'

/**
 * IAM study-team roster for assignee dropdowns (Tasks, monitoring, etc.).
 * Only users on the study team for the selected study are listed.
 */
export function useAssignableUsers(
  studyId: string | null | undefined,
  options?: {
    enabled?: boolean
    /** Keep a currently-assigned user visible even if off the study team. */
    includeUserIds?: string[]
    extraUsers?: AppUser[]
  },
) {
  const enabled = options?.enabled ?? Boolean(studyId)
  const studyTeamQuery = useStudyTeam(studyId ?? undefined, { enabled })

  const users = useMemo(() => {
    const fromStudyTeam = studyTeamRowsToAppUsers(studyTeamQuery.data?.data)
    const includeIds = new Set(options?.includeUserIds?.filter(Boolean) ?? [])
    const extras = (options?.extraUsers ?? []).filter((u) => u?.user_id && includeIds.has(u.user_id))
    return mergeAssigneeUsers(fromStudyTeam, extras)
  }, [studyTeamQuery.data?.data, options?.includeUserIds, options?.extraUsers])

  return {
    users,
    isPending: enabled && studyTeamQuery.isPending,
    isError: studyTeamQuery.isError,
  }
}
