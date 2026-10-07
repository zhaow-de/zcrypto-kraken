"""The two fleet contracts are state files, held to shape: no date outside a `since` column, no table cell, bullet or paragraph past its cap, no heading below the fixed section set, a digest glossary that mirrors the pins table with no digest outside the digest cells and the glossary, and NAS rows that agree with the committed pins. Beside them, the fleet's one Alloy version is held to its three shapes and the NAS's Alloy literal to its committed digest.

Twice the two files grew a change history inside their state -- dated readings, incident narratives, cells three kilobytes long -- and each time a cleanup commit removed it by hand. A refusal in CI, and at the next `uv run pytest`, ends the class; an undated narrative that fits inside a block's cap is what the caps leave to the reader.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.test_alloy_version import alloy_version
from tests.test_pins_converged import pins

REPO = Path(__file__).resolve().parents[1]
FLEET = REPO / "docs" / "reference" / "fleet.md"
PINS = REPO / "docs" / "reference" / "fleet-pins.md"
NAS_VARS = REPO / "infra" / "ansible" / "host_vars" / "nas" / "vars.yml"
ALLOY_FILE = REPO / "infra" / "ansible" / "group_vars" / "observed" / "alloy.yml"
HOST_VARS = REPO / "infra" / "ansible" / "host_vars"
NAS_HOLD = HOST_VARS / "nas" / "alloy.yml"
SITE = REPO / "infra" / "ansible" / "site.yml"

CELL_MAX = 200  # an identifier and one clause; the cells that carried a saga ran past three thousand
BLOCK_MAX = 700  # a bullet or a paragraph holds one fact and its pointers
DATE = re.compile(
    r"\b\d{4}[-/.]\d{2}[-/.]\d{2}\b"  # 2026-09-10, 2026/09/10
    r"|\b\d{1,2}[-/.]\d{1,2}[-/.]\d{4}\b"  # 10.09.2026, 9/10/2026
    r"|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.? \d{1,2}\b"  # Sept 1
)
FULL = re.compile(r"sha256:([0-9a-f]{64})\b")
LEADING = re.compile(r"`([0-9a-f]{12})`")  # a cell's digest is the backticked 12-hex it opens with, the way the pruner reads it
HEX12 = re.compile(r"(?<![0-9a-f])[0-9a-f]{12}(?![0-9a-f])")  # a 12-hex token anywhere, backticked or not
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)]) ")
FLEET_SECTIONS = ["Hosts", "Services and instruments", "Storage topology", "Reboots", "Drills", "Telemetry labels"]
PINS_SECTIONS = ["Current pins", "Standing constraints", "Full digests"]


def _lines(path: Path) -> list[tuple[int, str]]:
    return list(enumerate(path.read_text(encoding="utf-8").splitlines(), start=1))


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", c) for c in _cells(line))


def _tables(path: Path) -> list[tuple[list[str], list[tuple[int, list[str]]]]]:
    """Each table as (header cells, [(line number, row cells)]) -- a contiguous block of `|` lines whose second line is the separator."""
    tables: list[tuple[list[str], list[tuple[int, list[str]]]]] = []
    block: list[tuple[int, str]] = []
    for i, line in [*_lines(path), (0, "")]:
        if line.startswith("|"):
            block.append((i, line))
            continue
        if len(block) >= 2 and _is_separator(block[1][1]):
            tables.append((_cells(block[0][1]), [(n, _cells(row)) for n, row in block[2:]]))
        block = []
    return tables


def _blocks(path: Path) -> list[tuple[int, str]]:
    """Each bullet (its continuation lines joined, indented or lazy, as Markdown renders them) and each paragraph (consecutive prose lines joined); tables, headings and fenced blocks are not blocks."""
    out: list[tuple[int, str]] = []
    kind = None  # "bullet", "paragraph" or None while the previous line closed a block
    fenced = False
    for i, line in _lines(path):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            kind = None
        elif fenced or not line.strip() or line.startswith(("|", "#")):
            kind = None
        elif BULLET.match(line):
            out.append((i, line))
            kind = "bullet"
        elif kind in ("bullet", "paragraph"):
            out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())
        else:
            out.append((i, line))
            kind = "paragraph"
    return out


def _sections(path: Path) -> dict[str, list[tuple[int, str]]]:
    """Each `## ` heading's text mapped to the numbered lines below it, in file order."""
    out: dict[str, list[tuple[int, str]]] = {}
    current = None
    for i, line in _lines(path):
        m = re.match(r"^## (.*)$", line)
        if m:
            current = m.group(1)
            out[current] = []
        elif current is not None:
            out[current].append((i, line))
    return out


def _leading(cell: str) -> str:
    m = LEADING.match(cell)
    return m.group(1) if m else ""


def _pins_rows(path: Path = PINS) -> list[tuple[int, str, str, str, str, str]]:
    """The `## Current pins` table's rows as (line, service, host cell, leading digest, leading operand digest or '', digest cell)."""
    header, rows = _tables(path)[0]
    i_service = header.index("service")
    i_host = header.index("host")
    i_digest = next(i for i, h in enumerate(header) if h.startswith("digest"))
    i_operand = next(i for i, h in enumerate(header) if h.startswith("rollback operand"))
    return [(n, c[i_service], c[i_host], _leading(c[i_digest]), _leading(c[i_operand]), c[i_digest]) for n, c in rows]


def test_the_topology_file_carries_no_date():
    hits = [(i, m.group(0)) for i, line in _lines(FLEET) for m in DATE.finditer(line)]
    assert hits == [], f"a date in fleet.md is a history entry, not topology: {hits}"


def test_a_date_in_the_pins_file_sits_in_a_since_column():
    since: set[tuple[int, str]] = set()
    for header, rows in _tables(PINS):
        cols = [k for k, h in enumerate(header) if h.startswith("since")]
        since.update((n, cells[k]) for n, cells in rows for k in cols)
    for i, line in _lines(PINS):
        for m in DATE.finditer(line):
            assert any(n == i and m.group(0) in cell for n, cell in since), (
                f"fleet-pins.md:{i} carries a date outside a `since` column: {m.group(0)!r} -- a reading or an incident goes to git, not here"
            )


@pytest.mark.parametrize("path", [FLEET, PINS], ids=["fleet", "pins"])
def test_no_table_cell_exceeds_the_cap(path: Path):
    long = [(n, len(c)) for _, rows in _tables(path) for n, cells in rows for c in cells if len(c) > CELL_MAX]
    assert long == [], f"{path.name}: a cell past {CELL_MAX} characters holds more than an identifier and one clause: {long}"


@pytest.mark.parametrize("path", [FLEET, PINS], ids=["fleet", "pins"])
def test_no_bullet_or_paragraph_exceeds_the_cap(path: Path):
    long = [(n, len(text)) for n, text in _blocks(path) if len(text) > BLOCK_MAX]
    assert long == [], f"{path.name}: a block past {BLOCK_MAX} characters is a narrative, not a fact and its pointers: {long}"


@pytest.mark.parametrize(("path", "expected"), [(FLEET, FLEET_SECTIONS), (PINS, PINS_SECTIONS)], ids=["fleet", "pins"])
def test_the_sections_are_the_fixed_set_and_nothing_nests_below_them(path: Path, expected: list[str]):
    assert list(_sections(path)) == expected, (
        f"{path.name}: the section set is fixed; a new kind of content is a new page, not a new section"
    )
    deeper = [i for i, line in _lines(path) if re.match(r"^#{3,} ", line)]
    assert deeper == [], f"{path.name}: a heading below the section set at lines {deeper} is where a sub-history starts"


def test_the_glossary_mirrors_the_pins_table():
    table = {d for _, _, _, digest, operand, _ in _pins_rows() for d in (digest, operand) if d}
    glossary: dict[str, int] = {}
    for i, line in _sections(PINS)["Full digests"]:
        fulls = FULL.findall(line)
        if not fulls:
            continue
        assert len(fulls) == 1 and line.startswith(f"- `{fulls[0][:12]}` = `sha256:{fulls[0]}`"), (
            f"fleet-pins.md:{i}: a glossary line is `<first 12>` = `sha256:<64>` and one clause"
        )
        glossary[fulls[0][:12]] = i
    assert set(glossary) == table, (
        f"glossary and table disagree -- only in the table {sorted(table - set(glossary))}, only in the glossary {sorted(set(glossary) - table)}"
    )
    table_lines = {n for _, rows in _tables(PINS) for n, _ in rows}
    stray = [
        i
        for i, line in _lines(PINS)
        if (FULL.search(line) or HEX12.search(line)) and i not in table_lines and i not in glossary.values()
    ]
    for k, (header, rows) in enumerate(_tables(PINS)):
        digest_cells = {i for i, h in enumerate(header) if h.startswith(("digest", "rollback operand"))} if k == 0 else set()
        stray += [
            n for n, cells in rows for i, c in enumerate(cells) if i not in digest_cells and (FULL.search(c) or HEX12.search(c))
        ]
    assert stray == [], f"a digest outside the pins table's digest cells and the glossary, at lines {sorted(stray)}"


def _hex12(ref: str) -> str:
    return ref.rsplit("sha256:", 1)[1][:12]


def _nas_rows_agree(pins: Path, nas_vars: Path, fleet: Path, host_vars: Path) -> bool:
    """`archive-pull` on `nas_capture_image`; the `alloy` row on `nas_alloy_image`, or behind it while that literal is the fleet file's and either the wave is open -- another host's `alloy` row off the fleet's digest, that host holding no `alloy.yml` hold file -- or the row carries `held` and its reason, which a hold's end leaves until the NAS converges."""
    literals = dict(re.findall(r"^(nas_capture_image|nas_alloy_image): (\S+@sha256:[0-9a-f]{64})", nas_vars.read_text(), re.M))
    assert set(literals) == {"nas_capture_image", "nas_alloy_image"}, literals
    fleet_digest = yaml.safe_load(fleet.read_text())["alloy_image_digest"]
    rows = [(service, [h.strip() for h in host.split(",")], digest, cell) for _, service, host, digest, _, cell in _pins_rows(pins)]
    nas = {service: (digest, cell) for service, hosts, digest, cell in rows if "nas" in hosts}
    others_off = [
        hosts
        for service, hosts, digest, _ in rows
        if service == "alloy"
        and "nas" not in hosts
        and not any((host_vars / host / "alloy.yml").exists() for host in hosts)
        and digest != _hex12(fleet_digest)
    ]
    pull_digest, _ = nas.get("archive-pull", ("", ""))
    alloy_digest, alloy_cell = nas.get("alloy", ("", ""))
    held = re.search(r"\bheld\b\W+\w", alloy_cell) is not None
    pull_agrees = pull_digest == _hex12(literals["nas_capture_image"])
    alloy_agrees = alloy_digest == _hex12(literals["nas_alloy_image"]) or (
        literals["nas_alloy_image"] == f"grafana/alloy@{fleet_digest}" and (bool(others_off) or held)
    )
    return pull_agrees and alloy_agrees


def test_the_nas_rows_agree_with_the_committed_pins():
    assert _nas_rows_agree(PINS, NAS_VARS, ALLOY_FILE, HOST_VARS), (
        "fleet-pins.md's NAS rows disagree with host_vars/nas/vars.yml: archive-pull is on nas_capture_image, and alloy on "
        "nas_alloy_image or, while that literal is the fleet file's, behind it with the wave open or the row `held`"
    )


FLEET_DIGEST = "sha256:" + "a" * 64
PREVIOUS = "sha256:" + "b" * 64
CAPTURE = "sha256:" + "c" * 64
ELSEWHERE = "sha256:" + "e" * 64


def _cell(digest: str, note: str = "v1.x") -> str:
    return f"`{_hex12(digest)}` — {note}"


def _constructed(
    tmp_path: Path, *, literal: str, nas_alloy: str, others: dict[str, str], held: tuple[str, ...] = (), pull: str = CAPTURE
):
    fleet = tmp_path / "group_vars" / "observed" / "alloy.yml"
    fleet.parent.mkdir(parents=True)
    fleet.write_text(f'alloy_version: "1.20.1"\nalloy_image_digest: {FLEET_DIGEST}\nalloy_deb_version: "1.20.1-1"\n')
    host_vars = tmp_path / "host_vars"
    nas_vars = host_vars / "nas" / "vars.yml"
    nas_vars.parent.mkdir(parents=True)
    nas_vars.write_text(
        f"nas_capture_image: ghcr.io/zhaow-de/zcrypto-capture@{CAPTURE}\nnas_alloy_image: grafana/alloy@{literal}\n"
    )
    for host in held:
        (host_vars / host).mkdir(parents=True, exist_ok=True)
        (host_vars / host / "alloy.yml").write_text(f"# the reason\nalloy_image_digest: {PREVIOUS}\n")
    rows = [("archive-pull", "nas", _cell(pull, "revision x")), ("alloy", "nas", nas_alloy)]
    rows += [("alloy", host, _cell(digest)) for host, digest in others.items()]
    pins = tmp_path / "fleet-pins.md"
    pins.write_text(
        "## Current pins\n\n"
        "| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (resident on the host at the re-pin) |\n"
        "| --- | --- | --- | --- | --- |\n"
        + "".join(f"| {s} | {h} | {c} | 2026-10-06 10:00:00 | first pin |\n" for s, h, c in rows)
    )
    return pins, nas_vars, fleet, host_vars


@pytest.mark.parametrize(
    ("literal", "nas_alloy", "others", "held", "pull", "agrees"),
    [
        (FLEET_DIGEST, _cell(FLEET_DIGEST), {"zcrypto": FLEET_DIGEST}, (), CAPTURE, True),
        (FLEET_DIGEST, _cell(PREVIOUS), {"zcrypto": FLEET_DIGEST, "zcrypto-red": PREVIOUS}, (), CAPTURE, True),
        (FLEET_DIGEST, _cell(PREVIOUS), {"zcrypto": FLEET_DIGEST, "zcrypto-red": FLEET_DIGEST}, (), CAPTURE, False),
        (FLEET_DIGEST, _cell(PREVIOUS), {"zcrypto": FLEET_DIGEST, "zcrypto-red": PREVIOUS}, ("zcrypto-red",), CAPTURE, False),
        (FLEET_DIGEST, _cell(PREVIOUS, "v1.19.2, held: 1.20.1 drops lines here"), {"zcrypto": FLEET_DIGEST}, (), CAPTURE, True),
        (ELSEWHERE, _cell(PREVIOUS), {"zcrypto": FLEET_DIGEST, "zcrypto-red": PREVIOUS}, (), CAPTURE, False),
        (FLEET_DIGEST, _cell(FLEET_DIGEST), {"zcrypto": FLEET_DIGEST, "zcrypto-red": PREVIOUS}, (), PREVIOUS, False),
    ],
    ids=[
        "both-rows-on-their-literals",
        "alloy-behind-the-fleet-literal-while-another-row-is-off",
        "alloy-behind-the-fleet-literal-with-every-other-row-on",
        "alloy-behind-the-fleet-literal-with-only-a-held-hosts-row-off",
        "alloy-behind-the-fleet-literal-with-the-row-held-and-its-reason",
        "alloy-behind-a-literal-off-the-fleet-file",
        "archive-pull-behind-its-literal-while-the-wave-is-open",
    ],
)
def test_the_nas_alloy_row_is_admitted_behind_its_literal_only_in_a_wave_or_a_hold_s_end(
    tmp_path, literal, nas_alloy, others, held, pull, agrees
):
    assert (
        _nas_rows_agree(*_constructed(tmp_path, literal=literal, nas_alloy=nas_alloy, others=others, held=held, pull=pull))
        is agrees
    )


def test_the_fleet_file_carries_three_values_in_their_shapes():
    fleet = yaml.safe_load(ALLOY_FILE.read_text())
    assert sorted(fleet) == ["alloy_deb_version", "alloy_image_digest", "alloy_version"], fleet
    assert all(isinstance(value, str) for value in fleet.values()), fleet
    assert re.fullmatch(r"\d+\.\d+\.\d+", fleet["alloy_version"]), fleet
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", fleet["alloy_image_digest"]), fleet
    assert re.fullmatch(r"\d+\.\d+\.\d+-\d+", fleet["alloy_deb_version"]), fleet
    assert fleet["alloy_deb_version"].startswith(fleet["alloy_version"] + "-"), fleet


def _nas_literal_is_committed(nas_vars: Path, hold: Path, fleet: Path) -> bool:
    committed = yaml.safe_load((hold if hold.exists() else fleet).read_text())
    (literal,) = re.findall(r"^nas_alloy_image:\s*(\S+@sha256:[0-9a-f]{64})\s*$", nas_vars.read_text(), re.M)
    return literal == f"grafana/alloy@{committed['alloy_image_digest']}"


def test_the_nas_alloy_literal_is_the_nas_committed_digest():
    assert _nas_literal_is_committed(NAS_VARS, NAS_HOLD, ALLOY_FILE), (
        "nas_alloy_image in host_vars/nas/vars.yml is not grafana/alloy@ the NAS's committed alloy_image_digest: "
        "host_vars/nas/alloy.yml's while the NAS is held, else group_vars/observed/alloy.yml's"
    )


@pytest.mark.parametrize(
    ("hold", "literal", "committed"),
    [(PREVIOUS, PREVIOUS, True), (PREVIOUS, FLEET_DIGEST, False), (None, FLEET_DIGEST, True)],
    ids=["held-literal-on-the-hold", "held-literal-on-the-fleet", "unheld-literal-on-the-fleet"],
)
def test_a_held_nas_s_literal_is_read_against_its_hold_file(tmp_path, hold, literal, committed):
    _, nas_vars, fleet, host_vars = _constructed(tmp_path, literal=literal, nas_alloy=_cell(literal), others={})
    if hold is not None:
        (host_vars / "nas" / "alloy.yml").write_text(f"# the reason\nalloy_image_digest: {hold}\n")
    assert _nas_literal_is_committed(nas_vars, host_vars / "nas" / "alloy.yml", fleet) is committed


def _package_alloy_hosts() -> set[str]:
    """The hosts a play reaches with a role whose tasks install the `alloy` package: the hosts that run Alloy from apt."""
    groups = pins.inventory_groups(REPO)
    return {
        host
        for play in yaml.safe_load(SITE.read_text())
        for entry in play.get("roles") or []
        if any(
            str((task.get("ansible.builtin.apt") or {}).get("name", "")).startswith("alloy=")
            for task, _, _ in alloy_version.role_leaves(entry["role"], frozenset())
        )
        for host in groups.get(play["hosts"], {play["hosts"]})
    }


def _alloy_package_rows_agree(pins_path: Path, apt_hosts: set[str]) -> bool:
    """Each `alloy` row of the package table names hosts that run Alloy from apt, its version cell opening with a
    backticked deb version, `<x.y.z>-<revision>`, the way `alloy-version.py off-fleet` reads it."""
    for header, rows in _tables(pins_path):
        if "package" not in header:
            continue
        i_package, i_host, i_version = header.index("package"), header.index("host"), header.index("version")
        for _, cells in rows:
            if cells[i_package] != "alloy":
                continue
            if not {host.strip() for host in cells[i_host].split(",")} <= apt_hosts:
                return False
            m = re.match(r"`([^`]+)`", cells[i_version])
            version = m.group(1) if m else ""
            if not re.fullmatch(r"\d+\.\d+\.\d+-\d+", version):
                return False
    return True


@pytest.mark.parametrize(
    ("host", "version", "agrees"),
    [
        ("zaccess", "`1.20.1-1`", True),
        ("zcrypto-ops", "`1.20.1-1`", False),
        ("zaccess", "1.20.1-1", False),
        ("zaccess", "`1.20.1`", False),
    ],
    ids=["an-apt-host-at-a-deb-version", "a-container-host", "a-version-without-backticks", "a-version-without-its-revision"],
)
def test_the_alloy_package_rows_name_apt_hosts_at_a_deb_version(tmp_path, host, version, agrees):
    pins_path = tmp_path / "fleet-pins.md"
    pins_path.write_text(
        "| package | host | version | since (UTC) | notes |\n| --- | --- | --- | --- | --- |\n"
        "| agentboard | zcrypto-ops | `0.5.3` (npm global) | 2026-09-17 | re-pins attended |\n"
        f"| alloy | {host} | {version} | 2026-10-06 | dpkg hold; pinned at 1001 |\n"
    )
    assert _alloy_package_rows_agree(pins_path, _package_alloy_hosts()) is agrees
