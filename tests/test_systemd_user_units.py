"""The user-unit templates under `infra/systemd/` render by placeholder substitution and parse as units.

`tests/test_infra_shell_templates_render.py` covers the Ansible-rendered `.sh.j2` templates; these
units are filled in by hand (`<repo>`, `<uv>`), so the render here is a substitution, and what is
checked is that every placeholder a unit carries is named in its header's `Placeholders:` line, that
nothing angle-bracketed survives the render, and that the directives a timer-driven oneshot needs sit
in the section systemd reads them from -- a `Persistent=` under `[Unit]` is silently ignored. Not
checked: `systemd-analyze verify`, which needs a user manager CI does not run."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
UNITS = REPO / "infra" / "systemd"

# Every infra/systemd/* must appear here, so a new unit cannot land unguarded.
REGISTERED = {
    "zcrypto-data-gated-tests.service",
    "zcrypto-data-gated-tests.timer",
    "zcrypto-engine-shadow.service",
}
# The placeholders a header may name, with the absolute paths the render fills them with.
KNOWN = {"<repo>": "/home/you/Projects/zcrypto-kraken", "<uv>": "/home/you/.local/bin/uv"}
_PLACEHOLDER = re.compile(r"<[a-z]+>")


def units() -> list[Path]:
    return sorted(p for p in UNITS.iterdir() if p.is_file())


def directives(text: str) -> dict[str, dict[str, str]]:
    """Section -> directive -> LAST value, comments and blank lines dropped: a scalar setting takes its
    last assignment, so a duplicate under the same section must read the way systemd reads it."""
    section, out = None, {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line
            continue
        assert section is not None, f"directive before any section: {line!r}"
        key, _, value = line.partition("=")
        assert _ == "=", f"a directive line without `=`: {line!r}"
        out.setdefault(section, {})[key.strip()] = value.strip()
    return out


def header_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("#")]


def render(text: str) -> str:
    for token, value in KNOWN.items():
        text = text.replace(token, value)
    return text


def test_every_unit_is_registered():
    found = {p.name for p in units()}
    assert found, "no units found — the directory is wrong, not the tree"
    assert found == REGISTERED, f"unregistered: {sorted(found - REGISTERED)}; stale entries: {sorted(REGISTERED - found)}"


@pytest.mark.parametrize("unit", units(), ids=lambda p: p.name)
def test_every_placeholder_is_known_and_named_in_the_header(unit):
    text = unit.read_text()
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    carried = set(_PLACEHOLDER.findall(body))
    assert carried <= set(KNOWN), f"{unit.name}: placeholder(s) the render cannot fill: {sorted(carried - set(KNOWN))}"
    if carried:
        named = [line for line in header_lines(text) if line.startswith("# Placeholders:")]
        assert named, f"{unit.name}: carries {sorted(carried)} but its header has no `# Placeholders:` line"
        missing = [t for t in sorted(carried) if t not in named[0]]
        assert not missing, f"{unit.name}: placeholder(s) not named on the `# Placeholders:` line: {missing}"


@pytest.mark.parametrize("unit", units(), ids=lambda p: p.name)
def test_the_render_leaves_nothing_angle_bracketed_and_parses(unit):
    rendered = render(unit.read_text())
    body = "\n".join(line for line in rendered.splitlines() if not line.startswith("#"))
    assert not _PLACEHOLDER.search(body), f"{unit.name}: a placeholder survived the render"
    parsed = directives(rendered)
    assert "Description" in parsed.get("[Unit]", {}), f"{unit.name}: no Description= under [Unit]"
    if unit.suffix == ".service":
        service = parsed.get("[Service]", {})
        assert service.get("WorkingDirectory") == KNOWN["<repo>"], f"{unit.name}: WorkingDirectory must be <repo>"
        assert service.get("ExecStart", "").startswith(KNOWN["<uv>"] + " run "), f"{unit.name}: ExecStart must run through <uv>"
    else:
        timer = parsed.get("[Timer]", {})
        assert "OnCalendar" in timer, f"{unit.name}: no OnCalendar= under [Timer]"
        assert timer.get("Persistent") == "true", f"{unit.name}: Persistent=true must sit under [Timer], where systemd reads it"
        assert (UNITS / timer.get("Unit", "")).is_file(), f"{unit.name}: Unit= must name a service beside it"
        assert parsed.get("[Install]", {}).get("WantedBy") == "timers.target", f"{unit.name}: a timer is wanted by timers.target"


def test_the_data_gated_service_is_a_oneshot_the_timer_owns():
    """Enabled through its timer alone: an [Install] section on the service would let `enable` start
    the whole suite at every login, and a non-oneshot would let the timer overlap a run still going."""
    service = directives(render((UNITS / "zcrypto-data-gated-tests.service").read_text()))
    timer = directives(render((UNITS / "zcrypto-data-gated-tests.timer").read_text()))
    assert service["[Service]"]["Type"] == "oneshot"
    assert "[Install]" not in service, "the service must not be enableable on its own"
    assert timer["[Timer]"]["Unit"] == "zcrypto-data-gated-tests.service"
    runner = service["[Service]"]["ExecStart"].split()[-1]
    assert runner == "infra/scripts/data-gated-run.py", f"ExecStart names an unexpected runner: {runner!r}"
    assert os.access(REPO / runner, os.X_OK), f"{runner} is not executable"
