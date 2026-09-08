#!/usr/bin/env python3
"""Prove a change is prose-only: same code shape, with the comment stream reported separately.

A comment edit is invisible to the AST, so the two arms stay distinguishable rather than one verdict."""

import ast
import difflib
import io
import pathlib
import subprocess
import sys
import tokenize
from dataclasses import dataclass

_HOLDS_DOCSTRING = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, _HOLDS_DOCSTRING):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                # `or [Pass()]`: a body that was ONLY a docstring becomes empty, and an empty body is
                # a statement-count change to any comparison -- which is how a deleted `errors.py`
                # docstring reads as a code change.
                node.body = body[1:] or [ast.Pass()]
    return tree


def code_shape(src: str) -> str:
    return ast.dump(_strip_docstrings(ast.parse(src)), include_attributes=False, indent=1)


def comment_stream(src: str) -> list[str]:
    return [tok.string for tok in tokenize.generate_tokens(io.StringIO(src).readline) if tok.type == tokenize.COMMENT]


@dataclass(frozen=True)
class Result:
    ast_inert: bool
    comments_same: bool
    detail: str


def compare(before: str, after: str) -> Result:
    shape_before, shape_after = code_shape(before), code_shape(after)
    detail = ""
    if shape_before != shape_after:
        # The differing nodes, not a bare verdict: a reader has to see WHICH construct moved.
        diff = difflib.unified_diff(shape_before.splitlines(), shape_after.splitlines(), "before", "after", lineterm="", n=1)
        detail = "\n".join(list(diff)[:14])
    return Result(shape_before == shape_after, comment_stream(before) == comment_stream(after), detail)


def _at_revision(rev: str, path: str) -> str:
    done = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    if done.returncode != 0:
        # Refused rather than read as empty: two failed extractions compare equal and report inert.
        raise SystemExit(f"prove-inert: cannot read {path} at {rev}: {done.stderr.strip()}")
    return done.stdout


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0] if argv else 'prove-inert.py'} <base-rev> <path>...", file=sys.stderr)
        return 2
    base, paths = argv[1], argv[2:]
    if not paths:
        print(f"usage: {argv[0]} <base-rev> <path>...", file=sys.stderr)
        return 2
    changed = 0
    for path in paths:
        result = compare(_at_revision(base, path), pathlib.Path(path).read_text())
        arms = "INERT" if result.ast_inert else "CODE CHANGED"
        comments = "comments same" if result.comments_same else "COMMENTS CHANGED"
        print(f"{path}: {arms}, {comments}")
        if result.detail:
            print(result.detail)
        changed += not result.ast_inert
    print(f"{len(paths)} file(s) compared against {base}, {changed} with code changes")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
