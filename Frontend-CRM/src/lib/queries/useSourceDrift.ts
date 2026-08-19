/**
 * Source-backed field drift hooks (#6).
 *
 * Backs SourceDriftPanel. GENERAL across any source-backed field / agreement type —
 * the backend decides which tokens are source-backed; the UI just surfaces the drift
 * and lets the user keep their edit or pull the live source value.
 *
 *   GET  /agreements/{id}/source-drift        -> { in_sync, drifted: [{token, doc_value, source_value}] }
 *   POST /agreements/{id}/source-drift/pull   -> { updated, version_number }   body: { tokens: [...] }
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface DriftedField {
  token: string
  doc_value: string
  source_value: string
}

export interface SourceDriftResponse {
  in_sync: string[]
  drifted: DriftedField[]
  note?: string
}

export const sourceDriftKey = (agreementId: string | null | undefined) =>
  ['agreement-source-drift', agreementId] as const

export function useSourceDrift(agreementId: string | null | undefined, enabled = true) {
  return useQuery<SourceDriftResponse>({
    queryKey: sourceDriftKey(agreementId),
    queryFn: async () => {
      const res = await api.get<SourceDriftResponse>(`/agreements/${agreementId}/source-drift`)
      return res.data
    },
    enabled: Boolean(agreementId) && enabled,
    staleTime: 15_000,
  })
}

export function usePullSourceValues(agreementId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation<{ updated: string[]; version_number: number }, unknown, string[]>({
    mutationFn: async (tokens: string[]) => {
      const res = await api.post(`/agreements/${agreementId}/source-drift/pull`, { tokens })
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: sourceDriftKey(agreementId) })
    },
  })
}
