import React, { useEffect, useState } from 'react'
import { fetchFxRate, resolveTemplate } from './services/budgeting.api'
import type { ResolvedBudgetLine } from './services/budgeting.api'
import { badge, table as t } from './ui'
import { currencyForCountry } from './country_currency'

type Props = {
  templateId: string
  level: 'TRIAL' | 'COUNTRY' | 'SITE'
  countryCode?: string | null
}

export const ElementsResolved: React.FC<Props> = ({ templateId, level, countryCode }) => {
  const [lines, setLines] = useState<ResolvedBudgetLine[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fxRate, setFxRate] = useState<number>(1)

  const localCurrency = currencyForCountry(countryCode)
  const showLocal = level !== 'TRIAL' && !!countryCode

  useEffect(() => {
    if (!templateId) { setLoading(false); setLines([]); return }
    let cancelled = false
    setLoading(true)
    setError(null)
    resolveTemplate(templateId)
      .then((data: any) => {
        if (cancelled) return
        const resolved: ResolvedBudgetLine[] = Array.isArray(data) ? data : (data?.lines ?? [])
        setLines(resolved)
      })
      .catch((e: any) => {
        if (cancelled) return
        const status = e?.response?.status ?? 0
        if (status === 0 || status >= 500) setError('Failed to load line items')
        setLines([])
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [templateId])

  useEffect(() => {
    if (!showLocal) {
      setFxRate(1)
      return
    }
    let cancelled = false
    fetchFxRate(localCurrency)
      .then((r) => { if (!cancelled) setFxRate(parseFloat(r) || 1) })
      .catch(() => { if (!cancelled) setFxRate(1) })
    return () => { cancelled = true }
  }, [showLocal, localCurrency])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
        <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
        Loading elements…
      </div>
    )
  }

  if (error) {
    return <p className="text-sm text-red-600 py-2">{error}</p>
  }

  if (lines.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center text-sm text-slate-400">
        No line items. Generate a visit matrix from SOA Import to populate elements.
      </div>
    )
  }

  const total = lines.reduce((sum, l) => {
    const v = parseFloat(l.factored_unit_cost ?? l.unit_cost_computed ?? l.unit_cost ?? '0') || 0
    return sum + v
  }, 0)
  const totalLocal = total * fxRate

  return (
    <div className="space-y-3">
      <div className={t.wrap}>
        <table className={t.base}>
          <thead className={t.thead}>
            <tr>
              <th className={t.th}>Element</th>
              <th className={t.thRight}>Unit Cost (USD)</th>
              {showLocal && <th className={t.thRight}>Factored Cost ({localCurrency})</th>}
              <th className={t.thCenter}>Status</th>
            </tr>
          </thead>
          <tbody>
            {(() => {
              let prevSection: string | null = null
              const totalCols = 3 + (showLocal ? 1 : 0)
              const rows: React.ReactElement[] = []
              lines.forEach((l) => {
                const section = (l.category ?? '').trim()
                if (section && section !== prevSection) {
                  rows.push(
                    <tr key={`__section__${section}`} className="bg-slate-100 border-t border-slate-200">
                      <td colSpan={totalCols} className="px-3 py-2 text-xs font-bold text-slate-700 uppercase tracking-wide">
                        {section}
                      </td>
                    </tr>
                  )
                  prevSection = section
                }
                const baseUsd = parseFloat(l.unit_cost_computed ?? l.unit_cost ?? '0') || 0
                const factoredUsd = parseFloat(l.factored_unit_cost ?? l.unit_cost_computed ?? l.unit_cost ?? '0') || 0
                const factoredLocal = factoredUsd * fxRate
                const excluded = !!l.is_excluded
                const policyIncluded = !!l.is_policy_included && !excluded
                const rowCls = excluded
                  ? 'border-t border-red-100 bg-red-50/60 hover:bg-red-50 transition-colors'
                  : policyIncluded
                  ? 'border-t border-emerald-100 bg-emerald-50/60 hover:bg-emerald-50 transition-colors'
                  : t.row
                const nameCls = excluded
                  ? 'font-medium text-red-700 line-through'
                  : policyIncluded
                  ? 'font-medium text-emerald-800'
                  : 'font-medium text-slate-800'
                rows.push(
                  <tr key={l.cost_element_id} className={rowCls}>
                    <td className={t.td}>
                      <div className={nameCls}>{l.name ?? l.code ?? l.cost_element_id}</div>
                    </td>
                    <td className={`${t.tdRight} ${excluded ? 'line-through text-red-400' : ''}`}>
                      {baseUsd > 0 ? `$${baseUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : <span className="text-slate-300">—</span>}
                    </td>
                    {showLocal && (
                      <td className={`${t.tdRight} font-semibold ${excluded ? 'line-through text-red-400' : 'text-indigo-700'}`}>
                        {factoredLocal > 0 ? `${localCurrency} ${factoredLocal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : <span className="text-slate-300">—</span>}
                      </td>
                    )}
                    <td className={t.tdCenter}>
                      {excluded ? (
                        <span className={badge.danger}>Not charged in country</span>
                      ) : policyIncluded ? (
                        <span className={badge.success}>Mandated by policy</span>
                      ) : l.needs_review ? (
                        <span className={badge.warn}>Review</span>
                      ) : l.inherited_from ? (
                        <span className={badge.info}>Inherited</span>
                      ) : (
                        <span className={badge.success}>Active</span>
                      )}
                    </td>
                  </tr>
                )
              })
              return rows
            })()}
          </tbody>
        </table>
      </div>
      {total > 0 && (
        <div className="flex justify-end gap-4 text-sm">
          <span className="text-slate-500">Total factored:</span>
          <span className="font-semibold font-mono text-indigo-700">
            ${total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          {showLocal && (
            <>
              <span className="text-slate-300">·</span>
              <span className="font-semibold font-mono text-indigo-700">
                {localCurrency} {totalLocal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  )
}
