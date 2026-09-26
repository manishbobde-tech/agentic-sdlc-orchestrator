"""LangGraph wiring for the Agentic SDLC Orchestrator.

Pipeline:
    intake -> approve_code (HITL) -> planner -> architect -> coder
        -> reviewer -> (changes_requested & rounds left ? coder : tester)
        -> approve_report (HITL) -> report -> END

Every node execution is traced to JSONL (timestamps, latency, token
estimates, verdicts). Human-in-the-loop checkpoints are plain callbacks:
``on_approval(stage, snapshot) -> bool``. The scaffold default auto-approves;
pass your own callback to pause for a human (a denial ends the run with
status "held_for_review").
"""
from __future__ import annotations

import os
import tempfile
import time
from typing import Callable

from langgraph.graph import END, StateGraph

from .llm import LLMProvider, from_env
from .personas import architect, coder, planner, reviewer, tester
from .state import SDLCState
from .tracing import TraceLogger

MAX_REVIEW_ROUNDS = 4  # 1 initial review + up to 3 "changes requested" loop-backs

ApprovalHook = Callable[[str, dict], bool]


def default_approval(stage: str, snapshot: dict) -> bool:
    """Scaffold default: auto-approve every checkpoint."""
    return True


def build_graph(
    llm: LLMProvider,
    trace: TraceLogger | None = None,
    on_approval: ApprovalHook | None = None,
):
    on_approval = on_approval or default_approval

    def traced(name: str, fn):
        def wrapper(state: SDLCState) -> dict:
            start = time.perf_counter()
            update = fn(state)
            latency_ms = (time.perf_counter() - start) * 1000
            verdict = ""
            if name == "reviewer":
                verdict = update.get("review_verdict", "")
            elif name == "tester":
                tr = update.get("test_results", {})
                verdict = f"{tr.get('passed', 0)}p/{tr.get('failed', 0)}f"
            elif name in ("approve_code", "approve_report"):
                verdict = (
                    "approved"
                    if update.get("approvals", {}).get(
                        "before_code_write"
                        if name == "approve_code"
                        else "before_final_report",
                        True,
                    )
                    else "denied"
                )
            tokens = (
                TraceLogger.estimate_tokens(str(update)) if trace else 0
            )
            if trace:
                trace.log(name, latency_ms, tokens, verdict)
            return update

        return wrapper

    # ---- nodes ---------------------------------------------------------
    def intake(state: SDLCState) -> dict:
        task = (state.get("task") or "").strip()
        if not task:
            raise ValueError("intake: 'task' must be a non-empty string")
        sandbox = state.get("sandbox_dir") or tempfile.mkdtemp(prefix="sdlc_")
        os.makedirs(sandbox, exist_ok=True)
        return {
            "task_id": state.get("task_id", "task"),
            "task": task,
            "sandbox_dir": sandbox,
            "status": "running",
            "review_round": 0,
            "approvals": {},
        }

    def approve_code(state: SDLCState) -> dict:
        ok = bool(on_approval("before_code_write", dict(state)))
        approvals = {**state.get("approvals", {}), "before_code_write": ok}
        return {
            "approvals": approvals,
            "status": "running" if ok else "held_for_review",
        }

    def approve_report(state: SDLCState) -> dict:
        ok = bool(on_approval("before_final_report", dict(state)))
        approvals = {**state.get("approvals", {}), "before_final_report": ok}
        return {
            "approvals": approvals,
            "status": "running" if ok else "held_for_review",
        }

    def report(state: SDLCState) -> dict:
        plan = state.get("plan", {})
        design = state.get("design", {})
        artifacts = state.get("code_artifacts", {})
        findings = state.get("review_findings", [])
        tr = state.get("test_results", {})
        lines = [
            f"# SDLC Run Report — {state.get('task_id', 'task')}",
            "",
            f"**Task:** {state.get('task', '')}",
            f"**Status:** {state.get('status', 'running')}",
            f"**Review rounds:** {state.get('review_round', 0)} "
            f"(verdict: {state.get('review_verdict', 'n/a')})",
            "",
            "## Plan",
            *[f"- {s.get('title', '')}" for s in plan.get("steps", [])],
            "",
            "## Design",
            f"Files: {', '.join(design.get('files_to_create', [])) or 'n/a'}",
            "",
            "## Code artifacts",
            *[f"- `{name}`" for name in sorted(artifacts)],
            "",
            "## Review findings",
            *[
                f"- [{f.get('severity', '?')}] `{f.get('file', '?')}`: "
                f"{f.get('comment', '')}"
                for f in findings
            ],
            "" if findings else "- none",
            "",
            "## Test results",
            f"Passed: {tr.get('passed', 0)}, Failed: {tr.get('failed', 0)}",
            f"Tests: {', '.join(tr.get('tests_written', [])) or 'n/a'}",
        ]
        return {"final_report": "\n".join(lines), "status": "completed"}

    # ---- graph ---------------------------------------------------------
    builder = StateGraph(SDLCState)
    builder.add_node("intake", traced("intake", intake))
    builder.add_node("approve_code", traced("approve_code", approve_code))
    builder.add_node("planner", traced("planner", lambda s: planner.run(s, llm)))
    builder.add_node(
        "architect", traced("architect", lambda s: architect.run(s, llm))
    )
    builder.add_node("coder", traced("coder", lambda s: coder.run(s, llm)))
    builder.add_node(
        "reviewer", traced("reviewer", lambda s: reviewer.run(s, llm))
    )
    builder.add_node("tester", traced("tester", lambda s: tester.run(s, llm)))
    builder.add_node(
        "approve_report", traced("approve_report", approve_report)
    )
    builder.add_node("report", traced("report", report))

    builder.set_entry_point("intake")
    builder.add_edge("intake", "approve_code")
    builder.add_conditional_edges(
        "approve_code",
        lambda s: "held" if s.get("status") == "held_for_review" else "go",
        {"held": END, "go": "planner"},
    )
    builder.add_edge("planner", "architect")
    builder.add_edge("architect", "coder")
    builder.add_edge("coder", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        lambda s: (
            "revise"
            if s.get("review_verdict") == "changes_requested"
            and s.get("review_round", 0) < MAX_REVIEW_ROUNDS
            else "test"
        ),
        {"revise": "coder", "test": "tester"},
    )
    builder.add_edge("tester", "approve_report")
    builder.add_conditional_edges(
        "approve_report",
        lambda s: "held" if s.get("status") == "held_for_review" else "go",
        {"held": END, "go": "report"},
    )
    builder.add_edge("report", END)
    return builder.compile()


def run_pipeline(
    task: str,
    *,
    task_id: str = "task",
    context_files: dict[str, str] | None = None,
    llm: LLMProvider | None = None,
    trace_path: str | None = None,
    sandbox_dir: str | None = None,
    on_approval: ApprovalHook | None = None,
) -> dict:
    """Run the full pipeline for one task; return the final state dict."""
    llm = llm or from_env()
    trace_path = trace_path or os.path.join(
        "traces", f"trace-{task_id}-{int(time.time())}.jsonl"
    )
    trace = TraceLogger(trace_path)
    graph = build_graph(llm, trace=trace, on_approval=on_approval)
    initial: SDLCState = {
        "task_id": task_id,
        "task": task,
        "context_files": context_files or {},
    }
    if sandbox_dir:
        initial["sandbox_dir"] = sandbox_dir
    final = graph.invoke(initial)
    final["trace_path"] = trace_path
    return final
