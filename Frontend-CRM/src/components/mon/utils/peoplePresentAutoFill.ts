import { api } from '@/lib/api'
import type { StudyTeamMemberRow } from './studyTeamAssignees'
import type { MvrTableRow } from '../components/views/visit-detail/visitReportFormDefaults'

export type PeoplePresentRows = {
  sitePersonnelRows: MvrTableRow[]
  monitorPersonnelRows: MvrTableRow[]
  otherPersonnelRows: MvrTableRow[]
}

export type PeoplePresentFetchOptions = {
  /** Mongo IAM study resource id — same as navbar / GET /studies → Study.id. */
  studyIamId: string
  /** Human study code e.g. MK-6482 — strips prefix from IAM role labels. */
  studyCode?: string | null
}

const EMPTY_ROW: MvrTableRow = { name: '', role: '' }

function normalizeRole(value: string): string {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, ' ')
}

/** IAM roles often look like "MK-6482 CRA" or "MK-6482 Principal Investigator". */
export function parseIamStudyRole(
  rawRole: string,
  studyCode?: string | null,
): string {
  let role = String(rawRole || '').trim()
  if (!role) return ''

  const code = String(studyCode || '').trim()
  if (code) {
    const escaped = code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    role = role.replace(new RegExp(`^${escaped}[\\s:_-]+`, 'i'), '').trim()
  }

  const tokenSplit = role.match(/^[A-Z0-9][A-Z0-9._-]*\s+(.+)$/i)
  if (tokenSplit?.[1]) {
    role = tokenSplit[1].trim()
  }

  return role
}

export function roleForStudyMember(
  row: StudyTeamMemberRow,
  studyIamId: string,
  studyCode?: string | null,
): string {
  const memberStudies = Array.isArray(row.studies) ? row.studies : []
  const match =
    memberStudies.find(
      (s) => String((s as { id?: string }).id || '') === studyIamId,
    ) ||
    (studyCode
      ? memberStudies.find(
          (s) =>
            String((s as { study_id?: string }).study_id || '') === studyCode ||
            String((s as { name?: string }).name || '') === studyCode,
        )
      : undefined) ||
    memberStudies[0]
  const raw = (match as { role?: string | null })?.role || ''
  return parseIamStudyRole(String(raw), studyCode)
}

export function displayPeoplePresentRole(role: string): string {
  const key = normalizeRole(role)
  if (key === 'cra' || key === 'clinical research associate') return 'CRA'
  if (key === 'principal investigator' || key === 'pi') return 'Principal Investigator'
  if (
    key.includes('sub') &&
    (key.includes('investigator') || key.includes('principal'))
  ) {
    return 'Sub-Investigator'
  }
  if (key === 'clinical research coordinator' || key === 'crc') return 'CRC'
  if (key === 'study manager' || key === 'study_manager') return 'Study Manager'
  if (key === 'medical monitor') return 'Medical Monitor'
  if (key === 'sponsor') return 'Sponsor'
  return String(role || '')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function isSitePersonnelRole(role: string): boolean {
  const key = normalizeRole(role)
  if (key === 'principal investigator' || key === 'pi') return true
  if (
    key.includes('sub') &&
    (key.includes('investigator') || key.includes('principal'))
  ) {
    return true
  }
  if (key === 'clinical research coordinator' || key === 'crc') return true
  return false
}

export function isMonitorPersonnelRole(role: string): boolean {
  const key = normalizeRole(role)
  return key === 'cra' || key === 'clinical research associate'
}

export function personnelRowsAreEmpty(rows: MvrTableRow[] | undefined): boolean {
  if (!rows?.length) return true
  return rows.every(
    (row) =>
      !String(row.role || '').trim() &&
      !String(row.name || '').trim(),
  )
}

function rowKey(role: string, name: string): string {
  return `${normalizeRole(role)}|${name.trim().toLowerCase()}`
}

function pushRow(
  bucket: MvrTableRow[],
  seen: Set<string>,
  role: string,
  name: string,
) {
  const cleanName = name.trim()
  if (!cleanName) return
  const displayRole = displayPeoplePresentRole(role)
  const key = rowKey(displayRole, cleanName)
  if (seen.has(key)) return
  seen.add(key)
  bucket.push({
    name: cleanName,
    role: displayRole,
  })
}

function withDefaultRows(rows: MvrTableRow[]): MvrTableRow[] {
  return rows.length > 0 ? rows : [{ ...EMPTY_ROW }]
}

export type SiteProfilePersonnelInput = {
  piName?: string | null
  subInvestigatorName?: string | null
  siteCoordinatorName?: string | null
  siteHeadName?: string | null
  /** CRA assigned to this specific visit (from visit overview / Assign CRA). */
  craName?: string | null
}

/**
 * Build People Present from the current site's Site Profile contacts (PI,
 * Sub Investigator, CRC, Site Head) plus the CRA assigned to this visit —
 * mirrors what's actually shown on the Site Profile / Site Staff Details
 * tabs and the visit's Assign CRA field, instead of the whole study team.
 */
export function buildPeoplePresentFromSiteProfile(
  input: SiteProfilePersonnelInput,
): PeoplePresentRows {
  const sitePersonnel: MvrTableRow[] = []
  const monitorPersonnel: MvrTableRow[] = []
  const seenSite = new Set<string>()
  const seenMonitor = new Set<string>()

  pushRow(sitePersonnel, seenSite, 'Principal Investigator', input.piName || '')
  pushRow(sitePersonnel, seenSite, 'Sub-Investigator', input.subInvestigatorName || '')
  pushRow(sitePersonnel, seenSite, 'CRC', input.siteCoordinatorName || '')
  pushRow(sitePersonnel, seenSite, 'Site Head', input.siteHeadName || '')
  pushRow(monitorPersonnel, seenMonitor, 'CRA', input.craName || '')

  return {
    sitePersonnelRows: withDefaultRows(sitePersonnel),
    monitorPersonnelRows: withDefaultRows(monitorPersonnel),
    otherPersonnelRows: withDefaultRows([]),
  }
}

/**
 * Build People Present from the current study's IAM users
 * (Study Setup → Users / Study Team, GET /study-team?study_id=…).
 */
export async function fetchPeoplePresentRows(
  options: PeoplePresentFetchOptions,
): Promise<PeoplePresentRows> {
  const { studyIamId, studyCode } = options
  const sitePersonnel: MvrTableRow[] = []
  const monitorPersonnel: MvrTableRow[] = []
  const otherPersonnel: MvrTableRow[] = []
  const seenSite = new Set<string>()
  const seenMonitor = new Set<string>()
  const seenOther = new Set<string>()

  const teamRes = await api.get<{ data?: StudyTeamMemberRow[] }>('/study-team', {
    params: { study_id: studyIamId },
  })

  for (const row of teamRes.data?.data ?? []) {
    if (!row || typeof row !== 'object') continue
    const status = String(row.status ?? '').toLowerCase()
    if (status === 'inactive') continue

    const name = String(row.name || row.email || '').trim()
    if (!name) continue

    const parsedRole = roleForStudyMember(row, studyIamId, studyCode)
    if (!parsedRole) continue

    if (isSitePersonnelRole(parsedRole)) {
      pushRow(sitePersonnel, seenSite, parsedRole, name)
    } else if (isMonitorPersonnelRole(parsedRole)) {
      pushRow(monitorPersonnel, seenMonitor, parsedRole, name)
    } else {
      pushRow(otherPersonnel, seenOther, parsedRole, name)
    }
  }

  return {
    sitePersonnelRows: withDefaultRows(sitePersonnel),
    monitorPersonnelRows: withDefaultRows(monitorPersonnel),
    otherPersonnelRows: withDefaultRows(otherPersonnel),
  }
}
