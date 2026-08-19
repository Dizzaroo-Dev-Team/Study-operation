import React, { useMemo, useState } from 'react'
import { useStudyTeam } from '@/lib/queries/useStudies'
import { useStudySite } from '../../../contexts/StudySiteContext'

interface StudyAccess {
  id: string
  name: string
  study_id: string
  role: string | null
}

interface StudyTeamRow {
  user_id: string
  email: string | null
  name: string
  status: string
  studies: StudyAccess[]
}

const STATUS_PILL: Record<string, string> = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  inactive: 'bg-amber-50 text-amber-700 border-amber-200',
  pending: 'bg-blue-50 text-blue-700 border-blue-200',
  unknown: 'bg-slate-100 text-slate-600 border-slate-200',
}

const formatRole = (role: string | null): string => {
  if (!role) return '—'
  return role
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

const initialsOf = (name: string): string => {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('') || '?'
}

const StudyTeam: React.FC = () => {
  const { selectedStudyId, studies } = useStudySite()
  const [search, setSearch] = useState('')
  const [scope, setScope] = useState<'this-study' | 'all'>('this-study')

  const studyName = useMemo(() => {
    const s = studies.find((x) => x.id === selectedStudyId)
    return s?.name || ''
  }, [studies, selectedStudyId])

  const teamQuery = useStudyTeam(selectedStudyId, { scopeAll: scope === 'all' })
  const allRows: StudyTeamRow[] = useMemo(() => {
    const rows = teamQuery.data?.data
    return Array.isArray(rows) ? (rows as StudyTeamRow[]) : []
  }, [teamQuery.data])
  const loading = teamQuery.isFetching
  const error = useMemo(() => {
    if (!teamQuery.isError) return null
    const err = teamQuery.error as any
    return err?.response?.data?.detail || err?.message || 'Failed to load study team'
  }, [teamQuery.isError, teamQuery.error])

  const visibleRows = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return allRows
    return allRows.filter((r) => {
      const haystack = [
        r.name,
        r.email || '',
        r.user_id,
        ...r.studies.map((s) => s.name),
        ...r.studies.map((s) => s.role || ''),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(q)
    })
  }, [allRows, search])

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-5" data-testid="study-team-header">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900">Users / Study Team</h2>
          <p className="text-sm text-slate-500 mt-1">
            Sourced from IAM hub. Scope and roles are managed in IAM — this view is read-only.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1">
              Scope
            </label>
            <div className="inline-flex rounded-lg border border-slate-300 overflow-hidden text-xs font-medium">
              <button
                type="button"
                onClick={() => setScope('this-study')}
                className={`px-3 py-1.5 transition-colors ${
                  scope === 'this-study'
                    ? 'bg-[#168AAD] text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {studyName ? `This study (${studyName})` : 'This study'}
              </button>
              <button
                type="button"
                onClick={() => setScope('all')}
                className={`px-3 py-1.5 transition-colors border-l border-slate-300 ${
                  scope === 'all'
                    ? 'bg-[#168AAD] text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                All studies
              </button>
            </div>
          </div>
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1">
              Search
            </label>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name, email, role, study…"
              className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#168AAD] focus:border-[#168AAD] min-w-[240px]"
            />
          </div>
        </div>
      </div>

      {/* States */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-lg border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Loading study team…
        </div>
      ) : visibleRows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
          <p className="text-sm font-semibold text-slate-700">No users found</p>
          <p className="mt-1 text-xs text-slate-500">
            {scope === 'this-study'
              ? 'No IAM users have access to this study yet. Grant access via the IAM admin app.'
              : 'No IAM users have any study access in this application yet.'}
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="text-left px-4 py-2.5">User</th>
                  <th className="text-left px-4 py-2.5">Email</th>
                  <th className="text-left px-4 py-2.5">
                    {scope === 'this-study' ? 'Role' : 'Studies & roles'}
                  </th>
                  <th className="text-left px-4 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visibleRows.map((row) => {
                  const status = (row.status || 'unknown').toLowerCase()
                  const pill = STATUS_PILL[status] || STATUS_PILL.unknown
                  const studiesForCurrent =
                    scope === 'this-study' && selectedStudyId
                      ? row.studies.filter((s) => s.id === selectedStudyId)
                      : row.studies
                  return (
                    <tr key={row.user_id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-[#168AAD] to-[#76C893] text-white text-xs font-semibold flex items-center justify-center">
                            {initialsOf(row.name)}
                          </div>
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-slate-900 truncate">{row.name}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-700">
                        {row.email ? (
                          <a className="hover:underline text-[#168AAD]" href={`mailto:${row.email}`}>
                            {row.email}
                          </a>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          {studiesForCurrent.length === 0 ? (
                            <span className="text-slate-400">—</span>
                          ) : (
                            studiesForCurrent.map((s) => (
                              <span
                                key={s.id}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-slate-200 bg-slate-50 text-[11px]"
                                title={`${s.name} (${formatRole(s.role)})`}
                              >
                                <span className="font-medium text-slate-700">{s.name}</span>
                                {s.role && (
                                  <span className="text-slate-400">·</span>
                                )}
                                {s.role && (
                                  <span className="text-[10px] text-slate-500">{formatRole(s.role)}</span>
                                )}
                              </span>
                            ))
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide ${pill}`}
                        >
                          {row.status || 'unknown'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2.5 text-[11px] text-slate-500 border-t border-slate-200 bg-slate-50/60">
            Showing {visibleRows.length} {visibleRows.length === 1 ? 'user' : 'users'}
            {scope === 'this-study' && studyName && <> on <span className="font-medium text-slate-700">{studyName}</span></>}
          </div>
        </div>
      )}
    </div>
  )
}

export default StudyTeam
