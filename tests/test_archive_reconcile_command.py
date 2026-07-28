from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.archive import command
from cli.archive.pull import verify_tree
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
    """The load-bearing default. `--min-gap-seconds` is not yet validated cross-host (T0039): the
    measured single-host max natural quiescence is 14.78 s and one secondary update row is enough to
    witness, so a coalescing artifact could trip a phantom splice — an unaudited data swap into an
    unbackfillable archive. Detect-only ledgers what it WOULD do and writes no parquet."""
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
    `would_mint` every cycle would inflate every cumulative counter by up to --window-hours and bias
    T0039's soak distribution toward the hours that sat in the window longest."""
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
    """T0039's end state: the soak ledgers `would_mint`, the threshold is pinned, the operator flips
    to --mint. Hours still inside the window must be healed, not skipped as already-decided."""
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
    assert set(series) == {
        "zcrypto_reconcile_last_success_timestamp_seconds",
        'zcrypto_reconcile_source_lag_seconds{source="primary"}',
        'zcrypto_reconcile_source_lag_seconds{source="secondary"}',
        "zcrypto_reconcile_spliced_hours_total",
        "zcrypto_reconcile_union_hours_total",
        # `healable` is the gap RATE, and it must be non-zero in detect-only: `healed` counts only
        # minted hours, and minting stays off for the whole T0039 soak, so the degrading-primary
        # alarm would be pinned at 0 exactly when it is most needed.
        "zcrypto_reconcile_healable_gap_seconds_total",
        "zcrypto_reconcile_healed_gap_seconds_total",
        "zcrypto_reconcile_residual_gap_seconds_total",
        'zcrypto_reconcile_trade_deficit_rows_total{host="primary"}',
        'zcrypto_reconcile_trade_deficit_rows_total{host="secondary"}',
        "zcrypto_reconcile_trade_dedup_rows_total",
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


def test_infinite_source_lag_is_emitted_as_prometheus_plus_inf(tmp_path):
    """An empty mirror (no finals at all) has +Inf lag, and it MUST be spelled the Prometheus way.

    `_lag` returns math.inf for a mirror with zero hours, and the exporter's own comment says that
    "+Inf trips the source-lag rule". But an f-string renders math.inf as the literal `inf`, which the
    Prometheus text format does not accept -- and node-exporter's textfile collector rejects the WHOLE
    file on one bad line, so a single infinite lag would drop EVERY zcrypto_reconcile_* series for that
    scrape. Reachable at cold bring-up (a mirror that exists but has not committed a final yet) or a
    total loss on one host -- exactly when source-lag most needs to fire.
    """
    import math

    from cli.archive.command import _write_textfile

    out = tmp_path / "reconcile.prom"
    _write_textfile(
        out,
        now=SETTLED,
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
            ),
            0.0,
        ),
        lags={"primary": math.inf, "secondary": 100.0},
    )
    text = out.read_text()

    lag_lines = [ln for ln in text.splitlines() if ln.startswith("zcrypto_reconcile_source_lag_seconds{")]
    assert 'source="primary"} +Inf' in " ".join(lag_lines), f"primary lag not +Inf: {lag_lines}"
    assert 'source="secondary"} 100.0' in " ".join(lag_lines)
    assert " inf" not in text.lower(), f"bare 'inf' would break the whole textfile: {text!r}"


# --- the counters describe the OUTPUT, not the input (T0103) --------------------------------------
#
# The 2026-07-27 07:00 UTC blackout: both mirrors went dark together and the secondary contributed
# only its post-resubscribe tail. `healed_seconds` was the full window WIDTH, admitted on one
# secondary update anywhere inside it, so the ledger claimed 2,311.536587 s healed against
# 82.955463 s actually spliced -- and the alert that reads it told an operator "every gap was
# covered" for 24 h. These two tests are that shape, and both fail against the pre-fix wiring.


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
    """`residual_gaps` was a literal `[]` at every mint call, so every provenance file on the NAS
    claims a complete hour. The sidecar is the cheapest audit surface there is -- a pure file
    assertion over data already on disk -- and it is worthless while it always says the same thing."""
    pri, sec, rec = _roots(tmp_path)
    _healthy(pri, sec, H)
    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    sidecar = json.loads(_seg_path(rec, "BTC/EUR", "book", H).with_name("09.provenance.json").read_text())
    assert sum(g["seconds"] for g in sidecar["residual_gaps"]) == pytest.approx(590.0), sidecar["residual_gaps"]
    assert sum(g["seconds"] for g in sidecar["gaps_healed"]) == pytest.approx(600.0), "the window it was admitted on"


def test_the_gap_rate_still_reads_the_full_window_when_the_heal_was_almost_nothing(tmp_path, monkeypatch):
    """`claimed_seconds` and `healed_seconds` must stay distinguishable in the shape that separates
    them: collapsing the rate onto the measured heal would drop the real event's degrading-primary
    signal from 2,311 s to 83 s."""
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
# ADA/EUR lost 208.566668 s in the 2026-07-27 blackout -- the largest hole in the canonical archive
# for that hour -- and produced NO record. Its secondary held 200 rows inside the gap, every one a
# `snapshot` at a single timestamp and not one an `update`, so `secondary_covers` was False,
# `find_book_gaps` returned [] and the `if not gaps: continue` path wrote nothing.


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
    among them. When the unwitnessed split dropped the secondary's monotonicity check, an hour whose
    only silence was UNWITNESSED reached the end of the cycle, published a textfile and refreshed
    `last_success_timestamp` -- exit 0 on a stream the archive cannot trust."""
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
