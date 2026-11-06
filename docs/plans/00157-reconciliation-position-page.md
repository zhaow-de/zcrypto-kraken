# The engine pages a position the library's reconciliation booked Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A position holding an order nautilus's reconciliation minted pages the main channel, at the first start that books it, and changes nothing the engine does.

**Architecture:** `venuestate.reconciliation_booked_positions(cache)` is the one reader (D1). `ProbeExecutor._publish_reconciliation_positions` reads it before each book read, logs one WARNING per position per process and sets `zcrypto_exec_reconciliation_positions` (D2, D3, D4). `zcrypto-engine-reconciliation-position` pages on that gauge, and `engine.md` says what to do (D4, D5). A case on the real wheel holds the tag (D6).

**Tech Stack:** Python 3.14, pytest, `nautilus-trader` 2.0.0rc9.dev20261101, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00157-reconciliation-position-page-design.md`

## Global Constraints

- The spec is the authority; where it is silent this plan rules, in *Rulings* below.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/recon-page` (branch `feat/00157-reconciliation-position-page`); every command runs with it as the working directory.
- No converge, image build, push or `grafana-query.py` read in a task. No venue call, and no `ZCRYPTO_LIVE_VENUE_TESTS`.
- Tests per commit: `T="$(infra/scripts/consumers.sh --direct <the commit's changed paths>) <the task's test files>"`, keep the `tests/test_*.py` names alone, leave out `tests/test_grafana_push_sh.py`, and run `uv run pytest $T -m "not slow" -n auto -q -p no:cacheprovider`. Read the result line before writing the commit message, in a separate call, and quote that line with the command in full.
- A task that edits a page under `infra/runbooks/` also runs `WALKERS`: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_guidance_refs_resolve.py tests/test_code_prose_citations.py -q -p no:cacheprovider`. `RATIO`, `tests/test_ops_daily.py`'s autonomy floor, read 376/535 at this plan's base, its margin 1.5 commands: a read a page adds is spelled in a shape the classifier admits, and the allowlist is not widened.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. A new Markdown file is one line per paragraph; an existing one keeps its shape.
- Commits: Conventional Commits, one subject per change, with `git add <every path the commit changes>`. Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`. Never amend, never `--no-verify`.
- Probes (this plan's tier is `full`, `infra/scripts/tier.py`): each arm a task lists runs as its own call on the committed tree through `infra/scripts/mutate-probe.sh --file <f> --control '1,$d' --mutation '<sed>' -- <the task's test command>`, its verdict recorded in an empty commit naming the script.

## Rulings where the spec is silent

- **The gauge's home.** `_ExecutionMetrics`, beside `self.position` at `cli/engine/command.py:657`, with a setter beside `set_position`, because the executor already holds that object as `_metrics`.
- **The set of positions logged.** `self._reconciliation_positions_logged: set[str]`, initialised with the executor's other per-process fields, keyed by `str(position.id)`.
- **The rule's panel.** One stat panel on the Engine board, in the row holding `zcrypto_exec_venue_read_failed`'s panel, its id the next free one there, its id in `__panelId__`.

## File structure

- Modify: `cli/engine/venuestate.py`, `cli/engine/executor.py`, `cli/engine/command.py`.
- Modify: `tests/test_engine_venuestate.py`, `tests/test_engine_executor.py`, `tests/test_cache_restart.py`, `tests/cache_restart_child.py`.
- Modify: `infra/grafana/alerts.yaml`, `infra/grafana/engine-dashboard.json`, `infra/runbooks/engine.md`, `infra/runbooks/engine-procedures.md`, `docs/research/14.phase6-decisions.md`.

## Review Focus

- Does a raise in the read reach anything the engine does (D3)?
- Is the read reached at a start whose book read fails (D2)?
- Do the existing executor tests' stub caches still pass without a logged exception, and does `tests/test_engine_stub_fidelity.py` classify what the reader touches?
- Does `RATIO` hold after the runbook edits?

---

### Task 1: The reader (D1)

**Files:** `cli/engine/venuestate.py`, `tests/test_engine_venuestate.py`.

- [ ] **Step 1: The failing test.** Over a stub cache whose `positions_open()` and `order(id)` answer from dicts:

```python
@pytest.mark.parametrize(
    ("orders", "counted"),
    [
        ({"a": ["RECONCILIATION"]}, True),  # the opener tagged
        ({"a": None, "b": ["RECONCILIATION"]}, True),  # a later order tagged, the opener not
        ({"a": ["VENUE"]}, False),
        ({"a": None}, False),
        ({}, False),  # the Cache holds neither order
    ],
)
def test_a_position_counts_when_it_holds_a_tagged_order(orders, counted):
    position = SimpleNamespace(client_order_ids=lambda: [ClientOrderId("a"), ClientOrderId("b")])
    cache = SimpleNamespace(
        positions_open=lambda: [position],
        order=lambda cid: SimpleNamespace(tags=orders[cid.value]) if cid.value in orders else None,
    )
    assert reconciliation_booked_positions(cache) == ([position] if counted else [])
```

- [ ] **Step 2: Run it and read it fail** on the missing name.
- [ ] **Step 3: The reader**, in `cli/engine/venuestate.py`:

```python
RECONCILIATION_TAG = "RECONCILIATION"


def reconciliation_booked_positions(cache) -> list:
    """Open positions holding an order the library minted to book a difference it could not explain (spec 00157 D1). Any order
    of the position, since a later mismatch tags an order on a position whose opener carries none."""
    return [
        position
        for position in cache.positions_open()
        if any(RECONCILIATION_TAG in ((order := cache.order(cid)) and order.tags or []) for cid in position.client_order_ids())
    ]
```

- [ ] **Step 4: Run the test, the gate, commit** `feat(engine): the reader of a position the library's reconciliation booked`.
- [ ] **Step 5: Probes:** the tag's string changed; `any` to `all`; the `or []` removed. Each KILLED.

### Task 2: The gauge and the executor's read (D2, D3, D4)

**Files:** `cli/engine/command.py`, `cli/engine/executor.py`, `tests/test_engine_executor.py`.

- [ ] **Step 1: The failing tests,** with the file's `_executor` helper and a metrics double recording the setter:
  - `test_a_position_the_library_booked_sets_the_gauge_and_logs_one_warning_per_process`: two passes over one tagged position give the gauge 1 twice and one WARNING naming its id, strategy, quantity and tagged order.
  - `test_the_gauge_falls_to_zero_when_the_position_goes`.
  - `test_a_raise_in_the_reconciliation_read_changes_nothing_the_engine_does`: a Cache whose `positions_open` raises logs one exception and the pass still settles from the book.
  - `test_the_read_runs_before_a_book_read_that_fails`: `_venue_holdings` raising leaves the gauge set.
  - `test_the_boundary_read_reads_it_before_its_book`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: The gauge,** in `_ExecutionMetrics` beside `self.position`:

```python
self.reconciliation_positions = Gauge(
    "zcrypto_exec_reconciliation_positions",
    "Open positions holding an order nautilus's reconciliation minted, read before each book read.",
    registry=registry,
)
```

with `def set_reconciliation_positions(self, count: int) -> None: self.reconciliation_positions.set(count)` beside `set_position`.

- [ ] **Step 4: The read,** in `ProbeExecutor`:

```python
def _publish_reconciliation_positions(self) -> None:
    """Page-only (spec 00157 D3): nothing the engine does reads this, and a raise is logged and dropped."""
    try:
        positions = reconciliation_booked_positions(self._cache)
        for position in positions:
            if str(position.id) not in self._reconciliation_positions_logged:
                self._reconciliation_positions_logged.add(str(position.id))
                logger.warning(
                    "position %s under %s, %s, holds an order nautilus's reconciliation minted, one of %s -- see infra/runbooks/engine.md#zcrypto-engine-reconciliation-position",
                    position.id,
                    position.strategy_id,
                    position.signed_qty,
                    [str(cid) for cid in position.client_order_ids()],
                )
        if _metrics is not None:
            _metrics.set_reconciliation_positions(len(positions))
    except Exception:
        logger.exception("the reconciliation position read raised -- continuing")
```

Call it as the first statement of `_settle_positions_from_venue`, and in the boundary's draft immediately before its `book = (self._venue_holdings or read_venue_book)()`.

- [ ] **Step 5: Run the tests, the direct readers with `tests/test_engine_stub_fidelity.py`.** A stub cache in an existing test that lacks `positions_open()` with no arguments or `order` is widened to answer it, classified as that file asks, so no existing test logs the exception.
- [ ] **Step 6: The gate, commit** `feat(engine): the executor publishes a position the library's reconciliation booked`.
- [ ] **Step 7: Probes:** the startup call removed; the boundary call removed; the `except` narrowed to `ValueError`; the set's `add` removed. Each KILLED.

### Task 3: The case on the real wheel (D6)

**Files:** `tests/test_cache_restart.py`, `tests/cache_restart_child.py`.

- [ ] **Step 1: The child's dump** gains, for each open position, the tags of each order in `client_order_ids()`, as the archived scratch child does (`.local/reads-archive/feat/00157-reconciliation-position-page/measure/child.py`), and the executor's published gauge value.
- [ ] **Step 2: `test_a_position_the_library_booked_is_counted_and_the_engines_own_are_not`:** a leveraged row the Cache does not hold, at a cold start: the gauge reads 1, the position is under `EXTERNAL`, and the WARNING names it. The same harness's restored margin position and spot lot, read in their own runs, read 0. Reuse the shapes of `test_case5_cold_leveraged_long`, `test_case1_margin_restored` and `test_case2_spot_lot` in the archived `measure/test_measure.py`. Its assertion messages name `_BUMP`, as the file's others do, since a wheel that renames the tag goes red here.
- [ ] **Step 3: Run the file's cases by `-k`, the gate, commit** `test(engine): a position the library booked is counted on the real wheel`.
- [ ] **Step 4: Probe:** `RECONCILIATION_TAG`'s string changed in `cli/engine/venuestate.py`, through this case. KILLED.

### Task 4: The rule, the panel and the runbook (D4, D5)

**Files:** `infra/grafana/alerts.yaml`, `infra/grafana/engine-dashboard.json`, `infra/runbooks/engine.md`, `infra/runbooks/engine-procedures.md`.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*. Read `RATIO`.
- [ ] **Step 2: The rule and panel,** by D4's values, copying `zcrypto-engine-exec-venue-diverged`'s shape. `for: 0s`, `severity: critical`, its summary saying what it means in one line with no internal term, its `__panelId__` the new panel's.
- [ ] **Step 3: `engine.md#zcrypto-engine-reconciliation-position`,** with its anchor and the shape of its neighbours: *What you are seeing*, *What it means*, *What to do*, *Retire when*, per D5. The bump skill's limit and dd8afce410 are named as the reason the clear is owed before a restart past `dev20261103`.
- [ ] **Step 4: `engine-procedures.md`:** the rung-3 restart read and the day's *Cache against Kraken* item each gain the gauge, in one clause.
- [ ] **Step 5: `WALKERS`, `tests/test_dashboards_cover_metrics.py`, `tests/test_drill_log.py`, `RATIO` again, the gate, commit** `feat(grafana): a position the library's reconciliation booked pages`.
- [ ] **Step 6: Probe:** the rule's threshold moved so the gauge at 1 does not fire, through `tests/test_infra_alert_rules.py`'s case for it. KILLED.

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
