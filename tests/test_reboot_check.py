"""The attended-reboot detector (spec 00071, T0027).

Flipping `Automatic-Reboot` to false creates a new gap: a kernel flag nobody notices. This timer is
what closes it, so the harness is part of the decision, not an optional extra.

As with `tests/test_engine_journal_prune.py`, the unit under test is the **shell script the capture
role installs**, driven with `bash` over a fixture directory — not a Python re-implementation.

Two things carry most of the weight here, and neither is about the happy path:

- The script must read **`/run`**, not `/var/run`. `/var/run` is a compatibility symlink; it works
  today, but the flag's real home is `/run` and the indirection is exactly the kind of thing that
  breaks silently under a hardened unit's namespace.
- It must publish `0` explicitly, never "no file". An absent series is indistinguishable from a
  dead exporter, so "no reboot pending" has to be a value, not a silence.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/capture"
SCRIPT = ROLE / "files/zcrypto-reboot-check.sh"


def _run(flag_path: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), str(flag_path), str(out)], capture_output=True, text=True, check=False)


def _series(prom: Path) -> dict[str, float]:
    """Parse the .prom into {name: value}, ignoring HELP/TYPE lines."""
    out = {}
    for line in prom.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, _, value = line.rpartition(" ")
        out[name.strip()] = float(value)
    return out


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


def _rw_paths(rw: str) -> set[str]:
    """The paths ReadWritePaths actually grants.

    Substring over the raw line is blind to a longer sibling: `/var/lib/x-backup` contains
    `/var/lib/x`, so a typo'd unit reads as writable. The leading `-` is systemd's may-not-exist
    marker, not part of the path.
    """
    return {p.lstrip("-") for p in rw.removeprefix("ReadWritePaths=").split()}


def test_publishes_1_when_the_flag_is_present(tmp_path):
    flag = tmp_path / "reboot-required"
    flag.write_text("*** System restart required ***\n")
    prom = tmp_path / "reboot.prom"
    result = _run(flag, prom)
    assert result.returncode == 0, result.stderr
    assert _series(prom)["node_reboot_required"] == 1.0


def test_publishes_0_rather_than_nothing_when_no_reboot_is_pending(tmp_path):
    """The load-bearing negative. An ABSENT series looks identical to a dead exporter, so the
    healthy state must be an explicit 0 — otherwise the alert can never distinguish "fine" from
    "this host stopped reporting"."""
    prom = tmp_path / "reboot.prom"
    result = _run(tmp_path / "definitely-not-here", prom)
    assert result.returncode == 0, result.stderr
    assert _series(prom)["node_reboot_required"] == 0.0


def test_the_flag_going_away_flips_the_gauge_back(tmp_path):
    """After the human reboots, the alert must resolve on its own."""
    flag = tmp_path / "reboot-required"
    flag.write_text("x")
    prom = tmp_path / "reboot.prom"
    _run(flag, prom)
    assert _series(prom)["node_reboot_required"] == 1.0
    flag.unlink()
    _run(flag, prom)
    assert _series(prom)["node_reboot_required"] == 0.0


def test_the_prom_is_well_formed_for_the_collector(tmp_path):
    prom = tmp_path / "reboot.prom"
    _run(tmp_path / "nope", prom)
    body = prom.read_text()
    assert "# HELP node_reboot_required " in body
    assert "# TYPE node_reboot_required gauge" in body
    assert body.endswith("\n"), "a .prom without a trailing newline can trip the parser"


def test_the_write_is_atomic_leaving_no_partial_file(tmp_path):
    """The collector globs this directory continuously; it must never read a half-written file.

    Asserted by INODE, not by the absence of temp files: a truncate-in-place rewrite (`> "$out"`)
    leaves no temp file either, so the no-turd check alone passes precisely *because* the safety
    mechanism was removed. A rename gives a new inode; an in-place rewrite keeps it.
    """
    prom = tmp_path / "reboot.prom"
    assert _run(tmp_path / "nope", prom).returncode == 0
    first = prom.stat().st_ino
    assert _run(tmp_path / "nope", prom).returncode == 0
    assert prom.stat().st_ino != first, (
        "the output inode did not change — the script rewrote in place rather than renaming over, "
        "so the collector can read a partially-written file"
    )
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith("reboot.prom.")]
    assert not leftovers, f"temp file left behind: {leftovers}"


def test_the_published_file_is_readable_by_the_non_root_collector(tmp_path):
    """Alloy runs as the non-root zcrypto-alloy user. mktemp creates 0600 and `mv` PRESERVES it, so
    without an explicit chmod the .prom is published root-only and the collector gets EACCES —
    metrics silently absent, which is exactly the T0100 failure mode. This is not hypothetical: the
    sibling journal-prune script shipped with precisely this bug and a review caught it.
    """
    prom = tmp_path / "reboot.prom"
    assert _run(tmp_path / "nope", prom).returncode == 0
    mode = prom.stat().st_mode & 0o777
    assert mode == 0o644, f"published {oct(mode)}; a non-root collector cannot read it"


def test_an_unwritable_destination_fails_loudly(tmp_path):
    """A silent failure here recreates the very blindness this whole change exists to fix."""
    result = _run(tmp_path / "nope", tmp_path / "no-such-dir" / "reboot.prom")
    assert result.returncode != 0
    assert result.stderr.strip(), "it must say why, not just exit nonzero"


def test_missing_arguments_are_refused(tmp_path):
    assert subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True).returncode == 2


# --- The systemd + ansible seam -----------------------------------------------------------------
# Same reasoning as the journal prune's seam test: a rename or an argument-order change fails
# nightly in a oneshot nobody watches.


def _rendered_unit() -> str:
    import re

    unit = (ROLE / "templates/zcrypto-reboot-check.service.j2").read_text()
    defaults = (ROLE / "defaults/main.yml").read_text()
    for var in set(re.findall(r"\{\{ (\w+) \}\}", unit)):
        m = re.search(rf"^{var}:\s*(\S+)", defaults, re.M)
        assert m, f"{var} has no default in roles/capture/defaults/main.yml"
        unit = unit.replace("{{ " + var + " }}", m.group(1).strip('"'))
    assert "{{" not in unit, f"unsubstituted variable remains: {unit}"
    return unit


def test_the_unit_runs_the_installed_script_with_the_expected_arguments():
    exec_start = next(line for line in _rendered_unit().splitlines() if line.startswith("ExecStart="))
    binary, flag, out = exec_start.removeprefix("ExecStart=").split()

    tasks = (ROLE / "tasks/main.yml").read_text()
    assert binary in _installed_dests(tasks), f"the unit runs {binary}, which the role does not install"
    assert flag == "/run/reboot-required", f"must read /run, not the /var/run compatibility symlink — got {flag}"
    assert out.endswith(".prom"), out


def test_the_unit_writes_into_the_directory_alloy_actually_scrapes():
    """The defect T0100 records is a producer writing where no reader looks. This pins the two ends
    together: the unit's output path and the collector's `directory` must agree."""
    out = next(line for line in _rendered_unit().splitlines() if line.startswith("ExecStart=")).split()[-1]
    host_dir = str(Path(out).parent)

    alloy = (ROLE / "files/config.alloy").read_text()
    # The directory agreeing is necessary but NOT sufficient: dropping "textfile" from
    # set_collectors leaves the block orphaned and the collector off, with the paths still matching.
    # Match the ASSIGNMENT, never any line mentioning the key: a comment naming it must not be
    # selectable, or the assertion compares against prose and passes or fails on the wrong text.
    set_collectors = next(line for line in alloy.splitlines() if line.strip().startswith("set_collectors"))
    # config-selector-ok: the needle carries both quotes, so "textfiles" cannot satisfy it
    assert '"textfile"' in set_collectors, f"the textfile collector is not enabled, so the block is inert: {set_collectors.strip()}"
    directory = next(line for line in alloy.splitlines() if line.strip().startswith("directory")).split('"')[1]
    # Alloy sees the host root at /host/root; the unit writes on the host itself.
    assert directory == f"/host/root{host_dir}", f"unit writes {host_dir}, collector reads {directory} — a .prom nobody scrapes"


def test_protectsystem_strict_still_permits_writing_the_textfile_dir():
    unit = _rendered_unit()
    assert any(l.strip() == "ProtectSystem=strict" for l in unit.splitlines())
    out = next(line for line in unit.splitlines() if line.startswith("ExecStart=")).split()[-1]
    rw = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
    assert str(Path(out).parent) in _rw_paths(rw), f"{out} is not writable under ProtectSystem=strict: {rw}"


def test_only_the_timer_is_enabled_not_the_oneshot():
    """Enabling the oneshot as well would prune/probe on every boot.

    The earlier form of this test split on "systemd_service" and inspected only [-1] — the region
    after the LAST of three occurrences in this file, which does not contain the reboot-check task
    at all. It passed without ever looking at the thing it named.
    """
    import yaml

    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    enabled = [
        t["ansible.builtin.systemd_service"]["name"]
        for t in _flatten(tasks)
        if "ansible.builtin.systemd_service" in t and t["ansible.builtin.systemd_service"].get("enabled")
    ]
    assert "zcrypto-reboot-check.timer" in enabled, f"the timer is not enabled: {enabled}"
    assert "zcrypto-reboot-check.service" not in enabled, f"the oneshot must not be enabled — it would run on every boot: {enabled}"


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
    """Content coverage for the .timer file, which nothing parsed before: removing OnUnitActiveSec
    leaves a timer that fires once at boot and never again — converging green, publishing a gauge
    that freezes at its first value."""
    timer = (ROLE / "files/zcrypto-reboot-check.timer").read_text()
    assert any(l.strip().startswith("OnUnitActiveSec=") for l in timer.splitlines()), (
        "without a repeat interval this fires once per boot"
    )
    assert any(l.strip().startswith("OnBootSec=") for l in timer.splitlines()), (
        "without a boot trigger the gauge is stale until the first interval"
    )
    assert any(l.strip() == "Unit=zcrypto-reboot-check.service" for l in timer.splitlines())
