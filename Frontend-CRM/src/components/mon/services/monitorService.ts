import { api } from "../../../lib/api";
import type { ChecklistItem, Finding } from "../types";
import type { MvrTemplateDto } from "../types/mvrTemplate";

export interface DashboardVisitRow {
  id: string;
  site_id?: string | null;
  site_name: string;
  study_id?: string | null;
  study_name: string;
  date: string;
  date_iso?: string | null;
  end_date?: string | null;
  end_date_iso?: string | null;
  priority?: string | null;
  estimated_duration_days?: number | null;
  cra_name: string;
  type: string;
  status: string;
  open_findings: number;
  /** Per-site ordinal ("Visit #1"); API `id` remains the stable key for URLs/API. */
  site_visit_number?: number | null;
}

export interface DashboardFindingRow {
  id: string;
  visit_id: string;
  subjectId?: string;
  reference?: string;
  category: string;
  description: string;
  severity: string;
  status: string;
  site: string;
  assignee: { initials: string; name: string; color: string };
  dueDate: string;
  dueColor: string;
  resolution?: string;
  isOverdue?: boolean;
}

export interface DashboardPayload {
  items: DashboardVisitRow[];
  total: number;
  page: number;
  page_size: number;
  /** @deprecated use items — kept for backward compatibility */
  visits?: DashboardVisitRow[];
  findings: DashboardFindingRow[];
  overdue_count: number;
  summary?: {
    total_visits?: number;
    scheduled?: number;
    in_progress?: number;
    completed?: number;
    cancelled?: number;
  };
}

/** Raw MVR payload from `/monitor/visits/{id}/visit-report`; merge with defaults on the client. */
export type VisitReportApiPayload = Record<string, unknown>;

export async function fetchActiveMvrTemplate(organizationId = "default"): Promise<{ template: MvrTemplateDto | null }> {
  const { data } = await api.get("/monitor/mvr-templates/active", {
    params: { organization_id: organizationId },
  });
  return data;
}

export async function listMvrTemplates(organizationId = "default"): Promise<{ items: MvrTemplateDto[] }> {
  const { data } = await api.get("/monitor/mvr-templates", {
    params: { organization_id: organizationId },
  });
  return data;
}

export async function fetchMvrTemplateById(
  templateId: string,
): Promise<{ template: MvrTemplateDto }> {
  const { data } = await api.get(`/monitor/mvr-templates/${encodeURIComponent(templateId)}`);
  return data;
}

export async function createMvrTemplateDraft(
  name = "Untitled Template",
  organizationId = "default",
): Promise<{ template: MvrTemplateDto }> {
  const { data } = await api.post("/monitor/mvr-templates/drafts", {
    name,
    organization_id: organizationId,
  });
  return data;
}

export async function patchMvrTemplate(
  templateId: string,
  body: { name?: string; schema?: Record<string, unknown>; finalize?: boolean },
): Promise<{ status: string; template: MvrTemplateDto }> {
  const { data } = await api.patch(`/monitor/mvr-templates/${encodeURIComponent(templateId)}`, body);
  return data;
}

export async function publishMvrTemplate(
  templateId: string,
  body?: { name?: string; schema?: Record<string, unknown> },
): Promise<{ status: string; template: MvrTemplateDto }> {
  const { data } = await api.post(`/monitor/mvr-templates/${encodeURIComponent(templateId)}/publish`, body ?? {});
  return data;
}

/** Mark a saved template as Live (used on the visit report tab). Only one Live template per organization. */
export async function activateMvrTemplate(
  templateId: string,
): Promise<{ status: string; template: MvrTemplateDto }> {
  const { data } = await api.post(`/monitor/mvr-templates/${encodeURIComponent(templateId)}/activate`);
  return data;
}

export async function duplicateMvrTemplate(
  templateId: string,
  body?: { name?: string; schema?: Record<string, unknown> },
  organizationId = "default",
): Promise<{ status: string; template: MvrTemplateDto }> {
  const { data } = await api.post(
    `/monitor/mvr-templates/${encodeURIComponent(templateId)}/duplicate`,
    { ...body, organization_id: organizationId },
  );
  return data;
}

export async function deleteMvrTemplate(templateId: string): Promise<{ status: string }> {
  const { data } = await api.delete(`/monitor/mvr-templates/${encodeURIComponent(templateId)}`);
  return data;
}

export async function deleteAllMvrTemplates(
  organizationId = "default",
): Promise<{ status: string; deleted_count?: number }> {
  const { data } = await api.delete("/monitor/mvr-templates/all", {
    params: { organization_id: organizationId },
  });
  return data;
}

export async function saveMvrTemplate(payload: {
  name: string;
  schema: Record<string, unknown>;
  publish: boolean;
  organization_id?: string;
}): Promise<{ status: string; template: MvrTemplateDto }> {
  const { data } = await api.post("/monitor/mvr-templates", payload);
  return data;
}

export async function saveVisitReport(
  visitId: string,
  payload: Record<string, unknown>,
): Promise<{ status: string }> {
  const { data } = await api.put(`/monitor/visits/${visitId}/visit-report`, { payload });
  return data;
}

export async function deleteVisit(visitId: string) {
  const { data } = await api.delete(`/monitor/visits/${visitId}`);
  return data;
}

export async function createVisit(payload: Record<string, unknown>): Promise<DashboardVisitRow> {
  const { data } = await api.post("/monitor/visits", payload);
  return data;
}

export async function updateVisit(visitId: string, payload: Record<string, unknown>): Promise<DashboardVisitRow> {
  const { data } = await api.patch(`/monitor/visits/${visitId}`, payload);
  return data;
}

export async function fetchSites(): Promise<Array<{ id: string; site_id?: string; name: string }>> {
  const { data } = await api.get("/sites");
  return data;
}

export async function fetchStudies(): Promise<Array<{ id: string; study_id?: string; name: string }>> {
  const { data } = await api.get("/studies");
  return data;
}

export async function toggleVisitObjective(
  visitId: string,
  objectiveId: number,
  done?: boolean,
): Promise<ChecklistItem> {
  const payload = typeof done === "boolean" ? { done } : undefined;
  const { data } = await api.patch(`/monitor/visits/${visitId}/objectives/${objectiveId}`, payload);
  return data;
}

export async function fetchMonitorTableStatus(): Promise<{
  required_tables: string[];
  present_tables: string[];
  missing_tables: string[];
}> {
  const { data } = await api.get("/monitor/tables/status");
  return data;
}

export async function saveConfirmationLetter(visitId: string, content: string) {
  const { data } = await api.put(`/monitor/visits/${visitId}/confirmation-letter`, { content });
  return data;
}

export async function sendConfirmationLetter(visitId: string, content: string, ccEmails?: string) {
  const { data } = await api.post(`/monitor/visits/${visitId}/confirmation-letter/send`, {
    content,
    cc_emails: ccEmails || "",
  });
  return data as {
    status: string;
    recipient_name: string;
    recipient_email: string;
    recipients?: Array<{ role: string; name: string; email: string }>;
    last_sent: string;
    delivery_status: string;
  };
}

export async function saveFollowUpLetter(visitId: string, content: string): Promise<{ status: string }> {
  const { data } = await api.put(`/monitor/visits/${visitId}/follow-up-letter`, { content });
  return data;
}

export async function closeVisit(visitId: string): Promise<{ status: string; visit_id: string }> {
  const { data } = await api.post(`/monitor/visits/${visitId}/close`);
  return data;
}

export async function generateVisitSummary(
  payload: Record<string, unknown>,
): Promise<{ summary: string }> {
  const { data } = await api.post("/monitor/generate-summary", payload);
  return data;
}

export async function togglePreVisitChecklistItem(visitId: string, checklistId: number) {
  const { data } = await api.patch(`/monitor/visits/${visitId}/pre-visit/checklist/${checklistId}`);
  return data;
}

export async function sendPreVisitSummary(
  visitId: string,
  content: string,
  ccEmails?: string,
): Promise<{ status: string; recipients?: string[]; preVisitReportStatus?: string }> {
  const { data } = await api.post(`/monitor/visits/${visitId}/pre-visit/send-summary`, {
    content,
    cc_emails: ccEmails || '',
  });
  return data;
}

export async function markPreVisitReviewed(
  visitId: string,
): Promise<{ status: string; already?: boolean; preVisitReviewedAt?: string | null }> {
  const { data } = await api.post(`/monitor/visits/${visitId}/pre-visit/reviewed`);
  return data;
}

export async function acknowledgePreVisitReport(
  visitId: string,
  token: string,
): Promise<{ status: string; already?: boolean }> {
  const { data } = await api.post(`/monitor/visits/${visitId}/pre-visit/acknowledge`, {
    token,
  });
  return data;
}

export async function savePreVisitPlan(visitId: string, payload: Record<string, unknown>) {
  const { data } = await api.put(`/monitor/visits/${visitId}/pre-visit/plan`, payload);
  return data;
}

/** Stored id is `{visitId}__F-01` (unique PK); show `F-01` in the UI. Legacy `F-041` ids unchanged. */
export function findingIdForDisplay(id: string, visitId?: string): string {
  if (visitId) {
    const prefix = `${visitId}__F-`;
    if (id.startsWith(prefix)) return `F-${id.slice(prefix.length)}`;
  }
  const m = id.match(/^([\w-]+)__F-(\d+)$/);
  if (m) return `F-${m[2]}`;
  return id;
}

export async function addVisitFinding(visitId: string, payload: Record<string, unknown>): Promise<Finding> {
  const { data } = await api.post(`/monitor/visits/${visitId}/findings`, payload);
  return data;
}

export async function updateVisitFinding(visitId: string, findingId: string, payload: Record<string, unknown>) {
  const { data } = await api.patch(`/monitor/visits/${visitId}/findings/${findingId}`, payload);
  return data;
}

export async function resolveVisitFinding(visitId: string, findingId: string) {
  const { data } = await api.patch(`/monitor/visits/${visitId}/findings/${findingId}/resolve`);
  return data;
}

export async function deleteVisitFinding(visitId: string, findingId: string) {
  const { data } = await api.delete(`/monitor/visits/${visitId}/findings/${findingId}`);
  return data;
}

export interface Notification {
  id: number;
  icon: string;
  text: string;
  time: string;
  unread: boolean;
  type: "finding" | "visit" | "activity";
  /** ISO-8601 UTC — newest notifications sort first; used for Clear all cutoff. */
  sort_at?: string;
}

export interface NotificationsResponse {
  notifications: Notification[];
  unread_count: number;
}

export interface VisitRescheduleRequestItem {
  id: string;
  visit_id: string;
  site_visit_number?: number | null;
  proposed_date: string;
  proposed_end_date?: string | null;
  proposed_slots?: Array<{
    index: number;
    proposed_datetime_iso: string;
    proposed_end_datetime_iso?: string | null;
  }>;
  reason: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  site_name?: string;
  study_name?: string;
}

/** Shown in UI; routes and DB still use `visitId`. */
export function formatVisitDisplayLabel(visitId: string, siteVisitNumber?: number | null): string {
  if (siteVisitNumber != null && Number.isFinite(Number(siteVisitNumber)) && Number(siteVisitNumber) >= 1) {
    return `Visit #${siteVisitNumber}`;
  }
  return visitId;
}

// ── Review Workflow ───────────────────────────────────────────────────────────

export interface ReviewComment {
  id: string;
  highlighted_text: string;
  dom_path: string;
  start_offset: number;
  end_offset: number;
  comment_text: string;
  author_reply?: string;
  author_reply_at?: string | null;
  created_at: string;
  updated_at: string;
}

export async function submitReportForReview(
  visitId: string,
  reviewerEmail: string,
  message: string,
  authorEmail: string,
): Promise<{ status: string; review_url: string; reviewer_email: string }> {
  const { data } = await api.post(`/monitor/visits/${visitId}/visit-report/submit-for-review`, {
    reviewer_email: reviewerEmail,
    message,
    author_email: authorEmail,
  });
  return data;
}

export async function saveReviewAnnotation(
  visitId: string,
  token: string,
  annotation: {
    highlighted_text: string;
    dom_path: string;
    start_offset: number;
    end_offset: number;
    comment_text: string;
  },
): Promise<{ status: string; id: string }> {
  const { data } = await api.post(
    `/monitor/visits/${visitId}/visit-report/review/comments`,
    { token, ...annotation },
  );
  return data;
}

export async function updateReviewAnnotation(
  visitId: string,
  commentId: string,
  token: string,
  commentText: string,
): Promise<{ status: string }> {
  const { data } = await api.patch(
    `/monitor/visits/${visitId}/visit-report/review/comments/${commentId}`,
    { token, comment_text: commentText },
  );
  return data;
}

export async function deleteReviewAnnotation(
  visitId: string,
  commentId: string,
  token: string,
): Promise<{ status: string }> {
  const { data } = await api.delete(
    `/monitor/visits/${visitId}/visit-report/review/comments/${commentId}`,
    { params: { token } },
  );
  return data;
}

export async function approveReport(
  visitId: string,
  token: string,
): Promise<{ status: string }> {
  const { data } = await api.post(
    `/monitor/visits/${visitId}/visit-report/review/approve`,
    { token },
  );
  return data;
}

export async function rejectReport(
  visitId: string,
  token: string,
  reason: string,
): Promise<{ status: string }> {
  const { data } = await api.post(
    `/monitor/visits/${visitId}/visit-report/review/reject`,
    { token, reason },
  );
  return data;
}

export async function fetchReportForReview(
  visitId: string,
  token: string,
): Promise<{
  payload: Record<string, unknown>;
  comments: ReviewComment[];
  reviewer_email: string;
  message: string;
}> {
  const { data } = await api.get(`/monitor/visits/${visitId}/visit-report/review`, {
    params: { token },
  });
  return data;
}

export async function decideVisitRescheduleRequest(
  visitId: string,
  requestId: string,
  decision: "approved" | "rejected",
  reason?: string,
  selectedSlotIndex?: number,
): Promise<{ status: string; request_status: string }> {
  const { data } = await api.post<{ status: string; request_status: string }>(
    `/monitor/visits/${visitId}/reschedule-requests/${requestId}/decision`,
    { decision, reason, selected_slot_index: selectedSlotIndex },
  );
  return data;
}
