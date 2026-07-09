from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from cli.registry.errors import RegistryCorruptionError, RegistryError

SCHEMA_VERSION = 3
_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3})
GENESIS_HASH = "0" * 64
VERDICTS = frozenset({"adopt", "reject", "park"})

_STORE_OWNED = ("trial_id", "schema_version", "timestamp", "prev_hash", "record_hash")
_REQUIRED_CALLER = ("iteration", "family", "spec_hash", "dataset_hash", "seeds", "metrics", "n_trials_in_family", "verdict")

_BASE_STORED_KEYS = frozenset(_STORE_OWNED) | frozenset(_REQUIRED_CALLER) | {"run_ref", "notes"}
_EXPECTED_STORED_KEYS = {2: _BASE_STORED_KEYS, 3: _BASE_STORED_KEYS | {"variant"}}


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
    if f.get("variant") is not None and (type(f["variant"]) is not str or not f["variant"]):
        raise RegistryError("variant must be a non-empty str or None")
    if type(f.get("notes", "")) is not str:
        raise RegistryError("notes must be a str")


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
    caller = {k: v for k, v in rec.items() if k not in _STORE_OWNED}
    validate_caller_fields(caller)


@dataclass(frozen=True, kw_only=True)
class TrialRecord:
    """A single trial record. `variant` is schema_version 3+ only: str | None, omitted from the serialized
    line entirely when None (schema_version 2 records may never carry the key at all).

    Historical note: trial_id 25-32 (family="A1", schema_version 2) predate this field. They encode their
    variant in free-text `notes` instead (e.g. "variant=A2-donchian; lookbacks=..."), all mapping to
    variant="A2-donchian". This is deliberately not backfilled — the registry is append-only — so readers
    of those eight records must consult `notes`, not `variant`.
    """

    trial_id: int
    schema_version: int
    timestamp: str
    iteration: str
    family: str
    variant: str | None = None
    spec_hash: str
    dataset_hash: str
    seeds: tuple[int, ...]
    metrics: dict
    n_trials_in_family: int
    verdict: str
    run_ref: str | None
    notes: str
    prev_hash: str
    record_hash: str
