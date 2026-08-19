import React, { useCallback, useEffect, useState } from 'react'
import {
  deleteMilestone,
  fetchFxRate,
  fetchMilestones,
  generateMilestones,
  patchMilestone,
} from './services/budgeting.api'
import { badge, btn, input, table as t } from './ui'
import { currencyForCountry } from './country_currency'

type Row = {
  id: string
  name: string
  unit_cost: string
  quantity: string
  payment_trigger?: string | null
  sort_order: number
  country_code?: string | null
  scope?: 'universal' | 'country'
}

type Props = {
  templateId: string
  onChanged: () => void
  // Read-only flag: applied to row edit/delete actions only.
  // The Generate button is shown at TRIAL and COUNTRY (both can regenerate),
  // hidden at SITE — we use `level` to decide.
  readOnly?: boolean
  level?: 'TRIAL' | 'COUNTRY' | 'SITE'
  countryCode?: string | null
}

function rowTotal(r: Row): number {
  const a = parseFloat(r.unit_cost) || 0
  const q = parseFloat(r.quantity) || 1
  return a * q
}

function fmtQty(s: string | undefined | null): string {
  const n = parseFloat(s ?? '1')
  if (!Number.isFinite(n)) return '1'
  return Number.isInteger(n) ? n.toString() : n.toFixed(2)
}

export const Milestones: React.FC<Props> = ({
  templateId,
  onChanged,
  readOnly = false,
  level,
  countryCode = null,
}) => {
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [genResult, setGenResult] = useState<string | null>(null)

  // Currency: USD at TRIAL; country's local currency at COUNTRY/SITE.
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

  const fmtMoney = (n: number): string => {
    if (!Number.isFinite(n)) return '—'
    const value = (n * fxRate).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    return showLocal ? `${localCurrency} ${value}` : `$${value}`
  }

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editUnitCost, setEditUnitCost] = useState('')
  const [editQty, setEditQty] = useState('1')
  const [editTrigger, setEditTrigger] = useState('')

  const load = useCallback(async () => {
    if (!templateId) {
      setLoading(false)
      setRows([])
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const data = await fetchMilestones(templateId)
      setRows(data as Row[])
    } catch (e: any) {
      const status = e?.response?.status ?? 0
      if (status === 0 || status >= 500) setLoadError('Could not load milestones.')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => { void load() }, [load])

  const generate = async () => {
    setGenerating(true)
    setGenError(null)
    setGenResult(null)
    try {
      const r = await generateMilestones(templateId)
      const cc = Object.keys(r.by_country)[0]
      if (r.universal > 0) {
        setGenResult(`Added ${r.universal} universal milestone${r.universal !== 1 ? 's' : ''} from the cost catalog.`)
      } else if (cc) {
        setGenResult(`Added ${r.by_country[cc]} ${cc} milestone${r.by_country[cc] !== 1 ? 's' : ''} from policy docs.`)
      } else {
        setGenResult('No milestones generated.')
      }
      await load()
      onChanged()
    } catch (e: any) {
      setGenError(e?.response?.data?.detail ?? e?.message ?? 'Generation failed.')
    } finally {
      setGenerating(false)
    }
  }

  const startEdit = (r: Row) => {
    setEditingId(r.id)
    setEditName(r.name)
    setEditUnitCost(r.unit_cost)
    setEditQty(r.quantity ?? '1')
    setEditTrigger(r.payment_trigger ?? '')
  }

  const saveEdit = async (id: string) => {
    setSaving(true)
    try {
      await patchMilestone(templateId, id, {
        name: editName.trim() || undefined,
        unit_cost: editUnitCost.trim() || undefined,
        quantity: editQty.trim() || undefined,
        payment_trigger: editTrigger.trim() || null,
      })
      setEditingId(null)
      await load()
      onChanged()
    } finally {
      setSaving(false)
    }
  }

  const remove = async (id: string) => {
    setSaving(true)
    try {
      await deleteMilestone(templateId, id)
      await load()
      onChanged()
    } finally {
      setSaving(false)
    }
  }

  const milestoneTotal = rows.reduce((s, r) => s + rowTotal(r), 0)

  // Generate button visible at TRIAL + COUNTRY (it regenerates the scope-appropriate rows).
  // Hidden at SITE because milestones inherit from country and re-running has no effect.
  const showGenerate = level !== 'SITE'
  const generateLabel = level === 'COUNTRY'
    ? 'Generate from Country Policy Docs'
    : 'Generate from Cost Catalog'

  return (
    <div className="space-y-5">
      {showGenerate && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[260px]">
            <p className="text-sm font-semibold text-slate-800">
              {level === 'COUNTRY'
                ? 'Generate country-specific milestones'
                : 'Generate universal study milestones'}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              {level === 'COUNTRY'
                ? 'Reads every policy document uploaded for this country (Study → Budget Configuration → Policy Docs) and lets the LLM extract milestones. Re-running replaces this country’s rows.'
                : 'LLM picks the universal milestones from the cost element catalog. Re-running replaces existing universals.'}
            </p>
            {genResult && <p className="text-xs text-emerald-700 mt-1">{genResult}</p>}
            {genError && <p className="text-xs text-red-600 mt-1">{genError}</p>}
          </div>
          <button
            type="button"
            onClick={() => void generate()}
            disabled={generating}
            className={btn.primary}
          >
            {generating ? (
              <>
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
                Generating…
              </>
            ) : (
              generateLabel
            )}
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500 py-4">
          <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          Loading milestones…
        </div>
      ) : loadError ? (
        <p className="text-sm text-red-600">{loadError}</p>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">
          No milestones yet. {showGenerate ? 'Click Generate above to create them.' : ''}
        </div>
      ) : (
        <div className={t.wrap}>
          <table className={t.base}>
            <thead className={t.thead}>
              <tr>
                <th className={t.th}>Milestone</th>
                <th className={t.th}>Scope</th>
                <th className={t.th}>Payment Trigger</th>
                <th className={t.thRight}>Unit Cost</th>
                <th className={t.thCenter}>Qty</th>
                <th className={t.thRight}>Total</th>
                <th className={t.th} />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                // Only rows that live on THIS template are editable from THIS view.
                // At TRIAL: editable iff country_code is null (universals).
                // At COUNTRY: editable iff country_code is non-null (country-specific rows
                //             stored on this country template; universals are inherited
                //             from TRIAL and must be edited there).
                const rowEditable = !readOnly && (
                  (level === 'TRIAL' && !r.country_code) ||
                  (level === 'COUNTRY' && !!r.country_code)
                )
                return editingId === r.id ? (
                  <tr key={r.id} className="bg-amber-50 border-t border-slate-100">
                    <td className="px-3 py-2">
                      <input className={input.sm} value={editName} onChange={(e) => setEditName(e.target.value)} />
                    </td>
                    <td className="px-3 py-2">
                      <span className={r.country_code ? badge.info : badge.neutral}>
                        {r.country_code ?? 'Universal'}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <input className={input.sm} value={editTrigger} onChange={(e) => setEditTrigger(e.target.value)} placeholder="Trigger" />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <input
                        className={`${input.sm} w-28 text-right`}
                        type="number"
                        step="0.01"
                        value={editUnitCost}
                        onChange={(e) => setEditUnitCost(e.target.value)}
                      />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <input
                        className={`${input.sm} w-16 text-center`}
                        type="number"
                        step="1"
                        min="1"
                        value={editQty}
                        onChange={(e) => setEditQty(e.target.value)}
                      />
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-700">
                      {fmtMoney((parseFloat(editUnitCost) || 0) * (parseFloat(editQty) || 1))}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1 justify-end">
                        <button type="button" disabled={saving} onClick={() => void saveEdit(r.id)} className={btn.primarySm}>
                          {saving ? '…' : 'Save'}
                        </button>
                        <button type="button" onClick={() => setEditingId(null)} className={btn.secondarySm}>
                          Cancel
                        </button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  <tr key={r.id} className={t.row}>
                    <td className={`${t.td} font-medium text-slate-800`}>{r.name}</td>
                    <td className={t.td}>
                      <span className={r.country_code ? badge.info : badge.neutral}>
                        {r.country_code ?? 'Universal'}
                      </span>
                    </td>
                    <td className={t.td}>
                      {r.payment_trigger ? (
                        <span className={badge.warn}>{r.payment_trigger}</span>
                      ) : <span className="text-slate-300 text-xs">—</span>}
                    </td>
                    <td className={t.tdRight}>{fmtMoney(parseFloat(r.unit_cost) || 0)}</td>
                    <td className={t.tdCenter}>{fmtQty(r.quantity)}</td>
                    <td className={`${t.tdRight} font-semibold text-slate-800`}>{fmtMoney(rowTotal(r))}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1 justify-end">
                        {rowEditable && (
                          <>
                            <button type="button" onClick={() => startEdit(r)} className={btn.icon} title="Edit">
                              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                              </svg>
                            </button>
                            <button type="button" disabled={saving} onClick={() => void remove(r.id)} className={btn.iconDanger} title="Delete">
                              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22" />
                              </svg>
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr className="border-t-2 border-slate-200 bg-slate-50">
                  <td colSpan={5} className="px-3 py-2.5 text-sm font-semibold text-slate-700 text-right">Milestone total</td>
                  <td className="px-3 py-2.5 text-right font-mono font-bold text-slate-900">{fmtMoney(milestoneTotal)}</td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </div>
  )
}
