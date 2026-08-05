"""Internal development vocabulary must not reach a surface an operator sees at runtime (T0096).

`Phase <N>`, `T<NNNN>`, `iter-<NNN>`, `spec <NNNNN>` (+ its D-numbers) and `WP<N>` are the repo's
traceability convention. They belong in specs, plans, decision logs and source comments, where they
are load-bearing. On a surface visible **without opening the repo** they are noise at best and
confusion at worst — the triggering example was a systemd unit announcing itself to `systemctl` as
`zcrypto shadow engine (Phase 6a soak)`.

- **In scope** — systemd `Description=`, CLI `--help`, CLI runtime output, Prometheus metric HELP
  text, Grafana alert summaries and panel titles/descriptions, compose interpolation errors, README.
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
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
ALERTS = REPO / "infra/grafana/alerts.yaml"

# Packages whose string literals reach an operator. `infra/scripts/` holds the instruments
# `capture-deploys.md` tells an operator to run, so its output is as user-facing as the CLI's.
SCANNED_PACKAGES = [REPO / "cli", REPO / "infra/scripts"]

VOCABULARY = re.compile(
    r"""(
        \bPhase\s+\d           # Phase 6a
      | \bT\d{4}\b             # T0096
      | \biter-\d+             # iter-117
      | \bspec\s+`?\d{5}       # spec 00052  /  spec `00052`
      | \bWP\d                 # WP4
      | \bD\d{1,2}\b           # D3 / D12 — spec decision numbers (the rule names them; this enforces it)
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
            for key in ("title", "description", "content"):
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
    """Panel titles, descriptions and text panels are the operator's actual UI."""
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
