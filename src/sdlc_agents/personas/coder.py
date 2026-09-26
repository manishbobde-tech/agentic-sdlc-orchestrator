"""CODER persona: writes implementation files into the sandbox directory."""
from __future__ import annotations

import json
import os

from ..llm import LLMProvider, extract_json
from ..state import SDLCState

SYSTEM_PROMPT = """You are the CODER in an agentic software-development pipeline.
You receive the task, the plan, and the architect's design. Your job is to
write the implementation files.

Rules:
- Output STRICT JSON only. No prose, no markdown fences, no commentary.
- "files" maps a relative path (e.g. "streak.py") to the file's full content.
- Write complete, runnable files — no placeholders, no TODOs, no ellipses.
- No network calls, no secrets, no hardcoded credentials in the code.
- Keep functions small, typed where it helps, and documented with docstrings.

Schema:
{
  "files": {"relative/path.py": "<full file content>"},
  "notes": "brief summary of what was implemented"
}"""


def _write_files(sandbox_dir: str, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        # Guard against path traversal: keep everything inside the sandbox.
        abs_path = os.path.abspath(os.path.join(sandbox_dir, rel_path))
        if not abs_path.startswith(os.path.abspath(sandbox_dir) + os.sep):
            raise ValueError(f"Refusing to write outside sandbox: {rel_path}")
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content if content.endswith("\n") else content + "\n")


def run(state: SDLCState, llm: LLMProvider) -> dict:
    task_id = state.get("task_id", "")
    sandbox = state["sandbox_dir"]
    user = (
        f"TASK:\n{state['task']}\n\n"
        f"PLAN:\n{json.dumps(state.get('plan', {}), indent=2)}\n\n"
        f"DESIGN:\n{json.dumps(state.get('design', {}), indent=2)}\n\n"
        "Return the implementation as strict JSON."
    )
    raw = llm.generate(
        system=SYSTEM_PROMPT, user=user, persona="coder", task_id=task_id
    )
    payload = extract_json(raw)
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"Coder output missing 'files': {raw[:200]!r}")
    _write_files(sandbox, files)
    return {
        "code_artifacts": files,
        "coder_notes": payload.get("notes", ""),
    }
