from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

CONFIG_FILENAME = "zcrypto.toml"
CONFIG_TABLE = "zcrypto"
_DEFAULT_NFS_MOUNT = Path("/mnt/zhao-crypto")  # the NAS mount root; aligned across the workstation + ops


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


@dataclass(frozen=True)
class EngineConfig:
    """Operational tuning for the `zcrypto engine` shadow node. Each field overrides a built-in
    default via the [zcrypto.engine] table in zcrypto.toml."""

    store_dir: Path = Path("data/engine-store")
    journal_dir: Path = Path("data/engine-journal")
    shadow_nav_eur: float = 1000.0
    exec_enabled: bool = False
    # Whether the engine may SUBMIT. Independent of exec_enabled (which only says the transport is
    # connected) and, on its own, insufficient: arming also requires the arm file on the host, so
    # no single change can arm the live trade path.
    exec_armed: bool = False
    # The total-notional cap a probe plan may carry — the blast-radius bound.
    exec_max_plan_notional_eur: float = 100.0
    settle_delay_secs: int = 90
    # The weekly tracking-error trip's band, in bps of NAV. UNSET ships the trip disarmed: with no
    # band there is nothing to exceed, so no closed week can ever latch the kill switch. Set it only
    # once a live armed window has shown the engine's own weeks read the way the report says.
    tracking_band_bps: float | None = None


@dataclass(frozen=True)
class DataConfig:
    """The hot-cluster exchange (spec 00056): where this node pushes what it authors, and which
    sets it authors. The fetch source is derived from [zcrypto].nfs_mount_dir, not stored here."""

    push_dest: str | None = None  # rsync destination for push (ssh alias or path; rrsync-pinned)
    authored_sets: tuple[str, ...] = ()  # set names this node may push


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path | None
    nfs_mount_dir: Path  # the NAS mount root; the hot/ fetch source and custody sets derive from it
    fetch: FetchConfig
    engine: EngineConfig
    data: DataConfig


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

    if "exec_armed" in raw:
        value = raw["exec_armed"]
        if not isinstance(value, bool):
            raise ConfigError(f"[{CONFIG_TABLE}.engine].exec_armed in {config_path} must be a boolean")
        overrides["exec_armed"] = value

    if "exec_max_plan_notional_eur" in raw:
        value = raw["exec_max_plan_notional_eur"]
        # bool is a subclass of int — reject it explicitly. TOML admits `nan`/`inf` as real float
        # literals: nan defeats every "<= 0" comparison (always False) and inf disables the
        # blast-radius bound entirely (nothing ever compares as "exceeding" it) — both must be
        # refused explicitly via math.isfinite, not admitted as "positive".
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ConfigError(f"[{CONFIG_TABLE}.engine].exec_max_plan_notional_eur in {config_path} must be a positive number")
        overrides["exec_max_plan_notional_eur"] = float(value)

    if "tracking_band_bps" in raw:
        value = raw["tracking_band_bps"]
        # `exec_max_plan_notional_eur`'s arm exactly, and for the mirror-image reason: this number
        # is compared as `mean > band`, so a nan band answers False to every week ever measured and
        # disarms the trip while looking configured, and inf does the same in the open. A zero or
        # negative band is the opposite failure — it trips on the first week scored.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ConfigError(f"[{CONFIG_TABLE}.engine].tracking_band_bps in {config_path} must be a positive number")
        overrides["tracking_band_bps"] = float(value)

    if "settle_delay_secs" in raw:
        value = raw["settle_delay_secs"]
        # bool is a subclass of int — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"[{CONFIG_TABLE}.engine].settle_delay_secs in {config_path} must be a positive integer")
        overrides["settle_delay_secs"] = value

    return EngineConfig(**overrides)


def _build_data(table: dict, config_path: Path) -> DataConfig:
    raw = table.get("data", {})
    if not isinstance(raw, dict):
        raise ConfigError(f"[{CONFIG_TABLE}.data] in {config_path} must be a table")
    known = {f.name for f in fields(DataConfig)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"[{CONFIG_TABLE}.data] in {config_path} has unknown key(s): {', '.join(unknown)}")

    overrides: dict = {}

    if "push_dest" in raw:
        value = raw["push_dest"]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"[{CONFIG_TABLE}.data].push_dest in {config_path} must be a non-empty string")
        overrides["push_dest"] = value

    if "authored_sets" in raw:
        value = raw["authored_sets"]
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise ConfigError(f"[{CONFIG_TABLE}.data].authored_sets in {config_path} must be a list of non-empty strings")
        overrides["authored_sets"] = tuple(value)

    return DataConfig(**overrides)


def load_config(config_path: Path = Path(CONFIG_FILENAME)) -> AppConfig:
    if not config_path.exists():
        return AppConfig(
            data_dir=None, nfs_mount_dir=_DEFAULT_NFS_MOUNT, fetch=FetchConfig(), engine=EngineConfig(), data=DataConfig()
        )
    try:
        raw = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{config_path} is not valid TOML: {e}") from e
    table = raw.get(CONFIG_TABLE, {})
    if not isinstance(table, dict):
        raise ConfigError(f"[{CONFIG_TABLE}] in {config_path} must be a table")
    return AppConfig(
        data_dir=_read_path(table, "data_dir", config_path),
        nfs_mount_dir=_read_path(table, "nfs_mount_dir", config_path) or _DEFAULT_NFS_MOUNT,
        fetch=_build_fetch(table, config_path),
        engine=_build_engine(table, config_path),
        data=_build_data(table, config_path),
    )


def _resolve(flag_value: Path | None, config_value: Path | None, *, name: str, flag: str) -> Path:
    if flag_value is not None:
        return flag_value
    if config_value is not None:
        return config_value
    raise ConfigError(f"no {name} configured — set [{CONFIG_TABLE}].{name} in {CONFIG_FILENAME} or pass {flag} <path>.")


def resolve_data_dir(flag_value: Path | None, cfg: AppConfig) -> Path:
    return _resolve(flag_value, cfg.data_dir, name="data_dir", flag="--data-dir")


def resolve_ohlcvt_source_dir(flag_value: Path | None, cfg: AppConfig) -> Path:
    # Custody set — derived from the NAS mount root (a real default always exists).
    return flag_value if flag_value is not None else cfg.nfs_mount_dir / "kraken-ohlcvt-updates"


def resolve_hot_source(cfg: AppConfig) -> Path:
    # The hot-cluster fetch source — the hot/ subdir of the NAS mount root.
    return cfg.nfs_mount_dir / "hot"


def resolve_push_dest(cfg: AppConfig) -> str:
    if cfg.data.push_dest is not None:
        return cfg.data.push_dest
    raise ConfigError(f"no data.push_dest configured — set [{CONFIG_TABLE}.data].push_dest in {CONFIG_FILENAME}.")
