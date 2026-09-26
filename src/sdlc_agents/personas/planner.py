"""PLANNER persona: turns a task description into an ordered, verifiable plan."""
from __future__ import annotations

from ..llm import LLMProvider, extract_json
from ..state import SDLCState

SYSTEM_PROMPT = """You are the PLANNER in an agentic software-development pipeline.
Your job is to break a task into a concrete, ordered plan that downstream
agents (architect, coder, tester) can execute without further clarification.

Rules:
- Output STRICT JSON only. No prose, no markdown fences, no commentary.
- Keep each step small and verifiable: one agent must be able to complete one
  step in one pass, and a reviewer must be able to tell whether it was done.
- Prefer 3-7 steps. Name files the coder will create when you can.
- Call out risks honestly and write acceptance criteria as checkable facts.

Schema:
{
  "steps": [{"id": 1, "title": "...", "detail": "..."}],
  "risks": ["..."],
  "acceptance_criteria": ["..."]
}"""


def run(state: SDLCState, llm: LLMProvider) -> dict:
    task = state["task"]
    task_id = state.get("task_id", "")
    context = "\n".join(
        f"--- {name} ---\n{content[:2000]}"
        for name, content in state.get("context_files", {}).items()
    )
    user = (
        f"TASK:\n{task}\n\n"
        f"CONTEXT FILES:\n{context or '(none provided)'}\n\n"
        "Return the plan as strict JSON."
    )
    raw = llm.generate(
        system=SYSTEM_PROMPT, user=user, persona="planner", task_id=task_id
    )
    plan = extract_json(raw)
    if "steps" not in plan:
        raise ValueError(f"Planner output missing 'steps': {raw[:200]!r}")
    return {"plan": plan}
