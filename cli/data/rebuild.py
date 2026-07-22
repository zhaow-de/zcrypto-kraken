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
from cli.costs.spread import SPREAD_CALIBRATION, effective_spread_bps
from cli.data.errors import DataSyncError
from cli.derivatives.funding import build_funding_substrate
from cli.ohlc.dataset import read_parquet
from cli.snapshot import CANDIDATE_SYMBOLS, derive_universe
from cli.snapshot.fetch import fetch_public
from cli.snapshot.register import build_snapshot
from cli.universe.build import build_universe_file
from cli.universe.rules import (
    DEFAULT_MAX_SPREAD_BPS,
    DEFAULT_MIN_LEVERAGE,
    DEFAULT_MIN_MEDIAN_QUOTE_VOLUME,
    MANDATORY,
    SPREAD_REFERENCE_NOTIONAL_EUR,
    finalize_universe,
)
from cli.universe.volume import quote_volume_in_eur

_OHLC_INTERVALS = ["1440", "240", "60"]
_UNIVERSE_VOLUME_WINDOW_DAYS = 30
# Days the universe rebuild tolerates between the OHLC set's newest daily bar and the rebuild
# stamp. Daily bars lag by a day or so by construction, and a rebuild need not run the same day
# the dumps land, so the budget is a week -- generous for operational slack, far tighter than
# the 30-day window it protects, and nowhere near the 3.5-month gap that motivated it (T0093).
UNIVERSE_MAX_OHLC_STALENESS_DAYS = 7


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


def _require_fresh_ohlc(frontier: datetime, ctx: RebuildContext) -> None:
    """Refuse to build a universe from an OHLC set that does not reach the present (T0093).

    The volume criterion is a TRAILING 30-day median, so it only describes current tradeability if
    the dataset's newest bar is recent. `ohlc-full` is reconstructed from the OHLCVT dumps and stops
    where they stop; the v0 REST set it superseded in iter-103 was live-fetched, and the
    supersession was verified bit-identical on the OVERLAP -- not in the recency direction. Left
    unguarded, this path computes a "30-day median" over a months-old window and drops names for
    what reads as a liquidity move (measured 2026-07-22: AVAX/EUR at 132,274.82 vs the 150,000
    floor, selecting 11 -- and `escalate` stays False because 11 >= MIN_NAMES, so nothing flags it).
    """
    as_of = datetime.strptime(ctx.stamp, "%Y%m%d").replace(tzinfo=UTC)
    staleness_days = (as_of - frontier).days
    if staleness_days > UNIVERSE_MAX_OHLC_STALENESS_DAYS:
        raise DataSyncError(
            f"data rebuild: universe needs an ohlc-full set reaching the present -- its newest daily "
            f"bar is {frontier.date().isoformat()}, {staleness_days} days before the rebuild stamp "
            f"{as_of.date().isoformat()} (budget {UNIVERSE_MAX_OHLC_STALENESS_DAYS} days). A trailing "
            f"{_UNIVERSE_VOLUME_WINDOW_DAYS}-day median over that window measures past liquidity, not "
            f"current (T0093)."
        )


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
    frontier = None  # the dataset's newest daily bar across the basket -- see _require_fresh_ohlc
    for symbol in symbols:
        base, quote = symbol.split("/")
        daily = read_parquet(ohlc_root / base / quote / "1440.parquet")
        if daily.height:
            last_ts = daily["ts"][-1]
            frontier = last_ts if frontier is None else max(frontier, last_ts)
        volumes[symbol] = quote_volume_in_eur(daily, fx_daily=None if quote == "EUR" else btc_eur)
    if frontier is not None:
        _require_fresh_ohlc(frontier, ctx)

    # Spread cap (T0024, spec 00067): priced from the committed calibration at the same max-size
    # position the volume floor uses. The map covers EUR-quoted pairs with a calibrated base;
    # everything else (today: the BTC-quoted legs, which have no L2 capture) is absent by
    # construction -- finalize_universe records them `spread_bps: None`
    # and does NOT reject them (absence of evidence is not evidence of a wide spread; T0092).
    spreads = {
        symbol: round(effective_spread_bps(symbol.split("/")[0], SPREAD_REFERENCE_NOTIONAL_EUR), 3)
        for symbol in symbols
        if symbol.split("/")[1] == "EUR" and symbol.split("/")[0] in SPREAD_CALIBRATION
    }
    selection = finalize_universe(pairs, volumes, spreads=spreads, max_spread_bps=DEFAULT_MAX_SPREAD_BPS)
    params = {
        "min_leverage": DEFAULT_MIN_LEVERAGE,
        "min_median_quote_volume": DEFAULT_MIN_MEDIAN_QUOTE_VOLUME,
        "median_quote_volume_window_days": _UNIVERSE_VOLUME_WINDOW_DAYS,
        "mandatory": list(MANDATORY),
    }
    spread_cap = {
        "max_spread_bps": DEFAULT_MAX_SPREAD_BPS,
        "reference_notional_eur": SPREAD_REFERENCE_NOTIONAL_EUR,
        "source": "cli/costs/spread.py (T0014, spec 00066) — mean effective spread at size",
        "unevaluated_count": sum(1 for e in selection.entries if e["spread_bps"] is None),
    }
    manifest_path = ohlc_root / "manifest.json"
    ohlc_dataset_hash = json.loads(manifest_path.read_text())["basket_sha256"] if manifest_path.exists() else ""
    provenance = {"snapshot_sha256": snapshot["raw_sha256"], "ohlc_dataset_hash": ohlc_dataset_hash}
    file = build_universe_file(
        selection,
        as_of=datetime.now(UTC).strftime("%Y-%m-%d"),
        params=params,
        provenance=provenance,
        spread_cap=spread_cap,
    )
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
        try:
            builder(ctx, out_root)
        except Exception:
            # A builder that raises mid-run must not leave an empty sibling behind: the per-day stamp
            # would then make a same-day retry trip the "already exists" guard forever. Clean up the
            # dir we just minted (only when still empty -- never delete builder output) and re-raise.
            if not any(out_root.iterdir()):
                out_root.rmdir()
            raise
        minted.append(out_root)
    return minted
