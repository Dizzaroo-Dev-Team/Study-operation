import React, { useEffect, useMemo, useState } from 'react'
import {
  CheckCircle2,
  Calendar,
  Download,
  MapPin,
  Clock,
  User,
  FileText,
  AlertTriangle,
  Loader2,
  CalendarCheck,
  Ban,
} from 'lucide-react'
import { api } from '@/lib/api'

// ── Types ─────────────────────────────────────────────────────────────────────

interface CalendarEvent {
  title: string
  start_utc: string
  end_utc: string
  location: string
  description: string
}

interface ConfirmationData {
  status: 'confirmed' | 'already_confirmed'
  actor_role: string
  actor_label: string
  confirmed_by_name: string
  visit_label: string
  event: CalendarEvent
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function pathVisitId(pathname: string): string | null {
  const m = pathname.match(/^\/monitoring\/visits\/([^/]+)\/confirm\/?$/)
  return m ? decodeURIComponent(m[1]) : null
}

function queryToken(): string {
  return new URLSearchParams(window.location.search).get('token') ?? ''
}

/** Format just the date portion for a summary row (e.g. "Thu, May 14, 2026"). */
function formatUtcDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    timeZone: 'UTC',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/** Format just the time portion (e.g. "08:00 AM UTC"). */
function formatUtcTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString(undefined, {
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

/** True when start and end fall on the same calendar date in UTC. */
function isSameUtcDay(isoA: string, isoB: string): boolean {
  const a = new Date(isoA)
  const b = new Date(isoB)
  return (
    a.getUTCFullYear() === b.getUTCFullYear() &&
    a.getUTCMonth() === b.getUTCMonth() &&
    a.getUTCDate() === b.getUTCDate()
  )
}

/** Convert ISO UTC string to Google Calendar compact format: YYYYMMDDTHHMMSSz */
function toGcalDate(iso: string): string {
  return new Date(iso).toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z'
}

function buildGoogleCalendarUrl(event: CalendarEvent): string {
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: event.title,
    dates: `${toGcalDate(event.start_utc)}/${toGcalDate(event.end_utc)}`,
    details: event.description,
    location: event.location,
  })
  return `https://calendar.google.com/calendar/render?${params.toString()}`
}

function downloadIcs(event: CalendarEvent, visitId: string): void {
  const now = new Date().toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z'
  const ics = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Dizzaroo CRM//Monitoring Visit//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:visit-${visitId}@dizzaroo.com`,
    `DTSTAMP:${now}`,
    `DTSTART:${toGcalDate(event.start_utc)}`,
    `DTEND:${toGcalDate(event.end_utc)}`,
    `SUMMARY:${event.title}`,
    `DESCRIPTION:${event.description.replace(/\n/g, '\\n')}`,
    `LOCATION:${event.location}`,
    'STATUS:CONFIRMED',
    'TRANSP:OPAQUE',
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\r\n')

  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `monitoring-visit-${visitId}.ics`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // Defer revoke: revoking synchronously after .click() races with the
  // browser's download pipeline (especially on slow disks / Firefox), which
  // could land an empty .ics file. ~2s is enough for the dispatcher to grab
  // the blob without keeping the URL alive longer than needed.
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

// ── Sub-components ────────────────────────────────────────────────────────────

const InfoRow: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({
  icon,
  label,
  value,
}) => (
  <div className="flex items-start gap-3 py-3 border-b border-gray-100 last:border-0">
    <span className="mt-0.5 flex-shrink-0 text-blue-500">{icon}</span>
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-400 mb-0.5">{label}</p>
      <p className="text-sm text-gray-800 font-medium leading-snug">{value}</p>
    </div>
  </div>
)

// ── Main Page ─────────────────────────────────────────────────────────────────

const VisitConfirmationPage: React.FC = () => {
  const visitId = useMemo(() => pathVisitId(window.location.pathname), [])
  const token = useMemo(() => queryToken(), [])

  const [data, setData] = useState<ConfirmationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  /** True when the backend returned 409 — the link is consumed by a conflicting action. */
  const [isConflict, setIsConflict] = useState(false)

  useEffect(() => {
    if (!visitId || !token) {
      setError('Invalid confirmation link. Please check your email and try again.')
      setLoading(false)
      return
    }

    // Abort the in-flight request if the component unmounts or visitId/token
    // change mid-fetch. Without this, navigating away and back in quick
    // succession could land a stale response on the new mount (or trigger
    // "setState on unmounted component" warnings in StrictMode).
    const ac = new AbortController()
    let cancelled = false

    api
      .get<ConfirmationData>(
        `/monitor/visits/${encodeURIComponent(visitId)}/confirmation-letter/confirm-data`,
        { params: { token }, signal: ac.signal },
      )
      .then((res) => {
        if (cancelled) return
        setData(res.data)
      })
      .catch((err) => {
        if (cancelled) return
        if ((err as any)?.code === 'ERR_CANCELED' || ac.signal.aborted) return
        const status: number | undefined = (err as any)?.response?.status
        const detail: unknown = (err as any)?.response?.data?.detail
        const msg = typeof detail === 'string' ? detail : 'Could not load confirmation details. Please try again.'
        if (status === 409) {
          setIsConflict(true)
        }
        setError(msg)
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })

    return () => {
      cancelled = true
      ac.abort()
    }
  }, [visitId, token])

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="fixed inset-0 z-[200] flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-10 w-10 text-blue-500 animate-spin" />
          <p className="text-sm text-gray-500 font-medium">Confirming your visit…</p>
        </div>
      </div>
    )
  }

  // ── Conflict: link consumed by an opposing action ──────────────────────────
  if (isConflict) {
    return (
      <div className="fixed inset-0 z-[200] flex items-center justify-center bg-gradient-to-br from-slate-50 via-amber-50 to-orange-100 px-4">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
          <div className="bg-gradient-to-r from-amber-500 to-orange-500 px-8 py-6 text-center">
            <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-white/20 ring-4 ring-white/30">
              <Ban className="h-9 w-9 text-white" strokeWidth={1.8} />
            </div>
            <h1 className="text-xl font-bold text-white">Link No Longer Valid</h1>
          </div>
          <div className="px-8 py-6 text-center">
            <p className="text-sm text-gray-700 leading-relaxed">{error}</p>
            <p className="mt-4 text-xs text-gray-400">
              Each action link can only be used once. If you need to change the visit status,
              please contact your assigned Clinical Research Associate.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Generic error ──────────────────────────────────────────────────────────
  if (error || !data) {
    return (
      <div className="fixed inset-0 z-[200] flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 px-4">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-8 text-center">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-red-50">
            <AlertTriangle className="h-8 w-8 text-red-500" />
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Unable to Confirm Visit</h1>
          <p className="text-sm text-gray-500 leading-relaxed">{error}</p>
        </div>
      </div>
    )
  }

  const { event, visit_label, actor_label, confirmed_by_name, status } = data
  const isAlreadyConfirmed = status === 'already_confirmed'

  // ── Success ────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-[200] overflow-y-auto bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="flex min-h-full items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg">

          {/* Card */}
          <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">

            {/* Top banner */}
            <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-8 py-6 text-center">
              <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-white/20 ring-4 ring-white/30">
                <CheckCircle2 className="h-11 w-11 text-white" strokeWidth={1.8} />
              </div>
              <h1 className="text-2xl font-bold text-white tracking-tight">
                {isAlreadyConfirmed ? 'Already Confirmed' : 'Visit Confirmed!'}
              </h1>
              <p className="mt-1.5 text-blue-100 text-sm">
                {isAlreadyConfirmed
                  ? `You have already confirmed ${visit_label}. No further action is needed.`
                  : `Thank you, ${confirmed_by_name}. Your confirmation has been recorded.`}
              </p>
            </div>

            {/* Body */}
            <div className="px-6 py-5">

              {/* Status badge */}
              <div className="mb-5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CalendarCheck className="h-4 w-4 text-green-600" />
                  <span className="text-xs font-semibold uppercase tracking-widest text-green-700">
                    Confirmed
                  </span>
                </div>
                <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                  {actor_label}
                </span>
              </div>

              {/* Visit info rows */}
              <div className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-1 mb-6">
                <InfoRow
                  icon={<FileText className="h-4 w-4" />}
                  label="Visit"
                  value={event.title}
                />
                <InfoRow
                  icon={<Calendar className="h-4 w-4" />}
                  label="Date"
                  value={
                    isSameUtcDay(event.start_utc, event.end_utc)
                      ? formatUtcDate(event.start_utc)
                      : `${formatUtcDate(event.start_utc)} → ${formatUtcDate(event.end_utc)}`
                  }
                />
                <InfoRow
                  icon={<Clock className="h-4 w-4" />}
                  label="Time"
                  value={`${formatUtcTime(event.start_utc)} → ${formatUtcTime(event.end_utc)}`}
                />
                <InfoRow
                  icon={<MapPin className="h-4 w-4" />}
                  label="Location"
                  value={event.location || 'TBD'}
                />
                <InfoRow
                  icon={<User className="h-4 w-4" />}
                  label="Confirmed by"
                  value={`${confirmed_by_name} (${actor_label})`}
                />
              </div>

              {/* Calendar actions */}
              <div>
                <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-400">
                  Add to your calendar
                </p>
                <div className="flex flex-col gap-3 sm:flex-row">
                  {/* Google Calendar */}
                  <a
                    href={buildGoogleCalendarUrl(event)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex flex-1 items-center justify-center gap-2.5 rounded-xl border-2 border-blue-100 bg-white px-4 py-3 text-sm font-semibold text-blue-700 shadow-sm transition hover:border-blue-300 hover:bg-blue-50 hover:shadow-md active:scale-[0.98]"
                  >
                    {/* Google Calendar wordmark icon */}
                    <svg className="h-5 w-5 flex-shrink-0" viewBox="0 0 48 48" aria-hidden="true">
                      <rect width="48" height="48" rx="6" fill="#fff" />
                      <rect x="6" y="6" width="36" height="36" rx="4" fill="#fff" stroke="#e2e8f0" strokeWidth="1" />
                      <rect x="6" y="6" width="36" height="10" rx="4" fill="#1a73e8" />
                      <rect x="6" y="12" width="36" height="4" fill="#1a73e8" />
                      <text x="24" y="34" textAnchor="middle" fontSize="16" fontWeight="700" fill="#1a73e8" fontFamily="Arial">
                        {new Date(event.start_utc).getUTCDate()}
                      </text>
                    </svg>
                    Add to Google Calendar
                  </a>

                  {/* Download .ics */}
                  <button
                    type="button"
                    onClick={() => downloadIcs(event, visitId!)}
                    className="flex flex-1 items-center justify-center gap-2.5 rounded-xl border-2 border-indigo-100 bg-white px-4 py-3 text-sm font-semibold text-indigo-700 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-50 hover:shadow-md active:scale-[0.98]"
                  >
                    <Download className="h-4 w-4 flex-shrink-0" />
                    Download .ics
                  </button>
                </div>

                <p className="mt-3 text-center text-xs text-gray-400">
                  .ics works with Apple Calendar, Outlook, and all major calendar apps.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="border-t border-gray-100 bg-gray-50 px-6 py-4 text-center">
              <p className="text-xs text-gray-400">
                Powered by{' '}
                <span className="font-semibold text-gray-500">Dizzaroo CRM</span>
                {' · '}
                You can safely close this tab.
              </p>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}

export default VisitConfirmationPage
