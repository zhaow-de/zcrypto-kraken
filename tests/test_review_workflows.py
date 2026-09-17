"""The three review workflows carry one grading, one scope and one set of rules, copied because a workflow script
cannot import another."""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

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
    check = re.search(r"^const SAYS_NOTHING = .*?^if \([^\n]*\) log\(`OWED: [^\n]*$", text, re.M | re.S)
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


def test_every_workflow_records_itself_once_it_has_read_and_the_ledger_gates_the_two_reads():
    texts = {f: (_FLOWS / f"{f}.js").read_text() for f in ("pre-read", "review", "re-review")}
    for name, text in texts.items():
        record, append = text.index("phase('Record')"), text.index("const recorded = await agent(")
        assert text.rindex("phase('") == record, f"{name}: Record is the last phase"
        assert record < append < text.rindex("\nreturn ") and text.rindex("await agent(") == text.index("await agent(", append), (
            f"{name}: the row is appended by the last agent to run and before the return, so a read that dies leaves no row"
        )
    for name, phase in (("review", "Read"), ("re-review", "Re-read")):
        text = texts[name]
        gate, ledger = text.index("phase('Ledger')"), text.index("const ledger = await agent(")
        assert gate < ledger < text.index(f"\nphase('{phase}')"), (
            f"{name}: the Ledger phase gates the read, both before the first read phase"
        )
    before_the_grader = texts["pre-read"][: texts["pre-read"].index("phase('Pre-read')")]
    assert "ledger" not in before_the_grader and before_the_grader.count("throw") == 1, (
        "pre-read is the first read: it reads no ledger and refuses nothing but its arguments"
    )


@pytest.mark.parametrize("flow", sorted(p.stem for p in _FLOWS.glob("*.js")))
def test_every_workflow_parses_as_the_harness_runs_it(flow, tmp_path):
    """The harness runs the body inside an async function, where a top-level `return` is legal and a second
    `const` of one name is not; nothing else parses a script before its first dispatch."""
    assert shutil.which("node") is not None, "no node on PATH, so the script cannot be parsed"
    body = (_FLOWS / f"{flow}.js").read_text().replace("export const meta", "const meta", 1)
    program = tmp_path / f"{flow}.cjs"
    program.write_text(f"async function wrap(args, agent, phase, parallel, pipeline, log, budget, workflow) {{\n{body}\n}}\n")
    done = subprocess.run(["node", "--check", str(program)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_the_two_reads_refuse_in_order_by_what_the_ledger_holds():
    """Driven, not read: a condition inverted under the right string passes every text assert above."""
    assert shutil.which("node") is not None, "no node on PATH, so the refusal cannot be driven"
    cases = {
        "review": [
            (None, "the ledger agent returned nothing"),
            ([], "records no pre-read"),
            ([{"kind": "pre-read", "coversTip": False}], "records no pre-read"),
            ([{"kind": "review", "coversTip": True}], "records no pre-read"),
            ([{"kind": "pre-read", "coversTip": True}], None),
        ],
        "re-review": [
            (None, "the ledger agent returned nothing"),
            ([], "records no review"),
            ([{"kind": "pre-read", "coversTip": True}], "records no review"),
            ([{"kind": "review", "coversTip": True}, {"kind": "pre-read", "coversTip": False}], "records no pre-read"),
            ([{"kind": "review", "coversTip": False}, {"kind": "pre-read", "coversTip": True}], None),
        ],
    }
    for flow, table in cases.items():
        text = (_FLOWS / f"{flow}.js").read_text()
        refuses = rf"^if \([^\n]*\) throw new Error\(`{flow} refuses \$\{{tip\}}: "
        block = re.search(
            refuses + r"the ledger agent returned nothing[^\n]*$.*?" + refuses + r"\$\{ledgerPath\} records no pre-read[^\n]*$",
            text,
            re.M | re.S,
        )
        assert block, (
            f"{flow}: the refusals are the block from the null-ledger throw to the pre-read refusal, anchored on their words"
        )
        program = "\n".join(
            (
                "const tip = 'TIP', ledgerPath = 'LEDGER'",
                f"const CASES = {json.dumps([entries for entries, _ in table])}",
                "const OUT = CASES.map((entries) => { const ledger = entries === null ? null : { entries }; try {",
                block.group(0),
                "return null } catch (e) { return e.message } })",
                "console.log(JSON.stringify(OUT))",
            )
        )
        done = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
        for (entries, expect), got in zip(table, json.loads(done.stdout), strict=True):
            if expect is None:
                assert got is None, f"{flow} refused {entries}: {got}"
            else:
                assert got and expect in got, f"{flow} over {entries}: a refusal saying {expect!r}, got {got}"
                assert f"{flow} refuses TIP" in got and ("LEDGER records" in got or not expect.startswith("records")), (
                    f"{flow}: a refusal names the tip it refuses and the ledger it read: {got}"
                )
