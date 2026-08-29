"""VPS engine-journal retention (spec 00070, T0021).

The unit under test is the **shell script the `engine` role installs**
(`infra/ansible/roles/engine/files/zcrypto-engine-journal-prune.sh`), driven with `bash` over a
fixture journal tree — not a Python re-implementation. What deletes bytes on the trade-key host is
that file; a second implementation would only be a second thing to get wrong.

The load-bearing assertions are the NEGATIVE ones, and one of them is not about disk at all.
`cli/engine/cycle.py` derives each cycle's orders as a delta against the most recent journaled
cycle, located by globbing this tree; with no prior record every delta becomes the full target and
the engine rebuilds the whole book ("the shadow book starts flat"). So the prune must keep the
newest `retention_days` day-dirs REGARDLESS of age — the guard is inert in healthy operation and
is the only thing standing between a >60-day engine outage and a spurious book rebuild (spec
00070 D2).

Dates are taken from the directory NAME, never from mtime (D4): the name is the day's identity,
while an mtime is rewritten by any restore or rsync.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "infra/ansible/roles/engine/files/zcrypto-engine-journal-prune.sh"


def _day(root: Path, days_ago: int) -> Path:
    """Plant a realistic journal day-dir dated N days before today (UTC), with its cycle records."""
    name = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    d = root / name
    (d / "snapshots" / "cycle-00").mkdir(parents=True, exist_ok=True)
    (d / "cycle-00.json").write_text('{"cycle_ts": "x"}')
    (d / "orders.jsonl").write_text("{}\n")
    (d / "snapshots" / "cycle-00" / "BTC-240.parquet").write_bytes(b"snap")
    return d


# 14 here is a TEST parameter chosen to keep fixtures small -- it is deliberately NOT the deployed
# default (60, spec 00070). The script is parameterized; the deployed value is pinned separately by
# test_the_deployed_retention_matches_the_spec below.
def _prune(root: Path, days: str = "14", *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), str(root), days, *extra], capture_output=True, text=True, check=False)


def _rw_paths(rw: str) -> set[str]:
    """The paths ReadWritePaths actually grants.

    Substring over the raw line is blind to a longer sibling: `/var/lib/x-backup` contains
    `/var/lib/x`, so a typo'd unit reads as writable. The leading `-` is systemd's may-not-exist
    marker, not part of the path.
    """
    return {p.lstrip("-") for p in rw.removeprefix("ReadWritePaths=").split()}


def test_deletes_only_days_older_than_retention(tmp_path):
    old, edge, fresh = _day(tmp_path, 40), _day(tmp_path, 15), _day(tmp_path, 3)
    # 20 recent days so the keep-newest floor is satisfied and age is the only variable under test.
    for n in range(1, 21):
        _day(tmp_path, n)
    result = _prune(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not old.exists(), "a 40-day-old day must be pruned"
    assert not edge.exists(), "a 15-day-old day is beyond the 14-day window"
    assert fresh.exists(), "a 3-day-old day is inside the window"


@pytest.mark.parametrize("retention", ["14", "60"])
def test_keeps_the_newest_n_days_even_when_all_are_aged(tmp_path, retention):
    """D2, the load-bearing guard: an engine outage longer than the window ages out EVERY day. An
    age-only prune would empty the journal and the next cycle would rebuild the whole book flat.

    Parametrized over the DEPLOYED retention (60) as well as the small test default, because this
    is the case where the floor binds: a literal `14` hardcoded into the floor passes every
    fixed-at-14 test in this file and shows up only here.
    """
    n = int(retention)
    planted = [_day(tmp_path, m) for m in range(n + 10, n + 10 + n + 16)]  # all far beyond retention
    result = _prune(tmp_path, retention)
    assert result.returncode == 0, result.stderr
    survivors = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert len(survivors) == n, f"must keep the newest {n} regardless of age, kept {len(survivors)}"
    assert survivors == sorted(d.name for d in planted)[-n:], "the survivors must be the NEWEST n"


def test_never_touches_the_current_utc_day(tmp_path):
    today = _day(tmp_path, 0)
    for n in range(1, 21):
        _day(tmp_path, n)
    assert _prune(tmp_path).returncode == 0
    assert today.exists(), "the day being written must never be deleted"


@pytest.mark.parametrize("retention", ["14", "60"])
def test_a_day_exactly_at_the_retention_boundary_survives(tmp_path, retention):
    """The AGE condition, isolated from the keep-newest floor.

    15 consecutive days means exactly one candidate below the floor — the oldest, aged exactly
    `retention_days`. The cutoff is `today - 14` and the comparison is strictly-older, so that day
    must survive. This is the only shape where age decides anything the floor has not already
    decided: with 15 distinct days the oldest is necessarily >= 14 days old, so any fixture with
    more days makes the floor sufficient and leaves the cutoff untested.
    """
    n = int(retention)
    days = {m: _day(tmp_path, m) for m in range(n + 1)}  # ages 0..n
    result = _prune(tmp_path, retention)
    assert result.returncode == 0, result.stderr
    assert "deleted=0" in result.stdout, f"nothing is strictly older than the cutoff: {result.stdout}"
    assert days[n].exists(), "a day aged exactly retention_days is NOT strictly older than the cutoff"


def test_a_day_one_past_the_boundary_is_deleted(tmp_path):
    """The other side of the same comparison — together these pin the sense of `<` and prove the
    cutoff is evaluated at all."""
    days = {n: _day(tmp_path, n) for n in range(16)}  # ages 0..15
    result = _prune(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not days[15].exists(), "a day one past the window must go"
    assert days[14].exists(), "...but the boundary day itself stays"
    assert "deleted=1" in result.stdout, result.stdout


def test_the_regex_anchors_reject_names_that_merely_contain_a_date(tmp_path):
    """D3 calls this glob the entire safety argument, so mutate-test it rather than assert it.

    retention_days=1 leaves the single real day-dir protected by the floor and every stray a
    deletion candidate, so each anchor failure shows up as a deletion:
      - no trailing `$`      -> `2020-01-01.tmp` / `2020-01-03x` match and are swept
      - no leading `/`       -> `backup-2020-01-02` matches, and the real dir sorts ahead of it
                                into the candidate slot and is swept instead
      - no `-type d`         -> the plain FILE `2020-01-04` matches and is swept
    """
    real = _day(tmp_path, 40)
    affixed = [tmp_path / n for n in ("2020-01-01.tmp", "backup-2020-01-02", "2020-01-03x")]
    for d in affixed:
        d.mkdir()
        (d / "evidence").write_text("x")
    plain_file = tmp_path / "2020-01-04"
    plain_file.write_text("not a directory")

    result = _prune(tmp_path, "1")
    assert result.returncode == 0, result.stderr
    for d in affixed:
        assert d.exists(), f"{d.name} is not an ISO day-dir and must never be swept"
    assert plain_file.exists(), "a plain file is not a day-dir even when its name is a date"
    assert real.exists(), "the one genuine day-dir is the only match, so the floor protects it"


def test_ignores_anything_that_is_not_an_iso_day_dir(tmp_path):
    """An unexpected name means something else writes here — a reason to stop, not to sweep."""
    for n in range(1, 21):
        _day(tmp_path, n)
    stray_dir = tmp_path / "cache"
    stray_dir.mkdir()
    (stray_dir / "keep").write_text("x")
    stray_file = tmp_path / "README"
    stray_file.write_text("x")
    weird = tmp_path / "2026-07"  # partial date, must not match
    weird.mkdir()
    assert _prune(tmp_path).returncode == 0
    assert stray_dir.exists() and (stray_dir / "keep").exists()
    assert stray_file.exists()
    assert weird.exists()


def test_dry_run_deletes_nothing_but_reports(tmp_path):
    old = _day(tmp_path, 40)
    # Exactly 14 in-window days: satisfies the keep-newest floor while leaving `old` the sole
    # deletable candidate, so `deleted=1` isolates the one thing under test.
    for n in range(1, 15):
        _day(tmp_path, n)
    result = _prune(tmp_path, "14", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert old.exists(), "--dry-run must not delete"
    assert "deleted=1" in result.stdout, "it must still report what it WOULD delete"


def test_reports_a_structured_line(tmp_path):
    _day(tmp_path, 40)
    for n in range(1, 15):
        _day(tmp_path, n)
    out = _prune(tmp_path).stdout
    assert "zcrypto-engine-journal-prune:" in out
    assert "deleted=1" in out and "retention_days=14" in out and "kept=" in out


def test_the_published_file_is_readable_by_the_non_root_collector(tmp_path):
    """Alloy runs as the non-root zcrypto-alloy user, and `mv` PRESERVES mktemp's 0600 — so without
    an explicit chmod this .prom publishes root-only and the collector gets EACCES.

    This shipped broken: the retro-fix that made this unit pass --textfile again was inert on
    delivery, failing in exactly the silent mode T0100 exists to record, while the staleness alert
    shipped alongside it was structurally unable to surface the failure (the collector skips an
    unreadable file BEFORE stamping its mtime, so there is no series to go stale).
    """
    _day(tmp_path, 40)
    for n in range(1, 15):
        _day(tmp_path, n)
    prom = tmp_path.parent / "mode.prom"
    assert _prune(tmp_path, "14", "--textfile", str(prom)).returncode == 0
    mode = prom.stat().st_mode & 0o777
    assert mode == 0o644, f"published {oct(mode)}; a non-root collector cannot read it"


def test_every_published_series_is_admitted_by_the_keep_regex(tmp_path):
    """The allow-list has no `node_.*` wildcard, so a published-but-unadmitted series is dropped at
    the remote-write boundary and looks exactly like a producer that never ran (spec 00071 D2).
    Derived from what the script ACTUALLY emits rather than from a hand-kept list — that is how
    `oldest_day_age_seconds` came to be published and silently dropped."""
    _day(tmp_path, 40)
    for n in range(1, 15):
        _day(tmp_path, n)
    prom = tmp_path.parent / "admitted.prom"
    assert _prune(tmp_path, "14", "--textfile", str(prom)).returncode == 0
    emitted = {line.split()[0] for line in prom.read_text().splitlines() if line and not line.startswith("#")}

    alloy = (ROLE.parent / "capture/files/config.alloy").read_text()
    regex = next(line for line in alloy.splitlines() if line.strip().startswith("regex") and "node_load1" in line).split('"')[1]
    admitted = set(regex.split("|"))
    assert not (emitted - admitted), f"published but dropped at remote_write: {sorted(emitted - admitted)}"


def test_writes_a_textfile_metric_when_asked(tmp_path):
    _day(tmp_path, 40)
    for n in range(1, 15):
        _day(tmp_path, n)
    prom = tmp_path.parent / "prune.prom"
    assert _prune(tmp_path, "14", "--textfile", str(prom)).returncode == 0
    body = prom.read_text()
    assert "zcrypto_engine_journal_prune_deleted_days 1" in body
    assert "zcrypto_engine_journal_prune_kept_days" in body
    assert "zcrypto_engine_journal_prune_last_run_timestamp_seconds" in body


@pytest.mark.parametrize("bad", ["/", "/var", "/var/lib", "/usr", "/etc", "/home"])
def test_refuses_system_roots(tmp_path, bad):
    result = _prune(Path(bad))
    assert result.returncode == 2, "a system root must be refused before anything is deleted"
    assert "refusing" in result.stderr.lower()


@pytest.mark.parametrize("bad", ["0", "-1", "abc", ""])
def test_refuses_a_bad_retention(tmp_path, bad):
    _day(tmp_path, 40)
    assert _prune(tmp_path, bad).returncode == 2


def test_refuses_a_missing_journal_dir(tmp_path):
    result = _prune(tmp_path / "nope")
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()


def test_deletes_the_whole_day_never_a_partial(tmp_path):
    """The day is the unit the engine and the gate both reason about."""
    old = _day(tmp_path, 40)
    for n in range(1, 21):
        _day(tmp_path, n)
    assert _prune(tmp_path).returncode == 0
    assert not old.exists(), "the day dir and everything under it goes together"


# --- The systemd wiring ------------------------------------------------------------------------
# The script above is only correct if the unit invokes it the way it expects. A mismatch here is
# near-silent: the timer fires nightly, the oneshot fails, and nothing pages — the journal simply
# grows while the fleet looks healthy. These two guard the seam.

ROLE = Path(__file__).resolve().parents[1] / "infra/ansible/roles/engine"


def _role_vars() -> dict[str, str]:
    """Every role default the unit template interpolates, discovered from the template itself.

    Discovered rather than listed: a hardcoded list silently stops covering a variable the moment
    the template grows one, and this seam is the only thing pinning the unit to the role.
    """
    text = (ROLE / "defaults/main.yml").read_text()
    template = (ROLE / "templates/zcrypto-engine-journal-prune.service.j2").read_text()
    out = {}
    for var in sorted(set(re.findall(r"\{\{ (\w+) \}\}", template))):
        m = re.search(rf"^{var}:\s*(\S+)", text, re.M)
        assert m, f"{var} is used by the unit but has no default in roles/engine/defaults/main.yml"
        out[var] = m.group(1).strip('"')
    return out


def _rendered_unit() -> str:
    unit = (ROLE / "templates/zcrypto-engine-journal-prune.service.j2").read_text()
    for key, value in _role_vars().items():
        unit = unit.replace("{{ " + key + " }}", value)
    assert "{{" not in unit, f"an unsubstituted variable remains: {unit}"
    return unit


def test_the_unit_invokes_the_script_the_role_installs_with_the_argument_order_it_expects():
    exec_start = next(line for line in _rendered_unit().splitlines() if line.startswith("ExecStart="))
    binary, journal_dir, days, *rest = exec_start.removeprefix("ExecStart=").split()

    install_dest = next(
        line.strip()
        for line in (ROLE / "tasks/main.yml").read_text().splitlines()
        if line.strip().startswith("dest:") and "zcrypto-engine-journal-prune" in line
    )
    assert install_dest.split(":", 1)[1].strip() == binary, f"the unit runs {binary}, the role installs {install_dest}"

    assert journal_dir == f"{_role_vars()['engine_state_dir']}/journal"
    assert days == _role_vars()["engine_journal_retention_days"]
    # Positional order is <journal-dir> <retention-days>: swapped, the retention parse rejects a
    # path and the unit fails closed rather than sweeping with a nonsense window.
    assert _prune(Path("/nonexistent"), days).returncode == 2
    # The guard stays, its allow-list grows by exactly the one flag T0100 added. Anything else is
    # an argument nobody reasoned about reaching a script that deletes bytes on the trade-key host.
    assert rest[:1] == ["--textfile"], f"unexpected argument: {rest}"
    assert len(rest) == 2, f"--textfile takes exactly one path: {rest}"


def test_protectsystem_strict_still_permits_writing_the_journal_dir():
    """ProtectSystem=strict mounts /usr and /var read-only; without the ReadWritePaths escape the
    prune cannot delete anything it correctly identified."""
    unit = _rendered_unit()
    assert any(l.strip() == "ProtectSystem=strict" for l in unit.splitlines())
    journal = f"{_role_vars()['engine_state_dir']}/journal"
    rw = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
    assert journal in _rw_paths(rw), f"{journal} is not writable under ProtectSystem=strict: {rw}"


def test_the_prune_publishes_into_the_directory_alloy_actually_scrapes():
    """T0100's defect in one assertion: a producer writing where no reader looks.

    This unit originally passed no --textfile at all, because these hosts ran no textfile collector.
    That was true, and the wrong conclusion — the fix was to add the reader. Three paths must agree
    or the metric silently goes nowhere: the engine role's dir, the capture role's dir (same host),
    and the container path Alloy's collector globs.
    """
    unit = _rendered_unit()
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "--textfile" in exec_start, "the prune must publish a .prom — a oneshot has no /metrics endpoint to scrape"
    out = exec_start.split("--textfile", 1)[1].strip().split()[0]
    host_dir = str(Path(out).parent)

    capture_defaults = (ROLE.parent / "capture/defaults/main.yml").read_text()
    capture_dir = re.search(r"^capture_textfile_dir:\s*(\S+)", capture_defaults, re.M).group(1)
    assert host_dir == capture_dir, f"engine writes {host_dir}, capture role declares {capture_dir} — same host, must agree"

    alloy = (ROLE.parent / "capture/files/config.alloy").read_text()
    directory = next(line for line in alloy.splitlines() if line.strip().startswith("directory")).split('"')[1]
    assert directory == f"/host/root{host_dir}", f"prune writes {host_dir}, Alloy reads {directory} — a .prom nobody scrapes"

    rw = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
    assert host_dir in _rw_paths(rw), f"ProtectSystem=strict would block the write: {rw}"


def test_the_deployed_retention_matches_the_spec():
    """The retention window is an owner ruling with safety consequences (how long a day survives on
    the VPS, and how deep the keep-newest floor is), not a tunable. Pin it so a drive-by edit to the
    role default has to change this line and confront the spec."""
    assert _role_vars()["engine_journal_retention_days"] == "60", (
        "spec 00070 records 60 days (owner ruling 2026-07-26) -- update the spec, not just the default"
    )


def _field(out: str, name: str) -> str:
    return re.search(rf"{name}=(\S+)", out).group(1)


def test_a_dry_run_publishes_no_metric(tmp_path):
    """A dry run's `kept` counts would-delete entries, so publishing it renders a pruned journal
    that was never pruned. The log line can say "(dry-run)"; a .prom the collector scrapes cannot."""
    _day(tmp_path, 40)
    for n in range(1, 15):
        _day(tmp_path, n)
    prom = tmp_path.parent / "dry.prom"
    assert _prune(tmp_path, "14", "--dry-run", "--textfile", str(prom)).returncode == 0
    assert not prom.exists(), "a dry run must not publish metrics for deletions it did not make"
    assert not list(tmp_path.parent.glob("dry.prom.*")), "and must leave no mktemp turd behind"


@pytest.mark.parametrize("zero_prefixed,plain", [("014", "14"), ("060", "60")])
def test_a_zero_prefixed_retention_is_decimal_not_octal(tmp_path, zero_prefixed, plain):
    """`$(( 014 ))` is octal 12 in bash while `date -d "014 days ago"` reads decimal 14 — without a
    `10#` prefix the floor and the cutoff silently disagree, protecting fewer days than asked.

    Only visible when the floor binds, which is why every day planted here is far beyond retention.
    """
    n = int(plain)
    for m in range(200, 200 + n + 20):
        _day(tmp_path, m)
    prefixed = _prune(tmp_path, zero_prefixed, "--dry-run")
    assert prefixed.returncode == 0, prefixed.stderr
    plain_run = _prune(tmp_path, plain, "--dry-run")
    assert _field(prefixed.stdout, "kept") == _field(plain_run.stdout, "kept") == str(n), (
        f"{zero_prefixed} must mean {n}, not octal: {prefixed.stdout}"
    )
