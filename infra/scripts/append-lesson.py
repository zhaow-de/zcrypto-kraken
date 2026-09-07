#!/usr/bin/env python3
"""Append one validated record to this session's inbox in the MAIN checkout, never a worktree's.
Validation is `check-agent-lessons.py`'s `record_errors`, so the harvest's shape and a writer's
cannot drift apart; a refusal writes nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

_CHECKER = pathlib.Path(__file__).resolve().parent / "check-agent-lessons.py"


def _validator():
    spec = importlib.util.spec_from_file_location("check_agent_lessons", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main_checkout(cwd: pathlib.Path | None = None) -> pathlib.Path:
    """The first `git worktree list` row: a worktree's own inbox is removed when its branch merges."""
    cmd = ["git", "worktree", "list", "--porcelain"]
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout.splitlines()
    if not out or not out[0].startswith("worktree "):
        raise RuntimeError(f"no worktree row in `git worktree list --porcelain`: {out[:1]}")
    return pathlib.Path(out[0].removeprefix("worktree ")).resolve()


def build(args: argparse.Namespace, now: str) -> dict:
    cites = [c.strip() for c in args.cites.split(",")] if args.cites else []
    return {
        "ts": now,
        "session": args.session,
        "branch": args.branch,
        "kind": args.kind,
        "cites": cites,
        "what": args.what,
        "why": args.why,
    }


def run(argv: list[str], cwd: pathlib.Path | None = None, now: str | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for flag in ("session", "branch", "kind", "what", "why"):
        parser.add_argument(f"--{flag}", required=True)
    parser.add_argument("--cites", default="", help="comma-separated; empty for none")
    args = parser.parse_args(argv)

    stamp = now or dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = build(args, stamp)

    problems = _validator().record_errors(record)
    if problems:
        for problem in problems:
            print(f"append-lesson: refused — {problem}", file=sys.stderr)
        return 1

    try:
        root = main_checkout(cwd)
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        detail = getattr(exc, "stderr", None) or exc
        print(f"append-lesson: refused — cannot resolve the main checkout: {detail}", file=sys.stderr)
        return 2
    # The session names ONE file in the inbox directory: a name carrying `/` or `..` resolves to a path
    # still inside the checkout, which a containment check against the ROOT accepts and the harvest
    # never reads -- a lesson written, reported appended, and lost.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.session):
        print(f"append-lesson: refused — {args.session!r} is not a session name", file=sys.stderr)
        return 2
    inbox_dir = (root / ".local" / "agent-lessons").resolve()
    inbox = inbox_dir / f"{args.session}.jsonl"
    if not inbox_dir.is_dir():
        print(f"append-lesson: refused — {inbox_dir} does not exist", file=sys.stderr)
        return 2

    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"append-lesson: appended to {inbox}")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
