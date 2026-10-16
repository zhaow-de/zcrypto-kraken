"""The per-diff tier, read from a tmp repository through the real prove-inert and merge-gate."""

import importlib.util
import pathlib
import subprocess
import sys

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra" / "scripts" / "tier.py"


def _load():
    spec = importlib.util.spec_from_file_location("tier", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tier = _load()

ENGINE = 'def f():\n    """One."""\n    return 1\n'


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: pathlib.Path, files: dict[str, str], message: str) -> None:
    for rel, body in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        _git(repo, "add", rel)
    _git(repo, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    _git(tmp_path, "init", "-q")
    for key, value in (("user.email", "t@t"), ("user.name", "t")):
        _git(tmp_path, "config", key, value)
    _commit(tmp_path, {"README.md": "base\n"}, "base")
    return tmp_path


def _run(repo: pathlib.Path, capsys: pytest.CaptureFixture[str], *args: str) -> list[str]:
    assert tier.main(["tier.py", *args, "--repo", str(repo)]) == 0
    return capsys.readouterr().out.splitlines()


def _change(repo: pathlib.Path, capsys: pytest.CaptureFixture[str], before: dict[str, str], after: dict[str, str]) -> list[str]:
    if before:
        _commit(repo, before, "before")
    _commit(repo, after, "after")
    return _run(repo, capsys, "HEAD~1..HEAD")


def test_a_docs_only_diff_is_none(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _change(repo, capsys, {}, {"docs/reference/a.md": "a\n", "infra/runbooks/b.md": "b\n"}) == ["tier: none"]


def test_a_runbook_beside_a_script_is_light(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _change(repo, capsys, {}, {"infra/runbooks/r.md": "r\n", "infra/scripts/s.py": "X = 1\n"})
    assert out == ["tier: light", "light infra/scripts/s.py"]


def test_a_docstring_only_change_under_cli_engine_is_light(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _change(repo, capsys, {"cli/engine/x.py": ENGINE}, {"cli/engine/x.py": ENGINE.replace("One.", "Two.")})
    assert out == ["tier: light", "light cli/engine/x.py"]


def test_a_comment_only_change_under_cli_engine_is_light(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _change(repo, capsys, {"cli/engine/x.py": ENGINE}, {"cli/engine/x.py": ENGINE + "# a note\n"})
    assert out == ["tier: light", "light cli/engine/x.py"]


def test_a_code_change_under_cli_engine_is_full(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _change(repo, capsys, {"cli/engine/x.py": ENGINE}, {"cli/engine/x.py": ENGINE.replace("return 1", "return 2")})
    assert out == ["tier: full", "full cli/engine/x.py — under cli/engine/; prove-inert exit 1 (CODE CHANGED)"]


def test_a_working_copy_off_head_is_never_proven(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    _commit(repo, {"cli/engine/x.py": ENGINE}, "before")
    _commit(repo, {"cli/engine/x.py": ENGINE.replace("One.", "Two.")}, "after")
    (repo / "cli/engine/x.py").write_text(ENGINE.replace("return 1", "return 2"))
    out = _run(repo, capsys, "HEAD~1..HEAD")
    assert out[0] == "tier: full" and "the working tree differs from HEAD" in out[1], out


@pytest.mark.parametrize(
    ("statement", "module"),
    [("from cli.engine import x", "cli.engine"), ("import cli.engine.x", "cli.engine.x"), ("from cli import engine", "cli.engine")],
)
def test_a_test_importing_cli_engine_is_full(
    repo: pathlib.Path, capsys: pytest.CaptureFixture[str], statement: str, module: str
) -> None:
    before = f"{statement}\n\n\ndef test_x():\n    assert 1 == 1\n"
    out = _change(repo, capsys, {"tests/test_x.py": before}, {"tests/test_x.py": before.replace("1 == 1", "2 == 2")})
    assert out == ["tier: full", f"full tests/test_x.py — a test importing {module}; prove-inert exit 1 (CODE CHANGED)"]


def test_an_alerts_yaml_change_is_full(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    rules = "infra/grafana/alerts.yaml"
    out = _change(repo, capsys, {rules: "groups: []\n"}, {rules: "groups:\n  - name: a\n"})
    assert out[0] == "tier: full" and out[1].startswith(f"full {rules} — under {rules}; prove-inert exit "), out


def test_a_changed_line_naming_the_holdout_is_full(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _change(
        repo, capsys, {"cli/data/paths.py": 'ROOT = "data/ohlc"\n'}, {"cli/data/paths.py": 'ROOT = "data/ohlc-holdout"\n'}
    )
    assert out == ["tier: full", "full cli/data/paths.py — a changed line names ohlc-holdout; prove-inert exit 1 (CODE CHANGED)"]


def test_a_docs_page_naming_the_holdout_stays_none(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _change(repo, capsys, {}, {"docs/research/h.md": "the ohlc-holdout window\n"}) == ["tier: none"]


@pytest.mark.parametrize("argv", [["no-such-rev..HEAD"], ["HEAD~1...HEAD"], [], ["HEAD~1..HEAD", "--paths", "a.py"]])
def test_a_bad_range_or_a_bad_form_is_rc_2(repo: pathlib.Path, argv: list[str]) -> None:
    done = subprocess.run([sys.executable, str(_SCRIPT), *argv, "--repo", str(repo)], capture_output=True, text=True)
    assert done.returncode == 2, done.stdout + done.stderr


def test_a_plan_naming_cli_engine_is_full(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _run(repo, capsys, "--paths", "cli/engine/x.py")
    assert out == ["tier: full", "full cli/engine/x.py — under cli/engine/, read as a non-prose change"]


def test_a_plan_naming_a_script_and_a_docs_page_is_light(repo: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(repo, capsys, "--paths", "infra/scripts/y.py", "docs/z.md") == ["tier: light", "light infra/scripts/y.py"]


def test_a_plan_naming_a_test_is_full_only_when_it_exists_and_imports_one(
    repo: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, {"tests/test_r.py": "from cli.registry import errors\n"}, "test")
    out = _run(repo, capsys, "--paths", "tests/test_r.py", "tests/test_new.py")
    assert out == ["tier: full", "full tests/test_r.py — a test importing cli.registry, read as a non-prose change"]
