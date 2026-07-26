"""Internal development vocabulary must not reach a surface an operator sees at runtime (T0096).

`Phase <N>`, `T<NNNN>`, `iter-<NNN>`, `spec <NNNNN>` (+ its D-numbers) and `WP<N>` are the repo's
traceability convention. They belong in specs, plans, decision logs and source comments, where they
are load-bearing. On a surface visible **without opening the repo** they are noise at best and
confusion at worst — the triggering example was a systemd unit announcing itself to `systemctl` as
`zcrypto shadow engine (Phase 6a soak)`.

The boundary, and why this is a test rather than a one-off sweep:

- **In scope** — systemd `Description=`, CLI `--help` text (both `help=` and the command docstrings
  Typer renders), CLI runtime messages (raised exceptions, `typer.echo`, `print`), and README.
- **Out of scope** — source comments, `docs/`, commit messages. Cleansing those would destroy
  traceability for zero operator benefit.
- **Log lines are deliberately out of scope.** They are operator-visible, but they are also the
  primary debugging surface, and a `T<NNNN>` pointer in a log line genuinely helps whoever is
  reading it — that reader has the repo open by definition. Decided here rather than left implicit,
  because the topic flagged it as an open boundary question.

A one-off sweep would have to be re-run by someone who remembers it exists. This file makes the
rule enforce itself, which is also the answer to whether a pre-commit hook is worth the noise: it
is not, because the suite already runs on every PR.

The method matters as much as the rule. A `T\\d{4}`-only pass over `raise` statements already
produced one false all-clear, so the walk covers the **whole vocabulary** and every operator-facing
call, not just raises.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "cli"
README = REPO / "README.md"

# The full vocabulary. `spec <NNNNN>` optionally carries a D-number, matched together so a bare `D5`
# (which appears legitimately in prose) is not a false positive.
VOCABULARY = re.compile(
    r"""(
        \bPhase\s\d            # Phase 6a
      | \bT\d{4}\b             # T0096
      | \biter-\d+             # iter-117
      | \bspec\s`?\d{5}        # spec 00052  /  spec `00052`
      | \bWP\d                 # WP4
    )""",
    re.VERBOSE,
)

# A file PATH containing a token is not a leak: you need the exact name to open the file, so the
# token is an operand rather than a reference. `docs/open-topics/T0023-liquidations.md` stays.
PATH_LIKE = re.compile(r"[\w./-]*/[\w./-]*")


def _leaks(text: str) -> list[str]:
    """Vocabulary hits in `text`, ignoring any that sit inside a path."""
    spans = [m.span() for m in PATH_LIKE.finditer(text)]
    return [m.group(0) for m in VOCABULARY.finditer(text) if not any(s <= m.start() and m.end() <= e for s, e in spans)]


def _python_files() -> list[Path]:
    return sorted(p for p in CLI.rglob("*.py") if "__pycache__" not in p.parts)


def _runtime_message_strings(tree: ast.AST) -> list[tuple[int, str]]:
    """String literals in this module that reach an operator at RUNTIME.

    Deliberately broader than `raise`: `typer.echo`/`print` reach the operator without raising, and
    a raise-only walk cannot see them — that method gap is how a `T\\d{4}`-only pass over raises
    produced a false all-clear once already.

    Deliberately NOT every docstring: an internal helper's docstring is a source comment, which the
    boundary puts out of scope. The docstrings that DO reach an operator are the ones Typer renders
    into `--help`, and those are measured against the real rendered output below rather than guessed
    at from the AST.
    """
    out: list[tuple[int, str]] = []

    def literals(node: ast.AST) -> list[tuple[int, str]]:
        return [(n.lineno, n.value) for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]

    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            out += literals(node.exc)
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in ("echo", "secho", "print"):
                out += literals(node)
            for kw in node.keywords:
                if kw.arg in ("help", "short_help"):
                    out += literals(kw.value)

    return out


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_cli_runtime_messages_carry_no_internal_vocabulary(path):
    """Raised exception messages, printed output, and `help=` strings in `cli/`."""
    tree = ast.parse(path.read_text())
    found = [
        (lineno, text.strip().replace("\n", " ")[:100], hits)
        for lineno, text in _runtime_message_strings(tree)
        if (hits := _leaks(text))
    ]
    assert not found, "\n".join(
        f"{path.relative_to(REPO)}:{ln} leaks {hits} — move the token to an adjacent comment: {txt!r}" for ln, txt, hits in found
    )


def _systemd_descriptions() -> list[tuple[str, int, str]]:
    out = []
    for pattern in ("*.service", "*.timer", "*.service.j2", "*.timer.j2"):
        for p in (REPO / "infra").rglob(pattern):
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if line.startswith("Description="):
                    out.append((str(p.relative_to(REPO)), i, line))
    return sorted(out)


@pytest.mark.parametrize("unit,lineno,line", _systemd_descriptions(), ids=lambda v: v if isinstance(v, str) else "")
def test_systemd_descriptions_carry_no_internal_vocabulary(unit, lineno, line):
    """`Description=` is what `systemctl status` and `list-timers` print — the most-seen surface."""
    hits = _leaks(line)
    assert not hits, (
        f"{unit}:{lineno} leaks {hits} into `systemctl status` output — keep the semantic content, "
        f"move the token to the comment above: {line!r}"
    )


def test_readme_carries_no_internal_vocabulary():
    """The project's front door, and its Usage section mirrors the CLI's own help text."""
    found = [(i, line.strip()[:110], hits) for i, line in enumerate(README.read_text().splitlines(), 1) if (hits := _leaks(line))]
    assert not found, "\n".join(f"README.md:{i} leaks {hits}: {txt!r}" for i, txt, hits in found)


def _rendered_help() -> list[tuple[str, str]]:
    """Every `--help` screen the CLI can actually render, walked from the real app.

    Measured, not inferred: this is the surface a user sees, so scanning the rendered text has no
    false positives from internal docstrings and no false negatives from a command registered in a
    way an AST walk would not recognise.
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
        seen.append((" ".join(["zcrypto", *path]) or "zcrypto", text))
        # Recurse into subcommands listed in this screen's Commands block.
        if "Commands" in text:
            block = text.split("Commands", 1)[1]
            for line in block.splitlines():
                m = re.match(r"^[\s│|]*([a-z][a-z0-9-]*)\s{2,}", line)
                if m and len(path) < 3:
                    queue.append([*path, m.group(1)])
    return seen


def test_rendered_cli_help_carries_no_internal_vocabulary():
    """The `--help` text a user actually sees, walked from the real Typer app."""
    screens = _rendered_help()
    assert screens, "walked no help screens — the walker is broken, not the CLI clean"
    found = [(cmd, hits) for cmd, text in screens if (hits := _leaks(text))]
    assert not found, "\n".join(f"`{cmd} --help` leaks {hits}" for cmd, hits in found)
