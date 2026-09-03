# 00111 — the adapter's blind reads: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make flatten see what is actually at the venue — under BOTH of the venue's spellings for a pair — and stop the engine's funding gate from reading a free balance that overstates available cash; then prove the first offline, on the legs the live fixture cannot reach, and the second on the live account.

**Architecture:** Two independent fixes to our own code, both caused by the same nautilus Kraken adapter. Flatten populates the client's instrument cache before it reads, caching each pair under its `AssetPairs` key AND, where the two differ, under its altname as a distinct-id twin, with the twin-spelled positions aliased back (D1). `plan_refusals` gains a fail-closed refusal when the balance is known untrustworthy (D2) plus a loud assertion when that stops being true (D3). The cache fix is discriminated **offline** against a loopback venue — cold 0 of 6, listing-only 1 of 6, listing+twins 6 of 6 — which is a committed CI test rather than a live reading (D4). A committed `kraken-cli` script mints the fixture (D6), and the attended window corroborates against the real venue through a non-adapter witness (D4, D5).

**Tech Stack:** Python 3.14, `uv`, pytest. `nautilus_trader` 2.0.0rc4.dev20260825 (pinned). `kraken-cli` 0.4.1 — **workstation only**.

**Spec:** `docs/specs/00111-adapter-blind-reads-design.md`

## Global Constraints

- **`kraken-cli` is never a runtime dependency.** Not imported by `cli/`, not present in CI, not invoked by the engine. It appears only in `infra/scripts/` and in operator prose.
- **A test double that does not model the defect proves nothing.** `FakeClient` currently returns orders regardless of its instrument cache, so a test written against it passes with and without the fix. Task 1 fixes the double *before* Task 2 fixes the code, and the reds that fix produces are read before the production change lands.
- **Identity comes from the non-adapter witness; the adapter contributes a count** (spec D4). `kraken-cli` names the fixture txids and symbols. Flatten prints `N resting order(s) will be cancelled account-wide` and nothing else about orders — `render_plan` echoes no txid, and the dry path returns before `write_journal`, so there is no artifact to read one out of. The adapter's count is therefore never compared with itself: what discriminates is the same count read through **two code versions** (Task 5 Step 5), with the identities supplied by `kraken-cli`.
- **The mechanism is settled OFFLINE, and the live readings corroborate it** (spec D4, and the spec's own offline section). The client's credential check is a string-presence gate, `base_url` redirects its transport to a loopback HTTP server, and `request_instruments()` rebuilds the listing from whatever `AssetPairs` body that server returns — so listing → `cache_instrument` → order/position report runs end to end with no venue, no credential and no host. Task 2 Step 8 is that test, it needs no opt-in variable and no data mount, and CI runs it. **A live count on `SOLEUR` moves 0→2 whether the twins are present or not**, so no live reading in this plan can discriminate the fix; only the offline arms can.
- **Nothing in this plan converges a host, pushes Grafana, or arms anything.** The consequence is load-bearing and easy to miss: `/usr/local/sbin/zcrypto-flatten` execs `{{ engine_image }}@{{ engine_image_digest }}`, the *deployed* pin, so **no run through the host wrapper can contain this branch's code** — the fix is proven from the worktree instead (Task 5 Step 5). The wrapper's dry run is used once, deliberately, as that step's **pre-fix arm**: read-only, no arguments, and never `--execute`.
- **The two existing SOL/EUR orders (`OZRI5U-U7WGD-OYCOMW` spot, `OVNLAJ-6PXBH-T4GDXF` 2:1 margin) must survive every task.** Nothing here cancels them.
- Every commit carries `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>` and **no `Claude-Session:` trailer**. Each code commit is reviewed by a different agent before push, at the **Fable floor** — this touches the live trade path.

## File Structure

| File | Responsibility |
|---|---|
| `tests/test_engine_flatten.py` | `FakeClient` gains instrument-cache semantics; the red test for the blind read; the alias threaded through 33 call sites |
| `cli/engine/flatten.py` | `read_listing` result is fed to the client's cache before `read_snapshot` reads, each row twice where the venue spells the pair two ways; the altname fetch; the twin-spelled position alias |
| `tests/test_engine_flatten_offline_venue.py` | **New.** The three arms against a loopback Kraken with the REAL client — 0 of 6 / 1 of 6 / 6 of 6 — plus the six position branches. No venue, no credential, no data mount; runs in CI |
| `cli/engine/probeplan.py` | `plan_refusals` gains the untrustworthy-balance refusal and the `locked > 0` assertion |
| `tests/test_engine_probeplan.py` | Guard tests: refuses while orders rest; asserts loudly when `locked` becomes real |
| `cli/engine/venuestate.py` | `VenueState` carries `balances_locked` so the guard can see holds — a live field, **not** journalled by `to_payload()` |
| `cli/engine/executor.py`, `cli/engine/command.py` | The two `plan_refusals` call sites, threaded — and `command.py`'s `flatten` docstring is `--help`, which carries the exit-3 clause Task 2 widens |
| `infra/runbooks/engine-procedures.md` | Task 2: the flatten procedure's dry-run paragraph, the exit-code table's row 3 — cause **and** action — and step 5's per-`reason` residual triage list, which the new residual joins. Task 3: the `engine-probe-window` procedure's step 3, which enumerates `probe-plan --check`'s expected output verbatim and so goes stale on the new disclosure line |
| `README.md` | The Usage row for `flatten`, which restates the same exit-3 clause |
| `infra/scripts/kraken-fixture.sh` | Mints, verifies and closes the fixture over `kraken-cli`; `--validate` default |
| `infra/scripts/flatten-with-vaulted-key.sh` | **New**, so Task 5 can run this branch's flatten with the vaulted key. A second entry point rather than a mode on `probe-with-vaulted-key.sh`, and **deliberately not allowlisted** — see Task 4 Step 4 |
| `infra/scripts/kraken-order-semantics-probe.py` | All three balance renders widen to `total`/`locked`/`free` — probes 1, 5 and 6 are the only surfaces that read the exec client's `MARGIN`-typed account from outside the engine, and that is the account D2's signal was never measured on |
| `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` | Gains both live pair spellings per basket leg and the twin count (Task 4 Step 8), and the order + position verification row (Task 5 Step 6) |
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

**The position read is deliberately left ungated, and the reason has changed** (spec D5). The gate is no longer unobserved — the position read shares the cache and **raises** on a miss where the order read drops the row silently — but modelling that in `FakeClient` would force a fixture migration across every positions test in this file and buy nothing, because Task 2 Step 8 exercises that read on the **real client** against a loopback venue, which is the stricter witness. Recorded here so the ungated position read is not later "corrected" into the double.

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
        self._maybe_raise("cache_instrument")
        raw = getattr(instrument, "raw_symbol", None)
        self.cached_symbols.add(str(raw) if raw is not None else str(getattr(instrument, "id", "")))
```

`_maybe_raise` is the double's existing plumbing and it **pops**, so one entry in `raises` fails exactly the FIRST listing row and every later row caches normally. That is what lets Task 2 Step 1 build both arms of the containment from one fixture family: a one-symbol listing makes the single failure the whole listing, and a two-symbol listing makes it one row of two. No new `raises` machinery, and no second `_FAKE_CLIENT_PLUMBING` entry.

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
- **`_Instrument` does NOT currently carry `raw_symbol`** — it sets `self.id = f"{symbol}.KRAKEN"` plus the constraint floats. **Add `self.raw_symbol = symbol.replace("/", "")`** so `_listing("SOL/EUR")` yields a row whose raw symbol is `SOLEUR`. **That reproduces the venue's spelling for the coinciding class only, and one comment line beside it must say so** — `cli/ohlc/fetch.py`'s `PAIR_KEYS` gives a pair key that is not the display symbol with the slash removed for seven of the basket's twelve legs (`BTC/EUR` is `XXBTZEUR`), so a double keyed this way models `SOLEUR` faithfully and can never model a legacy-pair miss:

```python
        # The coinciding spelling class only: Kraken's pair key is `XXBTZEUR` for BTC/EUR, not
        # `BTCEUR` (`cli/ohlc/fetch.py`'s PAIR_KEYS). Nothing in THIS file drives a legacy-coded
        # row -- the spelling that differs is exercised in `test_engine_flatten_offline_venue.py`,
        # on the real client against a loopback venue, which is where it belongs.
        self.raw_symbol = symbol.replace("/", "")
```

**Do not teach the double the second spelling, and do not give it an `altname`.** The real `CurrencyPair` carries none — its `info` is `{}` (measured) — so an `altname` attribute here would be a name the library type lacks, which is a red under this file's own fidelity guard AND a model of a world that does not exist. The altname reaches production from the public `AssetPairs` endpoint (Task 2 Step 3), and every test in this file supplies it through `run_flatten`'s injected reader, so the fixtures in this file are all coinciding-spelling ones by construction and mint no twins. The legacy-pair miss — the whole subject of the twin — is measured on real listing rows in Task 2 Step 8.

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

### Task 2: Flatten populates the cache before it reads — under both of the venue's spellings

**Files:**
- Modify: `cli/engine/flatten.py` (`read_altnames`, `_twin`, `read_positions`, `read_snapshot`, `sweep`, `run_flatten`), `cli/engine/command.py` (the `flatten` docstring, which is `--help`), `infra/runbooks/engine-procedures.md`, `README.md`
- Test: `tests/test_engine_flatten.py`, and the new `tests/test_engine_flatten_offline_venue.py`

**Interfaces:**
- Consumes: Task 1's `FakeClient.cache_instrument`.
- Produces: `read_listing` runs before `read_snapshot`; every row is cached, and every row whose altname differs from its `AssetPairs` key is cached a second time as a distinct-id twin; a twin-spelled position is resolved back to its real pair.

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

Two more, for the containment's two ends. Without them the `except Exception` is a fail-open nothing tests: a contained row is invisible to every later read, and the run's own verdict is computed from one of those reads.

```python
def test_a_listing_nothing_can_be_cached_refuses_before_the_first_write(tmp_path):
    """Every row failing is not a contained row -- it is the pre-fix blind state, in which the
    order read comes back a silent empty list and the run judges itself flat on it. Refused at
    exit 3, which is the code for a read that could not be prepared BEFORE the cancel."""
    _armed(tmp_path)
    client = _client_with(orders=[SimpleNamespace(raw_symbol="SOLEUR")], symbols=("SOL/EUR",))
    client.raises["cache_instrument"] = RuntimeError("no")

    assert _run(client, tmp_path) == 3
    assert not client.submitted
    assert "cancel_all_orders" not in [c[0] for c in client.calls]


def test_a_partly_uncacheable_listing_cannot_read_flat(tmp_path):
    """The direction the per-row containment omits. One row of two fails, so an order on it is
    invisible to `read_open_orders`, `judge_final` sees no order residual and `exit_code` would
    return 0 -- printing that the account reads flat over exposure nothing looked at. The uncached
    row reaches the verdict instead, and the journal names it."""
    _armed(tmp_path)
    client = _client_with(symbols=("SOL/EUR", "BTC/EUR"))
    client.raises["cache_instrument"] = RuntimeError("no")

    assert _run(client, tmp_path) == 2

    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    assert doc["uncached"] == ["SOL/EUR: no"]
    assert any(row["kind"] == "cache" for row in doc["residuals"])
```

`(path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))` is this file's own idiom for reading the one journal a run wrote — used at eleven sites already (the file has seventeen `glob("flatten-*.json")` calls; the other six are `len(list(...)) == …`, `assert list(...) == []` and `journals = list(...)`), including `test_the_residuals_are_judged_against_the_final_snapshot_and_never_the_pre_sweep_one`. Add no helper for it. The second test's account is otherwise **empty**, which is deliberate: exit 2 there can only come from the cache residual, so a degenerate fixture cannot pass it.

**`_armed(tmp_path)` is the first line of both, and `execute` stays at its default.** These two are execute-mode tests — the whole-listing arm must show a refusal that precedes the cancel, and the partial arm must leave a journal, which `_dry_exit` never writes. In execute mode `run_flatten` reaches `check_kill_file(state_dir)` before any client call; with no kill file that raises `FlattenRefused` and the run returns **1** having called nothing, so both tests would read 1 before and after Step 3 and neither would touch the code under test. `_armed` is what every other execute-mode `_run` site in the file calls first. Do **not** reach for `execute=False` instead when a red does not match: a dry run calls neither `cancel_all_orders` nor `submit_order` under any implementation, so the first test's two corroborating assertions would become assertions nothing can fail.

**The altname source is INJECTED, not monkeypatched, and that decision is what keeps the network out of this file.** Step 3 makes `run_flatten` fetch Kraken's public `AssetPairs` for the altname map (spec D1). `run_flatten` already injects every other outside read the same way — `venue_reader`, `tty_available`, `prompt`, `echo` — so it gains `altnames_reader: Callable[[], dict[str, str]] = read_altnames` beside them, and the `_run` helper gains one keyword, `altnames_reader=_no_altnames`, where `_no_altnames` is a module-level `def _no_altnames(): return {}` beside `_online`. One keyword, not two: a test that wants a map or a raise passes its own reader, the same way `_run` already takes `venue=_offline`. **Without that the roughly thirty `run_flatten`-driving tests in this file would each make a real HTTPS request to `api.kraken.com`**, which is a network-gated suite created by accident — exactly what `CLAUDE.md` forbids. Every fixture in this file is a coinciding-spelling one, so `{}` is the truthful default and no test here mints a twin.

Two more in this file, both about the map's own reader and its failure, neither needing a client:

```python
def test_read_altnames_returns_only_the_pairs_the_venue_spells_two_ways(monkeypatch):
    """The map is `AssetPairs` key -> altname for the rows where the two DIFFER, because a row that
    spells them the same needs no twin and a twin minted for it would be a second cache entry under
    an identity nothing at the venue uses. `SOLEUR` is the control: present in the body, absent from
    the map."""
    monkeypatch.setattr(
        flatten,
        "fetch_public",
        lambda method: {"XXBTZEUR": {"altname": "XBTEUR"}, "SOLEUR": {"altname": "SOLEUR"}},
    )
    assert flatten.read_altnames() == {"XXBTZEUR": "XBTEUR"}


def test_a_failed_altname_fetch_cannot_read_flat(tmp_path):
    """Spec 00111 D1's visible degradation. The reader raises, so no twin is minted and every order
    on a legacy-coded pair stays invisible to this run -- which must not print the same verdict as a
    run that could see them. The account is otherwise EMPTY, so exit 2 here can come from nothing
    but the altname residual and a degenerate fixture cannot pass it."""
    _armed(tmp_path)
    client = _client_with(symbols=("SOL/EUR",))

    def _boom():
        raise RuntimeError("no")

    assert _run(client, tmp_path, altnames_reader=_boom) == 2

    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    assert doc["altnames"]["error"] == "no"
    assert any(row["reason"] == "altnames_unavailable" for row in doc["residuals"])
```

`_no_altnames` is a plain `def` beside `_online` and `_offline`, matching the shape those two already have. It adds nothing for `tests/test_engine_stub_fidelity.py` to classify: that walk takes top-level non-test functions only when they build a `SimpleNamespace`, and this one returns a dict.

**And the twin and the alias are NOT tested in this file** (spec D5's re-tensed note): the double's `_Instrument` has no `to_dict`, the real `CurrencyPair` does, and the twin is built from that — so a twin test here would be a test of a fixture nobody ships. Step 8's loopback file carries them, on the real client.

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_engine_flatten.py -k "caches_the_listing_before or nothing_can_be_cached or partly_uncacheable or read_altnames_returns_only or failed_altname_fetch" -v`
Expected: all five FAIL. `caches_the_listing_before` on `names.index` raising `ValueError` — `cache_instrument` is never called. `read_altnames_returns_only` on an `AttributeError` naming `fetch_public`, raised by `monkeypatch.setattr` before the body ever calls `read_altnames` — `setattr` refuses a name the target does not already carry, so the red names the import Step 3 adds rather than the function it adds, and a red naming `read_altnames` instead means the import landed and the function did not. The other three on the **exit code**, which is 0 all three times: the kill file is in place (`_armed`) and the confirmation matches, so the run completes over an account nothing raised on, and neither the refusal nor either residual exists. **A red reading exit 1 means the `_armed` line was dropped**, not that the fix is missing; a red reading `TypeError: run_flatten() got an unexpected keyword argument 'altnames_reader'` on the last one means the helper was threaded and the parameter was not. **Read which assertion fired**: a red on the journal glob unpacking, or a `KeyError` for `uncached` / `altnames`, is also what a half-implementation shows, and only the exit-code line separates the two. Confirm the selection collects exactly 5 first: same command with `--collect-only -q`.

- [ ] **Step 3: Implement**

Three module-level additions come first, because the loop below uses all three.

```python
from cli.snapshot.fetch import fetch_public


def read_altnames() -> dict[str, str]:
    """Kraken's OTHER spelling for every pair that has one: `AssetPairs` key -> `altname`, for the
    rows where the two differ.

    Not a new failure domain and not a new dependency: this is the SAME endpoint `read_listing`'s
    `request_instruments()` already calls, unauthenticated, and `cli.snapshot.fetch` is stdlib
    `urllib` throughout. Rows that spell the two alike are dropped here rather than filtered later,
    so `{}` means "no pair needs a twin" and never "the map was not read" -- the caller separates
    those by whether this raised.

    Synchronous inside an async caller, deliberately: it blocks the loop for at most
    `fetch_public`'s own timeout, nothing else is pending on that loop at this point (the listing
    read has returned, the snapshot read has not started), and wrapping it in a thread would buy
    concurrency nothing is waiting for.
    """
    return {
        key: row["altname"]
        for key, row in fetch_public("AssetPairs").items()
        if isinstance(row, dict) and row.get("altname") and row["altname"] != key
    }


def _twin(row: Any, altname: str) -> Any:
    """The same listing row under the venue's other spelling, with its OWN instrument id.

    A distinct id is mandatory, not stylistic: the client's cache is keyed on the instrument id and
    scanned by `raw_symbol`, so a twin that reused `row.id` would REPLACE the real entry and the
    key spelling would then miss the cache altogether -- measured, 100/100, in both caching orders
    (spec 00111 D1). `to_dict`/`from_dict` rather than a field-by-field rebuild: the field list is
    the library's to change, and a rebuild that missed one would ship a twin whose constraints
    differ from the row it was made from.
    """
    payload = row.to_dict()
    payload["id"] = f"{altname}.KRAKEN"
    payload["raw_symbol"] = altname
    return type(row).from_dict(payload)
```

And the loop itself, as a module-level function beside the other reads rather than inline in `run_flatten` — the shape every other stage of the button already has (`read_listing`, `read_snapshot`, `build_plan`, `judge_final`, `sweep` are all module-level and composed by `run_flatten`). It is not an abstraction for its own sake: it is what lets the twin and the alias be driven by a test **against the real client** without a state directory, a venue stub and a confirmation gate, which is Step 8's whole method.

```python
def prime_cache(client: Any, listing: dict[str, Any], altnames: dict[str, str]) -> tuple[list[str], dict[str, str], int]:
    """Cache every listing row -- and every row the venue ALSO spells another way a second time, as
    a twin under that other spelling. Returns what this run will be blind to, the map from a twin's
    symbol back to the real pair, and how many rows were cached under their own spelling.

    The third value is what the caller's whole-listing refusal keys on, and a length comparison is
    NOT a substitute for it: a row whose own caching succeeded and whose TWIN failed also lands in
    the blind list, so `len(blind) == len(listing)` can be reached on a fully cached listing and
    would refuse a healthy button.

    Called BEFORE the snapshot, never after: the client drops every order whose raw symbol misses
    its instrument cache, and `request_instruments` does NOT populate that cache -- only
    `cache_instrument` does (spec 00111 D1). Reading first returns a silent empty list.

    The twin is what makes the fix reach the legacy-coded pairs: the cache is scanned by the
    listing row's `raw_symbol`, which is Kraken's `AssetPairs` KEY, while an open order is looked
    up by its own `descr.pair`, which is the ALTNAME. Caching keys alone returns 1 of 6 measured on
    six such legs; keys plus twins returns 6 of 6.

    One bad row is CONTAINED and reported, never refused: `constraints_for` states that rule for
    this same ~1600-row listing, and refusing the whole button over one unrelated row would exit 3
    having cancelled nothing. Containment is not silence -- an uncached row is invisible to every
    read after it, so the caller journals it, says it, and counts it as a residual.
    """
    uncached: list[str] = []
    aliases: dict[str, str] = {}
    cached = 0
    for symbol, row in listing.items():
        try:
            client.cache_instrument(row)
        except Exception as exc:  # noqa: BLE001
            uncached.append(f"{symbol}: {exc}")
            continue
        cached += 1
        altname = altnames.get(str(getattr(row, "raw_symbol", "")))
        if altname is None:
            continue
        try:
            client.cache_instrument(_twin(row, altname))
        except Exception as exc:  # noqa: BLE001
            # Contained per row like an uncacheable one, and for the same reason: it costs one
            # pair's visibility under one of its two spellings, not the button.
            uncached.append(f"{symbol} as {altname}: {exc}")
            continue
        aliases[altname] = symbol
    return uncached, aliases, cached
```

Then in `run_flatten`, the three lines inside the `try` currently read `snapshot` first. Replace them with:

```python
        listing = await read_listing(client, rec)
        try:
            altnames = altnames_reader()
            altname_failure = None
        except Exception as exc:  # noqa: BLE001
            # Degraded, never refused: this is a second read of the endpoint that answered
            # `read_listing` a moment ago, and caching the keys alone still beats the blind state.
            # It reaches the verdict below, so the run cannot call itself flat over the pairs it
            # could not see.
            altnames, altname_failure = {}, str(exc)
        record["altnames"] = {"count": len(altnames), "error": altname_failure}
        # `aliases` maps a twin's symbol back to the real pair. An order report's identity is read
        # nowhere in this module, but a POSITION's is -- `_symbol_of` would yield `XBTEUR`, which
        # the listing does not carry, and `margin_legs` would size no closer for a leveraged leg.
        uncached, aliases, cached = prime_cache(client, listing, altnames)
        record["uncached"] = uncached
        if not cached:
            # Not a contained row: nothing cached IS the pre-fix blind state, in which every order
            # read below comes back a silent empty list and the run judges itself flat on it. This
            # is still before the first write, where aborting costs nothing. `read_listing` raises
            # on an empty listing, so this is never the vacuous truth about an empty one -- and it
            # counts rows CACHED rather than comparing lengths, because a row whose twin alone
            # failed is in `uncached` too and a length test would refuse a healthy listing.
            raise FlattenUnreachable(
                f"not one of the {len(listing)} listing rows could be cached, so every order and position "
                f"read after this would come back silently empty: {uncached[0]}"
            )
        if uncached:
            # One line, not one per row: 1600 warnings would bury the plan the operator reads. Said
            # as well as logged, because a dry run writes no journal (`_dry_exit`) and the terminal
            # is its whole record.
            message = (
                f"{len(uncached)} of {len(listing)} listing rows are not cached under every spelling the venue "
                f"uses -- any order or position on them stays invisible to this run: {'; '.join(uncached[:5])}"
            )
            logger.warning("%s", message)
            say(message)
        if altname_failure is not None:
            message = (
                "the venue's list of alternate pair names could not be read, so any order or position on a "
                f"pair the venue spells two ways stays invisible to this run: {altname_failure}"
            )
            logger.warning("%s", message)
            say(message)
        snapshot = await read_snapshot(client, rec, aliases)
        plan = await build_plan(client, rec, snapshot, listing)
```

and, immediately after `residuals = judge_final(...)` further down `run_flatten`, the half that reaches the verdict:

```python
    if uncached:
        # A row nothing could cache is a row this run could not SEE, so the account cannot be
        # called flat on a snapshot that excludes it. A new input to `exit_code`'s existing rule
        # (any residual -> 2); the rule, the write sequence and the confirmation gate are spec
        # 00106's and are untouched.
        residuals.append({"kind": "cache", "count": len(uncached), "reason": "uncached_listing_rows"})
    if altname_failure is not None:
        # Same rule, same reason, different blind set: without the map no twin was minted, so every
        # pair the venue spells two ways read as empty. A flat verdict here would be the one this
        # spec exists to stop -- the account reads flat over exposure nothing looked at.
        residuals.append({"kind": "cache", "reason": "altnames_unavailable", "error": altname_failure})
```

`read_listing` is `-> dict[str, Any]` and builds `listing[symbol] = row` where `row` is what `request_instruments()` returned, so the values are the instrument objects the cache wants and the keys are the symbols the warning names; `cache_instrument` is synchronous on the real client and is correctly called un-awaited (Step 4 pins that shape). `logger` and `say` both already exist at that point — `logger` at module level in `flatten.py`, `say` assigned at the top of `run_flatten`. `uncached`, `aliases`, `cached` and `altname_failure` are assigned inside the `try` and read at the residual lines outside it; Python function scope keeps them live, and the only path that skips the assignments is the `except FlattenUnreachable` one, which returns.

**Then thread the alias, which is a required parameter at every site and not a defaulted one.** A default would let a missed site keep the pre-twin behaviour — a position under the altname yielding `pair_not_listed` and **no closer** — which type-checks, ships green and is a fail-open on the close path; without one it is a `TypeError` no run can miss. Three signatures gain `aliases: dict[str, str]`: `read_positions(client, rec, aliases)`, `read_snapshot(client, rec, aliases)`, and `sweep(client, rec, plan, listing, *, stamp, aliases)` (keyword-only, beside `stamp`). `read_positions` applies it at the one line that builds the row, leaving everything downstream exactly as it is today:

```python
        symbol = _symbol_of(instrument_id)
        # A twin-spelled position carries the twin's id, so this yields `XBTEUR` where the listing
        # is keyed `BTC/EUR` -- `margin_legs` would size no closer for it and `judge_final` would
        # book it `pair_not_listed` at exit 2, a red button reporting a leveraged position instead
        # of closing it (spec 00111 D1). An empty map, and a key spelling under a full one, both
        # leave this line as it was.
        out.append(PositionRow(symbol=aliases.get(symbol, symbol), instrument_id=instrument_id, side=side, quantity=qty))
```

`instrument_id` deliberately keeps the twin's value: nothing downstream reads it — `constraints_for` takes the id from the LISTING row, and `_snapshot_payload` journals symbol, side and quantity only — so rewriting it would be a second edit nothing can observe.

**The call sites, enumerated so none is discovered by CI.** Six in production, all in `cli/engine/flatten.py`: `read_positions` at `read_snapshot`'s `positions=` line and twice inside `sweep` (the `margin_legs` line and the `_read_for_the_record` lambda); `read_snapshot` inside `sweep` and in `run_flatten`; `sweep` in `run_flatten`. **Thirty-three in `tests/test_engine_flatten.py`, and no other test file calls any of the three** (`grep -rn "read_positions(\|read_snapshot(\|sweep(" tests/` returns this file plus four unrelated `*_the_sweep` test names and one local helper): `flatten.read_positions(` ×4, `flatten.read_snapshot(` ×14, `flatten.sweep(` ×15. Every one takes `{}` — no fixture in that file mints a twin, so `{}` is the truthful value and not a placeholder. Count the three greps again after the edit and expect the same 4/14/15; a number that moved means a site was rewritten rather than threaded.

**Why the containment is per row AND still reaches the verdict — both directions, because the omitted one was this loop's blast radius.** An uncacheable row loses only its own orders, which is the pre-fix status quo for that row, while the button still works for everything else; a whole-listing refusal on one bad row would exit 3 having cancelled nothing. But invisibility is not free: `read_open_orders`'s own docstring says the LIST decides the exit code, `judge_final` adds an order residual only `if final.orders:`, and `exit_code` returns 0 on empty residuals — so a blind row that is silently contained lets the run print *"the account reads flat"* over live exposure. The `constraints_for` precedent the comment cites is not analogous either, and reading it as one is how the omission happens: its containment lands **inside** the verdict as an `unjudgeable:` residual, i.e. fails closed. So the containment here is made to do the same — the journal names the rows, the operator is told, and the run cannot be called flat. And the systematic case (a wrong object shape makes all ~1600 rows raise identically) is separated out and refused before the first write, because it is the pre-fix state and not a contained row.

Enumerated so it is not re-derived: this loop is the **only** place in the branch that touches the whole listing, so the family of whole-listing guards this plan could get wrong has exactly one member.

**Then land the contract edits the code above makes owed, in this same step.** All are prose the operator meets and the code does not check, so nothing turns red if they are skipped.

*Exit 3 gains a cause that is not the venue.* Today every surface pins the cause on the venue, spelled "the venue could not be reached or read" or just "the venue could not be read", and an operator who reads that during an incident goes and checks `status.kraken.com` while the venue is healthy and our own cache writer is not. Widen each to say the account could not be **read** before anything was sent — the venue unreachable, **or** the reads not preparable — and let the run's own message say which. Keep the semantic and change nothing else in the sentence; the exit-code RULE is spec `00106`'s and is untouched. **Family, six surfaces, enumerated by the CLAIM and not by one phrase — `grep -rnE "could not be reached or read|could not be read before|venue could not be read" cli/ infra/ README.md` returns exactly these six and nothing else** (the third alternative is the one that matters: a grep on the first two returns five and silently drops the dry-run paragraph, which spells the cause in neither. Widening the same clause under `docs/` is Task 6's, and spec `00106` and the phase-6 changelog are point-in-time records that keep their wording):

| surface | what it is |
|---|---|
| `cli/engine/flatten.py`, `FlattenUnreachable`'s class docstring | the in-code contract the new raise reuses |
| `cli/engine/flatten.py`, `run_flatten`'s docstring | the same sentence on the function that returns the code |
| `cli/engine/command.py`, the `flatten` command's docstring | **`zcrypto engine flatten --help`** — the only exit-code map an operator reaches without the repo |
| `infra/runbooks/engine-procedures.md`, the dry-run paragraph in step 1 of the flatten procedure | the paragraph directly under the `sudo zcrypto-flatten` of step 1 — the command the operator runs **first** — and a dry run is a path the whole-listing refusal reaches: `run_flatten`'s `except FlattenUnreachable` returns `_dry_exit(3, str(exc), say)` |
| `infra/runbooks/engine-procedures.md`, the exit-code table's row 3 | what the incident runbook says to do |
| `README.md`, the `flatten` Usage row | the same clause again (`readme-usage.md` requires it in this change) |

*Exit 3's ACTION column, which widening its cause alone leaves wrong.* `grep -n '\*\*3\*\*' infra/runbooks/engine-procedures.md` returns one line, so exit 3 has exactly one triage home in the runbook: the **action** cell of the exit-code table row the widening above already opens, reading "nothing was sent; the account is as it was". Under a venue outage the action it implies (wait, run it again) works; under the new cause it does not, because a re-run against an unchanged cache writer reproduces the refusal and the operator retries a dead emergency exit. The cell gains what is owed instead: when the message says no listing row could be cached, this run saw nothing at the venue and a re-run will not either — cancel and close by hand on Kraken's own pages. **Deliberately not the exit-2 bullet's wording**: there the record's `uncached` list names which pairs were blind, here nothing was read at all and the whole account is what has to be checked. **Family: one member** — the grep above is the whole enumeration; unlike exit 2 there is no step-5 equivalent for exit 3.

*Exit 2 gains TWO residual `reason`s the runbook's triage list does not carry.* Step 5 of `infra/runbooks/engine-procedures.md` is an exhaustive per-`reason` list, and its nearest neighbours (`resting_order`, `sellable_balance`, `unjudgeable: …`) all end in "run it again" — which against an unchanged cause reproduces the same residual. Add a bullet for **`uncached_listing_rows`**: the symbols are in the record's `uncached` list, and each named pair is hand-checked on Kraken's own pages, because this run could not see it. And a bullet for **`altnames_unavailable`**, whose owed action is different and must not be collapsed into the first: nothing names WHICH pairs were blind, because the map that would have named them is what failed — so the check is every pair the venue spells two ways, which on today's account means every legacy-coded pair, hand-checked on Kraken's own pages. Both say a re-run is worth one attempt (the fetch may have been transient) and that a second identical residual means the pairs are checked by hand, not that the button is retried again. **Family: one member** — `grep -rn "unjudgeable" cli/ infra/` returns that list and the balance raise in `flatten.py` and nothing else, so the per-`reason` triage list has exactly one home, and both bullets land in it.

`.claude/rules/operator-facing-text.md` applies to every surface in the table above, to the exit-3 action cell and to the new bullet: no decision token in the text, the citation on the adjacent comment where one is wanted.

- [ ] **Step 4: Pin the eighth real-client call, and re-tense the seven-call table**

Step 3 makes `cache_instrument` the **eighth** call the red button makes on the real client, and the only one with no pin on its shape. `_real_calls` is a hardcoded table of the other seven and nothing joins it to what `flatten.py` actually calls, so an eighth added to production turns no test red. The offline suite cannot see it either — `FakeClient.cache_instrument` is a plain `def`, so the double models the shape rather than measuring it. **What that leaves live:** if a version bump makes the real `cache_instrument` awaitable-returning, the un-awaited call **returns** instead of raising, Step 3's `except Exception` never fires, `uncached` stays empty, the cache is never populated, and the whole branch silently reverts to the empty order list it exists to fix — with a green suite.

Family, three members, all in `tests/test_engine_flatten.py`:

1. **The sibling pin**, beside `test_every_client_call_the_red_button_makes_needs_a_running_loop`, asserting the **opposite** shape to that one. It must NOT be added to `_real_calls`, whose assertion is the inverse.

```python
def test_the_instrument_cache_writer_answers_without_a_loop():
    """The eighth call the button makes, and the one the seven-call pin above must not hold: it is
    written un-awaited in `run_flatten`, so its answer must be the value and not a `Future`.
    `inspect.iscoroutinefunction` is False for it exactly as it is for the seven, so the shape is
    measured by CALLING -- and by calling with a REAL instrument, because a bare `object()` is
    rejected during argument conversion before either shape can differ."""
    import inspect

    client = _real_client()
    answer = client.cache_instrument(_a_real_currency_pair())  # a raise here is the failure
    assert not inspect.isawaitable(answer), f"cache_instrument answered {type(answer).__name__}, not the value"
```

`_a_real_currency_pair()` builds the library type `_nautilus_standins` already registers `_Instrument` against. **`nautilus_trader.test_kit` does not exist in this wheel** and `nautilus_trader.model.currencies` does not either, so the provider shortcut is not available and every field is passed explicitly — measured, this exact construction is accepted and `cache_instrument` on it returns `None`:

```python
def _a_real_currency_pair():
    from decimal import Decimal

    from nautilus_trader.model import Currency, CurrencyPair, InstrumentId, Price, Quantity, Symbol, Venue

    eur, btc = Currency.from_str("EUR"), Currency.from_str("BTC")
    return CurrencyPair(
        instrument_id=InstrumentId(Symbol("BTC/EUR"), Venue("KRAKEN")),
        raw_symbol=Symbol("XXBTZEUR"),
        base_currency=btc,
        quote_currency=eur,
        price_precision=1,
        size_precision=8,
        price_increment=Price(0.1, 1),
        size_increment=Quantity(0.00000001, 8),
        margin_init=Decimal(0),
        margin_maint=Decimal(0),
        maker_fee=Decimal(0),
        taker_fee=Decimal(0),
        ts_event=0,
        ts_init=0,
    )
```

Measured on the pinned version, with this construction verbatim: the call returns `None`, `isawaitable(None)` is False, and `inspect.iscoroutinefunction(client.cache_instrument)` is False — the same False the seven give, which is why the pin calls rather than introspects. **`raw_symbol` is inert to THIS pin, whose assertion is about the answer's KIND** — `cache_instrument` accepts any `Symbol`, and it accepts a `raw_symbol` that matches nothing at the venue (`TOTALLY-GARBAGE-NOT-A-PAIR` against `id=BTC/EUR.KRAKEN` is cached without complaint, measured). It is **not** inert to the twin pin below, which reads it on both sides. `XXBTZEUR` is what the adapter's own listing rows carry for `BTC/EUR` — measured on the real listing, and the same value `cli/ohlc/fetch.py`'s `PAIR_KEYS` and `docs/reference/kraken-snapshot-register.md` record — so this helper builds a row shaped like a real one, and the twin test below turns it into `XBTEUR`.

**Prove the pin bites before recording it as proof.** The differ-fixture is on the same compiled class: put `client.request_instruments()` in place of the `cache_instrument` line and the test must fail with `RuntimeError: no running event loop` — measured, it does. That is the shape the pin exists to reject, and a pin that accepted it would accept the defect.

2. **The twin's construction, pinned on the library type rather than on our copy of its field list.** `_twin` is `to_dict` → override `id` and `raw_symbol` → `from_dict`, and if a version bump drops either method or stops round-tripping an overridden id, every twin raises, every twin is contained, and the branch degrades to 1-of-6 — visibly (exit 2 with a residual) but for a reason nothing else in the suite would name. Measured on the pinned wheel, verbatim: `to_dict()` returns 25 keys including `id` and `raw_symbol`; `from_dict` on that dict with both overridden yields a `CurrencyPair` whose `id` is `XBTEUR.KRAKEN` and whose `raw_symbol` is `XBTEUR`, whose `price_increment`, `size_increment`, `base_currency`, `quote_currency` and `min_quantity` all equal the source row's, and the source row is unchanged.

```python
def test_the_twin_is_the_same_instrument_under_the_other_spelling():
    """`_twin` builds the second cache entry the venue's second spelling needs. Both halves are
    asserted: the twin's identity is its OWN (a shared id would REPLACE the real entry in a cache
    keyed on the id, which is the whole reason the twin carries one), and its constraints are the
    source row's (a twin sized differently from the pair it stands for would send a wrong closer)."""
    real = _a_real_currency_pair()
    twin = flatten._twin(real, "XBTEUR")

    assert (str(twin.id), str(twin.raw_symbol)) == ("XBTEUR.KRAKEN", "XBTEUR")
    assert (str(real.id), str(real.raw_symbol)) == ("BTC/EUR.KRAKEN", "XXBTZEUR")
    assert (twin.price_increment, twin.size_increment) == (real.price_increment, real.size_increment)
    assert (twin.base_currency, twin.quote_currency) == (real.base_currency, real.quote_currency)
```

3. **`_real_calls`'s docstring**, which Step 3 makes false. It opens `"""The seven calls `cli/engine/flatten.py` makes` — after Step 3 the button makes eight. Re-tense it to say the seven **async** calls, and that `cache_instrument` is the eighth, deliberately absent here because this table's assertion is the inverse of the one that pins it. **`fetch_public` is not a ninth**: it is not a call on this client and reaches no adapter surface, which is why it is injected into `run_flatten` rather than pinned here.

- [ ] **Step 5: Run the full flatten suite**

Run: `uv run pytest tests/test_engine_flatten.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py -q`
Expected: all pass — including Task 1 Step 4's two known reds, which this fix is what turns green. Several existing tests assert on `client.calls` ordering — update any whose expectations the new call legitimately changes, and **read each one before changing it**: a test that now fails because the sequence genuinely changed is correct to update; one failing because the fix broke it is not. The two guard files are why *part* of the `--help`, README and runbook prose is run rather than eyeballed — and which part is the point, because a green run is not a clean bill for the rest. Step 3 writes prose on six operator surfaces plus the fenced comments. `test_internal_terms_not_operator_visible.py` reaches exactly **two** of the six for the decision vocabulary: the `--help` map, through `test_rendered_cli_help_carries_no_internal_vocabulary`'s rendered Typer output, and the README row. It reaches neither `flatten.py` docstring (`_non_docstring_literals` drops docstrings by AST) nor either runbook row (`SCANNED_PACKAGES` is `cli/` and `infra/scripts/`, and no glob in that file carries `infra/`'s `*.md`) — **those four are eyeballed**. It does cover one thing the table does not list: Step 3's new non-docstring literals in `flatten.py` — the whole-listing raise and **both** warning messages, the uncached-rows one and the alternate-names one — which `test_python_string_literals_carry_no_internal_vocabulary` walks. That second message is also why the operator-facing wording says "the venue's list of alternate pair names" rather than naming the endpoint or the twin: an operator reading it mid-incident needs the consequence, and `altname` is the venue's word, not theirs. `test_code_prose_citations.py` is the only guard here that reads the runbook at all — its `_GLOBS` carry `*.md` and its roots are `cli/`, `tests/` and `infra/` — and it rejects a plan-task number with no 5-digit serial beside it. (Step 3's fences cite `spec 00111` and no task number, so that one is insurance rather than a known red; the plan's one remaining `Task <N>` token sits in a Task 5 terminal command, which lands in no file.)

- [ ] **Step 6: Commit — Task 1's work lands here too**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py cli/engine/command.py \
        infra/runbooks/engine-procedures.md README.md
git commit -m "fix(engine_flatten): cache the listing under both venue spellings before reading"
```

- [ ] **Step 7: Mutation-prove the guard**

After the commit, because `mutate-probe.sh` refuses a dirty worktree (its `git status --porcelain` check) and restores with `git checkout --`. Both operands are named, because the script requires a `--control` and exits rc 2 without one, rc 5 if the control does not fail, and rc 6 on a sed that matches nothing:

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/flatten.py \
  --control 's/uncached, aliases, cached = prime_cache(client, listing, altnames)/uncached, aliases, cached = [], {}, len(listing)/' \
  --mutation 's/client\.cache_instrument(row)/pass/' \
  -- uv run pytest tests/test_engine_flatten.py -k caches_the_listing_before -q
```

Expected: KILLED. The mutation leaves the loop **present, iterating and syntactically valid** while caching nothing: `cached` still increments, so the whole-listing refusal does not fire, nothing reaches `client.calls`, and `names.index("cache_instrument")` raises `ValueError` — the pre-fix behaviour reproduced exactly. The control skips `prime_cache` altogether and hands back the values a fully successful run would produce, so the same `ValueError` fires one statement earlier; it reaches the red **through** the guard rather than around it. (`s/client\.cache_instrument(row)/` matches the plain call and not `client.cache_instrument(_twin(row, altname))`, so the twin line is untouched by either operand — which is deliberate: the twin has its own probe at Step 8.)

**Two operands are excluded, and both fail the same way — they reach the whole-listing raise on an EMPTY `uncached`, whose message interpolates `uncached[0]`.** `'s/listing = await read_listing(client, rec)/listing = {}/'` gives an empty listing, and `'s/for symbol, row in listing\.items():/for symbol, row in []:/'` an unentered loop; either leaves `cached` at 0, so control reaches the raise, and building its argument raises `IndexError` before any `FlattenUnreachable` exists. `except FlattenUnreachable` does not catch it: it escapes a `run_flatten` that promises to raise nothing, and the test ERRORS. `mutate-probe.sh` scores an error exactly as it scores a detection, so either would be recorded as proof having proven nothing — the class the paragraph below excludes. (Production is unaffected: `read_listing` raises on an empty listing, so `cached == 0` there means every row's own caching raised and `uncached` is non-empty by construction, which is what the comment in Step 3 says.)

Before trusting either verdict, confirm the `-k` filter collects the test: `uv run pytest tests/test_engine_flatten.py -k caches_the_listing_before --collect-only -q` must report exactly 1.

**The operand must be checked against the block Step 3 actually writes, not against the loop in isolation.** `mutate-probe.sh` decides on `if "$@" >/dev/null 2>&1` with all output discarded, so an `IndentationError` scores KILLED exactly as a real detection does and the guard ships recorded as proven having proven nothing. A line-range deletion (`'/for …/,+1d'`) is the shape that produces one: applied to Step 3's block it removes the loop header and the `try:` under it, leaving `client.cache_instrument(row)` over-indented — reproduced, `py_compile` reports `IndentationError: unexpected indent`, and the probe would have scored that KILLED. Rule for **every** probe in this plan: apply the sed to the block as written, `python -m py_compile` the result, and only then run `mutate-probe.sh`. Task 3 Step 7's three probes were checked the same way and their six operands are sound — each is a same-line expression substitution that changes no indentation: `'s/resting_orders > 0 and //'` leaves a valid `elif`, `'s/cannot be trusted/is fine/'` a valid literal, and the four in probes (b) and (c) swap one call or one argument value inside an expression that stays on its own line.

- [ ] **Step 8: The offline venue — the only instrument that can see this fix**

**This is the step the branch turns on.** Every other test in this plan runs against `FakeClient`, whose fixtures are all coinciding-spelling pairs, and the live A/B at Task 5 runs on `SOLEUR`, whose count moves 0→2 with the twins and without them. Neither can tell the twin fix from the cached-listing-only one. This file can, it needs no venue, no credential, no vault and no data mount, and CI runs it. `tests/test_engine_data_socket.py` is the committed precedent for the shape — an inline real venue row, a `http.server` on `127.0.0.1`, and its own docstring saying why it is not opt-in.

**Its red phase is a mutation probe, not a temporal one, and that is deliberate.** Written after Step 3 it would be green on arrival, which this plan's own constraint calls worthless ("a test that passes with and without the fix"). Two things answer that instead: the arms test carries the pre-fix state as its own ARM B, so the file exhibits the defect and the fix side by side in one run; and the probes below construct the two defects and watch them bite.

Create `tests/test_engine_flatten_offline_venue.py`:

- **The fixture is six real `AssetPairs` rows, embedded verbatim.** The five basket legs whose altname differs from their key — `XXBTZEUR`/`XBTEUR`, `XETHZEUR`/`ETHEUR`, `XXRPZEUR`/`XRPEUR`, `XLTCZEUR`/`LTCEUR`, `XETHXXBT`/`ETHXBT` — plus `SOLEUR`, whose two spellings coincide and which is therefore the control that separates arm B from arm C. Take them from a credential-free public `AssetPairs` fetch (Task 4 Step 8 makes one anyway) and trim only `fees`/`fees_maker` to two rungs, exactly as `test_engine_data_socket.py` trims its row. **Do not hand-minimise the row further**: which fields the compiled parser requires is undocumented, and a row it rejects fails as an empty listing rather than as a named missing field.
- **The server answers four paths**, and the `AssetPairs` one must branch on its query string: `GET /0/public/AssetPairs` returns the six rows, `GET /0/public/AssetPairs?aclass_base=tokenized_asset` returns `{}` (the adapter requests both — measured; answering the second with the same six yields twelve rows and a listing that is silently doubled), `POST /0/private/OpenOrders` returns `{"error": [], "result": {"open": {…}}}`, `POST /0/private/OpenPositions` and `POST /0/private/Balance` return the canned bodies each test needs. Every body is `{"error": [], "result": …}`; Kraken carries errors in a 200.
- **The client is the real one**, `KrakenSpotHttpClient(key, secret, base_url=f"http://127.0.0.1:{port}")`, on values that authenticate nothing — the credential check is a string-presence gate, so a literal key and a base64 secret clear it and no request leaves the loopback interface. A module docstring says that, in the same terms as `test_engine_data_socket.py`'s.

The tests, and what each one alone would fail to prove:

```python
def test_the_three_cache_arms_discriminate_the_twin_fix():
    """The defect and the two candidate fixes, on one venue, in one run: cold cache 0 of 6, every
    listing row cached 1 of 6, listing rows plus altname twins 6 of 6. The one row arm B returns is
    `SOL/EUR`, whose two spellings coincide -- which is why a live A/B on that pair cannot tell arm
    B from arm C, and why this test exists. A claim about the ADAPTER: it passes whatever
    `run_flatten` does, and the test below is the one that reads production."""


def test_run_flatten_reads_every_resting_order_the_venue_holds():
    """Production's claim, through `run_flatten` itself so the twin loop and the altname map are
    both wired and not merely present: a dry run over an account resting one order per leg prints
    `6 resting order(s)`. Read the printed line, never the exit code -- a dry run returns 0 whether
    it saw six orders or none, which is the defect."""


def test_a_position_the_venue_spells_with_the_altname_closes_under_its_real_pair():
    """The twin's cost, paid. With twins cached and no alias the position comes back `XBTEUR`, the
    listing carries `BTC/EUR`, and `margin_legs` sizes NO closer -- the red button reporting a
    leveraged position instead of closing it. Through `prime_cache`'s own alias map it is one
    `BTC/EUR` SELL leg. Both halves are asserted, so an alias that silently did nothing fails."""


def test_the_alias_leaves_a_key_spelled_position_exactly_as_it_was():
    """The control for the test above: same twins, same alias map, a position the venue spells with
    the KEY. It must produce the identical `BTC/EUR` SELL leg -- an alias that only worked by
    rewriting every symbol would pass the test above and break every pair on the account."""


def test_a_cold_cache_aborts_the_position_read_rather_than_reading_flat():
    """The live defect this branch resolves as a side effect, pinned so a later edit cannot restore
    it: the position read shares the cache and RAISES on a miss where the order read drops the row
    silently, so today's deployed flatten exits 3 on any account holding a margin position. Asserted
    on the raised type and its message, because exit 3 is also what an unreachable venue returns."""
```

Measured, so each `Expected` is a reproduction rather than a prediction — the six readings the last three tests pin, taken through `read_positions` and `margin_legs` on this exact harness:

| cache | the venue's `pair` | result |
|---|---|---|
| cold | `XXBTZEUR` | `FlattenUnreachable: margin positions could not be read: OpenPositions: instrument not in cache for pair XXBTZEUR` |
| listing only | `XXBTZEUR` | one leg, `('BTC/EUR', 'SELL', 0.01)` |
| listing only | `XBTEUR` | `FlattenUnreachable: … instrument not in cache for pair XBTEUR` |
| listing + twins, no alias | `XBTEUR` | no leg; `unclosable` reason `pair_not_listed` |
| listing + twins, aliased | `XBTEUR` | one leg, `('BTC/EUR', 'SELL', 0.01)`, base `BTC` |
| listing + twins, aliased | `XXBTZEUR` | one leg, `('BTC/EUR', 'SELL', 0.01)` — unchanged |

**The new file has one blast-radius item outside itself, and it is not discoverable by reading this file.** `tests/test_engine_stub_fidelity.py` derives its `MODULES` from the directory — `glob("test_engine_*.py")` — and `_doubles_in` sweeps **every top-level `class`**, so the loopback handler class in a file named `test_engine_flatten_offline_venue.py` is an unclassified double and its own docstring says the consequence: "a NEW `test_engine_*.py` carrying a double is a red run until its doubles are classified here." Add the module and its handler to `TABLE` as `NOT_A_STANDIN` — it models a venue ENDPOINT, not a type this repo or the library owns, which is exactly the verdict's stated case ("a fixture-environment helper") — with an empty guards tuple, in the same edit that creates the file. Every top-level class in the new file needs an entry, and a top-level non-test function that builds a `SimpleNamespace` does too; keep helper functions free of `SimpleNamespace` and the class count to the handler and nothing else, and the entry stays one line.

Run: `uv run pytest tests/test_engine_flatten_offline_venue.py tests/test_engine_stub_fidelity.py -q`
Expected: all pass — 5 from the new file. A failure inside `request_instruments` reading "listing came back empty" is the fixture rows being rejected by the parser, not the fix; a failure in `test_every_test_double_in_the_engine_suite_is_classified` naming the new module is the `TABLE` entry above, not a defect in the double.

Commit, then prove both new guards bite:

```bash
git add tests/test_engine_flatten_offline_venue.py tests/test_engine_stub_fidelity.py
git commit -m "test(engine_flatten): the twin fix, discriminated against a loopback venue"

infra/scripts/mutate-probe.sh \
  --file cli/engine/flatten.py \
  --control 's/f"{altname}\.KRAKEN"/str(row.id)/' \
  --mutation 's/client\.cache_instrument(_twin(row, altname))/pass/' \
  -- uv run pytest tests/test_engine_flatten_offline_venue.py -k "reads_every_resting_order or key_spelled_position" -q

infra/scripts/mutate-probe.sh \
  --file cli/engine/flatten.py \
  --control 's/aliases\.get(symbol, symbol)/symbol/' \
  --mutation 's/aliases\[altname\] = symbol/pass/' \
  -- uv run pytest tests/test_engine_flatten_offline_venue.py -k "closes_under_its_real_pair" -q
```

Both KILLED, and the first pair's operands bite **different** tests, which is why they are run together. The control is the same-id twin — the cheap-looking edit a later reader reaches for, and the one the offline measurement disproved: sharing the real instrument's id does not add a second cache entry, it REPLACES the real one, so the KEY spelling then misses and `test_the_alias_leaves_a_key_spelled_position_exactly_as_it_was` goes red on a raise. The mutation removes the twin entirely, so the order count falls to 1 of 6 and `test_run_flatten_reads_every_resting_order_the_venue_holds` goes red. The second probe's pair is the alias's two halves: the control stops `read_positions` applying the map (the reader), the mutation stops `prime_cache` building it (the writer), and either alone leaves the close path exactly as blind as it was. Confirm each `-k` collects exactly the expected count (`2`, then `1`) with `--collect-only -q` first, and apply each sed to the block as written and `python -m py_compile` the result before trusting a verdict — all four are same-line expression substitutions that change no indentation.

---

### Task 3: The funding gate fails closed, and announces when it need not

**Files:**
- Modify: `cli/engine/probeplan.py` (`plan_refusals`), `cli/engine/venuestate.py`, `cli/engine/executor.py`, `cli/engine/command.py`, `infra/runbooks/engine-procedures.md` (the `engine-probe-window` procedure's step 3, which enumerates the output the new echo joins)
- Test: `tests/test_engine_probeplan.py`, `tests/test_engine_executor.py` (the three `_pickup` threading tests), `tests/test_engine_venuestate.py` (the locked map's source), `tests/test_engine_command.py` (the `--check` disclosure), plus the `VenueState(...)` construction sites and the two fake accounts listed in Step 1

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `plan_refusals` accepting the two new inputs.

- [ ] **Step 1: Carry the locked map through `venuestate`, and NOT through the journal**

`venue_state_from_cache` currently keeps only `balances_free()`. Add the sibling map beside it, mirroring that line exactly — `Account.balances_locked()` **does** exist on the installed 2.0.0rc4.dev20260825 (`hasattr(MarginAccount, 'balances_locked')` is True) and returns `dict[Currency, Money]`, so no manual derivation from `AccountBalance.locked` is needed:

```python
    balances_locked = {currency.code: float(money) for currency, money in account.balances_locked().items()}
```

Executed on a constructed `MarginAccount` with a `2.757 EUR` hold, that expression returns `{'EUR': 2.76}` (EUR precision 2 quantizes it) — the same shape and the same quantization as the `balances` line above it.

**What this reader sees in production is not the account the spec measured, and no offline run here can close that.** `Cache.account_for_venue` returns the exec client's account, and `node.py`'s `_exec_client_config` builds that client `spot_account_type=AccountType.MARGIN`; the spec's `locked == 0` came off flatten's `CASH`-typed read (spec D2's second paragraph). Every fixture below passes a map by hand, so a green suite says the reader and the guard are wired correctly and says **nothing** about what the live margin-typed account reports. Task 5 Step 5 takes that reading, and D2 decides the outcomes in advance.

`VenueState` gains `balances_locked: dict[str, float]` as a **required** field, and **`to_payload()` is left untouched**. That is the decision, not an oversight (spec D2's "Where it runs"): `to_payload()`'s output is the `state` object of every `venue-<HH>.json`, and `validate_venue_record` compares its key set for exact equality against `_STATE_KEYS = {"snapshot_at", "instruments", "positions", "balances"}` — executed, the current shape validates and the same document plus one extra key raises `EngineJournalError: venue record 'state' keys [...] != expected [...]`. Journalling the field would therefore require bumping `VENUE_SCHEMA_VERSION`, giving `_STATE_KEYS` a per-version shape, and updating **three** readers that hardcode `schema_version != 2` — `command._seed_exec_positions`, `command._newest_venue_record`, `executor._newest_venue_balances` — plus a rollback hazard on the live trade path. Not done here.

**What declining it leaves standing, stated rather than discovered.** The third of those readers is not an advisory one: `executor._newest_venue_balances` returns `state["balances"]` and `_classify_close` hands it to `_classify_spot_close`, whose `qty <= balance` bound at `REDUCE_ONLY` is on the **live trade path** — its own docstring calls that bound plus the venue's insufficient-funds rejection "the whole guard". Those balances are `account.balances_free()`, the figure spec 00111 mechanism 2 shows is overstated by whatever the venue holds. So this plan closes the fail-open at `plan_refusals` and leaves the identically-caused one at `_classify_spot_close` open, deliberately and at the price of the schema bump above. **Registered, not left in prose**: `T0160` already carries it as its own sub-item, beside the `hold_trade` deferral it is the other half of; Task 6 Step 2 re-reads and re-tenses it at closeout rather than adding it again.

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

Give each a `balances_locked` returning `dict[Currency, Money]` — the real type's own terms, the reason `_fake_account`'s docstring gives for not using plain str/float keys, and what forces the reader to call `.code`/`float()`.

**Neither stand-in may return a constant, and this is the half a plan like this one usually gets wrong.** `balances_locked` is one of D2's two live inputs, and the argument this plan already makes for the other one — *"a mis-threaded `resting_orders=0` type-checks and keeps every one of them green"* — applies to it identically and harder: `{}` is simultaneously the value a hardcoded stand-in returns, the value `venue_state_from_cache` would produce if someone wrote `balances_locked = {}` instead of calling the account, and the value a mis-threaded call site passes. All three read the same to every test that does not vary it. Measured, the two stand-ins below are the only ones — `grep -rn balances_free cli/ tests/` returns `tests/test_engine_venuestate.py`, `tests/test_engine_executor.py` and the one production reader — so no third fixture accidentally covers this.

So both stand-ins take the map as an argument:

- **`_fake_account(balances_free, balances_locked=None)`**, and the `fake_cache` fixture passes `{"EUR": 2.757}` beside its existing free map `{"EUR": 987.65, "BTC": 0.5}`. The locked map is deliberately **different from the free map in both keys and values**, so a `balances_free()` copy-paste in the reader is caught as well as a hardcoded `{}`. The other **three** `_fake_account(...)` sites keep the default, which is `{}` — `grep -n "_fake_account(" tests/test_engine_venuestate.py` returns the definition plus four call sites, and the three that are not the `fake_cache` fixture are `fake_cache_missing_dot`, `test_no_account_cached_raises`' neighbour, and — the one an enumeration stopping at "the fixtures" misses — the `_library_standins()` registration `("_fake_account", _fake_account({"EUR": 1.0}), MarginAccount, frozenset())`, which is a fidelity registration rather than a fixture and is the site that makes the new `balances_locked` legal at all.
- **`StubCache(..., locked=None)`**, threaded into the namespace `account_for_venue` returns rather than hardcoded there. `{}` stays the default, which is the fail-closed value Step 2's first `_pickup` test keys on; Step 2's third test passes a real hold. **Add `"_locked"` to `_STUB_CACHE_PLUMBING` in the same edit** — `nautilus_trader.common.Cache` carries neither `_locked` nor `locked` (measured), and that file's `test_no_stub_in_this_file_offers_a_name_its_real_nautilus_type_lacks` fails on any name the stub offers that the real type lacks. This is the same trap Task 1 Step 1 closes for `cached_symbols`, in the other file.

**Write the source assertion here, before the line that satisfies it**, beside `test_balances_are_read_by_currency_code` in `tests/test_engine_venuestate.py` — the file's own one-line precedent for exactly this read:

```python
def test_locked_balances_are_read_by_currency_code_and_differ_from_the_free_map(fake_cache):
    """The locked map has its own keys and its own values, so a reader that returned the free map,
    or a constant `{}`, reads differently here. Every other fixture in this file passes `{}`, which
    is also what a hardcoded reader would produce, so nothing else here can tell the two apart."""
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert vs.balances_locked == {"EUR": 2.76}
```

`2.76`, not `2.757`: `Money` at EUR precision 2 quantizes, exactly as the `{'EUR': 2.76}` measured at the top of this step. Run it before adding the production line and read the failure — `AttributeError: 'VenueState' object has no attribute 'balances_locked'` — then add the line and see it green. It is green from here on, so it is **not** part of Step 3's red run; what proves it bites is Step 7's second mutation probe.

**Only one of the two is pinned, and the run that pins it is not the file whose name says so.** `tests/test_engine_stub_fidelity.py` *classifies* `_fake_account` as standing in for `nautilus_trader.model.MarginAccount` and names the guard — it never constructs the stub and never imports the library (its own docstring: "Nothing here imports the modules it classifies: the walk reads them as source"), so it cannot tell a legal attribute from a fabricated one. The run that can is **`tests/test_engine_venuestate.py`'s `test_no_stub_in_the_venue_reader_suite_offers_a_name_its_real_library_type_lacks`**, which builds `_library_standins()` in that file and checks each offered name against the real class. `MarginAccount` carries `balances_locked` (measured), so the addition is legal and that test is where a green says so. The executor stand-in is the **anonymous `SimpleNamespace`** `StubCache.account_for_venue` returns; neither file registers an account stand-in for it, so nothing checks its shape. Match `_fake_account`'s shape there by hand; no fidelity run will catch a wrong one.

- [ ] **Step 2: Write the failing tests**

In `tests/test_engine_probeplan.py`, beside the fifteen existing `plan_refusals` tests. The module constant is `NOW` (line 11) — there is no `_NOW`.

**`caplog` cannot see these records; three of the assertions below would be vacuous or red under it.** pytest's `caplog` handler sits on the ROOT logger, and `cli.logging.config.configure()` sets `zcrypto.propagate = False` — which every `zcrypto` CLI invocation performs, the call sitting in `cli/__main__.py`'s app callback — so once any CliRunner test has run earlier in the session nothing arrives. `tests/test_engine_command.py` sorts ahead of this file and is full of `runner.invoke` calls, so a local single-file run reads records and CI's alphabetical whole-suite run reads none: the two announcement assertions would go RED in CI on a fix the implementer just watched pass locally, and the third would pass vacuously with nothing pointing at the cause. Collect off the module's own logger instead — the pattern `tests/test_engine_executor.py`'s `_the_tick_backstop_never_fires` already uses, and which names both reasons. Add `import logging` and `from contextlib import contextmanager` (the module imports neither today):

```python
@contextmanager
def _announcements():
    """The records `plan_refusals` logs, collected off the module's own logger.

    NOT `caplog`: its handler sits on the root logger while `cli.logging.config.configure()` sets
    `zcrypto.propagate = False`, so these records stop arriving as soon as any CliRunner test has
    run earlier in the session. `tests/test_engine_executor.py`'s `_the_tick_backstop_never_fires`
    records the same finding and the same workaround."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    log = logging.getLogger("zcrypto.engine.probeplan")
    handler = _Collect()
    previous_level = log.level
    log.setLevel(logging.DEBUG)  # a logger's own level wins over any ancestor a CLI test configured
    log.addHandler(handler)
    try:
        yield records
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)
```

`r.getMessage()`, never `r.message`: `.message` is set by a formatter, which `caplog` runs and a bare handler does not.

```python
def test_plan_refusals_refuses_when_free_cannot_be_trusted():
    """No balance reports a hold while an order rests, so `free` includes money the venue has
    reserved (spec 00111 D2). The gate fails CLOSED rather than sizing against cash it cannot see,
    and D3's announcement stays SILENT on the same inputs -- an announcement on an all-zero map
    would ride along with every refusal for the life of the guard and signal nothing. The comparison
    written `>= 0.0` refuses exactly as asserted below and announces here, which is the one state
    the firing and not-evaluated tests beside it cannot separate."""
    with _announcements() as records:
        reasons = plan_refusals(
            _margin_plan(),
            now=NOW,
            ledgered=frozenset(),
            max_plan_notional_eur=100.0,
            free_zeur=99.52,
            balances_locked={"EUR": 0.0},
            resting_orders=1,
        )
    assert any("cannot be trusted" in r for r in reasons)
    assert records == []


def test_plan_refusals_does_not_refuse_when_nothing_rests():
    """The control: same all-zero locked map, no resting orders, no refusal. Without this a guard
    that always refuses would pass the test above."""
    reasons = plan_refusals(
        _margin_plan(),
        now=NOW,
        ledgered=frozenset(),
        max_plan_notional_eur=100.0,
        free_zeur=99.52,
        balances_locked={"EUR": 0.0},
        resting_orders=0,
    )
    assert not any("cannot be trusted" in r for r in reasons)


def test_an_empty_locked_map_refuses_like_an_all_zero_one():
    """A read that returned no balances learned nothing about holds, which is the untrustworthy
    input this refusal exists to catch -- not a licence to size against `free`."""
    reasons = plan_refusals(
        _margin_plan(),
        now=NOW,
        ledgered=frozenset(),
        max_plan_notional_eur=100.0,
        free_zeur=99.52,
        balances_locked={},
        resting_orders=1,
    )
    assert any("cannot be trusted" in r for r in reasons)


def test_a_nonzero_locked_announces_and_stops_refusing():
    """D3: when any balance reports a hold, `locked` is real and the refusal stops firing --
    correct, but silent. Both halves are asserted here, so a guard that announced without releasing
    (or released without announcing) fails."""
    with _announcements() as records:
        reasons = plan_refusals(
            _margin_plan(),
            now=NOW,
            ledgered=frozenset(),
            max_plan_notional_eur=100.0,
            free_zeur=99.52,
            balances_locked={"EUR": 2.757},
            resting_orders=1,
        )
    assert not any("cannot be trusted" in r for r in reasons)
    assert any("a balance reports held funds" in r.getMessage() for r in records)


def test_a_non_finite_hold_is_named_and_still_announces_the_real_one():
    """`nan > 0.0` is False, so a non-finite hold would otherwise read as 'no balance reports a
    hold' and be indistinguishable from a real zero. It is named instead -- and this is the one
    state where the refusal and the announcement are both live, which is why the announcement is
    not the refusal's `else`."""
    with _announcements() as records:
        reasons = plan_refusals(
            _margin_plan(),
            now=NOW,
            ledgered=frozenset(),
            max_plan_notional_eur=100.0,
            free_zeur=99.52,
            balances_locked={"EUR": float("nan"), "USD": 5.0},
            resting_orders=1,
        )
    assert any("not finite" in r and "EUR" in r for r in reasons)
    assert any("a balance reports held funds" in r.getMessage() for r in records)


def test_unknown_inputs_neither_refuse_nor_announce():
    """The offline validator's case: it reads a journalled snapshot carrying neither input, so it
    passes None and the check is NOT EVALUATED -- no refusal it could never clear, and no
    announcement it never observed. `probe-plan --check` prints that it did not run."""
    with _announcements() as records:
        reasons = plan_refusals(
            _margin_plan(),
            now=NOW,
            ledgered=frozenset(),
            max_plan_notional_eur=100.0,
            free_zeur=99.52,
            balances_locked=None,
            resting_orders=None,
        )
    assert not any("cannot be trusted" in r or "not finite" in r for r in reasons)
    assert records == []
```

**Three more, in the two files the threading actually reaches.** The six above call `plan_refusals` directly and so cannot see a call site that threads a literal; a mis-threaded `resting_orders=0` — or `balances_locked={}` — type-checks and keeps every one of them green. The first two below discriminate the count; the third discriminates the map, and without it every test in the branch reads `{}` for `balances_locked` and a call site passing that literal ships green.

**The existing tests the new refusal changes — measured by running the suite under the guard, not by reading it.** `plan_refusals` sees a live cache only through `executor._pickup`, and `tests/test_engine_executor.py` is the only suite that drives it (`tests/test_engine_node.py` substitutes a `RecordingExecutor`; `tests/test_engine_probeplan.py` calls `plan_refusals` directly, which is Step 4's fifteen-call update). In that file **exactly one** existing test both populates `StubCache.open_orders` and drops a plan: `test_a_position_that_contradicts_the_intents_fills_trips_at_the_terminal`. Its plan is dropped by the `_resting_executor` helper rather than in its own body, which is why grepping test bodies for `_drop_plan` reports this family EMPTY — it is not, and Step 4 updates that one fixture. Every other `open_orders=[…]` construction in that file is a startup, adoption or reconciliation test that drops no plan, so `plan_refusals` is never reached with a non-empty book in any of them and the refusal changes no other expectation — run under the guard, that one test is the file's only red.

```python
# tests/test_engine_executor.py, beside the other plan-refusal tests
def test_a_resting_order_with_no_reported_hold_refuses_the_plan(tmp_path):
    """`_pickup` threads the LIVE count, not a literal. Two other tests here reach `_pickup` with a
    non-empty book -- `test_a_position_that_contradicts_the_intents_fills_trips_at_the_terminal`, the
    only one that did before this change, and `test_a_reported_hold_does_not_refuse_the_plan_for_trust`
    below -- and BOTH report a hold, so the trust refusal cannot fire in either whatever the count
    says. This is the only test here the count can move: a call site passing `resting_orders=0` keeps
    the whole suite green while the guard never fires in production, present in review and inert on
    the arming path."""
    client = StubClient(StubCache(balances={"EUR": 99.84}, open_orders=[_open_order("O-resting")]))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=30.0, leverage=2)]))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    assert entry["disposition"] == "refused"
    assert any("cannot be trusted" in r for r in entry["reasons"])


def test_the_same_plan_is_not_refused_for_trust_with_an_empty_book(tmp_path):
    """The control that makes the test above about the COUNT and not about the fixture: same
    balances, same plan, empty book. Asserts only on the trust reason, so any other refusal the
    plan may earn cannot make it pass vacuously. Named to avoid `nothing_rests`, which is a
    probeplan test's substring and would be swept up by a cross-file `-k`."""
    client = StubClient(StubCache(balances={"EUR": 99.84}))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=30.0, leverage=2)]))

    ex.on_timer(NOW)

    assert not any("cannot be trusted" in r for r in _plan_entry(tmp_path)["reasons"])


def test_a_reported_hold_does_not_refuse_the_plan_for_trust(tmp_path):
    """The map's discriminator. Identical to the refusing test above except that a balance reports
    a hold -- so a call site passing the literal `{}`, a reader hardcoding `{}`, and the real map
    read the same in every other test here but the adopted-reducer trip, whose own red reads as a
    kill switch that did not fire rather than as anything about the map."""
    client = StubClient(StubCache(balances={"EUR": 99.84}, locked={"EUR": 2.757}, open_orders=[_open_order("O-resting")]))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=30.0, leverage=2)]))

    ex.on_timer(NOW)

    assert not any("cannot be trusted" in r for r in _plan_entry(tmp_path)["reasons"])
```

```python
# tests/test_engine_command.py, beside test_probe_plan_check_echoes_the_rest_hold_offset_and_hold
def test_probe_plan_check_says_the_untrustworthy_balance_check_did_not_run(tmp_path, monkeypatch):
    """Spec 00111 D2 makes the disclosure part of the decision: this command passes None for both
    live inputs, so an operator reading a clean refusal list must not read it as the funding gate's
    verdict. Nothing else in the output would go red if the one echo were dropped."""
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent()])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "was not evaluated here" in out
```

- [ ] **Step 3: Run and see them fail for the RIGHT reason**

Run: `uv run pytest tests/test_engine_probeplan.py -k "cannot_be_trusted or nothing_rests or empty_locked_map or nonzero_locked or non_finite_hold or unknown_inputs" -v`
Expected: all six FAIL, and **the failure text must name `balances_locked`/`resting_orders`** — `TypeError: plan_refusals() got an unexpected keyword argument`. A `NameError` or a collection error means the red proves nothing about the signature. Confirm the selection collects exactly six first: same command with `--collect-only -q`.

The four cross-file tests are a second red, and they fail for a **different** reason — the call sites do not thread yet, so the refusal and the echo simply do not appear:

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_command.py -k "no_reported_hold or not_refused_for_trust or a_reported_hold_does_not_refuse or untrustworthy_balance_check_did_not_run" -v`
Expected: `no_reported_hold` FAILS on its **disposition** line (`AssertionError: assert 'accepted' == 'refused'`) — that assertion sits above the reason one, so the missing refusal is what it reads as an accepted plan — `untrustworthy_balance_check_did_not_run` FAILS on the missing echo, and **both controls PASS** — `not_refused_for_trust` and `a_reported_hold_does_not_refuse`, which are red here only if they are testing the wrong thing. A control that passes here proves nothing on its own, which is why each has a mutation operand in Step 7. Confirm the selection collects exactly four first: same command with `--collect-only -q`.

`tests/test_engine_venuestate.py`'s locked assertion is **not** in this run: Step 1 both wrote it and made it green, and its red phase was read there.

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
                "a balance reports held funds (%r) -- the untrustworthy-balance refusal does not "
                "fire while this holds; re-derive whether the funding gate still needs it",
                balances_locked,
            )
```

**The line says what it READ, not that anything changed** (spec D3's no-memory paragraph). The guard holds no previous reading, so the earlier wording — *locked is no longer zero … the adapter now reports held funds* — asserted a transition nothing observed, and would have told an operator that the upstream fix had landed on the first pickup of an account whose `MARGIN`-typed `locked` was never zero to begin with. That is the reading spec D2 records as unmeasured and Task 5 Step 5 takes. **Family, four members, all of the substring and none of them the same edit**: this literal; the two `records` assertions in Step 2 (`test_a_nonzero_locked_announces_and_stops_refusing`, `test_a_non_finite_hold_is_named_and_still_announces_the_real_one`), which key on `"a balance reports held funds"` — **the leading article is load-bearing**, since the refusal reason beside it reads *no balance reports held funds* and the bare `"reports held funds"` is a substring of both, one edit away from an assertion that cannot tell the announcement from the refusal; and `T0160`'s sub-item, which quotes the old literal as the signal its first arm watches for — re-tensed at Task 6 Step 2, which is where this branch's `T0160` edits land. `grep -rn "locked is no longer zero" cli/ tests/ docs/open-topics/` is the completion check and must return nothing once all four have landed; this plan is deliberately outside those roots, because the paragraph you are reading quotes the superseded wording on purpose.

**The log line carries no decision token.** `tests/test_internal_terms_not_operator_visible.py` scans every non-docstring string literal under `cli/` and `\bD\d{1,2}[a-z]?\b` is in its vocabulary. Run against the literals this step writes — the warning above, both refusal reasons, and `command.py`'s echo below — `_leaks(...)` returns `[]` for each, while `_leaks("spec 00111 D2 says so")` returns `['spec 00111', 'D2']`, which is what says the helper would have spoken had the token been left in. The guard's own failure message says what to do anyway: move the token to the adjacent comment, which is what the comment above does.

Thread both inputs at the two call sites, whose sources differ and are the reason the parameters are nullable:

- **`executor.py`'s `_pickup`** — the live gate. **One placement, and it is not the `free_zeur` line**: on the line immediately after `state = venue_state_from_cache(self._client.cache, clock=self._now)`, INSIDE that `try`.
  ```python
          resting_orders = len(self._client.cache.orders_open(venue=_VENUE))
  ```
  The `try`'s `except Exception:` block ends in a `return`, and `free_zeur` is assigned after it — outside the `try` — so the two are different places and only one is safe. `orders_open` is a read this file already treats as failure-prone: both existing call sites carry their own `try`/`except` (`"venue orders could not be read at startup"`, `"open orders could not be read while tripping"`), and `_FlakyOrdersCache` and `_UnreadableOrderCache` in `tests/test_engine_executor.py` exist to model exactly that. Outside the `try`, a raise escapes `_pickup` into `on_timer`'s catch-all and the plan is **neither journalled with a disposition nor deleted** — it sits in `exec/` with no refusal record, repeating every tick if the condition is not transient. Inside it, the same failure degrades to the existing journalled `"no venue truth"` refusal. Python function scope keeps the name live at the `plan_refusals` call below. Pass `balances_locked=state.balances_locked, resting_orders=resting_orders`.

  **The count inherits the defect this branch is fixing, and that is worth stating rather than discovering.** The Cache's open-order index is filled by the node's own reconciliation, which reads through the same adapter — so if the node's instrument cache is cold the way `flatten`'s was, `resting_orders` reads 0, D2 never fires, and the guard is present and inert. The evidence that it is not cold is indirect and dated: `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` records the engine's `unmatched` external-event counter rising by **12** across the 2026-08-26 probe window (12 → 24, one process throughout), i.e. it saw orders it had not placed. The 24 is the counter's absolute reading and that document's own discharged note forbids quoting it as the run's total. Task 5 takes the direct reading.
- **`command.py`'s `probe_plan`** — the offline `--check` validator. Its record is a journalled `venue-<HH>.json`, whose `state` carries neither holds nor orders, so it passes `balances_locked=None, resting_orders=None` and echoes one line saying so, in the same place it echoes the gate verdict and the snapshot timestamp:
  ```python
      typer.echo("the untrustworthy-balance check needs live venue truth and was not evaluated here")
  ```
  That is honest rather than fail-open: this command "writes nothing anywhere" and its own help calls it "Advisory only -- the engine re-validates every plan live before any order". Making it refuse instead would refuse **every** plan forever, since a journalled record can never supply the inputs.

  **The echo changes an output a runbook enumerates verbatim, so that edit lands in this same step.** `grep -rn "venue snapshot:" infra/ README.md cli/` returns exactly two lines: the echo above it in `command.py`, and step 3 of the `engine-probe-window` procedure in `infra/runbooks/engine-procedures.md`, whose "Expect the gate verdict, a `venue snapshot: <timestamp>` line, then one line per intent … and a last line `plan ok: …`" is exhaustive and whose own instruction on any mismatch is to fix the plan and not place it. Add the disclosure line to that expectation, between `venue snapshot:` and the per-intent lines — where the echo puts it. **Family: one member** — that grep is the whole enumeration, and `README.md`'s `probe-plan` row lists what the command validates and no output line at all.

Then update the **fifteen** existing `plan_refusals` calls in `tests/test_engine_probeplan.py` (lines 329, 337, 344, 350, 356, 364, 371, 378, 390, 397, 404, 412, 418, 424, 431) with `balances_locked={}, resting_orders=0` — the values that preserve each test's existing subject, since no order rests in any of them.

**And the one existing fixture the guard's arrival breaks** — `test_a_position_that_contradicts_the_intents_fills_trips_at_the_terminal`, the member Step 2's enumeration names. Its `StubCache(open_orders=[_open_order("O-attached")])` gains `locked={"EUR": 2.757}`, the hold `test_a_reported_hold_does_not_refuse_the_plan_for_trust` uses; `locked` feeds nothing but `balances_locked()`, so the test's subject — a trip cancelling a resting order the engine adopted rather than placed — is untouched. **Not optional, and the shape of the failure is why**: without it that test's plan is refused `cannot be trusted`, so no order is submitted, so `_resting_executor`'s own trailing `assert len(client.submitted) == 1` fails `assert 0 == 1`, and the autouse `_no_unannounced_kill_trip` guard ERRORs at teardown with `this construction was supposed to trip the kill switch and did not` — the two reds together, one of which is not about the guard at all. The nearest edit that turns that green is an exemption in `plan_refusals` or `_pickup` for engine-adopted or reduce-only orders — which loosens this guard on exactly the case spec 00111 D2 prices, at the arming gate, shipped green. The fixture is the fix; the guard is not.

- [ ] **Step 5: Run every suite this task can reach**

Run: `uv run pytest tests/test_engine_probeplan.py tests/test_engine_venuestate.py tests/test_engine_venueledger.py tests/test_engine_executor.py tests/test_engine_cycle.py tests/test_engine_execledger.py tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_engine_node.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: all pass. **A red in `tests/test_engine_executor.py` here is a further member of Step 2's family — find its fixture, never loosen the guard**; Step 4's one fixture update is what keeps this list green, and the enumeration behind it is Step 2's. The venuestate/venueledger pair is what proves `to_payload()` was left alone; executor/cycle/execledger/command are the `VenueState` construction sites and the threaded call sites; **venuestate again is where the `balances_locked` addition is proved legal**, by `test_no_stub_in_the_venue_reader_suite_offers_a_name_its_real_library_type_lacks` — stub_fidelity only classifies `_fake_account` and imports nothing, so it is in the list to confirm the classification still resolves and not to check the attribute; node is the third `venue_state_from_cache` caller. **`test_internal_terms_not_operator_visible.py` is in the list for the same reason Task 2 Step 5 carries it**: Step 4 writes new non-docstring literals under `cli/` — `probeplan.py`'s two refusal reasons and its `logger.warning`, `command.py`'s `typer.echo` disclosure — and `test_python_string_literals_carry_no_internal_vocabulary` walks every literal in those packages with `\bD\d{1,2}[a-z]?\b` in its vocabulary. Step 4 already cites that guard as the reason the decision token sits in a comment; without the file here the guard first speaks in CI, on a commit this step declared clean.

Then run the two announcement tests **in CI's order as well**, because that order is what would break them and the list above hides it:

Run: `uv run pytest tests/test_engine_command.py tests/test_engine_probeplan.py -q`
Expected: all pass. `tests/test_engine_command.py` first is what CI's alphabetical whole-suite run does, and it is the condition under which a root-attached `caplog` reads empty — green here is the evidence that the announcement assertions are not order-dependent.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/probeplan.py cli/engine/venuestate.py cli/engine/executor.py cli/engine/command.py \
        tests/test_engine_probeplan.py tests/test_engine_venuestate.py tests/test_engine_venueledger.py \
        tests/test_engine_executor.py tests/test_engine_cycle.py tests/test_engine_execledger.py \
        tests/test_engine_command.py infra/runbooks/engine-procedures.md
git commit -m "fix(probeplan): the margin floor fails closed when free cannot be trusted"
```

Stage every file Step 1 and Step 4 touched — a `git add` short of that leaves the tree dirty, which the next step's `mutate-probe.sh` refuses outright. `tests/test_engine_stub_fidelity.py` is deliberately **not** in that list: no step here edits it. Its `TABLE` classifies `_fake_account` and `StubCache`, both of which keep their names through this task, and its walk reads only top-level classes plus top-level non-test functions that build a `SimpleNamespace` — so Step 2's `_announcements`, whose `_Collect(logging.Handler)` is nested inside a function, adds no discoverable double either. Run it (Step 5 does); stage nothing.

- [ ] **Step 7: Mutation-prove the guard — three probes, one per link in the chain**

The guard is only as good as its weakest link, and the three links fail independently: the refusal's own logic, the map's source, and the map's thread. A probe on one says nothing about the other two.

**(a) The refusal's logic.**

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/probeplan.py \
  --control 's/cannot be trusted/is fine/' \
  --mutation 's/resting_orders > 0 and //' \
  -- uv run pytest tests/test_engine_probeplan.py -k "cannot_be_trusted or nothing_rests" -q
```

Expected: KILLED. The two operands bite **different** tests, which is the point of running them as a pair: the control renames the refusal string, so `refuses_when_free_cannot_be_trusted` goes red; the mutation drops the resting-orders conjunct — the exact fail-tight defect D2's stated cost buys — so the refusal fires unconditionally and `does_not_refuse_when_nothing_rests` goes red. A mutation killed only by the first test would leave the control test unproven. Confirm the `-k` filter collects exactly 2 with `--collect-only -q` before trusting either verdict.

**(b) The map's SOURCE — the copy-paste that reads the wrong account method.**

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/venuestate.py \
  --control 's/account\.balances_locked()\.items()/{}.items()/' \
  --mutation 's/account\.balances_locked()/account.balances_free()/' \
  -- uv run pytest tests/test_engine_venuestate.py -k locked_balances -q
```

Expected: KILLED. Both operands are anchored on `account.balances_locked()`, which after Step 1 appears on exactly one line of that file — the dataclass field declaration and the `VenueState(...)` return carry the NAME but not the call, so neither sed can wander onto them. The mutation is the realistic defect (the line above it is the `balances_free()` one it was written beside); the control is the other one, a hardcoded empty map. The test's fixture is what makes both visible: its locked map differs from its free map in keys and values, so `{"EUR": 2.76}`, `{"EUR": 987.65, "BTC": 0.5}` and `{}` are three distinguishable answers. Confirm `-k locked_balances` collects exactly 1 first.

**(c) The map's THREAD — the literal at the call site, which nothing else in the branch can see.**

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/executor.py \
  --control 's/resting_orders=resting_orders/resting_orders=0/' \
  --mutation 's/balances_locked=state\.balances_locked/balances_locked={}/' \
  -- uv run pytest tests/test_engine_executor.py -k "no_reported_hold or a_reported_hold_does_not_refuse" -q
```

Expected: KILLED, and again on **different** tests: the control passes the count as a literal 0, so the refusal never fires and `a_resting_order_with_no_reported_hold_refuses_the_plan` goes red; the mutation passes the map as a literal `{}`, so the refusal fires on an account that IS reporting a hold and `a_reported_hold_does_not_refuse_the_plan_for_trust` goes red. Both operands are the two mis-threadings this step exists to exclude, written out. Confirm the `-k` filter collects exactly 2 first.

---

### Task 4: The fixture script

**Files:**
- Create: `infra/scripts/kraken-fixture.sh`
- Create: `infra/scripts/flatten-with-vaulted-key.sh` (the second entry point, for Task 5)
- Modify: `infra/scripts/kraken-order-semantics-probe.py` (the three balance renders — Step 7)
- Modify: `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` (the listing-spelling reading — Step 8)
- **Do NOT modify** `infra/scripts/probe-with-vaulted-key.sh`, and **do not touch `.claude/settings.json`** — Step 4 says why both are refusals rather than omissions
- Modify: `README.md` if it gains an operator-facing entry point

**Interfaces:**
- Consumes: `kraken-cli` 0.4.1 on the workstation, installed at `~/.cargo/bin/kraken` and **not on the default PATH**.
- Produces: a one-leg mint, an independent verification read, and a rehearsed close, all for Task 5.

- [ ] **Step 1: Write the script**

Header states the constraint verbatim: *workstation development tool; not available in CI; never imported by `cli/`; never a runtime dependency of the engine.* It also says where the binary is (`~/.cargo/bin/kraken`) and resolves it, so no caller has to know.

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

- [ ] **Step 2: Exercise all three modes in their default (validate) mode — bracketed, because this is the first-ever run**

`kraken-cli` is **not on the default PATH** (the binary is `~/.cargo/bin/kraken`). Step 1 settles that for the script itself — it resolves the binary in its own header, so **no `bash infra/scripts/kraken-fixture.sh …` invocation anywhere in this plan needs a PATH prefix**, at Task 5 Steps 1, 3, 4 and 7 included. What still needs one is a **bare** `kraken …` call, and the plan has exactly two places with those: this step's six before/mid/after captures, and Task 5 Step 7's `query-orders`. Both carry the `export PATH` line, which holds for the rest of that shell. Without it these runs abort with `kraken: command not found`, and the venue-side `--validate` rehearsal this step exists for slides into the attended window under the rollover clock.

```bash
export PATH="$HOME/.cargo/bin:$PATH"
kraken positions -o json > /tmp/fixture-before-positions.json
kraken extended-balance -o json > /tmp/fixture-before-balance.json

bash infra/scripts/kraken-fixture.sh verify
bash infra/scripts/kraken-fixture.sh mint

kraken positions -o json > /tmp/fixture-mid-positions.json
kraken extended-balance -o json > /tmp/fixture-mid-balance.json
diff /tmp/fixture-before-positions.json /tmp/fixture-mid-positions.json   # THE discriminator
diff /tmp/fixture-before-balance.json /tmp/fixture-mid-balance.json

bash infra/scripts/kraken-fixture.sh close

kraken positions -o json > /tmp/fixture-after-positions.json
kraken extended-balance -o json > /tmp/fixture-after-balance.json
diff /tmp/fixture-mid-positions.json /tmp/fixture-after-positions.json
diff /tmp/fixture-mid-balance.json /tmp/fixture-after-balance.json
```

All four diffs must be **empty**. The balance pair is split at the same point as the positions pair for one reason: a non-empty balance diff has to be attributable to `mint` or to `close` before it can be read at all. The captures bracket the runs rather than following them: this is the script's first-ever execution and its `--validate` default is exactly what is unproven, so a capture taken afterwards would already contain anything a wrongly-submitted `mint` created and `before == after` would report the safety default proven. (`extended-balance` moves with the venue's own hold accounting, so a non-empty balance diff is a finding to read, not noise to wave through.)

**The mid capture is what carries the proof, and it is why `mint` and `close` are not bracketed together.** `mint` is `--type market`, so a submitted leg *fills*; `close` is the exact `--reduce-only` netting order for it, so a submitted close fills too. Bracketed as one, a broken `--validate`/`--execute` inversion opens and closes the position **inside** the bracket and `positions` before == after == empty — the one diff left non-empty would be `extended-balance`, which the paragraph above pre-licenses as venue hold accounting. Split, the mint-only interval is the interval in which a wrongly-submitted leg must be visible, and an empty diff there is a reading that could have come out otherwise. The `mid`→`after` diff is then the close's own check and nothing more.

`verify` is read-only and costs nothing to run now — the spec makes it the witness every D4 assertion rests on, so it must not first execute inside the attended window.

**Its reading is compared against the spec's measured-basis table here, which is what makes the spec's "re-confirmed before the branch spends anything, not only at the attended step" true.** `verify`'s `open-orders` leg must show both txids (`OZRI5U-U7WGD-OYCOMW`, `OVNLAJ-6PXBH-T4GDXF`) at 0.06 @ 45.95, and its `extended-balance` leg a non-zero `hold_trade`. **A reading that disagrees stops the branch** — the same stop-condition Task 5 Step 1.2 carries, taken here because Tasks 1-4 are otherwise built, reviewed and committed against a fixture whose last reading is the spec's measured-basis table, with a contradiction surfacing only at the attended handoff. This is the only account read before Task 5.

`mint` and `close` must be **validated by the venue**, not merely parsed — and `close` has two possible rejections here that the exit status cannot tell apart, so **read the rejection's reason TEXT, never its status**. A rejection naming the pair, the order type, or `leverage`/`reduce_only` **as a parameter** is a finding to resolve here, not at Task 5. A rejection naming the absence of a position to reduce is **expected at this point and is not a finding**: nothing in Task 4 mints — `mint` runs `--validate` too, and Step 3's empty `before`→`mid` positions diff is the proof of it — so no SOL/EUR margin leg exists to reduce until Task 5 Step 3. Read either way round, the branch pays: on the status alone the benign rejection stops a healthy account, and waved through unread a real parameter rejection is met for the first time at Task 5 Step 7, with a leveraged leg open and rollover accruing. **What this step therefore cannot prove, stated rather than assumed:** that the venue accepts `--reduce-only --leverage 2` for this pair is first provable at Task 5 Step 7, where a position exists — which is why D6 puts the exact netting command in the script rather than leaving it to be typed under that clock. **Family: one member** — `mint --validate` needs no pre-existing state, and Task 5 Step 7's `close --execute` runs with the position open, so this is the plan's only invocation whose object does not yet exist when it runs.

- [ ] **Step 3: Prove the safety default against what a submitted order actually moves**

Read Step 2's four diffs — the `before`→`mid` positions one first, since it is the only one taken while a wrongly-submitted `mint` would still be open — then grep the script for `order buy`/`order sell` and check every occurrence is guarded by the `--validate`/`--execute` inversion. `open-orders` is the control that cannot see this defect and is therefore not the one used: the leg is `--type market`, and a market order that submits **fills** — it appears in `positions`, never in the open-order list. A script whose dangerous mode is reachable by default is the defect this step exists to catch, and a control that cannot see it is how it ships.

- [ ] **Step 4: A SECOND vaulted-key entry point — never a mode on the allowlisted one**

Task 5 must run **this branch's** flatten against the live account, and the host wrapper cannot do it (Global Constraints). `infra/scripts/probe-with-vaulted-key.sh` already puts exactly the two variables `zcrypto engine flatten` reads — `KRAKEN_SPOT_API_KEY`, `KRAKEN_SPOT_API_SECRET` — into an exec'd child's environment. **It is not extended, and it is not touched.**

**Why a mode flag on it is refused, since the cheaper edit looks obviously right.** `.claude/settings.json` carries `"Bash(infra/scripts/probe-with-vaulted-key.sh:*)"` and its `./`-prefixed twin: the grant is **wildcarded on arguments**. Any mode that script gains widens what an already-granted, no-prompt pre-approval authorises. Today no argument to it can cancel or close anything — the harness needs `--apply` **and** `--probe5` and carries its own refusing notional rail. With a flatten mode on it, that one allowlist entry would additionally authorise, unprompted, a program that cancels account-wide and closes every position by design and carries no notional rail at all. Securing the flag so it can never name a path is necessary and **not sufficient**; the question the property never asked is what the grant matches.

- **Create `infra/scripts/flatten-with-vaulted-key.sh`.** Its program vector is hardcoded to `[venv_python, "-m", "cli", "engine", "flatten", *forwarded]` and there is no second target and no mode flag, so it has the original's fixed-**program** property. `-m cli`, not the `zcrypto` console script: the loader `chdir`s to `repo` before exec and `venv_python` is the interpreter it has already validated.
- **A fixed program is not a fixed blast radius, and this one needs its own rail.** The original's target is money-gated *inside itself* — `kraken-order-semantics-probe.py` needs `--apply` before any order reaches the venue, `--probe5` on top of that for the one probe that spends, and its own refusing notional ceiling. This target's write mode is reachable through the very `*forwarded` slot, and it cancels account-wide and market-closes every position by design with no notional rail at all. It also skips both orderings `zcrypto-flatten.sh.j2` performs *before* flatten runs: the kill file written first, then `systemctl stop zcrypto-engine.service` **proven** inactive within 60 s or it refuses — "one key means one client, and a second live client fights the engine over nonces". This script writes no kill file, stops no unit and proves nothing. **So it refuses any forwarded argument equal to `--execute`**, exiting non-zero and naming `sudo zcrypto-flatten --execute` on the engine host as the only supported execute path — that one latches the halt and proves the unit stopped first. The plan's only uses of this script are Step 5's two offline runs and a dry read at Task 5 Step 5, so the rail costs the branch nothing — and Step 5 is where it is seen to trip.
- **Give it NO entry in `.claude/settings.json`, and add none.** No pre-approval exists for it, and none is to be added — an `allow` entry is unconditional pre-approval in *every* permission mode, which is why widening the original's wildcarded grant was the worse edit. What the absence buys is bounded and stated as such: it removes a pre-approval, it does not by itself create a prompt, since whether an un-allowlisted Bash command prompts depends on the session's permission mode and nothing in this repo fixes that. **The gates this script actually carries, all of which hold in every mode**: the `--execute` refusal above; and, on the engine's own path, `flatten`'s `check_kill_file` and the `FLATTEN` word it reads from `/dev/tty` (`cli/engine/flatten.py`). **Do not edit that file at all** — it is not named in `CLAUDE.md`, whose rule is that a config's absence there is the signal not to touch it. Narrowing the existing entry is not the remedy either; leave it meaning exactly what it means today.
- **Duplicate the ~40-line vault loader rather than extracting it, and leave it duplicated.** The judgement, so it is not "improved" later: extraction requires editing `probe-with-vaulted-key.sh` — the one script whose exec vector a wildcarded grant covers — into a form that reads its target from an argument slot of a shared helper, i.e. a program-selecting argument one indirection below the wildcarded layer. Forty duplicated lines in a script with no allowlist entry is the cheaper mistake to make. If the loader is ever changed, both copies change together.
- **Copy `probe-with-vaulted-key.sh` whole rather than writing a header from a list of its properties**, then change the target. Enumerated against the real file rather than counted, because two of the items are one line and a third is a comment — a literal "three things" leaves `harness` defined, still passed, and the rail in prose only:
  1. **The `os.execve` line**, which carries the program vector *and* the forwarded slice together: `[python, harness, *sys.argv[4:]]` becomes `[python, "-m", "cli", "engine", "flatten", *sys.argv[3:]]`.
  2. **Everything that fed the old `$harness` slot**, all of which must go together or the slice above is wrong: the `harness="$repo/infra/scripts/kraken-order-semantics-probe.py"` assignment, its `[ -f "$harness" ]` guard, the `repo, python, harness = sys.argv[1], sys.argv[2], sys.argv[3]` unpack (a two-name unpack now), and `"$harness"` in the trailing `' "$repo" "$venv_python" "$harness" "$@"`. `sys.argv[3:]` is correct **because** of this item: leave `"$harness"` in the trailing list and `sys.argv[3:]` is `['<harness path>', '--state-dir', …]`, so the exec becomes `… engine flatten <harness path> --state-dir …` and click rejects the unexpected positional — a script that cannot run. **No RUN in Tasks 1-4 can see it**: click answers a missing required option before it checks for extra arguments, so with no `--state-dir` forwarded the defect and the correct copy print the same `Missing option '--state-dir'`, and Step 5's runs are all no-`--state-dir` runs. Step 5's `grep -c harness` is what catches this one; its `sys.argv[3:]` grep catches the mirror-image off-by-one — a slice left at `sys.argv[4:]` after the trailing slot is correctly removed, which eats `--state-dir` itself and is invisible to the same runs for the same reason.
  3. **The header's target sentence — and every other mention of the harness in the header**, each of which is false of this target; Step 5's `grep -c harness` is the enumeration, so no count is written here. The header also gains the `--execute` refusal above — and the refusal itself as **code** in the bash preamble, beside the repo-root guard and before the `exec`, so it costs no vault load. A rail that lives only in the header is a comment.

  Copying is what carries the two properties a hand-written header reliably drops, and they are the two that matter if the script is ever edited: *the decrypted values go straight into the exec'd child's environment — never echoed, never written to a file, never on a command line, one process throughout so they never cross a pipe*, and *it refuses outside the repo root, so neither the target nor the vault path can be shadowed* (a bash-preamble guard, not part of the vault loader below it).
- There is **no `--` handling** and none is added: `"$@"` is forwarded verbatim, so a `--` would reach `zcrypto engine flatten` as an argument and click would end option parsing there — measured, `['--', '--state-dir', '/tmp/x']` gives `MissingParameter: Missing option '--state-dir'`. Task 5's command carries no `--`.

Two prose surfaces state `probe-with-vaulted-key.sh`'s single-fixed-target property — `infra/scripts/kraken-order-semantics-probe.py`'s credential refusal and `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`'s "executes a hardcoded target" sentence. **Both stay true and neither sentence is edited**, which is a consequence of leaving that script alone rather than an omission. Step 7 edits three balance renders inside the harness that wrapper execs; the wrapper's own target is unchanged, so both sentences still describe it.

- [ ] **Step 5: Two runs and two greps — offline, venue-free, before it is committed**

The `--execute` rail is a guard, and a guard nothing has tripped is unproven. Step 2 applies exactly this discipline to the sibling script (*"`verify` is read-only and costs nothing to run now … so it must not first execute inside the attended window"*); without this step `flatten-with-vaulted-key.sh` is committed unrun and first executes at Task 5 Step 5, with a minted leg open, rollover accruing and this workstation's IP allowlisted on the trade key.

```bash
bash infra/scripts/flatten-with-vaulted-key.sh             # the true positive
bash infra/scripts/flatten-with-vaulted-key.sh --execute   # the rail
grep -c harness infra/scripts/flatten-with-vaulted-key.sh            # the slice, read statically
grep -c 'flatten", \*sys\.argv\[3:\]' infra/scripts/flatten-with-vaulted-key.sh
```

**All four are main-loop steps, not subagent ones.** The script has no allowlist entry and none is to be added (Step 4), and it decrypts the vault: dispatched, the permission prompt dies where nobody sees it and the step returns a failure that is not about the code, or is skipped as unrunnable — which leaves the script committed unrun, the outcome this step exists to prevent. Same reason `agent-ops.md` keeps host-touching steps in the main loop.

Both runs exit non-zero, so **read WHICH refusal each prints; the status separates neither.** Both greps too: `grep -c` exits 1 on a count of 0, so **read the NUMBER.**

- The no-argument run must reach click and stop at `Missing option '--state-dir'`. That message proves the exec vector and the vault load: a vault that did not load exits on one of the script's own `refusing:` lines instead, and no program vector but `flatten`'s produces click's demand for `--state-dir`. It is equally the rail's **true positive**: a guard that refused this healthy invocation would refuse everything and ship green.
- **It proves nothing about the forwarded slice, and no offline run can** — which is why the two greps carry that half. Click answers a missing required option before it checks for extra arguments, so with no `--state-dir` forwarded, a correct copy, a copy with the `$harness` slot left in the trailing list and a copy with the slice left at `sys.argv[4:]` all print that same one message at exit 2 (measured on all three, against this branch's `zcrypto engine flatten`). Supplying `--state-dir` would separate them — and would also carry a loaded vault straight past click into `flatten`'s body and the venue, which is what this step must not do. So the slice is read from the file: `grep -c harness` is **0** — nothing named `harness` survives the copy, item 2's four sub-edits and the copied header's own harness prose together in one number — and `grep -c 'flatten", \*sys\.argv\[3:\]'` is **1**, pinning the index **on the exec line itself**. The pattern is anchored to that line because an unanchored `sys\.argv\[3:\]` matches the literal anywhere in the file and so pins the token's presence rather than the index the exec uses: a copy whose exec is left at `sys.argv[4:]` and which also carries a comment quoting the index — item 2 above argues at length for why it is 3, which is exactly the invariant a copier records beside the line — returns the identical healthy pair, `harness` 0 and the unanchored count 1, and takes the slice defect into Task 5. Measured on that copy, on the plain `sys.argv[4:]` one, and on the two `$harness` arms — the anchored count is 1 for both of those, so they stay the first grep's to catch. Anything else is the defect, caught here rather than at Task 5 Step 5 with a minted leg open.
- The `--execute` run must print the script's own refusal naming `sudo zcrypto-flatten --execute` as the supported execute path. That it costs no vault load is read from the rail's POSITION in the file — Step 4 puts it in the bash preamble, above the `exec` — never from the terminal: a rail placed below the loader prints the identical refusal, and against an unlocked GPG agent the extra decrypt is silent and fast.

Neither run opens a client, reaches the venue, or writes anything: `--state-dir` is a required `typer.Option`, so click answers before `flatten`'s body — where the credential read and `KrakenSpotHttpClient(...)` are — ever runs.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/kraken-fixture.sh infra/scripts/flatten-with-vaulted-key.sh README.md
git commit -m "feat(scripts): a repeatable Kraken fixture mint, validate-by-default"
```

Drop `README.md` from the `git add` if it gained nothing.

- [ ] **Step 7: Teach the account probe to print the two fields the funding gate keys on**

Spec D2's signal is unmeasured on the account the gate reads, and Task 5 Step 5 is where it gets measured. `infra/scripts/kraken-order-semantics-probe.py` builds its exec client with the same `spot_account_type=AccountType.MARGIN` the engine's does, so it is the one program outside the engine that reads that account — and it renders `.total` alone, which is why the 2026-08-26 record holds no `locked`. **The render is a family of three, not one**, and the same substitution serves all three:

```python
{str(c): str(b.total) for c, b in account.balances().items()}   # before
{str(c): f"total={b.total} locked={b.locked} free={b.free}" for c, b in account.balances().items()}   # after
```

| where | what it feeds |
|---|---|
| `_probe1_read`'s `balances` | probe 1's `observed`, i.e. Task 5 Step 5's reading — the one this branch needs |
| `_probe5_bought`'s `post_buy_balances` | the post-buy `print`, nothing else |
| `_probe6`'s `balances` | probe 6's `observed`, the row `infra/runbooks/order-semantics-verification.md` makes the standard closing read (`--probes 6`) |

**All three, not probe 1 alone**, because the runbook's closing read is what the NEXT adapter bump's record is built from, and `T0160`'s third sub-item is precisely a watch for `locked` becoming real upstream: leaving probes 5 and 6 at `.total` writes that record blind again. Neither of the other two feeds a rail — `post_buy_balances` is printed and dropped, probe 6's `balances` only reaches `observed` — so no verdict, notional ceiling or refusal moves; `grep -c 'locked={b.locked}' infra/scripts/kraken-order-semantics-probe.py` is the completion check — **0 before the edit and 3 after**, which a `b.total` grep cannot say since it returns 3 either way. Probe 1's edit is one line replacing one line at 118 characters against `ruff.toml`'s `line-length = 132`; the other two carry a trailing `if account else {}` and land at 146 and 137, so `ruff format` wraps each into a parenthesised

```python
        post_buy_balances = (
            {str(c): f"total={b.total} locked={b.locked} free={b.free}" for c, b in account.balances().items()} if account else {}
        )
```

— measured by applying the substitution to a copy of the file and running `ruff format --line-length 132` on it: exactly those two lines move, probe 1's stays whole, and nothing else in the file reformats. **Expected there, not a defect**; write the wrapped form directly or let the commit gate produce it. `observed` and the `balances=` print interpolate probe 1's `balances` and are untouched, so the widened reading reaches the terminal, the evidence JSON and the row Task 5 Step 6 appends, from one edit. `AccountBalance` carries all three as `Money` (measured on the pinned wheel: `total=100.00 EUR locked=2.76 EUR free=97.24 EUR` for a `2.757 EUR` hold at EUR precision 2). No venue is reached, and nothing about `--apply`, the notional rail or the credential refusal moves.

Two checks, both offline:

```bash
uv run python infra/scripts/kraken-order-semantics-probe.py --selftest
uv run pytest tests/test_internal_terms_not_operator_visible.py -q
```

`--selftest` runs the pure-logic rails and **reaches none of the three renders** — it is the regression control for the file, never coverage of this edit, and reading it as coverage is the trap here. It reported `SELFTEST PASSED (51 checks)` against the unedited file, so a count that moves is this edit's doing. What covers the edit's shape is the measured render above, taken before the attended window rather than inside it. The second run is why the literal spells `total=`/`locked=`/`free=` and nothing else: `SCANNED_PACKAGES` carries `infra/scripts/`, so a decision token in this f-string is a red on an operator-visible surface.

```bash
git add infra/scripts/kraken-order-semantics-probe.py
git commit -m "feat(scripts): the account probe reads held and free, not the total alone"
```

Its own commit, not folded into Step 6's: a different script, a different subject, and Step 6's message names the fixture mint.

- [ ] **Step 8: Record BOTH pair spellings and the twin count, from the live listing — public data, before the window**

**This is a reading of the twin fix's own INPUT, taken against today's live listing rather than against the 2026-08-04 snapshot the offline arms replay.** Both halves of the pair spelling are public, unauthenticated data — no credential, no allowlist, no window — and the fix's correctness depends on the live `AssetPairs` body carrying an `altname` per row and on the count of rows where it differs from the key being what the design expects. Take it here rather than promising to remember it, and record it beside the offline arms rather than in place of them.

```bash
uv run python - <<'PY'
import asyncio

from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

from cli.snapshot.fetch import fetch_public

BASKET = ("BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "ADA/EUR", "LINK/EUR",
          "DOGE/EUR", "LTC/EUR", "DOT/EUR", "AVAX/EUR", "ETH/BTC", "SOL/BTC")


async def main():
    rows = await KrakenSpotHttpClient("dummy-key", "dummy-secret").request_instruments()
    carried = {str(r.id).removesuffix(".KRAKEN"): str(r.raw_symbol) for r in rows}
    pairs = fetch_public("AssetPairs")
    altnames = {key: row.get("altname") for key, row in pairs.items()}
    differ = [key for key, alt in altnames.items() if alt and alt != key]
    print(len(rows), "listing rows;", len(pairs), "AssetPairs rows;", len(differ), "spelled two ways")
    for symbol in BASKET:
        key = carried.get(symbol, "ABSENT")
        print(f"{symbol:9s} raw_symbol={key:10s} altname={altnames.get(key, 'ABSENT')}")

asyncio.run(main())
PY
```

**Credential-free on both halves, and that is measured rather than assumed**: `test_a_client_call_inside_a_loop_answers_with_an_awaitable_the_module_must_await`, in `tests/test_engine_flatten.py`, already drives that exact client call on `KrakenSpotHttpClient("dummy-key", "dummy-secret")` and asserts a list comes back — its own docstring reads "Only the read-only public listing call" — and `fetch_public` is `GET /0/public/AssetPairs` over stdlib `urllib`, the same endpoint the client itself just hit. This is a one-off measurement and **not** a new test, so it adds no CI surface and no gate.

**What each reading is checked against, all three offline-established and none of them a prediction:** `raw_symbol` is the `AssetPairs` key on every basket leg; `altname` differs from it for exactly the five legs BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR and ETH/BTC; and on the committed 2026-08-04 body **44 of 1429** rows are spelled two ways, with no altname equal to another pair's key and no altname held by two pairs. The live counts will differ — the listing grows — but the SHAPE must hold.

Five outcomes, and one of them stops the branch:

- **The shape holds** — record the twelve rows and the three counts. This is the reading the twin loop's input is expected to have.
- **A basket leg's `raw_symbol` comes back as the ALTNAME** rather than the key — then that leg needs no twin and the map already skips it, so nothing breaks; record it, because it means the venue changed a spelling and `cli/ohlc/fetch.py`'s `PAIR_KEYS` is now wrong too, which is a finding beyond this branch.
- **An `altname` missing from a row** — `read_altnames` skips such a row by construction (`row.get("altname")`), so that pair gets no twin and stays visible only under its key. Record which rows, and whether any is a basket leg.
- **An altname that equals another pair's key, or one held by two pairs** — the collision the offline probe measured as **non-deterministic** in the scan (~50/50) and found absent from the committed listing. **This one stops the branch**: a colliding twin makes an order report resolve to an arbitrary one of two instruments, and no code in this plan would say so. Record it and take it to the owner before Task 5.
- **The call failing** — record it as **not taken**, never as a value; a null read as agreement is the failure this whole spec exists to eliminate.

```bash
git add docs/reference/adapter-verification/2.0.0rc4.dev20260825.md
git commit -m "docs(adapter_verification): both pair spellings the listing carries, per basket leg"
```

Recorded there rather than in the spec because it is a measurement of the pinned build against the live listing, and that file is where this repo keeps those. Task 5 Step 6's row cites it rather than repeating the values. **Task 2 Step 8's fixture rows come from this same public endpoint**, taken earlier in the branch; if the two readings disagree on any of the six, the fixture is stale and that is a finding to resolve here, not at the window.

---

### Task 5: 🅿️ ATTENDED — mint the position and take the readings only the venue can give

**This task requires the owner.** It places a real, filling order. Everything buildable is already done; this is the single handoff.

**Its scope is smaller than it was, and the shrink is stated so the window is not spent proving what is already proven.** Task 2 Step 8 discriminates the cache mechanism offline, on both spellings, for orders and positions alike — 0 of 6, 1 of 6, 6 of 6, plus the six position branches — so this window is no longer where the fix is decided. **What only the venue can settle, and therefore what this window is for:**

1. **The gate's own account** — `total`/`locked`/`free` on the exec client's `MARGIN`-typed account, taken with the minted position open and again with it closed. Nothing in this repo has ever read it, no offline run can, and spec D2's whole signal is assumed on it. This is the window's first purpose and the one that can stop the branch.
2. **The engine's own resting-order count** — `cache.orders_open(venue=KRAKEN)` on a live node, the count D2's refusal keys on. A cold node cache makes the guard inert, and nothing offline can say whether the node's cache is cold.
3. **That flatten's twin path survives the real venue** — the real listing rather than six replayed rows, the real `AssetPairs` body behind the altname fetch, the real credential, the real account. An end-to-end run, not a discrimination.
4. **The close path against a position the venue actually opened**, including that the venue accepts the exact `--reduce-only --leverage 2` netting order flatten itself would send.

**What this window is NOT for, and what a reading here cannot decide.** The `SOLEUR` order count moves 0→2 with the twins and without them, so it corroborates and never discriminates; the same is true of the minted position, which is `SOL/EUR`. Neither is evidence about the twin, and the row at Step 6 says so in its own words. If a reading here contradicts an offline arm, the contradiction is the finding — one of the two is measuring something other than what it claims — and it stops the branch rather than being averaged.

- [ ] **Step 1: Pre-flight, immediately before**

Four checks, all before anything is opened or minted — and the fourth is a reading, not a gate:

1. Read the Kraken maintenance feed matching on **name OR components**; confirm no REST/WebSocket window is open or imminent.
2. Run `bash infra/scripts/kraken-fixture.sh verify` and confirm the two resting limits (`OZRI5U-U7WGD-OYCOMW`, `OVNLAJ-6PXBH-T4GDXF`) are still there, still 0.06 @ 45.95, and still far below market. **A reading that disagrees stops the branch** — every decision in the spec rests on that fixture, and it has been unattended since 2026-09-01.
3. **Confirm the engine cannot submit.** Both commands literally, on the engine host — the CLI lives only inside the container, so a bare `zcrypto …` is `command not found` there:

   ```bash
   sudo docker exec zcrypto-engine zcrypto engine exec-status   # expect level=none
   sudo ls -la /var/lib/zcrypto-engine/exec/                    # expect no probe-plan.json
   ```

   `exec-status` is read-only and prints `level=`, `reasons=` and every gate input, but it reports **nothing about a staged plan**, which is why the second command exists rather than being folded into the first. Step 5 opens a second authenticated client on the same key while a real position is open and this workstation's IP is allowlisted — the one window in this branch where an engine order or cancel rejected on a nonce would land beside a live position. If the engine may submit, stop: this is a check, not a formality, and the rest of the task reads it as already taken.

4. **Take the order A/B's cold arm now, because after Step 3 mints the position it can no longer be taken.** On the engine host, `sudo zcrypto-flatten` with no arguments — the deployed digest's dry run, read-only, sending nothing. Expect `0 resting order(s) will be cancelled account-wide` beside the two limits check 2 has just seen at the venue, and record it for Step 5's A/B. With a margin position open this same command is expected to abort at exit 3 before it prints any count (Step 5 says why), so a cold order count taken later would not exist.

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

**The fix is read from this worktree, never from the host wrapper** — the wrapper execs the deployed digest, which predates this branch, so on its own it returns the same empty list the defect returns and a green from it would be indistinguishable from a failed fix. That is precisely why it serves below as the *pre-fix arm* and never as the proof. Run the dry run from this worktree with the vaulted key, through Task 4 Step 4's new entry point:

```bash
bash infra/scripts/flatten-with-vaulted-key.sh --state-dir <a scratch dir>
```

It has no allowlist entry, and none is to be added — if the session prompts, that is the design (Task 4 Step 4) and not a misconfiguration to route around. No `--execute`: the script refuses it outright (Task 4 Step 4), and the supported execute path is `sudo zcrypto-flatten --execute` on the engine host. And **no `--`** — the script forwards `"$@"` verbatim, so a `--` would reach click and end option parsing before `--state-dir` (Task 4 Step 4). The read shares the trade key with the running engine — the same accepted exposure `zcrypto-flatten`'s own dry-run banner names — and the engine was **confirmed** unable to submit at Step 1.3, not assumed to be.

Four readings, then the one deliberately not taken:

- **Orders — the A/B is across CODE VERSIONS, not across cache states within one run.** A post-fix flatten performs exactly one order read, so there is no cold arm inside it; and flatten prints a count, never a txid (Global Constraints). So take both arms:
  - **cold / pre-fix, run TWICE and the order matters**: on the engine host, `sudo zcrypto-flatten` with **no arguments** — a dry run that reads the account, prints the plan and sends nothing. It execs the deployed digest, whose flatten predates this branch, which is exactly what makes it the control here rather than a hazard. Checkable before running it: `git show 8f4ac521:cli/engine/flatten.py | grep -c cache_instrument` is **0** for the revision `docs/reference/fleet-pins.md`'s engine row names.
    - **For the order count — taken back at Step 1.4, because after Step 3 it cannot be taken at all.** Expect `0 resting order(s) will be cancelled account-wide` against the two fixture limits `kraken-cli` has just named. See the second run for why the position makes this reading unobtainable.
    - **After the mint, for the position read.** With a margin leg open, this arm is expected **not to print a plan at all**: the offline harness measured that a cold-cache position read RAISES on any position the venue reports, so the deployed button should abort at **exit 3** on `margin positions could not be read: OpenPositions: instrument not in cache for pair …`. That is the pre-existing live defect this branch resolves, observed on production's own binary and on the real venue — the one reading in this window that confirms an offline finding against the deployed artifact, and worth the second dry run for exactly that. **If it prints a plan instead, that is a finding**: the offline model of this read is wrong somewhere, and the branch stops until that is understood. Record whichever it does, verbatim.
  - **warm / this branch**: the worktree command above. Expect `2 resting order(s) will be cancelled account-wide` — **and expect NO degradation line**. `run_flatten` says one when the alternate-names fetch failed and one when a listing row could not be cached (Task 2 Step 3); neither appearing is the only evidence this run has that the altname map was actually read against the live venue and that every twin the live listing calls for was minted. Record their absence explicitly: an absence nobody looked for is not a reading. If either line appears, the run is a degraded one — record it as such, and it is not the warm arm.
  - **identity**: from `bash infra/scripts/kraken-fixture.sh verify`'s `open-orders` read, taken between the two arms — the non-adapter witness naming both fixture txids. The count moving 0→2 against an unchanged witness is the discriminator; either arm alone reads the same whether the defect is present or not, which is how the earlier version of this defect was retracted.
- **Positions: the minted long present in the warm run's plan, by symbol and by the CLOSING side that corresponds to it.** Never side-equality: `render_plan` prints no position's own side. `margin_legs` maps the position to its closer — `sides = {"LONG": "SELL", "SHORT": "BUY"}` — and `_leg_line` renders that mapped value, so the minted long appears as `  margin SOL/EUR SELL 0.06000000 -- market, reduce-only, …` beside a `kraken-cli` `positions` row that says long. The two surfaces disagree by construction on that field and the mapping is the reconciliation; a `BUY` there would be the finding, because it is what an inverted side produces. (A position's own side reaches the terminal only through `plan.unclosable`, which is the failure branch: a row printed there is a position flatten could size no closer for, and is itself a stop.) **The minted leg is `SOL/EUR`, whose two spellings coincide, so this reading is the real-venue corroboration and not the discriminator** (spec D4/D5): what the close path does on a legacy-coded pair — under the key, under the altname, with and without the alias — is Task 2 Step 8's six measured branches, and this run cannot add to them. What it does add is that the venue's own `OpenPositions` body parses, that the position the venue actually opened reaches `margin_legs`, and that the closer flatten would send is the one the account needs.
- **The engine's own view of the resting book.** D2's `resting_orders` comes from the Cache the node's reconciliation fills through this same adapter, so a cold node cache makes the guard inert. Read it directly, through the probe wrapper this branch leaves unchanged (Task 4 Step 4 refuses to touch it; the harness it execs gains three widened balance renders at Task 4 Step 7 and nothing else): `bash infra/scripts/probe-with-vaulted-key.sh --probes 1,2 --evidence-dir /tmp` — read-only without `--apply`, and probe 2 prints `open orders N` plus one `pre-existing open order:` line per order from `cache.orders_open(venue=KRAKEN_VENUE)`, which is the exact surface `_pickup` counts. Expect the two fixture orders listed and the probe's own verdict **REVIEW**, which is what it records when the account carries pre-existing state — here that verdict is the reading wanted, not a failure. `open orders 0` is the finding: it would mean the node's cache is cold the way flatten's was and D2's guard ships inert. **`open orders 2` is a reading about `SOLEUR` and about no other spelling, and here that limit is load-bearing rather than cosmetic** — the two fixture orders are both `SOL/EUR`, whose key and altname coincide, so they resolve on the node's cache under either spelling. The five legs that do not coincide include both legs of the T2 set RUNG 1 opens first, and **no twin of flatten's reaches this client**: `prime_cache` runs inside the red button, on the button's own `KrakenSpotHttpClient`, while the node builds its own. So this count says the Cache's order index is not empty and the reconciliation read reached the venue; it says nothing about whether that read can see an `XXBTZEUR`-coded order, which is exactly the question `T0160`'s cancel-sweep sub-item holds. The row at Step 6 says so in those words. This is the live half; the offline half is Task 3 Step 2's three `_pickup` tests, and neither substitutes for the other. `--evidence-dir` is not decoration: it defaults to the cwd, the wrapper `chdir`s to the repo root immediately before `exec`, and the harness's own help says to pass a path outside the repo — without it an untracked `evidence-*.json` lands in the working tree, invisible to Step 9's `git add`. **The selection is `1,2` and not `2`** — one invocation, two readings, because probe 1 is the only surface in this selection that reads the account the next bullet is about, and a second invocation is a second client on the trade key for no gain. (Probes 5 and 6 read the same account object — Task 4 Step 7 widens all three renders — but 5 spends and 6 is by its own note a separate invocation, so neither is reachable here.)
- **The gate's own account — the reading D2 keys on and nothing has ever taken.** Probe 1 of the same invocation reads `self.portfolio.account(KRAKEN_VENUE)` and, after Task 4 Step 7's widening, prints `total=`/`locked=`/`free=` per balance. That account is the exec client's, and the harness builds its client `spot_account_type=AccountType.MARGIN` exactly as `node.py` builds the engine's — so it is the account `venue_state_from_cache` reads and `plan_refusals` receives, and not the `CASH`-typed one flatten's `locked == 0` came off (spec D2). **Three outcomes, decided here and not on the day, and only one of them lets the branch continue:**
  - **every balance reports `locked` 0** — the signal holds on the path the guard runs on. Record the figures; continue.
  - **any balance reports `locked > 0`** — the conjunct that releases D2's refusal is already satisfied, so the funding gate ships inert on the arming path and D3's line fires on every pickup. **Record the figures, then STOP before Task 6**: the refusal is re-keyed, or this branch does not close out. **The recording is not conditional on the verdict** — this is the account reading nothing in the repo has ever taken, and it is exactly the reading a re-keying would be designed against, so a stop that ends the session without it costs another attended window to retake (spec D2 says the same). It is not a number to weigh against the offline tests, every one of which passes a map by hand and can see none of this.
  - **no reading at all** — probe 1 records `no AccountState arrived`, or the invocation dies. Record it as **not measured**, and treat it as the stop above: reading a null as the zero that confirms the design is the exact failure this spec was written to eliminate.

  **Taken with the minted position OPEN**, and taken again at Step 7 once it is closed. The two are not the same question, and the recorded shape of this account is why: `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`'s Observation 2 reports, **on this very pin**, "a single figure keyed `EUR`, not per-asset wallet balances — `{'EUR': '99.67730000 EUR'}` under `spot_account_type=MARGIN`", and `1.230.0.md` named the same shape for an older version as **TradeBalance-derived equity in `margin_balance_asset`**; on an account of that shape `locked` moves with margin in use rather than with an order's hold. Neither record measured `locked`, so the shape is measured on the pinned build while the figure this step reads is not, which is what makes the open/closed pair a discriminator rather than a repeat. Open-then-closed, against a spot order that rests throughout, is the one pair of readings this fixture can separate those two causes with — and the second costs one extra read-only invocation inside a window that is already open.

- **No fills leg.** Nothing in `cli/` reads fills — `request_fill_reports` appears in no file under `cli/`, `tests/` or `infra/` — so the named run produces no fill row to assert on, and the committed record holds order txids (four of them `filled_qty=0.0`), not fill identities. Spec D4 records the drop and its reason.

- [ ] **Step 6: Record the row**

Append the verification row to `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`, carrying **both** order-count arms (the deployed pre-fix count taken at Step 1.4, and this branch's), the **deployed button's behaviour with a position open** — the exit-3 abort the offline harness predicts, or the plan it printed instead — the warm arm's position line verbatim, the probe-2 `open orders` count, the probe-1 `total=`/`locked=`/`free=` reading with the position OPEN, the `kraken-cli` readings beside them, and a plain statement that fills were not exercised. A row holding only the warm arm records a number nobody can tell from the defect's; a row holding only the order counts throws away the deployed button's position reading, which is this window's only observation of that defect on the artifact that is actually running. The probe-1 reading is appended to rather than replaced at Step 7, which takes the same reading with the position closed — the row carries both, each labelled with the state it was taken in, or neither can be read. **If positions come back empty, that is the finding — stop, and do not ship a fix that cannot see the close path.**

**The row states what the readings do NOT cover, in the row itself and not only in the spec.** Every count and every position line here is read on `SOL/EUR`, whose two Kraken spellings coincide; five of the twelve basket legs are spelled two ways, and both legs of spec `00090`'s T2 set — the first pairs RUNG 1 opens — are among the five (spec D4 carries the enumeration). So the row says in its own words: that these are **corroborations on the real venue and not discriminations**, the discrimination being the offline arms a committed test carries; that the twin fix's coverage of the five two-way legs is established there and not here; that the twin count and both spellings per basket leg are Task 4 Step 8's recorded live reading; and that the probe-2 `open orders` count is a reading about the ENGINE's cache, which no twin of flatten's reaches, leaving `T0160`'s cancel-sweep question exactly where it was. Without those sentences the row reads as coverage of the basket, which is what a later reader — and `T0160` — would take it for.

- [ ] **Step 7: Close the minted position, deliberately**

The margin leg accrues rollover.

```bash
bash infra/scripts/kraken-fixture.sh close --execute
```

**Confirm closure on a POSITIVE trace, because the obvious check cannot be satisfied here.** A successfully closed leg produces no `positions` row, so "by symbol and side" — correct at Step 4, where the position must be PRESENT — has nothing to match at Step 7, where it must be ABSENT, and the only reading the venue can return is the empty one that is also what a read failure, a rejected `reduce_only` or an IP-allowlist error returns. Take the trace the close itself produces, then use the absence only as corroboration:

```bash
export PATH="$HOME/.cargo/bin:$PATH"   # the one bare `kraken` call in Task 5
txid=<the txid the close's own `-o json` printed -- paste it, this line is not optional>
kraken query-orders "$txid" -o json
bash infra/scripts/kraken-fixture.sh verify
```

**Assign `txid` before running the query, not after reading it.** `[TXIDS]...` is optional in `kraken query-orders [OPTIONS] [TXIDS]...`, so an unset variable expands to an empty argument and the call parses, reaches the venue and answers about no order — a reading that "does not say closed", which this step's own stop-condition reads as *the position is still open*, on a position that is in fact closed and under the rollover clock.

`query-orders` must report that order `closed` and fully filled — that is the reading no failed submission can produce. `verify` then supplies the corroboration in one read: `positions` empty, and `extended-balance` moved back toward its pre-mint value. It is used rather than a hand-typed `kraken positions -o json` for the same reason as Steps 2 and 4 — the spec makes this subcommand the witness — and it needs no PATH prefix, which is why the export above is scoped to the one bare call beside it. **If `query-orders` does not say closed, the position is still open** — that is a stop, not a reading to average against the empty `positions` list. **And the recourse is not another close through this branch's path**: a venue that rejected `--reduce-only --leverage 2` for this pair (the acceptance Step 2 of Task 4 records it cannot prove until here) rejects `sudo zcrypto-flatten --execute` for the same reason, since flatten closes margin legs with that same reduce-only market order. Close the leg by hand with Kraken's own settle-position action in the web UI — the close no order can send, which `infra/runbooks/engine-procedures.md` already names for the below-minimum remainder. **Leave the two original resting orders untouched**; `verify`'s `open-orders` leg is where that is read.

**Then take the account reading again, with the position closed and the spot order still resting:**

```bash
bash infra/scripts/probe-with-vaulted-key.sh --probes 1 --evidence-dir /tmp
```

Read-only, no `--apply`. **Re-run Step 1.3's two commands immediately before this one** — `exec-status` and the `exec/` listing, both read-only and both seconds — because Step 1.3 was a point-in-time reading and this is the window's third authenticated client on the trade key, opened after the allowlist was widened, a leg minted, a flatten dry run taken, the first probe run and a `close --execute` submitted. The guarantee Step 1.3 bought was scoped to Step 5's invocation; nothing between then and here re-read the arming state, and a nonce-rejected engine order landing beside live account state is what the check exists to exclude. This is the second half of Step 5's account bullet and it is what separates the two causes of a non-zero `locked`: a hold the venue placed against the resting spot order, or margin in use by a position that no longer exists. Its three outcomes are Step 5's, unchanged — including that a reading which could not be taken is recorded as **not measured** and never as a zero — with one addition this state makes available: `locked > 0` here, with no position open, is a hold, and `locked` falling to 0 between the two readings says the figure tracked the position and not the order. **Append both readings to the Step 6 row before Step 9's commit**, each labelled with the state it was taken in. Run it only after `query-orders` has said `closed` — a probe started against a position that is still open answers the Step 5 question over again and not this one.

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

Load the `iteration-closeout` skill; append to `docs/iterations-history-phase6.md`. State what was proven **offline** (the three cache arms and the six position branches, in CI, on both of the venue's spellings), what was corroborated **live** and on which single pair, and what was not verified at all — the engine's own instrument cache, which no part of this branch touches.

- [ ] **Step 2: Update the topics**

`T0159` gains the cache finding — **both halves of it**, the empty cache and the second spelling the cache is scanned by, since a reader who takes away only "flatten now caches the listing" has the version that returns 1 of 6 — and its exit-code contract bullet — which restates exit 3 as "the venue could not be reached or read" — is re-tensed to the widened wording Task 2 Step 3 landed on the surfaces under `cli/`, `infra/` and `README.md` (that step's own table is the enumeration; no count is restated here, so the two cannot disagree). That bullet is the only restatement of the clause under `docs/` that is a live record rather than a point-in-time one; spec `00106` and `docs/iterations-history-phase6.md` keep theirs.

**`T0160`'s four `00111` sub-items are already registered** — spec D7's two upstream reports and the `_classify_spot_close` fail-open D2 leaves standing, each with its own `ripe_when`, landed when the spec asserted them rather than deferred to here, because the spec claims them in the present tense and a claim that is not yet true is the failure the registration rule names; plus the cancel-sweep blind spot, which is not a spec decision but the second consumer of D7's first defect. So this step **re-reads** them against what the branch actually did and re-tenses anything the implementation moved — it does not add them again. The fourth is the one whose re-read has to be taken against the tree the branch PRODUCED rather than the one it started from: its consumer enumeration counts `executor._pickup`'s `resting_orders`, a reader Task 3 Step 4 adds, so a re-read against `develop` reports it wrong by one. Register no **new** topic without the approver's word (`zcrypto-main` holds that call).

**Three edits inside those sub-items that the branch's own work makes owed, all re-tensings and none a new registration:**

- The first upstream report — the silent order-report drop — gains the two things this branch measured that make it a report a maintainer can act on without an account: a **credential-free reproduction** (the loopback harness of `tests/test_engine_flatten_offline_venue.py`, which shows 0 / 1 / 6 rows across three cache states), and the **in-file inconsistency** that is its own strongest argument — `request_position_status_reports` answers the identical instrument-cache miss with `RuntimeError: OpenPositions: instrument not in cache for pair …`, while the order read drops the row and returns success. The ask is unchanged and the `ripe_when` is unchanged; what changes is that the report no longer rests on a source read of a revision the wheel does not carry.

- The first sub-item quotes `locked is no longer zero` as the literal its arm watches for. Task 3 Step 4 does not write that literal — the announcement says what it read rather than that anything changed (spec D3) — so the quote is re-tensed to the text that landed, read from `cli/engine/probeplan.py` rather than from this plan. This is the last member of the family Task 3 Step 4 enumerates; that step carries the completion grep, and this plan is outside its roots because it quotes the superseded wording on purpose.
- The fourth is re-tensed HARDER than it was drafted, because the branch settled the spelling question and in doing so made that sub-item's own hazard concrete rather than conjectural. What is now measured, offline and credential-free: the cache is scanned by the listing row's `raw_symbol`, which is the `AssetPairs` **key**; an order report is looked up by its own `descr.pair`, which is the **altname**; and on six legs a cold cache returns 0 rows, a key-only cache 1, and a key-plus-twin cache 6. Flatten closes that for itself with `prime_cache`. **The engine does not get the fix**: `prime_cache` runs inside the red button on the button's own client, `node.py` builds its own, and nothing in this repo caches an instrument into it — so a reconciliation read on that client is blind under *whichever* of the two conditions holds, cold cache or listing-only cache, and the three Cache consumers the sub-item already enumerates inherit it. So the sub-item stops asking which spelling the lookup keys on — that is answered — and asks the two questions that remain: whether the exec client's cache is populated at all before reconciliation reads through it, and, if it is, whether it carries the second spelling. Its `ripe_when` is unchanged: the same attended engine start with a resting order the starting process did not place still settles it, and it settles it better now, because the pair to rest it on is a **two-way-spelled** leg (`BTC/EUR`, `ETH/EUR`, `XRP/EUR`, `LTC/EUR`, `ETH/BTC`) rather than any leg at all — a `SOLEUR` order would resolve under either condition and prove nothing, which is the same degenerate control this whole spec exists to refuse. Read the outcome from the record, never from this plan.

**Then reconcile the QUEUE, which registration alone does not do.** The memo's topic-closure line schedules `T0160` for `resolved` at the nautilus-bump item. That milestone satisfies the bump leg's trigger and **none** of the first three `00111` sub-items': the two upstream reports become ripe when 00111's listing-cache commit is on `develop`, and the `_classify_spot_close` item when the pinned `nautilus_trader` carries the `BalanceEx` read or a `REDUCE_ONLY` spot disposal is planned — the bump is to a nightly that still carries the defect the reports are about. The fourth is the one to **evaluate** at that milestone rather than assume unripe: its second arm fires on an attended engine start with an order resting at the venue that the starting process did not place, which is a condition the bump's own work can create rather than one only a third party can. Taking the topic to `resolved` there would archive a live deferred sub-item on the live trade path, which `.claude/rules/open-topics.md` forbids outright, and it would remove the only registration of a fail-open this branch knowingly left standing. **Amend that closure line here**: the bump item closes `T0160`'s bump leg only, leaving the topic `partial` while the four sub-items stand. Registration and queue insertion travel together; a topic scheduled to be archived before its own triggers can fire is invisible at pick time either way.

- [ ] **Step 3: Commit the closeout**

```bash
git add docs/iterations-history-phase6.md docs/open-topics/
# <N> is read from docs/iterations-history-phase6.md at closeout -- it is not knowable now.
git commit -m "docs(closeout): iter-<N> -- 00111's blind reads, fixed and verified live"
```

- [ ] **Step 4: Whole-branch review at the Fable floor, then PR**

Closeout is the branch's END, so it commits **before** the PR opens: re-verify the entry and every status claim against the full branch log, then `infra/scripts/review-trailer-audit.sh develop` must PASS before push, then PR into `develop` via the `open-pr` skill — whose trailer aggregation would otherwise be regenerated after the fact.
