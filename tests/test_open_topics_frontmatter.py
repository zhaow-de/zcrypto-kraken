"""The open-topics frontmatter invariants `.claude/skills/topic-ops/SKILL.md` states, checked
mechanically."""

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

TOPICS = Path(__file__).resolve().parents[1] / "docs" / "open-topics"
OPEN_TOPICS = sorted(TOPICS.glob("T*.md"))
ARCHIVED = sorted((TOPICS / "archive").glob("T*.md"))
VALID_STATUS = {"open", "partial", "resolved"}


def _frontmatter(path: Path) -> str:
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert m, f"{path.name}: no YAML frontmatter block"
    return m.group(1)


def test_the_topic_directories_are_not_empty():
    """A glob that silently matched nothing would make every parametrized test below vacuous."""
    assert OPEN_TOPICS, "no open topics found -- the glob is wrong, not the tree"
    assert ARCHIVED, "no archived topics found -- the glob is wrong, not the tree"


@pytest.mark.parametrize("path", OPEN_TOPICS + ARCHIVED, ids=lambda p: p.name)
def test_frontmatter_parses_as_yaml_with_a_valid_status(path: Path):
    data = yaml.safe_load(_frontmatter(path))
    assert isinstance(data, dict), f"{path.name}: frontmatter is {type(data).__name__}, not a mapping"
    assert data.get("status") in VALID_STATUS, f"{path.name}: status={data.get('status')!r}"


@pytest.mark.parametrize("path", ARCHIVED, ids=lambda p: p.name)
def test_an_archived_topic_carries_no_ripe_when(path: Path):
    """Closing deletes the trigger rather than leaving it discharged, so that a `ripe_when` in
    `archive/` is by construction a live deferral that was archived with the topic."""
    assert "ripe_when" not in yaml.safe_load(_frontmatter(path)), (
        f"{path.name}: an archived topic still carries a ripe_when -- either it is not really "
        f"resolved, or the trigger should have been deleted at close"
    )


# --- the archived shape: one Resolution, nothing that reads as pending ----------------------------
# `.claude/skills/topic-ops/SKILL.md`'s *Closing a topic*: a `partial` topic's `## Done so far` is
# RENAMED to `## Resolution` and no `## Suggested next steps` survives, because a line under either
# heading reads as pending whatever it says and an archived file is never reviewed again. These three
# hold what that rule asks for; the sweep that made them green is this branch.

_HEADING = re.compile(r"^##+ +(.+?)\s*$", re.M)


def _headings(path: Path, prefix: str) -> list[str]:
    """Every heading of this file whose text begins with `prefix` -- a prefix, not an equality, because
    a section may carry a date or a clause (`## Done so far -- the alert leg (2026-07-26)`)."""
    return [h for h in _HEADING.findall(path.read_text()) if h.startswith(prefix)]


@pytest.mark.parametrize("path", ARCHIVED, ids=lambda p: p.name)
def test_an_archived_topic_records_how_it_was_disposed_of(path: Path):
    """An archived topic whose work is done but unrecorded is indistinguishable on inspection from one
    whose work was never done."""
    found = _headings(path, "Resolution")
    assert found, (
        f"{path.name}: an archived topic carries no `## Resolution` -- it records no commit, PR, spec or "
        f"measurement that disposed of it, so nothing here distinguishes done from never done"
    )
    assert len(found) == 1, (
        f"{path.name}: {len(found)} headings begin `Resolution` ({found}) -- two of them means a fold left "
        f"the old section standing beside the new one, and a reader cannot tell which records the close"
    )


@pytest.mark.parametrize("path", ARCHIVED, ids=lambda p: p.name)
def test_an_archived_topic_carries_no_done_so_far(path: Path):
    """`Done so far` is the heading of a live partial: its name says the work is unfinished, and the
    archive holds finished work. At close it is renamed, or folded into the Resolution that exists."""
    assert not _headings(path, "Done so far"), (
        f"{path.name}: an archived topic still carries `## Done so far` -- rename it to `## Resolution`, "
        f"or fold its body into the Resolution already there"
    )


@pytest.mark.parametrize("path", ARCHIVED, ids=lambda p: p.name)
def test_an_archived_topic_carries_no_suggested_next_steps(path: Path):
    """A line under this heading reads as pending whatever label it carries, and an archived file is
    never reviewed again -- so a deferral left there is lost rather than parked."""
    assert not _headings(path, "Suggested next steps"), (
        f"{path.name}: an archived topic still carries `## Suggested next steps` -- each bullet is "
        f"answered in the Resolution, or named there as left open at the close"
    )


# --- the live shape: the four sections `.claude/skills/topic-ops/SKILL.md`'s *Required file shape* lists,
# and `## Done so far` on a partial alone -----------------------------------------------------------------

_LIVE_SECTIONS = ("Context — what", "Why this matters", "Findings so far", "Suggested next steps")


@pytest.mark.parametrize("path", OPEN_TOPICS, ids=lambda p: p.name)
def test_a_live_topic_carries_the_four_sections(path: Path):
    """A section edit anchored on a string whose first occurrence sits inside body prose deletes whole
    sections silently, and the heading set is what shows it."""
    missing = [s for s in _LIVE_SECTIONS if not _headings(path, s)]
    assert not missing, f"{path.name}: no heading begins {missing} -- a live topic carries all of {_LIVE_SECTIONS}"


@pytest.mark.parametrize("path", OPEN_TOPICS, ids=lambda p: p.name)
def test_done_so_far_marks_a_partial_and_nothing_else(path: Path):
    """`Done so far` records what landed: a `partial` without one records nothing, and an `open` topic with
    one is status drift -- work landed and the frontmatter did not follow."""
    status = yaml.safe_load(_frontmatter(path))["status"]
    found = _headings(path, "Done so far")
    assert bool(found) == (status == "partial"), (
        f"{path.name}: status={status!r} with {len(found)} `Done so far` heading(s) -- a partial carries one, any other status none"
    )


# --- every live topic carries a trigger: the counter's decision, as a gate -------------------------
# CLAUDE.md's topics line: a live topic's `ripe_when:` is one of six shapes -- a date, another topic's
# resolution, an alert, an evaluation statement, a milestone, an activity -- and `infra/scripts/
# count-list.sh live-topics-without-a-trigger` is the count under it. That counter's whole grammar is one
# grep, `grep -L '^ripe_when:' docs/open-topics/T*.md`: a live file with no line opening `ripe_when:`.
# The six shapes themselves are semantic -- nothing mechanical separates a milestone from an activity,
# and a grammar tight enough to try would refuse ordinary triggers -- so the shape is read by hand in
# `zcrypto-daily-ops` §5b, and these decide exactly what the counter decides and no more: the regex is
# the counter's, and the tie test reads it back from the script so the two move together.

COUNT_LIST = TOPICS.parents[1] / "infra" / "scripts" / "count-list.sh"
_TRIGGER_LINE = re.compile(r"^ripe_when:", re.M)
_COUNTER_GREP = re.compile(r"^c_topics_without_a_trigger\(\) \{[^\n]*grep -L '([^']*)' docs/open-topics/T\*\.md", re.M)


def carries_a_trigger(text: str) -> bool:
    """The counter's decision over one file: a line opening `ripe_when:` anywhere in it -- the whole file,
    not the frontmatter, because that is what the grep reads; a key indented, mistyped or absent is none."""
    return bool(_TRIGGER_LINE.search(text))


@pytest.mark.parametrize("path", OPEN_TOPICS, ids=lambda p: p.name)
def test_a_live_topic_carries_a_trigger(path: Path):
    """A live topic with no trigger waits on nothing anyone can evaluate, and the counter that would show
    it is a number to read, not a gate."""
    assert carries_a_trigger(path.read_text(encoding="utf-8")), (
        f"{path.name}: no line opens `ripe_when:` -- a live topic carries a trigger in one of the six shapes "
        f"CLAUDE.md names, or it is not a topic (`.claude/skills/topic-ops/SKILL.md`, *Before the file exists*)"
    )


def test_the_trigger_grammar_is_the_counters():
    """`count-list.sh live-topics-without-a-trigger` and this file decide by the same pattern, or one of
    them reports a number the other does not gate."""
    m = _COUNTER_GREP.search(COUNT_LIST.read_text(encoding="utf-8"))
    assert m, "the counter's function is gone, renamed, or no longer a `grep -L '<pattern>' docs/open-topics/T*.md`"
    assert m.group(1) == _TRIGGER_LINE.pattern, (
        f"the counter greps {m.group(1)!r} and this file {_TRIGGER_LINE.pattern!r} -- move both, or the gate and the count disagree"
    )


@pytest.mark.parametrize(
    ("text", "carried"),
    [
        ("---\nstatus: open\nripe_when: rung 1 produces real fills\n---\n\n# a title\n", True),
        ('---\nstatus: partial\nripe_when: "per family — B2: settled; C1: weeks of captured L2 exist"\n---\n', True),
        ("---\nstatus: open\nripe_when: 'the first armed session''s order\n  survives a restart'\n---\n", True),
        ("---\nstatus: open\n---\n\nripe_when: a line in the body\n", True),
        ("---\nstatus: open\n---\n\n# a title\n", False),
        ("---\nstatus: open\nripe-when: a mistyped key\n---\n", False),
        ("---\nstatus: open\n  ripe_when: indented under nothing\n---\n", False),
        ("---\nstatus: open\nripe_when_note: a longer key\n---\n", False),
        ("---\nstatus: open\n# ripe_when: commented out\n---\n", False),
    ],
    ids=[
        "plain-value",
        "double-quoted-value",
        "single-quoted-folded-value",
        "body-line-admitted-as-the-counter-admits-it",
        "no-key",
        "mistyped-key",
        "indented-key",
        "longer-key",
        "commented-key",
    ],
)
def test_carries_a_trigger_reads_the_line_the_counter_reads(text: str, carried: bool):
    """Both directions of the grep: the value's quoting and folding are not read, and a key that is not
    `ripe_when:` at column 0 is not a trigger. The body-line case is admitted on purpose -- the counter
    reads the whole file, and a frontmatter-only rewrite here would gate what the counter does not count."""
    assert carries_a_trigger(text) is carried


# --- every link in the index lands on a file that exists ------------------------------------------
# A topic's filename is its identity: a sweep that rewrites a link target rather than moving the
# file leaves a dead pointer here.

_INDEX_LINK = re.compile(r"\]\(((?:archive/)?T\d{4}-[A-Za-z0-9._-]+\.md)\)")


def test_every_topic_link_in_the_index_resolves():
    index = TOPICS / "README.md"
    dead = [target for target in _INDEX_LINK.findall(index.read_text()) if not (index.parent / target).is_file()]
    assert not dead, f"index links to files that do not exist: {dead}"


def test_the_index_has_one_title_and_no_blockquote_line():
    """A second `# ` line or a `>` line is a conflict marker's residue or a hand edit; the render has one title and no blockquote."""
    lines = (TOPICS / "README.md").read_text().split("\n")
    titles = [n for n, line in enumerate(lines, 1) if line.startswith("# ")]
    quoted = [n for n, line in enumerate(lines, 1) if line.startswith(">")]
    assert titles == [1], f"the topic index has H1 lines other than its title: {titles}"
    assert not quoted, f"blockquote lines in the topic index: {quoted}"


# --- each topic has exactly one bullet in the index ------------------------------------------------
# A rebase that keeps both sides of an index conflict re-adds the bullet the other side had moved, so a
# topic reads twice. A link inside another bullet's description is a cross-reference, not a bullet.

_BULLET_ID = re.compile(r"^- \[(T\d{4})[^\]]*\]\(")


def duplicate_bullets(text: str) -> list[str]:
    """Every index line whose leading link repeats a topic an earlier bullet already led with."""
    first: dict[str, int] = {}
    defects: list[str] = []
    for n, line in enumerate(text.split("\n"), 1):
        m = _BULLET_ID.match(line)
        if not m:
            continue
        tid = m.group(1)
        if tid in first:
            defects.append(f"line {n}: {tid} has a second bullet (first at line {first[tid]})")
        first.setdefault(tid, n)
    return defects


_ANY_TOPIC_ITEM = re.compile(r"^\s*[-*+] .*\]\((?:archive/)?T\d{4}-")


def _generator():
    spec = importlib.util.spec_from_file_location(
        "topics_index_under_test", TOPICS.parents[1] / "infra" / "scripts" / "topics-index.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # registered before exec, so the dataclass resolves its annotations
    spec.loader.exec_module(mod)
    return mod


def test_the_index_is_the_render_of_the_topic_files():
    """The index is derived state: a bullet, a section or a clause that differs from what the topic files render is a hand edit or a stale regeneration."""
    assert (TOPICS / "README.md").read_text(encoding="utf-8") == _generator().render(TOPICS), (
        "docs/open-topics/README.md differs from the render -- run `uv run python infra/scripts/topics-index.py`"
    )


def test_the_render_places_a_topic_by_status_and_carries_a_live_trigger(tmp_path):
    (tmp_path / "archive").mkdir()
    (tmp_path / "T0002-b.md").write_text(
        "---\nstatus: open\nripe_when: 'when the\n  moon\n  is full'\n---\n\n# T0002 — a live one\n"
    )
    (tmp_path / "T0003-c.md").write_text("---\nstatus: partial\n---\n\n# Half done\n")
    (tmp_path / "archive" / "T0001-a.md").write_text("---\nstatus: resolved\n---\n\n# Done long ago\n")
    (tmp_path / "T0004-d.md").write_text("---\nstatus: open\n---\n\n# T0002 — a title that opens with another topic's serial\n")
    text = _generator().render(tmp_path)
    assert text.index("## Open") < text.index("## Partially done") < text.index("## Resolved")
    assert "- [T0002 — a live one](T0002-b.md) — ripe when: when the moon is full\n" in text
    assert "- [T0003 — Half done](T0003-c.md)\n" in text
    assert "- [T0004 — T0002 — a title that opens with another topic's serial](T0004-d.md)\n" in text
    assert "- [T0001 — Done long ago](archive/T0001-a.md)\n" in text


def test_the_index_has_one_bullet_per_topic():
    text = (TOPICS / "README.md").read_text()
    assert duplicate_bullets(text) == []
    admitted = {m.group(1) for m in (_BULLET_ID.match(line) for line in text.split("\n")) if m}
    assert admitted == {p.name[:5] for p in OPEN_TOPICS + ARCHIVED}, "a topic file with no bullet, or a bullet with no file"
    unhandled = [n for n, line in enumerate(text.split("\n"), 1) if _ANY_TOPIC_ITEM.match(line) and not _BULLET_ID.match(line)]
    assert not unhandled, f"list items linking a topic in a shape the checker does not read: {unhandled}"


def test_duplicate_bullets_names_a_second_bullet_and_ignores_a_cross_reference():
    """A topic with two bullets is named once, at the second; a link to it inside another bullet's text is not a bullet."""
    planted = "\n".join(
        [
            "# index",
            "- [T0001 — a](archive/T0001-a.md) — resolved.",
            "- [T0002 — b](archive/T0002-b.md) — resolved with [T0001](archive/T0001-a.md) beside it.",
            "- [T0001 — a](archive/T0001-a.md) — resolved again.",
        ]
    )
    assert duplicate_bullets(planted) == ["line 4: T0001 has a second bullet (first at line 2)"]
