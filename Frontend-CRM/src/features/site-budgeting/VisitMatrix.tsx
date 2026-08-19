import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { createVisit, deleteVisit, fetchFxRate, fetchVisitMatrixResolved, patchVisitMatrix, resetTrialBudget, resolveTemplate } from './services/budgeting.api'
import type { ResolvedBudgetLine } from './services/budgeting.api'
import { btn, input, table as t } from './ui'
import { currencyForCountry } from './country_currency'

type Visit = { id: string; visit_code?: string | null; visit_name: string; visit_order: number }
type Cell = { id: string; budget_line_item_id: string; visit_schedule_id: string; units: string }

type LineRow = {
  line_item_id?: string | null
  code?: string | null
  name?: string | null
  category?: string | null
  sort_order?: number
  unit_cost?: string | null
  unit_cost_computed?: string | null
  factored_unit_cost?: string | null
  is_excluded?: boolean
  is_policy_included?: boolean
}

type Props = {
  templateId: string
  // Optional; if omitted the component fetches its own resolved lines.
  lines?: LineRow[]
  onChanged: () => void
  readOnly?: boolean
  level?: 'TRIAL' | 'COUNTRY' | 'SITE'
  countryCode?: string | null
}

function displayCost(line: LineRow): string | null {
  return line.unit_cost_computed ?? line.factored_unit_cost ?? line.unit_cost ?? null
}

// Visit cells store Numeric(10,4) → "1.0000". Display as a clean integer when whole,
// otherwise trim to 2 decimals.
function fmtUnits(s: string): string {
  const n = parseFloat(s)
  if (!Number.isFinite(n)) return s
  return Number.isInteger(n) ? n.toString() : n.toFixed(2)
}

export const VisitMatrix: React.FC<Props> = ({
  templateId,
  lines: linesProp,
  onChanged,
  readOnly = false,
  level = 'TRIAL',
  countryCode = null,
}) => {
  const [visits, setVisits] = useState<Visit[]>([])
  const [cells, setCells] = useState<Cell[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [fetchedLines, setFetchedLines] = useState<ResolvedBudgetLine[]>([])

  // Currency: USD at TRIAL; the country's local currency at COUNTRY/SITE.
  const showLocal = level !== 'TRIAL' && !!countryCode
  const localCurrency = showLocal ? currencyForCountry(countryCode) : 'USD'
  const [fxRate, setFxRate] = useState<number>(1)

  useEffect(() => {
    if (!showLocal) { setFxRate(1); return }
    let cancelled = false
    fetchFxRate(localCurrency)
      .then((r) => { if (!cancelled) setFxRate(parseFloat(r) || 1) })
      .catch(() => { if (!cancelled) setFxRate(1) })
    return () => { cancelled = true }
  }, [showLocal, localCurrency])

  // Render helpers — money is shown in localCurrency at COUNTRY/SITE, USD at TRIAL.
  const fmtMoneyDisplay = (n: number, decimals = 2): string => {
    if (!Number.isFinite(n)) return '—'
    const value = (n * fxRate).toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
    return showLocal ? `${localCurrency} ${value}` : `$${value}`
  }
  const fmtCellMoney = (s: string | null | undefined): string => {
    if (s == null || s === '') return '—'
    const n = parseFloat(s)
    if (!Number.isFinite(n)) return '—'
    return fmtMoneyDisplay(n, 2)
  }

  // If parent didn't pass lines, fetch them ourselves.
  useEffect(() => {
    if (linesProp !== undefined) return
    if (!templateId) { setFetchedLines([]); return }
    let cancelled = false
    resolveTemplate(templateId)
      .then((data: any) => {
        if (cancelled) return
        const resolved: ResolvedBudgetLine[] = Array.isArray(data) ? data : (data?.lines ?? [])
        setFetchedLines(resolved)
      })
      .catch(() => { if (!cancelled) setFetchedLines([]) })
    return () => { cancelled = true }
  }, [templateId, linesProp])

  const lines: LineRow[] = linesProp ?? fetchedLines

  const [newVisitName, setNewVisitName] = useState('')
  const [newVisitCode, setNewVisitCode] = useState('')
  const [addingVisit, setAddingVisit] = useState(false)
  const [visitErr, setVisitErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!templateId) {
      setLoading(false)
      setVisits([])
      setCells([])
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const data = await fetchVisitMatrixResolved(templateId)
      setVisits(data.visits || [])
      setCells(
        (data.cells || []).map((c) => ({
          id: `${c.budget_line_item_id}|${c.visit_schedule_id}`,
          budget_line_item_id: c.budget_line_item_id,
          visit_schedule_id: c.visit_schedule_id,
          units: c.units,
        }))
      )
    } catch (e: any) {
      // 404 / missing template → render the empty state below, not a red error.
      // Surface an actual error banner only for genuine non-404 failures.
      const status = e?.response?.status ?? 0
      if (status === 0 || status >= 500) {
        setLoadError('Could not load visit matrix.')
      }
      setVisits([])
      setCells([])
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => { void load() }, [load])

  const cellMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of cells) {
      m.set(`${c.budget_line_item_id}|${c.visit_schedule_id}`, c.units)
    }
    return m
  }, [cells])

  const sortedVisits = useMemo(
    () => [...visits].sort((a, b) => a.visit_order - b.visit_order),
    [visits]
  )

  const matrixLines = useMemo(() => lines.filter((l) => Boolean(l.line_item_id)), [lines])

  const visitTotals = useMemo(() => {
    const totals: Record<string, number> = {}
    for (const v of sortedVisits) {
      let total = 0
      for (const line of matrixLines) {
        const key = `${line.line_item_id}|${v.id}`
        const units = parseFloat(cellMap.get(key) ?? '0') || 0
        const cost = parseFloat(displayCost(line) ?? '0') || 0
        total += units * cost
      }
      totals[v.id] = total
    }
    return totals
  }, [sortedVisits, matrixLines, cellMap])

  const maxVisitTotal = useMemo(
    () => Math.max(...Object.values(visitTotals), 1),
    [visitTotals]
  )

  const addVisit = async () => {
    if (!newVisitName.trim()) return
    setAddingVisit(true); setVisitErr(null)
    try {
      await createVisit(templateId, {
        visit_name: newVisitName.trim(),
        visit_code: newVisitCode.trim() || undefined,
        visit_order: visits.length + 1,
      })
      setNewVisitName(''); setNewVisitCode('')
      await load()
      onChanged()
    } catch { setVisitErr('Could not add visit.') }
    finally { setAddingVisit(false) }
  }

  const removeVisit = async (visitId: string) => {
    setSaving(true)
    try { await deleteVisit(templateId, visitId); await load(); onChanged() }
    finally { setSaving(false) }
  }

  const updateCell = async (lineId: string, visitId: string, units: string) => {
    setSaving(true)
    try {
      await patchVisitMatrix(templateId, [
        { budget_line_item_id: lineId, visit_schedule_id: visitId, units },
      ])
      await load()
      onChanged()
    } finally {
      setSaving(false)
    }
  }

  const [clearing, setClearing] = useState(false)
  const clearAll = async () => {
    if (!confirm(
      'Clear ALL budget data for this trial?\n\n' +
      'This will delete every visit, line item, milestone, note, country/site template ' +
      'and policy document for this trial. The Study template itself is kept so you can ' +
      'reimport SOA. This is for testing — cannot be undone.'
    )) return
    setClearing(true)
    try {
      await resetTrialBudget(templateId)
      await load()
      onChanged()
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? 'Clear failed')
    } finally {
      setClearing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500 py-6">
        <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
        Loading visit matrix…
      </div>
    )
  }

  if (loadError) {
    return <p className="text-sm text-red-600 py-2">{loadError}</p>
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Enter the number of times each procedure occurs at each visit (0 = not performed).
        The footer row shows estimated cost per visit based on current unit costs.
      </p>

      {!readOnly && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm font-semibold text-slate-700 mb-3">Add visit column</p>
          <div className="flex flex-wrap gap-2 items-center">
            <input
              className={`${input.base} flex-1 min-w-[160px]`}
              placeholder="Visit name (e.g. Screening)"
              value={newVisitName}
              onChange={(e) => setNewVisitName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void addVisit()}
            />
            <input
              className={`${input.base} w-32`}
              placeholder="Code (e.g. SCR)"
              value={newVisitCode}
              onChange={(e) => setNewVisitCode(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void addVisit()}
            />
            <button
              type="button"
              disabled={addingVisit || !newVisitName.trim()}
              onClick={() => void addVisit()}
              className={btn.primary}
            >
              {addingVisit ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Adding
                </>
              ) : (
                <>+ Add visit</>
              )}
            </button>
            <button
              type="button"
              disabled={clearing}
              onClick={() => void clearAll()}
              className="inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 active:bg-red-200 transition-colors disabled:opacity-40"
              title="Wipe all budget data for this trial — testing only"
            >
              {clearing ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Clearing
                </>
              ) : (
                <>
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22" />
                  </svg>
                  Clear all (testing)
                </>
              )}
            </button>
          </div>
          {visitErr && <p className="text-xs text-red-600 mt-2">{visitErr}</p>}
        </div>
      )}

      {(visits.length === 0 || matrixLines.length === 0) ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {visits.length === 0
            ? 'No visits yet — add visits above.'
            : 'No cost elements in budget — add line items in Budget Configuration first.'}
        </div>
      ) : (
        <div
          className="rounded-lg border border-slate-200 bg-white overflow-auto"
          style={{ maxHeight: 'calc(100vh - 280px)' }}
        >
            <table className="text-sm border-collapse" style={{ minWidth: `${240 + sortedVisits.length * 96}px` }}>
              <thead className={t.thead}>
                <tr>
                  <th
                    className={`${t.th} bg-slate-50 border-r border-slate-200`}
                    style={{ position: 'sticky', left: 0, top: 0, zIndex: 4, minWidth: 220 }}
                  >
                    Element
                  </th>
                  <th
                    className={`${t.thRight} bg-slate-50 border-r border-slate-100`}
                    style={{ position: 'sticky', top: 0, zIndex: 3, minWidth: 96 }}
                  >
                    Unit cost
                  </th>
                  {sortedVisits.map((v) => (
                    <th
                      key={v.id}
                      className="px-2 py-2.5 text-center font-semibold text-slate-600 text-[11px] whitespace-nowrap bg-slate-50"
                      style={{ position: 'sticky', top: 0, zIndex: 3, minWidth: 88 }}
                    >
                      <div className="flex flex-col items-center gap-0.5">
                        <span className="uppercase tracking-wide">{v.visit_code || v.visit_name}</span>
                        {v.visit_code && (
                          <span className="text-[10px] text-slate-400 font-normal normal-case truncate max-w-[80px]">{v.visit_name}</span>
                        )}
                        {!readOnly && (
                          <button
                            type="button"
                            disabled={saving}
                            onClick={() => void removeVisit(v.id)}
                            className="text-[10px] text-slate-300 hover:text-red-500 leading-none mt-0.5 disabled:opacity-40 transition-colors"
                            title="Remove visit"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    </th>
                  ))}
                  <th
                    className={`${t.thRight} bg-slate-50 border-l border-slate-100`}
                    style={{ position: 'sticky', top: 0, zIndex: 3, minWidth: 96 }}
                  >
                    Per patient
                  </th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  // Render section header rows whenever the SOA section (= cost element category)
                  // changes between consecutive rows. Backend returns lines pre-sorted by sort_order
                  // so SOA-insertion order is preserved.
                  let prevSection: string | null = null
                  const totalCols = 2 + sortedVisits.length + 1 // element + unit-cost + visits + per-patient
                  const rows: React.ReactElement[] = []
                  matrixLines.forEach((line) => {
                    const section = (line.category ?? '').trim()
                    if (section && section !== prevSection) {
                      rows.push(
                        <tr key={`__section__${section}`} className="bg-slate-100 border-t border-slate-200">
                          <td
                            colSpan={totalCols}
                            className="px-0 py-0 bg-slate-100"
                          >
                            {/* Inner sticky div keeps the label glued to the left edge of the
                                viewport when the user scrolls horizontally, so the user never
                                loses context for which section they're in. */}
                            <div
                              className="px-3 py-2 text-xs font-bold text-slate-700 uppercase tracking-wide bg-slate-100"
                              style={{ position: 'sticky', left: 0, display: 'inline-block' }}
                            >
                              {section}
                            </div>
                          </td>
                        </tr>
                      )
                      prevSection = section
                    }
                    const excluded = !!line.is_excluded
                    const policyIncluded = !!line.is_policy_included && !excluded
                    const cost = excluded ? 0 : (parseFloat(displayCost(line) ?? '0') || 0)
                    const perPatient = excluded ? 0 : sortedVisits.reduce((s, v) => {
                      const units = parseFloat(cellMap.get(`${line.line_item_id}|${v.id}`) ?? '0') || 0
                      return s + units * cost
                    }, 0)
                    const rowCls = excluded
                      ? 'border-t border-red-100 bg-red-50/60 hover:bg-red-50 transition-colors'
                      : policyIncluded
                      ? 'border-t border-emerald-100 bg-emerald-50/60 hover:bg-emerald-50 transition-colors'
                      : t.row
                    const stickyBg = excluded ? 'bg-red-50' : policyIncluded ? 'bg-emerald-50' : 'bg-white'
                    rows.push(
                      <tr key={line.line_item_id!} className={rowCls}>
                        <td
                          className={`px-3 py-2.5 ${stickyBg} border-r border-slate-100`}
                          style={{ position: 'sticky', left: 0, zIndex: 1 }}
                        >
                          <div className={`text-sm truncate max-w-[260px] ${excluded ? 'font-medium text-red-700 line-through' : policyIncluded ? 'font-medium text-emerald-800' : 'font-medium text-slate-800'}`}>
                            {line.name || line.code}
                          </div>
                          {excluded && (
                            <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-red-600 uppercase tracking-wide">
                              ✕ Not charged
                            </div>
                          )}
                          {policyIncluded && (
                            <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 uppercase tracking-wide">
                              ✓ Mandated by policy
                            </div>
                          )}
                        </td>
                        <td className={`px-3 py-2.5 text-right font-mono text-sm border-r border-slate-50 ${excluded ? 'text-red-400 line-through' : 'text-slate-600'}`}>
                          {fmtCellMoney(displayCost(line))}
                        </td>
                        {sortedVisits.map((v) => {
                          const key = `${line.line_item_id}|${v.id}`
                          const val = cellMap.get(key) ?? '0'
                          const display = excluded ? '0' : fmtUnits(val)
                          const hasValue = !excluded && parseFloat(val) > 0
                          return (
                            <td key={v.id} className="px-1.5 py-1.5 text-center">
                              <input
                                key={`${key}-${val}-${excluded ? 'x' : 'o'}`}
                                className={excluded ? `${input.cell} text-red-400 line-through bg-red-50/40` : (hasValue ? input.cellFilled : input.cell)}
                                defaultValue={display}
                                disabled={saving || readOnly || excluded}
                                onBlur={(e) => {
                                  if (readOnly || excluded) return
                                  const n = e.target.value.trim() || '0'
                                  if (n !== display) void updateCell(line.line_item_id!, v.id, n)
                                }}
                              />
                            </td>
                          )
                        })}
                        <td className={`px-3 py-2.5 text-right font-mono font-semibold border-l border-slate-100 ${excluded ? 'text-red-400 line-through' : 'text-slate-800'}`}>
                          {excluded ? '—' : (perPatient > 0 ? fmtMoneyDisplay(perPatient, 2) : '—')}
                        </td>
                      </tr>
                    )
                  })
                  return rows
                })()}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-slate-300 bg-slate-50">
                  <td
                    className="px-3 py-2.5 font-semibold text-slate-700 text-xs uppercase tracking-wide bg-slate-50 border-r border-slate-200"
                    style={{ position: 'sticky', left: 0 }}
                  >
                    Visit cost
                  </td>
                  <td className="border-r border-slate-100" />
                  {sortedVisits.map((v) => {
                    const total = visitTotals[v.id] ?? 0
                    const barPct = maxVisitTotal > 0 ? (total / maxVisitTotal) * 100 : 0
                    return (
                      <td key={v.id} className="px-2 py-2.5 text-center">
                        <div className="font-mono text-xs text-slate-700 font-semibold">
                          {total > 0 ? fmtMoneyDisplay(total, 0) : '—'}
                        </div>
                        <div className="mx-auto mt-1 h-1 rounded-full bg-slate-200" style={{ width: 64 }}>
                          <div
                            className="h-1 rounded-full bg-indigo-500 transition-all"
                            style={{ width: `${barPct}%` }}
                          />
                        </div>
                      </td>
                    )
                  })}
                  <td className="px-3 py-2.5 text-right font-mono font-bold text-slate-900 border-l border-slate-100">
                    {fmtMoneyDisplay(Object.values(visitTotals).reduce((s, total) => s + total, 0), 2)}
                  </td>
                </tr>
              </tfoot>
            </table>
        </div>
      )}
    </div>
  )
}
