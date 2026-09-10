"""The merge-pr gate: every reason a pull request is not ready to merge, or GATE PASSED."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REPO = "zhaow-de/zcrypto-kraken"
GUARD = pathlib.Path(__file__).with_name("guidance-guard.py")
INDEX = "docs/reference/change-index.md"
JOURNAL = "docs/reference/ops-journal/"
FIELDS = "number,headRefName,baseRefName,state,mergeable,mergeStateStatus,reviewDecision,isDraft,statusCheckRollup,body,headRefOid"
READ_LINE = re.compile(r"^Read before push by: *(.+?) +at +([0-9a-f]{7,40}) *$", re.M)
FLOOR = re.compile(r"Claude (Opus|Fable)\b", re.I)
FABLE_PATHS = (
    "CLAUDE.md",
    ".claude/",
    "cli/engine/",
    "cli/capture/",
    "infra/ansible/roles/capture/",
    "infra/ansible/roles/engine/",
)
_DONE = ("SUCCESS", "NEUTRAL", "SKIPPED")
_BAD = ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "STARTUP_FAILURE")


def _state(check: dict) -> str:
    return (check.get("conclusion") or check.get("state") or "").upper()


def _fable_paths_touched(files: list[str]) -> list[str]:
    return sorted(p for p in files if any(p == g or (g.endswith("/") and p.startswith(g)) for g in FABLE_PATHS))


def read_line_fails(pr: dict, head_commit: dict | None, files: list[str] | None) -> list[str]:
    """The read is at the floor and names the head, or the head is the one change-index row commit past the tip it names."""
    if pr.get("headRefName") == "ops-journal":
        if files is None:
            return ["the PR's file list was not fetched, so the ops-journal exemption cannot be scoped to the journal files"]
        if all(f.startswith(JOURNAL) for f in files):
            return []  # a month of journal entries has nothing for a reviewer to read (docs/reference/ops-journal/README.md)
    body = pr.get("body") or ""
    head = pr.get("headRefOid") or ""
    m = READ_LINE.search(body)
    if not m or m.group(1).strip().startswith("<"):
        return ["no 'Read before push by: <model> at <sha>' line in the body: the whole-branch read is unrecorded"]
    model, sha = m.group(1).strip(), m.group(2)
    family = FLOOR.match(model)
    if not family:
        return [
            f"the read named in the body was by {model!r}; the floor is Claude Opus, and Claude Fable where the PR touches {', '.join(FABLE_PATHS)}"
        ]
    if family.group(1).lower() == "opus":
        if files is None:
            return ["the PR's file list was not fetched, so the paths that need a Fable read cannot be checked"]
        touched = _fable_paths_touched(files)
        if touched:
            more = f" and {len(touched) - 1} more" if len(touched) > 1 else ""
            return [
                f"the read named in the body was by {model!r}, and the PR touches {touched[0]}{more}: the floor there is Claude Fable"
            ]
    if head.startswith(sha):
        return []
    if head_commit is not None:
        parents = [p.get("sha") or "" for p in head_commit.get("parents") or []]
        files = [f.get("filename") for f in head_commit.get("files") or []]
        if len(parents) == 1 and parents[0].startswith(sha) and files == [INDEX]:
            return []
    return [
        f"the read named in the body covers {sha[:8]}, not the head {head[:8]}: read the delta or re-read, then update the line"
    ]


def evaluate(
    pr: dict, head_commit: dict | None = None, files: list[str] | None = None, branch_growth: list[str] | None = None
) -> list[str]:
    """branch_growth is guidance-guard.py --range's refusals over the branch, [] when it refused nothing; None means it was not run."""
    fails: list[str] = []
    base = pr.get("baseRefName")
    state = pr.get("state")
    mergeable = pr.get("mergeable")
    rollup = pr.get("statusCheckRollup") or []
    body = pr.get("body") or ""
    if base != "develop":
        fails.append(f"base branch is {base!r}, not develop (feature PRs never merge to main)")
    if state != "OPEN":
        fails.append(f"state is {state!r}, expected OPEN")
    if pr.get("isDraft"):
        fails.append("PR is a draft")
    if mergeable == "CONFLICTING":
        fails.append("mergeable=CONFLICTING (conflicts) — update the branch and resolve first")
    elif mergeable != "MERGEABLE":
        fails.append(f"mergeable={mergeable!r} — GitHub is still computing; re-run in a moment, never merge on UNKNOWN")
    if pr.get("mergeStateStatus") == "BLOCKED":
        fails.append("mergeStateStatus=BLOCKED (branch protection: a required review or required check is unsatisfied)")
    if pr.get("reviewDecision") == "CHANGES_REQUESTED":
        fails.append("reviewDecision=CHANGES_REQUESTED (a reviewer requested changes)")
    bad = [c for c in rollup if _state(c) in _BAD]
    if bad:
        fails.append(f"{len(bad)} CI check(s) failing")
    pending = [c for c in rollup if _state(c) not in _DONE + _BAD]
    if pending:
        fails.append(f"{len(pending)} CI check(s) still running — wait; nothing else blocks a merge on pending")
    if not rollup:
        fails.append("no CI checks reported yet — wait for coverage.yml to register")
    if "- [ ]" in body:
        fails.append("PR description has unchecked checklist item(s) (- [ ])")
    fails.extend(read_line_fails(pr, head_commit, files))
    if branch_growth is None:
        fails.append(
            "the branch's ambient growth was not checked commit by commit: `guidance-guard.py --range <base>..<head>` did not run"
        )
    fails.extend(branch_growth or [])
    return fails


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, timeout=60).stdout


def branch_growth(base_ref: str, head_ref: str, head: str) -> list[str]:
    """Fetch both branches, then judge every commit past the merge base against its parent through the guard's range mode; each refusal of a commit names it, and a branch that cannot be fetched, based or judged is one refusal, never a crash."""
    try:
        subprocess.run(
            ["git", "fetch", "-q", "origin", base_ref, head_ref], check=True, capture_output=True, text=True, timeout=120
        )
        merge_base = subprocess.run(
            ["git", "merge-base", f"origin/{base_ref}", head], check=True, capture_output=True, text=True
        ).stdout.strip()
        done = subprocess.run(
            [sys.executable, str(GUARD), "--range", f"{merge_base}..{head}"], capture_output=True, text=True, timeout=300
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = ((getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or "") or "").strip()
        if not detail and list(exc.cmd[:2]) == ["git", "merge-base"]:
            detail = f"no merge base between origin/{base_ref} and {head[:8]}"  # git says nothing and exits 1
        return [f"the branch could not be checked commit by commit: {detail or str(exc)}"]
    if done.returncode == 0:
        return []
    refusals = [line[4:] for line in done.stdout.splitlines() if line.startswith("  - ")]
    if refusals:
        return [f"a commit fails the guidance guard against its parent — {r}" for r in refusals]
    return [f"the branch could not be checked commit by commit: {(done.stdout + done.stderr).strip()}"]


def main(argv: list[str]) -> int:
    if argv[1:] == ["--fable-paths"]:
        print("\n".join(FABLE_PATHS))  # the one copy of the list; CLAUDE.md names this command instead of repeating it
        return 0
    number = argv[1:2]
    pr = json.loads(_gh("pr", "view", *number, "--json", FIELDS))
    head_commit = files = None
    m = READ_LINE.search(pr.get("body") or "")
    head = pr.get("headRefOid") or ""
    if m or pr.get("headRefName") == "ops-journal":
        files = _gh("api", "--paginate", f"repos/{REPO}/pulls/{pr['number']}/files", "--jq", ".[].filename").split()
    if m and head and not head.startswith(m.group(2)):
        head_commit = json.loads(_gh("api", f"repos/{REPO}/commits/{head}"))
    fails = evaluate(pr, head_commit, files, branch_growth(pr["baseRefName"], pr["headRefName"], head))
    if fails:
        print("GATE FAILED:")
        for fail in fails:
            print("  - " + fail)
        return 1
    print("GATE PASSED — ready to merge")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
