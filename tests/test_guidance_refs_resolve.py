"""Every guidance path a live surface cites resolves to a file that exists.

A round that collapses `.claude/rules/` or renames a skill leaves the surfaces that cite it pointing at nothing, and
a session following the citation improvises the rule instead of reading it. The zero-base of 2026-09-10 took the
rules from twelve files to one; the live surfaces were swept with it, and this is what keeps the next one swept.

Scope is what a session reads and acts on today. Outside it, deliberately: `docs/plans/`, `docs/specs/` and
`docs/research/` (a plan, a spec and a closeout are the record of a change, cited during their own branch and
frozen after), `docs/open-topics/archive/` (a resolved topic), and the append-only records under
`docs/reference/` (a journal entry, a drill or deploy row, a change-index row — each says what was cited on the
day it was written, and editing a merged month's record to get CI green is the wrong repair).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The surfaces a session loads or follows: the corpus, the guidance tree, the contracts and references, the live
# topics whose triggers the daily pass evaluates, the runbooks an alert routes to, and the code and tests whose
# comments send a reader somewhere.
LIVE = (
    "CLAUDE.md",
    ".claude/",
    "docs/reference/",
    "docs/open-topics/",
    "infra/runbooks/",
    "infra/scripts/",
    "infra/ansible/",
    "cli/",
    "tests/",
)
# Inside a LIVE prefix but a record of what was cited when written, not a surface anyone acts on. Named by
# shape, not by directory: an ops-journal month and an adapter-verification row are records, while the README
# beside them is procedure and stays walked -- it is the only live citation of the daily-ops skill.
RECORDS = (
    "docs/open-topics/archive/",
    "docs/reference/drill-log.md",
    "docs/reference/change-index.md",
)
_RECORD_ENTRY = re.compile(r"^docs/reference/(?:ops-journal|adapter-verification)/[^/]*\d")

# A citation of a rule, a skill, a skill reference, a skill script, a saved workflow, a hook or the settings file.
_GUIDANCE = re.compile(
    r"\.claude/(?:rules/[A-Za-z0-9._-]+\.md"
    r"|skills/[A-Za-z0-9._-]+/(?:SKILL\.md|references/[A-Za-z0-9._-]+\.md|scripts/[A-Za-z0-9._-]+\.(?:py|sh))"
    r"|workflows/[A-Za-z0-9._-]+\.js"
    r"|hooks/[A-Za-z0-9._-]+\.sh"
    r"|settings\.json)"
)
# A skill cites its own references and scripts relatively, and that is the tree's commoner form: `references/x.md`
# from inside `.claude/skills/<name>/`, resolved against the skill's own directory.
_RELATIVE = re.compile(r"(?<![A-Za-z0-9._/-])(references/[A-Za-z0-9._-]+\.md|scripts/[A-Za-z0-9._-]+\.(?:py|sh))")

# Prefixes assembled at run time, so this file's own allowlist and fixture never read as citations when the
# checker walks the real tree -- the first shape of this test allowlisted its own literals and could not fail.
_C = ".claude" + "/"
_RULES, _SKILLS, _FLOWS, _HOOKS = _C + "rules/", _C + "skills/", _C + "workflows/", _C + "hooks/"

# Paths a guard test builds to drive a refusal over a synthetic tree; they name no file and must not. Asserted
# both ways, so an entry that stops being cited, or starts resolving, fails rather than sitting here unread.
_SYNTHETIC = {_RULES + "new.md", _RULES + "old.md"}

# Walked prefixes that cite no guidance today and are kept anyway, because a citation there is a matter of course
# rather than of kind: a code comment sending a reader to a runbook is exactly what the engine's data-client
# docstring nearly became. Asserted both ways, so a prefix that starts citing loses its entry here.
_QUIET = {"cli/"}


def _walked(listed: list[str]) -> list[str]:
    return [r for r in listed if r.startswith(LIVE) and not r.startswith(RECORDS) and not _RECORD_ENTRY.match(r)]


def citations(root: Path, listed: list[str]) -> dict[str, list[str]]:
    """Every guidance path a live surface of `root` cites, absolute or relative, mapped to the surfaces citing it."""
    found: dict[str, list[str]] = {}
    for rel in _walked(listed):
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError:
            continue
        targets = set(_GUIDANCE.findall(text))
        parts = rel.split("/")
        if rel.startswith(_SKILLS) and len(parts) > 2:  # a skill file's own relative citations
            skill = "/".join(parts[:3])
            targets |= {f"{skill}/{m}" for m in _RELATIVE.findall(text)}
        for target in targets:
            found.setdefault(target, []).append(rel)
    return found


def dangling(root: Path, listed: list[str], allowed: set[str]) -> dict[str, list[str]]:
    """The cited guidance paths that name no file, the allowlisted synthetic ones aside."""
    found = citations(root, listed)
    return {t: sorted(s) for t, s in found.items() if t not in allowed and not (root / t).is_file()}


def stale_allowlist(root: Path, cited: dict[str, list[str]], allowed: set[str]) -> tuple[list[str], list[str]]:
    """(the allowlisted paths nothing cites any more, the allowlisted paths that now name a real file)."""
    return sorted(p for p in allowed if p not in cited), sorted(p for p in allowed if (root / p).is_file())


def quiet_prefixes(root: Path, listed: list[str], prefixes: tuple[str, ...]) -> set[str]:
    """The walked prefixes under which no surface cites any guidance at all."""
    return {p for p in prefixes if not citations(root, [r for r in listed if r.startswith(p)])}


def _tracked() -> list[str]:
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, check=True)
    return listed.stdout.split()


def test_a_live_surface_cites_no_guidance_file_that_is_missing():
    listed = _tracked()
    cited = citations(REPO, listed)
    assert len(cited) > 8, "the citation regex found suspiciously few targets -- it is broken, not the tree clean"
    assert dangling(REPO, listed, _SYNTHETIC) == {}, "live surfaces cite guidance files that do not exist"


def test_every_walked_prefix_earns_its_place():
    """A prefix contributing nothing is a surface that moved or a scope quietly shrunk -- the move the zero-base made."""
    listed = _tracked()
    quiet = quiet_prefixes(REPO, listed, LIVE)
    assert quiet - _QUIET == set(), f"walked prefixes citing no guidance at all: {sorted(quiet - _QUIET)}"
    assert _QUIET - quiet == set(), f"prefixes recorded as quiet that now cite guidance: {sorted(_QUIET - quiet)}"


def test_the_synthetic_allowlist_is_neither_stale_nor_resolving():
    """A synthetic path that stopped being cited, or that now names a real file, is an allowlist entry to delete."""
    unused, real = stale_allowlist(REPO, citations(REPO, _tracked()), _SYNTHETIC)
    assert unused == [], f"allowlisted synthetic paths no longer cited anywhere: {unused}"
    assert real == [], f"allowlisted synthetic paths now name real files, so they are citations: {real}"


_LIVE_RULE, _GONE_RULE = _RULES + "live.md", _RULES + "gone.md"
_KEEP_SKILL, _A_FLOW, _A_HOOK = _SKILLS + "keep/SKILL.md", _FLOWS + "flow.js", _HOOKS + "guard.sh"
_A_REF, _A_SCRIPT = _SKILLS + "keep/references/ref.md", _SKILLS + "keep/scripts/tool.py"
_SETTINGS = _C + "settings.json"


def _fake(tmp_path: Path) -> list[str]:
    """A tree whose live surfaces cite every shape, beside an archival file citing a deleted rule."""
    for rel in (_LIVE_RULE, _KEEP_SKILL, _A_FLOW, _A_HOOK, _A_REF, _A_SCRIPT, _SETTINGS):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("a guidance file\n")
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text(f"reads `{_LIVE_RULE}`, `{_KEEP_SKILL}`, `{_A_FLOW}`, `{_A_HOOK}` and `{_SETTINGS}`\n")
    # The skill cites its own reference and script relatively, as every skill in the tree does.
    (tmp_path / _KEEP_SKILL).write_text("renders `references/ref.md` and runs `scripts/tool.py`\n")
    (tmp_path / "docs" / "plans" / "00001-a.md").write_text(f"cited `{_GONE_RULE}` when written\n")
    return ["CLAUDE.md", _LIVE_RULE, _KEEP_SKILL, _A_FLOW, _A_HOOK, _A_REF, _A_SCRIPT, _SETTINGS, "docs/plans/00001-a.md"]


def test_the_checker_names_a_live_surface_and_leaves_an_archival_one(tmp_path):
    listed = _fake(tmp_path)
    assert dangling(tmp_path, listed, set()) == {}, "the plan's dead citation is archival and out of scope"
    corpus = tmp_path / "CLAUDE.md"
    corpus.write_text(corpus.read_text() + f"and `{_GONE_RULE}`\n")
    assert dangling(tmp_path, listed, set()) == {_GONE_RULE: ["CLAUDE.md"]}
    assert dangling(tmp_path, listed, {_GONE_RULE}) == {}, "an allowlisted path is not dangling"


def test_the_checker_reads_every_citation_shape(tmp_path):
    listed = _fake(tmp_path)
    assert set(citations(tmp_path, listed)) == {_LIVE_RULE, _KEEP_SKILL, _A_FLOW, _A_HOOK, _A_REF, _A_SCRIPT, _SETTINGS}, (
        "a citation shape the tree uses went unread"
    )


def test_a_skills_own_relative_citation_resolves_against_its_directory(tmp_path):
    """`references/x.md` inside a SKILL.md means that skill's own file, and is how the tree usually writes it."""
    listed = _fake(tmp_path)
    (tmp_path / _A_REF).unlink()
    assert dangling(tmp_path, listed, set()) == {_A_REF: [_KEEP_SKILL]}


def test_the_allowlist_check_catches_an_uncited_entry_and_a_resolving_one(tmp_path):
    listed = _fake(tmp_path)
    cited = citations(tmp_path, listed)
    assert stale_allowlist(tmp_path, cited, {_GONE_RULE}) == ([_GONE_RULE], []), "an entry nothing cites is named"
    assert stale_allowlist(tmp_path, cited, {_LIVE_RULE}) == ([], [_LIVE_RULE]), "an entry naming a real file is named"


def test_the_quiet_check_names_a_barren_prefix_and_not_a_citing_one(tmp_path):
    listed = _fake(tmp_path)
    assert quiet_prefixes(tmp_path, listed, ("CLAUDE.md", "docs/")) == {"docs/"}, "the plans dir cites nothing walked"
    (tmp_path / "cli").mkdir()
    (tmp_path / "cli" / "m.py").write_text("# nothing here\n")
    assert quiet_prefixes(tmp_path, listed + ["cli/m.py"], ("cli/",)) == {"cli/"}
    (tmp_path / "cli" / "m.py").write_text(f"# see `{_LIVE_RULE}`\n")
    assert quiet_prefixes(tmp_path, listed + ["cli/m.py"], ("cli/",)) == set()


def test_the_walked_scope_is_the_one_recorded_here():
    """Deleting a prefix shrinks what the other tests iterate over, so the tuple itself is pinned: a scope change is
    a deliberate edit here, which is the move the zero-base made on the rules with nothing to catch it."""
    assert LIVE == (
        "CLAUDE.md",
        ".claude/",
        "docs/reference/",
        "docs/open-topics/",
        "infra/runbooks/",
        "infra/scripts/",
        "infra/ansible/",
        "cli/",
        "tests/",
    )


def test_a_dated_record_is_not_walked_and_the_procedure_beside_it_is(tmp_path):
    """An ops-journal month says what was cited on the day it was written; the README beside it is procedure.
    Editing a merged month to get CI green is the wrong repair, so the month is out and the README is in."""
    journal = tmp_path / "docs" / "reference" / "ops-journal"
    journal.mkdir(parents=True)
    (journal / "2026-09.md").write_text(f"converged per `{_GONE_RULE}` that day\n")
    (journal / "README.md").write_text(f"the monthly routine is `{_GONE_RULE}`\n")
    listed = ["docs/reference/ops-journal/2026-09.md", "docs/reference/ops-journal/README.md"]
    assert dangling(tmp_path, listed, set()) == {_GONE_RULE: ["docs/reference/ops-journal/README.md"]}
