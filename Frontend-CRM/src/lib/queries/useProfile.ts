/**
 * Profile-domain query hooks.
 *
 * Backs the Profile view, which switches between the current authenticated
 * user (no `userId` → /profile/...) and an arbitrary user lookup
 * (`userId` → /users/{id}/...). Each tab loads its own slice, so they're
 * exposed as independent hooks rather than one mega-query.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export type ProfileSlice = 'profile' | 'rd-studies' | 'iis-studies' | 'events'

function pathFor(slice: ProfileSlice, userId?: string | null): string {
  const tail =
    slice === 'profile'
      ? 'profile'
      : slice === 'rd-studies'
        ? 'rd-studies'
        : slice === 'iis-studies'
          ? 'iis-studies'
          : 'events'
  if (userId) {
    // /users/{id}/profile, /users/{id}/rd-studies, etc.
    return `/users/${userId}/${tail === 'profile' ? 'profile' : tail}`
  }
  // /profile, /profile/rd-studies, /profile/iis-studies, /profile/events
  return tail === 'profile' ? '/profile' : `/profile/${tail}`
}

export function useUserProfile(
  userId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<any>({
    queryKey: ['profile', userId ?? 'self'],
    queryFn: async () => {
      const res = await api.get(pathFor('profile', userId ?? null))
      return res.data
    },
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
    retry: 0,
  })
}

export function useUserRdStudies(
  userId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<any[]>({
    queryKey: ['profile', userId ?? 'self', 'rd-studies'],
    queryFn: async () => {
      const res = await api.get<any[]>(pathFor('rd-studies', userId ?? null))
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
    retry: 0,
  })
}

export function useUserIisStudies(
  userId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<any[]>({
    queryKey: ['profile', userId ?? 'self', 'iis-studies'],
    queryFn: async () => {
      const res = await api.get<any[]>(pathFor('iis-studies', userId ?? null))
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
    retry: 0,
  })
}

export function useUserEvents(
  userId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<any[]>({
    queryKey: ['profile', userId ?? 'self', 'events'],
    queryFn: async () => {
      const res = await api.get<any[]>(pathFor('events', userId ?? null))
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
    retry: 0,
  })
}

export interface ResearchPaper {
  title: string
  link: string
  snippet: string
  source?: string
  relatedStudy?: string | null
}

export function useUserPublicInfo(
  userId: string | null | undefined,
  searchQuery: string,
  options?: { enabled?: boolean },
) {
  return useQuery<ResearchPaper[]>({
    queryKey: ['profile', userId ?? 'self', 'public-info', searchQuery],
    queryFn: async () => {
      const path = userId
        ? `/users/${userId}/public-info`
        : '/profile/public-info'
      const params: Record<string, unknown> = { num_results: 10 }
      // Public-info-by-id ignores the query string (backend already knows
      // the user); for /profile/public-info we still pass the derived terms.
      if (!userId) params.query = searchQuery
      const res = await api.get<ResearchPaper[]>(path, { params })
      const rows = res.data ?? []
      return rows.map((paper) => ({ ...paper, relatedStudy: null }))
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60_000,
    retry: 0,
  })
}
