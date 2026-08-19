import React, { useEffect, useMemo, useState } from 'react'
import { Ban, Building2, CalendarClock, FileText, MapPin, Plus, Send, ShieldCheck, Trash2 } from 'lucide-react'
import {
  useSubmitVisitReschedule,
  useVisitReschedule,
} from '@/lib/queries/useMonitoring'

const pathVisitId = (pathname: string): string | null => {
  const m = pathname.match(/^\/monitoring\/visits\/([^/]+)\/reschedule\/?$/)
  return m ? decodeURIComponent(m[1]) : null
}

/** User-facing label; prefer per-site visit number over internal id. */
function visitDisplayLabel(visit: { id: string; site_visit_number?: number | null }): string {
  const n = visit.site_visit_number
  if (n != null && Number.isFinite(n) && n >= 1) return `Visit #${n}`
  return visit.id
}

/** ISO 8601 instant in UTC, e.g. 2026-05-02T08:00:00Z — T joins date+time, Z = UTC (Zulu). */
function formatVisitInstantUtcLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return (
    d.toLocaleString(undefined, { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' }) + ' UTC'
  )
}

/**
 * Full-viewport scroll layer. `html/body/#root` use overflow:hidden in index.css, so `h-full`
 * children often fail to show a document scrollbar. `fixed inset-0` + `overflow-y-auto` always
 * creates a real scrollport for the form (reason + submit below the fold).
 */
const PageShell: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div
    className={[
      'fixed inset-0 z-[200] overflow-x-hidden overflow-y-auto overscroll-y-auto [scrollbar-gutter:stable]',
      'bg-gradient-to-b from-slate-50 via-white to-slate-100/90',
      'min-h-0', // allow flex children to shrink if any nested flex appears later
      className,
    ].join(' ')}
  >
    {children}
  </div>
)

/** Extract YYYY-MM-DD from an ISO instant for date inputs. */
function isoToDateInput(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Extract HH:MM from an ISO instant for time inputs (local clock). */
function isoToTimeInput(iso: string, fallback = '08:00'): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return fallback
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** Combine local date + time into UTC ISO for the API. */
function localDateTimeToIso(dateYmd: string, timeHhmm: string): string {
  const d = new Date(`${dateYmd}T${timeHhmm || '08:00'}`)
  if (Number.isNaN(d.getTime())) throw new Error('invalid datetime')
  return d.toISOString()
}

const inputClass =
  'block w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm transition placeholder:text-slate-400 focus:border-[#1E73BE] focus:outline-none focus:ring-2 focus:ring-[#1E73BE]/20 [color-scheme:light]'

type SlotDraft = {
  startDate: string
  startTime: string
  endDate: string
  endTime: string
}

const MIN_PROPOSED_SLOTS = 2
const MAX_PROPOSED_SLOTS = 10

const emptySlot = (): SlotDraft => ({
  startDate: '',
  startTime: '08:00',
  endDate: '',
  endTime: '17:00',
})

const emptySlots = (): SlotDraft[] => [emptySlot(), emptySlot()]

function addDaysYmd(ymd: string, days: number): string {
  if (!ymd) return ''
  const d = new Date(`${ymd}T00:00`)
  if (Number.isNaN(d.getTime())) return ymd
  d.setDate(d.getDate() + days)
  return isoToDateInput(d.toISOString())
}

const VisitReschedulePage: React.FC = () => {
  const visitId = useMemo(() => pathVisitId(window.location.pathname), [])
  const token = useMemo(() => new URLSearchParams(window.location.search).get('token') || '', [])

  const [success, setSuccess] = useState(false)
  /** True when the backend returned 409 — visit was already confirmed or cancelled. */
  const [isConflict, setIsConflict] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [slots, setSlots] = useState<SlotDraft[]>(() => emptySlots())
  const [reason, setReason] = useState('')

  // Surface link-validation errors before any fetch fires.
  const linkValidationError = !visitId
    ? 'Invalid reschedule link (missing visit).'
    : !token
      ? 'This page requires a valid token from your email link.'
      : null

  const rescheduleQuery = useVisitReschedule(visitId, token)
  const submitMutation = useSubmitVisitReschedule(visitId)

  // Translate query error into the same string + 409 conflict signal the
  // legacy load() effect produced.
  useEffect(() => {
    if (!rescheduleQuery.isError) return
    const anyErr = rescheduleQuery.error as any
    const status: number | undefined = anyErr?.response?.status
    if (status === 409) {
      setIsConflict(true)
    }
  }, [rescheduleQuery.isError, rescheduleQuery.error])

  const data = rescheduleQuery.data ?? null
  const loading = Boolean(visitId && token) && rescheduleQuery.isLoading
  const submitting = submitMutation.isPending

  // Prefill proposed slot from the current visit schedule when the form loads.
  useEffect(() => {
    if (!data?.visit) return
    const startIso = data.visit.visit_date_iso
    const endIso = data.visit.visit_end_date_iso
    if (!startIso) return
    const startYmd = isoToDateInput(startIso)
    const endYmd = endIso ? isoToDateInput(endIso) : startYmd
    const startHhmm = isoToTimeInput(startIso)
    const endHhmm = endIso ? isoToTimeInput(endIso, '17:00') : '17:00'
    setSlots([0, 1].map((offset) => ({
      startDate: addDaysYmd(startYmd, offset),
      startTime: startHhmm,
      endDate: addDaysYmd(endYmd, offset),
      endTime: endHhmm,
    })))
  }, [data?.visit?.id, data?.visit?.visit_date_iso, data?.visit?.visit_end_date_iso])

  const updateSlot = (index: number, patch: Partial<SlotDraft>) => {
    setSlots((prev) => prev.map((slot, i) => (i === index ? { ...slot, ...patch } : slot)))
  }

  const addSlot = () => {
    setSlots((prev) => {
      if (prev.length >= MAX_PROPOSED_SLOTS) return prev
      const last = prev[prev.length - 1]
      const nextStart = last?.startDate ? addDaysYmd(last.startDate, 1) : ''
      const nextEnd = last?.endDate ? addDaysYmd(last.endDate, 1) : nextStart
      return [
        ...prev,
        {
          startDate: nextStart,
          startTime: last?.startTime ?? '08:00',
          endDate: nextEnd,
          endTime: last?.endTime ?? '17:00',
        },
      ]
    })
  }

  const removeSlot = (index: number) => {
    setSlots((prev) => {
      if (prev.length <= MIN_PROPOSED_SLOTS) return prev
      return prev.filter((_, i) => i !== index)
    })
  }

  const fetchErrorMessage = useMemo(() => {
    if (!rescheduleQuery.isError) return null
    const anyErr = rescheduleQuery.error as any
    const detail: unknown = anyErr?.response?.data?.detail
    return (
      (typeof detail === 'string' ? detail : null) ||
      anyErr?.message ||
      'Could not load visit details.'
    )
  }, [rescheduleQuery.isError, rescheduleQuery.error])

  const error = linkValidationError ?? submitError ?? fetchErrorMessage

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!visitId || !token) return
    if (slots.length < MIN_PROPOSED_SLOTS) {
      setSubmitError(`Please provide at least ${MIN_PROPOSED_SLOTS} proposed visit options.`)
      return
    }
    const missingSlot = slots.findIndex((slot) => !slot.startDate.trim() || !slot.endDate.trim())
    if (missingSlot >= 0) {
      setSubmitError(`Please complete start and end dates for option ${missingSlot + 1}.`)
      return
    }
    if (reason.trim().length < 2) {
      setSubmitError('Please enter a reason for rescheduling (at least a few characters).')
      return
    }
    let proposedSlots: Array<{ proposed_datetime_iso: string; proposed_end_datetime_iso: string }>
    try {
      proposedSlots = slots.map((slot) => ({
        proposed_datetime_iso: localDateTimeToIso(slot.startDate, slot.startTime),
        proposed_end_datetime_iso: localDateTimeToIso(slot.endDate, slot.endTime),
      }))
    } catch {
      setSubmitError('Proposed date or time is not valid.')
      return
    }
    const invalidSlot = proposedSlots.findIndex(
      (slot) => new Date(slot.proposed_end_datetime_iso).getTime() < new Date(slot.proposed_datetime_iso).getTime(),
    )
    if (invalidSlot >= 0) {
      setSubmitError(`Option ${invalidSlot + 1} end must be on or after its start.`)
      return
    }

    setSubmitError(null)
    try {
      await submitMutation.mutateAsync({
        token,
        proposed_datetime_iso: proposedSlots[0].proposed_datetime_iso,
        proposed_end_datetime_iso: proposedSlots[0].proposed_end_datetime_iso,
        proposed_slots: proposedSlots,
        reason: reason.trim(),
      })
      setSuccess(true)
    } catch (err: unknown) {
      const anyErr = err as any
      const status: number | undefined = anyErr?.response?.status
      const detail: unknown = anyErr?.response?.data?.detail
      const respData: unknown = anyErr?.response?.data
      const message: unknown = anyErr?.message

      const safeDetail = typeof detail === 'string' ? detail : undefined
      const safeData =
        typeof respData === 'string'
          ? respData
          : respData && typeof respData === 'object' && 'detail' in respData
            ? String((respData as any).detail)
            : undefined

      const finalMsg =
        safeDetail || safeData || (typeof message === 'string' ? message : 'Submit failed.')

      if (status === 409) {
        setIsConflict(true)
      }
      setSubmitError(finalMsg)
    }
  }

  if (loading) {
    return (
      <PageShell className="flex items-center justify-center px-4 py-12">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-slate-200 border-t-[#1E73BE]" />
          <p className="mt-4 text-slate-600">Loading visit…</p>
        </div>
      </PageShell>
    )
  }

  if (isConflict) {
    return (
      <PageShell className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
          <div className="bg-gradient-to-r from-amber-500 to-orange-500 px-8 py-6 text-center">
            <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-white/20 ring-4 ring-white/30">
              <Ban className="h-9 w-9 text-white" strokeWidth={1.8} />
            </div>
            <h1 className="text-xl font-bold text-white">Link No Longer Valid</h1>
          </div>
          <div className="px-8 py-6 text-center">
            <p className="text-sm leading-relaxed text-gray-700">{error}</p>
            <p className="mt-4 text-xs text-gray-400">
              Each action link can only be used once. If you need to request a reschedule,
              please contact your assigned Clinical Research Associate directly.
            </p>
          </div>
        </div>
      </PageShell>
    )
  }

  if (!loading && !data && error && !success) {
    return (
      <PageShell>
        <div className="mx-auto flex min-h-min max-w-md flex-col px-4 py-12 sm:py-16">
          <div className="rounded-2xl border border-red-100 bg-white p-8 shadow-sm">
            <h1 className="text-lg font-semibold text-slate-900">Cannot open reschedule form</h1>
            <p className="mt-2 text-sm text-red-800">{error}</p>
          </div>
        </div>
      </PageShell>
    )
  }

  if (success) {
    return (
      <PageShell>
        <div className="mx-auto flex min-h-min max-w-lg flex-col px-4 py-10 sm:py-14">
          <div className="dizzaroo-shadow rounded-2xl border border-slate-100/80 bg-white/95 p-8 sm:p-10 backdrop-blur-sm">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
              <ShieldCheck className="h-7 w-7" strokeWidth={2} />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Request received</h1>
            <p className="mt-2 text-slate-600">
              Your reschedule request is recorded. Visit status is now{' '}
              <span className="font-medium text-slate-900">Reschedule Requested</span>.
            </p>
          </div>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <div className="mx-auto min-h-min max-w-2xl px-4 py-8 pb-20 sm:py-12 sm:pb-24">
        {/* Top brand strip */}
        <div className="mb-6 flex items-center gap-2 text-sm font-medium text-slate-500">
          <span className="rounded-md bg-gradient-to-r from-[#168AAD] to-[#1E73BE] px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-white">
            Dizzaroo
          </span>
          <span className="text-slate-400">|</span>
          <span>Monitoring</span>
        </div>

        <div className="dizzaroo-shadow-lg overflow-hidden rounded-2xl border border-slate-200/60 bg-white/95 shadow-sm backdrop-blur-sm">
          <div className="border-b border-slate-100 bg-gradient-to-r from-slate-50/80 to-white px-6 py-5 sm:px-8 sm:py-6">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">Request visit reschedule</h1>
            <p className="mt-1.5 text-sm text-slate-600">
              Signed in as{' '}
              <span className="font-medium text-slate-800">{data?.actor_label ?? 'site contact'}</span> via your secure
              email link.
            </p>
          </div>

          {data?.visit && (
            <div className="border-b border-slate-100 px-6 py-5 sm:px-8 sm:py-6">
              <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                <FileText className="h-4 w-4 text-[#1E73BE]" />
                Current visit
              </h2>
              <dl className="grid gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-500">Visit</dt>
                  <dd className="mt-1 text-sm font-semibold text-slate-900">{visitDisplayLabel(data.visit)}</dd>
                </div>
                <div className="min-w-0 sm:col-span-2">
                  <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                    <CalendarClock className="h-3.5 w-3.5" />
                    Visit start
                  </dt>
                  <dd className="mt-1 text-sm text-slate-900">{data.visit.visit_date || '—'}</dd>
                  {data.visit.visit_date_iso ? (
                    <dd
                      className="mt-1.5 text-xs text-slate-500"
                      title={`ISO 8601 (exact value): ${data.visit.visit_date_iso}`}
                    >
                      <span className="text-slate-400">Same time in UTC:</span>{' '}
                      {formatVisitInstantUtcLabel(data.visit.visit_date_iso)}
                    </dd>
                  ) : null}
                </div>
                {(data.visit.visit_end_date || data.visit.visit_end_date_iso) && (
                  <div className="min-w-0 sm:col-span-2">
                    <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                      <CalendarClock className="h-3.5 w-3.5" />
                      Visit end
                    </dt>
                    <dd className="mt-1 text-sm text-slate-900">{data.visit.visit_end_date || '—'}</dd>
                    {data.visit.visit_end_date_iso ? (
                      <dd
                        className="mt-1.5 text-xs text-slate-500"
                        title={`ISO 8601 (exact value): ${data.visit.visit_end_date_iso}`}
                      >
                        <span className="text-slate-400">Same time in UTC:</span>{' '}
                        {formatVisitInstantUtcLabel(data.visit.visit_end_date_iso)}
                      </dd>
                    ) : null}
                  </div>
                )}
                <div className="min-w-0 sm:col-span-2">
                  <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                    <MapPin className="h-3.5 w-3.5 shrink-0" />
                    Location
                  </dt>
                  <dd className="mt-1 text-sm leading-relaxed text-slate-800">{data.visit.location || '—'}</dd>
                </div>
                {data.visit.visit_type ? (
                  <div>
                    <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                      <Building2 className="h-3.5 w-3.5" />
                      Visit type
                    </dt>
                    <dd className="mt-1 text-sm text-slate-900">{data.visit.visit_type}</dd>
                  </div>
                ) : null}
              </dl>
            </div>
          )}

          {error && (
            <div className="border-b border-slate-100 bg-red-50/80 px-6 py-3 sm:px-8">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {data?.visit && (
            <form onSubmit={handleSubmit} className="px-6 py-6 sm:px-8 sm:py-7">
              <h2 className="mb-5 text-sm font-semibold uppercase tracking-wide text-slate-500">Proposed visit options</h2>
              <div className="space-y-6">
                {slots.map((slot, index) => (
                  <div key={index} className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 sm:p-5">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Option {index + 1}
                      </h3>
                      {slots.length > MIN_PROPOSED_SLOTS && (
                        <button
                          type="button"
                          onClick={() => removeSlot(index)}
                          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-red-600 transition hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-200"
                          aria-label={`Remove option ${index + 1}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Remove
                        </button>
                      )}
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="min-w-0">
                        <label htmlFor={`slot-${index}-start-date`} className="mb-1.5 block text-sm font-medium text-slate-800">
                          Start date
                        </label>
                        <input
                          id={`slot-${index}-start-date`}
                          type="date"
                          value={slot.startDate}
                          onChange={(ev) => updateSlot(index, { startDate: ev.target.value })}
                          className={inputClass}
                          required
                        />
                      </div>
                      <div className="min-w-0">
                        <label htmlFor={`slot-${index}-end-date`} className="mb-1.5 block text-sm font-medium text-slate-800">
                          End date
                        </label>
                        <input
                          id={`slot-${index}-end-date`}
                          type="date"
                          value={slot.endDate}
                          onChange={(ev) => updateSlot(index, { endDate: ev.target.value })}
                          className={inputClass}
                          required
                        />
                      </div>
                      <div className="min-w-0">
                        <label htmlFor={`slot-${index}-start-time`} className="mb-1.5 block text-sm font-medium text-slate-800">
                          Start time
                        </label>
                        <input
                          id={`slot-${index}-start-time`}
                          type="time"
                          value={slot.startTime}
                          onChange={(ev) => updateSlot(index, { startTime: ev.target.value })}
                          className={inputClass}
                          required
                        />
                      </div>
                      <div className="min-w-0">
                        <label htmlFor={`slot-${index}-end-time`} className="mb-1.5 block text-sm font-medium text-slate-800">
                          End time
                        </label>
                        <input
                          id={`slot-${index}-end-time`}
                          type="time"
                          value={slot.endTime}
                          onChange={(ev) => updateSlot(index, { endTime: ev.target.value })}
                          className={inputClass}
                          required
                        />
                      </div>
                    </div>
                  </div>
                ))}

                {slots.length < MAX_PROPOSED_SLOTS && (
                  <button
                    type="button"
                    onClick={addSlot}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-[#1E73BE] hover:bg-slate-50 hover:text-[#1E73BE] focus:outline-none focus:ring-2 focus:ring-[#1E73BE]/20"
                  >
                    <Plus className="h-4 w-4" />
                    Add another option
                  </button>
                )}

                <p className="text-xs text-slate-500">
                  Provide at least {MIN_PROPOSED_SLOTS} options in your local time. Use the + button to add more if needed.
                  The CRA will choose one option and confirm the visit.
                </p>
                <div>
                  <label htmlFor="reason" className="mb-1.5 block text-sm font-medium text-slate-800">
                    Reason for rescheduling
                  </label>
                  <textarea
                    id="reason"
                    value={reason}
                    onChange={(ev) => setReason(ev.target.value)}
                    rows={4}
                    className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-[#1E73BE] focus:outline-none focus:ring-2 focus:ring-[#1E73BE]/20"
                    placeholder="Briefly describe why you need a different time…"
                    required
                  />
                </div>
                <div className="pt-1">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[#1E73BE] to-[#168AAD] px-4 py-3.5 text-sm font-semibold text-white shadow-md transition hover:brightness-105 focus:outline-none focus:ring-2 focus:ring-[#1E73BE] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:min-w-[220px]"
                  >
                    {submitting ? (
                      'Submitting…'
                    ) : (
                      <>
                        <Send className="h-4 w-4" />
                        Submit reschedule request
                      </>
                    )}
                  </button>
                </div>
              </div>
            </form>
          )}

        </div>
      </div>
    </PageShell>
  )
}

export default VisitReschedulePage
