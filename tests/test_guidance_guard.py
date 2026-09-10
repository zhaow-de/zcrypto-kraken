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


def test_growth_stated_by_its_exact_count_passes():
    before = {RULE: COUNTED}
    after = {RULE: COUNTED + DECLARED}
    n = len(DECLARED.encode())
    assert (
        guard.evaluate(before, after, f"claude(rules): one line\n\nAmbient grows by {n} bytes: the owner kept it by name\n") == []
    )


def test_growth_without_the_line_is_refused_and_names_the_skill():
    fails = guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + DECLARED}, "claude(rules): one line\n")
    assert len(fails) == 1 and f"grows by {len(DECLARED.encode())} bytes" in fails[0] and fails[0].endswith(guard.SKILL)


def test_growth_stated_by_the_wrong_count_is_refused():
    fails = guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + DECLARED}, "x\n\nAmbient grows by 1 bytes: a guess\n")
    assert len(fails) == 1 and "says the ambient grows by 1 bytes" in fails[0]


def test_a_shrink_needs_no_line_and_a_line_on_a_shrink_is_refused():
    assert guard.evaluate({RULE: COUNTED + DECLARED}, {RULE: COUNTED}, "claude(rules): one fewer\n") == []
    fails = guard.evaluate({RULE: COUNTED + DECLARED}, {RULE: COUNTED}, "x\n\nAmbient grows by 5 bytes: stale\n")
    assert len(fails) == 1 and "change it by -" in fails[0]


def test_a_moved_line_is_a_trade_not_a_growth():
    before = {"CLAUDE.md": COUNTED + DECLARED, RULE: ""}
    after = {"CLAUDE.md": COUNTED, RULE: DECLARED}
    assert guard.evaluate(before, after, "claude(rules): the line moves\n") == []


def test_a_skill_description_is_ambient_and_its_body_is_not():
    short, longer = _skill("Use when opening a PR."), _skill("Use when opening a PR, or editing a PR title or body.")
    fails = guard.evaluate({SKILL: short}, {SKILL: longer}, "claude(skills): wider trigger\n")
    grown = len(longer.encode()) - len(short.encode())
    assert len(fails) == 1 and f"grows by {grown} bytes" in fails[0]
    grown_body = _skill("Use when opening a PR.", body="\n# open-pr\n\nSteps, and many more steps than before.\n")
    assert guard.evaluate({SKILL: short}, {SKILL: grown_body}, "claude(skills): a longer body\n") == []
    other_key = _skill("Use when opening a PR.", extra="disable-model-invocation: true\nmodel: claude-opus-5")
    assert guard.evaluate({SKILL: short}, {SKILL: other_key}, "claude(skills): another frontmatter key\n") == []


def test_a_new_corpus_file_counts_whole_and_a_deleted_one_counts_as_a_shrink():
    fails = guard.evaluate({}, {".claude/rules/new.md": COUNTED}, "claude(rules): a new file\n")
    assert len(fails) == 1 and f"grows by {len(COUNTED.encode())} bytes" in fails[0]
    assert guard.evaluate({".claude/rules/old.md": COUNTED}, {}, "claude(rules): a file goes\n") == []


def test_a_universal_without_a_count_is_refused_at_its_line():
    fails = guard.evaluate({RULE: COUNTED}, {RULE: COUNTED + BARE}, f"x\n\nAmbient grows by {len(BARE.encode())} bytes: a test\n")
    assert len(fails) == 1 and fails[0].startswith(f"{RULE}:2 carries a universal ('Never')") and fails[0].endswith(guard.SKILL)


def test_a_counted_or_declared_universal_and_a_non_bullet_pass():
    header = "L2 capture is unbackfillable — every mistake is permanent.\n\n"
    text = header + COUNTED + DECLARED
    assert guard.evaluate({RULE: text}, {RULE: text}, "x\n") == []


def test_a_skill_file_is_not_read_for_universals():
    text = _skill("Use when opening a PR.", body="\n- Never open a PR without the word.\n")
    assert guard.evaluate({SKILL: text}, {SKILL: text}, "x\n") == []


def test_the_corpus_on_disk_carries_no_uncounted_universal():
    """The fifth test as a CI assertion over the real files, not only over what a commit stages."""
    paths = [_ROOT / "CLAUDE.md", *sorted((_ROOT / ".claude" / "rules").glob("*.md"))]
    bad = [
        (p.relative_to(_ROOT), i, line[:60])
        for p in paths
        for i, line in guard.uncounted_universals(str(p.relative_to(_ROOT)), p.read_text())
    ]
    assert bad == [], bad


def test_the_script_passes_with_nothing_ambient_staged(tmp_path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("chore: nothing\n\n# a comment line git adds\n")
    staged = subprocess.run(["git", "-C", str(_ROOT), "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout
    if any(guard.CORPUS.match(p) or guard.SKILL_FILE.match(p) for p in staged.split("\n")):
        return  # an ambient file is staged in this checkout right now; the unit tests above cover the arms
    done = subprocess.run([sys.executable, str(_SCRIPT), str(msg)], cwd=_ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
