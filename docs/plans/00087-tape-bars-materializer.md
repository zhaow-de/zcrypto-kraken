# Tape-Bars Materializer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `tape-bars` — a 15m bar dataset built from the captured trade tape, published as daily finals once heal-complete, with 60/240/1440 derived exactly from the base.

**Architecture:** `cli/tick/` gains `materialize.py` (build → publish → watermarked sweep) and `command.py` (`zcrypto tick`), reusing the already-proven `ticks_to_bars` and the `cli/archive/mint.py` atomic-write pattern. Input is the healed archive via `canonical_segments(..., kind="trades")`; output is `<pair>/<YYYY>/<MM>/<DD>.parquet` + `.sha256` sidecars.

**Tech Stack:** Python 3.14 / polars / Typer / pytest, `uv` throughout.

## Global Constraints

- Spec: `docs/specs/00087-tape-bars-materializer-design.md`. Decision numbers (D1…D6) refer to it.
- **Heal-completeness is MEASURED by `cli.trades.gaps.detect`, never inferred from the clock** (D3). `TAPE_SETTLE = timedelta(hours=26)` past day end survives only as a cheap pre-filter and is no longer load-bearing.
- The healer's settle rule is `_SETTLE` in **`cli/trades/backfill.py`** — a module-local constant it does NOT import from `cli/archive/settle.py`. Cite the one the healer actually reads.
- **`RESCAN_DAYS = 3`** — the trailing window is measured in CALENDAR days back from the newest settled day (the code subtracts a timedelta), so for a pair with whole quiet days it spans fewer settled days than the number suggests.
- **Base grid is 15 minutes.** 60/240/1440 are derived, never materialized.
- **Reconciled-first always**: `canonical_segments(primary_root, reconciled_root, kind="trades")`. A bare glob over `capture-segments/` is forbidden — it double-counts pre-2026-07-16 hours.
- **Column rename is mandatory**: the archive's `TRADE_SCHEMA` uses `qty`; `ticks_to_bars` consumes `volume`. Rename before aggregating or every bar's volume/vwap is wrong.
- Bar columns are `ticks_to_bars`' own order: `[ts, open, high, low, close, volume, count, vwap]`.
- **Empty 15m windows emit no row** (measured canonical convention; `ticks_to_bars` already does this). Never gap-fill.
- Frames: `ts` is `Datetime("us", "UTC")`. Errors live in `cli/tick/errors.py` (`TickError`).
- **Never write into `data/ohlc-full`** or any frozen canonical.
- Commits: Conventional Commits, `Co-Authored-By: <the ACTUAL authoring model> <noreply@anthropic.com>` last line. **Review floor is Fable for every commit** — this reads the unbackfillable capture archive.
- Commit gate `uv run pre-commit run -a` until clean; stage by explicit path, never `git add -A`.
- Data-gated tests **skip with a reason**, never pass vacuously.

---

### Task 1: `build_day` — one day of tape into 15m bars

**Files:**

- Create: `cli/tick/materialize.py`
- Test: `tests/test_tick_materialize.py`

**Interfaces:**

- Produces: `BASE_INTERVAL_MINUTES = 15`; `SegmentIndex`; `segment_index(primary_root: Path, reconciled_root: Path) -> SegmentIndex` — `reconciled_root` is REQUIRED (D4), an empty directory is legal and omission is not expressible; `build_day(index: SegmentIndex, pair: str, day: date) -> pl.DataFrame` returning the `_BAR_SCHEMA` frame for that UTC day; raises `TickError` only when the day has no segments at all (completeness is the heal gate's business, not hour counting).
- Consumes: `cli.archive.reader.canonical_segments`, `cli.tick.aggregate.ticks_to_bars`, `cli.tick.errors.TickError`.

- [ ] **Step 1: Write the failing tests** — `tests/test_tick_materialize.py`

```python
"""The tape-bars day builder (spec 00087 D1/D4)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.tick.errors import TickError
from cli.tick.materialize import build_day, segment_index


def _seg(root: Path, pair: str, hour: datetime, rows: list[tuple[float, float, int]]) -> None:
    """Write one canonical trades segment.

    The canonical layout is <root>/<BASE>/<QUOTE>/<kind>/<Y>/<m>/<d>/<H>.parquet -- the pair spans
    TWO path levels. `canonical_segments` globs `*/*/{kind}/*/*/*/*.parquet` and reads the pair from
    parts[-7]/parts[-6], so a flattened `BTCEUR/` tree is INVISIBLE to it and every positive test
    would fail against a correct implementation.
    """
    d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
    d.mkdir(parents=True, exist_ok=True)
    frame = pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=s) for _, _, s in rows],
            "symbol": [pair] * len(rows),
            "side": ["buy"] * len(rows),
            "price": [p for p, _, _ in rows],
            "qty": [q for _, q, _ in rows],
            "ord_type": ["limit"] * len(rows),
            "trade_id": list(range(len(rows))),
        },
        schema=TRADE_SCHEMA,
    )
    frame.write_parquet(d / f"{hour:%H}.parquet")


def _full_day(root: Path, pair: str, day: date, *, per_hour=((10.0, 2.0, 5),)) -> None:
    for h in range(24):
        _seg(root, pair, datetime(day.year, day.month, day.day, h, tzinfo=UTC), list(per_hour))


def test_a_full_day_yields_one_bar_per_traded_window(tmp_path):
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 1))
    bars = build_day(segment_index(tmp_path, tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume", "count", "vwap"]
    # One trade per hour at :05 -> exactly one 15m bar per hour, not 96: empty windows emit NO row.
    assert bars.height == 24
    assert bars["ts"][0] == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)


def test_volume_comes_from_qty_not_a_missing_column(tmp_path):
    """The archive's TRADE_SCHEMA says `qty`; ticks_to_bars consumes `volume`. Without the rename
    the aggregation raises or produces null volume -- and a null vwap silently follows."""
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 1), per_hour=((10.0, 3.0, 5),))
    bars = build_day(segment_index(tmp_path, tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))
    assert bars["volume"].sum() == pytest.approx(72.0)  # 24 hours x 3.0
    assert bars["vwap"].null_count() == 0
    assert bars["vwap"][0] == pytest.approx(10.0)


def test_the_reconciled_overlay_wins_over_the_primary(tmp_path):
    """D4: reconciled-first. The healed hour must be the one that reaches the bars."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _full_day(primary, "BTC/EUR", date(2026, 8, 1), per_hour=((10.0, 1.0, 5),))
    _seg(overlay, "BTC/EUR", datetime(2026, 8, 1, 3, tzinfo=UTC), [(99.0, 1.0, 5)])
    bars = build_day(segment_index(primary, overlay), "BTC/EUR", date(2026, 8, 1))
    hour3 = bars.filter(pl.col("ts") == datetime(2026, 8, 1, 3, 0, tzinfo=UTC))
    assert hour3["close"][0] == pytest.approx(99.0)


def test_a_day_with_no_segments_is_refused(tmp_path):
    """Unreachable through the sweep (the calendar only lists days WITH segments) but reachable by
    direct callers such as the REST control -- so the refusal is pinned here, or its probe has
    nothing to kill."""
    (tmp_path / "data").mkdir()
    with pytest.raises(TickError, match="no trade segments"):
        build_day(segment_index(tmp_path / "data", tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))


def test_only_the_named_day_is_included(tmp_path):
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 1))
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 2))
    bars = build_day(segment_index(tmp_path, tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))
    assert bars["ts"].min() >= datetime(2026, 8, 1, tzinfo=UTC)
    assert bars["ts"].max() < datetime(2026, 8, 2, tzinfo=UTC)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_tick_materialize.py -q`
Expected: FAIL — `ModuleNotFoundError: cli.tick.materialize`.

- [ ] **Step 3: Implement `build_day`**

```python
"""Materialize 15m bars from the captured trade tape (spec 00087).

The tape is the only fine-cadence source whose reach does not expire: REST's window recedes and the
OHLCVT dumps are quarterly, while captured trades accrue. This module turns one healed UTC day of
that tape into the 15m bars that `tape-bars` publishes as a daily final.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments
from cli.tick.aggregate import ticks_to_bars
from cli.tick.errors import TickError

BASE_INTERVAL_MINUTES = 15


SegmentIndex = dict[str, dict[datetime, Path]]


def segment_index(primary_root: Path, reconciled_root: Path) -> SegmentIndex:
    """`{pair: {hour: path}}` for the whole healed trade archive, walked ONCE.

    `canonical_segments` globs the entire archive, so calling it per pair or per day is
    O(pairs x days x archive) on a tree that grows forever under an hourly sweep. Every consumer
    below takes this index instead of the roots.
    """
    index: SegmentIndex = {}
    for pair, hour, path in canonical_segments(primary_root, reconciled_root, kind="trades"):
        index.setdefault(pair, {})[hour] = path
    return index


def build_day(index: SegmentIndex, pair: str, day: date) -> pl.DataFrame:
    """The healed tape for `pair` on UTC `day`, aggregated to 15m bars.

    Reads the pre-built index (reconciled-first by construction). Aggregates whatever hours the day
    HAS: hour-file presence is not a completeness signal, because a quiet hour writes no final.
    Completeness is `is_heal_complete`'s measured trade_id contiguity (D3/D4).
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    hours = index.get(pair, {})
    present = {hour: path for hour, path in hours.items() if start <= hour < end}
    if not present:
        raise TickError(f"tape-bars: {pair} {day.isoformat()} has no trade segments at all")

    # Deliberately NO 24-hour completeness check. The capture writer commits no final for an hour
    # with no events, and zero-print trades hours are production-measured (settle.py records
    # LINK/EUR: 8 prints in hour 01, 9 in hour 04, zero between), so an absent hour means "quiet",
    # not "missing". Requiring 24 would make every day with a quiet hour permanently unpublishable.
    # Completeness is trade_id contiguity -- is_heal_complete -- which tells the two apart.
    frames = [pl.read_parquet(present[hour]) for hour in sorted(present)]
    ticks = pl.concat(frames).rename({"qty": "volume"}).select("ts", "price", "volume")
    return ticks_to_bars(ticks, interval_minutes=BASE_INTERVAL_MINUTES)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_tick_materialize.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/tick/materialize.py tests/test_tick_materialize.py
git commit -m "feat(tick): build one healed tape day into 15m bars"
```

---

### Task 2: `derive_bars` — the coarser grids, exactly

**Files:**

- Modify: `cli/tick/materialize.py`
- Test: `tests/test_tick_derive.py`

**Interfaces:**

- Produces: `derive_bars(bars: pl.DataFrame, *, interval_minutes: int) -> pl.DataFrame` — same `_BAR_SCHEMA` columns, coarser grid.
- Consumes: `build_day` (Task 1) in tests only.

- [ ] **Step 1: Write the failing tests** — `tests/test_tick_derive.py`

```python
"""Deriving 60/240/1440 from the 15m base is EXACT, not approximate (spec 00087 D1)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.tick.aggregate import ticks_to_bars
from cli.tick.materialize import build_day, derive_bars, segment_index


def _tape(tmp_path: Path, pair: str, day: date) -> Path:
    """A day of varied trades -- varied so an averaged vwap and a weighted one differ."""
    root = tmp_path / "p"
    for h in range(24):
        hour = datetime(day.year, day.month, day.day, h, tzinfo=UTC)
        d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
        d.mkdir(parents=True, exist_ok=True)
        n = 4 + (h % 5)
        pl.DataFrame(
            {
                "ts": [hour + timedelta(minutes=3 * i) for i in range(n)],
                "symbol": [pair] * n,
                "side": ["buy"] * n,
                "price": [100.0 + h + i for i in range(n)],
                "qty": [1.0 + 3.0 * ((h + i) % 4) for i in range(n)],  # lopsided on purpose
                "ord_type": ["limit"] * n,
                "trade_id": [h * 100 + i for i in range(n)],
            },
            schema=TRADE_SCHEMA,
        ).write_parquet(d / f"{hour:%H}.parquet")
    return root


@pytest.mark.parametrize("interval", [60, 240, 1440])
def test_derived_equals_direct_aggregation(tmp_path, interval):
    """THE property D1 claims. Derived-from-15m must equal ticks_to_bars run at that interval on the
    same ticks -- every column, not just the ones that trivially telescope."""
    root = _tape(tmp_path, "BTC/EUR", date(2026, 8, 1))
    base = build_day(segment_index(root, root.parent / "r"), "BTC/EUR", date(2026, 8, 1))
    derived = derive_bars(base, interval_minutes=interval)

    ticks = pl.concat(
        pl.read_parquet(p) for p in sorted((root / "BTC" / "EUR" / "trades").rglob("*.parquet"))
    ).rename({"qty": "volume"}).select("ts", "price", "volume")
    direct = ticks_to_bars(ticks, interval_minutes=interval)

    assert derived.height == direct.height
    for col in ("ts", "open", "high", "low", "close", "count"):
        assert derived[col].to_list() == direct[col].to_list(), col
    for col in ("volume", "vwap"):
        assert derived[col].to_list() == pytest.approx(direct[col].to_list()), col


def test_an_averaged_vwap_would_be_wrong(tmp_path):
    """Guards the formula, not just the result: on lopsided volume the weighted vwap differs from a
    plain mean of sub-bar vwaps, so a naive implementation cannot pass the test above by accident."""
    root = _tape(tmp_path, "BTC/EUR", date(2026, 8, 1))
    base = build_day(segment_index(root, root.parent / "r"), "BTC/EUR", date(2026, 8, 1))
    derived = derive_bars(base, interval_minutes=60)
    naive = base.group_by_dynamic("ts", every="60m", closed="left").agg(pl.col("vwap").mean())
    assert derived["vwap"].to_list() != pytest.approx(naive["vwap"].to_list())


def test_a_coarse_window_exists_iff_a_sub_bar_does(tmp_path):
    """Sparse input stays sparse: no gap-filling, and a coarse bar is never invented."""
    root = _tape(tmp_path, "BTC/EUR", date(2026, 8, 1))
    base = build_day(segment_index(root, root.parent / "r"), "BTC/EUR", date(2026, 8, 1)).filter(
        pl.col("ts") >= datetime(2026, 8, 1, 12, tzinfo=UTC)
    )
    derived = derive_bars(base, interval_minutes=60)
    assert derived["ts"].min() >= datetime(2026, 8, 1, 12, tzinfo=UTC)
    assert derived.height == 12
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_tick_derive.py -q`
Expected: FAIL — `ImportError: cannot import name 'derive_bars'`.

- [ ] **Step 3: Implement `derive_bars`** (append to `cli/tick/materialize.py`)

```python
def derive_bars(bars: pl.DataFrame, *, interval_minutes: int) -> pl.DataFrame:
    """Aggregate 15m base bars up to `interval_minutes` -- exactly, not approximately.

    `ticks_to_bars` computes a TRUE tick-weighted vwap, so `Σ(vwap_i · volume_i)` over sub-bars
    telescopes to `Σ(price · volume)` over the whole window and the coarse vwap re-derives as
    `Σ(vwap_i·vol_i) / Σ(vol_i)`. A plain mean of sub-bar vwaps is the tempting form and is WRONG on
    any window whose volume is not uniform. Empty windows stay absent: a coarse bar exists iff at
    least one sub-bar does.
    """
    if bars.height == 0:
        return bars
    return (
        bars.sort("ts")
        .group_by_dynamic("ts", every=f"{interval_minutes}m", closed="left")
        .agg(
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.col("count").sum(),
            (pl.col("vwap") * pl.col("volume")).sum().alias("_pv_sum"),
        )
        .with_columns((pl.col("_pv_sum") / pl.col("volume")).alias("vwap"))
        .select("ts", "open", "high", "low", "close", "volume", "count", "vwap")
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_tick_derive.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/tick/materialize.py tests/test_tick_derive.py
git commit -m "feat(tick): derive 60/240/1440 from the 15m base, exactly"
```

---

### Task 3: Publish + settle + watermarked sweep

**Files:**

- Modify: `cli/tick/materialize.py`
- Test: `tests/test_tick_sweep.py`

**Interfaces:**

- Produces: `TAPE_SETTLE`, `RESCAN_DAYS`; `is_heal_complete(index: SegmentIndex, pair, day) -> bool`; `publish_day(out_root, pair, day, bars) -> Path`; `@dataclass MaterializeResult(days_written, days_skipped, days_unsettled, rows, errors)`; `materialize(primary_root, reconciled_root, out_root, *, now: datetime, settle: timedelta = TAPE_SETTLE) -> MaterializeResult`.
- Consumes: `build_day` (Task 1).

- [ ] **Step 1: Write the failing tests** — `tests/test_tick_sweep.py`

```python
"""Settle gate, watermark, heal gate and sweep isolation (spec 00087 D2/D3/D4)."""

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.tick.materialize import materialize


def _day(root: Path, pair: str, day: date, *, start_id: int, hours: list[int] | None = None) -> int:
    """One trade per present hour, trade_ids SEQUENTIAL from `start_id`; returns the next unused id.

    Ids advance only when a trade prints -- they are unrelated to the calendar. A fixture that keys
    ids off the hour number fabricates an id hole at every quiet hour and every skipped day, so the
    heal gate refuses healthy days for a reason that reads exactly like a code bug. Tests therefore
    CHAIN start_id explicitly.
    """
    next_id = start_id
    for h in (range(24) if hours is None else hours):
        hour = datetime(day.year, day.month, day.day, h, tzinfo=UTC)
        d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
        d.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(
            {"ts": [hour], "symbol": [pair], "side": ["buy"], "price": [10.0], "qty": [1.0],
             "ord_type": ["limit"], "trade_id": [next_id]},
            schema=TRADE_SCHEMA,
        ).write_parquet(d / f"{hour:%H}.parquet")
        next_id += 1
    return next_id


def _after(day: date, *, hours: float) -> datetime:
    """`hours` past the END of `day`."""
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1, hours=hours)


# Every fixture below gives the day under test a SUCCESSOR segment: the heal gate refuses the
# archive's newest day (live edge -- its tail id is an endpoint, not proof), and in production a
# settled day always has successors because capture keeps writing. A one-day fixture would fail
# for the wrong reason.


def test_an_unsettled_day_is_deferred_then_taken_once_settled(tmp_path):
    """D3's pre-filter: 26h past day end is the boundary, and the watermark must not move early."""
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    nid = _day(src, "BTC/EUR", d, start_id=0)
    _day(src, "BTC/EUR", d + timedelta(days=1), start_id=nid, hours=[0])

    early = materialize(src, tmp_path / "r", out, now=_after(d, hours=25))
    assert early.days_written == 0 and early.days_unsettled == 2
    assert not list(out.rglob("*.parquet"))

    late = materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    assert late.days_written == 1 and late.days_unsettled == 1  # the successor day is still young
    assert (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()


def test_a_published_day_is_skipped_not_rewritten(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    nid = _day(src, "BTC/EUR", d, start_id=0)
    _day(src, "BTC/EUR", d + timedelta(days=1), start_id=nid, hours=[0])
    materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    final = out / "BTC" / "EUR" / "2026" / "08" / "01.parquet"
    before = final.stat().st_mtime_ns
    again = materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    assert again.days_written == 0 and again.days_skipped == 1
    assert final.stat().st_mtime_ns == before


def test_a_sidecar_is_written_and_matches_the_final(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    nid = _day(src, "BTC/EUR", d, start_id=0)
    _day(src, "BTC/EUR", d + timedelta(days=1), start_id=nid, hours=[0])
    materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    final = out / "BTC" / "EUR" / "2026" / "08" / "01.parquet"
    sidecar = final.with_suffix(".parquet.sha256")
    assert sidecar.exists()
    assert sidecar.read_text().split()[0] == hashlib.sha256(final.read_bytes()).hexdigest()


def test_a_corrupt_segment_is_isolated_and_the_sweep_continues(tmp_path):
    """D4: one broken day must not cost the others. `errors` is for the EXCEPTIONAL -- a corrupt
    segment -- because an incomplete tape is `days_unhealed`, not an error."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = 0
    for d in (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)):
        nid = _day(src, "BTC/EUR", d, start_id=nid)
    (src / "BTC" / "EUR" / "trades" / "2026" / "08" / "01" / "07.parquet").write_bytes(b"not a parquet")

    res = materialize(src, tmp_path / "r", out, now=_after(date(2026, 8, 3), hours=27))
    assert len(res.errors) == 1 and res.errors[0][0] == "BTC/EUR"
    assert res.days_written == 1  # 08-02; 08-01 errored, 08-03 is the live edge
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()
    assert (out / "BTC" / "EUR" / "2026" / "08" / "02.parquet").exists()


def test_a_quiet_hour_does_not_block_a_day(tmp_path):
    """The withdrawn 24-hour rule would refuse this forever. An absent hour file means QUIET -- no
    trade printed, so no id was consumed -- and the id stream runs contiguous straight across it."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2026, 8, 1), start_id=0)
    nid = _day(src, "BTC/EUR", date(2026, 8, 2), start_id=nid, hours=[h for h in range(24) if h != 13])
    nid = _day(src, "BTC/EUR", date(2026, 8, 3), start_id=nid)
    _day(src, "BTC/EUR", date(2026, 8, 4), start_id=nid, hours=[0])  # successor for 08-03's gate

    res = materialize(src, tmp_path / "r", out, now=_after(date(2026, 8, 3), hours=27))
    assert res.days_unhealed == 0, res
    assert res.days_written == 3
    assert (out / "BTC" / "EUR" / "2026" / "08" / "02.parquet").exists()


_EPOCH = date(2020, 1, 1)


def _holed_day(root: Path, pair: str, day: date, *, drop_hour: int | None = None) -> None:
    """A day of calendar-keyed monotone ids (24 per day), optionally with one hour's trade MISSING
    -- file and id together, a real hole.

    Unlike `_day`, ids here are keyed off the calendar so that dropping an hour leaves a genuine gap
    in the sequence. Days written with this helper must be CALENDAR-CONSECUTIVE, or the keying
    itself fabricates holes between them.
    """
    base = (day - _EPOCH).days * 24
    for h in range(24):
        if drop_hour is not None and h == drop_hour:
            continue
        hour = datetime(day.year, day.month, day.day, h, tzinfo=UTC)
        d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
        d.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(
            {"ts": [hour], "symbol": [pair], "side": ["buy"], "price": [10.0], "qty": [1.0],
             "ord_type": ["limit"], "trade_id": [base + h]},
            schema=TRADE_SCHEMA,
        ).write_parquet(d / f"{hour:%H}.parquet")


def test_a_day_with_a_trade_id_hole_is_refused_then_published_once_healed(tmp_path):
    """D3, the load-bearing gate. The clock cannot see this: the day is long settled and still
    un-healed, which is exactly the state a wall-clock proxy publishes permanently."""
    src, out, overlay = tmp_path / "src", tmp_path / "out", tmp_path / "r"
    d = date(2026, 8, 1)
    _holed_day(src, "BTC/EUR", d, drop_hour=7)
    _holed_day(src, "BTC/EUR", date(2026, 8, 2))  # a successor, so d is not at the live edge

    res = materialize(src, overlay, out, now=_after(date(2026, 8, 2), hours=99))
    assert res.days_unhealed >= 1
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()

    _holed_day(src, "BTC/EUR", d)  # the healer fills the hole
    materialize(src, overlay, out, now=_after(date(2026, 8, 2), hours=99))
    assert (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()


def test_a_hole_on_the_day_boundary_is_caught_by_the_neighbour_extension(tmp_path):
    """`detect` treats the last observed id as an endpoint, never a gap -- so over one day a hole at
    the day's TAIL reads clean and a truncated day publishes short, permanently. The extension into
    the next present segment is what makes it visible."""
    src, out, overlay = tmp_path / "src", tmp_path / "out", tmp_path / "r"
    _holed_day(src, "BTC/EUR", date(2026, 8, 1))                # complete
    _holed_day(src, "BTC/EUR", date(2026, 8, 2), drop_hour=23)  # its LAST trade missing
    _holed_day(src, "BTC/EUR", date(2026, 8, 3))                # the extension target
    res = materialize(src, overlay, out, now=_after(date(2026, 8, 3), hours=27))
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "02.parquet").exists(), "a tail hole must be seen"
    assert (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists(), "its intact neighbour still publishes"


def test_a_healed_day_inside_the_rescan_window_is_picked_up_later(tmp_path):
    """D4's trailing re-scan, proven in BOTH directions: a healed day outside the window stays
    unpublished, and widening the window picks it up."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2026, 8, 1), start_id=0)
    nid = _day(src, "BTC/EUR", date(2026, 8, 5), start_id=nid)
    nid = _day(src, "BTC/EUR", date(2026, 8, 9), start_id=nid)
    _day(src, "BTC/EUR", date(2026, 8, 10), start_id=nid, hours=[0])
    hole = src / "BTC" / "EUR" / "trades" / "2026" / "08" / "05" / "07.parquet"
    kept = hole.read_bytes()
    hole.write_bytes(b"not a parquet")

    now = _after(date(2026, 8, 9), hours=27)
    first = materialize(src, tmp_path / "r", out, now=now)
    assert first.days_written == 2 and len(first.errors) == 1  # 08-01 and 08-09 publish; 08-05 errors

    hole.write_bytes(kept)  # a late overlay mint replaces the corrupt segment
    tight = materialize(src, tmp_path / "r", out, now=now, rescan_days=0)
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "05.parquet").exists()
    assert tight.days_gap == 1  # the healed-but-outside-window day is a VISIBLE gap, not a vanished one

    wide = materialize(src, tmp_path / "r", out, now=now, rescan_days=9)
    assert wide.days_written == 1
    assert (out / "BTC" / "EUR" / "2026" / "08" / "05.parquet").exists()


def test_every_pair_in_the_archive_is_swept(tmp_path):
    """D4: pairs are discovered, never hardcoded -- the capture set has already changed once."""
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    for pair in ("BTC/EUR", "ETH/BTC"):
        nid = _day(src, pair, d, start_id=0)
        _day(src, pair, d + timedelta(days=1), start_id=nid, hours=[0])
    res = materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    assert res.days_written == 2
    assert (out / "ETH" / "BTC" / "2026" / "08" / "01.parquet").exists()

```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_tick_sweep.py -q`
Expected: FAIL — `ImportError: cannot import name 'materialize'`.

- [ ] **Step 3: Implement** (append to `cli/tick/materialize.py`)

Write the constant with its derivation attached — the number alone rots the moment either input moves:

```python
# D3, derived rather than estimated. An hour heals only when `zcrypto archive backfill-trades`
# repairs it, and that job DEFERS any hour younger than its own module-local `_SETTLE` (2h) in `cli/trades/backfill.py` -- NOT `cli.archive.settle.SETTLE_HOURS`, which it never imports while
# running only once per UTC day (~00:12, the `.trade-backfill-last-utc-day` stamp on the *:12,42 pull
# timer). So at the D+1 run day D's hours 00-22 heal but hour 23 is still inside the 2h gate and is
# deferred -- it heals at the D+2 run. Day D is therefore heal-complete at D+2 00:12 UTC, ~24.2h
# after it closes; 26h adds buffer for the NAS pull cycle and clock skew. IF THE BACKFILL'S CADENCE
# OR backfill.py's _SETTLE CHANGES, THIS PRE-FILTER DRIFTS -- harmless now that the real gate is
# the measured trade_id contiguity check, which is why this constant is no longer load-bearing.
TAPE_SETTLE = timedelta(hours=26)
RESCAN_DAYS = 3
```

```python
@dataclass(frozen=True)
class MaterializeResult:
    """One sweep's verdict: published, already-covered, deferred as not-yet-heal-complete (D3), and
    failed outright (isolated, never raised -- one bad day must not cost the others)."""

    days_written: int
    days_skipped: int
    days_unsettled: int
    days_unhealed: int
    #: settled, unpublished days that have fallen OUTSIDE the candidate window -- permanent gaps.
    #: Counted from the calendar and the published set alone (zero file reads), so the signal never
    #: expires: without it, a day that leaves the window also leaves every counter, and the dataset's
    #: one permanent failure mode becomes invisible at exactly the moment it becomes final.
    days_gap: int
    rows: int
    errors: list[tuple[str, date, str]]


def is_heal_complete(index: SegmentIndex, pair: str, day: date) -> bool:
    """Has the healer finished with this day? MEASURED, never inferred from the clock (D3).

    Kraken's `trade_id` is dense and per-pair monotone, so a hole in the sequence IS missing data --
    `cli.trades.gaps.detect` proves it with no REST call. The day is read WITH the NEAREST PRESENT
    segment on each side, not merely the adjacent hour: `detect` treats the first and last observed
    id as endpoints rather than gaps, and the adjacent hour is often legitimately absent (a quiet
    hour writes no final), so an adjacent-hour-only extension degrades silently back to endpoint
    blindness and publishes a truncated day. No later segment at all means the live edge, which is
    refused; no earlier segment at all means the archive's genesis day, where the endpoint rule is
    correct and the day is accepted.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    hours = index.get(pair, {})
    own = sorted(h for h in hours if start <= h < end)
    if not own:
        return False
    before = [h for h in hours if h < start]
    after = [h for h in hours if h >= end]
    if not after:
        return False  # live edge: nothing after the day, so its tail id is an endpoint, not proof
    # `[max(before)] * bool(before)` LOOKS lazy but is not: Python evaluates max() before the
    # multiply, so an empty `before` -- the genesis day, the case this rule ACCEPTS -- crashed with
    # ValueError, and the sweep's broad except turned every pair's first day into a permanent error.
    span = own + ([max(before)] if before else []) + [min(after)]
    detection = detect(pl.concat(pl.read_parquet(hours[h]) for h in sorted(span)))
    return not detection.gaps and not detection.duplicate_ids


def _final_path(out_root: Path, pair: str, day: date) -> Path:
    base, quote = pair.split("/")
    return out_root / base / quote / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.parquet"


def publish_day(out_root: Path, pair: str, day: date, bars: pl.DataFrame) -> Path:
    """Atomic publish: tmp in the destination dir -> sidecar minted from the tmp bytes -> os.replace
    -> fsync the dir. The sidecar is written BEFORE the publishing rename so a reader never sees a
    final without its digest (the `cli/archive/mint.py` pattern)."""
    final = _final_path(out_root, pair, day)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_suffix(f".parquet.{os.getpid()}.tmp")
    bars.write_parquet(tmp)
    _fsync(tmp)  # data before rename -- mint.py's `_replace_durably` semantics, for BOTH artifacts
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    sidecar_tmp = final.with_suffix(f".parquet.sha256.{os.getpid()}.tmp")
    sidecar_tmp.write_text(f"{digest}  {final.name}\n")
    # A torn sidecar is PERMANENT: the .exists() skip means the day is never re-published, so an
    # un-fsynced sidecar that loses its bytes at power loss reads as corruption on an irreplaceable
    # final, forever. The sidecar gets the same durability as the final it vouches for.
    _fsync(sidecar_tmp)
    os.replace(sidecar_tmp, final.with_suffix(".parquet.sha256"))
    os.replace(tmp, final)
    _fsync(final.parent)
    return final


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _archive_calendar(index: SegmentIndex) -> dict[str, list[date]]:
    """Every archived pair -> its sorted distinct UTC days, read off the one index walk."""
    return {pair: sorted({hour.date() for hour in hours}) for pair, hours in sorted(index.items())}


def _watermark(out_root: Path, pair: str) -> date | None:
    """The newest published day for `pair`, or None on a first run."""
    base, quote = pair.split("/")
    finals = sorted((out_root / base / quote).rglob("*.parquet"))
    if not finals:
        return None
    newest = finals[-1]
    return date(int(newest.parents[1].name), int(newest.parent.name), int(newest.stem))


def materialize(
    primary_root: Path,
    reconciled_root: Path,
    out_root: Path,
    *,
    now: datetime,
    settle: timedelta = TAPE_SETTLE,
    rescan_days: int = RESCAN_DAYS,
) -> MaterializeResult:
    """Sweep every archived pair, publishing each settled day that has no final yet.

    `now` is injected so the settle boundary is testable. A day is settled once
    `now - (day_end) >= settle`; an unsettled day is counted and left alone, so a later sweep takes
    it once heal-complete (D3 / T0066 option (a)). A day that raises is isolated into `errors`.
    """
    written = skipped = unsettled = unhealed = gap = rows = 0
    errors: list[tuple[str, date, str]] = []
    index = segment_index(primary_root, reconciled_root)
    for pair, days in _archive_calendar(index).items():
        settled = [d for d in days if now - (datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1)) >= settle]
        unsettled += len(days) - len(settled)
        if not settled:
            continue
        # Bounded candidate range (D4): everything past the watermark, plus a trailing re-scan window
        # so a day that failed while its tape was incomplete is retried while a late overlay mint can
        # still rescue it -- and then becomes a permanent, VISIBLE gap rather than an unbounded retry.
        watermark = _watermark(out_root, pair)
        if watermark is None:
            # FIRST RUN: sweep the whole archive. Bounding it here would silently strand the entire
            # backlog -- the watermark would jump to the newest day and everything below the floor
            # would never be attempted again, with no error and no counter. A permanently short
            # dataset that looks complete is the worst outcome this design can produce.
            candidates = settled
        else:
            floor = min(settled[-1] - timedelta(days=rescan_days), watermark + timedelta(days=1))
            candidates = [d for d in settled if d >= floor]
            gap += sum(1 for d in settled if d < floor and not _final_path(out_root, pair, d).exists())
        for day in candidates:
            if _final_path(out_root, pair, day).exists():
                skipped += 1
                continue
            try:
                if not is_heal_complete(index, pair, day):
                    unhealed += 1
                    continue
                bars = build_day(index, pair, day)
            except Exception as exc:  # noqa: BLE001 -- one bad day must not abort the sweep
                # Broad on purpose, matching cli/panel/materialize.py: a corrupt parquet or an
                # unexpected error inside detect must cost one day, never every pair's whole sweep.
                errors.append((pair, day, f"{type(exc).__name__}: {exc}"))
                continue
            publish_day(out_root, pair, day, bars)
            written += 1
            rows += bars.height
    return MaterializeResult(written, skipped, unsettled, unhealed, gap, rows, errors)
```

Add `import hashlib`, `import os`, `from dataclasses import dataclass`, and `from cli.trades.gaps import detect` to the module imports.

**Note on `days_unsettled`:** it counts unsettled days across the whole archive calendar, not only recent ones, so on a fresh archive the newest day or two register there — that is the D3 gate working. The candidate range, by contrast, is bounded by the watermark and the trailing window, which is what keeps a sweep O(recent) on an archive that grows forever.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_tick_sweep.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/tick/materialize.py tests/test_tick_sweep.py
git commit -m "feat(tick): settle-gated, watermark-skipping sweep with atomic daily finals"
```

---

### Task 4: The CLI + README

**Files:**

- Create: `cli/tick/command.py`
- Modify: `cli/__main__.py`, `README.md`
- Test: `tests/test_tick_command.py`

**Interfaces:**

- Produces: `tick_app` (Typer sub-app), registered as `zcrypto tick`; `zcrypto tick materialize <primary-root> <out-root> --reconciled-root PATH [--settle-hours INT]`.
- Consumes: `materialize`, `MaterializeResult`, `TAPE_SETTLE`, `RESCAN_DAYS` (Task 3).

- [ ] **Step 1: Write the failing tests** — `tests/test_tick_command.py`

```python
"""The `zcrypto tick materialize` surface (spec 00087 D6)."""

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.segment_writer import TRADE_SCHEMA

runner = CliRunner()


def _day(root: Path, pair: str, day: date, *, start_id: int, hours: list[int] | None = None) -> int:
    """Same contract as tests/test_tick_sweep.py's `_day`: sequential ids, chained explicitly."""
    next_id = start_id
    for h in (range(24) if hours is None else hours):
        hour = datetime(day.year, day.month, day.day, h, tzinfo=UTC)
        d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
        d.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(
            {"ts": [hour], "symbol": [pair], "side": ["buy"], "price": [10.0], "qty": [1.0],
             "ord_type": ["limit"], "trade_id": [next_id]},
            schema=TRADE_SCHEMA,
        ).write_parquet(d / f"{hour:%H}.parquet")
        next_id += 1
    return next_id


def test_materialize_publishes_and_reports(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)  # long past -- settled against the real clock
    _day(src, "BTC/EUR", date(2020, 1, 2), start_id=nid, hours=[0])  # successor: the live-edge day never publishes
    res = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r")])
    assert res.exit_code == 0, res.output
    assert "days_written=1" in res.output
    assert (out / "BTC" / "EUR" / "2020" / "01" / "01.parquet").exists()


def test_a_failed_day_exits_nonzero_and_names_the_pair(tmp_path):
    """A sweep that isolated an error must not report success -- the exit code is what a timer sees.
    A CORRUPT segment is the error case; an incomplete tape is days_unhealed and exits 0."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)
    _day(src, "BTC/EUR", date(2020, 1, 2), start_id=nid, hours=[0])
    (src / "BTC" / "EUR" / "trades" / "2020" / "01" / "01" / "07.parquet").write_bytes(b"not a parquet")
    res = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r")])
    assert res.exit_code != 0
    assert "BTC/EUR" in res.output


def test_rescan_days_reaches_the_sweep(tmp_path):
    """A flag accepted and ignored is a lie in --help. The first run sweeps the WHOLE archive (no
    watermark -- bounding it would strand the backlog silently); with a watermark, a healed old day
    is retried only inside the window, and widening the window reaches it."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)
    nid = _day(src, "BTC/EUR", date(2020, 1, 5), start_id=nid)
    nid = _day(src, "BTC/EUR", date(2020, 1, 9), start_id=nid)
    _day(src, "BTC/EUR", date(2020, 1, 10), start_id=nid, hours=[0])
    hole = src / "BTC" / "EUR" / "trades" / "2020" / "01" / "05" / "07.parquet"
    kept = hole.read_bytes()
    hole.write_bytes(b"not a parquet")

    first = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r")])
    assert first.exit_code != 0  # the corrupt day is an error...
    assert (out / "BTC" / "EUR" / "2020" / "01" / "01.parquet").exists(), "...and the backlog day still published"

    hole.write_bytes(kept)
    tight = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r"), "--rescan-days", "0"])
    assert tight.exit_code == 0
    assert not (out / "BTC" / "EUR" / "2020" / "01" / "05.parquet").exists()

    wide = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r"), "--rescan-days", "9"])
    assert wide.exit_code == 0
    assert (out / "BTC" / "EUR" / "2020" / "01" / "05.parquet").exists()


def test_settle_hours_is_overridable(tmp_path):
    """An operator must be able to widen the gate; the default is TAPE_SETTLE."""
    src, out = tmp_path / "src", tmp_path / "out"
    _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)
    res = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r"), "--settle-hours", "999999"])
    assert res.exit_code == 0
    assert "days_unsettled=1" in res.output
    assert not list(out.rglob("*.parquet"))

```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_tick_command.py -q`
Expected: FAIL — no `tick` command.

- [ ] **Step 3: Implement `cli/tick/command.py`**

```python
"""The `zcrypto tick` Typer sub-app: materialize tape-bars from the healed trade archive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from cli.tick.materialize import RESCAN_DAYS, TAPE_SETTLE, materialize

tick_app = typer.Typer(help="Bars derived from the captured trade tape.")


@tick_app.command("materialize")
def materialize_cmd(
    primary_root: Path = typer.Argument(..., help="The primary (raw) canonical trade archive."),
    out_root: Path = typer.Argument(..., help="Dataset root the daily finals are published into."),
    reconciled_root: Path = typer.Option(..., "--reconciled-root", help="The healed overlay, read first. REQUIRED: an optional overlay is one forgotten flag away from publishing the un-healed stream."),
    settle_hours: int = typer.Option(int(TAPE_SETTLE.total_seconds() // 3600), "--settle-hours", help="Hours past a day's end before it may be published."),
    rescan_days: int = typer.Option(RESCAN_DAYS, "--rescan-days", help="Trailing settled days re-attempted, so a late-healed day is still picked up."),
) -> None:
    """Publish every settled, not-yet-published day of 15m tape-bars.

    A day is published only once heal-complete, so a normal run on a fresh archive reports
    `days_unsettled` for the newest day or two -- that is the gate working, not a failure.
    """
    result = materialize(
        primary_root,
        reconciled_root,
        out_root,
        now=datetime.now(UTC),
        settle=timedelta(hours=settle_hours),
        rescan_days=rescan_days,
    )
    typer.echo(
        f"days_written={result.days_written} days_skipped={result.days_skipped} "
        f"days_unsettled={result.days_unsettled} days_unhealed={result.days_unhealed} "
        f"days_gap={result.days_gap} "
        f"rows={result.rows} errors={len(result.errors)}"
    )
    for pair, day, message in result.errors:
        typer.echo(f"  ERROR {pair} {day.isoformat()}: {message}", err=True)
    if result.errors:
        raise typer.Exit(code=1)
```

Every option must do something: `--rescan-days` reaches `materialize`'s parameter of the same name, and Task 4's third test proves `--settle-hours` reaches the gate. A flag that is accepted and ignored is a lie in `--help`.

Register in `cli/__main__.py` beside the existing sub-apps:

```python
app.add_typer(tick_app, name="tick")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_tick_command.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: PASS. The second file matters: `cli/tick/command.py` is a scanned surface, so no `T<NNNN>`, `spec NNNNN`, `D<n>` or `iter-` tokens may appear in any **non-docstring** string literal.

- [ ] **Step 5: README `## Usage`**

Add a `zcrypto tick materialize` entry documenting the two arguments, the three options, and that a fresh archive's newest day or two will report `days_unsettled` by design.

- [ ] **Step 6: Commit**

```bash
git add cli/tick/command.py cli/__main__.py README.md tests/test_tick_command.py
git commit -m "feat(tick): zcrypto tick materialize, the tape-bars entry point"
```

---

### Task 5: The REST control — the only independent witness, and it expires

**Files:**

- Test: `tests/test_tape_bars_rest_control.py`

**Interfaces:**

- Consumes: `build_day` (Task 1); the repo's existing Kraken public REST OHLC client.

- [ ] **Step 1: Find the existing REST OHLC fetcher**

Run: `grep -rn "def .*ohlc\|OHLC" cli/ohlc/*.py | grep -i "rest\|fetch\|client" | head`
Use whatever the reach round already uses (`cli/ohlc/reach.py` calls it) — do **not** write a second REST client.

- [ ] **Step 2: Write the control**

```python
"""The tape's only independent witness -- and it expires (spec 00087 Verification).

The tape starts 2026-07-08 and `ohlc-full` ends 2026-03-31, so they do NOT overlap and there is no
canonical to check tape-bars against. Kraken's public REST OHLC does overlap, at 15m, for only about
7.5 days back. This control therefore proves the whole chain -- reconciled read -> ticks_to_bars ->
day file -- against an independent source, and it can only ever prove it for a RECENT day. It skips
(never passes) when the archive is absent or the REST window no longer reaches the day it needs.
"""
```

The test: pick the newest day that is both fully present in the archive and inside the REST 15m window; build it with `build_day`; fetch REST 15m for the same UTC day; compare bar-for-bar on `ts`/`open`/`high`/`low`/`close`, and on `volume`/`vwap` within a documented tolerance. Skip with an explicit reason when the archive root is absent, when no day satisfies both windows, or when the REST call fails — a network failure must not read as a data failure.

**Tolerance is a decision, not a fudge:** Kraken's published OHLC is built from its own trade feed, so `ts`/OHLC must match **exactly**; `volume`/`vwap` may differ in the last ulps from float summation order. Assert exact equality on the price columns and `pytest.approx` with `rel=1e-9` on the two summed columns. If a real mismatch appears, that is a finding to report — **do not widen the tolerance to make it pass.**

- [ ] **Step 3: Run it on the workstation**

Run: `uv run pytest tests/test_tape_bars_rest_control.py -q -rs`
Expected: PASS if the archive is present locally, else SKIP with the reason printed. If it FAILS, stop and report the discrepancy — that is the control doing its job.

- [ ] **Step 4: Commit**

```bash
git add tests/test_tape_bars_rest_control.py
git commit -m "test(tick): prove tape-bars against Kraken REST while the window still reaches"
```

---

### Task 6: Prove the guards by construction

All probes through `infra/scripts/mutate-probe.sh` (clean tree; it refuses a dirty one, a no-op sed, and a control that does not fail). Record **which** failure fired for each — a red exit can be the harness misfiring.

- [ ] **Probe 1 — the settle gate:** sed `TAPE_SETTLE = timedelta(hours=26)` to `hours=0` → `test_an_unsettled_day_is_deferred_then_taken_once_settled` must fail.
- [ ] **Probe 2 — the qty→volume rename:** sed `.rename({"qty": "volume"})` to `.rename({})` → `test_volume_comes_from_qty_not_a_missing_column` must fail.
- [ ] **Probe 3 — the empty-day refusal:** sed `if not present:` in `build_day` to `if False:` → `test_a_day_with_no_segments_is_refused` must fail.
- [ ] **Probe 4 — reconciled-first:** sed `canonical_segments(primary_root, reconciled_root, kind="trades")` in `segment_index` to pass `None` as the overlay → `test_the_reconciled_overlay_wins_over_the_primary` must fail. (`reconciled_root` is a required argument, so the un-healed path is unreachable through the API; this probe proves the reader is genuinely overlay-aware rather than that a caller remembered a flag.)
- [ ] **Probe 5 — the weighted vwap:** sed `(pl.col("vwap") * pl.col("volume")).sum().alias("_pv_sum")` to `(pl.col("vwap").mean() * pl.col("volume").sum()).alias("_pv_sum")` → `test_derived_equals_direct_aggregation` must fail **by VALUE, not by crash** — the alias is kept precisely so the wrong formula flows silently into the equality assertion, which is the failure mode D1 warns about. (An alias-dropping sed dies on `ColumnNotFoundError` instead: that proves the line load-bearing, but not that the test catches a silently wrong number.)
- [ ] **Probe 6 — no-rewrite:** sed the `_final_path(...).exists()` skip to `False` → `test_a_published_day_is_skipped_not_rewritten` must fail.
- [ ] **Probe 7 — the measured heal gate:** sed `is_heal_complete(...)` in the sweep to `True` → `test_a_day_with_a_trade_id_hole_is_refused_then_published_once_healed` must fail. This is the guard that replaced a wall-clock proxy cold review killed; if it does not bite, the design is back to publishing un-healed days permanently.
- [ ] **Probe 8 — the neighbour extension:** sed the `span = own + ...` line to `span = own` (no neighbours) → `test_a_hole_on_the_day_boundary_is_caught_by_the_neighbour_extension` must fail. Without the extension `detect` reads a boundary hole as clean, so this probe is what proves the test is not passing for the wrong reason.
- [ ] **Probe 9 — the first-run backlog:** sed the `if watermark is None:` branch to take the bounded path → `test_rescan_days_reaches_the_sweep`'s first-run assertion must fail. The defect it reconstructs strands a month of tape silently, with no error and no counter.
- [ ] **Probe 10 — error isolation:** sed the `except Exception` block to re-raise → `test_a_corrupt_segment_is_isolated_and_the_sweep_continues` must fail.
- [ ] **Probe 11 — the quiet-hour acceptance:** reinstate the withdrawn 24-hour rule (add a `len(present) != 24` raise to `build_day`) → `test_a_quiet_hour_does_not_block_a_day` must fail. This reconstructs the defect cold review found: a rule that reads like completeness and actually refuses every thin day forever.
- [ ] **Record every verdict** in the task report: probe, sed target, which test failed, and the control's result. A probe whose control did not fail proves nothing — choose a control the probe must detect and re-run.

---

### Task 7: The ops runner + timer

**Files:**

- Create: `infra/ansible/roles/ops/templates/tape-bars.sh.j2`, `infra/ansible/roles/ops/templates/tape-bars.service.j2`, `infra/ansible/roles/ops/templates/tape-bars.timer.j2`
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (render + enable, mirroring the panel's block)

- [ ] **Step 1: Read the panel's three templates and its task block** — `panel-materialize.{sh,service,timer}.j2`. Mirror them exactly: same `docker run --rm --pull never` shape, same image/digest variables, same log handling, same `--limit`-free structure.
- [ ] **Step 2: Write the three templates.** The runner mirrors the panel's OBSERVABILITY as well as its shape — the panel is protected by textfile metrics, an alert rule and a dead-man, and a runner with none of those can stall forever with every surface green, because the unhealed path exits 0 by design. The sh template therefore exports textfile gauges after every run (`zcrypto_tapebars_exit_code`, `_days_written`, `_days_unhealed`, `_days_gap`, `_errors`, and `_last_success_timestamp_seconds` on success), following the panel runner's export pattern exactly. The timer is `OnCalendar=*-*-* *:52:00` — clear of the `:12,42` pull, the panel's `:22`, and the `02:25` auto-reboot. Hourly though the grain is daily: a day becomes eligible ~26 h after it ends and is taken within the hour, and an hourly sweep catches up after any outage with no backlog logic.
- [ ] **Step 3: Verify by rendering, not by converging.** Run `uv run pytest tests/test_converge_sh.py -q` plus any template-rendering test the repo has, and `uv run ansible-lint infra/ansible` if the pre-commit hook does not already cover it.
- [ ] **Step 4: Commit**

```bash
git add infra/ansible/roles/ops/templates/tape-bars.sh.j2 \
        infra/ansible/roles/ops/templates/tape-bars.service.j2 \
        infra/ansible/roles/ops/templates/tape-bars.timer.j2 \
        infra/ansible/roles/ops/tasks/main.yml
git commit -m "feat(ops): render the tape-bars materializer timer"
```

**The converge itself is NOT part of this plan.** It is an attended ops step requiring `--limit zcrypto-ops`, a `fleet-pins.md` row, and the owner's explicit word — carried to closeout, never run by an implementer.

---

### Task 8: Closeout

- [ ] **Step 1:** `docs/reference/data-catalog-full.md` — add `tape-bars` to the accruing operational members: producer (`zcrypto tick materialize` on ops, hourly), location and layout, the 15m base with derived grids, the 26 h settle and why, and that it carries `.sha256` sidecars and **no manifest** (D5).
- [ ] **Step 2:** [[T0065]] — move the materializer to `## Done so far` with its commits; rewrite `ripe_when` so **REACH's remaining half is the Q2/Q3 ingest alone**, still gated on Kraken publishing (verified absent 2026-08-10). Index bullet updated to match (`topic-ops`). Do **not** mark T0065 resolved — the ingest half is live.
- [ ] **Step 3:** Two alert rules into `infra/grafana/alerts.yaml`, pushed and verified BY VALUE at the attended converge (never before it): `zcrypto_tapebars_days_gap > 0` — a permanent gap just became final, and nothing else will ever say so again — and staleness on `zcrypto_tapebars_last_success_timestamp_seconds`, the stalled-healer case where the watermark freezes with every other surface green. Follow `.claude/rules/fleet-deploys.md`'s push/verify/prune discipline.
- [ ] **Step 4:** Iterations-history entry (phase 6 per `iteration-closeout`), naming: the measured settle derivation and that it corrects [[T0066]]'s estimate's *mechanism*; the no-overlap verification problem and the perishable REST control; the probe verdicts; and that the ops converge is owed and un-run.
- [ ] **Step 5:** Phase-6 decisions-log entry for D1 (15m base + derived grids), D2 (daily finals), D3 (26 h settle, measured) and D5 (no manifest), each with its options and the ruling.
- [ ] **Step 6:** Full suite + `uv run pre-commit run -a` clean. Report ready, naming the owed ops converge explicitly. **Do not open the PR without the owner's word.**
