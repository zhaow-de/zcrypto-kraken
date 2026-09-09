#!/usr/bin/env python3
"""Prove a change is prose-only: the same code shape, with the comment stream reported separately.

exit 0  INERT -- the only verdict that licenses the words *prose-only*
exit 1  CODE CHANGED -- the stripped shape or a scope's statement count moved
exit 2  a usage error, which is this text
exit 3  COMMENTS CHANGED -- a comment's text, column, the line it sits above, or its distance moved
exit 4  REFUSED -- a docstring that is program output changed, a path or the replay closure itself could not
        be read, or the file is one whose raw bytes `replay_fingerprint` digests: no arm proves no effect

3 and 4 are verdicts to act on, never a run to retry: 3 says a guard that reads a comment's position
may have stopped seeing it, and 4 says the claim cannot be made from here at all. A docstring is often
program OUTPUT -- a Typer command's is its `--help` body, and scripts hand it to argparse.

An effect carried by a file's raw BYTES is invisible to these arms: `replay_fingerprint` digests whole files, so
that set is refused, never certified. Run this through `uv run`: the set needs an importable `cli`, and an older
interpreter cannot parse this file at all -- exiting 1, which is CODE CHANGED above rather than the crash it is."""

import ast
import difflib
import io
import os
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
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Call) and _names_a_typer_hook(node.func)):
            continue
        for target in (*node.args, *(kw.value for kw in node.keywords)):
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
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
    """A group callback's docstring is its `--help` body, so `.callback` counts as much as `.command`.

    Matched on the attribute, not on the dump: a bare `@app.callback()` names neither in its keywords,
    and `invoke_without_command=True` merely happens to contain the substring."""
    node = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(node, ast.Attribute) and node.attr in ("command", "callback")


def _docstring_is_output(node: ast.AST, output_names: frozenset[str]) -> bool:
    if any(_names_a_typer_hook(dec) for dec in getattr(node, "decorator_list", [])):
        return True
    # A name collision over-refuses, which is the safe direction for a tool that certifies.
    return getattr(node, "name", None) in output_names


def _has_docstring(node: ast.AST) -> bool:
    body = getattr(node, "body", None)
    return (
        bool(body)
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )


def _strip_docstrings(tree: ast.AST, *, module_doc_is_output: bool, keep_output: bool, output_names: frozenset[str]) -> ast.AST:
    for node in ast.walk(tree):
        if not isinstance(node, _HOLDS_DOCSTRING):
            continue
        if not _has_docstring(node):
            # A module is the one body that can already be empty, so it takes the same fill: without
            # it, a docstring added to an empty `__init__.py` reads as the `pass` put in its place.
            node.body = node.body or [ast.Pass()]
            continue
        is_output = _docstring_is_output(node, output_names) or (isinstance(node, ast.Module) and module_doc_is_output)
        if keep_output and is_output:
            continue
        # `or [Pass()]` is the method's prescribed normalisation; what keeps an emptied body from
        # reading as a real `pass` is the per-scope count, which no dump of the tree can carry.
        node.body = node.body[1:] or [ast.Pass()]
    return tree


def _scope_statement_counts(tree: ast.AST) -> list[int]:
    """Read BEFORE the fill runs, because the fill equates an emptied body with a real `pass`.

    Mode-independent, so the kept-output shape can never differ by this alone."""
    return [len(node.body) - (1 if _has_docstring(node) else 0) for node in ast.walk(tree) if isinstance(node, _HOLDS_DOCSTRING)]


def _shape(src: str, *, keep_output: bool, output_names: frozenset[str]) -> str:
    # optimize=0 explicitly: under `-OO` the interpreter discards docstrings before this sees them.
    tree = ast.parse(src, optimize=0)
    module_doc_is_output = any(isinstance(n, ast.Name) and n.id == "__doc__" for n in ast.walk(tree))
    counts = _scope_statement_counts(tree)
    dump = ast.dump(
        _strip_docstrings(tree, module_doc_is_output=module_doc_is_output, keep_output=keep_output, output_names=output_names),
        include_attributes=False,
        indent=1,
    )
    return f"{dump}\nnon-docstring statements per scope: {counts}"


_NOT_A_NEIGHBOUR = frozenset(
    {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT, tokenize.ENDMARKER}
)


def comment_stream(src: str) -> list[tuple[int, str, str, int]]:
    """A guard can read a comment's POSITION, so identity alone is not the comment.

    The line BELOW and not the one above: deleting a docstring above a comment must stay inert, and
    it moves neither that line nor the distance to it."""
    lines = src.splitlines()
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    out = []
    for i, tok in enumerate(toks):
        if tok.type != tokenize.COMMENT:
            continue
        after = next((t for t in toks[i + 1 :] if t.type not in _NOT_A_NEIGHBOUR), None)
        # The whole line and the distance, because `assert` is what these markers name by design: a
        # marker sliding onto the next one keeps its column, its own text and its successor's token.
        named = lines[after.start[0] - 1].strip() if after else ""
        gap = after.start[0] - tok.start[0] if after else 0
        out.append((tok.start[1], tok.string, named, gap))
    return out


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


def replay_closure() -> tuple[frozenset[str], pathlib.Path] | str:
    """The repo-relative paths whose bytes `replay_fingerprint` digests, and the tree they
    describe, or a string saying why they could not be read: only a named cause tells an operator whether to
    fix their invocation or the tree. The tree is the INSTALLED package's, usually but not necessarily the one
    being judged. Every failure is caught, since one escaping here exits 1, this tool's own CODE CHANGED."""
    try:
        from cli.engine.gate_cache import _REPO_ROOT, _replay_code_paths
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    try:
        # Repo-relative and normalised (`./`, `//`, interior `..`) -- STRICTER membership, the opposite
        # direction from a forgiving `_at_revision`. Absolute and leading-`../` it does not fold; both exit
        # 128 in `_at_revision`, but only at the toplevel, which is why `main` refuses any other cwd.
        relative = frozenset(str(path.relative_to(_REPO_ROOT)) for path in _replay_code_paths())
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return relative, _REPO_ROOT


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
    if listed.returncode != 0:
        # A short listing silently under-refuses, which is the one direction a certifier must not fail in.
        raise SystemExit(f"prove-inert: cannot list the tree: {listed.stderr.strip()}")
    for rel in listed.stdout.split():
        try:
            names |= docstring_reader_names((root / rel).read_text())
        except OSError, SyntaxError, ValueError:
            unscanned += 1
    return frozenset(names), unscanned


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f"usage: {argv[0] if argv else 'prove-inert.py'} <base-rev> <path>...\n", file=sys.stderr)
        # The contract is met here, at the moment of use; printing it also makes this docstring
        # program output, so the tool's own refusal covers an edit to it.
        print(__doc__, file=sys.stderr)
        return EXIT_USAGE
    base, paths = argv[1], argv[2:]
    root = _repo_root()
    # Lexical membership, `git show`'s cwd and `root / path` agree only here, and exit 0 is a licence.
    if pathlib.Path.cwd() != root:
        print(f"prove-inert: run from the repo root ({root}), not {pathlib.Path.cwd()}\n", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return EXIT_USAGE
    output_names, unscanned = output_names_in(root)
    print(f"after-side tree: {root}")
    if unscanned:
        print(f"WARNING: {unscanned} file(s) could not be scanned for docstring readers")
    closure = replay_closure()
    relative: frozenset[str] = frozenset()
    unreadable: str | None = None
    if isinstance(closure, str):
        unreadable = f"the replay closure could not be read ({closure}); it needs an importable `cli` -- try `uv run`"
    else:
        relative, closure_root = closure
        print(f"replay closure describes: {closure_root} ({len(relative)} files)")
    worst = EXIT_INERT
    for path in paths:
        # Ahead of the arms, because a clean shape is exactly what makes such a file's edit look free.
        if unreadable is not None:
            print(f"{path}: REFUSED -- {unreadable}")
            worst = worse(worst, EXIT_REFUSED)
            continue
        if os.path.normpath(path) in relative:
            # Membership, never a diagnosis: the arms never ran, so nothing here knows what changed.
            print(f"{path}: REFUSED -- `replay_fingerprint` digests this file, so any byte of it rebuilds the gate cache")
            worst = worse(worst, EXIT_REFUSED)
            continue
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
