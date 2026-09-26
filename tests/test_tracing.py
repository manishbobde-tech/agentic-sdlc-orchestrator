"""Trace logger unit tests: JSONL format, fields, token estimates."""
import json
import os

from sdlc_agents.tracing import TraceLogger


def test_log_writes_valid_jsonl(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    trace = TraceLogger(path)
    record = trace.log("coder", latency_ms=12.5, tokens=100, verdict="ok",
                       detail={"files": 2})
    assert os.path.exists(path)
    assert record["node"] == "coder"
    assert record["latency_ms"] == 12.5
    assert record["tokens_est"] == 100
    assert record["verdict"] == "ok"
    assert record["detail"] == {"files": 2}
    assert len(record["run_id"]) == 8
    with open(path, encoding="utf-8") as fh:
        assert json.loads(fh.readline())["node"] == "coder"


def test_read_all_and_node_names(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    trace = TraceLogger(path)
    trace.log("planner", 1.0, 10)
    trace.log("coder", 2.0, 20, verdict="done")
    assert trace.node_names() == ["planner", "coder"]
    assert len(trace.read_all()) == 2


def test_read_all_missing_file_returns_empty(tmp_path):
    trace = TraceLogger(str(tmp_path / "nope.jsonl"))
    assert trace.read_all() == []
    assert trace.node_names() == []


def test_estimate_tokens_scales_with_text():
    assert TraceLogger.estimate_tokens("") == 0
    short = TraceLogger.estimate_tokens("hello")
    long = TraceLogger.estimate_tokens("hello" * 100)
    assert long > short
    assert TraceLogger.estimate_tokens("ab", "cd") == 1  # 4 chars -> 1 token
