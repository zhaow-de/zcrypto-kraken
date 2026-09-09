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

# The codes are an interface, so their NUMBERS cannot carry severity -- 3 is not worse than 1. A run
# aggregates by this order, or a code change alongside a comment change reports as a comment change.
_SEVERITY = (EXIT_INERT, EXIT_COMMENTS_CHANGED, EXIT_REFUSED, EXIT_CODE_CHANGED)


def worse(left: int, right: int) -> int:
    return max(left, right, key=_SEVERITY.index)


def registered_command_names(main_src: str) -> frozenset[str]:
    """Names registered by CALL rather than by decorator -- `app.command(name="capture")(capture)`.

    Those functions live in another module and carry no decorator, so a per-file scan cannot see that
    their docstring is a `--help` body."""
    names = set()
    for node in ast.walk(ast.parse(main_src, optimize=0)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Call) and "command" in ast.dump(node.func.func):
            names.update(arg.id for arg in node.args if isinstance(arg, ast.Name))
    return frozenset(names)


def docstring_reader_names(src: str) -> frozenset[str]:
    """Names whose `__doc__` this source READS -- `flatten.run_flatten.__doc__` yields `run_flatten`.

    A test asserting on a docstring pins it as surely as `--help` does, and the file defining it
    carries no sign of that."""
    names = set()
    for node in ast.walk(ast.parse(src, optimize=0)):
        if not (isinstance(node, ast.Attribute) and node.attr == "__doc__"):
            continue
        owner = node.value
        if isinstance(owner, ast.Attribute):
            names.add(owner.attr)
        elif isinstance(owner, ast.Name):
            names.add(owner.id)
    return frozenset(names)


def _names_a_typer_hook(dec: ast.AST) -> bool:
    """`.command` or `.callback` on the decorator itself -- a group callback's docstring is its help.

    Matched on the attribute, not on the dump: a bare `@app.callback()` names neither in its keywords,
    and `invoke_without_command=True` merely happens to contain the substring."""
    node = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(node, ast.Attribute) and node.attr in ("command", "callback")


def _docstring_is_output(node: ast.AST, output_names: frozenset[str]) -> bool:
    if any(_names_a_typer_hook(dec) for dec in getattr(node, "decorator_list", [])):
        return True
    # A name collision over-refuses, which is the safe direction for a tool that certifies.
    return getattr(node, "name", None) in output_names


def _docstring_index(node: ast.AST) -> bool:
    body = getattr(node, "body", None)
    return (
        bool(body)
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )


def _strip_docstrings(tree: ast.AST, *, module_doc_is_output: bool, keep_output: bool, output_names: frozenset[str]) -> ast.AST:
    for node in ast.walk(tree):
        if not isinstance(node, _HOLDS_DOCSTRING) or not _docstring_index(node):
            continue
        is_output = _docstring_is_output(node, output_names) or (isinstance(node, ast.Module) and module_doc_is_output)
        if keep_output and is_output:
            continue
        # `or [Pass()]`: a body that was ONLY a docstring becomes empty, and an empty body is a
        # statement-count change to any comparison -- how a deleted `errors.py` docstring reads as code.
        node.body = node.body[1:] or [ast.Pass()]
    return tree


def _shape(src: str, *, keep_output: bool, output_names: frozenset[str]) -> str:
    # optimize=0 explicitly: under `-OO` the interpreter discards docstrings before this sees them.
    tree = ast.parse(src, optimize=0)
    module_doc_is_output = any(isinstance(n, ast.Name) and n.id == "__doc__" for n in ast.walk(tree))
    return ast.dump(
        _strip_docstrings(tree, module_doc_is_output=module_doc_is_output, keep_output=keep_output, output_names=output_names),
        include_attributes=False,
        indent=1,
    )


_NOT_A_NEIGHBOUR = frozenset(
    {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT, tokenize.ENDMARKER}
)


def comment_stream(src: str) -> list[tuple[int, str, str]]:
    """Each comment with its column and the token that FOLLOWS it, since a guard can read POSITION.

    The successor and not the predecessor: deleting a docstring above a comment must stay inert, which
    is the commonest edit this tool certifies."""
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    return [
        (tok.start[1], tok.string, next((t.string for t in toks[i + 1 :] if t.type not in _NOT_A_NEIGHBOUR), ""))
        for i, tok in enumerate(toks)
        if tok.type == tokenize.COMMENT
    ]


@dataclass(frozen=True)
class Result:
    ast_inert: bool
    comments_same: bool
    output_docstring_changed: bool
    detail: str


def compare(before: str, after: str, *, output_names: frozenset[str] = frozenset()) -> Result:
    bare_b, bare_a = (
        _shape(before, keep_output=False, output_names=output_names),
        _shape(after, keep_output=False, output_names=output_names),
    )
    kept_b, kept_a = (
        _shape(before, keep_output=True, output_names=output_names),
        _shape(after, keep_output=True, output_names=output_names),
    )
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


def output_names_in(root: pathlib.Path) -> tuple[frozenset[str], int]:
    """Names the tree pins the docstring of, and the count of files that could not be scanned.

    Both facts are cross-file: a call-registered command carries no decorator, and a docstring read as
    `mod.fn.__doc__` leaves no mark where it is defined. An unscannable file is counted, not skipped."""
    names: set[str] = set()
    unscanned = 0
    entry = root / "cli" / "__main__.py"
    if entry.is_file():
        names |= registered_command_names(entry.read_text())
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "*.py"], capture_output=True, text=True)
    for rel in listed.stdout.split():
        try:
            names |= docstring_reader_names((root / rel).read_text())
        except OSError, SyntaxError, ValueError:
            unscanned += 1
    return frozenset(names), unscanned


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f"usage: {argv[0] if argv else 'prove-inert.py'} <base-rev> <path>...", file=sys.stderr)
        return EXIT_USAGE
    base, paths = argv[1], argv[2:]
    root = _repo_root()
    output_names, unscanned = output_names_in(root)
    print(f"after-side tree: {root}")
    if unscanned:
        print(f"WARNING: {unscanned} file(s) could not be scanned for docstring readers")
    worst = EXIT_INERT
    for path in paths:
        try:
            result = compare(_at_revision(base, path), (root / path).read_text(), output_names=output_names)
        except (ValueError, OSError, SyntaxError) as exc:
            # One unreadable path must not abort the rest, or a run prints partial results and no summary.
            print(f"{path}: REFUSED -- {exc}")
            worst = worse(worst, EXIT_REFUSED)
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
        worst = worse(worst, code)
    print(f"{len(paths)} file(s) compared against {base}, exit {worst}")
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
