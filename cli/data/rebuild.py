"""`zcrypto data rebuild` (spec 00056 D3): dataset-aware re-freeze/refresh orchestrating the
existing, tested library code -- the builders all take an `out_root` argument, so sibling-minting
is an orchestration-level choice of output directory, never a library change (D1c: a revision mints
a sibling, never overwrites the live set)."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cli.backfill.backfill import backfill_basket
from cli.backfill.substrate15m import build_15m_substrate
from cli.data.errors import DataSyncError
from cli.derivatives.funding import build_funding_substrate
from cli.ohlc.dataset import read_parquet
from cli.snapshot import CANDIDATE_SYMBOLS, derive_universe
from cli.snapshot.fetch import fetch_public
from cli.snapshot.register import build_snapshot
from cli.universe.build import build_universe_file
from cli.universe.rules import DEFAULT_MIN_LEVERAGE, DEFAULT_MIN_MEDIAN_QUOTE_VOLUME, MANDATORY, finalize_universe
from cli.universe.volume import quote_volume_in_eur

_OHLC_INTERVALS = ["1440", "240", "60"]


@dataclass(frozen=True)
class RebuildContext:
    data_root: Path
    ohlcvt_source_dir: Path | None
    stamp: str  # UTC %Y%m%d, injected -- never computed inside the library, so tests pin it


def _require_source_dir(ctx: RebuildContext, set_name: str) -> Path:
    if ctx.ohlcvt_source_dir is None:
        raise DataSyncError(f"data rebuild: {set_name} needs ohlcvt_source_dir, none configured")
    return ctx.ohlcvt_source_dir


def _rebuild_ohlc_full(ctx: RebuildContext, out_root: Path) -> None:
    source_dir = _require_source_dir(ctx, "ohlc-full")
    backfill_basket(source_dir, list(CANDIDATE_SYMBOLS), _OHLC_INTERVALS, out_root, datetime.now(UTC).isoformat())


def _rebuild_ohlc_15m(ctx: RebuildContext, out_root: Path) -> None:
    source_dir = _require_source_dir(ctx, "ohlc-15m")
    build_15m_substrate(source_dir, list(CANDIDATE_SYMBOLS), out_root, fetched_at=datetime.now(UTC).isoformat())


def _refresh_funding(ctx: RebuildContext, out_root: Path) -> None:
    build_funding_substrate(out_root)


def _refresh_snapshots(ctx: RebuildContext, out_root: Path) -> None:
    """Refresh the venue reference-data snapshot via the canonical builder
    (`cli.snapshot.register.build_snapshot`), matching the live set's filename convention
    (`kraken-refdata-<UTC stamp>.json`) and payload shape (spec D3)."""
    fetched_at = datetime.now(UTC)
    snapshot = build_snapshot(fetch_public("AssetPairs"), fetch_public("Assets"), list(CANDIDATE_SYMBOLS), fetched_at.isoformat())
    (out_root / f"kraken-refdata-{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json").write_text(json.dumps(snapshot, sort_keys=True))


def _require_ohlc_full(ctx: RebuildContext) -> Path:
    ohlc_root = ctx.data_root / "ohlc-full"
    if not ohlc_root.exists():
        raise DataSyncError(f"data rebuild: universe needs the live ohlc-full/ set, not found at {ohlc_root}")
    return ohlc_root


def _refresh_universe(ctx: RebuildContext, out_root: Path) -> None:
    """Refresh the point-in-time universe file via the canonical builders (`derive_universe` +
    `finalize_universe` + `build_universe_file`), matching the live set's filename
    (`point-in-time-universe.json`) and payload shape -- including the `selected` key
    `zcrypto capture` reads (spec D3). Quote volumes are read from the LIVE `ohlc-full` set, not a
    freshly-minted sibling: a universe refresh reuses the currently-live OHLC, it does not repull it."""
    symbols = list(CANDIDATE_SYMBOLS)
    assetpairs_result = fetch_public("AssetPairs")
    assets_result = fetch_public("Assets")
    snapshot = build_snapshot(assetpairs_result, assets_result, symbols, datetime.now(UTC).isoformat())
    pairs = derive_universe(assetpairs_result, assets_result, symbols)

    ohlc_root = _require_ohlc_full(ctx)
    btc_eur = read_parquet(ohlc_root / "BTC" / "EUR" / "1440.parquet")
    volumes = {}
    for symbol in symbols:
        base, quote = symbol.split("/")
        daily = read_parquet(ohlc_root / base / quote / "1440.parquet")
        volumes[symbol] = quote_volume_in_eur(daily, fx_daily=None if quote == "EUR" else btc_eur)

    selection = finalize_universe(pairs, volumes)
    params = {
        "min_leverage": DEFAULT_MIN_LEVERAGE,
        "min_median_quote_volume": DEFAULT_MIN_MEDIAN_QUOTE_VOLUME,
        "median_quote_volume_window_days": 30,
        "mandatory": list(MANDATORY),
    }
    manifest_path = ohlc_root / "manifest.json"
    ohlc_dataset_hash = json.loads(manifest_path.read_text())["basket_sha256"] if manifest_path.exists() else ""
    provenance = {"snapshot_sha256": snapshot["raw_sha256"], "ohlc_dataset_hash": ohlc_dataset_hash}
    file = build_universe_file(selection, as_of=datetime.now(UTC).strftime("%Y-%m-%d"), params=params, provenance=provenance)
    (out_root / "point-in-time-universe.json").write_text(json.dumps(file, sort_keys=True))


REBUILDABLE: dict[str, Callable[[RebuildContext, Path], None]] = {
    "ohlc-full": _rebuild_ohlc_full,
    "ohlc-15m": _rebuild_ohlc_15m,
    "derivatives-funding": _refresh_funding,
    "snapshots": _refresh_snapshots,
    "universe": _refresh_universe,
}


def rebuild_sets(sets: Sequence[str], ctx: RebuildContext) -> list[Path]:
    """For each named set: mint the sibling dir data_root/f"{name}-{ctx.stamp}" (DataSyncError if it
    already exists or the name is unknown), call its builder with out_root=<sibling>, and return the
    minted dirs. NEVER writes into the live set dir -- the sibling is the whole contract (spec D1c/D3)."""
    minted = []
    for name in sets:
        builder = REBUILDABLE.get(name)
        if builder is None:
            raise DataSyncError(f"data rebuild: unknown set {name!r}")
        out_root = ctx.data_root / f"{name}-{ctx.stamp}"
        if out_root.exists():
            raise DataSyncError(f"data rebuild: sibling already exists: {out_root}")
        out_root.mkdir(parents=True)
        builder(ctx, out_root)
        minted.append(out_root)
    return minted
