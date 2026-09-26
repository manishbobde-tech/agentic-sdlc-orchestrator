"""Shared graph state for the Agentic SDLC Orchestrator.

The state is a plain TypedDict so LangGraph can merge per-node updates.
Every field documents what the pipeline stage that writes it promises.
"""
from __future__ import annotations

from typing import TypedDict


class SDLCState(TypedDict, total=False):
    # --- intake ---
    task_id: str            # short id for the run, e.g. "habit-01"
    task: str               # natural-language task description
    context_files: dict[str, str]  # filename -> file contents (synthetic context)
    sandbox_dir: str        # directory where coder/tester write files
    status: str             # running | held_for_review | completed | failed

    # --- planner ---
    plan: dict              # {"steps": [...], "risks": [...], "acceptance_criteria": [...]}

    # --- architect ---
    design: dict            # {"components": [...], "data_model": {...},
                            #  "interfaces": [...], "files_to_create": [...]}

    # --- coder ---
    code_artifacts: dict[str, str]  # relative path -> file contents

    # --- reviewer ---
    review_findings: list[dict]  # [{"severity","file","line","comment"}]
    review_verdict: str          # "approved" | "changes_requested"
    review_round: int            # incremented each reviewer visit (cap enforced)

    # --- tester ---
    test_results: dict      # {"tests_written": [...], "passed": int,
                            #  "failed": int, "output": str}

    # --- human-in-the-loop ---
    approvals: dict[str, bool]   # stage name -> approved?

    # --- report ---
    final_report: str

    # --- tracing (filled by run_pipeline, not by graph nodes) ---
    trace_path: str
