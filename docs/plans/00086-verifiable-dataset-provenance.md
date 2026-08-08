# Verifiable Dataset Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a trial record's dataset reference self-describing and machine-checkable, for the datasets that actually back trials, so no future `dataset_hash` becomes unresolvable the way 44 existing ones have.

**Architecture:** Two per-shape adapters capture a `datasets` block (per-axis **resolved** slice + set digest + extent) for an allowlist of three datasets; `dataset_hash` becomes `compute_hash(datasets)`; `dataset_hash` moves into the store-owned key set so no caller can supply it; and `validate_stored_record` enforces both the block's shape and the derivation at LOAD, since `append()` has no production caller — with a hard schema-4 floor past trial 46 so a new record cannot escape the check by declaring 3.

**Tech Stack:** Python 3.14, `cli/registry/`, pytest, `infra/scripts/mutate-probe.sh`.

## Global Constraints

- Spec: `docs/specs/00086-verifiable-dataset-provenance-design.md`; D-numbers below refer to it. **This is the reshaped version** — a generic-capture design failed four cold-review rounds and was replaced by D1's allowlist. Do not re-generalise.
- **The registry is append-only and hash-chained.** No task rewrites, reorders or re-hashes a record. `docs/reference/trial-registry.jsonl` is modified by NO task.
- **The key-set move breaks all 46 records in three ways if done carelessly** (D3). Task 2 Step 2 makes ONLY that move and then performs a REAL load of the real file — set arithmetic over the constants cannot see any of the three, because two of them live inside `validate_caller_fields`.
- **The schema bump and the `append()` change land in ONE commit** (Task 2). Bumping `SCHEMA_VERSION` while `append()` still writes no `datasets` block would make every record it writes unloadable by the validator in the same commit.
- **Runtime readers**: `cli/portfolio/record44_legs.py` constructs `TrialRegistry`; `cli/engine/soak.py` parses the JSONL with raw `json.loads` and never validates. Breaking the loader breaks the first; the second does not inherit D4's check (named in the spec, not a defect to fix here).
- **Several seds in Task 4 quote implementation lines verbatim.** Where Task 1/2 prescribes an exact line, write it exactly — `mutate-probe.sh` exits 6 on a no-op sed.
- Each task stages **everything it edits**. `mutate-probe.sh` refuses a dirty worktree, so an unstaged edit makes every later probe exit 3.
- Commit gate `uv run pre-commit run -a` before each commit; a rewriting run reports Failed and leaves rewrites unstaged — re-run, re-stage, re-commit.

______________________________________________________________________

### Task 1: The two adapters and `capture_datasets`

Pure new module, no schema change, nothing else depends on it yet — so it lands safely first.

**Files:**

- Create: `cli/registry/provenance.py`
- Test: `tests/test_registry_provenance.py`

**Interfaces:**

- Produces: `capture_datasets(select: dict[str, dict[str, list[str]]], data_root: Path) -> dict` returning the D2 block; `ALLOWLIST: dict[str, str]` mapping dataset name (or prefix, for `ohlc-holdout-*`) to adapter name. Raises `RegistryError` on an empty `datasets` mapping, an unlisted dataset, an absent manifest, a `series` block that is not the adapter's expected shape, an unknown axis key, or a token that matches nothing.
- Consumes: `cli.registry.errors.RegistryError`.

- [ ] **Step 1: Write the failing tests** — `tests/test_registry_provenance.py`

```python
import json
import pytest
from pathlib import Path
from cli.registry.errors import RegistryError
from cli.registry.provenance import ALLOWLIST, capture_datasets

_NESTED = {
    "BTC/EUR": {"1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00",
                         "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64},
                "240":  {"rows": 60, "first_ts": "2020-01-01T00:00:00+00:00",
                         "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "d" * 64}},
    "ETH/EUR": {"1440": {"rows": 7, "first_ts": "2020-01-04T00:00:00+00:00",
                         "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "e" * 64},
                "240":  {"rows": 42, "first_ts": "2020-01-04T00:00:00+00:00",
                         "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "f" * 64}},
}


def _write(root: Path, name: str, payload: dict) -> None:
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "manifest.json").write_text(json.dumps(payload))


def _full(root: Path) -> None:
    _write(root, "ohlc-full", {"basket_sha256": "a" * 64, "fetched_at": "2020-01-11T00:00:00+00:00",
                               "source": "/machine/local/path", "series": _NESTED})


def test_backfill_shape_captures_the_declared_slice(tmp_path):
    _full(tmp_path)
    got = capture_datasets({"ohlc-full": {"intervals": ["1440"], "pairs": ["BTC/EUR"]}}, tmp_path)["ohlc-full"]
    assert got["select"] == {"intervals": ["1440"], "pairs": ["BTC/EUR"]}
    assert got["set_digest"] == "a" * 64
    assert got["extent"] == {"series": 1, "rows": 10,
                             "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T00:00:00+00:00"]}
    assert "source" not in got and "fetched_at" not in got  # D2: no per-run, no machine-local values


def test_each_axis_is_independently_selectable_and_empty_means_all(tmp_path):
    _full(tmp_path)
    whole = capture_datasets({"ohlc-full": {}}, tmp_path)["ohlc-full"]["extent"]
    assert whole == {"series": 4, "rows": 119,
                     "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T20:00:00+00:00"]}
    by_pair = capture_datasets({"ohlc-full": {"pairs": ["ETH/EUR"]}}, tmp_path)["ohlc-full"]["extent"]
    assert by_pair["series"] == 2 and by_pair["rows"] == 49
    by_interval = capture_datasets({"ohlc-full": {"intervals": ["240"]}}, tmp_path)["ohlc-full"]["extent"]
    assert by_interval["series"] == 2 and by_interval["rows"] == 102


def test_holdout_shape_uses_manifest_sha256_and_a_single_asset_axis(tmp_path):
    # No basket_sha256, no per-series sha256, series NOT nested by interval.
    _write(tmp_path, "ohlc-holdout-2026-07-10", {
        "manifest_sha256": "b" * 64, "pulled_at": "2026-07-10T01:30Z", "freeze_last_complete_day": "2026-07-09",
        "series": {"ADA": {"rows": 5, "first_ts": "2018-09-28 00:00:00+00:00",
                           "last_ts": "2026-07-09 00:00:00+00:00", "overlap_bars_verified": 3, "appended": 1},
                   "BTC": {"rows": 9, "first_ts": "2013-09-10 00:00:00+00:00",
                           "last_ts": "2026-07-09 00:00:00+00:00", "overlap_bars_verified": 3, "appended": 1}}})
    name = "ohlc-holdout-2026-07-10"
    got = capture_datasets({name: {"assets": ["ADA"]}}, tmp_path)[name]
    assert got["set_digest"] == "b" * 64
    assert got["extent"] == {"series": 1, "rows": 5,
                             "span": ["2018-09-28 00:00:00+00:00", "2026-07-09 00:00:00+00:00"]}
    with pytest.raises(RegistryError, match="intervals"):  # not an axis of this adapter
        capture_datasets({name: {"intervals": ["1440"]}}, tmp_path)


def test_select_is_resolved_so_order_duplicates_and_abbreviation_cannot_move_the_digest(tmp_path):
    _full(tmp_path)
    a = capture_datasets({"ohlc-full": {"intervals": ["240", "1440", "240"]}}, tmp_path)
    b = capture_datasets({"ohlc-full": {"intervals": ["1440", "240"]}}, tmp_path)
    # D2: an absent axis is RESOLVED to its full membership, not stored blank -- so the block states
    # which pairs were read without the manifest, and the abbreviation hashes as the slice it means.
    assert a == b
    assert a["ohlc-full"]["select"] == {"intervals": ["1440", "240"], "pairs": ["BTC/EUR", "ETH/EUR"]}
    assert capture_datasets({"ohlc-full": {}}, tmp_path) == a


def test_an_unlisted_dataset_is_refused_and_the_message_names_the_remedy(tmp_path):
    _write(tmp_path, "derivatives-funding", {"basket_sha256": "e" * 64, "fetched_at": "x", "series": {}})
    with pytest.raises(RegistryError, match="adapter"):
        capture_datasets({"derivatives-funding": {}}, tmp_path)


def test_an_absent_manifest_is_refused_and_names_the_path(tmp_path):
    with pytest.raises(RegistryError, match=r"ohlc-full/manifest\.json"):
        capture_datasets({"ohlc-full": {}}, tmp_path)


@pytest.mark.parametrize("bad", [{"intervals": ["60"]}, {"pairs": ["DOGE/EUR"]}, {"grids": ["1440"]}])
def test_an_unresolvable_select_token_or_axis_is_refused(tmp_path, bad):
    _full(tmp_path)
    with pytest.raises(RegistryError):
        capture_datasets({"ohlc-full": bad}, tmp_path)


def test_an_empty_datasets_mapping_is_refused(tmp_path):
    with pytest.raises(RegistryError, match="no dataset"):
        capture_datasets({}, tmp_path)


def test_a_changed_series_shape_is_a_registry_error_not_a_traceback(tmp_path):
    """`ohlc-reach` already writes `series` as a list[dict]; a supported writer could too."""
    _write(tmp_path, "ohlc-full", {"basket_sha256": "a" * 64, "fetched_at": "x",
                                   "series": [{"symbol": "BTC/EUR", "rows": 10}]})
    with pytest.raises(RegistryError, match="series"):
        capture_datasets({"ohlc-full": {}}, tmp_path)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: FAIL — `cli.registry.provenance` does not exist.

- [ ] **Step 3: Implement**

`ALLOWLIST = {"ohlc-full": "backfill", "ohlc-15m": "backfill", "ohlc-holdout": "holdout"}` — every key matches exactly **or** as a `<key>-…` prefix, so both `ohlc-holdout-<date>` and a re-freeze sibling `ohlc-full-<stamp>` resolve (D1: revisions mint siblings, so a sibling is the canonical's own successor, same writer and same shape). Resolution goes through a helper whose match line is quoted verbatim by Task 4 Probe 2:

```python
    for key, adapter in ALLOWLIST.items():
        if name == key or name.startswith(key + "-"):
```

Anything unmatched raises `RegistryError` whose message contains the word `adapter` and the dataset name.

An empty `datasets` mapping raises before any adapter runs, with a message containing `no dataset` (D2: a record naming no dataset carries no provenance).

**Axes.** Backfill declares `("pairs", "intervals")` and walks `series[pair][interval]`; holdout declares `("assets",)` and walks `series[asset]` (one level). Each adapter first checks `series` is a `dict` of the depth it expects and otherwise raises `RegistryError` naming the dataset, the key `series` and the expected shape — `ohlc-reach` already writes a `list[dict]`, so a writer drifting there must give a refusal, not an `AttributeError` traceback out of the on-disk conformance test. A `select` key outside the adapter's axes raises, naming the offending key and the allowed axes. Within an axis, an empty or absent list means all of it; a token matching no key on that axis raises, naming the token.

**`select` is RESOLVED, not echoed** (D2). Per axis, compute the sorted deduplicated list of tokens the declaration actually selects — the caller's list when non-empty, else that axis's full membership from the manifest — and emit **that** as `select`. So `{}` and the fully spelled-out slice produce one digest, and the stored block names the pairs/intervals without the (gitignored) manifest. Resolve before the leaf walk and keep it on its own line: Probe 3 blanks only the leaf filter, and must leave `select` correct while `extent` collapses.

The backfill leaf walk is quoted verbatim by Probe 3, so write the filter as its own line:

```python
    leaves = [
        leaf
        for pair, by_interval in series.items()
        for interval, leaf in by_interval.items()
        if _selected(pair, sel.get("pairs")) and _selected(interval, sel.get("intervals"))
    ]
```

**Refuse an empty selection BEFORE computing `extent`.** Immediately after the leaf walk, `if not leaves: raise RegistryError(...)` naming the dataset and the resolved `select`. Two real cases reach it: an allowlisted manifest whose `series` is `{}`, and a legal per-axis selection over a ragged manifest where every token resolves on its own axis but the cross-product is empty (e.g. `pairs=["BTC/EUR"], intervals=["240"]` where that pair carries only `1440`). Without it, `min()` over no leaves raises a bare `ValueError`, which falsifies the spec's promise that a drifted manifest refuses with a `RegistryError` naming the dataset — and would make the on-disk conformance test fire as a traceback rather than the promised refusal. Keep this OUT of the two lines Probes 3 and 4 quote verbatim, so those seds stay non-no-op.

`extent` per D2, in one shared helper over the selected leaves — `rows = sum(leaf["rows"] for leaf in leaves)` verbatim (Probe 4 quotes it), `series` = `len(leaves)`, `span` = `[min(first_ts), max(last_ts)]` as **raw strings** (the holdout's stamps use a space, not `T`; do not parse or normalise them — a round-trip through a datetime would silently change the recorded value). Sort each `select` axis list and drop duplicates. Emit **only** `select`, `set_digest`, `extent`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: PASS.

- [ ] **Step 5: Add the on-disk conformance tests**

Enumerate from disk, not from a hardcoded tuple — a set present but unlisted must be visible. **Skip, never pass, on an empty glob**: `data/` is gitignored except its own `.gitignore` (`git ls-files data/` returns exactly that one file), so on a bare CI checkout `_DATA.exists()` is TRUE and the glob is EMPTY — a bare `for` loop would report a green having asserted nothing.

All three sets are **frozen** — a revision mints a sibling, never an overwrite — so all three get a measured extent pin. Without one the loop asserts only `rows > 0`, which any non-empty manifest satisfies, and it is `ohlc-full`/`ohlc-15m` that back every historical trial.

```python
_DATA = Path(__file__).resolve().parent.parent / "data"

# Measured from this repo's data root 2026-08-08. Same "canonical dataset drifted -- STOP" contract as
# tests/test_crossfreq_system.py::EXTENT: a revision mints a sibling, so these never move in place.
_PINS = {
    "ohlc-full": {"series": 36, "rows": 1052322,
                  "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T23:00:00+00:00"]},
    "ohlc-15m": {"series": 12, "rows": 3122044,
                 "span": ["2013-09-10T23:45:00+00:00", "2026-03-31T23:45:00+00:00"]},
    "ohlc-holdout-2026-07-10": {"series": 10, "rows": 30032,
                                "span": ["2013-09-10 00:00:00+00:00", "2026-07-09 00:00:00+00:00"]},
}


def _listed(name: str) -> bool:
    return any(name == k or name.startswith(k + "-") for k in ALLOWLIST)


def test_every_allowlisted_dataset_on_disk_captures_and_every_other_is_refused():
    manifests = sorted(_DATA.glob("*/manifest.json"))
    if not manifests:
        pytest.skip("no dataset manifests on this host (the data root is gitignored)")
    captured = 0
    for manifest in manifests:
        name = manifest.parent.name
        if _listed(name):
            block = capture_datasets({name: {}}, _DATA)[name]
            assert block["extent"]["rows"] > 0 and len(block["set_digest"]) == 64
            captured += 1
        else:
            with pytest.raises(RegistryError, match="adapter"):
                capture_datasets({name: {}}, _DATA)
    assert captured, f"no allowlisted dataset among {[m.parent.name for m in manifests]}"


@pytest.mark.parametrize("name", sorted(_PINS))
def test_a_frozen_canonical_extent_matches_its_measured_pin(name):
    if not (_DATA / name / "manifest.json").is_file():
        pytest.skip(f"{name} absent on this host (the data root is gitignored)")
    assert capture_datasets({name: {}}, _DATA)[name]["extent"] == _PINS[name], (
        f"canonical dataset drifted — STOP: {name}'s whole-set extent moved. These sets are frozen; a "
        f"revision mints a sibling dir. Investigate before updating this pin."
    )
```

- [ ] **Step 6: Commit**

```bash
git add cli/registry/provenance.py tests/test_registry_provenance.py
git commit -m "feat(registry): two manifest adapters capture a declared dataset slice"
```

______________________________________________________________________

### Task 2: Schema 4, the key-set split, `append()`, and the load-time checks — ONE commit

Everything that changes the record contract lands together. Splitting it leaves an intermediate commit whose own `append()` writes records its own validator rejects.

**Files (5):**

- Modify: `cli/registry/record.py`, `cli/registry/store.py`
- Test: `tests/test_registry_record.py`, `tests/test_registry_store.py`, `tests/test_trial_registry_provenance.py`

**Interfaces:**

- Produces: `SCHEMA_VERSION = 4`; `TrialRecord.datasets: dict | None`; `append(*, datasets: dict[str, dict[str, list[str]]], ...)` with **no** `dataset_hash` parameter; `TrialRegistry(path, *, data_root: Path | None = None)`.
- Consumes: `capture_datasets` (Task 1).

- [ ] **Step 1: The key-set move ALONE, then a real load**

Four edits to `cli/registry/record.py`, nothing else yet:

1. `_STORE_OWNED` gains `"dataset_hash"`.
1. `_REQUIRED_CALLER` loses `"dataset_hash"`. `_BASE_STORED_KEYS` is the union of both, so it is unchanged — that is what makes the move safe. **Do NOT add `datasets` to either set** (D3 mistake 2).
1. `validate_caller_fields`'s hardcoded type-check tuple `("iteration", "family", "spec_hash", "dataset_hash")` loses `"dataset_hash"` (D3 mistake 1). `validate_stored_record` strips `_STORE_OWNED` before calling it, so leaving it there raises a bare `KeyError` on record 1.
1. `TrialRegistry.append` sets `dataset_hash` on `rec` **after** `validate_caller_fields(caller)` — passing it in `caller` now trips the store-owned refusal. For this step only, keep the parameter and assign `rec["dataset_hash"] = dataset_hash`.

Then load the real file through the real loader:

```bash
uv run python -c "
from pathlib import Path
from cli.registry import TrialRegistry
reg = TrialRegistry(Path('docs/reference/trial-registry.jsonl'))
print('loaded', len(reg), 'schema versions', sorted({r.schema_version for r in reg.records}))
assert len(reg) == 46"
```

Expected: `loaded 46 schema versions [2, 3]`. Anything else — a `RegistryError`, a `KeyError`, a short count — means the move is wrong; fix it here, before schema 4 exists. Then `uv run pytest tests/test_registry_store.py -q` — expect **36 passed**, nothing red: `_append` still passes `dataset_hash=` and every stored body still carries the key, so nothing in that file moves yet. `tests/test_registry_record.py` is what reds at this step, because its `_caller()` still supplies the now-store-owned `dataset_hash` — leave it; Step 4 fixes it. Do not "repair" it here, or you will undo the move.

- [ ] **Step 2: Write the failing tests** — all in `tests/test_registry_store.py`, beside the helpers they reuse (`_write`, `_new_registry`, `_append`, `canonical_json`, `compute_hash` are already there; add `import inspect`)

```python
def _data_root(tmp_path):
    """Two pairs x two intervals, so both backfill axes discriminate."""
    root = tmp_path / "data" / "ohlc-full"
    root.mkdir(parents=True, exist_ok=True)
    leaf = lambda n, last: {"rows": n, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": last, "sha256": "c" * 64}
    (root / "manifest.json").write_text(json.dumps({
        "basket_sha256": "a" * 64, "fetched_at": "x",
        "series": {"BTC/EUR": {"1440": leaf(10, "2020-01-10T00:00:00+00:00"), "240": leaf(60, "2020-01-10T20:00:00+00:00")},
                   "ETH/EUR": {"1440": leaf(7, "2020-01-10T00:00:00+00:00"), "240": leaf(42, "2020-01-10T20:00:00+00:00")}}}))
    return tmp_path / "data"


_REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"


def test_all_46_committed_records_still_load():
    """The defect that sank the first attempt. Assert against the REAL file, not a fixture."""
    reg = TrialRegistry(_REGISTRY)
    assert len(reg) >= 46  # floored, never pinned: the file grows with every registered trial
    assert all(r.schema_version in (2, 3) or r.datasets for r in reg.records)


def test_append_has_no_dataset_hash_parameter():
    assert "dataset_hash" not in inspect.signature(TrialRegistry.append).parameters


def test_a_schema_four_record_round_trips_through_disk(tmp_path):
    reg = _new_registry(tmp_path)
    written = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-full": {"intervals": ["1440"]}})
    reloaded = _new_registry(tmp_path).records[-1]
    assert reloaded.schema_version == 4
    assert reloaded.dataset_hash == compute_hash(reloaded.datasets) == written.dataset_hash


def test_different_declared_intervals_give_different_digests(tmp_path):
    reg = _new_registry(tmp_path)
    daily = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-full": {"intervals": ["1440"]}})
    both = _append(reg, family="B", n_trials_in_family=1, datasets={"ohlc-full": {"intervals": ["1440", "240"]}})
    assert daily.dataset_hash != both.dataset_hash


def test_different_declared_pairs_give_different_digests(tmp_path):
    """The axis the registry's own history varies on: trials 1-8 vs 9-16 differ on pairs alone."""
    reg = _new_registry(tmp_path)
    one = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-full": {"pairs": ["BTC/EUR"]}})
    two = _append(reg, family="B", n_trials_in_family=1, datasets={"ohlc-full": {}})
    assert one.dataset_hash != two.dataset_hash


_BLOCK = {"select": {"intervals": ["1440"]}, "set_digest": "a" * 64,
          "extent": {"series": 1, "rows": 10, "span": ["2020-01-01", "2020-01-10"]}}


def _schema4_line(**over):
    body = dict(
        trial_id=1, schema_version=4, timestamp="2026-08-08T00:00:00+00:00", iteration="iter-001",
        family="A1", spec_hash="s", seeds=[0], metrics={"dsr": 0.1}, n_trials_in_family=1,
        verdict="adopt", run_ref=None, notes="", prev_hash=GENESIS_HASH,
        datasets={"ohlc-full": dict(_BLOCK)},
    )
    body.update(over)
    body["dataset_hash"] = over.get("dataset_hash", compute_hash(body["datasets"]))
    return canonical_json(dict(body, record_hash=compute_hash(body)))


@pytest.mark.parametrize(
    "over, match",
    [
        ({"dataset_hash": "deadbeef" * 8}, "dataset_hash"),   # D4: derivation, not a caller claim
        ({"datasets": "ba47e37e"}, "datasets"),               # D2a: the original failure, verbatim
        ({"datasets": {}}, "datasets"),                       # D2: empty carries no provenance
        ({"datasets": {"ohlc-full": {"select": {}, "set_digest": "zz"}}}, "datasets"),  # short + bad digest
        # D2a's emptiness/strictness clauses. Each block below is otherwise perfectly shaped AND correctly
        # derived (`_schema4_line` re-derives `dataset_hash` from whatever it is given), so nothing but the
        # named clause can reject it -- and each defeats D2's property while satisfying the letter.
        ({"datasets": {"ohlc-full": {**_BLOCK, "select": {}}}}, "select"),
        ({"datasets": {"ohlc-full": {**_BLOCK, "select": {"intervals": []}}}}, "select"),
        ({"datasets": {"ohlc-full": {**_BLOCK, "extent": {"series": 0, "rows": 0, "span": ["a", "b"]}}}}, "extent"),
        ({"datasets": {"ohlc-full": {**_BLOCK, "extent": {"series": True, "rows": True, "span": ["a", "b"]}}}}, "extent"),
    ],
)
def test_a_forged_schema_four_record_is_rejected_at_load(tmp_path, over, match):
    """D4/D2a: the invariant is a property of the FILE, not of append()."""
    with pytest.raises(RegistryCorruptionError, match=match):
        TrialRegistry(_write(tmp_path, [_schema4_line(**over)]))


def test_a_schema_four_record_missing_datasets_entirely_is_rejected(tmp_path):
    line = json.loads(_schema4_line())
    del line["datasets"]
    line["record_hash"] = compute_hash({k: v for k, v in line.items() if k != "record_hash"})
    with pytest.raises(RegistryCorruptionError, match="datasets"):
        TrialRegistry(_write(tmp_path, [canonical_json(line)]))


@pytest.mark.parametrize("bad", ["", 123])
def test_a_stored_schema_three_dataset_hash_must_still_be_a_nonempty_str(tmp_path, bad):
    """D3: this check ran on EVERY load via `validate_caller_fields` until `dataset_hash` became
    store-owned. Nothing else covers schema 2/3 — the derivation check binds only >= 4 — so unless it
    is re-homed the guard lapses silently, with the whole suite green and 46 records still loading.
    `RegistryError` catches either spelling (`RegistryCorruptionError` is a subclass).
    """
    body = json.loads(_line(1))  # `_line` is the schema-3 helper, pinned to a literal 3 in Step 4
    del body["record_hash"]
    body["dataset_hash"] = bad
    with pytest.raises(RegistryError, match="dataset_hash"):
        TrialRegistry(_write(tmp_path, [canonical_json(dict(body, record_hash=compute_hash(body)))]))


def test_a_record_past_the_legacy_floor_must_declare_schema_four(tmp_path):
    """D4: what actually binds record 47. The load check binds only >= 4, and nothing else makes a NEW
    record say 4 -- the next direct JSONL writer templates off record 46, which says 3.

    Built on the REAL 46 records (read-only, never rewritten), because that is the file it appends to.
    """
    real = _REGISTRY.read_text(encoding="utf-8").splitlines()
    prev = json.loads(real[-1])

    def _line47(**over):
        body = dict(
            trial_id=prev["trial_id"] + 1, schema_version=4, timestamp="2026-08-08T00:00:00+00:00",
            iteration="iter-001", family="FLOOR", spec_hash="s", seeds=[0], metrics={"dsr": 0.1},
            n_trials_in_family=1, verdict="adopt", run_ref=None, notes="", prev_hash=prev["record_hash"],
            datasets={"ohlc-full": dict(_BLOCK)},
        )
        body.update(over)
        body["dataset_hash"] = compute_hash(body["datasets"])
        return canonical_json(dict(body, record_hash=compute_hash(body)))

    # Non-vacuous in both directions: at schema 4 the very same record loads, so it is the floor that
    # rejects the schema-3 one -- not the chain, the contiguity or the family-count rule.
    assert len(TrialRegistry(_write(tmp_path, [*real, _line47()]))) == prev["trial_id"] + 1

    v3 = json.loads(_line47())
    del v3["datasets"], v3["record_hash"]  # schema 3 may not carry the key at all (surplus-key check)
    v3["schema_version"] = 3
    v3["dataset_hash"] = "ba47e37e2601d6098fd13c0e338a5301e8eeebb16bb4341c76a68147c7b08e42"  # verbatim
    forged = canonical_json(dict(v3, record_hash=compute_hash(v3)))
    with pytest.raises(RegistryCorruptionError, match="schema_version"):
        TrialRegistry(_write(tmp_path, [*real, forged]))


def test_a_manifest_the_loader_would_reject_is_refused_at_append_and_nothing_is_written(tmp_path):
    """D4: capture succeeds, the loader would not -- and the file is append-only, so it must not land."""
    reg = _new_registry(tmp_path)  # FIRST -- _data_root() rewrites the manifest, undoing the edit below
    mf = tmp_path / "data" / "ohlc-full" / "manifest.json"
    m = json.loads(mf.read_text())
    m["basket_sha256"] = m["basket_sha256"].upper()  # an external writer's legal-looking spelling
    mf.write_text(json.dumps(m))
    with pytest.raises(RegistryError):
        _append(reg, family="A", n_trials_in_family=1)
    assert not reg.path.exists() or reg.path.read_text() == ""
```

Run: `uv run pytest tests/test_registry_store.py -q` — expected FAIL.

- [ ] **Step 3: Implement the rest**

`cli/registry/record.py`:

- `SCHEMA_VERSION = 4`; `_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})`.
- `_EXPECTED_STORED_KEYS = {2: _BASE_STORED_KEYS, 3: _BASE_STORED_KEYS | {"variant"}, 4: _BASE_STORED_KEYS | {"variant", "datasets"}}`. That entry only *permits* `datasets`; it does not require it — the surplus check is a superset test and the missing check is over `_BASE_STORED_KEYS`.
- `validate_caller_fields` gets **no** `datasets` check. `capture_datasets` is its only writer and always emits a valid shape; the block's shape is D2a's load-time business, and a caller-layer raise here would be a plain `RegistryError`, which `pytest.raises(RegistryCorruptionError)` cannot catch (corruption is a **subclass**, so it does not catch its parent). Its `_REQUIRED_CALLER` sweep must not name `datasets` either.
- `validate_stored_record` gains, for **every** version, the non-empty-str check on `rec["dataset_hash"]` that `validate_caller_fields` used to perform — it no longer sees the key, so without this the guard silently lapses for schema 2/3 with the whole suite green. Probe 6 seds this text, so write it exactly:

```python
    if type(rec.get("dataset_hash")) is not str or not rec["dataset_hash"]:
        raise RegistryCorruptionError(f"{where}: dataset_hash must be a non-empty str")
```

- `validate_stored_record`, for `version >= 4`, in order, each raising its own `RegistryCorruptionError` **naming `datasets` or `dataset_hash`, plus the offending sub-field where there is one** (`select`, `set_digest`, `extent`): (a) `datasets` present; (b) `_validate_datasets_shape(rec["datasets"], where)`; (c) the derivation, written verbatim as `rec["dataset_hash"] != compute_hash(rec["datasets"])` because Probe 1 seds that text. Order matters: (a) before (c), or (c) raises a bare `KeyError`.
- **Every `_validate_datasets_shape` message names exactly ONE sub-field and interpolates NEITHER the block NOR the offending value.** The parametrized cases match on the bare substrings `select` / `extent`, so an `f"{where}: bad datasets block {value!r}"` — which contains every sub-field name — would let the zero-`extent` case match `select` and vice versa: all four degenerate cases pass for the wrong reason, with nothing to detect it. Name the dataset key and the sub-field; state the rule violated, not the input.
- `_validate_datasets_shape` (D2a — no disk access, no axis-name knowledge): non-empty `dict`; each value a dict with **exactly** `{select, set_digest, extent}`; `select` a **non-empty** `dict[str, list[str]]` whose lists are each **non-empty**, sorted and deduplicated; `set_digest` 64-char lowercase hex; `extent` exactly `{series: int, rows: int, span: [str, str]}` with `series >= 1` and `rows >= 1`. Write the int checks as `type(x) is int`, **never `isinstance`** — `isinstance(True, int)` is `True`, and `_assert_finite` two functions up already uses the is-strict form with the comment saying why. The emptiness clauses are not decoration: without them `{"select": {}, "set_digest": <hex>, "extent": {"series": 0, "rows": 0, ...}}` satisfies every other clause, hashes and loads clean, and carries no slice — defeating D2's "the block says which pairs and intervals were read without the gitignored manifest". Capture can never emit one, so refusing it is free. Probe 7 seds the non-empty-`select` clause, so write that one exactly:

```python
        if type(block["select"]) is not dict or not block["select"]:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] select must be a non-empty dict")
```

- **Place that whole `version >= 4` block BEFORE the `caller = {k: v for k, v in rec.items() ...}` / `validate_caller_fields(...)` lines**, which are today the last two statements of the function — anything raised from the caller layer is a plain `RegistryError` the corruption tests cannot catch.
- `TrialRecord` gains `datasets: dict | None = None`.

`cli/registry/store.py`:

- `_to_record` passes `datasets=rec.get("datasets")` — without it the field is always `None` and the round-trip test fails silently.
- `TrialRegistry.__init__(self, path, *, data_root: Path | None = None)`, stored on the instance. **No `cli.config` default** — resolving it there would make a plain read of the registry raise `ConfigError` on an unconfigured host, and there is no production `append()` caller to serve. `append()` raises `RegistryError` naming `data_root` when it is `None`.
- `append()` drops `dataset_hash`, gains `datasets: dict[str, dict[str, list[str]]]`, calls `capture_datasets(datasets, self._data_root)`, puts the captured block in `caller["datasets"]`, and sets `rec["dataset_hash"] = compute_hash(caller["datasets"])` **after** `validate_caller_fields` (it is store-owned now).
- `append()` then calls `validate_stored_record(rec, f"{self.path} (append)")` **after** `rec["record_hash"] = compute_hash(rec)` and **before** `lock_f.write(...)`. Schema 4 is the first path where a successful capture can yield a record the loader rejects — `set_digest` and `extent.rows` come straight from a manifest, and the holdout's is written by an external freeze — and the file is append-only and hash-chained, so one such line makes the registry permanently unloadable with no legal repair (`_read_healing` heals only a torn *trailing* line).
- `_assert_cross_record` gains the **schema-4 floor** (D4) — the rule that binds record 47, and the only thing that does. Measured: the 46 committed records are `[2]×32` then `[3]×14` and the highest `trial_id` is 46, so the floor costs nothing against history and bites on the very next record. A weaker "non-decreasing `schema_version`" was considered and rejected: an unbroken run of 3s satisfies it, so it binds nothing until a first schema-4 append that nothing compels. Module constant, with the comment, then the guard — Probe 5 seds the guard line, so write both exactly:

```python
# The highest trial_id committed when the datasets block landed. Records 1-46 predate it and the file is
# append-only, so they can never carry one -- the exemption is by ID precisely because that cannot grow.
_LEGACY_UNPROVENANCED_MAX_TRIAL_ID = 46
```

```python
        if rec["trial_id"] > _LEGACY_UNPROVENANCED_MAX_TRIAL_ID and rec["schema_version"] < 4:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} declares schema_version {rec['schema_version']}; every "
                f"record past trial {_LEGACY_UNPROVENANCED_MAX_TRIAL_ID} must be schema_version 4+ and carry "
                f"a derived datasets block"
            )
```

- Update the `TrialRegistry` class docstring: `loads schema v2+v3, writes v3` → `loads schema v2-v4, writes v4`, plus one clause naming the v4 addition (a `datasets` block whose `compute_hash` is `dataset_hash`). Both halves are false after this task, and the constant sits three lines below. **Do NOT touch the two specs it cites** (`docs/specs/00000-…`, `docs/specs/00012-…`): their sha256 is pinned as `spec_hash` in committed records, so editing either dangles a pin that can never be repaired.

- [ ] **Step 4: Update every existing test that constructs a record**

`tests/test_registry_record.py`:

- `test_constants`: `SCHEMA_VERSION == 3` → `== 4`.
- `_caller()`: drop `dataset_hash="d"` — it is store-owned, so `validate_caller_fields(_caller())` would now refuse it.
- `test_invalid_caller_rejected`: add the case `{"dataset_hash": "d"}` beside `{"trial_id": 9}` — same rule, newly applicable.
- Every stored body built from `_caller()` — in `test_stored_record_hash_and_schema_checks`, `test_stored_record_schema_version_variant_compat` (its two `_caller()`-built bodies, `body_v2` and `body_v3`; the three derived copies `body_v3_variant`/`body_v2_bad`/`body_v3_bad` inherit), and `test_stored_record_validation_stays_lenient_about_run_ref` — must now add `dataset_hash="d"` explicitly and pin `schema_version=3` instead of `SCHEMA_VERSION`. They are v3-semantics tests; left on `SCHEMA_VERSION` they become schema-4 bodies with no `datasets` and pass or fail for the wrong reason.

`tests/test_registry_store.py` — the same v3 pin, and it is the trap in this task. Six construction sites:

- `_line` (`schema_version=SCHEMA_VERSION` → literal `3`) and `_line_v2` (already `2`; both keep `dataset_hash="d"`, which is legal in a *stored* body).
- The four inline bodies in `test_v3_record_with_nonstr_variant_is_corruption`, `test_v3_unknown_key_forge_is_corruption`, `test_missing_base_key_is_corruption`, `test_v3_without_variant_still_loads`: pin `schema_version=3`. Left on `SCHEMA_VERSION` the last one fails outright and the other three keep **passing for the wrong reason** — they would raise on the missing `datasets`, silently retiring the variant / forge / missing-base-key guards they exist to pin. Step 6's full-suite run cannot detect that; only this pin can.
- `_append`: drop `dataset_hash="d"`, add `datasets={"ohlc-full": {}}`.
- `_new_registry` takes the path, because two callers do **not** use `t.jsonl` and routing them blind would silently swap in an empty file:

```python
def _new_registry(tmp_path, path=None):
    return TrialRegistry(path or tmp_path / "t.jsonl", data_root=_data_root(tmp_path))
```

- Every site that builds a `TrialRegistry` inline and then calls `_append` must route through it — otherwise `data_root` stays `None` and `append()` raises the new `RegistryError`. **Fourteen** sites, split **eleven** whose registry really is `tmp_path/"t.jsonl"` and may route blind as `_new_registry(tmp_path)`: `test_append_assigns_contiguous_ids_across_reopen`, `test_append_rejects_nonfinite_before_writing`, `test_append_family_count_floor`, `test_append_then_records_snapshot`, `test_concurrent_registries_get_unique_ids`, `test_append_with_variant_round_trips`, `test_append_without_variant_omits_key_from_raw_line`, `test_append_rejects_invalid_variant_before_writing`, `test_append_records_a_committed_run_ref_end_to_end`, `test_variant_does_not_affect_family_budget_monotonic_check`, and **`test_chain_continues_across_registry_instances`** (its `reg2 = TrialRegistry(reg.path)` reopen is an `_append` caller that reads as a plain construction) — and **three** that must pass their own path as `_new_registry(tmp_path, p)`:
  - `test_append_after_torn_trailing_line_self_heal` — `p = _write(tmp_path, [_line(1)])` is `tmp_path/"trials.jsonl"` (the `_write` helper's filename), deliberately torn and then healed; on `t.jsonl` the append lands in an empty file and `assert r.trial_id == 2` fails.
  - `test_mixed_v2_and_v3_file_loads_with_intact_chain` — `p = tmp_path/"trials.jsonl"` pre-seeded with two v2 lines; on `t.jsonl` its first assertion `len(reg) == 2` fails.
  - `test_append_rejects_unprovenanced_run_ref_before_writing` — `p = tmp_path/f"t{hash(str(bad))}.jsonl"`, a fresh path per loop iteration. This is the dangerous one: `_validate_run_ref` fires inside `validate_caller_fields` **before** `open(self.path, "a")`, so no file is ever created either way and the trailing `assert not p.exists() or p.read_text() == ""` stays true whichever path the registry actually used — routing it blind retires that assertion silently instead of failing loudly.
- `grep -n "TrialRegistry(" tests/test_registry_store.py` finds the *names*, not the paths — so check each site's path expression, not just that it appears here.
- `test_append_requires_run_ref_explicitly` passes `dataset_hash="d"` directly to `append()`: replace with `datasets={"ohlc-full": {}}`, or the `TypeError` it asserts fires for the wrong keyword.

`tests/test_trial_registry_provenance.py`: its own `_caller()` supplies `dataset_hash="d"` (used by `test_both_layers_agree_on_path_spelling`) — drop it.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS. Run the FULL suite, not `-k registry` — `tests/test_portfolio_builder.py` and `tests/test_record44_legs.py` construct `TrialRegistry` over the real file and match no registry-shaped keyword.

- [ ] **Step 6: Commit** (stage all five files listed above)

______________________________________________________________________

### Task 3: The legacy pins table

**Files:**

- Create: `docs/reference/legacy-dataset-pins.jsonl`
- Test: `tests/test_legacy_dataset_pins.py`

- [ ] **Step 1: Write the failing tests**

```python
import hashlib
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_REGISTRY = _REPO / "docs" / "reference" / "trial-registry.jsonl"
_PINS_PATH = _REPO / "docs" / "reference" / "legacy-dataset-pins.jsonl"


def _jsonl(path):
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _records():
    return _jsonl(_REGISTRY)


def _pins():
    return _jsonl(_PINS_PATH)


def test_a_pin_record_has_exactly_the_documented_keys_and_names_its_citers():
    """Pins the artifact's shape against the three tests that index into it — otherwise Step 3's four
    entries and this file can silently disagree about key names. `trial_ids` is checked against the
    real registry, so it is the link from a schema-2/3 record to its pin and cannot rot."""
    for pin in _pins():
        assert set(pin) == {"dataset_hash", "referent", "confidence", "trial_ids", "evidence"}
        assert len(pin["dataset_hash"]) == 64 and pin["dataset_hash"] == pin["dataset_hash"].lower()
        assert pin["trial_ids"] == sorted(
            r["trial_id"] for r in _records() if r["dataset_hash"] == pin["dataset_hash"]
        )


def test_every_pre_schema_four_hash_is_pinned():
    historical = {r["dataset_hash"] for r in _records() if r["schema_version"] < 4}
    assert historical == {p["dataset_hash"] for p in _pins()}


def test_cccb8d17_reproduces():
    """The one entry whose recipe executes. Inline, not a data-driven interpreter."""
    pin = next(p for p in _pins() if p["dataset_hash"].startswith("cccb8d17"))
    assert pin["confidence"] == "reproduced"
    a, b = pin["evidence"]["operands"]
    assert hashlib.sha256(f"{a}:{b}".encode()).hexdigest() == pin["dataset_hash"]


def test_the_qualification_lives_in_the_referent_value():
    """A careless grep must not return a bare path that reads as verified fact -- for ANY confidence."""
    for pin in _pins():
        assert pin["confidence"] in ("reproduced", "inferred", "unrecoverable")
        if pin["confidence"] == "inferred":
            assert "INFERRED" in pin["referent"]
        if pin["confidence"] == "unrecoverable":
            assert pin["referent"] is None
        if pin["confidence"] == "reproduced":
            # `reproduced` names the RECIPE, not the data: cccb8d17's 4h operand is 81dc9b44, which this
            # same table classes unrecoverable. This is the row a careless reader trusts unconditionally.
            assert "UNRECOVERABLE" in pin["referent"]
            assert any(p["dataset_hash"].startswith("81dc9b44") and p["confidence"] == "unrecoverable"
                       for p in _pins())
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Write the four entries**, taking every claim from `docs/open-topics/T0065-...md`'s measured table and asserting nothing beyond it. Each carries `trial_ids`, measured from the registry and asserted by the shape test: `ba47e37e` trials 1–35 and 40–42 (38), `81dc9b44` 36–39, `45275ebe` 43–44, `cccb8d17` 45–46.

- `cccb8d17` — `reproduced`, evidence `operands` = the 4h and 15m hex operands, recipe `sha256(hex_4h + ":" + hex_15m)`. Referent `"sha256(81dc9b44 [UNRECOVERABLE 4h primitive] : data/ohlc-15m basket_sha256) — the RECIPE reproduces; the 4h operand's referent does not"`. T0065's words: "fully reproducible but only half traceable to bytes." Verified at full precision 2026-08-08 — the 15m operand is `data/ohlc-15m/manifest.json`'s on-disk `basket_sha256`.
- `ba47e37e` — `inferred`, referent `"data/ohlc-full daily (INFERRED from extent + exclusion — never recomputed)"`. Evidence is T0065's own measured extent and nothing else: BTC/EUR daily **4581 rows**, span `2013-09-10 → 2026-03-31`, `UNION_BARS[1440] = 4582` union stamps, plus the v0 exclusion (721 bars from 2024-07-17, zero hash overlap). **Do not record a whole-set row count as T0065 evidence** — the 1440 leaves sum to 34,460 over all 12 `ohlc-full` pairs and 29,032 over the 10-pair EUR basket (measured on disk 2026-08-08), and neither figure appears in T0065. T0065's argument covers the **daily** series only; do not widen it. Note also that 2 of its 38 citers (trials 33 and 35, `P1`) read daily **and** 4h, so the pin is narrower than some of the records pointing at it — say so in the evidence.
- `81dc9b44` — `unrecoverable`, `referent: null`. T0065 classes it an unresolved **4h primitive**, and nothing in the repo establishes a referent. Do **not** write "inherits" — only `45275ebe` inherits. Evidence records the negative: ~226,000 candidates tested, no driver ever committed.
- `45275ebe` — `inferred`, referent naming `data/ohlc-full` daily+4h with the INFERRED qualification; evidence names the two hashes it composes, that `81dc9b44` is unrecoverable so it cannot be recomputed, that the runbook's stated composition does **not** reproduce, and `tests/test_record44_legs.py`'s `UNION_BARS = {1440: 4582, 240: 27338}` as the actual extent evidence.

- [ ] **Step 4: Run to verify they pass**

- [ ] **Step 5: Commit** — stage **both** paths explicitly:

```bash
git add docs/reference/legacy-dataset-pins.jsonl tests/test_legacy_dataset_pins.py
```

`mutate-probe.sh` refuses on `git status --porcelain`, which reports untracked files too, so a forgotten `git add` here makes every Task 4 probe exit 3.

______________________________________________________________________

### Task 4: Prove the guards by construction

Runs after Tasks 1–3 are committed — `mutate-probe.sh` refuses a dirty tree. Only **Probe 4** needs a data-bearing host; every other probe rides tmp fixtures or the committed registry (Probe 2's control and mutation both bite tmp-fixture tests). On a bare checkout Probe 4's baseline skips-and-passes and its control cannot fail (rc 5), which is itself the finding.

**Verify each `-k` selector with `--collect-only -q` before running its probe.** `-k` is plain substring matching, not gapped, and these test names do not exist until this plan is executed — a near-miss silently deselects the only mutation-sensitive test and the probe returns a confident SURVIVED. Expected counts: Probe 3 → 2, Probe 4 → 4, Probe 5 → 2, Probe 6 → 3, Probe 7 → 8.

- [ ] **Step 1: The load-time derivation bites**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3})|' \
  --mutation 's|!= compute_hash(rec\["datasets"\])|!= rec["dataset_hash"]|' \
  -- uv run pytest tests/test_registry_store.py -q
```

Expected: `KILLED`. The control drops schema 4 from the loadable set, failing the round-trip test; the mutation makes the derivation check tautological, which the forged-record case carrying an inconsistent `dataset_hash` must catch.

- [ ] **Step 2: The allowlist refusal bites**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"ohlc-full": "backfill"|"ohlc-FULL": "backfill"|' \
  --mutation 's|if name == key or name.startswith(key + "-"):|if True:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

Expected: `KILLED`. The control breaks the exact-match key so every backfill test reds; the mutation makes any dataset resolve to the first adapter, so the refusal test reds.

- [ ] **Step 3: The declared slice actually resolves the extent**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|^def capture_datasets|def capture_datasets_RENAMED|' \
  --mutation 's|if _selected(pair, sel.get("pairs")) and _selected(interval, sel.get("intervals"))||' \
  -- uv run pytest tests/test_registry_provenance.py -k "declared_slice or each_axis" -q
```

Expected: `KILLED`. The control renames the function every test imports (ImportError, whole file reds); the mutation ignores the leaf filter, so `extent` collapses to the whole set — `test_backfill_shape_captures_the_declared_slice` pins `{"series": 1, "rows": 10, ...}` and `test_each_axis_is_independently_selectable_and_empty_means_all` pins `series == 2 and rows == 49` / `rows == 102`, so both red. (The blanked line stays inside the comprehension's brackets, so the file is still valid Python — a behaviour mutation, not a syntax error.)

**Do NOT aim this at the `different_declared_*` digest tests**: `select` is itself a hashed field of the block, so two records declaring different slices get different `dataset_hash` even when the extent collapses — those tests stay green under this mutation and would score it SURVIVED. The extent assertions are the ones the leaf filter actually moves.

- [ ] **Step 4: The on-disk conformance test can go red**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"manifest_sha256"|"manifest_sha256_ABSENT"|' \
  --mutation 's|rows = sum(leaf\["rows"\] for leaf in leaves)|rows = max(leaf["rows"] for leaf in leaves)|' \
  -- uv run pytest tests/test_registry_provenance.py -k "on_disk or measured_pin" -q
```

Expected: `KILLED`. This is the probe the previous version lacked: the on-disk test is the whole mechanism behind the spec's sustainability claim, and without a measured pin it passes for any non-empty manifest. `max` instead of `sum` leaves every other assertion true and moves only the pinned row counts — all three of them, so the probe does not hang on one dataset being present.

- [ ] **Step 5: Record 47 cannot be schema 3**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/store.py \
  --control 's|if rec\["prev_hash"\] != expected_prev:|if True:|' \
  --mutation 's|and rec\["schema_version"\] < 4:|and False:|' \
  -- uv run pytest tests/test_registry_store.py -k "past_the_legacy_floor or all_46" -q
```

Expected: `KILLED`. The control makes the chain check fire unconditionally, so `test_all_46_committed_records_still_load` reds — a control chosen to red *this selection*, not the deselected contiguity test. The mutation disables the floor, so the forged schema-3 record 47 loads clean while `test_all_46_committed_records_still_load` stays green: only the floor test can catch it, which is exactly why the selector must be verified first.

- [ ] **Step 6: The re-homed `dataset_hash` non-empty-str check bites**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|if type(rec.get("prev_hash")) is not str or len(rec\["prev_hash"\]) != 64:|if True:|' \
  --mutation 's|if type(rec.get("dataset_hash")) is not str or not rec\["dataset_hash"\]:|if False:|' \
  -- uv run pytest tests/test_registry_store.py -k "nonempty_str or all_46" -q
```

Expected: `KILLED`. This is the guard the key-set move silently strips (D3): every other stored body in the suite carries a valid `dataset_hash` and the derivation check binds only `>= 4`, so nothing else would notice its absence. The control makes the `prev_hash` check fire unconditionally, reddening `test_all_46_committed_records_still_load` within this selection; the mutation disables the re-homed check, so only the two schema-3 cases (`""` and `123`) can catch it.

- [ ] **Step 7: D2a's emptiness clause bites**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3})|' \
  --mutation 's|or not block\["select"\]:|:|' \
  -- uv run pytest tests/test_registry_store.py -k forged_schema_four -q
```

Expected: `KILLED`. The spec names the emptiness clauses as the ones carrying D2's property, so they need a constructed failure like every other guard. The control drops schema 4 from the loadable set, so every forged case raises `unknown schema_version` — matching none of the `match=` strings; the mutation keeps the type check and drops only the non-emptiness, so exactly the `"select": {}` case survives validation and reds. Confirm the collect count is **8** first: a selector collecting fewer means some parametrized cases were dropped and the probe proves less than it reports.

- [ ] **Step 8: Record every verdict.** A probe reporting `CONTROL mutation did not fail` means the harness does not bite — choose a control the probe must detect and re-run. Never record a verdict from an unproven harness.

______________________________________________________________________

### Task 5: Closeout

- [ ] **Step 1:** `docs/reference/data-catalog-full.md` — at its existing `dataset_hash` line, add: the registry's dataset reference is now a `datasets` block whose `select` is resolved per axis; the legacy table explains pre-4 hashes; the allowlist is named, including that its keys prefix-match re-freeze siblings.
  **Then state the supersession here, because it cannot be stated where the convention lives.** The "`dataset_hash` must equal record 1's, else STOP" gate is permanently unsatisfiable under schema 4 — the digest now hashes a declaration, not content — and its home `docs/specs/00035-combination-trial-design.md` is **immutable**: its sha256 `110b5a3479309f58…` is a committed `spec_hash` on a registry record, so per `spec-plan-locations.md` it can never be edited. Write the supersession as a positive line in `data-catalog-full.md` naming that unrepairable home, so a future trial author reading 00035 finds the correction rather than applying a gate that reads every new record as drift. The replacement is "declare the same `select` and compare the block", backed by the extent pins in `tests/test_crossfreq_system.py` and `tests/test_record44_legs.py`.
  Its other homes — `docs/plans/00035-combination-trial.md`, `docs/research/13.phase5-decisions.md` — are point-in-time records of executed work; leave them alone.

- [ ] **Step 2:** [[T0065]] — mark the going-forward sub-item done and retire its "`dataset_hash` == record 1's else STOP" line, pointing at Step 1's supersession; topic stays `partial` (the research-run command remains). **Do NOT edit `docs/reference/data-catalog.md`** — it is the retired v0 catalog (its own line 3 records the 2026-07-18 retirement and that the paths no longer exist), and its `dataset_hash` line names the per-frame content hash from `cli.ohlc.dataset.dataset_hash`, which schema 4 does not touch. Editing it would inject a false statement into a frozen record. [[T0132]] and [[T0133]] stay `open`; [[T0133]] was opened by this iteration (D5's holdout byte-coverage gap).
- [ ] **Step 3:** Iterations-history entry (phase 6 per `iteration-closeout`), naming the probe verdicts, D5's bounded claim, that a generic design failed four review rounds before the reshape, and that the on-disk conformance test plus Probe 4 are **workstation-only** — `data/` is gitignored, so CI skips them and a green CI branch has proven nothing about manifest shape.
- [ ] **Step 4:** Phase-6 decisions-log entry for D1 (allowlist over generality), D2 (per-axis `select`, resolved at capture — the pair axis is the one the registry's history varies on, and a resolved axis makes the block readable without the gitignored manifest), D3 (derived, store-owned) and D5 (do not rebuild byte verification here; register the holdout gap), each with options and the owner's pick.
- [ ] **Step 5:** Report ready. **Do not open the PR without the owner's explicit word.**
