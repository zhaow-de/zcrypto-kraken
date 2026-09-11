"""Reachability may FAIL a test, never skip it, and one flag name opens every test that reaches a venue.

A test that reaches a live venue is gated on `ZCRYPTO_LIVE_VENUE_TESTS=1`, never on whether the venue
answers. Gated on reachability such a test runs in CI, where it is a flake source, and goes
green-by-skip the day the venue blocks the runner -- and a skip is indistinguishable from a pass in a
summary line, so an outage reads as coverage of a contract nobody exercised. Gated on the flag, the
same outage FAILS: nothing downstream can turn the venue's silence into a skip. That asymmetry is
what the opt-in buys, and it is the whole of the rule.

Three assertions hold it, all keyed on the SHAPE of a gate rather than on a list of flag names, which
would go stale the moment a fourth is added:

- every skip gate in `tests/` whose guards read the environment read `ZCRYPTO_LIVE_VENUE_TESTS` and no
  other name, so a second opt-in cannot appear unnoticed;
- no skip gate's guards reach a network client library, directly or through a helper this file can
  read. The same probe may decide a `pytest.fail` -- `test_engine_node.py` does exactly that -- and
  that permission is the point rather than an exception to it;
- no skip gate is decided by something this file cannot read. A flag name assembled at run time, and
  a call to a function that is neither in the gate's own module nor in a module under `tests/`, both
  fail the guard rather than passing it. A gate it cannot judge is a gate it refuses, because the two
  assertions above are only worth their names over gates whose guards were actually read.

A GUARD here is any expression that decides whether a `pytest.skip()` is reached: a `skipif`
condition, the test of every enclosing `if` whether the skip sits in the body or the `else`, and the
BODY of an enclosing `try` when the skip sits in its handler -- `try: urlopen(...) except:
pytest.skip(...)` is the reachability skip in its commonest form, and it has no condition at all.

The class had three names until T0190: `ZCRYPTO_VENUE_CONTRACT` and `ZCRYPTO_E1B_LIVE` implemented the
same rule under their own spellings, so an agent that set the one name it had been given got the other
two tests silently skipped. The owner ruled one flag for the class on 2026-09-09, the order-placing
probe included, because the finer grain bought nothing a reader could act on.

Out of scope, deliberately and in both directions. Whether a test that reaches a venue is gated AT
ALL: no AST says a call leaves the machine, so an ungated venue test is not findable from here -- it
is also the loud failure, running red in CI on the first outage, rather than the silent one this file
exists to keep out. And WHICH calls reach the network: `NETWORK` names client libraries, so a probe
built on `subprocess` and a command-line tool, or on the project's own venue client, is not recognised
as one. What catches those is the third assertion, if and only if the probe sits behind a name this
file cannot read; a reachability probe written inline with `subprocess` in a skip's guard passes all
three. That is the guard's floor, not a claim about its ceiling.
"""

from __future__ import annotations

import ast
import builtins
import functools
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"

# The one opt-in, written out here and never learned from the tree: a guard that took the name from
# the files it checks would agree with whatever it found, including a fourth name.
OPT_IN = "ZCRYPTO_LIVE_VENUE_TESTS"

# Client libraries that speak to something off this machine, named by MODULE rather than by function,
# so a probe reaching for a different verb on the same library is caught by the same entry. What this
# tuple cannot name is a probe that shells out or uses our own adapter; the docstring says so, and the
# opaque assertion is what covers those when they sit behind a helper.
NETWORK = ("urllib", "socket", "http", "requests", "httpx", "aiohttp", "websockets", "asyncio.open_connection")


class Gate(NamedTuple):
    """One skip site: where it is, and what its guards read, reach and could not be read at all."""

    line: int
    kind: str
    env: tuple[str, ...]
    network: tuple[str, ...]
    opaque: tuple[str, ...]
    guards: str


class Module(NamedTuple):
    """A parsed module and the three lookups a guard is read against."""

    tree: ast.Module
    strings: dict[str, str]
    functions: dict[str, ast.AST]
    imported: dict[str, str]  # a name bound by import -> the tests/ module it came from, or ""
    label: str


def _module_strings(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"`, annotated or not, so a gate keyed on a constant resolves to the
    flag it means. A binding this misses reads UNRESOLVED, which fails the one-name assertion."""
    out: dict[str, str] = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if isinstance(getattr(node, "value", None), ast.Constant) and isinstance(node.value.value, str):
            out.update({t.id: node.value.value for t in targets if isinstance(t, ast.Name)})
    return out


def _module_functions(tree: ast.Module) -> dict[str, ast.AST]:
    """Every function and method defined in the module, by bare name -- a guard may call either."""
    return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _imported(tree: ast.Module) -> dict[str, str]:
    """Each name bound by an import, mapped to the module it came from.

    The distinction that matters downstream is not whether the module resolves but whose it is. A name
    from a library is not opaque -- reading `pathlib` is not this file's business -- while a name from
    a module under `tests/` is a test helper, and one of those that cannot be read is precisely the
    case that let a gate's whole decision sit somewhere nothing checked it.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.update({(a.asname or a.name): node.module for a in node.names})
        elif isinstance(node, ast.Import):
            out.update({(a.asname or a.name.split(".")[0]): a.name for a in node.names})
    return out


# Where this repo's own code lives. A helper in any of these can decide a skip and is followed; a
# library outside them is not this file's business to read and is exempt rather than opaque.
OURS = ("tests", "cli", "infra")


def _is_local_module(dotted: str) -> bool:
    """Whether an import names this repo's own code rather than a library."""
    return dotted.split(".")[0] in OURS or (TESTS / f"{dotted.split('.')[-1]}.py").is_file()


def _module_path(dotted: str) -> Path | None:
    """The file an import of our own code names, when there is one. A dotted path is tried whole, and
    a bare name is tried beside the importer, which is how this suite spells its helper imports."""
    for candidate in (REPO / (dotted.replace(".", "/") + ".py"), TESTS / f"{dotted.split('.')[-1]}.py"):
        if candidate.is_file():
            return candidate
    return None


@functools.cache
def _module(path: Path) -> Module:
    """A `tests/` module, parsed once. Cached because one helper module is imported by several."""
    return _module_of(path.read_text(), str(path.relative_to(REPO)))


def _module_of(source: str, label: str) -> Module:
    tree = ast.parse(source, label)
    return Module(tree, _module_strings(tree), _module_functions(tree), _imported(tree), label)


def _sibling(module: Module, name: str) -> ast.AST | None:
    """The function `name` refers to in a module under `tests/`, when it was imported from one and that
    module can be read. A local import that cannot be read returns None and falls to opaque."""
    dotted = module.imported.get(name)
    if not dotted or not _is_local_module(dotted):
        return None
    path = _module_path(dotted)
    return _module(path).functions.get(name) if path is not None else None


def _reachable_from(guards: list[ast.AST], module: Module) -> tuple[list[ast.AST], tuple[str, ...]]:
    """Every guard's own subtree, plus the body of each function it can reach, and the names it cannot.

    A bare name is resolved against the module's own functions first and a `tests/` module it was
    imported from second; `self._probe()` and `cls._probe()` resolve against the module's functions
    too. Anything else callable by a bare name that this file cannot read is returned OPAQUE rather
    than passed over -- it was reaching an unreadable name that let the first shape of this file call
    a gate clean when its whole decision lived one module away. An attribute call on anything but
    `self`/`cls` is NOT followed by its bare attribute name: doing that made every `os.environ.get(...)`
    guard walk into any module-level function happening to be called `get`, which turned correct
    gates red.
    """
    seen: set[str] = set()
    opaque: set[str] = set()
    pending, out = list(guards), []
    while pending:
        node = pending.pop()
        out.append(node)
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if isinstance(child.func, ast.Name):
                name = child.func.id
            elif isinstance(child.func, ast.Attribute) and ast.unparse(child.func.value) in ("self", "cls"):
                name = child.func.attr
            else:
                continue  # a library call reached through its module: not ours to read
            if name in seen:
                continue
            seen.add(name)
            body = module.functions.get(name) or _sibling(module, name)
            if body is not None:
                pending.append(body)
                continue
            origin = module.imported.get(name)
            if origin is None:
                if name not in dir(builtins):
                    opaque.add(name)  # bound by nothing this file can see
            elif _is_local_module(origin):
                opaque.add(name)  # a test helper whose module would not read
    return out, tuple(sorted(opaque))


def _environment_reads(reach: list[ast.AST], strings: dict[str, str]) -> tuple[str, ...]:
    """Every environment key these nodes read, in all four spellings the language offers: `.get`, a
    bare `getenv` bound by `from os import getenv`, a subscript, and a membership test. The first
    shape of this file knew the first and third, and a gate spelled either of the other two read the
    environment while being counted as reading nothing."""
    found: list[str] = []
    for node in [c for n in reach for c in ast.walk(n)]:
        if isinstance(node, ast.Call) and node.args:
            func = node.func
            attr = (
                isinstance(func, ast.Attribute)
                and func.attr in ("get", "getenv")
                and (ast.unparse(func.value).endswith("environ") or ast.unparse(func.value) == "os")
            )
            if attr or (isinstance(func, ast.Name) and func.id == "getenv"):
                found.append(_environment_key(node.args[0], strings))
        elif isinstance(node, ast.Subscript) and _is_environ(node.value):
            found.append(_environment_key(node.slice, strings))
        elif isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)) and _is_environ(comparator):
                    found.append(_environment_key(node.left, strings))
    return tuple(sorted(set(found)))


def _is_environ(node: ast.AST) -> bool:
    """`os.environ` or a bare `environ`, and not `payload['environment']`, whose text merely starts the
    same way -- the loose spelling of this check matched that line the first time it was written."""
    return ast.unparse(node) in ("os.environ", "environ")


def _environment_key(node: ast.AST, strings: dict[str, str]) -> str:
    """The variable name an environment read asks for. A key this cannot read is returned UNRESOLVED,
    which fails the one-name assertion rather than passing it -- the safe direction for a gate whose
    flag is assembled at run time."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in strings:
        return strings[node.id]
    return f"<unresolved: {ast.unparse(node)}>"


def _network_surfaces(reach: list[ast.AST]) -> tuple[str, ...]:
    """The network client libraries these nodes name, by import or by use. A local `import
    urllib.request` inside a helper counts: that is how the one reachability probe in this tree
    imports."""
    found: set[str] = set()
    for child in [c for n in reach for c in ast.walk(n)]:
        if isinstance(child, ast.Import):
            found |= {a.name for a in child.names if _is_network(a.name)}
        elif isinstance(child, ast.ImportFrom) and child.module and _is_network(child.module):
            found.add(child.module)
        elif isinstance(child, ast.Attribute) and _is_network(ast.unparse(child)):
            found.add(ast.unparse(child))
        elif isinstance(child, ast.Name) and child.id in NETWORK:
            found.add(child.id)
    return tuple(sorted(found))


def _is_network(text: str) -> bool:
    """A dotted name is a network surface when its first segment is one, or when it IS one -- the
    `asyncio.open_connection` entry names a verb because `asyncio` alone is not a network library."""
    return text.split(".")[0] in NETWORK or any(text == n or text.startswith(n + ".") for n in NETWORK)


def _parents(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    """Each node's parent, so a skip site can be walked back up to everything that decides it."""
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _guards_of(call: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.AST]:
    """Every expression deciding whether this call is reached, up to its function boundary.

    An `if` decides its `else` exactly as much as its body, and a `try` decides its handlers through
    what its BODY does -- `try: urlopen(...) except OSError: pytest.skip(...)` has no condition
    anywhere, and reading conditions alone is how the first shape of this file saw no gate there.
    """
    guards: list[ast.AST] = []
    current = call
    while current in parents:
        up = parents[current]
        if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            break
        if isinstance(up, (ast.If, ast.While)) and (current in up.body or current in getattr(up, "orelse", [])):
            guards.append(up.test)
        elif isinstance(up, ast.Try) and current not in up.body:
            guards.extend(up.body)
        current = up
    return guards


def _as_expression(node: ast.AST) -> tuple[ast.AST, tuple[str, ...]]:
    """A `skipif` condition, with pytest's string spelling parsed rather than passed over. A string
    that will not parse is opaque: pytest would evaluate it and this file cannot."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return ast.parse(node.value, mode="eval").body, ()
        except SyntaxError:
            return node, (f"<unparsable condition: {node.value[:40]}>",)
    return node, ()


def _gate(line: int, kind: str, guards: list[ast.AST], module: Module, extra: tuple[str, ...] = ()) -> Gate:
    reach, opaque = _reachable_from(guards, module)
    return Gate(
        line=line,
        kind=kind,
        env=_environment_reads(reach, module.strings),
        network=_network_surfaces(reach),
        opaque=tuple(sorted(set(opaque) | set(extra))),
        guards=" ; ".join(ast.unparse(g) for g in guards)[:300],
    )


def _gates(source: str, label: str = "<fixture>", attribute: str = "skip", path: Path | None = None) -> list[Gate]:
    """Every gate in this module whose guards decide a `pytest.<attribute>()`.

    Two shapes reach a skip: the `skipif` marker, wherever it is written -- a decorator, a
    `condition=` keyword, or a `pytest.param(..., marks=...)` entry -- and a `pytest.skip()` call,
    whose guards are read off the statements enclosing it rather than off any one condition.
    """
    module = _module(path) if path is not None else _module_of(source, label)
    parents = _parents(module.tree)
    out: list[Gate] = []
    for node in ast.walk(module.tree):
        if attribute == "skip" and isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.skipif"):
            raw = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "condition"), None)
            if raw is not None:
                condition, extra = _as_expression(raw)
                out.append(_gate(node.lineno, "skipif", [condition], module, extra))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attribute
            and ast.unparse(node.func.value).endswith("pytest")
        ):
            guards = _guards_of(node, parents)
            if guards:
                out.append(_gate(node.lineno, f"{attribute}-site", guards, module))
    return out


def _labelled(gates: list[Gate], label: str) -> list[tuple[str, Gate]]:
    """Gates from one source, tagged for the failure message. A fixture's gates are labelled too, so
    the assertions below run the SAME predicate over the tree and over the shapes that must trip it."""
    return [(label, gate) for gate in gates]


def _second_flags(labelled: list[tuple[str, Gate]]) -> list[tuple[str, Gate, str]]:
    """Every environment key a skip gate reads that is not the one opt-in."""
    return [(label, gate, name) for label, gate in labelled for name in gate.env if name != OPT_IN]


def _reachability_skips(labelled: list[tuple[str, Gate]]) -> list[tuple[str, Gate]]:
    """Every skip gate whose guards reach a network client library."""
    return [(label, gate) for label, gate in labelled if gate.network]


def _unreadable(labelled: list[tuple[str, Gate]]) -> list[tuple[str, Gate]]:
    """Every skip gate decided by something this file could not read."""
    return [(label, gate) for label, gate in labelled if gate.opaque]


def _tree_gates(attribute: str = "skip") -> list[tuple[str, Gate]]:
    """Every gate in `tests/`, labelled by file. Asserts the walk saw something: a broken walker must
    fail here rather than pass every assertion below it vacuously."""
    modules = sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)
    assert modules, "walked no test modules -- the glob is broken, not the tree clean"
    out = [(str(p.relative_to(REPO)), gate) for p in modules for gate in _gates("", str(p.relative_to(REPO)), attribute, path=p)]
    assert out, f"walked {len(modules)} test modules and found no {attribute} gate -- the walker is broken"
    return out


def test_every_environment_keyed_skip_gate_in_tests_reads_the_one_venue_opt_in():
    """One opt-in for the class: a gate keyed on any other environment name is a second flag, and a
    second flag is how an agent that sets the one it was given gets another test silently skipped."""
    keyed = [(label, gate) for label, gate in _tree_gates() if gate.env]
    assert keyed, "no skip gate in tests/ reads the environment -- the opt-in is gone, or the walker is"
    wrong = _second_flags(keyed)
    assert not wrong, "\n".join(
        f"{label}:{gate.line} [{gate.kind}] gates a skip on {name!r}, not {OPT_IN!r}: {gate.guards}" for label, gate, name in wrong
    )


def test_no_skip_gate_in_tests_decides_on_whether_the_venue_answers():
    """The fail-when-set arm, as a property rather than as a call: with the opt-in set, a venue that
    does not answer can only fail a test, because no skip in the tree is reached from a network call."""
    offending = _reachability_skips(_tree_gates())
    assert not offending, "\n".join(
        f"{label}:{gate.line} [{gate.kind}] skips on {list(gate.network)} -- an unreachable venue would "
        f"skip here, and a skip reads as a pass: gate it on {OPT_IN} and let the probe FAIL instead. "
        f"Guards: {gate.guards}"
        for label, gate in offending
    )


def test_no_skip_gate_in_tests_is_decided_by_something_this_file_cannot_read():
    """The two assertions above are worth their names only over gates whose guards were actually read.
    A gate deciding on a name this file cannot resolve -- a helper outside `tests/`, a condition
    assembled at run time -- is refused rather than counted clean, because clean is what it would
    otherwise look like."""
    unreadable = _unreadable(_tree_gates())
    assert not unreadable, "\n".join(
        f"{label}:{gate.line} [{gate.kind}] is decided by {list(gate.opaque)}, which this guard cannot "
        f"read, so neither assertion above covers it. Guards: {gate.guards}"
        for label, gate in unreadable
    )


def test_the_tree_holds_the_controls_that_keep_those_assertions_falsifiable():
    """All three pass on an empty set. Each needs a live counter-shape in the tree: a skip gate with no
    venue dependency, which must keep passing, and a reachability-keyed `pytest.fail`, which is the
    permitted half of the asymmetry actually being used."""
    plain = [(label, gate) for label, gate in _tree_gates() if not gate.env]
    assert plain, "every skip gate in tests/ reads the environment -- the one-name assertion has no control"
    reachability_fails = [(label, gate) for label, gate in _tree_gates("fail") if gate.network]
    assert reachability_fails, (
        "no `pytest.fail` in tests/ is keyed on reachability -- nothing in the tree exercises the half of "
        f"the rule that MAY read the venue, so {OPT_IN}=1 no longer fails loudly anywhere"
    )


# Every shape the three assertions must catch and every shape they must not, as source rather than as
# a description of source. The walker runs over this exactly as it runs over `tests/`, so a change
# that stops it seeing one of these fails here instead of going quiet over the real tree. It is passed
# with no path, which is also how the cross-module case is exercised: with no file to resolve against,
# an imported helper is a name this file cannot read.
_FIXTURE = """
import os
import pytest
from pathlib import Path
from os import getenv
from tests.venue_gate_absent_by_construction import venue_is_up

FLAG = "ZCRYPTO_LIVE_VENUE_TESTS"
OTHER = "ZCRYPTO_SOMETHING_ELSE"
ROOT = Path("data")


def _venue_answers():
    import urllib.request

    with urllib.request.urlopen("https://example.invalid", timeout=1) as answer:
        return answer.status == 200


def _opted_in():
    return os.environ.get(OTHER) == "1"


@pytest.mark.skipif(os.environ.get(FLAG) != "1", reason="the one opt-in")
def test_gated_on_the_flag():
    pass


@pytest.mark.skipif(os.environ.get(OTHER) != "1", reason="a second flag")
def test_gated_on_a_second_flag():
    pass


@pytest.mark.parametrize("value", [pytest.param(1, marks=pytest.mark.skipif(os.environ.get(OTHER) != "1", reason="marks="))])
def test_gated_on_a_second_flag_through_marks(value):
    pass


@pytest.mark.skipif(condition=os.environ["ZCRYPTO_" + "COMPUTED"] != "1", reason="assembled at run time")
def test_gated_on_a_computed_key():
    pass


@pytest.mark.skipif(not ROOT.exists(), reason="no dataset on this workstation")
def test_gated_on_a_local_dataset():
    pass


@pytest.mark.skipif("os.environ.get(OTHER) != '1'", reason="pytest's string spelling")
def test_gated_on_a_second_flag_written_as_a_string():
    pass


def test_gated_on_a_second_flag_one_call_away_from_the_condition():
    if not _opted_in():
        pytest.skip("the read is in the helper, not in the condition")


def test_gated_on_a_second_flag_read_by_subscript():
    if os.environ[OTHER] != "1":
        pytest.skip("a subscript reads the environment too")


def test_gated_on_a_second_flag_read_by_bare_getenv():
    if getenv(OTHER) != "1":
        pytest.skip("from os import getenv is the same read")


def test_gated_on_a_second_flag_read_by_membership():
    if OTHER not in os.environ:
        pytest.skip("membership reads the environment too")


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


def test_skips_in_the_else_rather_than_the_body():
    if _venue_answers():
        pass
    else:
        pytest.skip("an else is gated by the same condition")


def test_skips_in_an_except_handler_with_no_condition_anywhere():
    try:
        _venue_answers()
    except OSError:
        pytest.skip("the commonest reachability skip has no condition at all")


def test_gated_on_a_helper_this_file_cannot_read():
    if not venue_is_up():
        pytest.skip("the whole decision lives one module away")


def test_fails_rather_than_skips_when_the_opt_in_is_set():
    if os.environ.get(FLAG) != "1":
        pytest.skip("needs a live venue")
    if not _venue_answers():
        pytest.fail("the opt-in was set but the venue is unreachable")
"""

_FIXTURE_GATES = _labelled(_gates(_FIXTURE), "fixture")


def test_a_second_opt_in_name_is_caught_in_every_spelling_the_language_offers():
    """Seven ways to name a flag: the `skipif` decorator, a `marks=` entry, pytest's string condition,
    a same-module helper, a subscript, a bare `getenv`, and a membership test. The `condition=` keyword
    carries the eighth shape and names no flag at all -- its key is assembled at run time, and it is
    refused rather than read. The first shape of this file knew three of the seven, and a gate spelled
    any of the other four read the environment while being counted as reading nothing at all."""
    offenders = _second_flags(_FIXTURE_GATES)
    assert sum(name == "ZCRYPTO_SOMETHING_ELSE" for _, _, name in offenders) == 7, (
        f"every spelling of the second flag must be caught, got {[(g.line, n) for _, g, n in offenders]}"
    )
    assert any(name.startswith("<unresolved") for _, _, name in offenders), "a computed key must be refused"
    assert OPT_IN not in {name for _, _, name in offenders}, "the one opt-in must not be reported as a second flag"


def test_a_reachability_keyed_skip_is_caught_in_every_place_a_skip_can_sit():
    """Five places: inline, through a helper, nested below the condition, in an `else`, and in an
    `except` handler. The last has no condition anywhere -- it is the commonest way to write a
    reachability skip, and reading conditions alone finds no gate there at all."""
    caught = _reachability_skips(_FIXTURE_GATES)
    assert len(caught) == 5, f"expected five reachability skips, got {[(g.line, g.guards[:60]) for _, g in caught]}"
    assert any("except" not in g.guards and "urlopen" in g.guards for _, g in caught), "the except-handler case must be among them"


def test_a_gate_decided_one_module_away_is_refused_rather_than_called_clean():
    """The blind spot a discarded mutation probe was reporting. `venue_is_up` is imported from a module
    under `tests/` that does not exist, so its whole decision is unreadable -- and unreadable must fail,
    because the alternative is a gate that passes the other two assertions by being invisible to both.

    The absent module is asserted absent rather than assumed so: an earlier shape of this fixture
    imported a plausible name, and the day a real file took that name the case quietly stopped being
    the case it is here to prove and two assertions below it changed meaning with nothing to say so.
    """
    absent = TESTS / "venue_gate_absent_by_construction.py"
    assert not absent.exists(), f"{absent} now exists, so the fixture's unreadable helper is readable and proves nothing"
    unreadable = _unreadable(_FIXTURE_GATES)
    assert [g.opaque for _, g in unreadable] == [("venue_is_up",)], f"expected the sibling helper, got {unreadable}"


def test_a_gate_with_no_venue_dependency_passes_beside_them():
    """The degeneracy control. A guard that flagged every skip would pass its own fixture and refuse
    the dataset gates that are most of `tests/` -- an absent dataset is not an outage read as coverage."""
    dataset = [gate for gate in _gates(_FIXTURE) if "ROOT.exists" in gate.guards]
    assert len(dataset) == 1, f"the fixture's one dataset gate must be seen, got {dataset}"
    assert dataset[0].env == () and dataset[0].network == () and dataset[0].opaque == (), f"got {dataset[0]}"


def test_a_reachability_keyed_fail_is_not_a_skip_gate():
    """The permitted half, and the reason the rule is worth following: reading the venue to FAIL is what
    makes the opt-in mean something. Asserted on the LINE the `pytest.fail` sits on, because the first
    shape of this test searched gate guards for a string that only ever appears in a fail's MESSAGE --
    an empty list for every possible implementation, and an assertion that could not fail."""
    fail_line = next(i for i, text in enumerate(_FIXTURE.splitlines(), 1) if "pytest.fail(" in text)
    assert fail_line not in {g.line for g in _gates(_FIXTURE)}, "a `pytest.fail` must not be read as a skip gate"
    fails = [g for g in _gates(_FIXTURE, attribute="fail") if g.network]
    assert [g.line for g in fails] == [fail_line], f"the fail arm must be seen at {fail_line}, got {fails}"
