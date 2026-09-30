"""`infra/scripts/grafana-push.sh` — the bearer's delivery to curl."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "grafana-push.sh"
TOKEN = "glsa_TOTALLY_NOT_A_REAL_TOKEN_0123456789"


def test_every_curl_call_goes_through_gcurl():
    code = [line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")]
    bare = [line for line in code if re.search(r"(^|[^g])curl ", line) and not line.startswith("gcurl()")]
    assert bare == []
    bearer_sites = [line for line in code if "GRAFANA_SA_TOKEN" in line and not line.startswith(": ")]
    assert [line[:8] for line in bearer_sites] == ["gcurl() "]


def test_gcurl_hands_curl_the_bearer_as_a_config_line_and_never_in_argv(tmp_path):
    fake = tmp_path / "curl"
    fake.write_text(
        '#!/usr/bin/env bash\nprintf "ARGV %s\\n" "$*"\n'
        'while [ $# -gt 0 ]; do if [ "$1" = -K ]; then printf "CONFIG %s\\n" "$(cat "$2")"; fi; shift; done\n'
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    gcurl = re.search(r"^gcurl\(\) .*$", SCRIPT.read_text(), re.M).group(0)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "GRAFANA_SA_TOKEN": TOKEN}
    r = subprocess.run(["bash", "-c", gcurl + "\ngcurl -fsS https://example.invalid/x"], capture_output=True, text=True, env=env)
    argv = [line for line in r.stdout.splitlines() if line.startswith("ARGV ")]
    config = [line for line in r.stdout.splitlines() if line.startswith("CONFIG ")]
    assert r.returncode == 0
    assert TOKEN not in argv[0]
    assert config == [f'CONFIG header = "Authorization: Bearer {TOKEN}"']
