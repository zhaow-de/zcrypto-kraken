"""Internal development vocabulary must not reach a surface an operator sees at runtime (T0096).

`Phase <N>`, `T<NNNN>`, `iter-<NNN>`, `spec <NNNNN>` (+ its D-numbers) are the repo's
traceability convention. They belong in specs, plans, decision logs and source comments, where they
are load-bearing. `WP<N>` is different — memo-private, banned from every git-tracked file outright,
with exactly two recorded carriers (enforced by the last test in this file). On a surface visible **without opening the repo** they are noise at best and
confusion at worst — the triggering example was a systemd unit announcing itself to `systemctl` as
`zcrypto shadow engine (Phase 6a soak)`.

- **In scope** — the surface list lives in `.claude/rules/operator-facing-text.md` and is not
  restated here: a second copy drifts, and this one had already fallen four surfaces behind.
- **Out of scope** — source comments, docstrings, `docs/`, commit messages. Cleansing those would
  destroy traceability for zero operator benefit.
- **Log lines are deliberately out of scope.** They are the primary debugging surface and whoever
  reads one has the repo open. Verified rather than assumed: no `logger.*` literal in the scanned
  packages carries vocabulary today, so this carve-out costs nothing and is a boundary decision
  rather than a loophole.

**Why a test and not a one-off sweep.** A sweep has to be re-run by whoever remembers it exists.
This runs on every PR — which is also why a pre-commit hook is not worth its noise. The evidence is
blunt: the sweep this file accompanies found far more leaks than the estimate, and several had been
added the same evening by two other iterations while the topic sat in the queue.

**The method is the point.** A `T\\d{4}`-only pass over `raise` statements produced a false all-clear
here once. Three design choices close the gaps that made that possible:

1. **Every non-docstring string literal in the scanned packages is checked**, not just the ones
   lexically inside a `raise`/`echo`. A message built into a variable and echoed later
   (`text = render_report(...); typer.echo(text)`) is invisible to any call-site walk, and chasing
   it statically is dataflow analysis. Scanning all literals sidesteps that entirely — measured, it
   costs a handful of findings and no false positives, because docstrings are excluded and log
   messages happen to be clean.
2. **`--help` is checked against the RENDERED output of the real Typer app**, whitespace-normalised
   first: Rich wraps the help column at ~46 chars, and `spec 00052` split across a line break is
   invisible to a regex that expects the space.
3. **A path is only excused when it looks like one** — two separators or a file extension. Otherwise
   `spec 00054/T0058` (two tokens joined by a slash, not a path) silently loses its second token.
"""

from __future__ import annotations

import ast
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

VOCABULARY = re.compile(
    r"""(
        \bPhase\s+\d           # Phase 6a
      | \bT\d{4}\b             # T0096
      | \biter-\d+             # iter-117
      | \bspec\s+`?\d{5}       # spec 00052  /  spec `00052`
      | \bWP\d                 # work-package tokens
      | \bD\d{1,2}[a-z]?\b     # D3 / D12 / D5a — spec decision numbers (the rule names them; this
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


def _leaks(text: str) -> list[str]:
    """Vocabulary hits, ignoring any inside a path, after collapsing whitespace."""
    flat = re.sub(r"[\s\u2502]+", " ", text)
    spans = [m.span() for m in PATH_LIKE.finditer(flat)]
    return [m.group(0) for m in VOCABULARY.finditer(flat) if not any(s <= m.start() and m.end() <= e for s, e in spans)]


def _python_files() -> list[Path]:
    out = [p for pkg in SCANNED_PACKAGES for p in pkg.rglob("*.py") if "__pycache__" not in p.parts]
    assert out, "scanned no python files — the globs are broken, not the tree clean"
    return sorted(out)


def _shell_files() -> list[Path]:
    """Shell emits operator-facing text too: `# HELP` lines from the textfile exporters and stderr
    from the deploy scripts. Widening the scanned DIRECTORY without widening the file types is how
    the very string this rule uses as its example survived a sweep."""
    out = [p for root in (REPO / "infra",) for pattern in ("*.sh", "*.sh.j2", "*.bash") for p in root.rglob(pattern)]
    assert out, "scanned no shell files — the globs are broken, not the tree clean"
    return sorted(out)


@pytest.mark.parametrize("path", _shell_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_shell_operator_output_carries_no_internal_vocabulary(path):
    """`echo`/`printf` to stdout or stderr, including the `# HELP` text of textfile exporters.

    Line-based rather than AST-based: `#`-only comment lines are skipped, but a `printf` whose
    payload happens to contain a `#` (every HELP line) is still checked.
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
        # An ansible task `name:` is printed by every play and by every `--check --diff` preview an
        # operator reads before confirming a converge, so it is as operator-visible as
        # `Description=`. Collected: the `- name:` list-item form, inline or folded/literal. A bare
        # `name:` at deeper indent is a module argument (`ansible.builtin.systemd: name: alloy`)
        # and is not printed. Per .claude/rules/operator-facing-text.md, a new operator-visible surface joins
        # this list AND the test together.
        for p in chain((REPO / "infra/ansible").rglob("*.yml"), (REPO / "infra/ansible").rglob("*.yaml"))
        for i, line in _assembled_task_names(p.read_text(encoding="utf-8", errors="replace").splitlines())
    ]
    assert out, "found no ansible task names — the glob is broken, not the tree clean"
    return sorted(out)


def _assembled_task_names(lines: list[str]):
    """Yield `(lineno, full name value)` per task, ASSEMBLING folded/literal scalars.

    A `- name: >-` header carries its value on the CONTINUATION lines, and ansible renders the
    assembled value into the play log — so a single-line check reads only the vocabulary-free
    `>-` marker and passes a leaking name as clean. Plain single-line names pass through unchanged."""
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

    The string SHAPE is asserted, never used as a filter — a non-string value fails collection
    instead of dropping out of it.

    A task `name:` is not the only string ansible prints. A `debug: msg:` tagged `[always]` prints
    on every run including `--check`, and an `assert: fail_msg:` IS the refusal text an operator
    reads when a guard trips — the surface with the least repo access of any of them. Parsed rather
    than line-matched: these values are folded scalars far more often than names are, and the
    parser assembles them for free.
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
    # bug. Asserted rather than skipped silently — a genuinely unparseable file would otherwise drop
    # out of the scan and read as a clean tree.
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
        # *.socket/*.socket.j2 (spec 00075's NAS relay -- the repo's first socket-activated units):
        # a new operator-visible surface joins this list AND the test together, per
        # .claude/rules/operator-facing-text.md.
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


def test_grafana_alert_summaries_carry_no_internal_vocabulary():
    """An alert summary is read on a phone, in Slack, by someone with no repo open.

    The strongest case in this rule, not an exception to it — the reasoning that excuses log lines
    (the reader has the repo open) is exactly inverted here.
    """
    rules = yaml.safe_load(ALERTS.read_text())["rules"]
    found = [(r["uid"], hits) for r in rules if (hits := _leaks(" ".join((r.get("annotations") or {}).values())))]
    assert not found, "\n".join(f"alert {uid} leaks {hits} into its Slack message" for uid, hits in found)


def _dashboard_texts() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []

    def walk(node, where, name):
        if isinstance(node, dict):
            # `legendFormat` renders beside every series on the panel — as operator-visible as the
            # title above it, and it was unscanned until a token planted in one shipped unguarded.
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
    """The Slack message bodies. A new operator-visible surface joins this list AND the test
    together, per .claude/rules/operator-facing-text.md."""
    out = sorted((REPO / "infra/grafana/notification-templates").glob("*.tmpl"))
    assert out, "walked no notification templates — the glob is broken, not the templates clean"
    return out


@pytest.mark.parametrize("path", _notification_templates(), ids=lambda p: str(p.relative_to(REPO)))
def test_notification_templates_carry_no_internal_vocabulary(path):
    """The Slack notification body is the most operator-facing surface the fleet has: read on a
    phone, in a channel, with nothing else open.

    Every line is checked, `{{/* ... */}}` template comments included — unlike the `#` comments the
    shell scan skips. A Go template comment can be inline and can span lines, so recognising one
    costs more than it saves; and the template is written to carry no tokens anywhere, so a hit in a
    comment is a token to move rather than a false positive.
    """
    found = [(i, line.strip()[:110], hits) for i, line in enumerate(path.read_text().splitlines(), 1) if (hits := _leaks(line))]
    assert not found, "\n".join(f"{path.relative_to(REPO)}:{i} leaks {hits}: {txt!r}" for i, txt, hits in found)


def test_every_dashboard_json_matches_the_push_script_glob():
    """grafana-push.sh iterates infra/grafana/*-dashboard.json. A board named otherwise is
    committed, passes every check, and is NEVER pushed -- silently absent from Grafana."""
    strays = [p.name for p in sorted((REPO / "infra/grafana").glob("*.json")) if not p.name.endswith("-dashboard.json")]
    assert not strays, f"these .json files will never be pushed by grafana-push.sh: {strays}"


def test_every_notification_template_matches_the_push_script_glob():
    """The same trap as the dashboard glob above, one turn worse.

    A board named outside the push glob is merely absent from Grafana. A notification template
    renamed outside it leaves the OLD template object live on the stack, still referenced by both
    contact points and still rendering every alert the fleet sends — while the file the repo now
    edits is never pushed. Nothing anywhere reports the divergence.

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
    """Every `--help` screen the real Typer app can render.

    Measured rather than inferred: no false positives from internal docstrings, and no false
    negatives from a command registered in a way a static walk would not recognise.
    """
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
# The WP ban is repo-wide, not an operator-surface rule (operator-facing-text.md): WP labels are
# memo-private structure. The ban was violated twice in docs/ while written down as prose, which
# makes it a mechanization candidate (refine round 4), not a wording problem.

_WP = re.compile(r"\bWP\d")
_WP_CARRIERS = {
    # the one historical exception: this spec's title carries the token (work package seven)
    "docs/specs/00058-soak-check-oos-report-design.md",
    # the file that RECORDS the ban and the exception, and defines the memo's work-package format
    ".claude/skills/zcrypto-grooming/references/memo-protocol.md",
}


def test_wp_tokens_stay_out_of_git_tracked_files():
    """Banned everywhere, two recorded carriers — and the allowlist is asserted BOTH ways: a
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
