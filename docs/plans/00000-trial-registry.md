# Trial Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the append-only, integrity-checked trial registry (`cli/registry/`) so a NaN/inf metric — a deflated Sharpe (DSR) above all — can never enter or leave the registry silently.

**Architecture:** A stdlib-only library package mirroring `cli/logging/`: `record.py` (the `TrialRecord` dataclass, canonical serialization, hashing, validation), `store.py` (`TrialRegistry` — append-only JSONL load/append with `fcntl` locking + torn-tail self-heal + cross-record asserts), `errors.py` (loud-failure exceptions). Design is fully specified in `docs/specs/00000-trial-registry-design.md`; this plan sequences it — do not re-litigate design.

**Tech Stack:** Python 3.14, stdlib only (`json`, `hashlib`, `math`, `dataclasses`, `datetime`, `fcntl`, `os`, `pathlib`); pytest.

## Global Constraints

- **Stdlib only** for `cli/registry/` — no third-party imports (no qlib, numpy, polars).
- **Ruff:** line-length 132, double quotes; `from __future__ import annotations` at the top of each module (matches `cli/logging/`).
- **Loud failure:** every integrity/validation violation raises; never silently coerce.
- **Commit gate:** stage the new files, then `uv run pre-commit run -a`; re-stage anything the hooks rewrite; commit (never `--no-verify`).
- **Reviewer trailer:** each implementation commit is reviewed by a subagent before the branch is pushed (`.claude/rules/commit-messages.md`); amend the `Reviewed-by:` trailer. Co-author trailer names the actual executing model.
- **Store-owned fields** (`trial_id`, `schema_version`, `timestamp`, `record_hash`) are stamped by the store; a caller supplying any is rejected.

---

### Task 1: Errors + serialization/hashing primitives

**Files:**
- Create: `cli/registry/__init__.py` (empty for now — populated in Task 3)
- Create: `cli/registry/errors.py`
- Create: `cli/registry/record.py` (primitives only; validation added in Task 2)
- Test: `tests/test_registry_record.py`

**Interfaces:**
- Produces: `RegistryError`, `RegistryCorruptionError(RegistryError)`; `SCHEMA_VERSION: int = 1`; `VERDICTS: frozenset = {"adopt","reject","park"}`; `canonical_json(obj: dict) -> str`; `compute_hash(fields: dict) -> str`; `loads_strict(line: str) -> dict`; `TrialRecord` (frozen kw-only dataclass).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_registry_record.py
import math
import pytest
from cli.registry.errors import RegistryCorruptionError
from cli.registry.record import SCHEMA_VERSION, VERDICTS, canonical_json, compute_hash, loads_strict


def test_canonical_json_is_deterministic_and_sorted():
    a = canonical_json({"b": 2, "a": 1})
    assert a == '{"a":1,"b":2}'
    assert canonical_json({"a": 1, "b": 2}) == a  # key order irrelevant


def test_canonical_json_refuses_to_emit_nan_or_inf():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            canonical_json({"dsr": bad})


def test_compute_hash_stable_and_order_independent():
    h1 = compute_hash({"a": 1, "b": [1, 2]})
    h2 = compute_hash({"b": [1, 2], "a": 1})
    assert h1 == h2 and len(h1) == 64


def test_loads_strict_rejects_bare_nan_token():
    # Python's json HAPPILY round-trips the bare NaN token by default; we must not.
    with pytest.raises(RegistryCorruptionError):
        loads_strict('{"dsr": NaN}')
    for tok in ("Infinity", "-Infinity"):
        with pytest.raises(RegistryCorruptionError):
            loads_strict('{"x": %s}' % tok)


def test_loads_strict_accepts_finite():
    assert loads_strict('{"dsr":0.3,"n":[1,2]}') == {"dsr": 0.3, "n": [1, 2]}


def test_constants():
    assert SCHEMA_VERSION == 1 and VERDICTS == frozenset({"adopt", "reject", "park"})
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_record.py -q`
Expected: FAIL (`ModuleNotFoundError: cli.registry`).

- [ ] **Step 3: Implement `errors.py`**

```python
# cli/registry/errors.py
from __future__ import annotations


class RegistryError(Exception):
    """A trial-registry validation or integrity rule was violated."""


class RegistryCorruptionError(RegistryError):
    """A persisted registry line is malformed or carries a non-finite JSON token."""
```

- [ ] **Step 4: Implement `record.py` primitives**

```python
# cli/registry/record.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cli.registry.errors import RegistryCorruptionError

SCHEMA_VERSION = 1
VERDICTS = frozenset({"adopt", "reject", "park"})

_STORE_OWNED = ("trial_id", "schema_version", "timestamp", "record_hash")
_REQUIRED_CALLER = ("iteration", "family", "spec_hash", "dataset_hash", "seeds", "metrics", "n_trials_in_family", "verdict")


def canonical_json(obj: dict) -> str:
    # sort_keys + compact + allow_nan=False -> byte-stable line the store can never emit NaN/Inf into.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def compute_hash(fields: dict) -> str:
    return hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()


def _reject_constant(token: str):
    raise RegistryCorruptionError(f"non-finite JSON token {token!r} in registry line")


def loads_strict(line: str) -> dict:
    # parse_constant fires for the bare NaN/Infinity/-Infinity tokens json.loads accepts by default.
    return json.loads(line, parse_constant=_reject_constant)


@dataclass(frozen=True, kw_only=True)
class TrialRecord:
    trial_id: int
    schema_version: int
    timestamp: str
    iteration: str
    family: str
    spec_hash: str
    dataset_hash: str
    seeds: tuple[int, ...]
    metrics: dict
    n_trials_in_family: int
    verdict: str
    run_ref: str | None
    notes: str
    record_hash: str
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_registry_record.py -q` → all pass.

- [ ] **Step 6: Commit** (stage → `uv run pre-commit run -a` → re-stage → commit `feat(registry): add errors + serialization/hashing primitives`).

---

### Task 2: Record validation (finite walk + caller/stored validators)

**Files:**
- Modify: `cli/registry/record.py` (append validators)
- Test: `tests/test_registry_record.py` (append cases)

**Interfaces:**
- Consumes: `canonical_json`, `compute_hash`, `SCHEMA_VERSION`, `VERDICTS`, `_STORE_OWNED`, `_REQUIRED_CALLER`, `RegistryError`, `RegistryCorruptionError`.
- Produces: `validate_caller_fields(f: dict) -> None`; `validate_stored_record(rec: dict, where: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_registry_record.py  (append)
import pytest
from cli.registry.errors import RegistryCorruptionError, RegistryError
from cli.registry.record import SCHEMA_VERSION, compute_hash, validate_caller_fields, validate_stored_record


def _caller(**over):
    f = dict(iteration="iter-001", family="A1", spec_hash="s", dataset_hash="d",
             seeds=[0], metrics={"sharpe": 0.3, "dsr": 0.1}, n_trials_in_family=1, verdict="adopt")
    f.update(over)
    return f


def test_valid_caller_passes():
    validate_caller_fields(_caller())


@pytest.mark.parametrize("over", [
    {"iteration": ""}, {"family": 5}, {"verdict": "maybe"},
    {"seeds": [0, True]},                 # bool is not int
    {"n_trials_in_family": True},         # bool is not int
    {"metrics": {}},                      # empty
    {"metrics": {"x": float("nan")}},     # flat NaN
    {"metrics": {"cv": {"paths": [0.1, float("inf")]}}},  # NaN/inf buried in a nested list
    {"trial_id": 9},                      # caller supplied a store-owned field
])
def test_invalid_caller_rejected(over):
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(**over))


def test_seeds_may_be_empty_but_metrics_may_not():
    validate_caller_fields(_caller(seeds=[]))            # deterministic strategy: OK
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(metrics={}))


def test_stored_record_hash_and_schema_checks():
    body = dict(_caller(), trial_id=1, schema_version=SCHEMA_VERSION, timestamp="2026-07-07T00:00:00+00:00")
    rec = dict(body, record_hash=compute_hash(body))
    validate_stored_record(rec, "x")                    # OK
    bad = dict(rec, metrics={"sharpe": 0.9, "dsr": 0.1})  # mutated, hash now stale
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(bad, "x")
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(dict(rec, schema_version=999), "x")
```

- [ ] **Step 2: Run to verify fail** (`ImportError: validate_caller_fields`).

- [ ] **Step 3: Implement the validators in `record.py`**

```python
import math  # add to the imports block

from cli.registry.errors import RegistryCorruptionError, RegistryError  # widen the existing import


def _assert_finite(value, path: str) -> None:
    if type(value) is dict:
        for k, v in value.items():
            if type(k) is not str:
                raise RegistryError(f"{path}: metric key {k!r} is not a str")
            _assert_finite(v, f"{path}.{k}")
    elif type(value) is list:
        for i, v in enumerate(value):
            _assert_finite(v, f"{path}[{i}]")
    elif type(value) in (int, float):  # type() is-strict: rejects bool and numpy scalars
        if not math.isfinite(value):
            raise RegistryError(f"{path}: non-finite metric value {value!r}")
    else:
        raise RegistryError(f"{path}: unsupported metric leaf type {type(value).__name__} (pass builtin int/float)")


def validate_caller_fields(f: dict) -> None:
    supplied_owned = [k for k in _STORE_OWNED if k in f]
    if supplied_owned:
        raise RegistryError(f"caller must not supply store-owned field(s): {supplied_owned}")
    missing = [k for k in _REQUIRED_CALLER if k not in f]
    if missing:
        raise RegistryError(f"missing required field(s): {missing}")
    for key in ("iteration", "family", "spec_hash", "dataset_hash"):
        if type(f[key]) is not str or not f[key]:
            raise RegistryError(f"{key} must be a non-empty str")
    if type(f["seeds"]) is not list or any(type(s) is not int for s in f["seeds"]):
        raise RegistryError("seeds must be a list[int] (may be empty)")
    if type(f["metrics"]) is not dict or not f["metrics"]:
        raise RegistryError("metrics must be a non-empty dict")
    _assert_finite(f["metrics"], "metrics")
    if type(f["n_trials_in_family"]) is not int or f["n_trials_in_family"] < 1:
        raise RegistryError("n_trials_in_family must be an int >= 1")
    if f["verdict"] not in VERDICTS:
        raise RegistryError(f"verdict must be one of {sorted(VERDICTS)}")
    if f.get("run_ref") is not None and type(f["run_ref"]) is not str:
        raise RegistryError("run_ref must be a str or None")
    if type(f.get("notes", "")) is not str:
        raise RegistryError("notes must be a str")


def validate_stored_record(rec: dict, where: str) -> None:
    if rec.get("schema_version") != SCHEMA_VERSION:
        raise RegistryCorruptionError(f"{where}: unknown schema_version {rec.get('schema_version')!r}")
    if "record_hash" not in rec:
        raise RegistryCorruptionError(f"{where}: missing record_hash")
    body = {k: v for k, v in rec.items() if k != "record_hash"}
    if compute_hash(body) != rec["record_hash"]:
        raise RegistryCorruptionError(f"{where}: record_hash mismatch (record was mutated)")
    if type(rec.get("trial_id")) is not int:
        raise RegistryCorruptionError(f"{where}: trial_id must be int")
    caller = {k: v for k, v in rec.items() if k not in _STORE_OWNED}
    validate_caller_fields(caller)
```

- [ ] **Step 4: Run tests — expect PASS.**
- [ ] **Step 5: Commit** (`feat(registry): add trial-record validation (recursive finite walk, caller/stored validators)`).

---

### Task 3: Store load path (JSONL read, torn-tail heal, cross-record asserts)

**Files:**
- Create: `cli/registry/store.py` (load path only; `append` in Task 4)
- Modify: `cli/registry/__init__.py` (re-exports)
- Test: `tests/test_registry_store.py`

**Interfaces:**
- Consumes: `record.py` public functions; `cli.logging.get_logger`.
- Produces: `TrialRegistry(path)` with `.records`, `__len__`; module helpers `_read_healing`, `_assert_cross_record`, `_to_record`. `__init__.py` re-exports `TrialRegistry, TrialRecord, RegistryError, RegistryCorruptionError, VERDICTS, SCHEMA_VERSION`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_registry_store.py
import pytest
from cli.registry import RegistryCorruptionError, SCHEMA_VERSION, TrialRegistry
from cli.registry.record import canonical_json, compute_hash


def _line(trial_id, family="A1", n=1, metrics=None):
    body = dict(trial_id=trial_id, schema_version=SCHEMA_VERSION, timestamp="2026-07-07T00:00:00+00:00",
                iteration="iter-001", family=family, spec_hash="s", dataset_hash="d", seeds=[0],
                metrics=metrics or {"sharpe": 0.3, "dsr": 0.1}, n_trials_in_family=n, verdict="adopt",
                run_ref=None, notes="")
    return canonical_json(dict(body, record_hash=compute_hash(body)))


def _write(tmp_path, lines, trailing_nl=True):
    p = tmp_path / "trials.jsonl"
    text = "\n".join(lines)
    if trailing_nl and lines:
        text += "\n"
    p.write_text(text, encoding="utf-8")
    return p


def test_absent_and_empty_file_is_empty_registry(tmp_path):
    assert len(TrialRegistry(tmp_path / "none.jsonl")) == 0
    assert len(TrialRegistry(_write(tmp_path, []))) == 0


def test_valid_file_loads(tmp_path):
    reg = TrialRegistry(_write(tmp_path, [_line(1), _line(2)]))
    assert len(reg) == 2 and reg.records[1].trial_id == 2


def test_bare_nan_token_line_raises(tmp_path):
    poison = '{"trial_id":1,"schema_version":1,"metrics":{"dsr":NaN}}'
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [poison]))


def test_contiguity_violation_raises(tmp_path):
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [_line(1), _line(3)]))       # gap
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [_line(2), _line(1)]))       # reorder


def test_record_hash_mismatch_raises(tmp_path):
    good = _line(1)
    tampered = good.replace('"sharpe":0.3', '"sharpe":0.9')          # finite->finite edit, hash now stale
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [tampered]))


def test_torn_trailing_line_self_heals(tmp_path):
    p = _write(tmp_path, [_line(1)])
    with p.open("a", encoding="utf-8") as f:
        f.write('{"trial_id":2,"fam')                                # crash mid-append, NO trailing newline
    reg = TrialRegistry(p)                                           # heals, does not raise
    assert len(reg) == 1
    assert p.read_text(encoding="utf-8").endswith("}\n")            # partial line physically truncated


def test_torn_interior_line_raises(tmp_path):
    # same partial content but as an INTERIOR line (file ends in newline) -> body corruption, must raise
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, ['{"trial_id":1,"fam', _line(2)]))


def test_unknown_schema_version_raises(tmp_path):
    body = dict(trial_id=1, schema_version=999, timestamp="t", iteration="i", family="A1", spec_hash="s",
                dataset_hash="d", seeds=[0], metrics={"dsr": 0.1}, n_trials_in_family=1, verdict="adopt",
                run_ref=None, notes="")
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [line]))
```

- [ ] **Step 2: Run to verify fail** (`ModuleNotFoundError`/`ImportError`).

- [ ] **Step 3: Implement `store.py` (load path)**

```python
# cli/registry/store.py
from __future__ import annotations

import json
import os
from pathlib import Path

from cli.logging.get_logger import get_logger
from cli.registry.errors import RegistryCorruptionError
from cli.registry.record import (
    SCHEMA_VERSION,
    TrialRecord,
    canonical_json,
    compute_hash,
    loads_strict,
    validate_caller_fields,
    validate_stored_record,
)

logger = get_logger("registry.store")


def _to_record(rec: dict) -> TrialRecord:
    return TrialRecord(
        trial_id=rec["trial_id"], schema_version=rec["schema_version"], timestamp=rec["timestamp"],
        iteration=rec["iteration"], family=rec["family"], spec_hash=rec["spec_hash"],
        dataset_hash=rec["dataset_hash"], seeds=tuple(rec["seeds"]), metrics=rec["metrics"],
        n_trials_in_family=rec["n_trials_in_family"], verdict=rec["verdict"],
        run_ref=rec.get("run_ref"), notes=rec.get("notes", ""), record_hash=rec["record_hash"],
    )


def _assert_cross_record(recs: list[dict], path: Path) -> None:
    seen: dict[str, int] = {}
    for idx, rec in enumerate(recs):
        if rec["trial_id"] != idx + 1:
            raise RegistryCorruptionError(f"{path}: trial_id {rec['trial_id']} not contiguous (expected {idx + 1})")
        prior = seen.get(rec["family"], 0)
        if rec["n_trials_in_family"] < prior + 1:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} n_trials_in_family={rec['n_trials_in_family']} < {prior + 1} in family {rec['family']!r}"
            )
        seen[rec["family"]] = prior + 1


def _read_healing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if not raw:
        return []
    text = raw.decode("utf-8")
    ends_nl = text.endswith("\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    out: list[dict] = []
    for i, line in enumerate(lines):
        is_last = i == len(lines) - 1
        try:
            rec = loads_strict(line)
        except RegistryCorruptionError:
            raise  # NaN/Inf token is always poison — never self-heal
        except json.JSONDecodeError as e:
            if is_last and not ends_nl:
                logger.warning("registry %s: truncating unparseable torn trailing line", path)
                nl = raw.rfind(b"\n")
                with open(path, "r+b") as fh:
                    fh.truncate(nl + 1 if nl >= 0 else 0)
                break
            raise RegistryCorruptionError(f"{path}: malformed JSON at line {i + 1}") from e
        validate_stored_record(rec, f"{path} line {i + 1}")
        out.append(rec)
    _assert_cross_record(out, path)
    return out


class TrialRegistry:
    """Append-only, integrity-checked JSONL store of validation trials. See docs/specs/00000-trial-registry-design.md.

    The record_hash self-check catches accidental/careless in-place edits (and, with contiguity, deletion/
    reorder/truncation); it is NOT tamper-evidence against a re-hashing writer — that is the Phase-2 hash chain.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records = tuple(_to_record(r) for r in _read_healing(self.path))

    @property
    def records(self) -> tuple[TrialRecord, ...]:
        return self._records

    def __len__(self) -> int:
        return len(self._records)
```

- [ ] **Step 4: Implement `__init__.py`**

```python
# cli/registry/__init__.py
from cli.registry.errors import RegistryCorruptionError, RegistryError
from cli.registry.record import SCHEMA_VERSION, VERDICTS, TrialRecord
from cli.registry.store import TrialRegistry

__all__ = ["TrialRegistry", "TrialRecord", "RegistryError", "RegistryCorruptionError", "VERDICTS", "SCHEMA_VERSION"]
```

- [ ] **Step 5: Run tests — expect PASS.**
- [ ] **Step 6: Commit** (`feat(registry): add append-only JSONL load with torn-tail heal + cross-record asserts`).

---

### Task 4: Store append (flock, fsync, id assignment, store-owned stamping)

**Files:**
- Modify: `cli/registry/store.py` (add `append` + `_now_utc_iso`)
- Test: `tests/test_registry_store.py` (append cases)

**Interfaces:**
- Consumes: everything from Task 3 + `fcntl`, `datetime`.
- Produces: `TrialRegistry.append(*, iteration, family, spec_hash, dataset_hash, seeds, metrics, n_trials_in_family, verdict, run_ref=None, notes="") -> TrialRecord`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_registry_store.py  (append)
import pytest
from cli.registry import RegistryError, TrialRegistry


def _append(reg, **over):
    kw = dict(iteration="iter-001", family="A1", spec_hash="s", dataset_hash="d", seeds=[0],
              metrics={"sharpe": 0.3, "dsr": 0.1}, n_trials_in_family=2, verdict="adopt")
    kw.update(over)
    return reg.append(**kw)


def test_append_assigns_contiguous_ids_across_reopen(tmp_path):
    p = tmp_path / "t.jsonl"
    r1 = _append(TrialRegistry(p))
    assert r1.trial_id == 1 and r1.record_hash and r1.timestamp.endswith("+00:00")
    r2 = _append(TrialRegistry(p))                 # fresh registry, same path
    assert r2.trial_id == 2
    assert len(TrialRegistry(p)) == 2              # reload verifies all asserts


def test_append_rejects_nonfinite_before_writing(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), metrics={"dsr": float("nan")})
    assert not p.exists() or p.read_text() == ""   # nothing was written


def test_append_family_count_floor(tmp_path):
    p = tmp_path / "t.jsonl"
    _append(TrialRegistry(p), family="A1", n_trials_in_family=1)     # 1st in A1, floor is 1 -> OK
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), family="A1", n_trials_in_family=1)  # 2nd in A1 needs >= 2


def test_append_then_records_snapshot(tmp_path):
    reg = TrialRegistry(tmp_path / "t.jsonl")
    _append(reg)
    assert reg.records[-1].trial_id == 1           # in-memory cache updated


def test_concurrent_registries_get_unique_ids(tmp_path):
    p = tmp_path / "t.jsonl"
    a, b = TrialRegistry(p), TrialRegistry(p)       # both see empty
    _append(a)
    _append(b)                                      # b re-reads under lock -> id 2, not a duplicate 1
    ids = sorted(r.trial_id for r in TrialRegistry(p).records)
    assert ids == [1, 2]
```

- [ ] **Step 2: Run to verify fail** (`AttributeError: append`).

- [ ] **Step 3: Implement `append` in `store.py`**

```python
import fcntl                                   # add to imports
from datetime import datetime, timezone        # add to imports


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- add as a method on TrialRegistry ----
    def append(self, *, iteration: str, family: str, spec_hash: str, dataset_hash: str,
               seeds: list[int], metrics: dict, n_trials_in_family: int, verdict: str,
               run_ref: str | None = None, notes: str = "") -> TrialRecord:
        caller = dict(iteration=iteration, family=family, spec_hash=spec_hash, dataset_hash=dataset_hash,
                      seeds=list(seeds), metrics=metrics, n_trials_in_family=n_trials_in_family,
                      verdict=verdict, run_ref=run_ref, notes=notes)
        validate_caller_fields(caller)                 # raises on non-finite metric BEFORE opening the file
        lock_f = open(self.path, "a", encoding="utf-8")
        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            disk = _read_healing(self.path)            # re-derive from disk under lock — the file is authoritative
            next_id = disk[-1]["trial_id"] + 1 if disk else 1
            prior = sum(1 for r in disk if r["family"] == family)
            if n_trials_in_family < prior + 1:
                raise RegistryError(
                    f"n_trials_in_family={n_trials_in_family} < {prior + 1} already recorded in family {family!r}"
                )
            rec = {**caller, "trial_id": next_id, "schema_version": SCHEMA_VERSION, "timestamp": _now_utc_iso()}
            rec["record_hash"] = compute_hash(rec)
            lock_f.write(canonical_json(rec) + "\n")
            lock_f.flush()
            os.fsync(lock_f.fileno())
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            lock_f.close()
        record = _to_record(rec)
        self._records = (*self._records, record)
        return record
```

- [ ] **Step 4: Run the full registry suite — expect PASS.**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`

- [ ] **Step 5: Commit** (`feat(registry): add locked append with fsync, id assignment, and family-count floor`).

---

### Task 5: Iterations-history closeout

**Files:**
- Modify: `docs/iterations-history.md`

- [ ] **Step 1: Append the iter-001 entry**

```markdown
## 2026-07-07 — iter-001: trial registry (Phase 0 · P0-1)

- Added `cli/registry/` — the append-only, integrity-checked JSONL trial registry (`TrialRegistry`, `TrialRecord`, `RegistryError`/`RegistryCorruptionError`), stdlib-only, mirroring `cli/logging/`.
- Encodes the PoC NaN-DSR failure on both paths: `json.dumps(allow_nan=False)` on write and `json.loads(parse_constant=…)` on read, plus a recursive finiteness walk over nested dicts/lists of metrics.
- Integrity by construction: monotonic-contiguous `trial_id`, per-record `record_hash` self-check (accidental-edit detection; the cross-record hash chain is deferred to Phase 2), `n_trials_in_family` >= recorded-family-count floor, `fcntl.flock`+`fsync` append, and a torn-trailing-line self-heal so a crashed append never bricks the autonomous loop.
- Design/plan: `docs/specs/00000-trial-registry-design.md`, `docs/plans/00000-trial-registry.md`. Deferred to Phase 2: the cross-record hash chain, the corrupt-a-copy CI test, and SPA/DSR computation. Phase 0 human-gated items parked in open-topic `T0000`.
```

- [ ] **Step 2: Commit** (`docs: iter-001 closeout — trial registry`).

---

## Self-Review

- **Spec coverage:** schema table → Task 1/2 (`TrialRecord` + validators); JSONL/canonical/NaN-defense → Task 1 (`canonical_json`/`loads_strict`) + Task 3 (read path); integrity asserts 1–8 → Task 2 (fields/finite/verdict/schema/hash) + Task 3 (contiguity, family-count, well-formed, torn-tail) + Task 4 (append-time family floor); immutability self-hash → Task 2/3; identity+flock → Task 4; torn-tail → Task 3; API surface + module layout → Tasks 3/4 + `__init__`; test suite (all planted-corruption cases) → Tasks 1–4; Phase-2 deferrals → not built (correct); closeout → Task 5. No gaps.
- **Placeholders:** none — every step carries real code.
- **Type consistency:** `validate_caller_fields`/`validate_stored_record`/`canonical_json`/`compute_hash`/`loads_strict`/`_read_healing`/`_assert_cross_record`/`_to_record`/`TrialRegistry.append` names and signatures are identical across the tasks that define and consume them; `TrialRecord` field set matches the spec table and `_to_record`.
