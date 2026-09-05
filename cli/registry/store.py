from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cli.logging.get_logger import get_logger
from cli.registry.errors import RegistryCorruptionError, RegistryError
from cli.registry.record import (
    GENESIS_HASH,
    SCHEMA_VERSION,
    TrialRecord,
    canonical_json,
    compute_hash,
    loads_strict,
    validate_caller_fields,
    validate_stored_record,
)

logger = get_logger("registry.store")

# The highest trial_id predating the datasets block; the file is append-only, so an exemption by ID can never grow.
_LEGACY_UNPROVENANCED_MAX_TRIAL_ID = 46


def _to_record(rec: dict) -> TrialRecord:
    return TrialRecord(
        trial_id=rec["trial_id"],
        schema_version=rec["schema_version"],
        timestamp=rec["timestamp"],
        iteration=rec["iteration"],
        family=rec["family"],
        variant=rec.get("variant"),
        spec_hash=rec["spec_hash"],
        dataset_hash=rec["dataset_hash"],
        datasets=rec.get("datasets"),
        seeds=tuple(rec["seeds"]),
        metrics=rec["metrics"],
        n_trials_in_family=rec["n_trials_in_family"],
        verdict=rec["verdict"],
        run_ref=rec.get("run_ref"),
        notes=rec.get("notes", ""),
        prev_hash=rec["prev_hash"],
        record_hash=rec["record_hash"],
    )


def _assert_cross_record(recs: list[dict], path: Path) -> None:
    seen: dict[str, int] = {}
    for idx, rec in enumerate(recs):
        if rec["trial_id"] != idx + 1:
            raise RegistryCorruptionError(f"{path}: trial_id {rec['trial_id']} not contiguous (expected {idx + 1})")
        if rec["trial_id"] > _LEGACY_UNPROVENANCED_MAX_TRIAL_ID and rec["schema_version"] < 4:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} declares schema_version {rec['schema_version']}; every "
                f"record past trial {_LEGACY_UNPROVENANCED_MAX_TRIAL_ID} must be schema_version 4+ and carry "
                f"a derived datasets block"
            )
        expected_prev = GENESIS_HASH if idx == 0 else recs[idx - 1]["record_hash"]
        if rec["prev_hash"] != expected_prev:
            raise RegistryCorruptionError(f"{path}: trial {rec['trial_id']} prev_hash breaks the chain")
        prior = seen.get(rec["family"], 0)
        if rec["n_trials_in_family"] < prior + 1:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} n_trials_in_family={rec['n_trials_in_family']} < {prior + 1} "
                f"in family {rec['family']!r}"
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


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrialRegistry:
    """Append-only, integrity-checked JSONL store of validation trials; design and non-goals in
    docs/specs/00000-trial-registry-design.md and docs/specs/00012-registry-hash-chain-design.md (the prev_hash chain).
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records = tuple(_to_record(r) for r in _read_healing(self.path))

    @property
    def records(self) -> tuple[TrialRecord, ...]:
        return self._records

    def __len__(self) -> int:
        return len(self._records)

    def append(
        self,
        *,
        iteration: str,
        family: str,
        spec_hash: str,
        datasets: dict,  # the observed block (see ObservedReader.block); dataset_hash is derived from it
        seeds: list[int],
        metrics: dict,
        n_trials_in_family: int,
        verdict: str,
        run_ref: str,  # required: must name a repo-relative path that exists (see _validate_run_ref)
        notes: str = "",
        variant: str | None = None,
    ) -> TrialRecord:
        caller = dict(
            iteration=iteration,
            family=family,
            spec_hash=spec_hash,
            seeds=list(seeds),
            metrics=metrics,
            n_trials_in_family=n_trials_in_family,
            verdict=verdict,
            run_ref=run_ref,
            notes=notes,
        )
        if variant is not None:  # omit the key entirely rather than serialize a `null` (canonical form stays clean)
            caller["variant"] = variant
        validate_caller_fields(caller)  # raises on non-finite metric BEFORE opening the file
        lock_f = open(self.path, "a", encoding="utf-8")
        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            disk = _read_healing(self.path)  # re-derive from disk under lock — the file is authoritative
            next_id = disk[-1]["trial_id"] + 1 if disk else 1
            prior = sum(1 for r in disk if r["family"] == family)
            if n_trials_in_family < prior + 1:
                raise RegistryError(f"n_trials_in_family={n_trials_in_family} < {prior + 1} already recorded in family {family!r}")
            prev_hash = disk[-1]["record_hash"] if disk else GENESIS_HASH
            rec = {
                **caller,
                "trial_id": next_id,
                "schema_version": SCHEMA_VERSION,
                "timestamp": _now_utc_iso(),
                "prev_hash": prev_hash,
                "datasets": datasets,
            }
            rec["dataset_hash"] = compute_hash(rec["datasets"])
            rec["record_hash"] = compute_hash(rec)
            validate_stored_record(rec, f"{self.path} (append)")  # one bad line is permanent: refuse before the write
            lock_f.write(canonical_json(rec) + "\n")
            lock_f.flush()
            os.fsync(lock_f.fileno())
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            lock_f.close()
        record = _to_record(rec)
        self._records = (*self._records, record)
        return record
