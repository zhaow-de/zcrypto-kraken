from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.archive import command, scan_cache
from cli.archive.pull import verify_tree
from cli.archive.settle import scan_hours
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA

H = datetime(2026, 7, 16, 9, tzinfo=UTC)
SETTLED = H + timedelta(hours=2)  # the earliest `now` at which hour H is considered
LATE = H + timedelta(hours=6)  # past the late deadline: a secondary-only hour may be minted
PAIRS = ("BTC/EUR", "ETH/EUR")


# --- fixtures: real segment trees, real parquet, real sidecars ------------------------------------


def _seg_path(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    base, quote = pair.split("/")
    return root / base / quote / kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"


def _write(root: Path, pair: str, kind: str, hour: datetime, frame: pl.DataFrame) -> Path:
    path = _seg_path(root, pair, kind, hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path, compression="zstd")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return path


def _book(pair: str, hour: datetime, rows: list[tuple[float, str]]) -> pl.DataFrame:
    """rows = [(offset_seconds, type)] — one wire message per row."""
    return pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=o) for o, _ in rows],
            "symbol": [pair] * len(rows),
            "type": [t for _, t in rows],
            "side": ["bid"] * len(rows),
            "price": [float(o) for o, _ in rows],
            "qty": [1.0] * len(rows),
            "checksum": [0] * len(rows),
        },
        schema=BOOK_SCHEMA,
    )


def _trades(pair: str, hour: datetime, ids: list[int]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=i) for i in ids],
            "symbol": [pair] * len(ids),
            "side": ["buy"] * len(ids),
            "price": [float(i) for i in ids],
            "qty": [1.0] * len(ids),
            "ord_type": ["limit"] * len(ids),
            "trade_id": ids,
        },
        schema=TRADE_SCHEMA,
    )


def _dense(seconds: range = range(0, 3600, 10)) -> list[tuple[float, str]]:
    """A healthy hour: a book message every 10 s, well under any threshold."""
    return [(float(s), "update") for s in seconds]


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    pri, sec, rec = tmp_path / "primary", tmp_path / "secondary", tmp_path / "reconciled"
    for root in (pri, sec):
        root.mkdir(parents=True, exist_ok=True)
    return pri, sec, rec


def _healthy(pri: Path, sec: Path, hour: datetime, *, pairs: tuple[str, ...] = PAIRS) -> None:
    """Both hosts recording both pairs, no gaps anywhere."""
    for pair in pairs:
        _write(pri, pair, "book", hour, _book(pair, hour, _dense()))
        _write(sec, pair, "book", hour, _book(pair, hour, _dense(range(3, 3600, 10))))


def _plant_primary_gap(pri: Path, sec: Path, hour: datetime, pair: str = "BTC/EUR") -> None:
    """The primary goes silent 600 s -> 1200 s; the secondary keeps updating through it."""
    quiet = [s for s in range(0, 3600, 10) if not 600 < s < 1200]
    _write(pri, pair, "book", hour, _book(pair, hour, [(float(s), "update") for s in quiet]))
    _write(sec, pair, "book", hour, _book(pair, hour, _dense(range(3, 3600, 10))))


def _run(args: list[str], *, now: datetime, monkeypatch) -> object:
    monkeypatch.setattr(command, "_utc_now", lambda: now)
    return CliRunner().invoke(app, ["archive", "reconcile", *args])


def _ledger(rec: Path) -> list[dict]:
    path = rec / "reconcile-ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _states(rec: Path) -> list[str]:
    return [r["state"] for r in _ledger(rec)]


def _series(textfile: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in textfile.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, _, value = line.rpartition(" ")
        out[name] = float(value)
    return out


# --- the default: detect-only ---------------------------------------------------------------------


def test_detect_only_is_the_default_and_mints_nothing(tmp_path, monkeypatch):
    """Detect-only by default so an ad-hoc run ledgers what it WOULD splice and writes no parquet;
    the deployed reconciler passes `--mint`, which is the option's own help."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    result = _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert list(rec.rglob("*.parquet")) == []  # nothing minted
    would = [r for r in _ledger(rec) if r["state"] == "would_mint"]
    assert [(r["pair"], r["kind"]) for r in would] == [("BTC/EUR", "book")]
    assert would[0]["healed_seconds"] == pytest.approx(600.0)  # 600 -> 1200, the covered silence
    assert would[0]["gaps_healed"][0]["seconds"] == pytest.approx(600.0)


def test_mint_writes_the_healed_hour_into_the_overlay(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    final = _seg_path(rec, "BTC/EUR", "book", H)
    assert final.exists()
    assert [p.name for p in sorted(rec.rglob("*.parquet"))] == ["09.parquet"]  # only the gappy pair
    assert verify_tree(rec, now=SETTLED).failed == ()  # the overlay verifies like a raw mirror
    provenance = json.loads(final.with_name("09.provenance.json").read_text())
    assert [b["source"] for b in provenance["blocks"]] == ["primary", "secondary", "primary"]
    assert _states(rec) == ["minted"]


def test_a_detect_only_rerun_never_re_ledgers_the_same_hour(tmp_path, monkeypatch):
    """The ledger is the counters' backing store AND detect-only's only output. Re-appending the same
    `would_mint` every cycle would inflate every cumulative counter by up to --window-hours."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    for _ in range(3):
        assert _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch).exit_code == 0

    assert _states(rec) == ["would_mint"]


def test_a_mint_rerun_is_a_no_op(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
    before = _seg_path(rec, "BTC/EUR", "book", H).read_bytes()
    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert _seg_path(rec, "BTC/EUR", "book", H).read_bytes() == before
    assert _states(rec) == ["minted"]


def test_a_soaked_would_mint_hour_still_mints_when_the_flag_flips(tmp_path, monkeypatch):
    """An hour already ledgered `would_mint` and still inside the window must be healed when the flag
    flips, not skipped as already-decided."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)
    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert _seg_path(rec, "BTC/EUR", "book", H).exists()
    assert _states(rec) == ["would_mint", "minted"]


# --- the settle rule ------------------------------------------------------------------------------


def test_an_hour_younger_than_the_settle_delay_is_not_considered(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    # 10:59 — hour 09 finalized at 10:00 but the pull cycle that carries it has not run yet.
    result = _run([str(pri), str(sec), str(rec)], now=H + timedelta(hours=1, minutes=59), monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert _ledger(rec) == []


def test_a_missing_primary_hour_waits_for_the_late_deadline_then_mints(tmp_path, monkeypatch):
    """Before the deadline the primary's file may still be in flight — minting a full-secondary hour
    would shadow primary data that arrives an hour later. Past it, nothing arriving can add coverage."""
    pri, sec, rec = _roots(tmp_path)
    for hour in (H - timedelta(hours=1), H + timedelta(hours=1)):
        _healthy(pri, sec, hour)  # so the absent hour is not a total_loss: the secondary HAS it
    _healthy(pri, sec, H, pairs=("ETH/EUR",))
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, _dense()))  # secondary only

    early = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
    assert early.exit_code == 0
    assert not _seg_path(rec, "BTC/EUR", "book", H).exists()
    assert _ledger(rec) == []

    late = _run([str(pri), str(sec), str(rec), "--mint"], now=LATE, monkeypatch=monkeypatch)
    assert late.exit_code == 0
    final = _seg_path(rec, "BTC/EUR", "book", H)
    assert final.exists()
    provenance = json.loads(final.with_name("09.provenance.json").read_text())
    assert [b["source"] for b in provenance["blocks"]] == ["secondary"]  # the whole hour
    assert pl.read_parquet(final).height == 360


# --- correlated loss: unconditional, never spliced -------------------------------------------------


def test_both_streams_silent_is_ledgered_paged_and_never_minted(tmp_path, monkeypatch):
    """The case the witness-based detector structurally cannot see: when BOTH streams are dark there
    is nothing to witness with. Every pair, both hosts, the same window — at depth 100 across the
    top-10 that has no benign explanation. Permanent loss: ledger it, book it as residual, never
    splice it (a correlated event hits every host at the same exchange event)."""
    pri, sec, rec = _roots(tmp_path)
    dark = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]
    for pair in PAIRS:
        _write(pri, pair, "book", H, _book(pair, H, dark))
        _write(sec, pair, "book", H, _book(pair, H, dark))

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert list(rec.rglob("*.parquet")) == []  # NEVER spliced
    silent = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert len(silent) == 1
    assert silent[0]["windows"][0]["seconds"] == pytest.approx(610.0)
    assert silent[0]["residual_seconds"] == pytest.approx(1220.0)  # 610 s x 2 dark book streams


def test_one_pair_going_quiet_alone_is_never_both_streams_silent(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    quiet = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, quiet))
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, quiet))

    result = _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert "both_streams_silent" not in _states(rec)  # ETH ticked right through it


def test_an_hour_absent_from_both_mirrors_is_a_total_loss(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H - timedelta(hours=1))
    _healthy(pri, sec, H + timedelta(hours=1))  # H itself exists nowhere

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=LATE, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert list(rec.rglob("*.parquet")) == []
    lost = [r for r in _ledger(rec) if r["state"] == "total_loss"]
    assert {(r["pair"], r["kind"]) for r in lost} == {(p, "book") for p in PAIRS}
    assert all(r["hour"] == H.isoformat() for r in lost)
    assert all(r["residual_seconds"] == 3600.0 for r in lost)
    # and the hour is NOT double-booked as both_streams_silent: no file exists to be dark
    assert "both_streams_silent" not in _states(rec)


def test_the_hours_before_a_pairs_first_capture_are_not_a_total_loss(tmp_path, monkeypatch):
    """Adding a pair to the universe must not page 46 permanent-loss alarms for the hours of the
    window that predate its first capture — nor book them into a counter that cannot be walked back."""
    pri, sec, rec = _roots(tmp_path)
    for hour in (H, H + timedelta(hours=1)):
        _healthy(pri, sec, hour, pairs=("BTC/EUR",))
    _healthy(pri, sec, H + timedelta(hours=1), pairs=("ETH/EUR",))  # ETH starts an hour late

    result = _run([str(pri), str(sec), str(rec)], now=LATE, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert _states(rec) == []


# --- trades ---------------------------------------------------------------------------------------


def test_a_primary_trade_deficit_is_unioned_and_a_secondary_one_is_only_a_qa_signal(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _write(pri, "BTC/EUR", "trades", H, _trades("BTC/EUR", H, [1, 2, 5]))
    _write(sec, "BTC/EUR", "trades", H, _trades("BTC/EUR", H, [1, 2, 3, 4, 5]))
    _write(pri, "ETH/EUR", "trades", H, _trades("ETH/EUR", H, [7, 8, 9]))
    _write(sec, "ETH/EUR", "trades", H, _trades("ETH/EUR", H, [7, 8]))  # the SECONDARY is deficient

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    btc = _seg_path(rec, "BTC/EUR", "trades", H)
    assert pl.read_parquet(btc)["trade_id"].to_list() == [1, 2, 3, 4, 5]
    assert not _seg_path(rec, "ETH/EUR", "trades", H).exists()  # a secondary deficit never mints
    by_pair = {(r["pair"], r["kind"]): r for r in _ledger(rec)}
    assert by_pair[("BTC/EUR", "trades")]["state"] == "minted"
    assert by_pair[("BTC/EUR", "trades")]["trades_added"] == 2
    assert by_pair[("ETH/EUR", "trades")]["state"] == "trade_deficit"
    assert by_pair[("ETH/EUR", "trades")]["trades_secondary_deficit"] == 1


# --- the exporter ---------------------------------------------------------------------------------


def test_the_textfile_carries_every_series_and_is_written_atomically(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)
    _write(pri, "BTC/EUR", "trades", H, _trades("BTC/EUR", H, [1, 2, 5]))
    _write(sec, "BTC/EUR", "trades", H, _trades("BTC/EUR", H, [1, 2, 3, 4, 5]))
    out = tmp_path / "textfile" / "reconcile.prom"
    out.parent.mkdir()

    result = _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(out)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    series = _series(out)
    # Name-only admission below would stay green on a gauge wired to nothing, and a zero here reads as
    # a healthy scan rather than a broken one. This pins that it carries a real measurement.
    assert float(series["zcrypto_reconcile_ledger_scan_seconds"]) > 0.0, series["zcrypto_reconcile_ledger_scan_seconds"]
    assert set(series) == {
        "zcrypto_reconcile_last_success_timestamp_seconds",
        "zcrypto_reconcile_cycle_duration_seconds",
        "zcrypto_reconcile_ledger_scan_seconds",
        'zcrypto_reconcile_source_lag_seconds{source="primary"}',
        'zcrypto_reconcile_source_lag_seconds{source="secondary"}',
        "zcrypto_reconcile_spliced_hours_total",
        "zcrypto_reconcile_union_hours_total",
        # `healable` is the gap RATE and must be non-zero in detect-only: `healed` counts only
        # minted hours, so the degrading-primary alarm would otherwise read 0 in that mode.
        "zcrypto_reconcile_healable_gap_seconds_total",
        "zcrypto_reconcile_healed_gap_seconds_total",
        "zcrypto_reconcile_residual_gap_seconds_total",
        'zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent"}',
        'zcrypto_reconcile_dark_episode_seconds_total{verdict="capture_divergent"}',
        'zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}',
        'zcrypto_reconcile_trade_deficit_rows_total{host="primary"}',
        'zcrypto_reconcile_trade_deficit_rows_total{host="secondary"}',
        "zcrypto_reconcile_trade_dedup_rows_total",
        "zcrypto_reconcile_ledger_records",
        "zcrypto_reconcile_hours_skipped",
    }
    assert series["zcrypto_reconcile_last_success_timestamp_seconds"] == SETTLED.timestamp()
    assert series["zcrypto_reconcile_spliced_hours_total"] == 1.0
    assert series["zcrypto_reconcile_union_hours_total"] == 1.0
    assert series["zcrypto_reconcile_healed_gap_seconds_total"] == pytest.approx(600.0)
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] == 0.0
    assert series['zcrypto_reconcile_trade_deficit_rows_total{host="primary"}'] == 2.0
    # both mirrors hold hour 09; `now` is 11:00 -> the newest final is 2 h old
    assert series['zcrypto_reconcile_source_lag_seconds{source="primary"}'] == 7200.0
    assert series['zcrypto_reconcile_source_lag_seconds{source="secondary"}'] == 7200.0
    assert list(out.parent.iterdir()) == [out]  # no .tmp left behind


def test_textfile_reports_cycle_duration_and_stamps_completion(tmp_path):
    start = datetime(2026, 8, 21, 8, 12, 15, tzinfo=UTC)
    ended = datetime(2026, 8, 21, 8, 35, 6, tzinfo=UTC)
    out = tmp_path / "reconcile.prom"
    command._write_textfile(
        out, now=start, ended=ended, totals=command._totals([]), lags={}, hours_skipped=0, ledger_scan_seconds=0.0
    )
    text = out.read_text()
    assert "# TYPE zcrypto_reconcile_cycle_duration_seconds gauge" in text
    assert "zcrypto_reconcile_cycle_duration_seconds 1371.0" in text
    # the success stamp is the END of the cycle, not its start (spec 00097 D1)
    assert f"zcrypto_reconcile_last_success_timestamp_seconds {ended.timestamp()}" in text
    assert f"zcrypto_reconcile_last_success_timestamp_seconds {start.timestamp()}" not in text


def test_the_cli_stamps_the_clock_read_at_the_END_of_the_cycle(tmp_path, monkeypatch):
    """The end stamp must be a SECOND clock read, taken after the work — not the start value relabelled.

    A constant `_utc_now` fake makes `ended == now`, so a regression to `ended=now` at the call site
    would ship green. This fake returns a SEQUENCE instead: `reconcile()` reads the clock exactly
    twice, and the second read must be the one that reaches the stamp.
    """
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    out = tmp_path / "reconcile.prom"
    ended = SETTLED + timedelta(seconds=1371)
    reads = iter((SETTLED, ended))
    monkeypatch.setattr(command, "_utc_now", lambda: next(reads))

    result = CliRunner().invoke(app, ["archive", "reconcile", str(pri), str(sec), str(rec), "--textfile", str(out)])

    assert result.exit_code == 0
    series = _series(out)
    assert series["zcrypto_reconcile_last_success_timestamp_seconds"] == ended.timestamp()
    assert series["zcrypto_reconcile_last_success_timestamp_seconds"] != SETTLED.timestamp()
    assert series["zcrypto_reconcile_cycle_duration_seconds"] == 1371.0
    # `now` still drives the lag arithmetic: the start read, not the end one. Both mirrors hold hour H
    # and SETTLED is H+2h, so a lag measured from `ended` would read 1371 s higher.
    assert series['zcrypto_reconcile_source_lag_seconds{source="primary"}'] == 7200.0


def test_a_half_written_textfile_is_never_published(tmp_path, monkeypatch):
    """A textfile is scraped in place: a partial write is scraped as garbage. The publish is a rename
    over a fully-written temp file in the same directory, so a scrape sees the old file or the new
    one, never half of either."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    out = tmp_path / "reconcile.prom"
    out.write_text("zcrypto_reconcile_last_success_timestamp_seconds 1\n")

    def _boom(self, *args, **kwargs):
        raise OSError("disk full mid-write")

    monkeypatch.setattr(command.Path, "write_text", _boom)  # the temp write dies half way

    result = _run([str(pri), str(sec), str(rec), "--textfile", str(out)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 1
    assert out.read_text() == "zcrypto_reconcile_last_success_timestamp_seconds 1\n"  # the old one stands


def test_the_counters_are_cumulative_across_runs(tmp_path, monkeypatch):
    """`_total` is a Prometheus COUNTER and the reconciler is a one-shot process: the only state it
    has is the ledger. A run that exported just its own cycle's numbers would reset the counter to 0
    on the next quiet hour — Prometheus reads that as a restart, and `increase()` then invents a
    permanent-loss page out of nothing. Totals are therefore derived from the whole ledger."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)
    out = tmp_path / "reconcile.prom"

    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(out)], now=SETTLED, monkeypatch=monkeypatch)
    assert _series(out)["zcrypto_reconcile_spliced_hours_total"] == 1.0

    # a later, entirely clean cycle: the counter must HOLD, not reset to this cycle's zero
    later = H + timedelta(hours=3)
    _healthy(pri, sec, H + timedelta(hours=1))
    _run(
        [str(pri), str(sec), str(rec), "--mint", "--textfile", str(out)],
        now=later + timedelta(hours=2),
        monkeypatch=monkeypatch,
    )
    series = _series(out)
    assert series["zcrypto_reconcile_spliced_hours_total"] == 1.0
    assert series["zcrypto_reconcile_healed_gap_seconds_total"] == pytest.approx(600.0)


def test_a_mirror_with_no_finals_at_all_reports_infinite_lag(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H, pairs=("BTC/EUR",))
    (sec / "BTC" / "EUR" / "book" / "2026" / "07" / "16" / "09.parquet").unlink()
    out = tmp_path / "reconcile.prom"

    result = _run([str(pri), str(sec), str(rec), "--textfile", str(out)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert _series(out)['zcrypto_reconcile_source_lag_seconds{source="secondary"}'] == float("inf")


# --- exit codes -----------------------------------------------------------------------------------


def test_an_absent_mirror_exits_two(tmp_path, monkeypatch):
    """Transport class. Silently treating an absent secondary mirror as "no witness available" would
    let the reconciler report all-clean forever while the redundancy is simply not there."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)

    assert _run([str(pri), str(tmp_path / "nope"), str(rec)], now=SETTLED, monkeypatch=monkeypatch).exit_code == 2
    assert _run([str(tmp_path / "nope"), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch).exit_code == 2


def test_an_unreadable_segment_exits_one_and_never_mints_that_hour(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)
    _seg_path(pri, "BTC/EUR", "book", H).write_bytes(b"not a parquet file")
    out = tmp_path / "reconcile.prom"

    result = _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(out)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 1
    assert not _seg_path(rec, "BTC/EUR", "book", H).exists()
    assert _states(rec) == ["failed"]
    assert not out.exists()  # a failed cycle publishes no textfile: last_success goes stale -> page


def test_a_corrupt_ledger_line_exits_one_and_never_under_counts(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    rec.mkdir(parents=True)
    (rec / "reconcile-ledger.jsonl").write_text('{"state": "minted"}\nnot json at all\n')

    result = _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 1


def test_a_non_monotonic_source_segment_is_reported_not_sorted(tmp_path, monkeypatch):
    """`_message_ts` refuses out-of-order input rather than sorting it (L2 rows carry absolute
    quantities). The command must turn that into one ledgered failure + exit 1, not a crash that
    abandons the other 47 hours of the window."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _healthy(pri, sec, H + timedelta(hours=1))
    _plant_primary_gap(pri, sec, H + timedelta(hours=1))
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, [(0, "update"), (900, "update"), (10, "update")]))

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=LATE, monkeypatch=monkeypatch)

    assert result.exit_code == 1
    failed = [r for r in _ledger(rec) if r["state"] == "failed"]
    assert [(r["pair"], r["hour"]) for r in failed] == [("BTC/EUR", H.isoformat())]
    # the healthy hour after it was still reconciled — one bad segment is not a cycle-wide outage
    assert _seg_path(rec, "BTC/EUR", "book", H + timedelta(hours=1)).exists()


def test_a_wrong_unit_ts_column_fails_that_hour_instead_of_killing_the_cycle(tmp_path, monkeypatch):
    """`us_view` guards the fleet-dark timeline, which is built in the per-hour loop with NO
    enclosing `try` of its own -- so it is called inside the read's, where the existing handler
    ledgers the failure and suppresses this hour's booking. Raised anywhere else it would abandon
    every remaining hour of the window and publish nothing: one bad segment, a dead cycle.

    Hour H is WHOLLY `ms`, deliberately. Those integers are 1000x too small for the microsecond hour
    bounds, so `fleet_dark_windows` clamps every stamp away and a healthy, dense hour reads as
    entirely dark: with the guard bypassed it books 10800.0 s -- 3600 s x 3 streams -- against a
    truth of zero. Leave ONE healthy pair in the hour and the timeline stays populated, the bypass
    books nothing at all, and the over-book assertion below never bites."""
    pri, sec, rec = _roots(tmp_path)
    bad = ("ADA/EUR", "BTC/EUR", "ETH/EUR")
    for pair in bad:
        ms = _book(pair, H, _dense()).with_columns(pl.col("ts").cast(pl.Datetime("ms", "UTC")))
        for root in (pri, sec):
            _write(root, pair, "book", H, ms)
    _healthy(pri, sec, H + timedelta(hours=1))
    _plant_primary_gap(pri, sec, H + timedelta(hours=1))

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=LATE, monkeypatch=monkeypatch)

    assert result.exit_code == 1
    # THE discriminating assertion: H is suppressed, never mis-booked. Asserted before the ledger's
    # shape because a bypass still ledgers the same three failures (from the heal path's
    # `_message_ts`, a cycle later than this guard) -- only the fabricated booking tells them apart.
    assert "both_streams_silent" not in _states(rec), "a wholly-ms hour was booked as fleet darkness"
    failed = [r for r in _ledger(rec) if r["state"] == "failed"]
    assert [(r["pair"], r["hour"]) for r in failed] == [(p, H.isoformat()) for p in bad]
    # ...and it fired at the READ, inside its try, not later in the heal path.
    assert all("book `ts` column is" in r["reason"] for r in failed)
    # ...and the cycle ran to completion: the next hour was still reconciled and minted.
    assert _seg_path(rec, "BTC/EUR", "book", H + timedelta(hours=1)).exists()


def test_infinite_source_lag_is_emitted_as_prometheus_plus_inf(tmp_path):
    """An empty mirror (no finals at all) has +Inf lag, and it MUST be spelled the Prometheus way.

    `_lag` returns `math.inf` for a mirror with zero hours, but an f-string renders it as the literal
    `inf`, which the Prometheus text format does not accept -- and node-exporter's textfile collector
    rejects the WHOLE file on one bad line, so a single infinite lag would drop EVERY
    zcrypto_reconcile_* series for that scrape. Reachable at cold bring-up or a total loss on one host
    -- exactly when source-lag most needs to fire.
    """
    import math

    from cli.archive.command import _write_textfile

    out = tmp_path / "reconcile.prom"
    _write_textfile(
        out,
        now=SETTLED,
        ended=SETTLED,
        totals=dict.fromkeys(
            (
                "spliced_hours",
                "union_hours",
                "healed_seconds",
                "healable_seconds",
                "residual_seconds",
                "deficit_primary",
                "deficit_secondary",
                "dedup_rows",
                "ledger_records",
                "dark_venue_silent",
                "dark_capture_divergent",
                "dark_undetermined",
            ),
            0.0,
        ),
        lags={"primary": math.inf, "secondary": 100.0},
        hours_skipped=0,
        ledger_scan_seconds=0.0,
    )
    text = out.read_text()

    lag_lines = [ln for ln in text.splitlines() if ln.startswith("zcrypto_reconcile_source_lag_seconds{")]
    assert 'source="primary"} +Inf' in " ".join(lag_lines), f"primary lag not +Inf: {lag_lines}"
    assert 'source="secondary"} 100.0' in " ".join(lag_lines)
    assert " inf" not in text.lower(), f"bare 'inf' would break the whole textfile: {text!r}"


def test_textfile_publishes_the_ledger_record_count(tmp_path):
    """Every reconcile counter is summed from the whole ledger, so a reset has no visible cause
    without this. It explains the silent empty-ledger path too, which a corrections counter cannot."""
    from cli.archive.command import _write_textfile

    out = tmp_path / "reconcile.prom"
    totals = dict.fromkeys(
        (
            "spliced_hours",
            "union_hours",
            "healed_seconds",
            "healable_seconds",
            "residual_seconds",
            "deficit_primary",
            "deficit_secondary",
            "dedup_rows",
            "dark_venue_silent",
            "dark_capture_divergent",
            "dark_undetermined",
        ),
        0.0,
    )
    totals["ledger_records"] = 4211
    _write_textfile(
        out,
        now=SETTLED,
        ended=SETTLED,
        totals=totals,
        lags={"primary": 0.0, "secondary": 0.0},
        hours_skipped=0,
        ledger_scan_seconds=0.0,
    )
    body = out.read_text()

    assert "# TYPE zcrypto_reconcile_ledger_records gauge" in body
    assert "zcrypto_reconcile_ledger_records 4211" in body


# --- the counters describe the OUTPUT, not the input (T0103) --------------------------------------


def _outage(pri: Path, sec: Path, hour: datetime, pair: str, *, secondary_dark: bool) -> None:
    """The primary is silent 600 s -> 1200 s. The secondary either goes dark with it and comes back
    with a 3-message tail at 1190-1192 (the correlated shape), or stays dense (an ordinary primary
    gap the secondary really does cover)."""
    _write(pri, pair, "book", hour, _book(pair, hour, [(float(s), "update") for s in range(0, 3600, 10) if not 600 < s < 1200]))
    if secondary_dark:
        stamps = sorted([s for s in range(3, 3600, 10) if not 596 < s < 1190] + [1190, 1191, 1192])
    else:
        stamps = list(range(3, 3600, 10))
    _write(sec, pair, "book", hour, _book(pair, hour, [(float(s), "update") for s in stamps]))


def test_healed_is_what_the_splice_inserted_not_the_window_it_was_admitted_on(tmp_path, monkeypatch):
    """One pair loses both mirrors while the other keeps recording, so no fleet-dark window exists to
    absorb the loss: the whole unfilled remainder is this pair's own residual."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output

    minted = [r for r in _ledger(rec) if r["state"] == "minted" and r["kind"] == "book"]
    assert len(minted) == 1, [r["state"] for r in _ledger(rec)]
    record = minted[0]
    assert record["claimed_seconds"] == pytest.approx(600.0), "the window the gap was admitted on"
    assert record["healed_seconds"] == pytest.approx(10.0), "only the 10 s after the secondary came back was covered"
    assert record["residual_seconds"] == pytest.approx(590.0), "the 590 s neither mirror held is permanent loss"
    assert sum(g["seconds"] for g in record["residual_gaps"]) == pytest.approx(590.0)
    assert "both_streams_silent" not in _states(rec), "one pair going dark alone is not a fleet outage"


def test_a_fleet_dark_window_is_never_booked_as_loss_twice(tmp_path, monkeypatch):
    """Both pairs lose both mirrors simultaneously. `both_streams_silent` already books that
    intersection into the loss counter for every stream, so the per-pair residual must book only
    what is left over -- correcting a heal over-count must not manufacture a loss over-count."""
    pri, sec, rec = _roots(tmp_path)
    for pair in PAIRS:
        _outage(pri, sec, H, pair, secondary_dark=True)

    result = _run(
        [str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch
    )
    assert result.exit_code == 0, result.output

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert len(fleet) == 1 and fleet[0]["residual_seconds"] == pytest.approx(1180.0), fleet  # 590 s x 2 streams
    minted = [r for r in _ledger(rec) if r["state"] == "minted" and r["kind"] == "book"]
    assert len(minted) == 2
    for record in minted:
        assert record["healed_seconds"] == pytest.approx(10.0)
        assert record["residual_seconds"] == pytest.approx(0.0), "every one of its 590 s is already in the fleet record"

    series = _series(tmp_path / "r.prom")
    assert series["zcrypto_reconcile_healed_gap_seconds_total"] == pytest.approx(20.0)
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(1180.0)
    # The invariant the two predicates exist to keep: per stream, nothing is claimed twice.
    assert (20.0 + 1180.0) <= 600.0 * len(PAIRS) + 1e-9


def test_the_gap_rate_still_sees_the_full_window_the_secondary_witnessed(tmp_path, monkeypatch):
    """`healable_gap_seconds_total` is the DEGRADING-PRIMARY signal, so it stays denominated in
    primary silence -- otherwise a correlated outage, which is not the primary degrading, would make
    the rate signal quieter than an ordinary one."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=False)

    result = _run([str(pri), str(sec), str(rec), "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output

    series = _series(tmp_path / "r.prom")
    assert series["zcrypto_reconcile_healable_gap_seconds_total"] == pytest.approx(600.0)
    would = [r for r in _ledger(rec) if r["state"] == "would_mint"][0]
    assert would["healed_seconds"] == pytest.approx(600.0), "a live secondary really does cover the window"
    assert would["residual_seconds"] == pytest.approx(0.0)


def test_the_provenance_sidecar_records_what_the_hour_still_lacks(tmp_path, monkeypatch):
    """The sidecar must carry the hour's measured residual: it is the cheapest audit surface there is
    -- a pure file assertion over data already on disk -- and a `residual_gaps` that is always `[]`
    claims every minted hour is complete."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    sidecar = json.loads(_seg_path(rec, "BTC/EUR", "book", H).with_name("09.provenance.json").read_text())
    assert sum(g["seconds"] for g in sidecar["residual_gaps"]) == pytest.approx(590.0), sidecar["residual_gaps"]
    assert sum(g["seconds"] for g in sidecar["gaps_healed"]) == pytest.approx(600.0), "the window it was admitted on"


def test_the_gap_rate_still_reads_the_full_window_when_the_heal_was_almost_nothing(tmp_path, monkeypatch):
    """`claimed_seconds` and `healed_seconds` must stay distinguishable in the shape that separates
    them: collapsing the rate onto the measured heal would shrink the degrading-primary signal to the
    fraction the secondary happened to cover."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)

    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)

    series = _series(tmp_path / "r.prom")
    assert series["zcrypto_reconcile_healable_gap_seconds_total"] == pytest.approx(600.0)
    assert series["zcrypto_reconcile_healed_gap_seconds_total"] == pytest.approx(10.0)


def test_the_would_mint_to_minted_flip_books_the_permanent_loss_once(tmp_path, monkeypatch):
    """Both records now carry a MEASURED residual, and the same hour is ledgered twice across the
    flip. Summed twice, the second step reads to the CRITICAL permanent-loss page as a fresh event --
    an increase, so that rule's counter-reset guard does not suppress it."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)

    _run([str(pri), str(sec), str(rec), "--textfile", str(tmp_path / "detect.prom")], now=SETTLED, monkeypatch=monkeypatch)
    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "mint.prom")], now=SETTLED, monkeypatch=monkeypatch)

    assert _states(rec) == ["would_mint", "minted"]
    assert _series(tmp_path / "detect.prom")["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(590.0)
    assert _series(tmp_path / "mint.prom")["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(590.0)


def test_a_pair_whose_mirror_arrives_after_the_fleet_decision_still_books_its_own_loss(tmp_path, monkeypatch):
    """`both_streams_silent` is decided ONCE, for the pairs present on that cycle. A pair whose files
    land later was never given a share of it, so subtracting a freshly recomputed dark window from
    its residual would delete a real loss from a total nobody ever added it to."""
    pri, sec, rec = _roots(tmp_path)
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert fleet[0]["pairs"] == ["BTC/EUR"] and fleet[0]["residual_seconds"] == pytest.approx(590.0)

    _outage(pri, sec, H, "ETH/EUR", secondary_dark=True)  # the second pair's mirrors land a cycle late
    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)

    eth = [r for r in _ledger(rec) if r["state"] == "minted" and r["pair"] == "ETH/EUR"][0]
    assert eth["residual_seconds"] == pytest.approx(590.0), "no fleet record ever booked ETH/EUR's share"
    assert _series(tmp_path / "r.prom")["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(1180.0)


def test_a_pair_that_minted_before_the_fleet_detector_ran_is_not_booked_twice(tmp_path, monkeypatch):
    """The mirror image: an unreadable segment suppresses the fleet detector for a cycle (an honest
    timeline cannot be built from it), so a pair that mints meanwhile books its residual FIRST. The
    fleet record must then book only the streams that have not already booked their own."""
    pri, sec, rec = _roots(tmp_path)
    for pair in PAIRS:
        _outage(pri, sec, H, pair, secondary_dark=True)
    _seg_path(sec, "ETH/EUR", "book", H).write_bytes(b"not a parquet")

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
    btc = [r for r in _ledger(rec) if r["state"] == "minted" and r["pair"] == "BTC/EUR"][0]
    assert btc["residual_seconds"] == pytest.approx(590.0), "nothing had booked it yet"
    assert "both_streams_silent" not in _states(rec)

    _outage(pri, sec, H, "ETH/EUR", secondary_dark=True)  # the segment is re-pulled intact
    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"][0]
    assert fleet["residual_seconds"] == pytest.approx(590.0), "BTC/EUR's 590 s was already on its own record"
    assert _series(tmp_path / "r.prom")["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(1180.0)


# --- the pair with the biggest hole and no ledger record at all (T0103) ---------------------------
#
# `secondary_covers` is False for a window whose only secondary rows are snapshots, so `find_book_gaps`
# returns [] for it -- and without the `unwitnessed` state the biggest holes are the ones that leave
# no record at all.


def _unwitnessed(pri: Path, sec: Path, hour: datetime, pair: str) -> None:
    """The primary is silent 600 s -> 1200 s; the secondary holds only SNAPSHOT rows inside it, at a
    single instant -- the post-reconnect re-snapshot, which is full state but never market activity,
    so it may not testify that anything was lost."""
    _write(pri, pair, "book", hour, _book(pair, hour, [(float(s), "update") for s in range(0, 3600, 10) if not 600 < s < 1200]))
    stamps = [(float(s), "update") for s in range(3, 3600, 10) if not 600 < s < 1200]
    stamps += [(900.0, "snapshot")] * 5  # one instant, five level-rows, zero updates
    _write(sec, pair, "book", hour, _book(pair, hour, sorted(stamps)))


def test_a_gap_no_update_witnessed_is_ledgered_instead_of_vanishing(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _unwitnessed(pri, sec, H, "BTC/EUR")

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output

    records = [r for r in _ledger(rec) if r["state"] == "unwitnessed"]
    assert len(records) == 1, _states(rec)
    assert records[0]["pair"] == "BTC/EUR"
    assert sum(g["seconds"] for g in records[0]["gaps_unwitnessed"]) == pytest.approx(600.0)
    assert not any(r["state"] == "minted" and r["pair"] == "BTC/EUR" for r in _ledger(rec)), "nothing to splice"


def test_an_unwitnessed_gap_moves_no_counter(tmp_path, monkeypatch):
    """Visibility only. Its seconds are ALREADY booked by `both_streams_silent` whenever the fleet
    was dark, so feeding a counter here would double-count them -- and when the fleet was NOT dark,
    a single pair silent on both mirrors is indistinguishable from a quiet market, which is the very
    ambiguity the fleet-wide intersection exists to resolve. So it is ledgered and never counted."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _unwitnessed(pri, sec, H, "BTC/EUR")

    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)

    series = _series(tmp_path / "r.prom")
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(0.0)
    assert series["zcrypto_reconcile_healable_gap_seconds_total"] == pytest.approx(0.0)
    assert series["zcrypto_reconcile_healed_gap_seconds_total"] == pytest.approx(0.0)


def test_a_witnessed_gap_is_not_also_reported_as_unwitnessed(tmp_path, monkeypatch):
    """The two states partition the primary's silence windows; a window that a secondary update did
    witness is healed, and must not be double-reported as invisible."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert "unwitnessed" not in _states(rec)
    assert "minted" in _states(rec)


def test_an_unwitnessed_gap_is_reported_in_detect_only_too(tmp_path, monkeypatch):
    """It is a FINDING about the archive, not a heal, so `--detect-only` must carry it -- that mode
    is the loss report."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _unwitnessed(pri, sec, H, "BTC/EUR")

    _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    assert "unwitnessed" in _states(rec)


def test_an_unwitnessed_gap_is_decided_once_not_re_ledgered_every_cycle(tmp_path, monkeypatch):
    """The hour stays in the trailing window for 48 h. Re-ledgering it each cycle would re-fire the
    finding hourly for two days about a hole nobody can do anything about."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _unwitnessed(pri, sec, H, "BTC/EUR")

    _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)
    _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    assert [r["state"] for r in _ledger(rec)].count("unwitnessed") == 1


def test_a_non_monotonic_secondary_still_fails_the_hour_instead_of_exiting_clean(tmp_path, monkeypatch):
    """The contract (`--help` and README): exit 1 on an integrity failure, a non-monotonic stream
    among them. Without the secondary's monotonicity check an hour whose only silence is UNWITNESSED
    reaches the end of the cycle, publishes a textfile and refreshes `last_success_timestamp` -- exit
    0 on a stream the archive cannot trust."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _unwitnessed(pri, sec, H, "BTC/EUR")
    rows = [(float(s), "update") for s in range(3, 3600, 10) if not 600 < s < 1200]
    rows = rows[:5] + [(rows[9][0], "update")] + rows[5:]  # a stamp reappearing after a newer one
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, rows))

    result = _run(
        [str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch
    )

    assert result.exit_code == 1, result.output
    assert any(r["state"] == "failed" and "non-monotonic" in r.get("reason", "") for r in _ledger(rec)), _states(rec)
    assert not (tmp_path / "r.prom").exists(), "no textfile on an integrity failure"


def test_the_unwitnessed_finding_is_announced_once_not_every_cycle(tmp_path, monkeypatch, caplog):
    """The ledger dedupes on its own, so the `_decided` guard's real job is the LOG: the hour stays
    in the 48 h window, and without the guard the WARNING re-fires hourly for two days about a hole
    nobody can act on. Asserting only the ledger count would pass with the guard deleted."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _unwitnessed(pri, sec, H, "BTC/EUR")

    with caplog.at_level(logging.WARNING, logger="zcrypto.archive.command"):
        _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)
        _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    announced = [r for r in caplog.records if "unwitnessed" in r.message]
    assert len(announced) == 1, [r.message for r in announced]


# --- per-intersection-window booking (T0103) -------------------------------------------------------


def _dark_from(pri: Path, sec: Path, hour: datetime, pair: str, *, quiet_from: int, quiet_to: int) -> None:
    """Both mirrors silent for this pair across [quiet_from, quiet_to); dense either side."""
    stamps = [float(s) for s in range(0, 3600, 10) if not quiet_from <= s < quiet_to]
    _write(pri, pair, "book", hour, _book(pair, hour, [(s, "update") for s in stamps]))
    _write(sec, pair, "book", hour, _book(pair, hour, [(s + 3.0, "update") for s in stamps if s + 3.0 < 3600]))


def test_each_stream_is_booked_its_own_window_not_the_intersection(tmp_path, monkeypatch):
    """BTC returns first, so it binds the intersection; ETH stays dark 200 s longer. Booking the
    intersection x 2 would charge ETH with BTC's shorter loss and lose the surplus entirely."""
    pri, sec, rec = _roots(tmp_path)
    _dark_from(pri, sec, H, "BTC/EUR", quiet_from=600, quiet_to=1200)
    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1400)

    result = _run([str(pri), str(sec), str(rec), "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"][0]
    per_stream = {p: sum(w["seconds"] for w in ws) for p, ws in fleet["stream_windows"].items()}
    # BTC: last stamp 593 (sec) -> first at 1200. ETH: 593 -> 1400.
    assert per_stream["ETH/EUR"] > per_stream["BTC/EUR"], per_stream
    assert per_stream["ETH/EUR"] - per_stream["BTC/EUR"] == pytest.approx(200.0)
    assert fleet["residual_seconds"] == pytest.approx(sum(per_stream.values()))


def test_a_streams_window_spanning_two_fleet_windows_is_booked_once(tmp_path, monkeypatch):
    """Two fleet-dark windows exist because ONE stream ticked between them. The stream that did not
    tick has a single window containing both, and summing per-window would book it twice."""
    pri, sec, rec = _roots(tmp_path)
    # BTC ticks once at 900, splitting the intersection into [600,900) and [900,1500).
    btc = [float(s) for s in range(0, 3600, 10) if not 600 <= s < 1500] + [900.0]
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, [(s, "update") for s in sorted(btc)]))
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, [(s, "update") for s in sorted(btc)]))
    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1500)  # silent across both windows

    _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"][0]
    eth = fleet["stream_windows"]["ETH/EUR"]
    assert len(eth) == 1, f"one window, not one per fleet window: {eth}"
    assert eth[0]["seconds"] < 1000.0, "the hour was not booked twice"


def test_the_healed_path_subtracts_the_stream_window_the_fleet_record_actually_booked(tmp_path, monkeypatch):
    """The attributed-exactly-once invariant. `_booked_dark` must read the per-stream window, not
    the intersection -- otherwise the wider window is booked fleet-wide and its surplus is booked
    AGAIN as the pair's own residual."""
    pri, sec, rec = _roots(tmp_path)
    _dark_from(pri, sec, H, "BTC/EUR", quiet_from=600, quiet_to=1200)
    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1400)

    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"][0]
    booked = sum(w["seconds"] for ws in fleet["stream_windows"].values() for w in ws)
    total = _series(tmp_path / "r.prom")["zcrypto_reconcile_residual_gap_seconds_total"]
    assert total == pytest.approx(booked), "every second attributed exactly once across both paths"


def test_a_pre_split_fleet_record_still_reads_as_the_intersection(tmp_path, monkeypatch):
    """The ledger is append-only. Records written before `stream_windows` existed carry only
    `windows`, and the healed path must still subtract them or it double-books history."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    # The gap must be genuinely UNFILLED or the assertion is vacuous: a fully-healed gap leaves
    # `unfilled == 0`, and the record reads 0.0 whether or not the legacy window was subtracted.
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)
    rec.mkdir(parents=True, exist_ok=True)
    legacy = {
        "state": "both_streams_silent",
        "pair": "*",
        "kind": "book",
        "hour": H.isoformat(),
        "pairs": ["BTC/EUR"],
        "residual_seconds": 590.0,
        "windows": [
            {"start": (H + timedelta(seconds=600)).isoformat(), "end": (H + timedelta(seconds=1190)).isoformat(), "seconds": 590.0}
        ],
    }
    (rec / "reconcile-ledger.jsonl").write_text(json.dumps(legacy) + "\n")

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    minted = [r for r in _ledger(rec) if r["state"] == "minted" and r["pair"] == "BTC/EUR"][0]
    assert minted["residual_gaps"], "the gap must be genuinely unfilled or this test asserts nothing"
    assert minted["residual_seconds"] == pytest.approx(0.0), "the legacy record's 590 s are still subtracted"


# --- the late-mirror trap: a per-stream window is only honest with BOTH mirrors (T0103) ------------
#
# `stream_windows` is computed from the mirrors readable THIS cycle, and the record is `_decided`
# once and never revised -- while the heal path deliberately WAITS for a late mirror. Unsynchronised,
# a stream whose second mirror lands a cycle later has its entire SINGLE-mirror silence booked as
# permanent loss, into a monotone counter that cannot be walked back. Reachable by the repo's own
# mandated pair-add order (primary first, secondary second), which creates single-mirror hours by
# construction.


def test_a_stream_missing_a_mirror_is_booked_the_intersection_not_its_own_window(tmp_path, monkeypatch):
    """The fallback that bounds the damage: without both mirrors we cannot know the stream's own
    silence, so book the intersection -- the old, bounded behaviour -- rather than a window the
    absent mirror would have shortened."""
    pri, sec, rec = _roots(tmp_path)
    # ETH has both mirrors and is dark 600->1400; BTC has both and is dark 600->1200, so the
    # intersection is [600, 1200). ADA has ONLY a primary and is quiet 600->3600.
    _dark_from(pri, sec, H, "BTC/EUR", quiet_from=600, quiet_to=1200)
    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1400)
    _write(pri, "ADA/EUR", "book", H, _book("ADA/EUR", H, [(float(s), "update") for s in range(0, 600, 10)]))

    result = _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"][0]
    per_stream = {p: sum(w["seconds"] for w in ws) for p, ws in fleet["stream_windows"].items()}
    intersection = sum(w["seconds"] for w in fleet["windows"])

    assert per_stream["ADA/EUR"] == pytest.approx(intersection), (
        f"single-mirror stream booked {per_stream['ADA/EUR']}s of its own silence instead of the "
        f"{intersection}s intersection -- an unbounded over-count into the permanent-loss counter"
    )
    assert per_stream["ETH/EUR"] > intersection, "a stream WITH both mirrors still gets its own window"


def test_a_present_but_empty_final_is_booked_the_intersection_not_the_whole_hour(tmp_path, monkeypatch):
    """Its file exists, so it evades `total_loss`; it has no stamps, so `containing_dark_window`
    would hand back the entire hour. Same root cause, same fallback."""
    pri, sec, rec = _roots(tmp_path)
    _dark_from(pri, sec, H, "BTC/EUR", quiet_from=600, quiet_to=1200)
    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1400)
    for root in (pri, sec):
        _write(root, "ADA/EUR", "book", H, _book("ADA/EUR", H, []))

    _run([str(pri), str(sec), str(rec)], now=SETTLED, monkeypatch=monkeypatch)

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"][0]
    ada = sum(w["seconds"] for w in fleet["stream_windows"].get("ADA/EUR", []))
    assert ada == pytest.approx(sum(w["seconds"] for w in fleet["windows"])), f"empty final booked {ada}s"
    assert ada < 3600.0, "the whole hour was booked for a stream we know nothing about"


def test_an_unknown_ledger_state_moves_no_counter(tmp_path, monkeypatch):
    """A ledger correction is an appended `state: "correction"` note carrying no counter field, and its
    whole safety argument is that `_totals` ignores it BY CONSTRUCTION — any record that lowered
    `healed_gap_seconds_total` would read to Prometheus as a reset and report the post-reset value as
    fresh healing, louder than the fiction it corrects. A refactor giving unknown states a default
    contribution would move a counter on such a note, with no test between it and the CRITICAL page."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    rec.mkdir(parents=True, exist_ok=True)
    note = {
        "state": "correction",
        "pair": "*",
        "kind": "book",
        "hour": H.isoformat(),
        "measured_healed_seconds": 82.955463,
        "reason": "the counters over-stated this hour before the splice was measured",
    }
    (rec / "reconcile-ledger.jsonl").write_text(json.dumps(note) + "\n")

    result = _run([str(pri), str(sec), str(rec), "--textfile", str(tmp_path / "r.prom")], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output

    series = _series(tmp_path / "r.prom")
    for name in ("healed_gap_seconds_total", "residual_gap_seconds_total", "healable_gap_seconds_total"):
        assert series[f"zcrypto_reconcile_{name}"] == pytest.approx(0.0), f"{name} moved on a note record"


def test_the_verdict_is_recorded_and_counted_while_the_booking_is_untouched(tmp_path, monkeypatch):
    """Spec 00096 D1/D4 -- the load-bearing regression, because the booking is a CONTRACT.

    Splitting an episode into two windows must not move `residual_seconds` by a single second: the
    counter derived from it is monotonic and unwalkbackable. The verdict rides ALONGSIDE, on the
    record and in its own partitioned counter, and never subtracts from residual.
    """
    pri, sec, rec = _roots(tmp_path)
    dark = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]
    for pair in PAIRS:
        _write(pri, pair, "book", H, _book(pair, H, dark))
        _write(sec, pair, "book", H, _book(pair, H, dark))
    # ONE interior event, on BTC only, written IDENTICALLY to both mirrors -- the 2026-08-20 shape.
    # It splits the fleet-dark span into TWO windows, which is the only thing that creates an
    # interior span at all; without it there is nothing for the discriminator to read.
    split = sorted(dark + [(1500.0, "update")])
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))

    # NOT caplog: cli/logging/config.py sets `propagate = False` on the `zcrypto` logger and
    # cli/__main__.py calls configure() on every CliRunner invocation, so records never reach
    # pytest's root handler. Verified -- caplog is empty here every time.
    lines: list[str] = []
    monkeypatch.setattr(command.logger, "error", lambda fmt, *a, **k: lines.append(fmt % a))
    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    silent = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert len(silent) == 1
    record = silent[0]

    # (a) THE CONTRACT: the booked seconds are IDENTICAL to the single-window case in
    #     test_both_streams_silent_is_ledgered_paged_and_never_minted, even though the episode now
    #     books as two windows instead of one -- BTC books 310+300, ETH books its containing 610
    #     once. Splitting an episode must not move the counter.
    assert record["residual_seconds"] == pytest.approx(1220.0)
    assert [w["seconds"] for w in record["windows"]] == [pytest.approx(310.0), pytest.approx(300.0)]

    # (b) the verdict and its evidence are on the DURABLE record, not only in a log line
    assert record["verdict"] == "venue_silent"
    assert record["pairs_agreeing"] == 1
    assert record["divergent_pairs"] == []

    # (c) the key set is pinned EXACTLY: the record gains these keys and nothing else.
    assert set(record) == {
        "at",
        "state",
        "pair",
        "kind",
        "hour",
        "pairs",
        "windows",
        "stream_windows",
        "residual_seconds",
        "verdict",
        "interior_updates",
        "interior_snapshots",
        "interior_seconds",
        "pairs_agreeing",
        "pairs_skipped",
        "divergent_pairs",
    }

    # (d) the operator's log line carries it too -- that is the 3am path
    line = next(m for m in lines if "both_streams_silent" in m)
    assert "verdict=venue_silent" in line


def test_the_dark_episode_counter_partitions_the_booked_seconds(tmp_path, monkeypatch):
    """D4 -- the metric checks itself: the three label values sum to exactly the
    `both_streams_silent` seconds, so a classification bug cannot quietly lose or duplicate time.

    And it is a PARALLEL VIEW: residual_gap still books every second, so venue_silent <= residual.
    """
    pri, sec, rec = _roots(tmp_path)
    dark = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]
    for pair in PAIRS:
        _write(pri, pair, "book", H, _book(pair, H, dark))
        _write(sec, pair, "book", H, _book(pair, H, dark))
    split = sorted(dark + [(1500.0, "update")])
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))

    textfile = tmp_path / "reconcile.prom"
    result = _run(
        [str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)],
        now=SETTLED,
        monkeypatch=monkeypatch,
    )
    assert result.exit_code == 0
    series = _series(textfile)

    booked = sum(v for k, v in series.items() if k.startswith("zcrypto_reconcile_dark_episode_seconds_total{"))
    assert booked == pytest.approx(1220.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent"}'] == pytest.approx(1220.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="capture_divergent"}'] == pytest.approx(0.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}'] == pytest.approx(0.0)
    # the parallel-view invariant: residual books everything, and never less than the classified part
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] >= booked


def test_a_record_written_before_the_discriminator_existed_counts_as_undetermined(tmp_path, monkeypatch):
    """D4a. A record written before the discriminator existed carries no `verdict`, and `_decided`
    prevents re-deciding it. The counter must NEVER retroactively claim knowledge the
    system did not have -- a verdict-less record is `undetermined`, not `venue_silent`.
    """
    pri, sec, rec = _roots(tmp_path)
    rec.mkdir(parents=True, exist_ok=True)
    legacy = {
        "at": "2026-08-06T09:12:00+00:00",
        "state": "both_streams_silent",
        "pair": "*",
        "kind": "book",
        "hour": "2026-08-06T07:00:00+00:00",
        "pairs": ["BTC/EUR"],
        "windows": [{"start": "2026-08-06T07:01:02+00:00", "end": "2026-08-06T07:18:18+00:00", "seconds": 1036.0}],
        "residual_seconds": 1036.0,
    }
    (rec / "reconcile-ledger.jsonl").write_text(json.dumps(legacy) + "\n")

    textfile = tmp_path / "reconcile.prom"
    result = _run([str(pri), str(sec), str(rec), "--textfile", str(textfile)], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0
    series = _series(textfile)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}'] == pytest.approx(1036.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent"}'] == pytest.approx(0.0)


def test_an_unrecognized_verdict_string_counts_as_undetermined_not_a_crash(tmp_path, monkeypatch):
    """An UNRECOGNIZED verdict, not a missing one. The ledger is append-only and outlives any single
    image version -- widen the verdict vocabulary later, then roll back to this code (a normal
    operation -- `.claude/skills/zcrypto-rollout-image/SKILL.md`'s `Ops converges` makes it a
    re-converge to the recorded digest), and it must not crash-loop indexing a `dark_<verdict>` key
    that does not exist. An unknown verdict is bucketed as `undetermined`, same as no verdict at
    all -- not silently dropped, which would break the three-label partition of the booked seconds.
    """
    pri, sec, rec = _roots(tmp_path)
    rec.mkdir(parents=True, exist_ok=True)
    future = {
        "at": "2026-09-01T09:12:00+00:00",
        "state": "both_streams_silent",
        "pair": "*",
        "kind": "book",
        "hour": "2026-09-01T07:00:00+00:00",
        "pairs": ["BTC/EUR"],
        "windows": [{"start": "2026-09-01T07:01:02+00:00", "end": "2026-09-01T07:18:18+00:00", "seconds": 1036.0}],
        "residual_seconds": 1036.0,
        "verdict": "venue_silent_likely",  # a value a NEWER image wrote, unknown to this code
    }
    (rec / "reconcile-ledger.jsonl").write_text(json.dumps(future) + "\n")

    textfile = tmp_path / "reconcile.prom"
    result = _run([str(pri), str(sec), str(rec), "--textfile", str(textfile)], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output  # never a KeyError abort on a rollback
    series = _series(textfile)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}'] == pytest.approx(1036.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent"}'] == pytest.approx(0.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="capture_divergent"}'] == pytest.approx(0.0)


# --- the settled-hour skip cache (spec 00097 D4/D5) ------------------------------------------------

CACHE = "scan-cache.json"
# Three consecutive hours, and four cycle clocks at which every one of them is both SETTLED (+2 h)
# and past the late deadline (+6 h). A window of exactly-three-late-hours does not exist: the newest
# settled hour is only 2 h old, so the newest four window hours are never late.
HOURS3 = (H, H + timedelta(hours=1), H + timedelta(hours=2))
N1 = H + timedelta(hours=9)
N2 = N1 + timedelta(hours=1)
N3 = N1 + timedelta(hours=2)
N4 = N1 + timedelta(hours=3)


def _three_healthy_hours(pri: Path, sec: Path) -> None:
    """Three consecutive healthy hours — the k=2 audit arithmetic needs THREE skippable hours before
    a single one is ever skipped (3 skippable − 2 audited = 1)."""
    for hour in HOURS3:
        _healthy(pri, sec, hour)


def _entries(rec: Path) -> dict[str, dict]:
    return json.loads((rec / CACHE).read_text())["hours"]


def _info(monkeypatch) -> list[str]:
    """NOT caplog: `cli/logging/config.py` sets `propagate = False` on the `zcrypto` logger during the
    first CliRunner invoke, so capture is order-dependent and a negative assertion passes vacuously."""
    lines: list[str] = []
    monkeypatch.setattr(command.logger, "info", lambda fmt, *a, **k: lines.append(fmt % a))
    return lines


def _complete(lines: list[str]) -> str:
    matches = [line for line in lines if line.startswith("reconcile complete")]
    assert len(matches) == 1, lines
    return matches[0]


def _stamps(rec: Path) -> dict[str, str]:
    entries = _entries(rec)
    return {hour.isoformat(): entries[hour.isoformat()]["examined_at"] for hour in HOURS3}


def test_second_cycle_skips_settled_hours_and_first_does_not(tmp_path, monkeypatch):
    """The optimization itself. A first cycle has no cache and skips nothing; the second skips the
    hours the audit did not claim — and an examined hour and a skipped hour must decide the same
    thing, which for a healthy hour is nothing at all."""
    pri, sec, rec = _roots(tmp_path)
    _three_healthy_hours(pri, sec)
    lines = _info(monkeypatch)

    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N1, monkeypatch=monkeypatch).exit_code == 0

    assert _complete(lines).endswith("skipped=0 audited=0")
    first = _entries(rec)
    assert [first[h.isoformat()]["examined_at"] for h in HOURS3] == [N1.isoformat()] * 3
    assert all(first[h.isoformat()]["late_at_exam"] and first[h.isoformat()]["complete"] for h in HOURS3)
    assert _ledger(rec) == []

    lines.clear()
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N2, monkeypatch=monkeypatch).exit_code == 0

    assert _complete(lines).endswith("skipped=1 audited=2")
    assert _ledger(rec) == []  # a skipped hour and an audited hour alike decide nothing new
    # Durable proof of WHICH hours moved: the two oldest were audited (equal `examined_at` from
    # cycle 1, tie broken by hour ascending), the newest was skipped and carried forward untouched.
    assert _stamps(rec) == {
        HOURS3[0].isoformat(): N2.isoformat(),
        HOURS3[1].isoformat(): N2.isoformat(),
        HOURS3[2].isoformat(): N1.isoformat(),
    }


def test_changed_file_reexamines(tmp_path, monkeypatch):
    """The fingerprint is the whole safety argument: touch the final of the hour cycle 2 would have
    skipped and it is examined in full instead."""
    pri, sec, rec = _roots(tmp_path)
    _three_healthy_hours(pri, sec)
    lines = _info(monkeypatch)
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N1, monkeypatch=monkeypatch).exit_code == 0

    os.utime(_seg_path(pri, "BTC/EUR", "book", HOURS3[2]), ns=(0, 0))
    lines.clear()
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N2, monkeypatch=monkeypatch).exit_code == 0

    assert _complete(lines).endswith("skipped=0 audited=2")  # only two remain skippable, the audit takes both
    assert _stamps(rec) == {h.isoformat(): N2.isoformat() for h in HOURS3}


def test_non_late_hour_is_never_cached(tmp_path, monkeypatch):
    """An hour past SETTLE but before LATE is still awaiting a possibly-arriving primary: its
    examination is provisional, so it is recorded `late_at_exam=False` and never skipped."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    early, later = H + timedelta(hours=4), H + timedelta(hours=5)  # settled at +2 h, late only at +6 h

    assert _run([str(pri), str(sec), str(rec), "--mint"], now=early, monkeypatch=monkeypatch).exit_code == 0

    entry = _entries(rec)[H.isoformat()]
    assert entry["late_at_exam"] is False and entry["complete"] is True

    lines = _info(monkeypatch)
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=later, monkeypatch=monkeypatch).exit_code == 0

    assert _complete(lines).endswith("skipped=0 audited=0")
    assert _entries(rec)[H.isoformat()]["examined_at"] == later.isoformat()


def test_audit_divergence_drops_cache_and_logs_error(tmp_path, monkeypatch):
    """The net under the fingerprint model. The audit re-examines a hour the cache called settled; if
    that examination decides ANYTHING, the model failed somewhere and the whole cache is dropped —
    a wrongly-skipped hour is permanent loss nothing downstream would ever detect.

    Deleting the ledger is the cheapest constructible divergence; the mechanism is generic."""
    pri, sec, rec = _roots(tmp_path)
    dark = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]
    for pair in PAIRS:
        _write(pri, pair, "book", H, _book(pair, H, dark))
        _write(sec, pair, "book", H, _book(pair, H, dark))

    # Cycle 1 DECIDES the hour, so it is deliberately not cached. Cycle 2 re-examines it, decides
    # nothing new, and caches it.
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N1, monkeypatch=monkeypatch).exit_code == 0
    assert "both_streams_silent" in _states(rec)
    assert H.isoformat() not in _entries(rec)  # an hour THIS cycle changed is never cached
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N2, monkeypatch=monkeypatch).exit_code == 0
    assert _entries(rec)[H.isoformat()]["examined_at"] == N2.isoformat()

    (rec / "reconcile-ledger.jsonl").unlink()
    errors: list[str] = []
    monkeypatch.setattr(command.logger, "error", lambda fmt, *a, **k: errors.append(fmt % a))

    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N3, monkeypatch=monkeypatch).exit_code == 0

    assert [e for e in errors if "scan-cache audit divergence" in e and H.isoformat() in e]
    assert not (rec / CACHE).exists()  # the WHOLE cache, not just the divergent hour


def test_corrupt_cache_is_a_full_cycle(tmp_path, monkeypatch):
    """Every cache failure is fail-open to a slow full cycle, never to a wrong skip."""
    pri, sec, rec = _roots(tmp_path)
    _three_healthy_hours(pri, sec)
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N1, monkeypatch=monkeypatch).exit_code == 0

    (rec / CACHE).write_text("{ this is not json")
    lines = _info(monkeypatch)
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N2, monkeypatch=monkeypatch).exit_code == 0

    assert _complete(lines).endswith("skipped=0 audited=0")
    assert _stamps(rec) == {h.isoformat(): N2.isoformat() for h in HOURS3}  # and a valid cache is rewritten


def test_detect_only_neither_reads_nor_writes_the_cache(tmp_path, monkeypatch):
    """Spec D4's mode gate. A detect-only run's verdicts are not the deployed cycle's, so one must
    never be able to make a `--mint` cycle skip an hour it owes a heal."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _plant_primary_gap(pri, sec, H)

    # "neither loads, saves, fingerprints NOR audits": the audit is the one of the four with no file
    # of its own to observe, so it is counted directly. (c) below is its true positive -- a zero that
    # only ever reads zero would pass with the counter wired to nothing.
    picks: list[int] = []
    real_pick = scan_cache.pick_audit_hours

    def _counting_pick(*args, **kwargs):
        picks.append(1)
        return real_pick(*args, **kwargs)

    monkeypatch.setattr(scan_cache, "pick_audit_hours", _counting_pick)

    # (a) a detect-only cycle writes no cache at all
    assert _run([str(pri), str(sec), str(rec)], now=N1, monkeypatch=monkeypatch).exit_code == 0
    assert not (rec / CACHE).exists()
    assert picks == []
    assert _states(rec) == ["would_mint"]

    # (b) a cache that WOULD mark the hour skippable is ignored. Salted `mint=False` deliberately:
    #     the mode gate is then the ONLY thing between this entry and a skipped hour, so a future
    #     change that drops the gate but keeps the salt fails here.
    scans = {
        src: {kind: scan_hours(root, kind) for kind in ("book", "trades")} for src, root in (("primary", pri), ("secondary", sec))
    }
    fingerprint, complete = scan_cache.hour_fingerprint(
        H,
        scans=scans,
        primary_root=pri,
        secondary_root=sec,
        reconciled_root=rec,
        book_pairs=sorted(PAIRS),
        trade_pairs=[],
    )
    assert complete
    (rec / CACHE).write_text(
        json.dumps(
            {
                "algo": scan_cache.algo_salt(30.0, mint=False),
                "hours": {
                    H.isoformat(): {
                        "fingerprint": fingerprint,
                        "examined_at": N1.isoformat(),
                        "late_at_exam": True,
                        "failures": 0,
                        "complete": True,
                    }
                },
            }
        )
    )
    seeded = (rec / CACHE).read_bytes()
    (rec / "reconcile-ledger.jsonl").unlink()  # so a re-examination is observable

    assert _run([str(pri), str(sec), str(rec)], now=N2, monkeypatch=monkeypatch).exit_code == 0

    assert _states(rec) == ["would_mint"]  # examined: the seeded entry was never consulted
    assert (rec / CACHE).read_bytes() == seeded  # nor rewritten
    assert picks == []  # nor audited

    # (c) and the follow-up minting cycle mints the hour, seeded cache and all
    assert _run([str(pri), str(sec), str(rec), "--mint"], now=N3, monkeypatch=monkeypatch).exit_code == 0
    assert _seg_path(rec, "BTC/EUR", "book", H).exists()
    assert "minted" in _states(rec)
    assert picks == [1]  # the true positive: a minting cycle DOES audit, so the zeros above are real


def test_the_skip_gauge_counts_what_the_loop_did_not_what_it_planned(tmp_path, monkeypatch):
    """The cache degrades SILENTLY -- `complete` demands every tree-wide pair on both mirrors, so a
    pair dropped from capture drives the skip rate to zero permanently with no error. This gauge is
    the only Prometheus-side observable of that, and it is incremented INSIDE the skip branch, never
    published from `len(skip_hours)`: with the skip branch disabled, the plan-derived count still
    reads 1, so a gauge carrying that arithmetic would report an engaged cache while every hour was
    in fact re-examined -- exactly the reading the runbook's `skipped=0` triage exists to trust."""
    pri, sec, rec = _roots(tmp_path)
    _three_healthy_hours(pri, sec)
    first, second = tmp_path / "first.prom", tmp_path / "second.prom"

    args = [str(pri), str(sec), str(rec), "--mint"]
    assert _run([*args, "--textfile", str(first)], now=N1, monkeypatch=monkeypatch).exit_code == 0
    assert _series(first)["zcrypto_reconcile_hours_skipped"] == 0.0  # no cache yet: nothing to skip

    assert _run([*args, "--textfile", str(second)], now=N2, monkeypatch=monkeypatch).exit_code == 0
    assert _series(second)["zcrypto_reconcile_hours_skipped"] == 1.0  # 3 skippable - 2 audited


def test_a_detect_only_cycle_publishes_the_skip_gauge_at_zero(tmp_path, monkeypatch):
    """Every mode publishes it. An omitted series is NoData, which on the board is indistinguishable
    from a cycle that never ran -- and a detect-only run legitimately skips nothing (spec D4)."""
    pri, sec, rec = _roots(tmp_path)
    _three_healthy_hours(pri, sec)
    out = tmp_path / "detect.prom"

    assert _run([str(pri), str(sec), str(rec), "--textfile", str(out)], now=N1, monkeypatch=monkeypatch).exit_code == 0
    assert _series(out)["zcrypto_reconcile_hours_skipped"] == 0.0


def test_the_audited_hours_rotate_across_cycles(tmp_path, monkeypatch):
    """`pick_audit_hours` rotates on `examined_at`, while spec D5 describes LRU on a `last_audited`.
    The substitution is correct ONLY because an audited hour is FULLY examined and therefore restamped.
    If a future change ever carried an audited hour's OLD entry forward, the same two hours would be
    audited every cycle forever and the divergence net would cover 2 of ~48 window hours."""
    pri, sec, rec = _roots(tmp_path)
    _three_healthy_hours(pri, sec)

    audited: list[set[str]] = []
    for now in (N1, N2, N3, N4):
        assert _run([str(pri), str(sec), str(rec), "--mint"], now=now, monkeypatch=monkeypatch).exit_code == 0
        audited.append({hour for hour, at in _stamps(rec).items() if at == now.isoformat()})

    h0, h1, h2 = (h.isoformat() for h in HOURS3)
    assert audited == [{h0, h1, h2}, {h0, h1}, {h0, h2}, {h0, h1}]  # cycle 1 examines all three
    assert set().union(*audited[1:]) == {h0, h1, h2}  # every hour swept within three audited cycles
