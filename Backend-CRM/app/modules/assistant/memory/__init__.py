"""Orbit derived memory.

A small, bounded, *derived* memory for the assistant — concise facts about the
user's preferences and working patterns (never transcripts, never PHI). Modelled
on how Claude's memory works, adapted with clinical guardrails.

Two tables (see ``models.py``):
  * ``assistant_turn``   — short-TTL RAW buffer of recent turns; the ONLY thing
    the nightly distiller reads. Rolling retention; not a permanent transcript.
  * ``assistant_memory`` — capped (~40/user) DERIVED items; PHI-stripped,
    de-duped, evicted when over cap. This is what loads at session open.

Nothing here writes memory on the request path: derivation is a nightly Celery
job (``derivation.py``). Loads are a single read (``repository.load_memory``).
"""
