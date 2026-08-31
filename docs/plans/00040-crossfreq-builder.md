# Record-44 Builder + Concordance Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/specs/00040-crossfreq-builder-design.md`: the record-44 builder (verified + equivalence-gated fast path) in `cli/portfolio/crossfreq_system.py`, and the concordance core (journal contract, replay, compare, gate) in `cli/engine/`, with frozen-figure regression tests against registry trials 43/44.

**Architecture:** Three TDD subagent tasks — (1) the verified builder, (2) the fast path + equivalence, (3) the concordance core — then orchestrator docs closeout. Task 1 blocks 2 and 3; 2 and 3 are independent of each other. The spec is the single source of construction truth; Task 1 was transcribed from the iter-081 trial driver, which lived in a session scratchpad and is gone. **The durable equivalents are committed**: `cli/portfolio/record44_legs.py` re-derives record 44 from committed code, and `cli/portfolio/record43_book.py` is trial 43's instrument — whose own docstring carries the recovery history, including that the five scratchpad scripts were recovered verbatim from a session transcript that the tooling's retention prune then destroyed. A later reader opens those two modules; there is nothing else to point at.

**Tech Stack:** Python 3.14, existing `cli` machinery (`cli.alpha`, `cli.benchmark.strategies`, `cli.portfolio.crossfreq`, `cli.risk`), polars/numpy for the fast path, pytest.

## Global Constraints

- **The feed map is law** (spec §The builder): RAW union prices (Nones preserved) → `dynamic_inverse_vol_basket`/`_inverse_vol_weights`/`build_combined_system` QA; BTC-ffilled → `a1_book_returns`/`a2_book_returns`; return grids = `_asset_returns` over BTC-ffilled with `None → 0.0`.
- **Frozen figures** (skipif-data, extent-guard first, "canonical dataset drifted — STOP"): governed Sharpe 1.5609 full / 1.5583 decisive (k≥1380, ppy 2190), maxDD 0.1357 (pre-gov 0.1866), `cap_breach_bars` 1318, `governor_engaged_bars` 7302; anchors: daily bench 1.2455 + elementwise ≤1e-12 vs `build_combined_system`, A1-lf book 1.3798, arms 1.3274/1.3017/1.3585. Tolerances 0.005 (Sharpe) / 1e-12 (elementwise).
- **Conventions behind the integers**: `cap_breach_bars` = bars where any asset |capped−combined| > 1e-15; `governor_engaged_bars` = bars with multiplier < 1.0; all turnover loops start `prev = 0.0` (bar 0 charged full entry).
- **Newest-row contract** (spec): one extra row for the forming interval via synthetic next-boundary + dummy-close appends; dummy-insensitive; forming-day multiplier via appended zero day-return; the three-part invariant test is mandatory.
- **Equivalence gate**: fast vs verified ≤1e-12 elementwise on `final_targets` + both net series over the full frozen history; identical integer diagnostics; off-ramp = production runs verified path (never loosen the gate).
- `data/ohlc-full` is read-only everywhere. Ruff 132/double quotes; gate `uv run pre-commit run -a`; commits carry actual-model `Co-Authored-By` + `Claude-Session` trailers; every task commit gets subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD): the verified builder

**Files:** Create `cli/portfolio/crossfreq_system.py`, `tests/test_crossfreq_system.py`; modify `cli/portfolio/__init__.py` (re-export `CrossfreqSystemConfig`, `CrossfreqSystemResult`, `build_crossfreq_system`).

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class CrossfreqSystemConfig:  # record 44's constants as defaults — validate on use, PortfolioError on bad values
    assets: tuple[str, ...] = ("ADA","AVAX","BTC","DOGE","DOT","ETH","LINK","LTC","SOL","XRP")
    spot_fee_per_side: float = 0.006
    long_cap: float = 0.20
    short_cap: float = 0.10
    a2_arms: tuple[tuple[tuple[int, int, int], float], ...] = (((20,50,100),0.12), ((60,120,240),0.10), ((60,120,240),0.12))
    governor: GovernorConfig = GovernorConfig()
    # B-sleeve constants (basket/gate/vt/weights lookbacks) and A1/A2 configs are fixed record-44 values, not knobs

@dataclass(frozen=True)
class CrossfreqSystemResult:
    final_targets: dict[str, list[float]]   # n_periods + 1 rows: completed bars + the forming interval (mult x capped)
    governed_net: list[float]               # n_periods rows (completed bars only)
    ungoverned_net: list[float]
    multipliers: list[float]                # n_periods + 1 (forming-interval multiplier appended)
    sleeve_positions: dict[str, dict[str, list[float]]]  # {"B": ..., "A1": ..., "A2": ...} on the 4h grid
    cap_breach_bars: int
    governor_engaged_bars: int
    day_index: list[int]
    n_periods: int

def build_crossfreq_system(daily_prices, daily_ts, h4_prices, h4_ts, *, config=CrossfreqSystemConfig()) -> CrossfreqSystemResult
```

Transcribe the construction from the reference driver (path in Architecture) per the spec's feed map + construction order; the newest row per the spec's contract (dummy-close appends; zero day-return multiplier trick). Steps: (1) unit tests first — config validation, degenerate inputs (empty dicts, length mismatches → `PortfolioError`), the synthetic mini-grid end-to-end (hand-computable 2-asset, ~30-day grid), and the three-part newest-row invariant; run → fail; (2) implement; (3) add the skipif-data regression test (extent guard: per-pair bar count + last ts of `data/ohlc-full/*/EUR/{1440,240}.parquet` pinned to the frozen values the implementer reads at build time and records in the test; then the frozen figures + anchors); (4) full suite green; (5) pre-commit; commit `feat(portfolio): record-44 verified builder (build_crossfreq_system)`.

### Task 2 (subagent, TDD): the fast path + equivalence gate

**Files:** Modify `cli/portfolio/crossfreq_system.py` (add `build_crossfreq_system_fast`), `cli/portfolio/__init__.py`; extend `tests/test_crossfreq_system.py`.

**Consumes:** Task 1's result type + verified path. **Produces:** `build_crossfreq_system_fast(...)` — identical signature/result type.

Profile the verified path first (the three A2 arms dominate); vectorize order-insensitive arithmetic only, feeding discrete decisions (gate, qualification, fallback, cap, breakouts, rungs) values computed the verified way (spec §fast path). Tests first: (1) the CI-unconditional synthetic mini-grid equivalence (fast ≡ verified exactly on the mini-grid); (2) the skipif-data full-history equivalence (≤1e-12 elementwise on `final_targets` + both nets; identical integers; 4dp headline round). Record the measured speedup in the test docstring and the task report (advisory target ~10×). If 1e-12 is unattainable on a layer after genuine effort: STOP, report BLOCKED with the layer named — the off-ramp decision (production on verified path) is the orchestrator's to take, never a loosened tolerance. Commit `feat(portfolio): equivalence-gated fast path for the record-44 builder`.

### Task 3 (subagent, TDD): the concordance core

**Files:** Create `cli/engine/__init__.py`, `cli/engine/journal.py`, `cli/engine/concordance.py`, `cli/engine/errors.py`, `tests/test_engine_journal.py`, `tests/test_engine_concordance.py`.

**Consumes:** `build_crossfreq_system` / `build_crossfreq_system_fast` signatures (Task 1/2). **Produces (for iter-083's node):**

```python
# journal.py — schema_version = 1
@dataclass(frozen=True)
class SnapshotEntry:   # one per pair x grid
    pair: str; grid: str  # "1440" | "240"
    n_bars: int; first_ts: datetime; last_ts: datetime
    content_hash: str; path: str

@dataclass(frozen=True)
class CycleRecord:
    schema_version: int; cycle_ts: datetime
    snapshots: tuple[SnapshotEntry, ...]
    final_targets: dict[str, float]        # newest-row targets, per asset
    started_at: datetime; completed_at: datetime
    code_version: str; builder_path: str   # "fast" | "verified"

def snapshot_content_hash(ts: list[datetime], closes: list[float | None]) -> str
    # sha256 over: int64 epoch-seconds LE (row order), then float64 IEEE-754 LE (None -> NaN). THE one helper both sides use.
def validate_record(record: CycleRecord) -> None     # schema + snapshot-boundary invariant (raises EngineJournalError)
def to_json(record) -> str / def from_json(s) -> CycleRecord

# concordance.py
def replay_cycle(record, snapshot_reader, *, path="fast") -> dict[str, float]   # hash-verify (fail => MISMATCH), boundary invariant, locate by cycle_ts
def compare_targets(a: dict[str, float], b: dict[str, float], *, tol=1e-6) -> CompareResult  # structural fail on asset-set mismatch
def evaluate_gate(entries: list[CycleOutcome]) -> GateStatus   # complete-UTC-days universe, 6 cycles, boundary<=completed_at<=boundary+30min, >=14 consecutive clean days
```

The boundary invariant: per pair, last 4h stamp == cycle_ts − 4h; last daily stamp == (last midnight ≤ cycle_ts) − 1d. Tests on synthetic journals per the spec's list: clean streaks; missed cycle; late cycle; mismatch; boundary-invariant violation; intra-day evaluation mid-streak (unbroken); mid-day start (first full day counts). `replay_cycle` tests use a stub snapshot_reader + a monkeypatched builder — no dataset needed. Commit `feat(engine): journal contract + concordance core (replay, compare, 4h gate)`.

### Task 4 (orchestrator): docs closeout + PR

- [ ] Runbook (`docs/research/12.phase5-system-spec-runbook.md`): decision-dated record-44 section (construction summary, registered figures, reproduction via the builder, the multiplier-transition P&L disclosure, the equivalence-evidence discipline: PRs touching the builder run the data-machine tests locally and say so); record-33 sections marked superseded-but-historical.
- [ ] CLAUDE.md: fix the stale "CLI subcommands (none exist yet…)" parenthetical (cli/capture exists).
- [ ] Run the full data-machine evidence: `uv run pytest tests/test_crossfreq_system.py -v` (all regression + equivalence green here, where `data/ohlc-full` exists); record in the PR test plan.
- [ ] Iterations-history entry (iter-082); pre-commit; commit; PR into develop titled `feat(portfolio): iter-082 — record-44 builder + concordance core`; aggregated trailers per `pull-requests.md`; merge on the human's go (attended mode).
