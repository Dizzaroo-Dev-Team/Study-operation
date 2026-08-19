/**
 * Users query hooks.
 *
 * UserPicker and the user-directory views both fetch from `/users`; sharing
 * one cache means opening a picker right after viewing the directory is an
 * instant cache hit instead of another network round trip.
 *
 * Loose `User = any` typing for now — there's no canonical User type in
 * @/types yet beyond the AuthContext's shape, and the consumer types are
 * inconsistent. Follow-up: lift a canonical type and tighten this.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export type User = any

export interface UsersListFilters {
  site_id?: string | null
  limit?: number
  offset?: number
}

export function useUsersList(
  filters: UsersListFilters = {},
  options?: { enabled?: boolean },
) {
  return useQuery<User[]>({
    queryKey: ['users', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = {
        limit: filters.limit ?? 500,
        offset: filters.offset ?? 0,
      }
      if (filters.site_id) params.site_id = filters.site_id
      const res = await api.get<User[]>('/users', { params })
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    // Users change rarely — let the cache hold for 5 minutes.
    staleTime: 5 * 60_000,
  })
}

// -----------------------------------------------------------------------------
// Role assignments for a site
// -----------------------------------------------------------------------------
// Backs SiteHeaderBanner's CRA / Site Manager pillrow. Loose typing because
// the consumer maps assignments → users with its own local shape.
export type RoleAssignment = any

export function useRoleAssignments(
  filters: { site_id?: string | null; study_id?: string | null } = {},
  options?: { enabled?: boolean },
) {
  return useQuery<RoleAssignment[]>({
    queryKey: ['role-assignments', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = {}
      if (filters.site_id) params.site_id = filters.site_id
      if (filters.study_id) params.study_id = filters.study_id
      const res = await api.get<RoleAssignment[]>('/role-assignments', { params })
      return res.data ?? []
    },
    enabled:
      (Boolean(filters.site_id) || Boolean(filters.study_id)) &&
      (options?.enabled ?? true),
    staleTime: 60_000,
    retry: 0,
  })
}
