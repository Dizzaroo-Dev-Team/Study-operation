import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  deletePolicyDocument,
  listPolicyDocuments,
  uploadPolicyDocument,
} from './services/budgeting.api'
import type { PolicyDocSummary } from './services/budgeting.api'
import { btn, table as t } from './ui'
import { COUNTRY_TO_CURRENCY } from './country_currency'

type Props = {
  trialId: string
}

const COUNTRY_OPTIONS = Object.keys(COUNTRY_TO_CURRENCY).sort()

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

export const PolicyDocs: React.FC<Props> = ({ trialId }) => {
  const [docs, setDocs] = useState<PolicyDocSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [country, setCountry] = useState<string>(COUNTRY_OPTIONS[0] ?? '')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    if (!trialId) {
      setLoading(false)
      setDocs([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const rows = await listPolicyDocuments(trialId)
      setDocs(rows)
    } catch (e: any) {
      const status = e?.response?.status ?? 0
      if (status === 0 || status >= 500) setError('Could not load policy documents.')
      setDocs([])
    } finally {
      setLoading(false)
    }
  }, [trialId])

  useEffect(() => { void load() }, [load])

  const grouped = useMemo(() => {
    const m = new Map<string, PolicyDocSummary[]>()
    for (const d of docs) {
      const list = m.get(d.country_code) ?? []
      list.push(d)
      m.set(d.country_code, list)
    }
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [docs])

  // Set of country codes that already have at least one policy document.
  // Drives the green-vs-grey chip colour below. Recomputed cheaply on every
  // docs change — small list, no need to memoise the Set itself separately.
  const uploadedCountries = useMemo(
    () => new Set(docs.map((d) => d.country_code)),
    [docs],
  )
  const countDocsForCountry = useCallback(
    (cc: string) => docs.reduce((n, d) => (d.country_code === cc ? n + 1 : n), 0),
    [docs],
  )

  const submit = async () => {
    if (!file || !country) return
    setUploading(true)
    setUploadError(null)
    try {
      await uploadPolicyDocument(trialId, country, file)
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      await load()
    } catch (e: any) {
      setUploadError(e?.response?.data?.detail ?? e?.message ?? 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const remove = async (doc: PolicyDocSummary) => {
    if (!confirm(`Delete "${doc.file_name}" (${doc.country_code})?`)) return
    try {
      await deletePolicyDocument(trialId, doc.id)
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800">Country Policy Documents</h3>
        <p className="mt-1 text-sm text-slate-500">
          Upload regulatory / policy documents tagged by country. When you switch to a Country tab and
          regenerate milestones, the LLM reads every document for that country and extracts country-specific
          milestones.
        </p>
      </div>

      {/* Upload form. Country picker is now a horizontal strip of chips
          instead of a dropdown — gives an at-a-glance map of upload coverage
          (green = has at least one doc, grey = none yet) without forcing the
          user to open a select to find out. Clicking a chip picks it as the
          target for the next upload. */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
        <div>
          <div className="flex items-baseline justify-between">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Country
            </label>
            <span className="text-[11px] text-slate-400">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 mr-1 align-middle" />
              has document
              <span className="inline-block h-2 w-2 rounded-full bg-slate-300 ml-3 mr-1 align-middle" />
              none yet
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Select country">
            {COUNTRY_OPTIONS.map((cc) => {
              const hasDoc = uploadedCountries.has(cc)
              const isSelected = country === cc
              const docCount = countDocsForCountry(cc)
              const base =
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1'
              const tone = hasDoc
                ? 'bg-emerald-50 text-emerald-800 border-emerald-300 hover:bg-emerald-100 focus:ring-emerald-400'
                : 'bg-slate-50 text-slate-600 border-slate-300 hover:bg-slate-100 focus:ring-slate-400'
              const selectedRing = isSelected
                ? hasDoc
                  ? 'ring-2 ring-emerald-500 ring-offset-1'
                  : 'ring-2 ring-indigo-500 ring-offset-1'
                : ''
              return (
                <button
                  key={cc}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  onClick={() => setCountry(cc)}
                  disabled={uploading}
                  className={`${base} ${tone} ${selectedRing} disabled:opacity-50 disabled:cursor-not-allowed`}
                  title={
                    hasDoc
                      ? `${cc} — ${docCount} document${docCount === 1 ? '' : 's'}`
                      : `${cc} — no documents yet`
                  }
                >
                  {/* dot indicator so the state is clear even for users with
                      reduced colour perception */}
                  <span
                    aria-hidden="true"
                    className={`h-2 w-2 rounded-full ${hasDoc ? 'bg-emerald-500' : 'bg-slate-400'}`}
                  />
                  <span>{cc}</span>
                  {hasDoc && (
                    <span className="text-[10px] font-medium text-emerald-700/80">
                      ({docCount})
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[260px]">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Policy file (PDF/DOCX) for{' '}
              <span className="text-slate-700 font-bold">{country || '—'}</span>
            </label>
            <div className="mt-1.5 flex items-center gap-2">
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm text-slate-700 file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border-0 file:bg-indigo-50 file:text-indigo-700 file:font-medium hover:file:bg-indigo-100"
                disabled={uploading || !country}
              />
            </div>
          </div>

          <button
            type="button"
            disabled={!file || !country || uploading}
            onClick={() => void submit()}
            className={btn.primary}
          >
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
        </div>

        {file && !uploading && (
          <p className="text-xs text-slate-500">
            Selected: <span className="font-medium text-slate-700">{file.name}</span> · {fmtBytes(file.size)}
          </p>
        )}
        {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}
      </div>

      {/* Document list */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500 py-4">
          <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          Loading documents…
        </div>
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : grouped.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">
          No policy documents uploaded yet.
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map(([cc, list]) => (
            <div key={cc} className="rounded-lg border border-slate-200 bg-white overflow-hidden">
              <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-700">{cc}</span>
                <span className="text-xs text-slate-400">({list.length} document{list.length !== 1 ? 's' : ''})</span>
              </div>
              <table className={t.base}>
                <thead className={t.thead}>
                  <tr>
                    <th className={t.th}>File</th>
                    <th className={t.th}>Size</th>
                    <th className={t.th}>Uploaded</th>
                    <th className={t.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((d) => (
                    <tr key={d.id} className={t.row}>
                      <td className={`${t.td} font-medium text-slate-800`}>{d.file_name}</td>
                      <td className={`${t.td} text-slate-600 font-mono text-xs`}>{fmtBytes(d.file_size)}</td>
                      <td className={`${t.td} text-slate-500 text-xs`}>
                        {d.uploaded_at ? new Date(d.uploaded_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <button
                          type="button"
                          onClick={() => void remove(d)}
                          className={btn.iconDanger}
                          title="Delete"
                        >
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
