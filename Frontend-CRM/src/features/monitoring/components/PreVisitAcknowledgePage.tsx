import React, { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Loader2, AlertTriangle } from 'lucide-react'
import { acknowledgePreVisitReport } from '@/components/mon/services/monitorService'

const pathVisitId = (pathname: string): string | null => {
  const m = pathname.match(/^\/monitoring\/visits\/([^/]+)\/pre-visit-report\/acknowledge\/?$/)
  return m ? decodeURIComponent(m[1]) : null
}

const PreVisitAcknowledgePage: React.FC = () => {
  const visitId = useMemo(() => pathVisitId(window.location.pathname), [])
  const token = useMemo(() => new URLSearchParams(window.location.search).get('token') || '', [])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [already, setAlready] = useState(false)

  useEffect(() => {
    if (!visitId || !token) {
      setError('This link is invalid or incomplete.')
      setLoading(false)
      return
    }

    const run = async () => {
      try {
        setLoading(true)
        setError(null)
        const res = await acknowledgePreVisitReport(visitId, token)
        setDone(true)
        setAlready(Boolean(res?.already))
      } catch (e: unknown) {
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setError(typeof detail === 'string' ? detail : 'Could not record acknowledgment.')
      } finally {
        setLoading(false)
      }
    }

    void run()
  }, [visitId, token])

  return (
    <div className="fixed inset-0 z-[220] flex items-center justify-center bg-gradient-to-br from-slate-50 via-indigo-50 to-slate-100 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-xl text-center">
        {loading && (
          <>
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-indigo-600" />
            <p className="mt-4 text-sm text-slate-600">Confirming acknowledgment…</p>
          </>
        )}
        {!loading && error && (
          <>
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-red-50">
              <AlertTriangle className="h-7 w-7 text-red-600" />
            </div>
            <h1 className="text-lg font-bold text-slate-900">Unable to acknowledge</h1>
            <p className="mt-2 text-sm text-red-700">{error}</p>
          </>
        )}
        {!loading && !error && done && (
          <>
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50">
              <CheckCircle2 className="h-8 w-8 text-emerald-600" strokeWidth={2} />
            </div>
            <h1 className="text-xl font-bold text-slate-900">
              {already ? 'Already acknowledged' : 'Thank you'}
            </h1>
            <p className="mt-2 text-sm text-slate-600">
              {already
                ? 'This pre-visit summary was already acknowledged. No further action is needed.'
                : 'Your acknowledgment of the pre-visit summary has been recorded. The study team has been notified.'}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export default PreVisitAcknowledgePage
