# Trial-Registry Hash Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `prev_hash` chain to `cli/registry/` (tamper-evidence against a re-hashing writer) per `docs/specs/00012-registry-hash-chain-design.md`, preserving all existing integrity behavior.

**Architecture:** Surgical edits to `cli/registry/record.py` + `store.py` + `__init__.py`; update existing registry tests for the new field; add corruption-detection tests. TDD (new tests first, then edits).

**Tech Stack:** Python 3.14, stdlib (`hashlib`, `json`, `fcntl`), pytest. Ruff line-length 132, double quotes.

## Global Constraints

- **Preserve** every existing behavior: caller `append(...)` signature, `_assert_finite`/NaN rejection, torn-tail self-heal, contiguity + monotone-family checks. `prev_hash` is **store-owned** (callers must not supply it).
- The chain: each record's `prev_hash` = the prior record's `record_hash` (`GENESIS_HASH = "0"*64` for the first). `prev_hash` is inside the hashed body, so the existing self-hash already protects it; the only new logic is the link check in `_assert_cross_record`.
- `SCHEMA_VERSION` bumps `1 → 2`. No CLI/README change, no new deps.

---

### Task 1: Add the hash chain to `cli/registry/`

**Files:**
- Modify: `cli/registry/record.py`, `cli/registry/store.py`, `cli/registry/__init__.py`
- Modify/add: `tests/test_registry_store.py`, `tests/test_registry_record.py`

**Interfaces:**
- Produces: `GENESIS_HASH`; `TrialRecord` gains `prev_hash: str`; `SCHEMA_VERSION == 2`; the on-disk record gains a `prev_hash` field; `_assert_cross_record` enforces the chain.

- [ ] **Step 1: Read the current code + tests first.** Read `cli/registry/record.py`, `cli/registry/store.py`, `tests/test_registry_record.py`, `tests/test_registry_store.py` in full so the edits are surgical and you know which existing tests construct records / build stored dicts / recompute hashes (those need the new field).

- [ ] **Step 2: Write the new failing corruption tests** in `tests/test_registry_store.py` (use the module's existing helpers/fixtures for appending trials; look at how current tests build a valid trial). Add:

```python
def test_chain_links_are_written(tmp_path):
    reg = _new_registry(tmp_path)  # use the existing test's construction pattern
    r0 = _append_trial(reg, family="A")   # reuse the existing helper that appends a valid trial
    r1 = _append_trial(reg, family="A")
    r2 = _append_trial(reg, family="A")
    from cli.registry import GENESIS_HASH
    assert r0.prev_hash == GENESIS_HASH
    assert r1.prev_hash == r0.record_hash
    assert r2.prev_hash == r1.record_hash


def test_rehashing_tamper_of_middle_record_is_caught(tmp_path):
    import json
    from cli.registry import RegistryCorruptionError, TrialRegistry
    from cli.registry.record import compute_hash

    reg = _new_registry(tmp_path)
    _append_trial(reg, family="A")
    _append_trial(reg, family="A")
    _append_trial(reg, family="A")
    lines = reg.path.read_text().splitlines()
    rec = json.loads(lines[1])          # record 2 (trial_id 2)
    rec["metrics"] = {**rec["metrics"], "sharpe": 999.0}  # tamper a metric
    body = {k: v for k, v in rec.items() if k != "record_hash"}
    rec["record_hash"] = compute_hash(body)  # re-hash so the SELF-hash check passes
    lines[1] = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)          # chain check fails at record 3 (prev_hash mismatch)


def test_metric_tamper_without_rehash_still_caught(tmp_path):
    import json
    from cli.registry import RegistryCorruptionError, TrialRegistry

    reg = _new_registry(tmp_path)
    _append_trial(reg, family="A")
    _append_trial(reg, family="A")
    lines = reg.path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["metrics"] = {**rec["metrics"], "sharpe": 999.0}  # no re-hash
    lines[0] = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)          # existing self-hash check fires


def test_deleting_middle_record_is_caught(tmp_path):
    from cli.registry import RegistryCorruptionError, TrialRegistry

    reg = _new_registry(tmp_path)
    _append_trial(reg, family="A")
    _append_trial(reg, family="A")
    _append_trial(reg, family="A")
    lines = reg.path.read_text().splitlines()
    del lines[1]
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)


def test_schema_version_1_record_is_rejected(tmp_path):
    import json
    from cli.registry import RegistryCorruptionError, TrialRegistry

    reg = _new_registry(tmp_path)
    _append_trial(reg, family="A")
    lines = reg.path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["schema_version"] = 1
    body = {k: v for k, v in rec.items() if k != "record_hash"}
    from cli.registry.record import compute_hash
    rec["record_hash"] = compute_hash(body)
    lines[0] = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)


def test_chain_continues_across_registry_instances(tmp_path):
    reg = _new_registry(tmp_path)
    last = _append_trial(reg, family="A")
    reg2 = TrialRegistry(reg.path)  # reopen
    nxt = _append_trial(reg2, family="A")
    assert nxt.prev_hash == last.record_hash
```

Adapt `_new_registry` / `_append_trial` to whatever the existing test file uses to make a registry + a valid trial (do NOT invent a new fixture if one exists — reuse it; if the existing tests append inline, factor a tiny local helper).

- [ ] **Step 3: Run the new tests, verify they fail** — `uv run pytest tests/test_registry_store.py -q` (the new tests fail because `prev_hash`/chain don't exist yet).

- [ ] **Step 4: Edit `cli/registry/record.py`** per the spec: `SCHEMA_VERSION = 2`; add `GENESIS_HASH = "0" * 64`; add `"prev_hash"` to `_STORE_OWNED`; add `prev_hash: str` to `TrialRecord` (before `record_hash`); in `validate_stored_record`, after the self-hash check, add `if type(rec.get("prev_hash")) is not str or len(rec["prev_hash"]) != 64: raise RegistryCorruptionError(f"{where}: prev_hash must be a 64-char hex str")`.

- [ ] **Step 5: Edit `cli/registry/store.py`** per the spec: import `GENESIS_HASH` from `cli.registry.record`; in `_to_record` add `prev_hash=rec["prev_hash"]`; in `append`, set `prev_hash = disk[-1]["record_hash"] if disk else GENESIS_HASH` and build `rec = {**caller, "trial_id": next_id, "schema_version": SCHEMA_VERSION, "timestamp": _now_utc_iso(), "prev_hash": prev_hash}` before `rec["record_hash"] = compute_hash(rec)`; in `_assert_cross_record`, add the chain check `expected_prev = GENESIS_HASH if idx == 0 else recs[idx - 1]["record_hash"]` / raise `RegistryCorruptionError` if `rec["prev_hash"] != expected_prev`.

- [ ] **Step 6: Edit `cli/registry/__init__.py`** — import + export `GENESIS_HASH`.

- [ ] **Step 7: Fix the existing tests** — update every place in `tests/test_registry_record.py` / `tests/test_registry_store.py` that directly constructs a `TrialRecord` (now needs `prev_hash=...`) or hand-builds a stored dict / expects a specific record layout (now includes `prev_hash`), so all pre-existing assertions pass with the new schema. Do NOT weaken any existing integrity assertion.

- [ ] **Step 8: Run tests, verify all pass** — `uv run pytest tests/test_registry_store.py tests/test_registry_record.py -q` (existing + new all green).

- [ ] **Step 9: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 10: Commit** — `feat(registry): add prev_hash chain for tamper-evidence`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-019: trial-registry hash chain (Phase 2)`: `cli/registry/` gains a `prev_hash` chain (`GENESIS_HASH`, `SCHEMA_VERSION 1→2`) — each record commits to its predecessor's `record_hash`, so a re-hashing tamper of any record (which the Phase-0 self-hash alone missed, per its own docstring) breaks the next record's link and is caught by the cross-record chain check. Closes the §9.7 "hash-chain intact" gap + the corruption-detection CI test (re-hashing mid-chain tamper → loud failure). All existing integrity (self-hash, contiguity, monotone counts, self-heal, NaN rejection) preserved; no data migration (empty registry). Spec/plan `00012`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-019 closeout — registry hash chain`.
