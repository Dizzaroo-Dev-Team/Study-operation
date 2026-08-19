import React, { useEffect, useState } from 'react'
import { fetchEffectiveTemplate, fetchFactorsByScope, fetchFxRate } from './services/budgeting.api'
import type { BudgetTemplateRow, ScopedFactor } from './services/budgeting.api'
import { useStudySite } from '../../contexts/StudySiteContext'
import { BudgetConfiguration } from './BudgetConfiguration'
import { badge, input as inp } from './ui'
import { currencyForCountry } from './country_currency'

type Props = {
  trialId: string
  selectedCountry: string | null
  selectedSiteId: string | null
  onSiteChange: (siteId: string) => void
}

export const SiteColumn: React.FC<Props> = ({ trialId, selectedCountry, selectedSiteId, onSiteChange }) => {
  const { filteredSites } = useStudySite()
  const [template, setTemplate] = useState<BudgetTemplateRow | null>(null)
  const [loadingTpl, setLoadingTpl] = useState(false)
  const [tplError, setTplError] = useState<string | null>(null)
  const [countryFactor, setCountryFactor] = useState<string>('1.00')
  const [siteFactor, setSiteFactor] = useState<string>('1.00')
  const [fxRate, setFxRate] = useState<string>('1.00')

  useEffect(() => {
    if (!selectedSiteId || !selectedCountry) { setTemplate(null); return }
    let cancelled = false
    setLoadingTpl(true)
    setTplError(null)

    fetchEffectiveTemplate({
      trial_id: trialId,
      site_id: selectedSiteId,
      country_code: selectedCountry,
    })
      .then((t) => { if (!cancelled) setTemplate(t as unknown as BudgetTemplateRow) })
      .catch(() => { if (!cancelled) setTplError('Failed to load site template') })
      .finally(() => { if (!cancelled) setLoadingTpl(false) })

    return () => { cancelled = true }
  }, [trialId, selectedSiteId, selectedCountry])

  const currency = currencyForCountry(selectedCountry)

  useEffect(() => {
    if (!selectedCountry) { setCountryFactor('1.00'); setFxRate('1.00'); return }
    let cancelled = false
    fetchFactorsByScope('COUNTRY')
      .then((factors: ScopedFactor[]) => {
        const match = factors.find((f) => f.country_code === selectedCountry)
        if (!cancelled) setCountryFactor(match?.value ?? '1.00')
      })
      .catch(() => {})
    fetchFxRate(currency)
      .then((r) => { if (!cancelled) setFxRate(r) })
      .catch(() => { if (!cancelled) setFxRate('1.00') })
    return () => { cancelled = true }
  }, [selectedCountry, currency])

  useEffect(() => {
    let cancelled = false
    fetchFactorsByScope('SITE')
      .then((factors: ScopedFactor[]) => {
        const global = factors.find((f) => !f.site_id)
        if (!cancelled) setSiteFactor(global?.value ?? '1.00')
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const selectedSite = filteredSites.find((s) => s.id === selectedSiteId)
  const effectiveMultiplier = (parseFloat(countryFactor) || 1) * (parseFloat(siteFactor) || 1)

  return (
    <div className="flex flex-col min-h-0">
      <div className="bg-white border-b border-slate-200 px-6 py-4 shrink-0">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Site</label>
            <select
              className={`${inp.base} w-64`}
              value={selectedSiteId ?? ''}
              onChange={(e) => onSiteChange(e.target.value)}
            >
              <option value="">— choose site —</option>
              {filteredSites.map((s) => (
                <option key={s.id} value={s.id}>
                  {(s as any).name ?? (s as any).site_id ?? s.id}
                </option>
              ))}
            </select>
          </div>
          {selectedSiteId && (
            <>
              {selectedCountry && (
                <>
                  <span className={badge.success}>Country factor ×{parseFloat(countryFactor).toFixed(2)}</span>
                  <span className={badge.info}>1 USD = {parseFloat(fxRate).toLocaleString('en-US', { maximumFractionDigits: 4 })} {currency}</span>
                </>
              )}
              <span className={badge.warn}>Site factor ×{parseFloat(siteFactor).toFixed(2)}</span>
              <span className="text-xs text-slate-500">
                Effective ×{effectiveMultiplier.toFixed(3)} of base
                {selectedCountry && <> in {currency}</>}
              </span>
            </>
          )}
          {loadingTpl && (
            <svg className="animate-spin h-4 w-4 text-violet-500 shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          )}
          {tplError && <span className="text-xs text-red-500">{tplError}</span>}
          {selectedSite && (
            <span className="text-xs text-slate-400 font-mono ml-auto truncate max-w-[160px]">{selectedSiteId}</span>
          )}
        </div>
      </div>

      {!selectedSiteId ? (
        <div className="flex-1 flex items-center justify-center py-16 text-sm text-slate-400">
          <div className="text-center">
            <svg className="mx-auto mb-3 h-10 w-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            Select a site to view site-level budget
          </div>
        </div>
      ) : template ? (
        <div className="flex-1 p-6">
          <BudgetConfiguration templateId={template.id} level="SITE" countryCode={selectedCountry} trialId={trialId} />
        </div>
      ) : (
        <p className="p-6 text-sm text-slate-400 italic">Waiting for template…</p>
      )}
    </div>
  )
}
