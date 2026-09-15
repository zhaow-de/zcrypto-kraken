"""message-citations.py: a commit message whose `path:line`, `path::symbol` / `path:symbol` or `T<NNNN>` resolves on neither side of the commit is refused, and every shape the hook leaves alone is admitted.

Driven with synthetic messages over a fake tree for the judgement, and over a repository of its own for the git-facing arms: the index against HEAD, a file the commit lands or takes away, an ignored path, a topic at a sibling branch tip, the script run from a subdirectory, and `--range`. The wiring test reads the pre-commit config, so the hook cannot fall out of the commit-msg stage unnoticed."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

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
    """A side of a commit as a dict of path -> text; `ignored` is a set of paths git would ignore."""

    def __init__(self, files: dict[str, str], label: str = "staged", ignored: set[str] = frozenset()) -> None:
        self.files, self.label, self._ignored = files, label, set(ignored)

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
}
TREE = FakeTree(FILES, ignored={"data/x.jsonl", ".local/memo.md"})


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


# --- the excluded shapes -----------------------------------------------------------------------


def test_the_excluded_shapes_are_not_citations():
    shapes = {
        "a URL": "https://github.com/x/y/blob/main/cli/z.py:99 and https://x/T0009",
        "a URL with a coordinate in its query": "https://github.com/search?q=cli/x.py:99+T0009 and https://x/s?q=cli/x.py::nope",
        "a fenced block": "before\n```\ncli/x.py:99 T0009 cli/x.py::nope\n```\nafter",
        "a tilde fence": "~~~bash\ncli/x.py:99\n~~~",
        "an unclosed fence": "```\ncli/x.py:99",
        "a quoted command": "`sed -n '99p' cli/x.py:99` and `git show HEAD:cli/x.py:99`",
        "a host and port": "status.kraken.com:443 and grafana.example.com:3000",
        "a version": "ruff 0.16.0:3 and nautilus 2.x:1 and python3.14:1",
        "an absolute path": "/home/x/cli/x.py:99 and ~/cli/x.py:99 and /cli/x.py:99",
        "a dotdot path": "../cli/x.py:99 and cli/../cli/x.py:99",
        "a branch name": "fix/T0009-slug and docs/t0009-slug and origin/T0009-x",
        "an ignored path": ".local/memo.md:99 and data/x.jsonl:99",
        "a time and a ratio": "12:30 and 1:1 and 2026-09-14T1230",
        "a no-extension path": "Dockerfile:12 and LICENSE:3",
        "a dotfile": ".gitignore:3",
        "a suffix in a word": "ocli/x.py:99",
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


def test_a_message_with_no_candidate_token_lists_no_tree():
    class Untouchable:
        label = "staged"

        @property
        def paths(self):
            raise AssertionError("listed")

    assert guard.judge("docs: a plain message about nothing\n\nCo-Authored-By: x <x@y.com>\n", [Untouchable()]) == []


def test_the_message_is_read_as_git_records_it():
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


def _run(repo: pathlib.Path, message: str, *args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    (repo / "MSG").write_text(message)
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
        "\n  a coordinate quoted on purpose goes in a fenced block, or in a code span with a space in it\n"
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


# --- the wiring --------------------------------------------------------------------------------


def test_the_hook_is_wired_at_the_commit_msg_stage():
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text())
    hooks = [h for repo in config["repos"] if repo["repo"] == "local" for h in repo["hooks"] if h["id"] == "message-citations"]
    assert len(hooks) == 1, "one local hook with the id"
    (hook,) = hooks
    assert hook["stages"] == ["commit-msg"] and hook["always_run"] is True
    assert hook["entry"] == "uv run python infra/scripts/message-citations.py"
