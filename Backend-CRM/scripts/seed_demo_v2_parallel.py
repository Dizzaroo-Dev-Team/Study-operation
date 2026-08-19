"""
seed_demo_v2_parallel.py
========================

Seeds the V2 UI walkthrough workflow and proves the whole path server-side.

The definition (key V2-DEMO):

  draft (form)
    -> fork (split)
         -> legal_review  (approval)                                  -> merge
         -> finance_review (approval, 2-minute timer -> finance_escalation -> merge)
  merge (join: all) -> distribute (job kind "notify": generate+distribute PDF)
    -> executed (terminal)

What you SEE in the UI: the Task Inbox with BOTH review tasks at once, both
tracks actionable in parallel in the runner, the job panel running to
completion, and the 2-minute countdown chip on the finance track.

Run inside the backend container:
  python scripts/seed_demo_v2_parallel.py            # seed + verify + fresh instance
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import AsyncSessionLocal  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(label, ok, detail=""):
    _results.append(ok)
    print(f"  {PASS if ok else FAIL}  {label}" + (f"  -> {detail}" if detail else ""))


DEMO = {
    "key": "V2-DEMO",
    "name": "V2 Demo — Parallel Review + PDF Job + Timer",
    "description": "Two parallel review tracks, a join, an automated distribute job, "
                   "and a 2-minute escalation timer on the finance track.",
    "start_step": "draft",
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft the package",
         "config": {"fields": [{"key": "study_name", "label": "Study name",
                                "type": "text", "required": True}]},
         "transitions": [{"id": "submit", "to": "fork", "label": "Submit for review",
                          "action": "submit"}]},
        {"id": "fork", "type": "split", "name": "Open parallel reviews",
         "transitions": [
             {"id": "go_legal", "to": "legal_review", "label": "Legal track", "action": "auto"},
             {"id": "go_fin", "to": "finance_review", "label": "Finance track", "action": "auto"}]},
        {"id": "legal_review", "type": "approval", "name": "Legal Review",
         "assignee": {"type": "role", "value": "legal"},
         "transitions": [{"id": "l_ok", "to": "merge", "label": "Legal approves",
                          "action": "approve"}]},
        {"id": "finance_review", "type": "approval", "name": "Finance Review",
         "assignee": {"type": "role", "value": "financial"},
         "config": {"timer": {"seconds": 120, "action": "timeout"}},
         "transitions": [
             {"id": "f_ok", "to": "merge", "label": "Finance approves", "action": "approve"},
             {"id": "f_esc", "to": "finance_escalation", "label": "Escalate (2 min)",
              "action": "timeout"}]},
        {"id": "finance_escalation", "type": "approval", "name": "Finance Escalation (VP)",
         "assignee": {"type": "role", "value": "vp"},
         "transitions": [{"id": "esc_ok", "to": "merge", "label": "VP approves",
                          "action": "approve"}]},
        {"id": "merge", "type": "join", "name": "Both reviews complete",
         "config": {"join": {"mode": "all"}},
         "transitions": [{"id": "merged", "to": "distribute", "label": "Merged",
                          "action": "join_met"}]},
        {"id": "distribute", "type": "job", "name": "Generate & distribute final PDF",
         "config": {"job": {"kind": "notify", "max_attempts": 3,
                            "params": {"recipients": ["site-team@example.org"],
                                       "subject": "Final package PDF"},
                            "output": {"distribution": "notified"}}},
         "transitions": [
             {"id": "jd", "to": "executed", "label": "Distributed", "action": "job_done"},
             {"id": "jf", "to": "dist_failed", "label": "Failed", "action": "job_failed"}]},
        {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
        {"id": "dist_failed", "type": "terminal", "name": "Distribution failed",
         "transitions": []},
    ],
}


def U(uid, *roles):
    return CurrentUser(id=uid, roles=list(roles))


async def main():
    async with AsyncSessionLocal() as db:
        body = WorkflowDefinitionBody.model_validate(DEMO)
        await service.create_or_update_definition(db, body, publish=True,
                                                  published_by="seed-script")
        await db.commit()
        print("Published definition V2-DEMO.")

        # ── Throwaway verification instance: drive the whole demo path. ──────
        print("\nVerifying the walkthrough path end-to-end:")
        inst = await service.start_instance(db, "V2-DEMO", {})
        iid = int(inst.id)
        await db.commit()

        await service.perform_action(db, iid, U("demo", "study_manager"), "submit",
                                     {"study_name": "ST-42"}, None)
        await db.commit()
        fresh = await service.get_instance(db, iid)
        tokens = sorted(t["step"] for t in fresh.context.get("_tokens", []))
        check("split opened both tracks", tokens == ["finance_review", "legal_review"],
              str(tokens))

        tasks = await service.list_tasks_for_user(db, U("anyone"))
        mine = [(t["step_id"]) for t in tasks if t["instance_id"] == iid]
        check("inbox shows BOTH review tasks at once",
              sorted(mine) == ["finance_review", "legal_review"], str(sorted(mine)))

        act = await service.list_activity(db, iid)
        timer = next((t for t in act["timers"]
                      if t["step_id"] == "finance_review" and t["status"] == "pending"), None)
        check("2-minute timer armed on finance track", timer is not None,
              f"fires at {timer['fire_at']}" if timer else "missing")

        # Both tracks act IN PARALLEL (order-independent): finance first, then legal.
        await service.perform_action(db, iid, U("fin", "financial"), "f_ok", {}, None)
        await db.commit()
        fresh = await service.get_instance(db, iid)
        check("finance done, legal still open (join waits)",
              [t["step"] for t in fresh.context.get("_tokens", [])] == ["legal_review"])

        await service.perform_action(db, iid, U("leg", "legal"), "l_ok", {}, None)
        await db.commit()
        fresh = await service.get_instance(db, iid)
        check("join met -> parked on the PDF job step", fresh.current_step == "distribute")
        act = await service.list_activity(db, iid)
        job = act["jobs"][-1] if act["jobs"] else None
        check("job row pending (visible in the job panel)",
              bool(job and job["status"] == "pending"))

        processed = await service.run_pending_jobs(db)
        await db.commit()
        fresh = await service.get_instance(db, iid)
        check("sweep ran the job -> workflow executed",
              processed >= 1 and fresh.current_step == "executed"
              and fresh.status == "completed")

        # Tidy: remove the throwaway instance, keep the definition.
        await service.reset_agreement(db, str(iid) + "-nonexistent")  # no-op guard
        # (we keep the completed throwaway as history; it is harmless)

        # ── A FRESH instance for the user to walk through in the UI. ─────────
        demo = await service.start_instance(db, "V2-DEMO", {})
        await db.commit()
        print(f"\nFresh walkthrough instance started: id={demo.id}")
        print(f"Open it at:  /workflows/instances/{demo.id}")
        print("Or find its tasks in the Task Inbox at:  /workflows/inbox")

        ok = all(_results)
        print(f"\n{sum(_results)}/{len(_results)} checks passed")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
