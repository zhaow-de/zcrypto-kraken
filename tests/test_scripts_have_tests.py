"""Every script under `infra/scripts/` and `.claude/skills/*/scripts/` has a test named for it, and that test
says which script it drives: a regular `.py` or `.sh` file `<stem>.<ext>`, at any depth in either tree, is
covered by `tests/test_<stem>.py` or, for a `.sh`, `tests/test_<stem>_sh.py`, with `-` read as `_` because a
`-` is not importable in a module name, and the covering file's text must carry the script's own file name.
The rule keys on the `.py`/`.sh` suffix alone: an extensionless file and the two `.zsh` files -- the operator's
own terminal tooling, a tmux cockpit and a workstation-to-ops transport -- are all out on it. No allowlist -- a
script without a test is named here until it has one."""

from __future__ import annotations

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SUFFIXES = {".py", ".sh"}
# Assembled at run time, so the fixture below never reads as this tree's citation of a guidance script that does
# not exist -- `tests/test_guidance_refs_resolve.py` walks `tests/` for that spelling, and its own literals are
# assembled the same way.
_SKILL_SCRIPT = ".claude" + "/skills/one/scripts/tool.py"
_SKILL_NESTED = _SKILL_SCRIPT.replace("/tool.py", "/deep/tool.py")


def _scripts(root: pathlib.Path) -> list[pathlib.Path]:
    dirs = [root / "infra" / "scripts", *sorted((root / ".claude" / "skills").glob("*/scripts"))]
    return sorted(
        p
        for d in dirs
        if d.is_dir()
        for p in d.rglob("*")
        if p.is_file() and p.suffix in _SUFFIXES and "__pycache__" not in p.parts
    )


def _test_names(script: pathlib.Path) -> list[str]:
    stem = script.stem.replace("-", "_")
    return [f"test_{stem}.py", *([f"test_{stem}_sh.py"] if script.suffix == ".sh" else [])]


def _covers(test: pathlib.Path, script: pathlib.Path) -> bool:
    return test.is_file() and script.name in test.read_text(encoding="utf-8")


def _missing(root: pathlib.Path) -> list[str]:
    return [
        script.relative_to(root).as_posix()
        for script in _scripts(root)
        if not any(_covers(root / "tests" / n, script) for n in _test_names(script))
    ]


def _tree(root: pathlib.Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def test_the_rule_names_the_uncovered_script_and_leaves_the_covered_and_the_zsh_alone(tmp_path):
    _tree(
        tmp_path,
        {
            "infra/scripts/plain-py.py": "",
            "infra/scripts/covered-sh.sh": "",
            "infra/scripts/other-sh.sh": "",
            "infra/scripts/shell.zsh": "",
            _SKILL_SCRIPT: "",
            "tests/test_covered_sh_sh.py": "drives covered-sh.sh",
            "tests/test_other_sh.py": "drives other-sh.sh",
        },
    )
    (tmp_path / "infra" / "scripts" / "a-directory.py").mkdir()
    assert _missing(tmp_path) == [_SKILL_SCRIPT, "infra/scripts/plain-py.py"]


def test_a_test_covers_a_script_only_if_it_names_it(tmp_path):
    _tree(
        tmp_path,
        {
            "infra/scripts/shim-mod.py": "",
            "infra/scripts/shim_mod.py": "",
            "tests/test_shim_mod.py": "drives shim_mod.py",
        },
    )
    assert _missing(tmp_path) == ["infra/scripts/shim-mod.py"]


def test_the_walk_reaches_a_subdirectory_of_either_tree(tmp_path):
    _tree(
        tmp_path,
        {
            "infra/scripts/helpers/nested-uncovered.py": "",
            "infra/scripts/helpers/nested-covered.py": "",
            _SKILL_NESTED: "",
            "tests/test_nested_covered.py": "drives nested-covered.py",
        },
    )
    assert _missing(tmp_path) == [_SKILL_NESTED, "infra/scripts/helpers/nested-uncovered.py"]


def test_the_walk_sees_both_trees():
    scripts = _scripts(_ROOT)
    assert _ROOT / "infra" / "scripts" / "count-list.sh" in scripts
    skills = sorted((_ROOT / ".claude" / "skills").glob("*/scripts"))
    assert skills and all(any(d in p.parents for p in scripts) for d in skills), skills
    assert not any(p.suffix == ".zsh" for p in scripts) and any(p.suffix == ".zsh" for p in (_ROOT / "infra" / "scripts").iterdir())


def test_every_script_has_a_test():
    assert _missing(_ROOT) == []
