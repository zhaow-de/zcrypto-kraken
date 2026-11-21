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
# Declare an exception on the line above the comparison or within the comparison's own lines:
# `# config-selector-ok: <why>`. `test_the_exemption_window_is_the_comparisons_own` pins it.
_MARKER = "config-selector-ok:"


def _path_consts(tree: ast.Module, src: str) -> set[str]:
    """Names whose value names a path under infra/."""
    return {
        t.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name) and _HAZARD in (ast.get_source_segment(src, n.value) or "")
    }


def _reads_infra(node: ast.AST, src: str, consts: set[str], generic: frozenset[str] = frozenset()) -> bool:
    """A read of an infra file, whether the path is spelled out or held in a constant, read inline or
    by a `generic` helper handed an infra path as an argument (`_program(ROLE / "x")`)."""

    def names_infra(node: ast.AST) -> bool:
        seg = ast.get_source_segment(src, node) or ""
        return _HAZARD in seg or any(c in seg for c in consts)

    if ".read_text()" in (ast.get_source_segment(src, node) or "") and names_infra(node):
        return True
    return any(
        isinstance(c, ast.Call) and _callee(c) in generic and any(names_infra(a) for a in [*c.args, *(k.value for k in c.keywords)])
        for c in ast.walk(node)
    )


def _callee(call: ast.Call) -> str | None:
    """The called name: `_unit()` is `_unit`, and `self._src(n)` or `Cls._src(n)` is `_src`."""
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _chain_calls(node: ast.AST) -> set[str]:
    """The names called along an expression's chain: `self._src(n).splitlines()` calls `splitlines` and `_src`."""
    names: set[str] = set()
    while True:
        if isinstance(node, ast.Call):
            names.add(_callee(node) or "")
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return names


def _functions(tree: ast.Module) -> list[tuple[str, set[str], list[ast.expr]]]:
    """Every function or method, as its name, its parameters and the values it returns. A list, not a
    dict: two functions sharing a name both count."""
    out = []
    for f in ast.walk(tree):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = f.args
            params = {p.arg for p in [*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg] if p}
            out.append((f.name, params, [r.value for r in ast.walk(f) if isinstance(r, ast.Return) and r.value is not None]))
    return out


def _generic_readers(functions) -> frozenset[str]:
    """Functions that return a `.read_text()` of a path built from a parameter: `return path.read_text()`."""
    names = set()
    for name, params, values in functions:
        for c in (c for v in values for c in ast.walk(v)):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "read_text":
                if any(isinstance(x, ast.Name) and x.id in params for x in ast.walk(c.func.value)):
                    names.add(name)
    return frozenset(names)


def _infra_text_vars(tree: ast.Module, src: str) -> set[str]:
    """Names bound to the TEXT of a file under infra/, directly or through a path const."""
    consts = _path_consts(tree, src)
    functions = _functions(tree)
    generic = _generic_readers(functions)
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and _reads_infra(n.value, src, consts, generic):
            out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    # A function returning an infra read, inline or through a haystack, is a haystack by name:
    # `_unit()` and `self._src(n)` called inline, and `unit = _unit()`. A name it was handed is not
    # its haystack, so `def _norm(line): return line.strip()` is no reader.
    readers = {name for name, _, values in functions if any(_reads_infra(v, src, consts, generic) for v in values)}
    # Anything DERIVED from a haystack is a haystack: aliases, `next(... for l in h.splitlines())`,
    # `h.splitlines()`. Iterate to a fixed point -- a chain can be any number of hops, and the sets
    # only grow, so it ends.
    while True:
        before = set(out)
        readers |= {
            name
            for name, params, values in functions
            if any(_root_name(v) in out - params or _chain_calls(v) & (out - params) for v in values)
        }
        out |= readers
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                v = n.value
                derived = (
                    _root_name(v) in out
                    or bool(_chain_calls(v) & readers)
                    or (
                        # `rw = next(l for l in unit.splitlines() if ...)` -- one line OF a haystack
                        isinstance(v, ast.Call)
                        and _root_name(v.func) == "next"
                        and any(
                            ".splitlines()" in (ast.get_source_segment(src, g.iter) or "")
                            and any(h in (ast.get_source_segment(src, g.iter) or "") for h in out)
                            for a in v.args
                            for g in getattr(a, "generators", [])
                        )
                    )
                )
                if derived:
                    out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
            # A loop variable over `<haystack>.splitlines()` IS the haystack, one line at a time. Without
            # this, `any("x" in line for line in text.splitlines())` slips through -- and that is precisely
            # the form someone reaches for to satisfy this guard. Both comprehension generators and plain
            # `for` statements.
            gens = list(getattr(n, "generators", []))
            if isinstance(n, ast.For):
                gens.append(n)
            for gen in gens:
                it = ast.get_source_segment(src, gen.iter) or ""
                if ".splitlines()" in it and any(h in it for h in out):
                    out |= {t.id for t in ast.walk(gen.target) if isinstance(t, ast.Name)}
        if out == before:
            break
    return out


def _line_vars(tree: ast.Module, src: str, haystacks: set[str]) -> set[str]:
    """Names bound to a single LINE of a haystack -- the only place a prefix anchor is meaningful."""
    out: set[str] = set()
    for n in ast.walk(tree):
        gens = list(getattr(n, "generators", []))
        if isinstance(n, ast.For):
            gens.append(n)
        for gen in gens:
            it = ast.get_source_segment(src, gen.iter) or ""
            if ".splitlines()" in it and any(h in it for h in haystacks):
                out |= {t.id for t in ast.walk(gen.target) if isinstance(t, ast.Name)}
    return out


# Suites the guard reaches but predates. Two rules: NEW code never lands here -- that would be
# defeating the guard rather than satisfying it -- and an entry may be added only when the guard's
# SCOPE widens onto ground it did not previously cover, with the reason recorded beside it.
_GRANDFATHERED = {
    "test_infra_converge_guards.py",  # pre-existing at the guard's introduction
    "test_panel_regenerate.py",  # pre-existing at the guard's introduction
    # Admitted because they assert on rendered output, where the needles are specific rendered
    # command strings with low collision risk -- NOT because a render is comment-free, since a j2
    # template's comments survive into it. `test_infra_archive_pull_template.py`'s metric-name
    # assert is the weakest of them and sits on the hazard.
    "test_infra_archive_pull_template.py",
    "test_infra_firewall_template.py",
    "test_infra_verify_replay_template.py",
}


def _root_name(node: ast.AST) -> str | None:
    """The base identifier of an expression: `ln.strip()` and `ln` both root at `ln`."""
    while True:
        if isinstance(node, ast.Call):
            node = node.func  # `_unit()` roots at `_unit`; `ln.strip()` keeps unwrapping to `ln`
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            break
    return node.id if isinstance(node, ast.Name) else None


def _prefix_anchored(tree: ast.Module, src: str, line_vars: set[str]) -> set[int]:
    """Compare nodes sitting beside a `.startswith(...)` on the same name.

    `startswith("regex") and "node_load1" in ln` is safe: the prefix already excludes comments, and
    the substring only says WHICH anchored line. Flagging it would push editors toward suppressions.
    """
    safe: set[int] = set()
    for n in ast.walk(tree):
        # `and` only: in an `or`, the anchor gates nothing. And the anchor must be on a LINE
        # variable -- `text.startswith("---") and "x" in text` anchors on the whole file, which for
        # a YAML document is always true and exempts the substring for free.
        if not isinstance(n, ast.BoolOp) or not isinstance(n.op, ast.And):
            continue
        # The anchor's CONTENT, not just its spelling: `startswith("")` is true of every line, so an
        # empty prefix exempts any substring for free -- and a prefix this reads as no literal at all
        # (a name, a tuple of alternatives) is one whose exclusion of comments it cannot judge.
        names = {
            root
            for v in n.values
            if isinstance(v, ast.Call)
            and isinstance(v.func, ast.Attribute)
            and v.func.attr == "startswith"
            and len(v.args) == 1
            and isinstance(v.args[0], ast.Constant)
            and isinstance(v.args[0].value, str)
            and v.args[0].value
            for root in (_root_name(v.func.value),)
            if root
        }
        if not names:
            continue
        for v in n.values:
            if isinstance(v, ast.Compare) and _root_name(v.comparators[0]) in names & line_vars:
                safe.add(id(v))
    return safe


def _violations(src: str, name: str = "<src>") -> list[str]:
    """Every substring selector over an infra file's text in `src`."""
    tree = ast.parse(src)
    consts = _path_consts(tree, src)
    generic = _generic_readers(_functions(tree))
    haystacks = _infra_text_vars(tree, src)
    src_lines = src.splitlines()
    anchored = _prefix_anchored(tree, src, _line_vars(tree, src, haystacks))
    return [
        f"{name}:{n.lineno}  {(ast.get_source_segment(src, n) or '').strip()[:110]}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and len(n.ops) == 1
        and isinstance(n.ops[0], ast.In)
        and id(n) not in anchored
        and not any(_MARKER in l for l in src_lines[max(0, n.lineno - 2) : (n.end_lineno or n.lineno)])
        and (
            _root_name(n.comparators[0]) in haystacks
            or bool(_chain_calls(n.comparators[0]) & haystacks)
            or _reads_infra(n.comparators[0], src, consts, generic)
        )
    ]


# Each of these evaded an earlier version of this guard.
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
    "startswith shield on the whole file": """
def t():
    defaults = (REPO / "infra/defaults.yml").read_text()
    assert defaults.startswith("---") and "cap: 100.0" in defaults
""",
    "haystack via a helper's return": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def t():
    unit = _unit()
    assert "ProtectSystem=strict" in unit
""",
    "a reader helper called inline": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def t():
    assert "ProtectSystem=strict" in _unit()
""",
    "a reader helper's lines, inline": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def t():
    assert "ProtectSystem=strict" in _unit().splitlines()
""",
    "a loop over a reader helper's lines": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def t():
    for line in _unit().splitlines():
        assert "ProtectSystem=strict" in line
""",
    "any over a reader helper's lines": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def t():
    assert any("ProtectSystem=strict" in l for l in _unit().splitlines())
""",
    "a helper returning a haystack local": """
def _unit():
    text = (REPO / "infra/u.service").read_text()
    return text
def t():
    unit = _unit()
    assert "ProtectSystem=strict" in unit
""",
    "a helper returning a haystack local, called inline": """
def _unit():
    text = (REPO / "infra/u.service").read_text()
    return text
def t():
    assert "ProtectSystem=strict" in _unit()
""",
    "a method reader via self": """
class TestUnit:
    def _src(self, name):
        return (REPO / "infra" / "scripts" / name).read_text()
    def test_it(self):
        assert "ProtectSystem=strict" in self._src("u.service")
""",
    "a method reader bound to a local": """
class TestUnit:
    def _src(self, name):
        return (REPO / "infra" / "scripts" / name).read_text()
    def test_it(self):
        unit = self._src("u.service")
        assert "ProtectSystem=strict" in unit
""",
    "a static reader via its class": """
class Units:
    @staticmethod
    def src(name):
        return (REPO / "infra" / name).read_text()
def t():
    assert "ProtectSystem=strict" in Units.src("u.service")
""",
    "a generic reader handed an infra path": """
def _program(path):
    return path.read_text()
def t():
    assert "ProtectSystem=strict" in _program(REPO / "infra/u.service")
""",
    "a generic reader handed a path constant": """
ROLE = REPO / "infra/roles/x"
def _program(path):
    return path.read_text()
def t():
    unit = _program(ROLE / "u.service")
    assert "ProtectSystem=strict" in unit
""",
    "a reader five helpers deep": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def _a():
    return _unit()
def _b():
    return _a()
def _c():
    return _b()
def _d():
    return _c()
def t():
    assert "ProtectSystem=strict" in _d()
""",
    "a reader sharing its name with a later function": """
def _unit():
    return (REPO / "infra/u.service").read_text()
class Other:
    def _unit(self):
        return "literal"
def t():
    assert "ProtectSystem=strict" in _unit()
""",
    "one line pulled out with next()": """
def t():
    unit = (REPO / "infra/u.service").read_text()
    rw = next(l for l in unit.splitlines() if l.startswith("ReadWritePaths="))
    assert "/var/lib/x" in rw
""",
    "plain for-statement over splitlines": """
def t():
    unit = (REPO / "infra/u.service").read_text()
    for line in unit.splitlines():
        assert "ProtectSystem=strict" in line
""",
    "comparator derived from the haystack": """
def t():
    text = (REPO / "infra/defaults.yml").read_text()
    assert "cap: 100.0" in text.strip()
""",
    "f-string needle": """
def t():
    tasks = (REPO / "infra/m.yml").read_text()
    assert f"dest: {b}" in tasks
""",
    "empty prefix anchor on a line": """
def t():
    unit = (REPO / "infra/u.service").read_text()
    assert any(line.startswith("") and "ProtectSystem=strict" in line for line in unit.splitlines())
""",
}


@pytest.mark.parametrize("label", sorted(_MUST_CATCH), ids=list(sorted(_MUST_CATCH)))
def test_the_guard_catches_each_known_evasion(label: str) -> None:
    assert _violations(_MUST_CATCH[label]), f"the guard no longer catches: {label}"


def test_the_guard_accepts_a_real_prefix_anchor() -> None:
    """The true positive beside the empty-prefix case above: a prefix that does exclude comments stays exempt."""
    src = """
def t():
    unit = (REPO / "infra/u.service").read_text()
    assert any(line.startswith("ReadWritePaths=") and "/var/lib/x" in line for line in unit.splitlines())
"""
    assert not _violations(src)


def test_the_guard_accepts_a_real_prefix_anchor_over_a_reader_helpers_lines() -> None:
    src = """
def _unit():
    return (REPO / "infra/u.service").read_text()
def t():
    assert any(line.startswith("ReadWritePaths=") and "/var/lib/x" in line for line in _unit().splitlines())
"""
    assert not _violations(src)


_MUST_STAY_CLEAN = {
    "a helper whose parameter shares a line variable's name": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def _norm(line):
    return line.strip()
def t(out):
    for line in _unit().splitlines():
        assert line.startswith("ExecStart=") and "x" in line
    assert "Usage" in _norm(out)
""",
    "a helper whose parameter shares a haystack's name": """
def _unit():
    return (REPO / "infra/u.service").read_text()
def _first(rendered):
    return rendered.strip()
def t(tmp_path):
    rendered = _unit()
    assert rendered
    assert "ok" in _first(tmp_path.joinpath("log").read_text())
""",
    "a generic reader handed a file the test wrote": """
def _program(path):
    return path.read_text()
def t(tmp_path):
    assert "ok" in _program(tmp_path / "log")
""",
    "a helper reading its own fixed file, handed an infra path for another use": """
STATIC = REPO / "tests/fixtures/lint.cfg"
ROLE = REPO / "infra/roles/x"
def _lint(path):
    return run(STATIC.read_text(), path)
def t():
    assert "ok" in _lint(ROLE / "t.j2")
""",
}


@pytest.mark.parametrize("label", sorted(_MUST_STAY_CLEAN), ids=list(sorted(_MUST_STAY_CLEAN)))
def test_the_guard_leaves_a_text_that_is_no_infra_read_alone(label: str) -> None:
    assert not _violations(_MUST_STAY_CLEAN[label]), f"the guard now flags: {label}"


def test_the_guard_accepts_a_declared_exception() -> None:
    src = """
def t():
    s = (REPO / "infra/m.yml").read_text()
    # config-selector-ok: searching, not selecting
    assert name in s
"""
    assert not _violations(src)


_WINDOW_HEAD = '\ndef t():\n    s = (REPO / "infra/m.yml").read_text()\n'


@pytest.mark.parametrize(
    ("position", "body", "exempted"),
    [
        ("no marker", "    assert name in s\n", False),
        ("above the comparison", "    # config-selector-ok: why\n    assert name in s\n", True),
        ("two lines above", "    # config-selector-ok: why\n\n    assert name in s\n", False),
        ("trailing on the comparison", "    assert name in s  # config-selector-ok: why\n", True),
        ("above a wrapped assert", "    # config-selector-ok: why\n    assert (\n        name\n        in s\n    )\n", False),
        ("on the wrapped assert's line", "    assert (  # config-selector-ok: why\n        name\n        in s\n    )\n", True),
        ("between the operands", "    assert (\n        name\n        # config-selector-ok: why\n        in s\n    )\n", True),
        (
            "on its own line below the comparison",
            "    assert (\n        name\n        in s\n        # config-selector-ok: why\n    )\n",
            False,
        ),
        ("trailing on the closing paren", "    assert (\n        name\n        in s\n    )  # config-selector-ok: why\n", False),
    ],
)
def test_the_exemption_window_is_the_comparisons_own(position: str, body: str, exempted: bool) -> None:
    """The window is the line above the comparison plus the comparison's own lines."""
    assert bool(_violations(_WINDOW_HEAD + body)) is not exempted, position


@pytest.mark.parametrize("path", sorted(p for p in TESTS.glob("test_*.py") if p.name not in _GRANDFATHERED), ids=lambda p: p.name)
def test_no_substring_selector_over_a_hand_edited_config(path: Path) -> None:
    bad = _violations(path.read_text(), path.name)
    assert not bad, "substring selector over a hand-edited config -- parse it, or match by prefix:\n  " + "\n  ".join(bad)
