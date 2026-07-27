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
# Days the universe rebuild tolerates between a symbol's newest daily bar and the rebuild stamp.
# A chosen convention, not a derivation: daily bars lag ~a day by construction, and a week leaves
# operational slack while staying far tighter than the 30-day window it protects. NOTE this budget
# is deliberately unsatisfiable by the QUARTERLY OHLCVT dumps alone -- freshly ingesting a just-
# closed quarter still leaves the frontier weeks old -- so a universe rebuild needs a live-tailed
# source, not merely an up-to-date dump ingest (T0093).
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
    """Carry `ohlc-full` forward from Kraken's REST OHLC window (T0065).

    Reads the LIVE canonical set and writes only into the minted sibling, so the canonical stays
    immutable. Series whose REST window still overlaps the canonical tail land continuous; those it
    no longer reaches land `.detached` -- kept because REST bars expire as the window recedes. See
    `cli/ohlc/reach.py` for why both outcomes are written rather than one being refused.
    """
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
    """Refresh the venue reference-data snapshot via the canonical builder
    (`cli.snapshot.register.build_snapshot`), matching the live set's filename convention
    (`kraken-refdata-<UTC stamp>.json`) and payload shape (spec D3)."""
    fetched_at = datetime.now(UTC)
    snapshot = build_snapshot(fetch_public("AssetPairs"), fetch_public("Assets"), list(CANDIDATE_SYMBOLS), fetched_at.isoformat())
    (out_root / f"kraken-refdata-{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json").write_text(json.dumps(snapshot, sort_keys=True))


def _require_fresh_ohlc(last_bars: dict[str, datetime], ctx: RebuildContext) -> None:
    """Refuse to build a universe from an OHLC set that does not reach the present (T0093).

    The volume criterion is a TRAILING 30-day median, so it only describes current tradeability if
    the dataset's newest bar is recent. Left unguarded, this path computes a "30-day median" over a
    months-old window and drops names for what reads as a liquidity move (measured 2026-07-22:
    AVAX/EUR at 132,274.82 vs the 150,000 floor, selecting 11 -- and `escalate` stays False because
    11 >= MIN_NAMES, so nothing flags it).

    Checked PER SYMBOL, on the stalest, rather than on the basket's newest bar: each symbol's median
    is computed from its own frame, so a basket-wide `max` would let one fresh symbol vouch for
    stale ones. That is not hypothetical -- the live-trades->bars materializer planned in T0065's
    REACH round feeds EUR pairs only (capture is EUR-quoted; T0092), which would leave the
    BTC-quoted legs behind while a `max` check signed off. The cost of this strictness: a
    legitimately delisted symbol fails the whole rebuild. That is the intended direction -- a
    delisting is a corporate action wanting human attention (T0025), not something to select around
    on a stale window -- and the error names the offender.
    """
    as_of = datetime.strptime(ctx.stamp, "%Y%m%d").replace(tzinfo=UTC)
    symbol, last_bar = min(last_bars.items(), key=lambda kv: kv[1])
    staleness_days = (as_of - last_bar).days
    if staleness_days > UNIVERSE_MAX_OHLC_STALENESS_DAYS:
        raise DataSyncError(
            f"data rebuild: universe needs an ohlc-full set reaching the present -- {symbol}'s newest "
            f"daily bar is {last_bar.date().isoformat()}, {staleness_days} days before the rebuild "
            f"stamp {as_of.date().isoformat()} (budget {UNIVERSE_MAX_OHLC_STALENESS_DAYS} days). A "
            # T0093: the staleness budget and this message's wording.
            f"trailing {_UNIVERSE_VOLUME_WINDOW_DAYS}-day median over that window measures past "
            f"liquidity, not current."
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
    dailies = {s: read_parquet(ohlc_root / s.split("/")[0] / s.split("/")[1] / "1440.parquet") for s in symbols}
    # Freshness BEFORE the medians: `quote_volume_in_eur` raises on a short frame, so a stale set
    # that is also short would report a row count and never diagnose the staleness (T0093 review).
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
        # T0014 / spec 00066: the spread model this provenance field cites.
        "source": "cli/costs/spread.py — mean effective spread at size",
        "unevaluated_count": sum(1 for e in selection.entries if e["spread_bps"] is None),
    }
    manifest_path = ohlc_root / "manifest.json"
    # Fail closed on a missing manifest (T0094). `backfill_basket` always writes one, so its absence
    # means a broken or half-written set -- exactly when emitting a provenance hash of `""` is most
    # harmful: an empty string reads as a value and compares EQUAL across two entirely different
    # broken builds, so two artifacts would agree on provenance while sharing none. A directory name
    # is not an identity (T0093); the hash is what makes the citation resolvable.
    if not manifest_path.exists():
        raise DataSyncError(
            f"data rebuild: universe needs {manifest_path} to record the OHLC set's identity -- "
            # T0094: why an absent manifest is a hard refusal rather than a warning.
            "absent, so the set is broken or half-written; refusing to write an artifact whose "
            "provenance hash would be empty"
        )
    # A manifest that exists but cannot be read is the same defect wearing a different costume, so
    # it gets the same typed failure rather than an untyped KeyError/JSONDecodeError from deep in
    # the call stack (review finding): both mean "this set cannot identify itself".
    try:
        ohlc_dataset_hash = json.loads(manifest_path.read_text())["basket_sha256"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise DataSyncError(
            f"data rebuild: {manifest_path} is unreadable as a basket manifest ({exc!r}) -- "
            # T0094: same defect as the absent-manifest branch above, different costume.
            "refusing to write an artifact that cannot cite the set it was built from"
        ) from exc
    # Name the set this build actually READ, and how fresh it was (T0093). A hash alone is not a
    # citation: the 2026-07-07 artifact cited `data/ohlc`'s hash, that directory was later retired,
    # and the reference became unresolvable -- with nothing in the file saying which window the
    # volumes covered.
    #
    # The published bar is the STALEST symbol's newest bar -- the value `_require_fresh_ohlc` tests,
    # and the only one that supports a statement about the basket: every symbol's trailing window
    # ends at or after it. The basket's `max` would support no such inference (one fresh symbol says
    # nothing about the other eleven), which is the same reason the guard rejects `max`.
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
