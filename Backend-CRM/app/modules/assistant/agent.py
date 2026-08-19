"""Assistant turn runner + tool-calling loop.

Flow: build a provider agent-session with the whitelisted tools -> send the user
message -> for each tool call the model makes, validate args and invoke the real
route AS THE USER (guards run) -> feed results back -> repeat until a final text
answer or the hard iteration cap. Read commands auto-execute; write/regulated
gating arrives in CP2.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.modules.assistant.blocks import build_blocks, build_summary_blocks
from app.modules.assistant.commands import Command, DEFAULT_SCREENS, REGISTRY, Risk
from app.modules.assistant.confirmations import confirmations
from app.modules.assistant.docs import get_feature_docs
from app.modules.assistant.invoker import InvocationResult, invoke_command
from app.modules.assistant.providers import ToolResult, create_agent_session
from app.modules.assistant.session import hub
from app.modules.assistant.tools import build_tool

logger = logging.getLogger(__name__)

# Hard cap on tool-call rounds per turn — prevents runaway loops / cost.
MAX_TOOL_ROUNDS = 5

# How long a pending write/regulated action waits for user approval.
CONFIRM_TIMEOUT_SECONDS = 300

# Cap list results fed back to the model so a large payload can't blow the
# context / cost. The model is told when results were truncated.
_MAX_LIST_ITEMS = 25

_SYSTEM_BASE = (
    "You are Orbit, a capable operations teammate embedded in the Study Operations "
    "CRM — a sharp, trustworthy colleague who gets things done for the user, not a "
    "chatbot. Speak naturally, plainly, and warmly: be concise and confident, never "
    "stiff, robotic, or corporate. But do NOT act beyond what the user asked, infer "
    "unstated goals, or volunteer unrelated actions — your value is being reliable "
    "and honest, not chatty or presumptuous. You act on behalf of the logged-in user. "
    "When the user asks about their data (tasks, "
    "studies, conversations), call the appropriate tool to fetch it, then answer "
    "concisely from the real result. Never invent data. If a tool result is an "
    "error or access-denied, tell the user plainly that they don't have access "
    "or that it failed — do not pretend to know the answer. "
    "To act on a specific task or agreement, first look it up (e.g. list_my_tasks) "
    "to get its id if you don't already have it. "
    "You cannot apply e-signatures; you can only send an agreement for signature, "
    "which emails a link for the human signer to sign themselves.\n\n"
    "CLASSIFY EACH REQUEST:\n"
    "1. NAVIGATION — 'open X', 'go to X', 'take me to X', 'show me the X screen', "
    "'navigate to X'. This is an ACTION: move the user there via navigate_to. "
    "NEVER answer a navigation request with manual click-by-click / how-to steps. "
    "Match the user's words (and aliases) to a screen in the SCREEN CATALOG below. "
    "If nothing matches, say plainly you can't open that screen — do NOT fall back "
    "to how-to steps or offer an unrelated tool.\n"
    "   Each catalog screen lists the context it needs (none / study / study+site). "
    "Resolve required study/site IN THIS ORDER:\n"
    "     a) CURRENT CONTEXT — if the needed study/site is already selected (see the "
    "'current screen' line), use its id; do not ask.\n"
    "     b) MATCH — if the user named a study/site, call list_studies (and "
    "list_study_sites for a site) and match by name (e.g. 'breast cancer' -> "
    "'Breast Cancer DP'). If exactly one matches, use its id.\n"
    "     c) ASK — if still missing or MORE THAN ONE matches, call present_choices "
    "with the accessible studies/sites as options and STOP (wait for the pick). "
    "Never guess. Make each option's message a full instruction, e.g. 'Open "
    "agreements for Breast Cancer DP'.\n"
    "   Only ever use studies/sites returned by list_studies / list_study_sites (the "
    "user's entitled set). Once all required params are known, call navigate_to with "
    "screen + study_id/site_id. If a named study/site isn't in the user's set, say "
    "so with show_notice — never invent one.\n"
    "1b. GUIDED TOUR / DEMO / HOW-TO — 'show me around X', 'give me a tour of X', "
    "'walk me through the X screen', 'show me a demo of X', 'demo X', AND how-to "
    "questions like 'how do I create a budget?', 'how to set up a monitoring visit?'. "
    "Call start_tour with the matching tour id from the GUIDED TOURS list (read-only; "
    "on-screen highlights + narration — always prefer this over a text answer, it "
    "shows the user exactly where to click). Every navigable screen has a screen tour "
    "(orientation-first: it shows WHERE the screen lives before navigating), and "
    "common workflows have how_to_* tours (e.g. 'how do I add a site' -> "
    "how_to_add_site, 'demo of IRB' -> irb_administrative_info, 'tour the whole app' "
    "-> app_overview). Match the topic to the closest id/alias. Only if nothing in "
    "the list is even close, answer with help_answer instead.\n"
    "   CAPABILITY QUESTIONS ARE NOT TOUR REQUESTS — 'what can you do (for me)?', "
    "'what can you help with?', 'help', 'what are your features?': answer with "
    "help_answer (a short summary of what you can do here), setting "
    "offer_label='Take a tour' / offer_message='give me a tour of the app' so the "
    "user can OPT IN. NEVER call start_tour for these — a tour takes over the "
    "user's screen, so it must only start when the user EXPLICITLY asked to be "
    "shown around / walked through / given a demo. Mentioning or offering a tour "
    "in your answer is not a reason to start one.\n"
    "1c. OPEN A SPECIFIC RECORD — 'open the CDA_with_sig template', 'open the agreement "
    "for Site A', 'open Subject 111', 'open this'. Identify the entity type from the "
    "ENTITY CATALOG (by aliases). Then RESOLVE it (entitlement-scoped): call that "
    "entity's search command (study/site auto-apply from context), match by the user's "
    "name/qualifier. Exactly one match -> call open_entity(entity_type, id). More than "
    "one -> present_choices with the matches (each message like 'open <name>'). None / "
    "not accessible -> show_notice ('I couldn't find a <type> matching …'). If the entity "
    "type isn't in the catalog (e.g. subjects) -> show_notice honestly (offer its list "
    "screen via navigate_to if one exists). 'open this/that/it' -> use the record on the "
    "current screen; if the context doesn't identify one, ask which.\n"
    "1d. CREATE / ACT ON A RECORD — 'create an agreement', 'create a task'. If a create "
    "command exists for that entity, use it (confirmation + audit; regulated where "
    "applicable — never auto-sign). If NO create command exists, say so specifically and "
    "OFFER to open the create screen via navigate_to — never fabricate the create.\n"
    "1e. FILL A FORM (live over-the-shoulder loop) — 'fill in a new task with …', 'fill "
    "this form with …', 'populate the task form'. If the target form is in FILLABLE "
    "FORMS, call fill_form with that form id and the field key/value pairs you derive "
    "from the user's request (map their words to the listed field keys; use only those "
    "keys). You FILL fields ONLY — you NEVER submit, save, or sign. "
    "VISIBLE-ONLY LOOP: check 'FORM ON SCREEN NOW' — fill ONLY the fields listed as "
    "visible now. If the user asked for values that map to fields NOT visible (they're "
    "under 'not visible' — off-screen or on a later step), fill what IS visible, then ask "
    "the user to scroll to / open the step with those fields and say 'continue' — then "
    "STOP and wait. On their continue, re-check what's visible and fill the rest. After "
    "filling, tell the user to review and click the form's submit button THEMSELVES (that "
    "is what saves it); NEVER say you created / saved / submitted it. If the form isn't in "
    "FILLABLE FORMS (e.g. a signing or agreement form), do NOT fill it — say so honestly. "
    "If the form isn't open on screen, tell them to open it first.\n"
    "2. HOW-TO / HELP — 'how do I…', 'how does X work', 'where do I find…'. Answer "
    "using the Feature Documentation below, aware of the user's current screen. "
    "Do NOT treat a navigation request as a how-to question.\n"
    "2b. EXPLAIN / SUMMARIZE THIS SCREEN — 'explain this screen', 'what's on this "
    "screen', 'summarize this page', 'what am I looking at'. Call read_screen — it "
    "returns ONLY what is currently VISIBLE on the user's screen (rendered viewport "
    "content, like looking over their shoulder — never hidden data, never a backend "
    "fetch). Answer from that visible content OPERATIONALLY, obeying SENSITIVE-DETAIL "
    "RESTRAINT (no subject / patient / site identifiers in your prose). OVER-THE-"
    "SHOULDER LOOP: if fully answering needs content that isn't visible (more_below / "
    "more_above is true, or it's clearly one page of more), summarize what you can see "
    "NOW, then ask the user to scroll / open the tab / expand the panel to reveal the "
    "rest and say 'continue' — then STOP and wait. When they reply (e.g. 'continue'), "
    "read_screen again for the newly-visible content and carry on. If read_screen "
    "returns readable=false, say honestly you can't read what's on this screen and ask "
    "them to make it visible — do NOT substitute a tasks / studies summary, and do NOT "
    "fetch from the backend. (Only pull backend/underlying data if the user EXPLICITLY "
    "asks for the full/underlying dataset — that is a separate deep-read.)\n"
    "   CONTINUE SIGNAL: if the user's message is a short continuation like 'continue', "
    "'more', 'go on', 'next', 'keep going', 'show me the rest', or 'I've scrolled' (they "
    "just scrolled / revealed more after you asked), RESUME WHAT YOU WERE JUST DOING — "
    "don't ask what they mean: (a) if you were reading / summarizing the screen, call "
    "read_screen for the now-visible content; (b) if you were FILLING A FORM (you asked "
    "them to reveal more fields), call fill_form for the fields now shown as visible in "
    "FORM ON SCREEN NOW, reusing the values the user already gave you earlier (you "
    "remember them from the conversation). Use whether a form is on screen (FORM ON "
    "SCREEN NOW) to tell which case you're in.\n"
    "2c. DEEP-READ (full underlying data) — ONLY when the user EXPLICITLY asks for the "
    "full / underlying dataset: 'give me all 20 pages', 'pull the full dataset', 'show me "
    "everything / all the rows', 'fetch the underlying data'. Call deep_read — it goes to "
    "the real backend route and returns what that route allows (it may be denied; report "
    "that honestly). Present it OPERATIONALLY (SENSITIVE-DETAIL RESTRAINT still applies). "
    "This is the ONLY path that fetches from the backend. Never use deep_read for a plain "
    "'summarize/explain this screen' — that stays on-screen (read_screen). If unsure "
    "which they want, default to the on-screen read.\n\n"
    "OFFER DISCIPLINE & HONESTY: Only offer a tool when it directly serves what "
    "the user actually asked. Never attach an unrelated offer (e.g. don't offer a "
    "budget template on a navigation request). When you lack a capability, state "
    "that plainly — never substitute an adjacent how-to and present it as if it "
    "fulfilled the request.\n"
    "CONSISTENCY: never say you can't do something and then do it in the same reply; "
    "if you can do it, just do it. Never present duplicate or redundant option chips.\n"
    "HONESTY ABOUT CAPABILITIES: you have tools to create tasks, update tasks, create "
    "conversations, post messages in a conversation, transition agreements, send an "
    "agreement for signature, create/approve budgets, and navigate. If the user asks "
    "for one of these, DO IT (via the tool + confirmation) — never claim you can't and "
    "never tell the user to 'go do it themselves on the screen'. Only state a limitation "
    "if it is REAL and SPECIFIC (e.g. 'I can post a message in an existing conversation "
    "but can't delete one yet') — never a generic false refusal.\n\n"
    "HISTORY DISCIPLINE — earlier turns are context, not content: prior messages in "
    "this session exist ONLY so you can resume an in-progress activity (a 'continue' "
    "after a screen read, values the user already gave you mid-fill, a follow-up about "
    "YOUR immediately preceding answer). NEVER re-answer, re-summarize, or resurface a "
    "previous turn's topic in a new turn that didn't ask about it. If an earlier "
    "question looks unanswered in the history, assume it WAS answered — many answers "
    "are delivered as on-screen cards/blocks that don't appear in this history — and do "
    "NOT answer it again. A navigation request ('open X', 'take me to X') gets ONLY the "
    "navigation and a one-line confirmation — never content carried over from an "
    "earlier topic.\n\n"
    "VOICE — how to sound: Write like a helpful human colleague — natural sentences, "
    "plain words, no enterprise jargon. Prefer 'I couldn't find…' over 'operation "
    "failed'; 'that's outside your access' over 'access denied / unauthorized'. When "
    "something fails, is denied, or you can't do it, STILL say so honestly and "
    "specifically — the honesty rules above are absolute — just phrase it "
    "conversationally and, where you can, say why. Examples: access denied -> 'That "
    "agreement belongs to another study team, so I can't open it from your account.'; "
    "not found -> 'I couldn't find a template called \"X\" in this study — want me to "
    "open the Template Library so you can check?'; missing capability -> 'I can post a "
    "message in an existing conversation, but I can't delete one yet.' Softening the "
    "wording must NEVER soften the truth: never hide an error, denial, or limitation "
    "to sound friendlier, and never imply something worked when it didn't.\n\n"
    "DATA TRUTH — never contradict, outrun, or embellish the data:\n"
    "- Assert ONLY facts that appear in a tool result you actually fetched THIS turn, or "
    "in the current-screen context you were given. If you did not fetch a fact — a "
    "status, a count, a date, an owner — do NOT state it. Say you'd need to look it up, "
    "or simply omit it. NEVER invent a status label the data did not return, and never "
    "assign a status to a record that contradicts the status the data DID return.\n"
    "- Report ONLY the fields the data returned; do NOT editorialize or infer meaning "
    "beyond them. NEVER characterize a record from its NAME or id — no 'this suggests…', "
    "'appears to be…', 'representing completed work', 'sequential placeholders', and no "
    "guessing a phase, purpose, or lifecycle from a title. A record's status is exactly "
    "the returned status field and nothing more: do not translate 'archived' into "
    "'completed work' or read a story into it (an archived study may still be one the "
    "user actively works in — don't imply it's defunct, especially if it's their "
    "selected/current context).\n"
    "- If there is little to synthesize, say that in one short honest line — do NOT pad "
    "the answer with invented narrative, characterizations, or implications the data "
    "doesn't support. Under-claim rather than guess.\n\n"
    "SENSITIVE-DETAIL RESTRAINT — keep prose operational:\n"
    "- Your free-text narrative stays OPERATIONAL: counts, priorities, what needs "
    "attention first, groupings, and duplicates. Do NOT reproduce subject-level clinical "
    "specifics in prose — no subject ids, patient or site ids, patient-signature status, "
    "visit numbers tied to a subject, diagnoses, or named individuals tied to clinical "
    "detail. That content already appears in the structured record cards (access-checked, "
    "exactly where the app itself shows it) — leave it there; do not restate it in prose. "
    "Example: write 'two critical ICF items need attention' — NOT 'Subject 111 is missing "
    "a patient signature on the ICF for Visit #62'. Category-level, not identifiers.\n\n"
    "READ INTENT — classify every data request first:\n"
    "- BROWSE ('show / list / fetch / pull up / top N my tasks') → call the read with "
    "view='cards'. Records render as interactive cards automatically; do NOT re-list "
    "them in prose (one line or a next step is enough).\n"
    "- SYNTHESIZE ('summarize / summary / overview / analyze / how many / what's "
    "urgent / breakdown') → call the read with view='summary' and NO status/limit "
    "filters (fetch the full set). Totals + a grouped breakdown + a 'show all' chip "
    "are shown for you; then write a COMPACT synthesized narrative that REASONS over "
    "the data — surface what needs attention first (Critical/overdue), notable "
    "groupings (status, severity, assignee), and flag likely DUPLICATE items "
    "(near-identical titles). Do NOT dump cards and do NOT restate the counts. Keep the "
    "narrative OPERATIONAL and free of subject-level clinical specifics (see "
    "SENSITIVE-DETAIL RESTRAINT): say WHAT needs attention and WHY at a category level, "
    "never individual patient / subject / site identifiers — those stay in the cards.\n"
    "- NAVIGATE-ONLY ('open / go to / take me to X') → navigate; give a short "
    "confirmation + optional next-step chips. Do NOT also fetch and dump that "
    "screen's records as chat cards.\n"
    "- COMBINED ('open X and summarize') → navigate AND synthesize (view='summary'); "
    "still no card dump.\n\n"
    "RESPONSE BLOCKS — compose with rich blocks instead of walls of text:\n"
    "- Disambiguation / next steps / offers: call present_choices with tappable "
    "options instead of listing them in prose (e.g. 'Which study?'). An 'offer to "
    "act' is a choice too.\n"
    "- How-to / help questions: call help_answer with the doc-grounded answer; set "
    "offer_label/offer_message when you can perform it with a tool.\n"
    "- Limits / errors / access-denied / 'can't do that': call show_notice.\n"
    "- Charts / graphs / visualisations ('make a chart', 'plot this', proportions, "
    "comparisons, trends): call show_chart with the numeric points (bar = compare "
    "categories, donut = parts of a whole, line = trend). NEVER draw a chart in "
    "text — no ASCII art, no pipe/box drawings, no emoji bars; if you have the "
    "numbers, show_chart is the ONLY way to chart them.\n"
    "When you call present_choices, show_notice, help_answer, or show_chart, that "
    "IS your response — do not also write separate prose."
)


def _format_catalog(catalog: Optional[list]) -> str:
    """Render the frontend's screen catalog for the prompt."""
    if not catalog:
        return ""
    lines = []
    for entry in catalog:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        aliases = entry.get("aliases") or []
        alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
        requires = entry.get("requires") or "none"
        lines.append(f"- {entry['name']}{alias_str} — needs: {requires}")
    return "\n".join(lines)


def _format_tours(tours: Optional[list]) -> str:
    if not tours:
        return ""
    lines = []
    for t in tours:
        if not isinstance(t, dict) or not t.get("id"):
            continue
        aliases = t.get("aliases") or []
        alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
        lines.append(f"- {t['id']}{alias_str} — {t.get('label', t['id'])}")
    return "\n".join(lines)


def _format_entities(entities: Optional[list]) -> str:
    if not entities:
        return ""
    lines = []
    for e in entities:
        if not isinstance(e, dict) or not e.get("type"):
            continue
        aliases = e.get("aliases") or []
        alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
        opens = "opens the record" if e.get("openable") == "record" else "opens its screen"
        search = f"; search via {e['search']}" if e.get("search") else "; no search"
        create = f"; create via {e['create']}" if e.get("create") else "; no create command"
        lines.append(f"- {e['type']}{alias_str} — {opens}{search}{create}")
    return "\n".join(lines)


def _format_forms(forms: Optional[list]) -> str:
    if not forms:
        return ""
    lines = []
    for f in forms:
        if not isinstance(f, dict) or not f.get("id"):
            continue
        aliases = f.get("aliases") or []
        alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
        fields = f.get("fields") or []
        field_str = "; ".join(
            f"{fld.get('key')}: {fld.get('label')} [{fld.get('type')}]"
            for fld in fields if isinstance(fld, dict) and fld.get("key")
        )
        submit = f.get("submit_label") or "Submit"
        lines.append(f"- {f['id']}{alias_str} — fields: {field_str}. (User submits via '{submit}'.)")
    return "\n".join(lines)


def _format_form_view(form_view: Optional[list]) -> str:
    """Live on-screen form state: which fields are visible now vs off-screen."""
    if not form_view:
        return ""
    lines = []
    for f in form_view:
        if not isinstance(f, dict) or not f.get("id"):
            continue
        vis = ", ".join(f.get("visible_fields") or []) or "(none)"
        hid = ", ".join(f.get("hidden_fields") or []) or "(none)"
        lines.append(f"- {f['id']} ({f.get('label', f['id'])}): visible now = {vis}; not visible (scroll / later step) = {hid}")
    return "\n".join(lines)


def _build_system(
    screen: Optional[str],
    catalog: Optional[list] = None,
    tours: Optional[list] = None,
    entities: Optional[list] = None,
    memory_block: Optional[str] = None,
    forms: Optional[list] = None,
    form_view: Optional[list] = None,
) -> str:
    parts = [_SYSTEM_BASE]
    # Derived memory (preferences / working patterns) injected compactly so Orbit
    # adapts to the user. Empty for a fresh user → no block → no fake familiarity.
    if memory_block:
        parts.append(memory_block)
    catalog_str = _format_catalog(catalog)
    if catalog_str:
        parts.append(
            "\n# SCREEN CATALOG (the only screens you can open with navigate_to)\n"
            + catalog_str
        )
    tours_str = _format_tours(tours)
    if tours_str:
        parts.append(
            "\n# GUIDED TOURS (the only tours you can run with start_tour; read-only)\n"
            + tours_str
        )
    entities_str = _format_entities(entities)
    if entities_str:
        parts.append(
            "\n# ENTITY CATALOG (record types you can find + open with open_entity)\n"
            + entities_str
        )
    forms_str = _format_forms(forms)
    if forms_str:
        parts.append(
            "\n# FILLABLE FORMS (the only forms you can fill with fill_form; FILL only, "
            "never submit/save/sign)\n" + forms_str
        )
    form_view_str = _format_form_view(form_view)
    if form_view_str:
        parts.append(
            "\n# FORM ON SCREEN NOW (live, THIS turn) — authoritative visibility\n"
            "When filling, target EXACTLY the fields under 'visible now' (using the values "
            "the user gave). Do NOT (re)fill fields under 'not visible' — they're off-screen "
            "or on a later step and will be skipped; ask the user to reveal them and "
            "continue. On a 'continue' after you asked them to reveal more, fill the fields "
            "that are 'visible now' THIS turn (not the ones you already did).\n"
            + form_view_str
        )
    parts.append(f"\n# User's current screen\n{screen or 'unknown'}")
    docs = get_feature_docs()
    if docs:
        parts.append(f"\n# Feature Documentation (source of truth for how-to answers)\n{docs}")
    return "\n".join(parts)


def _summarize_result(status_code: int, data: Any, ok: bool) -> Dict[str, Any]:
    """Shape a route response into a compact dict for the model."""
    if not ok:
        return {
            "status": status_code,
            "error": data if isinstance(data, (str, dict, list)) else str(data),
        }
    payload: Dict[str, Any] = {"status": status_code}
    if isinstance(data, list):
        payload["count"] = len(data)
        payload["items"] = data[:_MAX_LIST_ITEMS]
        if len(data) > _MAX_LIST_ITEMS:
            payload["truncated"] = True
    else:
        payload["data"] = data
    return payload


def _fallback_message(last_exec: Optional[tuple], hit_cap: bool) -> str:
    """Honest closing line for a turn that would otherwise end silently.

    Never claims success it can't stand behind: each branch states only what the
    last tool outcome actually established. This is the never-silent guarantee —
    every turn ends with an answer or an honest limit."""
    if hit_cap:
        return (
            "I hit my step limit before I could finish that, so I stopped. "
            "Nothing further was changed — try asking again, a bit more specifically."
        )
    if last_exec:
        name, outcome = last_exec
        out = outcome if isinstance(outcome, dict) else {}
        if name == "read_screen" and not out.get("readable", True):
            return (
                "I couldn't read this screen — it may still be loading. "
                "Give it a moment and ask me again."
            )
        if name == "navigate_to" and out.get("status") == "navigated":
            screen = str(out.get("screen") or "that screen").replace("_", " ")
            return f"Done — I've opened {screen}."
        if name == "open_entity" and out.get("status") == "opened":
            return "Done — I've opened it."
        if out.get("status") == "cancelled_by_user":
            return "Cancelled — nothing was done."
        if isinstance(out.get("reason"), str) and out["reason"].startswith("Confirmation timed out"):
            return "That confirmation timed out, so nothing was done. Ask again when you're ready."
        if out.get("error") is not None:
            return (
                "That didn't go through — the last step failed, so I stopped rather "
                "than guess. Nothing was changed."
            )
    return "I couldn't put together an answer for that one — mind rephrasing or asking again?"


def apply_context(command: Command, args: Dict[str, Any], context: Optional[dict]) -> Dict[str, Any]:
    """Fill a command's scope args (study/site) from the caller's current context
    when the model didn't supply them. Explicit model values always win. Central,
    per `command.context_params` ({context_key -> arg_name})."""
    if not command.context_params or not context:
        return args
    out = dict(args)
    for ctx_key, arg_name in command.context_params.items():
        if not out.get(arg_name) and context.get(ctx_key):
            out[arg_name] = context[ctx_key]
    return out


def _describe_action(command: Command, args: Dict[str, Any]) -> str:
    """Human-readable summary shown in the confirmation card. Regulated actions
    are spelled out explicitly (what will and won't happen)."""
    if command.name == "create_task":
        title = args.get("title") or (args.get("description") or "").strip()[:80] or "Untitled task"
        text = f'Create a task: "{title}"'
        if args.get("dueDate"):
            text += f" (due {args['dueDate']})"
        if args.get("assigneeId"):
            text += f", assigned to {args['assigneeId']}"
        return text
    if command.name == "create_conversation":
        where = f" in site {args['site_id']}" if args.get("site_id") else ""
        return f'Start a new conversation "{args.get("subject")}"{where}.'
    if command.name == "send_conversation_message":
        body = (args.get("body") or "")[:100]
        channel = args.get("channel") or "email"
        return f'Send a {channel} message in conversation {args.get("conversation_id")}: "{body}"'
    if command.name == "update_task":
        bits = [f"{k}={v}" for k, v in args.items() if k != "task_id"]
        return f'Update task {args.get("task_id")}: {", ".join(bits) or "(no changes)"}'
    if command.name == "transition_agreement_status":
        return (
            f'Change agreement {args.get("agreement_id")} status to '
            f'{args.get("status")}. Only transitions the workflow permits will apply.'
        )
    if command.name == "send_agreement_for_signature":
        signer = args.get("site_signer_email") or "the site signer on file"
        return (
            f'REGULATED ACTION — Send agreement {args.get("agreement_id")} for e-signature. '
            f'This will EMAIL a secure signing link to {signer}. '
            f'It will NOT apply any signature on your or anyone else\'s behalf, and it '
            f'cannot bypass the required signing order — the human signer must sign themselves.'
        )
    if command.name == "create_budget_template":
        return (
            f'Create a budget template "{args.get("name")}" for study/trial '
            f'{args.get("trial_id")}'
            + (f', site {args["site_id"]}' if args.get("site_id") else "")
            + f' ({args.get("target_currency_code", "USD")}).'
        )
    if command.name == "set_budget_status":
        return (
            f'REGULATED ACTION — Set budget template {args.get("template_id")} status to '
            f'"{args.get("status")}". Approving/executing a budget is a controlled change '
            f'and will be recorded.'
        )
    return f"Run {command.name} with {args}"


async def _audit_agent_action(
    actor_user_id: Optional[str], command: Command, args: Dict[str, Any], res: InvocationResult
) -> None:
    """Uniform bot-action audit for every successful write/regulated command.

    Some routes audit natively (e.g. create_task, message_created) and those rows
    are already provenance-stamped via the header/ContextVar. This adds a single
    guaranteed AuditLog row per bot mutation regardless of the route's own audit,
    so a bot action is never audit-exempt (21 CFR Part 11)."""
    from app import crud
    from app.db import AsyncSessionLocal

    target_id = None
    if isinstance(res.data, dict):
        target_id = res.data.get("id")
    if not target_id:
        target_id = next((str(v) for k, v in args.items() if k.endswith("_id") and v), "n/a")
    try:
        async with AsyncSessionLocal() as session:
            await crud.create_audit_log(
                session,
                user=str(actor_user_id) if actor_user_id else None,
                action=f"assistant.{command.name}",
                target_type=command.name,
                target_id=str(target_id),
                details={"via": "agentic_assistant", "command": command.name, "args": args},
            )
    except Exception:  # noqa: BLE001 — never let audit failure break the turn
        logger.exception("agent-side audit failed for %s", command.name)


async def _read_current_screen(
    key: str,
    mode: Optional[str],
    screen_view: Optional[dict],
    actor_user_id: Optional[str],
) -> Dict[str, Any]:
    """Live ON-SCREEN read (over-the-shoulder): Orbit sees ONLY what the user
    currently sees — the rendered, VISIBLE viewport text the frontend captured.
    NEVER a backend fetch, never the DOM's hidden parts or fetched-but-unshown
    data. If the visible content isn't enough, the model asks the user to scroll /
    open the tab / expand the panel and say 'continue' (explicit handshake), then
    reads the newly-visible content on the next turn. Leaking is impossible on this
    path because Orbit only ever receives what is on screen."""
    view = screen_view or {}
    text = (view.get("text") or "").strip()
    more_below = bool(view.get("more_below"))
    more_above = bool(view.get("more_above"))
    hub.emit(key, {"type": "step", "command": "read_screen", "risk": Risk.READ,
                   "label": "Reading what's on screen…"})
    hub.emit(key, {"type": "step_result", "command": "read_screen",
                   "status": "ok" if text else "empty"})

    if not text:
        return {
            "readable": False, "screen": mode,
            "_ui_note": (
                "You could see NO readable text on the current screen (it may be an "
                "embedded editor / iframe, an image, or a data-heavy screen that is "
                "STILL LOADING — the capture already waited and retried once). Tell the "
                "user honestly you couldn't read what's on this screen yet: if it's "
                "likely still loading, say so and ask them to give it a moment and ask "
                "again; otherwise ask them to make the content visible (switch to the "
                "right tab / open the panel) and say 'continue'. Do NOT fetch from the "
                "backend and do NOT substitute another summary. You MUST reply with this "
                "honest message — never end the turn without telling the user."
            ),
        }
    return {
        "readable": True, "screen": mode,
        "visible_text": text[:6000],
        "more_below": more_below, "more_above": more_above,
        "_ui_note": (
            "The visible_text above is ONLY what is currently on the user's screen "
            "(rendered viewport text — NOT a backend fetch, NOT hidden DOM). Answer the "
            "user's question from THIS visible content, OPERATIONALLY, obeying "
            "SENSITIVE-DETAIL RESTRAINT (no subject / patient / site identifiers in your "
            "prose). If answering fully needs content that ISN'T in this visible text — "
            "more_below/more_above is true and they asked about the whole thing, or it's "
            "clearly one page of more — then: summarize what you CAN see now, ask the user "
            "to scroll (or open the tab / expand the panel) to reveal the rest and say "
            "'continue', then STOP and wait. NEVER invent unseen content, and NEVER fetch "
            "from the backend here (a full/underlying-data pull is a separate explicit "
            "request)."
        ),
    }


async def _deep_read_screen(
    key: str, mode: Optional[str], context: Optional[dict], bearer_token: Optional[str]
) -> Dict[str, Any]:
    """Explicit deep-read: fetch the current screen's underlying data via its REAL
    route (inherits the route's own access rules — no Orbit-side entitlement gate).
    Only reached when the user explicitly asks for the full/underlying dataset."""
    from app.modules.assistant.deep_read import deep_read

    hub.emit(key, {"type": "step", "command": "deep_read", "risk": Risk.READ,
                   "label": "Pulling the full underlying data…"})
    result = await deep_read(mode, context, bearer_token)
    hub.emit(key, {"type": "step_result", "command": "deep_read",
                   "status": "ok" if result.get("available") else "unavailable"})
    if result.get("available"):
        result["_ui_note"] = (
            "This is the FULL underlying data from the real backend route (the user "
            "explicitly asked for it; it inherits the route's own access rules). Present "
            "it OPERATIONALLY, obeying SENSITIVE-DETAIL RESTRAINT (no subject / patient / "
            "site identifiers in prose — aggregates and what stands out). If some "
            "endpoints were denied (denied_endpoints) or unavailable, say so honestly. If "
            "study_selected is false, tell them to pick a study first."
        )
    else:
        result["_ui_note"] = (
            "There is no backend deep-read route for this screen. Tell the user honestly "
            "you can't pull underlying data for this screen; do not substitute another "
            "summary."
        )
    return result


async def _execute(
    key: str,
    command: Command,
    args: Dict[str, Any],
    bearer_token: Optional[str],
    actor_user_id: Optional[str],
    mode: Optional[str] = None,
    context: Optional[dict] = None,
    screen_view: Optional[dict] = None,
    emitted: Optional[dict] = None,
) -> Dict[str, Any]:
    # Live on-screen read: sees ONLY the rendered/visible content the frontend
    # captured for this turn — no backend fetch, not a single route, not a
    # frontend event. Handled before the normal invoke path.
    if command.name == "read_screen":
        return await _read_current_screen(key, mode, screen_view, actor_user_id)

    # Explicit deep-read: fetch the underlying data via the real route (route-governed).
    if command.name == "deep_read":
        return await _deep_read_screen(key, mode, context, bearer_token)

    # Frontend command: no HTTP route — emit an SSE block/event the browser acts
    # on. Harmless (presentation / moving the user's own view) so auto-run + unaudited.
    if command.frontend:
        return _run_frontend_command(key, command, args, emitted)

    # `view` is a rendering hint, not a route param — pull it out before calling.
    view = args.pop("view", "cards")

    verb = "Fetching" if command.risk == Risk.READ else "Running"
    hub.emit(key, {
        "type": "step",
        "command": command.name,
        "risk": command.risk,
        "label": f"{verb} {command.name.replace('_', ' ')}…",
    })
    res = await invoke_command(command, args, bearer_token=bearer_token)
    hub.emit(key, {"type": "step_result", "command": command.name, "status": res.status_code})
    # Audit every successful mutation (writes + regulated) with bot provenance.
    if command.risk != Risk.READ and res.ok:
        await _audit_agent_action(actor_user_id, command, args, res)

    # Attach blocks for successful reads. Browse -> record cards; summary ->
    # totals + grouped breakdown (+ a 'show all' chip), NO cards.
    if command.risk == Risk.READ and res.ok:
        if view == "summary":
            data_blocks = build_summary_blocks(command.name, res.data)
        else:
            data_blocks = build_blocks(command.name, res.data)
        for block in data_blocks:
            hub.emit(key, {"type": "block", "block": block})
        if data_blocks:
            # Data blocks ARE a user-visible answer (cards/summary) even with no
            # trailing prose — record that so the never-silent fallback stands down,
            # and leave a stub for the history buffer (stale-bleed fix).
            if emitted is not None:
                emitted["visible"] = True
                emitted["note"] = (
                    f"(answered with on-screen {command.name.replace('_', ' ')} "
                    f"{'summary' if view == 'summary' else 'cards'})"
                )
            summary = _summarize_result(res.status_code, res.data, res.ok)
            if view == "summary":
                summary["_ui_note"] = (
                    "A totals + grouped breakdown and a 'show all' chip were ALREADY shown. "
                    "Do NOT list records, do NOT repeat the counts, do NOT add choices. Write "
                    "only a COMPACT synthesized narrative: what needs attention first (Critical / "
                    "overdue), notable groupings, and flag likely DUPLICATE items (near-identical "
                    "titles). A few sentences max. "
                    "OPERATIONAL ONLY — this is mandatory: do NOT put any subject id, patient or "
                    "site id, visit number, or named individual into your prose; those specifics "
                    "already appear in the cards, so describe CATEGORIES (e.g. 'several critical "
                    "ICF-signature tasks'), never identities (never 'Subject 111', 'Visit #62', a "
                    "site code, or a person's name). Assert ONLY statuses and facts the data "
                    "returned — do NOT invent a status ('archived'/'completed') or infer meaning, "
                    "phase, or purpose from a record's NAME. If there is little to synthesize, say "
                    "so in one honest line instead of padding with invented narrative."
                )
            else:
                summary["_ui_note"] = (
                    "These records were already shown as interactive cards. Do NOT list them "
                    "again — at most a one-line summary or a suggested next step."
                )
            return summary

    return _summarize_result(res.status_code, res.data, res.ok)


def _run_frontend_command(
    key: str, command: Command, args: Dict[str, Any], emitted: Optional[dict] = None
) -> Dict[str, Any]:
    """Execute a frontend-only command by emitting the SSE block/event it maps to."""
    name = command.name
    # These produce something the user SEES in the console (a block, or — for
    # fill_form / start_tour — a frontend-rendered notice / visible tour overlay),
    # so the never-silent fallback need not add anything. navigate_to/open_entity
    # are deliberately NOT here: they move the view without a chat answer, so if
    # the model adds no prose the fallback supplies an honest one-liner.
    if emitted is not None and name in (
        "present_choices", "show_notice", "help_answer", "fill_form", "start_tour",
        "show_chart",
    ):
        emitted["visible"] = True
    if name == "open_entity":
        entity_type = args.get("entity_type")
        entity_id = args.get("id")
        hub.emit(key, {"type": "step", "command": name, "risk": command.risk,
                       "label": f"Opening {str(entity_type).replace('_', ' ')}…"})
        hub.emit(key, {"type": "open_entity", "entity_type": entity_type, "id": entity_id})
        hub.emit(key, {"type": "step_result", "command": name, "status": "ok"})
        return {"status": "opened", "entity_type": entity_type, "id": entity_id}
    if name == "start_tour":
        tour = args.get("tour")
        hub.emit(key, {"type": "step", "command": name, "risk": command.risk, "label": f"Starting tour: {tour}…"})
        hub.emit(key, {"type": "demo", "mode": "tour", "recipe": tour})
        hub.emit(key, {"type": "step_result", "command": name, "status": "ok"})
        return {"status": "tour_started", "recipe": tour}
    if name == "navigate_to":
        screen = args.get("screen")
        hub.emit(key, {"type": "step", "command": name, "risk": command.risk,
                       "label": f"Opening {str(screen).replace('_', ' ')}…"})
        # study_id/site_id (if resolved) are selected by the frontend before it
        # navigates. Selection is navigation-class (the destination screen still
        # enforces its own access) — no confirmation, no audit.
        hub.emit(key, {
            "type": "navigate",
            "screen": screen,
            "study_id": args.get("study_id"),
            "site_id": args.get("site_id"),
        })
        hub.emit(key, {"type": "step_result", "command": name, "status": "ok"})
        return {"status": "navigated", "screen": screen}
    if name == "fill_form":
        form = args.get("form")
        fields = args.get("fields") or []
        hub.emit(key, {"type": "step", "command": name, "risk": command.risk,
                       "label": f"Filling the {str(form).replace('_', ' ')} form…"})
        # Emit the fill event; the frontend resolves each field key -> its data-testid
        # and populates the real on-screen field. It NEVER submits/saves/signs.
        hub.emit(key, {"type": "fill_form", "form": form, "fields": fields})
        hub.emit(key, {"type": "step_result", "command": name, "status": "ok"})
        return {
            "status": "form_filled", "form": form, "field_count": len(fields),
            "_ui_note": (
                "You populated the on-screen form fields ONLY — you did NOT submit, save, "
                "or sign anything. Tell the user briefly to review the filled form and "
                "click its submit button themselves to save (their click runs the guarded, "
                "audited route). NEVER claim you created / saved / submitted it. If the form "
                "wasn't open, the fields won't have filled — then tell them to open it first."
            ),
        }
    if name == "present_choices":
        options = [{"label": str(o), "message": str(o)} for o in (args.get("options") or [])]
        hub.emit(key, {"type": "block", "block": {
            "type": "choice_chips", "question": args.get("question"), "options": options}})
        return {"status": "shown", "_ui_note": "Choices shown as tappable chips; do not repeat them in prose."}
    if name == "show_notice":
        hub.emit(key, {"type": "block", "block": {
            "type": "notice", "kind": args.get("kind", "info"), "message": args.get("message", "")}})
        return {"status": "shown", "_ui_note": "Notice shown to the user; no further prose needed."}
    if name == "help_answer":
        offer = None
        if args.get("offer_label"):
            offer = {"label": args["offer_label"], "message": args.get("offer_message") or args["offer_label"]}
        hub.emit(key, {"type": "block", "block": {
            "type": "help_answer", "markdown": args.get("markdown", ""), "offer": offer}})
        return {"status": "shown", "_ui_note": "Help answer shown to the user; no further prose needed."}
    if name == "show_chart":
        points = [
            {"label": str(p.get("label", "")), "value": p.get("value"), "tone": p.get("tone")}
            for p in (args.get("points") or [])
            if isinstance(p, dict)
        ]
        hub.emit(key, {"type": "block", "block": {
            "type": "chart", "kind": args.get("kind", "bar"), "title": args.get("title"),
            "unit": args.get("unit"), "points": points}})
        return {
            "status": "shown",
            "_ui_note": (
                "A real themed chart was rendered for the user. Add at most one short "
                "takeaway sentence — do NOT restate the numbers and NEVER draw an "
                "ASCII/text version of the chart."
            ),
        }
    return {"status": "error", "error": f"unhandled frontend command '{name}'"}


async def _confirm_and_execute(
    key: str,
    command: Command,
    args: Dict[str, Any],
    bearer_token: Optional[str],
    actor_user_id: Optional[str],
    emitted: Optional[dict] = None,
) -> Dict[str, Any]:
    """Gate a write/regulated command behind explicit user approval."""
    description = _describe_action(command, args)
    pending = confirmations.create(
        owner_key=key,
        command_name=command.name,
        args=args,
        risk=command.risk,
        description=description,
    )
    # The confirmation card is a user-visible response in its own right.
    if emitted is not None:
        emitted["visible"] = True
    hub.emit(key, {"type": "block", "block": {
        "type": "confirmation",
        "token": pending.token,
        "command": command.name,
        "risk": command.risk,
        "description": description,
        # Presentational: lets the card show the real approval window counting
        # down. The authoritative timeout stays server-side (asyncio.wait_for).
        "expires_in": CONFIRM_TIMEOUT_SECONDS,
    }})
    # Engine-agnostic wait: local Future or Redis BLPOP (multi-worker safe).
    approved = await confirmations.wait(pending, timeout=CONFIRM_TIMEOUT_SECONDS)
    if approved is None:
        await confirmations.discard(pending.token)
        hub.emit(key, {"type": "step_result", "command": command.name, "status": "timeout"})
        return {"status": "not_performed", "reason": "Confirmation timed out; nothing was done."}

    if not approved:
        hub.emit(key, {"type": "step_result", "command": command.name, "status": "cancelled"})
        return {"status": "cancelled_by_user", "reason": "The user declined; nothing was done."}

    return await _execute(key, command, args, bearer_token, actor_user_id, emitted=emitted)


async def _buffer_turn_safe(user_id: str, session_id: str, role: str, text: str) -> None:
    """Buffer one raw turn without ever letting a failure surface into the turn."""
    try:
        from app.modules.assistant.memory import repository as memory_repo

        await memory_repo.buffer_turn(user_id, session_id, role, text)
    except Exception:  # noqa: BLE001
        logger.exception("assistant memory: buffer_turn_safe failed")


async def run_turn(
    key: str,
    user_text: str,
    *,
    bearer_token: Optional[str],
    screen: Optional[str] = None,
    catalog: Optional[list] = None,
    context: Optional[dict] = None,
    tours: Optional[list] = None,
    entities: Optional[list] = None,
    mode: Optional[str] = None,
    forms: Optional[list] = None,
    screen_view: Optional[dict] = None,
    form_view: Optional[list] = None,
) -> None:
    """Run one assistant turn, streaming step/token/confirmation/done events over SSE."""
    # key is "{user_id}:{session_id}" — the acting user for audit attribution.
    actor_user_id = key.split(":", 1)[0] or None
    session_id = key.split(":", 1)[1] if ":" in key else key

    # Live evals (feature-flagged, DEFAULT OFF): arm the per-turn event tap so
    # the finished turn can be scored AFTER the answer. Recording only — the
    # turn itself is never blocked or altered; scheduling happens in the
    # finally below via the app's fire-and-forget create_task pattern.
    turn_started_at = datetime.now(timezone.utc)
    try:
        from app.modules.assistant.live_eval import service as live_eval_service

        live_eval_service.start_recording(key)
    except Exception:  # noqa: BLE001 — live evals must never touch the turn
        live_eval_service = None  # type: ignore[assignment]
        logger.exception("live-eval start_recording failed (turn unaffected)")

    # Load a short rolling history of THIS session's prior turns BEFORE buffering
    # the current message, so multi-turn continuations (screen-read 'continue',
    # fill 'fill the rest') keep context. Best-effort.
    history: list = []
    if actor_user_id:
        try:
            from app.modules.assistant.memory import repository as memory_repo

            history = await memory_repo.recent_session_turns(actor_user_id, session_id, limit=6)
        except Exception:  # noqa: BLE001
            logger.exception("assistant: recent-session-turns load failed")

    # Buffer the user's message into the raw turn store (best-effort, off-path).
    # This is the distiller's food + the "last time you…" recap source; it is a
    # short-TTL buffer, never a permanent transcript.
    if actor_user_id:
        await _buffer_turn_safe(actor_user_id, session_id, "user", user_text)

    # Load the user's derived memory (one read) and inject it. Study-reference
    # context items are entitlement-gated elsewhere (welcome-back); per turn we
    # pass no entitled set, so any study-scoped context item is conservatively
    # withheld rather than risk surfacing a lost-access study.
    memory_block = ""
    if actor_user_id:
        try:
            from app.modules.assistant.memory import service as memory_service

            memory_block = await memory_service.build_prompt_block(actor_user_id)
        except Exception:  # noqa: BLE001 — memory is best-effort; never break a turn
            logger.exception("assistant memory: prompt-block load failed")
    # Screen names / tour ids / entity types come from the frontend's registries;
    # navigate_to / start_tour / open_entity are constrained to exactly these.
    # A turn without a catalog falls back to DEFAULT_SCREENS so navigate_to's
    # enum is NEVER unconstrained.
    screen_names = [e["name"] for e in (catalog or []) if isinstance(e, dict) and e.get("name")]
    screen_names = screen_names or list(DEFAULT_SCREENS)
    tour_ids = [t["id"] for t in (tours or []) if isinstance(t, dict) and t.get("id")]
    entity_types = [e["type"] for e in (entities or []) if isinstance(e, dict) and e.get("type")]
    form_ids = [f["id"] for f in (forms or []) if isinstance(f, dict) and f.get("id")]
    try:
        session = create_agent_session(
            system=_build_system(screen, catalog, tours, entities, memory_block, forms, form_view),
            tool=build_tool(
                screen_names=screen_names or None,
                tour_ids=tour_ids or None,
                entity_types=entity_types or None,
                form_ids=form_ids or None,
            ),
            history=history or None,
        )
        turn = await session.send_user(user_text)

        # Terminal presentation blocks (help/notice/choices) ARE the response —
        # suppress any trailing model prose so we don't append junk after them.
        _TERMINAL = {"help_answer", "show_notice", "present_choices"}
        suppress_final = False
        # Never-silent bookkeeping: did anything user-visible reach the console,
        # what did the last tool actually do, and which prose was streamed early.
        emitted: Dict[str, Any] = {"visible": False, "note": None}
        last_exec: Optional[tuple] = None
        interleaved: list = []
        # Chat-visible text of terminal blocks — buffered as the assistant's reply
        # so seeded history never shows an unanswered question (stale-bleed fix).
        terminal_texts: list = []

        rounds = 0
        while turn.tool_calls and rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            # Text accompanying a tool-call round used to be dropped; stream it so
            # the model's narration is never lost (part of the never-silent fix).
            round_text = (turn.text or "").strip()
            if round_text:
                hub.emit(key, {"type": "token", "text": round_text})
                interleaved.append(round_text)
                emitted["visible"] = True
            results = []
            for call in turn.tool_calls:
                command = REGISTRY.get(call.name)
                if command is None:
                    results.append(ToolResult(call, {"error": f"unknown command '{call.name}'"}))
                    last_exec = (call.name, {"error": "unknown command"})
                    continue

                try:
                    validated = command.input_model(**(call.args or {})).model_dump(
                        exclude_none=True
                    )
                except Exception as exc:  # noqa: BLE001
                    results.append(ToolResult(call, {"error": f"invalid arguments: {exc}"}))
                    last_exec = (call.name, {"error": "invalid arguments"})
                    continue

                # Only a VALID terminal call suppresses the final prose (an invalid
                # one never rendered a block, so the prose must still flow).
                if call.name in _TERMINAL:
                    suppress_final = True
                    if call.name == "help_answer":
                        terminal_texts.append(str(validated.get("markdown") or "").strip())
                    elif call.name == "show_notice":
                        terminal_texts.append(str(validated.get("message") or "").strip())
                    elif call.name == "present_choices":
                        q = str(validated.get("question") or "").strip()
                        opts = ", ".join(str(o) for o in (validated.get("options") or []))
                        terminal_texts.append(
                            (q + (f" (offered choices: {opts})" if opts else "")).strip()
                        )

                # Central context threading: fill scope-dependent args (study/site)
                # from the caller's current context when the model didn't supply
                # them — so results match the on-screen data by default.
                validated = apply_context(command, validated, context)

                # Read auto-executes; write/regulated requires explicit confirmation.
                if command.risk == Risk.READ:
                    outcome = await _execute(
                        key, command, validated, bearer_token, actor_user_id,
                        mode=mode, context=context, screen_view=screen_view,
                        emitted=emitted,
                    )
                else:
                    outcome = await _confirm_and_execute(
                        key, command, validated, bearer_token, actor_user_id,
                        emitted=emitted,
                    )

                last_exec = (call.name, outcome)
                results.append(ToolResult(call, outcome))

            turn = await session.send_tool_results(results)

        # The model still wanted more tool calls when the round cap cut it off.
        hit_cap = bool(turn.tool_calls) and rounds >= MAX_TOOL_ROUNDS

        # Narration is optional — blocks may already carry the whole answer. But a
        # turn must NEVER end silently: if nothing user-visible was produced (or the
        # cap cut the work short), close with an honest line instead of just 'done'.
        final = (turn.text or "").strip()
        fallback: Optional[str] = None
        if suppress_final:
            pass  # the terminal block carries the response
        elif final:
            hub.emit(key, {"type": "token", "text": final})
        # Honest close needed when the cap cut work short (even mid-sentence), or
        # when absolutely nothing user-visible was produced this turn.
        if hit_cap or (not suppress_final and not final and not emitted["visible"]):
            fallback = _fallback_message(last_exec, hit_cap)
            hub.emit(key, {"type": "token", "text": fallback})
        hub.emit(key, {"type": "done"})

        # Buffer what the user actually GOT this turn as the assistant's reply
        # (best-effort). Terminal-block text, streamed prose, the honest fallback,
        # or a data-blocks stub — so the next turn's seeded history shows every
        # question answered and never resurfaces it as a new topic.
        if suppress_final:
            reply_text = " ".join(t for t in terminal_texts if t).strip()
        else:
            prose = " ".join([*interleaved, final]).strip()
            reply_text = prose or fallback or (emitted.get("note") or "")
        if actor_user_id and reply_text:
            await _buffer_turn_safe(actor_user_id, session_id, "assistant", reply_text)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
        logger.exception("assistant run_turn failed")
        hub.emit(key, {"type": "error", "message": str(exc)})
    finally:
        # Live evals: pop the tap and fire-and-forget the scorer (sampled,
        # flag-gated inside). Guarded so a scoring bug can never surface here.
        try:
            if live_eval_service is not None:
                live_eval_service.finish_turn(
                    key=key,
                    user_id=actor_user_id,
                    session_id=session_id,
                    user_text=user_text,
                    screen_view=screen_view,
                    started_at=turn_started_at,
                )
        except Exception:  # noqa: BLE001
            logger.exception("live-eval finish_turn failed (turn unaffected)")
