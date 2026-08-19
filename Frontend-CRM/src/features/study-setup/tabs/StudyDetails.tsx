// Study Details (read-only for v1). Fields we already hold come from the study
// record; fields sourced from other systems show a clear placeholder until those
// integrations land.
import React from 'react'
import { useStudySite } from '../../../contexts/StudySiteContext'

// Shown in place of any field whose data lives in another application and will be
// pulled in via a later integration.
const FETCH_LATER = 'Will be fetched from other application'

const StudyDetails: React.FC = () => {
  const { studies, selectedStudyId, loading } = useStudySite()
  const study = studies.find((s) => s.id === selectedStudyId) ?? null

  if (loading) {
    return <div className="p-6 text-sm text-slate-500">Loading study…</div>
  }
  if (!study) {
    return <div className="p-6 text-sm text-slate-500">Select a study from the navbar.</div>
  }

  // value === undefined  → not in our app yet → render the FETCH_LATER placeholder.
  const fields: { label: string; value?: string | null }[] = [
    { label: 'Study Full Title', value: study.name },
    { label: 'Therapeutic Area', value: undefined },
    { label: 'Indication', value: undefined },
    { label: 'Study Phase', value: undefined },
    { label: 'Study Design', value: undefined },
    { label: 'Sponsor Name', value: undefined },
    { label: 'Sponsor Address', value: undefined },
    { label: 'Protocol Version', value: undefined },
    { label: 'Current Study Status', value: study.status },
  ]

  return (
    <div className="p-6">
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden" data-testid="study-details-card">
        <div className="px-5 py-4 border-b border-slate-200">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Study Details</p>
          <h2 className="mt-1 text-lg font-bold text-slate-800">{study.name}</h2>
        </div>
        <dl className="divide-y divide-slate-100">
          {fields.map((f) => {
            const hasValue = f.value !== undefined && f.value !== null && String(f.value).trim() !== ''
            return (
              <div key={f.label} className="grid grid-cols-1 sm:grid-cols-3 gap-1 sm:gap-4 px-5 py-3">
                <dt className="text-sm font-medium text-slate-600">{f.label}</dt>
                <dd className="sm:col-span-2 text-sm">
                  {hasValue ? (
                    <span className="text-slate-800">{f.value}</span>
                  ) : (
                    <span className="italic text-slate-400">{FETCH_LATER}</span>
                  )}
                </dd>
              </div>
            )
          })}
        </dl>
      </div>
    </div>
  )
}

export default StudyDetails
