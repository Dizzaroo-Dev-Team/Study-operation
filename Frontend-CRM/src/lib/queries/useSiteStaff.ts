import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface SiteStaffMember {
  id: string
  site_id: string
  staff_id: string
  staff_name: string
  study_role: string
  email?: string | null
  phone?: string | null
  start_date?: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface StaffCreate {
  staff_name: string
  study_role: string
  email?: string
  phone?: string
  start_date?: string
  status?: string
}

export interface StaffUpdate {
  staff_name?: string
  study_role?: string
  email?: string
  phone?: string
  start_date?: string
  status?: string
}

const key = (siteId: string | null | undefined) => ['site-staff', siteId]

export function useSiteStaff(siteId: string | null | undefined) {
  return useQuery<SiteStaffMember[]>({
    queryKey: key(siteId),
    queryFn: async () => {
      const res = await api.get<SiteStaffMember[]>(`/sites/${siteId}/staff`)
      return res.data ?? []
    },
    enabled: Boolean(siteId),
    staleTime: 30_000,
    retry: (count, err: any) => err?.response?.status !== 404 && count < 2,
  })
}

export function useCreateSiteStaff(siteId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation<SiteStaffMember, unknown, StaffCreate>({
    mutationFn: async (payload) => {
      const res = await api.post<SiteStaffMember>(`/sites/${siteId}/staff`, payload)
      return res.data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(siteId) }),
  })
}

export function useUpdateSiteStaff(siteId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation<SiteStaffMember, unknown, { staffRowId: string; updates: StaffUpdate }>({
    mutationFn: async ({ staffRowId, updates }) => {
      const res = await api.patch<SiteStaffMember>(`/sites/${siteId}/staff/${staffRowId}`, updates)
      return res.data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(siteId) }),
  })
}

export function useDeleteSiteStaff(siteId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation<void, unknown, string>({
    mutationFn: async (staffRowId) => {
      await api.delete(`/sites/${siteId}/staff/${staffRowId}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(siteId) }),
  })
}
