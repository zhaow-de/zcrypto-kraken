import re

import typer
from typer.testing import CliRunner

from cli.__main__ import app

_INTERNAL = re.compile(r"iter-\d+|spec\s*`?\d{5}|OPS-\d|phase[- ]\d|T\d{4}", re.IGNORECASE)
runner = CliRunner()


def _all_paths():
    # typer 0.27 vendors its own click fork (typer._click): TyperGroup no longer subclasses the
    # installed `click.Group`, so `isinstance(cmd, click.Group)` never recurses -- duck-type on
    # `commands` instead, which every Typer(sub-)group still exposes.
    stack = [([], typer.main.get_command(app))]
    while stack:
        path, cmd = stack.pop()
        yield path
        if hasattr(cmd, "commands"):
            for name, sub in cmd.commands.items():
                stack.append(([*path, name], sub))


def test_no_internal_tracker_terms_in_any_help():
    offenders = []
    for path in _all_paths():
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0, path
        match = _INTERNAL.search(result.output)
        if match:
            offenders.append((path, match.group(0)))
    assert offenders == []
