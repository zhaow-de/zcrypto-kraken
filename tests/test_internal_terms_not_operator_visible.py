"""Internal development vocabulary must not reach a surface an operator sees at runtime (T0096).

The surface list is this file's own parametrisations and walkers, restated nowhere else: a
second copy drifts. A new surface an operator reads at runtime -- a unit description, an alert
summary, a notification template, a `fail_msg` -- joins this file's parametrisations or walkers in
the change that creates it. `WP<N>` is different -- memo-private, banned from every git-tracked file
outright, enforced by the last test in this file; widening its allowlist, `_WP_CARRIERS`, is a
different act from adding a surface and is refused.

Every non-docstring string literal in the scanned packages is checked, not just the ones lexically
inside a `raise`/`echo`: a message built into a variable and echoed later
(`text = render_report(...); typer.echo(text)`) is invisible to any call-site walk, and chasing it
statically is dataflow analysis. That makes this scan STRICTER than a log-line carve-out would
be, `logger.*` literals included, and it stays so: narrowing it to spare a log line reopens the
loophole such a carve-out would otherwise be.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
from fnmatch import fnmatch
from itertools import chain
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
ALERTS = REPO / "infra/grafana/alerts.yaml"

# Packages whose string literals reach an operator. `infra/scripts/` holds the instruments
# `.claude/skills/zcrypto-rollout-image/SKILL.md` tells an operator to run, so its output is as
# user-facing as the CLI's.
SCANNED_PACKAGES = [REPO / "cli", REPO / "infra/scripts"]

# Five of the six classes read case-insensitively: prose capitalises a sentence's first word, so
# `Spec 00039` opening a sentence is the same unresolvable reference as `spec 00039` inside one, and a
# case-sensitive class is a door open to the shape prose produces most often. `D<N>` is the exception
# and stays case-sensitive: `d4` is a key in the soak report's payload, a record field its readers
# index on, and folding case there would report a schema name as operator vocabulary.
VOCABULARY = re.compile(
    r"""(
        (?i:\bPhase\s+\d)      # Phase 6a — folded, so ordinary "phase 2 of the rollout" is a hit too: reword it, do not allowlist
      | (?i:\bT\d{4}\b)        # T0096
      | (?i:\biter-\d+)        # iter-117
      | (?i:\bspec\s+`?\d{5})  # spec 00052  /  spec `00052`  /  Spec 00052
      | (?i:\bWP\d)            # work-package tokens
      | \bD\d{1,2}[a-z]?\b     # D3 / D12 / D5a — spec decision numbers (CLAUDE.md's guards bullet names them; this
                               # enforces it). The optional letter is NOT cosmetic: `\bD\d{1,2}\b`
                               # cannot match `D5a`, because there is no word boundary between `5`
                               # and `a` — so every lettered decision escaped the guard entirely,
                               # and D5a/D6a/D1c are the most-cited decisions in the specs.
    )""",
    re.VERBOSE,
)

# A token inside a real file PATH is an operand, not a reference: you need the exact name to open
# the file, so `docs/open-topics/T0023-*.md` stays. A path must start at a known repo root OR carry
# a file extension — not merely contain slashes, or `spec 00054/T0058` (two tokens joined by a
# slash) and `half-hourly/hourly/T0060-daily` would be excused as paths.
PATH_LIKE = re.compile(
    r"(?:docs|cli|infra|tests|data|scripts|\.claude)/[\w./*-]+"
    r"|[\w*-]+(?:/[\w.*-]+)*\.[A-Za-z0-9]{1,8}\b"
)


def _flat(text: str) -> str:
    """Whitespace and the box-drawing bar collapsed to single spaces, so a token a wrap or a table
    border splits reads as the one token it is. Every reader of a hit's position shares this, or a
    preview cut from the unflattened text would not hold the hit found in the flattened one."""
    return re.sub(r"[\s\u2502]+", " ", text)


def _leak_spans(text: str) -> list[tuple[int, str]]:
    """Each hit as its offset into `_flat(text)` and its text, ignoring any inside a path.

    The offset is the only way back to WHICH occurrence was the hit: the same token may appear twice
    in one unit, once inside an exempt path and once bare, and searching the flattened text for the
    hit's characters lands on the exempt one.
    """
    flat = _flat(text)
    spans = [m.span() for m in PATH_LIKE.finditer(flat)]
    return [
        (m.start(), m.group(0)) for m in VOCABULARY.finditer(flat) if not any(s <= m.start() and m.end() <= e for s, e in spans)
    ]


def _leaks(text: str) -> list[str]:
    """Vocabulary hits, ignoring any inside a path, after collapsing whitespace."""
    return [hit for _, hit in _leak_spans(text)]


def test_a_sentence_initial_token_is_the_same_token():
    """The capitalised spelling is what a paragraph produces, and it is what escaped the guard: a
    runbook step read `Spec 00039 decision 3 …` while every surface walked here reported clean.

    `D<N>` is deliberately absent from the folded classes, and the third case is why: lowercased it is
    a key in the soak report's payload, not a reference an operator is handed.
    """
    assert _leaks("Spec 00039 decision 3 makes the workstation IP an exception.") == ["Spec 00039"]
    assert _leaks("Iter-117 registered it as T0123 during Phase 6a.") == ["Iter-117", "T0123", "Phase 6"]
    assert _leaks('payload["d4"] = {"d4_gap_bps": gap}') == []


def _python_files() -> list[Path]:
    out = [p for pkg in SCANNED_PACKAGES for p in pkg.rglob("*.py") if "__pycache__" not in p.parts]
    assert out, "scanned no python files — the globs are broken, not the tree clean"
    return sorted(out)


def _shell_files() -> list[Path]:
    """Shell emits operator-facing text too: `# HELP` lines from the textfile exporters and stderr
    from the deploy scripts."""
    out = [p for root in (REPO / "infra",) for pattern in ("*.sh", "*.sh.j2", "*.bash") for p in root.rglob(pattern)]
    assert out, "scanned no shell files — the globs are broken, not the tree clean"
    return sorted(out)


@pytest.mark.parametrize("path", _shell_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_shell_operator_output_carries_no_internal_vocabulary(path):
    """`echo`/`printf` to stdout or stderr, including the `# HELP` text of textfile exporters.

    Only a line that STARTS with `#` is skipped, so a `printf` whose payload carries a `#` -- every
    HELP line -- is still checked.
    """
    found = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if re.match(r"\s*#", line):  # a shell comment is source documentation, out of scope
            continue
        if hits := _leaks(line):
            found.append((i, line.strip()[:100], hits))
    assert not found, "\n".join(f"{path.relative_to(REPO)}:{ln} leaks {hits}: {txt!r}" for ln, txt, hits in found)


def _non_docstring_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """Every string literal except docstrings, which are source documentation and out of scope."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    return [
        (n.lineno, n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    ]


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_python_string_literals_carry_no_internal_vocabulary(path):
    """Raised messages, printed output, `help=`, metric HELP text — every literal but docstrings."""
    found = [
        (lineno, text.strip().replace("\n", " ")[:100], hits)
        for lineno, text in _non_docstring_literals(ast.parse(path.read_text()))
        if (hits := _leaks(text))
    ]
    assert not found, "\n".join(
        f"{path.relative_to(REPO)}:{ln} leaks {hits} — move the token to an adjacent comment: {txt!r}" for ln, txt, hits in found
    )


def _ansible_task_names() -> list[tuple[str, int, str]]:
    out = [
        (str(p.relative_to(REPO)), i, line)
        # Collected: the `- name:` list-item form, inline or folded/literal. A bare `name:` at
        # deeper indent is a module argument (`ansible.builtin.systemd: name: alloy`), not printed.
        for p in chain((REPO / "infra/ansible").rglob("*.yml"), (REPO / "infra/ansible").rglob("*.yaml"))
        for i, line in _assembled_task_names(p.read_text(encoding="utf-8", errors="replace").splitlines())
    ]
    assert out, "found no ansible task names — the glob is broken, not the tree clean"
    return sorted(out)


def _assembled_task_names(lines: list[str]):
    """Yield `(lineno, full name value)` per task, ASSEMBLING folded/literal scalars.

    A `- name: >-` header carries its value on the CONTINUATION lines, and ansible renders the
    assembled value into the play log — so a single-line check reads only the vocabulary-free
    `>-` marker and passes a leaking name as clean."""
    header = re.compile(r"^(\s*)-\s+name:\s*(.*\S)\s*$")
    for i, line in enumerate(lines, 1):
        m = header.match(line)
        if not m:
            continue
        value = m.group(2)
        if re.fullmatch(r"[>|][+-]?", value):
            # The block ends at the first nonblank line indented LESS than the block's own content
            # — measured from the first continuation line, not from the `-`: the task's module keys
            # sit between those two depths, and bounding on the `-` swallowed them into the value.
            block, content_indent = [], None
            for cont in lines[i:]:
                if cont.strip() == "":
                    continue
                cur = len(cont) - len(cont.lstrip())
                if content_indent is None:
                    content_indent = cur
                if cur < content_indent:
                    break
                block.append(cont.strip())
            value = " ".join(block)
        yield i, value


@pytest.mark.parametrize("unit,lineno,line", _ansible_task_names(), ids=lambda v: v if isinstance(v, str) else "")
def test_ansible_task_names_carry_no_internal_vocabulary(unit, lineno, line):
    """A task `name:` is the line an operator reads in the play log and in every converge preview."""
    hits = _leaks(line)
    assert not hits, (
        f"{unit}:{lineno} leaks {hits} into the play log — keep the semantic content, move the "
        f"token to the comment above the task: {line.strip()!r}"
    )


def _ansible_operator_messages() -> list[tuple[str, str, str]]:
    """Yield `(file, key, value)` per `msg`/`fail_msg`/`success_msg` in `infra/ansible/**/*.{yml,yaml}`.

    Parsed rather than line-matched, unlike the task names above: these values are folded scalars far
    more often, and the parser assembles them for free.
    """
    out, unparsed = [], []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("msg", "fail_msg", "success_msg"):
                    # A list-valued msg is legal and ansible prints it, but the walk would descend
                    # past it and see only list ITEMS, never a value under a printing key. Assert
                    # the shape so a new one fails loudly instead of dropping out of the scan.
                    assert isinstance(value, str), (
                        f"{path}: non-string {key}= ({type(value).__name__}) is unscanned — flatten "
                        f"non-string values into the walk; never reshape the task to satisfy this"
                    )
                    out.append((path, key, " ".join(value.split())))
                walk(value, path)
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    for p in sorted(chain((REPO / "infra/ansible").rglob("*.yml"), (REPO / "infra/ansible").rglob("*.yaml"))):
        rel = str(p.relative_to(REPO))
        try:
            documents = list(yaml.safe_load_all(p.read_text(encoding="utf-8", errors="replace")))
        except yaml.YAMLError:
            unparsed.append(rel)
            continue
        for document in documents:
            walk(document, rel)
    # The only files a plain parser cannot read are the vaulted ones (`!vault` is an ansible-only
    # tag), and those hold variables, never tasks. Keyed on the MARKER, not the filename: any name is
    # a legal vault file, so `endswith("vault.yml")` would report a newly-vaulted `creds.yml` as a
    # bug.
    assert all("!vault" in (REPO / p).read_text(encoding="utf-8", errors="replace") for p in unparsed), (
        f"unparseable YAML with no !vault marker: {unparsed}"
    )
    assert out, "found no ansible operator messages — the walk is broken, not the tree clean"
    return sorted(out)


@pytest.mark.parametrize("path,key,text", _ansible_operator_messages(), ids=lambda v: v if isinstance(v, str) else "")
def test_ansible_operator_messages_carry_no_internal_vocabulary(path, key, text):
    """`debug: msg:` prints on every run; `assert: fail_msg:` is what a tripped guard tells the operator."""
    hits = _leaks(text)
    assert not hits, (
        f"{path} {key}= leaks {hits} into the operator's console — keep the semantic content, move "
        f"the token to the comment above the task: {text[:120]!r}"
    )


def _systemd_descriptions() -> list[tuple[str, int, str]]:
    out = [
        (str(p.relative_to(REPO)), i, line)
        for pattern in ("*.service", "*.timer", "*.socket", "*.service.j2", "*.timer.j2", "*.socket.j2")
        for p in (REPO / "infra").rglob(pattern)
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if line.startswith("Description=")
    ]
    assert out, "found no systemd Description= lines — the glob is broken, not the tree clean"
    return sorted(out)


@pytest.mark.parametrize("unit,lineno,line", _systemd_descriptions(), ids=lambda v: v if isinstance(v, str) else "")
def test_systemd_descriptions_carry_no_internal_vocabulary(unit, lineno, line):
    """`Description=` is what `systemctl status` and `list-timers` print."""
    hits = _leaks(line)
    assert not hits, (
        f"{unit}:{lineno} leaks {hits} into `systemctl status` — keep the semantic content, move the "
        f"token to the comment above: {line!r}"
    )


def test_readme_carries_no_internal_vocabulary():
    """The project's front door, whose Usage section mirrors the CLI's own help text."""
    found = [(i, line.strip()[:110], hits) for i, line in enumerate(README.read_text().splitlines(), 1) if (hits := _leaks(line))]
    assert not found, "\n".join(f"README.md:{i} leaks {hits}: {txt!r}" for i, txt, hits in found)


def _guidance_guard():
    """`infra/scripts/guidance-guard.py`, loaded by path: a hyphen makes the name unimportable.

    Two halves of the page rule are borrowed from the commit-msg guard rather than restated here --
    what a list item is, and where an HTML comment is -- so that the guard's bullet reader and this
    page reader cannot drift into two verdicts on one line. The token classes do not move the other
    way: `VOCABULARY`'s own examples are a string literal, and under `infra/scripts/` this file would
    read them as an operator-facing leak and refuse its own definition.
    """
    spec = importlib.util.spec_from_file_location("guidance_guard", REPO / "infra/scripts/guidance-guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GUARD = _guidance_guard()
_without_html_comments = _GUARD.without_html_comments


def _without_fenced_blocks(text: str) -> str:
    """Every fenced block, its markers included, blanked to its own newlines.

    A fence is the command an operator pastes, so a serial inside one is the operand and not
    vocabulary aimed at them -- the carve-out `tests/test_runbook_internal_tokens.py` already pins for
    the bullet instrument, restated here so the two readers of one rule do not disagree about the same
    line. An INDENTED code block is not known here, as it is not known to `bullets()` either: a token
    in one is read, and the page's answer is to fence it.
    """
    out, fenced = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            out.append("")
        else:
            out.append("" if fenced else line)
    return "\n".join(out)


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """Each unit as its first line number and its lines joined, a blank line ending one.

    The unit is not the line: `spec`/`Phase` and their numbers are two words, and a wrap falling
    between them is invisible to a line reader while `bullets()`, which joins a wrapped item, sees it.
    Nor is it the whole run of text -- a list item, a heading and a table row each open their own unit,
    because the number reported is the unit's FIRST line and an operator opens the page there: a whole
    list joined into one would report a hit in its last item at the first item's line. The item is
    `bullets()`' item, read with the guard's own marker, and its continuation lines join it.
    """
    out: list[tuple[int, str]] = []
    joining = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            joining = False
        elif joining and not stripped.startswith(("#", "|")) and not _GUARD.BULLET.match(line):
            out[-1] = (out[-1][0], f"{out[-1][1]} {stripped}")
        else:
            out.append((i, stripped))
            joining = not stripped.startswith(("#", "|"))
    return out


_PREVIEW = 110


def _preview(para: str, at: int, hit: str) -> str:
    """At most `_PREVIEW` characters of the unit, flattened as `_leaks` reads it and centred on `at`
    -- the offset `_leak_spans` matched, not the first place the hit's characters appear, or a unit
    that cites an exempt path before its real leak shows a window round the path the rule permits.
    These pages do not hard-wrap, and a unit is routinely longer than the window."""
    flat = _flat(para)
    if len(flat) <= _PREVIEW:
        return flat
    start = min(max(at - (_PREVIEW - len(hit)) // 2, 0), len(flat) - _PREVIEW)
    return ("…" if start else "") + flat[start : start + _PREVIEW] + ("…" if start + _PREVIEW < len(flat) else "")


def _page_leaks(text: str) -> list[tuple[int, str, list[str]]]:
    """A page's leaking units as (first lineno, preview, hits) -- comments blanked before fences, for
    the reason `without_html_comments` gives."""
    return [
        (i, _preview(para, *spans[0]), [hit for _, hit in spans])
        for i, para in _paragraphs(_without_fenced_blocks(_without_html_comments(text)))
        if (spans := _leak_spans(para))
    ]


def test_a_fenced_block_is_the_command_to_paste_and_the_step_under_it_is_still_prose():
    """Both directions of the carve-out in one page: the serial an operator pastes passes, and the
    prose under the block is still read, so the exemption cannot be widened into a hiding place."""
    text = "# P\n\n```\nzcrypto engine replay --spec 00106\n```\n\nThen record T0123.\n"
    assert _page_leaks(text) == [(7, "Then record T0123.", ["T0123"])]


def test_a_fence_marker_inside_a_comment_does_not_blank_the_page_under_it():
    """A stale command block commented out with its markers tucked into the comment's own lines leaves
    an odd marker for a fence blanker that cannot see comments: read fences first and the block opens,
    the step below it is blanked unread, and the command inside the comment is reported in its place."""
    text = "# P\n\n<!-- ```\nzcrypto engine replay --spec 00106\n``` -->\n\nThen record T0123.\n"
    assert _page_leaks(text) == [(7, "Then record T0123.", ["T0123"])]


def test_a_token_a_line_wrap_splits_is_still_the_token():
    """`spec` ending a line and its serial opening the next is what a 100-column wrap produces, and the
    bullet instrument already reports it. Two paragraphs are not one wrapped paragraph."""
    assert _page_leaks("# P\n\nThe exception is granted by spec\n00039 decision 3.\n") == [
        (3, "The exception is granted by spec 00039 decision 3.", ["spec 00039"])
    ]
    assert _page_leaks("# P\n\nGranted by spec\n\n00039 is the serial.\n") == []


def test_a_heading_and_a_table_row_each_name_their_own_line():
    """A paragraph reader that swallowed them would report a table's every hit at its first row."""
    assert _page_leaks("# Restart\nThe step records T0123.\n") == [(2, "The step records T0123.", ["T0123"])]
    table = "| step | note |\n| --- | --- |\n| restart | ordinary |\n| verify | see T0123 |\n"
    assert _page_leaks(table) == [(4, "| verify | see T0123 |", ["T0123"])]


def test_a_list_item_is_its_own_unit_and_a_wrap_inside_one_is_not():
    """A list read as one unit reported a hit in its last item at the FIRST item's line, which is the
    cost the table case above refuses; a prose line running into the list without a blank line between
    made that first line the prose's. Both halves in one text. The wrap a page can still put inside an
    item stays one unit, so the two words of `spec 00039` are not split by the narrower unit."""
    listed = "# P\n\nThe steps are:\n- Restart the daemon.\n  - A nested note.\n- The last step records T0123.\n"
    assert _page_leaks(listed) == [(6, "- The last step records T0123.", ["T0123"])]
    assert _page_leaks("# P\n\n- Granted by spec\n  00039 decision 3.\n") == [
        (3, "- Granted by spec 00039 decision 3.", ["spec 00039"])
    ]


def test_the_preview_is_cut_around_the_token_not_around_the_unit_s_opening():
    """These pages do not hard-wrap -- a step is one line of some hundreds of characters -- so a window
    taken from the unit's start shows an operator 110 characters that need not contain the token the
    failure names, and they then read the wrong end of the right line."""
    filler = "the step runs on, as these pages write it, " * 4
    ((line, preview, hits),) = _page_leaks(f"# P\n\n- A first step.\n- {filler}and it records T0123 at the end.\n")
    assert (line, hits) == (4, ["T0123"])
    assert "T0123" in preview and preview.startswith("…") and len(preview) <= _PREVIEW + 2


def test_the_preview_centres_on_the_reported_hit_not_on_an_exempt_path_before_it():
    """A step that opens a topic file and leaks the same token in prose further along: the hit is the
    prose one, so a window cut where the token's characters first appear lands on the path instead and
    tells the operator to rename a reference the rule exempts, while the leak it named stays."""
    filler = "the step runs on, as these pages write it, " * 5
    step = f"- Open `docs/open-topics/T0123-live-venue.md` first. {filler}and then it records T0123."
    ((line, preview, hits),) = _page_leaks(f"# P\n\n{step}\n")
    assert (line, hits) == (3, ["T0123"])
    assert preview.endswith("and then it records T0123."), preview
    assert "docs/open-topics" not in preview, preview


def _runbook_pages() -> list[Path]:
    """Every page under `infra/runbooks/`, a subdirectory's included: an operator opens any of them."""
    out = sorted((REPO / "infra/runbooks").rglob("*.md"))
    assert out, "walked no runbook pages — the glob is broken, not the pages clean"
    return out


@pytest.mark.parametrize("path", _runbook_pages(), ids=lambda p: str(p.relative_to(REPO)))
def test_runbook_pages_carry_no_internal_vocabulary(path):
    """A runbook page is where an alert's `Runbook:` link lands and what a procedure is read from, so
    the whole page is the surface -- its paragraphs and table rows as much as the bullets
    `infra/scripts/runbook-internal-tokens.py` counts. An HTML comment is where a token may sit
    hidden, being where the provenance a maintainer needs lives; a fenced block is where one may sit
    in plain view, being the command the operator pastes.
    """
    on_the_page = _page_leaks(path.read_text())
    assert not on_the_page, "\n".join(
        f"{path.relative_to(REPO)}:{i} leaks {hits} — say it in words, or keep the token in an HTML comment beside it. "
        f"Around the token: {txt!r}"
        for i, txt, hits in on_the_page
    )


def test_grafana_alert_summaries_carry_no_internal_vocabulary():
    """An alert summary is read on a phone, in Slack, by someone with no repo open."""
    rules = yaml.safe_load(ALERTS.read_text())["rules"]
    found = [(r["uid"], hits) for r in rules if (hits := _leaks(" ".join((r.get("annotations") or {}).values())))]
    assert not found, "\n".join(f"alert {uid} leaks {hits} into its Slack message" for uid, hits in found)


def _dashboard_texts() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []

    def walk(node, where, name):
        if isinstance(node, dict):
            # `legendFormat` renders beside every series on the panel, as operator-visible as the
            # title above it.
            for key in ("title", "description", "content", "legendFormat"):
                if isinstance(node.get(key), str):
                    out.append((name, f"{where}.{key}", node[key]))
            for k, v in node.items():
                walk(v, f"{where}.{k}", name)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]", name)

    for path in sorted((REPO / "infra/grafana").glob("*.json")):
        walk(json.loads(path.read_text()), path.stem, path.name)
    assert out, "walked no dashboard text — the glob is broken, not the dashboards clean"
    return out


def test_grafana_dashboard_text_carries_no_internal_vocabulary():
    """Panel titles, descriptions, series legends and text panels are the operator's actual UI."""
    found = [(f, where, hits) for f, where, text in _dashboard_texts() if (hits := _leaks(text))]
    assert not found, "\n".join(f"{f} {where} leaks {hits}" for f, where, hits in found)


def _notification_templates() -> list[Path]:
    """The Slack message bodies."""
    out = sorted((REPO / "infra/grafana/notification-templates").glob("*.tmpl"))
    assert out, "walked no notification templates — the glob is broken, not the templates clean"
    return out


@pytest.mark.parametrize("path", _notification_templates(), ids=lambda p: str(p.relative_to(REPO)))
def test_notification_templates_carry_no_internal_vocabulary(path):
    """The Slack notification body is the most operator-facing surface the fleet has: read on a
    phone, in a channel, with nothing else open.

    Every line is checked, `{{/* ... */}}` template comments included: a Go template comment can be
    inline and can span lines, so recognising one costs more than it saves.
    """
    found = [(i, line.strip()[:110], hits) for i, line in enumerate(path.read_text().splitlines(), 1) if (hits := _leaks(line))]
    assert not found, "\n".join(f"{path.relative_to(REPO)}:{i} leaks {hits}: {txt!r}" for i, txt, hits in found)


def test_every_dashboard_json_matches_the_push_script_glob():
    """grafana-push.sh iterates infra/grafana/*-dashboard.json. A board named otherwise is
    committed, passes every check, and is NEVER pushed -- silently absent from Grafana."""
    strays = [p.name for p in sorted((REPO / "infra/grafana").glob("*.json")) if not p.name.endswith("-dashboard.json")]
    assert not strays, f"these .json files will never be pushed by grafana-push.sh: {strays}"


def test_every_notification_template_matches_the_push_script_glob():
    """The same trap as the dashboard glob above, one turn worse: a notification template renamed
    outside the push glob leaves the OLD template object live on the stack, still rendering every
    alert the fleet sends, while the file the repo now edits is never pushed.

    The pattern is READ OUT of the script rather than restated here: a guard that hardcodes its own
    copy of the thing it audits drifts silently the moment the script's glob changes.
    """
    m = re.search(
        r"for tmpl in \"\$\{root\}\"/infra/grafana/notification-templates/(\S+); do",
        (REPO / "infra/scripts/grafana-push.sh").read_text(),
    )
    assert m, "found no notification-template loop in grafana-push.sh — the guard is broken, not the tree clean"
    pattern = m.group(1)
    files = sorted(p for p in (REPO / "infra/grafana/notification-templates").iterdir() if p.is_file())
    assert files, "walked no notification templates — the glob is broken, not the tree clean"
    strays = [p.name for p in files if not fnmatch(p.name, pattern)]
    assert not strays, (
        f"these files will never be pushed by grafana-push.sh (it iterates {pattern!r}), while the object "
        f"they used to push stays live in Grafana rendering every notification: {strays}"
    )


def test_compose_interpolation_errors_carry_no_internal_vocabulary():
    """`${VAR:?message}` is what Docker Compose prints when the variable is unset — operator-facing,
    unlike the `#` comments around it."""
    found = []
    for path in sorted((REPO / "infra").rglob("*compose*.y*ml*")):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            for m in re.finditer(r"\$\{[^}]*:\?([^}]*)\}", line):
                if hits := _leaks(m.group(1)):
                    found.append((str(path.relative_to(REPO)), i, hits))
    assert not found, "\n".join(f"{p}:{i} leaks {hits} into a compose error" for p, i, hits in found)


def _rendered_help() -> list[tuple[str, str]]:
    """Every `--help` screen the real Typer app can render."""
    from typer.testing import CliRunner

    from cli.__main__ import app

    runner = CliRunner()
    seen: list[tuple[str, str]] = []
    queue: list[list[str]] = [[]]
    while queue:
        path = queue.pop()
        result = runner.invoke(app, [*path, "--help"])
        if result.exit_code != 0:
            continue
        text = result.stdout
        seen.append((" ".join(["zcrypto", *path]), text))
        if "Commands" in text and len(path) < 3:
            block = text.split("Commands", 1)[1]
            for line in block.splitlines():
                if m := re.match(r"^[\s│|]*([a-z][a-z0-9-]*)\s{2,}", line):
                    queue.append([*path, m.group(1)])
    return seen


def test_rendered_cli_help_carries_no_internal_vocabulary():
    """The `--help` text a user actually sees, whitespace-normalised so a Rich line break cannot
    hide a token that contains a space."""
    screens = _rendered_help()
    assert screens, "walked no help screens — the walker is broken, not the CLI clean"
    found = [(cmd, hits) for cmd, text in screens if (hits := _leaks(text))]
    assert not found, "\n".join(f"`{cmd} --help` leaks {hits}" for cmd, hits in found)


# ---------------------------------------------------------------------------------------------
# The WP ban is repo-wide, not an operator-surface rule: WP labels are
# memo-private structure.

_WP = re.compile(r"\bWP\d")
_WP_CARRIERS = {
    # the one historical exception: this spec's title carries the token (work package seven); the
    # memo protocol defines the work-package format as `WP<N>`, which carries no digit
    "docs/specs/00058-soak-check-oos-report-design.md",
}


def test_wp_tokens_stay_out_of_git_tracked_files():
    """Banned everywhere but the recorded carriers -- and the allowlist is asserted BOTH ways: a
    carrier that stops matching is a stale allowlist entry, never a silent pass."""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.splitlines()
    assert len(tracked) > 100, "git ls-files returned suspiciously few files — the walk is broken"
    hits = set()
    for rel in tracked:
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError:
            continue  # binary, or deleted in the worktree
        if _WP.search(text):
            hits.add(rel)
    strays = sorted(hits - _WP_CARRIERS)
    assert not strays, f"WP tokens outside the recorded carriers: {strays}"
    stale = sorted(_WP_CARRIERS - hits)
    assert not stale, f"stale allowlist — recorded carriers no longer carry a WP token: {stale}"
