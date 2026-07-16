import datetime as dt

import polars as pl
import pytest

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.trades.backfill import backfill
from cli.trades.errors import TradeBackfillError
from cli.trades.gaps import detect

NOW = dt.datetime(2026, 7, 12, tzinfo=dt.UTC)
H = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)


def _rows(ids, hour=H):
    return pl.DataFrame(
        [
            {
                "ts": hour + dt.timedelta(seconds=i),
                "symbol": "BTC/EUR",
                "side": "buy",
                "price": 1.0,
                "qty": 1.0,
                "ord_type": "market",
                "trade_id": t,
            }
            for i, t in enumerate(ids)
        ],
        schema=TRADE_SCHEMA,
    )


def _write(root, ids, hour=H, pair="BTC/EUR"):
    d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y/%m/%d}"
    d.mkdir(parents=True, exist_ok=True)
    _rows(ids, hour).write_parquet(d / f"{hour:%H}.parquet")


def test_a_planted_gap_is_recovered_and_the_invariant_holds(tmp_path):
    """Known-answer proof (master plan §9): plant a gap, recover it, assert the invariant."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])  # 12,13,14 missing

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows([12, 13, 14])

    res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)
    assert res.gaps_found == 1 and res.trades_recovered == 3 and res.hours_minted == 1
    healed = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [10, 11, 12, 13, 14, 15, 16]
    assert detect(healed).gaps == []  # THE INVARIANT
    assert detect(healed).duplicate_ids == []


def test_duplicates_are_collapsed_even_with_no_gap(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 11, 12])
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([]))
    assert res.duplicates_collapsed == 1 and res.hours_minted == 1
    healed = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [10, 11, 12]
    assert detect(healed).duplicate_ids == []


def test_ids_rest_will_not_serve_are_unrecoverable_never_fabricated(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 14])  # 11,12,13 missing
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12]))  # REST serves only 12
    assert res.trades_recovered == 1 and res.trades_unrecoverable == 2
    healed = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [10, 12, 14]  # 11 and 13 are ABSENT, not invented


def test_unsettled_hours_are_never_touched(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    recent = dt.datetime(2026, 7, 11, 23, tzinfo=dt.UTC)
    _write(primary, [10, 15], hour=recent)
    res = backfill(primary, overlay, now=recent + dt.timedelta(hours=1), fetch=lambda *a, **k: _rows([]))
    assert res.gaps_found == 0 and res.hours_minted == 0
    assert not (overlay / "BTC").exists()


def test_detect_only_mints_nothing(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15])
    res = backfill(primary, overlay, now=NOW, detect_only=True, fetch=lambda *a, **k: _rows([12, 13, 14]))
    assert res.gaps_found == 1 and res.hours_minted == 0
    assert not overlay.exists() or not any(overlay.rglob("*.parquet"))


def test_a_fetch_failure_is_isolated_and_the_sweep_continues(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 15], pair="BTC/EUR")
    _write(primary, [20, 21], pair="ETH/EUR")

    def boom(pair, since, *, until=None, **kw):
        if pair == "BTC/EUR":
            raise TradeBackfillError("kraken down")
        return _rows([])

    res = backfill(primary, overlay, now=NOW, fetch=boom)
    assert len(res.errors) == 1 and res.errors[0][0] == "BTC/EUR"
    assert res.pairs == 2  # ETH still swept


def test_second_run_is_a_no_op(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])
    backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))
    res2 = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([]))
    assert res2.gaps_found == 0 and res2.hours_minted == 0


def test_raw_mirror_is_never_written(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 15])
    before = {p: p.read_bytes() for p in primary.rglob("*.parquet")}
    backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([11, 12, 13, 14]))
    assert {p: p.read_bytes() for p in primary.rglob("*.parquet")} == before
