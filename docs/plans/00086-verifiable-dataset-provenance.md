# Verifiable Dataset Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a trial record's dataset reference self-describing and machine-checkable, for the datasets that actually back trials, so no future `dataset_hash` becomes unresolvable the way 44 existing ones have.

**Architecture:** Two per-shape adapters capture a `datasets` block (declared slice + set digest + extent) for an allowlist of three datasets; `dataset_hash` becomes `compute_hash(datasets)`; `dataset_hash` moves into the store-owned key set so no caller can supply it; and `validate_stored_record` enforces the derivation at LOAD, since `append()` has no production caller.

**Tech Stack:** Python 3.14, `cli/registry/`, pytest, `infra/scripts/mutate-probe.sh`.

## Global Constraints

- Spec: `docs/specs/00086-verifiable-dataset-provenance-design.md`; D-numbers below refer to it. **This is the reshaped version** — a generic-capture design failed four cold-review rounds and was replaced by D1's allowlist. Do not re-generalise.
- **The registry is append-only and hash-chained.** No task rewrites, reorders or re-hashes a record. `docs/reference/trial-registry.jsonl` is modified by NO task.
- **`_BASE_STORED_KEYS` is derived from `_REQUIRED_CALLER`** (`cli/registry/record.py`). Moving `dataset_hash` between those sets silently rewrites the stored-key contract. `_EXPECTED_STORED_KEYS` needs an explicit `4:` entry or a schema-4 load raises a bare `KeyError`. This is how the previous attempt broke all 46 records; Task 2 Step 2 exists to catch it before anything else proceeds.
- **The schema bump and the `append()` change land in ONE commit** (Task 2). Bumping `SCHEMA_VERSION` while `append()` still writes no `datasets` block would make every record it writes unloadable by the validator in the same commit.
- **Runtime readers**: `cli/portfolio/record44_legs.py` constructs `TrialRegistry`; `cli/engine/soak.py` parses the JSONL with raw `json.loads` and never validates. Breaking the loader breaks the first; the second does not inherit D4's check (named in the spec, not a defect to fix here).
- Each task stages **everything it edits**. `mutate-probe.sh` refuses a dirty worktree, so an unstaged edit makes every later probe exit 3.
- Commit gate `uv run pre-commit run -a` before each commit; a rewriting run reports Failed and leaves rewrites unstaged — re-run, re-stage, re-commit.

---

### Task 1: The two adapters and `capture_datasets`

Pure new module, no schema change, nothing else depends on it yet — so it lands safely first.

**Files:**
- Create: `cli/registry/provenance.py`
- Test: `tests/test_registry_provenance.py`

**Interfaces:**
- Produces: `capture_datasets(select: dict[str, list[str]], data_root: Path) -> dict` returning the D2 block; `ALLOWLIST: dict[str, str]` mapping dataset name (or prefix, for `ohlc-holdout-*`) to adapter name. Raises `RegistryError` on an unlisted dataset, an absent manifest, or an unresolvable `select` token.
- Consumes: `cli.registry.errors.RegistryError`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import pytest
from pathlib import Path
from cli.registry.errors import RegistryError
from cli.registry.provenance import ALLOWLIST, capture_datasets

_NESTED = {"BTC/EUR": {"1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00",
                                "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64},
                       "240":  {"rows": 60, "first_ts": "2020-01-01T00:00:00+00:00",
                                "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "d" * 64}}}


def _write(root: Path, name: str, payload: dict) -> None:
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "manifest.json").write_text(json.dumps(payload))


def test_backfill_shape_captures_the_declared_slice(tmp_path):
    _write(tmp_path, "ohlc-full", {"basket_sha256": "a" * 64, "fetched_at": "2020-01-11T00:00:00+00:00",
                                   "source": "/machine/local/path", "series": _NESTED})
    got = capture_datasets({"ohlc-full": ["1440"]}, tmp_path)["ohlc-full"]
    assert got["select"] == ["1440"]
    assert got["set_digest"] == "a" * 64
    assert got["extent"] == {"series": 1, "rows": 10,
                             "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T00:00:00+00:00"]}
    assert "source" not in got and "fetched_at" not in got  # D2: no per-run, no machine-local values


def test_empty_select_means_the_whole_set_explicitly(tmp_path):
    _write(tmp_path, "ohlc-full", {"basket_sha256": "a" * 64, "fetched_at": "x", "series": _NESTED})
    got = capture_datasets({"ohlc-full": []}, tmp_path)["ohlc-full"]
    assert got["select"] == []
    assert got["extent"]["series"] == 2 and got["extent"]["rows"] == 70


def test_holdout_shape_uses_manifest_sha256_and_flat_series(tmp_path):
    # No basket_sha256, no per-series sha256, series NOT nested by interval.
    _write(tmp_path, "ohlc-holdout-2026-07-10", {
        "manifest_sha256": "b" * 64, "pulled_at": "2026-07-10T01:30Z", "freeze_last_complete_day": "2026-07-09",
        "series": {"ADA": {"rows": 5, "first_ts": "2018-09-28 00:00:00+00:00",
                           "last_ts": "2026-07-09 00:00:00+00:00", "overlap_bars_verified": 3, "appended": 1}}})
    got = capture_datasets({"ohlc-holdout-2026-07-10": []}, tmp_path)["ohlc-holdout-2026-07-10"]
    assert got["set_digest"] == "b" * 64
    assert got["extent"] == {"series": 1, "rows": 5,
                             "span": ["2018-09-28 00:00:00+00:00", "2026-07-09 00:00:00+00:00"]}


def test_select_is_normalised_so_order_and_duplicates_cannot_move_the_digest(tmp_path):
    _write(tmp_path, "ohlc-full", {"basket_sha256": "a" * 64, "fetched_at": "x", "series": _NESTED})
    a = capture_datasets({"ohlc-full": ["240", "1440", "240"]}, tmp_path)
    b = capture_datasets({"ohlc-full": ["1440", "240"]}, tmp_path)
    assert a == b and a["ohlc-full"]["select"] == ["1440", "240"]


def test_an_unlisted_dataset_is_refused_and_the_message_names_the_remedy(tmp_path):
    _write(tmp_path, "derivatives-funding", {"basket_sha256": "e" * 64, "fetched_at": "x", "series": {}})
    with pytest.raises(RegistryError, match="adapter"):
        capture_datasets({"derivatives-funding": []}, tmp_path)


def test_an_absent_manifest_is_refused_and_names_the_path(tmp_path):
    with pytest.raises(RegistryError, match=r"ohlc-full/manifest\.json"):
        capture_datasets({"ohlc-full": []}, tmp_path)


def test_an_unresolvable_select_token_is_refused(tmp_path):
    _write(tmp_path, "ohlc-full", {"basket_sha256": "a" * 64, "fetched_at": "x", "series": _NESTED})
    with pytest.raises(RegistryError, match="60"):
        capture_datasets({"ohlc-full": ["60"]}, tmp_path)


def test_an_empty_datasets_mapping_is_refused(tmp_path):
    with pytest.raises(RegistryError, match="no dataset"):
        capture_datasets({}, tmp_path)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: FAIL — `cli.registry.provenance` does not exist.

- [ ] **Step 3: Implement**

`ALLOWLIST = {"ohlc-full": "backfill", "ohlc-15m": "backfill", "ohlc-holdout-": "holdout"}` — exact match first, then prefix match, so `ohlc-holdout-<date>` resolves. Anything else raises `RegistryError` whose message contains the word `adapter` and the dataset name.

The **backfill** adapter reads `basket_sha256`, walks `series[pair][interval]`, and treats a `select` token as an interval. The **holdout** adapter reads `manifest_sha256`, walks `series[asset]` (one level), and accepts only an empty `select` (there is no second dimension to select on) — a non-empty one raises.

`extent` per D2: `series` = count of selected leaves, `rows` = their sum, `span` = `[min(first_ts), max(last_ts)]` as raw strings (the holdout's stamps use a space, not `T`; do not parse or normalise them — a round-trip through a datetime would silently change the recorded value). Sort `select`, drop duplicates. Emit **only** `select`, `set_digest`, `extent`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Add the on-disk conformance test**

Enumerate from disk, not from a hardcoded tuple — a set present but unlisted must be visible:

```python
_DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.mark.skipif(not _DATA.exists(), reason="gitignored data root absent")
def test_every_allowlisted_dataset_on_disk_captures_and_every_other_is_refused():
    for manifest in sorted(_DATA.glob("*/manifest.json")):
        name = manifest.parent.name
        listed = name in ALLOWLIST or any(name.startswith(k) for k in ALLOWLIST if k.endswith("-"))
        if listed:
            block = capture_datasets({name: []}, _DATA)[name]
            assert block["extent"]["rows"] > 0 and len(block["set_digest"]) == 64
        else:
            with pytest.raises(RegistryError, match="adapter"):
                capture_datasets({name: []}, _DATA)
```

- [ ] **Step 6: Commit**

```bash
git add cli/registry/provenance.py tests/test_registry_provenance.py
git commit -m "feat(registry): two manifest adapters capture a declared dataset slice"
```

---

### Task 2: Schema 4, the key-set split, `append()`, and the load-time check — ONE commit

Everything that changes the record contract lands together. Splitting it leaves an intermediate commit whose own `append()` writes records its own validator rejects.

**Files:**
- Modify: `cli/registry/record.py` (`SCHEMA_VERSION`, `_LOADABLE_SCHEMA_VERSIONS`, `_STORE_OWNED`, `_REQUIRED_CALLER`, `_EXPECTED_STORED_KEYS`, `TrialRecord`, `validate_caller_fields`, `validate_stored_record`)
- Modify: `cli/registry/store.py` (`_to_record`, `TrialRegistry.__init__`, `TrialRegistry.append`)
- Test: `tests/test_registry_record.py`, `tests/test_registry_store.py`, `tests/test_trial_registry_provenance.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION = 4`; `TrialRecord.datasets: dict | None`; `append(*, datasets: dict[str, list[str]], ...)` with **no** `dataset_hash` parameter; `TrialRegistry(path, data_root=...)`.
- Consumes: `capture_datasets` (Task 1).

- [ ] **Step 1: Write the failing tests**

```python
def test_all_46_committed_records_still_load():
    """The defect that sank the first attempt. Assert against the REAL file, not a fixture."""
    reg = TrialRegistry(Path("docs/reference/trial-registry.jsonl"))
    assert len(reg) == 46
    assert {r.schema_version for r in reg.records} == {2, 3}


def test_a_schema_four_record_round_trips_through_disk(tmp_path, tmp_data):
    reg = TrialRegistry(tmp_path / "r.jsonl", data_root=tmp_data)
    written = reg.append(datasets={"ohlc-full": ["1440"]}, **_ok())
    reloaded = TrialRegistry(tmp_path / "r.jsonl", data_root=tmp_data).records[-1]
    assert reloaded.dataset_hash == compute_hash(reloaded.datasets) == written.dataset_hash


def test_append_has_no_dataset_hash_parameter():
    assert "dataset_hash" not in inspect.signature(TrialRegistry.append).parameters


def test_a_forged_schema_four_record_is_rejected_at_load(tmp_path):
    """D4: the invariant is a property of the FILE, not of append()."""
    body = _schema4_body(dataset_hash="deadbeef" * 8)  # inconsistent with its own datasets block
    (tmp_path / "r.jsonl").write_text(json.dumps(_rehashed(body)) + "\n")
    with pytest.raises(RegistryCorruptionError, match="dataset_hash"):
        TrialRegistry(tmp_path / "r.jsonl")


def test_different_declared_slices_give_different_digests(tmp_path, tmp_data):
    reg = TrialRegistry(tmp_path / "r.jsonl", data_root=tmp_data)
    daily = reg.append(datasets={"ohlc-full": ["1440"]}, **_ok())
    both = reg.append(datasets={"ohlc-full": ["1440", "240"]}, **_ok())
    assert daily.dataset_hash != both.dataset_hash
```

- [ ] **Step 2: Run to verify they fail, and CONFIRM the key-set trap before implementing**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`

Then, before writing the implementation, simulate the key-set change against the real file:

```bash
uv run python -c "
import json
from cli.registry.record import _STORE_OWNED, _REQUIRED_CALLER
store = set(_STORE_OWNED) | {'dataset_hash'}          # the proposed move
caller = set(_REQUIRED_CALLER) - {'dataset_hash'} | {'datasets'}
base = store | caller | {'run_ref', 'notes'}
bad = 0
for line in open('docs/reference/trial-registry.jsonl'):
    if not line.strip(): continue
    rec = json.loads(line)
    expected = base if rec['schema_version'] == 2 else base | {'variant'}
    # schema<4 records carry no datasets block, so it must NOT be in the required set for them
    if (set(rec) - expected) or ((base - {'datasets'}) - set(rec)): bad += 1
print('records that would fail:', bad)"
```
Expected: `0`. A non-zero number means the split is wrong — fix it before proceeding.

- [ ] **Step 3: Implement**

Move `dataset_hash` from `_REQUIRED_CALLER` into `_STORE_OWNED`. Add `datasets` to `_REQUIRED_CALLER`. Because `_BASE_STORED_KEYS` is derived from both, `datasets` must be **version-scoped**, not base: keep `_BASE_STORED_KEYS` free of it and give `_EXPECTED_STORED_KEYS` explicit entries — `{2: base, 3: base | {"variant"}, 4: base | {"variant", "datasets"}}` — and make the *missing*-key check subtract `datasets` for versions < 4, exactly as `variant` is already special-cased.

`SCHEMA_VERSION = 4`; `_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})`. Add `datasets: dict | None = None` to `TrialRecord` **and to `_to_record`** (`store.py`) — without the latter it is always `None` and the round-trip test fails silently. In `validate_stored_record`, for `version >= 4`, raise `RegistryCorruptionError` naming `dataset_hash` when `rec["dataset_hash"] != compute_hash(rec["datasets"])`.

`TrialRegistry.__init__(self, path, *, data_root: Path | None = None)`, defaulting to `cli.config`'s data dir. `append()` drops `dataset_hash`, gains `datasets: dict[str, list[str]]`, calls `capture_datasets(datasets, self._data_root)`, sets `caller["datasets"]` to the captured block, and sets `dataset_hash` **after** `validate_caller_fields` — it is store-owned now, so validating it as a caller field would reject the store's own output.

- [ ] **Step 4: Update every existing test that constructs a record**

These exist today and break; all three files are in this task's Files list:
- `tests/test_registry_record.py` — `_caller()` supplies `dataset_hash="d"`; the `SCHEMA_VERSION == 3` pin; every stored-body helper built with `schema_version=SCHEMA_VERSION` that asserts it validates (pin those to a literal `3`).
- `tests/test_registry_store.py` — `_line`, `_line_v2`, `_append` and the direct `reg.append(...)` call.
- `tests/test_trial_registry_provenance.py` — its own `_caller()` supplies `dataset_hash="d"`, used by `test_both_layers_agree_on_path_spelling`.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS. Run the FULL suite, not `-k registry` — `tests/test_portfolio_builder.py` and `tests/test_record44_legs.py` construct `TrialRegistry` over the real file and match no registry-shaped keyword.

- [ ] **Step 6: Commit** (stage all six files listed above)

---

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


def test_inferred_rows_carry_the_qualification_in_the_referent_value():
    """A careless grep must not return a bare path that reads as verified fact."""
    for pin in _pins():
        if pin["confidence"] == "inferred":
            assert "INFERRED" in pin["referent"]
```

- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Write the four entries** — `cccb8d17` `reproduced` with its two operands; `ba47e37e` `inferred`, referent `"data/ohlc-full (INFERRED from extent + exclusion — never recomputed)"`, evidence = 1440 `rows 34460`, span `2013-09-10 → 2026-03-31`, plus the v0 exclusion (721 bars from 2024-07-17, zero hash overlap); `81dc9b44` and `45275ebe` `inferred`, each naming what it inherits from and — for `45275ebe` — that the runbook's stated composition does **not** reproduce, with `tests/test_crossfreq_system.py` named as the actual evidence.
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 4: Prove the guards by construction

Runs after Tasks 1–3 are committed — `mutate-probe.sh` refuses a dirty tree.

- [ ] **Step 1: The load-time invariant bites**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})|_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3})|' \
  --mutation 's|!= compute_hash(rec\["datasets"\])|!= rec["dataset_hash"]|' \
  -- uv run pytest tests/test_registry_store.py -q
```
Expected: `KILLED`. The control drops schema 4 from the loadable set, which fails the round-trip test; the mutation makes the check tautological.

- [ ] **Step 2: The allowlist refusal bites**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"ohlc-full": "backfill"|"ohlc-FULL": "backfill"|' \
  --mutation 's|raise RegistryError(f"{name}: no adapter|return {} or RegistryError(f"{name}: no adapter|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```
Expected: `KILLED`. Adjust the mutation to whatever single line the refusal actually occupies — it must stay one line, since the probe applies a single-line `sed`.

- [ ] **Step 3: The slice actually discriminates**

Mutate the capture to ignore `select` (e.g. force the whole-set branch) and expect `test_different_declared_slices_give_different_digests` to fail. Control: change the `extent` `rows` sum to a max. Expected: `KILLED`.

- [ ] **Step 4: Record every verdict.** A probe reporting `CONTROL mutation did not fail` means the harness does not bite — choose a control the probe must detect and re-run. Never record a verdict from an unproven harness.

---

### Task 5: Closeout

- [ ] **Step 1:** `docs/reference/data-catalog-full.md` — the registry's dataset reference is a `datasets` block; the legacy table explains pre-4 hashes; the allowlist is named.
- [ ] **Step 2:** [[T0065]] — mark the going-forward sub-item done; topic stays `partial` (the research-run command remains). [[T0132]] stays `open`.
- [ ] **Step 3:** Iterations-history entry (phase 6 per `iteration-closeout`), naming the probe verdicts, D5's bounded claim, and that a generic design failed four review rounds before the reshape.
- [ ] **Step 4:** Phase-6 decisions-log entry for D1 (allowlist over generality), D3 (derived, store-owned) and D5 (do not rebuild byte verification), each with options and the owner's pick.
- [ ] **Step 5:** Report ready. **Do not open the PR without the owner's explicit word.**
