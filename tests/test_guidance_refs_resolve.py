"""Every guidance path a live surface cites resolves to a file that exists.

A round that collapses `.claude/rules/` or renames a skill leaves the surfaces that cite it pointing at nothing, and
a session following the citation improvises the rule instead of reading it. The zero-base of 2026-09-10 took the
rules from twelve files to one; the live surfaces were swept with it, and this is what keeps the next one swept.

Scope is the surfaces a session reads and acts on today. `docs/plans/`, `docs/open-topics/archive/` and
`docs/research/` are records of what was cited when they were written, and are deliberately outside it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The surfaces a session loads or follows: the corpus, the guidance tree, the contracts and references,
# the runbooks an alert routes to, and the code and tests whose comments send a reader somewhere.
LIVE = ("CLAUDE.md", ".claude/", "docs/reference/", "infra/runbooks/", "infra/scripts/", "infra/ansible/", "cli/", "tests/")

# A citation of a rule, a skill, a skill reference, a saved workflow or a hook -- the five shapes the tree uses.
_GUIDANCE = re.compile(
    r"\.claude/(?:rules/[A-Za-z0-9._-]+\.md"
    r"|skills/[A-Za-z0-9._-]+/(?:SKILL\.md|references/[A-Za-z0-9._-]+\.md)"
    r"|workflows/[A-Za-z0-9._-]+\.js"
    r"|hooks/[A-Za-z0-9._-]+\.sh)"
)

# Paths a test builds to drive a guard over a synthetic tree; they name no file and must not. Asserted both
# ways, so an entry that stops being cited, or starts resolving, fails rather than sitting here unread.
_SYNTHETIC = {
    ".claude/rules/new.md",
    ".claude/rules/old.md",
}


def citations(root: Path, listed: list[str]) -> dict[str, list[str]]:
    """Every guidance path cited by a live surface of `root`, mapped to the surfaces citing it."""
    found: dict[str, list[str]] = {}
    for rel in [r for r in listed if r.startswith(LIVE)]:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError:
            continue
        for target in set(_GUIDANCE.findall(text)):
            found.setdefault(target, []).append(rel)
    return found


def dangling(root: Path, listed: list[str], allowed: set[str]) -> dict[str, list[str]]:
    """The cited guidance paths that name no file, the allowlisted synthetic ones aside."""
    found = citations(root, listed)
    return {t: sorted(s) for t, s in found.items() if t not in allowed and not (root / t).is_file()}


def stale_allowlist(root: Path, cited: dict[str, list[str]], allowed: set[str]) -> tuple[list[str], list[str]]:
    """(the allowlisted paths nothing cites any more, the allowlisted paths that now name a real file)."""
    return sorted(p for p in allowed if p not in cited), sorted(p for p in allowed if (root / p).is_file())


def _tracked() -> list[str]:
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, check=True)
    return listed.stdout.split()


def test_a_live_surface_cites_no_guidance_file_that_is_missing():
    listed = _tracked()
    cited = citations(REPO, listed)
    assert len(cited) > 8, "the citation regex found suspiciously few targets -- it is broken, not the tree clean"
    assert dangling(REPO, listed, _SYNTHETIC) == {}, "live surfaces cite guidance files that do not exist"


def test_the_synthetic_allowlist_is_neither_stale_nor_resolving():
    """A synthetic path that stopped being cited, or that now names a real file, is an allowlist entry to delete."""
    unused, real = stale_allowlist(REPO, citations(REPO, _tracked()), _SYNTHETIC)
    assert unused == [], f"allowlisted synthetic paths no longer cited anywhere: {unused}"
    assert real == [], f"allowlisted synthetic paths now name real files, so they are citations: {real}"


# The fixture's paths are assembled at run time rather than written as literals, so this file's own
# synthetic tree never reads as a citation when the checker walks the real one.
_RULES, _SKILLS, _FLOWS = ".claude/" + "rules/", ".claude/" + "skills/", ".claude/" + "workflows/"
_LIVE_RULE, _GONE_RULE = _RULES + "live.md", _RULES + "gone.md"
_KEEP_SKILL, _A_FLOW = _SKILLS + "keep/SKILL.md", _FLOWS + "flow.js"


def _fake(tmp_path: Path) -> list[str]:
    """A tree whose live surface cites a rule, a skill and a workflow, beside an archival file citing a deleted rule."""
    for rel in (_LIVE_RULE, _KEEP_SKILL, _A_FLOW):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("a guidance file\n")
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text(f"reads `{_LIVE_RULE}`, `{_KEEP_SKILL}` and `{_A_FLOW}`\n")
    (tmp_path / "docs" / "plans" / "00001-a.md").write_text(f"cited `{_GONE_RULE}` when written\n")
    return ["CLAUDE.md", _LIVE_RULE, _KEEP_SKILL, _A_FLOW, "docs/plans/00001-a.md"]


def test_the_checker_names_a_live_surface_and_leaves_an_archival_one(tmp_path):
    listed = _fake(tmp_path)
    assert dangling(tmp_path, listed, set()) == {}, "the plan's dead citation is archival and out of scope"
    corpus = tmp_path / "CLAUDE.md"
    corpus.write_text(corpus.read_text() + f"and `{_GONE_RULE}`\n")
    assert dangling(tmp_path, listed, set()) == {_GONE_RULE: ["CLAUDE.md"]}
    assert dangling(tmp_path, listed, {_GONE_RULE}) == {}, "an allowlisted path is not dangling"


def test_the_checker_reads_every_citation_shape(tmp_path):
    listed = _fake(tmp_path)
    assert set(citations(tmp_path, listed)) == {_LIVE_RULE, _KEEP_SKILL, _A_FLOW}, (
        "a live surface's citation of a rule, a skill or a workflow went unread"
    )


def test_the_allowlist_check_catches_an_uncited_entry_and_a_resolving_one(tmp_path):
    listed = _fake(tmp_path)
    cited = citations(tmp_path, listed)
    assert stale_allowlist(tmp_path, cited, {_GONE_RULE}) == ([_GONE_RULE], []), "an entry nothing cites is named"
    assert stale_allowlist(tmp_path, cited, {_LIVE_RULE}) == ([], [_LIVE_RULE]), "an entry that names a real file is named"
