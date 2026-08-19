"""
step_types.py
=============

Static metadata describing the reusable step kinds. The builder palette renders
one draggable card per entry here, and the runner picks one generic component per
`type`. Adding a brand-new step kind is the ONLY thing that ever needs code — and
even then it is one component + one entry here, never a per-document rewrite.
"""

STEP_TYPE_CATALOG = [
    {
        "type": "form",
        "label": "Form",
        "description": "Collect or edit structured data (e.g. draft the agreement).",
        "icon": "form",
        "color": "#6366f1",
        "supports_assignee": True,
        "config_schema": {"fields": "list[FormField]"},
    },
    {
        "type": "approval",
        "label": "Approval",
        "description": "A person reviews and approves or rejects.",
        "icon": "check",
        "color": "#10b981",
        "supports_assignee": True,
        "config_schema": {},
    },
    {
        "type": "signature",
        "label": "Signature",
        "description": "A person signs the document.",
        "icon": "pen",
        "color": "#f59e0b",
        "supports_assignee": True,
        "config_schema": {},
    },
    {
        "type": "decision",
        "label": "Decision",
        "description": "Automatic branch based on context (no human click).",
        "icon": "branch",
        "color": "#8b5cf6",
        "supports_assignee": False,
        "config_schema": {},
    },
    {
        "type": "terminal",
        "label": "End",
        "description": "A final state (Executed, Rejected, Cancelled).",
        "icon": "flag",
        "color": "#64748b",
        "supports_assignee": False,
        "config_schema": {},
    },
    {
        "type": "split",
        "label": "Parallel split",
        "description": "Open every outgoing branch at once; each branch is a full sequence.",
        "icon": "branch",
        "color": "#0ea5e9",
        "supports_assignee": False,
        "config_schema": {},
    },
    {
        "type": "join",
        "label": "Join",
        "description": "Wait for incoming branches; advances when the join policy is met.",
        "icon": "branch",
        "color": "#0ea5e9",
        "supports_assignee": False,
        "config_schema": {"join": "{mode: all|n_of_m|percent, value?}"},
    },
    {
        "type": "job",
        "label": "Automated step",
        "description": "Run a registered job (notification, AI agent, API call) with retries.",
        "icon": "form",
        "color": "#f97316",
        "supports_assignee": False,
        "config_schema": {"job": "{kind, params?, max_attempts?, output?}"},
    },
    {
        "type": "wait_message",
        "label": "Wait for event",
        "description": "Park until an external message arrives for this document.",
        "icon": "form",
        "color": "#14b8a6",
        "supports_assignee": False,
        "config_schema": {"message": "{name, output?}"},
    },
    {
        "type": "call",
        "label": "Sub-workflow",
        "description": "Spawn child workflow(s) and continue when enough complete.",
        "icon": "branch",
        "color": "#a855f7",
        "supports_assignee": False,
        "config_schema": {"call": "{definition_key, items_path?, context_map?, join?}"},
    },
]
