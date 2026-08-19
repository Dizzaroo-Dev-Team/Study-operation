/**
 * Feasibility-domain query hooks.
 *
 * Backs the token-gated public Feasibility form page. The token is single-use,
 * so we disable focus-refetch and retries to avoid surprising the signer.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface FeasibilityQuestion {
  text: string
  section?: string
  type: string
  id?: string
  display_order?: number
}

export interface ProtocolSynopsis {
  id: string
  study_site_id: string
  file_name: string
  file_path: string
  content_type: string
  size: number
  uploaded_by?: string
  uploaded_at: string
}

export interface FeasibilityFormData {
  request_id: string
  study_name: string
  site_name: string
  questions: FeasibilityQuestion[]
  protocol_synopsis?: ProtocolSynopsis
}

export function useFeasibilityForm(token: string | null) {
  return useQuery<FeasibilityFormData>({
    queryKey: ['feasibility-form', token],
    queryFn: async () => {
      const res = await api.get<FeasibilityFormData>('/feasibility/form', {
        params: token ? { token } : undefined,
      })
      return res.data
    },
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 0,
  })
}

export interface FeasibilitySubmitPayload {
  token: string
  answers: Array<{
    question_text: string
    question_id: string | null
    answer: string
    section: string | null
  }>
}

export function useSubmitFeasibility() {
  return useMutation({
    mutationFn: async (payload: FeasibilitySubmitPayload) => {
      const res = await api.post('/feasibility/submit', payload)
      return res.data
    },
  })
}
