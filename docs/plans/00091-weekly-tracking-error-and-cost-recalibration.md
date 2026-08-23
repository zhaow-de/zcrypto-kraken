# Weekly tracking-error report and cost recalibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the three obligations T0018 registers to serial `00091` — (A) `zcrypto engine tracking-report`, the read-only weekly instrument rung 3's go/no-go reads; (B) the standing reader for the owner's Kraken ledger export; (C) the tracking-error kill-switch trip, engine code on the live trade path.

**Architecture:** A new pure module `cli/engine/tracking.py` holds the arithmetic and refusals for A and B; `cli/engine/command.py` gains Typer wiring; `cli/engine/cycle.py` journals the closes each cycle used; `cli/engine/executor.py` gains C's trip. The floor half is not re-derived — it calls the validated `accumulation_payload`.

**Tech Stack:** Python 3.14, Typer, pytest. No new dependencies.

## The three components do not ship alike

| | what it is | risk tier | review floor | how it reaches production |
| --- | --- | --- | --- | --- |
| **A** | `tracking-report`, read-only, workstation-only | none — reads a pulled journal | Opus | nothing to deploy |
| **B** | Kraken ledger-export reader, read-only over a file the owner exports | none — no credential, no venue call | Opus | nothing to deploy |
| **C** | the trip, plus the cycle record's `closes` widening it needs | **live trade path** | **Fable** (`spec-plan-locations.md`) | canary-gated converge, `--tags capture,engine`, readers before writer |

**Tasks 1–5 are A and B. Tasks 6–7 are C and are the only tasks touching code that runs with real money** — their review floor is Fable, not Opus.

## Global Constraints

- **A and B write nothing anywhere.** `fee_per_side` is PROPOSED, never applied (spec D4).
- **Reuse, do not re-derive.** `accumulation_payload`, `feeders._p95`, `feeders._median`, `feeders._weekly_drift`, `feeders._CYCLES_PER_FULL_WEEK` are imported, never reimplemented — a second percentile or week boundary lets the two halves disagree while both look right.
- **`held` accumulates SIGNED base quantity** — `+qty` on a `buy`, `−qty` on a `sell`, side read from `intent["side"]` (spec D3). Base units, never EUR. Never `zcrypto_exec_position`, never the venue record.
- **A fill is attributed to the boundary its submitted row was journaled under**, never by comparing its wall-clock stamp to a boundary (spec D3, post-decision attribution).
- **The two `/BTC` legs are EXCLUDED from the drift half, and counted in the output.** `cycle._MODEL_SYMBOLS = tuple(s for s in BASKET if s.endswith("/EUR"))`, so `select_model_inputs` DROPS `ETH/BTC` and `SOL/BTC`; the model's targets are ten EUR bases, and folding a `/BTC` fill into `held["ETH"]` inflates held against a target that never included it.
- **One key space per run.** Floors and targets are keyed by **base** (`"BTC"`); a journaled intent's `symbol` is a **pair** (`"BTC/EUR"`). Map pair → base once, at the reader's edge.
- **A `reconciled` repair is real position change and MUST reach `held`.** `executor._reconcile_adopted_rows` journals `{"event": "reconciled", "qty": delta, "venue_filled_qty": …}` with `add_filled_qty=delta` — base quantity that filled at the venue while this process was down. It is not a fill (no `px`, no fee, deliberately) but it moves the position, so skipping it makes `held` under-report by exactly the repaired amount, silently, in a module whose contract is that a number nobody can stand behind is worse than none. It becomes a `Fill` with `px=None` and `fee=None`, signed by the row's `intent["side"]` like any other, and a note records it. **`px` is therefore `float | None`**, and anything computing notional skips px-less fills.
- **`liquidity` is stored UPPERCASE** — `executor._liquidity` writes `"MAKER"` / `"TAKER"` / `"NO_LIQUIDITY_SIDE"` because `str()` on the pinned `LiquiditySide` `IntFlag` yields `"1"`. Match the stored casing: a lowercase-only match aborts every real fill while every lowercase fixture passes.
- **`NO_LIQUIDITY_SIDE` is counted but unpriced, never an abort** (spec D5). Only a value the enum cannot name at all — `"1"` — aborts.
- **The euro has two spellings**: `("EUR", "ZEUR")`. Never test `== "EUR"`.
- **Partial ISO weeks carry no verdict**, and are marked. The gate needs ≥3 complete weeks. **Rung-2 weeks are measured but not gate-eligible.**
- **"No data" means the realized series never started** — never "this week was quiet" (spec D10).
- **A week STRADDLING the first fill is measured but not gate-eligible**, for the same reason a partial week is not: its mean is not comparable to a full week's. Measured on a 42-cycle week whose first fill lands at cycle 21, the twenty pre-fill cycles each contribute the full 10000 bps and the week reads 4761.9 bps — so the FIRST week of live trading would be systematically biased toward `fail`, in exactly the go/no-go window this report exists for. Report the number, exclude it from the verdict.
- **A degenerate fixture proves nothing about a comparison.** Any fixture where the floor and the realized side are both exactly 0.0 leaves `<=` vs `>=` unpinned — the single arithmetic the gate rests on. Every band comparison needs a fixture where the two sides DIFFER, and the suite needs a case that reaches the `fail` verdict.
- Every command flag documented in `README.md` `## Usage` in the same change (`readme-usage.md`).
- Loggers are `get_logger("engine.tracking")` from `cli.logging` (a package — there is no `cli.logging_setup`). Match `cli/engine/feeders.py`'s docstring register: state WHY, name the failure the code prevents.
- **No internal traceability vocabulary on operator-visible surfaces** (`operator-facing-text.md`); `tests/test_internal_terms_not_operator_visible.py` enforces it.
- **Findings discovered mid-implementation are resolved in this branch** — fold them onto the surface that owns them, or drop them with the reasoning written down. Do not open a new `T<NNNN>` topic.

## The input does not exist yet — measured, not assumed

`/mnt/zhao-crypto/engine-journal` holds **64 exec records spanning 2026-08-12T08:00 → 2026-08-22T20:00, every one `level: "none"`, zero `submitted` rows, zero fills**, and **258 `cycle-*.json` artifacts** (read 2026-08-22, re-derived by an independent reviewer). Rung 1 is unfunded; the engine has never submitted an order.

1. Every unit test is fixture-based.
2. The only production-shaped input is `--simulated-fills`, and it is the D6 true-positive — without it every refusal below could be an always-refusing guard shipping green.
3. Component C's guard is proven by CONSTRUCTED defect, both directions, plus a proven call site.

## File structure

| file | responsibility |
| --- | --- |
| `cli/engine/instruments.py` (modify) | gains `EUR_CODES` — the shared leaf both `executor` and `tracking` import (breaks the cycle). |
| `cli/engine/tracking.py` (new) | pure: fill extraction, realized drift, ISO-week aggregation, cost blend, ledger reconciliation. |
| `cli/engine/command.py` (modify) | `tracking-report` Typer command. |
| `cli/engine/cycle.py` (modify) | journals the closes each cycle used (spec D9). |
| `cli/engine/config.py` → `cli/config.py` (modify) | the parsed `tracking_band_bps` key. |
| `cli/engine/executor.py` (modify) | component C's trip and its call site. |
| `tests/test_engine_tracking.py` (new) | every arm and refusal, plus the true-positive. |
| `tests/test_engine_executor.py`, `tests/test_engine_cycle.py`, `tests/test_config.py` (modify) | C's constructed defect, the widening, the knob. |

## Interfaces this plan consumes (read from the repo 2026-08-22, use verbatim)

- `feeders.accumulation_payload(stages, minimums, navs) -> dict` — `{"by_nav": {nav: {"cycles": [{"cycle_ts", "drift_bps", "drift_eur", "placed", "target_qty"}], "median_drift_bps", "p95_drift_bps", "n_placed", "weeks"}}}`. **Base-keyed.**
- `feeders._weekly_drift(stages, rows) -> [{"iso_year", "iso_week", "n_cycles", "mean_drift_bps", "partial"}]`
- `feeders._p95(values) -> float` (nearest rank, observed value; NaN on empty), `feeders._median`, `feeders._CYCLES_PER_FULL_WEEK = 42`
- `feeders.load_minimums(path) -> tuple[dict[str, tuple[float, float]], str]` — **base-keyed**, EUR-quoted pairs only.
- `feeders.replay_stages(record, reader, *, config=None) -> CycleStages` — `.cycle_ts`, `.final`, `.closes`.
- `command._window_records`, `command._resolve_minimums`, `command._snapshot_reader`, `command._emit_report`
- **`command._emit_report(text, payload, *, as_json)` reads `payload["n_failed"]` and raises `typer.Exit(1)` when truthy** — the payload MUST carry that key or every invocation is a `KeyError`.
- `command.accum_replay`'s flags are `--journal-dir` and a **repeatable** `--nav` — match them.
- Exec record: `{"schema_version", "cycle_ts", "evaluated_at", "level", "reasons", "inputs", "plans", "submitted"}`; `inputs` carries only gate inputs (`arm_file`, `armed_in_config`, `kill_file`, `restart_hold`, `venue_snapshot_age_seconds`, `venue_status`) — **no prices**.
- Cycle artifact: `{"builder_path", "code_version", "completed_at", "cycle_ts", "final_targets", "schema_version", "snapshots", "started_at"}` — `final_targets` is **pair-keyed weights**; there are **no closes** (which is what Task 6 adds).
- `execledger._ROW_KEYS = {plan_id, intent_index, client_order_id, intent, order, state, filled_qty, events}`
- `row["intent"]` keys (`probeplan._INTENT_KEYS`): `{symbol, side, action, mode, notional_eur, qty, leverage}` — **no `asset`**.
- Fill event (`executor._fill_payload`): `{"event": "fill", "at", "qty", "px", "fee", "fee_currency", "liquidity", "trade_id"}`
- `executor._trip_kill(reason)` — idempotent via `self._kill_tripped`; writes the kill file, cancels resting orders, halts the plan, republishes the gate.
- `cli.engine.store.BASKET` — a **tuple** of twelve pair strings; `cycle._MODEL_SYMBOLS` is the ten `/EUR` ones.
- `cli/portfolio/crossfreq_system.py`: `CrossfreqSystemConfig.fee_per_side = 0.0040`, `spread_per_side = 0.0020`, `cost_per_side` = their sum; `builder.spot_fee_per_side` is fed that SUM under a `# DO NOT "correct" this` comment.

---

### Task 1: The shared euro constant, and the fill reader

**Files:**
- Modify: `cli/engine/instruments.py`, `cli/engine/executor.py`
- Create: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Why the constant moves first.** `tracking.py` needs the euro spellings and `executor.py` will import `tracking` in Task 7. `executor.py` has all imports at module top and defines `_EUR_CODES` at line 109, so a direct `from cli.engine.executor import _EUR_CODES` is a hard circular import — `ImportError: cannot import name … from partially initialized module`, at engine start, on the live trade path. `instruments.py` is already a shared leaf (it imports only `store`, and `executor.py` line 47 already imports from it), and venue-spelling constants are exactly what it holds. **Do not** paper this over with a function-local import inside the executor: a deferred import on the trade path converts a start-time failure into a first-trip failure.

**Interfaces:**
- Produces: `instruments.EUR_CODES = ("EUR", "ZEUR")`; `tracking.Fill` (NamedTuple: `boundary: datetime`, `at: datetime`, `base: str | None`, `side: str`, `qty: float`, `px: float | None`, `fee: float | None`, `liquidity: str`, `trade_id: str`) and `tracking.extract_fills(records) -> tuple[list[Fill], list[str]]`.

- [ ] **Step 1: Move the constant.** Add `EUR_CODES = ("EUR", "ZEUR")` to `cli/engine/instruments.py` with the existing comment about Kraken's two spellings; in `cli/engine/executor.py` import it (`from cli.engine.instruments import EUR_CODES, INSTRUMENT_IDS, …`), delete the local definition, and update both use sites — `_fee_eur`, and the realized-PnL loop over `position.realized_pnl` (NOT the fill-payload path: `_fill_payload` reaches the codes only indirectly, through `_fee_eur`). Grep for the exact count before and after. Run `uv run pytest tests/test_engine_executor.py -q` — it must stay green; this is a pure move.

- [ ] **Step 2: Write the failing tests.**

```python
from datetime import UTC, datetime

import pytest

from cli.engine.errors import EngineError
from cli.engine.tracking import extract_fills

_BOUNDARY = "2026-09-01T00:00:00+00:00"

def _rec(events, *, symbol="BTC/EUR", side="buy", cycle_ts=_BOUNDARY):
    return {"schema_version": 2, "cycle_ts": cycle_ts,
            "evaluated_at": cycle_ts, "level": "full", "reasons": [],
            "inputs": {}, "plans": [],
            "submitted": [{"plan_id": "p1", "intent_index": 0, "client_order_id": "O-1",
                           "intent": {"symbol": symbol, "side": side, "action": "open",
                                      "mode": "spot", "notional_eur": 50.0, "qty": None,
                                      "leverage": None},
                           "order": {"qty": 0.001}, "state": "filled", "filled_qty": 0.001,
                           "events": events}]}

def _fill(**kw):
    base = {"event": "fill", "at": "2026-09-01T00:01:00+00:00", "qty": 0.001, "px": 50000.0,
            "fee": 0.05, "fee_currency": "EUR", "liquidity": "MAKER", "trade_id": "T-1"}
    base.update(kw)
    return base

def test_reads_the_venues_own_uppercase_liquidity_and_the_rows_boundary():
    fills, notes = extract_fills([_rec([_fill()])])
    assert notes == []
    f = fills[0]
    assert (f.base, f.side, f.qty, f.px, f.fee, f.liquidity, f.trade_id) == (
        "BTC", "buy", 0.001, 50000.0, 0.05, "MAKER", "T-1")
    # Attribution is the ROW's boundary, not the fill's wall clock: a fill arriving after the
    # boundary belongs to the decision that produced it.
    assert f.boundary == datetime.fromisoformat(_BOUNDARY)
    assert f.at != f.boundary

def test_a_sell_is_carried_as_a_sell():
    fills, _ = extract_fills([_rec([_fill()], side="sell")])
    assert fills[0].side == "sell"

def test_lowercase_liquidity_is_refused_because_the_ledger_never_writes_it():
    with pytest.raises(EngineError, match="liquidity"):
        extract_fills([_rec([_fill(liquidity="maker")])])

def test_a_liquidity_the_enum_cannot_name_aborts():
    # `str()` on the pinned IntFlag yields "1" -- this repo shipped exactly that once.
    with pytest.raises(EngineError, match="liquidity"):
        extract_fills([_rec([_fill(liquidity="1")])])

def test_no_liquidity_side_is_counted_but_unpriced_and_never_aborts():
    fills, notes = extract_fills([_rec([_fill(liquidity="NO_LIQUIDITY_SIDE")])])
    assert len(fills) == 1 and fills[0].fee is None
    assert any("NO_LIQUIDITY_SIDE" in n for n in notes)

def test_zeur_is_a_euro():
    fills, notes = extract_fills([_rec([_fill(fee_currency="ZEUR")])])
    assert notes == [] and fills[0].fee == 0.05

def test_a_btc_denominated_fee_disables_pricing_without_aborting():
    fills, notes = extract_fills([_rec([_fill(fee_currency="XXBT")], symbol="ETH/BTC")])
    assert len(fills) == 1 and fills[0].fee is None
    assert any("XXBT" in n for n in notes)

def test_the_btc_quoted_legs_are_excluded_from_the_drift_half_and_counted():
    # select_model_inputs DROPS ETH/BTC and SOL/BTC, so the model's targets are ten EUR bases.
    # Folding such a fill into held["ETH"] would inflate held against a target that never had it.
    fills, notes = extract_fills([_rec([_fill()], symbol="ETH/BTC")])
    assert fills[0].base is None
    assert any("ETH/BTC" in n for n in notes)

def test_a_symbol_outside_the_basket_aborts():
    with pytest.raises(EngineError, match="basket"):
        extract_fills([_rec([_fill()], symbol="PEPE/EUR")])

def test_a_side_outside_buy_sell_aborts():
    with pytest.raises(EngineError, match="side"):
        extract_fills([_rec([_fill()], side="flat")])
```

- [ ] **Step 3: Run and read WHICH assertion fails.** Expected: `ModuleNotFoundError: No module named 'cli.engine.tracking'`.

- [ ] **Step 4: Implement.**

```python
"""The realized half of the weekly tracking comparison: what the ledger says actually happened.

Pure. Reads a journal already on disk and returns numbers; writes nothing, reaches no venue. The
refusals are the point -- a tracking number nobody can stand behind is worse than none, because it
will be read as a gate input.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from cli.engine.errors import EngineError
from cli.engine.instruments import EUR_CODES
from cli.engine.store import BASKET
from cli.logging import get_logger

logger = get_logger("engine.tracking")

# The venue's own names, as `executor._liquidity` writes them. NOT lowercased: matching a casing
# the ledger never writes would abort every real fill while every fixture passed.
_PRICEABLE_LIQUIDITY = frozenset({"MAKER", "TAKER"})
_VENUE_LIQUIDITY = _PRICEABLE_LIQUIDITY | {"NO_LIQUIDITY_SIDE"}
_SIDES = frozenset({"buy", "sell"})
# The MODEL's universe is the ten EUR legs (cycle._MODEL_SYMBOLS). The two /BTC legs are real
# basket symbols with no model target, so they map to base None: excluded from drift, counted.
_BASE_BY_SYMBOL = {s: (s.split("/")[0] if s.endswith("/EUR") else None) for s in BASKET}


class Fill(NamedTuple):
    boundary: datetime   # the cycle whose decision produced it -- NOT the wall clock
    at: datetime
    base: str | None     # None for the /BTC legs, which carry no model target
    side: str
    qty: float
    px: float
    fee: float | None    # None when not euro-denominated or the side is unpriceable
    liquidity: str
    trade_id: str


def extract_fills(records: list[dict]) -> tuple[list[Fill], list[str]]:
    """Every journaled fill, in ledger order, plus the notes that disabled part of the report."""
    out: list[Fill] = []
    notes: list[str] = []

    def note(text: str) -> None:
        if text not in notes:
            notes.append(text)
            logger.warning("%s", text)

    for rec in records:
        boundary = datetime.fromisoformat(rec["cycle_ts"])
        for row in rec.get("submitted", []):
            intent = row.get("intent") or {}
            symbol = intent.get("symbol")
            if symbol not in _BASE_BY_SYMBOL:
                raise EngineError(
                    f"submitted row {row.get('client_order_id')!r} names symbol {symbol!r}, "
                    "which is not in the basket -- refusing to map it to a floor"
                )
            side = intent.get("side")
            if side not in _SIDES:
                raise EngineError(
                    f"submitted row {row.get('client_order_id')!r} carries side {side!r}, not one "
                    f"of {sorted(_SIDES)} -- an unsigned quantity would book a sell as a buy"
                )
            base = _BASE_BY_SYMBOL[symbol]
            if base is None:
                note(f"{symbol} has no model target and is excluded from the drift half")
            for ev in row.get("events", []):
                if ev.get("event") != "fill":
                    continue
                liq = ev.get("liquidity")
                if liq not in _VENUE_LIQUIDITY:
                    raise EngineError(
                        f"fill on {row.get('client_order_id')!r} carries liquidity={liq!r}, which "
                        f"is not a name the venue's enum yields -- refusing to blend an unlabelled side"
                    )
                cur = ev.get("fee_currency")
                fee: float | None = float(ev["fee"])
                if cur not in EUR_CODES:
                    fee = None
                    note(f"fee on {symbol} is denominated in {cur}, not euro -- excluded from the cost blend")
                if liq not in _PRICEABLE_LIQUIDITY:
                    fee = None
                    note(f"a fill on {symbol} carries {liq} -- counted, but excluded from the cost blend")
                out.append(Fill(boundary, datetime.fromisoformat(ev["at"]), base, side,
                                float(ev["qty"]), float(ev["px"]), fee, liq, str(ev["trade_id"])))
    return out, notes
```

- [ ] **Step 5: Run to green.** → 10 passed.

- [ ] **Step 6: Prove each refusal bites, reading WHICH assertion fires.** Via `infra/scripts/mutate-probe.sh`, one at a time (`--collect-only` first to confirm the tests are selected): lowercase `_PRICEABLE_LIQUIDITY` → the uppercase test fails; admit any string as liquidity → both liquidity tests fail; drop the `side` arm → the side test fails; map `/BTC` legs to their base → the exclusion test fails; replace `EUR_CODES` with `("EUR",)` → the ZEUR test fails; attribute by `ev["at"]` instead of the row's boundary → the boundary test fails.

- [ ] **Step 7: Commit.** `git add cli/engine/instruments.py cli/engine/executor.py cli/engine/tracking.py tests/test_engine_tracking.py && git commit` — `feat(engine): the tracking report's fill reader, signed and attributed to its boundary`

---

### Task 2: Realized drift, ISO weeks, and the rung boundary

**Files:**
- Modify: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Produces:
  - `drift_bps(final, closes, held, nav) -> float` — **the shared core both components call.** Plain dicts only: no `CycleStages`, no minimums, no `accumulation_payload`, because component C runs where none of those exist.
  - `realized_drift(stages, fills, nav) -> dict` — `{"cycles": [{"cycle_ts", "drift_bps", "drift_eur"}], "median_drift_bps", "p95_drift_bps", "n_fills"}`. **This is NOT `accumulation_payload`'s block shape** — it has no `placed`/`target_qty`/`n_placed`, because the realized side has no placement decision to record. Do not claim otherwise.
  - `weekly_tracking(stages, fills, minimums, nav, *, rung_by_week=None) -> dict` — `{"weeks": [{"iso_week": "2026-W36", "cycles", "complete", "rung", "gate_eligible", "floor_p95_bps", "realized_mean_bps", "within_band"}], "complete_gate_eligible_weeks", "verdict"}`.

**The quantity, stated before the code.** NAV is held constant by design, so a base-keyed **target** moves inversely with price while base-keyed **held** does not. The floor half absorbs that by re-placing every cycle; the realized half absorbs it only when the engine actually places. **An engine that keeps trading tracks the target; one that stops accumulates drift without bound — and that is the divergence being measured, not an artifact to correct away.** An earlier draft asserted a price move "re-prices target and held together" and wrote tests around it; the arithmetic below is what actually happens.

- [ ] **Step 1: Write the failing tests.**

```python
from cli.engine.feeders import CycleStages
from cli.engine.tracking import Fill, realized_drift, weekly_tracking

_MINIMUMS = {"BTC": (0.00005, 0.45)}

def _stage(ts, *, weight=1.0, close=50000.0):
    # CycleStages is a frozen dataclass with EIGHT required fields and no defaults; supplying
    # three raises TypeError at construction, before any assertion is reached.
    return CycleStages(cycle_ts=datetime.fromisoformat(ts), sleeve_positions={}, combined={},
                       capped={}, final={"BTC": weight}, multiplier=1.0,
                       closes={"BTC": close}, cap_bound=False)

def _mk(boundary, qty, side="buy", px=50000.0):
    b = datetime.fromisoformat(boundary)
    return Fill(b, b, "BTC", side, qty, px, 0.05, "MAKER", f"T-{boundary}-{side}")

def test_a_fill_matching_the_target_leaves_zero_drift():
    # NAV 1000 at 50k -> target 0.02 BTC.
    out = realized_drift([_stage("2026-08-31T00:00:00+00:00")],
                         [_mk("2026-08-31T00:00:00+00:00", 0.02)], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(0.0)

def test_a_price_move_moves_realized_drift_and_that_is_the_signal():
    # Held 0.02 BTC, close 50k -> 60k, NAV pinned at 1000: target falls to 0.016667 while held
    # stays put -> 0.003333 BTC * 60000 = 200 EUR = 2000 bps. An engine that kept placing would
    # have re-placed; one that stopped accumulates exactly this. It is the measurement, not a bug.
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00", close=60000.0)]
    out = realized_drift(stages, [_mk("2026-08-31T00:00:00+00:00", 0.02)], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(0.0)
    assert out["cycles"][1]["drift_bps"] == pytest.approx(2000.0)

def test_a_sell_reduces_held_and_a_round_trip_returns_it_to_zero():
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00")]
    fills = [_mk("2026-08-31T00:00:00+00:00", 0.02),
             _mk("2026-08-31T04:00:00+00:00", 0.02, side="sell")]
    out = realized_drift(stages, fills, 1000.0)
    # held back to 0 against a 0.02 target -> the whole NAV undeployed -> 10000 bps.
    assert out["cycles"][1]["drift_bps"] == pytest.approx(10000.0)

def test_a_fill_is_attributed_to_its_own_boundary_not_a_later_one():
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00")]
    out = realized_drift(stages, [_mk("2026-08-31T04:00:00+00:00", 0.02)], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(10000.0)  # nothing held yet
    assert out["cycles"][1]["drift_bps"] == pytest.approx(0.0)

def test_a_fill_whose_boundary_has_no_cycle_is_refused_not_dropped():
    # Dropping it would overstate drift for every later cycle with no note and no refusal.
    with pytest.raises(EngineError, match="match no cycle"):
        realized_drift([_stage("2026-08-31T00:00:00+00:00")],
                       [_mk("2026-08-31T04:00:00+00:00", 0.02)], 1000.0)

def test_a_fill_on_a_btc_quoted_leg_is_skipped_rather_than_inflating_a_base():
    b = datetime.fromisoformat("2026-08-31T00:00:00+00:00")
    excluded = Fill(b, b, None, "buy", 5.0, 3000.0, None, "MAKER", "T-X")
    out = realized_drift([_stage("2026-08-31T00:00:00+00:00")], [excluded], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(10000.0)

def test_a_partial_iso_week_is_marked_and_carries_no_verdict():
    out = weekly_tracking([_stage("2026-08-31T00:00:00+00:00")], [], _MINIMUMS, 1000.0)
    wk = out["weeks"][0]
    assert (wk["iso_week"], wk["complete"], wk["within_band"]) == ("2026-W36", False, None)
    assert out["verdict"] == "insufficient-data"

def test_no_data_means_the_series_never_started_not_a_quiet_week():
    # THE BLOCKER THIS PINS: an engine that stops placing is maximal tracking error, and is
    # exactly what a tracking-error trip exists to catch. A quiet week must carry a NUMBER.
    stages = ([_stage(f"2026-08-31T{h:02d}:00:00+00:00") for h in (0, 4, 8, 12, 16, 20)]
              + [_stage(f"2026-09-07T{h:02d}:00:00+00:00") for h in (0, 4, 8, 12, 16, 20)])
    out = weekly_tracking(stages, [_mk("2026-08-31T00:00:00+00:00", 0.02)], _MINIMUMS, 1000.0)
    weeks = {w["iso_week"]: w for w in out["weeks"]}
    assert weeks["2026-W36"]["realized_mean_bps"] is not None
    assert weeks["2026-W37"]["realized_mean_bps"] is not None, "a quiet week is not 'no data'"

def test_before_any_fill_the_series_has_not_started():
    out = weekly_tracking([_stage("2026-08-31T00:00:00+00:00")], [], _MINIMUMS, 1000.0)
    assert out["weeks"][0]["realized_mean_bps"] is None

def _full_week(monday="2026-08-31", **kw):
    # 42 stages = 6 boundaries x 7 days, so `partial` is False and the rung rule is the ONLY
    # thing that can make the week ineligible. A one-stage week is partial and would pass this
    # test with the rung rule deleted.
    day = date.fromisoformat(monday)
    return [_stage(f"{day + timedelta(days=d)}T{h:02d}:00:00+00:00", **kw)
            for d in range(7) for h in (0, 4, 8, 12, 16, 20)]

def _tracking_fills(stages, nav=1000.0):
    # A fill at every boundary that exactly meets that cycle's target -> realized drift 0.
    out = []
    for st in stages:
        held = (nav * st.final["BTC"]) / st.closes["BTC"]
        prev = sum(f.qty if f.side == "buy" else -f.qty for f in out)
        delta = held - prev
        if delta:
            out.append(Fill(st.cycle_ts, st.cycle_ts, "BTC", "buy" if delta > 0 else "sell",
                            abs(delta), st.closes["BTC"], 0.05, "MAKER", f"T-{st.cycle_ts}"))
    return out

def test_a_fill_whose_at_is_skewed_past_the_next_boundary_still_counts_at_its_own():
    # Every other fixture sets at == boundary, which makes the "attribute by wall clock"
    # mutation unobservable. This skew IS the defect being guarded.
    b = datetime.fromisoformat("2026-08-31T00:00:00+00:00")
    late = Fill(b, datetime.fromisoformat("2026-08-31T05:30:00+00:00"), "BTC", "buy",
                0.02, 50000.0, 0.05, "MAKER", "T-late")
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00")]
    out = realized_drift(stages, [late], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(0.0)

def test_three_complete_weeks_within_band_read_pass():
    # The only test that reaches a `pass` verdict -- without it the _GATE_MIN_WEEKS probe has
    # nothing to fail against, since every other fixture yields insufficient-data either way.
    stages = _full_week("2026-08-31") + _full_week("2026-09-07") + _full_week("2026-09-14")
    out = weekly_tracking(stages, _tracking_fills(stages), _MINIMUMS, 1000.0)
    assert out["complete_gate_eligible_weeks"] == 3
    assert out["verdict"] == "pass"

def test_a_rung_2_week_is_measured_but_not_gate_eligible():
    # Given a FILL, so the exclusion is what makes it ineligible -- without one this test would
    # pass with the rung-2 rule entirely removed.
    stages = _full_week("2026-08-31")
    out = weekly_tracking(stages, _tracking_fills(stages), _MINIMUMS, 1000.0,
                          rung_by_week={"2026-W36": 2})
    wk = out["weeks"][0]
    assert wk["complete"] is True, "a partial week would be ineligible whatever the rung rule"
    assert wk["rung"] == 2 and wk["gate_eligible"] is False
    assert wk["floor_p95_bps"] is not None
    assert out["complete_gate_eligible_weeks"] == 0
```

- [ ] **Step 2: Run and read WHICH assertion fails.** The thirteen new tests fail on `ImportError`; Task 1's ten still pass.

- [ ] **Step 3: Implement.** Add to the module header: `import math`, `from cli.engine.feeders import CycleStages, _median, _p95, _weekly_drift, accumulation_payload`. Import `_median` — the floor half uses it and it drops NaN, so `statistics.median` here would be a second convention. Do **not** import `_CYCLES_PER_FULL_WEEK`: completeness reaches this code only through `_weekly_drift`'s `partial` flag, so it has exactly one definition and a direct import would be unused (`ruff.toml` selects `I` only, so nothing in the gate would catch it).

```python
def _iso_key(dt: datetime) -> tuple[int, int]:
    iso = dt.isocalendar()
    return (iso.year, iso.week)


def _iso_label(key: tuple[int, int]) -> str:
    return f"{key[0]}-W{key[1]:02d}"


def drift_bps(final: dict[str, float], closes: dict[str, float],
              held: dict[str, float], nav: float) -> float:
    """One cycle's drift, in bps of NAV, from plain dicts.

    THE shared core: component A calls it from replayed stages, component C from journaled
    artifacts. No CycleStages, no venue minimums, no accumulation_payload -- component C runs on
    the engine host, which carries no refdata snapshot, so anything needing `load_minimums` cannot
    run there at all. One implementation, two callers: the number a human bands and the number the
    engine trips on cannot drift apart.
    """
    drift_eur = 0.0
    for a, weight in final.items():
        close = closes[a]
        drift_eur += abs((weight * nav) / close - held.get(a, 0.0)) * close
    return drift_eur / nav * 10_000


def realized_drift(stages: list[CycleStages], fills: list[Fill], nav: float) -> dict:
    """Per-cycle drift with `held` taken from REAL fills instead of the modelled policy.

    `held` is SIGNED BASE UNITS: a sell that booked as a buy would double the apparent position
    and silently halve the measured drift. Fills are applied by the BOUNDARY their row was
    journaled under, so a fill arriving minutes after boundary N counts at N -- the decision that
    produced it -- rather than at N+1.
    """
    if not math.isfinite(nav) or nav <= 0:
        raise EngineError(f"NAV must be finite and positive, got {nav!r} -- a negative one signs every drift_bps")
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    by_boundary: dict[datetime, list[Fill]] = {}
    for f in fills:
        if f.base is None:      # a /BTC leg: no model target, so no drift contribution
            continue
        by_boundary.setdefault(f.boundary, []).append(f)
    # A fill whose boundary journaled no cycle artifact (a failed cycle writes only a sidecar) or
    # that falls outside the window would never enter `held`, overstating drift for every later
    # cycle -- silently, and on component C that is a spurious kill-file trip.
    orphans = sorted({b.isoformat() for b in by_boundary} - {s.cycle_ts.isoformat() for s in ordered})
    if orphans:
        raise EngineError(
            f"{len(orphans)} fill boundary(ies) match no cycle in the window ({orphans[:3]}...) -- "
            "refusing to report a drift that silently omits their position"
        )
    held: dict[str, float] = {}
    rows: list[dict] = []
    for s in ordered:
        for f in by_boundary.get(s.cycle_ts, []):
            held[f.base] = held.get(f.base, 0.0) + (f.qty if f.side == "buy" else -f.qty)
        bps = drift_bps(s.final, s.closes, held, nav)
        rows.append({"cycle_ts": s.cycle_ts.isoformat(), "drift_bps": bps,
                     "drift_eur": bps / 10_000 * nav})
    values = [r["drift_bps"] for r in rows]
    return {"cycles": rows, "median_drift_bps": _median(values) if values else None,
            "p95_drift_bps": _p95(values) if values else None, "n_fills": len(fills)}


def weekly_tracking(stages, fills, minimums, nav, *, rung_by_week=None) -> dict:
    """That week's floor p95 against that week's realized MEAN drift.

    The edge is ratified, not chosen here: on the data the band was derived from a median edge
    fails two of four weeks while a p95 edge passes all four.

    "No data" means the realized series NEVER STARTED -- not that a week was quiet. A week with
    no fills but a non-zero `held` is fully measured, and is precisely the week a tracking-error
    trip exists to catch.
    """
    rung_by_week = rung_by_week or {}
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    floor = accumulation_payload(ordered, minimums, [nav])["by_nav"][nav]
    real = realized_drift(ordered, fills, nav)
    floor_weeks = {(w["iso_year"], w["iso_week"]): w for w in _weekly_drift(ordered, floor["cycles"])}
    real_weeks = {(w["iso_year"], w["iso_week"]): w for w in _weekly_drift(ordered, real["cycles"])}
    floor_cycles: dict[tuple[int, int], list[float]] = {}
    for stage, row in zip(ordered, floor["cycles"], strict=True):
        floor_cycles.setdefault(_iso_key(stage.cycle_ts), []).append(row["drift_bps"])
    first_fill = min((f.boundary for f in fills if f.base is not None), default=None)

    weeks: list[dict] = []
    for key, fw in sorted(floor_weeks.items()):
        label = _iso_label(key)
        complete = not fw["partial"]
        rung = rung_by_week.get(label)
        gate_eligible = complete and rung != 2
        # Started, not "had a fill this week".
        started = first_fill is not None and any(
            s.cycle_ts >= first_fill for s in ordered if _iso_key(s.cycle_ts) == key)
        realized_mean = real_weeks[key]["mean_drift_bps"] if started else None
        floor_p95 = _p95(floor_cycles[key])
        weeks.append({"iso_week": label, "cycles": fw["n_cycles"], "complete": complete,
                      "rung": rung, "gate_eligible": gate_eligible, "floor_p95_bps": floor_p95,
                      "realized_mean_bps": realized_mean,
                      "within_band": (realized_mean <= floor_p95)
                      if (gate_eligible and realized_mean is not None) else None})
    decided = [w for w in weeks if w["within_band"] is not None]
    verdict = ("insufficient-data" if len(decided) < _GATE_MIN_WEEKS
               else "pass" if all(w["within_band"] for w in decided) else "fail")
    return {"weeks": weeks, "complete_gate_eligible_weeks": len(decided), "verdict": verdict}
```

with `_GATE_MIN_WEEKS = 3` beside the other module constants.

- [ ] **Step 4: Run to green.** → 23 passed.

- [ ] **Step 5: Prove the arms bite, naming the assertion that must fire.** Three of these need a fixture built for them, or the mutation is unobservable — build the fixture first, then probe:

| mutation | test that must fail | why the fixture matters |
| --- | --- | --- |
| unsigned accumulation (`+ f.qty` always) | the round-trip test | — |
| apply fills by `f.at <= s.cycle_ts` | the attribution test | **needs a fill whose `at` falls past the next boundary** — every `_mk` fixture sets `at == boundary`, so the mutation is invisible against them. That skew IS the defect being guarded. |
| stop skipping `base is None` | the `/BTC` test | — |
| `started` → "has a fill this week" | the quiet-week test | — |
| `_GATE_MIN_WEEKS = 1` | a verdict test | **needs a three-complete-week fixture that must read `pass`** — in the partial-week test `decided == []`, so `0 < 1` still yields `insufficient-data` and the assertion holds either way. |
| drop `rung != 2` | the rung-2 test | **needs 42 stages inside one ISO week** — a one-stage fixture is `partial`, so `gate_eligible` is already False and the rung rule never runs. |
| drop the orphan-boundary refusal | the orphan test | — |

- [ ] **Step 6: Commit.** `feat(engine): realized weekly drift -- signed, boundary-attributed, quiet weeks measured`

---

### Task 3: The cost blend and its proposal

**Files:**
- Modify: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Produces: `cost_blend(fills: list[Fill]) -> dict` — `{"n_fills", "n_priced", "maker_share", "taker_share", "realized_fee_per_side", "per_fill_min", "per_fill_median", "per_fill_max", "current_fee_per_side", "current_spread_per_side", "proposed_fee_per_side", "basis"}`.

**It prices the FEE term only.** The constant is `cli/portfolio/crossfreq_system.py`'s `CrossfreqSystemConfig.fee_per_side = 0.0040`, imported — never a literal, and never `builder.spot_fee_per_side`, which is fed `cost_per_side` (`fee_per_side + spread_per_side = 0.0060`) at the builder seam under an explicit `# DO NOT "correct" this` comment. Proposing a realized fee-only rate against that sum would silently delete the `spread_per_side = 0.0020` term T0090's ruling exists to keep separate.

**It reports min/median/max per fill** — a spread, not a standard deviation: a handful of probe-scale fills cannot support a parametric dispersion, and quoting one would dress up a sample of tens (spec D4).

**It proposes; it never applies.** Nothing here writes `crossfreq_system.py`.

- [ ] **Step 1: Write the failing tests.**

```python
from cli.engine.tracking import cost_blend
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

def _cf(liquidity="MAKER", qty=1.0, px=100.0, fee=0.1, base="BTC"):
    b = datetime.fromisoformat("2026-08-31T00:00:00+00:00")
    return Fill(b, b, base, "buy", qty, px, fee, liquidity, "T-1")

def test_the_blend_is_share_of_NOTIONAL_not_a_count_of_fills():
    # One large taker fill beside nine tiny maker ones is a taker-heavy book; a count-weighted
    # blend would call it 90% maker and under-price the cost.
    out = cost_blend([_cf("TAKER", qty=100.0)] + [_cf("MAKER", qty=0.1) for _ in range(9)])
    assert out["taker_share"] > 0.98

def test_realized_fee_per_side_is_fees_over_priced_notional():
    out = cost_blend([_cf(qty=1.0, px=100.0, fee=0.25)])
    assert out["realized_fee_per_side"] == pytest.approx(0.0025)

def test_unpriced_fills_are_counted_but_excluded_from_the_rate():
    out = cost_blend([_cf(fee=0.1), _cf(fee=None)])
    assert (out["n_fills"], out["n_priced"]) == (2, 1)
    # The RATE is what the mutation moves: dividing by gross (200) instead of priced notional
    # (100) halves it, and a count-only assertion cannot see that.
    assert out["realized_fee_per_side"] == pytest.approx(0.001)

def test_no_priced_fills_proposes_nothing_rather_than_zero():
    out = cost_blend([_cf(fee=None)])
    assert out["realized_fee_per_side"] is None and out["proposed_fee_per_side"] is None
    assert "no euro-denominated fills" in out["basis"]

def test_it_prices_the_fee_term_and_leaves_the_spread_alone():
    out = cost_blend([_cf(qty=1.0, px=100.0, fee=0.25)])
    cfg = CrossfreqSystemConfig()
    assert out["current_fee_per_side"] == cfg.fee_per_side == 0.0040
    assert out["current_spread_per_side"] == cfg.spread_per_side == 0.0020
    assert out["proposed_fee_per_side"] == pytest.approx(0.0025)

def test_the_dispersion_is_a_spread_not_a_deviation():
    out = cost_blend([_cf(qty=1.0, px=100.0, fee=f) for f in (0.1, 0.2, 0.6)])
    assert (out["per_fill_min"], out["per_fill_median"], out["per_fill_max"]) == (
        pytest.approx(0.001), pytest.approx(0.002), pytest.approx(0.006))
    assert "std" not in out and "stdev" not in out
```

- [ ] **Step 2: Run and read WHICH assertion fails.** Expected: `ImportError` on `cost_blend`.

- [ ] **Step 3: Implement.** Add `from cli.portfolio.crossfreq_system import CrossfreqSystemConfig` to the module header — the code below constructs it, and only the test imported it before.

```python
def cost_blend(fills: list[Fill]) -> dict:
    """The realized maker/taker blend and the fee-per-side it implies.

    Weighted by NOTIONAL, never by fill count: one large taker fill beside nine tiny maker ones
    is a taker-heavy book, and a count-weighted blend would under-price the cost the whole
    portfolio is evaluated against.

    Unpriced fills are COUNTED but not PRICED -- leaving their notional in the denominator while
    dropping their fee from the numerator would silently deflate the rate. With nothing priced the
    answer is None: a proposal of 0.0 reads as "trading is free" to whoever ratifies it.

    Prices the FEE term only. `spread_per_side` is a separate, deliberately-kept term.
    """
    cfg = CrossfreqSystemConfig()
    # A repair has no price by construction, so it is neither priced nor notional -- multiplying
    # by its None px would raise, and counting it at zero would deflate the blend.
    priced = [f for f in fills if f.fee is not None and f.px is not None]
    notional: dict[str, float] = {}
    for f in fills:
        if f.px is None:
            continue
        notional[f.liquidity] = notional.get(f.liquidity, 0.0) + abs(f.qty) * f.px
    maker, taker = notional.get("MAKER", 0.0), notional.get("TAKER", 0.0)
    gross = maker + taker
    priced_notional = sum(abs(f.qty) * f.px for f in priced)  # every `priced` fill has a px
    per_fill = sorted(f.fee / (abs(f.qty) * f.px) for f in priced if f.qty and f.px)
    realized = (sum(f.fee for f in priced) / priced_notional) if priced_notional > 0 else None
    basis = (f"{len(priced)} euro-denominated fill(s) over {priced_notional:,.2f} EUR of notional"
             if realized is not None else
             "no euro-denominated fills in the window -- no rate proposed")
    return {
        "n_fills": len(fills), "n_priced": len(priced),
        "maker_share": (maker / gross) if gross > 0 else None,
        "taker_share": (taker / gross) if gross > 0 else None,
        "realized_fee_per_side": realized,
        "per_fill_min": per_fill[0] if per_fill else None,
        "per_fill_median": _median(per_fill) if per_fill else None,
        "per_fill_max": per_fill[-1] if per_fill else None,
        "current_fee_per_side": cfg.fee_per_side,
        "current_spread_per_side": cfg.spread_per_side,
        "proposed_fee_per_side": realized,
        "basis": basis,
    }
```

`notional` is built with `.get`, not a fixed two-key dict — `NO_LIQUIDITY_SIDE` is a legal value and a fixed dict would `KeyError` on it.

- [ ] **Step 4: Run to green.** → 29 passed.

- [ ] **Step 5: Prove the arms bite.** Weight by `len()` → the notional test fails; divide by `gross` instead of `priced_notional` → the unpriced test fails; return `0.0` when nothing is priced → the no-proposal test fails; read `builder.spot_fee_per_side` → the fee-term test fails.

- [ ] **Step 6: Commit.** `feat(engine): the realized maker/taker blend, pricing the fee term only`

---

### Task 4: The command, and the true-positive that proves it before rung 1

**Files:**
- Modify: `cli/engine/command.py`, `README.md`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Produces: `zcrypto engine tracking-report [--journal-dir PATH] [--since ISO] [--until ISO] [--nav FLOAT (repeatable)] [--minimums PATH] [--ledger-export PATH] [--simulated-fills] [--json]`.
- **Payload shape** (the tests assert these keys, so they are part of the interface, not an implementation detail):

```python
{
  "tracking": weekly_tracking(stages, fills, minimums, nav, rung_by_week=…),   # weeks, verdict
  "floor":    accumulation_payload(stages, minimums, [nav])["by_nav"][nav],    # window-wide p95
  "cost":     cost_blend(fills),
  "reconciliation": reconcile_ledger(...) or None,   # None when --ledger-export is absent
  "schema_versions": [1, 2],                          # the distinct versions in the window
  "simulated": bool,                                  # True under --simulated-fills
  "n_failed": int,                                    # records that failed to replay, plus a
                                                      # FAILED reconciliation -- `_emit_report`
                                                      # raises typer.Exit(1) when truthy
}
```

  `"floor"` is `accumulation_payload`'s per-NAV block **verbatim** — that block carries the window-wide `p95_drift_bps` comparable to `accum-replay`'s `by_nav["1000.0"]["p95_drift_bps"]`. `weekly_tracking`'s per-week `_p95` is a different quantity and will not match.

**Flags match the sibling `accum-replay` exactly** — `--journal-dir`, and `--nav` repeatable with the same default list. A near-miss flag name on a sibling command is a papercut the operator hits in the go/no-go window.

**The payload MUST carry `n_failed`.** `command._emit_report` reads `payload["n_failed"]` and raises `typer.Exit(1)` when truthy; without the key every invocation is a `KeyError`. It counts records that failed to replay, and — per spec D8 — a failed ledger reconciliation also makes the exit non-zero.

**`--simulated-fills` is the true-positive, not a convenience.** Zero journaled fills exist, so without it every refusal in Tasks 1–3 could be an always-refusing guard shipping green. It takes `accumulation_payload`'s modelled placements as the fill source at the journaled close, labelled `"MAKER"` (the ladder is maker-first).

**The two fixtures, specified.** `--simulated-fills` needs journaled snapshot **parquets** (`_snapshot_reader` resolves `journal_dir / entry.path` and raises when absent), so neither fixture can be synthesised JSON alone:
- `real_journal_fixture` — a session-scoped fixture that copies a bounded slice of `/mnt/zhao-crypto/engine-journal` (three complete ISO weeks plus their referenced snapshot parquets) into `tmp_path_factory`, **and a refdata snapshot alongside it**. It **skips** when the mount is absent: `pytest.skip("engine journal mount not present")`.
- **Every invocation passes `--minimums` explicitly** (Tasks 4 and 5, all six). With it absent, `_resolve_minimums(None)` globs the refdata pattern under the *configured data dir*, so the tests would silently depend on the developer's own `data/snapshots` rather than on the fixture — and `test_the_command_writes_nothing` diffs mtimes only inside the fixture, so a write outside it would be invisible.
- `short_journal_fixture` — the same, sliced to one partial week.
- `mixed_schema_fixture` — a two-record tree built in `tmp_path`, one `schema_version: 1` record and one `schema_version: 2`, with their snapshot parquets. Mount-free, so it runs in CI.
- **CI has no mount, so these skip there.** What still covers D6 in CI: Tasks 1–3's fixture tests and their mutate-probes, which are mount-free. The end-to-end true-positive is a workstation gate, run in Step 5 and recorded in the closeout — state this in the test module's docstring so a green CI run is not misread as having exercised it.

- [ ] **Step 1: Write the failing tests.**

```python
def test_simulated_fills_produce_a_non_degenerate_report(real_journal_fixture):
    result = runner.invoke(app, ["engine", "tracking-report", "--journal-dir",
                                 str(real_journal_fixture), "--simulated-fills",
                                 "--nav", "1000", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    weeks = payload["tracking"]["weeks"]
    assert weeks, "the replay produced no weeks at all"
    # `_p95` returns NaN on an empty list and `_payload_json` maps non-finite floats to null,
    # so a bare `> 0` would raise TypeError -- a red exit proving nothing about the pipeline.
    assert any(isinstance(w["floor_p95_bps"], (int, float)) and w["floor_p95_bps"] > 0
               for w in weeks), "a silently zeroed pipeline would pass 'it ran'"

def test_the_floor_figures_match_accum_replay_for_the_same_window(real_journal_fixture):
    # One implementation, two callers -- and the two paths genuinely differ (accum-replay goes
    # through accumulation_report with its own NAV list and stamp), so this is not redundant.
    a = runner.invoke(app, ["engine", "accum-replay", "--journal-dir", str(real_journal_fixture),
                            "--nav", "1000", "--json"])
    b = runner.invoke(app, ["engine", "tracking-report", "--journal-dir", str(real_journal_fixture),
                            "--simulated-fills", "--nav", "1000", "--json"])
    assert (json.loads(a.stdout)["by_nav"]["1000.0"]["p95_drift_bps"]
            == pytest.approx(json.loads(b.stdout)["floor"]["p95_drift_bps"]))

def test_the_verdict_is_insufficient_data_before_three_complete_weeks(short_journal_fixture):
    result = runner.invoke(app, ["engine", "tracking-report", "--journal-dir",
                                 str(short_journal_fixture), "--simulated-fills",
                                 "--nav", "1000", "--json"])
    assert json.loads(result.stdout)["tracking"]["verdict"] == "insufficient-data"

def test_the_command_writes_nothing(real_journal_fixture):
    before = {p: p.stat().st_mtime_ns for p in real_journal_fixture.rglob("*") if p.is_file()}
    runner.invoke(app, ["engine", "tracking-report", "--journal-dir", str(real_journal_fixture),
                        "--simulated-fills", "--nav", "1000"])
    after = {p: p.stat().st_mtime_ns for p in real_journal_fixture.rglob("*") if p.is_file()}
    assert before == after

def test_the_minimums_snapshot_stamp_is_quoted(real_journal_fixture):
    result = runner.invoke(app, ["engine", "tracking-report", "--journal-dir",
                                 str(real_journal_fixture), "--simulated-fills", "--nav", "1000"])
    assert "minimums read" in result.stdout.lower()

def test_a_window_straddling_the_schema_bump_says_so(mixed_schema_fixture):
    # Schema 1 records are base-keyed, schema 2 symbol-keyed; a straddling run must say so
    # rather than mixing key spaces silently (spec D3).
    result = runner.invoke(app, ["engine", "tracking-report", "--journal-dir",
                                 str(mixed_schema_fixture), "--simulated-fills", "--nav", "1000"])
    assert "schema" in result.stdout.lower()

def test_a_simulated_run_is_labelled_as_simulated(real_journal_fixture):
    # Spec D6: the number is real-shaped but not real. An unlabelled one read in the go/no-go
    # window is the whole hazard.
    result = runner.invoke(app, ["engine", "tracking-report", "--journal-dir",
                                 str(real_journal_fixture), "--simulated-fills", "--nav", "1000"])
    assert "simulated" in result.stdout.lower()
```

**Two things Task 2 hands this task, registered here rather than left in a task report:**

- **`realized_drift` hard-aborts on an orphaned fill, and this command must decide what that means.** `accumulation_report` DROPS a record whose `replay_stages` raises, names it in `failures` and counts it in `n_failed` — but a fill journaled under that dropped boundary then orphans, and `realized_drift` raises `EngineError`, replacing that designed degradation with a hard abort of the whole report. It is masked under `--simulated-fills` (the fills derive from the surviving stages) and bites at rung 1 with real fills. Wrap the `weekly_tracking` call in the same `except EngineError → _abort` pattern `decompose` already uses, so a replay failure still yields a named, counted, exit-1 report rather than a stack trace.
- **Key the cost text on `n_priced`, not on the `basis` phrase.** `basis` selects its "no euro-denominated fills" wording from `realized is not None`, while `realized` is gated on `priced_notional > 0` — so a window whose fills all carry zero quantity would read that phrase with `n_priced > 0`. The proposed number stays correctly `None`; only the sentence is imprecise.
- **`maker_share + taker_share` sum to 1.0 over the PRICEABLE book only.** `NO_LIQUIDITY_SIDE` notional is accumulated but excluded from `gross`, and an all-`NO_LIQUIDITY_SIDE` window returns `None` for both shares. The renderer must not print them as a complete split of the window's trading.
- **A straddling week is distinguishable only by elimination.** Its row reads `complete: True, rung: None, gate_eligible: False`, and a reader must infer why. The renderer decides knowingly: either label it in the text, or state in this task's report that eliminating is sufficient. Do not leave the choice implicit.

- [ ] **Step 2: Run and read WHICH assertion fails.** Expected: `No such command 'tracking-report'`.

- [ ] **Step 3: Implement the Typer command**, following `accum_replay`'s structure (same inputs, same helpers): resolve journal, `_window_records`, `_snapshot_reader`, `replay_stages` per record, `load_minimums`, then `weekly_tracking` + `cost_blend` (+ `reconcile_ledger` when `--ledger-export` is given), then `_emit_report` with a payload carrying `n_failed`. Quote the venue-minimums snapshot stamp as `accum-replay` does.

  Two output lines the tests above pin, and neither falls out of the arithmetic — write them deliberately: **the schema straddle** (collect the distinct `schema_version` values across the window's records; when more than one, say so in the text and carry the set in the payload) and **the simulated label** (when `--simulated-fills` is set, the text says the fills are simulated and the payload carries the flag).

- [ ] **Step 4: Run to green.**

- [ ] **Step 5: Run it over the real pulled journal** — `/mnt/zhao-crypto/engine-journal`, read-only, never a live dir — and read the OUTPUT, not the exit code. Record the week count, each week's floor p95, and `verdict`. Zero fills exist, so without `--simulated-fills` the realized half must read *no data* on every week; a realized number there is a defect. Paste the run into the task report.

- [ ] **Step 6: `README.md` `## Usage`** gains the subcommand and every flag, same commit.

- [ ] **Step 7: Commit.** `feat(engine): tracking-report, with the replay-as-fills true-positive`

---

### Task 5: Component B — the standing reader for the owner's Kraken ledger export

**Files:**
- Modify: `cli/engine/tracking.py`, `cli/engine/command.py`, `infra/runbooks/engine.md`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Produces: `LedgerRow` (NamedTuple: `txid: str`, `refid: str`, `at: datetime`, `type: str`, `asset: str`, `amount: float`, `fee: float`) and:
  - `read_ledger_export(path: Path) -> list[LedgerRow]`
  - `reconcile_ledger(rows, fills) -> dict` — `{"status": "ok"|"FAILED", "matched": int, "rollover_fees_eur": float, "unmatched": list[str]}`

**What it replaces.** T0018: *"Rung 1's rollover rows are read by hand from the owner's ledger export during the attended window; the standing reader is `00091`'s."* It reads a file the owner exports — no API key, no venue call, no fetch.

**Why it belongs to the cost component:** a margin position's rollover fee is charged against the POSITION, not against a fill, so a cost basis built from fills alone omits it.

**The export's columns are an assumption until the first real export is read.** Kraken's ledger CSV is documented as `txid,refid,time,type,subtype,aclass,asset,amount,fee,balance`. The reader is **header-driven and refuses an export whose header lacks a column it needs, naming the missing column**, so a changed format fails loudly instead of parsing into plausible nonsense. Do not "handle" a missing column with a default.

**An unmatched row fails the reconciliation, not the run** (spec D8): the block reports `FAILED`, names every unmatched id, and the cost half refuses to publish a blend built over a ledger it could not reconcile — while the drift half still prints, because denying the operator the numbers they need to investigate is the disproportion D5 rejects. The exit code is non-zero so no script reads a failed reconciliation as a pass.

- [ ] **Step 1: Write the failing tests.**

```python
_HEADER = "txid,refid,time,type,subtype,aclass,asset,amount,fee,balance"

def _export(tmp_path, rows, header=_HEADER):
    p = tmp_path / "ledgers.csv"
    p.write_text(header + "\n" + "\n".join(rows) + "\n")
    return p

def _lfill(trade_id="T-1"):
    b = datetime.fromisoformat("2026-08-31T00:00:00+00:00")
    return Fill(b, b, "BTC", "buy", 0.001, 50000.0, 0.05, "MAKER", trade_id)

def test_a_missing_column_is_refused_by_name(tmp_path):
    p = _export(tmp_path, [], header="txid,time,type,asset,amount")
    with pytest.raises(EngineError, match="fee"):
        read_ledger_export(p)

def test_rollover_rows_are_summed_as_a_cost(tmp_path):
    p = _export(tmp_path, ['"L1","R1","2026-08-31 00:00:00","rollover","","currency","ZEUR","-0.12","0.12","900.0"'])
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["rollover_fees_eur"] == pytest.approx(0.12)

def test_a_non_euro_rollover_is_not_summed_into_a_euro_total(tmp_path):
    p = _export(tmp_path, ['"L1","R1","2026-08-31 00:00:00","rollover","","currency","XXBT","-0.0001","0.0001","1.0"'])
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["rollover_fees_eur"] == pytest.approx(0.0)

def test_a_trade_row_matching_no_journaled_fill_FAILS_the_reconciliation(tmp_path):
    # The account did something the engine's record does not know about -- the one thing this
    # component exists to detect. Named, never averaged away.
    p = _export(tmp_path, ['"L2","T-UNKNOWN","2026-08-31 00:00:00","trade","","currency","ZEUR","-50.0","0.05","850.0"'])
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["status"] == "FAILED" and out["unmatched"] == ["T-UNKNOWN"]

def test_a_trade_row_matching_a_journaled_fill_reconciles(tmp_path):
    p = _export(tmp_path, ['"L3","T-1","2026-08-31 00:00:00","trade","","currency","ZEUR","-50.0","0.05","850.0"'])
    out = reconcile_ledger(read_ledger_export(p), [_lfill("T-1")])
    assert out["status"] == "ok" and out["matched"] == 1 and out["unmatched"] == []

def test_a_failed_reconciliation_makes_the_command_exit_non_zero(tmp_path, real_journal_fixture):
    p = _export(tmp_path, ['"L2","T-UNKNOWN","2026-08-31 00:00:00","trade","","currency","ZEUR","-50.0","0.05","850.0"'])
    result = runner.invoke(app, ["engine", "tracking-report", "--journal-dir",
                                 str(real_journal_fixture), "--simulated-fills",
                                 "--ledger-export", str(p), "--nav", "1000"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run and read WHICH assertion fails.**

- [ ] **Step 3: Implement** with `csv.DictReader`, refusing on a missing required column by name. Sum `fee` over `type == "rollover"` rows **whose `asset` is in `EUR_CODES`**; match `type == "trade"` rows to fills by `refid` against `Fill.trade_id`.

- [ ] **Step 4: Run to green.**

- [ ] **Step 5: Wire `--ledger-export PATH`** into Task 4's command; absent, the report omits the reconciliation block rather than refusing — the export is an attended artifact and most runs will not have one. A `FAILED` block contributes to `n_failed`.

- [ ] **Step 6: Prove the refusals bite.** Drop the required-column check → the missing-column test fails; make an unmatched row a warning → the FAILED test fails; drop the asset filter → the non-euro rollover test fails.

- [ ] **Step 7: The probe checklist gains the comparison.** `infra/runbooks/engine.md`'s probe-window procedure already has the owner exporting the ledger. Add the step that runs the reader against that export **once while the hand-read still exists**, and compares the two — a standing reader that never agreed with the hand-read it replaced has not been verified.

- [ ] **Step 8: Commit.** `feat(engine): the standing ledger-export reader, refusing an export it cannot map`

---

### Task 6: The cycle record journals the closes it used (LIVE PATH — Fable floor)

**Files:**
- Modify: `cli/engine/journal.py`, `cli/engine/cycle.py`
- Test: `tests/test_engine_journal.py`, `tests/test_engine_cycle.py`

**Why this exists.** Component C must compute realized drift at a boundary, and the only producer of `CycleStages` is `replay_stages` — snapshot reads, content-hash verification and the full builder, per cycle. **Measured: 73 s for one ISO week** (`accum-replay` over 2026-08-10..16, 42 cycles, ~91 MB). Inside the executor that blocks the nautilus event loop for over a minute with orders possibly resting, and pushes `completed_at` toward the `[B, B+30 min]` bound that is itself a gate-streak condition.

The artifact already carries `final_targets`; **closes are the only missing term.**

**The record is `journal.py`'s, not `cycle.py`'s.** `CycleRecord` is an eight-field dataclass; `to_json` writes an explicit key list, `from_json` reads an explicit key list, and `validate_record` is schema-aware. Nothing done in `cycle.py` alone can put a key into the artifact.

**The value already exists in `run_cycle`:** `model_h4` — base-keyed, the ten EUR legs, the identical construction `replay_stages` uses for `CycleStages.closes`. **Not** `h4_closes`, which is pair-keyed. Pass it; do not recompute it.

**Journal the INPUT, not the derivative.** A journaled drift number would rot against the code that derived it; journaled closes stay true.

**Readers before writer** (`capture-deploys.md`). Tasks 1–5 never read `closes`, and the absence-tolerant `from_json` arm below is what keeps the 258 existing artifacts loadable.

- [ ] **Step 1: Write the failing tests** in `tests/test_engine_journal.py`, built the way that module already builds records (there are no `journal_dir` / `one_cycle` / `legacy_artifact` fixtures — `tests/test_engine_cycle.py` works from `tmp_path, monkeypatch` plus `_env(...)` / `_success_record_json(...)`; follow those).

```python
def test_the_record_round_trips_its_closes():
    rec = _record(closes={"BTC": 50000.0, "ETH": 3000.0})
    assert from_json(json.loads(to_json(rec)))["closes"] == {"BTC": 50000.0, "ETH": 3000.0}

def test_closes_are_base_keyed_ten_and_positive():
    art = json.loads(to_json(_record(closes=_ten_eur_closes())))
    assert set(art["closes"]) == {s.split("/")[0] for s in art["final_targets"] if s.endswith("/EUR")}
    assert "BTC" in art["closes"] and "BTC/EUR" not in art["closes"]
    assert all(isinstance(v, float) and v > 0 for v in art["closes"].values())

def test_an_artifact_without_closes_still_loads():
    # The 258 artifacts on disk have no closes key. A reader that raised on them would take
    # component A down over its own upgrade -- this IS the readers-before-writer guarantee.
    payload = json.loads(to_json(_record(closes=_ten_eur_closes())))
    del payload["closes"]
    assert from_json(payload).closes is None

def test_validate_record_refuses_a_pair_keyed_closes():
    payload = json.loads(to_json(_record(closes=_ten_eur_closes())))
    payload["closes"] = {"BTC/EUR": 50000.0}
    with pytest.raises(EngineError, match="closes"):
        validate_record(payload)
```

- [ ] **Step 2: Run and read WHICH assertion fails.**

- [ ] **Step 3: Implement in `journal.py`** — a `closes: dict[str, float] | None` field on `CycleRecord`, the `to_json` arm, an absence-tolerant `from_json` arm (`payload.get("closes")`), and the `validate_record` arm (base-keyed, positive floats). Then in `cycle.run_cycle`, pass `model_h4` into the `CycleRecord(...)` construction.

- [ ] **Step 4: Run to green, then the FULL suite** — this touches the record every engine reader parses, and `tests/test_engine_cycle.py::_success_record_json` needs the new key.

- [ ] **Step 5: Prove the tolerance arm bites.** Change `payload.get("closes")` to `payload["closes"]` → the without-closes test must fail. That arm is the readers-before-writer guarantee; a probe that does not bite here leaves the existing journal unprotected.

- [ ] **Step 6: Commit.** `feat(engine): the cycle artifact journals the closes it used`

**Deploy note (not a plan step):** the WRITER half of a schema widening — every reader converges first. Attended, inside a 4-hourly inter-cycle gap, canary-gated, from a tree whose rendered config matches the fleet.

---

### Task 7: Component C — the tracking-error trip (LIVE TRADE PATH — Fable floor)

**Files:**
- Modify: `cli/config.py`, `cli/engine/execledger.py`, `cli/engine/executor.py`, `zcrypto.toml`, `infra/ansible/roles/capture/files/config.alloy`, `infra/grafana/engine-dashboard.json`, `infra/runbooks/engine.md`
- Test: `tests/test_config.py`, `tests/test_engine_execledger.py`, `tests/test_engine_executor.py`

**Interfaces:**
- **Requirement inherited from Task 2's review:** `drift_bps` raises a bare `KeyError` when `closes` lacks an asset present in `final`. On component A that is unreachable — `replay_stages` builds both over the same asset set and raises `EngineError` first — but on THIS path the inputs are journaled artifacts that can disagree, so component C must check `set(final) <= set(closes)` and refuse the week rather than propagate a `KeyError`. The refusal is owed here, not in `drift_bps`, which would otherwise be guarding a door with no caller.
- Consumes: `tracking.drift_bps` (Task 2's shared core — plain dicts), `tracking.extract_fills`, the journaled `closes` (Task 6), `EngineConfig.shadow_nav_eur`, `self._trip_kill(reason)`.
- Produces: `EngineConfig.tracking_band_bps: float | None`; `execledger.exec_records_for_week(journal_dir, iso_key)`; `executor._evaluate_tracking_band(now)`; a rendered gauge.

**It never computes the floor, and cannot.** `load_minimums` reads a refdata **snapshot file**; the engine host carries no refdata snapshot (state dir and config only), and `accumulation_payload` raises on the first asset with no minimum. So the trip compares that week's realized mean drift against the **configured** `tracking_band_bps`, which a human sets from component A's output — where the floor IS computed, on a workstation that has the snapshot. Do not import `weekly_tracking` or `accumulation_payload` here.

**Its inputs are all journaled**: `final_targets` (pair-keyed twelve → contracted to the ten EUR bases at this reader's edge), `closes` (base-keyed, Task 6), fills (`extract_fills`), NAV (`shadow_nav_eur`).

- [ ] **Step 1: The week-window reader.** `execledger._exec_records_in_window` is **current + previous UTC day** — a 2/7 window that would silently see five sevenths of nothing. Add `exec_records_for_week(journal_dir, iso_key) -> list[dict]` built from the week's day dirs, with its own test asserting it returns all seven days and ignores neighbouring weeks. A trip reading 2/7 of a week is a wrong number with a kill file attached.

- [ ] **Step 2: The config knob, with its refusals.** `EngineConfig` is a frozen dataclass in `cli/config.py` with a hand-written per-key parser; follow the `shadow_nav_eur` arm, including a `math.isfinite` refusal — a `nan` band defeats every `>` comparison. The table is `[zcrypto.engine]` (`CONFIG_TABLE = "zcrypto"`), not `[engine]`. Tests: absent → `None`; negative, zero, `nan`, and non-number each refused by name.

- [ ] **Step 3: Write the failing executor tests.** Build the fixtures from `tests/test_engine_executor.py`'s existing patterns; each helper below is this task's own scaffolding.

```python
def test_an_unset_band_never_trips(executor_disarmed):
    executor_disarmed._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_disarmed._kill_tripped is False
    assert not (exec_dir(executor_disarmed._state_dir) / KILL_FILE).exists()

def test_a_complete_week_beyond_the_band_latches_the_kill_file(executor_with_band_120):
    # THE CONSTRUCTED DEFECT.
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=300.0)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_with_band_120._kill_tripped is True
    assert "tracking" in (exec_dir(executor_with_band_120._state_dir) / KILL_FILE).read_text()

def test_a_healthy_complete_week_does_not_trip(executor_with_band_120):
    # THE TRUE-POSITIVE. Without it an always-tripping guard ships green.
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=40.0)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_with_band_120._kill_tripped is False

def test_a_quiet_week_with_a_started_series_still_trips(executor_with_band_120):
    # The failure the trip exists for: the engine stopped placing entirely.
    _journal_a_week_with_no_fills_after_a_filled_one(executor_with_band_120)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_with_band_120._kill_tripped is True

def test_a_partial_week_never_trips_however_bad_it_looks(executor_with_band_120):
    _journal_a_partial_week(executor_with_band_120, realized_mean_bps=5000.0)
    executor_with_band_120._evaluate_tracking_band(_mid_week_boundary())
    assert executor_with_band_120._kill_tripped is False

def test_it_is_refused_while_exec_armed_is_false(executor_band_120_not_armed):
    _journal_a_complete_week(executor_band_120_not_armed, realized_mean_bps=300.0)
    executor_band_120_not_armed._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_band_120_not_armed._kill_tripped is False

def test_a_week_missing_journaled_closes_is_refused_not_guessed(executor_with_band_120):
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=300.0, closes=None)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_with_band_120._kill_tripped is False

def test_an_unreadable_journal_does_not_raise_onto_the_trade_path(executor_with_band_120):
    _corrupt_a_cycle_artifact(executor_with_band_120)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())  # must not raise
    assert executor_with_band_120._kill_tripped is False

def test_the_trip_is_idempotent_and_keeps_the_first_reason(executor_with_band_120):
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=300.0)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    first = (exec_dir(executor_with_band_120._state_dir) / KILL_FILE).read_text()
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert (exec_dir(executor_with_band_120._state_dir) / KILL_FILE).read_text() == first

def test_the_executor_actually_CALLS_the_trip_at_a_boundary(executor_with_band_120):
    # A guard nothing calls ships green exactly as an always-refusing one does.
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=300.0)
    _drive_one_boundary_tick(executor_with_band_120)      # the real tick path, not the method
    assert (exec_dir(executor_with_band_120._state_dir) / KILL_FILE).exists()

def test_the_pair_keyed_targets_are_contracted_before_comparison(executor_with_band_120):
    # final_targets is pair-keyed twelve including the /BTC legs at zero weight; an uncontracted
    # read matches no close and the drift is computed against nothing.
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=300.0)
    assert executor_with_band_120._week_mean_bps(_last_complete_week()) == pytest.approx(300.0, rel=0.05)
```

- [ ] **Step 4: Run and read WHICH assertion fails.** Expected: `AttributeError: _evaluate_tracking_band`.

- [ ] **Step 5: Implement, and NAME THE CALL SITE.** Wire the evaluation into the boundary path beside the existing gate evaluation — **the task is not done while the method exists and nothing calls it.** Return immediately when the band is unset or `exec_armed` is false; read the just-closed week via Step 1's reader; contract `final_targets` to the ten EUR bases; refuse a week lacking `closes`; wrap every read in an exception boundary; compute each cycle's `drift_bps` from the shared core and mean them; trip only on a **complete** week whose mean exceeds the band, with a reason naming the week, the mean and the band. Reuse `_trip_kill` — no second latch path.

- [ ] **Step 6: Prove the guard bites, reading WHICH failure fires.** Via `mutate-probe.sh`: drop the `complete` condition → the partial-week test fails; invert the comparison → the healthy-week test fails; drop the unset-band early return → the disarmed test fails; drop the `exec_armed` check → that test fails; skip the pair→base contraction → the contraction test fails; **delete the call site → the call-site test fails** (that one is the point of Step 5).

- [ ] **Step 7: Render the state.** A gauge for the trip's armed/disarmed state, added to the capture role's keep-regex in `config.alloy` **and** a dashboard target — a disarmed trip with no rendered state cannot be confirmed disarmed after the converge. **No new alert rule**: a latched trip already pages via `zcrypto-engine-exec-kill-tripped`, and a second would double-page one event; record that decision in the runbook section so its absence does not read as an oversight.

- [ ] **Step 8: The runbook section** — what the operator sees, what it means, what to do, when it retires. No internal traceability tokens in operator-visible strings.

- [ ] **Step 9: Commit.** `feat(engine): the tracking-error trip, disarmed until three complete weeks exist`

**Deploy note (not a plan step) — three legs, in this order:**
1. **Readers first** (Tasks 1–5 merged), then the writer (Task 6), then this.
2. **Engine + capture converge**, attended, inside a 4-hourly inter-cycle gap, canary-gated (the secondary's capture bake IS the engine's gate). `--tags capture,engine` because the keep-regex lives in the capture role, with `-e capture_image_digest` and `-e capture_alloy_digest` at the currently-running digests. Verify the new family **by value** at the next scrape — `(no series)` is FAIL.
3. **The NAS leg.** This branch edits `command.py`, `cycle.py` and `journal.py` and adds `tracking.py` to `command.py`'s closure — all inside `gate_cache._REPLAY_ROOTS`' transitive digest, so the fingerprint changes and the whole gate-export replays. **Size that window against the measured 2490 s cold cost**, never the smaller figure. (`evidence_fingerprint` is unaffected — it digests snapshots, `cycle_ts`, `completed_at` and `final_targets`, not `closes`.)

---

### Task 8: Closeout

**Files:**
- Modify: `infra/runbooks/engine.md`, `docs/open-topics/T0018-phase6-build-sequence.md`, `docs/open-topics/T0090-*.md`, `docs/research/14.phase6-decisions.md`, `docs/iterations-history-phase6.md`

- [ ] **Step 1: The probe-window procedure gains the weekly reading** — the command, the ISO week to pass, and what an unproducible week means (a refusal to record, never a zero to shrug at). **This is what makes the absent timer safe** (spec D2): there is no scheduled run, so the procedure is the only thing that compels the reading.

- [ ] **Step 2: The sleeve-composition alert's step 3 gains the realized half** — it currently names only `accum-replay`, which is the floor half.

- [ ] **Step 3: T0018's `00091` row.** It still reads `| 00091 | … | none (read-only) | not started |`. The risk column is now wrong — component C is a live-trade-path kill-switch trip plus a record widening. Update the row's risk tier and status in THIS PR (`open-topics.md`: the PR that completes a sub-item carries that topic's whole update).

- [ ] **Step 4: T0090's next-step.** Task 3 builds the instrument that closes it, but with zero fills the *measurement* cannot be taken. Rewrite the next-step to record exactly that split — instrument shipped, number ripe at first fills — so it neither reads as closed nor loses the residual.

- [ ] **Step 5: The decisions log** — `docs/research/14.phase6-decisions.md`, one `[iter-<N>]` entry per decision, 2–3 options each with `(Decision: N)`: D2 (command vs timer), D4 (propose vs apply, and the fee term vs the sum), D9 (journal the closes vs replay at the boundary), D10 (the trip's evaluation basis).

- [ ] **Step 6: The iterations-history entry** — written NOW, at closeout, against the full branch log.

- [ ] **Step 7: Re-verify every status claim this branch touched** against the branch log immediately before PR-open, and recompute any load-bearing number rather than quoting an earlier draft (the journal counts in this plan were measured 2026-08-22 and will have moved).

- [ ] **Step 8: Commit.** `docs(engine): 00091 closeout -- the weekly reading step, the topics, the decisions, the history`

---

## Self-review

**Spec coverage.** D1 → Task 2. D2 → Task 4 + Task 8 Step 1. D3 → Tasks 1–2. D4 → Task 3. D5 → Tasks 1–3. D6 → Task 4 (the true-positive, the simulated label) and every mutate-probe step. D7 → Tasks 4 Step 6, 5 Step 7, 7 Steps 7–8, 8. D8 → Task 5. D9 → Task 6. D10 → Task 7.

**Placeholders.** Named-but-unwritten scaffolding, stated honestly rather than denied: Task 6's `_record` / `_ten_eur_closes` and Task 7's `_journal_a_complete_week` / `_drive_one_boundary_tick` / `_corrupt_a_cycle_artifact` / `_boundary_after_a_complete_week`. Both test modules already own these patterns (`tests/test_engine_cycle.py` works from `tmp_path, monkeypatch` + `_env(...)` / `_success_record_json(...)`), and the implementer builds them from there. Everything else — values, keys, signatures, the exact source variable (`model_h4`, not `h4_closes`) — is given. Task 5's export columns are a stated assumption behind a fail-loud reader.

**Type consistency.** `Fill` carries `boundary, at, base (str | None), side, qty, px, fee (float | None), liquidity, trade_id` from Task 1 onward; no later task changes it. Week labels are `"YYYY-Www"` strings everywhere including `rung_by_week` keys. `realized_drift`'s shape is explicitly NOT `accumulation_payload`'s block. `drift_bps(final, closes, held, nav)` is the one function both components call, so the number a human bands and the number the engine trips on cannot diverge.

**Ordering.** Readers (1–5) before the writer (6), and 7 depends on 6's output. Task 7 imports `drift_bps` and `extract_fills` but never `weekly_tracking` or `accumulation_payload` — those need venue minimums, which the engine host has no snapshot for.

**Verification.** Every refusal constructed and seen to trip, each probe naming WHICH assertion must fire, and the three probes that could not bite are now given the fixtures that make them bite. Both always-green failure modes are covered: always-refusing (the true-positives) and never-called (Task 7's call-site test). Task 4 Step 5 runs the pipeline over the real journal where the honest answer is *no data*.
