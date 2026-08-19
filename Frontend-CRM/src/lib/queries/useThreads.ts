/**
 * Threads query / mutation hooks.
 *
 * Mirrors `useConversations.ts` shape so consumers see a consistent API.
 *
 * Today the hottest paths are:
 *   * UnifiedInbox listing the threads sidebar
 *   * ThreadDetail loading a single thread + its messages
 *   * Create-thread modal posting a new thread
 *
 * All three now share one query cache; refetching after a WS event or a
 * successful create invalidates from a single place.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryClient'

export interface ThreadListFilters {
  study_id?: string | null
  site_id?: string | null
  limit?: number
  offset?: number
}

export function useThreadsList(
  filters: ThreadListFilters = {},
  options?: { enabled?: boolean; refetchInterval?: number | false },
) {
  return useQuery({
    queryKey: QK.threads(filters as Record<string, unknown>),
    queryFn: async () => {
      const params: Record<string, unknown> = {}
      if (filters.study_id) params.study_id = filters.study_id
      if (filters.site_id) params.site_id = filters.site_id
      if (filters.limit) params.limit = filters.limit
      if (filters.offset) params.offset = filters.offset
      const res = await api.get('/threads', { params })
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchInterval ?? false,
    staleTime: 15_000,
  })
}

export function useThread(
  threadId: string | null | undefined,
  options?: { limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: QK.thread(threadId ?? ''),
    queryFn: async () => {
      if (!threadId) return null
      const params: Record<string, number> = {}
      if (options?.limit) params.limit = options.limit
      if (options?.offset) params.offset = options.offset
      const res = await api.get(`/threads/${threadId}`, { params })
      return res.data
    },
    enabled: Boolean(threadId),
    staleTime: 5_000,
  })
}

/**
 * Create-thread mutation. Invalidates the threads-list cache on success so
 * the sidebar updates without manual refetch.
 */
export interface CreateThreadPayload {
  conversation_id?: string
  title: string
  description?: string
  thread_type: string
  related_patient_id?: string
  related_study_id?: string | null
  site_id?: string | null
  priority: string
  created_by?: string
  participants?: Array<{
    participant_id: string
    participant_name?: string
    participant_email?: string
    role?: string
  }>
}

export function useDeleteThread() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (threadId: string) => {
      await api.delete(`/threads/${threadId}`)
      return threadId
    },
    onSuccess: (threadId) => {
      qc.invalidateQueries({ queryKey: ['threads'] })
      qc.removeQueries({ queryKey: QK.thread(threadId) })
    },
  })
}

export function useCreateThread() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CreateThreadPayload) => {
      const res = await api.post('/threads', payload)
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['threads'] })
    },
  })
}

// -----------------------------------------------------------------------------
// AI thread-combination suggestions
// -----------------------------------------------------------------------------
// Backs ThreadCombinationSuggestions. The queryFn runs the upstream AI call
// then sanity-checks each suggestion against the threads API — if a thread
// in a returned suggestion no longer exists (e.g. it was just deleted),
// drop the row rather than render a broken card.
export interface ThreadCombinationSuggestion {
  thread1_id: string
  thread2_id: string
  thread1_title: string
  thread2_title: string
  should_combine: boolean
  similarity_score: number
  reasoning: string
  factors: string[]
  recommendation: 'strong' | 'moderate' | 'weak' | 'no'
}

export function useThreadCombinationSuggestions(
  studyId: string | null | undefined,
  siteId: string | null | undefined,
  options?: { enabled?: boolean; limit?: number },
) {
  const limit = options?.limit ?? 10
  return useQuery<ThreadCombinationSuggestion[]>({
    queryKey: ['thread-combinations', studyId, siteId, limit],
    queryFn: async () => {
      if (!studyId || !siteId) return []
      try {
        const res = await api.get<ThreadCombinationSuggestion[]>(
          '/threads/suggest-combinations',
          { params: { study_id: studyId, site_id: siteId, limit } },
        )
        const suggestions = res.data ?? []
        const valid: ThreadCombinationSuggestion[] = []
        for (const s of suggestions) {
          try {
            // Both threads must still exist — otherwise the card renders but
            // the Combine action 404s. Probe each side before keeping the row.
            await Promise.all([
              api.get(`/threads/${s.thread1_id}`, { params: { limit: 1 } }),
              api.get(`/threads/${s.thread2_id}`, { params: { limit: 1 } }),
            ])
            valid.push(s)
          } catch {
            // Skip suggestion silently — a referenced thread was deleted.
          }
        }
        return valid
      } catch (err: any) {
        if (err?.response?.status === 404) return []
        throw err
      }
    },
    enabled: Boolean(studyId && siteId) && (options?.enabled ?? true),
    staleTime: 60_000,
    retry: 0,
  })
}

export function useCombineThreads() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: {
      thread1_id: string
      thread2_id: string
      target_thread_id?: string
    }) => {
      const res = await api.post('/threads/combine', {
        thread1_id: payload.thread1_id,
        thread2_id: payload.thread2_id,
        target_thread_id: payload.target_thread_id ?? payload.thread1_id,
      })
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['threads'] })
      qc.invalidateQueries({ queryKey: ['thread-combinations'] })
    },
  })
}
