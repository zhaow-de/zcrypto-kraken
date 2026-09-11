"""Reachability may FAIL a test, never skip it, and one flag name opens every test that reaches a venue.

A test that reaches a live venue is gated on `ZCRYPTO_LIVE_VENUE_TESTS=1`, never on whether the venue
answers. Gated on reachability such a test runs in CI, where it is a flake source, and goes
green-by-skip the day the venue blocks the runner -- and a skip is indistinguishable from a pass in a
summary line, so an outage reads as coverage of a contract nobody exercised. Gated on the flag, the
same outage FAILS: nothing downstream can turn the venue's silence into a skip. That asymmetry is
what the opt-in buys, and it is the whole of the rule.

Two assertions hold it, both keyed on the SHAPE of a gate rather than on a list of flag names, which
would go stale the moment a fourth name is added:

- every skip gate in `tests/` whose condition reads the environment reads `ZCRYPTO_LIVE_VENUE_TESTS`
  and no other name, so a second opt-in cannot appear unnoticed. A gate whose key is computed rather
  than written out is refused too: this file cannot tell what such a gate reads, and a flag it cannot
  read is a flag it cannot hold to one name.
- no skip gate's condition reaches a network call, directly or through a helper defined in its own
  module. The same probe may decide a `pytest.fail` -- `test_engine_node.py` does exactly that -- and
  that permission is the point rather than an exception to it.

The class had three names until T0190: `ZCRYPTO_VENUE_CONTRACT` and `ZCRYPTO_E1B_LIVE` implemented
the same rule under their own spellings, so an agent that set the one name it had been given got the
other two tests silently skipped. The owner ruled one flag for the class on 2026-09-09, the
order-placing probe included, because the finer grain bought nothing a reader could act on.

Out of scope, deliberately: whether a test that reaches a venue is gated at all. No AST says a call
leaves the machine, so an ungated venue test is not findable from here. It is also the loud failure --
it runs, and goes red in CI on the first outage -- rather than the silent one this file exists to keep
out.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"

# The one opt-in, written out here and never learned from the tree: a guard that took the name from
# the files it checks would agree with whatever it found, including a fourth name.
OPT_IN = "ZCRYPTO_LIVE_VENUE_TESTS"

# What a call crosses to leave the machine, named by MODULE rather than by function, so a probe that
# reaches for a different verb on the same library is caught by the same entry.
NETWORK = ("urllib", "socket", "http", "requests", "httpx", "aiohttp", "websockets")


class Gate(NamedTuple):
    """One skip gate: where it is, what environment keys its condition reads, what network it reaches."""

    line: int
    kind: str
    env: tuple[str, ...]
    network: tuple[str, ...]
    condition: str


def _module_strings(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"`, annotated or not, so a gate keyed on a constant resolves to
    the flag it means. A binding this misses is not silently passed: the key reads UNRESOLVED, which
    fails the one-name assertion."""
    out: dict[str, str] = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if isinstance(getattr(node, "value", None), ast.Constant) and isinstance(node.value.value, str):
            out.update({t.id: node.value.value for t in targets if isinstance(t, ast.Name)})
    return out


def _module_functions(tree: ast.Module) -> dict[str, ast.AST]:
    """Every function defined in the module, including methods -- a condition may call either."""
    return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _environment_key(node: ast.AST, strings: dict[str, str]) -> str:
    """The variable name an `os.environ` read asks for. A key this cannot read is returned UNRESOLVED,
    which fails the one-name assertion rather than passing it -- the safe direction for a gate whose
    flag is assembled at run time."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in strings:
        return strings[node.id]
    return f"<unresolved: {ast.unparse(node)}>"


def _reachable_from(condition: ast.AST, functions: dict[str, ast.AST]) -> list[ast.AST]:
    """The condition's own subtree, plus the body of every same-module helper it can reach.

    A call is followed by NAME, so `_probe()` and `self._probe()` are followed alike. That
    over-follows -- a method whose name happens to match a module function is followed too -- and it
    over-follows toward flagging, the direction a guard should err in. BOTH reads below run over
    this, so a gate that puts its `os.environ` read behind a helper is caught by the same following
    that catches a hidden `urllib` call; an asymmetry here would make one read evadable and not the
    other.
    """
    seen: set[str] = set()
    pending, out = [condition], []
    while pending:
        node = pending.pop()
        out.append(node)
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            name = child.func.id if isinstance(child.func, ast.Name) else getattr(child.func, "attr", None)
            if name in functions and name not in seen:
                seen.add(name)
                pending.append(functions[name])
    return out


def _environment_reads(reach: list[ast.AST], strings: dict[str, str]) -> tuple[str, ...]:
    """Every environment key these nodes read -- `os.environ.get(X)`, `os.getenv(X)`, `os.environ[X]`."""
    found: list[str] = []
    for node in [c for n in reach for c in ast.walk(n)]:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("get", "getenv"):
            base = ast.unparse(node.func.value)
            if (base.endswith("environ") or base == "os") and node.args:
                found.append(_environment_key(node.args[0], strings))
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value).endswith("environ"):
            found.append(_environment_key(node.slice, strings))
    return tuple(sorted(set(found)))


def _network_surfaces(reach: list[ast.AST]) -> tuple[str, ...]:
    """The network modules these nodes name, by import or by use. A local `import urllib.request`
    inside a helper counts: that is how the one reachability probe in this tree imports."""
    found: set[str] = set()
    for child in [c for n in reach for c in ast.walk(n)]:
        if isinstance(child, ast.Import):
            found |= {a.name for a in child.names if a.name.split(".")[0] in NETWORK}
        elif isinstance(child, ast.ImportFrom) and child.module and child.module.split(".")[0] in NETWORK:
            found.add(child.module)
        elif isinstance(child, ast.Attribute):
            text = ast.unparse(child)
            if text.split(".")[0] in NETWORK:
                found.add(text)
        elif isinstance(child, ast.Name) and child.id in NETWORK:
            found.add(child.id)
    return tuple(sorted(found))


def _guards_a(statements: list[ast.stmt], attribute: str) -> bool:
    """Whether `pytest.<attribute>()` is called anywhere under these statements -- nesting included, so
    a skip moved inside a `with` or a second `if` is still gated by the condition above it."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
        and ast.unparse(node.func.value).endswith("pytest")
        for statement in statements
        for node in ast.walk(statement)
    )


def _gates(source: str, attribute: str = "skip") -> list[Gate]:
    """Every gate in this module whose condition decides a `pytest.<attribute>()`.

    Two shapes carry a condition: the `skipif` marker, wherever it is written -- as a decorator or in
    a `pytest.param(..., marks=...)` -- and the `if` a `pytest.skip()` sits under.
    """
    tree = ast.parse(source)
    strings, functions = _module_strings(tree), _module_functions(tree)
    out: list[Gate] = []
    for node in ast.walk(tree):
        condition, kind = None, ""
        if attribute == "skip" and isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.skipif"):
            keyword = next((k.value for k in node.keywords if k.arg == "condition"), None)
            condition, kind = (node.args[0] if node.args else keyword), "skipif"
        elif isinstance(node, ast.If) and _guards_a(node.body, attribute):
            condition, kind = node.test, f"if/{attribute}"
        if condition is not None:
            reach = _reachable_from(condition, functions)
            out.append(
                Gate(
                    line=node.lineno,
                    kind=kind,
                    env=_environment_reads(reach, strings),
                    network=_network_surfaces(reach),
                    condition=ast.unparse(condition),
                )
            )
    return out


def _tree_gates(attribute: str = "skip") -> list[tuple[str, Gate]]:
    """Every gate in `tests/`, labelled by file. Asserts the walk saw something: a broken walker must
    fail here rather than pass every assertion below it vacuously."""
    modules = sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)
    assert modules, "walked no test modules -- the glob is broken, not the tree clean"
    out = [(str(p.relative_to(REPO)), gate) for p in modules for gate in _gates(p.read_text(), attribute)]
    assert out, f"walked {len(modules)} test modules and found no {attribute} gate -- the walker is broken"
    return out


def _labelled(gates: list[Gate], label: str) -> list[tuple[str, Gate]]:
    """Gates from one source, tagged for the failure message. A fixture's gates are labelled too, so
    the assertions below run the SAME predicate over the tree and over the shapes that must trip it."""
    return [(label, gate) for gate in gates]


def _second_flags(labelled: list[tuple[str, Gate]]) -> list[tuple[str, Gate, str]]:
    """Every environment key a skip gate reads that is not the one opt-in."""
    return [(label, gate, name) for label, gate in labelled for name in gate.env if name != OPT_IN]


def _reachability_skips(labelled: list[tuple[str, Gate]]) -> list[tuple[str, Gate]]:
    """Every skip gate whose condition can reach a network call."""
    return [(label, gate) for label, gate in labelled if gate.network]


def _tree_gates(attribute: str = "skip") -> list[tuple[str, Gate]]:
    """Every gate in `tests/`, labelled by file. Asserts the walk saw something: a broken walker must
    fail here rather than pass every assertion below it vacuously."""
    modules = sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)
    assert modules, "walked no test modules -- the glob is broken, not the tree clean"
    out = [(str(p.relative_to(REPO)), gate) for p in modules for gate in _gates(p.read_text(), attribute)]
    assert out, f"walked {len(modules)} test modules and found no {attribute} gate -- the walker is broken"
    return out


def test_every_environment_keyed_skip_gate_in_tests_reads_the_one_venue_opt_in():
    """One opt-in for the class: a gate keyed on any other environment name is a second flag, and a
    second flag is how an agent that sets the one it was given gets another test silently skipped."""
    keyed = [(label, gate) for label, gate in _tree_gates() if gate.env]
    assert keyed, "no skip gate in tests/ reads the environment -- the opt-in is gone, or the walker is"
    wrong = _second_flags(keyed)
    assert not wrong, "\n".join(
        f"{label}:{gate.line} [{gate.kind}] gates a skip on {name!r}, not {OPT_IN!r}: {gate.condition}"
        for label, gate, name in wrong
    )


def test_no_skip_gate_in_tests_decides_on_whether_the_venue_answers():
    """The fail-when-set arm, as a property rather than as a call: with the opt-in set, a venue that
    does not answer can only fail a test, because no skip in the tree is reached from a network call."""
    offending = _reachability_skips(_tree_gates())
    assert not offending, "\n".join(
        f"{label}:{gate.line} [{gate.kind}] skips on {list(gate.network)} -- an unreachable venue would "
        f"skip here, and a skip reads as a pass: gate it on {OPT_IN} and let the probe FAIL instead. "
        f"Condition: {gate.condition}"
        for label, gate in offending
    )


def test_the_tree_holds_both_controls_that_keep_the_two_assertions_falsifiable():
    """Both assertions above pass on an empty set. Each needs a live counter-shape in the tree: a skip
    gate with no venue dependency, which must keep passing, and a reachability-keyed `pytest.fail`,
    which is the permitted half of the asymmetry actually being used."""
    plain = [(label, gate) for label, gate in _tree_gates() if not gate.env]
    assert plain, "every skip gate in tests/ reads the environment -- the one-name assertion has no control"
    reachability_fails = [(label, gate) for label, gate in _tree_gates("fail") if gate.network]
    assert reachability_fails, (
        "no `pytest.fail` in tests/ is keyed on reachability -- nothing in the tree exercises the half of "
        f"the rule that MAY read the venue, so {OPT_IN}=1 no longer fails loudly anywhere"
    )


# Every shape the two assertions must catch and every shape they must not, as source rather than as a
# description of source. The walker runs over this exactly as it runs over `tests/`, so a change that
# stops it seeing one of these fails here instead of going quiet over the real tree.
_FIXTURE = """
import os
import pytest
from pathlib import Path

FLAG = "ZCRYPTO_LIVE_VENUE_TESTS"
OTHER = "ZCRYPTO_SOMETHING_ELSE"
ROOT = Path("data")


def _venue_answers():
    import urllib.request

    try:
        with urllib.request.urlopen("https://example.invalid", timeout=1) as answer:
            return answer.status == 200
    except Exception:
        return False


def _opted_in():
    return os.environ.get(OTHER) == "1"


@pytest.mark.skipif(os.environ.get(FLAG) != "1", reason="the one opt-in")
def test_gated_on_the_flag():
    pass


def test_gated_on_a_second_flag_one_call_away_from_the_condition():
    if not _opted_in():
        pytest.skip("the read is in the helper, not in the condition")


@pytest.mark.skipif(os.environ.get(OTHER) != "1", reason="a second flag")
def test_gated_on_a_second_flag():
    pass


@pytest.mark.parametrize("value", [pytest.param(1, marks=pytest.mark.skipif(os.environ.get(OTHER) != "1", reason="in marks="))])
def test_gated_on_a_second_flag_through_marks(value):
    pass


@pytest.mark.skipif(condition=os.environ["ZCRYPTO_" + "COMPUTED"] != "1", reason="assembled at run time")
def test_gated_on_a_computed_key():
    pass


@pytest.mark.skipif(not ROOT.exists(), reason="no dataset on this workstation")
def test_gated_on_a_local_dataset():
    pass


def test_skips_through_a_reachability_helper():
    if not _venue_answers():
        pytest.skip("the venue is down")


def test_skips_on_a_reachability_read_written_inline():
    import urllib.request

    if urllib.request.urlopen("https://example.invalid").status != 200:
        pytest.skip("the venue is down")


def test_skips_below_the_condition_rather_than_directly_under_it():
    if not _venue_answers():
        with open("/dev/null"):
            pytest.skip("still gated on reachability")


def test_fails_rather_than_skips_when_the_opt_in_is_set():
    if os.environ.get(FLAG) != "1":
        pytest.skip("needs a live venue")
    if not _venue_answers():
        pytest.fail("the opt-in was set but the venue is unreachable")
"""


def test_a_second_opt_in_name_is_caught_wherever_the_condition_is_written():
    """Four places carry one: the `skipif` decorator, its `condition=` keyword, a `marks=` entry inside
    `parametrize`, and a helper the condition calls -- the last because the read that matters can sit
    one call away, exactly as a reachability probe does. A key assembled at run time is refused rather
    than read: this file cannot tell what it says, and a name it cannot read is one it cannot hold."""
    offenders = _second_flags(_labelled(_gates(_FIXTURE), "fixture"))
    caught = {name for _, _, name in offenders}
    assert sum(name == "ZCRYPTO_SOMETHING_ELSE" for _, _, name in offenders) == 3, (
        f"the decorator, the `marks=` and the behind-a-helper spellings must all be caught, got {offenders}"
    )
    assert any(name.startswith("<unresolved") for name in caught), f"a computed key must be refused, got {caught}"
    assert OPT_IN not in caught, "the one opt-in must not be reported as a second flag"


def test_a_reachability_keyed_skip_is_caught_inline_through_a_helper_and_below_a_nesting():
    """The three ways a skip can end up deciding on the venue. The helper case is the one that matters:
    it is the shape `test_engine_node.py` uses, where the network call is a `urllib` import one call
    away from the condition and invisible to any read of the condition alone."""
    caught = _reachability_skips(_labelled(_gates(_FIXTURE), "fixture"))
    assert len(caught) == 3, f"expected the inline, helper and nested skips, got {[g.condition for _, g in caught]}"
    assert {g.condition for _, g in caught} == {
        "not _venue_answers()",
        "urllib.request.urlopen('https://example.invalid').status != 200",
    }


def test_a_gate_with_no_venue_dependency_passes_beside_them():
    """The degeneracy control. A guard that flagged every skip would pass its own fixture and refuse
    the dataset gates that are most of `tests/` -- an absent dataset is not an outage read as coverage."""
    dataset = [gate for gate in _gates(_FIXTURE) if "ROOT.exists" in gate.condition]
    assert len(dataset) == 1, f"the fixture's one dataset gate must be seen, got {dataset}"
    assert dataset[0].env == () and dataset[0].network == (), f"a dataset gate is neither, got {dataset[0]}"


def test_a_reachability_keyed_fail_is_not_a_skip_gate():
    """The permitted half, and the reason the rule is worth following: reading the venue to FAIL is
    what makes the opt-in mean something. The skip walk must not see it; the fail walk must."""
    assert not [g for g in _gates(_FIXTURE) if "the opt-in was set" in g.condition], "a `pytest.fail` is not a skip gate"
    fails = [gate for gate in _gates(_FIXTURE, "fail") if gate.network]
    assert [gate.condition for gate in fails] == ["not _venue_answers()"], f"the fail arm must be seen, got {fails}"
