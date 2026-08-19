"""THE CONNECTOR CONTRACT — the only thing a project must implement.

To plug a new project into this toolkit, write one async function:

    async def run(input: dict) -> RunResult

* ``input`` is an opaque, project-defined dict. It is passed VERBATIM from a
  golden's ``input:`` block; the generic toolkit never interprets it. Put
  whatever your agent needs in it (message, user fixture, screen context,
  auto-approve policy, ...).
* The connector must actually execute the agent (or a clearly-labeled fixture)
  and then assemble the result from the agent's own ground truth — an audit
  log, an event stream, tool-call records — NOT from the model's claims.

``RunResult`` fields:

    answer: str
        The final user-visible answer text of the agent.

    trace: dict
        A normalized record of what the agent ACTUALLY did. All keys are
        optional (graders treat a missing key as empty):

        actions: list[dict]
            One entry per tool/command execution attempt, in order.
            {
              "name": str,          # command/tool name
              "risk": str | None,   # e.g. "read" / "write" / "regulated"
              "status": Any,        # per-action outcome: "ok", an HTTP int,
                                    # "cancelled", "timeout", ...
              "ok": bool,           # True iff the action succeeded
              "executed": bool,     # True iff it actually ran (False for e.g.
                                    # a declined confirmation stub)
            }

        confirmations: list[dict]
            Human-approval gates the agent raised.
            {"command", "risk", "description", "decision"}  where decision is
            "approved" / "declined" / "timeout" / "resolve_failed".

        audit: list[dict]
            Durable audit-trail rows attributable to this run.
            {"action", "actor", "target_type", "target_id", "details",
             "via", "actor_is_acting_user"}

        flags: dict
            Arbitrary project-specific probes addressed by dotted path in the
            ``flag_equals`` check, e.g. {"phi_filter": {"fired": true}} or
            {"navigate": {"screen": "tasks"}}.

        raw: dict
            Optional untyped extras (raw event stream, timings). Never used by
            graders; kept for debugging failed cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict


@dataclass
class RunResult:
    answer: str
    trace: Dict[str, Any] = field(default_factory=dict)


# The contract, as a type: each project's connector module exposes `run`.
Connector = Callable[[Dict[str, Any]], Awaitable[RunResult]]
