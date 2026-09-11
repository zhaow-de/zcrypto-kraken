"""Reachability may FAIL a test, never skip it, and one flag name opens every test that reaches a venue.

A test that reaches a live venue is gated on `ZCRYPTO_LIVE_VENUE_TESTS=1`, never on whether the venue
answers. Gated on reachability such a test runs in CI, where it is a flake source, and goes
green-by-skip the day the venue blocks the runner -- and a skip is indistinguishable from a pass in a
summary line, so an outage reads as coverage of a contract nobody exercised. Gated on the flag, the
same outage FAILS. That asymmetry is what the opt-in buys, and it is the whole of the rule.

HOW THIS FILE ASKS THE QUESTION, which is the part worth understanding before changing anything. It
does not recognise the ways a guard can read the environment or reach the venue. It REDUCES each
guard to a reading -- environment keys, network surfaces, and what could not be read -- and an
expression it cannot reduce is REFUSED rather than assumed to read nothing.

That inversion is the finding of three review rounds, not a preference. The first shape recognised
spellings and called everything else clean; twenty-five planted defects passed it, because recognition
fails by MIS-recognising and nothing sits under that. The reductions grew from four spellings to
fourteen across three source lists and a fresh reader still found eleven more. Closed-world is the
only shape with a floor: an unrecognised guard is a failure by construction, so the next spelling
nobody has thought of fails loudly instead of passing quietly.

Three assertions over every skip gate in `tests/`:

- every gate whose reading names environment keys names `ZCRYPTO_LIVE_VENUE_TESTS` and no other;
- no gate's reading reaches a network client library;
- no gate has anything it could not read.

The permitted predicates in `_PREDICATES` are the leaves of the reduction, and their SOURCE is this
tree rather than judgement: blanking names and literals out of every guard expression `_tree_gates()`
finds gives 15 distinct shapes over 61 expressions, and these are the predicates those shapes use.
Each declares WHAT IT READS, and the venue property is computed from that declaration rather than by
re-deriving meaning from a shape a second time.

What that list does NOT do, stated because an earlier draft of this paragraph said it did: it is not
an allowlist of methods a guard may call. A method on a value that reads nothing -- `raw.get(k)`,
`", ".join(xs)`, `path.samefile(other)` -- is permitted whether or not its name is listed, because a
receiver with no venue provenance cannot acquire one by having a method called on it. `_PREDICATES` is
the set this file UNDERSTANDS well enough to attribute a reading to. What is refused is a call it
cannot resolve to a definition in our own code and cannot attribute to a library, and the refusal
names both ways out: rewrite the guard in a form this file can reduce, or add the form with what it
reads. A mutation probe is what forced the distinction -- `PRIMARY_ROOT.samefile(...)` SURVIVED a probe
written against the stronger claim, and the stronger claim was the thing that was wrong.

One earned exemption, stated because it is the only one: a function that already `pytest.fail`s on a
condition reading the venue may skip on what the venue RETURNED. Its loud arm has fired by then, so
the skip is not reachable by an outage -- which is a different thing from a skip decided by whether
the venue answers at all. `tests/test_tape_bars_rest_control.py` is the case: it fails on no candles
and on a window shorter than the day it compares, and then skips on local archive state.

Out of scope, and both directions are bounded rather than open. Whether a venue-reaching test is
gated AT ALL: no AST says a call leaves the machine, so an ungated venue test is not findable here --
it is also the loud failure, running red in CI on the first outage, rather than the silent one. And
WHICH calls reach the network: `NETWORK` names client libraries, so a probe built on `subprocess` and
a command-line tool is not recognised as one. What catches those is the third assertion, if and only
if the probe sits behind a name this file cannot read.

The class had three names until T0190: `ZCRYPTO_VENUE_CONTRACT` and `ZCRYPTO_E1B_LIVE` implemented the
same rule under their own spellings, so an agent that set the one name it had been given got the other
two tests silently skipped. The owner ruled one flag for the class on 2026-09-09, the order-placing
probe included, because the finer grain bought nothing a reader could act on.

Those two names in the paragraph above are why `git grep 'ZCRYPTO_VENUE_CONTRACT\\|ZCRYPTO_E1B_LIVE' --
tests/ cli/ infra/ .claude/ CLAUDE.md` returns one hit rather than none, and the hit is this file. A
guard that names what it forbids is always inside its own corpus; the sweep is not regressed and the
answer is not to delete the history it records. What keeps the guard from reading ITSELF is that the
walker runs over gates and this file has none: its shapes are held as source in a string, which no
parse of this module sees as code.
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

# Every mapping accessor that answers with a value for a key. `setdefault` and `pop` mutate as well as
# read, which is why they fall out of a list assembled from what a gate USUALLY looks like -- and a
# gate keyed on either reads the environment exactly as `.get` does.
_MAPPING_READS = ("get", "getenv", "setdefault", "pop")

# Accessors that answer with the mapping itself or a view of it, so a gate reading through one is
# reading the environment. Taken from `dir(os.environ)` rather than from what a gate usually does.
_MAPPING_VIEWS = ("copy", "keys", "values", "items")


class Gate(NamedTuple):
    """One skip site: where it is, and what its guards read, reach and could not be read at all."""

    line: int
    kind: str
    env: tuple[str, ...]
    network: tuple[str, ...]
    opaque: tuple[str, ...]
    guards: str


class Module(NamedTuple):
    """A parsed module and the lookups a guard is read against, all of them ITS OWN.

    The module travels with every node taken from it. Names inside a helper resolve where the helper
    lives and nowhere else, and resolving them against the module that CALLED it reads correct code as
    unreadable in one direction and an unreadable helper as clean in the other -- both measured before
    this field existed.
    """

    tree: ast.Module
    strings: dict[str, str]
    functions: dict[str, ast.AST]
    imported: dict[str, str]  # a name bound by import -> the dotted module it came from
    modules: dict[str, str]  # a name bound to a MODULE of ours -> its dotted path
    defined: frozenset[str]  # every name this module binds at its top level
    environs: frozenset[str]  # names holding the environment mapping itself
    label: str


def _assigned(node: ast.AST) -> set[str]:
    """Every bare name assigned anywhere under this node, by `=`, `:=`, a `for`, a `with` or an import."""
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            out.add(child.id)
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            out |= {(a.asname or a.name).split(".")[0] for a in child.names}
    return out


def _module_strings(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"`, annotated or not, so a gate keyed on a constant resolves to the
    flag it means.

    A name that any function also assigns is left OUT, so it reads UNRESOLVED rather than resolving to
    the module's value. A gate inside such a function may be reading the local binding, and answering
    with the module-level one would name a flag the gate does not read -- reporting the one opt-in for
    a gate keyed on a second, which is a false negative wearing the right answer's clothes.
    """
    out: dict[str, str] = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if isinstance(getattr(node, "value", None), ast.Constant) and isinstance(node.value.value, str):
            out.update({t.id: node.value.value for t in targets if isinstance(t, ast.Name)})
    shadowed = set().union(*(_assigned(n) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), set())
    return {name: value for name, value in out.items() if name not in shadowed}


def _module_functions(tree: ast.Module) -> dict[str, ast.AST]:
    """Every definition a call can land on, by bare name: functions, methods, and CLASSES.

    A class belongs here because calling one is calling its body, and leaving classes out made every
    constructor call in a followed helper an unreadable name -- one real helper module refused for
    nine of them, none of which had anything to do with a venue.
    """
    return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _imported(tree: ast.Module) -> dict[str, str]:
    """Each name bound by an import, mapped to the module it came from.

    The distinction that matters downstream is not whether the module resolves but whose it is. A name
    from a library is not opaque -- reading `pathlib` is not this file's business -- while a name from
    this repo's own code is one of ours, and one of those that cannot be read is precisely the case
    that lets a gate's whole decision sit where nothing checks it.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.update({(a.asname or a.name): node.module for a in node.names})
        elif isinstance(node, ast.Import):
            out.update({(a.asname or a.name.split(".")[0]): a.name for a in node.names})
    return out


OURS = ("tests", "cli", "infra")


def _is_local_module(dotted: str) -> bool:
    """Whether an import names this repo's own code rather than a library."""
    return dotted.split(".")[0] in OURS or (TESTS / f"{dotted.split('.')[-1]}.py").is_file()


def _module_path(dotted: str) -> Path | None:
    """The file an import of our own code names, when there is one. A dotted path is tried whole, and
    a bare name is tried beside the importer, which is how this suite spells its helper imports."""
    stem = dotted.replace(".", "/")
    for candidate in (REPO / f"{stem}.py", REPO / stem / "__init__.py", TESTS / f"{dotted.split('.')[-1]}.py"):
        if candidate.is_file():
            return candidate
    return None


def _module_aliases(tree: ast.Module) -> dict[str, str]:
    """Names bound to a MODULE of ours rather than to a value in one.

    `from tests import basket_fixture` is this suite's own idiom -- `test_engine_feeders.py`,
    `test_engine_soak.py` and `test_engine_tracking.py` all spell it that way -- and it binds a module,
    so the helper is reached as `basket_fixture.probe()`. Treating that receiver as an ordinary object
    is how a gate calling a sibling module's probe read clean.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                dotted = f"{node.module}.{a.name}"
                if _module_path(dotted) is not None:
                    out[a.asname or a.name] = dotted
        elif isinstance(node, ast.Import):
            for a in node.names:
                if _module_path(a.name) is not None:
                    out[a.asname or a.name] = a.name
    return out


def _os_aliases(tree: ast.Module) -> frozenset[str]:
    """Names bound to the `os` module. `import os as o` then `o.environ.get(K)` is an environment read,
    and a receiver test spelled as the literal text `os.environ` does not see it -- measured as a
    regression against an earlier shape of this file that tested the text's SUFFIX instead."""
    return frozenset(
        {(a.asname or a.name) for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names if a.name == "os"} | {"os"}
    )


def _is_environ_expression(node: ast.AST, aliases: frozenset[str]) -> bool:
    """Whether this expression IS the environment mapping: `os.environ`, a name holding it, or a copy.

    `os.environ.copy()` and `dict(os.environ)` carry the same keys, so a gate reading one is reading
    the environment however the mapping got into its hands.
    """
    if isinstance(node, (ast.Name, ast.Attribute)):
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            return ast.unparse(node.value) in _OS_ALIASES.get(id(aliases), {"os"})
        return ast.unparse(node) == "environ" or (isinstance(node, ast.Name) and node.id in aliases)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _MAPPING_VIEWS and _is_environ_expression(func.value, aliases):
            return True
        if isinstance(func, ast.Name) and func.id == "dict" and node.args and _is_environ_expression(node.args[0], aliases):
            return True
    return False


def _register_os_aliases(tree: ast.Module, environs: frozenset[str]) -> frozenset[str]:
    """Bind this module's `os` aliases to its environ-alias set, so the receiver test can reach them."""
    _OS_ALIASES[id(environs)] = _os_aliases(tree)
    return environs


def _environ_aliases(tree: ast.Module) -> frozenset[str]:
    """Every name holding the environment mapping, to a fixpoint so `b = a` after `a = os.environ`
    counts. Without this the receiver test is a literal `os.environ`, and `env = os.environ` one line
    above the gate makes every read through `env` invisible -- measured, with the guard still green."""
    # MODULE-LEVEL only. Walking the whole tree promoted any function's local `env = os.environ.copy()`
    # -- the ordinary subprocess idiom, in four functions of `test_engine_node.py` -- to a module-wide
    # alias, so another function's local `env` holding an unrelated dict read as the environment and
    # turned correct code red. A function-local binding reaches its gate through the scope instead.
    aliases: frozenset[str] = frozenset()
    while True:
        found = set(aliases)
        for node in tree.body:
            if isinstance(node, ast.Assign) and _is_environ_expression(node.value, aliases):
                found |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        if found == set(aliases):
            return aliases
        aliases = frozenset(found)


@functools.cache
def _module(path: Path) -> Module:
    """A module of ours, parsed once. Cached because one helper module is imported by several."""
    return _module_of(path.read_text(), str(path.relative_to(REPO)))


def _module_of(source: str, label: str) -> Module:
    tree = ast.parse(source, label)
    return Module(
        tree=tree,
        strings=_module_strings(tree),
        functions=_module_functions(tree),
        imported=_imported(tree),
        modules=_module_aliases(tree),
        defined=frozenset(_assigned(tree)) | frozenset(_module_functions(tree)),
        environs=_register_os_aliases(tree, _environ_aliases(tree)),
        label=label,
    )


def _read_module(dotted: str) -> Module | None:
    """The parsed module a dotted name refers to, when it is ours and on disk."""
    path = _module_path(dotted) if _is_local_module(dotted) else None
    return _module(path) if path is not None else None


def _resolve(owner: Module, call: ast.Call) -> tuple[ast.AST, Module] | str | None:
    """What a call reaches: a function with the module it lives in, an OPAQUE name, or None to ignore.

    Three receivers are followed -- a bare name, `self`/`cls`, and a name bound to a module of ours.
    Everything else is a library reached through its own module and is not this file's business. A
    name that should resolve to our code and does not comes back as a string, which the caller records
    as unreadable rather than passing over.
    """
    func = call.func
    if isinstance(func, ast.Name):
        name, holder = func.id, owner
    elif isinstance(func, ast.Attribute):
        receiver = ast.unparse(func.value)
        if receiver in ("self", "cls"):
            name, holder = func.attr, owner
        elif receiver in owner.modules:
            found = _read_module(owner.modules[receiver])
            if found is None:
                return func.attr
            name, holder = func.attr, found
        elif isinstance(func.value, ast.Name) and _is_local_module(owner.imported.get(func.value.id, "")):
            # A name imported from our own code. It is a VALUE if the module it came from binds it --
            # `DATA_ROOT.exists()` is a Path, not a package -- and only an unreadable MODULE is opaque.
            source = _read_module(owner.imported[func.value.id])
            return None if source is not None and func.value.id in source.defined else func.attr
        else:
            return None
    else:
        return None
    return _follow(name, holder, 0)


def _follow(name: str, holder: Module, depth: int) -> tuple[ast.AST, Module] | str | None:
    """Where a name is defined, following re-exports through our own packages.

    `from cli.registry import TrialRegistry` lands on `cli/registry/__init__.py`, which imports the
    class from `store.py` -- a package that re-exports is the ordinary shape here, and stopping at the
    `__init__` reports our own code as unreadable. Bounded at five hops: a chain longer than that is
    a chain this file should refuse rather than chase.
    """
    if depth > 5:
        return name
    body = holder.functions.get(name)
    if body is not None:
        return (body, holder)
    dotted = holder.imported.get(name)
    if dotted is None:
        return None if name in dir(builtins) else name
    if not _is_local_module(dotted):
        return None  # a library: exempt rather than opaque
    found = _read_module(dotted)
    return _follow(name, found, depth + 1) if found is not None else name


def _environment_key(node: ast.AST, strings: dict[str, str]) -> str:
    """The variable name an environment read asks for. A key this cannot read is returned UNRESOLVED,
    which fails the one-name assertion rather than passing it -- the safe direction for a gate whose
    flag is assembled at run time."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in strings:
        return strings[node.id]
    return f"<unresolved: {ast.unparse(node)}>"


def _is_network(text: str) -> bool:
    """A dotted name is a network surface when its first segment is one, or when it IS one -- the
    `asyncio.open_connection` entry names a verb because `asyncio` alone is not a network library."""
    return text.split(".")[0] in NETWORK or any(text == n or text.startswith(n + ".") for n in NETWORK)


# --- the closed world -----------------------------------------------------------------------------
# Everything below answers ONE question about a guard expression: what does it read? The answer is a
# reading, and an expression this file cannot reduce to a reading is REFUSED rather than assumed to
# read nothing. That is the whole of the inversion. Three rounds of the previous design -- which
# recognised the ways an expression could read the environment and called everything else clean --
# left twenty-five planted defects passing, because recognition fails by MIS-recognising and there is
# no backstop under it. Here an unrecognised shape is a failure by construction.
#
# The permitted predicates below are the leaves of that reduction. Their source is this tree's own
# guards, not judgement: blanking names and literals out of every guard expression `_tree_gates()`
# finds gives 15 distinct shapes over 61 expressions, and these are the predicates those shapes use.
# Each names WHAT IT READS, and the venue property is computed from that declaration rather than by
# re-recognising the shape a second time.
_PREDICATES = {
    "exists": "a path on disk",
    "is_file": "a path on disk",
    "is_dir": "a path on disk",
    "geteuid": "the effective uid of this process",
    "which": "whether a binary is on PATH",
    "resolve": "a path, normalised",
    "read_text": "the bytes of a file already on disk",
    "glob": "the names under a directory on disk",
    "rglob": "the names under a directory on disk",
    "splitlines": "a string already in hand",
    "strip": "a string already in hand",
    "lower": "a string already in hand",
    "startswith": "a string already in hand",
    "endswith": "a string already in hand",
    "split": "a string already in hand",
    "keys": "the names in a mapping already in hand",
    "values": "the values in a mapping already in hand",
    "items": "the pairs in a mapping already in hand",
}
# Builtins a guard may call. Same source: what this tree's guards actually use.
_BUILTINS = ("len", "any", "all", "sorted", "set", "list", "tuple", "dict", "str", "int", "bool", "isinstance", "getattr")

_REFUSAL_REMEDY = (
    "rewrite the guard as one of the permitted forms in _PREDICATES, or add the form to _PREDICATES with what it reads"
)


class Reading(NamedTuple):
    """What one guard expression reads: environment keys, network surfaces, and what was unreadable."""

    env: frozenset[str]
    network: frozenset[str]
    refused: frozenset[str]

    def __or__(self, other):
        return Reading(self.env | other.env, self.network | other.network, self.refused | other.refused)


_NOTHING = Reading(frozenset(), frozenset(), frozenset())

# What a function reads is a property of the function, not of who called it, so it is computed once.
# Measured: the walk over 220 modules costs 28s without this and a fraction of that with it, because a
# helper called from twenty gates was being reduced twenty times.
_BODY_READING: dict[tuple[str, str], Reading] = {}
# `os` aliases per module, reached from the environ-alias frozenset every caller already carries.
_OS_ALIASES: dict[int, frozenset[str]] = {}


def _reads(*parts: str) -> Reading:
    return Reading(frozenset(parts), frozenset(), frozenset())


def _refuses(*names: str) -> Reading:
    return Reading(frozenset(), frozenset(), frozenset(names))


def _locals_of(function: ast.AST | None) -> dict[str, ast.AST]:
    """`name = <expr>` inside the gate's own function, so a guard reading a local reads what built it.
    Without this a gate spelled `env = os.environ` then `env.get(K)` reads a bare name and nothing
    else, which is how a mapping bound one line above a gate stayed invisible."""
    if function is None:
        return {}
    # Parameters first: a name the caller binds is a VALUE, and calling one is not calling something
    # this file failed to read. `cli/derivatives/funding.py`'s `_get_bytes(*, opener)` is the shape --
    # `opener(url)` refused as unreadable until this line, while the network its default carries is
    # picked up from the default expression either way.
    out: dict[str, ast.AST] = {a.arg: None for a in ast.walk(function) if isinstance(a, ast.arg)}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            out.update({t.id: node.value for t in node.targets if isinstance(t, ast.Name)})
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
    return out


def _classify(node: ast.AST, module: Module, scope: dict[str, ast.AST], seen: frozenset) -> Reading:
    """The reading of one expression, reducing calls into code this repo owns and refusing the rest."""
    if node is None or isinstance(node, (ast.Constant, ast.Slice)):
        return _NOTHING
    if _is_environ_expression(node, module.environs):
        return _reads("<unresolved: the environment reached without naming a key>")
    if isinstance(
        node,
        (
            ast.BoolOp,
            ast.UnaryOp,
            ast.BinOp,
            ast.IfExp,
            ast.Starred,
            ast.Tuple,
            ast.List,
            ast.Set,
            ast.Dict,
            ast.JoinedStr,
            ast.FormattedValue,
            ast.Yield,
            ast.YieldFrom,
            ast.Await,
            ast.NamedExpr,
        ),
    ):
        kids = [k for k in ast.iter_child_nodes(node) if isinstance(k, ast.expr)]
        return _fold(kids, module, scope, seen)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        kids = [k for k in ast.walk(node) if isinstance(k, ast.expr) and k is not node]
        return _fold(kids, module, scope, seen)
    if isinstance(node, ast.Compare):
        reading = _classify(node.left, module, scope, seen)
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)) and _is_environ_expression(comparator, module.environs):
                reading = reading | _reads(_environment_key(node.left, module.strings))
            else:
                reading = reading | _classify(comparator, module, scope, seen)
        return reading
    if isinstance(node, ast.Subscript):
        if _is_environ_expression(node.value, module.environs):
            return _reads(_environment_key(node.slice, module.strings))
        return _classify(node.value, module, scope, seen) | _classify(node.slice, module, scope, seen)
    if isinstance(node, ast.Name):
        if node.id in scope and node.id not in seen:
            return _classify(scope[node.id], module, scope, seen | {node.id})
        return _NOTHING  # a parameter, a module constant, or a value already reduced
    if isinstance(node, ast.Attribute):
        if _is_network(ast.unparse(node)):
            return Reading(frozenset(), frozenset({ast.unparse(node)}), frozenset())
        owned = _owned_attribute(node, module, scope)
        if owned is not None:
            body, holder = owned
            return _fold(_body_expressions(body), holder, _locals_of(body), seen)
        return _classify(node.value, module, scope, seen)
    if isinstance(node, ast.Call):
        return _classify_call(node, module, scope, seen)
    if isinstance(node, ast.stmt):
        # A `try` body is statements, not an expression: `try: urlopen(...) except: skip()` hands this
        # an `ast.Expr`, and refusing it reported the commonest reachability skip as unreadable.
        return _fold([k for k in ast.iter_child_nodes(node) if isinstance(k, ast.expr)], module, scope, seen)
    return _refuses(f"{type(node).__name__} expression")


def _body_expressions(body: ast.AST) -> list[ast.AST]:
    """Every expression not nested inside another, letting `_classify` recurse into the rest.

    Folding `ast.walk` instead reduces `os.environ.get(K)` twice -- once as the call that names K and
    once as the bare mapping inside it -- and reports a key AND an unkeyed read for one expression.
    Taking each statement's DIRECT children instead misses the other way: `with urllib.request.urlopen(
    ...) as answer:` holds its call in a `withitem`, which is not an expression, so the one reachability
    probe in the fixture read clean. Parent-is-not-an-expression is the condition that does both.
    """
    parents = {child: node for node in ast.walk(body) for child in ast.iter_child_nodes(node)}
    return [node for node in ast.walk(body) if isinstance(node, ast.expr) and not isinstance(parents.get(node), ast.expr)]


def _fold(nodes, module: Module, scope: dict[str, ast.AST], seen: frozenset) -> Reading:
    reading = _NOTHING
    for n in nodes:
        reading = reading | _classify(n, module, scope, seen)
    return reading


def _owned_class(node: ast.AST, module: Module, scope: dict[str, ast.AST]) -> tuple[ast.ClassDef, Module] | None:
    """The class one of our own names refers to, whether the name holds the class or an instance of it.

    `_Probe.up()` and `_probe = _Probe()` then `_probe.up()` reach the same method by two receivers, and
    a walker that follows only bare names and `self`/`cls` sees neither -- both were planted carrying a
    real `urlopen` probe and both read clean.
    """
    if isinstance(node, ast.Call):
        return _owned_class(node.func, module, scope)
    if isinstance(node, ast.Name):
        bound = scope.get(node.id)
        if isinstance(bound, ast.AST):
            found = _owned_class(bound, module, scope)
            if found is not None:
                return found
        here = _module_scope(module.tree).get(node.id)
        if here is not None and here is not bound:
            found = _owned_class(here, module, {})  # a name bound at the top of the gate's OWN module
            if found is not None:
                return found
        answer = _follow(node.id, module, 0)
        if isinstance(answer, tuple) and isinstance(answer[0], ast.ClassDef):
            return answer
        dotted = module.imported.get(node.id)
        if dotted is not None and _is_local_module(dotted):
            source = _read_module(dotted)
            if source is not None:
                bound_there = _module_scope(source.tree).get(node.id)
                if bound_there is not None:
                    return _owned_class(bound_there, source, {})
    return None


def _owned_attribute(func: ast.Attribute, module: Module, scope: dict[str, ast.AST]) -> tuple[ast.AST, Module] | None:
    """What `<one of ours>.<name>` is: a method, or the expression a class attribute is bound to."""
    found = _owned_class(func.value, module, scope)
    if found is None:
        return None
    klass, holder = found
    for node in klass.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func.attr:
            return (node, holder)
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(x, ast.Name) and x.id == func.attr for x in targets) and node.value is not None:
            return (node, holder)
    return None


def _classify_call(node: ast.Call, module: Module, scope: dict[str, ast.AST], seen: frozenset) -> Reading:
    func = node.func
    args = _fold(list(node.args) + [k.value for k in node.keywords], module, scope, seen)
    if isinstance(func, ast.Attribute):
        owned = _owned_attribute(func, module, scope)
        if owned is not None:
            body, holder = owned
            return args | _fold(_body_expressions(body), holder, _locals_of(body), seen)
        if func.attr in _MAPPING_READS:
            # A mapping handed back by a call, or held on one of our own objects, is still the mapping,
            # so the RECEIVER is classified rather than matched against text. `_env().get(K)` and
            # `_Probe.mapping.get(K)` are both environment reads and neither spells `os.environ`.
            inner = _classify(func.value, module, scope, seen)
            if _is_environ_expression(func.value, module.environs) or any(
                k.startswith("<unresolved: the environment") for k in inner.env
            ):
                return _reads(_environment_key(node.args[0], module.strings)) if node.args else _reads("<unresolved: no key>")
        if _is_network(ast.unparse(func)):
            return args | Reading(frozenset(), frozenset({ast.unparse(func)}), frozenset())
        if func.attr in _PREDICATES:
            return args | _classify(func.value, module, scope, seen)
    if isinstance(func, ast.Name):
        if func.id in scope:
            return args  # a value the caller bound, classified where it was bound
        if func.id == "getenv":
            return _reads(_environment_key(node.args[0], module.strings)) if node.args else _reads("<unresolved: no key>")
        if func.id in _BUILTINS:
            return args
    answer = _resolve(module, node)
    if isinstance(answer, tuple):
        body, holder = answer
        key = (holder.label, getattr(body, "name", ""))
        if key in seen:
            return args
        cached = _BODY_READING.get(key)
        if cached is None:
            cached = _fold(_body_expressions(body), holder, _locals_of(body), seen | {key})
            _BODY_READING[key] = cached
        return args | cached
    if answer is None:
        # `_resolve` answers None for a builtin and for a library -- neither is ours to read, and
        # neither is refused. It answers a NAME only for something that should have resolved here.
        return args
    return args | _refuses(ast.unparse(func))


def _parents(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    """Each node's parent, so a skip site can be walked back up to everything that decides it."""
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _guards_of(call: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.AST]:
    """Every expression deciding whether this call is reached, up to its function boundary.

    The list comes from the grammar rather than from memory: every `ast` statement node that can hold
    another statement is handled, because every one of them decides whether the skip below it runs. An
    `if` decides its `else` as much as its body; a `try` and a `try*` decide their handlers through
    what the BODY does -- `try: urlopen(...) except OSError: pytest.skip(...)` has no condition
    anywhere; a `match` decides through its SUBJECT; a `for` decides through its ITERABLE, so a loop
    over a venue call gates every skip inside it; and a `with` decides through its context manager,
    which is how `contextlib.suppress` turns a raise into a skip.

    Four of those carry no condition at all. Assembling this list from recall found two of the four,
    twice in a row; reading `ast`'s own node list found the rest in one pass.
    """
    guards: list[ast.AST] = []
    current = call
    while current in parents:
        up = parents[current]
        if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            break
        if isinstance(up, (ast.If, ast.While)) and (current in up.body or current in getattr(up, "orelse", [])):
            guards.append(up.test)
        elif isinstance(up, (ast.Try, ast.TryStar)) and current not in up.body:
            guards.extend(up.body)
        elif isinstance(up, (ast.For, ast.AsyncFor)) and current in up.body:
            guards.append(up.iter)  # a loop runs, or does not, on what its iterable answers
        elif isinstance(up, (ast.With, ast.AsyncWith)):
            guards.extend(item.context_expr for item in up.items)  # `contextlib.suppress` decides too
        elif isinstance(up, ast.Match):
            guards.append(up.subject)
            if isinstance(current, ast.match_case) and current.guard is not None:
                guards.append(current.guard)
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


def _pytest_bindings(tree: ast.Module, attribute: str) -> set[str]:
    """Names bound by `from pytest import <attribute>`, under whatever alias -- so `skip(...)` and a
    `from pytest import skip as bail` then `bail(...)` are both recognised. Bare-name recognition is
    limited to what the module actually imported: any suite has functions of its own called `skip`,
    and treating every one of them as pytest's would be a guess."""
    bound = {
        (a.asname or a.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "pytest"
        for a in node.names
        if a.name == attribute
    }
    # `_skip = pytest.skip` binds it too, and a name assigned the function is the function.
    modules = _pytest_modules(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) and node.value.attr == attribute:
            if ast.unparse(node.value.value) in modules:
                bound |= {x.id for x in node.targets if isinstance(x, ast.Name)}
    return bound


def _pytest_modules(tree: ast.Module) -> set[str]:
    """Names bound to the pytest MODULE. `import pytest as pt` then `pt.skip(...)` is a skip, and a
    receiver test spelled as the literal text `pytest` does not see it."""
    return {
        (a.asname or a.name) for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names if a.name == "pytest"
    } or {"pytest"}


def _skip_helpers(tree: ast.Module, attribute: str, bound: set[str], modules: set[str], parents: dict) -> set[str]:
    """Module functions that skip unconditionally, so calling one IS calling `pytest.skip`.

    `def bail(m): pytest.skip(m)` moves the skip one call away, and a walker that looks only for
    pytest's own name at the call site finds no skip site at all. It is the same indirection that hid
    a gate's flag read and a gate's reachability probe, applied to the skip itself -- found by reading
    pytest's API rather than by remembering what a skip looks like.
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if _is_pytest_call(child, attribute, bound, modules) and not _guards_of(child, parents):
                out.add(node.name)
    return out


def _is_pytest_call(node: ast.AST, attribute: str, bound: set[str], modules: set[str]) -> bool:
    """Whether this node reaches pytest's `<attribute>`: as an attribute of the module under any alias,
    as a bare name the module imported, or as `raise pytest.skip.Exception(...)`."""
    if isinstance(node, ast.Raise) and node.exc is not None:
        raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return ast.unparse(raised).endswith(f"{attribute}.Exception")
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == attribute:
        return ast.unparse(func.value) in modules
    return isinstance(func, ast.Name) and func.id in bound


def _module_scope(tree: ast.Module) -> dict[str, ast.AST]:
    """Module-level `name = <expr>`, the scope a `skipif` condition is evaluated in."""
    return {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    """The function a skip site sits in, whose local bindings its guards may read."""
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
    return None


def _gate(line: int, kind: str, guards: list[ast.AST], module: Module, scope: dict[str, ast.AST], extra=()) -> Gate:
    reading = _fold(guards, module, scope, frozenset())
    return Gate(
        line=line,
        kind=kind,
        env=tuple(sorted(reading.env)),
        network=tuple(sorted(reading.network)),
        opaque=tuple(sorted(reading.refused | set(extra))),
        guards=" ; ".join(ast.unparse(g) for g in guards)[:300],
    )


def _fails_loudly_on_the_venue(module: Module, parents: dict[ast.AST, ast.AST], modules: set[str]) -> set[int]:
    """Functions that already `pytest.fail` on a condition reading the venue.

    A skip inside one of those is not reachable by an OUTAGE: the loud arm has already fired by the
    time the skip is evaluated, so what remains is the venue's ANSWER intersected with local state,
    which is a different thing from a skip decided by whether the venue answers at all. That is the
    distinction this guard could not express in its first shape, and it is stated here rather than
    left for a reader to infer -- a function may earn the right to skip on venue-derived data by
    failing first, and no other way.
    """
    bound = _pytest_bindings(module.tree, "fail")
    loud: set[int] = set()
    for node in ast.walk(module.tree):
        if not _is_pytest_call(node, "fail", bound, modules):
            continue
        function = _enclosing_function(node, parents)
        guards = _guards_of(node, parents)
        if function is not None and guards and _fold(guards, module, _locals_of(function), frozenset()).network:
            loud.add(id(function))
    return loud


def _gates(source: str, label: str = "<fixture>", attribute: str = "skip", path: Path | None = None) -> list[Gate]:
    """Every gate in this module whose guards decide a `pytest.<attribute>()`.

    Two shapes reach it: the `skipif` marker, wherever it is written -- a decorator, a `condition=`
    keyword, or a `pytest.param(..., marks=...)` entry -- and a call, whose guards are read off the
    statements enclosing it rather than off any one condition. The call is recognised through the
    pytest module under any alias, through a bare name imported from pytest under any alias, through
    `raise pytest.skip.Exception`, and through a module function that skips unconditionally.

    Two of pytest's three skipping names are deliberately not here. `importorskip` takes a MODULE name,
    so it cannot be keyed on a venue flag or on reachability and cannot carry this defect. `xfail`
    stops a test without failing it, but an xfailed test is counted separately from a passing one in
    every report pytest writes, so it is not an outage read as coverage -- which is the thing this file
    exists to prevent, and the only thing it claims.
    """
    module = _module(path) if path is not None else _module_of(source, label)
    parents = _parents(module.tree)
    bound = _pytest_bindings(module.tree, attribute)
    modules = _pytest_modules(module.tree)
    bound |= _skip_helpers(module.tree, attribute, bound, modules, parents)
    loud = _fails_loudly_on_the_venue(module, parents, modules) if attribute == "skip" else set()
    out: list[Gate] = []
    for node in ast.walk(module.tree):
        if attribute == "skip" and isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.skipif"):
            raw = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "condition"), None)
            if raw is not None:
                condition, extra = _as_expression(raw)
                out.append(_gate(node.lineno, "skipif", [condition], module, _module_scope(module.tree), extra))
        elif _is_pytest_call(node, attribute, bound, modules):
            guards = _guards_of(node, parents)
            if guards:
                function = _enclosing_function(node, parents)
                gate = _gate(node.lineno, f"{attribute}-site", guards, module, _locals_of(function))
                if attribute == "skip" and function is not None and id(function) in loud:
                    gate = gate._replace(network=())
                out.append(gate)
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

    A gate deciding on anything this file cannot reduce -- a call to a name nothing binds, one into our
    own code that will not read, a predicate not on the permitted list, a condition assembled at run
    time -- is refused rather than counted clean, because clean is what it would otherwise look like.
    At EVERY depth: a previous shape of this file refused only what a guard called directly, which let
    a decision one function deeper read clean and was a regression on the shape before it.
    """
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
import os as o
import pytest
import urllib.request
from pathlib import Path
from os import getenv
from pytest import skip
from tests import basket_fixture
from tests import venue_gate_absent_by_construction
from tests.venue_gate_absent_by_construction import venue_is_up

ENV = os.environ
FLAG = "ZCRYPTO_LIVE_VENUE_TESTS"
OTHER = "ZCRYPTO_SOMETHING_ELSE"
SHADOWED = "ZCRYPTO_LIVE_VENUE_TESTS"
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


def test_gated_on_a_constant_a_function_rebinds():
    SHADOWED = "ZCRYPTO_SOMETHING_ELSE"
    if os.environ.get(SHADOWED) != "1":
        pytest.skip("the module-level value is not what this gate reads")


class _Probe:
    mapping = os.environ

    @staticmethod
    def up():
        return urllib.request.urlopen("https://example.invalid", timeout=1).status == 200


_probe = _Probe()
_skip = pytest.skip


def _env_map():
    return os.environ


def test_gated_on_a_second_flag_through_a_module_alias():
    if o.environ.get(OTHER) != "1":
        pytest.skip("`import os as o` spells the same mapping")


def test_gated_on_a_second_flag_a_function_handed_back():
    if _env_map().get(OTHER) != "1":
        pytest.skip("a mapping returned by a call is still the mapping")


def test_gated_on_a_second_flag_held_on_one_of_our_classes():
    if _Probe.mapping.get(OTHER) != "1":
        pytest.skip("a mapping on a class attribute is still the mapping")


def test_skips_on_a_probe_reached_through_a_class():
    if not _Probe.up():
        pytest.skip("the receiver is a class of ours")


def test_skips_on_a_probe_reached_through_an_instance():
    if not _probe.up():
        pytest.skip("the receiver is an instance of one")


def test_skips_through_a_name_bound_to_pytests_skip():
    if o.environ.get(OTHER) != "1":
        _skip("a name assigned the function is the function")


def test_gated_on_a_second_flag_read_through_an_alias_of_the_mapping():
    if ENV.get(OTHER) != "1":
        pytest.skip("an alias of the environment IS the environment")


def test_gated_on_a_second_flag_read_through_a_copy_of_the_mapping():
    if OTHER not in os.environ.copy():
        pytest.skip("a copy carries the same keys")


def test_skips_from_a_match_subject_with_no_condition_anywhere():
    match _venue_answers():
        case False:
            pytest.skip("a match decides through its subject")


def test_skips_through_the_bare_name_imported_from_pytest():
    if os.environ.get(OTHER) != "1":
        skip("pytest.skip reached by the name the module imported")


def test_gated_on_a_module_of_ours_that_resolves():
    if not basket_fixture.grids():
        pytest.skip("a real helper module, read and found clean")


def test_gated_on_a_module_of_ours_that_cannot_be_read():
    if not venue_gate_absent_by_construction.up():
        pytest.skip("the module-attribute form of an unreadable decision")


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
    """Fourteen ways to put a second flag in front of a skip, varying independently along four axes:
    where the gate is WRITTEN, how the SKIP is spelled, how the MAPPING is reached, and how the KEY is
    read off it. Two further shapes name no flag at all and are refused rather than read -- a key
    assembled at run time, and a constant some function rebinds.

    The count is written out because the assertion below IS the count: a spelling added to the fixture
    without moving this number is a spelling nothing checks. The recognition engine this replaced knew
    four of the fourteen, then seven, then ten, and each round the ones it did not know were a gate
    reading the environment while being counted as reading nothing at all. That is why the engine was
    replaced rather than widened a fourth time."""
    offenders = _second_flags(_FIXTURE_GATES)
    assert sum(name == "ZCRYPTO_SOMETHING_ELSE" for _, _, name in offenders) == 14, (
        f"every spelling of the second flag must be caught, got {[(g.line, n) for _, g, n in offenders]}"
    )
    unresolved = sorted(name for _, _, name in offenders if name.startswith("<unresolved"))
    assert len(unresolved) == 2, f"a computed key and a shadowed constant must both be refused, got {unresolved}"
    # NOT `OPT_IN not in offenders`: `_second_flags` filters on `!= OPT_IN`, so that could not fail for
    # any walker ever written. The property it meant is that the fixture's flag-keyed gate resolves.
    assert OPT_IN in {n for g in _gates(_FIXTURE) for n in g.env}, (
        "the fixture's own opt-in gate must resolve to the one flag, or the count above proves nothing"
    )


def test_a_constant_a_function_rebinds_is_refused_rather_than_answered_from_the_module():
    """The module-level `SHADOWED` holds the one opt-in and the gate reads a local rebinding holding a
    second flag. Answering from the module would name the right flag for the wrong gate -- a false
    negative wearing the correct answer's clothes -- so the key is refused instead."""
    gate = next(g for g in _gates(_FIXTURE) if "SHADOWED" in g.guards)
    assert gate.env == ("<unresolved: SHADOWED>",), f"a shadowed constant must not resolve, got {gate.env}"


def test_a_reachability_keyed_skip_is_caught_in_every_place_a_skip_can_sit():
    """Eight places a reachability skip can sit: inline, through a helper, nested below the condition,
    in an `else`, in an `except` handler, under a `match` case, behind a class receiver and behind an
    instance one. The `except` and `match` cases have no condition anywhere -- an `except` is the
    commonest way to write a reachability skip, and a `match` decides through its subject -- so reading
    conditions alone finds no gate in either, which is what the first two shapes of this file did. The
    last two were planted by a reviewer against the third shape and read clean."""
    caught = _reachability_skips(_FIXTURE_GATES)
    assert len(caught) == 8, f"expected eight reachability skips, got {[(g.line, g.guards[:60]) for _, g in caught]}"
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
    assert sorted(g.opaque for _, g in unreadable) == [("venue_gate_absent_by_construction.up",), ("venue_is_up",)], (
        f"BOTH import forms of an unreadable module must be refused -- `from tests import mod` then "
        f"`mod.up()`, and `from tests.mod import f` then `f()` -- got {unreadable}"
    )
    readable = [g for g in _gates(_FIXTURE) if "basket_fixture" in g.guards]
    assert len(readable) == 1 and readable[0].opaque == (), (
        f"a module of ours that DOES read must stay clean, or the refusal is just a ban on helpers: {readable}"
    )


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
