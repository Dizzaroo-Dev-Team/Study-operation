/**
 * Logistics query hook.
 *
 * Today's `/api/logistics` endpoint may be unavailable in some envs — the
 * legacy component swallowed errors and rendered the empty state. We
 * preserve that behavior by setting `retry: 0` and letting the consumer
 * treat `data ?? []` as the source of truth.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { SiteLogistics } from '@/types'

export interface LogisticsFilters {
  study_id?: string | null
  site_id?: string | null
}

export function useLogisticsList(
  filtersOrOptions?: LogisticsFilters | { enabled?: boolean },
  options?: { enabled?: boolean },
) {
  // Backwards-compatible: callers pre-Wave 4 passed `{ enabled }` directly as
  // the only argument. Detect that shape and remap to the new positional form.
  const isLegacyShape =
    filtersOrOptions != null &&
    Object.keys(filtersOrOptions).every((k) => k === 'enabled')
  const filters: LogisticsFilters = isLegacyShape ? {} : ((filtersOrOptions ?? {}) as LogisticsFilters)
  const opts = isLegacyShape ? (filtersOrOptions as { enabled?: boolean }) : options

  return useQuery<SiteLogistics[]>({
    queryKey: ['logistics', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = {}
      if (filters.study_id) params.study_id = filters.study_id
      if (filters.site_id) params.site_id = filters.site_id
      const res = await api.get<SiteLogistics[]>(
        '/logistics',
        Object.keys(params).length ? { params } : undefined,
      )
      return res.data ?? []
    },
    enabled: opts?.enabled ?? true,
    staleTime: 60_000,
    retry: 0,
  })
}
