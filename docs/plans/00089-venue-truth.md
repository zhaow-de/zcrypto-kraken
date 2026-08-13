# 00089 — Venue Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the engine a read-only, journaled view of venue truth — the instrument map, constraint sizing, held positions/balances, per-cycle realized-state artifact, and basket concordance — plus the two fired-trigger passengers (T0130 build identity, T0134 caplog fix).

**Architecture:** A frozen `VenueState` snapshot is taken from the Nautilus Cache at the cycle boundary (the only new Nautilus-touching code) and passed through a new injectable seam into `run_cycle`, which journals it as `venue-HH.json` (the `execledger.py` pattern) with a runtime concordance verdict. Repo-side, a test pins the traded basket against the committed universe doc with a ruled-exceptions baseline. A `zcrypto_venue_*` gauge family rides the existing metrics sink.

**Tech Stack:** Python 3.14, nautilus-trader 1.230.0, prometheus_client, pytest; Alloy keep-list on the capture hosts; GitHub Actions + Docker for T0130's build identity.

## Global Constraints

- **Read-only, provable:** nothing calls `size_order` from any production path, and `run_cycle`'s outputs (targets, orders, journal record content other than the new `venue-HH.json`) are IDENTICAL with and without a `VenueState` — pinned by test (Task 4), not asserted.
- **The traded basket is record 44's ten EUR legs** (`cli/engine/store.py::PAIR_KEYS`, base-keyed). Nothing in this plan changes it; the concordance baseline's ruled exceptions cite [[T0137]].
- **The Stage-6a gate must stay blind to the new artifact:** `_journal_artifacts` filters on the `cycle-` prefix; `venue-HH.json` must be structurally invisible, proven by test the way `exec-HH.json`'s invisibility was.
- **Metric admission travels both directions in the same change:** the capture-host Alloy keep-regex (`infra/ansible/roles/capture/files/config.alloy:147`, one `regex` line of explicit names) AND the watched-or-excluded guard (`tests/test_infra_alert_rules.py` derives the admitted set from that regex; every name must be queried by a rule in `infra/grafana/alerts.yaml` or excluded in `NOT_A_FAULT_SIGNAL` with a written reason). The published→admitted direction is `tests/test_infra_alloy_series.py`. A gauge that publishes but is not admitted silently vanishes from Cloud; never-published-at-all is caught only by the deploy-time value check.
- **Operator-facing text carries no internal tokens** (`T<NNNN>`, spec serials, `iter-<N>`) — metric HELP strings are in scope; `tests/test_internal_terms_not_operator_visible.py` enforces.
- Python 3.14 / PEP 758: unparenthesized `except A, B:` is valid — do not "fix" it.
- Tests make **no network calls**; Nautilus imports stay out of every test file except `tests/test_engine_venuestate.py` and the existing node tests.
- Commit gate `uv run pre-commit run -a` to clean; stage by explicit path; implementers run **targeted test files only**, never the full suite.

## File Structure

| File | Responsibility |
| --- | --- |
| `cli/engine/instruments.py` | *create* — asset→`InstrumentId` map (ten legs) + the pure `size_order` function |
| `cli/engine/venuestate.py` | *create* — `InstrumentConstraints` + `VenueState` frozen dataclasses; `venue_state_from_cache` (the only new Nautilus-touching code) |
| `cli/engine/venueledger.py` | *create* — `venue-HH.json` writer/reader, `VENUE_SCHEMA_VERSION = 1`, `_PREFIX = "venue"` |
| `cli/engine/cycle.py` | *modify* — `run_cycle(..., venue_state=None)` seam; write the venue record FIRST; `_code_version()`; `CycleResult.venue` summary |
| `cli/engine/node.py` | *modify* — `snapshot_fn` plumbing through `on_start_logic`/`on_alert_logic`/`_invoke_cycle`; `ShadowStrategy._snapshot_venue_state` |
| `cli/engine/command.py` | *modify* — `VenueGauges` (the `ExecGauges` pattern) updated from the existing sink |
| `.github/workflows/capture-image.yml` + `infra/docker/Dockerfile` | *modify* — T0130: `GIT_REVISION` build-arg → `ENV ZCRYPTO_BUILD_REVISION` |
| `infra/ansible/roles/capture/files/config.alloy` | *modify* — admit the four `zcrypto_venue_*` names to the keep-regex |
| `infra/grafana/alerts.yaml` | *modify* — the two venue rules (concordance failures, snapshot staleness); additive, no prune owed |
| `tests/test_engine_instruments.py`, `tests/test_engine_venuestate.py`, `tests/test_engine_venueledger.py`, `tests/test_basket_concordance.py` | *create* |
| `tests/test_engine_cycle.py`, `tests/test_engine_node.py`, `tests/test_engine_metrics.py` (T0134 fix + gauge tests), `tests/test_infra_alert_rules.py` | *modify* — find the real files first; do not create parallel ones |
| Closeout: `docs/iterations-history-phase6.md`, `docs/research/14.phase6-decisions.md`, T0130 + T0134 archive moves, `docs/open-topics/README.md`, the `00089` row in `docs/open-topics/T0018-phase6-build-sequence.md` | *modify* (Task 9 only) |

---

### Task 1: The instrument map and the pure sizing function

**Files:** Create `cli/engine/instruments.py`, `tests/test_engine_instruments.py`.

**Interfaces:**
- Produces: `INSTRUMENT_IDS: dict[str, str]` — base → `"BASE/EUR.KRAKEN"`, derived from `cli.engine.store.PAIR_KEYS` keys, exactly ten entries.
- Produces: `InstrumentConstraints` is Task 2's — this task defines `size_order(target_qty: float, reference_price: float, *, ordermin: float, costmin: float, lot_step: float, tick_size: float) -> SizedOrder | BelowMinimum` with frozen dataclasses `SizedOrder(qty: float, price: float, notional: float)` and `BelowMinimum(reason: str)`. Both quantizations happen here so `00090` inherits ONE proven function: qty floors to `lot_step`, the reference price floors to `tick_size`, and `notional = qty * price` (the quantized pair) feeds the `costmin` check.

- [ ] **Step 1: Probe the adapter's instrument-ID normalization BEFORE pinning the map** — Kraken spells bitcoin XBT and doge XDG (`cli/ohlc/fetch.py`), and the one measured example (`ADA/EUR.KRAKEN`, `cli/engine/node.py`) is alias-free, so it proves nothing about BTC/DOGE. Inspect the installed adapter's instrument provider (`uv run python - <<'PY'` over `nautilus_trader.adapters.kraken` — find the symbol-normalization code and print what XBTEUR/XDGEUR become). If the adapter preserves venue aliases, the map's VALUES are `XBT/EUR.KRAKEN`/`XDG/EUR.KRAKEN` while the KEYS stay our bases (`BTC`, `DOGE`) — adjust the test's expected literals to the probe's answer and record the probe output in the task report. Guessing here costs a second engine converge on the trade-key host.
- [ ] **Step 2: Write the failing tests** (literals per the Step 1 probe)

```python
from cli.engine.instruments import INSTRUMENT_IDS, BelowMinimum, SizedOrder, size_order


def test_instrument_ids_cover_exactly_the_ratified_basket():
    from cli.engine.store import PAIR_KEYS

    assert set(INSTRUMENT_IDS) == set(PAIR_KEYS)
    assert INSTRUMENT_IDS["BTC"] == "BTC/EUR.KRAKEN"
    assert all(v == f"{base}/EUR.KRAKEN" for base, v in INSTRUMENT_IDS.items())


def test_sizing_floors_qty_to_the_lot_step_and_price_to_the_tick():
    r = size_order(0.1234567, 100.007, ordermin=0.01, costmin=0.5, lot_step=0.0001, tick_size=0.01)
    assert isinstance(r, SizedOrder)
    assert r.qty == 0.1234  # floored, never rounded up past the target
    assert r.price == 100.0  # tick-misaligned reference price floors to the tick
    assert r.notional == r.qty * r.price


def test_one_lot_below_ordermin_is_below_minimum():
    r = size_order(0.0099, 100.0, ordermin=0.01, costmin=0.0, lot_step=0.0001, tick_size=0.01)
    assert isinstance(r, BelowMinimum)
    assert "ordermin" in r.reason


def test_a_cent_below_costmin_is_below_minimum():
    # qty clears ordermin; cost 4.99 sits under costmin 5.00
    r = size_order(0.0499, 100.0, ordermin=0.01, costmin=5.0, lot_step=0.0001, tick_size=0.01)
    assert isinstance(r, BelowMinimum)
    assert "costmin" in r.reason


def test_flooring_can_push_a_passing_target_below_ordermin():
    # target 0.0199 clears ordermin 0.011 -- but at lot_step 0.01 it floors to 0.01, which
    # does NOT. The ordermin check must run on the FLOORED qty, or an unfillable order passes.
    r = size_order(0.0199, 100.0, ordermin=0.011, costmin=0.0, lot_step=0.01, tick_size=0.01)
    assert isinstance(r, BelowMinimum)
```

- [ ] **Step 3: Run to verify they fail** — `uv run pytest tests/test_engine_instruments.py -v` → import error.
- [ ] **Step 4: Implement** — the map by comprehension over `PAIR_KEYS` (with the probe-confirmed alias overrides where the venue form differs); `size_order` floors `target_qty` to `lot_step` and `reference_price` to `tick_size` via `math.floor(x / step) * step` (guard both steps `> 0`), checks the FLOORED qty against `ordermin`, then `qty * floored_price` against `costmin`, in that order, reasons naming the failing constraint and both numbers.
- [ ] **Step 5: Run to green**, then `uv run pre-commit run -a`, stage `cli/engine/instruments.py tests/test_engine_instruments.py`, commit `feat(engine): the instrument map and the pure constraint-sizing function`.

### Task 2: `VenueState` and the Cache reader

**Files:** Create `cli/engine/venuestate.py`, `tests/test_engine_venuestate.py`.

**Interfaces:**
- Produces: `InstrumentConstraints(base: str, instrument_id: str, ordermin: float, costmin: float, lot_step: float, tick_size: float)` — frozen.
- Produces: `VenueState(snapshot_at: datetime, instruments: dict[str, InstrumentConstraints], positions: dict[str, float], balances: dict[str, float])` — frozen; `to_payload() -> dict` (JSON-ready, ISO timestamps).
- Produces: `venue_state_from_cache(cache, *, clock) -> VenueState` — reads the ten `INSTRUMENT_IDS` from the Cache, open positions (signed base qty per base), account balances (currency code → free balance as float). Raises on any read failure — the CALLER (Task 5's strategy hook) converts to `None`.
- Produces: `ConcordanceVerdict(ok: bool, failures: tuple[str, ...])` frozen + `runtime_concordance(state: VenueState) -> ConcordanceVerdict` — for each of the ten bases: instrument present, `ordermin/costmin/lot_step/tick_size` all `> 0`; failure strings `"BASE: <what>"`. Lives here (it judges a `VenueState`), so Task 3 consumes the real type and Task 4 only wires.

- [ ] **Step 1: Probe the real Cache API before writing anything** — the exact accessor names on nautilus 1.230.0 are load-bearing and must not be guessed:

```bash
uv run python - <<'PY'
from nautilus_trader.cache.cache import Cache
for name in ("instrument", "instruments", "positions_open", "position", "accounts", "account_for_venue"):
    print(name, hasattr(Cache, name))
import inspect
print(inspect.signature(Cache.instrument))
print(inspect.signature(Cache.positions_open))
print(inspect.signature(Cache.account_for_venue))
PY
```

Record the output in the task report. Kraken instrument objects carry `min_quantity` (ordermin), `min_notional` (costmin), `size_increment` (lot), `price_increment` (tick) — verify the attribute names on the loaded class the same way (`nautilus_trader.model.instruments.CurrencyPair`) and use what the probe shows, not what this plan guesses. Extend the probe to the **Position and Account surfaces** the reader traverses (signed base qty per position; currency code → free balance on the account object) — the scripted probe above covers only Cache accessors and instrument attributes, and those two object shapes are equally load-bearing.

- [ ] **Step 2: Write the failing tests** — construct fakes with the probed attribute shapes (plain `SimpleNamespace` stand-ins; this file is the ONE test file allowed to import Nautilus, but prefer fakes so the tests document the consumed surface):

```python
def test_venue_state_freezes_the_ten_legs(fake_cache):
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert set(vs.instruments) == set(INSTRUMENT_IDS)
    assert vs.snapshot_at == FIXED_NOW
    with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
        vs.snapshot_at = FIXED_NOW  # frozen


def test_a_missing_instrument_raises_rather_than_silently_narrowing(fake_cache_missing_dot):
    with pytest.raises(EngineError, match="DOT"):
        venue_state_from_cache(fake_cache_missing_dot, clock=lambda: FIXED_NOW)


def test_payload_round_trips_to_json():
    payload = make_venue_state().to_payload()
    assert json.loads(json.dumps(payload)) == payload
```

- [ ] **Step 3: Run to failure, implement, run to green.** Missing instrument → `EngineError` naming the base (fail loud at the read; the strategy layer decides degradation). Decimal fields cast to float at the freeze — the artifact is evidence, not an order.
- [ ] **Step 4: Gate, stage, commit** `feat(engine): VenueState -- the frozen venue-truth snapshot and its cache reader`.

### Task 3: The venue ledger

**Files:** Create `cli/engine/venueledger.py`, `tests/test_engine_venueledger.py`.

**Interfaces:**
- Produces: `VENUE_SCHEMA_VERSION = 1`, `venue_record_path(journal_dir, cycle_ts) -> Path` (day-dir / `venue-HH.json`), `write_venue_record(journal_dir, cycle_ts, *, state: VenueState | None, concordance: ConcordanceVerdict | None, code_version: str, error: str | None = None) -> Path`, `read_venue_record(path) -> dict`. Mirror `cli/engine/execledger.py` exactly in shape — read it first.
- Consumes: Task 2's `VenueState.to_payload()` and `ConcordanceVerdict` (serialized as `{"ok": bool, "failures": [str, ...]}`).

- [ ] **Step 1: Failing tests** — a success record round-trips (`schema_version`, `cycle_ts`, `code_version`, `state`, `concordance`, `status: "ok"`); an error record (`state=None, error="..."`) writes `status: "error"` with the reason and NO state key; and the gate-invisibility pin:

```python
def test_venue_records_are_invisible_to_the_stage6a_gate(tmp_path):
    """`_journal_artifacts` filters on the `cycle-` prefix; a venue record parked in the same
    day-dir must never be parsed as a boundary -- the property exec-HH.json proved, re-proved
    for this prefix."""
    from cli.engine.command import _journal_artifacts
    day = tmp_path / "2026-08-13"; day.mkdir()
    (day / "venue-08.json").write_text("{}")
    (day / "cycle-08.json").write_text(json.dumps(VALID_MINIMAL_CYCLE))
    arts = _journal_artifacts(tmp_path)
    assert [p.name for p in arts] == ["cycle-08.json"]
```

(The sketch's arity is wrong on purpose-of-illustration: the real signature is `_journal_artifacts(journal_dir, pattern, name_glob) -> list[tuple[datetime, Path]]` at `cli/engine/command.py:108`. Do not write a parallel fixture — EXTEND the two existing exec pins in `tests/test_engine_execledger.py`: `test_exec_records_are_invisible_to_every_journal_glob` (carries the non-vacuity guard) and the looser-glob canary `test_the_exec_prefix_would_be_swept_up_by_a_looser_glob`, parametrizing both over the `venue-` prefix.)

- [ ] **Step 2–3: red → implement → green.** Writer never raises on serialization of a well-formed input; a `state=None` with no `error` is a programming error → `ValueError`.
- [ ] **Step 4: Gate, stage, commit** `feat(engine): the venue ledger -- venue-HH.json beside the cycle record`.

### Task 4: Runtime concordance + the `run_cycle` seam

**Files:** Modify `cli/engine/cycle.py`; modify `tests/test_engine_cycle.py`.

**Interfaces:**
- Consumes: Task 2's `runtime_concordance` and `ConcordanceVerdict`; Task 3's `write_venue_record`.
- Produces: `run_cycle(cycle_ts, *, config, fetch_fn=fetch_ohlc, clock=_utc_now, venue_state: VenueState | None = None)`.
- Produces: `_code_version() -> str` in `cycle.py` — `version("zcrypto")` plus `+{ZCRYPTO_BUILD_REVISION[:12]}` when that env var is non-empty (T0130, D8). Replace the literal at `cli/engine/cycle.py:413` (`code_version=version("zcrypto")`) with a call.
- Produces: `CycleResult.venue: dict | None` — the summary the metrics sink reads (`{"loaded": int, "expected": len(INSTRUMENT_IDS), "failures": int, "snapshot_at": iso-str}` — expected DERIVED, never a literal; tests assert `== 10`), `None` when no snapshot.

- [ ] **Step 1: Failing tests**, the three load-bearing ones first:

```python
def test_venue_record_is_written_first_and_survives_a_failing_cycle(...):
    """The record lands BEFORE target computation, so a cycle that dies later still leaves
    the venue evidence for the boundary."""
    # run_cycle with a fetch_fn that raises; assert venue-HH.json exists with status ok,
    # while cycle-HH.json is absent.


def test_targets_are_identical_with_and_without_venue_state(...):
    """THE read-only pin: venue truth is journaled, never consulted. Two runs, same inputs,
    one with an ADVERSARIAL VenueState -- ordermin/costmin set ABOVE every order the fixture
    produces, positions/balances that would change targets if netted -- final_targets, orders,
    and the journaled cycle-HH.json byte-identical, full stop; only CycleResult.venue differs.
    A permissive VenueState would pass even if the cycle consulted it, proving nothing."""


def test_no_snapshot_writes_an_error_record_and_the_cycle_proceeds(...):
    # venue_state=None -> venue-HH.json status=error, cycle completes, CycleResult.venue is None.


def test_code_version_composes_the_build_revision(monkeypatch):
    monkeypatch.setenv("ZCRYPTO_BUILD_REVISION", "0daa2c12aaaaabbbbbcccc")
    assert _code_version().endswith("+0daa2c12aaaa")
    monkeypatch.delenv("ZCRYPTO_BUILD_REVISION")
    assert "+" not in _code_version()
```

- [ ] **Step 2–3: red → implement → green.** Write order inside `run_cycle`: compute concordance (or error) → `write_venue_record` → everything existing, unchanged. The venue record's `code_version` and the cycle record's come from the same `_code_version()`.
- [ ] **Step 4: Gate, stage, commit** `feat(engine): the venue_state seam -- journaled first, never consulted`.

### Task 5: The strategy snapshot hook

**Files:** Modify `cli/engine/node.py`, `tests/test_engine_node.py`.

**Interfaces:**
- `_invoke_cycle(run_cycle_fn, cycle_ts, config, snapshot_fn)` — calls `snapshot_fn()` inside its own try (a snapshot failure logs and passes `None`; it must never cost the boundary), then `run_cycle_fn(cycle_ts, config=config, venue_state=...)`.
- `on_start_logic(..., snapshot_fn=lambda: None)` / `on_alert_logic(..., snapshot_fn=lambda: None)` — pure functions stay pure; the default keeps every existing test valid.
- `ShadowStrategy._snapshot_venue_state(self)` — `venue_state_from_cache(self.cache, clock=...)` wrapped so any exception logs (`logger.exception`) and returns `None`; passed as `snapshot_fn` from `on_start`/the alert handler.

- [ ] **Step 1: Failing tests** — the pure-logic ones with a recording fake: `on_alert_logic` passes the snapshot product into `run_cycle_fn`; a raising `snapshot_fn` still invokes `run_cycle_fn` with `venue_state=None` (assert from the fake's captured kwargs, and assert the exception was logged); `ShadowStrategy` wires its own hook. The node test harness is `_recorders`/`FakeClock` (`tests/test_engine_node.py:118,222`) — extend it, don't rebuild; note its recording `run_fn(cycle_ts, *, config)` fakes must gain the `venue_state` kwarg or every existing pure-logic test breaks on the new pass-through.
- [ ] **Step 2–3: red → green.**
- [ ] **Step 4: Gate, stage, commit** `feat(engine): the boundary snapshot hook -- venue truth crosses at the alert, degrades to None`.

### Task 6: The repo-side basket concordance test

**Files:** Create `tests/test_basket_concordance.py`. **No production file.**

- [ ] **Step 1: Write the test (passes immediately — it pins today's ruled state; TDD's red leg is the mutation probe below):**

```python
"""The basket-vs-universe concordance pin (spec 00089 D2/D5; the ruled baseline is T0137's).

The traded basket is record 44's ten EUR legs, a code constant. The committed universe doc
carries the selection. This test is the ONLY place the two meet: a future regeneration that
shifts selection turns it red and forces a conscious edit of the ruled baseline -- divergence
can never again arrive silently, and the engine host never reads the universe artifact.
"""
import re
from pathlib import Path

_DOC = Path(__file__).resolve().parent.parent / "docs" / "universe" / "point-in-time-universe.md"

# The ruled exceptions -- each owned by T0137; editing either side without a ruling is the
# drift this test exists to catch.
RULED_TRADED_BUT_DESELECTED = {"DOT/EUR"}
RULED_SELECTED_BUT_UNREACHABLE = {"ETH/BTC", "SOL/BTC"}


def _selected() -> set[str]:
    text = _DOC.read_text()
    block = text.split("## Selected universe")[1].split("##")[0]
    symbols = {s.strip() for s in block.strip().split(",")}
    assert all(re.fullmatch(r"[A-Z]+/[A-Z]+", s) for s in symbols), symbols
    return symbols


def test_the_basket_and_the_universe_diverge_exactly_as_ruled():
    from cli.engine.store import PAIR_KEYS

    basket = {f"{base}/EUR" for base in PAIR_KEYS}
    selected = _selected()
    assert basket - selected == RULED_TRADED_BUT_DESELECTED, (
        "the traded basket carries symbols the universe no longer selects, beyond the ruled "
        "baseline -- a T0137 re-ratification decision, not an edit to this constant"
    )
    assert selected - basket == RULED_SELECTED_BUT_UNREACHABLE, (
        "the universe selects symbols the basket cannot express, beyond the ruled baseline -- "
        "T0137 owns whether the multi-quote solve makes them reachable"
    )
```

- [ ] **Step 2: Run — expect PASS** (it pins the present). Then **prove it bites** with two probes via `infra/scripts/mutate-probe.sh`: (a) edit the doc's selected line to re-add `DOT/EUR` → red; (b) drop `"DOT/EUR"` from the ruled baseline → red. Record both KILLED verdicts in the task report — control proven, tree restored.
- [ ] **Step 3: Gate, stage, commit** `test(engine): pin basket-vs-universe divergence to the T0137 ruled baseline`.

### Task 7: Venue gauges + Alloy admission

**Files:** Modify `cli/engine/command.py`, `tests/test_engine_metrics.py`, `infra/ansible/roles/capture/files/config.alloy`, `tests/test_infra_alert_rules.py`.

- [ ] **Step 1: Read how `zcrypto_exec_*` entered the keep-list** — it is ONE `regex = "..."` line (`config.alloy:147`), entered as **explicit names**; mirror that, never a wildcard. The admitted set in `tests/test_infra_alert_rules.py` is *derived* from that regex by `_admitted_series()` — there is no hand-list to edit; what you WILL edit is `NOT_A_FAULT_SIGNAL` (the exclusions with written reasons). The published→admitted direction is guarded by `tests/test_infra_alloy_series.py` (tree-derived), which goes green automatically once the keep-regex carries the four names — run it in Step 5 anyway.
- [ ] **Step 2: Failing tests** in `tests/test_engine_metrics.py`: the four gauges exist after seeding (`zcrypto_venue_snapshot_timestamp_seconds`, `zcrypto_venue_instruments_loaded`, `zcrypto_venue_instruments_expected` seeded to `10`, `zcrypto_venue_concordance_failures` seeded to `0`); a sink update from a `CycleResult` carrying `venue={"loaded": 10, "expected": 10, "failures": 0, "snapshot_at": ...}` moves them; a `CycleResult` with `venue=None` moves NONE of them (the timestamp keeps its last value — absence must look stale, not fresh). HELP strings carry no internal tokens — `uv run pytest tests/test_internal_terms_not_operator_visible.py` must stay green.
- [ ] **Step 3: Implement the gauges** — `VenueGauges` beside `ExecGauges` in `command.py`, eager registration, updated inside the existing sink. `instruments_expected` is DERIVED (`len(INSTRUMENT_IDS)`), never a literal — a T0137 re-ratification must change it in one committed place; the tests assert `== 10`.
- [ ] **Step 4: The two alert rules + exclusions (spec D6)** — without these, admitting the names auto-fails `test_every_fault_signal_metric_is_watched_by_a_rule`, because every admitted series must be watched or excluded with a reason. In `infra/grafana/alerts.yaml`, following the sibling engine rules' shape (instant query + threshold node, `folderUID`/`datasourceUid` templated, `noDataState: OK`, `execErrState: Alerting`, `for: 5m`, `severity: warning`, `receiver: metrics`, uid ≤ 40 chars):
  - `zcrypto-venue-concordance-failed` — expr `zcrypto_venue_concordance_failures > 0`; summary: a ratified instrument went missing or unparseable at the venue (operator-facing — no serials/topic tokens).
  - `zcrypto-venue-snapshot-stale` — expr `(time() - zcrypto_venue_snapshot_timestamp_seconds) > 18000` (one 4h cycle + 1h slack); summary: the venue snapshot writer has stopped producing.
  In `tests/test_infra_alert_rules.py::NOT_A_FAULT_SIGNAL`, exclude `zcrypto_venue_instruments_loaded` and `zcrypto_venue_instruments_expected` with the reason: the failures count already reduces them; a rule on each would double-page one event.
- [ ] **Step 5:** `uv run pytest tests/test_engine_metrics.py tests/test_infra_alert_rules.py tests/test_infra_alloy_series.py tests/test_internal_terms_not_operator_visible.py -q` to green. Gate, stage, commit `feat(engine): the zcrypto_venue_* gauge family, admitted and watched end to end`.

### Task 8: T0130 build identity + T0134 caplog fix

**Files:** Modify `.github/workflows/capture-image.yml`, `infra/docker/Dockerfile`, `tests/test_engine_metrics.py`.

- [ ] **Step 1 (T0130):** In the workflow's `build-args:` block (line ~70), add `GIT_REVISION=${{ github.sha }}`. In the Dockerfile, after the existing `ARG POLARS_RUNTIME` (line ~35): `ARG GIT_REVISION=""` and `ENV ZCRYPTO_BUILD_REVISION=$GIT_REVISION`. The composing code and its tests landed in Task 4 — this step is only the delivery path. Verify the workflow parses: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/capture-image.yml'))"`.
- [ ] **Step 2 (T0134):** `tests/test_engine_metrics.py:850`, `test_run_survives_an_unreadable_journal_record_at_metrics_seed_time` — fails alone because `cli/logging/config.py::configure()` sets the `zcrypto` logger's `propagate = False`, starving caplog's root handler. Fix inside the test, production untouched:

```python
zlogger = logging.getLogger("zcrypto")
zlogger.addHandler(caplog.handler)
try:
    ...  # existing body
finally:
    zlogger.removeHandler(caplog.handler)
```

- [ ] **Step 3: Prove it:** `uv run pytest "tests/test_engine_metrics.py::test_run_survives_an_unreadable_journal_record_at_metrics_seed_time" -v` ALONE (the previously-failing shape) → green; then the whole file → green.
- [ ] **Step 4: Gate, then TWO commits, unconditionally** — the staged-kind hook only enforces claude-kind vs everything else, so it would not stop a mixed commit; the split is `commit-messages.md` discipline, not hook appeasement. First `ci(build): bake the git revision into the image as ZCRYPTO_BUILD_REVISION` (workflow + Dockerfile), then `test(engine): capture the zcrypto logger directly -- the order-dependent caplog fix` (the T0134 file). T0130 and T0134 share nothing; they only ride the same task for dispatch economy.

### Task 9: Closeout

**Files:** `docs/iterations-history-phase6.md`, `docs/research/14.phase6-decisions.md`, `docs/open-topics/T0130-*` + `T0134-*` (resolve + archive via `topic-ops`), `docs/open-topics/README.md`, the `00089` row in `docs/open-topics/T0018-phase6-build-sequence.md`.

- [ ] **Step 1:** Load the `iteration-closeout` skill; author the history entry **from the branch log**, not this plan. Subject-matter phase 6.
- [ ] **Step 2:** T0130 → `resolved`: rewrite its "packaging default" hypothesis in place (D8's measured correction — no release was ever cut), record the fix (workflow build-arg → `ZCRYPTO_BUILD_REVISION` → `code_version` composition) and that final acceptance is **by value at the converge** (the first `cycle-HH.json`/`venue-HH.json` under the new image reading `0.0.0+<sha12>`); archive per topic-ops. T0134 → `resolved`: the fix, the standalone-green proof; archive. Index bullets move with links repointed.
- [ ] **Step 3:** Update T0018's spec table: `00089` → `landed (iter-<N>)`.
- [ ] **Step 4:** Decisions-log entries per the closeout skill's format for the spec's D-numbers that were genuine option-picks (D2, D3, D5, D9 at minimum), `(Decision: N)` marked.
- [ ] **Step 5:** Gate, stage by explicit path, commit `docs(engine): iter-<N> closeout -- venue truth lands; T0130 and T0134 resolve`.

---

## The deploy (after merge — NOT part of task execution)

The full `00088` pattern, attended: the new digest bakes as capture on `zcrypto-red` (the engine's canary — there is no engine secondary), gate per `zcrypto-captures-rollout`; the engine converge lands in a 4-hourly inter-cycle gap with `fleet-pins.md` updated first. The keep-regex edit makes Alloy the subject on the capture hosts: the converge carries `-e capture_alloy_digest=<currently-running>`. Verify by value, never presence: the first `venue-HH.json` on the host (`status: ok`, ten instruments, `code_version` = `0.0.0+<sha12>` matching the image's revision label), `zcrypto_venue_*` in Cloud with `concordance_failures` read as a number equal to 0 — `(no series)` is a FAIL — and T0130's acceptance recorded on its archived topic.
