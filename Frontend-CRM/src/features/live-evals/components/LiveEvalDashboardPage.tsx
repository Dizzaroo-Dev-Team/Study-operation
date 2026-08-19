// Orbit Live Evals — in-house dashboard for Kind B (live) scoring.
// Read-only view over the append-only live_eval_scores table: recent turns
// with per-metric pass/fail, click-through to the judge's REASON for each
// metric, an hourly pass-rate trend, and honest mode banners.
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  liveEvalService,
  LiveEvalScoreDetail,
  LiveEvalScoreSummary,
  LiveEvalStatus,
  LiveEvalSummary,
} from '../services/liveEvalService'

const METRIC_LABELS: Record<string, string> = {
  no_phi_in_answer: 'No PHI in answer',
  dangerous_request_refused: 'Dangerous request refused',
  rbac_denials_honored: 'RBAC denials honored',
  fill_never_submit: 'Fill-never-submit',
  no_forbidden_actions: 'No forbidden actions',
  write_gate_integrity: 'Write gate integrity',
  grounding: 'Grounding (LLM judge)',
}

const metricLabel = (name: string) => METRIC_LABELS[name] || name

const MetricChip: React.FC<{ m: { name: string; passed: boolean; applicable: boolean } }> = ({ m }) => (
  <span
    title={metricLabel(m.name)}
    className={
      'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium mr-1 mb-1 ' +
      (!m.applicable
        ? 'bg-gray-100 text-gray-400 border border-gray-200'
        : m.passed
          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
          : 'bg-red-50 text-red-700 border border-red-300')
    }
  >
    {!m.applicable ? '·' : m.passed ? '✓' : '✗'}&nbsp;{metricLabel(m.name)}
  </span>
)

const Banner: React.FC<{ status: LiveEvalStatus | null }> = ({ status }) => {
  if (!status) return null
  if (!status.enabled) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <strong>Live evals are disabled</strong> (ENABLE_LIVE_EVALS=false). No new turns are being
        scored; the data below is historical.
      </div>
    )
  }
  if (!status.judge_enabled) {
    return (
      <div className="rounded-lg border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-800">
        <strong>Deterministic-only mode</strong> — the LLM judge is disabled
        (ENABLE_LIVE_JUDGE=false). All checks run locally; no text leaves the box. Grounding is not
        scored in this mode.
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
      Live scoring active with judge <strong>{status.judge_model}</strong> (PHI-scrubbed text only) ·
      sampling {(status.sample_rate * 100).toFixed(0)}% of turns.
    </div>
  )
}

const DetailPanel: React.FC<{ detail: LiveEvalScoreDetail; onClose: () => void }> = ({ detail, onClose }) => (
  <div className="rounded-xl border border-gray-300 bg-white shadow-sm p-4 space-y-3">
    <div className="flex items-start justify-between">
      <div>
        <div className="text-sm font-semibold text-gray-900">
          Turn {detail.created_at ? new Date(detail.created_at).toLocaleString() : ''}
        </div>
        <div className="text-xs text-gray-500">
          user {detail.user_id} · session {detail.session_id} · mode{' '}
          <span className="font-medium">{detail.scored_mode}</span>
          {detail.judge_model ? ` · judge ${detail.judge_model}` : ''}
        </div>
      </div>
      <button onClick={onClose} className="text-xs text-gray-500 hover:text-gray-800 underline">
        close
      </button>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="rounded-lg bg-gray-50 border border-gray-200 p-3">
        <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">User asked (scrubbed)</div>
        <div className="text-sm text-gray-800 whitespace-pre-wrap">{detail.message_preview || '—'}</div>
      </div>
      <div className="rounded-lg bg-gray-50 border border-gray-200 p-3">
        <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">Orbit answered (scrubbed)</div>
        <div className="text-sm text-gray-800 whitespace-pre-wrap">{detail.answer_preview || '—'}</div>
      </div>
    </div>

    <div>
      <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-2">
        Metrics — with the &ldquo;why&rdquo;
      </div>
      <div className="space-y-2">
        {detail.metrics.map((m) => (
          <div
            key={m.name}
            className={
              'rounded-lg border p-3 ' +
              (!m.applicable
                ? 'border-gray-200 bg-gray-50'
                : m.passed
                  ? 'border-emerald-200 bg-emerald-50/50'
                  : 'border-red-300 bg-red-50/60')
            }
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-900">{metricLabel(m.name)}</span>
              <span className="text-xs font-mono text-gray-600">
                {!m.applicable ? 'n/a' : `${m.passed ? 'PASS' : 'FAIL'} · ${m.score.toFixed(2)}`}
              </span>
            </div>
            <div className="mt-1 text-sm text-gray-700 whitespace-pre-wrap">{m.reason}</div>
          </div>
        ))}
      </div>
    </div>
  </div>
)

const LiveEvalDashboardPage: React.FC = () => {
  const [status, setStatus] = useState<LiveEvalStatus | null>(null)
  const [summary, setSummary] = useState<LiveEvalSummary | null>(null)
  const [rows, setRows] = useState<LiveEvalScoreSummary[]>([])
  const [detail, setDetail] = useState<LiveEvalScoreDetail | null>(null)
  const [metricFilter, setMetricFilter] = useState('')
  const [failingOnly, setFailingOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [st, sm, sc] = await Promise.all([
        liveEvalService.status(),
        liveEvalService.summary(24),
        liveEvalService.scores({ limit: 100, metric: metricFilter || undefined, failingOnly }),
      ])
      setStatus(st)
      setSummary(sm)
      setRows(sc)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'failed to load live evals')
    } finally {
      setLoading(false)
    }
  }, [metricFilter, failingOnly])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 30000)
    return () => clearInterval(t)
  }, [refresh])

  const openDetail = async (id: string) => {
    try {
      setDetail(await liveEvalService.score(id))
    } catch {
      /* row may have raced; refresh picks it up */
    }
  }

  const trendData = useMemo(
    () =>
      (summary?.trend || []).map((b) => ({
        time: new Date(b.bucket).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        passRate: b.total ? Math.round((b.passed / b.total) * 100) : null,
        turns: b.total,
      })),
    [summary],
  )

  const metricNames = useMemo(() => Object.keys(summary?.per_metric || {}), [summary])

  return (
    // The app shell sets overflow:hidden on html/body/#root, so this page must
    // own its scrolling: full-height container + overflow-y-auto.
    <div className="h-screen overflow-y-auto bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Orbit Live Evals</h1>
            <p className="text-sm text-gray-500">
              Every real turn, scored after the answer — deterministic safety invariants first, LLM
              judge (grounding) where enabled. Append-only record.
            </p>
          </div>
          <button
            onClick={refresh}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
          >
            Refresh
          </button>
        </div>

        <Banner status={status} />
        {error && (
          <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Trend + per-metric pass rates */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 rounded-xl border border-gray-300 bg-white p-4">
            <div className="text-sm font-medium text-gray-900 mb-2">
              Pass rate — last 24h ({summary?.turns_scored ?? 0} turns scored)
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip formatter={(v: any, n: any) => (n === 'passRate' ? [`${v}%`, 'pass rate'] : [v, n])} />
                  <Line type="monotone" dataKey="passRate" stroke="#0d9488" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="rounded-xl border border-gray-300 bg-white p-4">
            <div className="text-sm font-medium text-gray-900 mb-2">Per-metric (24h, applicable turns)</div>
            <div className="space-y-2">
              {metricNames.length === 0 && <div className="text-sm text-gray-400">no data yet</div>}
              {metricNames.map((name) => {
                const s = summary!.per_metric[name]
                const rate = s.total ? Math.round((s.passed / s.total) * 100) : 0
                return (
                  <div key={name}>
                    <div className="flex justify-between text-xs text-gray-600 mb-0.5">
                      <span>{metricLabel(name)}</span>
                      <span className="font-mono">{s.passed}/{s.total} · {rate}%</span>
                    </div>
                    <div className="h-1.5 rounded bg-gray-100 overflow-hidden">
                      <div
                        className={rate === 100 ? 'h-full bg-emerald-500' : rate >= 80 ? 'h-full bg-amber-500' : 'h-full bg-red-500'}
                        style={{ width: `${rate}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <select
            value={metricFilter}
            onChange={(e) => setMetricFilter(e.target.value)}
            className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700"
          >
            <option value="">all metrics</option>
            {metricNames.map((n) => (
              <option key={n} value={n}>{metricLabel(n)}</option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={failingOnly}
              onChange={(e) => setFailingOnly(e.target.checked)}
              className="rounded border-gray-300"
            />
            failing only
          </label>
          {loading && <span className="text-xs text-gray-400">loading…</span>}
        </div>

        {/* Detail panel (above the table once opened) */}
        {detail && <DetailPanel detail={detail} onClose={() => setDetail(null)} />}

        {/* Interactions table */}
        <div className="rounded-xl border border-gray-300 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2">When</th>
                <th className="px-3 py-2">User asked (scrubbed)</th>
                <th className="px-3 py-2">Mode</th>
                <th className="px-3 py-2">Overall</th>
                <th className="px-3 py-2">Metrics</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.length === 0 && !loading && (
                <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-400">
                  No scored turns yet{status && !status.enabled ? ' — live evals are disabled' : ''}.
                </td></tr>
              )}
              {rows.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => openDetail(r.id)}
                  className="cursor-pointer hover:bg-gray-50"
                  title="Click to see per-metric reasons"
                >
                  <td className="px-3 py-2 whitespace-nowrap text-gray-600">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2 max-w-[320px] truncate text-gray-800">{r.message_preview || '—'}</td>
                  <td className="px-3 py-2 text-xs text-gray-500">{r.scored_mode === 'with_judge' ? 'judge' : 'deterministic'}</td>
                  <td className="px-3 py-2">
                    <span className={
                      'rounded-full px-2 py-0.5 text-xs font-semibold ' +
                      (r.overall_passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')
                    }>
                      {r.overall_passed ? 'PASS' : 'FAIL'}
                    </span>
                  </td>
                  <td className="px-3 py-2">{r.metrics.map((m) => <MetricChip key={m.name} m={m} />)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="text-xs text-gray-400">
          Previews and judge inputs are PHI-scrubbed ([REDACTED-*]); deterministic check reasons
          name patterns, never matched text. Scores are engineering signal — judge verdicts should
          be spot-checked by a human (judge quality caps eval quality).
        </p>
      </div>
    </div>
  )
}

export default LiveEvalDashboardPage
