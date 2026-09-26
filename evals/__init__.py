"""Eval harness: golden-dataset tasks, deterministic checks, LLM-as-judge.

Run with:  python -m evals.run_evals        (mock/CI mode, no network)
           python -m evals.run_evals --real  (real LLM, needs OPENAI_API_KEY)
"""
