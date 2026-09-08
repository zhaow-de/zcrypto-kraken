#!/usr/bin/env python3
"""Prove a change is prose-only: same code shape, with the comment stream reported separately.

A docstring here is often program OUTPUT -- a Typer command's is its `--help` body, and three scripts
hand it to argparse -- so a change to one is REFUSED rather than certified."""

import ast
import difflib
import io
import pathlib
import subprocess
import sys
import tokenize
from dataclasses import dataclass

_HOLDS_DOCSTRING = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

EXIT_INERT = 0
EXIT_CODE_CHANGED = 1
EXIT_USAGE = 2
EXIT_COMMENTS_CHANGED = 3
EXIT_REFUSED = 4


def _is_command(node: ast.AST) -> bool:
    # `@app.command()`, `@app.command(name=...)`, `@app.command` all render `command` in the dump.
    return any("command" in ast.dump(dec) for dec in getattr(node, "decorator_list", []))


def _docstring_index(node: ast.AST) -> bool:
    body = getattr(node, "body", None)
    return (
        bool(body)
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )


def _strip_docstrings(tree: ast.AST, *, module_doc_is_output: bool, keep_output: bool) -> ast.AST:
    for node in ast.walk(tree):
        if not isinstance(node, _HOLDS_DOCSTRING) or not _docstring_index(node):
            continue
        is_output = _is_command(node) or (isinstance(node, ast.Module) and module_doc_is_output)
        if keep_output and is_output:
            continue
        # `or [Pass()]`: a body that was ONLY a docstring becomes empty, and an empty body is a
        # statement-count change to any comparison -- how a deleted `errors.py` docstring reads as code.
        node.body = node.body[1:] or [ast.Pass()]
    return tree


def _shape(src: str, *, keep_output: bool) -> str:
    # optimize=0 explicitly: under `-OO` the interpreter discards docstrings before this sees them.
    tree = ast.parse(src, optimize=0)
    module_doc_is_output = any(isinstance(n, ast.Name) and n.id == "__doc__" for n in ast.walk(tree))
    return ast.dump(
        _strip_docstrings(tree, module_doc_is_output=module_doc_is_output, keep_output=keep_output),
        include_attributes=False,
        indent=1,
    )


def comment_stream(src: str) -> list[str]:
    return [tok.string for tok in tokenize.generate_tokens(io.StringIO(src).readline) if tok.type == tokenize.COMMENT]


@dataclass(frozen=True)
class Result:
    ast_inert: bool
    comments_same: bool
    output_docstring_changed: bool
    detail: str


def compare(before: str, after: str) -> Result:
    bare_b, bare_a = _shape(before, keep_output=False), _shape(after, keep_output=False)
    kept_b, kept_a = _shape(before, keep_output=True), _shape(after, keep_output=True)
    detail = ""
    if bare_b != bare_a:
        # The differing nodes, not a bare verdict: a reader has to see WHICH construct moved.
        diff = difflib.unified_diff(bare_b.splitlines(), bare_a.splitlines(), "before", "after", lineterm="", n=1)
        detail = "\n".join(list(diff)[:14])
    return Result(
        ast_inert=bare_b == bare_a,
        comments_same=comment_stream(before) == comment_stream(after),
        output_docstring_changed=bare_b == bare_a and kept_b != kept_a,
        detail=detail,
    )


def _repo_root() -> pathlib.Path:
    done = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit("prove-inert: not inside a git worktree")
    return pathlib.Path(done.stdout.strip())


def _at_revision(rev: str, path: str) -> str:
    done = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    if done.returncode != 0:
        # Refused, not read as "": two failed extractions compare equal and would report inert.
        raise ValueError(f"cannot read {path} at {rev}: {done.stderr.strip()}")
    return done.stdout


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f"usage: {argv[0] if argv else 'prove-inert.py'} <base-rev> <path>...", file=sys.stderr)
        return EXIT_USAGE
    base, paths = argv[1], argv[2:]
    root = _repo_root()
    print(f"after-side tree: {root}")
    worst = EXIT_INERT
    for path in paths:
        try:
            result = compare(_at_revision(base, path), (root / path).read_text())
        except (ValueError, OSError, SyntaxError) as exc:
            # One unreadable path must not abort the rest, or a run prints partial results and no summary.
            print(f"{path}: REFUSED -- {exc}")
            worst = max(worst, EXIT_REFUSED)
            continue
        if not result.ast_inert:
            verdict, code = "CODE CHANGED", EXIT_CODE_CHANGED
        elif result.output_docstring_changed:
            verdict, code = "REFUSED -- a docstring that is program output changed", EXIT_REFUSED
        elif not result.comments_same:
            verdict, code = "COMMENTS CHANGED", EXIT_COMMENTS_CHANGED
        else:
            verdict, code = "INERT", EXIT_INERT
        print(f"{path}: {verdict}")
        if result.detail:
            print(result.detail)
        worst = max(worst, code)
    print(f"{len(paths)} file(s) compared against {base}, exit {worst}")
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
