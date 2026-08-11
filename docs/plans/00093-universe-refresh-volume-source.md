# The universe refresh's volume source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `_refresh_universe` a source that reaches the present for all twelve candidate symbols, make a narrower source refuse instead of silently shrinking the universe, and publish the artifact as a stamped set so an additive-only transport can express a second version.

**Architecture:** Four independent seams. `PAIR_KEYS` becomes symbol-keyed so one base can carry two quotes; `reach.py` becomes quote-aware on its glob, its read/write paths and its manifest; `_refresh_universe` gains a presence guard over `CANDIDATE_SYMBOLS`; and the canonical artifact becomes `universe-<stamp>/` sets resolved newest-wins, using the sibling naming `rebuild_sets` already mints and the `extra_sets` parameter `push_hot` already takes.

**Tech Stack:** Python 3.14, uv, polars, Typer. No new dependency.

## Global Constraints

- **Symbol identity is the full `BASE/QUOTE` string** (`"ETH/EUR"`, `"ETH/BTC"`) everywhere this plan touches. A base-keyed structure cannot express two quotes for one base — that is the defect being fixed, so do not reintroduce it.
- **The venue spells it `XBT`; we spell it `BTC`.** Pair keys are `XETHXXBT` / `SOLXBT` with `wsname` `ETH/XBT` / `SOL/XBT`. Any match on the venue's spelling without normalising produces a false negative that looks exactly like "the legs do not exist".
- **The engine CONSUMES `cli.ohlc.fetch.PAIR_KEYS`** — `cli/engine/store.py` imports and re-exports it to `cycle.py`, `soak.py` and the package root. An earlier draft of this constraint claimed the opposite; it was wrong, and the error came from a grep piped through `head` that dropped the `store.py` import. **Sweep without truncating.** Re-keying it unqualified widens the engine's basket from ten EUR legs to twelve and breaks its store paths, so Task 1 must land the derived EUR-only view in the same commit.
- **Never write through `/mnt/zhao-crypto`** — it is a read-only NFS mount. Read datasets in place.
- **Additive-only sync is a property, not an accident** (spec `00056`): `rsync --archive --ignore-existing`, never `--delete`. No task may add a delete, and no task may make a same-named artifact mutable on the hub.
- **A guard is unproven until the defect it names is constructed and seen to trip it.** Every refusal in this plan needs a test that builds the bad state.
- Commit gate is `uv run pre-commit run -a`, run to clean, hook rewrites re-staged, never `--no-verify`. Stage by explicit path.
- Review floor is **Fable** for every commit — this touches canonical data.

---

## Which task discharges which decision

| Spec decision | Task |
| --- | --- |
| D1 — extend reach to the BTC-quoted legs | 2 (with the pair keys from 1) |
| D2 — `PAIR_KEYS` re-keyed by full symbol | 1 |
| D3 — manifest `series` keyed by full symbol | 2 |
| D4 — a narrower source refuses | 3 (guard) + 3a (pointed at the resolved root) |
| D4a — the source is resolved newest-wins | 3a |
| D5 — stamped set, resolved newest-wins | 4 (read side) + 5 (publish side) |
| D6 — the Markdown stays single and git-versioned | 6 (closeout) + the attended sitting |

---

## File Structure

| File | Responsibility |
| --- | --- |
| `cli/ohlc/fetch.py` | *modify* — `PAIR_KEYS` re-keyed by full symbol, plus the two BTC-quoted legs |
| `cli/ohlc/reach.py` | *modify* — quote-aware discovery, read/write paths, manifest entries; correct a false docstring |
| `cli/data/rebuild.py` | *modify* — the `CANDIDATE_SYMBOLS` presence guard in `_refresh_universe` |
| `cli/capture/command.py` | *modify* — resolve the newest stamped universe set, legacy fallback |
| `cli/data/sync.py` or its caller | *modify* — publish the stamped sibling via `push_hot`'s existing `extra_sets` |
| `tests/test_ohlc_reach.py`, `tests/test_data_rebuild.py`, `tests/test_capture_command.py`, `tests/test_data_sync.py` | *modify* — find the real filenames first; do not create parallel files |

---

### Task 1: `PAIR_KEYS` re-keyed by full symbol

**Files:**
- Modify: `cli/ohlc/fetch.py`
- Modify: every consumer found by grep (expected: `cli/ohlc/reach.py` only, within `cli/`)
- Test: the existing fetch/reach test files

**Interfaces:**
- Produces: `PAIR_KEYS: dict[str, str]` keyed `"BASE/QUOTE"` → Kraken pair key, with 12 entries.

- [ ] **Step 1: Find every consumer before changing anything**

Run: `grep -rn 'PAIR_KEYS' cli/ tests/`
Record the hits. `cli/engine/cycle.py` and `cli/engine/store.py` are a **different** `PAIR_KEYS` and must not be edited. If a consumer outside `cli/ohlc/` imports from `cli.ohlc.fetch`, stop and report — the spec measured the blast radius as `reach.py` only, and a wider one is a finding.

- [ ] **Step 2: Write the failing test**

Add to the fetch tests:

```python
def test_pair_keys_are_symbol_keyed_and_cover_every_candidate():
    from cli.ohlc.fetch import PAIR_KEYS
    from cli.snapshot.assetpairs import CANDIDATE_SYMBOLS

    assert all("/" in k for k in PAIR_KEYS), "PAIR_KEYS must be keyed BASE/QUOTE, not by base alone"
    missing = [s for s in CANDIDATE_SYMBOLS if s not in PAIR_KEYS]
    assert missing == [], f"no REST pair key for {missing}"


def test_the_btc_quoted_legs_carry_the_venues_xbt_spelling():
    # The venue spells it XBT and we spell it BTC. A key that reads "...BTC" would be wrong.
    from cli.ohlc.fetch import PAIR_KEYS

    assert PAIR_KEYS["ETH/BTC"] == "XETHXXBT"
    assert PAIR_KEYS["SOL/BTC"] == "SOLXBT"
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/ -k pair_keys -v`
Expected: FAIL — keys are currently bases (`"BTC"`, `"ETH"`, …), so the `"/" in k` assertion fails on every entry.

- [ ] **Step 4: Re-key the map**

In `cli/ohlc/fetch.py`, replace the ten base keys with twelve symbol keys:

```python
# Keyed by FULL symbol, not by base: ETH and SOL each carry two quotes, which a base key cannot
# express. Kraken spells bitcoin XBT in both the pair key and the wsname; our symbols say BTC.
PAIR_KEYS: dict[str, str] = {
    "BTC/EUR": "XXBTZEUR",
    "ETH/EUR": "XETHZEUR",
    "SOL/EUR": "SOLEUR",
    "XRP/EUR": "XXRPZEUR",
    "ADA/EUR": "ADAEUR",
    "LINK/EUR": "LINKEUR",
    "DOGE/EUR": "XDGEUR",
    "LTC/EUR": "XLTCZEUR",
    "DOT/EUR": "DOTEUR",
    "AVAX/EUR": "AVAXEUR",
    "ETH/BTC": "XETHXXBT",
    "SOL/BTC": "SOLXBT",
}
```

- [ ] **Step 5: Keep the engine's basket at ten legs, by derivation**

This is the load-bearing half of the task. In `cli/engine/store.py`, replace the re-export with a derived view and keep the name the engine already imports:

```python
from cli.ohlc.fetch import PAIR_KEYS as _FETCH_PAIR_KEYS

# The engine trades EUR legs only. Derived from the one source of truth rather than duplicated,
# and keyed by BASE because the store path is root/<base>/EUR/<interval>.parquet. Without this the
# symbol re-key would silently widen the engine basket from 10 to 12 and produce paths like
# root/ETH/BTC/EUR/1440.parquet.
PAIR_KEYS: dict[str, str] = {
    symbol.split("/")[0]: key for symbol, key in _FETCH_PAIR_KEYS.items() if symbol.endswith("/EUR")
}
```

- [ ] **Step 6: Pin the derivation so a future leg cannot leak in**

```python
def test_the_engine_basket_stays_eur_only_and_ten_legs():
    from cli.engine.store import PAIR_KEYS as ENGINE_KEYS
    from cli.ohlc.fetch import PAIR_KEYS as FETCH_KEYS

    assert len(ENGINE_KEYS) == 10
    assert all("/" not in k for k in ENGINE_KEYS), "engine keys are BASE, its store path appends /EUR"
    assert "ETH" in ENGINE_KEYS and ENGINE_KEYS["ETH"] == FETCH_KEYS["ETH/EUR"]
    # A BTC-quoted leg must never reach the engine, however the fetch map grows.
    assert not any(k.endswith("XBT") for k in ENGINE_KEYS.values())
```

- [ ] **Step 7: Update the two tests that pin the old shape**

`tests/test_engine_store.py::test_pair_keys_content` pins the 10-entry base-keyed dict — it now describes `cli.engine.store.PAIR_KEYS`, which is still correct, so verify rather than assume it needs changing. `tests/test_tape_bars_rest_control.py` uses `PAIR_KEYS["BTC"]` at module level and will KeyError **at collection** if it imports from `cli.ohlc.fetch`; point it at the engine map or use `"BTC/EUR"`, whichever matches its intent. Read both before editing.

- [ ] **Step 8: Update every other consumer found in Step 1**

`cli/ohlc/reach.py`'s `PAIR_KEYS.get(symbol)` already passes whatever `_canonical_symbols` yields — Task 2 makes that a full symbol, so this call site becomes correct then. Do not change it here.

- [ ] **Step 9: Run the tests**

Run: `uv run pytest tests/test_engine_store.py tests/test_tape_bars_rest_control.py -v` first (the collection-time KeyError lives there), then `uv run pytest tests/ -k 'pair_keys or fetch or reach' -v`
Expected: the two new tests pass. Reach tests may fail — Task 2 fixes them; note which, do not patch them here.

- [ ] **Step 10: Commit**

```bash
git add cli/ohlc/fetch.py cli/engine/store.py tests/
git commit -m "refactor(ohlc): key PAIR_KEYS by full symbol and add the BTC-quoted legs"
```

---

### Task 2: `reach.py` becomes quote-aware

**Files:**
- Modify: `cli/ohlc/reach.py` (`_canonical_symbols`, `reach_round`, `_write_manifest`)
- Test: the existing reach test file

**Interfaces:**
- Consumes: `PAIR_KEYS` symbol-keyed (Task 1).
- Produces: reach output at `out_root/<BASE>/<QUOTE>/<interval>.parquet`; manifest `series` entries whose `symbol` is the full `BASE/QUOTE`.

- [ ] **Step 1: Write the failing tests**

Build a canonical fixture carrying BOTH quotes for one base — that is the case the current code cannot express:

```python
def test_reach_discovers_both_quotes_of_a_base(tmp_path):
    from cli.ohlc.reach import _canonical_symbols

    for leg in ("ETH/EUR", "ETH/BTC", "ADA/EUR"):
        base, quote = leg.split("/")
        d = tmp_path / base / quote
        d.mkdir(parents=True)
        (d / "1440.parquet").touch()

    assert _canonical_symbols(tmp_path, 1440) == ["ADA/EUR", "ETH/BTC", "ETH/EUR"]


def test_reach_writes_under_base_and_quote(tmp_path):
    """Two quotes of one base must not collapse onto one path — that would have one leg
    silently overwrite the other."""
    canonical, out = tmp_path / "canon", tmp_path / "out"
    _write_canonical(canonical, "ETH/EUR", 60, _BASE, 20, close=100.0)
    _write_canonical(canonical, "ETH/BTC", 60, _BASE, 20, close=200.0)
    rest_eur = _rest_rows(_BASE + timedelta(hours=10), 25, close=110.0)
    rest_btc = _rest_rows(_BASE + timedelta(hours=10), 25, close=210.0)
    now = _BASE + timedelta(hours=40)

    report = reach_round(
        canonical,
        out,
        fetch_fn=_fetcher({"XETHZEUR": rest_eur, "XETHXXBT": rest_btc}),
        clock=lambda: now,
        sleep_fn=_no_sleep,
    )

    assert len(report.entries) == 2
    eur = read_parquet(out / "ETH" / "EUR" / "60.parquet")
    btc = read_parquet(out / "ETH" / "BTC" / "60.parquet")
    assert eur.height == 35 and btc.height == 35
    # Distinct content, so neither path was written twice.
    assert eur["close"].to_list() != btc["close"].to_list()


def test_manifest_entries_are_keyed_by_full_symbol(tmp_path):
    """Base-keyed entries collide the moment a base carries two quotes: two entries both
    claiming "ETH"."""
    canonical, out = tmp_path / "canon", tmp_path / "out"
    _write_canonical(canonical, "ETH/EUR", 60, _BASE, 20, close=100.0)
    _write_canonical(canonical, "ETH/BTC", 60, _BASE, 20, close=200.0)
    rest = _rest_rows(_BASE + timedelta(hours=10), 25, close=110.0)
    now = _BASE + timedelta(hours=40)

    reach_round(
        canonical,
        out,
        fetch_fn=_fetcher({"XETHZEUR": rest, "XETHXXBT": rest}),
        clock=lambda: now,
        sleep_fn=_no_sleep,
    )

    manifest = json.loads((out / "manifest.json").read_text())
    assert {e["symbol"] for e in manifest["series"]} == {"ETH/EUR", "ETH/BTC"}
```

**`_write_canonical` must become quote-aware too, and this is not optional.** As it stands it writes to `root / symbol / "EUR" / ...` — hardcoded — so a fixture written with today's helper *cannot express* `ETH/BTC` and the tests above would silently both land on the EUR path. Change its final line to split the symbol:

```python
    base, quote = symbol.split("/")
    write_parquet(frame, root / base / quote / f"{interval}.parquet")
```

Every existing call site passes a bare base (`"BTC"`, `"ETH"`) and must become a full symbol (`"BTC/EUR"`). That is a mechanical sweep of `tests/test_ohlc_reach.py` — do it in this task, and expect the file's other tests to need their `out / "BTC" / "EUR" / ...` read paths left unchanged, since those were already base/quote.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/ -k reach -v`
Expected: FAIL — `_canonical_symbols` returns bases `["ADA", "ETH"]`. Note the mechanism: the BTC leg is not "collapsed", it is INVISIBLE to the `*/EUR/` glob.

- [ ] **Step 3: Make discovery quote-aware**

Replace `_canonical_symbols`, and correct its docstring, which currently asserts something measurably false:

```python
def _canonical_symbols(canonical_root: Path, interval: int) -> list[str]:
    """Full `BASE/QUOTE` symbols carrying a canonical file for `interval`, sorted.

    Derived from the canonical tree rather than a hardcoded basket, so a symbol the canonical set
    does not carry is out of scope here instead of raising. The quote is discovered, not assumed:
    an earlier version globbed `*/EUR/` and its docstring claimed the BTC-quoted legs were ones
    "capture holds but the dumps do not" -- measurably false, `ohlc-full` carries ETH/BTC and
    SOL/BTC dailies. That claim made a wiring limit read as a data limit.
    """
    return sorted(
        f"{p.parent.parent.name}/{p.parent.name}"
        for p in canonical_root.glob(f"*/*/{interval}.parquet")
    )
```

- [ ] **Step 4: Make the round's paths quote-aware**

In `reach_round`, replace the two hardcoded `"EUR"` path segments:

```python
        for symbol in _canonical_symbols(canonical_root, interval):
            pair_key = PAIR_KEYS.get(symbol)
            if pair_key is None:
                logger.warning("reach_round: no REST pair key for %s -- skipping", symbol)
                continue
            base, quote = symbol.split("/")

            canonical = read_parquet(canonical_root / base / quote / f"{interval}.parquet")
```

and the write:

```python
            write_parquet(frame, out_root / base / quote / name)
```

`ReachEntry.symbol` now carries the full symbol with no further change, because it is assigned from `symbol`.

- [ ] **Step 5: Make the manifest re-read quote-aware**

`_write_manifest` re-reads each entry's file to hash it. Split there too:

```python
        base, quote = entry.symbol.split("/")
        frame = read_parquet(out_root / base / quote / name)
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/ -k reach -v`
Expected: all pass, including any pre-existing reach tests. If a pre-existing test asserted base-keyed output, it is asserting the defect — update it and say so in the report; do not weaken the new assertions to match it.

- [ ] **Step 7: Commit**

```bash
git add cli/ohlc/reach.py tests/
git commit -m "feat(ohlc): make the reach round quote-aware so the BTC legs can be minted"
```

---

### Task 3: A source narrower than the candidate set REFUSES

**Files:**
- Modify: `cli/data/rebuild.py` (`_refresh_universe`)
- Test: the existing rebuild test file

**Interfaces:**
- Consumes: `cli.snapshot.assetpairs.CANDIDATE_SYMBOLS`.
- Produces: a `DataSyncError` naming every missing leg, raised before any median is computed.

- [ ] **Step 1: Write the failing test**

```python
def test_a_source_missing_a_candidate_leg_refuses_and_names_it(tmp_path):
    """The guard this task exists for. `escalate` cannot see a narrower SOURCE: a ten-of-twelve
    source yields a ten-name universe with escalate False -- a silent shrink. The refusal must
    also replace today's untyped FileNotFoundError from inside polars."""
    # Build an ohlc-full-shaped tree carrying every CANDIDATE_SYMBOL except ETH/BTC.
    ...  # reuse the rebuild test file's existing tree fixture
    with pytest.raises(DataSyncError, match="ETH/BTC"):
        _refresh_universe(ctx, out_root)


def test_a_symbol_the_floor_rejects_is_NOT_a_missing_source(tmp_path):
    """Presence, not outcome. A leg present but below the volume floor is a selection result and
    must still flow through escalate -- it must NOT trip the guard."""
    ...  # all twelve present, one with volume far below the floor; assert no raise
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/ -k refresh_universe -v`
Expected: the first FAILS with `FileNotFoundError` (untyped, from polars) rather than `DataSyncError` — which is precisely the defect.

- [ ] **Step 3: Add the guard**

In `_refresh_universe`, immediately after the source root is resolved and **before** any frame is read:

```python
    missing = [
        symbol
        for symbol in CANDIDATE_SYMBOLS
        if not (ohlc_root / Path(symbol) / f"{_UNIVERSE_INTERVAL}.parquet").exists()
    ]
    if missing:
        # `escalate` compares the SELECTED set against the previous one; it cannot see that the
        # SOURCE was narrower, so a missing leg would shrink the universe silently with
        # escalate False. Refuse here, naming the legs, rather than raising an untyped
        # FileNotFoundError from inside polars several frames later.
        raise DataSyncError(
            "data rebuild: universe source is missing candidate leg(s): "
            f"{', '.join(missing)} -- under {ohlc_root}"
        )
```

`_refresh_universe` hardcodes `"1440.parquet"` today and there is no `_UNIVERSE_INTERVAL` constant — do NOT mint one for this guard; match the surrounding code's literal.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/ -k refresh_universe -v`
Expected: both pass.

- [ ] **Step 5: Prove the guard by mutation**

Run the reversion through `infra/scripts/mutate-probe.sh` (never a hand-rolled mutate-and-restore loop): delete the `if missing:` raise and confirm the first test goes red. Report which test killed it.

- [ ] **Step 6: Commit**

```bash
git add cli/data/rebuild.py tests/
git commit -m "feat(data): refuse a universe source narrower than the candidate set"
```

---

### Task 3a: Resolve the newest stamped SOURCE

**Files:**
- Modify: `cli/data/rebuild.py` (`_require_ohlc_full` and its caller)
- Test: `tests/test_data_rebuild.py`

**Interfaces:**
- Produces: `resolve_ohlc_source(data_root: Path) -> Path` — newest `ohlc-reach-<stamp>/`, else `ohlc-full/`.

**Why this task exists:** without it the whole iteration is undischarged. `_require_ohlc_full` hardcodes `data_root / "ohlc-full"`, so the attended sitting refuses at its rebuild step however fresh the reach round was — and a fresh round lands as `ohlc-reach-<stamp>` that nothing resolves, because `--ignore-existing` freezes the hub's promoted `ohlc-reach/` forever. This is the same rule as Task 4, applied to the source end.

- [ ] **Step 1: Write the failing tests**

```python
def test_newest_stamped_source_wins_over_ohlc_full(tmp_path):
    (tmp_path / "ohlc-full").mkdir()
    for stamp in ("20260701", "20260811"):
        (tmp_path / f"ohlc-reach-{stamp}").mkdir()
    assert resolve_ohlc_source(tmp_path).name == "ohlc-reach-20260811"


def test_ohlc_full_is_the_fallback_when_no_stamped_source_exists(tmp_path):
    (tmp_path / "ohlc-full").mkdir()
    assert resolve_ohlc_source(tmp_path).name == "ohlc-full"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_data_rebuild.py -k resolve_ohlc_source -v`
Expected: FAIL — the function does not exist.

- [ ] **Step 3: Implement the resolver and point the caller at it**

```python
def resolve_ohlc_source(data_root: Path) -> Path:
    """The newest stamped reach set, else the canonical dump-derived set.

    Same newest-wins rule as the universe artifact, and for the same reason: publication is
    additive (`rsync --ignore-existing`), so a fixed name can never be refreshed on the hub. The
    stamp is %Y%m%d, so lexicographic order is chronological.
    """
    stamped = sorted((p for p in data_root.glob("ohlc-reach-*") if p.is_dir()), reverse=True)
    return stamped[0] if stamped else data_root / "ohlc-full"
```

Replace `_require_ohlc_full`'s hardcoded path with this call. Keep its existing existence check and error message shape — only the path it checks changes.

- [ ] **Step 4: Point Task 3's guard at the RESOLVED root**

The presence guard added in Task 3 must run against `resolve_ohlc_source(...)`'s result, not against `ohlc-full`. This is the point of the pairing: `ohlc-full` always carries all twelve legs, so a guard pointed there can never trip — a reach set is where a ten-of-twelve source actually occurs.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_data_rebuild.py -v`
Expected: pass, including Task 3's guard tests, which now exercise the resolved root.

- [ ] **Step 6: Commit**

```bash
git add cli/data/rebuild.py tests/test_data_rebuild.py
git commit -m "feat(data): resolve the newest stamped reach set as the universe source"
```

---

### Task 4: Resolve the newest stamped universe set

**Files:**
- Modify: `cli/capture/command.py` (`UNIVERSE_RELATIVE_PATH` and `_default_pairs`'s caller)
- Test: the existing capture-command test file

**Interfaces:**
- Produces: `resolve_universe_path(data_root: Path) -> Path` — newest `universe-<stamp>/point-in-time-universe.json`, falling back to `universe/point-in-time-universe.json`.

- [ ] **Step 1: Write the failing tests**

```python
def test_newest_stamped_set_wins(tmp_path):
    for stamp in ("20260101", "20260811", "20260501"):
        d = tmp_path / f"universe-{stamp}"
        d.mkdir()
        (d / "point-in-time-universe.json").write_text("{}")
    assert resolve_universe_path(tmp_path).parent.name == "universe-20260811"


def test_legacy_set_is_the_fallback_when_no_stamped_set_exists(tmp_path):
    d = tmp_path / "universe"
    d.mkdir()
    (d / "point-in-time-universe.json").write_text("{}")
    assert resolve_universe_path(tmp_path).parent.name == "universe"


def test_a_stamped_set_without_the_json_does_not_mask_an_older_complete_one(tmp_path):
    """The resolver's own silent-shrink case: degrading to an OLDER universe without saying so is
    the same defect class as a narrower source. A newer directory that lacks the artifact must not
    be chosen, and the older complete one must be."""
    (tmp_path / "universe-20260101").mkdir()
    (tmp_path / "universe-20260101" / "point-in-time-universe.json").write_text("{}")
    (tmp_path / "universe-20260811").mkdir()  # newer stamp, NO artifact inside
    with caplog.at_level("ERROR"):
        resolved = resolve_universe_path(tmp_path)
    assert resolved.parent.name == "universe-20260101"
    # The spec forbids a QUIET fall-back: asserting only the path would pin the defect.
    assert any("universe-20260811" in r.message for r in caplog.records)
```

Take `caplog` as a parameter. The implementation must therefore log an ERROR naming the skipped directory — see the spec's verification bullet, which rules quiet degradation out explicitly.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/ -k resolve_universe -v`
Expected: FAIL — `resolve_universe_path` does not exist.

- [ ] **Step 3: Implement the resolver**

In `cli/capture/command.py`:

```python
UNIVERSE_FILENAME = "point-in-time-universe.json"
UNIVERSE_RELATIVE_PATH = Path("universe") / UNIVERSE_FILENAME  # legacy set, the fallback


def resolve_universe_path(data_root: Path) -> Path:
    """The newest stamped universe set's artifact, else the legacy one.

    Publication is additive (`rsync --ignore-existing`, never `--delete`), so a fixed filename can
    never be updated on the hub -- the artifact is a SERIES of immutable sets instead. The stamp is
    %Y%m%d, so lexicographic order is chronological and no date parsing is needed. A stamped dir
    without the artifact inside is skipped rather than chosen: silently degrading to an older
    universe is the same defect class the source guard refuses.
    """
    candidates = sorted(
        (p for p in data_root.glob(f"universe-*/{UNIVERSE_FILENAME}")),
        key=lambda p: p.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else data_root / UNIVERSE_RELATIVE_PATH
```

- [ ] **Step 4: Point the caller at it**

Replace `_default_pairs((cfg.data_dir or Path("data")) / UNIVERSE_RELATIVE_PATH)` with
`_default_pairs(resolve_universe_path(cfg.data_dir or Path("data")))`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/ -k 'resolve_universe or default_pairs or capture_command' -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add cli/capture/command.py tests/
git commit -m "feat(capture): resolve the newest stamped universe set, legacy as fallback"
```

---

### Task 5: Publish the stamped set

**Files:**
- Modify: whichever module invokes `push_hot` for a rebuild's output (find it: `grep -rn 'push_hot' cli/`)
- Test: the existing sync test file

**Interfaces:**
- Consumes: `push_hot(..., extra_sets=...)`, which already exists — do not add a parameter.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_stamped_set_is_published_via_extra_sets(tmp_path):
    # The minted sibling is data/universe-<stamp>/; it must reach the hub under its own name,
    # never overwriting the legacy universe/ set.
    ...  # assert the rsync runner was called with a dest ending "universe-20260811/"


def test_publishing_the_same_stamp_twice_creates_nothing_the_second_time(tmp_path):
    """Additive by construction. Assert on rsync's itemised output, not on the absence of an
    error -- a run that silently overwrote would also not error."""
    ...
```

Read the sync test file for its existing fake `runner` and reuse it; `_run_rsync` takes `runner=subprocess.run`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/ -k 'push or sync' -v`

- [ ] **Step 3: There is nothing to wire — pin what already exists**

`cli/data/command.py` already calls `push_hot(data_root, [], dest, extra_sets=[p.name for p in minted])`, so every minted sibling including `universe-<stamp>` is already published, and `--push` defaults to true. Step 2 will therefore NOT fail as a red test would. Rewrite this task honestly as regression tests pinning that behaviour, and add the half the spec asks for that is genuinely untested: **pushing a NEW stamp must not modify a previously published one** — assert on the fake runner's per-set destination argv, not on the absence of an error. Do **not** add a stamped name to `authored_sets`: `push_hot` raises if any named set is missing from disk, so it would break every future push once that sibling is cleaned up.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/ -k 'push or sync' -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add cli/ tests/
git commit -m "feat(data): publish the universe as a stamped set via extra_sets"
```

---

### Task 6: Closeout

**Files:**
- Modify: `docs/iterations-history-phase1.md` (or the phase the closeout skill routes to)
- Modify: the phase decisions log
- Modify: `docs/open-topics/T0093-universe-rebuild-reads-a-stale-ohlc-set.md`, `T0024`, and `docs/open-topics/README.md`

- [ ] **Step 1: Load the `iteration-closeout` skill and follow it** for the entry format and phase routing. Do not improvise either.

- [ ] **Step 2: Write the history entry from the branch log**, not from this plan. Record the three corrections the spec carries — the rebuild refuses on every source today, the "eleven names / drop AVAX" figure is a stale-window artifact, and the real question was what supplies the BTC legs — plus the false `_canonical_symbols` docstring this branch corrected.

- [ ] **Step 3: Decisions-log entries**, `[iter-<N>]` prefixed, 2–3 options each with `(Decision: N)`: the volume source; the `PAIR_KEYS` key shape; the stamped-set publication versus deleting the hub copy versus a guarded promote command.

- [ ] **Step 4: Update the topics.** T0093 moves to `partial` or `resolved` per what actually landed — the wiring is done here, the *operational sitting* is not. T0024's `pending-capture` remainder is NOT discharged by this branch: it is discharged by the rebuild run, which is attended work after merge. Say so rather than flipping it early.

- [ ] **Step 5: State explicitly that no dataset-catalog change is owed** by the code branch — the reach set's shape changes only when a fresh round is minted, which is the attended sitting.

- [ ] **Step 6: Commit**

---

## The attended sitting (after merge — NOT part of task execution)

One sitting, in order. Splitting it rebuilds the canonical universe more than once, and every downstream selection reads that artifact.

1. `zcrypto data rebuild ohlc-reach` — mints all twelve legs now that Task 2 has landed. Verify `ETH/BTC` and `SOL/BTC` come back `status: continuous` with non-zero `overlap_bars`; a `detached` status on either is a failure of this iteration, not a caveat to accept.
2. `zcrypto data fetch` — `data/ohlc-reach` is absent on the workstation; the promoted set lives only on the read-only NAS.
3. `zcrypto data rebuild universe` — re-measure selection on the fresh window and state every median. The last measured window gave 12/12 with DOT/EUR thinnest at 194,771.98; a different outcome is a finding to report, not a number to adjust.
4. Publish the stamped set; confirm the hub carries `universe-<stamp>/` and that the legacy `universe/` is untouched.
5. Regenerate `docs/universe/point-in-time-universe.md` by hand, set its `as_of` to the published stamp, and run `uv run pytest tests/test_universe_provenance.py` — its basket-hash line is pinned against `docs/reference/data-catalog.md`, whose rows are irreplaceable.

**Two live Kraken public GETs fire before any guard runs**, so a "just see what happens" invocation is not free of network side effects. `--push` defaults to true on `zcrypto data rebuild`; pass `--no-push` for a local trial.
