# 00111 — the adapter's blind reads: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make flatten see what is actually at the venue, and stop the engine's funding gate from reading a free balance that overstates available cash — then prove both against a live fixture rather than a fake that agrees with us.

**Architecture:** Two independent fixes to our own code, both caused by the same nautilus Kraken adapter. Flatten populates the client's instrument cache before it reads (D1). `plan_refusals` gains a fail-closed refusal when the balance is known untrustworthy (D2) plus a loud assertion when that stops being true (D3). A committed `kraken-cli` script mints the fixture (D6), and verification runs against the live account through a non-adapter witness (D4, D5).

**Tech Stack:** Python 3.14, `uv`, pytest. `nautilus_trader` 2.0.0rc4.dev20260825 (pinned). `kraken-cli` 0.4.1 — **workstation only**.

**Spec:** `docs/specs/00111-adapter-blind-reads-design.md`

## Global Constraints

- **`kraken-cli` is never a runtime dependency.** Not imported by `cli/`, not present in CI, not invoked by the engine. It appears only in `infra/scripts/` and in operator prose.
- **A test double that does not model the defect proves nothing.** `FakeClient` currently returns orders regardless of its instrument cache, so a test written against it passes with and without the fix. Task 1 fixes the double *before* Task 2 fixes the code, and the reds that fix produces are read before the production change lands.
- **Verification is by identity, never by row count** (spec D4). Fixture txids and symbols, matched against a `kraken-cli` read — never the adapter compared with itself.
- **Nothing in this plan converges a host, pushes Grafana, or arms anything.** The consequence is load-bearing and easy to miss: `/usr/local/sbin/zcrypto-flatten` execs `{{ engine_image }}@{{ engine_image_digest }}`, the *deployed* pin, so **no run through the host wrapper can contain this branch's code** and an empty read from it proves nothing. Task 5 runs from the worktree instead.
- **The two existing SOL/EUR orders (`OZRI5U-U7WGD-OYCOMW` spot, `OVNLAJ-6PXBH-T4GDXF` 2:1 margin) must survive every task.** Nothing here cancels them.
- Every commit carries `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>` and **no `Claude-Session:` trailer**. Each code commit is reviewed by a different agent before push, at the **Fable floor** — this touches the live trade path.

## File Structure

| File | Responsibility |
|---|---|
| `tests/test_engine_flatten.py` | `FakeClient` gains instrument-cache semantics; the red test for the blind read |
| `cli/engine/flatten.py` | `read_listing` result is fed to the client's cache before `read_snapshot` reads |
| `cli/engine/probeplan.py` | `plan_refusals` gains the untrustworthy-balance refusal and the `locked > 0` assertion |
| `tests/test_engine_probeplan.py` | Guard tests: refuses while orders rest; asserts loudly when `locked` becomes real |
| `cli/engine/venuestate.py` | `VenueState` carries `balances_locked` so the guard can see holds — a live field, **not** journalled by `to_payload()` |
| `cli/engine/executor.py`, `cli/engine/command.py` | The two `plan_refusals` call sites, threaded |
| `infra/scripts/kraken-fixture.sh` | Mints, verifies and closes the fixture over `kraken-cli`; `--validate` default |
| `infra/scripts/probe-with-vaulted-key.sh` | Gains a second hardcoded target so Task 5 can run this branch's flatten with the vaulted key |
| `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` | Gains the order + position verification row |
| `docs/iterations-history-phase6.md` | The iteration entry (final task) |

---

### Task 1: Make the test double model the defect

**Files:**
- Modify: `tests/test_engine_flatten.py` (`FakeClient`)
- Test: `tests/test_engine_flatten.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FakeClient` with `cache_instrument(instrument)` and a cache-gated **order** read, used by Task 2.

**This task does not commit.** Its filter drops every order row whose `raw_symbol` misses the cache, and until Task 2 makes production call `cache_instrument` the cache is empty on every `run_flatten` path — so two existing tests that drive `run_flatten` cannot be made green here by any edit to this file. Tasks 1 and 2 share Task 2's commit; the double is still written and seen to bite before the production change, which is what the double-must-model-the-defect constraint asks for.

**The position read is deliberately left ungated.** Only the ORDER read was measured against the live account, and a double that models a cache gate nobody has observed would manufacture agreement with a mechanism we are guessing at — the failure this task exists to prevent, inverted. What covers the position path is Task 5's live read against a minted position (spec D5), not an offline assumption.

- [ ] **Step 1: Teach `FakeClient` the upstream cache semantics**

In `FakeClient.__init__`, add the cache:

```python
        # The real client drops any order whose raw symbol misses `instruments_cache`, silently and
        # with a successful empty return (spec 00111's measured basis). Modelled here because a
        # double that answers regardless of the cache makes the blind-read test pass either way.
        self.cached_symbols: set[str] = set()
```

**And add `"cached_symbols"` to `_FAKE_CLIENT_PLUMBING` in the same edit.** `test_no_stub_in_the_red_button_suite_offers_a_name_its_real_library_type_lacks` fails on any name the stub offers that `KrakenSpotHttpClient` lacks; measured, the violation set with this attribute added and unlisted is exactly `['cached_symbols']`. Do **not** add `cache_instrument` there — the real class carries it, and that guard's `stale` half fails on any plumbing entry the real type does have.

Add the writer the real client exposes:

```python
    def cache_instrument(self, instrument) -> None:
        self.calls.append(("cache_instrument", {"instrument": _norm(instrument)}))
        raw = getattr(instrument, "raw_symbol", None)
        self.cached_symbols.add(str(raw) if raw is not None else str(getattr(instrument, "id", "")))
```

Gate the order read on it:

```python
    async def request_order_status_reports(self, account_id, **kw):
        self._record("request_order_status_reports", account_id, kw)
        self._maybe_raise("request_order_status_reports")
        rows = self._next(self._orders)
        if rows is None:
            # `orders=[[], None, []]` is a real fixture: the venue answering nothing is a branch
            # `read_open_orders` owns and names. Filtering it would raise TypeError inside the
            # double instead, which reaches production as a different failure with a different
            # message.
            return None
        # The silent drop: no warning, no error, a successful empty list.
        return [r for r in rows if str(getattr(r, "raw_symbol", "")) in self.cached_symbols]
```

- [ ] **Step 2: Write the test that pins the double's semantics**

It PASSES on the double alone — it is a claim about the fixture, not about production, and Step 4 says so.

```python
def test_read_open_orders_is_blind_until_the_instrument_cache_is_populated():
    """The defect 00111 fixes: a client whose instrument cache is empty returns NO orders, with no
    error, for an account that has them. The second half is the control -- the same client, same
    orders, cache populated -- so a passing implementation cannot be one that simply returns rows."""
    order = SimpleNamespace(raw_symbol="SOLEUR")

    cold = _client_with(orders=[order], symbols=("SOL/EUR",))
    assert _sync(flatten.read_open_orders(cold, flatten.Recorder())) == []

    warm = _client_with(orders=[order], symbols=("SOL/EUR",))
    for inst in _listing("SOL/EUR").values():
        warm.cache_instrument(inst)
    assert len(_sync(flatten.read_open_orders(warm, flatten.Recorder()))) == 1
```

**Two facts about the existing fixtures, both checked rather than assumed:**

- **There is no order-row builder and none is needed.** `read_open_orders`'s own docstring says only the LIST is load-bearing and no per-row field is required; existing tests pass `orders=[[]]` or a bare `object()`. So the row here is an inline `SimpleNamespace(raw_symbol="SOLEUR")` — the one attribute the double's filter keys on. Import `SimpleNamespace` from `types` if the module does not already.
- **`_Instrument` does NOT currently carry `raw_symbol`** — it sets `self.id = f"{symbol}.KRAKEN"` plus the constraint floats. **Add `self.raw_symbol = symbol.replace("/", "")`** so `_listing("SOL/EUR")` yields a row whose raw symbol is `SOLEUR`, matching what Kraken returns in `descr.pair` and what the real cache keys on.

- [ ] **Step 3: Migrate the fixture family the filter now drops**

`str(getattr(object(), "raw_symbol", ""))` is `""`, which is in no cache, so **every bare-`object()` order row is now dropped**. That family is exactly three rows, enumerated so the next reader does not re-derive it — grep `object()` in `tests/test_engine_flatten.py` returns these and nothing else:

| line | test | what it asserts |
|---|---|---|
| 867 | `test_the_rendered_plan_names_every_leg_every_dust_line_and_everything_it_cannot_touch` | `"1 resting order" in text` |
| 1765 | `test_a_resting_order_that_outlived_the_cancel_exits_two_even_with_nothing_else_open` | `_run(client, tmp_path) == 2` |
| 1958 | `test_the_residuals_are_judged_against_the_final_snapshot_and_never_the_pre_sweep_one` | `doc["snapshot_after"]["open_orders"] == 1` |

The same enumeration has a fourth member of a different shape, already handled by Step 1's `None` guard rather than by a fixture edit: line 1560's `orders=[[], None, []]` in `test_a_failing_post_cancel_order_count_does_not_cost_the_closes`, where the venue answering nothing is the subject of the test.

Give each row a symbol the surrounding fixture actually lists — `SimpleNamespace(raw_symbol="BTCEUR")` at all three, since `_flat_client` defaults `symbols=("BTC/EUR",)` and line 867's `_client_with` lists `BTC/EUR` first. **These are the correct kind of update**: the assertion is unchanged, only the row gains the attribute production's cache keys on. Weakening any of the three assertions instead would delete the red button's only post-cancel residual-order coverage.

The 867 case needs one more line, and it is the one that says what the fix means: that test drives `read_listing` and `read_snapshot` by hand, so it must cache the listing itself before reading, exactly as Task 2 makes `run_flatten` do —

```python
    listing = _sync(flatten.read_listing(client, rec))
    for inst in listing.values():
        client.cache_instrument(inst)
```

867 then passes at this point in the branch. 1765 and 1958 go through `run_flatten` and stay RED until Task 2 — that is expected and is why this task does not commit.

- [ ] **Step 4: Run it and confirm exactly the expected reds**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: the new `instrument_cache_is_populated` test **PASSES** (it pins the double's semantics, not the production fix — if its cold half fails, the double is not modelling the drop), 867 passes, and exactly two tests fail: `a_resting_order_that_outlived_the_cancel` and `the_residuals_are_judged_against_the_final_snapshot`. **Read the failure text, not just the count** — both must fail on the order count reaching zero. Any third red is a fixture this enumeration missed; find it before continuing.

No commit here — see the note under Interfaces. The double's proof that it bites is Task 2's mutation probe, which needs a clean tree and therefore runs after Task 2's commit.

---

### Task 2: Flatten populates the cache before it reads

**Files:**
- Modify: `cli/engine/flatten.py` (`run_flatten`)
- Test: `tests/test_engine_flatten.py`

**Interfaces:**
- Consumes: Task 1's `FakeClient.cache_instrument`.
- Produces: `read_listing` runs before `read_snapshot`, and its rows are cached.

- [ ] **Step 1: Write the failing test**

```python
def test_run_flatten_caches_the_listing_before_it_reads_orders(tmp_path):
    """Order matters and is the whole fix: the listing must be fetched AND fed to the client's cache
    before the snapshot reads orders, or every order is dropped. Asserts on call ORDER, because a
    version that caches after reading is indistinguishable by outcome on a flat account."""
    client = _client_with(orders=[SimpleNamespace(raw_symbol="SOLEUR")], symbols=("SOL/EUR",))
    _run(client, tmp_path, execute=False)
    names = [c[0] for c in client.calls]
    assert names.index("cache_instrument") < names.index("request_order_status_reports")
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_engine_flatten.py -k caches_the_listing_before -v`
Expected: FAIL — `cache_instrument` is never called, so `names.index` raises `ValueError`.

- [ ] **Step 3: Implement**

In `run_flatten`, the three lines inside the `try` currently read `snapshot` first. Replace them with:

```python
        listing = await read_listing(client, rec)
        # BEFORE the snapshot, not after: the client drops every order whose raw symbol misses its
        # instrument cache, and `request_instruments` does NOT populate that cache -- only
        # `cache_instrument` does (spec 00111 D1). Reading first returns a silent empty list.
        # The conversion matches every other read in this file: this function's callers get
        # `FlattenUnreachable` and an exit code, never a traceback out of the red button.
        try:
            for row in listing.values():
                client.cache_instrument(row)
        except Exception as exc:  # noqa: BLE001
            raise FlattenUnreachable(f"the instrument cache could not be populated: {exc}") from exc
        snapshot = await read_snapshot(client, rec)
        plan = await build_plan(client, rec, snapshot, listing)
```

`read_listing` is `-> dict[str, Any]` and builds `listing[symbol] = row` where `row` is what `request_instruments()` returned, so `.values()` are the instrument objects the cache wants; `cache_instrument` is synchronous on the real client and is correctly called un-awaited.

- [ ] **Step 4: Run the full flatten suite**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: all pass — including Task 1 Step 4's two known reds, which this fix is what turns green. Several existing tests assert on `client.calls` ordering — update any whose expectations the new call legitimately changes, and **read each one before changing it**: a test that now fails because the sequence genuinely changed is correct to update; one failing because the fix broke it is not.

- [ ] **Step 5: Commit — Task 1's work lands here too**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "fix(engine_flatten): cache the listing before reading, or every order is dropped"
```

- [ ] **Step 6: Mutation-prove the guard**

After the commit, because `mutate-probe.sh` refuses a dirty worktree (its `git status --porcelain` check) and restores with `git checkout --`. Both operands are named, because the script requires a `--control` and exits rc 2 without one, rc 5 if the control does not fail, and rc 6 on a sed that matches nothing:

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/flatten.py \
  --control 's/listing = await read_listing(client, rec)/listing = {}/' \
  --mutation '/for row in listing\.values():/,+1d' \
  -- uv run pytest tests/test_engine_flatten.py -k caches_the_listing_before -q
```

Expected: KILLED. The mutation is a **deletion of the loop**, not the "move it below `read_snapshot`" the block-move wording implied — `--mutation` takes a line-wise sed, which cannot move a block, and deleting the loop reproduces the pre-fix behaviour exactly. The control empties the listing, so nothing is cached and `names.index("cache_instrument")` raises: a real, different defect the probe must detect, not a syntax error that would fail everything. Before trusting either verdict, confirm the `-k` filter collects the test: `uv run pytest tests/test_engine_flatten.py -k caches_the_listing_before --collect-only -q` must report exactly 1.

---

### Task 3: The funding gate fails closed, and announces when it need not

**Files:**
- Modify: `cli/engine/probeplan.py` (`plan_refusals`), `cli/engine/venuestate.py`, `cli/engine/executor.py`, `cli/engine/command.py`
- Test: `tests/test_engine_probeplan.py`, plus the `VenueState(...)` construction sites and the two fake accounts listed in Step 1

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `plan_refusals` accepting the two new inputs.

- [ ] **Step 1: Carry the locked map through `venuestate`, and NOT through the journal**

`venue_state_from_cache` currently keeps only `balances_free()`. Add the sibling map beside it, mirroring that line exactly — `Account.balances_locked()` **does** exist on the installed 2.0.0rc4.dev20260825 (`hasattr(MarginAccount, 'balances_locked')` is True) and returns `dict[Currency, Money]`, so no manual derivation from `AccountBalance.locked` is needed:

```python
    balances_locked = {currency.code: float(money) for currency, money in account.balances_locked().items()}
```

Executed on a constructed `MarginAccount` with a `2.757 EUR` hold, that expression returns `{'EUR': 2.76}` (EUR precision 2 quantizes it) — the same shape and the same quantization as the `balances` line above it.

`VenueState` gains `balances_locked: dict[str, float]` as a **required** field, and **`to_payload()` is left untouched**. That is the decision, not an oversight (spec D2's "Where it runs"): `to_payload()`'s output is the `state` object of every `venue-<HH>.json`, and `validate_venue_record` compares its key set for exact equality against `_STATE_KEYS = {"snapshot_at", "instruments", "positions", "balances"}` — executed, the current shape validates and the same document plus one extra key raises `EngineJournalError: venue record 'state' keys [...] != expected [...]`. Journalling the field would therefore require bumping `VENUE_SCHEMA_VERSION`, giving `_STATE_KEYS` a per-version shape, and updating **three** readers that hardcode `schema_version != 2` — `command._seed_exec_positions`, `command._newest_venue_record`, `executor._newest_venue_balances` — plus a rollback hazard on the live trade path, all bought for an advisory offline report. Not done here.

Because the field is required and the dataclass is frozen, **every construction site must pass it**. There are nine, enumerated so none is discovered by CI:

| file | line | site |
|---|---|---|
| `cli/engine/venuestate.py` | 151 | `venue_state_from_cache`'s return — the only production one |
| `tests/test_engine_venueledger.py` | 15 | record-building helper |
| `tests/test_engine_venuestate.py` | 227 | state helper |
| `tests/test_engine_execledger.py` | 93 | state helper |
| `tests/test_engine_cycle.py` | 167, 230, 256 | three sites |
| `tests/test_engine_executor.py` | 551, 1281 | two sites |

The eight test sites take `balances_locked={}`, which is the fail-closed value: no balance reporting a hold is exactly what the refusal keys on. `to_payload()` is unchanged, so `tests/test_engine_venuestate.py:203` and `tests/test_engine_venueledger.py:50`, which assert on its exact output, keep passing as written — **check that they do rather than assuming it**, since they are the pin on this decision.

The same change also makes `venue_state_from_cache` call a method its fake accounts do not offer. **Both stand-ins must gain `balances_locked()` in the same edit**, or every test that drives the reader dies on `AttributeError` rather than on anything about this guard:

| file | line | stand-in |
|---|---|---|
| `tests/test_engine_venuestate.py` | 92 | `_fake_account`, `SimpleNamespace(balances_free=lambda: balances)` |
| `tests/test_engine_executor.py` | 387-392 | `StubCache.account_for_venue`'s returned namespace, same shape |

Give each a `balances_locked` returning `dict[Currency, Money]` — the real type's own terms, the reason `_fake_account`'s docstring gives for not using plain str/float keys, and what forces the reader to call `.code`/`float()`. Both are pinned by `tests/test_engine_stub_fidelity.py`'s standin table against `nautilus_trader.model.MarginAccount`, which carries `balances_locked` — so the addition is legal there; run that file and confirm rather than assuming.

- [ ] **Step 2: Write the failing tests**

In `tests/test_engine_probeplan.py`, beside the fourteen existing `plan_refusals` tests. The module constant is `NOW` (line 11) — there is no `_NOW`.

```python
def test_plan_refusals_refuses_when_free_cannot_be_trusted():
    """No balance reports a hold while an order rests, so `free` includes money the venue has
    reserved (spec 00111 D2). The gate fails CLOSED rather than sizing against cash it cannot see."""
    reasons = plan_refusals(_margin_plan(), now=NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            balances_locked={"EUR": 0.0}, resting_orders=1)
    assert any("cannot be trusted" in r for r in reasons)


def test_plan_refusals_does_not_refuse_when_nothing_rests():
    """The control: same all-zero locked map, no resting orders, no refusal. Without this a guard
    that always refuses would pass the test above."""
    reasons = plan_refusals(_margin_plan(), now=NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            balances_locked={"EUR": 0.0}, resting_orders=0)
    assert not any("cannot be trusted" in r for r in reasons)


def test_an_empty_locked_map_refuses_like_an_all_zero_one():
    """A read that returned no balances learned nothing about holds, which is the untrustworthy
    input this refusal exists to catch -- not a licence to size against `free`."""
    reasons = plan_refusals(_margin_plan(), now=NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            balances_locked={}, resting_orders=1)
    assert any("cannot be trusted" in r for r in reasons)


def test_a_nonzero_locked_announces_and_stops_refusing(caplog):
    """D3: when the upstream fix lands, `locked` becomes real and the refusal stops firing --
    correct, but silent. Both halves are asserted here, so a guard that announced without releasing
    (or released without announcing) fails."""
    reasons = plan_refusals(_margin_plan(), now=NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            balances_locked={"EUR": 2.757}, resting_orders=1)
    assert not any("cannot be trusted" in r for r in reasons)
    assert any("locked is no longer zero" in r.message for r in caplog.records)


def test_a_non_finite_hold_is_named_and_still_announces_the_real_one(caplog):
    """`nan > 0.0` is False, so a non-finite hold would otherwise read as 'no balance reports a
    hold' and be indistinguishable from a real zero. It is named instead -- and this is the one
    state where the refusal and the announcement are both live, which is why the announcement is
    not the refusal's `else`."""
    reasons = plan_refusals(_margin_plan(), now=NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            balances_locked={"EUR": float("nan"), "USD": 5.0}, resting_orders=1)
    assert any("not finite" in r and "EUR" in r for r in reasons)
    assert any("locked is no longer zero" in r.message for r in caplog.records)


def test_unknown_inputs_neither_refuse_nor_announce(caplog):
    """The offline validator's case: it reads a journalled snapshot carrying neither input, so it
    passes None and the check is NOT EVALUATED -- no refusal it could never clear, and no
    announcement it never observed. `probe-plan --check` prints that it did not run."""
    reasons = plan_refusals(_margin_plan(), now=NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            balances_locked=None, resting_orders=None)
    assert not any("cannot be trusted" in r or "not finite" in r for r in reasons)
    assert not caplog.records
```

- [ ] **Step 3: Run and see them fail for the RIGHT reason**

Run: `uv run pytest tests/test_engine_probeplan.py -k "cannot_be_trusted or nothing_rests or empty_locked_map or nonzero_locked or non_finite_hold or unknown_inputs" -v`
Expected: all six FAIL, and **the failure text must name `balances_locked`/`resting_orders`** — `TypeError: plan_refusals() got an unexpected keyword argument`. A `NameError` or a collection error means the red proves nothing about the signature. Confirm the selection collects exactly six first: same command with `--collect-only -q`.

- [ ] **Step 4: Implement**

Two required keyword-only parameters, **no defaults**: `balances_locked: dict[str, float] | None` and `resting_orders: int | None`. A default would keep the fifteen existing test calls green while leaving any un-threaded production caller silently guardless — the guard present in review and inert in production. Without one, an un-threaded caller is a `TypeError` the suite cannot miss. `None` is the explicit "this caller has no live venue truth" value, and the docstring names its one legitimate user.

`probeplan.py` has no logger today. Add `from cli.logging import get_logger` and `logger = get_logger("engine.probeplan")` — the module docstring's "imports only stdlib, `cli.engine.errors`, and `cli.engine.store.BASKET`" sentence must be amended in the same edit to name it. The constraint it protects is unharmed: `cli.engine.store` already imports `cli.logging` at module level, so this module pays that cost today and the import adds nothing; what the sentence is really guarding is "no nautilus", which still holds.

Extend the docstring's finiteness paragraph to cover the new map, then add, after the margin-floor block:

```python
    # spec 00111 D2/D3 -- the token stays here rather than in the log line, which the
    # operator-visible-vocabulary guard scans.
    if balances_locked is not None and resting_orders is not None:
        non_finite = sorted(code for code, held in balances_locked.items() if not math.isfinite(held))
        if non_finite:
            reasons.append(f"locked balances are not finite: {non_finite}")
        elif resting_orders > 0 and not any(held > 0.0 for held in balances_locked.values()):
            reasons.append(
                f"free_zeur {free_zeur:.2f} cannot be trusted: {resting_orders} order(s) rest while no "
                "balance reports held funds, so free includes cash already committed"
            )
        if any(held > 0.0 for held in balances_locked.values()):
            logger.warning(
                "locked is no longer zero (%r) -- the adapter now reports held funds, so the "
                "untrustworthy-balance refusal no longer fires; re-derive whether the funding gate "
                "still needs it",
                balances_locked,
            )
```

**The log line carries no decision token.** `tests/test_internal_terms_not_operator_visible.py` scans every non-docstring string literal under `cli/` and `\bD\d{1,2}[a-z]?\b` is in its vocabulary — run against the literal, `_leaks(...)` returns `['D2']`. The guard's own failure message says what to do: move the token to the adjacent comment, which is what the comment above does.

Thread both inputs at the two call sites, whose sources differ and are the reason the parameters are nullable:

- **`executor.py`'s `_pickup`** — the live gate. Inside the same `try` that wraps `venue_state_from_cache` (so a read failure keeps its existing "no venue truth" refusal rather than escaping), beside the `free_zeur` line:
  ```python
          resting_orders = len(self._client.cache.orders_open(venue=_VENUE))
  ```
  `orders_open(venue=_VENUE)` is the same Cache surface `executor.py` already reads at its startup-adoption and kill paths. Pass `balances_locked=state.balances_locked, resting_orders=resting_orders`.

  **The count inherits the defect this branch is fixing, and that is worth stating rather than discovering.** The Cache's open-order index is filled by the node's own reconciliation, which reads through the same adapter — so if the node's instrument cache is cold the way `flatten`'s was, `resting_orders` reads 0, D2 never fires, and the guard is present and inert. The evidence that it is not cold is indirect and dated: `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`'s fifth observation records the engine registering **24** `unmatched` external events during the 2026-08-26 probe run, i.e. it saw orders it had not placed. Task 5 takes the direct reading.
- **`command.py`'s `probe_plan`** — the offline `--check` validator. Its record is a journalled `venue-<HH>.json`, whose `state` carries neither holds nor orders, so it passes `balances_locked=None, resting_orders=None` and echoes one line saying so, in the same place it echoes the gate verdict and the snapshot timestamp:
  ```python
      typer.echo("the untrustworthy-balance check needs live venue truth and was not evaluated here")
  ```
  That is honest rather than fail-open: this command "writes nothing anywhere" and its own help calls it "Advisory only -- the engine re-validates every plan live before any order". Making it refuse instead would refuse **every** plan forever, since a journalled record can never supply the inputs.

Then update the **fifteen** existing `plan_refusals` calls in `tests/test_engine_probeplan.py` (lines 329, 337, 344, 350, 356, 364, 371, 378, 390, 397, 404, 412, 418, 424, 431) with `balances_locked={}, resting_orders=0` — the values that preserve each test's existing subject, since no order rests in any of them.

- [ ] **Step 5: Run every suite this task can reach**

Run: `uv run pytest tests/test_engine_probeplan.py tests/test_engine_venuestate.py tests/test_engine_venueledger.py tests/test_engine_executor.py tests/test_engine_cycle.py tests/test_engine_execledger.py tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_engine_node.py -q`
Expected: all pass. The venuestate/venueledger pair is what proves `to_payload()` was left alone; executor/cycle/execledger/command are the `VenueState` construction sites and the threaded call site; stub_fidelity pins the two fake accounts against the real `MarginAccount`; node is the third `venue_state_from_cache` caller.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/probeplan.py cli/engine/venuestate.py cli/engine/executor.py cli/engine/command.py \
        tests/test_engine_probeplan.py tests/test_engine_venuestate.py tests/test_engine_venueledger.py \
        tests/test_engine_executor.py tests/test_engine_cycle.py tests/test_engine_execledger.py \
        tests/test_engine_stub_fidelity.py
git commit -m "fix(probeplan): the margin floor fails closed when free cannot be trusted"
```

Stage every file Step 1 and Step 4 touched — a `git add` short of that leaves the tree dirty, which the next step's `mutate-probe.sh` refuses outright.

- [ ] **Step 7: Mutation-prove the guard**

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/probeplan.py \
  --control 's/cannot be trusted/is fine/' \
  --mutation 's/resting_orders > 0 and //' \
  -- uv run pytest tests/test_engine_probeplan.py -k "cannot_be_trusted or nothing_rests" -q
```

Expected: KILLED. The two operands bite **different** tests, which is the point of running them as a pair: the control renames the refusal string, so `refuses_when_free_cannot_be_trusted` goes red; the mutation drops the resting-orders conjunct — the exact fail-tight defect D2's stated cost buys — so the refusal fires unconditionally and `does_not_refuse_when_nothing_rests` goes red. A mutation killed only by the first test would leave the control test unproven. Confirm the `-k` filter collects exactly 2 with `--collect-only -q` before trusting either verdict.

---

### Task 4: The fixture script

**Files:**
- Create: `infra/scripts/kraken-fixture.sh`
- Modify: `infra/scripts/probe-with-vaulted-key.sh` (a second hardcoded target, for Task 5)
- Modify: `README.md` if it gains an operator-facing entry point

**Interfaces:**
- Consumes: `kraken-cli` 0.4.1 on the workstation.
- Produces: a one-leg mint, an independent verification read, and a rehearsed close, all for Task 5.

- [ ] **Step 1: Write the script**

Header states the constraint verbatim: *workstation development tool; not available in CI; never imported by `cli/`; never a runtime dependency of the engine.*

Behaviour:
- `--validate` **is the default.** Every `kraken order buy`/`kraken order sell` carries `--validate` unless `--execute` is passed. This mirrors `zcrypto-flatten`'s inversion and exercises the real API without submitting.
- `-o json` on every call.
- **`mint` places exactly ONE order** — the margin leg below (spec D5 authorises one executing leg and prices it). The two hand-placed limits are not re-minted: they already rest, they must survive, and a second executing leg is money nothing authorised. The script echoes the count it will submit, and the task's expectation is "exactly 1; any other count is a defect".
  ```
  kraken order buy SOLEUR 0.06 --type market --leverage 2 --cl-ord-id zc-fixture-margin -o json
  ```
  `PAIR` and `VOLUME` are **positional** — `kraken order buy [OPTIONS] <PAIR> <VOLUME>`; there is no `--pair` and no `--volume`, and writing them is a clap parse error before any request leaves.
- **`close` mode**, `--validate` by default like `mint`, carrying the exact netting command so nothing is composed by hand under a rollover clock:
  ```
  kraken order sell SOLEUR 0.06 --type market --leverage 2 --reduce-only --cl-ord-id zc-fixture-close -o json
  ```
  `--reduce-only` is the safety that matters: without it a leveraged sell against no position opens a **short**, which is the failure a wrong close produces. `--type` defaults to `limit`, so stating `market` is required, not decorative.
- **`verify` subcommand** reads `kraken positions`, `kraken extended-balance`, `kraken open-orders`, all `-o json`. **This is the independent witness; it never calls the adapter.**
- `--yes` ("Skip confirmation prompts for destructive operations") exists and is **not** passed: Task 5 is attended, and the operator answering the prompt is the last gate before real money.

- [ ] **Step 2: Exercise all three modes in their default (validate) mode**

```bash
bash infra/scripts/kraken-fixture.sh verify
bash infra/scripts/kraken-fixture.sh mint
bash infra/scripts/kraken-fixture.sh close
```
`verify` is read-only and costs nothing to run now — the spec makes it the witness every D4 assertion rests on, so it must not first execute inside the attended window. `mint` and `close` must be **validated by the venue**, not merely parsed: a `close --validate` that the venue rejects because it will not take `reduce_only` on this pair is a finding to resolve here, not at Task 5.

- [ ] **Step 3: Prove the safety default against what a submitted order actually moves**

`open-orders` cannot see this defect: the leg is `--type market`, and a market order that submits **fills** — it appears in `positions`, never in the open-order list. So capture `kraken positions -o json` and `kraken extended-balance -o json` before and after Step 2's validate-mode runs and assert both are **unchanged**. Then grep the script for `order buy`/`order sell` and check every occurrence is guarded. A script whose dangerous mode is reachable by default is the defect this step exists to catch, and a control that cannot see it is how it ships.

- [ ] **Step 4: Extend the vaulted-key wrapper with a second fixed target**

Task 5 must run **this branch's** flatten against the live account, and the host wrapper cannot do it (Global Constraints). `infra/scripts/probe-with-vaulted-key.sh` already puts exactly the two variables `zcrypto engine flatten` reads — `KRAKEN_SPOT_API_KEY`, `KRAKEN_SPOT_API_SECRET` — into an exec'd child's environment, but its target is hardcoded to the probe harness. Add a second **equally hardcoded** target selected by a fixed flag, preserving the property the header names: *the target is FIXED; arguments are forwarded, none of them selects a program.* Two hardcoded targets, chosen by a flag whose values are a closed set, is still that property; a `--` passthrough would not be.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/kraken-fixture.sh infra/scripts/probe-with-vaulted-key.sh README.md
git commit -m "feat(scripts): a repeatable Kraken fixture mint, validate-by-default"
```

Drop `README.md` from the `git add` if it gained nothing.

---

### Task 5: 🅿️ ATTENDED — mint the position and verify all three paths live

**This task requires the owner.** It places a real, filling order. Everything buildable is already done; this is the single handoff.

- [ ] **Step 1: Pre-flight, immediately before**

Read the Kraken maintenance feed matching on **name OR components**; confirm no REST/WebSocket window is open or imminent. Run `bash infra/scripts/kraken-fixture.sh verify` and confirm the two resting limits (`OZRI5U-U7WGD-OYCOMW`, `OVNLAJ-6PXBH-T4GDXF`) are still there, still 0.06 @ 45.95, and still far below market. **A reading that disagrees stops the branch** — every decision in the spec rests on that fixture, and it has been unattended since 2026-09-01.

- [ ] **Step 2: Open the key's allowlist for this workstation**

The `zcrypto-engine` key is IP-bound and the engine host is currently its only allowlisted host — `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`'s closure section records the removal. Add this workstation's public IP, per `infra/runbooks/order-semantics-verification.md`. **Closing it again is Step 8, not an afterthought.**

- [ ] **Step 3: Owner mints the margin leg**

```bash
bash infra/scripts/kraken-fixture.sh mint --execute
```
Exactly **one** order is submitted. Any other count is a defect, not a surprise to absorb.

- [ ] **Step 4: Confirm the position exists — through `kraken-cli`, NOT the adapter**

```bash
bash infra/scripts/kraken-fixture.sh verify
```
Expected: one open SOL/EUR long, and `hold_trade` still reflecting the resting spot order. **This reading is the control. Without it, a zero from the adapter is ambiguous rather than a finding** — which is exactly how this defect was wrongly retracted once already. The script is used rather than hand-typed reads, because the spec makes this subcommand the witness and a witness nobody runs is not one.

- [ ] **Step 5: Read both paths through the adapter, running THIS branch's code**

**Not through the host wrapper** — it execs the deployed digest, which predates this branch, so it would exercise flatten without Task 2's fix and return the same empty list the defect returns. Run the dry run from this worktree with the vaulted key, through Task 4 Step 4's second target:

```bash
bash infra/scripts/probe-with-vaulted-key.sh <the flatten target flag> -- --state-dir <a scratch dir>
```

No `--execute`. The read shares the trade key with the running engine — the same accepted exposure `zcrypto-flatten`'s own dry-run banner names, and the engine is disarmed. Assert, by identity:

- **orders — as an A/B in this one run.** Both fixture txids **absent** from a cold-cache read and **present** from the warm one. The A/B is the discriminator, and it is also the only proof of the cache mechanism available to anyone working from this repo: the mechanism was read from an upstream Rust tree that the installed wheel does not carry, so nothing here can re-open it.
- **positions: the minted long present, by symbol and side.**
- **The engine's own view of the resting book**, since D2's `resting_orders` is read from the Cache the node's reconciliation fills through this same adapter: confirm the engine counts the fixture orders rather than zero. A guard whose count is structurally 0 is inert, and this is the one moment in the branch where that is observable.
- **No fills leg.** Nothing in `cli/` reads fills — `request_fill_reports` appears in no file under `cli/`, `tests/` or `infra/` — so the named run produces no fill row to assert on, and the committed record holds order txids (four of them `filled_qty=0.0`), not fill identities. Spec D4 records the drop and its reason.

- [ ] **Step 6: Record the row**

Append the verification row to `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`, with the `kraken-cli` readings beside the adapter's, and say plainly that fills were not exercised. **If positions come back empty, that is the finding — stop, and do not ship a fix that cannot see the close path.**

- [ ] **Step 7: Close the minted position, deliberately**

The margin leg accrues rollover.

```bash
bash infra/scripts/kraken-fixture.sh close --execute
```

Confirm closure by symbol and side against `kraken positions -o json`, not by an empty list: an empty list is also what a read failure returns. **Leave the two original resting orders untouched.**

- [ ] **Step 8: Close the key's allowlist**

Remove this workstation's public IP, restoring the engine host as the key's only allowlisted host, and say so in the row appended at Step 6 — the way the 2026-08-26 pass recorded its own closure.

- [ ] **Step 9: Commit**

```bash
git add docs/reference/adapter-verification/2.0.0rc4.dev20260825.md
git commit -m "docs(adapter_verification): the order and position read paths, against a live fixture"
```

---

### Task 6: Closeout

- [ ] **Step 1: Append the iterations-history entry**

Load the `iteration-closeout` skill; append to `docs/iterations-history-phase6.md`. State what was verified live and what was not.

- [ ] **Step 2: Update the topics**

`T0159` gains the cache finding. `T0160` gains spec D7's two upstream deferrals — the silent row-drop report and the `hold_trade` PR — each with its `ripe_when`, because a deferral whose only home is spec prose is untracked and the `hold_trade` fix is the same event D3's assertion exists to detect. Register no **new** topic without the approver's word (`zcrypto-main` holds that call); both of these fold into existing ones.

- [ ] **Step 3: Commit the closeout**

```bash
git add docs/iterations-history-phase6.md docs/open-topics/
# <N> is read from docs/iterations-history-phase6.md at closeout -- it is not knowable now.
git commit -m "docs(closeout): iter-<N> -- 00111's blind reads, fixed and verified live"
```

- [ ] **Step 4: Whole-branch review at the Fable floor, then PR**

Closeout is the branch's END, so it commits **before** the PR opens: re-verify the entry and every status claim against the full branch log, then `infra/scripts/review-trailer-audit.sh develop` must PASS before push, then PR into `develop` via the `open-pr` skill — whose trailer aggregation would otherwise be regenerated after the fact.
