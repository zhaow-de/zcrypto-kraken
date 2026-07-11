# §10 Portfolio Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/specs/00046-portfolio-limits-design.md`: the three remaining §10 limits as tested pure functions in `cli/risk/limits.py`.

**Architecture:** One TDD task extending the existing module in its established idiom; orchestrator closeout. No consumers wired (none exist yet).

**Tech Stack:** Python 3.14 stdlib (`math`), `cli.risk.errors.RiskError`, pytest.

## Global Constraints

- §10-ratified constants verbatim as defaults: gross `soft_cap=1.5` / `hard_cap=2.0`; net band `short_bound=-0.5` / `long_bound=1.0`; margin `floor=2.5`.
- The `apply_position_caps` idiom is binding: pure pre-trade transforms, proportional scaling only (never redistribution), inclusive at limits, `RiskError` guards, untouched paths return values bit-identical.
- The margin model + closed-form scale factor exactly per the spec (piecewise-linear derivation documented in the docstring; no bisection).
- Ruff 132/double quotes; `uv run pre-commit run -a`; actual-model trailers + `Claude-Session`; subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD): the three limits

**Files:** Modify `cli/risk/limits.py` (module docstring updated: the deferred-limits sentence replaced by the delivered inventory + the composition-order note), extend `tests/` (find the limits tests via `grep -rl apply_position_caps tests/`), extend `cli/risk/__init__.py` re-exports if the module has them (mirror the existing pattern).

**Interfaces (produces):**

```python
def apply_gross_leverage_cap(positions: dict[str, list[float]], *, soft_cap: float = 1.5, hard_cap: float = 2.0) -> dict[str, list[float]]
def apply_net_exposure_band(positions: dict[str, list[float]], *, short_bound: float = -0.5, long_bound: float = 1.0) -> dict[str, list[float]]
def margin_level(bar_positions: dict[str, float]) -> float          # unit-NAV model per the spec; no-margin -> math.inf
def apply_margin_floor(positions: dict[str, list[float]], *, floor: float = 2.5) -> dict[str, list[float]]
```

Steps: failing tests first — the spec's full test list verbatim (pass-through bit-identity, at-limit inclusive, scaled-to-exactly-the-bound within 1e-12, proportionality, mixed books, the three margin-model unit cases incl. the 0.3-short/0.8-long → level exactly 2.5 fixture, closed-form-vs-brute-force at 1e-6 on the three named fixtures, guards, per-function idempotence). Reuse the existing test file's fixture style. Then implement; file green; full suite (`uv run pytest`, expect 1185 + new); `uv run pre-commit run -a` until clean. Commit `feat(risk): §10 gross/net/margin-floor limits as pre-trade transforms (spec 00046)`.

### Task 2 (orchestrator, closeout)

- [ ] T0016: the standing-prerequisite bullet reworded — code delivered (link the commit), the remainder is wiring into whichever family harness binds first; the borrow-unavailable stress re-run reminder stays untouched.
- [ ] Decisions-log entry (`[iter-088]` delivery note); iterations-history entry; pre-commit; commit; final whole-branch review; PR `feat(risk): iter-088 — §10 portfolio limits (gross, net band, margin floor)`; merge via merge-pr when green.
