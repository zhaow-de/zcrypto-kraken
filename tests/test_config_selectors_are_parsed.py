"""No test may pull a value out of a hand-edited config file by substring.

Substring containment over a config file's TEXT matches comments, `fail_msg` prose and SUFFIXED
values, so it cannot tell the setting apart from something that merely mentions it.

Parse the file (`yaml.safe_load`, `json.loads`) or select by prefix (`line.strip().startswith(key)`).
Where substring really is the right semantics, declare it: `# config-selector-ok: <why>`.

Not covered, deliberately: reader helpers reached through an intermediate variable; AnnAssign,
walrus and tuple bindings; the CONTENT of a prefix anchor (`startswith("")` exempts anything);
`not in` and `re.search`; and files outside `infra/`.
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
    readers: set[str] = set()
    # Functions whose body returns an infra read: `unit = _rendered_unit()` is a haystack too.
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and any(
            isinstance(r, ast.Return)
            and ".read_text()" in (ast.get_source_segment(src, r) or "")
            and (
                _HAZARD in (ast.get_source_segment(src, r) or "")
                or any(c in (ast.get_source_segment(src, r) or "") for c in consts)
            )
            for r in ast.walk(n)
        ):
            readers.add(n.name)
    # Anything DERIVED from a haystack is a haystack: aliases, `next(... for l in h.splitlines())`,
    # `h.splitlines()`. Iterate to a fixed point -- a chain can be two hops.
    for _ in range(4):
        before = set(out)
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                v = n.value
                derived = _root_name(v) in out | readers or (
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
                if derived:
                    out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
            # both comprehension generators and plain `for` statements
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
    # Added when haystack tracking learned to follow helper returns and derived bindings. They
    # assert on rendered output. That is NOT comment-free -- a j2 template's comments survive into
    # the render -- so the justification is narrower: the needles are specific rendered command
    # strings with low collision risk. `test_infra_archive_pull_template.py`'s metric-name assert is
    # the weakest of them and sits on the hazard.
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
            if isinstance(v, ast.Compare) and _root_name(v.comparators[0]) in names & line_vars:
                safe.add(id(v))
    return safe


def _violations(src: str, name: str = "<src>") -> list[str]:
    """Every substring selector over an infra file's text in `src`."""
    tree = ast.parse(src)
    consts = _path_consts(tree, src)
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
        and (_root_name(n.comparators[0]) in haystacks or _reads_infra(n.comparators[0], src, consts))
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
