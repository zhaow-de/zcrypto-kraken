# Stage-6b Feeder Measurements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `zcrypto engine decompose` and `zcrypto engine accum-replay` per spec `00081`, then run both over the 136-cycle journal and record the answers in [[T0117]] and [[T0118]].

**Architecture:** One new module `cli/engine/feeders.py` with two pure report functions over a shared per-cycle replay; two thin CLI commands in the existing `engine_app`. Read-only over a pulled journal replica — no builder change, no live path touched.

**Tech Stack:** Python 3.14 (uv-locked), polars (via the existing snapshot reader), Typer, pytest.

## Global Constraints

- Run everything through uv. Stage by explicit path (never `git add -A`). Conventional Commits.
- Every commit ends with the authoring model's `Co-Authored-By:` trailer and gets a different-agent review before push (`commit-messages.md`).
- **No change to `cli/portfolio/crossfreq_system.py` or any builder/risk module.** The harness reads public parts only. A task that finds itself editing the builder has misread the spec — stop and report.
- **Both commands are read-only.** They open the journal for reading and write nothing under it.
- CLI `--help` text and all runtime output: no `T<NNNN>`, spec serials, or phase tokens (`tests/test_internal_terms_not_operator_visible.py` walks non-docstring literals in `cli/`).
- `README.md` `## Usage` gains both subcommands in the same change that adds them (`readme-usage.md`).
- The journal replica is at `/mnt/zhao-crypto/engine-journal` (read-only NFS — **never write through it**). 136 records, 2026-07-11 → 2026-08-02.

## File Structure

- `cli/engine/feeders.py` (new) — `replay_stages`, `decompose_report`, `accumulation_report` + their dataclasses.
- `cli/engine/command.py` (modify) — two `@engine_app.command(...)` wrappers.
- `tests/test_engine_feeders.py` (new) — all unit tests; fixtures hand-built, no journal dependency.
- `README.md` (modify) — Usage entries.

---

### Task 1: The per-cycle stage extraction (`replay_stages`)

**Files:**
- Create: `cli/engine/feeders.py`
- Test: `tests/test_engine_feeders.py`

**Interfaces:**
- Consumes: `cli.engine.journal.CycleRecord`, `cli.engine.concordance.replay_cycle`'s reader contract, `cli.portfolio.crossfreq_system.build_crossfreq_system_fast`, `cli.risk.apply_position_caps`.
- Produces: `CycleStages` dataclass + `replay_stages(record, reader) -> CycleStages`, consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine_feeders.py`:

```python
import math

import pytest

from cli.engine.feeders import CycleStages, cancellation_ratio, stage_grosses


def test_stage_grosses_sums_absolute_positions():
    sleeves = {"B": {"BTC": 0.10, "ETH": -0.04}, "A1": {"BTC": 0.02, "ETH": 0.0}, "A2": {"BTC": 0.0, "ETH": 0.06}}
    g = stage_grosses(sleeves)
    assert g["B"] == pytest.approx(0.14)
    assert g["A1"] == pytest.approx(0.02)
    assert g["A2"] == pytest.approx(0.06)


def test_cancellation_ratio_is_one_when_sleeves_agree():
    # Identical sleeves: the 1/3 combination reproduces them exactly, so nothing cancels.
    one = {"BTC": 0.09, "ETH": 0.03}
    ratio, combined_gross, mean_sleeve_gross = cancellation_ratio({"B": one, "A1": one, "A2": one})
    assert ratio == pytest.approx(1.0)
    assert combined_gross == pytest.approx(0.12)
    assert mean_sleeve_gross == pytest.approx(0.12)


def test_cancellation_ratio_below_one_when_sleeves_oppose():
    # B and A1 cancel on BTC; A2 is flat there. Combined BTC = 0, so gross drops.
    sleeves = {"B": {"BTC": 0.09}, "A1": {"BTC": -0.09}, "A2": {"BTC": 0.0}}
    ratio, combined_gross, mean_sleeve_gross = cancellation_ratio(sleeves)
    assert combined_gross == pytest.approx(0.0)
    assert mean_sleeve_gross == pytest.approx(0.06)
    assert ratio == pytest.approx(0.0)


def test_cancellation_ratio_is_nan_on_a_flat_book():
    # All sleeves flat: the ratio is 0/0. Report NaN rather than inventing 1.0 or crashing.
    flat = {"BTC": 0.0}
    ratio, _, _ = cancellation_ratio({"B": flat, "A1": flat, "A2": flat})
    assert math.isnan(ratio)
```

- [ ] **Step 2: Run them — they must fail on the missing module**

Run: `uv run pytest tests/test_engine_feeders.py -v`
Expected: collection error / ImportError on `cli.engine.feeders`. Anything else means the file already exists — stop and report.

- [ ] **Step 3: Write the module's stage layer**

Create `cli/engine/feeders.py`:

```python
"""Read-only measurements over the journaled shadow cycles, feeding the go-live sizing questions.

Two reports share one replay: `decompose_report` attributes a cycle's gross across the pipeline's
stages (per-sleeve -> combined -> capped -> governed), and `accumulation_report` simulates an
accumulate-until-placeable order policy against Kraken's venue minimums to measure the drift floor
those minimums impose. Neither writes anything, and neither touches the builder: every stage is
recomputed from public parts and then PROVEN against the builder's own output (see
`replay_stages`), so a builder change surfaces as a raised error rather than a silently wrong table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from cli.engine.errors import EngineError
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, validate_record
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, build_crossfreq_system_fast
from cli.risk import apply_position_caps

SLEEVES = ("B", "A1", "A2")

Reader = Callable[[SnapshotEntry], tuple[list[datetime], list[float | None]]]


@dataclass(frozen=True)
class CycleStages:
    """One cycle's forming-row book at each pipeline stage, plus the governor multiplier."""

    cycle_ts: datetime
    sleeve_positions: dict[str, dict[str, float]]  # per sleeve, per asset
    combined: dict[str, float]
    capped: dict[str, float]
    final: dict[str, float]
    multiplier: float
    closes: dict[str, float]  # the 4h close used for the forming row, per asset
    cap_bound: bool


def stage_grosses(sleeve_positions: dict[str, dict[str, float]]) -> dict[str, float]:
    """Gross (sum of absolute positions) for each sleeve."""
    return {name: sum(abs(v) for v in book.values()) for name, book in sleeve_positions.items()}


def cancellation_ratio(sleeve_positions: dict[str, dict[str, float]]) -> tuple[float, float, float]:
    """Return `(ratio, combined_gross, mean_sleeve_gross)`.

    The 1/3 combination nets opposing sleeve positions away asset by asset, so the combined book's
    gross is NOT the mean of the sleeve grosses. The ratio names how much of the sleeves' exposure
    survives the combination: 1.0 = they agree and nothing cancels; well below 1.0 = disagreement
    is where gross is going. NaN on a flat book (0/0) -- reporting 1.0 there would claim agreement
    that was never demonstrated.
    """
    assets = {a for book in sleeve_positions.values() for a in book}
    third = 1 / 3
    combined_gross = sum(abs(sum(third * book.get(a, 0.0) for book in sleeve_positions.values())) for a in assets)
    grosses = stage_grosses(sleeve_positions)
    mean_sleeve_gross = sum(grosses.values()) / len(grosses) if grosses else 0.0
    ratio = combined_gross / mean_sleeve_gross if mean_sleeve_gross else math.nan
    return ratio, combined_gross, mean_sleeve_gross
```

- [ ] **Step 4: Run the tests — they must pass**

Run: `uv run pytest tests/test_engine_feeders.py -v`
Expected: 4 passed.

- [ ] **Step 5: Add `replay_stages` with its self-proving identity**

Append to `cli/engine/feeders.py`:

```python
def replay_stages(record: CycleRecord, reader: Reader, *, config: CrossfreqSystemConfig | None = None) -> CycleStages:
    """Rebuild one journaled cycle and return its forming-row book at every pipeline stage.

    Two identities, both per cycle, because they catch different failures. INTERNAL:
    `multiplier * capped[a]` must equal the builder's own `final_targets[a]` exactly -- evidence
    the recomputed intermediate IS the builder's, so a changed combination or cap raises instead of
    reporting a wrong attribution. JOURNAL: the rebuilt targets must equal the RECORD's own
    `final_targets` -- which the internal one structurally cannot catch, since a self-consistent
    rebuild that diverges from what the engine actually traded would agree with itself all the way
    and both reports would describe a book that never existed.
    """
    c = config or CrossfreqSystemConfig()
    validate_record(record)  # no-peek + snapshot-boundary discipline, before any snapshot is read
    by_grid: dict[str, dict[str, tuple[list[datetime], list[float | None]]]] = {"1440": {}, "240": {}}
    for entry in record.snapshots:
        ts, closes = reader(entry)
        if snapshot_content_hash(ts, closes) != entry.content_hash:
            raise EngineError(f"content hash mismatch for pair={entry.pair!r} grid={entry.grid!r} -- corrupt evidence")
        # Metadata-vs-data reconciliation: validate_record pins the metadata and the hash pins the
        # data, but NOTHING otherwise ties one to the other -- so data ending at the wrong bar, or
        # extending past cycle_ts (look-ahead), passes both behind honest-looking metadata.
        if len(ts) != entry.n_bars or ts[0] != entry.first_ts or ts[-1] != entry.last_ts:
            raise EngineError(
                f"pair={entry.pair!r} grid={entry.grid!r}: read data disagrees with its own journaled metadata -- "
                f"n_bars={len(ts)} vs {entry.n_bars!r}, first_ts={ts[0]!r} vs {entry.first_ts!r}, "
                f"last_ts={ts[-1]!r} vs {entry.last_ts!r}"
            )
        by_grid[entry.grid][entry.pair] = (ts, closes)

    def assemble(grid: str) -> tuple[list[datetime], dict[str, list[float | None]]]:
        shared: list[datetime] | None = None
        prices: dict[str, list[float | None]] = {}
        for pair, (ts, closes) in by_grid[grid].items():
            if shared is None:
                shared = ts
            elif ts != shared:
                raise EngineError(f"pair={pair!r} grid={grid!r} ts calendar disagrees with the grid's shared calendar")
            prices[pair] = closes
        if shared is None:
            raise EngineError(f"no snapshots for grid={grid!r}")
        return shared, prices

    daily_ts, daily_prices = assemble("1440")
    h4_ts, h4_prices = assemble("240")
    # The forming row must BE the cycle's row, re-derived from the data just read rather than
    # trusted from metadata -- `replay_cycle` enforces the same thing for the same reason.
    if h4_ts[-1] != record.cycle_ts - timedelta(hours=4):
        raise EngineError(
            f"the builder's grid does not contain the cycle_ts interval: h4_ts[-1]={h4_ts[-1]!r} != "
            f"cycle_ts - 4h ({record.cycle_ts - timedelta(hours=4)!r})"
        )
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=c)
    n = result.n_periods

    sleeves = {name: {a: result.sleeve_positions[name][a][n] for a in c.assets} for name in SLEEVES}
    third = 1 / 3
    # CHAINED `+`, never sum(): the builder computes `third*b + third*a1 + third*a2`, and since
    # Python 3.12 sum() applies Neumaier compensation to floats, so the two disagree by 1 ulp on
    # ~17% of real triples (measured, 3.14.6). Under the exact `!=` identity below that would raise
    # on roughly one cycle in five and leave the aggregates computed over the biased subset that
    # happens to bit-agree. Match the builder's expression exactly.
    combined = {a: third * sleeves["B"][a] + third * sleeves["A1"][a] + third * sleeves["A2"][a] for a in c.assets}
    capped_series = apply_position_caps({a: [combined[a]] for a in c.assets}, long_cap=c.long_cap, short_cap=c.short_cap)
    capped = {a: capped_series[a][0] for a in c.assets}
    multiplier = result.multipliers[n]
    final = {a: result.final_targets[a][n] for a in c.assets}

    _check_stage_identity(multiplier, capped, final, cycle_ts=record.cycle_ts)

    # The journal identity: what we rebuilt must be what the engine actually traded.
    if set(final) != set(record.final_targets):
        raise EngineError(
            f"rebuilt asset set differs from the journaled one at cycle_ts={record.cycle_ts}: "
            f"{sorted(set(final) ^ set(record.final_targets))}"
        )
    for a, journaled in record.final_targets.items():
        if final[a] != journaled:
            raise EngineError(
                f"replay disagrees with the journal for asset={a!r} at cycle_ts={record.cycle_ts}: "
                f"rebuilt={final[a]!r} != journaled={journaled!r} -- this cycle's rebuild does not "
                "describe the book the engine traded"
            )

    closes = {}
    for a in c.assets:
        series = h4_prices[a]
        value = series[-1]
        if value is None:
            raise EngineError(f"the forming row's close is missing for asset={a!r} at cycle_ts={record.cycle_ts}")
        closes[a] = float(value)

    return CycleStages(
        cycle_ts=record.cycle_ts,
        sleeve_positions=sleeves,
        combined=combined,
        capped=capped,
        final=final,
        multiplier=multiplier,
        closes=closes,
        cap_bound=any(abs(capped[a] - combined[a]) > 1e-15 for a in c.assets),
    )
```

- [ ] **Step 6: Extract the identity as a pure helper and test it directly**

The comparison is a pure function, so it needs no builder-reaching stub and keeps a committed regression test after the branch-time mutation proof is gone. Add to `cli/engine/feeders.py`:

```python
def _check_stage_identity(multiplier: float, capped: dict[str, float], final: dict[str, float], *, cycle_ts) -> None:
    """Raise unless `multiplier * capped[a] == final[a]` exactly, for every asset.

    Exact equality is correct here, not float-fragile: the harness reruns the builder's own
    arithmetic on the builder's own floats in the same order (`sleeve_positions` stores the
    already-4h-expanded series, and apply_position_caps is a pure per-element clip), so any
    difference means the recomputation genuinely diverged.
    """
    for a, target in final.items():
        if multiplier * capped[a] != target:
            raise EngineError(
                f"stage identity broken for asset={a!r} at cycle_ts={cycle_ts}: "
                f"multiplier*capped={multiplier * capped[a]!r} != builder final_targets={target!r} -- "
                "the recomputed combination or cap no longer matches the builder"
            )
```

And its test:

```python
def test_stage_identity_raises_when_the_recomputation_disagrees():
    from cli.engine.feeders import _check_stage_identity

    _check_stage_identity(0.5, {"BTC": 0.10}, {"BTC": 0.05}, cycle_ts="t")  # holds, no raise
    with pytest.raises(Exception, match="stage identity broken"):
        _check_stage_identity(0.5, {"BTC": 0.10}, {"BTC": 0.06}, cycle_ts="t")
```

- [ ] **Step 7: Run and commit**

Run: `uv run pytest tests/test_engine_feeders.py -v`

```bash
git add cli/engine/feeders.py tests/test_engine_feeders.py
git commit -m "feat(engine): per-cycle stage extraction for the sizing measurements"
```

---

### Task 2: `decompose_report` — the attribution table

**Files:**
- Modify: `cli/engine/feeders.py`
- Test: `tests/test_engine_feeders.py`

**Interfaces:**
- Consumes: `replay_stages` (Task 1).
- Produces: `decompose_report(records, reader) -> tuple[str, dict]` — rendered text plus a payload dict, matching `cli.engine.soak.soak_report`'s existing shape.

- [ ] **Step 1: Write the failing test**

```python
def test_decompose_payload_reports_every_stage_and_the_ratios():
    stages = [
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 12, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.12}, "A1": {"BTC": 0.06}, "A2": {"BTC": 0.0}},
            combined={"BTC": 0.06},
            capped={"BTC": 0.06},
            final={"BTC": 0.03},
            multiplier=0.5,
            closes={"BTC": 50000.0},
            cap_bound=False,
        )
    ]
    payload = decompose_payload(stages)
    row = payload["cycles"][0]
    assert row["combined_gross"] == pytest.approx(0.06)
    assert row["capped_gross"] == pytest.approx(0.06)
    assert row["final_gross"] == pytest.approx(0.03)
    assert row["multiplier"] == pytest.approx(0.5)
    assert row["n_active"] == 1
    # mean sleeve gross = (0.12 + 0.06 + 0.0)/3 = 0.06; combined = 0.06 -> ratio 1.0
    assert row["cancellation_ratio"] == pytest.approx(1.0)
    assert payload["n_cycles"] == 1
```

- [ ] **Step 2: Run it — expect ImportError on `decompose_payload`**

- [ ] **Step 3: Implement `decompose_payload` + `decompose_report`**

```python
def decompose_payload(stages: list[CycleStages]) -> dict:
    """Per-cycle attribution rows plus their aggregates. Pure -- no I/O, no replay."""
    rows = []
    for s in stages:
        ratio, combined_gross, mean_sleeve_gross = cancellation_ratio(s.sleeve_positions)
        rows.append(
            {
                "cycle_ts": s.cycle_ts.isoformat(),
                "sleeve_gross": stage_grosses(s.sleeve_positions),
                "mean_sleeve_gross": mean_sleeve_gross,
                "combined_gross": combined_gross,
                "cancellation_ratio": ratio,
                "capped_gross": sum(abs(v) for v in s.capped.values()),
                "multiplier": s.multiplier,
                "final_gross": sum(abs(v) for v in s.final.values()),
                "n_active": sum(1 for v in s.final.values() if v != 0.0),
                "cap_bound": s.cap_bound,
            }
        )

    def _median(values: list[float]) -> float:
        clean = sorted(v for v in values if not math.isnan(v))
        if not clean:
            return math.nan
        mid = len(clean) // 2
        return clean[mid] if len(clean) % 2 else (clean[mid - 1] + clean[mid]) / 2

    return {
        "n_cycles": len(rows),
        "cycles": rows,
        "median": {
            key: _median([r[key] for r in rows])
            for key in ("mean_sleeve_gross", "combined_gross", "cancellation_ratio", "capped_gross", "final_gross", "multiplier")
        },
    }
```

Add a per-cycle `capped_ratio` (`capped_gross / combined_gross`, NaN when combined is 0) and `governed_ratio` (`= multiplier`) to each row, and include both in the `median` block — so all three consecutive-stage ratios are **medians of per-cycle ratios**, one basis throughout. Never a ratio of medians: with the multiplier varying across the window the two differ materially in the headline number, which is what the Task 3 two-cycle fixture pins.

Then `decompose_report(stages) -> tuple[str, dict]` rendering a fixed-width table: one line per cycle with `cycle_ts`, the three sleeve grosses, `combined`, `ratio`, `capped`, `mult`, `final`, `n_active`, `cap_bound`; then a MEDIAN row; then a short attribution summary naming each consecutive ratio (`sleeve→combined`, `combined→capped`, `capped→final`) and the count of cap-bound cycles, so the reader sees which stage the gross is lost at. Plain operator language, no internal tokens.

- [ ] **Step 4: Run tests, then commit**

```bash
git add cli/engine/feeders.py tests/test_engine_feeders.py
git commit -m "feat(engine): attribute a cycle's gross across the pipeline stages"
```

---

### Task 3: `accumulation_report` — the drift floor

**Files:**
- Modify: `cli/engine/feeders.py`
- Test: `tests/test_engine_feeders.py`

**Interfaces:**
- Consumes: `CycleStages` (for `final` weights and `closes`), plus a `minimums: dict[str, tuple[float, float]]` mapping asset → `(ordermin_base, costmin)`.
- Produces: `accumulation_payload(stages, minimums, navs) -> dict`, `accumulation_report(...) -> tuple[str, dict]`, and `load_minimums(path) -> dict` reading the canonical snapshot.

- [ ] **Step 1: Write the failing tests — the policy's edges**

```python
def _stage(ts, weight, close):
    return CycleStages(
        cycle_ts=ts, sleeve_positions={s: {"BTC": 0.0} for s in ("B", "A1", "A2")},
        combined={"BTC": 0.0}, capped={"BTC": 0.0}, final={"BTC": weight},
        multiplier=1.0, closes={"BTC": close}, cap_bound=False,
    )


def test_delta_below_ordermin_is_not_placed_and_accumulates():
    # target 0.001 BTC/cycle against an ordermin of 0.005: nothing places until it crosses.
    stages = [_stage(datetime(2026, 8, 1, h, tzinfo=UTC), 0.001 * (i + 1), 1000.0) for i, h in enumerate((0, 4, 8, 12, 16, 20))]
    payload = accumulation_payload(stages, {"BTC": (0.005, 0.45)}, [1000.0])
    placed = [c["placed"] for c in payload["by_nav"][1000.0]["cycles"]]
    assert placed[:4] == [False, False, False, False]   # 1..4 units of 0.001 < 0.005
    assert placed[4] is True                            # the 5th crosses the floor
    assert payload["by_nav"][1000.0]["cycles"][4]["drift_eur"] == pytest.approx(0.0)


def test_costmin_refuses_a_delta_that_clears_the_quantity_floor():
    # target_qty = 0.1*1.0/0.10 = 1.0 unit: clears ordermin 0.5, but is worth EUR 0.10 < costmin.
    # (An earlier draft used weight=1.0, giving 10 units worth EUR 1.00 -- which places, so the
    # test was red against correct code. The arithmetic is the test here; check it, don't eyeball.)
    stages = [_stage(datetime(2026, 8, 1, 0, tzinfo=UTC), 0.1, 0.10)]
    payload = accumulation_payload(stages, {"BTC": (0.5, 0.45)}, [1.0])
    assert payload["by_nav"][1.0]["cycles"][0]["placed"] is False


def test_a_price_move_alone_changes_drift_with_no_order_placed():
    # THE HELD POSITION MUST BE NONZERO or this test proves nothing: at held_qty=0 the drift is
    # target_qty*close = weight*NAV, the close CANCELS, and a EUR-denominated held state gives
    # byte-identical output. So: cycle 1 places (held=10.0 units), then the close moves by less
    # than the floor, so cycle 2 places nothing and its drift is pure re-pricing.
    stages = [
        _stage(datetime(2026, 8, 1, 0, tzinfo=UTC), 1.0, 100.0),
        _stage(datetime(2026, 8, 1, 4, tzinfo=UTC), 1.0, 100.5),
    ]
    payload = accumulation_payload(stages, {"BTC": (0.1, 0.0)}, [1000.0])
    cycles = payload["by_nav"][1000.0]["cycles"]
    assert cycles[0]["placed"] is True
    assert cycles[0]["drift_eur"] == pytest.approx(0.0)          # placed -> exactly on target
    assert cycles[1]["placed"] is False                          # |delta| ~ 0.0498 < ordermin 0.1
    assert cycles[1]["target_qty"]["BTC"] == pytest.approx(1000.0 / 100.5)
    # held 10.0 units vs target ~9.9502 -> ~0.0498 units * 100.5 ~= EUR 5.00 of pure re-pricing.
    assert cycles[1]["drift_eur"] == pytest.approx(5.0, abs=0.05)


def test_an_unplaced_asset_cycle_always_sits_below_its_floor():
    # The true invariant (spec Verification). NAV-monotonicity is NOT one and must not be asserted:
    # held histories diverge across NAV rungs, so a lower NAV just after placing can beat a higher
    # one carrying a fresh sub-floor residual.
    stages = [_stage(datetime(2026, 8, 1, h, tzinfo=UTC), 0.001 * (i + 1), 100.0) for i, h in enumerate((0, 4, 8, 12))]
    payload = accumulation_payload(stages, {"BTC": (0.05, 0.45)}, [1000.0])
    for cycle in payload["by_nav"][1000.0]["cycles"]:
        if not cycle["placed"]:
            assert cycle["drift_eur"] < max(0.05 * 100.0, 0.45)


def test_stage_ratios_use_the_median_of_per_cycle_ratios():
    # Two asymmetric cycles: median-of-ratios and ratio-of-medians differ, so this pins the basis.
    # A single-cycle fixture cannot -- there the two definitions coincide.
    stages = [
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 0, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.12}, "A1": {"BTC": 0.12}, "A2": {"BTC": 0.12}},
            combined={"BTC": 0.12}, capped={"BTC": 0.12}, final={"BTC": 0.12},
            multiplier=1.0, closes={"BTC": 100.0}, cap_bound=False,
        ),
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 4, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.09}, "A1": {"BTC": -0.09}, "A2": {"BTC": 0.0}},
            combined={"BTC": 0.0}, capped={"BTC": 0.0}, final={"BTC": 0.0},
            multiplier=0.5, closes={"BTC": 100.0}, cap_bound=False,
        ),
    ]
    payload = decompose_payload(stages)
    # per-cycle cancellation ratios are 1.0 and 0.0 -> median 0.5.
    # ratio-of-medians would be median(combined)/median(mean_sleeve) = 0.06/0.09 = 0.667.
    assert payload["median"]["cancellation_ratio"] == pytest.approx(0.5)
```

- [ ] **Step 2: Run them — expect ImportError**

- [ ] **Step 3: Implement the policy exactly as spec D4 states**

Per NAV, iterate `stages` in `cycle_ts` order carrying `held_qty: dict[str, float]` initialised to 0.0:

```python
target_qty = (final[a] * nav) / closes[a]
delta_qty = target_qty - held_qty[a]
ordermin_base, costmin = minimums[a]
placed_a = abs(delta_qty) >= ordermin_base and abs(delta_qty) * closes[a] >= costmin
if placed_a:
    held_qty[a] = target_qty
drift_eur_a = abs(target_qty - held_qty[a]) * closes[a]
```

Per cycle record `placed` (True iff any asset placed), the per-asset `target_qty`, and `drift_eur = sum(drift_eur_a)`. Per NAV report per-cycle `median_drift_bps` and `p95_drift_bps` (= drift_eur / nav × 10_000, meaningful over 136 points).

**The weekly aggregation prints every week, and reports NO weekly p95** (spec D6). The journal spans exactly **4 ISO weeks — (2026,28) 12 cycles, (2026,29) 42, (2026,30) 42, (2026,31) 40** (measured), and the first is a 2-day partial. Emit a row per week: `(iso_year, iso_week), n_cycles, mean_drift_bps`, with the partial week flagged — a p95 over 4 points is the maximum wearing a percentile's name, and this number becomes a live-trading gate band.

`load_minimums(path)` reads the canonical snapshot JSON and returns `({asset: (ordermin_base, costmin)}, fetched_at)`.

**Read the `universe` block, NOT `raw["assetpairs"]`, and filter the quote — both traps are measured, and both yield a silently wrong floor rather than an error:**

```python
def load_minimums(path: Path) -> tuple[dict[str, tuple[float, float]], str]:
    """Per-asset (ordermin_base, costmin) for the EUR book, plus the snapshot's fetched_at stamp.

    Sourced from the snapshot's `universe` block, which is already normalised to base/quote —
    NOT from `raw.assetpairs`, where Kraken lists DOGE as `XDG/EUR` (there is no `DOGE/EUR`
    wsname at all) and BTC as `XBT/EUR`, so a `<ASSET>/EUR` match silently loses assets.
    The `quote == "EUR"` filter is load-bearing: `universe` also carries ETH/BTC and SOL/BTC
    whose costmin is 0.00002 BTC, and keying by base without it would overwrite ETH's and
    SOL's EUR floors with a BTC-denominated number read as euros.
    """
    payload = json.loads(path.read_text())
    out: dict[str, tuple[float, float]] = {}
    for entry in payload["universe"]:
        if entry.get("quote") != "EUR":
            continue
        base = entry["base"]
        if base in out:
            raise EngineError(f"duplicate EUR pair for base={base!r} in {path} -- ambiguous minimums")
        out[base] = (float(entry["ordermin"]), float(entry["costmin"]))
    return out, payload["fetched_at"]
```

The caller raises on any configured asset missing from the returned map — a silently absent floor would understate drift. A test pins that DOGE resolves (ordermin 50) and that ETH's costmin is 0.45, not 0.00002.

- [ ] **Step 4: Run tests, then commit**

```bash
git add cli/engine/feeders.py tests/test_engine_feeders.py
git commit -m "feat(engine): simulate the accumulate-until-placeable policy to measure its drift floor"
```

---

### Task 4: The two CLI commands, README, and the live runs

**Files:**
- Modify: `cli/engine/command.py`, `README.md`
- Test: `tests/test_engine_feeders.py` (CLI smoke via Typer's `CliRunner`)

- [ ] **Step 1: Add both commands**

In `cli/engine/command.py`, mirroring `soak_check`'s existing shape (`--journal-dir` default from config, `_snapshot_reader(journal_root)`, iterate day-dirs' `cycle-*.json` via the same discovery `soak_check`/`report` already use):

- `@engine_app.command(name="decompose")` — options `--journal-dir`, `--since` / `--until` (optional ISO dates), `--json` (emit the payload instead of the table). Help text: "Attribute each journaled cycle's gross across the pipeline stages."
- `@engine_app.command(name="accum-replay")` — same journal options plus `--minimums` (path, default `data/snapshots/…` resolved from config or the newest `kraken-refdata-*.json`) and `--nav` (repeatable float, default `500, 1000, 2500, 5000, 10000`). Help text: "Measure the position drift the venue's order minimums impose at each portfolio size."

`accumulation_report`'s rendering **prints the minimums' `fetched_at` stamp beside the drift table** (spec D8) — these floors move, and a band quoted at the gate from a stale table is the silent-staleness failure the monthly refresh exists to prevent. A test asserts the stamp appears in the rendered output.

A record that fails to replay is **reported with its cycle_ts and the error, and counted** — never silently skipped (spec Verification).

- [ ] **Step 2: CLI smoke tests**

Two `CliRunner` tests: each command with `--help` exits 0 and mentions its purpose; each against a tmp journal dir containing zero records exits non-zero with a clear "no cycle records found" message rather than an empty table.

- [ ] **Step 3: README**

Add both to `## Usage` under the `engine` group, matching the surrounding entries' format.

- [ ] **Step 4: Run the full suite + gate, then commit**

```bash
uv run pytest
uv run pre-commit run -a
git add cli/engine/command.py cli/engine/feeders.py tests/test_engine_feeders.py README.md
git commit -m "feat(engine): expose the two sizing measurements as engine subcommands"
```

- [ ] **Step 5: The live runs (ORCHESTRATOR, main loop — the journal is on an NFS mount)**

```bash
uv run zcrypto engine decompose --journal-dir /mnt/zhao-crypto/engine-journal
uv run zcrypto engine accum-replay --journal-dir /mnt/zhao-crypto/engine-journal
```

~3.4 min each. Save both outputs to the scratchpad. **Read the numbers, do not just capture them** — in particular whether the multiplier is 0.5 across the whole window or varies, and which consecutive ratio is smallest (that is the answer to "where does 15–20 % die").

- [ ] **Step 6: Prove BOTH identity guards bite, on real data**

`1 / 3` → `1 / 2` is a **same-length** edit, and the `.pyc` cache key is (mtime-seconds, size) — so a same-second edit runs unmutated code and "the guard didn't bite" would be a false conclusion. Set `PYTHONDONTWRITEBYTECODE=1` for every run below, or clear `cli/engine/__pycache__` before each.

1. Internal identity: change `third = 1 / 3` to `1 / 2`, re-run `decompose` over one day-dir, confirm it raises `stage identity broken`. `git checkout --` to restore.
2. Journal identity: perturb the rebuilt `final` (e.g. `final[a] * 1.0000001` before the journal comparison), re-run, confirm it raises `replay disagrees with the journal`. Restore.
3. Re-run clean, confirm no raise, and `git status --porcelain` empty.

Report the actual error lines seen, and which guard produced each — a red exit is not evidence until you have read *which* failure fired.

---

### Task 5: Closeout

**Files:**
- Modify: `docs/open-topics/T0117-…md`, `docs/open-topics/T0118-…md` → `archive/` (via `git mv`), `docs/open-topics/README.md`, `docs/iterations-history-phase6.md`

- [ ] **Step 1: Record the answers in both topics, then resolve them** (load the `topic-ops` skill)

Each gets a `## Resolution` naming spec `00081`, the commits, and **the measured numbers themselves** — the attribution table's medians and which stage loses the gross for T0117; the weekly drift floor per NAV for T0118, with the `fetched_at` stamp of the minimums used. Flip `status: resolved`, delete `ripe_when` if present, `git mv` to `archive/`, move both index bullets to `### Resolved` with archived links.

**If the measurement does not settle T0117's question** (spec Risks), say so plainly in the Resolution and register what remains — do not force the residual to zero.

- [ ] **Step 2: Hand the parameters to T0116**

Add to `T0116`'s `## Findings so far`: the measured expected gross for rungs 2–3, and the measured band with its NAV curve. This is the feeder hand-off the whole iteration exists for.

Also carry the **re-derivation trigger** into T0116 rather than leaving it in spec prose: the band is derived from *shadow* targets, so if rung 1/2 execution changes the target series materially, the band wants re-deriving before rung 3's gate reads it. T0116 is its durable home — a caveat living only in a spec is one nobody executing will read.

- [ ] **Step 3: Changelog entry** — `docs/iterations-history-phase6.md`, matching the file's existing format; one bullet per landed piece plus the measurement answers.

- [ ] **Step 4: Gate and commit**

```bash
uv run pre-commit run -a
git add docs/open-topics/archive/T0117-*.md docs/open-topics/archive/T0118-*.md docs/open-topics/T0116-*.md docs/open-topics/README.md docs/iterations-history-phase6.md
git commit -m "docs(ops): iter closeout -- the two 6b feeder measurements answered (spec 00081)"
```

- [ ] **Step 5: Memo (ORCHESTRATOR ONLY — main loop, Edit/Write tools, never staged: gitignored)**

Move the T0117 and T0118 queue items to `DONE ITEMS` with their measured answers; note in the owning queue group that T0116's parameters are now supplied.
