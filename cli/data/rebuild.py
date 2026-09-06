"""`zcrypto data rebuild`: dataset-aware re-freeze/refresh over the existing builders, which all take
an `out_root` -- so a revision mints a sibling and never overwrites the live set (spec 00056 D1c/D3)."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cli.backfill.backfill import backfill_basket
from cli.backfill.substrate15m import build_15m_substrate
from cli.costs.spread import SPREAD_CALIBRATION, effective_spread_bps
from cli.data.errors import DataSyncError
from cli.data.manifest import ManifestError, read_manifest
from cli.derivatives.funding import build_funding_substrate
from cli.derivatives.oi import build_oi_substrate
from cli.logging import get_logger
from cli.ohlc.dataset import read_parquet
from cli.ohlc.reach import reach_round
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

logger = get_logger("data.rebuild")

_OHLC_INTERVALS = ["1440", "240", "60"]
_UNIVERSE_VOLUME_WINDOW_DAYS = 30
# Days tolerated between a symbol's newest daily bar and the rebuild stamp: a chosen convention, far
# tighter than the 30-day window it protects, and deliberately unsatisfiable by the QUARTERLY OHLCVT
# dumps alone -- a universe rebuild needs a live-tailed source, not a fresh dump ingest (T0093).
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


def _rebuild_ohlc_reach(ctx: RebuildContext, out_root: Path) -> None:
    """Carry `ohlc-full` forward from Kraken's REST OHLC window (T0065), reading the LIVE canonical
    set and writing only into the minted sibling; series the window no longer reaches land
    `.detached` and are warned about, not refused."""
    report = reach_round(_require_ohlc_full(ctx), out_root)
    detached = report.detached
    if detached:
        logger.warning(
            "data rebuild: %d of %d reach series are DETACHED (no seam to the canonical tail): %s",
            len(detached),
            len(report.entries),
            ", ".join(f"{e.symbol}@{e.interval}" for e in detached),
        )


def _refresh_funding(ctx: RebuildContext, out_root: Path) -> None:
    build_funding_substrate(out_root)


def _refresh_oi(ctx: RebuildContext, out_root: Path) -> None:
    build_oi_substrate(out_root)


def _refresh_snapshots(ctx: RebuildContext, out_root: Path) -> None:
    """Mint a refdata snapshot via `build_snapshot`, matching the live set's filename convention
    (`kraken-refdata-<UTC stamp>.json`) and payload shape, so the sibling is drop-in (spec 00056 D3)."""
    fetched_at = datetime.now(UTC)
    snapshot = build_snapshot(fetch_public("AssetPairs"), fetch_public("Assets"), list(CANDIDATE_SYMBOLS), fetched_at.isoformat())
    (out_root / f"kraken-refdata-{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json").write_text(json.dumps(snapshot, sort_keys=True))


def _require_fresh_ohlc(last_bars: dict[str, datetime], ctx: RebuildContext) -> None:
    """Refuse a universe build from an OHLC set that does not reach the present: the volume criterion
    is a TRAILING 30-day median, describing current tradeability only if the newest bar is recent.
    Checked on the STALEST symbol -- a basket `max` would let one fresh symbol vouch
    for stale ones -- so a delisted symbol fails the rebuild, a corporate action wanting a human (T0025)."""
    as_of = datetime.strptime(ctx.stamp, "%Y%m%d").replace(tzinfo=UTC)
    symbol, last_bar = min(last_bars.items(), key=lambda kv: kv[1])
    staleness_days = (as_of - last_bar).days
    if staleness_days > UNIVERSE_MAX_OHLC_STALENESS_DAYS:
        raise DataSyncError(
            f"data rebuild: universe needs an ohlc-full set reaching the present -- {symbol}'s newest "
            f"daily bar is {last_bar.date().isoformat()}, {staleness_days} days before the rebuild "
            f"stamp {as_of.date().isoformat()} (budget {UNIVERSE_MAX_OHLC_STALENESS_DAYS} days). A "
            f"trailing {_UNIVERSE_VOLUME_WINDOW_DAYS}-day median over that window measures past "
            f"liquidity, not current."
        )


def _require_ohlc_full(ctx: RebuildContext) -> Path:
    ohlc_root = ctx.data_root / "ohlc-full"
    if not ohlc_root.exists():
        raise DataSyncError(f"data rebuild: universe needs the live ohlc-full/ set, not found at {ohlc_root}")
    return ohlc_root


_STAMPED_REACH = re.compile(r"ohlc-reach-\d{8}")


def resolve_ohlc_source(data_root: Path) -> Path:
    """The newest stamped `ohlc-reach-<%Y%m%d>` sibling, else canonical `ohlc-full`: newest-wins because
    publication is additive (`rsync --ignore-existing`), so a fixed name is never refreshable on the hub.
    Only exact stamped names are candidates, fixed-width digits sorting chronologically, so a stray sibling
    never outranks a date. Not for `_rebuild_ohlc_reach`, which anchors on `_require_ohlc_full`'s canonical."""
    stamped = sorted(
        (p for p in data_root.glob("ohlc-reach-*") if p.is_dir() and _STAMPED_REACH.fullmatch(p.name)),
        key=lambda p: p.name,
        reverse=True,
    )
    if stamped:
        return stamped[0]
    fallback = data_root / "ohlc-full"
    if not fallback.exists():
        raise DataSyncError(f"data rebuild: universe needs the live ohlc-full/ set, not found at {fallback}")
    return fallback


def _refresh_universe(ctx: RebuildContext, out_root: Path) -> None:
    """Refresh the point-in-time universe file via the canonical builders, matching the live set's
    filename (`point-in-time-universe.json`) and payload shape -- including the `selected` key
    `zcrypto capture` reads (spec 00056 D3). Volumes are read from `resolve_ohlc_source(...)`, so the
    refresh never repulls OHLC: it reads whichever set already reaches furthest."""
    symbols = list(CANDIDATE_SYMBOLS)
    assetpairs_result = fetch_public("AssetPairs")
    assets_result = fetch_public("Assets")
    snapshot = build_snapshot(assetpairs_result, assets_result, symbols, datetime.now(UTC).isoformat())
    pairs = derive_universe(assetpairs_result, assets_result, symbols)

    ohlc_root = resolve_ohlc_source(ctx.data_root)
    missing = [symbol for symbol in CANDIDATE_SYMBOLS if not (ohlc_root / Path(symbol) / "1440.parquet").exists()]
    if missing:
        # `escalate` compares the SELECTED set against band bounds and cannot see that the SOURCE was
        # narrower, so a missing leg would shrink the universe silently. Refuse here, naming the legs,
        # rather than an untyped FileNotFoundError from inside polars several frames later.
        raise DataSyncError(f"data rebuild: universe source is missing candidate leg(s): {', '.join(missing)} -- under {ohlc_root}")
    btc_eur = read_parquet(ohlc_root / "BTC" / "EUR" / "1440.parquet")
    dailies = {s: read_parquet(ohlc_root / s.split("/")[0] / s.split("/")[1] / "1440.parquet") for s in symbols}
    # Freshness BEFORE the medians: `quote_volume_in_eur` raises on a short frame, so a stale set that
    # is also short would report a row count and never diagnose the staleness.
    last_bars = {symbol: daily["ts"][-1] for symbol, daily in dailies.items() if daily.height}
    if last_bars:
        _require_fresh_ohlc(last_bars, ctx)
    volumes = {
        symbol: quote_volume_in_eur(
            daily,
            fx_daily=None if symbol.split("/")[1] == "EUR" else btc_eur,
            window=_UNIVERSE_VOLUME_WINDOW_DAYS,
        )
        for symbol, daily in dailies.items()
    }

    # Spread cap (T0024, spec 00067): priced from the committed calibration at the max-size
    # position the volume floor uses, keyed by FULL SYMBOL (spec 00085 D3) -- the calibration covers the
    # BTC-quoted legs, so membership alone decides. A symbol absent from the table is recorded
    # `spread_bps: None` by `finalize_universe`, never rejected.
    spreads = {
        symbol: round(effective_spread_bps(symbol, SPREAD_REFERENCE_NOTIONAL_EUR), 3)
        for symbol in symbols
        if symbol in SPREAD_CALIBRATION
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
        # T0014 / spec 00066: the spread model this provenance field cites.
        "source": "cli/costs/spread.py — mean effective spread at size",
        "unevaluated_count": sum(1 for e in selection.entries if e["spread_bps"] is None),
    }
    manifest_path = ohlc_root / "manifest.json"
    # Fail closed on a missing manifest: `backfill_basket` always writes one, so its
    # absence means a broken or half-written set, and an empty provenance hash reads as a value and
    # compares EQUAL across two unrelated broken builds -- a directory name is not an identity.
    if not manifest_path.exists():
        raise DataSyncError(
            f"data rebuild: universe needs {manifest_path} to record the OHLC set's identity -- "
            "absent, so the set is broken or half-written; refusing to write an artifact whose "
            "provenance hash would be empty"
        )
    # A manifest that exists but cannot be read means the same thing, that the set cannot identify
    # itself, so it takes the same typed failure rather than an untyped error from deep in the stack.
    try:
        # ONE accessor, no dataset name in this path: reach's identity is its continuous subset and
        # ohlc-full's is set-wide, and the manifest declares which -- choosing here would restore the
        # per-set knowledge the contract removed.
        ohlc_dataset_hash = read_manifest(manifest_path).identity_digest
    except ManifestError:
        # A legacy manifest still identifies itself the old way; degrading rather than refusing keeps
        # a hub-fetched tree usable before it has been converted.
        try:
            ohlc_dataset_hash = json.loads(manifest_path.read_text())["basket_sha256"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise DataSyncError(
                f"data rebuild: {manifest_path} is unreadable as a basket manifest ({exc!r}) -- "
                "refusing to write an artifact that cannot cite the set it was built from"
            ) from exc
    except (json.JSONDecodeError, KeyError) as exc:
        raise DataSyncError(
            f"data rebuild: {manifest_path} is unreadable as a basket manifest ({exc!r}) -- "
            "refusing to write an artifact that cannot cite the set it was built from"
        ) from exc
    # Name the set this build READ and how fresh it was: a hash alone stops resolving once a directory
    # is retired. The published bar is the STALEST symbol's newest -- the value
    # `_require_fresh_ohlc` tests, and the only one every symbol's trailing window ends at or after.
    provenance = {
        "snapshot_sha256": snapshot["raw_sha256"],
        "ohlc_dataset_hash": ohlc_dataset_hash,
        "ohlc_dataset_dir": ohlc_root.name,
        "ohlc_stalest_daily_bar": min(last_bars.values()).date().isoformat(),
    }
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
    "ohlc-reach": _rebuild_ohlc_reach,
    "derivatives-funding": _refresh_funding,
    "derivatives-oi": _refresh_oi,
    "snapshots": _refresh_snapshots,
    "universe": _refresh_universe,
}


def rebuild_sets(sets: Sequence[str], ctx: RebuildContext) -> list[Path]:
    """Mint `data_root/<name>-<stamp>` for each named set, run its builder with that as `out_root`, and
    return the minted dirs; DataSyncError on an unknown name or an existing sibling. NEVER writes into
    the live set dir -- the sibling is the whole contract (spec 00056 D1c/D3)."""
    minted = []
    for name in sets:
        builder = REBUILDABLE.get(name)
        if builder is None:
            raise DataSyncError(f"data rebuild: unknown set {name!r}")
        out_root = ctx.data_root / f"{name}-{ctx.stamp}"
        if out_root.exists():
            raise DataSyncError(
                f"data rebuild: sibling already exists: {out_root} -- either a completed sibling "
                "from earlier today, or the leavings of a run killed mid-build (a failed builder "
                "cleans up after itself, but a hard kill cannot); inspect the directory and "
                "remove it to retry"
            )
        out_root.mkdir(parents=True)
        try:
            builder(ctx, out_root)
        except BaseException:
            # Delete the sibling so a same-day retry is not blocked by the exists-guard forever: the
            # guard fired before `mkdir`, so the tree holds only what this run wrote, and every current
            # builder derives repeatable input -- one consuming unrepeatable input would need its own
            # protection. BaseException on purpose, so an operator's Ctrl-C cleans up like an error.
            shutil.rmtree(out_root)
            raise
        minted.append(out_root)
    return minted
