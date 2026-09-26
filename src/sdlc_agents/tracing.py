"""JSONL trace logging for every pipeline node execution.

Each record captures when a node ran, how long it took, an estimated token
count, and the node's verdict (reviewer verdict, tester pass/fail counts, ...).
The trace is the raw material for latency/cost dashboards and for debugging
why a run behaved the way it did.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone


class TraceLogger:
    def __init__(self, path: str) -> None:
        self.path = path
        self.run_id = uuid.uuid4().hex[:8]
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)

    @staticmethod
    def estimate_tokens(*texts: str) -> int:
        """Rough token estimate (~4 chars per token)."""
        return sum(len(t or "") for t in texts) // 4

    def log(
        self,
        node: str,
        latency_ms: float,
        tokens: int,
        verdict: str = "",
        detail: dict | None = None,
    ) -> dict:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "node": node,
            "latency_ms": round(latency_ms, 2),
            "tokens_est": tokens,
            "verdict": verdict,
            "detail": detail or {},
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return record

    def read_all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def node_names(self) -> list[str]:
        return [r["node"] for r in self.read_all()]
