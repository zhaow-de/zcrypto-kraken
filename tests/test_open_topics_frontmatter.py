"""The open-topics frontmatter invariants, which until now were enforced by eye.

Three things these files must satisfy, which nothing checked. `.claude/rules/open-topics.md`
mandates the `ripe_when` frontmatter and the partial/resolved lifecycle; the three-value
`status` set and the archived-topic rule are `.claude/skills/topic-ops/SKILL.md`'s, which the
rule delegates file mechanics to. That rule's stated reason for deleting a trigger at close
rather than leaving it discharged is the one worth pinning: it makes a hit in `archive/` BY
CONSTRUCTION a stranded live deferral, rather than something to read through and adjudicate.

The YAML one is not theoretical. Seven topics' frontmatter did not parse before the
2026-08-23 hygiene pass -- from three separate causes, a leading backtick, a leading `**`
(read as an alias) and an embedded ": " (read as a nested mapping) -- and the pass itself
reintroduced the third while writing the paragraph describing it. Nothing consumes the field
programmatically yet, which is exactly why it went unnoticed: the first tool to try would
have been the one to find out.
"""

import re
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


# --- every link in the index lands on a file that exists ------------------------------------------
# The index is the surface every review consults; a link target that drifts from the file on disk
# is a dead pointer nothing else catches. It happened by mechanical rename (2026-08-28): a sed over
# the repo rewrote two ARCHIVE link targets whose files rightly kept their names -- a topic's
# filename is its identity -- and no test noticed.

_INDEX_LINK = re.compile(r"\]\(((?:archive/)?T\d{4}-[A-Za-z0-9._-]+\.md)\)")


def test_every_topic_link_in_the_index_resolves():
    index = TOPICS / "README.md"
    dead = [target for target in _INDEX_LINK.findall(index.read_text()) if not (index.parent / target).is_file()]
    assert not dead, f"index links to files that do not exist: {dead}"


def test_the_index_has_one_title_and_no_blockquote_line():
    """A conflict marker mdformat has rewritten is an extra H1 (`<<<<<<< HEAD` over `=======`) or a blockquote (`>>>>>>>`)."""
    lines = (TOPICS / "README.md").read_text().split("\n")
    titles = [n for n, line in enumerate(lines, 1) if line.startswith("# ")]
    quoted = [n for n, line in enumerate(lines, 1) if line.startswith(">")]
    assert titles == [1], f"the topic index has H1 lines other than its title: {titles}"
    assert not quoted, f"blockquote lines in the topic index: {quoted}"
