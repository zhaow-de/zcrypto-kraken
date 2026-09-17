"""merge-gate.py: the read line must be at the floor and name the head, with exactly four exceptions -- the change-index
row commit past the tip it names, a head whose tree is that tip's tree, the ops-journal month PR, and a
dependabot branch whose every commit is the bot's -- and a keyed
branch owes its change-index row before the merge."""

from __future__ import annotations

import importlib.util
import pathlib
import random
import subprocess
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "merge-gate.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load(_SCRIPT, "merge_gate")


def _eval(pr, head_commit=None, files=None, branch_growth=(), read_commit=None):
    return gate.evaluate(pr, head_commit, files, list(branch_growth), read_commit)


TIP = "6f02667280cfbd7b76cb39d3139a5f865d995c61"
PREV = "20a3bddb1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f"
OTHER = "38f78872aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _pr(**over) -> dict:
    pr = {
        "number": 1,
        "headRefName": "feat/x",
        "baseRefName": "develop",
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "body": f"## Summary\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n- [x] done\n",
        "headRefOid": TIP,
    }
    pr.update(over)
    return pr


def _head(parents: list[str], files: list[str]) -> dict:
    return {"sha": TIP, "parents": [{"sha": p} for p in parents], "files": [{"filename": f} for f in files]}


def _stale_body(sha: str = PREV) -> str:
    return f"## Summary\n\nRead before push by: Claude Fable 5.1 at {sha[:8]}\n\n- [x] done\n"


def test_a_read_at_the_head_passes():
    assert _eval(_pr()) == []


def test_the_one_row_commit_past_the_read_passes():
    pr = _pr(body=_stale_body())
    assert _eval(pr, _head([PREV], [gate.INDEX])) == []


def _tree(commit: dict, tree: str) -> dict:
    return {**commit, "commit": {"tree": {"sha": tree}}}


def test_an_amend_that_kept_the_tree_the_read_graded_passes():
    pr = _pr(body=_stale_body())
    head = _tree(_head([PREV], ["cli/engine/executor.py"]), "t" * 40)
    assert _eval(pr, head, read_commit=_tree({"sha": PREV}, "t" * 40)) == []


def test_a_head_whose_tree_differs_from_the_read_tips_fails():
    pr = _pr(body=_stale_body())
    head = _tree(_head([PREV], ["cli/engine/executor.py"]), "t" * 40)
    fails = _eval(pr, head, read_commit=_tree({"sha": PREV}, "u" * 40))
    assert len(fails) == 1 and fails[0].startswith(f"the read named in the body covers {PREV[:8]}, not the head {TIP[:8]}")
    assert len(_eval(pr, head)) == 1  # the read tip's commit not fetched: no tree to compare, so no pass


def test_a_row_commit_that_also_touches_another_file_fails():
    pr = _pr(body=_stale_body())
    fails = _eval(pr, _head([PREV], [gate.INDEX, "cli/engine/executor.py"]))
    assert len(fails) == 1 and fails[0].startswith(f"the read named in the body covers {PREV[:8]}, not the head {TIP[:8]}")


def test_a_second_commit_past_the_read_fails():
    pr = _pr(body=_stale_body())
    assert len(_eval(pr, _head([OTHER], [gate.INDEX]))) == 1


def test_a_merge_commit_past_the_read_fails():
    pr = _pr(body=_stale_body())
    assert len(_eval(pr, _head([PREV, OTHER], [gate.INDEX]))) == 1


def test_a_stale_read_with_no_head_commit_to_inspect_fails():
    assert len(_eval(_pr(body=_stale_body()))) == 1


JOURNAL_PR = {"headRefName": "ops-journal", "body": "## 2026-09\n\n- [x] CI green\n"}

BOT = [{"authors": [{"login": "dependabot[bot]"}]}]
BUMP_PR = {"headRefName": "dependabot/uv/develop/polars-1.44.2", "body": "Bumps polars.\n\n- [x] done\n"}


def test_the_exemption_is_reachable_from_the_fetch_the_gate_actually_makes():
    """The arm's input has to be in FIELDS, or it refuses every PR of that shape instead of exempting one.

    The case below builds its PR from `FIELDS` alone, so a key the arm reads and `main()` does not fetch
    cannot be smuggled in by the test: that is exactly how the arm shipped once refusing every dependabot
    PR while four green cases and four probe verdicts said it exempted them."""
    values = {"headRefName": "dependabot/uv/develop/polars-1.44.2", "body": "Bumps polars.\n", "headRefOid": TIP, "commits": BOT}
    # Only what the fetch returns. `update()` puts `commits` back whether or not FIELDS asks for it, which is
    # how the first version of this case passed while the gate refused every dependabot PR: the probe
    # SURVIVED and said so.
    bump = {key: values.get(key) for key in gate.FIELDS.split(",")}
    assert "commits" in bump, "FIELDS does not fetch `commits`, so the dependabot arm refuses every such PR"
    assert gate.read_line_fails(bump, None, ["uv.lock"]) == []


def test_a_dependabot_bump_with_no_fix_commit_needs_no_read_line():
    """`.claude/skills/dependabot`: a PR with no fix commit needs no read, and §2d's squash bypasses this gate
    anyway -- so the arm exists for the counter, which applies this function to every merged PR."""
    assert _eval(_pr(**BUMP_PR, commits=BOT), files=["uv.lock"]) == []


def test_a_dependabot_pr_carrying_a_fix_commit_takes_every_arm():
    """The skill grants the exemption to a PR with NO fix commit; one commit of mine is what withdraws it."""
    mine = BOT + [{"authors": [{"login": "claude"}]}]
    fails = _eval(_pr(**BUMP_PR, commits=mine), files=["uv.lock"])
    assert len(fails) == 1 and fails[0].startswith("no 'Read before push by:")


def test_a_dependabot_pr_with_no_commit_list_fails():
    """Refused rather than exempted, as the ops-journal arm refuses a missing file list: an exemption that
    cannot be scoped is not one."""
    fails = _eval(_pr(**BUMP_PR), files=["uv.lock"])
    assert len(fails) == 1 and "commit list was not fetched" in fails[0]


def test_a_dependabot_branch_with_an_empty_commit_list_is_not_exempt():
    """`all()` over an empty list is True, which would exempt a PR whose commits came back as none."""
    fails = _eval(_pr(**BUMP_PR, commits=[]), files=["uv.lock"])
    assert len(fails) == 1 and fails[0].startswith("no 'Read before push by:")


def test_the_ops_journal_month_pr_needs_no_read_line():
    assert _eval(_pr(**JOURNAL_PR), files=["docs/reference/ops-journal/2026-09.md"]) == []


def test_a_journal_pr_carrying_a_foreign_file_takes_every_arm():
    files = ["docs/reference/ops-journal/2026-09.md", "cli/engine/executor.py"]
    fails = _eval(_pr(**JOURNAL_PR), files=files)
    assert len(fails) == 1 and fails[0].startswith("no 'Read before push by:")
    haiku = _pr(headRefName="ops-journal", body=f"Read before push by: Claude Haiku 4.5 at {TIP}\n\n- [x] done\n")
    assert len(_eval(haiku, files=files)) == 1 and "the floor is Claude Opus" in _eval(haiku, files=files)[0]


def test_a_journal_pr_with_no_file_list_fails():
    assert len(_eval(_pr(**JOURNAL_PR))) == 1


def test_a_missing_or_placeholder_line_fails():
    unrecorded = "no 'Read before push by: <model> at <sha>' line in the body: the whole-branch read is unrecorded"
    assert _eval(_pr(body="## Summary\n\n- [x] done\n")) == [unrecorded]
    assert _eval(_pr(body=f"Read before push by: <model> at {TIP}\n")) == [unrecorded]
    assert _eval(_pr(body="Read before push by: Claude Fable 5.1\n")) == [unrecorded]


def _read_by(model: str) -> str:
    return f"## Summary\n\nRead before push by: {model} at {TIP}\n\n- [x] done\n"


def test_a_read_below_the_floor_fails():
    fails = _eval(_pr(body=_read_by("Claude Haiku 4.5")), files=[])
    assert len(fails) == 1 and "the floor is Claude Opus" in fails[0]
    assert len(_eval(_pr(body=_read_by("Claude Sonnet 4.6")), files=[])) == 1


def test_an_opus_read_passes_off_the_guarded_paths():
    pr = _pr(body=_read_by("Claude Opus 4.8"))
    assert _eval(pr, files=["cli/costs/schedule.py", "docs/reference/fleet.md", "infra/ansible/roles/ops/tasks/main.yml"]) == []


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        ".claude/skills/open-pr/SKILL.md",
        "cli/engine/executor.py",
        "cli/capture/daemon.py",
        "infra/ansible/roles/capture/tasks/main.yml",
        "infra/ansible/roles/engine/tasks/main.yml",
    ],
)
def test_an_opus_read_on_a_guarded_path_fails(path):
    fails = _eval(_pr(body=_read_by("Claude Opus 4.8")), files=["cli/costs/schedule.py", path])
    assert len(fails) == 1 and path in fails[0] and "the floor there is Claude Fable" in fails[0]
    assert "Fable floor substituted by Opus" in fails[0], "the refusal names the one line that lifts it"


def _read_by_opus_with_substitution(reason: str) -> str:
    return f"## Summary\n\nRead before push by: Claude Opus 5 at {TIP}\n\nFable floor substituted by Opus: {reason}\n\n- [x] done\n"


@pytest.mark.parametrize("path", ["CLAUDE.md", ".claude/rules/fleet-deploys.md", "cli/engine/journal.py", "cli/capture/daemon.py"])
def test_the_substitution_line_admits_an_opus_read_on_a_guarded_path(path):
    """The Fable floor is substitutable and only in the open: the body says the substitution happened and why, so
    whoever opens the PR afterwards reads it there rather than having to notice a gate nobody ran."""
    body = _read_by_opus_with_substitution("the account's Fable limit is reached; the owner authorised Opus")
    assert _eval(_pr(body=body), files=["cli/costs/schedule.py", path]) == []


def test_the_substitution_line_needs_a_reason():
    """A bare marker would be a switch anyone could flip without saying anything; the reason is the whole point."""
    body = f"## Summary\n\nRead before push by: Claude Opus 5 at {TIP}\n\nFable floor substituted by Opus:\n\n- [x] done\n"
    fails = _eval(_pr(body=body), files=["cli/engine/journal.py"])
    assert len(fails) == 1 and "the floor there is Claude Fable" in fails[0]


def test_the_substitution_line_does_not_lower_the_floor_below_opus():
    """It substitutes for FABLE, never for the Opus floor every PR has: a cheaper read stays refused with it."""
    body = (
        f"## Summary\n\nRead before push by: Claude Haiku 4.5 at {TIP}\n\n"
        f"Fable floor substituted by Opus: the Fable limit is reached\n\n- [x] done\n"
    )
    fails = _eval(_pr(body=body), files=["cli/engine/journal.py"])
    assert len(fails) == 1 and "the floor is Claude Opus" in fails[0]


@pytest.mark.parametrize("reason", ["<reason>", "TODO", "tbd", "N/A", "none", "x", ".", "----", "reason", "why", "short"])
def test_a_reason_nobody_wrote_is_no_reason(reason):
    """The placeholder is the string this repo prints in its own refusal message and in CLAUDE.md, so a
    copy-paste of the instruction would otherwise clear the floor; the filler tokens arrive the same way."""
    fails = _eval(_pr(body=_read_by_opus_with_substitution(reason)), files=["cli/engine/journal.py"])
    assert len(fails) == 1 and "the floor there is Claude Fable" in fails[0]


@pytest.mark.parametrize(
    ("shape", "body_tpl"),
    [
        ("an HTML comment, which the rendered PR hides", "## Summary\n\n{read}\n\n<!--\n{line}\n-->\n\n- [x] done\n"),
        ("a fenced block, which is a quotation of code", "## Summary\n\n{read}\n\n```\n{line}\n```\n\n- [x] done\n"),
        ("a quoted line, which is somebody else's text", "## Summary\n\n{read}\n\n> {line}\n\n- [x] done\n"),
    ],
)
def test_a_substitution_a_reader_cannot_see_does_not_lift_the_floor(shape, body_tpl):
    """The whole point of the line is that it is visible where the merge decision is read. The pull-request
    template ships an HTML comment block, so this is the likeliest accident, not a contrived one."""
    body = body_tpl.format(
        read=f"Read before push by: Claude Opus 5 at {TIP}",
        line="Fable floor substituted by Opus: the account's Fable limit is reached",
    )
    fails = _eval(_pr(body=body), files=["cli/engine/journal.py"])
    assert len(fails) == 1 and "the floor there is Claude Fable" in fails[0], shape


@pytest.mark.parametrize(
    ("shape", "body"),
    [
        (
            "an unterminated comment, which hides the rest of the rendered page",
            "## Summary\n\n{read}\n\n<!-- note to self\n{line}\n",
        ),
        ("a marker under an unterminated opener", "## Summary\n\n{read}\n\n<!-- \n\n{line}\n\nmore prose\n"),
        (
            "a ``` block nested inside a ```` block, which is how this feature gets documented",
            "## Summary\n\n{read}\n\n````\n```\n{line}\n```\n````\n\n- [x] done\n",
        ),
        ("an unterminated fence, which renders the rest as code", "## Summary\n\n{read}\n\n```\n{line}\n"),
        (
            "a <details> block, collapsed until somebody clicks it",
            "## Summary\n\n{read}\n\n<details><summary>why</summary>\n{line}\n</details>\n\n- [x] done\n",
        ),
    ],
)
def test_no_delimiter_shape_hides_a_substitution_from_the_gate(shape, body):
    """The first pass at this used two regexes and each of these got past it. A renderer keeps state; so does the
    walk now, which is why an unterminated opener hides to the end of the document here as it does there."""
    filled = body.format(
        read=f"Read before push by: Claude Opus 5 at {TIP}",
        line="Fable floor substituted by Opus: the account's Fable limit is reached",
    )
    fails = _eval(_pr(body=filled), files=["cli/engine/journal.py"])
    assert fails, shape
    assert any("Claude Fable" in f or "unrecorded" in f for f in fails), (shape, fails)


@pytest.mark.parametrize(
    "reason",
    [
        "&lt;reason&gt;",  # renders as the placeholder itself, so the `<` check has to see through the escape
        "\uff34\uff2f\uff24\uff2f fill in later",  # fullwidth TODO, which NFKC folds onto the token
        "aaaaaaaaaaaa",
        "!!!!!!!!!!!!",
        "-------------",
        ".... ---- ....",
        "fill in",
        "placeholder",
    ],
)
def test_a_reason_with_no_content_does_not_lift_the_floor(reason):
    """Length was the wrong bar: it admitted a run of one character and rejected an honest short answer. The bar
    is distinct alphanumerics, after unescaping, NFKC and dropping the zero-width padding."""
    fails = _eval(_pr(body=_read_by_opus_with_substitution(reason)), files=["cli/engine/journal.py"])
    assert len(fails) == 1 and "the floor there is Claude Fable" in fails[0]


@pytest.mark.parametrize("reason", ["no Fable", "Fable\u914d\u984d\u5df2\u7528\u76e1", "quota exhausted"])
def test_a_short_honest_reason_in_any_script_lifts_the_floor(reason):
    """The mirror of the case above, and the reason the bar is not length: two true words, or a dense script, must
    not be refused for being brief."""
    assert _eval(_pr(body=_read_by_opus_with_substitution(reason)), files=["cli/engine/journal.py"]) == []


def test_a_leftover_placeholder_line_does_not_refuse_the_filled_one():
    """Once the line is instructed as a fill-in template, a leftover above a filled one is the natural accident:
    every occurrence is considered, not the first."""
    body = (
        f"## Summary\n\nRead before push by: Claude Opus 5 at {TIP}\n\n"
        "Fable floor substituted by Opus: <reason>\n\n"
        "Fable floor substituted by Opus: the account's Fable limit is reached\n\n- [x] done\n"
    )
    assert _eval(_pr(body=body), files=["cli/engine/journal.py"]) == []


@pytest.mark.parametrize(
    ("shape", "above"),
    [
        ("an unterminated tilde fence", "~~~"),
        ("a tilde fence whose info string carries backticks, which CommonMark allows", "~~~`js`"),
        ("a <details> that comments out its own closer, so the element never closes", "<details><!--</details>-->"),
    ],
)
def test_no_delimiter_line_above_the_substitution_leaves_it_counting(shape, above):
    """Every unsafe divergence three rounds of review found put the marker below a delimiter line — a tilde fence
    the pattern declined, a details element that commented out its own closer — so the prefix rule refuses on the
    delimiter itself rather than on a judgement about what it does."""
    body = (
        f"## Summary\n\nRead before push by: Claude Opus 5 at {TIP}\n\n{above}\n\n"
        "Fable floor substituted by Opus: the account's Fable limit is reached\n\n- [x] done\n"
    )
    assert _eval(_pr(body=body), files=["cli/engine/journal.py"]), shape


def test_a_one_line_comment_above_the_line_leaves_it_counting():
    """The repo's own pull-request template ships `<!-- A few sentences mirroring the spec's goal. -->` above both
    lines, and a comment that opens and closes on one line hides nothing below it under any parse. Breaking the
    prefix on it refused a template-derived body, and the refusal told the author to move a line that was already
    where it belonged."""
    body = (
        f"## Summary\n\n<!-- A few sentences mirroring the spec's goal. -->\n\n"
        f"Read before push by: Claude Opus 5 at {TIP}\n\n"
        "Fable floor substituted by Opus: the account's Fable limit is reached\n\n- [x] done\n"
    )
    assert _eval(_pr(body=body), files=["cli/engine/journal.py"]) == []


def test_a_one_line_details_above_the_line_still_refuses():
    """Not symmetric, and the asymmetry is measured: a one-line `<details>` can comment out its own closer, so
    the element stays open and everything below renders collapsed."""
    body = (
        f"## Summary\n\n<details><!--</details>-->\n\nRead before push by: Claude Opus 5 at {TIP}\n\n"
        "Fable floor substituted by Opus: the account's Fable limit is reached\n\n- [x] done\n"
    )
    assert _eval(_pr(body=body), files=["cli/engine/journal.py"])


def test_a_terminated_fence_above_the_line_refuses_it_too():
    """The cost of the plain-prefix rule, stated rather than hidden: a TERMINATED fence between the read line and
    the substitution refuses as well. Three review rounds found seven walk-versus-renderer divergences, every
    unsafe one with the marker below a delimiter line, so the prefix does not try to tell the two apart."""
    body = (
        f"## Summary\n\nRead before push by: Claude Opus 5 at {TIP}\n\n"
        "```\ngh pr view 1\n```\n\n"
        "Fable floor substituted by Opus: the account's Fable limit is reached\n\n- [x] done\n"
    )
    fails = _eval(_pr(body=body), files=["cli/engine/journal.py"])
    assert len(fails) == 1 and "plain prefix" in fails[0], fails


def test_the_refusal_says_when_the_line_is_there_but_hidden():
    """An author looking straight at the line needs to be told it is invisible, not that it is missing."""
    body = f"## Summary\n\n<!--\nRead before push by: Claude Fable 5.1 at {TIP}\n-->\n\n- [x] done\n"
    fails = _eval(_pr(body=body), files=["cli/costs/schedule.py"])
    assert len(fails) == 1 and "hidden from the rendered page" in fails[0]


def test_the_refusal_distinguishes_a_bad_reason_from_a_missing_line():
    """The other diagnostic: the line is visible and the reason is not one, which is a different fix."""
    fails = _eval(_pr(body=_read_by_opus_with_substitution("TODO")), files=["cli/engine/journal.py"])
    assert len(fails) == 1 and "its reason is the placeholder" in fails[0]


@pytest.mark.parametrize(
    ("shape", "body"),
    [
        (
            "a </details> inside a code span, which the renderer escapes rather than honouring",
            "## Summary\n\n{read}\n\n<details><summary>why</summary>\n\nthe `</details>` tag closes it\n\n{line}\n</details>\n",
        ),
        ("a fence opener whose info string carries <!--", "## Summary\n\n{read}\n\n```<!--\n-->\n{line}\n```\n"),
        ("a fence opener whose info string carries <details", "## Summary\n\n{read}\n\n```<details\n</details>\n{line}\n```\n"),
    ],
)
def test_a_closer_the_renderer_does_not_honour_does_not_reveal_the_line(shape, body):
    """The second pass at the walk got past on both: a closer written inside a code span left the hidden state,
    and a fence opener carrying a comment opened the comment instead of the fence. A renderer settles fences
    before inline markup exists, and a code span is content — so the walk does too."""
    filled = body.format(
        read=f"Read before push by: Claude Opus 5 at {TIP}",
        line="Fable floor substituted by Opus: the account's Fable limit is reached",
    )
    assert _eval(_pr(body=filled), files=["cli/engine/journal.py"]), shape


@pytest.mark.parametrize(
    ("shape", "above"),
    [
        ("an inline `<!--` in prose, which renders as text", "the walker treats `<!--` as an opener"),
        ("an inline `<details>` in prose", "about `<details>` blocks and what they hide"),
        ("a four-space-indented fence, which is an indented code block", "    ```"),
        ("a line-initial ```x``` span, whose info string has a backtick", "```gh pr view```"),
        ("a comment closed with --!>, which every browser honours", "<!-- a note --!>"),
    ],
)
def test_prose_about_the_gate_does_not_refuse_the_pr_it_sits_in(shape, above):
    """The mirror failure, and the likeliest one on this very branch: a PR body that DISCUSSES comments and fences
    must not lose the lines it carries. Each of these discarded the rest of the body once. The prose sits BELOW
    the two lines, which is where a PR puts its discussion and where the plain-prefix rule leaves it alone."""
    body = (
        f"## Summary\n\nRead before push by: Claude Opus 5 at {TIP}\n\n"
        f"Fable floor substituted by Opus: the account's Fable limit is reached\n\n{above}\n\n- [x] done\n"
    )
    assert _eval(_pr(body=body), files=["cli/engine/journal.py"]) == [], shape


def test_a_comment_above_the_read_line_closed_the_html_way_still_records_the_read():
    """`--!>` closes a comment in every browser, so the page shows what follows and the read line counts. The
    read line is judged by the walk alone, which is why a construct above it is not fatal the way it is for the
    substitution."""
    body = f"## Summary\n\n<!-- a note --!>\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n- [x] done\n"
    assert _eval(_pr(body=body), files=["cli/engine/journal.py"]) == []


def test_a_read_line_below_a_details_that_hides_it_is_no_recorded_read():
    """The hole this closes, measured by the fourth safety read: a one-line `<details>` that comments out its own
    closer leaves the element open, so the page renders the read line collapsed while a walk shows it. The read
    line is judged in the plain prefix for the same reason the substitution is."""
    body = f"## Summary\n\n<details><!--</details>-->\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n- [x] done\n"
    fails = _eval(_pr(body=body), files=["cli/costs/schedule.py"])
    assert len(fails) == 1 and "plain prefix" in fails[0], fails


def test_a_read_line_below_a_fence_is_refused_and_told_why():
    """The cost of extending the prefix to the read line, stated: a body that opens a fence above its read line
    is refused, and the refusal names the prefix rather than claiming the line is missing."""
    body = f"## Summary\n\n```\ngh pr view 1\n```\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n- [x] done\n"
    fails = _eval(_pr(body=body), files=["cli/costs/schedule.py"])
    assert len(fails) == 1 and "plain prefix" in fails[0], fails


@pytest.mark.parametrize(
    "model",
    ["Claude Opus or Claude Fable", "Claude Fable or Claude Opus", "Claude Opus, Claude Fable", "Claude Opus 5 or anyone"],
)
def test_a_read_line_naming_two_readers_records_no_read(model):
    """The template's placeholder minus its markers is exactly this shape, and the floor matched its prefix."""
    body = f"## Summary\n\nRead before push by: {model} at {TIP}\n\n- [x] done\n"
    fails = _eval(_pr(body=body), files=["cli/costs/schedule.py"])
    assert len(fails) == 1 and "more than one reader" in fails[0], fails


def test_the_template_as_shipped_records_no_read():
    """A minimal edit of the placeholder must not produce a line the gate accepts, so the shipped line and its
    marker-stripped form are both refused."""
    template = (pathlib.Path(__file__).resolve().parents[1] / ".github" / "pull_request_template.md").read_text()
    line = next(ln for ln in template.splitlines() if ln.startswith("Read before push by:"))
    stripped = line.replace("<model — ", "").replace(">", "").replace("<sha", TIP)
    for candidate in (line, stripped):
        fails = _eval(_pr(body=f"## Summary\n\n{candidate}\n\n- [x] done\n"), files=["cli/costs/schedule.py"])
        assert fails, f"the gate accepted the template's read line: {candidate!r}"


def test_a_read_line_a_reader_cannot_see_is_no_recorded_read():
    """The same stripping applies to the read line: a read claimed inside a comment is a read nobody can check."""
    body = f"## Summary\n\n<!--\nRead before push by: Claude Fable 5.1 at {TIP}\n-->\n\n- [x] done\n"
    fails = _eval(_pr(body=body), files=["cli/costs/schedule.py"])
    assert len(fails) == 1 and "the whole-branch read is unrecorded" in fails[0]


def test_the_substitution_line_is_inert_where_no_guarded_path_is_touched():
    """It lifts one arm and adds nothing: a PR that never needed a Fable read is judged exactly as before."""
    body = _read_by_opus_with_substitution("not needed here")
    assert _eval(_pr(body=body), files=["cli/costs/schedule.py"]) == []


def test_a_look_alike_path_is_not_guarded():
    pr = _pr(body=_read_by("Claude Opus 4.8"))
    assert _eval(pr, files=["cli/engine_tools/x.py", "docs/CLAUDE.md", "infra/ansible/roles/capture-mirror/tasks/main.yml"]) == []


def test_an_opus_read_with_no_file_list_fails():
    assert len(_eval(_pr(body=_read_by("Claude Opus 4.8")))) == 1


def test_every_other_arm_still_fires():
    pr = _pr(
        baseRefName="main",
        isDraft=True,
        mergeable="UNKNOWN",
        mergeStateStatus="BLOCKED",
        reviewDecision="CHANGES_REQUESTED",
        statusCheckRollup=[{"conclusion": "FAILURE"}, {"state": "PENDING"}],
        body=f"Read before push by: Claude Fable 5.1 at {TIP}\n\n- [ ] not yet\n",
    )
    fails = _eval(pr)
    assert [f.split(" ")[0] for f in fails] == [
        "base",
        "PR",
        "mergeable='UNKNOWN'",
        "mergeStateStatus=BLOCKED",
        "reviewDecision=CHANGES_REQUESTED",
        "1",
        "1",
        "PR",
    ]


def test_the_fable_paths_subcommand_prints_the_gate_s_own_list():
    """CLAUDE.md names this command instead of repeating the list, so what it prints is what the gate enforces."""
    done = subprocess.run([sys.executable, str(_SCRIPT), "--fable-paths"], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.split("\n")[:-1] == list(gate.FABLE_PATHS)
    assert "cli/engine/" in gate.FABLE_PATHS and ".claude/" in gate.FABLE_PATHS


def test_a_commit_growing_the_guidance_unstated_fails_the_gate():
    growth = [
        "1a2b3c4d claude(rules): x: the always-loaded guidance grows by 40 bytes against its parent and the message does not say so"
    ]
    assert _eval(_pr(), branch_growth=growth) == growth


def test_the_range_mode_s_refusals_are_prefixed_with_the_commit_and_a_run_failure_is_not(monkeypatch):
    def fake_run(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            return gate.subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "merge-base"]:
            return gate.subprocess.CompletedProcess(args, 0, "a" * 40 + "\n", "")
        return gate.subprocess.CompletedProcess(
            args,
            1,
            "guidance-guard: refused over a..b\n  - 1a2b3c4d claude(rules): x: the always-loaded guidance grows by 40 bytes\n",
            "",
        )

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate.branch_growth("develop", "feat/x", "b" * 40) == [
        "a commit fails the guidance guard's range walk — 1a2b3c4d claude(rules): x: the always-loaded guidance grows by 40 bytes"
    ]


def test_a_timeout_anywhere_and_a_silent_merge_base_failure_are_refusals_too(monkeypatch):
    calls = []

    def guard_times_out(args, **kwargs):
        calls.append(args[:2])
        if args[:2] == ["git", "fetch"]:
            return gate.subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "merge-base"]:
            return gate.subprocess.CompletedProcess(args, 0, "a" * 40 + "\n", "")
        raise gate.subprocess.TimeoutExpired(args, 300)

    monkeypatch.setattr(gate.subprocess, "run", guard_times_out)
    fails = gate.branch_growth("develop", "feat/x", "b" * 40)
    assert len(calls) == 3 and len(fails) == 1 and fails[0].startswith("the branch could not be checked commit by commit: ")

    def orphan(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            return gate.subprocess.CompletedProcess(args, 0, "", "")
        raise gate.subprocess.CalledProcessError(1, args, output="", stderr="")  # merge-base: no output, exit 1

    monkeypatch.setattr(gate.subprocess, "run", orphan)
    assert gate.branch_growth("develop", "feat/x", "b" * 40) == [
        "the branch could not be checked commit by commit: no merge base between origin/develop and bbbbbbbb"
    ]

    def gone(args, **kwargs):
        raise gate.subprocess.CalledProcessError(128, args, output="", stderr="fatal: couldn't find remote ref gone/branch\n")

    monkeypatch.setattr(gate.subprocess, "run", gone)
    assert gate.branch_growth("develop", "gone/branch", "b" * 40) == [
        "the branch could not be checked commit by commit: fatal: couldn't find remote ref gone/branch"
    ]


def test_an_unchecked_branch_growth_fails_the_gate():
    fails = gate.evaluate(_pr(), None, None, None)
    assert len(fails) == 1 and "was not checked commit by commit" in fails[0]


def test_a_branch_that_cannot_be_fetched_is_one_refusal_not_a_crash(monkeypatch):
    def raise_fetch(*args, **kwargs):
        raise gate.subprocess.CalledProcessError(128, args[0], output="", stderr="fatal: couldn't find remote ref gone/branch\n")

    monkeypatch.setattr(gate.subprocess, "run", raise_fetch)
    fails = gate.branch_growth("develop", "gone/branch", "0" * 40)
    assert fails == ["the branch could not be checked commit by commit: fatal: couldn't find remote ref gone/branch"]


def test_a_keyed_branch_with_no_row_is_refused() -> None:
    fails = gate.index_row_fails(_pr(number=99999, headRefName="docs/t0210-register-the-thing"))
    assert len(fails) == 1 and "has no `| #99999 ` row" in fails[0], fails


def test_an_unkeyed_branch_owes_no_row() -> None:
    """Most branches carry no key; this arm asks the branch name only, so a key spelled only in the title is not its business."""
    assert gate.index_row_fails(_pr(number=99999, headRefName="claude/w16-skills-pass")) == []


def test_a_keyed_branch_whose_row_exists_passes() -> None:
    """A pass needs both a key and a row, so it is driven through a merged PR the index really holds."""
    assert gate.index_row_fails(_pr(number=514, headRefName="fix/t0193-nonfinite-snapshot-close")) == []


def test_the_branch_key_grammar_mirrors_the_tests_grammar() -> None:
    """Generated rather than sampled: a list of spellings cannot cover a digit range, so a widened `_ITER`
    keys `iter-0664` in one grammar and not the other with the list still green."""
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from test_change_index import _keys

    rng = random.Random(20260914)
    heads = ["iter-", "ITER-", "Iter-", "T", "t", "spec-", "v", ""]
    for _ in range(3000):
        digits = "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 7)))
        branch = (
            rng.choice(["", "feat/", "docs/", "chore/x-", "claude/"])
            + rng.choice(heads)
            + digits
            + rng.choice(["", "-tail", "/more"])
        )
        assert bool(gate.BRANCH_KEY.search(branch)) == any(_keys(branch)), branch


def test_evaluate_carries_the_index_row_arm() -> None:
    """Wired into `evaluate`, not merely defined: unwiring it leaves every other case in this file green."""
    fails = _eval(_pr(number=99999, headRefName="docs/t0210-register-the-thing"))
    assert any("change-index" in f for f in fails), fails


def test_an_unchecked_box_quoted_in_a_code_span_is_not_a_box() -> None:
    """The marker inside a code span renders as text; the old substring test read it as an open item."""
    body = f"## Summary\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\nthe gate parses `- [ ]` items\n\n- [x] done\n"
    assert not [f for f in _eval(_pr(body=body)) if "checklist" in f]


def test_an_unchecked_box_in_a_fenced_block_is_not_a_box() -> None:
    """A fenced block is code to a reader, so a list marker inside it is not a checklist item."""
    body = f"## Summary\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n```\n- [ ] not a box\n```\n\n- [x] done\n"
    assert not [f for f in _eval(_pr(body=body)) if "checklist" in f]


def test_a_real_unchecked_box_still_fails() -> None:
    """The two exemptions above must not have widened into ignoring the box the arm exists to catch."""
    body = f"## Summary\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n- [ ] not done\n"
    assert [f for f in _eval(_pr(body=body)) if "checklist" in f]


def _boxed(body: str) -> bool:
    return any(
        "checklist" in f for f in _eval(_pr(body=f"## Summary\n\nRead before push by: Claude Fable 5.1 at {TIP}\n\n{body}\n"))
    )


def test_a_real_box_inside_details_is_still_a_box() -> None:
    """GitHub renders a task list inside `<details>`; hiding it was the read-line rule leaking into gate 6."""
    assert _boxed("<details>\n<summary>later</summary>\n\n- [ ] real\n\n</details>")


def test_a_real_box_on_a_quoted_line_is_still_a_box() -> None:
    """A blockquote is visible on the page, so a box inside it counts, its marker stripped before the match."""
    assert _boxed("> - [ ] real") and _boxed("> > - [ ] nested quote")


def test_the_star_and_numbered_spellings_are_boxes() -> None:
    """The arm widened past `- [ ]` to every list marker CommonMark renders; nothing pinned the widening."""
    assert _boxed("* [ ] real") and _boxed("+ [ ] real") and _boxed("1. [ ] real") and _boxed("1) [ ] real")


def test_a_nested_box_is_a_box() -> None:
    assert _boxed("- outer\n  - [ ] inner")


def test_a_marker_that_is_only_text_is_not_a_box() -> None:
    """A code span at the line's start, and a list item whose content is a code span, both render as text."""
    assert not _boxed("`- [ ]` is the marker") and not _boxed("- `[ ]` is the marker's text")


def test_a_box_inside_a_details_html_block_is_literal_text() -> None:
    """With no blank line after `<summary>`, CommonMark keeps the HTML block open, and GitHub draws no box there."""
    assert not _boxed("<details>\n<summary>later</summary>\n- [ ] literal\n</details>")
    assert _boxed("<details>\n<summary>later</summary>\n\n- [ ] real\n\n</details>")


def test_a_box_right_after_a_closing_details_tag_is_literal_text() -> None:
    """The closing tag opens an HTML block of its own, to the next blank line."""
    assert not _boxed("<details>\n\n- [x] done\n\n</details>\n- [ ] literal") and _boxed(
        "<details>\n\n- [x] done\n\n</details>\n\n- [ ] real"
    )


def test_a_quoted_fence_or_comment_is_still_code() -> None:
    """A fenced block or an HTML comment inside a blockquote renders as code or nothing, never as a task item --
    while a plain quoted box in the same body is still a box, so this case fails in both directions."""
    assert (
        not _boxed("> ```\n> - [ ] in quoted code\n> ```")
        and not _boxed("> <!--\n> - [ ] in quoted comment\n> -->")
        and not _boxed("> > ```\n> > - [ ] nested\n> > ```")
    )
    assert _boxed("> ```\n> - [ ] in quoted code\n> ```\n\n> - [ ] real")


def test_a_quoted_fence_inside_a_fence_does_not_close_it() -> None:
    """Fence content is literal: a `> ```` line inside an open fence is code, not a quoted fence closing the block."""
    assert not _boxed("```\n> ```\n- [ ] still inside the fence\n```")


def test_a_quoted_fence_or_comment_ends_with_its_blockquote() -> None:
    """Neither takes lazy continuation, so the blockquote's end closes it and a box after it is a rendered box."""
    assert (
        _boxed("> ```\n> code\n\n- [ ] real") and _boxed("> <!--\n> hidden\n\n- [ ] real") and _boxed("> ```\n> code\n- [ ] real")
    )
    assert not _boxed("> ```\n> - [ ] in quoted code\n\n> more quote")


def test_a_quoted_fence_closed_by_an_unquoted_fence_line_opens_a_new_fence() -> None:
    """The unquoted line ends the blockquote and starts a top-level fence that runs on, so nothing after it is a box."""
    assert not _boxed("> ```\n```\n- [ ] after")


def test_a_quoted_html_block_ends_with_its_blockquote() -> None:
    """An HTML block takes no lazy continuation either, so the blockquote's end closes it and a box after it counts."""
    assert _boxed("> <details>\n- [ ] real") and not _boxed("> <details>\n> - [ ] literal")


def test_a_construct_two_quotes_deep_is_closed_by_a_line_one_quote_deep() -> None:
    """A blockquote ends at the first line with fewer markers than it opened with, not only at an unquoted line."""
    assert _boxed("> > ```\n> - [ ] real") and _boxed("> > <!--\n> - [ ] real")
    assert not _boxed("> > ```\n> > - [ ] in code\n> more") and _boxed("> > ```\n> > - [ ] in code\n> > ```\n> > - [ ] later")


def test_a_quote_marker_alone_is_content_to_an_unquoted_html_block() -> None:
    """A `>`-only line is blank inside a quoted block and content inside an unquoted one, so each is measured at its own depth."""
    assert (
        not _boxed("<details>\n>\n- [ ] box") and _boxed("> <details>\n>\n> - [ ] x") and not _boxed("> <details>\n> >\n> - [ ] x")
    )


def test_a_deeper_quoted_fence_line_inside_a_quoted_fence_is_content() -> None:
    """A fence opened one quote deep is closed by a one-quote line, not by a two-quote one, which is code to it."""
    assert not _boxed("> ```\n> > ```\n> - [ ] after") and _boxed("> ```\n> ```\n> - [ ] after")


def test_the_tail_of_a_block_comments_closing_line_is_not_a_box() -> None:
    """The line carrying `-->` is the HTML block's last line, so a marker after it is raw text on the page, not a task
    item; on the next line it is a box again."""
    assert (
        not _boxed("<!--\nhidden\n--> - [ ] box")
        and not _boxed("> <!--\n> hidden\n> --> - [ ] box")
        and _boxed("<!--\nhidden\n-->\n- [ ] box")
    )


def test_an_html_block_or_comment_admits_at_most_three_columns_of_indent() -> None:
    """Four spaces, or a tab at the line's start, before the opener is an indented code block on the page, and a box
    after it is drawn."""
    assert not _boxed("## Checklist\n\n   <details>\n- [ ] unchecked")
    assert _boxed("## Checklist\n\n    <details>\n- [ ] unchecked") and _boxed("## Checklist\n\n\t<details>\n- [ ] unchecked")
    assert _boxed("## Checklist\n\n    <!--\n- [ ] unchecked") and _boxed("- notes\n    <details>\n- [ ] unchecked")


def test_an_openers_indent_is_measured_as_the_page_measures_it() -> None:
    """A tab after a quote marker expands from the line's start, so it stops two columns past the marker and opens a
    block; a non-breaking space is content, not indent, so it opens nothing and the box after it is drawn."""
    assert not _boxed("## C\n\n> \t<details>\n> - [ ] x") and not _boxed("## C\n\n>\t<details>\n> - [ ] x")
    assert _boxed("## C\n\n\u00a0<details>\n- [ ] x")


def test_a_quote_marker_is_indented_at_most_three_spaces() -> None:
    """Four spaces, a tab or a non-breaking space before `>` make the line code or a paragraph, not a quote, so a
    `<details>` there opens nothing and the quoted box on the next line is drawn; three spaces still quote."""
    assert _boxed("    > <details>\n> - [ ] x") and _boxed("\t> <details>\n> - [ ] x") and _boxed("\u00a0> <details>\n> - [ ] x")
    assert not _boxed("   > <details>\n> - [ ] x") and _boxed("   > - [ ] x")


def test_a_tab_after_a_quote_marker_before_a_fence_is_a_fence() -> None:
    """A tab expands from the line's start, so after a quote marker it stops two columns in and opens a fence; at
    the line's own start it reaches column four, which is an indented code block, and the box after it is drawn."""
    assert not _boxed("> \t```\n> - [ ] x\n> ```") and _boxed("\t```\n- [ ] x\n```")


def test_a_box_behind_an_over_indented_quote_marker_still_counts() -> None:
    """Four spaces before `>` is a list item's nested content or indented code, and the walk tracks no list; the marker
    opens nothing and the box behind it counts, so the gate is loud where the page shows code and never silent
    where it draws the box."""
    assert _boxed("- item\n    > - [ ] x") and _boxed("- item\n    > > - [ ] x")


def test_an_unknown_tag_hides_nothing_under_gate_6() -> None:
    """`<detailsx>` is a spelling the block regex declines, and the closer-terminated `<details` arm is the read line's
    alone, so under gate 6 the tag is content and the box past the blank line is counted, as the page draws it."""
    assert _boxed("## C\n\n<detailsx>\n\n- [ ] real")


def test_a_tag_condition_6_does_not_open_hides_nothing_under_gate_6() -> None:
    """`<details-foo> text` is a paragraph on the page -- condition 6 wants a space, a tab, `>`, `/>` or the line's
    end after the tag name -- and the box on the next line interrupts it, so gate 6 counts it; `<details>` and
    `<details open>` still open the block that hides theirs."""
    assert _boxed("## C\n\n<details-foo> text\n- [ ] real")
    assert _boxed("<summary-x> text\n- [ ] real")
    assert not _boxed("<details>\n- [ ] literal\n</details>")
    assert not _boxed("<details open>\n- [ ] literal\n</details>")


def test_a_commit_with_no_author_entries_withdraws_the_dependabot_exemption():
    """Flattened, such a commit contributes nothing and vanishes; the exemption then survives a commit
    nothing is known about, which is not `every commit is the bot's`."""
    fails = _eval(_pr(**BUMP_PR, commits=BOT + [{"authors": []}]), files=["uv.lock"])
    assert len(fails) == 1 and fails[0].startswith("no 'Read before push by:")
