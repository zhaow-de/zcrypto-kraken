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
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)

    disjoint_rows = _rows_from(DAILY_START, timedelta(days=1), 50, 9)  # zero overlap w/ canonical i=0..9
    fetch_fn = _fetch_override("XXBTZEUR", 1440, disjoint_rows)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)

    assert "OHLCVT" in str(exc.value)
    assert "shortfall" in str(exc.value)


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
    assert "then promote the verified sibling into the canonical name" in str(exc.value)
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

    assert reader in str(exc.value) and str(path) in str(exc.value)
    # Pinned because the earlier wording here pinned a data-loss instruction.
    assert 'recast the column in place (`pl.col("ts").cast(pl.Datetime("us", "UTC"))`)' in str(exc.value)
    assert "copy the file aside (outside the dataset root)" in str(exc.value)
    assert "a re-seed refuses this file" in str(exc.value)
    assert (
        "drops every bar the canonical lacks unless the re-seed's seam holds -- six shared stamps into the canonical "
        "and every shared close equal"
    ) in str(exc.value)


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
    assert f"overlap mismatch for BTC/EUR@1440 at {stamp}" in msg
    assert "absent on the REST fetch" in msg
    assert "zcrypto engine seed" in msg
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
    assert f"overlap mismatch for BTC/EUR@1440 at {stamp}" in msg
    assert "absent on the REST fetch" in msg
    _, closes = read_store_series(store_dir, "BTC/EUR", 1440)
    assert closes[N_CANON - 4] == 100.0 + N_CANON - 4
    assert len(closes) == N_CANON


def test_refresh_store_zero_overlap_is_distinct_error(tmp_path):
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 1440))

    disjoint_rows = _rows_from(DAILY_START, timedelta(days=1), 100, 5)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: disjoint_rows, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "catastrophically stale" in msg
    assert "mismatch" not in msg  # distinct from the overlap-mismatch guard


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
    assert ("cannot read" if wreck == "corrupt bytes" else "types close as") in str(exc.value)


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
