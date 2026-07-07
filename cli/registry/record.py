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
