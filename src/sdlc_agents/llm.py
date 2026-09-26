"""LLM provider abstraction.

All persona code talks to an ``LLMProvider``. Two implementations ship:

* :class:`MockLLM` — deterministic, scripted responses. No network. This is
  what the pytest suite and the eval harness use in CI mode.
* :class:`OpenAICompatibleLLM` — talks to any OpenAI-compatible chat
  completions endpoint. Model, key, and base URL come from the environment
  (``SDLC_LLM_MODEL``, ``OPENAI_API_KEY``, ``SDLC_LLM_BASE_URL``).

:func:`from_env` returns the real provider when a key is present, else the
mock, so the same code path works in CI and in live demos.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from abc import ABC, abstractmethod

from langchain_core.messages import HumanMessage, SystemMessage

_ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant"}


class LLMProvider(ABC):
    """Minimal chat interface every persona uses."""

    @abstractmethod
    def generate(
        self, *, system: str, user: str, persona: str = "", task_id: str = ""
    ) -> str:
        """Return the model's raw text response."""
        raise NotImplementedError

    @property
    def is_mock(self) -> bool:
        return False


class MockLLM(LLMProvider):
    """Deterministic test double.

    ``fixtures`` maps ``(persona, task_id)`` -> canned response string.
    Wildcards are supported: ``(persona, "*")``, ``("*", task_id)``,
    ``("*", "*")``. When ``reviewer_verdicts`` is non-empty, reviewer calls
    consume verdicts from it in order (used to exercise the review loop).
    """

    def __init__(
        self,
        fixtures: dict[tuple[str, str], str] | None = None,
        reviewer_verdicts: list[str] | None = None,
    ) -> None:
        self.fixtures = dict(fixtures or {})
        self.reviewer_verdicts = list(reviewer_verdicts or [])

    @property
    def is_mock(self) -> bool:
        return True

    def generate(
        self, *, system: str, user: str, persona: str = "", task_id: str = ""
    ) -> str:
        if persona == "reviewer" and self.reviewer_verdicts:
            verdict = self.reviewer_verdicts.pop(0)
            findings = (
                []
                if verdict == "approved"
                else [
                    {
                        "severity": "major",
                        "file": "solution.py",
                        "line": 1,
                        "comment": "Mock finding: handle empty input explicitly.",
                    }
                ]
            )
            return json.dumps(
                {
                    "findings": findings,
                    "verdict": verdict,
                    "summary": f"Mock reviewer verdict: {verdict}.",
                }
            )
        for key in (
            (persona, task_id),
            (persona, "*"),
            ("*", task_id),
            ("*", "*"),
        ):
            if key in self.fixtures:
                return self.fixtures[key]
        return self._generic(persona, user, task_id)

    def _generic(self, persona: str, user: str, task_id: str) -> str:
        first_line = (user.strip().splitlines() or [""])[0][:120]
        if persona == "planner":
            return json.dumps(
                {
                    "steps": [
                        {"id": 1, "title": "Understand the task",
                         "detail": first_line},
                        {"id": 2, "title": "Implement",
                         "detail": "Write the code."},
                        {"id": 3, "title": "Verify",
                         "detail": "Run the tests."},
                    ],
                    "risks": ["Ambiguous requirements"],
                    "acceptance_criteria": ["Task requirements met"],
                }
            )
        if persona == "architect":
            return json.dumps(
                {
                    "components": [
                        {"name": "solution", "responsibility": first_line}
                    ],
                    "data_model": {},
                    "interfaces": [],
                    "files_to_create": ["solution.py"],
                }
            )
        if persona == "coder":
            return json.dumps(
                {
                    "files": {
                        "solution.py": (
                            f'"""{task_id or "task"}: synthetic solution."""\n\n'
                            "def solve(*args, **kwargs):\n"
                            '    """Return a placeholder result."""\n'
                            "    return 0\n"
                        )
                    },
                    "notes": "Generic mock implementation.",
                }
            )
        if persona == "reviewer":
            return json.dumps(
                {
                    "findings": [],
                    "verdict": "approved",
                    "summary": "Generic mock approval.",
                }
            )
        if persona == "tester":
            return json.dumps(
                {
                    "tests": {
                        "test_solution.py": (
                            "def test_solve_callable():\n"
                            "    from solution import solve\n"
                            "    assert callable(solve)\n"
                        )
                    }
                }
            )
        return json.dumps({"ok": True})


class OpenAICompatibleLLM(LLMProvider):
    """Chat provider for any OpenAI-compatible endpoint (stdlib HTTP only)."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.model = model or os.environ.get("SDLC_LLM_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("SDLC_LLM_BASE_URL",
                                       "https://api.openai.com/v1")
        ).rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Export it (or SDLC_LLM_BASE_URL "
                "for a compatible endpoint) to use the real provider."
            )

    def generate(
        self, *, system: str, user: str, persona: str = "", task_id: str = ""
    ) -> str:
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": _ROLE_MAP.get(m.type, "user"), "content": m.content}
                for m in messages
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def from_env() -> LLMProvider:
    """Real provider when credentials exist, else the deterministic mock."""
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAICompatibleLLM()
    return MockLLM()


def extract_json(text: str) -> dict:
    """Pull a JSON object out of model output (tolerates code fences)."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = match.group(1) if match else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(candidate[start : end + 1])
        raise ValueError(
            f"Could not parse JSON from model output: {text[:200]!r}"
        )
