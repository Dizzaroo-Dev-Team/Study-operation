import type { AppUser } from '@/features/operations/components/TaskFormModal'
import type { StudyTeamMemberRow } from '@/components/mon/utils/studyTeamAssignees'

export function studyTeamRowsToAppUsers(rows: unknown): AppUser[] {
  if (!Array.isArray(rows)) return []

  const byId = new Map<string, AppUser>()
  for (const raw of rows) {
    if (!raw || typeof raw !== 'object') continue
    const row = raw as StudyTeamMemberRow
    const status = String(row.status ?? '').toLowerCase()
    if (status === 'inactive') continue

    const userId = String(row.user_id || '').trim()
    if (!userId) continue

    const name =
      (typeof row.name === 'string' && row.name.trim()) ||
      (typeof row.email === 'string' && row.email.trim()) ||
      userId

    byId.set(userId, {
      user_id: userId,
      name,
      email: row.email ?? null,
      role: row.role ?? row.studies?.find((s) => s?.role)?.role ?? null,
    })
  }

  return [...byId.values()].sort((a, b) =>
    displayAssignableUser(a).localeCompare(displayAssignableUser(b))
  )
}

export function displayAssignableUser(user: AppUser): string {
  return (user.name && user.name.trim()) || user.email || user.user_id
}

export function mergeAssigneeUsers(
  primary: AppUser[],
  extras: AppUser[] = [],
): AppUser[] {
  const byId = new Map<string, AppUser>()
  for (const user of primary) {
    if (!user?.user_id) continue
    byId.set(user.user_id, user)
  }
  for (const user of extras) {
    if (!user?.user_id) continue
    if (!byId.has(user.user_id)) byId.set(user.user_id, user)
  }
  return [...byId.values()].sort((a, b) =>
    displayAssignableUser(a).localeCompare(displayAssignableUser(b))
  )
}
