"""Reviewer loop-back tests: the coder is retried on 'changes requested',
but the loop is capped so a stubborn reviewer can never wedge the run."""
from sdlc_agents import MockLLM, run_pipeline
from sdlc_agents.orchestrator import MAX_REVIEW_ROUNDS
from sdlc_agents.tracing import TraceLogger


def _node_counts(trace_path):
    names = TraceLogger(trace_path).node_names()
    return {name: names.count(name) for name in set(names)}


def test_immediate_approval_runs_coder_once(tmp_path, demo_task):
    trace_path = str(tmp_path / "t.jsonl")
    final = run_pipeline(
        demo_task,
        task_id="loop-none",
        llm=MockLLM(),  # generic mock reviewer approves immediately
        trace_path=trace_path,
        sandbox_dir=str(tmp_path / "s"),
    )
    counts = _node_counts(trace_path)
    assert counts["coder"] == 1
    assert counts["reviewer"] == 1
    assert final["review_round"] == 1
    assert final["status"] == "completed"


def test_changes_requested_loops_back_to_coder(tmp_path, demo_task):
    trace_path = str(tmp_path / "t.jsonl")
    llm = MockLLM(
        reviewer_verdicts=["changes_requested", "changes_requested", "approved"]
    )
    final = run_pipeline(
        demo_task,
        task_id="loop-twice",
        llm=llm,
        trace_path=trace_path,
        sandbox_dir=str(tmp_path / "s"),
    )
    counts = _node_counts(trace_path)
    assert counts["coder"] == 3  # initial + 2 loop-backs
    assert counts["reviewer"] == 3
    assert final["review_verdict"] == "approved"
    assert final["review_round"] == 3
    assert final["status"] == "completed"


def test_review_loop_is_capped(tmp_path, demo_task):
    """A reviewer that never approves still lets the pipeline finish."""
    trace_path = str(tmp_path / "t.jsonl")
    llm = MockLLM(reviewer_verdicts=["changes_requested"] * 10)
    final = run_pipeline(
        demo_task,
        task_id="loop-capped",
        llm=llm,
        trace_path=trace_path,
        sandbox_dir=str(tmp_path / "s"),
    )
    counts = _node_counts(trace_path)
    # 1 initial coder run + (MAX_REVIEW_ROUNDS - 1) loop-backs.
    assert counts["coder"] == MAX_REVIEW_ROUNDS
    assert counts["reviewer"] == MAX_REVIEW_ROUNDS
    assert final["review_verdict"] == "changes_requested"
    # Pipeline proceeds to testing anyway — it never wedges.
    assert counts["tester"] == 1
    assert final["status"] == "completed"


def test_reviewer_fail_closed_on_garbage_verdict(tmp_path, demo_task):
    fixtures = {
        ("reviewer", "garbage"): '{"verdict": "maybe", "findings": []}',
    }
    llm = MockLLM(fixtures=fixtures)
    final = run_pipeline(
        demo_task,
        task_id="garbage",
        llm=llm,
        trace_path=str(tmp_path / "t.jsonl"),
        sandbox_dir=str(tmp_path / "s"),
    )
    # Unparseable verdict must not become a silent approval.
    assert final["review_verdict"] == "changes_requested"
