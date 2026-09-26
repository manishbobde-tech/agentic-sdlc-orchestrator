# Agentic SDLC Orchestrator

A portfolio scaffold (v0.1) for a **multi-persona agentic software pipeline**:
five LLM personas — planner, architect, coder, reviewer, tester — wired into a
[LangGraph](https://github.com/langchain-ai/langgraph) state machine, with
JSONL tracing, human-in-the-loop checkpoints, and a **golden-dataset eval
harness** that scores every run with deterministic checks plus an LLM judge.

The point of this repo is not the demo app. It's the *machinery around the
agents*: typed shared state, a review loop with a hard cap, real test
execution (not vibes), per-node trace logs, and evals you can run in CI with
zero network access.

## Architecture

```
 intake ──▶ approve_code (HITL) ──▶ planner ──▶ architect ──▶ coder
                                                                    │
                              ┌─────────────────────────────────────┘
                              ▼
                          reviewer ── changes_requested ──▶ coder   (loop, max 3x)
                              │
                    approved / cap reached
                              ▼
                           tester ──▶ approve_report (HITL) ──▶ report ──▶ END
```

- **intake** validates the task and creates an isolated sandbox directory.
- **approve_code / approve_report** are human-in-the-loop gates. They call an
  `on_approval(stage, snapshot) -> bool` callback; the scaffold default
  auto-approves, a denial ends the run as `held_for_review`.
- **reviewer → coder loop**: `changes_requested` routes back to the coder, up
  to 3 loop-backs (4 review rounds max). A reviewer that never approves
  cannot wedge the run — the pipeline proceeds to testing after the cap.
- **tester** writes pytest files into the sandbox and *actually runs them*
  in a subprocess. A green result means the generated code executed.
- Every node logs to JSONL: timestamp, latency, estimated tokens, verdict.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 1. Run the test suite (deterministic mock LLM, no network)
pytest

# 2. Run the golden eval suite in CI mode (mock LLM, no network)
python -m evals.run_evals

# 3. Run one pipeline end-to-end (mock mode)
python - <<'EOF'
from sdlc_agents import run_pipeline, MockLLM
final = run_pipeline(
    "Add a `current_streak(dates)` function returning consecutive-day count.",
    task_id="demo",
    llm=MockLLM(),
    sandbox_dir="/tmp/sdlc-demo",
)
print(final["final_report"])
EOF
```

### With a real model

The same code path works against any OpenAI-compatible endpoint — no code
changes, just environment:

```bash
export OPENAI_API_KEY=...                 # required
export SDLC_LLM_MODEL=gpt-4o-mini         # optional, default shown
export SDLC_LLM_BASE_URL=https://...      # optional, for compatible endpoints
python -m evals.run_evals --real
```

## Eval philosophy

Demos lie; evals don't. Every agent change in this repo is expected to move a
number, and the harness is built so that number is trustworthy:

- **Golden dataset** (`evals/golden/`): 6 synthetic SDLC tasks, each with a
  task description, context files, and a scoring rubric. Fixed inputs, fixed
  expectations — the only thing that changes between runs is the pipeline.
- **Deterministic checks first**: `file_exists`, `file_contains`,
  `tests_pass`. These are machine-verifiable facts about the run, not model
  opinions. A run cannot pass evals on charm.
- **LLM-as-judge second**: qualitative criteria (edge cases, purity, error
  handling) are scored per-criterion by a judge model with a strict JSON
  schema. Judge failures fail closed (criterion scores 0).
- **CI mode**: with no API key, the harness runs the full pipeline per task
  using the deterministic `MockLLM` — real file writes, real pytest
  execution, scripted model responses. `pytest` and
  `python -m evals.run_evals` are both green with no network.

## What's synthetic

Everything. The demo domain is a fictional personal habit-tracker app. All
tasks, code, plans, and reviews in this repo are invented for demonstration.
There are no real companies, employers, domains, datasets, or credentials
anywhere in this project, and no API keys are committed (see `.gitignore`).

## Project layout

```
src/sdlc_agents/
  state.py          shared TypedDict graph state
  llm.py            provider abstraction (mock + OpenAI-compatible) + JSON parsing
  tracing.py        JSONL trace logger (latency, token estimates, verdicts)
  orchestrator.py   LangGraph wiring, review loop, HITL checkpoints, run_pipeline()
  personas/         planner, architect, coder, reviewer, tester (prompt + run())
evals/
  golden/           6 synthetic tasks with rubrics
  run_evals.py      harness: `python -m evals.run_evals [--real] [--task ID]`
  fixtures_mock.py  deterministic mock fixtures aligned to the golden rubrics
examples/
  habit_tracker/    tiny fictional CLI app the agents operate on
  demo_task.md      annotated sample run
tests/              pytest suite (graph, review loop cap, tracing, eval scoring)
```

## Roadmap

- [ ] Richer golden tasks (multi-file refactors, bug-fix from failing tests)
- [ ] Cost/latency dashboard over `traces/*.jsonl`
- [ ] Parallel persona fan-out (e.g. reviewer + tester concurrently)
- [ ] Persistent memory across runs (plan/design library)
- [ ] Regression mode: fail CI when the golden pass rate drops vs. baseline
- [ ] Real HITL UI (approve/deny with diff view) instead of the callback stub
