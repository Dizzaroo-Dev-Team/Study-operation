import React, { useMemo, useState } from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'
import SiteRequiredPrompt from '@/components/SiteRequiredPrompt'
import { useSiteProfile } from '@/lib/queries/useSiteProfile'
import { useStudyTeam } from '@/lib/queries/useStudies'

// ── Role colour palette (matches reference image) ──────────────────────────
const ROLE_COLORS: Record<string, { bg: string; text: string }> = {
  'Principal Investigator':      { bg: '#e0f2fe', text: '#0369a1' },
  'Sub Investigator':            { bg: '#e0e7ff', text: '#4338ca' },
  'Site Coordinator (CRC)':      { bg: '#d1fae5', text: '#065f46' },
  'Site Head':                   { bg: '#fef9c3', text: '#92400e' },
}

function roleStyle(role: string) {
  return ROLE_COLORS[role] ?? { bg: '#f3f4f6', text: '#374151' }
}

const STATUS_STYLE: Record<string, string> = {
  active:   'bg-emerald-100 text-emerald-700',
  inactive: 'bg-red-100 text-red-600',
  'on leave': 'bg-amber-100 text-amber-700',
}

const normalizeName = (name: string) => name.trim().toLowerCase()

interface StaffRow {
  key: string
  staff_name: string
  role_label: string
  email: string | null
  phone: string | null
  status: string
}

// ── Main tab ────────────────────────────────────────────────────────────────
// Shows only the named contacts actually saved on the Site Profile tab for
// this site (PI, Sub Investigator, Site Coordinator/CRC, Site Head) — not the
// full study team roster (that lives under Study Setup → Users / Study Team).
const SiteStaffDetailsTab: React.FC = () => {
  const { selectedSiteId, selectedStudyId, filteredSites } = useStudySite()
  const profileQuery = useSiteProfile(selectedSiteId)
  const teamQuery = useStudyTeam(selectedStudyId)
  const [searchQuery, setSearchQuery] = useState('')

  const selectedSiteName = useMemo(() => {
    const site = filteredSites.find((x) => x.id === selectedSiteId || x.site_id === selectedSiteId)
    return site?.name?.trim() || ''
  }, [filteredSites, selectedSiteId])

  const statusByName = useMemo(() => {
    const rows = teamQuery.data?.data ?? []
    const map = new Map<string, string>()
    rows.forEach((r: any) => {
      if (r?.name) map.set(normalizeName(r.name), r.status || 'unknown')
    })
    return map
  }, [teamQuery.data])

  const staff: StaffRow[] = useMemo(() => {
    const profile = profileQuery.data
    if (!profile) return []

    const candidates: { key: string; name?: string | null; email?: string | null; phone?: string | null; role_label: string }[] = [
      { key: 'pi', name: profile.pi_name, email: profile.pi_email, phone: profile.pi_phone, role_label: 'Principal Investigator' },
      { key: 'sub_investigator', name: profile.sub_investigator_name, email: profile.sub_investigator_email, phone: profile.sub_investigator_phone, role_label: 'Sub Investigator' },
      { key: 'site_coordinator', name: profile.site_coordinator_name, email: profile.site_coordinator_email, phone: profile.site_coordinator_phone, role_label: 'Site Coordinator (CRC)' },
      { key: 'site_head', name: profile.site_head_name, email: profile.site_head_email, phone: profile.site_head_phone, role_label: 'Site Head' },
    ]

    return candidates
      .filter((c) => c.name && c.name.trim())
      .map((c) => ({
        key: c.key,
        staff_name: c.name!.trim(),
        role_label: c.role_label,
        email: c.email ?? null,
        phone: c.phone ?? null,
        status: statusByName.get(normalizeName(c.name!)) || 'active',
      }))
  }, [profileQuery.data, statusByName])

  if (!selectedSiteId) {
    return <SiteRequiredPrompt fullPage feature="site staff details" />
  }

  const loading = profileQuery.isLoading

  const filtered = staff.filter((s) => {
    const q = searchQuery.toLowerCase()
    return (
      !q ||
      s.staff_name.toLowerCase().includes(q) ||
      s.role_label.toLowerCase().includes(q) ||
      (s.email ?? '').toLowerCase().includes(q)
    )
  })

  return (
    <div className="h-full w-full overflow-y-auto bg-gray-50">
      <div className="p-6 max-w-6xl mx-auto space-y-4">

        {/* Header card */}
        <div
          className="rounded-2xl shadow-sm p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
          style={{ background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)' }}
          data-testid="site-staff-header"
        >
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-white">Site Staff Details</h1>
              {selectedSiteName && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-white/20 border border-white/30 text-xs font-semibold text-white">
                  {selectedSiteName}
                </span>
              )}
            </div>
            <p className="text-sm text-white/80 mt-0.5">
              Contacts saved on this site's Site Profile (PI, Sub Investigator, CRC, Site Head)
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/60 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
              </svg>
              <input
                type="text"
                placeholder="Search staff…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-2 bg-white/20 border border-white/30 rounded-lg text-sm text-white placeholder:text-white/60 focus:outline-none focus:ring-2 focus:ring-white/50 w-44"
              />
            </div>
          </div>
        </div>

        {/* Table card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden" data-testid="site-staff-table">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-gray-500 text-sm">
              <svg className="animate-spin w-5 h-5 mr-2 text-[#168AAD]" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="60" strokeLinecap="round"/>
              </svg>
              Loading staff...
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-400 gap-3">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" className="text-gray-300">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
              <p className="text-sm font-medium">
                {searchQuery
                  ? 'No staff match your search.'
                  : 'No contacts saved yet. Fill in PI, Sub Investigator, CRC, or Site Head on the Site Profile tab.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ background: 'linear-gradient(135deg, #0e6c8b 0%, #3e9e6e 100%)' }}>
                    {['Staff Name', 'Study Role', 'Email', 'Status'].map((h) => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-bold text-white uppercase tracking-wider whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s, i) => {
                    const rs = roleStyle(s.role_label)
                    const statusKey = (s.status || 'unknown').toLowerCase()
                    return (
                      <tr
                        key={s.key}
                        className={`border-b border-gray-100 hover:bg-blue-50/40 transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/60'}`}
                      >
                        <td className="px-4 py-3.5 font-semibold text-gray-800 whitespace-nowrap">
                          {s.staff_name}
                        </td>
                        <td className="px-4 py-3.5">
                          <span
                            className="px-2.5 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap"
                            style={{ background: rs.bg, color: rs.text }}
                          >
                            {s.role_label}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-gray-600">{s.email || '—'}</td>
                        <td className="px-4 py-3.5">
                          <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase ${STATUS_STYLE[statusKey] ?? 'bg-gray-100 text-gray-600'}`}>
                            {s.status}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {filtered.length > 0 && (
            <div className="px-4 py-2.5 border-t border-gray-100 text-xs text-gray-400 flex justify-between">
              <span>{filtered.length} staff member{filtered.length !== 1 ? 's' : ''}{searchQuery ? ' found' : ' total'}</span>
              <span>{staff.filter((s) => (s.status || '').toLowerCase() === 'active').length} active</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default SiteStaffDetailsTab
