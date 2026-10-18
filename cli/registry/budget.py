"""The hard trial budgets and the bucket each family spends from; design in docs/specs/00133-t0222-trial-attempts-design.md."""

from __future__ import annotations

# Master plan §12's budgets, B shared by its families and P1 unbudgeted (docs/specs/00133 D5, which cites both rulings).
BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "P1": None}
BUDGET: dict[str, int] = {"A": 40, "B": 25, "C": 10}
