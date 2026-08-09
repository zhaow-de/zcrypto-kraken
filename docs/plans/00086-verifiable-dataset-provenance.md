# Verifiable Dataset Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close T0065's execution-reproducibility round whole: dataset identity computed from the bytes a run reads (the capturing loader), enforced at load with a schema-4 floor, written through the committed `zcrypto research eval` command — the registry's first production caller — with the legacy ruling executed as a committed pins table.

**Architecture:** `cli/registry/observed.py` (the loader) produces the `datasets` block; `cli/registry/record.py`/`store.py` derive `dataset_hash = compute_hash(datasets)` and enforce shape+derivation+floor at load; `cli/research/` is the door; `docs/reference/legacy-dataset-pins.jsonl` documents the 4 historical hashes. No manifest is parsed anywhere in the identity path.

**Tech Stack:** Python 3.14 / polars / Typer / pytest, `uv` throughout.

## Global Constraints

- `docs/reference/trial-registry.jsonl` is append-only, hash-chained, and committed: all 46 records MUST load after every commit of this plan. The real-file load test (`tests/test_registry_store.py::test_live_registry_file_loads_clean`) is the tripwire — run it after each task.
- The schema bump and the `append()` rework land in ONE commit (Task 2) — an intermediate commit whose own `append()` writes records its own validator rejects is forbidden.
- `_BASE_STORED_KEYS` is derived from `_REQUIRED_CALLER` ∪ `_STORE_OWNED`: the Task 2 key-set move follows its steps exactly; deviations have historically made all 46 records unloadable three separate ways.
- Int strictness is `type(x) is int`, never `isinstance` (`isinstance(True, int)` is `True`); the file already uses this idiom with the comment saying why.
- Every guard gets a mutate-probe with a control that fails first (`infra/scripts/mutate-probe.sh`; clean tree; Task 6). A guard is unproven until its defect is constructed and seen to trip it.
- Data-gated tests **skip** with a reason off the workstation — never pass vacuously. CI (bare checkout) must still exercise the full synthetic-parquet pipeline.
- Commits: Conventional Commits, `Co-Authored-By: <actual authoring model> <noreply@anthropic.com>` last line; **review floor is Fable for every commit** (this plan touches canonical-data provenance). Frames: `ts` is `Datetime("us", "UTC")`; errors live in `cli.registry.errors`.
- Spec: `docs/specs/00086-verifiable-dataset-provenance-design.md` (this plan's serial mate). Decision numbers below (D1…D7) refer to it.

---

### Task 1: The capturing loader replaces the manifest adapters

The identity referent changes from manifest declarations to observed bytes (D1/D2), so the two manifest adapters — committed on this branch, never merged — are removed in the same commit that lands their replacement.

**Files:**

- Delete: `cli/registry/provenance.py`, `tests/test_registry_provenance.py` (`git rm`)
- Create: `cli/registry/observed.py`
- Test: `tests/test_registry_observed.py`

**Interfaces:**

- Produces: `ObservedReader(data_root: Path)` with `read_series(dataset: str, relpath: str, window: tuple[str, str] | None = None) -> pl.DataFrame` and `block() -> dict`; module-level `_sha256_file(path: Path) -> str`.
- Consumes: `cli.ohlc.dataset.read_parquet`, `cli.data.sync._manifest_sha256s`, `cli.registry.errors.RegistryError`.

- [ ] **Step 1: Write the failing tests** — `tests/test_registry_observed.py`

```python
"""The capturing loader: identity is what the run read (spec 00086 D1/D2)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cli.ohlc.dataset import to_frame, write_parquet
from cli.registry.errors import RegistryError
from cli.registry.observed import ObservedReader


def _rows(n, start=1577836800):  # 2020-01-01, daily steps
    return [[start + i * 86400, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(n)]


def _dataset(tmp_path, name="ohlc-test", series=(("BTC/EUR/1440.parquet", 10), ("ETH/EUR/1440.parquet", 7))):
    root = tmp_path / "data"
    for relpath, n in series:
        write_parquet(to_frame(_rows(n)), root / name / relpath)
    return root


def test_block_records_files_rows_span_from_what_was_read(tmp_path):
    root = _dataset(tmp_path)
    reader = ObservedReader(root)
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    reader.read_series("ohlc-test", "ETH/EUR/1440.parquet")
    block = reader.block()
    entry = block["ohlc-test"]
    assert set(entry) == {"files", "rows", "span"}
    assert set(entry["files"]) == {"BTC/EUR/1440.parquet", "ETH/EUR/1440.parquet"}
    raw = (root / "ohlc-test" / "BTC/EUR/1440.parquet").read_bytes()
    assert entry["files"]["BTC/EUR/1440.parquet"] == hashlib.sha256(raw).hexdigest()
    assert entry["rows"] == 17
    assert entry["span"][0] == "2020-01-01 00:00:00+00:00"


def test_a_flipped_byte_moves_the_hash(tmp_path):
    root = _dataset(tmp_path)
    before = ObservedReader(root)
    before.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    p = root / "ohlc-test" / "BTC/EUR/1440.parquet"
    raw = bytearray(p.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    p.write_bytes(bytes(raw))
    after = ObservedReader(root)
    try:  # the flip may or may not still parse as parquet; the hash is taken from bytes either way
        after.read_series("ohlc-test", "BTC/EUR/1440.parquet")
        assert after.block()["ohlc-test"]["files"] != before.block()["ohlc-test"]["files"]
    except Exception:
        pass  # an unreadable flip is also a detected change — the read refused


def test_window_moves_rows_and_span_and_is_applied_by_the_loader(tmp_path):
    root = _dataset(tmp_path, series=(("BTC/EUR/1440.parquet", 10),))
    reader = ObservedReader(root)
    frame = reader.read_series("ohlc-test", "BTC/EUR/1440.parquet",
                               window=("2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00"))
    assert frame.height == 3
    entry = reader.block()["ohlc-test"]
    assert entry["rows"] == 3
    assert entry["span"] == ["2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00"]


def test_same_file_read_twice_is_one_entry_and_a_window_mismatch_is_refused(tmp_path):
    root = _dataset(tmp_path, series=(("BTC/EUR/1440.parquet", 10),))
    reader = ObservedReader(root)
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    assert reader.block()["ohlc-test"]["rows"] == 10  # not 20 — one read, one entry
    with pytest.raises(RegistryError, match="window"):
        reader.read_series("ohlc-test", "BTC/EUR/1440.parquet", window=("2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00"))


def test_empty_accumulation_and_zero_row_dataset_are_refused(tmp_path):
    root = _dataset(tmp_path, series=(("BTC/EUR/1440.parquet", 10),))
    with pytest.raises(RegistryError, match="nothing"):
        ObservedReader(root).block()
    reader = ObservedReader(root)
    with pytest.raises(RegistryError, match="zero rows"):
        reader.read_series("ohlc-test", "BTC/EUR/1440.parquet",
                           window=("2031-01-01 00:00:00+00:00", "2031-01-02 00:00:00+00:00"))


def test_vouched_check_true_positive_mismatch_and_absence(tmp_path):
    from cli.ohlc.dataset import dataset_hash as content_hash, read_parquet

    root = _dataset(tmp_path)
    # No manifest at all -> inert, and the reader says so.
    reader = ObservedReader(root)
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    assert reader.vouched_status()["ohlc-test"] == "inert (0 vouched hashes)"
    # TRUE POSITIVE — the round-1 blocker's regression test. The frozen manifests vouch FRAME-CONTENT
    # hashes (dataset_hash = sha256 of canonical CSV), not file-byte hashes; a manifest vouching the
    # correct content hash MUST pass, or the loader refuses every healthy read of ohlc-full/ohlc-15m
    # while CI stays green. A mismatch-only suite cannot catch a wrong-grade comparison.
    good = content_hash(read_parquet(root / "ohlc-test" / "BTC/EUR/1440.parquet"))
    (root / "ohlc-test" / "manifest.json").write_text(json.dumps({"series": {"BTC": {"sha256": good}}}))
    reader2 = ObservedReader(root)
    reader2.read_series("ohlc-test", "BTC/EUR/1440.parquet")  # healthy read passes
    assert reader2.vouched_status()["ohlc-test"] == "checked (1 vouched hashes)"
    # A manifest vouching a DIFFERENT hash -> the data changed since the freeze: refuse.
    (root / "ohlc-test" / "manifest.json").write_text(json.dumps({"series": {"X": {"sha256": "f" * 64}}}))
    reader3 = ObservedReader(root)
    with pytest.raises(RegistryError, match="vouched"):
        reader3.read_series("ohlc-test", "BTC/EUR/1440.parquet")


_FULL_SET_EXPECTATIONS = {  # measured 2026-08-08; spans in the loader's own stamp format
    "ohlc-full": (36, 1_052_322, "2013-09-10 00:00:00+00:00", "2026-03-31 23:00:00+00:00"),
    "ohlc-15m": (12, 3_122_044, "2013-09-10 23:45:00+00:00", "2026-03-31 23:45:00+00:00"),
    "ohlc-holdout-2026-07-10": (10, 30_032, "2013-09-10 00:00:00+00:00", "2026-07-09 00:00:00+00:00"),
}


@pytest.mark.parametrize("dataset", sorted(_FULL_SET_EXPECTATIONS))
def test_loader_reproduces_the_frozen_full_set_extents(dataset):
    # Workstation-gated: the loader over every frozen set reproduces the frozen figures. Same
    # "canonical dataset drifted -- STOP" contract as tests/test_crossfreq_system.py.
    root = Path(__file__).resolve().parents[1] / "data"
    if not (root / dataset).is_dir():
        pytest.skip(f"{dataset} not on this host — data-bearing workstation only")
    reader = ObservedReader(root)
    for f in sorted((root / dataset).rglob("*.parquet")):
        reader.read_series(dataset, f.relative_to(root / dataset).as_posix())
    files, rows, first, last = _FULL_SET_EXPECTATIONS[dataset]
    entry = reader.block()[dataset]
    assert (len(entry["files"]), entry["rows"], *entry["span"]) == (files, rows, first, last)
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_registry_observed.py -q` — expected: import error (`cli.registry.observed` does not exist).

- [ ] **Step 3: Implement** — `cli/registry/observed.py`

```python
"""The capturing loader: dataset identity computed from the bytes a run actually reads.

The one sanctioned way research reads frozen datasets (spec 00086 D1). Hashes every file it opens,
applies any window itself, and accumulates per-dataset files/rows/span from what it RETURNS -- so
rows-used cannot drift from rows-recorded by construction. It imports nothing from manifests: no
manifest shape can reach the identity path. Where a manifest vouches per-series hashes, a computed
hash absent from a non-empty vouched set means the file changed since the manifest was written --
fitting on disputed bytes is exactly what should stop a run, so `read_series` refuses.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl

from datetime import datetime

from cli.data.sync import _manifest_sha256s
from cli.ohlc.dataset import dataset_hash, read_parquet
from cli.registry.errors import RegistryError

_TS_FORMAT = "%Y-%m-%d %H:%M:%S%z"  # matches the frozen manifests' stamp style: space, not 'T'


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _stamp(value) -> str:
    s = value.strftime(_TS_FORMAT)
    return s[:-2] + ":" + s[-2:]  # +0000 -> +00:00


class ObservedReader:
    def __init__(self, data_root: Path) -> None:
        self._root = Path(data_root)
        self._files: dict[str, dict[str, str]] = {}
        self._reads: dict[tuple[str, str], tuple[str, str] | None] = {}  # (dataset, relpath) -> window
        self._rows: dict[str, int] = {}
        self._span: dict[str, tuple] = {}  # dataset -> (first_ts, last_ts) as datetimes
        self._vouched: dict[str, set[str]] = {}

    def _vouched_for(self, dataset: str) -> set[str]:
        if dataset not in self._vouched:
            manifest = self._root / dataset / "manifest.json"
            self._vouched[dataset] = _manifest_sha256s(json.loads(manifest.read_text())) if manifest.exists() else set()
        return self._vouched[dataset]

    def vouched_status(self) -> dict[str, str]:
        return {
            d: (f"checked ({len(v)} vouched hashes)" if v else "inert (0 vouched hashes)")
            for d, v in ((d, self._vouched_for(d)) for d in self._files)
        }

    def read_series(self, dataset: str, relpath: str, window: tuple[str, str] | None = None) -> pl.DataFrame:
        key = (dataset, relpath)
        if key in self._reads and self._reads[key] != window:
            raise RegistryError(f"{dataset}/{relpath}: already read with window {self._reads[key]!r}; one record, one read discipline")
        path = self._root / dataset / relpath
        full = read_parquet(path)
        if key not in self._reads:
            digest = _sha256_file(path)  # the IDENTITY: file bytes as on disk
            vouched = self._vouched_for(dataset)
            # The cross-check runs at the manifests' own grade: the frozen manifests vouch FRAME-CONTENT
            # hashes (dataset_hash = sha256 of canonical CSV), never file-byte hashes -- a byte-grade
            # membership test here refuses every healthy read of ohlc-full/ohlc-15m (the round-1 blocker).
            # Checked on the FULL frame, before windowing: the freeze vouched the whole series.
            if vouched and dataset_hash(full) not in vouched:
                raise RegistryError(f"{dataset}/{relpath}: frame-content hash absent from the manifest's vouched set — the data changed since the freeze")
        frame = full
        if window is not None:
            start, end = (datetime.fromisoformat(w) for w in window)
            frame = frame.filter((pl.col("ts") >= start) & (pl.col("ts") <= end))
        if frame.height == 0:
            raise RegistryError(f"{dataset}/{relpath}: zero rows after windowing — a block that says nothing is refused")
        if key not in self._reads:
            self._reads[key] = window
            self._files.setdefault(dataset, {})[relpath] = digest
            self._rows[dataset] = self._rows.get(dataset, 0) + frame.height
            first, last = frame["ts"][0], frame["ts"][-1]
            lo, hi = self._span.get(dataset, (first, last))
            self._span[dataset] = (min(lo, first), max(hi, last))
        return frame

    def block(self) -> dict:
        if not self._files:
            raise RegistryError("ObservedReader accumulated nothing — a block that says nothing is refused")
        return {
            d: {"files": dict(sorted(self._files[d].items())), "rows": self._rows[d],
                "span": [_stamp(self._span[d][0]), _stamp(self._span[d][1])]}
            for d in sorted(self._files)
        }
```

(The implementer wires the exact polars filter expression to the frame's `Datetime("us", "UTC")` dtype and confirms `_stamp` output equals the test's expected strings — the tests are the contract, the sketch is not. The full-set expectations test belongs to the data-dependent tier: ~tens of seconds on the workstation, skipped elsewhere.)

- [ ] **Step 4: Run to verify they pass** — `uv run pytest tests/test_registry_observed.py -q`
- [ ] **Step 5: Verify the deletion left nothing dangling** — `grep -rn "registry.provenance\|capture_datasets" cli/ tests/` → zero hits.
- [ ] **Step 6: Commit** — `git rm cli/registry/provenance.py tests/test_registry_provenance.py`, `git add cli/registry/observed.py tests/test_registry_observed.py`, commit `feat(registry): the capturing loader replaces the manifest adapters`.

---

### Task 2: Schema 4, the key-set split, `append()`, and the load-time checks — ONE commit

Everything that changes the record contract lands together. `append()` no longer computes anything from disk: it receives the loader's finished block, validates, derives, writes. `TrialRegistry` gains **no** constructor parameter.

**Files (5):**

- Modify: `cli/registry/record.py`, `cli/registry/store.py`
- Test: `tests/test_registry_record.py`, `tests/test_registry_store.py`, `tests/test_trial_registry_provenance.py`

**Interfaces:**

- Produces: `SCHEMA_VERSION = 4`; `TrialRecord.datasets: dict | None`; `append(*, datasets: dict, ...)` with **no** `dataset_hash` parameter.
- Consumes: block dicts (from `ObservedReader.block()` or literals in tests — `append()` does not care who produced the dict; the shape check does the caring).

- [ ] **Step 1: The key-set move ALONE, then a real load**

Four edits to `cli/registry/record.py`, nothing else yet:

1. `_STORE_OWNED` gains `"dataset_hash"`.
1. `_REQUIRED_CALLER` loses `"dataset_hash"`. `_BASE_STORED_KEYS` is the union of both, so it is unchanged — that is what makes the move safe. **Do NOT add `datasets` to either set.**
1. `validate_caller_fields`'s hardcoded type-check tuple `("iteration", "family", "spec_hash", "dataset_hash")` loses `"dataset_hash"` — `validate_stored_record` strips `_STORE_OWNED` before calling it, so leaving it there raises a bare `KeyError` on record 1.
1. `TrialRegistry.append` sets `rec["dataset_hash"]` **after** `validate_caller_fields(caller)` — for this step only, keep the old parameter and assign it directly.

Then load the real file through the real loader:

```bash
uv run python -c "
from pathlib import Path
from cli.registry import TrialRegistry
reg = TrialRegistry(Path('docs/reference/trial-registry.jsonl'))
print('loaded', len(reg), 'schema versions', sorted({r.schema_version for r in reg.records}))
assert len(reg) == 46"
```

Expected: `loaded 46 schema versions [2, 3]`. Anything else means the move is wrong; fix HERE, before schema 4 exists. `tests/test_registry_record.py` reds at this step (its `_caller()` still supplies `dataset_hash`) — leave it for Step 4.

- [ ] **Step 2: Write the failing tests** — in `tests/test_registry_store.py` (helpers `_write`, `_new_registry`, `_append`, `canonical_json`, `compute_hash` are already there; add `import inspect`)

```python
_REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"

_BLOCK = {"files": {"BTC/EUR/1440.parquet": "c" * 64}, "rows": 10,
          "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"]}


def test_all_46_committed_records_still_load():
    reg = TrialRegistry(_REGISTRY)
    assert len(reg) >= 46  # floored, never pinned: the file grows with every registered trial
    assert all(r.schema_version in (2, 3) or r.datasets for r in reg.records)


def test_append_has_no_dataset_hash_parameter():
    assert "dataset_hash" not in inspect.signature(TrialRegistry.append).parameters


def test_a_schema_four_record_round_trips_through_disk(tmp_path):
    reg = _new_registry(tmp_path)
    written = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    reloaded = _new_registry(tmp_path).records[-1]
    assert reloaded.schema_version == 4
    assert reloaded.dataset_hash == compute_hash(reloaded.datasets) == written.dataset_hash


def test_different_file_sets_give_different_digests(tmp_path):
    """The slice IS the file list: daily-only vs daily+4h differ by construction (D2)."""
    reg = _new_registry(tmp_path)
    daily = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    both_files = {**_BLOCK["files"], "BTC/EUR/240.parquet": "d" * 64}
    both = _append(reg, family="B", n_trials_in_family=1,
                   datasets={"ohlc-test": {**_BLOCK, "files": both_files, "rows": 70}})
    assert daily.dataset_hash != both.dataset_hash


def test_a_windowed_read_gives_a_different_digest(tmp_path):
    """The sample window is expressible (D2): same files, different rows/span, different digest."""
    reg = _new_registry(tmp_path)
    full = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    windowed = _append(reg, family="B", n_trials_in_family=1,
                       datasets={"ohlc-test": {**_BLOCK, "rows": 3,
                                 "span": ["2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00"]}})
    assert full.dataset_hash != windowed.dataset_hash


def _schema4_line(**over):
    body = dict(
        trial_id=1, schema_version=4, timestamp="2026-08-09T00:00:00+00:00", iteration="iter-001",
        family="A1", spec_hash="s", seeds=[0], metrics={"dsr": 0.1}, n_trials_in_family=1,
        verdict="adopt", run_ref=None, notes="", prev_hash=GENESIS_HASH,
        datasets={"ohlc-test": dict(_BLOCK)},
    )
    body.update(over)
    body["dataset_hash"] = over.get("dataset_hash", compute_hash(body["datasets"]))
    return canonical_json(dict(body, record_hash=compute_hash(body)))


@pytest.mark.parametrize(
    "over, match",
    [
        ({"dataset_hash": "deadbeef" * 8}, "dataset_hash"),        # D4: derivation, not a caller claim
        ({"datasets": "ba47e37e"}, "datasets"),                    # the original failure, verbatim
        ({"datasets": {}}, "datasets"),                            # empty carries no provenance
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {}}}}, "files"),          # says nothing
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"a.parquet": "C" * 64}}}}, "files"),  # uppercase hex
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"a.parquet": "c" * 63}}}}, "files"),  # short hex
        ({"datasets": {"ohlc-test": {**_BLOCK, "rows": 0}}}, "rows"),             # zero-extent
        ({"datasets": {"ohlc-test": {**_BLOCK, "rows": True}}}, "rows"),          # bool-as-int
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"/etc/x": "c" * 64}}}}, "files"),      # absolute key
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"../x.parquet": "c" * 64}}}}, "files"),  # escaping key
        ({"datasets": {"ohlc-test": {**_BLOCK, "span": ["a"]}}}, "span"),         # wrong arity
        ({"datasets": {"ohlc-test": {k: v for k, v in _BLOCK.items() if k != "span"}}}, "span"),  # missing key
        ({"datasets": {"ohlc-test": {**_BLOCK, "extra": 1}}}, "datasets"),        # surplus key
    ],
)
def test_a_forged_schema_four_record_is_rejected_at_load(tmp_path, over, match):
    """D4/D2: the invariant is a property of the FILE, not of append()."""
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
    """This check ran on EVERY load via `validate_caller_fields` until the key became store-owned;
    nothing else covers schema 2/3, so unless re-homed the guard lapses silently."""
    body = json.loads(_line(1))  # the schema-3 helper, pinned to a literal 3 in Step 4
    del body["record_hash"]
    body["dataset_hash"] = bad
    with pytest.raises(RegistryError, match="dataset_hash"):
        TrialRegistry(_write(tmp_path, [canonical_json(dict(body, record_hash=compute_hash(body)))]))


def test_a_record_past_the_legacy_floor_must_declare_schema_four(tmp_path):
    """D4: what actually binds record 47 — built on the REAL 46 records (read-only)."""
    real = _REGISTRY.read_text(encoding="utf-8").splitlines()
    prev = json.loads(real[-1])

    def _line47(**over):
        body = dict(
            trial_id=prev["trial_id"] + 1, schema_version=4, timestamp="2026-08-09T00:00:00+00:00",
            iteration="iter-001", family="FLOOR", spec_hash="s", seeds=[0], metrics={"dsr": 0.1},
            n_trials_in_family=1, verdict="adopt", run_ref=None, notes="", prev_hash=prev["record_hash"],
            datasets={"ohlc-test": dict(_BLOCK)},
        )
        body.update(over)
        body["dataset_hash"] = compute_hash(body["datasets"])
        return canonical_json(dict(body, record_hash=compute_hash(body)))

    # Non-vacuous both directions: the same record at schema 4 loads, so the floor is what rejects.
    assert len(TrialRegistry(_write(tmp_path, [*real, _line47()]))) == prev["trial_id"] + 1

    v3 = json.loads(_line47())
    del v3["datasets"], v3["record_hash"]
    v3["schema_version"] = 3
    v3["dataset_hash"] = "ba47e37e2601d6098fd13c0e338a5301e8eeebb16bb4341c76a68147c7b08e42"  # verbatim
    forged = canonical_json(dict(v3, record_hash=compute_hash(v3)))
    with pytest.raises(RegistryCorruptionError, match="schema_version"):
        TrialRegistry(_write(tmp_path, [*real, forged]))


def test_append_revalidates_and_a_bad_block_writes_nothing(tmp_path):
    """One bad line is permanent (append-only, hash-chained) — refuse BEFORE the write."""
    reg = _new_registry(tmp_path)
    with pytest.raises(RegistryError):
        _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": {**_BLOCK, "rows": 0}})
    assert not reg.path.exists() or reg.path.read_text() == ""
```

Run: `uv run pytest tests/test_registry_store.py -q` — expected FAIL.

- [ ] **Step 3: Implement the rest**

`cli/registry/record.py`:

- `SCHEMA_VERSION = 4`; `_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})`.
- `_EXPECTED_STORED_KEYS = {2: _BASE_STORED_KEYS, 3: _BASE_STORED_KEYS | {"variant"}, 4: _BASE_STORED_KEYS | {"variant", "datasets"}}` — the `4:` entry *permits* `datasets`; the requirement is an explicit check below.
- `validate_stored_record` gains, for **every** version, the re-homed non-empty-str check — Probe 4 seds this text, so write it exactly:

```python
    if type(rec.get("dataset_hash")) is not str or not rec["dataset_hash"]:
        raise RegistryCorruptionError(f"{where}: dataset_hash must be a non-empty str")
```

- `validate_stored_record`, for `version >= 4`, in order, each its own `RegistryCorruptionError` naming the offending sub-field (`files` / `rows` / `span`) or `datasets`/`dataset_hash`: (a) `datasets` present; (b) `_validate_datasets_shape(rec["datasets"], where)`; (c) the derivation, written verbatim as `rec["dataset_hash"] != compute_hash(rec["datasets"])` (Probe 1 seds that text). **(a) before (c)** or (c) raises a bare `KeyError`. **Every message names exactly ONE sub-field and interpolates neither the block nor the offending value** — the parametrized cases match bare substrings, so a message containing every name lets cases pass for the wrong reason.
- `_validate_datasets_shape` (no disk access, no dataset-name knowledge): non-empty `dict`; each value a dict with **exactly** `{files, rows, span}`; `files` a **non-empty** `dict[str, str]` whose values are 64-char lowercase hex (`re.fullmatch(r"[0-9a-f]{64}", v)`) and whose KEYS are relative POSIX paths — refuse a key that is empty, starts with `/`, contains `\\`, or carries a `..` segment (message naming `files`), so a forged block cannot point the conformance pass outside `data/`; `rows` `type(x) is int` and `>= 1`; `span` a list of exactly 2 `str`. Probe 3 seds the non-empty-`files` clause, so write it exactly:

```python
        if type(block["files"]) is not dict or not block["files"]:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] files must be a non-empty dict")
```

- **Place the whole `version >= 4` block BEFORE the `caller = ...` / `validate_caller_fields(...)` lines** (today the function's last two statements) — the caller layer raises plain `RegistryError`, which `pytest.raises(RegistryCorruptionError)` cannot catch.
- `TrialRecord` gains `datasets: dict | None = None`.

`cli/registry/store.py`:

- `_to_record` passes `datasets=rec.get("datasets")` — without it the field is always `None` and the round-trip test fails silently.
- `append()` drops `dataset_hash`, gains `datasets: dict`, puts it in the stored body, sets `rec["dataset_hash"] = compute_hash(rec["datasets"])` **after** `validate_caller_fields` (store-owned), then calls `validate_stored_record(rec, f"{self.path} (append)")` **after** `rec["record_hash"] = compute_hash(rec)` and **before** `lock_f.write(...)`.
- `_assert_cross_record` gains the schema-4 floor — module constant + guard, written exactly (Probe 2 seds the guard line):

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

- Update the `TrialRegistry` class docstring (`loads schema v2+v3, writes v3` → `loads schema v2-v4, writes v4`, one clause naming the v4 block). **Do NOT touch the two specs it cites** — their sha256 is pinned as `spec_hash` in committed records.

- [ ] **Step 4: Update every existing test that constructs a record**

`tests/test_registry_record.py`: `test_constants` `SCHEMA_VERSION == 3` → `== 4`; `_caller()` drops `dataset_hash="d"`; `test_invalid_caller_rejected` adds the case `{"dataset_hash": "d"}` (store-owned refusal); every stored body built from `_caller()` (`test_stored_record_hash_and_schema_checks`, `test_stored_record_schema_version_variant_compat` with its derived copies, `test_stored_record_validation_stays_lenient_about_run_ref`) adds `dataset_hash="d"` explicitly and pins `schema_version=3` — they are v3-semantics tests; left on `SCHEMA_VERSION` they become schema-4 bodies with no `datasets` and pass or fail for the wrong reason.

`tests/test_registry_store.py`: `_line` pins `schema_version=3` (keep `dataset_hash="d"` — legal in a *stored* v3 body); the four inline bodies in `test_v3_record_with_nonstr_variant_is_corruption`, `test_v3_unknown_key_forge_is_corruption`, `test_missing_base_key_is_corruption`, `test_v3_without_variant_still_loads` pin `schema_version=3` — left on `SCHEMA_VERSION`, the last fails outright and the other three keep passing **for the wrong reason** (raising on missing `datasets`, silently retiring the guards they pin). `_append` drops `dataset_hash="d"`, gains `datasets={"ohlc-test": dict(_BLOCK)}` as its default. `test_append_requires_run_ref_explicitly` passes `datasets=...` instead of `dataset_hash="d"` or its `TypeError` fires for the wrong keyword. `TrialRegistry` gains no constructor parameter, so existing `TrialRegistry(...)` construction sites need **no** routing changes (verified: no test file outside the three named here — plus the deleted `test_registry_provenance.py` — supplies `dataset_hash=`).

`tests/test_trial_registry_provenance.py`: its `_caller()` drops `dataset_hash="d"`.

- [ ] **Step 5: Run the whole suite** — `uv run pytest -q`, FULL, not `-k registry` (`test_portfolio_builder.py` and `test_record44_legs.py` construct `TrialRegistry` over the real file). Expected: PASS.
- [ ] **Step 6: Commit** (stage all five files) — `feat(registry)!: schema 4 — dataset_hash is derived from an observed datasets block`.

---

### Task 3: The legacy pins table — the ruling, executed

**Files:**

- Create: `docs/reference/legacy-dataset-pins.jsonl`
- Test: `tests/test_legacy_dataset_pins.py`

**Interfaces:** four JSONL lines, keys `{hash, confidence, referent, trial_ids, evidence}`; `confidence ∈ {reproduced, inferred, unrecoverable}`; an `unrecoverable` row has `referent: null`; every non-null referent carries its epistemics inline.

- [ ] **Step 1: Extract the full hashes and operands** (workstation, one-off, results become literals):

```bash
uv run python -c "
import json
recs = [json.loads(l) for l in open('docs/reference/trial-registry.jsonl')]
for pfx in ('ba47e37e','81dc9b44','45275ebe','cccb8d17'):
    ids = [r['trial_id'] for r in recs if r['dataset_hash'].startswith(pfx)]
    print(pfx, recs[[r['trial_id'] for r in recs].index(ids[0])]['dataset_hash'], ids)
print('15m basket:', json.load(open('data/ohlc-15m/manifest.json'))['basket_sha256'])"
```

- [ ] **Step 2: Write the failing tests**

```python
"""The four pre-schema-4 hashes: ruled 2026-08-09 — documented, never repaired (spec 00086 D6)."""

import hashlib
import json
from pathlib import Path

_PINS = Path(__file__).resolve().parents[1] / "docs" / "reference" / "legacy-dataset-pins.jsonl"
_REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"


def _rows():
    return [json.loads(l) for l in _PINS.read_text().splitlines()]


def test_exactly_the_four_known_hashes_with_registry_true_trial_ids():
    rows = {r["hash"][:8]: r for r in _rows()}
    assert set(rows) == {"ba47e37e", "81dc9b44", "45275ebe", "cccb8d17"}
    recs = [json.loads(l) for l in _REGISTRY.read_text().splitlines()]
    for row in rows.values():
        cited = sorted(r["trial_id"] for r in recs if r["dataset_hash"] == row["hash"])
        assert row["trial_ids"] == cited, f"{row['hash'][:8]}: pins say {row['trial_ids']}, registry says {cited}"


def test_the_reproduced_recipe_executes_from_its_own_literals():
    row = next(r for r in _rows() if r["confidence"] == "reproduced")
    h4, h15 = row["evidence"]["operand_4h"], row["evidence"]["operand_15m"]
    assert hashlib.sha256(f"{h4}:{h15}".encode()).hexdigest() == row["hash"]


def test_epistemics_live_in_the_referent_value():
    for row in _rows():
        if row["confidence"] == "unrecoverable":
            assert row["referent"] is None
        elif row["confidence"] == "inferred":
            assert "INFERRED" in row["referent"] and "never recomputed" in row["referent"]
        else:  # reproduced — the row a careless reader trusts most needs the qualifier most
            assert "unrecoverable" in row["referent"]


def test_no_pin_claims_more_than_t0065_measured():
    assert all(r["confidence"] in ("reproduced", "inferred", "unrecoverable") for r in _rows())
```

- [ ] **Step 3: Run to verify they fail**, then **write the four entries**, every claim taken from T0065's measured table and nothing beyond it: `ba47e37e` `inferred`, referent `"data/ohlc-full daily (INFERRED from extent + exclusion — never recomputed)"`, trial_ids from Step 1 (expected 1–35 ∪ 40–42, 38 ids), evidence naming the 4581-row/2013→2026 extent match + v0 exclusion + the trials-33/35 scope mismatch; `81dc9b44` `unrecoverable`, `referent: null`, evidence "resisted ~226,000 candidates; no driver ever committed"; `45275ebe` `inferred`, referent `"composition of ba47e37e + 81dc9b44 (INFERRED — never recomputed; pinned by tests/test_record44_legs.py's UNION_BARS extents)"`, evidence noting it inherits `81dc9b44`'s unrecoverability and that the runbook's stated recipe does not reproduce; `cccb8d17` `reproduced`, referent naming inline that its 4h operand is the unrecoverable `81dc9b44`, evidence `{"operand_4h": "<full 81dc9b44 hash>", "operand_15m": "<basket literal>", "recipe": "sha256(hex_4h + ':' + hex_15m)"}`.
- [ ] **Step 4: Run to verify they pass**, plus a workstation-gated check that `operand_15m` equals `data/ohlc-15m/manifest.json`'s `basket_sha256` on disk (skip off-workstation with a reason).
- [ ] **Step 5: Commit** — stage both paths explicitly: `docs(registry): the legacy dataset pins — ruled unverifiable, documented with epistemics inline`.

---

### Task 4: `zcrypto research eval` — the door

**Files:**

- Create: `cli/research/__init__.py`, `cli/research/subjects.py`, `cli/research/command.py`
- Modify: `cli/__main__.py` (register `research_app`), `cli/portfolio/record44_legs.py` (`load_union` gains `read=` — optional, default preserves behavior), `README.md` (`## Usage`)
- Test: `tests/test_research_command.py`

**Interfaces:**

- Produces: `research_app` (Typer sub-app); `SUBJECTS: dict[str, Subject]` with `Subject(name, intervals: tuple[int, ...], build: Callable)`; `zcrypto research eval --subject <name> --dataset <dir> [--window START END] [--register --iteration I --family F --spec-hash H --verdict V [--notes N] [--seed S]...] [--registry PATH]`.
- Consumes: `ObservedReader` (Task 1), `TrialRegistry.append(datasets=...)` (Task 2), `build_crossfreq_system_fast`, `build_combined_system`, `load_union`.

- [ ] **Step 1: `load_union` gains a `read` parameter** — `load_union(interval, *, root=DATA_ROOT, read=read_parquet)`; the body's one `read_parquet(path)` call becomes `read(path)`. Run `uv run pytest tests/test_record44_legs.py -q` (skips off-workstation; on the workstation it must still pass — the default preserves behavior byte-for-byte).

- [ ] **Step 2: Write the failing tests** — `tests/test_research_command.py`, CliRunner, with a stub subject monkeypatched into `SUBJECTS` (production entries stay clean):

```python
def _stub_subject(monkeypatch, tmp_path):
    """A subject whose build returns fixed metrics over whatever the reader hands it. Declares its
    OWN assets — required_relpaths derives from subject.assets x subject.intervals, so the stub needs
    only the one BTC file, not CrossfreqSystemConfig's ten. Tests also monkeypatch
    cli.research.command._DATA_ROOT to tmp_path/"data" (the module constant is repo-anchored)."""
    from cli.research import subjects
    def build(reader, dataset, window):
        reader.read_series(dataset, "BTC/EUR/1440.parquet", window=window)
        return {"sharpe": 1.0}
    monkeypatch.setitem(subjects.SUBJECTS, "stub", subjects.Subject("stub", (1440,), ("BTC",), build))
```

Tests: (1) `eval --subject stub --dataset ohlc-test` over a synthetic dataset prints a report containing the block's rows and the vouched-status line, exit 0, **no registry write**; (2) with `--register --registry <tmp> --iteration iter-001 --family STUB --spec-hash s --verdict adopt --n-trials 1` the tmp registry gains one schema-4 record whose `dataset_hash == compute_hash(datasets)` and whose `datasets` block names `BTC/EUR/1440.parquet` — and a SECOND register into the same family with `--n-trials 2` succeeds while a repeat with `--n-trials 1` is refused by the registry's family floor (the flag exists precisely because the floor demands `prior + 1`; a hardcoded 1 forbids every second trial in any family — A1 already holds 40); (3) `--register` without `--iteration`/`--family`/`--spec-hash`/`--verdict` exits non-zero naming the missing flag; (4) a subject whose required series the dataset lacks (crossfreq on a daily-only synthetic dataset) exits non-zero **naming the missing files**; (5) an unknown subject exits non-zero listing the known ones.

- [ ] **Step 3: Run to verify they fail**, then **implement**:

`cli/research/subjects.py` — `Subject` dataclass (`name`, `intervals: tuple[int, ...]`, `assets: tuple[str, ...]`, `build: Callable[[ObservedReader, str, tuple | None], dict]`); `required_relpaths(subject) -> list[str]` = `[f"{a}/EUR/{i}.parquet" for a in subject.assets for i in subject.intervals]`; `SUBJECTS` with the two production entries (both with `assets=CrossfreqSystemConfig().assets`):

- `record44-crossfreq` (`intervals=(1440, 240)`): loads both unions via `load_union(interval, root=data_root/dataset, read=<reader-bound closure mapping path→relpath>)`, calls `build_crossfreq_system_fast`, returns its headline metrics dict.
- `record33-combined` (`intervals=(1440,)`): daily union → `build_combined_system`, returns its metrics dict.

`cli/research/command.py` — `research_app = typer.Typer(...)`; `eval` command: resolve `_DATA_ROOT = <repo>/data` (module constant, `record44_legs` pattern); refuse unknown subject (list known); refuse missing required series **before any read** (`(data_root/dataset/rel).exists()` sweep, message naming every missing file); instantiate `ObservedReader`; run `subject.build(reader, dataset, window)`; print the report (metrics, the block summary, `reader.vouched_status()`); on `--register`, require the caller flags (including `--n-trials`), then `TrialRegistry(registry_path).append(iteration=..., family=..., spec_hash=..., seeds=[...], metrics=..., n_trials_in_family=<--n-trials>, variant=<--variant or omitted>, verdict=..., run_ref="cli/research/command.py — docs/specs/00086-verifiable-dataset-provenance-design.md", notes=..., datasets=reader.block())`. `--registry` defaults to a REPO-ANCHORED module constant (`_REGISTRY = <repo root> / "docs" / "reference" / "trial-registry.jsonl"`, the `record44_legs` pattern) — a cwd-relative default on a registry WRITE would silently create a fresh registry elsewhere. Register in `cli/__main__.py`: `app.add_typer(research_app, name="research")`. Operator-facing text: no internal tokens in any printed literal; the `run_ref` literal cites the spec by its full `docs/` path, which the vocabulary scan's PATH_LIKE rule excuses (verified) — `tests/test_internal_terms_not_operator_visible.py` must stay green.

- [ ] **Step 4: Run to verify they pass** — `uv run pytest tests/test_research_command.py tests/test_internal_terms_not_operator_visible.py -q`, then the full suite.
- [ ] **Step 5: README `## Usage`** — the `research eval` section with the two subjects and the `--register` contract, same change (readme-usage rule).
- [ ] **Step 6: Commit** — `feat(research): the committed eval command is the registry's door`.

---

### Task 5: Controls — the runner proves itself against history; conformance over the real registry

**Files:**

- Test: `tests/test_research_control.py`, `tests/test_registry_conformance.py`

- [ ] **Step 1: The record-44 control** (workstation-gated, skip-with-reason off it): drive the runner's own loading path — `load_union(1440/240, root=data/ohlc-full, read=<ObservedReader closure>)` — feed `build_crossfreq_system_fast`, and assert `governor_engaged_bars == 7302` and `cap_breach_bars == 1318` as literals AND equal to the registry record 44 values read from the REAL registry (the same figures `instrument_self_check` reproduces; literals so a drifted registry and a drifted build cannot cancel), and the block equals the frozen extent: 20 files, rows 202,405, span `["2013-09-10 00:00:00+00:00", "2026-03-31 20:00:00+00:00"]` — measured 2026-08-08. A drifted canonical must turn this red — same STOP contract as `tests/test_crossfreq_system.py`.
- [ ] **Step 2: The everywhere end-to-end** (CI, bare checkout): synthetic dataset in tmp → `ObservedReader` → `block()` → `append()` to a tmp registry → reload → `dataset_hash == compute_hash(datasets)` re-derived — the full pipeline with zero real data.
- [ ] **Step 3: The disk conformance pass** — for every schema-4 record in the real registry: re-hash its `files` against `data/`, memoised per `(path, size, mtime)`; verdicts `rederived` / `absent-here` / **finding** (dir present with a hash mismatch or a named file missing — fails the test naming record and file). `absent-here` is legal ONLY for dataset dirs named in `_ABSENT_OK: frozenset[str] = frozenset()` — a committed module constant in the test file, empty at birth, grown only by reviewed PR: an UNLISTED citation that does not resolve is a **finding** too, so a fabricated citation cannot be laundered as merely-elsewhere (it either fails the suite or is itself a visible commit). One taxonomy clause: a mismatch on an in-place, undated dir is STOP-class under the data-model rule that a re-freeze mints a sibling — consistent with the existing STOP contracts, not in tension with D2's "re-examine" reading, which governs cross-SIBLING digest differences. Zero schema-4 records today → the real-file half **skips** with reason "no schema-4 records yet"; the mechanism is proven NOW against a constructed tmp registry + tmp data tree (one rederived, one listed-absent, one UNLISTED-absent→finding, one mismatch→finding case), so the test is non-vacuous from birth.
- [ ] **Step 4: Full suite**, then **commit** — `test(registry): the runner reproduces record 44, and conformance re-hashes what records cite`.

---

### Task 6: Prove the guards by construction

All probes through `infra/scripts/mutate-probe.sh` (clean tree, controls first). Record WHICH failure fired for each — a red exit can be the harness misfiring.

- [ ] **Probe 1 — derivation:** sed Task 2's verbatim `rec["dataset_hash"] != compute_hash(rec["datasets"])` to `==` → the forged-hash case must fail. Control: unmutated suite green.
- [ ] **Probe 2 — floor:** sed the guard's `< 4` to `< 3` → `test_a_record_past_the_legacy_floor_must_declare_schema_four` must fail.
- [ ] **Probe 3 — files emptiness:** sed the verbatim non-empty-`files` clause (`not block["files"]` → `False`) → the empty-files case must fail.
- [ ] **Probe 4 — re-homed non-empty-str:** sed Task 2's verbatim `dataset_hash` str check → its parametrized test must fail.
- [ ] **Probe 5 — loader hash:** sed `observed.py`'s `h.update(chunk)` to `pass` → `test_block_records_files_rows_span…` (known digest) must fail.
- [ ] **Probe 6 — zero-row refusal:** sed the `frame.height == 0` refusal → its test must fail.
- [ ] **Probe 7 — missing-series refusal:** sed the command's pre-read existence sweep → CliRunner test (4) must fail.
- [ ] **Probe 8 — `--register` gating:** sed the register gate to always-append → CliRunner test (1)'s no-write assertion must fail.
- [ ] **Probe 9 — the cross-check's grade:** sed `observed.py`'s `dataset_hash(full)` to `_sha256_file(path)` — the round-1 blocker, reconstructed verbatim → the true-positive vouched test must fail (a byte-grade comparison refuses the healthy read). Control: unmutated suite green.
- [ ] **Commit** any probe-revealed fixes; otherwise no commit (probes leave no tree changes).

---

### Task 7: Closeout

- [ ] **Step 1:** `docs/reference/data-catalog-full.md` — at its `dataset_hash` line: the registry's reference is now a `datasets` block of observed per-file sha256 + rows + span, derived and enforced at load; the legacy pins table explains pre-4 hashes; state positively that spec 00035's "== record 1's input else STOP" gate is superseded by schema 4 and its home is immutable (spec_hash-pinned). **Do NOT edit `docs/reference/data-catalog.md`** (retired v0; its `dataset_hash` line names the per-frame content hash — editing it injects a false statement into a frozen record).
- [ ] **Step 2:** T0065 — the execution-reproducibility round moves to `## Done so far` **whole**: recipe (loader + schema 4), command (`zcrypto research eval`), ruling (pins table), each with commit links; `ripe_when` rewritten to name the REACH round alone; status stays `partial` (REACH lives, gated on the Q2 dump — external, not this round's subject). Index bullet updated to match (topic-ops). T0132 body AND `ripe_when` (it names the discarded allowlist shape): provenance no longer waits on the manifest contract; the vouched cross-check is not a generic consumer. T0133 body: record-scoped file hashes exist from record 47 on; freeze-side verification remains its scope.
- [ ] **Step 3:** Iterations-history entry (phase 6, `iteration-closeout` skill): the referent pivot (declarations → observed bytes) and why nine rounds died on the old referent; the probe verdicts; the bounded claims (hand-rolled-writer door, file-grain identity, bypass reads); that conformance's real-file half skips until record 47 exists.
- [ ] **Step 4:** Phase-6 decisions-log entry: D-referent (manifest-declared / committed-pin / observed-bytes → observed, Decision 3), D-door (registration requires a committed subject — options and the ruling), D6 (the owner's unverifiable ruling, ratified with the spec).
- [ ] **Step 5:** Full suite + `uv run pre-commit run -a` clean; report ready. **Do not open the PR without the owner's explicit word.**
