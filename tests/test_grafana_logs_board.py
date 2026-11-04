from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOARD = json.loads((REPO / "infra/grafana/zcrypto-logs-dashboard.json").read_text())


def test_every_query_variable_on_the_logs_board_resolves_on_dashboard_load():
    # 2, on time range change, re-runs the variable's query on every auto-refresh, and Grafana then cancels and re-runs
    # every panel that reads it.
    refresh = {v["name"]: v.get("refresh") for v in BOARD["templating"]["list"] if v["type"] == "query"}
    assert refresh and set(refresh.values()) == {1}, refresh
