import json
import math
import re
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from cli.alpha import c3 as alpha_c3
from cli.alpha.errors import AlphaError
from cli.data.manifest import build_manifest, series_entry
from cli.onchain import series as onchain_series
from cli.onchain.freeze import SNAPSHOT_RELPATH
from cli.onchain.series import COLUMNS, SCHEMA
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig
from cli.portfolio.errors import PortfolioError
from cli.registry.record import validate_metrics
from cli.research import subjects
from cli.validation import ValidationError

SUBJECT = "c3-onchain-reading"
DATASET = "btc-onchain-test"
ASSETS = CrossfreqSystemConfig().assets
UNION_START = datetime(2020, 10, 1, tzinfo=UTC)
N_DAYS = 320
LEAD = 800
# Every asset falls 5 % over the 7 closes from each index divisible by CYCLE and rises 15 % on the eighth, so the A1
# sleeve, gated on BTC's 200-day average, holds each asset listed on the first day long from index 200 on.
CYCLE = 8
FALL, RISE = 0.95 ** (1 / 7), 1.15
SOL_LISTED = 280
AS_OF_LINE = {"relpath": "index/2021/08/16.json", "sha256": "5" * 64}
FEATURES = ("mvrv", "mvrv_z", "asopr", "sth_supply_share")
TAILS = ("low", "high")
STATES = ("long", "flat")
CELLS = {
    f"{feature}|{tail}|{state}|H{horizon}" for feature in FEATURES for tail in TAILS for state in STATES for horizon in (7, 30)
}


def _legs() -> dict[str, pl.DataFrame]:
    ts = [UNION_START + timedelta(days=k) for k in range(N_DAYS)]
    legs = {}
    for i, asset in enumerate(ASSETS):
        closes = [10.0 * (i + 1)]
        for k in range(N_DAYS - 1):
            closes.append(closes[-1] * (FALL if k % CYCLE < CYCLE - 1 else RISE))
        first = SOL_LISTED if asset == "SOL" else 0
        legs[f"{asset}/EUR/1440.parquet"] = pl.DataFrame({"ts": ts[first:], "close": closes[first:]})
    return legs


def _snapshot(*, lead: int = LEAD, unpriced: int = 0, dropped: int | None = None) -> pl.DataFrame:
    """Day j of the snapshot lies `lead` days before the union's first day. `mvrv` is planted: a new high on the day before
    each index divisible by CYCLE, and below every high on the others, which are 7 in 8, so no other day reaches the high
    tail; `asopr` is flat, its tails on an 11-day cycle that the 8-day price cycle does not share; `market_cap` swings
    about `price`, so the reading's own `mvrv_z` reaches both tails, and the snapshot's `mvrv_z` is NaN."""
    n = lead + N_DAYS
    columns = {column: [1.0] * n for column in COLUMNS[3:]}
    columns["price"] = [10_000.0 + j for j in range(n)]
    columns["mvrv"] = [2.0 + 0.001 * j if (j - lead + 1) % CYCLE == 0 else (j * 0.6180339887) % 1 for j in range(n)]
    columns["market_cap"] = [(10_000.0 + j) * (1 + 0.5 * ((j * 0.4142135624) % 1)) for j in range(n)]
    columns["realized_cap"] = [9_000.0] * n
    columns["mvrv_z"] = [math.nan] * n
    columns["asopr"] = [float(j % 11) for j in range(n)]
    columns["sth_supply_share"] = [(j * 0.7548776662) % 1 for j in range(n)]
    for column in ("price", "market_cap", "mvrv", "asopr"):
        columns[column][:unpriced] = [0.0] * unpriced
    frame = pl.DataFrame(
        {
            "ts": [UNION_START - timedelta(days=lead - j) for j in range(n)],
            "last_height": list(range(n)),
            "last_hash": [f"{j:064x}" for j in range(n)],
        }
        | columns,
        schema=SCHEMA,
    )
    return frame if dropped is None else pl.concat([frame.head(dropped), frame.slice(dropped + 1)])


class _Reader:
    def __init__(self, root, snapshot, legs, broken, error):
        self._root, self.snapshot, self.legs, self.broken, self.error = root, snapshot, legs, broken, error

    def read_series(self, dataset, relpath, window=None):
        if (dataset, relpath) == self.broken:
            raise self.error(f"cannot read {relpath}")
        if (dataset, relpath) == (DATASET, SNAPSHOT_RELPATH):
            return self.snapshot
        assert dataset == "ohlc-full" and window is None, (dataset, relpath, window)
        return self.legs[relpath]


def _reader(root, *, snapshot=None, provenance=None, manifest=True, broken=None, error=OSError) -> _Reader:
    snapshot = _snapshot() if snapshot is None else snapshot
    if manifest:
        provenance = {"producer": "zcrypto onchain freeze", "as_of_line": AS_OF_LINE} if provenance is None else provenance
        document = build_manifest(
            {SNAPSHOT_RELPATH: series_entry(snapshot, SNAPSHOT_RELPATH)},
            written_at="2021-08-17T00:00:00+00:00",
            identity="set",
            provenance=provenance,
        )
        (root / DATASET).mkdir(parents=True)
        (root / DATASET / "manifest.json").write_text(json.dumps(document))
    return _Reader(root, snapshot, _legs(), broken, error)


def _build(reader):
    return subjects._build_c3_onchain_reading(reader, DATASET, None)


def _inputs(reader):
    _, snapshot, grid, prices = subjects._c3_reads(reader, DATASET, SUBJECT)
    return subjects._c3_reading_inputs(snapshot, grid, prices)


def _column(snapshot: pl.DataFrame, feature: str) -> list[float | None]:
    days = [stamp.date() for stamp in snapshot["ts"].to_list()]
    if feature != "mvrv_z":
        return alpha_c3.from_first_day(days, snapshot[feature].to_list())
    caps = alpha_c3.from_first_day(days, snapshot["market_cap"].to_list())
    return alpha_c3.from_first_day(days, onchain_series.mvrv_z(caps, snapshot["realized_cap"].to_list()))


def _yyyymmdd(day: date) -> int:
    return int(day.strftime("%Y%m%d"))


@pytest.fixture
def resamples(monkeypatch):
    monkeypatch.setattr(alpha_c3, "N_RESAMPLES", 200)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _build(_reader(tmp_path_factory.mktemp("c3-set")))


def test_the_build_returns_exactly_the_declared_keys_and_32_cells(built):
    assert set(built) == subjects._C3_READING_KEYS == {"cells", "event_years", "counts", "features", "arm", "constants"}
    assert set(built["cells"]) == CELLS and len(CELLS) == 32
    assert all(set(cell) == {"log", "summed"} for cell in built["cells"].values())
    assert set(built["event_years"]) == CELLS
    assert built["constants"] == {
        "low": 0.10,
        "high": 0.90,
        "min_history": 365,
        "lag_days": 1,
        "horizons": [7, 30],
        "mean_block": 102,
        "n_resamples": 10000,
        "seed": 42,
        "far": [0.078125, 99.921875],
        "cost_round_trip": 0.012,
        "min_event_years": 4,
    }


def test_the_inputs_half_reads_no_forward(tmp_path, monkeypatch):
    assert subjects._C3ReadingInputs._fields == ("grid", "years", "arm", "positions", "states", "features", "bands", "counts")
    _, snapshot, grid, prices = subjects._c3_reads(_reader(tmp_path), DATASET, SUBJECT)
    for module, name in ((alpha_c3, "forwards"), (subjects, "event_contrast_blocks"), (subjects, "stationary_bootstrap_blocks")):
        monkeypatch.setattr(module, name, lambda *args, called=name, **kwargs: pytest.fail(f"{called} in the inputs half"))

    inputs = subjects._c3_reading_inputs(snapshot, grid, prices)

    assert inputs.grid == grid and len(inputs.counts) == 16 and set(inputs.arm) == set(ASSETS)


def test_the_bands_rank_the_snapshots_whole_history(tmp_path):
    snapshot = _snapshot()
    inputs = _inputs(_reader(tmp_path, snapshot=snapshot))
    days = [stamp.date() for stamp in snapshot["ts"].to_list()]
    read = days.index(UNION_START.date() - timedelta(days=1))
    assert read == LEAD - 1 and inputs.grid[0] == UNION_START
    for feature in FEATURES:
        whole = alpha_c3.bands(_column(snapshot, feature))
        assert inputs.bands[feature][0] is not None and inputs.bands[feature][0] == whole[read], feature
        assert inputs.bands[feature] == alpha_c3.lagged(dict(zip(days, whole, strict=True)), inputs.grid), feature


def test_a_valuation_on_an_unpriced_day_is_unread(tmp_path):
    snapshot = _snapshot(lead=300, unpriced=30)
    inputs = _inputs(_reader(tmp_path, snapshot=snapshot))
    days = [stamp.date() for stamp in snapshot["ts"].to_list()]
    for feature in ("mvrv", "asopr"):
        assert inputs.features[feature]["first"] == _yyyymmdd(days[30 + 364]), feature
    assert inputs.features["sth_supply_share"]["first"] == _yyyymmdd(days[364])
    # mvrv_z's σ counts priced market caps alone, its band 365 values after its first.
    snapshot = _snapshot(lead=500, unpriced=30)
    inputs = _inputs(_reader(tmp_path / "z", snapshot=snapshot))
    days = [stamp.date() for stamp in snapshot["ts"].to_list()]
    assert inputs.features["mvrv_z"]["first"] == _yyyymmdd(days[30 + 364 + 364])


@pytest.mark.parametrize(
    ("offset", "features", "first"),
    [((500, ("mvrv", "asopr", "sth_supply_share"), 500 + 364)), (100, ("mvrv_z",), 100 + 364 + 364)],
    ids=["the-snapshots-features", "the-readings-mvrv-z"],
)
def test_a_day_before_the_first_day_holds_no_value(tmp_path, monkeypatch, offset, features, first):
    snapshot = _snapshot()
    days = [stamp.date() for stamp in snapshot["ts"].to_list()]
    monkeypatch.setattr(alpha_c3, "FIRST_DAY", days[offset])
    inputs = _inputs(_reader(tmp_path, snapshot=snapshot))
    for feature in features:
        assert inputs.features[feature]["first"] == _yyyymmdd(days[first]), feature


def test_a_planted_long_state_veto_reads_bounds_excluding_zero(tmp_path, resamples):
    cells = _build(_reader(tmp_path))["cells"]

    veto = cells["mvrv|high|long|H7"]["log"]["pooled"]
    assert veto[2] == pytest.approx(math.log(0.95))
    assert veto[4] < 0 and veto[7] <= veto[8] < 0
    flat = {name: cell for name, cell in cells.items() if name.startswith("asopr|")}
    assert all("pooled" in flat[f"asopr|{tail}|long|H7"]["log"] for tail in TAILS)
    for name, cell in flat.items():
        for series, rows in cell.items():
            if "pooled" in rows:
                assert rows["pooled"][7] <= 0 <= rows["pooled"][8], (name, series)


def test_every_cell_is_contrasted_at_the_bonferroni_far_bounds(tmp_path, monkeypatch, resamples):
    real, fars = subjects.event_contrast_blocks, []

    def recording(flags, forwards, blocks, *, far):
        fars.append(far)
        return real(flags, forwards, blocks, far=far)

    monkeypatch.setattr(subjects, "event_contrast_blocks", recording)
    _build(_reader(tmp_path))

    assert len(fars) == 32 and all(far == alpha_c3.FAR for far in fars)


def test_one_draw_at_the_readings_constants_serves_every_cell(tmp_path, monkeypatch, resamples):
    real, draws = subjects.stationary_bootstrap_blocks, []

    def recording(*args, **kwargs):
        draws.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(subjects, "stationary_bootstrap_blocks", recording)
    _build(_reader(tmp_path))

    constants = {"mean_block": alpha_c3.MEAN_BLOCK, "n_resamples": alpha_c3.N_RESAMPLES, "seed": alpha_c3.SEED}
    assert draws == [((N_DAYS,), constants)]


def test_the_floors_years_count_the_pooled_events(tmp_path, resamples):
    reader = _reader(tmp_path)
    out = _build(reader)
    inputs = _inputs(reader)
    assert inputs.states["SOL"][:SOL_LISTED] == [None] * SOL_LISTED
    assert True in alpha_c3.flags(inputs.bands["mvrv"], inputs.states["BTC"], tail="high", in_state="long")[-30:]

    pooled = {name: cell["log"]["pooled"] for name, cell in out["cells"].items() if "pooled" in cell["log"]}
    assert "mvrv|high|long|H30" in pooled
    for name, row in pooled.items():
        assert sum(out["event_years"][name].values()) == row[0], name


def test_the_counts_precede_any_forward(tmp_path, monkeypatch, resamples):
    inputs_half, forwards, calls, held = subjects._c3_reading_inputs, alpha_c3.forwards, [], []

    def recording_inputs(*args):
        held.append(inputs_half(*args))
        calls.append("inputs")
        return held[-1]

    def recording_forwards(*args):
        calls.append("forward")
        return forwards(*args)

    monkeypatch.setattr(subjects, "_c3_reading_inputs", recording_inputs)
    monkeypatch.setattr(alpha_c3, "forwards", recording_forwards)
    out = _build(_reader(tmp_path))

    assert calls[0] == "inputs" and calls.count("inputs") == 1 and "forward" in calls
    assert out["counts"] == held[0].counts


def test_the_features_arm_and_counts_blocks_take_their_literal_shape(tmp_path, resamples):
    snapshot = _snapshot()
    reader = _reader(tmp_path, snapshot=snapshot)
    out = _build(reader)
    inputs = _inputs(reader)
    grid, days = inputs.grid, [stamp.date() for stamp in snapshot["ts"].to_list()]
    new_year = grid.index(datetime(2021, 1, 1, tzinfo=UTC))

    features, band = {}, {}
    for feature in FEATURES:
        band[feature] = alpha_c3.lagged(dict(zip(days, alpha_c3.bands(_column(snapshot, feature)), strict=True)), grid)
        assert band[feature][new_year] is not None, feature
        read = [(stamp.date() - timedelta(days=1), b) for stamp, b in zip(grid, band[feature], strict=True) if b is not None]
        band_days: dict[str, dict[str, int]] = {}
        for day, b in read:
            band_days.setdefault(str(day.year), {"low": 0, "mid": 0, "high": 0})[b] += 1
        features[feature] = {"first": _yyyymmdd(read[0][0]), "last": _yyyymmdd(read[-1][0]), "band_days": band_days}
    arm = {asset: {"long": held.count("long"), "flat": held.count("flat")} for asset, held in inputs.states.items()}
    counts = {}
    for feature in FEATURES:
        for tail in TAILS:
            for state in STATES:
                counts[f"{feature}|{tail}|{state}"] = {
                    asset: {"events": flags.count(True), "others": flags.count(False)}
                    for asset, flags in (
                        (asset, alpha_c3.flags(band[feature], held, tail=tail, in_state=state))
                        for asset, held in inputs.states.items()
                    )
                }

    assert out["features"] == features and out["arm"] == arm and out["counts"] == counts
    assert list(out["arm"]) == list(ASSETS) and len(out["counts"]) == 16
    assert all(list(by_asset) == list(ASSETS) for by_asset in out["counts"].values())
    for feature in FEATURES:
        block = out["features"][feature]
        assert (block["first"], block["last"]) == (20200930, 20210815), feature
        assert all(set(year) == {"low", "mid", "high"} for year in block["band_days"].values()), feature
        # The 1 January index reads 31 December, counted under 2020: 93 read days in it, not the 92 grid days.
        assert {year: sum(n.values()) for year, n in block["band_days"].items()} == {"2020": 93, "2021": N_DAYS - 93}


def test_the_metrics_hold_only_leaves_the_registry_stores(built):
    validate_metrics(built, "metrics")
    assert type(built["features"]["mvrv"]["first"]) is int


class _RaisingReader:
    @property
    def _root(self):
        raise AssertionError("read the data root")

    def read_series(self, dataset, relpath, window=None):
        raise AssertionError(f"read {relpath}")


def test_as_of_and_window_are_refused_before_any_read():
    with pytest.raises(subjects.SubjectError) as as_of:
        subjects._build_c3_onchain_reading(_RaisingReader(), DATASET, None, as_of="2021-08-16")
    assert str(as_of.value) == (
        "c3-onchain-reading evaluates a frozen snapshot whole, never the rolling dataset as of a day: drop --as-of"
    )
    window = ("2021-01-01 00:00:00+00:00", "2021-02-01 00:00:00+00:00")
    with pytest.raises(subjects.SubjectError) as windowed:
        subjects._build_c3_onchain_reading(_RaisingReader(), DATASET, window)
    assert str(windowed.value) == (
        "c3-onchain-reading over the window 2021-01-01 00:00:00+00:00 .. 2021-02-01 00:00:00+00:00: it reads its frozen sets "
        "whole, and the bands' history reaches back past any window's first day; drop --window"
    )


@pytest.mark.parametrize(
    "provenance",
    [
        pytest.param({"producer": "zcrypto onchain freeze"}, id="no-as-of-line"),
        pytest.param({"as_of_line": {"relpath": AS_OF_LINE["relpath"]}}, id="no-sha256"),
    ],
)
def test_a_snapshot_without_its_as_of_line_is_refused(tmp_path, provenance):
    with pytest.raises(subjects.SubjectError) as refused:
        _build(_reader(tmp_path, provenance=provenance))
    assert str(refused.value) == (
        f"c3-onchain-reading over the full history: {DATASET}/manifest.json's provenance names no as-of line's sha256"
    )


@pytest.mark.parametrize(
    ("dropped", "refused"),
    [pytest.param(100, True, id="after-the-first-priced-day"), pytest.param(10, False, id="before-the-first-priced-day")],
)
def test_a_snapshot_missing_a_day_after_its_first_priced_day_is_refused(tmp_path, resamples, dropped, refused):
    reader = _reader(tmp_path, snapshot=_snapshot(lead=300, unpriced=30, dropped=dropped))
    first = UNION_START.date() - timedelta(days=300)
    if not refused:
        assert set(_build(reader)) == subjects._C3_READING_KEYS
        return
    with pytest.raises(subjects.SubjectError) as caught:
        _build(reader)
    assert str(caught.value) == (
        f"c3-onchain-reading over the full history: {DATASET}/{SNAPSHOT_RELPATH}: its days are not consecutive from its "
        f"first priced day {first + timedelta(days=30)}: {first + timedelta(days=99)} is followed by "
        f"{first + timedelta(days=101)}"
    )


def test_a_snapshot_with_no_priced_day_is_refused(tmp_path):
    with pytest.raises(subjects.SubjectError) as refused:
        _build(_reader(tmp_path, snapshot=_snapshot(unpriced=LEAD + N_DAYS)))
    assert str(refused.value) == (
        f"c3-onchain-reading over the full history: {DATASET}/{SNAPSHOT_RELPATH}: no day's price is finite and above 0"
    )


@pytest.mark.parametrize(
    ("broken", "error"),
    [
        pytest.param((DATASET, SNAPSHOT_RELPATH), FileNotFoundError, id="the-snapshot"),
        pytest.param((DATASET, SNAPSHOT_RELPATH), pl.exceptions.ComputeError, id="the-snapshot-unparsed"),
        pytest.param(("ohlc-full", "ETH/EUR/1440.parquet"), pl.exceptions.ComputeError, id="a-leg"),
    ],
)
def test_an_unreadable_file_names_its_relpath(tmp_path, broken, error):
    with pytest.raises(subjects.SubjectError, match=re.escape(f"{'/'.join(broken)}: cannot read {broken[1]}")):
        _build(_reader(tmp_path, broken=broken, error=error))


@pytest.mark.parametrize("column", ["price", "market_cap", "realized_cap", "asopr"])
def test_a_snapshot_without_a_column_it_reads_is_refused_naming_its_relpath(tmp_path, column):
    with pytest.raises(subjects.SubjectError) as refused:
        _build(_reader(tmp_path, snapshot=_snapshot().drop(column)))
    assert str(refused.value).startswith(f"{DATASET}/{SNAPSHOT_RELPATH}: ") and f'"{column}"' in str(refused.value)


@pytest.mark.parametrize("spoil", ["absent", "unparseable"])
def test_an_unreadable_manifest_names_its_path(tmp_path, spoil):
    reader = _reader(tmp_path, manifest=False)
    if spoil == "unparseable":
        (tmp_path / DATASET).mkdir()
        (tmp_path / DATASET / "manifest.json").write_text("{not json")
    with pytest.raises(subjects.SubjectError) as refused:
        _build(reader)
    assert str(refused.value).startswith(f"c3-onchain-reading over the full history: {DATASET}/manifest.json cannot be read: ")


@pytest.mark.parametrize("error", [AlphaError, PortfolioError, ValidationError], ids=lambda error: error.__name__)
def test_a_compute_error_is_refused_over_the_full_history(tmp_path, monkeypatch, error):
    def raising(values):
        raise error("the planted cause")

    monkeypatch.setattr(alpha_c3, "bands", raising)
    with pytest.raises(subjects.SubjectError) as refused:
        _build(_reader(tmp_path))
    assert str(refused.value) == "c3-onchain-reading over the full history: the planted cause"


def test_the_subject_is_registered_as_a_reading():
    s = subjects.SUBJECTS[SUBJECT]
    assert (s.name, s.intervals, s.assets, s.build) == (SUBJECT, (1440,), (), subjects._build_c3_onchain_reading)
    assert s.spec == "docs/specs/00164-t0228-btc-onchain-design.md" and s.seeds == (42,)
    assert s.metric_keys == subjects._C3_READING_KEYS
    assert s.verdict is None and s.no_verdict is None and s.incumbent is None and s.family is None and s.n_trials is None
