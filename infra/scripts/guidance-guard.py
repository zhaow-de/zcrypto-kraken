"""The commit-msg guard over the always-loaded guidance: growth is stated in the message, and a universal is counted."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

SKILL = ".claude/skills/zcrypto-refine-rules/SKILL.md"
CORPUS = re.compile(r"^(CLAUDE\.md|\.claude/rules/[^/]+\.md)$")
SKILL_FILE = re.compile(r"^\.claude/skills/[^/]+/SKILL\.md$")
GROWTH_LINE = re.compile(r"^Ambient grows by (\d+) bytes: \S", re.M)
UNIVERSAL = re.compile(r"\b(every|never|always|only|any|cannot)\b", re.I)
CODE_SPAN = re.compile(r"`[^`]*`")
BULLET = re.compile(r"^\s*[-*] ")
COUNTED = ("count: `infra/scripts/count-list.sh ", "(no count command:")
SCISSORS = "# ------------------------ >8 ------------------------"


def frontmatter_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return []
    out: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        out.append(line)
    return out


def ambient_bytes(path: str, text: str) -> int:
    """What a session pays for the file on every turn: a corpus file whole; a skill's name and description values, block scalars included."""
    if CORPUS.match(path):
        return len(text.encode())
    if SKILL_FILE.match(path):
        total, inside = 0, False
        for line in frontmatter_lines(text):
            if line.startswith(("name:", "description:")):
                inside = True
            elif not line[:1].isspace():
                inside = False  # a new top-level key ends a folded or literal block
            if inside:
                total += len(line.encode()) + 1
        return total
    return 0


def bullets(text: str) -> list[tuple[int, str]]:
    """Each bullet, nested ones included, as its first line number and its text with continuation lines joined."""
    out: list[tuple[int, str]] = []
    open_bullet = False
    for i, line in enumerate(text.split("\n"), 1):
        if BULLET.match(line):
            out.append((i, line))
            open_bullet = True
        elif open_bullet and line.strip() and line[:1].isspace():
            out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())
        else:
            open_bullet = False
    return out


def uncounted_universals(path: str, text: str) -> list[tuple[int, str]]:
    """Corpus bullets whose prose outside code spans carries a universal word, with neither a count entry nor a no-count declaration: (line, word)."""
    if not CORPUS.match(path):
        return []
    hits: list[tuple[int, str]] = []
    for i, block in bullets(text):
        m = UNIVERSAL.search(CODE_SPAN.sub("", block))
        if m and not any(c in block for c in COUNTED):
            hits.append((i, m.group(0)))
    return hits


def evaluate(before: dict[str, str], after: dict[str, str], message: str, basis: str = "HEAD") -> list[str]:
    """before/after map each staged ambient path to its text at the basis commit and in the index; a missing key is an absent file."""
    fails: list[str] = []
    growth = sum(ambient_bytes(p, after.get(p, "")) - ambient_bytes(p, before.get(p, "")) for p in set(before) | set(after))
    lines = GROWTH_LINE.findall(message)
    if len(lines) > 1:
        fails.append(f"two `Ambient grows by` lines in the message; one, with the whole commit's growth — {SKILL}")
    n = int(lines[0]) if lines else None
    against = "" if basis == "HEAD" else f" against {basis}, the amended commit's parent, since the subject is unchanged"
    if growth > 0 and n is None:
        fails.append(
            f"the always-loaded guidance grows by {growth} bytes{against} and the message does not say so: add one line "
            f"`Ambient grows by {growth} bytes: <reason>`, or trade the growth for a deletion of that size — {SKILL}"
        )
    elif growth > 0 and n != growth:
        fails.append(f"the message says the ambient grows by {n} bytes; the staged files grow it by {growth}{against} — {SKILL}")
    elif growth <= 0 and n is not None:
        fails.append(f"the message says the ambient grows by {n} bytes; the staged files change it by {growth}{against} — {SKILL}")
    for path in sorted(after):
        for i, word in uncounted_universals(path, after[path]):
            fails.append(
                f"{path}:{i} carries a universal ({word!r}) with no count entry and no `(no count command: …)` declaration — {SKILL}"
            )
    return fails


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _show(spec: str) -> str | None:
    done = _git("show", spec)
    return done.stdout if done.returncode == 0 else None


def _message(path: str) -> tuple[str, str]:
    """The message as git will record it: nothing below the scissors line, no comment lines; and its subject."""
    kept: list[str] = []
    for line in pathlib.Path(path).read_text().split("\n"):
        if line.startswith(SCISSORS):
            break
        if not line.startswith("#"):
            kept.append(line)
    text = "\n".join(kept)
    subject = next((line.strip() for line in kept if line.strip()), "")
    return text, subject


def tree_ambient_bytes(root: pathlib.Path) -> int:
    paths = [
        root / "CLAUDE.md",
        *sorted((root / ".claude" / "rules").glob("*.md")),
        *sorted((root / ".claude" / "skills").glob("*/SKILL.md")),
    ]
    return sum(ambient_bytes(str(p.relative_to(root)), p.read_text()) for p in paths if p.is_file())


def main(argv: list[str]) -> int:
    top = _git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        print(top.stderr, file=sys.stderr)
        return 2
    root = pathlib.Path(top.stdout.strip())
    if argv[1:] == ["--ambient-bytes"]:
        print(tree_ambient_bytes(root))
        return 0
    if len(argv) != 2:
        print("usage: guidance-guard.py <commit-message-file> | --ambient-bytes", file=sys.stderr)
        return 2
    merge_head = _git("rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    if merge_head and os.path.exists(merge_head):
        return 0  # a merge commit carries the other branch's growth, which was judged at its own commits
    staged = _git("diff", "--cached", "--name-only", "--no-renames")
    if staged.returncode != 0:
        print(staged.stderr, file=sys.stderr)
        return 2
    paths = [p for p in staged.stdout.split("\n") if CORPUS.match(p) or SKILL_FILE.match(p)]
    if not paths:
        return 0
    message, subject = _message(argv[1])
    basis = "HEAD"
    if (
        subject
        and subject == _git("log", "-1", "--format=%s").stdout.strip()
        and _git("rev-parse", "--verify", "-q", "HEAD~1").returncode == 0
    ):
        basis = "HEAD~1"  # an amend keeps its subject; the resulting commit's growth is against its parent
    before = {p: t for p in paths if (t := _show(f"{basis}:{p}")) is not None}
    after = {p: t for p in paths if (t := _show(f":{p}")) is not None}
    fails = evaluate(before, after, message, basis)
    if fails:
        print("guidance-guard: refused")
        for fail in fails:
            print("  - " + fail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
