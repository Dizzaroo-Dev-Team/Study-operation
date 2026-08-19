import React, { useEffect, useState } from 'react'
import { fetchElements } from './services/budgeting.api'
import type { CostElementRow } from './services/budgeting.api'
import { badge, table as t } from './ui'

type Props = {
  studyId?: string | null
}

const COST_VARIABILITY_STYLE: Record<string, string> = {
  FIXED: badge.info,
  VARIABLE: badge.warn,
}

export const CostElementsList: React.FC<Props> = () => {
  const [elements, setElements] = useState<CostElementRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchElements()
      .then((data) => { if (!cancelled) setElements(data.filter((el) => el.is_active !== false)) })
      .catch(() => { if (!cancelled) setError('Failed to load cost elements') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  if (loading) return (
    <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
      <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
      </svg>
      Loading elements…
    </div>
  )
  if (error) return <p className="text-sm text-red-500 py-2">{error}</p>
  if (elements.length === 0) return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">
      No cost elements found.
    </div>
  )

  return (
    <div className={t.wrap}>
      <table className={t.base}>
        <thead className={t.thead}>
          <tr>
            <th className={t.th}>Code</th>
            <th className={t.th}>Name</th>
            <th className={t.th}>Category</th>
            <th className={t.th}>Subcategory</th>
            <th className={t.th}>Payment Type</th>
            <th className={t.th}>Cost Type</th>
            <th className={t.th}>Unit</th>
            <th className={t.thCenter}>Pass-Thru</th>
            <th className={t.thRight}>Base Cost</th>
          </tr>
        </thead>
        <tbody>
          {elements.map((el) => (
            <tr key={el.id} className={t.row}>
              <td className={`${t.td} font-mono text-xs text-slate-500`}>{el.code}</td>
              <td className={`${t.td} font-medium text-slate-800`}>{el.name}</td>
              <td className={t.td}>
                {el.category ? (
                  <span className={badge.info}>{el.category}</span>
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </td>
              <td className={t.td}>
                {el.subcategory ? (
                  <span className="text-slate-700">{el.subcategory}</span>
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </td>
              <td className={t.td}>
                {el.unit ? (
                  <span className="text-slate-700">{el.unit}</span>
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </td>
              <td className={t.td}>
                {el.cost_variability ? (
                  <span className={COST_VARIABILITY_STYLE[el.cost_variability] ?? badge.neutral}>
                    {el.cost_variability}
                  </span>
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </td>
              <td className={t.td}>
                {el.unit_label ? (
                  <span className="text-slate-700">{el.unit_label}</span>
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </td>
              <td className={t.tdCenter}>
                {el.pass_thru === 'Y' ? (
                  <span className={badge.success}>Yes</span>
                ) : el.pass_thru === 'N' ? (
                  <span className={badge.neutral}>No</span>
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </td>
              <td className={t.tdRight}>
                {el.latest_version
                  ? `${el.latest_version.reference_currency} ${parseFloat(el.latest_version.base_unit_cost).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                  : <span className="text-slate-300">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
