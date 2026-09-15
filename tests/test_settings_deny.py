"""The leading spellings of a hook bypass are refused at the tool layer, a second door behind the hook.

`permissions.deny` in `.claude/settings.json` matches the whole command string -- the installed CLI (2.1.271)
matches `Bash(<body>)` as `^` + the body split on `*` and joined with `.*` + `$`, flag `s`, which `_denied` copies --
so it cannot tell an argv flag from a word inside a quoted message, and holds only the spellings with no such false
positive: the flag directly after `git commit`, `-c core.hooksPath=` directly after `git`, and `core.hooksPath`
followed by a value under `--local`, `--global` or no scope (the space before the `*` is what makes each config
rule a set; the bare read has no space). What a leading spelling misses -- a bundle (`-an`), an abbreviation
(`--no-veri`), an option before the subcommand (`git -C <dir> commit`), a later position (`--amend --no-verify`) --
is `.claude/hooks/bash-guard.sh`'s, an argv judge, and the last tests walk that hook's refused corpus through both
doors: what the rules miss the hook refuses, and what the rules deny one of the seven denies. Outside both,
deliberately: the pre-commit framework's `SKIP=<hook>` door, and an edit of `.git/hooks/` or of the settings file.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_bash_guard import REFUSED

SETTINGS = Path(__file__).resolve().parents[1] / ".claude" / "settings.json"
HOOK = SETTINGS.parent / "hooks" / "bash-guard.sh"
REQUIRED = (
    "Bash(git commit --no-verify*)",
    "Bash(git commit -n *)",
    "Bash(git commit -n)",
    "Bash(git -c core.hooksPath=*)",
    "Bash(git config core.hooksPath *)",
    "Bash(git config --local core.hooksPath *)",
    "Bash(git config --global core.hooksPath *)",
)
HEREDOC_MESSAGE = "$(cat <<'EOF'\nclaude(settings): --no-verify and -n are refused\n\n-n in a bundle too\nEOF\n)"


def _deny() -> list[str]:
    return json.loads(SETTINGS.read_text())["permissions"]["deny"]


def _denying_rule(command: str) -> str | None:
    for rule in _deny():
        body = rule.removeprefix("Bash(").removesuffix(")")
        if re.fullmatch(".*".join(re.escape(part) for part in body.split("*")), command, re.S):
            return rule
    return None


def _denied(command: str) -> bool:
    return _denying_rule(command) is not None


def _hook_refuses(command: str) -> bool:
    r = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )
    return r.returncode == 2


def test_the_bypass_rules_are_present() -> None:
    deny = _deny()
    for rule in REQUIRED:
        assert rule in deny, f"{rule} is not in permissions.deny"


def test_every_live_bypass_rule_is_a_leading_spelling() -> None:
    # The live rules about the bypass, not the file's own constants: a `*` anywhere but last would match the flag
    # as message text again.
    rules = [r for r in _deny() if "--no-verify" in r or " -n" in r or "core.hooksPath" in r]
    assert rules, "no bypass rule in permissions.deny"
    for rule in rules:
        assert rule.startswith("Bash(git ") and rule.endswith(")"), rule
        body = rule.removeprefix("Bash(").removesuffix(")")
        assert "*" not in body.rstrip("*"), rule


@pytest.mark.parametrize(
    "command",
    [
        "git commit --no-verify",
        "git commit --no-verify -m msg",
        "git commit -n",
        "git commit -n -m msg",
        "git -c core.hooksPath=/dev/null commit -m msg",
        "git config core.hooksPath /dev/null",
        "git config --local core.hooksPath /tmp/none",
        "git config --global core.hooksPath /x",
    ],
)
def test_a_leading_spelling_of_the_bypass_is_denied(command: str) -> None:
    assert _denied(command), command


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m msg",
        "git commit --amend -m msg",
        'git commit -m "docs: never --no-verify"',
        'git commit -m "chore: drop the -n door"',
        f'git commit -m "{HEREDOC_MESSAGE}"',
        "git config --get core.hooksPath",
        "git config core.hooksPath",
        "git config --unset core.hooksPath",
        "git config --local --get core.hooksPath",
        "git merge feature",
        "git -c color.ui=never log -1",
        "git log -n 5",
    ],
)
def test_message_text_and_a_config_read_are_admitted(command: str) -> None:
    assert not _denied(command), command


MISSED = [command for command, _ in REFUSED if not _denied(command)]


def test_the_leading_spellings_miss_part_of_the_corpus() -> None:
    assert MISSED, "every refused spelling is denied at the tool layer, so the walk below is empty"


@pytest.mark.parametrize("command", MISSED)
def test_what_the_leading_spelling_misses_the_hook_refuses(command: str) -> None:
    assert _hook_refuses(command), command


def test_what_the_rules_deny_one_of_the_seven_denies() -> None:
    denied = {command: _denying_rule(command) for command, _ in REFUSED if _denied(command)}
    assert denied, "no refused spelling is denied at the tool layer"
    for command, rule in denied.items():
        assert rule in REQUIRED, f"{command}: denied by {rule}, which is not one of the seven leading spellings"
