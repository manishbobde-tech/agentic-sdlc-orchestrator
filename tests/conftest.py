"""Pytest fixtures: put src/ and the project root on sys.path, share a MockLLM."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from sdlc_agents import MockLLM  # noqa: E402


@pytest.fixture()
def mock_llm() -> MockLLM:
    return MockLLM()


@pytest.fixture()
def demo_task() -> str:
    return (
        "Add a `current_streak` function that takes a list of ISO date "
        "strings and returns the count of consecutive days ending today. "
        "Empty list returns 0."
    )
