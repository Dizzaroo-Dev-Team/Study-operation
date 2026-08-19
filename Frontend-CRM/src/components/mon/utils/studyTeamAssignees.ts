/** Minimal row shape from GET /study-team (same as Study Setup → Users / Study Team). */
export interface StudyTeamMemberRow {
  user_id?: string
  email?: string | null
  name: string
  status?: string
  role?: string | null
  studies?: Array<{ id?: string; study_id?: string; name?: string; role?: string | null }>
}

export interface StudyTeamAssigneeOption {
  name: string
  role?: string
  label: string
}

export function formatStudyTeamRole(role: string | null | undefined): string {
  const raw = String(role ?? '').trim()
  if (!raw) return ''
  const normalized = raw.toLowerCase().replace(/[\s-]+/g, '_')
  const labels: Record<string, string> = {
    cra: 'CRA',
    clinical_research_associate: 'CRA',
    principal_investigator: 'PI',
    investigator: 'PI',
    pi: 'PI',
    study_coordinator: 'Coordinator',
    site_coordinator: 'Coordinator',
    coordinator: 'Coordinator',
    study_manager: 'Study Manager',
    medical_monitor: 'Medical Monitor',
    sponsor: 'Sponsor',
  }
  return labels[normalized] || raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** True if a raw study-team role string represents a CRA (Clinical Research Associate). */
export function isCraRole(role: string | null | undefined): boolean {
  return formatStudyTeamRole(role) === 'CRA'
}

const BADGE_COLORS = ['blue', 'purple', 'green', 'teal', 'orange', 'red'] as const
const UUID_LIKE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

/** Match Study Setup tab: first letter of up to two name parts. */
export function initialsFromDisplayName(name: string): string {
  if (!name?.trim()) return '?'
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const letters = parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
  return letters || '?'
}

/** Stable avatar color for any IAM user name (no static CRA list). */
export function assigneeBadgeFromName(name: string): {
  initials: string
  name: string
  color: (typeof BADGE_COLORS)[number]
} {
  const n = name.trim() || '?'
  return {
    initials: initialsFromDisplayName(n),
    name: n,
    color: BADGE_COLORS[hashString(n) % BADGE_COLORS.length],
  }
}

/**
 * Build sorted assignee display names for monitoring dropdowns.
 * Excludes `inactive` users; includes active, pending, unknown, or missing status.
 */
export function studyTeamRowsToAssigneeNames(rows: unknown, opts?: { onlyCra?: boolean }): string[] {
  return studyTeamRowsToAssigneeOptions(rows, opts).map((option) => option.name)
}

export function studyTeamRowsToAssigneeOptions(
  rows: unknown,
  opts?: { onlyCra?: boolean },
): StudyTeamAssigneeOption[] {
  if (!Array.isArray(rows)) return []
  const byName = new Map<string, StudyTeamAssigneeOption>()
  for (const raw of rows) {
    if (!raw || typeof raw !== 'object') continue
    const r = raw as StudyTeamMemberRow
    const status = String(r.status ?? '').toLowerCase()
    if (status === 'inactive') continue
    const name = typeof r.name === 'string' ? r.name.trim() : ''
    if (!name) continue
    if (UUID_LIKE.test(name)) continue
    const rawRole = r.role || r.studies?.find((s) => s?.role)?.role
    if (opts?.onlyCra && !isCraRole(rawRole)) continue
    const role = formatStudyTeamRole(rawRole)
    byName.set(name, {
      name,
      role: role || undefined,
      label: role ? `${name} (${role})` : name,
    })
  }
  return [...byName.values()].sort((a, b) => a.name.localeCompare(b.name))
}

/** Shape from StudySiteContext / GET /studies — only fields needed for resolution. */
export type StudyPickerRow = { id: string; study_id: string; name: string }

/**
 * GET /study-team expects the Mongo IAM study resource id (same as `Study.id` from GET /studies).
 * Monitoring APIs often store `study_id` as Postgres UUID text or human protocol code instead —
 * map those to the roster study id when possible; otherwise fall back to the navbar selection.
 */
export function resolveIamStudyResourceIdForStudyTeam(
  visitOrRowStudyHint: string | null | undefined,
  studies: StudyPickerRow[],
  selectedStudyId: string | null,
): string | null {
  const hint = (visitOrRowStudyHint || '').trim()
  if (hint) {
    if (studies.some((s) => s.id === hint)) return hint
    const byCode = studies.find((s) => s.study_id === hint || s.name === hint)
    if (byCode) return byCode.id
  }
  return selectedStudyId
}
