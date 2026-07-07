from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from cli.registry.errors import RegistryCorruptionError, RegistryError

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
