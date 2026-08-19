"""
engine.py
=========

The generic state machine. It is intentionally ignorant of CTA, CDA, or any
document type. It understands only steps, transitions, conditions, and who may
act. The same engine runs every workflow ever drawn in the builder.

Everything here is pure logic over (definition, current_step, context, user).
It does not touch the database or the web layer, which makes it fully unit
testable and reusable.

PURE LOGIC — touches no DB, stays synchronous.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from .conditions import _missing, evaluate_condition, referenced_fields
from .schemas import (
    AssigneeType,
    AvailableAction,
    BranchSpec,
    BroadcastConfig,
    CurrentUser,
    FieldType,
    FormField,
    JoinPolicy,
    OrderedSigningConfig,
    ParallelConfig,
    SignerSlot,
    Step,
    StepType,
    Transition,
    WorkflowDefinitionBody,
)


# ---------------------------------------------------------------------------
# ROLE MATCHING — the canonical form for a role identifier.
# Roles come from IAM as free-form display strings ("Contract Specialist",
# "CRA", ...) — NOT a fixed enum. A workflow step's `role` assignee is matched
# against the user's ACTUAL IAM roles by comparing a normalized SLUG on BOTH
# sides (lowercase, non-alphanumeric runs -> "_"), so "Contract Specialist",
# "contract_specialist" and "CONTRACT-SPECIALIST" all match. There is no
# allow-list and nothing is squashed to a default.
# ---------------------------------------------------------------------------
def role_slug(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def role_matches(assignee_value: Optional[str], user_roles: Optional[list[str]]) -> bool:
    """True iff the step's role assignee matches any of the user's real roles,
    compared as slugs on both sides."""
    target = role_slug(assignee_value)
    if not target:
        return False
    return target in {role_slug(r) for r in (user_roles or [])}


# ---------------------------------------------------------------------------
# JOIN POLICY (V2 Phase 2) — the one completion evaluator. The parallel macro's
# quorum and explicit join gateways both resolve through this function, so
# "quorum" is literally a join policy.
# ---------------------------------------------------------------------------
def evaluate_join_policy(mode: str, value: Optional[int], on_fail: str,
                         total: int, ok: int, fail: int, open_count: int) -> str:
    """'met' | 'failed' | 'open' given ok/fail/open outcome counts out of `total`.

    on_fail: 'fail_fast' fails on the first fail outcome; 'count' fails only
    when the threshold becomes unreachable. Either way, all-resolved-without-
    meeting-threshold is failed."""
    if mode == "all":
        threshold = total
    elif mode == "n_of_m":
        threshold = int(value)
    elif mode == "percent":
        threshold = math.ceil(total * int(value) / 100)
    else:
        raise EngineError(f"Unknown join/quorum mode '{mode}'")

    if ok >= threshold:
        return "met"
    if on_fail == "fail_fast" and fail >= 1:
        return "failed"
    if on_fail == "count" and ok + open_count < threshold:
        return "failed"
    if open_count == 0:
        return "failed"
    return "open"


class EngineError(Exception):
    """Raised for any illegal move (bad transition, unauthorized, missing comment)."""


# How many automatic (decision) hops we will follow in a row before assuming the
# definition has an accidental loop. Generous, but bounded.
_MAX_AUTO_HOPS = 50

# The step kinds a human acts on. Decision/terminal steps are never actioned by a
# human in either enforcement mode. (Parallel steps are human-actionable too, but
# per-BRANCH — handled on its own path, not via the generic single-assignee logic.)
_HUMAN_STEP_TYPES = {StepType.FORM, StepType.APPROVAL, StepType.SIGNATURE}

# Reserved instance.context key holding per-step, per-branch vote state:
#   context["_branches"][<step_id>][<branch_id>] = {"actor", "decision", "at"}
# Generic on purpose — future fan-out / ordered-signing blocks reuse it.
_BRANCHES_KEY = "_branches"

# V2 token state (Phase 2). Only present when the definition contains explicit
# split/join gateways — legacy single-token flows never gain these keys, so
# their persisted state is byte-for-byte unchanged.
#   _tokens : [{"id": str, "step": str, "groups": [[group_id, expected], ...]}]
#             the active tokens parked at steps; "groups" is the nesting stack
#             of splits this token was born from (innermost last).
#   _joins  : {join_step_id: {group_id: arrived_count}} — arrivals per join.
#   _tok_seq: monotonically increasing int for deterministic token/group ids.
_TOKENS_KEY = "_tokens"
_JOINS_KEY = "_joins"
_SEQ_KEY = "_tok_seq"

# V2 task reassignment (Phase 3): context["_task_overrides"]["<step>:<slot>"]
# holds the user id a work item was reassigned to. When present it REPLACES the
# definition's assignee for that one step/slot in strict mode (the work moved;
# the original assignee is no longer responsible). Engine-owned: client
# payloads can never write it (reserved underscore prefix).
_OVERRIDES_KEY = "_task_overrides"

# Context keys starting with this prefix belong to the ENGINE (e.g. _branches —
# the vote/slot ledger). Client payloads may NEVER write them: a payload that
# could set "_branches" would let an actor forge votes; one that could set a
# routing variable or a context-assignee key not declared on the current step
# could steer the flow or make themselves a later assignee. perform()/decide
# therefore WHITELIST payload keys (see _sanitize_payload).
_RESERVED_PREFIX = "_"

# Synthetic transition token the runner sends when the owner ANSWERS a parked
# decision step. The engine ignores its literal value: it merges the answer
# (payload) into context and routes via the normal _next_auto, so the decision is
# the state machine's job as always — the UI only supplies the variable value.
DECIDE_TOKEN = "__decide__"


@dataclass
class StepResult:
    """The outcome of entering / advancing to a step."""

    step_id: str
    step_type: StepType
    is_terminal: bool
    context: dict[str, Any]
    visited: list[str] = field(default_factory=list)  # auto-hops taken to get here
    # For a parallel-branch vote: {"branch_id", "decision", "actor", "at"} so the
    # service can write a precise audit row. None for ordinary sequential moves.
    vote: Optional[dict[str, Any]] = None
    # Branch ids of NOTIFY recipients delivered on ENTERING a fan-out step, so the
    # service can emit one "notified" audit row each. Empty for everything else.
    notified: list[str] = field(default_factory=list)


class WorkflowEngine:
    def __init__(self, body: WorkflowDefinitionBody, enforce_roles: bool = True):
        self.body = body
        self._steps: dict[str, Step] = {s.id: s for s in body.steps}
        # Strict per-assignee authorization is the PERMANENT product behavior: the
        # service ALWAYS constructs the engine with enforce_roles=True and there is
        # no config switch to relax it. `enforce_roles=False` is a TEST-ONLY seam so
        # pure-engine unit tests can drive transitions without building a full role
        # context — it is never reachable from the running application.
        self.enforce_roles = enforce_roles
        # Gateway (token) mode activates ONLY when the definition declares
        # split/join steps. All other definitions run the legacy single-token
        # paths untouched.
        self._has_gateways = any(
            s.type in (StepType.SPLIT, StepType.JOIN) for s in body.steps)
        # Per-call scratch used while dispatching a tokenized action (engines
        # are built per request and used single-threaded).
        self._current_groups: list | None = None
        self._settled_tokens = False

    # -- lookups ---------------------------------------------------------------
    def step(self, step_id: str) -> Step:
        if step_id not in self._steps:
            raise EngineError(f"Unknown step '{step_id}'")
        return self._steps[step_id]

    def is_terminal(self, step_id: str) -> bool:
        return self.step(step_id).type == StepType.TERMINAL

    # -- authorization ---------------------------------------------------------
    # THE SINGLE AUTHORIZATION SWITCH.
    # Every availability/permission decision (available_actions + perform) routes
    # through here, so this is the one place that governs who may act on a step.
    # The application ALWAYS runs strict (enforce_roles=True): a user may act on a
    # step only when they match its assignee (role / user / context) or hold its
    # reassignment override. The enforce_roles==False branch is a TEST-ONLY seam
    # (unit tests of the pure state machine) — it is not reachable in the running
    # app. Decision / terminal steps are never human-actionable.
    @staticmethod
    def _reassigned_to(context: dict[str, Any], step_id: str,
                       slot_id: str = "") -> Optional[str]:
        """The user a step/slot work item was reassigned to, if any."""
        return (context.get(_OVERRIDES_KEY) or {}).get(f"{step_id}:{slot_id or ''}")

    def user_can_act(self, step: Step, user: CurrentUser,
                     context: dict[str, Any]) -> bool:
        """Decide whether `user` is allowed to act on `step`."""
        # Non-human steps (decision/terminal) and explicit system assignees are
        # never actioned by a human — unchanged in both modes.
        if step.type not in _HUMAN_STEP_TYPES:
            return False
        assignee = step.assignee
        if assignee is not None and assignee.type == AssigneeType.SYSTEM:
            return False

        # TEST-ONLY bypass (never set by the application — see __init__).
        if not self.enforce_roles:
            return True

        # ── STRICT (the only behavior in the running app) ────────────────────
        override = self._reassigned_to(context, step.id)
        if override is not None:
            return user.id == override  # the work moved; override replaces assignee
        if assignee is None:
            return False
        if assignee.type == AssigneeType.ROLE:
            return role_matches(assignee.value, user.roles)
        if assignee.type == AssigneeType.USER:
            return assignee.value == user.id
        if assignee.type == AssigneeType.CONTEXT:
            return context.get(assignee.value) == user.id
        return False

    # -- available actions -----------------------------------------------------
    def available_actions(self, step_id: str, context: dict[str, Any],
                          user: CurrentUser) -> list[AvailableAction]:
        """Human-firable actions for `user`. In gateway (token) mode this is the
        UNION over all active tokens' steps; otherwise the single current step."""
        tokens = context.get(_TOKENS_KEY) if self._has_gateways else None
        if tokens:
            seen: set[str] = set()
            out: list[AvailableAction] = []
            for tok in tokens:
                for a in self._step_available_actions(tok["step"], context, user):
                    if a.transition_id not in seen:
                        seen.add(a.transition_id)
                        out.append(a)
            return out
        return self._step_available_actions(step_id, context, user)

    def _step_available_actions(self, step_id: str, context: dict[str, Any],
                                user: CurrentUser) -> list[AvailableAction]:
        """Human-firable transitions out of `step_id` for `user`, given context.

        Excludes 'auto' transitions (those are the engine's job) and any whose
        condition currently evaluates false.
        """
        step = self.step(step_id)
        if step.type in (StepType.TERMINAL, StepType.SPLIT, StepType.JOIN):
            return []  # gateways are automatic; nobody acts on them
        if step.type == StepType.BROADCAST:
            return []  # pure delivery — nobody acts (it auto-advances on entry)
        if step.type == StepType.DECISION:
            # Only a PARKED (unanswered) decision is actionable — the owner answers
            # the question. A resolvable decision never parks here.
            return self._decision_available_actions(step, context, user)
        if step.type == StepType.PARALLEL:
            return self._parallel_available_actions(step, context, user)
        if step.type == StepType.ORDERED_SIGNING:
            return self._ordered_available_actions(step, context, user)
        if not self.user_can_act(step, user, context):
            return []

        actions: list[AvailableAction] = []
        for t in step.transitions:
            if t.action == "auto":
                continue
            if not evaluate_condition(t.condition, context):
                continue
            actions.append(
                AvailableAction(
                    transition_id=t.id,
                    action=t.action,
                    label=t.label,
                    to=t.to,
                    requires_comment=t.requires_comment,
                )
            )
        return actions

    # -- payload sanitization + form validation ---------------------------------
    # Client payloads are UNTRUSTED. Two layers, both raising EngineError:
    #   1. _sanitize_payload — whitelist: only keys explicitly declared on the
    #      CURRENT step may be written (config.fields; plus the two step-scoped
    #      signature-meta keys on signature steps; plus the decision variable(s)
    #      on a parked decision). Reserved (underscore-prefixed) keys are always
    #      rejected, so engine-owned state like _branches is unwritable.
    #   2. _validate_payload_values / _require_required_fields — declared type,
    #      allowed options, and (on form steps) required-ness are enforced
    #      server-side before the merge.
    def _declared_fields(self, step: Step) -> list[FormField]:
        """The step's declared config.fields, parsed leniently (a malformed field
        declaration is skipped rather than crashing the action)."""
        raw = (step.config or {}).get("fields") or []
        out: list[FormField] = []
        for f in raw:
            try:
                out.append(FormField.model_validate(f) if not isinstance(f, FormField) else f)
            except Exception:  # noqa: BLE001 — bad authoring, not a runtime fault
                continue
        return out

    def _allowed_payload_keys(self, step: Step) -> set[str]:
        allowed = {f.key for f in self._declared_fields(step)}
        if step.type == StepType.SIGNATURE:
            # The generic signature step records who/when via these two
            # step-scoped keys (runner steps/index.tsx).
            allowed |= {f"{step.id}_signed_by", f"{step.id}_signed_at"}
        return allowed

    def _sanitize_payload(self, step: Step, payload: dict[str, Any] | None,
                          extra_allowed: Optional[set[str]] = None) -> dict[str, Any]:
        """Return a copy of `payload` containing only keys this step may write.
        Raises EngineError on any reserved or undeclared key (loud > silent)."""
        if not payload:
            return {}
        for key in payload:
            if key.startswith(_RESERVED_PREFIX):
                raise EngineError(
                    f"Payload key '{key}' is reserved for the engine and cannot be set")
        allowed = self._allowed_payload_keys(step) | (extra_allowed or set())
        unknown = sorted(k for k in payload if k not in allowed)
        if unknown:
            raise EngineError(
                f"Payload keys not declared on step '{step.id}': {', '.join(unknown)}")
        return dict(payload)

    @staticmethod
    def _is_unset(value: Any) -> bool:
        """'' and None mean "left blank" (the runner sends '' for empty inputs)."""
        return value is None or value == ""

    def _validate_payload_values(self, step: Step, payload: dict[str, Any]) -> None:
        """Type/options checks for provided values against the declared fields.
        Blank values are skipped here — required-ness is checked separately on
        the merged context (so a value kept from a prior round still counts)."""
        fields = {f.key: f for f in self._declared_fields(step)}
        for key, value in payload.items():
            f = fields.get(key)
            if f is None or self._is_unset(value):
                continue
            if f.type == FieldType.NUMBER:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise EngineError(f"Field '{key}' must be a number")
            elif f.type == FieldType.BOOLEAN:
                if not isinstance(value, bool):
                    raise EngineError(f"Field '{key}' must be true or false")
            elif f.type == FieldType.DATE:
                try:
                    date.fromisoformat(str(value)[:10])
                except (ValueError, TypeError):
                    raise EngineError(f"Field '{key}' must be an ISO date (YYYY-MM-DD)")
            elif f.type == FieldType.SELECT:
                if not isinstance(value, str):
                    raise EngineError(f"Field '{key}' must be a string option")
                if f.options and value not in f.options:
                    raise EngineError(f"Field '{key}' must be one of: {', '.join(f.options)}")
            else:  # TEXT
                if not isinstance(value, str):
                    raise EngineError(f"Field '{key}' must be text")

    def _require_required_fields(self, step: Step, merged_context: dict[str, Any]) -> None:
        """On FORM steps every required declared field must be present (in the
        payload or already in context) before the step may be left."""
        if step.type != StepType.FORM:
            return
        for f in self._declared_fields(step):
            if f.required and self._is_unset(merged_context.get(f.key)):
                raise EngineError(f"Required field '{f.key}' is missing")

    # -- performing an action --------------------------------------------------
    def _find_transition(self, step: Step, transition_id: str) -> Transition:
        for t in step.transitions:
            if t.id == transition_id:
                return t
        raise EngineError(f"Transition '{transition_id}' not found on step '{step.id}'")

    def perform(self, current_step_id: str, transition_id: str,
                context: dict[str, Any], user: CurrentUser,
                payload: dict[str, Any] | None = None,
                comment: str | None = None,
                trusted_payload: bool = False) -> StepResult:
        """Validate and execute a human action, then settle any auto branches.

        Returns the resulting StepResult. Raises EngineError on any illegal move.
        Note: `context` is updated with `payload` (so forms persist their data).

        ``trusted_payload`` is for INTERNAL service-to-service callers only
        (e.g. the unified review/signing services writing bookkeeping keys like
        "reviewer"). It skips the declared-keys whitelist; reserved
        (underscore-prefixed) keys are still always rejected. The HTTP router
        must NEVER set it — client payloads stay fully sanitized.

        Gateway (token) mode: the action is routed to whichever active token's
        step accepts this transition; all other tokens stay parked.
        """
        if self._has_gateways and context.get(_TOKENS_KEY):
            return self._perform_tokenized(transition_id, context, user,
                                           payload, comment, trusted_payload)
        return self._perform_single(current_step_id, transition_id, context, user,
                                    payload, comment, trusted_payload)

    def _perform_single(self, current_step_id: str, transition_id: str,
                        context: dict[str, Any], user: CurrentUser,
                        payload: dict[str, Any] | None = None,
                        comment: str | None = None,
                        trusted_payload: bool = False) -> StepResult:
        step = self.step(current_step_id)
        if step.type == StepType.TERMINAL:
            raise EngineError("Cannot act on a terminal step")
        if step.type == StepType.BROADCAST:
            # Broadcast steps auto-advance on entry and never park, so an instance
            # is never sitting on one to act against.
            raise EngineError("Broadcast steps require no action; they auto-advance")

        # A decision step is answered by the owner: the payload carries the chosen
        # variable value; the engine routes on it (no ordinary transition fired).
        if step.type == StepType.DECISION:
            return self._perform_decision(step, transition_id, context, user, payload, comment)
        # Parallel steps take per-branch votes, not ordinary transitions.
        if step.type == StepType.PARALLEL:
            return self._perform_parallel_vote(step, transition_id, context, user, comment)
        # Ordered signing takes a per-slot sign/decline against the current signer.
        if step.type == StepType.ORDERED_SIGNING:
            return self._perform_ordered_sign(step, transition_id, context, user, comment)

        transition = self._find_transition(step, transition_id)
        if transition.action == "auto":
            raise EngineError("Auto transitions cannot be triggered by a user")
        if not self.user_can_act(step, user, context):
            raise EngineError("You are not authorized to act on this step")
        if not evaluate_condition(transition.condition, context):
            raise EngineError("This action is not available under current conditions")
        if transition.requires_comment and not (comment and comment.strip()):
            raise EngineError("A comment is required for this action")

        if trusted_payload:
            # Internal caller: whitelist waived, engine-owned keys still walled off.
            clean = dict(payload or {})
            for key in clean:
                if key.startswith(_RESERVED_PREFIX):
                    raise EngineError(
                        f"Payload key '{key}' is reserved for the engine and cannot be set")
        else:
            clean = self._sanitize_payload(step, payload)
            self._validate_payload_values(step, clean)

        new_context = dict(context)
        if clean:
            new_context.update(clean)
        self._require_required_fields(step, new_context)

        return self._settle(transition.to, new_context)

    def start(self, context: dict[str, Any]) -> StepResult:
        """Enter the start step and settle any immediate auto branches."""
        return self._settle(self.body.start_step, dict(context))

    def _settle(self, step_id: str, context: dict[str, Any]) -> StepResult:
        """Settle dispatcher. Legacy (no gateways): single-token walk, byte-for-
        byte the original behavior. Gateway mode: token settling (splits spawn,
        joins collect, policies fire)."""
        if self._has_gateways:
            return self._settle_tokens(step_id, context, groups=self._current_groups)
        return self._settle_single(step_id, context)

    def _settle_single(self, step_id: str, context: dict[str, Any]) -> StepResult:
        """Enter `step_id`; while it is a decision/auto OR a broadcast step, keep
        advancing. Stops at a human step, a parallel/ordered step, or terminal.

        `notified` accumulates across the whole settle so any broadcast (or
        fan-out entry) passed on the way contributes its deliveries to the result.
        """
        visited: list[str] = []
        notified: list[str] = []
        current = step_id

        for _ in range(_MAX_AUTO_HOPS):
            step = self.step(current)
            visited.append(current)

            # Round-based steps (parallel / fan-out / ordered_signing / broadcast)
            # REOPEN on every (re-)entry: clear this step's working branch/slot
            # state so a reworked/sent-back step starts a fresh round with all
            # branches or signer slots open again. Only this step is touched —
            # other steps' history is untouched — and the AUDIT log is separate
            # from _branches, so prior rounds remain in history. No-op on first
            # entry (nothing recorded yet), so existing flows are unchanged.
            if step.type in (StepType.PARALLEL, StepType.ORDERED_SIGNING, StepType.BROADCAST):
                context = self._reset_branch_state(context, current)

            if step.type == StepType.TERMINAL:
                return StepResult(current, step.type, True, context, visited,
                                  notified=notified)

            # Broadcast: record deliveries to all recipients, then auto-advance
            # through the single broadcast_done transition. The hop counter (this
            # loop) is the loop guard.
            if step.type == StepType.BROADCAST:
                context, new_ids = self._record_notify_ids(
                    current, self._broadcast_recipient_ids(step), context)
                notified.extend(new_ids)
                transition = self._transition_by_action(step, "broadcast_done")
                if transition is None:
                    raise EngineError(
                        f"Broadcast step '{current}' has no 'broadcast_done' transition")
                current = transition.to
                continue

            # A DECISION whose variable isn't set yet WAITS for the owner to answer
            # instead of silently taking the default branch (which made the alternate
            # branch unreachable from the UI). Park here so the runner can render the
            # question; once answered (perform → _perform_decision sets the variable),
            # the engine routes normally. If the variable WAS set earlier (collected at
            # draft), this is False and the decision auto-resolves exactly as before.
            if step.type == StepType.DECISION and self._decision_pending(step, context):
                return StepResult(current, step.type, False, context, visited,
                                  notified=notified)

            auto = self._next_auto(step, context)
            if auto is None:
                # A human step (form/approval/signature), a parallel/fan-out step,
                # an ordered-signing step, or a decision with no matching branch —
                # we settle here.
                if step.type == StepType.PARALLEL:
                    # On ENTERING a fan-out step, record notify-recipient
                    # deliveries so they're traceable and never re-emitted.
                    context, new_ids = self._record_notify_deliveries(step, context)
                    notified.extend(new_ids)
                return StepResult(current, step.type, False, context, visited,
                                  notified=notified)
            current = auto.to

        raise EngineError(
            f"Auto-transition loop detected starting at '{step_id}' "
            f"(visited {len(visited)} steps). Check your decision branches."
        )

    def _next_auto(self, step: Step, context: dict[str, Any]) -> Optional[Transition]:
        """First auto transition whose condition passes. Unconditional autos win
        only if no conditional auto matched earlier in the list, so order your
        decision branches specific-first, default-last."""
        fallback: Optional[Transition] = None
        for t in step.transitions:
            if t.action != "auto":
                continue
            if t.condition is None:
                fallback = fallback or t
                continue
            if evaluate_condition(t.condition, context):
                return t
        return fallback

    # ======================================================================
    # TOKENS + GATEWAYS (V2 Phase 2)
    # ----------------------------------------------------------------------
    # When a definition declares split/join steps, the instance's execution
    # state is a SET of tokens (context["_tokens"]), each walking its own full
    # sequence of ordinary steps. A split consumes its token and spawns one
    # child token per condition-passing outgoing transition; a join consumes
    # arriving tokens and fires its policy (the same evaluate_join_policy that
    # powers parallel quorum) once enough have arrived — cancelling straggler
    # siblings for n_of_m/percent. A terminal reached by ANY token terminates
    # the whole instance (terminate-all semantics). The legacy composite steps
    # (parallel / ordered_signing / broadcast) work unchanged inside a token's
    # branch — they are macros over the same join-policy machinery.
    # ======================================================================
    @staticmethod
    def _next_seq(context: dict[str, Any]) -> tuple[dict[str, Any], int]:
        n = int(context.get(_SEQ_KEY) or 0) + 1
        new_context = dict(context)
        new_context[_SEQ_KEY] = n
        return new_context, n

    @staticmethod
    def _in_group(tok: dict[str, Any], gid: str) -> bool:
        return any(g[0] == gid for g in (tok.get("groups") or []))

    def _join_policy(self, step: Step) -> JoinPolicy:
        try:
            return JoinPolicy.model_validate((step.config or {}).get("join") or {})
        except EngineError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"Invalid join config on step '{step.id}': {exc}") from exc

    def _settle_tokens(self, step_id: str, context: dict[str, Any],
                       groups: list | None = None) -> StepResult:
        """Gateway-mode settle: drop one entry token at `step_id` (inheriting the
        acting token's group stack) and run the token world to rest."""
        self._settled_tokens = True
        context, n = self._next_seq(context)
        entry = {"id": f"t{n}", "step": step_id, "groups": list(groups or [])}
        parked, context, visited, notified, terminal = self._settle_many([entry], context)
        if terminal is not None:
            return StepResult(terminal, StepType.TERMINAL, True, context, visited,
                              notified=notified)
        if not parked:
            raise EngineError(
                "All tokens were consumed without reaching a terminal — "
                "check the join policies of this workflow")
        context = dict(context)
        context[_TOKENS_KEY] = parked
        first = self.step(parked[0]["step"])
        return StepResult(first.id, first.type, False, context, visited,
                          notified=notified)

    def _settle_many(self, entry_tokens: list[dict],
                     context: dict[str, Any]):
        """Settle `entry_tokens` (plus any tokens already parked in context)
        until every live token rests at a human/macro step, is consumed by a
        join, or a terminal terminates the instance.

        Returns (parked_tokens, context, visited, notified, terminal_step)."""
        from collections import deque

        context = dict(context)
        parked: list[dict] = [dict(t) for t in (context.pop(_TOKENS_KEY, None) or [])]
        work = deque(dict(t) for t in entry_tokens)
        visited: list[str] = []
        notified: list[str] = []
        hops = 0

        while work:
            tok = work.popleft()
            current = tok["step"]
            settling = True
            while settling:
                hops += 1
                if hops > _MAX_AUTO_HOPS * 4:
                    raise EngineError(
                        "Auto-transition loop detected while settling tokens "
                        f"(visited {len(visited)} steps). Check splits/decisions.")
                step = self.step(current)
                visited.append(current)

                if step.type in (StepType.PARALLEL, StepType.ORDERED_SIGNING,
                                 StepType.BROADCAST):
                    context = self._reset_branch_state(context, current)

                if step.type == StepType.TERMINAL:
                    # Terminate-all: drop every other token, instance completes.
                    context.pop(_TOKENS_KEY, None)
                    context.pop(_JOINS_KEY, None)
                    return [], context, visited, notified, current

                if step.type == StepType.BROADCAST:
                    context, new_ids = self._record_notify_ids(
                        current, self._broadcast_recipient_ids(step), context)
                    notified.extend(new_ids)
                    transition = self._transition_by_action(step, "broadcast_done")
                    if transition is None:
                        raise EngineError(
                            f"Broadcast step '{current}' has no 'broadcast_done' transition")
                    current = transition.to
                    continue

                if step.type == StepType.SPLIT:
                    outs = [t for t in step.transitions
                            if evaluate_condition(t.condition, context)]
                    if not outs:
                        raise EngineError(
                            f"Split '{current}' has no branch whose condition passes")
                    context, gnum = self._next_seq(context)
                    gid = f"{current}#{gnum}"
                    child_groups = list(tok.get("groups") or []) + [[gid, len(outs)]]
                    for t in outs:
                        context, tnum = self._next_seq(context)
                        work.append({"id": f"t{tnum}", "step": t.to,
                                     "groups": child_groups})
                    settling = False  # parent token consumed by the split
                    continue

                if step.type == StepType.JOIN:
                    groups = list(tok.get("groups") or [])
                    if groups:
                        gid, expected = groups[-1][0], int(groups[-1][1])
                    else:
                        gid, expected = f"solo:{tok['id']}", 1
                    joins = {k: dict(v) for k, v in (context.get(_JOINS_KEY) or {}).items()}
                    slot = dict(joins.get(current, {}))
                    arrived = int(slot.get(gid, 0)) + 1
                    slot[gid] = arrived
                    joins[current] = slot
                    context[_JOINS_KEY] = joins

                    pol = self._join_policy(step)
                    outcome = evaluate_join_policy(
                        pol.mode, pol.value, "count",
                        total=expected, ok=arrived, fail=0,
                        open_count=expected - arrived)
                    if outcome == "met":
                        # Cancel straggler siblings (n_of_m / percent) and clear
                        # this group's arrival counter.
                        parked = [p for p in parked if not self._in_group(p, gid)]
                        work = deque(w for w in work if not self._in_group(w, gid))
                        slot.pop(gid, None)
                        joins[current] = slot
                        context[_JOINS_KEY] = joins
                        transition = self._transition_by_action(step, "join_met")
                        if transition is None:
                            raise EngineError(
                                f"Join step '{current}' has no 'join_met' transition")
                        tok = {"id": tok["id"], "step": transition.to,
                               "groups": groups[:-1]}
                        current = transition.to
                        continue
                    settling = False  # token consumed into the join; await siblings
                    continue

                if step.type == StepType.DECISION and self._decision_pending(step, context):
                    tok = dict(tok)
                    tok["step"] = current
                    parked.append(tok)
                    settling = False
                    continue

                auto = self._next_auto(step, context)
                if auto is None:
                    if step.type == StepType.PARALLEL:
                        context, new_ids = self._record_notify_deliveries(step, context)
                        notified.extend(new_ids)
                    tok = dict(tok)
                    tok["step"] = current
                    parked.append(tok)
                    settling = False
                    continue
                current = auto.to

        return parked, context, visited, notified, None

    def _token_for_transition(self, tokens: list[dict], transition_id: str,
                              context: dict[str, Any]) -> Optional[dict]:
        """Which active token's step accepts this transition. Vote tokens
        ('<branch>:<verb>', '<slot>:<verb>') match their macro step; DECIDE_TOKEN
        matches the first parked, unanswered decision; ordinary ids match the
        step's own transition list."""
        for tok in tokens:
            step = self.step(tok["step"])
            if step.type == StepType.PARALLEL:
                bid, sep, _verb = transition_id.rpartition(":")
                if sep and self._parallel_config(step).branch(bid) is not None:
                    return tok
            elif step.type == StepType.ORDERED_SIGNING:
                sid, sep, _verb = transition_id.rpartition(":")
                if sep and self._ordered_config(step).signer(sid) is not None:
                    return tok
            elif step.type == StepType.DECISION:
                if transition_id == DECIDE_TOKEN and self._decision_pending(step, context):
                    return tok
            else:
                if any(t.id == transition_id for t in step.transitions):
                    return tok
        return None

    def _perform_tokenized(self, transition_id: str, context: dict[str, Any],
                           user: CurrentUser, payload: dict[str, Any] | None,
                           comment: str | None, trusted_payload: bool) -> StepResult:
        tokens = [dict(t) for t in (context.get(_TOKENS_KEY) or [])]
        tok = self._token_for_transition(tokens, transition_id, context)
        if tok is None:
            raise EngineError(
                f"Transition '{transition_id}' is not available on any active step")

        # The acting token leaves the parked set; whatever its action settles
        # into is computed by _settle_tokens (which re-reads the parked set from
        # context and merges/cancels as joins fire).
        remaining = [t for t in tokens if t["id"] != tok["id"]]
        ctx = dict(context)
        ctx[_TOKENS_KEY] = remaining

        self._current_groups = list(tok.get("groups") or [])
        self._settled_tokens = False
        try:
            result = self._perform_single(tok["step"], transition_id, ctx, user,
                                          payload, comment, trusted_payload)
        finally:
            self._current_groups = None

        if not self._settled_tokens and not result.is_terminal:
            # The step stayed parked (open parallel vote / mid ordered-signing /
            # rejected nothing): put the acting token back where it was.
            new_context = dict(result.context)
            new_context[_TOKENS_KEY] = [t for t in (new_context.get(_TOKENS_KEY) or [])
                                        if t["id"] != tok["id"]] + [tok]
            return StepResult(result.step_id, result.step_type, False, new_context,
                              result.visited, vote=result.vote,
                              notified=result.notified)
        return result

    # ======================================================================
    # SYSTEM TRANSITIONS (V2 Phase 4) — timers and jobs advance the flow
    # without a human: fire a step's transition by ACTION name. No assignee
    # check, no payload. Token-aware: consumes the token parked at the step.
    # ======================================================================
    def parked_steps(self, current_step: Optional[str],
                     context: dict[str, Any]) -> list[str]:
        """The step ids the instance is currently parked on (all tokens)."""
        if current_step is None:
            return []
        if self._has_gateways and context.get(_TOKENS_KEY):
            return [t["step"] for t in context[_TOKENS_KEY]]
        return [current_step]

    def fire_system_transition(self, step_id: str, action: str,
                               context: dict[str, Any]) -> StepResult:
        step = self.step(step_id)
        transition = self._transition_by_action(step, action)
        if transition is None:
            raise EngineError(f"Step '{step_id}' has no '{action}' transition")
        if self._has_gateways and context.get(_TOKENS_KEY):
            tokens = [dict(t) for t in context[_TOKENS_KEY]]
            tok = next((t for t in tokens if t["step"] == step_id), None)
            if tok is None:
                raise EngineError(f"No active token parked at step '{step_id}'")
            ctx = dict(context)
            ctx[_TOKENS_KEY] = [t for t in tokens if t["id"] != tok["id"]]
            self._current_groups = list(tok.get("groups") or [])
            try:
                return self._settle(transition.to, ctx)
            finally:
                self._current_groups = None
        return self._settle(transition.to, dict(context))

    # ======================================================================
    # WORK UNITS (V2 Phase 3) — the open human work items implied by a state.
    # One per parked human step; one per OPEN parallel action branch; one for
    # the CURRENT ordered-signing slot; one per parked decision. Pure
    # derivation: the kernel diffs these between states to emit CreateTask /
    # CompleteTask / CancelTask commands, and the service materializes them as
    # workflow_tasks rows (the worklist read-model).
    # ======================================================================
    def work_units(self, current_step: Optional[str],
                   context: dict[str, Any]) -> list[dict[str, Any]]:
        if current_step is None:
            return []
        if self._has_gateways and context.get(_TOKENS_KEY):
            step_ids = [t["step"] for t in context[_TOKENS_KEY]]
        else:
            step_ids = [current_step]

        units: list[dict[str, Any]] = []
        for sid in step_ids:
            step = self.step(sid)
            if step.type in _HUMAN_STEP_TYPES:
                units.append(self._work_unit(step, None, step.name, step.assignee))
            elif step.type == StepType.DECISION and self._decision_pending(step, context):
                units.append(self._work_unit(step, None, step.name or "Decision",
                                             step.assignee))
            elif step.type == StepType.PARALLEL:
                cfg = self._parallel_config(step)
                voted = set(self._branch_votes(step, context))
                for b in cfg.branches:
                    if b.kind == "action" and b.id not in voted:
                        units.append(self._work_unit(
                            step, b.id, f"{step.name}: {b.name}", b.assignee))
            elif step.type == StepType.ORDERED_SIGNING:
                cfg = self._ordered_config(step)
                cur = self._current_signer(cfg, step, context)
                if cur is not None:
                    units.append(self._work_unit(
                        step, cur.id, f"{step.name}: {cur.name}", cur.assignee))
        return units

    @staticmethod
    def _work_unit(step: Step, slot: Optional[str], name: str,
                   assignee) -> dict[str, Any]:
        return {
            "step_id": step.id,
            "slot_id": slot or "",
            "name": name,
            "assignee_type": assignee.type.value if assignee else None,
            "assignee_value": assignee.value if assignee else None,
        }

    # ======================================================================
    # DECISION (ask-the-owner branch)
    # ----------------------------------------------------------------------
    # A decision step branches on a context variable. When that variable is not
    # set yet, the engine PARKS on the step (see _settle) so the runner can ask
    # the owner the question and route on the answer — rather than auto-taking the
    # default and leaving the other branch unreachable. Fully GENERAL: the
    # variable(s), the question phrasing, and the options all come from the step's
    # own definition (its transitions + the workflow context_schema). Nothing here
    # is CRO/IRB/budget-specific.
    # ======================================================================
    def _decision_fields(self, step: Step) -> set[str]:
        """The context variable(s) this decision branches on — the union of fields
        referenced by its CONDITIONAL auto transitions. Presence tests
        (exists/not_exists) are excluded: those branch on absence, so they must not
        make the decision wait for a value."""
        fields: set[str] = set()
        for t in step.transitions:
            if t.action == "auto" and t.condition is not None:
                fields |= referenced_fields(t.condition, exclude_presence_ops=True)
        return fields

    def _decision_pending(self, step: Step, context: dict[str, Any]) -> bool:
        """True when this decision can't be answered yet: it HAS conditional
        branches keyed on variable(s), and NONE of those variables is set in
        context. A pure pass-through decision (only an unconditional default) has no
        variable, so it is never pending and auto-resolves as before."""
        if step.type != StepType.DECISION:
            return False
        fields = self._decision_fields(step)
        if not fields:
            return False
        return all(_missing(context, f) for f in fields)

    def _decision_user_can_act(self, step: Step, user: CurrentUser,
                               context: dict[str, Any]) -> bool:
        """Who may ANSWER a parked decision. Open mode → any authenticated user
        (creator-owns is enforced at the module/service layer, like other steps).
        Strict mode → the step's own assignee (role/user/context) if one is set;
        with no assignee the engine can't resolve "creator", so it defers (False)
        and ownership is gated above the engine."""
        if not self.enforce_roles:
            return True
        override = self._reassigned_to(context, step.id)
        if override is not None:
            return user.id == override
        assignee = step.assignee
        if assignee is None or assignee.type == AssigneeType.SYSTEM:
            return False
        if assignee.type == AssigneeType.ROLE:
            return role_matches(assignee.value, user.roles)
        if assignee.type == AssigneeType.USER:
            return assignee.value == user.id
        if assignee.type == AssigneeType.CONTEXT:
            return context.get(assignee.value) == user.id
        return False

    def _decision_available_actions(self, step: Step, context: dict[str, Any],
                                    user: CurrentUser) -> list[AvailableAction]:
        """A parked, unanswered decision offers ONE synthetic 'decide' action to the
        decision-maker. The runner renders the real options (Yes/No, a value, …)
        from the definition; on submit it sends DECIDE_TOKEN + the chosen value as
        payload. An already-resolvable decision (variable set) offers nothing —
        the engine auto-resolves it and never parks here."""
        if not self._decision_pending(step, context):
            return []
        if not self._decision_user_can_act(step, user, context):
            return []
        return [AvailableAction(
            transition_id=DECIDE_TOKEN, action="decide",
            label=step.name or "Make decision", to="", requires_comment=False,
        )]

    def _perform_decision(self, step: Step, transition_id: str,
                          context: dict[str, Any], user: CurrentUser,
                          payload: dict[str, Any] | None,
                          comment: str | None) -> StepResult:
        """Record the owner's answer (payload sets the decision variable) and route.

        The engine does NOT trust a hand-picked branch: it merges the answer into
        context and re-runs _next_auto, so the SAME condition logic that runs for a
        pre-set variable decides the branch. This keeps the engine the single router
        and works for any operator (is_true/eq/gt/…) with zero per-variable code."""
        if not self._decision_user_can_act(step, user, context):
            raise EngineError("You are not authorized to decide this step")

        # The answer may only set the decision's OWN variable(s) — never reserved
        # keys, never unrelated context (no smuggling routing flags via DECIDE).
        clean = self._sanitize_payload(step, payload,
                                       extra_allowed=self._decision_fields(step))

        new_context = dict(context)
        if clean:
            new_context.update(clean)

        # The answer must actually resolve the decision. If the variable is still
        # unset after the merge, the owner didn't choose — reject rather than fall
        # through to a default (the very bug this feature fixes).
        if self._decision_pending(step, new_context):
            raise EngineError("Choose an answer for this decision before continuing")

        chosen = self._next_auto(step, new_context)
        if chosen is None:
            raise EngineError(
                f"The answer did not match any branch of decision '{step.id}'")

        result = self._settle(chosen.to, new_context)
        # Reuse the vote channel so the service writes a precise audit row
        # (action='decided', branch_id=<chosen transition>) alongside the payload.
        result.vote = {
            "branch_id": chosen.id, "decision": "decided",
            "actor": user.id, "at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    # ======================================================================
    # PARALLEL REVIEW (fan-out)
    # ----------------------------------------------------------------------
    # A parallel step opens several branches at once and is its own implicit
    # JOIN: current_step parks on it (no auto transitions leave it, so _settle
    # stops here) until QUORUM resolves, then we settle PAST it along the
    # "quorum_met" / "quorum_failed" transition. All branch state lives in
    # context[_branches][step_id] — pure JSON, no DB.
    # ======================================================================
    def _parallel_config(self, step: Step) -> ParallelConfig:
        try:
            return ParallelConfig.model_validate(step.config)
        except Exception as exc:  # noqa: BLE001 — surface as an engine error
            raise EngineError(f"Invalid parallel config on step '{step.id}': {exc}") from exc

    def _branch_user_can_act(self, branch: BranchSpec, user: CurrentUser,
                             context: dict[str, Any],
                             step_id: str = "") -> bool:
        """Per-branch authorization. Mirrors user_can_act's open/strict switch:
        open mode lets any authenticated user act on any branch; strict mode
        matches the branch's own assignee (role/user/context) — unless the work
        item was reassigned, in which case the override user replaces it."""
        if not self.enforce_roles:
            return True
        override = self._reassigned_to(context, step_id, branch.id)
        if override is not None:
            return user.id == override
        assignee = branch.assignee
        if assignee is None or assignee.type == AssigneeType.SYSTEM:
            return False
        if assignee.type == AssigneeType.ROLE:
            return role_matches(assignee.value, user.roles)
        if assignee.type == AssigneeType.USER:
            return assignee.value == user.id
        if assignee.type == AssigneeType.CONTEXT:
            return context.get(assignee.value) == user.id
        return False

    def _branch_votes(self, step: Step, context: dict[str, Any]) -> dict[str, Any]:
        """Read-only view of recorded votes for this step: {branch_id: {...}}."""
        return dict((context.get(_BRANCHES_KEY) or {}).get(step.id, {}))

    def _parallel_available_actions(self, step: Step, context: dict[str, Any],
                                    user: CurrentUser) -> list[AvailableAction]:
        """Open ACTION branches the user may act on, each as approve + reject.
        NOTIFY branches are never actionable. A branch already voted is closed
        (omitted) — no double-voting."""
        cfg = self._parallel_config(step)
        voted = set(self._branch_votes(step, context).keys())
        actions: list[AvailableAction] = []
        for b in cfg.branches:
            if b.kind != "action":
                continue  # notify recipients never appear as actions
            if b.id in voted:
                continue  # closed: already decided
            if not self._branch_user_can_act(b, user, context, step_id=step.id):
                continue
            # Vote token is "<branch_id>:<verb>" so it rides the normal
            # perform(transition_id=...) channel with no route/schema change.
            actions.append(AvailableAction(
                transition_id=f"{b.id}:{b.action_approve}", action=b.action_approve,
                label=f"{b.name}: {b.action_approve}", to="", requires_comment=False,
            ))
            actions.append(AvailableAction(
                transition_id=f"{b.id}:{b.action_reject}", action=b.action_reject,
                label=f"{b.name}: {b.action_reject}", to="", requires_comment=False,
            ))
        return actions

    def _perform_parallel_vote(self, step: Step, transition_id: str,
                               context: dict[str, Any], user: CurrentUser,
                               comment: str | None) -> StepResult:
        """Record one branch vote, then re-evaluate quorum and settle if resolved."""
        cfg = self._parallel_config(step)

        # Parse "<branch_id>:<verb>" and map the verb to approve/reject.
        branch_id, sep, verb = transition_id.rpartition(":")
        if not sep or not branch_id:
            raise EngineError(f"Invalid parallel vote token '{transition_id}'")
        branch = cfg.branch(branch_id)
        if branch is None:
            raise EngineError(f"Unknown branch '{branch_id}' on step '{step.id}'")
        if branch.kind != "action":
            raise EngineError(f"Branch '{branch_id}' is notify-only and cannot be voted")
        if verb == branch.action_approve:
            decision = "approve"
        elif verb == branch.action_reject:
            decision = "reject"
        else:
            raise EngineError(f"Invalid action '{verb}' for branch '{branch_id}'")

        if not self._branch_user_can_act(branch, user, context, step_id=step.id):
            raise EngineError("You are not authorized to act on this branch")

        votes = self._branch_votes(step, context)
        if branch_id in votes:
            raise EngineError(f"Branch '{branch_id}' has already been voted")

        # Record the vote into a fresh copy of the branch state (shared helper —
        # reused by ordered signing too).
        vote = {"actor": user.id, "decision": decision,
                "at": datetime.now(timezone.utc).isoformat()}
        new_context = self._record_branch_decision(context, step.id, branch_id, vote)
        step_votes = new_context[_BRANCHES_KEY][step.id]

        vote_record = {"branch_id": branch_id, **vote}

        outcome = self._evaluate_quorum(cfg, step_votes)
        if outcome == "open":
            # Stay parked on the parallel step; more votes needed.
            return StepResult(step.id, StepType.PARALLEL, False, new_context,
                              [step.id], vote=vote_record)

        action = "quorum_met" if outcome == "met" else "quorum_failed"
        transition = self._transition_by_action(step, action)
        if transition is None:
            raise EngineError(f"Parallel step '{step.id}' has no '{action}' transition")
        result = self._settle(transition.to, new_context)
        result.vote = vote_record
        return result

    def _transition_by_action(self, step: Step, action: str) -> Optional[Transition]:
        for t in step.transitions:
            if t.action == action:
                return t
        return None

    def _record_notify_ids(self, step_id: str, recipient_ids: list[str],
                           context: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Shared notify-delivery writer (reused by fan-out NOTIFY branches and by
        broadcast recipients). Marks each id as delivered in
        context[_branches][step_id] (decision='notified', actor=None) and returns
        (new_context, newly_notified_ids). No-op when there's nothing new to record
        — so already-delivered recipients are never double-counted."""
        if not recipient_ids:
            return context, []
        existing = (context.get(_BRANCHES_KEY) or {}).get(step_id, {})
        new_ids = [rid for rid in recipient_ids if rid not in existing]
        if not new_ids:
            return context, []

        now = datetime.now(timezone.utc).isoformat()
        new_context = dict(context)
        all_branches = {k: dict(v) for k, v in (context.get(_BRANCHES_KEY) or {}).items()}
        slot = dict(all_branches.get(step_id, {}))
        for rid in new_ids:
            slot[rid] = {"actor": None, "decision": "notified", "at": now}
        all_branches[step_id] = slot
        new_context[_BRANCHES_KEY] = all_branches
        return new_context, new_ids

    def _record_notify_deliveries(self, step: Step,
                                  context: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Fan-out (block 2): record this parallel step's NOTIFY branches as
        delivered. Thin wrapper over the shared writer — preserves block-2 output."""
        cfg = self._parallel_config(step)
        notify_ids = [b.id for b in cfg.branches if b.kind == "notify"]
        return self._record_notify_ids(step.id, notify_ids, context)

    def _broadcast_config(self, step: Step) -> BroadcastConfig:
        try:
            return BroadcastConfig.model_validate(step.config)
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"Invalid broadcast config on step '{step.id}': {exc}") from exc

    def _broadcast_recipient_ids(self, step: Step) -> list[str]:
        return [r.id for r in self._broadcast_config(step).recipients]

    def _evaluate_quorum(self, cfg: ParallelConfig,
                         step_votes: dict[str, Any]) -> str:
        """Decide the parallel step's state: 'met' | 'failed' | 'open'.

        The parallel step is a compiled MACRO over the shared join policy:
        each action branch is a (derived) token, a vote is that token arriving
        at the macro's implicit join with an ok/fail outcome, and the quorum is
        the join policy (evaluate_join_policy). Notify recipients (recorded with
        decision='notified') never gate progress.
        """
        action_ids = {b.id for b in cfg.branches if b.kind == "action"}
        total = len(action_ids)
        action_votes = [v for bid, v in step_votes.items() if bid in action_ids]
        approvals = sum(1 for v in action_votes if v.get("decision") == "approve")
        rejects = sum(1 for v in action_votes if v.get("decision") == "reject")
        open_branches = total - len(action_votes)
        return evaluate_join_policy(cfg.quorum.mode, cfg.quorum.value, cfg.on_reject,
                                    total, approvals, rejects, open_branches)

    # ----------------------------------------------------------------------
    # Shared branch-state writer (used by parallel votes AND ordered signing).
    # Records one slot decision into a fresh copy of context[_branches][step_id]
    # without mutating the caller's context.
    # ----------------------------------------------------------------------
    def _reset_branch_state(self, context: dict[str, Any], step_id: str) -> dict[str, Any]:
        """Clear ONE step's working branch/slot state (used on entry so a
        re-entered round-based step reopens). Returns the SAME context object when
        there's nothing recorded for this step — so first entry is a true no-op and
        forward-only flows are byte-for-byte unchanged. Never touches other steps;
        never touches the audit log (which lives outside _branches)."""
        branches = context.get(_BRANCHES_KEY)
        if not branches or step_id not in branches:
            return context
        new_context = dict(context)
        new_context[_BRANCHES_KEY] = {k: v for k, v in branches.items() if k != step_id}
        return new_context

    def _record_branch_decision(self, context: dict[str, Any], step_id: str,
                                slot_id: str, record: dict[str, Any]) -> dict[str, Any]:
        new_context = dict(context)
        all_branches = {k: dict(v) for k, v in (context.get(_BRANCHES_KEY) or {}).items()}
        slot_votes = dict(all_branches.get(step_id, {}))
        slot_votes[slot_id] = record
        all_branches[step_id] = slot_votes
        new_context[_BRANCHES_KEY] = all_branches
        return new_context

    # ======================================================================
    # ORDERED SIGNING
    # ----------------------------------------------------------------------
    # An ordered_signing step holds an ORDERED signer list. Only the current
    # (first not-yet-signed) signer's slot is open; the next unlocks after the
    # current signs. Strict order, no skipping. Reuses _branches for slot state
    # and StepResult.vote for the audit row. Like parallel, the step is its own
    # join: current_step parks here until the last signer signs (-> "all_signed")
    # or a signer declines (-> "signing_declined").
    # ======================================================================
    def _ordered_config(self, step: Step) -> OrderedSigningConfig:
        try:
            return OrderedSigningConfig.model_validate(step.config)
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"Invalid ordered_signing config on step '{step.id}': {exc}") from exc

    def _slot_user_can_act(self, slot: SignerSlot, user: CurrentUser,
                           context: dict[str, Any],
                           step_id: str = "") -> bool:
        """Per-signer authorization — same open/strict switch as branches."""
        if not self.enforce_roles:
            return True
        override = self._reassigned_to(context, step_id, slot.id)
        if override is not None:
            return user.id == override
        assignee = slot.assignee
        if assignee is None or assignee.type == AssigneeType.SYSTEM:
            return False
        if assignee.type == AssigneeType.ROLE:
            return role_matches(assignee.value, user.roles)
        if assignee.type == AssigneeType.USER:
            return assignee.value == user.id
        if assignee.type == AssigneeType.CONTEXT:
            return context.get(assignee.value) == user.id
        return False

    def _current_signer(self, cfg: OrderedSigningConfig, step: Step,
                        context: dict[str, Any]) -> Optional[SignerSlot]:
        """First signer (in order) with no recorded decision yet, or None when
        all have signed."""
        recorded = self._branch_votes(step, context)
        for s in cfg.signers:
            if s.id not in recorded:
                return s
        return None

    def _ordered_available_actions(self, step: Step, context: dict[str, Any],
                                   user: CurrentUser) -> list[AvailableAction]:
        """Only the CURRENT signer's slot — never a later signer."""
        cfg = self._ordered_config(step)
        current = self._current_signer(cfg, step, context)
        if current is None:
            return []
        if not self._slot_user_can_act(current, user, context, step_id=step.id):
            return []
        actions = [AvailableAction(
            transition_id=f"{current.id}:sign", action="sign",
            label=f"{current.name}: sign", to="", requires_comment=False,
        )]
        # Offer decline only if the step defines a decline path. A decline carries the
        # transition's requires_comment flag through to the UI so a step authored with
        # requires_comment=True forces the signer to give a reason (NEED 2).
        decline_t = self._transition_by_action(step, "signing_declined")
        if decline_t is not None:
            actions.append(AvailableAction(
                transition_id=f"{current.id}:decline", action="decline",
                label=f"{current.name}: decline", to="",
                requires_comment=bool(decline_t.requires_comment),
            ))
        return actions

    def _perform_ordered_sign(self, step: Step, transition_id: str,
                              context: dict[str, Any], user: CurrentUser,
                              comment: str | None) -> StepResult:
        """Sign/decline the CURRENT slot. Out-of-order or repeat slots raise."""
        cfg = self._ordered_config(step)

        slot_id, sep, verb = transition_id.rpartition(":")
        if not sep or not slot_id:
            raise EngineError(f"Invalid ordered-signing token '{transition_id}'")
        slot = cfg.signer(slot_id)
        if slot is None:
            raise EngineError(f"Unknown signer '{slot_id}' on step '{step.id}'")
        if verb not in ("sign", "decline"):
            raise EngineError(f"Invalid action '{verb}' for signer '{slot_id}'")

        recorded = self._branch_votes(step, context)
        if slot_id in recorded:
            raise EngineError(f"Signer '{slot_id}' has already {recorded[slot_id].get('decision', 'acted')}")
        current = self._current_signer(cfg, step, context)
        if current is None or slot_id != current.id:
            expected = current.id if current else "(none — all signed)"
            raise EngineError(
                f"Out-of-order signing: it is '{expected}'s turn, not '{slot_id}'"
            )
        if not self._slot_user_can_act(slot, user, context, step_id=step.id):
            raise EngineError("You are not authorized to sign this slot")

        decision = "signed" if verb == "sign" else "declined"

        if decision == "declined":
            transition = self._transition_by_action(step, "signing_declined")
            if transition is None:
                raise EngineError(
                    f"Signer '{slot_id}' declined but step '{step.id}' has no "
                    f"'signing_declined' transition"
                )
            # NEED 2: when the decline path requires a reason, enforce it here so the
            # rejection explanation is always captured (then persisted with the
            # document + in the audit trail by the service). Backward compatible:
            # steps whose signing_declined has requires_comment=False are unchanged.
            if transition.requires_comment and not (comment and comment.strip()):
                raise EngineError("A reason is required to decline a signature")
            record = {"actor": user.id, "decision": decision,
                      "at": datetime.now(timezone.utc).isoformat()}
            if comment and comment.strip():
                record["reason"] = comment.strip()  # carried into context + audit
            new_context = self._record_branch_decision(context, step.id, slot_id, record)
            result = self._settle(transition.to, new_context)
            result.vote = {"branch_id": slot_id, **record}
            return result

        record = {"actor": user.id, "decision": decision,
                  "at": datetime.now(timezone.utc).isoformat()}
        new_context = self._record_branch_decision(context, step.id, slot_id, record)
        vote_record = {"branch_id": slot_id, **record}

        # Signed. If a later signer remains, stay parked (pointer advances); else
        # the whole ordered list is complete -> settle along all_signed.
        if self._current_signer(cfg, step, new_context) is not None:
            return StepResult(step.id, StepType.ORDERED_SIGNING, False, new_context,
                              [step.id], vote=vote_record)
        transition = self._transition_by_action(step, "all_signed")
        if transition is None:
            raise EngineError(f"Ordered_signing step '{step.id}' has no 'all_signed' transition")
        result = self._settle(transition.to, new_context)
        result.vote = vote_record
        return result
