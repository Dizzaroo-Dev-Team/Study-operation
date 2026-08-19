"""
Seed a LONG custom workflow shape so the sandbox runner (/workflow-test) has a
second, differently-shaped flow to start (proving the runner is data-driven —
it renders this shape's stepper line + buttons with zero shape-specific code).

Shape: draft (form) -> review (parallel: legal + financial)
        -> signing (ordered_signing: director -> pi -> vp)
        -> distribute (broadcast) -> done (terminal)

Published as key DEMO_LONG. Idempotent (re-running just publishes a new version).
This is a SANDBOX demo definition — it does not affect CDA/CTA or any agreement.
Run in the backend container.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

DEMO_LONG = {
    "key": "DEMO_LONG",
    "name": "Demo — long custom flow",
    "description": "draft → parallel review → ordered signing → broadcast → done (sandbox demo).",
    "start_step": "draft",
    "context_schema": [],
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "review", "label": "Submit for review", "action": "submit"}]},
        {"id": "review", "type": "parallel", "name": "Parallel Review",
         "config": {"branches": [
             {"id": "legal", "name": "Legal", "assignee": {"type": "role", "value": "legal"}},
             {"id": "financial", "name": "Financial", "assignee": {"type": "role", "value": "financial"}}],
             "quorum": {"mode": "all"}, "on_reject": "count"},
         "transitions": [
             {"id": "ok", "to": "signing", "label": "Both approved", "action": "quorum_met"},
             {"id": "rwk", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
        {"id": "signing", "type": "ordered_signing", "name": "Ordered Signing",
         "config": {"signers": [
             {"id": "director", "name": "Site Director", "assignee": {"type": "role", "value": "sponsor"}},
             {"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "coordinator"}},
             {"id": "vp", "name": "VP", "assignee": {"type": "role", "value": "sponsor"}}]},
         "transitions": [
             {"id": "all_signed", "to": "distribute", "label": "All signed", "action": "all_signed"},
             {"id": "declined", "to": "draft", "label": "Declined", "action": "signing_declined"}]},
        {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy",
         "config": {"recipients": [
             {"id": "pi", "name": "PI"}, {"id": "crc", "name": "CRC"}, {"id": "site_legal", "name": "Site Legal"}]},
         "transitions": [{"id": "done_t", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}


async def main():
    body = WorkflowDefinitionBody.model_validate(DEMO_LONG)
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            v = await service.create_or_update_definition(db, body, publish=True, published_by="system:seed")
        print(f"Seeded + published DEMO_LONG version {v.version}")
        order = [s["id"] for s in (await service.get_definition_version(db, "DEMO_LONG")).body["steps"]]
        print("steps:", order)


if __name__ == "__main__":
    asyncio.run(main())
