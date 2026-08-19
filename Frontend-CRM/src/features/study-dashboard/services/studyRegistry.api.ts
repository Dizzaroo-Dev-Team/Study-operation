// Study Registry service — talks to the backend proxy over the Data Platform
// Study Registry (GET /api/v1/study-registry upstream). The backend filters to
// active studies and strips connection strings; the browser addresses a study
// by studyId only.
import { api } from '../../../lib/api'
import type { DashboardStudy, StudyRegistryItem } from '../types'

// The pre-existing hardcoded study. Selecting it keeps every request on the
// exact code path the dashboard used before the registry existed (no
// registry_study_id param is sent, so the backend uses study_db_01).
export const LOCAL_STUDY: DashboardStudy = {
  studyId: 'local',
  studyName: 'Current Demo Study',
  databaseName: 'study_db_01',
  connectionString: null,
  source: 'local',
}

function toDashboardStudy(item: StudyRegistryItem): DashboardStudy {
  return {
    studyId: item.studyId,
    studyName: item.studyName,
    databaseName: item.databaseName ?? null,
    connectionString: null,
    source: 'registry',
  }
}

/** Active studies from the registry, as uniform DashboardStudy objects. */
export async function getStudies(): Promise<DashboardStudy[]> {
  const { data } = await api.get<{ items: StudyRegistryItem[] }>(
    '/study-dashboard/study-registry',
  )
  return (data.items ?? []).map(toDashboardStudy)
}

/** One registry study by id. */
export async function getStudy(studyId: string): Promise<DashboardStudy> {
  const { data } = await api.get<StudyRegistryItem>(
    `/study-dashboard/study-registry/${encodeURIComponent(studyId)}`,
  )
  return toDashboardStudy(data)
}

/**
 * Query param fragment widgets attach to every dashboard fetch. Local study →
 * empty object, so requests stay byte-identical to the pre-registry ones.
 */
export function registryParams(study: DashboardStudy): { registry_study_id?: string } {
  return study.source === 'registry' ? { registry_study_id: study.studyId } : {}
}
