import { api } from '../../../lib/api'
import type {
  AssistantHistoryTurn,
  AssistantResponse,
  DeviationsResponse,
  DispositionResponse,
  EnrollmentResponse,
  MilestonesResponse,
  PatientVisitMatrixResponse,
  VisitComplianceResponse,
} from '../types'

// All fetchers accept an optional `registry_study_id`. Omitted (the default,
// and always the case for the hardcoded study_db_01 study) the backend serves
// the request exactly as it did before the Study Registry integration.

export async function fetchPatientVisitMatrix(params?: {
  study_id?: string
  limit_subjects?: number
  registry_study_id?: string
}): Promise<PatientVisitMatrixResponse> {
  const { data } = await api.get<PatientVisitMatrixResponse>(
    '/study-dashboard/patient-visit-matrix',
    { params },
  )
  return data
}

export async function fetchEnrollment(params?: {
  study_id?: string
  registry_study_id?: string
}): Promise<EnrollmentResponse> {
  const { data } = await api.get<EnrollmentResponse>('/study-dashboard/enrollment', { params })
  return data
}

export async function fetchDisposition(params?: {
  study_id?: string
  registry_study_id?: string
}): Promise<DispositionResponse> {
  const { data } = await api.get<DispositionResponse>('/study-dashboard/disposition', { params })
  return data
}

export async function fetchVisitCompliance(params?: {
  study_id?: string
  max_visits?: number
  registry_study_id?: string
}): Promise<VisitComplianceResponse> {
  const { data } = await api.get<VisitComplianceResponse>('/study-dashboard/visit-compliance', { params })
  return data
}

export async function fetchDeviations(params?: {
  study_id?: string
  registry_study_id?: string
}): Promise<DeviationsResponse> {
  const { data } = await api.get<DeviationsResponse>('/study-dashboard/deviations', { params })
  return data
}

export async function fetchMilestones(params?: {
  study_id?: string
  registry_study_id?: string
}): Promise<MilestonesResponse> {
  const { data } = await api.get<MilestonesResponse>('/study-dashboard/milestones', { params })
  return data
}

export async function askAssistant(
  question: string,
  history?: AssistantHistoryTurn[],
  registryStudyId?: string,
): Promise<AssistantResponse> {
  const { data } = await api.post<AssistantResponse>('/study-dashboard/ai-assistant', {
    question,
    history,
    registry_study_id: registryStudyId,
  })
  return data
}
