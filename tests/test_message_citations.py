"""message-citations.py: a commit message whose `path:line`, `path::symbol` / `path:symbol`, `T<NNNN>` or hex id resolves on neither side of the commit is refused, and every shape the hook leaves alone is admitted.

Driven with synthetic messages over a fake tree for the judgement, and over a repository of its own for the git-facing arms: the index against HEAD, a file the commit lands or takes away, an ignored path, a topic at a sibling branch tip, an id in the object store or in a tracked file, the script run from a subdirectory, `--range`, and a message file that is not UTF-8. The wiring test reads the pre-commit config, so the hook cannot fall out of the commit-msg stage unnoticed."""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import subprocess
import sys
from unittest import mock

import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "message-citations.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load(_SCRIPT, "message_citations")


class FakeTree:
    """A side of a commit as a dict of path -> text; `ignored` is a set of paths git would ignore, `objects` the full ids of the object store."""

    def __init__(
        self, files: dict[str, str], label: str = "staged", ignored: set[str] = frozenset(), objects: set[str] = frozenset()
    ) -> None:
        self.files, self.label, self._ignored, self.objects = files, label, set(ignored), set(objects)

    @property
    def paths(self) -> list[str]:
        return sorted(self.files)

    @property
    def topics(self) -> set[str]:
        return {m.group(1) for p in self.files if (m := guard.TOPIC_FILE.match(p))}

    def read(self, path: str) -> bytes | None:
        return self.files[path].encode() if path in self.files else None

    def ignored(self, path: str) -> bool:
        return path in self._ignored

    def has_object(self, hex_id: str) -> bool:
        return any(o.startswith(hex_id) for o in self.objects)

    def carries(self, token: str) -> bool:
        return any(token in text for text in self.files.values())

    @property
    def digests(self) -> set[str]:
        return {hashlib.sha256(text.encode()).hexdigest() for text in self.files.values()}


COMMIT = "40ff64783c3be42bc815804299af06539bee1823"
UPSTREAM = "a52de0f914770b635701ae8961994e0f9b9067db"
SPEC_HASH = "305f6b005cdd25c22a3e3c992364153be25a3adb3d10f44f2db295a4566fcc6a"
RECORD_HASH = "8f5025fd647cbd3982ea7cc2e0cee18eaf837724bd071343da79f9c86ccd44c0"
DEAD40, DEAD64 = "deadbee1" * 5, "deadbee1" * 8
PY = "import os\n\nasync def fetch():\n    pass\n\ndef run():\n    pass\n\nclass Foo:\n    pass\nLIMIT: int = 3\nNAME = 'x'\n"
SH = "c_a() { true; }\nfunction c_b {\n  true\n}\nexport TOKEN=1\n"
FILES = {
    "cli/x.py": PY,
    "tests/test_x.py": "def test_a():\n    pass\n\nclass TestB:\n    def test_c(self):\n        pass\n",
    "infra/scripts/count-list.sh": SH,
    "infra/runbooks/nas.md": "one\ntwo\nthree\n",
    "other/nas.md": "one\n",
    "docs/open-topics/T0001-live.md": "x\n",
    "docs/open-topics/archive/T0002-archived.md": "x\n",
    "README.md": "a\nb",
    "data/.gitignore": "*\n",
    "docs/reference/fleet-pins.md": "| 2026-09-07 19:04:29 | `ac6172b9ffb2` |\n",
    "docs/specs/00100-adapter-design.md": f"upstream pinned at {UPSTREAM}\n",
    "docs/reference/trial-registry.jsonl": f'{{"record_hash":"{RECORD_HASH}","spec_hash":"{SPEC_HASH}"}}\n',
}
TREE = FakeTree(FILES, ignored={"data/x.jsonl", ".local/memo.md"}, objects={COMMIT, "7ae7d1e8" + "0" * 32})


def _judge(message: str, *trees: FakeTree, tips: tuple[FakeTree, ...] = ()) -> list[str]:
    return guard.judge(message, trees or (TREE,), tips)


# --- a dead citation refused, a live one admitted --------------------------------------------


def test_a_dead_path_line_is_refused_and_a_live_one_is_admitted():
    assert _judge("see cli/y.py:3 for the loop\n") == [
        "cli/y.py:3: no tracked file is or ends with cli/y.py, on either side of the commit"
    ]
    assert _judge("see cli/x.py:3 and `tests/test_x.py:1`, README.md:2, T0001 and tests/test_x.py::TestB::test_c\n") == []


def test_a_line_past_the_end_or_zero_is_refused_and_a_range_or_list_is_read_number_by_number():
    n = guard._line_count(PY.encode())
    assert _judge(f"cli/x.py:{n}\n") == []
    assert _judge(f"cli/x.py:{n + 1}\n") == [f"cli/x.py:{n + 1}: cli/x.py has {n} lines staged"]
    assert _judge("cli/x.py:0\n") == [f"cli/x.py:0: cli/x.py has {n} lines staged"]
    assert _judge(f"cli/x.py:3-{n} and cli/x.py:1,{n}\n") == []
    assert _judge(f"cli/x.py:3-{n + 1}\n") == [f"cli/x.py:3-{n + 1}: cli/x.py has {n} lines staged"]
    assert _judge("README.md:2\n") == [], "a last line with no newline is a line"
    assert _judge("README.md:3\n") == ["README.md:3: README.md has 2 lines staged"]


def test_a_suffix_resolves_and_an_ambiguous_one_stands_when_any_candidate_has_the_line():
    assert _judge("nas.md:3 and runbooks/nas.md:2\n") == []
    assert _judge("nas.md:4\n") == ["nas.md:4: infra/runbooks/nas.md has 3 lines staged, other/nas.md has 1 lines staged"]
    assert _judge("unbooks/nas.md:1\n") == [], (
        "a suffix is bounded by a slash, and an unmatched one under no top-level directory is left alone"
    )


def test_an_unmatched_path_is_refused_only_when_it_claims_a_top_level_directory():
    assert _judge("tests/test_gone.py:3\n") == [
        "tests/test_gone.py:3: no tracked file is or ends with tests/test_gone.py, on either side of the commit"
    ]
    assert _judge("cli/engine/executer.py::run\n") == [
        "cli/engine/executer.py::run: no tracked file is or ends with cli/engine/executer.py, on either side of the commit"
    ]
    for shape in ("m.py:1", "probe.sh:2", "polars/series/series.py:925", "apt.py:815", "drafts/cli/x.py:1", "CALIBRATION.md:57"):
        assert _judge(shape + "\n") == [], shape


def test_a_citation_of_the_other_side_of_the_commit_stands():
    """A message describes the move from HEAD to the index: the line a commit takes away, and the file it deletes, resolve at HEAD."""
    head = FakeTree({**FILES, "cli/x.py": PY + "extra\n" * 5, "cli/old.py": "def gone():\n    pass\n"}, label="at HEAD")
    staged = FakeTree({p: t for p, t in FILES.items()})
    n = guard._line_count(PY.encode())
    assert _judge(f"cli/x.py:{n + 5} said so, and cli/old.py:1 with cli/old.py::gone is gone\n", staged, head) == []
    assert _judge(f"cli/x.py:{n + 6}\n", staged, head) == [
        f"cli/x.py:{n + 6}: cli/x.py has {n} lines staged, cli/x.py has {n + 5} lines at HEAD"
    ]
    landed = FakeTree({**FILES, "cli/new.py": "def born():\n    pass\n"})
    assert _judge("cli/new.py:2 and cli/new.py::born\n", landed, FakeTree(FILES, label="at HEAD")) == []


# --- topics ------------------------------------------------------------------------------------


def test_a_dead_topic_is_refused_and_a_live_archived_parent_side_or_branch_tip_one_is_not():
    assert _judge("T0001, T0002 and T0001-T0002\n") == []
    assert _judge("T0003 was never registered\n") == [
        "T0003: no topic file under docs/open-topics/ or its archive, on either side of the commit or at a branch tip"
    ]
    folded = FakeTree({p: t for p, t in FILES.items() if "T0001" not in p})
    assert _judge("fold T0001 away\n", folded, TREE) == [], "the topic the commit deletes is at HEAD"
    tip = FakeTree({"docs/open-topics/T0003-on-a-branch.md": "x\n"}, label="refs/heads/other")
    assert _judge("T0003 is on a sibling branch\n", tips=(tip,)) == []
    assert _judge("T0003 twice, T0003\n") == [
        "T0003: no topic file under docs/open-topics/ or its archive, on either side of the commit or at a branch tip"
    ], "one refusal per token"


# --- symbols -----------------------------------------------------------------------------------


def test_a_dead_symbol_is_refused_and_every_definition_shape_admits_one():
    admitted = (
        "cli/x.py::run, cli/x.py:fetch, cli/x.py:Foo, cli/x.py:LIMIT, cli/x.py:NAME, x.py:Foo.bar, tests/test_x.py::test_a[1-2]"
    )
    assert _judge(admitted + "\n") == []
    assert _judge("count-list.sh:c_a, count-list.sh::c_b, count-list.sh:TOKEN\n") == []
    assert _judge("cli/x.py::nope\n") == ["cli/x.py::nope: no line of cli/x.py defines nope, on either side of the commit"]
    assert _judge("tests/test_x.py::TestB::nope\n") == [
        "tests/test_x.py::TestB::nope: no line of tests/test_x.py defines TestB and nope, on either side of the commit"
    ]
    assert _judge("count-list.sh:c_z\n") == [
        "count-list.sh:c_z: no line of infra/scripts/count-list.sh defines c_z, on either side of the commit"
    ]
    assert _judge("cli/x.py:os\n") == ["cli/x.py:os: no line of cli/x.py defines os, on either side of the commit"], (
        "an import is not a definition"
    )


def test_a_symbol_on_a_file_that_is_not_python_or_shell_and_an_entry_name_are_not_judged():
    assert _judge("README.md:badge and nas.md:Heading and count-list.sh:live-topics-without-a-trigger\n") == []


# --- hex ids -----------------------------------------------------------------------------------


def test_a_dead_hex_id_is_refused_and_one_the_object_store_has_is_admitted():
    assert _judge(f"`{COMMIT[:8]}`, `{COMMIT[:12]}`, `7ae7d1e`, `{COMMIT}` and bare {COMMIT}\n") == []
    assert _judge("`deadbee1` twice, `deadbee1`\n") == [
        "deadbee1: no object has that id, and no tracked file carries it, on either side of the commit"
    ], "one refusal per token"
    assert _judge("`deadbe1`\n") == ["deadbe1: no object has that id, and no tracked file carries it, on either side of the commit"]
    assert _judge(f"{DEAD40} bare and `{DEAD40}` quoted\n") == [
        f"{DEAD40}: no object has that id, and no tracked file carries it, on either side of the commit"
    ]
    dead = f"{DEAD40}: no object has that id, and no tracked file carries it, on either side of the commit"
    for tail in (".", ",", ")", "-", ".)", "'s", " done"):
        assert _judge(f"the upstream commit {DEAD40}{tail}\n") == [dead], f"a 40-hex ending a sentence: {tail!r}"


def test_an_ambiguous_short_id_is_one_the_store_holds():
    """`git cat-file -e` refuses every peel of an ambiguous prefix, so the id resolves by the disambiguation instead."""
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str):
        calls.append(args)
        listed = "1d5ed0c74a\n1d5ed0ca1b\n" if args[-1].endswith("1d5ed0c") else ""
        return subprocess.CompletedProcess(args, 0 if listed else 1, listed, "")

    tree = guard.Tree()
    with mock.patch.object(guard, "_git", fake_git):
        assert tree.has_object("1d5ed0c") is True, "two objects share the prefix, so the store holds it"
        assert tree.has_object("deadbee1") is False
    assert calls == [("rev-parse", "--disambiguate=1d5ed0c"), ("rev-parse", "--disambiguate=deadbee1")]


def test_a_hex_a_tracked_file_carries_stands_on_either_side():
    assert _judge(f"`ac6172b9ffb2`, its prefix `ac6172b9`, and the upstream {UPSTREAM} a spec pins\n") == []
    repinned = FakeTree({p: t for p, t in FILES.items() if p != "docs/reference/fleet-pins.md"})
    assert _judge("`ac6172b9ffb2` goes\n", repinned, TREE) == [], "the digest the commit takes away is at HEAD"
    assert _judge("`ac6172b9ffb2`\n", repinned) == [
        "ac6172b9ffb2: no object has that id, and no tracked file carries it, on either side of the commit"
    ]
    assert _judge("`deadbeef0000`\n") == [
        "deadbeef0000: no object has that id, and no tracked file carries it, on either side of the commit"
    ]


def test_a_quoted_64_hex_is_a_registry_hash_or_a_file_digest_and_a_bare_one_is_left_alone():
    assert _judge(f"`{SPEC_HASH}`, `{RECORD_HASH}` and `{hashlib.sha256(PY.encode()).hexdigest()}`\n") == []
    assert _judge(f"`{DEAD64}`\n") == [f"{DEAD64}: no tracked file carries it or hashes to it, on either side of the commit"]
    assert _judge(f"ast {DEAD64} (unchanged), stmt {DEAD64}, HEAD {DEAD64}\n") == [], "a bare 64-hex is a digest of derived text"
    head = FakeTree({**FILES, "cli/old.py": "def gone():\n    pass\n"}, label="at HEAD")
    assert _judge(f"`{hashlib.sha256(b'def gone():\n    pass\n').hexdigest()}` goes\n", TREE, head) == [], (
        "the digest of the file the commit deletes is at HEAD"
    )


# --- the excluded shapes -----------------------------------------------------------------------


def test_the_excluded_shapes_are_not_citations():
    shapes = {
        "a URL": "https://github.com/x/y/blob/main/cli/z.py:99 and https://x/T0009",
        "a URL with a coordinate in its query": "https://github.com/search?q=cli/x.py:99+T0009 and https://x/s?q=cli/x.py::nope",
        "a fenced block": "before\n```\ncli/x.py:99 T0009 cli/x.py::nope `deadbee1`\n```\nafter",
        "a tilde fence": "~~~bash\ncli/x.py:99\n~~~",
        "an unclosed fence": "```\ncli/x.py:99",
        "a quoted command": "`sed -n '99p' cli/x.py:99` and `git show HEAD:cli/x.py:99` and `git show deadbee1`",
        "a hex in a URL": f"https://github.com/x/y/commit/{DEAD40} and https://x/deadbee1",
        "an unquoted short hex": "deadbee1, ac6172b9ffb2 and deadbee1deadbee1 in prose",
        "a bare 64-hex": f"ast {DEAD64} (unchanged) and sha256:{DEAD64}",
        "a span that is a word or a number": "`deadbeef`, `defaced`, `500000000`, `20260915` and `2147483648`",
        "a sha256-labelled span": "sha256 `9ca1382c84a5`, sha256:`3cc4c1a149df`, sha256: `20ccc4496c9a` and sha256\n`20ccc4496c9b`",
        "a sha256 label spaced or quoted": "sha256  `9ca1382c84a5`, the `sha256` `3cc4c1a149df` and sha256 :\n `20ccc4496c9a`",
        "a 40-hex path segment": f"commit/{DEAD40}, {DEAD40}/x, x-{DEAD40}, {DEAD40}.py, {DEAD40}-slug and v1.{DEAD40}",
        "a span holding more than the id": "`deadbee1..deadbee2`, `deadbee1^` and `deadbee1:cli/x.py`",
        "a hex of another length": f"`abc123`, `deadbee1deadbee1` and `{DEAD40}1`",
        "a host and port": "status.kraken.com:443 and grafana.example.com:3000",
        "a version": "ruff 0.16.0:3 and nautilus 2.x:1 and python3.14:1",
        "an absolute path": "/home/x/cli/x.py:99 and ~/cli/x.py:99 and /cli/x.py:99",
        "a dotdot path": "../cli/x.py:99 and cli/../cli/x.py:99",
        "a branch name": "fix/T0009-slug and docs/t0009-slug and origin/T0009-x",
        "an ignored path": ".local/memo.md:99 and data/x.jsonl:99",
        "a time and a ratio": "12:30 and 1:1 and 2026-09-14T1230",
        "a no-extension path": "Dockerfile:12 and LICENSE:3",
        "a dotfile": ".gitignore:3",
        "a top-level name with a prefix, which claims no top-level directory": "ocli/x.py:99",
    }
    for shape, text in shapes.items():
        assert _judge(text + "\n") == [], shape


def test_a_citation_beside_an_excluded_one_is_still_judged():
    assert _judge("```\ncli/x.py:99\n```\nand cli/x.py:99 outside\n") == [
        f"cli/x.py:99: cli/x.py has {guard._line_count(PY.encode())} lines staged"
    ]
    assert _judge("`cli/x.py:99`\n") == [f"cli/x.py:99: cli/x.py has {guard._line_count(PY.encode())} lines staged"], (
        "a span holding one token is a citation"
    )
    assert _judge("```\n`deadbee1`\n```\nand `deadbee1` outside, sha256 `deadbee1` labelled\n") == [
        "deadbee1: no object has that id, and no tracked file carries it, on either side of the commit"
    ]


def test_a_dead_coordinate_between_two_whitespace_free_spans_is_refused():
    assert _judge("the `--range` flag and cli/gone.py:99 live beside `judge`\n") == [
        "cli/gone.py:99: no tracked file is or ends with cli/gone.py, on either side of the commit"
    ]
    assert _judge("`judge` lists lines, cli/engine/gone.py:3 is dead, and `strip` ends\n") == [
        "cli/engine/gone.py:3: no tracked file is or ends with cli/engine/gone.py, on either side of the commit"
    ]
    # A URL ends at a backtick: a span holding one keeps its closing backtick, so the next span pairs with its own
    assert _judge("see `https://x/y` and cli/gone.py:99 beside `judge`\n") == [
        "cli/gone.py:99: no tracked file is or ends with cli/gone.py, on either side of the commit"
    ]


def test_a_message_with_no_candidate_token_lists_no_tree():
    class Untouchable:
        label = "staged"

        @property
        def paths(self):
            raise AssertionError("listed")

    assert guard.judge("docs: a plain message about nothing\n\nCo-Authored-By: x <x@y.com>\n", [Untouchable()]) == []


def test_comment_lines_and_the_scissors_tail_are_not_judged():
    raw = f"subject\n\n# cli/x.py:99 is a comment\nbody\n{guard.SCISSORS}\ncli/x.py:99 below the scissors\n"
    assert guard.clean(raw) == "subject\n\nbody"


# --- the script, in a repository of its own ----------------------------------------------------


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "guard@test")
    _git(repo, "config", "user.name", "guard")
    _git(repo, "config", "commit.gpgsign", "false")
    for path, text in FILES.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    (repo / ".gitignore").write_text("data/*\n!data/.gitignore\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _run(repo: pathlib.Path, message: str | bytes, *args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    (repo / "MSG").write_bytes(message.encode() if isinstance(message, str) else message)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *(args or (str(repo / "MSG"),))], cwd=cwd or repo, capture_output=True, text=True
    )


def test_the_script_refuses_a_dead_citation_and_admits_a_live_one(tmp_path):
    repo = _repo(tmp_path)
    refused = _run(repo, "fix: see cli/y.py:3\n")
    assert refused.returncode == 1 and refused.stdout.startswith("message-citations: refused\n  - cli/y.py:3: "), (
        refused.stdout + refused.stderr
    )
    assert refused.stdout.endswith(
        "\n  a coordinate or id quoted on purpose goes in a fenced block, or in a code span with a space in it\n"
    )
    passed = _run(repo, "fix: see cli/x.py:3, tests/test_x.py::TestB::test_c and T0002\n")
    assert passed.returncode == 0 and passed.stdout == "", passed.stdout + passed.stderr


def test_the_script_reads_the_index_and_head(tmp_path):
    """A staged new file resolves before it is committed; a file `git rm` takes away still resolves at HEAD; the working tree is not read."""
    repo = _repo(tmp_path)
    (repo / "cli" / "new.py").write_text("def born():\n    pass\n")
    _git(repo, "add", "cli/new.py")
    _git(repo, "rm", "-q", "cli/x.py")
    passed = _run(repo, "feat: cli/new.py:2 lands with cli/new.py::born, cli/x.py:3 and cli/x.py::run go\n")
    assert passed.returncode == 0, passed.stdout + passed.stderr
    (repo / "cli" / "unstaged.py").write_text("x\n")
    refused = _run(repo, "feat: cli/unstaged.py:1\n")
    assert refused.returncode == 1 and "cli/unstaged.py:1: no tracked file" in refused.stdout, refused.stdout + refused.stderr


def test_the_script_resolves_a_hex_id_in_the_object_store_and_in_a_tracked_file(tmp_path):
    """The store holds the repository's own commit; a digest resolves through the pin row a file carries, staged or at HEAD, or by hashing a blob."""
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    tree, blob = (_git(repo, "rev-parse", "--short=8", rev).stdout.strip() for rev in ("HEAD^{tree}", "HEAD:README.md"))
    readme = hashlib.sha256(FILES["README.md"].encode()).hexdigest()
    passed = _run(
        repo,
        f"fix: after `{head[:8]}`, {head}, tree `{tree}` and blob `{blob}`, the pin `ac6172b9ffb2`, `{SPEC_HASH}` and README's `{readme}`\n",
    )
    assert passed.returncode == 0 and passed.stdout == "", passed.stdout + passed.stderr
    refused = _run(repo, f"fix: `deadbee1`, `{DEAD40}` and `{DEAD64}`\n")
    assert refused.returncode == 1 and refused.stdout.count("\n  - ") == 3, refused.stdout + refused.stderr
    assert f"  - {DEAD64}: no tracked file carries it or hashes to it" in refused.stdout
    (repo / "docs" / "reference" / "deploy-log.jsonl").write_text('{"digest":"06998998e876"}\n')
    _git(repo, "add", "docs/reference/deploy-log.jsonl")
    _git(repo, "rm", "-q", "docs/reference/fleet-pins.md")
    passed = _run(repo, "fix: `06998998e876` lands, `ac6172b9ffb2` goes\n")
    assert passed.returncode == 0, passed.stdout + passed.stderr
    (repo / "README.md").write_text("`0badc0de0000`\n")
    refused = _run(repo, "fix: `0badc0de0000`\n")
    assert refused.returncode == 1 and "0badc0de0000: no object" in refused.stdout, "the working tree is not read"


def test_the_range_mode_resolves_an_id_at_the_commit_or_its_parent(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "rm", "-q", "docs/reference/fleet-pins.md")
    _git(repo, "commit", "-q", "-m", f"docs: after `{base[:8]}`, `ac6172b9ffb2` goes")
    assert _run(repo, "", "--range", f"{base}..HEAD").returncode == 0
    _git(repo, "commit", "-q", "--allow-empty", "-m", "docs: `ac6172b9ffb2` is gone and `deadbee1` never was")
    refused = _run(repo, "", "--range", f"{base}..HEAD")
    assert refused.returncode == 1 and refused.stdout.count("\n  - ") == 2, refused.stdout + refused.stderr
    assert ": ac6172b9ffb2: no object has that id" in refused.stdout and ": deadbee1: no object has that id" in refused.stdout


def test_an_ignored_path_is_left_alone(tmp_path):
    repo = _repo(tmp_path)
    assert _run(repo, "docs: data/x.jsonl:99 is the dataset\n").returncode == 0


def test_the_script_run_from_a_subdirectory_reads_the_whole_tree(tmp_path):
    """git lists, names and ignores paths from the working directory; the script moves to the top before it reads."""
    repo = _repo(tmp_path)
    refused = _run(repo, "fix: T0001 and cli/y.py:3\n", cwd=repo / "infra")
    assert refused.returncode == 1 and "cli/y.py:3: no tracked file" in refused.stdout and "T0001" not in refused.stdout, (
        refused.stdout + refused.stderr
    )
    passed = _run(repo, "fix: T0001 and cli/x.py:3\n", cwd=repo / "infra")
    assert passed.returncode == 0, passed.stdout + passed.stderr


def test_a_topic_at_a_sibling_branch_tip_resolves(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "other")
    (repo / "docs" / "open-topics" / "T0003-on-a-branch.md").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs: register T0003")
    _git(repo, "checkout", "-q", "develop")
    assert _run(repo, "fix: T0003 is registered on other\n").returncode == 0
    refused = _run(repo, "fix: T0004 is registered nowhere\n")
    assert refused.returncode == 1 and "T0004: no topic file" in refused.stdout, refused.stdout + refused.stderr


def test_the_range_mode_judges_each_commit_against_its_own_sides_and_skips_merges(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "README.md").write_text("a\nb\nc\n")
    _git(repo, "commit", "-q", "-am", "docs: README.md:3 lands")
    (repo / "README.md").write_text("a\n")
    _git(repo, "commit", "-q", "-am", "docs: README.md:3 goes, README.md:4 never was")
    dead = _git(repo, "rev-parse", "--short=8", "HEAD").stdout.strip()
    refused = _run(repo, "", "--range", f"{base}..HEAD")
    assert refused.returncode == 1 and refused.stdout.count("\n  - ") == 1, refused.stdout + refused.stderr
    assert (
        f"  - {dead} docs: README.md:3 goes, README.md:4 never was: README.md:4: README.md has 1 lines at {dead}, README.md has 3 lines at its parent"
        in refused.stdout
    )
    _git(repo, "commit", "-q", "--amend", "-m", "docs: README.md:3 goes")
    passed = _run(repo, "", "--range", f"{base}..HEAD")
    assert passed.returncode == 0 and "every citation" in passed.stdout, passed.stdout + passed.stderr
    _git(repo, "checkout", "-q", "-b", "side", base)
    (repo / "cli" / "x.py").write_text(PY + "\n")
    _git(repo, "commit", "-q", "-am", "chore: side")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge side: cli/nope.py:1 in a merge message is not judged", "side")
    assert _run(repo, "", "--range", f"{base}..HEAD").returncode == 0
    three_dot = _run(repo, "", "--range", f"{base}...HEAD")
    assert three_dot.returncode == 2 and "usage" in three_dot.stderr


def test_the_script_names_a_message_it_cannot_read_and_exits_2(tmp_path):
    repo = _repo(tmp_path)
    proc = subprocess.run([sys.executable, str(_SCRIPT), "missing"], cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 2 and "cannot read" in proc.stderr and "Traceback" not in proc.stderr
    proc = subprocess.run([sys.executable, str(_SCRIPT)], cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 2 and proc.stderr.startswith("usage:")


def test_a_message_that_is_not_utf8_is_judged_and_not_a_traceback(tmp_path):
    repo = _repo(tmp_path)
    refused = _run(repo, b"fix: caf\xe9 and cli/y.py:3\n")
    assert refused.returncode == 1 and "cli/y.py:3: no tracked file" in refused.stdout, refused.stdout + refused.stderr
    assert "Traceback" not in refused.stderr, refused.stderr
    passed = _run(repo, b"fix: caf\xe9 and cli/x.py:3\n")
    assert passed.returncode == 0 and passed.stdout == "", passed.stdout + passed.stderr
    # The other carrier: under a repo-wide commitEncoding, `git log` prints the recorded bytes untranscoded, and
    # --range reads them through _git
    _git(repo, "config", "i18n.commitEncoding", "ISO-8859-1")
    (repo / "MSG").write_bytes(b"fix: caf\xe9 and cli/y.py:3\n")
    _git(repo, "commit", "-q", "--allow-empty", "-F", "MSG")
    refused = _run(repo, "", "--range", "HEAD~1..HEAD")
    assert refused.returncode == 1 and "cli/y.py:3: no tracked file" in refused.stdout, refused.stdout + refused.stderr
    assert "Traceback" not in refused.stderr, refused.stderr
    (repo / "MSG").write_bytes(b"fix: caf\xe9 and cli/x.py:3\n")
    _git(repo, "commit", "-q", "--amend", "--allow-empty", "-F", "MSG")
    passed = _run(repo, "", "--range", "HEAD~1..HEAD")
    assert passed.returncode == 0 and "every citation" in passed.stdout, passed.stdout + passed.stderr


# --- the wiring --------------------------------------------------------------------------------


def test_the_hook_is_wired_at_the_commit_msg_stage():
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text())
    hooks = [h for repo in config["repos"] if repo["repo"] == "local" for h in repo["hooks"] if h["id"] == "message-citations"]
    assert len(hooks) == 1, "one local hook with the id"
    (hook,) = hooks
    assert hook["stages"] == ["commit-msg"] and hook["always_run"] is True
    assert hook["entry"] == "uv run python infra/scripts/message-citations.py"
