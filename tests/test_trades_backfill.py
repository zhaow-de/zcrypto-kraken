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
    """A gap spanning an ENTIRELY missing hour -- a capture outage's primary scenario -- must mint
    a NEW overlay hour from the REST rows alone, not just count them recovered and drop them
    (there is no `frames[h]` entry for an hour with no canonical file at all)."""
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
    """A row REST would serve, but whose ts falls in an hour that hasn't settled (hour + 2h > now),
    must be neither minted (the settle rule stays) nor reported as recovered -- it lands in the
    honest `trades_deferred` bucket: fetched, not yet landed, for a later run to pick up once the
    hour settles."""
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
    """The invariant re-check (D9) must FIRE on a real violation, not just stay quiet on a clean
    sweep. Stub `mint_hour` to silently no-op -- simulating "reported recovery it never performed",
    the exact bug class this branch shipped once -- so the union succeeds in memory but nothing is
    ever published to disk. D9 re-reads the settled canonical view from disk, so it must catch the
    unhealed gap and log/record it, rather than let the in-memory counters report a false success."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])  # 12,13,14 missing

    monkeypatch.setattr("cli.trades.backfill.mint_hour", lambda *a, **k: None)

    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))
    assert len(res.errors) == 1
    assert "accounting invariant violated" in res.errors[0][1]  # D9, worded without the token (operator surface)
    assert "unaccounted=3" in res.errors[0][1]
    assert not (overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet").exists()


def test_an_unreadable_segment_is_isolated_and_the_sweep_continues(tmp_path):
    """A corrupt/bit-rotten segment (exactly what an rsync'd NAS mirror can produce) for one pair
    must not abort the whole pass: it becomes a per-pair `errors` entry, and the sweep continues to
    heal a real gap in another pair."""
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
    """The `replace=True` retry path: run 1 recovers what REST offers, leaving a residual gap
    (`trades_unrecoverable`); run 2, with REST now serving the rest, must re-mint the FULLER union,
    not skip the hour because it was already minted once."""
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
    """detect-only is spec 00053 D11's loss report: it must surface the DETECTOR's findings --
    `trades_missing` and `duplicate_rows_found` -- even though nothing is healed in this mode.
    `trades_recovered` and `duplicates_collapsed` must stay 0: detect-only heals nothing."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 11, 15])  # duplicate 11 (1 dup row); 12,13,14 missing (3 ids)
    res = backfill(primary, overlay, now=NOW, detect_only=True, fetch=lambda *a, **k: _rows([12, 13, 14]))
    assert res.trades_missing == 3
    assert res.duplicate_rows_found == 1
    assert res.trades_recovered == 0
    assert res.duplicates_collapsed == 0
    assert res.hours_minted == 0


def test_real_sweep_reports_found_and_landed_counters_together(tmp_path):
    """A real (--mint) sweep must report BOTH what the detector FOUND (`trades_missing`,
    `duplicate_rows_found`) and what actually LANDED (`trades_recovered`, `duplicates_collapsed`).
    Only partial recovery here, so found (4 missing) != landed (2 recovered) -- a mutation that
    conflates the found-counter with the landed-counter is caught."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 11, 16])  # duplicate 11 (1 dup row); 12,13,14,15 missing (4 ids)
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 14]))  # only 2 of 4 recovered
    assert res.trades_missing == 4
    assert res.trades_recovered == 2
    assert res.trades_unrecoverable == 2
    assert res.duplicate_rows_found == 1
    assert res.duplicates_collapsed == 1


def test_cross_hour_duplicate_is_reported_not_silently_collapsed(tmp_path):
    """A trade_id duplicated ACROSS an hour boundary (the T0026 reconnect-overwrite signature)
    cannot be fixed by `union_trades`, which mints per-hour -- neither hour alone contains a
    duplicate. That is fine, but it must surface as a residual finding (`duplicates_cross_hour`),
    never as a `duplicates_collapsed` count that didn't actually happen."""
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
    """T0078: a gap whose fetch RAISES must surface its missing ids in the run-level
    `trades_fetch_failed` bucket — before this, they landed in no printed bucket at all
    (the per-gap `continue` skipped even the unrecoverable accounting), so README's
    "a run can never read as clean by omitting one" was false for exactly this class.
    The ids must appear in fetch_failed ONLY — not double-counted into unrecoverable."""
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
    # The RESULT carrying the bucket is not enough: T0078's acceptance criterion is the printed
    # summary, and there are two printers. This pins the logger line; the CLI's own typer.echo is
    # pinned separately in test_trades_command.py. Caught at review — without this, deleting
    # `fetch_failed=%d` from the format string left all 20 tests green.
    summary = next(r.message for r in caplog.records if "trade backfill complete" in r.message)
    assert "fetch_failed=4" in summary


# --- the two outcomes the summary could not name (T0087, T0043) -----------------------------------


def _write_book(root, hour=H, pair="BTC/EUR", first_s=0, last_s=3599):
    """A book final for the same (pair, hour). The witness is that it SPANS the hour — a final that
    merely exists proves only that one book event landed somewhere in it, which a capture restart
    at :45 produces too (and our own image converges restart capture)."""
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
    """T0087: the mint's `except ... continue` isolates a bad hour but also skips the recovered
    tally, so rows the REST really served were counted in NO printed bucket -- not `recovered`
    (they never landed), not `unrecoverable` (REST served them), not `fetch_failed` (the fetch
    succeeded). The run is never silently clean, but the number was visible only inside the
    invariant-violation message."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])  # 12,13,14 missing

    def exploding_mint(*a, **k):
        raise OSError("no space left on device")

    monkeypatch.setattr("cli.trades.backfill.mint_hour", exploding_mint)
    with caplog.at_level(logging.INFO, logger="zcrypto.trades.backfill"):
        res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))

    assert res.trades_mint_failed == 3, "the three rows REST served and the mint dropped"
    assert res.trades_recovered == 0 and res.trades_unrecoverable == 0 and res.trades_fetch_failed == 0
    # Two printers, both pinned: T0078's review found that deleting a bucket from the logger's
    # format string left every test green because only the result object was asserted.
    summary = next(r.message for r in caplog.records if "trade backfill complete" in r.message)
    assert "mint_failed=3" in summary


def test_a_mint_failure_still_trips_the_accounting_invariant(tmp_path, monkeypatch):
    """The decision behind the new counter: it is REPORTED but never SUBTRACTED. A fetched-but-
    unminted row is retryable -- the next run re-detects and re-fetches it -- so treating it as an
    explained absence would make the strongest check in the sweep go quiet on a real failure."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])

    monkeypatch.setattr("cli.trades.backfill.mint_hour", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))

    violations = [msg for _, msg in res.errors if "accounting invariant violated" in msg]
    assert violations and "unaccounted=3" in violations[0], res.errors
    assert res.trades_mint_failed == 3, "reported in full while the invariant still trips -- both halves"


def test_a_trades_hour_absent_while_its_book_sibling_survived_is_counted_when_repaired(tmp_path, caplog):
    """T0043: `is_total_loss` classifies a both-mirrors trades loss as "nobody traded" (a quiet pair
    genuinely prints nothing for an hour), and the REST backfill then repairs it SILENTLY -- so a
    real infrastructure loss left no operator-visible trace of ever having happened. The signature
    that distinguishes the two: no trades final, a BOOK final for the same hour proving the
    connection was alive, and rows the REST tape had for it."""
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
    """The false positive the mere-existence check could not see, and the one our own operations
    produce: capture is down for part of the hour and reconnects at :45, so a book final for that
    hour EXISTS while the pair was simply quiet across the connected part. Nothing was lost, and a
    counter whose entire purpose is loss attribution must not say otherwise."""
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
