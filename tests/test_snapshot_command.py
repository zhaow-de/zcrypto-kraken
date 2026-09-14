"""CLI tests for `zcrypto snapshot sweep`: the two venue fetches and the maintenance feed are replaced by the committed
fixtures, so no test here reaches the network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.snapshot import command
from cli.snapshot.errors import SnapshotError

_FIXTURES = Path(__file__).parent / "fixtures"
ASSETPAIRS = json.loads((_FIXTURES / "kraken_assetpairs.json").read_text())
ASSETS = json.loads((_FIXTURES / "kraken_assets.json").read_text())
FEED = json.loads((_FIXTURES / "kraken_scheduled_maintenances.json").read_text())

runner = CliRunner()


def _wire(monkeypatch, *, assetpairs=ASSETPAIRS, assets=ASSETS, feed=FEED):
    monkeypatch.setattr(command, "fetch_public", lambda method: {"AssetPairs": assetpairs, "Assets": assets}[method])
    monkeypatch.setattr(command, "_fetch_maintenance_feed", lambda: feed)


def _sweep(tmp_path):
    return runner.invoke(app, ["snapshot", "sweep", "--snapshots-dir", str(tmp_path / "snapshots")])


def _archived(tmp_path) -> list[Path]:
    return sorted((tmp_path / "snapshots").glob("kraken-refdata-*.json")) if (tmp_path / "snapshots").exists() else []


def _delistings(*names):
    return {
        "scheduled_maintenances": [
            {
                "name": name,
                "scheduled_for": "2026-12-01T00:00:00.000Z",
                "created_at": "2026-08-01T00:00:00.000Z",
                "status": "scheduled",
                "components": [],
            }
            for name in names
        ]
    }


def test_a_clean_sweep_archives_the_snapshot_it_judges_and_exits_zero(tmp_path, monkeypatch):
    _wire(monkeypatch)
    result = _sweep(tmp_path)
    assert result.exit_code == 0, result.output
    files = _archived(tmp_path)
    assert len(files) == 1, files
    archived = json.loads(files[0].read_text())
    assert f"JUDGING SNAPSHOT: {archived['fetched_at']}" in result.output
    # The archived files' own naming: the stamp is `fetched_at` compacted, so the name carries the fetch, not the mtime.
    assert files[0].name == f"kraken-refdata-{archived['fetched_at'].replace('-', '').replace(':', '')[:15]}Z.json"
    assert "REFUSALS: none" in result.output and "ANNOUNCED DELISTINGS: none" in result.output
    assert "## Candidate-basket margin & leverage ground truth" in result.output and "| BTC/EUR |" in result.output


def test_a_refusal_names_the_pair_exits_non_zero_and_still_archives_the_evidence(tmp_path, monkeypatch):
    key = next(k for k, v in ASSETPAIRS.items() if v.get("wsname") == "XBT/EUR")
    _wire(monkeypatch, assetpairs={**ASSETPAIRS, key: {**ASSETPAIRS[key], "status": "cancel_only"}})
    result = _sweep(tmp_path)
    assert result.exit_code == 1, result.output
    assert "REFUSALS:" in result.output and "BTC/EUR" in result.output and "cancel_only" in result.output
    assert len(_archived(tmp_path)) == 1


def test_an_announced_delisting_is_printed_in_both_spellings_and_does_not_fail_the_run(tmp_path, monkeypatch):
    _wire(monkeypatch, feed=_delistings("DOGE, MOON, KET Delisting", "XBT Delisting"))
    result = _sweep(tmp_path)
    assert result.exit_code == 0, result.output
    assert "ANNOUNCED DELISTINGS:" in result.output
    assert "DOGE: DOGE, MOON, KET Delisting" in result.output
    assert "XBT: XBT Delisting" in result.output
    assert "scheduled_for 2026-12-01" in result.output


@pytest.mark.parametrize("failing", ["fetch_public", "_fetch_maintenance_feed"])
def test_a_failed_fetch_exits_non_zero_and_archives_nothing(tmp_path, monkeypatch, failing):
    _wire(monkeypatch)

    def _raise(*_args):
        raise SnapshotError("transport error: venue unreachable")

    monkeypatch.setattr(command, failing, _raise)
    result = _sweep(tmp_path)
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    assert _archived(tmp_path) == []
