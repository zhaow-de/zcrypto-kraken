"""The user-unit templates under `infra/systemd/` render by placeholder substitution and parse as units.

`tests/test_infra_shell_templates_render.py` covers the Ansible-rendered `.sh.j2` templates; these
units are rendered into a copy by the install's `sed`, so the render here is a substitution, and
what is checked is that every placeholder a unit carries is named in its header's `Placeholders:`
line and filled, from the expression `FILLS` names, by every tracked copy of the install command --
found by `git grep`, so a copy pasted into a runbook is held too -- that no `<...>` token of any
spelling -- a whitespace-bearing `<data root>` included -- survives the render, and that the
directives a timer-driven oneshot needs sit in the section systemd reads
them from -- a `Persistent=` under `[Unit]` is silently ignored. Not checked: `systemd-analyze
verify`, which reads `ExecStart=` and `WorkingDirectory=` off disk and refuses the example paths
this render fills in."""

from __future__ import annotations

import os
import re
import subprocess
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
# `s<d><token><d><replacement><d>` for any delimiter the install picks: a `|` in $PATH kills a
# `s|…|` expression, and hardening against that by switching to `s#…#` must not read as no install.
_SED_CLAUSE = re.compile(r"s(.)(<[^<>]+>)\1(.*?)\1")
# The command WITH its script argument. `used`, `closed` and `based` carry `sed` as a substring, and
# prose naming the command carries it as a word -- the read-back step this file's own header tells
# the operator to run says "renders wrong through sed", one clause away from reading as an install.
_SED_CMD = re.compile(r"""\bsed\b\s+(?:-\w+\s+)*["']""")
# What the install fills each placeholder FROM. Checked beside the token, or a clause rendering
# <path> from $PWD -- a unit whose PATH is the checkout, so no node and a red night -- reads as a
# match. One spelling each, the one the tree uses; another lands here with the edit that wants it.
FILLS = {"<repo>": "$PWD", "<uv>": "$(command -v uv)", "<path>": "$PATH"}


def units() -> list[Path]:
    return sorted(p for p in UNITS.iterdir() if p.is_file())


def body(text: str) -> str:
    """The unit as systemd reads it -- the header is comments."""
    return "\n".join(line for line in text.splitlines() if not line.startswith("#"))


def _logical_lines(text: str):
    """(first line number, line) with `\\` continuations joined, the way a shell reads a command.

    A wrapped install is one command; read as two physical lines it is neither, and this guard's
    whole subject is drift nobody is told about."""
    buf, start = "", 0
    for n, raw in enumerate(text.splitlines(), 1):
        if not buf:
            start = n
        if raw.endswith("\\"):
            buf += raw[:-1]
            continue
        yield start, buf + raw
        buf = ""
    if buf:
        yield start, buf


def install_copies(unit: Path) -> list[tuple[str, dict[str, str]]]:
    """Every tracked command that renders `unit` through `sed`, as (where, {token: replacement}).

    Found rather than listed, so a copy pasted into a runbook or a skill is held to the unit the way
    the header's and README.md's are -- README.md is how this drift got in. A command is held when it
    names the unit and runs `sed` over a quoted script filling at least one placeholder; prose about
    the install reads as prose, and a copy reaching the unit through a variable is not found."""
    found = subprocess.run(
        ["git", "-C", str(REPO), "grep", "-l", "--no-color", "-e", unit.name],
        capture_output=True,
        text=True,
        check=False,
    )
    # rc 1 is "nothing names it", which the caller reads; anything above is a checkout this guard
    # cannot search, and it says so rather than reporting every copy missing.
    assert found.returncode < 2, f"`git grep` could not search this checkout: {found.stderr.strip()!r}"
    here = str(Path(__file__).resolve().relative_to(REPO))
    copies = []
    for path in found.stdout.splitlines():
        if path == here:
            continue
        try:
            text = (REPO / path).read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        for lineno, line in _logical_lines(text):
            if not _SED_CMD.search(line) or unit.name not in line:
                continue
            clauses: dict[str, str] = {}
            for _, token, replacement in _SED_CLAUSE.findall(line):
                clauses.setdefault(token, replacement)  # sed applies the FIRST clause for a token
            if clauses:
                copies.append((f"{path}:{lineno}", clauses))
    return copies


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


def test_every_known_placeholder_names_what_the_install_fills_it_from():
    assert set(FILLS) == set(KNOWN), "a placeholder in KNOWN with no FILLS entry is unchecked in every install copy"


@pytest.mark.parametrize("unit", units(), ids=lambda p: p.name)
def test_every_copy_of_the_install_fills_exactly_what_the_body_carries(unit):
    """No copy of the install command is the unit, and each drifts from it on its own: a clause
    short renders its placeholder into ~/.config verbatim, a clause extra outlives the placeholder
    it filled, and a clause filling the right token from the wrong expression renders a unit that
    starts and fails. The `Placeholders:` line reads correct through all three."""
    carried = set(_PLACEHOLDER.findall(body(unit.read_text())))
    copies = install_copies(unit)
    if not carried:
        assert not copies, f"{unit.name} carries no placeholder, yet {[w for w, _ in copies]} render it through `sed`"
        return
    assert copies, (
        f"{unit.name}: body carries {sorted(carried)} and no tracked `sed` command renders it -- a copy "
        f"reaching the unit only through a variable is not found, and neither is one whose `sed` carries "
        f"no quoted script"
    )
    for where, clauses in copies:
        assert set(clauses) == carried, (
            f"{unit.name}: the install at {where} fills {sorted(clauses)} but the body carries "
            f"{sorted(carried)} -- rendered verbatim into the installed copy: "
            f"{sorted(carried - set(clauses))}; clause(s) filling nothing: {sorted(set(clauses) - carried)}"
        )
        unnamed = sorted(set(clauses) - set(FILLS))
        assert not unnamed, f"{unit.name}: the install at {where} fills {unnamed}, which `FILLS` does not name"
        wrong = {tok: rep for tok, rep in clauses.items() if rep != FILLS[tok]}
        assert not wrong, f"{unit.name}: the install at {where} fills " + ", ".join(
            f"{tok} from {rep!r}, not {FILLS[tok]!r}" for tok, rep in sorted(wrong.items())
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
