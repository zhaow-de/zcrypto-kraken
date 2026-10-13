"""`zcrypto research eval` — the committed door to the registry (spec 00086).

`cli.research.command._REGISTRY` defaults to the committed ledger, so a register run reaching that
default appends a fabricated row to it; `_registry_default_off_the_committed_ledger` is the guard."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.alpha.a1 import _asset_returns
from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import (
    net_of_cost,
    per_year_engaged_counts,
    per_year_max_drawdown,
    per_year_positions_differ,
    per_year_turnover,
    scale_positions,
)
from cli.derivatives.funding import PERP_SYMBOLS
from cli.features.derivatives import coverage_by_year
from cli.ohlc.dataset import to_frame, write_parquet
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, _ffill_btc
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost, calendar_year_slices
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.rolling_fixtures import HOLE, write_chain

runner = CliRunner()

_DAY = 86400
_EPOCH_2020 = 1577836800  # 2020-01-01T00:00:00Z
_COMMITTED_REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"


def _rows(n: int, *, phase: float = 0.0, start: int = _EPOCH_2020, step: int = _DAY):
    """A trending, oscillating close series — non-degenerate enough that the gated, vol-targeted
    book the production builders produce has non-zero variance (Sharpe is undefined otherwise)."""
    out = []
    for i in range(n):
        close = 100.0 * (1.001**i) * (1 + 0.05 * math.sin(i / 7.0 + phase))
        out.append([start + i * step, f"{close}", f"{close * 1.01}", f"{close * 0.99}", f"{close}", f"{close}", "10", 3])
    return out


def _write_series(root: Path, dataset: str, relpath: str, n: int, *, phase: float = 0.0, step: int = _DAY) -> None:
    write_parquet(to_frame(_rows(n, phase=phase, step=step)), root / dataset / relpath)


def _stub_dataset(tmp_path: Path, dataset: str = "ohlc-test") -> Path:
    root = tmp_path / "data"
    _write_series(root, dataset, "BTC/EUR/1440.parquet", 10)
    return root


def _daily_dataset(tmp_path: Path, n: int = 600, dataset: str = "ohlc-test") -> Path:
    """One daily file per production asset — enough bars to clear the 200-bar gate warm-up."""
    root = tmp_path / "data"
    for i, asset in enumerate(CrossfreqSystemConfig().assets):
        _write_series(root, dataset, f"{asset}/EUR/1440.parquet", n, phase=i * 0.7)
    return root


def _stub_subject(monkeypatch):
    """A subject returning fixed metrics over whatever the reader hands it, declaring only BTC so
    `required_relpaths` demands just the one file `_stub_dataset` writes."""

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        reader.read_series(dataset, "BTC/EUR/1440.parquet", window=window)
        return {"sharpe": 1.0}

    monkeypatch.setitem(subjects.SUBJECTS, "stub", subjects.Subject("stub", (1440,), ("BTC",), build))


def _anchor(monkeypatch, data_root: Path, registry: Path | None = None):
    monkeypatch.setattr("cli.research.command._DATA_ROOT", data_root)
    monkeypatch.setattr("cli.research.command._REGISTRY", registry if registry is not None else data_root / "never.jsonl")


@pytest.fixture(autouse=True)
def _registry_default_off_the_committed_ledger(tmp_path, monkeypatch):
    """`TrialRegistry(registry or _REGISTRY).append` writes wherever `_REGISTRY` points, so no test
    in this module may start or end with it on the committed ledger."""
    monkeypatch.setattr("cli.research.command._REGISTRY", tmp_path / "unanchored-registry.jsonl")
    yield
    assert research_command._REGISTRY != _COMMITTED_REGISTRY, (
        "this test left cli.research.command._REGISTRY on the committed trial registry"
    )


def _register_args(registry: Path, *, n_trials: int, family: str = "STUB") -> list[str]:
    return [
        "--register",
        "--registry",
        str(registry),
        "--iteration",
        "iter-001",
        "--family",
        family,
        "--spec-hash",
        "s",
        "--verdict",
        "adopt",
        "--n-trials",
        str(n_trials),
    ]


def test_eval_reports_the_block_and_writes_no_record_without_register(tmp_path, monkeypatch):
    root = _stub_dataset(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _stub_subject(monkeypatch)
    _anchor(monkeypatch, root, registry)

    result = runner.invoke(app, ["research", "eval", "--subject", "stub", "--dataset", "ohlc-test"])

    assert result.exit_code == 0, result.output
    assert '"rows": 10' in result.output
    assert "inert (0 vouched hashes)" in result.output
    assert not registry.exists(), "a read-only eval must not touch the registry"


def test_register_appends_one_schema_4_record_whose_hash_derives_from_the_observed_block(tmp_path, monkeypatch):
    root = _stub_dataset(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _stub_subject(monkeypatch)
    _anchor(monkeypatch, root, registry)

    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "stub", "--dataset", "ohlc-test", *_register_args(registry, n_trials=1)],
    )

    assert result.exit_code == 0, result.output
    lines = registry.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["schema_version"] == 4
    assert record["dataset_hash"] == compute_hash(record["datasets"])
    assert list(record["datasets"]["ohlc-test"]["files"]) == ["BTC/EUR/1440.parquet"]
    assert record["run_ref"].startswith("cli/research/command.py")


def test_a_register_run_that_forgets_to_anchor_lands_off_the_committed_ledger(tmp_path, monkeypatch):
    """The case the autouse fixture exists for: no `_anchor` and no `--registry`, so the append
    resolves the module default, and the row must land on the fixture's file with the committed
    ledger byte-identical. The pre-invoke assertion is what keeps this test from being the hazard
    itself if the fixture ever goes."""
    root = _stub_dataset(tmp_path)
    _stub_subject(monkeypatch)
    monkeypatch.setattr("cli.research.command._DATA_ROOT", root)
    assert research_command._REGISTRY != _COMMITTED_REGISTRY
    before = _COMMITTED_REGISTRY.read_bytes()

    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "stub", "--dataset", "ohlc-test", "--register"]
        + ["--iteration", "iter-001", "--family", "STUB", "--spec-hash", "s", "--verdict", "adopt", "--n-trials", "1"],
    )

    assert result.exit_code == 0, result.output
    assert len(research_command._REGISTRY.read_text().splitlines()) == 1
    assert _COMMITTED_REGISTRY.read_bytes() == before


def test_a_second_trial_in_a_family_needs_n_trials_above_the_recorded_count(tmp_path, monkeypatch):
    """A hardcoded `--n-trials` of 1 would forbid every second trial in a family."""
    root = _stub_dataset(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _stub_subject(monkeypatch)
    _anchor(monkeypatch, root, registry)
    base = ["research", "eval", "--subject", "stub", "--dataset", "ohlc-test"]

    assert runner.invoke(app, [*base, *_register_args(registry, n_trials=1)]).exit_code == 0

    repeat = runner.invoke(app, [*base, *_register_args(registry, n_trials=1)])
    assert repeat.exit_code != 0
    assert "n_trials_in_family" in repeat.output
    assert len(registry.read_text().splitlines()) == 1

    second = runner.invoke(app, [*base, *_register_args(registry, n_trials=2)])
    assert second.exit_code == 0, second.output
    assert len(registry.read_text().splitlines()) == 2


def test_register_without_the_caller_fields_is_refused_naming_them(tmp_path, monkeypatch):
    root = _stub_dataset(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _stub_subject(monkeypatch)
    _anchor(monkeypatch, root, registry)

    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "stub", "--dataset", "ohlc-test", "--register", "--registry", str(registry)],
    )

    assert result.exit_code != 0
    for flag in ("--iteration", "--family", "--spec-hash", "--verdict", "--n-trials"):
        assert flag in result.output
    assert not registry.exists()


def test_a_dataset_missing_required_series_is_refused_naming_every_missing_file(tmp_path, monkeypatch):
    """Plurality is the point: naming one file is indistinguishable from the first read's own
    FileNotFoundError — the sweep must run before any read and report the whole shortfall."""
    root = _daily_dataset(tmp_path, n=20)  # daily only: every 4h series is absent
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "record44-crossfreq", "--dataset", "ohlc-test"])

    assert result.exit_code != 0
    named = [a for a in CrossfreqSystemConfig().assets if f"{a}/EUR/240.parquet" in result.output]
    assert len(named) >= 2, result.output


def test_an_unknown_subject_is_refused_listing_the_known_ones(tmp_path, monkeypatch):
    _anchor(monkeypatch, _stub_dataset(tmp_path))

    result = runner.invoke(app, ["research", "eval", "--subject", "nope", "--dataset", "ohlc-test"])

    assert result.exit_code != 0
    assert "record44-crossfreq" in result.output
    assert "record33-combined" in result.output


def _block_and_metrics(output: str) -> dict:
    """The JSON report the command prints after the human-readable lines."""
    start = output.index("{")
    return json.loads(output[start:])


# `record33-combined`'s committed headline keys, pinned here as literals: reading them back off the
# subject under test would assert nothing about which metrics the command actually reports.
_COMBINED_METRIC_KEYS = {"ann_sharpe_noc", "per_period_sharpe", "bench_ann_sharpe", "cap_breach_bars", "n_periods"}


def test_a_production_subject_honours_window_all_the_way_down_to_the_reads(tmp_path, monkeypatch):
    """The pass-through proof: `--window` must reach `ObservedReader.read_series`. If the closure
    drops it the run silently fits FULL history while its block stays self-consistent."""
    root = _daily_dataset(tmp_path, n=600)
    _anchor(monkeypatch, root)
    base = ["research", "eval", "--subject", "record33-combined", "--dataset", "ohlc-test"]

    full = runner.invoke(app, base)
    assert full.exit_code == 0, full.output
    windowed = runner.invoke(app, [*base, "--window", "2020-06-01 00:00:00+00:00", "2021-06-01 00:00:00+00:00"])
    assert windowed.exit_code == 0, windowed.output

    full_report, win_report = _block_and_metrics(full.output), _block_and_metrics(windowed.output)
    full_block = full_report["datasets"]["ohlc-test"]
    win_block = win_report["datasets"]["ohlc-test"]
    assert win_block["rows"] < full_block["rows"]
    assert win_block["span"][0] > full_block["span"][0]
    assert win_block["span"][1] < full_block["span"][1]
    assert set(win_report["metrics"]) == _COMBINED_METRIC_KEYS
    assert set(full_report["metrics"]) == _COMBINED_METRIC_KEYS
    assert win_report["metrics"] != full_report["metrics"], "a windowed fit that matches the full fit read no window"


def test_required_relpaths_is_the_cross_product_of_assets_and_intervals():
    subject = subjects.SUBJECTS["record44-crossfreq"]
    relpaths = subjects.required_relpaths(subject)
    assert len(relpaths) == len(subject.assets) * len(subject.intervals)
    assert "BTC/EUR/240.parquet" in relpaths and "BTC/EUR/1440.parquet" in relpaths


_EUR_PAIRS = tuple(f"{a}/EUR" for a in CrossfreqSystemConfig().assets)
_BASE_LINE = "index/2026/09/30.json"


def _rolling_set(tmp_path: Path, *, pairs: tuple[str, ...] = _EUR_PAIRS, **chain) -> Path:
    root = tmp_path / "data"
    write_chain(root / "ohlc-rolling", pairs=pairs, **chain)
    return root


def _rolling_subject(monkeypatch) -> list:
    """A subject over the ten assets reading 1440 as the production builds do, returning fixed metrics so no fit's minimum
    history applies to a four-day chain; the list it returns gains each build's `as_of`."""
    calls = []

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        calls.append(as_of)
        subjects._capturing_union(reader, dataset, 1440, window, as_of, accept_holes)
        return {"sharpe": 1.0}

    assets = CrossfreqSystemConfig().assets
    monkeypatch.setitem(subjects.SUBJECTS, "rolling-stub", subjects.Subject("rolling-stub", (1440,), assets, build))
    return calls


def _rolling_eval(*args: str) -> list[str]:
    return ["research", "eval", "--subject", "rolling-stub", "--dataset", "ohlc-rolling", *args]


def test_eval_on_a_chained_set_requires_as_of(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path))
    calls = _rolling_subject(monkeypatch)

    result = runner.invoke(app, _rolling_eval())

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--as-of" in result.output
    assert calls == []


@pytest.mark.parametrize("flags", [["--as-of", "2026-10-03"], ["--accept-holes"]], ids=["as-of", "accept-holes"])
def test_eval_on_an_unchained_set_refuses_as_of(tmp_path, monkeypatch, flags):
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch)

    result = runner.invoke(app, ["research", "eval", "--subject", "stub", "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert flags[0] in result.output


def test_eval_on_the_rolling_set_records_the_as_of_line(tmp_path, monkeypatch):
    root = _rolling_set(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, root, registry)
    _rolling_subject(monkeypatch)
    line = "index/2026/10/02.json"
    digest = hashlib.sha256((root / "ohlc-rolling" / line).read_bytes()).hexdigest()

    result = runner.invoke(app, _rolling_eval("--as-of", "2026-10-02", *_register_args(registry, n_trials=1)))

    assert result.exit_code == 0, result.output
    printed = result.output.splitlines()
    assert printed[printed.index("window: full history") + 1] == "as of: 2026-10-02"
    record = json.loads(registry.read_text())
    assert record["datasets"] == {
        "ohlc-rolling": {
            "files": {line: digest},
            "rows": 30,
            "span": ["2026-09-30 00:00:00+00:00", "2026-10-02 00:00:00+00:00"],
        }
    }
    assert record["dataset_hash"] == compute_hash(record["datasets"])
    report, _ = json.JSONDecoder().raw_decode(result.output, result.output.index("{"))
    assert report["vouched"] == {"ohlc-rolling": f"chained (as of 2026-10-02, line {digest[:12]})"}
    assert "inert" not in result.output


def test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path, holes={date(2026, 10, 2): {"BTC/EUR", "SOL/EUR"}}))
    _rolling_subject(monkeypatch)

    refused = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03"))

    assert refused.exit_code == 1
    assert isinstance(refused.exception, SystemExit)
    assert f"BTC/EUR has a hole on 2026-10-02 ({HOLE}) inside the window read (--accept-holes leaves the day out)" in refused.output

    accepted = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03", "--accept-holes"))

    assert accepted.exit_code == 0, accepted.output
    holes = [text for text in accepted.output.splitlines() if text.startswith("hole: ")]
    assert holes == ["hole: BTC/EUR 2026-10-02", "hole: SOL/EUR 2026-10-02"]
    assert _block_and_metrics(accepted.output)["datasets"]["ohlc-rolling"]["rows"] == 38


def test_a_chained_set_missing_a_required_pair_is_refused_naming_it(tmp_path, monkeypatch):
    held = tuple(pair for pair in _EUR_PAIRS if pair not in ("AVAX/EUR", "XRP/EUR"))
    _anchor(monkeypatch, _rolling_set(tmp_path, pairs=held))
    calls = _rolling_subject(monkeypatch)

    result = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03"))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "AVAX/EUR" in result.output and "XRP/EUR" in result.output
    assert [pair for pair in held if pair in result.output] == []
    assert calls == []


def test_eval_refuses_a_chained_set_whose_base_line_cannot_be_read(tmp_path, monkeypatch):
    root = _rolling_set(tmp_path)
    (root / "ohlc-rolling" / _BASE_LINE).write_bytes(b"{}")
    _anchor(monkeypatch, root)
    _rolling_subject(monkeypatch)

    result = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03"))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert _BASE_LINE in result.output


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_eval_refuses_a_rolling_index_it_cannot_list_in_one_line(tmp_path, monkeypatch):
    root = _rolling_set(tmp_path)
    month = root / "ohlc-rolling" / "index/2026/10"
    _anchor(monkeypatch, root)
    calls = _rolling_subject(monkeypatch)
    os.chmod(month, 0o000)
    try:
        result = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03"))
    finally:
        os.chmod(month, 0o755)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"dataset 'ohlc-rolling': [Errno 13] Permission denied: '{month}'" in result.output
    assert calls == []


def test_eval_on_an_absent_dataset_names_it_and_the_fetch(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    _anchor(monkeypatch, root)
    calls = _rolling_subject(monkeypatch)

    result = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03"))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"dataset 'ohlc-rolling' is absent: no directory {root / 'ohlc-rolling'}; zcrypto data fetch" in result.output
    assert "frozen" not in result.output
    assert calls == []


def test_the_window_reaches_the_rolling_reads(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path))
    _rolling_subject(monkeypatch)

    result = runner.invoke(
        app, _rolling_eval("--as-of", "2026-10-03", "--window", "2026-10-01 00:00:00+00:00", "2026-10-02 00:00:00+00:00")
    )

    assert result.exit_code == 0, result.output
    block = _block_and_metrics(result.output)["datasets"]["ohlc-rolling"]
    assert block["rows"] == 20
    assert block["span"] == ["2026-10-01 00:00:00+00:00", "2026-10-02 00:00:00+00:00"]


def test_the_b2_subject_is_registered_over_the_ten_assets_4h_series():
    subject = subjects.SUBJECTS["b2-funding-derisk"]
    assert subject.name == "b2-funding-derisk"
    assert subject.intervals == (240,)
    assert subject.assets == CrossfreqSystemConfig().assets
    assert subject.build is subjects._build_b2_funding_derisk


# Spec 00128 D7's metric keys, pinned as literals for the reason `_COMBINED_METRIC_KEYS` is.
_B2_METRIC_KEYS = {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe_4h",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_passes",
    "spa_p_decisive_b30_s42",
    "spa_p_decisive_b30_s7",
    "spa_p_decisive_b30_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_2021",
    "head_to_head_spa_p_2021",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_reduction_pct",
    "turnover_a",
    "turnover_b",
    "stamps_positions_differ",
    "engaged_per_year",
    "positions_differ_per_year",
    "turnover_a_per_year",
    "turnover_b_per_year",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "binperp_funding_z30d_coverage",
}
_B2_GRID = ((30, 42), (30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))
_B2_FLAGS = ("dsr_pass", "spa_pass", "cost_stress_pass", "worst_slice_pass")
_B2_ASSETS = CrossfreqSystemConfig().assets
_B2_START = datetime(2020, 10, 1, tzinfo=UTC)
_B2_BARS = 1_640
_B2_WINDOW_BARS = 1_620
# (first bar, bars, depth) on every asset: December 2020's fall is the window's deepest, February 2021's the deepest from
# 2021-01-01 and the one the funding spikes sit inside.
_B2_FALLS = ((420, 24, 0.40), (822, 24, 0.25))
_B2_FUNDING_FROM = datetime(2020, 8, 15, tzinfo=UTC)
_B2_PRINTS = 1_000
_B2_SPIKE_PRINTS = 6
_B2_NEVER_SPIKES = "XRP"


def _b2_ohlc_rows(phase: float, start: datetime, flat: bool) -> list[list]:
    rows = []
    for i, row in enumerate(_rows(_B2_BARS, phase=phase, start=int(start.timestamp()), step=4 * 3600)):
        factor = math.prod(1 - depth * min(max((i - first) / bars, 0.0), 1.0) for first, bars, depth in _B2_FALLS)
        prices = ("100.0", "101.0", "99.0", "100.0", "100.0") if flat else (f"{float(v) * factor}" for v in row[1:6])
        rows.append([row[0], *prices, *row[6:]])
    return rows


def _b2_dataset(tmp_path: Path, *, start: datetime = _B2_START, flat: bool = False) -> Path:
    """The ten 4h series and a `derivatives-funding` set whose 8h prints open 47 days before `_B2_START`; every perp but
    one spikes inside the second fall, each from its own print, so the overlay de-risks each asset at its own stamps."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        write_parquet(to_frame(_b2_ohlc_rows(i * 0.7, start, flat)), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    stamps = [_B2_FUNDING_FROM + timedelta(hours=8 * j) for j in range(_B2_PRINTS)]
    second_fall = _B2_START + timedelta(hours=4 * _B2_FALLS[1][0])
    for i, asset in enumerate(_B2_ASSETS):
        rates = [0.0001 * (1 + 0.5 * math.sin(j + i)) for j in range(_B2_PRINTS)]
        if asset != _B2_NEVER_SPIKES:
            first = stamps.index(second_fall + timedelta(hours=8 * i))
            rates[first : first + _B2_SPIKE_PRINTS] = [0.003] * _B2_SPIKE_PRINTS
        frame = pl.DataFrame(
            {"ts": stamps, "funding_rate": rates, "interval_hours": [8] * _B2_PRINTS},
            schema={"ts": pl.Datetime("us", "UTC"), "funding_rate": pl.Float64, "interval_hours": pl.Int64},
        )
        write_parquet(frame, root / "derivatives-funding" / PERP_SYMBOLS[asset] / "funding.parquet")
    return root


def _recording(monkeypatch, name: str, rewrite) -> list[tuple[dict, dict]]:
    """`subjects.<name>` as a pass-through keeping each call's arguments, bound with defaults applied, and the result
    `rewrite` makes of the real one."""
    real = getattr(subjects, name)
    signature = inspect.signature(real)
    calls = []

    def wrapper(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        result = rewrite(dict(bound.arguments), real(*args, **kwargs))
        calls.append((dict(bound.arguments), result))
        return result

    monkeypatch.setattr(subjects, name, wrapper)
    return calls


def _kill_bar_sentinels(cell, *, inverted: bool) -> dict:
    """Per-call sentinels for the eight keys the subject reads, so a float or a flag read off the wrong cell or key, a flag
    read off another flag, or `passes` read off a flag or another cell fails the record's comparison: the flags are ints
    other than 0 and 1, which the subject's `int()` and the registry's leaf check carry through."""
    i = (*_B2_GRID, "A").index(cell)
    if cell == "A":
        floats = {"dsr": 0.91, "spa_p_value": 0.81, "spa_p_value_full": 0.71}
    else:
        floats = {"dsr": 0.11 + i / 100, "spa_p_value": 0.21 + i / 100, "spa_p_value_full": 0.31 + i / 100}
    # B's `passes` is true at the headline alone, or false there alone, so an `all` or an `any` over the grid moves it;
    # arm A's is false, told from B's headline by the first parametrisation and from B's other cells by the second.
    passes = cell != "A" and (cell == (30, 42)) != inverted
    return floats | {"passes": passes} | {flag: 10 * (i + 1) + j for j, flag in enumerate(_B2_FLAGS)}


@pytest.mark.parametrize("inverted", [False, True], ids=["passes-at-the-headline", "passes-off-the-headline"])
def test_the_b2_subject_registers_each_metric_from_its_own_call(tmp_path, monkeypatch, inverted):
    root = _b2_dataset(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, root, registry)
    ts = [_B2_START + timedelta(hours=4 * k) for k in range(_B2_WINDOW_BARS)]
    close = [t + timedelta(hours=4) for t in ts[:-1]]
    k21 = next(k for k, t in enumerate(close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert k21 == 551
    window = (str(ts[0]), str(ts[-1]))

    inputs = subjects._b2_inputs(ObservedReader(root), "ohlc-test", window, None, False)
    assert inputs.h4_ts == ts
    cost = CrossfreqSystemConfig().cost_per_side
    arm_a, scales = inputs.arm_a, inputs.scales
    arm_b = scale_positions(arm_a, scales)
    fed = _ffill_btc(inputs.h4_prices)
    returns = {a: _asset_returns(fed[a]) for a in _B2_ASSETS}
    net_a = net_of_cost(arm_a, returns, cost_per_side=cost)
    net_b = net_of_cost(arm_b, returns, cost_per_side=cost)
    net_a_x15 = net_of_cost(arm_a, returns, cost_per_side=1.5 * cost)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    slices_a, slices_b, slices_bench = (
        {year: s for year, s in calendar_year_slices(series, ts).items() if year != "2020"} for series in (net_a, net_b, bench)
    )

    assert net_b[k21:] != net_a[k21:]
    assert abs(max_drawdown(net_b[k21:]) - max_drawdown(net_a[k21:])) > 1e-9
    assert abs(max_drawdown(net_b[k21:]) - max_drawdown(net_b)) > 1e-9
    assert abs(max_drawdown(net_a[k21:]) - max_drawdown(net_a)) > 1e-9
    assert abs(book_turnover(arm_b) - book_turnover(arm_a)) > 1e-9
    assert scales[_B2_NEVER_SPIKES] == [1.0] * len(close)
    assert len({tuple(s) for s in scales.values()}) == len(_B2_ASSETS)
    assert list(slices_b) == list(slices_bench) == ["2021"]

    def kill_bar(arguments, result):
        book = arguments["book_net_returns"]
        cell = "A" if book == net_a else (arguments["mean_block"], arguments["seed"]) if book == net_b else None
        return result | _kill_bar_sentinels(cell, inverted=inverted) if cell in ("A", *_B2_GRID) else result

    def head_to_head(arguments, result):
        p = {len(net_b): 0.41, len(net_b) - k21: 0.42}.get(len(arguments["book_net_of_cost"]))
        return result if p is None else result | {"spa_p_value": p}

    kill_calls = _recording(monkeypatch, "a1_kill_bar", kill_bar)
    verdict_calls = _recording(monkeypatch, "net_of_cost_verdict", head_to_head)
    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "b2-funding-derisk", "--dataset", "ohlc-test", "--window", *window]
        + _register_args(registry, n_trials=1),
    )
    assert result.exit_code == 0, result.output

    bar = {
        "n_trials": 1,
        "var_trials": 0.0,
        "benchmark_net_returns": bench,
        "benchmark_slices": slices_bench,
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    arm_a_call = {"book_net_returns": net_a, "mean_block": 30, "seed": 42, "cost_stressed_returns": net_a_x15}
    want = [bar | arm_a_call | {"regime_slices": slices_a}] + [
        bar | {"book_net_returns": net_b, "mean_block": b, "seed": s, "cost_stressed_returns": net_b_x15, "regime_slices": slices_b}
        for b, s in _B2_GRID
    ]

    def by_cell(arguments):
        return arguments["book_net_returns"] == net_a, arguments["mean_block"], arguments["seed"]

    assert sorted((arguments for arguments, _ in kill_calls), key=by_cell) == sorted(want, key=by_cell)
    verdict = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    assert [arguments for arguments, _ in verdict_calls] == [
        {"book_net_of_cost": net_b, "benchmark_net_of_cost": net_a} | verdict,
        {"book_net_of_cost": net_b[k21:], "benchmark_net_of_cost": net_a[k21:]} | verdict,
    ]
    full, from_2021 = (outcome for _, outcome in verdict_calls)
    assert full["mean_outperformance"] != from_2021["mean_outperformance"]
    assert (full["spa_p_value"], from_2021["spa_p_value"]) == (0.41, 0.42)

    results = {
        "A" if arguments["book_net_returns"] == net_a else (arguments["mean_block"], arguments["seed"]): outcome
        for arguments, outcome in kill_calls
    }
    headline = results[(30, 42)]
    drawdown_b, drawdown_a = max_drawdown(net_b[k21:]), max_drawdown(net_a[k21:])
    differ = per_year_positions_differ(arm_a, arm_b, close)
    expected = {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=2190),
        "ann_sharpe_noc_decisive": sharpe(net_b[1380:], periods_per_year=2190),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": int(headline["dsr_pass"]),
        "spa_pass": int(headline["spa_pass"]),
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": int(headline["cost_stress_pass"]),
        "worst_slice_relative_pass": int(headline["worst_slice_pass"]),
        "passes": int(headline["passes"]),
        "decisive_start": 1380,
        "n_resamples": 2000,
        "arm_a_passes": int(results["A"]["passes"]),
        **{f"spa_p_decisive_b{b}_s{s}": results[(b, s)]["spa_p_value"] for b, s in _B2_GRID},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2021": from_2021["mean_outperformance"],
        "head_to_head_spa_p_2021": from_2021["spa_p_value"],
        "max_drawdown": drawdown_b,
        "arm_a_max_drawdown": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        "turnover_a": book_turnover(arm_a),
        "turnover_b": book_turnover(arm_b),
        "stamps_positions_differ": sum(differ.values()),
        "engaged_per_year": per_year_engaged_counts(arm_a, scales, close),
        "positions_differ_per_year": differ,
        "turnover_a_per_year": per_year_turnover(arm_a, close),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "binperp_funding_z30d_coverage": {
            a: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(close, inputs.binperp_funding_z30d[a]).items()}
            for a in _B2_ASSETS
        },
    }
    record = json.loads(registry.read_text())
    assert set(record["metrics"]) == _B2_METRIC_KEYS
    assert record["metrics"] == expected
    assert set(record["datasets"]["derivatives-funding"]["files"]) == {f"{PERP_SYMBOLS[a]}/funding.parquet" for a in _B2_ASSETS}
    ohlc = record["datasets"]["ohlc-test"]
    assert ohlc["rows"] == len(_B2_ASSETS) * _B2_WINDOW_BARS < len(_B2_ASSETS) * _B2_BARS
    assert ohlc["span"] == [str(ts[0]), str(ts[-1])]


_B2_SPOILT = PERP_SYMBOLS["SOL"]
# From here 1,469 return indices close before 2021-01-01.
_B2_FROM_MAY_2020 = datetime(2020, 5, 1, tzinfo=UTC)
_B2_IN_2026 = datetime(2026, 1, 1, tzinfo=UTC)


def _b2_eval(start: datetime, bars: int) -> list[str]:
    end = start + timedelta(hours=4 * (bars - 1))
    return ["research", "eval", "--subject", "b2-funding-derisk", "--dataset", "ohlc-test", "--window", str(start), str(end)]


def _a_print_61s_late(path: Path) -> None:
    frame = pl.read_parquet(path)
    stamps = frame["ts"].to_list()
    stamps[5] += timedelta(seconds=61)
    frame.with_columns(ts=pl.Series(stamps, dtype=frame.schema["ts"])).write_parquet(path)


@pytest.mark.parametrize(
    ("spoil", "cause"),
    [
        pytest.param(Path.unlink, "No such file or directory", id="missing"),
        pytest.param(lambda path: path.write_bytes(b"not a parquet file"), "File out of specification", id="not-parquet"),
        pytest.param(
            lambda path: pl.read_parquet(path).drop("funding_rate").write_parquet(path),
            '"funding_rate" not found',
            id="no-rate-column",
        ),
        pytest.param(lambda path: pl.read_parquet(path).clear().write_parquet(path), "zero rows", id="empty"),
        pytest.param(_a_print_61s_late, "beyond the 60 s settlement tolerance", id="a-print-61s-past-its-hour"),
        pytest.param(
            lambda path: pl.read_parquet(path).with_columns(funding_rate=math.nan).write_parquet(path),
            "must be finite numbers or None",
            id="non-finite-rates",
        ),
    ],
)
def test_the_b2_subject_refuses_a_funding_file_it_cannot_read_naming_it(tmp_path, monkeypatch, spoil, cause):
    root = _b2_dataset(tmp_path)
    spoil(root / "derivatives-funding" / _B2_SPOILT / "funding.parquet")
    _anchor(monkeypatch, root)

    result = runner.invoke(app, _b2_eval(_B2_START, _B2_WINDOW_BARS))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"derivatives-funding/{_B2_SPOILT}/funding.parquet" in result.output
    assert cause in result.output


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_the_b2_subject_refuses_a_funding_file_it_may_not_open_naming_it(tmp_path, monkeypatch):
    root = _b2_dataset(tmp_path)
    spoilt = root / "derivatives-funding" / _B2_SPOILT / "funding.parquet"
    _anchor(monkeypatch, root)
    os.chmod(spoilt, 0o000)
    try:
        result = runner.invoke(app, _b2_eval(_B2_START, _B2_WINDOW_BARS))
    finally:
        os.chmod(spoilt, 0o644)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"derivatives-funding/{_B2_SPOILT}/funding.parquet" in result.output
    assert "Permission denied" in result.output


@pytest.mark.parametrize(
    ("start", "bars", "flat", "cause"),
    [
        pytest.param(
            _B2_START,
            1_382,
            False,
            "it holds 1381 return indices, and the kill bar's decisive window opens at index 1380 and needs 2",
            id="one-index-short",
        ),
        pytest.param(
            _B2_FROM_MAY_2020,
            1_471,
            False,
            "1 of its return indices close at or after 2021-01-01T00:00Z, and the from-2021 head-to-head needs 2",
            id="one-index-into-2021",
        ),
        pytest.param(
            _B2_IN_2026,
            _B2_BARS,
            False,
            "none of its return indices closes in a calendar year the worst-slice leg reads",
            id="inside-2026",
        ),
        pytest.param(_B2_START, _B2_WINDOW_BARS, True, "degenerate backtest: returns have zero variance", id="arms-never-trade"),
        pytest.param(
            _B2_FROM_MAY_2020,
            1_472,
            False,
            "arm A never draws down from 2021-01-01T00:00Z, so max_drawdown_reduction_pct divides by zero",
            id="arm-a-never-draws-down-from-2021",
        ),
    ],
)
def test_the_b2_subject_refuses_a_window_it_cannot_evaluate_naming_it(tmp_path, monkeypatch, start, bars, flat, cause):
    _anchor(monkeypatch, _b2_dataset(tmp_path, start=start, flat=flat))
    args = _b2_eval(start, bars)

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"b2-funding-derisk over the window {args[-2]} .. {args[-1]}: {cause}" in result.output


def test_the_b2_subject_refuses_a_window_its_benchmark_never_trades_naming_it(tmp_path, monkeypatch):
    """A window the frozen benchmark's 1,200-bar gate never opens over leaves its returns flat; the fixture's gate opens,
    so the flat series is handed in."""
    _anchor(monkeypatch, _b2_dataset(tmp_path))
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", lambda prices, *, cost_per_side: [0.0] * (len(prices["BTC"]) - 1))
    args = _b2_eval(_B2_START, _B2_WINDOW_BARS)

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"b2-funding-derisk over the window {args[-2]} .. {args[-1]}: no non-degenerate slice to compare" in result.output
