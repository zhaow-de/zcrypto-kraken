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
    # A loop variable over `<haystack>.splitlines()` IS the haystack, one line at a time. Without
    # this, `any("x" in line for line in text.splitlines())` slips through -- and that is precisely
    # the form someone reaches for to satisfy this guard.
    for n in ast.walk(tree):
        for gen in getattr(n, "generators", []):
            it = ast.get_source_segment(src, gen.iter) or ""
            if ".splitlines()" in it and any(h in it for h in out):
                out |= {t.id for t in ast.walk(gen.target) if isinstance(t, ast.Name)}
    return out


# Pre-existing offenders, outside this branch's blast radius. The guard exists to stop the class
# GROWING; retrofitting unrelated suites is a separate change. This list may only ever shrink -- a
# new name here means the guard was defeated rather than satisfied.
_GRANDFATHERED = {"test_infra_converge_guards.py", "test_panel_regenerate.py"}


def _root_name(node: ast.AST) -> str | None:
    """The base identifier of an expression: `ln.strip()` and `ln` both root at `ln`."""
    while isinstance(node, ast.Call | ast.Attribute):
        node = (
            node.func.value if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else getattr(node, "value", None)
        )
        if node is None:
            return None
    return node.id if isinstance(node, ast.Name) else None


def _prefix_anchored(tree: ast.Module, src: str) -> set[int]:
    """Compare nodes sitting beside a `.startswith(...)` on the same name.

    `startswith("regex") and "node_load1" in ln` is safe: the prefix already excludes comments, and
    the substring only says WHICH anchored line. Flagging it would push editors toward suppressions.
    """
    safe: set[int] = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.BoolOp):
            continue
        names = {
            root
            for v in n.values
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "startswith"
            for root in (_root_name(v.func.value),)
            if root
        }
        if not names:
            continue
        for v in n.values:
            if isinstance(v, ast.Compare) and _root_name(v.comparators[0]) in names:
                safe.add(id(v))
    return safe


def _violations(src: str, name: str = "<src>") -> list[str]:
    """Every substring selector over an infra file's text in `src`."""
    tree = ast.parse(src)
    consts = _path_consts(tree, src)
    haystacks = _infra_text_vars(tree, src)
    src_lines = src.splitlines()
    anchored = _prefix_anchored(tree, src)
    return [
        f"{name}:{n.lineno}  {(ast.get_source_segment(src, n) or '').strip()[:110]}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and len(n.ops) == 1
        and isinstance(n.ops[0], ast.In)
        and id(n) not in anchored
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
    "in inside a comprehension over splitlines": """
def t():
    unit = (REPO / "infra/u.service").read_text()
    assert any("ProtectSystem=strict" in l for l in unit.splitlines())
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
