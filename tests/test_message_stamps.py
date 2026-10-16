"""message-stamps.py: a commit message carrying a placeholder stamp outside a code span and a fenced block is refused, and a read stamp, a hex beside a colon, a quoted placeholder and a comment line are admitted."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "message-stamps.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load(_SCRIPT, "message_stamps")

# (message, the stamp named)
REFUSED = [
    ("docs: landed at 2026-10-16 14:2xZ\n", "14:2x"),
    ("fix: the daily pass at 1x:30\n", "1x:30"),
    ("chore: stamped ??:?? until the record is read\n", "??:??"),
    ("chore: 14:25Z\n\nbody read at 14:XXZ\n", "14:XX"),
]

ADMITTED = {
    "a read stamp": "docs: landed at 2026-10-16 14:25Z, 09:05 and 23:59:59\n",
    "a hex beside a colon": "fix: after ab12:0xff and a0:ff, 0x10:0x20 is the pair\n",
    "a code span": "docs: the memo's `14:2xZ` shape and `??:??` are refused\n",
    "a fenced block": "docs: the shape\n\n```\n14:2xZ and ??:??\n```\n\n~~~\n1x:30\n~~~\nafter\n",
    "a comment line": "docs: x\n# 14:2xZ is a comment git drops\n",
    "below the scissors": f"docs: x\n{'# ' + '-' * 24 + ' >8 ' + '-' * 24}\n+14:2xZ in the diff\n",
}


@pytest.mark.parametrize(("message", "stamp"), REFUSED, ids=[s for _, s in REFUSED])
def test_a_placeholder_stamp_is_refused_and_named(message: str, stamp: str):
    assert [s for _, s in guard.stamps(message)] == [stamp]


@pytest.mark.parametrize("message", ADMITTED.values(), ids=ADMITTED.keys())
def test_a_read_stamp_a_hex_and_a_quoted_or_commented_placeholder_are_admitted(message: str):
    assert guard.stamps(message) == []


def test_a_placeholder_outside_a_closed_span_or_fence_is_still_refused():
    message = "docs: `14:25Z` then 1x:30\n\n```\n??:??\n```\n14:2xZ after the fence\n"
    assert guard.stamps(message) == [(1, "1x:30"), (6, "14:2x")]


def _run(tmp_path: pathlib.Path, message: str, *args: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "MSG").write_text(message)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *(args or (str(tmp_path / "MSG"),))], cwd=tmp_path, capture_output=True, text=True
    )


def test_the_script_refuses_with_the_stamp_and_the_remedy_and_admits_silently(tmp_path):
    refused = _run(tmp_path, "docs: landed 14:2xZ\n\nread at 1x:30\n")
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert refused.stdout.startswith("message-stamps: refused\n  - line 1: '14:2x'\n  - line 3: '1x:30'\n"), refused.stdout
    assert "paste the printed value of `date -u` or of the record" in refused.stdout
    passed = _run(tmp_path, "docs: landed 14:25Z\n")
    assert (passed.returncode, passed.stdout, passed.stderr) == (0, "", "")


def test_the_script_names_a_message_it_cannot_read_and_exits_2(tmp_path):
    proc = subprocess.run([sys.executable, str(_SCRIPT), "missing"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 2 and "cannot read" in proc.stderr and "Traceback" not in proc.stderr
    proc = subprocess.run([sys.executable, str(_SCRIPT)], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 2 and proc.stderr.startswith("usage:")


def test_the_hook_is_wired_at_the_commit_msg_stage():
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text())
    hooks = [h for repo in config["repos"] if repo["repo"] == "local" for h in repo["hooks"] if h["id"] == "message-stamps"]
    assert len(hooks) == 1, "one local hook with the id"
    (hook,) = hooks
    assert hook["stages"] == ["commit-msg"] and hook["always_run"] is True
    assert hook["entry"] == "uv run python infra/scripts/message-stamps.py"
