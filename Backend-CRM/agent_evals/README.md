# agent_evals â€” reusable agent-evaluation toolkit

Automated evals for agentic AI features, graded with [DeepEval](https://deepeval.com)
running **local-first** (no cloud account, no OpenAI) with **Gemini 2.5 Pro** as the
LLM judge â€” and a strong bias toward **deterministic checks over LLM judging**
wherever a right/wrong answer exists.

Two kinds of evaluation share this toolkit:

* **Kind A â€” offline goldens** (`test_orbit_evals.py`): pre-written test cases
  run against the agent on demand / in CI.
* **Kind B â€” live scoring** (`core/live.py` + `app/modules/assistant/live_eval/`):
  every REAL user turn is scored after its answer is produced. Referenceless
  only (no goldens, no expected outputs), feature-flagged, default OFF. See
  "Live scoring" below.

```
agent_evals/
  core/            generic toolkit â€” NOTHING project-specific may live here
    connector.py     the one contract a project implements: run(input) -> RunResult
    goldens.py       YAML/JSON goldens loader
    checks.py        deterministic trace predicates (primary grading layer, offline)
    live.py          REFERENCELESS live scorer: deterministic invariants +
                     scrub-gated grounding judge (no deepeval import â€” prod-safe)
    gemini_client.py deepeval-free Gemini client (shared by live + offline judge)
    metrics.py       DeepEval metrics: DeterministicChecksMetric, ExpectedToolsMetric, G-Eval builder
    judge.py         Gemini judge for DeepEval (offline only; wraps gemini_client)
    runner.py        golden + RunResult -> LLMTestCase + metric bundle
  connectors/      one module per project
    orbit.py         Orbit (this CRM's agentic assistant) â€” live agent + audit-log trace
    fixture.py       replay connector for CI self-tests (clearly labeled, not a real agent)
  goldens/
    orbit.yaml            Orbit starter goldens (HUMAN SIGN-OFF REQUIRED â€” see banner)
    fixture_selftest.yaml toolkit self-test cases (engineering, CI-safe)
  test_orbit_evals.py          live-agent golden suite (needs backend runtime)
  test_toolkit_selftest.py     deterministic self-tests (CI-safe: no DB/LLM/network)
  test_live_scorer_selftest.py live-scorer self-tests (CI-safe: no DB/LLM/network)
```

## Running

**Toolkit self-tests** (anywhere, no secrets):

```bash
pip install -r agent_evals/requirements.txt
deepeval test run agent_evals/test_toolkit_selftest.py
```

**Orbit live evals** (inside the backend runtime â€” needs dev Postgres/Mongo/Redis
and `GEMINI_API_KEY`, all already present in the container env):

```bash
docker exec backend-crm-backend-1 pip install -q "deepeval>=3.0" pyyaml   # once per container
docker exec -e PYTHONPATH=/app -e DEEPEVAL_TELEMETRY_OPT_OUT=YES \
    backend-crm-backend-1 deepeval test run agent_evals/test_orbit_evals.py
```

`EVAL_SKIP_JUDGE=1` runs the deterministic layer only (no Gemini judge calls).
`EVAL_JUDGE_MODEL` overrides the judge model (default `gemini-3.5-flash`).

## How to add a NEW PROJECT

1. **Write one connector module** â€” `connectors/<project>.py` exposing
   `async def run(input: dict) -> RunResult`. It must execute your agent and
   assemble the trace from the agent's own **ground truth** (audit log, event
   stream, tool-call records) â€” never from what the model *says* it did. The
   normalized trace shape is documented in [`core/connector.py`](core/connector.py).
   Everything project-specific (fixture users, context resolution, cleanup)
   stays inside this module.
2. **Write goldens** â€” `goldens/<project>.yaml` (shape in
   [`core/goldens.py`](core/goldens.py)).
3. **Copy the ~20-line test file** â€” duplicate `test_orbit_evals.py`, point it
   at your goldens + connector. Done.

## How to add GOLDENS

Each case is `{input, checks, expected_tools?, judge?}`:

- `input` â€” passed verbatim to the connector; put whatever your agent needs.
- `checks` â€” deterministic predicates over the trace (see the catalog in
  [`core/checks.py`](core/checks.py): `action_taken`, `no_actions_with_risk`,
  `audit_contains`, `flag_equals`, `answer_contains`, ...). **This is the
  primary layer â€” prefer a check over a judge whenever right/wrong exists.**
- `expected_tools` â€” deterministic "did it call the right tools" metric.
- `judge` â€” plain-English G-Eval criteria for the Gemini judge. Use ONLY for
  genuinely fuzzy expectations (honest phrasing, grounding of a summary).

Every golden carries `review: pending | approved`. **A human domain expert must
review and approve goldens before their results count as anything more than
engineering signal** â€” the goldens are the accountability layer, not machine
truth.

## Live scoring (Kind B) â€” every real turn, scored after the answer

**How it works.** `run_turn` arms a per-turn event tap (the SSE stream consumes
hub events destructively, so they're recorded as they're emitted). When the
turn finishes â€” success or failure â€” the app fire-and-forgets a scoring task
(`asyncio.create_task`, same pattern as the turn task itself): the user's
response is NEVER blocked, delayed, or altered, and a scoring crash is logged
and swallowed. The scorer normalizes the events with the same digest the
offline connector uses, snapshots the turn's audit rows, runs the referenceless
metrics, and INSERTs one row into the append-only `live_eval_scores` table
(attributable, UTC-timestamped, no update/delete path â€” ALCOA+).

**Referenceless only.** Live user questions aren't pre-written, so live metrics
never use goldens or expected outputs. Deterministic invariants (local, nothing
leaves the box): `no_phi_in_answer`, `dangerous_request_refused`,
`rbac_denials_honored`, `fill_never_submit`, `no_forbidden_actions`,
`write_gate_integrity`. One LLM-judge metric: `grounding` â€” did the answer
stick to what the agent actually retrieved/saw this turn.

**PHI scrub before judge â€” non-bypassable.** Deterministic checks run locally
on raw text. Any text bound for the Gemini judge (answer + evidence) passes
through `phi_filter.scrub_text` (direct identifiers â†’ `[REDACTED-*]`); the
generic scorer REFUSES to run a judge without a scrubber
(`score_live_turn(judge_client=..., scrubber=None)` raises). The judge only
ever sees scrubbed text, so its stored reasons are scrub-safe by construction;
deterministic reasons name patterns, never matched text. Note the scrub is
identifier-focused (emails, phones, SSN/long ids, dates, subject/patient
labels) â€” it is de-identification of direct identifiers, not NLP-grade
anonymization; that is why the judge stays behind its own flag.

**Feature flags â€” default OFF (the safety gate):**

| Flag | Default | Meaning |
|---|---|---|
| `ENABLE_LIVE_EVALS` | `false` | Master switch. Off = no recording, no scoring, zero overhead. |
| `ENABLE_LIVE_JUDGE` | `false` | Judge switch. Off = deterministic-only: **zero data to Gemini** â€” the compliance-safe default that needs no sign-off. |
| `LIVE_EVAL_SAMPLE_RATE` | `1.0` | Fraction of turns scored (cost control). |
| `LIVE_EVAL_JUDGE_MODEL` | `gemini-3.5-flash` | Judge model for live grounding. |

> **âš ï¸ Sign-off required:** turning `ENABLE_LIVE_JUDGE=true` sends PHI-SCRUBBED
> excerpts of real clinical-CRM turns to the Gemini API. Do not enable it
> without explicit human sign-off from the compliance owner. The app logs a
> warning at first use as a reminder. Never enable it by default.

**Dashboard (in-house only).** `/orbit/evals` in the frontend â€” recent turns
with per-metric pass/fail, click into any turn for each metric's REASON (the
judge's "why"), 24h pass-rate trend, per-metric rates, metric/failing-only
filters, and an honest banner for disabled / deterministic-only modes. Backed
by read-only routes under `/api/assistant/live-evals/*`. Nothing is sent to
Confident AI or any external dashboard.

**Dependency permanence.** The live path imports only `agent_evals.core.live`
+ `core.gemini_client` â€” no deepeval anywhere in the production process
(google-genai is already an app dependency). deepeval remains a dev/offline
tool installed ad-hoc for golden runs.

## Caveats â€” read before trusting a green run

- **Judge-model quality caps eval quality.** G-Eval verdicts are only as good
  as Gemini 2.5 Pro's reading of your criteria. Spot-check judge reasoning by
  hand early (it is printed in the test output), and keep migrating anything
  spot-checkable into deterministic checks.
- **G-Eval anchor trap (learned the hard way):** never write numeric scores
  into criteria ("scores 1", "score 0"). G-Eval rates on an internal 0â€“10
  scale, and the literal number anchors it â€” we observed "scores 1" produce a
  0.1 verdict whose own reasoning said the reply was good. Phrase criteria as
  qualitative GOOD/BAD conditions instead.
- The Orbit trace combines two sources by design: the per-turn SSE event stream
  (every action, including unaudited reads/frontend commands) and the durable
  `audit_logs` rows (`via: agentic_assistant`) for writes. Reads and frontend
  commands (navigate, fill_form) are deliberately unaudited in the app, so the
  audit table alone is not the full per-turn trace.
- Live evals run the REAL agent against the dev database with fixture users
  (`test@gmail.com`, `dev@gmail.com`) â€” created records are cleaned up via the
  app's own routes; audit rows are retained (Part 11).
- LLM agents are nondeterministic: a live-suite failure can be a flaky model
  choice rather than a regression. Re-run the failing case before filing a bug;
  chronic flakes usually mean the golden under-specifies context.

## CI

`azure-pipelines-2.yml` runs the **deterministic self-test suite** on every
build (no secrets needed) and gates the image build on it. The **live Orbit
suite** is opt-in (set pipeline variable `RUN_ORBIT_LIVE_EVALS=true` on an
environment that has the seeded dev DB + `GEMINI_API_KEY`), since hosted CI
agents have neither the data fixtures nor the secrets by default.
