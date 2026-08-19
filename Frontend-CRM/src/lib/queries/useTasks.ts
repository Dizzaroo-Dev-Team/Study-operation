/**
 * Tasks query hooks.
 *
 * Replaces hand-rolled `useState + useEffect + api.get('/tasks')` blocks in
 * CommandPalette, WorkspaceHome, etc. Two consumers mounting in the same
 * tick with the same filters share one in-flight request and one cache.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { MonitoringTask, TaskStatus } from '@/types'

export interface TasksListFilters {
  siteId?: string | null
  sponsorId?: string | null
  role?: string | null
  status?: TaskStatus | 'all' | null
  limit?: number
  offset?: number
}

export function useTasksList(
  filters: TasksListFilters = {},
  options?: { enabled?: boolean },
) {
  return useQuery<MonitoringTask[]>({
    queryKey: ['tasks', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = {}
      if (filters.siteId) params.siteId = filters.siteId
      if (filters.sponsorId) params.sponsorId = filters.sponsorId
      if (filters.role) params.role = filters.role
      if (filters.status && filters.status !== 'all') params.status = filters.status
      if (filters.limit) params.limit = filters.limit
      if (filters.offset) params.offset = filters.offset
      const res = await api.get<MonitoringTask[]>('/tasks', { params })
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    // Tasks change on user action (status updates, new assignments). A short
    // staleTime lets quick re-mounts share the cache without serving truly
    // stale data; explicit invalidation drives freshness after mutations.
    staleTime: 15_000,
  })
}

export function useDeleteTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (taskId: string) => {
      await api.delete(`/tasks/${taskId}`)
      return taskId
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}

export function useUpdateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { taskId: string; updates: Record<string, any> }) => {
      const res = await api.put(`/tasks/${payload.taskId}`, payload.updates)
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}
