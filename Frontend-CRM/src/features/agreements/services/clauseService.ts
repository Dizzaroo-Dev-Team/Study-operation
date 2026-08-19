/**
 * Clause Library API client.
 *
 * Wraps src/lib/api.ts (axios instance with auth + error handling).
 * Never call fetch() directly — always go through `api`.
 */
import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type LockPolicy = 'STANDARD_LOCKED' | 'EDITABLE' | 'ALTERNATE'
export type ClauseVersionStatus = 'DRAFT' | 'APPROVED' | 'RETIRED'
export type CompositionMode = 'DOCX_UPLOAD' | 'CLAUSE_COMPOSED'

export interface ClauseVersion {
  id: string
  clause_id: string
  version_number: number
  content_json: Record<string, unknown>
  status: ClauseVersionStatus
  created_by: string | null
  created_at: string
}

export interface Clause {
  id: string
  title: string
  category: string
  description: string | null
  lock_policy: LockPolicy
  current_version_id: string | null
  current_version: ClauseVersion | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface TemplateClause {
  id: string
  template_id: string
  clause_id: string
  pinned_clause_version_id: string | null
  sort_order: number
  is_locked: boolean
  is_editable: boolean
  has_override: boolean
  // Denormalised clause info
  clause_title: string | null
  clause_category: string | null
  lock_policy: LockPolicy | null
  pinned_version_number: number | null
}

// ---------------------------------------------------------------------------
// Clause CRUD
// ---------------------------------------------------------------------------

export async function listClauses(params?: {
  q?: string
  category?: string
}): Promise<Clause[]> {
  const res = await api.get<Clause[]>('/clauses', { params })
  return res.data
}

export async function getClause(clauseId: string): Promise<Clause> {
  const res = await api.get<Clause>(`/clauses/${clauseId}`)
  return res.data
}

export async function createClause(body: {
  title: string
  category: string
  description?: string
  lock_policy: LockPolicy
  content_json: Record<string, unknown>
}): Promise<Clause> {
  const res = await api.post<Clause>('/clauses', body)
  return res.data
}

export async function updateClause(
  clauseId: string,
  body: {
    title?: string
    category?: string
    description?: string
    lock_policy?: LockPolicy
  },
): Promise<Clause> {
  const res = await api.patch<Clause>(`/clauses/${clauseId}`, body)
  return res.data
}

export async function deleteClause(clauseId: string): Promise<void> {
  await api.delete(`/clauses/${clauseId}`)
}

// ---------------------------------------------------------------------------
// Clause versions
// ---------------------------------------------------------------------------

export async function listClauseVersions(clauseId: string): Promise<ClauseVersion[]> {
  const res = await api.get<ClauseVersion[]>(`/clauses/${clauseId}/versions`)
  return res.data
}

export async function publishClauseVersion(
  clauseId: string,
  body: {
    content_json: Record<string, unknown>
    status?: ClauseVersionStatus
  },
): Promise<ClauseVersion> {
  const res = await api.post<ClauseVersion>(`/clauses/${clauseId}/versions`, body)
  return res.data
}

// ---------------------------------------------------------------------------
// Template composition
// ---------------------------------------------------------------------------

export async function listTemplateClauses(templateId: string): Promise<TemplateClause[]> {
  const res = await api.get<TemplateClause[]>(`/templates/${templateId}/clauses`)
  return res.data
}

export async function insertClauseIntoTemplate(
  templateId: string,
  body: { clause_id: string; sort_order?: number },
): Promise<TemplateClause> {
  const res = await api.post<TemplateClause>(`/templates/${templateId}/clauses`, body)
  return res.data
}

export async function removeClauseFromTemplate(
  templateId: string,
  tcId: string,
): Promise<void> {
  await api.delete(`/templates/${templateId}/clauses/${tcId}`)
}

export async function reorderTemplateClauses(
  templateId: string,
  orderedIds: string[],
): Promise<void> {
  await api.patch(`/templates/${templateId}/clauses/reorder`, {
    ordered_ids: orderedIds,
  })
}

export async function updateClauseLock(
  templateId: string,
  tcId: string,
  body: { is_locked: boolean; is_editable: boolean },
): Promise<TemplateClause> {
  const res = await api.patch<TemplateClause>(
    `/templates/${templateId}/clauses/${tcId}/lock`,
    body,
  )
  return res.data
}

export async function saveClauseOverride(
  templateId: string,
  tcId: string,
  overrideContentJson: Record<string, unknown>,
): Promise<TemplateClause> {
  const res = await api.patch<TemplateClause>(
    `/templates/${templateId}/clauses/${tcId}/override`,
    { override_content_json: overrideContentJson },
  )
  return res.data
}

export async function pinClauseVersion(
  templateId: string,
  tcId: string,
  clauseVersionId: string,
): Promise<TemplateClause> {
  const res = await api.patch<TemplateClause>(
    `/templates/${templateId}/clauses/${tcId}/pin`,
    { clause_version_id: clauseVersionId },
  )
  return res.data
}

/**
 * Server-side lock validation.  Call this BEFORE saving document content.
 * Throws with violation details if any locked clause was modified.
 */
export async function validateLockedClauses(
  templateId: string,
  documentJson: Record<string, unknown>,
): Promise<void> {
  await api.post(`/templates/${templateId}/validate-locks`, {
    document_json: documentJson,
  })
}

/**
 * Materialise the template into one flat Tiptap JSON document.
 * Returns the document JSON (no DB write on the server).
 */
export async function materializeTemplate(
  templateId: string,
): Promise<Record<string, unknown>> {
  const res = await api.post<{ document_json: Record<string, unknown> }>(
    `/templates/${templateId}/materialize`,
  )
  return res.data.document_json
}

/** Save Tiptap JSON content back to the template (clause-only templates). */
export async function saveTemplateContent(
  templateId: string,
  contentJson: Record<string, unknown>,
): Promise<void> {
  await api.patch(`/templates/${templateId}/content`, { content_json: contentJson })
}

// ---------------------------------------------------------------------------
// Clause Builder — DOCX block anchors + insertions
// ---------------------------------------------------------------------------

export interface DocumentBlock {
  index: number
  type: 'paragraph' | 'table'
  text: string
}

export interface ClauseInsertion {
  after_block: number          // -1 = before first block
  clause_id: string
  clause_version_id?: string | null
  clause_title?: string | null
}

export interface TemplateBlocksResponse {
  blocks: DocumentBlock[]
  clause_insertions: ClauseInsertion[]
  has_docx: boolean
}

/** Fetch the original DOCX's body blocks + any saved clause insertions. */
export async function getDocumentBlocks(templateId: string): Promise<TemplateBlocksResponse> {
  const res = await api.get<TemplateBlocksResponse>(`/templates/${templateId}/document-blocks`)
  return res.data
}

/** Persist the ordered clause insertions for a template. */
export async function saveClauseInsertions(
  templateId: string,
  insertions: ClauseInsertion[],
): Promise<void> {
  await api.patch(`/templates/${templateId}/clause-insertions`, { clause_insertions: insertions })
}
