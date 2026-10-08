"""`zcrypto engine preflight`: the offline self-test a candidate image runs against the engine host's state directory
before the engine is re-pinned to it. It writes nothing; its network boundary is the container's, not this module's
imports."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

from cli.config import CONFIG_FILENAME, ConfigError, EngineConfig, load_config
from cli.engine.errors import EngineJournalError
from cli.engine.execgate import _installed_nautilus_version, _verified_nautilus_versions
from cli.engine.journal import CycleRecord, from_json, validate_record
from cli.engine.store import BASKET, GRID_INTERVALS, _store_path


@dataclass(frozen=True)
class PreflightResult:
    config: str
    verified: bool
    stores_missing: list[str] | None
    journal: str | None
    version: str
    nautilus: str
    ok: bool

    def to_json_line(self) -> str:
        return json.dumps(asdict(self))


def _under(path: Path, root: Path) -> bool:
    return Path(os.path.normpath(path)).is_relative_to(os.path.normpath(root))


def _check_config(state_dir: Path) -> tuple[str, EngineConfig | None]:
    if not Path(CONFIG_FILENAME).exists():
        return f"no {CONFIG_FILENAME} in the working directory {Path.cwd()}", None
    try:
        engine = load_config().engine
    except ConfigError as exc:
        return str(exc), None
    for name, path in (("store_dir", engine.store_dir), ("journal_dir", engine.journal_dir)):
        if not _under(path, state_dir):
            return f"{name} {path} does not lie under the state directory {state_dir}", None
    return "ok", engine


def _check_verified(nautilus: str) -> bool:
    return nautilus in _verified_nautilus_versions()


def _check_stores(store_dir: Path) -> list[str]:
    return [
        f"{symbol}@{interval}"
        for symbol in BASKET
        for interval in GRID_INTERVALS
        if not _store_path(store_dir, symbol, interval).exists()
    ]


def _load_newest_record(path: Path) -> CycleRecord:
    record = from_json(path.read_text())
    validate_record(record)
    return record


def _check_journal(journal_dir: Path) -> str:
    from cli.engine.command import _journal_artifacts  # here, not at the top: cli.engine.command imports this module

    artifacts = _journal_artifacts(journal_dir, "*", "cycle-*.json")
    if not artifacts:
        return "none"
    newest = artifacts[-1][1]
    try:
        _load_newest_record(newest)
    except (OSError, EngineJournalError) as exc:
        return f"{newest}: {exc}"
    return "ok"


def run_preflight(state_dir: Path) -> PreflightResult:
    nautilus = _installed_nautilus_version()
    verified = _check_verified(nautilus)
    config, engine = _check_config(state_dir)
    if engine is None:
        stores_missing, journal = None, None
    else:
        stores_missing, journal = _check_stores(engine.store_dir), _check_journal(engine.journal_dir)
    ok = config == "ok" and verified and stores_missing == [] and journal in ("ok", "none")
    return PreflightResult(
        config=config,
        verified=verified,
        stores_missing=stores_missing,
        journal=journal,
        version=version("zcrypto"),
        nautilus=nautilus,
        ok=ok,
    )
