import React, { useEffect, useState } from 'react'
import {
  fetchEffectiveTemplate,
  fetchFactorsByScope,
  fetchFxRate,
  refactorBudgetFromPolicy,
} from './services/budgeting.api'
import type { BudgetTemplateRow, RefactorBudgetResult, ScopedFactor } from './services/budgeting.api'
import { BudgetConfiguration } from './BudgetConfiguration'
import { badge, btn } from './ui'
import { currencyForCountry } from './country_currency'

type Props = {
  trialId: string
  selectedCountry: string | null
  onCountryChange: (code: string) => void
}

export const CountryColumn: React.FC<Props> = ({ trialId, selectedCountry, onCountryChange }) => {
  const [template, setTemplate] = useState<BudgetTemplateRow | null>(null)
  const [loadingTpl, setLoadingTpl] = useState(false)
  const [tplError, setTplError] = useState<string | null>(null)
  const [countries, setCountries] = useState<{ code: string; label: string; factor: string }[]>([])
  const [fxRate, setFxRate] = useState<string>('1.00')

  useEffect(() => {
    fetchFactorsByScope('COUNTRY')
      .then((factors: ScopedFactor[]) => {
        const seen = new Set<string>()
        const list: { code: string; label: string; factor: string }[] = []
        for (const f of factors) {
          if (f.country_code && !seen.has(f.country_code)) {
            seen.add(f.country_code)
            list.push({ code: f.country_code, label: f.label ?? f.country_code, factor: f.value })
          }
        }
        setCountries(list.sort((a, b) => a.label.localeCompare(b.label)))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedCountry) { setTemplate(null); return }
    let cancelled = false
    setLoadingTpl(true)
    setTplError(null)
    fetchEffectiveTemplate({ trial_id: trialId, country_code: selectedCountry })
      .then((t) => { if (!cancelled) setTemplate(t as unknown as BudgetTemplateRow) })
      .catch(() => { if (!cancelled) setTplError('Failed to load country template') })
      .finally(() => { if (!cancelled) setLoadingTpl(false) })
    return () => { cancelled = true }
  }, [trialId, selectedCountry])

  const currency = currencyForCountry(selectedCountry)

  useEffect(() => {
    if (!selectedCountry) { setFxRate('1.00'); return }
    let cancelled = false
    fetchFxRate(currency)
      .then((r) => { if (!cancelled) setFxRate(r) })
      .catch(() => { if (!cancelled) setFxRate('1.00') })
    return () => { cancelled = true }
  }, [selectedCountry, currency])

  const selectedCountryRow = countries.find((c) => c.code === selectedCountry)

  // Refactor-budget action: reads policy docs for this country, asks LLM for
  // no-charge rules, applies them as line-item exclusions on the COUNTRY template.
  const [refactoring, setRefactoring] = useState(false)
  const [refactorErr, setRefactorErr] = useState<string | null>(null)
  const [refactorResult, setRefactorResult] = useState<RefactorBudgetResult | null>(null)
  const [showSummary, setShowSummary] = useState(true)
  const [refactorKey, setRefactorKey] = useState(0)

  // Clear the inline refactor result when the user switches to a different country.
  useEffect(() => {
    setRefactorErr(null)
    setRefactorResult(null)
  }, [selectedCountry])

  const refactor = async () => {
    if (!template?.id) return
    if (!confirm(
      'Refactor budget?\n\n' +
      'The LLM will read every policy document uploaded for this country and exclude line items that are not charged here. ' +
      'Existing exclusions will be replaced.'
    )) return
    setRefactoring(true)
    setRefactorErr(null)
    setRefactorResult(null)
    try {
      const r = await refactorBudgetFromPolicy(template.id)
      setRefactorResult(r)
      setShowSummary(true)
      setRefactorKey((k) => k + 1)
    } catch (e: any) {
      setRefactorErr(e?.response?.data?.detail ?? e?.message ?? 'Refactor failed.')
    } finally {
      setRefactoring(false)
    }
  }

  return (
    <div className="flex flex-col min-h-0">
      <div className="bg-white border-b border-slate-200 px-6 py-4 shrink-0">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide shrink-0">Country</label>
            <div className="flex items-center gap-2 overflow-x-auto py-0.5">
              {countries.length === 0 ? (
                <span className="text-xs text-slate-400">No countries available</span>
              ) : (
                countries.map((c) => {
                  const active = c.code === selectedCountry
                  return (
                    <button
                      key={c.code}
                      type="button"
                      onClick={() => onCountryChange(c.code)}
                      aria-pressed={active}
                      title={`${c.label} (${c.code})`}
                      className={`shrink-0 rounded-full border px-3 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 ${
                        active
                          ? 'border-emerald-500 bg-emerald-500 text-white shadow-sm'
                          : 'border-slate-200 bg-white text-slate-600 hover:border-emerald-300 hover:bg-emerald-50'
                      }`}
                    >
                      {c.label} ({c.code})
                    </button>
                  )
                })
              )}
            </div>
          </div>
          {selectedCountryRow && (
            <>
              <span className={badge.success}>
                Country factor ×{parseFloat(selectedCountryRow.factor).toFixed(2)}
              </span>
              <span className={badge.info}>
                1 USD = {parseFloat(fxRate).toLocaleString('en-US', { maximumFractionDigits: 4 })} {currency}
              </span>
            </>
          )}
          {loadingTpl && (
            <svg className="animate-spin h-4 w-4 text-emerald-500 shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          )}
          {tplError && <span className="text-xs text-red-500">{tplError}</span>}
        </div>
        {selectedCountry && (
          <div className="mt-3 flex flex-wrap items-center gap-3 pt-3 border-t border-slate-100">
            <button
              type="button"
              disabled={refactoring || !template}
              onClick={() => void refactor()}
              className={btn.primary}
              title={!template ? 'Loading country template…' : "Read country policy docs, exclude elements that aren't charged here"}
            >
              {refactoring ? (
                <>
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Refactoring…
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Refactor Budget
                </>
              )}
            </button>
            <span className="text-xs text-slate-500">
              Reads country policy docs, marks elements not charged here as excluded.
            </span>
            {refactorErr && (
              <span className="text-xs text-red-600">{refactorErr}</span>
            )}
          </div>
        )}
      </div>

      {!selectedCountry ? (
        <div className="flex-1 flex items-center justify-center py-16 text-sm text-slate-400">
          <div className="text-center">
            <svg className="mx-auto mb-3 h-10 w-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Select a country to view country-level budget
          </div>
        </div>
      ) : template ? (
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {refactorResult && showSummary && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/60 overflow-hidden">
              <div className="flex items-start gap-3 px-4 py-3 border-b border-amber-200">
                <div className="flex-shrink-0 mt-0.5">
                  <svg className="h-5 w-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-amber-900">
                    Budget refactor — {refactorResult.country_code}
                  </p>
                  <p className="text-xs text-amber-800 mt-0.5">
                    Read {refactorResult.doc_count} policy document{refactorResult.doc_count !== 1 ? 's' : ''} for {refactorResult.country_code}; applied {refactorResult.excluded.length} exclusion{refactorResult.excluded.length !== 1 ? 's' : ''}, {refactorResult.included.length} visit-matrix inclusion{refactorResult.included.length !== 1 ? 's' : ''}, and {(refactorResult.milestone_items ?? []).length} milestone item{(refactorResult.milestone_items ?? []).length !== 1 ? 's' : ''} (route to Milestones tab). The TRIAL template is unchanged.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowSummary(false)}
                  className="text-amber-600 hover:text-amber-900 text-xl leading-none px-1"
                  title="Dismiss"
                >
                  ×
                </button>
              </div>
              <div className="px-4 py-3 space-y-3">
                {refactorResult.excluded.length === 0 && refactorResult.included.length === 0 && (refactorResult.milestone_items ?? []).length === 0 ? (
                  <p className="text-xs text-amber-800 italic">
                    No rules were extracted. Either the policy doesn't list any inclusions/exclusions, or the LLM couldn't find a match in this trial's element list. Active rows remain unchanged.
                  </p>
                ) : (
                  <>
                    {refactorResult.excluded.length > 0 && (
                      <div className="rounded-md border border-red-200 bg-red-50/60 p-3">
                        <p className="text-xs font-semibold text-red-800 uppercase tracking-wide mb-2">
                          Excluded ({refactorResult.excluded.length}) — not charged in this country
                        </p>
                        <ul className="space-y-1.5">
                          {refactorResult.excluded.map((e) => (
                            <li key={`ex-${e.element_name}`} className="flex items-start gap-2 text-xs">
                              <span className="inline-flex items-center justify-center mt-0.5 h-4 w-4 rounded-full bg-red-100 text-red-700 text-[10px] font-bold">✕</span>
                              <div className="flex-1 min-w-0">
                                <p className="font-semibold text-slate-800">{e.element_name}</p>
                                {e.reason && <p className="text-slate-600 italic">{e.reason}</p>}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {refactorResult.included.length > 0 && (
                      <div className="rounded-md border border-emerald-200 bg-emerald-50/60 p-3">
                        <p className="text-xs font-semibold text-emerald-800 uppercase tracking-wide mb-2">
                          Mandated in visit matrix ({refactorResult.included.length}) — per-visit costs country requires
                        </p>
                        <ul className="space-y-1.5">
                          {refactorResult.included.map((e) => (
                            <li key={`in-${e.element_name}`} className="flex items-start gap-2 text-xs">
                              <span className="inline-flex items-center justify-center mt-0.5 h-4 w-4 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold">✓</span>
                              <div className="flex-1 min-w-0">
                                <p className="font-semibold text-slate-800">{e.element_name}</p>
                                {e.reason && <p className="text-slate-600 italic">{e.reason}</p>}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {(refactorResult.milestone_items ?? []).length > 0 && (
                      <div className="rounded-md border border-indigo-200 bg-indigo-50/60 p-3">
                        <p className="text-xs font-semibold text-indigo-800 uppercase tracking-wide mb-2">
                          Mandated in milestones ({refactorResult.milestone_items.length}) — one-time / pass-through costs
                        </p>
                        <p className="text-[11px] text-indigo-700 italic mb-2">
                          These are milestone-triggered costs (startup fees, close-out fees, per-patient pass-throughs). They belong in the Milestones section — regenerate milestones from policy to add them there.
                        </p>
                        <ul className="space-y-1.5">
                          {refactorResult.milestone_items.map((e) => (
                            <li key={`ms-${e.element_name}`} className="flex items-start gap-2 text-xs">
                              <span className="inline-flex items-center justify-center mt-0.5 h-4 w-4 rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-bold">M</span>
                              <div className="flex-1 min-w-0">
                                <p className="font-semibold text-slate-800">{e.element_name}</p>
                                {e.reason && <p className="text-slate-600 italic">{e.reason}</p>}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
          {refactorResult && !showSummary && (
            <button
              type="button"
              onClick={() => setShowSummary(true)}
              className="text-xs text-amber-700 hover:text-amber-900 underline"
            >
              Show last refactor summary ({refactorResult.excluded.length} excluded, {refactorResult.included.length} mandated in matrix, {(refactorResult.milestone_items ?? []).length} in milestones)
            </button>
          )}
          <BudgetConfiguration
            key={refactorKey}
            templateId={template.id}
            level="COUNTRY"
            countryCode={selectedCountry}
            trialId={trialId}
          />
        </div>
      ) : (
        <p className="p-6 text-sm text-slate-400 italic">Waiting for template…</p>
      )}
    </div>
  )
}
