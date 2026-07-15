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


def test_verify_tree_skips_held_spills(tmp_path):
    # A held-spill (`<HH>.held####.parquet`) is quarantine the capture writer kept for rows whose
    # hour was never quorum-confirmed (T0037): not a final, never manifested — verify must not
    # count it failed, or every stop with an unconfirmed hold would page as archive corruption.
    d = tmp_path / "BTC/EUR/trades/2026/07/12"
    d.mkdir(parents=True)
    pl.DataFrame({"x": [1]}).write_parquet(d / "12.held0000.parquet")
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert r.checked == 0 and r.failed == ()


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


def test_pull_missing_ssh_key_exits_two(tmp_path, monkeypatch):
    # No _run_rsync monkeypatch: exercise the real guard. With ARCHIVE_SSH_KEY unset the ssh
    # transport can't start, so it must exit 2 (transport class) -- never the bare KeyError that
    # Click would surface as exit 1, colliding with the hash-mismatch code.
    monkeypatch.delenv("ARCHIVE_SSH_KEY", raising=False)
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


# --- T0038: prune stale parts after a verified final -------------------------------------------


def _part(root: Path, pair: str, kind: str, hour: str, idx: int) -> Path:
    d = root / pair / kind / "2026" / "07" / "12"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{hour}.part{idx:04d}.parquet"
    p.write_bytes(b"partial")
    return p


def test_verify_tree_reports_which_finals_verified() -> None:
    """`verified` is the set of OK final paths -- the authority prune uses to know what is safe to remove."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seg(root, "BTC/EUR", "book", "10")
        _seg(root, "BTC/EUR", "book", "11", corrupt=True)
        r = verify_tree(root, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
        assert any("10.parquet" in v for v in r.verified)
        assert not any("11.parquet" in v for v in r.verified), "a failed final must NOT be listed as verified"


def test_prune_stale_parts_removes_parts_of_a_verified_final_only(tmp_path: Path) -> None:
    from cli.archive.pull import prune_stale_parts, verify_tree

    # hour 10: verified final + 3 stale parts -> parts pruned, final kept
    _seg(tmp_path, "BTC/EUR", "book", "10")
    for i in range(3):
        _part(tmp_path, "BTC/EUR", "book", "10", i)
    # hour 12: parts but NO final (live/unpublished hour) -> left completely alone
    live = [_part(tmp_path, "BTC/EUR", "book", "12", i) for i in range(2)]

    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    hours, parts = prune_stale_parts(r.verified)

    d = tmp_path / "BTC/EUR/book/2026/07/12"
    assert (d / "10.parquet").exists(), "the verified final must be kept"
    assert list(d.glob("10.part*.parquet")) == [], "stale parts of a verified hour must be gone"
    assert all(p.exists() for p in live), "parts of an hour with NO verified final must be untouched"
    assert (hours, parts) == (1, 3)


def test_prune_leaves_parts_of_an_UNVERIFIABLE_final_alone(tmp_path: Path) -> None:
    """A corrupt final does not verify, so its parts are the only intact copy -- never delete them."""
    from cli.archive.pull import prune_stale_parts, verify_tree

    _seg(tmp_path, "BTC/EUR", "book", "10", corrupt=True)
    _part(tmp_path, "BTC/EUR", "book", "10", 0)

    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    hours, parts = prune_stale_parts(r.verified)

    d = tmp_path / "BTC/EUR/book/2026/07/12"
    assert (d / "10.part0000.parquet").exists(), "parts of an unverifiable final must be kept"
    assert (hours, parts) == (0, 0)


def test_prune_never_touches_a_held_spill_beside_a_verified_final(tmp_path: Path) -> None:
    """A `.held` file is a quarantined spill -- potentially the only copy of some rows. The glob keys
    on `.part`, so it must never match `.held`; this pins that a widening of the glob would be caught."""
    from cli.archive.pull import prune_stale_parts, verify_tree

    _seg(tmp_path, "BTC/EUR", "book", "10")
    _part(tmp_path, "BTC/EUR", "book", "10", 0)
    d = tmp_path / "BTC/EUR/book/2026/07/12"
    held = d / "10.held0000.parquet"
    held.write_bytes(b"quarantined spill")

    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    prune_stale_parts(r.verified)

    assert held.exists(), "a held-spill must never be pruned"
    assert list(d.glob("10.part*.parquet")) == [], "the real stale part was still pruned"


def test_prune_leaves_parts_of_an_ERRORING_final_alone(tmp_path: Path) -> None:
    """A final whose manifest is MISSING errors (CaptureError), not just mismatches -- it must land in
    `failed`, never `verified`, so its parts (the only intact copy) are untouched."""
    from cli.archive.pull import prune_stale_parts, verify_tree

    _seg(tmp_path, "BTC/EUR", "book", "10")
    (tmp_path / "BTC/EUR/book/2026/07/12/10.parquet.sha256").unlink()  # remove the manifest -> errors
    _part(tmp_path, "BTC/EUR", "book", "10", 0)

    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert not any("10.parquet" in v for v in r.verified), "an erroring final must not be verified"
    hours, parts = prune_stale_parts(r.verified)

    d = tmp_path / "BTC/EUR/book/2026/07/12"
    assert (d / "10.part0000.parquet").exists(), "parts of an erroring final must be kept"
    assert (hours, parts) == (0, 0)


def test_prune_leaves_a_nonstandard_partlike_name_alone(tmp_path: Path) -> None:
    """A name the writer would never emit -- an rsync artefact / hand-made backup -- must be left, not
    swept, even beside a verified final (strict `<HH>.part<digits>.parquet` only)."""
    from cli.archive.pull import prune_stale_parts, verify_tree

    _seg(tmp_path, "BTC/EUR", "book", "10")
    _part(tmp_path, "BTC/EUR", "book", "10", 0)  # a real stale part -> pruned
    d = tmp_path / "BTC/EUR/book/2026/07/12"
    weird = d / "10.part0000-copy.parquet"
    weird.write_bytes(b"a human backup")

    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    hours, parts = prune_stale_parts(r.verified)

    assert weird.exists(), "a non-daemon part-like name must be left alone"
    assert not (d / "10.part0000.parquet").exists(), "the real stale part was still pruned"
    assert (hours, parts) == (1, 1)


def test_prune_survives_an_unlink_failure_without_escaping(tmp_path: Path, monkeypatch) -> None:
    """An unlink failure (permissions, a concurrent process) must be caught, not escape as an
    unhandled exception -- which would skip the pull command's failed-verify -> exit-1 path. The part
    simply stays and prune reports it as not-pruned."""
    from pathlib import Path as _P

    from cli.archive.pull import prune_stale_parts, verify_tree

    _seg(tmp_path, "BTC/EUR", "book", "10")
    _part(tmp_path, "BTC/EUR", "book", "10", 0)

    def _boom(self, *a, **k):
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(_P, "unlink", _boom)
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    hours, parts = prune_stale_parts(r.verified)  # must not raise

    assert (hours, parts) == (0, 0), "a failed unlink is not counted as pruned"
    assert (tmp_path / "BTC/EUR/book/2026/07/12/10.part0000.parquet").exists(), "the part stays on a failed delete"
