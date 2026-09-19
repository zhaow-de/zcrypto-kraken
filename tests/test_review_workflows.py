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
    texts = {f: (_FLOWS / f"{f}.js").read_text() for f in ("pre-review", "review", "re-review")}
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
    text = (_FLOWS / "pre-review.js").read_text()
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
    texts = {f: (_FLOWS / f"{f}.js").read_text() for f in ("pre-review", "review", "re-review")}
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
    before_the_grader = texts["pre-review"][: texts["pre-review"].index("phase('Pre-review')")]
    assert "ledger" not in before_the_grader and before_the_grader.count("throw") == 1, (
        "pre-review is the first read: it reads no ledger and refuses nothing but its arguments"
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
    """Driven, not read: a condition inverted under the right string passes every text assert above. A
    pre-review covers the one tip it read, written short or long; the branch's first pre-review is an ancestor
    of every later tip and covers none of them."""
    assert shutil.which("node") is not None, "no node on PATH, so the refusal cannot be driven"
    cases = {
        "review": [
            (None, "the ledger agent returned nothing"),
            ([], "records no pre-review"),
            ([{"kind": "pre-review", "tip": "0ancestor"}], "records no pre-review"),
            ([{"kind": "review", "tip": "abcdef012"}], "records no pre-review"),
            ([{"kind": "pre-review", "tip": "abcdef012"}], None),
            ([{"kind": "pre-review", "tip": "abcdef0123456789"}], None),
            ([{"kind": "pre-review", "tip": "abcdef0"}], None),
            ([{"kind": "pre-review", "tip": "abcde"}], "records no pre-review"),
            ([{"kind": "pre-review"}], "records no pre-review"),
        ],
        "re-review": [
            (None, "the ledger agent returned nothing"),
            ([], "records no review"),
            ([{"kind": "pre-review", "tip": "abcdef012"}], "records no review"),
            ([{"kind": "review", "tip": "abcdef012"}, {"kind": "pre-review", "tip": "0ancestor"}], "records no pre-review"),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review", "tip": "abcdef012"}], None),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review", "tip": "abcdef0"}], None),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review", "tip": "abcde"}], "records no pre-review"),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review"}], "records no pre-review"),
        ],
    }
    for flow, table in cases.items():
        text = (_FLOWS / f"{flow}.js").read_text()
        refuses = rf"^if \([^\n]*\) throw new Error\(`{flow} refuses \$\{{tip\}}: "
        block = re.search(
            refuses + r"the ledger agent returned nothing[^\n]*$.*?" + refuses + r"\$\{ledgerPath\} records no pre-review[^\n]*$",
            text,
            re.M | re.S,
        )
        assert block, (
            f"{flow}: the refusals are the block from the null-ledger throw to the pre-review refusal, anchored on their words"
        )
        program = "\n".join(
            (
                "const tip = 'abcdef012', ledgerPath = 'LEDGER'",
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
                assert f"{flow} refuses abcdef012" in got and ("LEDGER records" in got or not expect.startswith("records")), (
                    f"{flow}: a refusal names the tip it refuses and the ledger it read: {got}"
                )


def _drive_pre_review(args: dict) -> dict:
    """The whole script run as the harness runs it, its agents stubbed: each grader answers from its label, so
    what the union did with two answers is read off the return value rather than off the script's text."""
    assert shutil.which("node") is not None, "no node on PATH, so the fan-out cannot be driven"
    body = (_FLOWS / "pre-review.js").read_text().replace("export const meta", "const meta", 1)
    program = "\n".join(
        (
            "const CALLS = [], LOGS = []",
            "const part = (label) => ({ ready: label !== 'tail', verdict: `v-${label}`, graded: label === 'task-1' ? 3 : 4,",
            "  prose: [{ site: 'a.py:1', survives: label === 'task-1' ? 'keep' : 'trim', correct: true, duplicateOf: '', ship: `ship-${label}` },",
            "          { site: `${label}.py:9`, survives: 'keep', correct: true, duplicateOf: '', ship: 'a reader would not find the unit without it' }],",
            "  claims: [{ commit: label, claim: 'c', disposition: 'reproduces', by: 'b' }], probes: [], classWalk: [], reportPath: `r-${label}.md` })",
            "const agent = async (prompt, opts) => { CALLS.push({ label: opts.label, prompt })",
            "  return opts.label === 'record' ? { appended: true } : part(opts.label.replace('pre-review:', '')) }",
            "const parallel = (thunks) => Promise.all(thunks.map((t) => t()))",
            "async function wrap(args, agent, phase, parallel, pipeline, log, budget, workflow) {",
            body,
            "}",
            f"wrap({json.dumps(args)}, agent, () => {{}}, parallel, null, (l) => LOGS.push(l), null, null)",
            "  .then((out) => console.log(JSON.stringify({ out, calls: CALLS, logs: LOGS })))",
            "  .catch((e) => console.log(JSON.stringify({ error: e.message })))",
        )
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


_BRANCH = {"repo": "/r", "range": "develop..tip9abcde", "tip": "tip9abcde", "reportDir": "/r/.tmp/reads/x"}
_SLICES = [{"label": "task-1", "range": "develop..aaa1111"}, {"label": "tail", "range": "aaa1111..tip9abcde"}]


def test_a_fanned_pre_review_runs_one_grader_per_slice_and_records_the_branch_tip_once():
    """The tip rule reads ONE pre-review row at the branch tip, so a fan-out that recorded a row per slice, or
    a row at a slice's own end, would either pass a review over a tip nobody read whole or refuse one that was."""
    ran = _drive_pre_review({**_BRANCH, "ranges": _SLICES, "rulings": "/r/.tmp/sdd/progress.md", "worktree": "/r/.tmp/wt"})
    assert "error" not in ran, ran
    assert [c["label"] for c in ran["calls"]] == ["pre-review:task-1", "pre-review:tail", "record"]
    first, last, record = (c["prompt"] for c in ran["calls"])
    for prompt, slice_ in ((first, _SLICES[0]), (last, _SLICES[1])):
        assert (
            f"`git log {slice_['range']}`" in prompt
            and f"the slice `{slice_['label']}` of the branch range `develop..tip9abcde`" in prompt
        )
        assert f"/r/.tmp/reads/x/pre-review-tip9abcde-{slice_['label']}.md" in prompt
        assert f"/r/.tmp/reads/x/wt-pre-{slice_['label']} tip9abcde" in prompt
        assert "you are its only user" not in prompt, "a fanned grader was told the shared worktree is its own"
    assert "/r/.tmp/sdd/progress.md" in last and "/r/.tmp/sdd/progress.md" not in first, "the rulings go to the last slice alone"
    assert record.count('"kind":"pre-review"') == 1 and '"range":"develop..tip9abcde","tip":"tip9abcde"' in record
    out = ran["out"]
    assert out["recorded"] is True and out["graded"] == 7 and out["ready"] is False
    assert out["verdict"] == "[task-1] v-task-1 [tail] v-tail"
    rows = {row["site"]: row["ship"] for row in out["prose"]}
    assert rows == {"a.py:1": "ship-tail", "task-1.py:9": rows["task-1.py:9"], "tail.py:9": rows["tail.py:9"]}, (
        "a site two slices graded is one row, and the row asking for a change outranks the keep"
    )
    assert [c["commit"] for c in out["claims"]] == ["task-1", "tail"]


def test_a_pre_review_given_no_slices_is_the_one_grader_it_was():
    ran = _drive_pre_review({**_BRANCH, "worktree": "/r/.tmp/wt", "rulings": "/r/.tmp/sdd/progress.md"})
    assert [c["label"] for c in ran["calls"]] == ["pre-review", "record"]
    prompt = ran["calls"][0]["prompt"]
    assert "/r/.tmp/reads/x/pre-review-tip9abcde.md" in prompt and "the slice" not in prompt
    assert "you are its only user" in prompt and "/r/.tmp/sdd/progress.md" in prompt
    assert ran["out"]["graded"] == 4 and len(ran["out"]["prose"]) == 2, "the one grader's report is returned as it came"


@pytest.mark.parametrize(
    "ranges",
    [
        [],
        "develop..tip9abcde",
        [{"label": "task-1"}],
        [{"label": "Task 1", "range": "a..b"}],
        [{"label": "task-1", "range": "a..b"}, {"label": "task-1", "range": "b..c"}],
    ],
)
def test_a_malformed_fan_out_is_refused_before_any_grader_runs(ranges):
    ran = _drive_pre_review({**_BRANCH, "ranges": ranges})
    assert ran.get("error", "").startswith("args: "), ran
