from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from cli.registry.errors import RegistryCorruptionError, RegistryError

SCHEMA_VERSION = 4
_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})
GENESIS_HASH = "0" * 64
VERDICTS = frozenset({"adopt", "reject", "park"})

_STORE_OWNED = ("trial_id", "schema_version", "timestamp", "prev_hash", "record_hash", "dataset_hash")
_REQUIRED_CALLER = ("iteration", "family", "spec_hash", "seeds", "metrics", "n_trials_in_family", "verdict")

_BASE_STORED_KEYS = frozenset(_STORE_OWNED) | frozenset(_REQUIRED_CALLER) | {"run_ref", "notes"}
_EXPECTED_STORED_KEYS = {
    2: _BASE_STORED_KEYS,
    3: _BASE_STORED_KEYS | {"variant"},
    4: _BASE_STORED_KEYS | {"variant", "datasets"},
}

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def canonical_json(obj: dict) -> str:
    # sort_keys + compact + allow_nan=False -> byte-stable line the store can never emit NaN/Inf into.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def compute_hash(fields: dict) -> str:
    return hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()


_REPO_ROOT = Path(__file__).resolve().parents[2]  # cli/registry/record.py -> repo root
_SCRATCHPAD_MARKER = "scratchpad"
_TOKEN_PUNCTUATION = "(),;:+'\"`[]<>"


def run_ref_path_candidates(run_ref: str) -> list[str]:
    """The path-like tokens in a free-text `run_ref`, in order; absolute and `..` tokens are dropped because provenance means a
    path inside the repo, and `.` segments are stripped so this and `tests/test_trial_registry_provenance.py`, which feeds the
    same tokens to `git ls-files`, accept the same spellings — the registry being append-only, a record that passed the append
    guard and failed that test could never be repaired."""
    out: list[str] = []
    for raw in run_ref.split():
        token = raw.strip(_TOKEN_PUNCTUATION)
        if not token or token.startswith("/"):
            continue
        if "/" not in token and "." not in token:
            continue
        parts = token.split("/")
        if ".." in parts:
            continue
        canonical = "/".join(p for p in parts if p not in (".", ""))
        if not canonical:
            continue
        out.append(canonical)
    return out


def _resolves_in_repo(token: str) -> bool:
    try:
        return (_REPO_ROOT / token).is_file()  # is_file, not exists: a directory is not a runner
    except OSError:
        return False  # an over-long or otherwise unusable token is simply not a path


def _validate_run_ref(run_ref) -> None:
    """Append-time provenance guard: a trial that cannot be pointed back at code is not recordable; no subprocess and no git,
    since this runs on every append, so committedness is left to `tests/test_trial_registry_provenance.py` over the real
    registry."""
    if type(run_ref) is not str or not run_ref:
        raise RegistryError(
            f"run_ref must be a non-empty str naming a repo-relative path to the code that produced this run "
            f"(got {run_ref!r}); e.g. run_ref='cli/portfolio/crossfreq_system.py'"
        )
    if _SCRATCHPAD_MARKER in run_ref.lower():
        raise RegistryError(
            f"run_ref names a scratchpad, which records no recoverable provenance: {run_ref!r}. Scratchpad "
            f"scripts are session-scoped and are gone by the time anyone re-reads this record, leaving its "
            f"verdict permanently unreproducible. Commit the runner into the repo first, then reference its "
            f"repo-relative path."
        )
    candidates = run_ref_path_candidates(run_ref)
    if not any(_resolves_in_repo(c) for c in candidates):
        raise RegistryError(
            f"run_ref names no repo-relative file that exists: {run_ref!r}. At least one path-like token must "
            f"resolve under {_REPO_ROOT} (tokens checked: {candidates or 'none — run_ref contains no path'}). "
            f"Commit the code that produced this run, then reference its repo-relative path."
        )


def _reject_constant(token: str):
    raise RegistryCorruptionError(f"non-finite JSON token {token!r} in registry line")


def loads_strict(line: str) -> dict:
    # parse_constant fires for the bare NaN/Infinity/-Infinity tokens json.loads accepts by default.
    return json.loads(line, parse_constant=_reject_constant)


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


def validate_caller_fields(f: dict, *, check_run_ref_provenance: bool = True) -> None:
    """Validate the caller-supplied half of a record; `check_run_ref_provenance` is off only for stored-record re-validation,
    because the registry is append-only and records written before the guard existed must keep loading."""
    supplied_owned = [k for k in _STORE_OWNED if k in f]
    if supplied_owned:
        raise RegistryError(f"caller must not supply store-owned field(s): {supplied_owned}")
    missing = [k for k in _REQUIRED_CALLER if k not in f]
    if missing:
        raise RegistryError(f"missing required field(s): {missing}")
    for key in ("iteration", "family", "spec_hash"):
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
    if check_run_ref_provenance:
        _validate_run_ref(f.get("run_ref"))
    elif f.get("run_ref") is not None and type(f["run_ref"]) is not str:
        raise RegistryError("run_ref must be a str or None")
    if f.get("variant") is not None and (type(f["variant"]) is not str or not f["variant"]):
        raise RegistryError("variant must be a non-empty str or None")
    if type(f.get("notes", "")) is not str:
        raise RegistryError("notes must be a str")


def _is_relative_posix_path(value) -> bool:
    # Form only, no disk access: a key escaping its dataset directory would point
    # tests/test_registry_conformance.py at a real repo file outside data/ and re-hash it green.
    return type(value) is str and bool(value) and not value.startswith("/") and "\\" not in value and ".." not in value.split("/")


def _validate_datasets_shape(datasets, where: str) -> None:
    """Pure FORM check of the observed-datasets block — no disk access, no allowlist knowledge."""
    if type(datasets) is not dict or not datasets:
        raise RegistryCorruptionError(f"{where}: datasets must be a non-empty dict")
    for name, block in datasets.items():
        if not _is_relative_posix_path(name):
            raise RegistryCorruptionError(f"{where}: datasets key must be a relative path with no '..' segment")
        if type(block) is not dict:
            raise RegistryCorruptionError(f"{where}: datasets entry must be a dict")
        for key in ("files", "rows", "span"):
            if key not in block:
                raise RegistryCorruptionError(f"{where}: datasets[{name!r}] is missing {key}")
        if set(block) - {"files", "rows", "span"}:
            raise RegistryCorruptionError(f"{where}: datasets entry carries unknown key(s)")
        if type(block["files"]) is not dict or not block["files"]:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] files must be a non-empty dict")
        for relpath, digest in block["files"].items():
            if not _is_relative_posix_path(relpath):
                raise RegistryCorruptionError(f"{where}: datasets[{name!r}] files key must be a relative path with no '..' segment")
            if type(digest) is not str or not _SHA256_HEX.fullmatch(digest):
                raise RegistryCorruptionError(f"{where}: datasets[{name!r}] files value must be a 64-char lowercase hex digest")
        if type(block["rows"]) is not int or block["rows"] < 1:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] rows must be an int >= 1")
        if type(block["span"]) is not list or len(block["span"]) != 2 or any(type(s) is not str for s in block["span"]):
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] span must be a list of exactly 2 str")


def validate_stored_record(rec: dict, where: str) -> None:
    version = rec.get("schema_version")
    if version not in _LOADABLE_SCHEMA_VERSIONS:
        raise RegistryCorruptionError(f"{where}: unknown schema_version {version!r}")
    surplus = sorted(set(rec) - _EXPECTED_STORED_KEYS[version])
    if surplus:
        raise RegistryCorruptionError(f"{where}: unknown key(s) {surplus} for schema_version {version}")
    missing = sorted(_BASE_STORED_KEYS - set(rec))
    if missing:
        raise RegistryCorruptionError(f"{where}: missing required key(s) {missing}")
    if version == 2 and "variant" in rec:
        raise RegistryCorruptionError(f"{where}: schema_version 2 record must not carry a variant field")
    if "variant" in rec and type(rec["variant"]) is not str:
        raise RegistryCorruptionError(f"{where}: variant must be a str when present")
    if "record_hash" not in rec:
        raise RegistryCorruptionError(f"{where}: missing record_hash")
    body = {k: v for k, v in rec.items() if k != "record_hash"}
    if compute_hash(body) != rec["record_hash"]:
        raise RegistryCorruptionError(f"{where}: record_hash mismatch (record was mutated)")
    if type(rec.get("prev_hash")) is not str or len(rec["prev_hash"]) != 64:
        raise RegistryCorruptionError(f"{where}: prev_hash must be a 64-char hex str")
    if type(rec.get("trial_id")) is not int:
        raise RegistryCorruptionError(f"{where}: trial_id must be int")
    # dataset_hash is store-owned, so the caller-field re-validation below never sees it.
    if type(rec.get("dataset_hash")) is not str or not rec["dataset_hash"]:
        raise RegistryCorruptionError(f"{where}: dataset_hash must be a non-empty str")
    if version >= 4:
        if "datasets" not in rec:
            raise RegistryCorruptionError(f"{where}: schema_version 4 record must carry a datasets block")
        _validate_datasets_shape(rec["datasets"], where)
        if rec["dataset_hash"] != compute_hash(rec["datasets"]):
            raise RegistryCorruptionError(f"{where}: dataset_hash is not the digest of this record's datasets block")
    caller = {k: v for k, v in rec.items() if k not in _STORE_OWNED}
    validate_caller_fields(caller, check_run_ref_provenance=False)


@dataclass(frozen=True, kw_only=True)
class TrialRecord:
    """A single trial record; `variant` is schema_version 3+ only, omitted from the serialized line when None. Trials 25-32
    (family A1, schema_version 2) predate the field and carry theirs in free-text `notes` (`variant=A2-donchian`), never
    backfilled because the registry is append-only, so a reader selecting on `variant` misses them."""

    trial_id: int
    schema_version: int
    timestamp: str
    iteration: str
    family: str
    variant: str | None = None
    spec_hash: str
    dataset_hash: str
    datasets: dict | None = None
    seeds: tuple[int, ...]
    metrics: dict
    n_trials_in_family: int
    verdict: str
    run_ref: str | None
    notes: str
    prev_hash: str
    record_hash: str
