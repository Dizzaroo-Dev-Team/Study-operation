"""agent_evals — a reusable, project-neutral agent-evaluation toolkit.

Layout:
    core/        — generic toolkit (connector contract, goldens, graders,
                   DeepEval metrics, Gemini judge). NOTHING project-specific
                   may live here.
    connectors/  — one module per project. Each implements the single
                   ``run(input) -> RunResult`` contract from core.connector.
    goldens/     — golden test-case files (JSON/YAML), one per project.

Grading philosophy: deterministic checks over the agent's *trace* are the
primary layer; the LLM judge (G-Eval on Gemini) is reserved for genuinely
fuzzy criteria (honesty of phrasing, grounding of a summary).
"""
