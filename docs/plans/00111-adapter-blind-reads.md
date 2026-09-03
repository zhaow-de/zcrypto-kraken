# 00111 — the adapter's blind reads: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make flatten see what is actually at the venue, and stop the engine's funding gate from reading a free balance that overstates available cash — then prove both against a live fixture rather than a fake that agrees with us.

**Architecture:** Two independent fixes to our own code, both caused by the same nautilus Kraken adapter. Flatten populates the client's instrument cache before it reads (D1). `plan_refusals` gains a fail-closed refusal when the balance is known untrustworthy (D2) plus a loud assertion when that stops being true (D3). A committed `kraken-cli` script mints the fixture (D6), and verification runs against the live account through a non-adapter witness (D4, D5).

**Tech Stack:** Python 3.14, `uv`, pytest. `nautilus_trader` 2.0.0rc4.dev20260825 (pinned). `kraken-cli` 0.4.1 — **workstation only**.

**Spec:** `docs/specs/00111-adapter-blind-reads-design.md`

## Global Constraints

- **`kraken-cli` is never a runtime dependency.** Not imported by `cli/`, not present in CI, not invoked by the engine. It appears only in `infra/scripts/` and in operator prose.
- **A test double that does not model the defect proves nothing.** `FakeClient` currently returns orders regardless of its instrument cache, so a test written against it passes with and without the fix. Task 1 fixes the double *before* Task 2 fixes the code, and Task 1's test is seen RED first.
- **Verification is by identity, never by row count** (spec D4). Fixture txids and symbols, matched against a `kraken-cli` read — never the adapter compared with itself.
- **Nothing in this plan converges a host, pushes Grafana, or arms anything.**
- **The two existing SOL/EUR orders (`OZRI5U-U7WGD-OYCOMW` spot, `OVNLAJ-6PXBH-T4GDXF` 2:1 margin) must survive every task.** They are also G3c's and E1a's fixture. Nothing here cancels them.
- Every commit carries `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>` and **no `Claude-Session:` trailer**. Each code commit is reviewed by a different agent before push, at the **Fable floor** — this touches the live trade path.

## File Structure

| File | Responsibility |
|---|---|
| `tests/test_engine_flatten.py` | `FakeClient` gains instrument-cache semantics; the red test for the blind read |
| `cli/engine/flatten.py` | `read_listing` result is fed to the client's cache before `read_snapshot` reads |
| `cli/engine/probeplan.py` | `plan_refusals` gains the untrustworthy-balance refusal and the `locked > 0` assertion |
| `tests/test_probeplan.py` | Guard tests: refuses while orders rest; asserts loudly when `locked` becomes real |
| `cli/engine/venuestate.py` | Carries `locked` through so the guard can see it |
| `infra/scripts/kraken-fixture.sh` | Mints and verifies the fixture over `kraken-cli`; `--validate` default |
| `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` | Gains the three-path verification row |
| `docs/iterations-history-phase6.md` | The iteration entry (final task) |

---

### Task 1: Make the test double model the defect, and see the test go red

**Files:**
- Modify: `tests/test_engine_flatten.py` (`FakeClient`)
- Test: `tests/test_engine_flatten.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FakeClient` with `cache_instrument(instrument)` and cache-gated order/fill reads, used by Task 2.

- [ ] **Step 1: Teach `FakeClient` the upstream cache semantics**

In `FakeClient.__init__`, add the cache:

```python
        # The real client drops any order whose raw symbol misses `instruments_cache`, silently and
        # with a successful empty return (spec 00111's measured basis). Modelled here because a
        # double that answers regardless of the cache makes the blind-read test pass either way.
        self.cached_symbols: set[str] = set()
```

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
        # The silent drop: no warning, no error, a successful empty list.
        return [r for r in rows if str(getattr(r, "raw_symbol", "")) in self.cached_symbols]
```

- [ ] **Step 2: Write the failing test**

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

- [ ] **Step 3: Run it and confirm BOTH halves behave**

Run: `uv run pytest tests/test_engine_flatten.py -k instrument_cache_is_populated -v`
Expected: **PASS** — this test pins the double's semantics, not the production fix. It must pass now; if the cold half fails, the double is not modelling the drop.

- [ ] **Step 4: Prove the double actually bites**

Temporarily revert the filter in `request_order_status_reports` to `return rows`, re-run, and confirm the cold half FAILS. Restore. **A double that cannot fail is the thing this task exists to prevent.**

- [ ] **Step 5: Commit**

```bash
git add tests/test_engine_flatten.py
git commit -m "test(engine_flatten): the double models the adapter's silent cache-miss drop"
```

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

In `run_flatten`, replace the read sequence:

```python
        listing = await read_listing(client, rec)
        # BEFORE the snapshot, not after: the client drops every order whose raw symbol misses its
        # instrument cache, and `request_instruments` does NOT populate that cache -- only
        # `cache_instrument` does (spec 00111 D1). Reading first returns a silent empty list.
        for row in listing.values():
            client.cache_instrument(row)
        snapshot = await read_snapshot(client, rec)
        plan = await build_plan(client, rec, snapshot, listing)
```

Confirm what `read_listing` returns keys/values of before writing `listing.values()` — if it maps symbol to a dict rather than to the instrument object, cache the instrument row instead.

- [ ] **Step 4: Run the full flatten suite**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: all pass. Several existing tests assert on `client.calls` ordering — update any whose expectations the new call legitimately changes, and **read each one before changing it**: a test that now fails because the sequence genuinely changed is correct to update; one failing because the fix broke it is not.

- [ ] **Step 5: Mutation-prove the guard**

Run: `infra/scripts/mutate-probe.sh` with a mutation that moves the caching loop back below `read_snapshot`. Expected: KILLED.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "fix(engine_flatten): cache the listing before reading, or every order is dropped"
```

---

### Task 3: The funding gate fails closed, and announces when it need not

**Files:**
- Modify: `cli/engine/probeplan.py` (`plan_refusals`), `cli/engine/venuestate.py`
- Test: `tests/test_probeplan.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `plan_refusals` accepting the two new inputs.

- [ ] **Step 1: Carry `locked` through `venuestate`**

`venue_state_from_cache` currently keeps only `balances_free()`. Add a sibling map so the guard can see holds:

`AccountBalance` exposes `.total`, `.free` and `.locked` — **verified against the installed 2.0.0rc4.dev20260825**. There is no confirmed `Account.balances_locked()`, so derive from the balance objects rather than assuming a convenience method:

```python
    balances_locked = {b.currency.code: float(b.locked) for b in account.balances().values()}
```

Confirm `account.balances()` returns a mapping of currency to `AccountBalance` on the pinned version before writing it; if it returns a sequence, iterate directly. Add `balances_locked` to `VenueState` and to its `to_dict`.

- [ ] **Step 2: Write the failing tests**

```python
def test_plan_refusals_refuses_when_free_cannot_be_trusted():
    """locked == 0 while an order rests means `free` includes money the venue has reserved
    (spec 00111 D2). The gate fails CLOSED rather than sizing against cash it cannot see."""
    reasons = plan_refusals(_margin_plan(), now=_NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            locked_zeur=0.0, resting_orders=1)
    assert any("cannot be trusted" in r for r in reasons)


def test_plan_refusals_does_not_refuse_when_nothing_rests():
    """The control: same untrustworthy-looking zero, no resting orders, no refusal. Without this a
    guard that always refuses would pass the test above."""
    reasons = plan_refusals(_margin_plan(), now=_NOW, ledgered=frozenset(),
                            max_plan_notional_eur=100.0, free_zeur=99.52,
                            locked_zeur=0.0, resting_orders=0)
    assert not any("cannot be trusted" in r for r in reasons)


def test_a_nonzero_locked_asserts_loudly(caplog):
    """D3: if the upstream fix lands, `locked` becomes real and this guard stops firing -- correct,
    but silent. The transition must announce itself, because the upstream release cadence is not
    ours to schedule."""
    plan_refusals(_margin_plan(), now=_NOW, ledgered=frozenset(),
                  max_plan_notional_eur=100.0, free_zeur=99.52,
                  locked_zeur=2.757, resting_orders=1)
    assert any("locked is no longer zero" in r.message for r in caplog.records)
```

- [ ] **Step 3: Run and see all three fail**

Run: `uv run pytest tests/test_probeplan.py -k "cannot_be_trusted or nothing_rests or asserts_loudly" -v`
Expected: FAIL — `plan_refusals` does not accept `locked_zeur` or `resting_orders`.

- [ ] **Step 4: Implement**

Add the parameters and the two behaviours to `plan_refusals`:

```python
    if locked_zeur == 0.0 and resting_orders > 0:
        reasons.append(
            f"free_zeur {free_zeur:.2f} cannot be trusted: {resting_orders} order(s) rest while the "
            "venue reports zero held funds, so free includes cash already committed"
        )
    elif locked_zeur > 0.0:
        logger.warning(
            "locked is no longer zero (%.8f) -- the adapter now reports held funds, so 00111 D2's "
            "guard no longer fires; re-derive whether the funding gate still needs it",
            locked_zeur,
        )
```

Thread `locked_zeur` and `resting_orders` through both call sites: `command.py`'s `probe_plan` and `executor.py`'s `_pickup`.

- [ ] **Step 5: Run and confirm green, then mutation-prove**

Run: `uv run pytest tests/test_probeplan.py -q`
Then `infra/scripts/mutate-probe.sh` with the `and resting_orders > 0` clause deleted. Expected: KILLED by the second test.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/probeplan.py cli/engine/venuestate.py tests/test_probeplan.py
git commit -m "fix(probeplan): the margin floor fails closed when free cannot be trusted"
```

---

### Task 4: The fixture script

**Files:**
- Create: `infra/scripts/kraken-fixture.sh`
- Modify: `README.md` if it gains an operator-facing entry point

**Interfaces:**
- Consumes: `kraken-cli` 0.4.1 on the workstation.
- Produces: a repeatable mint + an independent verification read for Task 5.

- [ ] **Step 1: Write the script**

Header states the constraint verbatim: *workstation development tool; not available in CI; never imported by `cli/`; never a runtime dependency of the engine.*

Behaviour:
- `--validate` **is the default.** Every `kraken order buy` carries `--validate` unless `--execute` is passed. This mirrors `zcrypto-flatten`'s inversion and exercises the real API without submitting.
- Each leg carries `--cl-ord-id` — `zc-fixture-margin`, `zc-fixture-spot` — so legs are identified by name, not by matching txids afterwards.
- `-o json` on every call.
- `verify` subcommand reads `kraken positions`, `kraken extended-balance`, `kraken open-orders`, all `-o json`. **This is the independent witness; it never calls the adapter.**
- The margin leg: `kraken order buy --pair SOLEUR --type market --volume 0.06 --leverage 2 --cl-ord-id zc-fixture-margin`.

- [ ] **Step 2: Run it in its default (validate) mode**

Run: `bash infra/scripts/kraken-fixture.sh mint`
Expected: Kraken validates and returns without submitting. **Confirm no order appears**: `kraken open-orders` still shows exactly the two pre-existing orders.

- [ ] **Step 3: Prove the safety default**

Confirm that omitting `--execute` cannot submit: grep the script for `order buy` and check every occurrence is guarded. A script whose dangerous mode is reachable by default is the defect this step exists to catch.

- [ ] **Step 4: Commit**

```bash
git add infra/scripts/kraken-fixture.sh
git commit -m "feat(scripts): a repeatable Kraken fixture mint, validate-by-default"
```

---

### Task 5: 🅿️ ATTENDED — mint the position and verify all three paths live

**This task requires the owner.** It places a real, filling order. Everything buildable is already done; this is the single handoff.

- [ ] **Step 1: Pre-flight, immediately before**

Read the Kraken maintenance feed matching on **name OR components**; confirm no REST/WebSocket window is open or imminent. Re-read SOL/EUR and confirm the two resting limits are still ~46 % below market and unfillable.

- [ ] **Step 2: Owner mints the margin leg**

```bash
bash infra/scripts/kraken-fixture.sh mint --execute
```

- [ ] **Step 3: Confirm the position exists — through `kraken-cli`, NOT the adapter**

```bash
kraken positions -o json
kraken extended-balance -o json
```
Expected: one open SOL/EUR long, and `hold_trade` still reflecting the resting spot order. **This reading is the control. Without it, a zero from the adapter is ambiguous rather than a finding** — which is exactly how this defect was wrongly retracted once already.

- [ ] **Step 4: Read all three paths through the adapter**

Run the flatten dry run through the host wrapper. Assert, by identity:
- orders: both fixture txids present;
- fills: 6 rows against `adapter-verification/2.0.0rc4.dev20260825.md`;
- **positions: the minted long present, by symbol and side.**

- [ ] **Step 5: Record the row**

Append a three-path verification row to `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`, with the `kraken-cli` readings beside the adapter's. **If positions come back empty, that is the finding — stop, and do not ship a fix that cannot see the close path.**

- [ ] **Step 6: Close the minted position, deliberately**

The margin leg accrues rollover. Close it and confirm flat via `kraken positions`. **Leave the two original resting orders untouched** — they are G3c's and E1a's fixture.

- [ ] **Step 7: Commit**

```bash
git add docs/reference/adapter-verification/2.0.0rc4.dev20260825.md
git commit -m "docs(adapter_verification): all three read paths, against a live fixture"
```

---

### Task 6: Closeout

- [ ] **Step 1: Append the iterations-history entry**

Load the `iteration-closeout` skill; append to `docs/iterations-history-phase6.md`. State what was verified live and what was not.

- [ ] **Step 2: Update the topics**

`T0159` gains the cache finding. Register nothing new without the approver's word (`zcrypto-main` holds that call).

- [ ] **Step 3: Whole-branch review at the Fable floor, then PR**

`infra/scripts/review-trailer-audit.sh develop` must PASS before push. PR into `develop` via the `open-pr` skill.

- [ ] **Step 4: Commit**

```bash
git add docs/iterations-history-phase6.md docs/open-topics/
# <N> is read from docs/iterations-history-phase6.md at closeout -- it is not knowable now.
git commit -m "docs(closeout): iter-<N> -- 00111's blind reads, fixed and verified live"
```
