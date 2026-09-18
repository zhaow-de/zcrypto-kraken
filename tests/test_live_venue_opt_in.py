"""One flag name opens every test that reaches a venue, and a guard that matches no form is refused.

A test that reaches a live venue is gated on `ZCRYPTO_LIVE_VENUE_TESTS=1`, never on whether the venue
answers. Gated on reachability such a test runs in CI, where it is a flake source, and goes
green-by-skip the day the venue blocks the runner -- and a skip is indistinguishable from a pass in a
summary line, so an outage reads as coverage of a contract nobody exercised.

WHAT THIS FILE HOLDS, the two halves of that rule:

- every skip gate in `tests/` that reads an environment key reads `ZCRYPTO_LIVE_VENUE_TESTS` and no
  other, so a second opt-in cannot appear unnoticed;
- every skip gate in `tests/` matches one of six forms, and a guard that matches none of them is
  refused. No form reaches a venue, which is how the other half -- no skip decided by whether the
  venue answers -- is held: by a closed set of shapes rather than by a reading of what a guard does.

THE SIX FORMS, each syntactic and each constraining what it may read: `path`, a presence method --
`exists`, `is_file`, `is_dir` -- taking no argument, on a literal-rooted receiver; `uid`,
`os.geteuid() == 0`; `binary`, `shutil.which('<literal>') is None`; `opt-in`, a read with no default
under a key that is a literal or a plain module constant, compared to a string literal, spelled
`<key> in os.environ`, or tested against a module-level constant collection of literals; `membership`,
a call-free literal-rooted expression tested against such a collection; and `registry`, a call into
`tests/skip_gates.py`.

The registry is where a gate whose reading has no form of its own declares it: `develop_resolves()`,
`no_binary(...)` and `nothing_found(...)` say at the call site what the skip is decided by. A form
that is a call into a sibling module is worth no more than that module, so
`test_the_registry_reads_nothing_a_form_could_not` holds it closed -- its imports, the names its calls
may reach, the one `git` it may launch, and the single `return` of every function it defines.

WHAT THIS FILE DOES NOT HOLD:

- gate DISCOVERY. The matcher judges the gates the walker finds, and any set this file computed to
  check that walk would be computed by the walker; the positions a skip can sit in are held against
  the fixture by `test_the_fixture_carries_every_position_a_skip_can_sit`, and a position the fixture
  does not carry is held by nothing;
- the provenance of a registry call's ARGUMENTS. `nothing_found(rows)` is the call site's claim that
  those rows were gathered locally, and no shape of the call can check it, so rows a venue answer
  filtered would decide a skip under a declaration that says otherwise. That is the one reading a gate
  may still carry unjudged.

From 2026-09-11 until this change the file was a REDUCER: it followed a call into our own code and
read what the helper it landed on reached, rather than matching the guard against a form. Its blind
spots were hand-counted four times, each count was wrong, and that is why a closed set of forms
replaced it.

The class had three names until T0190: `ZCRYPTO_VENUE_CONTRACT` and `ZCRYPTO_E1B_LIVE` implemented the
same rule under their own spellings, so an agent that set the one name it had been given got the other
two tests silently skipped. The owner ruled one flag for the class on 2026-09-09, the order-placing
probe included. Those two names are why `git grep` for them over `tests/ cli/ infra/ .claude/
CLAUDE.md` is not empty: the hits are this docstring. A guard that names what it forbids sits inside
its own corpus, and that is expected rather than a regression. What keeps it from reading ITSELF is
that the walker runs over gates and this file has none -- its shapes are held as source in a string,
which no parse of this module sees as code.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"

# The one opt-in, written out here and never learned from the tree: a guard that took the name from
# the files it checks would agree with whatever it found, including a fourth name.
OPT_IN = "ZCRYPTO_LIVE_VENUE_TESTS"

REGISTRY = TESTS / "skip_gates.py"
# The dotted name `_registry_call` keys on, derived from the path so the two cannot drift apart.
REGISTRY_MODULE = f"{TESTS.name}.{REGISTRY.stem}"
REGISTRY_IMPORTS = frozenset({"shutil", "subprocess", "pathlib", "typing"})
# The builtins the registry may call: NONE -- its three functions call only what their imports bind.
# An allowlist and not a blocklist of the importing ones, because no blocklist holds:
# `__import__("socket")` is an `ast.Call` and not an `ast.Import`, so the import allowlist below never
# sees it, and `globals()["__builtins__"]["__import__"]` reaches it without naming it.
REGISTRY_BUILTINS: frozenset[str] = frozenset()
# Every word `develop_resolves()`'s argv may carry, each of them a literal. `git` is itself a network
# client, so its name at argv[0] constrains nothing: `ls-remote`, `fetch` and a
# `-c protocol.ext.allow=<transport>` all reach a remote under it, and a skip would then be decided by
# whether that remote answers. The checkout the launch runs in is `cwd=REPO` and no word of the argv.
REGISTRY_GIT_ARGV = frozenset({"git", "rev-parse", "--verify", "--quiet", "develop"})


class Form(NamedTuple):
    """One recognised guard shape and, for the opt-in form, the key it read."""

    name: str
    key: str | None = None


class Gate(NamedTuple):
    """One skip site: where it is, the forms its guards matched, the opt-in keys those read, and what was refused."""

    line: int
    kind: str
    forms: tuple[Form, ...]
    env: tuple[str, ...]
    opaque: tuple[str, ...]
    guards: str


class Module(NamedTuple):
    """A parsed module and the two lookups a guard is read against: what its imports bind, and which
    names are the `os` module."""

    tree: ast.Module
    imported: dict[str, str]
    os_names: frozenset[str]
    label: str


def _imported(tree: ast.Module) -> dict[str, str]:
    """Each name bound by an import, mapped to the module it came from.

    Every arm that reads it asks for ONE module by name: `environ` and `getenv` from `os`, a name the
    registry bound, a name `unittest` bound (`_unittest_skip` asks it of a decorator's receiver and of
    a bare `skipIf`/`skipUnless`), and in `_rooted` a `pathlib` import, the one library whose names
    root an operand. `_rooted` refuses every other imported name -- what such a name holds is its own
    module's business, and no form here reads it.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.update({(a.asname or a.name): node.module for a in node.names})
        elif isinstance(node, ast.Import):
            # `import a.b` binds `a` and denotes `a`; only an `as` binds the dotted module itself.
            out.update({(a.asname or a.name.split(".")[0]): (a.name if a.asname else a.name.split(".")[0]) for a in node.names})
    return out


def _os_aliases(tree: ast.Module) -> frozenset[str]:
    """Names bound to the `os` module. `import os as o` then `o.environ.get(K)` is an environment read,
    and a receiver test spelled as the literal text `os.environ` does not see it -- measured as a
    regression against an earlier shape of this file that tested the text's SUFFIX instead."""
    return frozenset(
        {(a.asname or a.name) for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names if a.name == "os"} | {"os"}
    )


@functools.cache
def _module(path: Path) -> Module:
    """A module of ours, parsed once. Cached because one helper module is imported by several."""
    return _module_of(path.read_text(), str(path.relative_to(REPO)))


def _module_of(source: str, label: str) -> Module:
    tree = ast.parse(source, label)
    return Module(tree=tree, imported=_imported(tree), os_names=_os_aliases(tree), label=label)


_PRESENCE = ("exists", "is_file", "is_dir")
_ENV_READS = ("get", "getenv")
_REFUSAL_REMEDY = (
    "write the guard as a presence check whose RECEIVER is LITERAL-ROOTED -- a `Path('<literal>')` "
    "chain, a `/` join whose EVERY operand is one, or a name bound once, at this module's top level "
    "or in this function, to one of those -- `os.geteuid() == 0`, `shutil.which('<name>') is None`, "
    "a read of the one opt-in under a literal or plain module-constant key and with NO default, "
    "COMPARED to a string literal, spelled `<key> in os.environ`, or tested against a module-level "
    "constant collection of literals, membership of a CALL-FREE literal-rooted expression in such a "
    "collection, or a call into tests/skip_gates.py -- `no_binary(...)` under `from tests.skip_gates "
    "import no_binary`, or `<name>.no_binary(...)` under `from tests import skip_gates` or `import "
    "tests.skip_gates as <name>`. Do NOT hoist the receiver's call to the line above: the binding is "
    "read by the same predicate. And a call that reaches a VENUE is neither hoisted nor declared -- "
    "a reachability probe fails a test, it never skips it"
)


def _assignments(name: str, module: Module) -> list[ast.AST]:
    """Every `Store` of `name` anywhere in the module, so a plain constant is one that is bound once."""
    return [n for n in ast.walk(module.tree) if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)]


def _plain_literal(name: str, module: Module) -> str | None:
    """`NAME = "<literal>"` at the module's top level, bound nowhere else (spec 00114 D2)."""
    if len(_assignments(name, module)) != 1:
        return None
    for node in module.tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            value = node.value
            return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None
    return None


def _plain_collection(name: str, module: Module) -> bool:
    """`NAME = (...)`, `[...]`, `{...}` or `frozenset({...})` of literals at the top level, bound once."""
    if len(_assignments(name, module)) != 1:
        return False
    for node in module.tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in ("frozenset", "set", "tuple")
                and len(value.args) == 1
            ):
                value = value.args[0]
            return isinstance(value, (ast.Tuple, ast.List, ast.Set)) and all(isinstance(e, ast.Constant) for e in value.elts)
    return False


def _key(node: ast.AST, module: Module) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return _plain_literal(node.id, module)
    return None


def _is_environ(node: ast.AST, module: Module) -> bool:
    """`os.environ` under any name the module binds `os` to, or `environ` imported from os under its
    own name (`_imported` keeps the bound name only, so `from os import environ as e` is refused)."""
    if isinstance(node, ast.Attribute) and node.attr == "environ" and isinstance(node.value, ast.Name):
        return node.value.id in module.os_names
    return isinstance(node, ast.Name) and node.id == "environ" and module.imported.get("environ") == "os"


def _env_read_key(node: ast.AST, module: Module) -> ast.AST | None:
    """The key of `os.environ.get(K)`, `os.getenv(K)`, `environ.get(K)`, `getenv(K)` or `os.environ[K]`
    -- of a read with NO default, positional or keyword: the key is `args[0]` and a default is read by
    nothing, so `os.environ.get(K, _venue_up())` would be a venue call written inside a form whose
    reading this matcher declares fixed -- the whole-call pinning `_match` requires of every arm that
    judges a call at the gate."""
    if isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _ENV_READS:
            if _is_environ(func.value, module) or (isinstance(func.value, ast.Name) and func.value.id in module.os_names):
                return node.args[0]
        if isinstance(func, ast.Name) and func.id == "getenv" and module.imported.get("getenv") == "os":
            return node.args[0]
    if isinstance(node, ast.Subscript) and _is_environ(node.value, module):
        return node.slice
    return None


def _bound_to_module(module: Module, dotted: str) -> frozenset[str]:
    """Every name this module binds to the MODULE `dotted` by import and rebinds nowhere:
    `import <dotted> as n`, and `from <package> import <leaf>` under its own name or an alias -- this
    suite's idiom for a `tests/` helper. `_imported` keys on the bound name and maps the `from`
    spelling to the PACKAGE, so a receiver that names a module is resolved here instead: a plain
    `import tests.skip_gates` binds `tests`, which is the package and not the registry, and yields
    nothing. An import any `Store` of that name rebinds yields nothing either, at any scope --
    nothing here tracks scopes, so a local of that name in an unrelated function is enough: the
    once-bound discipline `_plain_literal` applies to a key, applied to a module over the same
    whole-tree walk. `_bindings` is what asks it, so every binding form the language has counts -- a
    `def`, a `class`, a second `import ... as` and a plain assignment alike -- with an attribute
    assignment on the name counted beside them, the one takeover that leaves a name single-bound: the
    import is the ONE binding a blessed name may carry, and the store is what a blessed call would
    otherwise have run. A rebound name falls to `no form matches`, whose remedy
    prints the spelling the author already wrote."""
    package, _, leaf = dotted.rpartition(".")
    bound: set[str] = set()
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ImportFrom) and node.module == package:
            bound |= {a.asname or a.name for a in node.names if a.name == leaf}
        elif isinstance(node, ast.Import):
            bound |= {a.asname for a in node.names if a.asname and a.name == dotted}
    return frozenset(n for n in bound if len(_bindings(n, module.tree)) == 1)


def _stores(target: ast.AST, name: str) -> bool:
    """Whether this binding target binds `name` -- the Name under it whose context is a `Store`."""
    return any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store) for n in ast.walk(target))


def _bindings(name: str, where: ast.AST) -> list[ast.AST | str]:
    """Every binding of `name` in `where` -- a module, or the gate's own function.

    A plain assignment contributes the EXPRESSION it binds, which `_rooted` then judges by the same
    predicate. Every other binding form contributes the words of its own refusal, because what it
    binds is not an expression this file can read; the arms below are every binding Python has beside
    the plain one, so a name reaching `_rooted` is either judged or refused and never missed: a
    parameter, a `for` or comprehension target, a `with ... as`, an `except ... as`, an import, a
    `def`, a `class`, an augmented assignment, a `global` or `nonlocal` declaration, an unpacking
    target, and a `match` capture. One arm is no binding at all: an attribute assignment on the name,
    `<name>.<attr> = ...`, which rebinds nothing and so is invisible to any once-bound test while
    being exactly what a read off that name then answers with -- `skip_gates.no_binary = _venue_up`
    at a registry receiver, `ROOT.child = _venue()` at a path one. It is the ONE takeover of a
    single-bound name this walk reads; a takeover spelled some other way is not a shape this file
    sees. `_assignments` counts the STORES of a name anywhere in the module,
    which is the once-bound test `_plain_literal` rides on; this answers the other question, what the
    ONE scope that binds a name binds it to, so a local bound once inside its own function is not
    refused for a namesake in another. Asked over `module.tree` it answers the once-bound question as
    well, and over every binding form rather than over `Store` nodes alone -- which is what
    `_registry_call` and `_bound_to_module` ask of a registry name, a `def`, a `class` and an import
    each creating no `Store` for `_assignments` to find.
    """
    out: list[ast.AST | str] = []
    for node in ast.walk(where):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out += [node.value] if target.id == name else []
                elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == name:
                    out.append("an attribute assignment on it")
                elif _stores(target, name):
                    out.append("an unpacking target")
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                out.append(node.value)
        elif isinstance(node, ast.AugAssign) and _stores(node.target, name):
            out.append("an augmented assignment")
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)) and _stores(node.target, name):
            out.append("a `for` target")
        elif isinstance(node, ast.withitem) and node.optional_vars is not None and _stores(node.optional_vars, name):
            out.append("a `with ... as` binding")
        elif isinstance(node, ast.ExceptHandler) and node.name == name:
            out.append("an `except ... as` binding")
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and any((a.asname or a.name.split(".")[0]) == name for a in node.names):
            out.append("an import")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            out.append("a `def` or a `class`")
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            out.append("a `global` or `nonlocal` declaration")
        elif isinstance(node, ast.arg) and node.arg == name:
            out.append("a parameter")
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == name:
            out.append("a `match` capture")
        elif isinstance(node, ast.MatchMapping) and node.rest == name:
            out.append("a `match` capture")
    return out


def _rooted(node: ast.AST, module: Module, function: ast.AST | None, seen: frozenset[str] = frozenset()) -> str | None:
    """`None` when this expression is LITERAL-ROOTED, else the OPERAND that is not (spec 00114 D2).

    ONE predicate, applied to every operand of an expression exactly as it is applied to the
    expression: a literal, `__file__`, a name this module imported from `pathlib`, or a name bound
    exactly once -- in the gate's own function, else at the module's top level, and by a plain
    assignment -- to another expression it accepts. An attribute, a subscript, a `/` join and a call
    are accepted only when every operand under them is, so a call's callee AND its arguments are
    judged, which refuses every call but a `pathlib` chain over operands this accepts and refuses an
    environment read anywhere inside as the import `os` or `environ` is. That is `_plain_literal`'s
    discipline given to a receiver instead of a key: it is what stops `marker = _venue_reads()` one
    line above the gate from reading as the local it is written as, and what stops
    `ROOT / _venue_name()` written at the gate, or bound a line above it, from reading as a path.
    There is no operand it passes over, which is the whole of it: a rule that rooted the chain alone
    made hoisting the call into a binding the working repair for its own refusal. Every refusal names
    what it saw, so the message says WHICH operand; `seen` refuses a name bound through itself rather
    than following it round.
    """
    if isinstance(node, ast.Constant):
        return None
    if isinstance(node, ast.Attribute):
        return _rooted(node.value, module, function, seen)
    if isinstance(node, ast.Subscript):
        return _rooted(node.value, module, function, seen) or _rooted(node.slice, module, function, seen)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _rooted(node.left, module, function, seen) or _rooted(node.right, module, function, seen)
    if isinstance(node, ast.Call):
        parts = [node.func, *node.args, *(k.value for k in node.keywords)]
        return next((why for why in (_rooted(p, module, function, seen) for p in parts) if why is not None), None)
    if not isinstance(node, ast.Name):
        return f"{ast.unparse(node)}, which is not an operand this predicate reads"
    if node.id == "__file__" or module.imported.get(node.id, "").split(".")[0] == "pathlib":
        return None
    if node.id in module.imported:
        return f"{node.id}, imported from {module.imported[node.id]}"
    if node.id in seen:
        return f"{node.id}, bound through itself"
    found = _bindings(node.id, function) if function is not None else []
    where = function.name if found else module.label
    found = found or _bindings(node.id, module.tree)
    if not found:
        return f"{node.id}, which no assignment in {module.label} binds"
    if len(found) > 1:
        return f"{node.id}, bound {len(found)} times in {where}"
    if isinstance(found[0], str):
        return f"{node.id}, {found[0]} of {where}"
    return _rooted(found[0], module, function, seen | {node.id})


def _registry_call(node: ast.Call, module: Module) -> bool:
    """Whether this call reaches `tests/skip_gates.py` (spec 00114 D3): a name imported from it, or an
    attribute on a name bound to the module. BOTH spellings require the registry's import to be the
    name's ONE binding, which `_bindings` answers over every binding form the language has: a
    module-level `no_binary = lambda n: venue_up()`, a `def no_binary`, a `class no_binary` and a
    second `import ... as` of the receiver are each a rebinding and not a declaration, and each is
    the binding Python runs where the import is the one this file would have read;
    `<receiver>.no_binary = venue_up` is refused beside them although it rebinds nothing, because an
    attribute assignment on the receiver is what the call runs while the name stays single-bound. The dict lookup
    stays in front of `_bindings`, which walks the whole module: only a name the import bound pays
    for that walk."""
    func = node.func
    if isinstance(func, ast.Name):
        return module.imported.get(func.id) == REGISTRY_MODULE and len(_bindings(func.id, module.tree)) == 1
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in _bound_to_module(module, REGISTRY_MODULE)
    )


def _opt_in(key_node: ast.AST, module: Module) -> list[Form] | str:
    key = _key(key_node, module)
    if key is None:
        return f"an environment key that is not a literal or a plain module constant: {ast.unparse(key_node)}"
    return [Form("opt-in", key)]


def _match(guard: ast.AST, module: Module, function: ast.AST | None) -> list[Form] | str:
    """The forms this guard is made of, or why it is refused (spec 00114 D1-D3).

    No arm below matches a CALL whose shape it has not pinned -- the positional count exact,
    `keywords` empty, a splat resolving to nothing a form can read -- because a form declares what it
    reads and an argument nothing judges is where a venue read sits: `shutil.which('bash',
    path=_nas_bin())` reads a mount and not PATH. The registry arm is the one exception, by design:
    its argument is the claim the call site makes, which no shape of it can check (spec 00114 D3).
    The two arms whose OPERAND rather than whose callee carries the reading take `function` as well,
    the function the gate sits in, because a name in an operand is judged at its binding and a local
    binds in there (`_rooted`)."""
    node = guard
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node = node.operand
    if isinstance(node, ast.BoolOp):
        forms: list[Form] = []
        for value in node.values:
            got = _match(value, module, function)
            if isinstance(got, str):
                return got
            forms.extend(got)
        return forms
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _PRESENCE
        and not node.args
        and not node.keywords
    ):
        stray = _rooted(node.func.value, module, function)
        if stray is None:
            return [Form("path")]
        return f"a path-presence method whose receiver is not literal-rooted -- {stray}: {ast.unparse(guard)!r}"
    if isinstance(node, ast.Call) and _registry_call(node, module):
        return [Form("registry")]
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, op, right = node.left, node.ops[0], node.comparators[0]
        if (
            isinstance(op, ast.Eq)
            and isinstance(left, ast.Call)
            and not left.args
            and not left.keywords
            and ast.unparse(left.func) in {f"{n}.geteuid" for n in module.os_names}
        ):
            if isinstance(right, ast.Constant) and right.value == 0:
                return [Form("uid")]
        if isinstance(op, ast.Is) and isinstance(right, ast.Constant) and right.value is None and isinstance(left, ast.Call):
            if (
                ast.unparse(left.func) == "shutil.which"
                and len(left.args) == 1
                and isinstance(left.args[0], ast.Constant)
                and not left.keywords
            ):
                return [Form("binary")]
        if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(right, ast.Constant) and isinstance(right.value, str):
            key_node = _env_read_key(left, module)
            if key_node is not None:
                return _opt_in(key_node, module)
        if isinstance(op, (ast.In, ast.NotIn)) and _is_environ(right, module):
            return _opt_in(left, module)
        if isinstance(op, (ast.In, ast.NotIn)) and isinstance(right, ast.Name) and _plain_collection(right.id, module):
            key_node = _env_read_key(left, module)
            if key_node is not None:
                return _opt_in(key_node, module)
            stray = _rooted(left, module, function)
            if stray is not None:
                return f"a membership test whose left operand is not literal-rooted -- {stray}: {ast.unparse(guard)!r}"
            return [Form("membership")]
    return f"no form matches {ast.unparse(guard)!r}"


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
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        named = isinstance(value, ast.Attribute) and value.attr == attribute and ast.unparse(value.value) in modules
        # `_b = functools.partial(pytest.skip, ...)` binds it as surely as `_skip = pytest.skip` does,
        # and the call site then names neither pytest nor the attribute.
        wrapped = (
            isinstance(value, ast.Call)
            and ast.unparse(value.func).endswith("partial")
            and bool(value.args)
            and isinstance(value.args[0], ast.Attribute)
            and value.args[0].attr == attribute
            and ast.unparse(value.args[0].value) in modules
        )
        if named or wrapped:
            bound |= {x.id for x in node.targets if isinstance(x, ast.Name)}
    return bound


def _pytest_modules(tree: ast.Module) -> set[str]:
    """Names bound to the pytest MODULE. `import pytest as pt` then `pt.skip(...)` is a skip, and a
    receiver test spelled as the literal text `pytest` does not see it."""
    return {
        (a.asname or a.name) for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names if a.name == "pytest"
    } or {"pytest"}


_UNITTEST_SKIPS = ("skipIf", "skipUnless")


def _unittest_skip(func: ast.AST, module: Module) -> bool:
    """`skipIf`/`skipUnless` reached through `unittest` under any name it is bound to, or imported from
    it under any name -- the alias tolerance `_pytest_modules` and `_pytest_bindings` give pytest's
    spellings. `_imported` keeps the BOUND name and loses the imported one, so the bare form is
    resolved off the import nodes through `_bound_to_module` (spec 00114 Task 3) rather than that dict:
    `from unittest import skipIf as skip_if` is a fourth spelling of the construct, and a name bound
    to anything else is not one of them. `module.imported` is asked first and answers in one lookup:
    every name the walk below can bless is one that dict maps to `unittest`, and this function runs
    for every bare-name call in every module walked."""
    if isinstance(func, ast.Attribute) and func.attr in _UNITTEST_SKIPS:
        return isinstance(func.value, ast.Name) and module.imported.get(func.value.id) == "unittest"
    if not (isinstance(func, ast.Name) and module.imported.get(func.id) == "unittest"):
        return False
    return any(func.id in _bound_to_module(module, f"unittest.{n}") for n in _UNITTEST_SKIPS)


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
    """Whether this node reaches pytest's `<attribute>`: an attribute of the module under any alias,
    `<alias>.mark.<attribute>` applied conditionally, a bare name the module imported or assigned it or
    bound it through `functools.partial`, `getattr(<alias>, "<attribute>")`, `raise
    pytest.<attribute>.Exception` and `raise unittest.SkipTest`.

    `unittest` is in scope through two arms outside this function: `self.skipTest(...)` is a skip
    here, recognised on the receiver `self` alone, while `skipIf`/`skipUnless` are gates through
    `_gates`' third arm rather than through this one."""
    if isinstance(node, ast.Raise) and node.exc is not None:
        raised = ast.unparse(node.exc.func if isinstance(node.exc, ast.Call) else node.exc)
        # `raise pytest.skip.Exception` and `raise unittest.SkipTest` are the two raised spellings.
        return raised.endswith(f"{attribute}.Exception") or (attribute == "skip" and raised.endswith("SkipTest"))
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == attribute:
        receiver = ast.unparse(func.value)
        if receiver in modules:
            return True
        # `pytest.mark.skip(...)` is a skip too. Applied unconditionally as a decorator it has no
        # guards and yields no gate, which is right; applied inside an `if` -- a collection hook doing
        # `item.add_marker(pytest.mark.skip(...))` is the shape -- that `if` is its guard. Without this
        # the gate is never FOUND, and the one-name assertion only ranges over gates that are.
        base, _, tail = receiver.rpartition(".")
        return tail == "mark" and base in modules
    if isinstance(func, ast.Name) and func.id in bound:
        return True
    # `getattr(pytest, "skip")(...)` and `functools.partial(pytest.skip, ...)` reach the same function
    # through two indirections the attribute test cannot see. Both name it in an argument.
    if isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) == 2:
        holder, name = node.args
        return ast.unparse(holder) in modules and isinstance(name, ast.Constant) and name.value == attribute
    if ast.unparse(func).endswith("partial") and node.args:
        return _is_pytest_call(ast.Call(func=node.args[0], args=[], keywords=[]), attribute, bound, modules)
    if isinstance(func, ast.Attribute) and func.attr == "skipTest" and isinstance(func.value, ast.Name) and func.value.id == "self":
        return attribute == "skip"
    return False


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    """The function a skip site sits in, whose local bindings its guards may read."""
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
    return None


def _gate(line: int, kind: str, guards: list[ast.AST], module: Module, function: ast.AST | None, extra=()) -> Gate:
    forms: list[Form] = []
    refusals: list[str] = list(extra)
    for guard in guards:
        got = _match(guard, module, function)
        (refusals.append if isinstance(got, str) else forms.extend)(got)
    return Gate(
        line=line,
        kind=kind,
        forms=tuple(forms),
        env=tuple(sorted({f.key for f in forms if f.name == "opt-in" and f.key is not None})),
        opaque=tuple(refusals),
        guards=" ; ".join(ast.unparse(g) for g in guards)[:300],
    )


def _gates(source: str, label: str = "<fixture>", path: Path | None = None) -> list[Gate]:
    """Every gate in this module whose guards decide a `pytest.skip()`.

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
    bound = _pytest_bindings(module.tree, "skip")
    modules = _pytest_modules(module.tree)
    bound |= _skip_helpers(module.tree, "skip", bound, modules, parents)
    out: list[Gate] = []
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.skipif"):
            raw = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "condition"), None)
            if raw is not None:
                condition, extra = _as_expression(raw)
                out.append(_gate(node.lineno, "skipif", [condition], module, None, extra))
        elif isinstance(node, ast.Call) and _unittest_skip(node.func, module):
            raw = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "condition"), None)
            if raw is not None:
                condition, extra = _as_expression(raw)
                out.append(_gate(node.lineno, "skipif", [condition], module, None, extra))
        elif _is_pytest_call(node, "skip", bound, modules):
            guards = _guards_of(node, parents)
            if guards:
                out.append(_gate(node.lineno, "skip-site", guards, module, _enclosing_function(node, parents)))
    return out


def _labelled(gates: list[Gate], label: str) -> list[tuple[str, Gate]]:
    """Gates from one source, tagged for the failure message. A fixture's gates are labelled too, so
    the assertions below run the SAME predicate over the tree and over the shapes that must trip it."""
    return [(label, gate) for gate in gates]


def _second_flags(labelled: list[tuple[str, Gate]]) -> list[tuple[str, Gate, str]]:
    """Every environment key a skip gate reads that is not the one opt-in."""
    return [(label, gate, name) for label, gate in labelled for name in gate.env if name != OPT_IN]


def _unreadable(labelled: list[tuple[str, Gate]]) -> list[tuple[str, Gate]]:
    """Every skip gate decided by something this file could not read."""
    return [(label, gate) for label, gate in labelled if gate.opaque]


def _tree_gates() -> list[tuple[str, Gate]]:
    """Every gate in `tests/`, labelled by file. Asserts the walk saw something: a broken walker must
    fail here rather than pass every assertion below it vacuously."""
    modules = sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)
    assert modules, "walked no test modules -- the glob is broken, not the tree clean"
    out = [(str(p.relative_to(REPO)), gate) for p in modules for gate in _gates("", str(p.relative_to(REPO)), path=p)]
    assert out, f"walked {len(modules)} test modules and found no skip gate -- the walker is broken"
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


def test_every_skip_gate_in_tests_matches_a_form():
    """A guard is one of six forms or it is refused (spec 00114 D1). The forms are the only things a
    skip may be decided by and none of them reaches a venue: that is how the rule's second half -- no
    skip decided by whether the venue answers -- is held, by a closed set rather than by a reading."""
    unmatched = [(label, gate, why) for label, gate in _unreadable(_tree_gates()) for why in gate.opaque]
    assert not unmatched, "\n".join(
        f"{label}:{gate.line} [{gate.kind}] {why}: {gate.guards} -- {_REFUSAL_REMEDY}" for label, gate, why in unmatched
    )


def test_the_tree_holds_the_control_that_keeps_the_one_name_assertion_falsifiable():
    """The one-name assertion passes on an empty set, so it needs a live counter-shape: a skip gate
    that reads no environment at all and must keep passing. Most of the tree's gates are that shape;
    take the split from a run. What this holds is the EMPTY-set degeneracy alone -- a matcher that read
    the opt-in at every gate would leave `plain` empty and fail here. The other direction, a matcher
    that refused every gate, leaves `plain` untouched and is held by
    `test_every_skip_gate_in_tests_matches_a_form` instead."""
    plain = [(label, gate) for label, gate in _tree_gates() if not gate.env]
    assert plain, "every skip gate in tests/ reads the environment -- the one-name assertion has no control"


def _call_root(node: ast.AST) -> str:
    """The name a call reaches through, as text for a refusal message: `shutil` in
    `shutil.which(...)`, `Path` in `Path(x).resolve()`. A chained call is judged by what it started
    from rather than by its first dotted segment, so the walk goes left through an attribute, a call,
    a subscript and a `/` join to the leftmost operand."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)) or (
        isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ):
        node = node.func if isinstance(node, ast.Call) else node.left if isinstance(node, ast.BinOp) else node.value
    return node.id if isinstance(node, ast.Name) else ast.unparse(node)


def test_the_registry_reads_nothing_a_form_could_not():
    """A call into `tests/skip_gates.py` is a form (spec 00114 D3), so the module is held closed: its
    imports are within the four named, every call reaches a name one of those imports binds or a
    builtin it is allowlisted for, the one process it may launch is a `git` every word of whose argv
    is a literal on the allowlist -- the checkout it runs in is handed to `cwd`, never written as a
    word -- and every function it defines anywhere -- private ones too -- is one `return`. A registry
    that could open a socket would be the reducer's leak, one file over -- and `subprocess` is on the
    allowlist, so the launch and the walk are what close that direction."""
    tree = ast.parse(REGISTRY.read_text(), str(REGISTRY))
    bound = {
        (alias.asname or alias.name).split(".")[0]: (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    imported = set(bound.values())
    assert imported <= REGISTRY_IMPORTS, f"the registry imports {sorted(imported - REGISTRY_IMPORTS)}"
    calls = [call for call in ast.walk(tree) if isinstance(call, ast.Call)]
    roots = {_call_root(call.func) for call in calls}
    allowed = set(bound) | REGISTRY_BUILTINS
    assert roots <= allowed, f"the registry calls {sorted(roots - allowed)}"
    for call in calls:
        if bound.get(_call_root(call.func)) != "subprocess":
            continue
        argv = call.args[0] if call.args else None
        launched = (
            isinstance(argv, ast.List) and argv.elts and isinstance(argv.elts[0], ast.Constant) and argv.elts[0].value == "git"
        )
        assert launched, f"a process launch that is not git: {ast.unparse(call)}"
        literals = all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in argv.elts)
        assert literals, f"a git argv word that is not a string literal: {ast.unparse(argv)}"
        words = {e.value for e in argv.elts}
        assert words <= REGISTRY_GIT_ARGV, f"a git that may leave this repo: {sorted(words - REGISTRY_GIT_ARGV)}"
    defined = [f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    public = {f.name for f in defined if not f.name.startswith("_")}
    assert public == {"develop_resolves", "no_binary", "nothing_found"}, f"the registry's public functions are {sorted(public)}"
    for f in defined:
        body = [s for s in f.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        assert len(body) == 1 and isinstance(body[0], ast.Return), f"{f.name} is more than one return"


# Every shape the two assertions must catch and every shape they must not, as source rather than as
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


from tests.skip_gates import no_binary
import tests.skip_gates as declared
from tests import skip_gates
import tests.skip_gates
from os import environ
from tests.basket_fixture import *

ANNOTATED: str = "ZCRYPTO_SOMETHING_ELSE"
if True:
    IN_IF = "ZCRYPTO_SOMETHING_ELSE"
try:
    IN_TRY = "ZCRYPTO_SOMETHING_ELSE"
except NameError:
    IN_TRY = ""
_LITERAL_LOCAL_ROOT = Path("data") / "snapshots"
_DOWN_STATES = ("maintenance", "cancel_only")
_TRUTHY = ("1", "true")
_SKIPPABLE = ("data", "scratch")


class _Keyed:
    KEY = "ZCRYPTO_SOMETHING_ELSE"

    def test_gated_on_a_second_flag_whose_key_is_an_attribute(self):
        if os.environ.get(self.KEY) != "1":
            pytest.skip("a key read off an attribute is not the plain form")


def _skip_unless_opted():
    if os.environ.get(OTHER) != "1":
        pytest.skip("the read is inside the skip helper, not at the call site")


def _live():
    return os.environ.get(OTHER) == "1"


def _skip_unless_live():
    if not _live():
        pytest.skip("the skip helper reads through a second helper")


def test_gated_on_the_registry_by_name():
    if no_binary("jq"):
        pytest.skip("the registry is the one helper a guard may call")


def test_gated_on_the_registry_by_module():
    if declared.no_binary("jq"):
        pytest.skip("the module spelling of the same call")


def test_gated_on_the_registry_through_the_package():
    if skip_gates.no_binary("jq"):
        pytest.skip("`from tests import skip_gates` is this suite's idiom for a tests/ helper")


def test_skips_on_a_sibling_reached_through_the_package_name():
    if tests.venue_is_up():
        pytest.skip("a plain `import tests.skip_gates` binds the PACKAGE, not the registry")


def test_skips_on_a_presence_read_of_what_a_call_returned():
    if not _venue_answers().exists():
        pytest.skip("a presence method on a call's result reads the call, not the filesystem")


def test_gated_on_a_second_flag_read_inside_the_skip_helper():
    _skip_unless_opted()


def test_gated_on_a_second_flag_two_helpers_from_the_condition():
    _skip_unless_live()


def test_gated_on_a_second_flag_through_an_annotated_constant():
    if os.environ.get(ANNOTATED) != "1":
        pytest.skip("an annotated assignment is not the plain form")


def test_gated_on_a_second_flag_through_a_constant_bound_under_an_if():
    if os.environ.get(IN_IF) != "1":
        pytest.skip("a binding under an `if` is not top level")


def test_gated_on_a_second_flag_through_a_constant_bound_under_a_try():
    if os.environ.get(IN_TRY) != "1":
        pytest.skip("a binding under a `try` is not top level either")


def test_gated_on_a_second_flag_whose_key_arrived_by_star_import():
    if os.environ.get(STARRED) != "1":
        pytest.skip("a name this module never binds cannot be a plain constant")


def test_gated_on_a_second_flag_through_environ_imported_by_name():
    if environ.get(OTHER) != "1":
        pytest.skip("`from os import environ` is the mapping under its own name")


def test_skips_on_a_membership_of_what_a_call_returned():
    if _venue_answers() in _DOWN_STATES:
        pytest.skip("membership names an operator, so its left operand is where a venue read hides")


def test_gated_on_a_second_flag_read_by_membership_in_a_constant():
    if os.environ.get(OTHER) not in _TRUTHY:
        pytest.skip("an environment read on the left is the opt-in form, key and all")


def test_gated_on_a_membership_of_a_module_constant():
    if ROOT.name in _SKIPPABLE:
        pytest.skip("a call-free left operand against a module-level constant collection")


def test_skips_on_a_presence_read_hoisted_to_the_line_above():
    marker = _venue_answers()
    if not marker.exists():
        pytest.skip("hoisting the call off the receiver does not make the receiver a path")


def test_gated_on_a_local_bound_once_to_a_literal_path():
    local = _LITERAL_LOCAL_ROOT / "kraken-refdata.json"
    if not local.exists():
        pytest.skip("a local bound once to a literal-rooted path is the accepting direction")


def test_skips_on_a_presence_read_of_a_fixture_parameter(tmp_path):
    if not tmp_path.exists():
        pytest.skip("a parameter is a value this file never sees bound")


def test_skips_on_a_presence_read_of_an_imported_root():
    if not basket_fixture.exists():
        pytest.skip("an imported name is not followed across a module boundary")


from tests.skip_gates import develop_resolves, nothing_found
import tests.skip_gates as shadowed
import tests.skip_gates as rebound
import json as rebound
import tests.skip_gates as stored
from tests import skip_gates as also_stored

develop_resolves = _venue_answers
stored.no_binary = _venue_answers
also_stored.nothing_found = _venue_answers


def nothing_found(rows):
    return _venue_answers()


class shadowed:
    @staticmethod
    def answers(name):
        return _venue_answers()


def test_skips_on_a_registry_name_a_def_shadows():
    if nothing_found(ROOT.iterdir()):
        pytest.skip("a `def` over the registry's own import is the binding Python runs")


def test_skips_on_a_registry_name_an_assignment_rebinds():
    if not develop_resolves():
        pytest.skip("an assignment over that import is a rebinding too")


def test_skips_on_a_registry_module_a_class_shadows():
    if shadowed.answers("jq"):
        pytest.skip("a `class` of the receiver's name rebinds the module")


def test_skips_on_a_registry_module_a_second_import_rebinds():
    if rebound.no_binary("jq"):
        pytest.skip("a second `import ... as` names another module under the same name")


def test_skips_on_a_registry_module_an_attribute_store_takes_over():
    if stored.no_binary("jq"):
        pytest.skip("an attribute assignment on the module rebinds no name and is what the call runs")


def test_skips_on_a_registry_module_an_attribute_store_takes_over_the_other_spelling():
    if also_stored.nothing_found(ROOT.iterdir()):
        pytest.skip("the same takeover written at the other module spelling")


import unittest.mock
import unittest as ut
from unittest import skipUnless
from unittest import skipIf as skip_if


class TestOld(unittest.TestCase):
    @unittest.skipIf(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator(self):
        pass

    @unittest.skipIf(condition=not ROOT.exists(), reason="no data")
    def test_gated_by_a_unittest_decorator_whose_condition_is_a_keyword(self):
        pass

    @skipUnless(ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_imported_by_name(self):
        pass

    @skip_if(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_imported_under_an_alias(self):
        pass

    @ut.skipIf(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_through_a_module_alias(self):
        pass

    def test_gated_by_a_unittest_method(self):
        if not ROOT.exists():
            self.skipTest("no data")
"""

_FIXTURE_GATES = _labelled(_gates(_FIXTURE), "fixture")


# Every function the fixture defines, methods included, each spanned from its FIRST DECORATOR: a
# `skipif` mark's gate line is the decorator's, which sits above the `def`, so a span starting at
# `FunctionDef.lineno` matches none of the fixture's decorator-written gates.
_FIXTURE_FUNCTIONS = [f for f in ast.walk(ast.parse(_FIXTURE)) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _fixture_span(f: ast.AST) -> tuple[int, int]:
    return (f.decorator_list[0].lineno if f.decorator_list else f.lineno), f.end_lineno


def _fixture_case(gate: Gate) -> str:
    """The fixture function a gate sits in, so a disposition can be asserted by the case's name."""
    found = next((f.name for f in _FIXTURE_FUNCTIONS if _fixture_span(f)[0] <= gate.line <= _fixture_span(f)[1]), None)
    assert found is not None, f"fixture gate at line {gate.line} sits in no function: {gate.guards}"
    return found


def _fixture(name: str) -> Gate:
    hits = [g for _, g in _FIXTURE_GATES if _fixture_case(g) == name]
    assert len(hits) == 1, f"{name}: {len(hits)} gates"
    return hits[0]


# Every spelling of a second opt-in the fixture carries, each caught by exactly one of the two tree
# assertions: NAMED, the matcher read the second key and the one-name assertion refuses it; REFUSED,
# no form matched and the every-gate-matches assertion refuses it.
_SECOND_FLAG_NAMED = (
    "test_gated_on_a_second_flag",
    "test_gated_on_a_second_flag_through_marks",
    "test_gated_on_a_second_flag_written_as_a_string",
    "test_gated_on_a_second_flag_read_by_subscript",
    "test_gated_on_a_second_flag_read_by_bare_getenv",
    "test_gated_on_a_second_flag_read_by_membership",
    "test_gated_on_a_second_flag_through_a_module_alias",
    "test_skips_through_a_name_bound_to_pytests_skip",
    "test_skips_through_the_bare_name_imported_from_pytest",
    "test_gated_on_a_second_flag_through_environ_imported_by_name",
    "test_gated_on_a_second_flag_read_by_membership_in_a_constant",
    "_skip_unless_opted",
)
_SECOND_FLAG_REFUSED = (
    "test_gated_on_a_second_flag_one_call_away_from_the_condition",
    "test_gated_on_a_second_flag_a_function_handed_back",
    "test_gated_on_a_second_flag_held_on_one_of_our_classes",
    "test_gated_on_a_second_flag_read_through_an_alias_of_the_mapping",
    "test_gated_on_a_second_flag_read_through_a_copy_of_the_mapping",
    "test_gated_on_a_computed_key",
    "test_gated_on_a_constant_a_function_rebinds",
    "test_gated_on_a_second_flag_through_an_annotated_constant",
    "test_gated_on_a_second_flag_through_a_constant_bound_under_an_if",
    "test_gated_on_a_second_flag_through_a_constant_bound_under_a_try",
    "test_gated_on_a_second_flag_whose_key_is_an_attribute",
    "test_gated_on_a_second_flag_whose_key_arrived_by_star_import",
    "_skip_unless_live",
)
_REACHABILITY_REFUSED = (
    "test_skips_through_a_reachability_helper",
    "test_skips_on_a_reachability_read_written_inline",
    "test_skips_below_the_condition_rather_than_directly_under_it",
    "test_skips_in_the_else_rather_than_the_body",
    "test_skips_in_an_except_handler_with_no_condition_anywhere",
    "test_skips_on_a_probe_reached_through_a_class",
    "test_skips_on_a_probe_reached_through_an_instance",
    "test_skips_from_a_match_subject_with_no_condition_anywhere",
    "test_gated_on_a_module_of_ours_that_resolves",
    "test_gated_on_a_module_of_ours_that_cannot_be_read",
    "test_gated_on_a_helper_this_file_cannot_read",
    "test_skips_on_a_sibling_reached_through_the_package_name",
    "test_skips_on_a_presence_read_of_what_a_call_returned",
    "test_skips_on_a_membership_of_what_a_call_returned",
    "test_skips_on_a_presence_read_hoisted_to_the_line_above",
    "test_skips_on_a_presence_read_of_a_fixture_parameter",
    "test_skips_on_a_presence_read_of_an_imported_root",
    "test_skips_on_a_registry_name_a_def_shadows",
    "test_skips_on_a_registry_name_an_assignment_rebinds",
    "test_skips_on_a_registry_module_a_class_shadows",
    "test_skips_on_a_registry_module_a_second_import_rebinds",
    "test_skips_on_a_registry_module_an_attribute_store_takes_over",
    "test_skips_on_a_registry_module_an_attribute_store_takes_over_the_other_spelling",
)
_REGISTRY_MATCHED = (
    "test_gated_on_the_registry_by_name",
    "test_gated_on_the_registry_by_module",
    "test_gated_on_the_registry_through_the_package",
)
_UNITTEST_DECORATED = (
    "test_gated_by_a_unittest_decorator",
    "test_gated_by_a_unittest_decorator_whose_condition_is_a_keyword",
    "test_gated_by_a_unittest_decorator_imported_by_name",
    "test_gated_by_a_unittest_decorator_imported_under_an_alias",
    "test_gated_by_a_unittest_decorator_through_a_module_alias",
)
_UNITTEST_METHOD = ("test_gated_by_a_unittest_method",)
# The gates that must NOT be refused for the assertions above to mean anything: the one opt-in read
# twice, a dataset gate, and a membership of a module constant -- the last two the accepting direction
# of the two forms whose operand rather than whose callee carries the reading: without `_LOCAL_DATASET`
# the path arm could be deleted outright and pass, and without `_MEMBERSHIP_MATCHED` the membership arm
# could be narrowed to its refusals and pass. spec 00114 Task 4 extends `_DISPOSED` with two tuples when it
# appends its cases.
_OPT_IN_READ = ("test_gated_on_the_flag", "test_fails_rather_than_skips_when_the_opt_in_is_set")
_LOCAL_DATASET = ("test_gated_on_a_local_dataset", "test_gated_on_a_local_bound_once_to_a_literal_path")
_MEMBERSHIP_MATCHED = ("test_gated_on_a_membership_of_a_module_constant",)
_DISPOSED = (
    _SECOND_FLAG_NAMED
    + _SECOND_FLAG_REFUSED
    + _REACHABILITY_REFUSED
    + _REGISTRY_MATCHED
    + _OPT_IN_READ
    + _LOCAL_DATASET
    + _MEMBERSHIP_MATCHED
    + _UNITTEST_DECORATED
    + _UNITTEST_METHOD
)


def test_every_second_opt_in_spelling_is_caught_by_one_of_the_two_assertions():
    """Every way to put a second flag in front of a skip that this fixture carries, each caught by one
    assertion or the other. `_SECOND_FLAG_NAMED` is READ -- the key is a literal or a plain module
    constant, so the matcher names it and the one-name assertion refuses it; `_SECOND_FLAG_REFUSED` is
    REFUSED -- the mapping or the key is reached some other way, and the matcher follows nothing
    (spec 00114 D2), so no form matches and the every-gate-matches assertion refuses it. The two tuples
    are the count; take it from them rather than from a number written here."""
    for name in _SECOND_FLAG_NAMED:
        gate = _fixture(name)
        assert gate.env == ("ZCRYPTO_SOMETHING_ELSE",) and gate.opaque == (), f"{name}: {gate}"
    for name in _SECOND_FLAG_REFUSED:
        gate = _fixture(name)
        assert gate.env == () and gate.opaque, f"{name}: {gate}"
    for control in _OPT_IN_READ:
        assert _fixture(control).env == (OPT_IN,), f"{control}: the one opt-in must be read, or the tuples above prove nothing"


def test_every_fixture_case_carries_a_disposition():
    """The tuples are the count the fixture used to carry as a number. A case appended to `_FIXTURE`
    and named in none of them is passed to `_fixture()` by nothing, so the harness would silently stop
    covering a spelling it holds -- which is the failure the number it replaces existed to prevent."""
    carried = sorted({_fixture_case(gate) for _, gate in _FIXTURE_GATES})
    assert carried == sorted(_DISPOSED), (
        f"undisposed: {sorted(set(carried) - set(_DISPOSED))}; stale: {sorted(set(_DISPOSED) - set(carried))}; "
        f"repeated: {sorted(n for n in set(_DISPOSED) if _DISPOSED.count(n) > 1)}"
    )


def test_every_reachability_spelling_is_refused():
    """A venue probe -- inline, in a helper, on a class, through a module of ours that is not the
    registry, worn as a form by putting the call in an `.exists()` receiver or on the left of an `in`,
    or HOISTED off the receiver to the line above, where the binding is read too, or wearing a
    registry name a `def`, a `class`, an assignment, a second `import ... as` or an attribute
    assignment has taken over -- matches no form. The `..._hoisted...`, `..._of_a_fixture_parameter` and `..._of_an_imported_root`
    cases are the operand predicate's refusing answers (spec 00114 D2): each a value this file cannot
    root in a literal and each a value a venue may have decided. The last six are the registry arm's:
    four binding forms that shadow the import Python would otherwise have run, and an attribute
    assignment on the module at each of its two spellings, which rebinds nothing and changes what the
    call runs. A name whose import is not its ONE binding is not a declaration, and neither is one the
    module assigns an attribute on, whichever spelling the call uses. The
    `..._module_of_ours_that_resolves` case is the price of following nothing: a call is a form only
    into the registry (spec 00114 D3), so a sibling module declares itself there or is rewritten at
    the gate, whatever that module happens to read."""
    for name in _REACHABILITY_REFUSED:
        gate = _fixture(name)
        assert gate.forms == () and gate.opaque, f"{name}: {gate}"


def test_the_registry_is_the_one_call_a_guard_may_make():
    """The three spellings D3 accepts -- a name imported from the registry, an alias of the module, and
    the `from tests import skip_gates` idiom this suite uses for every other `tests/` helper. The two
    it refuses are in `_REACHABILITY_REFUSED` and in the tree assertion's remedy, not here."""
    for name in _REGISTRY_MATCHED:
        gate = _fixture(name)
        assert gate.forms == (Form("registry"),) and gate.opaque == (), f"{name}: {gate}"


def test_unittests_decorator_and_method_are_gates_the_walker_finds():
    """`@unittest.skipIf`/`skipUnless` and `self.skipTest(...)` are the two `unittest` spellings the
    reducer's docstring listed as passing uncaught (spec 00114 D6). Both are gates now, matched like
    any other, and the decorator is recognised under each name `unittest` can be bound by -- the
    dotted module, a module alias, and the name imported from it under its own name or an alias --
    with its condition read from `args[0]` or from the `condition=` keyword."""
    for name in _UNITTEST_DECORATED:
        decorated = _fixture(name)
        assert decorated.kind == "skipif" and decorated.forms == (Form("path"),), f"{name}: {decorated}"
    method = _fixture(_UNITTEST_METHOD[0])
    assert method.kind == "skip-site" and method.forms == (Form("path"),), method


def test_the_fixture_carries_every_position_a_skip_can_sit():
    """The fixture carries a guarded skip in every position one can sit: an `if`, an `else`, an
    `except` handler, a `match` case, a nesting, and behind each receiver and spelling the walker
    recognises. That is a property of the FIXTURE and it is what this test checks.

    It does NOT check that the walker finds them, and the attempt to is deleted rather than repaired.
    `assert guarded <= found` compared a set derived from `_is_pytest_call` and `_guards_of` against a
    set `_gates` derives from the same pair, so it held by construction: three mutations that broke
    discovery and were KILLED by the test this replaced all SURVIVED it. **Discovery cannot be asserted
    from inside this file** -- any set it computes to check the walker against is computed by the
    walker. Asserting it needs a fixture whose expected gates are written down independently, which is
    the enumeration this file's whole history argues against, or a second implementation.
    """
    tree = ast.parse(_FIXTURE)
    parents = _parents(tree)
    modules = _pytest_modules(tree)
    bound = _pytest_bindings(tree, "skip") | _skip_helpers(tree, "skip", _pytest_bindings(tree, "skip"), modules, parents)
    guarded = {n.lineno for n in ast.walk(tree) if _is_pytest_call(n, "skip", bound, modules) and _guards_of(n, parents)}
    assert len(guarded) >= 8, f"the fixture must carry every position a skip can sit, got {len(guarded)}"


def test_a_gate_with_no_venue_dependency_passes_beside_them():
    """The degeneracy control. A guard that flagged every skip would pass its own fixture and refuse
    the dataset gates that are most of `tests/` -- an absent dataset is not an outage read as coverage.
    `_LOCAL_DATASET`'s two are the accepting answers of the path form's operand predicate: one written at
    the gate, one a local bound once to a literal-rooted path, without which the rule could answer
    "not rooted" to everything and pass. The membership case is that control for the other form whose
    operand carries its reading: without an accepting case, the `membership` arm could be narrowed to
    its refusals and nothing here would fail. The tuples are the count; take it from them."""
    for name in _LOCAL_DATASET:
        gate = _fixture(name)
        assert gate.forms == (Form("path"),) and gate.env == () and gate.opaque == (), f"{name}: {gate}"
    member = _fixture(_MEMBERSHIP_MATCHED[0])
    assert member.forms == (Form("membership"),) and member.env == () and member.opaque == (), f"got {member}"
