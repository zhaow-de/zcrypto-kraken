from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra" / "scripts" / "workspace-transport.zsh"
SETTINGS = REPO / ".claude" / "settings.json"

_ROOT = re.compile(r"""^CLAUDE_TMP_ROOT="\$\(jq -r '(?P<filter>[^']+)' "\$REPO_DIR/\.claude/settings\.json"\)"$""", re.M)
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


def test_the_temp_root_the_script_reads_is_the_settings_override():
    line = _ROOT.search(SCRIPT.read_text())
    assert line, "the script no longer reads CLAUDE_TMP_ROOT out of .claude/settings.json with jq"
    read = subprocess.run(["jq", "-r", line.group("filter"), str(SETTINGS)], capture_output=True, text=True, check=True).stdout
    expected = json.loads(SETTINGS.read_text())["env"]["CLAUDE_CODE_TMPDIR"]
    assert read.strip() == expected, f"the script's filter reads {read.strip()!r}; the settings say {expected!r}"
    assert Path(expected).is_absolute(), expected


def test_the_scratchpad_step_walks_the_settings_root_and_tmp_the_cli_default():
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
