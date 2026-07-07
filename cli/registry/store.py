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
        trial_id=rec["trial_id"],
        schema_version=rec["schema_version"],
        timestamp=rec["timestamp"],
        iteration=rec["iteration"],
        family=rec["family"],
        spec_hash=rec["spec_hash"],
        dataset_hash=rec["dataset_hash"],
        seeds=tuple(rec["seeds"]),
        metrics=rec["metrics"],
        n_trials_in_family=rec["n_trials_in_family"],
        verdict=rec["verdict"],
        run_ref=rec.get("run_ref"),
        notes=rec.get("notes", ""),
        record_hash=rec["record_hash"],
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
