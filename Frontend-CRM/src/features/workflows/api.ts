// api.ts
// Typed client for the workflow engine, routed through the app's shared axios
// client (src/lib/api.ts). That client already:
//   * sets baseURL from VITE_API_BASE (which is ".../api" in this project), and
//   * attaches the session/JWT (cookie in hub mode, bearer in local mode), and
//   * handles 401 redirects + no-cache headers.
//
// IMPORTANT: the backend workflow router is mounted at "/api/workflows/...".
// Because the shared client's baseURL ALREADY ends in "/api", paths here are
// written WITHOUT the leading "/api" (e.g. "/workflows/..."), so the final URL
// is ".../api/workflows/..." and not ".../api/api/workflows/...".
//
// The header-stub authHeaders() and the standalone API_BASE/fetch wrapper from
// the reference implementation are intentionally gone — auth is the shared
// client's job. Function names/exports are unchanged so callers are unaffected.

import { api } from "@/lib/api";
import type {
  AuditEntry,
  AvailableAction,
  ChildInstance,
  ClarifyAnswer,
  ClarifyResult,
  DefinitionSummary,
  DefinitionVersion,
  DefinitionVersionSummary,
  DiscussionComment,
  GenerateResult,
  InstanceActivity,
  StepTypeMeta,
  WorkflowDefinitionBody,
  WorkflowInstance,
  WorkflowTask,
} from "./types";

const BASE = "/workflows";

export const workflowApi = {
  // catalog
  stepTypes: () =>
    api.get<StepTypeMeta[]>(`${BASE}/step-types`).then((r) => r.data),

  // Runner config. The unified platform + strict roles are always on (no flags);
  // `dev_sweep` says whether the dev-only background sweeper / dev controls (manual
  // sweep, test-event-deliver) are enabled. Prod uses the Celery beat → false.
  config: () =>
    api
      .get<{ dev_sweep: boolean }>(`${BASE}/config`)
      .then((r) => r.data),
  // Permission primitive — is the current user the creator/owner of this agreement?
  // Modules call this for creator-owns-send/receive gating (reuses created_by).
  checkOwner: (subjectRef: string) =>
    api
      .get<{ is_owner: boolean; created_by: string | null; current_user_id: string | null; found: boolean }>(
        `${BASE}/permits/owner`,
        { params: { subject_ref: subjectRef } },
      )
      .then((r) => r.data),

  // definitions
  listDefinitions: () =>
    api.get<DefinitionSummary[]>(`${BASE}/definitions`).then((r) => r.data),
  getDefinition: (key: string, version?: number) =>
    api
      .get<DefinitionVersion>(`${BASE}/definitions/${key}`, {
        params: version ? { version } : undefined,
      })
      .then((r) => r.data),
  // Version history for one workflow (newest first), for the library's History view.
  listVersions: (key: string) =>
    api
      .get<DefinitionVersionSummary[]>(`${BASE}/definitions/${key}/versions`)
      .then((r) => r.data),
  saveDefinition: (body: WorkflowDefinitionBody, publish = false) =>
    api
      .post<DefinitionVersion>(`${BASE}/definitions`, { body, publish })
      .then((r) => r.data),
  publish: (key: string, version: number) =>
    api
      .post<DefinitionVersion>(`${BASE}/definitions/${key}/publish/${version}`)
      .then((r) => r.data),
  // DEV/test only (gated to WORKFLOW_UNIFIED on the backend): wipe one template's
  // workflow (definition + versions + instances + audit) so it returns to the
  // "no workflow yet" state. Body carries the key (avoids a colon in the URL path).
  resetTemplateWorkflow: (key: string) =>
    api
      .post<{
        key: string
        instances_deleted: number
        audit_deleted: number
        versions_deleted: number
        definition_deleted: boolean
      }>(`${BASE}/definitions/reset`, { key })
      .then((r) => r.data),
  // DEV/test only (gated to WORKFLOW_UNIFIED): study+site-SPECIFIC reset. Deletes
  // ONE agreement (subject_ref) + its workflow instance(s) + children, freeing just
  // that (study, site, template) slot. Keeps the shared definition + other sites.
  resetAgreementWorkflow: (subjectRef: string) =>
    api
      .post<{
        subject_ref: string
        instances_deleted: number
        audit_deleted: number
        agreements_deleted: number
      }>(`${BASE}/instances/reset-agreement`, { subject_ref: subjectRef })
      .then((r) => r.data),

  // STEP 1 (clarify): ask which shape-changing things are ambiguous before drafting.
  // Gated to WORKFLOW_UNIFIED on the backend. Returns {questions, clear}; the LLM
  // only classifies ambiguity here — it writes/runs nothing.
  clarifyWorkflow: (description: string, mermaid?: string) =>
    api
      .post<ClarifyResult>(`${BASE}/generate/clarify`, { description, mermaid })
      .then((r) => r.data),

  // STEP 2 (confirm): turn the description (+ confirmed answers + optional pasted
  // Mermaid) into a DRAFT body + a plain-English summary. Never saves/publishes; the
  // caller shows it for approval, then loads it onto the canvas and publishes (STEP 3).
  //
  // REFINE (iterative): pass `prior` (the current generated definition) + `feedback`
  // (a change request) to MODIFY that workflow instead of redrafting — the confirm
  // screen's "Request changes" loop. `feedbackLog` carries earlier rounds for context
  // so refinements compound. Same validation/normalizer/confirm response shape.
  generate: (
    description: string, key?: string, name?: string,
    answers?: ClarifyAnswer[], mermaid?: string,
    prior?: WorkflowDefinitionBody, feedback?: string, feedbackLog?: string[],
  ) =>
    api
      .post<GenerateResult>(`${BASE}/generate`, {
        description, key, name, answers, mermaid,
        prior, feedback, feedback_log: feedbackLog,
      })
      .then((r) => r.data),

  // instances
  startInstance: (
    definition_key: string,
    context: Record<string, unknown>,
    subject_ref?: string,
  ) =>
    api
      .post<WorkflowInstance>(`${BASE}/instances`, {
        definition_key,
        context,
        subject_ref,
      })
      .then((r) => r.data),
  // Idempotent: returns the existing instance for (subject_ref, definition_key) or
  // starts exactly one. Used by the unified page (definition_key = "tpl:<id>").
  ensureInstance: (
    definition_key: string,
    subject_ref: string,
    context: Record<string, unknown> = {},
  ) =>
    api
      .post<WorkflowInstance>(`${BASE}/instances/ensure`, {
        definition_key,
        subject_ref,
        context,
      })
      .then((r) => r.data),
  getInstance: (id: number) =>
    api.get<WorkflowInstance>(`${BASE}/instances/${id}`).then((r) => r.data),
  // Read-only: resolve the newest instance for a subject (e.g. an agreement id),
  // optionally scoped to a definition_key (CDA/CTA). Returns null when none exists.
  // Backing the read-only "Engine step" overlay — observes, never advances.
  findInstance: (subjectRef: string, definitionKey?: string) =>
    api
      .get<WorkflowInstance | null>(`${BASE}/instances`, {
        params: definitionKey
          ? { subject_ref: subjectRef, definition_key: definitionKey }
          : { subject_ref: subjectRef },
      })
      .then((r) => r.data),
  getActions: (id: number) =>
    api
      .get<AvailableAction[]>(`${BASE}/instances/${id}/actions`)
      .then((r) => r.data),
  act: (
    id: number,
    transition_id: string,
    payload: Record<string, unknown>,
    comment?: string,
  ) =>
    api
      .post<WorkflowInstance>(`${BASE}/instances/${id}/actions`, {
        transition_id,
        payload,
        comment,
      })
      .then((r) => r.data),
  cancel: (id: number, comment?: string) =>
    api
      .post<WorkflowInstance>(`${BASE}/instances/${id}/cancel`, {
        transition_id: "",
        payload: {},
        comment,
      })
      .then((r) => r.data),
  getAudit: (id: number) =>
    api.get<AuditEntry[]>(`${BASE}/instances/${id}/audit`).then((r) => r.data),

  // Tasks (V2): my open work items across ALL instances, + lifecycle.
  tasks: (status: "open" | "completed" | "cancelled" = "open") =>
    api
      .get<WorkflowTask[]>(`${BASE}/tasks`, { params: { status } })
      .then((r) => r.data),
  claimTask: (taskId: number) =>
    api.post<WorkflowTask>(`${BASE}/tasks/${taskId}/claim`).then((r) => r.data),
  reassignTask: (taskId: number, userId: string) =>
    api
      .post<WorkflowTask>(`${BASE}/tasks/${taskId}/reassign`, { user_id: userId })
      .then((r) => r.data),

  // Engine activity for one instance (read-only): job executions + armed timers.
  getActivity: (id: number) =>
    api.get<InstanceActivity>(`${BASE}/instances/${id}/activity`).then((r) => r.data),
  // Retry a FAILED job (resets it to pending for the next sweep).
  retryJob: (instanceId: number, jobId: number) =>
    api
      .post<{ status: string }>(`${BASE}/instances/${instanceId}/jobs/${jobId}/retry`)
      .then((r) => r.data),
  // DEV (gated to WORKFLOW_UNIFIED): run the timer + job sweeps once, NOW —
  // dev stacks run no celery beat, so the UI triggers sweeps to make pending
  // jobs/due timers visibly execute.
  runSweeps: () =>
    api
      .post<{ timers_fired: number; jobs_processed: number }>(`${BASE}/run-sweeps`)
      .then((r) => r.data),

  // External message events (V2): deliver an event correlated by subject_ref.
  postEvent: (name: string, subjectRef: string, payload: Record<string, unknown> = {}) =>
    api
      .post<{ delivered: number }>(`${BASE}/events`, {
        name,
        subject_ref: subjectRef,
        payload,
      })
      .then((r) => r.data),

  // Sub-workflows (V2): the child instances spawned by this parent's call steps.
  getChildren: (id: number) =>
    api.get<ChildInstance[]>(`${BASE}/instances/${id}/children`).then((r) => r.data),

  // Discussion (NEED 1): a tracked two-party comment exchange on a discussion step.
  // Reuses agreement_comments server-side; rows are append-only (the audit trail).
  // Gated to WORKFLOW_UNIFIED on the backend (403 when off). Resolve = the normal
  // act() advance on the step's resolve transition.
  getDiscussion: (id: number) =>
    api.get<DiscussionComment[]>(`${BASE}/instances/${id}/discussion`).then((r) => r.data),
  postDiscussion: (id: number, content: string, party: "internal" | "external" = "internal") =>
    api
      .post<DiscussionComment>(`${BASE}/instances/${id}/discussion`, { content, party })
      .then((r) => r.data),
};
