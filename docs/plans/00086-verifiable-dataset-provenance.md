# Verifiable Dataset Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the trial registry's opaque, caller-supplied `dataset_hash` with a `datasets` block the store derives from each named dataset's manifest, so a future record's provenance cannot become unresolvable the way 44 of the 46 existing ones have.

**Architecture:** Schema 4 adds a `datasets` block carrying, per dataset, a `manifest_digest` (drift alarm), an `extent` (identifier), and a `select` (the slice read). `dataset_hash` becomes `compute_hash(datasets)`; both keys become store-owned, so the caller has no argument through which to supply either. `validate_stored_record` re-checks the round-trip on **every load**, because `append()` has no production caller. Historical hashes move into a committed, test-policed legacy table.

**Tech Stack:** Python 3.14, `cli/registry/` (`record.py`, `store.py`, new `provenance.py`), pytest, `infra/scripts/mutate-probe.sh`.

## Global Constraints

- Spec: `docs/specs/00086-verifiable-dataset-provenance-design.md`. Every decision reference below (D1–D6) is to that file.
- **The registry is append-only and hash-chained.** No task may rewrite, reorder or re-hash an existing record. `docs/reference/trial-registry.jsonl` is touched by NO task in this plan.
- **`cli/engine/command.py` and `cli/portfolio/record44_legs.py` read this registry at runtime via `TrialRegistry(path)`.** `TrialRegistry.__init__` keeps its single-argument signature; only `append()` gains parameters.
- `_LOADABLE_SCHEMA_VERSIONS` gains `4` and **keeps `2` and `3`**. All 46 committed records must keep loading unchanged; an absent `datasets` block below schema 4 is normal, never an error.
- **`_BASE_STORED_KEYS` is derived and is required of every record at every version** — `datasets` must never enter that derivation (D2). Verify after Task 1 that the real registry still loads before doing anything else.
- Follow the `variant` precedent: a key that does not apply is **omitted entirely**, never serialised as `null`. `select` is the exception and is always present — an empty list is the explicit "whole set" (D1).
- Error messages are operator-facing: no `T<NNNN>`, no `spec 00086`, no `iter-<N>` in any raised string (`.claude/rules/operator-facing-text.md`). Those tokens go in comments.
- Every guard is proven by `infra/scripts/mutate-probe.sh`, never asserted. The probe refuses a dirty tree, so all probes run in Task 5, after Tasks 1–4 are committed.
- Commit gate `uv run pre-commit run -a` before every commit; a rewriting run reports Failed and leaves rewrites unstaged — re-run, re-stage, re-commit.
- **No decisions-log entry is owed.** `.claude/rules/decisions-log.md` gates on a *subject-matter research* decision; this is registry engineering. Do not add one.
- **No README change is owed** — no CLI subcommand or option changes.

---

### Task 1: Schema 4 — the record shape, the store-owned split, and the load-time invariant

**Files:**

- Modify: `cli/registry/record.py` (`SCHEMA_VERSION`, `_LOADABLE_SCHEMA_VERSIONS`, the `_STORE_OWNED` split, `_REQUIRED_CALLER`, `_EXPECTED_STORED_KEYS`, `validate_caller_fields`, `validate_stored_record`, `TrialRecord`)
- Modify: `cli/registry/store.py` (`_to_record` only — it must carry the new field onto the dataclass)
- Test: `tests/test_registry_record.py`, `tests/test_registry_store.py`

**Interfaces:**

- Produces: `SCHEMA_VERSION = 4`; `TrialRecord.datasets: dict | None = None`; `dataset_hash` and `datasets` store-owned; `validate_stored_record` enforcing `compute_hash(rec["datasets"]) == rec["dataset_hash"]` for schema ≥ 4.
- Consumes: nothing from later tasks.

- [ ] **Step 1: Write the failing tests**

In `tests/test_registry_record.py`, first fix the existing helpers and bodies — this is mechanical and must be done in the same step or nothing else compiles:

- `_caller()` **drops** `dataset_hash="d"` (a caller may no longer supply it).
- Every stored-record body built from `_caller()` gains `dataset_hash="d"` explicitly (`test_stored_record_hash_and_schema_checks`, `test_stored_record_schema_version_variant_compat`, `test_stored_record_validation_stays_lenient_about_run_ref`).
- In `test_stored_record_schema_version_variant_compat`, `body_v3` must pin `schema_version=3` **literally** — it is a v3 compatibility test and `SCHEMA_VERSION` is about to become 4.
- `test_constants` asserts `SCHEMA_VERSION == 4`.
- `test_invalid_caller_rejected`'s parametrisation gains `{"dataset_hash": "d"}` and `{"datasets": {}}` — both are store-owned now.

Then add:

```python
_BLOCK = {
    "ohlc-x": {
        "select": ["1440"],
        "manifest_digest": "a" * 64,
        "extent": {"series": 1, "rows": 10, "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T00:00:00+00:00"]},
    }
}


def _v4_body(**over):
    body = dict(
        _caller(),
        trial_id=1,
        schema_version=4,
        timestamp="2026-07-07T00:00:00+00:00",
        prev_hash=GENESIS_HASH,
        run_ref=None,
        notes="",
        datasets=_BLOCK,
    )
    body["dataset_hash"] = compute_hash(body["datasets"])
    body.update(over)
    return dict(body, record_hash=compute_hash(body))


def test_a_schema_four_record_round_trips():
    validate_stored_record(_v4_body(), "x")


def test_schema_four_dataset_hash_must_equal_compute_hash_of_the_block():
    # The load-time invariant: a hand-written record cannot claim a digest it did not derive.
    with pytest.raises(RegistryCorruptionError, match="dataset_hash"):
        validate_stored_record(_v4_body(dataset_hash="d" * 64), "x")


def test_schema_four_requires_a_datasets_block():
    body = _v4_body()
    del body["datasets"]
    with pytest.raises(RegistryCorruptionError, match="datasets"):
        validate_stored_record(dict(body, record_hash=compute_hash({k: v for k, v in body.items() if k != "record_hash"})), "x")


@pytest.mark.parametrize(
    "block",
    [
        {},  # empty
        {"ohlc-x": "not-a-dict"},
        {"ohlc-x": {"select": [], "manifest_digest": "short", "extent": {}}},
        {"ohlc-x": {"select": [], "manifest_digest": "a" * 64}},  # no extent
        {"ohlc-x": {"manifest_digest": "a" * 64, "extent": {}}},  # no select
    ],
)
def test_a_malformed_datasets_block_is_corruption(block):
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(_v4_body(datasets=block, dataset_hash=compute_hash(block)), "x")


def test_pre_schema_four_records_still_load_and_carry_no_block():
    assert {2, 3, 4} <= _LOADABLE_SCHEMA_VERSIONS
    for version in (2, 3):
        body = dict(
            _caller(),
            trial_id=1,
            schema_version=version,
            timestamp="2026-07-07T00:00:00+00:00",
            prev_hash=GENESIS_HASH,
            dataset_hash="d",
            run_ref=None,
            notes="",
        )
        validate_stored_record(dict(body, record_hash=compute_hash(body)), "x")


def test_a_pre_four_record_carrying_a_datasets_block_is_corruption():
    body = dict(
        _caller(),
        trial_id=1,
        schema_version=3,
        timestamp="2026-07-07T00:00:00+00:00",
        prev_hash=GENESIS_HASH,
        dataset_hash="d",
        run_ref=None,
        notes="",
        datasets=_BLOCK,
    )
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(dict(body, record_hash=compute_hash(body)), "x")


def test_the_committed_registry_still_loads():
    # The whole point of the store-owned split: 46 live records, read at runtime by the engine.
    path = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        validate_stored_record(loads_strict(line), f"line {i}")
```

Add `_LOADABLE_SCHEMA_VERSIONS` and `pathlib.Path` to that file's imports (`RegistryCorruptionError` and `loads_strict` are already imported).

In `tests/test_registry_store.py`, `_line()` builds its body with `schema_version=SCHEMA_VERSION`. Change `_line()` to pin `schema_version=3` literally — it exists to exercise chain/contiguity mechanics, not schema 4 — and leave `_line_v2()` alone. Add:

```python
def test_registry_reads_a_schema_four_line(tmp_path):
    block = {"ohlc-x": {"select": [], "manifest_digest": "a" * 64, "extent": {"series": 1, "rows": 3}}}
    body = dict(
        trial_id=1,
        schema_version=4,
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        dataset_hash=compute_hash(block),
        datasets=block,
        seeds=[0],
        metrics={"sharpe": 0.3},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=None,
        notes="",
        prev_hash=GENESIS_HASH,
    )
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    assert TrialRegistry(_write(tmp_path, [line])).records[0].datasets == block
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`
Expected: FAIL — `SCHEMA_VERSION` is 3, `datasets` is an unknown key, no round-trip check exists.

- [ ] **Step 3: Implement in `cli/registry/record.py`**

Constants — the split is the load-bearing part (D2):

```python
SCHEMA_VERSION = 4
_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})

# Store-owned in EVERY version: these feed _BASE_STORED_KEYS, which is required of every record.
_STORE_OWNED_ALWAYS = ("trial_id", "schema_version", "timestamp", "prev_hash", "record_hash", "dataset_hash")
# Store-owned but schema-4 only: version-scoped in _EXPECTED_STORED_KEYS, exactly as `variant` is.
# It must NOT reach _BASE_STORED_KEYS or every pre-4 record fails the missing-key check.
_STORE_OWNED_V4 = ("datasets",)
_STORE_OWNED = _STORE_OWNED_ALWAYS + _STORE_OWNED_V4
_REQUIRED_CALLER = ("iteration", "family", "spec_hash", "seeds", "metrics", "n_trials_in_family", "verdict")

_BASE_STORED_KEYS = frozenset(_STORE_OWNED_ALWAYS) | frozenset(_REQUIRED_CALLER) | {"run_ref", "notes"}
_EXPECTED_STORED_KEYS = {
    2: _BASE_STORED_KEYS,
    3: _BASE_STORED_KEYS | {"variant"},
    4: _BASE_STORED_KEYS | {"variant", "datasets"},
}
```

`validate_caller_fields`: drop `dataset_hash` from the `for key in (...)` non-empty-str loop. Nothing else changes — the existing `supplied_owned` check now rejects a caller passing `dataset_hash` or `datasets`, and the existing `missing` check no longer demands `dataset_hash`.

`validate_stored_record`: add, after the `variant` checks and before the `record_hash` check —

```python
    if type(rec.get("dataset_hash")) is not str or not rec["dataset_hash"]:
        raise RegistryCorruptionError(f"{where}: dataset_hash must be a non-empty str")
    if version >= 4:
        _validate_datasets_block(rec.get("datasets"), where)
        if compute_hash(rec["datasets"]) != rec["dataset_hash"]:
            raise RegistryCorruptionError(f"{where}: dataset_hash is not compute_hash(datasets)")
```

and the module-level helper:

```python
def _validate_datasets_block(block, where: str) -> None:
    if type(block) is not dict or not block:
        raise RegistryCorruptionError(f"{where}: schema_version 4 record must carry a non-empty datasets dict")
    for name, entry in block.items():
        if type(entry) is not dict:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] must be a dict")
        if type(entry.get("manifest_digest")) is not str or len(entry["manifest_digest"]) != 64:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}].manifest_digest must be a 64-char str")
        if type(entry.get("extent")) is not dict or type(entry.get("select")) is not list:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] must carry an extent dict and a select list")
```

`TrialRecord`: add `datasets: dict | None = None` with a docstring line saying it is schema-4+ and that pre-4 records legitimately carry `None`.

In `cli/registry/store.py`, `_to_record` gains `datasets=rec.get("datasets")`. Nothing else in that file changes in this task.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`
Expected: PASS.

- [ ] **Step 5: Prove the live registry and its runtime readers are intact**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py tests/test_trial_registry_provenance.py tests/test_portfolio_builder.py tests/test_engine_command.py -q`
Expected: PASS. These are the tests that load the real 46-record file; a red here means the `_BASE_STORED_KEYS` split is wrong and must be fixed before proceeding.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run -a
git add cli/registry/record.py cli/registry/store.py tests/test_registry_record.py tests/test_registry_store.py
git commit -m "feat(registry): schema 4 carries a store-owned datasets block and checks its digest on load"
```

---

### Task 2: Capture the block from a manifest, whatever shape it is

**Files:**

- Create: `cli/registry/provenance.py`
- Test: `tests/test_registry_provenance.py`

**Interfaces:**

- Produces: `capture_datasets(selection: dict[str, list[str]], data_root: Path) -> dict` — the D1 block; raises `RegistryError` naming the offending path, dataset or token.
- Consumes: `cli.registry.record.compute_hash`, `cli.registry.errors.RegistryError`.

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path

import pytest

from cli.registry.errors import RegistryError
from cli.registry.provenance import capture_datasets

DATA = Path(__file__).resolve().parents[1] / "data"


def _write(root: Path, name: str, manifest: dict) -> None:
    (root / name).mkdir(parents=True)
    (root / name / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _nested(**extra):
    return {
        "fetched_at": "2026-07-07T21:17:30+00:00",
        "source": "somewhere",
        "basket_sha256": "b" * 64,
        "series": {
            "BTC/EUR": {
                "1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64},
                "240": {"rows": 60, "first_ts": "2020-01-01T04:00:00+00:00", "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "d" * 64},
            },
            "ETH/EUR": {
                "1440": {"rows": 5, "first_ts": "2019-01-01T00:00:00+00:00", "last_ts": "2019-01-06T00:00:00+00:00", "sha256": "e" * 64},
            },
        },
        **extra,
    }


def test_extent_counts_leaves_sums_rows_and_spans_the_union(tmp_path):
    # A max()-based rows would read 60 and a single-series span would hide the 2019 start.
    _write(tmp_path, "ohlc-x", _nested())
    got = capture_datasets({"ohlc-x": ["1440"]}, tmp_path)
    assert got["ohlc-x"]["extent"] == {
        "series": 3,
        "rows": 75,
        "span": ["2019-01-01T00:00:00+00:00", "2020-01-10T20:00:00+00:00"],
    }
    assert got["ohlc-x"]["select"] == ["1440"]
    assert len(got["ohlc-x"]["manifest_digest"]) == 64


def test_a_refetch_that_only_moves_the_timestamp_does_not_move_the_digest(tmp_path):
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", _nested(fetched_at="2026-08-08T00:00:00+00:00"))
    assert capture_datasets({"a": []}, tmp_path)["a"]["manifest_digest"] == capture_datasets({"b": []}, tmp_path)["b"]["manifest_digest"]


def test_a_content_change_does_move_the_digest(tmp_path):
    changed = _nested()
    changed["series"]["BTC/EUR"]["1440"]["rows"] = 11
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", changed)
    assert capture_datasets({"a": []}, tmp_path)["a"]["manifest_digest"] != capture_datasets({"b": []}, tmp_path)["b"]["manifest_digest"]


def test_a_flat_manifest_with_no_interval_level_is_captured(tmp_path):
    _write(tmp_path, "funding", {"fetched_at": "x", "basket_sha256": "b" * 64, "series": {
        "BTCUSDT": {"rows": 7, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-08T00:00:00+00:00", "sha256": "f" * 64}}})
    assert capture_datasets({"funding": ["BTCUSDT"]}, tmp_path)["funding"]["extent"]["series"] == 1


def test_a_list_shaped_manifest_is_captured_and_addressable(tmp_path):
    _write(tmp_path, "reach", {"built_at": "x", "basket_sha256": "b" * 64, "series": [
        {"symbol": "BTC", "interval": 1440, "status": "continuous", "rows": 4,
         "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-04T00:00:00+00:00", "sha256": "a" * 64}]})
    got = capture_datasets({"reach": ["1440", "BTC"]}, tmp_path)
    assert got["reach"]["extent"]["series"] == 1


def test_a_manifest_without_a_basket_hash_is_captured(tmp_path):
    # data/ohlc-holdout-2026-07-10 has no basket_sha256 and no per-series sha256 at all. It is the
    # deployable's out-of-sample evidence -- refusing it would disqualify the design.
    _write(tmp_path, "holdout", {"pulled_at": "2026-07-10T01:30Z", "manifest_sha256": "0" * 64, "series": {
        "BTC": {"rows": 4681, "first_ts": "2013-09-10 00:00:00+00:00", "last_ts": "2026-07-09 00:00:00+00:00", "appended": 100}}})
    got = capture_datasets({"holdout": ["BTC"]}, tmp_path)
    assert got["holdout"]["extent"]["span"] == ["2013-09-10T00:00:00+00:00", "2026-07-09T00:00:00+00:00"]


def test_capture_refuses_a_missing_manifest_and_names_the_path(tmp_path):
    with pytest.raises(RegistryError, match=r"ohlc-absent/manifest\.json"):
        capture_datasets({"ohlc-absent": []}, tmp_path)


def test_capture_refuses_a_manifest_with_no_series(tmp_path):
    _write(tmp_path, "empty", {"fetched_at": "x", "series": {}})
    with pytest.raises(RegistryError, match="series"):
        capture_datasets({"empty": []}, tmp_path)


def test_capture_refuses_an_unknown_select_token_and_names_it(tmp_path):
    _write(tmp_path, "ohlc-x", _nested())
    with pytest.raises(RegistryError, match="1441"):
        capture_datasets({"ohlc-x": ["1441"]}, tmp_path)


def test_the_block_is_sorted_and_stable(tmp_path):
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", _nested())
    assert list(capture_datasets({"b": [], "a": []}, tmp_path)) == ["a", "b"]


@pytest.mark.skipif(not (DATA / "ohlc-full").is_dir(), reason="compiled datasets absent")
@pytest.mark.parametrize(
    "name,series,rows",
    [
        ("ohlc-full", 36, 1052322),
        ("ohlc-15m", 12, 3122044),
        ("derivatives-funding", 10, 68281),
        ("ohlc-holdout-2026-07-10", 10, 30032),
    ],
)
def test_capture_matches_the_measured_extent_of_every_real_dataset(name, series, rows):
    if not (DATA / name / "manifest.json").is_file():
        pytest.skip(f"{name} absent")
    extent = capture_datasets({name: []}, DATA)[name]["extent"]
    assert (extent["series"], extent["rows"]) == (series, rows)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: FAIL — `cli.registry.provenance` does not exist.

- [ ] **Step 3: Implement `cli/registry/provenance.py`**

One walk produces both outputs; no second traversal, no per-shape branch beyond the one named constant:

```python
_VOLATILE_MANIFEST_KEYS = frozenset({"fetched_at", "pulled_at", "built_at"})
_LEAF_KEYS = frozenset({"rows", "first_ts", "last_ts"})
# The list-shaped manifest (cli/ohlc/reach.py) addresses its rows by these two fields instead of by
# nesting. This is the only per-shape knowledge in the module; everything else is structural.
_ROW_ADDRESS_KEYS = ("symbol", "interval")
```

`_walk_series(node, leaves, tokens)`: if `node` is a dict whose keys are a superset of `_LEAF_KEYS`, append it to `leaves`, add `str(node[k])` to `tokens` for each `_ROW_ADDRESS_KEYS` key present as a `str`/`int`, and **stop descending**; otherwise recurse over dict values (adding each dict key to `tokens`) and list items.

`capture_datasets(selection, data_root)`, for each name in `sorted(selection)`:

1. `path = Path(data_root) / name / "manifest.json"`; `RegistryError` naming `path` if it is not a file; `RegistryError` naming `path` if `json.loads` fails.
2. `series = manifest.get("series")`; `RegistryError` if falsy — name the dataset and say a manifest must carry a non-empty `series`.
3. Walk it. `RegistryError` if `leaves` is empty (a `series` with no `rows`/`first_ts`/`last_ts` leaf identifies nothing).
4. `unknown = [t for t in select if t not in tokens]`; `if unknown:` raise `RegistryError` naming the tokens and, to make the message actionable, `sorted(tokens)`.
5. `extent = {"series": len(leaves), "rows": sum(int(leaf["rows"]) for leaf in leaves)}`; over leaves whose `first_ts` and `last_ts` are both non-null, `extent["span"] = [datetime.fromisoformat(min(...)).isoformat(), datetime.fromisoformat(max(...)).isoformat()]` — omit `span` entirely when no leaf carries both (the `variant` omit-not-null precedent).
6. `manifest_digest = compute_hash({k: v for k, v in manifest.items() if k not in _VOLATILE_MANIFEST_KEYS})`.
7. Entry `{"select": list(select), "manifest_digest": ..., "extent": ...}`.

Return the dict built in sorted-name order. `canonical_json` sorts anyway; the sorted build is so the in-memory object a caller inspects matches the serialised one.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: PASS (the real-dataset parametrisation runs here, where `data/` is present).

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add cli/registry/provenance.py tests/test_registry_provenance.py
git commit -m "feat(registry): capture a dataset's provenance from its manifest, whatever shape it is"
```

---

### Task 3: `append()` derives the digest and has no argument for it

**Files:**

- Modify: `cli/registry/store.py` (`TrialRegistry.append`)
- Test: `tests/test_registry_store.py`

**Interfaces:**

- Produces: `append(*, ..., datasets: dict[str, list[str]], data_root: Path, ...) -> TrialRecord`; no `dataset_hash` parameter exists.
- Consumes: `capture_datasets` (Task 2), schema 4 (Task 1).

- [ ] **Step 1: Write the failing tests**

`tests/test_registry_store.py` already has a `registry` fixture (`TrialRegistry(tmp_path / "t.jsonl")`) and imports `json`. Add `inspect` to its imports. Every existing call to `.append(dataset_hash=...)` in that file is updated to `datasets={...}, data_root=...`; a test that *asserts* the old shape is a legitimate inversion, not a workaround. Add a manifest fixture and:

```python
@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    (root / "ohlc-x").mkdir(parents=True)
    (root / "ohlc-x" / "manifest.json").write_text(
        json.dumps({"fetched_at": "x", "series": {"BTC/EUR": {"1440": {
            "rows": 10, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-10T00:00:00+00:00"}}}}),
        encoding="utf-8",
    )
    return root


def _ok(**over):
    f = dict(iteration="iter-001", family="A1", spec_hash="s", seeds=[0],
             metrics={"sharpe": 0.3}, n_trials_in_family=1, verdict="adopt", run_ref="cli/registry/record.py")
    f.update(over)
    return f


def test_append_derives_the_dataset_hash_from_the_captured_block(registry, data_root):
    rec = registry.append(datasets={"ohlc-x": ["1440"]}, data_root=data_root, **_ok())
    assert rec.schema_version == 4
    assert rec.dataset_hash == compute_hash(rec.datasets)
    assert rec.datasets["ohlc-x"]["select"] == ["1440"]


def test_append_has_no_dataset_hash_parameter(registry, data_root):
    # The structural fix: not "validated", ABSENT. A caller cannot express a wrong provenance.
    assert "dataset_hash" not in inspect.signature(TrialRegistry.append).parameters
    with pytest.raises(TypeError):
        registry.append(dataset_hash="deadbeef", datasets={"ohlc-x": []}, data_root=data_root, **_ok())


def test_append_refuses_when_a_named_dataset_is_absent(registry, data_root):
    with pytest.raises(RegistryError, match="manifest"):
        registry.append(datasets={"ohlc-absent": []}, data_root=data_root, **_ok())
    assert len(registry) == 0  # nothing was written


def test_an_appended_record_reloads_from_disk(registry, data_root, tmp_path):
    written = registry.append(datasets={"ohlc-x": []}, data_root=data_root, **_ok())
    assert TrialRegistry(tmp_path / "t.jsonl").records[0] == written
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_store.py -q`
Expected: FAIL — `append` still takes `dataset_hash` and knows nothing of `data_root`.

- [ ] **Step 3: Implement**

In `TrialRegistry.append`: replace the `dataset_hash: str` parameter with `datasets: dict[str, list[str]]` and add `data_root: Path`. Build `caller` **without** either key (both are store-owned, so `validate_caller_fields(caller)` would reject them). After that validation and before the lock, call `captured = capture_datasets(datasets, data_root)` — capture must refuse before the file is opened, exactly as the non-finite-metric check already does. Then add both keys to the record body beside the other store-owned fields:

```python
            rec = {
                **caller,
                "trial_id": next_id,
                "schema_version": SCHEMA_VERSION,
                "timestamp": _now_utc_iso(),
                "datasets": captured,
                "dataset_hash": compute_hash(captured),
                "prev_hash": prev_hash,
            }
```

`record_hash` chaining, locking, healing and `_assert_cross_record` are untouched.

- [ ] **Step 4: Run the registry suite**

Run: `uv run pytest tests/ -q -k registry`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add cli/registry/store.py tests/test_registry_store.py
git commit -m "feat(registry): append derives dataset_hash from disk and drops the caller's parameter"
```

---

### Task 4: The legacy pins table

**Files:**

- Create: `docs/reference/legacy-dataset-pins.jsonl`
- Test: `tests/test_legacy_dataset_pins.py`

**Interfaces:**

- Produces: one line per distinct pre-schema-4 `dataset_hash`, shape per D5. **Every line starts with `{"dataset_hash": "` so a single pin is addressable by a line-anchored pattern** (Task 5 mutates one).
- Consumes: nothing.

- [ ] **Step 1: Write the failing tests**

```python
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PINS = REPO / "docs" / "reference" / "legacy-dataset-pins.jsonl"
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"


def _pins():
    return [json.loads(line) for line in PINS.read_text(encoding="utf-8").splitlines() if line.strip()]


def _historical():
    return {json.loads(line)["dataset_hash"] for line in REGISTRY.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line)["schema_version"] < 4}


def test_every_pre_schema_four_dataset_hash_is_pinned():
    # Regression protection, not completeness by construction: the historical set is frozen at four.
    unpinned = _historical() - {p["dataset_hash"] for p in _pins()}
    assert not unpinned, f"unpinned: {sorted(unpinned)}"


def test_the_table_pins_nothing_that_is_not_in_the_registry():
    assert {p["dataset_hash"] for p in _pins()} <= _historical()


def test_reproduced_entries_actually_reproduce():
    # `reproduced: true` is an executable claim, not a label. cccb8d17 is the only live case.
    checked = 0
    for pin in _pins():
        if pin["confidence"] != "reproduced":
            continue
        recipe = pin["recipe"]
        assert recipe["form"] == "sha256(a + ':' + b)", f"unknown recipe form {recipe['form']!r}"
        got = hashlib.sha256((recipe["a"] + ":" + recipe["b"]).encode()).hexdigest()
        assert got == pin["dataset_hash"]
        checked += 1
    assert checked == 1  # the claim is live, not vacuously satisfied by an empty table


def test_inferred_entries_do_not_claim_a_recipe():
    for pin in _pins():
        if pin["confidence"] == "inferred":
            assert pin["recipe"] is None and pin["reproduced"] is False


def test_every_pin_declares_a_known_confidence_and_a_referent():
    for pin in _pins():
        assert pin["confidence"] in {"inferred", "reproduced"}
        assert pin["reproduced"] is (pin["confidence"] == "reproduced")
        assert pin["referent"] and pin["notes"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_legacy_dataset_pins.py -q`
Expected: FAIL — the pins file does not exist.

- [ ] **Step 3: Write the four entries**

One JSON object per line, `dataset_hash` first, no trailing spaces (mdformat does not touch `.jsonl`; the whitespace hooks do).

- `ba47e37e2601d6098fd13c0e338a5301e8eeebb16bb4341c76a68147c7b08e42` — 38 records (A1 + P1). `referent: "data/ohlc-full"`, `basis: "extent"`, `confidence: "inferred"`, `reproduced: false`, `recipe: null`. `evidence`: daily rows `4581` for BTC/EUR over `2013-09-10 → 2026-03-31`; record 1's `run_ref` headline of 4581 returns, which is 4582 daily union stamps minus one (`UNION_BARS = {1440: 4582, 240: 27338}`, pinned in `tests/test_record44_legs.py`); and the exclusion of the only alternative daily dataset — the retired v0 REST seed, 721 bars from 2024-07-17, zero per-series hash overlap. `notes` must say in its own words that this is **identification by extent, not verification by digest** — an arithmetic match plus an exclusion, never a recomputation — and that ~226,000 candidate recipes were tested without a match on a method validated against two known targets.
- `81dc9b44f8897e38aacf78f00d3cffa12d54e724ccf0c9add0bced3fd5e1291f` — 4 records, the 4h primitive of the same dataset. Same treatment; `notes` records that it is carried as a literal operand inside `cccb8d17`'s recipe, so it is reproducible-by-citation but not traceable to bytes.
- `45275ebeb7986e3cca76e8ca8952f031256885e32b231fc782be0cd0d58871a7` — 2 records, record 44, the deployable. `confidence: "inferred"`, and `notes` must state that `docs/research/12.phase5-system-spec-runbook.md` describes it as `sha256(daily ‖ 4h)` **semantically**, that ~100 concatenation forms of `ba47e37e` and `81dc9b44` were tested and none reproduces it, and that the dataset is nevertheless pinned by the extent assertions in `tests/test_crossfreq_system.py` and `tests/test_record44_legs.py`.
- `cccb8d175d2038c462de57b295e9eb53ee2d51278e4110accfa350d93ced68b9` — 2 records. `confidence: "reproduced"`, `reproduced: true`, `basis: "recipe"`, `recipe: {"form": "sha256(a + ':' + b)", "a": "81dc9b44…", "b": "0fed24a6…"}` with both operands in full: `a` is the 4h primitive above, `b` is `data/ohlc-15m`'s `basket_sha256`. `notes`: it survived only because `docs/specs/00045-b1-seasonality-conditioning-design.md` wrote the recipe down — documentation discipline, which is why this table exists.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_legacy_dataset_pins.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add docs/reference/legacy-dataset-pins.jsonl tests/test_legacy_dataset_pins.py
git commit -m "docs(registry): pin every pre-schema-4 dataset hash in a test-policed legacy table"
```

---

### Task 5: Prove all six guards

**Files:** none — probes only. Runs AFTER Tasks 1–4 are committed; `mutate-probe.sh` refuses a dirty tree.

Each probe must print `KILLED`. If one reports **no-op sed** (rc 6), the committed text differs from the pattern — re-read the file and fix the pattern; never skip the probe. If one reports **CONTROL mutation did not fail** (rc 5), the harness does not bite — pick a control the probe must detect and re-run; do not record a verdict from an unproven harness.

- [ ] **Step 1: Load-time round-trip (D6-1)**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3})|' \
  --mutation 's|if compute_hash(rec\["datasets"\]) != rec\["dataset_hash"\]:|if False:|' \
  -- uv run pytest tests/test_registry_record.py -q
```

- [ ] **Step 2: No caller path to the digest (D6-2)**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|if type(f\["seeds"\]) is not list|if False and type(f["seeds"]) is not list|' \
  --mutation 's|for k in _STORE_OWNED if k in f|for k in () if k in f|' \
  -- uv run pytest tests/test_registry_record.py -q
```

- [ ] **Step 3: Capture refuses an absent manifest (D6-3)**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|sum(int(leaf\["rows"\]) for leaf in leaves)|max(int(leaf["rows"]) for leaf in leaves)|' \
  --mutation 's|if not path.is_file():|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 4: Capture refuses an unknown `select` token (D6-4)**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|if not path.is_file():|if False:|' \
  --mutation 's|if unknown:|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 5: Legacy completeness (D6-5)**

```bash
infra/scripts/mutate-probe.sh --file docs/reference/legacy-dataset-pins.jsonl \
  --control 's|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de0|' \
  --mutation '/^{"dataset_hash": "ba47e37e/d' \
  -- uv run pytest tests/test_legacy_dataset_pins.py -q
```

- [ ] **Step 6: Reproduced means reproduced (D6-6)**

```bash
infra/scripts/mutate-probe.sh --file docs/reference/legacy-dataset-pins.jsonl \
  --control '/^{"dataset_hash": "ba47e37e/d' \
  --mutation 's|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de0|' \
  -- uv run pytest tests/test_legacy_dataset_pins.py -q
```

- [ ] **Step 7: Record all six verdicts verbatim** for the closeout entry — the probe's own last line, not a paraphrase.

---

### Task 6: Closeout

- [ ] **Step 1: Full suite.** `uv run pytest` — expected PASS (~7 min with `data/ohlc-full` present, which is required here: Task 2's real-dataset parametrisation is the check that the design admits all four manifest shapes).

- [ ] **Step 2:** `docs/reference/data-catalog-full.md` — record the manifest contract the registry now depends on (a non-empty top-level `series`; series leaves carrying `rows`/`first_ts`/`last_ts`; a top-level timestamp key from `fetched_at`/`pulled_at`/`built_at`, which is excluded from `manifest_digest`), and point at `legacy-dataset-pins.jsonl` as where pre-schema-4 hashes are explained.

- [ ] **Step 3:** [[T0065]] via the `topic-ops` skill — the going-forward half of the execution-reproducibility sub-item is done; rewrite it into `## Done so far` as its outcome and remove it from `## Suggested next steps`. The topic stays `partial`: the committed research-run command and the fine-cadence reach round remain. Update `ripe_when` accordingly and re-check the index bullet.

- [ ] **Step 4:** Append the iterations-history entry (phase 6 → `docs/iterations-history-phase6.md`, per the `iteration-closeout` skill), naming the six probe verdicts, the accepted cost from D4 (a record can only be written where its data is present), and the residual gap from D4 (`select` is caller-asserted; closing it belongs to [[T0065]]'s research-run command).

- [ ] **Step 5:** Re-verify every status claim on the branch against the full branch log, then report the branch ready. **Do not open the PR without the owner's explicit word.**
