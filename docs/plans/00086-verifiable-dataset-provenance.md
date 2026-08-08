# Verifiable Dataset Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the trial registry's opaque, caller-supplied `dataset_hash` with a `datasets` block the store derives from each named dataset's manifest and re-derives from disk over the real file, so a future record's provenance cannot become unresolvable the way 44 of the 46 existing ones have.

**Architecture:** Schema 4 adds a `datasets` block carrying, per dataset, a normalised `select` (the slice read), a `series_digest` (drift alarm) and an `extent` (identifier). `dataset_hash` becomes `compute_hash(datasets)`; both keys become store-owned, so the caller has no argument through which to supply either, and the data root is a module constant rather than a parameter. Two guard layers: `validate_stored_record` re-checks the round-trip on **every load** (D3), and a repo-level test re-derives every schema-4 block from `data/` (D5). Historical hashes move into a committed, test-policed legacy table.

**Tech Stack:** Python 3.14, `cli/registry/` (`record.py`, `store.py`, new `provenance.py`), pytest, `infra/scripts/mutate-probe.sh`.

## Global Constraints

- Spec: `docs/specs/00086-verifiable-dataset-provenance-design.md`. Every decision reference below (D1–D7) is to that file.
- **The registry is append-only and hash-chained.** No task may rewrite, reorder or re-hash an existing record. `docs/reference/trial-registry.jsonl` is touched by NO task in this plan.
- **What reads the registry at runtime, measured — the constraint protects the right thing.** `cli/portfolio/record44_legs.py` constructs `TrialRegistry(path)` at two call sites and therefore goes through the loader: `TrialRegistry.__init__` keeps its single-argument signature and only `append()` changes shape. `cli/engine/command.py` does **not** construct a `TrialRegistry` — it hands `--registry` to `cli/engine/soak.py::_load_registry_record`, which `json.loads` the lines directly and reads only record 44's `metrics`. That path is unaffected by anything in Task 2, and equally uncovered by D3's invariant; the gap is pre-existing, out of scope, and registered in Task 6.
- `_LOADABLE_SCHEMA_VERSIONS` gains `4` and **keeps `2` and `3`**. All 46 committed records must keep loading unchanged; an absent `datasets` block below schema 4 is normal, never an error.
- **`_BASE_STORED_KEYS` is derived and is required of every record at every version** — `datasets` must never enter that derivation (D2). `dataset_hash` must stay in it (every record since schema 2 carries the key).
- **The schema bump and the writer land in ONE commit (Task 2).** `append()` writes `schema_version=SCHEMA_VERSION`; bumping the constant while leaving `append()` alone would make every record the writer produces unloadable by the validator in the same commit, redding ~8 append-then-reload tests and leaving the tree red for `mutate-probe.sh`, which refuses to run from a red or dirty tree.
- Follow the `variant` precedent: a key that does not apply is **omitted entirely**, never serialised as `null`. `select` is the exception and is always present — an empty list is the explicit "whole set" (D1). `extent["span"]` follows the `variant` precedent and is omitted when no series leaf carries both timestamps.
- Error messages are operator-facing: no `T<NNNN>`, no `spec 00086`, no `iter-<N>` in any raised string (`.claude/rules/operator-facing-text.md`). Those tokens go in comments.
- Every guard is proven by `infra/scripts/mutate-probe.sh`, never asserted. The probe refuses a dirty tree, so all probes run in Task 5, after Tasks 1–4 are committed. D5's layer is the one exception and is proven by its constructive companion test instead (D7).
- Commit gate `uv run pre-commit run -a` before every commit; a rewriting run reports Failed and leaves rewrites unstaged — re-run, re-stage, re-commit.
- **No decisions-log entry is owed.** `.claude/rules/decisions-log.md` gates on a *subject-matter research* decision; this is registry engineering. Do not add one.
- **No README change is owed** — no CLI subcommand or option changes.

---

### Task 1: Capture a dataset's provenance from its manifest, whatever shape it is

Ordered first deliberately: it changes no schema and touches no existing test, so the suite stays green and Task 2 has `capture_datasets` available in the same commit as the writer that needs it.

**Files:**

- Create: `cli/registry/provenance.py`
- Create: `tests/test_registry_provenance.py`

**Interfaces:**

- Produces: `DATA_ROOT: Path` (the repo's own `data/`); `capture_datasets(selection: dict[str, list[str]], data_root: Path) -> dict` — the D1 block; raises `RegistryError` naming the offending path, dataset or token.
- Consumes: `cli.registry.record.compute_hash`, `cli.registry.errors.RegistryError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_registry_provenance.py`:

```python
import json
from datetime import datetime

import pytest

from cli.registry.errors import RegistryError
from cli.registry.provenance import DATA_ROOT, capture_datasets


def _write(root, name, manifest):
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
    assert len(got["ohlc-x"]["series_digest"]) == 64


def test_select_is_normalised_so_one_read_has_one_digest(tmp_path):
    # canonical_json sorts dict keys but preserves list order, so an un-normalised select would give
    # one identical read two different dataset_hash values.
    _write(tmp_path, "ohlc-x", _nested())
    a = capture_datasets({"ohlc-x": ["240", "1440"]}, tmp_path)
    b = capture_datasets({"ohlc-x": ["1440", "240", "1440"]}, tmp_path)
    assert a == b
    assert a["ohlc-x"]["select"] == ["1440", "240"]


def test_only_the_series_subtree_is_digested(tmp_path):
    # Measured on the real manifests: data/ohlc-full and data/ohlc-15m spell the SAME source directory
    # relatively and absolutely. A whole-manifest digest would fire on that, and on reach.py's
    # top-level min_seam_overlap knob -- i.e. on exactly the refresh the alarm must stay quiet for.
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", _nested(fetched_at="2026-08-08T00:00:00+00:00", source="/abs/somewhere", min_seam_overlap=8))
    assert capture_datasets({"a": []}, tmp_path)["a"]["series_digest"] == capture_datasets({"b": []}, tmp_path)["b"]["series_digest"]


def test_a_content_change_does_move_the_digest(tmp_path):
    changed = _nested()
    changed["series"]["BTC/EUR"]["1440"]["sha256"] = "0" * 64
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", changed)
    assert capture_datasets({"a": []}, tmp_path)["a"]["series_digest"] != capture_datasets({"b": []}, tmp_path)["b"]["series_digest"]


def test_a_flat_manifest_with_no_interval_level_is_captured(tmp_path):
    _write(tmp_path, "funding", {"fetched_at": "x", "basket_sha256": "b" * 64, "series": {
        "BTCUSDT": {"rows": 7, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-08T00:00:00+00:00", "sha256": "f" * 64}}})
    assert capture_datasets({"funding": ["BTCUSDT"]}, tmp_path)["funding"]["extent"]["series"] == 1


def test_a_list_shaped_manifest_is_captured_and_addressable(tmp_path):
    # cli/ohlc/ingest.py and cli/ohlc/reach.py both emit this shape; the rows carry their own address.
    _write(tmp_path, "reach", {"built_at": "x", "basket_sha256": "b" * 64, "min_seam_overlap": 6, "series": [
        {"symbol": "BTC", "interval": 1440, "status": "continuous", "rows": 4,
         "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-04T00:00:00+00:00", "sha256": "a" * 64}]})
    got = capture_datasets({"reach": ["1440", "BTC"]}, tmp_path)
    assert got["reach"]["extent"]["series"] == 1


def test_a_manifest_without_any_per_series_digest_is_captured(tmp_path):
    # data/ohlc-holdout-2026-07-10 has no basket_sha256 and no per-series sha256 at all, and spells its
    # stamps with a space separator. It is the deployable's out-of-sample evidence -- refusing it would
    # disqualify the design, and a string min()/max() across the two spellings would be wrong.
    _write(tmp_path, "holdout", {"pulled_at": "2026-07-10T01:30Z", "manifest_sha256": "0" * 64, "series": {
        "BTC": {"rows": 4681, "first_ts": "2013-09-10 00:00:00+00:00", "last_ts": "2026-07-09 00:00:00+00:00",
                "appended": 100, "overlap_bars_verified": 621}}})
    got = capture_datasets({"holdout": ["BTC"]}, tmp_path)
    assert got["holdout"]["extent"]["span"] == ["2013-09-10T00:00:00+00:00", "2026-07-09T00:00:00+00:00"]


def test_capture_refuses_a_missing_manifest_and_names_the_path(tmp_path):
    with pytest.raises(RegistryError, match=r"ohlc-absent/manifest\.json"):
        capture_datasets({"ohlc-absent": []}, tmp_path)


def test_capture_refuses_an_unparseable_manifest(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RegistryError, match="JSON"):
        capture_datasets({"broken": []}, tmp_path)


def test_capture_refuses_a_manifest_with_no_series(tmp_path):
    _write(tmp_path, "empty", {"fetched_at": "x", "series": {}})
    with pytest.raises(RegistryError, match="series"):
        capture_datasets({"empty": []}, tmp_path)


def test_capture_refuses_a_series_with_no_identifiable_leaf(tmp_path):
    _write(tmp_path, "shapeless", {"fetched_at": "x", "series": {"BTC": {"sha256": "a" * 64}}})
    with pytest.raises(RegistryError, match="rows"):
        capture_datasets({"shapeless": []}, tmp_path)


def test_capture_refuses_an_unparseable_timestamp(tmp_path):
    _write(tmp_path, "bad-ts", {"fetched_at": "x", "series": {
        "BTC": {"rows": 1, "first_ts": "yesterday", "last_ts": "today"}}})
    with pytest.raises(RegistryError, match="timestamp"):
        capture_datasets({"bad-ts": []}, tmp_path)


def test_capture_refuses_an_unknown_select_token_and_names_it(tmp_path):
    _write(tmp_path, "ohlc-x", _nested())
    with pytest.raises(RegistryError, match="1441"):
        capture_datasets({"ohlc-x": ["1441"]}, tmp_path)


def test_the_block_is_built_in_sorted_name_order(tmp_path):
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", _nested())
    assert list(capture_datasets({"b": [], "a": []}, tmp_path)) == ["a", "b"]


def test_the_data_root_constant_points_at_the_repo_data_dir():
    # append() takes no data-root argument; this constant IS the root, and D5 re-derives against it.
    assert DATA_ROOT.name == "data" and (DATA_ROOT.parent / "pyproject.toml").is_file()


@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
@pytest.mark.parametrize(
    "name,series,rows,span",
    [
        ("ohlc-full", 36, 1052322, ["2013-09-10T00:00:00+00:00", "2026-03-31T23:00:00+00:00"]),
        ("ohlc-15m", 12, 3122044, ["2013-09-10T23:45:00+00:00", "2026-03-31T23:45:00+00:00"]),
        ("derivatives-funding", 10, 68281, ["2020-01-01T00:00:00+00:00", "2026-06-30T16:00:00.005000+00:00"]),
        ("ohlc-holdout-2026-07-10", 10, 30032, ["2013-09-10T00:00:00+00:00", "2026-07-09T00:00:00+00:00"]),
    ],
)
def test_capture_matches_the_measured_extent_of_every_real_dataset(name, series, rows, span):
    if not (DATA_ROOT / name / "manifest.json").is_file():
        pytest.skip(f"{name} absent")
    assert capture_datasets({name: []}, DATA_ROOT)[name]["extent"] == {"series": series, "rows": rows, "span": span}
    assert datetime.fromisoformat(span[0]) < datetime.fromisoformat(span[1])
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: FAIL at collection — `cli.registry.provenance` does not exist.

- [ ] **Step 3: Implement `cli/registry/provenance.py`**

One walk produces both outputs; no second traversal, no per-shape branch beyond the one named constant.

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cli.registry.errors import RegistryError
from cli.registry.record import compute_hash

# The one root a record may be captured from. Deliberately a constant and NOT an append() argument:
# `run_ref` anchors to _REPO_ROOT for the same reason -- a root the caller chooses is a root the caller
# can point at a hand-made manifest. It is also how the append-time and repo-level layers agree on
# what to compare (spec 00086 D4/D5).
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"  # cli/registry/provenance.py -> repo root

_LEAF_KEYS = frozenset({"rows", "first_ts", "last_ts"})
# The list-shaped manifests (cli/ohlc/ingest.py, cli/ohlc/reach.py) address their rows by these two
# fields instead of by nesting. This is the ONLY per-shape knowledge in the module.
_ROW_ADDRESS_KEYS = ("symbol", "interval")


def _walk(node, leaves: list[dict], tokens: set[str]) -> None:
    """Collect series leaves and the tokens that address them, without assuming a manifest shape."""
    if type(node) is dict:
        if _LEAF_KEYS <= node.keys():
            leaves.append(node)
            for key in _ROW_ADDRESS_KEYS:
                if type(node.get(key)) in (str, int):
                    tokens.add(str(node[key]))
            return  # a leaf's own fields are not addressing tokens
        for key, value in node.items():
            tokens.add(str(key))
            _walk(value, leaves, tokens)
    elif type(node) is list:
        for value in node:
            _walk(value, leaves, tokens)


def capture_datasets(selection: dict[str, list[str]], data_root: Path) -> dict:
    """The provenance block for each named dataset, read from its manifest. Refuses what it cannot verify."""
    out: dict = {}
    for name in sorted(selection):
        path = Path(data_root) / name / "manifest.json"
        if not path.is_file():
            raise RegistryError(f"no manifest at {path}: a trial can only be registered where the data it read is present")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RegistryError(f"{path} is not valid JSON: {e}") from e
        series = manifest.get("series")
        if not series:
            raise RegistryError(f"{path} carries no non-empty 'series': nothing in it identifies the data")
        leaves: list[dict] = []
        tokens: set[str] = set()
        _walk(series, leaves, tokens)
        if not leaves:
            raise RegistryError(f"{path}: no series entry carries all of {sorted(_LEAF_KEYS)}, so the data cannot be identified")
        select = sorted(set(selection[name]))
        unknown = [t for t in select if t not in tokens]
        if unknown:
            raise RegistryError(f"{path}: unknown select token(s) {unknown}; addressable tokens are {sorted(tokens)}")
        extent: dict = {"series": len(leaves), "rows": sum(int(leaf["rows"]) for leaf in leaves)}
        dated = [leaf for leaf in leaves if leaf["first_ts"] and leaf["last_ts"]]
        if dated:  # omit the key entirely rather than serialize a null, as `variant` does
            try:
                firsts = [datetime.fromisoformat(leaf["first_ts"]) for leaf in dated]
                lasts = [datetime.fromisoformat(leaf["last_ts"]) for leaf in dated]
                extent["span"] = [min(firsts).isoformat(), max(lasts).isoformat()]
            except (TypeError, ValueError) as e:
                raise RegistryError(f"{path}: unusable series timestamp: {e}") from e
        out[name] = {
            "select": select,
            # The series subtree ONLY: the whole manifest carries a `source` spelled two ways for one
            # directory and per-writer config knobs, so a whole-manifest digest fires on a re-fetch of
            # identical content (spec 00086 D1).
            "series_digest": compute_hash({"series": series}),
            "extent": extent,
        }
    return out
```

Sorted-name order is for the in-memory object a caller inspects; `canonical_json` sorts the serialised form regardless.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: PASS, with the four real-dataset cases **running, not skipping** (`data/` is present on the research machine — that parametrisation is the check that the design admits all four manifest shapes).

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add cli/registry/provenance.py tests/test_registry_provenance.py
git commit -m "feat(registry): capture a dataset's provenance from its manifest, whatever shape it is"
```

---

### Task 2: Schema 4 — the store-owned split, the load-time invariant, and the writer, in one commit

**Files:**

- Modify: `cli/registry/record.py` (`SCHEMA_VERSION`, `_LOADABLE_SCHEMA_VERSIONS`, the `_STORE_OWNED` split, `_REQUIRED_CALLER`, `_EXPECTED_STORED_KEYS`, `validate_caller_fields`, `validate_stored_record`, `_validate_datasets_block`, `TrialRecord`)
- Modify: `cli/registry/store.py` (`_to_record` and `TrialRegistry.append`)
- Modify: `tests/test_registry_record.py`
- Modify: `tests/test_registry_store.py`
- Modify: `tests/test_trial_registry_provenance.py` (its module-local `_caller()` only — see Step 1)

**Interfaces:**

- Produces: `SCHEMA_VERSION = 4`; `TrialRecord.datasets: dict | None = None`; `dataset_hash` and `datasets` store-owned; `validate_stored_record` enforcing `compute_hash(rec["datasets"]) == rec["dataset_hash"]` for schema ≥ 4; `append(*, ..., datasets: dict[str, list[str]], ...)` with no `dataset_hash` and no `data_root` parameter.
- Consumes: `capture_datasets`, `DATA_ROOT` (Task 1).

- [ ] **Step 1: Fix every existing test the schema bump touches**

Mechanical, and it must be complete before anything else — an unlisted file here is a red suite at commit time and a refused `mutate-probe.sh` in Task 5. The full list, each verified against the current file:

`tests/test_registry_record.py`

- `_caller()` **drops** `dataset_hash="d"` (a caller may no longer supply it).
- `test_constants` asserts `SCHEMA_VERSION == 4`.
- `test_invalid_caller_rejected`'s parametrisation gains `{"dataset_hash": "d"}` and `{"datasets": {}}` — both are store-owned now.
- Three stored-record tests build bodies from `_caller()` with `schema_version=SCHEMA_VERSION` and assert they VALIDATE. All three are **pre-4 compatibility** tests, so each gains an explicit `dataset_hash="d"` and pins `schema_version=3` **literally**: `test_stored_record_hash_and_schema_checks`, `test_stored_record_schema_version_variant_compat` (both `body_v2` — which pins 2 already but still needs `dataset_hash` — and `body_v3`), and `test_stored_record_validation_stays_lenient_about_run_ref`.
- Imports gain `_LOADABLE_SCHEMA_VERSIONS` from `cli.registry.record` and `Path` from `pathlib`.

`tests/test_registry_store.py`

- `_line()` pins `schema_version=3` literally (it exercises chain/contiguity mechanics, not schema 4) and keeps `dataset_hash="d"`. `_line_v2()` is untouched.
- Four more bodies pin `schema_version=SCHEMA_VERSION` and expect a pre-4 outcome — pin each literally to `3`: `test_v3_record_with_nonstr_variant_is_corruption`, `test_v3_unknown_key_forge_is_corruption`, `test_missing_base_key_is_corruption`, `test_v3_without_variant_still_loads`.
- The module-level helper `_append(reg, **over)` is where ~20 call sites reach `append()`: drop `dataset_hash="d"` from its `kw` dict and add `datasets={"ohlc-x": ["1440"]}`. No call site changes, and no `data_root` is threaded anywhere — `append()` has no such parameter (Step 3).
- `test_append_requires_run_ref_explicitly` calls `reg.append(...)` directly: swap its `dataset_hash="d"` for `datasets={"ohlc-x": []}`.
- Rename `test_mixed_v2_and_v3_file_loads_with_intact_chain` → `test_mixed_v2_and_v4_file_loads_with_intact_chain`; its appended record is now schema 4 and the `SCHEMA_VERSION` assertions in it stay correct unchanged.
- Imports gain `inspect` and `from cli.registry import store`.
- Add the autouse data-root fixture, which is what lets every existing `_append` call keep working:

```python
@pytest.fixture(autouse=True)
def _stub_data_root(tmp_path, monkeypatch):
    """append() reads a module constant, not an argument (spec 00086 D4). Point it at a two-series stub
    so every append test exercises the REAL capture path without needing the gitignored data/ tree."""
    root = tmp_path / "data"
    (root / "ohlc-x").mkdir(parents=True)
    (root / "ohlc-x" / "manifest.json").write_text(
        json.dumps({"fetched_at": "2026-07-07T00:00:00+00:00", "series": {"BTC/EUR": {
            "1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64},
            "240": {"rows": 20, "first_ts": "2020-01-01T04:00:00+00:00", "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "d" * 64}}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "DATA_ROOT", root)
    return root
```

`tests/test_trial_registry_provenance.py`

- Its **module-local** `_caller()` (the one near the bottom, beside `test_both_layers_agree_on_path_spelling`) supplies `dataset_hash="d"` and the test calls `validate_caller_fields(_caller(run_ref=spelling))` expecting no raise. Drop `dataset_hash="d"` from it. Nothing else in that file changes in this task.

- [ ] **Step 2: Write the new failing tests**

In `tests/test_registry_record.py`:

```python
_BLOCK = {
    "ohlc-x": {
        "select": ["1440"],
        "series_digest": "a" * 64,
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
    # The load-time invariant: a record cannot claim a digest it did not derive from its own block.
    with pytest.raises(RegistryCorruptionError, match="dataset_hash"):
        validate_stored_record(_v4_body(dataset_hash="d" * 64), "x")


def test_schema_four_requires_a_datasets_block():
    body = _v4_body()
    del body["record_hash"], body["datasets"]
    with pytest.raises(RegistryCorruptionError, match="datasets"):
        validate_stored_record(dict(body, record_hash=compute_hash(body)), "x")


@pytest.mark.parametrize(
    "block",
    [
        {},  # empty
        {"ohlc-x": "not-a-dict"},
        {"ohlc-x": {"select": [], "series_digest": "short", "extent": {}}},
        {"ohlc-x": {"select": [], "series_digest": "a" * 64}},  # no extent
        {"ohlc-x": {"series_digest": "a" * 64, "extent": {}}},  # no select
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


def test_the_committed_registry_still_loads_record_by_record():
    # The whole point of the store-owned split: 46 live records, one of which the deployable depends on.
    path = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 46
    for i, line in enumerate(lines, start=1):
        validate_stored_record(loads_strict(line), f"line {i}")
```

In `tests/test_registry_store.py`:

```python
def test_append_derives_the_dataset_hash_from_the_captured_block(tmp_path):
    r = _append(_new_registry(tmp_path))
    assert r.schema_version == 4
    assert r.dataset_hash == compute_hash(r.datasets)
    assert r.datasets["ohlc-x"]["extent"] == {
        "series": 2, "rows": 30,
        "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T20:00:00+00:00"],
    }
    assert TrialRegistry(tmp_path / "t.jsonl").records[0] == r  # survives write -> read -> re-validate


def test_append_offers_no_argument_for_the_digest_or_the_data_root(tmp_path):
    # The structural fix: not "validated", ABSENT. A caller can express neither a wrong provenance nor
    # a root to read it from.
    params = inspect.signature(TrialRegistry.append).parameters
    assert "dataset_hash" not in params and "data_root" not in params
    with pytest.raises(TypeError):
        _append(_new_registry(tmp_path), dataset_hash="deadbeef")


def test_append_normalises_the_selected_slice(tmp_path):
    r = _append(_new_registry(tmp_path), datasets={"ohlc-x": ["240", "1440", "1440"]})
    assert r.datasets["ohlc-x"]["select"] == ["1440", "240"]


def test_append_refuses_a_dataset_that_is_not_on_disk(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError, match="manifest"):
        _append(TrialRegistry(p), datasets={"ohlc-absent": []})
    assert not p.exists() or p.read_text() == ""  # refused BEFORE the file was opened


def test_append_refuses_an_unknown_select_token_before_writing(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError, match="1441"):
        _append(TrialRegistry(p), datasets={"ohlc-x": ["1441"]})
    assert not p.exists() or p.read_text() == ""
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`
Expected: FAIL — `SCHEMA_VERSION` is 3, `datasets` is an unknown key, `append` still takes `dataset_hash`, no round-trip check exists.

- [ ] **Step 4: Implement `cli/registry/record.py`**

Constants — the split is the load-bearing part (D2):

```python
SCHEMA_VERSION = 4
_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})

# Store-owned in EVERY version: these feed _BASE_STORED_KEYS, required of every record at every version.
# dataset_hash belongs here -- every record since schema 2 carries the key; only its OWNER changes.
_STORE_OWNED_ALWAYS = ("trial_id", "schema_version", "timestamp", "prev_hash", "record_hash", "dataset_hash")
# Store-owned but schema-4 only: version-scoped in _EXPECTED_STORED_KEYS, exactly as `variant` is.
# It must NOT reach _BASE_STORED_KEYS or all 46 committed records fail the missing-key check.
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

`validate_caller_fields`: drop `"dataset_hash"` from the `for key in ("iteration", "family", "spec_hash", "dataset_hash")` non-empty-str loop. Nothing else changes there — the existing `supplied_owned` check now rejects a caller passing `dataset_hash` or `datasets`, and the existing `missing` check no longer demands `dataset_hash`.

`validate_stored_record`: insert after the `variant` checks and before the `record_hash` check —

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
        if type(entry.get("series_digest")) is not str or len(entry["series_digest"]) != 64:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}].series_digest must be a 64-char str")
        if type(entry.get("extent")) is not dict or type(entry.get("select")) is not list:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] must carry an extent dict and a select list")
```

`TrialRecord`: add `datasets: dict | None = None`, with a docstring line saying it is schema-4+ and that pre-4 records legitimately carry `None`.

**Then implement `cli/registry/store.py` in the same commit.** `_to_record` gains `datasets=rec.get("datasets")`. `TrialRegistry.append` replaces its `dataset_hash: str` parameter with `datasets: dict[str, list[str]]`, adds no other parameter, and imports `DATA_ROOT`/`capture_datasets` from `cli.registry.provenance`. Build `caller` **without** either store-owned key, then capture after `validate_caller_fields(caller)` and before the lock — a refusal must land before the file is opened, exactly as the non-finite-metric check already does:

```python
        validate_caller_fields(caller)  # raises on non-finite metric BEFORE opening the file
        captured = capture_datasets(datasets, DATA_ROOT)  # ...and refuses unverifiable provenance here
        lock_f = open(self.path, "a", encoding="utf-8")
```

and add both keys beside the other store-owned fields in the record body:

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

`record_hash` chaining, locking, healing and `_assert_cross_record` are untouched. Update the `TrialRegistry` class docstring's "loads schema v2+v3, writes v3" clause to v2+v3+v4 / writes v4.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`
Expected: PASS.

- [ ] **Step 6: Prove the live registry and its runtime reader are intact**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py tests/test_trial_registry_provenance.py tests/test_portfolio_builder.py tests/test_record44_legs.py -q`
Expected: PASS. These load the real 46-record file. Diagnose by which assertion fires, not by the file: a *missing required key* red means `datasets` leaked into `_BASE_STORED_KEYS`; an *unknown key* red means the `4:` entry is missing from `_EXPECTED_STORED_KEYS`; a *store-owned field* red in `test_trial_registry_provenance.py` means its module-local `_caller()` still supplies `dataset_hash` (Step 1).

- [ ] **Step 7: Commit**

```bash
uv run pre-commit run -a
git add cli/registry/record.py cli/registry/store.py tests/test_registry_record.py tests/test_registry_store.py tests/test_trial_registry_provenance.py
git commit -m "feat(registry): schema 4 derives dataset_hash from a captured datasets block"
```

---

### Task 3: Layer 2 — re-derive every schema-4 block from disk, over the real registry

Without this the load-time check is self-referential: a hand-writer who invents a block and calls `compute_hash` on it satisfies D3 forever, and a hand-written record is the normal case (D3/D5).

**Files:**

- Modify: `tests/test_trial_registry_provenance.py`

**Interfaces:**

- Produces: `_rederivation_mismatches(records) -> set[int]` plus two tests — the standing assertion over the real file, and the constructive companion that proves the check bites while zero schema-4 records exist.
- Consumes: `capture_datasets`, `DATA_ROOT` (Task 1); schema 4 (Task 2).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_trial_registry_provenance.py` (its imports gain `pytest`, `RegistryError`, and `DATA_ROOT`/`capture_datasets`), and extend the module docstring's two-layer paragraph to say the same split now guards `datasets`. Write the two tests **without** the helper they call, so the red is real:

```python
@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
def test_no_schema_four_record_carries_a_block_that_does_not_re_derive():
    # Layer 2. The load-time check proves a record is internally consistent; only this one compares the
    # block to the data. A dataset legitimately refreshed after a record was written also lands here --
    # append-only means the record cannot be repaired, so pin the ids and the refresh, as
    # LEGACY_UNCOMMITTED does above; never widen the check to make the red go away.
    stale = _rederivation_mismatches(_records())
    assert stale == set(), f"trial(s) {sorted(stale)} carry a datasets block that does not re-derive from data/"


@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
def test_the_re_derivation_check_bites_before_any_schema_four_record_exists():
    # Constructive proof, in the same shape as the run_ref one above: the standing assertion is vacuous
    # until the first schema-4 record lands, and a vacuous guard is a decoration.
    honest = capture_datasets({"ohlc-full": ["1440"]}, DATA_ROOT)
    assert _rederivation_mismatches([{"trial_id": 900, "schema_version": 4, "datasets": honest}]) == set()

    forged = {"ohlc-full": {**honest["ohlc-full"], "series_digest": "0" * 64}}
    assert _rederivation_mismatches([{"trial_id": 901, "schema_version": 4, "datasets": forged}]) == {901}

    inflated = {"ohlc-full": {**honest["ohlc-full"], "extent": {**honest["ohlc-full"]["extent"], "rows": 1}}}
    assert _rederivation_mismatches([{"trial_id": 902, "schema_version": 4, "datasets": inflated}]) == {902}

    invented = {"ohlc-nowhere": {"select": [], "series_digest": "0" * 64, "extent": {}}}
    assert _rederivation_mismatches([{"trial_id": 903, "schema_version": 4, "datasets": invented}]) == {903}

    # ...and a pre-4 record is out of scope for this layer, not silently "passing" it.
    assert _rederivation_mismatches(_records()) == set()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_trial_registry_provenance.py -q`
Expected: FAIL — `NameError: name '_rederivation_mismatches' is not defined` in both new tests, and every pre-existing test in the file still PASSES.

- [ ] **Step 3: Implement the helper**

```python
def _rederivation_mismatches(records: list[dict]) -> set[int]:
    """Trial ids whose stored `datasets` block does not re-derive from what is on disk today."""
    out: set[int] = set()
    for rec in records:
        if rec.get("schema_version", 0) < 4:
            continue
        selection = {name: entry["select"] for name, entry in rec["datasets"].items()}
        try:
            captured = capture_datasets(selection, DATA_ROOT)
        except RegistryError:  # an invented dataset name refuses at the manifest, which IS a mismatch
            out.add(rec["trial_id"])
            continue
        if captured != rec["datasets"]:
            out.add(rec["trial_id"])
    return out
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_trial_registry_provenance.py -q`
Expected: PASS with both new tests **running, not skipping**. A skip on the research machine means `DATA_ROOT` is wrong — fix that before proceeding, since a silently-skipped provenance guard is the failure class this whole change is about.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add tests/test_trial_registry_provenance.py
git commit -m "test(registry): re-derive every schema-4 datasets block from disk over the real registry"
```

---

### Task 4: The legacy pins table

**Files:**

- Create: `docs/reference/legacy-dataset-pins.jsonl`
- Create: `tests/test_legacy_dataset_pins.py`

**Interfaces:**

- Produces: one line per distinct pre-schema-4 `dataset_hash`, shape per D6. **Every line starts with `{"dataset_hash": "` so a single pin is addressable by a line-anchored pattern** (Task 5 mutates one).
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
    records = [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["dataset_hash"] for r in records if r["schema_version"] < 4}


def test_every_pre_schema_four_dataset_hash_is_pinned():
    # Regression protection, not completeness by construction: the historical set is frozen at four the
    # moment SCHEMA_VERSION is 4, so this asserts over constants and is worth exactly that.
    unpinned = _historical() - {p["dataset_hash"] for p in _pins()}
    assert not unpinned, f"unpinned: {sorted(unpinned)}"
    assert len(_historical()) == 4


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
        assert hashlib.sha256((recipe["a"] + ":" + recipe["b"]).encode()).hexdigest() == pin["dataset_hash"]
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

- `ba47e37e2601d6098fd13c0e338a5301e8eeebb16bb4341c76a68147c7b08e42` — 38 records (32 v2 + 6 v3). `referent: "data/ohlc-full"`, `basis: "extent"`, `confidence: "inferred"`, `reproduced: false`, `recipe: null`. `evidence`: daily rows `4581` for BTC/EUR over `2013-09-10 → 2026-03-31`; record 1's `run_ref` headline of 4581 returns, which is 4582 daily union stamps minus one (`UNION_BARS = {1440: 4582, 240: 27338}`, pinned in `tests/test_record44_legs.py`); and the exclusion of the only alternative daily dataset — the retired v0 REST seed, 721 bars from 2024-07-17, zero per-series hash overlap. `notes` must say in its own words that this is **identification by extent, not verification by digest** — an arithmetic match plus an exclusion, never a recomputation — and that ~226,000 candidate recipes were tested without a match, on a method validated against two known targets.
- `81dc9b44f8897e38aacf78f00d3cffa12d54e724ccf0c9add0bced3fd5e1291f` — 4 records, the 4h primitive of the same dataset. Same treatment; `notes` records that it is carried as a literal operand inside `cccb8d17`'s recipe, so it is reproducible-by-citation but not traceable to bytes.
- `45275ebeb7986e3cca76e8ca8952f031256885e32b231fc782be0cd0d58871a7` — 2 records, record 44, the deployable. `confidence: "inferred"`, and `notes` must state that `docs/research/12.phase5-system-spec-runbook.md` describes it as `sha256(daily ‖ 4h)` **semantically**, that ~100 concatenation forms of `ba47e37e` and `81dc9b44` were tested and none reproduces it, and that the dataset is nevertheless pinned by the extent assertions in `tests/test_crossfreq_system.py` and `tests/test_record44_legs.py`.
- `cccb8d175d2038c462de57b295e9eb53ee2d51278e4110accfa350d93ced68b9` — 2 records. `confidence: "reproduced"`, `reproduced: true`, `basis: "recipe"`, `recipe: {"form": "sha256(a + ':' + b)", "a": "81dc9b44f8897e38aacf78f00d3cffa12d54e724ccf0c9add0bced3fd5e1291f", "b": "0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1"}` — `a` is the 4h primitive above, `b` is `data/ohlc-15m`'s `basket_sha256`, both verbatim. `notes`: it survived only because `docs/specs/00045-b1-seasonality-conditioning-design.md` wrote the recipe down — documentation discipline, which is why this table exists.

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

### Task 5: Prove the six mutate-probe guards

**Files:** none — probes only. Runs AFTER Tasks 1–4 are committed; `mutate-probe.sh` refuses a dirty tree and refuses to score anything from a tree whose probe does not pass unmutated.

Each probe must print `KILLED`. Diagnose by exit code, never by re-running blind: **rc 6** (no-op sed) means the committed text differs from the pattern — re-read the file and fix the pattern; **rc 5** (control did not fail) means the harness does not bite — pick another control, verify by reading which test the control would break, and re-run; **rc 7** means the tree is red before any mutation. Never record a verdict from an unproven harness.

Controls below were each chosen against a specific existing test that must break. That reasoning is stated so a rc-5 can be diagnosed rather than guessed at.

- [ ] **Step 1: Load-time round-trip (D7-1)**

Control breaks `test_invalid_caller_rejected[{"verdict": "maybe"}]`, which then stops raising.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|if f\["verdict"\] not in VERDICTS:|if False:|' \
  --mutation 's|if compute_hash(rec\["datasets"\]) != rec\["dataset_hash"\]:|if False:|' \
  -- uv run pytest tests/test_registry_record.py -q
```

- [ ] **Step 2: No caller path to the digest (D7-2)**

Control breaks `test_seeds_may_be_empty_but_metrics_may_not` and `test_invalid_caller_rejected[{"metrics": {}}]` — an empty dict passes `_assert_finite` without raising, so both stop raising.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|if type(f\["metrics"\]) is not dict or not f\["metrics"\]:|if False:|' \
  --mutation 's|for k in _STORE_OWNED if k in f|for k in () if k in f|' \
  -- uv run pytest tests/test_registry_record.py -q
```

- [ ] **Step 3: Capture refuses an absent manifest (D7-3)**

Control breaks `test_extent_counts_leaves_sums_rows_and_spans_the_union` (75 becomes 60). The mutation makes the missing file surface as a bare `FileNotFoundError`, which `pytest.raises(RegistryError)` does not catch.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|sum(int(leaf\["rows"\]) for leaf in leaves)|max(int(leaf["rows"]) for leaf in leaves)|' \
  --mutation 's|if not path.is_file():|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 4: Capture refuses an unknown `select` token (D7-4)**

Control breaks `test_select_is_normalised_so_one_read_has_one_digest` (the two spellings stop agreeing).

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|select = sorted(set(selection\[name\]))|select = list(selection[name])|' \
  --mutation 's|if unknown:|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 5: Legacy completeness (D7-5)**

Control corrupts the `cccb8d17` recipe's `b` operand, breaking `test_reproduced_entries_actually_reproduce`.

```bash
infra/scripts/mutate-probe.sh --file docs/reference/legacy-dataset-pins.jsonl \
  --control 's|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de0|' \
  --mutation '/^{"dataset_hash": "ba47e37e/d' \
  -- uv run pytest tests/test_legacy_dataset_pins.py -q
```

- [ ] **Step 6: Reproduced means reproduced (D7-6)**

Same pair, swapped: control deletes the `ba47e37e` pin (breaking completeness), mutation corrupts the recipe operand.

```bash
infra/scripts/mutate-probe.sh --file docs/reference/legacy-dataset-pins.jsonl \
  --control '/^{"dataset_hash": "ba47e37e/d' \
  --mutation 's|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de0|' \
  -- uv run pytest tests/test_legacy_dataset_pins.py -q
```

- [ ] **Step 7: Record all six verdicts verbatim** for the closeout entry — each probe's own last line, not a paraphrase. D5's layer carries no probe here by design (D7): its constructive companion in Task 3 is the constructed failure.

---

### Task 6: Closeout

- [ ] **Step 1: Full suite.** `uv run pytest` — expected PASS (~7 min with `data/ohlc-full` present, which is required here: Task 1's real-dataset parametrisation and Task 3's whole layer both need it).

- [ ] **Step 2:** `docs/reference/data-catalog-full.md` — record the manifest contract the registry now depends on (a non-empty top-level `series`; series leaves carrying `rows`/`first_ts`/`last_ts`; parseable ISO timestamps), that only the `series` subtree is digested and why, and point at `legacy-dataset-pins.jsonl` as where pre-schema-4 hashes are explained.

- [ ] **Step 3:** Register the soak-read gap as its own topic via the `topic-ops` skill, and queue it in `docs/memo.local.md` in the same edit (registration and queue insertion travel together): `cli/engine/soak.py::_load_registry_record` reads `docs/reference/trial-registry.jsonl` with raw `json.loads` and pulls record 44's `metrics` without any chain, `record_hash` or schema validation — the live engine's instrument self-test trusts a file it never checks. Pre-existing, not introduced here.

- [ ] **Step 4:** [[T0065]] via the `topic-ops` skill — the going-forward half of the execution-reproducibility sub-item is done; rewrite it into `## Done so far` as its outcome and remove it from `## Suggested next steps`. The topic stays `partial`: the committed research-run command and the fine-cadence reach round remain. Update `ripe_when` accordingly and re-check the index bullet.

- [ ] **Step 5:** Append the iterations-history entry (phase 6 → `docs/iterations-history-phase6.md`, per the `iteration-closeout` skill), naming the six probe verdicts, the two-layer split, the accepted cost from D4 (a record can only be written where its data sits under the repo's own `data/`), and the residual gap from D4 (`select` is caller-asserted; closing it belongs to [[T0065]]'s research-run command).

- [ ] **Step 6:** Re-verify every status claim on the branch against the full branch log, then report the branch ready. **Do not open the PR without the owner's explicit word.**
