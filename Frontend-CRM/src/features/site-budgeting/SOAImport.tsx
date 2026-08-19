import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { generateVisitMatrix, listSoaStudyIds } from './services/budgeting.api'
import type { SoaStudy, SoaSelectedStudy, VisitMatrixGenerateResult } from './services/budgeting.api'
import { btn, input, label as lbl } from './ui'

type Props = {
  templateId: string
  /** The currently-selected study/trial id — used to auto-detect its SoA record. */
  selectedStudyId: string
  onImported: () => void
}

// One entry in the local "previous runs" log. Persisted to localStorage so
// the user can scan what they've already pulled, and one-click reload any
// past run's inputs back into the form to re-generate without retyping.
type HistoryEntry = {
  id: string
  ts: number // ms since epoch
  inputs: {
    study_id: string
    treatment_duration: number
    followup_duration: number
    unscheduled_visits: number
  }
  result: VisitMatrixGenerateResult | null // null when the run errored
  error: string | null
}

// Keyed per templateId so different trials don't bleed history into each other.
const historyKey = (templateId: string) => `soa-import-history:${templateId || 'unknown'}`
const MAX_HISTORY = 25

function loadHistory(templateId: string): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(historyKey(templateId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveHistory(templateId: string, entries: HistoryEntry[]): void {
  try {
    localStorage.setItem(historyKey(templateId), JSON.stringify(entries.slice(0, MAX_HISTORY)))
  } catch {
    // Out of quota or storage disabled — non-fatal, history just won't persist.
  }
}

function fmtAgo(ts: number): string {
  const diff = Date.now() - ts
  const sec = Math.round(diff / 1000)
  if (sec < 60) return `${sec}s ago`
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 30) return `${day}d ago`
  return new Date(ts).toLocaleDateString()
}

export const SOAImport: React.FC<Props> = ({ templateId, selectedStudyId, onImported }) => {
  const [studyId, setStudyId] = useState('')
  const [treatment, setTreatment] = useState('')
  const [followup, setFollowup] = useState('')
  const [unscheduled, setUnscheduled] = useState('')

  const [studies, setStudies] = useState<SoaStudy[]>([])
  const [selected, setSelected] = useState<SoaSelectedStudy | null>(null)
  const [loadingIds, setLoadingIds] = useState(false)
  // false → SoA cluster is unconfigured/unreachable (backend degraded to empty).
  const [soaAvailable, setSoaAvailable] = useState(true)
  const [soaError, setSoaError] = useState<string | null>(null)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<VisitMatrixGenerateResult | null>(null)

  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory(templateId))

  // Re-load history when the active trial switches so we never show stale
  // entries from a previously-open template.
  useEffect(() => {
    setHistory(loadHistory(templateId))
  }, [templateId])

  useEffect(() => {
    let cancelled = false
    setLoadingIds(true)
    // Pass the selected trial id so the backend can resolve its name + SoA presence.
    listSoaStudyIds(selectedStudyId || undefined)
      .then(({ studies: rows, selected: sel, available, error }) => {
        if (cancelled) return
        setStudies(rows)
        setSelected(sel)
        setSoaAvailable(available)
        setSoaError(error)
        // Auto-populate the field with the selected study's SoA protocol id when it
        // exists — but never clobber whatever the user is already typing.
        if (sel?.in_soa && sel.study_id) {
          const hit = sel.study_id
          setStudyId((cur) => (cur.trim() === '' ? hit : cur))
        }
      })
      .catch(() => {
        if (cancelled) return
        setStudies([])
        setSelected(null)
        setSoaAvailable(false)
        setSoaError('Could not reach the SoA database.')
      })
      .finally(() => {
        if (!cancelled) setLoadingIds(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedStudyId])

  // Label lookup: prefer the CRM study name, fall back to the protocol id.
  const labelFor = useCallback(
    (id: string) => {
      const s = studies.find((x) => x.study_id === id)
      return s?.name ? `${s.name} (${s.study_id})` : id
    },
    [studies],
  )

  const idList = useMemo(() => studies.map((s) => s.study_id), [studies])

  // Autocomplete matches the typed text against both the protocol id and the name.
  const matches = studyId.trim()
    ? studies
        .filter((s) => {
          const q = studyId.trim().toLowerCase()
          return (
            s.study_id.toLowerCase().includes(q) ||
            (s.name ?? '').toLowerCase().includes(q)
          )
        })
        .map((s) => s.study_id)
        .slice(0, 6)
    : []

  const ready =
    studyId.trim() !== '' &&
    treatment.trim() !== '' &&
    followup.trim() !== '' &&
    unscheduled.trim() !== ''

  const pushHistory = useCallback(
    (entry: HistoryEntry) => {
      setHistory((prev) => {
        const next = [entry, ...prev].slice(0, MAX_HISTORY)
        saveHistory(templateId, next)
        return next
      })
    },
    [templateId],
  )

  const submit = async () => {
    if (!ready) return
    setSubmitting(true)
    setError(null)
    setResult(null)
    const inputs = {
      study_id: studyId.trim(),
      treatment_duration: parseInt(treatment, 10) || 0,
      followup_duration: parseInt(followup, 10) || 0,
      unscheduled_visits: parseInt(unscheduled, 10) || 0,
    }
    try {
      const r = await generateVisitMatrix(templateId, inputs)
      setResult(r)
      pushHistory({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        ts: Date.now(),
        inputs,
        result: r,
        error: null,
      })
      onImported()
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.message ?? 'Failed to generate visit matrix.'
      setError(msg)
      // Failed runs are recorded too — useful when debugging "why did X fail".
      pushHistory({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        ts: Date.now(),
        inputs,
        result: null,
        error: msg,
      })
    } finally {
      setSubmitting(false)
    }
  }

  const reuseEntry = useCallback((entry: HistoryEntry) => {
    setStudyId(entry.inputs.study_id)
    setTreatment(String(entry.inputs.treatment_duration))
    setFollowup(String(entry.inputs.followup_duration))
    setUnscheduled(String(entry.inputs.unscheduled_visits))
    setError(null)
    setResult(null)
  }, [])

  const removeEntry = useCallback(
    (id: string) => {
      setHistory((prev) => {
        const next = prev.filter((h) => h.id !== id)
        saveHistory(templateId, next)
        return next
      })
    },
    [templateId],
  )

  const clearHistory = useCallback(() => {
    if (!confirm('Clear all SOA import history for this trial?')) return
    setHistory([])
    saveHistory(templateId, [])
  }, [templateId])

  const historyCount = history.length
  const lastRun = useMemo(() => (history.length > 0 ? history[0] : null), [history])

  return (
    // Two columns: form on the left fills available width, history fills
    // the previously-empty right gutter. Stacks on small screens.
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-6">
      <div className="space-y-6 min-w-0">
        <div>
          <h3 className="text-lg font-semibold text-slate-800">Generate Visit Matrix from SOA</h3>
          <p className="mt-1 text-sm text-slate-500">
            Pulls the Schedule of Activities for the selected study from the protocol library, maps
            activities to cost elements, and writes the resulting visit matrix. Appends the requested
            number of Unscheduled visits at the end.
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
          {/* Selected-study presence banner. Tells the user (and demo audience)
              whether the currently-selected study exists in the SoA database.
              Shows the study NAME (from the CRM), not the raw id/uuid. */}
          {selectedStudyId.trim() !== '' && (
            <div>
              {(() => {
                const studyLabel = selected?.name ?? selected?.study_id ?? 'the selected study'
                if (!soaAvailable) {
                  return (
                    <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                      <span aria-hidden="true">⚠️</span>
                      <span>
                        SoA database is currently unavailable — cannot check whether{' '}
                        <span className="font-semibold">{studyLabel}</span> exists.
                        {soaError && <span className="block text-xs text-amber-600 mt-0.5">{soaError}</span>}
                      </span>
                    </div>
                  )
                }
                if (loadingIds) {
                  return (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500">
                      Checking SoA database for <span className="font-semibold">{studyLabel}</span>…
                    </div>
                  )
                }
                if (selected?.in_soa) {
                  return (
                    <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                      <span aria-hidden="true">✓</span>
                      <span>
                        Selected study <span className="font-semibold">{studyLabel}</span> is present in
                        the SoA database{selected.study_id && (
                          <> (<span className="font-mono">{selected.study_id}</span>)</>
                        )} and has been filled in below.
                      </span>
                    </div>
                  )
                }
                return (
                  <div className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                    <span aria-hidden="true">ℹ️</span>
                    <span>
                      Study <span className="font-semibold">{studyLabel}</span> is not present in the
                      SoA database. Pick an available study below to continue.
                    </span>
                  </div>
                )
              })()}
            </div>
          )}

          <div>
            <label className={lbl}>Protocol / Study ID</label>
            <div className="relative mt-1.5">
              <input
                className={input.base}
                placeholder={loadingIds ? 'Loading study IDs…' : 'Start typing a study ID…'}
                value={studyId}
                onChange={(e) => setStudyId(e.target.value)}
                autoComplete="off"
                disabled={submitting}
              />
              {matches.length > 0 && matches[0] !== studyId.trim() && (
                <div className="absolute left-0 right-0 top-full mt-1 rounded-lg border border-slate-200 bg-white shadow-lg z-10 max-h-56 overflow-y-auto">
                  {matches.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setStudyId(m)}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 text-slate-700"
                    >
                      {labelFor(m)}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Always-visible dropdown of every study present in the SoA database,
                labelled by study NAME (falls back to the protocol id when the study
                isn't in the CRM). Makes picking a valid study one click during demos. */}
            <div className="mt-2 flex items-center gap-2">
              <select
                className={input.base}
                value={idList.includes(studyId.trim()) ? studyId.trim() : ''}
                onChange={(e) => setStudyId(e.target.value)}
                disabled={submitting || loadingIds || studies.length === 0}
                aria-label="Available SoA studies"
              >
                <option value="">
                  {loadingIds
                    ? 'Loading studies…'
                    : studies.length === 0
                      ? soaAvailable
                        ? 'No studies found in SoA database'
                        : 'SoA database unavailable'
                      : `Available in SoA database (${studies.length})…`}
                </option>
                {studies.map((s) => (
                  <option key={s.study_id} value={s.study_id}>
                    {s.name ? `${s.name} (${s.study_id})` : s.study_id}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className={lbl}>Treatment duration (weeks)</label>
              <input
                className={`${input.base} mt-1.5`}
                type="number"
                min={0}
                value={treatment}
                onChange={(e) => setTreatment(e.target.value)}
                disabled={submitting}
                placeholder="e.g. 24"
              />
            </div>
            <div>
              <label className={lbl}>Follow-up duration (weeks)</label>
              <input
                className={`${input.base} mt-1.5`}
                type="number"
                min={0}
                value={followup}
                onChange={(e) => setFollowup(e.target.value)}
                disabled={submitting}
                placeholder="e.g. 12"
              />
            </div>
            <div>
              <label className={lbl}>Unscheduled visits (count)</label>
              <input
                className={`${input.base} mt-1.5`}
                type="number"
                min={0}
                value={unscheduled}
                onChange={(e) => setUnscheduled(e.target.value)}
                disabled={submitting}
                placeholder="e.g. 2"
              />
            </div>
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!ready || submitting}
              className={btn.primary}
              data-testid="soa-generate-button"
            >
              {submitting ? (
                <>
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Generating…
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Generate Visit Matrix
                </>
              )}
            </button>
            {error && <p className="text-sm text-red-600">{error}</p>}
            {lastRun && !error && !submitting && !result && (
              <p className="text-xs text-slate-400">
                Last run {fmtAgo(lastRun.ts)} ·{' '}
                <span className="font-mono">{lastRun.inputs.study_id}</span>
              </p>
            )}
          </div>
        </div>

        {result && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <p className="text-sm font-semibold text-emerald-800">Visit matrix generated</p>
            <ul className="mt-2 text-sm text-emerald-900 space-y-1">
              <li>
                Visits inserted: <span className="font-mono">{result.visits_inserted}</span>
                {result.unscheduled_appended > 0 && (
                  <> (+ <span className="font-mono">{result.unscheduled_appended}</span> unscheduled)</>
                )}
              </li>
              <li>Line items inserted: <span className="font-mono">{result.line_items_inserted}</span></li>
              <li>Matrix cells inserted: <span className="font-mono">{result.matrix_cells_inserted}</span></li>
              {result.unmapped_activities.length > 0 && (
                <li className="text-amber-700">
                  {result.unmapped_activities.length} activity(ies) could not be mapped to a cost element.
                </li>
              )}
            </ul>
            <p className="mt-2 text-xs text-emerald-700">
              Switch to the Visit Matrix tab to review the generated schedule.
            </p>
          </div>
        )}
      </div>

      {/* Right column — history of past generations for this trial. Persisted
          to localStorage so it survives reloads. Clicking "Reuse" repopulates
          the form on the left so the user doesn't have to retype the inputs. */}
      <aside className="lg:sticky lg:top-4 self-start min-w-0">
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Previous runs</h4>
              <p className="text-[11px] text-slate-500">
                {historyCount === 0
                  ? 'Nothing yet — your generations will show up here.'
                  : `${historyCount} of ${MAX_HISTORY} kept (this device, this trial).`}
              </p>
            </div>
            {historyCount > 0 && (
              <button
                type="button"
                onClick={clearHistory}
                className="text-[11px] font-medium text-slate-500 hover:text-red-600 underline-offset-2 hover:underline"
                title="Clear all history for this trial"
              >
                Clear all
              </button>
            )}
          </div>

          {historyCount === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-slate-400">
              <svg
                className="mx-auto h-8 w-8 text-slate-300 mb-2"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3M9 3v2m6-2v2M5 7h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V9a2 2 0 012-2z" />
              </svg>
              Fill the form and click <span className="font-medium text-slate-500">Generate Visit Matrix</span> — every run lands here.
            </div>
          ) : (
            <ul className="divide-y divide-slate-100 max-h-[520px] overflow-y-auto">
              {history.map((h) => {
                const ok = h.result !== null && !h.error
                return (
                  <li key={h.id} className="px-4 py-3 hover:bg-slate-50 group">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-block h-2 w-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-red-500'}`}
                            aria-hidden="true"
                          />
                          <span className="font-mono text-xs font-semibold text-slate-800 truncate">
                            {h.inputs.study_id}
                          </span>
                        </div>
                        <div className="mt-1 text-[11px] text-slate-500">
                          {fmtAgo(h.ts)} · {new Date(h.ts).toLocaleString()}
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1 text-[10px]">
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                            Tx <span className="font-semibold">{h.inputs.treatment_duration}w</span>
                          </span>
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                            FU <span className="font-semibold">{h.inputs.followup_duration}w</span>
                          </span>
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                            Unsch <span className="font-semibold">{h.inputs.unscheduled_visits}</span>
                          </span>
                        </div>
                        {ok && h.result && (
                          <div className="mt-1.5 text-[11px] text-emerald-700">
                            {h.result.visits_inserted} visits · {h.result.line_items_inserted} line items
                            {h.result.unmapped_activities.length > 0 && (
                              <span className="text-amber-700">
                                {' '}· {h.result.unmapped_activities.length} unmapped
                              </span>
                            )}
                          </div>
                        )}
                        {!ok && h.error && (
                          <div className="mt-1.5 text-[11px] text-red-600 line-clamp-2" title={h.error}>
                            {h.error}
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          type="button"
                          onClick={() => reuseEntry(h)}
                          className="text-[11px] font-medium text-indigo-600 hover:text-indigo-800 px-2 py-1 rounded hover:bg-indigo-50"
                          title="Copy these inputs back into the form"
                          disabled={submitting}
                        >
                          Reuse
                        </button>
                        <button
                          type="button"
                          onClick={() => removeEntry(h.id)}
                          className="text-[11px] font-medium text-slate-400 hover:text-red-600 px-2 py-1 rounded hover:bg-red-50"
                          title="Remove this entry"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </aside>
    </div>
  )
}
