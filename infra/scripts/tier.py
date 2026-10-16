#!/usr/bin/env python3
"""The tier a change owes, one per diff: it decides both the spec+plan review and the mutate-probe rule.

    uv run python infra/scripts/tier.py <base>..<head> [--repo <path>]
    uv run python infra/scripts/tier.py --paths <path>... [--repo <path>]

The first line is `tier: full|light|none`; one line follows per path at that tier, `full <path> — <why>` or
`light <path>`, and a `none` tier lists none. rc 0; rc 2 on a usage or a git error.

Per file of `git diff --name-only --no-renames <base>..<head>` -- a rename is its old path and its new:
  none   a Markdown file under docs/ or infra/runbooks/; the diff is none only when every file is
  full   a file under FULL_PATHS, with `vault` in its path, with a changed line naming ohlc-holdout, or a changed
         tests/**/test_*.py importing a module under cli/engine, cli/capture or cli/registry -- unless
         `prove-inert.py <base> <file>` exits 0 (prose-only) or 3 (comments changed, nothing else) for it
  light  everything else
The diff's tier is the highest of its files. prove-inert reads the after side from the working tree, so a file
whose working copy differs from <head>, or that <head> deletes, is never made light by it.

`--paths` decides from the paths a plan names, before the code exists: each is read as a non-prose change -- no
diff, no prove-inert, no ohlc-holdout line -- and a listed test file is full when it exists and imports one of
those modules.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import pathlib
import subprocess
import sys

_HERE = pathlib.Path(__file__).resolve().parent
PROVE_INERT = _HERE / "prove-inert.py"


def _load_sibling(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


merge_gate = _load_sibling("merge_gate", "merge-gate.py")

FULL_PATHS = tuple(
    dict.fromkeys(
        (
            *merge_gate.FABLE_PATHS,
            "cli/engine/",
            "cli/capture/",
            "cli/registry/",
            "infra/ansible/",
            "infra/grafana/alerts.yaml",
            "docs/reference/trial-registry.jsonl",
        )
    )
)
PRODUCTION_MODULES = ("cli.engine", "cli.capture", "cli.registry")
NONE_DIRS = ("docs/", "infra/runbooks/")
VAULT = "vault"
HOLDOUT = "ohlc-holdout"
# prove-inert's INERT and COMMENTS CHANGED: a comment or docstring edit is light even under a full path.
LIGHT_EXITS = (0, 3)
RANK = {"none": 0, "light": 1, "full": 2}


class GitError(Exception):
    pass


def _git(root: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def _at(root: pathlib.Path, rev: str, path: str) -> str | None:
    done = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{path}"], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


def none_eligible(path: str) -> bool:
    return path.endswith(".md") and path.startswith(NONE_DIRS)


def is_test(path: str) -> bool:
    name = pathlib.PurePosixPath(path).name
    return path.startswith("tests/") and name.startswith("test_") and name.endswith(".py")


def production_imports(src: str) -> list[str] | None:
    """The modules under PRODUCTION_MODULES the source imports, None when it does not parse."""
    try:
        tree = ast.parse(src)
    except SyntaxError, ValueError:
        return None
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # `from cli import engine` imports the module cli.engine as surely as `import cli.engine` does.
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return sorted(n for n in names if any(n == m or n.startswith(f"{m}.") for m in PRODUCTION_MODULES))


def full_reason(path: str, *, names_holdout: bool, test_sources: list[str]) -> str | None:
    """Why a path is a full candidate before prove-inert is asked, None when it is not one."""
    for prefix in FULL_PATHS:
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            return f"under {prefix}"
    if VAULT in path.lower():
        return f"its path names {VAULT}"
    if names_holdout:
        return f"a changed line names {HOLDOUT}"
    if is_test(path):
        for src in test_sources:
            found = production_imports(src)
            if found is None:
                return "a test that does not parse, so its imports cannot be read"
            if found:
                return f"a test importing {found[0]}"
    return None


def names_holdout(root: pathlib.Path, base: str, head: str, path: str) -> bool:
    diff = _git(root, "diff", "-U0", "--no-renames", "--no-ext-diff", "--no-textconv", f"{base}..{head}", "--", path)
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line[:1] in ("+", "-") and HOLDOUT in line:
            return True
    return False


def comments_or_prose_only(root: pathlib.Path, base: str, head: str, path: str) -> tuple[bool, str]:
    """Whether prove-inert finds the file's change prose-only or comments alone, and, when not, what said so."""
    if _at(root, head, path) is None:
        return False, f"{head} deletes it"
    if subprocess.run(["git", "-C", str(root), "diff", "--quiet", head, "--", path], capture_output=True).returncode != 0:
        return False, f"the working tree differs from {head} there, and prove-inert reads the working tree"
    done = subprocess.run([sys.executable, str(PROVE_INERT), base, path], cwd=root, capture_output=True, text=True)
    if done.returncode in LIGHT_EXITS:
        return True, ""
    verdict = next((ln.removeprefix(f"{path}: ") for ln in done.stdout.splitlines() if ln.startswith(f"{path}: ")), "")
    return False, f"prove-inert exit {done.returncode}" + (f" ({verdict.split(' -- ')[0]})" if verdict else "")


def classify_diff(root: pathlib.Path, base: str, head: str) -> list[tuple[str, str, str]]:
    listed = _git(root, "diff", "--name-only", "-z", "--no-renames", f"{base}..{head}")
    out = []
    for path in (p for p in listed.split("\0") if p):
        if none_eligible(path):
            out.append(("none", path, ""))
            continue
        sources = [s for s in (_at(root, base, path), _at(root, head, path)) if s is not None] if is_test(path) else []
        reason = full_reason(path, names_holdout=names_holdout(root, base, head, path), test_sources=sources)
        if reason is None:
            out.append(("light", path, ""))
            continue
        proven, why = comments_or_prose_only(root, base, head, path)
        out.append(("light", path, "") if proven else ("full", path, f"{reason}; {why}"))
    return out


def classify_paths(root: pathlib.Path, paths: list[str]) -> list[tuple[str, str, str]]:
    out = []
    for raw in paths:
        path = os.path.normpath(raw)
        if os.path.isabs(path) and pathlib.Path(path).is_relative_to(root):
            path = pathlib.Path(path).relative_to(root).as_posix()
        if none_eligible(path):
            out.append(("none", path, ""))
            continue
        file = root / path
        sources = [file.read_text()] if is_test(path) and file.is_file() else []
        reason = full_reason(path, names_holdout=False, test_sources=sources)
        out.append(("full", path, f"{reason}, read as a non-prose change") if reason else ("light", path, ""))
    return out


def render(rows: list[tuple[str, str, str]]) -> list[str]:
    tier = max((t for t, _, _ in rows), key=RANK.__getitem__, default="none")
    lines = [f"tier: {tier}"]
    for t, path, why in rows:
        if t == tier == "full":
            lines.append(f"full {path} — {why}")
        elif t == tier == "light":
            lines.append(f"light {path}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="tier.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("range", nargs="?", help="<base>..<head>")
    parser.add_argument("--paths", nargs="+", help="the paths a plan names")
    parser.add_argument("--repo", default=".", help="a path inside the repository (default: the current directory)")
    args = parser.parse_args(argv[1:])
    if (args.range is None) == (args.paths is None):
        parser.error("give either <base>..<head> or --paths <path>...")
    if args.range is not None:
        base, sep, head = args.range.partition("..")
        if not sep or not base or not head or head.startswith("."):
            parser.error(f"the range must be <base>..<head>, not {args.range!r}")
    try:
        root = pathlib.Path(_git(pathlib.Path(args.repo), "rev-parse", "--show-toplevel").strip())
        if args.paths is not None:
            rows = classify_paths(root, args.paths)
        else:
            for rev in (base, head):
                _git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
            rows = classify_diff(root, base, head)
    except GitError as exc:
        print(f"tier.py: {exc}", file=sys.stderr)
        return 2
    print("\n".join(render(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
