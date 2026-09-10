"""The commit-msg guard over the always-loaded guidance: growth is stated in the message, and a universal is counted."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

SKILL = ".claude/skills/zcrypto-refine-rules/SKILL.md"
CORPUS = re.compile(r"^(CLAUDE\.md|\.claude/rules/[^/]+\.md)$")
SKILL_FILE = re.compile(r"^\.claude/skills/[^/]+/SKILL\.md$")
GROWTH_LINE = re.compile(r"^Ambient grows by (\d+) bytes: \S", re.M)
UNIVERSAL = re.compile(r"\b(every|never|always|only|any|cannot)\b", re.I)
COUNTED = ("count: `infra/scripts/count-list.sh ", "(no count command:")


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
    """What a session pays for the file on every turn: a corpus file whole, a skill's name and description lines."""
    if CORPUS.match(path):
        return len(text.encode())
    if SKILL_FILE.match(path):
        return sum(len(line.encode()) + 1 for line in frontmatter_lines(text) if line.startswith(("name:", "description:")))
    return 0


def uncounted_universals(path: str, text: str) -> list[tuple[int, str]]:
    """Corpus bullets carrying a universal word with neither a count entry nor a no-count declaration."""
    if not CORPUS.match(path):
        return []
    return [
        (i, line)
        for i, line in enumerate(text.split("\n"), 1)
        if line.startswith("- ") and UNIVERSAL.search(line) and not any(c in line for c in COUNTED)
    ]


def evaluate(before: dict[str, str], after: dict[str, str], message: str) -> list[str]:
    """before/after map each staged ambient path to its text at HEAD and in the index; a missing key is an absent file."""
    fails: list[str] = []
    growth = sum(ambient_bytes(p, after.get(p, "")) - ambient_bytes(p, before.get(p, "")) for p in set(before) | set(after))
    m = GROWTH_LINE.search(message)
    if growth > 0 and not m:
        fails.append(
            f"the always-loaded guidance grows by {growth} bytes and the message does not say so: add one line "
            f"`Ambient grows by {growth} bytes: <reason>`, or trade the growth for a deletion of that size — {SKILL}"
        )
    elif growth > 0 and int(m.group(1)) != growth:
        fails.append(f"the message says the ambient grows by {m.group(1)} bytes; the staged files grow it by {growth}")
    elif growth <= 0 and m:
        fails.append(f"the message says the ambient grows by {m.group(1)} bytes; the staged files change it by {growth}")
    for path in sorted(after):
        for i, line in uncounted_universals(path, after[path]):
            word = UNIVERSAL.search(line).group(0)
            fails.append(
                f"{path}:{i} carries a universal ({word!r}) with no count entry and no `(no count command: …)` declaration — {SKILL}"
            )
    return fails


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _show(spec: str) -> str | None:
    done = _git("show", spec)
    return done.stdout if done.returncode == 0 else None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: guidance-guard.py <commit-message-file>", file=sys.stderr)
        return 2
    top = _git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        print(top.stderr, file=sys.stderr)
        return 2
    root = pathlib.Path(top.stdout.strip())
    if (root / ".git" / "MERGE_HEAD").exists():
        return 0  # a merge commit carries the other branch's growth, which was judged at its own commits
    staged = _git("diff", "--cached", "--name-only", "--no-renames")
    if staged.returncode != 0:
        print(staged.stderr, file=sys.stderr)
        return 2
    paths = [p for p in staged.stdout.split("\n") if CORPUS.match(p) or SKILL_FILE.match(p)]
    if not paths:
        return 0
    before = {p: t for p in paths if (t := _show(f"HEAD:{p}")) is not None}
    after = {p: t for p in paths if (t := _show(f":{p}")) is not None}
    message = "\n".join(line for line in pathlib.Path(argv[1]).read_text().split("\n") if not line.startswith("#"))
    fails = evaluate(before, after, message)
    if fails:
        print("guidance-guard: refused")
        for fail in fails:
            print("  - " + fail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
