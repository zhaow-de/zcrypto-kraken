# Rung 1's execution findings: the reprice ladder, the ledger reader's margin rows and the intents a restart orphans — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A crossing post-only order is re-priced off a tick newer than the one it crossed on and, in `execute` mode, an exhausted maker ladder crosses through the bounded IOC before the intent ends `unfilled`; `tracking-report --ledger-export` matches `margin` rows by trade id, counts `settled` and `collateralconversion` as known no-fill types, reports the matched rows' fees beside the rollover total and prints both at four decimals; the startup pass settles every intent a restart orphans and marks a minted terminal on an adopted row `ambiguous`; the operator pages say so.

**Architecture:** Three tasks, one per finding, each a guard-proven commit on one branch. Task 1 adds two counters to `_ActiveIntent`, a phase `awaiting_reprice` with its own `_poll` arm, entered with the ended order detached, and the fall-through from `_reprice`'s exhaustion to `_fallback` in `cli/engine/executor.py`, records the priced quote inside each row's `order` payload, and gives the runbook's `Nothing retries itself` rule the clause that an `execute` intent's `unfilled` follows both ladders. Task 2 widens `reconcile_ledger`'s match in `cli/engine/tracking.py` to a `_MATCHED_LEDGER_TYPES` set, adds `known` and `matched_fees_eur` to its result, a fee summed under `_EURO_FEE_ASSETS`, the euro codes and EURC, and changes `cli/engine/command.py`'s rendering, with the README row and the runbook's §6 item 3 following. Task 3 adds `pending_plan_intents` to `cli/engine/execledger.py`, a `_settle_pending_intents` sweep the adopt pass runs after classification, which leaves `pending` every intent with an open row the pass did not cancel, and the `ambiguous` return of `_venue_terminal_state`'s reconciliation arm for a minted terminal, with the two drill and procedure pages and the error-logs runbook following. The third task is the spec's strikeable cluster: nothing in the first two depends on it.

**Tech Stack:** Python 3.14 through `uv run`, pytest, the pinned `nautilus-trader` (`2.0.0rc6.dev20260921`) whose real order events and orders the executor tests drive, `infra/scripts/mutate-probe.sh` for the guard verdicts, `uv run pre-commit run -a` as the commit gate.

**Spec:** `docs/specs/00119-exec-findings-design.md`

## Global Constraints

- The ladder's constants are unchanged: `_MAX_REPRICES` 5, `_MAX_IOC_ATTEMPTS` 3, `_QUOTE_SILENCE` 30 s, `_TIME_BOX` 15 min, `_ACK_WAIT` 30 s (spec D2, D3). The waiting phase is `awaiting_reprice`; a reprice resubmits at once when `quote_seq > priced_seq` and waits otherwise (spec D1); the wait is bounded by `resting`'s three checks in `resting`'s order (spec D2); the sixth crossing calls `_fallback` in `execute` mode and ends `unfilled` with `reprice budget exhausted` in the rest modes, and the runbook's `Nothing retries itself` rule says an `execute` intent's `unfilled` follows both ladders (spec D3). Entering the wait clears `client_order_id` and `order`, so the ended order's later events take the detached path, and `_resubmit` ends an intent `filled` when less than one lot step remains, as does `_poll`'s `awaiting_reprice` arm before its three checks (spec D1); `on_quote`'s handler refuses with `filled` carried (spec D2).
- No schema changes: `_ROW_KEYS` and `EXEC_SCHEMA_VERSION` in `cli/engine/execledger.py` stay as they are, the priced quote living inside the row's `order` payload as `bid`, `ask`, `quote_seq` (spec D5); `_INTENT_KEYS` in `cli/engine/probeplan.py` is untouched (spec D4); no `_inc_order` label is added, since `tests/test_engine_metrics.py` pins `_EXEC_ORDER_OUTCOMES` against the executor's call sites.
- The reader's constants: `_MATCHED_LEDGER_TYPES = {"trade", "margin"}`; `_NO_FILL_LEDGER_TYPES` gains `settled` and `collateralconversion`; the result gains `known` and `matched_fees_eur`, a fee summed when its asset is in `_EURO_FEE_ASSETS`, the euro codes and `EURC`, for the rollover arm and the matched arm alike; `status` is `ok` once a trade or margin row was compared; the rollover and matched-fee lines print `:,.4f` (spec D7, D9, D10); `_LEDGER_COLUMNS` is unchanged, so the sixteen-column export still parses and the only-used-columns rule `tests/test_engine_tracking.py` pins holds.
- The startup pass's words: `filled`, `revoked` with `the engine restarted while the intent was in flight`, `refused` with `not run -- the engine restarted before it ran`, written at classification time, before the venue answers the pass's cancel, so a fill after the write is on the order's row and not in the intent's `filled_qty`; an intent with an open row the pass sent no cancel for stays `pending`, six shapes — a reducer it kept, a cancel that raised, an order the venue read returned still open outside the Cache, a row the read did not return, a row that recorded no txid, and a row whose reconcile raised on an order closed at the venue — and so does the whole window's when the venue read or the ledger read failed or the pass latched the kill switch, the sweep skipped whole; a later startup inside the re-attach window — `_exec_records_in_window`'s in `cli/engine/execledger.py`, the boundary's UTC day and the next, which the intent sweep and the row re-attach both read — settles the intents of a failed read, a cancel that raised, an order outside the Cache once the venue reports it closed, and a reconcile that raised, and settles neither a row with no txid nor one no venue read returns, which stay `pending`; past the window no startup reads the intent or its row, and the pages say the window's entry records what stays `pending` beside Kraken's closed orders and positions read for the order; the one shape outside the rule, a Cache-resident order whose reconcile raised and which the loop then cancelled, is settled from the figure the raise left unrepaired (spec D14). A minted terminal on an adopted row writes `ambiguous` and logs at CRITICAL, naming the hand cancel on Kraken's open-orders page; a flagged non-terminal writes nothing (spec D15); a cancel the venue refuses on an adopted order — the pass's or a trip's — logs at CRITICAL naming the hand cancel and writes nothing, the row still open and the intent as the pass left it (spec D14).
- No string literal added under `cli/engine/` and no text added to `README.md`, `infra/runbooks/engine-procedures.md` or `infra/runbooks/drills-order-path.md` names a spec, a decision or a topic: `tests/test_internal_terms_not_operator_visible.py` walks them and runs in every task's consumer command.
- The three tasks land in order on one branch and merge together: the counts each task's failing and passing runs state assume the tasks before it have landed, and Task 2's and Task 3's first steps check the previous task's marker.
- A fence is the exact text at its indentation in the file: an indented fence is a fragment replaced in place, never a module of its own, and a `Replace, in <path>, this block:` instruction names the whole block it replaces, which occurs exactly once in the file at that step. A fence whose closing backticks sit on its last text line is a mid-line fragment with no trailing newline: the replacement lands inside that line, and neither the backticks nor the line end belongs to the text replaced.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean; the probe never runs while a pytest run is in flight in the same checkout.
- Every commit is green over the changed files' consumers, the union of `grep -rlE 'engine\.executor|engine import executor|engine\.execledger|engine import execledger' tests/test_*.py` for Tasks 1 and 3 and of `grep -rlE 'engine\.tracking|engine import tracking|engine\.command|engine import command' tests/test_*.py` for Task 2, each plus the internal-terms guard, and, since each task changes a page under `infra/runbooks/` or `README.md`, the tests that read those pages from the tree — `grep -rlE 'infra/runbooks|README\.md' tests/test_*.py` finds them among files that name the paths in a fixture, a string or a comment alone: `tests/test_code_prose_citations.py`, `tests/test_guidance_guard.py`, `tests/test_guidance_refs_resolve.py`, `tests/test_infra_alert_rules.py`, `tests/test_ops_daily.py`, `tests/test_runbook_internal_tokens.py`, `tests/test_runbook_triggers.py` and `tests/test_systemd_user_units.py` — all as they read when this plan was written; never the full suite locally, which is CI's on every push.
- `uv run pre-commit run -a` runs the pre-commit stage alone and is clean before every commit; `guidance-guard` and `message-citations` run at commit-msg, on `git commit`: the runbook list items the three tasks write carry no universal word (every, never, always, only, any, cannot) outside code spans, and no commit message cites a `path:line`, a `path::symbol` or a topic.
- No step reaches a host or a venue; the executor tests drive the library's own events against a stub client, and the tracking tests a synthetic export.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. An existing file's lines are left as they are, except where a step replaces them.
- A commit message ends with these two trailers, `<model>` being the executing model's own name, written by the executor:

```
Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU
```

## File structure

- Modify `cli/engine/executor.py` — `_ActiveIntent` gains `quote_seq` and `priced_seq`; `on_quote` advances the count and resubmits from `awaiting_reprice`; `_place` records the quote and sets `priced_seq`; `_reprice` waits, with the ended order detached, or falls through to `_fallback`, its tail moving to `_reprice_at_touch`; `_resubmit` ends a remainder below one lot step `filled`; `on_quote`'s handler carries `filled`; `_poll` gains the `awaiting_reprice` arm, the completion test at its head, and `_time_box_with_nothing_resting` (Task 1). `_adopt_resting_orders` records whether the ledger read succeeded, collects the intents it cancelled and calls `_settle_pending_intents`, a new method; `_venue_terminal_state`'s reconciliation arm returns `ambiguous` for a minted terminal (Task 3).
- Modify `tests/test_engine_executor.py` — the ladder test replaced by nineteen cases and six existing cases gaining the quote line the reprice waits for (Task 1); the pinned minted-terminal case flipped, the external cancel-rejection case's docstring re-trued, `_submitted_row` gaining a `qty` keyword, a `_pending_plan_entry` helper and seventeen cases on the sweep and the adopted row (Task 3).
- Modify `cli/engine/tracking.py` — `LedgerRow.refid`'s comment, `_EURO_FEE_ASSETS`, `_MATCHED_LEDGER_TYPES`, `_NO_FILL_LEDGER_TYPES`, `reconcile_ledger` (Task 2).
- Modify `cli/engine/command.py` — `_cost_over`'s basis text and `_render_tracking`'s ledger block (Task 2).
- Modify `tests/test_engine_tracking.py` — two unit cases replaced by six, the real-shape fixture among them; one CLI case replaced by three (Task 2).
- Modify `README.md` — the `tracking-report` row's ledger sentences (Task 2).
- Modify `infra/runbooks/engine-procedures.md` — the `Nothing retries itself` rule (Task 1); §6 item 3's lead-in and two bullets (Task 2); the rest-hold terminal vocabulary, the `Read filled_qty` paragraph's last sentence and three sentences of the pre-probe step on minted terminals (Task 3).
- Modify `cli/engine/execledger.py` — `pending_plan_intents` (Task 3).
- Modify `infra/runbooks/drills-order-path.md` — A1's Must fire and step 3, G's Must fire, step 4 and Record (Task 3).
- Modify `infra/runbooks/engine.md` — the error-logs runbook's step 2 gains the minted-terminal class and the refused cancel's (Task 3).

## Review Focus

- A reprice firing off the tick it crossed on, the measured defect: the resubmission must wait for a newer stored tick and price off it; Task 1 owns `test_a_venue_cancel_off_the_priced_tick_waits_for_the_next_quote_before_repricing` and `test_alternating_crossings_place_one_order_per_tick_and_the_sixth_crossing_crosses_through_the_ioc`, and `test_a_sell_closes_six_accept_then_cancel_crossings_end_in_an_ioc_at_the_bid` pins the measured side.
- A reprice that always waits, losing a tick that already arrived, or a rest mode crossing through the IOC: Task 1 owns `test_a_tick_that_landed_before_the_cancel_reprices_on_the_cancel_itself`, `test_a_half_book_tick_while_a_reprice_waits_prices_nothing`, `test_a_half_book_tick_while_the_order_rests_is_not_the_newer_tick_a_reprice_waits_for` and the two `spent_by_rejections` cases.
- A waiting reprice outliving a kill file, a dead feed or the time-box, an intent parked with no order and no bound, the box firing an IOC off a quote the silence bound already condemned, or an intent a detached fill completed ended `revoked` by the timer: Task 1 owns the five `with_no_cancel` cases, the rest-cancel one in two arms, `test_quote_silence_outranks_the_time_box_while_a_reprice_waits` and `test_a_late_fill_completing_the_intent_while_the_reprice_waits_ends_it_filled_on_the_timer_too`.
- The ended order's events reaching the in-flight arms while the reprice waits, a row reopened by a racing fill or a crossing counted twice: Task 1 owns `test_a_fill_racing_the_venue_cancel_lands_detached_while_the_reprice_waits` and `test_a_replayed_cancel_ack_while_the_reprice_waits_counts_no_crossing`.
- A margin row's realized PnL summed as a cost, a hand settle's pair failing the window, or a fee charged in EURC dropped from the venue's figure: Task 2 owns `test_a_margin_row_matching_a_journaled_fill_reconciles_and_carries_its_fee_not_its_pnl` and `test_every_row_type_of_the_real_export_lands_in_exactly_one_place`.
- A minted terminal read as the venue's answer, a kept reducer's intent rewritten, an intent closed `revoked` while its order rests at Kraken with nothing naming the hand cancel, or fills nobody compared or read, or the venue refuted, journaled as an intent's: Task 3 owns `test_a_terminal_the_engine_minted_marks_the_adopted_row_ambiguous_where_the_venues_ack_closes_it`, `test_the_startup_pass_leaves_the_intent_of_a_reducer_it_keeps_pending`, the three `leaves_its_intent_pending` cases, `test_a_cancel_the_venue_refused_on_an_adopted_order_logs_the_hand_cancel_and_leaves_the_row_accepted` and the five `leaves_the_pending_intents` cases, two of them with an opener resting, the restart every drill takes.
- An intent `filled` on a partial, or its target read off a remainder row or off a row with no readable quantity: Task 3 owns the partial arm of `test_an_intent_whose_order_closed_while_down_is_settled_from_its_rows`, `test_an_intents_two_orders_closed_while_down_are_summed_against_the_first_orders_quantity` and `test_a_row_with_no_readable_quantity_settles_its_intent_revoked_never_filled`.

---

### Task 1: A reprice waits for a tick newer than the one it crossed on, and an exhausted execute ladder crosses through the IOC

What this task decides, where the spec leaves it open:

- The tail of `_reprice` that prices and resubmits moves whole into `_reprice_at_touch`, which `on_quote` calls from `awaiting_reprice` and `_reprice` calls when a newer tick has already arrived: one resubmission path, two callers.
- `on_quote` advances `quote_seq` only for a tick it stores (both sides usable), and resubmits from `awaiting_reprice` only on such a tick, so a half book never prices a reprice; the `awaiting_quote` arm keeps its existing behaviour, where `_first_submission` refuses on no usable touch.
- The `_poll` arm for `awaiting_reprice` runs before the generic non-resting check, so `phase_deadline`, which `_enter` leaves None for the new phase, is never consulted for it.
- The six existing cases that drove a reprice off the priced tick gain one `on_quote` line after the crossing event, keeping each case's own subject (placement time, a refused resubmission, a late fill, the cross-order sum, the tripped chokepoint); the old ladder case is replaced by the nineteen cases below.
- `_reprice` clears `client_order_id` and `order` before entering `awaiting_reprice`, spec D1's detach, so `_on_order_event` routes the ended order's later events through `_on_detached_event`.
- `_resubmit` carries spec D1's completion end, one comparison at the head of the path every resubmission takes, and `_poll`'s `awaiting_reprice` arm the same comparison at its head, before its three checks, so a completed intent starved of ticks ends `filled` on the timer.
- `on_quote`'s handler carries `filled` into the refusal it writes, `_submit`'s rule, since the resubmission now runs inside it.

**Files:**
- Modify: `cli/engine/executor.py` (`_ActiveIntent`, the two fields appended after `hold_expired`; `on_quote`, the block from `bid = _as_price(...)` through the `awaiting_quote` arm; `_place`, the `order_payload` literal's tail and the line after it; `_reprice`, its docstring and its tail after the `cancel_requested` branch; `_resubmit`, its head; `on_quote`'s handler; `_poll`, its docstring and the arm inserted before `if active.phase != "resting":`; `_time_box_with_nothing_resting`, inserted before `_start_intent`)
- Modify: `infra/runbooks/engine-procedures.md` (the `Nothing retries itself` bullet's first sentence)
- Test: `tests/test_engine_executor.py` (`test_both_crossing_surfaces_count_one_reprice_and_the_sixth_refuses` replaced by nineteen cases; one line added to each of `test_a_late_fill_on_a_superseded_order_is_published_too`, `test_a_resting_orders_placement_time_belongs_to_the_order_and_to_no_other_phase`, `test_a_refused_resubmission_journals_the_fills_that_already_happened`, `test_an_intents_orders_filling_past_its_target_between_them_trips`, `test_a_superseded_orders_late_fills_are_summed_against_that_orders_own_quantity`, `test_the_chokepoint_refuses_once_this_process_has_tripped`)

**Interfaces:**
- Consumes: `_resting_executor`, `_advance_with_quotes`, `_quote`, `_accepted`, `_canceled`, `_rejected`, `_deliver_fill`, `_held`, `_intent`, `_intent_entry`, `_intent_outcome`, `_record`, `exec_dir`, `KILL_FILE`, `NOW`, `StubCache`, `StubClient`, `TimeInForce`, `Price`, `SimpleNamespace`, `timedelta` from the test module's existing names; `_limit_price`, `_resubmit`, `_fallback`, `_finish_active`, `_finish_revoked`, `_enter`, `_level_permits`, `_QUOTE_SILENCE`, `_MAX_REPRICES` in the executor.
- Produces: `_ActiveIntent.quote_seq` and `.priced_seq` (defaults 0, so every keyword construction in `tests/test_engine_node.py` and the test module keeps working); the phase `awaiting_reprice`; `ProbeExecutor._reprice_at_touch(active)` and `._time_box_with_nothing_resting(active)`; the row's `order` payload keys `bid`, `ask`, `quote_seq`; `_resubmit`'s and `_poll`'s `filled` end below one lot step; the ended order's events taking `_on_detached_event` while the reprice waits.

- [ ] **Step 1: Confirm the tree is at the spec's basis**

Run: `grep -c 'awaiting_reprice' cli/engine/executor.py`
Expected: `0`. Any other count means the phase already exists; stop and report it to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_executor.py`**

The first replacement is the whole old ladder case; the six after it each add one line to an existing case.

Replace, in `tests/test_engine_executor.py`, this block:

```python
def test_both_crossing_surfaces_count_one_reprice_and_the_sixth_refuses(tmp_path):
    """Surface 1: OrderRejected(due_post_only=True) -- the adapter's synchronous mapping.
    Surface 2: accept-then-venue-cancel (OrderCanceled with no cancel requested). Alternate them:
    5 reprices happen (6 submissions total), the 6th reprice is refused and the intent halts
    unfilled with NO 7th order."""
    ex, client, now = _resting_executor(tmp_path)  # helper: plan accepted, first order submitted
    for i in range(5):
        if i % 2 == 0:
            ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        else:
            ex.on_order_event(_canceled(client.last_order_id))
        ex.on_quote(_quote(bid=30000.0, ask=30001.0))
    assert len(client.submitted) == 6  # initial + 5 reprices
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert len(client.submitted) == 6  # the sixth reprice refused, nothing new
    assert _intent_outcome(tmp_path) == "unfilled"
```

with:

```python
def test_a_venue_cancel_off_the_priced_tick_waits_for_the_next_quote_before_repricing(tmp_path):
    """The stored quote priced the order the venue just cancelled as crossing, so repricing off it
    is the same order again. The resubmission waits for a newer tick and prices off that; both
    rows record the tick that priced them."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))

    ex.on_order_event(_canceled(client.last_order_id))  # unrequested: the venue's post-only cancel

    assert len(client.submitted) == 1, "a second order means it repriced off the tick that priced the first"
    assert ex._active.phase == "awaiting_reprice"
    assert _record(tmp_path)["submitted"][0]["state"] == "venue_canceled"

    ex.on_quote(_quote(bid=29990.0, ask=29991.0))

    assert len(client.submitted) == 2
    second, _ = client.submitted[1]
    assert (second.price, second.time_in_force, second.post_only) == (29990.0, TimeInForce.GTC, True)
    assert ex._active.phase == "resting"
    rows = _record(tmp_path)["submitted"]
    assert [(r["order"]["bid"], r["order"]["ask"], r["order"]["quote_seq"]) for r in rows] == [
        (30000.0, 30001.0, 1),
        (29990.0, 29991.0, 2),
    ]


def test_a_tick_that_landed_before_the_cancel_reprices_on_the_cancel_itself(tmp_path):
    """The other arm of the comparison: a tick newer than the priced one has already arrived, so
    nothing is waited for. A rule that always waited would pass the case above and lose a tick."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_quote(_quote(bid=29990.0, ask=29991.0))

    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 2
    assert client.submitted[1][0].price == 29990.0
    assert ex._active.phase == "resting"


def test_alternating_crossings_place_one_order_per_tick_and_the_sixth_crossing_crosses_through_the_ioc(tmp_path):
    """Both crossing surfaces alternated, each answered by one new tick: one order per tick, five
    reprices, six post-only orders. The sixth crossing spends the maker budget and, in `execute`
    mode, crosses through the bounded IOC at the opposite touch instead of ending `unfilled`; three
    returned remainders end it `unfilled` with the fallback's own reason, nine orders in all."""
    ex, client, clock = _resting_executor(tmp_path)
    for i in range(5):
        if i % 2 == 0:
            ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        else:
            ex.on_order_event(_canceled(client.last_order_id))
        assert len(client.submitted) == i + 1, "the reprice fired before its tick"
        ex.on_quote(_quote(bid=30000.0 - i, ask=30001.0 - i))
        assert len(client.submitted) == i + 2
    assert all(order.post_only is True for order, _ in client.submitted)

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

    assert len(client.submitted) == 7
    ioc, _ = client.submitted[6]
    assert (ioc.price, ioc.time_in_force, ioc.post_only) == (29997.0, TimeInForce.IOC, False)  # the last tick's ask
    assert ex._active.phase == "ioc"

    for _ in range(3):
        ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 9
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "unfilled" and intent["reasons"] == ["the bounded fallback did not fill"]


def test_a_rest_hold_ladder_spent_by_rejections_ends_unfilled_and_never_crosses(tmp_path):
    """The rest modes keep the ladder's old end: a spent budget is `unfilled` with no IOC, since a
    mode built never to fill may not take."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    for i in range(5):
        ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        ex.on_quote(_quote(bid=30000.0 - i, ask=30001.0 - i))
    assert len(client.submitted) == 6

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

    assert len(client.submitted) == 6
    assert all(order.post_only is True for order, _ in client.submitted)
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "unfilled" and intent["reasons"] == ["reprice budget exhausted"]


def test_a_kill_file_landing_while_a_reprice_waits_revokes_on_the_tick_with_no_cancel(tmp_path):
    """No order rests while the reprice waits, so the revoke has nothing to cancel and ends the
    intent on the tick itself; the plan halts as every revoke halts it."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked" and "kill_switch" in intent["reasons"]
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_quote_silence_while_a_reprice_waits_revokes_on_the_tick_with_no_cancel(tmp_path):
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked" and intent["reasons"] == ["quote_silence"]


def test_the_time_box_elapsing_while_a_reprice_waits_fires_the_ioc_with_no_cancel(tmp_path):
    """The box declares the maker attempt over; with nothing resting there is nothing to cancel,
    so the IOC fires on the tick, at the opposite touch of the stored quote. The box is reached
    inside the quote-silence bound because the last tick landed ten seconds before the box."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=14.75)
    assert clock.now == NOW + timedelta(minutes=14, seconds=50)
    ex.on_order_event(_canceled(client.last_order_id))  # ticks have arrived since the first order: repriced at once
    assert len(client.submitted) == 2
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))  # none since the second: the reprice waits
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=15, seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == []
    assert len(client.submitted) == 3
    ioc, _ = client.submitted[2]
    assert (ioc.price, ioc.time_in_force, ioc.post_only) == (30001.0, TimeInForce.IOC, False)


def test_the_hold_elapsing_while_a_rest_hold_reprice_waits_ends_it_expired_with_no_cancel(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=15)])
    _advance_with_quotes(ex, client, clock, minutes=14.75)
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert len(client.submitted) == 2
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=15, seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 2
    assert _intent_outcome(tmp_path) == "rest_hold_expired"


def test_a_sell_closes_six_accept_then_cancel_crossings_end_in_an_ioc_at_the_bid(tmp_path):
    """The 2026-09-25 shape: a margin close, a sell, accepted and then cancelled by the venue as
    crossing six times, each crossing answered by one tick, so each order is priced off a newer ask;
    the sixth crossing's IOC is bounded by the last tick's bid, the opposite touch on this side, and
    carries the closer's reduce-only flag."""
    client = StubClient(StubCache(positions=_held(**{"BTC/EUR": 0.001})))
    ex, client, clock = _resting_executor(
        tmp_path, client=client, intents=[_intent(side="sell", action="close", notional_eur=90.0, leverage=2)]
    )
    for i in range(5):
        ex.on_order_event(_accepted(client.last_order_id))
        ex.on_order_event(_canceled(client.last_order_id))
        assert len(client.submitted) == i + 1, "the reprice fired before its tick"
        ex.on_quote(_quote(bid=30000.0 + i, ask=30001.0 + i))
    assert [order.price for order, _ in client.submitted] == [30001.0, 30001.0, 30002.0, 30003.0, 30004.0, 30005.0]

    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 7
    ioc, _ = client.submitted[6]
    assert (ioc.price, ioc.time_in_force, ioc.post_only, ioc.reduce_only) == (30004.0, TimeInForce.IOC, False, True)


def test_a_fill_racing_the_venue_cancel_lands_detached_while_the_reprice_waits(tmp_path):
    """`ownTrades` and `openOrders` have no cross-stream ordering, so a fill on the cancelled order can
    land inside the wait. That order is no longer in flight: the fill takes the detached path, which
    appends without a state claim and credits the intent, so the row keeps `venue_canceled` and the
    replacement is sized to the remainder."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    assert ex._active.phase == "awaiting_reprice"

    _deliver_fill(ex, client, "O-1", 0.1, px=30.0)

    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("venue_canceled", 0.5)
    ex.on_quote(_quote(bid=30.0, ask=30.05))
    assert client.submitted[1][0].quantity == 0.5


def test_a_replayed_cancel_ack_while_the_reprice_waits_counts_no_crossing(tmp_path):
    """A second `OrderCanceled` for the order the venue already ended is evidence on its row, not a
    crossing: it takes the detached path, and the maker budget is not spent on a replay."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted("O-1"))
    ex.on_order_event(_canceled("O-1"))
    assert (ex._active.phase, ex._active.reprices) == ("awaiting_reprice", 1)

    ex.on_order_event(_canceled("O-1"))

    assert (ex._active.phase, ex._active.reprices, len(client.submitted)) == ("awaiting_reprice", 1, 1)
    assert [e["type"] for e in _record(tmp_path)["submitted"][0]["events"]] == ["OrderAccepted", "OrderCanceled", "OrderCanceled"]


def test_a_late_fill_completing_the_intent_while_the_reprice_waits_ends_it_filled_on_the_tick(tmp_path):
    """The cancelled order's late fills reach the target inside the wait, so the tick has nothing left
    to order: the intent ends `filled` with the whole quantity, where a remainder below one lot step
    would otherwise go out as an order the venue refuses."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    _deliver_fill(ex, client, "O-1", 0.6, px=30.0)

    ex.on_quote(_quote(bid=30.0, ask=30.05))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["filled_qty"]) == ("filled", 1.0)


def test_a_late_fill_completing_the_intent_while_the_reprice_waits_ends_it_filled_on_the_timer_too(tmp_path):
    """The completing fill can be the last thing the feed delivers for a while: the timer ends the
    intent `filled` on its next tick, where the wait's revoke arms would otherwise end it `revoked`
    on silence or the kill file, its whole quantity in `filled_qty`, and halt the plan."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    assert ex._active.phase == "awaiting_reprice"
    _deliver_fill(ex, client, "O-1", 0.6, px=30.0)

    clock.now = NOW + timedelta(seconds=31)  # past the silence bound, and no tick since the fill
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["filled_qty"]) == ("filled", 1.0)


def test_a_half_book_tick_while_a_reprice_waits_prices_nothing(tmp_path):
    """A tick carrying one side is not stored, so it is not the newer tick the reprice waits for:
    priced off the stale touch, the resubmission would be the crossing order again."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    ex.on_quote(SimpleNamespace(instrument_id="BTC/EUR.KRAKEN", bid_price=Price(29990.0, 1), ask_price=None))

    assert len(client.submitted) == 1 and ex._active.phase == "awaiting_reprice"
    ex.on_quote(_quote(bid=29990.0, ask=29991.0))
    assert len(client.submitted) == 2 and client.submitted[1][0].price == 29990.0


def test_a_half_book_tick_while_the_order_rests_is_not_the_newer_tick_a_reprice_waits_for(tmp_path):
    """A one-sided tick landing while the order rests advances no count, so the crossing after it
    still waits: counted, it would reprice at once off the touch it crossed on."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_quote(SimpleNamespace(instrument_id="BTC/EUR.KRAKEN", bid_price=Price(29990.0, 1), ask_price=None))

    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 1 and ex._active.phase == "awaiting_reprice"


def test_quote_silence_outranks_the_time_box_while_a_reprice_waits(tmp_path):
    """The checks are `resting`'s, in `resting`'s order: a feed dead for longer than the silence bound
    ends the intent `revoked` before the box can fire an IOC off that stale quote."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=14.75)
    ex.on_order_event(_canceled(client.last_order_id))  # ticks have arrived since the first order: repriced at once
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=15, seconds=25)  # 35 s after the last tick, and past the box
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 2
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked" and intent["reasons"] == ["quote_silence"]


def test_a_rest_cancel_ladder_spent_by_rejections_ends_unfilled_and_never_crosses(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-cancel")])
    for i in range(5):
        ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        ex.on_quote(_quote(bid=30000.0 - i, ask=30001.0 - i))
    assert len(client.submitted) == 6

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

    assert len(client.submitted) == 6 and client.canceled == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "unfilled" and intent["reasons"] == ["reprice budget exhausted"]


@pytest.mark.parametrize("filled_before, outcome", [(0.0, "rest_cancel_ok"), (0.2, "partial")])
def test_the_time_box_elapsing_while_a_rest_cancel_reprice_waits_ends_it_rest_cancel_ok_or_partial_with_no_cancel(
    tmp_path, filled_before, outcome
):
    """A mode built never to fill takes no IOC when its box elapses inside the wait; a fill that
    landed ahead of the acceptance makes the end `partial`, since the name alone says nothing filled."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05, intents=[_intent(mode="rest-cancel")])
    if filled_before:
        _deliver_fill(ex, client, "O-1", filled_before, px=30.0)  # ahead of the acceptance: the streams' own ordering
    _advance_with_quotes(ex, client, clock, minutes=14.75, bid=30.0, ask=30.05)
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel; ticks have arrived since: repriced at once
    assert len(client.submitted) == 2
    ex.on_order_event(_canceled(client.last_order_id))  # none since the second: the reprice waits
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=15, seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 2
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["filled_qty"]) == (outcome, filled_before)


def test_a_raise_inside_a_waiting_reprice_journals_the_fills_that_already_happened(tmp_path):
    """A raise inside the resubmission refuses the intent on the tick, and the refusal carries
    `filled`, so a real partial is not erased from the summary."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    assert ex._active.phase == "awaiting_reprice"
    client.cache._raises = True  # the Cache's instrument read raises on the tick

    ex.on_quote(_quote(bid=30.0, ask=30.05))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"], intent["filled_qty"]) == ("refused", ["quote handling failed"], 0.4)
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    ex.on_order_event(_accepted("O-1"))
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> reprice
    assert len(client.submitted) == 2

    metrics = RecordingMetrics()
```

with:

```python
    ex.on_order_event(_accepted("O-1"))
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> the reprice waits for a tick
    ex.on_quote(_quote(bid=30.0, ask=30.05))
    assert len(client.submitted) == 2

    metrics = RecordingMetrics()
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    clock.now = NOW + timedelta(minutes=7)
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert len(client.submitted) == 2  # the rejection repriced: nothing was ever resting
```

with:

```python
    clock.now = NOW + timedelta(minutes=7)
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    ex.on_quote(_quote())  # the tick the reprice waits for, newer than the one that priced the rejected order
    assert len(client.submitted) == 2  # the rejection repriced: nothing was ever resting
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    (exec_dir(tmp_path) / KILL_FILE).touch()
    ex.on_order_event(_canceled(client.last_order_id))  # the venue's own cancel

    assert len(client.submitted) == 1  # the gate refused the reprice
```

with:

```python
    (exec_dir(tmp_path) / KILL_FILE).touch()
    ex.on_order_event(_canceled(client.last_order_id))  # the venue's own cancel
    ex.on_quote(_quote(bid=30.0, ask=30.05))  # the tick the reprice waits for

    assert len(client.submitted) == 1  # the gate refused the reprice
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> reprice
    resting = client.submitted[1][0]
```

with:

```python
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> the reprice waits for a tick
    ex.on_quote(_quote(bid=30.0, ask=30.05))
    resting = client.submitted[1][0]
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    ex.on_order_event(_canceled("O-1"))  # superseded by the reprice

    _deliver_fill(ex, client, "O-1", 0.3, px=30.0)
```

with:

```python
    ex.on_order_event(_canceled("O-1"))  # superseded by the reprice, once its tick arrives
    ex.on_quote(_quote(bid=30.0, ask=30.05))

    _deliver_fill(ex, client, "O-1", 0.3, px=30.0)
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    ex.on_order_event(_canceled(client.last_order_id))  # would reprice

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["the kill switch tripped in this process"]
```

with:

```python
    ex.on_order_event(_canceled(client.last_order_id))  # would reprice, once its tick arrives
    ex.on_quote(_quote())

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["the kill switch tripped in this process"]
```

- [ ] **Step 3: Run the file and watch the new cases fail**

Run: `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`
Expected: `17 failed, 247 passed`. `test_a_venue_cancel_off_the_priced_tick_waits_for_the_next_quote_before_repricing` fails on `a second order means it repriced off the tick that priced the first`; `test_alternating_crossings_place_one_order_per_tick_and_the_sixth_crossing_crosses_through_the_ioc` and `test_a_sell_closes_six_accept_then_cancel_crossings_end_in_an_ioc_at_the_bid` on `the reprice fired before its tick`; `test_a_late_fill_completing_the_intent_while_the_reprice_waits_ends_it_filled_on_the_tick` on `assert 2 == 1`, a second order out; `test_a_half_book_tick_while_the_order_rests_is_not_the_newer_tick_a_reprice_waits_for` on `assert (2 == 1)`, the crossing repriced at once; `test_a_replayed_cancel_ack_while_the_reprice_waits_counts_no_crossing` on `assert ('resting', 1) == ('awaiting_reprice', 1)`; the eleven other arms that enter the wait — the five `with_no_cancel` cases, the rest-cancel one in both arms, the racing fill, the half-book tick, the completing fill on the timer, the silence-before-box case and the raise — on `assert 'resting' == 'awaiting_reprice'`. `test_a_tick_that_landed_before_the_cancel_reprices_on_the_cancel_itself` and the two `spent_by_rejections` cases pass on the old tree, since each pins the arm today's code already takes; the six adjusted cases pass either way.

- [ ] **Step 4: The counters, the waiting phase and the fall-through in `cli/engine/executor.py`**

Replace, in `cli/engine/executor.py`, this block:

```python
    # `revoke_reasons`' text instead would tie the outcome to a string written for a human.
    hold_expired: bool = False
```

with:

```python
    # `revoke_reasons`' text instead would tie the outcome to a string written for a human.
    hold_expired: bool = False
    # `quote_seq` counts the ticks stored since the intent started and `priced_seq` is its value when
    # the live order was priced, so a reprice can tell a tick that arrived after that order from the
    # one that priced it.
    quote_seq: int = 0
    priced_seq: int = 0
```

Replace, in `cli/engine/executor.py`, this block:

```python
            bid = _as_price(getattr(tick, "bid_price", None))
            ask = _as_price(getattr(tick, "ask_price", None))
            if bid is not None and ask is not None:
                # Both sides or neither: a reprice needs the near touch and the IOC fallback the
                # far one, and half a book is not a book to price either against.
                active.bid, active.ask = bid, ask
                active.last_quote_at = self._now()
            if active.phase == "awaiting_quote":
                self._first_submission(active)
```

with:

```python
            bid = _as_price(getattr(tick, "bid_price", None))
            ask = _as_price(getattr(tick, "ask_price", None))
            stored = bid is not None and ask is not None
            if stored:
                # Both sides or neither: a reprice needs the near touch and the IOC fallback the
                # far one, and half a book is not a book to price either against.
                active.bid, active.ask = bid, ask
                active.last_quote_at = self._now()
                active.quote_seq += 1
            if active.phase == "awaiting_quote":
                self._first_submission(active)
            elif active.phase == "awaiting_reprice" and stored:
                self._reprice_at_touch(active)
```

Replace, in `cli/engine/executor.py`, this block:

```python
        except Exception:
            logger.exception("executor quote handling raised -- refusing the intent")
            if self._active is not None:
                self._finish_active("refused", ("quote handling failed",))
```

with:

```python
        except Exception:
            logger.exception("executor quote handling raised -- refusing the intent")
            if self._active is not None:
                # `filled` carried, `_submit`'s rule: a resubmission runs here now, and a raise after
                # earlier orders filled must not erase what was bought from the operator's summary.
                self._finish_active("refused", ("quote handling failed",), self._active.filled)
```

Replace, in `cli/engine/executor.py`, this block:

```python
            "leverage": intent.leverage,
            # The startup pass's ONLY witness: whether the order this row stands for was a reducer.
            "reduce_only": active.reduce_only,
        }
        params = {"leverage": intent.leverage} if intent.leverage is not None else None
```

with:

```python
            "leverage": intent.leverage,
            # The startup pass's ONLY witness: whether the order this row stands for was a reducer.
            "reduce_only": active.reduce_only,
            # The quote this order was priced from: two rows of one intent sharing a `quote_seq` were priced off one tick.
            "bid": active.bid,
            "ask": active.ask,
            "quote_seq": active.quote_seq,
        }
        active.priced_seq = active.quote_seq
        params = {"leverage": intent.leverage} if intent.leverage is not None else None
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _reprice(self, active: _ActiveIntent) -> None:
        """Two callers, not two universally-reachable ones: the venue's synchronous post-only
        rejection and its accept-then-cancel. The rejection arm is unconditional -- nothing was ever
        resting, so the recomputed price is simply this intent's own offset off the CURRENT touch,
        and a tight-offset intent needs that recovery to get resting at all. The accept-then-cancel
        arm is filtered before it arrives: a rest-hold order is a drill's subject and its
        venue-originated cancel is terminal there (spec 00108 D5), never a reprice. The counter
        counts RESUBMISSIONS -- the first submission was never a reprice -- so `_MAX_REPRICES` of
        them happen and the next one refuses."""
```

with:

```python
    def _reprice(self, active: _ActiveIntent) -> None:
        """Two callers: the venue's synchronous post-only rejection and its accept-then-cancel. The
        rejection arm is unconditional; the accept-then-cancel arm is filtered before it arrives,
        since a rest-hold order's venue cancel is terminal. The counter counts RESUBMISSIONS -- the
        first submission was never a reprice -- so `_MAX_REPRICES` of them happen; the next crossing
        spends the maker budget, and in `execute` mode that crosses through the bounded IOC rather
        than ending the intent, since an unfilled leg strands the probe.

        A crossing says the stored touch is behind the venue's book, so the resubmission prices off
        a tick newer than the one that priced the order it replaces: at once when one has already
        arrived, else from `awaiting_reprice` when `on_quote` stores one; without the wait the whole
        budget goes in one dispatch. The wait is entered with the ended order detached, so a fill
        racing the cancel or a replayed ack takes the detached path -- a row append with no state
        claim, the fill credited to the intent -- and spends no budget."""
```

Replace, in `cli/engine/executor.py`, this block:

```python
        active.reprices += 1
        if active.reprices > _MAX_REPRICES:
            self._finish_active("unfilled", ("reprice budget exhausted",), active.filled)
            return
        price = self._limit_price(active)
        if price is None:
            self._finish_active("refused", (f"no usable touch price for {active.intent.symbol}",), active.filled)
            return
        self._resubmit(active, price, time_in_force=TimeInForce.GTC, post_only=True, next_phase="resting")

    def _fallback(self, active: _ActiveIntent) -> None:
```

with:

```python
        active.reprices += 1
        if active.reprices > _MAX_REPRICES:
            if active.intent.mode == "execute":
                self._fallback(active)
            else:
                self._finish_active("unfilled", ("reprice budget exhausted",), active.filled)
            return
        if active.quote_seq > active.priced_seq:
            self._reprice_at_touch(active)
            return
        active.client_order_id = active.order = None
        self._enter(active, "awaiting_reprice")

    def _reprice_at_touch(self, active: _ActiveIntent) -> None:
        price = self._limit_price(active)
        if price is None:
            self._finish_active("refused", (f"no usable touch price for {active.intent.symbol}",), active.filled)
            return
        self._resubmit(active, price, time_in_force=TimeInForce.GTC, post_only=True, next_phase="resting")

    def _fallback(self, active: _ActiveIntent) -> None:
```

Replace, in `cli/engine/executor.py`, this block:

```python
        remainder = active.target_qty - active.filled
        result, detail = self._place(active, remainder, price, time_in_force=time_in_force, post_only=post_only)
```

with:

```python
        if active.target_qty - active.filled < active.constraints.lot_step:
            # A late fill on the order this one replaces can complete the intent before the tick
            # arrives: `_on_fill`'s completion test, so no order below the venue's minimum goes out.
            self._finish_active("filled", (), active.filled)
            return
        remainder = active.target_qty - active.filled
        result, detail = self._place(active, remainder, price, time_in_force=time_in_force, post_only=post_only)
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _poll(self, now: datetime, verdict: GateVerdict) -> None:
        """The timer's whole authority over an in-flight intent. Only a RESTING order is revocable
        or time-boxable: a cancel is already outstanding in `cancelling`, and an IOC resolves at the
        venue within the tick rather than sitting there."""
        active = self._active
        if active.phase == "awaiting_quote":
            if now > active.quote_deadline:
                self._finish_active("refused", (f"no quote within {int(_QUOTE_WAIT.total_seconds())}s",))
            return
        if active.phase != "resting":
```

with:

```python
    def _poll(self, now: datetime, verdict: GateVerdict) -> None:
        """The timer's whole authority over an in-flight intent. A RESTING order, or a reprice
        waiting for its tick, is revocable or time-boxable: a cancel is already outstanding in
        `cancelling`, and an IOC resolves at the venue within the tick rather than sitting there."""
        active = self._active
        if active.phase == "awaiting_quote":
            if now > active.quote_deadline:
                self._finish_active("refused", (f"no quote within {int(_QUOTE_WAIT.total_seconds())}s",))
            return
        if active.phase == "awaiting_reprice":
            # Nothing rests, so a revoke ends the intent on this tick with no cancel to wait on; the
            # checks are `resting`'s, in `resting`'s order, after `_resubmit`'s completion test: a
            # detached fill can complete the intent inside the wait, and a feed silent from then on
            # would otherwise revoke what has already filled.
            if active.target_qty - active.filled < active.constraints.lot_step:
                self._finish_active("filled", (), active.filled)
            elif not _level_permits(verdict.level, active.intent):
                active.revoke_reasons = tuple(verdict.reasons)
                self._finish_revoked(active)
            elif active.last_quote_at is not None and now - active.last_quote_at > _QUOTE_SILENCE:
                active.revoke_reasons = ("quote_silence",)
                self._finish_revoked(active)
            elif now > active.timebox_at:
                self._time_box_with_nothing_resting(active)
            return
        if active.phase != "resting":
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _start_intent(self, now: datetime) -> None:
        """Always either arms `_active` or advances `_index` -- `_pump`'s loop depends on it."""
```

with:

```python
    def _time_box_with_nothing_resting(self, active: _ActiveIntent) -> None:
        """The time-box elapsing while a reprice waits: `_on_cancel_ack`'s requested arm less the
        cancel, since no order is out to cancel."""
        if active.intent.mode == "execute":
            self._fallback(active)
        elif active.intent.mode == "rest-cancel":
            self._finish_active("rest_cancel_ok" if active.filled == 0.0 else "partial", (), active.filled)
        else:
            self._finish_active("rest_hold_expired" if active.filled == 0.0 else "partial", (), active.filled)

    def _start_intent(self, now: datetime) -> None:
        """Always either arms `_active` or advances `_index` -- `_pump`'s loop depends on it."""
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
An intent ending `unfilled`, `refused`, `rejected`, `partial` or `ambiguous` stops there, and so do```

with:

```markdown
An intent ending `unfilled`, `refused`, `rejected`, `partial` or `ambiguous` stops there (an `execute` intent's `unfilled` follows both ladders, the maker reprices and the bounded IOC attempts, so its `filled_qty` is what its orders got, maker and IOC alike), and so do```

- [ ] **Step 5: Run the file and watch it pass**

Run: `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`
Expected: `264 passed`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_engine_execledger.py tests/test_engine_node.py tests/test_engine_metrics.py tests/test_engine_executor.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1914 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates, `ZCRYPTO_LIVE_VENUE_TESTS` unset.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/executor.py infra/runbooks/engine-procedures.md tests/test_engine_executor.py
git commit -m "fix(engine): a reprice waits for a tick newer than the one it crossed on, and an exhausted execute ladder crosses through the IOC

Measured on 2026-09-25: a post-only sell the venue accepted and cancelled as crossing was
re-submitted five times off the same stored quote, six orders at one price inside 206 ms, and the
intent ended unfilled with no IOC, the fallback being reachable only through the time-box. The
intent now counts the ticks it stores and remembers the count its live order was priced at; a
crossing resubmits at once when a newer tick has arrived and otherwise waits in awaiting_reprice
for the next stored tick, bounded as a resting order is -- the gate level, quote silence and the
time-box, in that order -- a revoke ending it on the tick with no cancel to wait on and the
time-box taking the cancel ack's arm less the cancel. The sixth crossing in execute mode crosses
through the bounded IOC fallback, the intent ending unfilled only once both budgets are spent; the
rest modes keep unfilled with the maker reason. Entering the wait detaches the ended order, so a
fill racing the cancel or a replayed ack takes the detached path, and a remainder below one lot
step ends the intent filled, on the tick or on the timer; the quote handler's refusal carries the
fills.
Each row's order payload records the bid, the ask and the tick count it was priced from, inside
the payload, so no schema moves. The runbook's Nothing-retries-itself rule says an execute intent's
unfilled follows both ladders.

Cases: the venue's cancel off the priced tick waits and the next quote prices the replacement,
both rows carrying their tick; a tick that landed before the cancel reprices on the cancel;
alternating crossings with one tick each, six post-only orders, the sixth crossing firing the IOC
at the last ask and three returned remainders ending it unfilled after nine orders; a sell close
crossed six times by accept-then-cancel ending in an IOC at the last bid; a rest-hold ladder and a
rest-cancel ladder spent by rejections ending unfilled with no IOC; a kill file, quote silence and
the time-box each ending a waiting reprice on the tick with no cancel, the box firing the IOC for
execute, rest_hold_expired for rest-hold and rest_cancel_ok, or partial on a fill, for rest-cancel,
and silence outranking the box inside the wait; a fill racing the venue's cancel landing detached
while the reprice waits, the row keeping venue_canceled and the replacement sized to the remainder;
a replayed cancel ack counting no crossing; late fills completing the intent inside the wait ending
it filled on the tick, and on the timer when no tick follows; a half-book tick pricing nothing, and
one landing while the order rests counting as no newer tick; a raise inside the waiting reprice
journaling the fills already made. Six existing cases deliver the quote the reprice now waits for.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with twelve probes, then record their verdicts by a message-only amend**

The control renames the waiting phase where `_reprice` enters it, so `on_quote` never resubmits from it and the waiting cases fail. The mutations, in order: every reprice fires at once; the sixth crossing does not cross in execute mode; the time-box is disarmed while a reprice waits; the tick count never advances, so a reprice waits for good; a half book resubmits off the stale touch; a rest-cancel ladder crosses through the IOC; the ended order stays attached while the reprice waits; a completed intent places its remainder anyway; the handler's refusal drops the fills; a waiting rest-cancel's box takes the IOC; a one-sided tick counts, so the crossing after it reprices at once; the timer's completion test is disarmed, so a completed intent waits for silence to revoke it. Each `-k` selects 20 of the file's 264 cases:

```bash
K="priced_tick or before_the_cancel or crossings_place or spent_by_rejections or reprice_waits or waiting_reprice or sell_closes"
C='s/self._enter(active, "awaiting_reprice")/self._enter(active, "resting")/'
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/if active.quote_seq > active.priced_seq:/if True:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            if active.intent.mode == "execute":$/            if active.intent.mode == "never":/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/            elif now > active.timebox_at:/            elif False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/                active.quote_seq += 1/                pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/            elif active.phase == "awaiting_reprice" and stored:/            elif active.phase == "awaiting_reprice":/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            if active.intent.mode == "execute":$/            if active.intent.mode != "rest-hold":/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/        active.client_order_id = active.order = None/        pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if active.target_qty - active.filled < active.constraints.lot_step:$/        if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/self._finish_active("refused", ("quote handling failed",), self._active.filled)/self._finish_active("refused", ("quote handling failed",))/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            self._finish_active("rest_cancel_ok" if active.filled == 0.0 else "partial", (), active.filled)/            self._fallback(active)/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^                active.quote_seq += 1$/            active.quote_seq += 1/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            if active.target_qty - active.filled < active.constraints.lot_step:$/            if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/executor.py`, control the waiting phase
renamed where `_reprice` enters it so the waiting cases fail, through
`-k "priced_tick or before_the_cancel or crossings_place or spent_by_rejections or reprice_waits or waiting_reprice or sell_closes"`:
every reprice firing at once, KILLED, control proven; the sixth crossing not crossing in execute
mode, KILLED, control proven; the time-box disarmed while a reprice waits, KILLED, control proven;
the tick count never advancing, KILLED, control proven; a half book repricing off the stale touch,
KILLED, control proven; a rest-cancel ladder crossing through the IOC, KILLED, control proven; the
ended order left attached while the reprice waits, KILLED, control proven; a completed intent
placing its remainder, KILLED, control proven; the handler's refusal dropping the fills, KILLED,
control proven; a waiting rest-cancel's box taking the IOC, KILLED, control proven; a one-sided
tick counted, KILLED, control proven; the timer's completion test disarmed, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 2: The ledger reader matches margin rows, names the no-fill types, reports the matched rows' fees and prints at the export's precision

What this task decides, where the spec leaves it open:

- `matched` stays one row count over both matched types, and the rendered line and `_cost_over`'s basis read `ledger trade or margin row(s)`; a split by type would be two counts for one question.
- The matched-fee line prints only when something matched: a `0.0000` under an export that matched nothing would read as a figure.
- The closed-world fixture uses the export's sixteen-column header through `_export`'s `header` argument and a `_real_row` helper, leaving `_HEADER` and every existing ten-column case as they are; its figures are synthetic and its rollover rows carry the measured 0.0040.
- The matched-fee render is driven through the real command with `reconcile_ledger` stood in for by a matched result, since no synthetic journal carries a venue trade id and a real export is not committed.
- `test_a_row_type_the_reader_places_nowhere_is_named_in_the_report` and `test_a_row_type_this_reader_places_nowhere_is_counted_by_type`, which pinned `margin` as an unplaced type, are replaced by cases on a type the reader has not met (`staking`), the property they held.
- A fee charged in EURC counts as euro at par, under `_EURO_FEE_ASSETS`, for the rollover arm and the matched arm alike: the venue charges a margin open's fee in EURC after converting euro to it at par beside the row, the export's `collateralconversion` pair, and the adapter reports that fill's commission in euro, so the journal's figure the line is read against already counts it (0.084 EURC on the BTC/EUR open of 2026-09-25, 0.08 EUR in the journal).
- The closed-world fixture spells its assets as the export does, `EUR`, `BTC` and `EURC`, and carries the EURC-charged open's `margin` row beside its conversion pair, the row a euro-only sum drops.

**Files:**
- Modify: `cli/engine/tracking.py` (`LedgerRow.refid`'s comment; the two lines above `_NO_FILL_LEDGER_TYPES` and the set itself, `_EURO_FEE_ASSETS` and `_MATCHED_LEDGER_TYPES` inserted above them; `reconcile_ledger` whole)
- Modify: `cli/engine/command.py` (`_cost_over`'s `basis` text; `_render_tracking`'s ledger block from the `Ledger export:` line through the `row types this reader places nowhere` line)
- Modify: `README.md` (the `tracking-report` row: its `fails the reconciliation, not the run` sentence, its `insufficient-data`, never `ok` sentence, and its sentences from `Rollover rows are summed` through `read at all.`)
- Modify: `infra/runbooks/engine-procedures.md` (§6 item 3's lead-in sentence and its first two bullets, `rollover fees 0.00` and `Only trade rows are matched today`)
- Test: `tests/test_engine_tracking.py` (`test_a_non_trade_non_rollover_row_is_neither_matched_nor_unmatched` and `test_a_row_type_this_reader_places_nowhere_is_counted_by_type` replaced by six cases, `_REAL_HEADER` and `_real_row` among them; `test_a_row_type_the_reader_places_nowhere_is_named_in_the_report` replaced by three CLI cases; `test_a_failed_reconciliation_withdraws_the_proposed_rate_from_the_payload` gaining the `basis` assertion)

**Interfaces:**
- Consumes: `_export`, `_lfill`, `_tracking_argv`, `_invoke`, `mixed_schema_fixture`, `reconcile_ledger`, `read_ledger_export`, `json`, `pytest` from the test module's existing names; `EUR_CODES` in the reader.
- Produces: `_EURO_FEE_ASSETS`, `_MATCHED_LEDGER_TYPES`; `reconcile_ledger`'s result keys `matched_fees_eur` and `known` beside the existing six; the rendered lines `fees on the matched rows <x> EUR` and `rows with no fill behind them by construction: <type> <count>`; `_REAL_HEADER` and `_real_row(...)` in the test module.

- [ ] **Step 1: Confirm Task 1 has landed and the reader is at the spec's basis**

Run: `grep -c '_reprice_at_touch' cli/engine/executor.py; grep -c '_MATCHED_LEDGER_TYPES' cli/engine/tracking.py`
Expected: `3` then `0`. A first count other than 3 means Task 1 is not on the branch; a second other than 0 means the match already widened; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_tracking.py`**

Replace, in `tests/test_engine_tracking.py`, this block:

```python
def test_a_non_trade_non_rollover_row_is_neither_matched_nor_unmatched(tmp_path):
    # A deposit has no fill behind it by construction; failing the reconciliation on one would make
    # every real export FAILED and the signal worthless. It is on the known-irrelevant list, so it
    # is not reported as a type this reader could not place either.
    p = _export(tmp_path, ['"L6","Q1","2026-08-31 00:00:00","deposit","","currency","ZEUR","500.0","0.0","1350.0"'])
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["status"] == "insufficient-data" and out["matched"] == 0 and out["unmatched"] == []
    assert out["ignored"] == {}


def test_a_row_type_this_reader_places_nowhere_is_counted_by_type(tmp_path):
    # `margin` is the one that matters: a margin position writes rows carrying the SAME refid as its
    # trade, and the first export this reader will ever see is a margin export. Consuming it would
    # guess semantics nobody has verified; accepting it silently would hide a whole class of row
    # exactly where the reader is first used. So it is counted and named.
    p = _export(
        tmp_path,
        [
            '"L7","T-1","2026-08-31 00:00:00","margin","","currency","ZEUR","-2.0","0.0","848.0"',
            '"L8","T-1","2026-08-31 00:00:00","margin","","currency","ZEUR","-3.0","0.0","845.0"',
            '"L9","S1","2026-08-31 04:00:00","settled","","currency","XXBT","0.001","0.0","0.001"',
            '"LA","Q1","2026-08-31 04:00:00","withdrawal","","currency","ZEUR","-10.0","0.0","835.0"',
        ],
    )
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["ignored"] == {"margin": 2, "settled": 1}  # the withdrawal is known-irrelevant
    assert out["status"] == "insufficient-data" and out["matched"] == 0 and out["unmatched"] == []
```

with:

```python
def test_a_no_fill_row_type_is_counted_as_known_never_matched(tmp_path):
    # A deposit has no fill behind it by construction; failing the reconciliation on one would make
    # every real export FAILED and the signal worthless. It is counted under `known`, apart from a
    # type the reader has not met.
    p = _export(tmp_path, ['"L6","Q1","2026-08-31 00:00:00","deposit","","currency","ZEUR","500.0","0.0","1350.0"'])
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["status"] == "insufficient-data" and out["matched"] == 0 and out["unmatched"] == []
    assert out["known"] == {"deposit": 1} and out["ignored"] == {}


def test_a_row_type_this_reader_has_not_met_is_counted_by_type(tmp_path):
    p = _export(
        tmp_path,
        [
            '"L7","X1","2026-08-31 00:00:00","staking","","currency","ZEUR","0.01","0.0","848.0"',
            '"LA","Q1","2026-08-31 04:00:00","withdrawal","","currency","ZEUR","-10.0","0.0","835.0"',
        ],
    )
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["ignored"] == {"staking": 1} and out["known"] == {"withdrawal": 1}
    assert out["status"] == "insufficient-data" and out["matched"] == 0 and out["unmatched"] == []


def test_a_margin_row_matching_a_journaled_fill_reconciles_and_carries_its_fee_not_its_pnl(tmp_path):
    # A margin open or close writes no `trade` row: its `margin` row carries the fill's own trade id,
    # the realized PnL as `amount` and the fill's fee as `fee`. The PnL is positive on purpose, so a
    # reader summing `amount` as a cost reads 0.1379 where 0.0795 belongs.
    p = _export(tmp_path, ['"L8","T-1","2026-08-31 00:00:00","margin","","currency","ZEUR","0.1379","0.0795","848.0"'])
    out = reconcile_ledger(read_ledger_export(p), [_lfill("T-1")])
    assert out["status"] == "ok" and out["matched"] == 1 and out["unmatched"] == []
    assert out["matched_fees_eur"] == pytest.approx(0.0795)
    assert out["known"] == {} and out["ignored"] == {}


def test_a_margin_row_matching_no_journaled_fill_FAILS_the_reconciliation(tmp_path):
    p = _export(tmp_path, ['"L8","T-UNKNOWN","2026-08-31 00:00:00","margin","","currency","ZEUR","-0.2","0.08","848.0"'])
    out = reconcile_ledger(read_ledger_export(p), [_lfill("T-1")])
    assert out["status"] == "FAILED" and out["unmatched"] == ["T-UNKNOWN"] and out["matched_fees_eur"] == 0.0


def test_a_rollover_charged_in_eurc_is_summed_at_par_beside_a_euro_one(tmp_path):
    # The rollover arm reads the same asset set as the matched arm: a EURC rollover, unseen in the
    # export so far, counts at par rather than falling out of the figure.
    p = _export(
        tmp_path,
        [
            '"L5","T-2","2026-08-31 14:33:50","rollover","","currency","EUR","-0.0040","0.0040","900.0"',
            '"L6","T-2","2026-08-31 18:33:52","rollover","","currency","EURC","-0.0040","0.0040","0.0800"',
        ],
    )
    out = reconcile_ledger(read_ledger_export(p), [])
    assert out["rollover_fees_eur"] == pytest.approx(0.0080)


_REAL_HEADER = (
    "txid,refid,time,type,subtype,aclass,subclass,asset,wallet,amount,fee,balance,amountusd,feeusd,balanceusd,feecurrency"
)


def _real_row(txid, refid, time, type_, subtype, asset, amount, fee, feecurrency="EUR"):
    """One line in the shape of the venue's own export, all sixteen columns, the usd columns blank."""
    return (
        f'"{txid}","{refid}","{time}","{type_}","{subtype}","currency","","{asset}","spot / main",'
        f'"{amount}","{fee}","0","","","","{feecurrency}"'
    )


def test_every_row_type_of_the_real_export_lands_in_exactly_one_place(tmp_path):
    """The closed world: the six row types the venue's export carries, one arm each -- `trade` and
    `margin` matched by trade id, `rollover` summed, `settled` and `collateralconversion` known
    no-fill types beside `deposit`, nothing left for `ignored`. A journaled spot fill T-1 and two
    margin fills, T-2 charged in euro and T-3 in EURC after the venue's par conversion beside it;
    the rollovers carry T-2, the position's opening trade, and the settle an id of its own; the spot
    fill's BTC leg carries a fee in BTC, outside the euro figure. The shape and the asset spellings
    are the export's; the figures are synthetic."""
    p = _export(
        tmp_path,
        [
            _real_row("L1", "T-1", "2026-09-25 20:44:53", "trade", "tradespot", "EUR", "19.86", "0.0800"),
            _real_row("L2", "T-1", "2026-09-25 20:44:53", "trade", "tradespot", "BTC", "-0.00027", "0.0000027", "BTC"),
            _real_row("L3", "T-2", "2026-09-25 10:32:05", "margin", "", "EUR", "0", "0.0800"),
            _real_row("L4", "T-3", "2026-09-25 10:32:03", "margin", "", "EURC", "0", "0.084000", "EURC"),
            _real_row("L5", "T-2", "2026-09-25 14:33:50", "rollover", "", "EUR", "-0.0040", "0.0040"),
            _real_row("L6", "T-2", "2026-09-25 18:33:52", "rollover", "", "EUR", "-0.0040", "0.0040"),
            _real_row("L7", "T-3", "2026-09-25 10:32:03", "collateralconversion", "", "EUR", "-0.0840", "0", ""),
            _real_row("L8", "T-3", "2026-09-25 10:32:03", "collateralconversion", "", "EURC", "0.084000", "0", ""),
            _real_row("L9", "S-1", "2026-09-25 20:30:26", "settled", "", "EUR", "-20.00", "0", ""),
            _real_row("LA", "S-1", "2026-09-25 20:30:26", "settled", "", "BTC", "0.00027", "0", ""),
            _real_row("LB", "Q-1", "2026-07-01 09:00:00", "deposit", "", "EUR", "100.0", "0", ""),
        ],
        header=_REAL_HEADER,
    )
    out = reconcile_ledger(read_ledger_export(p), [_lfill("T-1"), _lfill("T-2"), _lfill("T-3")])
    assert out["status"] == "ok" and out["n_rows"] == 11
    assert out["matched"] == 4 and out["unmatched"] == []
    assert out["matched_fees_eur"] == pytest.approx(0.2440)
    assert out["rollover_fees_eur"] == pytest.approx(0.0080)
    assert out["known"] == {"collateralconversion": 2, "settled": 2, "deposit": 1}
    assert out["ignored"] == {}
```

Replace, in `tests/test_engine_tracking.py`, this block:

```python
def test_a_row_type_the_reader_places_nowhere_is_named_in_the_report(tmp_path, mixed_schema_fixture):
    # Carried in the payload AND printed: the operator reading the rendered block is the one who has
    # to decide whether the match widens, and a count only a `--json` consumer sees is invisible.
    p = _export(tmp_path, ['"L7","T-1","2026-08-31 00:00:00","margin","","currency","ZEUR","-2.0","0.0","848.0"'])
    argv = _tracking_argv(mixed_schema_fixture, "--simulated-fills", "--ledger-export", str(p))
    run = _invoke(mixed_schema_fixture, argv)
    assert run.exit_code == 0, run.stdout
    assert json.loads(_invoke(mixed_schema_fixture, argv + ["--json"]).stdout)["reconciliation"]["ignored"] == {"margin": 1}
    assert "margin 1" in run.stdout
```

with:

```python
def test_a_row_type_the_reader_has_not_met_is_named_in_the_report(tmp_path, mixed_schema_fixture):
    # Carried in the payload AND printed: the operator reading the rendered block is the one who has
    # to decide what a type the reader has not met means, and a count only a `--json` consumer sees
    # is invisible.
    p = _export(tmp_path, ['"L7","X1","2026-08-31 00:00:00","staking","","currency","ZEUR","0.01","0.0","848.0"'])
    argv = _tracking_argv(mixed_schema_fixture, "--simulated-fills", "--ledger-export", str(p))
    run = _invoke(mixed_schema_fixture, argv)
    assert run.exit_code == 0, run.stdout
    assert json.loads(_invoke(mixed_schema_fixture, argv + ["--json"]).stdout)["reconciliation"]["ignored"] == {"staking": 1}
    assert "staking 1" in run.stdout


def test_the_rollover_figure_prints_at_four_decimals_and_the_no_fill_rows_are_named(tmp_path, mixed_schema_fixture):
    # Four rollover rows of 0.0040 read 0.016 by hand; a two-decimal print made that 0.02, which the
    # runbook's equality check could not accept. A deposit lands on the known no-fill line.
    rows = [
        f'"L{i}","T-OPEN","2026-08-31 0{i}:00:00","rollover","","currency","ZEUR","-0.0040","0.0040","900.0"' for i in range(1, 5)
    ]
    rows.append('"L9","Q1","2026-08-31 00:00:00","deposit","","currency","ZEUR","500.0","0.0","1400.0"')
    p = _export(tmp_path, rows)
    run = _invoke(mixed_schema_fixture, _tracking_argv(mixed_schema_fixture, "--simulated-fills", "--ledger-export", str(p)))
    assert run.exit_code == 0, run.stdout
    assert "rollover fees 0.0160 EUR" in run.stdout
    assert "rows with no fill behind them by construction: deposit 1" in run.stdout
    assert "fees on the matched rows" not in run.stdout  # nothing matched: a 0.0000 there would mean nothing


def test_the_matched_fee_figure_is_rendered_beside_the_rollover_line(tmp_path, mixed_schema_fixture, monkeypatch):
    # No synthetic journal carries a venue trade id, so the reconciliation is stood in for by what a
    # matched export produces; the render path under it is the real one.
    import cli.engine.command as command_module

    matched = {
        "status": "ok",
        "n_rows": 5,
        "matched": 3,
        "matched_fees_eur": 0.1594,
        "rollover_fees_eur": 0.016,
        "unmatched": [],
        "known": {"settled": 2},
        "ignored": {},
    }
    monkeypatch.setattr(command_module, "reconcile_ledger", lambda rows, fills: matched)
    p = _export(tmp_path, ['"L1","R1","2026-08-31 00:00:00","rollover","","currency","ZEUR","-0.12","0.12","900.0"'])
    run = _invoke(mixed_schema_fixture, _tracking_argv(mixed_schema_fixture, "--simulated-fills", "--ledger-export", str(p)))
    assert run.exit_code == 0, run.stdout
    assert "3 ledger trade or margin row(s) matched a journaled fill" in run.stdout
    assert "rollover fees 0.0160 EUR" in run.stdout
    assert "fees on the matched rows 0.1594 EUR" in run.stdout
    assert "rows with no fill behind them by construction: settled 2" in run.stdout
```

Replace, in `tests/test_engine_tracking.py`, this block:

```python
    assert "1" in cost["basis"] and "no rate proposed" in cost["basis"]  # the unmatched count, named
```

with:

```python
    assert "1" in cost["basis"] and "no rate proposed" in cost["basis"]  # the unmatched count, named
    assert "trade or margin row(s) matched no journaled fill" in cost["basis"]
```

- [ ] **Step 3: Run the file and watch the new cases fail**

Run: `uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider`
Expected: `9 failed, 77 passed, 3 skipped`. `test_a_no_fill_row_type_is_counted_as_known_never_matched` and `test_a_row_type_this_reader_has_not_met_is_counted_by_type` fail on `KeyError: 'known'`; `test_a_margin_row_matching_a_journaled_fill_reconciles_and_carries_its_fee_not_its_pnl` on `assert ('insufficient-data' == 'ok'`; `test_a_margin_row_matching_no_journaled_fill_FAILS_the_reconciliation` on `assert ('insufficient-data' == 'FAILED'`; `test_every_row_type_of_the_real_export_lands_in_exactly_one_place` on `assert (2 == 4)`, the margin rows unmatched; `test_a_rollover_charged_in_eurc_is_summed_at_par_beside_a_euro_one` on `assert 0.004 == 0.008 ± 8.0e-09`, the EURC row dropped; `test_the_rollover_figure_prints_at_four_decimals_and_the_no_fill_rows_are_named` on `'rollover fees 0.0160 EUR' in`; `test_the_matched_fee_figure_is_rendered_beside_the_rollover_line` on `'3 ledger trade or margin row(s) matched a journaled fill' in`; `test_a_failed_reconciliation_withdraws_the_proposed_rate_from_the_payload` on `'trade or margin row(s) matched no journaled fill' in`. `test_a_row_type_the_reader_has_not_met_is_named_in_the_report` passes on the old tree, since an unknown type is counted there today. The three skips are `_copy_slice`'s data gates, the journal mount or the refdata snapshot, whichever the checkout lacks.

- [ ] **Step 4: The widened match, the known types and the figures in `cli/engine/tracking.py`, the rendering in `cli/engine/command.py`, and the two pages**

Replace, in `cli/engine/tracking.py`, this block:

```python
class LedgerRow(NamedTuple):
    txid: str
    refid: str  # the venue trade id a `trade` row belongs to -- what `Fill.trade_id` carries
```

with:

```python
class LedgerRow(NamedTuple):
    txid: str
    # The venue trade id a `trade` or `margin` row belongs to -- what `Fill.trade_id` carries; a
    # `rollover` or `collateralconversion` row carries its position's OPENING trade id instead.
    refid: str
```

Replace, in `cli/engine/tracking.py`, this block:

```python
# Row types with no fill behind them BY CONSTRUCTION -- an allowlist, so an unknown type is reported rather than passed
# over (`margin` shares its trade's refid: counted, never matched), while failing on a deposit would fail every export.
_NO_FILL_LEDGER_TYPES = frozenset({"deposit", "withdrawal", "transfer"})
```

with:

```python
# The assets a fee is summed under as euro: the venue's two spellings, and EURC, which it charges a margin open's fee in
# after converting euro to it at par beside the row, the export's `collateralconversion` pair, so a EURC fee counts at par.
_EURO_FEE_ASSETS = frozenset(EUR_CODES) | {"EURC"}
# The row types a journaled fill is matched by: a spot fill writes `trade` rows and a margin open or close writes a
# `margin` row, each under the fill's own trade id and a margin fill with no `trade` row beside it.
_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})
# Row types with no fill behind them BY CONSTRUCTION -- an allowlist, so an unknown type is reported rather than passed
# over, while failing on a deposit would fail every export. `settled` is a hand settle's delivery pair, which the journal
# holds no row for; `collateralconversion` is the venue's own currency swap for a margin fee, keyed to the position's
# opening trade.
_NO_FILL_LEDGER_TYPES = frozenset({"deposit", "withdrawal", "transfer", "settled", "collateralconversion"})
```

Replace, in `cli/engine/tracking.py`, this block:

```python
def reconcile_ledger(rows: list[LedgerRow], fills: list[Fill]) -> dict:
    """An unmatched venue trade FAILS the comparison; an export with no trade row decides nothing; unknown types are only counted."""
    journaled = {f.trade_id for f in fills}
    matched = 0
    trade_rows = 0
    unmatched: list[str] = []
    ignored: dict[str, int] = {}
    rollover_fees_eur = 0.0
    for row in rows:
        # Rollover is why the function exists: the venue charges it against the POSITION, so a fill-based cost basis omits it.
        if row.type == "rollover":
            # `EUR_CODES`: the venue spells the euro two ways, and `== "EUR"` would drop every ZEUR row.
            if row.asset in EUR_CODES:
                rollover_fees_eur += row.fee
        elif row.type == "trade":
            trade_rows += 1
            if row.refid in journaled:
                # ROWS, not fills: one venue trade writes one ledger row per asset leg.
                matched += 1
            # Venue activity the journal does not know about is the one thing
            # this comparison exists to detect: it FAILS, and each id is named.
            elif row.refid not in unmatched:
                unmatched.append(row.refid)
        elif row.type not in _NO_FILL_LEDGER_TYPES:
            ignored[row.type] = ignored.get(row.type, 0) + 1
    return {
        # A third value, never "ok": with no trade row compared, "every venue trade matched" claims nothing.
        "status": "FAILED" if unmatched else "ok" if trade_rows else "insufficient-data",
        # Every row read: what separates an empty export from one carrying no trade rows.
        "n_rows": len(rows),
        "matched": matched,
        "rollover_fees_eur": rollover_fees_eur,
        "unmatched": unmatched,
        "ignored": ignored,
    }
```

with:

```python
def reconcile_ledger(rows: list[LedgerRow], fills: list[Fill]) -> dict:
    """An unmatched venue trade or margin row FAILS the comparison; an export with neither decides nothing; a known
    no-fill type is counted under `known`, an unknown type under `ignored`."""
    journaled = {f.trade_id for f in fills}
    matched = 0
    compared = 0
    unmatched: list[str] = []
    known: dict[str, int] = {}
    ignored: dict[str, int] = {}
    rollover_fees_eur = 0.0
    matched_fees_eur = 0.0
    for row in rows:
        # Rollover is why the function exists: the venue charges it against the POSITION, so a fill-based cost basis omits it.
        if row.type == "rollover":
            # `_EURO_FEE_ASSETS`: the venue spells the euro two ways and charges some fees in EURC, and `== "EUR"` would
            # drop the rest.
            if row.asset in _EURO_FEE_ASSETS:
                rollover_fees_eur += row.fee
        elif row.type in _MATCHED_LEDGER_TYPES:
            compared += 1
            if row.refid in journaled:
                # ROWS, not fills: one venue trade writes one ledger row per asset leg.
                matched += 1
                # The row's `fee` is the venue's own figure for the fill; its `amount` is a margin row's realized
                # PnL, a result and never a cost, so it is summed nowhere.
                if row.asset in _EURO_FEE_ASSETS:
                    matched_fees_eur += row.fee
            # Venue activity the journal does not know about is the one thing
            # this comparison exists to detect: it FAILS, and each id is named.
            elif row.refid not in unmatched:
                unmatched.append(row.refid)
        elif row.type in _NO_FILL_LEDGER_TYPES:
            known[row.type] = known.get(row.type, 0) + 1
        else:
            ignored[row.type] = ignored.get(row.type, 0) + 1
    return {
        # A third value, never "ok": with no trade or margin row compared, "every venue trade matched" claims nothing.
        "status": "FAILED" if unmatched else "ok" if compared else "insufficient-data",
        # Every row read: what separates an empty export from one carrying no trade or margin rows.
        "n_rows": len(rows),
        "matched": matched,
        "matched_fees_eur": matched_fees_eur,
        "rollover_fees_eur": rollover_fees_eur,
        "unmatched": unmatched,
        "known": known,
        "ignored": ignored,
    }
```

Replace, in `cli/engine/command.py`, this block:

```python
        "basis": f"{len(reconciliation['unmatched'])} ledger trade row(s) matched no journaled fill -- no rate "
        "proposed over a book the ledger could not reconcile",
```

with:

```python
        "basis": f"{len(reconciliation['unmatched'])} ledger trade or margin row(s) matched no journaled fill -- no rate "
        "proposed over a book the ledger could not reconcile",
```

Replace, in `cli/engine/command.py`, this block:

```python
            f"Ledger export: {reconciliation['status']} -- {reconciliation['n_rows']} row(s) read, of which "
            f"{reconciliation['matched']} ledger trade row(s) matched a journaled fill.",
        ]
        if payload["simulated"]:
            lines.append(
                "  SIMULATED FILLS were compared against a real export, so every ledger trade row below is unmatched "
                "by construction -- a modelled fill carries no venue trade id. Nothing in this block is a finding."
            )
        lines.append(
            f"  rollover fees {reconciliation['rollover_fees_eur']:,.2f} EUR -- charged against the POSITION rather "
            "than against a fill, so no execution record carries them and the blend above omits them."
        )
        if reconciliation["ignored"]:
            lines.append(
                "  row types this reader places nowhere: "
                + ", ".join(f"{kind} {count}" for kind, count in sorted(reconciliation["ignored"].items()))
                + " -- counted, never matched. A margin position writes rows sharing its trade's id, and what those "
                "mean is settled against a real export rather than guessed here."
            )
```

with:

```python
            f"Ledger export: {reconciliation['status']} -- {reconciliation['n_rows']} row(s) read, of which "
            f"{reconciliation['matched']} ledger trade or margin row(s) matched a journaled fill.",
        ]
        if payload["simulated"]:
            lines.append(
                "  SIMULATED FILLS were compared against a real export, so every ledger trade or margin row below is "
                "unmatched by construction -- a modelled fill carries no venue trade id. Nothing in this block is a finding."
            )
        # Four decimals: the export's own precision for a euro fee, so the figure can equal the hand read it is compared with.
        lines.append(
            f"  rollover fees {reconciliation['rollover_fees_eur']:,.4f} EUR -- charged against the POSITION rather "
            "than against a fill, so no execution record carries them and the blend above omits them."
        )
        if reconciliation["matched"]:
            lines.append(
                f"  fees on the matched rows {reconciliation['matched_fees_eur']:,.4f} EUR -- the venue's own figure for "
                "the window's journaled fills, a fee charged in EURC counted at par; the journal's fills carry each fee "
                "cent-rounded, and a margin row's amount is its realized PnL, summed nowhere."
            )
        if reconciliation["known"]:
            lines.append(
                "  rows with no fill behind them by construction: "
                + ", ".join(f"{kind} {count}" for kind, count in sorted(reconciliation["known"].items()))
                + " -- counted, never matched."
            )
        if reconciliation["ignored"]:
            lines.append(
                "  row types this reader places nowhere: "
                + ", ".join(f"{kind} {count}" for kind, count in sorted(reconciliation["ignored"].items()))
                + " -- counted, never matched; a type this reader has not met, to settle against the export that carries it."
            )
```

Replace, in `README.md`, this block:

```markdown
A `trade` row whose venue trade id matches no journaled fill **fails the reconciliation, not the run**```

with:

```markdown
A `trade` or `margin` row whose venue trade id matches no journaled fill **fails the reconciliation, not the run**```

Replace, in `README.md`, this block:

```markdown
**An export with no `trade` row reports `insufficient-data`, never `ok`** — nothing was compared, and a clean bill there would read exactly like an export whose every trade row matched.```

with:

```markdown
**An export with no `trade` or `margin` row reports `insufficient-data`, never `ok`** — nothing was compared, and a clean bill there would read exactly like an export whose every trade and margin row matched.```

Replace, in `README.md`, this block:

```markdown
Rollover rows are summed as a euro cost only when the row's asset is a euro (both venue spellings). Only `trade` rows are matched today, so any row type the reader places nowhere — `margin` above all, which a margin position writes carrying its trade's id — is **counted by type and printed**, and the block reports how many rows were read at all.```

with:

```markdown
Rollover rows are summed as a euro cost only when the row's asset is a euro (both venue spellings) or EURC, which the venue charges a fee in after converting euro to it at par. `trade` and `margin` rows are matched by their trade id — a margin open or close writes a `margin` row under the fill's own trade id and no `trade` row beside it — and a matched row's `fee`, in euro or in EURC at par, joins the `fees on the matched rows` figure, the venue's own total over the window's journaled fills, while a `margin` row's `amount`, the position's realized PnL, is summed nowhere. `settled` and `collateralconversion` rows have no fill behind them and are counted by type beside deposits; a row type the reader has not met is **counted by type and printed**, and the block reports how many rows were read at all. The `rollover fees` and matched-fee figures print at four decimals, the export's own precision for a euro fee.```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
   This is also the first real export the reader has ever seen, so it is where three shipped assumptions get settled. Record what you find for each, in the same entry:
```

with:

```markdown
   Three readings of the export go in the same entry:
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
   - **`rollover fees 0.00` against a nonzero hand read means the charge lives in `amount`, not `fee`.** The reader sums the `fee` column; which column a real rollover row carries the charge in was never verified (no count command: the column is the venue's export format, and no real export is in the tree), and this by-value comparison is exactly what catches it. A zero here is a finding about the reader, not about the window.
   - **Only `trade` rows are matched today.** (no count command: `reconcile_ledger` in `cli/engine/tracking.py` has one matching arm, for `trade`) Read the export's distinct `type` values (`cut -d, -f4 <the export>.csv | sort -u`, allowing for quoting). The `row types this reader places nowhere:` line names every type it consumed nothing from and how many — `margin` above all, which a margin position writes carrying the *same* `refid` as its trade. If `margin` appears, the match widens; that decision is yours to record here, not the reader's to guess.
```

with:

```markdown
   - **The `rollover fees` figure prints at four decimals, the export's precision for a euro fee.** The reader sums the `fee` column, where the charge lives (four `rollover` rows of 0.0040 read as 0.016 by hand and as 0.02 at the two-decimal print the reader used to have). A figure that differs from the hand read at four decimals is a finding about the reader, not about the window.
   - **`trade` and `margin` rows are matched by their trade id.** (no count command: `reconcile_ledger` in `cli/engine/tracking.py` holds the two matched types in `_MATCHED_LEDGER_TYPES`) A spot fill writes `trade` rows and a margin open or close writes a `margin` row under the fill's own trade id, with no `trade` row beside it. Read the export's distinct `type` values (`cut -d, -f4 <the export>.csv | sort -u`, allowing for quoting). `settled` rows, a hand settle's delivery pair the journal holds no row for, and `collateralconversion` rows, the venue's currency swap for a margin fee keyed to the position's opening trade, are counted on the `rows with no fill behind them by construction:` line beside deposits. The `row types this reader places nowhere:` line names a type the reader has not met, and a type appearing there is a decision to record here. The `fees on the matched rows` figure is the venue's own fee total over the window's journaled fills, a fee charged in EURC counted at par — the venue converts euro to EURC beside the row to charge a margin open's fee, and the journal reports that fill's fee in euro — printed at four decimals to read against the fills' cent-rounded fees in the ledger read; it is not added to the blend, and a `margin` row's `amount`, the realized PnL, is summed nowhere.
```

- [ ] **Step 5: Run the file and watch it pass**

Run: `uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider`
Expected: `86 passed, 3 skipped`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_config.py tests/test_engine_concordance.py tests/test_engine_gate_export_cache.py tests/test_engine_gate_cache.py tests/test_engine_stub_fidelity.py tests/test_engine_command.py tests/test_engine_gate_export.py tests/test_engine_feeders.py tests/test_engine_tracking.py tests/test_engine_execledger.py tests/test_ops_daily_soak.py tests/test_error_paths_are_logged.py tests/test_engine_metrics.py tests/test_engine_soak_command.py tests/test_ops_daily.py tests/test_engine_soak.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a data gate, none failed; `2132 passed, 7 skipped` when this plan was written.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. `mdformat` covers `README.md` and the runbook page.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/tracking.py cli/engine/command.py README.md infra/runbooks/engine-procedures.md tests/test_engine_tracking.py
git commit -m "fix(engine): the ledger reader matches margin rows, names the no-fill types and prints fees at the export's precision

Measured on 2026-09-26 against Kraken's real ledger export: the reader matched two trade rows, the
disposal's pair, and placed collateralconversion 4, margin 5, settled 2 nowhere; the window's two
margin opens and its margin close had no trade row at all, only a margin row under the fill's own
trade id, its amount the realized PnL and its fee the fill's fee; the rollover figure printed 0.02
against a hand read of 0.016, four rows of 0.0040. The match widens to margin rows by the same
refid rule, an unmatched one failing the reconciliation and a matched one counting as a comparison;
a matched row's fee, in euro or in EURC at par, joins matched_fees_eur, the venue's own figure over
the window's journaled fills, printed beside the rollover total while the blend keeps the journal's
cent-rounded fees, and a margin row's amount is summed nowhere; settled and collateralconversion join the known no-fill
types, counted under known and printed on their own line, ignored keeping the types the reader has
not met; both figures print at four decimals, the export's precision for a euro fee. The README row
and the runbook's third verify-by-outcome item say so. The adapter reports a EURC-charged fill's
commission in euro, so the journal's figure the venue's is read against already counts it at par.

Cases: a margin row matched by its trade id carrying its fee and not its positive PnL; an unmatched
margin row failing; every row type of the real export landing in exactly one place under the
sixteen-column header with its asset spellings, the EURC-charged open's fee counted, ignored empty; a deposit counted as known and an unmet type as ignored; four
rollover rows of 0.0040 printing 0.0160 with the deposit on the known line and no matched-fee line;
the matched-fee line rendered through the command with the reconciliation stood in; the basis text
naming margin rows on a failed reconciliation.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with eight probes, then record their verdicts by a message-only amend**

The reader's control narrows the matched types back to `trade`, so the margin cases fail. The first mutation sums a matched row's amount instead of its fee; the second drops the two new no-fill types; the third makes a margin row no comparison, so a margin-only export reads `insufficient-data`; the fourth drops EURC from the fee assets, so the EURC-charged open's fee falls out of the figure; the fifth drops the matched arm's asset gate, so the BTC leg's fee joins the euro figure; the sixth narrows the rollover arm's asset set to the euro codes, so the EURC rollover falls out of the figure. The command's control misspells the matched-fee line, which the render case pins, and its mutations put the rollover print back to two decimals and the basis text back to trade rows alone:

```bash
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py \
  --control 's/_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})/_MATCHED_LEDGER_TYPES = frozenset({"trade"})/' \
  --mutation 's/                    matched_fees_eur += row.fee/                    matched_fees_eur += row.amount/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py \
  --control 's/_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})/_MATCHED_LEDGER_TYPES = frozenset({"trade"})/' \
  --mutation 's/_NO_FILL_LEDGER_TYPES = frozenset({"deposit", "withdrawal", "transfer", "settled", "collateralconversion"})/_NO_FILL_LEDGER_TYPES = frozenset({"deposit", "withdrawal", "transfer"})/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py \
  --control 's/_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})/_MATCHED_LEDGER_TYPES = frozenset({"trade"})/' \
  --mutation 's/            compared += 1/            compared += row.type == "trade"/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py \
  --control 's/_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})/_MATCHED_LEDGER_TYPES = frozenset({"trade"})/' \
  --mutation 's/_EURO_FEE_ASSETS = frozenset(EUR_CODES) | {"EURC"}/_EURO_FEE_ASSETS = frozenset(EUR_CODES)/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py \
  --control 's/_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})/_MATCHED_LEDGER_TYPES = frozenset({"trade"})/' \
  --mutation 's/^                if row.asset in _EURO_FEE_ASSETS:$/                if True:/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py \
  --control 's/_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})/_MATCHED_LEDGER_TYPES = frozenset({"trade"})/' \
  --mutation 's/^            if row.asset in _EURO_FEE_ASSETS:$/            if row.asset in EUR_CODES:/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/command.py \
  --control 's/fees on the matched rows {/fees on matched rows {/' \
  --mutation 's/:,.4f} EUR -- charged/:,.2f} EUR -- charged/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/command.py \
  --control 's/fees on the matched rows {/fees on matched rows {/' \
  --mutation 's/ledger trade or margin row(s) matched no journaled fill/ledger trade row(s) matched no journaled fill/' \
  -- uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/tracking.py`, control the matched types
narrowed back to trade so the margin cases fail, the whole file as the probe: a matched row's
amount summed instead of its fee, KILLED, control proven; settled and collateralconversion dropped
from the no-fill types, KILLED, control proven; a margin row no longer a comparison, KILLED,
control proven; EURC dropped from the fee assets, KILLED, control proven; the matched arm's asset
gate dropped, KILLED, control proven; the rollover arm narrowed to the euro codes, KILLED, control
proven; over `cli/engine/command.py`, control the matched-fee line
misspelled: the rollover print back to two decimals, KILLED, control proven; the basis text back to
trade rows alone, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 3: The startup pass settles the intents a restart orphans, and a minted terminal marks an adopted row ambiguous

This task is the spec's third cluster (D13 to D16); struck, Tasks 1 and 2 stand as they are, and the restart finding keeps the registration this branch gave it — the third item on T0018's build-list line of 2026-09-26, drill G's reading — so the struck cluster stays owed work on that line rather than dropping out of the tree, and the closeout's re-true of the line names it as still open.

What this task decides, where the spec leaves it open:

- The sweep is one method, `_settle_pending_intents`, called from both exits of `_adopt_resting_orders`: the early return when nothing rests, with an empty cancelled set, and the end of the classification loop, with the intents whose order the pass sent a cancel for. It takes the `rows` and `finished` dicts the pass already holds, the `venue_orders` result, the `ledger_read` flag the pass sets false when its row read raised and `_kill_tripped`, which a withdrawal or an overfill in the sweeps above latches, spec D14's three-conjunct skip, and derives the intents it leaves `pending` from the rows' mirrored state and the cancelled set, spec D14's rule; the shapes that rule leaves `pending`, which of them a later startup settles, and the one shape outside the rule are the Global Constraints' startup-pass item.
- The first order's quantity is the largest `order.qty` among an intent's rows, read through `_ordered_qty`, and an intent whose rows carry no readable quantity is `revoked`, never `filled`.
- The minted-terminal arm keys on the flag and on `_RECONCILED_TERMINALS`, as the own-order path does, since the library's non-terminals carry the flag too; its log line moves from WARNING to CRITICAL and names the hand cancel on Kraken's open-orders page for an order still resting there; a refused cancel, `OrderCancelRejected`, takes an arm of its own before the Cache read, CRITICAL naming the hand cancel and returning no state, the own-order path's line given its adopted twin for the pass's and a trip's cancels alike; the `OrderPendingCancel` arm below them, the unreadable Cache, is unchanged.
- `_pending_plan_entry`, the new test helper, writes the plan entry through the real `append_plan_entry` at the same boundary `_submitted_row` files its rows, with an optional intent already terminal that the sweep must leave alone.
- `_submitted_row` gains a `qty` keyword, `None` for a row with no readable quantity, so the sweep's target rule has rows to differ on.

**Files:**
- Modify: `cli/engine/execledger.py` (`pending_plan_intents`, inserted before `open_submitted_rows`)
- Modify: `cli/engine/executor.py` (the `cli.engine.execledger` import block; `_adopt_resting_orders`, its docstring's last paragraph, the ledger read's `try` and its `except` arm, the `if not resting:` return, the `for order in resting:` loop's head and cancel branch, and the call after the loop; `_settle_pending_intents`, inserted before `_reconcile_adopted_rows`; `_venue_terminal_state`, its docstring's summary line, first paragraph and three-things paragraph, its reconciliation arm and the refused-cancel arm after it)
- Modify: `infra/runbooks/engine-procedures.md` (the `Three terminal outcomes` paragraph's `revoked` sentence; the `Read filled_qty` paragraph's last sentence; the pre-probe step's sentence on minted terminals, its `outcome="ambiguous"` sentence and its `Record the three numbers` sentence)
- Modify: `infra/runbooks/drills-order-path.md` (A1's Must fire, one bullet added after `Nothing else, on an ~83 s reboot`, and its operator action 3; G's Must fire, one bullet added after `Nothing, if the engine is back inside ~11 minutes`, its operator action 4, and one bullet added under its Record after `One more per fill racing the cancel`)
- Modify: `infra/runbooks/engine.md` (the error-logs runbook's step 2, two classes added before `Anything naming the executor`, the minted terminal's and the refused cancel's)
- Test: `tests/test_engine_executor.py` (`_submitted_row`'s signature and its row's `qty`; `test_a_terminal_the_engine_minted_leaves_the_adopted_row_open_where_the_venues_ack_closes_it` renamed and its true arm flipped; `test_an_external_cancel_rejection_is_recorded_without_closing_the_adopted_row`'s docstring re-trued; `_pending_plan_entry` and seventeen cases inserted before `_UnreadableOrderCache`)

**Interfaces:**
- Consumes: `_submitted_row`, `_resting_limit_order`, `_executor`, `_gate`, `_VenueOrders`, `_report`, `_intent_entry`, `_intent_outcome`, `_record`, `_kill_file`, `_executor_errors`, `_adopted_executor`, `_deliver_external_event`, `RecordingMetrics`, `set_executor_hooks`, `kill_trip_expected`, `append_plan_entry`, `GateVerdict`, `GateLevel`, `OrderStatus`, `OrderCanceled`, `OrderCancelRejected`, `ClientOrderId`, `StubClient`, `StubCache`, `OrderAccepted`, `_event`, `_boundary`, `executor_module`, `update_submitted_row`, `_TXID`, `NOW`, `logging`, `pytest`, `timedelta` from the test module's existing names; `_exec_records_in_window`, `_OPEN_ORDER_STATES` in the ledger; `update_plan_intent`, `_ordered_qty`, `_OVERFILL_TOLERANCE`, `_RECONCILED_TERMINALS` in the executor.
- Produces: `pending_plan_intents(journal_dir, now) -> list[tuple[datetime, str, int]]`; `ProbeExecutor._settle_pending_intents(now, rows, finished, cancelled, venue_orders, *, ledger_read)`; `_venue_terminal_state` returning `"ambiguous"` for a reconciled terminal and `None` with a CRITICAL for `OrderCancelRejected`; `_submitted_row(..., qty=0.001)` and `_pending_plan_entry(tmp_path, when, *, plan_id=..., n_intents=2, settled=None)` in the test module.

- [ ] **Step 1: Confirm Task 2 has landed and the ledger is at the spec's basis**

Run: `grep -c '_MATCHED_LEDGER_TYPES' cli/engine/tracking.py; grep -c 'pending_plan_intents' cli/engine/execledger.py`
Expected: `2` then `0`. A first count other than 2 means Task 2 is not on the branch; a second other than 0 means the accessor already exists; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_executor.py`**

Replace, in `tests/test_engine_executor.py`, this block:

```python
    index: int = 0,
    venue_order_id: str | None = None,
) -> dict:
```

with:

```python
    index: int = 0,
    venue_order_id: str | None = None,
    qty: float | None = 0.001,
) -> dict:
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
            "qty": 0.001,
```

with:

```python
            "qty": qty,
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    arrive. Nothing special-cases it -- the venue's order is still ACCEPTED after a refused cancel
    and no OPEN status is in the terminal map."""
```

with:

```python
    arrive. The row is not special-cased -- the venue's order is still ACCEPTED after a refused
    cancel and no OPEN status is in the terminal map -- and the CRITICAL the refusal logs, since the
    pass's sweep has already written the intent and no cancel is re-sent, is the cancelled opener's
    case below."""
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
        (False, "canceled", []),
        (True, "accepted", ["O-opener"]),
    ],
)
def test_a_terminal_the_engine_minted_leaves_the_adopted_row_open_where_the_venues_ack_closes_it(
    tmp_path, reconciled, expected_state, expected_open
):
    """A terminal the execution engine minted for itself is not a venue outcome, so it writes no venue
    outcome down -- the adopted surface's half of the property the own-order surface holds.

    The construction is the production one: the startup pass cancels an adopted non-reducer, the
    venue never answers, and past the in-flight retry budget the engine publishes the `OrderCanceled`
    itself. It is applied to the order before dispatch, so the Cache says CANCELED either way and
    only the flag can tell the two apart. Closing the row on it would put a venue claim in the ledger
    nobody made, and `_OPEN_ORDER_STATES` holds no terminal state, so the row would never re-attach.

    Read as a pair: the false arm is the true positive, and the `open_submitted_rows` reading IS what
    the next startup re-attaches from."""
```

with:

```python
        (False, "canceled", []),
        (True, "ambiguous", ["O-opener"]),
    ],
)
def test_a_terminal_the_engine_minted_marks_the_adopted_row_ambiguous_where_the_venues_ack_closes_it(
    tmp_path, reconciled, expected_state, expected_open
):
    """A terminal the execution engine minted for itself is not a venue outcome, so the row takes the
    active path's word for an outcome the venue never established, `ambiguous`, and no venue claim.

    The construction is the production one: the startup pass cancels an adopted opener, the venue
    never answers on the stream, and past the in-flight retry budget the
    engine publishes the `OrderCanceled` itself. It is applied to the order before dispatch, so the
    Cache says CANCELED either way and only the flag can tell the two apart. `canceled` on it would
    put a venue claim in the ledger nobody made; `accepted`, the old rule, claimed the order still
    rested when the venue had in fact cancelled it. `ambiguous` keeps the row open, so a startup
    inside the re-attach window re-attaches and settles it.

    Read as a pair: the false arm is the true positive, and the `open_submitted_rows` reading IS what
    a startup inside the re-attach window re-attaches from."""
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    assert [r.getMessage() for r in records] == (
        ["OrderCanceled for O-opener was reconciled, not received -- the venue never answered, so its row keeps the state it has"]
        if reconciled
        else []
    )
    assert metrics.external == ["matched"]
    assert not _kill_file(tmp_path).exists()


class _UnreadableOrderCache(StubCache):
```

with:

```python
    assert [(r.levelno, r.getMessage()) for r in records] == (
        [
            (
                logging.CRITICAL,
                "OrderCanceled for O-opener was reconciled, not received -- the venue never answered; its row reads "
                "ambiguous until a startup inside the re-attach window settles it: read Kraken's open orders, and cancel "
                "the order by hand there if it still rests",
            )
        ]
        if reconciled
        else []
    )
    assert metrics.external == ["matched"]
    assert not _kill_file(tmp_path).exists()


def _pending_plan_entry(tmp_path, when, *, plan_id="p-before-the-restart", n_intents=2, settled=None):
    """The plan entry a previous process journaled at pickup and never finished: every intent still
    `pending`, under the same boundary `_submitted_row` files that plan's rows; `settled` is one
    more intent, already terminal, that the sweep must leave as it is."""
    intents = [{"index": i, "intent": {}, "outcome": "pending", "reasons": [], "filled_qty": 0.0} for i in range(n_intents)]
    append_plan_entry(
        tmp_path / "journal",
        _boundary(when),
        {
            "plan_id": plan_id,
            "received_at": when.isoformat(),
            "disposition": "accepted",
            "reasons": [],
            "plan": {},
            "intents": intents + ([settled] if settled is not None else []),
        },
        verdict=GateVerdict(level=GateLevel.FULL, reasons=(), inputs={}),
        evaluated_at=when,
    )


def test_the_startup_pass_settles_the_intent_of_the_opener_it_cancels_and_the_ones_that_never_ran(tmp_path):
    """A rest-hold opener cancelled by the pass leaves its intent `pending` for good: the hold's timer
    died with the old process and nothing else writes an intent after a restart. The pass writes it
    `revoked` at its own boundary, and the plan's later intent, which no process will ever start,
    `refused` as not run."""
    earlier = NOW - timedelta(hours=4)
    done = {"index": 2, "intent": {}, "outcome": "filled", "reasons": [], "filled_qty": 0.001}
    _pending_plan_entry(tmp_path, earlier, settled=done)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert _intent_entry(tmp_path, 2, earlier) == done  # an intent already terminal is not the sweep's to rewrite
    first = _intent_entry(tmp_path, 0, earlier)
    assert (first["outcome"], first["reasons"], first["filled_qty"]) == (
        "revoked",
        ["the engine restarted while the intent was in flight"],
        0.0,
    )
    second = _intent_entry(tmp_path, 1, earlier)
    assert (second["outcome"], second["reasons"]) == ("refused", ["not run -- the engine restarted before it ran"])
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "accepted"  # the row still waits on the venue's answer


def test_the_startup_pass_leaves_the_intent_of_a_reducer_it_keeps_pending(tmp_path):
    """A kept reducer's order is live and its row is the record of it; the intent stays `pending`
    beside that open row, while the plan's later intent is still refused as never run."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert client.canceled == []
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"
    assert _intent_outcome(tmp_path, 1, earlier) == "refused"


def test_a_restart_with_nothing_resting_still_settles_the_windows_pending_intents(tmp_path):
    """The intent that was awaiting its first quote when the process stopped has no row at all, so no
    order-side event will ever reach it; the pass's early return on an empty Cache must not skip it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["reasons"]) == ("refused", ["not run -- the engine restarted before it ran"])


@pytest.mark.parametrize(
    "status, venue_filled, outcome, filled_qty",
    [
        (OrderStatus.CANCELED, "0", "revoked", 0.0),
        (OrderStatus.CANCELED, "0.0004", "revoked", 0.0004),
        (OrderStatus.FILLED, "0.001", "filled", 0.001),
    ],
)
def test_an_intent_whose_order_closed_while_down_is_settled_from_its_rows(tmp_path, status, venue_filled, outcome, filled_qty):
    """The row sweep reads the venue's own figure into the row first; the intent is then written
    from the rows -- `filled` once they carry the first order's quantity, `revoked` otherwise, a
    partial's fills carried either way."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    venue = _VenueOrders(_report(_TXID, status, filled_qty=venue_filled))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == (outcome, filled_qty)


def test_a_failed_venue_read_leaves_the_pending_intents_as_they_are(tmp_path):
    """With the venue unread the rows' fills were never compared -- a finished row's for a withdrawal,
    an open row's against its venue figure -- so an intent written from them would carry a figure
    nobody checked; the pending intents wait for the restart that reads again. The row here is
    already closed on its fill, the one shape the open-row rule alone would settle."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-opener", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(raises=RuntimeError("the venue read failed"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_failed_ledger_read_leaves_the_pending_intents_as_they_are(tmp_path, monkeypatch):
    """The pass's row read raised, so it holds no rows at all; run over none, the sweep would write
    every intent `refused` as never run, an intent that filled included. The rows were never read,
    the venue-read skip's own reason, and the pending intents wait for the restart that reads again."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)

    def _unreadable(journal_dir, now):
        raise OSError("the exec ledger could not be read")

    monkeypatch.setattr(executor_module, "open_submitted_rows", _unreadable)
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_an_intents_two_orders_closed_while_down_are_summed_against_the_first_orders_quantity(tmp_path):
    """A first order of 0.001 filled 0.0004 and was cancelled as crossing; its reprice, a remainder of
    0.0006, filled 0.0003 and closed while the engine was down. The target is the first order's
    quantity, the largest among the intent's rows, and 0.0007 against it is `revoked` with the sum
    carried -- read off the remainder row it would be `filled`."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-first", reduce_only=False, when=earlier, venue_order_id=_TXID)
    _submitted_row(tmp_path, "O-remainder", reduce_only=False, when=earlier, venue_order_id="OREMDR-AAAAA-BBBBBB", qty=0.0006)
    venue = _VenueOrders(
        _report(_TXID, OrderStatus.CANCELED, filled_qty="0.0004"),
        _report("OREMDR-AAAAA-BBBBBB", OrderStatus.CANCELED, filled_qty="0.0003", quantity="0.0006"),
    )
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == ("revoked", pytest.approx(0.0007))


def test_a_row_with_no_readable_quantity_settles_its_intent_revoked_never_filled(tmp_path):
    """A row whose `order.qty` is unreadable reads 0.0, and nothing filled against 0.0 must not read
    as complete: `revoked`, since such a row is not one to reason from."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID, qty=None)
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"


def test_an_order_resting_at_kraken_outside_the_cache_leaves_its_intent_pending(tmp_path):
    """The venue read returns the order still open and the Cache does not hold it: the pass can send
    it no cancel, so the order is live and its intent is not the sweep's to end."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "accepted"
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_row_the_venue_read_does_not_return_leaves_its_intent_pending(tmp_path):
    """The row's txid is in neither the Cache nor the venue's read, so the order may rest where no
    cancel of this process reaches it; the row reads `ambiguous` and the intent waits with it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    ex = _executor(
        tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=_VenueOrders()
    )

    ex.on_timer(NOW)

    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "ambiguous"
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_cancel_that_raised_leaves_its_intent_pending(tmp_path):
    """The pass's own cancel raised, so the opener may still rest: an intent is settled once a cancel
    went out, never on the attempt."""

    class _CancelRaises(StubClient):
        def cancel_order(self, client_order_id):
            raise RuntimeError("the cancel could not be sent")

    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = _CancelRaises(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_reducer_cancelled_on_a_latched_kill_has_its_intent_revoked(tmp_path):
    """At level NONE the pass cancels ledgered reducers too, and a cancelled reducer's intent is
    settled like an opener's: keeping is what leaves an intent `pending`, not the row's flag."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.NONE))

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"


def test_a_flagged_non_terminal_on_an_adopted_row_leaves_its_state_as_it_is(tmp_path):
    """The `reconciliation` flag rides on the library's non-terminals too, `OrderAccepted` among
    them, and only a minted TERMINAL says the venue never answered: a flagged acceptance on a kept
    reducer's row appends as evidence and moves nothing."""
    ex, client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderAccepted, client_order_id="O-attached", reconciliation=True))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "accepted" and [e["type"] for e in row["events"]] == ["OrderAccepted"]
    assert records == [] and metrics.external == ["matched"]


def test_a_failed_ledger_read_with_an_opener_resting_cancels_it_and_leaves_the_pending_intents_as_they_are(tmp_path, monkeypatch):
    """The restart every drill takes: an opener rests, and the row read raises. The pass cancels the
    opener as unmatched, and the sweep, run over no rows, would write its intent `refused` as never
    run -- it is skipped, and the intent stays `pending`."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)

    def _unreadable(journal_dir, now):
        raise OSError("the exec ledger could not be read")

    monkeypatch.setattr(executor_module, "open_submitted_rows", _unreadable)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_failed_venue_read_with_an_opener_resting_cancels_it_and_leaves_the_pending_intents_as_they_are(tmp_path):
    """The same restart with a second row whose txid the Cache lacks, so the pass reaches the venue,
    and the read raises: the opener is cancelled, and both intents stay `pending` -- the sweep run
    over the rows would write the cancelled opener's `revoked` from fills the venue never vouched
    for."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    _submitted_row(tmp_path, "O-gone", reduce_only=False, when=earlier, index=1, venue_order_id="OGONE0-AAAAA-BBBBBB")
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(raises=RuntimeError("the venue read failed"))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID] and venue.calls != []
    assert (_intent_outcome(tmp_path, 0, earlier), _intent_outcome(tmp_path, 1, earlier)) == ("pending", "pending")


def test_a_withdrawal_the_pass_latched_the_kill_switch_on_leaves_the_pending_intents_as_they_are(tmp_path, kill_trip_expected):
    """The venue reports less filled than the finished row carries, so the pass latches the kill
    switch and repairs nothing; the rows' figures are the ones the venue just refuted, and an intent
    written from them would read `filled` for a leg the venue says never filled."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-opener", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _kill_file(tmp_path).exists()  # the withdrawal tripped
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_cancel_the_venue_refused_on_an_adopted_order_logs_the_hand_cancel_and_leaves_the_row_accepted(tmp_path):
    """The pass cancelled the opener and wrote its intent `revoked` before the venue answered; the
    venue then refuses the cancel, so the order rests beside a terminal-looking intent and no cancel
    is re-sent. The own-order path's CRITICAL is the precedent: the line names the hand cancel, the
    row keeps its open state, and the intent stands as the pass wrote it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [_TXID] and _intent_outcome(tmp_path, 0, earlier) == "revoked"

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderCancelRejected, client_order_id=_TXID, reason="EService:Busy"))

    assert [(r.levelno, r.getMessage()) for r in records] == [
        (
            logging.CRITICAL,
            f"cancel of adopted order {_TXID} was REJECTED by the venue -- the order may still rest, and the cancel is "
            "not re-sent: cancel it by hand on Kraken's open-orders page",
        )
    ]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], [e["type"] for e in row["events"]]) == ("accepted", ["OrderAccepted", "OrderCancelRejected"])
    assert client.cache.order(ClientOrderId(_TXID)).status == OrderStatus.ACCEPTED
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"  # the pass's write stands; the line sends the operator to the page


class _UnreadableOrderCache(StubCache):
```

- [ ] **Step 3: Run the file and watch the new cases fail**

Run: `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`
Expected: `12 failed, 271 passed`. The true arm of `test_a_terminal_the_engine_minted_marks_the_adopted_row_ambiguous_where_the_venues_ack_closes_it` fails on `assert 'accepted' == 'ambiguous'`; `test_the_startup_pass_settles_the_intent_of_the_opener_it_cancels_and_the_ones_that_never_ran` on `assert ('pending', [], 0.0) == ('revoked', [...], 0.0)`; `test_the_startup_pass_leaves_the_intent_of_a_reducer_it_keeps_pending` on `assert 'pending' == 'refused'`; `test_a_restart_with_nothing_resting_still_settles_the_windows_pending_intents` on `assert ('pending', []) == ('refused', [...])`; the three arms of `test_an_intent_whose_order_closed_while_down_is_settled_from_its_rows` on `assert ('pending', 0.0) == ('revoked', 0.0)`, `('revoked', 0.0004)` and `('filled', 0.001)`; `test_an_intents_two_orders_closed_while_down_are_summed_against_the_first_orders_quantity` on `assert ('pending', 0.0) == ('revoked', 0.0007 ± 7.0e-10)`; `test_a_row_with_no_readable_quantity_settles_its_intent_revoked_never_filled` and `test_a_reducer_cancelled_on_a_latched_kill_has_its_intent_revoked` on `assert 'pending' == 'revoked'`; `test_a_flagged_non_terminal_on_an_adopted_row_leaves_its_state_as_it_is` on the WARNING record the old arm logs, `assert [<LogRecord ...>] == []`; `test_a_cancel_the_venue_refused_on_an_adopted_order_logs_the_hand_cancel_and_leaves_the_row_accepted` on `'pending' == 'revoked'`, the pass having written nothing. The false arm of the minted case, the three `leaves_its_intent_pending` cases and the five `leaves_the_pending_intents` cases pass on the old tree, which writes nothing and closes the row on the venue's own ack.

- [ ] **Step 4: The accessor in `cli/engine/execledger.py`, the sweep and the ambiguous arm in `cli/engine/executor.py`, and the three pages**

Replace, in `cli/engine/execledger.py`, this block:

```python
def open_submitted_rows(journal_dir: Path, now: datetime) -> list[tuple[datetime, dict]]:
```

with:

```python
def pending_plan_intents(journal_dir: Path, now: datetime) -> list[tuple[datetime, str, int]]:
    """Every (boundary, plan_id, index) whose intent still reads `pending`, over the same window as `open_submitted_rows`."""
    out: list[tuple[datetime, str, int]] = []
    for doc in _exec_records_in_window(journal_dir, now):
        boundary = datetime.fromisoformat(doc["cycle_ts"])
        for entry in doc.get("plans", []):
            out.extend((boundary, entry["plan_id"], i["index"]) for i in entry["intents"] if i["outcome"] == "pending")
    return out


def open_submitted_rows(journal_dir: Path, now: datetime) -> list[tuple[datetime, dict]]:
```

Replace, in `cli/engine/executor.py`, this block:

```python
from cli.engine.execledger import (
    append_plan_entry,
```

with:

```python
from cli.engine.execledger import (
    _OPEN_ORDER_STATES,
    append_plan_entry,
```

Replace, in `cli/engine/executor.py`, this block:

```python
    ledgered_plan_ids,
    open_submitted_rows,
    update_plan_intent,
```

with:

```python
    ledgered_plan_ids,
    open_submitted_rows,
    pending_plan_intents,
    update_plan_intent,
```

Replace, in `cli/engine/executor.py`, this block:

```python
        The classification population below is `orders_open`, but the row sweep is NOT: an order that
        filled, was canceled or expired while this process was down is not in the Cache at all -- the
        startup reconciliation reads open orders only -- so the pass cannot return early when nothing
        is resting: an idle startup can still owe row repairs.
        """
```

with:

```python
        The classification population below is `orders_open`, but the row sweep is NOT: an order that
        filled, was canceled or expired while this process was down is not in the Cache at all -- the
        startup reconciliation reads open orders only -- so the pass cannot return early when nothing
        is resting: an idle startup can still owe row repairs.

        LAST, the window's `pending` intents are settled (`_settle_pending_intents`): no process runs
        their plans, so each is written terminal from what its rows show, except one with an open row
        this pass sent no cancel for -- kept, or beyond its reach -- and none when either read above
        failed or a sweep above latched the kill switch.
        """
```

Replace, in `cli/engine/executor.py`, this block:

```python
        try:
            rows = {row["client_order_id"]: (boundary, row) for boundary, row in open_submitted_rows(self._journal_dir, now)}
```

with:

```python
        ledger_read = True
        try:
            rows = {row["client_order_id"]: (boundary, row) for boundary, row in open_submitted_rows(self._journal_dir, now)}
```

Replace, in `cli/engine/executor.py`, this block:

```python
            rows, finished = {}, {}
        venue_orders = self._read_venue_orders(rows, finished)
```

with:

```python
            rows, finished, ledger_read = {}, {}, False
        venue_orders = self._read_venue_orders(rows, finished)
```

Replace, in `cli/engine/executor.py`, this block:

```python
        if not resting:
            return  # nothing adopted -- and no gate read, so an idle startup stays the cheap path
```

with:

```python
        if not resting:
            self._settle_pending_intents(now, rows, finished, set(), venue_orders, ledger_read=ledger_read)
            return  # nothing adopted -- and no gate read, so an idle startup stays the cheap path
```

Replace, in `cli/engine/executor.py`, this block:

```python
        for order in resting:
            client_order_id = str(getattr(order, "client_order_id", ""))
            venue_order_id = _venue_order_id_of(order)
            attached = rows.get(client_order_id)
            if attached is None and venue_order_id is not None:
                attached = rows_by_venue.get(venue_order_id)
            if attached is not None:
                self._attach(attached, client_order_id, venue_order_id=venue_order_id)
            payload = attached[1].get("order") if attached is not None else None
            if isinstance(payload, dict) and payload.get("reduce_only") is True and not cancel_all:
                logger.warning("adopted resting order %s is a ledgered reducer -- left resting and re-attached", client_order_id)
                continue
```

with:

```python
        cancelled: set[tuple[str, int]] = set()
        for order in resting:
            client_order_id = str(getattr(order, "client_order_id", ""))
            venue_order_id = _venue_order_id_of(order)
            attached = rows.get(client_order_id)
            if attached is None and venue_order_id is not None:
                attached = rows_by_venue.get(venue_order_id)
            if attached is not None:
                self._attach(attached, client_order_id, venue_order_id=venue_order_id)
            payload = attached[1].get("order") if attached is not None else None
            if isinstance(payload, dict) and payload.get("reduce_only") is True and not cancel_all:
                logger.warning("adopted resting order %s is a ledgered reducer -- left resting and re-attached", client_order_id)
                continue
```

Replace, in `cli/engine/executor.py`, this block:

```python
            try:
                self._client.cancel_order(order.client_order_id)
            except Exception:
                logger.critical(
                    "cancel of adopted order %s raised -- it may still rest at the venue", client_order_id, exc_info=True
                )

    def _reconcile_adopted_rows(self, rows: dict, venue_orders: dict | None) -> None:
```

with:

```python
            try:
                self._client.cancel_order(order.client_order_id)
            except Exception:
                logger.critical(
                    "cancel of adopted order %s raised -- it may still rest at the venue", client_order_id, exc_info=True
                )
                continue
            if attached is not None:
                # The cancel went out, so the intent is the sweep's to settle; a fill racing the ack lands on the attached row.
                cancelled.add((attached[1]["plan_id"], attached[1]["intent_index"]))
        self._settle_pending_intents(now, rows, finished, cancelled, venue_orders, ledger_read=ledger_read)

    def _settle_pending_intents(
        self,
        now: datetime,
        rows: dict,
        finished: dict,
        cancelled: set,
        venue_orders: dict | None,
        *,
        ledger_read: bool,
    ) -> None:
        """A `pending` intent in the window belongs to a plan no process runs, so nothing else would
        ever end it. Each is written from what its rows show -- `filled` when they carry the first
        order's quantity, `revoked` when it ran and its order did not survive the restart, `refused`
        when it never ran -- except one with an open row this pass sent no cancel for: an order left
        resting, kept as a reducer or beyond the pass's reach, is still live and its row the live
        record. Skipped whole when either read failed or this pass latched the kill switch, since
        the rows' fills were then never compared, never read, or refuted by the venue, and are no
        figure to journal."""
        if venue_orders is None or not ledger_read or self._kill_tripped:
            return
        try:
            pending = pending_plan_intents(self._journal_dir, now)
        except Exception:
            logger.critical(
                "the plan entries could not be read at startup -- pending intents keep the state they have", exc_info=True
            )
            return
        filled: dict[tuple[str, int], float] = {}
        ordered: dict[tuple[str, int], float] = {}
        left: set[tuple[str, int]] = set()
        for _, row in [*rows.values(), *finished.values()]:
            key = (row["plan_id"], row["intent_index"])
            filled[key] = filled.get(key, 0.0) + float(row["filled_qty"])
            # The first order carries the intent's whole quantity and every later one a remainder, so
            # the largest of them is the target.
            ordered[key] = max(ordered.get(key, 0.0), _ordered_qty(row))
            if row.get("state") in _OPEN_ORDER_STATES and key not in cancelled:
                left.add(key)
        for boundary, plan_id, index in pending:
            key = (plan_id, index)
            if key in left:
                continue
            if key not in filled:
                outcome, reasons = "refused", ("not run -- the engine restarted before it ran",)
            elif ordered[key] > 0.0 and filled[key] >= ordered[key] - _OVERFILL_TOLERANCE:
                outcome, reasons = "filled", ()
            else:
                outcome, reasons = "revoked", ("the engine restarted while the intent was in flight",)
            try:
                update_plan_intent(
                    self._journal_dir, boundary, plan_id, index, outcome=outcome, reasons=reasons, filled_qty=filled.get(key, 0.0)
                )
            except Exception:
                logger.critical(
                    "intent %d of plan %s could not be journaled as %s at startup", index, plan_id, outcome, exc_info=True
                )

    def _reconcile_adopted_rows(self, rows: dict, venue_orders: dict | None) -> None:
```

Replace, in `cli/engine/executor.py`, this block:

```python
        An event the execution engine MINTED for itself writes none, and that is decided first,
        before the order is even read. Past its in-flight retry budget the engine stops waiting on an
        unanswered order and publishes that order's terminal itself, flagged `reconciliation`; the
        Cache's order has already taken it, so its status reads CANCELED or EXPIRED or REJECTED
        exactly as a venue answer would. It is not one. Nobody at the venue confirmed anything and
        the adopted order may still be resting, so a terminal state here would put a venue claim in
        the ledger on this engine's own authority -- and close a row that `_OPEN_ORDER_STATES` then
        never re-attaches, leaving a live order untracked for the life of the process. Left open, the
        event still appends as evidence, the entry stays in `_attached` for a fill that can still
        arrive, and the next startup's sweep settles the row against the order's own status. Keyed on
        the FLAG and never on the mechanism that set it, so a synthesis route nothing here enumerates
        is covered by construction; the cost when the flag sits on a venue-derived terminal is one
        row settled a restart later, which is the direction to be wrong in. `OrderFilled` never
        reaches this method -- the caller's fill branch returns above it -- so a reconciled fill
        keeps its row, its credit and its counter without anything here having to exempt it.
```

with:

```python
        An event the execution engine MINTED for itself writes `ambiguous`, and that is decided
        first, before the order is even read. Past its in-flight retry budget the engine stops
        waiting on an unanswered order and publishes that order's terminal itself, flagged
        `reconciliation`; the Cache's order has already taken it, so its status reads CANCELED or
        EXPIRED or REJECTED exactly as a venue answer would. It is not one. Nobody at the venue
        confirmed anything and the adopted order may still be resting, so a terminal state here
        would put a venue claim in the ledger on this engine's own authority -- and close a row that
        `_OPEN_ORDER_STATES` then never re-attaches, leaving a live order untracked for the life of
        the process. `ambiguous` claims nothing about the venue, is the active path's word for the
        same event, and keeps the row in the re-attach set: the event appends as evidence, the entry
        stays in `_attached` for a fill that can still arrive, and a startup inside the re-attach
        window settles the row against the order's own status; until then Kraken's open orders tell a
        cancel the venue executed unacknowledged from one that did not reach it, and an order still
        resting there is cancelled by hand on that page, since no cancel of this process reaches it
        -- the log line says both. Keyed on the flag and the terminal's name, as the own-order path
        is, and never on the mechanism that set the flag: a synthesis route nothing here enumerates
        is covered by construction, while the library's non-terminals carry the flag too and a
        flagged acceptance or cancel-side event writes nothing; the cost when the flag sits on a
        venue-derived terminal is one row settled a restart later, which is the direction to be
        wrong in. `OrderFilled` never reaches this method -- the caller's fill branch returns above
        it -- so a reconciled fill keeps its row, its credit and its counter without anything here
        having to exempt it.
```

Replace, in `cli/engine/executor.py`, this block:

```python
        if getattr(event, "reconciliation", False):
            logger.warning(
                "%s for %s was reconciled, not received -- the venue never answered, so its row keeps the state it has",
                type(event).__name__,
                getattr(event, "client_order_id", "?"),
            )
            return None
```

with:

```python
        if type(event).__name__ in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):
            logger.critical(
                "%s for %s was reconciled, not received -- the venue never answered; its row reads ambiguous until a "
                "startup inside the re-attach window settles it: read Kraken's open orders, and cancel the order by hand "
                "there if it still rests",
                type(event).__name__,
                getattr(event, "client_order_id", "?"),
            )
            return "ambiguous"
        if type(event).__name__ == "OrderCancelRejected":
            # The venue positively says the cancel did not take, so the order rests where the cancel is not re-sent and
            # after the pass's sweep has written its intent: the hand cancel is the operator's, the own-order path's line.
            logger.critical(
                "cancel of adopted order %s was REJECTED by the venue -- the order may still rest, and the cancel is not "
                "re-sent: cancel it by hand on Kraken's open-orders page",
                getattr(event, "client_order_id", "?"),
            )
            return None
```

Replace, in `cli/engine/executor.py`, this block:

```python
        """The row state a non-fill event writes, read off the VENUE's own order.
```

with:

```python
        """The row state a non-fill event writes: `ambiguous` for a terminal the engine minted, else
        read off the VENUE's own order, and none for a refused cancel, which logs CRITICAL.
```

Replace, in `cli/engine/executor.py`, this block:

```python
        Three further things mean the same thing here -- no terminal state, row untouched: a status
        outside the map (every OPEN one, so a refused cancel leaves the row pointing at a live
        order), an order the Cache does not hold, and a Cache that cannot be read at all. The last is
```

with:

```python
        Three things write nothing here -- no terminal state, row untouched: a status outside the
        map (every OPEN one), an order the Cache does not hold, and a Cache that cannot be read at
        all; a refused cancel writes nothing too, decided before the read and logged CRITICAL, since
        the venue positively says the order rests where the cancel is not re-sent and after the
        pass's sweep has written its intent. The unreadable Cache is
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
`revoked` — the kill file, a disarm or quote silence took it mid-rest, so it was revoked rather than held to its expiry, and the plan stops there.```

with:

```markdown
`revoked` — the kill file, a disarm, quote silence or an engine restart took it mid-rest, so it was revoked rather than held to its expiry, and the plan stops there. After a restart the startup pass writes it, with `the engine restarted while the intent was in flight` as the reason, and writes `not run -- the engine restarted before it ran` on the intents that never placed an order; the pass writes the intent before the venue answers its cancel, so a fill that lands afterwards — racing the cancel, or on an order the cancel did not reach — is on the order's row and not in the intent's `filled_qty`: read the row; a cancel the venue refuses leaves the order resting beside its `revoked` intent, the `cancel of adopted order … was REJECTED by the venue` line at CRITICAL says so, and the hand cancel on Kraken's open-orders page is yours. An intent still `pending` after the pass is one whose order the pass left resting — a reducer it kept, or an order it could not cancel or could not match — or the whole window's, when the pass's ledger or venue read failed or the pass latched the kill switch. A startup inside the re-attach window — the intent's boundary day and the next UTC day (`_exec_records_in_window` in `cli/engine/execledger.py` reads those two day directories, for the intent sweep and the row re-attach alike) — settles the intents a failed read left, a cancel that raised, a reconcile that raised, and an order resting outside the Cache once it is cancelled by hand or closes at the venue; an intent whose row recorded no txid, or whose txid no venue read returns, stays `pending` through later startups too. Past the window no startup reads the intent or its row: the window's entry records each intent still `pending`, and its row, beside Kraken's open and closed orders and the positions page read for that order.```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
On a `revoked` intent, `filled_qty` is the only field that answers whether anything reached the book.```

with:

```markdown
On a `revoked` intent, `filled_qty` is the only field that answers whether anything reached the book — on one the startup pass wrote, its rows' `filled_qty` summed, since a fill after the pass's write is on the cancelled order's row and not in the intent's figure.```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
The executor treats every one of those as an unknown venue outcome: the intent ends `ambiguous`, nothing is resubmitted, and the plan halts.```

with:

```markdown
The executor treats every one of those as an unknown venue outcome: the intent ends `ambiguous`, nothing is resubmitted, and the plan halts; on an order the startup pass adopted, the row reads `ambiguous` instead, until a startup inside the re-attach window settles it against the venue (the `Three terminal outcomes` paragraph below names the window and what the entry records past it), and its intent is the pass's, written before the venue answered, or left `pending` when the pass's ledger or venue read failed; read Kraken's open orders — an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled, which its entry in Kraken's closed orders, the positions page and the row's `filled_qty` tell apart.```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
`outcome="ambiguous"` is where a minted terminal lands.```

with:

```markdown
`outcome="ambiguous"` is where a minted terminal on the plan's own order lands; one on an order the startup pass adopted moves no outcome, and the `was reconciled, not received` lines count the mints on both paths, read the same way as the timeout count: `sudo docker logs --since 24h zcrypto-engine | grep -c 'was reconciled, not received'`.```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
Record the three numbers in this version's```

with:

```markdown
Record the numbers in this version's```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **A reboot long enough to page any of those is a finding about the reboot**```

with:

```markdown
- [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) (warning, `logs`), when the pass's cancel of the opener goes unacknowledged past the engine's in-flight budget and the engine mints the cancel's terminal for itself: the CRITICAL `was reconciled, not received` line pages it. Expected on that path and named in the entry; [`engine.md#zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) step 2 says what the line asks for, and it is not a disarm (no count command: whether the venue acknowledges is the venue's act, and the line is `_venue_terminal_state`'s in `cli/engine/executor.py`).
- **A reboot long enough to page any of those is a finding about the reboot**```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **Nothing, if the engine is back inside ~11 minutes.** All three of the rules D lists need longer, and G's stop is deliberately short.
```

with:

```markdown
- **Nothing, if the engine is back inside ~11 minutes.** All three of the rules D lists need longer, and G's stop is deliberately short.
- [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) (warning, `logs`), when the pass's cancel goes unacknowledged past the engine's in-flight budget and the engine mints the cancel's terminal for itself: the CRITICAL `was reconciled, not received` line pages it. Expected on that path and named in the entry; [`engine.md#zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) step 2 says what the line asks for, and it is not a disarm (no count command: whether the venue acknowledges is the venue's act, and the line is `_venue_terminal_state`'s in `cli/engine/executor.py`).
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
```

with:

```markdown
   - **`… was reconciled, not received -- the venue never answered; its row reads ambiguous …`**: the startup pass's cancel of an adopted order went unacknowledged past the engine's in-flight budget, so the engine minted the terminal itself; the row reads `ambiguous`, and its intent is written by the pass, unless the pass's ledger or venue read failed, when a startup inside the re-attach window writes it. Read Kraken's open orders: an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled — read its entry in Kraken's closed orders and the positions page, since the pass wrote the intent before the venue answered and a fill after that is on the order's row alone. A startup inside the re-attach window — the row's boundary day and the next UTC day — settles the row in both cases; past it no startup reads the row, so the restart's record — the attended window's entry, or the ops journal's — carries the row and its intent beside that closed-orders and positions reading. No disarm is owed for this line alone (no count command: the line is `_venue_terminal_state`'s in `cli/engine/executor.py`, the window `_exec_records_in_window`'s in `cli/engine/execledger.py`, and the venue's answer is the venue's act).
   - **`cancel of adopted order … was REJECTED by the venue`**: the venue refused the startup pass's, or a kill trip's, cancel of an order this process adopted, and the cancel is not re-sent; the order rests, and its intent, where the pass wrote it, reads `revoked` already. Cancel it by hand on Kraken's open-orders page, and read the row's `filled_qty` for what filled before that; no disarm is owed for this line alone (no count command: the line is `_venue_terminal_state`'s in `cli/engine/executor.py`, and the venue's refusal is the venue's act).
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
3. **The ledger**, with the probe window's ledger read: the order's row carries a terminal `state` and `filled_qty 0.0`, and no `fill` lines at all.```

with:

```markdown
3. **The ledger**, with the probe window's ledger read: the order's row carries `canceled`, or `ambiguous` where the venue's acknowledgement did not arrive and the engine minted the cancel's terminal for itself — step 4's read then decides it: an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart (drill G's record says how that reads) — `filled_qty 0.0`, and no `fill` lines at all; the intent reads `revoked`, written by the startup pass before the venue answered, unless the pass could not cancel or match the order, or its ledger or venue read failed, when it stays `pending` — which of those a later startup settles, inside what window, and what the entry records past it, the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) says.```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
4. **The ledger**, with the probe window's ledger read: the row's `events` for the cancel, and, if a fill raced it, a `fill` line beside it in the same row.```

with:

```markdown
4. **The ledger**, with the probe window's ledger read: the row's `events` for the cancel, and, if a fill raced it, a `fill` line beside it in the same row; the row `canceled`, or `ambiguous` where the engine minted the cancel's terminal for itself (the Record says how that reads, and an order still resting on Kraken's open-orders page is cancelled by hand there); the intent `revoked` with `the engine restarted while the intent was in flight`, written by the pass before the venue answered, so a fill that raced the cancel is on the row and not in the intent's `filled_qty`, and the plan's later intents `refused` as not run — an intent still `pending` after the pass is one whose order it could not cancel or match, or the whole window's when its ledger or venue read failed, and which of those a later startup settles, inside what window, and what the entry records past it, the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) says.```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **One more per fill racing the cancel**, keyed back the same way. Either reading proves a restart re-attaches a ledgered order by its txid, which is the question this reading exists to answer.
```

with:

```markdown
- **One more per fill racing the cancel**, keyed back the same way. Either reading proves a restart re-attaches a ledgered order by its txid, which is the question this reading exists to answer.
- **The row after the pass's cancel** reads `canceled` on the venue's own acknowledgement and `ambiguous` on one the engine minted for itself after its in-flight budget — the cancel executed at Kraken with its acknowledgement lost, or did not reach it, and Kraken's open orders are what tell those apart: an order still resting there is cancelled by hand on that page, one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart, and an `ambiguous` row is settled by a startup inside the re-attach window, which the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names with what the entry records past it. The intent reads `revoked` in both cases, written by the pass itself before the venue answered, so a fill after that is on the row alone — unless the pass's ledger or venue read failed, when it stays `pending` for a startup inside that window.
```

- [ ] **Step 5: Run the file and watch it pass**

Run: `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`
Expected: `283 passed`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_engine_execledger.py tests/test_engine_node.py tests/test_engine_metrics.py tests/test_engine_executor.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1933 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. `mdformat` covers the three runbook pages.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/execledger.py cli/engine/executor.py infra/runbooks/drills-order-path.md infra/runbooks/engine-procedures.md infra/runbooks/engine.md tests/test_engine_executor.py
git commit -m "fix(engine): the startup pass settles the intents a restart orphans, and a minted terminal marks an adopted row ambiguous

Measured on 2026-09-26, drill G: a rest-hold order rested through a stop and start, the pass
cancelled it, the venue never acknowledged on the stream, nautilus queried four times and minted
the OrderCanceled for itself, and the row stayed accepted and the intent pending through the hold's
expiry and the next boundary, since the hold's timer died with the old process and the pass wrote
nothing. The venue had cancelled the order. After classification the pass now settles every pending
intent of the two-day window, whose plans no process runs: filled when its rows' fills reach the
first order's quantity, revoked with the restart named when it ran and did not fill, refused as not
run when it has no row, the fills summed either way and written before the venue answers the
pass's cancel, so a fill after that lands on the row alone; an intent whose order the pass left
resting, a reducer it kept or an order it could neither cancel nor match, stays pending beside its
open row, and the sweep is skipped whole when the venue read or the ledger read failed or the pass
latched the kill switch, the rows' figures being the ones the venue refuted. A terminal
the engine minted for an adopted order now writes the row ambiguous, at CRITICAL, naming Kraken's
open orders as what tells a cancel the venue executed unacknowledged from one that did not reach it
and the hand cancel on that page for an order still resting; a flagged non-terminal writes nothing;
a cancel the venue refuses on an adopted order logs CRITICAL naming the hand cancel and writes
nothing, the intent standing as the pass left it; ambiguous keeps the row in the re-attach set, so
a startup inside the re-attach window settles it, and the pages name the window and what the
entry records past it. The runbook's
rest-hold vocabulary, its pre-probe step on minted terminals, drill A1's and G's Must fire, operator
and record clauses, and the error-logs runbook's classes for the two lines say so.

Cases: the cancelled opener's intent revoked and the plan's later intent refused, an intent already
terminal left alone; a kept reducer's intent left pending, and a reducer cancelled on a latched kill
revoked; a window with nothing resting settled; an order closed while down settled revoked, revoked
on a partial or filled from the venue's figure; two orders of one intent summed against the first
order's quantity; a row with no readable quantity revoked, never filled; an order the venue read
returned still open outside the Cache, a row the read did not return and a cancel that raised each
leaving its intent pending; a failed venue read and a failed ledger read leaving the intents as they
are, with nothing resting and with an opener the pass cancels; a withdrawal the pass latched the
kill switch on leaving them as they are; the minted terminal writing ambiguous with its CRITICAL
line where the venue's own ack writes canceled, a flagged acceptance leaving the row as it is, and a
cancel the venue refused after the pass wrote the intent logging the hand cancel with the row still
accepted.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with fourteen probes, then record their verdicts by a message-only amend**

The executor's control shortens the revoked reason, which the settling case pins. The mutations, in order: an intent whose order the pass left resting is settled; the sweep is skipped when nothing rests; the minted-terminal arm is disarmed, so the row reads the venue's status; the sweep runs on a failed ledger read; the sweep runs on a failed venue read; the sweep runs after the pass latched the kill switch; the loop's exit runs the sweep on a failed ledger read; the loop's exit runs it on a failed venue read; the refused-cancel arm is disarmed, so the venue's refusal logs nothing; a partial counts as filled; a row with no readable quantity counts as filled; the target is read off the smallest order; a flagged non-terminal writes ambiguous. The ledger's control misspells the pending word so the accessor lists nothing, and its mutation lists every intent, terminal ones included. Each `-k` selects 21 of the file's 283 cases:

```bash
K="settles_the_intent or reducer_it_keeps or nothing_resting or closed_while_down_is_settled or first_orders_quantity or no_readable_quantity or leaves_its_intent_pending or latched_kill_has or leaves_the_pending or minted_marks or flagged_non_terminal or venue_refused"
C='s/"the engine restarted while the intent was in flight"/"the engine restarted"/'
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/            if key in left:/            if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/            self._settle_pending_intents(now, rows, finished, set(), venue_orders, ledger_read=ledger_read)/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if type(event).__name__ in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):$/        if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if venue_orders is None or not ledger_read or self._kill_tripped:$/        if venue_orders is None or self._kill_tripped:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if venue_orders is None or not ledger_read or self._kill_tripped:$/        if not ledger_read or self._kill_tripped:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if venue_orders is None or not ledger_read or self._kill_tripped:$/        if venue_orders is None or not ledger_read:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/cancelled, venue_orders, ledger_read=ledger_read)/cancelled, venue_orders, ledger_read=True)/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/cancelled, venue_orders, ledger_read=ledger_read)/cancelled, venue_orders or {}, ledger_read=ledger_read)/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if type(event).__name__ == "OrderCancelRejected":$/        if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/filled\[key\] >= ordered\[key\] - _OVERFILL_TOLERANCE/filled[key] > 0.0/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/ordered\[key\] > 0.0 and //' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/ordered\[key\] = max(ordered.get(key, 0.0), _ordered_qty(row))/ordered[key] = min(ordered.get(key, float("inf")), _ordered_qty(row))/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if type(event).__name__ in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):$/        if getattr(event, "reconciliation", False):/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/execledger.py \
  --control 's/if i\["outcome"\] == "pending"/if i["outcome"] == "pendng"/' \
  --mutation 's/if i\["outcome"\] == "pending"/if True/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/executor.py`, control the revoked reason
shortened so the settling case fails, through
`-k "settles_the_intent or reducer_it_keeps or nothing_resting or closed_while_down_is_settled or first_orders_quantity or no_readable_quantity or leaves_its_intent_pending or latched_kill_has or leaves_the_pending or minted_marks or flagged_non_terminal or venue_refused"`:
an intent whose order the pass left resting settled, KILLED, control proven; the sweep skipped
when nothing rests, KILLED, control proven; the minted-terminal arm disarmed, KILLED, control
proven; the sweep run on a failed ledger read, KILLED, control proven; the sweep run on a failed
venue read, KILLED, control proven; the sweep run after the pass latched the kill switch, KILLED,
control proven; the loop's exit running the sweep on a failed ledger read, KILLED, control proven;
the loop's exit running it on a failed venue read, KILLED, control proven; the refused-cancel arm
disarmed, KILLED, control proven; a partial counted as filled, KILLED, control proven; a row with
no readable quantity counted as filled, KILLED, control proven; the target read off the smallest
order, KILLED, control proven; a flagged non-terminal writing ambiguous, KILLED, control proven;
over `cli/engine/execledger.py`, control the pending word misspelled: every intent listed, terminal
ones included, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

## Rollout (attended)

The change ships with T0213's engine rollout as one image, on the owner's word of 2026-09-26: the executor, the ledger and the reader ride the image that plan builds, through `.claude/skills/zcrypto-rollout-image/SKILL.md`'s engine section, inside an inter-cycle gap while flat, and this plan plans no converge of its own; T0213's findings carry that ride-along on this branch, so the engine half's author reads it there. If T0213's own plan is not converged within a week of this pair's merge, the pair takes its own rollout through the same skill. Both halves are registered where a reader evaluates them: at closeout the controller re-trues T0018's build-list line to `merged in PR #<N>, not deployed: rides T0213's engine image, or takes its own rollout by <merge date + 7 days>`, adds that date as an arm of T0018's `ripe_when` — `or <that date>, the pull request's image not yet on the engine, read from the engine row of docs/reference/fleet-pins.md` — and re-renders the index with `uv run python infra/scripts/topics-index.py`; the arm goes when the converge lands. The tracking-report change reaches the workstation at merge, where the report runs, and the runbook's §6 item 3 is read against it at the next attended window.

## Resolution

The branch delivers the build-list item registered on T0018 on 2026-09-26 from Rung 1's verdict and extended on this branch with drill G's finding: the reprice ladder, the ledger reader's margin rows, and the intents a restart orphans, one pull request on the live trade path. T0018 stays `partial`; its build-list line for the item is re-trued in the pull request's closeout, by the controller, to name the pull request and the deploy still owed (the Rollout's text), and to carry the restart finding as still open if the third cluster was struck; `docs/reference/change-index.md` maps the pull request to the topic. No topic is registered and none resolved; T0213's findings gain two lines on this branch, the kept reducer's intent and the ride-along, and T0214's one, the EURC-charged fee. What the pair leaves with a named home: the kept reducer's intent after a restart, T0213's engine half, on its findings line; cancel-on-stop and re-cancel-on-reconnect, T0018's other build-sequence items.

## Self-review

- Spec coverage: D1 and D2 are Task 1's counters, phase, detach and `_poll` arm, with the revoke, time-box, racing-fill, replayed-ack, completing-fill, half-book, silence-order and raise cases; D3 its fall-through with the alternating-crossings case, the sell close and the two rest-mode ladders, and its runbook clause in Task 1's page step; D4 a Global Constraint (no `_INTENT_KEYS` change); D5 the `order` payload keys the first case reads; D6 changes nothing and is a Global Constraint's silence. D7 and D12 are Task 2's matched set and the real-shape fixture; D8 its `matched_fees_eur` over `_EURO_FEE_ASSETS`, the PnL case and the fixture's EURC row; D9 its `known` tally; D10 the four-decimal cases; D11 changes nothing. D13 changes nothing; D14 is Task 3's sweep and its sixteen cases; D15 the flipped minted case and the flagged-acceptance case; D16 the page edits in Tasks 1, 2 and 3. The measured basis is the spec's and no task re-measures it.
- Placeholders: `PROBE_VERDICT` is the one token, replaced in each task's Step 10 and checked to be gone; `<model>` in the trailers is the executing model's own name, a Global Constraint.
- Names: every name a task consumes is listed under its Interfaces and exists in the test module or the source module at the step that uses it; the three new source names (`_reprice_at_touch`, `_time_box_with_nothing_resting`, `_settle_pending_intents`), the ledger accessor (`pending_plan_intents`) and the two test helpers (`_real_row`, `_pending_plan_entry`) are defined in the fence that introduces them, and `_submitted_row`'s `qty` keyword by the fence before the first case that passes it.
- Order: Task 2's and Task 3's first steps check the previous task's marker, and every failing and passing count was read with the tasks applied in this order.
