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
# The rendered files a rebase onto a moved base resolves by hand: the change index and the topics index.
RENDERED = (INDEX, "docs/open-topics/README.md")
JOURNAL = "docs/reference/ops-journal/"
DEPENDABOT = "dependabot[bot]"
# `commits` is here because `read_line_fails`'s dependabot arm reads it: a field an arm reads and this
# fetch omits is not a missing exemption, it is a refusal on every PR of that shape.
FIELDS = "number,headRefName,baseRefName,state,mergeable,mergeStateStatus,reviewDecision,isDraft,statusCheckRollup,body,headRefOid,commits"
READ_LINE = re.compile(r"^Read before push by: *(.+?) +at +([0-9a-f]{7,40}) *$", re.M)
# The key grammar of `_keys` in tests/test_change_index.py, which decides whether a merge owes a row: only
# its topic alternative case-folds, so a global re.I here would make `ITER-7` a key to the gate alone.
BRANCH_KEY = re.compile(r"\biter-\d{1,3}\b|\b\d{5}\b|\b[Tt]\d{4}\b")
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
# A tilde fence's info string may carry backticks; a backtick fence's may not (`” ```gh pr view``` ”` is a
# paragraph, not an opener). The bound therefore belongs to the backtick branch alone -- applied to both, it
# declined a tilde opener that a renderer honours, and everything below it counted as body.
_FENCE_OPEN = re.compile(r"^ {0,3}(?:(?P<run>`{3,})[^`]*|(?P<trun>~{3,}).*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(?P<run>`{3,}|~{3,}) *$")
# A checkbox is a list item whose text opens with `[ ]`; the marker inside a code span or mid-sentence renders as text.
# `(?:> *)*` admits a box behind a quote marker the walk left in place -- one the marker regex declines: indented four
# or more columns, which is a list item's nested content or indented code, or set off by a character that is content
# rather than indent, which is a paragraph. The walk tracks no list, so such a marker hides nothing and its box still
# counts: loud wherever the page draws no box there, never silent where it draws one.
_UNCHECKED_BOX = re.compile(r"^\s*(?:> *)*(?:[-*+]|\d+[.)]) +\[ \]", re.M)
# A marker may be indented at most three spaces, and only spaces -- the first from column 0, a nested one from the end
# of the marker containing it, as the page measures each: this walk tracks no list item, so a marker further in opens
# nothing (see `_UNCHECKED_BOX` for what it still counts).
_QUOTE_MARKERS = re.compile(r"^(?: {0,3}> ?)+")


def _quote_depth(raw: str) -> int:
    """How many blockquotes a line sits in, by its leading markers."""
    m = _QUOTE_MARKERS.match(raw)
    return m.group(0).count(">") if m else 0


def _at_depth(raw: str, depth: int) -> str:
    """The line as the blockquote `depth` levels deep sees it: that many markers, and the indent before them, off."""
    return re.sub(rf"^(?: {{0,3}}> ?){{{depth}}}", "", raw)


# What CommonMark's condition 6 admits after the tag name; `\b` would open a block on `<details-x> text`, a paragraph.
_TAG_END = r"(?=[ \t>]|/>|$)"
_HTML_BLOCK_TAG = re.compile(r"</?(?:details|summary)" + _TAG_END)
_OPENERS = ("<!--", "<details", "</details", "<summary", "</summary")
# An inline code span renders its content as text, so a `<!--` or a `</details>` inside one is neither an opener
# nor a closer. Masking keeps the line's length, so an index found in the masked line slices the real one.
_CODE_SPAN = re.compile(r"(?P<ticks>`+)(?:(?!(?P=ticks)).)*(?P=ticks)", re.S)
# `--!>` closes a comment in every browser, so a body using it renders in full and the gate must agree.
_COMMENT_CLOSE = re.compile(r"--!?>")


def _outside_code_spans(line: str) -> str:
    """The line with each inline code span blanked to spaces -- same length, so offsets still line up."""
    return _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)


def _as_a_reader_sees_it(body: str, *, keep_collapsed: bool = False) -> str:
    """The body with everything a rendered PR hides removed: comments (terminated or not, `--!>` included), fenced
    blocks (nested or not), `<details>` blocks, and quoted lines.

    `keep_collapsed` keeps the two a renderer still shows: `<details>` content and quoted lines. The read line must
    be plainly visible, so it is judged without them; a checklist item inside either is an item GitHub renders and
    counts, so gate 6 is judged with them -- as the page renders them. A `<details>` or `<summary>` line, opening or
    closing, opens an HTML block that runs to the next blank line (CommonMark block condition 6) -- blank at the
    quote depth the block opened under, so a `>`-only line is content to an unquoted block -- and inside it nothing
    is markdown, so a box written there is literal text and not counted.

    Two rules keep this close to a renderer without becoming one. A fence is decided before any inline markup is
    masked, because a renderer settles fences first -- and, under `keep_collapsed`, on the line with its quote
    markers off, since a fence inside a blockquote is still a fence. And a comment or `<details>` HIDES what
    follows it only when it opens the line and closes on a later one -- an HTML block; treating an unterminated
    `<!--` in the middle of a sentence as an opener threw away the rest of a body a reader can see in full.
    """
    visible: list[str] = []
    fence: str | None = None  # the opening run, when inside a fenced block
    in_comment = False
    in_details = False
    html_block = False  # keep_collapsed only: inside a details/summary HTML block, up to its blank line
    open_depth = 0  # keep_collapsed only: the quote depth the open fence or comment began at; 0 when not quoted
    html_depth = 0  # keep_collapsed only: the same for the open HTML block
    for raw in body.splitlines():
        # A fence, comment or HTML block opened inside a blockquote takes no lazy continuation, so the first line
        # at a lesser quote depth ends the blockquote and closes it; a fence opened outside a quote treats a quoted
        # line as literal content.
        # Under keep_collapsed every derivation that measures a column works on the line with tabs expanded from
        # its own start, which is the column the page counts from, so a tab after a quote marker measures as the
        # page measures it; inside an unquoted fence the line is literal content and is read raw.
        src = raw.expandtabs(4) if keep_collapsed else raw
        depth = _quote_depth(src) if keep_collapsed else 0
        if open_depth and depth < open_depth:
            fence, in_comment, open_depth = None, False, 0
        # Every closer is read at the depth its construct opened under: a quoted fence sees a deeper-quoted line as
        # literal content, and nothing open sees every depth, so an opener is found wherever it sits.
        if not keep_collapsed or (fence is not None and not open_depth):
            line = raw
        elif open_depth:
            line = _at_depth(src, open_depth)
        else:
            line = _QUOTE_MARKERS.sub("", src)
        if html_block:
            if html_depth and depth < html_depth:
                html_block, html_depth = False, 0  # the blockquote ended: this line is read
            elif not _at_depth(src, html_depth).strip():
                html_block, html_depth = False, 0
                continue
            else:
                continue
        if fence is not None:
            run = _FENCE_CLOSE.match(line)
            if run and run.group("run")[0] == fence[0] and len(run.group("run")) >= len(fence):
                fence, open_depth = None, 0
            continue
        if in_comment or in_details:
            # Inside a comment BLOCK a renderer parses no markdown, so a `-->` written in backticks still
            # closes it; inside a `<details>` element markdown resumes after the blank line, so a span there
            # is content.
            masked = line if in_comment else _outside_code_spans(line)
            if in_comment:
                m = _COMMENT_CLOSE.search(masked)
                if not m:
                    continue
                if keep_collapsed:
                    # The closing line is the HTML block's last line: what follows `-->` on it is raw text a reader can
                    # see, never a list item, so gate 6 does not read it while the read line's walk still does.
                    in_comment, open_depth = False, 0
                    continue
                line, in_comment, open_depth = line[m.end() :], False, 0
            else:
                at = masked.find("</details>")
                if at < 0:
                    continue
                line, in_details = line[at + len("</details>") :], False
        opener = _FENCE_OPEN.match(line)
        if opener:
            fence = opener.group("run") or opener.group("trun")
            open_depth = depth
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
        # end of the document when it has none; opened on a quoted line, it ends with the blockquote instead.
        stripped = line.lstrip()
        # An HTML block or comment admits at most three columns of indent (CommonMark, the bound `_FENCE_OPEN` spells
        # as `{0,3}`); four is an indented code block on the page, literal, hiding nothing and drawing no box. `line`
        # already has its tabs expanded and its markers off; only spaces are stripped here, since `lstrip()` would
        # take a non-breaking space, which is content.
        if keep_collapsed and stripped.startswith(_OPENERS):
            bare = line.lstrip(" ")
            if not bare.startswith(_OPENERS) or len(line) - len(bare) > 3:
                continue
        if stripped.startswith("<!--"):
            in_comment = True
            open_depth = depth
            continue
        if keep_collapsed and _HTML_BLOCK_TAG.match(stripped):
            html_block, html_depth = True, depth
            continue
        if stripped.startswith("<details") and not keep_collapsed:
            # Gate 6's mode is excluded: the arm above took every `<details`-prefixed spelling condition 6 opens a
            # block on, so what falls here -- `<detailsx>` alone on its line, `<details-x> text` -- is a block that
            # ends at the next blank line or a paragraph, never something a closer ends, and a box below it is one
            # gate 6 must count.
            in_details = True
            continue
        if stripped.startswith(">") and not keep_collapsed:
            continue
        visible.append(line)
    return "\n".join(visible)


def _before_anything_that_can_hide(body: str) -> str:
    """The body up to the first line that OPENS a comment, a `<details>` element or a fence, terminated or not.

    Depth for the arm that LIFTS a floor, and the only guard here whose correctness does not rest on
    out-parsing a renderer. Three review rounds found seven ways for the walk above to disagree with the page,
    and every unsafe one put the substitution line below a delimiter line -- so the line counts in the plain
    prefix and nowhere else. An earlier version cut at UNTERMINATED constructs alone and would have caught none
    of them, including neither of the two its own docstring cited, which is why the qualifier is gone.

    The cost is named rather than hidden: a terminated fence or `<details>` block between the read line and the
    substitution starts refusing, and the refusal says where the line goes. `open-pr` already puts it directly
    under the read line. The read line itself is judged by the walk alone -- refusing a real read because prose
    below it quotes a command costs more than it buys.
    """
    out: list[str] = []
    for raw in body.splitlines():
        stripped = raw.lstrip()
        # A comment that OPENS AND CLOSES on its own line hides nothing below it under any parse, and this
        # repo's own pull-request template ships one above both lines (`## Summary`'s instruction), so breaking
        # on it refused a body built from the template -- with advice the author could not act on, since the
        # obstruction sat above the line it told them to move. `<details>` and fences break unconditionally: a
        # one-line `<details>` can comment out its own closer and leave the element open, which is measured.
        if stripped.startswith("<!--") and _COMMENT_CLOSE.search(stripped):
            out.append(raw)
            continue
        if _FENCE_OPEN.match(raw) or stripped.startswith("<!--") or stripped.startswith("<details"):
            break
        out.append(raw)
    return "\n".join(out)


def _hidden_hint(body: str, pattern: re.Pattern[str]) -> str:
    """A clause for the refusal when the line IS in the body and is hidden from the rendered page. Without it the
    gate reports the line as missing, and an author looking straight at it has no way to tell what happened."""
    if pattern.search(body) and not pattern.search(_as_a_reader_sees_it(body)):
        return (
            " — the line is in the body but hidden from the rendered page: an HTML comment (terminated or not), a "
            "fenced block, a `<details>` block, or a quoted line"
        )
    return ""


def _prefix_hint(body: str, pattern: re.Pattern[str]) -> str:
    """A clause for the refusal when the line is visible but sits below a fence or a multi-line comment. Without
    it the gate says the line is missing while the author is looking straight at it."""
    visible = _as_a_reader_sees_it(body)
    if pattern.search(visible) and not pattern.search(_as_a_reader_sees_it(_before_anything_that_can_hide(body))):
        return (
            " — the line is below a fenced block, a `<details>` block or a multi-line comment; it counts in the "
            "body's plain prefix, above any of those"
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


def read_line_fails(
    pr: dict, head_commit: dict | None, files: list[str] | None, read_commit: dict | None = None, rebased: bool | str | None = None
) -> list[str]:
    """The read is at the floor and names the head, unless one of the arms below exempts the PR; `rebased` is
    `rebase_kept_every_patch`'s answer for the read's tip against the head, None when it was not asked."""
    if (pr.get("headRefName") or "").startswith("dependabot/"):
        commits = pr.get("commits")
        if commits is None:
            return ["the PR's commit list was not fetched, so the dependabot exemption cannot be scoped to a PR with no fix commit"]

        def _bot_only(commit: dict) -> bool:
            """Per commit, not over a flattened list: a commit contributing no author entries vanishes from
            the flattened one and the exemption survives a commit nothing is known about."""
            authors = [a.get("login") for a in (commit.get("authors") or [])]
            return bool(authors) and all(a == DEPENDABOT for a in authors)

        if commits and all(_bot_only(c) for c in commits):
            return []  # .claude/skills/dependabot: a PR with no fix commit needs no read, and its squash bypasses this gate
    if pr.get("headRefName") == "ops-journal":
        if files is None:
            return ["the PR's file list was not fetched, so the ops-journal exemption cannot be scoped to the journal files"]
        if all(f.startswith(JOURNAL) for f in files):
            return []  # a month of journal entries has nothing for a reviewer to read (docs/reference/ops-journal/README.md)
    body = pr.get("body") or ""
    head = pr.get("headRefOid") or ""
    # The read line is judged in the same plain prefix as the substitution. It costs nothing on a PR that uses
    # the substitution -- the read line sits above a marker that must be in the prefix anyway -- and it closes
    # the shape where a `<details>` commenting out its own closer leaves a read claimed on a page that renders it
    # collapsed. A body opening a fence or a multi-line comment ABOVE its read line is refused, and told which.
    m = READ_LINE.search(_as_a_reader_sees_it(_before_anything_that_can_hide(body)))
    if not m or m.group(1).strip().startswith("<"):
        return [
            "no 'Read before push by: <model> at <sha>' line in the body: the whole-branch read is unrecorded"
            + (_hidden_hint(body, READ_LINE) or _prefix_hint(body, READ_LINE))
        ]
    model, sha = m.group(1).strip(), m.group(2)
    family = FLOOR.match(model)
    if not family:
        return [
            f"the read named in the body was by {model!r}; the floor is Claude Opus, and Claude Fable where the PR touches {', '.join(FABLE_PATHS)}"
        ]
    # One reader. The template's placeholder names both floors; strip its markers and `Claude Opus or Claude
    # Fable` still matches the prefix, so a body that was never filled in would pass naming nobody.
    if len(FLOOR.findall(model)) > 1 or re.search(r"\bor\b", model):
        return [f"the read line names more than one reader ({model!r}): it records who read the branch, one model"]
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
        head_tree = ((head_commit.get("commit") or {}).get("tree") or {}).get("sha")
        read_tree = ((read_commit or {}).get("commit") or {}).get("tree", {}).get("sha") if read_commit else None
        if head_tree and read_tree and head_tree == read_tree:
            head_msg = (head_commit.get("commit") or {}).get("message")
            if head_msg is not None and head_msg == (read_commit.get("commit") or {}).get("message"):
                return []
            return [
                f"the head {head[:8]} has the tree the read at {sha[:8]} graded and a message it did not: the pre-review grades "
                "messages, so run `pre-review` over the amended commit and `re-review` over `<read>..<head>`, then update the line"
            ]
    if rebased is True:
        return []  # the read's tip on a base that moved under it, with no net change: no delta to read
    could_not = f"; the rebase arm could not compare: {rebased}" if isinstance(rebased, str) else ""
    return [
        f"the read named in the body covers {sha[:8]}, not the head {head[:8]}: read the delta or re-read, then update the line{could_not}"
    ]


def index_row_fails(pr: dict) -> list[str]:
    """A key in the BRANCH NAME obliges a row, and this is the last moment anything can say so.
    Reads the index from the checkout, so the gate is run from the branch that carries the row."""
    branch = pr.get("headRefName") or ""
    if not BRANCH_KEY.search(branch):
        return []
    path = pathlib.Path(__file__).resolve().parents[2] / INDEX
    try:
        text = path.read_text()
    except OSError as exc:
        return [f"{INDEX} unreadable ({exc.strerror or exc}) -- the row a keyed branch owes cannot be checked"]
    if re.search(rf"^\| #{pr['number']} ", text, re.M):
        return []
    return [
        f"branch `{branch}` carries a key and {INDEX} has no `| #{pr['number']} ` row -- the completeness "
        "test reads the branch name and turns develop red after this merge; write the row (open-pr Step 4, "
        "every cell may be an em dash) and re-run the gate from the branch"
    ]


def evaluate(
    pr: dict,
    head_commit: dict | None = None,
    files: list[str] | None = None,
    branch_growth: list[str] | None = None,
    read_commit: dict | None = None,
    rebased: bool | str | None = None,
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
    if _UNCHECKED_BOX.search(_as_a_reader_sees_it(body, keep_collapsed=True)):
        fails.append(
            "PR description has unchecked checklist item(s): a `- [ ]`, `* [ ]` or `1. [ ]` box, inside `<details>` or a quote too"
        )
    fails.extend(read_line_fails(pr, head_commit, files, read_commit, rebased))
    fails.extend(index_row_fails(pr))
    if branch_growth is None:
        fails.append(
            "the branch's ambient growth was not checked commit by commit: `guidance-guard.py --range <base>..<head>` did not run"
        )
    fails.extend(branch_growth or [])
    return fails


def _git(cwd: pathlib.Path | None, *args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, timeout=120, cwd=cwd).stdout.strip()


_DIFF_HEADER = re.compile(r"^(\+\+\+ (b/|/dev/null)|--- (a/|/dev/null))")


def _patch_lines(cwd: pathlib.Path | None, base: str, tip: str, path: str) -> list[str]:
    """What a range adds to and removes from one file, order set aside: the lines a hand resolution of that
    file carries into the head, wherever the moved base put them."""
    diff = _git(cwd, "diff", "--src-prefix=a/", "--dst-prefix=b/", base, tip, "--", path)
    return sorted(line for line in diff.splitlines() if line[:1] in "+-" and not _DIFF_HEADER.match(line))


def rebase_kept_every_patch(read: str, head: str, base_ref: str, cwd: pathlib.Path | None = None) -> bool | str:
    """True when `head` is the read's tip rebased onto a moved base, or that base merged into it, and nothing more, by the
    checks below; False when the
    base did not move or one of them fails; a string naming the cause when the arm could not compare."""
    try:
        try:
            read = _git(cwd, "rev-parse", "--verify", "--quiet", f"{read}^{{commit}}")
        except subprocess.CalledProcessError:
            _git(cwd, "fetch", "-q", "origin", read)
            read = _git(cwd, "rev-parse", "--verify", "--quiet", f"{read}^{{commit}}")
        old_base = _git(cwd, "merge-base", f"origin/{base_ref}", read)
        new_base = _git(cwd, "merge-base", f"origin/{base_ref}", head)
        if old_base == new_base:
            return False  # not a rebase: the tree arm above decides an amend, and a new commit takes a read
        messages = (
            "log",
            "--no-merges",
            "--format=%B%x00",
        )  # a merge of the base carries no patch of its own; the tree check reads it
        if _git(cwd, *messages, f"{old_base}..{read}") != _git(cwd, *messages, f"{new_base}..{head}"):
            return False  # a commit reworded, added or dropped: not the messages the pre-review graded
        merged = subprocess.run(
            ["git", "merge-tree", "--write-tree", f"--merge-base={old_base}", read, new_base],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cwd,
        )
        if merged.returncode not in (0, 1) or not merged.stdout.strip():
            return "`git merge-tree` could not merge the read onto the moved base"
        tree = merged.stdout.splitlines()[0].strip()  # exit 1 is a conflict: the tree still prints first, its markers inside
        changed = _git(cwd, "diff", "--name-only", tree, head).splitlines()
        if not all(path in RENDERED for path in changed):
            return False
        for path in changed:
            if _patch_lines(cwd, old_base, read, path) != _patch_lines(cwd, new_base, head, path):
                return False
    except subprocess.TimeoutExpired as exc:
        return f"`git {exc.cmd[1]}` timed out"
    except subprocess.CalledProcessError as exc:
        return f"`git {exc.cmd[1]}` exited {exc.returncode}: {(exc.stderr or '').strip() or 'no stderr'}"
    return True


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, timeout=60).stdout


def branch_growth(base_ref: str, head_ref: str, head: str) -> list[str]:
    """Fetch both branches, then judge every commit past the merge base through the guard's range mode; each refusal of a commit names it, and a branch that cannot be fetched, based or judged is one refusal, never a crash."""
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
        return [f"a commit fails the guidance guard's range walk — {r}" for r in refusals]
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
    growth = branch_growth(
        pr["baseRefName"], pr["headRefName"], head
    )  # fetches origin's base and head first: the rebase arm reads them
    read_commit = None
    rebased = None
    if m and head and not head.startswith(m.group(2)):
        head_commit = json.loads(_gh("api", f"repos/{REPO}/commits/{head}"))
        try:
            read_commit = json.loads(_gh("api", f"repos/{REPO}/commits/{m.group(2)}"))
        except subprocess.CalledProcessError, subprocess.TimeoutExpired:
            read_commit = None  # a tip GitHub never saw, or a fetch that failed or timed out: no tree to compare, so read_line_fails names the head the read does not cover
        rebased = rebase_kept_every_patch((read_commit or {}).get("sha") or m.group(2), head, pr["baseRefName"])
    fails = evaluate(pr, head_commit, files, growth, read_commit, rebased)
    if fails:
        print("GATE FAILED:")
        for fail in fails:
            print("  - " + fail)
        return 1
    print("GATE PASSED — ready to merge")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
