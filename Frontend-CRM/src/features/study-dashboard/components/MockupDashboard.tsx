/*
 * MockupDashboard — React port of ctrlm_ctms_dashboards_mockup.html, with each
 * section wired to the per-study SDTM Postgres (study_db_01) via the
 * /api/study-dashboard endpoints. Layout, class names, and SVG markup are
 * preserved 1:1 from the mockup so the visual output matches the static spec.
 *
 * Wiring status:
 *   Section 1  Enrollment       LIVE  /enrollment
 *   Section 2  Country & site   DEMO  (no COUNTRY column in DM — needs site→country lookup)
 *   Section 3  Disposition      LIVE  /disposition
 *   Section 4  Site activation  DEMO  (no activation-milestone tables in DB)
 *   Section 5  Visit compliance LIVE  /visit-compliance   (windows not yet wired)
 *   Section 5b Patient × visit  LIVE  /patient-visit-matrix
 *   Section 6  Queries          DEMO  (no EDC query tables in DB)
 *   Section 7  Deviations       LIVE  /deviations
 *   Section 8  Milestones       LIVE  /milestones
 *   Section 9  Portfolio        DEMO  (single-study DB)
 */
import React, { useEffect, useMemo, useState } from 'react'
import {
  fetchDeviations,
  fetchDisposition,
  fetchEnrollment,
  fetchMilestones,
  fetchPatientVisitMatrix,
  fetchVisitCompliance,
} from '../services/studyDashboard.api'
import type {
  DeviationsResponse,
  DispositionResponse,
  EnrollmentResponse,
  MilestoneItem,
  MilestonesResponse,
  PatientVisitMatrixResponse,
  SubjectRow,
  VisitComplianceResponse,
} from '../types'
import AIAssistantDrawer from './ai/AIAssistantDrawer'
import Section10MyInsights from './ai/Section10MyInsights'
import { SelectedStudyProvider, useSelectedStudy } from '../context/SelectedStudyContext'
import { registryParams } from '../services/studyRegistry.api'
import '../styles/mockup.css'

const DemoBadge: React.FC = () => <span className="demo-badge">Demo data</span>
const LiveBadge: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  return <span className="live-badge">Live · {selectedStudy.databaseName ?? selectedStudy.studyName}</span>
}
const Loading: React.FC = () => (
  <div className="muted fz11" style={{ padding: 12 }}>Loading…</div>
)
const ErrorBox: React.FC<{ msg: string }> = ({ msg }) => (
  <div className="muted fz11" style={{ padding: 12, color: 'var(--color-text-danger)' }}>
    Failed to load: {msg}
  </div>
)

function useApi<T>(loader: () => Promise<T>, deps: unknown[] = []): {
  data: T | null
  loading: boolean
  error: string | null
} {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    loader()
      .then((res) => { if (alive) setData(res) })
      .catch((e: any) => {
        if (alive) setError(e?.response?.data?.detail ?? e?.message ?? 'Failed')
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { data, loading, error }
}

// ─────────────────────────────────────────────────────────────────────────────
// Action bar + Nav
// ─────────────────────────────────────────────────────────────────────────────

// Study selector — hardcoded study_db_01 study first (and pre-selected), then
// the active studies from the Data Platform Study Registry. If the registry
// call fails the local study keeps the dashboard fully functional.
const StudySelector: React.FC = () => {
  const { studies, selectedStudy, setSelectedStudy, studiesLoading, studiesError } =
    useSelectedStudy()
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }} data-testid="study-selector">
      <label className="meta" htmlFor="study-selector-select" style={{ fontWeight: 600 }}>
        Study
      </label>
      <select
        id="study-selector-select"
        value={selectedStudy.studyId}
        onChange={(e) => {
          const next = studies.find((s) => s.studyId === e.target.value)
          if (next) setSelectedStudy(next)
        }}
        style={{ fontSize: 12, padding: '3px 6px', borderRadius: 6, maxWidth: 260 }}
      >
        {studies.map((s) => (
          <option key={s.studyId} value={s.studyId}>
            {s.source === 'local' ? `${s.studyName} (${s.databaseName})` : s.studyName}
          </option>
        ))}
      </select>
      {studiesLoading && <span className="meta">Loading studies…</span>}
      {!studiesLoading && studiesError && (
        <span className="meta" style={{ color: 'var(--color-text-danger)' }}>
          Unable to load studies.
        </span>
      )}
    </div>
  )
}

const ActionBar: React.FC<{ studyLabel: string; studyMeta: string }> = ({
  studyLabel,
  studyMeta,
}) => {
  const [persona, setPersona] = useState<'sm' | 'cra' | 'exec'>('sm')
  const { selectedStudy } = useSelectedStudy()
  return (
    <div className="ab" data-testid="dashboard-action-bar">
      <div className="l">
        <span className="study">
          {selectedStudy.source === 'local' ? studyLabel : selectedStudy.studyName}
        </span>
        <span className="meta">{studyMeta}</span>
        <StudySelector />
      </div>
      <div className="l">
        <div className="pt" role="tablist" aria-label="Persona view">
          <button type="button" className={persona === 'sm' ? 'on' : ''} onClick={() => setPersona('sm')}>
            Study manager
          </button>
          <button type="button" className={persona === 'cra' ? 'on' : ''} onClick={() => setPersona('cra')}>
            CRA
          </button>
          <button type="button" className={persona === 'exec' ? 'on' : ''} onClick={() => setPersona('exec')}>
            Exec
          </button>
        </div>
        <span className="meta">Refreshed just now</span>
      </div>
    </div>
  )
}

const DashboardNav: React.FC = () => {
  const links: { id: string; label: string }[] = [
    { id: 'd1', label: '1 · Enrollment' },
    { id: 'd2', label: '2 · Country & site' },
    { id: 'd3', label: '3 · Disposition' },
    { id: 'd4', label: '4 · Site activation' },
    { id: 'd5', label: '5 · Visit compliance' },
    { id: 'd5b', label: '5b · Patient × visit' },
    { id: 'd6', label: '6 · Queries' },
    { id: 'd7', label: '7 · Deviations' },
    { id: 'd8', label: '8 · Milestones' },
    { id: 'd10', label: '10 · My AI Insights' },
    { id: 'd9', label: '9 · Portfolio' },
  ]
  const onClick = (e: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault()
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <nav className="dn" aria-label="Dashboard navigation" data-testid="dashboard-nav">
      {links.map((l) => (
        <a key={l.id} href={`#${l.id}`} onClick={(e) => onClick(e, l.id)}>{l.label}</a>
      ))}
    </nav>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. Enrollment overview (LIVE)
// ─────────────────────────────────────────────────────────────────────────────
const FUNNEL_LAYOUT: { width: number; x: number; opacity: number; fill: string; textFill: string }[] = [
  { width: 260, x: 10, opacity: 1, fill: 'var(--color-background-info)', textFill: 'var(--color-text-info)' },
  { width: 260, x: 10, opacity: 0.85, fill: 'var(--color-background-info)', textFill: 'var(--color-text-info)' },
  { width: 260, x: 10, opacity: 0.85, fill: 'var(--color-background-danger)', textFill: 'var(--color-text-danger)' },
  { width: 260, x: 10, opacity: 0.7, fill: 'var(--color-background-info)', textFill: 'var(--color-text-info)' },
  { width: 260, x: 10, opacity: 0.55, fill: 'var(--color-background-info)', textFill: 'var(--color-text-info)' },
  { width: 260, x: 10, opacity: 1, fill: 'var(--color-background-success)', textFill: 'var(--color-text-success)' },
  { width: 260, x: 10, opacity: 1, fill: 'var(--color-background-warning)', textFill: 'var(--color-text-warning)' },
]

const Section1Enrollment: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  const { data, loading, error } = useApi<EnrollmentResponse>(
    () => fetchEnrollment(registryParams(selectedStudy)),
    [selectedStudy.studyId],
  )

  // S-curve SVG geometry
  const svg = useMemo(() => {
    if (!data || data.monthly.length === 0) return null
    const points = data.monthly
    const maxCum = Math.max(data.target ?? 0, points[points.length - 1].cumulative)
    const xScale = (i: number) => 30 + (i / Math.max(1, points.length - 1)) * 245
    const yScale = (v: number) => 140 - (v / Math.max(1, maxCum)) * 130
    const path = points
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i).toFixed(1)} ${yScale(p.cumulative).toFixed(1)}`)
      .join(' ')
    const last = points[points.length - 1]
    const lastX = xScale(points.length - 1)
    const lastY = yScale(last.cumulative)
    return { path, points, maxCum, lastX, lastY, lastCumulative: last.cumulative, firstMonth: points[0].month, lastMonth: last.month }
  }, [data])

  return (
    <section className="sec" id="d1">
      <h3>
        <span className="num">1</span> Enrollment overview <LiveBadge />
      </h3>
      <p className="sub">Funnel, S-curve actual, projected completion · Refresh: hot (15 min)</p>

      {loading ? <Loading /> : error ? <ErrorBox msg={error} /> : data ? (
        <>
          <div className="kg">
            <div className="kpi"><div className="kl">Target</div><div className="kv">{data.target ?? '—'}</div><div className="kd">subjects</div></div>
            <div className="kpi">
              <div className="kl">Enrolled</div>
              <div className="kv">{data.enrolled}</div>
              <div className={`kd ${data.target ? 'up' : ''}`}>
                {data.target ? `${Math.round((data.enrolled / data.target) * 100)}% of target` : 'no target in TS'}
              </div>
            </div>
            <div className="kpi"><div className="kl">Rate / mo</div><div className="kv">{data.rate_per_month || '—'}</div><div className="kd">over enrolment span</div></div>
            <div className="kpi"><div className="kl">LPI</div><div className="kv">{data.projected_lpi ?? '—'}</div><div className="kd">{data.projected_lpi?.includes('actual') ? 'actual' : 'projected'}</div></div>
          </div>

          <div className="row2">
            <div className="cc">
              <div className="ct">Funnel</div>
              <svg viewBox="0 0 280 200" className="svgwrap" role="img" aria-label="Enrollment funnel">
                <g fontSize="11">
                  {data.funnel.map((b, i) => {
                    const L = FUNNEL_LAYOUT[i] ?? FUNNEL_LAYOUT[FUNNEL_LAYOUT.length - 1]
                    const y = 6 + i * 28
                    return (
                      <g key={b.label}>
                        <rect x={L.x} y={y} width={L.width} height="22" rx="3" fill={L.fill} opacity={L.opacity} />
                        <text x={L.x + 10} y={y + 15} fill={L.textFill} fontWeight={i === 0 || i === 3 ? '500' : undefined}>{b.label}</text>
                        <text x={L.x + L.width - 10} y={y + 15} fill={L.textFill} textAnchor="end" fontWeight={i === 0 || i === 3 ? '500' : undefined}>
                          {b.count}
                        </text>
                      </g>
                    )
                  })}
                </g>
              </svg>
            </div>

            <div className="cc">
              <div className="ct">Cumulative enrollment (actual)</div>
              <div className="lg">
                <span><span className="sw" style={{ background: '#378ADD' }} />Actual</span>
                {data.target ? <span><span className="sw" style={{ background: '#888780' }} />Target</span> : null}
              </div>
              <svg viewBox="0 0 280 170" className="svgwrap" role="img" aria-label="S-curve actual">
                <g fontSize="9" fill="var(--color-text-tertiary)">
                  <line x1="30" y1="10" x2="30" y2="140" stroke="var(--color-border-tertiary)" strokeWidth="0.5" />
                  <line x1="30" y1="140" x2="275" y2="140" stroke="var(--color-border-tertiary)" strokeWidth="0.5" />
                  {svg ? (
                    <>
                      <text x="26" y="14" textAnchor="end">{svg.maxCum}</text>
                      <text x="26" y="143" textAnchor="end">0</text>
                      <text x="30" y="155">{svg.firstMonth}</text>
                      <text x="275" y="155" textAnchor="end">{svg.lastMonth}</text>
                    </>
                  ) : null}
                </g>
                {svg ? (
                  <>
                    {data.target ? (
                      <line
                        x1="30"
                        y1={(140 - (data.target / svg.maxCum) * 130).toFixed(1)}
                        x2="275"
                        y2={(140 - (data.target / svg.maxCum) * 130).toFixed(1)}
                        stroke="#888780"
                        strokeWidth="0.5"
                        strokeDasharray="2 2"
                      />
                    ) : null}
                    <path d={svg.path} fill="none" stroke="#378ADD" strokeWidth="2.5" />
                    <circle cx={svg.lastX} cy={svg.lastY} r="3.5" fill="#378ADD" />
                    <text x={Math.min(svg.lastX + 6, 230)} y={svg.lastY - 4} fontSize="9" fontWeight="500" fill="#378ADD">
                      {svg.lastCumulative}
                    </text>
                  </>
                ) : null}
              </svg>
            </div>
          </div>
        </>
      ) : null}
    </section>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. Country & site (DEMO — DB has no COUNTRY column on DM)
// ─────────────────────────────────────────────────────────────────────────────
const COUNTRY_ROWS = [
  { name: 'USA', actual: 95, target: 120, color: '#378ADD' },
  { name: 'Germany', actual: 42, target: 55, color: '#378ADD' },
  { name: 'Japan', actual: 38, target: 50, color: '#378ADD' },
  { name: 'UK', actual: 28, target: 40, color: '#378ADD' },
  { name: 'France', actual: 22, target: 35, color: '#378ADD' },
  { name: 'Spain', actual: 18, target: 30, color: '#EF9F27' },
  { name: 'Italy', actual: 16, target: 30, color: '#EF9F27' },
  { name: 'Canada', actual: 12, target: 25, color: '#EF9F27' },
  { name: 'Brazil', actual: 5, target: 20, color: '#E24B4A' },
  { name: 'Poland', actual: 2, target: 15, color: '#E24B4A' },
  { name: 'S. Korea', actual: 1, target: 10, color: '#E24B4A' },
]

const Section2CountrySite: React.FC = () => (
  <section className="sec" id="d2">
    <h3>
      <span className="num">2</span> Country &amp; site enrollment <DemoBadge />
    </h3>
    <p className="sub">No COUNTRY column on DM in this DB — needs site→country lookup before wire-up</p>

    <div className="cc" style={{ marginBottom: 10 }}>
      <div className="ct">Enrollment by country (actual / target)</div>
      <svg viewBox="0 0 600 200" className="svgwrap" role="img" aria-label="Country enrollment bars">
        <g fontSize="10">
          {COUNTRY_ROWS.map((c, i) => {
            const trackW = (c.target / 120) * 240
            const fillW = (c.actual / 120) * 240
            return (
              <g key={c.name} transform={`translate(0,${8 + i * 18})`}>
                <text x="0" y="9" fill="var(--color-text-primary)">{c.name}</text>
                <rect x="60" y="0" width={trackW} height="12" fill="var(--color-background-tertiary)" rx="2" />
                <rect x="60" y="0" width={fillW} height="12" fill={c.color} rx="2" />
                <text x="310" y="9" fill="var(--color-text-secondary)">
                  {c.actual} / {c.target} · {Math.round((c.actual / c.target) * 100)}%
                </text>
              </g>
            )
          })}
          <line x1="60" y1="0" x2="60" y2="200" stroke="var(--color-border-tertiary)" strokeWidth="0.5" />
        </g>
      </svg>
    </div>

    <div className="cc">
      <div className="ct">Top sites by enrollment</div>
      <table className="d">
        <thead>
          <tr><th>Site</th><th>Country</th><th className="r">Enrolled</th><th className="r">Target</th><th className="r">Rate / mo</th><th>Status</th></tr>
        </thead>
        <tbody>
          <tr><td>102 · MD Anderson</td><td>USA</td><td className="r">22</td><td className="r">25</td><td className="r">3.0</td><td><span className="p pg">On track</span></td></tr>
          <tr><td>101 · Stanford</td><td>USA</td><td className="r">18</td><td className="r">20</td><td className="r">2.1</td><td><span className="p pg">On track</span></td></tr>
          <tr><td>205 · Berlin Charité</td><td>Germany</td><td className="r">15</td><td className="r">18</td><td className="r">1.8</td><td><span className="p pg">On track</span></td></tr>
          <tr><td>308 · Tokyo NCC</td><td>Japan</td><td className="r">14</td><td className="r">15</td><td className="r">1.5</td><td><span className="p pg">On track</span></td></tr>
          <tr><td>215 · Munich LMU</td><td>Germany</td><td className="r">9</td><td className="r">15</td><td className="r">0.9</td><td><span className="p pa">Below plan</span></td></tr>
          <tr><td>825 · Toronto PMH</td><td>Canada</td><td className="r">4</td><td className="r">10</td><td className="r">0.0</td><td><span className="p pr">Idle 45d</span></td></tr>
          <tr><td>911 · Warsaw OC</td><td>Poland</td><td className="r">0</td><td className="r">8</td><td className="r">0.0</td><td><span className="p pr">Idle 72d</span></td></tr>
        </tbody>
      </table>
    </div>
  </section>
)

// ─────────────────────────────────────────────────────────────────────────────
// 3. Disposition (LIVE)
// ─────────────────────────────────────────────────────────────────────────────
const DONUT_COLORS = ['#E24B4A', '#EF9F27', '#BA7517', '#5F5E5A', '#856B5C', '#7C7C7C']

function buildDonutSegments(items: { label: string; count: number }[], radius: number) {
  const total = items.reduce((s, x) => s + x.count, 0) || 1
  const circ = 2 * Math.PI * radius
  let offset = 0
  return items.map((x, i) => {
    const len = (x.count / total) * circ
    const seg = { color: DONUT_COLORS[i % DONUT_COLORS.length], len, gap: circ - len, offset, label: x.label, count: x.count }
    offset -= len
    return seg
  })
}

const Section3Disposition: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  const { data, loading, error } = useApi<DispositionResponse>(
    () => fetchDisposition(registryParams(selectedStudy)),
    [selectedStudy.studyId],
  )
  return (
    <section className="sec" id="d3">
      <h3>
        <span className="num">3</span> Subject disposition <LiveBadge />
      </h3>
      <p className="sub">Status breakdown, discontinuation reasons, time-to-event medians · Refresh: warm</p>

      {loading ? <Loading /> : error ? <ErrorBox msg={error} /> : data ? (() => {
        const c = data.counts
        const total = Math.max(1, c.active + c.completed + c.screen_failed + c.discontinued)
        const segs = buildDonutSegments(data.discontinuation_reasons, 55)
        return (
          <>
            <div className="kg">
              <div className="kpi"><div className="kl">Median TT screen-fail</div><div className="kv">{data.median_tt_screen_fail_days ?? '—'} d</div></div>
              <div className="kpi"><div className="kl">Median time on study</div><div className="kv">{data.median_time_on_study_days ?? '—'} d</div><div className="kd">completers</div></div>
              <div className="kpi"><div className="kl">Median TT withdrawal</div><div className="kv">{data.median_tt_withdrawal_days ?? '—'} d</div></div>
              <div className="kpi"><div className="kl">Discontinuation rate</div><div className="kv">{data.discontinuation_rate_pct ?? '—'}%</div><div className="kd">of enrolled</div></div>
            </div>

            <div className="cc" style={{ marginBottom: 10 }}>
              <div className="ct">Subject status</div>
              <div className="lg">
                <span><span className="sw" style={{ background: '#378ADD' }} />Active {c.active}</span>
                <span><span className="sw" style={{ background: '#1D9E75' }} />Completed {c.completed}</span>
                <span><span className="sw" style={{ background: '#BA7517' }} />Screen-failed {c.screen_failed}</span>
                <span><span className="sw" style={{ background: '#E24B4A' }} />Discontinued {c.discontinued}</span>
              </div>
              <div className="bar-hb" role="img" aria-label="Status bar">
                {c.active > 0 ? <div className="seg" style={{ background: '#378ADD', width: `${(c.active / total) * 100}%` }}>{c.active}</div> : null}
                {c.completed > 0 ? <div className="seg" style={{ background: '#1D9E75', width: `${(c.completed / total) * 100}%` }}>{c.completed}</div> : null}
                {c.screen_failed > 0 ? <div className="seg" style={{ background: '#BA7517', width: `${(c.screen_failed / total) * 100}%` }}>{c.screen_failed}</div> : null}
                {c.discontinued > 0 ? <div className="seg" style={{ background: '#E24B4A', width: `${(c.discontinued / total) * 100}%` }}>{c.discontinued}</div> : null}
              </div>
              <div className="fz11 muted">Out of {c.total_screened} screened</div>
            </div>

            <div className="row2">
              <div className="cc">
                <div className="ct">Discontinuation reasons (n={c.discontinued})</div>
                <svg viewBox="0 0 280 160" className="svgwrap" role="img" aria-label="Discontinuation donut">
                  <g transform="translate(80,80)">
                    <circle r="55" fill="none" stroke="var(--color-background-tertiary)" strokeWidth="22" />
                    {segs.map((s, i) => (
                      <circle
                        key={i}
                        r="55"
                        fill="none"
                        stroke={s.color}
                        strokeWidth="22"
                        strokeDasharray={`${s.len.toFixed(2)} ${s.gap.toFixed(2)}`}
                        strokeDashoffset={s.offset.toFixed(2)}
                        transform="rotate(-90)"
                      />
                    ))}
                    <text y="-2" textAnchor="middle" fontSize="20" fontWeight="500" fill="var(--color-text-primary)">{c.discontinued}</text>
                    <text y="14" textAnchor="middle" fontSize="10" fill="var(--color-text-secondary)">total</text>
                  </g>
                  <g fontSize="10" transform="translate(170,20)" fill="var(--color-text-primary)">
                    {segs.slice(0, 6).map((s, i) => (
                      <g key={i} transform={`translate(0,${i * 18})`}>
                        <circle cx="0" cy="0" r="4" fill={s.color} />
                        <text x="10" y="4">{s.label.length > 18 ? s.label.slice(0, 17) + '…' : s.label} · {s.count}</text>
                      </g>
                    ))}
                  </g>
                </svg>
              </div>
              <div className="cc">
                <div className="ct">Screen failure / I-E criteria not met (n={c.screen_failed})</div>
                <table className="d">
                  <tbody>
                    {data.screen_failure_reasons.map((r) => {
                      const pct = c.screen_failed ? Math.round((r.count / c.screen_failed) * 100) : 0
                      const trimmed = r.label.length > 60 ? r.label.slice(0, 57) + '…' : r.label
                      return (
                        <tr key={r.label}>
                          <td>{trimmed}</td>
                          <td className="r">{r.count}</td>
                          <td className="r muted">{pct}%</td>
                        </tr>
                      )
                    })}
                    {data.screen_failure_reasons.length === 0 ? (
                      <tr><td colSpan={3} className="muted fz11">No screen-failure records in IE.</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )
      })() : null}
    </section>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. Site activation (DEMO — no DB source)
// ─────────────────────────────────────────────────────────────────────────────
const Section4SiteActivation: React.FC = () => (
  <section className="sec" id="d4">
    <h3>
      <span className="num">4</span> Site status &amp; activation <DemoBadge />
    </h3>
    <p className="sub">Needs site-activation milestone feed from CTMS — not in SDTM DB</p>

    <div className="cc" style={{ marginBottom: 10 }}>
      <div className="ct">Activation pipeline</div>
      <svg viewBox="0 0 600 70" className="svgwrap" role="img" aria-label="Activation pipeline">
        <defs>
          <marker id="arr4" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L 10 5 L 0 10 Z" fill="var(--color-border-secondary)" />
          </marker>
        </defs>
        <g fontSize="11">
          {[
            { x: 0, label: 'Identified', value: 42, fill: '#F1EFE8', textColor: '#2C2C2A', valueColor: '#5F5E5A' },
            { x: 124, label: 'Selected', value: 38, fill: '#F1EFE8', textColor: '#2C2C2A', valueColor: '#5F5E5A' },
            { x: 248, label: 'Initiated', value: 36, fill: '#E6F1FB', textColor: '#0C447C', valueColor: '#185FA5' },
            { x: 372, label: 'Active', value: 31, fill: '#E1F5EE', textColor: '#085041', valueColor: '#0F6E56' },
            { x: 496, label: 'Closed', value: 5, fill: '#F1EFE8', textColor: '#2C2C2A', valueColor: '#5F5E5A', width: 100 },
          ].map((s, i) => (
            <React.Fragment key={s.label}>
              {i > 0 ? (
                <path d={`M${s.x - 16} 35 L ${s.x - 2} 35`} stroke="var(--color-border-secondary)" strokeWidth="1" markerEnd="url(#arr4)" />
              ) : null}
              <g transform={`translate(${s.x},10)`}>
                <rect width={s.width ?? 106} height="50" rx="5" fill={s.fill} />
                <text x={(s.width ?? 106) / 2} y="20" textAnchor="middle" fill={s.textColor} fontWeight="500">{s.label}</text>
                <text x={(s.width ?? 106) / 2} y="40" textAnchor="middle" fill={s.valueColor} fontSize="16" fontWeight="500">{s.value}</text>
              </g>
            </React.Fragment>
          ))}
        </g>
      </svg>
    </div>

    <div className="cc">
      <div className="ct">Activation timeline · planned vs actual (sample sites)</div>
      <div className="lg">
        <span><span className="sw" style={{ background: '#B4B2A9' }} />Planned</span>
        <span><span className="sw" style={{ background: '#1D9E75' }} />Actual on-time</span>
        <span><span className="sw" style={{ background: '#EF9F27' }} />Slipped</span>
        <span><span className="sw" style={{ background: '#E24B4A' }} />Pending</span>
      </div>
      <svg viewBox="0 0 600 180" className="svgwrap" role="img" aria-label="Activation Gantt">
        <g fontSize="10" fill="var(--color-text-primary)">
          <g fill="var(--color-text-tertiary)" fontSize="9">
            <text x="100" y="14">Jan 24</text><text x="200" y="14">May 24</text><text x="300" y="14">Sep 24</text><text x="400" y="14">Jan 25</text><text x="500" y="14">May 25</text>
          </g>
          {[100, 200, 300, 400, 500].map((x) => (
            <line key={x} x1={x} y1="20" x2={x} y2="175" stroke="var(--color-border-tertiary)" strokeWidth="0.5" />
          ))}
          <g transform="translate(0,30)"><text x="0" y="9">102 · MD Anderson</text><rect x="100" y="2" width="16" height="10" fill="#B4B2A9" rx="2" /><rect x="110" y="2" width="16" height="10" fill="#1D9E75" rx="2" /><text x="540" y="9" fill="var(--color-text-success)">+5d</text></g>
          <g transform="translate(0,50)"><text x="0" y="9">101 · Stanford</text><rect x="115" y="2" width="16" height="10" fill="#B4B2A9" rx="2" /><rect x="120" y="2" width="16" height="10" fill="#1D9E75" rx="2" /><text x="540" y="9" fill="var(--color-text-success)">+3d</text></g>
          <g transform="translate(0,70)"><text x="0" y="9">205 · Berlin</text><rect x="135" y="2" width="16" height="10" fill="#B4B2A9" rx="2" /><rect x="148" y="2" width="16" height="10" fill="#1D9E75" rx="2" /><text x="540" y="9" fill="var(--color-text-success)">+7d</text></g>
          <g transform="translate(0,90)"><text x="0" y="9">308 · Tokyo</text><rect x="155" y="2" width="16" height="10" fill="#B4B2A9" rx="2" /><rect x="195" y="2" width="16" height="10" fill="#EF9F27" rx="2" /><text x="540" y="9" fill="var(--color-text-warning)">+38d</text></g>
          <g transform="translate(0,110)"><text x="0" y="9">619 · Madrid</text><rect x="220" y="2" width="16" height="10" fill="#B4B2A9" rx="2" /><rect x="280" y="2" width="16" height="10" fill="#EF9F27" rx="2" /><text x="540" y="9" fill="var(--color-text-warning)">+56d</text></g>
          <g transform="translate(0,130)"><text x="0" y="9">825 · Toronto</text><rect x="280" y="2" width="16" height="10" fill="#B4B2A9" rx="2" /><rect x="395" y="2" width="16" height="10" fill="#EF9F27" rx="2" /><text x="540" y="9" fill="var(--color-text-warning)">+110d</text></g>
          <g transform="translate(0,150)"><text x="0" y="9">911 · Warsaw</text><rect x="340" y="2" width="16" height="10" fill="#B4B2A9" rx="2" /><rect x="455" y="2" width="16" height="10" fill="#E24B4A" rx="2" stroke="#A32D2D" strokeWidth="0.5" strokeDasharray="2 2" /><text x="540" y="9" fill="var(--color-text-danger)">Pending</text></g>
        </g>
      </svg>
    </div>
  </section>
)

// ─────────────────────────────────────────────────────────────────────────────
// 5. Visit compliance (LIVE — coarse, no windows yet)
// ─────────────────────────────────────────────────────────────────────────────
const Section5VisitCompliance: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  const { data, loading, error } = useApi<VisitComplianceResponse>(
    () => fetchVisitCompliance(registryParams(selectedStudy)),
    [selectedStudy.studyId],
  )

  return (
    <section className="sec" id="d5">
      <h3>
        <span className="num">5</span> Visit compliance &amp; schedule adherence <LiveBadge />
      </h3>
      <p className="sub">
        Coarse compliance from SV vs TV — on-window / out-of-window split requires per-visit window config (not in TV)
      </p>

      {loading ? <Loading /> : error ? <ErrorBox msg={error} /> : data ? (() => {
        const rowsToShow = data.rows.slice(0, 10)
        const maxTotal = Math.max(1, ...data.rows.map((r) => r.performed + r.missed + r.upcoming))
        return (
          <>
            <div className="kg">
              <div className="kpi"><div className="kl">Visits performed</div><div className="kv">{data.total_performed}</div></div>
              <div className="kpi"><div className="kl">Expected (lower bound)</div><div className="kv">{data.total_expected}</div></div>
              <div className="kpi"><div className="kl">Compliance %</div><div className="kv">{data.compliance_pct}%</div><div className="kd">performed / expected</div></div>
              <div className="kpi"><div className="kl">Planned visits</div><div className="kv">{data.rows.length}</div></div>
            </div>

            <div className="cc">
              <div className="ct">Visit status by SoA visit (first {rowsToShow.length})</div>
              <div style={{ overflowX: 'auto' }}>
                <table className="d" style={{ minWidth: 480 }}>
                  <thead>
                    <tr>
                      <th>Visit</th>
                      <th className="r">Performed</th>
                      <th className="r">Missed</th>
                      <th className="r">Upcoming</th>
                      <th style={{ width: '40%' }}>Mix</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rowsToShow.map((r) => {
                      const total = r.performed + r.missed + r.upcoming
                      const denom = Math.max(maxTotal, total)
                      const perfPct = (r.performed / denom) * 100
                      const missPct = (r.missed / denom) * 100
                      const upPct = (r.upcoming / denom) * 100
                      return (
                        <tr key={r.visitnum}>
                          <td style={{ whiteSpace: 'nowrap' }}>{r.visit}</td>
                          <td className="r">{r.performed}</td>
                          <td className="r" style={{ color: r.missed > 0 ? 'var(--color-text-danger)' : undefined }}>{r.missed}</td>
                          <td className="r muted">{r.upcoming}</td>
                          <td>
                            <div style={{ display: 'flex', height: 10, borderRadius: 3, overflow: 'hidden', background: 'var(--color-background-tertiary)' }}>
                              {perfPct > 0 ? <div title={`Performed ${r.performed}`} style={{ width: `${perfPct}%`, background: '#1D9E75' }} /> : null}
                              {missPct > 0 ? <div title={`Missed ${r.missed}`} style={{ width: `${missPct}%`, background: '#E24B4A', opacity: 0.7 }} /> : null}
                              {upPct > 0 ? <div title={`Upcoming ${r.upcoming}`} style={{ width: `${upPct}%`, background: '#888780', opacity: 0.4 }} /> : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {data.rows.length > rowsToShow.length ? (
                <div className="fz11 muted" style={{ marginTop: 8 }}>+ {data.rows.length - rowsToShow.length} more visits</div>
              ) : null}
            </div>
          </>
        )
      })() : null}
    </section>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 5b. Patient × Visit matrix (LIVE)
// ─────────────────────────────────────────────────────────────────────────────
function dotClassForDisposition(d?: string | null): string {
  if (!d) return 'dot dot-act'
  const up = d.toUpperCase()
  if (up === 'SCREEN FAILURE') return 'dot dot-scf'
  if (
    up === 'WITHDRAWAL BY SUBJECT' ||
    up === 'ADVERSE EVENT' ||
    up === 'DEATH' ||
    up === 'PROGRESSIVE DISEASE' ||
    up === 'PHYSICIAN DECISION' ||
    up === 'LOST TO FOLLOW-UP' ||
    up === 'OTHER'
  )
    return 'dot dot-dis'
  if (up === 'COMPLETED' || up === 'STUDY COMPLETED') return 'dot dot-com'
  return 'dot dot-act'
}

function shortDate(iso?: string | null): string {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  if (!y || !m || !d) return iso
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${d.padStart(2, '0')} ${monthNames[Number(m) - 1] ?? m} ${y.slice(2)}`
}

const Section5bPatientVisit: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  const { data, loading, error } = useApi<PatientVisitMatrixResponse>(
    () => fetchPatientVisitMatrix({ limit_subjects: 200, ...registryParams(selectedStudy) }),
    [selectedStudy.studyId],
  )
  const [showAll, setShowAll] = useState(false)
  const subjects: SubjectRow[] = data?.subjects ?? []
  const visits = data?.visits ?? []
  const visible = showAll ? subjects : subjects.slice(0, 12)

  return (
    <section className="sec" id="d5b">
      <h3>
        <span className="num">5b</span> Patient × visit matrix <LiveBadge />
      </h3>
      <p className="sub">One row per subject, one column per protocol visit; cell shows actual date when performed</p>

      <div className="pvm-toolbar">
        <div className="ctrls">
          <label>Site</label>
          <select><option>All sites</option></select>
          <label style={{ marginLeft: 4 }}>Status</label>
          <select><option>All</option></select>
          <label style={{ marginLeft: 4 }}>Arm</label>
          <select><option>All arms</option></select>
        </div>
        <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
          {loading ? 'Loading…' : error ? 'Failed to load' : `Showing ${visible.length} of ${subjects.length}`}
        </span>
      </div>

      <div className="lg" role="group" aria-label="Visit status legend">
        <span><span className="sw" style={{ background: 'var(--color-background-success)' }} />On-window</span>
        <span><span className="sw" style={{ background: 'var(--color-background-warning)' }} />Out-of-window</span>
        <span><span className="sw" style={{ background: 'var(--color-background-danger)' }} />Missed / overdue</span>
        <span><span className="sw" style={{ background: 'var(--color-background-info)' }} />Due now</span>
        <span><span className="sw" style={{ background: 'var(--color-background-secondary)' }} />Upcoming</span>
        <span><span className="dot dot-act" />Active</span>
        <span><span className="dot dot-com" />Completed</span>
        <span><span className="dot dot-dis" />Discontinued</span>
        <span><span className="dot dot-scf" />Screen-failed</span>
      </div>

      {error ? (
        <ErrorBox msg={error} />
      ) : (
        <div
          style={{
            overflowX: 'auto',
            overflowY: 'hidden',
            border: '0.5px solid var(--color-border-tertiary)',
            borderRadius: 6,
          }}
        >
          <table
            className="mt"
            role="table"
            aria-label="Patient visit matrix"
            style={{
              // Subject column ~160px + each visit column ~58px so the table
              // is forced wider than the viewport, triggering horizontal scroll
              // on the wrapper. table-layout:fixed (from .mt) then distributes
              // the width evenly across the visit columns.
              minWidth: `${160 + visits.length * 58}px`,
              tableLayout: 'fixed',
            }}
          >
            <colgroup>
              <col style={{ width: 160 }} />
              {visits.map((v) => (
                <col key={v.visitnum} style={{ width: 58 }} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th className="sub" style={{ position: 'sticky', left: 0, zIndex: 2, background: 'var(--color-background-secondary)' }}>
                  Subject
                </th>
                {visits.map((v) => (
                  <th key={v.visitnum} title={v.visit} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {v.visit}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((sub) => (
                <tr key={sub.usubjid}>
                  <td
                    className="sub"
                    style={{
                      position: 'sticky',
                      left: 0,
                      zIndex: 1,
                      background: 'var(--color-background-primary)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                    title={sub.usubjid}
                  >
                    <span className={dotClassForDisposition(sub.disposition)} />
                    {sub.usubjid.split('-').slice(-1)[0]}
                  </td>
                  {sub.cells.map((c, i) => {
                    const klass = `cell ${c.status === 'done' ? 'ok' : c.status}`
                    return (
                      <td key={i}>
                        <div className={klass}>
                          {c.date ? (
                            <span className="d">{shortDate(c.date)}</span>
                          ) : c.status === 'na' ? (
                            <span className="d">—</span>
                          ) : c.status === 'due' ? (
                            <span className="d">due</span>
                          ) : (
                            <span className="d">&nbsp;</span>
                          )}
                        </div>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {subjects.length > 12 ? (
        <div className="foot">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            style={{
              background: 'transparent',
              border: '0.5px solid var(--color-border-tertiary)',
              borderRadius: 4,
              padding: '4px 8px',
              fontSize: 11,
              color: 'var(--color-text-secondary)',
              cursor: 'pointer',
            }}
          >
            {showAll ? 'Show first 12' : `Show all ${subjects.length}`}
          </button>
          {' '}Cells show actual visit date when completed. Window deviation requires TV visit-window config.
        </div>
      ) : null}
    </section>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. Queries (DEMO — no EDC tables in DB)
// ─────────────────────────────────────────────────────────────────────────────
const Section6Queries: React.FC = () => (
  <section className="sec" id="d6">
    <h3>
      <span className="num">6</span> Query &amp; data entry health <DemoBadge />
    </h3>
    <p className="sub">Needs EDC query feed — not in SDTM DB</p>

    <div className="kg">
      <div className="kpi"><div className="kl">Open queries</div><div className="kv">142</div><div className="kd dn">+12 this week</div></div>
      <div className="kpi"><div className="kl">Closed (cumulative)</div><div className="kv">1,238</div></div>
      <div className="kpi"><div className="kl">Median age</div><div className="kv">9 d</div></div>
      <div className="kpi"><div className="kl">Median entry lag</div><div className="kv">3.2 d</div><div className="kd">visit → eCRF</div></div>
    </div>

    <div className="row2">
      <div className="cc">
        <div className="ct">Open queries by age bucket</div>
        <svg viewBox="0 0 280 160" className="svgwrap" role="img" aria-label="Query aging">
          <g fontSize="10" fill="var(--color-text-primary)">
            <line x1="30" y1="120" x2="270" y2="120" stroke="var(--color-border-tertiary)" strokeWidth="0.5" />
            <rect x="50" y="44" width="40" height="76" fill="#1D9E75" rx="3" />
            <text x="70" y="38" textAnchor="middle" fontWeight="500">62</text>
            <text x="70" y="135" textAnchor="middle" fill="var(--color-text-secondary)">0–7 d</text>
            <rect x="105" y="68" width="40" height="52" fill="#EF9F27" opacity="0.85" rx="3" />
            <text x="125" y="62" textAnchor="middle" fontWeight="500">43</text>
            <text x="125" y="135" textAnchor="middle" fill="var(--color-text-secondary)">8–14 d</text>
            <rect x="160" y="88" width="40" height="32" fill="#BA7517" rx="3" />
            <text x="180" y="82" textAnchor="middle" fontWeight="500">27</text>
            <text x="180" y="135" textAnchor="middle" fill="var(--color-text-secondary)">15–30 d</text>
            <rect x="215" y="108" width="40" height="12" fill="#E24B4A" rx="3" />
            <text x="235" y="102" textAnchor="middle" fontWeight="500">10</text>
            <text x="235" y="135" textAnchor="middle" fill="var(--color-text-secondary)">30+ d</text>
          </g>
        </svg>
      </div>
      <div className="cc">
        <div className="ct">Data entry lag (days, all visits last 90d)</div>
        <svg viewBox="0 0 280 160" className="svgwrap" role="img" aria-label="Entry lag histogram">
          <g fontSize="9">
            <line x1="20" y1="125" x2="270" y2="125" stroke="var(--color-border-tertiary)" strokeWidth="0.5" />
            {[[22, 20, 105], [46, 35, 90], [70, 60, 65], [94, 85, 40], [118, 100, 25], [142, 108, 17], [166, 112, 13], [190, 116, 9], [214, 118, 7], [238, 120, 5]].map(([x, y, h], i) => (
              <rect key={i} x={x} y={y} width="22" height={h} fill={i >= 8 ? '#E24B4A' : i >= 7 ? '#EF9F27' : '#378ADD'} rx="2" />
            ))}
            <line x1="60" y1="20" x2="60" y2="125" stroke="#5F5E5A" strokeWidth="0.5" strokeDasharray="2 2" />
            <text x="64" y="20" fill="#5F5E5A" fontWeight="500">Median 3.2d</text>
          </g>
        </svg>
      </div>
    </div>
  </section>
)

// ─────────────────────────────────────────────────────────────────────────────
// 7. Deviations (LIVE)
// ─────────────────────────────────────────────────────────────────────────────
const Section7Deviations: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  const { data, loading, error } = useApi<DeviationsResponse>(
    () => fetchDeviations(registryParams(selectedStudy)),
    [selectedStudy.studyId],
  )
  return (
    <section className="sec" id="d7">
      <h3>
        <span className="num">7</span> Protocol deviations <LiveBadge />
      </h3>
      <p className="sub">DV.DVCAT only has Major/Minor in this dataset — "Critical" tier is N/A</p>

      {loading ? <Loading /> : error ? <ErrorBox msg={error} /> : data ? (() => {
        const maxWeek = Math.max(1, ...data.weekly.map((w) => w.count))
        const weeks = data.weekly.slice(-12)
        return (
          <>
            <div className="kg">
              <div className="kpi"><div className="kl">Total PDs</div><div className="kv">{data.total}</div></div>
              <div className="kpi"><div className="kl">Critical</div><div className="kv" style={{ color: 'var(--color-text-tertiary)' }}>{data.critical}</div><div className="kd">N/A</div></div>
              <div className="kpi"><div className="kl">Major</div><div className="kv">{data.major}</div></div>
              <div className="kpi"><div className="kl">PD rate / subject</div><div className="kv">{data.pd_rate_per_subject}</div></div>
            </div>

            <div className="row2">
              <div className="cc">
                <div className="ct">Weekly PD volume (last {weeks.length} weeks)</div>
                <svg viewBox="0 0 280 140" className="svgwrap" role="img" aria-label="Weekly PD trend">
                  <g fontSize="9">
                    <line x1="20" y1="110" x2="270" y2="110" stroke="var(--color-border-tertiary)" strokeWidth="0.5" />
                    <g fill="#378ADD">
                      {weeks.map((w, i) => {
                        const h = (w.count / maxWeek) * 84
                        const y = 110 - h
                        const x = 22 + i * 20
                        return <rect key={i} x={x} y={y} width="16" height={h} rx="2" />
                      })}
                    </g>
                    <g fill="var(--color-text-tertiary)">
                      <text x="30" y="123" textAnchor="middle">{weeks[0]?.week_start.slice(5)}</text>
                      <text x="250" y="123" textAnchor="middle">{weeks[weeks.length - 1]?.week_start.slice(5)}</text>
                    </g>
                  </g>
                </svg>
              </div>
              <div className="cc">
                <div className="ct">Top categories</div>
                <table className="d">
                  <tbody>
                    {data.top_categories.map((c) => (
                      <tr key={c.label}>
                        <td>{c.label}</td>
                        <td className="r">{c.count}</td>
                        <td><span className={`p ${c.major_count > 0 ? 'pa' : 'px'}`}>{c.major_count} major</span></td>
                      </tr>
                    ))}
                    {data.top_categories.length === 0 ? (
                      <tr><td colSpan={3} className="muted fz11">No DV records.</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )
      })() : null}
    </section>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 8. Milestones (LIVE — operational milestones only; DB lock not in DB)
// ─────────────────────────────────────────────────────────────────────────────
function colorForTone(tone: string): string {
  switch (tone) {
    case 'success': return '#1D9E75'
    case 'warning': return '#EF9F27'
    case 'danger': return '#E24B4A'
    default: return 'var(--color-background-tertiary)'
  }
}

function fmtMonth(iso: string | null): string {
  if (!iso) return '—'
  const [y, m] = iso.split('-')
  if (!y || !m) return iso
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${monthNames[Number(m) - 1] ?? m} ${y.slice(2)}`
}

const Section8Milestones: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  const { data, loading, error } = useApi<MilestonesResponse>(
    () => fetchMilestones(registryParams(selectedStudy)),
    [selectedStudy.studyId],
  )
  return (
    <section className="sec" id="d8">
      <h3>
        <span className="num">8</span> Study milestone tracker <LiveBadge />
      </h3>
      <p className="sub">FSI/FPI/LPI/LPO + 25/50/75% enrollment dates from DM. DB lock not in SDTM.</p>

      {loading ? <Loading /> : error ? <ErrorBox msg={error} /> : data ? (() => {
        const items = data.milestones
        const dated = items.filter((m): m is MilestoneItem & { date: string } => !!m.date)
        // Spread items horizontally with even spacing
        const W = 600
        const padding = 30
        const positions = items.map((_, i) => padding + (i * (W - padding * 2)) / Math.max(1, items.length - 1))
        return (
          <>
            <div className="cc" style={{ marginBottom: 10 }}>
              <div className="ct">Milestone timeline</div>
              <svg viewBox={`0 0 ${W} 130`} className="svgwrap" role="img" aria-label="Milestone timeline">
                <g fontSize="9" fill="var(--color-text-primary)">
                  <line x1="20" y1="65" x2={W - 20} y2="65" stroke="var(--color-border-secondary)" strokeWidth="1.5" />
                  {items.map((m, i) => {
                    const x = positions[i]
                    return (
                      <g key={m.key} transform={`translate(${x},65)`}>
                        <circle r="6" fill={colorForTone(m.tone)} stroke={m.tone === 'secondary' ? 'var(--color-border-secondary)' : undefined} strokeWidth={m.tone === 'secondary' ? 1 : undefined} />
                        <text y="-12" textAnchor="middle" fill="var(--color-text-secondary)" fontSize="9">{fmtMonth(m.date)}</text>
                        <text y="22" textAnchor="middle" fontWeight="500" fontSize="10">{m.label}</text>
                        <text y="34" textAnchor="middle" fill={`var(--color-text-${m.tone === 'secondary' ? 'secondary' : m.tone})`} fontSize="9">
                          {m.date ? '' : 'n/a'}
                        </text>
                      </g>
                    )
                  })}
                </g>
              </svg>
            </div>

            <div className="cc">
              <div className="ct">Milestone dates</div>
              <table className="d">
                <thead>
                  <tr><th>Milestone</th><th>Date</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {items.map((m) => (
                    <tr key={m.key}>
                      <td>{m.label}</td>
                      <td>{m.date ?? '—'}</td>
                      <td>
                        <span className={`p ${m.tone === 'secondary' ? 'px' : m.tone === 'success' ? 'pg' : m.tone === 'warning' ? 'pa' : 'pr'}`}>
                          {m.date ? 'actual' : 'not in DB'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="fz11 muted" style={{ marginTop: 8 }}>
                {dated.length} of {items.length} milestones derived from DM. Planned dates / variance need CTMS milestone config.
              </div>
            </div>
          </>
        )
      })() : null}
    </section>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 9. Portfolio (DEMO — single-study DB)
// ─────────────────────────────────────────────────────────────────────────────
const Section9Portfolio: React.FC = () => (
  <section className="sec" id="d9">
    <h3>
      <span className="num">9</span> Portfolio status <span className="p pi" style={{ marginLeft: 8 }}>Exec view</span> <DemoBadge />
    </h3>
    <p className="sub">Single-study DB — portfolio view needs cross-study source</p>

    <div className="cc" style={{ marginBottom: 10 }}>
      <div className="ct">Studies × KPIs</div>
      <table className="d">
        <thead>
          <tr><th>Study</th><th>Phase</th><th className="r">Enrolled</th><th className="r">Sites</th><th>Milestone</th><th className="r">Crit. PDs</th><th>Status</th></tr>
        </thead>
        <tbody>
          <tr><td>ONCOTRIA-301 · NSCLC</td><td>3</td><td className="r">287 / 450 (64%)</td><td className="r">31 / 38</td><td><span className="p pr">75% enr +90d</span></td><td className="r">2</td><td><span className="p pa">At risk</span></td></tr>
          <tr><td>DERMACURE-201 · Psoriasis</td><td>2</td><td className="r">142 / 180 (79%)</td><td className="r">22 / 25</td><td><span className="p pg">On plan</span></td><td className="r">0</td><td><span className="p pg">Healthy</span></td></tr>
          <tr><td>NEUROFLOW-302 · Alzheimer</td><td>3</td><td className="r">89 / 300 (30%)</td><td className="r">18 / 35</td><td><span className="p pr">50% enr +120d</span></td><td className="r">4</td><td><span className="p pr">At risk</span></td></tr>
          <tr><td>IMMUNOFRX-101 · Solid tumors</td><td>1</td><td className="r">24 / 40 (60%)</td><td className="r">6 / 8</td><td><span className="p pg">On plan</span></td><td className="r">0</td><td><span className="p pg">Healthy</span></td></tr>
          <tr><td>CARDIODYN-203 · Heart failure</td><td>2</td><td className="r">156 / 200 (78%)</td><td className="r">19 / 22</td><td><span className="p pg">On plan</span></td><td className="r">1</td><td><span className="p pg">Healthy</span></td></tr>
        </tbody>
      </table>
    </div>
  </section>
)

// ─────────────────────────────────────────────────────────────────────────────
// Top-level container
// ─────────────────────────────────────────────────────────────────────────────
const MockupDashboard: React.FC<{ studyLabel?: string; studyMeta?: string }> = ({
  studyLabel = 'DS8201-A-U201',
  studyMeta = 'Phase · Indication · sites — from TS',
}) => {
  return (
    <SelectedStudyProvider>
    <div className="ctms-root">
      <div className="page">
        <header className="page-header">
          <h1>CTMS Operational Dashboards</h1>
          <p>Sections marked Live are wired to the selected study's SDTM Postgres (study_db_01 by default). Demo data sections need a different feed (CTMS / EDC / cross-study DB).</p>
        </header>

        <ActionBar studyLabel={studyLabel} studyMeta={studyMeta} />
        <DashboardNav />

        <Section1Enrollment />
        <Section2CountrySite />
        <Section3Disposition />
        <Section4SiteActivation />
        <Section5VisitCompliance />
        <Section5bPatientVisit />
        <Section6Queries />
        <Section7Deviations />
        <Section8Milestones />
        <Section10MyInsights />
        <Section9Portfolio />

        <footer className="page-footer">
          <p>CTRLM Module 5 · CTMS Operational Dashboards</p>
        </footer>
      </div>

      {/* Floating AI assistant — anchored to viewport, not the .page wrapper. */}
      <AIAssistantDrawer />
    </div>
    </SelectedStudyProvider>
  )
}

export default MockupDashboard
