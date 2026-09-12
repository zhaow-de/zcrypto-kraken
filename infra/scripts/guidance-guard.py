"""The commit-msg guard over the always-loaded guidance: growth is stated in the message, and a universal is counted. `--uncounted` reads the same universal test over any page as an instrument, refusing nothing."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

SKILL = ".claude/skills/zcrypto-refine-rules/SKILL.md"
CORPUS = re.compile(r"^(CLAUDE\.md|\.claude/rules/[^/]+\.md)$")
CONTRACT = re.compile(
    r"^(docs/reference/fleet\.md|docs/reference/fleet-pins\.md|\.claude/skills/zcrypto-grooming/references/memo-protocol\.md|infra/runbooks/[^/]+\.md)$"
)  # read whole by the sessions and skills that act on them: read for universals like the corpus, never counted as ambient.
# The runbook pages joined on 2026-09-12, once `count-list.sh runbook-universals-without-a-count` read 0 -- the owner's
# ruling of 2026-09-11 that the test binds them, taken as an instrument first and a gate once the number it reads was 0.
SKILL_FILE = re.compile(r"^\.claude/skills/[^/]+/SKILL\.md$")
WORKFLOW_FILE = re.compile(r"^\.claude/workflows/[^/]+\.js$")
META_OPEN = "export const meta = {"  # the authoring reference's own shape, and the only one read
META_KEY = re.compile(r"^  (name|description|whenToUse):", re.M)
META_FIELD = re.compile(
    r"^  (name|description|whenToUse): '((?:[^'\\\n]|\\.)*)',?[ \t]*(?://.*)?$", re.M
)  # a trailing comment is the reference's own example
JS_ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", re.S)
_SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


class Unreadable(ValueError):
    """A file the guard will not measure: refused with the shape it reads, never guessed at."""


def _unescape(value: str) -> str:
    """A single-quoted JavaScript string's escapes resolved to the characters the harness lists."""
    if re.search(
        r"(?<!\\)(?:\\\\)*\\u\{", value
    ):  # an odd run of backslashes before u{ is the escape; an even one is a literal backslash
        raise Unreadable("a `\\u{...}` escape in a listed string: write the character itself")
    return JS_ESCAPE.sub(
        lambda m: (
            chr(int(m.group(1)[1:], 16)) if m.group(1)[0] in "ux" and len(m.group(1)) > 1 else _SIMPLE.get(m.group(1), m.group(1))
        ),
        value,
    )


def _meta_block(text: str) -> str:
    """The lines between `export const meta = {` on the file's first line and the first line that starts with `}`, which must be `}` alone; anything else is refused."""
    lines = text.split("\n")
    if not lines or lines[0] != META_OPEN:
        raise Unreadable("the meta literal is not `export const meta = {` on the file's first line")
    for i, line in enumerate(lines[1:], 1):
        if line.startswith("}"):
            if line.rstrip() != "}":
                raise Unreadable("the meta literal's closing `}` is not alone on its own line")
            return "\n".join(lines[1:i])
    raise Unreadable("the meta literal has no closing `}` alone on its own line")


def workflow_listed(text: str) -> list[str]:
    """The strings the harness lists for a saved workflow, read from the one meta shape the guard accepts."""
    block = _meta_block(text)
    fields = {key: _unescape(value) for key, value in META_FIELD.findall(block)}
    if len(META_KEY.findall(block)) != len(fields):
        raise Unreadable("a name, description or whenToUse line that is not one single-quoted string on its own line")
    for key in ("name", "description"):
        if key not in fields:
            raise Unreadable(f"no `{key}:` line in the meta literal, which the authoring reference requires")
    return list(fields.values())


GROWTH_LINE = re.compile(r"^Ambient grows by (\d+) bytes: \S", re.M)
UNIVERSAL = re.compile(r"\b(every|never|always|only|any|cannot)\b", re.I)
CODE_SPAN = re.compile(r"`[^`]*`")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)]) ")
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
    """What a session pays for the file on every turn: a corpus file whole; a skill's name and description values, block scalars included; a workflow's listed text -- the name, description and whenToUse strings of its meta literal."""
    if CORPUS.match(path):
        return len(text.encode())
    if SKILL_FILE.match(path):
        total, inside = 0, False
        for line in frontmatter_lines(text):
            if line.startswith(("name:", "description:")):
                inside = True
            elif line.strip() and not line[:1].isspace():
                inside = False  # a new top-level key ends a folded or literal block; a blank line inside one does not
            if inside:
                total += len(line.encode()) + 1
        return total
    if WORKFLOW_FILE.match(path):
        return sum(
            len(value.encode()) + 1 for value in workflow_listed(text)
        )  # the listed text, escapes resolved; an unreadable meta raises
    return 0


def bullets(text: str) -> list[tuple[int, str]]:
    """Each bullet, nested ones included and fenced blocks skipped, as its first line number and its text with continuation lines joined -- an indented fence keeps its list item open, so a step's prose under its command block is read."""
    out: list[tuple[int, str]] = []
    open_bullet = fenced = False
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            if fenced:
                fenced = False
            else:
                fenced = True
                # An INDENTED fence belongs to the open list item -- a step's command block, with the step's
                # own prose continuing under it. Closing the bullet here would leave that prose unread, which
                # is a universal the instrument cannot see and the gate cannot refuse.
                open_bullet = open_bullet and line[:1].isspace()
        elif fenced:
            continue
        elif BULLET.match(line):
            out.append((i, line))
            open_bullet = True
        elif open_bullet and line.strip() and line[:1].isspace():
            out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())
        else:
            open_bullet = False
    return out


def universals_without_a_count(text: str) -> list[tuple[int, str]]:
    """Bullets whose prose outside code spans carries a universal word, with neither a count entry nor a no-count declaration: (line, word)."""
    hits: list[tuple[int, str]] = []
    for i, block in bullets(text):
        m = UNIVERSAL.search(CODE_SPAN.sub("", block))
        if m and not any(c in block for c in COUNTED):
            hits.append((i, m.group(0)))
    return hits


def uncounted_universals(path: str, text: str) -> list[tuple[int, str]]:
    """The corpus and contract bullets a commit is refused on; `--uncounted` reads any page with the same test and refuses nothing."""
    if not (CORPUS.match(path) or CONTRACT.match(path)):
        return []
    return universals_without_a_count(text)


def evaluate(before: dict[str, str], after: dict[str, str], message: str, against: str = "") -> list[str]:
    """before/after map each ambient path the commit changes to its text at the basis and in the commit; a missing key is an absent file; `against` names a basis other than HEAD in a refusal."""
    fails: list[str] = []
    growth = 0
    for p in sorted(set(before) | set(after)):
        try:
            now = ambient_bytes(p, after[p]) if p in after else 0  # a deletion is a shrink, never a read of nothing
        except Unreadable as exc:
            fails.append(f"{p}: {exc} — {SKILL}")
            continue
        try:
            was = ambient_bytes(p, before[p]) if p in before else 0
        except Unreadable:
            was = 0  # a basis the guard cannot read counts as nothing, so the commit that reshapes it states the whole listed text
        growth += now - was
    lines = GROWTH_LINE.findall(message)
    if len(lines) > 1:
        fails.append(f"two `Ambient grows by` lines in the message; one, with the whole commit's growth — {SKILL}")
    n = int(lines[0]) if lines else None
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


def _clean(raw: str) -> tuple[str, str]:
    """A message as git records it: nothing below the scissors line, no comment lines; and its subject as `%s` renders it, the first paragraph joined by spaces."""
    kept: list[str] = []
    for line in raw.split("\n"):
        if line.startswith(SCISSORS):
            break
        if not line.startswith("#"):
            kept.append(line)
    text = "\n".join(kept)
    body = [line.strip() for line in kept]
    while body and not body[0]:
        body.pop(0)
    first: list[str] = []
    for line in body:
        if not line:
            break
        first.append(line)
    return text, " ".join(first)


def _message(path: str) -> tuple[str, str]:
    return _clean(pathlib.Path(path).read_text())


def _judged(paths: list[str]) -> list[str]:
    """The paths a commit is judged on: the ambient set for growth and universals, the contracts for universals alone."""
    return [p for p in paths if CORPUS.match(p) or SKILL_FILE.match(p) or WORKFLOW_FILE.match(p) or CONTRACT.match(p)]


def range_fails(base: str, head: str) -> list[str]:
    """Every non-merge commit of base..head judged against its first parent -- the record a rewrite may have lost or doubled, which no commit-msg hook sees."""
    listed = _git("rev-list", "--reverse", "--no-merges", f"{base}..{head}")
    if listed.returncode != 0:
        return [f"cannot list {base}..{head}: {listed.stderr.strip()}"]
    out: list[str] = []
    for commit in listed.stdout.split():
        changed = _git("diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", "--root", commit).stdout.split("\n")
        paths = _judged(changed)
        if not paths:
            continue
        before = {p: t for p in paths if (t := _show(f"{commit}^:{p}")) is not None}
        after = {p: t for p in paths if (t := _show(f"{commit}:{p}")) is not None}
        message, subject = _clean(_git("log", "-1", "--format=%B", commit).stdout)
        for fail in evaluate(before, after, message, " against its parent"):
            out.append(f"{commit[:8]} {subject}: {fail}")
    return out


def tree_ambient_bytes(root: pathlib.Path) -> int:
    paths = [
        root / "CLAUDE.md",
        *sorted((root / ".claude" / "rules").glob("*.md")),
        *sorted((root / ".claude" / "skills").glob("*/SKILL.md")),
        *sorted((root / ".claude" / "workflows").glob("*.js")),
    ]
    total = 0
    for p in paths:
        if not p.is_file():
            continue
        try:
            total += ambient_bytes(str(p.relative_to(root)), p.read_text())
        except Unreadable as exc:
            raise Unreadable(f"{p.relative_to(root)}: {exc}") from None
    return total


def main(argv: list[str]) -> int:
    top = _git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        print(top.stderr, file=sys.stderr)
        return 2
    root = pathlib.Path(top.stdout.strip())
    if argv[1:] == ["--ambient-bytes"]:
        try:
            print(tree_ambient_bytes(root))
        except Unreadable as exc:
            print(f"guidance-guard: a workflow the guard cannot measure -- {exc}", file=sys.stderr)
            return 2
        return 0
    if argv[1:2] == ["--uncounted"]:
        if len(argv) == 2:
            print("usage: guidance-guard.py --uncounted <page>...", file=sys.stderr)
            return 2
        for path in argv[2:]:  # the runbook instrument: one line per bullet carrying an uncounted universal, never a refusal
            try:
                text = pathlib.Path(path).read_text()
            except OSError as exc:
                print(f"guidance-guard: cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
                return 2
            for i, word in universals_without_a_count(text):
                print(f"{path}:{i} {word}")
        return 0
    if argv[1:2] == ["--range"] and len(argv) == 3 and ".." in argv[2] and "..." not in argv[2]:
        base, head = argv[2].split("..", 1)
        fails = range_fails(base, head)
        if fails:
            print(f"guidance-guard: refused over {argv[2]}")
            for fail in fails:
                print("  - " + fail)
            return 1
        print(f"guidance-guard: every commit of {argv[2]} states its ambient growth")
        return 0
    if len(argv) != 2:
        print(
            "usage: guidance-guard.py <commit-message-file> | --ambient-bytes | --range <base>..<head> | --uncounted <page>...",
            file=sys.stderr,
        )
        return 2
    merge_head = _git("rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    if merge_head and os.path.exists(merge_head):
        return 0  # a merge commit carries the other branch's growth, which was judged at its own commits
    message, subject = _message(argv[1])
    basis, against = "HEAD", ""
    if _git("rev-parse", "--verify", "-q", "HEAD").returncode != 0:
        basis = None  # a repository's first commit: the index against the empty tree
    elif (
        subject
        and subject == _git("log", "-1", "--format=%s").stdout.strip()
        and _git("rev-parse", "--verify", "-q", "HEAD~1").returncode == 0
    ):
        basis = "HEAD~1"  # an amend keeps its subject; the resulting commit's growth is against its parent
        against = " against HEAD~1, the amended commit's parent, since the subject is unchanged"
    staged = _git("diff", "--cached", "--name-only", "--no-renames", *([basis] if basis else []))  # the index against the basis
    if staged.returncode != 0:
        print(staged.stderr, file=sys.stderr)
        return 2
    paths = _judged(staged.stdout.split("\n"))
    if not paths:
        return 0
    before = {p: t for p in paths if basis and (t := _show(f"{basis}:{p}")) is not None}
    after = {p: t for p in paths if (t := _show(f":{p}")) is not None}
    fails = evaluate(before, after, message, against)
    if fails:
        print("guidance-guard: refused")
        for fail in fails:
            print("  - " + fail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
