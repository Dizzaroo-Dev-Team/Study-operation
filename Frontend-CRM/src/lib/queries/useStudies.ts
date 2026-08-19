/**
 * Studies + sites query hooks.
 *
 * These replace the hand-rolled `useEffect + useState` fetchers that
 * StudySiteContext and several feature components currently use to load the
 * roster of studies and sites the active user can see.
 *
 * Migration recipe — to convert a component that does:
 *
 *     const [studies, setStudies] = useState([])
 *     const [loading, setLoading] = useState(true)
 *     useEffect(() => {
 *       api.get('/studies').then(r => setStudies(r.data)).finally(() => setLoading(false))
 *     }, [])
 *
 * Replace with:
 *
 *     const { data: studies = [], isLoading } = useStudies()
 *
 * The cache is shared across the app, so the next component that mounts and
 * calls `useStudies()` is an instant cache hit instead of another network
 * round-trip.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryClient'

export interface Study {
  id: string
  study_id: string
  name: string
  description?: string
  status?: string
}

export interface Site {
  id: string
  site_id: string
  study_id: string
  name: string
  code?: string
  location?: string
  principal_investigator?: string
  address?: string
  city?: string
  country?: string
  status?: string
}

export function useStudies(options?: { enabled?: boolean }) {
  return useQuery<Study[]>({
    queryKey: QK.studies(),
    queryFn: async () => {
      const res = await api.get<Study[]>('/studies')
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    // Studies change rarely — bump staleTime so the navbar dropdown doesn't
    // re-fetch on every route change.
    staleTime: 5 * 60_000,
  })
}

// -----------------------------------------------------------------------------
// Study team (IAM-sourced users with access to a study)
// -----------------------------------------------------------------------------
// Backs the Study Setup → Users / Study Team tab. Loose row typing — the
// consumer defines a tighter shape locally.
export type StudyTeamRow = any

export interface StudyTeamResponse {
  data: StudyTeamRow[]
  total: number
  study_id: string | null
  app_key: string | null
}

export function useStudyTeam(
  studyId: string | null | undefined,
  options?: { scopeAll?: boolean; enabled?: boolean },
) {
  const scopeAll = options?.scopeAll ?? false
  return useQuery<StudyTeamResponse>({
    queryKey: ['study-team', scopeAll ? null : (studyId ?? null)],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (!scopeAll && studyId) params.study_id = studyId
      const res = await api.get<StudyTeamResponse>('/study-team', { params })
      return res.data
    },
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
  })
}

// -----------------------------------------------------------------------------
// Per-site workflow steps (Under Consideration stage)
// -----------------------------------------------------------------------------
// Backs ControlTowerMilestones polling. The legacy 3-second `setInterval`
// becomes `refetchInterval: 3_000`; React Query pauses polling when the
// browser tab is hidden, which the manual interval did not.
export interface WorkflowStep {
  step_name: string
  status: string
  step_data: Record<string, any>
}

export function useSiteWorkflowSteps(
  siteId: string | null | undefined,
  studyId: string | null | undefined,
  options?: { enabled?: boolean; refetchInterval?: number | false },
) {
  return useQuery<WorkflowStep[] | null>({
    queryKey: ['site-workflow-steps', siteId, studyId],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (studyId) params.study_id = studyId
      const res = await api.get<{ steps?: WorkflowStep[] }>(
        `/sites/${siteId}/workflow/steps`,
        { params },
      )
      return res.data?.steps ?? []
    },
    enabled: Boolean(siteId) && (options?.enabled ?? true),
    refetchInterval: options?.refetchInterval ?? 3_000,
    refetchIntervalInBackground: false,
    staleTime: 1_500,
    retry: 0,
  })
}

export function useSites(studyId: string | null | undefined) {
  return useQuery<Site[]>({
    queryKey: QK.sites(studyId),
    queryFn: async () => {
      if (!studyId) return []
      const res = await api.get<Site[]>('/sites', {
        params: { study_id: studyId },
      })
      return res.data ?? []
    },
    enabled: Boolean(studyId),
    // Sites change more often than studies (status updates, IRB events),
    // but still rarely enough that a 60s staleTime is comfortable.
    staleTime: 60_000,
  })
}
