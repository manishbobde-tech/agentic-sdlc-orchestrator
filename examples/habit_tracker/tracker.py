"""Fictional personal habit-tracker CLI (synthetic demo domain).

This app exists so the agentic pipeline has something concrete to operate on.
It is deliberately tiny and entirely fictional: no real data, no real users,
no external services.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

DATA_FILE = os.environ.get("HABIT_DATA", "habits.json")


def load() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def save(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def add_habit(name: str) -> dict:
    data = load()
    if name in data:
        raise ValueError(f"Habit {name!r} already exists.")
    data[name] = []
    save(data)
    return {"name": name}


def check_in(name: str, day: str | None = None) -> dict:
    data = load()
    if name not in data:
        raise ValueError(f"Unknown habit {name!r}.")
    day = day or date.today().isoformat()
    if day not in data[name]:
        data[name].append(day)
        data[name].sort()
    save(data)
    return {"name": name, "day": day}


def summary() -> str:
    data = load()
    lines = [f"{name}: {len(days)} check-ins" for name, days in sorted(data.items())]
    return "\n".join(lines) if lines else "No habits yet."


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: tracker.py <add|checkin|summary> [args]")
        return 2
    cmd, rest = argv[1], argv[2:]
    try:
        if cmd == "add" and len(rest) == 1:
            add_habit(rest[0])
            print(f"Added habit {rest[0]!r}.")
        elif cmd == "checkin" and len(rest) in (1, 2):
            result = check_in(rest[0], rest[1] if len(rest) == 2 else None)
            print(f"Checked in {result['name']!r} for {result['day']}.")
        elif cmd == "summary" and not rest:
            print(summary())
        else:
            print(f"unknown command: {cmd}")
            return 2
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
