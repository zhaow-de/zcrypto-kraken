"""TDD for `cli/archive/replay.py` — the canonical book continuity-replay driver (spec 00051 OPS-3).

Scope (finalized 2026-07-15, T0045): the archive stores price/qty as Float64, so the Kraken CRC is
NOT byte-exact re-derivable — the stored `checksum` column is trusted as capture-time ground truth
and is never compared against a re-derived one, and no "structural desync" heuristic exists (for a
depth-bounded book a legitimate out-of-window update is indistinguishable from corruption without
the CRC). What IS proven, per canonical hour: it opens with a snapshot, rows are ts-ordered, every
message carries a checksum attestation, and the rows regroup + replay through `OrderBook` without a
structural throw.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.archive import replay as replay_module
from cli.archive.checkpoint import CheckpointWriteError
from cli.archive.replay import Census, EvictionRefusedError, ReplayResult, regroup_messages, replay_segment, verify_replay
from cli.capture.segment_writer import BOOK_SCHEMA

H = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)


def _explode(pair: str, hour: datetime, messages: list[dict]) -> pl.DataFrame:
    """Fan each WS-shaped message out into one row per price level, exactly as the capture writer
    does (cli/capture/command.py:146-158): bids first, then asks, all rows sharing the message's
    `(ts, type, checksum)`."""
    rows = []
    for msg in messages:
        ts = hour + timedelta(seconds=msg["offset"])
        for side, levels in (("bid", msg.get("bids", [])), ("ask", msg.get("asks", []))):
            for price, qty in levels:
                rows.append(
                    {
                        "ts": ts,
                        "symbol": pair,
                        "type": msg["type"],
                        "side": side,
                        "price": price,
                        "qty": qty,
                        "checksum": msg.get("checksum", 1),
                    }
                )
    return pl.DataFrame(rows, schema=BOOK_SCHEMA)


def _book(root: Path, pair: str, hour: datetime, frame: pl.DataFrame) -> Path:
    """Write a committed canonical final (+ manifest sidecar) at the archive layout."""
    base, quote = pair.split("/")
    p = root / base / quote / "book" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(p, compression="zstd")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_name(p.name + ".sha256").write_text(f"{digest}  {p.name}\n")
    return p


def _coherent_messages() -> list[dict]:
    """One snapshot then three coherent updates — a replayable hour."""
    return [
        {
            "offset": 0,
            "type": "snapshot",
            "bids": [(100.0, 1.0), (99.0, 2.0)],
            "asks": [(101.0, 1.0), (102.0, 2.0)],
            "checksum": 11,
        },
        {"offset": 10, "type": "update", "bids": [(100.0, 0.5)], "asks": [], "checksum": 12},
        {"offset": 20, "type": "update", "bids": [], "asks": [(101.0, 0.0)], "checksum": 13},
        {"offset": 30, "type": "update", "bids": [(98.0, 3.0)], "asks": [(103.0, 1.5)], "checksum": 14},
    ]


# --- regroup: the exact inverse of the capture writer's per-level fan-out -------------------------


def test_regroup_reconstructs_ws_messages_in_order() -> None:
    frame = _explode(
        "BTC/EUR",
        H,
        [
            {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0), (99.0, 2.0)], "asks": [(101.0, 3.0)], "checksum": 7},
            {"offset": 5, "type": "update", "bids": [(100.0, 0.0)], "asks": [], "checksum": 8},
        ],
    )

    messages = regroup_messages(frame)

    assert len(messages) == 2
    first, second = messages
    assert first["type"] == "snapshot"
    assert first["checksum"] == 7
    assert first["bids"] == [{"price": 100.0, "qty": 1.0}, {"price": 99.0, "qty": 2.0}]
    assert first["asks"] == [{"price": 101.0, "qty": 3.0}]
    assert second["type"] == "update"
    assert second["checksum"] == 8
    assert second["bids"] == [{"price": 100.0, "qty": 0.0}]
    assert second["asks"] == []


# --- replay_segment: happy path --------------------------------------------------------------------


def test_replay_segment_happy_path(tmp_path: Path) -> None:
    frame = _explode("BTC/EUR", H, _coherent_messages())
    path = _book(tmp_path, "BTC/EUR", H, frame)

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.pair == "BTC/EUR"
    assert result.hour == H
    assert result.rows == frame.height
    assert result.messages == 4
    assert result.anchored is True
    assert result.ts_ordered is True
    assert result.checksum_present is True
    assert result.replay_ok is True
    assert result.error is None


# --- replay_segment: anomalies ----------------------------------------------------------------------


def test_missing_leading_snapshot_is_flagged(tmp_path: Path) -> None:
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.anchored is False
    # anchoring is its own verdict: updates onto an empty book are structurally fine
    assert result.replay_ok is True
    assert result.error is None


def test_unreadable_parquet_is_isolated_not_raised(tmp_path: Path) -> None:
    path = tmp_path / "BTC" / "EUR" / "book" / "2026" / "07" / "14" / "02.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a parquet file")

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.error is not None
    assert result.replay_ok is False


def test_out_of_order_ts_is_flagged(tmp_path: Path) -> None:
    messages = [
        {"offset": 10, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 11},
        {"offset": 5, "type": "update", "bids": [(100.0, 0.5)], "asks": [], "checksum": 12},
    ]
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.ts_ordered is False
    assert result.anchored is True  # the first message is still a snapshot


def test_null_checksum_is_flagged(tmp_path: Path) -> None:
    messages = _coherent_messages()
    messages[2]["checksum"] = None
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.checksum_present is False
    # a missing attestation is not a structural failure: the replay itself still runs
    assert result.replay_ok is True


def test_structural_ingest_throw_fails_replay(tmp_path: Path) -> None:
    messages = _coherent_messages()
    messages[1]["bids"] = [(None, 0.5)]  # a null price level: OrderBook's level parse raises
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.replay_ok is False
    assert result.error is not None
    assert result.anchored is True  # the independent checks still report honestly


# --- verify_replay: the sweep -----------------------------------------------------------------------


def test_verify_replay_isolates_a_bad_hour_and_continues(tmp_path: Path) -> None:
    # The corrupt hour comes FIRST in the (pair, hour)-sorted sweep, so this proves a later good
    # hour still proceeds past it — not merely that the sweep survives a bad hour at the end.
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H + timedelta(hours=1), _explode("BTC/EUR", H + timedelta(hours=1), _coherent_messages()))
    corrupt = primary / "BTC" / "EUR" / "book" / f"{H:%Y}" / f"{H:%m}" / f"{H:%d}" / f"{H.hour:02d}.parquet"
    corrupt.write_bytes(b"junk")

    results = verify_replay(primary, None, depth=10)

    assert len(results) == 2
    by_hour = {r.hour: r for r in results}
    assert by_hour[H].error is not None
    assert by_hour[H + timedelta(hours=1)].error is None and by_hour[H + timedelta(hours=1)].replay_ok is True


def test_verify_replay_filters_pair_and_since(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    for pair in ("BTC/EUR", "ETH/EUR"):
        for hour in (H, H + timedelta(hours=1)):
            _book(primary, pair, hour, _explode(pair, hour, _coherent_messages()))

    only_btc = verify_replay(primary, None, pair="BTC/EUR", depth=10)
    assert {r.pair for r in only_btc} == {"BTC/EUR"} and len(only_btc) == 2

    only_late = verify_replay(primary, None, since=H + timedelta(hours=1), depth=10)
    assert {r.hour for r in only_late} == {H + timedelta(hours=1)} and len(only_late) == 2


def test_verify_replay_reads_reconciled_first(tmp_path: Path) -> None:
    primary, reconciled = tmp_path / "primary", tmp_path / "reconciled"
    # the primary's hour is NOT snapshot-anchored; the reconciled overlay's healed hour is
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))
    _book(reconciled, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    results = verify_replay(primary, reconciled, depth=10)

    assert len(results) == 1
    assert results[0].anchored is True  # the overlay hour won, reconciled-first


# --- verify_replay: chain-anchored semantics (spec 00052 D3 correction) ------------------------------


def test_verify_replay_chain_anchors_an_update_opening_hour_after_a_clean_predecessor(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))  # H: snapshot-anchored, clean
    h1 = H + timedelta(hours=1)
    _book(primary, "BTC/EUR", h1, _explode("BTC/EUR", h1, _coherent_messages()[1:]))  # h1: update-opening only

    results = verify_replay(primary, None, depth=10)

    by_hour = {r.hour: r for r in results}
    assert by_hour[H].anchored is True
    assert by_hour[h1].anchored is True  # chained via H: contiguous, and H is itself anchored + error-free


def test_verify_replay_chain_anchoring_breaks_across_a_canonical_gap(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))  # H: snapshot-anchored
    h2 = H + timedelta(hours=2)  # H+1 is MISSING from the archive -- a canonical gap
    _book(primary, "BTC/EUR", h2, _explode("BTC/EUR", h2, _coherent_messages()[1:]))  # h2: update-opening only

    results = verify_replay(primary, None, depth=10)

    by_hour = {r.hour: r for r in results}
    assert by_hour[H].anchored is True
    assert by_hour[h2].anchored is False  # h2's exact predecessor (h1) is absent from the enumeration


def test_verify_replay_first_hour_of_a_pair_update_opening_is_not_anchored(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))  # no snapshot, no predecessor at all

    results = verify_replay(primary, None, depth=10)

    assert len(results) == 1
    assert results[0].anchored is False


# --- the CLI command ---------------------------------------------------------------------------------


def test_cli_verify_replay_clean_tree_exits_zero(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    result = CliRunner().invoke(app, ["archive", "verify-replay", str(primary)])

    assert result.exit_code == 0, result.output
    assert "1 ok, 0 failed" in result.output


def test_cli_verify_replay_failing_hour_exits_nonzero(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))  # not anchored

    result = CliRunner().invoke(app, ["archive", "verify-replay", str(primary)])

    assert result.exit_code == 1, result.output
    assert "FAILED" in result.output


def test_cli_verify_replay_failed_hour_logs_at_warning_not_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A failed hour is a finding about DATA; the sweep reporting it is the program working.
    `Ops · ERROR logs` fires on any ops ERROR within 15 minutes, so logging findings at ERROR pages
    nightly, forever, for an hour that is already triaged -- the third channel spec 00077 exists to
    close. Restoring `logger.error` here silently re-arms that page."""
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))  # not anchored

    # The CLI's root callback (`cli/__main__.py`) runs `cli.logging.config.configure` on every
    # invocation, which sets `propagate = False` on the "zcrypto" logger. `caplog` only auto-attaches
    # its capture handler to a logger that is ALREADY non-propagating when the fixture sets up
    # (`_pytest.logging.catching_logs`), so a session whose first-ever CLI call is this very test
    # would otherwise capture nothing. Attach the handler to "zcrypto" directly so the assertion
    # holds regardless of test order/selection -- Logger.callHandlers always invokes a visited
    # ancestor's own handlers en route up the chain, independent of that ancestor's own propagate flag.
    zcrypto_logger = logging.getLogger("zcrypto")
    zcrypto_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="zcrypto.archive.command"):
            result = CliRunner().invoke(app, ["archive", "verify-replay", str(primary)])
    finally:
        zcrypto_logger.removeHandler(caplog.handler)

    assert result.exit_code == 1, result.output
    findings = [r for r in caplog.records if "hour failed" in r.message]
    assert len(findings) == 1, [r.message for r in caplog.records]
    assert findings[0].levelno == logging.WARNING
    assert not any(r.levelno == logging.ERROR for r in caplog.records)


# --- the CLI command: incremental mode (spec 00078) ---------------------------------------------


def _invoke(*args: str):
    return CliRunner().invoke(app, ["archive", "verify-replay", *args])


def _summary_withheld(output: str) -> bool:
    """Neither summary surface present.

    The runner decides "did the sweep complete" by whether it can `sed` a `failed=` out of the
    output, and BOTH summary lines are in that output (the logger's stdout handler writes into the
    same stream `typer.echo` does). Printing either on a run that did not genuinely complete makes a
    broken sweep read as `run_ok=1`, and nothing pages.
    """
    return "verify-replay complete" not in output and not any(line.startswith("replayed ") for line in output.splitlines())


def test_state_dir_with_pair_is_refused(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))
    state = tmp_path / "state"

    result = _invoke(str(primary), "--state-dir", str(state), "--pair", "BTC/EUR")

    assert result.exit_code != 0, result.output
    assert "--state-dir" in result.output and "--pair" in result.output
    assert not state.exists()  # refused before anything is enumerated or written


def test_state_dir_with_since_is_refused(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))
    state = tmp_path / "state"

    result = _invoke(str(primary), "--state-dir", str(state), "--since", "2026-07-14")

    assert result.exit_code != 0, result.output
    assert "--state-dir" in result.output and "--since" in result.output
    assert not state.exists()


def test_reverify_all_requires_state_dir(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    result = _invoke(str(primary), "--reverify-all")

    assert result.exit_code != 0, result.output
    assert "--reverify-all" in result.output and "--state-dir" in result.output


def test_census_line_and_frozen_summary_both_emitted(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))
    state = tmp_path / "state"

    result = _invoke(str(primary), "--state-dir", str(state))

    assert result.exit_code == 0, result.output
    prefix = "verify-replay census replayed=1 reused=0 audited=0 mismatches=0 pending=0 evicted=0 duration_s="
    lines = result.output.splitlines()
    echoed = [line for line in lines if line.startswith(prefix)]
    logged = [line for line in lines if prefix in line and not line.startswith(prefix)]
    assert len(echoed) == 1, lines
    assert len(logged) == 1, lines  # the runner parses the LOG line; both surfaces must carry it
    assert echoed[0].removeprefix(prefix).isdigit()  # duration_s is an integer, never a float repr
    # The `00077` summary pair, byte-frozen: `failed=`/`hours=` are what the runner seds out.
    assert "verify-replay complete hours=1 ok=1 failed=0" in result.output
    assert "replayed 1 hour(s): 1 ok, 0 failed" in result.output
    assert "anchored=" not in result.output  # the per-hour `ok` lines are gone in incremental mode


def test_audit_mismatch_withholds_summary_and_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))
    passing = ReplayResult("BTC/EUR", H, 8, 4, True, True, True, True, None)
    # Sample order, which varies across seeds -- the operator must read the same run twice the same way.
    census = Census(
        replayed=0,
        reused=2,
        audited=2,
        audit_mismatches=("ETH/EUR 2026-07-14 03:00", "BTC/EUR 2026-07-14 02:00"),
        pending=0,
        evicted=0,
        duration_s=1.0,
    )
    monkeypatch.setattr(replay_module, "verify_replay_incremental", lambda *a, **k: ([passing], census))

    result = _invoke(str(primary), "--state-dir", str(tmp_path / "state"))

    assert result.exit_code == 2, result.output
    assert _summary_withheld(result.output)
    assert "verify-replay census replayed=0 reused=2 audited=2 mismatches=2 pending=0 evicted=0 duration_s=1" in result.output
    assert "ETH/EUR 2026-07-14 03:00" in result.output and "BTC/EUR 2026-07-14 02:00" in result.output
    assert result.output.index("BTC/EUR 2026-07-14 02:00") < result.output.index("ETH/EUR 2026-07-14 03:00")


def test_audit_mismatch_outranks_failing_hours(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run holding BOTH a failing hour and an audit mismatch exits 2 with the summary withheld, not
    1 with it published. The counts a summary carries are derived from a cache the audit has just
    proven unreliable, so publishing them would set `run_ok=1` over exactly that -- while the failing
    hour still gets its line, since the runbook sends the operator to the journal for identities."""
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))
    failing = ReplayResult("ETH/EUR", H, 0, 0, False, False, False, False, "ComputeError: not a parquet file")
    census = Census(
        replayed=1,
        reused=2,
        audited=2,
        audit_mismatches=("BTC/EUR 2026-07-14 02:00",),
        pending=0,
        evicted=0,
        duration_s=1.0,
    )
    monkeypatch.setattr(replay_module, "verify_replay_incremental", lambda *a, **k: ([failing], census))

    result = _invoke(str(primary), "--state-dir", str(tmp_path / "state"))

    # The summary is asserted FIRST: it is the signal the runner reads, and the regression this test
    # exists for -- letting the failing-hour `Exit(1)` win -- publishes it. The exit code is secondary.
    assert _summary_withheld(result.output), result.output
    assert result.exit_code == 2, result.output
    assert "ETH/EUR  2026-07-14 02:00  FAILED" in result.output
    assert "BTC/EUR 2026-07-14 02:00" in result.output


def test_eviction_refusal_withholds_summary_and_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    def _refuse(*args, **kwargs):
        raise EvictionRefusedError("refusing to evict 9 of 10 checkpointed hours")

    monkeypatch.setattr(replay_module, "verify_replay_incremental", _refuse)

    result = _invoke(str(primary), "--state-dir", str(tmp_path / "state"))

    assert result.exit_code == 2, result.output
    assert _summary_withheld(result.output)
    assert "verify-replay census" not in result.output
    assert "refusing to evict 9 of 10 checkpointed hours" in result.output


def test_checkpoint_write_error_withholds_summary_and_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    def _unwritable(*args, **kwargs):
        raise CheckpointWriteError("failed to write checkpoint to /state: Read-only file system")

    monkeypatch.setattr(replay_module, "verify_replay_incremental", _unwritable)

    result = _invoke(str(primary), "--state-dir", str(tmp_path / "state"))

    assert result.exit_code == 2, result.output
    assert _summary_withheld(result.output)
    assert "verify-replay census" not in result.output
    assert "failed to write checkpoint to /state" in result.output


def test_empty_tree_with_state_dir_emits_no_census_and_no_summary(tmp_path: Path) -> None:
    """spec 00078 D7/F3: an unmounted NAS resolves to an empty directory. A census of `hours=0` there
    would parse, so the runner would set `run_ok=1` and nobody would be paged."""
    primary = tmp_path / "primary"
    primary.mkdir()
    state = tmp_path / "state"

    result = _invoke(str(primary), "--state-dir", str(state))

    assert result.exit_code == 0, result.output
    assert "no canonical book hours found" in result.output
    assert "verify-replay census" not in result.output
    assert _summary_withheld(result.output)
    assert not (state / "checkpoint.parquet").exists()


def test_currently_failing_cached_hour_is_still_printed(tmp_path: Path) -> None:
    """A failing hour must keep appearing every night, archive-wide: the runbook sends the operator to
    the journal for the failing hours' identities, so an old one must not go quiet just because it is
    no longer news."""
    primary = tmp_path / "primary"
    state = tmp_path / "state"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))
    broken = _book(primary, "ETH/EUR", H, _explode("ETH/EUR", H, _coherent_messages()))
    broken.write_bytes(b"not a parquet file")  # unreadable -> a cached FAILURE, never trusted from cache

    first = _invoke(str(primary), "--state-dir", str(state))
    assert first.exit_code == 1, first.output

    second = _invoke(str(primary), "--state-dir", str(state))

    assert second.exit_code == 1, second.output
    assert "ETH/EUR  2026-07-14 02:00  FAILED" in second.output
    assert "BTC/EUR" not in second.output  # a passing hour prints no line
    assert "verify-replay census replayed=1 reused=1 audited=1 mismatches=0 pending=0 evicted=0 duration_s=" in second.output
    assert "verify-replay complete hours=2 ok=1 failed=1" in second.output


def test_without_state_dir_output_is_unchanged(tmp_path: Path) -> None:
    """The no-`--state-dir` path is the ad-hoc operator tool and is byte-identical to today."""
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    result = _invoke(str(primary))

    assert result.exit_code == 0, result.output
    assert "BTC/EUR  2026-07-14 02:00  ok  anchored=True ordered=True checksum=True replay=True rows=8 msgs=4" in result.output
    assert "replayed 1 hour(s): 1 ok, 0 failed" in result.output
    assert "verify-replay complete hours=1 ok=1 failed=0" in result.output
    assert "census" not in result.output
