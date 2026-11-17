# A restored order Kraken lists open while the Cache reads it closed is cancelled at the startup pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At a restart, the startup pass cancels at Kraken, by its txid, a restored order the ledger holds open that Kraken reports open while the Cache's copy of it reads closed, and the re-read pass then books a fill that raced the cancel and writes the intent.

**Architecture:** The open-row sweep of the startup pass (`_reconcile_adopted_rows`) gains one arm ahead of its restored arm: a restored row whose Kraken report is open and whose Cache copy's status is closed goes to a new `_cancel_closed_copy`, which runs the re-read pass's existing `_recancel` — repair from the report, `CancelOrder` by txid through `cancel_venue_order`, the row `canceled` with a `recancelled` event — with a `cache_status` that selects the startup's two lines, then adds the row to `_restored_fills` and arms the re-read pass (spec D3–D7, D13). The loopback's `trade` frame gains a switch for `order_qty`, and the restart harness proves both frame shapes landing before the startup pass's cancel and inside it, and a fill racing the new cancel (D2, D10). The rung-3 restart read and the error-logs page name the two lines; the decisions log takes the owner's three rulings and the author's four calls; T0226 goes `partial`.

**Tech Stack:** Python 3.14, pytest, `nautilus-trader` 2.0.0rc9.dev20261106, `tests/kraken_loopback.py`, `tests/cache_restart_child.py` against a local `valkey-server`, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00161-restored-remainder-cancelled-design.md`

**Tier** — `uv run python infra/scripts/tier.py --paths cli/engine/executor.py tests/test_engine_executor.py tests/kraken_loopback.py tests/test_cache_restart.py tests/slow-cases.txt infra/runbooks/engine-procedures.md infra/runbooks/engine.md docs/research/14.phase6-decisions.md docs/open-topics/T0226-a-restored-order-the-cache-reads-filled-keeps-its-remainder-resting.md docs/open-topics/README.md`, run at `62d52d6b2`:

```
tier: full
full cli/engine/executor.py — under cli/engine/, read as a non-prose change
full tests/test_engine_executor.py — a test importing cli.config, read as a non-prose change
full tests/test_cache_restart.py — a test importing cli.engine.execgate, read as a non-prose change
```

Every fence below was run against `9d08c6818` in detached scratch worktrees under `.tmp/t0226/` — `base`, the tree as it stands, and `wt`, with the plan's code applied and committed there — never pushed: Task 1's cases read `20 passed` on `wt` and `14 failed, 6 passed` on `base`; Task 2's read `5 passed` on `wt` and `2 failed, 3 passed` on `base`; every probe arm the tasks list read `KILLED (control proven, tree restored byte-identically)` on `wt`; the runbook texts, the decisions-log entries and the topic's edit went through the repository's commit hooks there, and `tests/test_open_topics_frontmatter.py`, `tests/test_topics_index.py`, `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_internal_terms_not_operator_visible.py` passed over them. The spec's *The measured basis* pastes each reading. The fences the plan review's first round rewrote — Task 1 Step 3's `_cancel_closed_copy` and `_recancel` branches and docstring lines, Task 2 Step 1's `REREAD_WINDOW` and docstrings, the spec's item-4 text — were applied from this file and the spec to a detached scratch worktree at `ee5376441` under `.tmp/plan-review/00161/`: Task 1's cases read `14 failed, 6 passed, 808 deselected` before the code and `20 passed, 808 deselected` and `828 passed` after it, its eleven arms each `KILLED (control proven, tree restored byte-identically)`; Task 2's selection read `5 passed, 17 deselected`, the whole harness file under `ZCRYPTO_RERUN_SLOW=1` `22 passed` and `tests/test_slow_cases.py` `2 passed`; the hooks left both runbook pages unchanged, and `tests/test_internal_terms_not_operator_visible.py` read `1113 passed` and the decisions-log tests `50 passed` over the texts.

## Global Constraints

- The spec, `docs/specs/00161-restored-remainder-cancelled-design.md`, is the authority, and a task that names one of its sections reads it there; where it is silent this plan rules, in *Rulings where the spec is silent*.
- No task converges, builds an image, pushes or reaches a venue: the change ships on the engine image spec D14 names, the converge the fleet's concern. Every venue read and cancel in a test goes to `tests/kraken_loopback.py` or a stub; the autouse `_no_production_venue_read` fixture in `tests/test_engine_executor.py` fails a case that reaches the production reader or canceller, so a case whose startup pass can reach the new cancel hands the executor a `venue_cancel`.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0226` (branch `feat/t0226-restored-remainder-cancelled`); every command runs with it as the working directory, and git takes `-C` that path. The main checkout is live.
- Before a task's first command, `mkdir -p .tmp/implementer .local/restored-remainder-cancelled`, its own call: every pytest run takes `--basetemp=.tmp/implementer/pt`, and pytest makes no parent of its basetemp.
- Tests per commit: `infra/scripts/consumers.sh --tests --direct <the commit's changed paths> 2>.tmp/implementer/cons.err >.tmp/implementer/cons.list`, its own call, exit 2 meaning no reader; `cat .tmp/implementer/cons.err`, its own call; then `T="$(sort -u .tmp/implementer/cons.list | tr '\n' ' ') <the task's test files>"; uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`. Never the full suite. Three cases read the repository that encloses their temporary directory and fail under an in-repository `--basetemp` on `9d08c6818` as on the branch: `tests/test_prove_inert.py::test_a_tree_it_cannot_list_is_refused`, `tests/test_prove_inert.py::test_a_cwd_outside_any_repo_is_a_usage_error_not_a_code_change` and `tests/test_ops_daily.py::test_the_deploy_log_is_the_main_checkouts_where_a_worktree_runs_the_pass`; a commit's message names them beside its result line when its run holds them.
- The restart harness's cases are `slow` (`tests/slow-cases.txt`), which `-m "not slow"` deselects: a task that adds or changes one runs it by `-k` in its own step, and a run whose selection holds the race case takes about 100 s for that case alone.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. A runbook page and an engine string literal carry no `spec <NNNNN>`, `D<N>`, `T<NNNN>`, `iter-<N>`, `Phase <N>` or `WP<N>` token (`tests/test_internal_terms_not_operator_visible.py`).
- Commits: Conventional Commits, one subject per change, after a `git -C <the worktree> add <every path the commit changes>` of its own, through `git -C <the worktree> commit -F - <<'EOF'`; the message says what changed and pastes the result line of the test command it names, run over the commit's own tree; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the implementer's own model in place of the placeholder, and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`.
- Probes (this plan's tier is `full`): each arm a task lists runs as its own call on the committed tree, `infra/scripts/mutate-probe.sh --file <file> --control '1,$d' --mutation '<mutation>' -- uv run pytest <test file> -k '<selection>' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Before each arm its pattern's count reads `1`, its own call: `sed -n '<range>p' <file> | grep -c '<pattern>'` for an arm whose mutation opens with a range, `grep -c '<pattern>' <file>` otherwise; the one arm whose pattern is two lines in its range says so. `: > .local/restored-remainder-cancelled/probes-task-<N>.txt` before a task's arms; after each arm its id and the script's last line are appended, its own call. A task's verdicts ride an empty commit through `git -C <the worktree> commit --allow-empty -F - <<'EOF'`, subject `test(engine): <task> proven by infra/scripts/mutate-probe.sh`, its body the probes file pasted whole, then the trailers; it names no test run, the verdicts being its result.
- A helper this plan names in a test (`_executor`, `_record`, `_intent_entry`, `_boundary`, `_executor_errors`, `_submitted_row`, `_pending_plan_entry`, `_restored_order`, `_report`, `_VenueOrders`, `_VenueCancel`, `_gate`, `_cache_config`, `_kill_file`, `StubClient`, `StubCache`, `NOW`, `_TXID`, `executor_module` in `tests/test_engine_executor.py`; `_venue`, `_script_cancel_ack`, `phase_one`, `PAIR`, `SYMBOL`, `QTY`, `PRICE`, `PHASE2_WINDOW` in `tests/test_cache_restart.py`) exists at `9d08c6818`; where a fence's call does not fit its real signature, the case's intent and assertions bind, not the spelling, and the report says what changed.

## Rulings where the spec is silent

- **The new method is `_cancel_closed_copy`, directly above `_recancel`, as Task 1 Step 3's fence writes it.** No `_answered` discard: at the startup pass nothing has answered the row before the sweep. The probe ranges address it from its `def` to `_recancel`'s.
- **The arm is its own `if` directly above `if restored and report is not None:` in `_reconcile_adopted_rows`, and `continue`s.** Its condition reads the copy's closedness off `order.status in _ADOPTED_TERMINAL_STATES`, never `order.is_closed`: the one-door walk sees `copy.status` and not `is_closed`, and the cases' stand-ins carry a `status`.
- **`_recancel` takes `cache_status: str | None = None`**, its signature then one parameter per line as `ruff format` lays it; None keeps both its lines byte for byte.
- **Placement:** Task 1's helper and four cases directly after `test_a_restored_order_the_cache_holds_closed_is_read_at_the_venue_and_the_report_wins`; Task 2's helpers and two cases directly after `test_a_trade_frame_on_a_restored_opener_racing_the_passs_cancel_is_booked_twice_and_the_row_settles_at_the_venues_figure`, and `REREAD_WINDOW` directly after `PHASE2_WINDOW`.
- **`tests/slow-cases.txt` stays sorted**, its header untouched.
- **What a task writes is in the task, verbatim, or printed by its own first command; nothing is written from a description.** The arm, `_cancel_closed_copy` and `_recancel`'s two branches are Task 1 Step 3's fences, the tests, the loopback's switch and the slow-case ids Task 1 Step 1's and Task 2 Step 1's, the decisions-log entries Task 4's and the topic's edits Task 5's; the runbook texts are the spec's *Runbook texts* fences, which Task 3 Step 1 prints from the spec and pastes byte for byte, so the spec's copy is the one copy.

## File structure

- Modify `cli/engine/executor.py`: the sweep's arm; `_cancel_closed_copy`; `_recancel`'s `cache_status` and lines; the restored arm's comment; four docstrings; the `_restored_fills` comment.
- Modify `tests/test_engine_executor.py`: `_ONE_DOOR_CALLERS`' `copy.status` reason; `test_a_restored_order_the_cache_holds_closed_is_read_at_the_venue_and_the_report_wins`; `_closed_copy_executor` and four cases.
- Modify `tests/kraken_loopback.py`: `exec_trade`'s `with_order_qty`.
- Modify `tests/test_cache_restart.py`: `REREAD_WINDOW` and its import of `_GATE_REFRESH`; the racing sibling over both shapes; `_seed_restored_opener`, `_part_fill`, `_before_the_pass` and two cases.
- Modify `tests/slow-cases.txt`, `infra/runbooks/engine-procedures.md`, `infra/runbooks/engine.md`, `docs/research/14.phase6-decisions.md`, `docs/open-topics/T0226-a-restored-order-the-cache-reads-filled-keeps-its-remainder-resting.md`; re-render `docs/open-topics/README.md`.

## Review Focus

1. A closed copy whose order Kraken reports in any status the library knows: only the nine statuses outside the closed map cancel, the six inside it write the row from the report as today. Pinned by Task 1's `test_a_restored_copy_the_library_closed_is_cancelled_by_its_txid_only_while_kraken_reports_the_order_open`, one case per `OrderStatus.variants()` member.
2. A ledgered reducer whose copy reads closed is cancelled, not kept, whatever the gate's level. Pinned by `[kept-reducer]` of Task 1's settle case and the changed `test_a_restored_order_the_cache_holds_closed_is_read_at_the_venue_and_the_report_wins`.
3. A copy the Cache holds open is cancelled through the strategy handle as before, never by txid. Pinned by the existing `test_a_restored_opener_the_venue_reports_open_is_cancelled_by_the_pass_and_a_kept_reducer_is_not`, whose executor has no canceller, and Task 1's `closed-copy-only` arm.
4. Kraken refuses the cancel: the row stays open at the report's figure, the CRITICAL names the hand cancel, and nothing is armed. Pinned by `test_a_startup_cancel_by_txid_kraken_refuses_leaves_the_row_open_names_the_hand_cancel_and_arms_no_re_read`.
5. Kraken answers the cancel and still lists the order open: the re-read pass reads it and sends no second cancel. Pinned by `test_the_re_read_pass_sends_no_second_cancel_for_a_closed_copy_kraken_still_lists_open`. A copy a minted terminal closed keeps today's startup, pinned by the one-door matrix's `reconnect` and `minted-external` rows, unedited.

---

### Task 1: The startup pass cancels a closed copy by its txid (spec D3–D7, D13)

**Files:**
- Modify: `cli/engine/executor.py` (`_reconcile_adopted_rows`, `_recancel`, the docstrings of `read_venue_orders`, `cancel_venue_order`, `_adopt_resting_orders`, the `_restored_fills` comment)
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `_recancel`, `cancel_venue_order` through `self._venue_cancel`, `_arm_reread_after_mint`, `_restored_fills`, `_ADOPTED_TERMINAL_STATES`.
- Produces: `_cancel_closed_copy(self, boundary, row, venue_order_id, report, *, order_id: str, cache_status: str) -> None`; `_recancel(..., cache_status: str | None = None) -> bool`; the two log lines Task 3's runbook texts quote.

- [ ] **Step 1: Write the failing cases.** In `_ONE_DOOR_CALLERS`, the `copy.status` entry of `_reconcile_adopted_rows` reads:

```python
    ("_reconcile_adopted_rows", "copy.status"): (
        "a row outside the restored set takes its Cache order's status; a restored copy's closed status routes its row to "
        "the cancel by txid and names it in the line"
    ),
```

`test_a_restored_order_the_cache_holds_closed_is_read_at_the_venue_and_the_report_wins` gains a canceller and the cancelled row; its docstring's last sentence reads "The row, repaired to 0.0007 by the previous process, stays there: the venue is read and its partial report is the figure, and the order Kraken still lists open is cancelled by its txid, the copy reading closed." Its body after the docstring:

```python
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0007)
    client = StubClient(StubCache(closed_orders=[_restored_order("O-reducer", filled=0.001)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0007"))
    cancel = _VenueCancel()
    ex = _executor(
        tmp_path,
        client=client,
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        venue_cancel=cancel,
        config=_cache_config(tmp_path),
    )
    assert client.cache.order(ClientOrderId("O-reducer")).status == OrderStatus.FILLED

    ex.on_timer(NOW)

    assert ex._restored == {"O-reducer": _TXID} and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], [e.get("event") for e in row["events"] if e.get("event")]) == (
        "canceled",
        0.0007,
        ["recancelled"],
    )
    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")] and client.canceled == []
    assert not _kill_file(tmp_path).exists() and "O-reducer" in ex._attached
```

Directly after it:

```python
def _closed_copy_executor(tmp_path, *, reduce_only=False, status=OrderStatus.ACCEPTED, cancel=None):
    """A restored row, 0 filled, whose Cache copy a `trade` frame with no `order_qty` rewrote to its 0.0004
    filled, FILLED, and whose order Kraken reports in `status` at 0.0004 of 0.001."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=reduce_only, when=earlier, venue_order_id=_TXID)
    copy = _restored_order("O-restored", filled=0.0004, quantity="0.0004")
    assert copy.status == OrderStatus.FILLED
    client = StubClient(StubCache(closed_orders=[copy]))
    venue = _VenueOrders(_report(_TXID, status, filled_qty="0.0004"))
    cancel = cancel if cancel is not None else _VenueCancel()
    ex = _executor(
        tmp_path,
        client=client,
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        venue_cancel=cancel,
        config=_cache_config(tmp_path),
    )
    return ex, client, venue, cancel, earlier


@pytest.mark.parametrize("reduce_only, kind", [(False, "restored opener"), (True, "kept reducer")], ids=["opener", "kept-reducer"])
def test_a_restored_copy_the_library_closed_while_kraken_lists_the_order_open_is_cancelled_by_its_txid_and_the_re_read_pass_settles_it(
    tmp_path, reduce_only, kind
):
    ex, client, venue, cancel, earlier = _closed_copy_executor(tmp_path, reduce_only=reduce_only)

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("canceled", 0.0004)
    assert [e.get("event") for e in row["events"] if e.get("event")] == ["reconciled", "recancelled"]
    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")] and client.canceled == []
    assert [r.getMessage() for r in records if "by its txid" in r.getMessage()] == [
        f"cancelled O-restored (Kraken {_TXID}) at Kraken by its txid -- Kraken listed it open (ACCEPTED, 0.0004 of 0.001 "
        "filled) while the Cache reads it FILLED, which no cancel through the Cache reaches; its row reads canceled"
    ]
    assert [r.levelname for r in records if "by its txid" in r.getMessage()] == ["WARNING"]
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending"

    venue.reports = [_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0007")]
    ex._evaluate(NOW)  # the gate read armed, as the idle refresh reads it
    ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("canceled", pytest.approx(0.0007))
    assert [e.get("qty") for e in row["events"] if e.get("event") == "reconciled"] == [0.0004, pytest.approx(0.0003)]
    assert len(cancel.calls) == 1 and len(venue.calls) == 2
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"], entry["reasons"]) == (
        "revoked",
        pytest.approx(0.0007),
        [f"the {kind} ended partly filled"],
    )


@pytest.mark.parametrize("status", list(OrderStatus.variants()), ids=lambda s: s.name)
def test_a_restored_copy_the_library_closed_is_cancelled_by_its_txid_only_while_kraken_reports_the_order_open(tmp_path, status):
    ex, client, venue, cancel, earlier = _closed_copy_executor(tmp_path, status=status)

    with _executor_errors(level=logging.WARNING):
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    ended = status in executor_module._ADOPTED_TERMINAL_STATES
    assert cancel.calls == ([] if ended else [(_TXID, "BTC/EUR.KRAKEN")])
    assert row["state"] == (executor_module._ADOPTED_TERMINAL_STATES[status] if ended else "canceled")
    assert client.canceled == []


def test_a_startup_cancel_by_txid_kraken_refuses_leaves_the_row_open_names_the_hand_cancel_and_arms_no_re_read(tmp_path):
    ex, client, venue, cancel, earlier = _closed_copy_executor(
        tmp_path, cancel=_VenueCancel(raises=RuntimeError("EOrder:Unknown order"))
    )

    with _executor_errors(level=logging.CRITICAL) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("accepted", 0.0004)
    assert [r.getMessage() for r in records] == [
        f"the startup pass's cancel of O-restored (Kraken {_TXID}) raised or was refused -- Kraken lists it open while the "
        "Cache reads it FILLED, so it may still rest at Kraken: cancel it by hand on Kraken's open-orders page"
    ]
    assert ex._reread_tries == 0 and "O-restored" not in ex._restored_fills
    ex._evaluate(NOW)
    ex.on_timer(NOW + timedelta(seconds=5))
    assert len(venue.calls) == 1 and len(cancel.calls) == 1
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending"


def test_the_re_read_pass_sends_no_second_cancel_for_a_closed_copy_kraken_still_lists_open(tmp_path):
    """The startup's cancel returned and Kraken still lists the order open, `{"count": 0}`'s shape: the
    re-read pass reads it and settles the row's intent, and sends no cancel of its own."""
    ex, client, venue, cancel, earlier = _closed_copy_executor(tmp_path)
    with _executor_errors(level=logging.WARNING):
        ex.on_timer(NOW)

    ex._evaluate(NOW)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert len(cancel.calls) == 1 and len(venue.calls) == 2
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("canceled", 0.0004)
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "revoked"
```

- [ ] **Step 2: Run them, expect FAIL.** `uv run pytest tests/test_engine_executor.py -k 'cancelled_by_its_txid or arms_no_re_read or no_second_cancel or cache_holds_closed_is_read' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` reads `14 failed, 6 passed, 808 deselected`: the nine open statuses of the enumeration, both settle cases, the refusal, the second-cancel case and the changed case fail; the six closed statuses pass.

- [ ] **Step 3: Implement.** In `cli/engine/executor.py`:
  - In `_reconcile_adopted_rows`, directly above `if restored and report is not None:`:

```python
                    if (
                        restored
                        and report is not None
                        and not recancel
                        and order.status in _ADOPTED_TERMINAL_STATES
                        and report.order_status not in _ADOPTED_TERMINAL_STATES
                    ):
                        self._cancel_closed_copy(
                            boundary,
                            row,
                            venue_order_id,
                            report,
                            order_id=str(order.client_order_id),
                            cache_status=order.status.name,
                        )
                        continue
```

    and the restored arm's comment's last clause reads `cancelled or kept by the startup's classification, or above where its copy reads closed.`
  - `_cancel_closed_copy`, directly above `_recancel`:

```python
    def _cancel_closed_copy(
        self, boundary: datetime, row: dict, venue_order_id: str, report, *, order_id: str, cache_status: str
    ) -> None:
        """The startup pass's cancel of a restored order Kraken reports open while its Cache copy reads closed
        (`cache_status`): a `trade` frame with no `order_qty` rewrites a restored copy to its filled quantity and
        FILLED, and a double booking can carry one to FILLED ahead of Kraken's figure. The strategy handle sends
        nothing for a closed order and the classification reads the open orders alone, so the cancel goes by txid
        (`_recancel`). A fill racing it is one the library drops against the closed copy, so the row then waits for
        the re-read pass's read, which books it and writes the intent."""
        self._recancel(boundary, row, venue_order_id, report, order_id=order_id, cache_status=cache_status)
        if row.get("state") != "canceled":
            return
        self._restored_fills.add(row["client_order_id"])
        self._arm_reread_after_mint()
```

  - `_recancel` gains `cache_status: str | None = None`. In its docstring, whitespace-normalised: the first clause reads "The re-read pass's cancel of an order the venue still reports open, and the startup pass's of a restored copy that reads `cache_status` (`_cancel_closed_copy`), whose lines name it: the report's fills"; "; a fill landing between the two is in the row once the stream delivers it," reads "; on the re-read pass's, a fill landing between the two is in the row once the stream delivers it,"; "which the page has the operator read. A cancel" reads "which the page has the operator read; on the startup pass's, the library drops that fill against the closed copy, and the re-read pass `_cancel_closed_copy` arms books it. A cancel"; and "a restored row's the caller writes once the row reads `canceled` (`_settle_restored_intent`), from the repair's answer, which this returns;" reads "a restored row's the re-read pass writes (`_settle_restored_intent`), after its own re-cancel once the row reads `canceled`, from the repair's answer, which this returns, and after the startup pass's from its own read of the row;". Its `except` body, and its lines from `row["state"] = "canceled"` to its last `return answered`, read as the two fences below: each new literal breaks where they break it, so each probe pattern of Step 6 sits on one source line, and without a `cache_status` both of today's lines are logged byte for byte.

```python
        except Exception:
            if cache_status is None:
                logger.critical(
                    "the re-read pass's cancel of %s raised or was refused -- the order may still rest at Kraken: cancel it "
                    "by hand on Kraken's open-orders page",
                    label,
                    exc_info=True,
                )
            else:
                logger.critical(
                    "the startup pass's cancel of %s raised or was refused -- Kraken lists it open while the Cache reads it "
                    "%s, so it may still rest at Kraken: cancel it by hand on Kraken's open-orders page",
                    label,
                    cache_status,
                    exc_info=True,
                )
            return answered
```

```python
        row["state"] = "canceled"
        if cache_status is None:
            logger.warning(
                "re-cancelled %s -- it rested at Kraken (%s) after a terminal this engine minted; its row reads canceled",
                label,
                report.order_status.name,
            )
        else:
            logger.warning(
                "cancelled %s at Kraken by its txid -- Kraken listed it open (%s, %.10g of %.10g filled) while the Cache "
                "reads it %s, which no cancel through the Cache reaches; its row reads canceled",
                label,
                report.order_status.name,
                float(report.filled_qty),
                float(report.quantity),
                cache_status,
            )
        return answered
```

  - The `_restored_fills` comment in `__init__`, "The restored rows a fill reached and the re-read pass has not repaired since: the credit is nothing (`_fill_credit`) and the pass repairs the row from the venue's cumulative figure.", reads "The restored rows a fill reached, or the startup pass cancelled by its txid (`_cancel_closed_copy`), and the re-read pass has not repaired since: a fill's credit is nothing (`_fill_credit`) and the pass repairs the row from the venue's cumulative figure."
  - `read_venue_orders`' docstring: "and `cancel_venue_order` follows it on the same terms;" reads "and `cancel_venue_order` follows it on the same terms -- at startup, after this read and before any cancel through the strategy handle;". `cancel_venue_order`'s: "the re-read pass's cancel of an order the Cache holds closed by a terminal this engine minted, which the strategy handle refuses to cancel" reads "the re-read pass's cancel of an order the Cache holds closed by a terminal this engine minted, and the startup pass's of a restored order whose copy the library closed while Kraken lists it open, both of which the strategy handle refuses to cancel". `_adopt_resting_orders`': "and one it reports open is classified as an adopted one is -- cancelled unless its row is a ledgered reducer." reads "and one it reports open is cancelled by txid in the sweep when its copy reads closed, whatever its row (`_cancel_closed_copy`), and otherwise classified as an adopted one is -- cancelled unless its row is a ledgered reducer."

- [ ] **Step 4: Run them, expect PASS.** Step 2's command reads `20 passed, 808 deselected`; `uv run pytest tests/test_engine_executor.py -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` reads `828 passed`, the one-door matrix and its walk unedited but for the reason.

- [ ] **Step 5: Commit** `fix(engine): the startup pass cancels by txid a restored order Kraken lists open while the Cache reads it closed`, after the gate, the per-commit run's result line in the body.

- [ ] **Step 6: Probes**, on `cli/engine/executor.py`, each `-- uv run pytest tests/test_engine_executor.py -k '<selection>' …`. "In the sweep" is the range `/def _reconcile_adopted_rows/,/def _cancel_closed_copy/`, "in the cancel" `/def _cancel_closed_copy/,/def _recancel/`, "in the re-cancel" `/def _recancel/,/def _mark_unmatched/`:
  - `arm-fires`: `-k 'cancelled_by_its_txid_and_the_re_read_pass_settles_it'`, mutation `/def _reconcile_adopted_rows/,/def _cancel_closed_copy/s/and not recancel$/and False/`.
  - `open-only`: `-k 'only_while_kraken_reports_the_order_open'`, mutation `/def _reconcile_adopted_rows/,/def _cancel_closed_copy/s/and report.order_status not in _ADOPTED_TERMINAL_STATES$/and True/`.
  - `closed-copy-only`: `-k 'restored_opener_the_venue_reports_open_is_cancelled_by_the_pass'`, mutation `/def _reconcile_adopted_rows/,/def _cancel_closed_copy/s/and order.status in _ADOPTED_TERMINAL_STATES$/and True/`.
  - `startup-only`: `-k 'no_second_cancel'`, mutation `/def _reconcile_adopted_rows/,/def _cancel_closed_copy/s/and not recancel$/and True/`.
  - `race-read-armed`: `-k 'cancelled_by_its_txid_and_the_re_read_pass_settles_it'`, mutation `/def _cancel_closed_copy/,/def _recancel/{/self._arm_reread_after_mint()/d}`.
  - `race-row-joins`: `-k 'cancelled_by_its_txid_and_the_re_read_pass_settles_it'`, mutation `/def _cancel_closed_copy/,/def _recancel/{/self._restored_fills.add(row\["client_order_id"\])/d}`.
  - `refused-arms-nothing`: `-k 'arms_no_re_read'`, mutation `/def _cancel_closed_copy/,/def _recancel/s/if row.get("state") != "canceled":/if False:/`.
  - `warning-level`: `-k 'cancelled_by_its_txid_and_the_re_read_pass_settles_it'`, mutation `/def _recancel/,/def _mark_unmatched/s/logger.warning(/logger.info(/` — its pattern counts `2` in the range, the re-read pass's line and the startup's, and the selected case reads the startup's.
  - `warning-text`: `-k 'cancelled_by_its_txid_and_the_re_read_pass_settles_it'`, mutation `s/which no cancel through the Cache reaches; its row reads canceled/its row reads canceled/`.
  - `critical-text`: `-k 'arms_no_re_read'`, mutation `s/%s, so it may still rest at Kraken: cancel it by hand/%s, so it may still rest at Kraken/`.
  - `kept-reducer`: `-k '(settles_it and kept) or cache_holds_closed_is_read'`, mutation `/def _reconcile_adopted_rows/,/def _cancel_closed_copy/s/and not recancel$/and not recancel and row["order"].get("reduce_only") is not True/`.

  Then the empty commit, `test(engine): the startup pass's cancel by txid proven by infra/scripts/mutate-probe.sh`.

### Task 2: Both frame shapes, both orderings and a fill racing the cancel, on the restart harness (spec D2, D10, D12)

**Files:**
- Modify: `tests/kraken_loopback.py`, `tests/slow-cases.txt`
- Test: `tests/test_cache_restart.py`

**Interfaces:**
- Consumes: Task 1's cancel and its WARNING line; `_phase_one`'s order (0.4 of 1.0 filled, resting) through the `phase_one` fixture.
- Produces: `exec_trade(..., with_order_qty: bool = True)`; nothing a later task calls.

- [ ] **Step 1: Write the switch and the cases.** In `tests/kraken_loopback.py`, `exec_trade` gains the keyword after `side`, its docstring the sentences after its first, and its body the deletion before the `cl_ord_id` test:

```python
    side: str = "buy",
    with_order_qty: bool = True,
) -> dict[str, Any]:
    """The `trade` execution frame for one fill of `last_qty`, carrying both halves upstream parses: the
    status half (`order_status`, `cum_qty`) and the fill half (`exec_id`, `last_qty`). `with_order_qty`
    False leaves `order_qty` out, as Kraken's one documented `trade` example does. On `2.0.0rc9.dev20261106`,
    on an order an earlier process placed, the frame with it is booked twice, and the frame without it
    rewrites the order to its filled quantity unless a cancel is pending on it, when it is booked twice too."""
```

```python
    if not with_order_qty:
        del data["order_qty"]
    if cl_ord_id is not None:
        data["cl_ord_id"] = cl_ord_id
    return data
```

In `tests/test_cache_restart.py`, `from cli.engine.executor import _GATE_REFRESH` joins the imports between `cli.engine.execledger`'s and `cli.engine.probeplan`'s, and directly after `PHASE2_WINDOW = 20`:

```python
# A restart's window past the gate's first idle refresh, `_GATE_REFRESH` after the executor's construction:
# where nothing rests, the re-read pass waits for that refresh to read the engine armed.
REREAD_WINDOW = int(_GATE_REFRESH.total_seconds()) + 20
```

The racing sibling takes both shapes: above its `def`, `@pytest.mark.parametrize("with_order_qty", [True, False], ids=["with-order_qty", "without-order_qty"])`; its parameters `phase_one, with_order_qty`; its `lb.exec_trade(` call's last line `exec_id="TLOOP3-AAAAA-AAAAAA", trade_id=1003, with_order_qty=with_order_qty,`; its assertions unchanged. Directly after it:

```python
def _seed_restored_opener(venue: lb.KrakenLoopback, wire: dict) -> None:
    """What the venue holds for `_phase_one`'s order at the restart: open, 0.4 of 1.0 filled, its trade and its margin position."""
    venue.balances = {"ZEUR": lb.balance("1000.00000000")}
    venue.open_orders[wire["txid"]] = dict(
        lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=wire["opened_at"]),
        oflags="fciq",
        vol_exec="0.40000000",
        price="150.00000",
        cost="60.00000",
    )
    venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
        wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
    )
    venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
        lb.margin_position(PAIR, volume="0.40000000", time=wire["filled_at"]), ordertxid=wire["txid"], cost="60.00000"
    )


def _part_fill(
    venue: lb.KrakenLoopback, exec_: lb.WsPeer, wire: dict, *, last: float, cum: float, n: int, with_order_qty: bool
) -> None:
    """One part-fill of `_phase_one`'s order: the venue's listings move, then the stream's `trade` frame says so."""
    trade_id = f"TLOOP{n}-AAAAA-AAAAAA"
    venue.open_orders[wire["txid"]].update(vol_exec=f"{cum:.8f}", cost=f"{cum * PRICE:.5f}")
    venue.trades[trade_id] = lb.trade_row(
        wire["txid"], PAIR, vol=f"{last:.8f}", price="150.00", trade_id=1000 + n, time=time.time()
    )
    venue.positions["TPOSLP-AAAAA-BBBBBB"].update(vol=f"{cum:.8f}", cost=f"{cum * PRICE:.5f}")
    exec_.send_execution(
        lb.exec_trade(
            wire["txid"], wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=last, cum_qty=cum,
            exec_id=trade_id, trade_id=1000 + n, with_order_qty=with_order_qty,
        )
    )  # fmt: skip


def _before_the_pass(exec_: lb.WsPeer, then) -> None:
    """`then` a second after the execution socket subscribes."""

    def later() -> None:
        if exec_.subscribed.wait(60):
            time.sleep(1)
            then()

    threading.Thread(target=later, daemon=True).start()


@pytest.mark.parametrize("with_order_qty", [False, True], ids=["without-order_qty", "with-order_qty"])
def test_a_part_fill_landing_before_the_startup_pass_leaves_no_remainder_resting_at_kraken(phase_one, with_order_qty):
    """The restored opener, 0.4 of 1.0 filled, takes a `trade` frame (last 0.2, cumulative 0.6) before the
    startup pass. Without `order_qty` the library rewrites its copy to 0.6, FILLED, which no cancel through
    the Cache reaches, and the pass cancels the order at Kraken by its txid; with it, the copy is booked
    twice and stays open, and the pass cancels it through the Cache. Either way Kraken's order ends."""
    valkey, node, wire, _ = phase_one
    with _venue() as (venue, data, exec_):
        _seed_restored_opener(venue, wire)
        _script_cancel_ack(venue, exec_, wire)
        _before_the_pass(exec_, lambda: _part_fill(venue, exec_, wire, last=0.2, cum=0.6, n=3, with_order_qty=with_order_qty))
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        cancels = list(venue.cancel_forms)
        resting = dict(venue.open_orders)
        closed = dict(venue.closed_orders)

    assert record["errors"] == [], record["errors"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert (resting, closed[wire["txid"]]["status"], closed[wire["txid"]]["vol_exec"]) == ({}, "canceled", "0.60000000")
    [row] = node.rows()
    cid = row["client_order_id"]
    assert (row["state"], row["filled_qty"]) == ("canceled", pytest.approx(0.6))
    [order] = record["at_end"]["orders"]
    if with_order_qty:
        assert (order["status"], order["quantity"], order["filled_qty"]) == ("CANCELED", "1.00000000", "0.80000000")
        assert f"canceling restored order {cid}, partial -- the ledger does not carry it as a resting reducer" in record["log"]
        assert "at Kraken by its txid" not in record["log"]
    else:
        assert (order["status"], order["quantity"], order["filled_qty"]) == ("FILLED", "0.60000000", "0.60000000")
        assert (
            f"cancelled {cid} (Kraken {wire['txid']}) at Kraken by its txid -- Kraken listed it open (ACCEPTED, 0.6 of 1 "
            "filled) while the Cache reads it FILLED, which no cancel through the Cache reaches; its row reads canceled"
        ) in record["log"]
        assert f"canceling restored order {cid}" not in record["log"]
        assert [e.get("event") for e in row["events"]][-1] == "recancelled"


def test_a_part_fill_racing_the_startup_passs_cancel_by_txid_is_dropped_by_the_library_and_the_re_read_pass_books_it(
    phase_one,
):
    """The rewrite's second part-fill (last 0.3, cumulative 0.9) lands inside the pass's cancel by txid. The
    library rejects it against the closed copy, so no event reaches the row, which reads 0.6 at the cancel;
    the re-read pass, armed by the cancel and run once the gate's first idle refresh has read the engine
    armed, reads Kraken's closed record, repairs the row to 0.9 and writes the intent."""
    valkey, node, wire, _ = phase_one
    with _venue() as (venue, data, exec_):
        _seed_restored_opener(venue, wire)
        _script_cancel_ack(venue, exec_, wire)
        ack = venue.on_cancel_order

        def fill_then_ack(form: dict) -> None:
            _part_fill(venue, exec_, wire, last=0.3, cum=0.9, n=4, with_order_qty=False)
            ack(form)

        venue.on_cancel_order = fill_then_ack
        _before_the_pass(exec_, lambda: _part_fill(venue, exec_, wire, last=0.2, cum=0.6, n=3, with_order_qty=False))
        record = node.run(2, venue, data, exec_, window=REREAD_WINDOW)
        closed = dict(venue.closed_orders)

    assert record["errors"] == [], record["errors"]
    assert (closed[wire["txid"]]["status"], closed[wire["txid"]]["vol_exec"]) == ("canceled", "0.90000000")
    assert "fill.last_qty=0.30000000, would result in filled_qty=0.90000000" in record["log"]
    [order] = record["at_end"]["orders"]
    assert (order["status"], order["filled_qty"]) == ("FILLED", "0.60000000")
    [row] = node.rows()
    assert (row["state"], row["filled_qty"]) == ("canceled", pytest.approx(0.9))
    assert [e.get("event") for e in row["events"] if e.get("event") in ("reconciled", "recancelled")] == [
        "reconciled", "recancelled", "reconciled",
    ]  # fmt: skip
    [intent] = node.intents()
    assert (intent["outcome"], intent["filled_qty"], intent["reasons"]) == (
        "revoked", pytest.approx(0.9), ["the restored opener ended partly filled"],
    )  # fmt: skip
```

In `tests/slow-cases.txt`, the racing sibling's line is replaced by its two ids and the three new ids join, the list sorted:

```
tests/test_cache_restart.py::test_a_part_fill_landing_before_the_startup_pass_leaves_no_remainder_resting_at_kraken[with-order_qty]
tests/test_cache_restart.py::test_a_part_fill_landing_before_the_startup_pass_leaves_no_remainder_resting_at_kraken[without-order_qty]
tests/test_cache_restart.py::test_a_part_fill_racing_the_startup_passs_cancel_by_txid_is_dropped_by_the_library_and_the_re_read_pass_books_it
tests/test_cache_restart.py::test_a_trade_frame_on_a_restored_opener_racing_the_passs_cancel_is_booked_twice_and_the_row_settles_at_the_venues_figure[with-order_qty]
tests/test_cache_restart.py::test_a_trade_frame_on_a_restored_opener_racing_the_passs_cancel_is_booked_twice_and_the_row_settles_at_the_venues_figure[without-order_qty]
```

- [ ] **Step 2: Run them, expect PASS on Task 1's tree.** `uv run pytest tests/test_cache_restart.py -k 'part_fill or racing_the_passs_cancel' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` reads `5 passed`; `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_cache_restart.py -n 12 -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` reads `22 passed`, the harness's other cases on Task 1's tree; `uv run pytest tests/test_slow_cases.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` reads `2 passed`. On the tree before Task 1 the first selection reads `2 failed, 3 passed`, the `[without-order_qty]` case finding no `CancelOrder` and the race case no closed order (the spec's measured basis); this task's probes are what prove each case can fail on the branch.

- [ ] **Step 3: Commit** `test(engine): the restart harness proves both trade-frame shapes before and inside the startup pass's cancel, and a fill racing the cancel by txid`, after the gate, the per-commit run's result line and Step 2's two lines in the body.

- [ ] **Step 4: Probes**, each `-- uv run pytest tests/test_cache_restart.py -k '<selection>' …`; "in the sweep" as in Task 1, "in the pass" `/def _adopt_resting_orders/,/def _settle_pending_intents/`:
  - `harness-arm-fires`: `--file cli/engine/executor.py`, `-k 'part_fill_landing_before_the_startup_pass and without'`, mutation `/def _reconcile_adopted_rows/,/def _cancel_closed_copy/s/and not recancel$/and False/`.
  - `harness-race-arm-fires`: `--file cli/engine/executor.py`, `-k 'part_fill_racing_the_startup'`, the same mutation.
  - `before-with-handle`: `--file cli/engine/executor.py`, `-k 'part_fill_landing_before_the_startup_pass and not without'`, mutation `/def _adopt_resting_orders/,/def _settle_pending_intents/s/self._client.cancel_order(order.client_order_id)/pass/`.
  - `race-sibling-without`: `--file cli/engine/executor.py`, `-k 'racing_the_passs_cancel and without'`, the same mutation.
  - `loopback-switch`: `--file tests/kraken_loopback.py`, `-k 'part_fill_landing_before_the_startup_pass and without'`, mutation `s/^        del data\["order_qty"\]$/        pass/`.

  Not an arm: Task 1's `race-read-armed` against the harness's race case reads `SURVIVED`, since there the rewrite's inferred fill arms the pass first on the event path (the spec's *Tests and guards*); Task 1's unit case holds it. Then the empty commit, `test(engine): the harness's frame shapes and orderings proven by infra/scripts/mutate-probe.sh`.

### Task 3: The operator's read (spec D13)

**Files:**
- Modify: `infra/runbooks/engine-procedures.md` (the rung-3 restart section's items 3 and 4), `infra/runbooks/engine.md` (`zcrypto-engine-error-logs` step 2)

**Interfaces:**
- Consumes: Task 1's two lines.
- Produces: nothing a later task calls.

- [ ] **Step 1: Apply the spec's *Runbook texts*, verbatim.** Print them first, its own call: `sed -n '/^## Runbook texts$/,/^## Deployment$/p' docs/specs/00161-restored-remainder-cancelled-design.md` shows three fences — item 3's line, item 4's paragraph and the error-logs item, in that order — and each fence's body is pasted from that output byte for byte, never retyped. In `engine-procedures.md`'s rung-3 restart item 3, the line below — `grep -c -F` the whole line first: `1`; its pattern's shorter stretches recur in the probe-window and rung-2 sections, which stay — gains `by its txid|` after `fill on restored order|`, and reads as the spec's first fence:

```
   sudo docker logs --since 30m zcrypto-engine 2>&1 | grep -E 'cache restore|Received [0-9]|Reconciliation complete|the venue holds|Unresolved positions|Failed to get mass status|could not be read|fill on restored order|instrument not in cache|order event ignored|Failed to load account|Error on cache insert|bounded fill|CRITICAL'
```

   Item 4's sentences from "A part-fill landing ahead of the start's cancel can leave the Cache reading that order filled" to "take Kraken's exports as the book." are replaced by the second fence's paragraph. In `engine.md`, the third fence's item goes directly before the item that opens `**`the execution watchdog froze the loop -- socket … down past the 30s grace …`**`.

- [ ] **Step 2: Run** the per-commit tests with `tests/test_internal_terms_not_operator_visible.py` as the task's test file; `uv run pre-commit run -a` leaves both pages unchanged (`mdformat` and `guidance-guard` passed the texts in the scratch tree).

- [ ] **Step 3: Commit** `docs(runbooks): the rung-3 restart read and the error-logs page name the startup pass's cancel by txid and its refusal`, the per-commit run's result line in the body.

### Task 4: The decisions-log entries (spec D1, D2, D4–D7, D15)

**Files:**
- Modify: `docs/research/14.phase6-decisions.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing a later task calls.

- [ ] **Step 1: Append, verbatim, after the file's last line**, one blank line between entries as the log holds them:

```markdown
[00161] How is the remainder a restored order's rewritten copy leaves resting at Kraken handled, before rung 3's first attended week and after it? (Decision: 1)
  The coordinator's recommendation, its message of 2026-11-07T09:58:17.692Z, verbatim: "**The unmanaged remainder:** I recommend the `kraken open-orders` read at the rung-3 restart check for entry, and the engine fix after the first attended week." The owner's word, 2026-11-07T10:02:30.560Z, verbatim: "merge #831. handle the unmanged remainder as recommended".
  1. **The `kraken open-orders` read at the rung-3 restart check for entry, and the engine fix after the first attended week (recommended).** **Taken** (owner, 2026-11-07).
  A plain message on the one course recommended, no other laid out. The read is `engine-procedures.md`'s rung-3 restart item 4; the fix is spec 00161.

[00161] In what order are T0226's three parts taken: the engine fix, a real Kraken `trade` frame's capture, and #5315's triggered fill? (Decision: 1)
  Asked 2026-11-17T00:36:38.221Z, verbatim: "T0226 has three parts. (1) The engine fix: at startup, compare Kraken's open orders with the Cache and cancel at Kraken any ledgered order Kraken still lists open while the Cache reads it closed. That cancels the stranded remainder whatever the stream frame's shape. (2) Capturing one real Kraken `trade` frame, to settle whether it carries `order_qty`. (3) The triggered-fill test you asked not to be forgotten (#5315). (2) and (3) need a key you mint and a USDC/EUR round trip you place, in an inter-cycle gap. In what order?". Answered 2026-11-17T01:30:14.214Z, verbatim: "Fix now, reads later (Recommended)".
  1. **Fix now, reads later (Recommended).** I spec and build the fix now, proven on the loopback with both frame shapes and both orderings. (2) and (3) become one attended session on your key in a gap you pick. T0226 goes partial until that session; the fix rides the same converge as T0229 and T0227. **Taken** (owner, 2026-11-17).
  2. **Reads first, then the fix.** We schedule the key and the USDC/EUR round trip first, record the real frame and the triggered fill, then spec the fix on the measured frame shape. The fix and the converge wait for that session.

[00161] How does the startup pass's cancel reach Kraken for a restored order whose Cache copy reads closed? (Decision: 3)
  1. **The strategy handle's `cancel_order`** — measured on the pinned wheel: `Cannot cancel order: state is Filled`, nothing sent.
  2. **The strategy handle's `cancel_all_orders`** — measured: it reads the open, emulated and in-flight orders and sends nothing; it would cancel the strategy's other open orders on the instrument, and the red-button test refuses it outside flatten.
  3. **By txid through `cancel_venue_order`, by way of `_recancel`** — the re-read pass's existing REST `CancelOrder` on the bare client, after the startup read and before any cancel through the handle; measured to end the order.
  Decided by the spec's author: the other two send nothing.

[00161] Which rows does the startup pass cancel by txid? (Decision: 1)
  1. **Every restored row the ledger holds open whose Kraken report reads open and whose Cache copy reads closed, a ledgered reducer included, at any gate level** — the ruling's "any ledgered order"; a closed copy rejects a kept reducer's later fills with no event.
  2. **Openers alone, a ledgered reducer kept as the classification keeps one** — keeps an order whose fills the engine cannot see.
  Decided by the spec's author. A copy a minted terminal closed is left as today, on the owner's ruling (the last `[00161]` entry).

[00161] Where does the comparison run: the startup pass alone, or the re-read pass too? (Decision: 1)
  1. **The startup pass alone** — the ruling's "at startup"; a kept reducer's copy a frame closes after the startup pass rests until a next start inside the row's two UTC days, a shape rung 3's spot rows never reach.
  2. **Both passes** — cancels mid-process a reducer the startup pass chose to keep, and needs a bound on repeated cancels.
  Decided by the spec's author.

[00161] How does a fill that races the startup pass's cancel reach the row? (Decision: 1)
  1. **The re-read pass, armed by the cancel, reads Kraken's closed record** — it books the fill the library dropped against the closed copy and writes the intent; measured, about a minute on where nothing rests.
  2. **Nothing until a restart** — the row and its intent short of the fill until a start inside the window repairs them.
  3. **A second read inline after the cancel** — one more synchronous signed read at startup, with failure handling of its own.
  Decided by the spec's author.

[00161] Does the startup pass also cancel by txid a restored copy a minted terminal closed, which Kraken still lists open at a restart? (Decision: 1)
  Asked 2026-11-17T02:52:54.552Z, verbatim: "Spec 00161 (T0226): at startup the engine will cancel by txid any order it placed that Kraken still lists open while its restored Cache copy reads closed. One neighbouring shape is different: an order whose restored copy a minted terminal closed (the engine itself recorded the cancel or fill, which Kraken never confirmed). Today a restart pages CRITICAL for that one and you cancel it by hand. Should the startup pass cancel it automatically too?". Answered 2026-11-17T06:39:31.375Z, verbatim: "Leave it as today (Recommended)".
  1. **Leave it as today (Recommended).** The startup CRITICAL still pages and you cancel by hand; the re-read pass re-cancels it when a mint in the same process arms it. It needs a restart between a mint and the re-read pass, and it isn't the silent remainder T0226 is about. Cost: one page and one hand cancel. **Taken** (owner, 2026-11-17).
  2. **Cancel it at startup too.** The paged hand cancel becomes an unpaged automatic one. Cost: 28 measured cases of the one-door test matrix change their expected values, so its reconnect and minted-external rows must be re-derived.
```

- [ ] **Step 2: Run** `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, which reads `50 passed`; the per-commit lister finds no reader (exit 2).

- [ ] **Step 3: Commit** `docs(research): the [00161] entries, the owner's three rulings on T0226 and the startup cancel's four calls`, the run's result line in the body.

### Task 5: T0226 to `partial` (the `topic-ops` skill)

**Files:**
- Modify: `docs/open-topics/T0226-a-restored-order-the-cache-reads-filled-keeps-its-remainder-resting.md`, `docs/open-topics/README.md` (re-rendered)

**Interfaces:**
- Consumes: the spec's and the plan's paths.
- Produces: nothing.

- [ ] **Step 1: Read the heading set**, its own call: `grep '^#' docs/open-topics/T0226-a-restored-order-the-cache-reads-filled-keeps-its-remainder-resting.md` prints the H1 and `## Context — what`, `## Why this matters`, `## Findings so far`, `## Suggested next steps`.

- [ ] **Step 2: Edit the topic.** Each anchor below reads `1` under `grep -c -F -e '<anchor>'` first, its enclosing section named.
  - The frontmatter's two lines read:

```yaml
status: partial
ripe_when: 'an activity: the owner''s attended session on a key the owner mints, in an inter-cycle gap the owner picks, that records a real Kraken `trade` frame and takes nautilus_trader #5315''s triggered fill, its entry in `docs/reference/rung3/days.md`; check: `grep -c -i "triggered fill" docs/reference/rung3/days.md` prints at least 1'
```

  - Between `## Findings so far`'s last bullet and `## Suggested next steps`:

```markdown
## Done so far

- The engine fix, `docs/specs/00161-restored-remainder-cancelled-design.md` and `docs/plans/00161-restored-remainder-cancelled.md`: the startup pass cancels at Kraken, by its txid, a restored order the ledger holds open that Kraken lists open while the Cache's copy reads closed, whatever the frame's shape, and the re-read pass then books a fill that raced the cancel. Proven on the loopback with the frame with and without `order_qty`, landing before the startup pass's cancel and inside it (`tests/test_cache_restart.py`). It ships on the engine image with T0229's and T0227's fixes, one converge, the fleet's concern.
- Spec 00120 D7's measurement, re-taken on a frame without `order_qty` (spec 00161's measured basis): the pass's cancel still bounds a frame inside it, booked twice on either shape; on a kept reducer the frame rewrites the copy instead, its remainder cancelled at a next start inside the row's two UTC days.
```

  - In `## Suggested next steps`, the first bullet's opening `- Record a real `trade` frame at the next funded fill, with` reads `- Both reads below are one attended session, on the owner's ruling of 2026-11-17. Record a real `trade` frame at the session's fill, with`; in the second, `and record the txids in `docs/reference/rung3/days.md`. Its frames` reads `and record the txids in `docs/reference/rung3/days.md` under an entry that names the triggered fill. Its frames`; the third bullet, `- Spec the fix: …`, goes whole.

- [ ] **Step 3: Re-render the index**, its own call: `uv run python infra/scripts/topics-index.py`; T0226's line leaves `## Open` for `## Partially done` with the new trigger. Read the heading set again (Step 1's command): Step 1's five and `## Done so far`, six, the new one between `## Findings so far` and `## Suggested next steps`.

- [ ] **Step 4: Run** the per-commit tests (`tests/test_merge_gate.py`, `tests/test_open_topics_frontmatter.py`, `tests/test_topics_index.py`).

- [ ] **Step 5: Commit** `docs(open-topics): T0226 partial, the engine fix done and the attended session's two reads left`, the run's result line in the body.
