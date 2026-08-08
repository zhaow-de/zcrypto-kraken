"""Tests for `cli.data.rebuild` (spec 00056 D3): the sibling-minting rebuild orchestration. The
builders are monkeypatched into `rebuild.REBUILDABLE` so these tests stay hermetic."""

import json
import tomllib
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.costs.spread import effective_spread_bps
from cli.data import rebuild
from cli.data.errors import DataSyncError
from cli.ohlc.reach import ReachEntry, ReachReport
from cli.universe.rules import DEFAULT_MAX_SPREAD_BPS, SPREAD_REFERENCE_NOTIONAL_EUR

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


def test_refresh_universe_writes_point_in_time_universe_json(tmp_path, monkeypatch):
    # Matches the live set's filename (point-in-time-universe.json, the sole file
    # cli/capture/command.py's _default_pairs reads) and the canonical build_universe_file
    # payload shape, incl. the "selected" key -- not an ad-hoc dict (spec D3).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    # Deliberately DIFFERENT frontiers, both inside the 7-day budget, so the published bar pins the
    # min/max choice: with equal `last=` the two statistics coincide and the assertion proves nothing.
    # BTC/EUR runs 34 bars so the inner ts-join with the earlier-ending ETH/BTC still yields the 30
    # aligned rows the median needs (intersection 2026-06-15..07-14).
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0, n=34, last=date(2026, 7, 18))
    _write_daily(ohlc_root / "ETH" / "BTC" / "1440.parquet", vwap=0.05, volume=1_000.0, last=date(2026, 7, 14))
    (ohlc_root / "manifest.json").write_text(json.dumps({"basket_sha256": "deadbeef"}))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    assert set(payload) == {"as_of", "entries", "escalate", "params", "provenance", "selected", "spread_cap"}
    assert payload["selected"] == ["BTC/EUR", "ETH/BTC"]
    # Pins that the artifact's DECLARED window is the module constant, so the two cannot drift
    # apart in the payload. It does NOT pin the constant->computation wiring: both sides of this
    # assertion move together, so removing `window=` from the quote_volume_in_eur call would still
    # pass. That wiring is correct at HEAD; pinning it needs a fixture whose last 30 rows differ
    # from its last 20 (T0093 review).
    assert payload["params"]["median_quote_volume_window_days"] == rebuild._UNIVERSE_VOLUME_WINDOW_DAYS
    assert payload["provenance"]["ohlc_dataset_hash"] == "deadbeef"
    assert len(payload["provenance"]["snapshot_sha256"]) == 64
    # T0093: the artifact must name the set it was ACTUALLY built from, and how fresh that set was.
    # The 2026-07-07 artifact cited `data/ohlc` by hash alone; when that directory was retired the
    # citation became unresolvable, and nothing in the file said which window the volumes covered.
    assert payload["provenance"]["ohlc_dataset_dir"] == "ohlc-full"
    # The STALEST bar (ETH/BTC's 07-14), not the basket's newest (BTC/EUR's 07-18): only the stalest
    # supports "every symbol's window ends at or after this". Publishing max would fail here.
    assert payload["provenance"]["ohlc_stalest_daily_bar"] == "2026-07-14"


def test_refresh_universe_refuses_a_basket_with_no_manifest(tmp_path, monkeypatch):
    """A missing `manifest.json` must fail closed, never emit `ohlc_dataset_hash: ""` (T0094).

    `backfill_basket` always writes a manifest, so its absence means a broken or half-written set --
    exactly when a silent empty hash is most harmful. An empty string is also the wrong shape for
    "unknown": it reads as a value and compares EQUAL across two entirely different broken builds,
    so two artifacts could agree on provenance while sharing none. A directory name is not an
    identity (that is T0093's whole story); the hash is what makes a citation resolvable.
    """
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0)
    _write_daily(ohlc_root / "ETH" / "BTC" / "1440.parquet", vwap=0.05, volume=1_000.0)
    # deliberately NO manifest.json

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="manifest"):
        rebuild._refresh_universe(ctx, out_root)

    # and it must fail BEFORE writing anything -- a half-written artifact is the failure mode too
    assert not (out_root / "point-in-time-universe.json").exists()


@pytest.mark.parametrize(
    ("payload", "label"),
    [("{not json", "invalid JSON"), ('{"other_key": 1}', "missing basket_sha256")],
)
def test_refresh_universe_refuses_an_unreadable_manifest(tmp_path, monkeypatch, payload, label):
    """A manifest that EXISTS but cannot be read is the same defect as an absent one (T0094).

    Both mean the set cannot identify itself, so both get the same typed failure -- otherwise this
    path raises an untyped KeyError/JSONDecodeError from deep in the call stack, with no path in
    the message, inconsistent with every other guard in this module.
    """
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0)
    _write_daily(ohlc_root / "ETH" / "BTC" / "1440.parquet", vwap=0.05, volume=1_000.0)
    (ohlc_root / "manifest.json").write_text(payload)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="unreadable"):
        rebuild._refresh_universe(ctx, out_root)
    assert not (out_root / "point-in-time-universe.json").exists(), label


def test_refresh_universe_actually_applies_the_spread_cap(tmp_path, monkeypatch):
    # The production path is the whole point of the criterion: wiring it in `_refresh_universe` is
    # what makes the cap real, so reverting that call to `finalize_universe(pairs, volumes)` must
    # turn this test red. Asserting only the `spread_cap` record would NOT -- that record is built
    # separately from the map that does the screening, so the two can drift silently (T0024 review).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0)
    _write_daily(ohlc_root / "ETH" / "BTC" / "1440.parquet", vwap=0.05, volume=1_000.0)
    (ohlc_root / "manifest.json").write_text(json.dumps({"basket_sha256": "deadbeef"}))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    entries = {e["symbol"]: e["spread_bps"] for e in payload["entries"]}
    # The EUR leg carries the calibrated number at the reference notional -- not None, not 0.0.
    expected = round(effective_spread_bps("BTC/EUR", SPREAD_REFERENCE_NOTIONAL_EUR), 3)
    assert entries["BTC/EUR"] == expected
    # INVERTED by spec 00085: the BTC-quoted leg is now calibrated, so it carries a real number
    # where it previously carried None. This assertion is the re-key's proof at the production
    # boundary -- with the base-keyed table `_refresh_universe` skipped the leg entirely, and with a
    # base-keyed lookup it would have priced a EUR notional against a BTC ladder instead.
    #
    # The unevaluated path itself is NOT lost with this flip: an uncalibrated pair being recorded
    # rather than auto-failed is pinned directly by
    # test_universe_rules.py::test_an_uncaptured_pair_is_recorded_as_unevaluated_and_NOT_rejected.
    assert entries["ETH/BTC"] == round(effective_spread_bps("ETH/BTC", SPREAD_REFERENCE_NOTIONAL_EUR), 3)
    assert payload["spread_cap"]["max_spread_bps"] == DEFAULT_MAX_SPREAD_BPS
    assert payload["spread_cap"]["reference_notional_eur"] == SPREAD_REFERENCE_NOTIONAL_EUR
    assert payload["spread_cap"]["unevaluated_count"] == 0


def test_refresh_universe_refuses_a_stale_ohlc_set(tmp_path, monkeypatch):
    """T0093: the volume floor is a TRAILING 30-day median, so it is only meaningful if the dataset
    reaches the present. `ohlc-full` stops where the OHLCVT dumps stop (2026-03-31 in the live set)
    while the v0 REST set it replaced was live-fetched -- so this path can compute a "30-day median"
    over a window months in the past and shrink the universe for what looks like a liquidity move.
    Measured on the live data: AVAX/EUR reads 132,274.82 against the 150,000 floor and drops out,
    with `escalate` staying False because 11 >= MIN_NAMES. Fail closed instead of selecting quietly.
    """
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    # Newest bar 2026-03-31, rebuild stamped 2026-07-18 -- the live situation exactly.
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0, last=date(2026, 3, 31))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="2026-03-31"):
        rebuild._refresh_universe(ctx, out_root)
    assert not (out_root / "point-in-time-universe.json").exists(), "must not write a stale universe"


def test_refresh_universe_refuses_a_basket_where_only_some_symbols_are_fresh(tmp_path, monkeypatch):
    """The guard is per-symbol, not on the basket's newest bar: each symbol's median comes from its
    own frame, so one fresh symbol must not vouch for a stale one. This is the shape T0065's REACH
    round would produce -- a live-trades->bars tail need not cover every basket symbol equally,
    leaving the thinner legs at the dump extent. A `max` check passes this basket."""
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0, last=date(2026, 7, 18))
    _write_daily(ohlc_root / "ETH" / "BTC" / "1440.parquet", vwap=0.05, volume=1_000.0, last=date(2026, 3, 31))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="ETH/BTC"):
        rebuild._refresh_universe(ctx, out_root)


def test_refresh_universe_diagnoses_staleness_before_the_row_count(tmp_path, monkeypatch):
    """A stale set that is ALSO too short must report the staleness, not the row count: the medians
    raise UniverseError on a short frame, which would mask the real diagnosis (T0093 review)."""
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0, n=10, last=date(2026, 3, 31))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    with pytest.raises(DataSyncError, match="2026-03-31"):
        rebuild._refresh_universe(ctx, out_root)


def test_refresh_universe_accepts_an_ohlc_set_inside_the_staleness_budget(tmp_path, monkeypatch):
    """The guard must not block an ordinary rebuild: daily bars lag by a day or so by construction."""
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0, last=date(2026, 7, 16))
    (ohlc_root / "manifest.json").write_text(json.dumps({"basket_sha256": "deadbeef"}))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)  # 2 days stale, inside the budget

    assert (out_root / "point-in-time-universe.json").exists()


def test_refresh_universe_requires_live_ohlc_full(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")

    with pytest.raises(DataSyncError, match="ohlc-full"):
        rebuild._refresh_universe(ctx, tmp_path / "universe-20260718")


def test_rebuild_ohlc_reach_reads_the_live_canonical_and_writes_only_the_sibling(tmp_path, monkeypatch):
    """The reach builder must read the LIVE ohlc-full and write into the minted sibling only --
    reading the sibling instead would reach forward from an empty set."""
    (tmp_path / "ohlc-full").mkdir()
    seen = {}

    def _fake_reach(canonical_root, out_root, **kwargs):
        seen["canonical"] = canonical_root
        seen["out"] = out_root
        (out_root / "written").write_text("x")
        return ReachReport(entries=())

    monkeypatch.setattr(rebuild, "reach_round", _fake_reach)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260723")

    minted = rebuild.rebuild_sets(["ohlc-reach"], ctx)

    assert seen["canonical"] == tmp_path / "ohlc-full"
    assert seen["out"] == tmp_path / "ohlc-reach-20260723" == minted[0]
    assert (tmp_path / "ohlc-reach-20260723" / "written").exists()


def test_rebuild_ohlc_reach_warns_naming_every_detached_series(tmp_path, monkeypatch, caplog):
    """A detached series is the case an operator must not miss, so it is logged by name."""
    (tmp_path / "ohlc-full").mkdir()
    entries = (
        ReachEntry(
            symbol="BTC",
            interval=60,
            status="detached",
            rest_first=datetime(2026, 6, 23, tzinfo=UTC),
            rest_last=datetime(2026, 7, 23, tzinfo=UTC),
            overlap_bars=0,
            appended=720,
            gap_bars=2009,
        ),
        ReachEntry(
            symbol="BTC",
            interval=240,
            status="continuous",
            rest_first=datetime(2026, 3, 25, tzinfo=UTC),
            rest_last=datetime(2026, 7, 23, tzinfo=UTC),
            overlap_bars=38,
            appended=682,
            gap_bars=0,
        ),
    )

    def _fake_reach(canonical_root, out_root, **kwargs):
        (out_root / "x").write_text("x")
        return ReachReport(entries=entries)

    monkeypatch.setattr(rebuild, "reach_round", _fake_reach)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260723")

    with caplog.at_level("WARNING"):
        rebuild.rebuild_sets(["ohlc-reach"], ctx)

    assert "1 of 2 reach series are DETACHED" in caplog.text
    assert "BTC@60" in caplog.text
    assert "BTC@240" not in caplog.text


def test_rebuild_ohlc_reach_fails_closed_without_a_live_canonical(tmp_path, monkeypatch):
    """No ohlc-full means nothing to reach forward FROM -- refuse rather than mint an empty set."""
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260723")
    with pytest.raises(DataSyncError):
        rebuild.rebuild_sets(["ohlc-reach"], ctx)


def test_every_rebuildable_dataset_is_an_authored_set():
    """A dataset this node can REBUILD is one it AUTHORS, so it must also be publishable.

    Guards a real, silent failure mode. `authored_sets` drives `data push`; `push_hot` raises only
    when a listed set is missing from DISK, never when a set is merely absent from the list. So a
    dataset dropped from `authored_sets` is never pushed, the ops node can never `data fetch` it,
    and NOTHING errors. That is exactly what a careless merge produces: two branches each appending
    a different dataset to this one-line array conflict, and a resolution keeping only one side
    looks clean. This assertion is what makes that loud.

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
