#!/usr/bin/env python3
"""The review ledger, `<reportDir>/ledger.jsonl`, kept by this script and never by a workflow agent.

`append` writes the row a pre-review, review or re-review returns, and for a review or re-review appends the
refutation block it returns to each report it names. `read` prints the entries a review or re-review takes as its
`ledger` argument, each pre-review entry at another tip carrying `sameTreeAndMessages` and the tip it was compared
against, which the workflows refuse when it is not their own.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

KINDS = ("pre-review", "review", "re-review")
SHA = re.compile(r"^[0-9a-f]{7,64}$")


class LedgerError(Exception):
    pass


def _sha(value: str) -> str:
    if not SHA.match(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a lowercase hex commit id of 7 to 64 digits")
    return value


def _range(value: str) -> str:
    ends = value.split("..")
    if len(ends) != 2 or not all(ends) or "..." in value or any(c.isspace() for c in value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a two-dot range `a..b`")
    return value


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True)


def same_tree_and_messages(repo: pathlib.Path, theirs: object, ours: str) -> bool:
    """A pre-review of `theirs` covers `ours` when both commits hold one tree and the commit messages from their
    merge base to each are the same bytes; an id git cannot resolve is false."""
    if not (isinstance(theirs, str) and SHA.match(theirs)):
        return False
    trees = [_git(repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{tree}}") for sha in (theirs, ours)]
    if any(t.returncode for t in trees) or trees[0].stdout != trees[1].stdout:
        return False
    base = _git(repo, "merge-base", theirs, ours)
    if base.returncode:
        return False
    since = base.stdout.decode().strip()
    logs = [_git(repo, "log", "--no-show-signature", "--format=%B", f"{since}..{sha}") for sha in (theirs, ours)]
    return not any(g.returncode for g in logs) and logs[0].stdout == logs[1].stdout


def read(report_dir: pathlib.Path, tip: str, repo: pathlib.Path) -> list[dict]:
    ledger = report_dir / "ledger.jsonl"
    if not ledger.exists():
        return []
    entries = []
    for n, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{ledger}:{n} is not JSON ({exc.msg}); mend the line by hand") from exc
        if not isinstance(entry, dict):
            raise LedgerError(f"{ledger}:{n} is not a JSON object; mend the line by hand")
        if entry.get("kind") == "pre-review" and entry.get("tip") != tip:
            entry["sameTreeAndMessages"] = same_tree_and_messages(repo, entry.get("tip"), tip)
            entry["against"] = tip
        entries.append(entry)
    return entries


def annotate(report: pathlib.Path, block: str) -> str | None:
    body = block.rstrip("\n") + "\n"
    if not report.exists():
        report.write_text(body, encoding="utf-8")
        return f"{report} did not exist: created holding the refutation block alone"
    text = report.read_text(encoding="utf-8")
    with report.open("a", encoding="utf-8") as fh:
        fh.write(("" if not text else "\n" if text.endswith("\n") else "\n\n") + body)
    return None


def append(report_dir: pathlib.Path, row: dict, refutation: pathlib.Path | None, reports: list[pathlib.Path]) -> list[str]:
    if not report_dir.is_dir():
        raise LedgerError(f"{report_dir} is not a directory: the reportDir the workflow was given")
    notes = []
    if refutation is not None:
        block = refutation.read_text(encoding="utf-8")
        if not block.strip():
            raise LedgerError(f"{refutation} is empty: it holds the `refutation` the workflow returned")
        notes = [note for report in reports if (note := annotate(report, block))]
    ledger = report_dir / "ledger.jsonl"
    held = ledger.read_bytes() if ledger.exists() else b""
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(("\n" if held and not held.endswith(b"\n") else "") + json.dumps(row, separators=(",", ":")) + "\n")
    return notes


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("append")
    add.add_argument("report_dir", type=pathlib.Path)
    add.add_argument("--kind", required=True, choices=KINDS)
    add.add_argument("--range", required=True, type=_range)
    add.add_argument("--tip", required=True, type=_sha)
    add.add_argument("--refutation", type=pathlib.Path, help="a file holding the `refutation` a review returned")
    add.add_argument("--report", action="append", default=[], type=pathlib.Path, help="a report it is appended to")
    get = sub.add_parser("read")
    get.add_argument("report_dir", type=pathlib.Path)
    get.add_argument("--tip", required=True, type=_sha)
    get.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."))
    args = parser.parse_args(argv)

    try:
        if args.command == "read":
            print(json.dumps(read(args.report_dir, args.tip, args.repo), ensure_ascii=False))
            return 0
        if (args.refutation is None) != (not args.report):
            raise LedgerError("--refutation and --report go together: the block and the reports it is appended to")
        if args.refutation is not None and args.kind == "pre-review":
            raise LedgerError("a pre-review returns no refutation block")
        stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = {"kind": args.kind, "range": args.range, "tip": args.tip, "ts": stamp}
        for note in append(args.report_dir, row, args.refutation, args.report):
            print(f"review-ledger: {note}", file=sys.stderr)
    except (LedgerError, OSError) as exc:
        print(f"review-ledger: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
