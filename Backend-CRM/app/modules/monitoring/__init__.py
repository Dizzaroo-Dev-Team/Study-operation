"""
monitoring module.

Phase 2.2 split of the 6,690-line app/monitor/router.py. The shim at
app/monitor/router.py keeps the parent router + the bootstrap helpers
(_ensure_monitor_tables and friends). Per-feature endpoint clusters live
here under routes/.

First cluster extracted: MVR Templates (10 endpoints).
Future sessions add: confirmation_letter, reschedule, pre_visit, findings,
visit_documents, post_visit, visit_report, follow_up_letter, etc.
"""
