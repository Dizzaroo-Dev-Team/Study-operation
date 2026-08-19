// types.ts
// TypeScript mirror of the backend workflow schema. Keeping these in sync with
// schemas.py is what lets the builder produce JSON the engine can run verbatim.

export type StepType =
  | "form" | "approval" | "signature" | "decision"
  | "parallel" | "ordered_signing" | "broadcast"
  | "terminal"
  // V2 step kinds (tokens/gateways, automation, orchestration)
  | "split" | "join" | "job" | "wait_message" | "wait_condition" | "call";
export type AssigneeType = "role" | "user" | "context" | "system";
export type FieldType = "text" | "number" | "boolean" | "date" | "select";

export type ConditionOperator =
  | "eq" | "neq" | "gt" | "gte" | "lt" | "lte"
  | "in" | "not_in" | "is_true" | "is_false" | "exists" | "not_exists";

export interface Clause {
  field: string;
  op: ConditionOperator;
  value?: unknown;
}

export interface Condition {
  all?: (Condition | Clause)[];
  any?: (Condition | Clause)[];
}

export interface Assignee {
  type: AssigneeType;
  value?: string;
}

export interface FormField {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: string[];
}

export interface Transition {
  id: string;
  to: string;
  label: string;
  action: string; // submit | approve | reject | sign | auto | custom
  condition?: Condition | null;
  requires_comment?: boolean;
}

export interface Step {
  id: string;
  type: StepType;
  name: string;
  description?: string;
  assignee?: Assignee | null;
  /** Which capability module the runner invokes for this step (e.g. "signing",
   *  "review"). Engine-ignored; unset -> runner falls back to the generic renderer. */
  module?: string | null;
  config: Record<string, unknown> & { fields?: FormField[] };
  transitions: Transition[];
}

export interface ContextVariable {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
}

export interface WorkflowDefinitionBody {
  key: string;
  name: string;
  description?: string;
  /** The plain-English prompt this workflow was authored from (AI builder input).
   *  Saved with every version so history/clone/edit can pre-fill the prompt box. */
  source_prompt?: string | null;
  start_step: string;
  context_schema: ContextVariable[];
  steps: Step[];
}

// --- API response shapes ---
export interface DefinitionSummary {
  id: number;
  key: string;
  name: string;
  latest_version: number;
  published_version: number | null;
  created_at: string;
  description?: string | null;    // description of the current default version
  published_by?: string | null;   // who published the current default version
  published_at?: string | null;   // when
}

// One row in a workflow's version-history browser (no body — fetched on demand).
export interface DefinitionVersionSummary {
  version: number;
  is_published: boolean;
  name: string;
  description?: string | null;
  /** The authoring prompt stored in this version's body — shown in the history
   *  browser and pre-filled when the version is cloned/edited. */
  source_prompt?: string | null;
  created_at: string;
  published_by?: string | null;
  published_at?: string | null;
}

export interface DefinitionVersion {
  id: number;
  definition_id: number;
  version: number;
  is_published: boolean;
  body: WorkflowDefinitionBody;
  created_at: string;
  published_by?: string | null;
  published_at?: string | null;
}

export interface AvailableAction {
  transition_id: string;
  action: string;
  label: string;
  to: string;
  requires_comment: boolean;
}

export interface WorkflowInstance {
  id: number;
  definition_key: string;
  definition_version: number;
  status: "active" | "completed" | "cancelled";
  current_step: string | null;
  current_step_type: StepType | null;
  current_step_name: string | null;
  subject_ref: string | null;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// V2 task (work item) — one row per open human work unit, the worklist
// read-model behind GET /workflows/tasks. Mirrors service._task_view.
export interface WorkflowTask {
  id: number;
  instance_id: number;
  definition_key: string;
  subject_ref: string | null;
  step_id: string;
  slot_id: string;
  name: string;
  status: "open" | "claimed" | "completed" | "cancelled" | "expired";
  assignee_type: string | null;
  assignee_value: string | null;
  resolved_user_id: string | null;
  claimed_by: string | null;
  due_at: string | null;
  created_at: string;
}

// V2 engine activity for one instance (read-only): automated-job executions
// and armed boundary timers. Backs the job panel + timer indicator.
export interface WorkflowJobRow {
  id: number;
  step_id: string;
  kind: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  attempts: number;
  max_attempts: number;
  error: string | null;
  /** The handler's raw result. Used to surface a DEGRADED completion (e.g.
   *  generate_document with no PDF backend returns {generated:false, reason}). */
  result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}
export interface WorkflowTimerRow {
  id: number;
  step_id: string;
  action: string;
  fire_at: string;
  status: "pending" | "fired" | "cancelled";
}
export interface InstanceActivity {
  jobs: WorkflowJobRow[];
  timers: WorkflowTimerRow[];
}

// V2 sub-workflow child summary (GET /instances/{id}/children).
export interface ChildInstance {
  id: number;
  definition_key: string;
  status: "active" | "completed" | "cancelled";
  current_step: string | null;
  parent_step_id: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  actor: string | null;
  action: string;
  from_step: string | null;
  to_step: string | null;
  comment: string | null;
  created_at: string;
}

export interface StepTypeMeta {
  type: StepType;
  label: string;
  description: string;
  icon: string;
  color: string;
  supports_assignee: boolean;
  config_schema: Record<string, unknown>;
}

// Discussion step (NEED 1): one tracked comment in a two-party exchange, stored
// server-side by reusing agreement_comments. Visible to both parties; append-only.
export interface DiscussionComment {
  id: string;
  party: "internal" | "external" | "system";
  author: string | null;
  content: string;
  created_at: string;
}

// --- LLM auto-create / clarify→confirm authoring ---
export interface ClarifyQuestion {
  id: string;                          // stable catalog id (e.g. "signers")
  question: string;                    // human-readable question
  options: string[];                   // suggested answers the UI renders
}
export interface ClarifyResult {
  questions: ClarifyQuestion[];        // ambiguous, shape-changing things to confirm
  clear: boolean;                      // true when nothing needs asking
}
export interface ClarifyAnswer {
  id: string;
  question?: string;
  answer: string;
}
export interface GenerateResult {
  body?: WorkflowDefinitionBody;       // a validated DRAFT (not saved/published)
  assumptions?: string[];              // choices the AI made — for human review
  summary?: string;                    // plain-English paragraph for the confirm screen
  needs_clarification?: string;        // present when the description was too vague
}
