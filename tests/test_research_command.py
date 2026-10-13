"""`zcrypto research eval` — the committed door to the registry (spec 00086).

`cli.research.command._REGISTRY` defaults to the committed ledger, so a register run reaching that
default appends a fabricated row to it; `_registry_default_off_the_committed_ledger` is the guard."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
import typer
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
from cli.alpha.errors import AlphaError
from cli.backtest.errors import BacktestError
from cli.benchmark.errors import BenchmarkError
from cli.derivatives.funding import PERP_SYMBOLS
from cli.features.derivatives import coverage_by_year
from cli.features.errors import FeatureError
from cli.ohlc.dataset import to_frame, write_parquet
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, _ffill_btc
from cli.portfolio.errors import PortfolioError
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost, calendar_year_slices
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.risk.errors import RiskError
from cli.validation import ValidationError, max_drawdown, sharpe
from tests.rolling_fixtures import HOLE, write_chain

runner = CliRunner()

_DAY = 86400
_EPOCH_2020 = 1577836800  # 2020-01-01T00:00:00Z
_REPO = Path(__file__).resolve().parents[1]
_COMMITTED_REGISTRY = _REPO / "docs" / "reference" / "trial-registry.jsonl"
_CLEAN_HEAD = "a" * 40


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


_STUB_SPEC = "docs/specs/00086-verifiable-dataset-provenance-design.md"
# What a stub declares unless its case overrides a keyword: a ruled subject, so a register run reaches the append.
_STUB_DECLARED = {
    "spec": _STUB_SPEC,
    "metric_keys": frozenset({"sharpe"}),
    "verdict": lambda metrics: "adopt",
    "no_verdict": "the stub's stop",
}


def _stub_subject(monkeypatch, name: str = "stub", *, metrics: dict | None = None, **declared) -> list:
    """A subject returning fixed metrics over whatever the reader hands it, declaring only BTC so
    `required_relpaths` demands just the one file `_stub_dataset` writes; the list it returns gains each build's dataset."""
    calls = []

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        calls.append(dataset)
        reader.read_series(dataset, "BTC/EUR/1440.parquet", window=window)
        return {"sharpe": 1.0} if metrics is None else metrics

    subject = subjects.Subject(name, (1440,), ("BTC",), build, **(_STUB_DECLARED | declared))
    monkeypatch.setitem(subjects.SUBJECTS, name, subject)
    return calls


def _stub_eval(name: str = "stub") -> list[str]:
    return ["research", "eval", "--subject", name, "--dataset", "ohlc-test"]


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


@pytest.fixture(autouse=True)
def _clean_tree(monkeypatch):
    """The register path reads the code root's HEAD and status: no verdict here may depend on the checkout it runs in."""
    monkeypatch.setattr(research_command, "_tree_state", lambda root: (_CLEAN_HEAD, ""))


def _register_args(registry: Path, *, n_trials: int, family: str = "STUB") -> list[str]:
    return [
        "--register",
        "--registry",
        str(registry),
        "--iteration",
        "iter-001",
        "--family",
        family,
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


def test_register_appends_one_schema_5_record_whose_hash_derives_from_the_observed_block(tmp_path, monkeypatch):
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
    assert record["schema_version"] == 5
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
        + ["--iteration", "iter-001", "--family", "STUB", "--n-trials", "1"],
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
    for flag in ("--iteration", "--family", "--n-trials"):
        assert flag in result.output
    assert "--spec-hash" not in result.output and "--verdict" not in result.output
    assert not registry.exists()


# The autouse `_clean_tree` stubs the module's name; the cases over real repositories call the function itself.
_unstubbed_tree_state = research_command._tree_state
# Passed on every commit: CI's runner has no git identity.
_GIT_IDENTITY = ("-c", "user.name=zcrypto-test", "-c", "user.email=zcrypto-test@example.invalid", "-c", "commit.gpgsign=false")


def _git_repo(root: Path, *paths: str) -> str:
    """A new repository at `root` whose one commit holds each path, written with its own name as its text, or one file
    when none is given; its HEAD."""
    root.mkdir(parents=True, exist_ok=True)
    tracked = paths or ("tracked.txt",)

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout

    git("init", "-q")
    for path in tracked:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(f"{path}\n")
    git("add", "--", *tracked)
    git(*_GIT_IDENTITY, "commit", "-q", "-m", "fixture")
    return git("rev-parse", "HEAD").strip()


def test_the_tree_state_is_the_code_roots_whatever_the_cwd(tmp_path, monkeypatch):
    first = _git_repo(tmp_path / "first", "first.txt")
    second = _git_repo(tmp_path / "second", "second.txt")
    assert first != second
    monkeypatch.chdir(tmp_path / "second")

    assert _unstubbed_tree_state(tmp_path / "first") == (first, "")


@pytest.mark.parametrize("show", [None, "no"], ids=["default", "show-untracked-files-no"])
def test_the_tree_state_lists_an_untracked_file_whatever_the_repository_config_says(tmp_path, show):
    root = tmp_path / "repo"
    _git_repo(root)
    (root / "scratch").mkdir()
    (root / "scratch" / "new-design.md").write_text("draft\n")
    if show is not None:
        subprocess.run(["git", "-C", str(root), "config", "status.showUntrackedFiles", show], check=True)

    assert _unstubbed_tree_state(root)[1] == "?? scratch/new-design.md\n"


def test_a_tree_whose_index_cannot_be_read_is_refused_never_read_clean(tmp_path, capsys):
    root = tmp_path / "repo"
    _git_repo(root)
    with open(root / ".git" / "index", "r+b") as index:
        index.truncate(20)

    with pytest.raises(typer.Exit) as refused:
        _unstubbed_tree_state(root)

    assert refused.value.exit_code == 1
    assert "git status failed" in capsys.readouterr().err


def test_a_directory_that_is_no_repository_is_refused(tmp_path, capsys):
    (tmp_path / "plain").mkdir()

    with pytest.raises(typer.Exit) as refused:
        _unstubbed_tree_state(tmp_path / "plain")

    assert refused.value.exit_code == 1
    assert "is not a git checkout" in capsys.readouterr().err


def test_a_register_run_from_an_unclean_tree_is_refused_before_the_fit_listing_the_paths(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    dirt = " M cli/research/subjects.py\n?? docs/specs/00999-scratch-design.md\n"
    monkeypatch.setattr(research_command, "_tree_state", lambda root: (_CLEAN_HEAD, dirt))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "cli/research/subjects.py" in result.output and "docs/specs/00999-scratch-design.md" in result.output
    assert calls == []
    assert not registry.exists()


@pytest.mark.parametrize(
    "after",
    [pytest.param(("b" * 40, ""), id="head-moved"), pytest.param((_CLEAN_HEAD, "?? scratch.py\n"), id="tree-dirtied")],
)
def test_a_tree_that_changes_during_the_fit_is_refused_and_nothing_recorded(tmp_path, monkeypatch, after):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    states = iter([(_CLEAN_HEAD, ""), after])
    monkeypatch.setattr(research_command, "_tree_state", lambda root: next(states))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "changed during the fit" in result.output
    assert calls == ["ohlc-test"]
    assert not registry.exists()


def test_register_refuses_an_evaluate_only_subject_before_the_fit(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "declares no verdict rule" in result.output
    assert calls == []
    assert not registry.exists()


@pytest.mark.parametrize("typed", [[], ["--verdict", "park"]], ids=["untyped", "typed-as-the-rule-gives"])
def test_register_records_the_verdict_the_subjects_rule_gives(tmp_path, monkeypatch, typed):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: "park")

    result = runner.invoke(app, [*_stub_eval(), *typed, *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    assert json.loads(registry.read_text())["verdict"] == "park"


def test_a_typed_verdict_the_rule_does_not_give_is_refused(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: "park")

    result = runner.invoke(app, [*_stub_eval(), "--verdict", "adopt", *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--verdict adopt" in result.output and "park" in result.output
    assert not registry.exists()


def test_a_rule_that_stops_is_refused_naming_the_subjects_stop(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None, no_verdict="the stub's own stop")

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "no verdict: the stub's own stop" in result.output
    assert not registry.exists()


_STUB_SPEC_SHA256 = hashlib.sha256((_REPO / _STUB_SPEC).read_bytes()).hexdigest()


@pytest.mark.parametrize("typed", [[], ["--spec-hash", _STUB_SPEC_SHA256]], ids=["untyped", "typed-as-computed"])
def test_register_records_the_sha256_of_the_subjects_spec_and_its_declared_seeds(tmp_path, monkeypatch, typed):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, seeds=(11, 5))

    result = runner.invoke(app, [*_stub_eval(), *typed, *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    record = json.loads(registry.read_text())
    assert record["spec_hash"] == _STUB_SPEC_SHA256
    assert record["seeds"] == [11, 5]


def test_a_typed_spec_hash_other_than_the_specs_is_refused_before_the_fit(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)

    result = runner.invoke(app, [*_stub_eval(), "--spec-hash", "0" * 64, *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert _STUB_SPEC in result.output
    assert calls == []
    assert not registry.exists()


def test_seed_is_no_option(tmp_path, monkeypatch):
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    calls = _stub_subject(monkeypatch)

    result = runner.invoke(app, [*_stub_eval(), "--seed", "1"])

    assert result.exit_code == 2
    assert "--seed" in result.output
    assert calls == []


@pytest.mark.parametrize(
    ("returned", "declared"),
    [
        pytest.param({"sharpe": 1.0, "sortino": 2.0}, {"sharpe"}, id="one-key-more"),
        pytest.param({"sharpe": 1.0}, {"sharpe", "sortino"}, id="one-key-fewer"),
    ],
)
def test_register_refuses_a_build_whose_keys_are_not_the_declared_ones(tmp_path, monkeypatch, returned, declared):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, metrics=returned, metric_keys=frozenset(declared))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "sortino" in result.output
    assert calls == ["ohlc-test"]
    assert not registry.exists()


def _committed_copy(tmp_path: Path) -> Path:
    """The committed registry copied, so a new trial's id lies above every legacy id a case names."""
    registry = tmp_path / "registry.jsonl"
    shutil.copyfile(_COMMITTED_REGISTRY, registry)
    return registry


def test_a_subject_with_an_incumbent_is_refused_without_a_comparator_trial(tmp_path, monkeypatch):
    registry = _committed_copy(tmp_path)
    before = registry.read_bytes()
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, incumbent="record44-crossfreq")

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "pass --comparator-trial" in result.output
    assert calls == []
    assert registry.read_bytes() == before


def test_a_subject_without_an_incumbent_is_refused_a_comparator_trial(tmp_path, monkeypatch):
    registry = _committed_copy(tmp_path)
    before = registry.read_bytes()
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)

    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "b2-funding-derisk", "--dataset", "ohlc-test", "--comparator-trial", "44"]
        + _register_args(registry, n_trials=1),
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "declares no incumbent" in result.output
    assert registry.read_bytes() == before


def test_a_legacy_record_the_incumbent_reproduces_is_recorded_as_the_comparator(tmp_path, monkeypatch):
    registry = _committed_copy(tmp_path)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, incumbent="record44-crossfreq")

    result = runner.invoke(app, [*_stub_eval(), "--comparator-trial", "44", *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    assert json.loads(registry.read_text().splitlines()[-1])["invocation"]["comparator_trial"] == 44


@pytest.mark.parametrize("n", [33, 45], ids=["another-subjects-legacy-record", "a-legacy-record-no-subject-reproduces"])
def test_a_legacy_record_the_incumbent_does_not_reproduce_is_refused_as_the_comparator(tmp_path, monkeypatch, n):
    registry = _committed_copy(tmp_path)
    before = registry.read_bytes()
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, incumbent="record44-crossfreq")

    result = runner.invoke(app, [*_stub_eval(), "--comparator-trial", str(n), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"--comparator-trial {n}" in result.output
    assert calls == []
    assert registry.read_bytes() == before


@pytest.mark.parametrize(
    ("incumbent", "recorded"),
    [pytest.param("stub", True, id="the-incumbents-trial"), pytest.param("record44-crossfreq", False, id="another-subjects-trial")],
)
def test_a_registered_trial_is_the_comparator_only_of_a_subject_naming_its_subject(tmp_path, monkeypatch, incumbent, recorded):
    registry = _committed_copy(tmp_path)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 0
    trial = json.loads(registry.read_text().splitlines()[-1])
    assert trial["schema_version"] == 5 and trial["invocation"]["subject"] == "stub"
    before = registry.read_text().splitlines()
    _stub_subject(monkeypatch, "follower", incumbent=incumbent)

    result = runner.invoke(
        app, [*_stub_eval("follower"), "--comparator-trial", str(trial["trial_id"]), *_register_args(registry, n_trials=2)]
    )

    after = registry.read_text().splitlines()
    if recorded:
        assert result.exit_code == 0, result.output
        assert after[: len(before)] == before and len(after) == len(before) + 1
        assert json.loads(after[-1])["invocation"]["comparator_trial"] == trial["trial_id"]
    else:
        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit)
        assert after == before


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
    """The JSON report the command prints after the human-readable lines, and before any refusal or stop."""
    return json.JSONDecoder().raw_decode(output, output.index("{"))[0]


# `record33-combined`'s committed headline keys, pinned here as literals: reading them back off the
# subject under test would assert nothing about which metrics the command actually reports.
_COMBINED_METRIC_KEYS = {"ann_sharpe_noc", "per_period_sharpe", "bench_ann_sharpe", "cap_breach_bars", "n_periods"}
# `record44-crossfreq`'s, for the same reason.
_CROSSFREQ_METRIC_KEYS = {
    "ann_sharpe_noc",
    "per_period_sharpe_4h",
    "ann_sharpe_ungoverned",
    "cap_breach_bars",
    "governor_engaged_bars",
    "n_periods",
}


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
    subject = subjects.Subject("rolling-stub", (1440,), assets, build, **_STUB_DECLARED)
    monkeypatch.setitem(subjects.SUBJECTS, "rolling-stub", subject)
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


def test_a_register_run_records_the_invocation_that_produced_it(tmp_path, monkeypatch):
    root = _rolling_set(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, root, registry)
    _rolling_subject(monkeypatch)
    window = ["2026-10-01 00:00:00+00:00", "2026-10-02 00:00:00+00:00"]

    result = runner.invoke(
        app, _rolling_eval("--as-of", "2026-10-03", "--accept-holes", "--window", *window, *_register_args(registry, n_trials=1))
    )

    assert result.exit_code == 0, result.output
    record = json.loads(registry.read_text())
    assert record["schema_version"] == 5
    assert record["invocation"] == {
        "subject": "rolling-stub",
        "dataset": "ohlc-rolling",
        "window": window,
        "as_of": "2026-10-03",
        "accept_holes": True,
        "comparator_trial": None,
        "commit": _CLEAN_HEAD,
    }


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


@pytest.mark.parametrize("name", sorted(subjects.SUBJECTS))
def test_every_subject_declares_a_tracked_spec_its_keys_seeds_rule_and_incumbent(name):
    subject = subjects.SUBJECTS[name]
    tracked = subprocess.run(
        ["git", "-C", str(_REPO), "ls-files", "--error-unmatch", "--", str(subject.spec)], capture_output=True, text=True
    )
    assert tracked.returncode == 0, f"{name} declares the spec {subject.spec!r}, which git does not track: {tracked.stderr}"
    assert subject.metric_keys
    assert (subject.verdict is None) == (subject.no_verdict is None)
    assert subject.incumbent is None or subject.incumbent in subjects.SUBJECTS
    assert type(subject.seeds) is tuple and all(type(seed) is int for seed in subject.seeds)


def test_each_subject_declares_the_metric_keys_its_build_returns():
    assert subjects.SUBJECTS["b2-funding-derisk"].metric_keys == _B2_METRIC_KEYS
    assert subjects.SUBJECTS["record33-combined"].metric_keys == _COMBINED_METRIC_KEYS
    assert subjects.SUBJECTS["record44-crossfreq"].metric_keys == _CROSSFREQ_METRIC_KEYS


# One engaged year of two, so a rule reading `all` where it reads `any` turns this adopt into a stop.
_B2_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2021": 4, "2022": 0},
    "passes": 1,
    "head_to_head_mean_outperf_2021": 0.001,
    "head_to_head_spa_p_2021": 0.01,
    "max_drawdown_reduction_pct": 5.0,
}
_B2_NEVER_ENGAGED = {"engaged_per_year": {"2021": 0, "2022": 0}}


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_NEVER_ENGAGED, None, id="the-overlay-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
        pytest.param({"passes": 0}, "reject", id="arm-b-fails-its-bar"),
        pytest.param(
            {"head_to_head_mean_outperf_2021": 0.001, "head_to_head_spa_p_2021": 0.01, "max_drawdown_reduction_pct": 5.0},
            "adopt",
            id="outperforms-significantly-and-cuts-drawdown",
        ),
        pytest.param({"head_to_head_spa_p_2021": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_mean_outperf_2021": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="reduction-at-exactly-1e-6"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6, "head_to_head_spa_p_2021": 0.2}, "park", id="reduction-past-1e-6-p-0.2"),
        pytest.param({"head_to_head_mean_outperf_2021": -0.001}, "reject", id="mean-negative"),
    ],
)
def test_the_b2_rule_maps_its_metrics_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b2_verdict({**_B2_ADOPTING, **change}) == verdict


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


def _kill_bar_sentinels(cell, *, inverted: bool, arm_a_passes) -> dict:
    """Per-call sentinels for the eight keys the subject reads, so a float or a flag read off the wrong cell or key, a flag
    read off another flag, or `passes` read off a flag or another cell fails the metrics' comparison: the flags are ints
    other than 0 and 1, which the subject's `int()` and the registry's leaf check carry through."""
    i = (*_B2_GRID, "A").index(cell)
    if cell == "A":
        floats = {"dsr": 0.91, "spa_p_value": 0.81, "spa_p_value_full": 0.71}
    else:
        floats = {"dsr": 0.11 + i / 100, "spa_p_value": 0.21 + i / 100, "spa_p_value_full": 0.31 + i / 100}
    # B's `passes` is true at the headline alone, or false there alone, so an `all` or an `any` over the grid moves it;
    # arm A's is false in the first two parametrisations, told from B's headline by the first and from B's other cells by
    # the second, so the rule stops on both; in the third it is the int 7, which no B cell carries.
    passes = arm_a_passes if cell == "A" else (cell == (30, 42)) != inverted
    return floats | {"passes": passes} | {flag: 10 * (i + 1) + j for j, flag in enumerate(_B2_FLAGS)}


@pytest.mark.parametrize(
    ("inverted", "arm_a_passes"),
    [
        pytest.param(False, False, id="passes-at-the-headline"),
        pytest.param(True, False, id="passes-off-the-headline"),
        pytest.param(True, 7, id="arm-a-passes"),
    ],
)
def test_the_b2_subject_registers_each_metric_from_its_own_call(tmp_path, monkeypatch, inverted, arm_a_passes):
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
        return (
            result | _kill_bar_sentinels(cell, inverted=inverted, arm_a_passes=arm_a_passes) if cell in ("A", *_B2_GRID) else result
        )

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
    if arm_a_passes:
        assert result.exit_code == 0, result.output
        reported = json.loads(registry.read_text())
        assert reported["verdict"] == "reject"
        assert reported["seeds"] == [42, 7, 1234]
        assert reported["metrics"]["arm_a_passes"] == 7
    else:
        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit)
        assert f"no verdict: {subjects.SUBJECTS['b2-funding-derisk'].no_verdict}" in result.output
        assert not registry.exists()
        reported = _block_and_metrics(result.output)

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
    assert set(reported["metrics"]) == _B2_METRIC_KEYS
    assert reported["metrics"] == expected
    assert set(reported["datasets"]["derivatives-funding"]["files"]) == {f"{PERP_SYMBOLS[a]}/funding.parquet" for a in _B2_ASSETS}
    ohlc = reported["datasets"]["ohlc-test"]
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
    ("spoil", "cause"),
    [
        pytest.param(lambda path: path.write_bytes(b"not a parquet file"), "File out of specification", id="not-parquet"),
        pytest.param(lambda path: pl.read_parquet(path).drop("close").write_parquet(path), "no close column", id="no-close-column"),
    ],
)
def test_a_price_file_the_union_cannot_read_is_refused_naming_it(tmp_path, monkeypatch, spoil, cause):
    root = _b2_dataset(tmp_path)
    spoil(root / "ohlc-test" / "ETH/EUR/240.parquet")
    _anchor(monkeypatch, root)

    result = runner.invoke(app, _b2_eval(_B2_START, _B2_WINDOW_BARS))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert "ohlc-test/ETH/EUR/240.parquet" in result.output
    assert cause in result.output


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


def _one_bar_in_the_window(path: Path) -> None:
    frame = pl.read_parquet(path)
    frame.filter(pl.col("ts") >= frame["ts"][_B2_WINDOW_BARS - 1]).write_parquet(path)


@pytest.mark.parametrize(
    "spoil",
    [
        pytest.param(_one_bar_in_the_window, id="one-bar-in-the-window"),
        pytest.param(
            lambda path: (
                (frame := pl.read_parquet(path)).with_columns(close=pl.lit(None, dtype=frame.schema["close"])).write_parquet(path)
            ),
            id="no-close-at-all",
        ),
    ],
)
def test_the_b2_subject_refuses_an_asset_too_thin_in_the_window_naming_the_window(tmp_path, monkeypatch, spoil):
    root = _b2_dataset(tmp_path)
    spoil(root / "ohlc-test" / "ETH/EUR/240.parquet")
    _anchor(monkeypatch, root)
    args = _b2_eval(_B2_START, _B2_WINDOW_BARS)

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"b2-funding-derisk over the window {args[-2]} .. {args[-1]}: prices must be a list of >= 2 values" in result.output


def test_the_b2_inputs_scale_each_spiking_asset_from_the_first_close_at_or_after_its_first_spike(tmp_path):
    ts = [_B2_START + timedelta(hours=4 * k) for k in range(_B2_WINDOW_BARS)]
    inputs = subjects._b2_inputs(ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", (str(ts[0]), str(ts[-1])), None, False)

    first = {a: next((k for k, s in enumerate(inputs.scales[a]) if s != 1.0), None) for a in _B2_ASSETS}

    # Asset i's first spike prints at bar 822 + 2i's open, which closes return index 821 + 2i.
    spikes = _B2_FALLS[1][0] - 1
    assert first == {a: None if a == _B2_NEVER_SPIKES else spikes + 2 * i for i, a in enumerate(_B2_ASSETS)}


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


def _declared_series(tmp_path: Path, subject: subjects.Subject) -> tuple[Path, datetime]:
    root = tmp_path / "data"
    for i, asset in enumerate(subject.assets):
        for interval in subject.intervals:
            relpath = f"{asset}/EUR/{interval}.parquet"
            _write_series(root, "ohlc-test", relpath, 600 * 1440 // interval, phase=i * 0.7, step=60 * interval)
    return root, datetime.fromtimestamp(_EPOCH_2020, UTC)


# A subject whose build reads a dataset it does not declare brings its own fixture here; any other is fed its declared series.
_CONTRACT_DATASETS = {"b2-funding-derisk": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START)}


def _a_close_zeroed(path: Path) -> None:
    frame = pl.read_parquet(path)
    closes = frame["close"].to_list()
    closes[len(closes) // 2] = 0.0
    frame.with_columns(close=pl.Series(closes, dtype=frame.schema["close"])).write_parquet(path)


def _no_close(path: Path) -> None:
    frame = pl.read_parquet(path)
    frame.with_columns(close=pl.lit(None, dtype=frame.schema["close"])).write_parquet(path)


def _first_bar_dropped(path: Path) -> None:
    pl.read_parquet(path).slice(1).write_parquet(path)


# Each spoils the named asset's file at one declared interval per row, so a guard holding one grid and not another fails.
_CONTRACT_SPOILS = {
    "a-zero-close": ("ETH", _a_close_zeroed),
    "an-asset-never-closes": ("ETH", _no_close),
    "btc-absent-at-the-first-stamp": ("BTC", _first_bar_dropped),
}
_CONTRACT_WINDOWS = ("1-bar-window", "2-bar-window", "5-bar-window")


def _contract_rows() -> list:
    rows = []
    for name in sorted(subjects.SUBJECTS):
        rows += [pytest.param(name, case, None, id=f"{name}-{case}") for case in ("evaluates", *_CONTRACT_WINDOWS)]
        rows += [
            pytest.param(name, case, interval, id=f"{name}-{case}-on-{interval}")
            for interval in subjects.SUBJECTS[name].intervals
            for case in _CONTRACT_SPOILS
        ]
    return rows


@pytest.mark.parametrize(("name", "case", "interval"), _contract_rows())
def test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit(
    tmp_path, monkeypatch, name, case, interval
):
    subject = subjects.SUBJECTS[name]
    root, start = _CONTRACT_DATASETS.get(name, _declared_series)(tmp_path, subject)
    _anchor(monkeypatch, root)
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-test"]
    spoilt = None
    if case in _CONTRACT_WINDOWS:
        end = start + timedelta(minutes=max(subject.intervals) * (int(case.split("-")[0]) - 1))
        args += ["--window", str(start), str(end)]
    elif case in _CONTRACT_SPOILS:
        asset, spoil = _CONTRACT_SPOILS[case]
        spoilt = f"ohlc-test/{asset}/EUR/{interval}.parquet"
        spoil(root / spoilt)

    result = runner.invoke(app, args)

    assert result.exception is None or isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    if case == "evaluates":
        assert result.exit_code == 0, result.output
        assert _block_and_metrics(result.output)["metrics"]
    elif case in _CONTRACT_WINDOWS:
        assert result.exit_code == 1
        assert f"{name} over the window {args[-2]} .. {args[-1]}" in result.output
    elif case == "a-zero-close":
        assert result.exit_code == 1
        assert f"{name} over the full history" in result.output
    elif result.exit_code == 1:
        # A subject may evaluate an asset that never closes or a late first BTC bar; one that refuses names where.
        assert f"{name} over the full history" in result.output or spoilt in result.output


def _record44_frozen(tmp_path: Path, asset: str, spoil) -> tuple[Path, list[str]]:
    root, _ = _declared_series(tmp_path, subjects.SUBJECTS["record44-crossfreq"])
    spoil(root / "ohlc-test" / f"{asset}/EUR/1440.parquet")
    return root, ["--dataset", "ohlc-test"]


_ROLLING_FIRST_DAY = ["--window", "2026-10-01 00:00:00+00:00", "2026-10-03 20:00:00+00:00"]


@pytest.mark.parametrize(
    ("dataset", "message"),
    [
        pytest.param(
            lambda tmp_path: _record44_frozen(tmp_path, "ETH", _no_close),
            "ohlc-test/ETH/EUR/1440.parquet: no close in the window read",
            id="frozen-eth-never-closes",
        ),
        pytest.param(
            lambda tmp_path: _record44_frozen(tmp_path, "BTC", _first_bar_dropped),
            "ohlc-test/BTC/EUR/1440.parquet: no close at 2020-01-01 00:00:00+00:00, the first daily stamp of the window read",
            id="frozen-btc-absent-at-the-first-daily-stamp",
        ),
        pytest.param(
            lambda tmp_path: (
                _rolling_set(tmp_path, bar=lambda pair, day: {"close": None} if pair == "ETH/EUR" else {}),
                ["--dataset", "ohlc-rolling", "--as-of", "2026-10-03"],
            ),
            "ohlc-rolling ETH/EUR at 1440 minutes as of 2026-10-03: no close in the window read",
            id="rolling-eth-never-closes",
        ),
        pytest.param(
            lambda tmp_path: (
                _rolling_set(tmp_path, holes={date(2026, 10, 1): {"BTC/EUR"}}),
                ["--dataset", "ohlc-rolling", "--as-of", "2026-10-03", "--accept-holes", *_ROLLING_FIRST_DAY],
            ),
            "ohlc-rolling BTC/EUR at 1440 minutes as of 2026-10-03: no close at 2026-10-01 00:00:00+00:00, the first daily "
            "stamp of the window read",
            id="rolling-btc-absent-at-the-first-daily-stamp",
        ),
    ],
)
def test_record44_refuses_a_grid_it_cannot_feed_naming_the_file_or_the_rolling_pair_and_grid(
    tmp_path, monkeypatch, dataset, message
):
    root, args = dataset(tmp_path)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "record44-crossfreq", *args])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert message in result.output


# Listed here, never read off `subjects.EVALUATION_ERRORS`: a class dropped from the tuple must fail a row, not lose it.
_COMPUTE_ERRORS = (AlphaError, BacktestError, BenchmarkError, FeatureError, PortfolioError, RiskError, ValidationError)


def _raising_subject(monkeypatch, error: type[Exception]) -> str:
    def build(reader, dataset, window, as_of=None, accept_holes=False):
        raise error("the stub's cause")

    monkeypatch.setitem(subjects.SUBJECTS, "raising-stub", subjects.Subject("raising-stub", (1440,), ("BTC",), build))
    return f"tests/test_research_command.py:{build.__code__.co_firstlineno + 1}"


@pytest.mark.parametrize("error", _COMPUTE_ERRORS, ids=lambda error: error.__name__)
def test_a_compute_package_error_ends_in_an_exit_naming_subject_window_dataset_class_and_raise_site(tmp_path, monkeypatch, error):
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    site = _raising_subject(monkeypatch, error)
    start, end = "2020-01-02 00:00:00+00:00", "2020-01-05 00:00:00+00:00"

    result = runner.invoke(app, ["research", "eval", "--subject", "raising-stub", "--dataset", "ohlc-test", "--window", start, end])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    cause = f"the stub's cause ({error.__name__} raised at {site})"
    assert f"raising-stub over the window {start} .. {end} of ohlc-test: {cause}" in result.output


@pytest.mark.parametrize(
    ("dataset", "flags", "where"),
    [
        pytest.param("ohlc-test", [], "the full history of ohlc-test", id="frozen-full-history"),
        pytest.param("ohlc-rolling", ["--as-of", "2026-10-02"], "the full history of ohlc-rolling as of 2026-10-02", id="as-of"),
    ],
)
def test_a_compute_package_error_names_the_full_history_and_the_as_of_day(tmp_path, monkeypatch, dataset, flags, where):
    _rolling_set(tmp_path)
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    site = _raising_subject(monkeypatch, ValidationError)

    result = runner.invoke(app, ["research", "eval", "--subject", "raising-stub", "--dataset", dataset, *flags])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"raising-stub over {where}: the stub's cause (ValidationError raised at {site})" in result.output


def test_a_plain_python_exception_in_a_build_escapes_as_itself(tmp_path, monkeypatch):
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _raising_subject(monkeypatch, ValueError)

    result = runner.invoke(app, ["research", "eval", "--subject", "raising-stub", "--dataset", "ohlc-test"])

    assert type(result.exception) is ValueError, "a plain Python exception is a fault in the code, never a refusal"
    assert str(result.exception) == "the stub's cause"
