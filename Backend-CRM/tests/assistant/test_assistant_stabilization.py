"""Regression tests for the assistant stop-and-stabilize pass.

Locks the fixed bug-classes so they can't silently return:
  A. context threading — apply_context fills study/site; scope commands declare it.
  B. data truth — stat totals come from the dataset, not the number of cards.
  C. honesty — every non-frontend command maps to a real route (no phantom refusals).
  D. create_conversation exists with the right contract.
  compliance — whitelist-only, no auto-sign, write/regulated risk levels intact.

Pure unit tests (no server/DB) over the assistant's registry + block builders +
the central context injector.
"""
from app.modules.assistant.agent import _fallback_message, apply_context
from app.modules.assistant.blocks import build_blocks, build_summary_blocks
from app.modules.assistant.commands import REGISTRY, Command, Risk


# --------------------------------------------------------------------------- B
def _tasks():
    return [
        {"id": "1", "title": "Critical: A", "status": "open", "dueDate": "2000-01-01"},  # overdue
        {"id": "2", "title": "Major: B", "status": "open", "dueDate": "2999-01-01"},
        {"id": "3", "title": "C", "status": "in-progress"},
        {"id": "4", "title": "D", "status": "done"},
    ]


def _stat_total(blocks):
    for b in blocks:
        if b["type"] == "stat_row":
            for s in b["stats"]:
                if s["label"] == "Total":
                    return s["value"]
    return None


def test_browse_total_is_dataset_not_cards():
    data = _tasks()
    blocks = build_blocks("list_my_tasks", data)
    assert _stat_total(blocks) == len(data) == 4  # not "cards rendered"
    rl = [b for b in blocks if b["type"] == "record_list"][0]
    assert len(rl["records"]) == 4


def test_summary_has_no_cards_correct_total_and_breakdown():
    data = _tasks()
    blocks = build_summary_blocks("list_my_tasks", data)
    types = [b["type"] for b in blocks]
    assert "record_list" not in types                 # no card wall
    assert _stat_total(blocks) == 4                    # true total (8 open + 1 in-prog analogue)
    bd = [b for b in blocks if b["type"] == "breakdown"][0]
    titles = [g["title"] for g in bd["groups"]]
    assert "By status" in titles and "By severity (open)" in titles
    # A "show all" chip is offered so the user can pull cards on demand.
    chips = [b for b in blocks if b["type"] == "choice_chips"][0]
    assert any("show all" in o["label"].lower() for o in chips["options"])


def test_summary_total_consistent_regardless_of_order():
    a = _stat_total(build_summary_blocks("list_my_tasks", _tasks()))
    b = _stat_total(build_summary_blocks("list_my_tasks", list(reversed(_tasks()))))
    assert a == b == 4


# --------------------------------------------------------------------------- A
def test_apply_context_fills_missing_scope():
    cmd = REGISTRY["list_my_conversations"]
    out = apply_context(cmd, {}, {"study_id": "S1", "site_id": "SITE1"})
    assert out["study_id"] == "S1" and out["site_id"] == "SITE1"


def test_apply_context_does_not_override_explicit():
    cmd = REGISTRY["list_my_conversations"]
    out = apply_context(cmd, {"site_id": "EXPLICIT"}, {"study_id": "S1", "site_id": "SITE1"})
    assert out["site_id"] == "EXPLICIT"       # model value wins
    assert out["study_id"] == "S1"            # missing one still filled


def test_apply_context_noop_without_context_params():
    cmd = REGISTRY["get_task"]                 # entity command, no context_params
    out = apply_context(cmd, {"task_id": "T"}, {"study_id": "S1", "site_id": "SITE1"})
    assert out == {"task_id": "T"}


def test_scope_commands_declare_context():
    assert REGISTRY["list_my_conversations"].context_params == {"study_id": "study_id", "site_id": "site_id"}
    assert REGISTRY["create_conversation"].context_params == {"study_id": "study_id", "site_id": "site_id"}
    assert REGISTRY["list_study_sites"].context_params == {"study_id": "study_id"}


# --------------------------------------------------------------------------- D
def test_create_conversation_contract():
    cmd = REGISTRY["create_conversation"]
    assert cmd.method == "POST"
    assert cmd.path_template == "/api/conversations"
    assert cmd.risk == Risk.WRITE                       # routes through confirmation + audit
    fields = cmd.input_model.model_fields
    assert "subject" in fields and fields["subject"].is_required()
    assert "study_id" in fields and "site_id" in fields


# --------------------------------------------------------------------------- C + compliance
def test_every_backend_command_maps_to_a_real_route():
    # Honesty: a non-frontend command must have a concrete HTTP route, so the
    # model never needs to invent a "can't / do it yourself" answer. The two
    # composite reads are special-cased in agent._execute (read_screen consumes
    # the frontend's visible-viewport snapshot; deep_read fans out to the real
    # dashboard routes via invoke_get) — no single route, still not frontend.
    _SPECIAL_CASED_READS = {"read_screen", "deep_read"}
    for name, cmd in REGISTRY.items():
        if name in _SPECIAL_CASED_READS:
            assert not cmd.frontend and cmd.risk == Risk.READ, name
            continue
        if cmd.frontend:
            assert cmd.method == "" and cmd.path_template == ""
        else:
            assert cmd.method and cmd.path_template.startswith("/api/"), name


def test_no_signature_application_command():
    # Compliance: the agent can never auto-fire an e-signature.
    banned = ("sign_submit", "sign_with_otp", "request_otp", "sign_dispatch", "attach_executed")
    assert not any(b in REGISTRY for b in banned)
    assert not any("otp" in n or n.endswith("_sign") for n in REGISTRY)


def test_risk_levels_intact():
    assert REGISTRY["send_agreement_for_signature"].risk == Risk.REGULATED
    assert REGISTRY["set_budget_status"].risk == Risk.REGULATED
    for w in ("create_task", "update_task", "send_conversation_message",
              "create_conversation", "transition_agreement_status", "create_budget_template"):
        assert REGISTRY[w].risk == Risk.WRITE
    for r in ("list_my_tasks", "list_studies", "list_my_conversations", "get_task"):
        assert REGISTRY[r].risk == Risk.READ


def test_presentation_tools_are_frontend_reads():
    for n in ("navigate_to", "present_choices", "show_notice", "help_answer", "show_chart"):
        assert REGISTRY[n].frontend and REGISTRY[n].risk == Risk.READ


# ------------------------------------------------------------- never-silent
# A turn must always end with an answer or an honest limit; these lock the
# fallback wording classes so the silent-stop bug can't return.

def test_fallback_unreadable_screen_says_still_loading():
    msg = _fallback_message(("read_screen", {"readable": False, "screen": "dashboard"}), False)
    assert "loading" in msg.lower() and "ask me again" in msg.lower()


def test_fallback_silent_navigate_confirms_destination():
    msg = _fallback_message(("navigate_to", {"status": "navigated", "screen": "study_setup"}), False)
    assert "study setup" in msg.lower()          # names the real destination
    assert "_" not in msg                         # human wording, not the token


def test_fallback_round_cap_is_honest_limit():
    msg = _fallback_message(("list_my_tasks", {"status": 200}), True)
    assert "step limit" in msg.lower() and "nothing further was changed" in msg.lower()


def test_fallback_error_never_claims_success():
    msg = _fallback_message(("update_task", {"status": 500, "error": "boom"}), False)
    assert "failed" in msg.lower() and "nothing was changed" in msg.lower()
    assert "done" not in msg.lower()


def test_fallback_generic_asks_to_rephrase():
    msg = _fallback_message(None, False)
    assert "rephras" in msg.lower() or "asking again" in msg.lower()
