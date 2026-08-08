# Verifiable Dataset Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a trial record's dataset reference self-describing and machine-checkable by construction, so no future `dataset_hash` can become unresolvable the way 42 existing ones have.

**Architecture:** Schema 4 adds a `datasets` block that the *store* captures from each named dataset's `manifest.json`; `dataset_hash` becomes `compute_hash(datasets)` using the registry's own canonicalisation. `append()` loses its `dataset_hash` parameter, so a caller has no way to express a provenance that disagrees with disk. Historical hashes are documented in a committed, test-policed legacy table.

**Tech Stack:** Python 3.14, `cli/registry/` (`record.py`, `store.py`), pytest, `infra/scripts/mutate-probe.sh`.

## Global Constraints

- Spec: `docs/specs/00086-verifiable-dataset-provenance-design.md`. Every decision reference below (D1–D5) is to that file.
- **The registry is append-only and hash-chained.** No task may rewrite, reorder or re-hash an existing record. `docs/reference/trial-registry.jsonl` is touched by NO task in this plan.
- `_LOADABLE_SCHEMA_VERSIONS` gains `4` and **keeps `2` and `3`**. Existing records must continue to load unchanged; an absent `datasets` block on a pre-4 record is normal, never an error.
- `extent` is derived from the manifest **only** — `series` (count at that interval), `rows` (their sum), `span` (`min(first_ts)` → `max(last_ts)`). Never read parquet; never compute a union-calendar count (D1).
- Follow the `variant` precedent in `store.py`: a key that does not apply is **omitted entirely**, never serialised as `null`, so the canonical form stays clean.
- Every guard is proven by `infra/scripts/mutate-probe.sh`, never asserted. The probe refuses a dirty tree, so each probe runs AFTER its task's commit.
- Commit gate `uv run pre-commit run -a` before every commit; a rewriting run reports Failed and leaves rewrites unstaged — re-run, re-stage, re-commit.

---

### Task 1: Schema 4 — the record shape and the loader

**Files:**
- Modify: `cli/registry/record.py` (`SCHEMA_VERSION`, `_LOADABLE_SCHEMA_VERSIONS`, `_REQUIRED_CALLER`, `TrialRecord`, `validate_caller_fields`)
- Test: `tests/test_registry_record.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION = 4`; `TrialRecord.datasets: dict | None`; validation that a schema-4 caller supplies `datasets` (a non-empty dict) and does **not** supply `dataset_hash`.
- Consumes: nothing from later tasks.

- [ ] **Step 1: Write the failing tests**

```python
def test_schema_four_requires_a_datasets_block():
    with pytest.raises(RegistryError, match="datasets"):
        validate_caller_fields(_caller(datasets={}))


def test_pre_schema_four_records_still_load():
    # The 46 committed records are schema 2 and 3; the loader must keep accepting both.
    assert {2, 3, 4} <= _LOADABLE_SCHEMA_VERSIONS


def test_a_pre_four_record_without_datasets_is_not_an_error():
    rec = _to_record({**_stored(schema_version=3), "dataset_hash": "d"})
    assert rec.datasets is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_record.py -q`
Expected: FAIL — `SCHEMA_VERSION` is 3, `datasets` unknown.

- [ ] **Step 3: Implement**

Bump `SCHEMA_VERSION` to `4`; `_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})`; add `datasets` to `_REQUIRED_CALLER`; drop `dataset_hash` from `_REQUIRED_CALLER` (the store now derives it — Task 3). Add `datasets: dict | None = None` to `TrialRecord`. In `validate_caller_fields`, require `datasets` to be a non-empty `dict`, and raise if the caller passed `dataset_hash`.

- [ ] **Step 4: Run the full registry suite**

Run: `uv run pytest tests/ -q -k registry`
Expected: PASS. Any test constructing a caller with `dataset_hash=` is updated to `datasets=`; a test that *asserts* the old shape is a legitimate inversion, not a workaround.

- [ ] **Step 5: Commit**

```bash
git add cli/registry/record.py tests/test_registry_record.py
git commit -m "feat(registry): schema 4 carries a datasets block instead of a caller-supplied digest"
```

---

### Task 2: Capture the block from manifests, and refuse when you cannot

**Files:**
- Create: `cli/registry/provenance.py`
- Test: `tests/test_registry_provenance.py`

**Interfaces:**
- Produces: `capture_datasets(names: list[str], data_root: Path) -> dict` — the D1 block; raises `RegistryError` naming the missing path when a manifest is absent or unreadable.
- Consumes: Task 1's schema.

- [ ] **Step 1: Write the failing tests**

```python
def test_capture_reads_basket_and_extent_from_the_manifest(tmp_path):
    _write_manifest(tmp_path / "ohlc-x", basket="ab" * 32, series={
        "BTC/EUR": {"1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00",
                             "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64}},
    })
    got = capture_datasets(["ohlc-x"], tmp_path)
    assert got["ohlc-x"]["basket_sha256"] == "ab" * 32
    assert got["ohlc-x"]["extent"]["1440"] == {
        "series": 1, "rows": 10, "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T00:00:00+00:00"]}


def test_capture_refuses_a_missing_manifest_and_names_the_path(tmp_path):
    with pytest.raises(RegistryError, match=r"ohlc-absent/manifest\.json"):
        capture_datasets(["ohlc-absent"], tmp_path)


def test_extent_sums_rows_across_series_and_spans_the_union(tmp_path):
    # Two series of different length and span: rows SUM, span is min(first)->max(last).
    # A max()-based rows would read 7 and a single-series span would hide the earlier start.
    ...
    assert got["ohlc-y"]["extent"]["1440"] == {"series": 2, "rows": 12, "span": ["2019-01-01...", "2020-01-10..."]}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `capture_datasets`**

Read `data_root/<name>/manifest.json`; take `basket_sha256` and `fetched_at` verbatim; walk `series[pair][interval]` building per-interval `{series, rows, span}`. Sort every mapping by key so the canonical form is stable. Raise `RegistryError` naming the exact path when the file is missing, unparseable, or lacks `basket_sha256`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

---

### Task 3: `append()` derives the digest and cannot be told otherwise

**Files:**
- Modify: `cli/registry/store.py` (`TrialRegistry.append`)
- Test: `tests/test_registry_store.py`

**Interfaces:**
- Produces: `append(..., datasets: list[str], ...)`; no `dataset_hash` parameter exists.
- Consumes: `capture_datasets` (Task 2), schema 4 (Task 1).

- [ ] **Step 1: Write the failing tests**

```python
def test_append_derives_the_dataset_hash_from_the_captured_block(registry, tmp_data):
    rec = registry.append(datasets=["ohlc-x"], **_ok())
    assert rec.dataset_hash == compute_hash(rec.datasets)


def test_append_has_no_dataset_hash_parameter():
    # The structural fix: not "validated", ABSENT. A caller cannot express a wrong provenance.
    assert "dataset_hash" not in inspect.signature(TrialRegistry.append).parameters
    with pytest.raises(TypeError):
        registry.append(dataset_hash="deadbeef", datasets=["ohlc-x"], **_ok())


def test_append_refuses_when_a_named_dataset_is_absent(registry, tmp_data):
    with pytest.raises(RegistryError, match="manifest"):
        registry.append(datasets=["ohlc-absent"], **_ok())
```

- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement** — replace the `dataset_hash` parameter with `datasets: list[str]`; call `capture_datasets`; set `caller["datasets"]` and `caller["dataset_hash"] = compute_hash(captured)`; leave `record_hash` chaining untouched.
- [ ] **Step 4: Run the registry suite**
- [ ] **Step 5: Commit**

---

### Task 4: The legacy pins table

**Files:**
- Create: `docs/reference/legacy-dataset-pins.jsonl`
- Test: `tests/test_legacy_dataset_pins.py`

**Interfaces:**
- Produces: one line per distinct pre-schema-4 `dataset_hash`, shape per D4.
- Consumes: nothing.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_historical_dataset_hash_is_pinned():
    """Completeness by construction -- a historical hash cannot be forgotten."""
    historical = {r["dataset_hash"] for r in _registry_records() if r["schema_version"] < 4}
    pinned = {p["dataset_hash"] for p in _legacy_pins()}
    assert historical <= pinned, f"unpinned: {sorted(historical - pinned)}"


def test_reproduced_entries_actually_reproduce():
    """`reproduced: true` is an executable claim, not a label. cccb8d17 is the live case."""
    for pin in _legacy_pins():
        if pin["confidence"] == "reproduced":
            assert _run_recipe(pin["recipe"]) == pin["dataset_hash"]


def test_inferred_entries_do_not_claim_a_recipe():
    for pin in _legacy_pins():
        if pin["confidence"] == "inferred":
            assert pin.get("recipe") is None and pin["reproduced"] is False
```

- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Write the four entries.** `cccb8d17` → `reproduced`, recipe `sha256(hex_4h + ":" + hex_15m)` with both operands. `ba47e37e` → `inferred`, `basis: extent`, evidence = ohlc-full 1440 `rows 34460`, span `2013-09-10 → 2026-03-31`, plus the v0 exclusion (721 bars from 2024-07-17, zero hash overlap). `81dc9b44` → `inferred`, the 4h operand of the above. `45275ebe` → `inferred`, composed of the two, with the note that the runbook's stated recipe does **not** verify.
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 5: Prove all four guards by construction

**Files:** none — probes only. Runs AFTER Tasks 1–4 are committed (`mutate-probe.sh` refuses a dirty tree).

- [ ] **Step 1: Round-trip guard**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/store.py \
  --control 's|caller\["dataset_hash"\] = compute_hash|caller["dataset_hash"] = "x" + compute_hash|' \
  --mutation 's|compute_hash(captured)|compute_hash({})|' \
  -- uv run pytest tests/test_registry_store.py -q
```
Expected: `KILLED`.

- [ ] **Step 2: Refusal guard** — mutate `capture_datasets`' raise into a silent `return {}`; expect `KILLED`.
- [ ] **Step 3: Legacy completeness** — drop a line from the table; expect `KILLED`.
- [ ] **Step 4: Reproduced-means-reproduced** — corrupt one hex digit of `cccb8d17`'s recipe operand; expect `KILLED`.
- [ ] **Step 5: Record every verdict in the closeout.** A probe that reports `CONTROL mutation did not fail` means the harness does not bite — pick a control the probe must detect and re-run; do not record a verdict from an unproven harness.

---

### Task 6: Closeout

- [ ] **Step 1:** Update `docs/reference/data-catalog-full.md` — the registry's dataset reference is now a `datasets` block, and the legacy table is where pre-4 hashes are explained.
- [ ] **Step 2:** [[T0065]] — mark the going-forward sub-item done; the topic stays `partial` (the research-run command remains).
- [ ] **Step 3:** Append the iterations-history entry (phase 6 routing per `iteration-closeout`), naming the four probe verdicts and the accepted cost from D3 (a record can only be written where its data is present).
- [ ] **Step 4:** Phase-6 decisions-log entry for D1 (both halves), D2 (derived not supplied) and D4 (table not prose), each with its options and the owner's pick.
- [ ] **Step 5:** Report the branch ready. **Do not open the PR without the owner's explicit word.**
