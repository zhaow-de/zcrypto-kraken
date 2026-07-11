# B1 Seasonality Conditioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/specs/00045-b1-seasonality-conditioning-design.md`: the leak-free B1 conditioning overlay (`cli/alpha/b1.py`, TDD), then — time permitting under the loop's gate — the pre-registered trial 1 per the spec's decision matrix.

**Architecture:** One TDD task builds the overlay module against the spec's exact interfaces; the trial driver is a scratchpad script per the trials-37–39 `run_ref` convention (never committed); the orchestrator holds the run/park checkpoint and the closeout.

**Tech Stack:** Python 3.14, `cli.alpha.a2` (`a2_book_returns`, the three adopted arm configs), `cli.alpha.killbar` (`a1_kill_bar`, `net_of_cost_verdict`), `cli.validation` (SPA/DSR/metrics), `cli.ohlc.dataset.read_parquet` (4h canonical + 15m substrate), `cli.registry` (family `B1`).

## Global Constraints

- **Leak-freeness is the deliverable**: slot key on `ts[k]+4h`; gates trained only on returns whose interval closes ≤ Y-01-01T00:00Z; scaler windows strictly trailing; all edge cases exactly as the spec pins them (F2–F8). Any deviation is a spec violation, not an implementation choice.
- The overlay consumes ensemble outputs as-is — no changes to `cli/alpha/a2.py`, `cli/portfolio/*`, or any adopted artifact.
- Trial 1 (if run) follows the spec's pre-registered decision matrix verbatim; metrics bools→0/1 ints, str keys; registry family `B1`, `n_trials_in_family=1`; dataset_hash recipe byte-exact per the spec.
- Ruff 132/double quotes; `uv run pre-commit run -a` gate; actual-model trailers + `Claude-Session`; subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD): the overlay module

**Files:** Create `cli/alpha/b1.py`, `tests/test_alpha_b1.py`; extend `cli/alpha/__init__.py` re-exports (mirror how a2 exports).

**Interfaces (produces):** exactly the spec's block — `B1Config` (six fields, defaults verbatim), `seasonality_gates(arm_noc_returns, union_ts, *, config) -> list[int]`, `vol_state_scale(m15_closes_by_asset, union_ts, *, config) -> list[float]`, `condition_positions(asset_positions, gates, scales) -> dict[str, list[float]]`. All lists indexed on the return index (`len(union_ts) - 1`). Loggers `get_logger("alpha.b1")`.

Tests first (synthetic fixtures, no dataset), each asserting a spec-pinned behavior:

1. **Slot key on the decision boundary**: a stamp `ts[k]` = Sunday 20:00 UTC keys cell `(0, Monday)` — assert via a fixture where exactly that cell is unfavorable in train and the Sunday-20:00 stamp is held.
2. **Walk-forward isolation**: plant a strongly negative cell pattern only in year Y+1; assert year Y's gates are unaffected (all-open under a flat prior history).
3. **Completion-time rule**: the Dec-31 20:00 stamp (interval closing Jan-1 00:00) IS in year Y+1's training set; the Dec-31 16:00 stamp is too (closes 20:00); a stamp closing Jan-1 04:00 is NOT.
4. **Thin-cell default open** (< 100 obs) and **favorable = summed noc > 0** (plant a cell with 100+ obs summing negative → gated).
5. **Hold-through**: with gates [1,0,0,1], conditioned positions at the two gated stamps equal the previous conditioned position verbatim (turnover zero there), and the update stamps apply `target × scale`.
6. **Scaler per-asset normalization**: a two-asset fixture where asset 2 lists mid-series with 3× the vol level of asset 1 — assert no 0.5-scaling is triggered by the listing itself (own-median normalization); then plant a genuine 3× vol spike in asset 1's own series → state > 1.5 → 0.5.
7. **Edge cases**: < 180 prior boundaries → neutral; < 48 of 96 bars for an asset → excluded that boundary; no qualifying asset → neutral; the substrate-extent assertion raises when the last 15m close < the last decision boundary.
8. **Engagement helpers**: per-year gated counts / scaled counts / turnover computed correctly on a fixture.

Then implement (pure functions, `statistics` stdlib + math; polars only if the 15m frames come in as frames — accept the `(ts_list, close_list)` tuples per the interface). File green → full suite (`uv run pytest`, expect 1173 + new) → pre-commit. Commit `feat(alpha): B1 conditioning overlay — walk-forward seasonality gates + vol-state scaler (spec 00045 task 1)`.

### Task 2 (orchestrator + subagent, checkpoint-gated): trial 1

- [ ] **Checkpoint**: if the reviewed Task-1 commit lands before the loop's gate margin (orchestrator's call), proceed; else park — T0022's next step already carries the pre-registration.
- [ ] Scratchpad driver (`b1_trial1_run.py`, per the trials-37–39 convention — `run_ref` names it, never committed): load 4h canonical (240.parquet, the 10 EUR assets, union calendar, BTC-only ffill — copy the `crossfreq_run.py` load shape) + the 15m substrate closes; build the three adopted A2 arms → equal-weight arm A; arm A noc at 0.006/side → gates + scales → arm B → arm B noc; the 4h-rebuilt frozen benchmark (the `a2_4h_run.py:52-69` recipe verbatim); `a1_kill_bar` + SPA grid + `net_of_cost_verdict(B, A)` full and from-2016; engagement report per spec.
- [ ] **Verdict per the decision matrix — no interpretation freedom**; registry append (family `B1`, the spec's dataset_hash recipe, metrics per the pinned key set + engagement); decisions-log verdict entry.
- [ ] Closeout: T0022 findings updated (trial 1 outcome or explicit park), iterations-history entry, pre-commit, commit, final whole-branch review, PR `feat(alpha): iter-086 — B1 family opening (conditioning overlay harness)` (+ trial-1 outcome in the title's description if run), merge via merge-pr when green.
