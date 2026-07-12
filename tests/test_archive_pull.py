import hashlib
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from cli.__main__ import app
from cli.archive.pull import pull_lag_seconds, verify_tree


def _seg(root: Path, pair: str, kind: str, hour: str, *, corrupt: bool = False) -> None:
    d = root / pair / kind / "2026" / "07" / "12"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{hour}.parquet"
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(p)
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if corrupt:
        digest = "0" * 64
    (d / f"{hour}.parquet.sha256").write_text(f"{digest}  {p.name}\n")


def test_verify_tree_all_ok(tmp_path):
    _seg(tmp_path, "BTC/EUR", "book", "10")
    _seg(tmp_path, "BTC/EUR", "trades", "11")
    now = datetime(2026, 7, 12, 13, 0, tzinfo=UTC)
    r = verify_tree(tmp_path, now=now)
    assert r.checked == 2 and r.ok == 2 and r.failed == ()
    # newest hour is 11:00 UTC -> lag = 2h
    assert pull_lag_seconds(r, now=now) == 2 * 3600


def test_verify_tree_flags_mismatch(tmp_path):
    _seg(tmp_path, "ETH/EUR", "book", "09", corrupt=True)
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert r.checked == 1 and r.ok == 0
    assert any("ETH/EUR/book/2026/07/12/09.parquet" in f for f in r.failed)


def test_verify_tree_skips_partfiles(tmp_path):
    d = tmp_path / "BTC/EUR/book/2026/07/12"
    d.mkdir(parents=True)
    (d / "12.part0000.parquet").write_bytes(b"partial")  # current-hour part, no manifest
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert r.checked == 0


def test_verify_tree_missing_sidecar_counts_failed(tmp_path):
    _seg(tmp_path, "BTC/EUR", "book", "10")
    d = tmp_path / "ETH/EUR/trades/2026/07/12"
    d.mkdir(parents=True)
    p = d / "09.parquet"
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(p)  # finalized, but no .sha256 sidecar
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert r.checked == 2 and r.ok == 1
    assert any("ETH/EUR/trades/2026/07/12/09.parquet" in f for f in r.failed)


def test_verify_tree_empty_sidecar_counts_failed(tmp_path):
    d = tmp_path / "BTC/EUR/book/2026/07/12"
    d.mkdir(parents=True)
    p = d / "10.parquet"
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(p)
    (d / "10.parquet.sha256").write_text("")  # malformed sidecar: empty, no digest to split()[0]
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert r.checked == 1 and r.ok == 0
    assert any("BTC/EUR/book/2026/07/12/10.parquet" in f for f in r.failed)


def test_pull_ok_exits_zero(tmp_path, monkeypatch):
    dest = tmp_path / "arch"
    dest.mkdir()
    _seg(dest, "BTC/EUR", "book", "10")
    from cli.archive import command

    monkeypatch.setattr(command, "_run_rsync", lambda source, d: 0)
    res = CliRunner().invoke(app, ["archive", "pull", "deploy@h:/src/", str(dest)])
    assert res.exit_code == 0


def test_pull_mismatch_exits_one(tmp_path, monkeypatch):
    dest = tmp_path / "arch"
    dest.mkdir()
    _seg(dest, "BTC/EUR", "book", "10", corrupt=True)
    from cli.archive import command

    monkeypatch.setattr(command, "_run_rsync", lambda source, d: 0)
    res = CliRunner().invoke(app, ["archive", "pull", "deploy@h:/src/", str(dest)])
    assert res.exit_code == 1


def test_pull_transport_failure_exits_two(tmp_path, monkeypatch):
    from cli.archive import command

    monkeypatch.setattr(command, "_run_rsync", lambda source, d: 23)
    res = CliRunner().invoke(app, ["archive", "pull", "deploy@h:/src/", str(tmp_path)])
    assert res.exit_code == 2


def test_pull_no_verify_skips_verification(tmp_path, monkeypatch):
    dest = tmp_path / "arch"
    dest.mkdir()
    d = dest / "engine-journal"
    d.mkdir(parents=True)
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(d / "snapshot.parquet")  # no .sha256 sidecar
    from cli.archive import command

    monkeypatch.setattr(command, "_run_rsync", lambda source, d: 0)
    res = CliRunner().invoke(app, ["archive", "pull", "--no-verify", "deploy@h:/src/", str(dest)])
    assert res.exit_code == 0
