import datetime as dt
import logging

import polars as pl
import pytest

from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA
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
    _write(primary, [20, 21, 25, 26], pair="ETH/EUR")  # 22, 23, 24 missing -- a REAL gap

    def boom(pair, since, *, until=None, **kw):
        if pair == "BTC/EUR":
            raise TradeBackfillError("kraken down")
        return _rows([22, 23, 24])

    res = backfill(primary, overlay, now=NOW, fetch=boom)
    assert len(res.errors) == 1 and res.errors[0][0] == "BTC/EUR"
    assert res.pairs == 2  # ETH still swept
    assert res.hours_minted >= 1  # ETH's recovery actually LANDED, not just counted
    healed = pl.read_parquet(overlay / "ETH" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [20, 21, 22, 23, 24, 25, 26]  # the healed ids are present


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


def test_a_wholly_missing_hour_is_healed_from_rest_alone(tmp_path):
    """A gap spanning an ENTIRELY missing hour -- a capture outage's primary scenario -- must mint a
    NEW overlay hour from the REST rows alone, not merely count them recovered and drop them."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    missing_hour = H + dt.timedelta(hours=1)
    later_hour = H + dt.timedelta(hours=2)
    _write(primary, [10, 11], hour=H)
    _write(primary, [20, 21], hour=later_hour)  # nothing written for missing_hour: 12..19 missing

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows(list(range(12, 20)), hour=missing_hour)

    res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)
    assert res.gaps_found == 1
    assert res.trades_recovered == 8
    assert res.trades_unrecoverable == 0
    assert res.hours_minted == 1
    healed = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "03.parquet")
    assert healed["trade_id"].to_list() == list(range(12, 20))
    full = pl.concat(
        [
            pl.read_parquet(primary / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet"),
            healed,
            pl.read_parquet(primary / "BTC" / "EUR" / "trades" / "2026/07/11" / "04.parquet"),
        ]
    )
    assert detect(full).gaps == []  # THE INVARIANT, across the whole pair


def test_recovered_row_in_an_unsettled_hour_is_deferred_not_dropped(tmp_path):
    """A row REST serves whose ts lands in an unsettled hour is neither minted nor counted as
    recovered: it goes to `trades_deferred`, for a later run once the hour settles."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    settled_hour = dt.datetime(2026, 7, 11, 20, tzinfo=dt.UTC)
    unsettled_hour = dt.datetime(2026, 7, 11, 23, tzinfo=dt.UTC)  # NOW - 1h: not yet 2h old
    _write(primary, [10, 14], hour=settled_hour)  # 11, 12, 13 missing

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows([12], hour=unsettled_hour)  # REST serves 12, but it lands in the fresh hour

    res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)
    assert res.gaps_found == 1
    assert res.trades_recovered == 0
    assert res.trades_deferred == 1
    assert res.trades_unrecoverable == 2  # 11 and 13: REST never even offered them
    assert res.hours_minted == 0
    assert not (overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "23.parquet").exists()


def test_d9_catches_a_mint_that_silently_did_nothing(tmp_path, monkeypatch):
    """The invariant re-check (spec 00053 D9) fires on a real violation: with `mint_hour` stubbed to
    a silent no-op the union succeeds in memory and nothing reaches disk, so the re-read of the
    settled canonical view must catch the unhealed gap instead of trusting the in-memory counters."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])  # 12,13,14 missing

    monkeypatch.setattr("cli.trades.backfill.mint_hour", lambda *a, **k: None)

    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))
    assert len(res.errors) == 1
    assert "accounting invariant violated" in res.errors[0][1]  # D9, worded without the token (operator surface)
    assert "unaccounted=3" in res.errors[0][1]
    assert not (overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet").exists()


def test_an_unreadable_segment_is_isolated_and_the_sweep_continues(tmp_path):
    """A corrupt segment for one pair -- what an rsync'd NAS mirror can produce -- becomes a per-pair
    `errors` entry while the sweep continues into another pair's real gap."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 15], pair="BTC/EUR")
    corrupt = primary / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet"
    corrupt.write_bytes(b"not a parquet file")  # truncated/bit-rotten segment
    _write(primary, [20, 21, 25, 26], pair="ETH/EUR")  # 22, 23, 24 missing -- a REAL gap

    res = backfill(primary, overlay, now=NOW, fetch=lambda pair, since, *, until=None, **kw: _rows([22, 23, 24]))
    assert len(res.errors) == 1 and res.errors[0][0] == "BTC/EUR"
    assert res.pairs == 2  # ETH still swept
    healed = pl.read_parquet(overlay / "ETH" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [20, 21, 22, 23, 24, 25, 26]


def test_a_partially_recoverable_gap_is_re_minted_fuller_on_retry(tmp_path):
    """The `replace=True` retry path: run 1 recovers what REST offers and leaves a residual gap; run
    2, with REST serving the rest, re-mints the FULLER union rather than skipping a minted hour."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 16])  # 11..15 missing

    res1 = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 14]))  # 11,13,15 still missing
    assert res1.trades_recovered == 2 and res1.trades_unrecoverable == 3
    healed1 = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed1["trade_id"].to_list() == [10, 12, 14, 16]

    res2 = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([11, 13, 15]))  # REST now has them all
    assert res2.trades_recovered == 3 and res2.trades_unrecoverable == 0
    healed2 = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed2["trade_id"].to_list() == [10, 11, 12, 13, 14, 15, 16]
    assert detect(healed2).gaps == []

    res3 = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([]))
    assert res3.gaps_found == 0 and res3.hours_minted == 0  # idempotent once fully healed


def test_detect_only_reports_missing_and_duplicate_magnitude(tmp_path):
    """detect-only is spec 00053 D11's loss report: it surfaces the DETECTOR's findings --
    `trades_missing` and `duplicate_rows_found` -- while healing nothing."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 11, 15])  # duplicate 11 (1 dup row); 12,13,14 missing (3 ids)
    res = backfill(primary, overlay, now=NOW, detect_only=True, fetch=lambda *a, **k: _rows([12, 13, 14]))
    assert res.trades_missing == 3
    assert res.duplicate_rows_found == 1
    assert res.trades_recovered == 0
    assert res.duplicates_collapsed == 0
    assert res.hours_minted == 0


def test_real_sweep_reports_found_and_landed_counters_together(tmp_path):
    """A real (--mint) sweep reports BOTH what the detector FOUND (`trades_missing`,
    `duplicate_rows_found`) and what actually LANDED (`trades_recovered`, `duplicates_collapsed`);
    recovery is deliberately partial here, so conflating the two reads differently."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 11, 16])  # duplicate 11 (1 dup row); 12,13,14,15 missing (4 ids)
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 14]))  # only 2 of 4 recovered
    assert res.trades_missing == 4
    assert res.trades_recovered == 2
    assert res.trades_unrecoverable == 2
    assert res.duplicate_rows_found == 1
    assert res.duplicates_collapsed == 1


def test_cross_hour_duplicate_is_reported_not_silently_collapsed(tmp_path):
    """A trade_id duplicated ACROSS an hour boundary (the T0026 reconnect-overwrite signature) is
    not fixable by `union_trades`, which mints per-hour -- so it must surface as a residual finding
    (`duplicates_cross_hour`), never as a `duplicates_collapsed` count that never happened."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    hour_b = H + dt.timedelta(hours=1)
    _write(primary, [10, 11, 12], hour=H)
    _write(primary, [12, 13, 14], hour=hour_b)  # id 12 duplicated across the hour boundary

    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([]))
    assert res.gaps_found == 0
    assert res.duplicates_collapsed == 0  # union_trades never even saw a per-hour duplicate
    assert res.duplicates_cross_hour == 1
    assert res.hours_minted == 0  # neither hour alone has an intra-hour duplicate to collapse


def test_fetch_failed_ids_land_in_their_own_summary_bucket(tmp_path, caplog):
    """T0078: a gap whose fetch RAISES surfaces its missing ids in the run-level
    `trades_fetch_failed` bucket, and there ONLY -- never also in `trades_unrecoverable`, which
    counts ids the fetch answered without."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 16])  # ids 12..15 missing -> 4 ids in one gap

    def boom(*a, **k):
        raise TradeBackfillError("kraken down")

    with caplog.at_level(logging.INFO, logger="zcrypto.trades.backfill"):
        res = backfill(primary, overlay, now=NOW, fetch=boom)
    assert res.trades_missing == 4  # the detector FOUND them
    assert res.trades_fetch_failed == 4  # ...and the failure is totalled, not dropped
    assert res.trades_recovered == 0
    assert res.trades_unrecoverable == 0  # no double-count: fetch never answered
    assert len(res.errors) == 1
    # The result object carrying the bucket is not enough: T0078's acceptance criterion is the
    # PRINTED summary, and there are two printers. This pins the logger line; the CLI's own
    # typer.echo is pinned in test_trades_command.py.
    summary = next(r.message for r in caplog.records if "trade backfill complete" in r.message)
    assert "fetch_failed=4" in summary


# --- the two outcomes the summary could not name (T0087, T0043) -----------------------------------


def _write_book(root, hour=H, pair="BTC/EUR", first_s=0, last_s=3599):
    """A book final for the same (pair, hour), spanning `first_s`..`last_s`. The mode it answers is
    whether the final SPANS the hour: one that merely exists proves only that a book event landed."""
    d = root / pair.split("/")[0] / pair.split("/")[1] / "book" / f"{hour:%Y/%m/%d}"
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "ts": hour + dt.timedelta(seconds=s),
                "symbol": pair,
                "type": "snapshot" if s == first_s else "update",
                "side": "bid",
                "price": 1.0,
                "qty": 1.0,
                "checksum": 1,
            }
            for s in (first_s, last_s)
        ],
        schema=BOOK_SCHEMA,
    ).write_parquet(d / f"{hour:%H}.parquet")


def test_rows_fetched_for_an_hour_whose_mint_fails_land_in_their_own_bucket(tmp_path, monkeypatch, caplog):
    """T0087: rows REST served for an hour whose mint RAISES land in `trades_mint_failed` -- not
    `recovered` (they never landed), not `unrecoverable` (REST served them), not `fetch_failed` (the
    fetch succeeded), so without their own bucket they would be printed nowhere."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])  # 12,13,14 missing

    def exploding_mint(*a, **k):
        raise OSError("no space left on device")

    monkeypatch.setattr("cli.trades.backfill.mint_hour", exploding_mint)
    with caplog.at_level(logging.INFO, logger="zcrypto.trades.backfill"):
        res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))

    assert res.trades_mint_failed == 3, "the three rows REST served and the mint dropped"
    assert res.trades_recovered == 0 and res.trades_unrecoverable == 0 and res.trades_fetch_failed == 0
    # Both printers are pinned: the result object alone cannot see a bucket dropped from the format string.
    summary = next(r.message for r in caplog.records if "trade backfill complete" in r.message)
    assert "mint_failed=3" in summary


def test_a_mint_failure_still_trips_the_accounting_invariant(tmp_path, monkeypatch):
    """The counter is REPORTED but never SUBTRACTED: a fetched-but-unminted row is retryable, so
    treating it as an explained absence would silence the sweep's strongest check on a real failure."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])

    monkeypatch.setattr("cli.trades.backfill.mint_hour", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))

    violations = [msg for _, msg in res.errors if "accounting invariant violated" in msg]
    assert violations and "unaccounted=3" in violations[0], res.errors
    assert res.trades_mint_failed == 3, "reported in full while the invariant still trips -- both halves"


def test_a_trades_hour_absent_while_its_book_sibling_survived_is_counted_when_repaired(tmp_path, caplog):
    """T0043: `is_total_loss` cannot tell a lost trades file from a quiet pair, so a repaired
    infrastructure loss left no trace. The signature that separates them: no trades final, a BOOK
    final spanning the same hour, and rows the REST tape had for it."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11], hour=H)
    _write(primary, [20, 21], hour=H + dt.timedelta(hours=2))  # brackets the hole
    _write_book(primary, hour=H + dt.timedelta(hours=1))  # the book survived the lost hour

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows([12, 13], hour=H + dt.timedelta(hours=1))

    with caplog.at_level(logging.INFO, logger="zcrypto.trades.backfill"):
        res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)

    assert res.hours_repaired_after_loss == 1, "the lost hour was repaired, and now it says so"
    assert res.hours_minted == 1 and res.trades_recovered == 2
    summary = next(r.message for r in caplog.records if "trade backfill complete" in r.message)
    assert "hours_repaired_after_loss=1" in summary
    assert any("repaired" in r.message and r.levelname == "WARNING" for r in caplog.records), "and it is loud"


def test_a_quiet_pair_with_no_book_witness_is_not_a_repaired_loss(tmp_path):
    """The false positive the signature exists to avoid: an hour with no trades final AND no book
    final is an ordinary absence with no evidence either way -- it must not be reported as a
    repaired infrastructure loss."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11], hour=H)
    _write(primary, [20, 21], hour=H + dt.timedelta(hours=2))

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows([12, 13], hour=H + dt.timedelta(hours=1))

    res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)

    assert res.hours_minted == 1 and res.trades_recovered == 2
    assert res.hours_repaired_after_loss == 0


def test_a_book_final_that_starts_mid_hour_is_not_a_witness(tmp_path):
    """The false positive our own operations produce: capture reconnects at :45, so a book final for
    the hour EXISTS while the pair was merely quiet across the connected part -- nothing was lost."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11], hour=H)
    _write(primary, [20, 21], hour=H + dt.timedelta(hours=2))
    _write_book(primary, hour=H + dt.timedelta(hours=1), first_s=2700, last_s=3599)  # reconnected at :45

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows([12, 13], hour=H + dt.timedelta(hours=1))

    res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)

    assert res.hours_minted == 1 and res.trades_recovered == 2
    assert res.hours_repaired_after_loss == 0, "a mid-hour reconnect witnesses nothing"


def test_a_book_final_that_dies_mid_hour_is_not_a_witness(tmp_path):
    """The mirror shape: the book final starts on the boundary but stops at :10, so the pair could
    have traded at :30 with nobody recording either stream."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11], hour=H)
    _write(primary, [20, 21], hour=H + dt.timedelta(hours=2))
    _write_book(primary, hour=H + dt.timedelta(hours=1), first_s=0, last_s=600)

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows([12, 13], hour=H + dt.timedelta(hours=1))

    res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)

    assert res.hours_repaired_after_loss == 0, "a stream that died at :10 witnesses nothing after it"


def test_repairing_an_hour_that_already_had_a_trades_final_is_not_a_repaired_loss(tmp_path):
    """An ordinary gap inside an hour whose file exists is a coalescing/reconnect hole, not a lost
    file -- the book witness is present for it too, so only the ABSENCE of the trades final
    separates the two cases."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])
    _write_book(primary, hour=H)

    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))

    assert res.trades_recovered == 3 and res.hours_repaired_after_loss == 0
