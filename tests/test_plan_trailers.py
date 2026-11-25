from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys

import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "plan-trailers.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load(_SCRIPT, "plan_trailers")

LITERAL = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PLACEHOLDER = "Co-Authored-By: <actual executing model> <noreply@anthropic.com>"
PLAN_A, PLAN_B, PLAN_C = "docs/plans/00001-a.md", "docs/plans/00002-b.md", "docs/plans/00003-c.md"


def _plan(*lines: str) -> str:
    body = "\n".join(lines)
    return f"# Plan\n\n## Task 1\n\n```bash\ngit commit -F - <<'EOF'\nfeat(x): y\n\n{body}\nEOF\n```\n"


def _line(text: str, line: str) -> int:
    return text.split("\n").index(line) + 1


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _write(repo: pathlib.Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)


def _repo(tmp_path: pathlib.Path, committed: dict[str, str] | None = None) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "guard@test")
    _git(repo, "config", "user.name", "guard")
    _git(repo, "config", "commit.gpgsign", "false")
    _write(repo, {"README.md": "# readme\n", **(committed or {})})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _stage(repo: pathlib.Path, files: dict[str, str]) -> None:
    _write(repo, files)
    _git(repo, "add", "--", *files)


def _run(repo: pathlib.Path, *paths: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(_SCRIPT), *paths], cwd=repo, capture_output=True, text=True)


def _named(proc: subprocess.CompletedProcess[str]) -> list[str]:
    return [line.removeprefix("  - ") for line in proc.stdout.splitlines() if line.startswith("  - ")]


def test_an_added_literal_trailer_is_refused_with_its_file_its_line_and_the_placeholder(tmp_path):
    literals = [
        LITERAL,
        "Co-authored-by: Claude Sonnet 4.5 <noreply@anthropic.com>",
        "   Co-Authored-By: Claude Fable <noreply@anthropic.com>",
        "Co-Authored-By: Claude 3.5 Haiku <noreply@anthropic.com>",
    ]
    text = _plan(*literals)
    repo = _repo(tmp_path)
    _stage(repo, {PLAN_A: text})
    proc = _run(repo, PLAN_A)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout.startswith("plan-trailers: refused\n"), proc.stdout
    assert _named(proc) == [f"{PLAN_A}:{_line(text, line)}: {line.strip()}" for line in literals]
    assert f"`{PLACEHOLDER}`" in proc.stdout


def test_the_placeholder_a_human_and_a_mention_in_prose_are_admitted_silently(tmp_path):
    text = _plan(
        PLACEHOLDER,
        "Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>",
        "Co-Authored-By: Jane Doe <jane@example.com>",
        f"- every commit fence ends with `{LITERAL}`, and an implementer on another model names its own",
        f"> {LITERAL}",
    )
    repo = _repo(tmp_path)
    _stage(repo, {PLAN_A: text})
    proc = _run(repo, PLAN_A)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def test_an_untouched_old_literal_is_admitted(tmp_path):
    old = _plan(LITERAL)
    repo = _repo(tmp_path, {PLAN_A: old})
    _stage(repo, {PLAN_A: old + "\n## Task 2\n\n" + PLACEHOLDER + "\n"})
    proc = _run(repo, PLAN_A)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def test_a_modified_line_that_still_carries_a_literal_is_refused(tmp_path):
    repo = _repo(tmp_path, {PLAN_A: _plan("Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>")})
    text = _plan(LITERAL)
    _stage(repo, {PLAN_A: text})
    proc = _run(repo, PLAN_A)
    assert proc.returncode == 1 and _named(proc) == [f"{PLAN_A}:{_line(text, LITERAL)}: {LITERAL}"], proc.stdout


def test_two_plans_are_each_named_and_a_clean_one_beside_them_is_not(tmp_path):
    first, clean, second = _plan(LITERAL), _plan(PLACEHOLDER), _plan("feat: z", "", LITERAL)
    repo = _repo(tmp_path)
    _stage(repo, {PLAN_A: first, PLAN_B: clean, PLAN_C: second})
    proc = _run(repo, PLAN_A, PLAN_B, PLAN_C)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert _named(proc) == [f"{PLAN_A}:{_line(first, LITERAL)}: {LITERAL}", f"{PLAN_C}:{_line(second, LITERAL)}: {LITERAL}"]


def test_a_non_plan_file_is_ignored_by_the_script_and_by_the_hook(tmp_path):
    others = ["README.md", "docs/specs/00001-x-design.md", "docs/plans/notes.txt", "docs/plans.md", "x/docs/plans/a.md"]
    repo = _repo(tmp_path)
    _stage(repo, dict.fromkeys(others, _plan(LITERAL)))
    proc = _run(repo, *others)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
    files = _hook()["files"]
    assert [p for p in others if re.search(files, p)] == [] and re.search(files, PLAN_A)


def test_the_staged_content_is_judged_not_the_working_tree(tmp_path):
    repo = _repo(tmp_path, {PLAN_A: _plan(PLACEHOLDER)})
    _stage(repo, {PLAN_A: _plan(LITERAL)})
    _write(repo, {PLAN_A: _plan(PLACEHOLDER), PLAN_B: _plan(PLACEHOLDER)})
    _stage(repo, {PLAN_B: _plan(PLACEHOLDER)})
    _write(repo, {PLAN_B: _plan(LITERAL)})
    proc = _run(repo, PLAN_A, PLAN_B)
    assert proc.returncode == 1 and _named(proc) == [f"{PLAN_A}:{_line(_plan(LITERAL), LITERAL)}: {LITERAL}"], proc.stdout


def test_a_plan_outside_the_index_is_refused_not_passed(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, {PLAN_A: _plan(PLACEHOLDER)})
    proc = _run(repo, PLAN_A)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert _named(proc) == [f"{PLAN_A}: not in the index, so its staged content cannot be read: stage it, then run again"]


def test_a_plan_whose_index_cannot_be_read_is_refused_not_passed(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, {PLAN_A: _plan(PLACEHOLDER), PLAN_B: _plan(PLACEHOLDER)})
    (repo / ".git" / "index").write_bytes(b"not an index")
    proc = _run(repo, PLAN_A, PLAN_B)
    assert proc.returncode == 1 and "Traceback" not in proc.stderr, proc.stdout + proc.stderr
    named = _named(proc)
    assert [n.split(": ", 1)[0] for n in named] == [PLAN_A, PLAN_B] and all("cannot read the index" in n for n in named), named


def test_no_plan_named_is_nothing_to_judge(tmp_path):
    proc = subprocess.run([sys.executable, str(_SCRIPT)], cwd=tmp_path, capture_output=True, text=True)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def _hook() -> dict:
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text())
    hooks = [h for repo in config["repos"] if repo["repo"] == "local" for h in repo["hooks"] if h["id"] == "plan-trailers"]
    assert len(hooks) == 1, "one local hook with the id"
    return hooks[0]


def test_the_hook_is_wired_at_the_commit_stage_over_the_plans():
    hook = _hook()
    assert hook["entry"] == "uv run python infra/scripts/plan-trailers.py" and hook["language"] == "system"
    assert hook["files"] == guard.PLAN.pattern
    assert hook.get("stages", ["pre-commit"]) == ["pre-commit"] and hook.get("pass_filenames", True) is True
    assert "always_run" not in hook
