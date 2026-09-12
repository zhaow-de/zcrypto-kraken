"""The merge-pr gate: every reason a pull request is not ready to merge, or GATE PASSED."""

from __future__ import annotations

import html
import json
import pathlib
import re
import subprocess
import sys
import unicodedata

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
# The Fable floor is substitutable, and only by a line that says so in the body. An Opus read on a Fable path
# passes when this line carries a reason -- written where the merge decision is read, so the substitution is
# visible to whoever opens the PR later, instead of being a gate nobody can see was bypassed.
SUBSTITUTE = re.compile(r"^Fable floor substituted by Opus: *(\S.*?) *$", re.M)
# A reason has to be one somebody wrote. These are the strings that arrive when nobody did: the placeholder this
# repo prints in its own instructions (the sibling READ_LINE arm below refuses `<...>` for the same reason), and
# the tokens a filler reaches for. The content bar is distinct alphanumerics rather than length, so a short honest
# reason in any script passes -- `no Fable` and `Fable配額已用盡` are reasons; `aaaaaaaaaaaa` and `............`
# are not.
_PLACEHOLDER = re.compile(r"^(?:todo|tbd|n/?a|none|x|reason|why|fill in|placeholder)\b", re.I)
_MIN_REASON_CHARS = 6
_MIN_DISTINCT = 3
# Zero-width and other format characters pad a reason to any length while rendering as nothing, so they go before
# anything is measured; HTML entities are unescaped first, because `&lt;reason&gt;` renders as the placeholder the
# `<` check exists to refuse; and NFKC folds the fullwidth forms of the filler tokens onto the tokens themselves.
_INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u2028-\u202e\u2060-\u2064\ufeff]")


def _normalised(reason: str) -> str:
    reason = unicodedata.normalize("NFKC", html.unescape(reason))
    return " ".join(_INVISIBLE.sub("", reason).split())


def _is_a_stated_reason(reason: str) -> bool:
    """Whether a reason says something. A determined author can always write a plausible falsehood; what this
    refuses is the reason nobody wrote -- the placeholder, a filler token, a run of one character."""
    reason = _normalised(reason)
    if reason.startswith("<") or _PLACEHOLDER.match(reason):
        return False
    if len(reason) < _MIN_REASON_CHARS:
        return False
    return len({c.casefold() for c in reason if c.isalnum()}) >= _MIN_DISTINCT


# A body is read as a reader sees it, which a pair of regexes cannot do: an unterminated `<!--` hides everything
# after it in the rendered page, a fence closes only on a run of its own character at least as long as its opener
# (so a ``` inside a ```` block is content, not a close), and an unterminated fence renders the rest as code. Each
# of those hid a line from the reader while a regex pass still saw it, and the mirror failure is as bad: a stray
# line-initial fence, or a `-->` in the author's own prose under the template's comment opener, swallowed a real
# read line and the gate then refused a legitimate PR for the wrong reason. So the body is walked once, in order,
# with the state a renderer keeps. `<details>` goes with them: collapsed by default is not visible either.
_FENCE_OPEN = re.compile(r"^(?P<run>`{3,}|~{3,})")


def _as_a_reader_sees_it(body: str) -> str:
    """The body with everything a rendered PR hides removed: comments (terminated or not), fenced blocks (nested
    or not), `<details>` blocks, and quoted lines."""
    visible: list[str] = []
    fence: str | None = None  # the opening run, when inside a fenced block
    hidden_to_end = False  # an unterminated comment or details block hides the rest of the document
    in_comment = False
    in_details = False
    for raw in body.splitlines():
        if hidden_to_end:
            break
        line = raw
        if fence is not None:
            run = _FENCE_OPEN.match(line.lstrip())
            if run and run.group("run")[0] == fence[0] and len(run.group("run")) >= len(fence):
                fence = None
            continue
        if in_comment or in_details:
            closer = "-->" if in_comment else "</details>"
            if closer not in line:
                continue
            line = line.split(closer, 1)[1]
            in_comment = in_details = False
        # Comments and details are resolved before fences: inside a fence there is no markup to resolve, and a
        # fence opener is only an opener when the line is not already hidden.
        while True:
            if "<!--" in line:
                before, rest = line.split("<!--", 1)
                if "-->" in rest:
                    line = before + rest.split("-->", 1)[1]
                    continue
                visible.append(before)
                in_comment, hidden_to_end = True, False
                line = None
                break
            if "<details" in line:
                before, rest = line.split("<details", 1)
                if "</details>" in rest:
                    line = before + rest.split("</details>", 1)[1]
                    continue
                visible.append(before)
                in_details = True
                line = None
                break
            break
        if line is None:
            continue
        run = _FENCE_OPEN.match(line.lstrip())
        if run:
            fence = run.group("run")
            continue
        if line.lstrip().startswith(">"):
            continue
        visible.append(line)
    return "\n".join(visible)


def _hidden_hint(body: str, pattern: re.Pattern[str]) -> str:
    """A clause for the refusal when the line IS in the body and is hidden from the rendered page. Without it the
    gate reports the line as missing, and an author looking straight at it has no way to tell what happened."""
    if pattern.search(body) and not pattern.search(_as_a_reader_sees_it(body)):
        return (
            " — the line is in the body but hidden from the rendered page: an HTML comment (terminated or not), a "
            "fenced block, or a quoted line"
        )
    return ""


def _substitution_reason(body: str) -> str | None:
    """The stated reason for substituting Opus for the Fable floor, or None when the body states none a reader
    would accept. Every occurrence is considered, not the first: a leftover placeholder line above a filled one is
    the natural accident once the line is instructed as a template, and it must not refuse the filled one."""
    for m in SUBSTITUTE.finditer(_as_a_reader_sees_it(body)):
        if _is_a_stated_reason(m.group(1)):
            return _normalised(m.group(1))
    return None


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
    m = READ_LINE.search(_as_a_reader_sees_it(body))
    if not m or m.group(1).strip().startswith("<"):
        return [
            "no 'Read before push by: <model> at <sha>' line in the body: the whole-branch read is unrecorded"
            + _hidden_hint(body, READ_LINE)
        ]
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
        if touched and _substitution_reason(body) is None:
            more = f" and {len(touched) - 1} more" if len(touched) > 1 else ""
            return [
                f"the read named in the body was by {model!r}, and the PR touches {touched[0]}{more}: the floor there is "
                f"Claude Fable, or a body line 'Fable floor substituted by Opus: <reason>' saying why it is not available"
                + (
                    _hidden_hint(body, SUBSTITUTE)
                    or (
                        " — the body carries the line, and its reason is the placeholder, a filler token, or too "
                        "little to be a reason"
                        if SUBSTITUTE.search(_as_a_reader_sees_it(body))
                        else ""
                    )
                )
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
    m = READ_LINE.search(_as_a_reader_sees_it(pr.get("body") or ""))
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
