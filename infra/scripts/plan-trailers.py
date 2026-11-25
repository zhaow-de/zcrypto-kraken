"""The pre-commit guard over a plan's commit trailers: a line the staged diff adds to a plan under `docs/plans/` that
is a `Co-Authored-By:` trailer naming a model, as `names_a_model` reads one, is refused, because the implementer that
commits the fence may run on another model. The placeholder, a human's trailer and a mention inside a prose line are
admitted, and a line the diff does not add is not judged. A plan with no readable staged content -- outside the index,
unmerged, an index or a staged diff git cannot read, or no git to run -- is refused. Paths are read from the repository
root, where pre-commit runs its hooks."""

from __future__ import annotations

import re
import subprocess
import sys

PLAN = re.compile(r"^docs/plans/.*\.md$")
TRAILER = re.compile(r"(?i)^\s*co-authored-by\s*:\s*(?P<who>.*)$")
FAMILY = re.compile(r"(?i)(?<![a-z])(?:opus|sonnet|haiku|fable)(?![a-z])")
SLOT = re.compile(r"<(?![^>]*claude)[a-z][a-z' -]*>")
ADDRESS = re.compile(r"<(?P<local>[^<>@]*)@(?P<domain>[^<>@]*)>")
MORE = re.compile(r"(?i)claude[^a-z0-9]*[a-z0-9]")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
PLACEHOLDER = "Co-Authored-By: <actual executing model> <noreply@anthropic.com>"


def names_a_model(line: str) -> bool:
    """A `Co-Authored-By:` line names a model when its value carries a family's name in any case, or carries `Claude`
    and a letter or digit after it -- outside its address, or in the address's local part -- with its address at
    anthropic.com or no address at all. A lowercase `<...>` slot is a placeholder and names nothing."""
    trailer = TRAILER.match(line)
    if trailer is None:
        return False
    if FAMILY.search(trailer["who"]):
        return True
    value = SLOT.sub(" ", trailer["who"])
    address = ADDRESS.search(value)
    if address is None:
        return MORE.search(value) is not None
    domain = address["domain"].strip().lower()
    if domain != "anthropic.com" and not domain.endswith(".anthropic.com"):
        return False
    rest = value[: address.start()] + " " + value[address.end() :]
    return MORE.search(rest) is not None or MORE.search(address["local"]) is not None


class Unreadable(Exception):
    pass


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(["git", "--literal-pathspecs", *args], capture_output=True)
    except OSError as exc:
        raise Unreadable(exc.strerror or str(exc)) from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise Unreadable(err[0] if err else f"git exited {proc.returncode}")
    return proc.stdout.decode("utf-8", errors="replace")


def added(diff: str) -> list[tuple[int, str]]:
    """Each line a one-file unified diff adds, with its line number in the new side."""
    found: list[tuple[int, str]] = []
    number, in_hunk = 0, False
    for line in diff.split("\n"):
        hunk = HUNK.match(line)
        if hunk:
            number, in_hunk = int(hunk.group(1)), True
        elif in_hunk and line.startswith("+"):
            found.append((number, line[1:].removesuffix("\r")))
            number += 1
        elif in_hunk and line.startswith(" "):
            number += 1
    return found


def judge(paths: list[str]) -> tuple[list[str], list[str]]:
    """The literal trailers the staged diff adds to the plans among `paths`, and the plans it cannot read."""
    plans = [p for p in paths if PLAN.match(p)]
    if not plans:
        return [], []
    try:
        entries = _git("ls-files", "--stage", "-z", "--", *plans).split("\0")
    except Unreadable as exc:
        return [], [f"{p}: cannot read the index ({exc})" for p in plans]
    listed = [e.partition("\t") for e in entries if e]
    indexed = {path for _, _, path in listed}
    staged = {path for meta, _, path in listed if meta.endswith(" 0")}
    literals: list[str] = []
    unreadable: list[str] = []
    for path in plans:
        if path not in indexed:
            unreadable.append(f"{path}: not in the index, so its staged content cannot be read: stage it, then run again")
            continue
        if path not in staged:
            unreadable.append(f"{path}: unmerged, so its staged content cannot be read: resolve it and stage it, then run again")
            continue
        try:
            diff = _git(
                "diff", "--cached", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--text", "-U0", "--", path
            )
        except Unreadable as exc:
            unreadable.append(f"{path}: cannot read its staged diff ({exc})")
            continue
        for number, line in added(diff):
            if names_a_model(line):
                literals.append(f"{path}:{number}: {line.strip()}")
    return literals, unreadable


def main(argv: list[str]) -> int:
    literals, unreadable = judge(argv[1:])
    if not literals and not unreadable:
        return 0
    print("plan-trailers: refused")
    for item in literals + unreadable:
        print(f"  - {item}")
    if literals:
        print(f"  write the trailer as `{PLACEHOLDER}`; the implementer puts its own model in its place at the commit")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
