"""
schemas.py
==========

This module defines the *language* of the workflow platform: the exact shape of
a workflow definition (the data that replaces hardcoded flows), plus the request
and response contracts for the API.

Key idea
--------
A workflow is DATA, not code. A definition is a list of `steps`. Each step has a
`type` (form / approval / signature / decision / terminal), an `assignee` (who may
act), and a list of `transitions` (the arrows leaving that step). A transition may
carry a `condition` so the path can branch ("Does a CRO exist?").

Because conditions are structured JSON (field / operator / value) rather than
free-text code, the drag-and-drop builder can generate them safely and the engine
can evaluate them without ever running arbitrary code.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class StepType(str, Enum):
    """The reusable kinds of step. The frontend ships one generic component per
    type, so adding a new document workflow never requires new step components."""

    FORM = "form"            # collect / edit structured data (e.g. draft the agreement)
    APPROVAL = "approval"    # a person approves or rejects
    SIGNATURE = "signature"  # a person signs
    DECISION = "decision"    # automatic branch based on context (no human click)
    PARALLEL = "parallel"    # several review branches open at once; advances on quorum
    ORDERED_SIGNING = "ordered_signing"  # ordered signer list; one slot open at a time
    BROADCAST = "broadcast"  # notify many recipients, no action, auto-advances
    TERMINAL = "terminal"    # an end state (Executed, Cancelled, Rejected)
    # V2 gateways (Phase 2): real parallel branches that are FULL SEQUENCES.
    SPLIT = "split"          # spawns one token per (condition-passing) outgoing arrow
    JOIN = "join"            # collects tokens; advances when its join policy is met
    # V2 automation (Phase 4): an automated step. The engine parks; the job
    # executor runs the registered handler and the kernel routes on
    # job_done / job_failed with an explicit output mapping.
    JOB = "job"
    # V2 orchestration (Phase 5): wait for an external message correlated by
    # subject_ref, or spawn child workflow instance(s) and await completion.
    WAIT_MESSAGE = "wait_message"
    CALL = "call"
    # GENERAL hold: park until a named, REGISTERED condition becomes true (re-checked
    # on the sweep), then auto-continue. Pluggable conditions live in waits.py.
    WAIT_CONDITION = "wait_condition"


class AssigneeType(str, Enum):
    ROLE = "role"          # anyone holding this role may act
    USER = "user"          # a specific user id
    CONTEXT = "context"    # resolve from instance context (e.g. context["pi_user_id"])
    SYSTEM = "system"      # the engine itself acts (used by decision steps)


class ConditionOperator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    SELECT = "select"


# ---------------------------------------------------------------------------
# Conditions  (structured, safe, no eval)
# ---------------------------------------------------------------------------
class Clause(BaseModel):
    """A single comparison against the instance context, e.g. has_cro == true."""

    field: str
    op: ConditionOperator
    value: Any = None


class Condition(BaseModel):
    """A boolean group of clauses. `all` => AND, `any` => OR. Groups may nest.

    Example: branch only when a CRO exists AND value is over 50k:
        {"all": [{"field": "has_cro", "op": "is_true"},
                 {"field": "contract_value", "op": "gt", "value": 50000}]}
    """

    all: Optional[list[Union["Condition", Clause]]] = None
    any: Optional[list[Union["Condition", Clause]]] = None


Condition.model_rebuild()


# ---------------------------------------------------------------------------
# Step building blocks
# ---------------------------------------------------------------------------
class Assignee(BaseModel):
    type: AssigneeType
    value: Optional[str] = None  # role name, user id, or context key

    @field_validator("value")
    @classmethod
    def _value_required_unless_system(cls, v, info):
        a_type = info.data.get("type")
        if a_type in (AssigneeType.ROLE, AssigneeType.USER, AssigneeType.CONTEXT) and not v:
            raise ValueError(f"assignee.value is required for type '{a_type}'")
        return v


class FormField(BaseModel):
    key: str
    label: str
    type: FieldType = FieldType.TEXT
    required: bool = False
    options: Optional[list[str]] = None  # for SELECT


# ---------------------------------------------------------------------------
# Parallel review (fan-out) — generic branch-state machinery
# ---------------------------------------------------------------------------
# A "parallel" step opens several independent review BRANCHES at once. Each
# branch is a mini approval slot with its own assignee and approve/reject verbs.
# Per-branch votes are recorded in instance.context["_branches"][<step_id>], so
# all state is JSON (no DB migration). The step itself is the implicit JOIN: it
# only advances once QUORUM resolves. This shape is intentionally generic so
# later work (mixed fan-out, ordered signing) can reuse it.
class BranchSpec(BaseModel):
    """One slot within a parallel / fan-out step.

    `kind` distinguishes the two fan-out roles (the real CTA "Send to Site Team"
    pattern):
      * "action" — a reviewer who must act; quorum is computed over these only.
      * "notify" — a recipient who is merely informed (PI, Site Manager, CRC);
                   recorded as delivered on entry, never gates progress, never
                   appears as an available action.
    """

    id: str
    name: str
    kind: Literal["action", "notify"] = "action"
    assignee: Optional[Assignee] = None
    action_approve: str = "approve"
    action_reject: str = "reject"


class Quorum(BaseModel):
    """How many branch approvals are needed to advance along the approved path.

      * all       — every branch must approve (value ignored)
      * n_of_m    — at least `value` branches must approve
      * percent   — at least ceil(M * value / 100) branches must approve
    """

    mode: Literal["all", "n_of_m", "percent"]
    value: Optional[int] = None

    @field_validator("value")
    @classmethod
    def _value_required_for_threshold_modes(cls, v, info):
        mode = info.data.get("mode")
        if mode in ("n_of_m", "percent"):
            if v is None or v <= 0:
                raise ValueError(f"quorum.value must be a positive int for mode '{mode}'")
        return v


class ParallelConfig(BaseModel):
    """Typed view of a parallel step's `config` dict.

    Parsed from ``step.config`` by the engine; not a new Step field, so the
    generic Step.config carrier (same place form `fields` live) is reused.
    """

    branches: list[BranchSpec] = Field(..., min_length=1)
    quorum: Quorum
    on_reject: Literal["fail_fast", "count"] = "count"

    def branch(self, branch_id: str) -> Optional[BranchSpec]:
        return next((b for b in self.branches if b.id == branch_id), None)


# ---------------------------------------------------------------------------
# Ordered signing (sequential signer list) — reuses the _branches slot/audit
# machinery, adds strict ordering: only the current signer's slot is open; the
# next unlocks only after the current one signs. (Real CTA signature phase:
# Site Director -> PI -> VP.)
# ---------------------------------------------------------------------------
class SignerSlot(BaseModel):
    """One signer in an ordered signing step."""

    id: str
    name: str
    assignee: Optional[Assignee] = None


class OrderedSigningConfig(BaseModel):
    """Typed view of an ordered_signing step's `config` dict.

    `signers` is an ORDERED list — index order is the signing order. Progress is
    tracked in context["_branches"][step_id][<signer_id>] = {actor, decision, at}
    exactly like parallel/fan-out, so the same vote/audit plumbing is reused.
    """

    signers: list[SignerSlot] = Field(..., min_length=1)

    def signer(self, signer_id: str) -> Optional[SignerSlot]:
        return next((s for s in self.signers if s.id == signer_id), None)


# ---------------------------------------------------------------------------
# Broadcast (notify-all, no action) — pure delivery. Reuses the notify-delivery
# recording + audit path from the fan-out work; the step requires no action and
# auto-advances through its single "broadcast_done" transition. (Real CTA
# "Distribute Final Copy".)
# ---------------------------------------------------------------------------
class BroadcastConfig(BaseModel):
    """Typed view of a broadcast step's `config` dict.

    `recipients` reuses SignerSlot's {id, name, assignee?} shape — all are
    notify-only; none gate progress.
    """

    recipients: list[SignerSlot] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Join policy (V2 Phase 2). The GENERALIZED completion rule shared by explicit
# join gateways and the parallel macro's quorum: how many "ok" outcomes are
# needed before the join fires. Quorum IS a join policy — the parallel step's
# {quorum, on_reject} compiles onto this same evaluator.
# ---------------------------------------------------------------------------
class JoinPolicy(BaseModel):
    """Typed view of a join step's ``config["join"]`` dict.

      * all     — every incoming token must arrive (value ignored; the default)
      * n_of_m  — at least `value` tokens must arrive (stragglers are cancelled)
      * percent — at least ceil(expected * value / 100) must arrive
    """

    mode: Literal["all", "n_of_m", "percent"] = "all"
    value: Optional[int] = None

    @field_validator("value")
    @classmethod
    def _value_required_for_threshold_modes(cls, v, info):
        mode = info.data.get("mode")
        if mode in ("n_of_m", "percent") and (v is None or v <= 0):
            raise ValueError(f"join.value must be a positive int for mode '{mode}'")
        return v


# ---------------------------------------------------------------------------
# Timer + Job configs (V2 Phase 4)
# ---------------------------------------------------------------------------
class TimerConfig(BaseModel):
    """Typed view of a step's ``config["timer"]``: after `seconds` parked on
    this step, the scheduler fires the step's transition whose action is
    `action` (escalation, timeout-reject, reminder hop, ...)."""

    seconds: int = Field(..., gt=0)
    action: str


class JobConfig(BaseModel):
    """Typed view of a JOB step's ``config["job"]``.

    `kind` selects the registered handler; `params` are passed verbatim.
    `output` is the EXPLICIT result-to-context mapping
    ({context_key: dotted.path.into.result}) — nothing merges implicitly.
    `max_attempts` retries the handler before the job_failed transition fires.
    """

    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=1, ge=1)
    output: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Message + Call configs (V2 Phase 5)
# ---------------------------------------------------------------------------
class MessageConfig(BaseModel):
    """Typed view of a wait_message step's ``config["message"]``: the step
    parks until an external event named `name` arrives for this instance's
    correlation key (subject_ref). `output` maps the event payload into context
    — explicitly, like job results."""

    name: str
    output: dict[str, str] = Field(default_factory=dict)


class WaitConfig(BaseModel):
    """Typed view of a wait_condition step's ``config["wait"]``: the step PARKS until a
    named, REGISTERED condition (waits.py) becomes true, re-checked on the sweep, then
    auto-continues via its ``condition_met`` transition.
      * condition — the registered checker name (e.g. "budget_ready").
      * params    — passed to the checker (checker-specific options).
      * message   — authorable status shown in the runner while holding
                    (e.g. "Waiting for the budget to be finalized")."""

    condition: str
    params: dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None


class CallConfig(BaseModel):
    """Typed view of a call step's ``config["call"]``.

    Spawns child instance(s) of `definition_key` and parks until enough have
    completed per `join` (the same join policy as gateways/quorum).
      * context_map — {child_context_key: parent_context_key} copied at spawn.
      * items_path  — a parent context key holding a LIST: one child per item
        (multi-instance); each child also gets {"item": <item>, "item_index": i}.
    """

    definition_key: str
    context_map: dict[str, str] = Field(default_factory=dict)
    items_path: Optional[str] = None
    join: JoinPolicy = Field(default_factory=JoinPolicy)


class Transition(BaseModel):
    """An arrow leaving a step.

    `action` is the verb a user performs to fire it ("submit", "approve",
    "reject", "sign"). The special action "auto" means the engine fires it itself
    when `condition` is true — that is how DECISION steps branch with no human.
    """

    id: str
    to: str                       # id of the destination step
    label: str
    action: str = "next"          # "submit" | "approve" | "reject" | "sign" | "auto" | custom
    condition: Optional[Condition] = None
    requires_comment: bool = False


class Step(BaseModel):
    id: str
    type: StepType
    name: str
    description: Optional[str] = None
    assignee: Optional[Assignee] = None       # not needed for terminal/decision
    # Which capability MODULE the runner invokes for this step (e.g. "signing",
    # "review", "approval"). Optional + engine-ignored: the engine stays the pure
    # state machine; only the runner reads `module`. Unset -> runner falls back to
    # the generic step renderer. The workflow/LLM author sets this per step.
    module: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)  # e.g. {"fields": [...]} for forms
    transitions: list[Transition] = Field(default_factory=list)

    @field_validator("transitions")
    @classmethod
    def _terminal_has_no_transitions(cls, v, info):
        if info.data.get("type") == StepType.TERMINAL and v:
            raise ValueError("terminal steps cannot have outgoing transitions")
        return v


class ContextVariable(BaseModel):
    """Declares a variable the workflow tracks (used by conditions and forms)."""

    key: str
    label: str
    type: FieldType = FieldType.TEXT
    options: Optional[list[str]] = None


class WorkflowDefinitionBody(BaseModel):
    """The full flow-as-data. This is what the builder produces and the engine runs."""

    key: str = Field(..., description="Stable code, e.g. 'CTA', 'CDA', 'NDA'")
    name: str
    description: Optional[str] = None
    # The plain-English prompt this workflow was authored from (the AI builder's
    # description box). Persisted with every version so opening/cloning it from
    # the history browser can pre-fill the same prompt. None for hand-drawn flows.
    source_prompt: Optional[str] = None
    start_step: str
    context_schema: list[ContextVariable] = Field(default_factory=list)
    steps: list[Step]

    @field_validator("steps")
    @classmethod
    def _validate_graph(cls, steps, info):
        ids = [s.id for s in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step ids found")
        id_set = set(ids)
        start = info.data.get("start_step")
        if start and start not in id_set:
            raise ValueError(f"start_step '{start}' is not a defined step")
        for s in steps:
            for t in s.transitions:
                if t.to not in id_set:
                    raise ValueError(f"transition '{t.id}' points to unknown step '{t.to}'")
        terminals = [s for s in steps if s.type == StepType.TERMINAL]
        if not terminals:
            raise ValueError("a workflow must have at least one terminal step")
        # V2 gateways: structural rules the engine relies on at runtime.
        for s in steps:
            if s.type == StepType.SPLIT and len(s.transitions) < 2:
                raise ValueError(f"split step '{s.id}' needs at least 2 outgoing transitions")
            if s.type == StepType.JOIN:
                if not any(t.action == "join_met" for t in s.transitions):
                    raise ValueError(f"join step '{s.id}' needs a 'join_met' transition")
                if "join" in (s.config or {}):
                    JoinPolicy.model_validate(s.config["join"])  # fail at save, not runtime
            # V2 timers/jobs: validate at save, not at runtime.
            if "timer" in (s.config or {}):
                tc = TimerConfig.model_validate(s.config["timer"])
                if not any(t.action == tc.action for t in s.transitions):
                    raise ValueError(
                        f"step '{s.id}' timer fires action '{tc.action}' but has no such transition")
            if s.type == StepType.JOB:
                JobConfig.model_validate((s.config or {}).get("job") or {})
                if not any(t.action == "job_done" for t in s.transitions):
                    raise ValueError(f"job step '{s.id}' needs a 'job_done' transition")
            if s.type == StepType.WAIT_MESSAGE:
                MessageConfig.model_validate((s.config or {}).get("message") or {})
                if not any(t.action == "message_received" for t in s.transitions):
                    raise ValueError(
                        f"wait_message step '{s.id}' needs a 'message_received' transition")
            if s.type == StepType.WAIT_CONDITION:
                WaitConfig.model_validate((s.config or {}).get("wait") or {})
                if not any(t.action == "condition_met" for t in s.transitions):
                    raise ValueError(
                        f"wait_condition step '{s.id}' needs a 'condition_met' transition")
            if s.type == StepType.CALL:
                CallConfig.model_validate((s.config or {}).get("call") or {})
                if not any(t.action == "children_done" for t in s.transitions):
                    raise ValueError(f"call step '{s.id}' needs a 'children_done' transition")
        return steps


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------
class DefinitionCreate(BaseModel):
    body: WorkflowDefinitionBody
    publish: bool = False


class DefinitionVersionOut(BaseModel):
    id: int
    definition_id: int
    version: int
    is_published: bool
    body: WorkflowDefinitionBody
    created_at: datetime
    # Governance/audit: WHO published this version and WHEN (None for drafts).
    published_by: Optional[str] = None
    published_at: Optional[str] = None

    class Config:
        from_attributes = True


class DefinitionOut(BaseModel):
    id: int
    key: str
    name: str
    latest_version: int
    published_version: Optional[int] = None
    created_at: datetime
    # Free-text description of the current default version (read from its body JSON).
    description: Optional[str] = None
    # Who published the current default version, and when.
    published_by: Optional[str] = None
    published_at: Optional[str] = None

    class Config:
        from_attributes = True


class DefinitionVersionSummary(BaseModel):
    """One row in a definition's version-history browser. No `body` — kept light;
    the builder fetches the full body separately when editing/cloning a version."""

    version: int
    is_published: bool
    name: str
    description: Optional[str] = None
    # The authoring prompt stored in this version's body (see WorkflowDefinitionBody.
    # source_prompt) — lets the history browser show/prefill what was asked for.
    source_prompt: Optional[str] = None
    created_at: datetime
    published_by: Optional[str] = None
    published_at: Optional[str] = None


class InstanceCreate(BaseModel):
    definition_key: str
    subject_ref: Optional[str] = Field(
        default=None, description="Your domain object id, e.g. the agreement id"
    )
    context: dict[str, Any] = Field(default_factory=dict)


class ResetRequest(BaseModel):
    key: str = Field(description="Definition key to wipe, e.g. tpl:<template_id>")


class AgreementResetRequest(BaseModel):
    subject_ref: str = Field(
        description="Agreement id to reset (study+site+template specific). Deletes this "
                    "agreement + its workflow instance(s); keeps the shared definition.")


class ActionRequest(BaseModel):
    transition_id: str
    payload: dict[str, Any] = Field(default_factory=dict)  # form data, signature meta, etc.
    comment: Optional[str] = None


class AvailableAction(BaseModel):
    transition_id: str
    action: str
    label: str
    to: str
    requires_comment: bool


# ---------------------------------------------------------------------------
# Discussion step (NEED 1): a tracked, in-system two-party comment exchange on a
# workflow step. Stored by REUSING agreement_comments (AgreementComment) — no new
# comment table. Visible to both parties + append-only (the rows are the audit).
# ---------------------------------------------------------------------------
class DiscussionPost(BaseModel):
    content: str
    # Which side posted — maps to AgreementComment.comment_type (internal/external).
    # Defaults to "internal" (on-system reviewers). The engine/step never branch on it;
    # it only tags the author's side for transparency.
    party: Literal["internal", "external"] = "internal"


class DiscussionComment(BaseModel):
    id: str
    party: str                       # "internal" | "external" | "system"
    author: Optional[str] = None     # created_by (None for system)
    content: str
    created_at: datetime


class AuditEntryOut(BaseModel):
    id: int
    actor: Optional[str] = None
    action: str
    from_step: Optional[str] = None
    to_step: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class InstanceOut(BaseModel):
    id: int
    definition_key: str
    definition_version: int
    status: str
    current_step: Optional[str] = None
    current_step_type: Optional[str] = None
    current_step_name: Optional[str] = None
    subject_ref: Optional[str] = None
    context: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CurrentUser(BaseModel):
    """Minimal user shape the engine needs. Map this from YOUR auth system."""

    id: str
    roles: list[str] = Field(default_factory=list)


class ClarifyAnswer(BaseModel):
    """One answered clarifying question, fed back into generation."""

    id: str
    question: Optional[str] = None
    answer: str


class ClarifyRequest(BaseModel):
    """POST /api/workflows/generate/clarify — ask what's ambiguous before drafting.

    `mermaid` is an optional pasted flowchart the LLM interprets alongside the text."""

    description: str = ""
    mermaid: Optional[str] = None


class GenerateRequest(BaseModel):
    """POST /api/workflows/generate — describe a workflow in plain English.

    `answers` carries the user's confirmed clarify Q&A (if any); the draft honors them.
    `mermaid` is an optional pasted flowchart the LLM interprets for the intended shape.

    REFINE mode: when `prior` (the previously generated definition) and `feedback`
    (the user's change request) are BOTH present, the generator MODIFIES `prior` per
    the feedback instead of drafting from scratch — preserving everything the user
    didn't ask to change. `feedback_log` is the accumulated change requests from prior
    rounds, passed for context so successive refinements compound. The original
    `description`/`mermaid` are still sent as background context."""

    description: str = ""
    key: Optional[str] = None
    name: Optional[str] = None
    answers: Optional[list[ClarifyAnswer]] = None
    mermaid: Optional[str] = None
    prior: Optional[dict[str, Any]] = None        # the existing draft to modify (refine)
    feedback: Optional[str] = None                # the change request for this round
    feedback_log: Optional[list[str]] = None      # earlier rounds' feedback, for context
