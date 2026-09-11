"""Render docs/open-topics/README.md from the topic files -- three lists by status, one bullet per topic with its title and, for a live topic, its trigger -- so the index is derived state, never hand-maintained.

Usage: topics-index.py [--check]  -- write the index; with --check, exit 1 when the committed index differs from the render.
"""

from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
TOPICS = REPO / "docs" / "open-topics"
SECTIONS = (("open", "Open"), ("partial", "Partially done"), ("resolved", "Resolved"))
HEADER = (
    "# Open topics\n"
    "\n"
    "Topics worth follow-up are parked here, one file per topic; the file mechanics are the `topic-ops` skill. "
    "This index is rendered from the topic files by `uv run python infra/scripts/topics-index.py` -- edit the topic, "
    "then regenerate; `tests/test_open_topics_frontmatter.py` refuses an index that differs from the render. "
    "A bullet is the topic's serial and title; a live topic's bullet carries its `ripe_when`.\n"
)
SERIAL = re.compile(r"^T(\d{4})-")


@dataclass(frozen=True)
class Topic:
    serial: str
    status: str
    title: str
    ripe: str
    rel: str


def frontmatter(text: str) -> dict:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            loaded = yaml.safe_load("\n".join(lines[1:i]))
            return loaded if isinstance(loaded, dict) else {}
    return {}


def title(text: str, serial: str) -> str:
    """The H1, with the file's own serial stripped when the H1 opens with it; another topic's serial is a cross-reference and stays."""
    for line in text.split("\n"):
        if line.startswith("# "):
            return re.sub(rf"^T{serial}\s*[—:-]\s*", "", line[2:].strip())
    raise ValueError("no H1 title")


def topic(path: pathlib.Path, topics_dir: pathlib.Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    meta = frontmatter(text)
    m = SERIAL.match(path.name)
    if not m:
        raise ValueError(f"{path.name}: no T<NNNN> serial")
    status = str(meta.get("status", ""))
    if status not in {s for s, _ in SECTIONS}:
        raise ValueError(f"{path.name}: status {status!r} is not one of open, partial, resolved")
    ripe = meta.get("ripe_when")
    heading = title(text, m.group(1))
    if "]" in heading or "[" in heading:
        raise ValueError(f"{path.name}: a bracket in the title breaks the index link")
    return Topic(m.group(1), status, heading, " ".join(str(ripe).split()) if ripe else "", path.relative_to(topics_dir).as_posix())


def render(topics_dir: pathlib.Path = TOPICS) -> str:
    topics = [topic(p, topics_dir) for p in [*sorted(topics_dir.glob("T*.md")), *sorted((topics_dir / "archive").glob("T*.md"))]]
    out = [HEADER]
    for status, heading in SECTIONS:
        out.append(f"## {heading}\n")
        for t in sorted((t for t in topics if t.status == status), key=lambda t: t.serial):
            clause = f" — ripe when: {t.ripe}" if t.ripe else ""
            out.append(f"- [T{t.serial} — {t.title}]({t.rel}){clause}")
        out.append("")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    index = TOPICS / "README.md"
    rendered = render()
    if argv[1:] == ["--check"]:
        if index.read_text(encoding="utf-8") == rendered:
            return 0
        print(
            f"{index.relative_to(REPO)} differs from the render; run `uv run python infra/scripts/topics-index.py`", file=sys.stderr
        )
        return 1
    if argv[1:]:
        print(__doc__, file=sys.stderr)
        return 2
    index.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
