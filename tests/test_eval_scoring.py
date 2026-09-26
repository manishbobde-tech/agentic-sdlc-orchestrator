"""Eval scoring tests: deterministic checks and the qualitative judge."""
import json
import os

import pytest

from evals.run_evals import (
    evaluate_task,
    judge_qualitative,
    load_tasks,
    score_deterministic,
)
from sdlc_agents import MockLLM

GOLDEN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "evals",
    "golden",
)


@pytest.fixture()
def golden_task():
    with open(os.path.join(GOLDEN_DIR, "habit-01_add_streak_counter.json")) as fh:
        return json.load(fh)


def _passing_state():
    return {
        "code_artifacts": {"streak.py": "def current_streak(*a, **k):\n    return 0\n"},
        "test_results": {"passed": 2, "failed": 0},
    }


def test_all_six_golden_tasks_load():
    tasks = load_tasks()
    assert len(tasks) == 6
    for task in tasks:
        assert task["id"] and task["task"] and task["title"]
        assert task["rubric"]["deterministic"]
        assert isinstance(task["rubric"].get("qualitative", []), list)


def test_load_tasks_filter():
    tasks = load_tasks("habit-03")
    assert len(tasks) == 1 and tasks[0]["id"] == "habit-03"
    with pytest.raises(SystemExit):
        load_tasks("no-such-task")


def test_deterministic_all_pass(golden_task):
    results = score_deterministic(golden_task, _passing_state())
    assert len(results) == 3
    assert all(r["passed"] for r in results)


def test_deterministic_failures_reported(golden_task):
    state = {
        "code_artifacts": {"streak.py": "# no function here\n"},
        "test_results": {"passed": 0, "failed": 1},
    }
    results = score_deterministic(golden_task, state)
    by_type = {r["check"]["type"]: r for r in results}
    assert by_type["file_exists"]["passed"] is True
    assert by_type["file_contains"]["passed"] is False
    assert "not found" in by_type["file_contains"]["detail"]
    assert by_type["tests_pass"]["passed"] is False


def test_deterministic_unknown_check_type_fails_closed(golden_task):
    task = {
        "rubric": {"deterministic": [{"type": "telepathy", "path": "x.py"}]}
    }
    results = score_deterministic(task, _passing_state())
    assert results[0]["passed"] is False
    assert "unknown check type" in results[0]["detail"]


def test_qualitative_mock_judge_auto_passes(golden_task):
    scored = judge_qualitative(golden_task, _passing_state(), MockLLM())
    assert len(scored) == 2
    assert all(s["passed"] for s in scored)
    assert all("Mock judge" in s["rationale"] for s in scored)


def test_evaluate_task_overall_verdict(golden_task):
    ok_result = evaluate_task(golden_task, _passing_state(), MockLLM())
    assert ok_result["passed"] is True
    assert ok_result["task_id"] == "habit-01"

    bad_state = {"code_artifacts": {}, "test_results": {"passed": 0, "failed": 0}}
    bad_result = evaluate_task(golden_task, bad_state, MockLLM())
    assert bad_result["passed"] is False
