# Verifiable Dataset Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a trial record's dataset reference self-describing and machine-checkable, for the datasets that actually back trials, so no future `dataset_hash` becomes unresolvable the way 44 existing ones have.

**Architecture:** Two per-shape adapters capture a `datasets` block (per-axis declared slice + set digest + extent) for an allowlist of three datasets; `dataset_hash` becomes `compute_hash(datasets)`; `dataset_hash` moves into the store-owned key set so no caller can supply it; and `validate_stored_record` enforces both the block's shape and the derivation at LOAD, since `append()` has no production caller.

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

- Produces: `capture_datasets(select: dict[str, dict[str, list[str]]], data_root: Path) -> dict` returning the D2 block; `ALLOWLIST: dict[str, str]` mapping dataset name (or prefix, for `ohlc-holdout-*`) to adapter name. Raises `RegistryError` on an unlisted dataset, an absent manifest, an unknown axis key, or a token that matches nothing.
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


def test_select_is_normalised_so_order_and_duplicates_cannot_move_the_digest(tmp_path):
    _full(tmp_path)
    a = capture_datasets({"ohlc-full": {"intervals": ["240", "1440", "240"]}}, tmp_path)
    b = capture_datasets({"ohlc-full": {"intervals": ["1440", "240"]}}, tmp_path)
    assert a == b and a["ohlc-full"]["select"] == {"intervals": ["1440", "240"]}


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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: FAIL — `cli.registry.provenance` does not exist.

- [ ] **Step 3: Implement**

`ALLOWLIST = {"ohlc-full": "backfill", "ohlc-15m": "backfill", "ohlc-holdout-": "holdout"}` — exact match first, then prefix match, so `ohlc-holdout-<date>` resolves. Resolution goes through a helper whose match line is quoted verbatim by Task 4 Probe 2:

```python
    for key, adapter in ALLOWLIST.items():
        if name == key or (key.endswith("-") and name.startswith(key)):
```

Anything unmatched raises `RegistryError` whose message contains the word `adapter` and the dataset name.

**Axes.** Backfill declares `("pairs", "intervals")` and walks `series[pair][interval]`; holdout declares `("assets",)` and walks `series[asset]` (one level). A `select` key outside the adapter's axes raises, naming the offending key and the allowed axes. Within an axis, an empty or absent list means all of it; a token matching no key on that axis raises, naming the token.

The backfill leaf walk is quoted verbatim by Probe 3, so write the filter as its own line:

```python
    leaves = [
        leaf
        for pair, by_interval in series.items()
        for interval, leaf in by_interval.items()
        if _selected(pair, sel.get("pairs")) and _selected(interval, sel.get("intervals"))
    ]
```

`extent` per D2, in one shared helper over the selected leaves — `rows = sum(leaf["rows"] for leaf in leaves)` verbatim (Probe 4 quotes it), `series` = `len(leaves)`, `span` = `[min(first_ts), max(last_ts)]` as **raw strings** (the holdout's stamps use a space, not `T`; do not parse or normalise them — a round-trip through a datetime would silently change the recorded value). Sort each `select` axis list and drop duplicates. Emit **only** `select`, `set_digest`, `extent`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: PASS.

- [ ] **Step 5: Add the on-disk conformance tests**

Enumerate from disk, not from a hardcoded tuple — a set present but unlisted must be visible. **Skip, never pass, on an empty glob**: `data/` is gitignored except its own `.gitignore` (`git ls-files data/` returns exactly that one file), so on a bare CI checkout `_DATA.exists()` is TRUE and the glob is EMPTY — a bare `for` loop would report a green having asserted nothing.

```python
_DATA = Path(__file__).resolve().parent.parent / "data"
_HOLDOUT = "ohlc-holdout-2026-07-10"


def _listed(name: str) -> bool:
    return name in ALLOWLIST or any(name.startswith(k) for k in ALLOWLIST if k.endswith("-"))


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


@pytest.mark.skipif(not (_DATA / _HOLDOUT / "manifest.json").is_file(), reason="frozen holdout absent")
def test_the_frozen_holdout_extent_matches_its_measured_pin():
    # The holdout is frozen, so its extent is pinnable; ohlc-full/ohlc-15m grow on every backfill
    # and deliberately get no row pin. Measured 2026-08-08.
    assert capture_datasets({_HOLDOUT: {}}, _DATA)[_HOLDOUT]["extent"] == {
        "series": 10, "rows": 30032,
        "span": ["2013-09-10 00:00:00+00:00", "2026-07-09 00:00:00+00:00"]}
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

Expected: `loaded 46 schema versions [2, 3]`. Anything else — a `RegistryError`, a `KeyError`, a short count — means the move is wrong; fix it here, before schema 4 exists. Then `uv run pytest tests/test_registry_store.py -q` to confirm the loader half is intact (append-side tests still red until Step 3).

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


def test_all_46_committed_records_still_load():
    """The defect that sank the first attempt. Assert against the REAL file, not a fixture."""
    reg = TrialRegistry(Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl")
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


def _schema4_line(**over):
    body = dict(
        trial_id=1, schema_version=4, timestamp="2026-08-08T00:00:00+00:00", iteration="iter-001",
        family="A1", spec_hash="s", seeds=[0], metrics={"dsr": 0.1}, n_trials_in_family=1,
        verdict="adopt", run_ref=None, notes="", prev_hash=GENESIS_HASH,
        datasets={"ohlc-full": {"select": {"intervals": ["1440"]}, "set_digest": "a" * 64,
                                "extent": {"series": 1, "rows": 10, "span": ["2020-01-01", "2020-01-10"]}}},
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
```

Run: `uv run pytest tests/test_registry_store.py -q` — expected FAIL.

- [ ] **Step 3: Implement the rest**

`cli/registry/record.py`:

- `SCHEMA_VERSION = 4`; `_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})`.
- `_EXPECTED_STORED_KEYS = {2: _BASE_STORED_KEYS, 3: _BASE_STORED_KEYS | {"variant"}, 4: _BASE_STORED_KEYS | {"variant", "datasets"}}`. That entry only *permits* `datasets`; it does not require it — the surplus check is a superset test and the missing check is over `_BASE_STORED_KEYS`.
- `validate_caller_fields` gains a `datasets` shape check **only when the key is present** (`if "datasets" in f: ...`), so schema-2/3 stored records keep validating. Its `_REQUIRED_CALLER` sweep must not name `datasets`.
- `validate_stored_record` gains, for **every** version, the non-empty-str check on `rec["dataset_hash"]` that `validate_caller_fields` used to perform — it no longer sees the key, so without this the guard silently lapses for schema 2/3.
- `validate_stored_record`, for `version >= 4`, in order, each raising its own `RegistryCorruptionError` **whose message contains `datasets` or `dataset_hash`** (the tests match on those): (a) `datasets` present; (b) `_validate_datasets_shape(rec["datasets"], where)` — non-empty `dict`; each value a dict with **exactly** `{select, set_digest, extent}`; `select` a `dict[str, list[str]]` whose lists are sorted and deduplicated; `set_digest` 64-char lowercase hex; `extent` exactly `{series: int, rows: int, span: [str, str]}` (D2a — no disk access, no axis-name knowledge); (c) the derivation, written verbatim as `rec["dataset_hash"] != compute_hash(rec["datasets"])` because Probe 1 seds that text. Order matters: (a) before (c), or (c) raises a bare `KeyError`.
- `TrialRecord` gains `datasets: dict | None = None`.

`cli/registry/store.py`:

- `_to_record` passes `datasets=rec.get("datasets")` — without it the field is always `None` and the round-trip test fails silently.
- `TrialRegistry.__init__(self, path, *, data_root: Path | None = None)`, stored on the instance. **No `cli.config` default** — resolving it there would make a plain read of the registry raise `ConfigError` on an unconfigured host, and there is no production `append()` caller to serve. `append()` raises `RegistryError` naming `data_root` when it is `None`.
- `append()` drops `dataset_hash`, gains `datasets: dict[str, dict[str, list[str]]]`, calls `capture_datasets(datasets, self._data_root)`, puts the captured block in `caller["datasets"]`, and sets `rec["dataset_hash"] = compute_hash(caller["datasets"])` **after** `validate_caller_fields` (it is store-owned now).

- [ ] **Step 4: Update every existing test that constructs a record**

`tests/test_registry_record.py`:

- `test_constants`: `SCHEMA_VERSION == 3` → `== 4`.
- `_caller()`: drop `dataset_hash="d"` — it is store-owned, so `validate_caller_fields(_caller())` would now refuse it.
- `test_invalid_caller_rejected`: add the case `{"dataset_hash": "d"}` beside `{"trial_id": 9}` — same rule, newly applicable.
- Every stored body built from `_caller()` — in `test_stored_record_hash_and_schema_checks`, `test_stored_record_schema_version_variant_compat` (all three bodies, including the literal-`2` one), and `test_stored_record_validation_stays_lenient_about_run_ref` — must now add `dataset_hash="d"` explicitly and pin `schema_version=3` instead of `SCHEMA_VERSION`. They are v3-semantics tests; left on `SCHEMA_VERSION` they become schema-4 bodies with no `datasets` and pass or fail for the wrong reason.

`tests/test_registry_store.py` — the same v3 pin, and it is the trap in this task. Six construction sites:

- `_line` (`schema_version=SCHEMA_VERSION` → literal `3`) and `_line_v2` (already `2`; both keep `dataset_hash="d"`, which is legal in a *stored* body).
- The four inline bodies in `test_v3_record_with_nonstr_variant_is_corruption`, `test_v3_unknown_key_forge_is_corruption`, `test_missing_base_key_is_corruption`, `test_v3_without_variant_still_loads`: pin `schema_version=3`. Left on `SCHEMA_VERSION` the last one fails outright and the other three keep **passing for the wrong reason** — they would raise on the missing `datasets`, silently retiring the variant / forge / missing-base-key guards they exist to pin. Step 6's full-suite run cannot detect that; only this pin can.
- `_append`: drop `dataset_hash="d"`, add `datasets={"ohlc-full": {}}`.
- `_new_registry(tmp_path)`: `TrialRegistry(tmp_path / "t.jsonl", data_root=_data_root(tmp_path))`. Every site that builds `TrialRegistry(p)` inline and then calls `_append` must route through `_new_registry` instead — `test_append_assigns_contiguous_ids_across_reopen`, `test_append_rejects_nonfinite_before_writing`, `test_append_family_count_floor`, `test_append_then_records_snapshot`, `test_concurrent_registries_get_unique_ids`, `test_append_after_torn_trailing_line_self_heal`, `test_append_with_variant_round_trips`, `test_append_without_variant_omits_key_from_raw_line`, `test_append_rejects_invalid_variant_before_writing`, `test_mixed_v2_and_v3_file_loads_with_intact_chain`, `test_append_records_a_committed_run_ref_end_to_end`, `test_append_rejects_unprovenanced_run_ref_before_writing`, `test_variant_does_not_affect_family_budget_monotonic_check`. Confirm the list with `grep -n "TrialRegistry(" tests/test_registry_store.py` rather than trusting it.
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
    """A careless grep must not return a bare path that reads as verified fact."""
    for pin in _pins():
        assert pin["confidence"] in ("reproduced", "inferred", "unrecoverable")
        if pin["confidence"] == "inferred":
            assert "INFERRED" in pin["referent"]
        if pin["confidence"] == "unrecoverable":
            assert pin["referent"] is None
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Write the four entries**, taking every claim from `docs/open-topics/T0065-...md`'s measured table and asserting nothing beyond it:

- `cccb8d17` — `reproduced`, evidence `operands` = the 4h and 15m hex operands, recipe `sha256(hex_4h + ":" + hex_15m)`.
- `ba47e37e` — `inferred`, referent `"data/ohlc-full daily (INFERRED from extent + exclusion — never recomputed)"`, evidence = 1440 `rows 34460`, span `2013-09-10 → 2026-03-31`, plus the v0 exclusion (721 bars from 2024-07-17, zero hash overlap). T0065's argument covers the **daily** series only; do not widen it.
- `81dc9b44` — `unrecoverable`, `referent: null`. T0065 classes it an unresolved **4h primitive**, and nothing in the repo establishes a referent. Do **not** write "inherits" — only `45275ebe` inherits. Evidence records the negative: ~226,000 candidates tested, no driver ever committed.
- `45275ebe` — `inferred`, referent naming `data/ohlc-full` daily+4h with the INFERRED qualification; evidence names the two hashes it composes, that `81dc9b44` is unrecoverable so it cannot be recomputed, that the runbook's stated composition does **not** reproduce, and `tests/test_record44_legs.py`'s `UNION_BARS = {1440: 4582, 240: 27338}` as the actual extent evidence.

- [ ] **Step 4: Run to verify they pass**

- [ ] **Step 5: Commit**

______________________________________________________________________

### Task 4: Prove the guards by construction

Runs after Tasks 1–3 are committed — `mutate-probe.sh` refuses a dirty tree. Probes 2–4 read `data/`, so they need a data-bearing host; on a bare checkout Probe 4's baseline skips-and-passes and its control cannot fail (rc 5), which is itself the finding.

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
  --mutation 's|if name == key or (key.endswith("-") and name.startswith(key)):|if True:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

Expected: `KILLED`. The control breaks the exact-match key so every backfill test reds; the mutation makes any dataset resolve to the first adapter, so the refusal test reds.

- [ ] **Step 3: The declared slice actually discriminates**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|^def capture_datasets|def capture_datasets_RENAMED|' \
  --mutation 's|if _selected(pair, sel.get("pairs")) and _selected(interval, sel.get("intervals"))||' \
  -- uv run pytest tests/test_registry_store.py -k different_declared -q
```

Expected: `KILLED`. The control breaks the import `store.py` performs; the mutation ignores `select` entirely, so both axes collapse to the whole set and both `different_declared_*` tests red. (The blanked line stays inside the comprehension's brackets, so the file is still valid Python — that is what makes it a behaviour mutation rather than a syntax error.)

- [ ] **Step 4: The on-disk conformance test can go red**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"manifest_sha256"|"manifest_sha256_ABSENT"|' \
  --mutation 's|rows = sum(leaf\["rows"\] for leaf in leaves)|rows = max(leaf["rows"] for leaf in leaves)|' \
  -- uv run pytest tests/test_registry_provenance.py -k "on_disk or holdout_extent" -q
```

Expected: `KILLED`. This is the probe the previous version lacked: the on-disk test is the whole mechanism behind the spec's sustainability claim, and without a measured pin it passes for any non-empty manifest. `max` instead of `sum` leaves every other assertion true and moves only the pinned row count.

- [ ] **Step 5: Record every verdict.** A probe reporting `CONTROL mutation did not fail` means the harness does not bite — choose a control the probe must detect and re-run. Never record a verdict from an unproven harness.

______________________________________________________________________

### Task 5: Closeout

- [ ] **Step 1:** `docs/reference/data-catalog-full.md` — the registry's dataset reference is a `datasets` block with a per-axis `select`; the legacy table explains pre-4 hashes; the allowlist is named.
- [ ] **Step 2:** [[T0065]] — mark the going-forward sub-item done; topic stays `partial` (the research-run command remains). [[T0132]] and [[T0133]] stay `open`; [[T0133]] was opened by this iteration (D5's holdout byte-coverage gap).
- [ ] **Step 3:** Iterations-history entry (phase 6 per `iteration-closeout`), naming the probe verdicts, D5's bounded claim, and that a generic design failed four review rounds before the reshape.
- [ ] **Step 4:** Phase-6 decisions-log entry for D1 (allowlist over generality), D2 (per-axis `select`, because the pair axis is the one the registry's history varies on), D3 (derived, store-owned) and D5 (do not rebuild byte verification here; register the holdout gap), each with options and the owner's pick.
- [ ] **Step 5:** Report ready. **Do not open the PR without the owner's explicit word.**
