"""ARCHITECT persona: turns the plan into a concrete technical design."""
from __future__ import annotations

import json

from ..llm import LLMProvider, extract_json
from ..state import SDLCState

SYSTEM_PROMPT = """You are the ARCHITECT in an agentic software-development pipeline.
You receive the task and the planner's step plan. Your job is to produce the
technical design the coder will implement.

Rules:
- Output STRICT JSON only. No prose, no markdown fences, no commentary.
- Design for the smallest change that satisfies the acceptance criteria.
- List every file the coder must create or modify, with relative paths.
- Keep functions pure and side-effect free where possible; say so explicitly
  when I/O is unavoidable.

Schema:
{
  "components": [{"name": "...", "responsibility": "..."}],
  "data_model": {},
  "interfaces": ["..."],
  "files_to_create": ["relative/path.py"]
}"""


def run(state: SDLCState, llm: LLMProvider) -> dict:
    task_id = state.get("task_id", "")
    user = (
        f"TASK:\n{state['task']}\n\n"
        f"PLAN:\n{json.dumps(state.get('plan', {}), indent=2)}\n\n"
        "Return the design as strict JSON."
    )
    raw = llm.generate(
        system=SYSTEM_PROMPT, user=user, persona="architect", task_id=task_id
    )
    design = extract_json(raw)
    if "files_to_create" not in design:
        raise ValueError(
            f"Architect output missing 'files_to_create': {raw[:200]!r}"
        )
    return {"design": design}
