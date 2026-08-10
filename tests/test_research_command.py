"""`zcrypto research eval` — the committed door to the registry (spec 00086).

Every register-path test monkeypatches BOTH `cli.research.command._DATA_ROOT` and
`cli.research.command._REGISTRY`: the defaults are repo-anchored, so a test that patched only the
data root would compute against a fixture and then append to the real committed registry.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.ohlc.dataset import to_frame, write_parquet
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig
from cli.registry.record import compute_hash
from cli.research import subjects

runner = CliRunner()

_DAY = 86400
_EPOCH_2020 = 1577836800  # 2020-01-01T00:00:00Z


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
    """A subject whose build returns fixed metrics over whatever the reader hands it. It declares its
    OWN assets — `required_relpaths` derives from assets x intervals, so the stub needs only the one
    BTC file rather than the production config's ten."""

    def build(reader, dataset, window):
        reader.read_series(dataset, "BTC/EUR/1440.parquet", window=window)
        return {"sharpe": 1.0}

    monkeypatch.setitem(subjects.SUBJECTS, "stub", subjects.Subject("stub", (1440,), ("BTC",), build))


def _anchor(monkeypatch, data_root: Path, registry: Path | None = None):
    monkeypatch.setattr("cli.research.command._DATA_ROOT", data_root)
    monkeypatch.setattr("cli.research.command._REGISTRY", registry if registry is not None else data_root / "never.jsonl")


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


def test_a_second_trial_in_a_family_needs_n_trials_above_the_recorded_count(tmp_path, monkeypatch):
    """The registry refuses an append whose `n_trials_in_family` is below the family's prior count
    plus one — so `--n-trials` must be a real flag: a hardcoded 1 forbids every second trial."""
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
