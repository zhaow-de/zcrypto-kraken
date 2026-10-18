from __future__ import annotations

import re
import subprocess

import pytest

from cli.registry import ReadingLedger, TrialRegistry
from tests.test_trial_registry_provenance import LEDGER, REGISTRY, REPO

_ENTRY = re.compile(r"^\[iter-(\d+)\b")
_TIE = re.compile(r"\((registry trial|reading) (\d+)(?=[,);])")
_VERDICT = re.compile(r"\b(ADOPT|PARK|REJECT)(?:ED|S)?\b")
_ANY_CASE_VERDICT = re.compile(_VERDICT.pattern, re.IGNORECASE)
_TRIAL_WORD = re.compile(r"\btrial\b", re.IGNORECASE)
_COUNTED = re.compile(r"\(attempts counted: ([0-9a-f]{8}#\d+(?:, [0-9a-f]{8}#\d+)*)\)")
_TIE_FLOOR_ITER = 175
_TOKEN_END = "the id ended by ',', ')' or ';'"


def _header(line: str) -> str:
    cut = line.find(". ")
    return line if cut < 0 else line[:cut]


def _entries(lines: list[str]) -> list[tuple[int, str]]:
    return [(int(entry.group(1)), line) for line in lines if (entry := _ENTRY.match(line))]


def _committed_entries() -> list[tuple[int, str]]:
    logs = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "docs/research/*decisions*"], capture_output=True, text=True, check=True
    ).stdout.split()
    return _entries([line for log in logs for line in (REPO / log).read_text(encoding="utf-8").splitlines()])


def _moved(iter_n: int, held: re.Match | None, remedy: str) -> str:
    if held is not None:
        return (
            f"[iter-{iter_n}]'s header ends at its first '. ', and the {held.group(0)} its line holds past it must move before it"
        )
    return remedy


def _verdict_findings(iter_n: int, line: str, cited: list[int], trials: dict[int, str]) -> list[str]:
    header = _header(line)
    stems = sorted({verdict.group(1) for verdict in _VERDICT.finditer(header)})
    if len(stems) > 1:
        return [
            f"[iter-{iter_n}]: its header holds the verdicts {stems}: one entry records one trial's verdict, so write any "
            "other in lowercase"
        ]
    if not stems:
        return [
            f"[iter-{iter_n}]: its header names (registry trial {cited[-1]} and states no verdict: write its own trial's "
            "ADOPT, PARK or REJECT before its first '. ', or, where it keeps a reading, put that (reading N there and move "
            "the cited trial's token past it"
        ]
    # A trial is registered after the incumbent it is compared with, so the highest id is the entry's own.
    judged = cited[-1:]
    return [
        f"[iter-{iter_n}]: its header's verdict {stem} is not trial {n}'s, {trials[n]!r}"
        for n in judged
        if n in trials
        for stem in stems
        if stem != trials[n].upper()
    ]


def _counted_findings(iter_n: int, header: str, judged: list[int], counted: dict[int, list[str]]) -> list[str]:
    owed = {token for n in judged for token in counted.get(n, [])}
    named = {token for held in _COUNTED.finditer(header) for token in held.group(1).split(", ")}
    found = []
    if missing := sorted(owed - named):
        found.append(
            f"[iter-{iter_n}]: registry trial {judged[-1]} counted attempts its header does not name: missing {missing}; "
            "name each before its first '. ' as (attempts counted: <log8>#<id>, …)"
        )
    if extra := sorted(named - owed):
        found.append(
            f"[iter-{iter_n}]: its header names attempts registry trial {judged[-1]} did not count: extra {extra}; its "
            "(attempts counted: …) names that record's counted entries alone"
        )
    return found


def tie_findings(
    entries: list[tuple[int, str]],
    trials: dict[int, str],
    readings: set[int],
    counted: dict[int, list[str]] | None = None,
) -> list[str]:
    """`entries` are `(iter, line)` pairs; `trials` maps every trial id to its verdict; `counted` maps a trial id to the
    `<log8>#<id>` tokens of its record's `attempt.counted`, a trial it omits counting none."""
    counted = counted or {}
    found, named, past = [], set(), {}
    for iter_n, line in entries:
        header = _header(line)
        ties = [(tie.group(1), int(tie.group(2))) for tie in _TIE.finditer(header)]
        named.update(ties)
        for tie in _TIE.finditer(line, len(header)):
            past.setdefault((tie.group(1), int(tie.group(2))), (iter_n, tie))
        for kind, n in ties:
            if n not in (trials if kind == "registry trial" else readings):
                found.append(f"[iter-{iter_n}]: ({kind} {n} names no {kind.split()[-1]} on record")
        if cited := sorted(n for kind, n in ties if kind == "registry trial"):
            found += _verdict_findings(iter_n, line, cited, trials)
            found += _counted_findings(iter_n, header, cited[-1:], counted)
        if iter_n > _TIE_FLOOR_ITER and _ANY_CASE_VERDICT.search(header) and _TRIAL_WORD.search(header) and not ties:
            remedy = _moved(
                iter_n,
                _TIE.search(line, len(header)),
                f"past iter-{_TIE_FLOOR_ITER} it names the record as (registry trial N or (reading N, {_TOKEN_END}",
            )
            found.append(f"[iter-{iter_n}]: its header holds a verdict on a trial and no tie: {remedy}")
    for kind, n in [("registry trial", n) for n in sorted(trials) if n > 47] + [("reading", n) for n in sorted(readings)]:
        if (kind, n) not in named:
            held_at, held = past.get((kind, n), (0, None))
            remedy = _moved(held_at, held, f"the entry recording its decision carries ({kind} {n}, {_TOKEN_END}")
            found.append(f"{kind} {n} is named by no decisions-log header: {remedy}")
    return found


def test_the_committed_decisions_logs_tie_every_verdict_to_its_record():
    entries = _committed_entries()
    trials = {record.trial_id: record.verdict for record in TrialRegistry(REGISTRY).records}
    readings = {reading.reading_id for reading in ReadingLedger(LEDGER).records}
    counted = {
        record.trial_id: [f"{entry['log'][:8]}#{entry['id']}" for entry in record.attempt["counted"]]
        for record in TrialRegistry(REGISTRY).records
        if record.attempt
    }

    assert len(entries) >= 318, "a decisions-log entry is never deleted"
    assert tie_findings(entries, trials, readings, counted) == []


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
        pytest.param(
            ["[iter-180] B2 trial 3 — REJECT against the incumbent (registry trial 47) (registry trial 49)."],
            {47: "adopt", 49: "adopt"},
            set(),
            "REJECT is not trial 49's",
            id="a-challengers-verdict-against-its-own-record",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 — the verdict (registry trial 48) (Decision: 1)"],
            {48: "reject"},
            set(),
            "states no verdict: write its own trial's ADOPT, PARK or REJECT before its first '. '",
            id="the-closeout-templates-question-line",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 rejected (registry trial 48). Body."],
            {48: "adopt"},
            set(),
            "states no verdict: write its own trial's ADOPT, PARK or REJECT before its first '. '",
            id="a-lowercase-verdict-beside-a-tie",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 stopped against the incumbent (registry trial 47) (reading 2) (Decision: 1)"],
            {47: "adopt"},
            {2},
            "where it keeps a reading, put that (reading N there and move the cited trial's token past it",
            id="a-stopped-challengers-reading-citing-its-incumbent-in-the-header",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 rejected, no tie. Body."],
            {},
            set(),
            "no tie: past iter-175",
            id="a-lowercase-past-floor-verdict-on-a-trial-without-a-tie",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 vs. arm A — REJECT (registry trial 48)."],
            {48: "reject"},
            set(),
            "[iter-176]'s header ends at its first '. ', and the (registry trial 48 its line holds past it must move before it",
            id="a-tie-past-an-abbreviations-full-stop",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 (registry trial 48). Verdict: REJECT."],
            {48: "adopt"},
            set(),
            "states no verdict: write its own trial's ADOPT, PARK or REJECT before its first '. '",
            id="a-verdict-past-the-headers-end",
        ),
        pytest.param(
            [
                "[iter-176] B2 trial 2 stopped against the incumbent (registry trial 47) (reading 2) (Decision: 1). The "
                "incumbent stays ADOPTED."
            ],
            {47: "adopt"},
            {2},
            "where it keeps a reading, put that (reading N there and move the cited trial's token past it",
            id="a-stopped-challengers-reading-whose-line-holds-its-incumbents-verdict",
        ),
        pytest.param(
            ["[iter-176] B2 trial 2 — REJECT. Recorded as (registry trial 48)."],
            {},
            set(),
            "no tie: [iter-176]'s header ends at its first '. ', and the (registry trial 48 its line holds past it",
            id="a-past-floor-verdicts-tie-past-the-headers-end",
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
        pytest.param(
            ["[iter-180] B2 trial 3 — REJECT against the incumbent (registry trial 47) (registry trial 49)."],
            {47: "adopt", 49: "reject"},
            id="a-challenger-citing-its-incumbents-trial",
        ),
        pytest.param(["[iter-178] Which bar (reading 3 sources) for B3? (Decision: 1)"], {}, id="prose-in-parentheses-is-no-tie"),
    ],
)
def test_a_sound_tie_is_no_finding(lines, trials):
    assert tie_findings(_entries(lines), trials, set()) == []


def test_a_stopped_challengers_reading_may_cite_its_incumbent_below_its_header():
    line = "[iter-176] B2 trial 2 stopped (reading 2), its incumbent cited below. Against (registry trial 47)."

    assert tie_findings(_entries([line]), {47: "adopt"}, {2}) == []


@pytest.mark.parametrize("end", [" — family B2)", ": B2)", " )"])
def test_a_tie_whose_id_ends_otherwise_is_told_how_its_id_ends(end):
    found = tie_findings(_entries([f"[iter-176] B2 trial 2 — REJECT (registry trial 48{end}. Body."]), {48: "reject"}, set())

    assert len(found) == 2 and all("the id ended by ',', ')' or ';'" in finding for finding in found), found


@pytest.mark.parametrize(
    ("line", "counted", "finding"),
    [
        pytest.param(
            "[iter-180] B1 trial 4 — REJECT (registry trial 49).",
            {49: ["ffffffff#5"]},
            "missing ['ffffffff#5']",
            id="a-counted-orphan-unnamed",
        ),
        pytest.param(
            "[iter-180] B1 trial 4 — REJECT (registry trial 49) (attempts counted: ffffffff#5, ffffffff#6).",
            {49: ["ffffffff#5"]},
            "extra ['ffffffff#6']",
            id="an-orphan-the-record-does-not-count",
        ),
    ],
)
def test_a_header_names_exactly_the_orphans_its_record_counted(line, counted, finding):
    found = tie_findings(_entries([line]), {49: "reject"}, set(), counted)

    assert len(found) == 1 and finding in found[0], found


@pytest.mark.parametrize(
    ("line", "counted"),
    [
        pytest.param(
            "[iter-180] B1 trial 4 — REJECT (registry trial 49) (attempts counted: ffffffff#5, eeeeeeee#2).",
            {49: ["eeeeeeee#2", "ffffffff#5"]},
            id="every-counted-orphan-named",
        ),
        pytest.param("[iter-180] B1 trial 4 — REJECT (registry trial 49).", {49: []}, id="a-record-that-counted-none"),
        pytest.param(
            "[iter-180] B1 trial 4 — REJECT against the incumbent (registry trial 47) (registry trial 49) (attempts counted: "
            "ffffffff#5).",
            {47: ["eeeeeeee#2"], 49: ["ffffffff#5"]},
            id="an-incumbents-counted-orphan-unnamed",
        ),
    ],
)
def test_a_header_naming_its_counted_orphans_is_no_finding(line, counted):
    assert tie_findings(_entries([line]), {47: "adopt", 49: "reject"}, set(), counted) == []
