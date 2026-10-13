"""Every verdict a decisions log records is tied to the trial or reading whose numbers it rests on (spec 00129 D7)."""

from __future__ import annotations

import re
import subprocess

import pytest

from cli.registry import ReadingLedger, TrialRegistry
from tests.test_trial_registry_provenance import LEDGER, REGISTRY, REPO

_ENTRY = re.compile(r"^\[iter-(\d+)\b")
_TIE = re.compile(r"\((registry trial|reading) (\d+)\b")
_VERDICT = re.compile(r"\b(ADOPT|PARK|REJECT)(?:ED|S)?\b")
_TRIAL_WORD = re.compile(r"\btrial\b", re.IGNORECASE)
_TIE_FLOOR_ITER = 175


def _header(line: str) -> str:
    cut = line.find(". ")
    return line if cut < 0 else line[:cut]


def _entries(lines: list[str]) -> list[tuple[int, str]]:
    return [(int(entry.group(1)), _header(line)) for line in lines if (entry := _ENTRY.match(line))]


def _committed_entries() -> list[tuple[int, str]]:
    logs = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "docs/research/*decisions*"], capture_output=True, text=True, check=True
    ).stdout.split()
    return _entries([line for log in logs for line in (REPO / log).read_text(encoding="utf-8").splitlines()])


def tie_findings(entries: list[tuple[int, str]], trials: dict[int, str], readings: set[int]) -> list[str]:
    """`entries` are `(iter, header)` pairs; `trials` maps every trial id to its verdict."""
    found, named = [], set()
    for iter_n, header in entries:
        ties = list(_TIE.finditer(header))
        for tie in ties:
            kind, n = tie.group(1), int(tie.group(2))
            named.add((kind, n))
            if n not in (trials if kind == "registry trial" else readings):
                found.append(f"[iter-{iter_n}]: ({kind} {n} names no {kind.split()[-1]} on record")
            elif kind == "registry trial":
                stems = {verdict.group(1) for verdict in _VERDICT.finditer(header)}
                if len(stems) > 1:
                    found.append(
                        f"[iter-{iter_n}]: its header holds the verdicts {sorted(stems)}, and trial {n} has one, {trials[n]!r}"
                    )
                elif len(stems) == 1 and stems != {trials[n].upper()}:
                    found.append(f"[iter-{iter_n}]: its header's verdict {stems.pop()} is not trial {n}'s, {trials[n]!r}")
        if iter_n > _TIE_FLOOR_ITER and _VERDICT.search(header) and _TRIAL_WORD.search(header) and not ties:
            found.append(
                f"[iter-{iter_n}]: its header holds a verdict on a trial and no tie: past iter-{_TIE_FLOOR_ITER} it names the "
                "record as (registry trial N or (reading N"
            )
    for kind, n in [("registry trial", n) for n in sorted(trials) if n > 47] + [("reading", n) for n in sorted(readings)]:
        if (kind, n) not in named:
            found.append(f"{kind} {n} is named by no decisions-log header: the entry recording its decision carries ({kind} {n}")
    return found


def test_the_committed_decisions_logs_tie_every_verdict_to_its_record():
    entries = _committed_entries()
    trials = {record.trial_id: record.verdict for record in TrialRegistry(REGISTRY).records}
    readings = {reading.reading_id for reading in ReadingLedger(LEDGER).records}

    assert len(entries) >= 318, "the logs held 318 entries when the tie was written, and an entry is never deleted"
    assert tie_findings(entries, trials, readings) == []


@pytest.mark.parametrize(
    ("lines", "trials", "readings", "finding"),
    [
        pytest.param(
            ["[iter-086] Verdict — B1 trial 1 REJECT (registry trial 99, family B1 n=1). Body."],
            {45: "reject"},
            set(),
            "(registry trial 99",
            id="an-unknown-trial",
        ),
        pytest.param(
            ["[iter-086] Verdict — B1 trial 1 REJECT (registry trial 45, family B1 n=1). Body."],
            {45: "adopt"},
            set(),
            "'adopt'",
            id="reject-before-the-token-over-an-adopt-record",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 (registry trial 48) — ADOPT. Body."],
            {48: "park"},
            set(),
            "'park'",
            id="adopt-after-the-token-over-a-park-record",
        ),
        pytest.param(["[iter-176] B2 trial 1's pre-flight (reading 1). Body."], {}, set(), "(reading 1", id="an-unknown-reading"),
        pytest.param(
            ["[iter-176] B2 trial 2 — REJECT. Body."], {}, set(), "no tie", id="a-past-floor-verdict-on-a-trial-without-a-tie"
        ),
        pytest.param(["[iter-176 — B2 trial 2 — REJECT. Body."], {}, set(), "no tie", id="the-same-opening-on-a-dash"),
        pytest.param([], {48: "reject"}, set(), "registry trial 48", id="a-record-past-47-named-by-no-header"),
        pytest.param([], {}, {1}, "reading 1", id="a-reading-named-by-no-header"),
        pytest.param(
            ["[iter-086] ADOPT on the first read, then REJECT (registry trial 45, family B1 n=1). Body."],
            {45: "reject"},
            set(),
            "['ADOPT', 'REJECT']",
            id="two-verdict-stems",
        ),
    ],
)
def test_one_broken_tie_is_exactly_one_finding(lines, trials, readings, finding):
    found = tie_findings(_entries(lines), trials, readings)

    assert len(found) == 1 and finding in found[0], found


@pytest.mark.parametrize(
    ("lines", "trials"),
    [
        pytest.param(["[iter-175] B2 trial 2 — REJECT. Body."], {}, id="the-same-header-at-the-floor"),
        pytest.param(["[iter-176] B2 overlay ADOPTED. Body."], {}, id="a-past-floor-verdict-without-the-word-trial"),
        pytest.param(["[iter-086] Verdict — ADOPTED (registry trial 45). Body."], {45: "adopt"}, id="adopted-over-an-adopt-record"),
        pytest.param(
            ["[iter-086] REJECT, the bar REJECTED (registry trial 45). Body."],
            {45: "reject"},
            id="reject-and-rejected-over-a-reject-record",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 — REJECT (registry trial 48). Body."],
            {48: "reject"},
            id="the-shape-every-entry-takes-from-48-on",
        ),
    ],
)
def test_a_sound_tie_is_no_finding(lines, trials):
    assert tie_findings(_entries(lines), trials, set()) == []
