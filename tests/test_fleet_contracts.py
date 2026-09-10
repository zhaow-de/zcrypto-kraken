"""The two fleet contracts are state files, held to shape: no date outside a `since` column, no table cell or bullet past its cap, no heading below the fixed section set, a digest glossary that mirrors the pins table with no digest elsewhere, and NAS rows that agree with the committed pins.

Twice the two files grew a change history inside their state -- dated readings, incident narratives, cells three kilobytes long -- and each time a cleanup commit removed it by hand. A refusal in CI, and at the next `uv run pytest`, ends the class; an undated narrative that fits inside a bullet's cap is what the caps leave to the reader.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FLEET = REPO / "docs" / "reference" / "fleet.md"
PINS = REPO / "docs" / "reference" / "fleet-pins.md"
NAS_VARS = REPO / "infra" / "ansible" / "host_vars" / "nas" / "vars.yml"

CELL_MAX = 200  # an identifier and one clause; the cells that carried a saga ran past three thousand
BULLET_MAX = 700  # one fact and its pointers; the storage listing is the longest legitimate bullet
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


def _bullets(path: Path) -> list[tuple[int, str]]:
    """Each list item with its indented continuation lines joined, fenced blocks skipped -- the guidance guard's reading."""
    out: list[tuple[int, str]] = []
    open_bullet = fenced = False
    for i, line in _lines(path):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            open_bullet = False
        elif fenced:
            continue
        elif BULLET.match(line):
            out.append((i, line))
            open_bullet = True
        elif open_bullet and line.strip() and line[:1].isspace():
            out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())
        else:
            open_bullet = False
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


def _pins_rows() -> list[tuple[int, str, str, str, str]]:
    """The `## Current pins` table's rows as (line, service, host cell, leading digest, leading operand digest or '')."""
    header, rows = _tables(PINS)[0]
    i_service = header.index("service")
    i_host = header.index("host")
    i_digest = next(i for i, h in enumerate(header) if h.startswith("digest"))
    i_operand = next(i for i, h in enumerate(header) if h.startswith("rollback operand"))
    return [(n, c[i_service], c[i_host], _leading(c[i_digest]), _leading(c[i_operand])) for n, c in rows]


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
def test_no_bullet_exceeds_the_cap(path: Path):
    long = [(n, len(text)) for n, text in _bullets(path) if len(text) > BULLET_MAX]
    assert long == [], f"{path.name}: a bullet past {BULLET_MAX} characters is a narrative, not a fact and its pointers: {long}"


@pytest.mark.parametrize(("path", "expected"), [(FLEET, FLEET_SECTIONS), (PINS, PINS_SECTIONS)], ids=["fleet", "pins"])
def test_the_sections_are_the_fixed_set_and_nothing_nests_below_them(path: Path, expected: list[str]):
    assert list(_sections(path)) == expected, (
        f"{path.name}: the section set is fixed; a new kind of content is a new page, not a new section"
    )
    deeper = [i for i, line in _lines(path) if re.match(r"^#{3,} ", line)]
    assert deeper == [], f"{path.name}: a heading below the section set at lines {deeper} is where a sub-history starts"


def test_the_glossary_mirrors_the_pins_table():
    table = {d for _, _, _, digest, operand in _pins_rows() for d in (digest, operand) if d}
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
    assert stray == [], f"a digest outside the pins tables and the glossary, at lines {stray}"


def test_the_nas_rows_agree_with_the_committed_pins():
    committed = {
        k: v[:12]
        for k, v in re.findall(r"^(nas_capture_image|nas_alloy_image): \S+@sha256:([0-9a-f]{64})", NAS_VARS.read_text(), re.M)
    }
    assert set(committed) == {"nas_capture_image", "nas_alloy_image"}, committed
    by_service = {service: digest for _, service, host, digest, _ in _pins_rows() if "nas" in [h.strip() for h in host.split(",")]}
    assert by_service.get("archive-pull") == committed["nas_capture_image"], (by_service, committed)
    assert by_service.get("alloy") == committed["nas_alloy_image"], (by_service, committed)
