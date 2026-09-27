"""workspace-transport.zsh: the scratchpad step moves Claude Code's per-uid directory under the temp root the settings name."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra" / "scripts" / "workspace-transport.zsh"
SETTINGS = REPO / ".claude" / "settings.json"

# The assignment as the script spells it: its jq filter is taken from here and run, never restated.
_ROOT = re.compile(r"""^CLAUDE_TMP_ROOT="\$\(jq -r '(?P<filter>[^']+)' "\$REPO_DIR/\.claude/settings\.json"\)"$""", re.M)
_SCRATCH = r"\$CLAUDE_TMP_ROOT/claude-\$UID/\$PROJECT_SLUG"
_STEP = re.compile(r'^if \[\[ -d "' + _SCRATCH + r'" \]\]; then\n(?P<body>(?:  .*\n)+?)fi$', re.M)
_MKDIR = (
    r'^  "\$\{RSYNC\[@\]\}" --delete --rsync-path="mkdir -m 700 -p '
    r'\$\{\(q\)CLAUDE_TMP_ROOT\} \$\{\(q\)CLAUDE_TMP_ROOT\}/claude-\$UID && rsync" \\$'
)


def test_the_temp_root_the_script_reads_is_the_settings_override():
    line = _ROOT.search(SCRIPT.read_text())
    assert line, "the script no longer reads CLAUDE_TMP_ROOT out of .claude/settings.json with jq"
    read = subprocess.run(["jq", "-r", line.group("filter"), str(SETTINGS)], capture_output=True, text=True, check=True).stdout
    expected = json.loads(SETTINGS.read_text())["env"]["CLAUDE_CODE_TMPDIR"]
    assert read.strip() == expected, f"the script's filter reads {read.strip()!r}; the settings say {expected!r}"
    assert Path(expected).is_absolute(), expected


def test_the_scratchpad_step_syncs_the_per_uid_directory_under_that_root_to_the_same_path():
    text = SCRIPT.read_text()
    step = _STEP.search(text)
    assert step, "the scratchpad step is gone, or its guard no longer tests the per-uid directory under the root"
    assert re.search(_MKDIR, step.group("body"), re.M), (
        "the destination's root and per-uid directory are no longer made 0700 ahead of the rsync"
    )
    assert re.search(r'^    "' + _SCRATCH + r'/" "\$DEST:' + _SCRATCH + r'/"$', step.group("body"), re.M), (
        "the source or the destination is no longer the per-uid directory under CLAUDE_TMP_ROOT"
    )
    assert not re.search(r"/tmp/claude", text), "a literal temp root is back in the script"
