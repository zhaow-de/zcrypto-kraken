"""Every script under `infra/scripts/` and `.claude/skills/*/scripts/` has a test named for it: a regular `.py` or
`.sh` file `<stem>.<ext>` is covered by `tests/test_<stem>.py` or, for a `.sh`, `tests/test_<stem>_sh.py`, with `-`
read as `_`. The `.zsh` files are out: they are the operator's own terminal tooling -- a tmux cockpit and a
workstation-to-ops transport -- and nothing but the suffix excludes them. No allowlist -- a script without a test is
named here until it has one."""

from __future__ import annotations

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SUFFIXES = {".py", ".sh"}
# Assembled at run time, so the fixture below never reads as this tree's citation of a guidance script that does
# not exist -- `tests/test_guidance_refs_resolve.py` walks `tests/` for that spelling, and its own literals are
# assembled the same way.
_SKILL_SCRIPT = ".claude" + "/skills/one/scripts/tool.py"


def _scripts(root: pathlib.Path) -> list[pathlib.Path]:
    dirs = [root / "infra" / "scripts", *sorted((root / ".claude" / "skills").glob("*/scripts"))]
    return sorted(p for d in dirs if d.is_dir() for p in d.iterdir() if p.is_file() and p.suffix in _SUFFIXES)


def _test_names(script: pathlib.Path) -> list[str]:
    stem = script.stem.replace("-", "_")
    return [f"test_{stem}.py", *([f"test_{stem}_sh.py"] if script.suffix == ".sh" else [])]


def _missing(root: pathlib.Path) -> list[str]:
    return [
        script.relative_to(root).as_posix()
        for script in _scripts(root)
        if not any((root / "tests" / n).is_file() for n in _test_names(script))
    ]


def test_the_rule_names_the_uncovered_script_and_leaves_the_covered_and_the_zsh_alone(tmp_path):
    for rel in (
        "infra/scripts/plain-py.py",
        "infra/scripts/covered-sh.sh",
        "infra/scripts/other-sh.sh",
        "infra/scripts/shell.zsh",
        _SKILL_SCRIPT,
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    (tmp_path / "infra" / "scripts" / "a-directory.py").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("test_covered_sh_sh.py", "test_other_sh.py", "test_shell.py"):
        (tmp_path / "tests" / name).write_text("", encoding="utf-8")
    assert _missing(tmp_path) == [_SKILL_SCRIPT, "infra/scripts/plain-py.py"]


def test_the_walk_sees_both_trees():
    scripts = _scripts(_ROOT)
    assert _ROOT / "infra" / "scripts" / "count-list.sh" in scripts
    assert any(".claude" in p.parts for p in scripts)
    assert not any(p.suffix == ".zsh" for p in scripts) and any(p.suffix == ".zsh" for p in (_ROOT / "infra" / "scripts").iterdir())


def test_every_script_has_a_test():
    assert _missing(_ROOT) == []
