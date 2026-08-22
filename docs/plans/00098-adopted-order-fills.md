# 00098 — Adopted-order fills observable — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A restart-adopted resting order's fills append to their forensic row, move the execution counters, and keep the overfill trip — while the operator's hand settle stays structurally invisible to the kill switch and becomes *counted* (spec `00098`, resolving `T0142`).

**Architecture:** One new delivery path, zero new bookkeeping: `node.py` subscribes the strategy's msgbus to `events.order.EXTERNAL` and forwards to a new executor entry `on_external_order_event`, which is a **disposition filter** — unmatched events are counted+logged and never touch the pipeline; matched events are delegated into the *existing* `_trip_on_fill` → `_on_detached_event` machinery, which already does the row append, fill mirroring, counters, and the matched-overfill trip. Terminal events on matched rows additionally close the row and end tracking.

**Tech Stack:** nautilus-trader 1.230.0 (pinned — PR #270 deliberately untouched), prometheus_client, pytest.

## Global Constraints

- **The own-topic path is byte-untouched**: `on_order_event`, `_on_order_event`, `_trip_on_fill`, `_on_detached_event` keep their existing behaviour for own-strategy events. **No pre-existing assertion is weakened, and exactly three pre-existing test surfaces are deliberately edited, red-first** (cold review F1/F6 — the blanket untouched rule was unsatisfiable): (1) `test_engine_node.py::test_no_module_widens_the_engines_order_event_stream` bans the literal text `msgbus` in every `cli/**/*.py` — widen it BEFORE the code change with an allowlist admitting exactly `cli/engine/node.py` for `msgbus` (keep `external_order_claims` banned everywhere, `msgbus` banned in every other cli file), and re-prove the widened guard by planting `msgbus` in `executor.py` and seeing red; (2) `test_engine_node.py`'s `_exec_stub` (a SimpleNamespace with no `msgbus`) gains a recording msgbus stub — the executor-wired `on_start` would otherwise raise `AttributeError` — and that stub is the vehicle for the new subscription assertions; (3) the `test_engine_executor.py:~2104` docstring stating the unobservability as standing fact is rewritten to the new truth. Additionally, the pre-existing test doubles gain the methods the new contract requires -- `test_engine_node.py`'s `RecordingExecutor` (`on_external_order_event` + `external_events`) and `test_engine_executor.py`'s metrics fakes (`inc_external`) -- purely additive, no pre-existing assertion touched (Task 3's review adjudicated the additions as forced by the contract). Every other pre-existing test passes untouched; any edit that changes an existing assertion is a defect.
- **`external_order_claims` stays unset** — grep proves no occurrence outside comments/docs after the change.
- **An unmatched external event must never reach `_trip_on_fill`, any row write, or any cancel** — this is the scope property; it gets its own test and its own mutation proof.
- `cli/engine/executor.py` does not import nautilus beyond its existing two lines — event dispatch stays duck-typed on `type(event).__name__`, matching the file's idiom. The topic string lives in `node.py` (which already imports nautilus).
- Metric HELP text carries no internal tokens (`tests/test_internal_terms_not_operator_visible.py` sweeps it).
- Counter label children pre-registered at 0 (the `_ExecutionMetrics` class's own documented idiom).
- Everything through `uv run …`; commit gate `uv run pre-commit run -a`; commits per `commit-messages.md`.

## File map

- `cli/engine/command.py` — `_ExecutionMetrics` gains the external-events counter (Task 1).
- `cli/engine/executor.py` — `_inc_external` helper + `on_external_order_event`/`_on_external_event` (Tasks 1–2), `_adopt_resting_orders` docstring rewrite (Task 5).
- `cli/engine/node.py` — subscription + forwarder + class-docstring extension (Task 3).
- `infra/ansible/roles/capture/files/config.alloy` keep-regex + `tests/test_infra_alloy_series.py` + `infra/grafana/engine-dashboard.json` (Task 4).
- `infra/runbooks/engine.md` arm step + `docs/research/14.phase6-decisions.md` (Task 5).
- Closeout: T0142 + index + memo + `docs/iterations-history-phase6.md` (Task 6).

---

### Task 1: The counter and its plumbing

**Files:** Modify `cli/engine/command.py` (~line 610), `cli/engine/executor.py` (~line 131). Test: `tests/test_engine_metrics.py`.

**Interfaces — Produces:** `_ExecutionMetrics.inc_external(disposition: str)`; module-level `_inc_external(disposition)` in executor.py (None-safe, mirroring `_inc_order`); `_EXEC_EXTERNAL_DISPOSITIONS = ("matched", "unmatched")` in command.py.

- [ ] **Step 1: Failing test** (mirror `tests/test_engine_metrics.py`'s existing pin idiom — read it first):

```python
def test_external_events_counter_preregisters_both_dispositions(...):
    # both label children exist at 0 before any event; inc_external moves exactly one
```

The tuple-exists and counter-registers pins land here; the call-site half of the pin (`_EXEC_EXTERNAL_DISPOSITIONS` against `_inc_external`'s call sites) lands in **Task 2 Step 1** with the call sites themselves (cold review F7 — a red pin cannot ride through Task 1's green commit gate).

- [ ] **Step 2: Implement.** In `_ExecutionMetrics.__init__`:

```python
        self.external_events = Counter(
            "zcrypto_exec_external_events_total",
            "Order events arriving on the external strategy topic, by disposition: matched means the "
            "event belonged to a restart-adopted order this engine's ledger vouches for; unmatched "
            "means it belonged to no such order and was counted and ignored.",
            ["disposition"],
            registry=registry,
        )
        for disposition in _EXEC_EXTERNAL_DISPOSITIONS:
            self.external_events.labels(disposition=disposition)
```

with `inc_external` beside `inc_order`, and in executor.py a `_inc_external(disposition)` mirroring `_inc_order` exactly (None-safe via `_metrics`). Wire it through whatever installs the sink (`set_metrics_sink` pattern — read command.run()'s installation and mirror).

- [ ] **Step 3: Run** `uv run pytest tests/test_engine_metrics.py -q` — green. **Step 4: Commit** `feat(engine): external-events counter, both dispositions pre-registered`.

---

### Task 2: The disposition filter in the executor

**Files:** Modify `cli/engine/executor.py` (new methods after `on_order_event`, ~line 1262). Test: `tests/test_engine_executor.py` (its `_fill(...)` helper at ~line 1096 constructs real `OrderFilled` events — reuse it; never invent a parallel fixture).

**Interfaces — Produces:** `on_external_order_event(event)` (public, wrapped) — Task 3 forwards to it.

- [ ] **Step 1: Failing tests** (each guard constructed and seen to trip, plus true positives):

```python
def test_external_fill_on_an_adopted_row_appends_and_counts(...):
    # seed a ledgered row + _attached (the adopt-pass fixtures already exist in this file — reuse);
    # deliver _fill(...) via on_external_order_event; assert: row filled_qty grew, events appended,
    # fills counter moved, kill NOT tripped, disposition counter matched=1

def test_external_fill_on_an_unknown_order_is_counted_and_nothing_else(...):
    # deliver a _fill for a client_order_id with no attached row; assert: unmatched=1, NO row write
    # anywhere, kill NOT tripped, no cancel issued — this is the hand-settle scope property

def test_external_overfill_on_an_adopted_row_trips_the_kill(...):
    # attached row with ordered qty Q; deliver fill of Q + 2*_OVERFILL_TOLERANCE; assert kill
    # latched, the fill itself journaled (no-fill-without-a-record), matched=1

def test_external_terminal_event_closes_the_row_and_ends_tracking(...):
    # deliver an OrderCanceled-shaped event for an attached row; assert row state is the ledger's
    # existing terminal name (read validate_exec_record's allowed states and reuse — never mint a
    # new state string), the entry left _attached, matched=1

def test_external_handler_never_raises_into_the_event_loop(...):
    # monkeypatch update_submitted_row to raise; deliver a matched fill; assert logged, no raise

def test_external_dispositions_are_pinned_against_their_call_sites(...):
    # the F7 pin, landing here WITH the call sites: mirror how _EXEC_ORDER_OUTCOMES is derived
    # from _inc_order("...") call-site scanning, for _inc_external; also add the
    # "pinned against that module's own call sites" clause to the tuple's comment (Task 1
    # deliberately omitted it while it would have been false)
```

- [ ] **Step 1b: The test fakes follow the contract** — `tests/test_engine_executor.py`'s hand-rolled metrics fakes (incl. `_RaisingMetrics`) gain `inc_external`; without it, `_inc_external`'s swallow turns a wiring regression into a silently-vacuous assertion (Task 1's review named the direction). One of Task 2's unmatched-path tests must assert the UNMATCHED label moved — that call site also closes the reviewer's probe E (a helper ignoring its argument currently survives).

- [ ] **Step 2: Implement:**

```python
    def on_external_order_event(self, event) -> None:
        try:
            self._on_external_event(event)
        except Exception:
            # Bookkeeping on an adopted order, never a submission: log and continue (the
            # on_order_event idiom).
            logger.exception("executor external-order-event handling raised -- continuing")

    def _on_external_event(self, event) -> None:
        """Events from `events.order.EXTERNAL` (spec 00098 D1): the delivery path for orders this
        process adopted at startup, filtered by disposition BEFORE anything else runs.

        Matched (the ledger vouches for the order): delegate into the existing pipeline --
        `_trip_on_fill` first, exactly as the own-topic path does, so a matched overfill trips the
        kill with the same arithmetic; a clean fill lands in `_on_detached_event`, which already
        appends the row by the order's own boundary, mirrors the quantity, and publishes counters.
        Terminal events additionally close the row and end tracking, which the detached path
        deliberately does not do for own orders.

        Unmatched (the operator's hand settle, any genuinely external act): counted, logged, and
        NOTHING else -- it must never reach `_trip_on_fill`, a row write, or a cancel. That filter
        is what keeps the unknown-order trip scoped while this subscription exists at all.
        """
        client_order_id = str(getattr(event, "client_order_id", ""))
        attached = self._attached.get(client_order_id)
        name = type(event).__name__
        if attached is None:
            _inc_external("unmatched")
            logger.info(
                "external order event ignored: %s for %s on %s -- no ledgered adopted row",
                name, client_order_id, getattr(event, "instrument_id", "?"),
            )
            return
        _inc_external("matched")
        if name == "OrderFilled":
            if self._trip_on_fill(event):
                return
            self._on_detached_event(client_order_id, event)
            return
        payload = {"type": name, "at": self._now().isoformat()}
        reason = getattr(event, "reason", None)
        if reason is not None:
            payload["reason"] = str(reason)
        boundary, _row = attached
        terminal_state = _EXTERNAL_TERMINAL_STATES.get(name)
        update_submitted_row(self._journal_dir, boundary, client_order_id, state=terminal_state, event=payload)
        if terminal_state is not None:
            # NO pop -- neither path ever removes from _attached (amended D2/D4: the no-pop symmetry)
```

with `_EXTERNAL_TERMINAL_STATES = {"OrderCanceled": "canceled", "OrderExpired": "venue_canceled", "OrderRejected": "rejected"}` — ruled by the cold review from `validate_exec_record`'s existing names: on this path `canceled` makes no we-requested claim (the dominant real source is the adopt pass's or a trip's own cancel, whose ack now arrives matched — say so in a docstring sentence), expiry is the venue's own doing, and `OrderCancelRejected` deliberately stays out of the map (event append, row stays attached). **Two additions to the matched-fill branch**: after `_on_detached_event`, when `row["filled_qty"]` has reached `_ordered_qty(row) - _OVERFILL_TOLERANCE`, mark the row `"filled"` via `update_submitted_row(state="filled")` and `_inc_order("filled")`, guarded once via the in-memory state mirror — NO pop (amended D2/D4) — nautilus publishes no terminal event after a resting order's final fill, so without this the row reads open forever. And one added assertion: the adopt pass's own cancel acks now CLOSE their rows (state `canceled`), which previously stayed open on every future scan.

- [ ] **Step 2b: One docstring sentence for the active-intent credit** (cold review F8): `_on_detached_event`'s credit of a running intent is inert for adopted rows because `plan_refusals` refuses any `plan_id` already in `ledgered_plan_ids`, scanned over the same two-UTC-day window as `open_submitted_rows` — a running plan can never share a plan_id with a row adopted at startup. The boundary: `_attached` outlives that window, so a process running ≥2 days past the adopted boundary could accept a reused plan_id. Name the dedupe and its two-day boundary where the credit happens; no code change.
- [ ] **Step 3: Run the file** — new tests green, pre-existing green per the re-scoped constraint. **Step 4: Mutation proof** (worktree; assert `cli.__file__`; read which assertion fires): (a) remove the unmatched early-return → the scope-property test must fail on the trip/row assertions; (b) swap the delegation order (detached before trip) → caught by the **clean full fill** test, not the overfill one (cold review F5: the overfill assertions all still pass under the swap) — so the clean-fill test MUST use a fill that completes the ledgered quantity and assert no trip, and the overfill test additionally asserts **exactly one** fill event in `row["events"]` (the swap double-journals). **Step 5: Commit** `feat(engine): external-topic events reach adopted rows through a disposition filter`.

---

### Task 3: The subscription, the forwarder, and the library-boundary tripwire

**Files:** Modify `cli/engine/node.py` (`ShadowStrategy.on_start` + a forwarder + the class docstring). Test: `tests/test_engine_node.py`.

- [ ] **Step 1: Failing tests.** Extend `tests/test_engine_node.py`'s existing scoping pins (the docstring says it "pins both halves" — read how, and add the third half): (a) with an executor wired, `on_start` subscribes to exactly `events.order.EXTERNAL` and the handler forwards to `executor.on_external_order_event`; (b) with `executor_factory=None`, no subscription is made. Then the tripwire, in whichever engine test file already constructs nautilus components:

```python
def test_the_external_topic_string_matches_the_installed_engines_format(...):
    # Build a real nautilus MessageBus (read the library's own tests/quickstart for the minimal
    # constructor: trader_id, clock, ...); subscribe our literal topic; publish a constructed
    # OrderFilled through msgbus.publish(topic=f"events.order.{StrategyId('EXTERNAL')}", ...) using
    # the SAME f-string shape engine.pyx:910 uses; assert delivery. If a future nautilus renames
    # the topic, this fails here, not in production (the PR #270 tripwire).
```

- [ ] **Step 2: Implement.** In `on_start`, after the executor is constructed:

```python
            self.msgbus.subscribe(topic=_EXTERNAL_ORDER_TOPIC, handler=self._on_external_order_event)
```

with module-level `_EXTERNAL_ORDER_TOPIC = f"events.order.{StrategyId('EXTERNAL')}"` (nautilus is already imported here), a forwarder mirroring the other three:

```python
    def _on_external_order_event(self, event) -> None:
        if self._executor is not None:
            self._executor.on_external_order_event(event)
```

and the class docstring extended: the claim list is still empty and the own-topic scoping still holds; the EXTERNAL topic is now *additionally* subscribed, delivering to a filter that acts only on ledger-vouched adopted rows — the hand settle remains structurally unable to reach the trip.

- [ ] **Step 3: Run** `uv run pytest tests/test_engine_node.py tests/test_engine_executor.py -q` — green, pre-existing untouched. **Step 4: Commit** `feat(engine): subscribe the external order topic, forward through the filter`.

---

### Task 4: The metric's lifecycle surfaces

**Files:** Modify `infra/ansible/roles/capture/files/config.alloy` (the keep-regex — add `zcrypto_exec_external_events_total` beside the other `zcrypto_exec_*` families), `tests/test_infra_alloy_series.py` (the engine section's hand-pinned list + any count comments — count the names yourself; that comment has been wrong three times), `infra/grafana/engine-dashboard.json` (a target on whichever panel carries the exec counters; the charted-family guard names the panel when it goes red).

- [ ] Red-first: after Task 1's counter exists there are **two** live reds, and Task 4's own keep-regex edit induces a **third** (Task 1's review proved it arrives then, not before): the charted-family guard, the alloy admission test, and `tests/test_infra_alert_rules.py::test_every_fault_signal_metric_is_watched_by_a_rule[zcrypto_exec_external_events_total]` — that test derives fault signals from the capture keep-regex minus `NOT_A_FAULT_SIGNAL`, so the moment the family joins the regex it demands an alert rule or a reasoned exclusion. The ruling: add a `NOT_A_FAULT_SIGNAL` entry beside the other exec instruments, reusing their attended-window-instrument reasoning — this counter is a forensic instrument, not a fault signal; a nonzero unmatched count is information, not a page. Fix all three forward from red. Commit `feat(obs): admit and chart the external-events family`. **Deploy note for the closeout, verbatim from the spec: the engine converge that ships this must run `--tags capture,engine` with both currently-running digests — the keep-regex lives in the capture role.**

---

### Task 5: The doc surfaces that move together

**Files:** `cli/engine/executor.py` (`_adopt_resting_orders` docstring — the paragraph stating the unobservability), `infra/runbooks/engine.md` (the arm step's read-venue-truth paragraph), `docs/research/14.phase6-decisions.md` (the `[iter-]` entry: D1's choice against the topic's three candidates, options + `(Decision: N)` per the `iteration-closeout` format).

- [ ] Rewrite both prose surfaces **in place** to the new truth: adopted-order fills append to their rows and move counters through the external-topic subscription; a matched overfill trips exactly as before; the hand settle remains invisible to the trip *by the filter, not by accident*, and is now counted (`zcrypto_exec_external_events_total{disposition="unmatched"}`). Sweep for the CLAIM (variants: "never reaches this handler", "unobservable", "reconciled only as venue truth", "read such an order from venue truth", "no such fill actually arrives") across `cli/engine/`, `infra/runbooks/`, `docs/`, **and `tests/`** (cold review F6: `test_engine_executor.py:~2104`'s docstring states the unobservability as standing fact) — every live carrier moves; point-in-time records are named, not edited. Commit `docs(engine): the adopted-order surfaces say what is now true`.

---

### Task 7: The adopt pass reconciles against venue truth (spec D7 -- added after the whole-branch review)

**Files:** Modify `cli/engine/executor.py` (`_adopt_resting_orders` only -- its body, untouched by this branch until now), `tests/test_engine_executor.py` (new tests + the existing adopt fixtures' stub cache).

**Interfaces:** consumes `_OVERFILL_TOLERANCE`, `_ordered_qty`, `_mirror_row_fill`, `_trip_kill`, `_inc_order`, `update_submitted_row`, `_EXTERNAL_TERMINAL_STATES`'s vocabulary. Produces no new public name.

- [ ] **Step 1: Read the installed source before writing anything.** Confirm from `.venv/lib/python3.14/site-packages/nautilus_trader/`: (a) `Cache.orders(venue=...)` returns closed orders as well as open ones -- name the signature you read; (b) how an order's terminal status is read from the object (the accessor and the enum's spelling), since the row's terminal state is mapped from it; (c) that `Order.filled_qty` is a `Quantity` and `float()` of it is exact for the venue's own quantities. Record all three in the report. If (a) is false, STOP and report -- the closed-while-down sweep has no source and the task's shape changes.
- [ ] **Step 2: Write the failing tests FIRST**, one per D7 disposition, against the existing adopt fixtures (`tests/test_engine_executor.py`'s stub cache -- extend it to answer `orders(venue=...)` alongside `orders_open`, and give its order objects a settable `filled_qty`):
  - positive delta journals: row ordered 0.001, ledgered `filled_qty` 0.0, cache order `filled_qty` 0.0004 -> after `on_timer`, the stored row reads 0.0004, carries a reconciliation event naming the delta, and `_attached`'s in-memory row mirrors it.
  - a delta that COMPLETES: cache order `filled_qty` == ordered -> row state `filled`, `_inc_order("filled")` counted exactly once.
  - a delta that OVERSHOOTS: cache order `filled_qty` above ordered + tolerance -> kill latched, and the repair still journaled (no-record-without-the-fill).
  - NEGATIVE delta: ledgered `filled_qty` above the cache order's -> kill latched.
  - closed-while-down: `orders_open` returns EMPTY, `orders` returns one CLOSED order matching an open row -> row repaired AND given its terminal state; this is the case that proves the early return moved.
  - idempotence: a second `on_timer` after `_adopted` changes nothing (no second append).
  - untouched: a row whose `filled_qty` already equals the cache order's gets NO write at all (the common clean restart must stay silent).
- [ ] **Step 3: Run them and read WHICH assertion fails** on each -- a test that fails for a missing stub method has proven nothing yet.
- [ ] **Step 4: Implement in `_adopt_resting_orders`.** Order of operations: read the wide order list (failure -> the existing critical-log-and-return, `_adopted` NOT set); set `_adopted`; read rows; **reconcile sweep**; then the existing classification loop over the resting list only, unchanged. The `if not resting: return` early-out MOVES to after the sweep -- the closed-while-down case has no resting orders by definition. Keep every existing log line and cancel behaviour byte-identical.
- [ ] **Step 5: Green, then the guard proofs.** Run the new tests plus the whole adopt/trip suite. Then, via `infra/scripts/mutate-probe.sh` (one at a time, reading WHICH assertion fires): delete the mirror -> the trip-base test bites; clamp the negative delta to zero -> the negative-delta test bites; leave the early return where it was -> the closed-while-down test bites.
- [ ] **Step 6: Docstring + commit.** `_adopt_resting_orders`' docstring gains the reconcile paragraph (it currently states the D1 story as the whole story). Commit `feat(engine): the adopt pass reconciles each row against venue truth`.

---

### Task 6: Closeout — **the orchestrator's, not a subagent's**

- [ ] T0142 → `resolved` + archive + index (topic-ops mechanics; the `ripe_when` never fired — resolved by owner fiat ahead of ripeness, say so); memo updated; iterations-history entry (the two-machine claim discipline: every number from the tests, none invented).
- [ ] Whole-branch review at the **Fable floor** (live trade path — mandatory), findings fixed, trailers amended.
- [ ] PR on the user's word; the deploy rides the next canary-gated `--tags capture,engine` converge, stated in the PR body.

## Self-review

1. **Spec coverage**: D1→Task 3, D2→Task 2, D3→Tasks 1+4, D4→Tasks 2-3, D5→Task 6/PR body, D6→Task 5. Verification section→Tasks 2-3 tests + mutation proofs.
2. **Placeholders**: Task 1 Step 1 and Task 3 Step 1 sketch test shapes with prose contracts — deliberate; the fixtures they must reuse exist and are named. Everything else is concrete.
3. **Type consistency**: `on_external_order_event` (Tasks 2, 3); `_inc_external` (Tasks 1, 2); `_EXEC_EXTERNAL_DISPOSITIONS` (Tasks 1, 2); `_EXTERNAL_ORDER_TOPIC` (Task 3 only).
