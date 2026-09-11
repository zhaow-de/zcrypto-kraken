"""Count the runbook sections with no trigger, and the ones owed a `Retire when`.

A section's kind marker is its trigger: an ALERT is named by a rule's `Runbook:` link in alerts.yaml, a KNOWN
LIMITATION or SCHEDULED REMINDER by a guard, comment, test or reminder -- a tracked file under cli/, infra/,
tests/ or .claude/ other than its own -- naming it by file and anchor, a PROCEDURE by the intent its heading states. A section
with no kind marker, or a fired kind nothing names, counts.

Usage: runbook-triggers.py [--list] {triggers|retire-when}  -- the count; --list prints each section first.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

REPO = pathlib.Path(__file__).resolve().parents[2]
RUNBOOKS = "infra/runbooks"
ALERTS = "infra/grafana/alerts.yaml"
KINDS = ("ALERT", "KNOWN LIMITATION", "PROCEDURE", "SCHEDULED REMINDER")
FIRED = ("KNOWN LIMITATION", "SCHEDULED REMINDER")  # named by a guard or a reminder, somewhere in the tree
RETIRING = ("ALERT", "KNOWN LIMITATION", "SCHEDULED REMINDER")
NAMERS = (
    "cli/",
    "infra/",
    "tests/",
    ".claude/",
)  # where a guard, a comment, a test, a reminder or a skill step lives; a topic, spec or plan is not a trigger
ANCHOR_CHARS = "[A-Za-z0-9_-]+"  # no dot: a citation that ends a sentence must not swallow the full stop
ANCHOR = re.compile(rf'^<a name="({ANCHOR_CHARS})"></a>$')  # matched on the stripped line, so an indented tag counts
KIND = re.compile(
    r"— (ALERT|KNOWN LIMITATION|PROCEDURE|SCHEDULED REMINDER)(?:\s*$|:)"
)  # the marker ends the heading, or a colon follows it
REF = re.compile(rf"(infra/runbooks/[A-Za-z0-9._-]+\.md)(?:#|`'s `)({ANCHOR_CHARS})")  # file#anchor, or `file`'s `anchor`
ALERT_REF = re.compile(rf"Runbook: (infra/runbooks/[A-Za-z0-9._-]+\.md)#({ANCHOR_CHARS})")
RETIRE = re.compile(r"^#{2,4} Retire when\b|\*\*Retire when\*\*", re.M)


@dataclass(frozen=True)
class Section:
    path: str  # repo-relative
    line: int  # 1-based heading line
    heading: str
    kind: str | None
    anchors: tuple[str, ...]
    body: str


def sections(rel: str, text: str) -> list[Section]:
    """Each `## ` section with the anchors that name it -- the run of `<a name>` lines directly above its heading, and any inside its body -- and its body up to the next heading's anchor run."""
    lines = text.split("\n")
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    out: list[Section] = []
    for n, h in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        lead: list[str] = []
        j = h - 1
        while j >= 0 and (not lines[j].strip() or ANCHOR.match(lines[j].strip())):
            m = ANCHOR.match(lines[j].strip())
            if m:
                lead.insert(0, m.group(1))
            j -= 1
        k = end - 1
        while k > h and (not lines[k].strip() or ANCHOR.match(lines[k].strip())):
            k -= 1
        body = lines[h + 1 : k + 1]
        inner = [m.group(1) for line in body if (m := ANCHOR.match(line.strip()))]
        kind = KIND.search(lines[h])
        out.append(Section(rel, h + 1, lines[h][3:].strip(), kind.group(1) if kind else None, (*lead, *inner), "\n".join(body)))
    return out


def tracked(repo: pathlib.Path) -> list[str]:
    done = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True)
    return done.stdout.split()


def references(repo: pathlib.Path, files: list[str]) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]]]:
    """(the file#anchor pairs alerts.yaml links as a Runbook, the (file, anchor, naming file) triples the tracked text names)."""
    alerts: set[tuple[str, str]] = set()
    tree: set[tuple[str, str, str]] = set()
    for rel in files:
        try:
            text = (repo / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError:
            continue
        if rel == ALERTS:
            alerts.update(ALERT_REF.findall(text))
        tree.update((f, a, rel) for f, a in REF.findall(text))
    return alerts, tree


def runbook_sections(repo: pathlib.Path, files: list[str]) -> list[Section]:
    out: list[Section] = []
    for rel in sorted(files):
        if rel.startswith(RUNBOOKS + "/") and rel.endswith(".md") and rel != f"{RUNBOOKS}/README.md":
            out.extend(sections(rel, (repo / rel).read_text(encoding="utf-8")))
    return out


def untriggered(repo: pathlib.Path, files: list[str] | None = None) -> list[tuple[Section, str]]:
    files = tracked(repo) if files is None else files
    alerts, tree = references(repo, files)
    out: list[tuple[Section, str]] = []
    for s in runbook_sections(repo, files):
        if s.kind is None:
            out.append((s, "no kind marker in the heading"))
        elif s.kind == "ALERT" and not any((s.path, a) in alerts for a in s.anchors):
            out.append((s, "no rule in alerts.yaml links it as its Runbook"))
        elif s.kind in FIRED and not any(
            f == s.path and a in s.anchors and src != s.path and src.startswith(NAMERS) for f, a, src in tree
        ):
            out.append(
                (s, "no guard, comment, test or reminder under cli/, infra/, tests/ or .claude/ names it by file and anchor")
            )
    return out


def without_retire_when(repo: pathlib.Path, files: list[str] | None = None) -> list[tuple[Section, str]]:
    files = tracked(repo) if files is None else files
    return [(s, "no Retire when") for s in runbook_sections(repo, files) if s.kind in RETIRING and not RETIRE.search(s.body)]


def main(argv: list[str]) -> int:
    args = argv[1:]
    listing = "--list" in args
    args = [a for a in args if a != "--list"]
    if args not in (["triggers"], ["retire-when"]):
        print(__doc__, file=sys.stderr)
        return 2
    found = untriggered(REPO) if args == ["triggers"] else without_retire_when(REPO)
    if listing:
        for s, why in found:
            print(f"{s.path}:{s.line} {s.heading} — {why}")
    print(len(found))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
