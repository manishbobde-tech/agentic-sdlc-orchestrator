"""Agentic SDLC Orchestrator v0.1.

A portfolio scaffold: five LLM personas (planner, architect, coder, reviewer,
tester) wired into a LangGraph pipeline, with JSONL tracing and a
golden-dataset eval harness.

Everything in this repo is synthetic. The demo domain is a fictional personal
habit-tracker app. No real company, employer, or proprietary system is
referenced anywhere.
"""

from .llm import LLMProvider, MockLLM, OpenAICompatibleLLM, from_env
from .orchestrator import build_graph, run_pipeline
from .state import SDLCState
from .tracing import TraceLogger

__version__ = "0.1.0"

__all__ = [
    "LLMProvider",
    "MockLLM",
    "OpenAICompatibleLLM",
    "from_env",
    "build_graph",
    "run_pipeline",
    "SDLCState",
    "TraceLogger",
    "__version__",
]
