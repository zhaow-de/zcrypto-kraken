"""Tape bars checked against Kraken's public REST OHLC (spec 00087 Verification), the only source
that overlaps the tape now that `ohlc-full` has ended: REST reaches only ~720 candles back (~7.5
days at 15m), so the day under test is COMPUTED — the newest heal-complete day of the last
`REST_REACH_DAYS` whole days — and never a pinned date, which would rot out of the window within a
week. That bound is the CALENDAR's and not the answer's, so a heal-complete day inside the REST
window but older than it is skipped rather than tested, and whether Kraken reached the chosen day
is a `pytest.fail` below rather than a skip."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from cli.config import load_config
from cli.ohlc.fetch import PAIR_KEYS, fetch_ohlc
from cli.tick.materialize import BASE_INTERVAL_MINUTES, build_day, is_heal_complete, segment_index
from tests.skip_gates import nothing_found

PAIR = "BTC/EUR"
PAIR_KEY = PAIR_KEYS[PAIR]

# Kraken's REST answer is 720 candles, and `now - <that window>` is at most (today - 7) 12:00 at 15m
# whatever hour a run starts at -- so each of the REST_REACH_DAYS whole days before today is wholly
# inside a full-length window; `recent` spans those days and today, which `is_heal_complete` refuses
# at the live edge before any read. The bound is read off the CALENDAR and never off `stamps`, which
# is why the window check below is a statement about Kraken's answer rather than about the archive,
# and it is computed from the interval this file already imports so a change to it cannot leave the 6 behind.
REST_REACH_DAYS = 720 * BASE_INTERVAL_MINUTES // (60 * 24) - 1

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
    # Opt-in, not reachability-gated: a skip on an unreachable venue is an outage read as coverage, so
    # once the flag is set `fetch_ohlc`'s OHLCError is left to FAIL this test rather than skip it.
    if os.environ.get("ZCRYPTO_LIVE_VENUE_TESTS") != "1":
        pytest.skip("needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it")
    _primary_present = [PRIMARY_ROOT] if PRIMARY_ROOT.exists() else []
    if nothing_found(_primary_present):
        pytest.skip(f"trade archive absent at {PRIMARY_ROOT} — data-bearing workstation only")

    index = segment_index(PRIMARY_ROOT, RECONCILED_ROOT)
    archived = sorted({hour.date() for hour in index.get(PAIR, {})})
    if nothing_found(archived):
        pytest.skip(f"no {PAIR} trade segments under {PRIMARY_ROOT}")

    recent = [d for d in archived if d >= datetime.now(UTC).date() - timedelta(days=REST_REACH_DAYS)]
    day = next((d for d in reversed(recent) if is_heal_complete(index, PAIR, d)), None)
    if nothing_found([day] if day is not None else []):
        pytest.skip(f"no heal-complete {PAIR} day in the last {REST_REACH_DAYS} days under {PRIMARY_ROOT}")

    rows = fetch_ohlc(PAIR_KEY, BASE_INTERVAL_MINUTES)
    if not rows:
        pytest.fail(f"Kraken REST returned no {PAIR_KEY} candles at {BASE_INTERVAL_MINUTES}m")

    stamps = sorted(datetime.fromtimestamp(int(row[_TIME]), UTC) for row in rows)
    # A window shorter than the one day this test compares is a venue answer too short to mean
    # anything, whatever the archive holds. It belongs beside the `not rows` fail above: with the
    # opt-in set, a venue answer short of the expected one fails rather than skipping. The day is
    # already chosen off the calendar above, so an old archive has skipped there and the window check
    # below is a venue statement too; this one stays for the sharper diagnostic it prints.
    if stamps[-1] - stamps[0] < timedelta(days=1):
        pytest.fail(
            f"Kraken REST returned {PAIR_KEY} {BASE_INTERVAL_MINUTES}m candles spanning only "
            f"{stamps[0]} to {stamps[-1]}, less than the day this test compares"
        )
    # The newest row is the still-forming candle, so `day_end <= stamps[-1]` is exactly the condition
    # that every one of the day's candles is present AND closed.
    day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    if not (day_start >= stamps[0] and day_start + timedelta(days=1) <= stamps[-1]):
        pytest.fail(
            f"Kraken REST reaches {stamps[0].date()}..{stamps[-1].date()} and does not cover the newest "
            f"heal-complete {PAIR} day {day}"
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
        # round-half-even). `slack` below only absorbs float representation at the edge.
        tick = float(_tick_size(theirs))
        published = float(theirs[_VWAP])
        slack = tick * 1e-9
        assert published - slack <= ours["vwap"] < published + tick + slack, (
            f"{where}: vwap {ours['vwap']} outside Kraken's published-truncated tick [{published}, {published + tick})"
        )
