"""The tape's only independent witness -- and it expires (spec 00087 Verification).

The tape starts 2026-07-08 and `ohlc-full` ends 2026-03-31, so they do NOT overlap and there is no
canonical to check tape-bars against. Kraken's public REST OHLC does overlap, at 15m, for only about
7.5 days back (the endpoint returns ~720 candles). This control therefore proves the whole chain --
reconciled read -> ticks_to_bars -> day frame -- against an independent source, and it can only ever
prove it for a RECENT day. It skips (never passes, never fails) when the archive is absent, when the
REST call fails, or when the REST window no longer reaches a day the archive has healed: a network
outage must not read as a data defect.

The day is COMPUTED, never hardcoded: the newest archived day that is both `is_heal_complete` and
wholly inside the REST window. A pinned date would silently rot out of the window within a week.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from cli.config import load_config
from cli.ohlc.errors import OHLCError
from cli.ohlc.fetch import PAIR_KEYS, fetch_ohlc
from cli.tick.materialize import BASE_INTERVAL_MINUTES, build_day, is_heal_complete, segment_index

PAIR = "BTC/EUR"
PAIR_KEY = PAIR_KEYS[PAIR]

_MOUNT = load_config().nfs_mount_dir
PRIMARY_ROOT = _MOUNT / "capture-segments"
RECONCILED_ROOT = _MOUNT / "capture-reconciled"

# Kraken's REST rows are `[time, open, high, low, close, vwap, volume, count]`.
_TIME, _OPEN, _HIGH, _LOW, _CLOSE, _VWAP, _VOLUME, _COUNT = range(8)


def _rest_bars_for_day(rows: list[list], day: date) -> dict[datetime, list]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    stamped = ((datetime.fromtimestamp(int(row[_TIME]), UTC), row) for row in rows)
    return {ts: row for ts, row in stamped if start <= ts < end}


def _tick_size(row: list) -> Decimal:
    """The pair's published price precision, read off the payload rather than hardcoded per pair."""
    text = str(row[_CLOSE])
    return Decimal(1).scaleb(-len(text.partition(".")[2]))


def test_tape_bars_match_kraken_rest_ohlc() -> None:
    if not PRIMARY_ROOT.exists():
        pytest.skip(f"trade archive absent at {PRIMARY_ROOT} — data-bearing workstation only")

    index = segment_index(PRIMARY_ROOT, RECONCILED_ROOT)
    archived = sorted({hour.date() for hour in index.get(PAIR, {})})
    if not archived:
        pytest.skip(f"no {PAIR} trade segments under {PRIMARY_ROOT}")

    try:
        rows = fetch_ohlc(PAIR_KEY, BASE_INTERVAL_MINUTES)
    except OHLCError as exc:
        # A transport/API failure is a NETWORK outcome, not a data outcome. Failing here would
        # indict the tape for someone else's downtime, so it must skip and say which it was.
        pytest.skip(f"Kraken REST unreachable (network, not data): {exc}")
    if not rows:
        pytest.skip(f"Kraken REST returned no {PAIR_KEY} candles at {BASE_INTERVAL_MINUTES}m")

    stamps = sorted(datetime.fromtimestamp(int(row[_TIME]), UTC) for row in rows)
    # The newest row is the still-forming candle, so `day_end <= stamps[-1]` is exactly the condition
    # that every one of the day's candles is present AND closed.
    covered = [
        d
        for d in archived
        if datetime(d.year, d.month, d.day, tzinfo=UTC) >= stamps[0]
        and datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1) <= stamps[-1]
    ]
    day = next((d for d in reversed(covered) if is_heal_complete(index, PAIR, d)), None)
    if day is None:
        pytest.skip(
            f"no heal-complete {PAIR} day inside the REST window "
            f"(REST reaches {stamps[0].date()}..{stamps[-1].date()}; archive holds {archived[0]}..{archived[-1]})"
        )

    bars = build_day(index, PAIR, day)
    rest = _rest_bars_for_day(rows, day)
    mine = {row["ts"]: row for row in bars.iter_rows(named=True)}

    # Kraken emits a candle per traded interval; so do we. A quiet interval that only ONE side
    # represents would be a real divergence, so the bar sets are compared whole, not intersected.
    assert set(mine) == set(rest), (
        f"{PAIR} {day}: bar sets differ — only in tape: {sorted(set(mine) - set(rest))}, "
        f"only in REST: {sorted(set(rest) - set(mine))}"
    )
    assert mine, f"{PAIR} {day}: no bars on either side"

    for ts in sorted(mine):
        ours, theirs = mine[ts], rest[ts]
        where = f"{PAIR} {day} {ts:%H:%M}"
        # Kraken builds its OHLC from the same trade feed we captured, so the prices and the trade
        # count are EXACT -- no tolerance is defensible on any of them.
        assert ours["open"] == float(theirs[_OPEN]), f"{where}: open"
        assert ours["high"] == float(theirs[_HIGH]), f"{where}: high"
        assert ours["low"] == float(theirs[_LOW]), f"{where}: low"
        assert ours["close"] == float(theirs[_CLOSE]), f"{where}: close"
        assert ours["count"] == int(theirs[_COUNT]), f"{where}: trade count"
        # Volume is a float sum whose ORDER may differ; measured worst case is ~7e-16 relative.
        assert ours["volume"] == pytest.approx(float(theirs[_VOLUME]), rel=1e-9), f"{where}: volume"
        # vwap is NOT a 1e-9 comparison, and that is a measured property of the source rather than a
        # widened tolerance: Kraken publishes vwap TRUNCATED to the pair's price precision (measured
        # 2026-08-10 on BTC/EUR 2026-08-09 -- 96/96 bars match under ROUND_DOWN to 0.1, 53/96 under
        # round-half-even, so it truncates). The exact identity that holds is therefore the
        # half-open tick interval below; `slack` only absorbs float representation at the edge.
        tick = float(_tick_size(theirs))
        published = float(theirs[_VWAP])
        slack = tick * 1e-9
        assert published - slack <= ours["vwap"] < published + tick + slack, (
            f"{where}: vwap {ours['vwap']} outside Kraken's published-truncated tick [{published}, {published + tick})"
        )
