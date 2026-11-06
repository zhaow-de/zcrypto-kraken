# The engine pages a position the library's reconciliation booked Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A position holding an order nautilus's reconciliation minted pages the main channel, at the first start that books it, and changes nothing the engine does.

**Architecture:** `venuestate.reconciliation_booked_positions(cache)` is the one reader (D1). `ProbeExecutor._publish_reconciliation_positions` reads it before each book read and on the idle refresh, logs one WARNING per position per process and sets `zcrypto_exec_reconciliation_positions` (D2, D3, D4). `zcrypto-engine-reconciliation-position` pages on that gauge, and `engine.md` says what to do (D4, D5). A case on the real wheel holds the tag (D6).

**Tech Stack:** Python 3.14, pytest, `nautilus-trader` 2.0.0rc9.dev20261101, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00157-reconciliation-position-page-design.md`

## Global Constraints

- The spec is the authority; where it is silent this plan rules, in the task the ruling binds.
- The tasks run in this order so that each commit is green. The guards over a published family read from the family to its panel and rule, outside `T`, so a gauge committed ahead of its rule and panel is a red commit; a rule and panel ahead of the gauge stay green.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/recon-page` (branch `feat/00157-reconciliation-position-page`); every command runs with it as the working directory.
- No converge, image build, push or `grafana-query.py` read in a task: those are `## Rollout`'s. No venue call, and no `ZCRYPTO_LIVE_VENUE_TESTS`.
- Tests per commit: `T="$(infra/scripts/consumers.sh --direct <the commit's changed paths>) <the task's test files>"`, keep the `tests/test_*.py` names alone, leave out `tests/test_grafana_push_sh.py`, and run `uv run pytest $T -m "not slow" -n auto -q -p no:cacheprovider`. Read the result line before writing the commit message, in a separate call, and quote that line with the command in full.
- A task that edits a page under `infra/runbooks/` also runs `WALKERS`: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_guidance_refs_resolve.py tests/test_code_prose_citations.py -q -p no:cacheprovider`. `RATIO`, `tests/test_ops_daily.py`'s autonomy floor, read 376/535 at this plan's base, its margin 1.5 commands: a read a page adds is spelled in a shape the classifier admits, and the allowlist is not widened.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. A new Markdown file is one line per paragraph; an existing one keeps its shape.
- Commits: Conventional Commits, one subject per change, with `git add <every path the commit changes>`. Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`. Never amend, never `--no-verify`.
- Probes (this plan's tier is `full`, `infra/scripts/tier.py`): each arm a task lists runs as its own call on the committed tree through `infra/scripts/mutate-probe.sh --file <f> --control '1,$d' --mutation '<sed>' -- uv run pytest <its test file> -k '<its case>' -q -p no:cacheprovider`, its verdict recorded in an empty commit naming the script. The script refuses only a `sed` that changes nothing, so each arm's `sed` is written to reach the one site it names.

## File structure

- Modify: `cli/engine/venuestate.py`, `cli/engine/executor.py`, `cli/engine/command.py`, `infra/scripts/ops_daily.py`.
- Modify: `tests/test_engine_venuestate.py`, `tests/test_engine_executor.py`, `tests/test_engine_metrics.py`, `tests/test_infra_alert_rules.py`, `tests/test_cache_restart.py`, `tests/cache_restart_child.py`, `tests/slow-cases.txt`.
- Modify: `infra/grafana/alerts.yaml`, `infra/grafana/engine-dashboard.json`, `infra/runbooks/engine.md`, `infra/runbooks/engine-procedures.md`, `docs/research/14.phase6-decisions.md`.

## Review Focus

- Does a raise in the read reach anything the engine does (D3)?
- Is the read reached at a start whose book read fails, and does the gauge fall when no pass or boundary recurs (D2)?
- Do the existing executor tests' stub caches still pass without a logged exception, and does `tests/test_engine_stub_fidelity.py` classify what the reader touches?
- Does `RATIO` hold after the runbook edits?

---

### Task 1: The reader (D1)

**Files:** `cli/engine/venuestate.py`, `tests/test_engine_venuestate.py`.

- [ ] **Step 1: The failing test,** with `ClientOrderId` added to the file's `nautilus_trader.model` import and the two readers to its `cli.engine.venuestate` import. Over a stub cache whose `positions_open()` and `order(id)` answer from dicts:

```python
@pytest.mark.parametrize(
    ("orders", "tagged"),
    [
        ({"a": ["RECONCILIATION"]}, ["a"]),  # the opener tagged
        ({"a": None, "b": ["RECONCILIATION"]}, ["b"]),  # a later order tagged, the opener not
        ({"a": ["VENUE"]}, []),
        ({"a": None}, []),
        ({}, []),  # the Cache holds neither order
    ],
)
def test_a_position_counts_when_it_holds_a_tagged_order(orders, tagged):
    position = SimpleNamespace(client_order_ids=lambda: [ClientOrderId("a"), ClientOrderId("b")])
    cache = SimpleNamespace(
        positions_open=lambda: [position],
        order=lambda cid: SimpleNamespace(tags=orders[cid.value]) if cid.value in orders else None,
    )
    assert [cid.value for cid in reconciliation_tagged_orders(cache, position)] == tagged
    assert reconciliation_booked_positions(cache) == ([position] if tagged else [])
```

- [ ] **Step 2: Run it and read it fail** on the missing name.
- [ ] **Step 3: The reader**, in `cli/engine/venuestate.py`:

```python
RECONCILIATION_TAG = "RECONCILIATION"


def reconciliation_tagged_orders(cache, position) -> list:
    """The orders of `position` the library minted to book a difference it could not explain (spec 00157 D1): any order of the
    position, since a later mismatch tags an order on a position whose opener carries none."""
    return [cid for cid in position.client_order_ids() if RECONCILIATION_TAG in ((order := cache.order(cid)) and order.tags or [])]


def reconciliation_booked_positions(cache) -> list:
    """The open positions holding such an order."""
    return [position for position in cache.positions_open() if reconciliation_tagged_orders(cache, position)]
```

- [ ] **Step 4: Run the test, the gate, commit** `feat(engine): the reader of a position the library's reconciliation booked`.
- [ ] **Step 5: Probes,** `--file cli/engine/venuestate.py`, through `tests/test_engine_venuestate.py -k 'test_a_position_counts_when_it_holds_a_tagged_order'`. Each KILLED:
  - the tag's string changed: `s/RECONCILIATION_TAG = "RECONCILIATION"/RECONCILIATION_TAG = "RECONCILED"/`;
  - the opener alone read: `s/for cid in position\.client_order_ids() if/for cid in position.client_order_ids()[:1] if/`;
  - the `or []` removed: `s/ and order\.tags or \[\]/ and order.tags/`.

### Task 2: The rule, the panel and the runbook (D4, D5)

**Files:** `infra/grafana/alerts.yaml`, `infra/grafana/engine-dashboard.json`, `infra/scripts/ops_daily.py`, `infra/runbooks/engine.md`, `infra/runbooks/engine-procedures.md`, `tests/test_infra_alert_rules.py`.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*. Read `RATIO`.
- [ ] **Step 2: The failing test,** in `tests/test_infra_alert_rules.py` beside `test_the_engines_venue_read_failing_for_fifteen_minutes_pages_and_a_venue_maintenance_does_not`, read failing on the missing uid:

```python
def test_a_position_the_library_booked_pages_at_one_and_reads_nothing_at_zero():
    rule = _rule("zcrypto-engine-reconciliation-position")
    assert _evaluator(rule) == {"type": "gt", "params": [0.5]}
    assert rule["data"][0]["model"]["expr"] == 'zcrypto_exec_reconciliation_positions{host="zcrypto"}'
    assert rule["for"] != "0s", "a pending period keeps one failed evaluation from firing a critical page, and costs no detection"
    assert (rule["noDataState"], rule["execErrState"]) == ("OK", "Alerting")
    assert rule["labels"]["severity"] == "critical"
    assert (rule["notification_settings"]["receiver"], rule["ruleGroup"]) == ("metrics", "zcrypto-gate")
```

- [ ] **Step 3: The rule,** in `infra/grafana/alerts.yaml` after `zcrypto-engine-exec-venue-diverged`, copying its shape: uid `zcrypto-engine-reconciliation-position`, title `Engine · a position holds an order the library's reconciliation minted`, group `zcrypto-gate`, expression `zcrypto_exec_reconciliation_positions{host="zcrypto"}`, evaluator `{type: gt, params: [0.5]}`, `noDataState: OK` with the neighbour's comment, `execErrState: Alerting`, `severity: critical`, receiver `metrics`, `__dashboardUid__: "zcrypto-engine"`, its summary saying what it means in one line with no internal term and closing `Runbook: infra/runbooks/engine.md#zcrypto-engine-reconciliation-position`, and:

```yaml
    # 5m absorbs the one-minute datasource transients and no more: the count opens no faster than a
    # start and stands until the position goes, so the wait costs no detection.
    for: 5m
```

`infra/scripts/ops_daily.py`'s `_UID_HOST` gains `"zcrypto-engine-reconciliation-position": "zcrypto"`, which `tests/test_ops_daily.py` owes a host-pinned rule under `execErrState: Alerting`.
- [ ] **Step 4: The panel.** One stat panel on the Engine board, in the row holding `zcrypto_exec_venue_read_failed`'s panel, its id the next free one there and that id, a quoted string, in the rule's `__panelId__`: title `Positions the library's reconciliation booked`, the rule's expression as its target, no value mapping, `noValue` `NOT READ YET`, and `steps` green at null and red at `0.5`, the rule's own bar, which `test_a_panels_red_line_agrees_with_the_rule_it_charts` holds. Its description says what the count means, that 0 is the healthy reading, that the series is absent until the engine's first read after a start, and closes with the runbook's anchor.
- [ ] **Step 5: `engine.md`.** After `zcrypto-engine-exec-venue-diverged`'s section, its `______` rule between them, verbatim:

```markdown
<a name="zcrypto-engine-reconciliation-position"></a>

## zcrypto-engine-reconciliation-position — ALERT

### What you are seeing

A critical Grafana alert (`Engine · a position holds an order the library's reconciliation minted`): `zcrypto_exec_reconciliation_positions{host="zcrypto"}` has read above 0 for five minutes, and the Engine board's `Positions the library's reconciliation booked` tile reads the count. The engine logged one WARNING per position per process: `position <id> under <strategy>, <quantity>, holds an order nautilus's reconciliation minted, [<order>] -- see infra/runbooks/engine.md#zcrypto-engine-reconciliation-position`.

### What it means

Kraken reported a position the library could not explain, and the library booked the difference as a position under `EXTERNAL` holding an order tagged `RECONCILIATION`. The engine's net stays right and nothing it does reads this count, so it trades on. The danger is a later build: upstream commit dd8afce410 sends a reconciliation fill older than such a position's opening to the order alone, so on a nautilus build carrying it a second start can hide a close behind this position with no log line. `dev20261103` predates that commit, and `_NEWEST_PIN_WITHOUT_THE_TWO_START_CASE` in `tests/test_nautilus_adapter.py` is the bump's limit there, which is why the clear is owed before a restart past `dev20261103`.

The engine reads the count before each book read and once a minute while no plan runs. The WARNING's time dates its first read in this process: at the start's first pass it says a start booked it, this one or an earlier one, and later says it opened while the engine ran, which no measured run has shown, so take that one to the owner.

### What to do

1. **Read the facts.** The WARNING, on the `Logs` panel of the `zcrypto-logs` board with the container filter at `engine`; on the workstation, `kraken positions -o json` and the balance export, `kraken extended-balance -o json`.
2. **Explain the gap as one of the shapes a measured start booked:** a leveraged row the Cache did not hold at a cold start; a leveraged row differing from the Cache's net; a fill made while the engine was down and absent from the trade history; a store lost with the fill past the 720-minute lookback; the engine's dust lot beside its own margin fill; a later mismatch on a hand-opened position, its opener untagged. An unexplained one goes to the owner.
3. **Silence the rule once it is explained,** in the node's UI, on `__alert_rule_uid__=zcrypto-engine-reconciliation-position`, with a dated end no later than the next restart taken by hand and a comment naming the position id and the count it explains. The series is one unlabelled count, so the silence hides a later position too: [the restart read](engine-procedures.md#rung-3-after-a-restart) and [the daily read](engine-procedures.md#rung-3-the-daily-read) compare the gauge with the count it explained.
4. **A flat book: clear the store before a restart past `dev20261103`.** Flat reads as `kraken open-orders -o json` listing nothing, `kraken positions -o json` printing `{}` and `kraken extended-balance -o json` showing no lot: the positions read prints `{}` with a spot lot held too. The clear is [the prefix-wide form](engine-procedures.md#engine-clear-stored-account-prefix-wide); [the single-key form](engine-procedures.md#engine-clear-stored-account) deletes the account key and leaves the position, so this rule keeps firing after it.
5. **A lot or a margin position held: no clear.** On a build without dd8afce410 the position may stand, silenced as in step 3, with no bump past `dev20261103` until it is cleared at a flat book. Flattening to clear is the owner's decision.
6. **It resolves** when the position closes, within a minute of the close while no plan runs, or when the store is cleared.

### Retire when

`zcrypto-engine-reconciliation-position` is absent from `infra/grafana/alerts.yaml`: the rule can no longer fire and this section describes nothing.
```

And in `#zcrypto-engine-error-logs` step 2, directly above its `Anything naming the executor` bullet, verbatim:

```markdown
   - **`the reconciliation position read raised -- continuing`**: telemetry, the read alone, with no order path touched. No disarm is owed for this line alone. `zcrypto_exec_reconciliation_positions` says nothing while the line stands, so read Kraken's positions by hand, [`zcrypto-engine-reconciliation-position`](#zcrypto-engine-reconciliation-position) step 1, and take the traceback to the owner (no count command: the line is `_publish_reconciliation_positions`'s in `cli/engine/executor.py`, and nothing the engine does reads that read).
```

- [ ] **Step 6: `engine-procedures.md`,** four edits, verbatim:
  - the prefix-wide form's step 1 bullet, whole: `` Kraken flat: on the workstation, `kraken open-orders -o json` lists nothing, `kraken positions -o json` prints `{}`, and the balance export, `kraken extended-balance -o json`, shows no lot held: the positions read prints `{}` with a spot lot held too. ``
  - the rung-3 restart section's item 3, *Read the boot*, its paragraph under the fence closing with: `` `zcrypto_exec_reconciliation_positions` on the Engine board reads 0 or the count a standing silence explained; a higher count is a new position, [`engine.md#zcrypto-engine-reconciliation-position`](engine.md#zcrypto-engine-reconciliation-position) step 1. ``
  - the daily read's item 4, *The Cache against Kraken*, closing with: `` `zcrypto_exec_reconciliation_positions` reads as [the restart read](#rung-3-after-a-restart) item 3 has it. ``
  - the go/no-go's item 2, its close becoming: `` each unmatched ledger row explained at the weekly reads, and each position `zcrypto_exec_reconciliation_positions` counted explained in `docs/reference/rung3/days.md`. ``
- [ ] **Step 7: `WALKERS`, `tests/test_dashboards_cover_metrics.py`, `tests/test_drill_log.py`, `RATIO` again, the gate, commit** `feat(grafana): a position the library's reconciliation booked pages`.
- [ ] **Step 8: Probes,** `--file infra/grafana/alerts.yaml`, through `tests/test_infra_alert_rules.py -k 'test_a_position_the_library_booked_pages_at_one_and_reads_nothing_at_zero'`. Each KILLED:
  - the threshold moved, so the gauge at 1 does not fire: `/uid: zcrypto-engine-reconciliation-position/,/notification_settings/s/params: \[0\.5\]/params: [1.5]/`;
  - the pending period gone: `/uid: zcrypto-engine-reconciliation-position/,/notification_settings/s/for: 5m/for: 0s/`.

### Task 3: The gauge and the executor's read (D2, D3, D4)

**Files:** `cli/engine/command.py`, `cli/engine/executor.py`, `tests/test_engine_executor.py`, `tests/test_engine_metrics.py`, `tests/cache_restart_child.py`.

- [ ] **Step 1: The failing tests.** `tests/test_engine_executor.py`'s `RecordingMetrics` gains `set_reconciliation_positions`, recording the counts, and `StubCache` gains `hold_tagged_position(symbol, signed_qty)`, its name in `_STUB_CACHE_PLUMBING`: an `EXTERNAL` position carrying `id`, `strategy_id`, `signed_qty`, `realized_pnl` and `client_order_ids`, its two orders served by `order`, an untagged `O-PLAIN` and a tagged `O-TAGGED`. With the file's `_executor`:
  - `test_a_position_the_library_booked_sets_the_gauge_and_logs_one_warning_per_process`: two reads over that position give the gauge 1 twice and one WARNING naming its id, strategy, quantity and `O-TAGGED`, and not `O-PLAIN`.
  - `test_the_gauge_falls_to_zero_when_the_position_goes`, through `on_timer` and no pass: the first tick's startup pass reads 1, the position is removed, and a tick `_GATE_REFRESH` later leaves the setter's calls `[1, 0]`.
  - `test_a_raise_in_the_reconciliation_read_changes_nothing_the_engine_does`: a `StubCache` subclass, defined in the test, whose `positions_open` raises `RuntimeError` when `instrument_id is None`, the call the reader alone makes, since `_cache_net` reads the same accessor by instrument; with `_VenueHoldings({"BTC/EUR": 0.0})`, `_settle_positions_from_venue` returns True, the one ERROR record reads `the reconciliation position read raised -- continuing`, and `set_position` ran for `BTC/EUR`.
  - `test_the_read_runs_before_a_book_read_that_fails`: `venue_holdings` raising makes the pass return False with the gauge set to 1.
  - `test_the_boundary_read_reads_it_before_its_book`: over `_boundary_executor`, its book read raising and no startup pass run, `on_boundary` then one `_draft_cycle_plan` leaves the gauge set to 1.

  And in `tests/test_engine_metrics.py`, beside `test_the_freeze_and_the_undrafted_boundary_are_eager_at_zero_and_the_equity_and_drawdown_absent_until_set`, importing `StubCache`, `StubClient`, `_executor` and `_executor_errors` from `test_engine_executor` as that file's other cases do:
  - `test_the_reconciliation_count_is_absent_until_the_first_read_and_the_read_moves_the_real_gauge`: a real `command._ExecutionMetrics(CollectorRegistry())` exposes no `zcrypto_exec_reconciliation_positions`; through `set_executor_hooks`, one read over a tagged position gives `registry.get_sample_value("zcrypto_exec_reconciliation_positions") == 1`; a second read with the position gone gives 0; no ERROR record; the hooks cleared in a `finally`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: The gauge,** in `_ExecutionMetrics`, the object the executor already holds as `_metrics`. In `__init__` beside `self.drawdown_bps`:

```python
# Registered on first use, as `tracking_state` is: the series at 0 then says a read ran.
self.reconciliation_positions: Gauge | None = None
```

and beside `set_position`:

```python
def set_reconciliation_positions(self, count: int) -> None:
    if self.reconciliation_positions is None:
        self.reconciliation_positions = Gauge(
            "zcrypto_exec_reconciliation_positions",
            "Open positions holding an order nautilus's reconciliation minted.",
            registry=self._registry,
        )
    self.reconciliation_positions.set(count)
```

- [ ] **Step 4: The read,** in `ProbeExecutor`, with `reconciliation_booked_positions` and `reconciliation_tagged_orders` added to the module's `cli.engine.venuestate` import and `self._reconciliation_positions_logged: set[str] = set()`, keyed by `str(position.id)`, initialised in `__init__` beside `self._rows_the_pass_repaired`:

```python
def _publish_reconciliation_positions(self) -> None:
    """A raise is logged and dropped; the callers ignore it (spec 00157 D3)."""
    try:
        positions = reconciliation_booked_positions(self._cache)
        for position in positions:
            if str(position.id) not in self._reconciliation_positions_logged:
                self._reconciliation_positions_logged.add(str(position.id))
                logger.warning(
                    "position %s under %s, %s, holds an order nautilus's reconciliation minted, %s -- see infra/runbooks/engine.md#zcrypto-engine-reconciliation-position",
                    position.id,
                    position.strategy_id,
                    position.signed_qty,
                    [str(cid) for cid in reconciliation_tagged_orders(self._cache, position)],
                )
        if _metrics is not None:
            _metrics.set_reconciliation_positions(len(positions))
    except Exception:
        logger.exception("the reconciliation position read raised -- continuing")
```

Three call sites: the first statement of `_settle_positions_from_venue`; in `_draft_cycle_plan` immediately before its `book = (self._venue_holdings or read_venue_book)()`; and the first statement inside the `if` of `_refresh_gate`, its docstring gaining that read.

- [ ] **Step 5: Run the tests, the direct readers with `tests/test_engine_stub_fidelity.py`.** These doubles widen, so that the one existing test still logging the exception is `test_a_raising_fill_metrics_hook_never_costs_the_fill_its_row`, whose metrics double stays without the setter, its hooks raising by design:
  - `StubCache.positions_open` answers a call with neither `instrument_id` nor `strategy_id` with every own and external position it holds, its refusal of a mistyped id kept;
  - `_held`, `StubCache.set_position` and `set_external_position` build their namespaces with `client_order_ids=list`, a name the real `Position` carries;
  - `tests/cache_restart_child.py`'s `_Recorder` gains `set_reconciliation_positions`, appending to a list `_write()` puts in `RECORD["metrics"]` as `reconciliation_positions`.

  `_PositionReadFails` and `StubCache(raises=True)` inherit the widening and need nothing of their own. No module-level double is new, so `tests/test_engine_stub_fidelity.py`'s table takes no row.
- [ ] **Step 6: The gate, commit** `feat(engine): the executor publishes a position the library's reconciliation booked`.
- [ ] **Step 7: Probes.** Each KILLED. `--file cli/engine/executor.py`, through `tests/test_engine_executor.py -k '<the case>'`:
  - the startup call removed, `test_the_read_runs_before_a_book_read_that_fails`: `/def _settle_positions_from_venue/,/book = /{/self\._publish_reconciliation_positions()/d}`;
  - the boundary call removed, `test_the_boundary_read_reads_it_before_its_book`: `/def _draft_cycle_plan/,/book = /{/self\._publish_reconciliation_positions()/d}`;
  - the idle call removed, `test_the_gauge_falls_to_zero_when_the_position_goes`: `/def _refresh_gate/,/gate refresh raised/{/self\._publish_reconciliation_positions()/d}`;
  - the `except` narrowed, `test_a_raise_in_the_reconciliation_read_changes_nothing_the_engine_does`: `/def _publish_reconciliation_positions/,/raised -- continuing/s/except Exception:/except ValueError:/`;
  - the set's `add` removed, `test_a_position_the_library_booked_sets_the_gauge_and_logs_one_warning_per_process`: `/self\._reconciliation_positions_logged\.add(str(position\.id))/d`;
  - every order logged, the same case: `s/reconciliation_tagged_orders(self\._cache, position)\]/position.client_order_ids()]/`.

  `--file cli/engine/command.py`, through `tests/test_engine_metrics.py -k 'test_the_reconciliation_count_is_absent_until_the_first_read_and_the_read_moves_the_real_gauge'`:
  - the setter emptied: `s/self\.reconciliation_positions\.set(count)/pass/`;
  - the gauge made eager: `s/self\.reconciliation_positions: Gauge | None = None/self.reconciliation_positions = Gauge("zcrypto_exec_reconciliation_positions", "h", registry=registry)/`.

### Task 4: The case on the real wheel (D6)

**Files:** `tests/test_cache_restart.py`, `tests/cache_restart_child.py`, `tests/slow-cases.txt`.

- [ ] **Step 1: The child's dump** gains, for each position, `order_tags`: each id in `client_order_ids()` mapped to `cache.order(cid)`'s tags, `None` for an order the Cache does not return, read as the archived scratch child reads them (`/home/zhaow/Projects/zcrypto-kraken/.local/reads-archive/feat/00157-reconciliation-position-page/measure/child.py`). The gauge's counts are already in `RECORD["metrics"]`, from Task 3.
- [ ] **Step 2: `test_a_position_the_library_booked_is_counted_and_a_hand_orders_is_not`,** two runs, each its own `_Valkey` and `_Node`, on the shapes of `test_case5_cold_leveraged_long` and `test_case4a_hand_fill_live_spot_then_restart` and the helpers `_margin_row` and `_hand_frames` in `/home/zhaow/Projects/zcrypto-kraken/.local/reads-archive/feat/00157-reconciliation-position-page/measure/test_measure.py`. A leveraged row the Cache does not hold, at a cold start: the counts read `[1]`, the open position is under `EXTERNAL`, `RECONCILIATION` is among its `order_tags`, and the WARNING names it. A hand order's fill seen live, then a restart: the restart's counts are non-empty and all 0. A helper `_reads_nothing(record)` holds that last reading, and `test_a_resting_order_and_a_margin_position_are_restored_across_a_restart` and `test_a_restored_spot_lot_comes_back_at_the_lot_with_no_external_short_and_the_account_keeps_its_coin` each assert it over their restart's record, so the restored margin position and spot lot need no run of their own. The assertion messages name `_BUMP`, as the file's others do, since a wheel that renames the tag goes red here. The new case's id goes in `tests/slow-cases.txt`, in sorted place.
- [ ] **Step 3: Run the three cases, then `tests/test_slow_cases.py`, the gate, commit** `test(engine): a position the library booked is counted on the real wheel`. The run names the slow cases itself, and takes about a minute and a half at `-n 3`: `uv run pytest tests/test_cache_restart.py -k 'test_a_position_the_library_booked_is_counted_and_a_hand_orders_is_not or test_a_resting_order_and_a_margin_position_are_restored_across_a_restart or test_a_restored_spot_lot_comes_back_at_the_lot' -n 3 -q -p no:cacheprovider`. The message records `probe skipped: slow case`: the tag's string is Task 1's arm.

### Task 5: The decisions log

**Files:** `docs/research/14.phase6-decisions.md`.

- [ ] **Step 1: Load `iteration-closeout`.** Append, verbatim:

```
[00157] What should a detector do when a position holds an order the library's reconciliation minted? (Decision: 1)
  1. **Page only** — the net is right in the trap, by reading, so stopping trading would turn a bookkeeping error into a real outage.
  2. **Refuse to trade the leg until someone clears it** — stricter; a false reading stops a leg.
  Human: "i'm sure we will move past dev20261103. is there more prominent way to ensure we won't end up with that trap?", then "yes, build it, and page-only as recommended".
```

- [ ] **Step 2: `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py`, the gate, commit** `docs(research): the owner's word that the reconciliation position pages and stops nothing`.

## Rollout — the owner's, from merged `develop` (D7)

The push, the image and the host read are the owner's, none of them inside a task; the reads by value are taken from the workstation in the same sitting. The rule goes first and the image second.

**R1. The rule.** The push through the `zcrypto-grafana-push` skill, from merged `develop`, its closeout naming it. Its Step 1 reads `(no series)` for this rule's selector until R2, and its Step 3's first-sample read waits for R3: the skill's hold is for a series a healthy host already publishes, and the rule's bare selector with `noDataState: OK` stays quiet with none. Read the rule `Normal` in the node's UI.

**R2. The image.** On the bulk rollout the owner's word of 2026-11-06 defers, if this has merged before it, else the next engine image, through `zcrypto-rollout-image`. The engine's pin stays `dev20261101` until half a day before rung 3, then `dev20261103`.

**R3. The proof, by value, after the engine's first start on that image.** The series reads 0, which a read alone can have set, and the tile reads 0; `(no series)` is a read that has not run, and a value above 0 is `engine.md#zcrypto-engine-reconciliation-position`. The second line is the owner's container read for the one-process premise, which prints `running` and the restart count:

```bash
uv run python infra/scripts/grafana-query.py 'zcrypto_exec_reconciliation_positions{host="zcrypto"}'   # on the workstation
sudo docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-engine   # on the host
```
