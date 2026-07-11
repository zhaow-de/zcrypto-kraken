# 15m Bar Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/specs/00044-15m-substrate-design.md`: full-history 15m bars for the 12-pair universe at `data/ohlc-15m/` (backfill-derived, manifest-hashed), QA'd (gap/density) and instrument-proved (tick reconciliation + 1h seam check) — resolving T0012.

**Architecture:** One tiny TDD task (the `"15"` interval key), one substrate task (a tested driver module reusing `cli/backfill` + `cli/tick`, then the real run against the NAS archives), then the orchestrator closeout. Existing machinery is consumed, not redesigned.

**Tech Stack:** Python 3.14, `cli.backfill` (`backfill_basket(source_dir, symbols, intervals, out_root, fetched_at)`), `cli.tick` (`read_trades_csv`, `ticks_to_bars`, `reconcile`), `cli.ohlc.qa.detect_gaps`, polars.

## Global Constraints

- **NAS archives are read-only** (`/home/zhaow/Projects/zcrypto-kraken-data/{kraken-ohlcvt-updates,kraken-trades}/`); `data/ohlc-full` is immutable canonical — the new root is `data/ohlc-15m/` (gitignored by `data/.gitignore`'s ignore-everything rule, like every dataset).
- **Acceptance is T0004-consistent**: dense-window tick reconciliation ≥ 99.4% within 1%; a material miss STOPS the substrate (instrument finding), never a tolerance loosened.
- The universe = the 12 canonical pairs exactly as the canonical backfill used them (read the basket the same way `data/ohlc-full`'s manifest records).
- Ruff 132/double quotes; gate `uv run pre-commit run -a`; actual-model trailers + `Claude-Session`; subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD): the 15m interval key

**Files:** Modify `cli/ohlc/qa.py` (`INTERVAL_SECONDS` gains `"15": 900`); extend the existing backfill/QA tests (find via `grep -rl INTERVAL_SECONDS tests/`).

Tests first: `aggregate_minutes(rows, 900)` buckets a synthetic 1-minute series into 900-s bars (open=first/high/low/close=last/volume-sum/vwap reconstruction — mirror the existing 3600-s test shape at 900 s); `backfill_pair(source_dir, symbol, ["15"])` returns a canonical frame with 900-s spacing (tiny zip fixture, mirroring existing fixtures); `detect_gaps` at 900 s flags a synthetic missing bucket. Then the one-line implementation. File green → full suite → pre-commit. Commit `feat(backfill): 15m interval support (spec 00044 task 1)`.

### Task 2 (subagent): the substrate driver + the real build/QA/reconciliation run

**Files:** Create `cli/backfill/substrate15m.py`, `tests/test_substrate15m.py`.

**Interfaces (produces):**

```python
def build_15m_substrate(source_dir: Path, symbols: list[str], out_root: Path, *, fetched_at: str) -> dict
#   backfill_basket(..., intervals=["15"], ...) verbatim; returns the manifest.
def qa_15m(out_root: Path, symbols: list[str]) -> dict
#   Per pair: rows, first/last ts, gap count + largest gap (detect_gaps at 900), per-year bar
#   density vs the ideal 96/day grid. Pure read of the written parquet.
def reconcile_15m_vs_ticks(out_root: Path, tick_zip: Path, symbol_csvs: dict[str, str], window: tuple[datetime, datetime]) -> dict
#   read_trades_csv -> ticks_to_bars(interval_minutes=15) on the window -> cli.tick.reconcile
#   against the pair's 15.parquet rows in-window; returns the reconcile dict per pair.
def seam_15m_to_1h(out_root: Path, canonical_root: Path, symbols: list[str], window: tuple[datetime, datetime]) -> dict
#   Aggregate the 15m frame to 3600-s buckets in-window (aggregate_minutes on the 15m rows is
#   NOT valid — it assumes 1m inputs; do the polars group-by explicitly: open=first, high=max,
#   low=min, close=last, volume=sum over floor(ts/3600)) and compare O/H/L/C/V against the
#   canonical 60.parquet stamps (exact volume, 1e-9 price tolerance); returns match stats per pair.
```

Unit tests with tiny synthetic fixtures for all four (no NAS dependency in tests). Then the REAL run (a `python -c`/script invocation in the task report, not committed): `build_15m_substrate` over the NAS archive for the 12 pairs; `qa_15m`; `reconcile_15m_vs_ticks` on **one dense recent window per pair** (Q1-2026 quarterly tick zip, or the full-history zip's tail, ≥ 30 days); `seam_15m_to_1h` on the same windows. Paste the four result summaries (per-pair tables) into the task report verbatim. Full suite + pre-commit. Commit `feat(backfill): 15m substrate driver + QA/reconciliation (spec 00044 task 2)`.

### Task 3 (orchestrator, closeout)

- [ ] Read Task 2's evidence against the acceptance bar (≥ 99.4% within 1% dense windows; seam exact-volume; no new anomaly classes). A miss → instrument bug-hunt, not shipping.
- [ ] T0012: resolve (storage decision recorded: 15m Parquet derivation; tick catalog dropped with the C2/C1 re-open note), `git mv` to `docs/open-topics/archive/`, index bullet → Resolved with the archived link.
- [ ] Decisions-log verdict entry (`[iter-085]`: substrate delivered, dataset `basket_sha256`, acceptance numbers, adopt).
- [ ] Iterations-history entry (per-pair QA + reconciliation summary, the dataset hash, the B1-opening next step).
- [ ] Pre-commit; commit; final whole-branch review; PR `feat(backfill): iter-085 — the 15m bar substrate for Bucket B (T0012)` into develop; merge via merge-pr when green (loop mode).
