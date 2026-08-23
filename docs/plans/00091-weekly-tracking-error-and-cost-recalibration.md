# Weekly tracking-error report and cost recalibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the three obligations T0018 registers to serial `00091` — (A) `zcrypto engine tracking-report`, the read-only weekly instrument rung 3's go/no-go reads; (B) the standing reader for the owner's Kraken ledger export, which replaces a by-hand rollover-row read; (C) the tracking-error kill-switch trip, which is engine code on the live trade path.

**Architecture:** A new pure module `cli/engine/tracking.py` holds the arithmetic and the refusals for A and B; `cli/engine/command.py` gains only Typer wiring; `cli/engine/executor.py` gains C's trip beside the divergence trips it already carries. The floor half of the comparison is not re-derived — it calls the validated `accumulation_payload`.

**Tech Stack:** Python 3.14, Typer, pytest. No new dependencies.

## The three components do not ship alike

| | what it is | risk tier | review floor | how it reaches production |
| --- | --- | --- | --- | --- |
| **A** | `tracking-report`, read-only, workstation-only | none — reads a pulled journal | Opus | nothing to deploy |
| **B** | Kraken ledger-export reader, read-only over a file the owner exports | none — no credential, no venue call | Opus | nothing to deploy |
| **C** | the tracking-error trip in the executor | **live trade path** | **Fable** (`spec-plan-locations.md`) | canary-gated engine converge; ships **disarmed** |

Tasks 1–5 are A and B. Tasks 6–7 are C. **Task 6 is the only task touching code that runs with real money**, and its review floor is Fable, not Opus.

## Global Constraints

- **A and B write nothing anywhere** — not the journal, not config, not the fleet. `fee_per_side` is PROPOSED, never applied (spec D4).
- **Reuse the floor, do not re-derive it.** `accumulation_payload` is validated against T0118's registered curve; a second implementation is a second thing to be wrong (spec D1).
- **`held` accumulates from the ledger's own fills in BASE UNITS**, never EUR, never `zcrypto_exec_position`, never the venue record (spec D3). Drift is measured AFTER the placement decision, exactly as `accumulation_payload` does.
- **One key space per run.** `accumulation_payload` and `load_minimums` are keyed by **base** (`"BTC"`, `"ETH"`); a journaled intent's `symbol` is a **pair** (`"BTC/EUR"`, `"ETH/BTC"`). Every fill is mapped pair → base at the reader's edge, once, and nothing downstream sees a pair. Verified: `cli/engine/store.BASKET` is twelve pair strings; `feeders.load_minimums` keys by `entry["base"]` under a `quote == "EUR"` filter.
- **Fail closed, and fail PROPORTIONATELY.** A week with no fills reads *no data*, never zero drift. A `liquidity` outside the venue's own names aborts the cost half. A non-EUR `fee_currency` disables the cost half **and says so** — it does not abort the run (spec D5).
- **`liquidity` is stored UPPERCASE.** `executor._liquidity` writes the venue's NAME — `"MAKER"` / `"TAKER"` / `"NO_LIQUIDITY_SIDE"` — because `str()` on the pinned `LiquiditySide` `IntFlag` yields `"1"`. Match the stored casing. A lowercase-only match aborts every real fill while every lowercase fixture passes.
- **The euro has two spellings.** Import `executor._EUR_CODES` (`("EUR", "ZEUR")`); never test `== "EUR"`.
- **Partial ISO weeks are excluded from every verdict** and marked in the output. The gate needs ≥3 complete weeks (spec D3).
- **Rung-2 weeks are labelled measured-but-not-gate-eligible** and excluded from verdicts (spec D3, T0116 ratified).
- Every command flag documented in `README.md` `## Usage` in the same change (`readme-usage.md`).
- Loggers are `get_logger("engine.tracking")`. Match `cli/engine/feeders.py`'s docstring register: state WHY, name the failure the code prevents.
- **No internal traceability vocabulary on operator-visible surfaces** (`operator-facing-text.md`) — not in `--help`, not in the report's own text, not in a metric HELP string. `tests/test_internal_terms_not_operator_visible.py` enforces it.

## The input does not exist yet — measured, not assumed

The live engine journal at `/mnt/zhao-crypto/engine-journal` holds **64 exec records spanning 2026-08-12 → 2026-08-22, every one `level: "none"`, with zero `submitted` rows and therefore zero fills** (read 2026-08-22). Rung 1 is unfunded, so the engine has never submitted an order.

Three consequences bind this plan:

1. Every unit test is fixture-based. There is no real fill to read.
2. The only production-shaped input available is `--simulated-fills` — `replay_stages` over real journaled cycles, its placements read as fills. That is the true-positive the guard-proving rule demands (`agent-ops.md`), and without it every refusal in Tasks 1–3 could be an always-refusing guard shipping green.
3. Component C cannot be proven by observation either. Its defect is CONSTRUCTED (Task 6, Step 5) — spec D9 and T0018's own rule: *"a guard whose defect cannot be constructed is unproven by this project's own rule."*

## File structure

| file | responsibility |
| --- | --- |
| `cli/engine/tracking.py` (new) | pure arithmetic + refusals: fill extraction, realized drift, ISO-week aggregation, cost blend, ledger-export reconciliation. No I/O beyond reading the export path handed to it. |
| `cli/engine/command.py` (modify) | `tracking-report` Typer command: resolve journal/minimums/NAV/export, call the module, `_emit_report`. |
| `cli/engine/executor.py` (modify) | component C only: the complete-week tracking-error trip, beside the existing divergence trips. |
| `tests/test_engine_tracking.py` (new) | fixtures for every arm and refusal, plus the `--simulated-fills` true-positive. |
| `tests/test_engine_executor.py` (modify) | component C's constructed defect and its healthy true-positive. |
| `README.md` (modify) | `## Usage` entry. |
| `infra/runbooks/engine.md` (modify) | probe-window procedure gains the weekly reading step; sleeve-alert step 3 gains the realized half; component C gains its own alert section. |

## Interfaces this plan consumes (read from the repo 2026-08-22, use verbatim)

- `feeders.accumulation_payload(stages: list[CycleStages], minimums: dict[str, tuple[float, float]], navs: list[float]) -> dict` — `{"by_nav": {nav: {"cycles": [{"cycle_ts": str, "drift_bps": float, "drift_eur": float, "placed": bool, "target_qty": dict}], "median_drift_bps": float, "p95_drift_bps": float, "n_placed": int, "weeks": [...]}}}`. **Keyed by base.**
- `feeders.replay_stages(record, reader, *, config=None) -> CycleStages`
- `feeders.load_minimums(path: Path) -> tuple[dict[str, tuple[float, float]], str]` — **keyed by base**, EUR-quoted pairs only.
- `command._window_records(journal_root: Path, since: str | None, until: str | None) -> list[CycleRecord]`
- `command._resolve_minimums(flag_value: Path | None) -> Path`
- `command._snapshot_reader(journal_dir: Path)`
- `command._emit_report(text: str, payload: dict, *, as_json: bool) -> None`
- `execledger._exec_records_in_window(journal_dir: Path, now: datetime) -> list[dict]` — **current + previous UTC day only**; the report reads its own window instead.
- Exec-record shape: `{"schema_version", "cycle_ts", "evaluated_at", "level", "reasons", "inputs", "plans", "submitted"}`
- Submitted-row key set (`execledger._ROW_KEYS`, exact): `{plan_id, intent_index, client_order_id, intent, order, state, filled_qty, events}`
- `row["intent"]` is `dict(ctx.raw_intent)` — the probe-plan intent, keys `{symbol, side, action, mode, notional_eur, qty, leverage}` (`probeplan._INTENT_KEYS`). **There is no `asset` key.**
- Fill event inside `row["events"]` (`executor._fill_payload`, verbatim): `{"event": "fill", "at": iso, "qty": float, "px": float, "fee": float, "fee_currency": str, "liquidity": "MAKER"|"TAKER"|"NO_LIQUIDITY_SIDE", "trade_id": str}`
- `executor._EUR_CODES = ("EUR", "ZEUR")`
- `executor._trip_kill(reason: str) -> None` — idempotent through `self._kill_tripped`; writes the kill file, cancels every resting order, halts the plan, republishes the gate.
- `cli.engine.store.BASKET` — `['ADA/EUR','AVAX/EUR','BTC/EUR','DOGE/EUR','DOT/EUR','ETH/BTC','ETH/EUR','LINK/EUR','LTC/EUR','SOL/BTC','SOL/EUR','XRP/EUR']`

---

### Task 1: The fill reader and its refusals

**Files:**
- Create: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: the exec-record and fill-event shapes above.
- Produces: `Fill` (NamedTuple: `at: datetime`, `base: str`, `qty: float`, `px: float`, `fee: float | None`, `liquidity: str`) and `extract_fills(records: list[dict]) -> tuple[list[Fill], list[str]]` — the fills, and the notes that disabled anything (e.g. a non-EUR fee currency).

- [ ] **Step 1: Write the failing tests.** Every refusal is a defect constructed and seen to trip; the happy path uses the venue's real uppercase spelling.

```python
import pytest
from cli.engine.errors import EngineError
from cli.engine.tracking import extract_fills

def _rec(events, *, symbol="BTC/EUR", state="filled"):
    return {"schema_version": 2, "cycle_ts": "2026-09-01T00:00:00+00:00",
            "evaluated_at": "2026-09-01T00:00:05+00:00", "level": "full", "reasons": [],
            "inputs": {}, "plans": [],
            "submitted": [{"plan_id": "p1", "intent_index": 0, "client_order_id": "O-1",
                           "intent": {"symbol": symbol, "side": "buy", "action": "open",
                                      "mode": "spot", "notional_eur": 50.0, "qty": None,
                                      "leverage": None},
                           "order": {"qty": 0.001}, "state": state, "filled_qty": 0.001,
                           "events": events}]}

def _fill(**kw):
    base = {"event": "fill", "at": "2026-09-01T00:01:00+00:00", "qty": 0.001, "px": 50000.0,
            "fee": 0.05, "fee_currency": "EUR", "liquidity": "MAKER", "trade_id": "T-1"}
    base.update(kw)
    return base

def test_extract_fills_reads_the_venues_own_uppercase_liquidity():
    fills, notes = extract_fills([_rec([_fill()])])
    assert notes == []
    assert len(fills) == 1
    f = fills[0]
    assert (f.base, f.qty, f.px, f.fee, f.liquidity) == ("BTC", 0.001, 50000.0, 0.05, "MAKER")

def test_the_pair_is_mapped_to_a_base_at_the_edge():
    # accumulation_payload and load_minimums are base-keyed; a pair leaking downstream
    # would silently match no floor at all.
    fills, _ = extract_fills([_rec([_fill()], symbol="ETH/BTC")])
    assert fills[0].base == "ETH"

def test_non_fill_events_are_ignored():
    fills, notes = extract_fills([_rec([{"event": "accepted", "at": "2026-09-01T00:00:30+00:00"}])])
    assert (fills, notes) == ([], [])

def test_a_liquidity_the_venue_never_names_aborts():
    # `str()` on the pinned library's IntFlag yields "1" -- this repo shipped exactly that
    # into the forensic ledger once. A blend over unlabelled sides is wrong invisibly.
    with pytest.raises(EngineError, match="liquidity"):
        extract_fills([_rec([_fill(liquidity="1")])])

def test_lowercase_liquidity_is_refused_because_the_ledger_never_writes_it():
    with pytest.raises(EngineError, match="liquidity"):
        extract_fills([_rec([_fill(liquidity="maker")])])

def test_zeur_is_a_euro():
    fills, notes = extract_fills([_rec([_fill(fee_currency="ZEUR")])])
    assert notes == [] and fills[0].fee == 0.05

def test_a_btc_denominated_fee_disables_the_cost_half_without_aborting():
    # ETH/BTC and SOL/BTC legs pay BTC fees legitimately; the executor's own _fee_eur
    # returns None for them rather than raising. Taking the whole report down over a leg
    # structurally at zero target would be out of proportion to the doubt.
    fills, notes = extract_fills([_rec([_fill(fee_currency="XXBT")], symbol="ETH/BTC")])
    assert len(fills) == 1 and fills[0].fee is None
    assert any("XXBT" in n for n in notes)

def test_a_symbol_outside_the_basket_aborts():
    with pytest.raises(EngineError, match="basket"):
        extract_fills([_rec([_fill()], symbol="PEPE/EUR")])
```

- [ ] **Step 2: Run them and read WHICH assertion fails.**

Run: `uv run pytest tests/test_engine_tracking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.engine.tracking'`. A later failure for a different reason means the fixture is wrong, not the code.

- [ ] **Step 3: Implement `extract_fills`.**

```python
"""The realized half of the weekly tracking comparison: what the ledger says actually happened.

Pure. Everything here reads a journal already on disk and returns numbers; nothing writes, and
nothing reaches the venue. The refusals are the point -- a tracking number nobody can stand
behind is worse than no number, because it will be read as a gate input.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from cli.engine.errors import EngineError
from cli.engine.executor import _EUR_CODES
from cli.engine.store import BASKET
from cli.logging_setup import get_logger

logger = get_logger("engine.tracking")

# The venue's own names, as `executor._liquidity` writes them. NOT lowercased: matching a casing
# the ledger never writes would abort every real fill while every fixture passed -- an
# always-refusing guard that ships green.
_LIQUIDITY = frozenset({"MAKER", "TAKER"})
_BASE_BY_SYMBOL = {symbol: symbol.split("/")[0] for symbol in BASKET}


class Fill(NamedTuple):
    at: datetime
    base: str
    qty: float
    px: float
    fee: float | None  # None when the fee is not euro-denominated
    liquidity: str


def extract_fills(records: list[dict]) -> tuple[list[Fill], list[str]]:
    """Every journaled fill, in ledger order, plus the notes that disabled part of the report.

    The pair -> base mapping happens HERE and only here: `accumulation_payload` and
    `load_minimums` are base-keyed, so a pair leaking downstream would match no floor and
    report a drift computed against nothing.
    """
    out: list[Fill] = []
    notes: list[str] = []
    for rec in records:
        for row in rec.get("submitted", []):
            symbol = (row.get("intent") or {}).get("symbol")
            base = _BASE_BY_SYMBOL.get(symbol)
            if base is None:
                raise EngineError(
                    f"submitted row {row.get('client_order_id')!r} names symbol {symbol!r}, "
                    "which is not in the basket -- refusing to map it to a floor"
                )
            for ev in row.get("events", []):
                if ev.get("event") != "fill":
                    continue
                liq = ev.get("liquidity")
                if liq not in _LIQUIDITY:
                    raise EngineError(
                        f"fill on {row.get('client_order_id')!r} carries liquidity={liq!r}, "
                        f"not one of {sorted(_LIQUIDITY)} -- refusing to blend an unlabelled side"
                    )
                cur = ev.get("fee_currency")
                fee: float | None = float(ev["fee"])
                if cur not in _EUR_CODES:
                    fee = None
                    note = f"fee on {symbol} is denominated in {cur}, not euro -- excluded from the cost blend"
                    if note not in notes:
                        notes.append(note)
                    logger.warning("%s", note)
                out.append(
                    Fill(datetime.fromisoformat(ev["at"]), base, float(ev["qty"]),
                         float(ev["px"]), fee, liq)
                )
    return out, notes
```

- [ ] **Step 4: Run to green.** `uv run pytest tests/test_engine_tracking.py -v` → 8 passed.

- [ ] **Step 5: Prove the refusals bite.** Via `infra/scripts/mutate-probe.sh`, one at a time, reading WHICH assertion fires: relax `if liq not in _LIQUIDITY` to `if False` → the two liquidity tests must fail; replace `_LIQUIDITY` with a lowercased set → `test_extract_fills_reads_the_venues_own_uppercase_liquidity` must fail; drop the `base is None` arm → the basket test must fail; replace `_EUR_CODES` with `("EUR",)` → `test_zeur_is_a_euro` must fail. Confirm the probe collects the tests first (`--collect-only`) — a `-k` filter that deselects them makes a passing probe meaningless.

- [ ] **Step 6: Commit.** `git add cli/engine/tracking.py tests/test_engine_tracking.py && git commit` — `feat(engine): the tracking report's fill reader, refusing what it cannot blend`

---

### Task 2: Realized drift, ISO weeks, and the rung boundary

**Files:**
- Modify: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: `Fill` from Task 1; `CycleStages` (`.cycle_ts`, `.final`, `.closes`) from `feeders`.
- Produces:
  - `realized_drift(stages, fills, nav) -> dict` — the SAME per-NAV block shape `accumulation_payload` returns (`{"cycles": [...], "median_drift_bps", "p95_drift_bps", "n_placed"}`), so the two halves are comparable cell by cell rather than by eye.
  - `weekly_tracking(stages, fills, minimums, nav, *, rung_by_week: dict[str, int] | None = None) -> dict` — `{"weeks": [{"iso_week": "2026-W36", "cycles": int, "complete": bool, "rung": int|None, "gate_eligible": bool, "floor_p95_bps": float, "realized_mean_bps": float|None, "within_band": bool|None}], "complete_gate_eligible_weeks": int, "verdict": "pass"|"fail"|"insufficient-data"}`.

**Why this signature:** the earlier draft passed a pre-computed floor payload alongside a separately-shaped realized one, which made the comparison a join in the caller — two shapes, two chances to align them wrongly. One function, one shape, and the per-week comparison is a subtraction.

- [ ] **Step 1: Write the failing tests.**

```python
from datetime import UTC, datetime

from cli.engine.feeders import CycleStages
from cli.engine.tracking import Fill, realized_drift, weekly_tracking

def _stage(ts, *, btc_weight=1.0, close=50000.0):
    return CycleStages(cycle_ts=datetime.fromisoformat(ts), final={"BTC": btc_weight},
                       closes={"BTC": close})

_MINIMUMS = {"BTC": (0.00005, 0.45)}

def test_held_accumulates_in_base_units_and_drift_is_measured_after_the_fill():
    # NAV 1000 at 50k -> target 0.02 BTC. A fill of exactly the target leaves zero drift.
    stages = [_stage("2026-08-31T00:00:00+00:00")]
    fills = [Fill(datetime(2026, 8, 31, 0, 1, tzinfo=UTC), "BTC", 0.02, 50000.0, 0.05, "MAKER")]
    out = realized_drift(stages, fills, 1000.0)
    assert out["cycles"][0]["drift_bps"] == 0.0

def test_a_price_move_alone_does_not_manufacture_drift():
    # The held state is base-keyed, so a pure price move re-prices target AND held together.
    # A EUR-denominated held state would report drift here, which is the defect this pins.
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00", close=60000.0)]
    fills = [Fill(datetime(2026, 8, 31, 0, 1, tzinfo=UTC), "BTC", 0.02, 50000.0, 0.05, "MAKER")]
    out = realized_drift(stages, fills, 1000.0)
    assert out["cycles"][1]["drift_bps"] == 0.0

def test_a_fill_after_the_cycle_does_not_count_toward_it():
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00")]
    fills = [Fill(datetime(2026, 8, 31, 3, 0, tzinfo=UTC), "BTC", 0.02, 50000.0, 0.05, "MAKER")]
    out = realized_drift(stages, fills, 1000.0)
    assert out["cycles"][0]["drift_bps"] > 0.0   # nothing held yet at 00:00
    assert out["cycles"][1]["drift_bps"] == 0.0  # filled before 04:00

def test_a_partial_iso_week_is_marked_and_never_carries_a_verdict():
    stages = [_stage("2026-08-31T00:00:00+00:00")]
    out = weekly_tracking(stages, [], _MINIMUMS, 1000.0)
    wk = out["weeks"][0]
    assert wk["iso_week"] == "2026-W36"
    assert wk["complete"] is False
    assert wk["within_band"] is None
    assert out["verdict"] == "insufficient-data"

def test_a_week_with_no_fills_reads_no_data_not_zero_drift():
    stages = [_stage(f"2026-08-31T{h:02d}:00:00+00:00") for h in (0, 4, 8, 12, 16, 20)]
    out = weekly_tracking(stages, [], _MINIMUMS, 1000.0)
    assert out["weeks"][0]["realized_mean_bps"] is None

def test_a_rung_2_week_is_measured_but_not_gate_eligible():
    stages = [_stage("2026-08-31T00:00:00+00:00")]
    out = weekly_tracking(stages, [], _MINIMUMS, 1000.0, rung_by_week={"2026-W36": 2})
    wk = out["weeks"][0]
    assert wk["rung"] == 2
    assert wk["gate_eligible"] is False
    assert wk["floor_p95_bps"] is not None       # still measured
    assert out["complete_gate_eligible_weeks"] == 0

def test_the_gate_needs_three_complete_eligible_weeks():
    assert weekly_tracking([_stage("2026-08-31T00:00:00+00:00")], [], _MINIMUMS, 1000.0)["verdict"] == "insufficient-data"
```

- [ ] **Step 2: Run and read WHICH assertion fails.** `uv run pytest tests/test_engine_tracking.py -v` → the seven new tests fail on `ImportError`; Task 1's eight still pass.

- [ ] **Step 3: Implement both functions.**

```python
# Imported, never re-written: `feeders` already owns the percentile convention (nearest rank,
# always an OBSERVED value), the complete-week threshold, and the ISO-week bucketing. A second
# implementation of any of them would let the floor half and the realized half disagree by a rank
# or a week boundary while both looked right.
from cli.engine.feeders import _CYCLES_PER_FULL_WEEK, _p95, _weekly_drift, accumulation_payload

_GATE_MIN_WEEKS = 3


def realized_drift(stages: list[CycleStages], fills: list[Fill], nav: float) -> dict:
    """Per-cycle drift with `held` taken from REAL fills instead of the modelled policy.

    Same shape as `accumulation_payload`'s per-NAV block on purpose: the whole comparison is
    floor-vs-realized cell by cell, and two shapes would put the alignment in the caller.

    `held` is BASE UNITS. A EUR-denominated held state would compare a price-stale held against
    a freshly priced target and report drift across a pure price move that filled nothing.
    Drift is measured AFTER the cycle's fills are applied, matching `accumulation_payload`.
    """
    if not math.isfinite(nav) or nav <= 0:
        raise EngineError(f"NAV must be finite and positive, got {nav!r} -- a negative one signs every drift_bps")
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    by_time = sorted(fills, key=lambda f: f.at)
    held: dict[str, float] = {}
    rows: list[dict] = []
    cursor = 0
    for s in ordered:
        # Every fill at or before this boundary has happened by the time this cycle is measured.
        while cursor < len(by_time) and by_time[cursor].at <= s.cycle_ts:
            f = by_time[cursor]
            held[f.base] = held.get(f.base, 0.0) + f.qty
            cursor += 1
        drift_eur = 0.0
        for a, weight in s.final.items():
            close = s.closes[a]
            target = (weight * nav) / close
            drift_eur += abs(target - held.get(a, 0.0)) * close
        rows.append({"cycle_ts": s.cycle_ts.isoformat(), "drift_bps": drift_eur / nav * 10_000,
                     "drift_eur": drift_eur})
    values = [r["drift_bps"] for r in rows]
    return {"cycles": rows,
            "median_drift_bps": statistics.median(values) if values else None,
            "p95_drift_bps": _p95(values) if values else None,
            "n_fills": len(by_time)}


def weekly_tracking(stages, fills, minimums, nav, *, rung_by_week=None) -> dict:
    """The per-ISO-week comparison rung 3's go/no-go reads: that week's floor p95 against that
    week's realized MEAN drift.

    The edge is not this function's to choose -- T0116's amendment ratified it, and on the very
    data the band was derived from a median edge fails two of four weeks while a p95 edge passes
    all four. Partial weeks carry no verdict at all: a partial week's mean is not comparable to
    a complete week's, and the four-week window makes a weekly p95 a percentile over four points.

    Both halves are bucketed by `feeders._weekly_drift` -- the same function, over the same
    `stages` -- so a week boundary can never fall in two places.
    """
    rung_by_week = rung_by_week or {}
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    floor = accumulation_payload(ordered, minimums, [nav])["by_nav"][nav]
    real = realized_drift(ordered, fills, nav)
    floor_weeks = {(w["iso_year"], w["iso_week"]): w for w in _weekly_drift(ordered, floor["cycles"])}
    real_weeks = {(w["iso_year"], w["iso_week"]): w for w in _weekly_drift(ordered, real["cycles"])}
    # The floor p95 is per-week, which `_weekly_drift` deliberately does not compute (it is a
    # weekly MEAN by design). Bucket the floor's own per-cycle rows for it, using the same key.
    floor_cycles: dict[tuple[int, int], list[float]] = {}
    for stage, row in zip(ordered, floor["cycles"], strict=True):
        iso = stage.cycle_ts.isocalendar()
        floor_cycles.setdefault((iso.year, iso.week), []).append(row["drift_bps"])

    weeks: list[dict] = []
    for key, fw in sorted(floor_weeks.items()):
        label = f"{key[0]}-W{key[1]:02d}"
        complete = not fw["partial"]
        rung = rung_by_week.get(label)
        gate_eligible = complete and rung != 2
        has_fill = any(_iso_key(f.at) == key for f in fills)
        # No fills is NOT zero drift -- an empty result is not an absent event.
        realized_mean = real_weeks[key]["mean_drift_bps"] if has_fill else None
        floor_p95 = _p95(floor_cycles[key])
        weeks.append({
            "iso_week": label, "cycles": fw["n_cycles"], "complete": complete,
            "rung": rung, "gate_eligible": gate_eligible,
            "floor_p95_bps": floor_p95, "realized_mean_bps": realized_mean,
            "within_band": (realized_mean <= floor_p95) if (gate_eligible and realized_mean is not None) else None,
        })
    decided = [w for w in weeks if w["within_band"] is not None]
    verdict = ("insufficient-data" if len(decided) < _GATE_MIN_WEEKS
               else "pass" if all(w["within_band"] for w in decided) else "fail")
    return {"weeks": weeks, "complete_gate_eligible_weeks": len(decided), "verdict": verdict}
```

`_iso_key(dt)` is the one new helper — `(dt.isocalendar().year, dt.isocalendar().week)` — and the `"YYYY-Www"` label is derived from it, never parsed back. `_CYCLES_PER_FULL_WEEK` reaches the code only through `_weekly_drift`'s `partial` flag, so the completeness threshold has exactly one definition.

- [ ] **Step 4: Run to green.** `uv run pytest tests/test_engine_tracking.py -v` → 15 passed.

- [ ] **Step 5: Prove the load-bearing arms bite.** Via `mutate-probe.sh`: change `held` to accumulate `f.qty * f.px` (a EUR-denominated held state) → `test_a_price_move_alone_does_not_manufacture_drift` must fail; change `<= s.cycle_ts` to `<= s.cycle_ts + timedelta(hours=4)` → the fill-ordering test must fail; drop the `week_fills and` guard → the no-data test must fail; set `_GATE_MIN_WEEKS = 1` → the three-week test must fail; make `gate_eligible` ignore `rung != 2` → the rung-2 test must fail.

- [ ] **Step 6: Commit.** `git add cli/engine/tracking.py tests/test_engine_tracking.py && git commit` — `feat(engine): realized weekly drift against the venue floor, base-keyed and week-complete`

---

### Task 3: The cost blend and its proposal

**Files:**
- Modify: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: `Fill` from Task 1.
- Produces: `cost_blend(fills: list[Fill], *, current: float = 0.006) -> dict` — `{"n_fills": int, "n_priced": int, "maker_share": float|None, "taker_share": float|None, "realized_fee_per_side": float|None, "current_fee_per_side": float, "proposed_fee_per_side": float|None, "basis": str}`.

**What it closes.** T0090's third next-step: *"Derive the realized maker/taker blend from real fills and re-price against it. Until then the quoted baseline is the range 0.51–0.91 conditional, not a point."* The point replaces the range. The constant it prices is `cli/portfolio/builder.py`'s `spot_fee_per_side: float = 0.006`.

**It proposes; it never applies.** Spec D4, and the owner's ruling: a human ratifies. Nothing in this task writes `builder.py`.

- [ ] **Step 1: Write the failing tests.**

```python
from cli.engine.tracking import cost_blend

def _f(liquidity, qty=1.0, px=100.0, fee=0.1):
    return Fill(datetime(2026, 8, 31, tzinfo=UTC), "BTC", qty, px, fee, liquidity)

def test_the_blend_is_share_of_NOTIONAL_not_a_count_of_fills():
    # One large taker fill and nine tiny maker ones is a taker-heavy book, and a
    # count-weighted blend would call it 90% maker and under-price the cost.
    fills = [_f("TAKER", qty=100.0)] + [_f("MAKER", qty=0.1) for _ in range(9)]
    out = cost_blend(fills)
    assert out["taker_share"] > 0.98

def test_realized_fee_per_side_is_fees_over_notional():
    out = cost_blend([_f("MAKER", qty=1.0, px=100.0, fee=0.25)])
    assert out["realized_fee_per_side"] == pytest.approx(0.0025)

def test_unpriced_fills_are_excluded_from_the_rate_but_counted():
    fills = [_f("MAKER", fee=0.1), Fill(datetime(2026, 8, 31, tzinfo=UTC), "ETH", 1.0, 100.0, None, "MAKER")]
    out = cost_blend(fills)
    assert out["n_fills"] == 2 and out["n_priced"] == 1

def test_no_priced_fills_proposes_nothing_rather_than_zero():
    out = cost_blend([Fill(datetime(2026, 8, 31, tzinfo=UTC), "ETH", 1.0, 100.0, None, "MAKER")])
    assert out["realized_fee_per_side"] is None
    assert out["proposed_fee_per_side"] is None
    assert "no euro-denominated fills" in out["basis"]

def test_the_current_constant_is_reported_beside_the_proposal():
    out = cost_blend([_f("MAKER", qty=1.0, px=100.0, fee=0.25)])
    assert out["current_fee_per_side"] == 0.006
    assert out["proposed_fee_per_side"] == pytest.approx(0.0025)
```

- [ ] **Step 2: Run and read WHICH assertion fails.** Expected: `ImportError` on `cost_blend`.

- [ ] **Step 3: Implement.**

```python
def cost_blend(fills: list[Fill], *, current: float = 0.006) -> dict:
    """The realized maker/taker blend and the fee-per-side it implies.

    Weighted by NOTIONAL, never by fill count: one large taker fill beside nine tiny maker ones
    is a taker-heavy book, and a count-weighted blend would call it 90% maker and under-price
    the cost the whole portfolio is evaluated against.

    Fills whose fee is not euro-denominated are COUNTED but not PRICED -- excluding them from
    the numerator while leaving their notional in the denominator would silently deflate the
    rate. With no priced fills at all the answer is None: a proposal of 0.0 would read as
    "trading is free" and would be ratified by someone who trusted it.
    """
    priced = [f for f in fills if f.fee is not None]
    notional = {"MAKER": 0.0, "TAKER": 0.0}
    for f in fills:
        notional[f.liquidity] += abs(f.qty) * f.px
    gross = notional["MAKER"] + notional["TAKER"]
    priced_notional = sum(abs(f.qty) * f.px for f in priced)
    realized = (sum(f.fee for f in priced) / priced_notional) if priced_notional > 0 else None
    if realized is None:
        basis = "no euro-denominated fills in the window -- no rate proposed"
    else:
        basis = f"{len(priced)} euro-denominated fill(s) over {priced_notional:,.2f} EUR of notional"
    return {
        "n_fills": len(fills), "n_priced": len(priced),
        "maker_share": (notional["MAKER"] / gross) if gross > 0 else None,
        "taker_share": (notional["TAKER"] / gross) if gross > 0 else None,
        "realized_fee_per_side": realized,
        "current_fee_per_side": current,
        "proposed_fee_per_side": realized,
        "basis": basis,
    }
```

- [ ] **Step 4: Run to green.** → 20 passed.

- [ ] **Step 5: Prove the arms bite.** Via `mutate-probe.sh`: weight the blend by `len()` instead of notional → the notional test must fail; divide by `gross` instead of `priced_notional` → the unpriced test must fail; return `0.0` instead of `None` when nothing is priced → the no-proposal test must fail.

- [ ] **Step 6: Commit.** `feat(engine): the realized maker/taker blend, notional-weighted and proposal-only`

---

### Task 4: The command, and the true-positive that proves it before rung 1

**Files:**
- Modify: `cli/engine/command.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: `weekly_tracking`, `cost_blend`, `extract_fills` from Tasks 1–3; `_window_records`, `_resolve_minimums`, `_snapshot_reader`, `_emit_report`, `replay_stages`, `load_minimums` from the repo.
- Produces: `zcrypto engine tracking-report [--journal PATH] [--since ISO] [--until ISO] [--nav FLOAT] [--minimums PATH] [--ledger-export PATH] [--simulated-fills] [--json]`.

**`--simulated-fills` is the true-positive, not a convenience.** There are zero journaled fills in existence (measured above), so without it every refusal in Tasks 1–3 could be an always-refusing guard that ships green. It replays real journaled cycles through `replay_stages`, reads each modelled placement as a fill at the journaled close, and runs the whole pipeline over them. A run that emits zero drift across the window FAILS the test rather than passing it.

- [ ] **Step 1: Write the failing tests.**

```python
from typer.testing import CliRunner
from cli.__main__ import app

runner = CliRunner()

def test_simulated_fills_produce_a_non_degenerate_report(tmp_path, real_journal_fixture):
    result = runner.invoke(app, ["engine", "tracking-report", "--journal", str(real_journal_fixture),
                                 "--simulated-fills", "--nav", "1000", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    weeks = payload["tracking"]["weeks"]
    assert weeks, "the replay produced no weeks at all"
    # A pipeline that silently zeroes everything would pass a mere "it ran" assertion.
    assert any(w["floor_p95_bps"] > 0 for w in weeks)

def test_the_verdict_is_insufficient_data_before_three_complete_weeks(tmp_path, short_journal_fixture):
    result = runner.invoke(app, ["engine", "tracking-report", "--journal", str(short_journal_fixture),
                                 "--simulated-fills", "--nav", "1000", "--json"])
    assert json.loads(result.stdout)["tracking"]["verdict"] == "insufficient-data"

def test_the_command_writes_nothing(tmp_path, real_journal_fixture):
    before = {p: p.stat().st_mtime_ns for p in real_journal_fixture.rglob("*") if p.is_file()}
    runner.invoke(app, ["engine", "tracking-report", "--journal", str(real_journal_fixture),
                        "--simulated-fills", "--nav", "1000"])
    after = {p: p.stat().st_mtime_ns for p in real_journal_fixture.rglob("*") if p.is_file()}
    assert before == after

def test_the_minimums_snapshot_stamp_is_quoted(real_journal_fixture):
    result = runner.invoke(app, ["engine", "tracking-report", "--journal", str(real_journal_fixture),
                                 "--simulated-fills", "--nav", "1000"])
    assert "minimums read" in result.stdout.lower()
```

- [ ] **Step 2: Run and read WHICH assertion fails.** Expected: `No such command 'tracking-report'`.

- [ ] **Step 3: Implement the Typer command** in `cli/engine/command.py`, following `accum-replay`'s structure exactly (it is the sibling command with the same inputs): resolve the journal, `_window_records`, `_snapshot_reader`, `replay_stages` per record, `load_minimums`, then `weekly_tracking` + `cost_blend`, then `_emit_report`. `--simulated-fills` converts each modelled placement into a `Fill` at the journaled close, labelled `"MAKER"` — the ladder is maker-first, and labelling simulated fills taker would flatter nothing but would misstate the blend the report is about to propose from.

The report's text quotes the venue-minimums snapshot stamp, exactly as `accum-replay` does: *"these floors move, so a band quoted from an older table is stale, not conservative."*

- [ ] **Step 4: Run to green.**

- [ ] **Step 5: Run it over the real pulled journal** — `/mnt/zhao-crypto/engine-journal`, read-only, never the live dir — and read the output rather than the exit code. Record the week count, the floor p95 per week, and `verdict: insufficient-data`. Zero fills exist, so the realized half must read *no data* on every week; a realized number appearing here is a defect, not a surprise.

- [ ] **Step 6: `README.md` `## Usage`** gains the subcommand and every flag, in this same commit (`readme-usage.md`).

- [ ] **Step 7: Commit.** `feat(engine): tracking-report, with the replay-as-fills true-positive`

---

### Task 5: Component B — the standing reader for the owner's Kraken ledger export

**Files:**
- Modify: `cli/engine/tracking.py`, `cli/engine/command.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Produces: `read_ledger_export(path: Path) -> list[LedgerRow]` and `reconcile_ledger(rows: list[LedgerRow], fills: list[Fill]) -> dict` — `{"matched": int, "rollover_fees_eur": float, "unmatched": list[str]}`.

**What it replaces.** T0018: *"Rung 1's rollover rows are read by hand from the owner's ledger export during the attended window; the standing reader is `00091`'s."* It reads a file the owner exports. It holds no API key, makes no venue call, and fetches nothing.

**Why it belongs to the cost component and not to a spec of its own:** a margin position's rollover fee is charged by the venue against the POSITION, not against a fill, so a cost basis built from fills alone omits it. This closes that hole in Task 3's number.

**The export's columns are an assumption until the first real export is read.** Kraken's ledger CSV is documented as `txid,refid,time,type,subtype,aclass,asset,amount,fee,balance`. The reader is header-driven and **refuses an export whose header lacks a column it needs, naming the missing column** — so a changed export format fails loudly instead of parsing into plausible nonsense. Do not "handle" a missing column with a default.

- [ ] **Step 1: Write the failing tests.**

```python
def _export(tmp_path, rows, header="txid,refid,time,type,subtype,aclass,asset,amount,fee,balance"):
    p = tmp_path / "ledgers.csv"
    p.write_text(header + "\n" + "\n".join(rows) + "\n")
    return p

def test_a_missing_column_is_refused_by_name(tmp_path):
    p = _export(tmp_path, [], header="txid,time,type,asset,amount")
    with pytest.raises(EngineError, match="fee"):
        read_ledger_export(p)

def test_rollover_rows_are_summed_as_a_cost(tmp_path):
    p = _export(tmp_path, ['"L1","R1","2026-08-31 00:00:00","rollover","","currency","ZEUR","-0.12","0.12","900.0"'])
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["rollover_fees_eur"] == pytest.approx(0.12)

def test_a_trade_row_matching_no_journaled_fill_is_reported_unmatched(tmp_path):
    # The account did something the engine's record does not know about -- which is the one
    # thing this component exists to detect. It is reported, never averaged away.
    p = _export(tmp_path, ['"L2","T-UNKNOWN","2026-08-31 00:00:00","trade","","currency","ZEUR","-50.0","0.05","850.0"'])
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["unmatched"] == ["T-UNKNOWN"]

def test_a_trade_row_matching_a_journaled_fill_reconciles(tmp_path):
    p = _export(tmp_path, ['"L3","T-1","2026-08-31 00:00:00","trade","","currency","ZEUR","-50.0","0.05","850.0"'])
    fills = [Fill(datetime(2026, 8, 31, tzinfo=UTC), "BTC", 0.001, 50000.0, 0.05, "MAKER")._replace()]
    # the Fill carries its trade_id through from the journal row
    out = reconcile_ledger(read_ledger_export(p), fills)
    assert out["matched"] == 1 and out["unmatched"] == []
```

**Note for the implementer:** `Fill` gains a `trade_id: str` field in this task (the journal already carries it — `executor._fill_payload` writes `"trade_id": str(event.trade_id)`); Task 1 dropped it because nothing needed it yet. Add the field, thread it through `extract_fills`, and update Task 1's fixtures in the same commit.

- [ ] **Step 2: Run and read WHICH assertion fails.**

- [ ] **Step 3: Implement**, header-driven, refusing on a missing required column, `csv.DictReader`. Sum `fee` over `type == "rollover"` rows; match `type == "trade"` rows to fills by `refid` against `Fill.trade_id`.

- [ ] **Step 4: Run to green.**

- [ ] **Step 5: Wire `--ledger-export PATH`** into the command from Task 4 — absent, the report simply omits the reconciliation block rather than refusing (the export is an attended artifact and most runs will not have one).

- [ ] **Step 6: Prove the refusals bite** via `mutate-probe.sh`: drop the required-column check → the missing-column test must fail; make an unmatched row a warning instead of a reported id → the unmatched test must fail.

- [ ] **Step 7: The probe checklist gains the comparison.** `infra/runbooks/engine.md`'s probe-window procedure already has the owner exporting the ledger. Add the step that runs the reader against that export **once while the hand-read still exists**, and compares the two. A standing reader that never agreed with the hand-read it replaced has not been verified.

- [ ] **Step 8: Commit.** `feat(engine): the standing ledger-export reader, refusing an export it cannot map`

---

### Task 6: Component C — the tracking-error trip (LIVE TRADE PATH — Fable review floor)

**Files:**
- Modify: `cli/engine/executor.py`, `zcrypto.toml`
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `weekly_tracking` from Task 2; `self._trip_kill(reason)` from the executor.
- Produces: an executor method that evaluates the complete-week tracking error at a cycle boundary and trips, plus a config knob `[engine] tracking_band_bps` (default **unset**).

**This is the only task in this plan that touches code running with real money.** Its review floor is **Fable**, not Opus (`spec-plan-locations.md`), and it reaches production only through a canary-gated engine converge whose gate is the secondary's capture bake (`capture-deploys.md`).

**It ships disarmed.** `tracking_band_bps` unset ⇒ the trip is configured off and renders its state, exactly as `00088`'s envelope renders a disarmed gate. There are fewer than three complete gate-eligible weeks in existence, so an armed threshold would be a guess, and a guess that pages teaches the operator to clear it.

**It evaluates on COMPLETE ISO weeks only** (spec D9), at the first boundary after a week closes — never per cycle. A partial week's mean is not comparable to a full week's band; a per-cycle trip would fire on arithmetic rather than on divergence.

- [ ] **Step 1: Write the failing tests** in `tests/test_engine_executor.py`, beside the existing trip tests.

```python
def test_an_unset_band_never_trips(executor_disarmed):
    # The default state, and the one that ships. A trip here would be a guess with a kill file.
    executor_disarmed._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_disarmed._kill_tripped is False
    assert not (exec_dir(executor_disarmed._state_dir) / KILL_FILE).exists()

def test_a_complete_week_beyond_the_band_latches_the_kill_file(executor_with_band_120):
    # THE CONSTRUCTED DEFECT. A week whose realized mean drift exceeds the configured band.
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=300.0, floor_p95_bps=120.0)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_with_band_120._kill_tripped is True
    body = (exec_dir(executor_with_band_120._state_dir) / KILL_FILE).read_text()
    assert "tracking" in body

def test_a_healthy_complete_week_does_not_trip(executor_with_band_120):
    # THE TRUE-POSITIVE. Without it an always-tripping or always-refusing guard ships green.
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=40.0, floor_p95_bps=120.0)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert executor_with_band_120._kill_tripped is False

def test_a_partial_week_never_trips_however_bad_it_looks(executor_with_band_120):
    # A partial week's mean is not comparable to a full week's band.
    _journal_a_partial_week(executor_with_band_120, realized_mean_bps=5000.0)
    executor_with_band_120._evaluate_tracking_band(_mid_week_boundary())
    assert executor_with_band_120._kill_tripped is False

def test_the_trip_is_idempotent_and_keeps_the_first_reason(executor_with_band_120):
    _journal_a_complete_week(executor_with_band_120, realized_mean_bps=300.0, floor_p95_bps=120.0)
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    first = (exec_dir(executor_with_band_120._state_dir) / KILL_FILE).read_text()
    executor_with_band_120._evaluate_tracking_band(_boundary_after_a_complete_week())
    assert (exec_dir(executor_with_band_120._state_dir) / KILL_FILE).read_text() == first
```

- [ ] **Step 2: Run and read WHICH assertion fails.** Expected: `AttributeError: _evaluate_tracking_band`.

- [ ] **Step 3: Implement.** Read the band from config; return immediately when unset. At a boundary, read the journal's own exec records for the just-closed ISO week, build fills via `extract_fills`, call `weekly_tracking`, and trip only when a **complete, gate-eligible** week reports `within_band is False`. The trip reason names the week, the realized mean, and the band. Reuse `_trip_kill` — do not write a second latch path.

- [ ] **Step 4: Run to green.**

- [ ] **Step 5: Prove the guard bites, and read WHICH failure fires.** Via `mutate-probe.sh`: remove the `complete` condition → the partial-week test must fail; invert the comparison → the healthy-week test must fail; drop the unset-band early return → the disarmed test must fail. A red exit is not enough — confirm the expected assertion is the one that fired.

- [ ] **Step 6: The operator surfaces.** `infra/runbooks/engine.md` gains a section for the trip — what the operator is seeing, what it means, what to do, and when it retires. A latched trip already pages via `zcrypto-engine-exec-kill-tripped`, so **no new alert rule is added**; adding one would double-page a single event. State that decision in the section rather than leaving it as an absence. Keep internal traceability tokens out of every operator-visible string (`operator-facing-text.md`).

- [ ] **Step 7: Commit.** `feat(engine): the tracking-error trip, disarmed until three complete weeks exist`

**Deploy note (not a plan step):** this task does not ship on merge. The engine converge is a separate, attended action inside a 4-hourly inter-cycle gap, canary-gated, from a tree whose rendered config matches the fleet (`capture-deploys.md`). If the trip publishes any new metric family, the converge is `--tags capture,engine` — the keep-list lives in the capture role.

---

### Task 7: Closeout

**Files:**
- Modify: `infra/runbooks/engine.md`, `docs/research/14.phase6-decisions.md`, `docs/iterations-history-phase6.md`

- [ ] **Step 1: The probe-window procedure gains the weekly reading** — `infra/runbooks/engine.md`'s `## engine-probe-window — PROCEDURE`, as a numbered step: the command, the ISO week to pass, and what an unproducible week means (a refusal to record, never a zero to shrug at). **This step is what makes the absent timer safe** (spec D2): there is no scheduled run, so the procedure is the only thing that compels the reading.

- [ ] **Step 2: The sleeve-composition alert's step 3 gains the realized half.** It currently sends the operator to re-derive the band and names only `accum-replay`, which is the floor half; once the realized half exists that step points at half the comparison.

- [ ] **Step 3: The decisions log** — `docs/research/14.phase6-decisions.md`, one `[iter-<N>]` entry per decision with 2–3 options and `(Decision: N)`, per `iteration-closeout`. Log D2 (command vs timer), D4 (propose vs apply), and D9 (the trip's evaluation basis).

- [ ] **Step 4: The iterations-history entry** — `docs/iterations-history-phase6.md`, per `iteration-closeout`. Written NOW, at closeout, against the full branch log — never drafted earlier (`iterations-history.md`).

- [ ] **Step 5: Re-verify every status claim this branch touched** against the branch log immediately before PR-open, and recompute any load-bearing number rather than quoting an earlier draft.

- [ ] **Step 6: Commit.** `docs(engine): 00091 closeout -- the weekly reading step, the decisions, the history`

---

## Self-review

**Spec coverage.** D1 → Task 2 (calls `accumulation_payload`, never re-derives). D2 → Task 4 (command) + Task 7 Step 1 (the procedure step that replaces the timer). D3 → Tasks 1–2 (base units, base key space, post-decision drift, complete weeks, rung-2 exclusion). D4 → Task 3 (proposal only). D5 → Tasks 1–3 (every refusal, each with a constructed defect). D6 → Task 4 Step 5 (`--simulated-fills` true-positive) and every task's mutate-probe step. D7 → Tasks 4 Step 6, 5 Step 7, 6 Step 6, 7 Steps 1–3. D8 → Task 5. D9 → Task 6.

**Placeholders.** None: every step carries the code or the exact file and text to change. Task 5's export columns are marked as an assumption with a fail-loud reader, which is a stated design choice, not a gap.

**Type consistency.** `Fill` is defined in Task 1 and gains `trade_id` in Task 5 — flagged in Task 5 with the obligation to update Task 1's fixtures in the same commit. `weekly_tracking`'s week labels are `"YYYY-Www"` strings everywhere, including `rung_by_week`'s keys. `realized_drift` returns `accumulation_payload`'s per-NAV block shape, which is what makes the comparison a subtraction.

**Verification the plan pins.** Every refusal is constructed and seen to trip (`agent-ops.md`), each mutate-probe step names WHICH assertion must fire, and Task 4 Step 5 runs the whole pipeline over the real pulled journal where the honest answer is *no data* — a realized number there is a defect.
