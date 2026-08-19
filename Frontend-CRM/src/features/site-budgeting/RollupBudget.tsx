import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchRollupBudget } from './services/budgeting.api'
import type { RollupBudgetRow } from './services/budgeting.api'
import { btn, table as t, emptyState } from './ui'

type Props = {
  trialId: string
}

function fmtMoney(v: string | number): string {
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export const RollupBudget: React.FC<Props> = ({ trialId }) => {
  const [rows, setRows] = useState<RollupBudgetRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!trialId) {
      setLoading(false)
      setRows([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await fetchRollupBudget(trialId)
      setRows(data)
    } catch (e: any) {
      const status = e?.response?.status ?? 0
      if (status === 0 || status >= 500) setError('Could not load rollup budget.')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [trialId])

  useEffect(() => {
    load()
  }, [load])

  const grandTotal = useMemo(
    () =>
      rows.reduce((sum, r) => {
        const n = Number(r.total_cost)
        return Number.isFinite(n) ? sum + n : sum
      }, 0),
    [rows],
  )

  if (loading) {
    return <div className={emptyState}>Loading rollup…</div>
  }

  if (rows.length === 0) {
    return (
      <div className={emptyState}>
        <div>No sites under this study yet.</div>
        <div className="text-xs">Add sites in Study Setup → Site Setup first.</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-500">
          Total = (variable × planned patients) + fixed, per site. Variable =
          per-patient sum of cost-element line totals from the country budget.
          Fixed = milestone total (with ancestor chain).
        </div>
        <button className={btn.secondarySm} onClick={load}>
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className={t.wrap}>
        <table className={t.base}>
          <thead className={t.thead}>
            <tr>
              <th className={t.th}>Site</th>
              <th className={t.th}>Country</th>
              <th className={t.thRight}># Patients</th>
              <th className={t.thRight}>Variable cost</th>
              <th className={t.thRight}>Fixed cost</th>
              <th className={t.thRight}>Total cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.site_id} className={t.row}>
                <td className={t.td}>
                  <div className="font-medium text-slate-800">{r.site_name}</div>
                  {r.site_code && (
                    <div className="text-xs text-slate-400 font-mono">{r.site_code}</div>
                  )}
                </td>
                <td className={t.td}>{r.country_code ?? <span className="text-slate-400">—</span>}</td>
                <td className={t.tdRight}>{r.planned_patients}</td>
                <td className={t.tdRight}>{fmtMoney(r.variable_cost)}</td>
                <td className={t.tdRight}>{fmtMoney(r.fixed_cost)}</td>
                <td className={`${t.tdRight} font-semibold text-slate-900`}>
                  {fmtMoney(r.total_cost)}
                </td>
              </tr>
            ))}
            <tr className="border-t-2 border-slate-300 bg-slate-50">
              <td className={`${t.td} font-semibold`} colSpan={5}>
                Grand total
              </td>
              <td className={`${t.tdRight} font-bold text-slate-900`}>
                {fmtMoney(grandTotal)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
