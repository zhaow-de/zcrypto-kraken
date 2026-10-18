from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cli.logging.get_logger import get_logger
from cli.registry.errors import RegistryCorruptionError, RegistryError
from cli.registry.record import (
    GENESIS_HASH,
    READING_SCHEMA_VERSION,
    SCHEMA_VERSION,
    ReadingRecord,
    TrialRecord,
    canonical_json,
    compute_hash,
    loads_strict,
    validate_caller_fields,
    validate_reading_fields,
    validate_record_attempt,
    validate_stored_reading,
    validate_stored_record,
)

logger = get_logger("registry.store")

# The highest trial_id predating the datasets block; the file is append-only, so an exemption by ID can never grow.
_LEGACY_UNPROVENANCED_MAX_TRIAL_ID = 46
# The highest trial_id predating the invocation (docs/specs/00129 D1), fixed for the same reason.
_INVOCATION_FLOOR_TRIAL_ID = 47
# The highest trial_id and reading_id predating the attempt (docs/specs/00133 D8), fixed for the same reason.
_ATTEMPT_FLOOR_TRIAL_ID = 48
_ATTEMPT_FLOOR_READING_ID = 1


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
        invocation=rec.get("invocation"),
        attempt=rec.get("attempt"),
        seeds=tuple(rec["seeds"]),
        metrics=rec["metrics"],
        n_trials_in_family=rec["n_trials_in_family"],
        verdict=rec["verdict"],
        run_ref=rec.get("run_ref"),
        notes=rec.get("notes", ""),
        prev_hash=rec["prev_hash"],
        record_hash=rec["record_hash"],
    )


def _refuse_an_id_out_of_place(recs: list[dict], idx: int, path: Path, id_key: str) -> None:
    if recs[idx][id_key] != idx + 1:
        raise RegistryCorruptionError(f"{path}: {id_key} {recs[idx][id_key]} not contiguous (expected {idx + 1})")


def _refuse_a_broken_link(recs: list[dict], idx: int, path: Path, id_key: str) -> None:
    expected_prev = GENESIS_HASH if idx == 0 else recs[idx - 1]["record_hash"]
    if recs[idx]["prev_hash"] != expected_prev:
        raise RegistryCorruptionError(f"{path}: {id_key.removesuffix('_id')} {recs[idx][id_key]} prev_hash breaks the chain")


def _assert_cross_record(recs: list[dict], path: Path) -> None:
    seen: dict[str, int] = {}
    for idx, rec in enumerate(recs):
        _refuse_an_id_out_of_place(recs, idx, path, "trial_id")
        if rec["trial_id"] > _LEGACY_UNPROVENANCED_MAX_TRIAL_ID and rec["schema_version"] < 4:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} declares schema_version {rec['schema_version']}; every "
                f"record past trial {_LEGACY_UNPROVENANCED_MAX_TRIAL_ID} must be schema_version 4+ and carry "
                f"a derived datasets block"
            )
        if rec["trial_id"] > _INVOCATION_FLOOR_TRIAL_ID and rec["schema_version"] < 5:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} declares schema_version {rec['schema_version']}; every "
                f"record past trial {_INVOCATION_FLOOR_TRIAL_ID} must be schema_version 5+ and carry "
                f"the invocation that produced it"
            )
        if rec["trial_id"] > _ATTEMPT_FLOOR_TRIAL_ID and rec["schema_version"] < 6:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} declares schema_version {rec['schema_version']}; every "
                f"record past trial {_ATTEMPT_FLOOR_TRIAL_ID} must be schema_version 6 and carry "
                f"the attempt its run's log minted"
            )
        _refuse_a_broken_link(recs, idx, path, "trial_id")
        prior = seen.get(rec["family"], 0)
        if rec["n_trials_in_family"] < prior + 1:
            raise RegistryCorruptionError(
                f"{path}: trial {rec['trial_id']} n_trials_in_family={rec['n_trials_in_family']} < {prior + 1} "
                f"in family {rec['family']!r}"
            )
        seen[rec["family"]] = prior + 1


def _to_reading(rec: dict) -> ReadingRecord:
    return ReadingRecord(**rec)


def _assert_reading_chain(recs: list[dict], path: Path) -> None:
    for idx, rec in enumerate(recs):
        _refuse_an_id_out_of_place(recs, idx, path, "reading_id")
        _refuse_a_broken_link(recs, idx, path, "reading_id")
        if rec["reading_id"] > _ATTEMPT_FLOOR_READING_ID and rec["schema_version"] < 2:
            raise RegistryCorruptionError(
                f"{path}: reading {rec['reading_id']} declares schema_version {rec['schema_version']}; every reading past "
                f"reading {_ATTEMPT_FLOOR_READING_ID} must be schema_version 2"
            )


def _read_healing(
    path: Path, validate: Callable[[dict, str], None], assert_cross_record: Callable[[list[dict], Path], None]
) -> list[dict]:
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
                logger.warning("%s: truncating unparseable torn trailing line", path)
                nl = raw.rfind(b"\n")
                with open(path, "r+b") as fh:
                    fh.truncate(nl + 1 if nl >= 0 else 0)
                break
            raise RegistryCorruptionError(f"{path}: malformed JSON at line {i + 1}") from e
        validate(rec, f"{path} line {i + 1}")
        out.append(rec)
    assert_cross_record(out, path)
    return out


def _read_trials(path: Path) -> list[dict]:
    return _read_healing(path, validate_stored_record, _assert_cross_record)


def _read_readings(path: Path) -> list[dict]:
    return _read_healing(path, validate_stored_reading, _assert_reading_chain)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_locked(
    path: Path,
    id_key: str,
    read: Callable[[Path], list[dict]],
    compose: Callable[[list[dict]], dict],
    validate: Callable[[dict, str], None],
) -> dict:
    """`compose` gets the file as re-read under the lock, which is authoritative, and builds the line's own fields."""
    lock_f = open(path, "a", encoding="utf-8")
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        disk = read(path)
        rec = compose(disk)
        rec[id_key] = disk[-1][id_key] + 1 if disk else 1
        rec["prev_hash"] = disk[-1]["record_hash"] if disk else GENESIS_HASH
        rec["dataset_hash"] = compute_hash(rec["datasets"])
        rec["record_hash"] = compute_hash(rec)
        validate(rec, f"{path} (append)")  # one bad line is permanent: refuse before the write
        lock_f.write(canonical_json(rec) + "\n")
        lock_f.flush()
        os.fsync(lock_f.fileno())
    finally:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        lock_f.close()
    return rec


class TrialRegistry:
    """Append-only, integrity-checked JSONL store of validation trials; design and non-goals in
    docs/specs/00000-trial-registry-design.md and docs/specs/00012-registry-hash-chain-design.md (the prev_hash chain).
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records = tuple(_to_record(r) for r in _read_trials(self.path))

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
        invocation: dict,  # the command's arguments and the code's commit (see validate_invocation)
        seeds: list[int],
        metrics: dict,
        n_trials_in_family: int,
        verdict: str,
        run_ref: str,  # required: must name a repo-relative path that exists (see _validate_run_ref)
        attempt: dict,
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
        validate_record_attempt(attempt, f"{self.path} (append)")

        def compose(disk: list[dict]) -> dict:
            prior = sum(1 for r in disk if r["family"] == family)
            if n_trials_in_family < prior + 1:
                raise RegistryError(f"n_trials_in_family={n_trials_in_family} < {prior + 1} already recorded in family {family!r}")
            return {
                **caller,
                "schema_version": SCHEMA_VERSION,
                "timestamp": _now_utc_iso(),
                "datasets": datasets,
                "invocation": invocation,
                "attempt": attempt,
            }

        record = _to_record(_append_locked(self.path, "trial_id", _read_trials, compose, validate_stored_record))
        self._records = (*self._records, record)
        return record


class ReadingLedger:
    """Append-only, hash-chained JSONL store of readings, through the registry's locked append and torn-line healing; its
    own class because a reading has no family, budget or verdict, which `TrialRegistry`'s validator requires
    (docs/specs/00129 D7)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records = tuple(_to_reading(r) for r in _read_readings(self.path))

    @property
    def records(self) -> tuple[ReadingRecord, ...]:
        return self._records

    def __len__(self) -> int:
        return len(self._records)

    def append(
        self,
        *,
        iteration: str,
        spec_hash: str,
        invocation: dict,
        datasets: dict,
        metrics: dict,
        outcome: str | None,
        attempt: dict | None,
        notes: str = "",
    ) -> ReadingRecord:
        caller = dict(
            iteration=iteration,
            spec_hash=spec_hash,
            invocation=invocation,
            datasets=datasets,
            metrics=metrics,
            outcome=outcome,
            notes=notes,
            attempt=attempt,
        )
        validate_reading_fields(caller, f"{self.path} (append)")  # before the open, which creates the file

        def compose(disk: list[dict]) -> dict:
            return {**caller, "schema_version": READING_SCHEMA_VERSION, "timestamp": _now_utc_iso()}

        record = _to_reading(_append_locked(self.path, "reading_id", _read_readings, compose, validate_stored_reading))
        self._records = (*self._records, record)
        return record
