"""The host clock-skew exporter (spec 00103 D4, T0037).

A clock leading the true hour lets a bogus exchange timestamp close an archive hour early, and no
clock-referenced counter can see it (spec 00103 D1b). This exporter is that residual's ONLY detector.

The unit under test is the **shell script the capture role installs**, driven with `bash` over a
fixture `chronyc`, not a Python re-implementation. Three things carry the weight, and none of them is
the happy path:

- Both series must be emitted on EVERY run. An absent series is indistinguishable from a dead
  exporter.
- A chronyc that is missing, fails, or answers in an unrecognised shape must publish `NaN`, never a
  fabricated `0` — a 0 offset reads as a perfectly disciplined clock.
- The sign says which way the clock is wrong, and only one direction destroys data. `fast` (ahead)
  is positive.
"""

from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/capture"
SCRIPT = ROLE / "files/zcrypto-clock-offset.sh"

TRACKING = """Reference ID    : C0248F82 (ntp1.example.net)
Stratum         : 3
Ref time (UTC)  : Sat Aug 29 09:12:31 2026
System time     : {magnitude} seconds {direction} of NTP time
Last offset     : -0.000004567 seconds
RMS offset      : 0.000010000 seconds
Frequency       : 12.345 ppm slow
Residual freq   : +0.001 ppm
Skew            : 0.123 ppm
Root delay      : 0.012345678 seconds
Root dispersion : 0.001234567 seconds
Update interval : 64.2 seconds
Leap status     : {leap}
"""


def _chronyc(tmp_path: Path, stdout: str, *, exit_code: int = 0) -> Path:
    """A stand-in for /usr/bin/chronyc that replays a fixture `tracking` report."""
    path = tmp_path / "chronyc"
    path.write_text(f"#!/usr/bin/env bash\ncat <<'FIXTURE'\n{stdout}FIXTURE\nexit {exit_code}\n")
    path.chmod(0o755)
    return path


def _run(chronyc: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), str(chronyc), str(out)], capture_output=True, text=True, check=False)


def _series(prom: Path) -> dict[str, float]:
    """Parse the .prom into {name: value}, ignoring HELP/TYPE lines."""
    out = {}
    for line in prom.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, _, value = line.rpartition(" ")
        out[name.strip()] = float(value)
    return out


def _emit(tmp_path: Path, *, magnitude: str = "0.000012345", direction: str = "fast", leap: str = "Normal") -> dict[str, float]:
    prom = tmp_path / "clock-offset.prom"
    result = _run(_chronyc(tmp_path, TRACKING.format(magnitude=magnitude, direction=direction, leap=leap)), prom)
    assert result.returncode == 0, result.stderr
    return _series(prom)


def _installed_dests(role_tasks_yaml: str) -> set[str]:
    """Every `dest:` the role actually installs, parsed.

    A substring check against the file's text matches a comment or a fail_msg naming the path, and
    is also blind to a SUFFIXED dest -- `.../zcrypto-reboot-check-TYPO` contains the real name.
    """
    return {
        str(v).strip()
        for task in yaml.safe_load(role_tasks_yaml) or []
        for mod in task.values()
        if isinstance(mod, dict) and (v := mod.get("dest"))
    }


def test_a_healthy_clock_emits_both_series_rather_than_staying_silent(tmp_path):
    """The load-bearing positive. Publishing nothing while all is well leaves the alert unable to
    tell "the clock is fine" from "the exporter died"."""
    series = _emit(tmp_path)
    assert series == pytest.approx({"zcrypto_clock_offset_seconds": 1.2345e-05, "zcrypto_clock_synchronised": 1.0})


def test_a_clock_running_ahead_is_positive_and_one_running_behind_is_negative(tmp_path):
    """The sign is the whole diagnosis: a clock AHEAD is the one that truncates archive hours, and
    reading the direction backwards would report the destructive case as the harmless one."""
    assert _emit(tmp_path, magnitude="42.500000000", direction="fast")["zcrypto_clock_offset_seconds"] == 42.5
    assert _emit(tmp_path, magnitude="42.500000000", direction="slow")["zcrypto_clock_offset_seconds"] == -42.5


@pytest.mark.parametrize(
    ("leap", "synchronised"),
    [("Normal", 1.0), ("Insert leap second", 1.0), ("Delete leap second", 1.0), ("Not synchronised", 0.0)],
)
def test_the_flag_follows_the_leap_status(tmp_path, leap, synchronised):
    """An unsynchronised host is free to drift into the destructive range, so it pages on its own
    leg — and a pending leap second is a disciplined clock, not an outage."""
    series = _emit(tmp_path, leap=leap)
    assert series["zcrypto_clock_synchronised"] == synchronised
    assert not math.isnan(series["zcrypto_clock_offset_seconds"]), "an unsynchronised reading still carries a measured offset"


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param(lambda p: p / "no-chronyc-here", id="missing"),
        pytest.param(lambda p: _chronyc(p, "", exit_code=1), id="fails"),
        pytest.param(lambda p: _chronyc(p, "506 Cannot talk to daemon\n"), id="unrecognised"),
    ],
)
def test_an_unreadable_clock_publishes_unknown_rather_than_a_fabricated_zero(tmp_path, broken):
    """`0` would read as a perfectly disciplined clock and silence as a dead exporter; NaN is
    neither. PromQL comparisons against NaN are false, so the offset threshold cannot fire on it —
    the paging is left to the synchronisation flag, which reads 0 here."""
    prom = tmp_path / "clock-offset.prom"
    result = _run(broken(tmp_path), prom)
    assert result.returncode == 0, result.stderr
    series = _series(prom)
    assert math.isnan(series["zcrypto_clock_offset_seconds"]), series
    assert series["zcrypto_clock_synchronised"] == 0.0


def test_the_prom_is_well_formed_for_the_collector(tmp_path):
    prom = tmp_path / "clock-offset.prom"
    assert _run(_chronyc(tmp_path, TRACKING.format(magnitude="0.1", direction="fast", leap="Normal")), prom).returncode == 0
    body = prom.read_text()
    for metric in ("zcrypto_clock_offset_seconds", "zcrypto_clock_synchronised"):
        assert f"# HELP {metric} " in body
        assert f"# TYPE {metric} gauge" in body
    assert body.endswith("\n"), "a .prom without a trailing newline can trip the parser"


def test_the_write_is_atomic_leaving_no_partial_file(tmp_path):
    """The collector globs this directory continuously; it must never read a half-written file.

    Asserted by INODE, not by the absence of temp files: a truncate-in-place rewrite (`> "$out"`)
    leaves no temp file either, so the no-turd check alone passes precisely *because* the safety
    mechanism was removed. A rename gives a new inode; an in-place rewrite keeps it.
    """
    prom = tmp_path / "clock-offset.prom"
    chronyc = _chronyc(tmp_path, TRACKING.format(magnitude="0.1", direction="fast", leap="Normal"))
    assert _run(chronyc, prom).returncode == 0
    first = prom.stat().st_ino
    assert _run(chronyc, prom).returncode == 0
    assert prom.stat().st_ino != first, (
        "the output inode did not change — the script rewrote in place rather than renaming over, "
        "so the collector can read a partially-written file"
    )
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith("clock-offset.prom.")]
    assert not leftovers, f"temp file left behind: {leftovers}"


def test_the_published_file_is_readable_by_the_non_root_collector(tmp_path):
    """Alloy runs as the non-root zcrypto-alloy user. mktemp creates 0600 and `mv` PRESERVES it, so
    without an explicit chmod the .prom is published root-only and the collector gets EACCES —
    metrics silently absent, which is exactly the T0100 failure mode."""
    prom = tmp_path / "clock-offset.prom"
    assert _run(_chronyc(tmp_path, TRACKING.format(magnitude="0.1", direction="fast", leap="Normal")), prom).returncode == 0
    mode = prom.stat().st_mode & 0o777
    assert mode == 0o644, f"published {oct(mode)}; a non-root collector cannot read it"


def test_an_unwritable_destination_fails_loudly(tmp_path):
    """A silent failure here recreates the very blindness this whole change exists to fix."""
    chronyc = _chronyc(tmp_path, TRACKING.format(magnitude="0.1", direction="fast", leap="Normal"))
    result = _run(chronyc, tmp_path / "no-such-dir" / "clock-offset.prom")
    assert result.returncode != 0
    assert result.stderr.strip(), "it must say why, not just exit nonzero"


def test_missing_arguments_are_refused():
    assert subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True).returncode == 2


# --- The systemd + ansible seam -----------------------------------------------------------------
# A rename or an argument-order change fails in a oneshot nobody watches, and the metric it stops
# publishing is this residual's only detector.


def _rendered_unit() -> str:
    unit = (ROLE / "templates/zcrypto-clock-offset.service.j2").read_text()
    defaults = (ROLE / "defaults/main.yml").read_text()
    for var in set(re.findall(r"\{\{ (\w+) \}\}", unit)):
        m = re.search(rf"^{var}:\s*(\S+)", defaults, re.M)
        assert m, f"{var} has no default in roles/capture/defaults/main.yml"
        unit = unit.replace("{{ " + var + " }}", m.group(1).strip('"'))
    assert "{{" not in unit, f"unsubstituted variable remains: {unit}"
    return unit


def _exec_start() -> list[str]:
    return next(line for line in _rendered_unit().splitlines() if line.startswith("ExecStart=")).removeprefix("ExecStart=").split()


def test_the_unit_runs_the_installed_script_with_the_expected_arguments():
    binary, chronyc, out = _exec_start()
    tasks = (ROLE / "tasks/main.yml").read_text()
    assert binary in _installed_dests(tasks), f"the unit runs {binary}, which the role does not install"
    assert chronyc.startswith("/"), f"chronyc must be an absolute path, not a PATH lookup: {chronyc}"
    assert out.endswith(".prom"), out


def test_the_unit_writes_into_the_directory_alloy_actually_scrapes():
    """The defect T0100 records is a producer writing where no reader looks. This pins the two ends
    together: the unit's output path and the collector's `directory` must agree."""
    host_dir = str(Path(_exec_start()[-1]).parent)
    alloy = (ROLE / "files/config.alloy").read_text()
    # Match the ASSIGNMENT, never any line mentioning the key: a comment naming it must not be
    # selectable, or the assertion compares against prose.
    set_collectors = next(line for line in alloy.splitlines() if line.strip().startswith("set_collectors"))
    assert '"textfile"' in set_collectors, f"the textfile collector is not enabled, so the block is inert: {set_collectors.strip()}"
    directory = next(line for line in alloy.splitlines() if line.strip().startswith("directory")).split('"')[1]
    # Alloy sees the host root at /host/root; the unit writes on the host itself.
    assert directory == f"/host/root{host_dir}", f"unit writes {host_dir}, collector reads {directory} — a .prom nobody scrapes"


def test_every_series_the_script_emits_is_admitted_by_the_capture_keep_regex(tmp_path):
    """The T0051 trap: the keep is an allow-list, so a name it does not carry is dropped at
    remote_write and the alert watching it reads no data forever — rendering identically to healthy.
    The names come from an actual run, not a literal, so a rename in the script is caught here."""
    prom = tmp_path / "clock-offset.prom"
    assert _run(_chronyc(tmp_path, TRACKING.format(magnitude="0.1", direction="fast", leap="Normal")), prom).returncode == 0
    alloy = (ROLE / "files/config.alloy").read_text()
    keep = next(ln for ln in alloy.splitlines() if ln.strip().startswith("regex") and "node_load1" in ln).split('"')[1].split("|")
    missing = [name for name in _series(prom) if name not in keep]
    assert not missing, f"{missing} are written to the textfile dir but dropped at remote_write"


def test_protectsystem_strict_still_permits_the_two_writes_the_probe_needs():
    """`chronyc` binds its own reply socket beside chronyd's in /run/chrony, so a read-only /run
    breaks the READ as well as the publish — and the exporter would then report an unknown offset
    forever while the unit converged green."""
    unit = _rendered_unit()
    assert any(l.strip() == "ProtectSystem=strict" for l in unit.splitlines())
    rw = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
    assert str(Path(_exec_start()[-1]).parent) in rw, f"the output directory is not writable: {rw}"
    assert "/run/chrony" in rw, f"chronyc cannot create its client socket: {rw}"


def test_only_the_timer_is_enabled_not_the_oneshot():
    """Enabling the oneshot as well would probe on every boot."""
    import yaml

    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    enabled = [
        t["ansible.builtin.systemd_service"]["name"]
        for t in _flatten(tasks)
        if "ansible.builtin.systemd_service" in t and t["ansible.builtin.systemd_service"].get("enabled")
    ]
    assert "zcrypto-clock-offset.timer" in enabled, f"the timer is not enabled, so nothing ever runs the probe: {enabled}"
    assert "zcrypto-clock-offset.service" not in enabled, f"the oneshot must not be enabled — it would run on every boot: {enabled}"


def _flatten(tasks):
    """Task lists nest inside `block:`; a flat scan would miss anything inside one."""
    for t in tasks or []:
        if not isinstance(t, dict):
            continue
        yield t
        for key in ("block", "rescue", "always"):
            if key in t:
                yield from _flatten(t[key])


def test_the_timer_actually_repeats():
    """Removing OnUnitActiveSec leaves a timer that fires once at boot and never again — converging
    green, publishing an offset that freezes at its first value."""
    timer = (ROLE / "files/zcrypto-clock-offset.timer").read_text()
    assert any(l.strip().startswith("OnUnitActiveSec=") for l in timer.splitlines()), (
        "without a repeat interval this fires once per boot"
    )
    assert any(l.strip().startswith("OnBootSec=") for l in timer.splitlines()), (
        "without a boot trigger the gauge is stale until the first interval"
    )
    assert any(l.strip() == "Unit=zcrypto-clock-offset.service" for l in timer.splitlines())
