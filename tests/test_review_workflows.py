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


def test_no_workflow_keeps_the_ledger_and_the_first_read_reads_none():
    for name in ("pre-review", "review", "re-review"):
        text = (_FLOWS / f"{name}.js").read_text()
        assert "Bookkeeping" not in text and "phase('Record')" not in text and "phase('Ledger')" not in text, name
    before_the_grader = (_FLOWS / "pre-review.js").read_text().split("phase('Pre-review')")[0]
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
    """Driven, not read: a condition inverted under the right string passes every text assert above; what each row
    must do is the admission comment above `sameTip` in the flow it drives."""
    assert shutil.which("node") is not None, "no node on PATH, so the refusal cannot be driven"
    ancestor = {"kind": "pre-review", "tip": "0ancestor", "sameTreeAndMessages": True}
    cases = {
        "review": [
            (None, "is not the array"),
            ({"entries": []}, "is not the array"),
            ([None], "is not the array"),
            ([], "records no pre-review"),
            ([{"kind": "pre-review", "tip": "0ancestor"}], "records no pre-review"),
            ([{"kind": "review", "tip": "abcdef012"}], "records no pre-review"),
            ([{"kind": "pre-review", "tip": "abcdef012"}], None),
            ([{"kind": "pre-review", "tip": "abcdef0123456789"}], None),
            ([{"kind": "pre-review", "tip": "abcdef0"}], None),
            ([{"kind": "pre-review", "tip": "abcde"}], "records no pre-review"),
            ([{"kind": "pre-review"}], "records no pre-review"),
            ([ancestor], None),
            ([{**ancestor, "against": "abcdef012"}], None),
            ([{**ancestor, "against": "abcdef0"}], None),
            ([{**ancestor, "against": "fedcba987"}], "was read against another tip"),
            ([{"kind": "pre-review", "tip": "abcdef012"}, {**ancestor, "against": "fedcba987"}], "was read against another tip"),
            ([{"kind": "pre-review", "tip": "0ancestor", "sameTreeAndMessages": False}], "records no pre-review"),
            ([{"kind": "review", "tip": "0ancestor", "sameTreeAndMessages": True}], "records no pre-review"),
        ],
        "re-review": [
            (None, "is not the array"),
            ({"entries": []}, "is not the array"),
            ([None], "is not the array"),
            ([], "records no review"),
            ([{"kind": "pre-review", "tip": "abcdef012"}], "records no review"),
            ([{"kind": "review", "tip": "abcdef012"}, {"kind": "pre-review", "tip": "0ancestor"}], "records no pre-review"),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review", "tip": "abcdef012"}], None),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review", "tip": "abcdef0"}], None),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review", "tip": "abcde"}], "records no pre-review"),
            ([{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review"}], "records no pre-review"),
            ([{"kind": "review", "tip": "0ancestor"}, ancestor], None),
            ([{"kind": "review", "tip": "0ancestor"}, {**ancestor, "against": "abcdef012"}], None),
            ([{"kind": "review", "tip": "0ancestor"}, {**ancestor, "against": "fedcba987"}], "was read against another tip"),
            ([{**ancestor, "against": "fedcba987"}], "was read against another tip"),
            (
                [{"kind": "review", "tip": "0ancestor"}, {"kind": "pre-review", "tip": "0ancestor", "sameTreeAndMessages": False}],
                "records no pre-review",
            ),
            ([{"kind": "review", "tip": "0ancestor", "sameTreeAndMessages": True}], "records no pre-review"),
        ],
    }
    for flow, table in cases.items():
        text = (_FLOWS / f"{flow}.js").read_text()
        refuses = rf"^if \([^\n]*\) throw new Error\(`{flow} refuses \$\{{tip\}}: "
        block = re.search(
            refuses + r"\\`ledger\\` is not the array[^\n]*$.*?" + refuses + r"\$\{ledgerPath\} records no pre-review[^\n]*$",
            text,
            re.M | re.S,
        )
        assert block, (
            f"{flow}: the refusals are the block from the ledger-shape throw to the pre-review refusal, anchored on their words"
        )
        program = "\n".join(
            (
                "const tip = 'abcdef012', ledgerPath = 'LEDGER', reportDir = 'RD'",
                f"const CASES = {json.dumps([entries for entries, _ in table])}",
                "const OUT = CASES.map((ledger) => { try {",
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


def _drive(flow: str, args: dict, answers: tuple[str, ...]) -> dict:
    """The whole script run as the harness runs it, its agents stubbed: each answers from its label, so what the
    script did with the answers is read off the return value rather than off the script's text."""
    assert shutil.which("node") is not None, "no node on PATH, so the workflow cannot be driven"
    body = (_FLOWS / f"{flow}.js").read_text().replace("export const meta", "const meta", 1)
    program = "\n".join(
        (
            "const CALLS = [], LOGS = []",
            *answers,
            "const parallel = (thunks) => Promise.all(thunks.map((t) => t()))",
            "async function wrap(args, agent, phase, parallel, pipeline, log, budget, workflow) {",
            body,
            "}",
            f"wrap({json.dumps(args)}, agent, () => {{}}, parallel, null, (l) => LOGS.push(l), null, null)",
            "  .then((out) => console.log(JSON.stringify({ out, calls: CALLS, logs: LOGS })))",
            "  .catch((e) => console.log(JSON.stringify({ error: e.message, calls: CALLS })))",
        )
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


_GRADERS = (
    "const part = (label) => ({ ready: label !== 'tail', verdict: `v-${label}`, graded: label === 'head' ? 3 : 4,",
    "  prose: [{ site: 'a.py:1', survives: label === 'head' ? 'keep' : 'trim', correct: true, duplicateOf: '', ship: `ship-${label}` },",
    "          { site: 'b.py:2', survives: label === 'head' ? 'trim' : 'cut', correct: true, duplicateOf: '', ship: label === 'head' ? 'ship-b' : '' },",
    "          { site: 'c.py:3', survives: 'cut', correct: true, duplicateOf: '', ship: '' },",
    "          { site: `${label}.py:9`, survives: 'keep', correct: true, duplicateOf: '', ship: 'a reader would not find the unit without it' }],",
    "  claims: [{ commit: label, claim: 'c', disposition: 'reproduces', by: 'b' }], probes: [], classWalk: [], reportPath: `r-${label}.md` })",
    "const twice = (r) => ({ ...r, prose: [...r.prose, { site: 'a.py:1', survives: 'cut', correct: true, duplicateOf: '', ship: '' }] })",
    "const agent = async (prompt, opts) => { CALLS.push({ label: opts.label, prompt, model: opts.model })",
    "  return opts.label === 'pre-review' ? twice(part('pre-review')) : part(opts.label.replace('pre-review:', '')) }",
)
_READERS = (
    "const finding = { severity: 'Important', path: 'a.py', line: 1, claim: 'c', evidence: 'e', consequence: 'q' }",
    "const agent = async (prompt, opts) => { CALLS.push({ label: opts.label, prompt, model: opts.model })",
    "  if (opts.label.startsWith('refute:')) return { refuted: true, reason: 'r | why' }",
    "  const prior = opts.label === 're-read' ? { prior: [{ id: 1, status: 'closed', by: 'b' }] } : {}",
    "  return { verdict: 'v', ...prior, findings: [finding], executed: [], reportPath: 'x' } }",
)


def _drive_pre_review(args: dict) -> dict:
    return _drive("pre-review", args, _GRADERS)


_BRANCH = {"repo": "/r", "range": "develop..tip9abcde", "tip": "tip9abcde", "reportDir": "/r/.tmp/reads/x"}


def test_the_graders_run_on_opus_unless_a_caller_names_another_which_is_refused():
    """The graders re-run commands and diff texts — the work the owner put on Opus on 2026-09-20; Fable keeps
    the reads, whose class walks build compositions by hand."""
    for args in (_BRANCH, {**_BRANCH, "model": "opus"}):
        ran = _drive_pre_review(args)
        assert [(c["label"], c["model"]) for c in ran["calls"]] == [("pre-review", "opus")]
    for below_or_above in ("sonnet", "fable"):
        ran = _drive_pre_review({**_BRANCH, "model": below_or_above})
        assert "floor and cap" in ran.get("error", ""), (below_or_above, ran)


_SLICES = [{"label": "head", "range": "develop..aaa1111"}, {"label": "tail", "range": "aaa1111..tip9abcde"}]


def test_a_fanned_pre_review_runs_one_grader_per_slice_and_returns_one_row_at_the_branch_tip():
    """The tip rule reads ONE pre-review row at the branch tip, so a fan-out that returned a row per slice, or
    a row at a slice's own end, would either pass a review over a tip nobody read whole or refuse one that was."""
    ran = _drive_pre_review({**_BRANCH, "ranges": _SLICES, "rulings": "/r/.tmp/sdd/progress.md", "worktree": "/r/.tmp/wt"})
    assert "error" not in ran, ran
    assert [c["label"] for c in ran["calls"]] == ["pre-review:head", "pre-review:tail"]
    first, last = (c["prompt"] for c in ran["calls"])
    for prompt, slice_ in ((first, _SLICES[0]), (last, _SLICES[1])):
        assert (
            f"`git log {slice_['range']}`" in prompt
            and f"the slice `{slice_['label']}` of the branch range `develop..tip9abcde`" in prompt
        )
        assert f"/r/.tmp/reads/x/pre-review-tip9abcde-{slice_['label']}.md" in prompt
        assert f"/r/.tmp/reads/x/wt-pre-{slice_['label']} tip9abcde" in prompt
        assert "you are its only user" not in prompt, "a fanned grader was told the shared worktree is its own"
    assert "/r/.tmp/sdd/progress.md" in last and "/r/.tmp/sdd/progress.md" not in first, "the rulings go to the last slice alone"
    out = ran["out"]
    assert out["row"] == {"kind": "pre-review", "range": "develop..tip9abcde", "tip": "tip9abcde"} and "recorded" not in out
    assert "review-ledger.py append /r/.tmp/reads/x --kind pre-review --range develop..tip9abcde --tip tip9abcde" in ran["logs"][-1]
    assert out["graded"] == 7 and out["ready"] is False
    assert out["verdict"] == "[head] v-head [tail] v-tail"
    rows = sorted((row["site"], row["survives"], row["ship"]) for row in out["prose"])
    assert [r for r in rows if r[0] == "a.py:1"] == [("a.py:1", "trim", "ship-tail")], "a change outranks a sibling slice's keep"
    assert [r for r in rows if r[0] == "b.py:2"] == [("b.py:2", "cut", ""), ("b.py:2", "trim", "ship-b")], (
        "two slices asking one site for different changes are both returned: dropping either loses a ship silently"
    )
    assert [r for r in rows if r[0] == "c.py:3"] == [("c.py:3", "cut", "")], "two slices asking one change of a site ask it once"
    assert sorted({r[0] for r in rows}) == ["a.py:1", "b.py:2", "c.py:3", "head.py:9", "tail.py:9"]
    contested = [line for line in ran["logs"] if line.startswith("CONTESTED: ")]
    assert len(contested) == 1 and contested[0].startswith("CONTESTED: 1 site(s)") and contested[0].endswith("— b.py:2"), ran[
        "logs"
    ]
    assert any("graded (summed over slices" in line for line in ran["logs"]), "the census is a sum, and the log has to say so"
    assert [c["commit"] for c in out["claims"]] == ["head", "tail"]


@pytest.mark.parametrize("absent", [{}, {"ranges": None}], ids=["left out", "null"])
def test_a_pre_review_given_no_slices_is_the_one_grader_it_was(absent):
    ran = _drive_pre_review({**_BRANCH, "worktree": "/r/.tmp/wt", "rulings": "/r/.tmp/sdd/progress.md", **absent})
    assert [c["label"] for c in ran["calls"]] == ["pre-review"]
    prompt = ran["calls"][0]["prompt"]
    assert "/r/.tmp/reads/x/pre-review-tip9abcde.md" in prompt and "the slice" not in prompt
    assert "you are its only user" in prompt and "/r/.tmp/sdd/progress.md" in prompt
    assert "graded once in the range whose commits landed that task's code" in prompt, (
        "a completed task's plan fences are graded in their own range"
    )
    assert ran["out"]["graded"] == 4 and len(ran["out"]["prose"]) == 5, "the one grader's report is returned as it came"
    # The lone grader's stub grades `a.py:1` twice with two different asks, which between slices is a contest.
    assert [row["survives"] for row in ran["out"]["prose"] if row["site"] == "a.py:1"] == ["trim", "cut"]
    assert not any("summed over slices" in line or line.startswith("CONTESTED") for line in ran["logs"]), ran["logs"]


def _whole(label):
    return [{"label": label, "range": "develop..tip9abcde"}]


@pytest.mark.parametrize(
    "ranges",
    [
        [],
        "develop..tip9abcde",
        [{"label": "head"}],
        _whole("Head Slice"),
        _whole("-task"),
        _whole("t" * 33),
        [{"label": "t", "range": "develop..aaa1111"}, {"label": "t", "range": "aaa1111..tip9abcde"}],
        # Each of the next three leaves commits of the branch range to no grader while the one row says it was read.
        [{"label": "head", "range": "develop..aaa1111"}, {"label": "tail", "range": "bbb2222..tip9abcde"}],
        [{"label": "head", "range": "develop..aaa1111"}],
        [{"label": "head", "range": "aaa1111..tip9abcde"}],
        [{"label": "empty", "range": "develop..develop"}, {"label": "tail", "range": "develop..tip9abcde"}],
    ],
)
def test_a_malformed_fan_out_is_refused_with_the_args_rule(ranges):
    ran = _drive_pre_review({**_BRANCH, "ranges": ranges})
    assert ran.get("error", "").startswith("args: "), ran


def test_the_longest_label_and_a_one_slice_cover_are_admitted():
    ran = _drive_pre_review({**_BRANCH, "ranges": _whole("t" * 32)})
    assert [c["label"] for c in ran.get("calls", [])] == ["pre-review:" + "t" * 32], ran


_PRE_REVIEWED = {"kind": "pre-review", "range": "develop..tip9abcde", "tip": "tip9abcde", "ts": "t"}
_READS = {
    "review": ({**_BRANCH, "ledger": [_PRE_REVIEWED]}, ["read:behaviour", "read:guards", "refute:1"], ["behaviour", "guards"]),
    "re-review": (
        {
            **_BRANCH,
            "prior": [{"id": 1, "severity": "Important", "path": "a.py", "line": 1, "claim": "c"}],
            "ledger": [{**_PRE_REVIEWED, "kind": "review"}, _PRE_REVIEWED],
        },
        ["re-read", "refute:1"],
        ["re-review"],
    ),
}


@pytest.mark.parametrize("flow", sorted(_READS))
def test_a_read_runs_no_bookkeeping_agent_and_returns_its_row_and_refutation(flow):
    args, labels, reports = _READS[flow]
    ran = _drive(flow, args, _READERS)
    assert "error" not in ran, ran
    assert [c["label"] for c in ran["calls"]] == labels, "every agent is a reader or a skeptic"
    assert not any("ledger" in c["prompt"] for c in ran["calls"]), "no agent is told of the ledger"
    out = ran["out"]
    assert out["row"] == {"kind": flow, "range": "develop..tip9abcde", "tip": "tip9abcde"} and "recorded" not in out
    assert out["refutation"].startswith("## Refutation\n") and "| REFUTED — r \\| why |" in out["refutation"]
    append = f"review-ledger.py append /r/.tmp/reads/x --kind {flow} --range develop..tip9abcde --tip tip9abcde --refutation "
    assert any(append in line for line in ran["logs"]), ran["logs"]
    for report in reports:
        assert any(f"--report /r/.tmp/reads/x/{report}-tip9abcde.md" in line for line in ran["logs"]), (report, ran["logs"])


@pytest.mark.parametrize("flow", sorted(_READS))
@pytest.mark.parametrize(
    "ledger", [{}, {"ledger": None}, {"ledger": {"entries": []}}], ids=["left out", "null", "the agent's shape"]
)
def test_a_read_given_no_ledger_array_refuses_before_any_agent(flow, ledger):
    args = {k: v for k, v in _READS[flow][0].items() if k != "ledger"} | ledger
    ran = _drive(flow, args, _READERS)
    assert ran.get("error", "").startswith(f"{flow} refuses tip9abcde: `ledger` is not the array"), ran
    assert "review-ledger.py read /r/.tmp/reads/x --tip tip9abcde" in ran["error"] and ran["calls"] == []
