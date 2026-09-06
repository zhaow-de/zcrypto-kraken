"""The controls that make the provenance mechanism non-vacuous (spec 00086 D7): record 44's figures
are asserted against LITERALS *and* the real registry, since literals alone drift with the build and
the registry alone lets a drifted registry and build cancel out; the synthetic control is deliberately
ungated, building under `tmp_path` so a bare checkout still proves the identity path."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cli.ohlc.dataset import to_frame, write_parquet
from cli.portfolio.crossfreq_system import build_crossfreq_system_fast
from cli.portfolio.record44_legs import load_union
from cli.registry import TrialRegistry
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _REPO_ROOT / "data"
_CANONICAL = _DATA_ROOT / "ohlc-full"
_REGISTRY = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"

_RECORD_44 = 44
_GOVERNOR_ENGAGED_BARS = 7302
_CAP_BREACH_BARS = 1318

# The record-44 slice of data/ohlc-full as the capturing loader observes it — 10 assets x {1440, 240}.
# The span's upper bound is the 4h leg's last bar START; the daily leg ends 00:00.
_FROZEN_FILES = 20
_FROZEN_ROWS = 202_405
_FROZEN_SPAN = ["2013-09-10 00:00:00+00:00", "2026-03-31 20:00:00+00:00"]

_DRIFTED = (
    "canonical dataset drifted — STOP: data/ohlc-full is the frozen record-44 oracle and must never be "
    "appended to (the engine's live store is a separate root, T0018). Every registered figure below was "
    "measured against these bytes; re-freezing mints a sibling directory instead of moving this one."
)


@pytest.mark.skipif(
    not _CANONICAL.is_dir(), reason="data/ohlc-full absent — the record-44 control runs on the data-bearing workstation only"
)
def test_the_committed_loading_path_reproduces_record_44s_figures_and_slice():
    reader = ObservedReader(_DATA_ROOT)

    def union(interval: int):
        # Exactly the composition cli/research/subjects.py builds: a bare relative root, so the paths
        # load_union composes ARE the dataset-relative keys the reader records.
        return load_union(interval, root=Path(), read=lambda path: reader.read_series("ohlc-full", path.as_posix()))

    daily_ts, daily_prices = union(1440)
    h4_ts, h4_prices = union(240)
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts)

    assert (result.governor_engaged_bars, result.cap_breach_bars) == (_GOVERNOR_ENGAGED_BARS, _CAP_BREACH_BARS), _DRIFTED
    registered = {r.trial_id: r.metrics for r in TrialRegistry(_REGISTRY).records}[_RECORD_44]
    assert (registered["governor_engaged_bars"], registered["cap_breach_bars"]) == (_GOVERNOR_ENGAGED_BARS, _CAP_BREACH_BARS)

    block = reader.block()["ohlc-full"]
    assert (len(block["files"]), block["rows"], block["span"]) == (_FROZEN_FILES, _FROZEN_ROWS, _FROZEN_SPAN), _DRIFTED


def _rows(n: int, *, start: int = 1577836800, step: int = 86400):  # 2020-01-01, daily steps
    return [[start + i * step, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(n)]


def test_the_whole_identity_path_round_trips_on_synthetic_data(tmp_path):
    root = tmp_path / "data"
    series = {"BTC/EUR/1440.parquet": 12, "ETH/EUR/1440.parquet": 9}
    for relpath, n in series.items():
        write_parquet(to_frame(_rows(n)), root / "ohlc-synthetic" / relpath)

    reader = ObservedReader(root)
    for relpath in series:
        reader.read_series("ohlc-synthetic", relpath)
    block = reader.block()

    registry_path = tmp_path / "registry.jsonl"
    appended = TrialRegistry(registry_path).append(
        iteration="iter-000",
        family="CONTROL",
        spec_hash="0" * 64,
        datasets=block,
        seeds=[],
        metrics={"sharpe": 1.0},
        n_trials_in_family=1,
        verdict="park",
        run_ref="cli/registry/observed.py",
    )

    reloaded = TrialRegistry(registry_path).records
    assert len(reloaded) == 1
    record = reloaded[0]
    assert record.schema_version == 4
    assert record.datasets == block
    assert record.dataset_hash == compute_hash(record.datasets) == appended.dataset_hash
    # The stored digests are the files' own bytes, so the round trip is not self-referential.
    entry = record.datasets["ohlc-synthetic"]
    assert entry["rows"] == sum(series.values())
    for relpath in series:
        raw = (root / "ohlc-synthetic" / relpath).read_bytes()
        assert entry["files"][relpath] == hashlib.sha256(raw).hexdigest()
