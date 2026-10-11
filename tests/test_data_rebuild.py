"""Tests for `cli.data.rebuild` (spec 00056 D3): the sibling-minting rebuild orchestration. The
builders are monkeypatched into `rebuild.REBUILDABLE` so these tests stay hermetic."""

import hashlib
import json
import os
import re
import tomllib
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.costs.spread import effective_spread_bps
from cli.data import rebuild
from cli.data.errors import DataSyncError
from cli.data.rolling import RollingError
from cli.universe.rules import DEFAULT_MAX_SPREAD_BPS, SPREAD_REFERENCE_NOTIONAL_EUR
from tests.rolling_fixtures import SEAM, line_bytes, write_chain

_FIXTURES = Path(__file__).parent / "fixtures"
_ASSETPAIRS = json.loads((_FIXTURES / "kraken_assetpairs.json").read_text())
_ASSETS = json.loads((_FIXTURES / "kraken_assets.json").read_text())


def _fake_fetch_public(endpoint: str) -> dict:
    return _ASSETPAIRS if endpoint == "AssetPairs" else _ASSETS


def _write_daily(path: Path, *, vwap: float, volume: float, n: int = 30, last: date = date(2026, 7, 18)) -> None:
    # Real UTC daily timestamps ending at `last`, not range(n): the freshness guard reads the
    # dataset's newest bar, and an integer ts cannot express staleness at all (T0093).
    frame = pl.DataFrame(
        {
            "ts": [datetime.combine(last - timedelta(days=n - 1 - i), time(), tzinfo=UTC) for i in range(n)],
            "open": [vwap] * n,
            "high": [vwap] * n,
            "low": [vwap] * n,
            "close": [vwap] * n,
            "vwap": [vwap] * n,
            "volume": [volume] * n,
            "count": [1] * n,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def test_rebuild_mints_sibling_and_dispatches(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: calls.append(out) or (out / "ok").write_text("x"))
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    minted = rebuild.rebuild_sets(["ohlc-full"], ctx)
    assert minted == [tmp_path / "ohlc-full-20260718"] == calls
    assert (tmp_path / "ohlc-full-20260718/ok").exists()


def test_rebuild_refuses_existing_sibling(tmp_path, monkeypatch):
    (tmp_path / "ohlc-full-20260718").mkdir()
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    with pytest.raises(DataSyncError, match="already exists"):
        rebuild.rebuild_sets(["ohlc-full"], ctx)
    with pytest.raises(DataSyncError, match="remove it to retry"):
        rebuild.rebuild_sets(["ohlc-full"], ctx)


def test_rebuild_never_touches_live_dir(tmp_path, monkeypatch):
    live = tmp_path / "ohlc-full"
    live.mkdir()
    (live / "keep.parquet").write_bytes(b"K")
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: (out / "new").write_text("x"))
    rebuild.rebuild_sets(["ohlc-full"], rebuild.RebuildContext(tmp_path, tmp_path, "20260718"))
    assert sorted(p.name for p in live.iterdir()) == ["keep.parquet"]


def test_rebuild_cleans_up_empty_sibling_on_builder_failure(tmp_path, monkeypatch):
    # A builder that raises must not orphan an empty sibling — else the per-day stamp blocks retry.
    def _boom(ctx, out):
        raise RuntimeError("network down")

    monkeypatch.setitem(rebuild.REBUILDABLE, "snapshots", _boom)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    with pytest.raises(RuntimeError, match="network down"):
        rebuild.rebuild_sets(["snapshots"], ctx)
    assert not (tmp_path / "snapshots-20260718").exists()  # retryable same day


def test_rebuild_removes_partial_sibling_on_builder_failure(tmp_path, monkeypatch):
    # A builder that wrote real output before raising must not strand the sibling: the date-stamped
    # name would turn every same-day retry into "sibling already exists" (T0098 sub-item 1).
    def _partial(ctx, out):
        (out / "BTC" / "EUR").mkdir(parents=True)
        (out / "BTC" / "EUR" / "1440.parquet").write_bytes(b"partial")
        raise RuntimeError("fetch 7 of 30 failed")

    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", _partial)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260802")
    with pytest.raises(RuntimeError, match="fetch 7 of 30"):
        rebuild.rebuild_sets(["ohlc-full"], ctx)
    assert not (tmp_path / "ohlc-full-20260802").exists()

    # And the same-day retry now succeeds.
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: (out / "ok").write_text("x"))
    assert rebuild.rebuild_sets(["ohlc-full"], ctx) == [tmp_path / "ohlc-full-20260802"]


def test_rebuild_cleanup_covers_operator_interrupt(tmp_path, monkeypatch):
    # Ctrl-C during a paced REST round is the likeliest mid-build abort; the handler catches
    # BaseException so the sibling is removed before the interrupt propagates. This test is the
    # pin that keeps the handler from being narrowed back to Exception.
    def _interrupted(ctx, out):
        (out / "partial").write_text("x")
        raise KeyboardInterrupt

    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", _interrupted)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260802")
    with pytest.raises(KeyboardInterrupt):
        rebuild.rebuild_sets(["ohlc-full"], ctx)
    assert not (tmp_path / "ohlc-full-20260802").exists()


def test_rebuild_unknown_set_raises(tmp_path):
    with pytest.raises(DataSyncError, match="unknown"):
        rebuild.rebuild_sets(["ohlc"], rebuild.RebuildContext(tmp_path, None, "20260718"))


def test_refresh_snapshots_writes_timestamped_kraken_refdata_json(tmp_path, monkeypatch):
    # Matches the live set's filename convention (kraken-refdata-<UTC stamp>.json) and the
    # canonical build_snapshot payload shape -- not an ad-hoc dict (spec D3).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "snapshots-20260718"
    out_root.mkdir()

    rebuild._refresh_snapshots(ctx, out_root)

    files = list(out_root.glob("kraken-refdata-*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert set(payload) == {"fetched_at", "raw", "raw_sha256", "symbols", "universe"}
    assert payload["symbols"] == ["BTC/EUR", "ETH/BTC"]


def _head(days: int) -> date:
    return SEAM + timedelta(days=days - 1)


def _stamp(day: date) -> str:
    return f"{day:%Y%m%d}"


def _line_sha256(root: Path, day: date) -> str:
    return hashlib.sha256((root / f"index/{day:%Y/%m/%d}.json").read_bytes()).hexdigest()


def _refresh_into(data_root: Path, name: str, stamp: str) -> dict:
    out_root = data_root / name
    out_root.mkdir()
    rebuild._refresh_universe(rebuild.RebuildContext(data_root=data_root, ohlcvt_source_dir=None, stamp=stamp), out_root)
    return json.loads((out_root / "point-in-time-universe.json").read_text())


def _the_closing_days(days: int) -> list[date]:
    """The last five days of a `days`-day chain, from a day inside the 30 the median reads to the head."""
    return [_head(days) - timedelta(days=n) for n in range(5)]


def test_refresh_universe_writes_point_in_time_universe_json(tmp_path, monkeypatch):
    # Matches the live set's filename (point-in-time-universe.json, the sole file
    # cli/capture/command.py's _default_pairs reads) and the canonical build_universe_file
    # payload shape, incl. the "selected" key -- not an ad-hoc dict (spec D3).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-rolling"
    write_chain(ohlc_root, days=30)
    head = _head(30)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(head + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    assert set(payload) == {"as_of", "entries", "escalate", "params", "provenance", "selected", "spread_cap"}
    assert payload["selected"] == ["BTC/EUR", "ETH/BTC"]
    assert payload["params"]["median_quote_volume_window_days"] == rebuild._UNIVERSE_VOLUME_WINDOW_DAYS
    assert payload["provenance"]["ohlc_dataset_hash"] == _line_sha256(ohlc_root, head)
    assert len(payload["provenance"]["snapshot_sha256"]) == 64
    # T0093: the artifact must name the set it was ACTUALLY built from, and how fresh that set was.
    assert payload["provenance"]["ohlc_dataset_dir"] == "ohlc-rolling"
    # The head's day: every pair's trailing window ends there, the one day a chained set's
    # stalest and newest daily bars share.
    assert payload["provenance"]["ohlc_stalest_daily_bar"] == "2026-10-30"


def test_refresh_universe_reads_the_rolling_set_at_its_head(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    root = tmp_path / "ohlc-rolling"
    write_chain(root, days=30)
    head, before = _head(30), _head(29)
    stamp = _stamp(head + timedelta(days=2))

    at_head = _refresh_into(tmp_path, "universe-at-head", stamp)["provenance"]
    # A fetch that brought the head's line ahead of one of its files: the head is the line before,
    # whose 30 daily bars the median still takes.
    (root / f"days/ETH/BTC/{head:%Y/%m/%d}.parquet").unlink()
    behind = _refresh_into(tmp_path, "universe-behind", stamp)["provenance"]

    assert (at_head["ohlc_as_of"], at_head["ohlc_dataset_hash"], at_head["ohlc_stalest_daily_bar"]) == (
        head.isoformat(),
        _line_sha256(root, head),
        head.isoformat(),
    )
    assert (behind["ohlc_as_of"], behind["ohlc_dataset_hash"], behind["ohlc_stalest_daily_bar"]) == (
        before.isoformat(),
        _line_sha256(root, before),
        before.isoformat(),
    )


def test_refresh_universe_provenance_names_the_set_the_as_of_and_the_line(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    root = tmp_path / "ohlc-rolling"
    write_chain(root, days=30)
    head = _head(30)

    provenance = _refresh_into(tmp_path, "universe", _stamp(head + timedelta(days=2)))["provenance"]

    assert len(provenance.pop("snapshot_sha256")) == 64
    assert provenance == {
        "ohlc_dataset_hash": _line_sha256(root, head),
        "ohlc_dataset_dir": "ohlc-rolling",
        "ohlc_as_of": "2026-10-30",
        "ohlc_stalest_daily_bar": "2026-10-30",
        "ohlc_closed_pairs": [],
    }


def test_refresh_universe_refuses_a_rolling_set_whose_chain_does_not_walk(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    root = tmp_path / "ohlc-rolling"
    write_chain(root, days=30)
    # A line edited after the next one chained to it, still in the index's canonical form.
    edited = root / "index/2026/10/15.json"
    line = json.loads(edited.read_bytes())
    line["files"][min(line["files"])] = "0" * 64
    edited.write_bytes(line_bytes(line))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(_head(30) + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    with pytest.raises(RollingError, match=r"index/2026/10/16\.json: its prev is not the sha256 of index/2026/10/15\.json"):
        rebuild._refresh_universe(ctx, out_root)
    assert not (out_root / "point-in-time-universe.json").exists()


def test_rebuild_refuses_ohlc_reach_as_an_unknown_set(tmp_path):
    with pytest.raises(DataSyncError, match="unknown set 'ohlc-reach'"):
        rebuild.rebuild_sets(["ohlc-reach"], rebuild.RebuildContext(tmp_path, None, "20261101"))
    assert list(tmp_path.iterdir()) == []


def test_refresh_universe_reads_past_a_hole_older_than_its_volume_window(tmp_path, monkeypatch):
    """The read spans the 30 daily bars the median takes, 2026-10-03 to the head 2026-11-01 here."""
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    stamp = _stamp(_head(32) + timedelta(days=2))
    older, inside = tmp_path / "older", tmp_path / "inside"
    write_chain(older / "ohlc-rolling", days=32, holes={date(2026, 10, 1): {"ETH/BTC"}, date(2026, 10, 2): {"ETH/BTC"}})
    write_chain(inside / "ohlc-rolling", days=32, holes={date(2026, 10, 3): {"ETH/BTC"}})

    payload = _refresh_into(older, "universe", stamp)

    assert [entry["symbol"] for entry in payload["entries"]] == ["BTC/EUR", "ETH/BTC"]
    with pytest.raises(RollingError, match=r"ETH/BTC has a hole on 2026-10-03"):
        _refresh_into(inside, "universe", stamp)


def test_refresh_universe_leaves_a_closed_pair_out_and_names_it(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    # Two `/EUR` legs whose candidate order is not their sorted order, so the provenance's sorted order is not
    # the candidates' order.
    shut = {day: {"XRP/EUR", "ADA/EUR"} for day in _the_closing_days(30)}
    closed, open_holes = tmp_path / "closed", tmp_path / "open-holes"
    write_chain(closed / "ohlc-rolling", pairs=rebuild.CANDIDATE_SYMBOLS, days=30, closed=shut)
    write_chain(open_holes / "ohlc-rolling", pairs=rebuild.CANDIDATE_SYMBOLS, days=30, holes=shut)
    stamp = _stamp(_head(30) + timedelta(days=2))

    payload = _refresh_into(closed, "universe", stamp)

    assert [entry["symbol"] for entry in payload["entries"]] == [
        symbol for symbol in rebuild.CANDIDATE_SYMBOLS if symbol not in {"XRP/EUR", "ADA/EUR"}
    ]
    assert {"XRP/EUR", "ADA/EUR"}.isdisjoint(payload["selected"])
    assert payload["provenance"]["ohlc_closed_pairs"] == ["ADA/EUR", "XRP/EUR"]
    with pytest.raises(RollingError, match=r"(XRP|ADA)/EUR has a hole on 2026-10-26"):
        _refresh_into(open_holes, "universe", stamp)


@pytest.mark.parametrize("mandatory", ["BTC/EUR", "ETH/EUR"])
def test_refresh_universe_refuses_a_closed_mandatory_pair(tmp_path, monkeypatch, mandatory):
    """BTC/EUR also prices the `/BTC` legs in EUR, so its close refuses here, never at the read of its holes."""
    fetched = []
    monkeypatch.setattr(rebuild, "fetch_public", lambda endpoint: fetched.append(endpoint) or _fake_fetch_public(endpoint))
    # ADA/EUR sorts before both, so a refusal that read only the first closed pair would find no mandatory one.
    shut = {day: {"ADA/EUR", mandatory} for day in _the_closing_days(30)}
    write_chain(tmp_path / "ohlc-rolling", pairs=rebuild.CANDIDATE_SYMBOLS, days=30, closed=shut)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(_head(30) + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match=f"mandatory pair {mandatory} ") as refused:
        rebuild._refresh_universe(ctx, out_root)

    assert "ADA/EUR" not in str(refused.value)
    assert fetched == []
    assert not (out_root / "point-in-time-universe.json").exists()


def test_refresh_universe_leaves_a_closed_eth_btc_out_though_eth_is_mandatory(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    write_chain(
        tmp_path / "ohlc-rolling",
        pairs=rebuild.CANDIDATE_SYMBOLS,
        days=30,
        closed={day: {"ETH/BTC"} for day in _the_closing_days(30)},
    )

    payload = _refresh_into(tmp_path, "universe", _stamp(_head(30) + timedelta(days=2)))

    assert "ETH/BTC" not in {entry["symbol"] for entry in payload["entries"]}
    assert "ETH/BTC" not in payload["selected"]
    assert payload["provenance"]["ohlc_closed_pairs"] == ["ETH/BTC"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_refresh_universe_refuses_an_index_it_cannot_list(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    write_chain(tmp_path / "ohlc-rolling", days=30)
    month = tmp_path / "ohlc-rolling/index/2026/10"
    os.chmod(month, 0o000)
    try:
        with pytest.raises(DataSyncError, match=r"universe cannot read \S*/ohlc-rolling -- .*Permission denied"):
            _refresh_into(tmp_path, "universe", _stamp(_head(30) + timedelta(days=2)))
    finally:
        os.chmod(month, 0o755)


# 40 daily BTC/EUR bars, its vwap one value on the first thirty and twice it on the last ten: the last-20
# window sees ten of each and the last-30 window twenty against ten, so the two medians disagree.
# `quote_volume_in_eur`'s own default window is 30 independently of `_UNIVERSE_VOLUME_WINDOW_DAYS`,
# and a fixture whose windows agreed would pass with the call site's `window=` dropped.
_TWO_WINDOW_DAYS = 39
_DOUBLED_FROM = date(2026, 10, 30)
_VWAP = 100_000.0
# A day's 96 bars of volume 0.5 sum to 48, and its vwap is theirs: a daily quote volume of 48 times it.
_MEDIAN_OVER_30, _MEDIAN_OVER_20 = 48 * _VWAP, 48 * 1.5 * _VWAP


def _two_window_vwaps(pair: str, day: date) -> dict[str, float]:
    if pair != "BTC/EUR":
        return {}
    return {"vwap": _VWAP if day < _DOUBLED_FROM else 2 * _VWAP}


def _btc_entry(payload: dict) -> dict:
    rows = [entry for entry in payload["entries"] if entry["symbol"] == "BTC/EUR"]
    assert len(rows) == 1, payload["entries"]
    return rows[0]


def test_refresh_universe_medians_over_the_window_its_params_declare(tmp_path, monkeypatch):
    """The published `median_quote_volume_window_days` and the window the medians were taken over are
    two different values, and only the entry moving with the constant proves they are the same one."""
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    write_chain(tmp_path / "ohlc-rolling", days=_TWO_WINDOW_DAYS, bar=_two_window_vwaps)
    stamp = _stamp(_head(_TWO_WINDOW_DAYS))

    monkeypatch.setattr(rebuild, "_UNIVERSE_VOLUME_WINDOW_DAYS", 30)
    payload = _refresh_into(tmp_path, "universe-30", stamp)
    assert payload["params"]["median_quote_volume_window_days"] == 30
    assert _btc_entry(payload)["median_quote_volume"] == _MEDIAN_OVER_30

    monkeypatch.setattr(rebuild, "_UNIVERSE_VOLUME_WINDOW_DAYS", 20)
    moved = _refresh_into(tmp_path, "universe-20", stamp)
    assert moved["params"]["median_quote_volume_window_days"] == 20
    assert _btc_entry(moved)["median_quote_volume"] == _MEDIAN_OVER_20


def test_refresh_universe_actually_applies_the_spread_cap(tmp_path, monkeypatch):
    # The production path is the whole point of the criterion: wiring it in `_refresh_universe` is
    # what makes the cap real, so reverting that call to `finalize_universe(pairs, volumes)` must
    # turn this test red. Asserting only the `spread_cap` record would NOT -- that record is built
    # separately from the map that does the screening, so the two can drift silently (T0024 review).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    write_chain(tmp_path / "ohlc-rolling", days=30)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(_head(30) + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    entries = {e["symbol"]: e["spread_bps"] for e in payload["entries"]}
    # The EUR leg carries the calibrated number at the reference notional -- not None, not 0.0.
    expected = round(effective_spread_bps("BTC/EUR", SPREAD_REFERENCE_NOTIONAL_EUR), 3)
    assert entries["BTC/EUR"] == expected
    # The BTC-quoted leg is calibrated too (spec 00085), and this assertion is the re-key's proof at
    # the production boundary: with the base-keyed table `_refresh_universe` skipped the leg
    # entirely, and with a base-keyed lookup it would price a EUR notional against a BTC ladder.
    assert entries["ETH/BTC"] == round(effective_spread_bps("ETH/BTC", SPREAD_REFERENCE_NOTIONAL_EUR), 3)
    assert payload["spread_cap"]["max_spread_bps"] == DEFAULT_MAX_SPREAD_BPS
    assert payload["spread_cap"]["reference_notional_eur"] == SPREAD_REFERENCE_NOTIONAL_EUR
    assert payload["spread_cap"]["unevaluated_count"] == 0


def test_refresh_universe_refuses_a_stale_ohlc_set(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    # Head 2026-10-30, rebuild stamped 2026-11-18: 19 days, past the 7-day budget.
    write_chain(tmp_path / "ohlc-rolling", pairs=("BTC/EUR",), days=30)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20261118")
    out_root = tmp_path / "universe-20261118"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="2026-10-30"):
        rebuild._refresh_universe(ctx, out_root)
    assert not (out_root / "point-in-time-universe.json").exists(), "must not write a stale universe"


def test_refresh_universe_diagnoses_staleness_before_the_row_count(tmp_path, monkeypatch):
    """A stale set that is ALSO too short must report the staleness, not the row count: the medians
    raise UniverseError on a short frame, which would mask the real diagnosis (T0093 review)."""
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    # Ten daily bars, the head 2026-10-09.
    write_chain(tmp_path / "ohlc-rolling", pairs=("BTC/EUR",), days=9)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20261118")
    out_root = tmp_path / "universe-20261118"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="2026-10-09"):
        rebuild._refresh_universe(ctx, out_root)


def test_refresh_universe_accepts_an_ohlc_set_inside_the_staleness_budget(tmp_path, monkeypatch):
    """The guard must not block an ordinary rebuild: daily bars lag by a day or so by construction."""
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    write_chain(tmp_path / "ohlc-rolling", pairs=("BTC/EUR",), days=30)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(_head(30) + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)  # 2 days stale, inside the budget

    assert (out_root / "point-in-time-universe.json").exists()


def test_refresh_universe_requires_the_rolling_set(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20261101")
    absent = re.escape(str(tmp_path / "ohlc-rolling"))

    with pytest.raises(DataSyncError, match=rf"the ohlc-rolling set, which is absent: no directory {absent}; zcrypto data fetch"):
        rebuild._refresh_universe(ctx, tmp_path / "universe-20261101")


def test_a_source_missing_a_candidate_leg_refuses_and_names_it(tmp_path, monkeypatch):
    """The guard this task exists for. `escalate` cannot see a narrower SOURCE: a ten-of-twelve
    source yields a ten-name universe with escalate False -- a silent shrink."""
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    # The base line without ETH/BTC, the missing leg.
    write_chain(tmp_path / "ohlc-rolling", pairs=tuple(s for s in rebuild.CANDIDATE_SYMBOLS if s != "ETH/BTC"), days=30)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(_head(30) + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="ETH/BTC"):
        rebuild._refresh_universe(ctx, out_root)
    assert not (out_root / "point-in-time-universe.json").exists()


def test_a_symbol_the_floor_rejects_is_NOT_a_missing_source(tmp_path, monkeypatch):
    """Presence, not outcome. A leg present but below the volume floor is a selection result and
    must still flow through escalate -- it must NOT trip the guard."""
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    # SOL/BTC is present but priced to land far below the volume floor -- a selection outcome,
    # not a missing leg.
    write_chain(
        tmp_path / "ohlc-rolling",
        pairs=rebuild.CANDIDATE_SYMBOLS,
        days=30,
        bar=lambda pair, day: {"volume": 0.001} if pair == "SOL/BTC" else {},
    )

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(_head(30) + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)  # must not raise

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    entries = {e["symbol"]: e for e in payload["entries"]}
    assert entries["SOL/BTC"]["selected"] is False
    assert any("below floor" in reason for reason in entries["SOL/BTC"]["reasons"])


def test_refresh_universe_reads_the_rolling_set_not_the_hardcoded_ohlc_full(tmp_path, monkeypatch):
    """The wiring: the rebuild reads `ohlc-rolling` at its head, its provenance naming the set and the head line's
    sha256, and never the `ohlc-full` beside it, which holds no index line, so a rebuild reading it refuses."""
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    stale_root = tmp_path / "ohlc-full"
    for symbol in rebuild.CANDIDATE_SYMBOLS:
        base, quote = symbol.split("/")
        _write_daily(stale_root / base / quote / "1440.parquet", vwap=100.0, volume=2_000.0, last=date(2026, 3, 31))
    (stale_root / "manifest.json").write_text(json.dumps({"basket_sha256": "stale"}))

    fresh_root = tmp_path / "ohlc-rolling"
    write_chain(fresh_root, pairs=rebuild.CANDIDATE_SYMBOLS, days=30)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp=_stamp(_head(30) + timedelta(days=2)))
    out_root = tmp_path / "universe-20261101"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)  # must succeed by reading the rolling set

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    assert payload["provenance"]["ohlc_dataset_dir"] == "ohlc-rolling"
    assert payload["provenance"]["ohlc_dataset_hash"] == _line_sha256(fresh_root, _head(30))


def test_every_rebuildable_dataset_is_an_authored_set():
    """A dataset this node can REBUILD is one it AUTHORS, so it must also be publishable.

    `authored_sets` drives `data push`; `push_hot` raises only when a listed set is missing from DISK,
    never when a set is merely absent from the list. So a dataset dropped from `authored_sets` is
    never pushed, the ops node can never `data fetch` it, and NOTHING errors.

    The converse is deliberately NOT asserted -- `authored_sets` may legitimately hold sets that are
    not rebuildable (e.g. `ohlc-holdout-*`, a frozen one-off with a spent look budget).
    """
    config = tomllib.loads((Path(__file__).resolve().parents[1] / "zcrypto.toml").read_text())
    authored = set(config["zcrypto"]["data"]["authored_sets"])

    missing = sorted(set(rebuild.REBUILDABLE) - authored)

    assert not missing, (
        f"rebuildable dataset(s) absent from zcrypto.toml authored_sets: {missing}. "
        "`data push` would silently skip them and the ops node could never fetch them -- if you hit "
        "this after a merge, the resolution dropped an entry; the fix is the UNION of both sides."
    )
