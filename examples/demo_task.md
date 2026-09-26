# Demo task: add a streak counter to the fictional habit tracker

This is a sample end-to-end run of the pipeline against the fictional
habit-tracker app in `examples/habit_tracker/`. Everything is synthetic.

## The task

> Add a `current_streak` function that computes how many consecutive days
> (ending today) a habit was checked in. It takes a list of ISO date strings
> and returns an int. An empty list returns 0.

## How to run it (mock mode — no API key, no network)

```bash
cd agentic-sdlc-orchestrator
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python - <<'EOF'
from sdlc_agents import run_pipeline, MockLLM

final = run_pipeline(
    "Add a `current_streak` function ... (task text above)",
    task_id="demo-streak",
    context_files={"tracker.py": open("examples/habit_tracker/tracker.py").read()},
    llm=MockLLM(),          # deterministic; swap for from_env() with a real key
    sandbox_dir="/tmp/demo-streak",
)
print(final["final_report"])
print("trace:", final["trace_path"])
EOF
```

## What you should see

1. **intake** validates the task and creates a sandbox directory.
2. **planner** breaks the work into steps (design, implement, test).
3. **architect** names the file to create (`solution.py` in mock mode) and the
   function contract.
4. **coder** writes the implementation into the sandbox.
5. **reviewer** checks it against the checklist and approves
   (verdict: `approved`).
6. **tester** writes a pytest file, runs it for real in the sandbox, and
   reports pass/fail.
7. **report** assembles the markdown run report.

With a real LLM key (`export OPENAI_API_KEY=...`), the same code path runs
with generated plans, designs, code, and tests instead of the canned mocks —
no code changes needed.

## Try the review loop

Force the reviewer to request changes twice before approving:

```python
from sdlc_agents import run_pipeline, MockLLM
llm = MockLLM(reviewer_verdicts=["changes_requested", "changes_requested", "approved"])
final = run_pipeline("...", task_id="demo-loop", llm=llm, sandbox_dir="/tmp/demo-loop")
# coder ran 3x, reviewer ran 3x — see tests/test_reviewer_loop.py
```

The loop is capped: after the cap is reached the pipeline proceeds to testing
regardless of the verdict, so a stubborn reviewer can never wedge the run.
