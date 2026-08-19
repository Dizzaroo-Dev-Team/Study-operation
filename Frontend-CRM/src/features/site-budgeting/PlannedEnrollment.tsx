import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  listCountryBudgets,
  listPlannedEnrollment,
  upsertPlannedEnrollment,
} from './services/budgeting.api'
import type {
  CountryBudgetOption,
  PlannedEnrollmentRow,
} from './services/budgeting.api'
import { btn, input as inp, table as t, emptyState } from './ui'

type Props = {
  trialId: string
}

type DraftRow = PlannedEnrollmentRow & {
  dirty?: boolean
  saving?: boolean
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export const PlannedEnrollment: React.FC<Props> = ({ trialId }) => {
  const [rows, setRows] = useState<DraftRow[]>([])
  const [countries, setCountries] = useState<CountryBudgetOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savedId, setSavedId] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!trialId) {
      setLoading(false)
      setRows([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [planRows, countryRows] = await Promise.all([
        listPlannedEnrollment(trialId),
        listCountryBudgets(trialId),
      ])
      setRows(planRows.map((r) => ({ ...r })))
      setCountries(countryRows)
    } catch (e: any) {
      const status = e?.response?.status ?? 0
      if (status === 0 || status >= 500) setError('Could not load planned enrollment.')
      setRows([])
      setCountries([])
    } finally {
      setLoading(false)
    }
  }, [trialId])

  useEffect(() => {
    load()
  }, [load])

  const updateField = (siteId: string, patch: Partial<DraftRow>) => {
    setRows((prev) =>
      prev.map((r) => (r.site_id === siteId ? { ...r, ...patch, dirty: true } : r)),
    )
  }

  const save = async (row: DraftRow) => {
    if (row.saving) return
    setRows((prev) =>
      prev.map((r) => (r.site_id === row.site_id ? { ...r, saving: true } : r)),
    )
    try {
      const saved = await upsertPlannedEnrollment({
        study_id: trialId,
        site_id: row.site_id,
        country_code: row.country_code,
        planned_patients: Number.isFinite(row.planned_patients)
          ? Number(row.planned_patients)
          : 0,
        planned_activation_date: row.planned_activation_date,
      })
      setRows((prev) =>
        prev.map((r) =>
          r.site_id === row.site_id
            ? { ...r, ...saved, dirty: false, saving: false }
            : r,
        ),
      )
      setSavedId(row.site_id)
      window.setTimeout(() => setSavedId((cur) => (cur === row.site_id ? null : cur)), 1500)
    } catch (e: any) {
      const detail = e?.response?.data?.detail || 'Could not save plan.'
      setError(detail)
      setRows((prev) =>
        prev.map((r) => (r.site_id === row.site_id ? { ...r, saving: false } : r)),
      )
    }
  }

  const noCountriesYet = useMemo(() => countries.length === 0, [countries])

  if (loading) {
    return <div className={emptyState}>Loading planned enrollment…</div>
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
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
      {noCountriesYet && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          No country-level budgets yet. Create a country budget under Budget
          Configuration → Country before mapping sites here.
        </div>
      )}

      <div className={t.wrap}>
        <table className={t.base}>
          <thead className={t.thead}>
            <tr>
              <th className={t.th}>Site</th>
              <th className={t.th}>Country budget</th>
              <th className={t.thRight}># Patients</th>
              <th className={t.th}>Planned activation</th>
              <th className={t.thCenter}>Save</th>
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
                <td className={t.td}>
                  <select
                    className={inp.sm}
                    value={r.country_code ?? ''}
                    disabled={noCountriesYet}
                    onChange={(e) =>
                      updateField(r.site_id, { country_code: e.target.value || null })
                    }
                  >
                    <option value="">—</option>
                    {countries.map((c) => (
                      <option key={c.template_id} value={c.country_code}>
                        {c.country_code} — {c.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className={t.tdRight}>
                  <input
                    type="number"
                    min={0}
                    className={`${inp.sm} text-right`}
                    value={Number.isFinite(r.planned_patients) ? r.planned_patients : 0}
                    onChange={(e) =>
                      updateField(r.site_id, {
                        planned_patients: Number(e.target.value || 0),
                      })
                    }
                  />
                </td>
                <td className={t.td}>
                  <input
                    type="date"
                    className={inp.sm}
                    value={r.planned_activation_date ?? ''}
                    max={undefined}
                    placeholder={todayIso()}
                    onChange={(e) =>
                      updateField(r.site_id, {
                        planned_activation_date: e.target.value || null,
                      })
                    }
                  />
                </td>
                <td className={t.tdCenter}>
                  <button
                    className={btn.primarySm}
                    disabled={!r.dirty || r.saving}
                    onClick={() => save(r)}
                  >
                    {r.saving ? 'Saving…' : savedId === r.site_id ? 'Saved' : 'Save'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
