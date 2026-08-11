# The universe refresh's volume source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `_refresh_universe` a source that reaches the present for all twelve candidate symbols, make a narrower source refuse instead of silently shrinking the universe, and publish the artifact as a stamped set so an additive-only transport can express a second version.

**Architecture:** Four independent seams. `PAIR_KEYS` becomes symbol-keyed so one base can carry two quotes; `reach.py` becomes quote-aware on its glob, its read/write paths and its manifest; `_refresh_universe` gains a presence guard over `CANDIDATE_SYMBOLS`; and the canonical artifact becomes `universe-<stamp>/` sets resolved newest-wins, using the sibling naming `rebuild_sets` already mints and the `extra_sets` parameter `push_hot` already takes.

**Tech Stack:** Python 3.14, uv, polars, Typer. No new dependency.

## Global Constraints

- **Symbol identity is the full `BASE/QUOTE` string** (`"ETH/EUR"`, `"ETH/BTC"`) everywhere this plan touches. A base-keyed structure cannot express two quotes for one base — that is the defect being fixed, so do not reintroduce it.
- **The venue spells it `XBT`; we spell it `BTC`.** Pair keys are `XETHXXBT` / `SOLXBT` with `wsname` `ETH/XBT` / `SOL/XBT`. Any match on the venue's spelling without normalising produces a false negative that looks exactly like "the legs do not exist".
- **`cli/engine/cycle.py`'s `PAIR_KEYS` is a DIFFERENT symbol**, imported from `cli.engine.store`. It is NOT touched by this plan. A grep that does not distinguish the two will over-scope the change.
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
| D4 — a narrower source refuses | 3 |
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

- [ ] **Step 5: Update every consumer found in Step 1**

`cli/ohlc/reach.py`'s `PAIR_KEYS.get(symbol)` already passes whatever `_canonical_symbols` yields — Task 2 makes that a full symbol, so this call site becomes correct then. Do not change it here; verify only that no OTHER call site passes a bare base.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/ -k 'pair_keys or fetch or reach' -v`
Expected: the two new tests pass. Reach tests may fail — Task 2 fixes them; note which, do not patch them here.

- [ ] **Step 7: Commit**

```bash
git add cli/ohlc/fetch.py tests/
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
Expected: FAIL — `_canonical_symbols` returns bases (`["ADA", "ETH"]`, with the two ETH legs collapsed to one entry).

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

Use the interval constant the function already uses for the daily grid; read the surrounding code and match it rather than hardcoding `1440`.

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
    assert resolve_universe_path(tmp_path).parent.name == "universe-20260101"
```

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

- [ ] **Step 3: Wire the publication**

Pass the minted sibling's directory name as `extra_sets=[sibling_name]` at the existing `push_hot` call site. Do **not** add it to `authored_sets` in `zcrypto.toml`: `push_hot` requires every authored set to exist on disk, so a stamped name there would break every future push once that sibling is cleaned up.

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
