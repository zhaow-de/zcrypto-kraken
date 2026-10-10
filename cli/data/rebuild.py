"""`zcrypto data rebuild`: dataset-aware re-freeze/refresh over the existing builders, which all take
an `out_root` -- so a revision mints a sibling and never overwrites the live set (spec 00056 D1c/D3)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

from cli.backfill.backfill import backfill_basket
from cli.backfill.errors import BackfillError
from cli.backfill.substrate15m import build_15m_substrate
from cli.costs.errors import CostModelError
from cli.costs.spread import SPREAD_CALIBRATION, effective_spread_bps
from cli.data import rolling
from cli.data.errors import DataSyncError
from cli.data.manifest import ManifestError
from cli.derivatives.errors import DerivativesError
from cli.derivatives.funding import build_funding_substrate
from cli.derivatives.oi import build_oi_substrate
from cli.ohlc.errors import OHLCError
from cli.snapshot import CANDIDATE_SYMBOLS, derive_universe
from cli.snapshot.errors import SnapshotError
from cli.snapshot.fetch import fetch_public
from cli.snapshot.register import build_snapshot
from cli.universe.build import build_universe_file
from cli.universe.errors import UniverseError
from cli.universe.rules import (
    DEFAULT_MAX_SPREAD_BPS,
    DEFAULT_MIN_LEVERAGE,
    DEFAULT_MIN_MEDIAN_QUOTE_VOLUME,
    MANDATORY,
    SPREAD_REFERENCE_NOTIONAL_EUR,
    _is_mandatory,
    finalize_universe,
)
from cli.universe.volume import quote_volume_in_eur

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


def _refresh_funding(ctx: RebuildContext, out_root: Path) -> None:
    build_funding_substrate(out_root)


def _refresh_oi(ctx: RebuildContext, out_root: Path) -> None:
    build_oi_substrate(out_root)


def _refresh_snapshots(ctx: RebuildContext, out_root: Path) -> None:
    """Mint a refdata snapshot matching the live set's payload shape (spec 00056 D3)."""
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
            f"data rebuild: universe needs the {rolling.ROLLING_SET} set reaching the present -- {symbol}'s newest "
            f"daily bar is {last_bar.date().isoformat()}, {staleness_days} days before the rebuild "
            f"stamp {as_of.date().isoformat()} (budget {UNIVERSE_MAX_OHLC_STALENESS_DAYS} days). A "
            f"trailing {_UNIVERSE_VOLUME_WINDOW_DAYS}-day median over that window measures past "
            f"liquidity, not current."
        )


def _refresh_universe(ctx: RebuildContext, out_root: Path) -> None:
    """Refresh the point-in-time universe file via the canonical builders, matching the live set's
    payload shape -- including the `selected` key `zcrypto capture` reads (spec 00056 D3)."""
    root = ctx.data_root / rolling.ROLLING_SET
    try:
        line = rolling.head(root)
        set_pairs = rolling.pairs(root)
        # A pair the head line records as closed on the owner's word has no data while the close runs, so it is
        # no candidate. The selection rule keeps a mandatory leg selected only among the candidates it is handed,
        # so a closed mandatory pair refuses the rebuild instead (spec 00125 D6).
        closed = sorted(rolling.closed_pairs(line, set_pairs))
        for pair in closed:
            base, quote = pair.split("/")
            if _is_mandatory(SimpleNamespace(base=base, quote=quote), MANDATORY):
                raise DataSyncError(
                    f"data rebuild: universe refuses the closed mandatory pair {pair} -- {line.relpath} records its "
                    "close on the owner's word, and every universe selects the mandatory EUR legs"
                )
        missing = [symbol for symbol in CANDIDATE_SYMBOLS if symbol not in set_pairs]
        if missing:
            # `escalate` compares the SELECTED set against band bounds and cannot see that the SOURCE was
            # narrower, so a missing leg would shrink the universe silently. Refuse here, naming every leg.
            raise DataSyncError(f"data rebuild: universe source is missing candidate leg(s): {', '.join(missing)} -- under {root}")
        symbols = [symbol for symbol in CANDIDATE_SYMBOLS if symbol not in closed]
        # Only the daily bars the volume median takes, ending at the head: a hole is permanent, so a read of the
        # whole history would refuse every later rebuild on one hole, where one inside these bars refuses this one.
        end = datetime.combine(line.day, time(), tzinfo=UTC)
        window = (end - timedelta(days=_UNIVERSE_VOLUME_WINDOW_DAYS - 1), end)
        frames = {
            pair: rolling.read_rolling(root, pair, 1440, line.day, window=window, accept_holes=False).frame
            for pair in dict.fromkeys(["BTC/EUR", *symbols])
        }
    except OSError as exc:
        raise DataSyncError(f"data rebuild: universe cannot read {root} -- {exc}") from exc
    btc_eur = frames["BTC/EUR"]
    dailies = {symbol: frames[symbol] for symbol in symbols}
    # Freshness BEFORE the medians: `quote_volume_in_eur` raises on a short frame, so a stale set that
    # is also short would report a row count and never diagnose the staleness.
    last_bars = {symbol: daily["ts"][-1] for symbol, daily in dailies.items() if daily.height}
    if last_bars:
        _require_fresh_ohlc(last_bars, ctx)

    assetpairs_result = fetch_public("AssetPairs")
    assets_result = fetch_public("Assets")
    snapshot = build_snapshot(assetpairs_result, assets_result, symbols, datetime.now(UTC).isoformat())
    pairs = derive_universe(assetpairs_result, assets_result, symbols)
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
    # Name the set this build READ and how fresh it was: a hash alone stops resolving once a directory
    # is retired. The published bar is the STALEST symbol's newest -- the value
    # `_require_fresh_ohlc` tests, and the only one every symbol's trailing window ends at or after.
    provenance = {
        "snapshot_sha256": snapshot["raw_sha256"],
        "ohlc_dataset_hash": line.sha256,
        "ohlc_dataset_dir": root.name,
        "ohlc_as_of": line.day.isoformat(),
        "ohlc_stalest_daily_bar": min(last_bars.values()).date().isoformat(),
        "ohlc_closed_pairs": closed,
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
    "derivatives-funding": _refresh_funding,
    "derivatives-oi": _refresh_oi,
    "snapshots": _refresh_snapshots,
    "universe": _refresh_universe,
}

# What a builder above raises on purpose, its message written for the operator.
BUILDER_REFUSALS: tuple[type[Exception], ...] = (
    BackfillError,
    CostModelError,
    DataSyncError,
    DerivativesError,
    ManifestError,
    OHLCError,
    rolling.RollingError,
    SnapshotError,
    UniverseError,
)


def rebuild_sets(sets: Sequence[str], ctx: RebuildContext) -> list[Path]:
    """NEVER writes into the live set dir -- the sibling is the whole contract (spec 00056 D1c/D3)."""
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
