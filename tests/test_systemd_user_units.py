"""The user-unit templates under `infra/systemd/` render by placeholder substitution and parse as units.

`tests/test_infra_shell_templates_render.py` covers the Ansible-rendered `.sh.j2` templates; these
units are rendered into a copy by the install's `sed`, so the render here is a substitution, and
what is checked is that every placeholder a unit carries is named in its header's `Placeholders:`
line and filled by every copy of the install command, that no `<...>` token of any spelling -- a
whitespace-bearing `<data root>` included -- survives the render, and that the directives a
timer-driven oneshot needs sit in the section systemd reads them from -- a `Persistent=` under
`[Unit]` is silently ignored. Not checked:
`systemd-analyze verify`, which reads `ExecStart=` and `WorkingDirectory=` off disk and refuses the
example paths this render fills in."""

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
KNOWN = {
    "<repo>": "/home/you/Projects/zcrypto-kraken",
    "<uv>": "/home/you/.local/bin/uv",
    # A substitution source, not a reading of this machine: the real value is the installing
    # shell's $PATH, and pinning a node version here would read as a fact about it.
    "<path>": "/home/you/.local/bin:/usr/local/bin:/usr/bin",
}
_PLACEHOLDER = re.compile(r"<[^<>]+>")
_SED_CLAUSE = re.compile(r"s\|(<[^<>]+>)\|")


def units() -> list[Path]:
    return sorted(p for p in UNITS.iterdir() if p.is_file())


def body(text: str) -> str:
    """The unit as systemd reads it -- the header is comments."""
    return "\n".join(line for line in text.splitlines() if not line.startswith("#"))


def install_sed_clauses(text: str, unit: Path) -> list[set[str]]:
    """The tokens each `sed` line in `text` that renders `unit` fills, one set per line."""
    return [
        set(_SED_CLAUSE.findall(line))
        for line in text.splitlines()
        if f"infra/systemd/{unit.name}" in line and _SED_CLAUSE.search(line)
    ]


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


@pytest.mark.parametrize("token", ["<repo>", "<data_root>", "<data root>"])
def test_a_placeholder_of_any_spelling_is_seen_whitespace_included(token):
    assert _PLACEHOLDER.findall(f"WorkingDirectory={token}\n") == [token]


def test_every_unit_is_registered():
    found = {p.name for p in units()}
    assert found, "no units found — the directory is wrong, not the tree"
    assert found == REGISTERED, f"unregistered: {sorted(found - REGISTERED)}; stale entries: {sorted(REGISTERED - found)}"


@pytest.mark.parametrize("unit", units(), ids=lambda p: p.name)
def test_every_placeholder_is_known_and_named_in_the_header(unit):
    text = unit.read_text()
    carried = set(_PLACEHOLDER.findall(body(text)))
    assert carried <= set(KNOWN), f"{unit.name}: placeholder(s) the render cannot fill: {sorted(carried - set(KNOWN))}"
    if carried:
        named = [line for line in header_lines(text) if line.startswith("# Placeholders:")]
        assert named, f"{unit.name}: carries {sorted(carried)} but its header has no `# Placeholders:` line"
        missing = [t for t in sorted(carried) if t not in named[0]]
        assert not missing, f"{unit.name}: placeholder(s) not named on the `# Placeholders:` line: {missing}"
    # And the other direction, or a body that LOSES a placeholder keeps a header documenting it and
    # every case still passes — which is how the `Environment=PATH=` line's own probe survived.
    for token in _PLACEHOLDER.findall(" ".join(line for line in header_lines(text) if line.startswith("# Placeholders:"))):
        assert token in carried, f"{unit.name}: header names {token} and the body no longer carries it"


@pytest.mark.parametrize("unit", units(), ids=lambda p: p.name)
def test_the_render_leaves_nothing_angle_bracketed_and_parses(unit):
    rendered = render(unit.read_text())
    assert not _PLACEHOLDER.search(body(rendered)), f"{unit.name}: a placeholder survived the render"
    parsed = directives(rendered)
    assert "Description" in parsed.get("[Unit]", {}), f"{unit.name}: no Description= under [Unit]"
    if unit.suffix == ".service":
        service = parsed.get("[Service]", {})
        assert service.get("WorkingDirectory") == KNOWN["<repo>"], f"{unit.name}: WorkingDirectory must be <repo>"
        assert service.get("ExecStart", "").startswith(KNOWN["<uv>"] + " run "), f"{unit.name}: ExecStart must run through <uv>"
    else:
        timer = parsed.get("[Timer]", {})
        assert timer.get("OnCalendar"), f"{unit.name}: no OnCalendar= with a value under [Timer]"
        assert timer.get("Persistent") == "true", f"{unit.name}: Persistent=true must sit under [Timer], where systemd reads it"
        assert (UNITS / timer.get("Unit", "")).is_file(), f"{unit.name}: Unit= must name a service beside it"
        assert parsed.get("[Install]", {}).get("WantedBy") == "timers.target", f"{unit.name}: a timer is wanted by timers.target"


@pytest.mark.parametrize("unit", units(), ids=lambda p: p.name)
def test_every_copy_of_the_install_fills_exactly_what_the_body_carries(unit):
    """The install `sed` is written twice, in the unit's own header and in README.md, and neither
    copy is the unit: a clause short renders its placeholder into ~/.config verbatim, a clause extra
    outlives the placeholder it filled, and the `Placeholders:` line reads correct either way."""
    text = unit.read_text()
    carried = set(_PLACEHOLDER.findall(body(text)))
    for where, source in (("its own header", text), ("README.md", (REPO / "README.md").read_text())):
        clauses = install_sed_clauses(source, unit)
        assert len(clauses) == (1 if carried else 0), (
            f"{unit.name}: {where} holds {len(clauses)} install `sed` line(s) naming it, expected "
            f"{1 if carried else 0} for a body carrying {sorted(carried) or 'no placeholder'}"
        )
        if carried:
            assert clauses[0] == carried, (
                f"{unit.name}: {where}'s install `sed` fills {sorted(clauses[0])} but the body carries "
                f"{sorted(carried)} -- rendered verbatim into the installed copy: "
                f"{sorted(carried - clauses[0])}; clause(s) filling nothing: {sorted(clauses[0] - carried)}"
            )


def test_the_data_gated_service_is_a_oneshot_the_timer_owns():
    """Enabled through its timer alone: an [Install] section on the service would let `enable` start
    the whole suite at every login, and a non-oneshot would go active the moment pytest forked, so
    the timer's trigger and a hand `systemctl start` would stop reporting the suite's own result.
    `ExecStart=` is a list directive -- a oneshot runs every line, in order, and `directives()` keeps
    only the last -- so the count is read off the raw text."""
    raw = (UNITS / "zcrypto-data-gated-tests.service").read_text()
    service = directives(render(raw))
    timer = directives(render((UNITS / "zcrypto-data-gated-tests.timer").read_text()))
    assert service["[Service]"]["Type"] == "oneshot"
    assert "[Install]" not in service, "the service must not be enableable on its own"
    assert timer["[Timer]"]["Unit"] == "zcrypto-data-gated-tests.service"
    exec_lines = [line for line in raw.splitlines() if line.startswith("ExecStart=")]
    assert len(exec_lines) == 1, f"a oneshot runs every ExecStart= line, and there must be one: {exec_lines}"
    runner = exec_lines[0].split()[-1]
    assert runner == "infra/scripts/data-gated-run.py", f"ExecStart names an unexpected runner: {runner!r}"
    assert os.access(REPO / runner, os.X_OK), f"{runner} is not executable"
