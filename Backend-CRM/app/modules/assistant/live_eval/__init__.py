"""Orbit live evals — Kind B scoring of every real turn after its answer.

Feature-flagged (default OFF): ``ENABLE_LIVE_EVALS`` gates everything;
``ENABLE_LIVE_JUDGE`` additionally gates the (PHI-scrubbed) Gemini grounding
judge. Scoring is fire-and-forget and can never touch the user's response.
"""
