"""No test may pull a value out of a hand-edited config file by substring.

Substring containment over a config file's TEXT matches comments, `fail_msg` prose and SUFFIXED
values, so it cannot tell the setting apart from something that merely mentions it.

Parse the file (`yaml.safe_load`, `json.loads`) or select by prefix (`line.strip().startswith(key)`).
Where substring really is the right semantics, declare it: `# config-selector-ok: <why>`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
# A hand-edited artifact we do not control the shape of. Fixtures a test writes itself are fair game
# for a substring check -- it knows exactly what it wrote.
_HAZARD = "infra"
# Declare an exception on the line above the check, or anywhere inside a multi-line one:
# `# config-selector-ok: <why>`.
_MARKER = "config-selector-ok:"


def _path_consts(tree: ast.Module, src: str) -> set[str]:
    """Module-level names whose value names a path under infra/."""
    return {
        t.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name) and _HAZARD in (ast.get_source_segment(src, n.value) or "")
    }


def _reads_infra(node: ast.AST, src: str, consts: set[str]) -> bool:
    """A read of an infra file, whether the path is spelled out or held in a constant."""
    seg = ast.get_source_segment(src, node) or ""
    return ".read_text()" in seg and (_HAZARD in seg or any(c in seg for c in consts))


def _infra_text_vars(tree: ast.Module, src: str) -> set[str]:
    """Names bound to the TEXT of a file under infra/, directly or through a module-level path const."""
    consts = _path_consts(tree, src)
    out: set[str] = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        seg = ast.get_source_segment(src, n.value) or ""
        if ".read_text()" not in seg:
            continue
        if _HAZARD in seg or any(c in seg for c in consts):
            out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return out


# Pre-existing offenders, outside this branch's blast radius. The guard exists to stop the class
# GROWING; retrofitting unrelated suites is a separate change. This list may only ever shrink -- a
# new name here means the guard was defeated rather than satisfied.
_GRANDFATHERED = {"test_config.py", "test_infra_converge_guards.py", "test_panel_regenerate.py"}


def _violations(src: str, name: str = "<src>") -> list[str]:
    """Every substring selector over an infra file's text in `src`."""
    tree = ast.parse(src)
    consts = _path_consts(tree, src)
    haystacks = _infra_text_vars(tree, src)
    src_lines = src.splitlines()
    return [
        f"{name}:{n.lineno}  {(ast.get_source_segment(src, n) or '').strip()[:110]}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and len(n.ops) == 1
        and isinstance(n.ops[0], ast.In)
        and not any(_MARKER in l for l in src_lines[max(0, n.lineno - 2) : (n.end_lineno or n.lineno)])
        and (
            (isinstance(n.comparators[0], ast.Name) and n.comparators[0].id in haystacks)
            or _reads_infra(n.comparators[0], src, consts)
        )
    ]


# Each of these evaded an earlier version of this guard. Proving it on every run is cheaper than
# rediscovering them: a change that stops catching one of these fails HERE, not in six months.
_MUST_CATCH = {
    "const path, inline read": """
ROLE = REPO / "infra/x"
def t():
    assert "a: b" in (ROLE / "tasks/main.yml").read_text()
""",
    "bare name on the left": """
ROLE = REPO / "infra/x"
def t():
    tasks = (ROLE / "m.yml").read_text()
    assert binary in tasks
""",
    "f-string needle": """
def t():
    tasks = (REPO / "infra/m.yml").read_text()
    assert f"dest: {b}" in tasks
""",
}


@pytest.mark.parametrize("label", sorted(_MUST_CATCH), ids=list(sorted(_MUST_CATCH)))
def test_the_guard_catches_each_known_evasion(label: str) -> None:
    assert _violations(_MUST_CATCH[label]), f"the guard no longer catches: {label}"


def test_the_guard_accepts_a_declared_exception() -> None:
    src = """
def t():
    s = (REPO / "infra/m.yml").read_text()
    # config-selector-ok: searching, not selecting
    assert name in s
"""
    assert not _violations(src)


@pytest.mark.parametrize("path", sorted(TESTS.glob("test_*.py")), ids=lambda p: p.name)
def test_no_substring_selector_over_a_hand_edited_config(path: Path) -> None:
    if path.name in _GRANDFATHERED:
        pytest.skip("pre-existing; see _GRANDFATHERED")
    bad = _violations(path.read_text(), path.name)
    assert not bad, "substring selector over a hand-edited config -- parse it, or match by prefix:\n  " + "\n  ".join(bad)
