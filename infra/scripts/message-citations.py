"""The commit-msg guard over a message's citations: every `path:line`, `path::symbol` / `path:symbol` and `T<NNNN>` the
message carries resolves on a side of the commit, and a message citing what is on neither side is refused.

A commit has two sides and a message describes the move between them, so a citation stands when it resolves in the STAGED
tree (`git ls-files`, `git show :<path>` -- the file the commit lands) or at HEAD (the file, or the line, the commit takes
away); under `--range` the two sides are the commit and its first parent. What it refuses:
- a `path:line` token -- a path with an extension some tracked file has, a colon, digits; a range `12-14` or a list
  `12,15` is read number by number -- whose line is 0 or past the end of every file the path resolves to on either side;
  the path resolves to a tracked file it equals or is a `/`-bounded suffix of (`nas.md:92`, `roles/nas/tasks/main.yml:206`),
  and a path that resolves to nothing is refused only when it claims a place under a top-level directory of the tree
  (`cli/engine/executer.py:12`, a typo; `tests/test_gone.py:3`, a rename);
- a `T<NNNN>` that names no `docs/open-topics/T<NNNN>-*.md` and no `docs/open-topics/archive/T<NNNN>-*.md` on either side,
  nor at the tip of any local or remote-tracking branch -- a topic another session registered on a branch not yet merged
  is cited by serial here before the merge, and is not a dead citation;
- a `path::symbol` or `path:symbol` token on a Python or shell file whose symbol no line of the file defines on either
  side -- for Python a `def`, an `async def`, a `class` or a module-level `name =` / `name: type =`; for shell a `name()`
  function, a `function name`, or `name=`; a `test_a::TestB::test_c` chain is read segment by segment and a `[param]`
  suffix is not read.

What it deliberately leaves alone -- the false-positive shapes considered and excluded, each one the tree's own usage:
- a URL; anything inside a ``` or ~~~ fenced block; a code span with whitespace in it, which is a quoted command
  (`sed -n '12p' cli/x.py`, `git show HEAD:cli/x.py`) and not a citation -- so a dead coordinate a message quotes on purpose,
  the way a commit that repairs one names it, goes in a fenced block or beside a word in its span;
- a bare basename or a foreign-rooted path that matches nothing: `m.py:1` and `probe.sh:2` are files a test writes into a
  repository of its own, `polars/series/series.py:925` and `apt.py:815` are a library's source, none a tracked-file path;
  an absolute path; a path with a `..` segment; a path git ignores (`.local/`, `data/`);
- a token whose extension no tracked file has -- `status.kraken.com:443` is a host and port, `2.x:` is a version -- and a
  version string, whose "extension" is digits (`0.16.0:`);
- a `T<NNNN>` preceded by `/` (a branch name `fix/T<NNNN>-slug`, a path segment) and the lowercase `t<NNNN>` a branch here
  usually carries; a `T<NNNN>` inside a URL or a fenced block goes with the URL or the block;
- a `path:symbol` token on a file that is not Python or shell (`README.md:badge` is a `version_files` entry quoted from
  `.cz.toml`), and a symbol followed by `-` (`count-list.sh:live-topics` is an entry name, not a function);
- a suffix that resolves to several files: the token stands when any of them has the line or defines the symbol.

The hook covers commit messages alone: dispatch text and PR bodies leave no record in the tree. `--range <a>..<b>` judges
every non-merge commit's message of the range, for a gate to run over a branch."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from collections.abc import Sequence

SCISSORS = "# ------------------------ >8 ------------------------"
URL = re.compile(r"\b\w+://\S+")
COMMAND_SPAN = re.compile(r"`[^`\n]*[ \t][^`\n]*`")
_PATH = r"(?<![\w./-])(?P<path>[\w./-]*[\w-]\.(?P<ext>[A-Za-z]\w*))"
LINE = re.compile(_PATH + r":(?P<lines>\d+(?:[,-]\d+)*)(?!\w)")
SYMBOL = re.compile(_PATH + r"::?(?P<symbol>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)(?![\w-])")
TOPIC = re.compile(r"(?<![\w/])T(?P<serial>\d{4})(?!\w)")
TOPIC_FILE = re.compile(r"^docs/open-topics/(?:archive/)?T(\d{4})-[^/]+\.md$")
EXTENSION = re.compile(r"\.([A-Za-z]\w*)$")
PYTHON, SHELL = {"py"}, {"sh", "bash", "zsh"}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


class Tree:
    """One side a citation may resolve on: the index when `rev` is empty, else a commit or a branch tip; listed only once a message carries a candidate token, and a branch tip only for its topics."""

    def __init__(self, rev: str = "", label: str = "staged") -> None:
        self.rev, self.label = rev, label
        self._paths: list[str] | None = None
        self._topics: set[str] | None = None

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

    def read(self, path: str) -> bytes | None:
        done = subprocess.run(["git", "show", f"{self.rev}:{path}"], capture_output=True)
        return done.stdout if done.returncode == 0 else None

    def ignored(self, path: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", "--", path], capture_output=True).returncode == 0


def clean(raw: str) -> str:
    """A message as git records it: nothing below the scissors line, no comment line."""
    kept: list[str] = []
    for line in raw.split("\n"):
        if line.startswith(SCISSORS):
            break
        if not line.startswith("#"):
            kept.append(line)
    return "\n".join(kept)


def strip(text: str) -> str:
    """The message with fenced blocks, URLs and quoted commands -- a code span with whitespace in it -- taken out."""
    kept: list[str] = []
    fenced = False
    for line in text.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            kept.append(line)
    return COMMAND_SPAN.sub(" ", URL.sub(" ", "\n".join(kept)))


def _line_count(data: bytes) -> int:
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _defines(text: str, ext: str, name: str) -> bool:
    n = re.escape(name)
    if ext in PYTHON:
        pattern = rf"^\s*(?:(?:async\s+)?def|class)\s+{n}\b|^\s*{n}\s*(?::[^=\n]*)?=(?!=)"
    else:
        pattern = rf"^\s*function\s+{n}\b|^\s*{n}\s*\(\)|^\s*(?:export\s+|readonly\s+|local\s+)?{n}="
    return re.search(pattern, text, re.M) is not None


def _resolvable(path: str) -> bool:
    return not path.startswith("/") and ".." not in path.split("/")


def judge(text: str, trees: Sequence[Tree], tips: Sequence[Tree] = ()) -> list[str]:
    """Each citation of the message that resolves on none of `trees` -- the staged tree and HEAD, or a commit and its parent -- once per token, in the message's order; a topic id also stands when a `tips` tree holds its file."""
    body = strip(text)
    if not (LINE.search(body) or SYMBOL.search(body) or TOPIC.search(body)):
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
        if token in seen or ext not in extensions or not _resolvable(path):
            continue
        seen.add(token)
        if files := candidates(token, path):
            wanted = [int(n) for n in re.split(r"[,-]", m.group("lines"))]
            counts = {key: _line_count(data) for key, data in contents(files).items()}
            if not any(all(1 <= n <= c for n in wanted) for c in counts.values()):
                fails.append(f"{token}: " + ", ".join(f"{f} has {c} lines {label}" for (f, label), c in counts.items()))
    for m in SYMBOL.finditer(body):
        token, path, ext = m.group(0), m.group("path").removeprefix("./"), m.group("ext")
        if token in seen or ext not in extensions or ext not in PYTHON | SHELL or not _resolvable(path):
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
        raw = pathlib.Path(argv[1]).read_text()
    except OSError as exc:
        print(f"message-citations: cannot read {argv[1]}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    os.chdir(top.stdout.strip())  # `git check-ignore` reads paths from the working directory; the index and a commit's tree do not
    sides = [Tree()]
    if _git("rev-parse", "--verify", "-q", "HEAD").returncode == 0:
        sides.append(Tree("HEAD", "at HEAD"))
    fails = judge(clean(raw), sides, _tips())
    if fails:
        print("message-citations: refused")
        for fail in fails:
            print("  - " + fail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
