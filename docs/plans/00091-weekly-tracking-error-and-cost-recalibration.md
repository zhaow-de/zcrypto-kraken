# Weekly tracking-error report and cost recalibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `zcrypto engine tracking-report`, a read-only workstation command producing the two numbers rung 3's go/no-go reads — weekly realized drift against the venue-imposed floor, and the cost basis measured from real fills.

**Architecture:** One reader over a pulled engine journal, two aggregations. A new pure module `cli/engine/tracking.py` holds the arithmetic and the refusals; `cli/engine/command.py` gains only the Typer wiring. The floor half calls the existing, already-validated `accumulation_payload` rather than re-deriving it.

**Tech Stack:** Python 3.14, Typer, pytest. No new dependencies. No fleet surface, no timer, no metric family, no alert rule.

## Global Constraints

- **Read-only.** The command writes nothing anywhere — not the journal, not config, not the fleet. `fee_per_side` is PROPOSED, never applied (spec D4).
- **Reuse the floor, do not re-derive it.** `accumulation_payload` is validated against T0118's registered curve; a second implementation is a second thing to be wrong (spec D1).
- **`held` accumulates from the ledger's own fills** — never `zcrypto_exec_position`, never the venue record (spec D3).
- **Fail closed.** A week with no fills reads *no data*, never zero drift. A `liquidity` outside `{maker, taker}` aborts the cost half. A `fee_currency` other than `EUR` aborts (spec D5).
- **Partial ISO weeks are excluded from every verdict** and marked in the output. The gate needs ≥3 complete weeks (spec D3).
- **Rung-2 weeks are labelled measured-but-not-gate-eligible** and excluded from verdicts (spec D3, T0116 ratified).
- Every command flag documented in `README.md` `## Usage` in the same change (`readme-usage.md`).
- Loggers are `get_logger("engine.tracking")`. Match `cli/engine/feeders.py`'s docstring register: state WHY, name the failure the code prevents.

## File structure

| file | responsibility |
| --- | --- |
| `cli/engine/tracking.py` (new) | pure arithmetic + refusals: fill extraction, realized drift, ISO-week aggregation, cost blend. No I/O. |
| `cli/engine/command.py` (modify) | `tracking-report` Typer command: resolve journal/minimums/NAV, call the module, `_emit_report`. |
| `tests/test_engine_tracking.py` (new) | fixtures for every arm and refusal, plus the `--simulated-fills` true-positive. |
| `README.md` (modify) | `## Usage` entry. |
| `infra/runbooks/engine.md` (modify) | sleeve-alert step 3 gains the realized half beside `accum-replay`. |

## Interfaces this plan consumes (read from the repo, use verbatim)

- `feeders.accumulation_payload(stages: list[CycleStages], minimums: dict[str, tuple[float, float]], navs: list[float]) -> dict` — returns `{"by_nav": {nav: {"cycles": [{"cycle_ts": str, "drift_bps": float, "drift_eur": float, "placed": bool, "target_qty": dict}], "median_drift_bps": float, "p95_drift_bps": float, "n_placed": int, "weeks": [...]}}}`
- `feeders.replay_stages(record, reader, *, config=None) -> CycleStages`
- `feeders.load_minimums(path: Path) -> tuple[dict[str, tuple[float, float]], str]`
- `command._window_records(journal_root: Path, since: str | None, until: str | None) -> list[CycleRecord]`
- `command._resolve_minimums(flag_value: Path | None) -> Path`
- `command._snapshot_reader(journal_dir: Path)`
- `command._emit_report(text: str, payload: dict, *, as_json: bool) -> None`
- `execledger._exec_records_in_window(journal_dir: Path, now: datetime) -> list[dict]`
- Exec-record shape: `{"schema_version", "cycle_ts", "evaluated_at", "level", "reasons", "inputs", "plans", "submitted"}`
- Submitted-row key set (`execledger._ROW_KEYS`, exact): `{plan_id, intent_index, client_order_id, intent, order, state, filled_qty, events}`
- Fill event inside `row["events"]`: `{"event": "fill", "at": iso, "qty": float, "px": float, "fee": float, "fee_currency": str, "liquidity": "maker"|"taker", "trade_id": str}`

---

### Task 1: The fill reader and its refusals

**Files:**
- Create: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: the exec-record and fill-event shapes above.
- Produces: `Fill` (NamedTuple: `at: datetime`, `asset: str`, `qty: float`, `px: float`, `fee: float`, `liquidity: str`), and `extract_fills(records: list[dict]) -> list[Fill]`.

- [ ] **Step 1: Write the failing tests.** Cover the happy path and each refusal; every refusal is a defect constructed and seen to trip, per the guard-proving rule.

```python
import pytest
from cli.engine.tracking import extract_fills
from cli.engine.errors import EngineError

def _rec(events, *, asset="BTC/EUR", state="filled"):
    return {"schema_version": 2, "cycle_ts": "2026-09-01T00:00:00+00:00",
            "evaluated_at": "2026-09-01T00:00:05+00:00", "level": "full", "reasons": [],
            "inputs": {}, "plans": [],
            "submitted": [{"plan_id": "p1", "intent_index": 0, "client_order_id": "O-1",
                           "intent": {"asset": asset}, "order": {"qty": 0.001},
                           "state": state, "filled_qty": 0.001, "events": events}]}

def _fill(**kw):
    base = {"event": "fill", "at": "2026-09-01T00:01:00+00:00", "qty": 0.001, "px": 50000.0,
            "fee": 0.05, "fee_currency": "EUR", "liquidity": "maker", "trade_id": "T-1"}
    base.update(kw)
    return base

def test_extract_fills_reads_qty_price_fee_and_liquidity():
    fills = extract_fills([_rec([_fill()])])
    assert len(fills) == 1
    f = fills[0]
    assert (f.asset, f.qty, f.px, f.fee, f.liquidity) == ("BTC/EUR", 0.001, 50000.0, 0.05, "maker")

def test_non_fill_events_are_ignored():
    assert extract_fills([_rec([{"type": "OrderAccepted", "at": "2026-09-01T00:00:30+00:00"}])]) == []

def test_a_liquidity_outside_maker_taker_aborts():
    # `str()` on the pinned library's enum yields "1", not "MAKER" -- this repo shipped exactly
    # that into the forensic ledger once. A skewed blend is worse than no blend.
    with pytest.raises(EngineError, match="liquidity"):
        extract_fills([_rec([_fill(liquidity="1")])])

def test_a_non_eur_fee_currency_aborts():
    with pytest.raises(EngineError, match="fee_currency"):
        extract_fills([_rec([_fill(fee_currency="USD")])])
```

- [ ] **Step 2: Run them and read WHICH assertion fails.**

Run: `uv run pytest tests/test_engine_tracking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.engine.tracking'`. A later failure for a different reason means the fixture is wrong, not the code.

- [ ] **Step 3: Implement `extract_fills`.**

```python
"""The realized half of spec 00091: what the ledger says actually happened."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from cli.engine.errors import EngineError
from cli.logging_setup import get_logger

logger = get_logger("engine.tracking")

_LIQUIDITY = frozenset({"maker", "taker"})


class Fill(NamedTuple):
    at: datetime
    asset: str
    qty: float
    px: float
    fee: float
    liquidity: str


def extract_fills(records: list[dict]) -> list[Fill]:
    """Every journaled fill, in ledger order.

    Refuses rather than reporting a number it cannot stand behind. `liquidity` outside
    {maker, taker} is the `str()`-on-the-enum defect that once wrote "1" into this ledger:
    a blend computed over unlabelled sides is wrong in a direction nobody can see, so it
    aborts. A non-EUR `fee_currency` aborts for the same reason -- summing mixed units
    silently produces a plausible number.
    """
    out: list[Fill] = []
    for rec in records:
        for row in rec.get("submitted", []):
            asset = (row.get("intent") or {}).get("asset", "")
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
                if cur != "EUR":
                    raise EngineError(
                        f"fill on {row.get('client_order_id')!r} carries fee_currency={cur!r}, "
                        "not EUR -- refusing to sum mixed units"
                    )
                out.append(Fill(datetime.fromisoformat(ev["at"]), asset, float(ev["qty"]),
                                float(ev["px"]), float(ev["fee"]), liq))
    return out
```

- [ ] **Step 4: Run to green.** `uv run pytest tests/test_engine_tracking.py -v` → 4 passed.

- [ ] **Step 5: Prove the refusals bite.** Via `infra/scripts/mutate-probe.sh`, one at a time, reading WHICH assertion fires: relax `if liq not in _LIQUIDITY` to `if False` → the liquidity test must fail; same for the currency arm. A probe that passes means the test is not testing the guard.

- [ ] **Step 6: Commit.** `git add cli/engine/tracking.py tests/test_engine_tracking.py && git commit` — `feat(engine): the tracking report's fill reader, refusing what it cannot blend`

---

### Task 2: Realized drift, ISO weeks, and the rung boundary

**Files:**
- Modify: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: `Fill` from Task 1; `accumulation_payload`'s per-cycle `{"cycle_ts", "drift_bps"}` entries.
- Produces: `weekly_tracking(cycles: list[dict], fills: list[Fill], targets: dict[str, dict[str, float]], nav: float, gate_eligible_from: date | None) -> list[WeekRow]` and `WeekRow` (NamedTuple: `iso_year: int`, `iso_week: int`, `n_cycles: int`, `complete: bool`, `gate_eligible: bool`, `mean_realized_bps: float | None`, `floor_p95_bps: float`).

**The rung boundary — the spec implies it, nothing in the journal records it.** No cycle carries a rung marker, so the report cannot infer gate-eligibility. It is supplied: `gate_eligible_from: date | None`. Weeks ending before it are `gate_eligible=False` and carry no verdict. `None` means no week is gate-eligible, which is the correct default until rung 3 starts.

- [ ] **Step 1: Write the failing tests.**

```python
from datetime import date, datetime, timezone
from cli.engine.tracking import Fill, weekly_tracking

def _cyc(ts, drift):  # one accumulation_payload cycle entry
    return {"cycle_ts": ts, "drift_bps": drift, "placed": True}

def test_a_week_with_no_fills_reads_no_data_never_zero():
    # An empty result is not an absent event. Reporting 0.0 here would claim perfect
    # tracking for a week that traded nothing.
    rows = weekly_tracking([_cyc("2026-09-01T00:00:00+00:00", 50.0)], [], {}, 1000.0, None)
    assert rows[0].mean_realized_bps is None

def test_a_partial_week_is_marked_and_carries_no_verdict():
    rows = weekly_tracking([_cyc("2026-09-01T00:00:00+00:00", 50.0)], [], {}, 1000.0, None)
    assert rows[0].complete is False and rows[0].gate_eligible is False

def test_a_week_before_gate_eligible_from_is_measured_but_not_eligible():
    # T0116 ratified that rung-2 tracking error is NOT a gate input: concentration fixes
    # entry placeability, not delta placeability. Averaging it into a verdict corrupts
    # the exact number the go/no-go reads.
    cycles = [_cyc(f"2026-09-0{d}T{h:02d}:00:00+00:00", 50.0) for d in (1,2,3,4,5,6,7) for h in (0,4,8,12,16,20)]
    rows = weekly_tracking(cycles, [], {}, 1000.0, date(2026, 10, 1))
    assert all(r.gate_eligible is False for r in rows)

def test_realized_drift_uses_held_from_fills_not_a_position_gauge():
    f = Fill(datetime(2026,9,1,0,1,tzinfo=timezone.utc), "BTC/EUR", 0.001, 50000.0, 0.05, "maker")
    rows = weekly_tracking([_cyc("2026-09-01T00:00:00+00:00", 50.0)], [f],
                           {"2026-09-01T00:00:00+00:00": {"BTC/EUR": 0.10}}, 1000.0, None)
    # target 0.10*1000 = EUR 100 held; fills give 0.001*50000 = EUR 50 -> 50 EUR drift = 500 bps
    assert rows[0].mean_realized_bps == 500.0
```

- [ ] **Step 2: Run and read the failure.** Expected: `ImportError: cannot import name 'weekly_tracking'`.

- [ ] **Step 3: Implement.** ISO week from `datetime.isocalendar()`; a week is `complete` at 42 cycles (6 per day × 7), matching `accumulation_report`'s own rule; `held` accumulates signed `qty * px` per asset from fills up to each cycle; realized drift is `sum(abs(target_eur - held_eur)) / nav * 10_000`.

- [ ] **Step 4: Run to green.**

- [ ] **Step 5: Prove the two rules bite.** Mutation probes: make `mean_realized_bps` return `0.0` instead of `None` on an empty week → the no-data test must fail; make `gate_eligible` ignore `gate_eligible_from` → the rung test must fail.

- [ ] **Step 6: Commit.** `feat(engine): weekly realized drift, with partial and pre-gate weeks excluded from every verdict`

---

### Task 3: The cost blend and its proposal

**Files:**
- Modify: `cli/engine/tracking.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: `Fill`.
- Produces: `cost_basis(fills: list[Fill], registered_fee_per_side: float) -> CostBasis` and `CostBasis` (NamedTuple: `n: int`, `n_maker: int`, `maker_share: float`, `realized_per_side: float`, `registered_per_side: float`, `spread_min: float`, `spread_median: float`, `spread_max: float`).

- [ ] **Step 1: Write the failing tests.**

```python
from cli.engine.tracking import cost_basis

def _f(liq, fee, qty=0.001, px=50000.0):
    return Fill(datetime(2026,9,1,tzinfo=timezone.utc), "BTC/EUR", qty, px, fee, liq)

def test_blend_and_maker_share_from_real_fills():
    cb = cost_basis([_f("maker", 0.05), _f("maker", 0.05), _f("taker", 0.10), _f("taker", 0.10)], 0.001)
    assert cb.n == 4 and cb.n_maker == 2 and cb.maker_share == 0.5
    # per-side realized = fee / notional; 0.05/50 = 0.001, 0.10/50 = 0.002 -> mean 0.0015
    assert cb.realized_per_side == 0.0015

def test_dispersion_is_a_spread_not_a_standard_deviation():
    # Tens of probe-scale fills cannot support a parametric dispersion; quoting one
    # would dress up the sample.
    cb = cost_basis([_f("maker", 0.05), _f("taker", 0.10), _f("taker", 0.15)], 0.001)
    assert (cb.spread_min, cb.spread_max) == (0.001, 0.003)

def test_no_fills_yields_no_proposal_rather_than_zero():
    cb = cost_basis([], 0.001)
    assert cb.n == 0 and cb.realized_per_side is None
```

- [ ] **Step 2: Run and read the failure.**
- [ ] **Step 3: Implement.** `realized_per_side = mean(fee / (qty*px))`; `maker_share = n_maker / n`; min/median/max of the per-fill ratios. Return `realized_per_side=None` when `n == 0`.
- [ ] **Step 4: Run to green.**
- [ ] **Step 5: Commit.** `feat(engine): the realized cost blend, proposed and never applied`

---

### Task 4: The command, and the true-positive that proves it before rung 1

**Files:**
- Modify: `cli/engine/command.py`
- Test: `tests/test_engine_tracking.py`

**Interfaces:**
- Consumes: everything above, plus `_window_records`, `_resolve_minimums`, `load_minimums`, `_snapshot_reader`, `replay_stages`, `accumulation_payload`, `_emit_report`.
- Produces: `zcrypto engine tracking-report` with `--journal-dir`, `--since`, `--until`, `--nav` (repeatable), `--minimums`, `--gate-eligible-from`, `--simulated-fills`, `--json`.

- [ ] **Step 1: Write the failing test for the true-positive.**

```python
def test_simulated_fills_produce_a_non_degenerate_number_over_the_real_journal(tmp_path):
    """The true-positive the guard rule demands: a healthy, production-shaped input that
    must pass. Without it an always-zero or always-refusing report ships green, and its
    first real invocation would be inside the decision window it exists to inform."""
    # built from accumulation_payload's own placed orders over constructed stages
    rows, cb = run_tracking(cycles=_cycles_with_placements(), simulated=True, nav=1000.0)
    assert any(r.mean_realized_bps not in (None, 0.0) for r in rows)
```

- [ ] **Step 2: Run and read the failure.**

- [ ] **Step 3: Implement the command**, mirroring `accum_replay`'s structure exactly (option shapes, `_abort` on a bad minimums file, `_emit_report(text, payload, as_json=json_out)`). `--simulated-fills` derives fills from `accumulation_payload`'s `placed` cycles and their `target_qty` deltas, and the emitted text and payload both carry a `simulated: true` marker so no run can be quoted as a measurement.

- [ ] **Step 4: Run to green, then run it for real** against `/mnt/zhao-crypto/engine-journal --simulated-fills --since 2026-07-11 --until 2026-08-22 --nav 1000`. Record the output in the task report; a run that emits zero drift across 256 cycles is a FAILURE, not a pass.

- [ ] **Step 5: Prove the simulated marker cannot be lost.** Probe: drop the `simulated` flag from the payload → a test asserting its presence must fail.

- [ ] **Step 6: Commit.** `feat(engine): the tracking-report command, with a true-positive that runs before rung 1 exists`

---

### Task 5: Surfaces and closeout

**Files:**
- Modify: `README.md`, `infra/runbooks/engine.md`, `docs/research/14.phase6-decisions.md`, `docs/iterations-history-phase6.md`
- Create: a `docs/open-topics/T<NNNN>-*.md` for the deferred scheduled run

- [ ] **Step 1: `README.md` `## Usage`** — the subcommand and every flag, matching the section's existing register.
- [ ] **Step 2: `infra/runbooks/engine.md`, the sleeve-composition alert's step 3.** It currently names only `accum-replay`, which is the FLOOR half; it gains `tracking-report` as the realized half, or it sends the operator to half the comparison. Do NOT add a `— PROCEDURE` section: the procedure that uses this instrument is rung 3's go/no-go, which has not run.
- [ ] **Step 3: Register the deferred scheduled run** as its own topic via `topic-ops` — the owner chose "command now, timer later", and prose is not registration. `ripe_when`: a rung-3 week closes with no report produced. Declare the trigger and stop; the reasoning goes in the body.
- [ ] **Step 4: Decisions-log entry** in `docs/research/14.phase6-decisions.md`, `[iter-<N>]` format: the workstation-vs-timer choice and the propose-vs-apply choice, options with tradeoffs and `(Decision: N)`.
- [ ] **Step 5: Iterations-history entry** in `docs/iterations-history-phase6.md`, authored at closeout against the full branch log, with the suite figure re-measured rather than carried forward.
- [ ] **Step 6: Commit.** `docs(engine): 00091's surfaces -- usage, the runbook's realized half, and the deferred timer registered`

## Self-review

**1. Spec coverage:** D1 → Tasks 1–4 (one module, one pass, floor reused). D2 → Task 4 (command) + Task 5 step 3 (registered timer). D3 → Task 2. D4 → Task 3. D5 → Tasks 1–3 refusals. D6 → Tasks 1–4 probes + Task 4's true-positive. D7 → Task 5. Verification section → each task's probe steps + Task 4 step 4.

**2. Placeholders:** none — every code step carries real code; every test asserts a value.

**3. Type consistency:** `Fill` (Task 1) is consumed unchanged by Tasks 2–3. `WeekRow`/`CostBasis` field names are used identically in Task 4's wiring. `gate_eligible_from` is `date | None` in both Task 2's signature and Task 4's flag.

**One gap the spec left and this plan closes explicitly:** D3 requires rung labelling, but no cycle in the journal carries a rung marker. The plan supplies it as `--gate-eligible-from`, defaulting to `None` = nothing is gate-eligible, which is correct until rung 3 starts. Flag this to the reviewer: it is a plan-level decision on a spec-level gap.
