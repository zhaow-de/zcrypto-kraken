"""No test may pull a value out of a hand-edited config file by substring.

Five hand sweeps of this class each missed a live case, and one guard sat blind on the live trade
path -- the path it asserted on appeared in a `fail_msg`, so the prose satisfied the check while the
real lookup pointed elsewhere. Substring containment over a config file's TEXT matches comments,
messages and suffixed values, so it cannot distinguish the setting from prose that mentions it.

Parse the file (`yaml.safe_load`, `json.loads`) or select the assignment by prefix
(`line.strip().startswith(key)`) instead. This test is the guard prose could not be.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
# A hand-edited artifact we do not control the shape of. Fixtures a test writes itself are fair game
# for a substring check -- it knows exactly what it wrote.
_HAZARD = "infra"


def _reads_infra(node: ast.AST, src: str) -> bool:
    seg = ast.get_source_segment(src, node) or ""
    return ".read_text()" in seg and _HAZARD in seg


def _infra_text_vars(tree: ast.Module, src: str) -> set[str]:
    """Names bound to the TEXT of a file under infra/, directly or through a module-level path const."""
    consts = {
        t.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name) and _HAZARD in (ast.get_source_segment(src, n.value) or "")
    }
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


@pytest.mark.parametrize("path", sorted(TESTS.glob("test_*.py")), ids=lambda p: p.name)
def test_no_substring_selector_over_a_hand_edited_config(path: Path) -> None:
    if path.name in _GRANDFATHERED:
        pytest.skip("pre-existing; see _GRANDFATHERED")
    src = path.read_text()
    tree = ast.parse(src)
    haystacks = _infra_text_vars(tree, src)
    bad = [
        f"{path.name}:{n.lineno}  {(ast.get_source_segment(src, n) or '').strip()[:110]}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and len(n.ops) == 1
        and isinstance(n.ops[0], ast.In)
        and isinstance(n.left, ast.Constant | ast.JoinedStr)
        and ((isinstance(n.comparators[0], ast.Name) and n.comparators[0].id in haystacks) or _reads_infra(n.comparators[0], src))
    ]
    assert not bad, "substring selector over a hand-edited config -- parse it, or match by prefix:\n  " + "\n  ".join(bad)
