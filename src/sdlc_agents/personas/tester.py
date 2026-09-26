"""TESTER persona: writes pytest tests for the new code and runs them.

The model proposes test files; this module writes them into the sandbox and
executes pytest in a subprocess, then parses the pass/fail counts. The test
run is real — a green result means the generated code actually executed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from ..llm import LLMProvider, extract_json
from ..state import SDLCState

SYSTEM_PROMPT = """You are the TESTER in an agentic software-development pipeline.
You receive the task and the coder's files. Your job is to write pytest tests
that verify the new behavior.

Rules:
- Output STRICT JSON only. No prose, no markdown fences, no commentary.
- "tests" maps a relative path (e.g. "test_streak.py") to file content.
- Tests must import from the implementation modules directly
  (e.g. "from streak import current_streak"). The tests run with the sandbox
  directory as the working directory, so top-level modules are importable.
- Cover the happy path plus at least one edge case (empty input, boundary).
- Do not write tests that need network, files outside the sandbox, or secrets.

Schema:
{
  "tests": {"test_<name>.py": "<full test file content>"}
}"""


def _write_files(sandbox_dir: str, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        abs_path = os.path.abspath(os.path.join(sandbox_dir, rel_path))
        if not abs_path.startswith(os.path.abspath(sandbox_dir) + os.sep):
            raise ValueError(f"Refusing to write outside sandbox: {rel_path}")
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content if content.endswith("\n") else content + "\n")


def _run_pytest(sandbox_dir: str) -> tuple[int, int, str]:
    """Run pytest in the sandbox; return (passed, failed, output_tail)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=sandbox_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (proc.stdout + proc.stderr)[-3000:]
    passed = failed = 0
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    if proc.returncode != 0 and passed == 0 and failed == 0:
        # pytest errored before collecting (import error, syntax error, ...).
        failed = 1
    return passed, failed, output


def run(state: SDLCState, llm: LLMProvider) -> dict:
    task_id = state.get("task_id", "")
    sandbox = state["sandbox_dir"]
    artifacts = state.get("code_artifacts", {})
    code_dump = "\n".join(
        f"===== {name} =====\n{content[:4000]}"
        for name, content in artifacts.items()
    )
    user = (
        f"TASK:\n{state['task']}\n\n"
        f"CODE UNDER TEST:\n{code_dump or '(no files)'}\n\n"
        "Return the tests as strict JSON."
    )
    raw = llm.generate(
        system=SYSTEM_PROMPT, user=user, persona="tester", task_id=task_id
    )
    payload = extract_json(raw)
    tests = payload.get("tests")
    if not isinstance(tests, dict) or not tests:
        raise ValueError(f"Tester output missing 'tests': {raw[:200]!r}")
    _write_files(sandbox, tests)
    passed, failed, output = _run_pytest(sandbox)
    return {
        "test_results": {
            "tests_written": sorted(tests.keys()),
            "passed": passed,
            "failed": failed,
            "output": output,
        }
    }
