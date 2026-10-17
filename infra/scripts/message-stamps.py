"""The commit-msg guard over a message's stamps: memo-guard's placeholder-stamp pattern, refused in the message as in an
Edit or a Write. Below git's scissors line is the diff `commit -v` appends; a `#` line is read, since git keeps it from
`-m` and `-F`."""

from __future__ import annotations

import pathlib
import re
import sys

SCISSORS = "# ------------------------ >8 ------------------------"
SPAN = re.compile(r"`[^`\n]*`")
CANDIDATE = re.compile(r"(?i)[0-9x?]{2}:[0-9x?]{2}(?![0-9a-f])")
UNREAD = re.compile(r"(?i)[x?]")


def stamps(raw: str) -> list[tuple[int, str]]:
    """Each placeholder stamp of the message with its line number in the file, in order."""
    found: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(raw.split("\n"), 1):
        if line.startswith(SCISSORS):
            break
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        found.extend((number, m.group()) for m in CANDIDATE.finditer(SPAN.sub(" ", line)) if UNREAD.search(m.group()))
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: message-stamps.py <commit-message-file>", file=sys.stderr)
        return 2
    try:
        raw = pathlib.Path(argv[1]).read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        print(f"message-stamps: cannot read {argv[1]}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    found = stamps(raw)
    if not found:
        return 0
    print("message-stamps: refused")
    for number, stamp in found:
        print(f"  - line {number}: '{stamp}'")
    print(
        "  a placeholder stamp: paste the printed value of `date -u` or of the record (an mtime, a reflog, a PR's"
        " createdAt); a stamp quoted on purpose goes in a code span or a fenced block"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
