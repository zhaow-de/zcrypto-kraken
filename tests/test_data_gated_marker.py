"""A test file whose gates skip for want of data carries `pytestmark = pytest.mark.data`.

CI has no `data/` and no NAS mount, so the data-gated family skips there whatever is run; the only
place it runs is a data-bearing workstation, and the pre-push run that reaches it is `uv run pytest
-m data`. That selection is only as good as the marks, and a gate added without one is invisible to
it -- the failure this file exists to make loud, at the moment the gate lands rather than the night
`infra/systemd/zcrypto-data-gated-tests.timer` fires.

The mark is the MODULE's. A per-test mark cannot be checked here without resolving the f-strings
some reasons are built from, the helpers that raise a skip on a caller's behalf, and the fixture
graph that carries one to its consumers -- three refinements that each found gates the last had
missed. A file-level mark needs none of them: a file either holds such a gate or it does not.

The vocabulary is `infra/scripts/data-gated-run.py`'s own `is_data_absence`, imported rather than
restated, so the runner that parses the nightly skips and the guard that marks their sites cannot
drift apart. A gate in a new voice is caught by widening that one regex.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
_RUNNER = ROOT / "infra" / "scripts" / "data-gated-run.py"


def _is_data_absence():
    spec = importlib.util.spec_from_file_location("data_gated_run_under_test", _RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.is_data_absence


def _reason_literal(node: ast.AST) -> str | None:
    """The literal text of a reason argument: a plain string, or an f-string's constant parts.

    An f-string's interpolations are dropped rather than the whole reason: `f"{name} not present on
    this node"` keeps the vocabulary that decides it, and no gate in this tree puts the deciding
    word inside the interpolation.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _gate_reasons(tree: ast.Module) -> list[str]:
    """Every reason a `pytest.skip(...)` or a `skipif(..., reason=...)` in this module gives."""
    out: list[str] = []
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        name = ast.unparse(call.func)
        if not (name.endswith("pytest.skip") or name == "skip" or name.endswith("skipif")):
            continue
        for arg in list(call.args) + [k.value for k in call.keywords if k.arg == "reason"]:
            if (text := _reason_literal(arg)) is not None:
                out.append(text)
    return out


def _module_marks(tree: ast.Module) -> set[str]:
    """The marks a top-level `pytestmark` assigns, whether one mark or a list of them."""
    marks: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
        for v in values:
            text = ast.unparse(v)
            if text.startswith("pytest.mark."):
                marks.add(text.removeprefix("pytest.mark.").split("(")[0])
    return marks


def _files() -> list[Path]:
    return sorted(p for p in TESTS.glob("test_*.py"))


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_a_file_whose_gates_want_data_carries_the_module_mark(path: Path):
    is_data_absence = _is_data_absence()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    gated = [r for r in _gate_reasons(tree) if is_data_absence(r)]
    if not gated:
        return
    assert "data" in _module_marks(tree), (
        f"{path.name} gates on a dataset this machine may not have -- {gated[0]!r} -- but carries no "
        f"`pytestmark = pytest.mark.data`, so `uv run pytest -m data` does not select it and the gate "
        f"runs nowhere: CI skips it for want of data and the marked run never reaches it."
    )


def test_the_marked_set_is_exactly_the_gated_set():
    """The mark is not claimed where no gate wants data: an unearned mark makes the selection wider
    than the family it names, and the next reader cannot tell which files the runner is really for."""
    is_data_absence = _is_data_absence()
    gated, marked = set(), set()
    for path in _files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(is_data_absence(r) for r in _gate_reasons(tree)):
            gated.add(path.name)
        if "data" in _module_marks(tree):
            marked.add(path.name)

    assert marked == gated, f"marked but not gated: {sorted(marked - gated)}; gated but not marked: {sorted(gated - marked)}"


def test_the_guard_reads_the_runners_vocabulary_and_not_a_copy_of_it():
    """The control on both cases above: they are only as good as the imported predicate, so this
    asserts it is the runner's own and that it answers both ways over this tree's real reasons."""
    is_data_absence = _is_data_absence()

    assert is_data_absence("canonical data/ohlc-full absent")
    assert is_data_absence("no refdata snapshot present (gitignored data root)")
    assert is_data_absence("trade archive absent at /srv — data-bearing workstation only")
    assert not is_data_absence("needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it")
    assert not is_data_absence("develop is not a ref in this checkout")
