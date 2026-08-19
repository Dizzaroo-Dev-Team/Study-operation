"""Command registry — the assistant's action whitelist.

The model can ONLY invoke commands registered here; it cannot hit arbitrary
URLs or run raw SQL/DB. Each command maps 1:1 to an existing HTTP route and
carries the route's inputs as a Pydantic model (which the tool-declaration
generator turns into a function declaration for the model).

``risk`` drives the confirmation gate (added in CP2):
  * read      — auto-executes.
  * write     — requires explicit user confirmation before the route is called.
  * regulated — like write, but the confirmation is spelled out; e-signatures
                never auto-fire and sequential-signing rules are never bypassed.

CP1 registers read commands only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Type

from pydantic import BaseModel, Field


class Risk:
    READ = "read"
    WRITE = "write"
    REGULATED = "regulated"


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    method: str          # HTTP verb, e.g. "GET" / "POST"
    path_template: str   # e.g. "/api/tasks" or "/api/conversations/{conversation_id}"
    risk: str
    input_model: Type[BaseModel]
    # How non-path params are encoded for write routes: "json" (Pydantic body,
    # the default) or "form" (application/x-www-form-urlencoded, for routes whose
    # params are declared with fastapi.Form(...), e.g. send-for-signature).
    body_encoding: str = "json"
    # Frontend-only command: not an HTTP route. The agent "executes" it by
    # emitting an SSE event the browser acts on (e.g. navigate_to). It never
    # touches the invoker, needs no route, and (like reads) is auto-run + unaudited.
    frontend: bool = False
    # Central context threading: {context_key -> arg_name}. Before invoking, the
    # agent fills these args from the caller's current study/site context when the
    # model didn't supply them — so scope-dependent commands match the on-screen
    # data by default (context keys: "study_id", "site_id"). One shared mechanism,
    # not per-command patches.
    context_params: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Input models — mirror each route's existing query/path parameters. Only the
# fields we want the model to be able to set are exposed.
# ---------------------------------------------------------------------------

class GetTaskInput(BaseModel):
    task_id: str = Field(..., description="The id of the task to fetch.")


# --- Presentation blocks the model authors (frontend-only; no route) ---

class PresentChoicesInput(BaseModel):
    question: Optional[str] = Field(None, description="Optional prompt shown above the choices.")
    options: list[str] = Field(
        ..., min_length=1, description="Tappable options; tapping one sends it as the next message."
    )


class ShowNoticeInput(BaseModel):
    kind: Literal["info", "warning", "error"] = Field(
        "info", description="Notice severity for styling."
    )
    message: str = Field(..., description="The message to show.")


class ChartPointInput(BaseModel):
    label: str = Field(..., description="Category / bucket name, e.g. 'Enrolled'.")
    value: float = Field(..., description="Numeric value for this point.")
    tone: Optional[Literal["success", "warning", "error", "info", "neutral"]] = Field(
        None,
        description="Optional semantic color: 'warning' for at-risk, 'error' for failed, 'success' for healthy.",
    )


class ShowChartInput(BaseModel):
    kind: Literal["bar", "donut", "line"] = Field(
        "bar",
        description=(
            "'bar' compares categories, 'donut' shows parts of a whole "
            "(e.g. enrolled vs screen-failed), 'line' shows a trend over time."
        ),
    )
    title: Optional[str] = Field(None, description="Short chart title, e.g. 'Screened population'.")
    unit: Optional[str] = Field(None, description="Unit for the values, e.g. 'subjects'.")
    points: list[ChartPointInput] = Field(
        ..., min_length=1, max_length=12, description="The data points, in display order."
    )


class HelpAnswerInput(BaseModel):
    markdown: str = Field(..., description="The doc-grounded help answer, in markdown.")
    offer_label: Optional[str] = Field(
        None, description="If you can perform the action, the label of an offer button, e.g. 'Create it for me'."
    )
    offer_message: Optional[str] = Field(
        None, description="The message sent as the next turn when the offer button is tapped."
    )


# view controls how a read renders: "cards" = record cards (browse); "summary" =
# a synthesized answer + a grouped breakdown (no card wall). For "summary" do NOT
# apply filters — fetch the full set so totals are correct.
_VIEW_DESC = (
    "Rendering intent. Use 'cards' for browse ('show/list/fetch') — renders record "
    "cards. Use 'summary' for synthesize ('summarize/overview/how many/what's "
    "urgent/breakdown') — renders a grouped breakdown, not cards; when using "
    "'summary' do NOT set status/limit filters (fetch everything so totals are right)."
)


class ListMyTasksInput(BaseModel):
    view: Literal["cards", "summary"] = Field("cards", description=_VIEW_DESC)
    status: Optional[str] = Field(
        None, description="Filter by task status, e.g. 'open' or 'closed'. Omit for summaries."
    )
    role: Optional[str] = Field(
        None, description="Filter by the role a task is assigned to."
    )
    limit: int = Field(
        100, ge=1, le=500, description="Maximum number of tasks to return."
    )


class ListStudiesInput(BaseModel):
    view: Literal["cards", "summary"] = Field("cards", description=_VIEW_DESC)


class ListStudySitesInput(BaseModel):
    study_id: str = Field(..., description="The study id whose accessible sites to list.")


class ListMyConversationsInput(BaseModel):
    view: Literal["cards", "summary"] = Field("cards", description=_VIEW_DESC)
    study_id: Optional[str] = Field(
        None, description="Filter conversations by study id."
    )
    site_id: Optional[str] = Field(
        None, description="Filter conversations by site id."
    )
    limit: int = Field(
        50, ge=1, le=100, description="Maximum number of conversations to return."
    )


class CreateTaskInput(BaseModel):
    title: Optional[str] = Field(None, description="Short task title.")
    description: Optional[str] = Field(None, description="Task details / what needs doing.")
    status: str = Field("open", description="One of: open, in-progress, done, cancelled.")
    dueDate: Optional[str] = Field(
        None, description="Due date in ISO format, e.g. 2026-07-03."
    )
    assigneeId: Optional[str] = Field(
        None, description="User id to assign the task to. Omit to leave unassigned."
    )
    siteId: Optional[str] = Field(None, description="Site id the task relates to (optional).")


class SendConversationMessageInput(BaseModel):
    conversation_id: str = Field(
        ..., description="The id of the conversation to post the message to."
    )
    body: str = Field(..., description="The message text to send.")
    channel: str = Field(
        "email", description="Delivery channel: 'email', 'sms', or 'whatsapp'."
    )


class CreateConversationInput(BaseModel):
    subject: str = Field(..., description="The subject/topic of the new conversation.")
    study_id: Optional[str] = Field(None, description="Study id (auto-filled from the selected study if omitted).")
    site_id: Optional[str] = Field(None, description="Site id (auto-filled from the selected site if omitted).")
    title: Optional[str] = Field(None, description="Optional title (defaults to the subject).")


class UpdateTaskInput(BaseModel):
    task_id: str = Field(..., description="The id of the task to update.")
    status: Optional[str] = Field(
        None, description="New status: open, in-progress, done, or cancelled."
    )
    title: Optional[str] = Field(None, description="New title.")
    description: Optional[str] = Field(None, description="New description.")
    dueDate: Optional[str] = Field(None, description="New due date, ISO YYYY-MM-DD.")
    statusUpdate: Optional[str] = Field(None, description="A short status note / comment.")


class TransitionAgreementStatusInput(BaseModel):
    agreement_id: str = Field(..., description="The id of the agreement to transition.")
    status: str = Field(
        ...,
        description=(
            "Target status, e.g. UNDER_REVIEW, READY_FOR_SIGNATURE, SENT_FOR_SIGNATURE, "
            "EXECUTED. Only transitions the workflow allows will succeed."
        ),
    )


class SendAgreementForSignatureInput(BaseModel):
    agreement_id: str = Field(..., description="The id of the agreement to send for signature.")
    site_signer_email: Optional[str] = Field(
        None, description="Signer's email (auto-filled from the site profile if omitted)."
    )
    message: Optional[str] = Field(None, description="Optional note to include in the invite.")


class CreateBudgetTemplateInput(BaseModel):
    trial_id: str = Field(..., description="The study/trial id the budget belongs to.")
    name: str = Field(..., description="A name for the budget template.")
    site_id: Optional[str] = Field(None, description="Site id, if this is a site-level budget.")
    target_currency_code: str = Field("USD", description="3-letter currency code, e.g. USD.")
    enrollment_planned: Optional[int] = Field(None, description="Planned enrollment count.")


class SetBudgetStatusInput(BaseModel):
    template_id: str = Field(..., description="The budget template id.")
    status: str = Field(
        ...,
        description="New status: draft, under_review, approved, executed, amended, or archived.",
    )


# The set of navigable screens is provided per-turn by the frontend's
# auto-derived catalog (complete-by-construction from the app's routes/modes/tabs),
# and injected as navigate_to's `screen` enum at tool-build time (see tools.py).
# This fallback list is used only if a turn arrives without a catalog.
DEFAULT_SCREENS = [
    "dashboard", "tasks", "conversations", "threads", "site_profile", "site_staff",
    "irb_administrative_info", "site_status", "monitoring", "documents",
    "study_setup", "site_setup", "agreements", "budget", "workflow_tasks",
]


class ListSiteAgreementsInput(BaseModel):
    site_id: str = Field(..., description="Site id whose agreements to list (auto-filled from the selected site).")
    study_id: Optional[str] = Field(None, description="Study id (auto-filled from the selected study).")


class ListStudyTemplatesInput(BaseModel):
    study_id: str = Field(..., description="Study id whose templates to list (auto-filled from the selected study).")


class OpenEntityInput(BaseModel):
    entity_type: str = Field(
        ..., description="The kind of record to open — must be one in the ENTITY CATALOG."
    )
    id: str = Field(..., description="The id of the specific record to open.")


class StartTourInput(BaseModel):
    tour: str = Field(
        ...,
        description="The tour id to run — must be one of the tours listed in your instructions.",
    )


class FillFieldInput(BaseModel):
    key: str = Field(..., description="The field key to populate — must be one listed for that form in FILLABLE FORMS.")
    value: str = Field(..., description="The value to put in that field.")


class FillFormInput(BaseModel):
    form: str = Field(..., description="Which form to fill — must be one of the ids in FILLABLE FORMS.")
    fields: list[FillFieldInput] = Field(
        ..., description="Field key/value pairs to populate. Use only the field keys listed for that form."
    )


class DeepReadInput(BaseModel):
    # No args — deep-read pulls the underlying data for the CURRENT screen +
    # study/site context (both come from the message, not the model).
    pass


class ReadScreenInput(BaseModel):
    # No args: the server reads whatever screen the user is currently on (the
    # message's current-screen key is authoritative; the model can't redirect it).
    pass


class NavigateToInput(BaseModel):
    screen: str = Field(
        ...,
        description=(
            "The screen to open — must be one of the screens listed in the SCREEN "
            "CATALOG in your instructions. If what the user wants isn't in the "
            "catalog, do NOT call this tool; say you can't open it."
        ),
    )
    # Some screens need a study (and/or site) selected first. Resolve these to
    # ids the user is entitled to (via list_studies / list_study_sites) and pass
    # them here; the app selects that study/site before opening the screen.
    study_id: Optional[str] = Field(None, description="Study id to select before opening, if the screen needs a study.")
    site_id: Optional[str] = Field(None, description="Site id to select before opening, if the screen needs a site.")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: Dict[str, Command] = {}


def register(command: Command) -> None:
    if command.name in REGISTRY:
        raise ValueError(f"duplicate command: {command.name}")
    REGISTRY[command.name] = command


register(
    Command(
        name="navigate_to",
        description=(
            "Open / navigate the user to a screen in the app. Use this for "
            "requests like 'open X', 'go to X', 'take me to X', 'show me the X "
            "screen'. Only the listed screens are available; if the user asks for "
            "a screen that isn't an option, say you can't open it — do not give "
            "manual step-by-step directions."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=NavigateToInput,
        frontend=True,
    )
)

register(
    Command(
        name="fill_form",
        description=(
            "Populate the fields of a form that is open on the user's screen — e.g. "
            "'fill in a new task with …'. You FILL fields ONLY; you NEVER submit, save, "
            "or sign. After filling, tell the user to review and click the form's own "
            "submit button themselves (their click does the guarded, audited save). Only "
            "forms in the FILLABLE FORMS list can be filled, and only the field keys "
            "listed there. If the form isn't open on screen the fill does nothing — then "
            "tell the user to open it first. Never use this for signing or agreements."
        ),
        method="",
        path_template="",
        risk=Risk.READ,  # fills the user's own view; the WRITE is the user's own submit click
        input_model=FillFormInput,
        frontend=True,
    )
)

register(
    Command(
        name="deep_read",
        description=(
            "Pull the FULL UNDERLYING DATA behind the current screen from the backend — "
            "use ONLY when the user EXPLICITLY asks for the full/underlying dataset "
            "('give me all the data', 'pull the full dataset', 'show me all N pages/rows', "
            "'fetch everything'). It calls the real data route and returns what that route "
            "allows (it inherits the route's own access rules; if access is denied you'll "
            "get a denial to report honestly). For a normal 'explain / summarize this "
            "screen', do NOT use this — use read_screen (on-screen only). If there's no "
            "data route for this screen, say so honestly."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=DeepReadInput,
    )
)

register(
    Command(
        name="read_screen",
        description=(
            "Read what is CURRENTLY VISIBLE on the user's screen (like looking over "
            "their shoulder). Use when the user asks to explain / describe / summarize "
            "'this screen' / 'what's on this screen' / 'this page' / 'what am I looking "
            "at'. It returns ONLY the rendered, on-screen content (never hidden data, "
            "never a backend fetch). Answer from that visible content; if more is needed, "
            "ask the user to scroll / open the tab / expand and say 'continue', then wait. "
            "If nothing is readable, say so honestly."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=ReadScreenInput,
        # Special-cased in agent._execute (composite read across guarded routes),
        # not a single route and not a frontend event.
    )
)

register(
    Command(
        name="list_site_agreements",
        description=(
            "List the agreements (CTA/CDA/etc.) for a site — use to find/resolve a "
            "specific agreement by name or type. Study/site auto-applied from context."
        ),
        method="GET",
        path_template="/api/sites/{site_id}/agreements",
        risk=Risk.READ,
        input_model=ListSiteAgreementsInput,
        context_params={"site_id": "site_id", "study_id": "study_id"},
    )
)

register(
    Command(
        name="list_study_templates",
        description=(
            "List the document templates (agreement/clause templates) for a study — "
            "use to find/resolve a specific template by name. Study auto-applied."
        ),
        method="GET",
        path_template="/api/studies/{study_id}/templates",
        risk=Risk.READ,
        input_model=ListStudyTemplatesInput,
        context_params={"study_id": "study_id"},
    )
)

register(
    Command(
        name="open_entity",
        description=(
            "Open a specific record's detail once you know its id (from a search). "
            "entity_type must be one from the ENTITY CATALOG. Navigation-class — no "
            "confirmation, no audit."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=OpenEntityInput,
        frontend=True,
    )
)

register(
    Command(
        name="start_tour",
        description=(
            "Run a read-only GUIDED TOUR — animated on-screen highlights + narration, "
            "no changes made. Use for 'show me around X', 'give me a tour of X', 'walk me "
            "through X', 'show me a demo of X', 'demo X', and HOW-TO questions ('how do I "
            "create a budget?' -> how_to_create_budget). Screen tours show where the "
            "screen lives before navigating; how_to_* tours walk the exact click path; "
            "app_overview sweeps the whole app. Every navigable screen has a tour — match "
            "the user's topic to the closest tour id/alias in your instructions; only if "
            "nothing matches at all, fall back to help_answer."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=StartTourInput,
        frontend=True,
    )
)

register(
    Command(
        name="present_choices",
        description=(
            "Show tappable choice chips instead of listing options in prose. Use "
            "for disambiguation ('which study?') and for suggesting next steps. "
            "Tapping a chip sends it as the user's next message."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=PresentChoicesInput,
        frontend=True,
    )
)

register(
    Command(
        name="show_notice",
        description=(
            "Show a clean styled notice for an info/limit/error message — e.g. "
            "'I can't open that screen yet' or an access-denied result. Use this "
            "instead of plain prose for limits and errors."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=ShowNoticeInput,
        frontend=True,
    )
)

register(
    Command(
        name="show_chart",
        description=(
            "Render a REAL themed chart (bar / donut / line) from numeric data you "
            "already have. ALWAYS use this when the user asks for a chart, graph, "
            "or visualisation, or when proportions/comparisons/trends would read "
            "better visually. NEVER draw ASCII-art charts, pipe tables posing as "
            "bars, or emoji sparklines in text — this tool is the only way to chart."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=ShowChartInput,
        frontend=True,
    )
)

register(
    Command(
        name="help_answer",
        description=(
            "Give a doc-grounded how-to / help answer as a themed block, with an "
            "optional offer button when you can perform the action via a tool."
        ),
        method="",
        path_template="",
        risk=Risk.READ,
        input_model=HelpAnswerInput,
        frontend=True,
    )
)

register(
    Command(
        name="get_task",
        description="Fetch a single task by id (renders as one detailed task card).",
        method="GET",
        path_template="/api/tasks/{task_id}",
        risk=Risk.READ,
        input_model=GetTaskInput,
    )
)

register(
    Command(
        name="list_my_tasks",
        description=(
            "List the current user's tasks / action items. Use when the user asks "
            "what they need to do, their to-dos, or their open tasks."
        ),
        method="GET",
        path_template="/api/tasks",
        risk=Risk.READ,
        input_model=ListMyTasksInput,
    )
)

register(
    Command(
        name="list_studies",
        description="List the studies (clinical trials) the current user has access to.",
        method="GET",
        path_template="/api/studies",
        risk=Risk.READ,
        input_model=ListStudiesInput,
    )
)

register(
    Command(
        name="list_study_sites",
        description=(
            "List the sites the current user can access within a study. Use to "
            "resolve or disambiguate a site by name for navigation."
        ),
        method="GET",
        path_template="/api/sites",
        risk=Risk.READ,
        input_model=ListStudySitesInput,
        context_params={"study_id": "study_id"},
    )
)

register(
    Command(
        name="list_my_conversations",
        description=(
            "List the current user's conversations for the selected site (the same "
            "the Conversations screen shows). Study/site are applied automatically."
        ),
        method="GET",
        path_template="/api/conversations",
        risk=Risk.READ,
        input_model=ListMyConversationsInput,
        context_params={"study_id": "study_id", "site_id": "site_id"},
    )
)

register(
    Command(
        name="create_task",
        description=(
            "Create a new task / action item for the user. Use when the user asks "
            "to add, create, or make a task, to-do, or reminder."
        ),
        method="POST",
        path_template="/api/tasks",
        risk=Risk.WRITE,
        input_model=CreateTaskInput,
        context_params={"site_id": "siteId"},
    )
)

register(
    Command(
        name="create_conversation",
        description=(
            "Start a NEW conversation (thread) with a subject in the selected "
            "site/study. Use when the user asks to create/start a new conversation. "
            "Study/site are applied from context automatically; the message body is "
            "not part of this — after creating, offer to post a first message."
        ),
        method="POST",
        path_template="/api/conversations",
        risk=Risk.WRITE,
        input_model=CreateConversationInput,
        context_params={"study_id": "study_id", "site_id": "site_id"},
    )
)

register(
    Command(
        name="send_conversation_message",
        description=(
            "Send / post a message in an existing conversation. Use when the user "
            "asks to reply to or send a message in a conversation."
        ),
        method="POST",
        path_template="/api/conversations/{conversation_id}/messages",
        risk=Risk.WRITE,
        input_model=SendConversationMessageInput,
    )
)

register(
    Command(
        name="update_task",
        description=(
            "Update an existing task — change its status (e.g. mark done), title, "
            "description, due date, or add a status note. Look up the task first "
            "with list_my_tasks to get its id."
        ),
        method="PUT",
        path_template="/api/tasks/{task_id}",
        risk=Risk.WRITE,
        input_model=UpdateTaskInput,
    )
)

register(
    Command(
        name="transition_agreement_status",
        description=(
            "Advance an agreement's workflow status (e.g. to UNDER_REVIEW or "
            "READY_FOR_SIGNATURE). The route enforces the allowed transitions — it "
            "will reject backward moves or skipped states."
        ),
        method="PATCH",
        path_template="/api/agreements/{agreement_id}/status",
        risk=Risk.WRITE,
        input_model=TransitionAgreementStatusInput,
    )
)

# REGULATED. This INITIATES the signing workflow (emails a secure signing link);
# it does NOT and cannot apply a signature. No signature-application route
# (/sign/submit, /sign/request-otp, /document/sign-with-otp, /sign/dispatch,
# /sign/attach-executed) is registered as a command, so the agent can never
# auto-fire an e-signature or bypass the route's sequential-signing rules.
register(
    Command(
        name="send_agreement_for_signature",
        description=(
            "Send an agreement to its signer for e-signature. This emails a secure "
            "signing link to the signer; the signer still has to open it and sign — "
            "this does NOT sign on anyone's behalf."
        ),
        method="POST",
        path_template="/api/agreements/{agreement_id}/send-for-signature",
        risk=Risk.REGULATED,
        input_model=SendAgreementForSignatureInput,
        body_encoding="form",
    )
)

register(
    Command(
        name="create_budget_template",
        description=(
            "Create a new site/study budget template — the first step in setting up "
            "a budget. Offer this when the user wants to set up or start a budget. "
            "Needs the study/trial id (use list_studies to find it)."
        ),
        method="POST",
        path_template="/api/budgeting/templates",
        risk=Risk.WRITE,
        input_model=CreateBudgetTemplateInput,
        context_params={"study_id": "trial_id", "site_id": "site_id"},
    )
)

# REGULATED — approving/executing a budget is a controlled state change.
register(
    Command(
        name="set_budget_status",
        description=(
            "Change a budget template's status, e.g. approve or execute it. "
            "Approving/executing a budget is a regulated, controlled action."
        ),
        method="PATCH",
        path_template="/api/budgeting/templates/{template_id}/status",
        risk=Risk.REGULATED,
        input_model=SetBudgetStatusInput,
    )
)
