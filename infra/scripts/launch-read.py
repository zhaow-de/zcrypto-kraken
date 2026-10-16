#!/usr/bin/env python3
"""The arguments a pre-review, review or re-review is launched with, and a dispatch brief's standing lines.

`args` prints the JSON object the workflow takes: each rev resolved by git to its full sha, `ledger` read by
`review-ledger.py read` against that same tip, and some of the workflow's refusals made before the launch.
`brief` appends the standing-lines file to a brief unless the brief already carries it, and prints the brief's path.
rc: 0 printed, 2 refused with the rule named on stderr.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("review_ledger", _HERE / "review-ledger.py")
review_ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review_ledger)

STANDING_LINES = _HERE.parents[1] / ".claude/skills/zcrypto-plan-review/references/standing-lines.md"
DRIVE_CAP = 400
LABEL = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
SEVERITIES = ("Critical", "Important")
MODELS = {"pre-review": ("opus",), "review": ("opus", "fable"), "re-review": ("opus", "fable")}
TAKES = {
    "pre-review": {"rulings", "ranges", "worktree"},
    "review": {"drive", "lenses"},
    "re-review": {"prior", "reported", "drive", "left"},
}


class Refused(Exception):
    pass


def resolve(repo: pathlib.Path, rev: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if done.returncode:
        raise Refused(f"{rev!r} names no commit in {repo}: a rev is resolved by git, never extended or typed by hand")
    return done.stdout.strip()


def js_length(text: str) -> int:
    """`drive.length` as the workflow measures it: UTF-16 code units, so a character outside the BMP counts two."""
    return len(text.encode("utf-16-le")) // 2


def objects(flag: str, path: pathlib.Path, item: str) -> list[dict]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"--{flag} {path} is not readable JSON ({exc})") from exc
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise Refused(f"--{flag} {path} is not a JSON array of {item} objects")
    return rows


def priors(path: pathlib.Path) -> list[dict]:
    rows = objects("prior", path, "finding")
    for row in rows:
        if row.get("severity") not in SEVERITIES:
            raise Refused(
                f"prior #{row.get('id')} is {row.get('severity')}: a prior is Critical or Important — a Minor goes in "
                "--reported as context, fixed or left with its reason"
            )
    return rows


def slices(specs: list[str], base: str, tip: str, repo: pathlib.Path) -> list[dict]:
    out = []
    for spec in specs:
        label, sep, span = spec.partition("=")
        ends = span.split("..")
        if not sep or len(ends) != 2 or not all(ends) or "..." in span:
            raise Refused(f"--ranges {spec!r} is not <label>=<base>..<tip>")
        if not LABEL.match(label):
            raise Refused(f"--ranges label {label!r} is not 1 to 32 of lowercase, digits and dashes, opening with no dash")
        out.append({"label": label, "range": f"{resolve(repo, ends[0])}..{resolve(repo, ends[1])}"})
    labels = [s["label"] for s in out]
    if len(set(labels)) != len(labels):
        raise Refused(f"--ranges labels are not unique: {', '.join(labels)}")
    chain = "the slices chain from --base to --tip, each opening where the one before it closes, none empty"
    opening = base
    for s in out:
        start, end = s["range"].split("..")
        if start != opening:
            raise Refused(f"{chain}: {s['label']} opens at {start}, not at {opening}")
        if start == end:
            raise Refused(f"{chain}: {s['label']} is empty")
        opening = end
    if opening != tip:
        raise Refused(f"{chain}: the last slice closes at {opening}, not at --tip {tip}")
    return out


def build(a: argparse.Namespace) -> dict:
    given = ("prior", "reported", "drive", "rulings", "ranges", "left", "worktree", "lenses")
    stray = [n for n in given if getattr(a, n) is not None and n not in TAKES[a.kind]]
    if stray:
        raise Refused(f"{a.kind} takes no {', '.join('--' + n for n in stray)}: the workflow would drop it unread")
    if a.model not in MODELS[a.kind]:
        raise Refused(f"{a.kind} runs on {' or '.join(MODELS[a.kind])}, never {a.model}")
    if a.kind == "re-review" and a.prior is None:
        raise Refused("re-review takes --prior: the JSON array of the open Critical and Important findings it walks")
    if a.drive is not None and js_length(a.drive) > DRIVE_CAP:
        raise Refused(
            f"--drive is {js_length(a.drive)} characters, at most {DRIVE_CAP}: one sentence naming what the standing "
            "brief does not cover"
        )
    repo = a.repo.resolve()
    base, tip = resolve(repo, a.base), resolve(repo, a.tip)
    out: dict = {"repo": str(repo), "range": f"{base}..{tip}", "tip": tip}
    if a.prior is not None:
        out["prior"] = priors(a.prior)
    report_dir = a.report_dir.resolve()
    out["reportDir"] = str(report_dir)
    if a.worktree is not None:
        out["worktree"] = str(a.worktree.resolve())
    if a.kind != "pre-review":
        try:
            out["ledger"] = review_ledger.read(report_dir, tip, repo)
        except (review_ledger.LedgerError, OSError) as exc:
            raise Refused(str(exc)) from exc
    if a.lenses is not None:
        out["lenses"] = objects("lenses", a.lenses, "lens")
    for name in ("left", "reported", "drive", "rulings"):
        if getattr(a, name) is not None:
            out[name] = getattr(a, name)
    if a.ranges is not None:
        out["ranges"] = slices(a.ranges, base, tip, repo)
    out["model"] = a.model
    return out


def append_lines(brief: pathlib.Path, lines: pathlib.Path) -> pathlib.Path:
    try:
        standing = lines.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused(f"the standing-lines file {lines} is not readable ({exc.strerror})") from exc
    try:
        text = brief.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused(f"the brief {brief} is not readable ({exc.strerror})") from exc
    if not standing.strip():
        raise Refused(f"the standing-lines file {lines} is empty")
    if standing.strip() not in text:
        with brief.open("a", encoding="utf-8") as fh:
            fh.write(("" if not text or text.endswith("\n") else "\n") + standing.rstrip("\n") + "\n")
    return brief.resolve()


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    read = sub.add_parser("args")
    read.add_argument("kind", choices=tuple(MODELS))
    read.add_argument("--repo", type=pathlib.Path, required=True)
    read.add_argument("--base", required=True)
    read.add_argument("--tip", required=True)
    read.add_argument("--report-dir", type=pathlib.Path, required=True)
    read.add_argument("--prior", type=pathlib.Path, help="a JSON file holding the array of open Critical and Important findings")
    read.add_argument("--reported")
    read.add_argument("--left", help="each prior consciously left, by id (#<id>) with its reason")
    read.add_argument("--drive")
    read.add_argument(
        "--lenses", type=pathlib.Path, help="a JSON file holding the array of {name, brief} lenses read in place of the default two"
    )
    read.add_argument("--rulings")
    read.add_argument("--ranges", nargs="+", action="extend", metavar="LABEL=BASE..TIP")
    read.add_argument("--worktree", type=pathlib.Path, help="a detached worktree at the tip, already synced, the graders run in")
    read.add_argument("--model", choices=("opus", "fable"), default="opus")
    brief = sub.add_parser("brief")
    brief.add_argument("brief", type=pathlib.Path)
    brief.add_argument("--lines", type=pathlib.Path, default=STANDING_LINES)
    args = parser.parse_args(argv)
    try:
        if args.command == "args":
            print(json.dumps(build(args), ensure_ascii=False))
        else:
            print(append_lines(args.brief, args.lines))
    except Refused as exc:
        print(f"launch-read: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
