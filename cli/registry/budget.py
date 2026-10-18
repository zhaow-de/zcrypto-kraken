"""The hard trial budgets and the bucket each family spends from; design in docs/specs/00133-t0222-trial-attempts-design.md."""

from __future__ import annotations

# The trial budgets of docs/research/00.master-plan.md §12, "The Phased Master Plan" (its "Converted to
# autonomous-with-defaults" paragraph): A=40, B=25, C=10, B one budget its families share. P1, the portfolio-assembly
# family, maps to None: no pre-registered budget applies to it (docs/research/13.phase5-decisions.md, the ruling
# "Registry family key for the combination?"). §12 says "*expansion* escalates": an expansion, or a new family with
# its bucket, is the owner's ruling, landed by a pull request that edits these literals and the test asserting them and
# quotes that ruling.
BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "P1": None}
BUDGET: dict[str, int] = {"A": 40, "B": 25, "C": 10}
