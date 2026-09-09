#!/usr/bin/env python3
"""Prove a docstring-only edit changed no code: `compare` measures files against a base revision on three arms -- structure, per-scope statement counts and comments -- and `arms` drives the six mutations that show those measurements bite.

Why the arms exist, and what the pass may not do because of them, is `docs/reference/docstring-pass-method.md`. Here you will find only what a line's own shape needs to survive the next edit.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import subprocess
import sys
import tokenize

_SCOPE = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
# Longest first: a bare `<` would match inside `<=` and build a mutant that is not the flip intended.
_FLIP = {"==": "!=", "!=": "==", "<=": ">=", ">=": "<=", "<": ">", ">": "<"}


_EPILOG = """the three arms `compare` reports:
  ast   structure, with every docstring dropped and an emptied body filled with a `pass`
  stmt  per scope, the count of statements that are not the docstring
  cmt   the comment-token stream, which the structure arm cannot see

the six arms `arms` drives, three of which must differ and three of which must not:
  differ  pass deleted, comparison flipped, statement added
  equal   docstring text changed, docstring deleted from a body it shares, module docstring added

an arm that cannot be built on a file is reported with its reason and counted, never omitted.

when `compare` moves `stmt` alone, a scope's statement count changed while its structure did not.
one prose edit does that by design: a docstring that is a body's whole statement cannot be removed
without writing `pass` in its place, and that `pass` is a statement. an `errors.py` whose class body
IS its docstring reports CHANGED for that reason: the statement count really did move."""


class Refused(Exception):
    """Every refusal names the safe alternative in the same sentence."""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse(src: str, where: str) -> ast.Module:
    try:
        return ast.parse(src)
    except SyntaxError as exc:
        raise Refused(f"{where}: does not parse ({exc.msg}, line {exc.lineno}) -- pass a Python file, or fix it first") from exc


def _docstring(node: ast.AST) -> ast.Expr | None:
    body = getattr(node, "body", None)
    if not body or not isinstance(body[0], ast.Expr):
        return None
    value = body[0].value
    return body[0] if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _inner_scopes(node: ast.AST) -> list[ast.AST]:
    """The scopes directly inside `node`, in document order, stopping at each rather than descending
    through it -- so `visit` below reaches every scope exactly once."""
    found: list[ast.AST] = []

    def descend(parent: ast.AST) -> None:
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, _SCOPE):
                found.append(child)
            else:
                descend(child)

    descend(node)
    return found


def _scopes(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """Every scope with a path. Sibling scopes may share a name, so the ordinal disambiguates."""
    out: list[tuple[str, ast.AST]] = []

    def visit(node: ast.AST, path: str) -> None:
        out.append((path, node))
        for ordinal, child in enumerate(_inner_scopes(node)):
            visit(child, f"{path}/{getattr(child, 'name', '?')}#{ordinal}")

    visit(tree, "<module>")
    return out


# --- the three arms -------------------------------------------------------------------------------


def ast_arm(src: str, where: str = "<source>") -> str:
    tree = _parse(src, where)
    for node in ast.walk(tree):
        if not isinstance(node, _SCOPE):
            continue
        if _docstring(node) is not None:
            node.body = node.body[1:]
        # Fill ANY empty body, not only one a docstring emptied: an empty module never held a
        # docstring, so filling only the stripped ones makes ADDING one to `cli/__init__.py` read as
        # a structure change -- the arm the fill exists to keep.
        node.body = node.body or [ast.Pass()]
    return _sha(ast.dump(ast.fix_missing_locations(tree), include_attributes=False))


def stmt_arm(src: str, where: str = "<source>") -> str:
    """Counted per scope rather than per file: a statement moved between two scopes is a change, and
    a file-wide total would net it to zero."""
    rows = [f"{path}\t{len(node.body) - (1 if _docstring(node) is not None else 0)}" for path, node in _scopes(_parse(src, where))]
    return _sha("\n".join(rows))


def cmt_arm(src: str) -> str:
    tokens = tokenize.generate_tokens(io.StringIO(src).readline)
    return _sha("\n".join(t.string for t in tokens if t.type == tokenize.COMMENT))


ARMS = ("ast", "stmt", "cmt")


def digests(src: str, where: str = "<source>") -> tuple[str, str, str]:
    return ast_arm(src, where), stmt_arm(src, where), cmt_arm(src)


# --- byte-accurate source surgery, for the construction arms --------------------------------------


def _line_starts(src: str) -> list[int]:
    """Line starts as UTF-8 BYTE offsets. `ast` reports `col_offset` in bytes, not characters, and an
    em dash is three of them -- character slicing over-consumes and can build a valid-but-different
    mutant that no arm can tell from a real result."""
    out, total = [0], 0
    for line in src.encode("utf-8").splitlines(keepends=True):
        total += len(line)
        out.append(total)
    return out


def _span(src: str, node: ast.AST) -> tuple[int, int]:
    starts = _line_starts(src)
    return starts[node.lineno - 1] + node.col_offset, starts[node.end_lineno - 1] + node.end_col_offset


def _splice(src: str, lo: int, hi: int, replacement: str) -> str:
    raw = src.encode("utf-8")
    return (raw[:lo] + replacement.encode("utf-8") + raw[hi:]).decode("utf-8")


def _read(src: str, lo: int, hi: int) -> str:
    return src.encode("utf-8")[lo:hi].decode("utf-8")


def _cut_lines(src: str, node: ast.AST) -> str:
    lines = src.splitlines(keepends=True)
    return "".join(lines[: node.lineno - 1] + lines[node.end_lineno :])


def _docstring_spans(src: str, tree: ast.Module) -> list[tuple[int, int]]:
    return [_span(src, d) for n in ast.walk(tree) if isinstance(n, _SCOPE) and (d := _docstring(n)) is not None]


# --- the three that must DIFFER -------------------------------------------------------------------


def arm_pass_deleted(src: str, tree: ast.Module):
    """A scope whose body is [docstring, X]: deleting X empties it, and the `Pass` fill hides that
    from the AST arm alone. This is the arm STMT exists for."""
    for node in ast.walk(tree):
        if isinstance(node, _SCOPE) and _docstring(node) is not None and len(node.body) == 2:
            return _cut_lines(
                src, node.body[1]
            ), f"deleted the {type(node.body[1]).__name__} after {getattr(node, 'name', '<module>')}'s docstring"
    return None, "no scope whose body is exactly [docstring, one statement]"


def arm_comparison_flipped(src: str, tree: ast.Module):
    """An `ast.Compare` outside every docstring span. A regex anchor would flip one INSIDE a
    docstring, the dump would correctly not move, and the arm would report a false blind spot."""
    spans = _docstring_spans(src, tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        lo, hi = _span(src, node)
        if any(a <= lo and hi <= b for a, b in spans):
            continue
        gap_lo, gap_hi = _span(src, node.left)[1], _span(src, node.comparators[0])[0]
        gap = _read(src, gap_lo, gap_hi)
        for op, flipped in _FLIP.items():
            if op in gap:
                return _splice(src, gap_lo, gap_hi, gap.replace(op, flipped, 1)), f"flipped `{op}` at line {node.lineno}"
    return None, "no single-operator ast.Compare outside every docstring span"


def arm_statement_added(src: str, tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (doc := _docstring(node)) is not None:
            lines = src.splitlines(keepends=True)
            lines.insert(doc.end_lineno, f"{' ' * node.body[0].col_offset}_gate_probe = 1\n")
            return "".join(lines), f"added a statement to {node.name}"
    return None, "no function carrying a docstring"


# --- the three that must compare EQUAL ------------------------------------------------------------


def arm_docstring_text_changed(src: str, tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, _SCOPE) and (doc := _docstring(node)) is not None:
            lo, hi = _span(src, doc)
            return _splice(src, lo, hi, '"""x."""'), f"rewrote {getattr(node, 'name', '<module>')}'s docstring"
    return None, "no docstring"


def arm_docstring_deleted(src: str, tree: ast.Module):
    """A docstring sharing a body with other statements: a sole-statement one cannot be deleted at
    all, so there is no such mutant to build."""
    for node in ast.walk(tree):
        if isinstance(node, _SCOPE) and _docstring(node) is not None and len(node.body) > 1:
            return _cut_lines(
                src, _docstring(node)
            ), f"deleted {getattr(node, 'name', '<module>')}'s docstring, which shares its body"
    return None, "no docstring sharing a body with another statement"


def arm_module_docstring_added(src: str, tree: ast.Module):
    """Driven in reverse where one is already present: the `before` is the file without it."""
    doc = _docstring(tree)
    if doc is not None:
        return _cut_lines(src, doc), "module docstring present, compared against its own absence"
    return '"""m."""\n\n' + src, "module docstring absent, added"


_DIFFER = (
    ("pass deleted", arm_pass_deleted),
    ("comparison flipped", arm_comparison_flipped),
    ("statement added", arm_statement_added),
)
_EQUAL = (
    ("docstring text changed", arm_docstring_text_changed),
    ("docstring deleted", arm_docstring_deleted),
    ("module docstring added", arm_module_docstring_added),
)


# --- the two subcommands --------------------------------------------------------------------------


def at_rev(rev: str, path: str) -> str:
    result = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    if result.returncode != 0:
        raise Refused(f"{rev}:{path}: not readable from git ({result.stderr.strip()}) -- name a revision and a tracked path")
    return result.stdout


def compare(rev: str, paths: list[str]) -> int:
    moved_any = False
    for path in paths:
        before = digests(at_rev(rev, path), f"{rev}:{path}")
        try:
            after = digests(open(path, encoding="utf-8").read(), path)
        except OSError as exc:
            raise Refused(f"{path}: unreadable ({exc.strerror}) -- name a path in the working tree") from exc
        moved = [name for name, b, a in zip(ARMS, before, after, strict=True) if b != a]
        moved_any |= bool(moved)
        print(f"{'CHANGED' if moved else 'INERT  '} {path}")
        if moved == ["stmt"]:
            print("    (only the statement count moved -- see --help for the one prose edit that does this by design)")
        for name, b, a in zip(ARMS, before, after, strict=True):
            print(f"    {name:4s} {b} {'=' if b == a else '-> ' + a + '  MOVED'}")
    return 1 if moved_any else 0


def run_arms(paths: list[str]) -> int:
    passed = failed = unbuildable = 0
    for path in paths:
        try:
            src = open(path, encoding="utf-8").read()
        except OSError as exc:
            raise Refused(f"{path}: unreadable ({exc.strerror}) -- name a path in the working tree") from exc
        tree = _parse(src, path)
        base = digests(src, path)
        print(f"  {path}")
        for want_differ, group in ((True, _DIFFER), (False, _EQUAL)):
            for label, build in group:
                mutant, note = build(src, tree)
                if mutant is None:
                    print(f"    [n/a ] {label:24s} NOT CONSTRUCTIBLE -- {note}")
                    unbuildable += 1
                    continue
                got = digests(mutant, f"{path} (mutant: {label})")
                differed = got != base
                good = differed == want_differ
                passed += good
                failed += not good
                which = ",".join(n for n, b, a in zip(ARMS, base, got, strict=True) if b != a) or "none"
                verdict = "PASS" if good else "FAIL"
                print(f"    [{verdict}] {label:24s} must {'DIFFER' if want_differ else 'EQUAL ':6s} | moved: {which:14s} | {note}")
    print(f"  arms: {passed} passed, {failed} failed, {unbuildable} not constructible, of {6 * len(paths)}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0].replace("\n", " "),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    cmp_parser = sub.add_parser("compare", help="three arms: base revision against the working tree")
    cmp_parser.add_argument("rev", metavar="BASE", help="the revision the edit started from")
    cmp_parser.add_argument("paths", nargs="+", metavar="PATH", help="tracked Python files to compare")
    arms_parser = sub.add_parser("arms", help="six construction arms, driven on real files")
    arms_parser.add_argument("paths", nargs="+", metavar="PATH", help="Python files to drive the arms on")
    args = parser.parse_args(argv)

    stray = [p for p in args.paths if not p.endswith(".py")]
    if stray:
        print(f"docstring-gate: not Python files: {' '.join(stray)} -- this gate reads Python only", file=sys.stderr)
        return 2
    try:
        return compare(args.rev, args.paths) if args.mode == "compare" else run_arms(args.paths)
    except Refused as refusal:
        print(f"docstring-gate: {refusal}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
