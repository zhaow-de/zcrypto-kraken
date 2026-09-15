"""`infra/scripts/topics-index.py` renders `docs/open-topics/README.md` from the topic files: one section per
status in the order open, partial, resolved; one bullet per topic sorted by serial, the file's own serial stripped
from the H1, another topic's serial kept, and a live topic's `ripe_when` collapsed onto the bullet. A topic whose
status is not one of the three, whose H1 carries a bracket or whose file carries no serial is refused by name; a
text with no H1 is refused by `title`, which has no name to give. `--check` exits 1 when the committed index differs
from the render and names the command that regenerates it; any other argument is usage at exit 2, and writes
nothing."""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "topics-index.py"
_spec = importlib.util.spec_from_file_location("topics_index", _SCRIPT)
topics_index = importlib.util.module_from_spec(_spec)
# Registered before exec: the frozen dataclass resolves its stringized annotations through `sys.modules`.
sys.modules[_spec.name] = topics_index
_spec.loader.exec_module(topics_index)

_OPEN = "---\nstatus: open\nripe_when: |\n  the alert fires\n  twice\n---\n\n# T0002 — Second one\n"
_OPEN_LATER = "---\nstatus: open\n---\n\n# T0020 — Alpha, sorted after T0002 by serial\n"
_PARTIAL = "---\nstatus: partial\n---\n\n# T0010: Tenth, mentions T0002 in its title\n"
_RESOLVED = "---\nstatus: resolved\n---\n\n# T0001 - First one\n"


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    topics = tmp_path / "docs" / "open-topics"
    (topics / "archive").mkdir(parents=True)
    (topics / "T0002-second.md").write_text(_OPEN, encoding="utf-8")
    (topics / "T0020-alpha.md").write_text(_OPEN_LATER, encoding="utf-8")
    (topics / "T0010-tenth.md").write_text(_PARTIAL, encoding="utf-8")
    (topics / "archive" / "T0001-first.md").write_text(_RESOLVED, encoding="utf-8")
    return topics


def test_the_render_sections_by_status_sorts_by_serial_and_carries_a_live_topics_trigger(tmp_path):
    out = topics_index.render(_tree(tmp_path))
    assert out.startswith(topics_index.HEADER)
    assert out.index("## Open\n") < out.index("## Partially done\n") < out.index("## Resolved\n")
    assert "- [T0002 — Second one](T0002-second.md) — ripe when: the alert fires twice\n" in out
    assert "- [T0020 — Alpha, sorted after T0002 by serial](T0020-alpha.md)\n" in out
    assert out.index("- [T0002 — ") < out.index("- [T0020 — ") < out.index("## Partially done\n")
    assert "- [T0010 — Tenth, mentions T0002 in its title](T0010-tenth.md)\n" in out
    assert "- [T0001 — First one](archive/T0001-first.md)\n" in out


@pytest.mark.parametrize(
    ("name", "text", "reason"),
    [
        (
            "T0005-status.md",
            "---\nstatus: done\n---\n\n# T0005 — x\n",
            "T0005-status.md: status 'done' is not one of open, partial, resolved",
        ),
        (
            "T0006-bracket.md",
            "---\nstatus: open\n---\n\n# T0006 — a [link] here\n",
            "T0006-bracket.md: a bracket in the title breaks the index link",
        ),
        ("serial-less.md", "---\nstatus: open\n---\n\n# x\n", "serial-less.md: no T<NNNN> serial"),
        ("T0008-no-h1.md", "---\nstatus: open\n---\n\nplain text only\n", "no H1 title"),
    ],
)
def test_a_malformed_topic_is_refused_by_name(tmp_path, name, text, reason):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=re.escape(reason)):
        topics_index.topic(path, tmp_path)


@pytest.fixture
def rooted(tmp_path, monkeypatch):
    topics = _tree(tmp_path)
    monkeypatch.setattr(topics_index, "REPO", tmp_path)
    monkeypatch.setattr(topics_index, "TOPICS", topics)
    # `render`'s default root was bound at definition time, so the module attribute alone leaves `main` rendering the repo.
    monkeypatch.setattr(topics_index.render, "__defaults__", (topics,))
    return topics


def test_main_writes_the_index_and_check_reads_it_back(rooted, capsys):
    index = rooted / "README.md"
    assert topics_index.main(["topics-index.py"]) == 0
    assert index.read_text(encoding="utf-8") == topics_index.render(rooted)
    assert topics_index.main(["topics-index.py", "--check"]) == 0
    index.write_text(index.read_text(encoding="utf-8") + "- a hand-added bullet\n", encoding="utf-8")
    assert topics_index.main(["topics-index.py", "--check"]) == 1
    assert (
        "docs/open-topics/README.md differs from the render; run `uv run python infra/scripts/topics-index.py`"
        in capsys.readouterr().err
    )


def test_any_other_argument_is_usage_and_writes_nothing(rooted, capsys):
    assert topics_index.main(["topics-index.py", "--write"]) == 2
    assert not (rooted / "README.md").exists()
    assert "Usage: topics-index.py [--check]" in capsys.readouterr().err
