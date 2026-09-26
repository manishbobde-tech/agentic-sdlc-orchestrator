"""Persona package: planner, architect, coder, reviewer, tester.

Each persona module exposes:
  SYSTEM_PROMPT — the role definition sent to the model.
  run(state, llm) — executes the persona, returns a state-update dict.
"""
from . import architect, coder, planner, reviewer, tester

__all__ = ["planner", "architect", "coder", "reviewer", "tester"]
