// Read-only client for the Orbit live-eval score surface. In-house only —
// nothing is sent to external eval dashboards.
import { api } from '../../../lib/api'

export interface LiveEvalMetricSummary {
  name: string
  score: number
  passed: boolean
  applicable: boolean
}

export interface LiveEvalMetricDetail extends LiveEvalMetricSummary {
  reason: string
}

export interface LiveEvalScoreSummary {
  id: string
  created_at: string | null
  user_id: string
  session_id: string
  message_preview: string
  scored_mode: 'deterministic_only' | 'with_judge'
  judge_model: string | null
  overall_passed: boolean
  metrics: LiveEvalMetricSummary[]
}

export interface LiveEvalScoreDetail extends LiveEvalScoreSummary {
  answer_preview: string
  metrics: LiveEvalMetricDetail[]
}

export interface LiveEvalStatus {
  enabled: boolean
  judge_enabled: boolean
  judge_model: string
  sample_rate: number
}

export interface LiveEvalSummary {
  window_hours: number
  turns_scored: number
  trend: { bucket: string; total: number; passed: number }[]
  per_metric: Record<string, { total: number; passed: number }>
}

// Relative to the shared api client's baseURL, which already ends in /api
// (VITE_API_BASE=http://.../api) — same convention as the other services.
const BASE = '/assistant/live-evals'

export const liveEvalService = {
  status: async (): Promise<LiveEvalStatus> => (await api.get(`${BASE}/status`)).data,

  scores: async (opts: { limit?: number; metric?: string; failingOnly?: boolean } = {}):
    Promise<LiveEvalScoreSummary[]> => {
    const params: Record<string, unknown> = { limit: opts.limit ?? 50 }
    if (opts.metric) params.metric = opts.metric
    if (opts.failingOnly) params.failing_only = true
    return (await api.get(`${BASE}/scores`, { params })).data
  },

  score: async (id: string): Promise<LiveEvalScoreDetail> =>
    (await api.get(`${BASE}/scores/${id}`)).data,

  summary: async (hours = 24): Promise<LiveEvalSummary> =>
    (await api.get(`${BASE}/summary`, { params: { hours } })).data,
}
