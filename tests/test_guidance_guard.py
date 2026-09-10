"""guidance-guard.py: a commit that grows the always-loaded guidance says so by the exact byte count, and a corpus bullet with a universal names its count entry or declares it has none."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "guidance-guard.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load(_SCRIPT, "guidance_guard")

RULE = ".claude/rules/fleet-deploys.md"
SKILL = ".claude/skills/open-pr/SKILL.md"
COUNTED = "- Never wrap `converge.sh` in `timeout` (set: invocations; count: `infra/scripts/count-list.sh converge-sh-wrapped-in-timeout`).\n"
DECLARED = (
    "- A schema-widening deploy converges every reader before the writer (no count command: nothing records a deploy's order).\n"
)
BARE = "- Never wrap `converge.sh` in `timeout` — the confirm reads the tty.\n"


def _skill(description: str, body: str = "\n# open-pr\n\nSteps.\n", extra: str = "disable-model-invocation: true") -> str:
    return f"---\nname: open-pr\ndescription: {description}\n{extra}\n---\n{body}"


def _growth(n: int, reason: str = "a test") -> str:
    return f"x\n\nAmbient grows by {n} bytes: {reason}\n"


# --- the growth arm ---------------------------------------------------------------------------


def test_growth_stated_by_its_exact_count_passes():
    n = len(DECLARED.encode())
    assert guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + DECLARED}, _growth(n, "the owner kept it by name")) == []


def test_growth_without_the_line_is_refused_and_names_the_skill():
    fails = guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + DECLARED}, "claude(rules): one line\n")
    assert len(fails) == 1 and f"grows by {len(DECLARED.encode())} bytes" in fails[0] and fails[0].endswith(guard.SKILL)


def test_growth_stated_by_the_wrong_count_is_refused():
    fails = guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + DECLARED}, _growth(1, "a guess"))
    assert len(fails) == 1 and "says the ambient grows by 1 bytes" in fails[0] and fails[0].endswith(guard.SKILL)


def test_a_shrink_needs_no_line_and_a_line_on_a_shrink_is_refused():
    assert guard.evaluate({RULE: COUNTED + DECLARED}, {RULE: COUNTED}, "claude(rules): one fewer\n") == []
    fails = guard.evaluate({RULE: COUNTED + DECLARED}, {RULE: COUNTED}, _growth(5, "stale"))
    assert len(fails) == 1 and "change it by -" in fails[0] and fails[0].endswith(guard.SKILL)


def test_two_growth_lines_are_refused():
    n = len(DECLARED.encode())
    fails = guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + DECLARED}, _growth(n) + f"Ambient grows by {n} bytes: again\n")
    assert len(fails) == 1 and fails[0].startswith("two `Ambient grows by` lines")


def test_an_amend_basis_is_named_in_the_refusal():
    fails = guard.evaluate(
        {RULE: COUNTED}, {RULE: COUNTED + DECLARED}, "x\n", against=" against HEAD~1, the amended commit's parent"
    )
    assert len(fails) == 1 and "against HEAD~1, the amended commit's parent" in fails[0]


def test_a_moved_line_is_a_trade_not_a_growth():
    before = {"CLAUDE.md": COUNTED + DECLARED, RULE: ""}
    after = {"CLAUDE.md": COUNTED, RULE: DECLARED}
    assert guard.evaluate(before, after, "claude(rules): the line moves\n") == []


def test_a_skill_description_is_ambient_and_its_body_and_other_keys_are_not():
    short, longer = _skill("Use when opening a PR."), _skill("Use when opening a PR, or editing a PR title or body.")
    fails = guard.evaluate({SKILL: short}, {SKILL: longer}, "claude(skills): wider trigger\n")
    grown = len(longer.encode()) - len(short.encode())
    assert len(fails) == 1 and f"grows by {grown} bytes" in fails[0]
    grown_body = _skill("Use when opening a PR.", body="\n# open-pr\n\nSteps, and many more steps than before.\n")
    assert guard.evaluate({SKILL: short}, {SKILL: grown_body}, "claude(skills): a longer body\n") == []
    other_key = _skill("Use when opening a PR.", extra="disable-model-invocation: true\nmodel: claude-opus-5")
    assert guard.evaluate({SKILL: short}, {SKILL: other_key}, "claude(skills): another frontmatter key\n") == []


def test_a_blank_line_inside_a_folded_description_does_not_end_the_count():
    one = "---\nname: s\ndescription: >\n  First paragraph.\n---\n"
    two = "---\nname: s\ndescription: >\n  First paragraph.\n\n  Second paragraph, loaded with the first.\n---\n"
    assert guard.ambient_bytes(SKILL, two) - guard.ambient_bytes(SKILL, one) == len(
        "\n  Second paragraph, loaded with the first.\n".encode()
    )


def test_a_folded_description_is_counted_whole():
    """A `description: >` block is what the harness loads; the header line alone would register the change as a shrink."""
    flat = _skill("Use when opening a PR, or editing a PR title or body, or aggregating trailers.")
    folded = (
        "---\nname: open-pr\ndescription: >\n  Use when opening a PR, or editing a PR title or body,\n"
        "  or aggregating trailers, and much more than the flat line said.\ndisable-model-invocation: true\n---\n\n# open-pr\n"
    )
    assert guard.ambient_bytes(SKILL, folded) > guard.ambient_bytes(SKILL, flat)
    fails = guard.evaluate({SKILL: flat}, {SKILL: folded}, "claude(skills): folded\n")
    assert len(fails) == 1 and "grows by" in fails[0]


WORKFLOW = ".claude/workflows/review.js"


def _workflow(description: str, when: str = "Before a push.", body: str = "\nphase('Read')\nreturn 1\n") -> str:
    return f"export const meta = {{\n  name: 'review',\n  description: '{description}',\n  whenToUse: '{when}',\n  phases: [{{ title: 'Read' }}],\n}}\n{body}"


def test_a_workflow_s_listed_text_is_ambient_and_its_body_is_not():
    """The harness lists a saved workflow by name, description and whenToUse, the way it lists a skill's description."""
    short, longer = _workflow("Review a range."), _workflow("Review a range with two lenses and two skeptics.")
    grown = len(longer.encode()) - len(short.encode())
    fails = guard.evaluate({WORKFLOW: short}, {WORKFLOW: longer}, "claude(workflows): wider\n")
    assert len(fails) == 1 and f"grows by {grown} bytes" in fails[0]
    grown_body = _workflow("Review a range.", body="\nphase('Read')\nconst x = 1\nreturn x\n")
    assert guard.evaluate({WORKFLOW: short}, {WORKFLOW: grown_body}, "claude(workflows): a longer body\n") == []
    assert guard.ambient_bytes(WORKFLOW, short) == sum(len(v.encode()) + 1 for v in ("review", "Review a range.", "Before a push."))
    escapes = "export const meta = {\n  name: 'x',\n  description: 'caf\\u00e9 \\x41 it\\'s\\n',\n}\n"
    assert guard.ambient_bytes(WORKFLOW, escapes) == len("x".encode()) + 1 + len("café A it's\n".encode()) + 1


def test_a_meta_the_guard_cannot_read_is_refused_not_guessed_at():
    """One shape is read, the authoring reference's own; a workflow written another way is refused at commit and by --ambient-bytes."""
    refusals = {
        "one line": "export const meta = { name: 'x', description: 'd', whenToUse: 'w' }\nreturn 1\n",
        "double quotes": 'export const meta = {\n  name: "x",\n  description: "d",\n}\nreturn 1\n',
        "whenToUse in back quotes": "export const meta = {\n  name: 'x',\n  description: 'd',\n  whenToUse: `w`,\n}\nreturn 1\n",
        "no description": "export const meta = {\n  name: 'x',\n}\nreturn 1\n",
        "a brace escape": "export const meta = {\n  name: 'x',\n  description: 'caf\\u{e9}',\n}\nreturn 1\n",
        "meta not first": "// a comment\nexport const meta = {\n  name: 'x',\n  description: 'd',\n}\nreturn 1\n",
    }
    for shape, text in refusals.items():
        fails = guard.evaluate({}, {WORKFLOW: text}, "claude(workflows): x\n")
        assert len(fails) == 1 and fails[0].startswith(WORKFLOW + ": ") and fails[0].endswith(guard.SKILL), (shape, fails)


def test_deleting_or_reshaping_a_workflow_is_a_change_the_guard_measures_not_refuses():
    """The fourth re-review's Critical: the deletion side read as an empty file and was refused; a basis in another shape counts as nothing."""
    canonical = _workflow("Review a range.")
    assert guard.evaluate({WORKFLOW: canonical}, {}, "claude(workflows): drop it\n") == []
    old_shape = "export const meta = { name: 'review', description: 'Review a range.', whenToUse: 'Before a push.' }\nreturn 1\n"
    assert guard.evaluate({WORKFLOW: old_shape}, {}, "claude(workflows): drop the odd one\n") == []
    n = guard.ambient_bytes(WORKFLOW, canonical)
    assert (
        guard.evaluate(
            {WORKFLOW: old_shape},
            {WORKFLOW: canonical},
            f"claude(workflows): reshape\n\nAmbient grows by {n} bytes: the whole listed text, the basis unreadable\n",
        )
        == []
    )


def test_the_brace_must_be_alone_and_a_trailing_comment_is_allowed_on_a_field():
    commented = (
        "export const meta = {\n  name: 'x',\n  description: 'd',   // one-line, shown in the permission dialog\n}\nreturn 1\n"
    )
    assert guard.ambient_bytes(WORKFLOW, commented) == len("x".encode()) + 1 + len("d".encode()) + 1
    trailing = "export const meta = {\n  name: 'x',\n  description: 'd',\n} // not alone\nreturn 1\n"
    fails = guard.evaluate({}, {WORKFLOW: trailing}, "claude(workflows): x\n")
    assert len(fails) == 1 and "not alone on its own line" in fails[0], fails
    deeper = "export const meta = {\n  name: 'x',\n  description: 'd',\n} // not alone\nconst OPTS = {\n  whenToUse: 'from the body',\n}\nreturn 1\n"
    fails = guard.evaluate({}, {WORKFLOW: deeper}, "claude(workflows): x\n")
    assert len(fails) == 1 and "not alone on its own line" in fails[0], fails
    literal_backslash = "export const meta = {\n  name: 'x',\n  description: 'a \\\\u{b',\n}\nreturn 1\n"
    assert guard.ambient_bytes(WORKFLOW, literal_backslash) == len("x".encode()) + 1 + len("a \\u{b".encode()) + 1


def test_a_description_below_the_meta_literal_is_not_counted():
    """The third re-review's finding: a schema's description after the literal must not be charged as ambient."""
    text = "export const meta = {\n  name: 'x',\n  description: 'd',\n}\nconst FINDING = {\n  type: 'object',\n  description: 'the finding in one sentence',\n}\nreturn 1\n"
    assert guard.ambient_bytes(WORKFLOW, text) == len("x".encode()) + 1 + len("d".encode()) + 1


def test_a_new_corpus_file_counts_whole_and_a_deleted_one_counts_as_a_shrink():
    fails = guard.evaluate({}, {".claude/rules/new.md": COUNTED}, "claude(rules): a new file\n")
    assert len(fails) == 1 and f"grows by {len(COUNTED.encode())} bytes" in fails[0]
    assert guard.evaluate({".claude/rules/old.md": COUNTED}, {}, "claude(rules): a file goes\n") == []


# --- the universal arm ------------------------------------------------------------------------


def test_a_universal_without_a_count_is_refused_at_its_line():
    fails = guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + BARE}, _growth(len(BARE.encode())))
    assert len(fails) == 1 and fails[0].startswith(f"{RULE}:2 carries a universal ('Never')") and fails[0].endswith(guard.SKILL)


def test_a_nested_bullet_is_read_and_a_wrapped_bullet_is_one_block():
    nested = COUNTED + "  - a sub-bullet that is never counted.\n"
    assert [w for _, w in guard.uncounted_universals(RULE, nested)] == ["never"]
    wrapped = (
        "- Never wrap `converge.sh` in `timeout` — the confirm reads the tty\n"
        "  (set: invocations; count: `infra/scripts/count-list.sh converge-sh-wrapped-in-timeout`).\n"
    )
    assert guard.uncounted_universals(RULE, wrapped) == []


def test_plus_and_numbered_items_are_read_and_a_fenced_block_is_not():
    assert [w for _, w in guard.uncounted_universals(RULE, "+ never a plus.\n1. always a number.\n2) only a paren.\n")] == [
        "never",
        "always",
        "only",
    ]
    fenced = "- A counted item (no count command: none).\n\n```bash\n- uv sync --only-group dev\nnever\n```\n\n~~~\n- never in a tilde fence\n~~~\n"
    assert guard.uncounted_universals(RULE, fenced) == []


def test_a_universal_inside_a_code_span_is_not_a_universal():
    assert guard.uncounted_universals(RULE, "- Run `uv sync --only-group dev` and `any()` before the gate.\n") == []
    assert [w for _, w in guard.uncounted_universals(RULE, "- Run `uv sync` only before the gate.\n")] == ["only"]


def test_a_counted_or_declared_universal_and_a_paragraph_pass():
    header = "L2 capture is unbackfillable — every mistake is permanent.\n\n"
    text = header + COUNTED + DECLARED
    assert guard.evaluate({RULE: text}, {RULE: text}, "x\n") == []


def test_a_skill_file_is_not_read_for_universals():
    text = _skill("Use when opening a PR.", body="\n- Never open a PR without the word.\n")
    assert guard.evaluate({SKILL: text}, {SKILL: text}, "x\n") == []


def test_a_contract_is_read_for_universals_and_is_not_ambient():
    """The three contracts the skills load whole take the universal test; their bytes are not paid on every turn, so growth there needs no line."""
    contract = "docs/reference/fleet-pins.md"
    fails = guard.evaluate({}, {contract: "- Never re-pin the NAS to an AVX build.\n"}, "x\n")
    assert len(fails) == 1 and fails[0].startswith(f"{contract}:1 carries a universal ('Never')"), fails
    assert guard._judged([contract, "docs/reference/fleet.md", "docs/reference/drill-log.md", "cli/x.py"]) == [
        contract,
        "docs/reference/fleet.md",
    ]
    assert guard.ambient_bytes(contract, "- Never re-pin the NAS to an AVX build.\n") == 0


def test_the_corpus_on_disk_carries_no_uncounted_universal():
    """The universal test as a CI assertion over the real files -- the corpus and the three contracts -- not only over what a commit stages."""
    paths = [
        _ROOT / "CLAUDE.md",
        *sorted((_ROOT / ".claude" / "rules").glob("*.md")),
        _ROOT / "docs" / "reference" / "fleet.md",
        _ROOT / "docs" / "reference" / "fleet-pins.md",
        _ROOT / ".claude" / "skills" / "zcrypto-grooming" / "references" / "memo-protocol.md",
    ]
    bad = [
        (p.relative_to(_ROOT), i, w) for p in paths for i, w in guard.uncounted_universals(str(p.relative_to(_ROOT)), p.read_text())
    ]
    assert bad == [], bad


# --- the script, in a repository of its own ---------------------------------------------------


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "guard@test")
    _git(repo, "config", "user.name", "guard")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "CLAUDE.md").write_text("# CLAUDE.md\n\n" + DECLARED)
    (repo / ".claude" / "rules").mkdir(parents=True)
    (repo / ".claude" / "rules" / "fleet-deploys.md").write_text("# Fleet\n\n" + COUNTED)
    (repo / ".claude" / "skills" / "open-pr").mkdir(parents=True)
    (repo / SKILL).write_text(_skill("Use when opening a PR."))
    (repo / "README.md").write_text("# readme\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _run(repo: pathlib.Path, message: str, *args: str) -> subprocess.CompletedProcess[str]:
    (repo / "MSG").write_text(message)
    return subprocess.run([sys.executable, str(_SCRIPT), *(args or ("MSG",))], cwd=repo, capture_output=True, text=True)


def _grow_claude_md(repo: pathlib.Path, line: str = COUNTED) -> int:
    path = repo / "CLAUDE.md"
    path.write_text(path.read_text() + line)
    _git(repo, "add", "CLAUDE.md")
    return len(line.encode())


def test_the_script_refuses_growth_and_passes_with_the_line(tmp_path):
    repo = _repo(tmp_path)
    n = _grow_claude_md(repo)
    refused = _run(repo, "claude(rules): grow\n")
    assert refused.returncode == 1 and f"grows by {n} bytes" in refused.stdout, refused.stdout + refused.stderr
    passed = _run(repo, f"claude(rules): grow\n\nAmbient grows by {n} bytes: a test\n")
    assert passed.returncode == 0, passed.stdout + passed.stderr


def test_the_script_skips_a_merge_in_progress_from_the_checkout_and_from_a_worktree(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "other")
    n = _grow_claude_md(repo)
    _git(repo, "commit", "-q", "-m", f"claude(rules): grow\n\nAmbient grows by {n} bytes: on other\n")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "--no-commit", "--no-ff", "-q", "other")
    assert _run(repo, "Merge branch 'other'\n").returncode == 0
    _git(repo, "merge", "--abort")
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "in-wt", str(wt), "develop")
    assert (wt / ".git").is_file()
    _git(wt, "merge", "--no-commit", "--no-ff", "-q", "other")
    done = _run(wt, "Merge branch 'other'\n")
    assert done.returncode == 0, done.stdout + done.stderr
    _git(wt, "merge", "--abort")


def test_the_script_measures_an_amend_against_the_parent(tmp_path):
    """An amend keeps its subject; the resulting commit's growth is the whole of it, not the increment staged on top."""
    repo = _repo(tmp_path)
    n1 = _grow_claude_md(repo)
    message = f"claude(rules): grow\n\nAmbient grows by {n1} bytes: first\n"
    _git(repo, "commit", "-q", "-m", message)
    n2 = _grow_claude_md(repo, DECLARED)
    refused = _run(repo, message)
    assert refused.returncode == 1 and f"grow it by {n1 + n2} against HEAD~1" in refused.stdout, refused.stdout + refused.stderr
    passed = _run(repo, f"claude(rules): grow\n\nAmbient grows by {n1 + n2} bytes: first and second\n")
    assert passed.returncode == 0, passed.stdout + passed.stderr
    renamed = _run(repo, f"claude(rules): a new subject\n\nAmbient grows by {n2} bytes: measured against HEAD\n")
    assert renamed.returncode == 0, renamed.stdout + renamed.stderr


def test_an_amend_sees_every_file_the_whole_commit_changes(tmp_path):
    """The second file was changed by the original commit, not by the amend; against the parent it still counts."""
    repo = _repo(tmp_path)
    n1 = _grow_claude_md(repo)
    message = f"claude(rules): grow\n\nAmbient grows by {n1} bytes: first\n"
    _git(repo, "commit", "-q", "-m", message)
    rule = repo / ".claude" / "rules" / "fleet-deploys.md"
    rule.write_text(rule.read_text() + DECLARED)
    _git(repo, "add", str(rule))
    n2 = len(DECLARED.encode())
    refused = _run(repo, message)
    assert refused.returncode == 1 and f"grow it by {n1 + n2} against HEAD~1" in refused.stdout, refused.stdout + refused.stderr
    assert _run(repo, f"claude(rules): grow\n\nAmbient grows by {n1 + n2} bytes: both\n").returncode == 0


def test_a_message_only_amend_is_judged_against_the_parent(tmp_path):
    repo = _repo(tmp_path)
    n1 = _grow_claude_md(repo)
    message = f"claude(rules): grow\n\nAmbient grows by {n1} bytes: first\n"
    _git(repo, "commit", "-q", "-m", message)
    assert _run(repo, message).returncode == 0
    dropped = _run(repo, "claude(rules): grow\n\nthe line, dropped in the amend\n")
    assert dropped.returncode == 1 and "does not say so" in dropped.stdout, dropped.stdout + dropped.stderr


def test_a_wrapped_subject_is_read_the_way_git_renders_it(tmp_path):
    repo = _repo(tmp_path)
    n1 = _grow_claude_md(repo)
    message = f"claude(rules): grow a line that\nwraps onto a second\n\nAmbient grows by {n1} bytes: first\n"
    (repo / "M").write_text(message)
    _git(repo, "commit", "-q", "-F", str(repo / "M"))
    n2 = _grow_claude_md(repo, DECLARED)
    refused = _run(repo, message)
    assert refused.returncode == 1 and f"grow it by {n1 + n2} against HEAD~1" in refused.stdout, refused.stdout + refused.stderr


def test_the_script_reads_nothing_below_the_scissors_or_in_comments(tmp_path):
    repo = _repo(tmp_path)
    n = _grow_claude_md(repo)
    below = f"claude(rules): grow\n# Ambient grows by {n} bytes: a comment\n{guard.SCISSORS}\nAmbient grows by {n} bytes: below the scissors\n"
    refused = _run(repo, below)
    assert refused.returncode == 1 and "does not say so" in refused.stdout, refused.stdout + refused.stderr


def test_the_script_judges_only_a_commit_that_stages_an_ambient_file(tmp_path):
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("# readme, longer\n")
    _git(repo, "add", "README.md")
    assert _run(repo, "docs: readme\n\nAmbient grows by 99 bytes: a line the guard never reads\n").returncode == 0


def test_a_repository_s_first_commit_is_judged_against_the_empty_tree(tmp_path):
    repo = tmp_path / "fresh"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    (repo / "CLAUDE.md").write_text("# CLAUDE.md\n\n" + DECLARED)
    _git(repo, "add", "CLAUDE.md")
    n = len(("# CLAUDE.md\n\n" + DECLARED).encode())
    refused = _run(repo, "claude(rules): the first\n")
    assert refused.returncode == 1 and f"grows by {n} bytes" in refused.stdout, refused.stdout + refused.stderr
    assert _run(repo, f"claude(rules): the first\n\nAmbient grows by {n} bytes: born\n").returncode == 0


def test_the_range_mode_judges_every_commit_against_its_parent_and_skips_merges(tmp_path):
    """A rewrite that lost a line lands unrefused by the hook; the range mode is where it is caught."""
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    n1 = _grow_claude_md(repo)
    _git(repo, "commit", "-q", "-m", f"claude(rules): first\n\nAmbient grows by {n1} bytes: stated\n")
    rule = repo / ".claude" / "rules" / "fleet-deploys.md"
    rule.write_text(rule.read_text() + DECLARED)
    _git(repo, "add", str(rule))
    _git(repo, "commit", "-q", "-m", "claude(rules): second, its line lost in a rebase\n")
    lost = _git(repo, "rev-parse", "--short=8", "HEAD").stdout.strip()
    refused = _run(repo, "", "--range", f"{base}..HEAD")
    assert refused.returncode == 1 and refused.stdout.count("\n  - ") == 1 and f"{lost} claude(rules): second" in refused.stdout, (
        refused.stdout + refused.stderr
    )
    _git(
        repo,
        "commit",
        "-q",
        "--amend",
        "-m",
        f"claude(rules): second, its line restored\n\nAmbient grows by {len(DECLARED.encode())} bytes: restored\n",
    )
    passed = _run(repo, "", "--range", f"{base}..HEAD")
    assert passed.returncode == 0 and "every commit" in passed.stdout, passed.stdout + passed.stderr
    _git(repo, "checkout", "-q", "-b", "side", base)
    (repo / "README.md").write_text("# readme, on side\n")
    _git(repo, "commit", "-q", "-am", "docs: side")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", "side")
    assert _run(repo, "", "--range", f"{base}..HEAD").returncode == 0
    verbatim = f"claude(rules): stored verbatim\n\n{guard.SCISSORS}\nAmbient grows by 5 bytes: below the scissors, stored\n"
    (repo / "M").write_text(verbatim)
    (repo / "CLAUDE.md").write_text((repo / "CLAUDE.md").read_text() + "- five\n")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "--cleanup=verbatim", "-F", str(repo / "M"))
    stored = _run(repo, "", "--range", f"{base}..HEAD")
    assert stored.returncode == 1 and "does not say so" in stored.stdout, stored.stdout + stored.stderr
    three_dot = _run(repo, "", "--range", f"{base}...HEAD")
    assert three_dot.returncode == 2 and "usage" in three_dot.stderr, three_dot.stdout + three_dot.stderr


def test_the_ambient_bytes_subcommand_refuses_a_tree_with_an_unreadable_workflow(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".claude" / "workflows").mkdir()
    (repo / ".claude" / "workflows" / "odd.js").write_text("export const meta = { name: 'x', description: 'd' }\nreturn 1\n")
    done = _run(repo, "", "--ambient-bytes")
    assert done.returncode == 2 and "cannot measure" in done.stderr and "odd.js" in done.stderr, done.stdout + done.stderr


def test_the_ambient_bytes_subcommand_is_the_function_over_the_tree(tmp_path):
    repo = _repo(tmp_path)
    done = _run(repo, "", "--ambient-bytes")
    expected = sum(guard.ambient_bytes(p, (repo / p).read_text()) for p in ("CLAUDE.md", ".claude/rules/fleet-deploys.md", SKILL))
    assert done.returncode == 0 and done.stdout.strip() == str(expected), done.stdout + done.stderr
    here = subprocess.run([sys.executable, str(_SCRIPT), "--ambient-bytes"], cwd=_ROOT, capture_output=True, text=True)
    assert here.returncode == 0 and here.stdout.strip() == str(guard.tree_ambient_bytes(_ROOT))
