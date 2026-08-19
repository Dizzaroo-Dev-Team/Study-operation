"""Agentic assistant module.

Replaces the old inert "Ask Me Anything" chat. The assistant performs real
actions in the app *as the logged-in user* by invoking the app's own HTTP
routes in-process (added in CP1), so every route dependency — RBAC, tenancy /
study scoping, conversation-access, and 21 CFR Part 11 audit — runs unchanged.

CP0 provides the transport skeleton only: a persistent SSE channel
(server -> client) and a POST message endpoint (client -> server), plus a
streaming LLM provider behind a thin seam. No tools/commands yet.
"""
