"""Typed response blocks built from real command results.

The assistant streams a small vocabulary of typed blocks over SSE; the frontend
renders each with a real component. DATA blocks (records/stats) are built HERE,
from the route's structured JSON — the model never serializes records. Narration
and interactive blocks (choices, notices, help) are authored by the model via
presentation tools (see commands.py / agent.py).

Keeping the mapping backend-side means a record's fields, status colour, and
click target are trustworthy and consistent, not paraphrased by the model.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

# Mirror of the task status pills used on the Tasks screen (TasksTab.tsx) so the
# assistant's cards match the rest of the CRM.
_TASK_STATUS_LABEL = {
    "open": "Pending",
    "in-progress": "In Progress",
    "done": "Done",
    "cancelled": "Cancelled",
}
_TASK_STATUS_TONE = {
    "open": "warning",
    "in-progress": "info",
    "done": "success",
    "cancelled": "neutral",
}
_STUDY_STATUS_TONE = {
    "active": "success",
    "completed": "neutral",
    "archived": "neutral",
    "draft": "info",
    "on_hold": "warning",
}
_CONV_STATUS_TONE = {
    "open": "info",
    "awaiting_reply": "warning",
    "awaiting_us": "warning",
    "snoozed": "neutral",
    "resolved": "success",
    "closed": "neutral",
}


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None


def _friendly_date(value: Any) -> Optional[str]:
    d = _parse_date(value)
    return d.strftime("%b %-d, %Y") if d else (str(value) if value else None)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _task_card(t: Dict[str, Any]) -> Dict[str, Any]:
    status = (t.get("status") or "open").lower()
    title = t.get("title") or (t.get("description") or "").strip()[:120] or "Untitled task"
    subtitle = t.get("description") if t.get("title") else None

    # Severity out of the prose, into a flag chip + the card's accent spine.
    severity = _severity_of(title)
    flag = None
    if severity:
        title = _SEVERITY_PREFIX_RE.sub("", title) or title
        flag = {"label": severity, "tone": _SEVERITY_TONE.get(severity, "neutral")}

    meta: List[Dict[str, Any]] = []
    due = t.get("dueDate")
    if due:
        due_date = _parse_date(due)
        overdue = bool(due_date and due_date < _today() and status not in ("done", "cancelled"))
        meta.append({
            "label": "Overdue" if overdue else "Due",
            "value": _friendly_date(due),
            "tone": "error" if overdue else "neutral",
        })
    assignee = t.get("assigneeName") or t.get("assignedTo")
    if assignee:
        meta.append({"label": "Assignee", "value": str(assignee), "tone": "neutral"})

    actions: List[Dict[str, str]] = []
    if status not in ("done", "cancelled"):
        # Quick actions send a natural-language instruction as the next turn, so
        # they route through the normal command path (confirmation + audit).
        actions.append({"label": "Mark done", "message": f"Mark task {t.get('id')} as done"})

    return {
        "type": "record_card",
        "record_type": "task",
        "id": t.get("id"),
        "title": title,
        "subtitle": subtitle,
        "status": {"label": _TASK_STATUS_LABEL.get(status, status), "tone": _TASK_STATUS_TONE.get(status, "neutral")},
        "flag": flag,
        # The card's spine color: severity first, else the status tone.
        "accent": (flag or {}).get("tone") or _TASK_STATUS_TONE.get(status, "neutral"),
        "meta": meta,
        "actions": actions[:2],
    }


def _study_card(s: Dict[str, Any]) -> Dict[str, Any]:
    status = (s.get("status") or "").lower()
    return {
        "type": "record_card",
        "record_type": "study",
        "id": s.get("id") or s.get("study_id"),
        "title": s.get("name") or s.get("study_id") or "Study",
        "subtitle": s.get("study_id") if s.get("name") else None,
        "status": ({"label": s.get("status"), "tone": _STUDY_STATUS_TONE.get(status, "neutral")} if s.get("status") else None),
        "accent": _STUDY_STATUS_TONE.get(status, "neutral"),
        "meta": [],
        "actions": [],
    }


def _conversation_card(c: Dict[str, Any]) -> Dict[str, Any]:
    status = (c.get("status") or "").lower()
    title = c.get("subject") or c.get("title") or "Conversation"
    subtitle = c.get("ai_summary") or c.get("participant_email")
    meta: List[Dict[str, Any]] = []
    # High/urgent priority becomes the flag chip below; only mention the rest here.
    if c.get("ai_priority") and str(c["ai_priority"]).lower() not in ("high", "urgent"):
        meta.append({"label": "Priority", "value": str(c["ai_priority"]).title(), "tone": "neutral"})
    # High-priority conversations get a flag + a warning spine so they pop.
    priority = str(c.get("ai_priority") or "").lower()
    flag = {"label": "High priority", "tone": "warning"} if priority in ("high", "urgent") else None
    return {
        "type": "record_card",
        "record_type": "conversation",
        "id": str(c.get("id")) if c.get("id") else None,
        "title": title,
        "subtitle": (subtitle[:140] if isinstance(subtitle, str) else None),
        "status": ({"label": c.get("status"), "tone": _CONV_STATUS_TONE.get(status, "info")} if c.get("status") else None),
        "flag": flag,
        "accent": (flag or {}).get("tone") or _CONV_STATUS_TONE.get(status, "info"),
        "meta": meta,
        "actions": [],
    }


def _severity_of(title: str) -> Optional[str]:
    """Monitoring tasks embed severity in the title prefix ('Critical: …')."""
    t = (title or "").lower()
    for sev in ("critical", "major", "minor"):
        if t.startswith(sev) or f"{sev}:" in t[:20]:
            return sev.capitalize()
    return None


_SEVERITY_TONE = {"Critical": "error", "Major": "warning", "Minor": "info"}

# "Critical: Data quality…" → display title "Data quality…" + a severity FLAG
# chip. The severity stops being buried prose and becomes a scannable element.
_SEVERITY_PREFIX_RE = re.compile(r"^\s*(critical|major|minor)\s*[:\-–—]\s*", re.IGNORECASE)


def _group_counts(pairs: List[tuple], messages: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """[(label, tone)] -> ordered [{label, value, tone}] with counts.

    ``messages`` optionally maps a label to a drill-in message — tapping the
    count sends it as the next turn (same trust path as choice chips)."""
    from collections import OrderedDict
    acc: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for label, tone in pairs:
        if label not in acc:
            acc[label] = {"label": label, "value": 0, "tone": tone}
            msg = (messages or {}).get(label)
            if msg:
                acc[label]["message"] = msg
        acc[label]["value"] += 1
    return list(acc.values())


def _task_summary_blocks(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tasks = [t for t in data if isinstance(t, dict)]
    total = len(tasks)
    today = _today()

    def _st(t):
        return (t.get("status") or "open").lower()

    open_ = sum(1 for t in tasks if _st(t) == "open")
    in_prog = sum(1 for t in tasks if _st(t) == "in-progress")
    overdue = 0
    due_soon = 0
    for t in tasks:
        dd = _parse_date(t.get("dueDate"))
        if dd and _st(t) not in ("done", "cancelled"):
            if dd < today:
                overdue += 1
            elif (dd - today).days <= 7:
                due_soon += 1

    # Top-line totals — from the FULL dataset (not the number of cards). Each
    # stat carries a drill-in message (tap → next turn; the normal guarded path).
    stat = {"type": "stat_row", "stats": [
        {"label": "Total", "value": total, "tone": "neutral",
         "message": "Show all my tasks as cards"},
        {"label": "Open", "value": open_, "tone": "warning" if open_ else "neutral",
         "message": "Show my open tasks as cards"},
        {"label": "In progress", "value": in_prog, "tone": "info",
         "message": "Show my in-progress tasks as cards"},
        {"label": "Overdue", "value": overdue, "tone": "error" if overdue else "neutral",
         "message": "Which of my tasks are overdue?"},
    ]}

    # Grouped breakdown.
    _SEV_TONE = {"Critical": "error", "Major": "warning", "Minor": "info"}
    sev_pairs = []
    for t in tasks:
        if _st(t) in ("done", "cancelled"):
            continue
        sev = _severity_of(t.get("title") or t.get("description") or "")
        if sev:
            sev_pairs.append((sev, _SEV_TONE.get(sev, "neutral")))
    _STATUS_TONE = {"open": "warning", "in-progress": "info", "done": "success", "cancelled": "neutral"}
    status_pairs = [(_TASK_STATUS_LABEL.get(_st(t), _st(t)), _STATUS_TONE.get(_st(t), "neutral")) for t in tasks]
    assignee_pairs = [((t.get("assigneeName") or t.get("assignedTo") or "Unassigned"), "neutral") for t in tasks]

    _STATUS_MSG = {
        "Pending": "Show my open tasks as cards",
        "In Progress": "Show my in-progress tasks as cards",
        "Done": "Show my done tasks as cards",
        "Cancelled": "Show my cancelled tasks as cards",
    }
    _SEV_MSG = {s: f"Which of my open tasks are {s.lower()}?" for s in ("Critical", "Major", "Minor")}
    groups = [{"title": "By status", "items": _group_counts(status_pairs, _STATUS_MSG)}]
    if sev_pairs:
        groups.append({"title": "By severity (open)", "items": _group_counts(sev_pairs, _SEV_MSG)})
    if overdue or due_soon:
        groups.append({"title": "Timing", "items": [
            {"label": "Overdue", "value": overdue, "tone": "error" if overdue else "neutral",
             "message": "Which of my tasks are overdue?"},
            {"label": "Due within 7 days", "value": due_soon, "tone": "warning" if due_soon else "neutral",
             "message": "Which of my tasks are due within the next 7 days?"},
        ]})
    # Assignee: keep it small (top 4 by count).
    assignees = sorted(_group_counts(assignee_pairs), key=lambda x: -x["value"])[:4]
    if assignees:
        groups.append({"title": "By assignee", "items": assignees})

    return [stat, {"type": "breakdown", "groups": groups}]


_PLURAL = {"study": "studies", "conversation": "conversations", "task": "tasks"}


def _generic_summary_blocks(record_type: str, data: List[Dict[str, Any]], status_tone: Dict[str, str]) -> List[Dict[str, Any]]:
    items = [x for x in data if isinstance(x, dict)]
    plural = _PLURAL.get(record_type, f"{record_type}s")
    stat = {"type": "stat_row", "stats": [{
        "label": "Total", "value": len(items), "tone": "info",
        "message": f"Show all my {plural} as cards",
    }]}
    pairs = [((x.get("status") or "—"), status_tone.get((x.get("status") or "").lower(), "neutral")) for x in items]
    status_msgs = {
        label: f"Show my {label.lower()} {plural} as cards"
        for label, _tone in pairs if label != "—"
    }
    groups = [{"title": "By status", "items": _group_counts(pairs, status_msgs)}]
    return [stat, {"type": "breakdown", "groups": groups}]


# "Show all" chip appended to a summary so the user can pull the full card view
# on demand. Emitted by the backend (not the model) so the model's synthesized
# narrative isn't suppressed by a terminal presentation-tool call.
_SHOW_ALL = {
    "list_my_tasks": ("Show all tasks", "Show all my tasks as cards"),
    "list_studies": ("Show all studies", "Show all my studies as cards"),
    "list_my_conversations": ("Show all conversations", "Show all my conversations as cards"),
}


def build_summary_blocks(command_name: str, data: Any) -> List[Dict[str, Any]]:
    """Grouped-count breakdown for synthesize intent — no record cards. Counts are
    computed from the full dataset here, so totals are correct and consistent."""
    blocks: List[Dict[str, Any]] = []
    if command_name == "list_my_tasks" and isinstance(data, list):
        blocks = _task_summary_blocks(data)
    elif command_name == "list_studies" and isinstance(data, list):
        blocks = _generic_summary_blocks("study", data, _STUDY_STATUS_TONE)
    elif command_name == "list_my_conversations" and isinstance(data, list):
        blocks = _generic_summary_blocks("conversation", data, _CONV_STATUS_TONE)
    if blocks and command_name in _SHOW_ALL:
        label, message = _SHOW_ALL[command_name]
        blocks.append({"type": "choice_chips", "question": None,
                       "options": [{"label": label, "message": message}]})
    return blocks


def build_blocks(command_name: str, data: Any) -> List[Dict[str, Any]]:
    """Turn a read command's structured result into data blocks. Empty list when
    there's nothing to render as a block (the model then narrates as text)."""
    if command_name == "list_my_tasks" and isinstance(data, list):
        cards = [_task_card(t) for t in data if isinstance(t, dict)]
        total = len(cards)
        open_ = sum(1 for t in data if isinstance(t, dict) and (t.get("status") or "").lower() == "open")
        overdue = 0
        for t in data:
            if not isinstance(t, dict):
                continue
            dd = _parse_date(t.get("dueDate"))
            if dd and dd < _today() and (t.get("status") or "").lower() not in ("done", "cancelled"):
                overdue += 1
        stats = [
            {"label": "Total", "value": total, "tone": "neutral",
             "message": "Show all my tasks as cards"},
            {"label": "Open", "value": open_, "tone": "warning" if open_ else "neutral",
             "message": "Show my open tasks as cards"},
            {"label": "Overdue", "value": overdue, "tone": "error" if overdue else "neutral",
             "message": "Which of my tasks are overdue?"},
        ]
        blocks: List[Dict[str, Any]] = [{"type": "stat_row", "stats": stats}]
        if cards:
            blocks.append({"type": "record_list", "record_type": "task", "records": cards})
        return blocks

    if command_name == "get_task" and isinstance(data, dict) and data.get("id"):
        return [_task_card(data)]

    if command_name == "list_studies" and isinstance(data, list):
        cards = [_study_card(s) for s in data if isinstance(s, dict)]
        blocks = [{"type": "stat_row", "stats": [{"label": "Studies", "value": len(cards), "tone": "info"}]}]
        if cards:
            blocks.append({"type": "record_list", "record_type": "study", "records": cards})
        return blocks

    if command_name == "list_my_conversations" and isinstance(data, list):
        cards = [_conversation_card(c) for c in data if isinstance(c, dict)]
        blocks = [{"type": "stat_row", "stats": [{"label": "Conversations", "value": len(cards), "tone": "info"}]}]
        if cards:
            blocks.append({"type": "record_list", "record_type": "conversation", "records": cards})
        return blocks

    return []
