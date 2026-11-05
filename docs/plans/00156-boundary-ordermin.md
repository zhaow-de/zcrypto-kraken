# The engine holds a quantity against Kraken's current ordermin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every quantity the engine holds against `ordermin` is held against the higher of the Cache's floor and the floor in the venue listing its book read just fetched, so a floor Kraken raised stops the order before submission, and the venue record the helpers read carries the floor of the executor's newest book at its snapshot, up to one read behind.

**Architecture:** `read_venue_book` keeps the listing's floors on `VenueBook.ordermin` (D1, D4). `venuestate.held_ordermin` is the one rule and `venue_state_from_cache(..., listed=...)` applies it, so every existing reader of `InstrumentConstraints.ordermin` follows (D2, D3). The executor hands the newest book's floors to its venue-truth reads, the node hands them to the boundary's snapshot, and `_is_flat_dust` takes the same rule (D3). Two cases hold the two premises, a live opt-in one the nautilus bump runs and a restart over a real store (D5), and the rung-3 entry gate reads the pin row's revision and the record's floors (D6).

**Tech Stack:** Python 3.14, pytest, `nautilus-trader` 2.0.0rc9.dev20261101, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00156-boundary-ordermin-design.md`

## Global Constraints

- The spec is the authority; where it is silent this plan rules, in *Rulings* below.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/ordermin` (branch `feat/00156-boundary-ordermin`); every command runs with it as the working directory, and git takes `-C` that path. The main checkout is live.
- No converge, image build, push or `grafana-query.py` read in a task. The one network call is Task 4's opt-in run, public endpoints only, no credentials.
- Tests per commit: `T="$(infra/scripts/consumers.sh --direct <the commit's changed paths>) <the task's test files>"`, then `[ -n "$T" ] && uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, the two in one call; `mkdir -p .tmp/implementer .local/boundary-ordermin` first, its own call. Never the full suite. `tests/test_engine_executor.py` is large: a step's own run names `-k` cases, and the commit's run takes the whole list above.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. A runbook page carries no `spec <NNNNN>`, `D<N>`, `T<NNNN>`, `iter-<N>` or `Phase <N>` token (`tests/test_internal_terms_not_operator_visible.py`).
- Commits: Conventional Commits, one subject per change, after a `git -C <the worktree> add <every path the commit changes>` of its own, through `git -C <the worktree> commit -F - <<'EOF'`; the message says what changed and pastes the result line of the test command it names, run over the commit's own tree; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the implementer's own model in place of the placeholder, and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`.
- Probes (this plan's tier is `full`, `infra/scripts/tier.py`): each arm a task lists runs as its own call on the committed tree, `infra/scripts/mutate-probe.sh --file <file> --control '<control>' --mutation '<mutation>' -- uv run pytest <test file> -k '<selection>' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`, the control `1,$d` unless the arm names another. Before each arm `grep -c '<address or pattern>' <file>` prints `1`. `: > .local/boundary-ordermin/probes-task-<N>.txt` before a task's arms; after each arm its id and the script's last line are appended, its own call. A task's verdicts ride an empty commit, `git commit --allow-empty -F <message file>`, subject `test(engine): <task> proven by infra/scripts/mutate-probe.sh`, its body the probes file whole and the trailers. A case that skips is not probed, and neither is a `slow` one: Task 4's commit records `probe skipped: the case skips without ZCRYPTO_LIVE_VENUE_TESTS` for its live case and `probe skipped: slow case` for its restart case.
- A helper this plan names in a test (`_executor`, `_boundary_executor`, `_VenueHoldings`, `_drop_plan`, `_plan_dict`, `_intent`, `_quote`, `_intent_entry`, `_legs`, `_rung2_record`, `_only`, `_all_instruments`, `_fake_instrument`, `_executor_errors`, `StubClient`, `StubCache`) exists in `tests/test_engine_executor.py` at 9844ecf4a; where a fence's call does not fit its real signature, the case's intent and assertions bind, not the spelling, and the report says what changed.

## Rulings where the spec is silent

- **The rule lives in `venuestate.py`, the helper is public.** `held_ordermin` is imported by the executor for `_is_flat_dust`, since `venuestate.py` is already the module that turns a Cache figure into a constraint. Cost if wrong: one import to move.
- **`listed_ordermin()` is a public method on `ProbeExecutor`.** The node reads it through `self._executor`, and a stub executor in `tests/test_engine_node.py` that lacks it is given it in the test, never a `getattr` in the node. A stub lacking it would otherwise raise into `_snapshot_venue_state`'s catch and degrade the snapshot to `None`, which a test reading the snapshot would fail on, so it cannot pass silently.
- **`_listing_floors` runs last in `_read`,** after the positions and account reads, so a positions answer of `None` still raises first, and `client.calls` in `test_read_venue_holdings_refuses_a_positions_answer_of_none_and_the_settle_publishes_nothing` keeps its list. A stub listing row that reaches it without `id` or `min_quantity` takes them in the test, never a `getattr` in the reader.
- **A zero or negative listing floor is no floor** (D4 says "no positive"): `runtime_concordance` already treats a non-positive floor as a failure, `held_ordermin` leaves the Cache's floor standing over one either way, and leaving it out is what gives the leg its WARNING.
- **The WARNING's text names no spec or topic**, and reads as an operator would act on it: the leg stays on the floor the engine loaded at its start.
- **Eight docstrings the change makes false or short are corrected, as state and not history:** `cli/engine/venuestate.py`'s module docstring, `InstrumentConstraints`, `VenueState` and `runtime_concordance` (Task 2); `_VenueHoldings` in `tests/test_engine_executor.py` (Task 1); `_venue_state` in `tests/cache_restart_child.py` (Task 4); `_boundary_executor` in `tests/test_engine_executor.py` `size_probe_order` in `cli/engine/executor.py`, whose "on the Cache-fresh constraints", wrapped over two lines, reads "on the constraints `venue_state_from_cache` froze" (Task 3).
- **The runbook's `engine-rung-3` section takes the operator's text, never `engine-rung-2-box`, whose box is over:** a sub-item of the daily read saying when a moved floor takes effect, since an operator reading a carried leg's reason against a sweep's figure would otherwise read a lowered floor's dust as a fault and restart for it, which latches the hold; `The loop`'s floors clause; and the entry gate's two reads of D6, added to its reference-data sweep item so the gate stays six reads, plan 00092's R0 (5), the gate's other carrier, pointing at that item rather than restating it. `docs/reference/kraken-snapshot-register.md`'s sweep #4 row is a dated record and is left as it is.

## File structure

- Modify `cli/engine/venuestate.py`: `held_ordermin`, the `listed` argument, the docstrings.
- Modify `cli/engine/executor.py`: `VenueBook.ordermin`, `_listing_floors`, `read_venue_book`, `listed_ordermin`, the three `venue_state_from_cache` calls, `_is_flat_dust`.
- Modify `cli/engine/node.py`: `_snapshot_venue_state`.
- Modify tests `tests/test_engine_venuestate.py`, `tests/test_engine_executor.py`, `tests/test_engine_node.py`, `tests/test_cache_restart.py`, its child `tests/cache_restart_child.py`, and `tests/slow-cases.txt`.
- Modify `.claude/skills/zcrypto-bump-nautilus/SKILL.md`, `infra/runbooks/engine-procedures.md`, `docs/plans/00092-rung-3-accumulation.md`, `docs/research/14.phase6-decisions.md`; move `docs/open-topics/T0224-the-engine-and-the-helper-read-krakens-live-ordermin.md` to `docs/open-topics/archive/`; re-render `docs/open-topics/README.md`.

## Review Focus

1. The 2026-10-30 order, Cache floor 0.001 and listing floor 0.002, is stopped on both paths, the boundary's draft and an operator's plan, and the control without the listing still places it, so the case proves the listing did it. Pinned by Task 3's `test_the_boundary_carries_the_ten_thirty_sell_under_the_listings_raised_floor` and `test_a_plan_holding_the_ten_thirty_sell_is_refused_under_the_listings_raised_floor`.
2. A lowered floor never reaches the library's risk engine as a quantity it denies. Pinned by Task 2's `test_a_listed_floor_under_the_caches_leaves_the_caches_held` and Task 3's `test_the_boundary_holds_a_lowered_floor_at_the_caches_and_drafts_no_sell_between_them`.
3. The boundary's call uses the book it just read, not the previous one: its `venue_state_from_cache` precedes `self._venue_book = book`. Pinned by Task 3's `test_the_boundary_holds_the_floor_of_the_book_it_just_read`, whose startup pass reads no listing floor and whose boundary read does.
4. A failed book read leaves the previous floors standing, and a process that has read none holds the Cache's. Pinned by Task 3's `test_a_book_read_that_fails_leaves_the_previous_floors_standing` and `test_a_process_that_has_read_no_book_lists_no_floors`.
5. `_is_flat_dust` and `venue_state_from_cache` cannot disagree: both go through `held_ordermin`. Pinned by Task 3's `test_the_dust_floor_is_the_floor_the_engine_holds`.
6. The venue record carries the held floor. Pinned by Task 3's `test_the_boundarys_snapshot_carries_the_executors_floors` and, over a real executor, `test_a_boundarys_snapshot_holds_the_floor_of_the_executors_newest_book`.
7. A start takes the venue's floor over the stored instrument, which the lowered half of the rule rests on. Pinned by Task 4's `test_a_start_holds_the_venues_floor_over_the_stored_instrument`.

---

### Task 1: The venue book keeps the listing's floors (D1, D4)

**Files:**
- Modify: `cli/engine/executor.py`
- Test: `tests/test_engine_executor.py`

- [ ] **Step 1: Write the failing tests**, in `tests/test_engine_executor.py` directly after `test_read_venue_book_keeps_a_basket_coins_earn_coded_balance_apart_and_the_draft_refuses_its_held`, and give `_VenueHoldings` the floors (`ordermin=None` beside `earn=None`, `self.ordermin = {} if ordermin is None else dict(ordermin)`, `ordermin=dict(self.ordermin)` in the `VenueBook` it builds, and its docstring's "the EUR and earn figures it is handed" takes the listing's floors):

```python
def test_read_venue_book_keeps_each_legs_floor_off_the_listing_and_a_moved_row_moves_it(_loopback_credentials):
    with kraken_loopback.serve() as venue:
        venue.asset_pairs["SOLEUR"]["ordermin"] = "0.20000000"
        book = executor_module.read_venue_book(base_url=venue.base_url)
    assert book.ordermin == {"BTC/EUR": 0.00005, "SOL/EUR": 0.2}


def test_a_leg_the_listing_leaves_out_has_no_floor_in_the_book_and_warns_naming_it(_loopback_credentials):
    with kraken_loopback.serve() as venue:
        del venue.asset_pairs["SOLEUR"]
        with _executor_errors(logging.WARNING) as warnings:
            book = executor_module.read_venue_book(base_url=venue.base_url)
    assert book.ordermin == {"BTC/EUR": 0.00005}
    assert [r.getMessage() for r in warnings if "SOL/EUR" in r.getMessage()] == [
        "the venue's listing gives SOL/EUR no ordermin -- the leg stays on the floor the engine loaded at its start"
    ]


@pytest.mark.parametrize("floor", [None, 0.0, -1.0])
def test_a_listing_row_with_no_positive_floor_is_no_floor(floor):
    row = SimpleNamespace(id=INSTRUMENT_IDS["ETH/EUR"], min_quantity=floor)
    assert "ETH/EUR" not in executor_module._listing_floors([row])


def test_a_listing_floor_outside_the_basket_is_not_kept():
    row = SimpleNamespace(id="PEPE/EUR.KRAKEN", min_quantity=1000.0)
    assert set(executor_module._listing_floors([row])) == set()
```

The loopback's committed listing holds two rows, `SOLEUR` and `XXBTZEUR` (`tests/fixtures/kraken_assetpairs_mint.json`), `venue.asset_pairs` the mutable dict it answers from, so a loopback read logs the other legs' WARNING too and the second case filters by symbol.

- [ ] **Step 2: Run them, expect failure.** `uv run pytest tests/test_engine_executor.py -k 'listing' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` fails with `AttributeError` on `ordermin` or `_listing_floors`.

- [ ] **Step 3: Implement**, in `cli/engine/executor.py`. `from dataclasses import dataclass, field, replace`. The field, last in `VenueBook`:

```python
    read_at: datetime
    ordermin: dict[str, float] = field(default_factory=dict)  # per INSTRUMENT_IDS symbol, the listing's floor where it gave one
```

Above `read_venue_book`:

```python
def _listing_floors(instruments) -> dict[str, float]:
    """Each `INSTRUMENT_IDS` leg's `ordermin` off the venue's listing. A leg with no positive floor there is logged
    and left out."""
    listed = {str(instrument.id): instrument.min_quantity for instrument in instruments}
    floors: dict[str, float] = {}
    for symbol, instrument_id in INSTRUMENT_IDS.items():
        raw = listed.get(instrument_id)
        floor = 0.0 if raw is None else float(raw)
        if floor > 0.0:
            floors[symbol] = floor
        else:
            logger.warning("the venue's listing gives %s no ordermin -- the leg stays on the floor the engine loaded at its start", symbol)
    return floors
```

In `read_venue_book`'s `_read`, `return list(positions), state, _listing_floors(instruments)`; `positions, state, floors = asyncio.run(...)`; `ordermin=floors` in the returned `VenueBook`. Extend the docstring's second paragraph's first sentence, which accounts for the listing, with one clause: the listing's floors are kept as `ordermin`.

- [ ] **Step 4: Run them, expect pass**, with the same command, and read the other `read_venue_book` readers: `uv run pytest tests/test_engine_executor.py tests/test_engine_metrics.py tests/test_engine_stub_fidelity.py -k 'venue_book or venue_holdings or fidelity' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`. A stub listing row without `id` or `min_quantity` takes them in the test (Rulings).

- [ ] **Step 5: Commit** `feat(engine): the venue book keeps the floors of the listing it reads`, the per-commit test run's result line in the body, after the gate.

- [ ] **Step 6: Probes.** Arms, each against `tests/test_engine_executor.py`:
  - `floors-kept`: file `cli/engine/executor.py`, mutation `s/ordermin=floors/ordermin={}/`, `-k 'test_read_venue_book_keeps_each_legs_floor'`.
  - `positive-only`: file `cli/engine/executor.py`, mutation `s/if floor > 0.0:/if floor >= -2.0:/`, `-k 'test_a_listing_row_with_no_positive_floor'`.
  - `warned`: file `cli/engine/executor.py`, mutation `/floors\[symbol\] = floor/,/listing gives %s no ordermin/s/logger.warning/logger.debug/`, `-k 'test_a_leg_the_listing_leaves_out'`.

  Then the empty commit, `test(engine): the book's floors proven by infra/scripts/mutate-probe.sh`.

### Task 2: One rule for the floor held (D2, D3)

**Files:**
- Modify: `cli/engine/venuestate.py`
- Test: `tests/test_engine_venuestate.py`

- [ ] **Step 1: Write the failing tests**, after `test_venue_state_freezes_the_twelve_legs`, importing `held_ordermin`:

```python
def test_a_listed_floor_over_the_caches_is_held(fake_cache):
    cached = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW).instruments["ETH/EUR"].ordermin
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW, listed={"ETH/EUR": cached * 2})
    assert vs.instruments["ETH/EUR"].ordermin == cached * 2


def test_a_listed_floor_under_the_caches_leaves_the_caches_held(fake_cache):
    cached = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW).instruments["ETH/EUR"].ordermin
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW, listed={"ETH/EUR": cached / 2})
    assert vs.instruments["ETH/EUR"].ordermin == cached


def test_a_leg_the_listing_names_no_floor_for_keeps_the_caches(fake_cache):
    plain = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW).instruments
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW, listed={"ETH/EUR": plain["ETH/EUR"].ordermin * 2})
    assert vs.instruments["BTC/EUR"] == plain["BTC/EUR"]


@pytest.mark.parametrize(("cached", "listed", "held"), [(0.001, 0.002, 0.002), (0.002, 0.001, 0.002), (0.001, None, 0.001), (None, 0.002, 0.002), (None, None, 0.0)])
def test_the_floor_held_is_the_higher_of_the_two(cached, listed, held):
    assert held_ordermin(cached, listed) == held


def test_the_payload_carries_the_floor_held(fake_cache):
    payload = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW, listed={"ETH/EUR": 7.0}).to_payload()
    assert payload["instruments"]["ETH/EUR"]["ordermin"] == 7.0
```

- [ ] **Step 2: Run them, expect failure.** `uv run pytest tests/test_engine_venuestate.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` fails on the import.

- [ ] **Step 3: Implement**, in `cli/engine/venuestate.py`. `from collections.abc import Callable, Mapping`. After `_to_float`:

```python
def held_ordermin(cached: object, listed: float | None) -> float:
    """The floor a quantity is held against: the venue listing's, never under the Cache's, so a floor the venue
    raised holds from the next book read and one it lowered from the next start (spec 00156 D2)."""
    floor = _to_float(cached)
    return floor if listed is None else max(floor, listed)
```

`def venue_state_from_cache(cache, *, clock: Callable[[], datetime], listed: Mapping[str, float] | None = None) -> VenueState:`, `listed = {} if listed is None else listed` as its first line, and `ordermin=held_ordermin(instrument.min_quantity, listed.get(symbol)),`. Its docstring gains one sentence: `listed` is the newest venue book's floors, and `held_ordermin` decides each leg's. Correct `InstrumentConstraints`' docstring, whose `ordermin`/`lot_step`/`tick_size` "are read live from the Cache": `lot_step`/`tick_size` are the Cache's and `ordermin` is `held_ordermin`'s. The module docstring's second bullet stays true of `lot_step` and `tick_size`, and of `ordermin` where no listing names one: add "where no listing floor stands over it" to it. `VenueState`'s "A frozen, single-instant read of the Cache" gains "with each `ordermin` as `held_ordermin` holds it", and `runtime_concordance`'s "its three **Cache-supplied** `ordermin`/`lot_step`/`tick_size`" reads "venue-supplied" for "Cache-supplied".

- [ ] **Step 4: Run them, expect pass.**

- [ ] **Step 5: Commit** `feat(engine): the floor held is the higher of the Cache's and the listing's`, the per-commit run's result line in the body, after the gate.

- [ ] **Step 6: Probes.** Arms against `tests/test_engine_venuestate.py`:
  - `higher-of-two`: file `cli/engine/venuestate.py`, mutation `s/max(floor, listed)/listed/`, `-k 'test_a_listed_floor_under_the_caches or test_the_floor_held_is_the_higher'`.
  - `overlay-applied`: file `cli/engine/venuestate.py`, mutation `s/ordermin=held_ordermin(instrument.min_quantity, listed.get(symbol)),/ordermin=_to_float(instrument.min_quantity),/`, `-k 'test_a_listed_floor_over_the_caches or test_the_payload_carries'`.

  Then the empty commit, `test(engine): the floor rule proven by infra/scripts/mutate-probe.sh`.

### Task 3: Every venue-truth read holds the newest floors (D3)

**Files:**
- Modify: `cli/engine/executor.py`, `cli/engine/node.py`
- Test: `tests/test_engine_executor.py`, `tests/test_engine_node.py`

- [ ] **Step 1: Write the failing tests.** Give `_boundary_executor` two keywords, `cache_ordermin=None` (a `{symbol: floor}` that overrides the fixture's entry when `instruments` is built) and `listed_floors=None` (passed as `ordermin=` to its `_VenueHoldings`; the function's local `listed` is already the statuses), and its docstring gains "`cache_ordermin` overriding those floors and `listed_floors` being the book's". The fixture's ETH/EUR floor is 0.001 (`tests/fixtures/rung2/venue-12.json`). In `tests/test_engine_executor.py`, after `test_rung_twos_entry_day_drafts_the_ten_legs_at_nav_1000_with_the_notionals_the_floor_arithmetic_gives`:

```python
_TEN_THIRTY_QTY = 0.00109968


def _sell_all_eth(tmp_path, **kwargs):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR")),
        holdings={"ETH/EUR": kwargs.pop("held", _TEN_THIRTY_QTY)},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        **kwargs,
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    return _legs(tmp_path)["ETH/EUR"]


def test_the_boundary_places_the_ten_thirty_sell_on_the_caches_floor_alone(tmp_path):
    assert _sell_all_eth(tmp_path)["outcome"] == "placed"


def test_the_boundary_carries_the_ten_thirty_sell_under_the_listings_raised_floor(tmp_path):
    leg = _sell_all_eth(tmp_path, listed_floors={"ETH/EUR": 0.002})
    assert leg["outcome"] == "carried" and leg["qty"] is None
    assert leg["reason"] == f"sell {_TEN_THIRTY_QTY:.10g} is under ordermin 0.002"


def test_the_boundary_holds_a_lowered_floor_at_the_caches_and_drafts_no_sell_between_them(tmp_path):
    leg = _sell_all_eth(tmp_path, held=0.0015, cache_ordermin={"ETH/EUR": 0.002}, listed_floors={"ETH/EUR": 0.001})
    assert leg["outcome"] == "carried" and leg["reason"] == "sell 0.0015 is under ordermin 0.002"


def _ten_thirty_plan_run(tmp_path, listed):
    eth = INSTRUMENT_IDS["ETH/EUR"]
    client = StubClient(StubCache(instruments=_all_instruments() | {eth: _fake_instrument(eth, ordermin=0.001)}))
    ex = _executor(tmp_path, client=client, venue_holdings=_VenueHoldings({"ETH/EUR": _TEN_THIRTY_QTY}, ordermin=listed))
    _drop_plan(
        tmp_path,
        _plan_dict(intents=[_intent(symbol="ETH/EUR", side="sell", action="close", notional_eur=None, qty=_TEN_THIRTY_QTY)]),
    )
    ex.on_timer(NOW)
    ex.on_quote(_quote(eth, bid=3000.0, ask=3001.0))
    return client


def test_a_plan_holding_the_ten_thirty_sell_is_submitted_on_the_caches_floor_alone(tmp_path):
    assert len(_ten_thirty_plan_run(tmp_path, None).submitted) == 1


def test_a_plan_holding_the_ten_thirty_sell_is_refused_under_the_listings_raised_floor(tmp_path):
    client = _ten_thirty_plan_run(tmp_path, {"ETH/EUR": 0.002})
    assert client.submitted == []
    assert "is below ordermin 0.002" in _intent_entry(tmp_path, 0)["reasons"][0]


def test_the_boundary_holds_the_floor_of_the_book_it_just_read(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR")),
        holdings={"ETH/EUR": _TEN_THIRTY_QTY},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        listed_floors={"ETH/EUR": 0.002},
    )
    holdings = ex._venue_holdings
    # The startup pass's book names no floor, the boundary's the raised one.
    ex._venue_holdings = lambda: dataclasses.replace(holdings(), ordermin={}) if holdings.calls == 0 else holdings()
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    leg = _legs(tmp_path)["ETH/EUR"]
    assert holdings.calls == 2 and leg["outcome"] == "carried"
    assert leg["reason"] == f"sell {_TEN_THIRTY_QTY:.10g} is under ordermin 0.002"


@pytest.mark.parametrize(("listed", "disposition"), [(None, "refused"), ({"BTC/EUR": 0.001}, "accepted")])
def test_the_mixed_inventory_floor_is_the_floor_the_engine_holds(tmp_path, listed, disposition):
    """0.0005 BTC is over the stub's 0.0001 and under a listing floor of 0.001: inventory on the Cache's floor alone, dust under the one held."""
    ex = _executor(
        tmp_path,
        client=StubClient(),
        config=_cache_config(tmp_path),
        venue_holdings=_VenueHoldings({"BTC/EUR": 0.0005}, ordermin=listed),
        venue_positions=_VenuePositions({}),
    )
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(leverage=2)]))
    ex.on_timer(NOW)
    assert _plan_entry(tmp_path)["disposition"] == disposition


@pytest.mark.parametrize(
    ("cached", "listed", "held", "lines"),
    [(0.0001, 0.01, 0.005, 0), (0.0001, 0.001, 0.005, 1), (0.02, 0.001, 0.01, 0), (None, 0.01, 0.005, 0)],
)
def test_the_dust_floor_is_the_floor_the_engine_holds(tmp_path, cached, listed, held, lines):
    btc = INSTRUMENT_IDS["BTC/EUR"]
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    instruments = _all_instruments() | {btc: _fake_instrument(btc, ordermin=cached)}
    ex = _executor(tmp_path, client=StubClient(StubCache(instruments=instruments)), venue_holdings=_VenueHoldings())
    book = _VenueHoldings({"BTC/EUR": held}, ordermin={"BTC/EUR": listed})()
    with _executor_errors(logging.WARNING) as warnings:
        ex._settle_from_book(book, "the startup pass")
    assert len([r for r in warnings if "the venue holds" in r.getMessage()]) == lines


def test_a_boundarys_snapshot_holds_the_floor_of_the_executors_newest_book(tmp_path):
    eth = INSTRUMENT_IDS["ETH/EUR"]
    cache = StubCache(instruments=_all_instruments() | {eth: _fake_instrument(eth, ordermin=0.001)})
    ex = _executor(tmp_path, client=StubClient(cache), venue_holdings=_VenueHoldings({}, ordermin={"ETH/EUR": 0.002}))
    strategy = SimpleNamespace(cache=cache, _now=lambda: NOW, _executor=ex)
    assert ShadowStrategy._snapshot_venue_state(strategy).instruments["ETH/EUR"].ordermin == 0.001
    ex._settle_positions_from_venue("the startup pass")
    assert ShadowStrategy._snapshot_venue_state(strategy).instruments["ETH/EUR"].ordermin == 0.002


def test_a_process_that_has_read_no_book_lists_no_floors(tmp_path):
    assert _executor(tmp_path, venue_holdings=_VenueHoldings()).listed_ordermin() is None


def test_a_book_read_that_fails_leaves_the_previous_floors_standing(tmp_path):
    holdings = _VenueHoldings({}, ordermin={"ETH/EUR": 0.002})
    ex = _executor(tmp_path, venue_holdings=holdings)
    assert ex._settle_positions_from_venue("the startup pass") is True
    holdings._raises = EngineError("the read failed")
    assert ex._settle_positions_from_venue("the re-read pass") is False
    assert ex.listed_ordermin() == {"ETH/EUR": 0.002}
```

The `_only("BTC/EUR")` record gives ETH/EUR a target of 0.0, so its leg sells the whole holding. In `tests/test_engine_node.py`, after `_CacheReadableStrategy`:

```python
def test_the_boundarys_snapshot_carries_the_executors_floors(tmp_path, monkeypatch):
    strategy = _CacheReadableStrategy(_config(tmp_path))
    strategy._executor = types.SimpleNamespace(listed_ordermin=lambda: {"ETH/EUR": 7.0})
    seen = []
    monkeypatch.setattr(node, "venue_state_from_cache", lambda cache, *, clock, listed: seen.append(listed))
    strategy._snapshot_venue_state()
    assert seen == [{"ETH/EUR": 7.0}]


def test_a_strategy_with_no_executor_snapshots_on_no_listing(tmp_path, monkeypatch):
    strategy = _CacheReadableStrategy(_config(tmp_path))
    seen = []
    monkeypatch.setattr(node, "venue_state_from_cache", lambda cache, *, clock, listed: seen.append(listed))
    strategy._snapshot_venue_state()
    assert seen == [None]
```

The same step gives the three existing stubs of `venue_state_from_cache` the new keyword, so each still does its own work and not a `TypeError` a catch would hide: `boom` in `test_snapshot_venue_state_logs_and_returns_none_on_any_exception` and `unreadable_cache` in `test_an_engine_error_at_the_boundary_journals_the_error_venue_record` (`tests/test_engine_node.py`), and `_stateless` in `test_an_intent_symbol_absent_from_venue_truth_is_refused` (`tests/test_engine_executor.py`), each `(cache, *, clock, listed)`.

- [ ] **Step 2: Run them, expect failure.** `uv run pytest tests/test_engine_executor.py -k 'ten_thirty or lowered_floor or dust_floor_is_the_floor or lists_no_floors or previous_floors or book_it_just_read or mixed_inventory_floor or snapshot_holds_the_floor' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`. 15 cases: the two `..._on_the_caches_floor_alone` controls and the four that pin the Cache's floor standing pass already, `test_the_boundary_holds_a_lowered_floor_at_the_caches_and_drafts_no_sell_between_them`, `test_the_mixed_inventory_floor_is_the_floor_the_engine_holds[None-refused]`, `test_the_dust_floor_is_the_floor_the_engine_holds[0.0001-0.001-0.005-1]` and `[0.02-0.001-0.01-0]`; the other nine fail. Then `uv run pytest tests/test_engine_node.py -k 'test_the_boundarys_snapshot_carries or test_a_strategy_with_no_executor_snapshots' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, expect 2 failed.

- [ ] **Step 3: Implement.** In `cli/engine/executor.py`, `from cli.engine.venuestate import InstrumentConstraints, held_ordermin, venue_state_from_cache`, and on `ProbeExecutor`, directly above `_settle_positions_from_venue`:

```python
    def listed_ordermin(self) -> dict[str, float] | None:
        """The newest venue book's floors, or None before this process has read one."""
        return None if self._venue_book is None else self._venue_book.ordermin
```

The two calls off a held book, in `_accept_plan` and at intent start: `state = venue_state_from_cache(self._cache, clock=self._now, listed=self.listed_ordermin())`. The boundary's, in the draft pass: `state = venue_state_from_cache(self._cache, clock=self._now, listed=book.ordermin)`. `_is_flat_dust`'s last two lines:

```python
        instrument = self._cache.instrument(InstrumentId.from_str(INSTRUMENT_IDS[symbol]))
        return instrument is not None and 0.0 < venue_qty < held_ordermin(instrument.min_quantity, book.ordermin.get(symbol))
```

In `cli/engine/node.py`, `_snapshot_venue_state`'s `try`:

```python
            listed = None if self._executor is None else self._executor.listed_ordermin()
            return venue_state_from_cache(self.cache, clock=self._now, listed=listed)
```

Its docstring's first clause names the wrapped call and stays true.

- [ ] **Step 4: Run them, expect pass,** then the existing dust and node cases: `uv run pytest tests/test_engine_executor.py -k 'dust or under_ordermin or flat' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs` and `uv run pytest tests/test_engine_node.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`. A stub executor in `tests/test_engine_node.py` lacking `listed_ordermin` takes it in the test (Rulings).

- [ ] **Step 5: Commit** `feat(engine): every venue-truth read holds the newest book's floors`, the per-commit run's result line in the body, after the gate.

- [ ] **Step 6: Probes.** Arms against the test file each names:
  - `boundary-fresh-book`: file `cli/engine/executor.py`, mutation `s/clock=self._now, listed=book.ordermin)/clock=self._now, listed=self.listed_ordermin())/`, test `tests/test_engine_executor.py`, `-k 'test_the_boundary_holds_the_floor_of_the_book_it_just_read'`.
  - `intent-start`: file `cli/engine/executor.py`, mutation `/if not _level_permits(verdict.level, intent):/,/venue truth unavailable -- refusing intent/s/, listed=self.listed_ordermin())/)/`, test `tests/test_engine_executor.py`, `-k 'test_a_plan_holding_the_ten_thirty_sell_is_refused'`.
  - `accept-plan`: file `cli/engine/executor.py`, mutation `/self._reconciliation_refusal,),/,/venue truth unavailable -- refusing plan/s/, listed=self.listed_ordermin())/)/`, test `tests/test_engine_executor.py`, `-k 'test_the_mixed_inventory_floor_is_the_floor_the_engine_holds'`.
  - `dust-rule`: file `cli/engine/executor.py`, mutation `s/venue_qty < held_ordermin(instrument.min_quantity, book.ordermin.get(symbol))/venue_qty < float(instrument.min_quantity or 0.0)/`, test `tests/test_engine_executor.py`, `-k 'test_the_dust_floor_is_the_floor_the_engine_holds'`.
  - `node-floors`: file `cli/engine/node.py`, mutation `s/clock=self._now, listed=listed)/clock=self._now)/`, test `tests/test_engine_node.py`, `-k 'test_the_boundarys_snapshot_carries'`.
  - `composed-link`: file `cli/engine/node.py`, the same mutation, test `tests/test_engine_executor.py`, `-k 'test_a_boundarys_snapshot_holds_the_floor'`.
  - `boundary-overlay`: file `cli/engine/executor.py`, mutation `s/clock=self._now, listed=book.ordermin)/clock=self._now)/`, test `tests/test_engine_executor.py`, `-k 'test_the_boundary_carries_the_ten_thirty_sell'`.
  - `lowered-at-the-boundary`: file `cli/engine/venuestate.py`, mutation `s/max(floor, listed)/listed/`, test `tests/test_engine_executor.py`, `-k 'test_the_boundary_holds_a_lowered_floor'`.
  - `no-book`: file `cli/engine/executor.py`, mutation `s/return None if self._venue_book is None else self._venue_book.ordermin/return {}/`, test `tests/test_engine_executor.py`, `-k 'test_a_process_that_has_read_no_book'`.
  - `failed-read`: file `cli/engine/executor.py`, mutation `/holdings could not be read at %s/,/return False/s/return False/self._venue_book = None; return False/`, test `tests/test_engine_executor.py`, `-k 'test_a_book_read_that_fails'`.
  - `no-executor`: file `cli/engine/node.py`, mutation `s/listed = None if self._executor is None else self._executor.listed_ordermin()/listed = self._executor.listed_ordermin()/`, test `tests/test_engine_node.py`, `-k 'test_a_strategy_with_no_executor_snapshots'`.

  Then the empty commit, `test(engine): the floors' readers proven by infra/scripts/mutate-probe.sh`.

### Task 4: Two cases hold the two premises (D5)

**Files:**
- Test: `tests/test_engine_node.py`, `tests/test_cache_restart.py`
- Modify: `tests/cache_restart_child.py`, `tests/slow-cases.txt`, `.claude/skills/zcrypto-bump-nautilus/SKILL.md`

- [ ] **Step 1: Write the case**, after `test_the_twelve_instruments_are_in_the_cache_when_the_strategy_starts`, in the form that case's gate takes, which `tests/test_live_venue_opt_in.py` matches. Kraken's `wsname` spells BTC and DOGE as `XBT` and `XDG`, the mapping `cli/snapshot/assetpairs.py` keeps at its head:

```python
def test_the_listing_the_book_reads_carries_krakens_ordermin_on_every_leg():
    """The floors the venue book keeps are Kraken's own on all twelve legs of the real listing."""
    if os.environ.get("ZCRYPTO_LIVE_VENUE_TESTS") != "1":
        pytest.skip("needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it")
    if not _kraken_public_reachable():
        pytest.fail("ZCRYPTO_LIVE_VENUE_TESTS=1 was set but Kraken's public endpoint is unreachable")
    import asyncio
    import urllib.request

    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    from cli.engine.executor import _listing_floors
    from cli.engine.instruments import INSTRUMENT_IDS
    from cli.snapshot.assetpairs import _COMMON_TO_KRAKEN

    def wsname(symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{_COMMON_TO_KRAKEN.get(base, base)}/{_COMMON_TO_KRAKEN.get(quote, quote)}"

    async def listing():
        return await KrakenSpotHttpClient(api_key=None, api_secret=None).request_instruments()

    floors = _listing_floors(asyncio.run(asyncio.wait_for(listing(), 60)))
    with urllib.request.urlopen("https://api.kraken.com/0/public/AssetPairs", timeout=30) as response:
        pairs = json.load(response)["result"]
    by_wsname = {row["wsname"]: float(row["ordermin"]) for row in pairs.values() if row.get("wsname")}
    assert floors == pytest.approx({symbol: by_wsname[wsname(symbol)] for symbol in INSTRUMENT_IDS})
```

- [ ] **Step 2: Run the live case opted in, expect pass.** `ZCRYPTO_LIVE_VENUE_TESTS=1 uv run pytest tests/test_engine_node.py -k 'test_the_listing_the_book_reads' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, and without the flag, expect one skip. Then `uv run pytest tests/test_live_venue_opt_in.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, expect pass, since it walks the skip gates.

- [ ] **Step 3: Write the restart case.** In `tests/cache_restart_child.py`, `_venue_state`'s return gains the floors the engine's reader freezes: `"ordermin": {symbol: constraints.ordermin for symbol, constraints in state.instruments.items()}`, and its docstring gains "and `ordermin`, the Cache's floor, with no listing passed". In `tests/test_cache_restart.py`, after `_spot_process` and `_BUMP`, which it reads:

```python
def test_a_start_holds_the_venues_floor_over_the_stored_instrument(tmp_path):
    basket = _basket_pairs()
    eth = next(key for key, row in basket.items() if row.get("altname") == "ETHEUR")

    def listing(floor: str) -> dict:
        return basket | {eth: basket[eth] | {"ordermin": floor}}

    valkey = _Valkey(tmp_path / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "node", valkey.port)
        first, _, _ = _spot_process(node, 1, _EUR_ONLY, pairs=listing("0.002"))
        stored = _keys(valkey.port)
        second, _, _ = _spot_process(node, 2, _EUR_ONLY, pairs=listing("0.001"))
    finally:
        valkey.stop()

    assert first["errors"] == [] and second["errors"] == []
    assert "trader-SHADOW-001:instruments:ETH/EUR.KRAKEN" in stored
    floors = [record["venue_state_at_start"]["ordermin"]["ETH/EUR"] for record in (first, second)]
    assert floors == [0.002, 0.001], f"{_BUMP}: a start no longer takes the venue's floor over the stored instrument: {floors}"
```

Its id goes in `tests/slow-cases.txt`, in sorted place, since it starts two processes.

- [ ] **Step 4: Run it, expect pass.** `uv run pytest tests/test_cache_restart.py -k 'test_a_start_holds_the_venues_floor' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, about a minute, then `uv run pytest tests/test_slow_cases.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`.

- [ ] **Step 5: Commit** `test(engine): two cases hold the listing's floor and a start's reload of it`, the per-commit run's result line, the opted-in run's, the restart case's and the two guards' in the body, after the gate. Its message records the two skipped probes, as the Global Constraints say.

- [ ] **Step 6: The bump runs the live case.** Load `zcrypto-refine-rules` before editing a skill file, as its description asks. In `.claude/skills/zcrypto-bump-nautilus/SKILL.md`, the list under `## Step 3 — the static guards and the premises` gains, after the item that opens `` `tests/test_engine_stub_fidelity.py` ``:

```markdown
- `ZCRYPTO_LIVE_VENUE_TESTS=1 uv run pytest tests/test_engine_node.py -k test_the_listing_the_book_reads -q -p no:cacheprovider` — the floors the venue book keeps against public `AssetPairs` on all twelve legs; the flag is what opens it, and without the flag it reads as a skip.
```

Commit it alone, `claude(skills): the nautilus bump runs the listing's floor against Kraken`, the `staged-kind` hook refusing it beside any other kind, after the gate, with the result line of `T="$(infra/scripts/consumers.sh --direct .claude/skills/zcrypto-bump-nautilus/SKILL.md)"; [ -n "$T" ] && uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, or its message says the list is empty.

### Task 5: The runbook's three edits, plan 00092's R0, the topic's close and the decisions-log entry

**Files:**
- Modify: `infra/runbooks/engine-procedures.md`, `docs/plans/00092-rung-3-accumulation.md`, `docs/research/14.phase6-decisions.md`, `docs/open-topics/README.md`
- Move: `docs/open-topics/T0224-the-engine-and-the-helper-read-krakens-live-ordermin.md` to `docs/open-topics/archive/`

- [ ] **Step 1: Read the surfaces.** Load `zcrypto-refine-rules` before editing a runbook page, as its description asks, `topic-ops` before the topic, and `iteration-closeout` before the decisions-log entry. `grep -n 'min_quantity\|Cache instrument' infra/runbooks/*.md .claude/skills/zcrypto-refdata-sweep/SKILL.md` names any other page that states the floor's source; a page it names is corrected in this task and the commit says so.

- [ ] **Step 2: The runbook's three edits, in `infra/runbooks/engine-procedures.md`'s `engine-rung-3` section, each found by its text, never a line number.** In `### What it means`, `The loop`'s "a leg is carried when its delta is under the venue's floors" reads "under the floors the engine holds". In the entry gate, the item that opens `**The reference-data sweep inside the week of entry**`, after its sentence, gains: "With it, the engine's floors, each on the workstation: the engine row of `docs/reference/fleet-pins.md` names a revision holding the rule, `git show <revision>:cli/engine/venuestate.py | grep -c held_ordermin` above 0, at 0 the stop clearing by rolling the newest `develop` build under `zcrypto-rollout-image`, ahead of the sweep; and the newest venue record's twelve floors, `jq '.state.instruments | map_values(.ordermin)' /mnt/zhao-crypto/engine-journal/<day>/venue-<HH>.json`, match that register's `Ordermin` column by `Symbol`, a difference settled by the leg's row in public `AssetPairs`: a floor above Kraken's on a leg Kraken lowered since the engine's start is the limit the daily read names, which step 3's converge reloads, and another floor above Kraken's is the stop. The record reads the same on a revision without the rule: the revision's read shows the rule, and the record's shows no floor above Kraken's." In the daily read, item 1, directly under its paragraph, one sub-item:

```markdown
   - A carried leg's `ordermin` is the higher of the floor the engine loaded at its start and the floor in the venue listing it last read. A floor Kraken raised holds from the next read, and one it lowered holds from the next start, so until then a remainder between the two floors is carried though Kraken would take it, a limit that owes no restart of its own.
```

In `docs/plans/00092-rung-3-accumulation.md`'s R0, read (5)'s "`zcrypto-refdata-sweep`'s verdict read from the rendered tables." reads "`zcrypto-refdata-sweep`'s verdict read from the rendered tables, and the engine's floors as the reference-data sweep item of `infra/runbooks/engine-procedures.md`'s `engine-rung-3` step 1 reads them."

- [ ] **Step 3: Close the topic.** `git mv` it to `docs/open-topics/archive/`; `status: resolved`, `ripe_when:` deleted; `## Suggested next steps` gone; a `## Resolution` section: spec 00156 and this branch's pull request; a raised floor holds from the next book read and a lowered one from the next start, the lowered half bounded by the owner's ruling and not open (spec D2), the pin row's revision and the record's floors read at `engine-rung-3`'s entry gate, the 2026-10-30 case proved by `test_the_boundary_carries_the_ten_thirty_sell_under_the_listings_raised_floor` and `test_a_plan_holding_the_ten_thirty_sell_is_refused_under_the_listings_raised_floor`. Then `uv run python infra/scripts/topics-index.py`.

- [ ] **Step 4: The decisions-log entry**, appended to `docs/research/14.phase6-decisions.md`, keyed `[00156]`, verbatim as written here:

```markdown
[00156] Where do the engine and the helper read Kraken's `ordermin`? (Decision: 1)
  1. **The listing the boundary's venue read already fetches** — fresh at each read, no new venue call, and a failed read already stops the draft; it touches the engine's order path.
  2. **Public `AssetPairs`** — fresh at each boundary and independent of the adapter; one more venue call and a second failure path.
  3. **A committed floor per leg under a drift guard** — only as fresh as the last sweep, so a move between sweeps still gets through.
  The owner's words of 2026-11-05: "after the TLS fix's merge, please check if we can resolve T0224 earlier, I'd like to have it ready before rung-3 starts." and "boundary's listing, hold the bulk rollout, Q2 and Q5 as recommended"; of the second, the first clause is this decision, the second holds the bulk image until this merges, and the third answers the rung 2 exit report's two questions.

[00156] What does the engine do with a floor the venue lowered below the Cache's? (Decision: 1)
  1. **Hold the higher of the two, so a lowered floor holds from the next start** — never hands the library a quantity its risk engine denies and adds nothing to the live path; a remainder between the floors is carried until the next start, as it is today, under 2 EUR per leg on the last sweep's lowered EUR legs.
  2. **The same, and reload the lowered leg with `Strategy.request_instrument`** — the lower floor holds within one read and a failed reload leaves the higher floor; about ten more lines, and an instrument replaced mid-run on the live engine, unattended, on a path no real moved floor can be read through at will.
  The owner's pick of 2026-11-05: "Wait for restart (Recommended)".

[00156] What does rung 3's entry gate read of the engine's floors? (Decision: 2)
  1. **The venue record against public `AssetPairs` alone** — one read, which reads the same with this change absent, since a disarmed engine's one book read follows the Cache's own load.
  2. **The pin row's revision holding the rule, and the record against the sweep's register** — the revision shows the rule, the record shows no floor above Kraken's on a leg Kraken did not lower, and an offline case composing a real executor with the node's snapshot proves the path.
  3. **The same, and the revision read again at the arm converge** — a second copy of one read, since each later `develop` build descends from the revision the gate read.
  Decided by the implementing session: the reads that can tell the states apart, each at the gate that can stop on them.

[00156] What does the engine do with a leg the venue's listing gives no floor? (Decision: 1)
  1. **Log a WARNING per read and leave that leg on the Cache's floor** — one leg's gap does not stop the other eleven, and the status read already carries a leg the venue does not list as `TRADING`.
  2. **Refuse the whole book** — a stale floor never stands, and one leg's missing row stops the boundary's draft for all of them.
  Decided by the implementing session: the book read is what the draft's other reads depend on, and a leg's floor is not.
```

- [ ] **Step 5: Commit, each its own:** `docs(runbooks): rung 3 says when a moved ordermin takes effect and its gate reads the floors`, `docs(plans): plan 00092's R0 reads the engine's floors at its sweep`, and `docs(open-topics): T0224 resolved by spec 00156`, carrying the topic, the index and the log entry, each with the result line of `T="$(infra/scripts/consumers.sh --direct <its paths>)"; [ -n "$T" ] && uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`, or its message says the list is empty, after the gate. The decisions-log entry is this plan's closing task; the change-index row is `open-pr`'s.
