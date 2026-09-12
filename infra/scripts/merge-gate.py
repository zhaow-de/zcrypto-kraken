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
# A fence opener, CommonMark's shape: at most three spaces of indent, a run of three or more backticks or
# tildes, and for a backtick fence an info string with no backtick in it (`” ```gh pr view``` ”` is a paragraph,
# not an opener). The bound matters in both directions -- four spaces is an indented code block, which RENDERS
# its backticks, and treating it as an opener hid the rest of a body that a reader can see in full.
_FENCE_OPEN = re.compile(r"^ {0,3}(?P<run>`{3,}|~{3,})(?P<info>[^`]*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(?P<run>`{3,}|~{3,}) *$")
# An inline code span renders its content as text, so a `<!--` or a `</details>` inside one is neither an opener
# nor a closer. Masking keeps the line's length, so an index found in the masked line slices the real one.
_CODE_SPAN = re.compile(r"(?P<ticks>`+)(?:(?!(?P=ticks)).)*(?P=ticks)", re.S)
# `--!>` closes a comment in every browser, so a body using it renders in full and the gate must agree.
_COMMENT_CLOSE = re.compile(r"--!?>")


def _outside_code_spans(line: str) -> str:
    """The line with each inline code span blanked to spaces -- same length, so offsets still line up."""
    return _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)


def _as_a_reader_sees_it(body: str) -> str:
    """The body with everything a rendered PR hides removed: comments (terminated or not, `--!>` included), fenced
    blocks (nested or not), `<details>` blocks, and quoted lines.

    Two rules keep this close to a renderer without becoming one. A fence is decided on the RAW line, because a
    renderer settles fences before it ever looks for inline markup. And a comment or `<details>` HIDES what
    follows it only when it opens the line -- an HTML block -- while one that opens and closes inside a line just
    takes its own span with it; an unterminated `<!--` in the middle of a sentence renders as text, and treating
    it as an opener threw away the rest of a body a reader can see in full.
    """
    visible: list[str] = []
    fence: str | None = None  # the opening run, when inside a fenced block
    in_comment = False
    in_details = False
    for raw in body.splitlines():
        line = raw
        if fence is not None:
            run = _FENCE_CLOSE.match(line)
            if run and run.group("run")[0] == fence[0] and len(run.group("run")) >= len(fence):
                fence = None
            continue
        if in_comment or in_details:
            masked = _outside_code_spans(line)
            if in_comment:
                m = _COMMENT_CLOSE.search(masked)
                if not m:
                    continue
                line, in_comment = line[m.end() :], False
            else:
                at = masked.find("</details>")
                if at < 0:
                    continue
                line, in_details = line[at + len("</details>") :], False
        opener = _FENCE_OPEN.match(line)
        if opener:
            fence = opener.group("run")
            continue
        # An inline comment or details element, opened and closed on this line, takes its own span and nothing
        # more. Code spans are masked so a `<!--` written as prose about this gate is not read as markup.
        while True:
            masked = _outside_code_spans(line)
            pairs = []
            at = masked.find("<!--")
            if at >= 0:
                closer = _COMMENT_CLOSE.search(masked, at)
                if closer:
                    pairs.append((at, closer.end()))
            at = masked.find("<details")
            if at >= 0:
                close_at = masked.find("</details>", at)
                if close_at >= 0:
                    pairs.append((at, close_at + len("</details>")))
            if not pairs:
                break
            a, b = min(pairs)
            line = line[:a] + line[b:]
        # A block-level opener -- first non-space text on the line -- hides every line until its closer, or to the
        # end of the document when it has none, which is what a renderer does with it.
        stripped = line.lstrip()
        if stripped.startswith("<!--"):
            in_comment = True
            continue
        if stripped.startswith("<details"):
            in_details = True
            continue
        if stripped.startswith(">"):
            continue
        visible.append(line)
    return "\n".join(visible)


def _unterminated_opener(body: str) -> int | None:
    """The line index where a comment, `<details>` or fence opens and never closes, or None when the body closes
    everything it opens. Such a construct hides every line after it in the rendered page, and it is the shape a
    walk imitating a renderer is most likely to disagree about."""
    fence: str | None = None
    opened_at: int | None = None
    in_comment = in_details = False
    for i, raw in enumerate(body.splitlines()):
        line = raw
        if fence is not None:
            run = _FENCE_CLOSE.match(line)
            if run and run.group("run")[0] == fence[0] and len(run.group("run")) >= len(fence):
                fence, opened_at = None, None
            continue
        if in_comment or in_details:
            masked = _outside_code_spans(line)
            if in_comment:
                m = _COMMENT_CLOSE.search(masked)
                if not m:
                    continue
                line, in_comment, opened_at = line[m.end() :], False, None
            else:
                at = masked.find("</details>")
                if at < 0:
                    continue
                line, in_details, opened_at = line[at + len("</details>") :], False, None
        opener = _FENCE_OPEN.match(line)
        if opener:
            fence, opened_at = opener.group("run"), i
            continue
        stripped = _outside_code_spans(line).lstrip()
        if stripped.startswith("<!--") and not _COMMENT_CLOSE.search(stripped):
            in_comment, opened_at = True, i
        elif stripped.startswith("<details") and "</details>" not in stripped:
            in_details, opened_at = True, i
    return opened_at


def _before_anything_that_can_hide(body: str) -> str:
    """The body up to an unterminated comment, `<details>` or fence, which hides everything after it.

    Defence in depth for the arm that LIFTS a floor: the walk above tries to be a renderer, and a renderer has
    more edge cases than a reviewer can enumerate -- two of them got a substitution past an earlier version of
    it. A terminated construct is left alone, since the walk removes it and the reader sees the rest; it is the
    unterminated one, where the page and the walk can disagree about everything below, that the line may not sit
    under.
    """
    at = _unterminated_opener(body)
    return body if at is None else "\n".join(body.splitlines()[:at])


def _hidden_hint(body: str, pattern: re.Pattern[str]) -> str:
    """A clause for the refusal when the line IS in the body and is hidden from the rendered page. Without it the
    gate reports the line as missing, and an author looking straight at it has no way to tell what happened."""
    if pattern.search(body) and not pattern.search(_as_a_reader_sees_it(body)):
        return (
            " — the line is in the body but hidden from the rendered page: an HTML comment (terminated or not), a "
            "fenced block, a `<details>` block, or a quoted line"
        )
    return ""


def _substitution_hint(body: str) -> str:
    """A clause naming which of the two remaining refusals this is: the line sits below something that could have
    hidden it, or the line is where it should be and its reason is not one."""
    visible = _as_a_reader_sees_it(body)
    if not SUBSTITUTE.search(visible):
        return ""
    if not SUBSTITUTE.search(_as_a_reader_sees_it(_before_anything_that_can_hide(body))):
        return (
            " — the line sits below a comment, a `<details>` block or a fenced block; it counts only in the body's "
            "plain prefix, which is where `open-pr` puts it, directly under the read line"
        )
    return " — the body carries the line, and its reason is the placeholder, a filler token, or too little to be a reason"


def _substitution_reason(body: str) -> str | None:
    """The stated reason for substituting Opus for the Fable floor, or None when the body states none a reader
    would accept. Every occurrence is considered, not the first: a leftover placeholder line above a filled one is
    the natural accident once the line is instructed as a template, and it must not refuse the filled one."""
    for m in SUBSTITUTE.finditer(_as_a_reader_sees_it(_before_anything_that_can_hide(body))):
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
                + (_hidden_hint(body, SUBSTITUTE) or _substitution_hint(body))
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
