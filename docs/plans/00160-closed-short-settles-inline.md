# An order Kraken closes short of its size settles at the refused cancel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At a cancel the venue refuses, the executor reads Kraken's record of the order, and an order Kraken reports closed with exactly the fill the engine recorded ends its row and its intent `filled` and the plan runs its next intent; every other answer stays `ambiguous` with the remainder dropped, its CRITICAL line naming the answer.

**Architecture:** The active intent keeps its live order's Kraken txid from the order's acceptance (D3). The refused-cancel arm of `_on_order_event` calls one new method, `_settle_refused_cancel`, which reads `read_venue_orders` on its own terms — armed, nothing in flight, the txid known — and settles row 1 of the spec's answers or returns the phrase the arm's CRITICAL line names (D2–D6). The resume is the tick's ordinary `_start_intent`, unchanged (D5). Two cases pin the adapter's and the state machine's premises (D9); the error-logs runbook and the rung-3 daily read say what each line means (D6); the decisions log takes the ruling and the author's three calls, and T0229 closes.

**Tech Stack:** Python 3.14, pytest, `nautilus-trader` 2.0.0rc9.dev20261106, `tests/kraken_loopback.py`, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00160-closed-short-settles-inline-design.md`

**Tier** — `uv run python infra/scripts/tier.py --paths cli/engine/executor.py tests/test_engine_executor.py infra/runbooks/engine.md infra/runbooks/engine-procedures.md docs/research/14.phase6-decisions.md docs/open-topics/T0229-an-order-kraken-closes-short-of-its-size-ends-its-intent-ambiguous.md docs/open-topics/archive/T0229-an-order-kraken-closes-short-of-its-size-ends-its-intent-ambiguous.md docs/open-topics/README.md`, run at `a11aa9f4a`:

```
tier: full
full cli/engine/executor.py — under cli/engine/, read as a non-prose change
full tests/test_engine_executor.py — a test importing cli.config, read as a non-prose change
```

Every fence below was run against `ac3064f6b` in a detached scratch worktree before this plan was committed: the tasks' cases pass with the code applied, 29 of Task 2's Step 3 selection fail without it, and each probe arm listed reads `KILLED (control proven, tree restored byte-identically)`.

## Global Constraints

- The spec is the authority; where it is silent this plan rules, in *Rulings* below.
- No task hands the adapter defect upstream or converges anything: the hand-off is the coordinator's (spec D8), and the change ships on the engine image spec D10 names, the converge the fleet's concern.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0229` (branch `feat/t0229-closed-short-settles-inline`); every command runs with it as the working directory, and git takes `-C` that path. The main checkout is live.
- No converge, image build, push, network call or `grafana-query.py` read in a task. Every venue read in a test goes to `tests/kraken_loopback.py` or a stub; the autouse `_no_production_venue_read` fixture fails a case that reaches the production reader, so a case that delivers `OrderCancelRejected` on the own path hands the executor a `venue_orders` reader.
- Tests per commit: `mkdir -p .tmp/implementer .local/closed-short-settles-inline` first, its own call; then `infra/scripts/consumers.sh --tests --direct <the commit's changed paths> 2>.tmp/implementer/cons.err >.tmp/implementer/cons.list`, its own call, exit 2 meaning no reader; `cat .tmp/implementer/cons.err`, its own call; then `T="$(sort -u .tmp/implementer/cons.list | tr '\n' ' ') <the task's test files>"; uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`. Never the full suite. A step's own run names `-k` cases.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. A runbook page and an engine string literal carry no `spec <NNNNN>`, `D<N>`, `T<NNNN>`, `iter-<N>`, `Phase <N>` or `WP<N>` token (`tests/test_internal_terms_not_operator_visible.py`).
- Commits: Conventional Commits, one subject per change, after a `git -C <the worktree> add <every path the commit changes>` of its own, through `git -C <the worktree> commit -F - <<'EOF'`; the message says what changed and pastes the result line of the test command it names, run over the commit's own tree; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the implementer's own model in place of the placeholder, and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`.
- Probes (this plan's tier is `full`): each arm a task lists runs as its own call on the committed tree, `infra/scripts/mutate-probe.sh --file <file> --control '<control>' --mutation '<mutation>' -- uv run pytest tests/test_engine_executor.py -k '<selection>' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`, the control `1,$d` unless the arm names another. Before each arm its pattern's count reads `1`: `grep -c '<pattern>' <file>`, or, for an arm whose mutation opens with the settle's range `/def _settle_refused_cancel/,/def _on_rejected/`, `awk '/def _settle_refused_cancel/,/def _on_rejected/' cli/engine/executor.py | grep -c '<pattern>'`. `: > .local/closed-short-settles-inline/probes-task-<N>.txt` before a task's arms; after each arm its id and the script's last line are appended, its own call. A task's verdicts ride an empty commit, `git commit --allow-empty -F <message file>`, subject `test(engine): <task> proven by infra/scripts/mutate-probe.sh`, its body the probes file whole and the trailers.
- A helper this plan names in a test (`_executor`, `_resting_executor`, `_boundary_executor`, `_VenueOrders`, `_report`, `_resting_limit_order`, `_left_pending_cancel`, `_fill`, `_deliver_fill`, `_event`, `_accepted`, `_canceled`, `_quote`, `_intent`, `_plan_dict`, `_drop_plan`, `_Clock`, `_advance_with_quotes`, `_record`, `_intent_entry`, `_intent_outcome`, `_boundary`, `_executor_errors`, `_rung2_record`, `_only`, `_loopback_credentials`, `RecordingMetrics`, `StubClient`, `NOW`, `_RUNG2_12Z`, `_TXID`) exists in `tests/test_engine_executor.py` at `ac3064f6b`; where a fence's call does not fit its real signature, the case's intent and assertions bind, not the spelling, and the report says what changed.

## Rulings where the spec is silent

- **The settle is one method, `_settle_refused_cancel(self, active: _ActiveIntent, reason) -> str | None`, directly above `_on_rejected`.** None means it settled and ended the intent; a string is the `<answer>` the arm's CRITICAL line carries (spec D6). The probe arms address it by the range from its `def` to `_on_rejected`'s.
- **The acceptance sets the txid before the payload reads it.** `active.venue_order_id = str(event.venue_order_id)` then `payload["venue_order_id"] = active.venue_order_id`: a `payload["venue_order_id"]` read inside `_on_order_event` is a read of the ledger's txid key, which `test_every_read_of_a_rows_txid_or_its_cache_copy_goes_through_the_one_door_and_every_intent_writer_is_listed` refuses outside `_read_id`.
- **The read's seconds come from the executor's own clock** (`self._now()` before and after), so a case's fixed clock reads `0.0 s` and the line is pinned whole.
- **The mirror row in `_attached` takes no `filled` state.** Its `state` is read for a restored row (`_on_detached_event`) and an adopted one (`_on_external_event`), and a running intent's own row is neither.
- **The two lines that carry a traceback** — the in-flight read's and the venue read's failures — log it at WARNING with `exc_info=True`; the CRITICAL line names the exception's class alone, so the page's 200-character hoist reads the answer.
- **`_reconcile_terminal`'s docstring gains one sentence**, after "which is the state that path exists to produce.": "A refused cancel Kraken's record settles (`_settle_refused_cancel`) is none of them: the venue answered, so it reaches this as any terminal does." The refused-cancel arm's comment says the settle comes first. `_drop_remainder_after_ambiguity`'s "Five callers" stays true and is left.
- **The premise cases sit beside their kin:** the loopback case directly before `test_read_venue_orders_answers_past_a_closed_order_on_a_pair_the_listing_lacks`, the state-machine case directly after `test_a_cancel_the_client_denied_before_sending_parks_the_intent_ambiguous_at_once_and_halts_the_plan`, and Task 2's block directly after the state-machine case.
- **The runbook texts are the spec's *Runbook texts*, verbatim**, and the decisions-log entry is Task 4's fence, verbatim.

## File structure

- Modify `cli/engine/executor.py`: `_ActiveIntent.venue_order_id`; `_place`; the `OrderAccepted` arm; the refused-cancel arm; `_settle_refused_cancel`; `_reconcile_terminal`'s docstring.
- Modify `tests/test_engine_executor.py`: `_report`, `_boundary_executor`, `test_a_cancel_rejection_parks_the_intent_ambiguous_and_halts_the_plan`, and the new cases.
- Modify `infra/runbooks/engine.md`, `infra/runbooks/engine-procedures.md`, `docs/research/14.phase6-decisions.md`; move `docs/open-topics/T0229-an-order-kraken-closes-short-of-its-size-ends-its-intent-ambiguous.md` to `docs/open-topics/archive/`; re-render `docs/open-topics/README.md`.

## Review Focus

1. The measured case, an order closed three lot steps short with the fill the engine recorded, settles `filled` and the plan places its next intent. Pinned by Task 2's `test_a_refused_cancel_kraken_reports_closed_with_the_recorded_fill_ends_filled_and_the_plan_goes_on`.
2. No status but FILLED settles, enumerated over the library's own `OrderStatus.variants()`, so a status a wheel adds is a case and not a gap. Pinned by Task 2's `test_a_refused_cancel_kraken_reports_in_any_status_but_filled_stays_ambiguous`.
3. A FILLED figure apart from the recorded one — a fill the stream has not delivered, one Kraken no longer reports, or nothing filled — settles nothing, so the terminal's reconciliation never trips on a repair made here. Pinned by `test_a_refused_cancel_kraken_reports_filled_with_another_figure_stays_ambiguous` and `test_a_refused_cancel_of_an_unfilled_order_kraken_reports_closed_with_nothing_filled_stays_ambiguous`.
4. A read the engine must not make is not made: disarmed, an order in flight or a Cache that cannot say, no txid, a replacement whose acceptance has not landed reading the earlier order's record, or a cancel the client denied. Pinned by Task 2's six cases whose names carry `reads_nothing`.
5. The resume honours the window and the gate: a settle past the window's close carries the next intent, and one with a kill file placed refuses it. Pinned by `test_a_refused_cancel_that_settles_past_the_windows_close_carries_the_next_intent` and `test_a_refused_cancel_after_a_kill_file_settles_and_the_later_intents_are_refused_by_the_gate`.
6. A read that raises — the 30 s bound, the venue's error, a running asyncio loop on a future wheel — fails closed. Pinned by `test_a_refused_cancel_whose_read_raises_stays_ambiguous`.

---

### Task 1: The two premises the settle rests on (spec D9)

**Files:**
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `read_venue_orders(since, *, base_url)`, `kraken_loopback.closed_order`, `_resting_limit_order`, `_fill`, `_event`.
- Produces: nothing a later task calls.

- [ ] **Step 1: Write the two cases.** Directly before `test_read_venue_orders_answers_past_a_closed_order_on_a_pair_the_listing_lacks`:

```python
def test_read_venue_orders_reads_an_order_kraken_closed_short_as_filled_at_its_executed_volume(_loopback_credentials):
    """What the refused cancel's settle reads: Kraken's `closed` with `vol_exec` under `vol` reads FILLED at `vol_exec`,
    its reason carried as `cancel_reason` -- the 2026-11-11 DOT sell's shape, three lot steps short."""
    row = kraken_loopback.closed_order(
        "XBTEUR", price="30000.0", volume="0.00100003", side="sell", status="closed", vol_exec="0.00100000"
    )
    row["reason"] = "Insignificant volume remaining"
    with kraken_loopback.serve() as venue:
        venue.closed_orders[_TXID] = row
        [report] = read_venue_orders(NOW - timedelta(hours=9), base_url=venue.base_url)

    assert (report.order_status, float(report.filled_qty), float(report.quantity), report.cancel_reason) == (
        OrderStatus.FILLED,
        0.001,
        0.00100003,
        "Insignificant volume remaining",
    )
```

Directly after `test_a_cancel_the_client_denied_before_sending_parks_the_intent_ambiguous_at_once_and_halts_the_plan`:

```python
def test_an_order_whose_cancel_the_venue_refused_is_open_and_not_in_flight():
    """The library's own state machine: a refused cancel returns the order to its status before the cancel, so the
    Cache's in-flight set the settle's read waits on no longer holds it."""
    order = _resting_limit_order("O-1")
    order.apply(_fill("O-1", 0.4))
    order.apply(_event(OrderPendingCancel, client_order_id="O-1"))
    assert order.is_inflight
    order.apply(_event(OrderCancelRejected, client_order_id="O-1", reason="EOrder:Unknown order"))

    assert (order.status, order.is_inflight, order.is_open) == (OrderStatus.PARTIALLY_FILLED, False, True)
```

- [ ] **Step 2: Run them, expect PASS.** `uv run pytest tests/test_engine_executor.py -k 'closed_short_as_filled or refused_is_open_and_not_in_flight' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` reads `2 passed`. They pin the pinned wheel's behaviour, so they pass on the base; their probes in Step 4 are what prove each can fail.

- [ ] **Step 3: Commit** `test(engine): the adapter reads a closed-short order filled and a refused cancel leaves it out of flight`, the per-commit test run's result line in the body, after the gate.

- [ ] **Step 4: Probes**, each on `tests/test_engine_executor.py`, whose control `1,$d` would collect nothing, so each takes its own control, an `assert False` after the case's `def`:
  - `adapter`: control `/def test_read_venue_orders_reads_an_order_kraken_closed_short_as_filled_at_its_executed_volume/a\    assert False`, mutation `s/volume="0.00100003", side="sell", status="closed"/volume="0.00100003", side="sell", status="canceled"/`, `-k 'closed_short_as_filled'`.
  - `state-machine`: control `/def test_an_order_whose_cancel_the_venue_refused_is_open_and_not_in_flight/a\    assert False`, mutation `/order.apply(_event(OrderCancelRejected, client_order_id="O-1", reason="EOrder:Unknown order"))/d`, `-k 'refused_is_open_and_not_in_flight'`.

  Then the empty commit, `test(engine): the two premises proven by infra/scripts/mutate-probe.sh`.

### Task 2: The refused cancel reads Kraken's record and settles a closed-short order (spec D2–D7)

**Files:**
- Modify: `cli/engine/executor.py`
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `read_venue_orders(since) -> list[OrderStatusReport]` through `self._venue_orders or read_venue_orders`; `_finish_active(outcome, reasons, filled_qty)`; `_update_row(active, *, state, event)`; `_inc_order(outcome)`.
- Produces: `_ActiveIntent.venue_order_id: str | None`; `ProbeExecutor._settle_refused_cancel(active, reason) -> str | None`; the row event `{"event": "venue_closed", "at", "venue_order_id", "venue_filled_qty", "venue_qty", "reason"}`; `_report(..., cancel_reason=None)` and `_boundary_executor(..., venue_orders=None)` in the tests.

- [ ] **Step 1: The helpers and the existing case.** In `tests/test_engine_executor.py`: `_report` takes `cancel_reason=None` after `quantity` and passes `cancel_reason=cancel_reason` to `OrderStatusReport` after `client_order_id=None`; `_boundary_executor` takes `venue_orders=None` after `listed_floors=None` and passes `venue_orders=venue_orders` to `_executor` after `instrument_statuses=...`. `test_a_cancel_rejection_parks_the_intent_ambiguous_and_halts_the_plan` reads Kraken's empty answer, its docstring and its first and fourth statements becoming:

```python
    """The venue positively says the cancel failed, and Kraken's order read does not return the order, so it may
    still rest. Nothing may be submitted against a position this process can no longer describe."""
    venue = _VenueOrders()
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)], venue_orders=venue
    )
```

```python
    assert len(client.submitted) == 1 and venue.calls == [_boundary(NOW) - timedelta(hours=1)]
```

- [ ] **Step 2: Write the failing cases**, directly after Task 1's `test_an_order_whose_cancel_the_venue_refused_is_open_and_not_in_flight`. One case per row of the spec's *The answers*, and three for the resume:

```python
# The order's 0.001 closed three lot steps short: the 2026-11-11 DOT sell's 5.18909575 of 5.18909578.
_SHORT = 0.00099997
_INSIGNIFICANT = "Insignificant volume remaining"


def _refused_after_a_short_fill(tmp_path, *reports, raises=None, filled=_SHORT):
    """A plan of two intents whose first order, filled `filled` of its 0.001 with no terminal event, has its box's
    cancel out; the venue's orders answer `reports`, or raise `raises`. The refusal is the caller's to deliver."""
    venue = _VenueOrders(*reports, raises=raises)
    clock = _Clock()
    client = StubClient()
    ex = _executor(tmp_path, client=client, clock=clock, venue_orders=venue)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]))
    ex.on_timer(clock.now)
    ex.on_quote(_quote())
    cid = client.last_order_id
    ex.on_order_event(_accepted(cid))
    if filled:
        _deliver_fill(ex, client, cid, filled)
    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled == [cid] and ex._active.phase == "cancelling"
    return ex, client, clock, venue, cid


def _closed_short(cid, *, filled_qty=str(_SHORT), status=OrderStatus.FILLED):
    return _report(f"V-{cid}", status, filled_qty=filled_qty, quantity="0.00100000", cancel_reason=_INSIGNIFICANT)


def _refuse(ex, cid):
    ex.on_order_event(_event(OrderCancelRejected, client_order_id=cid, reason="EOrder:Unknown order"))


def test_a_refused_cancel_kraken_reports_closed_with_the_recorded_fill_ends_filled_and_the_plan_goes_on(tmp_path):
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid)]

    with _executor_errors(logging.WARNING) as records:
        _refuse(ex, cid)

    assert [r.getMessage() for r in records] == [
        f"cancel of {cid} was refused by the venue (EOrder:Unknown order), and Kraken reports order V-{cid} closed with "
        f"0.00099997 of 0.001 filled ({_INSIGNIFICANT}) -- its row reads filled, intent 0 ends filled and the plan goes on; "
        "the read took 0.0 s"
    ]
    assert venue.calls == [_boundary(NOW) - timedelta(hours=1)]
    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("filled", pytest.approx(_SHORT))
    assert row["events"][-2]["type"] == "OrderCancelRejected"
    assert row["events"][-1] == {
        "event": "venue_closed",
        "at": clock.now.isoformat(),
        "venue_order_id": f"V-{cid}",
        "venue_filled_qty": _SHORT,
        "venue_qty": 0.001,
        "reason": _INSIGNIFICANT,
    }
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"], intent["filled_qty"]) == ("filled", [], pytest.approx(_SHORT))
    assert metrics.orders.count("filled") == 1 and "ambiguous" not in metrics.orders
    assert ex._active is None and client.unsubscribed == ["BTC/EUR.KRAKEN"]

    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    ex.on_quote(_quote("ETH/EUR.KRAKEN", bid=2000.0, ask=2000.1))
    assert [str(order.instrument_id) for order, _ in client.submitted] == ["BTC/EUR.KRAKEN", "ETH/EUR.KRAKEN"]
    assert _intent_entry(tmp_path, 1)["outcome"] == "pending"


@pytest.mark.parametrize("status", [s for s in OrderStatus.variants() if s != OrderStatus.FILLED], ids=lambda s: s.name)
def test_a_refused_cancel_kraken_reports_in_any_status_but_filled_stays_ambiguous(tmp_path, status):
    """The status dimension of the answers, enumerated over the library's own `OrderStatus`: Kraken's `open`,
    `canceled` and `expired` read ACCEPTED, CANCELED and EXPIRED on the pinned adapter, and the rest no Kraken
    order reads, each with the fill this engine recorded."""
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid, status=status)]

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and Kraken reports order V-{cid} {status.name}, "
        "0.00099997 of 0.001 filled, against the 0.00099997 this engine recorded -- its intent ends ambiguous and the plan "
        "stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


@pytest.mark.parametrize("filled_qty", ["0.00099996", "0.00099998"], ids=["below-the-ledger", "above-the-ledger"])
def test_a_refused_cancel_kraken_reports_filled_with_another_figure_stays_ambiguous(tmp_path, filled_qty):
    """A figure that disagrees is left to a restart's startup pass, which repairs or trips on it."""
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid, filled_qty=filled_qty)]

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and Kraken reports order V-{cid} FILLED, "
        f"{float(filled_qty):.10g} of 0.001 filled, against the 0.00099997 this engine recorded -- its intent ends ambiguous "
        "and the plan stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


def test_a_refused_cancel_of_an_unfilled_order_kraken_reports_closed_with_nothing_filled_stays_ambiguous(tmp_path):
    """Closed with a fill is the settle's whole premise: an order that filled nothing settles nothing, whatever the
    two figures read."""
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path, filled=0.0)
    venue.reports = [_closed_short(cid, filled_qty="0")]

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and Kraken reports order V-{cid} FILLED, "
        "0 of 0.001 filled, against the 0 this engine recorded -- its intent ends ambiguous and the plan stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


def _assert_ambiguous_and_dropped(tmp_path, client, *, reason="EOrder:Unknown order"):
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"]) == ("ambiguous", [f"cancel rejected: {reason}"])
    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["events"][-1]["type"]) == ("accepted", "OrderCancelRejected")
    assert _intent_entry(tmp_path, 1)["reasons"] == [
        "not run -- intent 0 ended ambiguous, so the venue state this plan was authorized against is unknown"
    ]
    assert len(client.submitted) == 1


def test_a_refused_cancel_kraken_does_not_return_stays_ambiguous(tmp_path):
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_report("OOTHER-AAAAA-BBBBBB", OrderStatus.FILLED, filled_qty=str(_SHORT))]

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and Kraken's order read does not return order "
        f"V-{cid} -- its intent ends ambiguous and the plan stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


def test_a_refused_cancel_whose_read_raises_stays_ambiguous(tmp_path):
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path, raises=TimeoutError())

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert venue.calls == [_boundary(NOW) - timedelta(hours=1)]
    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and Kraken's orders could not be read "
        "(TimeoutError) -- its intent ends ambiguous and the plan stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


def test_a_refused_cancel_with_no_acceptance_reads_nothing_and_stays_ambiguous(tmp_path):
    venue = _VenueOrders()
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)], venue_orders=venue
    )
    cid = client.last_order_id
    _advance_with_quotes(ex, client, clock, minutes=16)

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert venue.calls == []
    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and no Kraken order id reached this engine for "
        "it, so its record was not read -- its intent ends ambiguous and the plan stops here"
    )
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"]) == ("ambiguous", ["cancel rejected: EOrder:Unknown order"])


def test_a_refused_cancel_of_a_replacement_not_yet_accepted_reads_nothing(tmp_path):
    """The txid is the live order's: a replacement whose acceptance has not landed reads no earlier order's record."""
    venue = _VenueOrders()
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)], venue_orders=venue
    )
    first = client.last_order_id
    ex.on_order_event(_accepted(first))
    ex.on_order_event(_canceled(first))  # the venue's own cancel of the resting maker: a reprice
    ex.on_quote(_quote())
    second = client.last_order_id
    assert second != first
    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled == [second]

    _refuse(ex, second)

    assert venue.calls == []
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"]) == ("ambiguous", ["cancel rejected: EOrder:Unknown order"])


def test_a_refused_cancel_on_a_disarmed_engine_reads_nothing_and_stays_ambiguous(tmp_path):
    """The disarm's own revoke: the attended passes that sign on the engine's key run with it disarmed."""
    venue = _VenueOrders()
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)], venue_orders=venue
    )
    cid = client.last_order_id
    ex.on_order_event(_accepted(cid))
    _deliver_fill(ex, client, cid, _SHORT)
    (exec_dir(tmp_path) / ARM_FILE).unlink()
    clock.now += timedelta(seconds=5)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)
    assert client.canceled == [cid]
    venue.reports = [_closed_short(cid)]

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert venue.calls == []
    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and the engine reads disarmed, so Kraken's "
        "record of the order was not read -- its intent ends ambiguous and the plan stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


def test_a_refused_cancel_with_an_order_in_flight_reads_nothing_and_stays_ambiguous(tmp_path):
    """A cancel of this engine's still unanswered -- a trip's, or the startup pass's of an adopted order -- shares the
    key the read signs on."""
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid)]
    client.cache._open_orders.append(_left_pending_cancel())

    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert venue.calls == []
    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and order O-left-by-the-last-process of this "
        "engine is in flight, so Kraken's record of the order was not read -- its intent ends ambiguous and the plan stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


def test_a_refused_cancel_whose_cache_cannot_say_what_is_in_flight_reads_nothing_and_stays_ambiguous(tmp_path, monkeypatch):
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid)]

    def _unreadable(**kwargs):
        raise RuntimeError("cache read failed")

    monkeypatch.setattr(client.cache, "orders_inflight", _unreadable)
    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert venue.calls == []
    assert records[0].getMessage() == (
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and the Cache's in-flight orders could not be "
        "read, so Kraken's record of the order was not read -- its intent ends ambiguous and the plan stops here"
    )
    _assert_ambiguous_and_dropped(tmp_path, client)


def test_a_refused_cancel_whose_settled_row_cannot_be_written_stays_ambiguous(tmp_path, monkeypatch):
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid)]
    write = executor_module.update_submitted_row

    def _refuse_the_settle(*args, state=None, **kwargs):
        if state == "filled":
            raise EngineError("the journal is read-only")
        return write(*args, state=state, **kwargs)

    monkeypatch.setattr(executor_module, "update_submitted_row", _refuse_the_settle)
    with _executor_errors(logging.CRITICAL) as records:
        _refuse(ex, cid)

    assert [r.getMessage() for r in records][:2] == [
        f"the row of {cid} could not be written filled from Kraken's record",
        f"cancel of {cid} was REJECTED by the venue (EOrder:Unknown order), and Kraken reports order V-{cid} closed, but "
        "its row could not be written filled -- its intent ends ambiguous and the plan stops here",
    ]
    _assert_ambiguous_and_dropped(tmp_path, client)


def test_a_cancel_the_client_denied_reads_nothing(tmp_path):
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid)]

    ex.on_order_event(_event(OrderCancelDenied, client_order_id=cid, reason="NoExecutionClient"))

    assert venue.calls == [] and _intent_entry(tmp_path, 0)["outcome"] == "ambiguous"


def test_a_settled_refusal_leaves_no_open_row_to_carry_its_leg_or_hold_the_freeze(tmp_path):
    """The same-day carry (`_draft_table`'s open rows) and the watchdog's strand (`_stranded_rows`) both read the
    window's open rows; the settled row is not one of them."""
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid)]
    assert [r["client_order_id"] for _, r in open_submitted_rows(tmp_path / "journal", clock.now)] == [cid]

    _refuse(ex, cid)

    assert open_submitted_rows(tmp_path / "journal", clock.now) == [] and ex._stranded_rows() == ""


def test_a_refused_cancel_that_settles_past_the_windows_close_carries_the_next_intent(tmp_path):
    """The box's cancel of a cycle plan's intent started at B+3h20 goes out at B+3h35, past the window's close: the
    settle ends the intent, and the next one is carried, never started."""
    venue = _VenueOrders()
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR", "ETH/EUR")),
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(hours=3, minutes=20),
        venue_orders=venue,
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    ex.on_quote(_quote(bid=98250.0, ask=98250.1))
    order = client.submitted[-1][0]
    cid, qty = str(order.client_order_id), float(order.quantity)
    short = round(qty - 0.00000003, 8)
    ex.on_order_event(_accepted(cid))
    _deliver_fill(ex, client, cid, short, px=98250.0)
    _advance_with_quotes(ex, client, clock, minutes=16, bid=98250.0, ask=98250.1)
    assert client.canceled == [cid] and clock.now > _RUNG2_12Z + timedelta(hours=3, minutes=30)
    venue.reports = [_report(f"V-{cid}", OrderStatus.FILLED, filled_qty=f"{short:.8f}", quantity=f"{qty:.8f}")]

    _refuse(ex, cid)
    ex.on_timer(clock.now)

    assert _intent_entry(tmp_path, 0, when=_RUNG2_12Z)["outcome"] == "filled"
    second = _intent_entry(tmp_path, 1, when=_RUNG2_12Z)
    assert (second["outcome"], second["reasons"]) == ("carried", ["the submission window closed"])
    assert client.subscribed == ["BTC/EUR.KRAKEN"]


def test_a_refused_cancel_after_a_kill_file_settles_and_the_later_intents_are_refused_by_the_gate(tmp_path):
    ex, client, clock, venue, cid = _refused_after_a_short_fill(tmp_path)
    venue.reports = [_closed_short(cid)]
    (exec_dir(tmp_path) / KILL_FILE).touch()

    _refuse(ex, cid)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert _intent_entry(tmp_path, 0)["outcome"] == "filled"
    second = _intent_entry(tmp_path, 1)
    assert (second["outcome"], second["reasons"]) == ("refused", ["kill_switch"])
    assert len(client.submitted) == 1
```

- [ ] **Step 3: Run them, expect failure.** `uv run pytest tests/test_engine_executor.py -k 'refused_cancel or settled_refusal or cancel_rejection or client_denied' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` reads `29 failed, 5 passed`: no read is made and the CRITICAL line names no answer. The five that pass are the two denied cases, `test_a_cancel_the_client_denied_reads_nothing` among them, the two adopted-order cases the selection's words also catch, and `test_a_refused_cancel_of_a_replacement_not_yet_accepted_reads_nothing`, which holds what the change must not do and so passes on a base that reads nothing; its probe in Step 7 proves it.

- [ ] **Step 4: Implement**, in `cli/engine/executor.py`. Last in `_ActiveIntent`:

```python
    # The live order's Kraken txid, from its acceptance: the name the refused-cancel arm reads Kraken's record of the
    # order by (`_settle_refused_cancel`). None until the acceptance lands, and again for each new order.
    venue_order_id: str | None = None
```

In `_place`, after `active.order_filled = 0.0`: `active.venue_order_id = None`. In `_on_order_event`'s `OrderAccepted` arm, the line `payload["venue_order_id"] = str(event.venue_order_id)` becomes the two lines `active.venue_order_id = str(event.venue_order_id)` and `payload["venue_order_id"] = active.venue_order_id` (*Rulings*). The refused-cancel arm, its comment and its first statements through `self._update_row(active, event=payload)`, becomes:

```python
        if name in ("OrderCancelRejected", "OrderCancelDenied"):
            # The venue positively says the cancel did NOT take (`OrderCancelRejected`), or the
            # client refused it before sending (`OrderCancelDenied`) and the venue never saw it.
            # A refusal Kraken's own record settles -- the order closed with exactly the fill this
            # process recorded -- ends the intent `filled` and the plan goes on
            # (`_settle_refused_cancel`). Otherwise the order may still rest while whatever asked for
            # the cancel (a kill file, the time-box) says it must not, and nothing further may be
            # submitted against a position this process can no longer describe: the row keeps its
            # OPEN state, and only the intent is journaled.
            denied = name == "OrderCancelDenied"
            if denied:
                logger.critical(
                    "cancel of %s was DENIED before it was sent (%s) -- the order may still rest; the plan stops here",
                    active.client_order_id,
                    reason,
                )
            self._update_row(active, event=payload)
            if not denied:
                answer = self._settle_refused_cancel(active, reason)
                if answer is None:
                    return
                logger.critical(
                    "cancel of %s was REJECTED by the venue (%s), and %s -- its intent ends ambiguous and the plan stops here",
                    active.client_order_id,
                    reason,
                    answer,
                )
```

its statements from `refusal = …` through `return` unchanged. Directly above `_on_rejected`, the settle; its condition and its lines are the spec's D3, D4 and D6, so the body is given whole:

```python
    def _settle_refused_cancel(self, active: _ActiveIntent, reason) -> str | None:
        """Kraken's own record of the order whose cancel the venue just refused, read at the refusal and
        settled from: an order Kraken reports closed -- FILLED, whatever its reason -- with a fill equal to the
        one this process recorded for it, within `_OVERFILL_TOLERANCE`, has its row written `filled` with a
        `venue_closed` event, counts `filled`, ends its intent `filled` and returns None, the plan's next intent
        starting on the next tick under that tick's own window, gate and box. Every other answer returns what
        the refused-cancel arm's CRITICAL line names, the row and the intent left to it: any other status, a
        figure that disagrees, an order the read does not return, a read that raises, a row write that fails,
        and a read not made -- no txid recorded, the engine disarmed, or an order of this process in flight or
        a Cache that cannot say, the terms `read_venue_orders` reads on.

        The read holds the node's main thread for its duration, up to `_VENUE_READ_TIMEOUT_SECONDS`: the order
        events, quotes and timer firings that land meanwhile are delivered after it, in order. A figure that
        disagrees is left to a restart's startup pass, which repairs or trips on it: a repair here would put the
        row ahead of the Cache's position, which `_reconcile_terminal` holds the fill to."""
        txid = active.venue_order_id
        if txid is None:
            return "no Kraken order id reached this engine for it, so its record was not read"
        if not self._gate_armed:
            return "the engine reads disarmed, so Kraken's record of the order was not read"
        try:
            in_flight = [str(order.client_order_id) for order in self._cache.orders_inflight(venue=_VENUE)]
        except Exception:
            logger.warning("the Cache's in-flight orders could not be read at the refused cancel", exc_info=True)
            return "the Cache's in-flight orders could not be read, so Kraken's record of the order was not read"
        if in_flight:
            return f"order {', '.join(in_flight)} of this engine is in flight, so Kraken's record of the order was not read"
        started = self._now()
        try:
            reports = list((self._venue_orders or read_venue_orders)(self._plan_cycle_ts - _VENUE_READ_MARGIN))
        except Exception as exc:
            logger.warning("Kraken's orders could not be read at the refused cancel of %s", active.client_order_id, exc_info=True)
            return f"Kraken's orders could not be read ({type(exc).__name__})"
        seconds = (self._now() - started).total_seconds()
        report = next((r for r in reports if str(r.venue_order_id) == txid), None)
        if report is None:
            return f"Kraken's order read does not return order {txid}"
        venue_filled = float(report.filled_qty)
        if not (
            report.order_status == OrderStatus.FILLED
            and venue_filled > _OVERFILL_TOLERANCE
            and abs(venue_filled - active.order_filled) <= _OVERFILL_TOLERANCE
        ):
            return (
                f"Kraken reports order {txid} {report.order_status.name}, {venue_filled:.10g} of "
                f"{float(report.quantity):.10g} filled, against the {active.order_filled:.10g} this engine recorded"
            )
        why = None if report.cancel_reason is None else str(report.cancel_reason)
        event = {
            "event": "venue_closed",
            "at": self._now().isoformat(),
            "venue_order_id": txid,
            "venue_filled_qty": venue_filled,
            "venue_qty": float(report.quantity),
            "reason": why,
        }
        try:
            self._update_row(active, state="filled", event=event)
        except Exception:
            logger.critical("the row of %s could not be written filled from Kraken's record", active.client_order_id, exc_info=True)
            return f"Kraken reports order {txid} closed, but its row could not be written filled"
        _inc_order("filled")
        logger.warning(
            "cancel of %s was refused by the venue (%s), and Kraken reports order %s closed with %.10g of %.10g filled (%s) "
            "-- its row reads filled, intent %d ends filled and the plan goes on; the read took %.1f s",
            active.client_order_id,
            reason,
            txid,
            venue_filled,
            float(report.quantity),
            why or "no reason given",
            active.index,
            seconds,
        )
        self._finish_active("filled", (), active.filled)
        return None
```

And `_reconcile_terminal`'s docstring takes its one sentence (*Rulings*).

- [ ] **Step 5: Run them, expect pass**, with Step 3's command, then the whole file: `uv run pytest tests/test_engine_executor.py -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` — `test_every_read_of_a_rows_txid_or_its_cache_copy_goes_through_the_one_door_and_every_intent_writer_is_listed` among them, which refuses the acceptance arm's payload read (*Rulings*).

- [ ] **Step 6: Commit** `feat(engine): a refused cancel reads Kraken's record, and an order closed with the engine's fill ends filled with the plan going on`, the per-commit test run's result line in the body, after the gate.

- [ ] **Step 7: Probes.** Each on `cli/engine/executor.py`, the control `1,$d`. An arm written `R` + `s/…/…/` prefixes its `s` command with the settle's range, the two one sed expression — the `no-txid` arm's mutation is `/def _settle_refused_cancel/,/def _on_rejected/s/if txid is None:/if False:/`:
  - `status`: mutation `s/report.order_status == OrderStatus.FILLED/report.order_status != OrderStatus.CANCELED/`, `-k 'any_status_but_filled'`.
  - `figure`: mutation `s/abs(venue_filled - active.order_filled) <= _OVERFILL_TOLERANCE/abs(venue_filled - active.order_filled) <= 1e-07/`, `-k 'another_figure'`.
  - `nothing`: mutation `s/and venue_filled > _OVERFILL_TOLERANCE/and venue_filled >= 0.0/`, `-k 'closed_with_nothing_filled'`.
  - `disarmed`: mutation `R` + `s/if not self._gate_armed:/if False:/`, `-k 'disarmed_engine'`.
  - `in-flight`: mutation `s/        if in_flight:/        if False:/`, `-k 'order_in_flight'`.
  - `cache-unread`: mutation `R` + `s/            return "the Cache.s in-flight orders could not be read, so Kraken.s record of the order was not read"/            in_flight = []/`, `-k 'cannot_say_what_is_in_flight'`.
  - `no-txid`: mutation `R` + `s/if txid is None:/if False:/`, `-k 'no_acceptance'`.
  - `replacement`: mutation `s/^        active.venue_order_id = None$//`, `-k 'replacement_not_yet_accepted'`.
  - `denied`: mutation `s/            if not denied:/            if True:/`, `-k 'client_denied_reads_nothing'`.
  - `returns`: mutation `R` + `s/        return None/        return "settled"/`, `-k 'closed_with_the_recorded_fill'`.
  - `row-state`: mutation `s/state="filled", event=event/event=event/`, `-k 'leaves_no_open_row'`.
  - `counter`: mutation `R` + `s/_inc_order("filled")/_inc_order("ambiguous")/`, `-k 'closed_with_the_recorded_fill'`.
  - `warning`: mutation `R` + `s/^        logger.warning($/        logger.info(/`, `-k 'closed_with_the_recorded_fill'`.
  - `since`: mutation `s/(self._plan_cycle_ts - _VENUE_READ_MARGIN)/(self._plan_cycle_ts)/`, `-k 'closed_with_the_recorded_fill'`.
  - `resumes`: mutation `R` + `s/        self._finish_active("filled", (), active.filled)/        self._journal_intent(active.index, "filled", (), active.filled)/`, `-k 'closed_with_the_recorded_fill'`.
  - `read-fails`: mutation `R` + `s/            return f"Kraken.s orders could not be read ({type(exc).__name__})"/            reports = []/`, `-k 'read_raises'`.
  - `not-returned`: mutation `R` + `s/        if report is None:/        if False:/`, `-k 'does_not_return'`.
  - `critical`: mutation `s/its intent ends ambiguous and the plan stops here/the plan stops here/`, `-k 'does_not_return'`.
  - `row-unwritten`: mutation `R` + `s/            return f"Kraken reports order {txid} closed, but its row could not be written filled"/            pass/`, `-k 'settled_row_cannot_be_written'`.
  - `kill-file`: mutation `/def _start_intent/,/def _classify_close/s/if not _level_permits(verdict.level, intent):/if False:/`, `-k 'after_a_kill_file'`.
  - `window`: mutation `s/if self._plan_window_close is not None and now > self._plan_window_close:/if False:/`, `-k 'past_the_windows_close'`.

  An apostrophe in a pattern is spelled `.`, as above, so the mutation stays one single-quoted word. Then the empty commit, `test(engine): the refused cancel's settle proven by infra/scripts/mutate-probe.sh`.

### Task 3: The runbook texts (spec D6)

**Files:**
- Modify: `infra/runbooks/engine.md`, `infra/runbooks/engine-procedures.md`

**Interfaces:**
- Consumes: Task 2's log lines, verbatim.
- Produces: nothing a later task calls.

- [ ] **Step 1: Load `zcrypto-refine-rules`** before editing a top-level runbook page, as its description asks; each edit is found by its text, never a line number, its anchor's `grep -c` reading `1` first.

- [ ] **Step 2: The error-logs class.** In `infra/runbooks/engine.md`'s `zcrypto-engine-error-logs` section, step 2, a new item directly after the one that opens `   - **`cancel of adopted order … was REJECTED by the venue`**`, its text the spec's *Runbook texts* first fence, verbatim, three spaces of indent kept.

- [ ] **Step 3: The daily read.** In `infra/runbooks/engine-procedures.md`'s rung-3 daily read, item 3, the sentence "An `ambiguous` intent halts its plan: on the workstation, read `kraken open-orders -o json` and establish what reached the venue; the re-read pass settles its row, and one Kraken's orders do not explain is an unreconciled state for [the go/no-go](#rung-3-go-no-go)." is replaced by the spec's *Runbook texts* second fence, verbatim.

- [ ] **Step 4: Commit** `docs(runbooks): the refused cancel's line says what Kraken's record answered, and the daily read reads the settled row`, the per-commit test run's result line in the body — `consumers.sh` names `tests/test_cache_restart.py tests/test_engine_draftplan.py tests/test_engine_executor.py tests/test_guidance_guard.py tests/test_merge_gate.py tests/test_ops_daily.py` for the two pages, and the task adds `tests/test_internal_terms_not_operator_visible.py` — after the gate, whose `guidance growth is stated, universals are counted` hook reads both pages.

### Task 4: The decisions-log entry and T0229's close

**Files:**
- Modify: `docs/research/14.phase6-decisions.md`, `docs/open-topics/README.md`
- Move: `docs/open-topics/T0229-an-order-kraken-closes-short-of-its-size-ends-its-intent-ambiguous.md` to `docs/open-topics/archive/`

- [ ] **Step 1: Load `iteration-closeout`** before the decisions-log entry and **`topic-ops`** before the topic.

- [ ] **Step 2: The decisions-log entry**, appended to `docs/research/14.phase6-decisions.md` after its last line, keyed `[00160]`, verbatim as written here; an owner's ruling on the spec's open question that lands before this task is entered the same way, its ask and answer verbatim:

```markdown

[00160] How does the fix settle an order Kraken closes short of its size, whose 15-minute box's cancel then meets `EOrder:Unknown order`? (Decision: 2)
  Asked 2026-11-16T15:47:43.223Z, verbatim: "T0229 (an order Kraken closes short of its size, e.g. DOT 5.18909575 of 5.18909578 on 11-11): today the 15-minute box's cancel meets `EOrder:Unknown order`, the intent ends ambiguous, the plan drops its later legs, and the row stays open until a restart. How should the fix settle it?". Answered 2026-11-16T15:48:55.449Z, verbatim: "Inline, and the plan resumes".
  1. **Via the re-read pass (Recommended).** At the refusal nothing changes (intent ambiguous, later legs dropped). It also arms the existing re-read pass, which on the next quiet tick reads Kraken's report and settles the row and the intent filled at vol_exec. That ends the open-until-restart row, the same-day carried leg and the watchdog strand. The dropped legs draft again at the next boundary. No new path on the order-event handler.
  2. **Inline, and the plan resumes.** The refusal's handler reads Kraken's record itself. On closed-with-a-fill, the intent ends filled and the plan runs its next leg, so the boundary loses nothing. It adds a synchronous venue read on the event path and a resume after a refused cancel, which the live trade path has never had. **Taken** (owner, 2026-11-16).

[00160] Where does the refused cancel's read of Kraken's record run? (Decision: 1)
  1. **In the refusal's handler, on the node's main thread, under the reader's own 30 s bound** — the ruling's synchronous read on the event path; measured on a loopback node, the events and timer firings that land during the read are delivered after it, in order, and nothing of the engine's can be live beside the refused intent.
  2. **On the next tick** — the same thread and the same bound, a phase to hold the intent in until then, and up to 5 s more.
  3. **On a worker thread a tick collects** — the main thread stays free, for a thread the engine has nowhere else, a bare client off the main thread no reading covers, and the same phase.
  Decided by the spec's author: the other two buy nothing the refused intent's plan can use, its next intent waiting on this one either way.

[00160] Which of Kraken's answers settle the refused cancel? (Decision: 1)
  1. **FILLED — Kraken's `closed`, whatever its reason — with a fill above zero equal to the one the engine recorded for the order, within 1e-12** — the startup pass already writes `filled` from any FILLED report, and a figure apart stays the startup pass's to repair or trip on.
  2. **The same, under the reason `Insignificant volume remaining` alone** — a string written for people decides a state.
  3. **Closed with any fill, the row repaired to Kraken's figure** — the repair puts the row ahead of the Cache's position, and the terminal's reconciliation trips the kill switch on that gap.
  Decided by the spec's author.

[00160] Which refused cancels read Kraken's record? (Decision: 1)
  1. **Every `OrderCancelRejected`, whatever its reason, with the engine armed, nothing of it in flight and the order's txid known; never `OrderCancelDenied`** — Kraken's answer decides, not its error text; a denied cancel never reached Kraken; the disarmed engine is the attended passes', whose nonce the read would race.
  2. **`EOrder:Unknown order` alone, on the same terms** — one read fewer on other refusals, keyed on a venue's string.
  Decided by the spec's author.

[00160] When the refused cancel's read finds the order CANCELED or EXPIRED with exactly the recorded fill, does the read write the row's state at once? (Decision: 1)
  Asked 2026-11-16T17:21:44.212Z, verbatim: "Spec 00160 (T0229): when the refused cancel's read finds the order CANCELED or EXPIRED at Kraken with exactly the fill the engine recorded, the intent stays ambiguous and the plan's later legs are dropped, per your ruling (only a closed-with-fill resumes). Should the read also write the row's state from Kraken's record at once?". Answered 2026-11-16T17:24:37.023Z, verbatim: "Leave it to a restart (Recommended)".
  1. **Leave it to a restart (Recommended).** As today: the row stays open until a restart's startup pass writes it. Neither answer has been seen on the live path, and the restart already settles them. **Taken** (owner, 2026-11-16).
  2. **Write it now.** The read writes `canceled`/`venue_canceled` from Kraken's record at once. That removes the same-day carried leg and the watchdog strand for those answers too, at the cost of one more write path.
```

- [ ] **Step 3: Close the topic.** `git mv` it to `docs/open-topics/archive/`; `status: resolved`, `ripe_when:` deleted; `## Suggested next steps` and everything under it replaced by this section, verbatim; then `uv run python infra/scripts/topics-index.py`, and the heading set read before and after with `grep '^#'`:

```markdown
## Resolution

Delivered by the pull request from `feat/t0229-closed-short-settles-inline` (spec 00160, plan 00160), on the owner's ruling of 2026-11-16, verbatim "Inline, and the plan resumes": at a cancel the venue refuses, the engine reads Kraken's record of the order at once. An order Kraken reports closed with exactly the fill the engine recorded ends its intent `filled` and its row `filled`, with a `venue_closed` event, and the plan runs its next intent; every other answer, or a read not made or failed, stays `ambiguous` with the remainder dropped, its CRITICAL line naming the answer.

- The 2026-11-11 DOT case, closed 3e-08 short, is `test_a_refused_cancel_kraken_reports_closed_with_the_recorded_fill_ends_filled_and_the_plan_goes_on`; the adapter reading such an order as filled at its executed volume, `test_read_venue_orders_reads_an_order_kraken_closed_short_as_filled_at_its_executed_volume`; a read that fails, `test_a_refused_cancel_whose_read_raises_stays_ambiguous`; all in `tests/test_engine_executor.py`.
- The settled row no longer carries its symbol's leg in the drafts or holds the watchdog's freeze; the Cache's stale open copy of the order stays, as the startup pass leaves it (spec 00160 D7).
- The missing terminal event is the adapter's, the `nautilus` peer's to raise upstream; spec 00160 D8 names the coordinator's hand-off and the record it carries.
- It ships on the engine image that carries [[T0226]]'s and [[T0227]]'s fixes, one converge, the fleet's concern (spec 00160 D10).
```

- [ ] **Step 4: Commit** `docs(open-topics): T0229 resolved by spec 00160`, carrying the archived topic, the index and the log entry, with the result line of the per-commit test run — `consumers.sh` names `tests/test_merge_gate.py tests/test_open_topics_frontmatter.py tests/test_topics_index.py` for the three files, and the task adds `tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py tests/test_internal_terms_not_operator_visible.py` — after the gate. The `git mv` has staged the topic's old path, so the commit's `add` names the archived file, the index and the log. The decisions-log entry is this plan's closing task; the change-index row is `open-pr`'s.
