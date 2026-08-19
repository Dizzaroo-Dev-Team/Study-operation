"""
kernel.py
=========

The event-sourced PURE kernel of the workflow platform (V2 Phase 1).

    decide(definition, state, event) -> Decision(state', commands)

Everything the platform does to an instance is expressed as an EVENT going in
and a new state plus a list of COMMANDS coming out. The kernel is a pure
function: no DB, no clock, no network — same inputs, same outputs, always.
The service layer is the only place commands are executed (audit rows written,
side effects triggered), inside the same transaction that persists the state.

Relationship to engine.py
-------------------------
WorkflowEngine remains the pure stepping mechanics (transitions, conditions,
quorum, ordered signing). The kernel owns the EVENT/COMMAND contract on top of
it. The HTTP layer and the engine's own unit tests are unchanged — this is the
re-foundation behind the existing API.

Event log
---------
Every event the kernel accepts is materialized by the service as one or more
``workflow_audit_entries`` rows (the AppendAudit commands below) in the SAME
transaction as the state change. That table — append-only, ordered, complete —
IS the event log; the GCP/21 CFR audit trail and the kernel's event history are
one and the same artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .engine import WorkflowEngine, evaluate_join_policy
from .schemas import (
    CallConfig,
    CurrentUser,
    JobConfig,
    MessageConfig,
    StepType,
    TimerConfig,
    WorkflowDefinitionBody,
)

# Reserved context key holding per-CALL-step child bookkeeping:
#   context["_calls"][<call_step_id>] = {"expected": n, "done": {child_ref: terminal}}
_CALLS_KEY = "_calls"


class KernelError(Exception):
    """An event the current state cannot accept (user-facing 409-level)."""


# ---------------------------------------------------------------------------
# State — everything the kernel needs to know about one instance.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InstanceState:
    status: str                      # "active" | "completed" | "cancelled"
    current_step: Optional[str]
    context: dict[str, Any]


# ---------------------------------------------------------------------------
# Events — the stimuli. Phase 1 has the human-driven three; later phases add
# TaskCompleted / TimerFired / JobCompleted / MessageReceived / ChildCompleted
# as new event types routed through this same decide().
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StartWorkflow:
    context: dict[str, Any]


@dataclass(frozen=True)
class ActionPerformed:
    user: CurrentUser
    transition_id: str
    payload: dict[str, Any]
    comment: Optional[str] = None
    trusted_payload: bool = False    # internal service-to-service callers only


@dataclass(frozen=True)
class CancelRequested:
    user: CurrentUser
    comment: Optional[str] = None


# --- System stimuli (V2 Phase 4). The scheduler / job executor inject these;
# the kernel routes them like any other event — it never reads a clock and
# never runs the side effect itself. ---------------------------------------
@dataclass(frozen=True)
class TimerFired:
    step_id: str
    action: str            # the transition action the timer fires


@dataclass(frozen=True)
class JobCompleted:
    step_id: str
    result: dict[str, Any]


@dataclass(frozen=True)
class JobFailed:
    step_id: str
    error: str


# --- External orchestration stimuli (V2 Phase 5). ---------------------------
@dataclass(frozen=True)
class MessageReceived:
    step_id: str
    name: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ConditionMet:
    """A held wait_condition step's predicate became true on the sweep — release it."""
    step_id: str


@dataclass(frozen=True)
class ChildCompleted:
    step_id: str            # the parent's CALL step
    child_ref: str          # child instance id (string)
    child_terminal: Optional[str]
    # The child's terminal STATUS: "completed" (reached an end step) or
    # "cancelled" (cancelled before finishing). Both are terminal ARRIVALS at the
    # parent's join — a cancelled child must still resolve the join so the parent
    # never hangs. Defaults to "completed" for backward compatibility.
    child_status: str = "completed"


Event = Union[StartWorkflow, ActionPerformed, CancelRequested,
              TimerFired, JobCompleted, JobFailed,
              MessageReceived, ConditionMet, ChildCompleted]


# ---------------------------------------------------------------------------
# Commands — side effects for the service to execute in the same transaction.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AppendAudit:
    """One event-log/audit row (workflow_audit_entries)."""
    action: str
    actor: Optional[str] = None
    transition_id: Optional[str] = None
    from_step: Optional[str] = None
    to_step: Optional[str] = None
    comment: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistDeclineReason:
    """A signer declined with a reason — retain it WITH the document (the
    service reuses the agreement system-comment writer, flag-gated)."""
    branch_id: str
    reason: Optional[str]


# --- Task commands (V2 Phase 3). Entering a human step emits CreateTask; the
# matching ActionPerformed IS that task's TaskCompleted (the engine "waits" by
# parking until it arrives); work the flow moves past gets CancelTask. ---------
@dataclass(frozen=True)
class CreateTask:
    step_id: str
    slot_id: str
    name: str
    assignee_type: Optional[str]
    assignee_value: Optional[str]
    resolved_user_id: Optional[str]   # participant resolution AT CREATION


@dataclass(frozen=True)
class CompleteTask:
    step_id: str
    slot_id: str
    actor: Optional[str]


@dataclass(frozen=True)
class CancelTask:
    step_id: str
    slot_id: str


# --- Timer / Job commands (V2 Phase 4). The service computes fire_at from
# ArmTimer.seconds at the boundary (the kernel holds no clock) and the job
# executor runs InvokeJob's handler outside the kernel. -----------------------
@dataclass(frozen=True)
class ArmTimer:
    step_id: str
    seconds: int
    action: str


@dataclass(frozen=True)
class CancelTimer:
    step_id: str


@dataclass(frozen=True)
class InvokeJob:
    step_id: str
    kind: str
    params: dict[str, Any]
    max_attempts: int


@dataclass(frozen=True)
class CancelJob:
    step_id: str


# --- Sub-workflow commands (V2 Phase 5). -------------------------------------
@dataclass(frozen=True)
class SpawnChild:
    step_id: str                    # the CALL step the child belongs to
    definition_key: str
    context: dict[str, Any]


@dataclass(frozen=True)
class CancelChildren:
    """Join met early (n_of_m / percent): cancel the still-running children of
    this CALL step."""
    step_id: str


Command = Union[AppendAudit, PersistDeclineReason, CreateTask, CompleteTask,
                CancelTask, ArmTimer, CancelTimer, InvokeJob, CancelJob,
                SpawnChild, CancelChildren]


@dataclass(frozen=True)
class Decision:
    state: InstanceState
    commands: list[Command]


# ---------------------------------------------------------------------------
# decide — the one pure entry point.
# ---------------------------------------------------------------------------
def decide(body: WorkflowDefinitionBody, state: InstanceState, event: Event,
           enforce_roles: bool = True) -> Decision:
    engine = WorkflowEngine(body, enforce_roles=enforce_roles)

    if isinstance(event, StartWorkflow):
        result = engine.start(event.context)
        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id,
            context=result.context,
        )
        commands: list[Command] = [
            AppendAudit(action="started", to_step=result.step_id),
        ]
        commands += _notify_audits(result)
        return _finalize(engine, state, new_state, commands)

    if isinstance(event, CancelRequested):
        if state.status != "active":
            raise KernelError(f"Instance is already {state.status}")
        new_state = InstanceState("cancelled", state.current_step, state.context)
        commands = [
            AppendAudit(action="cancelled", actor=event.user.id,
                        from_step=state.current_step, to_step=state.current_step,
                        comment=event.comment),
        ]
        return _finalize(engine, state, new_state, commands)

    if isinstance(event, ActionPerformed):
        if state.status != "active":
            raise KernelError(f"Instance is {state.status}; no actions allowed")
        from_step = state.current_step
        action_verb = _verb_for(engine, from_step, event.transition_id)

        result = engine.perform(
            current_step_id=from_step,
            transition_id=event.transition_id,
            context=state.context,
            user=event.user,
            payload=event.payload,
            comment=event.comment,
            trusted_payload=event.trusted_payload,
        )

        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id,
            context=result.context,
        )

        # Branch votes / decisions carry richer audit detail than plain moves.
        audit_action = action_verb
        audit_payload = dict(event.payload or {})
        if result.vote:
            audit_action = result.vote["decision"]
            audit_payload["branch_id"] = result.vote["branch_id"]

        commands = [AppendAudit(
            action=audit_action, actor=event.user.id,
            transition_id=event.transition_id, from_step=from_step,
            to_step=result.step_id, comment=event.comment, payload=audit_payload,
        )]
        commands += _notify_audits(result)
        if result.vote and result.vote.get("decision") == "declined":
            commands.append(PersistDeclineReason(
                branch_id=result.vote.get("branch_id") or "signer",
                reason=(result.vote.get("reason") or (event.comment or "")).strip() or None,
            ))
        acted_slot = result.vote["branch_id"] if result.vote else ""
        return _finalize(engine, state, new_state, commands,
                         acted=(from_step, acted_slot), actor=event.user.id)

    if isinstance(event, TimerFired):
        if state.status != "active":
            raise KernelError(f"Timer is stale: instance is {state.status}")
        if event.step_id not in engine.parked_steps(state.current_step, state.context):
            raise KernelError(
                f"Timer is stale: instance is no longer parked at '{event.step_id}'")
        result = engine.fire_system_transition(event.step_id, event.action, state.context)
        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id, context=result.context)
        commands = [AppendAudit(action="timer_fired", from_step=event.step_id,
                                to_step=result.step_id,
                                payload={"timer_action": event.action})]
        commands += _notify_audits(result)
        return _finalize(engine, state, new_state, commands)

    if isinstance(event, JobCompleted):
        _require_parked_job(engine, state, event.step_id)
        cfg = _job_config(engine, event.step_id)
        # EXPLICIT output mapping — nothing merges into context implicitly, and
        # engine-owned (underscore) keys remain unwritable even from results.
        mapped: dict[str, Any] = {}
        for ctx_key, path in (cfg.output or {}).items():
            if ctx_key.startswith("_"):
                continue
            mapped[ctx_key] = _pluck(event.result, path)
        merged = dict(state.context)
        merged.update(mapped)
        result = engine.fire_system_transition(event.step_id, "job_done", merged)
        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id, context=result.context)
        commands = [AppendAudit(action="job_completed", from_step=event.step_id,
                                to_step=result.step_id, payload={"output": mapped})]
        commands += _notify_audits(result)
        return _finalize(engine, state, new_state, commands)

    if isinstance(event, JobFailed):
        _require_parked_job(engine, state, event.step_id)
        step = engine.step(event.step_id)
        has_fail_path = any(t.action == "job_failed" for t in step.transitions)
        if not has_fail_path:
            # No authored error path: stay parked (admin-visible via the job row
            # + this audit row); the flow does not advance on a dead job.
            return Decision(state, [AppendAudit(
                action="job_failed", from_step=event.step_id, to_step=event.step_id,
                payload={"error": event.error})])
        result = engine.fire_system_transition(event.step_id, "job_failed", state.context)
        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id, context=result.context)
        commands = [AppendAudit(action="job_failed", from_step=event.step_id,
                                to_step=result.step_id,
                                payload={"error": event.error})]
        commands += _notify_audits(result)
        return _finalize(engine, state, new_state, commands)

    if isinstance(event, MessageReceived):
        if state.status != "active":
            raise KernelError(f"Message is stale: instance is {state.status}")
        if event.step_id not in engine.parked_steps(state.current_step, state.context):
            raise KernelError(
                f"Message is stale: instance is no longer parked at '{event.step_id}'")
        cfg = MessageConfig.model_validate(
            (engine.step(event.step_id).config or {}).get("message") or {})
        if cfg.name != event.name:
            raise KernelError(
                f"Step '{event.step_id}' waits for message '{cfg.name}', not '{event.name}'")
        mapped = {k: _pluck(event.payload, p) for k, p in (cfg.output or {}).items()
                  if not k.startswith("_")}
        merged = dict(state.context)
        merged.update(mapped)
        result = engine.fire_system_transition(event.step_id, "message_received", merged)
        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id, context=result.context)
        commands = [AppendAudit(action="message_received", from_step=event.step_id,
                                to_step=result.step_id,
                                payload={"message": event.name, "output": mapped})]
        commands += _notify_audits(result)
        return _finalize(engine, state, new_state, commands)

    if isinstance(event, ConditionMet):
        if state.status != "active":
            raise KernelError(f"Condition is stale: instance is {state.status}")
        if event.step_id not in engine.parked_steps(state.current_step, state.context):
            raise KernelError(
                f"Condition is stale: instance is no longer parked at '{event.step_id}'")
        result = engine.fire_system_transition(event.step_id, "condition_met", state.context)
        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id, context=result.context)
        commands = [AppendAudit(action="condition_met", from_step=event.step_id,
                                to_step=result.step_id, payload={})]
        commands += _notify_audits(result)
        return _finalize(engine, state, new_state, commands)

    if isinstance(event, ChildCompleted):
        if state.status != "active":
            raise KernelError(f"Child completion is stale: instance is {state.status}")
        if event.step_id not in engine.parked_steps(state.current_step, state.context):
            raise KernelError(
                f"Child completion is stale: instance is no longer parked at "
                f"'{event.step_id}'")
        cfg = CallConfig.model_validate(
            (engine.step(event.step_id).config or {}).get("call") or {})
        calls_state = {k: dict(v) for k, v in (state.context.get(_CALLS_KEY) or {}).items()}
        slot = dict(calls_state.get(event.step_id) or {"expected": 1, "done": {}})
        done = dict(slot.get("done") or {})
        # Refs that arrived CANCELLED (a terminal-but-failed outcome). Tracked
        # separately so `done` keeps its legacy shape (ref -> terminal step) for
        # completed children, while the join can still count cancels as failures.
        cancelled = list(slot.get("cancelled") or [])
        if event.child_ref in done:
            raise KernelError(f"Child '{event.child_ref}' was already recorded")
        done[event.child_ref] = event.child_terminal
        if event.child_status == "cancelled" and event.child_ref not in cancelled:
            cancelled.append(event.child_ref)
        slot["done"] = done
        slot["cancelled"] = cancelled
        calls_state[event.step_id] = slot
        new_context = dict(state.context)
        new_context[_CALLS_KEY] = calls_state

        expected = int(slot.get("expected") or 1)
        ok = len(done) - len(cancelled)          # children that genuinely completed
        fail = len(cancelled)                    # children that were cancelled
        outcome = evaluate_join_policy(cfg.join.mode, cfg.join.value, "count",
                                       total=expected, ok=ok, fail=fail,
                                       open_count=expected - len(done))
        base = [AppendAudit(action="child_completed", from_step=event.step_id,
                            to_step=event.step_id,
                            payload={"child": event.child_ref,
                                     "terminal": event.child_terminal,
                                     "status": event.child_status})]
        # The join RESOLVES on "met" (enough succeeded) OR "failed" (the threshold
        # is now unreachable because too many were cancelled). Only "open" — work
        # still outstanding — keeps the parent parked. This is what stops a
        # cancelled child from hanging an "all" join forever.
        if outcome == "open":
            interim = InstanceState(state.status, state.current_step, new_context)
            return Decision(interim, base)

        result = engine.fire_system_transition(event.step_id, "children_done", new_context)
        new_state = InstanceState(
            status="completed" if result.is_terminal else "active",
            current_step=result.step_id, context=result.context)
        commands = list(base)
        if len(done) < expected:
            commands.append(CancelChildren(step_id=event.step_id))  # stragglers
        commands += _notify_audits(result)
        return _finalize(engine, state, new_state, commands)

    raise KernelError(f"Unknown event type: {type(event).__name__}")


def _finalize(engine: WorkflowEngine, before: InstanceState, after: InstanceState,
              commands: list[Command], acted: Optional[tuple] = None,
              actor: Optional[str] = None) -> Decision:
    """Common tail for every state-changing event: task diff, timer/job
    boundary diff, and CALL-step child spawning (which also stamps the expected
    child count into context['_calls'])."""
    commands = list(commands)
    commands += _task_commands(engine, before, after, acted=acted, actor=actor)
    commands += _boundary_commands(engine, before, after)
    after, call_cmds = _call_spawn_commands(engine, before, after)
    commands += call_cmds
    return Decision(after, commands)


def _call_spawn_commands(engine: WorkflowEngine, before: InstanceState,
                         after: InstanceState):
    """For each CALL step newly parked on: compute the child specs (single or
    one-per-item), emit SpawnChild commands, and record the expected count in
    context['_calls'] so ChildCompleted joins have a denominator."""
    def parked_calls(s: InstanceState) -> set[str]:
        if s.status != "active":
            return set()
        return {sid for sid in engine.parked_steps(s.current_step, s.context)
                if engine.step(sid).type == StepType.CALL}

    new_calls = parked_calls(after) - parked_calls(before)
    if not new_calls:
        return after, []
    context = dict(after.context)
    calls_state = {k: dict(v) for k, v in (context.get(_CALLS_KEY) or {}).items()}
    cmds: list[Command] = []
    for sid in sorted(new_calls):
        step = engine.step(sid)
        cfg = CallConfig.model_validate((step.config or {}).get("call") or {})
        base_ctx = {ck: context.get(pk) for ck, pk in (cfg.context_map or {}).items()}
        specs: list[dict] = []
        if cfg.items_path:
            items = context.get(cfg.items_path)
            if not isinstance(items, list) or not items:
                raise KernelError(
                    f"Call step '{sid}': context['{cfg.items_path}'] must be a "
                    f"non-empty list to spawn children")
            for i, item in enumerate(items):
                specs.append({**base_ctx, "item": item, "item_index": i})
        else:
            specs.append(dict(base_ctx))
        for spec in specs:
            cmds.append(SpawnChild(step_id=sid, definition_key=cfg.definition_key,
                                   context=spec))
        calls_state[sid] = {"expected": len(specs), "done": {}}
    context[_CALLS_KEY] = calls_state
    return InstanceState(after.status, after.current_step, context), cmds


def _require_parked_job(engine: WorkflowEngine, state: InstanceState,
                        step_id: str) -> None:
    if state.status != "active":
        raise KernelError(f"Job event is stale: instance is {state.status}")
    if step_id not in engine.parked_steps(state.current_step, state.context):
        raise KernelError(
            f"Job event is stale: instance is no longer parked at '{step_id}'")


def _job_config(engine: WorkflowEngine, step_id: str) -> JobConfig:
    step = engine.step(step_id)
    return JobConfig.model_validate((step.config or {}).get("job") or {})


def _pluck(result: dict, path: str) -> Any:
    """Dotted-path lookup into a job result ('data.amount'). Missing -> None."""
    node: Any = result
    for part in (path or "").split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _boundary_commands(engine: WorkflowEngine, before: InstanceState,
                       after: InstanceState) -> list[Command]:
    """Diff the PARKED STEPS between two states into timer/job commands: arm a
    timer / invoke a job when a step with that config is newly parked; cancel
    them when the flow departs the step."""
    def parked(s: InstanceState) -> set[str]:
        if s.status != "active":
            return set()
        return set(engine.parked_steps(s.current_step, s.context))

    before_steps = parked(before)
    after_steps = parked(after)
    cmds: list[Command] = []
    for sid in sorted(after_steps - before_steps):
        step = engine.step(sid)
        raw_timer = (step.config or {}).get("timer")
        if raw_timer:
            tc = TimerConfig.model_validate(raw_timer)
            cmds.append(ArmTimer(step_id=sid, seconds=tc.seconds, action=tc.action))
        if step.type == StepType.JOB:
            jc = JobConfig.model_validate((step.config or {}).get("job") or {})
            cmds.append(InvokeJob(step_id=sid, kind=jc.kind, params=dict(jc.params),
                                  max_attempts=jc.max_attempts))
    for sid in sorted(before_steps - after_steps):
        step = engine.step(sid)
        if (step.config or {}).get("timer"):
            cmds.append(CancelTimer(step_id=sid))
        if step.type == StepType.JOB:
            cmds.append(CancelJob(step_id=sid))
    return cmds


def _task_commands(engine: WorkflowEngine, before: InstanceState,
                   after: InstanceState, acted: Optional[tuple] = None,
                   actor: Optional[str] = None) -> list[Command]:
    """Diff the open work units between two states into task commands. The unit
    the action consumed completes; units the flow moved past are cancelled;
    newly parked units are created (with the participant resolved NOW)."""
    def unit_map(s: InstanceState):
        if s.status != "active":
            return {}
        return {(u["step_id"], u["slot_id"]): u
                for u in engine.work_units(s.current_step, s.context)}

    before_units = unit_map(before)
    after_units = unit_map(after)
    cmds: list[Command] = []
    for key, u in after_units.items():
        if key not in before_units:
            cmds.append(CreateTask(
                step_id=u["step_id"], slot_id=u["slot_id"], name=u["name"],
                assignee_type=u["assignee_type"], assignee_value=u["assignee_value"],
                resolved_user_id=_resolve_participant(u, after.context),
            ))
    acted_keys = set()
    if acted is not None:
        acted_keys = {(acted[0], acted[1] or ""), (acted[0], "")}
    for key, u in before_units.items():
        if key in after_units:
            continue
        if key in acted_keys:
            cmds.append(CompleteTask(step_id=u["step_id"], slot_id=u["slot_id"],
                                     actor=actor))
        else:
            cmds.append(CancelTask(step_id=u["step_id"], slot_id=u["slot_id"]))
    return cmds


def _resolve_participant(unit: dict, context: dict) -> Optional[str]:
    """Participant resolution policy, applied at task creation: a concrete user
    when one is determinable (direct user, or a context-held user id); roles
    stay role-addressed and resolve at claim time."""
    if unit["assignee_type"] == "user":
        return unit["assignee_value"]
    if unit["assignee_type"] == "context" and unit["assignee_value"]:
        v = (context or {}).get(unit["assignee_value"])
        return str(v) if v else None
    return None


def _notify_audits(result) -> list[AppendAudit]:
    """One event-log row per notify-recipient delivered while settling."""
    return [
        AppendAudit(action="notified", from_step=result.step_id,
                    to_step=result.step_id, payload={"branch_id": branch_id})
        for branch_id in (result.notified or [])
    ]


def _verb_for(engine: WorkflowEngine, step_id: Optional[str], transition_id: str) -> str:
    if step_id is None:
        return "action"
    step = engine.step(step_id)
    for t in step.transitions:
        if t.id == transition_id:
            return t.action
    return "action"
