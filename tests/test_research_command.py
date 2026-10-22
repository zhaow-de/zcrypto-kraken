"""`zcrypto research eval` — the committed door to the registry (spec 00086) and to the readings ledger (spec 00129)."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import operator
import os
import re
import shutil
import statistics
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
import typer
from typer.testing import CliRunner

from cli.__main__ import app
from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.alpha.a2 import _asset_directions_a2
from cli.alpha.b1 import book_turnover
from cli.alpha.b1_exit import (
    a2_slot_positions,
    asset_directions_hourly_exit,
    exit_events_per_year,
    hourly_closes_differ_per_year,
    interior_closes_by_asset,
    intra_turnover,
    net_of_cost_hourly,
    price_paths,
)
from cli.alpha.b1_rv import (
    a2_positions_with_weights,
    hourly_rv_inverse_vol_weights,
    per_year_mean_weights,
    weight_total_variation,
    weights_differ_count,
)
from cli.alpha.b1_volume import (
    a2_positions_on_directions,
    asset_directions_confirmed,
    confirmations_by_asset,
    directions_differ_per_year,
    entry_events_per_year,
)
from cli.alpha.b2 import (
    B2Config,
    daily_zscore_grid_feature,
    derisk_scales,
    funding_grid_feature,
    liquidation_hourly_totals,
    net_of_cost,
    oi_zscore_grid_feature,
    per_year_engaged_counts,
    per_year_max_drawdown,
    per_year_positions_differ,
    per_year_turnover,
    ratio_max_signal,
    ratio_zscore_grid_features,
    reentry_counts_per_year,
    reentry_positions,
    scale_positions,
)
from cli.alpha.errors import AlphaError
from cli.backtest.errors import BacktestError
from cli.benchmark.errors import BenchmarkError
from cli.data import sync
from cli.derivatives.funding import PERP_SYMBOLS
from cli.features.derivatives import coverage_by_year, funding_zscore
from cli.features.errors import FeatureError
from cli.ohlc.dataset import to_frame, write_parquet
from cli.portfolio.builder import CombinedSystemConfig, build_combined_system
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, _ffill_btc
from cli.portfolio.errors import PortfolioError
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost, calendar_year_slices
from cli.registry import TrialRegistry, attempts, budget
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.risk.errors import RiskError
from cli.validation import ValidationError, max_drawdown, sharpe
from cli.validation.dsr import expected_max_sharpe
from tests.rolling_fixtures import HOLE, write_chain
from tests.test_trial_attempts import _reaped_pid
from tests.test_trial_registry_provenance import LEDGER, REGISTRY, _trials, live_entries

runner = CliRunner()

_DAY = 86400
_EPOCH_2020 = 1577836800  # 2020-01-01T00:00:00Z
_REPO = Path(__file__).resolve().parents[1]
_COMMITTED_REGISTRY = _REPO / "docs" / "reference" / "trial-registry.jsonl"
_CLEAN_HEAD = "a" * 40
# Read at import: the autouse fixtures below move both before every test.
_DEFAULT_REGISTRY, _DEFAULT_LEDGER = research_command._REGISTRY, research_command._LEDGER


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
    "family": "STUB",
    "n_trials": 1,
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
def _ledger_default_off_the_committed_file(tmp_path, monkeypatch):
    """`ReadingLedger(ledger or _LEDGER).append` writes wherever `_LEDGER` points, so no test in this module may start or
    end with it on the committed readings ledger."""
    monkeypatch.setattr("cli.research.command._LEDGER", tmp_path / "unanchored-ledger.jsonl")
    yield
    assert research_command._LEDGER != LEDGER, "this test left cli.research.command._LEDGER on the committed readings ledger"


@pytest.fixture(autouse=True)
def _clean_tree(monkeypatch):
    """The register path reads the code root's HEAD and status: no verdict here may depend on the checkout it runs in."""
    monkeypatch.setattr(research_command, "_tree_state", lambda root: (_CLEAN_HEAD, ""))


@pytest.fixture(autouse=True)
def _attempts_log(tmp_path, monkeypatch, _attempts_log_in_tmp_path) -> Path:
    path = attempts.log_path(_REPO)
    path.parent.mkdir(parents=True)
    log_id = attempts.init_log(path, host="zcrypto-test")
    (tmp_path / "trial-attempt-logs.txt").write_text(f"{log_id} zcrypto-test\n")
    monkeypatch.setattr(attempts, "landed", lambda code_root, registry, ledger: attempts.files_landed(registry, ledger))
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", None)
    return path


# The real functions, kept before a fixture can replace them.
_unstubbed_landed, _unstubbed_log_path, _unstubbed_allowed = attempts.landed, attempts.log_path, attempts.allowed_log_ids


def _register_args(registry: Path, *, n_trials: int, family: str = "STUB", ledger: Path | None = None) -> list[str]:
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
        *([] if ledger is None else ["--ledger", str(ledger)]),
    ]


def _as_trial(name: str, tmp_path: Path) -> list[str]:
    known = subjects.SUBJECTS[name]
    if known.verdict is None:
        return []
    return [
        "--register",
        "--registry",
        str(tmp_path / "registry.jsonl"),
        "--ledger",
        str(tmp_path / "ledger.jsonl"),
        "--iteration",
        "iter-001",
        "--family",
        known.family,
        "--n-trials",
        str(known.n_trials),
    ]


def _reading_args(ledger: Path) -> list[str]:
    return ["--reading", "--ledger", str(ledger), "--iteration", "iter-001"]


def _kept(ledger: Path) -> list[dict]:
    return [json.loads(line) for line in ledger.read_text().splitlines()]


def _log_lines(path: Path) -> list[dict]:
    return list(attempts.AttemptLog(path).lines)


def test_eval_reports_the_block_and_writes_no_record_without_register(tmp_path, monkeypatch):
    root = _stub_dataset(tmp_path)
    registry = tmp_path / "registry.jsonl"
    _stub_subject(monkeypatch, verdict=None, no_verdict=None)
    _anchor(monkeypatch, root, registry)

    result = runner.invoke(app, ["research", "eval", "--subject", "stub", "--dataset", "ohlc-test"])

    assert result.exit_code == 0, result.output
    assert '"rows": 10' in result.output
    assert "inert (0 vouched hashes)" in result.output
    assert not registry.exists(), "a read-only eval must not touch the registry"


def test_register_appends_one_schema_6_record_whose_hash_derives_from_the_observed_block(tmp_path, monkeypatch):
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
    assert record["schema_version"] == 6
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


def test_the_commands_default_ledger_is_the_one_every_check_reads():
    assert _DEFAULT_LEDGER == LEDGER


def test_the_commands_default_registry_is_the_one_every_check_reads():
    assert _DEFAULT_REGISTRY == REGISTRY


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
    assert "stub declares n_trials 1, and family STUB needs at least 2: 1 records, this run" in repeat.output
    assert "stub's n_trials is frozen by its trial 1: declare a new subject (a new name) for the further trial" in repeat.output
    assert len(registry.read_text().splitlines()) == 1

    _stub_subject(monkeypatch, "stub-2", n_trials=2)
    second = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=2)])
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


def test_a_verdict_outside_adopt_reject_and_park_is_refused_before_the_fit(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)

    result = runner.invoke(app, [*_stub_eval(), "--verdict", "adpot", *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--verdict adpot" in result.output
    assert calls == []
    assert not registry.exists()


def test_a_rule_that_stops_keeps_the_run_as_a_reading_and_spends_no_trial(tmp_path, monkeypatch):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None, no_verdict="the stub's own stop")

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, ledger=ledger)])

    assert result.exit_code == 0, result.output
    assert "no verdict — the stub's own stop: recorded reading 1; no trial spent" in result.output
    (reading,) = _kept(ledger)
    assert (reading["reading_id"], reading["outcome"], reading["metrics"]) == (1, "the stub's own stop", {"sharpe": 1.0})
    assert not registry.exists()


def test_a_typed_verdict_on_a_run_the_rule_stops_on_is_refused_and_nothing_kept(tmp_path, monkeypatch):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None, no_verdict="the stub's own stop")

    result = runner.invoke(app, [*_stub_eval(), "--verdict", "reject", *_register_args(registry, n_trials=1, ledger=ledger)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--verdict reject" in result.output and "no verdict" in result.output
    assert not ledger.exists()
    assert not registry.exists()


def test_a_clean_run_is_admitted_and_logged_begin_and_end(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(Path("registry.jsonl"), n_trials=1)])

    assert result.exit_code == 0, result.output
    record = json.loads(registry.read_text())
    log = attempts.AttemptLog(_attempts_log)
    begin, end = log.lines[1:]
    assert record["schema_version"] == 6
    assert record["attempt"] == {"log": log.log_id, "id": 1, "begin": begin["line_hash"], "absorbs": [], "counted": []}
    assert (begin["kind"], begin["attempt"], end["kind"], end["attempt"]) == ("begin", 1, "end", 1)
    assert begin["registry"] == str(registry.resolve())
    assert (begin["invocation"], begin["spec_hash"], begin["family"]) == (record["invocation"], record["spec_hash"], "STUB")
    assert (end["verdict"], end["stop"], end["failed"]) == ("adopt", None, None)
    assert end["metrics_hash"] == compute_hash(record["metrics"])


def _raising_stub(monkeypatch, returned: dict | None = None, raised: type[Exception] = subjects.SubjectError) -> None:
    def build(reader, dataset, window, as_of=None, accept_holes=False):
        reader.read_series(dataset, "BTC/EUR/1440.parquet", window=window)
        if returned is None:
            raise raised("the stub's window is too short")
        return returned

    monkeypatch.setitem(subjects.SUBJECTS, "stub", subjects.Subject("stub", (1440,), ("BTC",), build, **_STUB_DECLARED))


@pytest.mark.parametrize(
    ("returned", "raised", "failed"),
    [
        pytest.param(None, subjects.SubjectError, "SubjectError: the stub's window is too short", id="the-build-raises"),
        pytest.param(None, ValidationError, "ValidationError: the stub's window is too short", id="a-compute-error"),
        pytest.param(
            {"sharpe": 1.0, "extra": 2.0},
            subjects.SubjectError,
            "SubjectError: stub's build returned keys other than the ones it declares",
            id="the-keys-differ",
        ),
        pytest.param(
            {"sharpe": None},
            subjects.SubjectError,
            "RegistryError: metrics.sharpe: unsupported metric leaf type NoneType",
            id="a-leaf-the-registry-refuses",
        ),
    ],
)
def test_a_failed_build_ends_its_attempt_with_its_class_and_message(tmp_path, monkeypatch, _attempts_log, returned, raised, failed):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _raising_stub(monkeypatch, returned, raised)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and not registry.exists() and '"metrics"' not in result.output, result.output
    end = _log_lines(_attempts_log)[-1]
    assert end["kind"] == "end" and end["failed"].startswith(failed)
    assert (end["verdict"], end["stop"], end["metrics"], end["metrics_hash"]) == (None, None, None, None)


def test_a_stop_ends_its_attempt_with_the_stop_and_its_reading_carries_it(tmp_path, monkeypatch, _attempts_log):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, ledger=ledger)])

    assert result.exit_code == 0, result.output
    log = attempts.AttemptLog(_attempts_log)
    (reading,) = _kept(ledger)
    assert (reading["schema_version"], reading["attempt"]) == (
        2,
        {"log": log.log_id, "id": 1, "begin": log.lines[1]["line_hash"], "absorbs": []},
    )
    assert (log.lines[-1]["stop"], log.lines[-1]["verdict"]) == ("the stub's stop", None)


def test_a_ruleless_reading_writes_no_line_and_carries_no_attempt(tmp_path, monkeypatch, _attempts_log):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 0, result.output
    assert _kept(ledger)[0]["attempt"] is None and len(_log_lines(_attempts_log)) == 1


def test_a_begin_the_log_refuses_ends_the_run_before_the_build(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)

    def refuse(self, admit, **fields):
        raise OSError("No space left on device")

    monkeypatch.setattr(attempts.AttemptLog, "begin", refuse)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and "refused the run's first line: No space left on device; nothing ran" in result.output
    assert calls == [] and not registry.exists()


def test_an_end_the_log_refuses_withholds_the_numbers(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, metrics={"sharpe": 1.2345})

    def refuse(self, attempt, **outcome):
        raise OSError("No space left on device")

    monkeypatch.setattr(attempts.AttemptLog, "end", refuse)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert (
        "refused the run's last line: No space left on device; the numbers are withheld and the attempt stays open: run again "
        "with the same arguments, which absorbs it"
    ) in result.output
    assert "1.2345" not in result.output and not registry.exists()


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
    # Rendered in colour, as on CI, Typer styles each hyphen of an option apart.
    assert "--seed" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)
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
    """The committed registry: the legacy ids the cases name are records there with no invocation."""
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


def test_a_run_refused_for_an_unclean_tree_leaves_a_torn_registry_tail_unhealed(tmp_path, monkeypatch):
    registry = _committed_copy(tmp_path)
    with open(registry, "ab") as torn:
        torn.write(b'{"trial_id": 48, "fami')
    before = registry.read_bytes()
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, incumbent="record44-crossfreq")
    monkeypatch.setattr(research_command, "_tree_state", lambda root: (_CLEAN_HEAD, "?? scratch.py\n"))

    result = runner.invoke(app, [*_stub_eval(), "--comparator-trial", "44", *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "scratch.py" in result.output
    assert registry.read_bytes() == before
    assert calls == []


def test_a_legacy_record_the_incumbent_reproduces_is_recorded_as_the_comparator(tmp_path, monkeypatch):
    registry = _committed_copy(tmp_path)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, incumbent="record44-crossfreq")

    result = runner.invoke(app, [*_stub_eval(), "--comparator-trial", "44", *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    assert json.loads(registry.read_text().splitlines()[-1])["invocation"]["comparator_trial"] == 44


@pytest.mark.parametrize("n", [33, 43], ids=["another-subjects-legacy-record", "a-legacy-record-no-subject-reproduces"])
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
    assert trial["schema_version"] == 6 and trial["invocation"]["subject"] == "stub"
    before = registry.read_text().splitlines()
    _stub_subject(monkeypatch, "follower", incumbent=incumbent, n_trials=2)

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


def test_a_reading_of_a_ruleless_subject_is_kept_in_the_ledger_with_no_outcome(tmp_path, monkeypatch):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 0, result.output
    assert "recorded reading 1" in result.output
    (reading,) = _kept(ledger)
    assert (reading["reading_id"], reading["iteration"], reading["outcome"]) == (1, "iter-001", None)
    assert reading["metrics"] == {"sharpe": 1.0}
    assert not registry.exists()


def test_a_reading_records_the_sha256_of_the_subjects_spec_and_the_invocation_that_produced_it(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 0, result.output
    (reading,) = _kept(ledger)
    assert reading["spec_hash"] == _STUB_SPEC_SHA256
    assert reading["invocation"] == {
        "subject": "stub",
        "dataset": "ohlc-test",
        "window": None,
        "as_of": None,
        "accept_holes": False,
        "comparator_trial": None,
        "commit": _CLEAN_HEAD,
    }
    assert reading["dataset_hash"] == compute_hash(reading["datasets"])


def test_a_reading_of_a_subject_with_a_rule_is_refused_before_the_fit(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    calls = _stub_subject(monkeypatch)

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "declares a verdict rule" in result.output
    assert calls == []
    assert not ledger.exists()


def test_a_reading_beside_register_is_refused_before_the_fit(tmp_path, monkeypatch):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--register and --reading" in result.output
    assert calls == []
    assert not ledger.exists() and not registry.exists()


def test_a_reading_refuses_a_typed_verdict_before_the_fit(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    calls = _stub_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), "--verdict", "adopt", *_reading_args(ledger)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--verdict" in result.output
    assert calls == []
    assert not ledger.exists()


_RECORDING_PATHS = [
    pytest.param("reading", "--ledger", {"verdict": None, "no_verdict": None}, id="a-reading-runs-ledger"),
    pytest.param("register", "--ledger", {"verdict": lambda metrics: None}, id="a-stopping-register-runs-ledger"),
    pytest.param("reading", "--registry", {"verdict": None, "no_verdict": None}, id="a-reading-runs-registry"),
    pytest.param("register", "--registry", {}, id="a-register-runs-registry"),
]


@pytest.mark.parametrize(("flags", "flag", "declared"), _RECORDING_PATHS)
def test_a_ledger_or_registry_in_a_missing_directory_is_refused_before_the_fit_naming_it(
    tmp_path, monkeypatch, flags, flag, declared
):
    nodir = tmp_path / "nodir"
    registry = nodir / "r.jsonl" if flag == "--registry" else tmp_path / "registry.jsonl"
    ledger = nodir / "l.jsonl" if flag == "--ledger" else tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, **declared)
    if flags == "register":
        args = _register_args(registry, n_trials=1, ledger=ledger)
    else:
        args = [*_reading_args(ledger), "--registry", str(registry)]

    result = runner.invoke(app, [*_stub_eval(), *args])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"{flag} {nodir}" in result.output
    assert calls == []
    assert not nodir.exists() and not registry.exists() and not ledger.exists()


@pytest.mark.parametrize(("flags", "flag", "declared"), _RECORDING_PATHS)
def test_a_ledger_or_registry_that_is_a_directory_is_refused_before_the_fit_naming_it(tmp_path, monkeypatch, flags, flag, declared):
    adir = tmp_path / "adir"
    adir.mkdir()
    registry = adir if flag == "--registry" else tmp_path / "registry.jsonl"
    ledger = adir if flag == "--ledger" else tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, **declared)
    if flags == "register":
        args = _register_args(registry, n_trials=1, ledger=ledger)
    else:
        args = [*_reading_args(ledger), "--registry", str(registry)]

    result = runner.invoke(app, [*_stub_eval(), *args])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"{flag} {adir} is a directory" in result.output
    assert calls == []
    assert list(adir.iterdir()) == [] and not (tmp_path / "registry.jsonl").exists() and not (tmp_path / "ledger.jsonl").exists()


def test_a_reading_refuses_a_typed_spec_hash_other_than_the_specs_before_the_fit(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    calls = _stub_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), "--spec-hash", "0" * 64, *_reading_args(ledger)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert _STUB_SPEC in result.output
    assert calls == []
    assert not ledger.exists()


def test_a_reading_from_an_unclean_tree_is_refused_before_the_fit_listing_the_paths(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    calls = _stub_subject(monkeypatch, verdict=None, no_verdict=None)
    monkeypatch.setattr(research_command, "_tree_state", lambda root: (_CLEAN_HEAD, " M cli/research/subjects.py\n"))

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "cli/research/subjects.py" in result.output
    assert calls == []
    assert not ledger.exists()


def test_a_reading_whose_head_moves_during_the_fit_is_refused_and_nothing_kept(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    calls = _stub_subject(monkeypatch, verdict=None, no_verdict=None)
    states = iter([(_CLEAN_HEAD, ""), ("b" * 40, "")])
    monkeypatch.setattr(research_command, "_tree_state", lambda root: next(states))

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "changed during the fit" in result.output
    assert calls == ["ohlc-test"]
    assert not ledger.exists()


@pytest.mark.parametrize(
    ("returned", "declared"),
    [
        pytest.param({"sharpe": 1.0, "sortino": 2.0}, {"sharpe"}, id="one-key-more"),
        pytest.param({"sharpe": 1.0}, {"sharpe", "sortino"}, id="one-key-fewer"),
    ],
)
def test_a_reading_refuses_a_build_whose_keys_are_not_the_declared_ones(tmp_path, monkeypatch, returned, declared):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    calls = _stub_subject(monkeypatch, metrics=returned, metric_keys=frozenset(declared), verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "sortino" in result.output
    assert calls == ["ohlc-test"]
    assert not ledger.exists()


@pytest.mark.parametrize(
    ("declared", "flags", "kind"),
    [
        pytest.param({}, "register", "trial", id="a-trial"),
        pytest.param({"verdict": None, "no_verdict": None}, "reading", "reading", id="a-reading"),
        pytest.param({"verdict": lambda metrics: None}, "register", "reading", id="a-stops-reading"),
    ],
)
def test_every_append_prints_the_replay_case_of_its_line(tmp_path, monkeypatch, declared, flags, kind):
    registry, ledger = _committed_copy(tmp_path), tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, **declared)
    args = _register_args(registry, n_trials=1, ledger=ledger) if flags == "register" else _reading_args(ledger)

    result = runner.invoke(app, [*_stub_eval(), *args])

    assert result.exit_code == 0, result.output
    entries = live_entries(registry, ledger)
    if kind == "trial":
        appended = max(_trials(registry))
        (label,) = [label for label, k, entry in entries if k == "trial" and entry["trial_id"] == appended]
    else:
        (label,) = [label for label, k, _ in entries if k == "reading"]
        assert label == "reading-1"
    assert f"uv run pytest tests/test_registry_replay.py -k '[{label}]'" in result.output
    assert "data/ohlc-full" in result.output


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
    """The JSON report the command prints, read without the lines before or after it."""
    return json.JSONDecoder().raw_decode(output, output.index("{"))[0]


# `record33-combined`'s committed headline keys, pinned here as literals: reading them back off the
# subject under test would assert nothing about which metrics the command actually reports.
_COMBINED_METRIC_KEYS = {"ann_sharpe_noc", "per_period_sharpe", "bench_ann_sharpe", "cap_breach_bars", "n_periods"}
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


def _rolling_subject(monkeypatch, **declared) -> list:
    """A subject over the ten assets reading 1440 as the production builds do, returning fixed metrics so no fit's minimum
    history applies to a four-day chain; the list it returns gains each build's `as_of`."""
    calls = []

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        calls.append(as_of)
        subjects._capturing_union(reader, dataset, 1440, window, as_of, accept_holes)
        return {"sharpe": 1.0}

    assets = CrossfreqSystemConfig().assets
    subject = subjects.Subject("rolling-stub", (1440,), assets, build, **(_STUB_DECLARED | declared))
    monkeypatch.setitem(subjects.SUBJECTS, "rolling-stub", subject)
    return calls


def _rolling_eval(*args: str) -> list[str]:
    return ["research", "eval", "--subject", "rolling-stub", "--dataset", "ohlc-rolling", *args]


def test_eval_on_a_chained_set_requires_as_of(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path))
    calls = _rolling_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, _rolling_eval())

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--as-of" in result.output
    assert calls == []


@pytest.mark.parametrize("flags", [["--as-of", "2026-10-03"], ["--accept-holes"]], ids=["as-of", "accept-holes"])
def test_eval_on_an_unchained_set_refuses_as_of(tmp_path, monkeypatch, flags):
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch, verdict=None, no_verdict=None)

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
    assert record["schema_version"] == 6
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
    _rolling_subject(monkeypatch, verdict=None, no_verdict=None)

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
    calls = _rolling_subject(monkeypatch, verdict=None, no_verdict=None)

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
    _rolling_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03"))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert _BASE_LINE in result.output


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_eval_refuses_a_rolling_index_it_cannot_list_in_one_line(tmp_path, monkeypatch):
    root = _rolling_set(tmp_path)
    month = root / "ohlc-rolling" / "index/2026/10"
    _anchor(monkeypatch, root)
    calls = _rolling_subject(monkeypatch, verdict=None, no_verdict=None)
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
    calls = _rolling_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, _rolling_eval("--as-of", "2026-10-03"))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"dataset 'ohlc-rolling' is absent: no directory {root / 'ohlc-rolling'}; zcrypto data fetch" in result.output
    assert "frozen" not in result.output
    assert calls == []


def test_the_window_reaches_the_rolling_reads(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path))
    _rolling_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(
        app, _rolling_eval("--as-of", "2026-10-03", "--window", "2026-10-01 00:00:00+00:00", "2026-10-02 00:00:00+00:00")
    )

    assert result.exit_code == 0, result.output
    block = _block_and_metrics(result.output)["datasets"]["ohlc-rolling"]
    assert block["rows"] == 20
    assert block["span"] == ["2026-10-01 00:00:00+00:00", "2026-10-02 00:00:00+00:00"]


@pytest.mark.retired
def test_the_b2_subject_is_registered_over_the_ten_assets_4h_series():
    subject = subjects.SUBJECTS["b2-funding-derisk"]
    assert subject.name == "b2-funding-derisk"
    assert subject.intervals == (240,)
    assert subject.assets == CrossfreqSystemConfig().assets
    assert subject.build is subjects._build_b2_funding_derisk


@pytest.mark.retired
def test_the_b2_subjects_cost_arms_lookback_and_periods_are_the_literals_its_spec_fixes():
    assert subjects._B2_COST_PER_SIDE == 0.006
    assert subjects._B2_A2_ARMS == (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    assert subjects._B2_LOOKBACK == 180
    assert subjects.PPY_4H == 2190


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
    if subject.verdict is None:
        assert subject.family is None and subject.n_trials is None
    else:
        assert subject.family in budget.BUCKET_OF and type(subject.n_trials) is int and subject.n_trials >= 1


def test_each_subject_declares_the_metric_keys_its_build_returns():
    assert subjects.SUBJECTS["b2-funding-derisk"].metric_keys == _B2_METRIC_KEYS
    assert subjects.SUBJECTS["record33-combined"].metric_keys == _COMBINED_METRIC_KEYS
    assert subjects.SUBJECTS["record44-crossfreq"].metric_keys == _CROSSFREQ_METRIC_KEYS
    assert subjects.SUBJECTS["b1-hourly-rv"].metric_keys == _B1_HOURLY_RV_METRIC_KEYS
    assert subjects.SUBJECTS["b1-hourly-rv-preflight"].metric_keys == _B1_HOURLY_RV_PREFLIGHT_KEYS
    assert subjects.SUBJECTS["b1-volume-confirmation"].metric_keys == _B1_VOLUME_METRIC_KEYS
    assert subjects.SUBJECTS["b1-volume-confirmation-preflight"].metric_keys == _B1_VOLUME_PREFLIGHT_KEYS
    assert subjects.SUBJECTS["b1-hourly-channel-exits"].metric_keys == _B1_EXIT_METRIC_KEYS
    assert subjects.SUBJECTS["b1-hourly-channel-exits-preflight"].metric_keys == _B1_EXIT_PREFLIGHT_KEYS
    assert subjects.SUBJECTS["b2-funding-derisk-full"].metric_keys == _B2_METRIC_KEYS
    assert subjects.SUBJECTS["b2-funding-derisk-full-preflight"].metric_keys == _B2_FULL_PREFLIGHT_KEYS
    for name, (signal_key, _, _) in _B2_OVERLAYS.items():
        assert subjects.SUBJECTS[name].metric_keys == _overlay_metric_keys(signal_key)
        assert subjects.SUBJECTS[f"{name}-preflight"].metric_keys == _overlay_preflight_keys(signal_key)
    for name, (signal_key, *_) in _B2_REENTRIES.items():
        assert subjects.SUBJECTS[name].metric_keys == _overlay_metric_keys(signal_key)
        assert subjects.SUBJECTS[f"{name}-preflight"].metric_keys == _overlay_preflight_keys(signal_key)
    assert subjects.SUBJECTS["b2-liq-tape-reading"].metric_keys == _B2_TAPE_SPEC_KEYS


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


@pytest.mark.retired
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


_B1_START = datetime(2015, 6, 1, tzinfo=UTC)
_B1_BARS = 1_600  # 4h bars: 1,599 return indices, 315 of them from 2016-01-01, closes in 2015 and 2016


def _b1_dataset(tmp_path: Path, *, start: datetime = _B1_START, bars: int = _B1_BARS, m15: bool = True) -> Path:
    """Its 15m set's last bar closes four hours past the last 4h decision boundary, so the vol scaler's extent check passes."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        rows = _rows(bars, phase=i * 0.7, start=int(start.timestamp()), step=4 * 3600)
        write_parquet(to_frame(rows), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
        if m15:
            rows = _rows(bars * 16, phase=i * 0.7, start=int(start.timestamp()), step=900)
            write_parquet(to_frame(rows), root / "ohlc-15m" / f"{asset}/EUR/15.parquet")
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


@pytest.mark.retired
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
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, root, registry)
    ts = [_B2_START + timedelta(hours=4 * k) for k in range(_B2_WINDOW_BARS)]
    close = [t + timedelta(hours=4) for t in ts[:-1]]
    k21 = next(k for k, t in enumerate(close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert k21 == 551
    window = (str(ts[0]), str(ts[-1]))

    inputs = subjects._b2_inputs(ObservedReader(root), "ohlc-test", window, None, False, subject="b2-funding-derisk")
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
        + _register_args(registry, n_trials=1, family="B2", ledger=ledger),
    )
    assert result.exit_code == 0, result.output
    if arm_a_passes:
        reported = json.loads(registry.read_text())
        assert reported["verdict"] == "reject"
        assert reported["seeds"] == [42, 7, 1234]
        assert reported["metrics"]["arm_a_passes"] == 7
        assert not ledger.exists()
    else:
        stop = subjects.SUBJECTS["b2-funding-derisk"].no_verdict
        assert f"no verdict — {stop}: recorded reading 1; no trial spent" in result.output
        assert not registry.exists()
        reported = _block_and_metrics(result.output)
        (reading,) = _kept(ledger)
        assert reading["metrics"] == reported["metrics"]
        assert reading["outcome"] == stop

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


@pytest.mark.retired
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

    result = runner.invoke(app, [*_b2_eval(_B2_START, _B2_WINDOW_BARS), *_as_trial("b2-funding-derisk", tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"derivatives-funding/{_B2_SPOILT}/funding.parquet" in result.output
    assert cause in result.output


@pytest.mark.retired
@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_the_b2_subject_refuses_a_funding_file_it_may_not_open_naming_it(tmp_path, monkeypatch):
    root = _b2_dataset(tmp_path)
    spoilt = root / "derivatives-funding" / _B2_SPOILT / "funding.parquet"
    _anchor(monkeypatch, root)
    os.chmod(spoilt, 0o000)
    try:
        result = runner.invoke(app, [*_b2_eval(_B2_START, _B2_WINDOW_BARS), *_as_trial("b2-funding-derisk", tmp_path)])
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

    result = runner.invoke(app, [*_b2_eval(_B2_START, _B2_WINDOW_BARS), *_as_trial("b2-funding-derisk", tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert "ohlc-test/ETH/EUR/240.parquet" in result.output
    assert cause in result.output


@pytest.mark.retired
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

    result = runner.invoke(app, [*args, *_as_trial("b2-funding-derisk", tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"b2-funding-derisk over the window {args[-2]} .. {args[-1]}: {cause}" in result.output


def _one_bar_in_the_window(path: Path) -> None:
    frame = pl.read_parquet(path)
    frame.filter(pl.col("ts") >= frame["ts"][_B2_WINDOW_BARS - 1]).write_parquet(path)


@pytest.mark.retired
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

    result = runner.invoke(app, [*args, *_as_trial("b2-funding-derisk", tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"b2-funding-derisk over the window {args[-2]} .. {args[-1]}: prices must be a list of >= 2 values" in result.output


@pytest.mark.retired
def test_the_b2_inputs_scale_each_spiking_asset_from_the_first_close_at_or_after_its_first_spike(tmp_path):
    ts = [_B2_START + timedelta(hours=4 * k) for k in range(_B2_WINDOW_BARS)]
    inputs = subjects._b2_inputs(
        ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", (str(ts[0]), str(ts[-1])), None, False, subject="b2-funding-derisk"
    )

    first = {a: next((k for k, s in enumerate(inputs.scales[a]) if s != 1.0), None) for a in _B2_ASSETS}

    # Asset i's first spike prints at bar 822 + 2i's open, which closes return index 821 + 2i.
    spikes = _B2_FALLS[1][0] - 1
    assert first == {a: None if a == _B2_NEVER_SPIKES else spikes + 2 * i for i, a in enumerate(_B2_ASSETS)}


# Spec 00129 D7's ten keys of arm A's bar, pinned as literals for the reason `_COMBINED_METRIC_KEYS` is.
_ARM_A_BAR_KEYS = {
    "dsr",
    "dsr_pass",
    "spa_p_value",
    "spa_p_value_full",
    "spa_pass",
    "cost_stress_sharpe",
    "cost_stress_pass",
    "worst_slice_sharpe",
    "worst_slice_pass",
    "passes",
}
_ARM_A_BAR_FLAGS = {"dsr_pass", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes"}


@pytest.mark.retired
def test_the_arm_a_bar_subject_returns_its_ten_keys_as_ints_and_floats_and_never_builds_arm_b(tmp_path, monkeypatch):
    root = _b2_dataset(tmp_path)
    ts = [_B2_START + timedelta(hours=4 * k) for k in range(_B2_WINDOW_BARS)]
    scaled = _recording(monkeypatch, "scale_positions", lambda arguments, result: result)
    subject = subjects.SUBJECTS["b2-arm-a-bar"]

    metrics = subject.build(ObservedReader(root), "ohlc-test", (str(ts[0]), str(ts[-1])))

    assert subject.metric_keys == _ARM_A_BAR_KEYS
    assert set(metrics) == _ARM_A_BAR_KEYS
    assert {key for key, value in metrics.items() if type(value) is int} == _ARM_A_BAR_FLAGS
    assert {key for key, value in metrics.items() if type(value) is float} == _ARM_A_BAR_KEYS - _ARM_A_BAR_FLAGS
    assert {metrics[flag] for flag in _ARM_A_BAR_FLAGS} <= {0, 1}
    assert scaled == []


@pytest.mark.retired
def test_the_b2_subject_refuses_a_window_its_benchmark_never_trades_naming_it(tmp_path, monkeypatch):
    """A window the frozen benchmark's 1,200-bar gate never opens over leaves its returns flat; the fixture's gate opens,
    so the flat series is handed in."""
    _anchor(monkeypatch, _b2_dataset(tmp_path))
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", lambda prices, *, cost_per_side: [0.0] * (len(prices["BTC"]) - 1))
    args = _b2_eval(_B2_START, _B2_WINDOW_BARS)

    result = runner.invoke(app, [*args, *_as_trial("b2-funding-derisk", tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"b2-funding-derisk over the window {args[-2]} .. {args[-1]}: no non-degenerate slice to compare" in result.output


_B2_FULL_SPEC = "docs/specs/00137-b2-trial-2-ohlc-full-design.md"
_B2_FULL_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"
)
_B2_FULL_ANCHORS = frozenset(
    {
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown_full",
        "turnover_a",
        "arm_a_spot_drag_pct_yr",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    }
)
_B2_FULL_ENGAGEMENT = frozenset({"engaged_per_asset", "engaged_per_year", "binperp_funding_z30d_coverage"})
# Spec 00137 D9's keys of the pre-flight, typed from the spec, never read off the subject.
_B2_FULL_PREFLIGHT_KEYS = _B2_FULL_ANCHORS | _ARM_A_BAR_KEYS | _B2_FULL_ENGAGEMENT


@pytest.mark.retired
def test_the_b2_full_subjects_declare_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count():
    trial, preflight = subjects.SUBJECTS["b2-funding-derisk-full"], subjects.SUBJECTS["b2-funding-derisk-full-preflight"]
    assert (len(_B2_METRIC_KEYS), len(_B2_FULL_PREFLIGHT_KEYS)) == (40, 20)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        "b2-funding-derisk-full",
        (240,),
        _B2_ASSETS,
        _B2_FULL_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b2_funding_derisk_full and trial.metric_keys == _B2_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_verdict, _B2_FULL_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", 1) == ("B2", subjects._B2_FULL_N_TRIALS)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        "b2-funding-derisk-full-preflight",
        (240,),
        _B2_ASSETS,
        _B2_FULL_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b2_funding_derisk_full_preflight
    assert preflight.metric_keys == _B2_FULL_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


# Adopting on every key the rule reads, the full-window head-to-head and the block-102 cell set against the verdict, so a
# rule reading either in place of the from-2021 read or the headline cell moves the first row.
_B2_FULL_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2013": 0, "2021": 4},
    "passes": 1,
    "head_to_head_mean_outperf_2021": 0.001,
    "head_to_head_spa_p_2021": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "spa_p_decisive_b102_s42": 0.9,
    "max_drawdown_reduction_pct": 5.0,
}
_B2_FULL_NEVER_ENGAGED = {"engaged_per_year": {"2013": 0, "2021": 0}}


@pytest.mark.retired
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-outperforms-significantly-from-2021-and-draws-down-less"),
        pytest.param({"head_to_head_spa_p_2021": 0.0499}, "adopt", id="row-1-p-at-0.0499"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6}, "adopt", id="row-1-reduction-past-1e-6"),
        pytest.param({"head_to_head_spa_p_2021": 0.2}, "park", id="row-2-outperforms-insignificantly-from-2021"),
        pytest.param({"head_to_head_spa_p_2021": 0.05}, "park", id="row-2-p-at-exactly-0.05"),
        pytest.param({"head_to_head_mean_outperf_2021": -0.001}, "reject", id="row-3-underperforms-from-2021"),
        pytest.param({"head_to_head_mean_outperf_2021": 0.0}, "reject", id="row-3-mean-at-exactly-0"),
        pytest.param({"max_drawdown_reduction_pct": -5.0}, "reject", id="row-3-draws-down-more"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="row-3-reduction-at-exactly-1e-6"),
        pytest.param(
            {"head_to_head_mean_outperf_2021": -0.001, "head_to_head_mean_outperf_full": 0.001, "head_to_head_spa_p_full": 0.01},
            "reject",
            id="row-3-outperforms-over-the-full-window-alone",
        ),
        pytest.param({"passes": 0}, "reject", id="row-4-arm-b-fails-its-bar"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_FULL_NEVER_ENGAGED, None, id="the-overlay-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_FULL_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
    ],
)
def test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop(change, verdict):
    assert subjects.SUBJECTS["b2-funding-derisk-full"].verdict({**_B2_FULL_ADOPTING, **change}) == verdict


def _fingerprint(*parts) -> bytes:
    return hashlib.sha256(repr(parts).encode()).digest()


def _fake_kill_bar(
    book_net_returns,
    benchmark_net_returns,
    *,
    n_trials,
    var_trials,
    mean_block,
    seed,
    cost_stressed_returns,
    regime_slices,
    benchmark_slices,
    decisive_start=0,
    n_resamples=1000,
):
    """Each value a function of every argument: two builds making the same calls get the same results, and a key read off
    another call or another key differs; the flags are ints other than 0 and 1."""
    d = _fingerprint(
        book_net_returns,
        benchmark_net_returns,
        n_trials,
        var_trials,
        mean_block,
        seed,
        cost_stressed_returns,
        regime_slices,
        benchmark_slices,
        decisive_start,
        n_resamples,
    )
    floats = ("dsr", "spa_p_value", "spa_p_value_full", "cost_stress_sharpe", "worst_slice_sharpe")
    return (
        {key: d[i] / 256 + i for i, key in enumerate(floats)}
        | {key: 2 + d[10 + i] for i, key in enumerate(_B2_FLAGS)}
        | {"passes": 2 + d[20]}
    )


def _fake_benchmark(h4_prices, *, cost_per_side):
    d = _fingerprint(h4_prices, cost_per_side)
    return [(d[k % 32] - 128) / 1e5 for k in range(len(h4_prices["BTC"]) - 1)]


def _fake_head_to_head(book_net_of_cost, benchmark_net_of_cost, *, mean_block, seed, n_resamples=2000):
    d = _fingerprint(book_net_of_cost, benchmark_net_of_cost, mean_block, seed, n_resamples)
    return {
        "spa_p_value": d[0] / 256,
        "beats": False,
        "book_sharpe": 0.0,
        "benchmark_sharpe": 0.0,
        "mean_outperformance": d[1] - 128,
    }


@pytest.mark.retired
def test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept(tmp_path, monkeypatch):
    inputs = subjects._b2_inputs(
        ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", None, None, False, subject="b2-funding-derisk-full"
    )
    n = len(inputs.close)
    k21 = next(k for k, t in enumerate(inputs.close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert (n, k21) == (_B2_BARS - 1, 551)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    full = subjects._b2_full_metrics(inputs)

    assert set(full) == _B2_METRIC_KEYS
    assert sorted((arguments["mean_block"], arguments["seed"]) for arguments, _ in bars) == sorted([*_B2_GRID, (30, 42)])
    for arguments, _ in bars:
        assert (arguments["n_trials"], arguments["var_trials"], arguments["decisive_start"], arguments["n_resamples"]) == (
            1,
            0.0,
            1380,
            2000,
        )
        assert list(arguments["regime_slices"]) == list(arguments["benchmark_slices"]) == ["2020", "2021"]
    assert [len(arguments["book_net_of_cost"]) for arguments, _ in head_to_heads] == [n, n - k21]
    # Spec 00128's metrics, `_b2_slices` read as the stub years alone and at the full subject's count: `_b2_full_metrics`
    # must not call `_b2_slices`.
    monkeypatch.setattr(subjects, "_b2_slices", calendar_year_slices)
    monkeypatch.setattr(subjects, "_B2_N_TRIALS", subjects._B2_FULL_N_TRIALS)
    assert subjects._b2_metrics(inputs) == full


@pytest.mark.retired
def test_where_no_z_score_is_defined_the_b2_full_subjects_arm_b_is_arm_a_bit_for_bit(tmp_path, monkeypatch):
    inputs = subjects._b2_inputs(
        ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", None, None, False, subject="b2-funding-derisk-full"
    )
    dark = {a: [None] * len(inputs.close) for a in _B2_ASSETS}
    inputs = inputs._replace(binperp_funding_z30d=dark, scales=derisk_scales(dark, config=B2Config()))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    full = subjects._b2_full_metrics(inputs)

    assert [arguments["book_net_of_cost"] == arguments["benchmark_net_of_cost"] for arguments, _ in head_to_heads] == [True] * 2
    assert (full["stamps_positions_differ"], full["turnover_b"], full["max_drawdown"], full["max_drawdown_reduction_pct"]) == (
        0,
        full["turnover_a"],
        full["arm_a_max_drawdown"],
        0.0,
    )
    assert set(full["engaged_per_year"].values()) == {0}


@pytest.mark.retired
def test_the_b2_full_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b(tmp_path, monkeypatch):
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    def arm_b(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions")

    monkeypatch.setattr(subjects, "scale_positions", arm_b)
    reads = _recording(monkeypatch, "_b2_inputs", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS["b2-funding-derisk-full-preflight"].build(ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", None)

    ((_, inputs),) = reads
    returns = {a: _asset_returns(_ffill_btc(inputs.h4_prices)[a]) for a in _B2_ASSETS}
    net_a, net_a_x15 = (net_of_cost(inputs.arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.close)
    ((arguments, bar),) = bars
    assert arguments == {
        "book_net_returns": net_a,
        "benchmark_net_returns": bench,
        "n_trials": 1,
        "var_trials": 0.0,
        "mean_block": 30,
        "seed": 42,
        "cost_stressed_returns": net_a_x15,
        "regime_slices": calendar_year_slices(net_a, inputs.h4_ts),
        "benchmark_slices": calendar_year_slices(bench, inputs.h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    engaged = {a: sum(p > 0 and s < 1 for p, s in zip(inputs.arm_a[a], inputs.scales[a])) for a in _B2_ASSETS}
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        "engaged_per_asset": engaged,
        "engaged_per_year": per_year_engaged_counts(inputs.arm_a, inputs.scales, inputs.close),
        "binperp_funding_z30d_coverage": {
            a: {
                str(year): [c.non_null, c.total]
                for year, c in coverage_by_year(inputs.close, inputs.binperp_funding_z30d[a]).items()
            }
            for a in _B2_ASSETS
        },
    }
    assert set(metrics) == _B2_FULL_PREFLIGHT_KEYS
    assert sum(engaged.values()) == sum(metrics["engaged_per_year"].values()) > 0
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0


@pytest.mark.parametrize("name", ["b2-funding-derisk-full", "b2-funding-derisk-full-preflight"])
def test_a_b2_full_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, [*args, *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"{name} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen "
        "--dataset"
    ) in result.output


@pytest.mark.retired
@pytest.mark.parametrize(
    ("flags", "refused"),
    [
        pytest.param(
            [],
            "b2-funding-derisk-full declares a verdict rule, so every run of it is a trial: run it with --register",
            id="plain-eval",
        ),
        pytest.param(
            ["--register", "--iteration", "iter-181", "--family", "B2", "--n-trials", "2"],
            "--n-trials 2 is not 1, the count b2-funding-derisk-full declares and deflates at: pass --n-trials 1",
            id="another-count",
        ),
    ],
)
def test_b2_full_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, flags, refused):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_inputs", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-funding-derisk-full", "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.retired
@pytest.mark.parametrize(
    ("bars", "cause"),
    [
        pytest.param(
            1_471,
            "1 of its return indices close at or after 2021-01-01T00:00Z, and the from-2021 head-to-head needs 2",
            id="one-index-into-2021",
        ),
        pytest.param(
            1_472,
            "arm A never draws down from 2021-01-01T00:00Z, so max_drawdown_reduction_pct divides by zero",
            id="arm-a-never-draws-down-from-2021",
        ),
    ],
)
def test_the_b2_full_subject_refuses_a_window_it_cannot_evaluate_before_any_bar(tmp_path, monkeypatch, bars, cause):
    _anchor(monkeypatch, _b2_dataset(tmp_path, start=_B2_FROM_MAY_2020))
    args = _b2_eval(_B2_FROM_MAY_2020, bars)
    args[args.index("b2-funding-derisk")] = "b2-funding-derisk-full"
    kill_bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    result = runner.invoke(app, [*args, *_as_trial("b2-funding-derisk-full", tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"b2-funding-derisk-full over the window {args[-2]} .. {args[-1]}: {cause}" in result.output
    assert kill_bars == []


@pytest.mark.retired
def test_the_b2_full_subject_refuses_a_funding_file_it_cannot_read_naming_it(tmp_path, monkeypatch):
    root = _b2_dataset(tmp_path)
    (root / "derivatives-funding" / _B2_SPOILT / "funding.parquet").write_bytes(b"not a parquet file")
    _anchor(monkeypatch, root)
    args = ["research", "eval", "--subject", "b2-funding-derisk-full", "--dataset", "ohlc-test"]

    result = runner.invoke(app, [*args, *_as_trial("b2-funding-derisk-full", tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"derivatives-funding/{_B2_SPOILT}/funding.parquet" in result.output
    assert "File out of specification" in result.output


_B2_OVERLAY_SPEC = "docs/specs/00138-b2-three-overlays-design.md"
_B2_OVERLAY_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"
)
# Spec 00138's three trials: each signal's key, threshold and count, typed from the spec, never read off a subject; the
# liquidations trial's threshold is the one its build reads off the engagement rule, `None` here.
_B2_OVERLAYS = {
    "b2-oi-derisk": ("binperp_oi_z30d", 2.5, 2),
    "b2-ratio-derisk": ("binperp_ratio_max_z30d", 2.5, 3),
    "b2-liq-derisk": ("binperp_liq_long_z30d", None, 4),
}
_B2_OVERLAY_RATIOS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
_B2_OVERLAY_FROM_BAR = 300
_B2_OVERLAY_SPIKE_BARS = 12


def _overlay_metric_keys(signal_key: str) -> frozenset[str]:
    moved = {"head_to_head_mean_outperf_2021", "head_to_head_spa_p_2021", "binperp_funding_z30d_coverage"}
    return frozenset(_B2_METRIC_KEYS - moved) | {
        "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_primary",
        "primary_returns",
        "threshold",
        f"{signal_key}_coverage",
    }


def _overlay_preflight_keys(signal_key: str) -> frozenset[str]:
    return (_B2_FULL_PREFLIGHT_KEYS - {"binperp_funding_z30d_coverage"}) | {
        "primary_returns",
        "threshold",
        f"{signal_key}_coverage",
    }


def _overlay_threshold(name: str):
    threshold = _B2_OVERLAYS[name][1]
    return subjects._b2_engagement_threshold if threshold is None else threshold


def _overlay_signal(name: str):
    return {
        "b2-oi-derisk": subjects._b2_oi_signal,
        "b2-ratio-derisk": subjects._b2_ratio_signal,
        "b2-liq-derisk": subjects._b2_liq_signal,
    }[name]


@pytest.fixture(autouse=True)
def _liquidations_blocks_unattested(monkeypatch):
    """Keeps the read guard inert over a fixture's synthetic `liquidations-daily` and `liquidations-frozen`."""
    attested = sync._sidecar_by_dataset()
    blocks = ("liquidations-daily", "liquidations-frozen")
    monkeypatch.setattr(sync, "_sidecar_by_dataset", lambda: {name: s for name, s in attested.items() if name not in blocks})


def _b2_overlay_dataset(
    tmp_path: Path, *, start: datetime = _B2_START, flat: bool = False, from_bar: int = _B2_OVERLAY_FROM_BAR
) -> Path:
    """`_b2_dataset`'s ten 4h series, a `derivatives-oi` set and a daily liquidations block, each running 30 days past the
    union: BTC's OI rows open 47 days before it, every other asset's at bar `from_bar` and the daily rows at the first day
    after it; every asset but one spikes in its OI level and one of its four ratios for twelve bars, and in its long
    notional for two days, from its own bar inside the second fall, so each overlay de-risks each asset at its own
    stamps."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        write_parquet(to_frame(_b2_ohlc_rows(i * 0.7, start, flat)), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    opens, end = start + timedelta(hours=4 * from_bar), start + timedelta(hours=4 * _B2_BARS, days=30)
    day0 = (opens + timedelta(days=1)).replace(hour=0)
    days = [day0 + timedelta(days=d) for d in range((end - day0) // timedelta(days=1))]
    for i, asset in enumerate(_B2_ASSETS):
        spike = start + timedelta(hours=4 * (_B2_FALLS[1][0] + 2 * i))

        def hot(t: datetime) -> bool:
            return asset != _B2_NEVER_SPIKES and spike <= t < spike + timedelta(hours=4 * _B2_OVERLAY_SPIKE_BARS)

        first = _B2_FUNDING_FROM if asset == "BTC" else opens
        marks = [first + timedelta(hours=4 * j) for j in range((end - first) // timedelta(hours=4))]
        columns = {
            "ts": marks,
            "sum_open_interest": [2_000.0 if hot(t) else 1_000.0 + 10 * math.sin(j / 3 + i) for j, t in enumerate(marks)],
            "sum_open_interest_value": [1e7] * len(marks),
        }
        for c, ratio in enumerate(_B2_OVERLAY_RATIOS):
            columns[ratio] = [3.0 if hot(t) and c == i % 4 else 1.0 + 0.05 * math.sin(j / 5 + i + c) for j, t in enumerate(marks)]
        schema = {"ts": pl.Datetime("us", "UTC")} | dict.fromkeys(list(columns)[1:], pl.Float64)
        write_parquet(pl.DataFrame(columns, schema=schema), root / "derivatives-oi" / PERP_SYMBOLS[asset] / "oi.parquet")
        spike_day = spike.replace(hour=0)
        daily = {
            "ts": days,
            "long_usd": [
                1e7
                if asset != _B2_NEVER_SPIKES and spike_day <= d <= spike_day + timedelta(days=1)
                else 1e4 + 3e3 * math.sin(k / 3 + i)
                for k, d in enumerate(days)
            ],
            "short_usd": [8e3 + 2e3 * math.cos(k / 5 + i) for k in range(len(days))],
        }
        schema = {"ts": pl.Datetime("us", "UTC"), "long_usd": pl.Float64, "short_usd": pl.Float64}
        write_parquet(pl.DataFrame(daily, schema=schema), root / "liquidations-daily" / asset / "daily.parquet")
    return root


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    signal_key, _, count = _B2_OVERLAYS[name]
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    builder = f"_build_{name.replace('-', '_')}"
    assert (len(_overlay_metric_keys(signal_key)), len(_overlay_preflight_keys(signal_key))) == (42, 22)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B2_OVERLAY_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is getattr(subjects, builder) and trial.metric_keys == _overlay_metric_keys(signal_key)
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_overlay_verdict, _B2_OVERLAY_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", count)
    assert (preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == ((240,), _B2_ASSETS, _B2_OVERLAY_SPEC, (42,))
    assert preflight.build is getattr(subjects, f"{builder}_preflight")
    assert preflight.metric_keys == _overlay_preflight_keys(signal_key)
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


# Adopting on every key the rule reads, the full-window head-to-head and the block-102 cell set against the verdict, so a
# rule reading either in place of the primary read or the headline cell moves the first row.
_B2_OVERLAY_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2013": 0, "2023": 4},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "spa_p_decisive_b102_s42": 0.9,
    "max_drawdown_reduction_pct": 5.0,
}
_B2_OVERLAY_NEVER_ENGAGED = {"engaged_per_year": {"2013": 0, "2023": 0}}


@pytest.mark.retired
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-outperforms-significantly-from-the-start-and-draws-down-less"),
        pytest.param({"head_to_head_spa_p_primary": 0.0499}, "adopt", id="row-1-p-at-0.0499"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6}, "adopt", id="row-1-reduction-past-1e-6"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="row-2-outperforms-insignificantly-from-the-start"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="row-2-p-at-exactly-0.05"),
        pytest.param({"head_to_head_mean_outperf_primary": -0.001}, "reject", id="row-3-underperforms-from-the-start"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="row-3-mean-at-exactly-0"),
        pytest.param({"max_drawdown_reduction_pct": -5.0}, "reject", id="row-3-draws-down-more"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="row-3-reduction-at-exactly-1e-6"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001, "head_to_head_spa_p_full": 0.01},
            "reject",
            id="row-3-outperforms-over-the-full-window-alone",
        ),
        pytest.param({"passes": 0}, "reject", id="row-4-arm-b-fails-its-bar"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_OVERLAY_NEVER_ENGAGED, None, id="the-overlay-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_OVERLAY_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
    ],
)
def test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b2_overlay_verdict({**_B2_OVERLAY_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count(tmp_path, monkeypatch, name):
    signal_key, threshold, count = _B2_OVERLAYS[name]
    scalings = _recording(monkeypatch, "derisk_scales", lambda arguments, result: result)
    reader = ObservedReader(_b2_overlay_dataset(tmp_path))
    inputs = subjects._b2_overlay_inputs(name, _overlay_signal(name), _overlay_threshold(name), reader, "ohlc-test", None, False)
    start = next(k for k in range(len(inputs.close)) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS))
    assert 0 < start < len(inputs.close) - 2
    ruled = subjects._b2_engagement_threshold(inputs.signal, inputs.arm_a) if threshold is None else threshold
    assert [(arguments["z_by_asset"], arguments["config"]) for arguments, _ in scalings] == [
        (inputs.signal, B2Config(z_threshold=ruled))
    ]
    assert inputs.threshold == ruled
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b2_overlay_metrics(inputs, signal_key=signal_key, n_trials=count)

    assert set(metrics) == _overlay_metric_keys(signal_key) and {arguments["n_trials"] for arguments, _ in bars} == {count}
    # Trial 2's metrics over the same positions and signal, its from-2021 read moved to this signal's start and its count to
    # this trial's: `_b2_full_metrics`' own test proves it against a hand computation.
    monkeypatch.setattr(subjects, "_FROM_2021", inputs.close[start])
    monkeypatch.setattr(subjects, "_B2_FULL_N_TRIALS", count)
    trial_2 = subjects._b2_full_metrics(subjects._B2Inputs(*inputs[:6]))
    renamed = {
        "head_to_head_mean_outperf_2021": "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_2021": "head_to_head_spa_p_primary",
        "binperp_funding_z30d_coverage": f"{signal_key}_coverage",
    }
    assert {renamed.get(key, key): value for key, value in trial_2.items()} | {
        "primary_returns": len(inputs.close) - start,
        "threshold": ruled,
    } == metrics


@pytest.mark.retired
def test_where_no_signal_crosses_its_threshold_a_b2_overlays_arm_b_is_arm_a_bit_for_bit(tmp_path, monkeypatch):
    reader = ObservedReader(_b2_overlay_dataset(tmp_path))
    inputs = subjects._b2_overlay_inputs("b2-oi-derisk", subjects._b2_oi_signal, 2.5, reader, "ohlc-test", None, False)
    calm = {a: [0.0] * len(inputs.close) for a in _B2_ASSETS}
    inputs = inputs._replace(signal=calm, scales=derisk_scales(calm, config=B2Config(z_threshold=2.5)))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b2_overlay_metrics(inputs, signal_key="binperp_oi_z30d", n_trials=2)

    assert [arguments["book_net_of_cost"] == arguments["benchmark_net_of_cost"] for arguments, _ in head_to_heads] == [True] * 2
    assert (
        metrics["stamps_positions_differ"],
        metrics["turnover_b"],
        metrics["max_drawdown"],
        metrics["max_drawdown_reduction_pct"],
    ) == (
        0,
        metrics["turnover_a"],
        metrics["arm_a_max_drawdown"],
        0.0,
    )
    assert metrics["primary_returns"] == len(inputs.close) and set(metrics["engaged_per_year"].values()) == {0}


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b(tmp_path, monkeypatch, name):
    signal_key, threshold, count = _B2_OVERLAYS[name]
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    def arm_b(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions")

    monkeypatch.setattr(subjects, "scale_positions", arm_b)
    reads = _recording(monkeypatch, "_b2_overlay_inputs", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS[f"{name}-preflight"].build(ObservedReader(_b2_overlay_dataset(tmp_path)), "ohlc-test", None)

    ((read, inputs),) = reads
    assert (read["subject"], read["read_signal"], read["threshold"]) == (
        f"{name}-preflight",
        _overlay_signal(name),
        _overlay_threshold(name),
    )
    returns = {a: _asset_returns(_ffill_btc(inputs.h4_prices)[a]) for a in _B2_ASSETS}
    net_a, net_a_x15 = (net_of_cost(inputs.arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.close)
    start = next((k for k in range(n) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS)), n)
    ((arguments, bar),) = bars
    assert arguments == {
        "book_net_returns": net_a,
        "benchmark_net_returns": bench,
        "n_trials": count,
        "var_trials": 0.0,
        "mean_block": 30,
        "seed": 42,
        "cost_stressed_returns": net_a_x15,
        "regime_slices": calendar_year_slices(net_a, inputs.h4_ts),
        "benchmark_slices": calendar_year_slices(bench, inputs.h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    engaged = {a: sum(p > 0 and s < 1 for p, s in zip(inputs.arm_a[a], inputs.scales[a])) for a in _B2_ASSETS}
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        "engaged_per_asset": engaged,
        "engaged_per_year": per_year_engaged_counts(inputs.arm_a, inputs.scales, inputs.close),
        f"{signal_key}_coverage": {
            a: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(inputs.close, inputs.signal[a]).items()}
            for a in _B2_ASSETS
        },
        "primary_returns": n - start,
        "threshold": inputs.threshold,
    }
    assert set(metrics) == _overlay_preflight_keys(signal_key) and 0 < start < n - 2
    assert inputs.threshold == (subjects._b2_engagement_threshold(inputs.signal, inputs.arm_a) if threshold is None else threshold)
    assert sum(engaged.values()) == sum(metrics["engaged_per_year"].values()) > 0
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0


@pytest.mark.retired
def test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero(tmp_path, monkeypatch):
    # The daily block opening where the union ends: no close carries the signal, and the rule reads no long stamp.
    root = _b2_overlay_dataset(tmp_path, from_bar=_B2_BARS)
    _anchor(monkeypatch, root)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-liq-derisk-preflight", "--dataset", "ohlc-test"])

    assert result.exit_code == 0, result.output
    metrics = _block_and_metrics(result.output)["metrics"]
    assert (metrics["primary_returns"], set(metrics["engaged_per_year"].values()), set(metrics["engaged_per_asset"].values())) == (
        0,
        {0},
        {0},
    )
    assert {count for years in metrics["binperp_liq_long_z30d_coverage"].values() for count, _ in years.values()} == {0}
    assert metrics["threshold"] == 2.5


@pytest.mark.parametrize("name", sorted({*_B2_OVERLAYS, *(f"{name}-preflight" for name in _B2_OVERLAYS)}))
def test_a_b2_overlay_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, [*args, *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"{name} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen "
        "--dataset"
    ) in result.output


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    count = _B2_OVERLAYS[name][2]
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_overlay_inputs", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-182", "--family", "B2", "--n-trials", str(count + 1)]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials {count + 1} is not {count}, the count {name} declares and deflates at: pass --n-trials {count}"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.parametrize(
    ("name", "from_bar", "cause"),
    [
        pytest.param(
            "b2-oi-derisk",
            1_460,
            "1 of its return indices carry every asset's binperp_oi_z30d, and the head-to-head from the signal's own start needs 2",
            id="oi-one-index-from-the-start",
        ),
        pytest.param(
            "b2-liq-derisk",
            1_460,
            "0 of its return indices carry every asset's binperp_liq_long_z30d, and the head-to-head from the signal's own "
            "start needs 2",
            id="liquidations-no-index-from-the-start",
        ),
        pytest.param(
            "b2-oi-derisk",
            1_459,
            "arm A never draws down from the signal's own start, so max_drawdown_reduction_pct divides by zero",
            id="oi-arm-a-never-draws-down-from-the-start",
        ),
    ],
)
def test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar(tmp_path, monkeypatch, name, from_bar, cause):
    _anchor(monkeypatch, _b2_overlay_dataset(tmp_path, from_bar=from_bar))
    kill_bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the full history: {cause}" in result.output
    assert kill_bars == []


def _not_parquet(path: Path) -> None:
    path.write_bytes(b"not a parquet file")


@pytest.mark.parametrize(
    ("name", "relpath", "spoil", "cause"),
    [
        pytest.param("b2-oi-derisk", f"derivatives-oi/{_B2_SPOILT}/oi.parquet", _not_parquet, "File out of specification", id="oi"),
        pytest.param(
            "b2-ratio-derisk-preflight",
            f"derivatives-oi/{_B2_SPOILT}/oi.parquet",
            lambda path: pl.read_parquet(path).drop("count_long_short_ratio").write_parquet(path),
            '"count_long_short_ratio" not found',
            id="ratio",
        ),
        pytest.param(
            "b2-liq-derisk",
            "liquidations-daily/SOL/daily.parquet",
            lambda path: pl.read_parquet(path).drop("long_usd").write_parquet(path),
            '"long_usd" not found',
            id="liquidation-daily",
        ),
        pytest.param(
            "b2-liq-derisk-preflight",
            "liquidations-daily/BTC/daily.parquet",
            _not_parquet,
            "File out of specification",
            id="liquidation-daily-preflight",
        ),
    ],
)
def test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it(
    tmp_path, monkeypatch, name, relpath, spoil, cause
):
    root = _b2_overlay_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_each_b2_overlay_reads_its_signal_off_its_own_columns(tmp_path, name):
    root = _b2_overlay_dataset(tmp_path)
    h4_ts, _ = subjects._capturing_union(ObservedReader(root), "ohlc-test", 240, None, None, False)
    expected = {}
    for asset in _B2_ASSETS:
        oi = pl.read_parquet(root / "derivatives-oi" / PERP_SYMBOLS[asset] / "oi.parquet")
        daily = pl.read_parquet(root / "liquidations-daily" / asset / "daily.parquet")
        if name == "b2-oi-derisk":
            expected[asset] = oi_zscore_grid_feature(oi["ts"].to_list(), oi["sum_open_interest"].to_list(), h4_ts)
        elif name == "b2-ratio-derisk":
            ratios = {column: oi[column].to_list() for column in _B2_OVERLAY_RATIOS}
            expected[asset] = ratio_max_signal(ratio_zscore_grid_features(oi["ts"].to_list(), ratios, h4_ts))
        else:
            expected[asset] = daily_zscore_grid_feature(daily["ts"].to_list(), daily["long_usd"].to_list(), h4_ts)

    signal = _overlay_signal(name)(ObservedReader(root), h4_ts)

    assert signal == expected
    assert sum(v is not None and v > 2.5 for v in signal["BTC"]) > 0


_B2_REENTRY_SPEC = "docs/specs/00139-b2-reentries-design.md"
# Spec 00139's two trials: each signal's key, threshold, comparison, hold and count, typed from the spec, never read off a
# subject.
_B2_REENTRIES = {
    "b2-liq-reentry": ("binperp_liq_long_z30d", 2.5, operator.gt, 1, 5),
    "b2-funding-reentry": ("binperp_funding_z30d", -2.0, operator.lt, 6, 6),
}


def _reentry_signal(name: str):
    return {"b2-liq-reentry": subjects._b2_liq_signal, "b2-funding-reentry": subjects._b2_funding_signal}[name]


def _b2_reentry_dataset(
    tmp_path: Path, *, start: datetime = _B2_START, flat: bool = False, from_bar: int = _B2_OVERLAY_FROM_BAR
) -> Path:
    """`_b2_overlay_dataset`'s sets and a `derivatives-funding` set whose 8h prints open 47 days before `_B2_START`; every perp
    but one dips far below its usual rate inside the second fall, each from its own print, so each re-entry takes flat stamps
    on several assets and none on `_B2_NEVER_SPIKES`."""
    root = _b2_overlay_dataset(tmp_path, start=start, flat=flat, from_bar=from_bar)
    stamps = [_B2_FUNDING_FROM + timedelta(hours=8 * j) for j in range(_B2_PRINTS)]
    second_fall = _B2_START + timedelta(hours=4 * _B2_FALLS[1][0])
    for i, asset in enumerate(_B2_ASSETS):
        rates = [0.0001 * (1 + 0.5 * math.sin(j + i)) for j in range(_B2_PRINTS)]
        if asset != _B2_NEVER_SPIKES:
            first = stamps.index(second_fall + timedelta(hours=8 * i))
            rates[first : first + _B2_SPIKE_PRINTS] = [-0.003] * _B2_SPIKE_PRINTS
        frame = pl.DataFrame(
            {"ts": stamps, "funding_rate": rates, "interval_hours": [8] * _B2_PRINTS},
            schema={"ts": pl.Datetime("us", "UTC"), "funding_rate": pl.Float64, "interval_hours": pl.Int64},
        )
        write_parquet(frame, root / "derivatives-funding" / PERP_SYMBOLS[asset] / "funding.parquet")
    return root


def _reentry_inputs(name: str, root: Path):
    _, threshold, fire, hold, _ = _B2_REENTRIES[name]
    return subjects._b2_reentry_inputs(
        name, _reentry_signal(name), fire, hold, threshold, ObservedReader(root), "ohlc-test", None, False
    )


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_each_b2_reentry_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    signal_key, _, _, _, count = _B2_REENTRIES[name]
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    builder = f"_build_{name.replace('-', '_')}"
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B2_REENTRY_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is getattr(subjects, builder) and trial.metric_keys == _overlay_metric_keys(signal_key)
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_reentry_verdict, _B2_OVERLAY_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", count)
    assert (preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == ((240,), _B2_ASSETS, _B2_REENTRY_SPEC, (42,))
    assert preflight.build is getattr(subjects, f"{builder}_preflight")
    assert preflight.metric_keys == _overlay_preflight_keys(signal_key)
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


@pytest.mark.parametrize("name", sorted({*_B2_REENTRIES, *(f"{name}-preflight" for name in _B2_REENTRIES)}))
def test_each_b2_reentry_subject_builds_on_the_specs_signal_comparison_hold_threshold_and_count(monkeypatch, name):
    trial = name.removesuffix("-preflight")
    signal_key, threshold, fire, hold, count = _B2_REENTRIES[trial]
    compute = subjects._b2_reentry_metrics if name == trial else subjects._b2_reentry_preflight_metrics
    builds = []
    monkeypatch.setattr(subjects, "_b2_reentry_build", lambda *arguments: builds.append(arguments) or {})
    reader, window = object(), ("2024-01-01", "2024-06-30")

    subjects.SUBJECTS[name].build(reader, "ohlc-test", window, as_of="2026-10-03", accept_holes=True)

    instrument = (name, signal_key, _reentry_signal(trial), fire, hold, threshold, compute, count)
    assert builds == [(*instrument, reader, "ohlc-test", window, "2026-10-03", True)]


# Adopting on every key the rule reads, its drawdown a twentieth above arm A's; the full-window head-to-head and the
# block-102 cell set against the verdict, so a rule reading either in place of the primary read or the headline cell moves
# the first row.
_B2_REENTRY_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2013": 0, "2023": 4},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "spa_p_decisive_b102_s42": 0.9,
    "max_drawdown_reduction_pct": -5.0,
}


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-outperforms-significantly-a-twentieth-more-drawdown"),
        pytest.param({"head_to_head_spa_p_primary": 0.0499}, "adopt", id="row-1-p-at-0.0499"),
        pytest.param({"max_drawdown_reduction_pct": -20.0}, "adopt", id="row-1-drawdown-at-exactly-1.2-times"),
        pytest.param({"max_drawdown_reduction_pct": 5.0}, "adopt", id="row-1-drawdown-below-arm-as"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="row-2-p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="row-2-outperforms-insignificantly"),
        pytest.param({"max_drawdown_reduction_pct": -20.001}, "park", id="row-2-significant-but-drawdown-past-1.2-times"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": 1e-12, "head_to_head_spa_p_primary": 0.9, "max_drawdown_reduction_pct": -80.0},
            "park",
            id="row-2-a-hair-above-arm-a",
        ),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="row-3-mean-at-exactly-0"),
        pytest.param({"head_to_head_mean_outperf_primary": -0.001}, "reject", id="row-3-underperforms-from-the-start"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001, "head_to_head_spa_p_full": 0.01},
            "reject",
            id="row-3-outperforms-over-the-full-window-alone",
        ),
        pytest.param({"passes": 0}, "reject", id="row-4-arm-b-fails-its-bar"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_OVERLAY_NEVER_ENGAGED, None, id="the-re-entry-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_OVERLAY_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
    ],
)
def test_the_b2_reentry_rule_maps_the_matrix_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b2_reentry_verdict({**_B2_REENTRY_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_a_b2_reentrys_inputs_add_the_full_long_size_where_arm_a_is_flat_and_its_signal_fires(tmp_path, monkeypatch, name):
    _, threshold, fire, hold, _ = _B2_REENTRIES[name]
    sizes = _recording(monkeypatch, "full_long_sizes", lambda arguments, result: result)
    reentries = _recording(monkeypatch, "reentry_positions", lambda arguments, result: result)
    root = _b2_reentry_dataset(tmp_path)

    inputs = _reentry_inputs(name, root)

    overlay = subjects._b2_overlay_inputs(name, _reentry_signal(name), 2.5, ObservedReader(root), "ohlc-test", None, False)
    assert (inputs.h4_ts, inputs.close, inputs.arm_a, inputs.signal) == (
        overlay.h4_ts,
        overlay.close,
        overlay.arm_a,
        overlay.signal,
    )
    fed = _ffill_btc(inputs.h4_prices)
    levels = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=180,
                basket_lookback=180,
                periods_per_year=2190,
            ),
        )["vol_target_positions"]
        for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    ]
    ((size_arguments, full_long),) = sizes
    assert size_arguments == {"weights": _inverse_vol_weights(fed, lookback=180), "levels": levels, "assets": _B2_ASSETS}
    ((reentry_arguments, arm_b),) = reentries
    fires = {a: [z is not None and fire(z, threshold) for z in inputs.signal[a]] for a in _B2_ASSETS}
    assert reentry_arguments == {"asset_positions": inputs.arm_a, "full_long": full_long, "fires": fires, "hold": hold}
    assert (inputs.full_long, inputs.arm_b, inputs.threshold) == (full_long, arm_b, threshold)
    reentered = {a: sum(p == 0 and q > 0 for p, q in zip(inputs.arm_a[a], arm_b[a])) for a in _B2_ASSETS}
    assert reentered[_B2_NEVER_SPIKES] == 0 < sum(reentered.values())


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_a_b2_reentrys_metrics_are_the_overlays_with_its_positions_its_start_and_its_engagement(tmp_path, monkeypatch, name):
    signal_key, threshold, _, _, count = _B2_REENTRIES[name]
    inputs = _reentry_inputs(name, _b2_reentry_dataset(tmp_path))
    start = subjects._b2_reentry_start(inputs)
    k21 = next(k for k, t in enumerate(inputs.close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    defined = next(k for k in range(len(inputs.close)) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS))
    assert start == max(defined, k21) and 0 < start < len(inputs.close) - 2
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b2_reentry_metrics(inputs, signal_key=signal_key, n_trials=count)

    assert set(metrics) == _overlay_metric_keys(signal_key) and {arguments["n_trials"] for arguments, _ in bars} == {count}
    # The overlays' metrics over the same arm A and signal, their arm B, start and engagement the re-entry's:
    # `_b2_overlay_metrics`' own test proves that body.
    overlay = subjects._B2OverlayInputs(inputs.h4_ts, inputs.h4_prices, inputs.close, inputs.arm_a, inputs.signal, {}, threshold)
    monkeypatch.setattr(subjects, "scale_positions", lambda positions, scales: inputs.arm_b)
    monkeypatch.setattr(subjects, "_b2_overlay_start", lambda _: start)
    monkeypatch.setattr(subjects, "_b2_overlay_engagement", lambda _, key: subjects._b2_reentry_engagement(inputs, key))
    assert subjects._b2_overlay_metrics(overlay, signal_key=signal_key, n_trials=count) == metrics
    assert metrics["primary_returns"] == len(inputs.close) - start and metrics["threshold"] == threshold


def test_where_no_signal_fires_a_b2_reentrys_arm_b_is_arm_a_bit_for_bit(tmp_path, monkeypatch):
    inputs = _reentry_inputs("b2-liq-reentry", _b2_reentry_dataset(tmp_path))
    n = len(inputs.close)
    calm = {a: [0.0] * n for a in _B2_ASSETS}
    quiet = {a: [False] * n for a in _B2_ASSETS}
    inputs = inputs._replace(signal=calm, arm_b=reentry_positions(inputs.arm_a, inputs.full_long, quiet, hold=1))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b2_reentry_metrics(inputs, signal_key="binperp_liq_long_z30d", n_trials=5)

    assert [arguments["book_net_of_cost"] == arguments["benchmark_net_of_cost"] for arguments, _ in head_to_heads] == [True] * 2
    assert (
        metrics["stamps_positions_differ"],
        metrics["turnover_b"],
        metrics["max_drawdown"],
        metrics["max_drawdown_reduction_pct"],
    ) == (0, metrics["turnover_a"], metrics["arm_a_max_drawdown"], 0.0)
    k21 = next(k for k, t in enumerate(inputs.close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert metrics["primary_returns"] == n - k21 and set(metrics["engaged_per_year"].values()) == {0}


@pytest.mark.parametrize(("left", "refused"), [(0, True), (1, True), (2, False)])
def test_a_b2_reentry_refuses_fewer_than_2_returns_from_its_start(tmp_path, monkeypatch, left, refused):
    inputs = _reentry_inputs("b2-liq-reentry", _b2_reentry_dataset(tmp_path))
    n = len(inputs.close)
    inputs = inputs._replace(signal={a: [None] * (n - left) + [0.0] * left for a in _B2_ASSETS})
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    cause = (
        f"{left} of its return indices lie from the read's start, every asset's binperp_liq_long_z30d held and 2021 begun, and "
        "the head-to-head from it needs 2"
    )

    try:
        subjects._b2_reentry_metrics(inputs, signal_key="binperp_liq_long_z30d", n_trials=5)
        raised = ""
    except ValidationError as exc:
        raised = str(exc)

    assert (raised == cause) is refused


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_a_b2_reentrys_preflight_reads_arm_a_and_the_engagement_and_never_a_return_of_arm_b(tmp_path, monkeypatch, name):
    signal_key, threshold, fire, hold, count = _B2_REENTRIES[name]
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    reads = _recording(monkeypatch, "_b2_reentry_inputs", lambda arguments, result: result)
    nets = _recording(monkeypatch, "net_of_cost", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS[f"{name}-preflight"].build(ObservedReader(_b2_reentry_dataset(tmp_path)), "ohlc-test", None)

    ((read, inputs),) = reads
    assert (read["subject"], read["read_signal"], read["fire"], read["hold"], read["threshold"]) == (
        f"{name}-preflight",
        _reentry_signal(name),
        fire,
        hold,
        threshold,
    )
    assert [arguments["asset_positions"] is inputs.arm_a for arguments, _ in nets] == [True, True]
    returns = {a: _asset_returns(_ffill_btc(inputs.h4_prices)[a]) for a in _B2_ASSETS}
    net_a, net_a_x15 = (net_of_cost(inputs.arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.close)
    start = subjects._b2_reentry_start(inputs)
    ((arguments, bar),) = bars
    assert arguments == {
        "book_net_returns": net_a,
        "benchmark_net_returns": bench,
        "n_trials": count,
        "var_trials": 0.0,
        "mean_block": 30,
        "seed": 42,
        "cost_stressed_returns": net_a_x15,
        "regime_slices": calendar_year_slices(net_a, inputs.h4_ts),
        "benchmark_slices": calendar_year_slices(bench, inputs.h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    reentered = {a: sum(p == 0 and q > 0 for p, q in zip(inputs.arm_a[a], inputs.arm_b[a])) for a in _B2_ASSETS}
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        "engaged_per_asset": reentered,
        "engaged_per_year": reentry_counts_per_year(inputs.arm_a, inputs.arm_b, inputs.close),
        f"{signal_key}_coverage": {
            a: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(inputs.close, inputs.signal[a]).items()}
            for a in _B2_ASSETS
        },
        "primary_returns": n - start,
        "threshold": threshold,
    }
    assert set(metrics) == _overlay_preflight_keys(signal_key) and 0 < start < n - 2
    assert sum(reentered.values()) == sum(metrics["engaged_per_year"].values()) > 0
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0


@pytest.mark.parametrize("name", sorted({*_B2_REENTRIES, *(f"{name}-preflight" for name in _B2_REENTRIES)}))
def test_a_b2_reentry_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, [*args, *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"{name} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen "
        "--dataset"
    ) in result.output


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_a_b2_reentry_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    count = _B2_REENTRIES[name][4]
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_reentry_inputs", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-183", "--family", "B2", "--n-trials", str(count + 1)]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials {count + 1} is not {count}, the count {name} declares and deflates at: pass --n-trials {count}"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.parametrize(
    ("from_bar", "cause"),
    [
        pytest.param(
            1_458,
            "0 of its return indices lie from the read's start, every asset's binperp_liq_long_z30d held and 2021 begun, and the "
            "head-to-head from it needs 2",
            id="no-index-from-the-start",
        ),
        pytest.param(
            1_452,
            "arm A never draws down from the read's start, so max_drawdown_reduction_pct divides by zero",
            id="arm-a-never-draws-down-from-the-start",
        ),
    ],
)
def test_a_b2_reentry_trial_refuses_a_start_it_cannot_evaluate_before_any_bar(tmp_path, monkeypatch, from_bar, cause):
    _anchor(monkeypatch, _b2_reentry_dataset(tmp_path, from_bar=from_bar))
    kill_bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    args = ["research", "eval", "--subject", "b2-liq-reentry", "--dataset", "ohlc-test", *_as_trial("b2-liq-reentry", tmp_path)]

    result = runner.invoke(app, args)

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"b2-liq-reentry over the full history: {cause}" in result.output
    assert kill_bars == []


@pytest.mark.parametrize(
    ("name", "relpath", "spoil", "cause"),
    [
        pytest.param(
            "b2-liq-reentry",
            "liquidations-daily/SOL/daily.parquet",
            lambda path: pl.read_parquet(path).drop("long_usd").write_parquet(path),
            '"long_usd" not found',
            id="liquidation-daily",
        ),
        pytest.param(
            "b2-funding-reentry-preflight",
            f"derivatives-funding/{_B2_SPOILT}/funding.parquet",
            _not_parquet,
            "File out of specification",
            id="funding-preflight",
        ),
    ],
)
def test_a_b2_reentry_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it(
    tmp_path, monkeypatch, name, relpath, spoil, cause
):
    root = _b2_reentry_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_each_b2_reentry_reads_its_signal_off_its_own_columns(tmp_path, name):
    root = _b2_reentry_dataset(tmp_path)
    h4_ts, _ = subjects._capturing_union(ObservedReader(root), "ohlc-test", 240, None, None, False)
    expected = {}
    for asset in _B2_ASSETS:
        if name == "b2-liq-reentry":
            daily = pl.read_parquet(root / "liquidations-daily" / asset / "daily.parquet")
            expected[asset] = daily_zscore_grid_feature(daily["ts"].to_list(), daily["long_usd"].to_list(), h4_ts)
        else:
            prints = pl.read_parquet(root / "derivatives-funding" / PERP_SYMBOLS[asset] / "funding.parquet")
            columns = (prints[c].to_list() for c in ("ts", "funding_rate", "interval_hours"))
            expected[asset] = funding_grid_feature(*columns, h4_ts, config=B2Config())

    signal = _reentry_signal(name)(ObservedReader(root), h4_ts)

    assert signal == expected
    _, threshold, fire, _, _ = _B2_REENTRIES[name]
    assert sum(v is not None and fire(v, threshold) for v in signal["BTC"]) > 0


def _ruled_signal(held: list[float | None], flat: list[float]) -> tuple[dict, dict]:
    """BTC's signal at its long stamps `held` and at its flat ones `flat`, every other asset's flat and unread."""
    n = len(held) + len(flat)
    signal = {a: [None] * n for a in _B2_ASSETS} | {"BTC": [*held, *flat]}
    arm_a = {a: [0.0] * n for a in _B2_ASSETS} | {"BTC": [0.3] * len(held) + [0.0] * len(flat)}
    return signal, arm_a


@pytest.mark.retired
@pytest.mark.parametrize(
    ("held", "flat", "share", "threshold"),
    [
        # Shares of 6 % above 2.0 and 2 % above 2.5: the first is nearer 4.93 %.
        pytest.param([2.2] * 40 + [2.6] * 20 + [0.0] * 940, [], None, 2.0, id="2.0-nearer"),
        # 15 % and 6 %: the second is nearer.
        pytest.param([2.2] * 90 + [2.6] * 60 + [0.0] * 850, [], None, 2.5, id="2.5-nearer"),
        # 50 % and 0 % against a share of 25 %: a tie, read as 2.5.
        pytest.param([2.2, 2.3, 0.0, 0.0], [], 0.25, 2.5, id="a-tie"),
        # Flat stamps at 9.0 count for neither share: read over the long stamps alone, 6 % and 2 % again.
        pytest.param([2.2] * 40 + [2.6] * 20 + [0.0] * 940, [9.0] * 500, None, 2.0, id="flat-stamps-left-out"),
        # Long stamps the signal does not reach count for neither share: 8 % and 5 % over the 1,000 it reads, 4 % and 2.5 %
        # over all 2,000.
        pytest.param([2.2] * 30 + [2.6] * 50 + [0.0] * 920 + [None] * 1000, [], None, 2.5, id="unread-long-stamps-left-out"),
        pytest.param([], [9.0] * 10, None, 2.5, id="no-long-stamp-holds-the-signal"),
    ],
)
def test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share(monkeypatch, held, flat, share, threshold):
    if share is not None:
        monkeypatch.setattr(subjects, "_B2_TRIAL_2_ENGAGED_SHARE", share)
    assert subjects._B2_TRIAL_2_ENGAGED_SHARE == (share if share is not None else 3_486 / 70_682)
    assert subjects._b2_engagement_threshold(*_ruled_signal(held, flat)) == threshold


_B2_TAPE_SPEC_KEYS = frozenset(
    {
        "fwd_logret_1h",
        "fwd_logret_4h",
        "fwd_logret_24h",
        "fwd_rv_1h",
        "fwd_rv_4h",
        "fwd_rv_24h",
        "events_per_asset",
        "zscore_hours_per_asset",
        "threshold",
        "zscore_hours",
        "mean_block",
        "n_resamples",
    }
)
_B2_TAPE_START = datetime(2026, 7, 14, tzinfo=UTC)
_B2_TAPE_HOURS = 900


def _b2_tape_dataset(tmp_path: Path, *, hours: int = _B2_TAPE_HOURS, gap: range = range(0)) -> Path:
    """Hourly and 15-minute series, and a one-bucket-an-hour tape over every hour but `gap`'s, spiking past the warm-up."""
    root = tmp_path / "data"
    start = int(_B2_TAPE_START.timestamp())
    stamps = [_B2_TAPE_START + timedelta(hours=h) for h in range(hours)]
    write_parquet(
        pl.DataFrame({"ts": [t for h, t in enumerate(stamps) if h not in gap]}, schema={"ts": pl.Datetime("us", "UTC")}),
        root / "liquidations-frozen" / "covered-hours.parquet",
    )
    for i, asset in enumerate(_B2_ASSETS):
        quarter = [100.0 * (1 + 0.02 * math.sin(q / 9 + i)) * (1.0001**q) for q in range(4 * hours)]
        rows15 = [[start + 900 * q, f"{c}", f"{c * 1.01}", f"{c * 0.99}", f"{c}", f"{c}", "10", 3] for q, c in enumerate(quarter)]
        rows60 = [
            [start + 3600 * h, f"{c}", f"{c * 1.01}", f"{c * 0.99}", f"{c}", f"{c}", "40", 12] for h, c in enumerate(quarter[3::4])
        ]
        write_parquet(to_frame(rows15), root / "ohlc-test" / f"{asset}/EUR/15.parquet")
        write_parquet(to_frame(rows60), root / "ohlc-test" / f"{asset}/EUR/60.parquet")
        hot = set() if asset == _B2_NEVER_SPIKES else {760 + 13 * i + 7 * j for j in range(10)}
        buckets = {
            "ts": [t + timedelta(minutes=1) for t in stamps],
            "symbol": [f"{asset}USDT_PERP.A"] * hours,
            "long_usd": [5e4 if h in hot else 600.0 + 400 * math.sin(h / 5 + i) for h in range(hours)],
            "short_usd": [500.0 + 300 * math.cos(h / 7 + i) for h in range(hours)],
            "event_id": [f"{asset}USDT_PERP.A-{start + 3600 * h + 60}" for h in range(hours)],
        }
        schema = {
            "ts": pl.Datetime("us", "UTC"),
            "symbol": pl.String,
            "long_usd": pl.Float64,
            "short_usd": pl.Float64,
            "event_id": pl.String,
        }
        write_parquet(pl.DataFrame(buckets, schema=schema), root / "liquidations-frozen" / asset / "buckets.parquet")
    return root


@pytest.mark.retired
def test_the_tape_reading_declares_the_hourly_and_quarter_hour_grids_its_keys_and_no_rule():
    reading = subjects.SUBJECTS["b2-liq-tape-reading"]
    assert (reading.intervals, reading.assets, reading.spec, reading.seeds) == ((60, 15), _B2_ASSETS, _B2_OVERLAY_SPEC, (42,))
    assert reading.build is subjects._build_b2_liq_tape_reading and reading.metric_keys == _B2_TAPE_SPEC_KEYS
    assert (reading.verdict, reading.no_verdict, reading.incumbent, reading.family, reading.n_trials) == (None,) * 5


@pytest.mark.retired
def test_the_tape_forwards_read_from_the_close_its_hour_ends_on_and_merge_a_missing_quarter():
    hours = [_B2_TAPE_START + timedelta(hours=h) for h in range(30)]
    quarters = [_B2_TAPE_START + timedelta(minutes=15 * q) for q in range(120)]
    fine = [100.0 + q + (q % 3) for q in range(120)]
    # The quarter opening at 2h 30min is missing; the one opening at 10h 45min, hour 10's anchor, too.
    fine[10] = fine[43] = None
    hourly = [fine[4 * h + 3] for h in range(30)]
    out = subjects._b2_tape_forwards(hours, dict.fromkeys(_B2_ASSETS, hourly), quarters, dict.fromkeys(_B2_ASSETS, fine))

    assert set(out) == {f"fwd_{kind}_{h}h" for kind in ("logret", "rv") for h in (1, 4, 24)}
    btc = {series: values["BTC"] for series, values in out.items()}
    # Hour 0 ends at 1h, the close of the quarter opening at 45 min: its 1-hour return runs to the close at 2h.
    assert btc["fwd_logret_1h"][0] == pytest.approx(math.log(fine[7] / fine[3]))
    assert btc["fwd_logret_4h"][0] == pytest.approx(math.log(fine[19] / fine[3]))
    assert btc["fwd_rv_1h"][0] == pytest.approx(math.sqrt(sum(math.log(fine[q + 1] / fine[q]) ** 2 for q in range(3, 7))))
    # Hour 1's path runs 2h .. 3h: the missing 2h 30min quarter merges its neighbours' returns into one.
    path = [fine[7], fine[8], fine[9], fine[11]]
    assert btc["fwd_rv_1h"][1] == pytest.approx(math.sqrt(sum(math.log(b / a) ** 2 for a, b in zip(path, path[1:]))))
    # Hour 10's anchor quarter is missing, and the last hours lack the closes their horizons end on.
    assert (btc["fwd_rv_1h"][10], btc["fwd_logret_1h"][29], btc["fwd_logret_24h"][6], btc["fwd_rv_24h"][6]) == (
        None,
        None,
        None,
        None,
    )
    assert btc["fwd_logret_24h"][5] == pytest.approx(math.log(fine[119] / fine[23]))


@pytest.mark.retired
def test_the_tape_reading_flags_an_hour_whose_z_score_exceeds_2_and_hands_its_forwards_to_the_contrast(tmp_path, monkeypatch):
    # Hours 850-859 are not asserted: each asset's 720-hour z-score is read at hours 719-849 alone, where the gap read as
    # covered would add hours 850-899.
    root = _b2_tape_dataset(tmp_path, gap=range(850, 860))
    contrasts = _recording(monkeypatch, "event_contrast", lambda arguments, result: result)

    metrics = subjects.SUBJECTS["b2-liq-tape-reading"].build(ObservedReader(root), "ohlc-test", None)

    reader = ObservedReader(root)
    hours, hourly = subjects._capturing_union(reader, "ohlc-test", 60, None, None, False)
    quarters, quarterly = subjects._capturing_union(reader, "ohlc-test", 15, None, None, False)
    covered = pl.read_parquet(root / "liquidations-frozen" / "covered-hours.parquet")["ts"].to_list()
    flags = {}
    for asset in _B2_ASSETS:
        rows = pl.read_parquet(root / "liquidations-frozen" / asset / "buckets.parquet")
        totals = liquidation_hourly_totals(
            rows["ts"].to_list(), rows["long_usd"].to_list(), rows["short_usd"].to_list(), hours, covered
        )
        flags[asset] = [None if z is None else z > 2.0 for z in funding_zscore(totals, window=720)]
    ((arguments, result),) = contrasts
    assert arguments == {
        "flags": flags,
        "forwards": subjects._b2_tape_forwards(hours, hourly, quarters, quarterly),
        "mean_block": 24,
        "n_resamples": 2000,
        "seed": 42,
    }
    assert set(metrics) == _B2_TAPE_SPEC_KEYS and {key: metrics[key] for key in result} == result
    assert metrics["events_per_asset"] == {a: sum(flag is True for flag in flags[a]) for a in _B2_ASSETS}
    assert metrics["events_per_asset"][_B2_NEVER_SPIKES] == 0 < metrics["events_per_asset"]["BTC"]
    assert metrics["zscore_hours_per_asset"] == dict.fromkeys(_B2_ASSETS, 849 - 718)
    assert (metrics["threshold"], metrics["zscore_hours"], metrics["mean_block"], metrics["n_resamples"]) == (2.0, 720, 24, 2000)


@pytest.mark.retired
def test_the_tape_reading_refuses_a_bucket_file_it_cannot_read_naming_it(tmp_path, monkeypatch):
    root = _b2_tape_dataset(tmp_path)
    _not_parquet(root / "liquidations-frozen" / "SOL" / "buckets.parquet")
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-liq-tape-reading", "--dataset", "ohlc-test"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "liquidations-frozen/SOL/buckets.parquet: " in result.output and "File out of specification" in result.output


@pytest.mark.retired
def test_the_tape_reading_refuses_a_dataset_its_tapes_asserted_hours_miss(tmp_path):
    root = _b2_tape_dataset(tmp_path)
    covered = root / "liquidations-frozen" / "covered-hours.parquet"
    moved = [t + timedelta(days=400) for t in pl.read_parquet(covered)["ts"].to_list()]
    write_parquet(pl.DataFrame({"ts": moved}, schema={"ts": pl.Datetime("us", "UTC")}), covered)

    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS["b2-liq-tape-reading"].build(ObservedReader(root), "ohlc-test", None)

    assert str(refused.value) == (
        "b2-liq-tape-reading over the full history: no coin holds an hour with both the 720-hour z-score and the 24-hour "
        f"forward log return; the tape asserts the hours {moved[0]} .. {moved[-1]}"
    )


@pytest.mark.retired
def test_the_tape_reading_refuses_z_scored_hours_none_of_which_holds_a_24_hour_forward(tmp_path):
    # Hours 0-156 are not asserted: the first z-scored hour is 876, one past 875, the last whose 24-hour forward bar the
    # 900-hour union holds.
    root = _b2_tape_dataset(tmp_path, gap=range(157))

    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS["b2-liq-tape-reading"].build(ObservedReader(root), "ohlc-test", None)

    first, last = _B2_TAPE_START + timedelta(hours=157), _B2_TAPE_START + timedelta(hours=_B2_TAPE_HOURS - 1)
    assert str(refused.value) == (
        "b2-liq-tape-reading over the full history: no coin holds an hour with both the 720-hour z-score and the 24-hour "
        f"forward log return; the tape asserts the hours {first} .. {last}"
    )


@pytest.mark.retired
def test_the_tape_reading_refuses_744_hourly_bars_and_reads_745_with_no_event(tmp_path):
    reading = subjects.SUBJECTS["b2-liq-tape-reading"]
    with pytest.raises(subjects.SubjectError) as refused:
        reading.build(ObservedReader(_b2_tape_dataset(tmp_path / "744", hours=744)), "ohlc-test", None)
    assert str(refused.value) == (
        "b2-liq-tape-reading over the full history: it holds 744 hourly bars, and the 720-hour z-score and the 24-hour "
        "forward read need 745"
    )

    # Hours 719 and 720 hold a z-score and a 24-hour forward; the fixture's spikes start at hour 760.
    metrics = reading.build(ObservedReader(_b2_tape_dataset(tmp_path / "745", hours=745)), "ohlc-test", None)
    assert metrics["zscore_hours_per_asset"] == dict.fromkeys(_B2_ASSETS, 745 - 719)
    assert metrics["events_per_asset"] == dict.fromkeys(_B2_ASSETS, 0)


# Records 45 and 46's metric keys (docs/specs/00130 D3), pinned against the committed records below.
_B1_REGISTERED_KEYS = frozenset(
    {
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown",
        "arm_a_spot_drag_pct_yr",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
        "cost_stress_pass",
        "decisive_start",
        "dsr_corrected",
        "dsr_pass",
        "gated_per_year",
        "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016",
        "head_to_head_spa_p_full",
        "max_drawdown",
        "n_resamples",
        "passes",
        "per_period_sharpe_4h",
        "scaled_per_year",
        "spa_p_decisive_b102",
        "spa_p_decisive_b30",
        "spa_p_full",
        "spa_p_seed1234",
        "spa_p_seed7",
        "spa_pass",
        "spot_drag_pct_yr",
        "stamps_held",
        "stamps_positions_differ",
        "stamps_scaled",
        "turnover_a",
        "turnover_b",
        "turnover_reduction_pct",
        "worst_slice_relative_pass",
    }
)


@pytest.mark.retired
def test_the_b1_subjects_literals_are_the_ones_records_45_and_46_ran_with():
    assert subjects._B1_COST_PER_SIDE == 0.006
    assert subjects._B1_A2_ARMS == (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    assert subjects._B1_LOOKBACK == 180
    assert subjects._B1_DECISIVE_START == 1380
    assert subjects._B1_N_RESAMPLES == 2000
    assert subjects._B1_FROM_2016 == datetime(2016, 1, 1, tzinfo=UTC)
    assert subjects._B1_GRID == ((30, 7), (30, 1234), (102, 42))


@pytest.mark.parametrize(
    ("name", "trial_id", "build"),
    [("b1-conditioning", 45, "_build_b1_conditioning"), ("b1-window-only", 46, "_build_b1_window_only")],
)
def test_each_b1_subject_declares_its_records_keys_and_is_evaluate_only(name, trial_id, build):
    subject = subjects.SUBJECTS[name]
    assert subject.metric_keys == _B1_REGISTERED_KEYS == frozenset(_trials()[trial_id]["metrics"])
    assert subject.build is getattr(subjects, build)
    assert (subject.intervals, subject.assets, subject.seeds) == ((240,), _B2_ASSETS, (42, 7, 1234))
    assert subject.spec == "docs/specs/00045-b1-seasonality-conditioning-design.md"
    assert subject.verdict is None and subject.no_verdict is None and subject.incumbent is None


@pytest.mark.parametrize(
    ("name", "datasets"),
    [
        pytest.param("b1-conditioning", {"ohlc-test", "ohlc-15m"}, id="b1-conditioning"),
        pytest.param("b1-window-only", {"ohlc-test"}, id="b1-window-only"),
    ],
)
def test_only_b1_conditioning_reads_the_15m_set(tmp_path, name, datasets):
    reader = ObservedReader(_b1_dataset(tmp_path))
    subjects.SUBJECTS[name].build(reader, "ohlc-test", None)
    assert set(reader.block()) == datasets


@pytest.mark.retired
@pytest.mark.parametrize(
    ("spoil", "cause"),
    [
        pytest.param(Path.unlink, "No such file or directory", id="missing"),
        pytest.param(lambda path: path.write_bytes(b"not a parquet file"), "File out of specification", id="not-parquet"),
    ],
)
def test_b1_conditioning_names_a_15m_file_it_cannot_read(tmp_path, monkeypatch, spoil, cause):
    root = _b1_dataset(tmp_path)
    spoil(root / "ohlc-15m" / "SOL/EUR/15.parquet")
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b1-conditioning", "--dataset", "ohlc-test"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "ohlc-15m/SOL/EUR/15.parquet" in result.output and cause in result.output


@pytest.mark.retired
def test_b1_conditioning_refuses_a_15m_set_short_of_the_last_decision_boundary_in_its_own_terms(tmp_path, monkeypatch):
    root = _b1_dataset(tmp_path)
    for path in (root / "ohlc-15m").rglob("15.parquet"):
        # Eight hours off each file: the last close falls four hours short of the last decision boundary.
        pl.read_parquet(path).head(-32).write_parquet(path)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b1-conditioning", "--dataset", "ohlc-test"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "b1-conditioning over the full history: 15m substrate ends at" in result.output
    assert "pass a --window that ends by the frozen ohlc-15m set's last bar" in result.output
    assert "refresh the substrate" not in result.output


_B1_UNREADABLE_HISTORIES = [
    pytest.param(datetime(2020, 1, 1, tzinfo=UTC), 1_300, "it holds 1299 return indices", id="short-of-the-decisive-window"),
    pytest.param(
        datetime(2015, 1, 1, tzinfo=UTC),
        _B1_BARS,
        "0 of its return indices open at or after 2016-01-01T00:00Z",
        id="before-2016",
    ),
    pytest.param(
        datetime(2026, 1, 1, tzinfo=UTC), _B1_BARS, "none of its return indices closes in a calendar year", id="all-in-2026"
    ),
]


@pytest.mark.parametrize(("start", "bars", "message"), _B1_UNREADABLE_HISTORIES)
@pytest.mark.parametrize("name", ["b1-conditioning", "b1-window-only"])
def test_a_b1_history_the_bar_cannot_read_is_refused_before_the_arms(tmp_path, monkeypatch, name, start, bars, message):
    _anchor(monkeypatch, _b1_dataset(tmp_path, start=start, bars=bars, m15=False))
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"{name} over the full history: " in result.output and message in result.output
    assert calls == []


# BTC's two 4h buckets with no hourly bar: the first inside the stamps arm A weights, the second past the from-2016 cut.
_B1_HOURLY_RV_BTC_GAPS = (400, 1_500)


def _b1_hourly_rv_dataset(tmp_path: Path, *, start: datetime = _B1_START, bars: int = _B1_BARS) -> Path:
    """The ten hourly series and the 4h series aggregated from their present rows, so each 4h close is its bucket's last
    present hourly close. Each asset's closes bounce by a size of their own, which lifts its hourly realized variance against
    its 4h variance by its own amount; every other asset misses single hours and BTC two whole 4h buckets, which the union
    keeps and `_ffill_btc` fills."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        hourly = []
        for k, row in enumerate(_rows(bars * 4, phase=i * 0.7, start=int(start.timestamp()), step=3600)):
            if (k // 4 in _B1_HOURLY_RV_BTC_GAPS) if asset == "BTC" else (k % (89 + 2 * i) == 5):
                continue
            hourly.append([*row[:4], f"{float(row[4]) * (1 + 0.002 * (i + 1) * (-1) ** k)}", *row[5:]])
        write_parquet(to_frame(hourly), root / "ohlc-test" / f"{asset}/EUR/60.parquet")
        write_parquet(to_frame(_h4_bars(hourly)), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    return root


def _h4_bars(hourly: list[list]) -> list[list]:
    """Each 4h bucket's bar from its present hourly rows: the first open, their high and low, the last close."""
    buckets: dict[int, list[list]] = {}
    for row in hourly:
        buckets.setdefault(row[0] // 14_400 * 14_400, []).append(row)
    return [
        [
            ts,
            rows[0][1],
            f"{max(float(r[2]) for r in rows)}",
            f"{min(float(r[3]) for r in rows)}",
            rows[-1][4],
            rows[-1][5],
            f"{sum(float(r[6]) for r in rows)}",
            sum(r[7] for r in rows),
        ]
        for ts, rows in buckets.items()
    ]


# BTC's two missing 4h bars: the first among BTC's first 180 bars, where every entry is accepted, the second past them.
_B1_VOLUME_BTC_GAPS = (100, 1_500)


def _b1_volume_dataset(tmp_path: Path, *, start: datetime = _B1_START, bars: int = _B1_BARS) -> Path:
    """Each bar's volume moves on a phase of its own asset's, so the gate rejects entries past the warm-up."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        rows = [
            [*row[:6], f"{10.0 + 9.0 * math.sin(2.7 * k + i)}", row[7]]
            for k, row in enumerate(_rows(bars, phase=i * 0.7, start=int(start.timestamp()), step=4 * 3600))
            if not (asset == "BTC" and k in _B1_VOLUME_BTC_GAPS)
        ]
        write_parquet(to_frame(rows), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    return root


def _b1_volume_args(name: str, tmp_path: Path, *, dataset: str = "ohlc-test") -> list[str]:
    # A ruled subject's command-path cases register into tmp_path: spec 00133 D7 admits no plain eval of a subject with a rule.
    args = ["research", "eval", "--subject", name, "--dataset", dataset]
    if subjects.SUBJECTS[name].verdict is None:
        return args
    flags = ["--register", "--registry", str(tmp_path / "registry.jsonl"), "--ledger", str(tmp_path / "ledger.jsonl")]
    return [*args, *flags, "--iteration", "iter-001", "--family", "B1", "--n-trials", "4"]


def _b1_hourly_exit_dataset(tmp_path: Path, *, start: datetime = _B1_START, bars: int = _B1_BARS) -> Path:
    """Hourly closes on a slow cycle, so the 4h series makes new channel lows as well as highs, each 4h bucket's second
    hourly close dipped by a size of its asset's own, so an hourly close breaches a channel its 4h close then holds or
    breaks. BTC misses the two 4h buckets of `_B1_HOURLY_RV_BTC_GAPS`, which `_ffill_btc` fills, and every other asset
    single hours."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        hourly = []
        for k in range(bars * 4):
            if (k // 4 in _B1_HOURLY_RV_BTC_GAPS) if asset == "BTC" else (k % (89 + 2 * i) == 5):
                continue
            close = 100.0 * (1 + 0.25 * math.sin(k / 400.0 + i)) * (1 + 0.03 * math.sin(k / 9.0 + 0.7 * i))
            close *= 1 - 0.004 * (i + 1) if k % 4 == 1 else 1.0
            ts = int(start.timestamp()) + k * 3600
            hourly.append([ts, f"{close}", f"{close * 1.01}", f"{close * 0.99}", f"{close}", f"{close}", "10", 3])
        write_parquet(to_frame(hourly), root / "ohlc-test" / f"{asset}/EUR/60.parquet")
        write_parquet(to_frame(_h4_bars(hourly)), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    return root


_RULED_FIXTURES = {
    "b1-hourly-channel-exits": _b1_hourly_exit_dataset,
    "b1-hourly-rv": _b1_hourly_rv_dataset,
    "b1-volume-confirmation": _b1_volume_dataset,
    "b2-funding-derisk": _b2_dataset,
    "b2-funding-derisk-full": _b2_dataset,
    "b2-funding-reentry": _b2_reentry_dataset,
    "b2-liq-derisk": _b2_overlay_dataset,
    "b2-liq-reentry": _b2_reentry_dataset,
    "b2-oi-derisk": _b2_overlay_dataset,
    "b2-ratio-derisk": _b2_overlay_dataset,
}
# Each ruled subject's count constant, which the tie raises so that a literal at a kill-bar site fails it.
_DECLARED_COUNT = {
    "b1-hourly-channel-exits": "_B1_EXIT_N_TRIALS",
    "b1-hourly-rv": "_B1_HOURLY_RV_N_TRIALS",
    "b1-volume-confirmation": "_B1_VOLUME_N_TRIALS",
    "b2-funding-derisk": "_B2_N_TRIALS",
    "b2-funding-derisk-full": "_B2_FULL_N_TRIALS",
    "b2-funding-reentry": "_B2_FUNDING_REENTRY_N_TRIALS",
    "b2-liq-derisk": "_B2_LIQ_N_TRIALS",
    "b2-liq-reentry": "_B2_LIQ_REENTRY_N_TRIALS",
    "b2-oi-derisk": "_B2_OI_N_TRIALS",
    "b2-ratio-derisk": "_B2_RATIO_N_TRIALS",
}


def test_the_ruled_subjects_declare_their_families_and_trial_counts():
    declared = {name: (s.family, s.n_trials) for name, s in subjects.SUBJECTS.items() if s.verdict is not None}
    assert declared == {
        "b1-hourly-channel-exits": ("B1", 5),
        "b1-hourly-rv": ("B1", 3),
        "b1-volume-confirmation": ("B1", 4),
        "b2-funding-derisk": ("B2", 1),
        "b2-funding-derisk-full": ("B2", 1),
        "b2-funding-reentry": ("B2", 6),
        "b2-liq-derisk": ("B2", 4),
        "b2-liq-reentry": ("B2", 5),
        "b2-oi-derisk": ("B2", 2),
        "b2-ratio-derisk": ("B2", 3),
    }
    assert set(_RULED_FIXTURES) == set(declared) == set(_DECLARED_COUNT)


@pytest.mark.parametrize("name", sorted(_RULED_FIXTURES))
def test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count(tmp_path, monkeypatch, name):
    assert getattr(subjects, _DECLARED_COUNT[name]) == subjects.SUBJECTS[name].n_trials
    raised = subjects.SUBJECTS[name].n_trials + 1
    monkeypatch.setattr(subjects, _DECLARED_COUNT[name], raised)
    monkeypatch.setitem(subjects.SUBJECTS, name, replace(subjects.SUBJECTS[name], n_trials=raised))
    counts = []

    def recorder(*args, n_trials, **kwargs):
        counts.append(n_trials)
        return _b1_hourly_rv_bar_sentinels("B", passes=True)

    monkeypatch.setattr(subjects, "a1_kill_bar", recorder)

    subjects.SUBJECTS[name].build(ObservedReader(_RULED_FIXTURES[name](tmp_path)), "ohlc-test", None)

    assert counts and set(counts) == {raised}


_B1_HOURLY_RV_SPEC = "docs/specs/00132-b1-hourly-rv-weights-design.md"
_B1_HOURLY_RV_NO_VERDICT = (
    "instrument finding: arm A fails the bar, or arm B's weights equal arm A's at every stamp; no verdict, the trial unspent"
)
# Spec 00132 D8's keys of the trial and of its pre-flight, pinned as literals for the reason `_COMBINED_METRIC_KEYS` is.
_B1_HOURLY_RV_METRIC_KEYS = frozenset(
    {
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "per_period_sharpe_4h",
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
        "var_trials",
        "dsr_corrected",
        "dsr_pass",
        "spa_pass",
        "spa_p_full",
        "cost_stress_pass",
        "worst_slice_relative_pass",
        "passes",
        "decisive_start",
        "n_resamples",
        "arm_a_var_trials",
        "arm_a_passes",
        "spa_p_decisive_b30_s42",
        "spa_p_decisive_b30_s7",
        "spa_p_decisive_b30_s1234",
        "spa_p_decisive_b102_s42",
        "spa_p_decisive_b102_s7",
        "spa_p_decisive_b102_s1234",
        "head_to_head_mean_outperf_full",
        "head_to_head_spa_p_full",
        "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016",
        "max_drawdown",
        "arm_a_max_drawdown",
        "spot_drag_pct_yr",
        "arm_a_spot_drag_pct_yr",
        "turnover_a",
        "turnover_b",
        "turnover_reduction_pct",
        "stamps_weights_differ",
        "stamps_positions_differ",
        "weight_tv_a",
        "weight_tv_b",
        "weight_tv_ratio",
        "mean_weight_per_year",
    }
)
_B1_HOURLY_RV_ANCHORS = frozenset(
    {
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown",
        "turnover_a",
        "arm_a_spot_drag_pct_yr",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    }
)
_B1_HOURLY_RV_PREFLIGHT_KEYS = frozenset(
    {
        *_B1_HOURLY_RV_ANCHORS,
        "arm_a_var_trials",
        "dsr",
        "dsr_pass",
        "spa_p_value",
        "spa_p_value_full",
        "spa_pass",
        "cost_stress_sharpe",
        "cost_stress_pass",
        "worst_slice_sharpe",
        "worst_slice_pass",
        "passes",
        "stamps_weights_differ",
    }
)


@pytest.mark.retired
def test_the_b1_hourly_rv_subjects_declare_both_grids_the_specs_keys_and_seeds_and_the_trial_alone_a_rule():
    trial, preflight = subjects.SUBJECTS["b1-hourly-rv"], subjects.SUBJECTS["b1-hourly-rv-preflight"]
    assert (len(_B1_HOURLY_RV_METRIC_KEYS), len(_B1_HOURLY_RV_PREFLIGHT_KEYS)) == (42, 19)

    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        "b1-hourly-rv",
        (240, 60),
        _B2_ASSETS,
        _B1_HOURLY_RV_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b1_hourly_rv
    assert trial.metric_keys == _B1_HOURLY_RV_METRIC_KEYS
    assert trial.verdict is subjects._b1_hourly_rv_verdict
    assert trial.no_verdict == _B1_HOURLY_RV_NO_VERDICT
    assert trial.incumbent is None

    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        "b1-hourly-rv-preflight",
        (240, 60),
        _B2_ASSETS,
        _B1_HOURLY_RV_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b1_hourly_rv_preflight
    assert preflight.metric_keys == _B1_HOURLY_RV_PREFLIGHT_KEYS
    assert preflight.verdict is None and preflight.no_verdict is None and preflight.incumbent is None


@pytest.mark.retired
def test_the_b1_hourly_rv_dispersion_reads_records_45_and_46s_registered_sharpes_over_three_trials():
    assert (
        subjects._B1_RECORDED_PER_PERIOD_SHARPES
        == (0.02374, 0.02959)
        == tuple(_trials()[n]["metrics"]["per_period_sharpe_4h"] for n in (45, 46))
    )


# Adopting on every key the rule reads; each row moves the keys it names.
_B1_HOURLY_RV_ADOPTING = {
    "arm_a_passes": 1,
    "stamps_weights_differ": 9,
    "passes": 1,
    "spa_p_decisive_b102_s42": 0.01,
    "head_to_head_mean_outperf_full": 0.001,
    "head_to_head_spa_p_full": 0.01,
    "turnover_a": 140.0,
    "turnover_b": 120.0,
}


@pytest.mark.retired
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-passes-outperforms-significantly-at-both-blocks-and-trades-less"),
        pytest.param({"spa_p_decisive_b102_s42": 0.2}, "park", id="row-2-the-block-102-spa-fails"),
        pytest.param({"head_to_head_spa_p_full": 0.2}, "park", id="row-3-outperforms-insignificantly-and-trades-less"),
        pytest.param({"head_to_head_mean_outperf_full": -0.001}, "reject", id="row-4-underperforms"),
        pytest.param({"turnover_b": 150.0}, "reject", id="row-4-trades-more"),
        pytest.param({"passes": 0}, "reject", id="row-5-arm-b-fails-its-bar"),
        pytest.param({"turnover_b": 140.0}, "reject", id="turnover-tied"),
        pytest.param({"head_to_head_mean_outperf_full": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param({"head_to_head_spa_p_full": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.0499}, "adopt", id="both-p-at-0.0499"),
        pytest.param(
            {"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.05}, "park", id="block-102-p-at-exactly-0.05"
        ),
        pytest.param(
            {"head_to_head_mean_outperf_full": -0.001, "head_to_head_mean_outperf_2016": 0.001},
            "reject",
            id="outperforms-from-2016-alone",
        ),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param({"stamps_weights_differ": 0}, None, id="the-weights-never-differ"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({"stamps_weights_differ": 0, "passes": 0}, None, id="the-weights-read-before-passes"),
    ],
)
def test_the_b1_hourly_rv_rule_maps_its_metrics_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b1_hourly_rv_verdict({**_B1_HOURLY_RV_ADOPTING, **change}) == verdict


_B1_HOURLY_RV_CELLS = ((30, 42), (30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))
# Records 45 and 46's three A2 arms, typed here rather than read off the subject.
_B1_HOURLY_RV_ARMS = tuple(
    A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
)


def _b1_hourly_rv_bar_sentinels(cell: str, *, passes) -> dict:
    """Per-call sentinels for the eight keys of a kill-bar result the subject reads, as `_kill_bar_sentinels` makes them:
    the floats distinct across keys and the two calls, the flags ints other than 0 and 1, `passes` apart from them."""
    i = ("B", "A").index(cell)
    floats = {"dsr": 0.11 + i / 100, "spa_p_value": 0.21 + i / 100, "spa_p_value_full": 0.31 + i / 100}
    return floats | {"passes": passes} | {flag: 10 * (i + 1) + j for j, flag in enumerate(_B2_FLAGS)}


@pytest.mark.retired
@pytest.mark.parametrize(
    ("arm_b_passes", "arm_a_passes"),
    [pytest.param(True, False, id="arm-a-fails-so-the-rule-stops"), pytest.param(False, 7, id="arm-b-fails-so-the-rule-rejects")],
)
def test_the_b1_hourly_rv_subject_registers_each_metric_from_its_own_call(tmp_path, monkeypatch, arm_b_passes, arm_a_passes):
    root = _b1_hourly_rv_dataset(tmp_path)
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, root, registry)
    h4_ts, h4_prices, hourly = subjects._b1_hourly_rv_reads(
        ObservedReader(root), "ohlc-test", None, None, False, subject="b1-hourly-rv"
    )
    n = len(h4_ts) - 1
    k16 = next(k for k in range(n) if h4_ts[k] >= datetime(2016, 1, 1, tzinfo=UTC))
    assert k16 == 1_284
    cost = 0.006
    fed = _ffill_btc(h4_prices)
    weights_a = _inverse_vol_weights(fed, lookback=180)
    weights_b = hourly_rv_inverse_vol_weights(fed, h4_ts, hourly, lookback=180)
    arms_a = [a2_book_returns(fed, config=config)["asset_positions"] for config in _B1_HOURLY_RV_ARMS]
    arms_b = [a2_positions_with_weights(fed, weights_b, config=config) for config in _B1_HOURLY_RV_ARMS]
    arm_a, arm_b = (
        {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(n)] for a in _B2_ASSETS} for arms in (arms_a, arms_b)
    )
    returns = {a: _asset_returns(fed[a]) for a in _B2_ASSETS}
    net_a, net_b = (net_of_cost(arm, returns, cost_per_side=cost) for arm in (arm_a, arm_b))
    net_a_x15, net_b_x15 = (net_of_cost(arm, returns, cost_per_side=1.5 * cost) for arm in (arm_a, arm_b))
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=cost)

    # The other filled-or-raw choices refuse here: `_validate_prices_by_asset` refuses a BTC None, and arm A's weights over
    # the raw prices weight other assets than `weights_b`, which `weights_differ_count` refuses.
    assert fed["BTC"] != h4_prices["BTC"]
    assert net_of_cost(arm_b, {a: _asset_returns(h4_prices[a]) for a in _B2_ASSETS}, cost_per_side=cost) != net_b
    assert benchmark_4h_net_of_cost(fed, cost_per_side=cost) != bench
    assert any(wb != wa for wa, wb in zip(weights_a, weights_b))
    assert net_b != net_a and net_b[k16:] != net_a[k16:]
    assert book_turnover(arm_b) != book_turnover(arm_a)
    assert weight_total_variation(weights_b) != weight_total_variation(weights_a)

    def kill_bar(arguments, result):
        book = arguments["book_net_returns"]
        cell = "A" if book == net_a else "B" if book == net_b else None
        if cell is None:
            return result
        return result | _b1_hourly_rv_bar_sentinels(cell, passes=arm_a_passes if cell == "A" else arm_b_passes)

    spa_sentinels = {cell: 0.51 + i / 100 for i, cell in enumerate(_B1_HOURLY_RV_CELLS)}

    def spa(arguments, result):
        p = spa_sentinels.get((arguments["mean_block"], arguments["seed"]))
        return result if p is None else result | {"p_value": p}

    def head_to_head(arguments, result):
        p = {n: 0.41, n - k16: 0.42}.get(len(arguments["book_net_of_cost"]))
        return result if p is None else result | {"spa_p_value": p}

    kill_calls = _recording(monkeypatch, "a1_kill_bar", kill_bar)
    spa_calls = _recording(monkeypatch, "reality_check_pvalue", spa)
    verdict_calls = _recording(monkeypatch, "net_of_cost_verdict", head_to_head)
    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "b1-hourly-rv", "--dataset", "ohlc-test", "--register", "--registry", str(registry)]
        + ["--ledger", str(ledger), "--iteration", "iter-177", "--family", "B1", "--n-trials", "3"]
        + ["--variant", "B1-hourly-rv-weights-a2eq-v1"],
    )

    assert result.exit_code == 0, result.output
    if arm_a_passes:
        (record,) = [json.loads(line) for line in registry.read_text().splitlines()]
        assert set(record["metrics"]) == _B1_HOURLY_RV_METRIC_KEYS
        assert set(record["datasets"]["ohlc-test"]["files"]) == {f"{a}/EUR/{i}.parquet" for a in _B2_ASSETS for i in (240, 60)}
        assert record["n_trials_in_family"] == 3
        assert record["verdict"] == "reject"
        assert not ledger.exists()
        stored = record["metrics"]
    else:
        assert f"no verdict — {_B1_HOURLY_RV_NO_VERDICT}: recorded reading 1; no trial spent" in result.output
        assert not registry.exists()
        (reading,) = _kept(ledger)
        assert reading["outcome"] == _B1_HOURLY_RV_NO_VERDICT
        assert reading["metrics"] == _block_and_metrics(result.output)["metrics"]
        stored = reading["metrics"]

    var_b = statistics.variance([0.02374, 0.02959, sharpe(net_b)])
    var_a = statistics.variance([0.02374, 0.02959, sharpe(net_a)])
    bar = {
        "benchmark_net_returns": bench,
        "n_trials": 3,
        "mean_block": 30,
        "seed": 42,
        "benchmark_slices": calendar_year_slices(bench, h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    assert len(kill_calls) == 2
    assert {"A" if arguments["book_net_returns"] == net_a else "B": arguments for arguments, _ in kill_calls} == {
        "B": bar
        | {
            "book_net_returns": net_b,
            "var_trials": var_b,
            "cost_stressed_returns": net_b_x15,
            "regime_slices": calendar_year_slices(net_b, h4_ts),
        },
        "A": bar
        | {
            "book_net_returns": net_a,
            "var_trials": var_a,
            "cost_stressed_returns": net_a_x15,
            "regime_slices": calendar_year_slices(net_a, h4_ts),
        },
    }
    decisive = [[net_b[k] - bench[k]] for k in range(1380, n)]
    assert sorted(
        (arguments for arguments, _ in spa_calls), key=lambda arguments: (arguments["mean_block"], arguments["seed"])
    ) == [
        {"perf_matrix": decisive, "mean_block": block, "n_resamples": 2000, "seed": seed}
        for block, seed in sorted(_B1_HOURLY_RV_CELLS[1:])
    ]
    head_to_head_call = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    assert [arguments for arguments, _ in verdict_calls] == [
        {"book_net_of_cost": net_b, "benchmark_net_of_cost": net_a} | head_to_head_call,
        {"book_net_of_cost": net_b[k16:], "benchmark_net_of_cost": net_a[k16:]} | head_to_head_call,
    ]
    full, from_2016 = (outcome for _, outcome in verdict_calls)
    assert full["mean_outperformance"] != from_2016["mean_outperformance"]

    bars = {"A" if arguments["book_net_returns"] == net_a else "B": outcome for arguments, outcome in kill_calls}
    grid = {(arguments["mean_block"], arguments["seed"]): outcome["p_value"] for arguments, outcome in spa_calls}
    turnover_a, turnover_b = book_turnover(arm_a), book_turnover(arm_b)
    tv_a, tv_b = weight_total_variation(weights_a), weight_total_variation(weights_b)
    expected = {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=2190),
        "ann_sharpe_noc_decisive": sharpe(net_b[1380:], periods_per_year=2190),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        "var_trials": var_b,
        "dsr_corrected": bars["B"]["dsr"],
        "dsr_pass": int(bars["B"]["dsr_pass"]),
        "spa_pass": int(bars["B"]["spa_pass"]),
        "spa_p_full": bars["B"]["spa_p_value_full"],
        "cost_stress_pass": int(bars["B"]["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bars["B"]["worst_slice_pass"]),
        "passes": int(bars["B"]["passes"]),
        "decisive_start": 1380,
        "n_resamples": 2000,
        "arm_a_var_trials": var_a,
        "arm_a_passes": int(bars["A"]["passes"]),
        "spa_p_decisive_b30_s42": bars["B"]["spa_p_value"],
        **{f"spa_p_decisive_b{block}_s{seed}": grid[(block, seed)] for block, seed in _B1_HOURLY_RV_CELLS[1:]},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "spot_drag_pct_yr": turnover_b / n * 0.006 * 2190,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_weights_differ": weights_differ_count(weights_a, weights_b),
        "stamps_positions_differ": sum(any(arm_b[a][k] != arm_a[a][k] for a in _B2_ASSETS) for k in range(n)),
        "weight_tv_a": tv_a,
        "weight_tv_b": tv_b,
        "weight_tv_ratio": tv_b / tv_a,
        "mean_weight_per_year": per_year_mean_weights(weights_a, weights_b, h4_ts, list(_B2_ASSETS)),
    }
    assert set(expected) == _B1_HOURLY_RV_METRIC_KEYS
    assert stored == expected


@pytest.mark.retired
def test_the_b1_hourly_rv_preflight_reads_arm_a_and_the_two_weight_paths_and_never_builds_arm_bs_book(tmp_path, monkeypatch):
    root = _b1_hourly_rv_dataset(tmp_path)
    trial = subjects.SUBJECTS["b1-hourly-rv"].build(ObservedReader(root), "ohlc-test", None)

    def arm_b_book(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's book")

    monkeypatch.setattr(subjects, "a2_positions_with_weights", arm_b_book)
    metrics = subjects.SUBJECTS["b1-hourly-rv-preflight"].build(ObservedReader(root), "ohlc-test", None)

    ints = _ARM_A_BAR_FLAGS | {"stamps_weights_differ"}
    assert set(metrics) == _B1_HOURLY_RV_PREFLIGHT_KEYS
    assert {key for key, value in metrics.items() if type(value) is int} == ints
    assert {key for key, value in metrics.items() if type(value) is float} == _B1_HOURLY_RV_PREFLIGHT_KEYS - ints
    assert metrics["stamps_weights_differ"] == trial["stamps_weights_differ"] > 0
    assert (metrics["passes"], metrics["arm_a_var_trials"]) == (trial["arm_a_passes"], trial["arm_a_var_trials"])
    assert {key: metrics[key] for key in _B1_HOURLY_RV_ANCHORS} == {key: trial[key] for key in _B1_HOURLY_RV_ANCHORS}


@pytest.mark.parametrize("name", ["b1-hourly-rv", "b1-hourly-rv-preflight"])
def test_a_b1_hourly_rv_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)

    result = runner.invoke(
        app,
        ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-03", *_as_trial(name, tmp_path)],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert f"{name} evaluates a frozen set's 4h and hourly series, never the rolling dataset as of a day: drop --as-of" in (
        result.output
    )


@pytest.mark.retired
@pytest.mark.parametrize(
    ("spoil", "cause"),
    [
        pytest.param(lambda path: path.write_bytes(b"not a parquet file"), "File out of specification", id="not-parquet"),
        pytest.param(
            lambda path: pl.read_parquet(path).drop("close").write_parquet(path), '"close" not found', id="no-close-column"
        ),
    ],
)
def test_b1_hourly_rv_names_an_hourly_file_it_cannot_read(tmp_path, monkeypatch, spoil, cause):
    root = _b1_hourly_rv_dataset(tmp_path)
    spoil(root / "ohlc-test" / "SOL/EUR/60.parquet")
    _anchor(monkeypatch, root)

    result = runner.invoke(
        app, ["research", "eval", "--subject", "b1-hourly-rv", "--dataset", "ohlc-test", *_as_trial("b1-hourly-rv", tmp_path)]
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert "ohlc-test/SOL/EUR/60.parquet" in result.output and cause in result.output


def _arm_a_flat(monkeypatch) -> None:
    def flat(arguments, result):
        return result | {"asset_positions": {a: [0.0] * len(p) for a, p in result["asset_positions"].items()}}

    _recording(monkeypatch, "a2_book_returns", flat)


def _arm_a_weights_frozen(monkeypatch) -> None:
    monkeypatch.setattr(subjects, "weight_total_variation", lambda *args, **kwargs: 0.0)


@pytest.mark.retired
@pytest.mark.parametrize(
    ("freeze", "named"),
    [
        pytest.param(_arm_a_flat, "turnover_a is 0.0", id="arm-a-never-trades"),
        pytest.param(_arm_a_weights_frozen, "weight_tv_a is 0.0", id="arm-a-weights-never-move"),
    ],
)
def test_b1_hourly_rv_refuses_a_build_whose_arm_a_never_trades_or_whose_weights_never_move(tmp_path, monkeypatch, freeze, named):
    _anchor(monkeypatch, _b1_hourly_rv_dataset(tmp_path))
    freeze(monkeypatch)

    result = runner.invoke(
        app, ["research", "eval", "--subject", "b1-hourly-rv", "--dataset", "ohlc-test", *_as_trial("b1-hourly-rv", tmp_path)]
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    assert "b1-hourly-rv over the full history: " in result.output and named in result.output


@pytest.mark.retired
@pytest.mark.parametrize(("start", "bars", "message"), _B1_UNREADABLE_HISTORIES)
def test_a_b1_hourly_rv_history_the_bar_cannot_read_is_refused_before_the_arms_and_the_hourly_reads(
    tmp_path, monkeypatch, start, bars, message
):
    _anchor(monkeypatch, _b1_hourly_rv_dataset(tmp_path, start=start, bars=bars))
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)
    read_series, read = ObservedReader.read_series, []

    def recording_read(self, dataset, relpath, window=None):
        read.append(relpath)
        return read_series(self, dataset, relpath, window)

    monkeypatch.setattr(ObservedReader, "read_series", recording_read)

    result = runner.invoke(
        app, ["research", "eval", "--subject", "b1-hourly-rv", "--dataset", "ohlc-test", *_as_trial("b1-hourly-rv", tmp_path)]
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "b1-hourly-rv over the full history: " in result.output and message in result.output
    assert calls == []
    assert sorted(read) == sorted(f"{a}/EUR/240.parquet" for a in _B2_ASSETS)


_B1_VOLUME_SPEC = "docs/specs/00134-b1-volume-confirmation-design.md"
_B1_VOLUME_NO_VERDICT = (
    "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every stamp; no verdict, the trial unspent"
)
_B1_VOLUME_ENGAGEMENT = frozenset(
    {
        "entry_events",
        "entry_events_rejected",
        "share_rejected",
        "entry_events_per_year",
        "stamps_directions_differ",
        "stamps_directions_differ_per_year",
    }
)
# Typed from the spec's key list, never read off the subject.
_B1_VOLUME_METRIC_KEYS = _B1_VOLUME_ENGAGEMENT | {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe_4h",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "var_trials",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_var_trials",
    "arm_a_passes",
    "spa_p_decisive_b30_s42",
    "spa_p_decisive_b30_s7",
    "spa_p_decisive_b30_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_2016",
    "head_to_head_spa_p_2016",
    "max_drawdown",
    "arm_a_max_drawdown",
    "spot_drag_pct_yr",
    "arm_a_spot_drag_pct_yr",
    "turnover_a",
    "turnover_b",
    "turnover_reduction_pct",
    "stamps_positions_differ",
}
_B1_VOLUME_PREFLIGHT_KEYS = _B1_VOLUME_ENGAGEMENT | _B1_HOURLY_RV_ANCHORS | _ARM_A_BAR_KEYS | {"arm_a_var_trials"}


@pytest.mark.retired
def test_the_b1_volume_subjects_declare_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count():
    trial, preflight = subjects.SUBJECTS["b1-volume-confirmation"], subjects.SUBJECTS["b1-volume-confirmation-preflight"]
    assert (len(_B1_VOLUME_METRIC_KEYS), len(_B1_VOLUME_PREFLIGHT_KEYS)) == (43, 24)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        "b1-volume-confirmation",
        (240,),
        _B2_ASSETS,
        _B1_VOLUME_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b1_volume_confirmation and trial.metric_keys == _B1_VOLUME_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (
        subjects._b1_volume_confirmation_verdict,
        _B1_VOLUME_NO_VERDICT,
        None,
    )
    assert (trial.family, trial.n_trials) == ("B1", 4)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        "b1-volume-confirmation-preflight",
        (240,),
        _B2_ASSETS,
        _B1_VOLUME_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b1_volume_confirmation_preflight
    assert preflight.metric_keys == _B1_VOLUME_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


@pytest.mark.retired
def test_the_b1_volume_dispersion_reads_records_45_46_and_48s_registered_sharpes():
    assert (
        subjects._B1_VOLUME_RECORDED_PER_PERIOD_SHARPES
        == (0.02374, 0.02959, 0.030191886721210086)
        == tuple(_trials()[n]["metrics"]["per_period_sharpe_4h"] for n in (45, 46, 48))
    )


# Adopting on every key the rule reads; each row moves the keys it names.
_B1_VOLUME_ADOPTING = {
    "arm_a_passes": 1,
    "stamps_directions_differ": 9,
    "passes": 1,
    "spa_p_decisive_b102_s42": 0.01,
    "head_to_head_mean_outperf_full": 0.001,
    "head_to_head_spa_p_full": 0.01,
    "turnover_a": 140.0,
    "turnover_b": 120.0,
}


@pytest.mark.retired
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-passes-outperforms-significantly-at-both-blocks-and-trades-less"),
        pytest.param({"spa_p_decisive_b102_s42": 0.2}, "park", id="row-2-the-block-102-spa-fails"),
        pytest.param({"head_to_head_spa_p_full": 0.2}, "park", id="row-3-outperforms-insignificantly-and-trades-less"),
        pytest.param({"head_to_head_mean_outperf_full": -0.001}, "reject", id="row-4-underperforms"),
        pytest.param({"turnover_b": 150.0}, "reject", id="row-4-trades-more"),
        pytest.param({"passes": 0}, "reject", id="row-5-arm-b-fails-its-bar"),
        pytest.param({"turnover_b": 140.0}, "reject", id="turnover-tied"),
        pytest.param({"head_to_head_mean_outperf_full": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param({"head_to_head_spa_p_full": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.0499}, "adopt", id="both-p-at-0.0499"),
        pytest.param(
            {"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.05}, "park", id="block-102-p-at-exactly-0.05"
        ),
        pytest.param(
            {"head_to_head_mean_outperf_full": -0.001, "head_to_head_mean_outperf_2016": 0.001},
            "reject",
            id="outperforms-from-2016-alone",
        ),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param({"stamps_directions_differ": 0}, None, id="the-directions-never-differ"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({"stamps_directions_differ": 0, "passes": 0}, None, id="the-directions-read-before-passes"),
    ],
)
def test_the_b1_volume_rule_maps_its_metrics_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b1_volume_confirmation_verdict({**_B1_VOLUME_ADOPTING, **change}) == verdict


@pytest.mark.retired
@pytest.mark.parametrize(
    ("arm_b_passes", "arm_a_passes"),
    [pytest.param(True, False, id="arm-a-fails-so-the-rule-stops"), pytest.param(False, 7, id="arm-b-fails-so-the-rule-rejects")],
)
def test_the_b1_volume_subject_registers_each_metric_from_its_own_call(tmp_path, monkeypatch, arm_b_passes, arm_a_passes):
    root = _b1_volume_dataset(tmp_path)
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, root, registry)
    h4_ts, h4_prices, volumes = subjects._b1_volume_reads(
        ObservedReader(root), "ohlc-test", None, None, False, subject="b1-volume-confirmation"
    )
    n = len(h4_ts) - 1
    k16 = next(k for k in range(n) if h4_ts[k] >= datetime(2016, 1, 1, tzinfo=UTC))
    fed = _ffill_btc(h4_prices)
    confirm = confirmations_by_asset(fed, h4_prices, h4_ts, volumes, lookback=180, min_cell_obs=100)
    weights_a = _inverse_vol_weights(fed, lookback=180)
    union_idx = list(range(len(h4_ts)))
    asset_ts = {a: [k for k, p in enumerate(fed[a]) if p is not None] for a in _B2_ASSETS}
    books = [a2_book_returns(fed, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_a = [_asset_directions_a2(fed, union_idx, asset_ts, config=config) for config in _B1_HOURLY_RV_ARMS]
    confirmed = [asset_directions_confirmed(fed, union_idx, asset_ts, confirm, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_b = [directions for directions, _ in confirmed]
    arms_b = [a2_positions_on_directions(weights_a, d, book["vol_target_positions"]) for d, book in zip(directions_b, books)]
    arm_a, arm_b = (
        {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(n)] for a in _B2_ASSETS}
        for arms in ([book["asset_positions"] for book in books], arms_b)
    )
    returns = {a: _asset_returns(fed[a]) for a in _B2_ASSETS}
    net_a, net_b = (net_of_cost(arm, returns, cost_per_side=0.006) for arm in (arm_a, arm_b))
    net_a_x15, net_b_x15 = (net_of_cost(arm, returns, cost_per_side=1.5 * 0.006) for arm in (arm_a, arm_b))
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)

    assert fed["BTC"] != h4_prices["BTC"]
    assert net_of_cost(arm_b, {a: _asset_returns(h4_prices[a]) for a in _B2_ASSETS}, cost_per_side=0.006) != net_b
    assert benchmark_4h_net_of_cost(fed, cost_per_side=0.006) != bench
    assert any(not accepted for a in _B2_ASSETS if a != "BTC" for accepted in confirm[a][180:])
    assert confirm["BTC"][100] and not confirm["BTC"][1500]
    assert directions_b != directions_a and net_b != net_a and net_b[k16:] != net_a[k16:]
    assert book_turnover(arm_b) != book_turnover(arm_a)
    assert all(
        b <= a for da, db in zip(directions_a, directions_b) for s in _B2_ASSETS for a, b in zip(da[s], db[s]) if a is not None
    )
    assert all(arm_b[a][k] <= arm_a[a][k] for a in _B2_ASSETS for k in range(n))

    def kill_bar(arguments, result):
        book = arguments["book_net_returns"]
        cell = "A" if book == net_a else "B" if book == net_b else None
        if cell is None:
            return result
        return result | _b1_hourly_rv_bar_sentinels(cell, passes=arm_a_passes if cell == "A" else arm_b_passes)

    spa_sentinels = {cell: 0.51 + i / 100 for i, cell in enumerate(_B1_HOURLY_RV_CELLS)}

    def spa(arguments, result):
        p = spa_sentinels.get((arguments["mean_block"], arguments["seed"]))
        return result if p is None else result | {"p_value": p}

    def head_to_head(arguments, result):
        p = {n: 0.41, n - k16: 0.42}.get(len(arguments["book_net_of_cost"]))
        return result if p is None else result | {"spa_p_value": p}

    kill_calls = _recording(monkeypatch, "a1_kill_bar", kill_bar)
    spa_calls = _recording(monkeypatch, "reality_check_pvalue", spa)
    verdict_calls = _recording(monkeypatch, "net_of_cost_verdict", head_to_head)
    confirm_calls = _recording(monkeypatch, "confirmations_by_asset", lambda arguments, result: result)
    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "b1-volume-confirmation", "--dataset", "ohlc-test", "--register", "--registry"]
        + [str(registry), "--ledger", str(ledger), "--iteration", "iter-178", "--family", "B1", "--n-trials", "4"]
        + ["--variant", "B1-volume-confirm-a2eq-v1"],
    )

    assert result.exit_code == 0, result.output
    if arm_a_passes:
        (record,) = [json.loads(line) for line in registry.read_text().splitlines()]
        assert set(record["metrics"]) == _B1_VOLUME_METRIC_KEYS
        assert set(record["datasets"]["ohlc-test"]["files"]) == {f"{a}/EUR/240.parquet" for a in _B2_ASSETS}
        assert record["n_trials_in_family"] == 4
        assert record["verdict"] == "reject"
        assert not ledger.exists()
        stored = record["metrics"]
    else:
        assert f"no verdict — {_B1_VOLUME_NO_VERDICT}: recorded reading 1; no trial spent" in result.output
        assert not registry.exists()
        (reading,) = _kept(ledger)
        assert reading["outcome"] == _B1_VOLUME_NO_VERDICT
        assert reading["metrics"] == _block_and_metrics(result.output)["metrics"]
        stored = reading["metrics"]

    var_b = statistics.variance([0.02374, 0.02959, 0.030191886721210086, sharpe(net_b)])
    var_a = statistics.variance([0.02374, 0.02959, 0.030191886721210086, sharpe(net_a)])
    bar = {
        "benchmark_net_returns": bench,
        "n_trials": 4,
        "mean_block": 30,
        "seed": 42,
        "benchmark_slices": calendar_year_slices(bench, h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    assert len(kill_calls) == 2
    assert {"A" if arguments["book_net_returns"] == net_a else "B": arguments for arguments, _ in kill_calls} == {
        "B": bar
        | {
            "book_net_returns": net_b,
            "var_trials": var_b,
            "cost_stressed_returns": net_b_x15,
            "regime_slices": calendar_year_slices(net_b, h4_ts),
        },
        "A": bar
        | {
            "book_net_returns": net_a,
            "var_trials": var_a,
            "cost_stressed_returns": net_a_x15,
            "regime_slices": calendar_year_slices(net_a, h4_ts),
        },
    }
    assert [(arguments["lookback"], arguments["min_cell_obs"]) for arguments, _ in confirm_calls] == [(180, 100)]
    decisive = [[net_b[k] - bench[k]] for k in range(1380, n)]
    assert sorted(
        (arguments for arguments, _ in spa_calls), key=lambda arguments: (arguments["mean_block"], arguments["seed"])
    ) == [
        {"perf_matrix": decisive, "mean_block": block, "n_resamples": 2000, "seed": seed}
        for block, seed in sorted(_B1_HOURLY_RV_CELLS[1:])
    ]
    head_to_head_call = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    assert [arguments for arguments, _ in verdict_calls] == [
        {"book_net_of_cost": net_b, "benchmark_net_of_cost": net_a} | head_to_head_call,
        {"book_net_of_cost": net_b[k16:], "benchmark_net_of_cost": net_a[k16:]} | head_to_head_call,
    ]
    full, from_2016 = (outcome for _, outcome in verdict_calls)
    assert full["mean_outperformance"] != from_2016["mean_outperformance"]

    bars = {"A" if arguments["book_net_returns"] == net_a else "B": outcome for arguments, outcome in kill_calls}
    grid = {(arguments["mean_block"], arguments["seed"]): outcome["p_value"] for arguments, outcome in spa_calls}
    turnover_a, turnover_b = book_turnover(arm_a), book_turnover(arm_b)
    expected = {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=2190),
        "ann_sharpe_noc_decisive": sharpe(net_b[1380:], periods_per_year=2190),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        "var_trials": var_b,
        "dsr_corrected": bars["B"]["dsr"],
        "dsr_pass": int(bars["B"]["dsr_pass"]),
        "spa_pass": int(bars["B"]["spa_pass"]),
        "spa_p_full": bars["B"]["spa_p_value_full"],
        "cost_stress_pass": int(bars["B"]["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bars["B"]["worst_slice_pass"]),
        "passes": int(bars["B"]["passes"]),
        "decisive_start": 1380,
        "n_resamples": 2000,
        "arm_a_var_trials": var_a,
        "arm_a_passes": int(bars["A"]["passes"]),
        "spa_p_decisive_b30_s42": bars["B"]["spa_p_value"],
        **{f"spa_p_decisive_b{block}_s{seed}": grid[(block, seed)] for block, seed in _B1_HOURLY_RV_CELLS[1:]},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "spot_drag_pct_yr": turnover_b / n * 0.006 * 2190,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_positions_differ": sum(any(arm_b[a][k] != arm_a[a][k] for a in _B2_ASSETS) for k in range(n)),
    }
    own_stamps = {a: [h4_ts[k] for k in asset_ts[a]] for a in _B2_ASSETS}
    per_year = {str(i + 1): entry_events_per_year(events, own_stamps) for i, (_, events) in enumerate(confirmed)}
    counts = [
        c
        for arm in per_year.values()
        for by_asset in arm.values()
        for by_lookback in by_asset.values()
        for c in by_lookback.values()
    ]
    events, rejected = sum(c[0] for c in counts), sum(c[1] for c in counts)
    differ = directions_differ_per_year(directions_a, directions_b, h4_ts)
    expected |= {
        "entry_events_per_year": per_year,
        "entry_events": events,
        "entry_events_rejected": rejected,
        "share_rejected": rejected / events,
        "stamps_directions_differ": sum(differ.values()),
        "stamps_directions_differ_per_year": differ,
    }
    assert set(expected) == _B1_VOLUME_METRIC_KEYS
    assert stored == expected


@pytest.mark.retired
def test_the_b1_volume_preflight_reads_arm_a_and_the_entry_events_and_never_builds_arm_bs_positions(tmp_path, monkeypatch):
    root = _b1_volume_dataset(tmp_path)
    trial = subjects.SUBJECTS["b1-volume-confirmation"].build(ObservedReader(root), "ohlc-test", None)

    def arm_b_positions(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions")

    monkeypatch.setattr(subjects, "a2_positions_on_directions", arm_b_positions)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    metrics = subjects.SUBJECTS["b1-volume-confirmation-preflight"].build(ObservedReader(root), "ohlc-test", None)

    assert [arguments["n_trials"] for arguments, _ in bars] == [4]
    ints = _ARM_A_BAR_FLAGS | {"entry_events", "entry_events_rejected", "stamps_directions_differ"}
    dicts = {"entry_events_per_year", "stamps_directions_differ_per_year"}
    assert set(metrics) == _B1_VOLUME_PREFLIGHT_KEYS
    assert {key for key, value in metrics.items() if type(value) is int} == ints
    assert {key for key, value in metrics.items() if type(value) is dict} == dicts
    assert {key for key, value in metrics.items() if type(value) is float} == _B1_VOLUME_PREFLIGHT_KEYS - ints - dicts
    assert metrics["stamps_directions_differ"] > 0 and 0 < metrics["entry_events_rejected"] < metrics["entry_events"]
    assert {key: metrics[key] for key in _B1_VOLUME_ENGAGEMENT} == {key: trial[key] for key in _B1_VOLUME_ENGAGEMENT}
    assert (metrics["passes"], metrics["arm_a_var_trials"]) == (trial["arm_a_passes"], trial["arm_a_var_trials"])
    assert {key: metrics[key] for key in _B1_HOURLY_RV_ANCHORS} == {key: trial[key] for key in _B1_HOURLY_RV_ANCHORS}


@pytest.mark.parametrize("name", ["b1-volume-confirmation", "b1-volume-confirmation-preflight"])
def test_a_b1_volume_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)

    result = runner.invoke(app, [*_b1_volume_args(name, tmp_path, dataset="ohlc-rolling"), "--as-of", "2026-10-03"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} evaluates a frozen set's 4h series and their volumes, never the rolling dataset as of a day: drop --as-of" in (
        result.output
    )


@pytest.mark.retired
def test_b1_volume_names_a_240_file_without_a_volume_column(tmp_path, monkeypatch):
    root = _b1_volume_dataset(tmp_path)
    path = root / "ohlc-test" / "SOL/EUR/240.parquet"
    pl.read_parquet(path).drop("volume").write_parquet(path)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "ohlc-test/SOL/EUR/240.parquet" in result.output and '"volume" not found' in result.output


def _a_volume_set(path: Path, value: float | None) -> datetime:
    frame = pl.read_parquet(path)
    volumes, k = frame["volume"].to_list(), frame.height // 2
    volumes[k] = value
    frame.with_columns(volume=pl.Series(volumes, dtype=frame.schema["volume"])).write_parquet(path)
    return frame["ts"][k]


@pytest.mark.retired
@pytest.mark.parametrize(
    ("value", "named"),
    [
        pytest.param(0.0, "volume must be a finite number above 0, got 0.0 at ", id="zero-volume"),
        pytest.param(None, "no volume where the close is present at ", id="null-volume"),
    ],
)
def test_b1_volume_refuses_a_volume_it_cannot_gate_naming_the_asset_and_stamp(tmp_path, monkeypatch, value, named):
    root = _b1_volume_dataset(tmp_path)
    stamp = _a_volume_set(root / "ohlc-test" / "ETH/EUR/240.parquet", value)
    _anchor(monkeypatch, root)
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"b1-volume-confirmation over the full history: ETH: {named}{stamp.isoformat()}" in result.output
    assert calls == []


@pytest.mark.retired
def test_b1_volume_refuses_a_build_whose_arm_a_never_trades(tmp_path, monkeypatch):
    _anchor(monkeypatch, _b1_volume_dataset(tmp_path))
    _arm_a_flat(monkeypatch)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "b1-volume-confirmation over the full history: turnover_a is 0.0" in result.output


@pytest.mark.parametrize("name", ["b1-volume-confirmation", "b1-volume-confirmation-preflight"])
def test_a_b1_volume_build_without_an_entry_event_is_refused(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _b1_volume_dataset(tmp_path))
    real = subjects.asset_directions_confirmed

    def no_events(*args, **kwargs):
        directions, events = real(*args, **kwargs)
        return directions, {asset: dict.fromkeys(by_lookback, []) for asset, by_lookback in events.items()}

    monkeypatch.setattr(subjects, "asset_directions_confirmed", no_events)

    result = runner.invoke(app, _b1_volume_args(name, tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the full history: entry_events is 0, and share_rejected divides by it" in result.output


@pytest.mark.retired
@pytest.mark.parametrize(("start", "bars", "message"), _B1_UNREADABLE_HISTORIES)
def test_a_b1_volume_history_the_bar_cannot_read_is_refused_before_the_arms_and_the_volume_reads(
    tmp_path, monkeypatch, start, bars, message
):
    _anchor(monkeypatch, _b1_volume_dataset(tmp_path, start=start, bars=bars))
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)
    read_series, read = ObservedReader.read_series, []

    def recording_read(self, dataset, relpath, window=None):
        read.append(relpath)
        return read_series(self, dataset, relpath, window)

    monkeypatch.setattr(ObservedReader, "read_series", recording_read)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "b1-volume-confirmation over the full history: " in result.output and message in result.output
    assert calls == [] and sorted(read) == sorted(f"{a}/EUR/240.parquet" for a in _B2_ASSETS)


@pytest.mark.retired
def test_b1_volume_reads_its_volumes_under_the_unions_window(tmp_path, monkeypatch):
    root = _b1_volume_dataset(tmp_path)
    first, last = _B1_START + timedelta(hours=4 * 100), _B1_START + timedelta(hours=4 * (_B1_BARS - 1))
    window = (str(first), str(last))
    read_series, reads = ObservedReader.read_series, []

    def recording_read(self, dataset, relpath, window=None):
        reads.append((relpath, window))
        return read_series(self, dataset, relpath, window)

    monkeypatch.setattr(ObservedReader, "read_series", recording_read)

    h4_ts, h4_prices, volumes = subjects._b1_volume_reads(
        ObservedReader(root), "ohlc-test", window, None, False, subject="b1-volume-confirmation"
    )

    assert sorted(reads) == sorted((f"{a}/EUR/240.parquet", window) for a in _B2_ASSETS for _ in range(2))
    assert (h4_ts[0], h4_ts[-1]) == (first, last)
    assert all([v is not None for v in volumes[a]] == [p is not None for p in h4_prices[a]] for a in _B2_ASSETS)


_B1_EXIT_SPEC = "docs/specs/00135-b1-hourly-channel-exits-design.md"
_B1_EXIT_NO_VERDICT = (
    "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every hourly close; no verdict, the "
    "trial unspent"
)
_B1_EXIT_ENGAGEMENT = frozenset(
    {
        "exit_events",
        "exit_events_early",
        "exit_events_false",
        "share_false",
        "exit_events_per_year",
        "hourly_closes_directions_differ",
        "hourly_closes_directions_differ_per_year",
    }
)
# Typed from the spec's key list, never read off the subject.
_B1_EXIT_METRIC_KEYS = _B1_EXIT_ENGAGEMENT | {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe_4h",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "var_trials",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_var_trials",
    "arm_a_passes",
    "spa_p_decisive_b30_s42",
    "spa_p_decisive_b30_s7",
    "spa_p_decisive_b30_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_2016",
    "head_to_head_spa_p_2016",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_reduction_pct",
    "spot_drag_pct_yr",
    "arm_a_spot_drag_pct_yr",
    "turnover_a",
    "turnover_b",
    "turnover_b_intra",
    "turnover_reduction_pct",
    "stamps_positions_differ",
}
_B1_EXIT_PREFLIGHT_KEYS = _B1_EXIT_ENGAGEMENT | _B1_HOURLY_RV_ANCHORS | _ARM_A_BAR_KEYS | {"arm_a_var_trials"}


@pytest.mark.retired
def test_the_b1_hourly_exit_subjects_declare_both_grids_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count():
    trial, preflight = subjects.SUBJECTS["b1-hourly-channel-exits"], subjects.SUBJECTS["b1-hourly-channel-exits-preflight"]
    assert (len(_B1_EXIT_METRIC_KEYS), len(_B1_EXIT_PREFLIGHT_KEYS)) == (46, 25)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        "b1-hourly-channel-exits",
        (240, 60),
        _B2_ASSETS,
        _B1_EXIT_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b1_hourly_exit and trial.metric_keys == _B1_EXIT_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b1_hourly_exit_verdict, _B1_EXIT_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B1", 5)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        "b1-hourly-channel-exits-preflight",
        (240, 60),
        _B2_ASSETS,
        _B1_EXIT_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b1_hourly_exit_preflight
    assert preflight.metric_keys == _B1_EXIT_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


@pytest.mark.retired
def test_the_b1_hourly_exit_dispersion_reads_records_45_46_48_and_49s_registered_sharpes_and_deflates_at_five_trials():
    assert (
        subjects._B1_EXIT_RECORDED_PER_PERIOD_SHARPES
        == (0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177)
        == tuple(_trials()[n]["metrics"]["per_period_sharpe_4h"] for n in (45, 46, 48, 49))
    )
    assert expected_max_sharpe(subjects._B1_EXIT_N_TRIALS, 1.0) == 1.192594001014789


# Adopting on every key the rule reads, while trading more than arm A, which it does not read; each row moves the keys it names.
_B1_EXIT_ADOPTING = {
    "arm_a_passes": 1,
    "hourly_closes_directions_differ": 9,
    "passes": 1,
    "spa_p_decisive_b102_s42": 0.01,
    "head_to_head_mean_outperf_full": 0.001,
    "head_to_head_spa_p_full": 0.01,
    "max_drawdown_reduction_pct": 5.0,
    "turnover_a": 140.0,
    "turnover_b": 150.0,
}


@pytest.mark.retired
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-passes-outperforms-significantly-at-both-blocks-and-draws-down-less"),
        pytest.param({"spa_p_decisive_b102_s42": 0.2}, "park", id="row-2-the-block-102-spa-fails"),
        pytest.param({"head_to_head_spa_p_full": 0.2}, "park", id="row-3-outperforms-insignificantly-and-draws-down-less"),
        pytest.param({"head_to_head_mean_outperf_full": -0.001}, "reject", id="row-4-underperforms"),
        pytest.param({"max_drawdown_reduction_pct": -5.0}, "reject", id="row-4-draws-down-more"),
        pytest.param({"passes": 0}, "reject", id="row-5-arm-b-fails-its-bar"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="reduction-at-exactly-1e-6"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6}, "adopt", id="reduction-past-1e-6"),
        pytest.param({"head_to_head_mean_outperf_full": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param({"head_to_head_spa_p_full": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.0499}, "adopt", id="both-p-at-0.0499"),
        pytest.param(
            {"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.05}, "park", id="block-102-p-at-exactly-0.05"
        ),
        pytest.param(
            {"head_to_head_mean_outperf_full": -0.001, "head_to_head_mean_outperf_2016": 0.001},
            "reject",
            id="outperforms-from-2016-alone",
        ),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param({"hourly_closes_directions_differ": 0}, None, id="the-directions-never-differ"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({"hourly_closes_directions_differ": 0, "passes": 0}, None, id="the-directions-read-before-passes"),
    ],
)
def test_the_b1_hourly_exit_rule_maps_its_metrics_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b1_hourly_exit_verdict({**_B1_EXIT_ADOPTING, **change}) == verdict


@pytest.mark.retired
@pytest.mark.parametrize(
    ("arm_b_passes", "arm_a_passes"),
    [pytest.param(True, False, id="arm-a-fails-so-the-rule-stops"), pytest.param(False, 7, id="arm-b-fails-so-the-rule-rejects")],
)
def test_the_b1_hourly_exit_subject_registers_each_metric_from_its_own_call(tmp_path, monkeypatch, arm_b_passes, arm_a_passes):
    root = _b1_hourly_exit_dataset(tmp_path)
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, root, registry)
    h4_ts, h4_prices, hourly = subjects._b1_hourly_rv_reads(
        ObservedReader(root), "ohlc-test", None, None, False, subject="b1-hourly-channel-exits"
    )
    n = len(h4_ts) - 1
    k16 = next(k for k in range(n) if h4_ts[k] >= datetime(2016, 1, 1, tzinfo=UTC))
    fed = _ffill_btc(h4_prices)
    interior = interior_closes_by_asset(fed, h4_prices, h4_ts, hourly)
    weights_a = _inverse_vol_weights(fed, lookback=180)
    union_idx = list(range(len(h4_ts)))
    asset_ts = {a: [k for k, p in enumerate(fed[a]) if p is not None] for a in _B2_ASSETS}
    books = [a2_book_returns(fed, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_a = [_asset_directions_a2(fed, union_idx, asset_ts, config=config) for config in _B1_HOURLY_RV_ARMS]
    exits = [asset_directions_hourly_exit(fed, union_idx, asset_ts, interior, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_b = [directions for directions, _ in exits]
    arms_b = [a2_slot_positions(weights_a, d, book["vol_target_positions"]) for d, book in zip(directions_b, books)]
    arm_a = {a: [statistics.mean(book["asset_positions"][a][k] for book in books) for k in range(n)] for a in _B2_ASSETS}
    arm_b = {a: [tuple(statistics.mean(arm[a][k][i] for arm in arms_b) for i in range(4)) for k in range(n)] for a in _B2_ASSETS}
    returns, paths = {a: _asset_returns(fed[a]) for a in _B2_ASSETS}, price_paths(fed, interior)
    net_a, net_a_x15 = (net_of_cost(arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    net_b, net_b_x15 = (net_of_cost_hourly(arm_b, paths, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)

    assert fed["BTC"] != h4_prices["BTC"]
    assert net_b != net_a and net_b[k16:] != net_a[k16:]
    pairs = [(a, b) for da, db in zip(directions_a, directions_b) for s in _B2_ASSETS for a, b in zip(da[s], db[s])]
    assert all((a is None) == (b is None) for a, b in pairs)
    assert all(max(b) <= a for a, b in pairs if a is not None) and any(min(b) < a for a, b in pairs if a is not None)
    assert all(max(arm_b[a][k]) <= arm_a[a][k] for a in _B2_ASSETS for k in range(n))

    def kill_bar(arguments, result):
        book = arguments["book_net_returns"]
        cell = "A" if book == net_a else "B" if book == net_b else None
        if cell is None:
            return result
        return result | _b1_hourly_rv_bar_sentinels(cell, passes=arm_a_passes if cell == "A" else arm_b_passes)

    spa_sentinels = {cell: 0.51 + i / 100 for i, cell in enumerate(_B1_HOURLY_RV_CELLS)}

    def spa(arguments, result):
        p = spa_sentinels.get((arguments["mean_block"], arguments["seed"]))
        return result if p is None else result | {"p_value": p}

    def head_to_head(arguments, result):
        p = {n: 0.41, n - k16: 0.42}.get(len(arguments["book_net_of_cost"]))
        return result if p is None else result | {"spa_p_value": p}

    kill_calls = _recording(monkeypatch, "a1_kill_bar", kill_bar)
    spa_calls = _recording(monkeypatch, "reality_check_pvalue", spa)
    verdict_calls = _recording(monkeypatch, "net_of_cost_verdict", head_to_head)
    hourly_calls = _recording(monkeypatch, "net_of_cost_hourly", lambda arguments, result: result)
    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "b1-hourly-channel-exits", "--dataset", "ohlc-test", "--register", "--registry"]
        + [str(registry), "--ledger", str(ledger), "--iteration", "iter-179", "--family", "B1", "--n-trials", "5"]
        + ["--variant", "B1-hourly-exit-a2eq-v1"],
    )

    assert result.exit_code == 0, result.output
    if arm_a_passes:
        (record,) = [json.loads(line) for line in registry.read_text().splitlines()]
        assert set(record["metrics"]) == _B1_EXIT_METRIC_KEYS
        assert set(record["datasets"]["ohlc-test"]["files"]) == {f"{a}/EUR/{i}.parquet" for a in _B2_ASSETS for i in (240, 60)}
        assert record["n_trials_in_family"] == 5
        assert record["verdict"] == "reject"
        assert not ledger.exists()
        stored = record["metrics"]
    else:
        assert f"no verdict — {_B1_EXIT_NO_VERDICT}: recorded reading 1; no trial spent" in result.output
        assert not registry.exists()
        (reading,) = _kept(ledger)
        assert reading["outcome"] == _B1_EXIT_NO_VERDICT
        assert reading["metrics"] == _block_and_metrics(result.output)["metrics"]
        stored = reading["metrics"]

    var_b = statistics.variance([0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177, sharpe(net_b)])
    var_a = statistics.variance([0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177, sharpe(net_a)])
    bar = {
        "benchmark_net_returns": bench,
        "n_trials": 5,
        "mean_block": 30,
        "seed": 42,
        "benchmark_slices": calendar_year_slices(bench, h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    assert len(kill_calls) == 2
    assert {"A" if arguments["book_net_returns"] == net_a else "B": arguments for arguments, _ in kill_calls} == {
        "B": bar
        | {
            "book_net_returns": net_b,
            "var_trials": var_b,
            "cost_stressed_returns": net_b_x15,
            "regime_slices": calendar_year_slices(net_b, h4_ts),
        },
        "A": bar
        | {
            "book_net_returns": net_a,
            "var_trials": var_a,
            "cost_stressed_returns": net_a_x15,
            "regime_slices": calendar_year_slices(net_a, h4_ts),
        },
    }
    assert [arguments["cost_per_side"] for arguments, _ in hourly_calls] == [0.006, 1.5 * 0.006]
    decisive = [[net_b[k] - bench[k]] for k in range(1380, n)]
    assert sorted(
        (arguments for arguments, _ in spa_calls), key=lambda arguments: (arguments["mean_block"], arguments["seed"])
    ) == [
        {"perf_matrix": decisive, "mean_block": block, "n_resamples": 2000, "seed": seed}
        for block, seed in sorted(_B1_HOURLY_RV_CELLS[1:])
    ]
    head_to_head_call = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    assert [arguments for arguments, _ in verdict_calls] == [
        {"book_net_of_cost": net_b, "benchmark_net_of_cost": net_a} | head_to_head_call,
        {"book_net_of_cost": net_b[k16:], "benchmark_net_of_cost": net_a[k16:]} | head_to_head_call,
    ]
    full, from_2016 = (outcome for _, outcome in verdict_calls)
    assert full["mean_outperformance"] != from_2016["mean_outperformance"]

    bars = {"A" if arguments["book_net_returns"] == net_a else "B": outcome for arguments, outcome in kill_calls}
    grid = {(arguments["mean_block"], arguments["seed"]): outcome["p_value"] for arguments, outcome in spa_calls}
    turnover_a = book_turnover(arm_a)
    turnover_b = book_turnover({a: [p for slots in arm_b[a] for p in slots] for a in _B2_ASSETS})
    expected = {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=2190),
        "ann_sharpe_noc_decisive": sharpe(net_b[1380:], periods_per_year=2190),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        "var_trials": var_b,
        "dsr_corrected": bars["B"]["dsr"],
        "dsr_pass": int(bars["B"]["dsr_pass"]),
        "spa_pass": int(bars["B"]["spa_pass"]),
        "spa_p_full": bars["B"]["spa_p_value_full"],
        "cost_stress_pass": int(bars["B"]["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bars["B"]["worst_slice_pass"]),
        "passes": int(bars["B"]["passes"]),
        "decisive_start": 1380,
        "n_resamples": 2000,
        "arm_a_var_trials": var_a,
        "arm_a_passes": int(bars["A"]["passes"]),
        "spa_p_decisive_b30_s42": bars["B"]["spa_p_value"],
        **{f"spa_p_decisive_b{block}_s{seed}": grid[(block, seed)] for block, seed in _B1_HOURLY_RV_CELLS[1:]},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_reduction_pct": 100 * (max_drawdown(net_a) - max_drawdown(net_b)) / max_drawdown(net_a),
        "spot_drag_pct_yr": turnover_b / n * 0.006 * 2190,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_b_intra": intra_turnover(arm_b),
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_positions_differ": sum(any(p != arm_a[a][k] for a in _B2_ASSETS for p in arm_b[a][k]) for k in range(n)),
    }
    own_stamps = {a: [h4_ts[k] for k in asset_ts[a]] for a in _B2_ASSETS}
    per_year = {str(i + 1): exit_events_per_year(events, own_stamps) for i, (_, events) in enumerate(exits)}
    counts = [
        c
        for arm in per_year.values()
        for by_asset in arm.values()
        for by_lookback in by_asset.values()
        for c in by_lookback.values()
    ]
    events, early, false = (sum(c[i] for c in counts) for i in range(3))
    differ = hourly_closes_differ_per_year(directions_a, directions_b, h4_ts)
    expected |= {
        "exit_events_per_year": per_year,
        "exit_events": events,
        "exit_events_early": early,
        "exit_events_false": false,
        "share_false": false / events,
        "hourly_closes_directions_differ": sum(differ.values()),
        "hourly_closes_directions_differ_per_year": differ,
    }
    assert set(expected) == _B1_EXIT_METRIC_KEYS
    assert stored == expected


@pytest.mark.retired
def test_the_b1_hourly_exit_preflight_reads_arm_a_and_the_exits_and_never_builds_arm_bs_positions_or_returns(tmp_path, monkeypatch):
    root = _b1_hourly_exit_dataset(tmp_path)
    trial = subjects.SUBJECTS["b1-hourly-channel-exits"].build(ObservedReader(root), "ohlc-test", None)

    def arm_b(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions or returns")

    monkeypatch.setattr(subjects, "a2_slot_positions", arm_b)
    monkeypatch.setattr(subjects, "net_of_cost_hourly", arm_b)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    metrics = subjects.SUBJECTS["b1-hourly-channel-exits-preflight"].build(ObservedReader(root), "ohlc-test", None)

    assert [arguments["n_trials"] for arguments, _ in bars] == [5]
    ints = _ARM_A_BAR_FLAGS | {"exit_events", "exit_events_early", "exit_events_false", "hourly_closes_directions_differ"}
    dicts = {"exit_events_per_year", "hourly_closes_directions_differ_per_year"}
    assert set(metrics) == _B1_EXIT_PREFLIGHT_KEYS
    assert {key for key, value in metrics.items() if type(value) is int} == ints
    assert {key for key, value in metrics.items() if type(value) is dict} == dicts
    assert {key for key, value in metrics.items() if type(value) is float} == _B1_EXIT_PREFLIGHT_KEYS - ints - dicts
    assert metrics["hourly_closes_directions_differ"] > 0
    assert 0 < metrics["exit_events_early"] < metrics["exit_events"] == metrics["exit_events_early"] + metrics["exit_events_false"]
    assert {key: metrics[key] for key in _B1_EXIT_ENGAGEMENT} == {key: trial[key] for key in _B1_EXIT_ENGAGEMENT}
    assert (metrics["passes"], metrics["arm_a_var_trials"]) == (trial["arm_a_passes"], trial["arm_a_var_trials"])
    assert {key: metrics[key] for key in _B1_HOURLY_RV_ANCHORS} == {key: trial[key] for key in _B1_HOURLY_RV_ANCHORS}


def _b1_hourly_exit_args(name: str, tmp_path: Path, *, dataset: str = "ohlc-test") -> list[str]:
    return ["research", "eval", "--subject", name, "--dataset", dataset, *_as_trial(name, tmp_path)]


@pytest.mark.parametrize("name", ["b1-hourly-channel-exits", "b1-hourly-channel-exits-preflight"])
def test_a_b1_hourly_exit_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)

    result = runner.invoke(app, [*_b1_hourly_exit_args(name, tmp_path, dataset="ohlc-rolling"), "--as-of", "2026-10-03"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} evaluates a frozen set's 4h and hourly series, never the rolling dataset as of a day: drop --as-of" in (
        result.output
    )


def _an_hourly_close_set(path: Path, value: float | None) -> datetime:
    frame = pl.read_parquet(path)
    closes, k = frame["close"].to_list(), frame.height // 2
    closes[k] = value
    frame.with_columns(close=pl.Series(closes, dtype=frame.schema["close"])).write_parquet(path)
    return frame["ts"][k]


@pytest.mark.retired
@pytest.mark.parametrize(
    ("value", "shown"), [pytest.param(0.0, "0.0", id="zero-close"), pytest.param(None, "None", id="null-close")]
)
def test_b1_hourly_exit_refuses_an_hourly_close_it_cannot_check_naming_the_asset_and_stamp(tmp_path, monkeypatch, value, shown):
    root = _b1_hourly_exit_dataset(tmp_path)
    stamp = _an_hourly_close_set(root / "ohlc-test" / "ETH/EUR/60.parquet", value)
    _anchor(monkeypatch, root)
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)

    result = runner.invoke(app, _b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        "b1-hourly-channel-exits over the full history: ETH: hourly close must be a finite number above 0, got "
        f"{shown} at {stamp.isoformat()}"
    ) in result.output
    assert calls == []


@pytest.mark.retired
def test_b1_hourly_exit_refuses_an_hourly_bar_in_a_4h_bar_its_240_file_lacks(tmp_path, monkeypatch):
    root = _b1_hourly_exit_dataset(tmp_path)
    path = root / "ohlc-test" / "ETH/EUR/240.parquet"
    frame = pl.read_parquet(path)
    dropped = frame["ts"][frame.height // 2]
    frame.filter(pl.col("ts") != dropped).write_parquet(path)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, _b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"b1-hourly-channel-exits over the full history: ETH: an hourly bar at {dropped.isoformat()} lies in a 4h bar the 240 "
        "series lacks"
    ) in result.output


def _arm_a_never_draws_down(monkeypatch) -> None:
    monkeypatch.setattr(subjects, "max_drawdown", lambda returns: 0.0)


@pytest.mark.retired
@pytest.mark.parametrize(
    ("freeze", "named"),
    [
        pytest.param(_arm_a_flat, "turnover_a is 0.0", id="arm-a-never-trades"),
        pytest.param(_arm_a_never_draws_down, "arm_a_max_drawdown is 0.0", id="arm-a-never-draws-down"),
    ],
)
def test_b1_hourly_exit_refuses_a_build_whose_arm_a_never_trades_or_never_draws_down(tmp_path, monkeypatch, freeze, named):
    _anchor(monkeypatch, _b1_hourly_exit_dataset(tmp_path))
    freeze(monkeypatch)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    result = runner.invoke(app, _b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "b1-hourly-channel-exits over the full history: " in result.output and named in result.output
    assert bars == []


@pytest.mark.parametrize("name", ["b1-hourly-channel-exits", "b1-hourly-channel-exits-preflight"])
def test_a_b1_hourly_exit_build_without_an_exit_event_is_refused(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _b1_hourly_exit_dataset(tmp_path))
    real = subjects.asset_directions_hourly_exit

    def no_exits(*args, **kwargs):
        directions, events = real(*args, **kwargs)
        return directions, {asset: dict.fromkeys(by_lookback, []) for asset, by_lookback in events.items()}

    monkeypatch.setattr(subjects, "asset_directions_hourly_exit", no_exits)

    result = runner.invoke(app, _b1_hourly_exit_args(name, tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the full history: exit_events is 0, and share_false divides by it" in result.output


@pytest.mark.retired
@pytest.mark.parametrize(
    ("flags", "refused"),
    [
        pytest.param(
            [],
            "b1-hourly-channel-exits declares a verdict rule, so every run of it is a trial: run it with --register",
            id="plain-eval",
        ),
        pytest.param(
            ["--register", "--iteration", "iter-179", "--family", "B1", "--n-trials", "4"],
            "--n-trials 4 is not 5, the count b1-hourly-channel-exits declares and deflates at: pass --n-trials 5",
            id="trial-4s-count",
        ),
    ],
)
def test_b1_hourly_exit_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, flags, refused):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b1_hourly_rv_reads", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", "b1-hourly-channel-exits", "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.retired
def test_b1_hourly_exit_reads_both_grids_under_the_window(tmp_path, monkeypatch):
    root = _b1_hourly_exit_dataset(tmp_path)
    window = (str(_B1_START + timedelta(hours=4 * 100)), str(_B1_START + timedelta(hours=4 * (_B1_BARS - 1))))
    read_series, reads = ObservedReader.read_series, []

    def recording_read(self, dataset, relpath, window=None):
        reads.append((relpath, window))
        return read_series(self, dataset, relpath, window)

    def stop(reads):
        raise ValidationError("stopped after the reads")

    monkeypatch.setattr(ObservedReader, "read_series", recording_read)
    monkeypatch.setattr(subjects, "_b1_hourly_exit_inputs", stop)

    with pytest.raises(subjects.SubjectError, match="stopped after the reads"):
        subjects.SUBJECTS["b1-hourly-channel-exits"].build(ObservedReader(root), "ohlc-test", window)

    assert sorted(reads) == sorted((f"{a}/EUR/{i}.parquet", window) for a in _B2_ASSETS for i in (240, 60))


@pytest.mark.retired
def test_a_b1_hourly_exit_window_off_the_4h_grid_is_refused_naming_an_hourly_bar_its_240_read_lacks(tmp_path, monkeypatch):
    _anchor(monkeypatch, _b1_hourly_exit_dataset(tmp_path))
    start, end = _B1_START + timedelta(hours=2), _B1_START + timedelta(hours=4 * (_B1_BARS - 1))

    result = runner.invoke(app, [*_b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path), "--window", str(start), str(end)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"b1-hourly-channel-exits over the window {start} .. {end}: ADA: an hourly bar at {start.isoformat()} lies in a 4h "
        "bar the 240 series lacks"
    ) in result.output


def _declared_series(tmp_path: Path, subject: subjects.Subject) -> tuple[Path, datetime]:
    root = tmp_path / "data"
    for i, asset in enumerate(subject.assets):
        for interval in subject.intervals:
            relpath = f"{asset}/EUR/{interval}.parquet"
            _write_series(root, "ohlc-test", relpath, 600 * 1440 // interval, phase=i * 0.7, step=60 * interval)
    return root, datetime.fromtimestamp(_EPOCH_2020, UTC)


# A subject whose build reads a dataset it does not declare brings its own fixture here, and b1-window-only shares
# b1-conditioning's; the ruled B1 subjects and their pre-flights bring theirs, shorter than their declared series —
# `_B1_BARS` 4h bars against `_declared_series`' 600 days — because each row that evaluates them runs arm A's kill bar,
# and the trial's arm B's too, over the whole series; any other is fed its declared series.
_CONTRACT_DATASETS = {
    "b2-funding-derisk": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
    "b2-arm-a-bar": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
    "b2-funding-derisk-full": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
    "b2-funding-derisk-full-preflight": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
    "b2-oi-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-oi-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-ratio-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-ratio-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-tape-reading": lambda tmp_path, subject: (_b2_tape_dataset(tmp_path), _B2_TAPE_START),
    "b2-liq-reentry": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
    "b2-liq-reentry-preflight": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
    "b2-funding-reentry": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
    "b2-funding-reentry-preflight": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
    "b1-conditioning": lambda tmp_path, subject: (_b1_dataset(tmp_path), _B1_START),
    "b1-window-only": lambda tmp_path, subject: (_b1_dataset(tmp_path, m15=False), _B1_START),
    "b1-hourly-rv": lambda tmp_path, subject: (_b1_hourly_rv_dataset(tmp_path), _B1_START),
    "b1-hourly-rv-preflight": lambda tmp_path, subject: (_b1_hourly_rv_dataset(tmp_path), _B1_START),
    "b1-volume-confirmation": lambda tmp_path, subject: (_b1_volume_dataset(tmp_path), _B1_START),
    "b1-volume-confirmation-preflight": lambda tmp_path, subject: (_b1_volume_dataset(tmp_path), _B1_START),
    "b1-hourly-channel-exits": lambda tmp_path, subject: (_b1_hourly_exit_dataset(tmp_path), _B1_START),
    "b1-hourly-channel-exits-preflight": lambda tmp_path, subject: (_b1_hourly_exit_dataset(tmp_path), _B1_START),
}


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

    result = runner.invoke(app, [*args, *_as_trial(name, tmp_path)])

    assert result.exception is None or isinstance(result.exception, SystemExit), "a refusal ends in an exit, never a traceback"
    if case == "evaluates":
        assert result.exit_code == 0, result.output
        assert set(_block_and_metrics(result.output)["metrics"]) == subject.metric_keys
    elif case in _CONTRACT_WINDOWS:
        assert result.exit_code == 1
        assert f"{name} over the window {args[-2]} .. {args[-1]}" in result.output
    elif case == "a-zero-close":
        assert result.exit_code == 1
        assert f"{name} over the full history" in result.output
    elif result.exit_code == 1:
        # A subject may evaluate an asset that never closes or a late first BTC bar; one that refuses names where.
        assert f"{name} over the full history" in result.output or spoilt in result.output


@dataclass(frozen=True)
class _MovedCrossfreqDefaults(CrossfreqSystemConfig):
    fee_per_side: float = 0.0045
    spread_per_side: float = 0.0010
    a2_arms: tuple[tuple[tuple[int, int, int], float], ...] = (((10, 30, 60), 0.15), ((40, 80, 160), 0.08))


@pytest.mark.parametrize("name", sorted(subjects.SUBJECTS))
def test_every_subjects_metrics_hold_when_the_shared_defaults_move(tmp_path, monkeypatch, name):
    subject = subjects.SUBJECTS[name]
    root, _ = _CONTRACT_DATASETS.get(name, _declared_series)(tmp_path, subject)
    pinned = subject.build(ObservedReader(root), "ohlc-test", None)
    monkeypatch.setattr(subjects, "CrossfreqSystemConfig", _MovedCrossfreqDefaults)
    monkeypatch.setitem(build_combined_system.__kwdefaults__, "config", CombinedSystemConfig(spot_fee_per_side=0.0045))

    assert subject.build(ObservedReader(root), "ohlc-test", None) == pinned


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


def test_attempts_init_writes_one_genesis_line_and_prints_its_allowlist_row(tmp_path, monkeypatch):
    path = tmp_path / "fresh-clone" / ".local" / "trial-attempts.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(attempts, "log_path", lambda code_root: path)

    result = runner.invoke(app, ["research", "attempts-init"])

    assert result.exit_code == 0, result.output
    log = attempts.AttemptLog(path)
    assert len(log.lines) == 1 and f"{log.log_id} {log.host}" in result.output.splitlines()
    assert "docs/reference/trial-attempt-logs.txt" in result.output
    again = runner.invoke(app, ["research", "attempts-init"])
    assert again.exit_code == 1 and "exists: a log is created once" in again.output
    assert len(attempts.AttemptLog(path).lines) == 1


def test_attempts_init_creates_the_local_dir_a_fresh_clones_main_checkout_lacks(tmp_path, monkeypatch):
    main_checkout = tmp_path / "fresh-clone"
    main_checkout.mkdir()
    path = main_checkout / ".local" / "trial-attempts.jsonl"
    monkeypatch.setattr(attempts, "log_path", lambda code_root: path)
    assert not path.parent.exists()

    result = runner.invoke(app, ["research", "attempts-init"])

    assert result.exit_code == 0, result.output
    assert [line["kind"] for line in attempts.AttemptLog(path).lines] == ["genesis"]


def _refused_before_the_fit(tmp_path, monkeypatch, *, registry: Path | None = None, flags: dict | None = None, **declared) -> str:
    registry = registry or tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, **declared)
    typed = {"family": declared.get("family", "STUB"), "n_trials": declared.get("n_trials", 1), **(flags or {})}
    before = _log_lines(attempts.log_path(_REPO))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, **typed)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert calls == [] and _log_lines(attempts.log_path(_REPO)) == before
    return result.output


def _planted(path: Path, *subjects_ended: tuple[str, str | None], family: str = "STUB") -> None:
    """Another session's attempts, each ended with its verdict, or left open for None."""
    log = attempts.AttemptLog(path)
    for subject, verdict in subjects_ended:
        invocation = {
            "subject": subject,
            "dataset": "ohlc-test",
            "window": None,
            "as_of": None,
            "accept_holes": False,
            "comparator_trial": None,
            "commit": _CLEAN_HEAD,
        }
        attempt = log.begin(
            lambda lines: None,
            invocation=invocation,
            spec_hash="c" * 64,
            family=family,
            bucket=None,
            n_trials=1,
            worktree=path.parent,
            branch="research/elsewhere",
            registry=path.parent / "r.jsonl",
            ledger=path.parent / "l.jsonl",
        )
        if verdict is not None:
            log.end(attempt, verdict=verdict, metrics={"sharpe": 0.5})


_SEED_BLOCK = {
    "ohlc-test": {
        "files": {"BTC/EUR/1440.parquet": "c" * 64},
        "rows": 10,
        "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"],
    }
}


def _begin_line_hash(path: Path, attempt: int) -> str:
    return next(line["line_hash"] for line in _log_lines(path) if line["kind"] == "begin" and line["attempt"] == attempt)


def _seed(
    registry: Path,
    family: str,
    count: int,
    *,
    log: str = "e" * 32,
    first_id: int = 1,
    subject: str = "seed",
    begin_of=lambda attempt_id: f"{attempt_id:064x}",
) -> None:
    for n in range(1, count + 1):
        TrialRegistry(registry).append(
            iteration="iter-001",
            family=family,
            spec_hash="s",
            datasets=_SEED_BLOCK,
            seeds=[0],
            metrics={"sharpe": 0.3},
            invocation={
                "subject": subject,
                "dataset": "ohlc-test",
                "window": None,
                "as_of": None,
                "accept_holes": False,
                "comparator_trial": None,
                "commit": _CLEAN_HEAD,
            },
            n_trials_in_family=n,
            verdict="reject",
            run_ref="cli/registry/record.py",
            attempt={"log": log, "id": first_id + n - 1, "begin": begin_of(first_id + n - 1), "absorbs": [], "counted": []},
        )


def test_a_run_on_an_abandoned_branch_is_counted_by_the_next_registration(tmp_path, monkeypatch):
    main, worktree = tmp_path / "main", tmp_path / "wt"
    _git_repo(main, _STUB_SPEC)
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", "-b", "research/x", str(worktree)], check=True, capture_output=True
    )
    log = main / ".local" / "trial-attempts.jsonl"
    log.parent.mkdir()
    log_id = attempts.init_log(log, host="zcrypto-test")
    (tmp_path / "trial-attempt-logs.txt").write_text(f"{log_id} zcrypto-test\n")
    monkeypatch.setattr(
        attempts,
        "log_path",
        lambda root: _unstubbed_log_path(root) if Path(root).is_relative_to(tmp_path) else tmp_path / "stray.jsonl",
    )
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch)
    monkeypatch.setattr(research_command, "_REPO_ROOT", worktree)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(worktree / "registry.jsonl", n_trials=1)]).exit_code == 0
    subprocess.run(["git", "-C", str(main), "worktree", "remove", "--force", str(worktree)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(main), "branch", "-q", "-D", "research/x"], check=True, capture_output=True)
    monkeypatch.setattr(research_command, "_REPO_ROOT", main)
    calls = _stub_subject(monkeypatch, "stub-2")

    refused = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(main / "registry.jsonl", n_trials=1)])

    assert refused.exit_code == 1 and f"{log_id[:8]}#1 stub adopt" in refused.output and "on research/x" in refused.output
    assert calls == []
    _stub_subject(monkeypatch, "stub-2", n_trials=2)
    admitted = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(main / "registry.jsonl", n_trials=2)])
    assert admitted.exit_code == 0, admitted.output
    spec_hash = hashlib.sha256((main / _STUB_SPEC).read_bytes()).hexdigest()
    assert json.loads((main / "registry.jsonl").read_text())["attempt"]["counted"] == [
        {
            "log": log_id,
            "id": 1,
            "begin": _begin_line_hash(log, 1),
            "family": "STUB",
            "subject": "stub",
            "spec_hash": spec_hash,
            "verdict": "adopt",
            "metrics": {"sharpe": 1.0},
        }
    ]


def test_a_run_refused_after_its_print_still_counts(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    refused = runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)])
    assert refused.exit_code == 1 and '"sharpe": 1.0' in refused.output and not registry.exists()
    assert _log_lines(_attempts_log)[-1]["verdict"] == "adopt"
    calls = _stub_subject(monkeypatch, "stub-2")
    assert runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=1)]).exit_code == 1 and calls == []

    retry = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert retry.exit_code == 0, retry.output
    assert json.loads(registry.read_text())["attempt"]["absorbs"] == [{"id": 1, "begin": _begin_line_hash(_attempts_log, 1)}]


def test_a_retry_whose_numbers_moved_is_refused_after_its_print_and_both_count(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1
    _stub_subject(monkeypatch, metrics={"sharpe": 2.0})

    retry = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    assert retry.exit_code == 1 and '"sharpe": 2.0' in retry.output and f"{log8}#1" in retry.output and not registry.exists()
    _stub_subject(monkeypatch, "stub-2", n_trials=2)
    third = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=2)])
    assert third.exit_code == 1 and f"{log8}#1" in third.output and f"{log8}#2" in third.output


def _end_refused(self, attempt, **outcome):
    raise OSError("No space left on device")


@pytest.mark.parametrize(
    ("refused", "figure"),
    [
        pytest.param("after-its-print", 3, id="after-its-print"),
        pytest.param("before-the-fit", 3, id="before-the-fit"),
        pytest.param("open-and-held", 2, id="open-and-held"),
        pytest.param("frozen", 3, id="frozen"),
    ],
)
def test_raising_n_trials_to_the_figure_a_refusal_names_admits_the_next_run(tmp_path, monkeypatch, _attempts_log, refused, figure):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    if refused == "after-its-print":
        stub = subjects.SUBJECTS["stub"]

        def build(reader, dataset, window, as_of=None, accept_holes=False):
            _planted(_attempts_log, ("elsewhere", None))
            return stub.build(reader, dataset, window, as_of, accept_holes)

        monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))
        first = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])
        assert '"sharpe": 1.0' in first.output, first.output
        assert "0 records, the next run, and 2 attempts that never landed" in first.output, first.output
    else:
        if refused == "before-the-fit":
            assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1
        else:
            with monkeypatch.context() as patch:
                patch.setattr(attempts.AttemptLog, "end", _end_refused)
                # Its attempt stands for one whose process exited once its end was refused.
                patch.setattr(attempts, "_process_marks", lambda: {"pid": os.getpid(), "boot": "another boot"})
                assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 1
        if refused == "frozen":
            _seed(registry, "STUB", 1, subject="stub")
        else:
            _planted(_attempts_log, ("elsewhere", "reject"))
        first = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])
        assert '"sharpe"' not in first.output, first.output
    named = re.search(r"family STUB needs at least (\d+)", first.output)
    assert first.exit_code == 1 and named and int(named.group(1)) == figure, first.output
    assert ("stub's n_trials is frozen by its trial 1" in first.output) == (refused == "frozen"), first.output
    n, subject = figure, "stub-2" if refused == "frozen" else "stub"
    # This stub's numbers move with its declared count and its spec file stays, the case where the figure is exact.
    _stub_subject(monkeypatch, subject, n_trials=n, metrics={"sharpe": 1.0 / n})

    retry = runner.invoke(app, [*_stub_eval(subject), *_register_args(registry, n_trials=n)])

    assert retry.exit_code == 0, retry.output


def test_a_retry_of_a_printed_attempt_at_the_budgets_edge_is_refused_before_its_fit(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", "B")
    monkeypatch.setitem(budget.BUCKET_OF, "OTHER", "B")
    _seed(registry, "OTHER", 24)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1

    output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, n_trials=2, metrics={"sharpe": 2.0})

    assert "bucket B has spent 25 of its 25 trials (24 records, 1 attempts that never landed)" in output
    assert len(registry.read_text().splitlines()) == 24


def test_a_bucket_filled_during_the_fit_refuses_the_run_after_its_print(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", "B")
    monkeypatch.setitem(budget.BUCKET_OF, "OTHER", "B")
    _seed(registry, "OTHER", 24)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    stub = subjects.SUBJECTS["stub"]

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        _planted(_attempts_log, ("elsewhere", None), family="OTHER")
        return stub.build(reader, dataset, window, as_of, accept_holes)

    monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and '"sharpe": 1.0' in result.output, result.output
    assert "bucket B has spent 25 of its 25 trials (24 records, 1 attempts that never landed)" in result.output
    assert len(registry.read_text().splitlines()) == 24


def test_a_stop_after_its_bucket_filled_during_the_fit_keeps_its_reading(tmp_path, monkeypatch, _attempts_log):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", "B")
    monkeypatch.setitem(budget.BUCKET_OF, "OTHER", "B")
    _seed(registry, "OTHER", 24)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None)
    stub = subjects.SUBJECTS["stub"]

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        _planted(_attempts_log, ("elsewhere", None), family="OTHER")
        return stub.build(reader, dataset, window, as_of, accept_holes)

    monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, ledger=ledger)])

    assert result.exit_code == 0, result.output
    assert "no verdict — the stub's stop: recorded reading 1; no trial spent" in result.output
    assert _kept(ledger)[0]["attempt"]["id"] == 1 and len(registry.read_text().splitlines()) == 24


def test_a_record_of_the_subject_landed_during_the_fit_refuses_the_run_after_its_print_naming_a_new_subject(
    tmp_path, monkeypatch, _attempts_log
):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    stub = subjects.SUBJECTS["stub"]

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        _seed(registry, "STUB", 1, subject="stub")
        return stub.build(reader, dataset, window, as_of, accept_holes)

    monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and '"sharpe": 1.0' in result.output, result.output
    assert "family STUB needs at least 3: 1 records, the next run, and 1 attempts that never landed" in result.output
    assert "stub's n_trials is frozen by its trial 1: declare a new subject (a new name) for the further trial" in result.output
    assert len(registry.read_text().splitlines()) == 1


@pytest.mark.parametrize(
    ("marks", "admitted"),
    [
        pytest.param(lambda: None, False, id="its-process-runs"),
        pytest.param(lambda: {"pid": _reaped_pid(), "boot": attempts._boot_id()}, True, id="its-pid-reaped"),
        pytest.param(lambda: {"pid": os.getpid(), "boot": "another boot"}, True, id="another-boot"),
    ],
)
def test_an_open_attempt_at_the_budgets_edge_is_held_only_when_its_process_is_gone(
    tmp_path, monkeypatch, _attempts_log, marks, admitted
):
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", "B")
    monkeypatch.setitem(budget.BUCKET_OF, "OTHER", "B")
    _seed(registry, "OTHER", 24)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(attempts.AttemptLog, "end", _end_refused)
        if (planted := marks()) is not None:
            patch.setattr(attempts, "_process_marks", lambda: planted)
        assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 1

    if not admitted:
        output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, n_trials=2)
        assert "bucket B has spent 25 of its 25 trials (24 records, 1 attempts that never landed)" in output
        return
    _stub_subject(monkeypatch, n_trials=2)
    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=2)])
    assert result.exit_code == 0, result.output
    lines = registry.read_text().splitlines()
    assert len(lines) == 25 and json.loads(lines[-1])["attempt"]["absorbs"] == [
        {"id": 1, "begin": _begin_line_hash(_attempts_log, 1)}
    ]


def test_a_stop_spends_nothing(tmp_path, monkeypatch, _attempts_log):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, ledger=ledger)]).exit_code == 0
    assert _kept(ledger)[0]["attempt"]["id"] == 1
    _stub_subject(monkeypatch, "stub-2")
    # The stop's reading landed in `ledger`; this registration reads another, so the stop is not landed here.
    elsewhere = tmp_path / "another-ledger.jsonl"
    admitted = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=1, ledger=elsewhere)])
    assert admitted.exit_code == 0, admitted.output


def test_a_failed_build_logs_a_failed_end_and_counts_nothing(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _raising_stub(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 1
    assert _log_lines(_attempts_log)[-1]["failed"] == "SubjectError: the stub's window is too short"
    _stub_subject(monkeypatch, "stub-2")
    assert runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=1)]).exit_code == 0


def test_a_scratch_registry_run_is_an_orphan_once_the_committed_registry_is_the_target(tmp_path, monkeypatch, _attempts_log):
    scratch, committed = tmp_path / "scratch.jsonl", tmp_path / "committed.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), committed)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(scratch, n_trials=1)]).exit_code == 0
    calls = _stub_subject(monkeypatch, "stub-2")
    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    base = ["--register", "--iteration", "iter-001", "--family", "STUB"]
    refused = runner.invoke(app, [*_stub_eval("stub-2"), *base, "--n-trials", "1"])
    assert refused.exit_code == 1 and f"{log8}#1" in refused.output and calls == []
    _stub_subject(monkeypatch, "stub-2", n_trials=2)
    assert runner.invoke(app, [*_stub_eval("stub-2"), *base, "--n-trials", "2"]).exit_code == 0
    assert [entry["id"] for entry in json.loads(committed.read_text())["attempt"]["counted"]] == [1]


def test_an_open_attempt_in_the_family_raises_the_count(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _planted(_attempts_log, ("elsewhere", None))
    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    assert f"{log8}#1 elsewhere no end" in _refused_before_the_fit(tmp_path, monkeypatch, registry=registry)
    _stub_subject(monkeypatch, n_trials=2)

    admitted = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=2)])

    assert admitted.exit_code == 0, admitted.output
    assert json.loads(registry.read_text())["attempt"]["counted"] == []


def test_a_held_attempt_another_session_lands_mid_fit_is_absorbed_by_no_one_twice(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1
    log_id, stub = attempts.AttemptLog(_attempts_log).log_id, subjects.SUBJECTS["stub"]

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        _seed(registry, "OTHER", 1, log=log_id, begin_of=lambda attempt_id: _begin_line_hash(_attempts_log, attempt_id))
        return stub.build(reader, dataset, window, as_of, accept_holes)

    monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    assert json.loads(registry.read_text().splitlines()[-1])["attempt"]["absorbs"] == []


@pytest.mark.parametrize(
    ("planted", "method", "fitted", "figure"),
    [
        pytest.param("a-begin", "begin", False, 2, id="a-begin-in-the-window"),
        pytest.param("a-record", "begin", False, 2, id="a-record-in-the-window"),
        pytest.param("a-begin", "locked", True, 3, id="a-begin-before-the-post-check"),
    ],
)
def test_what_lands_between_a_read_and_the_lock_its_count_takes_is_counted(
    tmp_path, monkeypatch, _attempts_log, planted, method, fitted, figure
):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    real = getattr(attempts.AttemptLog, method)

    def planting(self, *args, **kwargs):
        monkeypatch.setattr(attempts.AttemptLog, method, real)
        if planted == "a-begin":
            _planted(_attempts_log, ("elsewhere", None))
        else:
            _seed(registry, "STUB", 1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(attempts.AttemptLog, method, planting)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    named = re.search(r"family STUB needs at least (\d+)", result.output)
    assert result.exit_code == 1 and named and int(named.group(1)) == figure, result.output
    assert bool(calls) is fitted, result.output


def test_a_plain_eval_of_a_ruled_subject_is_refused_before_any_read(tmp_path, monkeypatch):
    _anchor(monkeypatch, tmp_path / "no-data")
    calls = _stub_subject(monkeypatch)

    result = runner.invoke(app, _stub_eval())

    assert result.exit_code == 1 and calls == []
    assert (
        "stub declares a verdict rule, so every run of it is a trial: run it with --register; a ruleless pre-flight subject "
        "reads the inputs without the trial's result"
    ) in result.output


def test_a_plain_eval_of_a_ruleless_subject_is_admitted(tmp_path, monkeypatch, _attempts_log):
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch, verdict=None, no_verdict=None, family=None, n_trials=None)
    assert runner.invoke(app, _stub_eval()).exit_code == 0 and len(_log_lines(_attempts_log)) == 1


def test_a_family_other_than_the_subjects_is_refused(tmp_path, monkeypatch):
    output = _refused_before_the_fit(tmp_path, monkeypatch, flags={"family": "OTHER"})
    assert "--family OTHER is not STUB, the family stub declares: pass --family STUB" in output


def test_an_n_trials_other_than_the_subjects_is_refused(tmp_path, monkeypatch):
    output = _refused_before_the_fit(tmp_path, monkeypatch, flags={"n_trials": 2})
    assert "--n-trials 2 is not 1, the count stub declares and deflates at: pass --n-trials 1" in output


def test_a_subject_counting_fewer_than_its_family_needs_is_refused_naming_each_orphan(tmp_path, monkeypatch, _attempts_log):
    _planted(_attempts_log, ("elsewhere", "reject"), ("elsewhere-too", "park"))
    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    output = _refused_before_the_fit(tmp_path, monkeypatch)
    assert (
        "stub declares n_trials 1, and family STUB needs at least 3: 0 records, this run, and 2 attempts that never landed"
        in output
    )
    assert f"{log8}#1 elsewhere reject" in output and f"{log8}#2 elsewhere-too park" in output
    assert "raise stub's n_trials, which its deflated Sharpe uses, commit, then run again" in output


def test_a_bucket_at_its_budget_is_refused(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _seed(registry, "A1", 40)
    output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, family="A1", n_trials=41)
    assert (
        "bucket A has spent 40 of its 40 trials (40 records, 0 attempts that never landed), so this trial would exceed it: an "
        "expansion is the owner's ruling, written into cli/registry/budget.py by a pull request that quotes it"
    ) in output


def test_a_bucket_one_below_its_budget_admits_its_last_trial(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _seed(registry, "A1", 39)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, family="A1", n_trials=40)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, family="A1", n_trials=40)])

    assert result.exit_code == 0, result.output
    assert len(registry.read_text().splitlines()) == 40


def test_a_family_in_no_bucket_is_refused(tmp_path, monkeypatch):
    output = _refused_before_the_fit(tmp_path, monkeypatch, family="ZZ")
    assert "family ZZ is in no bucket of cli/registry/budget.py: add it with its bucket in a reviewed pull request" in output


@pytest.mark.parametrize(
    ("n_trials", "message"),
    [
        pytest.param(
            2,
            "stub declares n_trials 2, and its trial 1 landed at n_trials 1, which that record's deflated Sharpe used, so its n_trials is frozen: declare a new subject (a new name) for the further trial",
            id="raised-count",
        ),
        pytest.param(
            1,
            "stub's n_trials is frozen by its trial 1: declare a new subject (a new name) for the further trial",
            id="declared-count",
        ),
    ],
)
def test_a_landed_subjects_n_trials_is_frozen(tmp_path, monkeypatch, n_trials, message):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 0

    assert message in _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, n_trials=n_trials)


def _repo_with_develop(tmp_path: Path, monkeypatch, *records: dict, develop_at: str = "head") -> Path:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    if records:
        (repo / "docs" / "reference").mkdir(parents=True)
        (repo / attempts.REGISTRY_RELPATH).write_text("".join(json.dumps(record) + "\n" for record in records))
        subprocess.run(["git", "-C", str(repo), "add", "--", attempts.REGISTRY_RELPATH], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), *_GIT_IDENTITY, "commit", "-q", "-m", "landed"], check=True, capture_output=True)
        landed_at = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--detach", head], check=True, capture_output=True)
        head = landed_at if develop_at == "current" else head
    if develop_at != "none":
        subprocess.run(["git", "-C", str(repo), "update-ref", attempts.DEVELOP, head], check=True, capture_output=True)
    monkeypatch.setattr(attempts, "landed", lambda code_root, registry, ledger: _unstubbed_landed(repo, registry, ledger))
    return repo


def test_the_register_path_makes_no_network_call(tmp_path, monkeypatch):
    repo = _repo_with_develop(tmp_path, monkeypatch)
    log = repo / ".local" / "trial-attempts.jsonl"
    log.parent.mkdir()
    log_id = attempts.init_log(log, host="zcrypto-test")
    (repo / attempts.ALLOWLIST).parent.mkdir(parents=True, exist_ok=True)
    (repo / attempts.ALLOWLIST).write_text(f"{log_id} zcrypto-test\n")
    subprocess.run(["git", "-C", str(repo), "add", "--", attempts.ALLOWLIST], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), *_GIT_IDENTITY, "commit", "-q", "-m", "allowlist"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", attempts.DEVELOP, "HEAD"], check=True, capture_output=True)
    monkeypatch.setattr(attempts, "log_path", lambda code_root: _unstubbed_log_path(repo))
    monkeypatch.setattr(attempts, "allowed_log_ids", lambda code_root: _unstubbed_allowed(repo))
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    argvs, real_run = [], subprocess.run

    def spy(argv, *args, **kwargs):
        argvs.append([str(arg) for arg in argv])
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    assert any("show" in argv or "cat-file" in argv for argv in argvs), argvs
    assert [argv for argv in argvs if {"fetch", "ls-remote", "gh"} & set(argv) or argv[0] == "gh"] == []


@pytest.mark.parametrize("develop_at", ["stale", "current"])
def test_a_stale_develop_requires_the_same_count(tmp_path, monkeypatch, _attempts_log, develop_at):
    _planted(_attempts_log, ("elsewhere", "reject"))
    log_id = attempts.AttemptLog(_attempts_log).log_id
    landed_record = {
        "trial_id": 1,
        "family": "STUB",
        "record_hash": "7" * 64,
        "n_trials_in_family": 1,
        "invocation": {"subject": "elsewhere"},
        "attempt": {"log": log_id, "id": 1, "begin": _begin_line_hash(_attempts_log, 1), "absorbs": [], "counted": []},
    }
    # A legacy record: neither an invocation key nor an attempt key.
    legacy = {"trial_id": 2, "family": "A1", "record_hash": "6" * 64, "n_trials_in_family": 1}
    _repo_with_develop(tmp_path, monkeypatch, landed_record, legacy, develop_at=develop_at)
    registry = tmp_path / "registry.jsonl"

    assert "family STUB needs at least 2" in _refused_before_the_fit(tmp_path, monkeypatch, registry=registry)
    _stub_subject(monkeypatch, n_trials=2)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=2)]).exit_code == 0
    counted = [entry["id"] for entry in json.loads(registry.read_text())["attempt"]["counted"]]
    assert counted == ([1] if develop_at == "stale" else [])


def test_an_unresolvable_develop_is_refused(tmp_path, monkeypatch):
    repo = _repo_with_develop(tmp_path, monkeypatch, develop_at="none")
    output = _refused_before_the_fit(tmp_path, monkeypatch)
    assert f"origin/develop does not resolve in {repo}: run git fetch origin develop, then run again" in output


def test_an_unresolvable_develop_is_refused_before_the_empty_allowlist_it_reads(tmp_path, monkeypatch):
    repo = _repo_with_develop(tmp_path, monkeypatch, develop_at="none")
    monkeypatch.setattr(attempts, "allowed_log_ids", lambda code_root: _unstubbed_allowed(repo))
    assert _unstubbed_allowed(repo) == frozenset()

    output = _refused_before_the_fit(tmp_path, monkeypatch)

    assert f"origin/develop does not resolve in {repo}: run git fetch origin develop, then run again" in output
    assert "does not list" not in output


def test_an_absent_log_is_refused_with_its_remedy(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    _attempts_log.unlink()

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and calls == [] and not _attempts_log.exists()
    assert (
        f"no trial-attempts log at {_attempts_log}: restore it from a backup if one exists; otherwise create a new log with "
        "zcrypto research attempts-init and add its id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
    ) in result.output


def test_a_broken_log_is_refused_with_its_remedy(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    _attempts_log.write_text(_attempts_log.read_text().replace('"host":"zcrypto-test"', '"host":"elsewhere"'))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and calls == [] and not registry.exists()
    assert f"{_attempts_log}: line 1 line_hash" in result.output
    assert (
        "rename it aside, then restore it from a backup if one exists; otherwise create a new log with zcrypto research "
        "attempts-init and add its id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
    ) in result.output


def test_an_unlisted_log_is_refused_with_its_remedy(tmp_path, monkeypatch, _attempts_log):
    (tmp_path / "trial-attempt-logs.txt").write_text("")
    log_id = attempts.AttemptLog(_attempts_log).log_id
    output = _refused_before_the_fit(tmp_path, monkeypatch)
    assert (
        f"the trial-attempts log {_attempts_log} has id {log_id}, which docs/reference/trial-attempt-logs.txt on origin/develop "
        "does not list: restore the listed log from a backup if one exists; otherwise add this id to "
        "docs/reference/trial-attempt-logs.txt by PR, saying what was lost, and run again once it has merged and "
        "origin/develop is fetched"
    ) in output


def test_a_log_lacking_a_landed_attempt_is_refused(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _seed(registry, "STUB", 1, log=attempts.AttemptLog(_attempts_log).log_id, first_id=5)
    output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry)
    assert (
        f"{_attempts_log} lacks attempt 5, which trial 1 carries: the log was truncated, replaced, restored from an older backup "
        "or forked; rename it aside, then "
        "restore it from a backup if one exists; otherwise create a new log with zcrypto research attempts-init and add its "
        "id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
    ) in output


def test_a_b2_run_logs_its_bucket_count_ledger_worktree_and_branch_in_its_begin_line(tmp_path, monkeypatch, _attempts_log):
    code = tmp_path / "code"
    _git_repo(code, _STUB_SPEC)
    subprocess.run(["git", "-C", str(code), "checkout", "-q", "-b", "research/b2-run"], check=True, capture_output=True)
    monkeypatch.setattr(research_command, "_REPO_ROOT", code)
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, family="B2")

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, family="B2", ledger=ledger)])

    assert result.exit_code == 0, result.output
    begin = _log_lines(_attempts_log)[1]
    assert (begin["family"], begin["bucket"], begin["n_trials"]) == ("B2", "B", 1)
    assert (begin["ledger"], begin["registry"]) == (str(ledger.resolve()), str(registry.resolve()))
    assert (begin["worktree"], begin["branch"]) == (str(code.resolve()), "research/b2-run")
