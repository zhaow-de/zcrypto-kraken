# `zcrypto engine soak-check` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only `zcrypto engine soak-check` that places trial 44's realized shadow-soak behaviour against its backtest expectation via 7 position-derived structural metrics + a non-gating P&L line, as the T0064 stand-in for the never-run holdout (spec `00058`).

**Architecture:** A new pure-logic core `cli/engine/soak.py` (realized-series extraction, structural metrics, null construction, verdict engine, falsification guards, report rendering) plus a thin `soak-check` command in `cli/engine/command.py`. It reuses `journal.from_json`, `store.read_store_series`, `crossfreq_system.build_crossfreq_system_fast`, `risk.limits.apply_position_caps`, and `command._journal_artifacts`/`_snapshot_reader`. It never calls `evaluate_gate` and never touches the holdout.

**Tech Stack:** Python 3.14, numpy, polars (via existing store readers), Typer + `CliRunner` for the command, pytest.

## Global Constraints

- **Fee:** `0.006` per side (realized turnover cost); default overridable via `--fee-per-side`.
- **Settle/realizability:** score a boundary only if its forward bar close exists AND `T+4h ≤ now`; drop the in-progress candle (mirror `store._drop_in_progress`).
- **Band:** default `--band 0.90` → central `[p5, p95]`; live ∈ `[p10, p90]` consistent; ∈ `[p5,p10)∪(p90,p95]` weakly-consistent (edge); outside `[p5, p95]` INCONSISTENT — investigate (two-sided; too-good is a bug tell, never a reject); zero-width band / tiny effective-n → n/a.
- **Floor:** `L < --floor` (default 30) → no verdict.
- **The off-by-one keystone (spec 00058 D2):** `r_fwd_a(T) = C_a(T)/C_a(T−4h) − 1`, timestamp-keyed on `read_store_series(store_dir, a, 240)`, NEVER list-index. Start `C_a(T−4h)` = this cycle's 240-snapshot `last_ts` close (= `cycle_ts − 4h`); end `C_a(T)` = the NEXT cycle's 240-snapshot `last_ts` close. Cross-check invariant: `end(T) == start(T+4h)` (both are the price labeled T) — an off-by-one breaks it and must VOID.
- **Null cost convention (spec 00058 D3/D4):** `net_live[k] = governed_net[k] + mult[k]·fee_builder·Σ_a|Δcapped| − fee·Σ_a|Δfinal_targets|`, where `capped = apply_position_caps(⅓·(B+A1+A2))` from `result.sleeve_positions` and `mult = result.multipliers` — NEVER reconstruct capped by dividing `final_targets` by `multipliers` (mult==0 trap). `fee_builder = config.spot_fee_per_side`.
- **Reconciliation invariant:** `mult[k]·capped[a][k] == final_targets[a][k]` to `1e-9` for all a,k — VOID on failure.
- **Vocabulary lock:** the rendered report must never contain "validated", "passed", "confirmed", or "proven"; the honesty banner (the bare zero-OOS fact) is present on every emit.
- **Degeneracy override:** a near-zero-exposure window (echoing the record-33 `[0,0]` holdout) → "INDETERMINATE — DEGENERATE WINDOW", never "consistent".
- **The 10-asset universe** is `config`'s trading universe; the asset set of the journal's `final_targets` and the builder's `result.final_targets` must match exactly — a drift aborts.

---

## File Structure

- `cli/engine/soak.py` (create) — the pure core, ~5 sections matching Tasks 1–6.
- `cli/engine/command.py` (modify) — add the `soak-check` command (Task 7).
- `tests/test_engine_soak.py` (create) — Tasks 1–6 unit tests.
- `tests/test_engine_soak_command.py` (create) — Task 7 command tests.
- `README.md` (modify) — `## Usage` entry for `soak-check` (Task 7).
- `docs/iterations-history-phase1.md` (modify) — closeout entry (Task 7).

**Task order** (dependencies): metrics (pure, no deps) → realized series → null construction → verdict engine → falsification guards → report → command+docs.

---

## Task 1: Structural metrics (pure functions on weight vectors)

**Files:**
- Create: `cli/engine/soak.py`
- Test: `tests/test_engine_soak.py`

**Interfaces:**
- Produces: `structural_metrics(weights_by_bar: list[dict[str, float]]) -> dict[str, list[float]]` returning per-bar series keyed `gross`, `net`, `active_frac`, `turnover`, `hhi`, `cap_breach` (turnover is `Σ|w−w_prev|` with `prev=0` on the first bar; cap_breach is per-bar 0/1 given a `caps` arg — see below). Also `governor_engaged_daily(mult: list[float], day_index: list[int]) -> list[float]` → per-day engaged 0/1 (a day is engaged if any of its bars has `mult < 1.0`).
- Consumed by: Tasks 2, 3, 4.

**Signature detail:** `structural_metrics(weights_by_bar, *, long_cap=0.20, short_cap=0.10)`. Each element of `weights_by_bar` is `{asset: weight}` over the SAME asset set. Metrics per bar T:
- `gross = Σ_a |w_a|`; `net = Σ_a w_a`; `active_frac = #{a: |w_a|>1e-9} / len(assets)`;
- `turnover = Σ_a |w_a(T) − w_a(T_prev)|` (first bar: `w_prev=0`);
- `hhi = Σ_a (|w_a|/gross)^2` if `gross>1e-12` else `0.0`;
- `cap_breach = 1.0 if any(w_a > long_cap+1e-12 or w_a < −short_cap−1e-12) else 0.0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_soak.py
from cli.engine.soak import structural_metrics, governor_engaged_daily


def test_structural_metrics_basic():
    bars = [
        {"BTC": 0.10, "ETH": -0.05, "SOL": 0.0},
        {"BTC": 0.20, "ETH": 0.0, "SOL": 0.10},
    ]
    m = structural_metrics(bars, long_cap=0.20, short_cap=0.10)
    assert m["gross"] == [0.15, 0.30]
    assert m["net"][0] == 0.05 and abs(m["net"][1] - 0.30) < 1e-12
    assert m["active_frac"] == [2 / 3, 2 / 3]
    # turnover bar0: |0.10|+|−0.05|+0 = 0.15 (prev=0); bar1: |0.10|+|0.05|+|0.10| = 0.25
    assert abs(m["turnover"][0] - 0.15) < 1e-12
    assert abs(m["turnover"][1] - 0.25) < 1e-12
    # hhi bar0: (0.10/0.15)^2 + (0.05/0.15)^2 = 0.4444.. + 0.1111.. = 0.5556..
    assert abs(m["hhi"][0] - (2 / 3) ** 2 - (1 / 3) ** 2) < 1e-12
    assert m["cap_breach"] == [0.0, 0.0]


def test_structural_metrics_cap_breach_flagged():
    bars = [{"BTC": 0.25, "ETH": -0.15}]  # both beyond 0.20 / -0.10
    m = structural_metrics(bars, long_cap=0.20, short_cap=0.10)
    assert m["cap_breach"] == [1.0]


def test_governor_engaged_daily():
    mult = [1.0, 1.0, 0.5, 1.0, 1.0, 1.0]
    day_index = [0, 0, 0, 1, 1, 1]
    assert governor_engaged_daily(mult, day_index) == [1.0, 0.0]  # day 0 engaged, day 1 not
```

- [ ] **Step 2: Run test to verify it fails** — `uv run pytest tests/test_engine_soak.py -v` → FAIL (ImportError).
- [ ] **Step 3: Write minimal implementation** in `cli/engine/soak.py` — module docstring (no internal-tracker terms; the `_INTERNAL` help-hygiene regex `iter-\d+|spec\s*\d{5}|OPS-\d|phase[- ]\d|T\d{4}` is enforced only on Typer help strings, but keep the docstring clean anyway), then the two functions above. Use plain Python (no numpy needed here).
- [ ] **Step 4: Run test to verify it passes.**
- [ ] **Step 5: Commit** — `feat(cli): soak-check structural metrics`.

---

## Task 2: Realized series extraction — the off-by-one keystone

**Files:**
- Modify: `cli/engine/soak.py`
- Test: `tests/test_engine_soak.py`

**Interfaces:**
- Consumes: `journal.from_json`, `store.read_store_series`, Task 1's structural pieces indirectly (returns raw weight vectors + net series).
- Produces:
  - `select_clean_segment(records: list[CycleRecord]) -> list[CycleRecord]` — the longest run of success cycles at contiguous 4h boundaries (00/04/08/12/16/20 UTC, each exactly 4h after the prior), no gap.
  - `realized_series(records, store_dir, *, fee=0.006, now) -> RealizedSeries` where `RealizedSeries` is a dataclass: `cycle_ts: list[datetime]`, `weights: list[dict[str,float]]` (the `final_targets` per scored cycle), `gross: list[float]`, `turnover: list[float]`, `net: list[float]`, `dropped_tail: int`, `assets: tuple[str,...]`.

**Keystone logic (spec 00058 D2, Global Constraints):**
- For each cycle in the clean segment, read its 240-snapshot `last_ts` (the SnapshotEntry with `grid == "240"`; assert `last_ts == cycle_ts − 4h`). The start price for cycle T is the store `240` close at `last_ts(T)`; the end price is the store close at `last_ts(next cycle)` (= `cycle_ts(T)`). Look prices up **by timestamp** in `read_store_series(store_dir, a, 240)` (build a `{ts: close}` dict once per asset).
- Score cycle T only if the NEXT cycle exists in the segment (need the end price) AND `cycle_ts(next) + 0 ≤ now` is not the gate — the gate is: the end price's bar close `≤ now`. Concretely: score T iff `next.cycle_ts ≤ now` and both start/end closes are present & finite. The last segment cycle is never scored (no successor) — that plus the `now` gate is the dropped tail.
- `r_fwd_a(T) = end_close_a / start_close_a − 1`. `gross(T) = Σ_a q_a(T)·r_fwd_a(T)` with `q_a(T) = final_targets[a]`. `turnover(T) = Σ_a |q_a(T) − q_a(T_prev)|`, `q_prev = 0` for the FIRST scored cycle. `net(T) = gross(T) − fee·turnover(T)`.
- Cross-check invariant (VOID trigger in Task 5, computed here): for consecutive scored cycles, `start_close(T+4h) == end_close(T)` to `1e-12` (both are the store close labeled `cycle_ts(T)`). Expose a `chain_ok: bool` on `RealizedSeries`.
- Plausibility: `|r_fwd| ≤ 0.5` per 4h else mark `implausible=True`.

- [ ] **Step 1: Write the failing test — the off-by-one guard (must-fail on injection).**

```python
# tests/test_engine_soak.py — uses a synthetic store + journal
import math
from datetime import UTC, datetime, timedelta
from cli.engine.soak import realized_series, select_clean_segment


def _mk_records_and_store(tmp_path):
    """3 contiguous 4h cycles at 00:00, 04:00, 08:00 on a single asset BTC.

    Store 240 closes (ts-keyed): 20:00→100, 00:00→110, 04:00→121 (each +10%).
    A cycle at cycle_ts=T has its 240 last_ts at T-4h. final_targets BTC = 1.0 each cycle.
    """
    # ... build CycleRecords via journal.CycleRecord(...) with a single SnapshotEntry grid="240",
    #     last_ts = cycle_ts - 4h; write a 240 parquet store with the ts→close map above.
    ...


def test_realized_series_forward_join_and_offbyone_guard(tmp_path):
    records, store_dir, now = _mk_records_and_store(tmp_path)
    rs = realized_series(records, store_dir, fee=0.006, now=now)
    # cycle at 00:00: start=close@(00:00-4h=20:00)=100, end=close@(04:00-4h=00:00)=110 → +10%
    assert math.isclose(rs.gross[0], 1.0 * 0.10, rel_tol=1e-9)
    # only cycle 00:00 and 04:00 are scored (08:00 has no successor); tail dropped
    assert rs.dropped_tail >= 1
    assert rs.chain_ok is True
    # turnover of first scored cycle charges from prev=0: |1.0-0| = 1.0
    assert math.isclose(rs.turnover[0], 1.0, rel_tol=1e-9)


def test_offbyone_shift_breaks_chain(tmp_path):
    """If the join used the WRONG store bar (shifted by one), the chain cross-check must fail."""
    records, store_dir, now = _mk_records_and_store(tmp_path)
    # Corrupt the store so the ts→close map is shifted by one bar; end(T) != start(T+4h).
    # realized_series must set chain_ok=False (Task 5 turns that into a VOID).
    ...
    rs = realized_series(records, store_dir, fee=0.006, now=now)
    assert rs.chain_ok is False
```

(The implementer fills `_mk_records_and_store` per the docstring — it is the fixture both tests share.)

- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** `select_clean_segment` + `realized_series` per the keystone logic. Read `read_store_series` once per asset into a `{ts: close}` dict; assert the `grid=="240"` snapshot `last_ts == cycle_ts − 4h`.
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `feat(cli): soak-check realized forward-return series`.

---

## Task 3: Null construction (windowed + block-bootstrap, D4-cancelling P&L null)

**Files:**
- Modify: `cli/engine/soak.py`
- Test: `tests/test_engine_soak.py`

**Interfaces:**
- Consumes: `crossfreq_system.build_crossfreq_system_fast`, `risk.limits.apply_position_caps`, and the frozen canonical `data/ohlc-full`. **The loader is grounded, not a risk:** `data/ohlc-full/<ASSET>/EUR/<interval>.parquet` is the SAME layout as the engine store (`store._store_path`), so `read_store_series(canonical_dir, a, iv)` reads it directly; union-align the ten assets per grid with `cli/engine/cycle.py`'s `_union_align` (import it, or replicate its `{(a,iv): (ts,closes)}` → `(ts, prices)` per interval). Load the FROZEN set, never the live-appended engine store — the null must be reproducible (immutable, hash-versioned) and not drift as capture continues.
- Produces:
  - `build_null(canonical_dir, config) -> NullSystem` — a dataclass holding per-bar `weights: list[dict[str,float]]` (= `final_targets` per bar), `net_live: list[float]`, `multipliers`, `day_index`, `assets`, plus `reconcile_ok: bool` (the `mult·capped == final_targets` 1e-9 check).
  - `windowed_null(series: list[float], L: int) -> list[float]` — all contiguous overlapping length-L window statistics (mean for P&L-like, mean for rates; the caller picks the reducer). Return the list of per-window window-statistics.
  - `block_bootstrap_null(series, L, *, n=10000, mean_block=6) -> list[float]` — stationary bootstrap; deterministic (no `random`/`Math.random` in scripts, but this is app code — seed a `numpy.random.default_rng(seed)` with a FIXED seed passed in, default 0, so runs are reproducible).

**net_live derivation (Global Constraints, spec 00058 D3/D4):** from `result = build_crossfreq_system_fast(...)`:
```
capped = apply_position_caps(
    {a: [ (result.sleeve_positions["B"][a][k]
           + result.sleeve_positions["A1"][a][k]
           + result.sleeve_positions["A2"][a][k]) / 3.0
          for k in range(n)] for a in assets},
    long_cap=config.long_cap, short_cap=config.short_cap)
mult = result.multipliers
# reconcile: mult[k]*capped[a][k] == result.final_targets[a][k] to 1e-9  (else reconcile_ok=False)
turn_capped[k]  = Σ_a |capped[a][k] - capped[a][k-1]|          # prev=0 at k=0
turn_final[k]   = Σ_a |final_targets[a][k] - final_targets[a][k-1]|
net_live[k] = result.governed_net[k] + mult[k]*fee_builder*turn_capped[k] - fee*turn_final[k]
```
`fee_builder = config.spot_fee_per_side`; `fee = --fee-per-side` (both default 0.006 → the recost is a no-op when fees match AND mult is constant, which is the D4 "INACTIVE this window" case).

- [ ] **Step 1: Write the failing test — reconciliation + net_live identity.**

```python
def test_null_reconciles_and_net_live_matches_governed_when_fees_equal(tmp_path):
    # Build the null over a SMALL synthetic canonical set (few hundred 4h bars) so the builder runs fast.
    null = build_null(canonical_dir, config)  # config with spot_fee_per_side == fee == 0.006
    assert null.reconcile_ok is True
    # With equal fees, net_live == governed_net on every bar where mult is constant across k-1..k;
    # on bars where mult changes, they differ by exactly the D4 gap. Assert the identity holds:
    # net_live[k] == governed_net[k] + mult[k]*0.006*turn_capped[k] - 0.006*turn_final[k]
    ...
```

- [ ] **Step 2–4:** implement, verify fail→pass.
- [ ] **Step 5: Commit** — `feat(cli): soak-check backtest null (windowed + block-bootstrap)`.

---

## Task 4: Verdict engine (per-metric two-sided band, multiplicity, degeneracy)

**Files:** Modify `cli/engine/soak.py`; Test `tests/test_engine_soak.py`.

**Interfaces:**
- Produces: `metric_verdict(live: float, null_values: list[float], *, band=0.90) -> MetricVerdict` (`MetricVerdict` = `verdict: str` ∈ {consistent, weakly-consistent, inconsistent, n/a}, `median`, `lo`, `hi`, `percentile`, `effective_n`, `width`); `assemble_verdicts(live_metrics, null_by_metric, *, band, effective_n_by_metric) -> ReportVerdicts` including the multiplicity summary "X of 7 outside band (≈0.7 expected by chance at 90%)"; `degenerate(live_gross_series, *, floor=1e-6) -> bool`.

- [ ] **Step 1: Write failing tests — planted-consistent, planted-inconsistent, degeneracy, effective-n.**

```python
def test_metric_verdict_consistent_inside_inner_band():
    null = list(range(101))  # 0..100, p5=5 p10=10 p90=90 p95=95
    v = metric_verdict(50, null, band=0.90)
    assert v.verdict == "consistent"

def test_metric_verdict_edge_and_inconsistent():
    null = list(range(101))
    assert metric_verdict(7, null, band=0.90).verdict == "weakly-consistent"   # in [p5,p10)
    assert metric_verdict(200, null, band=0.90).verdict == "inconsistent"      # > p95
    assert metric_verdict(-50, null, band=0.90).verdict == "inconsistent"      # < p5 (too-low also flags)

def test_metric_verdict_na_on_zero_width():
    assert metric_verdict(1.0, [3.0] * 50, band=0.90).verdict == "n/a"

def test_degenerate_window_flagged():
    assert degenerate([0.0, 1e-9, 0.0]) is True
    assert degenerate([0.3, 0.25, 0.28]) is False
```

- [ ] **Steps 2–4:** implement (percentiles via `numpy.percentile` with linear interpolation; effective_n passed in — for governor it's ≈#days), verify.
- [ ] **Step 5: Commit** — `feat(cli): soak-check verdict engine + multiplicity`.

---

## Task 5: Falsification guards / self-tests (VOID gates)

**Files:** Modify `cli/engine/soak.py`; Test `tests/test_engine_soak.py`.

**Interfaces:**
- Produces: `self_tests(records, null, config, registry_path) -> SelfTestReport` (`instrument_ok`, `identity_ok`, `reconcile_ok`, `messages`), each VOID-on-failure:
  - **instrument** — a frozen build reproduces registry **record 44** figures within the registry's own tolerances (read `docs/reference/trial-registry.jsonl`, find record 44, compare the builder's headline stats). If the canonical set isn't present, `instrument_ok=None` (skip, not fail) — mirrors the data-dependent regression-test convention.
  - **identity** — journaled `final_targets == replay_cycle(fast)` to `1e-6` for a sampled cycle (reuse `concordance.replay_cycle`).
  - **reconcile** — `null.reconcile_ok` (Task 3) AND `realized.chain_ok` (Task 2).
- `plausibility(realized, null) -> list[str]` — the bound checks (Global Constraints); any hit → a "no verdict" reason.

- [ ] **Step 1: Write failing tests — identity VOID on tampered targets, asset-drift abort, chain VOID.**

```python
def test_identity_void_on_tampered_targets(...):
    # a journal whose final_targets are perturbed off replay_cycle by > 1e-6 → identity_ok False
    ...

def test_asset_set_drift_aborts(...):
    # journal final_targets over {BTC,ETH}; config universe {BTC,ETH,SOL} → SoakError
    ...
```

- [ ] **Steps 2–4:** implement (`SoakError` in `cli/engine/soak.py`), verify.
- [ ] **Step 5: Commit** — `feat(cli): soak-check falsification self-tests`.

---

## Task 6: Report rendering (banner, table, vocabulary lock)

**Files:** Modify `cli/engine/soak.py`; Test `tests/test_engine_soak.py`.

**Interfaces:**
- Produces: `render_report(realized, null, verdicts, self_tests, d4_gap, *, band) -> str` — the 10-line-block text (spec 00058 "Report shape"): banner → provenance → self-tests → degeneracy → structural table + multiplicity → governor/cap block (n≈days caveat + transition count) → D4 gap ACTIVE/INACTIVE → non-gating P&L block → regime context → honesty footer. Also `soak_report(...) -> tuple[str, dict]` orchestrating Tasks 1–6 end-to-end and returning `(text, json_payload)`.
- The BANNER constant (verbatim, spec 00058 Goal): the zero-OOS bare fact.

- [ ] **Step 1: Write failing tests — banner present, vocabulary lock, multiplicity line present.**

```python
FORBIDDEN = ("validated", "passed", "confirmed", "proven")

def test_report_banner_and_vocabulary_lock(...):
    text = render_report(...)
    assert "ZERO out-of-time holdout" in text
    low = text.lower()
    for w in FORBIDDEN:
        assert w not in low
    assert "expected by chance" in low  # multiplicity summary line
```

- [ ] **Steps 2–4:** implement, verify.
- [ ] **Step 5: Commit** — `feat(cli): soak-check report rendering`.

---

## Task 7: CLI command + JSON + docs

**Files:** Modify `cli/engine/command.py`; Create `tests/test_engine_soak_command.py`; Modify `README.md`, `docs/iterations-history-phase1.md`.

**Interfaces:**
- Consumes: `command._journal_artifacts`/`_snapshot_reader`, `soak.soak_report`.
- The command: `soak-check` on the existing `engine` Typer sub-app. Options per spec 00058: `--journal-dir` (default `config.journal_dir`), `--store-dir` (default `config.store_dir`), `--canonical-dir` (default `data/ohlc-full`), `--fee-per-side` (0.006), `--band` (0.90), `--floor` (30), `--null [windows|block-bootstrap|both]` (both), `--path [fast|verified]` (fast), `--json PATH` (atomic `.tmp` + `os.replace`). Prints the report text via the logger/echo like `report`; exit 0 on emit, non-zero only on operational failure or a VOID self-test. **Every option's help string must pass the `_INTERNAL` hygiene regex** (no `iter-N`/`spec NNNNN`/`OPS-N`/`phase-N`/`TNNNN`).

- [ ] **Step 1: Write failing command test** (`CliRunner`, synthetic journal+store+small canonical) — asserts exit 0, banner in output, `--json` writes a payload with the metric rows.
- [ ] **Step 2–4:** implement, verify. Run the full `uv run pytest tests/test_engine_soak.py tests/test_engine_soak_command.py -v`.
- [ ] **Step 5: Docs** — add the `soak-check` entry to `README.md` `## Usage`; append the iterations-history closeout entry to `docs/iterations-history-phase1.md` (what landed, the off-by-one keystone, the VOID self-tests, the zero-OOS banner, that it consumes no holdout budget and is decision-support for T0064). **Deferral sweep** per open-topics: flip [[T0064]] to `partial` (the OOS report exists; the go-live judgment remains human-gated) with a `## Done so far` linking this PR, and sync the index. Any residual (e.g. "run against the real ≥14-day journal at the gate") → a `ripe_when: the Stage-6a soak gate is reached (≥14 clean complete-UTC days)` note on T0064's remaining next-step.
- [ ] **Step 6: Commit** — `docs(cli): soak-check usage + closeout` (closeout-docs commit; user-approval-as-review exemption applies) and the code commit `feat(cli): zcrypto engine soak-check command`.

---

## Self-Review notes (author)

- Spec coverage: D1→Task 7; D2→Tasks 1–2; D3/D4→Task 3; D5→Tasks 1,4,6; D6→Tasks 2 (chain),3 (reconcile),5 (self-tests),4 (degeneracy). Report shape→Task 6. Test list items 1–14 map: 1→T2, 2/3→T4, 4→T4, 5→T2, 6→T3, 7→T5, 8→T2, 9→T2, 10→T5, 11→T3, 12→T6, 13→T4, 14→T4/T6.
- Type consistency: `weights_by_bar: list[dict[str,float]]` is the shared currency across Tasks 1/3/4; `final_targets` (journal) and `result.final_targets` (builder) are both `dict[str, list[float]]`-shaped once transposed to per-bar dicts — the transpose helper lives in Task 1.
- All APIs grounded against the real code: `journal.from_json`/`SnapshotEntry` (grid `"240"`/`"1440"`, `last_ts == cycle_ts−4h`), `store.read_store_series` + the shared `<asset>/EUR/<interval>.parquet` layout (so `data/ohlc-full` reads with the same reader), `crossfreq_system.build_crossfreq_system_fast` → `CrossfreqSystemResult{final_targets, governed_net, ungoverned_net, multipliers, sleeve_positions={B,A1,A2}, cap_breach_bars, governor_engaged_bars, day_index, n_periods}`, `risk.limits.apply_position_caps(dict,*,long_cap,short_cap)`, `concordance.replay_cycle`, `cycle._union_align`. The `net_live` identity is derivable from returned quantities alone — no builder-internal `ret_h` needed.
