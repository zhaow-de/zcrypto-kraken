from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

CONFIG_FILENAME = "zcrypto.toml"
CONFIG_TABLE = "zcrypto"


class ConfigError(Exception):
    """zcrypto.toml is malformed, or a required setting cannot be resolved."""


@dataclass(frozen=True)
class FetchConfig:
    """Operational tuning for `zcrypto data` fetching/pipelines. Each field overrides
    a built-in default via the [zcrypto.fetch] table in zcrypto.toml."""

    fetch_concurrency: int = 8
    http_timeout_head_secs: int = 5
    http_timeout_get_secs: int = 60
    http_retry_attempts: int = 3
    fetch_progress_log_interval: int = 50
    backfill_right_edge_grace_days: int = 7
    rename_synth_warn_days: int = 7


@dataclass(frozen=True)
class EngineConfig:
    """Operational tuning for the `zcrypto engine` shadow node. Each field overrides a built-in
    default via the [zcrypto.engine] table in zcrypto.toml."""

    store_dir: Path = Path("data/engine-store")
    journal_dir: Path = Path("data/engine-journal")
    shadow_nav_eur: float = 1000.0
    exec_enabled: bool = False
    settle_delay_secs: int = 90


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path | None
    backup_dir: Path | None
    ohlcvt_source_dir: Path | None
    fetch: FetchConfig
    engine: EngineConfig


def _read_path(table: dict, key: str, config_path: Path) -> Path | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"[{CONFIG_TABLE}].{key} in {config_path} must be a non-empty string")
    return Path(value)


def _build_fetch(table: dict, config_path: Path) -> FetchConfig:
    raw = table.get("fetch", {})
    if not isinstance(raw, dict):
        raise ConfigError(f"[{CONFIG_TABLE}.fetch] in {config_path} must be a table")
    known = {f.name for f in fields(FetchConfig)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"[{CONFIG_TABLE}.fetch] in {config_path} has unknown key(s): {', '.join(unknown)}")
    overrides: dict[str, int] = {}
    for name in known & set(raw):
        value = raw[name]
        # bool is a subclass of int — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"[{CONFIG_TABLE}.fetch].{name} in {config_path} must be a positive integer")
        overrides[name] = value
    return FetchConfig(**overrides)


def _build_engine(table: dict, config_path: Path) -> EngineConfig:
    raw = table.get("engine", {})
    if not isinstance(raw, dict):
        raise ConfigError(f"[{CONFIG_TABLE}.engine] in {config_path} must be a table")
    known = {f.name for f in fields(EngineConfig)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"[{CONFIG_TABLE}.engine] in {config_path} has unknown key(s): {', '.join(unknown)}")

    overrides: dict = {}

    for name in ("store_dir", "journal_dir"):
        if name not in raw:
            continue
        value = raw[name]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"[{CONFIG_TABLE}.engine].{name} in {config_path} must be a non-empty string")
        overrides[name] = Path(value)

    if "shadow_nav_eur" in raw:
        value = raw["shadow_nav_eur"]
        # bool is a subclass of int — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ConfigError(f"[{CONFIG_TABLE}.engine].shadow_nav_eur in {config_path} must be a positive number")
        overrides["shadow_nav_eur"] = float(value)

    if "exec_enabled" in raw:
        value = raw["exec_enabled"]
        if not isinstance(value, bool):
            raise ConfigError(f"[{CONFIG_TABLE}.engine].exec_enabled in {config_path} must be a boolean")
        overrides["exec_enabled"] = value

    if "settle_delay_secs" in raw:
        value = raw["settle_delay_secs"]
        # bool is a subclass of int — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"[{CONFIG_TABLE}.engine].settle_delay_secs in {config_path} must be a positive integer")
        overrides["settle_delay_secs"] = value

    return EngineConfig(**overrides)


def load_config(config_path: Path = Path(CONFIG_FILENAME)) -> AppConfig:
    if not config_path.exists():
        return AppConfig(data_dir=None, backup_dir=None, ohlcvt_source_dir=None, fetch=FetchConfig(), engine=EngineConfig())
    try:
        raw = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{config_path} is not valid TOML: {e}") from e
    table = raw.get(CONFIG_TABLE, {})
    if not isinstance(table, dict):
        raise ConfigError(f"[{CONFIG_TABLE}] in {config_path} must be a table")
    return AppConfig(
        data_dir=_read_path(table, "data_dir", config_path),
        backup_dir=_read_path(table, "backup_dir", config_path),
        ohlcvt_source_dir=_read_path(table, "ohlcvt_source_dir", config_path),
        fetch=_build_fetch(table, config_path),
        engine=_build_engine(table, config_path),
    )


def _resolve(flag_value: Path | None, config_value: Path | None, *, name: str, flag: str) -> Path:
    if flag_value is not None:
        return flag_value
    if config_value is not None:
        return config_value
    raise ConfigError(f"no {name} configured — set [{CONFIG_TABLE}].{name} in {CONFIG_FILENAME} or pass {flag} <path>.")


def resolve_data_dir(flag_value: Path | None, cfg: AppConfig) -> Path:
    return _resolve(flag_value, cfg.data_dir, name="data_dir", flag="--data-dir")


def resolve_backup_dir(flag_value: Path | None, cfg: AppConfig) -> Path:
    return _resolve(flag_value, cfg.backup_dir, name="backup_dir", flag="--backup-dir")


def resolve_ohlcvt_source_dir(flag_value: Path | None, cfg: AppConfig) -> Path:
    return _resolve(flag_value, cfg.ohlcvt_source_dir, name="ohlcvt_source_dir", flag="--ohlcvt-source-dir")
