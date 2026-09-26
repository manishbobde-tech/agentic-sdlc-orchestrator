"""End-to-end graph wiring tests with the deterministic mock LLM."""
import json
import os

from sdlc_agents import MockLLM, run_pipeline
from sdlc_agents.tracing import TraceLogger

EXPECTED_ORDER = [
    "intake",
    "approve_code",
    "planner",
    "architect",
    "coder",
    "reviewer",
    "tester",
    "approve_report",
    "report",
]


def test_full_pipeline_happy_path(tmp_path, demo_task):
    trace_path = str(tmp_path / "trace.jsonl")
    sandbox = str(tmp_path / "sandbox")
    final = run_pipeline(
        demo_task,
        task_id="demo",
        context_files={"tracker.py": "# synthetic context"},
        llm=MockLLM(),
        trace_path=trace_path,
        sandbox_dir=sandbox,
    )

    assert final["status"] == "completed"
    assert final["review_verdict"] == "approved"
    assert final["review_round"] == 1
    assert "plan" in final and "steps" in final["plan"]
    assert "design" in final and "files_to_create" in final["design"]
    assert "solution.py" in final["code_artifacts"]
    assert os.path.exists(os.path.join(sandbox, "solution.py"))
    tr = final["test_results"]
    assert tr["passed"] >= 1 and tr["failed"] == 0
    assert "SDLC Run Report" in final["final_report"]
    assert final["trace_path"] == trace_path


def test_node_execution_order_and_trace(tmp_path, demo_task):
    trace_path = str(tmp_path / "trace.jsonl")
    run_pipeline(
        demo_task,
        task_id="demo",
        llm=MockLLM(),
        trace_path=trace_path,
        sandbox_dir=str(tmp_path / "sandbox"),
    )
    trace = TraceLogger(trace_path)
    assert trace.node_names() == EXPECTED_ORDER
    for record in trace.read_all():
        assert record["latency_ms"] >= 0
        assert record["tokens_est"] >= 0
        assert "ts" in record and "run_id" in record
    reviewer_records = [r for r in trace.read_all() if r["node"] == "reviewer"]
    assert reviewer_records[0]["verdict"] == "approved"
    tester_records = [r for r in trace.read_all() if r["node"] == "tester"]
    assert "p/" in tester_records[0]["verdict"]


def test_empty_task_rejected(tmp_path):
    try:
        run_pipeline(
            "   ",
            task_id="empty",
            llm=MockLLM(),
            trace_path=str(tmp_path / "t.jsonl"),
            sandbox_dir=str(tmp_path / "s"),
        )
    except ValueError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("expected ValueError for empty task")


def test_human_checkpoint_denial_holds_run(tmp_path, demo_task):
    calls = []

    def deny_before_code(stage, snapshot):
        calls.append(stage)
        return False  # human says no

    final = run_pipeline(
        demo_task,
        task_id="demo-held",
        llm=MockLLM(),
        trace_path=str(tmp_path / "t.jsonl"),
        sandbox_dir=str(tmp_path / "s"),
        on_approval=deny_before_code,
    )
    assert final["status"] == "held_for_review"
    assert calls == ["before_code_write"]
    assert "code_artifacts" not in final  # coder never ran
    assert final["approvals"]["before_code_write"] is False


def test_trace_file_is_valid_jsonl(tmp_path, demo_task):
    trace_path = str(tmp_path / "trace.jsonl")
    run_pipeline(
        demo_task,
        task_id="demo",
        llm=MockLLM(),
        trace_path=trace_path,
        sandbox_dir=str(tmp_path / "s"),
    )
    with open(trace_path, encoding="utf-8") as fh:
        for line in fh:
            json.loads(line)  # must not raise
