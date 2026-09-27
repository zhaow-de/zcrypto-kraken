"""The commands `.claude/skills/zcrypto-daily-ops/SKILL.md` gives the pass, run as written against a scratch repo."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "zcrypto-daily-ops" / "SKILL.md"
_FILE_TOUCH = re.compile(r"`(git -C <main checkout> log --name-only --since=[^`]*)`")


def _env(home: Path, stamp: str | None = None) -> dict[str, str]:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        # A date-only `--since` resolves in the local zone; pinned, the case reads the same on every host.
        "TZ": "UTC",
    }
    if stamp:
        env |= {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    return env


def test_the_file_touch_command_lists_a_commit_from_the_first_second_of_the_entrys_day(tmp_path):
    (command,) = _FILE_TOUCH.findall(SKILL.read_text(encoding="utf-8"))
    entry_day = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "develop", str(repo)], check=True, env=_env(tmp_path))
    (repo / "early.txt").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "early.txt"], check=True, env=_env(tmp_path))
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "early"], check=True, env=_env(tmp_path, f"{entry_day}T00:00:01Z"))
    argv = shlex.split(command.replace("<main checkout>", str(repo)).replace("<the last journal entry's date>", entry_day))
    listed = subprocess.run(argv, check=True, capture_output=True, text=True, env=_env(tmp_path)).stdout.split()
    assert "early.txt" in listed, (argv, listed)
