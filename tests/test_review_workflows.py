"""The three review workflows carry one grading, one scope and one set of rules, copied because a workflow script
cannot import another; this holds the copies equal."""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

_FLOWS = pathlib.Path(__file__).resolve().parents[1] / ".claude" / "workflows"


def _constant(name: str, text: str) -> str:
    m = re.search(rf"^const {name} = `(.*?)`$", text, re.M | re.S)
    assert m, f"{name} is not a top-level template constant"
    return m.group(1)


def test_the_three_workflows_share_their_grading_scope_and_checkout_contract():
    texts = {f: (_FLOWS / f"{f}.js").read_text() for f in ("pre-read", "review", "re-review")}
    for name in ("GRADING", "SCOPE", "RULES"):
        values = {f: _constant(name, t) for f, t in texts.items()}
        assert len(set(values.values())) == 1, f"{name} differs between {sorted(values)}"


def test_a_keep_row_that_says_nothing_is_reported_as_owed():
    """A wrong predicate parses, so the check is driven rather than read, and the log call runs under a stub
    because it is the only part of it anyone sees."""
    # Never a skip: node is on the runner and on the workstation, so its absence means the caller
    # cannot run this case rather than that it need not — and a skip reads as a pass in a summary
    # line. The nightly unit found none for want of a PATH, and the night read clean.
    assert shutil.which("node") is not None, (
        "no node on PATH, so the workflow's own predicate cannot be run: in the nightly user unit "
        "this means `Environment=PATH=` is stale — re-render it after an nvm upgrade"
    )
    text = (_FLOWS / "pre-read.js").read_text()
    check = re.search(r"^const SAYS_NOTHING = .*?^if \(mute\.length\) log\(.*?\)$", text, re.M | re.S)
    assert check, "the owed-keep check must be the block the test drives, ending in its log call"
    nothing = [
        "",
        "  ",
        "—",
        "N.A.",
        "None.",
        "(none)",
        "TBD",
        "keep",
        "Keep.",
        "It stands as written.",
        "KEEP AS WRITTEN",
        "None needed.",
        "No changes.",
        "stands as is",
        "no change needed",
        "Good as is.",
        "reads fine",
        "Nothing to add.",
    ]
    something = [
        "a reader would not know the unit is the block",
        "without it the count is unattributed",
        "names the one tool whose refusals no test carries",
    ]
    rows = "const ROWS = CASES.map((ship, i) => ({ site: `p.py:${i}`, survives: 'keep', ship }))"
    program = "\n".join(
        (
            f"const CASES = {json.dumps(nothing + something)}",
            "const SAID = []",
            "const log = (line) => SAID.push(line)",
            rows,
            check.group(0).replace("report.prose", "ROWS"),
            "console.log(JSON.stringify([CASES.map(saysNothing), mute, SAID]))",
        )
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
    flags, owed, said = json.loads(done.stdout)
    assert flags == [True] * len(nothing) + [False] * len(something), done.stdout
    assert owed == [f"p.py:{i}" for i in range(len(nothing))], "every row that says nothing is owed"
    assert len(said) == 1 and said[0].startswith(f"OWED: {len(nothing)} "), said
    for site in owed:
        assert site in said[0], f"{site} is owed but the coordinator is not told"


def test_the_grading_grades_prose_by_consequence():
    text = _constant("GRADING", (_FLOWS / "review.js").read_text())
    assert "prose that, acted on as written, breaks something no test stops" in text


def test_every_workflow_records_itself_before_it_reads_and_the_two_reads_refuse_an_unread_tip():
    """The order of reviews is refused, not remembered: each script appends to `<reportDir>/ledger.jsonl` before its
    first phase, and review and re-review throw on a tip no pre-read covers -- the drift the ledger exists to stop."""
    texts = {f: (_FLOWS / f"{f}.js").read_text() for f in ("pre-read", "review", "re-review")}
    for name, text in texts.items():
        assert text.index("const ledger = await agent(") < text.index("\nphase("), (
            f"{name}: the ledger append must precede the first phase"
        )
    assert "throw new Error(`review refuses ${tip}" in texts["review"]
    assert "throw new Error(`re-review refuses ${tip}" in texts["re-review"]
    assert "records no review of this branch" in texts["re-review"]
    assert "refuses ${tip}" not in texts["pre-read"], "pre-read is the first read and refuses nothing"
