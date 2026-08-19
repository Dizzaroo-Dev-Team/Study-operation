import React, { useEffect, useState } from 'react'
import { fetchFactorsByScope, fetchFactors, patchFactor } from './services/budgeting.api'
import type { ScopedFactor } from './services/budgeting.api'
import { btn, input, badge } from './ui'

type Props =
  | { scope: 'TRIAL'; trialId: string; countryCode?: never; siteId?: never }
  | { scope: 'COUNTRY'; trialId: string; countryCode: string; siteId?: never }
  | { scope: 'SITE'; trialId: string; countryCode?: never; siteId: string }

export const FactorSelector: React.FC<Props> = ({ scope, trialId, countryCode, siteId }) => {
  const [factors, setFactors] = useState<ScopedFactor[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)

    const load = async () => {
      try {
        if (scope === 'TRIAL') {
          const raw = await fetchFactors(trialId)
          if (!cancelled) setFactors(raw)
        } else {
          const raw = await fetchFactorsByScope(scope)
          if (!cancelled) {
            if (scope === 'COUNTRY' && countryCode) {
              setFactors(raw.filter((f) => f.country_code === countryCode))
            } else if (scope === 'SITE' && siteId) {
              setFactors(raw.filter((f) => f.site_id === siteId))
            } else {
              setFactors(raw)
            }
          }
        }
      } catch (err: unknown) {
        // Surface the failure instead of silently rendering an empty list — a
        // hidden 401/404/500 from this endpoint is what produced the prod-only
        // "No trial-level factors configured." empty state.
        const status = (err as { response?: { status?: number } })?.response?.status
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        const message = (err as { message?: string })?.message ?? 'unknown error'
        console.error('[FactorSelector] failed to load factors', { scope, trialId, status, detail, err })
        if (!cancelled) {
          setLoadError(
            status
              ? `Could not load factors (HTTP ${status}${detail ? `: ${detail}` : ''}).`
              : `Could not load factors (${message}).`,
          )
          setFactors([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [scope, trialId, countryCode, siteId])

  const startEdit = (f: ScopedFactor) => {
    setEditingId(f.id)
    setEditValue(f.value)
  }

  const saveEdit = async (id: string) => {
    setSaving(true)
    try {
      await patchFactor(id, { value: editValue })
      setFactors((prev) => prev.map((f) => (f.id === id ? { ...f, value: editValue } : f)))
      setEditingId(null)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return (
    <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
      <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
      </svg>
      Loading factors…
    </div>
  )

  if (loadError) return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-6 text-sm text-rose-700">
      <p className="font-medium">Factors failed to load.</p>
      <p className="mt-1 text-xs text-rose-600">{loadError}</p>
      <p className="mt-2 text-xs text-rose-500">Check the browser DevTools Network tab and the backend logs.</p>
    </div>
  )

  if (factors.length === 0) return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">
      {scope === 'TRIAL' ? 'No trial-level factors configured.' : `No ${scope.toLowerCase()} factors found.`}
    </div>
  )

  return (
    <div className="space-y-2">
      {factors.map((f) => {
        const val = parseFloat(f.value)
        const isAbove = val > 1
        const isBelow = val < 1
        return (
          <div key={f.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 hover:border-slate-300 transition-colors">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-800 truncate">
                {f.label ?? f.factor_type.name}
              </p>
              {f.country_code && (
                <p className="text-xs text-slate-400 font-mono mt-0.5">{f.country_code}</p>
              )}
            </div>
            {editingId === f.id ? (
              <div className="flex items-center gap-2 shrink-0 ml-3">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  className={`${input.sm} w-24`}
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  autoFocus
                />
                <button onClick={() => saveEdit(f.id)} disabled={saving} className={btn.iconSuccess} title="Save">
                  {saving ? (
                    <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                  ) : (
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
                <button onClick={() => setEditingId(null)} className={btn.icon} title="Cancel">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 shrink-0 ml-3">
                <span className={isAbove ? badge.warn : isBelow ? badge.info : badge.neutral}>
                  ×{val.toFixed(2)}
                </span>
                <button onClick={() => startEdit(f)} className={btn.icon} title="Edit factor">
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
