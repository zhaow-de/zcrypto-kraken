# Rung 1's execution findings: the reprice ladder, the ledger reader's margin rows and the intents a restart orphans — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A crossing post-only order is re-priced off a tick newer than the one it crossed on and, in `execute` mode, an exhausted maker ladder crosses through the bounded IOC before the intent ends `unfilled`; `tracking-report --ledger-export` matches `margin` rows by trade id, counts `settled` and `collateralconversion` as known no-fill types, reports the matched rows' fees beside the rollover total and prints both at four decimals; the startup pass settles every intent a restart orphans and marks a minted terminal on an adopted row `ambiguous`; the executor's re-read pass re-reads at the venue each row it minted terminal, after a socket cut's return or after a mint with the sockets up, and cancels what still rests; the executor reads the Cache through a handle taken at construction, so the adopt pass's cancel logs no borrow traceback; the gate's gauges are republished once a minute while no plan runs; the operator pages say so.

**Architecture:** Five tasks, one per finding, each a guard-proven commit on one branch. Task 1 adds two counters to `_ActiveIntent`, a phase `awaiting_reprice` with its own `_poll` arm, entered with the ended order detached, and the fall-through from `_reprice`'s exhaustion to `_fallback` in `cli/engine/executor.py`, records the priced quote inside each row's `order` payload, and gives the runbook's `Nothing retries itself` rule the clause that an `execute` intent's `unfilled` follows both ladders. Task 2 widens `reconcile_ledger`'s match in `cli/engine/tracking.py` to a `_MATCHED_LEDGER_TYPES` set, adds `known` and `matched_fees_eur` to its result, a fee summed under `_EURO_FEE_ASSETS`, the euro codes and EURC, and changes `cli/engine/command.py`'s rendering, with the README row and the runbook's §6 item 3 following. Task 3 adds `pending_plan_intents` to `cli/engine/execledger.py`, a `_settle_pending_intents` sweep the adopt pass runs after classification, which leaves `pending` every intent with an open row the pass did not cancel, and the `ambiguous` return of `_venue_terminal_state`'s reconciliation arm for a minted terminal, with the two drill and procedure pages and the error-logs runbook following. The third task is the spec's strikeable cluster: nothing in the first two depends on it. Task 4 subscribes `ShadowStrategy` to the client's socket-state stream and forwards it to the executor, which arms a re-read pass on each return of an endpoint it reported down and runs it on its next tick with nothing in flight, no intent live and no order of this process in flight in the Cache: the startup's row sweep (`_reconcile_adopted_rows`) over the open rows whose Cache order a minted terminal closed, the mint read off the order's history, with a venue read scoped to them and a bare-client cancel by txid (`cancel_venue_order`) for a report still open, the row written `canceled`; drill F2's procedure and the two runbooks follow. Task 4 is the third cluster's pass at one more moment and falls with Task 3 if that cluster is struck. Task 5 stamps every gate evaluation and refreshes the gate at the tick's tail once `_GATE_REFRESH` has passed, so a control file moved by hand reaches the gauges within a minute, the refresh publishing the five readings and not the heartbeat, which stays the boundary sink's; two idle-tick cases are re-bounded, the freeze test runs the refresh beside the raising sink, and every page sentence, tile, rule comment and code comment that named the old cadence or the six gauges freezing together is re-trued. Task 5 stands whatever is struck.

**Tech Stack:** Python 3.14 through `uv run`, pytest, the pinned `nautilus-trader` (`2.0.0rc6.dev20260921`) whose real order events and orders the executor tests drive, `infra/scripts/mutate-probe.sh` for the guard verdicts, `uv run pre-commit run -a` as the commit gate.

**Spec:** `docs/specs/00119-exec-findings-design.md`

## Global Constraints

- The ladder's constants are unchanged: `_MAX_REPRICES` 5, `_MAX_IOC_ATTEMPTS` 3, `_QUOTE_SILENCE` 30 s, `_TIME_BOX` 15 min, `_ACK_WAIT` 30 s (spec D2, D3). The waiting phase is `awaiting_reprice`; a reprice resubmits at once when `quote_seq > priced_seq` and waits otherwise (spec D1); the wait is bounded by `resting`'s three checks in `resting`'s order (spec D2); the sixth crossing calls `_fallback` in `execute` mode and ends `unfilled` with `reprice budget exhausted` in the rest modes, and the runbook's `Nothing retries itself` rule says an `execute` intent's `unfilled` follows both ladders (spec D3). Entering the wait clears `client_order_id` and `order`, so the ended order's later events take the detached path, and `_resubmit` ends an intent `filled` when less than one lot step remains, as does `_poll`'s `awaiting_reprice` arm before its three checks (spec D1); `on_quote`'s handler refuses with `filled` carried (spec D2).
- No schema changes: `_ROW_KEYS` and `EXEC_SCHEMA_VERSION` in `cli/engine/execledger.py` stay as they are, the priced quote living inside the row's `order` payload as `bid`, `ask`, `quote_seq` (spec D5); `_INTENT_KEYS` in `cli/engine/probeplan.py` is untouched (spec D4); no `_inc_order` label is added, since `tests/test_engine_metrics.py` pins `_EXEC_ORDER_OUTCOMES` against the executor's call sites.
- The reader's constants: `_MATCHED_LEDGER_TYPES = {"trade", "margin"}`; `_NO_FILL_LEDGER_TYPES` gains `settled` and `collateralconversion`; the result gains `known` and `matched_fees_eur`, a fee summed when its asset is in `_EURO_FEE_ASSETS`, the euro codes and `EURC`, for the rollover arm and the matched arm alike; `status` is `ok` once a trade or margin row was compared; the rollover and matched-fee lines print `:,.4f` (spec D7, D9, D10); `_LEDGER_COLUMNS` is unchanged, so the sixteen-column export still parses and the only-used-columns rule `tests/test_engine_tracking.py` pins holds.
- The startup pass's words: `filled`, `revoked` with `the engine restarted while the intent was in flight`, `refused` with `not run -- the engine restarted before it ran`, written at classification time, before the venue answers the pass's cancel, so a fill after the write is on the order's row and not in the intent's `filled_qty`; an intent with an open row the pass sent no cancel for stays `pending`, six shapes — a reducer it kept, a cancel that raised, an order the venue read returned still open outside the Cache, a row the read did not return, a row that recorded no txid, and a row whose reconcile raised on an order closed at the venue — and so does the whole window's when the venue read or the ledger read failed or the pass latched the kill switch, the sweep skipped whole; a later startup inside the re-attach window — `_exec_records_in_window`'s in `cli/engine/execledger.py`, the boundary's UTC day and the next, which the intent sweep and the row re-attach both read — settles the intents of a failed read, a cancel that raised, an order outside the Cache once the venue reports it closed, and a reconcile that raised, and settles neither a row with no txid nor one no venue read returns, which stay `pending`, nor, while the latch's cause stands, the intents a latched kill skipped; past the window no startup reads the intent or its row, and the pages say the window's entry records what stays `pending` beside Kraken's closed orders and positions read for the order; the one shape outside the rule, a Cache-resident order whose reconcile raised and which the loop then cancelled, is settled from the figure the raise left unrepaired (spec D14). A minted terminal on an adopted row writes `ambiguous`, records the event's flag in the row and logs at WARNING, naming the venue's report as what settles it, the re-read pass's on the next tick; a flagged non-terminal writes nothing (spec D15); the executor reads the Cache and the strategy id through handles taken at construction, never through the client inside a dispatch (spec D26); a cancel the venue refuses on an adopted order — the pass's or a trip's — logs at CRITICAL naming the hand cancel and writes nothing, the row still open and the intent as the pass left it (spec D14).
- The re-read pass's words: `_REREAD_ATTEMPTS` 3; the population is the open rows of the re-attach window whose Cache order is closed with an event of `_RECONCILED_TERMINALS` carrying the `reconciliation` flag in its history (`_minted_terminal`, over `events()` and not the last event, since the state machine applies a later fill to an order it holds minted-closed), and `_cached_order` answers nothing for such an order; the pass is armed on each `CONNECTED` of an endpoint held down and by a mint on either path while no endpoint is held down, a `DISCONNECTED` clearing the arm, and runs on the tick before the pickup, when `_reread_tries` is set and `_nothing_in_flight()` holds, `_active` None and the Cache's `orders_inflight` empty; a report still open is cancelled through `venue_cancel`, `cancel_venue_order` by default, whose return -- the `count` unread, `{"count": 0}` and `{"count": 1}` alike -- writes the row `canceled` with a `recancelled` event; a raising cancel and a read past the budget log CRITICAL and write nothing; no intent is written, no `_inc_order` label is added and `_settle_pending_intents` is not called, and no counter moves for the re-cancel, a closed report that completes the row counting `filled` through the startup's arm; `ShadowStrategy.on_start` calls `subscribe_socket_state()` beside the tick and `on_socket_state` is the fifth forwarder (spec D17 to D20).
- The refresh's words: `_GATE_REFRESH` 60 s; `_evaluate` stamps `_gate_evaluated_at`, which the constructor sets to its clock; `_refresh_gate` runs at the tick's tail and evaluates once the period has passed, with `heartbeat` False through `_publish` to the hook, so `_ExecGauges.update` moves the five readings and leaves `last_evaluation`, and journals nothing (spec D22 to D25).
- No string literal added under `cli/engine/` and no text added to `README.md`, `infra/runbooks/engine-procedures.md` or `infra/runbooks/drills-order-path.md` names a spec, a decision or a topic: `tests/test_internal_terms_not_operator_visible.py` walks them and runs in every task's consumer command.
- The five tasks land in order on one branch and merge together: the counts each task's failing and passing runs state assume the tasks before it have landed, and every task's first step from the second on checks the previous task's marker.
- A fence is the exact text at its indentation in the file: an indented fence is a fragment replaced in place, never a module of its own, and a `Replace, in <path>, this block:` instruction names the whole block it replaces, which occurs exactly once in the file at that step. A fence whose closing backticks sit on its last text line is a mid-line fragment with no trailing newline: the replacement lands inside that line, and neither the backticks nor the line end belongs to the text replaced.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean, from a file (`git commit --amend -F <file>`) and never from a double-quoted `-m` argument, inside which the shell runs each backticked name of the verdict text as a command substitution and the message no longer carries the text as written; the probe never runs while a pytest run is in flight in the same checkout.
- Every commit is green over the changed files' consumers, the union of `grep -rlE 'engine\.executor|engine import executor|engine\.execledger|engine import execledger' tests/test_*.py` for Tasks 1 and 3 and of `grep -rlE 'engine\.tracking|engine import tracking|engine\.command|engine import command' tests/test_*.py` for Task 2, each plus the internal-terms guard, and, since each task changes a page under `infra/runbooks/` or `README.md`, the tests that read those pages from the tree — the files `grep -rlE 'infra/runbooks|README\.md' tests/test_*.py` finds that read the pages, not those it finds naming the paths in a fixture, a string or a comment alone, and `tests/test_code_prose_citations.py`, which walks `infra/` for `*.md`: `tests/test_code_prose_citations.py`, `tests/test_count_list.py`, `tests/test_guidance_guard.py`, `tests/test_guidance_refs_resolve.py`, `tests/test_infra_alert_rules.py`, `tests/test_ops_daily.py`, `tests/test_runbook_internal_tokens.py`, `tests/test_runbook_triggers.py` and `tests/test_systemd_user_units.py` — all as they read when this plan was written; for Task 4 the executor union with the loopback venue's other consumers, `grep -rl kraken_loopback tests/test_*.py`, since it teaches that venue an answer; for Task 5 the executor union with Task 2's, since it touches `cli/engine/command.py`; never the full suite locally, which is CI's on every push.
- `uv run pre-commit run -a` runs the pre-commit stage alone and is clean before every commit; `guidance-guard` and `message-citations` run at commit-msg, on `git commit`: the runbook list items the three tasks write carry no universal word (every, never, always, only, any, cannot) outside code spans, and no commit message cites a `path:line`, a `path::symbol` or a topic.
- No step reaches a host or a venue; the executor tests drive the library's own events against a stub client, and the tracking tests a synthetic export.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. An existing file's lines are left as they are, except where a step replaces them.
- A commit message ends with these two trailers, `<model>` being the executing model's own name, written by the executor:

```
Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU
```

## File structure

- Modify `cli/engine/executor.py` — `on_socket_state`, `_reread_pass`, `_minted_closed`, `_recancel`, `_cache_lookup`, `_minted_terminal` and `cancel_venue_order`, with `_cached_order` withholding a minted-closed order and `_reconcile_adopted_rows` taking `recancel` (Task 4); `_gate_evaluated_at`, `_refresh_gate` and `_GATE_REFRESH` (Task 5). `_ActiveIntent` gains `quote_seq` and `priced_seq`; `on_quote` advances the count and resubmits from `awaiting_reprice`; `_place` records the quote and sets `priced_seq`; `_reprice` waits, with the ended order detached, or falls through to `_fallback`, its tail moving to `_reprice_at_touch`; `_resubmit` ends a remainder below one lot step `filled`; `on_quote`'s handler carries `filled`; `_poll` gains the `awaiting_reprice` arm, the completion test at its head, and `_time_box_with_nothing_resting` (Task 1). `_adopt_resting_orders` records whether the ledger read succeeded, collects the intents it cancelled and calls `_settle_pending_intents`, a new method; `_venue_terminal_state`'s reconciliation arm returns `ambiguous` for a minted terminal at WARNING, the two mint sites record the flag, and `__init__` takes the Cache and strategy-id handles every read goes through (Task 3); `_arm_reread_after_mint` and `on_socket_state`'s clearing arm (Task 4).
- Modify `tests/test_engine_executor.py` — the ladder test replaced by nineteen cases and six existing cases gaining the quote line the reprice waits for (Task 1); the pinned minted-terminal case flipped, the external cancel-rejection case's docstring re-trued, `_submitted_row` gaining a `qty` keyword, a `_pending_plan_entry` helper and eighteen cases on the sweep and the adopted row, `_pending_cancel_read_at_dispatch` and its case on the borrow, and the own-path mint's flag reading (Task 3); fourteen re-read cases and the two socket cases re-cut (Task 4).
- Modify `cli/engine/tracking.py` — `LedgerRow.refid`'s comment, `_EURO_FEE_ASSETS`, `_MATCHED_LEDGER_TYPES`, `_NO_FILL_LEDGER_TYPES`, `reconcile_ledger` (Task 2).
- Modify `cli/engine/command.py` — `_cost_over`'s basis text and `_render_tracking`'s ledger block (Task 2); `_ExecGauges`' docstring (Task 5).
- Modify `tests/test_engine_tracking.py` — two unit cases replaced by six, the real-shape fixture among them; one CLI case replaced by three (Task 2).
- Modify `README.md` — the `tracking-report` row's ledger sentences (Task 2).
- Modify `infra/runbooks/engine-procedures.md` — the `Nothing retries itself` rule (Task 1); §6 item 3's lead-in and two bullets (Task 2); the rest-hold terminal vocabulary, the `Read filled_qty` paragraph's last sentence and three sentences of the pre-probe step on minted terminals (Task 3); two clauses of that step (Task 4); the no-alert bullet on the external-events counter (Task 5).
- Modify `cli/engine/execledger.py` — `pending_plan_intents` (Task 3).
- Modify `infra/runbooks/drills-order-path.md` — A1's Must fire and step 3, G's Must fire, step 4 and Record (Task 3); F2's Must fire, operator actions 3 and 4, its property paragraph and Record (Task 4); the derivation rule on the gate's gauges and E's resting-plan precondition (Task 5).
- Modify `infra/runbooks/engine.md` — the error-logs runbook's step 2 gains the refused cancel's class (Task 3); the re-read pass's class, and the socket section's real-drop bullet (Task 4); the kill-tripped runbook's step 3 (Task 5).
- Modify `cli/engine/node.py` — `ShadowStrategy` subscribes to the socket-state stream in `on_start` and forwards it (Task 4).
- Modify `tests/kraken_loopback.py` — the `CancelOrder` answer and its form record (Task 4).
- Modify `tests/test_engine_node.py` — the recorder's fifth method, the stub's subscription, three cases (Task 4); the factory-shape and tick-forwarding cases' client (Task 3).
- Modify `tests/test_engine_stub_fidelity.py` — the `_VenueCancel` row (Task 4).
- Modify `tests/test_infra_alert_rules.py` — the `NOT_A_FAULT_SIGNAL` entry's comment on the external-events counter (Task 5).

## Review Focus

- A reprice firing off the tick it crossed on, the measured defect: the resubmission must wait for a newer stored tick and price off it; Task 1 owns `test_a_venue_cancel_off_the_priced_tick_waits_for_the_next_quote_before_repricing` and `test_alternating_crossings_place_one_order_per_tick_and_the_sixth_crossing_crosses_through_the_ioc`, and `test_a_sell_closes_six_accept_then_cancel_crossings_end_in_an_ioc_at_the_bid` pins the measured side.
- A reprice that always waits, losing a tick that already arrived, or a rest mode crossing through the IOC: Task 1 owns `test_a_tick_that_landed_before_the_cancel_reprices_on_the_cancel_itself`, `test_a_half_book_tick_while_a_reprice_waits_prices_nothing`, `test_a_half_book_tick_while_the_order_rests_is_not_the_newer_tick_a_reprice_waits_for` and the two `spent_by_rejections` cases.
- A waiting reprice outliving a kill file, a dead feed or the time-box, an intent parked with no order and no bound, the box firing an IOC off a quote the silence bound already condemned, or an intent a detached fill completed ended `revoked` by the timer: Task 1 owns the five `with_no_cancel` cases, the rest-cancel one in two arms, `test_quote_silence_outranks_the_time_box_while_a_reprice_waits` and `test_a_late_fill_completing_the_intent_while_the_reprice_waits_ends_it_filled_on_the_timer_too`.
- The ended order's events reaching the in-flight arms while the reprice waits, a row reopened by a racing fill or a crossing counted twice: Task 1 owns `test_a_fill_racing_the_venue_cancel_lands_detached_while_the_reprice_waits` and `test_a_replayed_cancel_ack_while_the_reprice_waits_counts_no_crossing`.
- A margin row's realized PnL summed as a cost, a hand settle's pair failing the window, or a fee charged in EURC dropped from the venue's figure: Task 2 owns `test_a_margin_row_matching_a_journaled_fill_reconciles_and_carries_its_fee_not_its_pnl` and `test_every_row_type_of_the_real_export_lands_in_exactly_one_place`.
- A minted terminal read as the venue's answer, a kept reducer's intent rewritten, an intent closed `revoked` while its order rests at Kraken with nothing naming the hand cancel, or fills nobody compared or read, or the venue refuted, journaled as an intent's: Task 3 owns `test_a_terminal_the_engine_minted_marks_the_adopted_row_ambiguous_where_the_venues_ack_closes_it`, `test_the_startup_pass_leaves_the_intent_of_a_reducer_it_keeps_pending`, the three `leaves_its_intent_pending` cases, `test_a_cancel_the_venue_refused_on_an_adopted_order_logs_the_hand_cancel_and_leaves_the_row_accepted` and the five `leaves_the_pending_intents` cases, two of them with an opener resting, the restart every drill takes. The borrow behind the adopt pass's traceback, a read through the client inside its own command's dispatch: Task 3 owns `test_the_pending_cancel_of_an_adopted_order_is_read_through_the_handle_taken_at_construction`, against a real engine, and `test_the_adopt_pass_cancel_of_a_matched_opener_reads_its_pending_cancel_through_the_handle_and_logs_no_traceback`; the mint's flag on the row, the minted case's events line and `test_a_cancel_ack_the_engine_minted_halts_where_the_venues_own_ack_falls_back`.
- An order a cut left resting at Kraken after the engine minted its cancel, the measured defect: a socket's return must arm the pass, the tick must read the venue for that row and cancel it by txid on a report still open, and the row must settle; Task 4 owns `test_a_reconnect_after_a_minted_cancel_re_cancels_the_order_still_resting_and_settles_its_row` and the adopted twin, `test_a_partial_fill_applied_after_the_mint_keeps_the_row_in_the_reread_pass_which_re_cancels_the_remainder` holds the mint read off the order's history under a later fill, and `test_cancel_venue_order_sends_the_txid_on_the_real_client_and_returns_on_count_1_and_count_0_alike` pins the bare client.
- A pass reading every open row, running beside an intent live or an order of this process in flight, arming on the connect's own `CONNECTED` or waiting for a second socket's event, retrying a failed read for good or giving up at once, or writing a row on a cancel that raised: Task 4 owns `test_a_reconnect_reads_the_venue_for_no_row_the_engine_did_not_mint_terminal`, `test_the_pass_waits_for_a_tick_with_nothing_of_this_process_in_flight`, `test_the_reread_pass_waits_while_a_startup_cancel_of_an_adopted_order_is_still_unanswered`, `test_each_socket_reported_down_arms_the_pass_on_its_own_return_and_the_connect_itself_arms_nothing`, `test_a_venue_read_failing_after_the_reconnect_is_tried_on_three_ticks_then_left_to_the_hand_or_a_restart` and `test_a_re_cancel_the_venue_refuses_leaves_the_row_and_names_the_hand_cancel`; a void the venue reported read as a mint would strand the startup's withdrawal check, and `test_a_withdrawn_fill_on_a_row_this_engine_closed_latches_the_kill_switch` holds it; the one counter the pass moves, `test_a_venue_report_filled_at_the_reconnect_settles_the_minted_row_filled_and_counts_it_as_a_startup_would`.
- A mint with the sockets up left to a startup, paging on the venue's ordinary answer, or a mint inside a cut read into the cut: Task 4 owns `test_a_minted_cancel_of_an_adopted_opener_with_the_sockets_up_is_settled_from_the_venue_on_the_next_tick`, `test_a_socket_reported_down_holds_the_re_read_a_mint_armed_until_a_socket_is_back` and `test_a_mint_while_a_socket_is_held_down_arms_nothing_and_the_sockets_return_does`.
- A gauge holding the boot's reading with no plan running, the measured defect, or a refresh on every tick where the idle path was contracted cheap: Task 5 owns `test_a_kill_file_removed_on_an_idle_engine_is_republished_within_the_refresh_period` and `test_an_idle_tick_reads_no_gate_inside_the_refresh_period_and_one_per_period_past_it`; the refresh stamping the heartbeat, so the staleness rule stops watching the boundary sink and its exec record: `test_a_raising_ledger_writer_freezes_the_heartbeat_while_the_idle_refresh_moves_the_readings_and_the_staleness_condition_goes_true` in `tests/test_engine_metrics.py`.
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
    """The measured side: a sell, accepted and then cancelled by the venue as crossing six times,
    each crossing answered by one tick, so each order is priced off a newer ask; the sixth crossing's
    IOC is bounded by the last tick's bid, the opposite touch on this side. The 2026-09-25 order was
    a spot disposal; this one is a margin close, so the IOC also carries the closer's reduce-only
    flag."""
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

Run: `uv run pytest tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_engine_execledger.py tests/test_engine_node.py tests/test_engine_metrics.py tests/test_engine_executor.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_count_list.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1932 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates, `ZCRYPTO_LIVE_VENUE_TESTS` unset.

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

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <that file>` — the Global Constraints' rule, never `--amend -m "…"`, inside which the shell runs each backticked name below as a command:

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

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` — Expected: `1`, the verdict naming the script.

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
                f"  fees on the matched rows {reconciliation['matched_fees_eur']:,.4f} EUR -- the venue's own figure "
                "over the journaled fills the export's rows matched, a fee charged in EURC counted at par; the journal's "
                "fills carry each fee cent-rounded, and a margin row's amount is its realized PnL, summed nowhere."
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
Rollover rows are summed as a euro cost only when the row's asset is a euro (both venue spellings) or EURC, which the venue charges a fee in after converting euro to it at par. `trade` and `margin` rows are matched by their trade id — a margin open or close writes a `margin` row under the fill's own trade id and no `trade` row beside it — and a matched row's `fee`, in euro or in EURC at par, joins the `fees on the matched rows` figure, the venue's own total over the journaled fills the export's rows matched — the window's total only when the export's `time` span covers the window, which the reader does not check — while a `margin` row's `amount`, the position's realized PnL, is summed nowhere. `settled` and `collateralconversion` rows have no fill behind them and are counted by type beside deposits; a row type the reader has not met is **counted by type and printed**, and the block reports how many rows were read at all. The `rollover fees` and matched-fee figures print at four decimals, the export's own precision for a euro fee.```

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
   - **`trade` and `margin` rows are matched by their trade id.** (no count command: `reconcile_ledger` in `cli/engine/tracking.py` holds the two matched types in `_MATCHED_LEDGER_TYPES`) A spot fill writes `trade` rows and a margin open or close writes a `margin` row under the fill's own trade id, with no `trade` row beside it. Read the export's distinct `type` values (`cut -d, -f4 <the export>.csv | sort -u`, allowing for quoting). `settled` rows, a hand settle's delivery pair the journal holds no row for, and `collateralconversion` rows, the venue's currency swap for a margin fee keyed to the position's opening trade, are counted on the `rows with no fill behind them by construction:` line beside deposits. The `row types this reader places nowhere:` line names a type the reader has not met, and a type appearing there is a decision to record here. The `fees on the matched rows` figure is the venue's own fee total over the journaled fills the export's rows matched — a journaled fill the export carries no row for adds nothing and is not reported, so read the export's first and last `time` against the window's `--since` and `--until` before reading the figure as the window's — a fee charged in EURC counted at par (the venue converts euro to EURC beside the row to charge a margin open's fee, and the journal reports that fill's fee in euro), printed at four decimals to read against the fills' cent-rounded fees in the ledger read; it is not added to the blend, and a `margin` row's `amount`, the realized PnL, is summed nowhere.
```

- [ ] **Step 5: Run the file and watch it pass**

Run: `uv run pytest tests/test_engine_tracking.py -q -p no:cacheprovider`
Expected: `86 passed, 3 skipped`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_config.py tests/test_engine_concordance.py tests/test_engine_gate_export_cache.py tests/test_engine_gate_cache.py tests/test_engine_stub_fidelity.py tests/test_engine_command.py tests/test_engine_gate_export.py tests/test_engine_feeders.py tests/test_engine_tracking.py tests/test_engine_execledger.py tests/test_ops_daily_soak.py tests/test_error_paths_are_logged.py tests/test_engine_metrics.py tests/test_engine_soak_command.py tests/test_ops_daily.py tests/test_engine_soak.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_count_list.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a data gate, none failed; `2150 passed, 7 skipped` when this plan was written.

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
the journaled fills the export's rows matched, printed beside the rollover total while the blend
keeps the journal's
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

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <that file>` — the Global Constraints' rule, never `--amend -m "…"`, inside which the shell runs each backticked name below as a command:

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

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` — Expected: `1`, the verdict naming the script.

---

### Task 3: The startup pass settles the intents a restart orphans, and a minted terminal marks an adopted row ambiguous

This task is the spec's third cluster (D13 to D16); struck, Tasks 1 and 2 stand as they are, Task 4 falls with it, since its pass is this task's sweep at one more moment, Task 5 stands, and the restart finding keeps the registration this branch gave it — the third item on T0018's build-list line of 2026-09-26, drill G's reading — so the struck cluster stays owed work on that line rather than dropping out of the tree, and the closeout's re-true of the line names it as still open.

What this task decides, where the spec leaves it open:

- The sweep is one method, `_settle_pending_intents`, called from both exits of `_adopt_resting_orders`: the early return when nothing rests, with an empty cancelled set, and the end of the classification loop, with the intents whose order the pass sent a cancel for. It takes the `rows` and `finished` dicts the pass already holds, the `venue_orders` result, the `ledger_read` flag the pass sets false when its row read raised and `_kill_tripped`, which a withdrawal or an overfill in the sweeps above latches, spec D14's three-conjunct skip, and derives the intents it leaves `pending` from the rows' mirrored state and the cancelled set, spec D14's rule; the shapes that rule leaves `pending`, which of them a later startup settles, and the one shape outside the rule are the Global Constraints' startup-pass item.
- The first order's quantity is the largest `order.qty` among an intent's rows, read through `_ordered_qty`, and an intent whose rows carry no readable quantity is `revoked`, never `filled`.
- The minted-terminal arm keys on the flag and on `_RECONCILED_TERMINALS`, as the own-order path does, since the library's non-terminals carry the flag too; its line stays a WARNING and says what is known — no venue answer reached this engine, the row reads `ambiguous` until the venue's own report settles it — since on this wheel the mint is how each adopt-pass cancel measured ended, five of five, Kraken having cancelled at the second asked (spec D15), and both mint sites record the event's `reconciliation` flag in the row's payload, so the ledger tells a mint from the venue's own ack once the row is settled; a refused cancel, `OrderCancelRejected`, takes an arm of its own before the Cache read, CRITICAL naming the hand cancel and returning no state, the own-order path's line given its adopted twin for the pass's and a trip's cancels alike; the `OrderPendingCancel` arm below them reads through the handle the constructor took, so the `RuntimeError: Already mutably borrowed` WARNING that each such cancel logged with a traceback goes, and the except arm stays for a read failing for any other reason.
- The Cache and the strategy id are taken once in `__init__`, `self._cache` and `self._strategy_id`, and every read in the module goes through them — eleven sites at the tree's basis, and Task 4's two new reads with them (spec D26): the borrow is the client's PyO3 cell, held by its own `cancel_order` or `submit_order` while the library dispatches the event that command publishes, not the Cache's, which a handle taken earlier reads. Two guards pin it: `_pending_cancel_read_at_dispatch`, a real `BacktestEngine` with an observer strategy holding the order and a canceller strategy, the executor's client, cancelling it from a tick, the observer's `OrderPendingCancel` handler recording that the client's `cache` raises, that the Cache reads PENDING_CANCEL, and that `_venue_terminal_state` answers none with no line — the construction that reaches the PyO3 borrow, which the tree's loopback venue (REST only) and its data-socket harness (a data client alone) cannot, neither driving a strategy's `cancel_order` through the library's dispatch; and a stub twin whose client refuses each attribute while its own `cancel_order` runs and dispatches the event inside it. The node tests' factory-shape case and the tick-forwarding case hand the factory a client that answers the two reads, since an unregistered strategy refuses its `cache` and the production factory runs inside `on_start`.
- `_pending_plan_entry`, the new test helper, writes the plan entry through the real `append_plan_entry` at the same boundary `_submitted_row` files its rows, with an optional intent already terminal that the sweep must leave alone.
- `_submitted_row` gains a `qty` keyword, `None` for a row with no readable quantity, so the sweep's target rule has rows to differ on.

**Files:**
- Modify: `cli/engine/execledger.py` (`pending_plan_intents`, inserted before `open_submitted_rows`)
- Modify: `cli/engine/executor.py` (the `cli.engine.execledger` import block; `_adopt_resting_orders`, its docstring's last paragraph, the ledger read's `try` and its `except` arm, the `if not resting:` return, the `for order in resting:` loop's head and cancel branch, and the call after the loop; `_settle_pending_intents`, inserted before `_reconcile_adopted_rows`; `_venue_terminal_state`, its docstring's summary line, first paragraph and three-things paragraph, its reconciliation arm and the refused-cancel arm after it; `__init__`'s handles and the eleven `self._client.cache` and `self._client.strategy_id` reads — the adopt pass's `orders_open`, `_cached_order`, the two `venue_state_from_cache` reads, `_place`'s positions and instrument reads, `_cancel_resting`'s `orders_open`, `_reconcile_terminal`'s positions, `_venue_terminal_state`'s order read, `_publish_fill`'s and `_realized_eur`'s positions; the two mint sites' payloads, in `_on_order_event`'s reconciled arm and `_on_external_event`)
- Modify: `infra/runbooks/engine-procedures.md` (the `Three terminal outcomes` paragraph's `revoked` sentence; the `Read filled_qty` paragraph's last sentence; the pre-probe step's sentence on minted terminals, its `outcome="ambiguous"` sentence and its `Record the three numbers` sentence)
- Modify: `infra/runbooks/drills-order-path.md` (A1's Must fire, one bullet added after `Nothing else, on an ~83 s reboot`, and its operator action 3; G's Must fire, one bullet added after `Nothing, if the engine is back inside ~11 minutes`, its operator action 4, and one bullet added under its Record after `One more per fill racing the cancel`)
- Modify: `infra/runbooks/engine.md` (the error-logs runbook's step 2, one class added before `Anything naming the executor`, the refused cancel's)
- Test: `tests/test_engine_executor.py` (`_submitted_row`'s signature and its row's `qty`; `test_a_terminal_the_engine_minted_leaves_the_adopted_row_open_where_the_venues_ack_closes_it` renamed and its true arm flipped, its events line carrying the flag; `test_an_external_cancel_rejection_is_recorded_without_closing_the_adopted_row`'s docstring re-trued; `_pending_plan_entry` and eighteen cases inserted before `_UnreadableOrderCache`, the stub twin the last; the `OrderPendingCancel` import and its `_EVENT_DEFAULTS` entry; `_cache_reads_at_dispatch`'s comment on the borrow; `_pending_cancel_read_at_dispatch` and its case after `test_the_cache_already_carries_the_fill_when_the_strategy_handler_sees_it`; `_time_boxed_cancel_answered_by`'s `flagged` reading and its two cases' expected dicts; `_UnreadableOrderCache`'s docstring and its case's)
- Test: `tests/test_engine_node.py` (`test_probe_executor_factory_shape`'s client and its handle assertion; `test_a_quote_for_another_instrument_does_not_disturb_the_running_intent`'s client)

**Interfaces:**
- Consumes: `_submitted_row`, `_resting_limit_order`, `_executor`, `_gate`, `_VenueOrders`, `_report`, `_intent_entry`, `_intent_outcome`, `_record`, `_kill_file`, `_executor_errors`, `_adopted_executor`, `_deliver_external_event`, `RecordingMetrics`, `set_executor_hooks`, `kill_trip_expected`, `append_plan_entry`, `GateVerdict`, `GateLevel`, `OrderStatus`, `OrderCanceled`, `OrderCancelRejected`, `ClientOrderId`, `StubClient`, `StubCache`, `OrderAccepted`, `_event`, `_boundary`, `executor_module`, `update_submitted_row`, `_TXID`, `NOW`, `logging`, `pytest`, `timedelta` from the test module's existing names; `_exec_records_in_window`, `_OPEN_ORDER_STATES` in the ledger; `update_plan_intent`, `_ordered_qty`, `_OVERFILL_TOLERANCE`, `_RECONCILED_TERMINALS` in the executor; `OrderPendingCancel`, `_real_instrument`, `_cache_reads_at_dispatch`'s engine imports (`BacktestEngine`, `AccountType`, `OmsType`, `Venue`, `Strategy`), `INSTRUMENT_IDS`, `InstrumentId`, `Money`, `Currency`, `QuoteTick`, `TraderId`, `OrderSide`, `_time_boxed_cancel_answered_by` in the test module; `types`, `node`, `ShadowStrategy`, `_config` in the node tests.
- Produces: `pending_plan_intents(journal_dir, now) -> list[tuple[datetime, str, int]]`; `ProbeExecutor._cache` and `._strategy_id`, the handles every Cache and strategy-id read goes through; `ProbeExecutor._settle_pending_intents(now, rows, finished, cancelled, venue_orders, *, ledger_read)`; `_venue_terminal_state` returning `"ambiguous"` for a reconciled terminal, at WARNING, and `None` with a CRITICAL for `OrderCancelRejected`; the row event key `reconciliation` on a minted terminal, both paths; `_submitted_row(..., qty=0.001)`, `_pending_plan_entry(tmp_path, when, *, plan_id=..., n_intents=2, settled=None)` and `_pending_cancel_read_at_dispatch(tmp_path) -> dict` in the test module.

- [ ] **Step 1: Confirm Task 2 has landed and the ledger is at the spec's basis**

Run: `grep -c '_MATCHED_LEDGER_TYPES' cli/engine/tracking.py; grep -c 'pending_plan_intents' cli/engine/execledger.py`
Expected: `2` then `0`. A first count other than 2 means Task 2 is not on the branch; a second other than 0 means the accessor already exists; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_executor.py` and `tests/test_engine_node.py`**

Replace, in `tests/test_engine_executor.py`, this block:

```python
    OrderFillVoided,
    OrderRejected,
```

with:

```python
    OrderFillVoided,
    OrderPendingCancel,
    OrderRejected,
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    OrderExpired: {"reconciliation": False},
    OrderRejected: {"account_id": _ACCOUNT_ID, "reason": "the venue said no", "reconciliation": False},
```

with:

```python
    OrderExpired: {"reconciliation": False},
    OrderPendingCancel: {"account_id": _ACCOUNT_ID, "reconciliation": False},
    OrderRejected: {"account_id": _ACCOUNT_ID, "reason": "the venue said no", "reconciliation": False},
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
                # The event a command emits itself -- `OrderInitialized` at submit, `OrderPendingCancel`
                # at cancel -- is dispatched while the Cache is still mutably borrowed for the write
                # that produced it, and a read there raises `Already mutably borrowed`. Only the
                # venue's own answers are read here.
                return
```

with:

```python
                # The event a command emits itself -- `OrderInitialized` at submit, `OrderPendingCancel`
                # at cancel -- is dispatched while this strategy's own command still runs, so `self.cache`
                # raises `Already mutably borrowed` there: the strategy's PyO3 cell is what the command
                # holds, not the Cache (`_pending_cancel_read_at_dispatch` reads it through a handle).
                # Only the venue's own answers are read here.
                return
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    assert canceled["in_orders_open"] == []  # a settled order has already left the open index


def test_an_acceptance_then_a_full_fill_closes_the_intent_and_the_next_one_starts(tmp_path):
```

with:

```python
    assert canceled["in_orders_open"] == []  # a settled order has already left the open index


def _pending_cancel_read_at_dispatch(tmp_path) -> dict:
    """Run the adopt pass's cancel through a real engine: an observer strategy holds a resting order
    under its own id, as `node.py`'s external order observer holds an adopted one, and a second
    strategy, the executor's client, cancels it from a tick. The `OrderPendingCancel` that
    `cancel_order` publishes reaches the observer's handler while the client's own PyO3 cell is still
    held by that command -- the borrow the production traceback showed under `self._client.cache` --
    and a REAL engine is the only construction that reaches it. The executor is built inside the
    observer's `on_start`, where the client is not borrowed, as the node's factory builds it.
    Recorded, never asserted here: the library swallows a raising handler."""
    from nautilus_trader.backtest import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.model import AccountType, OmsType, StrategyId, Venue
    from nautilus_trader.trading import Strategy, StrategyConfig

    venue = Venue("KRAKEN")
    instrument_id = InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"])
    instrument = _real_instrument("BTC/EUR")
    readings: dict = {}

    def _config(tag):
        return StrategyConfig(strategy_id=StrategyId(f"PROBE-{tag}"), order_id_tag=tag)

    class _Canceller(Strategy):
        def __new__(cls):
            return super().__new__(cls, _config("002"))

        def __init__(self):
            super().__init__(config=_config("002"))
            self.target = None
            self.ticks = 0

        def on_start(self):
            self.subscribe_quotes(instrument_id)

        def on_quote(self, tick):
            self.ticks += 1
            if self.ticks == 3 and self.target is not None:
                self.cancel_order(self.target)

    class _Observer(Strategy):
        def __new__(cls, canceller):
            return super().__new__(cls, _config("001"))

        def __init__(self, canceller):
            super().__init__(config=_config("001"))
            self.canceller = canceller
            self.executor = None

        def on_start(self):
            self.executor = _executor(tmp_path, client=self.canceller)
            self.subscribe_quotes(instrument_id)
            order = self.order_factory.limit(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty(0.001),
                price=instrument.make_price(1000.0),  # far below: it rests untouched
            )
            self.submit_order(order)
            self.canceller.target = order.client_order_id

        def on_order_event(self, event):
            if type(event).__name__ != "OrderPendingCancel":
                return
            try:
                self.canceller.cache
                readings["client_cache"] = "readable"
            except RuntimeError as exc:
                readings["client_cache"] = str(exc)
            with _executor_errors(level=logging.WARNING) as records:
                readings["terminal_state"] = self.executor._venue_terminal_state(event)
            readings["warnings"] = [r.getMessage() for r in records]
            readings["status"] = self.cache.order(event.client_order_id).status

    canceller = _Canceller()
    engine = BacktestEngine(config=BacktestEngineConfig(trader_id=TraderId("PROBE-000")))
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(100_000, Currency.from_str("EUR")), Money(10, Currency.from_str("BTC"))],
    )
    engine.add_instrument(instrument)
    engine.add_strategy(_Observer(canceller))
    engine.add_strategy(canceller)
    engine.add_data(
        [
            QuoteTick(
                instrument_id,
                instrument.make_price(bid),
                instrument.make_price(bid + 1.0),
                instrument.make_qty(1.0),
                instrument.make_qty(1.0),
                ts,
                ts,
            )
            for ts, bid in ((1, 30001.0), (2_000_000_000, 29998.0), (3_000_000_000, 29998.0), (4_000_000_000, 29998.0))
        ]
    )
    try:
        engine.run()
    finally:
        engine.dispose()
    return readings


def test_the_pending_cancel_of_an_adopted_order_is_read_through_the_handle_taken_at_construction(tmp_path):
    """The adopt pass's cancel of a matched adopted order dispatches `OrderPendingCancel` inside the
    client's own `cancel_order`, and the read `_venue_terminal_state` took there answered nothing but
    `RuntimeError: Already mutably borrowed` -- measured on 2026-09-26, drills G and A1, a traceback
    WARNING on each such cancel. The borrow is the client's, not the Cache's: the first reading pins
    that the construction reaches it, the second that the Cache is free and a handle not held by the
    command reads PENDING_CANCEL, and the third that the executor reads through the handle it took
    at construction, answers no state, and logs nothing. A wheel that moved the borrow onto the
    Cache turns the second reading red rather than surfacing as a `PanicException` that no
    `except Exception` catches."""
    readings = _pending_cancel_read_at_dispatch(tmp_path)

    assert readings["client_cache"] == "Already mutably borrowed"
    assert readings["status"] == OrderStatus.PENDING_CANCEL
    assert (readings["terminal_state"], readings["warnings"]) == (None, [])


def test_an_acceptance_then_a_full_fill_closes_the_intent_and_the_next_one_starts(tmp_path):
```

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
    cancel and no OPEN status is in the terminal map -- and the CRITICAL the refusal logs here too,
    unasserted, is pinned by the cancelled opener's case below."""
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
    inside the re-attach window re-attaches and settles it. The line is a WARNING: on this wheel the
    mint is how each adopt-pass cancel measured ended, the venue having cancelled at the second asked,
    and the row's event records the flag so the ledger can tell the mint once the row is settled.

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
                logging.WARNING,
                "OrderCanceled for O-opener was reconciled, not received -- no venue answer reached this engine; its row "
                "reads ambiguous until the venue's own report settles it",
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


def test_the_adopt_pass_cancel_of_a_matched_opener_reads_its_pending_cancel_through_the_handle_and_logs_no_traceback(
    tmp_path,
):
    """The stub twin of the real-engine reading: the client refuses each attribute read while its own
    `cancel_order` runs and dispatches the `OrderPendingCancel` inside it, as the library does. The
    row keeps `accepted` with the event appended, the pass's own line is the one WARNING, and the
    client's refusal is not reached: the read went through the handle taken at construction."""

    class _HeldByItsOwnCancel(StubClient):
        def __init__(self, cache):
            self._held = False
            super().__init__(cache)
            self.executor = None

        @property
        def cache(self):
            if self._held:
                raise RuntimeError("Already mutably borrowed")
            return self._cache

        @cache.setter
        def cache(self, value):
            self._cache = value

        @property
        def strategy_id(self):
            if self._held:
                raise RuntimeError("Already mutably borrowed")
            return self._strategy_id

        @strategy_id.setter
        def strategy_id(self, value):
            self._strategy_id = value

        def cancel_order(self, client_order_id):
            super().cancel_order(client_order_id)
            self._held = True
            try:
                event = _event(OrderPendingCancel, client_order_id=str(client_order_id))
                self._cache.order(client_order_id).apply(event)
                self.executor.on_external_order_event(event)
            finally:
                self._held = False

    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = _HeldByItsOwnCancel(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    client.executor = ex

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert client.cache.order(ClientOrderId(_TXID)).status == OrderStatus.PENDING_CANCEL  # applied inside the cancel
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (logging.WARNING, f"canceling adopted resting order {_TXID} -- the ledger does not carry it as a resting reducer")
    ]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], [e["type"] for e in row["events"]]) == ("accepted", ["OrderAccepted", "OrderPendingCancel"])


class _UnreadableOrderCache(StubCache):
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    assert row["state"] == expected_state
    assert row["events"] == [{"type": "OrderCanceled", "at": NOW.isoformat()}]  # evidence, either way
    assert ex._attached["O-opener"][1]["state"] == expected_state  # the mirror stays with the row
```

with:

```python
    assert row["state"] == expected_state
    assert row["events"] == [  # evidence either way, the flag recorded where the engine minted it
        {"type": "OrderCanceled", "at": NOW.isoformat(), **({"reconciliation": True} if reconciled else {})}
    ]
    assert ex._attached["O-opener"][1]["state"] == expected_state  # the mirror stays with the row
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    """A Cache whose `order()` refuses the way the real one does from INSIDE an order-event handler:
    `RuntimeError("Already mutably borrowed")`, because the Cache is still mutably borrowed for the
    write that produced the event -- which this process's own cancel command generates, from the
    adopt pass and from a trip. Switchable, because the startup pass reads the same accessor and the
    row has to attach against a readable Cache first."""
```

with:

```python
    """A Cache whose `order()` refuses, with the text the client's `cache` getter raised inside its own
    command's dispatch before the executor read through a handle taken at construction -- raised here
    by the Cache itself, so the except arm for a read failing for any reason has a case. Switchable,
    because the startup pass reads the same accessor and the row has to attach against a readable
    Cache first."""
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    The dominant source of a terminal ack on this path is a cancel this very process sent, and a read
    taken inside that handler finds the Cache still mutably borrowed for the write that produced it.
    Letting it escape would abandon the whole handler, and with it the forensic event payload, to
    decide a state the event never carried -- so the event still appends, the entry stays attached,
    and the row keeps the state it has. Read as a pair: without the readable arm an unconditional
    `None` would pass, and without the raising arm a narrowed `except` is invisible."""
```

with:

```python
    No read here raises in production, since the executor reads through the handle taken at
    construction -- the borrow was the client's, inside its own command's dispatch, never the
    Cache's -- so this is the arm for a read failing for any other reason. Letting it escape would
    abandon the whole handler, and with it the forensic event payload, to decide a state the event
    never carried -- so the event still appends, the entry stays attached, and the row keeps the
    state it has. Read as a pair: without the readable arm an unconditional `None` would pass, and
    without the raising arm a narrowed `except` is invisible."""
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
        "next_intent": _intent_outcome(tmp_path, 1),
    }
```

with:

```python
        "next_intent": _intent_outcome(tmp_path, 1),
        "flagged": _record(tmp_path)["submitted"][0]["events"][-1].get("reconciliation"),
    }
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    assert venue == {"submissions": 2, "row_state": "canceled", "intent": "pending", "next_intent": "pending"}
    # No IOC, the row stays OPEN for re-attach because the order may still rest, and the ETH intent
    # never runs: the venue state that authorized it is no longer known.
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused"}
```

with:

```python
    assert venue == {"submissions": 2, "row_state": "canceled", "intent": "pending", "next_intent": "pending", "flagged": None}
    # No IOC, the row stays OPEN for re-attach because the order may still rest, and the ETH intent
    # never runs: the venue state that authorized it is no longer known. The row's event carries the flag.
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused", "flagged": True}
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    assert venue == {"submissions": 1, "row_state": "rejected", "intent": "rejected", "next_intent": "pending"}
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused"}
```

with:

```python
    assert venue == {"submissions": 1, "row_state": "rejected", "intent": "rejected", "next_intent": "pending", "flagged": None}
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused", "flagged": True}
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    config = _config(tmp_path, exec_armed=True)
    client = object()
    executor = node._probe_executor_factory(config)(client)
    assert isinstance(executor, ProbeExecutor)
    assert executor._client is client
```

with:

```python
    config = _config(tmp_path, exec_armed=True)
    # The two reads the constructor takes, as a registered strategy answers them inside `on_start`.
    client = types.SimpleNamespace(cache=object(), strategy_id=object())
    executor = node._probe_executor_factory(config)(client)
    assert isinstance(executor, ProbeExecutor)
    assert executor._client is client
    assert (executor._cache, executor._strategy_id) == (client.cache, client.strategy_id)
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    config = _config(tmp_path)
    strategy = ShadowStrategy(config)
    strategy._executor = node._probe_executor_factory(config)(strategy)
    now = B08 + timedelta(minutes=5)
```

with:

```python
    config = _config(tmp_path)
    strategy = ShadowStrategy(config)
    # Unregistered, the strategy refuses its `cache`, which the constructor reads; a registered one
    # answers it in `on_start`, and the tick forwarding under test reads no client.
    strategy._executor = node._probe_executor_factory(config)(
        types.SimpleNamespace(cache=object(), strategy_id=strategy.strategy_id)
    )
    now = B08 + timedelta(minutes=5)
```

- [ ] **Step 3: Run the two files and watch the new cases fail**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_node.py -q -p no:cacheprovider`
Expected: `17 failed, 352 passed, 2 skipped`; the executor file alone reads `16 failed, 269 passed`. The true arm of `test_a_terminal_the_engine_minted_marks_the_adopted_row_ambiguous_where_the_venues_ack_closes_it` fails on `assert 'accepted' == 'ambiguous'`; `test_the_startup_pass_settles_the_intent_of_the_opener_it_cancels_and_the_ones_that_never_ran` on `assert ('pending', [], 0.0) == ('revoked', [...], 0.0)`; `test_the_startup_pass_leaves_the_intent_of_a_reducer_it_keeps_pending` on `assert 'pending' == 'refused'`; `test_a_restart_with_nothing_resting_still_settles_the_windows_pending_intents` on `assert ('pending', []) == ('refused', [...])`; the three arms of `test_an_intent_whose_order_closed_while_down_is_settled_from_its_rows` on `assert ('pending', 0.0) == ('revoked', 0.0)`, `('revoked', 0.0004)` and `('filled', 0.001)`; `test_an_intents_two_orders_closed_while_down_are_summed_against_the_first_orders_quantity` on `assert ('pending', 0.0) == ('revoked', 0.0007 ± 7.0e-10)`; `test_a_row_with_no_readable_quantity_settles_its_intent_revoked_never_filled` and `test_a_reducer_cancelled_on_a_latched_kill_has_its_intent_revoked` on `assert 'pending' == 'revoked'`; `test_a_flagged_non_terminal_on_an_adopted_row_leaves_its_state_as_it_is` on the WARNING record the old arm logs, `assert [<LogRecord ...>] == []`; `test_a_cancel_the_venue_refused_on_an_adopted_order_logs_the_hand_cancel_and_leaves_the_row_accepted` on `'pending' == 'revoked'`, the pass having written nothing. `test_the_pending_cancel_of_an_adopted_order_is_read_through_the_handle_taken_at_construction` fails on `assert (None, ['the venue order behind O-19700101-000000-000-001-1 could not be read -- its row keeps the state it has']) == (None, [])`, the old tree reading the Cache through the client inside its own `cancel_order`; `test_the_adopt_pass_cancel_of_a_matched_opener_reads_its_pending_cancel_through_the_handle_and_logs_no_traceback` on the second WARNING record, that read's; `test_a_cancel_ack_the_engine_minted_halts_where_the_venues_own_ack_falls_back` and `test_a_kraken_coded_rejection_the_engine_minted_is_ambiguous_rather_than_terminal` on the `flagged` reading, `None` where `True` is expected; in the node file, `test_probe_executor_factory_shape` on `AttributeError: 'ProbeExecutor' object has no attribute '_cache'` and `test_a_quote_for_another_instrument_does_not_disturb_the_running_intent` passes on the old tree, whose constructor reads no client. The false arm of the minted case, the three `leaves_its_intent_pending` cases and the five `leaves_the_pending_intents` cases pass on the old tree, which writes nothing and closes the row on the venue's own ack.

- [ ] **Step 4: The accessor in `cli/engine/execledger.py`, the handles, the sweep and the ambiguous arm in `cli/engine/executor.py`, and the three pages**

Replace, in `cli/engine/executor.py`, this block:

```python
        self._client = client
        self._gate = gate
```

with:

```python
        self._client = client
        # The Cache and the strategy id, taken here, inside `on_start`, where the strategy is not
        # borrowed, and read through these handles ever after: `client.cache` is a getter on the
        # strategy, and inside the dispatch of an event the strategy's own command publishes before
        # it returns -- `OrderPendingCancel` from `cancel_order`, `OrderInitialized` from
        # `submit_order` -- it raises `Already mutably borrowed`, the strategy's PyO3 cell being held
        # by that command, while the Cache itself is free and a handle taken earlier reads it
        # (tests/test_engine_executor.py measures both against a real engine).
        self._cache = client.cache
        self._strategy_id = client.strategy_id
        self._gate = gate
```

Replace, in `cli/engine/executor.py`, this block:

```python
        try:
            resting = list(self._client.cache.orders_open(venue=_VENUE))
        except Exception:
            # Nothing can be adopted OR canceled without the list, and nothing has been touched --
```

with:

```python
        try:
            resting = list(self._cache.orders_open(venue=_VENUE))
        except Exception:
            # Nothing can be adopted OR canceled without the list, and nothing has been touched --
```

Replace, in `cli/engine/executor.py`, this block:

```python
        ones, and both accessors are typed and refuse a plain str."""
        cache = self._client.cache
```

with:

```python
        ones, and both accessors are typed and refuse a plain str."""
        cache = self._cache
```

Replace, in `cli/engine/executor.py`, this block:

```python
            state = venue_state_from_cache(self._client.cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing plan %s", plan.plan_id, exc_info=True)
```

with:

```python
            state = venue_state_from_cache(self._cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing plan %s", plan.plan_id, exc_info=True)
```

Replace, in `cli/engine/executor.py`, this block:

```python
            state = venue_state_from_cache(self._client.cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing intent %d of plan %s", index, plan.plan_id, exc_info=True)
```

with:

```python
            state = venue_state_from_cache(self._cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing intent %d of plan %s", index, plan.plan_id, exc_info=True)
```

Replace, in `cli/engine/executor.py`, this block:

```python
                float(p.signed_qty)
                for p in self._client.cache.positions_open(instrument_id=instrument_id, strategy_id=self._client.strategy_id)
```

with:

```python
                float(p.signed_qty) for p in self._cache.positions_open(instrument_id=instrument_id, strategy_id=self._strategy_id)
```

Replace, in `cli/engine/executor.py`, this block:

```python
        instrument = self._client.cache.instrument(active.instrument_id)
```

with:

```python
        instrument = self._cache.instrument(active.instrument_id)
```

Replace, in `cli/engine/executor.py`, this block:

```python
        try:
            resting = list(self._client.cache.orders_open(venue=_VENUE))
        except Exception:
            logger.critical("open orders could not be read while tripping -- others may still rest at the venue", exc_info=True)
```

with:

```python
        try:
            resting = list(self._cache.orders_open(venue=_VENUE))
        except Exception:
            logger.critical("open orders could not be read while tripping -- others may still rest at the venue", exc_info=True)
```

Replace, in `cli/engine/executor.py`, this block:

```python
                for p in self._client.cache.positions_open(instrument_id=active.instrument_id, strategy_id=self._client.strategy_id)
```

with:

```python
                for p in self._cache.positions_open(instrument_id=active.instrument_id, strategy_id=self._strategy_id)
```

Replace, in `cli/engine/executor.py`, this block:

```python
            order = self._client.cache.order(event.client_order_id)
```

with:

```python
            order = self._cache.order(event.client_order_id)
```

Replace, in `cli/engine/executor.py`, this block:

```python
            held = self._client.cache.positions_open(instrument_id=instrument_id)
```

with:

```python
            held = self._cache.positions_open(instrument_id=instrument_id)
```

Replace, in `cli/engine/executor.py`, this block:

```python
        account did; the reconciliation answers what our own orders did."""
        cache = self._client.cache
```

with:

```python
        account did; the reconciliation answers what our own orders did."""
        cache = self._cache
```

Replace, in `cli/engine/executor.py`, this block:

```python
            payload["reason"] = str(reason)
        boundary, row = attached
```

with:

```python
            payload["reason"] = str(reason)
        if getattr(event, "reconciliation", False):
            payload["reconciliation"] = True  # the flag a minted terminal carries: the ledger's own evidence of the mint
        boundary, row = attached
```

Replace, in `cli/engine/executor.py`, this block:

```python
            self._update_row(active, state="ambiguous", event=payload)
            self._strand_ambiguous(active, f"{name} was reconciled, not received -- the venue never answered")
```

with:

```python
            payload["reconciliation"] = True  # the ledger's own evidence of the mint, once the venue's report settles the row
            self._update_row(active, state="ambiguous", event=payload)
            self._strand_ambiguous(active, f"{name} was reconciled, not received -- the venue never answered")
```

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
        same event, and keeps the row in the re-attach set: the event appends as evidence, with the
        flag recorded so the ledger can tell the mint from the venue's own ack once the row is
        settled, the entry stays in `_attached` for a fill that can still arrive, and the venue's own
        report settles the row -- a startup inside the re-attach window reads it against the order's
        own status; until then the pages have the operator read Kraken's open orders, which tell a
        cancel the venue executed unacknowledged from one that did not reach it, and cancel by hand
        there an order still resting, since no cancel of this process reaches it. The line is a
        WARNING and pages nothing: on the pinned wheel each adopt-pass cancel measured ended in a
        mint about 31 s on, the venue having cancelled the order at the second asked and answered
        nothing this engine applied, so the mint is the expected end of that cancel and not a
        fault. Keyed on the flag and the terminal's name, as the own-order path
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
            logger.warning(
                "%s for %s was reconciled, not received -- no venue answer reached this engine; its row reads ambiguous "
                "until the venue's own report settles it",
                type(event).__name__,
                getattr(event, "client_order_id", "?"),
            )
            return "ambiguous"
        if type(event).__name__ == "OrderCancelRejected":
            # The venue positively says the cancel did not take, so the order rests where the cancel is not re-sent and,
            # where the pass cancelled it and its sweep ran, after the sweep has written its intent: the hand cancel is
            # the operator's, the own-order path's line.
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
        not hypothetical: a read inside the handler for an event a command of this process emits
        itself -- `OrderPendingCancel`, which the adopt pass's and a trip's cancels put on this path
        -- raises `Already mutably borrowed`, because the Cache is still mutably borrowed for the
        write that produced it. Letting that escape would abandon the whole handler and cost the row
        its event payload -- the forensic record this path exists to keep -- to decide a state those
        events never carried anyway.
```

with:

```python
        Three things write nothing here -- no terminal state, row untouched: a status outside the
        map (every OPEN one, PENDING_CANCEL among them, the status behind the `OrderPendingCancel`
        the adopt pass's and a trip's cancels put on this path), an order the Cache does not hold,
        and a Cache that cannot be read at all; a refused cancel writes nothing too, decided before
        the read and logged CRITICAL, since the venue positively says the order rests where the
        cancel is not re-sent and, where the pass cancelled it and its sweep ran, after the sweep has
        written its intent. The read goes through the handle taken at construction and not through
        the client: `OrderPendingCancel` is dispatched while the client's own `cancel_order` still
        runs, and the client's `cache` getter raises `Already mutably borrowed` there -- the
        strategy's PyO3 cell is what that command holds; the Cache itself is free, and the handle
        reads PENDING_CANCEL. A read that raises all the same is caught rather than let escape,
        which would abandon the whole handler and cost the row its event payload -- the forensic
        record this path exists to keep -- to decide a state those events never carried anyway.
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
`revoked` — the kill file, a disarm or quote silence took it mid-rest, so it was revoked rather than held to its expiry, and the plan stops there.```

with:

```markdown
`revoked` — the kill file, a disarm, quote silence or an engine restart took it mid-rest, so it was revoked rather than held to its expiry, and the plan stops there. After a restart the startup pass writes it, with `the engine restarted while the intent was in flight` as the reason, and writes `not run -- the engine restarted before it ran` on the intents that never placed an order; the pass writes the intent before the venue answers its cancel, so a fill that lands afterwards — racing the cancel, or on an order the cancel did not reach — is on the order's row and not in the intent's `filled_qty`: read the row; a cancel the venue refuses leaves the order resting beside its `revoked` intent, the `cancel of adopted order … was REJECTED by the venue` line at CRITICAL says so, and the hand cancel on Kraken's open-orders page is yours. An intent still `pending` after the pass is one whose order the pass left resting — a reducer it kept, or an order it could not cancel or could not match — or the whole window's, when the pass's ledger or venue read failed or the pass latched the kill switch. A startup inside the re-attach window — the intent's boundary day and the next UTC day (`_exec_records_in_window` in `cli/engine/execledger.py` reads those two day directories, for the intent sweep and the row re-attach alike) — settles the intents a failed read left, a cancel that raised, a reconcile that raised, and an order resting outside the Cache once it is cancelled by hand or closes at the venue; an intent whose row recorded no txid, or whose txid no venue read returns, stays `pending` through later startups too, and one the pass latched the kill switch over is written by no startup while the latch's cause stands. Past the window no startup reads the intent or its row: the window's entry records each intent still `pending`, and its row, beside Kraken's open and closed orders and the positions page read for that order.```

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
The executor treats every one of those as an unknown venue outcome: the intent ends `ambiguous`, nothing is resubmitted, and the plan halts; on an order the startup pass adopted, the row reads `ambiguous` instead, until a startup inside the re-attach window settles it against the venue (the `Three terminal outcomes` paragraph below names the window and what the entry records past it), and its intent is the pass's, written before the venue answered, or left `pending` when the pass's ledger or venue read failed or the pass latched the kill switch, when no startup writes it while the latch's cause stands; read Kraken's open orders — an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled, which its entry in Kraken's closed orders, the positions page and the row's `filled_qty` tell apart.```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
`outcome="ambiguous"` is where a minted terminal lands.```

with:

```markdown
`outcome="ambiguous"` is where a minted terminal on the plan's own order lands; one on an order the startup pass adopted moves no outcome, and the `was reconciled, not received` lines count the mints on both paths, read the same way as the timeout count, with `sudo docker logs --since 24h zcrypto-engine | grep -c 'was reconciled, not received'`.```

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
- **Nothing for the pass's cancel of the opener going unacknowledged.** On this wheel each adopt-pass cancel measured ended that way, five of five from 2026-09-24 to 2026-09-26: the venue cancels the order at the second asked and answers nothing the engine applies, nautilus queries the order four times and mints the cancel's terminal for itself about 31 s after the cancel, and the executor's `was reconciled, not received` line is a WARNING that pages nothing; the row reads `ambiguous` until the venue's own report settles it, and step 3 says what does (no count command: the mint is the library's, and the line is `_venue_terminal_state`'s in `cli/engine/executor.py`).
- **A reboot long enough to page any of those is a finding about the reboot**```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **Nothing, if the engine is back inside ≈7 minutes.** All three of the rules D lists need longer.
```

with:

```markdown
- **Nothing, if the engine is back inside ≈7 minutes.** All three of the rules D lists need longer.
- **Nothing for the pass's cancel going unacknowledged.** On this wheel each adopt-pass cancel measured ended that way, five of five from 2026-09-24 to 2026-09-26: the venue cancels the order at the second asked and answers nothing the engine applies, nautilus queries the order four times and mints the cancel's terminal for itself about 31 s after the cancel, and the executor's `was reconciled, not received` line is a WARNING that pages nothing; the row reads `ambiguous` until the venue's own report settles it, and step 4 says what does (no count command: the mint is the library's, and the line is `_venue_terminal_state`'s in `cli/engine/executor.py`).
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
```

with:

```markdown
   - **`cancel of adopted order … was REJECTED by the venue`**: the venue refused the startup pass's, or a kill trip's, cancel of an order this process adopted, and the cancel is not re-sent; the order rests, and its intent, where the pass wrote it, reads `revoked` already. Cancel it by hand on Kraken's open-orders page, and read the row's `filled_qty` for what filled before that; no disarm is owed for this line alone (no count command: the line is `_venue_terminal_state`'s in `cli/engine/executor.py`, and the venue's refusal is the venue's act).
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
3. **The ledger**, with the probe window's ledger read: the order's row carries a terminal `state` and `filled_qty 0.0`, and no `fill` lines at all.```

with:

```markdown
3. **The ledger**, with the probe window's ledger read: the order's row carries `canceled`, or `ambiguous` where the venue's acknowledgement did not arrive and the engine minted the cancel's terminal for itself — step 4's read then decides it: an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart (drill G's record says how that reads) — `filled_qty 0.0`, and no `fill` lines at all; the intent reads `revoked`, written by the startup pass before the venue answered, unless the pass could not cancel or match the order, its ledger or venue read failed, or it latched the kill switch, when it stays `pending` — which of those a later startup settles, inside what window, and what the entry records past it, the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) says.```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
4. **The ledger**, with the probe window's ledger read: the row's `events` for the cancel, and, if a fill raced it, a `fill` line beside it in the same row.```

with:

```markdown
4. **The ledger**, with the probe window's ledger read: the row's `events` for the cancel, and, if a fill raced it, a `fill` line beside it in the same row; the row `canceled`, or `ambiguous` where the engine minted the cancel's terminal for itself (the Record says how that reads, and an order still resting on Kraken's open-orders page is cancelled by hand there); the intent `revoked` with `the engine restarted while the intent was in flight`, written by the pass before the venue answered, so a fill that raced the cancel is on the row and not in the intent's `filled_qty`, and the plan's later intents `refused` as not run — an intent still `pending` after the pass is one whose order it could not cancel or match, or the whole window's when its ledger or venue read failed or it latched the kill switch, and which of those a later startup settles, inside what window, and what the entry records past it, the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) says.```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **One more per fill racing the cancel**, keyed back the same way. Either reading proves a restart re-attaches a ledgered order by its txid, which is the question this reading exists to answer.
```

with:

```markdown
- **One more per fill racing the cancel**, keyed back the same way. Either reading proves a restart re-attaches a ledgered order by its txid, which is the question this reading exists to answer.
- **The row after the pass's cancel** reads `canceled` on the venue's own acknowledgement and `ambiguous` on one the engine minted for itself after its in-flight budget — the cancel executed at Kraken with its acknowledgement lost, or did not reach it, and Kraken's open orders are what tell those apart: an order still resting there is cancelled by hand on that page, one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart, and an `ambiguous` row is settled by a startup inside the re-attach window, which the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names with what the entry records past it. The intent reads `revoked` in both cases, written by the pass itself before the venue answered, so a fill after that is on the row alone — unless the pass's ledger or venue read failed, when it stays `pending` for a startup inside that window, or the pass latched the kill switch, when no startup writes it while the latch's cause stands.
```

- [ ] **Step 5: Run the two files and watch them pass**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_node.py -q -p no:cacheprovider`
Expected: `369 passed, 2 skipped`; the executor file alone reads `285 passed`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_engine_execledger.py tests/test_engine_node.py tests/test_engine_metrics.py tests/test_engine_executor.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_count_list.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1955 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. `mdformat` covers the three runbook pages.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/execledger.py cli/engine/executor.py infra/runbooks/drills-order-path.md infra/runbooks/engine-procedures.md infra/runbooks/engine.md tests/test_engine_executor.py tests/test_engine_node.py
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
the engine minted for an adopted order now writes the row ambiguous, at WARNING, since on this wheel
the mint is how each adopt-pass cancel measured ended, five of five over 2026-09-24 to 2026-09-26,
Kraken having cancelled the order at the second asked and answered nothing the engine applied, and
both mint sites record the event's reconciliation flag in the row, so the ledger tells a mint from
the venue's own ack once the row is settled; a flagged non-terminal writes nothing;
a cancel the venue refuses on an adopted order logs CRITICAL naming the hand cancel and writes
nothing, the intent standing as the pass left it; ambiguous keeps the row in the re-attach set, so
a startup inside the re-attach window settles it, and the pages name the window and what the
entry records past it. The runbook's
rest-hold vocabulary, its pre-probe step on minted terminals, drill A1's and G's Must fire, operator
and record clauses, and the error-logs runbook's class for the refused cancel's line say so.

The executor takes the Cache and the strategy id once at construction, inside on_start, and reads
through those handles at every site: the RuntimeError: Already mutably borrowed WARNING that every
adopt-pass or trip cancel of a matched adopted order logged with a traceback was the client's own
PyO3 cell, held by its running cancel_order while the library dispatched the OrderPendingCancel it
publishes, not the Cache, which a handle taken earlier reads -- measured against a real engine, and
the prose that blamed the Cache is corrected. The read now answers PENDING_CANCEL, which maps to no
state, as it always should have; the node tests hand the factory a client that answers the two
reads a registered strategy answers in on_start.

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
accepted; the adopt pass's cancel dispatching OrderPendingCancel inside the client's own command, read
through the handle with no line, in a real engine with two strategies and against a stub client that
refuses each attribute while its cancel runs; the flag recorded on a minted terminal's event on both
paths and absent from the venue's own.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with eighteen probes, then record their verdicts by a message-only amend**

The executor's control shortens the revoked reason, which the settling case pins. The mutations, in order: an intent whose order the pass left resting is settled; the sweep is skipped when nothing rests; the minted-terminal arm is disarmed, so the row reads the venue's status; the sweep runs on a failed ledger read; the sweep runs on a failed venue read; the sweep runs after the pass latched the kill switch; the loop's exit runs the sweep on a failed ledger read; the loop's exit runs it on a failed venue read; the refused-cancel arm is disarmed, so the venue's refusal logs nothing; a partial counts as filled; a row with no readable quantity counts as filled; the target is read off the smallest order; a flagged non-terminal writes ambiguous; the external path's read goes back through the client, so the adopt pass's `OrderPendingCancel` raises inside the cancel; the minted arm logs CRITICAL; the external path drops the flag from the mint's event; the own path drops it. The ledger's control misspells the pending word so the accessor lists nothing, and its mutation lists every intent, terminal ones included. Each `-k` selects 25 of the file's 285 cases:

```bash
K="settles_the_intent or reducer_it_keeps or nothing_resting or closed_while_down_is_settled or first_orders_quantity or no_readable_quantity or leaves_its_intent_pending or latched_kill_has or leaves_the_pending or minted_marks or flagged_non_terminal or venue_refused or handle_taken_at_construction or logs_no_traceback or engine_minted_halts or rejection_the_engine_minted"
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
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/            order = self._cache.order(event.client_order_id)/            order = self._client.cache.order(event.client_order_id)/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation '/^        if type(event).__name__ in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):$/,/^            return "ambiguous"$/ s/logger.warning(/logger.critical(/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            payload\["reconciliation"\] = True  # the flag a minted terminal carries.*$/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            payload\["reconciliation"\] = True  # the ledger.s own evidence.*$/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/execledger.py \
  --control 's/if i\["outcome"\] == "pending"/if i["outcome"] == "pendng"/' \
  --mutation 's/if i\["outcome"\] == "pending"/if True/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <that file>` — the Global Constraints' rule, never `--amend -m "…"`, inside which the shell runs each backticked name below as a command:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/executor.py`, control the revoked reason
shortened so the settling case fails, through
`-k "settles_the_intent or reducer_it_keeps or nothing_resting or closed_while_down_is_settled or first_orders_quantity or no_readable_quantity or leaves_its_intent_pending or latched_kill_has or leaves_the_pending or minted_marks or flagged_non_terminal or venue_refused or handle_taken_at_construction or logs_no_traceback or engine_minted_halts or rejection_the_engine_minted"`:
an intent whose order the pass left resting settled, KILLED, control proven; the sweep skipped
when nothing rests, KILLED, control proven; the minted-terminal arm disarmed, KILLED, control
proven; the sweep run on a failed ledger read, KILLED, control proven; the sweep run on a failed
venue read, KILLED, control proven; the sweep run after the pass latched the kill switch, KILLED,
control proven; the loop's exit running the sweep on a failed ledger read, KILLED, control proven;
the loop's exit running it on a failed venue read, KILLED, control proven; the refused-cancel arm
disarmed, KILLED, control proven; a partial counted as filled, KILLED, control proven; a row with
no readable quantity counted as filled, KILLED, control proven; the target read off the smallest
order, KILLED, control proven; a flagged non-terminal writing ambiguous, KILLED, control proven;
the external path's read back through the client, KILLED, control proven; the minted arm at
CRITICAL, KILLED, control proven; the external path dropping the mint's flag, KILLED, control
proven; the own path dropping it, KILLED, control proven; over `cli/engine/execledger.py`, control the pending word misspelled: every intent listed, terminal
ones included, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` — Expected: `1`, the verdict naming the script.

---

### Task 4: The re-read pass re-cancels the order a cut left resting, settles its row from the venue's answer, and runs after a mint with the sockets up

This task is the spec's fourth cluster (D17 to D21): the third cluster's pass at one more moment, so it falls with Task 3 if that cluster is struck.

What this task decides, where the spec leaves it open:

- The trigger is kept in the executor as the set of endpoints reported down, `_sockets_down`, and the arm as a count of tries left, `_reread_tries`, set on each return of an endpoint held down; the handler arms and the tick runs, before the pickup and with nothing in flight, `_nothing_in_flight`: `_active` None and the Cache's `orders_inflight` empty, since the startup pass's cancels of adopted orders and a trip's leave orders PENDING_CANCEL with no intent live. The second trigger is `_arm_reread_after_mint`, called at both mint sites — `_venue_terminal_state`'s minted arm and `_on_order_event`'s reconciled arm — and arming only when no endpoint is held down; a `DISCONNECTED` clears the count, so a mint inside a cut, whichever of F2's two clocks fires first, reads nothing until a socket's return arms the pass again (spec D15, D17).
- The population is derived at the pass through `_minted_terminal`, a module-level predicate on the Cache's order, and `_cached_order` is split: `_cache_lookup` is the two-step lookup the startup sweeps used, and `_cached_order` withholds an order so closed from every caller.
- The pass calls `_reconcile_adopted_rows` with `recancel=True`, whose one new arm sends a report still open to `_recancel`; the read is `_read_venue_orders`' scope rule inline, since that method's failure arm sets the startup's refusal and this pass sets none.
- The bare-client cancel is `cancel_venue_order`, `read_venue_orders`' construction, injectable as `venue_cancel` beside `venue_orders`; the test module records it with `_VenueCancel` and resolves it at the call through `_cancel_venue_order`, so the module collects before the source step, and passes `venue_cancel` only when given, so every earlier case still builds its executor on the tree before that step.
- F2's shape on the plan's own order is built by `_minted_after_a_cut`: a real `LimitOrder` held in the stub Cache after the startup pass ran (`_hold_in_cache`), the quote feed silent through the cut so the executor sends its one cancel, and the minted `OrderCanceled` applied to the order before the executor sees it, as the library does.
- The loopback venue answers `CancelOrder` with `cancel_count`, 1 unless a test sets 0, and records the form, so the real client's cancel is measured offline as its read is, and its return on `{"count": 0}` -- the answer the client does not read -- with it.

**Files:**
- Modify `cli/engine/executor.py` (the `nautilus_trader.common` import; `_REREAD_ATTEMPTS` after `_VENUE_READ_MARGIN`; `_minted_terminal` before `_venue_order_id_of`; `read_venue_orders`' nonce paragraph; `cancel_venue_order` after it; `ProbeExecutor`'s docstring and `__init__`; `on_timer`'s reconnect line before the pickup; `on_socket_state` after `_publish_resting_age`; `_nothing_in_flight`, `_reread_pass` and `_minted_closed` before `_reconcile_adopted_rows`; `_reconcile_adopted_rows`' signature, docstring and report arm; `_recancel` before `_mark_unmatched`; `_cached_order` split into `_cached_order` and `_cache_lookup`; `_arm_reread_after_mint` after `on_socket_state`, called from `_venue_terminal_state`'s minted arm, whose line names the pass, and from `_on_order_event`'s reconciled arm; `on_socket_state`'s `DISCONNECTED` arm)
- Modify `cli/engine/node.py` (`ShadowStrategy`'s docstring; `on_start`'s subscription; the `on_socket_state` forwarder)
- Modify `infra/runbooks/drills-order-path.md` (F2's Must fire, one bullet added; its operator actions 3 and 4; the property paragraph after them; its Record; A1's operator action 3, G's operator action 4 and G's Record bullet on the row after the pass's cancel, each gaining the pass's settle)
- Modify `infra/runbooks/engine.md` (the error-logs runbook's step 2, one class added before `Anything naming the executor`; the socket section's real-drop bullet)
- Modify `infra/runbooks/engine-procedures.md` (the pre-probe step on minted terminals, two clauses)
- Test: `tests/test_engine_executor.py` (the `nautilus_trader.common` import and three model names; `StubCache.orders_inflight`; `_EVENT_DEFAULTS`' pending-cancel entry; `_executor`'s `venue_cancel`; `_VenueOrders`' docstring; `_VenueCancel` and `_cancel_venue_order` before `_closed_order`; `_resting_executor`'s two keywords; six helpers and fourteen cases before `_UnreadableOrderCache`, the minted case's asserted line re-trued to the pass; three cases after `test_read_venue_orders_refuses_without_credentials_before_building_a_client`)
- Test: `tests/kraken_loopback.py` (`cancel_forms` and `cancel_count`; the `CancelOrder` answer)
- Test: `tests/test_engine_node.py` (`RecordingExecutor.on_socket_state`; `_exec_stub`'s subscription; two `on_start` assertions; the forwarder case)
- Test: `tests/test_engine_stub_fidelity.py` (the `_VenueCancel` row)

**Interfaces:**
- Consumes: `_resting_executor`, `_executor`, `_intent`, `_resting_limit_order`, `_event`, `_accepted`, `_fill`, `_report`, `_VenueOrders`, `_submitted_row`, `_pending_plan_entry`, `_deliver_external_event`, `_deliver_fill`, `_drop_plan`, `_plan_dict`, `_quote`, `_record`, `_intent_outcome`, `_boundary`, `_executor_errors`, `_gate`, `_Clock`, `RecordingMetrics`, `set_executor_hooks`, `StubClient`, `StubCache`, `_TXID`, `_TRADER_ID`, `_ACCOUNT_ID`, `NOW`, `kraken_loopback`, `_loopback_credentials`, `executor_module` (and its `_ordered_qty`, `_REREAD_ATTEMPTS` through it), `EngineError`, `GateLevel`, `OrderStatus`, `OrderAccepted`, `OrderCanceled`, `ClientOrderId`, `VenueOrderId`, `UUID4`, `logging`, `pytest`, `timedelta` from the test module's existing names; `RecordingExecutor`, `_exec_stub`, `FakeClock`, `ShadowStrategy`, `_config` in the node tests; `_ADOPTED_TERMINAL_STATES`, `_RECONCILED_TERMINALS`, `_VENUE`, `_row_venue_order_id`, `_row_label`, `_reconcile_adopted_row`, `open_submitted_rows`, `update_submitted_row`, `_VENUE_READ_MARGIN`, `_VENUE_READ_TIMEOUT_SECONDS`, `_credentials`, `_ACCOUNT_ID` in the executor.
- Produces: `SocketState` and `SocketStateChanged` from `nautilus_trader.common`, `ClientId`, `OrderPendingCancel` and `Venue` from `nautilus_trader.model` in the test module; `cancel_venue_order(venue_order_id, instrument_id, *, base_url=None)`; `_minted_terminal(order) -> bool`; `_REREAD_ATTEMPTS`; `ProbeExecutor(..., venue_cancel=None)`, `.on_socket_state(event)`, `._arm_reread_after_mint()`, `._nothing_in_flight() -> bool`, `._reread_pass(now)`, `._minted_closed(row)`, `._recancel(boundary, row, venue_order_id, report)`, `._cache_lookup(row, venue_order_id)`, `._reconcile_adopted_rows(rows, venue_orders, *, recancel=False)`; `ShadowStrategy.on_socket_state(event)`; the row event `{"event": "recancelled", "at", "venue_order_id"}`; `StubCache.orders_inflight`, `_VenueCancel`, `_cancel_venue_order`, `_socket`, `_reconnect`, `_hold_in_cache`, `_minted_after_a_cut` in the test module; `KrakenLoopback.cancel_forms` and `.cancel_count`; `RecordingExecutor.socket_states`.

- [ ] **Step 1: Confirm Task 3 has landed and the executor is at the spec's basis**

Run: `grep -c '_settle_pending_intents' cli/engine/executor.py; grep -c 'on_socket_state' cli/engine/executor.py`
Expected: `4` then `0`. A first count other than 4 means Task 3 is not on the branch; a second other than 0 means the handler already exists; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_executor.py`, `tests/kraken_loopback.py`, `tests/test_engine_node.py` and `tests/test_engine_stub_fidelity.py`**

Replace, in `tests/test_engine_executor.py`, this block:

```python
                "reads ambiguous until the venue's own report settles it",
```

with:

```python
                "reads ambiguous until the re-read pass settles it from the venue's own report",
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
import pytest
from nautilus_trader.core import UUID4
from nautilus_trader.model import (
    AccountId,
    ClientOrderId,
```

with:

```python
import pytest
from nautilus_trader.common import SocketState, SocketStateChanged
from nautilus_trader.core import UUID4
from nautilus_trader.model import (
    AccountId,
    ClientId,
    ClientOrderId,
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    TradeId,
    TraderId,
    VenueOrderId,
```

with:

```python
    TradeId,
    TraderId,
    Venue,
    VenueOrderId,
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    def orders_open(self, *, venue=None, **kwargs):
        return list(self._open_orders)

    def account_for_venue(self, *, venue=None, **kwargs):
```

with:

```python
    def orders_open(self, *, venue=None, **kwargs):
        return list(self._open_orders)

    def orders_inflight(self, *, venue=None, **kwargs):
        """The orders the library's in-flight check queries, derived from each held order's own
        `is_inflight` -- SUBMITTED, PENDING_UPDATE or PENDING_CANCEL on the real state machine -- so
        a test moves it only by applying the library's own events to a REAL order."""
        return [o for o in self._open_orders if getattr(o, "is_inflight", False)]

    def account_for_venue(self, *, venue=None, **kwargs):
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
def _executor(tmp_path: Path, *, client=None, gate=None, config=None, clock=None, venue_orders=None) -> ProbeExecutor:
    client = client if client is not None else StubClient()
    return ProbeExecutor(
        client=client,
        gate=gate if gate is not None else _gate(tmp_path),
        config=config if config is not None else _config(tmp_path),
        clock=clock if clock is not None else (lambda: NOW),
        venue_orders=venue_orders,
    )
```

with:

```python
def _executor(
    tmp_path: Path, *, client=None, gate=None, config=None, clock=None, venue_orders=None, venue_cancel=None
) -> ProbeExecutor:
    client = client if client is not None else StubClient()
    return ProbeExecutor(
        client=client,
        gate=gate if gate is not None else _gate(tmp_path),
        config=config if config is not None else _config(tmp_path),
        clock=clock if clock is not None else (lambda: NOW),
        venue_orders=venue_orders,
        # Passed only when given: the keyword lands in the re-read task's source step, and every
        # other case here builds its executor before that step.
        **({"venue_cancel": venue_cancel} if venue_cancel is not None else {}),
    )
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
class _VenueOrders:
    """The executor's `venue_orders` reader: answers `reports`, or raises `raises`, and records the
    `since` of every call -- the read is once per process, and a second call is a finding."""
```

with:

```python
class _VenueOrders:
    """The executor's `venue_orders` reader: answers `reports`, or raises `raises`, and records the
    `since` of every call -- the startup pass reads once, and the re-read pass once more per arm
    over the rows it minted terminal; any other second call is a finding."""
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
def _closed_order(client_order_id, status, *, filled_qty=0.0, venue_order_id=None):
```

with:

```python
class _VenueCancel:
    """The executor's `venue_cancel`: records each `(venue_order_id, instrument_id)` it is asked to
    cancel, and raises `raises` instead when set -- the venue's refusal, or the cut not over."""

    def __init__(self, *, raises=None):
        self.calls: list[tuple[str, str]] = []
        self._raises = raises

    def __call__(self, venue_order_id, instrument_id):
        self.calls.append((venue_order_id, instrument_id))
        if self._raises is not None:
            raise self._raises


def _cancel_venue_order(*args, **kwargs):
    """`cancel_venue_order`, resolved at the call: the name lands in the re-read task's source step,
    and the module must collect before it does."""
    return executor_module.cancel_venue_order(*args, **kwargs)


def _closed_order(client_order_id, status, *, filled_qty=0.0, venue_order_id=None):
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
def _resting_executor(tmp_path, *, intents=None, bid=30000.0, ask=30001.0, client=None):
    """A plan accepted and its first intent resting: exactly one order at the venue. The trailing
    assert is the point -- a helper that quietly submitted nothing would hand every ladder test
    below a green it never earned."""
    clock = _Clock()
    client = client if client is not None else StubClient()
    ex = _executor(tmp_path, client=client, clock=clock)
```

with:

```python
def _resting_executor(tmp_path, *, intents=None, bid=30000.0, ask=30001.0, client=None, venue_orders=None, venue_cancel=None):
    """A plan accepted and its first intent resting: exactly one order at the venue. The trailing
    assert is the point -- a helper that quietly submitted nothing would hand every ladder test
    below a green it never earned."""
    clock = _Clock()
    client = client if client is not None else StubClient()
    ex = _executor(tmp_path, client=client, clock=clock, venue_orders=venue_orders, venue_cancel=venue_cancel)
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
class _UnreadableOrderCache(StubCache):
```

with:

```python
# --- the re-read pass (drills F2, G and A1) ---------------------------------------------------------------


def _socket(state, endpoint="kraken-spot-data-streams"):
    """A REAL `SocketStateChanged`, as the client's socket-state stream delivers it once the strategy
    subscribed: the Kraken client's id and the socket's own endpoint name, `kraken-spot-data-streams`
    measured against the loopback drop for the data socket. The execution socket's name is unmeasured
    offline, which is why the executor keys on the set of endpoints down and never on a name."""
    return SocketStateChanged(_TRADER_ID, ClientId("KRAKEN"), Venue("KRAKEN"), endpoint, state, UUID4(), 0, 0)


def _reconnect(ex, *endpoints):
    """The cut and the return as the stream reports them: each endpoint down, then each one back."""
    endpoints = endpoints or ("kraken-spot-data-streams",)
    for endpoint in endpoints:
        ex.on_socket_state(_socket(SocketState.DISCONNECTED, endpoint))
    for endpoint in endpoints:
        ex.on_socket_state(_socket(SocketState.CONNECTED, endpoint))


def _hold_in_cache(client, order):
    """Put a REAL order into the stub Cache after the startup pass ran, as the library's own submit
    does for an order this process places: held from construction, the pass at the first tick would
    cancel it as an order with no row."""
    client.cache._open_orders.append(order)


def _minted_after_a_cut(tmp_path, *, venue_orders=None, venue_cancel=None):
    """Drill F2's shape on the plan's own order: a rest-hold order accepted under `_TXID`, the quote
    feed silent through the cut so the executor sends its one cancel, the venue never answering it,
    and the engine minting `OrderCanceled` for itself -- the Cache's order closed by the flagged
    terminal, the row `ambiguous`, the intent `ambiguous`, the plan dropped."""
    ex, client, clock = _resting_executor(
        tmp_path,
        intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)],
        venue_orders=venue_orders,
        venue_cancel=venue_cancel,
    )
    order = _resting_limit_order("O-1", venue_order_id=_TXID)
    _hold_in_cache(client, order)
    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)  # quote silence: the one cancel goes out into the cut
    assert [str(cid) for cid in client.canceled] == ["O-1"]
    minted = _event(OrderCanceled, client_order_id="O-1", reconciliation=True)
    order.apply(minted)
    ex.on_order_event(minted)
    assert (_record(tmp_path)["submitted"][0]["state"], _intent_outcome(tmp_path)) == ("ambiguous", "ambiguous")
    return ex, client, clock


def test_a_reconnect_after_a_minted_cancel_re_cancels_the_order_still_resting_and_settles_its_row(tmp_path):
    """Drill F2, measured 2026-09-26: the REST cancel failed in the cut, the engine minted the cancel's
    terminal, and the order rested at Kraken for eight minutes with nothing re-cancelling it on the
    reconnect. The sockets' return arms the pass; the next tick with nothing in flight reads the venue
    for the row the mint closed, the report says the order still rests, the cancel goes out by txid on
    the bare client -- the strategy handle refuses an order it holds closed -- and the venue's
    acceptance writes the row `canceled`. The intent stays `ambiguous`: it was terminal at the mint,
    and the row is the re-cancel's record. No counter moves for the re-cancel."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _reconnect(ex)
    assert venue.calls == [] and cancel.calls == []  # the handler arms; the tick runs
    clock.now += timedelta(seconds=5)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(clock.now)

    assert venue.calls == [_boundary(NOW) - timedelta(hours=1)]
    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    assert [str(cid) for cid in client.canceled] == ["O-1"]  # no second cancel through the handle
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "canceled"
    assert row["events"][-1] == {"event": "recancelled", "at": clock.now.isoformat(), "venue_order_id": _TXID}
    assert _intent_outcome(tmp_path) == "ambiguous"
    assert metrics.orders == []
    assert [r.getMessage() for r in records if r.getMessage().startswith("re-cancelled")] == [
        f"re-cancelled O-1 (Kraken {_TXID}) -- it rested at Kraken (ACCEPTED) after a terminal this engine minted; "
        "its row reads canceled"
    ]
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 1  # the arm is consumed: a later tick reads nothing


def test_a_reconnect_after_a_minted_cancel_of_an_adopted_opener_re_cancels_it_and_leaves_the_intent_the_sweep_wrote(
    tmp_path,
):
    """The adopted path's twin: the startup pass cancelled the opener and its sweep wrote the intent
    `revoked`; the cut lost the ack and the engine minted the terminal, the row `ambiguous`. The
    re-read pass reads the venue, cancels what still rests by txid and settles the row; the intent
    stands as the sweep wrote it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=cancel)
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [_TXID] and _intent_outcome(tmp_path, 0, earlier) == "revoked"
    assert venue.calls == []  # the Cache answered the startup pass, so the venue was not read
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "ambiguous"

    _reconnect(ex)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "canceled" and row["events"][-1]["event"] == "recancelled"
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"


def test_a_venue_report_closed_at_the_reconnect_settles_the_minted_row_without_a_cancel(tmp_path):
    """G's shape met on a reconnect rather than a startup: the venue had executed the cancel and lost
    the ack. The report closes the row as a startup would, and no cancel goes out."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    cancel = _VenueCancel()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert cancel.calls == []
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "canceled"
    assert [e.get("event") or e["type"] for e in row["events"]] == ["OrderAccepted", "OrderCanceled"]


def test_a_venue_report_filled_at_the_reconnect_settles_the_minted_row_filled_and_counts_it_as_a_startup_would(tmp_path):
    """The one counter the pass moves, and not for a re-cancel: a report that completes the row takes
    the startup's completion arm, `filled` written and counted once, so the board reads the fill the
    cut hid as a restart's sweep would read it. The intent stays as the mint left it."""
    venue = _VenueOrders()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    ordered = executor_module._ordered_qty(_record(tmp_path)["submitted"][0])
    venue.reports.append(_report(_TXID, OrderStatus.FILLED, filled_qty=f"{ordered:.8f}", quantity=f"{ordered:.8f}"))
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"], metrics.orders) == ("filled", ordered, ["filled"])
    assert _intent_outcome(tmp_path) == "ambiguous"


def test_a_venue_read_failing_after_the_reconnect_is_tried_on_three_ticks_then_left_to_the_hand_or_a_restart(tmp_path):
    """The sockets' return is the host's network, not Kraken's REST edge answering: the pass asks
    again on the next tick, three ticks in all, then names the hand cancel and a restart and stops
    asking; a later return of the sockets arms it again. Unlike the startup read, no plan is refused
    for it."""
    venue = _VenueOrders(raises=RuntimeError("dns"))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())

    _reconnect(ex)
    with _executor_errors(level=logging.WARNING) as records:
        for _ in range(4):
            clock.now += timedelta(seconds=5)
            ex.on_timer(clock.now)

    assert len(venue.calls) == 3
    lines = [r for r in records if "re-read pass could not read" in r.getMessage()]
    assert [r.levelno for r in lines] == [logging.WARNING, logging.WARNING, logging.CRITICAL]
    assert lines[-1].getMessage().endswith("or restart the engine, whose startup pass reads it")
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"
    assert ex._reconciliation_refusal is None
    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 4


def test_a_reconnect_reads_the_venue_for_no_row_the_engine_did_not_mint_terminal(tmp_path):
    """The population is the rows whose Cache order a minted terminal closed and no other: a kept
    reducer's row is open and its order rests, so the sockets' return reads nothing for it."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)
    ex.on_timer(NOW)

    _reconnect(ex)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert venue.calls == [] and client.canceled == []


def test_each_socket_reported_down_arms_the_pass_on_its_own_return_and_the_connect_itself_arms_nothing(tmp_path):
    """The stream delivers `CONNECTED` at the connect itself, which owes nothing. With two endpoints
    down, the first back owes the pass whatever the second reports -- the execution socket's name,
    and whether its return arrives under the string its drop carried, are unmeasured offline, and the
    data socket's return is what F2 measured -- and the second back owes it again, an empty
    population consuming that arm with no read. A socket reported down first holds the arm the
    mint set, so the first tick measures the connect's `CONNECTED` alone."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "a-second-endpoint"))  # holds the arm the mint set

    ex.on_socket_state(_socket(SocketState.CONNECTED))  # the connect itself: not held down
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert venue.calls == []
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 1  # the first return arms it, the second endpoint still down
    assert (ex._reread_tries, ex._sockets_down) == (0, {"a-second-endpoint"})
    ex.on_socket_state(_socket(SocketState.CONNECTED, "a-second-endpoint"))
    assert ex._reread_tries == executor_module._REREAD_ATTEMPTS  # armed again
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 1  # nothing left minted terminal: the arm is consumed with no read


def test_the_pass_waits_for_a_tick_with_nothing_of_this_process_in_flight(tmp_path):
    """The read and the cancel go out on a second client on the same key -- `read_venue_orders`'
    nonce hazard against the execution client's in-flight queries -- so the pass runs on a tick with
    no order of this process in flight, the arm -- a mint's, here, beside a live intent -- kept until one comes."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    clock = _Clock()
    ex = _executor(tmp_path, client=client, clock=clock, venue_orders=venue, venue_cancel=_VenueCancel())
    ex.on_timer(clock.now)
    _drop_plan(tmp_path, _plan_dict())
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    ex.on_quote(_quote())
    assert client.last_order_id == "O-1" and ex._active is not None  # the plan's own order is in flight

    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))  # the mint arms
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert venue.calls == []
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.001)
    assert ex._active is None
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "canceled"


def test_the_reread_pass_waits_while_a_startup_cancel_of_an_adopted_order_is_still_unanswered(tmp_path):
    """`_active` None is not nothing in flight: the startup pass's cancels of adopted orders, and a
    trip's, leave orders PENDING_CANCEL with no intent live, and the library's in-flight check
    queries those on the same key. The pass waits for a tick on which the Cache holds no order of
    this process in flight, and the minted terminal that ends the library's query is what frees it."""
    earlier = NOW - timedelta(hours=4)
    minted, pending = _TXID, "OBBBBB-BBBBB-BBBBBB"
    _pending_plan_entry(tmp_path, earlier, n_intents=2)
    _submitted_row(tmp_path, "O-a", reduce_only=False, when=earlier, index=0, venue_order_id=minted)
    _submitted_row(tmp_path, "O-b", reduce_only=False, when=earlier, index=1, venue_order_id=pending)
    orders = [_resting_limit_order(minted, venue_order_id=minted), _resting_limit_order(pending, venue_order_id=pending)]
    client = StubClient(StubCache(open_orders=orders))
    venue = _VenueOrders(_report(minted, OrderStatus.ACCEPTED))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=_VenueCancel()
    )
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [minted, pending]
    for order in orders:  # the handle's own `OrderPendingCancel`, which the library applies on the cancel
        order.apply(_event(OrderPendingCancel, client_order_id=str(order.client_order_id)))
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=minted, reconciliation=True))

    _reconnect(ex)
    ex.on_timer(NOW + timedelta(seconds=5))
    assert venue.calls == [] and ex._active is None  # the second cancel is still in flight
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=pending, reconciliation=True))
    ex.on_timer(NOW + timedelta(seconds=10))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]


def test_a_re_cancel_the_venue_refuses_leaves_the_row_and_names_the_hand_cancel(tmp_path):
    """The order went between the read and the cancel, or the cut is not over for REST: the venue's
    refusal, or a raise, leaves the row as it was and the line names the hand cancel -- the
    refused-cancel arm's precedent -- and the arm is consumed, since the line is the operator's."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel(raises=RuntimeError("EOrder:Unknown order"))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    with _executor_errors() as records:
        ex.on_timer(clock.now)

    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"
    assert [r.getMessage() for r in records] == [
        f"the re-read pass's cancel of O-1 (Kraken {_TXID}) raised or was refused -- the order may still rest at "
        "Kraken: cancel it by hand on Kraken's open-orders page"
    ]
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 1


def test_a_partial_fill_applied_after_the_mint_keeps_the_row_in_the_reread_pass_which_re_cancels_the_remainder(
    tmp_path,
):
    """The order F2 exists for: a maker at the touch part-fills during the cut, and the private stream
    delivers the fill after the reconnect. The state machine applies it to the order held
    minted-CANCELED -- its last event is then the fill -- so the mint is read off the order's
    history, the venue is asked, and the remainder still resting is re-cancelled with the fill on
    the row."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004"))
    cancel = _VenueCancel()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)
    order = client.cache.order(ClientOrderId("O-1"))
    fill = _fill("O-1", 0.0004, venue_order_id=VenueOrderId(_TXID))
    order.apply(fill)
    ex.on_order_event(fill)
    assert (order.status, type(order.last_event).__name__) == (OrderStatus.CANCELED, "OrderFilled")

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1 and cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("canceled", 0.0004)


def test_a_minted_cancel_of_an_adopted_opener_with_the_sockets_up_is_settled_from_the_venue_on_the_next_tick(tmp_path):
    """Drills G and A1, measured 2026-09-26, and the shape of each adopt-pass cancel measured on this
    wheel: the pass cancels the adopted opener, Kraken cancels it at the second asked, nothing it
    answers is applied, and about 31 s on the engine mints the cancel's terminal with the sockets
    up. The mint writes the row `ambiguous` at WARNING and arms the re-read pass; the next tick with
    nothing in flight reads the venue for the row, the report says closed, and the row settles
    `canceled` with no cancel sent, no counter moved, no CRITICAL line, and the intent as the sweep
    wrote it. The row's own evidence of the mint is the flag on its `OrderCanceled` event."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    cancel = _VenueCancel()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=cancel)
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [_TXID] and _intent_outcome(tmp_path, 0, earlier) == "revoked"
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
        assert _record(tmp_path, earlier)["submitted"][0]["state"] == "ambiguous"
        ex.on_timer(NOW + timedelta(seconds=5))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)] and cancel.calls == []
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "canceled"
    assert row["events"][-1] == {"type": "OrderCanceled", "at": NOW.isoformat(), "reconciliation": True}
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"
    assert metrics.orders == []
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (
            logging.WARNING,
            f"OrderCanceled for {_TXID} was reconciled, not received -- no venue answer reached this engine; its row reads "
            "ambiguous until the re-read pass settles it from the venue's own report",
        ),
        (logging.WARNING, "the re-read pass reads 1 row(s) this engine minted terminal against the venue"),
    ]
    ex.on_timer(NOW + timedelta(seconds=10))
    assert len(venue.calls) == 1  # the arm is consumed


def test_a_socket_reported_down_holds_the_re_read_a_mint_armed_until_a_socket_is_back(tmp_path):
    """F2's shape, where the mint landed half a second before the socket's own deadline reported the
    cut: the mint arms the pass, the `DISCONNECTED` holds it, so nothing is read inside the cut, and
    the socket's return arms it again."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    assert ex._reread_tries == executor_module._REREAD_ATTEMPTS  # the mint armed it

    ex.on_socket_state(_socket(SocketState.DISCONNECTED))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert venue.calls == [] and ex._reread_tries == 0
    ex.on_socket_state(_socket(SocketState.CONNECTED))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1
    assert _record(tmp_path)["submitted"][0]["state"] == "canceled"


def test_a_mint_while_a_socket_is_held_down_arms_nothing_and_the_sockets_return_does(tmp_path):
    """The other order of F2's two clocks: the socket reports the cut before the in-flight budget
    mints the terminal. The mint arms nothing while an endpoint is held down, the tick reads
    nothing, and the return arms the pass."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=_VenueCancel()
    )
    ex.on_timer(NOW)
    ex.on_socket_state(_socket(SocketState.DISCONNECTED))

    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
    assert ex._reread_tries == 0
    ex.on_timer(NOW + timedelta(seconds=5))
    assert venue.calls == []
    ex.on_socket_state(_socket(SocketState.CONNECTED))
    ex.on_timer(NOW + timedelta(seconds=10))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "canceled"


class _UnreadableOrderCache(StubCache):
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
def test_read_venue_orders_refuses_without_credentials_before_building_a_client(monkeypatch):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    with pytest.raises(EngineError, match="the trade credentials are not in this environment"):
        read_venue_orders(NOW, base_url="http://127.0.0.1:9")
```

with:

```python
def test_read_venue_orders_refuses_without_credentials_before_building_a_client(monkeypatch):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    with pytest.raises(EngineError, match="the trade credentials are not in this environment"):
        read_venue_orders(NOW, base_url="http://127.0.0.1:9")


def test_cancel_venue_order_sends_the_txid_on_the_real_client_and_returns_on_count_1_and_count_0_alike(_loopback_credentials):
    """The re-cancel's whole contract on the pinned wheel, offline: the listing is cached first, the
    cancel names the order by its txid alone, and the client returns on the venue's answer without
    reading its `count` -- so `_recancel` writes `canceled` on a `{"count": 0}`, the answer Kraken may
    give for an order gone between the read and the cancel, exactly as on a `{"count": 1}`."""
    with kraken_loopback.serve() as venue:
        _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url=venue.base_url)
        venue.cancel_count = 0
        _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url=venue.base_url)

    assert [form["txid"] for form in venue.cancel_forms] == [_TXID, _TXID]
    assert venue.private_calls[-1] == "CancelOrder"


def test_cancel_venue_order_raises_on_the_venues_refusal(_loopback_credentials):
    with kraken_loopback.serve() as venue:
        venue.errors["CancelOrder"] = "EOrder:Unknown order"
        with pytest.raises(Exception, match="Unknown order"):
            _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url=venue.base_url)
    assert venue.private_calls[-1] == "CancelOrder"  # the refusal came from the venue, not from the client


def test_cancel_venue_order_refuses_without_credentials_before_building_a_client(monkeypatch):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    with pytest.raises(EngineError, match="the trade credentials are not in this environment"):
        _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url="http://127.0.0.1:9")
```

Replace, in `tests/kraken_loopback.py`, this block:

```python
    add_orders: list[dict[str, str]] = field(default_factory=list)
    closed_order_forms: list[dict[str, str]] = field(default_factory=list)
```

with:

```python
    add_orders: list[dict[str, str]] = field(default_factory=list)
    closed_order_forms: list[dict[str, str]] = field(default_factory=list)
    cancel_forms: list[dict[str, str]] = field(default_factory=list)
    # The `count` CancelOrder answers: 1 as Kraken answers a cancel it executed, 0 the other answer a
    # test serves, since which one Kraken gives for a txid already closed is unmeasured.
    cancel_count: int = 1
```

Replace, in `tests/kraken_loopback.py`, this block:

```python
        if path == "/0/private/AddOrder":
            self.add_orders.append(form)
            return {"descr": {"order": "loopback"}, "txid": [f"OLOOP{len(self.add_orders)}-AAAAA-BBBBBB"]}, []
```

with:

```python
        if path == "/0/private/AddOrder":
            self.add_orders.append(form)
            return {"descr": {"order": "loopback"}, "txid": [f"OLOOP{len(self.add_orders)}-AAAAA-BBBBBB"]}, []
        if path == "/0/private/CancelOrder":
            self.cancel_forms.append(form)
            return {"count": self.cancel_count}, []
```

Replace, in `tests/test_engine_node.py`, this block:

```python
        self.external_events: list[object] = []
        self.boundaries: list[datetime] = []

    def on_boundary(self, boundary):
        self.boundaries.append(boundary)
```

with:

```python
        self.external_events: list[object] = []
        self.boundaries: list[datetime] = []
        self.socket_states: list[object] = []

    def on_boundary(self, boundary):
        self.boundaries.append(boundary)

    def on_socket_state(self, event):
        self.socket_states.append(event)
```

Replace, in `tests/test_engine_node.py`, this block:

```python
        _executor_factory=executor_factory,
        _executor=executor,
    )
    stub._schedule_alert = functools.partial(ShadowStrategy._schedule_alert, stub)
```

with:

```python
        _executor_factory=executor_factory,
        _executor=executor,
        socket_subscriptions=[],
    )
    stub.subscribe_socket_state = lambda: stub.socket_subscriptions.append("all")
    stub._schedule_alert = functools.partial(ShadowStrategy._schedule_alert, stub)
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    # The alert chain is untouched by the wiring; the executor tick is a SECOND, repeating timer.
    assert [name for name, _, _ in clock.alerts] == ["shadow-cycle-2026-07-10T12"]
    assert clock.timers == [("exec-probe-tick", timedelta(seconds=5), stub._on_exec_tick)]


def test_on_start_registers_no_exec_tick_without_a_factory(tmp_path):
    clock = FakeClock()
    stub = _exec_stub(_config(tmp_path), clock)
    ShadowStrategy.on_start(stub)
    assert clock.timers == []
    assert stub._executor is None
```

with:

```python
    # The alert chain is untouched by the wiring; the executor tick is a SECOND, repeating timer.
    assert [name for name, _, _ in clock.alerts] == ["shadow-cycle-2026-07-10T12"]
    assert clock.timers == [("exec-probe-tick", timedelta(seconds=5), stub._on_exec_tick)]
    # The socket-state stream is opt-in, and the executor's re-read pass is what reads it.
    assert stub.socket_subscriptions == ["all"]


def test_on_start_registers_no_exec_tick_without_a_factory(tmp_path):
    clock = FakeClock()
    stub = _exec_stub(_config(tmp_path), clock)
    ShadowStrategy.on_start(stub)
    assert clock.timers == []
    assert stub._executor is None
    assert stub.socket_subscriptions == []
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    assert executor.external_events == [event]
    # The filter is a SEPARATE entry point: nothing arrived on the own-order path the trip reads.
    assert executor.events == []


# --- the external order observer (spec 00100 D2) ------------------------------------------------
```

with:

```python
    assert executor.external_events == [event]
    # The filter is a SEPARATE entry point: nothing arrived on the own-order path the trip reads.
    assert executor.events == []


def test_the_socket_state_forwarder_passes_the_object_through_and_is_inert_unwired(tmp_path):
    # The fifth forwarder, in the shape of the other four: object through, a no-op with no executor
    # wired, and a separate entry point from the two order paths.
    strategy = ShadowStrategy(_config(tmp_path))
    strategy.on_socket_state(object())

    executor = RecordingExecutor()
    strategy._executor = executor
    event = object()
    strategy.on_socket_state(event)
    assert executor.socket_states == [event]
    assert executor.events == [] and executor.external_events == []


# --- the external order observer (spec 00100 D2) ------------------------------------------------
```

Replace, in `tests/test_engine_stub_fidelity.py`, this block:

```python
        # Answers REAL `OrderStatusReport`s; what it restates is this repo's reader, not the library.
        "_VenueOrders": Standin(OURS, "cli.engine.executor.read_venue_orders, the venue_orders ProbeExecutor is built with", ()),
```

with:

```python
        # Answers REAL `OrderStatusReport`s; what it restates is this repo's reader, not the library.
        "_VenueOrders": Standin(OURS, "cli.engine.executor.read_venue_orders, the venue_orders ProbeExecutor is built with", ()),
        "_VenueCancel": Standin(OURS, "cli.engine.executor.cancel_venue_order, the venue_cancel ProbeExecutor is built with", ()),
```

- [ ] **Step 3: Run the three files and watch the new cases fail**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_node.py tests/test_engine_stub_fidelity.py -q -p no:cacheprovider`
Expected: `20 failed, 425 passed, 2 skipped`; the executor file alone reads `18 failed, 284 passed`. The thirteen re-read cases that hand the executor a `_VenueCancel` fail in `_executor` on `TypeError: ProbeExecutor.__init__() got an unexpected keyword argument 'venue_cancel'`; `test_a_reconnect_reads_the_venue_for_no_row_the_engine_did_not_mint_terminal` on `AttributeError: 'ProbeExecutor' object has no attribute 'on_socket_state'`; `test_cancel_venue_order_sends_the_txid_on_the_real_client_and_returns_on_count_1_and_count_0_alike` and `test_cancel_venue_order_refuses_without_credentials_before_building_a_client` on `AttributeError: module 'cli.engine.executor' has no attribute 'cancel_venue_order'`, and `test_cancel_venue_order_raises_on_the_venues_refusal` on `Regex pattern did not match`, the same attribute error caught by its `pytest.raises`; the true arm of `test_a_terminal_the_engine_minted_marks_the_adopted_row_ambiguous_where_the_venues_ack_closes_it` on the line's text, the old arm not naming the pass; `test_on_start_builds_the_executor_and_registers_the_exec_tick` on `assert [] == ['all']` and `test_the_socket_state_forwarder_passes_the_object_through_and_is_inert_unwired` on `TypeError: 'object' object is not an instance of 'SocketStateChanged'`, the library's own handler taking the call. `test_on_start_registers_no_exec_tick_without_a_factory` passes on the old tree, which subscribes nothing, and the fidelity table's row finds its class.

- [ ] **Step 4: The pass in `cli/engine/executor.py`, the wiring in `cli/engine/node.py`, and the three pages**

Replace, in `cli/engine/executor.py`, this block:

```python
from nautilus_trader.model import AccountId, ClientOrderId, InstrumentId, OrderSide, OrderStatus, TimeInForce, Venue, VenueOrderId
```

with:

```python
from nautilus_trader.common import SocketState
from nautilus_trader.model import AccountId, ClientOrderId, InstrumentId, OrderSide, OrderStatus, TimeInForce, Venue, VenueOrderId
```

Replace, in `cli/engine/executor.py`, this block:

```python
_VENUE_READ_MARGIN = timedelta(hours=1)
```

with:

```python
_VENUE_READ_MARGIN = timedelta(hours=1)
# How many ticks the re-read pass may fail to read the venue before it stops asking: the sockets'
# return says the host's network is back, not that Kraken's REST edge answers yet, and a pass that
# asked on every tick until it did would be the retry storm the engine runbook's socket section
# forbids. Past the budget the rows keep their state and the line names the hand cancel.
_REREAD_ATTEMPTS = 3
```

Replace, in `cli/engine/executor.py`, this block:

```python
    A second client on one key is a nonce hazard: the adapter serialises signed requests per client,
    so this client's can reach the venue out of order against the execution client's, and one of them
    is answered `Invalid nonce`. The caller therefore makes this read once per process, before this
    process has sent anything -- the startup pass reads it before its own cancels, and no plan is
    picked up before the pass has run -- and never retries it.
```

with:

```python
    A second client on one key is a nonce hazard: the adapter serialises signed requests per client,
    so this client's can reach the venue out of order against the execution client's, and one of them
    is answered `Invalid nonce`. The startup pass therefore makes this read once, before this process
    has sent anything -- before its own cancels, and no plan is picked up before the pass has run --
    and never retries it; the re-read pass reads again on a tick with no intent live and no order
    of this process in flight in the Cache's terms (`_nothing_in_flight`), and `cancel_venue_order`
    follows it on the same terms. What that gate cannot see is the execution client's own signed
    token request while its socket is still reconnecting: a collision there costs the library one
    reconnect attempt or this pass one try, and the library's retry of an `Invalid nonce` is
    unmeasured.
```

Replace, in `cli/engine/executor.py`, this block:

```python
    return list(asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS)) or ())


def _newest_venue_balances(journal_dir: Path) -> dict:
```

with:

```python
    return list(asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS)) or ())


def cancel_venue_order(venue_order_id: str, instrument_id: str, *, base_url: str | None = None) -> None:
    """Cancel one order at the venue by its txid, on `read_venue_orders`' client and terms: the
    re-read pass's cancel of an order the Cache holds closed by a terminal this engine minted,
    which the strategy handle refuses to cancel (`Cannot cancel order: state is ...`, sent nowhere).
    The listing is cached first because the client resolves the pair through it. Returns on the
    venue's answer without reading its `count` -- `{"count": 0}` and `{"count": 1}` return alike,
    measured against the loopback -- and raises on a refusal the venue phrases as an error, or on
    anything short of an answer inside `_VENUE_READ_TIMEOUT_SECONDS`. Which of the two Kraken gives
    for a txid already closed is unmeasured; drill F2's record reads it."""
    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    from cli.engine.node import _ACCOUNT_ID, _credentials

    credentials = _credentials()
    if credentials is None:
        raise EngineError("the trade credentials are not in this environment")
    api_key, api_secret = credentials
    client = KrakenSpotHttpClient(api_key=api_key, api_secret=api_secret, base_url=base_url)

    async def _cancel():
        for instrument in await client.request_instruments() or ():
            client.cache_instrument(instrument)
        await client.cancel_order(
            AccountId(_ACCOUNT_ID), InstrumentId.from_str(instrument_id), venue_order_id=VenueOrderId(venue_order_id)
        )

    asyncio.run(asyncio.wait_for(_cancel(), timeout=_VENUE_READ_TIMEOUT_SECONDS))


def _newest_venue_balances(journal_dir: Path) -> dict:
```

Replace, in `cli/engine/executor.py`, this block:

```python
    `venue_orders` is `read_venue_orders`' signature. None, the engine's construction, reads the
    module's own at call time, so a test can replace it before any executor exists.
    """

    def __init__(self, *, client, gate: ExecutionGate, config: EngineConfig, clock=_utc_now, venue_orders=None) -> None:
        self._client = client
        # The Cache and the strategy id, taken here, inside `on_start`, where the strategy is not
        # borrowed, and read through these handles ever after: `client.cache` is a getter on the
        # strategy, and inside the dispatch of an event the strategy's own command publishes before
        # it returns -- `OrderPendingCancel` from `cancel_order`, `OrderInitialized` from
        # `submit_order` -- it raises `Already mutably borrowed`, the strategy's PyO3 cell being held
        # by that command, while the Cache itself is free and a handle taken earlier reads it
        # (tests/test_engine_executor.py measures both against a real engine).
        self._cache = client.cache
        self._strategy_id = client.strategy_id
        self._gate = gate
        self._config = config
        self._now = clock
        self._venue_orders = venue_orders
```

with:

```python
    `venue_orders` is `read_venue_orders`' signature and `venue_cancel` is `cancel_venue_order`'s.
    None, the engine's construction, reads the module's own at call time, so a test can replace it
    before any executor exists.
    """

    def __init__(
        self, *, client, gate: ExecutionGate, config: EngineConfig, clock=_utc_now, venue_orders=None, venue_cancel=None
    ) -> None:
        self._client = client
        # The Cache and the strategy id, taken here, inside `on_start`, where the strategy is not
        # borrowed, and read through these handles ever after: `client.cache` is a getter on the
        # strategy, and inside the dispatch of an event the strategy's own command publishes before
        # it returns -- `OrderPendingCancel` from `cancel_order`, `OrderInitialized` from
        # `submit_order` -- it raises `Already mutably borrowed`, the strategy's PyO3 cell being held
        # by that command, while the Cache itself is free and a handle taken earlier reads it
        # (tests/test_engine_executor.py measures both against a real engine).
        self._cache = client.cache
        self._strategy_id = client.strategy_id
        self._gate = gate
        self._config = config
        self._now = clock
        self._venue_orders = venue_orders
        self._venue_cancel = venue_cancel
        # The socket endpoints the client has reported down and not yet back, and the re-read pass's
        # tries left once the last of them is back: the pass runs on the next tick with nothing in
        # flight, and a read that fails spends one try.
        self._sockets_down: set[str] = set()
        self._reread_tries = 0
```

Replace, in `cli/engine/executor.py`, this block:

```python
            if not self._adopted:
                self._adopt_resting_orders(now)
            # No plan before the startup pass has run: until it has, no row is reconciled against the
            # venue, and the pass's one venue read must reach the venue before any order of this
            # process does (`read_venue_orders` says why).
            if self._plan is None and self._adopted:
                self._pickup(now)
```

with:

```python
            if not self._adopted:
                self._adopt_resting_orders(now)
            # Before the pickup, so a plan dropped during a cut waits one tick behind the re-cancel;
            # with nothing in flight, `read_venue_orders`' nonce terms.
            if self._reread_tries and self._nothing_in_flight():
                self._reread_pass(now)
            # No plan before the startup pass has run: until it has, no row is reconciled against the
            # venue, and the pass's one venue read must reach the venue before any order of this
            # process does (`read_venue_orders` says why).
            if self._plan is None and self._adopted:
                self._pickup(now)
```

Replace, in `cli/engine/executor.py`, this block:

```python
        except Exception:
            logger.exception("executor resting-age publish raised -- continuing")

    def _adopt_resting_orders(self, now: datetime) -> None:
```

with:

```python
        except Exception:
            logger.exception("executor resting-age publish raised -- continuing")

    # --- the sockets ---------------------------------------------------------------------------

    def on_socket_state(self, event) -> None:
        """The client's socket-state stream, the strategy's `on_socket_state` once it subscribed:
        `DISCONNECTED` names an endpoint down, `CONNECTED` one back. The re-read pass is owed on
        each return of an endpoint held down -- the data socket's, measured, whatever the execution
        socket reports, and a second socket's later return owes it again, an empty population
        consuming that arm with no read -- and runs on the tick, never here: it reads the Cache and
        the venue, which the tick does on the main thread with no loop running (`read_venue_orders`).
        A `CONNECTED` for no endpoint held down, the connect itself, owes nothing; a `DISCONNECTED`
        holds off a pass a mint armed (`_arm_reread_after_mint`), so nothing is read inside a cut,
        and the return arms it again. Arming once the set
        empties, both sockets resubscribed, was set aside: it rests on the execution client reporting
        `CONNECTED` under the string its `DISCONNECTED` carried, unmeasured offline, and an entry
        whose return never comes under that string would hold the pass off for the life of the
        process. Bookkeeping, never a submission: log and continue."""
        try:
            endpoint = str(getattr(event, "endpoint", "?"))
            state = getattr(event, "state", None)
            if state == SocketState.DISCONNECTED:
                self._sockets_down.add(endpoint)
                self._reread_tries = 0  # held until a socket is back, which arms the pass again
                logger.warning(
                    "socket %s is down -- an order whose terminal this engine mints meanwhile is re-read at the venue "
                    "once a socket is back",
                    endpoint,
                )
            elif state == SocketState.CONNECTED and endpoint in self._sockets_down:
                self._sockets_down.discard(endpoint)
                self._reread_tries = _REREAD_ATTEMPTS
                logger.warning(
                    "socket %s is back%s -- the re-read pass runs on the next tick with nothing in flight",
                    endpoint,
                    f" ({', '.join(sorted(self._sockets_down))} still down)" if self._sockets_down else " and none is down",
                )
        except Exception:
            logger.exception("executor socket-state handling raised -- continuing")

    def _arm_reread_after_mint(self) -> None:
        """The re-read pass's second trigger: a terminal this engine minted, on the plan's own order or
        on one the startup pass adopted, with no socket held down -- the adopted path's shape on this
        wheel, where each adopt-pass cancel's ack goes unapplied and the mint lands about 31 s on
        with the sockets up (drills G and A1). A mint while a socket is held down arms nothing: the
        socket's return does (`on_socket_state`), so nothing is read inside a cut -- F2's shape,
        whose mint landed 0.5 s before the socket's own deadline reported the cut and whose
        `DISCONNECTED` then holds the arm this sets. The cost is a stale entry, an endpoint whose
        `CONNECTED` never comes under its `DISCONNECTED`'s string, unmeasured offline, holding every
        later mint's settlement off until a startup inside the re-attach window; F2's next run
        measures the execution socket's name."""
        if not self._sockets_down:
            self._reread_tries = _REREAD_ATTEMPTS

    def _adopt_resting_orders(self, now: datetime) -> None:
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _reconcile_adopted_rows(self, rows: dict, venue_orders: dict | None) -> None:
        """The startup reconciliation sweep (spec 00098 D7): every open ledgered row, compared
        against its order's own quantity and status, before anything is classified.
```

with:

```python
    def _nothing_in_flight(self) -> bool:
        """No intent of this process live, and no order of it in flight in the Cache's own terms --
        `orders_inflight`, the set the library's in-flight check queries -- so the pass's signed
        requests race nothing of the execution client's: `_active` None alone leaves the startup
        pass's cancels of adopted orders, and a trip's, PENDING_CANCEL with no intent live. A Cache
        that cannot be read holds the pass, never a plan."""
        try:
            return self._active is None and not list(self._cache.orders_inflight(venue=_VENUE))
        except Exception:
            logger.exception("executor in-flight read raised -- the re-read pass waits for the next tick")
            return False

    def _reread_pass(self, now: datetime) -> None:
        """The startup sweep at one more moment -- after the sockets come back, or after a terminal
        this engine minted with no socket held down -- over every open row of the window whose Cache
        order was closed by a terminal this engine minted: the cancel the venue never acknowledged,
        on the plan's own order (drill F2: the REST cancel failed in the cut and the engine minted
        `OrderCanceled` while the order rested at Kraken) or on one the startup pass adopted (drills
        G and A1: the venue cancelled at the second asked and answered nothing this engine applied,
        the mint landing about 31 s on with the sockets up). The venue's report settles each: a
        closed report as at startup, an open one by
        a cancel, since the Cache's own order is the guess the venue must answer. The rows are read
        from the ledger and the Cache when the pass runs, not collected at the mint: F2's mint landed
        half a second before the socket's own deadline reported the cut, and a mint the ack deadline
        had already stranded lands detached. No intent is written: each is terminal at its mint or by
        the startup sweep, and a plan may be running beside the pass. A read that fails spends one
        try and the tick asks again; past the budget the rows keep their state and the line names
        the hand cancel and a restart, whose startup pass reads them. Wrapped whole: a raise here may
        never drop a plan."""
        try:
            rows = {
                row["client_order_id"]: (boundary, row)
                for boundary, row in open_submitted_rows(self._journal_dir, now)
                if self._minted_closed(row)
            }
            if not rows:
                self._reread_tries = 0
                return
            since = min(boundary for boundary, _ in rows.values()) - _VENUE_READ_MARGIN
            reports = (self._venue_orders or read_venue_orders)(since)
        except Exception:
            self._reread_tries -= 1
            if self._reread_tries:
                logger.warning("the re-read pass could not read the ledger or the venue -- asking again next tick", exc_info=True)
            else:
                logger.critical(
                    "the re-read pass could not read the ledger or the venue on %d ticks -- an order this engine minted "
                    "terminal may still rest at Kraken: cancel it by hand on Kraken's open-orders page, or restart the "
                    "engine, whose startup pass reads it",
                    _REREAD_ATTEMPTS,
                    exc_info=True,
                )
            return
        self._reread_tries = 0
        logger.warning("the re-read pass reads %d row(s) this engine minted terminal against the venue", len(rows))
        self._reconcile_adopted_rows(rows, {str(report.venue_order_id): report for report in reports}, recancel=True)

    def _minted_closed(self, row: dict) -> bool:
        """Whether the Cache's order for `row` was closed by a terminal this engine minted: the order
        is closed and its last event carries the `reconciliation` flag, which a minted terminal
        carries and which a venue answer the state machine then refused cannot replace. A Cache that
        cannot be read answers no."""
        try:
            order = self._cache_lookup(row, _row_venue_order_id(row))
        except Exception:
            return False
        return _minted_terminal(order)

    def _reconcile_adopted_rows(self, rows: dict, venue_orders: dict | None, *, recancel: bool = False) -> None:
        """The startup reconciliation sweep (spec 00098 D7): every open ledgered row, compared
        against its order's own quantity and status, before anything is classified -- and the
        re-read pass's, with `recancel`, over the rows this engine minted terminal.
```

Replace, in `cli/engine/executor.py`, this block:

```python
        take the same arms in `_reconcile_adopted_row`, so a closed-while-down order gets its repair,
        its terminal state and both trips exactly as a resting one does. A report that is still open
        is an order reconciliation dropped, which `_log_resting_outside_the_cache` logs CRITICAL.
```

with:

```python
        take the same arms in `_reconcile_adopted_row`, so a closed-while-down order gets its repair,
        its terminal state and both trips exactly as a resting one does. A report that is still open
        is an order reconciliation dropped, which `_log_resting_outside_the_cache` logs CRITICAL at
        startup; the re-read pass cancels it instead (`_recancel`), by txid on the bare client, since
        the row is this engine's own record of an order it placed or adopted and the Cache's closed
        copy is why no cancel through the strategy handle reaches it.
```

Replace, in `cli/engine/executor.py`, this block:

```python
                    report = venue_orders.get(venue_order_id)
                    if report is None:
                        self._mark_unmatched(
                            boundary, row, f"the venue's order read has no order {venue_order_id}", open_row=True, critical=True
                        )
                        continue
                    _log_resting_outside_the_cache(_row_label(row, venue_order_id), report)
```

with:

```python
                    report = venue_orders.get(venue_order_id)
                    if report is None:
                        self._mark_unmatched(
                            boundary, row, f"the venue's order read has no order {venue_order_id}", open_row=True, critical=True
                        )
                        continue
                    if recancel and report.order_status not in _ADOPTED_TERMINAL_STATES:
                        self._recancel(boundary, row, venue_order_id, report)
                        continue
                    _log_resting_outside_the_cache(_row_label(row, venue_order_id), report)
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _mark_unmatched(self, boundary: datetime, row: dict, what: str, *, open_row: bool, critical: bool = False) -> None:
```

with:

```python
    def _recancel(self, boundary: datetime, row: dict, venue_order_id: str, report) -> None:
        """The re-read pass's cancel of an order the venue still reports open: the report's fills
        repair the row first, through the arms and trips a startup's repair takes, then the cancel
        goes out by txid on the bare client, and its return writes the row `canceled` with a
        `recancelled` event -- the client reads no `count` from the venue's answer and the library
        drops the stream's later event for an order it already holds closed, so `canceled` says the
        pass read the order open and its cancel returned, and a fill landing between the two is on
        Kraken's closed orders and not in the row, which the page has the operator read. A cancel
        that raises -- the cut not over for REST, or a refusal the venue phrases as an error --
        leaves the row and names the hand cancel, the refused-cancel arm's precedent. No counter
        moves for the re-cancel and no intent is written; a closed report that completes the row
        counts `filled` through `_reconcile_adopted_row`'s arm, the startup's rule."""
        label = _row_label(row, venue_order_id)
        self._reconcile_adopted_row(
            boundary, row, float(report.filled_qty), report.order_status, order_id=None, venue_order_id=venue_order_id
        )
        try:
            (self._venue_cancel or cancel_venue_order)(venue_order_id, str(report.instrument_id))
        except Exception:
            logger.critical(
                "the re-read pass's cancel of %s raised or was refused -- the order may still rest at Kraken: cancel it "
                "by hand on Kraken's open-orders page",
                label,
                exc_info=True,
            )
            return
        event = {"event": "recancelled", "at": self._now().isoformat(), "venue_order_id": venue_order_id}
        try:
            update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state="canceled", event=event)
        except Exception:
            logger.critical("the re-cancel of %s could not be journaled -- its row keeps the state it has", label, exc_info=True)
            return
        row["state"] = "canceled"
        logger.warning(
            "re-cancelled %s -- it rested at Kraken (%s) after a terminal this engine minted; its row reads canceled",
            label,
            report.order_status.name,
        )

    def _mark_unmatched(self, boundary: datetime, row: dict, what: str, *, open_row: bool, critical: bool = False) -> None:
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _cached_order(self, row: dict, venue_order_id: str | None):
        """The Cache's order for `row`: by the id this engine minted, then by the txid the row
        recorded. The second lookup is the one every order a restart reconciled needs, since the
        adapter's reports carry no client order id and reconciliation names the order by its txid;
        it goes through the Cache's own venue-order-id index rather than an assumption about how
        reconciliation names what it adopts. `cache.order` serves closed orders as readily as open
        ones, and both accessors are typed and refuse a plain str."""
        cache = self._cache
```

with:

```python
    def _cached_order(self, row: dict, venue_order_id: str | None):
        """The Cache's answer for `row`: its order (`_cache_lookup`), unless that order was closed by
        a terminal this engine minted (`_minted_terminal`), when the Cache holds this engine's own
        guess and answers nothing, so the venue is asked. At startup no order is closed that way --
        reconciliation adopts open orders, and the void it can mint is not one of those terminals --
        so the startup sweeps read as before."""
        order = self._cache_lookup(row, venue_order_id)
        return None if _minted_terminal(order) else order

    def _cache_lookup(self, row: dict, venue_order_id: str | None):
        """The Cache's order for `row`: by the id this engine minted, then by the txid the row
        recorded. The second lookup is the one every order a restart reconciled needs, since the
        adapter's reports carry no client order id and reconciliation names the order by its txid;
        it goes through the Cache's own venue-order-id index rather than an assumption about how
        reconciliation names what it adopts. `cache.order` serves closed orders as readily as open
        ones, and both accessors are typed and refuse a plain str."""
        cache = self._cache
```

Replace, in `cli/engine/executor.py`, this block:

```python
def _venue_order_id_of(order_or_event) -> str | None:
```

with:

```python
def _minted_terminal(order) -> bool:
    """Whether `order` was closed by a terminal the execution engine minted rather than received: it
    is closed and an event in its history is one of `_RECONCILED_TERMINALS` carrying the
    `reconciliation` flag -- the set the two minted arms key on; an `OrderFillVoided` carries the
    flag from the venue's own report and is not one. The history, not the last event: the state
    machine refuses a venue's later cancel ack of an order already closed but applies a later fill,
    which leaves a whole fill FILLED and a partial one CANCELED with `last_event` `OrderFilled`, so a
    last-event test would drop from the re-read pass the maker order that part-filled during the
    cut, the one it exists for. A stand-in without those attributes reads as not minted."""
    if order is None or not bool(getattr(order, "is_closed", False)):
        return False
    events = getattr(order, "events", None)
    return any(
        type(event).__name__ in _RECONCILED_TERMINALS and bool(getattr(event, "reconciliation", False))
        for event in (events() if callable(events) else ())
    )


def _venue_order_id_of(order_or_event) -> str | None:
```

Replace, in `cli/engine/executor.py`, this block:

```python
                "%s for %s was reconciled, not received -- no venue answer reached this engine; its row reads ambiguous "
                "until the venue's own report settles it",
                type(event).__name__,
                getattr(event, "client_order_id", "?"),
            )
            return "ambiguous"
```

with:

```python
                "%s for %s was reconciled, not received -- no venue answer reached this engine; its row reads ambiguous "
                "until the re-read pass settles it from the venue's own report",
                type(event).__name__,
                getattr(event, "client_order_id", "?"),
            )
            self._arm_reread_after_mint()
            return "ambiguous"
```

Replace, in `cli/engine/executor.py`, this block:

```python
        settled, the entry stays in `_attached` for a fill that can still arrive, and the venue's own
        report settles the row -- a startup inside the re-attach window reads it against the order's
        own status; until then the pages have the operator read Kraken's open orders, which tell a
```

with:

```python
        settled, the entry stays in `_attached` for a fill that can still arrive, and the venue's own
        report settles the row -- the re-read pass's on the next tick with nothing in flight
        (`_arm_reread_after_mint`), or a startup's inside the re-attach window where the pass could
        not read; until then the pages have the operator read Kraken's open orders, which tell a
```

Replace, in `cli/engine/executor.py`, this block:

```python
            self._update_row(active, state="ambiguous", event=payload)
            self._strand_ambiguous(active, f"{name} was reconciled, not received -- the venue never answered")
```

with:

```python
            self._update_row(active, state="ambiguous", event=payload)
            self._arm_reread_after_mint()  # the plan's own order: F2's shape, where the cut's DISCONNECTED then holds it
            self._strand_ambiguous(active, f"{name} was reconciled, not received -- the venue never answered")
```

Replace, in `cli/engine/node.py`, this block:

```python
    The four executor forwarders below are the ONLY inputs the order path has, and each carries
    exactly what nautilus routes to this strategy. `on_order_event` in particular is the
```

with:

```python
    The five executor forwarders below are the ONLY inputs the order path has, and each carries
    exactly what nautilus routes to this strategy. `on_socket_state` is the client's socket-state
    stream, opt-in through `subscribe_socket_state` in `on_start`, which the executor's reconnect
    pass keys on. `on_order_event` in particular is the
```

Replace, in `cli/engine/node.py`, this block:

```python
            self._executor = self._executor_factory(self)
            self.clock.set_timer(_EXEC_TIMER_NAME, timedelta(seconds=_TICK_SECONDS), callback=self._on_exec_tick)
```

with:

```python
            self._executor = self._executor_factory(self)
            self.clock.set_timer(_EXEC_TIMER_NAME, timedelta(seconds=_TICK_SECONDS), callback=self._on_exec_tick)
            # Every client and endpoint: the executor keys on the set of endpoints down, never on a name.
            self.subscribe_socket_state()
```

Replace, in `cli/engine/node.py`, this block:

```python
    def on_order_event(self, event) -> None:
        if self._executor is not None:
            self._executor.on_order_event(event)

    def _on_external_order_event(self, event) -> None:
```

with:

```python
    def on_order_event(self, event) -> None:
        if self._executor is not None:
            self._executor.on_order_event(event)

    def on_socket_state(self, event) -> None:
        if self._executor is not None:
            self._executor.on_socket_state(event)

    def _on_external_order_event(self, event) -> None:
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **Nothing during a hold under ≈7 minutes, then [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) (critical, `logs`) after the reconnect**, on the lines the ring held (below). The silence during the hold is a coverage finding, not a quiet fleet: every rule that would notice keys on the exporter or on the log stream, and all of them are slower than the entire behaviour this drill measures (no count command: `infra/grafana/alerts.yaml`'s rules on the engine's series are the set, and no entry reads it).
```

with:

```markdown
- **Nothing during a hold under ≈7 minutes, then [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) (critical, `logs`) after the reconnect**, on the lines the ring held (below). The silence during the hold is a coverage finding, not a quiet fleet: every rule that would notice keys on the exporter or on the log stream, and all of them are slower than the entire behaviour this drill measures (no count command: `infra/grafana/alerts.yaml`'s rules on the engine's series are the set, and no entry reads it).
- **The executor's own re-cancel, on its first tick after the reconnect with nothing in flight**: `re-cancelled <id> (Kraken <txid>) -- it rested at Kraken (<status>) after a terminal this engine minted; its row reads canceled` at WARNING, which pages nothing. Its two CRITICAL lines page [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) after the reconnect as the mint's lines do: `the re-read pass could not read the ledger or the venue on 3 ticks` and `the re-read pass's cancel of <id> raised or was refused`; [`engine.md#zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) step 2 says what each asks for (no count command: the lines are `_reread_pass`'s and `_recancel`'s in `cli/engine/executor.py`, and whether Kraken's REST edge answers after the socket's return is the venue's act).
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
3. **Read Kraken's open orders by hand.** The order may still be resting there and nothing in this engine will cancel it: the intent is terminal, so a hand-placed kill file sweeps nothing.
```

with:

```markdown
3. **Read the engine log for the re-cancel, then Kraken's open orders by hand.** On its first tick after `Reconnect succeeded` with nothing in flight, the executor's re-read pass reads the venue for the row the mint closed and cancels the order by its txid on the bare client, logging `re-cancelled <id> (Kraken <txid>) -- it rested at Kraken (<status>) after a terminal this engine minted`; Kraken's open orders then no longer carry it. The row reads `canceled` with a `recancelled` event, and the intent stays `ambiguous`: it was terminal at the mint, and the row is the re-cancel's record. Read a `recancelled` row against Kraken's closed orders and the positions page: the cancel's answer is not read, so a fill landing between the pass's read and its cancel closes the row `canceled` all the same, with the fill on Kraken's page and not in the row. A hand-placed kill file still sweeps nothing on this path.
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
4. **Clear it deliberately.** A direct cancel in the Kraken web UI always works```

with:

```markdown
4. **Clear it deliberately when the pass did not.** A CRITICAL `the re-read pass could not read the ledger or the venue on 3 ticks` or `the re-read pass's cancel of <id> raised or was refused` line means the order may still rest, and so does the pass's own line missing three ticks after `Reconnect succeeded`. A direct cancel in the Kraken web UI always works```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
If the property you wanted is "the order dies with the socket", that is re-cancel-on-reconnect, a build-sequence item not yet delivered<!-- T0018 -->, never an expectation to write against this drill.
```

with:

```markdown
"The order dies with the socket" is re-cancel-on-reconnect, delivered by the executor's re-read pass<!-- T0018 -->: this drill measures it — the time from `Reconnect succeeded` to the pass's line, and to the order leaving Kraken's open orders — and records a pass whose line did not come as the finding it is.
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
Entry `F2`: how long the order rested at the venue, whether the intent journaled `ambiguous` inside the derived ~60 s, which page fired if any, and how the order was finally cleared.```

with:

```markdown
Entry `F2`: how long the order rested at the venue, whether the intent journaled `ambiguous` inside the derived ~60 s, the endpoint on each `socket <endpoint> is down` and `socket <endpoint> is back` line — the execution socket's name, and whether its return arrives under the string its drop carried, are unmeasured offline — the re-read pass's line and its time after `Reconnect succeeded` — or the CRITICAL line that says it could not read or cancel — and, where Kraken's closed orders show the order gone before the pass's line, which of the two the pass logged, `re-cancelled …` or `… raised or was refused` with the venue's text under it: Kraken's answer to a cancel of a txid already closed, unmeasured, to be recorded in `docs/reference/adapter-verification/`; which page fired if any, and how the order was finally cleared.```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
```

with:

```markdown
   - **`the re-read pass could not read the ledger or the venue on 3 ticks …`** or **`the re-read pass's cancel of … raised or was refused`**: the executor's re-read pass — run on its next tick with nothing in flight after a socket's return, or after a terminal it minted with no socket held down — re-reads at the venue each row it minted terminal and cancels what still rests, and could not read on three ticks or could not cancel; the order may still rest at Kraken, its row `ambiguous`. Cancel it by hand on Kraken's open-orders page, or restart the engine inside the inter-cycle gap, whose startup pass reads the row (the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names the window). A row the pass did close reads `canceled` with a `recancelled` event, and is read against Kraken's closed orders and positions: the cancel's answer is not read, so a fill between the pass's read and its cancel is on Kraken's page and not in the row. No disarm is owed for these lines alone (no count command: the lines are `_reread_pass`'s and `_recancel`'s in `cli/engine/executor.py`, and the venue's answer is the venue's act).
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
both moving means the venue or the host's network moved; the engine alone moving is the engine's problem.
```

with:

```markdown
both moving means the venue or the host's network moved; the engine alone moving is the engine's problem. The executor's re-read pass follows on its next tick with nothing in flight: it re-reads at the venue each order whose terminal it minted during the drop and cancels what still rests, logging `re-cancelled … after the reconnect`; drill F2's procedure reads it.
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
which its entry in Kraken's closed orders, the positions page and the row's `filled_qty` tell apart. That is the right answer```

with:

```markdown
which its entry in Kraken's closed orders, the positions page and the row's `filled_qty` tell apart; the pass runs after the mint with the sockets up, or after the sockets' return where the mint fell inside a cut, and cancels what still rests, so read its `re-read pass reads … row(s)` and `re-cancelled …` lines before the hand cancel (drills A1, G and F2 read them). That is the right answer```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
3. **The ledger**, with the probe window's ledger read: the order's row carries `canceled`, or `ambiguous` where the venue's acknowledgement did not arrive and the engine minted the cancel's terminal for itself — step 4's read then decides it: an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart (drill G's record says how that reads) — `filled_qty 0.0`, and no `fill` lines at all;```

with:

```markdown
3. **The ledger**, with the probe window's ledger read: the order's row carries `canceled` — on the venue's own acknowledgement, or settled from the venue's report by the executor's re-read pass on its next tick with nothing in flight after the engine minted the cancel's terminal, the mint's `OrderCanceled` event carrying `reconciliation: true` — `filled_qty 0.0`, and no `fill` lines at all; a row still `ambiguous` a minute after the mint is the finding, with the pass's CRITICAL line or none of its lines saying why, and step 4's read then decides it: an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart (drill G's record says how that reads);```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
the row `canceled`, or `ambiguous` where the engine minted the cancel's terminal for itself (the Record says how that reads, and an order still resting on Kraken's open-orders page is cancelled by hand there);```

with:

```markdown
the row `canceled` — on the venue's own acknowledgement, or settled from the venue's report by the executor's re-read pass on its next tick with nothing in flight after the engine minted the cancel's terminal, the mint's event carrying `reconciliation: true` (the Record says how that reads; a row still `ambiguous` a minute after the mint is the finding, and an order still resting on Kraken's open-orders page is cancelled by hand there);```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **The row after the pass's cancel** reads `canceled` on the venue's own acknowledgement and `ambiguous` on one the engine minted for itself after its in-flight budget — the cancel executed at Kraken with its acknowledgement lost, or did not reach it, and Kraken's open orders are what tell those apart: an order still resting there is cancelled by hand on that page, one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart, and an `ambiguous` row is settled by a startup inside the re-attach window, which the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names with what the entry records past it. The intent reads `revoked` in both cases,```

with:

```markdown
- **The row after the pass's cancel** reads `canceled` on the venue's own acknowledgement — E's shape, the ack inside about 43 ms — and `ambiguous` on one the engine minted for itself after its in-flight budget, then `canceled` once the executor's re-read pass has settled it from the venue's own report on its next tick with nothing in flight, the `re-read pass reads 1 row(s) this engine minted terminal against the venue` line: G's and A1's shape, where the cancel executed at Kraken at the second asked and its acknowledgement was not applied, and on this wheel the shape of each adopt-pass cancel measured, five of five. A report still open there is re-cancelled by the pass on the bare client, `re-cancelled …` at WARNING, the cancel having not reached the venue; a row still `ambiguous` a minute after the mint, with the pass's CRITICAL line or none of its lines, is the finding, and Kraken's open orders decide it by hand: an order still resting there is cancelled on that page, one that is gone was cancelled or filled, which Kraken's closed orders and the row's `filled_qty` tell apart, and a startup inside the re-attach window settles the row, which the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names with what the entry records past it. The intent reads `revoked` in each case,```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
on an order the startup pass adopted, the row reads `ambiguous` instead, until a startup inside the re-attach window settles it against the venue (the `Three terminal outcomes` paragraph below names the window and what the entry records past it),```

with:

```markdown
on an order the startup pass adopted, the row reads `ambiguous` instead, until the executor's re-read pass settles it from the venue's own report on its next tick with nothing in flight, or a startup inside the re-attach window where the pass could not read (the `Three terminal outcomes` paragraph below names the window and what the entry records past it),```

- [ ] **Step 5: Run the three files and watch them pass**

Run: `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider; uv run pytest tests/test_engine_node.py tests/test_engine_stub_fidelity.py -q -p no:cacheprovider`
Expected: `302 passed`, then `143 passed, 2 skipped`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_engine_execledger.py tests/test_engine_node.py tests/test_engine_metrics.py tests/test_engine_executor.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_count_list.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py tests/test_kraken_fixture_mint_loopback.py tests/test_kraken_window_reads.py tests/test_kraken_wheel_contract.py tests/test_engine_flatten.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `2189 passed, 3 skipped` when this plan was written, the executor union's `1973 passed, 2 skipped` with the loopback venue's four other consumers, `216 passed, 1 skipped`, the skips `tests/test_engine_node.py`'s two live-venue gates and one of the loopback consumers' own.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. `mdformat` covers the three runbook pages.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/executor.py cli/engine/node.py infra/runbooks/drills-order-path.md infra/runbooks/engine-procedures.md infra/runbooks/engine.md tests/kraken_loopback.py tests/test_engine_executor.py tests/test_engine_node.py tests/test_engine_stub_fidelity.py
git commit -m "fix(engine): the re-read pass settles the rows this engine minted terminal from the venue's answer, after a cut's return and after a mint

Measured on 2026-09-26, drill F2: the engine container lost its network with a rest-hold order
resting, its one cancel failed on REST, the engine minted OrderCanceled for itself and the executor
wrote the intent and the row ambiguous; the sockets came back four minutes later and nothing
re-cancelled the order, which rested at Kraken for eight minutes until a hand cancel. The strategy
subscribes to the client's socket-state stream and forwards it to the executor, which keeps the set
of endpoints reported down and, on each one's return, runs the startup's row sweep on its next
tick with nothing in flight, no intent live and no order of this process in flight in the Cache,
over every open row of the window whose Cache order a minted terminal closed: the venue's report
settles a closed one as a startup would, and one still open is cancelled by txid on a bare client,
since the strategy handle refuses an order it holds closed, the cancel's return writing the row
canceled with a recancelled event. The mint is read off the order's history, since the state
machine applies a fill to an order it holds minted-CANCELED and the last event is then the fill. A
read that fails is tried on three ticks, then the line names the hand cancel and a restart; a
cancel that raises leaves the row and names it too. No intent is written, and no counter moves for
the re-cancel: a report that completes the row counts filled as a restart's sweep does. The Cache's
answer for an order so closed is withheld from the startup sweeps' lookup too, where reconciliation
adopts open orders and the void it can mint is not one of those terminals. Drill F2's Must fire,
operator action and record, the error-logs runbook's classes and the socket section, and the
procedures page's minted-terminal step say so.

The pass has a second trigger: a terminal this engine minted while no socket is held down arms it,
the adopted path's shape on this wheel, where drills G and A1 measured Kraken cancelling at the
second asked, applying no answer, and the engine minting the terminal about 31 s on with the
sockets up, so the row settles from the venue's report on the next tick and the mint's line, a
WARNING, pages nothing; a socket reported down clears the arm, so a mint inside a cut reads nothing
until the return arms the pass; and the lines and pages name the pass for what it does, the re-read
pass, and not for the cut.

Cases: F2's shape re-cancelled and settled with the intent left ambiguous and no counter moved; the
adopted path's twin with the intent left as the sweep wrote it; a closed report settling the row
with no cancel, and a filled one counting filled; a read failing on three ticks then left to the
hand or a restart, with a later return arming the pass again; a kept reducer's row read nowhere;
the connect's own CONNECTED arming nothing and each of two endpoints arming on its own return; the
pass waiting for a tick with nothing in flight, and while a startup cancel of an adopted order is
still unanswered; a partial fill applied after the mint keeping the row in the pass; a refused
cancel leaving the row; the bare client's cancel on the loopback venue sending the txid, returning
on count 1 and count 0 alike, raising on the venue's refusal and refusing without credentials; the
strategy's subscription and fifth forwarder; a minted cancel of an adopted opener with the sockets
up settled from the venue on the next tick with no cancel, no counter and no CRITICAL; a socket
reported down holding the arm a mint set until the return; a mint while a socket is held down
arming nothing, and the return arming the pass.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with sixteen probes, then record their verdicts by a message-only amend**

The executor's control disarms the re-cancel arm, so the re-cancel cases fail. The mutations, in order: the pass is never armed; the pass runs with an intent live or an order in flight; the pass runs with an adopted order's cancel still in flight; every open row is swept, minted or not; the Cache answers for an order a minted terminal closed; a void closed by the venue's own report counts as minted; the mint is read off the last event alone, not the history; a failed read never gives up; a failed read gives up at once; the cancel is skipped, so the row is written on nothing; the connect's own `CONNECTED` arms the pass; a mint on the adopted path arms nothing; a mint on the plan's own order arms nothing; a socket reported down leaves a mint's arm; a mint arms the pass while a socket is held down. The node's control drops the subscription, which the `on_start` case pins, and its mutation makes the forwarder inert. Each executor `-k` selects 18 of the file's 302 cases, the node's 3 of its 87:

```bash
K="reconnect or reread or re_cancel or socket_reported_down or nothing_of_this_process or cancel_venue_order or withdrawn_fill_on_a_row_this_engine_closed or sockets_up or holds_the_re_read or held_down_arms_nothing"
C='s/if recancel and report.order_status not in _ADOPTED_TERMINAL_STATES:/if False:/'
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/self._reread_tries = _REREAD_ATTEMPTS/self._reread_tries = 0/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/if self._reread_tries and self._nothing_in_flight():/if self._reread_tries:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/return self._active is None and not list(self._cache.orders_inflight(venue=_VENUE))/return self._active is None/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^                if self._minted_closed(row)$/                if True/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/return None if _minted_terminal(order) else order/return order/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/type(event).__name__ in _RECONCILED_TERMINALS and bool/True and bool/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/for event in (events() if callable(events) else ())/for event in (events()[-1:] if callable(events) else ())/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/self._reread_tries -= 1/pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/self._reread_tries -= 1/self._reread_tries = 0/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            (self._venue_cancel or cancel_venue_order)(venue_order_id, str(report.instrument_id))$/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/elif state == SocketState.CONNECTED and endpoint in self._sockets_down:/elif state == SocketState.CONNECTED:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            self._arm_reread_after_mint()$/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            self._arm_reread_after_mint()  # the plan.s own order.*$/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^                self._reread_tries = 0  # held until a socket is back.*$/                pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if not self._sockets_down:$/        if True:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/node.py \
  --control 's/^            self.subscribe_socket_state()$/            pass/' \
  --mutation 's/^            self._executor.on_socket_state(event)$/            pass/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "socket_state or registers_the_exec_tick or no_exec_tick"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <that file>` — the Global Constraints' rule, never `--amend -m "…"`, inside which the shell runs each backticked name below as a command:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/executor.py`, control the re-cancel arm
disarmed so the re-cancel cases fail, through
`-k "reconnect or reread or re_cancel or socket_reported_down or nothing_of_this_process or cancel_venue_order or withdrawn_fill_on_a_row_this_engine_closed or sockets_up or holds_the_re_read or held_down_arms_nothing"`:
the pass never armed, KILLED, control proven; the pass run with an intent live or an order in
flight, KILLED, control proven; the pass run with an adopted order's cancel in flight, KILLED,
control proven; every open row swept, KILLED, control proven; the Cache answering for an order a
minted terminal closed, KILLED, control proven; a venue-reported void counted as minted, KILLED,
control proven; the mint read off the last event alone, KILLED, control proven; a failed read never
giving up, KILLED, control proven; a failed read giving up at once, KILLED, control proven; the
cancel skipped, KILLED, control proven; the connect's own CONNECTED arming the pass, KILLED,
control proven; a mint on the adopted path arming nothing, KILLED, control proven; a mint on the
plan's own order arming nothing, KILLED, control proven; a socket reported down leaving a mint's
arm, KILLED, control proven; a mint arming the pass while a socket is held down, KILLED, control
proven; over `cli/engine/node.py`, control the subscription dropped: the forwarder inert,
KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` — Expected: `1`, the verdict naming the script.

---

### Task 5: The gate's gauges are republished once a minute while no plan runs

This task is the spec's fifth cluster (D22 to D25), on nothing but the executor's tick; it stands whatever is struck.

What this task decides, where the spec leaves it open:

- The stamp is `_gate_evaluated_at`, set by every `_evaluate` and by the constructor to its clock, so the first idle refresh comes a period after construction, the process's startup evaluation having published moments before; a clock stepping back delays the refresh by the step and forces nothing.
- `_refresh_gate` is the tick's last act, after the resting-age publish, wrapped as that publish is.
- `test_an_idle_tick_reads_no_gate_at_all` becomes the bounded claim with the same plan-file half; `test_the_idle_tick_never_evaluates_tracking` keeps its count, its three ticks preceding the period's first elapse, and says so.
- The heartbeat stays the boundary path's: `_ExecGauges.update` takes `heartbeat`, the hook contract carries it, and the refresh alone passes False, so `zcrypto_exec_last_evaluation_timestamp_seconds` moves at startup, in the boundary sink and on a running plan's evaluations as before, and `zcrypto-engine-exec-not-evaluated` keeps watching the sink and the exec record it writes first; the freeze test in `tests/test_engine_metrics.py` runs the refresh beside the raising sink and reads both halves by value.
- The surfaces naming the gauges' idle cadence or the six gauges freezing together, each re-trued to the refresh and to the heartbeat's exemption from it -- the family, enumerated so the next reader inherits it: `infra/runbooks/engine.md`'s arm-file step 2, kill-tripped step 3, and the exec-not-evaluated section's meaning paragraph and step 2; `infra/runbooks/drills-order-path.md`'s derivation rule, E's precondition and E's step 4; `infra/runbooks/engine-procedures.md`'s no-alert bullet; `infra/grafana/alerts.yaml`'s comment and summary on `zcrypto-engine-exec-not-evaluated`; `infra/grafana/engine-dashboard.json`'s venue-status and heartbeat tiles; `tests/test_infra_alert_rules.py`'s `NOT_A_FAULT_SIGNAL` entry; `_ExecGauges`' and `_make_exec_sink`'s docstrings in `cli/engine/command.py`; `_trip_kill`'s publish comment in the executor.

**Files:**
- Modify `cli/engine/executor.py` (`_GATE_REFRESH` after `_REREAD_ATTEMPTS`; `set_executor_hooks`' docstring and `_publish`'s `heartbeat`; `_gate_evaluated_at` in `__init__`; `_evaluate`'s docstring, stamp and `heartbeat`; `on_timer`'s refresh line; `_refresh_gate` after `_publish_resting_age`; `_trip_kill`'s publish comment)
- Modify `cli/engine/command.py` (`_ExecGauges`' docstring's first sentence; `update`'s `heartbeat`; `_make_exec_sink`'s docstring)
- Modify `infra/runbooks/engine.md` (the arm-file runbook's step 2; the kill-tripped runbook's step 3; the exec-not-evaluated runbook's meaning paragraph and step 2)
- Modify `infra/runbooks/drills-order-path.md` (the derivation rule on the gate's gauges; E's resting-plan precondition; E's step 4)
- Modify `infra/runbooks/engine-procedures.md` (the no-alert bullet on the external-events counter)
- Modify `infra/grafana/alerts.yaml` (`zcrypto-engine-exec-not-evaluated`'s comment and summary)
- Modify `infra/grafana/engine-dashboard.json` (the venue-status tile's and the heartbeat tile's descriptions)
- Test: `tests/test_engine_executor.py` (`test_an_idle_tick_reads_no_gate_at_all` replaced by two cases; `test_the_idle_tick_never_evaluates_tracking`'s docstring and comment; the verdict-hook case's hook)
- Test: `tests/test_engine_metrics.py` (the freeze test, replaced by one that runs the idle refresh beside the raising sink)
- Test: `tests/test_infra_alert_rules.py` (the `NOT_A_FAULT_SIGNAL` entry's comment on the external-events counter)

**Interfaces:**
- Consumes: `_executor`, `_gate`, `_drop_plan`, `_plan_dict`, `_kill_file`, `CountingGate`, `RecordingMetrics`, `StubClient`, `set_executor_hooks`, `GateLevel`, `NOW`, `timedelta` from the executor test module's existing names; `command`, `_ExecGauges`, `_sink_result`, `_raise`, `_staleness_threshold_seconds`, `ExecutionGate`, `VenueStatus`, `EngineConfig`, `CollectorRegistry`, `types`, `datetime`, `timedelta` in the metrics test module, and `exec_dir`, `KILL_FILE` from `cli.engine.execgate`; `_publish`, `_publish_resting_age` in the executor.
- Produces: `_GATE_REFRESH`; `ProbeExecutor._gate_evaluated_at`, `._refresh_gate(now)` and `._evaluate(now, *, heartbeat=True)`; `_publish(verdict, evaluated_at, *, heartbeat=True)`; the hook contract `publish_verdict(verdict, evaluated_at=..., heartbeat=...)`; `_ExecGauges.update(verdict, *, evaluated_at, heartbeat=True)`.

- [ ] **Step 1: Confirm Task 4 has landed and the executor is at the spec's basis**

Run: `grep -c 'on_socket_state' cli/engine/executor.py; grep -c '_GATE_REFRESH' cli/engine/executor.py`
Expected: `2` then `0`. A first count other than 2 means Task 4 is not on the branch; a second other than 0 means the refresh already exists; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_executor.py`**

Replace, in `tests/test_engine_executor.py`, this block:

```python
def test_an_idle_tick_reads_no_gate_at_all(tmp_path):
    """The cheap-lstat claim: with no plan file there is no gate evaluation and therefore no venue
    read. The second half is what stops this passing vacuously against an executor that never
    evaluates anything."""
    gate = CountingGate()
    ex = _executor(tmp_path, gate=gate)

    ex.on_timer(NOW)
    assert gate.calls == 0

    _drop_plan(tmp_path, _plan_dict())
    ex.on_timer(NOW)
    assert gate.calls > 0
```

with:

```python
def test_an_idle_tick_reads_no_gate_inside_the_refresh_period_and_one_per_period_past_it(tmp_path):
    """The cheap-lstat claim, bounded: with no plan file there is no gate evaluation and no venue
    read inside the refresh period, then one per period -- the tick a plan runs on evaluates anyway.
    The plan-file half is what stops this passing vacuously against an executor that never
    evaluates anything."""
    gate = CountingGate()
    ex = _executor(tmp_path, gate=gate)

    ex.on_timer(NOW)
    ex.on_timer(NOW + timedelta(seconds=55))
    assert gate.calls == 0
    ex.on_timer(NOW + timedelta(seconds=60))
    ex.on_timer(NOW + timedelta(seconds=65))
    assert gate.calls == 1
    ex.on_timer(NOW + timedelta(seconds=120))
    assert gate.calls == 2

    _drop_plan(tmp_path, _plan_dict(created_at=NOW + timedelta(seconds=120)))
    ex.on_timer(NOW + timedelta(seconds=125))
    assert gate.calls > 2


def test_a_kill_file_removed_on_an_idle_engine_is_republished_within_the_refresh_period(tmp_path):
    """Drill D, measured 2026-09-26: the boot published the switch as tripped, the file went, no
    intent was live, and the gauge held the boot's reading to the next boundary, so the rule paged a
    switch gone four minutes. The idle tick now re-evaluates the gate once a minute and the publish
    hook -- `_ExecGauges.update` in production -- sees the file gone within it, with `heartbeat`
    False, so the staleness rule's series stays the boundary path's; the refresh journals nothing."""
    published = []
    set_executor_hooks(
        publish_verdict=lambda verdict, *, evaluated_at, heartbeat: published.append((evaluated_at, verdict, heartbeat))
    )
    ex = _executor(tmp_path, gate=_gate(tmp_path, GateLevel.NONE))  # the kill file stands at the boot

    ex.on_timer(NOW)
    _kill_file(tmp_path).unlink()
    ex.on_timer(NOW + timedelta(seconds=5))
    assert published == []
    ex.on_timer(NOW + timedelta(seconds=60))

    assert [(at, v.level, v.inputs["kill_file"], hb) for at, v, hb in published] == [
        (NOW + timedelta(seconds=60), GateLevel.FULL, False, False)
    ]
    assert not (tmp_path / "journal").exists()
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    def _publish(verdict, *, evaluated_at):
        seen.append((verdict.level, evaluated_at))
        raise RuntimeError("gauge registry is gone")
```

with:

```python
    def _publish(verdict, *, evaluated_at, heartbeat):
        seen.append((verdict.level, evaluated_at, heartbeat))
        raise RuntimeError("gauge registry is gone")
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    assert seen and all(level == GateLevel.FULL for level, _ in seen)
```

with:

```python
    assert seen and all(level == GateLevel.FULL and heartbeat for level, _, heartbeat in seen)  # a plan's evaluations stamp it
```

Replace, in `tests/test_engine_metrics.py`, this block:

```python
def test_a_raising_ledger_writer_freezes_the_heartbeat_and_the_staleness_condition_goes_true(tmp_path, monkeypatch):
    """The monitoring-gap discharge, read by VALUE: the sink writes the ledger BEFORE any gauge, so
    a persistently failing `write_exec_record` starves
    `zcrypto_exec_last_evaluation_timestamp_seconds` and the deployed staleness rule's condition
    goes true. That ordering is the whole reason the gap is monitored rather than merely documented
    -- reverse it and the ledger could fail silently for days behind a heartbeat that keeps ticking."""
    registry = CollectorRegistry()
    gate = ExecutionGate(
        armed_in_config=False,
        state_dir=tmp_path,
        venue_reader=lambda *, now, opener=None: VenueStatus(status="online", ok=True, observed_at=now),
    )
    exec_gauges = _ExecGauges(registry)
    t0 = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    sink = command._make_exec_sink(gate, tmp_path / "journal", None, exec_gauges, None)

    sink(_sink_result(t0), t0, 1.0)  # one healthy cycle: the heartbeat is t0
    assert registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") == t0.timestamp()

    monkeypatch.setattr(command, "write_exec_record", _raise)
    t1 = t0 + timedelta(hours=8)
    try:
        sink(_sink_result(t1), t1, 1.0)
    except OSError:
        pass  # in production cycle.py's _update_metrics swallows exactly this raise -- same effect

    frozen = registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds")
    assert frozen == t0.timestamp(), "the heartbeat moved past a cycle whose ledger record was never written"
    assert t1.timestamp() - frozen > _staleness_threshold_seconds()
```

with:

```python
def test_a_raising_ledger_writer_freezes_the_heartbeat_while_the_idle_refresh_moves_the_readings_and_the_staleness_condition_goes_true(
    tmp_path, monkeypatch
):
    """The monitoring-gap discharge, read by VALUE: the sink writes the ledger BEFORE any gauge, so
    a persistently failing `write_exec_record` starves
    `zcrypto_exec_last_evaluation_timestamp_seconds` and the deployed staleness rule's condition
    goes true -- while the executor's idle refresh, on the hook `run()` installs, keeps the five
    readings moving and leaves the heartbeat alone. The ordering and the exemption are together the
    reason the gap is monitored rather than merely documented: reverse the first and the ledger
    could fail silently for days behind a heartbeat that keeps ticking; drop the second and the
    refresh would tick it for the ledger."""
    from test_engine_executor import StubClient

    from cli.engine.execgate import KILL_FILE, exec_dir
    from cli.engine.executor import ProbeExecutor, set_executor_hooks

    registry = CollectorRegistry()
    gate = ExecutionGate(
        armed_in_config=False,
        state_dir=tmp_path,
        venue_reader=lambda *, now, opener=None: VenueStatus(status="online", ok=True, observed_at=now),
    )
    exec_gauges = _ExecGauges(registry)
    t0 = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    sink = command._make_exec_sink(gate, tmp_path / "journal", None, exec_gauges, None)
    clock = types.SimpleNamespace(now=t0)
    config = EngineConfig(journal_dir=tmp_path / "journal", store_dir=tmp_path / "store")
    executor = ProbeExecutor(client=StubClient(), gate=gate, config=config, clock=lambda: clock.now)
    set_executor_hooks(publish_verdict=exec_gauges.update)
    try:
        sink(_sink_result(t0), t0, 1.0)  # one healthy cycle: the heartbeat is t0
        assert registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") == t0.timestamp()

        monkeypatch.setattr(command, "write_exec_record", _raise)
        t1 = t0 + timedelta(hours=8)
        try:
            sink(_sink_result(t1), t1, 1.0)
        except OSError:
            pass  # in production cycle.py's _update_metrics swallows exactly this raise -- same effect
        exec_dir(tmp_path).mkdir(parents=True, exist_ok=True)
        (exec_dir(tmp_path) / KILL_FILE).touch()  # what the refresh must publish, so its run is read by value
        clock.now = t1 + timedelta(seconds=5)
        executor.on_timer(clock.now)  # the idle tick, its refresh period long past
    finally:
        set_executor_hooks()

    assert registry.get_sample_value("zcrypto_exec_kill_tripped") == 1, "the idle refresh never published the readings"
    frozen = registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds")
    assert frozen == t0.timestamp(), "the heartbeat moved past a cycle whose ledger record was never written"
    assert t1.timestamp() - frozen > _staleness_threshold_seconds()
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
def test_the_idle_tick_never_evaluates_tracking(tmp_path):
    """`on_timer` is not a call site for this. A week-wide read on a 5-second tick would be 17280
    journal scans a day, and `_pickup`'s idle path is contracted to read no gate and no venue at
    all."""
```

with:

```python
def test_the_idle_tick_never_evaluates_tracking(tmp_path):
    """`on_timer` is not a call site for this. A week-wide read on a 5-second tick would be 17280
    journal scans a day, and `_pickup`'s idle path is contracted to read no gate inside the refresh
    period; the three ticks here precede the period's first elapse from the executor's
    construction."""
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    assert not _kill_file(tmp_path).exists()
    assert gate.calls == 0  # the idle path reads nothing at all
```

with:

```python
    assert not _kill_file(tmp_path).exists()
    assert gate.calls == 0  # the three ticks fall before the first refresh
```

- [ ] **Step 3: Run the file and watch the new cases fail**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_metrics.py -q -p no:cacheprovider`
Expected: `4 failed, 369 passed`; the executor file alone reads `3 failed, 300 passed` and the metrics file `1 failed, 69 passed`. `test_an_idle_tick_reads_no_gate_inside_the_refresh_period_and_one_per_period_past_it` fails on `assert 0 == 1` at the tick a period after construction; `test_a_kill_file_removed_on_an_idle_engine_is_republished_within_the_refresh_period` on `assert [] == [(datetime..., 'full', False, False)]`, nothing published; `test_the_verdict_hook_sees_every_evaluation_and_a_raising_hook_never_stops_a_submission` on `assert ([])`, the old `_publish` calling the hook without `heartbeat` so its `TypeError` is swallowed before `seen` gains a line; the freeze test on `assert 0.0 == 1`, `the idle refresh never published the readings`, there being no refresh yet. `test_the_idle_tick_never_evaluates_tracking` passes either way.

- [ ] **Step 4: The refresh in `cli/engine/executor.py`, the docstring in `cli/engine/command.py`, the three pages and the alert-rules entry**

Replace, in `cli/engine/executor.py`, this block:

```python
_REREAD_ATTEMPTS = 3
```

with:

```python
_REREAD_ATTEMPTS = 3
# The idle cadence the gate is re-evaluated and its readings republished at, against the kill-switch
# rule's `for: 5m`: a refresh, a scrape and the rule's evaluation are a minute each at most, so a
# switch removed on an idle engine resets the rule's pending period within three minutes, and a page
# is cleared whenever the file goes inside the first two minutes of pending. While a plan runs the
# tick evaluates anyway; between cycles the boundary sink alone published before, up to four hours
# apart. The refresh moves no heartbeat: `_ExecGauges.update`'s `heartbeat` says why.
_GATE_REFRESH = timedelta(seconds=60)
```

Replace, in `cli/engine/executor.py`, this block:

```python
def set_executor_hooks(*, publish_verdict=None, metrics=None) -> None:
    """Install (or clear, with the defaults) the executor's telemetry hooks: `publish_verdict` is
    called `(verdict, evaluated_at=...)` after EVERY gate evaluation, `metrics` is an object with
```

with:

```python
def set_executor_hooks(*, publish_verdict=None, metrics=None) -> None:
    """Install (or clear, with the defaults) the executor's telemetry hooks: `publish_verdict` is
    called `(verdict, evaluated_at=..., heartbeat=...)` after EVERY gate evaluation, `heartbeat`
    False on the idle refresh alone, `metrics` is an object with
```

Replace, in `cli/engine/executor.py`, this block:

```python
def _publish(verdict: GateVerdict, evaluated_at: datetime) -> None:
    if _publish_verdict is None:
        return
    try:
        _publish_verdict(verdict, evaluated_at=evaluated_at)
```

with:

```python
def _publish(verdict: GateVerdict, evaluated_at: datetime, *, heartbeat: bool = True) -> None:
    if _publish_verdict is None:
        return
    try:
        _publish_verdict(verdict, evaluated_at=evaluated_at, heartbeat=heartbeat)
```

Replace, in `cli/engine/executor.py`, this block:

```python
        self._sockets_down: set[str] = set()
        self._reread_tries = 0
```

with:

```python
        self._sockets_down: set[str] = set()
        self._reread_tries = 0
        # When the gate was last evaluated, for the idle refresh: the process's startup evaluation
        # published moments before this construction.
        self._gate_evaluated_at: datetime = self._now()
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _evaluate(self, now: datetime) -> GateVerdict:
        """The ONE gate read. Every evaluation reaches the publish hook (D4's cadence ruling), so
        the gate's published state is seconds-fresh for as long as a plan is running and reverts to
        the between-cycles cadence the moment one is not."""
        verdict = self._gate.evaluate(now)
        _publish(verdict, now)
        return verdict
```

with:

```python
    def _evaluate(self, now: datetime, *, heartbeat: bool = True) -> GateVerdict:
        """The ONE gate read. Every evaluation reaches the publish hook (D4's cadence ruling), so
        the gate's published state is seconds-fresh for as long as a plan is running and at most
        `_GATE_REFRESH` old while none is (`_refresh_gate`), since the board's kill-switch rule reads
        the gauge and a switch removed on an idle engine would otherwise page until the boundary.
        `heartbeat` False, the refresh's, publishes the readings and not the staleness rule's
        series, which stays the boundary path's."""
        verdict = self._gate.evaluate(now)
        self._gate_evaluated_at = now
        _publish(verdict, now, heartbeat=heartbeat)
        return verdict
```

Replace, in `cli/engine/executor.py`, this block:

```python
        # Publish now rather than waiting for a tick that may never evaluate again: with no plan
        # running, `on_timer` takes the idle path and reads no gate at all, so the trip gauge would
        # otherwise sit at its pre-trip value until the next cycle happens to publish one.
        self._evaluate(self._now())
```

with:

```python
        # Publish now rather than waiting for the tick: with no plan running, the idle path reads
        # the gate once a period (`_refresh_gate`), so the trip gauge would otherwise sit at its
        # pre-trip value for up to `_GATE_REFRESH`.
        self._evaluate(self._now())
```

Replace, in `cli/engine/executor.py`, this block:

```python
            self._pump(now)
            self._publish_resting_age(now)
        except Exception:
            # Refusal by default: whatever broke, stop running this plan. Anything already resting
```

with:

```python
            self._pump(now)
            self._publish_resting_age(now)
            self._refresh_gate(now)
        except Exception:
            # Refusal by default: whatever broke, stop running this plan. Anything already resting
```

Replace, in `cli/engine/executor.py`, this block:

```python
        except Exception:
            logger.exception("executor resting-age publish raised -- continuing")

    # --- the sockets ---------------------------------------------------------------------------
```

with:

```python
        except Exception:
            logger.exception("executor resting-age publish raised -- continuing")

    def _refresh_gate(self, now: datetime) -> None:
        """The idle refresh: one evaluation, published, once `_GATE_REFRESH` has passed since the last
        -- the tick a plan runs on evaluates anyway and stamps it. What it publishes is what the gate
        reads, its own fail-closed readings included, and not the heartbeat, which stays the boundary
        path's so the staleness rule keeps watching the sink and its exec record; it journals
        nothing, since the exec record's verdict is the boundary sink's alone. Wrapped as
        `_publish_resting_age` is: telemetry may never end a plan."""
        try:
            if now - self._gate_evaluated_at >= _GATE_REFRESH:
                self._evaluate(now, heartbeat=False)
        except Exception:
            logger.exception("executor gate refresh raised -- continuing")

    # --- the sockets ---------------------------------------------------------------------------
```

Replace, in `cli/engine/command.py`, this block:

```python
    """The execution envelope's published state, updated from the gate's verdict every cycle. `gate_level` and the presence gauges
```

with:

```python
    """The execution envelope's published state, updated at every gate evaluation: the boundary sink's, the executor's on its
    tick while a plan runs, and its idle refresh once a minute, so a control file moved by hand reaches the board within that
    minute; the heartbeat, `last_evaluation`, moves at all of those but the refresh, so it stays the boundary path's.
    `gate_level` and the presence gauges
```

Replace, in `cli/engine/command.py`, this block:

```python
    def update(self, verdict: GateVerdict, *, evaluated_at: datetime) -> None:
        i = verdict.inputs
```

with:

```python
    def update(self, verdict: GateVerdict, *, evaluated_at: datetime, heartbeat: bool = True) -> None:
        """`heartbeat` False publishes the five readings and leaves `last_evaluation` where it was: the executor's idle
        refresh, whose evaluation is not the boundary path's, so the staleness rule keeps watching the sink and the exec
        record it writes before it."""
        i = verdict.inputs
```

Replace, in `cli/engine/command.py`, this block:

```python
        self.venue_ok.set(1 if i["venue_status"] == "online" else 0)
        if self.last_evaluation is None:
```

with:

```python
        self.venue_ok.set(1 if i["venue_status"] == "online" else 0)
        if not heartbeat:
            return
        if self.last_evaluation is None:
```

Replace, in `cli/engine/command.py`, this block:

```python
    """`run()`'s per-cycle metrics sink, at module level rather than inline so a test can reach the closure and prove the ORDER
    inside it: a failing ledger write starves the heartbeat rather than being masked by a gauge that keeps ticking."""
```

with:

```python
    """`run()`'s per-cycle metrics sink, at module level rather than inline so a test can reach the closure and prove the ORDER
    inside it: a failing ledger write starves the heartbeat rather than being masked by a gauge that keeps ticking -- the
    executor's idle refresh included, which publishes with `heartbeat` False."""
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
`zcrypto_exec_armed` reads 0 on the engine's next evaluation (at most one cycle, roughly four hours), and because the rule reads `min_over_time` over the window```

with:

```markdown
`zcrypto_exec_armed` reads 0 on the engine's next gate evaluation — the executor's idle refresh within a minute, or its next tick while a plan runs — and because the rule reads `min_over_time` over the window```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
This is the heartbeat for the whole execution envelope, not a reading of any one input. The gate is evaluated at engine start and again after every cycle, roughly four-hourly, and the six gauges `_ExecGauges` publishes — the five gate readings plus this heartbeat, not the other eight `zcrypto_exec_*` families, which are the executor's own counters — are written as a side effect of a gate evaluation and nowhere else. If the evaluation call is dropped by a regression — anywhere in the cycle path, however unrelated it looks — those six FREEZE at their last published value: the only other writer is a plan in flight, whose intent-time gate reads reach the same publish hook — and a plan is built and picked up whether or not the engine is armed, since arming is an input to the gate (`armed_in_config`, the arm file) rather than a condition on the plan. Cycle telemetry (`zcrypto_engine_cycle_success`, `zcrypto_engine_cycle_completed_at_seconds`) can keep reading perfectly healthy through this, because nothing about the cycle itself needs to fail for the gate call inside it to be skipped. A stale `disarmed` reading is indistinguishable on this dashboard from a live one — this alert is the only signal that can tell the difference.
```

with:

```markdown
This is the heartbeat for the execution envelope's boundary path, not a reading of any one input. The gate is evaluated at engine start, after every cycle in the boundary sink — roughly four-hourly, beside the exec record that sink writes first — on the executor's tick while a plan runs, and once a minute on its idle refresh; of the six gauges `_ExecGauges` publishes — the five gate readings plus this heartbeat, not the other eight `zcrypto_exec_*` families, which are the executor's own counters — the five readings are written at every one of those evaluations and the heartbeat at all but the idle refresh, and nowhere else. If the boundary sink's evaluation call is dropped by a regression — anywhere in the cycle path, however unrelated it looks — or its record write keeps failing, which the sink orders before the gauges so that a record never written starves the heartbeat, this heartbeat FREEZES at its last published value while the five readings keep moving on the refresh: the only other writer of the heartbeat is a plan in flight, whose intent-time gate reads reach the same publish hook — and a plan is built and picked up whether or not the engine is armed, since arming is an input to the gate (`armed_in_config`, the arm file) rather than a condition on the plan. Cycle telemetry (`zcrypto_engine_cycle_success`, `zcrypto_engine_cycle_completed_at_seconds`) can keep reading perfectly healthy through this, because nothing about the cycle itself needs to fail for the gate call inside it to be skipped or its record write to raise. Live readings beside a frozen heartbeat are indistinguishable on this dashboard from a healthy boundary — this alert is the only signal that can tell the difference.
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
2. **If cycles ARE completing but this still fires**, the gate evaluation call has been dropped from the cycle path specifically — a code regression, not an infrastructure problem. Do not trust any of the other five gate gauges on the board (`zcrypto_exec_gate_level`, `zcrypto_exec_armed`, `zcrypto_exec_kill_tripped`, `zcrypto_exec_restart_hold`, `zcrypto_exec_venue_ok`) until it is fixed: every one of them is frozen at whatever it last read, and a frozen `disarmed` looks identical to a live one (set: the writes to the six gate gauges under `cli/` from outside `_ExecGauges.update`, whose one call publishes them together; count: `infra/scripts/count-list.sh gate-gauge-writes-outside-the-publish-call`).
```

with:

```markdown
2. **If cycles ARE completing but this still fires**, the boundary sink's gate evaluation has been dropped from the cycle path — a code regression, not an infrastructure problem — or its exec record write has been failing at every boundary: the sink writes the record before it touches the gauges, so a write that raises starves this heartbeat by design, and `metrics sink raised for cycle …` in the engine log is that shape. The other five gate gauges on the board (`zcrypto_exec_gate_level`, `zcrypto_exec_armed`, `zcrypto_exec_kill_tripped`, `zcrypto_exec_restart_hold`, `zcrypto_exec_venue_ok`) keep moving on the executor's idle refresh, which publishes them with the heartbeat left alone, so they are live while the executor ticks; what is missing is the boundary's exec record, so read the engine journal on the host for the boundary's `exec-*.json` before trusting a window's ledger (set: the writes to the six gate gauges under `cli/` from outside `_ExecGauges.update`, whose one call publishes them together; count: `infra/scripts/count-list.sh gate-gauge-writes-outside-the-publish-call`).
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
3. **If the reason no longer holds, remove the kill file on the engine host.** This clears immediately: no deploy, no restart, no engine downtime.
```

with:

```markdown
3. **If the reason no longer holds, remove the kill file on the engine host.** This clears within the executor's next gate refresh — one tick while a plan runs, a minute at most while none does — plus one scrape: no deploy, no restart, no engine downtime (no count command: `_GATE_REFRESH` in `cli/engine/executor.py` is the idle cadence, and drill D of 2026-09-26 measured the page outliving the file by four minutes before it).
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
While a plan is running the executor evaluates on every 5-second tick and publishes each verdict; with no plan running it evaluates at engine start and at each 4-hourly boundary. Every kill-switch bound below therefore assumes a plan is resting, which is why E's preconditions demand one: a kill file placed on an idle engine can wait four hours to reach Grafana at all.```

with:

```markdown
While a plan is running the executor evaluates on every 5-second tick and publishes each verdict; with no plan running it evaluates at engine start, at each 4-hourly boundary, and once a minute on its idle tick. Every kill-switch bound below assumes a plan is resting, which is why E's preconditions demand one: a kill file placed on an idle engine reaches Grafana within a minute plus a scrape, a phase the bounds below do not carry.```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
so a kill file placed on an idle engine can wait hours to reach Grafana and the measured page time would be an artefact of the cycle clock (no count command:```

with:

```markdown
so a kill file placed on an idle engine waits for the idle refresh, up to a minute, and the measured page time would carry the refresh's phase rather than the tick's (no count command:```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
4. **The page clears well after the reset, and that lag is the gauge's cadence rather than a stuck alert.** With the plan already gone the next publish is the 4-hourly boundary, and `exec-status` runs in its own process and publishes nothing. Read the reset from `exec-status`; do not wait on the alert to confirm it, and do not re-place the file because the page is still up.
```

with:

```markdown
4. **The page clears within about three minutes of the reset — the idle refresh, a scrape and the rule's evaluation, a minute each at most — and the lag is the gauge's cadence rather than a stuck alert.** With the plan already gone the next publish is the executor's idle refresh, and `exec-status` runs in its own process and publishes nothing. Read the reset from `exec-status`; do not wait on the alert to confirm it, and do not re-place the file because the page is still up.
```

Replace, in `infra/grafana/alerts.yaml`, this block:

```yaml
    # The rule that catches the one failure nothing else can see: a regression that drops the
    # gate evaluation from the cycle path freezes all six gauges at their last values, cycle
    # telemetry stays healthy, and every dashboard reads green while the envelope is gone.
    # Follows zcrypto-gate-exporter-stale's shape. Threshold = one cycle interval plus slack.
```

with:

```yaml
    # The rule that catches the one failure nothing else can see: a regression that drops the
    # gate evaluation from the cycle path, or a ledger write failing at every boundary, freezes
    # this heartbeat -- the executor's idle refresh moves the five readings and never this series,
    # so they read live while the boundary's exec record is gone -- cycle telemetry stays healthy,
    # and every dashboard reads green while the envelope's record is gone.
    # Follows zcrypto-gate-exporter-stale's shape. Threshold = one cycle interval plus slack.
```

Replace, in `infra/grafana/alerts.yaml`, this block:

```yaml
so every published value describing whether it may trade is frozen at whatever it last read. Nothing else reports this: the cycle metrics can look perfectly healthy while the safety gate is no longer consulted at all, and a stale reading of `disarmed` is indistinguishable from a live one. Check that cycles are still completing, then read the current state directly on the engine host with the exec-status command rather than trusting the dashboard.```

with:

```yaml
so the boundary path has stopped evaluating it and writing the exec record beside that evaluation, or the record's write has been failing at every boundary. The gate readings on this board keep moving on the executor's idle refresh while the process ticks, so they do not show this, and cycle telemetry can look perfectly healthy through it. Check that cycles are still completing, then read the engine journal on the host for the boundary's exec record and the engine log for a `metrics sink raised` line.```

Replace, in `infra/grafana/engine-dashboard.json`, this block:

```json
It moves ONLY when the execution gate is evaluated -- at process start, after each cycle (roughly four-hourly), and on every tick while a plan is running; an idle engine reads no gate at all. So between cycles this reading can be hours old, in EITHER direction: ONLINE right through a venue outage the capture side is already paging on, or NOT ONLINE long after the venue came back. The gate evaluation heartbeat beside it is this tile's age -- read the two together or neither.```

with:

```json
It moves when the execution gate is evaluated -- at process start, after each cycle, on every tick while a plan is running, and once a minute on the executor's idle refresh -- so it is at most about a minute old while the engine ticks, in EITHER direction: ONLINE briefly through a venue outage the capture side is already paging on, or NOT ONLINE briefly after the venue came back. The gate evaluation heartbeat beside it moves on the boundary's evaluation and not on that refresh, so it is not this tile's age: a frozen heartbeat beside a moving tile is the boundary path stopped, not this reading gone stale.```

Replace, in `infra/grafana/engine-dashboard.json`, this block:

```json
How long since the execution gate was last evaluated -- the heartbeat that makes every other tile on this row trustworthy. The gate runs at process start and after every cycle, roughly four-hourly, so a healthy reading tracks the cycle-age reading at the top of this board. If this stops advancing, EVERY gauge on this row freezes at its last value: cycle telemetry can stay perfectly healthy while the safety envelope is silently no longer being read at all.```

with:

```json
How long since the execution gate was last evaluated on the boundary path -- the heartbeat of the exec record the boundary sink writes beside that evaluation. It moves at process start, after every cycle's boundary sink and on every tick while a plan runs, and not on the executor's idle refresh, which moves the other tiles on this row once a minute; so a healthy reading tracks the cycle-age reading at the top of this board. If this stops advancing while the other tiles keep moving, the boundary's evaluation and its exec record have stopped -- a regression on the cycle path, or a ledger write failing at every boundary: cycle telemetry can stay perfectly healthy while the safety envelope's record is silently no longer written.```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
that gauge is published when the gate is EVALUATED, which while disarmed is engine start and each 4-hourly cycle — so it reads 0 for hours after you arm and 1 for hours after you disarm, and the rule would page on your own attended work and stay mute through the hour after you walk away. Visibility is unaffected: engine-dashboard panel 61 plots both dispositions. The full reasoning, and the one change that would make a rule viable, are in `tests/test_infra_alert_rules.py`'s `NOT_A_FAULT_SIGNAL` entry for this metric.```

with:

```markdown
that gauge follows an arm or a disarm within a minute, the executor's idle refresh, and the counter the rule would gate on counts your own hand-placed orders while the engine is disarmed — so the rule would page on your own account activity, and a rule on a forensic counter is a decision of its own. Visibility is unaffected: engine-dashboard panel 61 plots both dispositions. The full reasoning is in `tests/test_infra_alert_rules.py`'s `NOT_A_FAULT_SIGNAL` entry for this metric.```

Replace, in `tests/test_infra_alert_rules.py`, this block:

```python
    # `unmatched` rising while `zcrypto_exec_armed` is 0 -- is unsound, because `zcrypto_exec_armed`
    # is published only when the gate is EVALUATED (engine start, then each 4-hourly cycle), so it is
    # a snapshot rather than an attendance signal and is stale in BOTH directions: loud during the
    # owner's own attended activity, mute through the hours after a window closes. What would make
    # the candidate work is one change: publish `zcrypto_exec_armed` on the executor's 5s tick --
    # engine code on the live trade path, so a decision of its own. The silent failure no rule could
    # catch either way -- an adopted order whose events fail to key into `_attached` -- is a
    # by-value reading in T0018.
```

with:

```python
    # `unmatched` rising while `zcrypto_exec_armed` is 0 -- pages on the owner's own account
    # activity, since a hand-placed order while the engine is disarmed is exactly an unmatched
    # external event, and a rule on a forensic counter is a decision of its own. `zcrypto_exec_armed`
    # itself is no longer the obstacle: it is published at every gate evaluation, the executor's idle
    # refresh once a minute included, so it follows an arm or a disarm within that minute. The silent
    # failure no rule could catch either way -- an adopted order whose events fail to key into
    # `_attached` -- is a by-value reading in T0018.
```

- [ ] **Step 5: Run the two files and watch them pass**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_metrics.py -q -p no:cacheprovider`
Expected: `373 passed`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_config.py tests/test_engine_concordance.py tests/test_engine_gate_export_cache.py tests/test_engine_gate_cache.py tests/test_engine_stub_fidelity.py tests/test_engine_command.py tests/test_engine_gate_export.py tests/test_engine_feeders.py tests/test_engine_tracking.py tests/test_engine_execledger.py tests/test_ops_daily_soak.py tests/test_error_paths_are_logged.py tests/test_engine_metrics.py tests/test_engine_soak_command.py tests/test_ops_daily.py tests/test_engine_soak.py tests/test_engine_node.py tests/test_engine_executor.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_count_list.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_systemd_user_units.py tests/test_dashboards_cover_metrics.py tests/test_engine_journal_prune.py tests/test_grafana_push_sh.py tests/test_infra_alloy_series.py tests/test_infra_grafana_keepalive.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `2757 passed, 9 skipped` when this plan was written, the executor union with Task 2's, since the task touches `cli/engine/command.py`, and the five other readers of `infra/grafana/alerts.yaml` and `infra/grafana/engine-dashboard.json` (`grep -rlE 'engine-dashboard\.json|alerts\.yaml' tests/test_*.py` less the files already listed), since the task touches both.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. `mdformat` covers the three runbook pages.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/command.py cli/engine/executor.py infra/grafana/alerts.yaml infra/grafana/engine-dashboard.json infra/runbooks/drills-order-path.md infra/runbooks/engine-procedures.md infra/runbooks/engine.md tests/test_engine_executor.py tests/test_engine_metrics.py tests/test_infra_alert_rules.py
git commit -m "fix(engine): the gate's gauges are republished once a minute while no plan runs

Measured on 2026-09-26, drill D's restore: the startup evaluation published the kill switch as
tripped, the file and the hold were removed two minutes later with no intent live, and the gauges
kept the boot's reading until the next boundary, so the kill-tripped rule paged a switch gone four
minutes and cleared two hours later. Every gate evaluation now stamps its time and the executor's
tick re-evaluates the gate once sixty seconds have passed since the last, publishing what the gate
reads through the hook the boundary sink and a running plan's ticks use; a refresh, a scrape and
the rule's evaluation are a minute each at most, inside the rule's five-minute pending, and the
refresh journals nothing. The refresh publishes the five readings and not the heartbeat: the hook
carries a heartbeat flag the refresh alone sets false, so the staleness rule keeps watching the
boundary sink and the exec record it writes before the gauges, and a ledger write failing at
every boundary still starves it. The idle tick reads no gate inside the period and one per period
past it. The kill-tripped runbook's step says the removal clears within the refresh bound, the
drill page's derivation rule, E's precondition and E's clearing step name the idle refresh, the
arm-file step and the not-evaluated section's meaning and second step, the rule's comment and
summary and the two gate tiles say which gauges the refresh moves and which it leaves, and the
procedures page's no-alert bullet and the alert-rules entry on the external-events counter name
the signal, not the gauge's cadence, as what keeps a rule unauthored.

Cases: an idle tick reading no gate inside the period, one past it and one per period after, with
a plan file read on its own tick; D's shape, a boot with the kill file present, the file removed,
no intent live, and the published verdict reading the file gone at the first refresh with the
heartbeat flag false and the journal untouched; the verdict hook seeing the flag true on a plan's
evaluations; the freeze test running the idle refresh beside the raising sink, the readings moved
and the heartbeat frozen; the tracking idle case re-bounded to the period.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015giLLD6tUoSWoSNdhriVZU"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with five probes, then record their verdicts by a message-only amend**

The control stretches the period to four hours, so both idle cases fail. The mutations, in order: the refresh is never called; the refresh runs on every tick; the stamp is never set, so a refresh follows every tick past the first period. Each `-k` selects 3 of the file's 303 cases. Then the heartbeat, through the metrics file's three heartbeat cases: over the executor, the control drops the refresh, which the re-trued freeze test reads by value, and the mutation has the refresh stamp the heartbeat; over `cli/engine/command.py`, the control drops the heartbeat's set, which the sink case reads, and the mutation has `update` ignore `heartbeat`:

```bash
K="refresh_period or never_evaluates_tracking"
C='s/_GATE_REFRESH = timedelta(seconds=60)/_GATE_REFRESH = timedelta(hours=4)/'
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            self._refresh_gate(now)$/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/if now - self._gate_evaluated_at >= _GATE_REFRESH:/if True:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        self._gate_evaluated_at = now$/        pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control 's/^            self._refresh_gate(now)$/            pass/' \
  --mutation 's/self._evaluate(now, heartbeat=False)/self._evaluate(now)/' \
  -- uv run pytest tests/test_engine_metrics.py -q -p no:cacheprovider -k heartbeat
infra/scripts/mutate-probe.sh --file cli/engine/command.py \
  --control 's/^        self.last_evaluation.set(evaluated_at.timestamp())$/        pass/' \
  --mutation 's/^        if not heartbeat:$/        if False:/' \
  -- uv run pytest tests/test_engine_metrics.py -q -p no:cacheprovider -k heartbeat
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <that file>` — the Global Constraints' rule, never `--amend -m "…"`, inside which the shell runs each backticked name below as a command:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/executor.py`, control the refresh period
stretched to four hours so both idle cases fail, through
`-k "refresh_period or never_evaluates_tracking"`:
the refresh never called, KILLED, control proven; the refresh on every tick, KILLED, control
proven; the stamp never set, KILLED, control proven; through `-k heartbeat` over
`tests/test_engine_metrics.py`, control the refresh dropped: the refresh stamping the heartbeat,
KILLED, control proven; over `cli/engine/command.py`, control the heartbeat's set dropped:
`update` ignoring `heartbeat`, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` — Expected: `1`, the verdict naming the script.

---

## Rollout (attended)

The change ships with T0213's engine rollout as one image, on the owner's word of 2026-09-26: the executor, the ledger and the reader ride the image that plan builds, through `.claude/skills/zcrypto-rollout-image/SKILL.md`'s engine section, inside an inter-cycle gap while flat, and this plan plans no converge of its own; T0213's findings carry that ride-along on this branch, so the engine half's author reads it there. If T0213's own plan is not converged within a week of this pair's merge, the pair takes its own rollout through the same skill. Both halves are registered where a reader evaluates them: at closeout the controller re-trues T0018's build-list line to `merged in PR #<N>, not deployed: rides T0213's engine image, or takes its own rollout by <merge date + 7 days>`, adds that date as an arm of T0018's `ripe_when` — `or <that date>, the pull request's image not yet on the engine, read from the engine row of docs/reference/fleet-pins.md` — and re-renders the index with `uv run python infra/scripts/topics-index.py`; the arm goes when the converge lands. The tracking-report change reaches the workstation at merge, where the report runs, and the runbook's §6 item 3 is read against it at the next attended window.

## Resolution

The branch delivers the build-list item registered on T0018 on 2026-09-26 from Rung 1's verdict and extended on this branch with drill G's finding: the reprice ladder, the ledger reader's margin rows, and the intents a restart orphans, one pull request on the live trade path. T0018 stays `partial`; its build-list line for the item is re-trued in the pull request's closeout, by the controller, to name the pull request and the deploy still owed (the Rollout's text), and to carry the restart finding as still open if the third cluster was struck; `docs/reference/change-index.md` maps the pull request to the topic. No topic is registered and none resolved; T0213's findings gain two lines on this branch, the kept reducer's intent and the ride-along, and T0214's one, the EURC-charged fee. What the pair leaves with a named home: the kept reducer's intent after a restart, T0213's engine half, on its findings line; cancel-on-stop, T0018's other build-sequence item. Re-cancel-on-reconnect is delivered by Task 4 and the gate-gauge defect by Task 5, two T0018 lines the closeout re-trues beside the build-list line.

## Self-review

- Spec coverage: D1 and D2 are Task 1's counters, phase, detach and `_poll` arm, with the revoke, time-box, racing-fill, replayed-ack, completing-fill, half-book, silence-order and raise cases; D3 its fall-through with the alternating-crossings case, the sell close and the two rest-mode ladders, and its runbook clause in Task 1's page step; D4 a Global Constraint (no `_INTENT_KEYS` change); D5 the `order` payload keys the first case reads; D6 changes nothing and is a Global Constraint's silence. D7 and D12 are Task 2's matched set and the real-shape fixture; D8 its `matched_fees_eur` over `_EURO_FEE_ASSETS`, the PnL case and the fixture's EURC row; D9 its `known` tally; D10 the four-decimal cases; D11 changes nothing. D13 changes nothing; D14 is Task 3's sweep and its sixteen cases; D15 the flipped minted case and the flagged-acceptance case; D16 the page edits in Tasks 1, 2 and 3. D17 is Task 4's subscription, forwarder and socket handler with the two arming cases; D18 its `_minted_terminal` predicate over the order's history and the withheld Cache answer, with the partial-fill case, the reducer case and the withdrawn-fill case it must not disturb; D19 its pass, cancel and budget with the two re-cancel cases, the closed-report case, the failed-read case, the refused-cancel case, the two in-flight cases and the three loopback cases; D20 the intent and counter assertions inside the first case and the filled-report case; D21 a Global Constraint's silence and the spec's Out of scope. D22 and D23 are Task 5's stamp, refresh and constant with the bounded idle case; D24 the refresh's wrap; D25 the journal assertion in the D-shaped case, the heartbeat flag in that case, the verdict-hook case and the metrics file's freeze test, and the page, tile and rule edits in Task 5. The measured basis is the spec's and no task re-measures it. D26 is Task 3's handles, the eleven reads through them, and its two guards, the real engine's and the stub's; D15 as amended is Task 3's WARNING arm and flag and Task 4's second trigger, with the pages re-trued in each.
- Placeholders: `PROBE_VERDICT` is the one token, replaced in each task's Step 10 and checked to be gone; `<model>` in the trailers is the executing model's own name, a Global Constraint.
- Names: every name a task consumes is listed under its Interfaces and exists in the test module or the source module at the step that uses it; the new source names (`_reprice_at_touch`, `_time_box_with_nothing_resting`, `_settle_pending_intents`, `cancel_venue_order`, `_minted_terminal`, `on_socket_state`, `_arm_reread_after_mint`, `_nothing_in_flight`, `_reread_pass`, `_minted_closed`, `_recancel`, `_cache_lookup`, `_refresh_gate`), the ledger accessor (`pending_plan_intents`) and the test helpers (`_real_row`, `_pending_plan_entry`, `_pending_cancel_read_at_dispatch`, `_VenueCancel`, `_cancel_venue_order`, `_socket`, `_reconnect`, `_hold_in_cache`, `_minted_after_a_cut`, `StubCache.orders_inflight`) are defined in the fence that introduces them, `_submitted_row`'s `qty` keyword by the fence before the first case that passes it, and `_executor`'s and `_resting_executor`'s `venue_cancel` keyword by the fences before the first case that passes it, on a tree that does not yet take it.
- Order: Task 2's and Task 3's first steps check the previous task's marker, and every failing and passing count was read with the tasks applied in this order.
