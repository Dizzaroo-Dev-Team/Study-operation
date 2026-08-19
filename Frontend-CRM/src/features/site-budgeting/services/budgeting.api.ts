import { api } from '../../../lib/api'

const B = '/budgeting'

export type CostElementRow = {
  id: string
  code: string
  name: string
  description?: string | null
  unit?: string | null                // Payment Type column (ONCE | ANNUAL | PER PATIENT | …)
  category?: string | null
  subcategory?: string | null         // parsed from description on backend
  unit_label?: string | null          // human-readable Unit (Per Document | Lump Sum | …)
  cost_variability?: string | null    // 'FIXED' | 'VARIABLE' (master spreadsheet's Cost Type)
  pass_thru?: string | null           // 'Y' | 'N'
  element_type?: string | null        // ATOMIC | BUNDLE
  cost_type?: string | null           // PER_VISIT | PER_PATIENT | FIXED | MILESTONE | PASS_THROUGH
  therapeutic_area?: string | null
  is_active?: boolean
  latest_version?: { version_label: string; base_unit_cost: string; reference_currency: string } | null
}

export type BudgetTemplateRow = {
  id: string
  trial_id: string
  site_id?: string | null
  parent_template_id?: string | null
  name: string
  status: string
  enrollment_planned?: number | null
  target_currency_code: string
  template_level?: string | null   // TRIAL | COUNTRY | SITE
  country_code?: string | null
}

export type ResolvedBudgetLine = {
  line_item_id: string | null
  cost_element_id: string
  code?: string | null
  name?: string | null
  category?: string | null
  sort_order?: number
  inherited_from?: string | null
  override_unit_cost?: string | null
  unit_cost?: string | null
  unit_cost_computed?: string | null
  quantity?: string | null
  needs_review?: boolean
  factored_unit_cost?: string | null
  is_excluded?: boolean
  is_policy_included?: boolean
}

export type FactorTypeRow = { id: string; code: string; name: string; mode: string }

export async function fetchElements() {
  const { data } = await api.get<CostElementRow[]>(`${B}/elements`)
  return data
}

export async function patchElementCost(
  elementId: string,
  body: { version_label: string; base_unit_cost: string; reference_currency: string; source?: string; is_bundle_override?: boolean }
) {
  const { data } = await api.patch(`${B}/elements/${elementId}/cost`, body)
  return data
}

export async function createElement(body: {
  code: string; name: string; description?: string | null
  unit?: string | null; category?: string | null; category_id?: string | null
  element_type?: string; cost_type?: string | null; therapeutic_area?: string | null; is_active?: boolean
}) {
  const { data } = await api.post(`${B}/elements`, body)
  return data as { id: string; code: string }
}

export async function updateElement(elementId: string, body: {
  name?: string; description?: string | null; unit?: string | null
  category?: string | null; category_id?: string | null
  element_type?: string; cost_type?: string | null; therapeutic_area?: string | null; is_active?: boolean
}) {
  const { data } = await api.patch(`${B}/elements/${elementId}`, body)
  return data
}

export async function deleteElement(elementId: string) {
  await api.delete(`${B}/elements/${elementId}`)
}

export async function fetchBundleChildren(elementId: string) {
  const { data } = await api.get<{
    child_element_id: string; code: string; name: string
    quantity_in_bundle: string; sort_order: number; unit_cost: string | null; currency: string | null
  }[]>(`${B}/elements/${elementId}/bundle-children`)
  return data
}

export async function upsertBundleChildren(elementId: string, children: {
  child_element_id: string; quantity_in_bundle: string; sort_order: number
}[]) {
  const { data } = await api.put(`${B}/elements/${elementId}/bundle-children`, children)
  return data
}

export async function fetchCategories() {
  const { data } = await api.get<{ id: string; name: string; parent_id: string | null; sort_order: number }[]>(`${B}/categories`)
  return data
}

export async function createCategory(body: { name: string; parent_id?: string | null; sort_order?: number }) {
  const { data } = await api.post(`${B}/categories`, body)
  return data as { id: string; name: string }
}

export async function bulkFmvImport(file: File, versionLabel: string, currencyCode = 'USD', source?: string) {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ version_label: versionLabel, currency_code: currencyCode })
  if (source) params.set('source', source)
  const { data } = await api.post(`${B}/elements/fmv-import?${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { version_label: string; inserted: number; updated: number; skipped: string[] }
}

export async function fetchFactorTypes() {
  const { data } = await api.get<FactorTypeRow[]>(`${B}/factor-types`)
  return data
}

export async function fetchFactors(trialId?: string) {
  const { data } = await api.get(`${B}/factors`, { params: trialId ? { trial_id: trialId } : {} })
  return data
}

export async function createFactor(body: Record<string, unknown>) {
  const { data } = await api.post(`${B}/factors`, body)
  return data
}

export async function patchFactor(factorId: string, body: { value?: string; sequence_order?: number }) {
  const { data } = await api.patch(`${B}/factors/${factorId}`, body)
  return data
}

export async function deleteFactor(factorId: string) {
  await api.delete(`${B}/factors/${factorId}`)
}

export async function fetchTemplatesForTrial(trialId: string) {
  const { data } = await api.get<BudgetTemplateRow[]>(`${B}/trials/${trialId}/templates`)
  return data
}

export async function fetchEffectiveTemplate(params: { trial_id: string; country_code?: string; site_id?: string }) {
  const { data } = await api.get<{ id: string }>(`${B}/templates/effective`, { params })
  return data
}

export async function createTemplate(body: Record<string, unknown>) {
  const { data } = await api.post(`${B}/templates`, body)
  return data
}

export async function patchTemplate(templateId: string, body: { enrollment_planned?: number | null; name?: string; target_currency_code?: string }) {
  const { data } = await api.patch(`${B}/templates/${templateId}`, body)
  return data
}

export async function resolveTemplate(templateId: string, params?: { country_code?: string; site_id?: string }) {
  const { data } = await api.get(`${B}/templates/${templateId}/resolve`, { params })
  return data
}

/** After trial-level line items change: flag overridden child lines for review (backend propagates to descendants). */
export async function markAmendmentReview(templateId: string, elementIds: string[]) {
  const { data } = await api.post(`${B}/templates/${templateId}/amendment-mark-review`, {
    element_ids: elementIds,
  })
  return data as { marked: number }
}

export async function totalTemplate(templateId: string, params?: { country_code?: string; site_id?: string }) {
  const { data } = await api.get(`${B}/templates/${templateId}/total`, { params })
  return data
}

/** Cascade-merged visit matrix (same source as resolve/totals quantity logic). */
export async function fetchVisitMatrixResolved(templateId: string) {
  const { data } = await api.get(`${B}/templates/${templateId}/visit-matrix/resolved`)
  return data as {
    template_id: string
    visits: { id: string; visit_code?: string | null; visit_name: string; visit_order: number }[]
    cells: {
      cost_element_id: string
      visit_code: string
      visit_schedule_id: string
      budget_line_item_id: string
      units: string
      inherited_from_parent?: boolean
    }[]
  }
}

export async function patchVisitMatrix(
  templateId: string,
  cells: { budget_line_item_id: string; visit_schedule_id: string; units: string; is_excluded?: boolean }[]
) {
  const { data } = await api.patch(`${B}/templates/${templateId}/visit-matrix`, { cells })
  return data
}

export async function fetchMilestones(templateId: string) {
  const { data } = await api.get(`${B}/templates/${templateId}/milestones`)
  return data
}

export async function createLineItem(templateId: string, body: { cost_element_id: string; sort_order?: number }) {
  const { data } = await api.post(`${B}/templates/${templateId}/line-items`, body)
  return data
}

export async function createVisit(templateId: string, body: { visit_name: string; visit_code?: string; visit_order?: number }) {
  const { data } = await api.post(`${B}/templates/${templateId}/visits`, body)
  return data
}

export async function createMilestone(templateId: string, body: { name: string; unit_cost: string; quantity?: string; sort_order?: number; payment_trigger?: string | null }) {
  const { data } = await api.post(`${B}/templates/${templateId}/milestones`, body)
  return data
}

export async function patchLineItem(
  templateId: string,
  lineItemId: string,
  body: Partial<{ is_excluded: boolean; override_unit_cost: string | null; override_currency_code: string | null; sort_order: number }>
) {
  const { data } = await api.patch(`${B}/templates/${templateId}/line-items/${lineItemId}`, body)
  return data
}

export async function fetchCountries() {
  const { data } = await api.get<{ countries: { code: string; name: string }[] }>(`${B}/reference/countries`)
  return data.countries
}

export type ScopedFactor = {
  id: string
  factor_type: { id: string; code: string; name: string; mode: string }
  country_code: string | null
  site_id: string | null
  value: string
  label: string | null
}

export async function fetchFactorsByScope(scope: 'COUNTRY' | 'SITE') {
  const { data } = await api.get<ScopedFactor[]>(`${B}/factors/by-scope`, { params: { scope } })
  return data
}

export async function updateTemplateStatus(templateId: string, status: string) {
  const { data } = await api.patch(`${B}/templates/${templateId}/status`, { status })
  return data as { id: string; status: string }
}

export async function patchMilestone(
  templateId: string,
  milestoneId: string,
  body: Partial<{ name: string; unit_cost: string; quantity: string; payment_trigger: string | null; sort_order: number }>
) {
  const { data } = await api.patch(`${B}/templates/${templateId}/milestones/${milestoneId}`, body)
  return data
}

export async function deleteMilestone(templateId: string, milestoneId: string) {
  await api.delete(`${B}/templates/${templateId}/milestones/${milestoneId}`)
}

export async function fetchNotes(templateId: string) {
  const { data } = await api.get<{ id: string; category: string | null; body: string; user_id: string | null; created_at: string | null }[]>(`${B}/templates/${templateId}/notes`)
  return data
}

export async function createNote(templateId: string, body: { body: string; category?: string | null }) {
  const { data } = await api.post(`${B}/templates/${templateId}/notes`, body)
  return data as { id: string }
}

export async function deleteNote(templateId: string, noteId: string) {
  await api.delete(`${B}/templates/${templateId}/notes/${noteId}`)
}

export async function deleteVisit(templateId: string, visitId: string) {
  await api.delete(`${B}/templates/${templateId}/visits/${visitId}`)
}

export type SOAActivityMapping = {
  soa_item: string
  cost_element_code: string
  cost_element_name: string
  visit_flags: string[]
  confidence: number
  notes?: string
}

export type SOAMilestoneMapping = {
  soa_item: string
  cost_element_code: string
  cost_element_name: string
  confidence: number
  notes?: string
}

export type SOAImportResult = {
  template_id: string
  filename: string | null
  llm_error: string | null
  visits: string[]
  activity_mappings: SOAActivityMapping[]
  milestone_mappings: SOAMilestoneMapping[]
  unmatched: string[]
  low_confidence_items: string[]
}

export async function soaImport(templateId: string, file: File): Promise<SOAImportResult> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`${B}/templates/${templateId}/soa-import`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as SOAImportResult
}

// ─── Milestone Library ────────────────────────────────────────────────────────

export type MilestoneLibraryItem = {
  id: string
  name: string
  default_amount?: string | null
  payment_trigger?: string | null
  category?: string | null
  sort_order: number
  is_active: boolean
}

export async function fetchMilestoneLibrary(category?: string) {
  const { data } = await api.get<MilestoneLibraryItem[]>(`${B}/milestone-library`, {
    params: category ? { category } : {},
  })
  return data
}

export async function addMilestoneFromLibrary(
  templateId: string,
  body: { library_item_id: string; quantity?: number; amount_override?: string }
) {
  const { data } = await api.post(`${B}/templates/${templateId}/milestones/from-library`, body)
  return data
}

export async function bulkMilestonesFromLibrary(
  templateId: string,
  body: { library_item_ids: string[]; amount_overrides?: Record<string, string> }
) {
  const { data } = await api.post(`${B}/templates/${templateId}/milestones/bulk-from-library`, {
    library_item_ids: body.library_item_ids,
    amount_overrides: body.amount_overrides ?? {},
  })
  return data as { added: number; skipped_duplicate: number; skipped_no_amount: number }
}

// ─── SoA → Visit Matrix ──────────────────────────────────────────────────────

export type MatrixPlanRow = {
  visit_name: string
  activity_name: string
  element_code: string | null
  quantity: number
  confidence: number
  match_source?: 'string' | 'ai' | 'none'
}

export type SoaPreview = {
  study_id: string
  visits: string[]
  activities_count: number
  matrix_plan: MatrixPlanRow[]
  unmapped: string[]
  mappings: { activity: string; element_code: string | null; confidence: number }[]
}

export type SoaApplyResult = {
  template_id: string
  inserted_visits: number
  inserted_lines: number
  inserted_cells: number
  skipped: number
}

export type SoaStudy = {
  study_id: string        // SoA protocolId — the value the generate endpoint expects
  name: string | null     // human-readable name from the CRM studies table (null if unmatched)
  in_crm: boolean
}

export type SoaSelectedStudy = {
  trial_id: string
  study_id: string | null
  name: string | null
  in_soa: boolean
}

export type SoaStudies = {
  studies: SoaStudy[]
  selected: SoaSelectedStudy | null
  /** false when the SoA cluster is unconfigured/unreachable (endpoint degraded to empty). */
  available: boolean
  error: string | null
}

export async function listSoaStudyIds(trialId?: string): Promise<SoaStudies> {
  const { data } = await api.get<{
    studies?: SoaStudy[]
    selected?: SoaSelectedStudy | null
    available?: boolean
    error?: string | null
  }>(`${B}/generate/soa-ids`, { params: trialId ? { trial_id: trialId } : {} })
  return {
    studies: data.studies ?? [],
    selected: data.selected ?? null,
    available: data.available ?? true,
    error: data.error ?? null,
  }
}

export async function soaMatrixPreview(studyId: string): Promise<SoaPreview> {
  const { data } = await api.post(`${B}/generate/${encodeURIComponent(studyId)}/preview`)
  return data as SoaPreview
}

export async function soaMatrixApply(
  studyId: string,
  templateId: string,
  matrixPlan: { visit_name: string; element_code: string; quantity: number }[]
): Promise<SoaApplyResult> {
  const { data } = await api.post(`${B}/generate/${encodeURIComponent(studyId)}/apply`, {
    template_id: templateId,
    matrix_plan: matrixPlan,
  })
  return data as SoaApplyResult
}

// ─── New workflow endpoints ──────────────────────────────────────────────────

export type VisitMatrixGenerateBody = {
  study_id: string
  treatment_duration?: number | null
  followup_duration?: number | null
  unscheduled_visits?: number
}

export type VisitMatrixGenerateResult = {
  template_id: string
  study_id: string
  treatment_duration: number | null
  followup_duration: number | null
  visits_inserted: number
  line_items_inserted: number
  matrix_cells_inserted: number
  unscheduled_appended: number
  unmapped_activities: string[]
  skipped: number
}

export async function generateVisitMatrix(
  templateId: string,
  body: VisitMatrixGenerateBody,
): Promise<VisitMatrixGenerateResult> {
  const { data } = await api.post(
    `${B}/templates/${templateId}/visit-matrix/generate`,
    body,
  )
  return data as VisitMatrixGenerateResult
}

export type GenerateMilestonesResult = {
  universal: number
  by_country: Record<string, number>
  total: number
}

export async function generateMilestones(
  templateId: string,
): Promise<GenerateMilestonesResult> {
  const { data } = await api.post(`${B}/templates/${templateId}/milestones/generate`)
  return data as GenerateMilestonesResult
}

// ─── Policy documents ────────────────────────────────────────────────────────

export type PolicyDocSummary = {
  id: string
  country_code: string
  file_name: string
  mime_type: string
  file_size: number
  uploaded_at: string | null
}

export async function uploadPolicyDocument(
  trialId: string,
  countryCode: string,
  file: File,
): Promise<PolicyDocSummary> {
  const fd = new FormData()
  fd.append('policy_document', file)
  const { data } = await api.post(
    `${B}/trials/${trialId}/policy-documents`,
    fd,
    {
      params: { country_code: countryCode },
      headers: { 'Content-Type': 'multipart/form-data' },
    },
  )
  return data as PolicyDocSummary
}

export async function listPolicyDocuments(trialId: string): Promise<PolicyDocSummary[]> {
  const { data } = await api.get<PolicyDocSummary[]>(`${B}/trials/${trialId}/policy-documents`)
  return data
}

export async function deletePolicyDocument(trialId: string, docId: string): Promise<void> {
  await api.delete(`${B}/trials/${trialId}/policy-documents/${docId}`)
}

export function policyDocumentDownloadUrl(trialId: string, docId: string): string {
  return `${B}/trials/${trialId}/policy-documents/${docId}/download`
}

// Developer / testing convenience: wipes all budget data for the trial that owns this
// template, EXCEPT the TRIAL template itself.
export async function resetTrialBudget(templateId: string): Promise<{ trial_id: string; cleared: boolean }> {
  const { data } = await api.delete(`${B}/templates/${templateId}/reset-trial-budget`)
  return data as { trial_id: string; cleared: boolean }
}

// Country-level: read country's policy docs, ask LLM for no-charge rules, apply by
// excluding the matching line items at the COUNTRY template.
export type RefactorBudgetResult = {
  country_code: string
  doc_count: number
  rules_applied: number
  excluded: { element_name: string; reason: string | null }[]
  included: { element_name: string; reason: string | null }[]
  milestone_items: { element_name: string; reason: string | null }[]
}
export async function refactorBudgetFromPolicy(
  templateId: string,
): Promise<RefactorBudgetResult> {
  const { data } = await api.post(`${B}/templates/${templateId}/budget/refactor`)
  return data as RefactorBudgetResult
}

export async function fetchFxRate(
  toCurrency: string,
  fromCurrency: string = 'USD',
): Promise<string> {
  const { data } = await api.get<{ rate: string }>(`${B}/fx`, {
    params: { from_currency: fromCurrency, to_currency: toCurrency },
  })
  return data.rate
}


// ─── Planned Enrollment + Rollup Budget ──────────────────────────────────────

export type CountryBudgetOption = {
  template_id: string
  country_code: string
  name: string
}

export type PlannedEnrollmentRow = {
  id: string | null
  study_id: string
  site_id: string
  site_name: string
  site_code: string | null
  country_code: string | null
  planned_patients: number
  planned_activation_date: string | null
}

export type PlannedEnrollmentUpsert = {
  study_id: string
  site_id: string
  country_code: string | null
  planned_patients: number
  planned_activation_date: string | null
}

export type RollupBudgetRow = {
  site_id: string
  site_name: string
  site_code: string | null
  country_code: string | null
  planned_patients: number
  variable_cost: string
  fixed_cost: string
  total_cost: string
  template_id_used: string | null
}

export async function listCountryBudgets(trialId: string): Promise<CountryBudgetOption[]> {
  const { data } = await api.get<CountryBudgetOption[]>(`${B}/country-budgets`, {
    params: { trial_id: trialId },
  })
  return data
}

export async function listPlannedEnrollment(studyId: string): Promise<PlannedEnrollmentRow[]> {
  const { data } = await api.get<PlannedEnrollmentRow[]>(`${B}/planned-enrollment`, {
    params: { study_id: studyId },
  })
  return data
}

export async function upsertPlannedEnrollment(
  body: PlannedEnrollmentUpsert,
): Promise<PlannedEnrollmentRow> {
  const { data } = await api.put<PlannedEnrollmentRow>(`${B}/planned-enrollment`, body)
  return data
}

export async function fetchRollupBudget(studyId: string): Promise<RollupBudgetRow[]> {
  const { data } = await api.get<RollupBudgetRow[]>(`${B}/rollup-budget`, {
    params: { study_id: studyId },
  })
  return data
}
