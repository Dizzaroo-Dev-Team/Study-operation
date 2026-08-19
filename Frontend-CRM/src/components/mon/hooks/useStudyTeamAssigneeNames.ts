import { useMemo } from 'react'
import { useStudyTeam } from '@/lib/queries/useStudies'
import { studyTeamRowsToAssigneeNames, studyTeamRowsToAssigneeOptions } from '../utils/studyTeamAssignees'

/**
 * IAM-backed study team names for the current study (same source as Study Setup → Users / Study Team).
 * Used for monitoring "Assign CRA" / "Assign To" dropdowns.
 */
export function useStudyTeamAssigneeNames(
  studyId: string | null | undefined,
  opts?: { onlyCra?: boolean },
) {
  const enabled = Boolean(studyId)
  const q = useStudyTeam(studyId ?? undefined, { enabled })
  const names = useMemo(() => studyTeamRowsToAssigneeNames(q.data?.data, opts), [q.data, opts?.onlyCra])
  const options = useMemo(() => studyTeamRowsToAssigneeOptions(q.data?.data, opts), [q.data, opts?.onlyCra])
  return {
    names,
    options,
    /** True while the first fetch for this studyId is in flight. */
    isPending: enabled && q.isPending,
    isError: q.isError,
  }
}
