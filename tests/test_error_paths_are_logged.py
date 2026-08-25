"""Every error path must reach `logging`, so it carries a level.

The NAS/capture alerting selects on the `level` LABEL that Alloy attaches at ingest by
matching our Python log format (infra/nas/config.alloy). A failure that is *printed*
rather than *logged* — a bare `typer.echo`, or a traceback rendered by Typer's own
excepthook — carries no timestamp and no level, so Alloy never labels it and the
`NAS · archive-pull ERROR logs` rule cannot see it. The archive path is unbackfillable;
a detector that stays green while the thing it watches is broken is worse than none.

See docs/open-topics/T0041-archive-pull-failures-do-not-page.md.
"""

from __future__ import annotations

import logging
import pathlib
import re
import subprocess
import sys

import pytest
import typer

from cli.engine.command import _abort
from cli.logging.formatters import PlainTextFormatter

# The regex Alloy uses at ingest to lift `level` out of our Python log lines. Kept in sync
# with infra/nas/config.alloy -- if this drifts, the alerting goes blind without any test
# failing anywhere else.
INGEST_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (?P<level>[A-Z]+) (?P<rest>.*)$")


def test_abort_logs_at_error_rather_than_printing(caplog: pytest.LogCaptureFixture) -> None:
    """`_abort` must LOG at ERROR.

    It used to `typer.echo("ERROR: ...", err=True)`, which the old text-grep alert happened
    to catch and the current label-based alert does not -- every `engine gate-export` failure
    reaches the operator through one of its 16 call sites.
    """
    with caplog.at_level(logging.ERROR):
        exc = _abort("gate textfile is unwritable")

    assert isinstance(exc, typer.Exit)
    assert exc.exit_code == 1
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [("ERROR", "gate textfile is unwritable")]


def test_a_logged_error_matches_the_ingest_regex() -> None:
    """A rendered ERROR record must be labellable by Alloy, or the alert cannot select it."""
    record = logging.LogRecord("engine.command", logging.ERROR, "command.py", 51, "boom", (), None)
    line = PlainTextFormatter().format(record)

    m = INGEST_RE.match(line)
    assert m is not None, f"Alloy's ingest regex would not label this line: {line!r}"
    assert m.group("level") == "ERROR"


def test_pull_entrypoint_log_helper_emits_a_labellable_line() -> None:
    """`pull-entrypoint.sh`'s failure paths must emit lines Alloy can label.

    Those lines are the only record when the CLI is killed before it can log for itself. The helper
    deliberately avoids GNU date's `%3N` width modifier: uutils' date (the Rust coreutils shipped by
    some distros) silently ignores it and emits all 9 nanosecond digits, which this regex rejects --
    a difference that does not show up on the GNU-coreutils container but would on a rebuilt image.
    """
    script = pathlib.Path(__file__).parent.parent / "infra" / "nas" / "pull-entrypoint.sh"
    body = script.read_text()
    fn = body[body.index("log() {") : body.index("\n}", body.index("log() {")) + 2]

    proc = subprocess.run(
        ["sh", "-c", f'{fn}\nlog ERROR "capture pull failed (source=x dest=y), continuing"'],
        capture_output=True,
        text=True,
    )

    line = proc.stderr.strip()
    m = INGEST_RE.match(line)
    assert m is not None, f"Alloy's ingest regex would not label this line: {line!r}"
    assert m.group("level") == "ERROR"
    assert "capture pull failed" in m.group("rest")


@pytest.mark.parametrize(
    "base,exc_name",
    [
        ("Exception", "RuntimeError"),
        # A Rust panic reaches Python as `pyo3_runtime.PanicException`, which derives from
        # `BaseException` so that `except Exception` does NOT catch it. The engine's node core is
        # compiled Rust, so this is the shape of its loudest possible fault -- and the one a narrow
        # catch drops through Typer's excepthook unlabelled, where the alerting cannot see it.
        ("BaseException", "Panicky"),
    ],
    ids=["exception", "baseexception-panic-shaped"],
)
def test_an_unhandled_fault_of_either_base_is_logged_before_the_process_dies(base, exc_name) -> None:
    """Guard-proving: the `BaseException` case FAILS against a wrapper that catches only
    `Exception` -- the process still dies, but with no ERROR-labelled line for Alloy to ingest."""
    prog = (
        "import typer\n"
        "from cli import __main__ as m\n"
        f"class Panicky({base}): pass\n"
        "@m.app.command()\n"
        "def boom():\n"
        f"    raise {exc_name}('kaboom')\n"
        "m.run()\n"
    )
    proc = subprocess.run([sys.executable, "-c", prog, "boom"], capture_output=True, text=True)

    assert proc.returncode != 0, "a crash must not exit 0"
    combined = proc.stdout + proc.stderr
    levelled = [line for line in combined.splitlines() if (m := INGEST_RE.match(line)) and m.group("level") == "ERROR"]
    assert levelled, f"no ERROR-labelled line Alloy could see; got:\n{combined}"
    assert "kaboom" in combined, "the original exception must still be reported"


@pytest.mark.parametrize("raiser,expected_code", [("SystemExit(3)", 3), ("KeyboardInterrupt()", 1)])
def test_the_two_control_flow_exits_pass_through_unlogged(raiser, expected_code) -> None:
    """The widened catch must not swallow either: click renders usage errors and `typer.Exit` as
    `SystemExit`, whose CODE carries meaning, and a Ctrl-C is an operator action, not a fault. A
    wrapper that logged these would page on every mistyped command."""
    prog = f"import typer\nfrom cli import __main__ as m\n@m.app.command()\ndef boom():\n    raise {raiser}\nm.run()\n"
    proc = subprocess.run([sys.executable, "-c", prog, "boom"], capture_output=True, text=True)

    combined = proc.stdout + proc.stderr
    assert not [line for line in combined.splitlines() if (m := INGEST_RE.match(line)) and m.group("level") == "ERROR"], (
        f"control-flow exit must not be logged as a fault; got:\n{combined}"
    )
    if expected_code == 3:
        assert proc.returncode == 3, "SystemExit's code carries meaning and must survive"


def test_unhandled_exception_is_logged_before_the_process_dies() -> None:
    """An uncaught exception must reach `logging` (level=ERROR + traceback), not just stderr.

    Typer installs its own `sys.excepthook` that renders a Rich traceback straight to stderr,
    bypassing `logging` entirely -- so a crash of the pull loop, the worst thing that can happen
    to the unbackfillable archive short of the disk filling, was invisible to the alert.

    Driven as a subprocess because the behaviour under test IS the process-level entry point
    (`cli.__main__:run`, the `zcrypto` console script), not the Typer app object.
    """
    prog = "import typer\nfrom cli import __main__ as m\n@m.app.command()\ndef boom():\n    raise RuntimeError('kaboom')\nm.run()\n"
    proc = subprocess.run(
        [sys.executable, "-c", prog, "boom"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0, "a crash must not exit 0"

    combined = proc.stdout + proc.stderr
    levelled = [line for line in combined.splitlines() if (m := INGEST_RE.match(line)) and m.group("level") == "ERROR"]
    assert levelled, f"no ERROR-labelled line Alloy could see; got:\n{combined}"
    assert "kaboom" in combined, "the original exception must still be reported"
    assert "RuntimeError" in combined, "the traceback must be preserved for debugging"
