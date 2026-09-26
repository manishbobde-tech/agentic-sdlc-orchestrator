"""REVIEWER persona: critiques the code against a checklist, returns a verdict.

Verdict is "approved" or "changes_requested". The orchestrator loops back to
the coder on "changes_requested", up to a fixed cap.
"""
from __future__ import annotations

import json

from ..llm import LLMProvider, extract_json
from ..state import SDLCState

SYSTEM_PROMPT = """You are the REVIEWER in an agentic software-development pipeline.
You receive the design and the coder's files. Your job is to critique the code
against the checklist below and issue a verdict.

Checklist:
1. Correctness — does the code do what the task and design ask for?
2. Edge cases — empty inputs, missing files, off-by-one errors, bad types.
3. Security basics — no secrets, no network calls, no unsafe eval/exec, no
   path traversal.
4. Error handling — failures raise or return clear errors, never silently pass.
5. Style & readability — clear names, docstrings, no dead code.
6. Testability — functions are small and importable; I/O is separated.

Rules:
- Output STRICT JSON only. No prose, no markdown fences, no commentary.
- "verdict" is exactly "approved" or "changes_requested".
- Request changes ONLY for checklist failures that matter. Nits go in findings
  with severity "nit" and verdict "approved".
- Each finding: {"severity": "blocker|major|minor|nit", "file": "...",
  "line": <int|null>, "comment": "..."}.

Schema:
{
  "findings": [{"severity": "...", "file": "...", "line": 1, "comment": "..."}],
  "verdict": "approved",
  "summary": "one-paragraph rationale"
}"""

VALID_VERDICTS = {"approved", "changes_requested"}


def run(state: SDLCState, llm: LLMProvider) -> dict:
    task_id = state.get("task_id", "")
    artifacts = state.get("code_artifacts", {})
    code_dump = "\n".join(
        f"===== {name} =====\n{content[:4000]}"
        for name, content in artifacts.items()
    )
    user = (
        f"TASK:\n{state['task']}\n\n"
        f"DESIGN:\n{json.dumps(state.get('design', {}), indent=2)}\n\n"
        f"CODE UNDER REVIEW:\n{code_dump or '(no files)'}\n\n"
        "Return the review as strict JSON."
    )
    raw = llm.generate(
        system=SYSTEM_PROMPT, user=user, persona="reviewer", task_id=task_id
    )
    payload = extract_json(raw)
    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        # Fail closed: an unparseable verdict forces another look, never a
        # silent approval.
        verdict = "changes_requested"
    findings = payload.get("findings", [])
    return {
        "review_findings": findings if isinstance(findings, list) else [],
        "review_verdict": verdict,
        "review_summary": payload.get("summary", ""),
        "review_round": state.get("review_round", 0) + 1,
    }
