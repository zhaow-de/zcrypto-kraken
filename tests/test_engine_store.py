import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

import cli.engine.store as store_module
import cli.ohlc.fetch as fetch_module
from cli.engine.errors import EngineError
from cli.engine.store import (
    BASKET,
    GRID_INTERVALS,
    PAIR_KEYS,
    _store_path,
    read_store_series,
    refresh_store,
    seed_store,
)
from cli.ohlc.dataset import read_parquet, to_frame, write_parquet

DAILY_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
H4_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
N_CANON = 10
FAR_FUTURE = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _row(ts: datetime, close: float) -> list:
    # Kraken's real shape: [time, open, high, low, close, vwap, volume, count] -- prices as
    # strings, count as a plain int (see tests/fixtures/kraken_ohlc_xxbtzeur_1440.json).
    return [int(ts.timestamp()), str(close), str(close), str(close), str(close), str(close), "1.0", 1]


def _rows_from(ref_start: datetime, step: timedelta, first_i: int, n: int) -> list[list]:
    return [_row(ref_start + i * step, 100.0 + i) for i in range(first_i, first_i + n)]


def _grid_ref(interval: int) -> tuple[datetime, timedelta]:
    return (DAILY_START, timedelta(days=1)) if interval == 1440 else (H4_START, timedelta(hours=4))


def _canonical_rows(interval: int) -> list[list]:
    ref, step = _grid_ref(interval)
    return _rows_from(ref, step, 0, N_CANON)


def _good_rest_rows(interval: int) -> list[list]:
    """6 bars overlapping the canonical tail + 3 new completed bars, matching exactly."""
    ref, step = _grid_ref(interval)
    return _rows_from(ref, step, N_CANON - 6, 9)


def _good_fetch_fn(pair_key: str, interval: int) -> list[list]:
    return _good_rest_rows(interval)


def _fetch_override(pair_key_target: str, interval_target: int, override_rows: list[list]):
    def _fn(pair_key: str, interval: int) -> list[list]:
        if pair_key == pair_key_target and interval == interval_target:
            return override_rows
        return _good_rest_rows(interval)

    return _fn


def _write_full_universe(root: Path, row_fn) -> None:
    for symbol in PAIR_KEYS:
        for interval in GRID_INTERVALS:
            write_parquet(to_frame(row_fn(interval)), _store_path(root, symbol, interval))


def test_basket_has_twelve_sorted_members_with_both_btc_legs():
    assert len(BASKET) == 12
    assert list(BASKET) == sorted(BASKET)
    assert "ETH/BTC" in BASKET
    assert "SOL/BTC" in BASKET


def test_pair_keys_content():
    # Independently transcribed from docs/reference/kraken-snapshot-register.md's candidate
    # basket table -- all twelve symbols, EUR-quoted and BTC-quoted alike.
    expected = {
        "ADA/EUR": "ADAEUR",
        "AVAX/EUR": "AVAXEUR",
        "BTC/EUR": "XXBTZEUR",
        "DOGE/EUR": "XDGEUR",
        "DOT/EUR": "DOTEUR",
        "ETH/BTC": "XETHXXBT",
        "ETH/EUR": "XETHZEUR",
        "LINK/EUR": "LINKEUR",
        "LTC/EUR": "XLTCZEUR",
        "SOL/BTC": "SOLXBT",
        "SOL/EUR": "SOLEUR",
        "XRP/EUR": "XXRPZEUR",
    }
    assert PAIR_KEYS == expected
    assert PAIR_KEYS["ETH/BTC"] == "XETHXXBT"
    assert PAIR_KEYS["SOL/BTC"] == "SOLXBT"


def test_grid_intervals():
    assert GRID_INTERVALS == (1440, 240)


def test_the_engine_basket_now_spans_both_quotes_and_twelve_legs():
    from cli.engine.store import PAIR_KEYS as ENGINE_KEYS
    from cli.ohlc.fetch import PAIR_KEYS as FETCH_KEYS

    assert len(ENGINE_KEYS) == 12
    assert all("/" in k for k in ENGINE_KEYS), "engine keys are now full BASE/QUOTE symbols"
    assert ENGINE_KEYS["ETH/EUR"] == FETCH_KEYS["ETH/EUR"]
    # The two BTC-quoted legs the old ten-EUR-only basket excluded are now present, carrying the
    # fetch map's own venue spelling unchanged (never re-derived here).
    assert ENGINE_KEYS["ETH/BTC"] == FETCH_KEYS["ETH/BTC"] == "XETHXXBT"
    assert ENGINE_KEYS["SOL/BTC"] == FETCH_KEYS["SOL/BTC"] == "SOLXBT"


def test_store_path_is_quote_aware():
    root = Path("/root")
    assert _store_path(root, "ETH/BTC", 1440) == root / "ETH" / "BTC" / "1440.parquet"
    assert _store_path(root, "ETH/EUR", 1440) == root / "ETH" / "EUR" / "1440.parquet"


def test_basket_symbol_missing_from_fetch_map_raises_at_import(monkeypatch):
    reduced = dict(fetch_module.PAIR_KEYS)
    del reduced["ETH/BTC"]
    monkeypatch.setattr(fetch_module, "PAIR_KEYS", reduced)
    try:
        with pytest.raises(KeyError):
            importlib.reload(store_module)
    finally:
        monkeypatch.undo()
        importlib.reload(store_module)


def test_seed_store_happy_path(tmp_path):
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)

    report = seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    assert len(report.entries) == len(PAIR_KEYS) * len(GRID_INTERVALS)
    assert sum(e.appended for e in report.entries) == len(report.entries) * 3
    assert sum(e.replaced_tail_rows for e in report.entries) == 0

    btc_daily = next(e for e in report.entries if e.pair == "BTC/EUR" and e.interval == 1440)
    assert btc_daily.overlap_bars == 6
    assert btc_daily.appended == 3
    assert btc_daily.replaced_tail_rows == 0

    ts, closes = read_store_series(store_dir, "BTC/EUR", 1440)
    assert len(ts) == N_CANON + 3
    assert closes == [100.0 + i for i in range(N_CANON + 3)]
    assert ts[-1] == DAILY_START + timedelta(days=N_CANON + 2)
    assert ts[0].tzinfo is not None  # aware-UTC


def test_seed_store_window_shortfall_names_ohlcvt_dump(tmp_path):
    """`rest_head` (day 50) is newer than `store_tail` (day 9, the canonical's), so the two sides are disjoint by
    construction and the cause is ambiguous: both candidates are named with a next step each, the store-side one is
    the quarterly dump because this seed created the store file from the canonical, and the measurements an operator
    would read to tell them apart are carried. The copy has already landed when the seam refuses, so that repair opens
    by moving the landed leg aside -- without it the next seed reads the same leg and refuses the same way."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)

    disjoint_rows = _rows_from(DAILY_START, timedelta(days=1), 50, 9)  # zero overlap w/ canonical i=0..9
    fetch_fn = _fetch_override("XXBTZEUR", 1440, disjoint_rows)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "OHLCVT" in msg
    assert "shortfall" in msg
    assert "move this leg aside (outside the store) and use the quarterly OHLCVT dump" in msg
    assert "a seed over a present file never reads the canonical again" in msg  # why the move-aside comes first
    assert _store_path(store_dir, "BTC/EUR", 1440).exists()  # the leg the repair moves aside is on disk already
    assert "the venue answered with a shorter history than the seam needs" in msg  # the fetch-side candidate
    # The store side is the canonical here, not a file that predates the run: this seed copied it in.
    assert "the canonical this run copied into the store was already behind the REST window's reach" in msg
    assert "if the venue is the cause there is no store repair and the next run fetches again" in msg
    assert "9 completed row(s) the fetch carries" in msg  # a measurement; the forming bar is already dropped
    assert f"({DAILY_START + timedelta(days=9)})" in msg  # the store's last stamp, a measurement
    assert f"({DAILY_START + timedelta(days=50)})" in msg  # the fetch's oldest stamp, a measurement


def test_seed_store_seam_holes_names_a_step_on_each_side(tmp_path):
    """`rest_head` (day 5) is at or behind `store_tail` (day 9), so the window is proven to still reach it and a
    receded window is refuted, and the store leg (10 rows) clears the floor of 6 on its own: what is left is holes at
    the stamps the seam needs. Here they are the fetch's -- days 8 and 9 -- but the door cannot measure that, so it
    names both sides, the reading that separates them, and a step on each: the next fetch for the venue's side, and
    for the store's the repair its neighbouring arms name, which on a first seed opens by moving the landed leg
    aside. The dump stays out: it answers a receded window, which this arm has refuted."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)

    hole_rows = _rows_from(DAILY_START, timedelta(days=1), 5, 3) + _rows_from(DAILY_START, timedelta(days=1), 10, 2)
    fetch_fn = _fetch_override("XXBTZEUR", 1440, hole_rows)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "seed_store: window shortfall for BTC/EUR@1440 — only 3 shared stamp(s)" in msg
    assert "the stamps the seam needs are missing on one side or the other" in msg
    assert "absent from the fetch's answer, or absent from the store leg" in msg  # both candidates
    assert "read the two sides' stamps across the span they both cover" in msg  # the reading that separates them
    assert "there is no store repair -- the next run fetches again" in msg  # the fetch-side step
    assert "the store leg carries enough rows to clear the floor on its own" in msg
    assert "OHLCVT" not in msg and "quarterly" not in msg
    # The store-side step, routed as the neighbouring arms route it: this seed copied the leg in, so it is the
    # canonical's and it is already on disk, which is why the repair opens by moving it aside.
    assert "and if the store leg is the holed side, the leg is the canonical's, copied into the store by this seed" in msg
    assert "move this leg aside (outside the store) and rebuild the set" in msg
    assert _store_path(store_dir, "BTC/EUR", 1440).exists()
    assert "zcrypto engine seed" not in msg  # the store file's own recovery answers a re-seed, not a first seed


@pytest.mark.parametrize("seeding", ["first seed", "re-seed"])
def test_seed_store_short_store_leg_names_the_store_side_repair(tmp_path, seeding):
    """The leg holds 3 rows against a floor of 6, and the shared stamps being a subset of the leg's own, no answer
    the venue could send clears it -- so the height settles the arm and the fetch's reach is neither read nor
    claimed. The repair is routed by which file the short leg is: the canonical this seed copied, or the live store
    file."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir if seeding == "first seed" else store_dir, lambda iv: _rows_from(*_grid_ref(iv), 0, 3))

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=lambda pk, iv: _rows_from(*_grid_ref(iv), 1, 5), clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "seed_store: window shortfall for ADA/EUR@1440 — only 2 shared stamp(s)" in msg
    assert "the store leg carries 3 row(s) against a floor of 6" in msg
    assert "no answer the venue could send clears it and the store side is the cause" in msg
    assert "the venue answered with a shorter history" not in msg  # one cause, not two candidates
    if seeding == "first seed":
        assert "the leg is the canonical's, copied into the store by this seed" in msg
        assert "`zcrypto data rebuild ohlc-full --no-push`" in msg
        # The copy already landed, so the rebuild alone never reaches the next seed: the move-aside comes first.
        assert "move this leg aside (outside the store) and rebuild the set" in msg
        assert _store_path(store_dir, "ADA/EUR", 1440).exists()
    else:
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
        assert "rebuild the set" not in msg


def test_seed_store_short_store_leg_is_answered_as_short_even_when_disjoint(tmp_path):
    """The height test runs above the reach test: this leg holds 3 rows against a floor of 6 AND shares no stamp with
    the fetch (days 50-58), and its own height settles it. Routed by reach instead, it would take the disjoint hint,
    whose reading weighs a venue candidate the leg's height has already refuted."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, lambda iv: _rows_from(*_grid_ref(iv), 0, 3))

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=lambda pk, iv: _rows_from(*_grid_ref(iv), 50, 9), clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "seed_store: window shortfall for ADA/EUR@1440 — only 0 shared stamp(s)" in msg
    assert "the store leg carries 3 row(s) against a floor of 6" in msg
    assert "no answer the venue could send clears it and the store side is the cause" in msg
    assert "the venue answered with a shorter history than the seam needs" not in msg  # the disjoint arm's reading
    assert "share no stamp by construction" not in msg
    assert "the window still reaches the tail" not in msg  # the fetch is disjoint: nothing here proves reach


@pytest.mark.parametrize("seeding", ["first seed", "re-seed"])
def test_seed_store_short_store_leg_is_answered_as_short_even_when_the_fetch_is_empty(tmp_path, seeding):
    """The height test runs above the empty-fetch test: this leg holds 3 rows against a floor of 6 AND the fetch
    carries no completed bar, and its own height settles it. Routed by emptiness instead, it would be answered with a
    next fetch that cannot clear a floor the leg itself misses, at either seeding."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir if seeding == "first seed" else store_dir, lambda iv: _rows_from(*_grid_ref(iv), 0, 3))

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=lambda pk, iv: [], clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "seed_store: window shortfall for ADA/EUR@1440 — only 0 shared stamp(s)" in msg
    assert "the store leg carries 3 row(s) against a floor of 6" in msg
    assert "no answer the venue could send clears it and the store side is the cause" in msg
    assert "the REST fetch carries no completed bar" not in msg  # the empty arm's text, which sits below this one
    if seeding == "first seed":
        assert "move this leg aside (outside the store) and rebuild the set" in msg
        assert _store_path(store_dir, "ADA/EUR", 1440).exists()
    else:
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg


def test_seed_store_disjoint_reseed_names_store_file_recovery_not_the_dump(tmp_path):
    """On a re-seed the tail read is the live store file's, not the canonical's, so the store-side candidate the
    disjoint hint names is the store-file recovery (move the leg aside and re-seed) -- never the quarterly dump,
    whose repair only answers a first seed's canonical-derived tail."""
    store_dir = tmp_path / "store"
    canonical_dir = tmp_path / "unused_canonical"  # never read: the store pre-exists for every pair
    _write_full_universe(store_dir, _canonical_rows)

    disjoint_rows = _rows_from(DAILY_START, timedelta(days=1), 50, 9)  # zero overlap w/ the store's own i=0..9
    fetch_fn = _fetch_override("XXBTZEUR", 1440, disjoint_rows)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "shortfall" in msg
    assert "OHLCVT" not in msg  # the dump is not named; _STORE_RECOVERY's own "quarterly ingest" is a distinct phrase
    assert "the venue answered with a shorter history than the seam needs" in msg
    assert "the store fell behind the REST window's reach" in msg
    assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    assert "on the engine host the store is re-delivered, not seeded" in msg


def test_seed_store_routes_a_shortfall_from_an_empty_fetch_to_the_fetch(tmp_path):
    """The seed's shortfall arm is reached by an empty REST answer as well as by a canonical tail outside the REST
    window, and only the second names the dump, as a candidate: an empty answer is decided before either frame's
    stamps are read and names the fetch alone. The canonical copy has already landed when the seam refuses --
    `seed_store` copies an absent leg before the reconcile -- so the leg is present for the next run and the refusal
    prescribes nothing over it."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=lambda pair_key, interval: [], clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "seed_store: window shortfall for ADA/EUR@1440 — only 0 shared stamp(s)" in msg
    assert "the REST fetch carries no completed bar, so there is no store repair" in msg
    assert "the next run fetches again" in msg
    assert "OHLCVT" not in msg and "quarterly" not in msg
    # The landed copy is named, in the wording the first-seed arms use for it, and nothing is prescribed over it:
    # no move-aside, no re-seed -- the fetch is still the only thing that can change.
    assert "the leg is the canonical's, copied into the store by this seed" in msg
    assert "a seed over a present file never reads the canonical again" in msg
    assert "zcrypto engine seed" not in msg and "move this leg aside" not in msg
    assert "rebuild the set" not in msg
    landed = _store_path(store_dir, "ADA/EUR", 1440)
    assert read_parquet(landed).equals(to_frame(_canonical_rows(1440)))


def test_seed_store_overlap_mismatch_aborts_on_first_seed(tmp_path):
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)

    mismatched = _rows_from(DAILY_START, timedelta(days=1), N_CANON - 6, 9)
    for row in mismatched[:6]:  # corrupt the overlapping stamps' closes
        row[4] = str(float(row[4]) + 1000.0)
    fetch_fn = _fetch_override("XXBTZEUR", 1440, mismatched)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)

    assert "mismatch" in str(exc.value)
    assert "OHLCVT" not in str(exc.value)  # distinct from the window-shortfall guard


def test_seed_store_idempotent_reseed_appends_only_missing(tmp_path):
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)

    first = seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)
    assert sum(e.appended for e in first.entries) == len(first.entries) * 3

    second = seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)
    assert sum(e.appended for e in second.entries) == 0
    assert sum(e.replaced_tail_rows for e in second.entries) == 0

    ts, _ = read_store_series(store_dir, "BTC/EUR", 1440)
    assert len(ts) == N_CANON + 3  # unchanged by the second call


def test_seed_store_divergent_tail_replace_on_reseed(tmp_path):
    store_dir = tmp_path / "store"
    canonical_dir = tmp_path / "unused_canonical"  # never read: the store pre-exists for every pair

    def _poisoned_rows(interval: int) -> list[list]:
        rows = _canonical_rows(interval)
        for row in rows[N_CANON - 6 :]:  # the overlap-relevant tail (the last 6 rows) poisoned
            row[4] = str(float(row[4]) + 899.0)
        return rows

    _write_full_universe(store_dir, _poisoned_rows)

    report = seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    assert sum(e.replaced_tail_rows for e in report.entries) == len(report.entries) * 6
    assert sum(e.appended for e in report.entries) == len(report.entries) * 3

    ts, closes = read_store_series(store_dir, "BTC/EUR", 1440)
    assert closes[N_CANON - 6 : N_CANON] == [100.0 + i for i in range(N_CANON - 6, N_CANON)]  # repaired
    assert len(ts) == N_CANON + 3


def test_refresh_store_drop_rule_keeps_boundary_exact_drops_in_progress(tmp_path):
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, 1)), _store_path(store_dir, "BTC/EUR", 1440))
    write_parquet(to_frame(_rows_from(H4_START, timedelta(hours=4), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 240))

    now = H4_START + timedelta(hours=4 * 13)  # == bar[13]'s stamp == bar[12]'s interval end

    def _fetch_fn(pair_key: str, interval: int) -> list[list]:
        if interval == 1440:
            return _rows_from(DAILY_START, timedelta(days=1), 0, 1)  # matches store exactly
        return _rows_from(H4_START, timedelta(hours=4), 7, 7)  # bars 7..13

    report = refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=_fetch_fn, clock=lambda: now)

    btc_240 = next(e for e in report.entries if e.interval == 240)
    assert btc_240.appended == 3  # bars 10, 11, 12 kept; bar 13 dropped (in-progress)

    ts, _ = read_store_series(store_dir, "BTC/EUR", 240)
    assert ts[-1] == H4_START + timedelta(hours=4 * 12)  # boundary-exact bar 12 kept
    assert H4_START + timedelta(hours=4 * 13) not in ts  # bar 13 (interval end > now) dropped


def test_seed_store_names_the_canonical_when_the_copy_is_what_is_broken(tmp_path):
    """The canonical is checked before it is copied, so no broken copy is left for the next run to refuse."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    broken = _store_path(canonical_dir, "ADA/EUR", 240)
    write_parquet(read_parquet(broken).with_columns(pl.col("ts").cast(pl.Datetime("ns", "UTC"))), broken)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    assert str(broken) in str(exc.value)
    assert str(_store_path(store_dir, "ADA/EUR", 240)) not in str(exc.value)
    # A canonical is hash-attested, so "recast in place" is the wrong instruction there.
    assert "recast the column in place" not in str(exc.value)
    assert "dataset_hash" in str(exc.value) and "data rebuild ohlc-full --no-push" in str(exc.value)
    assert "nothing was copied to the store; a canonical is the data pipeline's to republish" in str(exc.value)
    assert not _store_path(store_dir, "ADA/EUR", 240).exists()  # no copy was written to be refused next round


# Each survives a `write_parquet`/`read_parquet` round trip and each then raises the same `SchemaError` at the
# same join, so the door's equality has to be exact: `ns` is what a pandas/pyarrow-written file carries.
@pytest.mark.parametrize(
    "dtype",
    [pl.Datetime("us", None), pl.Datetime("ns", "UTC"), pl.Datetime("ms", "UTC"), pl.Datetime("us", "Europe/Berlin")],
)
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_that_join_refuse_an_unjoinable_ts_column(tmp_path, reader, dtype):
    """Both readers that join. `read_store_series`' door cannot cover this: the frame meets the join first."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    # A whole seeded universe, so `seed_store` reaches the broken file by READING it, not by failing to copy.
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _store_path(store_dir, "ADA/EUR", 240)
    write_parquet(read_parquet(path).with_columns(pl.col("ts").cast(dtype)), path)
    assert read_parquet(path).schema["ts"] == dtype  # the round trip preserves it, which is why the door is needed

    with pytest.raises(EngineError) as exc:
        if reader == "refresh_store":
            refresh_store(store_dir, pairs={"ADA/EUR": "ADAEUR"}, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)
        else:
            seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert f"{reader}: {path} is not the frame the store readers join for ADA/EUR@240 -- ts is {dtype}, not " in msg
    # Pinned because an earlier wording here prescribed an in-place recast, which no other arm of the door has.
    assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    assert "any bar past the canonical's tail that REST no longer reaches" in msg
    assert "on the engine host the store is re-delivered, not seeded" in msg and "zcrypto-engine-cycle-stale" in msg
    assert "recast" not in msg


def test_refresh_store_overlap_mismatch_raises(tmp_path):
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 1440))

    mismatched = _rows_from(DAILY_START, timedelta(days=1), N_CANON - 3, 3)
    for row in mismatched:
        row[4] = str(float(row[4]) + 500.0)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: mismatched, clock=lambda: FAR_FUTURE)

    assert "mismatch" in str(exc.value)
    assert "zcrypto engine seed" in str(exc.value)


def test_refresh_store_refuses_an_absent_close_on_a_shared_stamp(tmp_path):
    """A REST null at a stamp the store holds is a disagreement the merge must not read as agreement."""
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 1440))

    rest = _rows_from(DAILY_START, timedelta(days=1), N_CANON - 3, 4)
    rest[1][4] = None
    stamp = DAILY_START + timedelta(days=N_CANON - 2)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: rest, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "overlap mismatch for BTC/EUR@1440" in msg and f"the REST fetch (first at {stamp})" in msg
    assert "absent on the REST fetch" in msg
    assert "no store repair" in msg and "zcrypto engine seed" not in msg  # the null is the fetch's, not the store's
    _, closes = read_store_series(store_dir, "BTC/EUR", 1440)
    assert closes == [100.0 + i for i in range(N_CANON)]  # nothing appended, nothing replaced


def test_seed_store_reseed_refuses_an_absent_close_and_keeps_the_store_close(tmp_path):
    """The re-seed's `allow_replace` repairs a divergent tail from REST; a REST null is not a repair."""
    store_dir = tmp_path / "store"
    canonical_dir = tmp_path / "unused_canonical"  # never read: the store pre-exists for every pair
    _write_full_universe(store_dir, _canonical_rows)

    rest = _good_rest_rows(1440)
    rest[2][4] = None
    stamp = DAILY_START + timedelta(days=N_CANON - 4)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_fetch_override("XXBTZEUR", 1440, rest), clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "overlap mismatch for BTC/EUR@1440" in msg and f"the REST fetch (first at {stamp})" in msg
    assert "absent on the REST fetch" in msg
    assert "fresh canonical copy" not in msg  # the store pre-existed: nothing was copied
    _, closes = read_store_series(store_dir, "BTC/EUR", 1440)
    assert closes[N_CANON - 4] == 100.0 + N_CANON - 4
    assert len(closes) == N_CANON


def test_refresh_store_zero_overlap_is_distinct_error(tmp_path):
    """`rest_head` (day 100) is newer than `store_tail` (day 9), so the two sides are disjoint by construction and
    the cause is ambiguous rather than a single claim of staleness: both candidates are named with a next step each,
    with the measurements an operator would read to tell them apart, and the host-routed store repair named only as
    the store-side one."""
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 1440))

    disjoint_rows = _rows_from(DAILY_START, timedelta(days=1), 100, 5)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: disjoint_rows, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "catastrophically stale" not in msg  # no longer a single unconditional claim
    assert "the venue answered with a shorter history than the seam needs" in msg
    assert "the store fell behind the REST window's reach before this run started" in msg
    assert "if the venue is the cause there is no store repair and the next run fetches again" in msg
    assert "5 completed row(s) the fetch carries" in msg  # the forming bar is already dropped
    assert f"({DAILY_START + timedelta(days=9)})" in msg  # the store's last stamp
    assert f"({DAILY_START + timedelta(days=100)})" in msg  # the fetch's oldest stamp
    assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    assert "mismatch" not in msg  # distinct from the overlap-mismatch guard


def test_refresh_store_seam_holes_names_a_step_on_each_side(tmp_path):
    """`rest_head` (day 1) is at or behind `store_tail` (day 9) and the leg clears the floor of 1, so the window is
    proven to still reach the tail and the leg's length is not the cause -- yet here the holes are the STORE's: the
    four days the fetch carries are exactly the four the store lacks. Nothing at this door measures whose holes they
    are, so the hint names both sides and a step on each, the store's being the store file's own recovery: the leg
    predates this run, so there is no canonical copy of this run's to move aside instead."""
    store_dir = tmp_path / "store"
    sparse_days = (0, 2, 4, 6, 8, 9)
    sparse_rows = [_row(DAILY_START + timedelta(days=d), 100.0 + d) for d in sparse_days]
    write_parquet(to_frame(sparse_rows), _store_path(store_dir, "BTC/EUR", 1440))

    hole_days = (1, 3, 5, 7)
    hole_rows = [_row(DAILY_START + timedelta(days=d), 100.0 + d) for d in hole_days]

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: hole_rows, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "refresh_store: window shortfall for BTC/EUR@1440 — only 0 shared stamp(s)" in msg
    assert "absent from the fetch's answer, or absent from the store leg" in msg  # both candidates, neither alone
    assert "whose own gaps can fall exactly where the fetch covers" in msg  # this very case, named
    assert "read the two sides' stamps across the span they both cover" in msg  # the reading that separates them
    assert "there is no store repair -- the next run fetches again" in msg  # the fetch-side step
    assert "catastrophically stale" not in msg
    assert (
        "and if the store leg is the holed side, on the workstation move this leg aside (outside the store) and run "
        "`zcrypto engine seed`"
    ) in msg
    assert "on the engine host the store is re-delivered, not seeded" in msg  # the store-side step is host-routed


def test_refresh_store_routes_a_shortfall_from_an_empty_fetch_to_the_fetch(tmp_path):
    """`_require_rest_frame` returns early on an empty fetch and leaves it to this arm, which a store behind the REST
    window's reach reaches too: the hint follows the cause, so an empty answer names the fetch and prescribes no
    store repair, decided before either frame's stamps are read rather than by where they sit."""
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 1440))

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: [], clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "refresh_store: window shortfall for BTC/EUR@1440 — only 0 shared stamp(s)" in msg
    assert "the REST fetch carries no completed bar, so there is no store repair" in msg
    assert "the next run fetches again" in msg
    assert "catastrophically stale" not in msg
    assert "zcrypto engine seed" not in msg and "move this leg aside" not in msg
    assert "copied into the store by this seed" not in msg  # no copy landed here: the leg predates this run
    assert read_parquet(_store_path(store_dir, "BTC/EUR", 1440)).equals(
        to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON))
    )


@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
@pytest.mark.parametrize("wreck", ["corrupt bytes", "close of strings"])
def test_the_store_readers_refuse_a_frame_they_cannot_read_or_price(tmp_path, reader, wreck):
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _store_path(store_dir, "ADA/EUR", 240)
    if wreck == "corrupt bytes":
        path.write_bytes(b"not a parquet file")
    else:
        write_parquet(read_parquet(path).with_columns(pl.col("close").cast(pl.Utf8)), path)

    with pytest.raises(EngineError) as exc:
        if reader == "refresh_store":
            refresh_store(store_dir, pairs={"ADA/EUR": "ADAEUR"}, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)
        else:
            seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    assert reader in str(exc.value) and str(path) in str(exc.value)
    assert ("cannot read" if wreck == "corrupt bytes" else "close is String, not Float64") in str(exc.value)


def test_seed_store_refuses_a_canonical_it_cannot_read_before_copying_it(tmp_path):
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    broken = _store_path(canonical_dir, "ADA/EUR", 240)
    broken.write_bytes(b"not a parquet file")

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    assert "cannot read" in str(exc.value) and str(broken) in str(exc.value)
    assert not _store_path(store_dir, "ADA/EUR", 240).exists()


# Every deviation below survives a `write_parquet`/`read_parquet` round trip, which is why the door is needed; each is
# what an operator would read off the refusal, so the cases assert the first difference by its text.
def _deviated(frame: pl.DataFrame, how: str) -> pl.DataFrame:
    stamp = frame["ts"][3]
    at_stamp = pl.col("ts") == stamp
    return {
        "open Float32": lambda: frame.with_columns(pl.col("open").cast(pl.Float32)),
        "count Int32": lambda: frame.with_columns(pl.col("count").cast(pl.Int32)),
        "close Float32": lambda: frame.with_columns(pl.col("close").cast(pl.Float32)),
        "an extra column": lambda: frame.with_columns(pl.lit(1).alias("extra")),
        "another order": lambda: frame.select(["ts", "close", "open", "high", "low", "vwap", "volume", "count"]),
        "no rows": lambda: frame.head(0),
        "a null stamp": lambda: frame.with_columns(pl.when(at_stamp).then(None).otherwise(pl.col("ts")).alias("ts")),
        "a repeated stamp": lambda: pl.concat([frame, frame.slice(3, 1)]).sort("ts"),
        "an off-grid stamp": lambda: frame.with_columns(
            pl.when(at_stamp).then(pl.col("ts") + pl.duration(minutes=7)).otherwise(pl.col("ts")).alias("ts")
        ),
        "a sub-second off-grid stamp": lambda: frame.with_columns(
            pl.when(at_stamp).then(pl.col("ts") + pl.duration(milliseconds=500)).otherwise(pl.col("ts")).alias("ts")
        ),
        "nan": lambda: frame.with_columns(pl.when(at_stamp).then(float("nan")).otherwise(pl.col("close")).alias("close")),
        "inf": lambda: frame.with_columns(pl.when(at_stamp).then(float("inf")).otherwise(pl.col("close")).alias("close")),
        "0.0": lambda: frame.with_columns(pl.when(at_stamp).then(0.0).otherwise(pl.col("close")).alias("close")),
        "-1.0": lambda: frame.with_columns(pl.when(at_stamp).then(-1.0).otherwise(pl.col("close")).alias("close")),
        "a null close": lambda: frame.with_columns(pl.when(at_stamp).then(None).otherwise(pl.col("close")).alias("close")),
    }[how]()


def _first_difference(how: str, interval: int) -> str:
    ref, step = _grid_ref(interval)
    stamp = ref + 3 * step
    return {
        "open Float32": "open is Float32, not Float64",
        "count Int32": "count is Int32, not Int64",
        "close Float32": "close is Float32, not Float64",
        "an extra column": "extra is not a column of it",
        "another order": "the columns are in another order (ts, close, open, high, low, vwap, volume, count)",
        "no rows": "it has no rows",
        "a null stamp": "ts is null in 1 row(s)",
        "a repeated stamp": "1 row(s) repeat a stamp another row carries",
        "an off-grid stamp": f"1 stamp(s) are off the {interval}-minute grid, the first {(stamp + timedelta(minutes=7)).isoformat()}",
        "a sub-second off-grid stamp": (
            f"1 stamp(s) are off the {interval}-minute grid, the first {(stamp + timedelta(milliseconds=500)).isoformat()}"
        ),
        "nan": f"close[3] at {stamp.isoformat()} is nan, not a finite positive number (1 such close(s))",
        "inf": f"close[3] at {stamp.isoformat()} is inf, not a finite positive number (1 such close(s))",
        "0.0": f"close[3] at {stamp.isoformat()} is 0.0, not a finite positive number (1 such close(s))",
        "-1.0": f"close[3] at {stamp.isoformat()} is -1.0, not a finite positive number (1 such close(s))",
    }[how]


def _deviate_store_file(store_dir: Path, symbol: str, interval: int, how: str) -> Path:
    path = _store_path(store_dir, symbol, interval)
    write_parquet(_deviated(read_parquet(path), how), path)
    return path


def _run_reader(reader: str, store_dir: Path, canonical_dir: Path, fetch_fn=_good_fetch_fn) -> None:
    if reader == "refresh_store":
        refresh_store(store_dir, pairs={"ADA/EUR": "ADAEUR"}, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)
    else:
        seed_store(store_dir, canonical_dir, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)


def _assert_store_refusal(exc: EngineError, reader: str, path: Path, interval: int, how: str) -> None:
    msg = str(exc)
    assert f"{reader}: {path} is not the frame the store readers join for ADA/EUR@{interval} -- " in msg
    assert _first_difference(how, interval) in msg
    assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    assert "any bar past the canonical's tail that REST no longer reaches" in msg
    assert "on the engine host the store is re-delivered, not seeded" in msg and "zcrypto-engine-cycle-stale" in msg
    assert "recast" not in msg


@pytest.mark.parametrize("how", ["open Float32", "count Int32", "close Float32", "an extra column", "another order"])
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_a_frame_off_the_schema(tmp_path, reader, how):
    """Each of these passes the seam and dies at `_reconcile`'s concat as a bare polars error today; the door names it."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _deviate_store_file(store_dir, "ADA/EUR", 240, how)

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir)

    _assert_store_refusal(exc.value, reader, path, 240, how)


@pytest.mark.parametrize("how", ["no rows", "a null stamp", "a repeated stamp", "an off-grid stamp", "a sub-second off-grid stamp"])
@pytest.mark.parametrize("interval", GRID_INTERVALS)
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_unsound_stamps(tmp_path, reader, interval, how):
    """No rows was the seam's shortfall; a null or repeated stamp and an interior off-grid stamp were carried into the
    store by both readers and refused later or never, so these are the frames the door newly refuses. The sub-second
    deviation is the one a grid arm read in whole seconds admits."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _deviate_store_file(store_dir, "ADA/EUR", interval, how)

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir)

    _assert_store_refusal(exc.value, reader, path, interval, how)
    assert read_parquet(path).equals(_deviated(to_frame(_canonical_rows(interval)), how))  # refused, not rewritten


@pytest.mark.parametrize("how", ["nan", "inf", "0.0", "-1.0"])
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_an_unusable_present_close(tmp_path, reader, how):
    """The predicate is the snapshot write's: a present close finite and positive. Row 3 is outside the REST overlap,
    where the seam cannot see it and the cycle's journal refused it, boundary after boundary."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _deviate_store_file(store_dir, "ADA/EUR", 240, how)

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir)

    _assert_store_refusal(exc.value, reader, path, 240, how)


@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_admit_a_null_close_at_an_unshared_stamp(tmp_path, reader):
    """A null close is an absent bar, admitted at the door as it is at the journal write; the seam refuses one on a
    SHARED stamp, and row 3 is not shared with the REST fetch."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    _deviate_store_file(store_dir, "ADA/EUR", 240, "a null close")

    _run_reader(reader, store_dir, canonical_dir)

    ts, closes = read_store_series(store_dir, "ADA/EUR", 240)
    assert closes[3] is None and len(ts) == N_CANON + 3


@pytest.mark.parametrize("how", ["an extra column", "no rows", "a null stamp", "a repeated stamp", "an off-grid stamp", "nan"])
def test_seed_store_refuses_a_deviated_canonical_before_copying_it(tmp_path, how):
    """One case per arm: the canonical is held to the whole width before the copy, named as the file that is broken,
    with the data pipeline's recovery and no store file left for the next run to refuse under the store's."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    broken = _deviate_store_file(canonical_dir, "ADA/EUR", 240, how)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert f"seed_store: {broken} is not the frame the store readers join for ADA/EUR@240 -- " in msg
    assert _first_difference(how, 240) in msg
    assert str(_store_path(store_dir, "ADA/EUR", 240)) not in msg
    assert "nothing was copied to the store; a canonical is the data pipeline's to republish" in msg
    assert "data rebuild ohlc-full --no-push" in msg and "dataset_hash" in msg
    assert "move this leg aside" not in msg and "recast the column in place" not in msg
    assert _store_path(store_dir, "ADA/EUR", 1440).exists()  # the legs before the refused one are seeded and written
    assert not _store_path(store_dir, "ADA/EUR", 240).exists()


@pytest.mark.parametrize("how", ["an off-grid stamp", "-1.0"])
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_a_rest_row_the_venue_carries(tmp_path, reader, how):
    """The door runs over the REST fetch too, before the merge: a venue row off the grid or with an unusable close
    would otherwise become resident, and the seed prescribed for the refused file would fill it back from the same
    window at every re-seed. The refusal is the venue's -- it names the fetch, not a file -- and writes nothing."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    rest = _good_rest_rows(240)
    last = len(rest) - 1  # the newest completed bar, past the store tail, so no seam arm sees it
    ref, step = _grid_ref(240)
    stamp = ref + (N_CANON + 2) * step
    if how == "an off-grid stamp":
        rest[last][0] += 7 * 60
        difference = f"1 stamp(s) are off the 240-minute grid, the first {(stamp + timedelta(minutes=7)).isoformat()}"
    else:
        rest[last][4] = "-1.0"
        difference = f"close[{last}] at {stamp.isoformat()} is -1.0, not a finite positive number (1 such close(s))"

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir, _fetch_override("ADAEUR", 240, rest))

    msg = str(exc.value)
    assert f"{reader}: the REST fetch for ADA/EUR@240 is not the frame the store readers join -- " in msg
    assert difference in msg
    assert "there is no store repair" in msg and "the next run fetches again" in msg
    assert "move this leg aside" not in msg and "zcrypto engine seed" not in msg
    path = _store_path(store_dir, "ADA/EUR", 240)
    assert read_parquet(path).equals(to_frame(_canonical_rows(240)))  # the fetch is refused, the leg as it was


def test_seed_store_refuses_a_rest_row_the_venue_carries_before_the_canonical_copy_lands(tmp_path):
    """The seed holds the fetch BEFORE the copy lands, so a refused fetch over an absent leg leaves no store file: the
    next seed still reads the leg as absent, where a canonical/REST disagreement is its data-integrity abort rather
    than a tail to replace, and the move-aside recovery is not answered by a file the operator never wrote."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    rest = _good_rest_rows(1440)
    last = len(rest) - 1  # the newest completed bar, past the canonical's tail, so no seam arm sees it
    rest[last][4] = "-1.0"
    stamp = DAILY_START + (N_CANON + 2) * timedelta(days=1)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_fetch_override("ADAEUR", 1440, rest), clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "seed_store: the REST fetch for ADA/EUR@1440 is not the frame the store readers join -- " in msg
    assert f"close[{last}] at {stamp.isoformat()} is -1.0, not a finite positive number (1 such close(s))" in msg
    assert not _store_path(store_dir, "ADA/EUR", 1440).exists()  # ADA/EUR@1440 is the first leg: nothing was copied


@pytest.mark.parametrize("fault", ["shortfall", "mismatch"])
def test_refresh_store_hints_route_the_repair_by_host(tmp_path, fault):
    """`refresh_store` runs at each boundary on the engine host, where `zcrypto engine seed` does not exist."""
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 1440))
    if fault == "shortfall":
        rest = _rows_from(DAILY_START, timedelta(days=1), 100, 5)
    else:
        rest = _rows_from(DAILY_START, timedelta(days=1), N_CANON - 3, 3)
        for row in rest:
            row[4] = str(float(row[4]) + 500.0)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: rest, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "on the engine host the store is re-delivered, not seeded" in msg and "zcrypto-engine-cycle-stale" in msg
    assert "`zcrypto engine seed` is the workstation's command" in msg
    if fault == "shortfall":
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    else:
        assert "whose re-seed over an existing file replaces the disagreeing tail inside the REST window" in msg


@pytest.mark.parametrize("side", ["store", "rest", "both", "both at one stamp"])
def test_refresh_store_routes_an_absent_close_by_the_side_that_holds_it(tmp_path, side):
    """The absent-close refusal runs whatever `allow_replace` is, so a null the store tail holds alone is a refused
    store file a plain re-seed refuses again, and a null in the REST fetch is nothing the store repairs. Under `both`
    the REST null is the earlier row, so a side or a stamp read off the first absent row alone sends the store's own
    null to the fetch's hint, at a stamp whose store close is present. Under `both at one stamp` the fetch answers the
    store's null with the same null, so the re-seed the store recovery prescribes would fill it back from this fetch
    and the next refresh would refuse it again: that one routes to the fetch."""
    store_dir = tmp_path / "store"
    rows = _rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)
    rest = _rows_from(DAILY_START, timedelta(days=1), N_CANON - 3, 4)
    if side == "store":
        rows[N_CANON - 2][4] = None
    elif side == "rest":
        rest[1][4] = None
    elif side == "both at one stamp":
        rows[N_CANON - 2][4] = None
        rest[1][4] = None
    else:
        rest[0][4] = None
        rows[N_CANON - 1][4] = None
    write_parquet(to_frame(rows), _store_path(store_dir, "BTC/EUR", 1440))
    store_stamp = DAILY_START + timedelta(days=N_CANON - 1 if side == "both" else N_CANON - 2)
    rest_stamp = DAILY_START + timedelta(days=N_CANON - 3 if side == "both" else N_CANON - 2)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: rest, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "overlap mismatch for BTC/EUR@1440" in msg
    both_sides = f"absent on the store tail (first at {store_stamp}) and the REST fetch (first at {rest_stamp})"
    if side == "rest":
        assert f"absent on the REST fetch (first at {rest_stamp})" in msg and "no store repair" in msg
        assert "move this leg aside" not in msg and "zcrypto engine seed" not in msg
    elif side == "both at one stamp":
        assert both_sides in msg and "no store repair" in msg
        assert "move this leg aside" not in msg and "zcrypto engine seed" not in msg
    else:
        assert f"the store tail (first at {store_stamp})" in msg and "a re-seed over this file refuses again" in msg
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
        assert "on the engine host the store is re-delivered, not seeded" in msg
    if side == "both":
        assert both_sides in msg
        assert "@1440 at " not in msg  # one headline stamp cannot be true of two sides absent at different rows
    _, closes = read_store_series(store_dir, "BTC/EUR", 1440)
    assert len(closes) == N_CANON  # refused, not rewritten


@pytest.mark.parametrize("case", ["existing store", "fresh copy", "fresh copy rest null"])
def test_seed_store_claims_a_fresh_copy_for_an_absent_close_only_when_it_copied(tmp_path, case):
    """Over an existing store the seed copies nothing, so its refusal of a null on the store tail must not call the
    file a fresh canonical copy: the leg is a refused store file, moved aside before the seed that does copy. On a
    fresh copy the claim holds on either side, the canonical's own null and a null the REST fetch brings."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    rest_null = case == "fresh copy rest null"

    def _nulled(interval: int) -> list[list]:
        rows = _canonical_rows(interval)
        if interval == 1440 and not rest_null:
            rows[N_CANON - 4][4] = None
        return rows

    _write_full_universe(canonical_dir, _nulled)
    if case == "existing store":
        _write_full_universe(store_dir, _nulled)
    rest = _good_rest_rows(1440)
    if rest_null:
        rest[2][4] = None
    stamp = DAILY_START + timedelta(days=N_CANON - 4)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_fetch_override("ADAEUR", 1440, rest), clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "overlap mismatch for ADA/EUR@1440" in msg
    if rest_null:
        assert f"absent on the REST fetch (first at {stamp})" in msg
        assert "this is a fresh canonical copy" in msg and "no store repair" in msg
        assert "move this leg aside" not in msg
    elif case == "existing store":
        assert f"absent on the store tail (first at {stamp})" in msg
        assert "fresh canonical copy" not in msg
        assert "the re-seed replaced nothing, because the seam refused" in msg
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    else:
        assert f"absent on the store tail (first at {stamp})" in msg
        assert "this is a fresh canonical copy" in msg and "whose copy already landed" in msg
        assert "move this leg aside (outside the store) and rebuild the set" in msg
