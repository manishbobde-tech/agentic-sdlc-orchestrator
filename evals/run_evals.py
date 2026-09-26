"""Eval harness for the Agentic SDLC Orchestrator.

For each task in ``evals/golden/*.json`` it runs the full pipeline, then
scores it two ways:

1. Deterministic checks — machine-verifiable facts about the run:
   ``file_exists``, ``file_contains``, ``tests_pass``.
2. Qualitative rubric — each criterion is scored pass/fail. In CI (mock)
   mode the judge auto-passes with a note; with ``--real`` an LLM judges
   each criterion against the produced artifacts.

Usage:
    python -m evals.run_evals            # mock/CI mode, no network
    python -m evals.run_evals --real     # real LLM (needs OPENAI_API_KEY)
    python -m evals.run_evals --task habit-01
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
)

from sdlc_agents import run_pipeline  # noqa: E402
from sdlc_agents.llm import LLMProvider, extract_json, from_env  # noqa: E402
from evals.fixtures_mock import build_mock_llm  # noqa: E402

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

JUDGE_SYSTEM = """You are an impartial code-review judge. Score ONE rubric
criterion against the produced code artifacts.

Rules:
- Output STRICT JSON only: {"passed": true|false, "rationale": "one sentence"}.
- "passed" is true only if the artifacts clearly satisfy the criterion.
- Do not reward effort or intent, only the actual code."""


def load_tasks(task_id: str | None = None) -> list[dict]:
    paths = sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.json")))
    tasks = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            task = json.load(fh)
        if task_id is None or task["id"] == task_id:
            tasks.append(task)
    if task_id and not tasks:
        raise SystemExit(f"No golden task with id {task_id!r}")
    return tasks


def score_deterministic(task: dict, final_state: dict) -> list[dict]:
    """Evaluate machine-checkable facts about the run."""
    results = []
    artifacts = final_state.get("code_artifacts", {}) or {}
    test_results = final_state.get("test_results", {}) or {}
    for check in task["rubric"]["deterministic"]:
        ctype = check.get("type")
        if ctype == "file_exists":
            ok = check["path"] in artifacts
            detail = "present" if ok else "missing"
        elif ctype == "file_contains":
            ok = check["text"] in artifacts.get(check["path"], "")
            detail = "found" if ok else "not found"
        elif ctype == "tests_pass":
            passed = test_results.get("passed", 0)
            failed = test_results.get("failed", 0)
            ok = passed >= check.get("min_passed", 1) and failed == 0
            detail = f"{passed} passed, {failed} failed"
        else:
            ok, detail = False, f"unknown check type: {ctype!r}"
        results.append({"check": check, "passed": ok, "detail": detail})
    return results


def judge_qualitative(
    task: dict, final_state: dict, llm: LLMProvider
) -> list[dict]:
    """Score each qualitative criterion pass/fail (LLM-as-judge)."""
    criteria = task["rubric"].get("qualitative", [])
    if llm.is_mock:
        return [
            {
                "criterion": c,
                "passed": True,
                "rationale": "Mock judge: auto-pass in CI mode.",
            }
            for c in criteria
        ]
    artifacts = final_state.get("code_artifacts", {}) or {}
    code_dump = "\n".join(
        f"===== {name} =====\n{content[:3000]}"
        for name, content in artifacts.items()
    )
    scored = []
    for criterion in criteria:
        user = (
            f"CRITERION:\n{criterion}\n\n"
            f"CODE ARTIFACTS:\n{code_dump or '(none)'}\n\n"
            "Return your score as strict JSON."
        )
        try:
            payload = extract_json(
                llm.generate(system=JUDGE_SYSTEM, user=user)
            )
            passed = bool(payload.get("passed", False))
            rationale = str(payload.get("rationale", ""))[:200]
        except Exception as exc:  # judge failure fails closed
            passed, rationale = False, f"judge error: {exc}"
        scored.append(
            {"criterion": criterion, "passed": passed, "rationale": rationale}
        )
    return scored


def evaluate_task(task: dict, final_state: dict, llm: LLMProvider) -> dict:
    det = score_deterministic(task, final_state)
    qual = judge_qualitative(task, final_state, llm)
    passed = all(r["passed"] for r in det) and all(r["passed"] for r in qual)
    return {
        "task_id": task["id"],
        "title": task["title"],
        "det": det,
        "qual": qual,
        "passed": passed,
    }


def print_report(results: list[dict]) -> None:
    print(f"\n{'Task':<28} {'Det':>7} {'Qual':>7}  Verdict")
    print("-" * 56)
    for r in results:
        det = f"{sum(x['passed'] for x in r['det'])}/{len(r['det'])}"
        qual = f"{sum(x['passed'] for x in r['qual'])}/{len(r['qual'])}"
        verdict = "PASS" if r["passed"] else "FAIL"
        print(f"{r['task_id']:<28} {det:>7} {qual:>7}  {verdict}")
        for d in r["det"]:
            if not d["passed"]:
                print(f"    ✗ det {d['check']} — {d['detail']}")
        for q in r["qual"]:
            if not q["passed"]:
                print(f"    ✗ qual {q['criterion'][:80]} — {q['rationale']}")
    passed = sum(r["passed"] for r in results)
    total = len(results)
    pct = (100.0 * passed / total) if total else 0.0
    print("-" * 56)
    print(f"Pass rate: {passed}/{total} ({pct:.1f}%)\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the golden eval suite.")
    parser.add_argument("--real", action="store_true",
                        help="Use the real LLM (needs OPENAI_API_KEY).")
    parser.add_argument("--task", default=None,
                        help="Run a single golden task by id.")
    args = parser.parse_args(argv)

    tasks = load_tasks(args.task)
    llm = from_env() if args.real else build_mock_llm(tasks)
    mode = "real LLM" if args.real else "mock LLM (CI mode)"
    print(f"Running {len(tasks)} golden task(s) with {mode}...")

    results = []
    for task in tasks:
        sandbox = tempfile.mkdtemp(prefix=f"eval-{task['id']}-")
        final = run_pipeline(
            task["task"],
            task_id=task["id"],
            context_files=task.get("context_files", {}),
            llm=llm,
            sandbox_dir=sandbox,
            trace_path=os.path.join("traces", f"eval-{task['id']}.jsonl"),
        )
        results.append(evaluate_task(task, final, llm))
    print_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
