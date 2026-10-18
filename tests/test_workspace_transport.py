from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra" / "scripts" / "workspace-transport.zsh"

_ROOT = re.compile(r"^CLAUDE_TMP_ROOT=.*$", re.M)
_ROOTS = re.compile(r"^typeset -aU SCRATCH_ROOTS=\((?P<roots>[^)]*)\)$", re.M)
_SCRATCH = r"\$root/claude-\$UID/\$PROJECT_SLUG"
_STEP = re.compile(
    r'^for root in "\$\{SCRATCH_ROOTS\[@\]\}"; do\n  if \[\[ -d "'
    + _SCRATCH
    + r'" \]\]; then\n(?P<body>(?:    .*\n)+?)  fi\ndone$',
    re.M,
)
_MKDIR = (
    r'^    "\$\{RSYNC\[@\]\}" --delete --rsync-path="mkdir -m 700 -p \$\{\(q\)root\} \$\{\(q\)root\}/claude-\$UID && rsync" \\$'
)
_LOCAL_EXCLUDES = re.compile(r"^LOCAL_EXCLUDES=\(.*\)$", re.M)


@pytest.mark.parametrize(
    ("launch_env", "root"),
    [
        ({"CLAUDE_CODE_TMPDIR": "/home/u/.cache/claude-tmp"}, "/home/u/.cache/claude-tmp"),
        ({}, "/tmp"),
        ({"CLAUDE_CODE_TMPDIR": ""}, "/tmp"),
    ],
    ids=["named", "unset", "empty"],
)
def test_the_temp_root_is_the_launch_environments_and_tmp_when_it_names_none(launch_env, root):
    (line,) = _ROOT.findall(SCRIPT.read_text())
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_TMPDIR"} | launch_env
    # `sh` reads the zsh script's line: this expansion means the same in both, and the suite then needs no zsh.
    read = subprocess.run(
        ["sh", "-c", f"{line}\nprintf '%s\\n' \"$CLAUDE_TMP_ROOT\""], env=env, capture_output=True, text=True, check=True
    )
    assert read.stdout == f"{root}\n", read


def test_the_scratchpad_step_walks_the_launch_root_and_tmp_the_cli_default():
    roots = _ROOTS.search(SCRIPT.read_text())
    assert roots, "the scratchpad step no longer walks a SCRATCH_ROOTS array"
    assert roots.group("roots") == '"$CLAUDE_TMP_ROOT" /tmp', roots.group("roots")


def test_the_scratchpad_step_syncs_the_per_uid_directory_under_each_root_to_the_same_path():
    text = SCRIPT.read_text()
    step = _STEP.search(text)
    assert step, "the scratchpad step is gone, or its guard no longer tests the per-uid directory under the root walked"
    assert re.search(_MKDIR, step.group("body"), re.M), (
        "the destination's root and per-uid directory are no longer made 0700 ahead of the rsync"
    )
    assert re.search(r'^      "' + _SCRATCH + r'/" "\$DEST:' + _SCRATCH + r'/"$', step.group("body"), re.M), (
        "the source or the destination is no longer the per-uid directory under the root walked"
    )
    assert not re.search(r"/tmp/claude", text), "a literal per-uid directory is back in the script"


def test_the_local_mirror_leaves_each_machines_trial_attempts_log_and_its_torn_copies_where_they_are(tmp_path):
    (line,) = _LOCAL_EXCLUDES.findall(SCRIPT.read_text())
    source, destination = tmp_path / "source", tmp_path / "destination"
    for root in (source, destination):
        root.mkdir()
        (root / "trial-attempts.jsonl").write_text(f"{root.name}\n")
        (root / f"trial-attempts.jsonl.torn-{root.name}").write_text(f"{root.name}\n")
    (source / "memo.md").write_text("memo\n")
    (destination / "retro.md").write_text("destination only\n")
    # `bash` runs the zsh script's array line, which means the same in both, so the suite needs no zsh.
    mirror = f'{line}\nrsync -a --delete "${{LOCAL_EXCLUDES[@]}}" "$1/" "$2/"'
    subprocess.run(["bash", "-c", mirror, "bash", str(source), str(destination)], check=True, capture_output=True)

    kept = sorted(path.name for path in destination.iterdir())
    assert kept == ["memo.md", "trial-attempts.jsonl", "trial-attempts.jsonl.torn-destination"], kept
    assert (destination / "trial-attempts.jsonl").read_text() == "destination\n"


def test_both_local_rsyncs_pass_the_exclusions():
    # config-selector-ok: an rsync command, not a setting; a comment line naming both moves the count off 2
    rsyncs = [line for line in SCRIPT.read_text().splitlines() if '"${RSYNC[@]}"' in line and '"$REPO_DIR/.local/"' in line]
    # config-selector-ok: each line is one of the two rsync commands selected above
    assert len(rsyncs) == 2 and all('"${LOCAL_EXCLUDES[@]}"' in line for line in rsyncs), (
        "the dry run that counts the plan's .local/ deletions and the .local/ mirror no longer both pass LOCAL_EXCLUDES",
        rsyncs,
    )
