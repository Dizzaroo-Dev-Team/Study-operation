/**
 * Site Profile query hooks.
 *
 * Backs SiteProfileTab. The GET endpoint returns 404 when no profile has
 * been created yet — the hook normalises that into a `null` data value so
 * consumers don't have to treat 404 as an error.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface SiteProfile {
  id: string
  site_id: string
  site_name?: string
  hospital_name?: string
  pi_name?: string
  pi_email?: string
  pi_phone?: string
  primary_contracting_entity?: string
  authorized_signatory_name?: string
  authorized_signatory_email?: string
  authorized_signatory_title?: string
  address_line_1?: string
  city?: string
  state?: string
  country?: string
  postal_code?: string
  site_coordinator_name?: string
  site_coordinator_email?: string
  site_coordinator_phone?: string
  site_head_name?: string
  site_head_email?: string
  site_head_phone?: string
  pi_designation?: string
  pi_department?: string
  sub_investigator_name?: string
  sub_investigator_email?: string
  sub_investigator_phone?: string
  sub_investigator_designation?: string
  sub_investigator_department?: string
  created_at?: string
  updated_at?: string
}

export function useSiteProfile(siteId: string | null | undefined) {
  return useQuery<SiteProfile | null>({
    queryKey: ['site-profile', siteId],
    queryFn: async () => {
      try {
        const res = await api.get<SiteProfile>(`/sites/${siteId}/profile`)
        return res.data ?? null
      } catch (err: any) {
        // 404 = profile not yet created for this site; render empty form.
        if (err?.response?.status === 404) return null
        throw err
      }
    },
    enabled: Boolean(siteId),
    staleTime: 60_000,
    retry: 0,
  })
}

export function useUpsertSiteProfile(siteId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation<SiteProfile, unknown, { payload: Partial<SiteProfile>; isUpdate: boolean }>({
    mutationFn: async ({ payload, isUpdate }) => {
      const path = `/sites/${siteId}/profile`
      const res = isUpdate
        ? await api.put<SiteProfile>(path, payload)
        : await api.post<SiteProfile>(path, payload)
      return res.data
    },
    onSuccess: (data) => {
      qc.setQueryData(['site-profile', siteId], data)
    },
  })
}
