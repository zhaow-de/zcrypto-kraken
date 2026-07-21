# Captured-spread cost calibration — implementation plan (T0014)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** add the calibrated spread term to `cli/costs/` and re-read the A-family net-of-cost conclusions with it included.

**Architecture:** one new module `cli/costs/spread.py` holding the calibrated table + lookup + a size interpolator, and one composition helper `round_trip_cost()` that sums fee + spread + margin carry. No existing behaviour changes; `fees.py` and `margin.py` are untouched.

**Tech Stack:** stdlib only (the table is literal data; polars is used for the calibration, not at runtime).

## Global Constraints

- Table values are the **mean effective spread in bps per side**, mid-relative, from spec `00066`'s table — copy exactly, do not round.
- Provenance constants are load-bearing and asserted by tests: window `2026-07-08T13:47:33Z … 2026-07-21T15:59:59Z`, `315` hours/pair, `1_123_509` minimum rows/pair.
- Sizes above €10,000 **raise** `CostModelError`; below €100 clamp to the €100 value.
- Every validation error is `CostModelError` (never bare `ValueError`), matching `fees.py`/`margin.py`.
- Pair keys are the base asset symbol, uppercase (`"BTC"`), matching the panel layout and the universe.

---

### Task 1: the calibrated table + per-size lookup

**Files:**
- Create: `cli/costs/spread.py`
- Test: `tests/test_costs_spread.py`

**Interfaces:**
- Produces: `SPREAD_CALIBRATION: dict[str, dict[int, float]]`, `CALIBRATION_WINDOW: tuple[str, str]`, `CALIBRATION_HOURS: int`, `CALIBRATION_MIN_ROWS: int`, `effective_spread_bps(pair: str, notional_eur: float) -> float`

- [ ] **Step 1: failing tests** — pinned values for all ten pairs at the three pinned sizes; unknown pair raises; non-finite/negative notional raises; `>10_000` raises with the reason in the message; `<100` clamps; log-interpolation midpoint between €1k and €10k for DOT lands strictly between 5.545 and 12.412 and above the linear-in-notional midpoint (the convexity guard).
- [ ] **Step 2: run, confirm failure** — `uv run pytest tests/test_costs_spread.py -q` → ImportError.
- [ ] **Step 3: implement** the table and `effective_spread_bps` (log-notional interpolation, clamp low, raise high).
- [ ] **Step 4: run, confirm pass.**
- [ ] **Step 5: commit.**

### Task 2: round-trip composition

**Files:**
- Modify: `cli/costs/spread.py` (add `round_trip_cost`)
- Test: `tests/test_costs_spread.py`

**Interfaces:**
- Consumes: `cli.costs.fees.round_trip_fee`, `cli.costs.margin.margin_carry`, `effective_spread_bps`
- Produces: `round_trip_cost(notional, *, pair, maker_rate, taker_rate, taker_open=False, taker_close=False, hold_hours=0.0, margin_rate_=None) -> dict`

- [ ] **Step 1: failing tests** — returns `{"fee", "spread", "carry", "total"}` summing exactly; spread is charged **twice** (once per side) and equals `2 × notional × bps/10_000`; with `hold_hours=0` carry is 0; spot path (no margin rate) has carry 0; the fee component equals `round_trip_fee` called directly (no silent re-implementation); a tier-1 taker round trip on €1k of DOT has fee ≫ spread (the order-of-magnitude guard from spec D4).
- [ ] **Step 2–4: red → implement → green.**
- [ ] **Step 5: commit.**

### Task 3: the reference table + README

**Files:**
- Create: `docs/reference/captured-spread-calibration.md`
- Modify: `README.md` (Usage — only if a CLI surface changed; it does not, so this is a no-op check, recorded explicitly)

- [ ] **Step 1:** write the reference doc — the table, the window/row provenance, D1's "never quote a median top-of-book spread for BTC/EUR", the rank-10 caveat, and the recalibration procedure.
- [ ] **Step 2:** confirm no CLI surface changed (`grep` the new module for `@app.command`) and record that README needs no edit.
- [ ] **Step 3: commit.**

### Task 4: A-family robustness re-read (no new trials)

**Files:**
- Create: `docs/research/<serial>.phase6-*` — **no**; the verdict rides `docs/research/14.phase6-decisions.md`.

- [ ] **Step 1:** read the A-family / P1 registry rows and their net-of-cost margins.
- [ ] **Step 2:** compute the spread drag at the basket's realistic per-trade notional and turnover, and state whether any adopt/reject flips. **No new trials are registered** — this is a re-read of existing verdicts, which the budget does not charge for.
- [ ] **Step 3:** record the outcome in the decisions log, including an explicit "no verdict moved" if that is the answer.

### Task 5: closeout

- [ ] Append the decisions-log entries (D1–D5 + the robustness verdict) to `docs/research/14.phase6-decisions.md`.
- [ ] Append the iterations-history entry to `docs/iterations-history-phase1.md` (subject-matter phase: research/cost model — verify by `grep -l` which phase file carries the cost-model iterations, per `.claude/rules/iterations-history.md`).
- [ ] Flip T0014 (`resolved` or `partial` with the remainder registered) + index, and update the memo via the grooming ad-hoc procedure.
