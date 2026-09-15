"""The commit-msg guard over a message's citations: every `path:line`, `path::symbol`, `T<NNNN>` and hex id the
message carries resolves on a side of the commit, and a message citing what is on neither side is refused.

A commit has two sides and a message describes the move between them, so a citation stands when it resolves in
the staged tree or at HEAD (the line the commit takes away included); under `--range` the sides are the commit
and its first parent. Judged, and refused when nothing resolves it:
- `path:line` -- a path with an extension some tracked file has, then `:` and a line, a range `12-14` or a list
  `12,15` read number by number. The path resolves to a tracked file it equals or is a `/`-bounded suffix of, and
  the token stands when any such file has the line; a path matching nothing is refused only when its first segment
  is a top-level directory of the tree (a typo, a rename), never when git ignores it or a `..` segment sits in it.
- `T<NNNN>` -- refused when no `docs/open-topics/T<NNNN>-*.md` exists on either side, in the archive, or at the tip
  of any local or remote-tracking branch: a serial is registered once, on a branch that may not be merged yet, so
  its file at any tip is the registration. A `/` before it (a branch name) and a lowercase `t<NNNN>` are not read.
- `path::symbol` or `path:symbol` on a Python or shell file -- refused when no line of the file defines the symbol on
  either side: for Python a `def`, `async def`, `class` or `name =` / `name: type =` at any indentation, for shell a
  `name()`, `function name` or `name=` with an optional `export`/`readonly`/`local`; a `::` chain is read segment by
  segment, a `[param]` suffix and a symbol followed by `-` are not read.
- a hex id -- a backticked 7-12 hex, a 40-hex bare or backticked, a backticked 64-hex, each holding a digit and a
  letter. The 7-12 and the 40 are refused when the repository holds no object with that id -- an ambiguous prefix is
  an id it holds -- and no tracked file on either side carries it (an image digest, an upstream commit a spec pins, a
  `spec_hash`); the 64 -- no sha1 object id -- when no tracked file carries it and no blob hashes to it. Left alone:
  an unquoted 7-12 hex and an unquoted 64-hex (the backticks are the citation marker; an unquoted 64 here is
  prove-inert's digest of derived text no side can recompute), a 7-12 span the word `sha256` labels -- quoted or not,
  with spaces, a colon or a newline between them (a truncated content digest) -- and a 40-hex a word character or `/`
  touches, or `.`/`-` with a word after it (`<id>/x`, `<id>.py`, `x-<id>`: a path segment, while a full stop ending a
  sentence is not). A backticked span holding more than a 7-12 or a 64 (`abc1234..def5678`, `abc1234^`) is no id, and
  neither is a hex of another length; a 40-hex inside such a span is still the id it is, and is judged.

Not read at all: a URL, a fenced block, and a code span with whitespace in it (a quoted command) -- the escapes for a
coordinate or id cited on purpose. Refused all the same, and so fenced: a path only a sibling session's branch holds,
a path an earlier commit of this branch renamed away, and an id quoted as dead -- a path is not registered once the
way a serial is, and a rename's old name still sits at every other tip, so tips resolve topics and never paths. An
id the author's own store holds is admitted here whatever any remote has, so an unpushed tip cited by id passes the
hook and is caught only by a `--range` run in a clone without it.

The hook covers commit messages alone. `--range <a>..<b>` judges every non-merge commit of a branch against its own
two sides, by hand; nothing in the tree calls it."""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence

SCISSORS = "# ------------------------ >8 ------------------------"
URL = re.compile(r"\b\w+://[^\s`]+")
SPAN = re.compile(r"`[^`\n]*`")
_PATH = r"(?<![\w./-])(?P<path>[\w./-]*[\w-]\.(?P<ext>[A-Za-z]\w*))"
LINE = re.compile(_PATH + r":(?P<lines>\d+(?:[,-]\d+)*)(?!\w)")
SYMBOL = re.compile(_PATH + r"::?(?P<symbol>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)(?![\w-])")
TOPIC = re.compile(r"(?<![\w/])T(?P<serial>\d{4})(?!\w)")
TOPIC_FILE = re.compile(r"^docs/open-topics/(?:archive/)?T(\d{4})-[^/]+\.md$")
SHORT_ID = re.compile(r"`(?P<hex>[0-9a-f]{7,12})`")
LABELLED = re.compile(r"sha256`?[ :\n]*$")
FULL_ID = re.compile(r"(?<![\w/.-])(?P<hex>[0-9a-f]{40})(?![\w/])(?![.-][\w/-])")
DIGEST = re.compile(r"`(?P<hex>[0-9a-f]{64})`")
EXTENSION = re.compile(r"\.([A-Za-z]\w*)$")
PYTHON, SHELL = {"py"}, {"sh", "bash", "zsh"}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


class Tree:
    """One side a citation may resolve on: the index when `rev` is empty, else a commit or a branch tip; listed only once a message carries a candidate token, and a branch tip only for its topics."""

    def __init__(self, rev: str = "", label: str = "staged") -> None:
        self.rev, self.label = rev, label
        self._paths: list[str] | None = None
        self._topics: set[str] | None = None
        self._digests: set[str] | None = None

    def _list(self, *pathspec: str) -> list[str]:
        if self.rev:
            done = _git("ls-tree", "-r", "--name-only", "-z", self.rev, "--", *pathspec)
        else:
            done = _git("ls-files", "-z", "--full-name", "--", *pathspec)
        return [p for p in done.stdout.split("\0") if p]

    @property
    def paths(self) -> list[str]:
        if self._paths is None:
            self._paths = self._list()
        return self._paths

    @property
    def topics(self) -> set[str]:
        if self._topics is None:
            self._topics = {m.group(1) for p in self._list("docs/open-topics") if (m := TOPIC_FILE.match(p))}
        return self._topics

    @property
    def digests(self) -> set[str]:
        if self._digests is None:
            if self.rev:
                entries = [e.split() for e in _git("ls-tree", "-r", "-z", self.rev).stdout.split("\0") if e]
                ids = [e[2] for e in entries if e[1] == "blob"]
            else:
                entries = [e.split() for e in _git("ls-files", "-s", "-z").stdout.split("\0") if e]
                ids = [e[1] for e in entries if e[0] != "160000"]
            batch = subprocess.run(
                ["git", "cat-file", "--batch"], input="".join(f"{i}\n" for i in ids).encode(), capture_output=True
            )
            self._digests = set(_blob_digests(batch.stdout))
        return self._digests

    def read(self, path: str) -> bytes | None:
        done = subprocess.run(["git", "show", f"{self.rev}:{path}"], capture_output=True)
        return done.stdout if done.returncode == 0 else None

    def carries(self, token: str) -> bool:
        where, cached = ([self.rev], []) if self.rev else ([], ["--cached"])
        return _git("grep", "-q", "-I", "-F", *cached, "-e", token, *where).returncode == 0

    def ignored(self, path: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", "--", path], capture_output=True).returncode == 0

    def has_object(self, hex_id: str) -> bool:
        # Every object whose id starts with the prefix, of any type and however many: `cat-file -e` would refuse an
        # ambiguous one whatever it peels to, and the store holds it all the same.
        return bool(_git("rev-parse", f"--disambiguate={hex_id}").stdout.split())


def clean(raw: str) -> str:
    """Comment lines and the scissors tail go, as the editor path's cleanup drops them; a `#` line a `-m`/`-F` message records (cleanup mode `whitespace`) is not judged."""
    kept: list[str] = []
    for line in raw.split("\n"):
        if line.startswith(SCISSORS):
            break
        if not line.startswith("#"):
            kept.append(line)
    return "\n".join(kept)


def strip(text: str) -> str:
    """The message with fenced blocks, URLs and quoted commands -- a code span with whitespace in it -- taken out; code spans pair left to right within a line, so the prose between two of them is read."""
    kept: list[str] = []
    fenced = False
    for line in text.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            kept.append(line)
    text = URL.sub(" ", "\n".join(kept))
    return SPAN.sub(lambda m: " " if re.search(r"[ \t]", m.group()) else m.group(), text)


def _line_count(data: bytes) -> int:
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _blob_digests(batch: bytes) -> Iterator[str]:
    """sha256 of each body in `git cat-file --batch` output: a `<id> <type> <size>` line, the body, a newline."""
    at = 0
    while at < len(batch):
        end = batch.index(b"\n", at)
        header = batch[at:end].split()
        if len(header) != 3:
            at = end + 1
            continue
        size = int(header[2])
        yield hashlib.sha256(batch[end + 1 : end + 1 + size]).hexdigest()
        at = end + 1 + size + 1


def _defines(text: str, ext: str, name: str) -> bool:
    n = re.escape(name)
    if ext in PYTHON:
        pattern = rf"^\s*(?:(?:async\s+)?def|class)\s+{n}\b|^\s*{n}\s*(?::[^=\n]*)?=(?!=)"
    else:
        pattern = rf"^\s*function\s+{n}\b|^\s*{n}\s*\(\)|^\s*(?:export\s+|readonly\s+|local\s+)?{n}="
    return re.search(pattern, text, re.M) is not None


def judge(text: str, trees: Sequence[Tree], tips: Sequence[Tree] = ()) -> list[str]:
    """Each citation of the message that resolves on none of `trees` -- the staged tree and HEAD, or a commit and its parent -- once per token, lines then symbols then topics then hex ids; a topic id also stands when a `tips` tree holds its file."""
    body = strip(text)
    if not any(p.search(body) for p in (LINE, SYMBOL, TOPIC, SHORT_ID, FULL_ID, DIGEST)):
        return []
    paths = sorted({p for t in trees for p in t.paths})
    extensions = {m.group(1) for p in paths if (m := EXTENSION.search(p))}
    top = {p.split("/", 1)[0] for p in paths if "/" in p}
    fails: list[str] = []
    seen: set[str] = set()

    def candidates(token: str, path: str) -> list[str]:
        found = [p for p in paths if p == path or p.endswith("/" + path)]
        if not found and path.split("/", 1)[0] in top and not trees[0].ignored(path):
            fails.append(f"{token}: no tracked file is or ends with {path}, on either side of the commit")
        return found

    def contents(files: list[str]) -> dict[tuple[str, str], bytes]:
        return {(f, t.label): data for t in trees for f in files if (data := t.read(f)) is not None}

    for m in LINE.finditer(body):
        token, path, ext = m.group(0), m.group("path").removeprefix("./"), m.group("ext")
        if token in seen or ext not in extensions or ".." in path.split("/"):
            continue
        seen.add(token)
        if files := candidates(token, path):
            wanted = [int(n) for n in re.split(r"[,-]", m.group("lines"))]
            counts = {key: _line_count(data) for key, data in contents(files).items()}
            if not any(all(1 <= n <= c for n in wanted) for c in counts.values()):
                fails.append(f"{token}: " + ", ".join(f"{f} has {c} lines {label}" for (f, label), c in counts.items()))
    for m in SYMBOL.finditer(body):
        token, path, ext = m.group(0), m.group("path").removeprefix("./"), m.group("ext")
        if token in seen or ext not in extensions or ext not in PYTHON | SHELL or ".." in path.split("/"):
            continue
        seen.add(token)
        if files := candidates(token, path):
            names = m.group("symbol").split("::")
            texts = [data.decode("utf-8", errors="replace") for data in contents(files).values()]
            if not any(all(_defines(t, ext, n) for n in names) for t in texts):
                fails.append(
                    f"{token}: no line of {' or '.join(files)} defines {' and '.join(names)}, on either side of the commit"
                )
    for m in TOPIC.finditer(body):
        token, serial = m.group(0), m.group("serial")
        if token in seen:
            continue
        seen.add(token)
        if not any(serial in t.topics for t in trees) and not any(serial in t.topics for t in tips):
            fails.append(
                f"{token}: no topic file under docs/open-topics/ or its archive, on either side of the commit or at a branch tip"
            )
    for m in (*SHORT_ID.finditer(body), *FULL_ID.finditer(body), *DIGEST.finditer(body)):
        token = m.group("hex")
        if token in seen or not (re.search(r"\d", token) and re.search(r"[a-f]", token)):
            continue
        if len(token) <= 12 and LABELLED.search(body[: m.start()]):
            continue
        seen.add(token)
        if len(token) == 64:
            if not any(t.carries(token) for t in trees) and not any(token in t.digests for t in trees):
                fails.append(f"{token}: no tracked file carries it or hashes to it, on either side of the commit")
        elif not trees[0].has_object(token) and not any(t.carries(token) for t in trees):
            fails.append(f"{token}: no object has that id, and no tracked file carries it, on either side of the commit")
    return fails


def _tips() -> list[Tree]:
    refs = _git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes").stdout.split()
    return [Tree(ref, ref) for ref in refs]


def range_fails(base: str, head: str) -> list[str]:
    """Every non-merge commit of base..head judged against itself and its first parent -- the message a rewrite may have left citing what neither side holds."""
    listed = _git("rev-list", "--reverse", "--no-merges", f"{base}..{head}")
    if listed.returncode != 0:
        return [f"cannot list {base}..{head}: {listed.stderr.strip()}"]
    out: list[str] = []
    tips = _tips()
    for commit in listed.stdout.split():
        message = clean(_git("log", "-1", "--format=%B", commit).stdout)
        subject = _git("log", "-1", "--format=%s", commit).stdout.strip()
        sides = [Tree(commit, f"at {commit[:8]}")]
        if _git("rev-parse", "--verify", "-q", f"{commit}^").returncode == 0:
            sides.append(Tree(f"{commit}^", "at its parent"))
        for fail in judge(message, sides, tips):
            out.append(f"{commit[:8]} {subject}: {fail}")
    return out


def main(argv: list[str]) -> int:
    top = _git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        print(top.stderr, file=sys.stderr)
        return 2
    if argv[1:2] == ["--range"] and len(argv) == 3 and ".." in argv[2] and "..." not in argv[2]:
        os.chdir(top.stdout.strip())
        fails = range_fails(*argv[2].split("..", 1))
        if fails:
            print(f"message-citations: refused over {argv[2]}")
            for fail in fails:
                print("  - " + fail)
            return 1
        print(f"message-citations: every citation of {argv[2]} resolves")
        return 0
    if len(argv) != 2:
        print("usage: message-citations.py <commit-message-file> | --range <base>..<head>", file=sys.stderr)
        return 2
    try:
        raw = pathlib.Path(argv[1]).read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        print(f"message-citations: cannot read {argv[1]}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    # git reads paths from the working directory -- check-ignore's argument, the subtree ls-files and ls-tree list and the
    # pathspec they take, the names ls-tree prints; only `show <rev>:<path>` is root-relative -- so from a subdirectory no
    # topic resolves and a dead path outside it passes
    os.chdir(top.stdout.strip())
    sides = [Tree()]
    if _git("rev-parse", "--verify", "-q", "HEAD").returncode == 0:
        sides.append(Tree("HEAD", "at HEAD"))
    fails = judge(clean(raw), sides, _tips())
    if fails:
        print("message-citations: refused")
        for fail in fails:
            print("  - " + fail)
        print("  a coordinate or id quoted on purpose goes in a fenced block, or in a code span with a space in it")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
