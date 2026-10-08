from __future__ import annotations

import os
import pathlib
import subprocess

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra" / "scripts" / "consumers.sh"
# Assembled so `tests/test_guidance_refs_resolve.py` does not read the fixture's `SKILL.md` path as a citation.
_SKILL_DIR = ".claude" + "/skills/x"


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    for d in ("infra/scripts", "infra/ansible/group_vars/all", "tests", _SKILL_DIR):
        (repo / d).mkdir(parents=True)
    (repo / "infra" / "scripts" / "thing.sh").write_text("#!/bin/sh\necho thing\n")
    (repo / "tests" / "test_thing_sh.py").write_text("SCRIPT = 'infra/scripts/thing.sh'\n")
    (repo / "tests" / "test_other.py").write_text("x = 1\n")
    (repo / "tests" / "test_walker.py").write_text(
        "import pathlib\nROOT = pathlib.Path(__file__).resolve().parents[1]\nFILES = sorted((ROOT / 'tests').rglob('*.py'))\n"
    )
    (repo / "tests" / "test_own_fixture_glob.py").write_text("import pathlib\nFILES = list(pathlib.Path('.').glob('*.txt'))\n")
    (repo / "tests" / "test_lsfiles.py").write_text(
        "import subprocess\nFILES = subprocess.run(['git', 'ls-files', 'infra'], capture_output=True).stdout\n"
    )
    (repo / "tests" / "test_parent_glob.py").write_text(
        'import pathlib\nFILES = sorted(pathlib.Path(__file__).resolve().parent.glob("test_*.py"))\n'
    )
    (repo / "tests" / "test_vault_pass_guard.py").write_text("SCRIPT = 'infra/scripts/thing.sh'\n")
    (repo / "tests" / "test_parent_glob_sq.py").write_text(
        "import pathlib\nFILES = sorted(pathlib.Path(__file__).resolve().parent.glob('test_*.py'))\n"
    )
    (repo / _SKILL_DIR / "SKILL.md").write_text("run infra/scripts/thing.sh first\n")
    (repo / "infra" / "ansible" / "group_vars" / "all" / "vault.yml").write_text("thing.sh: secret\n")
    (repo / "infra" / "scripts" / "lonely.py").write_text("print(1)\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "develop")
    run("config", "user.email", "c@test")
    run("config", "user.name", "c")
    run("add", "-A")
    run("commit", "-qm", "seed")
    return repo


def _run(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(SCRIPT), *args], cwd=repo, capture_output=True, text=True, env={**os.environ})


def test_direct_readers_are_listed_and_the_vault_file_is_not(tmp_path):
    repo = _repo(tmp_path)
    r = _run(repo, "infra/scripts/thing.sh")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert "tests/test_thing_sh.py" in lines
    assert "tests/test_vault_pass_guard.py" in lines  # a reader whose own name carries "vault" is kept
    assert f"{_SKILL_DIR}/SKILL.md" in lines
    assert "tests/test_other.py" not in lines
    assert not any(line.endswith("vault.yml") for line in lines)
    assert "infra/scripts/thing.sh" not in lines[1:]  # the file itself is not its own reader


def test_tree_walkers_follow_and_a_test_globbing_its_own_fixtures_is_not_one(tmp_path):
    repo = _repo(tmp_path)
    r = _run(repo, "infra/scripts/thing.sh")
    walkers = r.stdout.split("# tree walkers", 1)[1].splitlines()[1:]
    assert walkers == ["tests/test_lsfiles.py", "tests/test_parent_glob.py", "tests/test_parent_glob_sq.py", "tests/test_walker.py"]


def test_an_empty_reader_list_is_printed_as_a_finding_never_as_nothing(tmp_path):
    repo = _repo(tmp_path)
    r = _run(repo, "infra/scripts/lonely.py")
    assert r.returncode == 0
    assert "(none -- a finding" in r.stdout and "never the full suite" in r.stdout


def test_no_argument_is_usage(tmp_path):
    repo = _repo(tmp_path)
    r = _run(repo)
    assert r.returncode == 2 and "usage" in r.stderr


def test_the_tree_names_the_script_with_its_walker_tests():
    out = subprocess.run(
        [str(SCRIPT), "infra/scripts/consumers.sh"], cwd=SCRIPT.parents[2], capture_output=True, text=True, check=True
    ).stdout
    for walker in (
        "tests/test_scripts_have_tests.py",
        "tests/test_infra_alloy_series.py",
        "tests/test_internal_terms_not_operator_visible.py",
        "tests/test_guidance_guard.py",
        "tests/test_count_list.py",
        "tests/test_config_selectors_are_parsed.py",
        "tests/test_runbook_internal_tokens.py",
        "tests/test_systemd_user_units.py",
    ):
        assert walker in out.splitlines(), walker
