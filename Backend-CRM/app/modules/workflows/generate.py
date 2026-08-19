"""
generate.py
===========

LLM "auto-create": turn a plain-English description into a DRAFT
WorkflowDefinitionBody for the builder canvas. The LLM ONLY drafts — it never
saves or publishes. Validation (the SAME WorkflowDefinitionBody the builder uses)
plus human review on the canvas are the safety net.

Pipeline:
  1. Build a system prompt that teaches the FULL definition language, with the
     step/config schemas DERIVED from the Pydantic models (not hand-waved) and two
     worked few-shot examples (simple CDA + the full CTA).
  2. Call the EXISTING Gemini client (same one CTA placeholder fill uses), via the
     single swappable seam `_llm_generate_json`.
  3. Parse defensively (the client already strips markdown fences), then VALIDATE
     with WorkflowDefinitionBody.
  4. REPAIR LOOP: on invalid JSON / invalid schema, feed the error back and ask the
     model to fix and re-emit — up to 2 retries. If still invalid, return a clear
     error (never junk).
  5. Return the validated draft only: {"body": <json>, "assumptions": [...]}, or
     {"needs_clarification": "<question>"}, or {"error": "..."}.

PURE w.r.t. the engine: this module imports the schema + the engine's seed example
only; it never touches agreement code and never persists anything.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from pydantic import ValidationError

from .schemas import (
    BroadcastConfig,
    CallConfig,
    FormField,
    JobConfig,
    JoinPolicy,
    MessageConfig,
    OrderedSigningConfig,
    ParallelConfig,
    StepType,
    TimerConfig,
    WorkflowDefinitionBody,
)

logger = logging.getLogger(__name__)

# Few-shot example 1: a simple CDA (draft -> legal review -> signature -> executed).
# Inlined here (was imported from the now-removed legacy seed module) so generation
# is self-contained. PEDAGOGICAL ONLY — it teaches the definition language; it does
# not constrain the model to any document type or shape.
CDA_DEFINITION = {
    "key": "CDA",
    "name": "Confidential Disclosure Agreement",
    "description": "Lightweight two-step workflow for a CDA.",
    "start_step": "draft",
    "context_schema": [
        {"key": "counterparty", "label": "Counterparty", "type": "text"},
    ],
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft CDA",
         "assignee": {"type": "role", "value": "study_manager"},
         "config": {"fields": [{"key": "counterparty", "label": "Counterparty",
                                "type": "text", "required": True}]},
         "transitions": [{"id": "submit", "to": "legal_review",
                          "label": "Submit draft", "action": "submit"}]},
        {"id": "legal_review", "type": "approval", "name": "Legal Review",
         "assignee": {"type": "role", "value": "medical_monitor"},
         "transitions": [
             {"id": "approve", "to": "signature", "label": "Approve", "action": "approve"},
             {"id": "reject", "to": "draft", "label": "Reject", "action": "reject",
              "requires_comment": True}]},
        {"id": "signature", "type": "signature", "name": "Authorized Signature",
         "assignee": {"type": "role", "value": "sponsor"},
         "transitions": [{"id": "sign", "to": "executed", "label": "Sign", "action": "sign"}]},
        {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
    ],
}

MAX_REPAIR_RETRIES = 2


# ---------------------------------------------------------------------------
# The single, swappable model-call seam (reuses the existing Gemini client).
# Tests monkeypatch this; production delegates to the same AIClient.generate_json
# that CTA placeholder fill uses, so there's one provider + one set of creds.
# ---------------------------------------------------------------------------
async def _llm_generate_json(prompt: str) -> Optional[dict]:
    from app.config import settings
    from app.integrations.ai.client import AIClient

    client = AIClient(model_name=settings.workflow_generation_model)
    return await client.generate_json(prompt)


# ---------------------------------------------------------------------------
# Few-shot example 2: the full real CTA (mirrors tests/test_full_cta.py's flow).
# Embedded here so production code does not import from the tests package.
# ---------------------------------------------------------------------------
CTA_EXAMPLE_BODY: dict = {
    "key": "CTA",
    "name": "Clinical Trial Agreement",
    "start_step": "draft",
    "context_schema": [{"key": "has_cro", "label": "CRO involved?", "type": "boolean"}],
    "steps": [
        {"id": "draft", "type": "form", "name": "Main User Creates Document", "module": "document_create",
         "assignee": {"type": "role", "value": "study_manager"},
         "config": {"fields": [{"key": "has_cro", "label": "Is a CRO involved?", "type": "boolean", "required": True}]},
         "transitions": [{"id": "submit", "to": "internal_review", "label": "Submit", "action": "submit"}]},
        {"id": "internal_review", "type": "parallel", "name": "Internal Review", "module": "review",
         "config": {"branches": [
             {"id": "internal_legal", "name": "Internal Legal", "assignee": {"type": "role", "value": "legal"}},
             {"id": "internal_financial", "name": "Internal Financial", "assignee": {"type": "role", "value": "financial"}}],
             "quorum": {"mode": "all"}, "on_reject": "count"},
         "transitions": [
             {"id": "ir_ok", "to": "cro_gate", "label": "Both approved", "action": "quorum_met"},
             {"id": "ir_rwk", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
        {"id": "cro_gate", "type": "decision", "name": "Does CRO Exist?",
         "transitions": [
             {"id": "cro_yes", "to": "cro_review", "label": "CRO exists", "action": "auto",
              "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
             {"id": "cro_no", "to": "site_team", "label": "No CRO", "action": "auto"}]},
        {"id": "cro_review", "type": "parallel", "name": "CRO Review", "module": "review",
         "config": {"branches": [
             {"id": "cro_legal", "name": "CRO Legal", "assignee": {"type": "role", "value": "legal"}},
             {"id": "cro_financial", "name": "CRO Financial", "assignee": {"type": "role", "value": "financial"}}],
             "quorum": {"mode": "all"}, "on_reject": "count"},
         "transitions": [
             {"id": "cro_ok", "to": "signatures", "label": "Approved", "action": "quorum_met"},
             {"id": "cro_rwk", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
        {"id": "site_team", "type": "parallel", "name": "Send to Site Team", "module": "review",
         "config": {"branches": [
             {"id": "pi", "name": "PI", "kind": "notify"},
             {"id": "site_manager", "name": "Site Manager", "kind": "notify"},
             {"id": "crc", "name": "CRC", "kind": "notify"},
             {"id": "site_legal", "name": "Site Legal", "kind": "action", "assignee": {"type": "role", "value": "legal"}},
             {"id": "site_financial", "name": "Site Financial", "kind": "action", "assignee": {"type": "role", "value": "financial"}}],
             "quorum": {"mode": "all"}, "on_reject": "count"},
         "transitions": [
             {"id": "st_ok", "to": "signatures", "label": "Finalized", "action": "quorum_met"},
             {"id": "st_rwk", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
        {"id": "signatures", "type": "ordered_signing", "name": "Site Signatures", "module": "signing",
         "config": {"signers": [
             {"id": "site_director", "name": "Site Director", "assignee": {"type": "role", "value": "site_director"}},
             {"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "pi"}}]},
         "transitions": [{"id": "sig_done", "to": "vp_sign", "label": "Site signed", "action": "all_signed"}]},
        {"id": "vp_sign", "type": "ordered_signing", "name": "VP Signature", "module": "signing",
         "config": {"signers": [{"id": "vp", "name": "VP", "assignee": {"type": "role", "value": "sponsor"}}]},
         "transitions": [{"id": "vp_done", "to": "executed", "label": "VP signed", "action": "all_signed"}]},
        {"id": "executed", "type": "approval", "name": "Final Executed Document", "module": "approval",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "exec", "to": "distribute", "label": "Distribute", "action": "distribute"}]},
        {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy", "module": "broadcast",
         "config": {"recipients": [
             {"id": "pi", "name": "PI"}, {"id": "site_manager", "name": "Site Manager"},
             {"id": "site_legal", "name": "Site Legal"}, {"id": "site_financial", "name": "Site Financial"},
             {"id": "crc", "name": "CRC"}, {"id": "site_director", "name": "Site Director"}]},
         "transitions": [{"id": "dist", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}


# Few-shot example 3: the review→sign module flow (matches the unified modules and
# the "review gates signing" fix). Teaches `module` on every step, the send_back
# rework loop, owner-gated signing, and the plain-English summary shape.
REVIEW_SIGN_EXAMPLE: dict = {
    "body": {
        "key": "REVIEW_SIGN", "name": "Review then Sign", "start_step": "draft", "context_schema": [],
        "steps": [
            {"id": "draft", "type": "form", "name": "Create Document", "module": "document_create",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "review", "label": "Submit draft", "action": "submit"}]},
            {"id": "review", "type": "approval", "name": "Legal Review", "module": "review",
             "assignee": {"type": "role", "value": "legal"},
             "transitions": [
                 {"id": "ok", "to": "signing", "label": "Approve", "action": "approve"},
                 {"id": "back", "to": "draft", "label": "Send back", "action": "send_back", "requires_comment": True}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signature", "module": "signing",
             "config": {"handoff": "auto",
                        "signers": [{"id": "signer", "name": "Authorized Signer",
                                     "assignee": {"type": "role", "value": "sponsor"}}]},
             "transitions": [{"id": "signed", "to": "end", "label": "All signed", "action": "all_signed"}]},
            {"id": "end", "type": "terminal", "name": "Done", "transitions": []},
        ],
    },
    "assumptions": [
        "One legal reviewer; the reviewer can approve or send the document back to draft for edits.",
        "After approval, one authorized signer signs via OTP (automatic handoff between signers).",
        "Only the creator/owner sends for review and for signature.",
    ],
    "summary": ("This sends the document to one legal reviewer, who can approve it or return it "
                "for edits (it goes back to draft and can be re-sent). Once approved, one authorized "
                "signer signs via OTP, and the agreement is then complete."),
}


# Few-shot example 4 (V2): the ADVANCED capabilities — REAL parallel tracks that are
# each a FULL SEQUENCE (split -> branch sequences -> join), an AUTOMATIC step (job)
# with an explicit output mapping, and a TIMER escalation on a human step. Teaches the
# model that these types exist and exactly how to wire their config + transitions.
# Validated by tests so it can never drift out of schema.
V2_EXAMPLE_BODY: dict = {
    "key": "V2_PARALLEL", "name": "Parallel Tracks with Automation", "start_step": "intake",
    "context_schema": [],
    "steps": [
        {"id": "intake", "type": "form", "name": "Create Package", "module": "document_create",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "fork", "label": "Submit", "action": "submit"}]},
        # SPLIT: open two independent tracks at once; each is a full multi-step sequence.
        {"id": "fork", "type": "split", "name": "Open Legal & Budget Tracks",
         "transitions": [
             {"id": "to_legal", "to": "legal_draft", "label": "Legal track", "action": "auto"},
             {"id": "to_budget", "to": "budget_draft", "label": "Budget track", "action": "auto"}]},
        # Legal track sequence: draft -> review -> join.
        {"id": "legal_draft", "type": "form", "name": "Draft Legal Terms", "module": "document_create",
         "assignee": {"type": "role", "value": "legal"},
         "transitions": [{"id": "ld_submit", "to": "legal_review", "label": "Submit", "action": "submit"}]},
        {"id": "legal_review", "type": "approval", "name": "Legal Review", "module": "review",
         "assignee": {"type": "role", "value": "legal"},
         "transitions": [
             {"id": "lr_ok", "to": "merge", "label": "Approve", "action": "approve"},
             {"id": "lr_back", "to": "legal_draft", "label": "Send back", "action": "send_back",
              "requires_comment": True}]},
        # Budget track sequence: draft -> review -> join.
        {"id": "budget_draft", "type": "form", "name": "Draft Budget", "module": "document_create",
         "assignee": {"type": "role", "value": "financial"},
         "transitions": [{"id": "bd_submit", "to": "budget_review", "label": "Submit", "action": "submit"}]},
        {"id": "budget_review", "type": "approval", "name": "Budget Review", "module": "review",
         "assignee": {"type": "role", "value": "financial"},
         "transitions": [
             {"id": "br_ok", "to": "merge", "label": "Approve", "action": "approve"},
             {"id": "br_back", "to": "budget_draft", "label": "Send back", "action": "send_back",
              "requires_comment": True}]},
        # JOIN: wait for BOTH tracks (mode all), then continue on a single token.
        {"id": "merge", "type": "join", "name": "Both Tracks Complete",
         "config": {"join": {"mode": "all"}},
         "transitions": [{"id": "merged", "to": "render", "label": "Merged", "action": "join_met"}]},
        # JOB: an automatic step (no human) — render the final PDF. `kind` names the
        # registered handler; `output` maps result paths into context. On failure it
        # routes back to intake to fix and resubmit.
        {"id": "render", "type": "job", "name": "Generate Final PDF",
         "config": {"job": {"kind": "generate_document", "params": {"title": "Final Package"},
                            "max_attempts": 3, "output": {"document_url": "document_url"}}},
         "transitions": [
             {"id": "rendered", "to": "final_approval", "label": "Rendered", "action": "job_done"},
             {"id": "render_failed", "to": "intake", "label": "Generation failed", "action": "job_failed"}]},
        # TIMER: human sign-off that auto-escalates if no response within 2 minutes.
        # config.timer.action MUST match an outgoing transition's action.
        {"id": "final_approval", "type": "approval", "name": "Final Sign-off", "module": "approval",
         "assignee": {"type": "role", "value": "study_manager"},
         "config": {"timer": {"seconds": 120, "action": "escalate"}},
         "transitions": [
             {"id": "fa_ok", "to": "notify", "label": "Approve", "action": "approve"},
             {"id": "fa_esc", "to": "escalated", "label": "Escalate (no response in 2 min)",
              "action": "escalate"}]},
        {"id": "escalated", "type": "approval", "name": "Escalated Sign-off", "module": "approval",
         "assignee": {"type": "role", "value": "medical_monitor"},
         "transitions": [{"id": "esc_ok", "to": "notify", "label": "Approve", "action": "approve"}]},
        # JOB: automatic notification (registered "notify" handler).
        {"id": "notify", "type": "job", "name": "Notify Stakeholders",
         "config": {"job": {"kind": "notify", "params": {"subject": "Package executed"}}},
         "transitions": [{"id": "notified", "to": "distribute", "label": "Notified", "action": "job_done"}]},
        {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy", "module": "broadcast",
         "config": {"recipients": [{"id": "legal", "name": "Legal"}, {"id": "financial", "name": "Finance"}]},
         "transitions": [{"id": "dist", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}


def _schema_text() -> str:
    """Authoritative schema text DERIVED from the Pydantic models — the body
    contract plus the config shapes the builder validates against."""
    parts = {
        "WorkflowDefinitionBody": WorkflowDefinitionBody.model_json_schema(),
        "ParallelConfig (step.config for type 'parallel')": ParallelConfig.model_json_schema(),
        "OrderedSigningConfig (step.config for type 'ordered_signing')": OrderedSigningConfig.model_json_schema(),
        "BroadcastConfig (step.config for type 'broadcast')": BroadcastConfig.model_json_schema(),
        "FormField (each entry of step.config.fields for type 'form')": FormField.model_json_schema(),
        # V2 config shapes — the LLM needs these to author the advanced types.
        "JobConfig (step.config['job'] for type 'job' — 'kind' is REQUIRED)": JobConfig.model_json_schema(),
        "TimerConfig (step.config['timer'] on ANY step)": TimerConfig.model_json_schema(),
        "JoinPolicy (step.config['join'] for type 'join')": JoinPolicy.model_json_schema(),
        "MessageConfig (step.config['message'] for type 'wait_message')": MessageConfig.model_json_schema(),
        "CallConfig (step.config['call'] for type 'call')": CallConfig.model_json_schema(),
    }
    blocks = [f"### {title}\n{json.dumps(schema)}" for title, schema in parts.items()]
    return "\n\n".join(blocks)


def _real_roles_block(iam_roles: Optional[list[str]]) -> str:
    """The authoritative role vocabulary the LLM must author against — the roles
    that actually exist in IAM. Without it (no DB at call time) the model falls
    back to descriptive role words, which the normalizer then slug-matches."""
    roles = [str(r).strip() for r in (iam_roles or []) if str(r).strip()]
    if not roles:
        return ""
    listed = ", ".join(f'"{r}"' for r in roles)
    return (
        "\nREAL ROLES IN THIS SYSTEM (authoritative — use ONLY these for every role\n"
        "assignee; do NOT invent role names like 'study_manager'/'legal'):\n"
        f"  {listed}\n"
        "Map each role the description NAMES to the closest role in this list (case/\n"
        "spacing don't matter — 'contract specialist' -> 'CONTRACT_SPECIALIST').\n"
        "CRITICAL — DEFAULT UNNAMED ACTORS TO THE OWNER, NOT A GUESSED ROLE: when the\n"
        "description does NOT say who performs a step (who drafts, sends, signs, or\n"
        "acknowledges), assign that step to the OWNER with\n"
        "  {\"type\":\"context\",\"value\":\"owner_user_id\"}\n"
        "— NEVER pick a real role from the list at random to fill the gap. Use a\n"
        "specific role ONLY when the description names that role for that step. If the\n"
        "description names a role with NO clear match in this list, DO NOT invent one —\n"
        "list it under \"assumptions\" so a human can pick the real role.\n"
    )


def build_system_prompt(iam_roles: Optional[list[str]] = None) -> str:
    step_types = ", ".join(t.value for t in StepType)
    cda_example = {
        "body": CDA_DEFINITION,
        "assumptions": [
            "Assumed a single legal reviewer approves, then one authorized signer signs.",
            "Assigned roles 'legal' (review) and 'vp' (signature) as placeholders.",
        ],
    }
    cta_example = {
        "body": CTA_EXAMPLE_BODY,
        "assumptions": [
            "Internal legal + financial must BOTH approve (quorum: all).",
            "Branch on whether a CRO is involved (context flag has_cro).",
            "Signing order: Site Director, then PI, then VP.",
            "Final copy is broadcast to the whole site team.",
        ],
    }
    v2_example = {
        "body": V2_EXAMPLE_BODY,
        "assumptions": [
            "The legal and budget tracks run truly in PARALLEL — each is its own "
            "draft+review sequence — and merge only when BOTH are done (split/join, join mode all).",
            "PDF generation and stakeholder notification are AUTOMATIC (job steps, no human).",
            "Final sign-off auto-escalates to the medical monitor if there is no response "
            "within 2 minutes (timer of 120s firing the 'escalate' transition).",
        ],
        "summary": ("This opens two parallel tracks — a legal track (draft then review) and a "
                    "budget track (draft then review) — that run independently and merge once both "
                    "finish. The system then generates the final PDF automatically, asks the study "
                    "manager for final sign-off (auto-escalating to the medical monitor after two "
                    "minutes with no response), automatically notifies stakeholders, and distributes "
                    "the final copy."),
    }
    return f"""You are a workflow-definition generator for a clinical-trial document platform.
Convert the user's plain-English description into ONE valid workflow definition.

You output a DRAFT only — it is never auto-saved or published; a human reviews and
edits it on a builder canvas afterwards. Therefore: make reasonable assumptions and
proceed, but LIST those assumptions.

SCOPE — BUILD ONLY WHAT THE DESCRIPTION ASKS FOR (do not pad the workflow):
  - The worked examples below show CAPABILITIES, not a required template. Do NOT copy
    their review / parallel / multi-signer structure into a request that doesn't call
    for it.
  - NO REVIEW UNLESS ASKED. If the description does not mention review, approval, a
    reviewer, redlines, comments, feedback, or sending back, DO NOT add a review or
    approval step and DO NOT invent a reviewer role. A request with no reviewer has NO
    review step (and therefore no rework/send-back loop).
  - ONE SIGNER UNLESS MULTIPLE ARE NAMED. If the description implies a single signature
    (or says nothing suggesting several signers), emit exactly ONE signer — never
    parallel signing, never owner-gated handoff, never extra signer slots, never an
    invented co-signer.
  - DEFAULT UNNAMED ACTORS TO THE OWNER. When the description does not name who performs
    a step (drafts / sends / signs / acknowledges), assign that step to the OWNER via
    {{"type":"context","value":"owner_user_id"}} — do NOT pick a real IAM role at random.
    In particular the SIGNER defaults to the owner unless a different signer is named.
  - "comes back to me" / "returns to me" = a final OWNER acknowledge step (type
    "approval", module "approval", assignee owner_user_id), not a review.
  - CANONICAL SIMPLE CASE: "I draft and send for signature, the signed doc comes back to
    me" is EXACTLY: draft (owner) -> signing (single signer = owner) -> owner acknowledge
    -> done. Nothing more — no review, no second signer, no owner-gating.

A workflow is DATA: a list of `steps`, each with an `id`, a `type`, an optional
`assignee`, a `config`, and `transitions` (the arrows leaving it).
{_real_roles_block(iam_roles)}
STEP TYPES: {step_types}
  - form       : collect/edit data. config: {{"fields": [FormField, ...]}}.
  - approval   : a person approves/rejects (transitions carry action verbs).
  - signature  : a person signs.
  - decision   : automatic branch. Transitions use action "auto" with a structured
                 `condition` (or one unconditional default "auto" last).
  - parallel   : several branches open at once; advances on QUORUM. Two outgoing
                 transitions: action "quorum_met" and action "quorum_failed".
                 MIXED FAN-OUT = a parallel step whose branches have kind "notify"
                 (just informed; never gate, never need action) vs kind "action"
                 (must act; quorum is computed over ACTION branches only).
  - ordered_signing : an ORDERED signer list; only the current signer's slot is
                 open; completes via a transition with action "all_signed"
                 (optionally action "signing_declined").
  - broadcast  : notify many recipients, no action; auto-advances through its single
                 transition with action "broadcast_done".
  - terminal   : an end state; NO outgoing transitions.

ADVANCED (V2) STEP TYPES — for REAL concurrency, automation, deadlines, sub-flows.
Use them ONLY when the description calls for them (see "WHEN TO USE V2" below); a
plain step is better whenever it expresses the intent:
  - split    : open REAL parallel branches that are each a FULL SEQUENCE (their own
               steps), not just a single vote. >=2 outgoing transitions, each with
               action "auto" (add a `condition` to make a branch conditional). Every
               split is paired with a `join` downstream where the branches reconverge.
  - join     : wait for the split's branches and continue on ONE token. Provide a
               transition with action "join_met". Optional config.join =
               {{"mode": "all"|"n_of_m"|"percent", "value"?}} (default {{"mode":"all"}};
               value is a positive int for n_of_m/percent).
  - job      : an AUTOMATIC step with NO human action — generate a document/PDF, send a
               SYSTEM notification, etc. config.job = {{"kind": <REQUIRED handler name>,
               "params"?: {{...}}, "max_attempts"?: int, "output"?: {{context_key:
               "dotted.path.into.result"}}}}. `kind` MUST be one of the REGISTERED
               handlers — do NOT invent kind names:
                 * "generate_document" — generate/render a PDF or document (returns
                   {{document_path}}; map it, e.g. "output": {{"document_url":
                   "document_path"}}). Use this for any "generate the PDF/letter/report".
                 * "append_document" — ATTACH/MERGE a second document into the agreement
                   as a NEW version (e.g. append the budget / Annexure A to the CTA).
                   Use this for any "append/attach the budget", "add the annexure",
                   "merge the schedule into the agreement". params.source names WHAT to
                   attach: {{"source": {{"type": "budget"}}}} (the visit-matrix budget
                   today); optional "format": "docx" (a review-visible table baked into
                   the document — the DEFAULT for budget so it renders in the reviewed
                   doc) or "pdf" (a PDF appendix). Optional "placeholder": an
                   author-placed marker in the template like "{{ANNEXURE_A}}" — the
                   appendix is inserted AT that marker (deterministic); omit it to append
                   at the end. PLACE IT IMMEDIATELY BEFORE the signing step so the signed
                   document includes the appendix.
                 * "notify" — send a notification email (params: recipients, subject,
                   body). Use this for any "send a notification/email".
                 * "noop" — a harmless placeholder that just completes (for a step with
                   no real automation yet).
               Provide a transition with action "job_done" (and optionally "job_failed").
               NEVER emit a job step without config.job.kind.
  - wait_message : PARK until an EXTERNAL event arrives for this document. config.message
               = {{"name": <REQUIRED event name>, "output"?: {{...}}}}. Provide a transition
               with action "message_received".
  - wait_condition : HOLD until a named, REGISTERED condition becomes true, then auto-
               continue (re-checked automatically on the schedule). Use this for "wait
               until X is ready/done before <next step>" — e.g. "wait until the budget is
               finalized before signing". config.wait = {{"condition": <REGISTERED name>,
               "params"?: {{...}}, "message"?: "<status shown while waiting>"}}. Provide a
               transition with action "condition_met" to the next step. REGISTERED
               conditions you may use: "budget_ready" (the site budget is finalized). Do
               NOT invent a condition name that isn't registered — if the described
               condition has no match, OMIT the wait step and note it under "assumptions".
               To "append the budget before signing only once it's ready", author:
               … -> wait_condition(condition="budget_ready") -> job(append_document,
               source budget) -> signing.
  - call     : spawn CHILD workflow(s) and continue when enough complete. config.call =
               {{"definition_key": <REQUIRED>, "items_path"?: ..., "context_map"?: {{...}},
               "join"?: {{...}}}}. Provide a transition with action "children_done".
  - TIMER (config.timer on ANY step, not a step type): {{"seconds": <int > 0>, "action":
               <verb>}} arms a deadline; when it elapses the engine fires THAT step's
               transition whose action equals config.timer.action (escalation,
               auto-reject, reminder). The step MUST have a transition with that action.

HARD RULES (validation will reject violations):
  - Exactly one `start_step`, referencing a real step id.
  - At least one `terminal` step.
  - Every transition.to MUST reference a real step id.
  - decision steps: transitions use action "auto"; branch with a `condition` and/or
    one unconditional default.
  - parallel/fan-out: provide transitions with actions "quorum_met" AND
    "quorum_failed"; config.quorum.mode is one of all|n_of_m|percent (value is a
    positive int for n_of_m/percent); config.on_reject is fail_fast or count.
  - ordered_signing: provide a transition with action "all_signed"; config.signers
    is an ordered list.
  - broadcast: provide exactly one transition with action "broadcast_done".
  - split: at least 2 outgoing transitions (each action "auto"; optional `condition`).
  - join: provide a transition with action "join_met"; if config.join is set,
    config.join.mode is all|n_of_m|percent (value a positive int for n_of_m/percent).
  - job: config.job.kind is REQUIRED (a non-empty handler name); provide a transition
    with action "job_done" (optionally also "job_failed").
  - wait_message: config.message.name is REQUIRED; provide a transition with action
    "message_received".
  - wait_condition: config.wait.condition is REQUIRED and MUST be a registered condition
    (e.g. "budget_ready"); provide a transition with action "condition_met".
  - call: config.call.definition_key is REQUIRED; provide a transition with action
    "children_done".
  - timer: when a step has config.timer, seconds is > 0 and the SAME step has a
    transition whose action equals config.timer.action.

WHEN TO USE V2 (and when NOT to — do NOT over-reach):
  - PREFER the simple legacy steps. If a form/approval/signature/parallel/broadcast
    expresses the intent, use it — never introduce split/join/job/timer where a plain
    step suffices.
  - split/join ONLY for REAL concurrent tracks that are each a multi-step SEQUENCE
    running independently (e.g. "the legal track and the budget track each draft+review
    on their own, then merge"). For "two reviewers act at the same time and both must
    approve" (a single fan-out vote, no per-branch sequence) use a `parallel` step, NOT
    split/join.
  - `job` ONLY for steps with NO human action (generate/render a document, call an API,
    send an automatic system notification, run an AI agent). A human approval/review/
    signature is NEVER a job.
  - `timer` ONLY when the description states a deadline / escalation / auto-action after
    waiting ("escalate if no response in 2 minutes", "auto-reject after 7 days").
  - `wait_message` ONLY to wait on an external system/event; `call` ONLY to spawn
    sub-workflows. When unsure, use a plain step and note it under "assumptions".

MODULES (CRITICAL — set each step's `module` so it RUNS on the platform's capability
modules. NEVER leave a create / review / signing / notify / broadcast step untagged):
  - the document draft/create step (`form`)                            -> module "document_create"
  - a REVIEW step (a reviewer approves or sends back). ONE reviewer =
    type "approval"; SEVERAL reviewers at once that must ALL approve
    (e.g. legal + financial) = type "parallel" with action branches    -> module "review"
  - an internal approve/reject decision-to-proceed (`approval`)        -> module "approval"
  - SIGNING — see the SIGNING RULES below (always module "signing")
  - a step that only NOTIFIES parties, no gating (`approval`)          -> module "notify"
  - a tracked TWO-PARTY back-and-forth (e.g. Site Legal <-> Internal Legal coordinate
    or negotiate IN the system until resolved) = type "approval" with              -> module "discussion"
    config.discussion = {{"parties":[{{"role":"site_legal","label":"Site Legal"}},
    {{"role":"internal_legal","label":"Internal Legal"}}], "resolve":"owner"}};
    its forward transition (action e.g. "resolved") advances when the talk is resolved.
  - `broadcast`                                                        -> module "broadcast"
  - `decision`, `terminal`, `split`, `join`, `job`, `wait_message`, and `call` carry
    NO module (they are engine-level; the engine — not a capability module — runs them).
  PARALLEL steps DO carry a module: a parallel REVIEW -> "review", a parallel SIGNING
  -> "signing". Do NOT leave parallel review/signing steps untagged.

SIGNING RULES (the signing module ONLY drives type "ordered_signing" or "parallel"):
  - EVERY signing step is type "ordered_signing" (signers in a fixed order) or
    "parallel" (any order / quorum), module "signing", WITH a `config.signers`
    (ordered) or `config.branches` (parallel) list. NEVER emit a bare type
    "signature" step — the backend rejects it.
  - Sequential signing (e.g. Director then PI) = ONE `ordered_signing` step. Hand-off is
    AUTOMATIC by default — the next signer is notified the moment the previous one signs,
    no manual poke (DocuSign-style). Give EACH signer an `assignee` naming WHO signs, so
    the contact resolves up front and they are emailed automatically:
      {{"handoff":"auto","signers":[
        {{"id":"director","name":"Director","assignee":{{"type":"role","value":"site_director"}}}},
        {{"id":"pi","name":"PI","assignee":{{"type":"role","value":"pi"}}}}]}}
    Use real signer roles — pi, site_director, authorized_signatory, site_coordinator,
    sponsor — or {{"type":"user","value":"<id-or-email>"}}. A slot with NO assignee falls
    back to the owner typing the email manually. Set "handoff":"owner_gated" ONLY when the
    description explicitly wants the owner to review / act between signers.
  - Do NOT create separate "Send for X's Signature" approval steps, and do NOT split a
    signer into a send-step + a sign-step. Dispatch, recipient pick, OTP and owner-
    gating ALL live inside the signing step's config — the signing module sends.
  - "Remaining / all other signers sign together" = a `parallel` signing step
    (module "signing") with action branches, placed AFTER the ordered step.
A REVIEW step that can send back uses an "approve" exit (forward) and a "send_back"
(or per-branch "reject" for parallel) exit that returns to the draft/edit step (the
rework loop). SIGNING comes AFTER review when review gates it (review's "approve"
leads to the signing step).

AUTHORING RULES (apply to EVERY workflow — any document type, not just this example):
  - NO STANDALONE "OWNER SENDS FOR X" STEPS. Never emit an approval step like "Owner
    sends for review" / "Owner sends for signature" / "Owner sends to VP" before a
    review or signing step. Picking the recipient and sending the secure link is built
    INTO the review and signing modules — such a step is a hollow click that does no
    real work. Go straight from the prior step to the review/signing step. (ONE
    optional final owner approval gate immediately before the broadcast/distribute
    step is allowed, if a final sign-off is wanted.)
  - DISTRIBUTION IS SHARED ACROSS BRANCHES. If the finalized document is distributed,
    EVERY branch that finishes a fully-signed document must flow through the SAME single
    broadcast/distribute step before the terminal. Never give one branch its own
    terminal that skips distribution — all completion paths converge to one
    distribute -> done.
  - DECISION VARIABLES ARE ASKED AT THE DECISION. Any variable used in a `decision`
    condition MUST be declared in `context_schema` (give it the right `type` —
    boolean / number / select-with-options — so the owner gets the right input). You do
    NOT need to pre-collect it on the draft form: when the variable is unset the engine
    PAUSES at the decision step and asks the owner, then routes on the answer, so BOTH
    branches are always reachable. Only add it as a draft `form` field if you genuinely
    want it captured up-front (then the decision resolves automatically). Always give a
    decision ONE unconditional default `auto` transition last, so every answer routes.

MERMAID INPUT (when a "MERMAID DIAGRAM" is provided, read intent from it — there is
NO rigid parser; interpret it like a person would):
  - A decision node written with braces, e.g. `gate{{"Has CRO?"}}` or `gate{{Has CRO?}}`,
    becomes a `decision` step with conditional transitions (action "auto" + a
    structured `condition`, plus ONE unconditional default "auto" last).
  - One node fanning out to MANY targets that all proceed in parallel becomes a
    `parallel` step (quorum over the ACTION branches; "notify"-only targets are
    kind "notify").
  - An ORDERED signing sequence (e.g. "Director Signs -> Enable PI -> PI Signs ->
    then Remaining") becomes `ordered_signing` PRESERVING the order (Director BEFORE
    PI). A trailing "remaining / all others sign" group becomes a SEPARATE parallel
    (quorum) signing step AFTER the ordered one.
  - A node like "Returned to Main User" / "Back to Owner" is an OWNER checkpoint —
    an approval step (module "approval") whose action returns to the owner.
  - A "Distribute ... Copy" fan-out (one node -> many recipients, no action) becomes
    a `broadcast` step whose config.recipients are those targets.
  - DOTTED edges (`-.->`, often labelled "discussion"/"negotiation") are AMBIGUOUS:
    do NOT invent a hard transition for them — list them under "assumptions" (and the
    clarify step asks about them). Keep the solid-edge flow as the backbone.
The Mermaid is a HINT to the shape; the OUTPUT is still ONE valid workflow JSON.

SCHEMA (derived from the platform's Pydantic models — obey it exactly):
{_schema_text()}

WORKED EXAMPLE 1 (simple CDA):
{json.dumps(cda_example)}

WORKED EXAMPLE 2 (full CTA — parallel review, decision branch, mixed fan-out,
ordered signing, broadcast):
{json.dumps(cta_example)}

WORKED EXAMPLE 3 (review-then-sign with MODULES + the rework loop + a plain-English
summary — note the `module` on each step and review's "send_back" -> draft):
{json.dumps(REVIEW_SIGN_EXAMPLE)}

WORKED EXAMPLE 4 (V2 ADVANCED — use ONLY when the request needs it: REAL parallel
tracks that are each a full sequence via split/join, AUTOMATIC steps as `job` with
config.job.kind + output mapping, and a 2-minute escalation `timer` on the sign-off):
{json.dumps(v2_example)}

OUTPUT FORMAT — output ONLY a single JSON object, no markdown fences, no prose:
  {{"body": <WorkflowDefinitionBody>, "assumptions": ["...", "..."], "summary": "<one paragraph>"}}
- "assumptions": the concrete choices you made (roles, quorum, signing order, handoff).
- "summary": ONE plain-English paragraph describing exactly what the workflow does,
  in order (who reviews, approve/send-back, who signs and in what order, how it ends),
  so a non-technical user can confirm it before it runs.

If the user provided ANSWERS to clarifying questions, honor them EXACTLY (they
override your defaults).

If the description is too vague to build a sane flow, output INSTEAD:
  {{"needs_clarification": "<one specific question that would unblock you>"}}
"""


def _format_answers(answers: Optional[list]) -> str:
    """Render the user's clarify answers as explicit instructions the model must
    honor exactly (overriding its defaults)."""
    if not answers:
        return ""
    lines = []
    for a in answers:
        q = (a.get("question") or a.get("id") or "").strip()
        ans = str(a.get("answer", "")).strip()
        if q and ans:
            lines.append(f"- {q} -> {ans}")
    if not lines:
        return ""
    return ("\n\nThe user ANSWERED these clarifying questions — honor them EXACTLY "
            "(they override your defaults):\n" + "\n".join(lines))


def _user_prompt(description: str, key: Optional[str], name: Optional[str],
                 answers: Optional[list] = None, mermaid: Optional[str] = None) -> str:
    hints = []
    if key:
        hints.append(f'Use key "{key}".')
    if name:
        hints.append(f'Use name "{name}".')
    hint_text = (" " + " ".join(hints)) if hints else ""
    mermaid_text = (f"\n\nMERMAID DIAGRAM (interpret the intended flow from this):\n{mermaid.strip()}"
                    if mermaid and mermaid.strip() else "")
    return (f"DESCRIPTION:\n{(description or '').strip()}\n{hint_text}{mermaid_text}"
            f"{_format_answers(answers)}\n\nReturn the JSON now.")


def _refine_user_prompt(description: str, key: Optional[str], name: Optional[str],
                        mermaid: Optional[str], prior: dict,
                        feedback: str, feedback_log: Optional[list] = None) -> str:
    """The REFINE user prompt: hand the model the EXISTING definition + the user's
    change request and ask it to MODIFY that workflow (not redraft). Preserving
    everything the feedback doesn't touch is the whole point — successive rounds
    compound because `prior` is last round's result. The original description /
    mermaid / earlier feedback ride along as background context only."""
    hints = []
    if key:
        hints.append(f'Keep key "{key}".')
    if name:
        hints.append(f'Keep name "{name}" unless the change asks otherwise.')
    hint_text = (" " + " ".join(hints)) if hints else ""

    ctx_bits = []
    if description and description.strip():
        ctx_bits.append(f"Original description (context only):\n{description.strip()}")
    if mermaid and mermaid.strip():
        ctx_bits.append(f"Original Mermaid (context only):\n{mermaid.strip()}")
    earlier = [f.strip() for f in (feedback_log or []) if f and f.strip()]
    if earlier:
        ctx_bits.append("Earlier change requests already applied to the workflow below "
                        "(context only — do NOT re-apply, they are already in it):\n"
                        + "\n".join(f"  - {f}" for f in earlier))
    ctx_text = ("\n\n" + "\n\n".join(ctx_bits)) if ctx_bits else ""

    return (
        "You are REFINING an existing workflow. Below is the CURRENT workflow "
        "definition (valid JSON the user already reviewed) followed by the change "
        "they are requesting now.\n\n"
        f"CURRENT WORKFLOW (modify THIS — do not start over):\n{json.dumps(prior)}\n\n"
        f"REQUESTED CHANGE (apply ONLY this):\n{feedback.strip()}"
        f"{ctx_text}\n\n"
        "Produce the FULL updated workflow that applies the requested change while "
        "PRESERVING everything else exactly — keep every other step, transition, "
        "assignee, module, config, and the step ids stable wherever possible. Do not "
        "drop or rename unrelated steps. Re-use the same OUTPUT FORMAT "
        '({"body","assumptions","summary"}); in "assumptions" note what you changed.'
        f"{hint_text}\n\nReturn the JSON now."
    )


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        lines.append(f"{loc}: {err.get('msg', '')}".strip(": "))
    return "; ".join(lines) or str(exc)


def _repair_prompt(system_prompt: str, user_prompt: str, error: str,
                   last_obj: Optional[Any]) -> str:
    prior = json.dumps(last_obj) if last_obj is not None else "(your previous reply was not valid JSON)"
    return (
        f"{system_prompt}\n\n{user_prompt}\n\n"
        f"YOUR PREVIOUS ATTEMPT WAS INVALID.\n"
        f"Previous output: {prior}\n"
        f"Validation error: {error}\n"
        f"Fix the problem and re-emit the FULL corrected JSON object only — no fences, no prose."
    )


class NormalizeError(Exception):
    """The draft can't be safely repaired — surface as a clarifying question."""


_SIGNING_TYPES = ("ordered_signing", "parallel")
# "Owner sends for/to <review|signature|signing|VP>" — case-insensitive, plural-safe.
_SEND_STEP_RE = re.compile(r"\bsends?\s+(for|to)\b", re.IGNORECASE)

# Timer-driven transition verbs: an exit named one of these implies the engine (not a
# human) fires it on a deadline, so a step that has such an exit but no config.timer is
# repaired by attaching one. These verbs never appear in legacy (human-clicked) flows.
_TIMER_ACTIONS = {"escalate", "timeout", "auto_reject", "auto_reminder", "remind", "expire"}
# Fallback cadence when we must synthesize a timer the model forgot. The prompt teaches
# the model to emit the real duration; this only lands when it omitted config.timer.
_DEFAULT_TIMER_SECONDS = 3600

# Keyword routing for mapping an authored/invented job kind to a REAL registered
# handler (see jobs.py). Checked in order; first hit wins. Anything unmatched -> noop.
_JOB_KIND_KEYWORDS = (
    # append/attach FIRST: "append the budget annexure" must map to append_document,
    # not generate_document — these verbs are about merging an existing doc in, not
    # generating a new one.
    ("append_document", ("append", "attach", "annex", "annexure", "merge", "budget")),
    ("generate_document", ("generate", "render", "pdf", "doc", "letter", "report", "compile", "draft")),
    ("notify", ("notif", "email", "alert", "send", "remind", "mail", "message")),
)


def _canonical_job_kind(kind: str, name: str) -> str:
    """Map an authored job `kind` (possibly invented, e.g. "generate_pdf" /
    "send_notification", or blank) to a kind that ACTUALLY has a handler. If the
    kind is already registered, keep it; otherwise route by keyword over the kind
    + step name to the closest real handler; else "noop". GENERAL — any workflow."""
    try:
        from .jobs import registered_kinds
        known = registered_kinds()
    except Exception:  # noqa: BLE001 — keep generation working even if jobs import fails
        known = {"generate_document", "append_document", "notify", "noop"}
    k = (kind or "").strip().lower()
    if k and k in known:
        return k
    hay = f"{k} {(name or '').lower()}"
    for canonical, words in _JOB_KIND_KEYWORDS:
        if canonical in known and any(w in hay for w in words):
            return canonical
    return "noop" if "noop" in known else (next(iter(known), "noop"))


def _looks_like_send_step(step: dict) -> bool:
    """A standalone 'Owner sends for/to X (review / signature / VP …)' approval step.
    Owner dispatch (pick recipient + send) is built INTO the review and signing
    modules, so such a step is a hollow advance and must be folded away. GENERAL: not
    tied to any document type — matches 'send for', 'sends for', 'sends to', any case,
    referencing review/sign/signature/signing/vp."""
    if step.get("type") != "approval":
        return False
    name = step.get("name") or ""
    nl = name.lower()
    if _SEND_STEP_RE.search(name) and any(k in nl for k in ("review", "sign", "vp")):
        return True
    return ("send" in nl) and any(k in nl for k in ("review", "signature", "signing", " sign", "vp"))


def _condition_field_types(steps: list) -> dict:
    """Map each variable referenced by a `decision` condition to an inferred field
    type (boolean for is_true/is_false, number for comparisons, else text). GENERAL —
    works for ANY decision variable, not any specific one."""
    num_ops = {"gt", "gte", "lt", "lte"}
    bool_ops = {"is_true", "is_false"}
    out: dict = {}
    for s in steps:
        if s.get("type") != "decision":
            continue
        for t in s.get("transitions") or []:
            cond = t.get("condition") or {}
            for clause in (cond.get("all") or []) + (cond.get("any") or []):
                f, op = clause.get("field"), clause.get("op")
                if not f:
                    continue
                kind = "boolean" if op in bool_ops else ("number" if op in num_ops else "text")
                # boolean wins if any clause treats it as boolean (the common gate)
                out[f] = "boolean" if out.get(f) == "boolean" or kind == "boolean" else kind
    return out


def normalize_draft(body: dict) -> dict:
    """Server-side safety net BEFORE the confirm screen — repair the LLM authoring
    mistakes so generated workflows actually invoke the modules AND are reachable +
    complete. ALL rules are GENERAL (any document type, any workflow):

      1. type="signature" (rejected by the signing backend) -> ordered_signing with a
         config.signers from the step's assignee, module="signing" (+ remap exit verb).
      2. module-less steps get the right module by type/name.
      3. fold standalone "Owner sends for/to X" approval steps whose target is a REVIEW
         or SIGNING step — dispatch lives in those modules (signing target also gets
         handoff=owner_gated). A send-step before a broadcast is left alone (a final
         owner gate before distribution is allowed).
      4. unclassifiable parallel/approval -> clarifying question.
      5. DISTRIBUTION CONVERGENCE: if the flow distributes (has a broadcast step), every
         completion path must reach it — reroute any other terminal's inbound edges
         THROUGH the broadcast, then drop the orphan terminal(s).
      6. DECISION REACHABILITY: every variable used in a decision condition is declared
         in context_schema AND collected (added as a field on the draft/start form), so
         the branch can actually be taken. If nothing can collect it -> clarify.
      7. V2 TYPE REPAIRS (mirror rule 1): the LLM may reach for a V2 type but mis-wire
         its required config/transition. Backfill a `job` step's config.job.kind +
         remap its single forward arrow to "job_done"; remap a lone `join` arrow to
         "join_met"; and attach a config.timer when an escalation/timeout transition
         was authored without one. Every branch here is gated on a V2 type or a
         timer-style action that legacy flows NEVER use, so legacy generation is
         untouched."""
    steps = body.get("steps") or []

    # 1) bare signature -> ordered_signing + signers + module signing
    for s in steps:
        if s.get("type") == "signature":
            assignee = s.get("assignee") or {}
            signer = {"id": str(assignee.get("value") or s.get("id") or "signer"),
                      "name": s.get("name") or "Signer"}
            if assignee:
                signer["assignee"] = assignee
            cfg = dict(s.get("config") or {})
            cfg.setdefault("signers", [signer])
            s["type"], s["config"], s["module"] = "ordered_signing", cfg, "signing"
            for t in s.get("transitions") or []:
                if t.get("action") == "sign":
                    t["action"] = "all_signed"
                elif t.get("action") == "decline":
                    t["action"] = "signing_declined"

    # 1b) V2 type repairs — make a V2 step the LLM reached for actually valid. Gated on
    #     V2 types / timer-style actions that legacy flows never use (no legacy impact).
    for s in steps:
        stype = s.get("type")
        trs = s.get("transitions") or []
        if stype == "job":
            # Backfill / repair config.job.kind to a REGISTERED handler: fixes both
            # the missing-kind case (the "steps.kind: Field required" bug) AND an
            # invented kind like "generate_pdf"/"generate_document_x" that has no
            # handler — mapping it to a real one (generate_document / notify / noop)
            # so the authored job actually runs instead of "no handler" at runtime.
            cfg = dict(s.get("config") or {})
            job = dict(cfg.get("job") or {})
            job["kind"] = _canonical_job_kind(job.get("kind") or "", s.get("name") or "")
            cfg["job"] = job
            s["config"] = cfg
            # Ensure a job_done exit: a single forward (non-error) arrow becomes job_done.
            if not any(t.get("action") == "job_done" for t in trs):
                forward = [t for t in trs if t.get("action") != "job_failed"]
                if len(forward) == 1:
                    forward[0]["action"] = "job_done"
        elif stype == "join":
            # Ensure a join_met exit: a single outgoing arrow becomes join_met.
            if not any(t.get("action") == "join_met" for t in trs) and len(trs) == 1:
                trs[0]["action"] = "join_met"
        elif stype == "wait_condition":
            # Ensure a condition_met exit: a single outgoing arrow becomes condition_met.
            if not any(t.get("action") == "condition_met" for t in trs) and len(trs) == 1:
                trs[0]["action"] = "condition_met"
        # TIMER: an authored escalation/timeout exit with no timer to fire it -> attach
        # one (a default cadence; the prompt teaches the model to set the real seconds).
        if "timer" not in (s.get("config") or {}):
            timer_tr = next(
                (t for t in trs if t.get("action") in _TIMER_ACTIONS), None)
            if timer_tr is not None:
                cfg = dict(s.get("config") or {})
                cfg["timer"] = {"seconds": _DEFAULT_TIMER_SECONDS, "action": timer_tr.get("action")}
                s["config"] = cfg

    # 1c) BUDGET HOLD: an append_document(budget) job is NON-BLOCKING — a job always
    #     completes (job_done), so with no finalized budget it appends nothing and the
    #     agreement would proceed to signing WITHOUT the budget. Insert a
    #     wait_condition("budget_ready") immediately BEFORE each such append so the flow
    #     HOLDS until the budget is finalized, then auto-continues and appends it.
    #     Deterministic; gated on the append_document+budget source the LLM may emit
    #     without the gate (legacy/other workflows are untouched).
    def _is_budget_append(st: dict) -> bool:
        if st.get("type") != "job":
            return False
        job = (st.get("config") or {}).get("job") or {}
        if job.get("kind") != "append_document":
            return False
        src = (job.get("params") or {}).get("source") or {}
        return (src.get("type") if isinstance(src, dict) else src) == "budget"

    def _is_budget_wait(st: dict) -> bool:
        return (st.get("type") == "wait_condition"
                and ((st.get("config") or {}).get("wait") or {}).get("condition") == "budget_ready")

    existing_ids = {s.get("id") for s in steps}
    for s in list(steps):
        if not _is_budget_append(s):
            continue
        append_id = s.get("id")
        # Already gated? (a wait_condition(budget_ready) already flows into this append.)
        if any(_is_budget_wait(w) and any(t.get("to") == append_id for t in (w.get("transitions") or []))
               for w in steps):
            continue
        wait_id = f"wait_{append_id}"
        n = 1
        while wait_id in existing_ids:
            wait_id = f"wait_{append_id}_{n}"; n += 1
        existing_ids.add(wait_id)
        wait_step = {
            "id": wait_id, "type": "wait_condition", "name": "Wait for budget",
            "config": {"wait": {"condition": "budget_ready",
                                "message": "Waiting for the budget to be finalized"}},
            "transitions": [{"id": f"{wait_id}_ok", "to": append_id,
                             "label": "Budget ready", "action": "condition_met"}],
        }
        for other in steps:  # reroute predecessors of the append -> the wait
            for t in other.get("transitions") or []:
                if t.get("to") == append_id:
                    t["to"] = wait_id
        if body.get("start_step") == append_id:
            body["start_step"] = wait_id
        steps.insert(steps.index(s), wait_step)

    # 2) default/repair module by type then name (leave send-steps for the fold)
    for s in steps:
        if s.get("module"):
            continue
        t, name = s.get("type"), (s.get("name") or "").lower()
        if t == "form":
            s["module"] = "document_create"
        elif t == "ordered_signing":
            s["module"] = "signing"
        elif t == "broadcast":
            s["module"] = "broadcast"
        elif t == "parallel":
            s["module"] = "review" if "review" in name else ("signing" if "sign" in name else None)
        elif t == "approval":
            if any(k in name for k in ("discuss", "coordinat", "negotiat")):
                # A tracked two-party back-and-forth coordination step (NEED 1).
                s["module"] = "discussion"
            elif "review" in name:
                s["module"] = "review"
            elif not _looks_like_send_step(s):
                s["module"] = "approval"
        if s.get("module") is None and "module" in s:
            del s["module"]

    # 3) fold standalone "Owner sends for/to X" approval steps that lead into a REVIEW
    #    or SIGNING step (dispatch lives in those modules). Signing targets also become
    #    owner_gated. Send-steps before a broadcast are kept (final owner gate allowed).
    by_id = {s.get("id"): s for s in steps}
    for s in list(steps):
        trs = s.get("transitions") or []
        if not _looks_like_send_step(s) or len(trs) != 1:
            continue
        tgt = by_id.get(trs[0].get("to"))
        if not tgt:
            continue
        is_signing = tgt.get("type") in _SIGNING_TYPES and tgt.get("module") == "signing"
        is_review = tgt.get("module") == "review"
        if not (is_signing or is_review):
            continue
        if is_signing:
            cfg = dict(tgt.get("config") or {})
            cfg.setdefault("handoff", "owner_gated")
            tgt["config"] = cfg
        for other in steps:  # rewire predecessors -> the review/signing step
            for t in other.get("transitions") or []:
                if t.get("to") == s.get("id"):
                    t["to"] = trs[0].get("to")
        if body.get("start_step") == s.get("id"):
            body["start_step"] = trs[0].get("to")
        steps.remove(s)
        del by_id[s.get("id")]

    # 4) anything still unclassified -> ask rather than ship a broken workflow
    for s in steps:
        if not s.get("module") and s.get("type") in ("approval", "parallel"):
            raise NormalizeError(
                f"Step '{s.get('name') or s.get('id')}' is unclear — is it a REVIEW "
                f"(reviewer approves/sends back), an APPROVAL (approve/reject), or SIGNING?")

    # 5) DISTRIBUTION CONVERGENCE — every completion path goes through the broadcast.
    bcast = next((s for s in steps if s.get("type") == "broadcast"), None)
    if bcast is not None:
        bcast_to = {t.get("to") for t in (bcast.get("transitions") or [])}
        keep = {s.get("id") for s in steps if s.get("type") == "terminal" and s.get("id") in bcast_to}
        orphans = {s.get("id") for s in steps
                   if s.get("type") == "terminal" and s.get("id") not in keep and s.get("id") != bcast.get("id")}
        if orphans:
            for s in steps:  # any edge to a non-distribution terminal -> route via broadcast
                for t in s.get("transitions") or []:
                    if t.get("to") in orphans:
                        t["to"] = bcast.get("id")
            steps[:] = [s for s in steps if s.get("id") not in orphans]
            by_id = {s.get("id"): s for s in steps}

    # 6) DECISION REACHABILITY — DECLARE every decision-condition variable in
    #    context_schema (with an inferred type) so the runtime decision step can ask
    #    the owner with the right input (boolean -> Yes/No, number -> a value, …).
    #    We deliberately do NOT force-collect it on the draft form: the decision step
    #    itself is the collection point. When the variable is unset on arrival the
    #    engine PAUSES at the decision and asks, so BOTH branches stay reachable; if
    #    the author chose to collect it earlier on a form, the decision auto-resolves.
    #    GENERAL — any decision variable, any document type.
    cond_types = _condition_field_types(steps)
    if cond_types:
        schema = list(body.get("context_schema") or [])
        declared = {c.get("key") for c in schema if isinstance(c, dict)}
        for field, ftype in cond_types.items():
            if field not in declared:
                schema.append({"key": field, "label": field.replace("_", " ").title(), "type": ftype})
                declared.add(field)
        body["context_schema"] = schema

    body["steps"] = steps
    return body


async def generate_workflow(
    description: str,
    key: Optional[str] = None,
    name: Optional[str] = None,
    answers: Optional[list] = None,
    mermaid: Optional[str] = None,
    prior: Optional[dict] = None,
    feedback: Optional[str] = None,
    feedback_log: Optional[list] = None,
    iam_roles: Optional[list] = None,
    max_retries: int = MAX_REPAIR_RETRIES,
) -> dict:
    """Generate a validated DRAFT definition. Never saves or publishes.

    `iam_roles` is the real role vocabulary that exists in IAM; the model authors
    every role assignee against it (no invented role slugs).

    `answers` is the list of clarify Q&A ([{id, question, answer}]) the user confirmed;
    `mermaid` is an optional pasted flowchart the LLM interprets. Both are folded into
    the prompt and honored.

    REFINE mode: when `prior` (the previously generated definition) AND `feedback`
    (the change request) are both present, the model MODIFIES `prior` per the feedback
    instead of drafting from scratch — preserving everything the user didn't ask to
    change. `feedback_log` carries earlier rounds' requests for context so refinements
    compound. The result still flows through the SAME normalizer + validation + repair
    loop and is returned as a draft to confirm.

    Returns one of:
      {"body": <json>, "assumptions": [...], "summary": "<paragraph>"}  validated draft
      {"needs_clarification": "<question>"}        description too vague
      {"error": "<message>"}                       could not produce a valid draft
    """
    is_refine = bool(prior) and bool(feedback and feedback.strip())
    has_desc = bool(description and description.strip())
    has_mermaid = bool(mermaid and mermaid.strip())
    # A refine round must carry a change request (check before the generic empty
    # guard so the message is specific to refining).
    if bool(prior) and not (feedback and feedback.strip()):
        return {"error": "Describe the change you want to make to this workflow."}
    if not is_refine and not has_desc and not has_mermaid:
        return {"error": "Describe the workflow you want (or paste a Mermaid diagram)."}

    system_prompt = build_system_prompt(iam_roles)
    if is_refine:
        user_prompt = _refine_user_prompt(description, key, name, mermaid, prior, feedback, feedback_log)
    else:
        user_prompt = _user_prompt(description, key, name, answers, mermaid)
    prompt = f"{system_prompt}\n\n{user_prompt}"
    last_error: Optional[str] = None

    for attempt in range(max_retries + 1):
        parsed = await _llm_generate_json(prompt)

        if parsed is None or not isinstance(parsed, dict):
            last_error = "Response was not a valid JSON object."
            prompt = _repair_prompt(system_prompt, user_prompt, last_error, None)
            continue

        # Vague-input escape hatch — terminal, no repair.
        if parsed.get("needs_clarification"):
            return {"needs_clarification": str(parsed["needs_clarification"])}

        body_raw = parsed.get("body")
        if not isinstance(body_raw, dict):
            last_error = "JSON is missing the required 'body' object."
            prompt = _repair_prompt(system_prompt, user_prompt, last_error, parsed)
            continue

        # Apply explicit key/name overrides before validation so they persist.
        if key:
            body_raw["key"] = key
        if name:
            body_raw["name"] = name

        # NORMALIZE: repair the common module/type mistakes so the workflow actually
        # invokes the modules (signature->ordered_signing, missing modules, stray
        # send-steps). If it can't be safely repaired, ask instead of shipping broken.
        try:
            body_raw = normalize_draft(body_raw)
        except NormalizeError as exc:
            return {"needs_clarification": str(exc)}

        try:
            body = WorkflowDefinitionBody.model_validate(body_raw)
        except ValidationError as exc:
            last_error = _format_validation_error(exc)
            logger.info("generate_workflow: validation failed (attempt %d): %s", attempt + 1, last_error)
            prompt = _repair_prompt(system_prompt, user_prompt, last_error, body_raw)
            continue

        assumptions = parsed.get("assumptions") or []
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]
        summary = parsed.get("summary")
        body_json = body.model_dump(mode="json")
        # Persist the authoring prompt inside the draft body so approve → publish
        # carries it into the saved version (and history/clone can prefill it).
        # Refine rounds keep the ORIGINAL prompt the workflow was first authored
        # from, if the prior draft carried one.
        prompt_text = (description or "").strip()
        if is_refine and isinstance(prior, dict) and (prior.get("source_prompt") or "").strip():
            prompt_text = str(prior["source_prompt"]).strip()
        if prompt_text:
            body_json["source_prompt"] = prompt_text
        return {
            "body": body_json,
            "assumptions": [str(a) for a in assumptions],
            "summary": str(summary).strip() if summary else _fallback_summary(body),
        }

    return {
        "error": (
            f"Could not generate a valid workflow after {max_retries + 1} attempts. "
            f"Last validation error: {last_error}"
        )
    }


def _fallback_summary(body: WorkflowDefinitionBody) -> str:
    """Deterministic plain-English summary from the validated body, used when the
    model omitted "summary". Lists the steps in flow order with their role."""
    role = {
        "form": "a draft step", "approval": "an approval/review step",
        "signature": "a signature", "ordered_signing": "ordered signing",
        "parallel": "a parallel review", "broadcast": "a broadcast",
        "decision": "an automatic decision", "terminal": "completion",
    }
    bits = []
    for s in body.steps:
        t = s.type.value if hasattr(s.type, "value") else str(s.type)
        bits.append(f"{s.name} ({role.get(t, t)})")
    return "This workflow runs: " + " → ".join(bits) + "."


# ===========================================================================
# CLARIFY — structured questions about the few things that change SHAPE/behavior.
# ===========================================================================
# Canonical catalog. The model only decides WHICH of these the description leaves
# ambiguous; the question text + options are fixed here so the UI is stable and the
# behavior is testable. ids are stable contract values.
CLARIFY_CATALOG: dict[str, dict] = {
    "review_vs_signing": {
        "question": "Should review happen BEFORE signing, or should review and signing run in PARALLEL?",
        "options": ["Review before signing (sequential)", "Review and signing in parallel"],
    },
    "signers": {
        "question": "Who signs, how many signers, and in what order?",
        "options": ["One signer", "Two signers in sequence (specify the order)",
                    "Multiple signers in parallel (any order)"],
    },
    "signing_handoff": {
        "question": "Between sequential signers, should it AUTO-continue to the next signer, "
                    "or return to the owner between each (owner-gated)?",
        "options": ["Auto-continue to the next signer", "Owner-gated (return to owner between signers)"],
    },
    "who_sends": {
        "question": "Who can send for review / send for signature?",
        "options": ["The creator/owner (default)", "A specific role (name it)"],
    },
    "reject_loop": {
        "question": "On reviewer rejection, should it go back to draft for edits (rework loop)?",
        "options": ["Yes — send back to draft for edits", "No — end/abort on rejection"],
    },
}

# Trigger words that make a catalog clarify-question RELEVANT. The clarify step must
# never inject concerns the user didn't raise — no review questions when there is no
# reviewer, no multi-signer questions when a single signature is implied, no rework-loop
# question when rejection was never mentioned, no who-sends question when the owner
# obviously sends. Each catalog id is GATED on a trigger actually present in the user's
# words; absent the trigger the question is dropped. This is a hard guarantee that sits
# on top of the model's own judgment (the model can only ever ask a SUBSET of these).
_REVIEW_TRIGGERS = (
    "review", "reviewer", "approval", "approve", "approver", "sign off", "sign-off",
    "redline", "red-line", "comment", "feedback", "revision", "revise", "markup",
    "mark up", "send back", "sends back", "sent back", "send-back", "sendback",
    "reject", "rejection", "rework",
)
_MULTI_SIGNER_TRIGGERS = (
    "signers", "two sign", "2 sign", "three sign", "multiple sign", "several sign",
    "both sign", "co-sign", "cosign", "countersign", "counter-sign", "second signer",
    "second sign", "each signer", "each sign", "signing order", "order of sign",
    "sign in order", "sign in sequence", "sequential sign", "parallel sign",
    "signers in", "more than one sign", "additional signer", "other signer",
    "multiple signator",
)
_OTHER_SENDER_TRIGGERS = (
    "who sends", "who can send", "who should send", "who may send", "anyone can send",
    "coordinator send", "manager send", "specialist send", "assistant send",
    "delegate", "on my behalf", "someone else send", "a role sends",
)


def _relevant_clarify_ids(description: Optional[str], mermaid: Optional[str] = None) -> set[str]:
    """The catalog clarify ids ALLOWED for this request — each gated on a trigger
    actually present in the user's words. Absent the trigger the question is dropped,
    so clarify only ever asks about what the user genuinely mentioned: it never invents
    a review step, extra signers, a rework loop, or a non-owner sender."""
    text = f"{description or ''} {mermaid or ''}".lower()
    allowed: set[str] = set()
    if any(k in text for k in _REVIEW_TRIGGERS):
        allowed.update(("review_vs_signing", "reject_loop"))
    if any(k in text for k in _MULTI_SIGNER_TRIGGERS):
        allowed.update(("signers", "signing_handoff"))
    if any(k in text for k in _OTHER_SENDER_TRIGGERS):
        allowed.add("who_sends")
    return allowed


async def _llm_clarify_json(prompt: str) -> Optional[dict]:
    """Swappable seam for the clarify call (tests monkeypatch this); same client."""
    from app.config import settings
    from app.integrations.ai.client import AIClient

    client = AIClient(model_name=settings.workflow_generation_model)
    return await client.generate_json(prompt)


MAX_CLARIFY_QUESTIONS = 8


def build_clarify_prompt(description: str, mermaid: Optional[str] = None) -> str:
    catalog_lines = "\n".join(f'  - {qid}: {q["question"]}' for qid, q in CLARIFY_CATALOG.items())
    mermaid_block = ""
    extra_rules = ""
    if mermaid and mermaid.strip():
        mermaid_block = f"\nMERMAID DIAGRAM the user pasted (interpret it like a person):\n{mermaid.strip()}\n"
        extra_rules = (
            "\nBecause a MERMAID DIAGRAM was given, ALSO return diagram-specific questions in "
            '"extra_questions" (each {"id","question","options":[...]}) — but ONLY for things the '
            "diagram leaves genuinely unresolved, such as:\n"
            "  - which nodes are SIGNING vs REVIEW vs APPROVAL,\n"
            "  - who each role maps to (the assignee for a node),\n"
            "  - CONFIRM the signature ORDER you read from the diagram (e.g. Director before PI),\n"
            "  - how to model any DOTTED 'discussion'/'negotiation' edges.\n"
            "Ask nothing the diagram already makes clear. Use short, specific questions.\n"
        )
    return f"""You analyze a workflow request for a clinical-trial document platform and decide
which aspects are GENUINELY AMBIGUOUS — things that change the SHAPE or behavior of the
workflow and that the request does NOT already make clear.

Consider this fixed catalog of clarifying questions (by id):
{catalog_lines}

Rules:
  - Return in "ambiguous_ids" the catalog ids whose answer is NOT already clear.
  - Treat the catalog as CONDITIONAL, NOT a checklist. NEVER introduce a concern the
    user did not raise. Gate each id on the user's ACTUAL words:
      * review_vs_signing, reject_loop -> ONLY if the request mentions review,
        approval, a reviewer, redlines, comments, feedback, or sending back. NO
        reviewer mentioned = there is NO review step, so ask NOTHING about review or
        rework.
      * signers, signing_handoff -> ONLY if the request implies MORE THAN ONE signer,
        or an unclear signing order among several signers. One implied signature (or
        nothing suggesting multiple) -> ask NOTHING about signer count/order/handoff;
        the single signer simply defaults to the owner.
      * who_sends -> ONLY if the request suggests someone OTHER than the owner sends.
        "I send" / "I draft and send" / owner sends -> skip it.
  - Do NOT include an id the request already resolves (e.g. it names the single signer).
  - If the request is a clear, simple flow (e.g. "I draft and send for signature, it
    comes back to me"), return EMPTY lists — ask ZERO questions.
{extra_rules}
DESCRIPTION:
{(description or "").strip()}
{mermaid_block}
Output ONLY a single JSON object, no markdown, no prose:
  {{"ambiguous_ids": ["..."], "extra_questions": [{{"id": "...", "question": "...", "options": ["...", "..."]}}]}}
"""


async def clarify_workflow(description: str, mermaid: Optional[str] = None) -> dict:
    """Step 1 — return STRUCTURED clarifying questions for the genuinely-ambiguous,
    shape-changing aspects of the request (description and/or a pasted `mermaid`
    diagram), or an empty list when it is clear enough.

    Returns: {"questions": [{"id", "question", "options": [...]}], "clear": bool}.
    Catalog questions come from CLARIFY_CATALOG; when a mermaid is given the model may
    also return diagram-specific free-form questions (sanitized + capped here).
    Never raises and never blocks: on any model/parse problem it returns no questions
    (the caller then generates a draft with explicit assumptions). The LLM here only
    CLASSIFIES ambiguity; it writes nothing and runs nothing."""
    if not (description and description.strip()) and not (mermaid and mermaid.strip()):
        return {"questions": [], "clear": True}

    try:
        parsed = await _llm_clarify_json(build_clarify_prompt(description, mermaid))
    except Exception:  # noqa: BLE001 — clarify is best-effort; fall through to no-questions
        logger.exception("clarify_workflow: model call failed")
        parsed = None

    questions: list[dict] = []
    seen: set[str] = set()

    # Hard relevance gate: only catalog ids whose trigger appears in the user's words
    # are allowed, so clarify can never inject a concern the user didn't raise (review,
    # extra signers, rework loop, non-owner sender). The model can only narrow this set.
    allowed_ids = _relevant_clarify_ids(description, mermaid)

    if isinstance(parsed, dict):
        # 1) catalog ids (stable text + options)
        for x in parsed.get("ambiguous_ids") or []:
            qid = str(x)
            if qid in CLARIFY_CATALOG and qid in allowed_ids and qid not in seen:
                seen.add(qid)
                questions.append({"id": qid, "question": CLARIFY_CATALOG[qid]["question"],
                                  "options": list(CLARIFY_CATALOG[qid]["options"])})
        # 2) diagram-specific free-form questions (only meaningful with a mermaid)
        for q in parsed.get("extra_questions") or []:
            if not isinstance(q, dict):
                continue
            qtext = str(q.get("question") or "").strip()
            if not qtext:
                continue
            qid = (str(q.get("id") or "").strip() or f"diagram_{len(questions)}")
            if qid in seen:
                continue
            opts_raw = q.get("options")
            opts = [str(o) for o in opts_raw if str(o).strip()] if isinstance(opts_raw, list) else []
            seen.add(qid)
            questions.append({"id": qid, "question": qtext, "options": opts[:6]})
            if len(questions) >= MAX_CLARIFY_QUESTIONS:
                break

    return {"questions": questions, "clear": len(questions) == 0}
