# 00090 — The Rung-1 Order Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the one real order path — gate-inside submission chokepoint, ledger write-ahead, the maker-first state machine with a price-bounded IOC fallback, reduce-only classification, the first automatic kill trips — driven by operator-authored probe plans, with the execution metric families, the Engine board's execution and venue rows, and the probe checklist as an operating surface. Everything refusal-by-default; the model book stays shadow.

**Architecture:** Two new modules split by import weight: `cli/engine/probeplan.py` (pure plan model — parse, TTL, dedup, caps; no nautilus, so `probe-plan --check` stays fast) and `cli/engine/executor.py` (the ONE module in `cli/` that may reference `submit_order`/`order_factory` — a repo-walk test enforces it). The executor is event-driven on the node's single thread: `ShadowStrategy` forwards a 5 s timer tick, quote ticks, and order events into it; it holds the `ExecutionGate` (never a verdict) and evaluates immediately before every venue call. The exec ledger moves to schema 2 (write-ahead rows, merge-never-clobber, `{1, 2}` loadable) and the venue record gains `validate_venue_record` (T0140 option (a)). Metrics land under the reserved `zcrypto_exec_*` prefix plus T0121's `zcrypto_engine_limit_bound_total`, admitted end to end in the same change.

**Tech Stack:** Python 3.14, nautilus-trader 1.230.0 (installed, pinned — every adapter fact below is verified against `.venv`), prometheus_client, pytest + Typer `CliRunner`; stub clients in tests, no live node, no network.

## Pinned nautilus-trader 1.230.0 facts (verified in `.venv` — implementers use these calls, they do not rediscover them)

- Timer: `self.clock.set_timer(name: str, interval: timedelta, start_time=None, stop_time=None, callback: Callable[[TimeEvent], None] | None = None, allow_past=True, fire_immediately=False)` (`common/component.pyx`). Name must be unique per clock.
- Quotes: `self.subscribe_quote_ticks(instrument_id: InstrumentId)` → `on_quote_tick(self, tick: QuoteTick)`; `tick.instrument_id`, `tick.bid_price`/`tick.ask_price` (`Price`, `float()`-able); `self.unsubscribe_quote_ticks(instrument_id)`.
- Orders: `self.order_factory.limit(instrument_id: InstrumentId, order_side: OrderSide, quantity: Quantity, price: Price, time_in_force: TimeInForce = TimeInForce.GTC, ..., post_only: bool = False, reduce_only: bool = False, ..., client_order_id: ClientOrderId | None = None)` (`common/factories.pyx` line 312; GTC and IOC both valid for LIMIT). `self.submit_order(order, position_id=None, client_id=None, params: dict | None = None)`; `self.cancel_order(order, client_id=None, params=None)` (`trading/strategy.pyx`).
- Leverage: `params={"leverage": N}` flows `SubmitOrder.params` → `KrakenExecutionClient._parse_leverage` (int, `0 <= raw <= 65535`, else `generate_order_denied`) → `KrakenSpotHttpClient.submit_order(..., reduce_only=order.is_reduce_only, post_only=order.is_post_only, leverage=leverage, account_type=...)` (`adapters/kraken/execution.py` lines 859–1067). `default_leverage` stays unset (T0120): rung 1 passes leverage per order.
- `reduce_only` under `spot_account_type=CASH` → `generate_order_denied("reduce_only requires spot_account_type=Margin")`; the node runs MARGIN, so margin closers may carry it. A SPOT-class order must NOT carry it (D10: the disposal's whole guard is the executor-side quantity bound).
- Submit exception mapping: ANY exception in `_submit_order` → `generate_order_rejected(reason=str(e), due_post_only=("POST_ONLY_REJECTED:" in error_str))` (`execution.py` lines 1068–1078) — a timeout is event-indistinguishable from a venue rejection; only the reason text distinguishes them. `OrderRejected.due_post_only` is a real event field (`model/events/order.pyx` line 2145).
- Events at the strategy: `on_order_event(self, event: OrderEvent)` receives every event for the strategy's own orders; `OrderFilled` carries `client_order_id`, `last_qty`, `last_px`, `commission` (`Money`, `.currency.code`), `liquidity_side`, `trade_id`. The executor dispatches on `type(event).__name__` so stub events are plain `SimpleNamespace`s.
- Cache: `cache.instrument(InstrumentId) -> Instrument | None` (carries `make_qty`/`make_price`), `cache.positions_open(instrument_id=...)`/`cache.positions_closed(instrument_id=...) -> list[Position]` (`Position.signed_qty: float`, `Position.realized_pnl: Money | None`), `cache.orders_open(venue=None, instrument_id=None, strategy_id=None, ...)` (`cache/cache.pyx` line 4710), `cache.account_for_venue(venue) -> Account | None`.

## Global Constraints

- **Refusal-by-default is the spec's center**: every error, ambiguity, or absent-input path ends in **no order** — a raise inside the executor is converted to a journaled refusal, never propagated past a submission site, and never a retry.
- **Nothing widens a `00088` floor**: the restart hold still clears only by a human act, the kill file latches and no code clears it, arming still needs both keys. This spec only *narrows* (D10's startup cancel pass, D11's trips).
- Operator-facing text carries no `T<NNNN>`/spec-serial/`iter-<N>` — metric HELP, CLI `--help`, alert summaries, dashboard titles/descriptions all in scope; `tests/test_internal_terms_not_operator_visible.py` enforces every surface and covers the new strings.
- Python 3.14 / PEP 758: unparenthesized `except A, B:` is valid — not a defect; do not "fix" it in review.
- Commit gate `uv run pre-commit run -a` to clean; stage by explicit path, never `git add -A`/`-u`; implementers run **targeted test files only** — the full suite runs once in Task 13 and in the whole-branch review.
- No network in tests; everything the executor does in tests runs against constructed/stub objects — no live node, no real submission. What is only provable live (`reduce_only`'s first live use, the settle observation, adopted-order event routing) is routed to the D13 checklist, never faked.
- `docs/specs/00095-twelve-leg-deployable-design.md` and `docs/reference/trial-registry.jsonl` are **IMMUTABLE — never touched** (the spec hash pins record 47; an appended registry line breaks the chain).
- Markdown: one line per paragraph/bullet — never hard-wrap.
- The intent-side families are NOT renamed (`zcrypto_engine_*` are live series); new families use the reserved `zcrypto_exec_*` prefix exactly as spelled in D12.
- Plan caps verbatim: `exec_max_plan_notional_eur` default **100.0**; margin floor `sum(notional_i / leverage_i) × 2.5 ≤ free ZEUR balance`; plan TTL **60 minutes** from its own `created_at`; plan-id dedup over the **current or previous UTC day**'s exec ledger; quote wait/silence **30 s**; time-box **15 minutes**; at most **5 reprices** (resubmissions after the initial order — the initial submission is never counted); at most **3 IOC attempts**; rest-cancel prices **5 % away from the touch on the passive side**.

## File Structure

| File | Responsibility |
| --- | --- |
| `cli/engine/execledger.py` | *modify* — schema 2, `validate_exec_record`, merge-never-clobber `write_exec_record`, the write-ahead/append API, the dedup/attach scanners |
| `cli/engine/venueledger.py` | *modify* — `validate_venue_record` (`{1, 2}` loadable, both directions) |
| `cli/config.py` | *modify* — `EngineConfig.exec_max_plan_notional_eur: float = 100.0` |
| `cli/engine/probeplan.py` | *create* — plan model: parse, TTL, dedup, caps (pure; no nautilus import) |
| `cli/engine/executor.py` | *create* — THE venue-mutating module: sizing seam + T0138 guard, chokepoint, state machine, classification, startup pass, kill trips |
| `cli/engine/node.py` | *modify* — `ShadowStrategy` wires the executor: 5 s timer, quote/order-event forwarding |
| `cli/engine/cycle.py` | *modify* — `CycleResult.limit_bound` + `_limits_bound` (T0121) |
| `cli/engine/command.py` | *modify* — `probe-plan` command, `_ExecutionMetrics`, `_seed_exec_positions`, sink extraction + limit counter |
| `infra/ansible/roles/engine/templates/zcrypto.toml.j2` + `defaults/main.yml` | *modify* — render `exec_max_plan_notional_eur` explicitly |
| `infra/ansible/roles/capture/files/config.alloy` | *modify* — keep-regex admits the six new families |
| `infra/grafana/engine-dashboard.json` | *modify* — execution row, venue row, head panel rewrite |
| `infra/grafana/alerts.yaml` | *modify* — the two `zcrypto-venue-*` rules gain `__dashboardUid__`/`__panelId__` (no new rules, no prune) |
| `infra/runbooks/README.md` | *modify* — the probe-window checklist section (D13) |
| `README.md` | *modify* — `probe-plan` row in the `zcrypto engine` Usage table |
| `tests/test_engine_execledger.py`, `test_engine_venueledger.py`, `test_config.py`, `test_engine_probeplan.py` *(new)*, `test_engine_executor.py` *(new)*, `test_engine_node.py`, `test_engine_cycle.py`, `test_engine_metrics.py`, `test_engine_command.py`, `test_infra_alloy_series.py`, `test_infra_alert_rules.py`, `test_dashboards_cover_metrics.py` | tests per task |
| Closeout: `docs/iterations-history-phase6.md`, `docs/research/14.phase6-decisions.md`, T0138 + T0140 (resolve+archive), T0018, `docs/open-topics/README.md` | *modify* (Task 14 only) |

---

### Task 1: Exec ledger schema 2 — write-ahead rows, merge-never-clobber, schema-aware validation

**Files:** Modify `cli/engine/execledger.py`, `tests/test_engine_execledger.py`.

**Discharges spec Verification:** "the sink's merge write over a record carrying submitted rows preserves them byte-for-byte"; "same pair for `validate_exec_record`" (D9's exec half); "Streak immunity re-proven with populated exec records".

**Interfaces:**

- Consumes (unchanged upstream): `GateVerdict(level: str, reasons: tuple[str, ...], inputs: dict)` from `cli/engine/execgate.py`; `EngineError`, `EngineJournalError` from `cli/engine/errors.py`.
- `EXEC_SCHEMA_VERSION = 2`; `_LOADABLE_EXEC_SCHEMA_VERSIONS = frozenset({1, 2})` (the journal's `_LOADABLE_SCHEMA_VERSIONS` pattern, named in its comment).
- **Record shape** — v1 keys are exactly `{"schema_version", "cycle_ts", "evaluated_at", "level", "reasons", "inputs", "submitted"}` with `submitted == []` (written by code that could not submit); v2 is those keys **plus `"plans"`**. Version–shape disagreement is refused, never normalized.
- **Submitted row** (one per venue order, keys exact): `{"plan_id": str, "intent_index": int, "client_order_id": str, "intent": dict, "order": {"side": "buy"|"sell", "qty": float, "price": float, "time_in_force": "GTC"|"IOC", "post_only": bool, "reduce_only": bool, "leverage": int | None}, "state": str, "filled_qty": float, "events": list[dict]}`. `state ∈ {"submitting", "accepted", "rejected", "venue_canceled", "canceled", "filled", "ambiguous"}`; `_OPEN_ORDER_STATES = frozenset({"submitting", "accepted"})`.
- **Plan entry** (keys exact): `{"plan_id": str, "received_at": str, "disposition": "accepted"|"refused", "reasons": list[str], "plan": dict, "intents": list[dict]}` — `plan` is the parsed plan document verbatim (D3: "journals the plan verbatim"); each intents element `{"index": int, "outcome": str, "reasons": list[str], "filled_qty": float}`.
- Produces (signatures exact):
  - `validate_exec_record(doc: dict) -> None` — raises `EngineJournalError` on any version–shape disagreement (unknown schema; v1 with a `plans` key or non-empty `submitted`; v2 without `plans`; a row or plan entry whose key set ≠ the exact sets above; non-list `submitted`/`plans`/`reasons`/`events`).
  - `write_exec_record(journal_dir: Path, cycle_ts: datetime, verdict: GateVerdict, *, evaluated_at: datetime) -> Path` — **signature unchanged; semantics become merge-never-clobber**: an existing record's `submitted` and `plans` lists are carried into the rewrite byte-for-byte (a v1 record on disk upgrades to v2 with `plans: []`); only the verdict fields (`level`, `reasons`, `inputs`, `evaluated_at`) are replaced. An existing file that will not parse raises `EngineError` — clobbering forensics is never the answer; the frozen heartbeat (Task 10's proof) is the page.
  - `append_submitted_row(journal_dir, cycle_ts, row: dict, *, verdict: GateVerdict, evaluated_at: datetime) -> Path` — the write-ahead call: creates the boundary's v2 record from `verdict` when absent, appends `row` when present. Raises on any failure (the caller refuses the submission).
  - `update_submitted_row(journal_dir, cycle_ts, client_order_id: str, *, state: str | None = None, event: dict | None = None, add_filled_qty: float = 0.0) -> None` — appends `event` to the row's `events`, sets `state`, adds to `filled_qty`; raises `EngineError` when the row is absent.
  - `append_plan_entry(journal_dir, cycle_ts, entry: dict, *, verdict, evaluated_at) -> Path` and `update_plan_intent(journal_dir, cycle_ts, plan_id: str, index: int, *, outcome: str, reasons: tuple[str, ...] = (), filled_qty: float = 0.0) -> None`.
  - `ledgered_plan_ids(journal_dir: Path, now: datetime) -> frozenset[str]` — plan ids from `plans[*].plan_id` AND `submitted[*].plan_id` across every `exec-*.json` in the **current and previous UTC day** dirs; each record read is `validate_exec_record`-checked, and a raise propagates (a corrupt ledger refuses the plan — refusal-by-default).
  - `ledgered_intent_keys(journal_dir, now) -> frozenset[tuple[str, int]]` — `(plan_id, intent_index)` over the same window's submitted rows.
  - `open_submitted_rows(journal_dir, now) -> list[tuple[datetime, dict]]` — `(boundary, row)` for rows whose `state` is in `_OPEN_ORDER_STATES`, same window (D10's re-attach input).
- Every mutator writes via `.tmp` sibling + `os.replace` (the `_write_prom_textfile` pattern in `cli/engine/command.py`) so a reader never sees a partial record.

**Steps:**

- [ ] **Step 1: Failing tests** in `tests/test_engine_execledger.py` (keep the existing `_LEDGER_PREFIXES` glob tests untouched; the fixtures grow). The load-bearing ones verbatim:

```python
def test_the_sink_merge_never_clobbers_submitted_rows(tmp_path):
    """D5's merge-never-clobber, byte-for-byte: a per-cycle verdict write over a record already
    carrying submitted rows and plan entries preserves both lists exactly."""
    write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    row = _row()  # helper: one submitting-state row with the exact key set
    append_submitted_row(tmp_path, CYCLE_TS, row, verdict=_verdict(), evaluated_at=CYCLE_TS)
    before = read_exec_record(exec_record_path(tmp_path, CYCLE_TS))
    write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS + timedelta(minutes=5))
    after = read_exec_record(exec_record_path(tmp_path, CYCLE_TS))
    assert after["submitted"] == before["submitted"]
    assert after["plans"] == before["plans"]
    assert after["evaluated_at"] == (CYCLE_TS + timedelta(minutes=5)).isoformat()


def test_a_v1_record_with_a_populated_submitted_list_is_refused():
    doc = _v1_doc()  # the 7 exact v1 keys, submitted=[]
    doc["submitted"] = [_row()]
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_a_v2_record_without_the_plans_key_is_refused():
    doc = _v2_doc()
    del doc["plans"]
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)


def test_a_v1_record_validates_in_its_own_shape():
    validate_exec_record(_v1_doc())  # must not raise


def test_unknown_schema_is_refused():
    doc = _v2_doc()
    doc["schema_version"] = 3
    with pytest.raises(EngineJournalError):
        validate_exec_record(doc)
```

  Plus: a merge over a v1-on-disk record upgrades to v2 with `plans: []` and `submitted` preserved; an unparseable existing file makes `write_exec_record` raise `EngineError` and leaves the bytes untouched; `update_submitted_row` appends the event / adds filled qty / raises on an unknown id; `ledgered_plan_ids`/`ledgered_intent_keys`/`open_submitted_rows` over a constructed two-day journal include yesterday, exclude the day before, and a corrupt record makes the scan raise.
- [ ] **Step 2: The streak-immunity re-proof with POPULATED records**, through the real `report` path (the `00088` test proved empty records; this must not regress with rows present):

```python
def test_populated_exec_records_leave_the_report_byte_identical(tmp_path, monkeypatch):
    """A synthetic day of cycle records scores IDENTICALLY with and without exec records that
    carry submitted rows, plan entries and refusals -- through cli.engine.command's real
    _evaluate_journal/report path, never a hand-called evaluate_gate."""
    from typer.testing import CliRunner
    from cli.__main__ import app
    import cli.engine.command as command
    day = tmp_path / "2026-08-11"
    day.mkdir(parents=True)
    for hh in (0, 4, 8, 12, 16, 20):
        (day / f"cycle-{hh:02d}.json").write_text("{not json")  # classifies validation_failed -- deterministic
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(days=1))
    runner = CliRunner()
    args = ["engine", "report", "--journal-dir", str(tmp_path)]
    without = runner.invoke(app, args)
    for hh in (0, 4, 8, 12, 16, 20):
        p = append_submitted_row(tmp_path, CYCLE_TS.replace(hour=hh), _row(), verdict=_verdict(), evaluated_at=CYCLE_TS)
        append_plan_entry(tmp_path, CYCLE_TS.replace(hour=hh), _refused_plan_entry(), verdict=_verdict(), evaluated_at=CYCLE_TS)
        assert p.exists()
    with_records = runner.invoke(app, args)
    assert with_records.output == without.output
    assert with_records.exit_code == without.exit_code
```

- [ ] **Step 3: red.** `uv run pytest tests/test_engine_execledger.py -q` — the new tests fail on missing names (`ImportError: cannot import name 'validate_exec_record'`).
- [ ] **Step 4: Implement** in `cli/engine/execledger.py`: bump `EXEC_SCHEMA_VERSION = 2`; the validator (exact-key-set comparisons against module-level frozensets `_V1_KEYS`/`_V2_KEYS`/`_ROW_KEYS`/`_PLAN_ENTRY_KEYS`, error messages naming the offending key set, mirroring `journal.validate_record`'s message style); the merge read-modify-write core as one private `_load_or_new(path, verdict, evaluated_at) -> dict` + `_store(path, doc)` (tmp + `os.replace`) pair every mutator shares. `write_exec_record` keeps writing `indent=2, sort_keys=True`.
- [ ] **Step 5: green** on the same command. **Gate** `uv run pre-commit run -a`, stage `cli/engine/execledger.py tests/test_engine_execledger.py` by path, commit `feat(engine): exec ledger schema 2 -- write-ahead rows, merge-never-clobber, schema-aware validation`. The implementer appends `Co-Authored-By: <its own actual model> <noreply@anthropic.com>` (never a hardcoded model name) — this note applies to every commit step below.

### Task 2: `validate_venue_record` (T0140 option (a)) and the startup position seed

**Files:** Modify `cli/engine/venueledger.py`, `cli/engine/command.py`, `tests/test_engine_venueledger.py`, `tests/test_engine_metrics.py`.

**Discharges spec Verification:** "a schema-2 venue record with base keys is refused by `validate_venue_record`; a v1 record validates in its own shape"; "the startup position seed reads a constructed record correctly and skips an `error` record".

**Interfaces:**

- Consumes: `read_venue_record(path: Path) -> dict`, `VENUE_SCHEMA_VERSION = 2` (both existing in `venueledger.py`); `_journal_artifacts(journal_dir, pattern, name_glob)` (existing in `command.py`).
- Produces in `venueledger.py`: `_LOADABLE_VENUE_SCHEMA_VERSIONS = frozenset({1, 2})` and `validate_venue_record(doc: dict) -> None` raising `EngineJournalError` — schema-aware in BOTH directions, mirroring `cli/engine/journal.py::validate_record`:
  - `schema_version` must be in the loadable set; `cycle_ts`/`code_version`/`status` required; `status == "error"` requires `error` and forbids `state`/`concordance`; `status == "ok"` requires `state` (`{"snapshot_at", "instruments", "positions", "balances"}` exactly) and `concordance` (`{"ok", "failures"}` exactly).
  - v2: every `state.instruments` and `state.positions` key is a full-symbol key (`"/" in key` — reuse the journal's `_is_symbol_key` logic, re-stated locally); each instrument entry's key set is exactly `{"symbol", "instrument_id", "ordermin", "costmin", "costmin_quote", "lot_step", "tick_size", "costmin_source"}`. A base key or a missing `costmin_quote` is refused, never normalized.
  - v1 (workstation-side journals only — no v1 `venue-<HH>.json` ever existed on the engine host, `00089` deployed 2026-08-16 already at schema 2): every key is a base key (no `/`); entry key set exactly `{"base", "instrument_id", "ordermin", "costmin", "lot_step", "tick_size", "costmin_source"}`; a symbol key or a `costmin_quote` is refused (written by code that could not produce them).
- Produces in `command.py`: `_seed_exec_positions(journal_dir: Path) -> dict[str, float] | None` — the newest `venue-*.json` whose `status` is `"ok"` AND `schema_version == 2` (the gauge is symbol-labelled; a base-keyed v1 record cannot seed it), `validate_venue_record`-checked, returning `dict(doc["state"]["positions"])`; `None` when no such record exists. Mirrors `_seed_venue_state`'s glob/newest logic and its no-try/except contract (the caller's telemetry guard owns isolation). `_seed_venue_state` itself now calls `validate_venue_record(doc)` on each record before consulting `status` (D9: "called by every reader this spec adds and by `_seed_venue_state`").

**Steps:**

- [ ] **Step 1: Replace the two self-referential tests.** In `tests/test_engine_venueledger.py`, `test_a_success_record_round_trips_state_and_concordance` and `test_an_error_record_carries_the_reason_and_no_state_key` currently assert `doc["schema_version"] == VENUE_SCHEMA_VERSION` — true at any value. Rewrite both to call `validate_venue_record(doc)` on the written record (the writer's own output must validate under its declared schema) while keeping their value assertions (`status`, `state`, `concordance`, `error`) verbatim. Add the refusal tests:

```python
def test_a_schema2_record_with_base_keys_is_refused(tmp_path):
    p = write_venue_record(tmp_path, CYCLE_TS, state=_state(), concordance=_concordance(), code_version="abc123")
    doc = read_venue_record(p)
    doc["state"]["instruments"] = {"BTC": doc["state"]["instruments"]["BTC/EUR"]}
    doc["state"]["positions"] = {"BTC": 0.0}
    with pytest.raises(EngineJournalError):
        validate_venue_record(doc)


def test_a_v1_record_validates_in_its_own_shape():
    doc = _v1_doc()  # helper: schema_version 1, base-keyed, entries carry "base", no costmin_quote
    validate_venue_record(doc)  # must not raise
    doc["state"]["instruments"]["BTC"]["costmin_quote"] = "EUR"
    with pytest.raises(EngineJournalError):
        validate_venue_record(doc)


def test_unknown_schema_is_refused():
    doc = _v1_doc()
    doc["schema_version"] = 3
    with pytest.raises(EngineJournalError):
        validate_venue_record(doc)
```

- [ ] **Step 2: The seed tests** in `tests/test_engine_metrics.py` (beside the existing `_seed_venue_state` tests — find and mirror their fixture that writes `venue-<HH>.json` files): `_seed_exec_positions` returns the NEWEST ok record's positions dict; skips an `error` record even when it is newer; returns `None` on an empty journal; skips a `schema_version: 1` record.
- [ ] **Step 3: red → implement → green.** `uv run pytest tests/test_engine_venueledger.py tests/test_engine_metrics.py -q`. Implementation notes: `venueledger.py` imports `EngineJournalError` from `cli.engine.errors` (top-level — `errors.py` is nautilus-free); `VENUE_SCHEMA_VERSION`'s "Write-only: nothing reads or validates this constant" comment is now false — rewrite it in place to name `validate_venue_record` as the reader.
- [ ] **Step 4: Gate, stage `cli/engine/venueledger.py cli/engine/command.py tests/test_engine_venueledger.py tests/test_engine_metrics.py`, commit** `feat(engine): schema-aware venue record validation and the startup position seed`.

### Task 3: `exec_max_plan_notional_eur` + the probe-plan model with TTL/dedup

**Files:** Modify `cli/config.py`, `infra/ansible/roles/engine/templates/zcrypto.toml.j2`, `infra/ansible/roles/engine/defaults/main.yml`; create `cli/engine/probeplan.py`, `tests/test_engine_probeplan.py`; modify `tests/test_config.py`.

**Discharges spec Verification:** "TTL/dedup: an expired plan refuses; a plan_id already ledgered refuses" (the model half — the executor half is Task 5).

**Interfaces:**

- Produces in `cli/config.py`: `EngineConfig.exec_max_plan_notional_eur: float = 100.0` — parsed in `_build_engine` exactly like `shadow_nav_eur` (positive number, bool rejected). The field's comment: the total-notional cap a probe plan may carry — the blast-radius bound.
- Produces in `zcrypto.toml.j2` (rendered explicitly so a converge diff shows it, beside `exec_armed`): `exec_max_plan_notional_eur = {{ engine_exec_max_plan_notional_eur }}`; `defaults/main.yml` gains `engine_exec_max_plan_notional_eur: 100.0` under the existing "[zcrypto.engine] knobs" comment block.
- Produces in `cli/engine/probeplan.py` (pure — imports only stdlib, `cli.engine.errors`, and `cli.engine.store.BASKET`; **no nautilus**, so `probe-plan --check` and these tests stay fast):

```python
PLAN_FILENAME = "probe-plan.json"
PLAN_TTL = timedelta(minutes=60)

class ProbePlanError(EngineError): ...

@dataclass(frozen=True)
class ProbeIntent:
    symbol: str
    side: str              # "buy" | "sell"
    action: str            # "open" | "close"
    mode: str              # "execute" | "rest-cancel"
    notional_eur: float | None   # exactly one of notional_eur / qty
    qty: float | None            # the disposal's explicit base quantity (close + spot only)
    leverage: int | None         # None = spot; margin requires 2..10 (the committed band)

@dataclass(frozen=True)
class ProbePlan:
    plan_id: str
    created_at: datetime
    intents: tuple[ProbeIntent, ...]
    raw: dict              # the parsed document verbatim, journaled by the executor

def parse_plan(text: str) -> ProbePlan: ...
def plan_refusals(plan: ProbePlan, *, now: datetime, ledgered: frozenset[str],
                  max_plan_notional_eur: float, free_zeur: float) -> tuple[str, ...]: ...
```

- `parse_plan` raises `ProbePlanError` on ANY shape violation: non-JSON; missing/mistyped `plan_id`/`created_at` (must parse to an **aware** datetime)/`intents` (non-empty list); an intent whose `symbol` is not in `BASKET`, whose `side`/`action`/`mode` is outside its set, that carries both or neither of `notional_eur`/`qty`, whose numeric is non-finite/non-positive, whose `qty` appears with `action != "close"` or with `leverage` present, or whose `leverage` is present but not an int in `[2, 10]`.
- `plan_refusals` returns every applicable reason (the gate's plural-reasons discipline, deterministic order): `"plan expired: created_at ... is over 60 minutes old"` when `now - created_at > PLAN_TTL`; `"created_at is in the future"` when `created_at > now`; `"plan_id already ledgered"` when `plan.plan_id in ledgered`; `"plan notional ... exceeds the cap ..."` when `sum(i.notional_eur or 0.0) > max_plan_notional_eur` (a `qty` intent is a strictly-shrinking reducer bounded by D10's balance check, so it contributes no NEW notional to the cap — stated in the docstring); `"margin floor: ..."` when `sum(i.notional_eur / i.leverage for margin intents) * 2.5 > free_zeur` (§10's 250 % floor at rung scale).

**Steps:**

- [ ] **Step 1: Failing config tests** in `tests/test_config.py`, mirroring the three `exec_armed` tests exactly: default 100.0 when absent; reads a set value; rejects a non-number/non-positive/bool. Plus the template pin:

```python
def test_the_engine_role_template_renders_the_plan_cap_explicitly():
    """The blast-radius bound must appear in a converge diff, exactly like exec_armed."""
    text = Path("infra/ansible/roles/engine/templates/zcrypto.toml.j2").read_text()
    assert "exec_max_plan_notional_eur = {{ engine_exec_max_plan_notional_eur }}" in text
    defaults = Path("infra/ansible/roles/engine/defaults/main.yml").read_text()
    assert "engine_exec_max_plan_notional_eur: 100.0" in defaults
```

- [ ] **Step 2: Failing plan-model tests** in `tests/test_engine_probeplan.py` — one refusal per shape rule (each flipping alone, the execgate test style), and for `plan_refusals`: an expired plan refuses; a future `created_at` refuses; a ledgered id refuses; a €120 total against the 100.0 cap refuses; two margin intents `30 €` at leverage 2 pass a `free_zeur=100` floor (`30 × 2.5 = 75 ≤ 100`) and refuse at `free_zeur=50`; a valid plan returns `()`. Multi-condition: an expired AND over-cap plan returns BOTH reasons in declaration order (assert the tuple).
- [ ] **Step 3: red → implement → green.** `uv run pytest tests/test_config.py tests/test_engine_probeplan.py -q`.
- [ ] **Step 4: Gate, stage `cli/config.py cli/engine/probeplan.py infra/ansible/roles/engine/templates/zcrypto.toml.j2 infra/ansible/roles/engine/defaults/main.yml tests/test_config.py tests/test_engine_probeplan.py`, commit** `feat(engine): the probe-plan model -- TTL, dedup, caps, and the exec_max_plan_notional_eur key`.

### Task 4: The sized-intent seam with the T0138 denomination guard

**Files:** Create `cli/engine/executor.py` (the pure layer only), `tests/test_engine_executor.py`.

**Discharges spec Verification:** "the T0138 pair — `costmin=2e-05, costmin_quote="BTC"` against a EUR notional raises the denomination assert (read WHICH failure fired); the matched EUR pair passes".

**Interfaces:**

- Consumes (quoted exactly): `size_order(target_qty: float, reference_price: float, *, ordermin: float, costmin: float, lot_step: float, tick_size: float) -> SizedOrder | BelowMinimum` and `InstrumentConstraints(symbol, instrument_id, ordermin, costmin, costmin_quote, lot_step, tick_size)` — `size_order` takes `costmin` as a bare number; **the caller owns denomination** (its own docstring), which is exactly where T0138 says the guard lives. `fx_eur_notional(symbol: str, qty: float, price: float, btc_eur_close: float) -> float` stays pure and uncalled — named in the guard's error text as the sanctioned route for a future `/BTC`-leg notional; this spec's probe intents are EUR-leg only.
- Produces in `cli/engine/executor.py`:

```python
def size_probe_order(target_qty: float, touch_price: float, constraints: InstrumentConstraints) -> SizedOrder | BelowMinimum:
    """THE sizing call site (spec 00090 D8): every probe order is sized here, on the Cache-fresh
    constraints and the committed costmin, through the one proven size_order. The comparison this
    module makes is EUR-denominated end to end (an EUR intent notional, an EUR-quoted touch), so the
    guard T0138 holds lands immediately where the notional meets constraints.costmin: a floor
    denominated in anything but EUR must never be compared here -- a /BTC leg's 2e-05 BTC floor
    against a EUR notional passes everything silently (the fail-open defect). Route a future
    /BTC-leg notional through fx_eur_notional first; until then this raises."""
    if constraints.costmin_quote != "EUR":
        raise EngineError(
            f"{constraints.symbol}: costmin is denominated in {constraints.costmin_quote!r} but this "
            "path compares an EUR notional against it -- refusing a cross-denomination comparison "
            "(convert through fx_eur_notional before sizing a non-EUR-quoted leg)"
        )
    return size_order(target_qty, touch_price, ordermin=constraints.ordermin,
                      costmin=constraints.costmin, lot_step=constraints.lot_step, tick_size=constraints.tick_size)
```

Note: `executor.py`'s module docstring declares it the single venue-mutating module (the D4 walk test's anchor). The nautilus imports (`InstrumentId`, `OrderSide`, `TimeInForce`, `Venue`) join in Task 5.

**Steps:**

- [ ] **Step 1: Failing tests** in `tests/test_engine_executor.py`:

```python
def _constraints(**overrides):
    base = dict(symbol="BTC/EUR", instrument_id="BTC/EUR.KRAKEN", ordermin=0.0001,
                costmin=0.45, costmin_quote="EUR", lot_step=0.00000001, tick_size=0.1)
    base.update(overrides)
    return InstrumentConstraints(**base)


def test_the_mismatched_denomination_raises_and_names_the_defect():
    """T0138's constructed defect: a BTC floor (2e-05) against a EUR notional. Assert WHICH failure
    fired -- the denomination guard, not a BelowMinimum or an unrelated raise."""
    c = _constraints(symbol="ETH/BTC", instrument_id="ETH/BTC.KRAKEN", costmin=2e-05, costmin_quote="BTC")
    with pytest.raises(EngineError, match="cross-denomination"):
        size_probe_order(0.01, 0.05, c)


def test_the_matched_eur_pair_sizes_through_size_order():
    sized = size_probe_order(0.001, 30000.0, _constraints())
    assert isinstance(sized, SizedOrder)
    assert sized.qty == 0.001 and sized.price == 30000.0


def test_a_below_minimum_result_passes_through_unchanged():
    result = size_probe_order(0.00001, 30000.0, _constraints(ordermin=0.0001))
    assert isinstance(result, BelowMinimum)
```

- [ ] **Step 2: red → implement → green.** `uv run pytest tests/test_engine_executor.py -q`.
- [ ] **Step 3: Gate, stage `cli/engine/executor.py tests/test_engine_executor.py`, commit** `feat(engine): the sized-intent seam with the costmin denomination guard`.

### Task 5: The submission chokepoint — one module, gate-inside, ledger write-ahead, plan pickup

**Files:** Modify `cli/engine/executor.py`, `tests/test_engine_executor.py`.

**Discharges spec Verification:** "the single-call-site walk fails on a planted `submit_order` reference outside `executor.py`" (the walk test itself; the plant is Task 13's probe); "a raising `write_exec_record` at the submission site → the stub client is never called and the intent refuses" (via `append_submitted_row`); "venue-truth raise → intent refused"; "a plan over `exec_max_plan_notional_eur` refuses; a plan violating the ×2.5 margin floor refuses" (live-path half); "an expired plan refuses; a plan_id already ledgered refuses; an intent with a submitted row is not resubmitted across a simulated restart".

**Interfaces:**

- Consumes: `ExecutionGate.evaluate(now: datetime) -> GateVerdict`, `GateLevel.NONE/REDUCE_ONLY/FULL`, `exec_dir(state_dir: Path) -> Path`, `KILL_FILE` (all `cli/engine/execgate.py`); `venue_state_from_cache(cache, *, clock)` (`cli/engine/venuestate.py`); Task 1's ledger API; Task 3's plan model; `INSTRUMENT_IDS` (`cli/engine/instruments.py`).
- Produces in `cli/engine/executor.py`:

```python
_TICK_SECONDS = 5.0
_QUOTE_WAIT = timedelta(seconds=30)
_QUOTE_SILENCE = timedelta(seconds=30)
_TIME_BOX = timedelta(minutes=15)
_MAX_REPRICES = 5
_MAX_IOC_ATTEMPTS = 3
_REST_CANCEL_OFFSET = 0.05
_KRAKEN_ERROR_MARKERS = ("EOrder:", "EGeneral:", "EAccount:")
_POST_ONLY_MARKER = "POST_ONLY_REJECTED:"

def set_executor_hooks(*, publish_verdict=None, metrics=None) -> None: ...
    # the cycle.set_metrics_sink pattern: module-level, None-safe, installed by command.run()

class ProbeExecutor:
    """Owns every venue-mutating call in this repository. `client` is the strategy handle (or a
    stub with the same surface): .cache, .order_factory.limit(...), .submit_order(order, params=...),
    .cancel_order(order), .subscribe_quote_ticks(id), .unsubscribe_quote_ticks(id)."""
    def __init__(self, *, client, gate: ExecutionGate, config: EngineConfig, clock=_utc_now) -> None: ...
    def on_timer(self, now: datetime) -> None: ...
    def on_quote(self, tick) -> None: ...
    def on_order_event(self, event) -> None: ...
```

- **`_evaluate(now)`** — the ONE gate read: `verdict = self._gate.evaluate(now)`, then publishes through the `publish_verdict` hook (D4's cadence ruling: every executor evaluation reaches `_ExecGauges`, so gate state is seconds-fresh during a window). Called at every submission and on every tick **while a plan is active** — an idle tick does only the `os.lstat` (the `00088` between-cycles cadence stands unchanged; a per-idle-tick evaluation would re-read the venue every 30 s forever, which `00088` deliberately rejected).
- **`_submit(ctx, order, params)` — THE chokepoint.** Its first act is `verdict = self._evaluate(self._now())`, then the level check `if not self._level_permits(verdict.level, ctx.intent):` where `_level_permits(level, intent)` returns True for an open intent only at `GateLevel.FULL` and for a close intent at `GateLevel.REDUCE_ONLY` or `GateLevel.FULL`; a failing level journals the refusal (`update_plan_intent(..., outcome="refused", reasons=verdict.reasons)`), counts `metrics.inc_order("refused")`, and returns without touching the client. It then builds the write-ahead row (`state: "submitting"`, `filled_qty: 0.0`, `events: []`, the intent dict verbatim, the sized order dict, `client_order_id=str(order.client_order_id)`) and calls `append_submitted_row(...)` inside `try` — **any exception refuses the submission** (journal the refusal reason `"exec ledger write failed"` via `update_plan_intent`; if even that raises, log CRITICAL — the ledger is down and nothing may trade). Only then `self._client.submit_order(order, params=params)` and `metrics.inc_order("submitted")`. The function takes no verdict parameter and reads no stored verdict — there is no holdable token to go stale.
- **`_boundary(now)`** — private aware-UTC 4 h floor (`now.replace(hour=now.hour - now.hour % 4, minute=0, second=0, microsecond=0)` after `astimezone(timezone.utc)`); a local copy of `node.most_recent_boundary`'s arithmetic, named in its comment — importing `node` here would be an import cycle (node imports this module in Task 9).
- **Plan pickup** (`on_timer`, no active plan): `os.lstat` on `exec_dir(state_dir) / PLAN_FILENAME` (`state_dir = config.journal_dir.parent`, the `00088` convention); `FileNotFoundError` → return (the cheap idle path). Present → read text → `parse_plan`; a `ProbePlanError` journals a refused plan entry (`plan_id: "unparseable"`, `plan: {}`, the error string as the reason), **deletes the file**, and stops. Parsed → read venue truth `venue_state_from_cache(self._client.cache, clock=...)` in `try` — a raise journals the plan refused with reason `"no venue truth"` (**no venue truth → no orders**), deletes the file, and stops. Then `reasons = plan_refusals(plan, now=now, ledgered=ledgered_plan_ids(journal_dir, now), max_plan_notional_eur=config.exec_max_plan_notional_eur, free_zeur=state.balances.get("ZEUR", 0.0) or state.balances.get("EUR", 0.0))` (live balances spell `ZEUR` — measured in `node.py`'s currency-code comment; the `EUR` fallback covers constructed states, and both-absent reads 0.0 and refuses). Non-empty → journal refused with the reasons; empty → journal accepted (`append_plan_entry` with the verbatim `plan.raw`). **Every disposition journals first, then deletes the file** (the spec's order: journal the plan verbatim, delete, run — only a filesystem restore can bring the file back, into the TTL and dedup walls; a crash between journal and delete re-picks the file next tick, where the now-ledgered `plan_id` refuses it and the delete still runs), then an accepted plan's intents queue.
- **Sequential intents with the per-intent dedup belt**: before starting intent `i`, `(plan.plan_id, i) in ledgered_intent_keys(...)` → journal outcome `"already_ledgered"` and skip (a ledgered submitted row is never resubmitted). Intent start = gate level check → venue truth read (fresh per intent) → classification (Task 7) → `subscribe_quote_ticks` → `phase = "awaiting_quote"` with `quote_deadline = now + _QUOTE_WAIT`. One intent active at a time; the next starts on the tick after the previous reaches terminal state.
- The walk test (module-level in `tests/test_engine_executor.py`):

```python
def test_submit_order_and_order_factory_have_exactly_one_module():
    """D4's structural pin: all venue-mutating calls live in cli/engine/executor.py. A text walk,
    not an import walk -- a reference in a comment is still a reference a refactor can activate."""
    offenders = []
    for path in sorted(Path("cli").rglob("*.py")):
        if path.as_posix() == "cli/engine/executor.py":
            continue
        text = path.read_text()
        if "submit_order" in text or "order_factory" in text:
            offenders.append(path.as_posix())
    assert offenders == []
```

**Steps:**

- [ ] **Step 1: The stub harness** at the top of `tests/test_engine_executor.py` — `StubClient` (records `submitted`/`canceled`/`subscribed`; `order_factory.limit(**kwargs)` returns a `SimpleNamespace` order echoing its kwargs with `client_order_id` from a counter `"O-1"`, `"O-2"`, …), `StubCache` (mirror `tests/test_engine_venuestate.py`'s fakes: `instrument(id)` returns an object whose `id` str-matches `INSTRUMENT_IDS[symbol]`, carries `min_quantity`/`size_increment`/`price_increment` and `make_qty`/`make_price` as identity lambdas; `positions_open(instrument_id=...)`; `orders_open(venue=...)`; `account_for_venue(...)` with `balances_free()` keyed by a `SimpleNamespace(code="ZEUR")`), a `_gate(tmp_path, level)` helper building a real `ExecutionGate` with control files set for the wanted level (the `test_engine_execgate.py` `_all_clear` pattern with a stubbed venue reader), a `_drop_plan(tmp_path, plan_dict)` helper writing `exec/probe-plan.json`, and a `_tick(executor, now)` driver.
- [ ] **Step 2: Failing tests** — each construction seen to refuse, stub client asserted untouched where refusal is claimed:
  - the walk test above (green immediately — it pins, Task 13 proves it trips);
  - a valid plan through an all-clear gate reaches `subscribe_quote_ticks` and, after a quote, the stub records exactly one `submit_order` whose order is post-only GTC at the touch;
  - kill file present → intent refused, `submitted == []` (this test is Task 13's mutation probe target — name it `test_the_kill_file_refuses_the_submission_and_no_order_reaches_the_client`);
  - `monkeypatch.setattr(executor_module, "append_submitted_row", _raise)` → stub never called, plan intent journaled refused with `"exec ledger write failed"`;
  - `venue_state_from_cache` raising (cache stub raises) → plan journaled refused `"no venue truth"`, no subscribe, no submit;
  - an expired plan (created_at 61 min back) → refused + journaled; a plan whose `plan_id` is already in a constructed ledger → refused; **the simulated restart**: construct a ledger carrying a submitted row for `(plan_id, 0)` but no plan entry (the crash construction), drop the same plan → intent 0 skipped `"already_ledgered"`, intent 1 runs;
  - over-cap plan (€120) and floor-violating plan (free ZEUR 50) → refused with the exact reasons;
  - pickup deletes the plan file and journals the verbatim plan dict into the plan entry;
  - an idle tick with no plan file evaluates NO gate (assert via a counting gate stub) — the cheap-lstat claim.
- [ ] **Step 3: red → implement → green.** `uv run pytest tests/test_engine_executor.py -q`. Implementation: dispatch `on_order_event` by `type(event).__name__` (stub-friendly, adapter-real); order construction uses `instrument.make_qty(sized.qty)` / `instrument.make_price(sized.price)` from the Cache instrument; `params={"leverage": intent.leverage}` only when `leverage` is not None.
- [ ] **Step 4: Gate, stage `cli/engine/executor.py tests/test_engine_executor.py`, commit** `feat(engine): the submission chokepoint -- gate-inside, ledger write-ahead, plan pickup and dedup`.

### Task 6: The maker-first state machine

**Files:** Modify `cli/engine/executor.py`, `tests/test_engine_executor.py`.

**Discharges spec Verification:** the entire D6 bullet — both crossing surfaces count one reprice each; the sixth reprice refuses; time-box → cancel → IOC at the opposite touch (price asserted); partial-fill remainder sizing and cross-order quantity conservation; ambiguous outcome halts with NO second order; kill file mid-rest cancels with no fallback; quote silence past 30 s cancels and halts; rest-cancel never emits a second order.

**Interfaces (state machine, exact):**

- Intent context fields: `phase ∈ {"awaiting_quote", "resting", "cancelling", "ioc", "done"}`, `started_at`, `quote_deadline`, `timebox_at = started_at + _TIME_BOX`, `last_quote_at`, `bid`/`ask` (floats from the last tick), `reprices: int = 0`, `ioc_attempts: int = 0`, `filled: float = 0.0` (cumulative across ALL the intent's orders), `target_qty` (the intent's quantity), `order` (the live order object), `cancel_requested: bool`, `falling_back: bool`.
- **First submission** (on the first quote in `awaiting_quote`): join the touch — buy at `bid`, sell at `ask` (never improving into the spread); `mode: "rest-cancel"` prices 5 % away on the passive side instead — buy at `bid * (1 - _REST_CANCEL_OFFSET)`, sell at `ask * (1 + _REST_CANCEL_OFFSET)` (never joining — a join can fill in the instant after acknowledgment); size through `size_probe_order`; post-only GTC; `phase = "resting"`.
- **`on_quote`**: ignore ticks whose `str(tick.instrument_id)` differs from the active intent's instrument id; update `bid`/`ask`/`last_quote_at`; in `awaiting_quote`, proceed to first submission.
- **`on_order_event` dispatch** (by `type(event).__name__`):
  - `OrderAccepted` → row `state="accepted"` + event append; `metrics.inc_order("accepted")`; rest-cancel mode → `cancel_requested = True; self._client.cancel_order(ctx.order)`.
  - `OrderRejected` → read `reason = str(event.reason)`. `getattr(event, "due_post_only", False)` or `_POST_ONLY_MARKER in reason` → the synchronous crossing surface: row `state="rejected"` + `metrics.inc_order("rejected")`, then **one reprice** (below). Else any `_KRAKEN_ERROR_MARKERS` substring → a positive venue verdict: row `state="rejected"`, intent terminal `outcome="rejected"` with the reason, **no retry** (this is also the D6 non-tradeable-instrument halt). **Else AMBIGUOUS** — the order may be live at the venue (the installed adapter maps ANY submit exception here): row `state="ambiguous"`, intent terminal `outcome="ambiguous"`, **no resubmission, no IOC**, and the whole plan halts (`self._halted = True`; remaining intents journal `outcome="refused"`, reason `"predecessor intent ambiguous"`) — no further order until an open-orders re-read (the attended operator, or the next startup pass) establishes what reached the venue.
  - `OrderDenied` (a local refusal — leverage parse, reduce-only-under-CASH; nothing reached the venue) → row `state="rejected"`, intent terminal `outcome="rejected"`, no ambiguity.
  - `OrderCanceled` / `OrderExpired` → if `cancel_requested` and `falling_back` → proceed to IOC; if `cancel_requested` and rest-cancel → terminal `outcome=("rest_cancel_ok" if ctx.filled == 0.0 else "partial")`; if `cancel_requested` (a mid-rest revoke) → terminal `outcome="revoked"` with the revoke reasons; **if NOT `cancel_requested` while resting** → the venue-cancel crossing surface (iter-079's accept-then-venue-cancel, streamed through this adapter): row `state="venue_canceled"`, `metrics.inc_order("venue_canceled")`, **one reprice**; if in `ioc` phase → the IOC's unfilled remainder came back: next IOC attempt or terminal `outcome="unfilled"` after the third.
  - `OrderFilled` → Task 8 guards first, then `qty = float(event.last_qty)`; `ctx.filled += qty`; `update_submitted_row(..., event={"event": "fill", "at": ..., "qty": qty, "px": float(event.last_px), "fee": float(event.commission), "fee_currency": event.commission.currency.code, "liquidity": str(event.liquidity_side), "trade_id": str(event.trade_id)}, add_filled_qty=qty)`; metrics (`inc_fill`, fee — Task 10 wires the sink); order fully filled (`row filled_qty == order qty`) → row `state="filled"`, `metrics.inc_order("filled")`; intent remainder `target_qty - ctx.filled <= 0` → terminal `outcome="filled"`; a partial on a resting GTC keeps resting.
- **Reprice** (both crossing surfaces funnel here): `reprices += 1`; `if reprices > _MAX_REPRICES` → terminal `outcome="unfilled"`, reason `"reprice budget exhausted"` (the sixth reprice refuses; the initial submission is never counted — the counter counts resubmissions only). Else re-read the touch from the last quote and resubmit through `_submit`, **sized to the remainder** `target_qty - ctx.filled`; a remainder below `ordermin`/`lot_step` (a `BelowMinimum` from `size_probe_order`) → terminal `outcome="partial"` (a legitimate terminal state, never an unfillable order).
- **`on_timer` while a plan is active**: `verdict = self._evaluate(now)`; while an order rests — the kill file, disarm, the hold latching (level now insufficient for THIS intent), the venue leaving online (all read from the verdict), **or quote silence** (`now - last_quote_at > _QUOTE_SILENCE`) → `cancel_requested = True; cancel_order(ctx.order)`, terminal on the cancel ack as `outcome="revoked"` (reasons = the verdict's reasons or `("quote_silence",)`), and the plan halts — **no fallback is emitted**. Time-box: `now > timebox_at` while resting → `cancel_requested = True; falling_back = True; cancel_order(...)`. In `awaiting_quote`: `now > quote_deadline` → terminal `outcome="refused"`, reason `"no quote within 30 s"` (the rung-1 per-instrument cover `00088` deferred, claimed by name).
- **IOC fallback**: at most `_MAX_IOC_ATTEMPTS`; each attempt re-reads the touch and prices a **marketable LIMIT IOC at the opposite touch** — buy at `ask`, sell at `bid` — `time_in_force=TimeInForce.IOC`, `post_only=False`, sized to the remainder through `size_probe_order` (below-minimum → terminal `outcome="partial"`); submitted through `_submit` (the chokepoint — a gate change between cancel and fallback refuses it). Third attempt's remainder comes back canceled → terminal `outcome="unfilled"` for the operator.
- Terminal handling: `unsubscribe_quote_ticks`, `update_plan_intent(..., outcome=..., filled_qty=ctx.filled)`, next intent on the following tick.

**Steps:**

- [ ] **Step 1: Failing tests**, each named for the property (the two load-bearing ones verbatim):

```python
def test_both_crossing_surfaces_count_one_reprice_and_the_sixth_refuses(tmp_path):
    """Surface 1: OrderRejected(due_post_only=True) -- the adapter's synchronous mapping.
    Surface 2: accept-then-venue-cancel (OrderCanceled with no cancel requested). Alternate them:
    5 reprices happen (6 submissions total), the 6th reprice is refused and the intent halts
    unfilled with NO 7th order."""
    ex, client, now = _resting_executor(tmp_path)  # helper: plan accepted, first order submitted
    # _named(name, **attrs) builds an instance of a dynamically created class called `name`, so the
    # executor's type(event).__name__ dispatch sees the real event names on plain stub objects.
    for i in range(5):
        if i % 2 == 0:
            ex.on_order_event(_named("OrderRejected", client_order_id=client.last_order_id, reason="POST_ONLY_REJECTED: would cross", due_post_only=True))
        else:
            ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
        ex.on_quote(_quote(bid=30000.0, ask=30001.0))
    assert len(client.submitted) == 6  # initial + 5 reprices
    ex.on_order_event(_named("OrderRejected", client_order_id=client.last_order_id, reason="POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert len(client.submitted) == 6  # the sixth reprice refused, nothing new
    assert _intent_outcome(tmp_path) == "unfilled"


def test_an_ambiguous_rejection_halts_with_no_second_order(tmp_path):
    """The double-submit construction, seen refused: a timeout surfaced as a rejection carrying no
    Kraken error code and no post-only marker. The intent halts ambiguous; no reprice, no IOC."""
    ex, client, now = _resting_executor(tmp_path)
    ex.on_order_event(_named("OrderRejected", client_order_id=client.last_order_id, reason="request timed out", due_post_only=False))
    _advance_ticks(ex, minutes=20)   # deep past the time-box: still nothing may be emitted
    assert len(client.submitted) == 1
    assert _intent_outcome(tmp_path) == "ambiguous"
```

  Plus: time-box lapse cancels then emits an IOC **at the opposite touch with the price asserted** (buy intent → `submitted[1].price == ask`, `time_in_force == "IOC"`, `post_only is False`); a partial fill (0.4 of 1.0) then time-box → the IOC's qty is exactly `0.6` (quantity conservation through a constructed partial-fill-then-resubmit sequence); three unfilled IOCs → `outcome="unfilled"`, exactly 4 submissions total; a remainder below `ordermin` after a partial → `outcome="partial"` with no further order; kill file appearing mid-rest → cancel issued, NO fallback, plan halted; quote silence 30 s mid-rest → cancel + halt; `rest-cancel` mode → price asserted 5 % passive of the touch, cancel-on-ack, zero fills, `outcome="rest_cancel_ok"`, exactly 1 submission ever; a Kraken-coded rejection (`"EOrder:Insufficient funds"`) → terminal `rejected`, no retry.
- [ ] **Step 2: red → implement → green.** `uv run pytest tests/test_engine_executor.py -q`.
- [ ] **Step 3: Gate, stage the two files, commit** `feat(engine): the maker-first state machine -- join, reprice, time-box, bounded IOC fallback`.

### Task 7: Reduce-only classification and the startup ledger-attach/cancel pass

**Files:** Modify `cli/engine/executor.py`, `tests/test_engine_executor.py`.

**Discharges spec Verification:** the whole D10 bullet — opener at `reduce_only` refuses; over-|held| closer refuses; genuine closer passes with the flag; the spot disposal's balance bound both ways; the startup pass leaves exactly the ledger-attached reduce-only orders and cancels everything else including a reduce-only-flagged order with no ledger row; a post-restart fill on a re-attached order appends to its ledgered row.

**Interfaces:**

- **Margin closer** (`action == "close"`, `leverage` present): `held = sum(float(p.signed_qty) for p in cache.positions_open(instrument_id=...))`; `held == 0.0` → refuse `"no position to close"`; the side must oppose the sign (`sell` requires `held > 0`, `buy` requires `held < 0`) else refuse; **qty = `abs(held)` — sized from the Cache's live position, never from the plan** (the plan's `notional_eur` on a closer is advisory and unused for sizing); the order carries `reduce_only=True` so the venue enforces it too, plus `params={"leverage": N}`.
- **Spot disposal** (`action == "close"`, `leverage is None`, explicit `qty`): side must be `"sell"`; `qty` must be `<= _spot_balance(newest venue record)` — the newest schema-2 `venue-<HH>.json`'s `state.balances`, `validate_venue_record`-checked, read through `_spot_balance(balances: dict, base: str) -> float` which tries the venue alias spellings in order (`("BTC", "XBT", "XXBT")` for BTC, else `(base, f"X{base}")`), returning `0.0` when none is present (absent balance → 0.0 → refuses — refusal-by-default); **NO venue-side `reduce_only` flag** (Kraken's reduce_only is a margin concept a spot order cannot carry — the executor-side quantity bound is the whole guard); strictly shrinking, never flipping. An over-quantity plan refuses before any order exists; an over-quantity that somehow reaches the venue is venue-rejected with a Kraken error code and halts attended (Task 6's rejected path).
- **Openers at `reduce_only`**: already refused by Task 5's level check (`open` requires `FULL`) — the classification adds nothing for opens.
- **Startup pass** (first `on_timer` after construction): read `open_rows = open_submitted_rows(journal_dir, now)` and index by `client_order_id`; for every `order in cache.orders_open(venue=Venue("KRAKEN"))`: a matching non-terminal row whose **ledgered** `order["reduce_only"]` is `True` → leave resting and **re-attach** (`self._attached[client_order_id] = (boundary, row)`) so future `OrderFilled` events append to that row (`update_submitted_row` at the row's own boundary); everything else — an opener's row, a matched row not ledgered reduce-only, an order with no row at all, **including one whose adopted `is_reduce_only` flag reads True** — `cancel_order(order)`. The adopted report's flags are never consulted: whether Kraken's OpenOrders echo survives adoption truthfully is unverifiable in the installed source (the population is in the opaque Rust layer); the write-ahead row is the only trusted witness. A canceled close leg is re-dropped as a new signed-off plan — cancel-and-reissue over trusting an unverifiable flag. This narrows `00088` (a resting opener is a pending widening the hold exists to forbid); the hold, its human-only clear, and the gate's semantics are untouched.

**Steps:**

- [ ] **Step 1: Failing tests** (fixtures: `StubCache` grows `positions_open` returning constructed `SimpleNamespace(signed_qty=...)` lists and `orders_open` returning stub orders with `client_order_id` and `is_reduce_only` attributes; a `_venue_record(tmp_path, positions=..., balances=...)` helper writes a real schema-2 `venue-<HH>.json` via `write_venue_record`):
  - a `close` intent at gate `reduce_only` with `held=+0.001` and side `sell` → submits with `reduce_only=True` in the factory kwargs and `params={"leverage": 2}`;
  - side `sell` against `held=-0.001` → refused (`"side does not reduce the position"`); `held=0` → refused;
  - the disposal: plan `qty=0.0004` against a venue record `balances={"XXBT": 0.0005}` → submits a plain spot sell (`reduce_only` **absent/False** in factory kwargs, no `leverage` param); `qty=0.0006` → refused `"qty exceeds the venue record's balance"`; no venue record at all → refused;
  - an `open` intent at gate level `reduce_only` → refused (re-asserted here beside the closers);
  - **the startup matrix**: cache holds four open orders — (a) matched to a non-terminal reduce-only row, (b) matched to a non-terminal opener row, (c) `is_reduce_only=True` but NO row, (d) no row, no flag → exactly (b), (c), (d) canceled, (a) left resting;
  - **the post-restart fill**: after the pass, `ex.on_order_event(_named("OrderFilled", client_order_id="O-attached", last_qty=..., ...))` → the ORIGINAL boundary's exec record's row shows the appended fill event and grown `filled_qty` (read the file back by value).
- [ ] **Step 2: red → implement → green.** `uv run pytest tests/test_engine_executor.py -q`.
- [ ] **Step 3: Gate, stage the two files, commit** `feat(engine): reduce-only classification and the startup ledger-attach pass`.

### Task 8: The first automatic kill trips — reconciliation divergence

**Files:** Modify `cli/engine/executor.py`, `tests/test_engine_executor.py`.

**Discharges spec Verification:** the whole D11 bullet — each divergence construction creates the kill file and cancels resting orders (the trip is seen, not asserted into existence); a constructed external fill with no strategy claim does NOT trip.

**Interfaces:**

- `_trip_kill(self, reason: str)` — writes the kill file (`(exec_dir(state_dir) / KILL_FILE).write_text(reason)` — contents informational, presence load-bearing, exactly `00088`'s semantics: latching, human-cleared, no code path clears it), cancels the resting order if any (`cancel_requested = True; cancel_order(...)`), halts the plan (every further intent refused), logs CRITICAL. The next `_evaluate` publishes `zcrypto_exec_kill_tripped = 1` and the existing `zcrypto-engine-exec-kill-tripped` rule announces it — **no new alert rule**.
- The four trips, checked in this order:
  1. **Unknown own-strategy order** (checked FIRST in `on_order_event`, before any row update): an `OrderFilled` whose `client_order_id` is in neither the active rows nor `self._attached`. Strategy-scoped deliberately — only the strategy's own order events reach `on_order_event` (nautilus routes by strategy), so an account-external fill (the G4 settle) structurally never arrives here and routes through reconciliation as venue truth.
  2. **Per-order overfill**: `row["filled_qty"] + last_qty > row["order"]["qty"] + 1e-12`.
  3. **Per-intent cross-order overfill**: `ctx.filled + last_qty > ctx.target_qty + 1e-12` — the backstop of D6's remainder sizing.
  4. **Post-terminal reconciliation**: at every intent terminal, compare the Cache position against the ledger's expectation — `expected = ctx.position_before + (ctx.filled if buy else -ctx.filled)` (`position_before` read from the Cache at intent start), `actual = sum(signed_qty over cache.positions_open(instrument_id=...))`; `abs(actual - expected) > constraints.lot_step` → trip.

**Steps:**

- [ ] **Step 1: Failing tests** — each construction ends with `assert (exec_dir(tmp_path / "journal").parent / ...)`… concretely: `assert (exec_dir(state_dir) / KILL_FILE).exists()` **and** the resting order's cancel was issued (`client.canceled`), plus the quiet path:

```python
def test_an_external_fill_with_no_strategy_claim_does_not_trip(tmp_path):
    """The G4 settle's healthy path, proven quiet: the Cache position moves with NO order event
    reaching the executor (an external fill routes through reconciliation, never on_order_event).
    Ticks pass, no intent is active -- the kill file must NOT appear."""
    ex, client, state_dir = _idle_executor(tmp_path)
    client.cache.set_position("BTC/EUR", 0.0004)   # the settle landed as a holding
    _advance_ticks(ex, minutes=2)
    assert not (exec_dir(state_dir) / KILL_FILE).exists()
```

  The four trip constructions: (1) a fill for `"O-unknown"` while an intent rests; (2) a second fill pushing one order's `filled_qty` past its `order.qty`; (3) two orders of one intent whose fills sum past `target_qty` (construct by filling the resting order fully, then — after a reprice submitted a remainder order — over-filling the second); (4) at intent terminal, a stub cache position that disagrees with `position_before + filled` by more than `lot_step`.
- [ ] **Step 2: red → implement → green.** `uv run pytest tests/test_engine_executor.py -q`.
- [ ] **Step 3: Gate, stage the two files, commit** `feat(engine): the first automatic kill trips -- reconciliation divergence, unknown orders, overfills`.

### Task 9: Node wiring, `probe-plan --check`, README

**Files:** Modify `cli/engine/node.py`, `cli/engine/command.py`, `README.md`, `tests/test_engine_node.py`, `tests/test_engine_command.py`.

**Interfaces:**

- `ShadowStrategy.__init__(self, config: EngineConfig, *, run_cycle_fn: Callable = run_cycle, clock: Callable = _utc_now, executor_factory: Callable | None = None)` — `executor_factory(strategy) -> ProbeExecutor`, `None` (the default) wires nothing, so every existing construction and test is unchanged. `on_start` (after `on_start_logic`) builds `self._executor = self._executor_factory(self)` and registers the tick: `self.clock.set_timer("exec-probe-tick", timedelta(seconds=_TICK_SECONDS), callback=self._on_exec_tick)`. New forwarders, each a two-liner guarded on `self._executor is not None`: `_on_exec_tick(self, event)` → `self._executor.on_timer(self._now())`; `on_quote_tick(self, tick)` → `self._executor.on_quote(tick)`; `on_order_event(self, event)` → `self._executor.on_order_event(event)`. None of these references `submit_order`/`order_factory` — the walk test stays green.
- `build_shadow_node(config)` passes the real factory: a module-level `def _probe_executor_factory(config: EngineConfig)` returning `lambda strategy: ProbeExecutor(client=strategy, gate=ExecutionGate(armed_in_config=config.exec_armed, state_dir=config.journal_dir.parent, venue_reader=read_system_status), config=config)` — the executor import stays inside the function (`node.py` already pays nautilus; `executor.py` imports `venuestate`, fine here).
- `probe-plan` command in `command.py`:

```python
@engine_app.command(name="probe-plan")
def probe_plan(
    plan_path: Path = typer.Argument(..., help="Probe plan JSON file to validate."),
    check: bool = typer.Option(False, "--check", help="Validate the plan offline: shape, expiry, duplicate plan ids, the plan-level caps, and each intent against the newest venue snapshot's constraints. Advisory only -- the engine re-validates every plan live before any order."),
) -> None:
    """Validate an operator-authored probe plan against the newest journaled venue snapshot."""
```

  Without `--check` → `raise _abort("only --check is implemented -- the engine consumes plans from its state directory, never from this command")`. With it: `parse_plan` (a `ProbePlanError` → `_abort`); the newest ok schema-2 venue record from `config.journal_dir` (local import of `venueledger` — it pulls nautilus via `venuestate`, and `zcrypto --help` must never pay that; follow `_seed_venue_state`'s local-import pattern), `validate_venue_record`-checked, `_abort` when none exists; `ledgered_plan_ids(config.journal_dir, _utc_now())`; the gate evaluated and printed exactly as `exec-status` does (same `ExecutionGate(..., venue_reader=read_system_status)` construction so tests monkeypatch `command.read_system_status`); `plan_refusals(...)` with `free_zeur` from the record's balances; per intent print the checkable floors (a notional intent: `notional_eur` vs the record's `costmin` through the T0138 guard's rule — refuse printing a cross-denomination comparison; a qty intent: `qty` vs `ordermin` and lot alignment). Any refusal → exit 1; clean → `plan ok: <n> intent(s), total notional <x> EUR` and the per-intent lines.
- README `## Usage` → `zcrypto engine` table gains the row (`readme-usage.md`: same change as the CLI):

  `| `probe-plan <PATH> --check` | Validate an operator-authored probe plan offline before it is placed: plan shape, expiry, duplicate plan ids against the execution ledger, the plan-level notional cap and margin floor, each intent's floors against the newest journaled venue snapshot, and the current gate verdict. Advisory only — the engine re-validates every plan live before any order; a plan is placed by copying it into the engine state directory's `exec/probe-plan.json`, which only the account owner does. Exits non-zero on any refusal. Read-only — mutates nothing. |`

**Steps:**

- [ ] **Step 1: Failing node tests** (house style: `types.SimpleNamespace` stubs, `functools.partial` unbound-method driving — mirror `test_schedule_alert_sets_state_and_timer`): bare construction leaves `_executor is None` and `on_quote_tick`/`on_order_event` no-op; with a recording `executor_factory`, `on_start` builds the executor and registers `set_timer("exec-probe-tick", timedelta(seconds=5), ...)` (extend the test file's `FakeClock` with a `set_timer` recorder); `_on_exec_tick`/`on_quote_tick`/`on_order_event` forward with the right arguments; `build_shadow_node`'s factory shape is pinned the way `test_build_shadow_node_with_exec_client_when_enabled` pins the node config (construct, don't run).
- [ ] **Step 2: Failing CLI tests** in `tests/test_engine_command.py` (CliRunner + the file's config-monkeypatch fixture pattern): no `--check` → exit 1 with the one-line error; a valid plan against a written venue record and a stubbed `command.read_system_status` → exit 0, output carries `plan ok`; an expired plan → exit 1 naming the expiry; no venue record → exit 1; a plan over the cap → exit 1.
- [ ] **Step 3: red → implement → green.** `uv run pytest tests/test_engine_node.py tests/test_engine_command.py -q`.
- [ ] **Step 4: Gate, stage `cli/engine/node.py cli/engine/command.py README.md tests/test_engine_node.py tests/test_engine_command.py`, commit** `feat(engine): wire the probe executor into the node and add probe-plan --check`.

### Task 10: The execution metric families, the T0121 counter, admission, and the D5 ordering proof

**Files:** Modify `cli/engine/command.py`, `cli/engine/cycle.py`, `cli/engine/executor.py` (hook calls only), `infra/ansible/roles/capture/files/config.alloy`, `tests/test_engine_metrics.py`, `tests/test_engine_cycle.py`, `tests/test_infra_alloy_series.py`, `tests/test_infra_alert_rules.py`.

**Discharges spec Verification:** "the raising writer freezes `zcrypto_exec_last_evaluation_timestamp_seconds` and the `00088` staleness rule's condition goes true (read the value, not the rule's presence)"; D12's families/admission/budget re-measure.

**Interfaces:**

- `_ExecutionMetrics` in `command.py` (built on the same registry as `_CycleGauges`; HELP text operator-clean):

```python
class _ExecutionMetrics:
    def __init__(self, registry) -> None:
        self.orders = Counter("zcrypto_exec_orders_total", "Executor orders by outcome.", ["outcome"], registry=registry)
        self.fills = Counter("zcrypto_exec_fills_total", "Order fills by liquidity side.", ["liquidity"], registry=registry)
        self.fees = Counter("zcrypto_exec_fees_eur_total", "Trading fees paid, in EUR.", registry=registry)
        self.position = Gauge("zcrypto_exec_position", "Net position quantity by symbol, in base units.", ["symbol"], registry=registry)
        self.realized_pnl = Gauge("zcrypto_exec_realized_pnl_eur", "Realized profit and loss, in EUR.", registry=registry)
    def inc_order(self, outcome: str) -> None: ...
    def inc_fill(self, liquidity: str, fee_eur: float | None) -> None: ...
    def set_position(self, symbol: str, qty: float) -> None: ...
    def set_realized(self, value: float) -> None: ...
```

  Outcome label values exactly `submitted|accepted|rejected|venue_canceled|canceled|filled|refused`; liquidity `maker|taker` (lower-cased from `str(event.liquidity_side)`). Fees: only a commission whose `currency.code` is `EUR`/`ZEUR` is added — anything else is logged and skipped, never summed cross-currency (a future `/BTC`-leg fee converts through the BTC/EUR close before summing — not built here). The executor updates position/realized after each fill from the Cache: `qty = sum(signed_qty over positions_open(instrument_id=...))`; realized = sum of `float(p.realized_pnl)` over `positions_open + positions_closed` for the instruments this process has traded, EUR-denominated positions only (non-EUR logged and skipped). PnL is a **Gauge** — PnL falls, so never a counter.
- `run()` wiring: inside the registry block, its own isolation guard (the `_VenueGauges` pattern): build `_ExecutionMetrics(registry)`, seed positions from `_seed_exec_positions(config.journal_dir)` (each symbol → `position.labels(symbol=...).set(qty)`); then — registry or not — `executor.set_executor_hooks(publish_verdict=(exec_gauges.update if exec_gauges is not None else None), metrics=(exec_metrics if registry is not None else None))`.
- **T0121**: `CycleResult` gains `limit_bound: bool | None = None` (None on failure — no build ran). `cycle.py` gains:

```python
def _limits_bound(result) -> bool:
    """True iff the wired limit stack (caps -> gross -> net band -> margin floor; the governor is a
    returns overlay, deliberately outside) moved the combined book at the forming row. Mirrors
    cli/engine/feeders.py::replay_stages' recomputation exactly -- chained adds, one-element series."""
    c = CrossfreqSystemConfig()
    n = result.n_periods
    third = 1 / 3
    sleeves = {name: {a: result.sleeve_positions[name][a][n] for a in c.assets} for name in ("B", "A1", "A2")}
    combined = {a: third * sleeves["B"][a] + third * sleeves["A1"][a] + third * sleeves["A2"][a] for a in c.assets}
    limited = apply_whole_book_limits(apply_position_caps({a: [combined[a]] for a in c.assets}, long_cap=c.long_cap, short_cap=c.short_cap))
    return any(limited[a][0] != combined[a] for a in c.assets)
```

  with `from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, apply_whole_book_limits` and `from cli.risk import apply_position_caps`; `run_cycle` sets `limit_bound=_limits_bound(result)` on the success `CycleResult`. `_CycleGauges` gains `self.limit_bound = Counter("zcrypto_engine_limit_bound_total", "Cycles where a book-level limit changed the intended book.", registry=registry)` and `update()` does `if result.limit_bound: self.limit_bound.inc()` (intent-prefixed — the §10 limits bind on the intent book).
- **The D5 ordering proof needs the sink extractable**: refactor `run()`'s inline `_sink` closure into a module-level `_make_exec_sink(gate, journal_dir, cycle_gauges, exec_gauges, venue_gauges) -> Callable` with the identical body (verdict → `write_exec_record` FIRST → gauges) — behavior-preserving, and the only way to drive the real ordering in a test.
- **Alloy admission, both directions of the T0051 trap**: append to the capture keep-regex in `infra/ansible/roles/capture/files/config.alloy` (one `|`-joined block, beside the existing `zcrypto_exec_*` names): `zcrypto_exec_orders_total|zcrypto_exec_fills_total|zcrypto_exec_fees_eur_total|zcrypto_exec_position|zcrypto_exec_realized_pnl_eur|zcrypto_engine_limit_bound_total`. `tests/test_infra_alloy_series.py`'s capture required-list gains the same six (with a comment: attended-window execution instruments + the intent-side limit counter). `tests/test_infra_alert_rules.py::NOT_A_FAULT_SIGNAL` gains all six **with D12's written reason**: the execution families are attended-window instruments — arming is episodic through the tracking-error report's spec, so nothing fires unattended, and the kill-trip and armed-too-long rules already page the two states that outlive a window; `zcrypto_engine_limit_bound_total` is a level-shift detail read on the board (the §10 limits binding is legitimate behaviour, not a fault). **No new alert rules in this spec.**

**Steps:**

- [ ] **Step 1: The frozen-heartbeat proof**, written first:

```python
def test_a_raising_ledger_writer_freezes_the_heartbeat_and_the_staleness_condition_goes_true(tmp_path, monkeypatch):
    """D5's monitoring-gap discharge, read by VALUE: the sink writes the ledger BEFORE any gauge,
    so a persistently failing write_exec_record starves zcrypto_exec_last_evaluation_timestamp_seconds
    and the existing staleness rule's condition (now - ts past one cycle interval + slack) goes true."""
    registry = CollectorRegistry()
    gate = ExecutionGate(armed_in_config=False, state_dir=tmp_path, venue_reader=lambda *, now, opener=None: VenueStatus(status="online", ok=True, observed_at=now))
    exec_gauges = _ExecGauges(registry)
    t0 = datetime(2026, 8, 11, 8, 0, tzinfo=timezone.utc)
    sink = command._make_exec_sink(gate, tmp_path / "journal", None, exec_gauges, None)
    sink(_success_result(cycle_ts=t0), t0, 1.0)                      # one healthy cycle: ts = t0
    assert exec_gauges.last_evaluation._value.get() == t0.timestamp()
    monkeypatch.setattr(command, "write_exec_record", _raise)
    t1 = t0 + timedelta(hours=8)
    try:
        sink(_success_result(cycle_ts=t1), t1, 1.0)
    except Exception:
        pass  # in production cycle.py's _update_metrics swallows exactly this raise -- same effect
    frozen = exec_gauges.last_evaluation._value.get()
    assert frozen == t0.timestamp()                                   # the heartbeat froze
    assert (t1.timestamp() - frozen) > 4 * 3600 + 900                 # the rule's condition, as a number
```

- [ ] **Step 2: Remaining failing tests**: `_ExecutionMetrics` label/name pins (parse the registry via `text_string_to_metric_families`, the file's own pattern — `zcrypto_exec_orders_total{outcome="submitted"}` present after `inc_order`, a BTC-denominated commission is NOT added to fees while a ZEUR one is); `_limits_bound` direct: a constructed result-shape (`SimpleNamespace(n_periods=0, sleeve_positions={"B": {a: [0.9]}, ...})` with every asset at 0.9) → `True` (caps bind), an inside-limits book → `False`; `run_cycle` integration in `tests/test_engine_cycle.py`: the existing success fixture's result carries `limit_bound is False` (the shadow book is measured 0-of-137 cap-bound) and a failed cycle carries `None`; `_CycleGauges.update` increments the counter iff `limit_bound` is truthy.
- [ ] **Step 3: red → implement → green.** `uv run pytest tests/test_engine_metrics.py tests/test_engine_cycle.py tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py -q`. `tests/test_dashboards_cover_metrics.py` now goes red (six published families, no panels) — **deliberate, Task 11 lands the panels next; do not add NOT_CHARTED entries to silence it.**
- [ ] **Step 4: Re-measure the series budget** (D12: measured, never carried): count the new active series (7 outcome labels + 2 liquidity + 1 fees + 12 position + 1 pnl + 1 limit = 24) against the <1k budget with the current keep-list total, and state the number in the task report and commit body.
- [ ] **Step 5: Gate, stage `cli/engine/command.py cli/engine/cycle.py cli/engine/executor.py infra/ansible/roles/capture/files/config.alloy tests/test_engine_metrics.py tests/test_engine_cycle.py tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py`, commit** `feat(engine): the execution metric families, the limit-bound counter, and their admission`.

### Task 11: The Engine board — execution row, venue row, the head panel rewrite, and the venue-rule annotations

**Files:** Modify `infra/grafana/engine-dashboard.json`, `infra/grafana/alerts.yaml`, `tests/test_dashboards_cover_metrics.py`.

**Steps:**

- [ ] **Step 1: The head panel (id 1) is rewritten** — its "no position, no fill … anywhere in this fleet's telemetry today" and "`data/engine-journal` … sole source of truth for realized state" claims become false the moment these families ship. Replace `options.content` with the intent-vs-execution legend (title becomes `"Intent vs execution — read the right row"`):

  `**Two kinds of numbers live on this board.** The Intent and Composition rows are the engine's *decisions* — target weights and intended orders, computed every cycle whether or not anything may trade. The Execution row is what actually *happened* at the venue — orders, fills, fees, positions, realized PnL — published by the execution path and empty outside an attended trading window. The Venue truth row is what the exchange said we could trade and held at each cycle. An intended order with no fill beside it is the normal shadow state, not a failure.`
- [ ] **Step 2: Two new rows appended** (every existing panel tops out at `y + h = 60`; datasource object verbatim from panel 22: `{"type": "prometheus", "uid": "grafanacloud-prom"}`; every expr host-scoped `{host=~"$host"}` like the board's other engine exprs). Row `{"id": 60, "type": "row", "title": "Execution — what actually happened at the venue", "gridPos": {"h": 1, "w": 24, "x": 0, "y": 60}}`, then timeseries panels 61–66 laid out two per 12-wide half at `h: 6` (61/62 at y 61, 63/64 at y 67, 65/66 at y 73): 61 `Orders by outcome` (`zcrypto_exec_orders_total{host=~"$host"}`, legend `{{outcome}}`), 62 `Fills by liquidity side — the realized maker/taker blend` (`zcrypto_exec_fills_total{host=~"$host"}`, legend `{{liquidity}}`), 63 `Fees paid (EUR)` (`zcrypto_exec_fees_eur_total{host=~"$host"}`), 64 `Position by symbol (base units)` (`zcrypto_exec_position{host=~"$host"}`, legend `{{symbol}}`), 65 `Realized PnL (EUR)` (`zcrypto_exec_realized_pnl_eur{host=~"$host"}`), 66 `Cycles where a book-level limit bound the intended book` (`zcrypto_engine_limit_bound_total{host=~"$host"}`). Row `{"id": 70, "type": "row", "title": "Venue truth — what the exchange said", "gridPos": {"h": 1, "w": 24, "x": 0, "y": 79}}`, panels 71–73 three across at `h: 6, w: 8, y: 80` (x 0 / 8 / 16): 71 `Venue snapshot age` (`time() - zcrypto_venue_snapshot_timestamp_seconds{host=~"$host"}`), 72 `Instruments loaded vs expected` (two targets: `zcrypto_venue_instruments_loaded{host=~"$host"}`, `zcrypto_venue_instruments_expected{host=~"$host"}`), 73 `Venue concordance failures` (`zcrypto_venue_concordance_failures{host=~"$host"}`). Copy `fieldConfig`/`options` wholesale from panel 14 (the board's plain timeseries shape). Panel titles/descriptions carry no internal tokens.
- [ ] **Step 3: The two venue rules gain their panel pointers** (iter-127's a-firing-alert-points-at-its-panel invariant, no other rule field touched): in `infra/grafana/alerts.yaml`, `zcrypto-venue-concordance-failed` annotations gain `__dashboardUid__: "zcrypto-engine"` / `__panelId__: "73"`; `zcrypto-venue-snapshot-stale` gains `__dashboardUid__: "zcrypto-engine"` / `__panelId__: "71"` (both values quoted strings — an unquoted int aborts the whole push, the coverage test's assertion 4).
- [ ] **Step 4: Delete the four `NOT_CHARTED` venue entries** in `tests/test_dashboards_cover_metrics.py` — their written reason was exactly "until this pass"; leaving them would exempt families that now have panels.
- [ ] **Step 5: green.** `uv run pytest tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py tests/test_infra_alert_rules.py -q` (coverage assertions 1–4, dashboard-text vocabulary, rule fields).
- [ ] **Step 6: Gate, stage `infra/grafana/engine-dashboard.json infra/grafana/alerts.yaml tests/test_dashboards_cover_metrics.py`, commit** `feat(grafana): the engine board gains execution and venue rows; the head panel tells the truth`.

### Task 12: The probe checklist lands as a runbook section (D13)

**Files:** Modify `infra/runbooks/README.md`.

- [ ] **Step 1: Append the section** after `refdata-sweep-due`, following the file's section protocol (explicit `<a name=…>` anchor, marker suffix, `### What you are seeing / What it means / What to do / Retire when`): anchor `engine-probe-window`, heading `## engine-probe-window — PROCEDURE`. *What you are seeing*: you are about to run (or are running) an attended live-order probe window on the engine — nothing has fired; this is the only sanctioned way to run one. *What it means*: the engine's order path submits only operator-authored probe plans, inside an attended window bounded by two arming keys; every step below exists because its omission has a named failure. *What to do* — the five phases from spec 00090 D13, verbatim in content, imperative in form:
  - **Pre-probe**: sweep `docs/open-topics/README.md` + the memo for blockers and present the result with the arming request; verify funding (G1 — the balance covers the plan under the ×2.5 margin floor) and probe sign-off preconditions (G2); verify `tests/test_costmin_drift.py` and `tests/test_basket_concordance.py` green on the deployed digest; confirm free EUR covers the plan.
  - **Arm**: converge `exec_armed = true` (full engine-converge discipline: inter-cycle window, secondary-bake canary, pins recorded — `capture-deploys.md`); the restart latches the hold; verify reconciliation clean — `zcrypto engine exec-status` reasons read exactly `arm_file_absent,restart_hold`, positions/balances as expected in the newest venue record; the owner clears the hold; the owner creates the arm file.
  - **Drill before money**: a `mode: rest-cancel` plan through the full machine — verdict, ledger rows, acknowledgment, cancel, zero fills, zero fees, read back **by value** from `exec-<HH>.json`; then the disarmed-refusal drill — drop a plan with the arm file removed: every intent refused with reasons journaled, no venue call.
  - **Execute**: the open plan — **a funded plan is never dropped inside the final 60 minutes before a 4 h boundary** (00/04/08/12/16/20 UTC; the TTL makes that the natural bound — a cycle blocks the event loop up to ~25 min and no revoke can act while it does); monitor fills via the ledger and the board's Execution row; ≥ ~9 h later the close plan (same boundary rule); the settle act in the Kraken UI (owner-only — the engine cannot emit settle-position); the ledger-export read; the disposal plan with its explicit `qty` from that export (same sign-off and boundary rules); the Blockpit re-sync; **on a T2 fail, registering the T3 fallback as its own topic is a step of THIS checklist's fail branch, done in the same session as the verdict**.
  - **Disarm**: the owner deletes the arm file at window close AND **converges `exec_armed` back to `false` the same day** — between the two acts arming is one key; **any state-dir restore is treated as re-arming until proven otherwise** — after a restore, verify `exec/` holds no arm file and no plan file before the engine starts.
  - **Verify by outcome**: exec-record rows for every intent with terminal states; fills with fees and liquidity sides; two rollover rows per position in the ledger export; the settle-then-disposal observed in venue truth — read from the venue record written after the disarm converge's restart (the verified reconciliation path; an earlier next-boundary record is corroboration, never the gate); positions flat and balances back to EUR-only (dust-bounded); `zcrypto_exec_*` families live in Cloud read by value.
  - *Retire when*: the probe executor's plan-file path (`exec/probe-plan.json` handling in `cli/engine/executor.py`) is absent from the repo — the continuous loop that replaces attended probe windows has landed and this procedure with it.
- [ ] **Step 2: Gate** (`mdformat` will rewrite — re-stage), stage `infra/runbooks/README.md`, commit `docs(runbooks): the probe-window checklist lands as an operating surface`.

### Task 13: Mutation probes, the operator-facing sweep, the full suite

**Files:** none modified (probes restore; fixes, if any, get their own commits).

- [ ] **Step 1: The D4 gate-unavoidability probe** through the sanctioned path (`infra/scripts/mutate-probe.sh` — refuses a dirty tree, purges `.pyc`, proves the control):

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/executor.py \
  --control 's/if not self._level_permits(verdict.level, ctx.intent):/if self._level_permits(verdict.level, ctx.intent):/' \
  --mutation 's/verdict = self._evaluate(self._now())/verdict = GateVerdict(level=GateLevel.FULL, reasons=(), inputs={})/' \
  -- uv run pytest tests/test_engine_executor.py::test_the_kill_file_refuses_the_submission_and_no_order_reaches_the_client -x -q
```

  Adjust the two sed expressions to the exact committed `_submit` lines if their spelling drifted during implementation (the control inverts the level check — with the kill file present the refusal inverts into a submission, so the probe must go red; the mutation replaces the fresh evaluation with a forged FULL verdict — "deleting the evaluate call" in D4's words). Expected verdict: control proven, mutation **KILLED** — the kill-file test observed an order reach the stub client on the mutated tree. **Read WHICH failure fired** (the test's `submitted == []` assert, not a collection error) before recording the result.
- [ ] **Step 2: The walk-test plant** — control and mutation are two different plants in the same file, so the control proves the harness bites and the mutation is the named defect:

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/node.py \
  --control 's|^logger = get_logger("engine.node")|logger = get_logger("engine.node")  # order_factory|' \
  --mutation 's|^logger = get_logger("engine.node")|logger = get_logger("engine.node")  # submit_order|' \
  -- uv run pytest tests/test_engine_executor.py::test_submit_order_and_order_factory_have_exactly_one_module -x -q
```

  The planted reference outside `executor.py` must turn the walk test red (control proven, mutation **KILLED**) — a comment plants it deliberately: the walk is a text scan, because a reference in a comment is one refactor away from being code.
- [ ] **Step 3: The operator-facing sweep**: `uv run pytest tests/test_internal_terms_not_operator_visible.py -q`, then a manual read of every NEW operator-visible string (metric HELP in `_ExecutionMetrics` and `_CycleGauges.limit_bound`, `probe-plan` `--help`, the README row, panel titles/descriptions, the two rule annotations) for internal tokens — the test walks literals, the read catches semantics.
- [ ] **Step 4: THE FULL SUITE, foreground**: `uv run pytest -q` (~40 s without the data-dependent regressions, ~7 min with `data/ohlc-full` present) — green before Task 14. Then `uv run pre-commit run -a` to clean.
- [ ] **Step 5:** No commit if all green; any fix found here lands as its own typed commit with its own targeted test run, and Steps 1–4 re-run after it.

### Task 14: Closeout

**Files:** `docs/iterations-history-phase6.md`, `docs/research/14.phase6-decisions.md`, `docs/open-topics/T0138-costmin-denomination-guard-at-the-sizing-call-site.md` + `docs/open-topics/T0140-venue-record-schema-version-is-write-only.md` (resolve + archive), `docs/open-topics/T0018-phase6-build-sequence.md`, `docs/open-topics/README.md`.

Closeout content is authored **at closeout, from the branch log** — never pre-written; this task gives the shape and the links, not prose claiming completion.

- [ ] **Step 1: Load the `iteration-closeout` skill**, then author the **iter-140** entry in `docs/iterations-history-phase6.md` from `git log` over the whole branch (what shipped; the chokepoint + write-ahead design; the machine; the trips; what is deliberately NOT deployed/armed yet — the code lands disarmed, arming is the checklist's separate act).
- [ ] **Step 2: Decisions log** — append the `[iter-140]` entries to `docs/research/14.phase6-decisions.md` per the skill's entry format, covering the interactive rulings the spec records: the maker-first-with-taker-fallback re-affirmation (owner, 2026-08-03); the engine-disposes-the-settle-residual ruling (D7 — three grounds, rejected alternatives); T0140 ruled option (a) — the schema-aware validator (D9); T0119's `target − held` ruled OUT of 00090 with grounds (D2); the T0140/T0138 dispositions (both resolve at this closeout). Options and `(Decision: N)` markers per the skill.
- [ ] **Step 3: T0138 → `resolved` + archived** per `.claude/skills/topic-ops/SKILL.md` mechanics (status flip, a `## Resolution` section naming the guard's landing site — `size_probe_order` in `cli/engine/executor.py` — and the constructed-defect test, `ripe_when` deleted, `git mv` to `archive/`, then `git add` the new path, index bullet moved to the resolved block and repointed at `archive/`).
- [ ] **Step 4: T0140 → `resolved` + archived**, same mechanics (Resolution: option (a) built — `validate_venue_record`, `{1, 2}` loadable, the two self-referential tests replaced with refusal tests; the exec ledger given the identical treatment).
- [ ] **Step 5: T0018 update in the same PR** (`open-topics.md`: the completing PR carries the topic's whole update): the spec table's `00090` row → `landed (iter-140)` with deploy state; `## Done so far` gains the iter-140 paragraph; the discharged deferral bullets are removed or rewritten as done — the probe-checklist-owes-two-items bullet (now the runbook's Disarm phase), the gate-unavoidable and ledger-unavoidable obligations (proven by Task 13's probes and Task 5's tests), the venue-panel gap bullet (Task 11), the gate-evaluation-cadence revisit (D4's ruling); the deferrals that STAY are re-pointed at their named owners (`00091`, `00092`, T0120, T0049, T0005, the T3-fallback conditional).
- [ ] **Step 6: Sweep `docs/open-topics/README.md` + the memo queue state** so the pick-time view is true (registration and queue travel together), and mention newly opened topics, if any, in the entry.
- [ ] **Step 7: Gate, stage by explicit path (docs + topic files only — claude-kind vs docs-kind split does not arise here; all are docs), commit** `docs(engine): iter-140 closeout -- the rung-1 order path lands; T0138 + T0140 resolve`.

---

## The deploy and the probe window (after merge — attended, the owner runs each step; NOT an implementer task)

Per spec D14 and `capture-deploys.md` — **the code lands disarmed; the `exec_armed=true` converge is deliberately NOT this deploy** (a code defect and a live-armed engine must never meet before a disarmed drill has run).

1. **Pre-stage**: build/pull the new engine image on the host; record the digest in `docs/reference/fleet-pins.md` (the roles refuse an unrecorded digest); verify the secondary's capture bake gate for that digest (the engine role enforces the canary mechanically).
2. **One engine converge carries the code**, inside the 4-hourly inter-cycle gap, via `infra/ansible/scripts/converge.sh` with `--check --diff` read first: `--limit zcrypto`, `--tags engine`, `-e converge_primary=true -e capture_image_digest=sha256:<...>` — and because `config.alloy` changed, the same converge carries `-e capture_alloy_digest=<currently-running>` (config-only, no bake owed; read the running digest from the container, never the compose file).
3. **Verify the converge by outcome**: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`; `zcrypto engine exec-status` on the host reads `level=none` with reasons exactly `arm_file_absent,restart_hold` (config renders `exec_armed = false` and the new `exec_max_plan_notional_eur = 100.0` appears in the converge diff); the exec-status flip drill (kill file create/remove) still flips.
4. **`infra/scripts/grafana-push.sh` pushes the board and the two annotated venue rules AFTER the converge**, verified **evaluating by value** — each rule's query returns a number, never `(no series)`; the new panels render (the execution row legitimately empty, the venue row carrying real values). No rule is superseded, so **no prune is owed** (`GRAFANA_PRUNE` stays unset).
5. **Families in Cloud read by value**: `zcrypto_venue_*` unchanged; `zcrypto_engine_limit_bound_total` present after the first post-converge cycle (a number — 0 is the expected healthy value); the `zcrypto_exec_*` execution families appear at the first probe window, not before — absent-until-then is the designed state, not a failure.
6. **NAS and ops need nothing** — no surface they run reads exec or venue records (the gate scores `cycle-*`/`failed-cycle-*` only; re-proven by Task 1's populated-record test).
7. **The probe window itself** — arming, drills, the funded plans, the settle, the disposal, the T2 verdict, disarm — runs exclusively through the `engine-probe-window` runbook section (Task 12) and its human gates G1–G6. It is a separate, later, owner-worded event; nothing in this deploy arms anything.

## Coverage self-check (spec → task)

D1→T3/5/6/9; D2→no code (bounded claim; decisions-log entry in T14); D3→T3/5 (+T9 CLI); D4→T5/10/13; D5→T1/5/10; D6→T6; D7→T7 (the spot-disposal path) + T12/attended; D8→T3/4/5; D9→T2 (+T14's T0140 resolution); D10→T7; D11→T8; D12→T10/11; D13→T12; D14→attended section. Every Verification bullet's task is named in its owning task's "Discharges" line; the deploy-verification bullet is the attended section.
