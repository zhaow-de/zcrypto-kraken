"""The deploy-log audit's two arms: the rows that landed inside a published API-impacting window, and the engine rows that landed outside the 4-hourly gap."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import urllib.error

import pytest
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "deploy-log-audit.py"
FEED = _ROOT / "tests" / "fixtures" / "kraken_scheduled_maintenances.json"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit = _load(_SCRIPT, "deploy_log_audit")


def _row(ts: str, *, limit: str = "zcrypto", tags: str = "", rc: int = 0, extra_vars: dict | None = None) -> dict:
    return {"ts": ts, "limit": limit, "tags": tags, "rc": rc, "playbook": "site.yml", "extra_vars": extra_vars or {}}


def _log(tmp_path: pathlib.Path, rows: list[dict]) -> str:
    path = tmp_path / "deploy-log.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return str(path)


def test_api_impacting_reads_a_component_name_and_the_entrys_own_name():
    """An empty `components` is not an absent impact -- the second window carries it in its own name."""
    windows = audit.api_impacting(json.loads(FEED.read_text())["scheduled_maintenances"])
    assert [w["name"] for w in windows] == [
        "Beeks Maintenance",
        "REST API rate-limit change",
        "Derivatives Platform Maintenance",
    ]


def test_api_impacting_matches_the_venues_other_spelling_of_websocket():
    """The venue spells it `WebSocket` on one entry and `Websocket` on another, so the match folds case."""
    entry = {"name": "x", "components": [{"name": "Websocket API"}]}
    assert audit.api_impacting([entry]) == [entry]


@pytest.mark.parametrize(
    "name", ["Scheduled restart of the status page", "Website Restoration", "Restricted trading", "Interest accrual maintenance"]
)
def test_api_impacting_does_not_read_rest_inside_a_word(name):
    """`REST` is an API, so the match is word-bounded: folding case alone would read every one of
    these as API-impacting and book a converge against a window that constrains nothing."""
    assert audit.api_impacting([{"name": name, "components": []}]) == []


def test_maintenance_counts_the_row_inside_an_api_impacting_window(tmp_path, capsys):
    """The second row sits inside the fixture's website window, which impacts no API and must not count."""
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z", limit="nas"), _row("2026-08-20T01:00:00Z")])
    assert audit.main(["maintenance", "--log", log, "--from-snapshot", str(FEED)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["rows inside an API-impacting window 1 of 2", "  2026-08-28T23:40:17Z nas Beeks Maintenance"]


def test_the_venue_facing_derivation_still_holds():
    """The constant is hand-maintained and rests on this set; nothing else would notice it going stale."""
    infra = pathlib.Path(__file__).resolve().parents[1] / "infra"
    # The excluded hosts' payloads are rendered from outside their roles: the NAS compose stack, and the files
    # the `access` role copies to the bridgehead. `infra/docker/` builds the image the NAS runs and names Kraken;
    # what exonerates the NAS is the entrypoint override, asserted below, not that image.
    payloads = {d.name: d for d in (infra / "ansible" / "roles").iterdir() if d.is_dir()}
    payloads |= {"nas-stack": infra / "nas", "access-files": infra / "ansible" / "files"}
    # ... and the vars rendered onto them: each excluded host's host_vars, plus the group_vars of its groups and their ancestors.
    inventory = yaml.safe_load((infra / "ansible" / "inventory" / "hosts.yml").read_text())
    members: dict[str, set[str]] = {}

    def collect(name: str, node: dict) -> None:
        members.setdefault(name, set()).update((node or {}).get("hosts") or {})
        for child, sub in ((node or {}).get("children") or {}).items():
            members.setdefault(name, set()).add(f"group:{child}")
            collect(child, sub)

    def groups_of(host: str) -> set[str]:
        found = {g for g, m in members.items() if host in m}
        while True:
            parents = {g for g, m in members.items() if any(f"group:{d}" in m for d in found)} - found
            if not parents:
                return found
            found |= parents

    for name, node in inventory.items():
        collect(name, node)
    for host in audit.NO_VENUE_EXPOSURE:
        payloads[f"vars:{host}"] = infra / "ansible" / "host_vars" / host
        for group in groups_of(host):
            if (infra / "ansible" / "group_vars" / group).is_dir():
                payloads[f"vars:{group}"] = infra / "ansible" / "group_vars" / group
    walked = {name for name, d in payloads.items() if name.startswith("vars:") and d.is_dir()}
    assert {f"vars:{h}" for h in audit.NO_VENUE_EXPOSURE} | {"vars:all"} <= walked, walked
    speaks = {
        name
        for name, d in payloads.items()
        if any("kraken" in f.read_text(errors="ignore").lower() for f in d.rglob("*") if f.is_file())
    }
    assert speaks == {"capture", "engine", "ops"}, (
        f"the Kraken-referencing payloads are now {sorted(speaks)}; `NO_VENUE_EXPOSURE` "
        f"({sorted(audit.NO_VENUE_EXPOSURE)}) rests on that set and must be re-judged"
    )
    stack = yaml.safe_load((infra / "nas" / "compose.yaml").read_text())
    assert stack["services"]["archive-pull"]["entrypoint"] == ["/opt/pull-entrypoint.sh"]


@pytest.mark.parametrize("host", ["nas", "zaccess"])
def test_venue_facing_drops_a_host_a_window_cannot_harm(tmp_path, capsys, host):
    """The unnarrowed arm still reports the row, so the flag narrows the count and hides nothing."""
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z", limit=host), _row("2026-08-20T01:00:00Z")])
    assert audit.main(["maintenance", "--log", log, "--from-snapshot", str(FEED)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "rows inside an API-impacting window 1 of 2"

    assert audit.main(["maintenance", "--venue-facing", "--log", log, "--from-snapshot", str(FEED)]) == 0
    assert capsys.readouterr().out.splitlines() == ["rows inside an API-impacting window 0 of 1 venue-facing"]


@pytest.mark.parametrize("host", ["zcrypto", "zcrypto-red", "zcrypto-ops"])
def test_venue_facing_keeps_every_host_that_speaks_to_the_venue(tmp_path, capsys, host):
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z", limit=host)])
    assert audit.main(["maintenance", "--venue-facing", "--log", log, "--from-snapshot", str(FEED)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "rows inside an API-impacting window 1 of 1 venue-facing"
    assert out[1].endswith(f"{host} Beeks Maintenance")


def test_maintenance_counts_none_when_every_row_sits_outside(tmp_path, capsys):
    log = _log(tmp_path, [_row("2026-08-29T03:00:00Z"), _row("2026-09-01T02:00:00Z")])
    assert audit.main(["maintenance", "--log", log, "--from-snapshot", str(FEED)]) == 0
    assert capsys.readouterr().out.splitlines() == ["rows inside an API-impacting window 0 of 2"]


def test_engine_window_counts_the_rows_outside_the_gap(tmp_path, capsys):
    """First row is 200 s past a boundary, second is 300 s short of the next; the third clears both."""
    rows = [
        _row("2026-09-01T00:03:20Z", tags="engine"),
        _row("2026-09-01T03:55:00Z", tags="engine,ops", rc=1),
        _row("2026-09-01T01:00:00Z", tags="engine"),
    ]
    assert audit.main(["engine-window", "--log", _log(tmp_path, rows)]) == 0
    assert capsys.readouterr().out.strip() == "engine rows 3 outside window 2 failed 1 on the completion floor 0"


def test_engine_window_admits_the_row_the_playbook_admitted_on_a_completed_cycles_floor(tmp_path, capsys):
    """744 s past a boundary: past the earliest the playbook's completion floor can open, short of the fixed one."""
    rows = [_row("2026-09-19T08:12:24Z", tags="capture,engine")]
    assert audit.main(["engine-window", "--log", _log(tmp_path, rows)]) == 0
    assert capsys.readouterr().out.strip() == "engine rows 1 outside window 0 failed 0 on the completion floor 1"


@pytest.mark.parametrize(
    ("why", "row"),
    [
        (
            "it carried the bypass",
            _row("2026-09-19T08:12:24Z", tags="engine", extra_vars={"engine_window_override": "a reason given"}),
        ),
        ("the run did not succeed", _row("2026-09-19T08:12:24Z", tags="engine", rc=2)),
        ("no completed cycle opens the gap this early", _row("2026-09-19T08:04:59Z", tags="engine")),
    ],
)
def test_engine_window_still_counts_a_row_ahead_of_the_fixed_floor_that_the_playbook_did_not_admit(tmp_path, capsys, why, row):
    assert audit.main(["engine-window", "--log", _log(tmp_path, [row])]) == 0
    assert capsys.readouterr().out.strip().startswith("engine rows 1 outside window 1 "), why


def test_engine_window_counts_none_when_every_engine_row_sits_in_the_gap(tmp_path, capsys):
    """The capture row is outside the gap and belongs to no engine cycle, so the tag filter must drop it."""
    rows = [_row("2026-09-01T01:00:00Z", tags="engine"), _row("2026-09-01T00:10:00Z", tags="capture")]
    assert audit.main(["engine-window", "--log", _log(tmp_path, rows)]) == 0
    assert capsys.readouterr().out.strip() == "engine rows 1 outside window 0 failed 0 on the completion floor 0"


def test_an_unreachable_feed_exits_2_rather_than_counting_zero(tmp_path, capsys, monkeypatch):
    def _unreachable(*_args, **_kwargs):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(audit, "fetch_maintenances", _unreachable)
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z")])
    assert audit.main(["maintenance", "--log", log]) == audit.EXIT_FEED_UNREACHABLE
    captured = capsys.readouterr()
    assert "feed unreachable" in captured.err
    assert captured.out == ""


def test_a_snapshot_reads_back_the_count_the_network_produced(tmp_path, capsys, monkeypatch):
    payload = json.loads(FEED.read_text())["scheduled_maintenances"]
    monkeypatch.setattr(audit, "fetch_maintenances", lambda *_a, **_k: payload)
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z", limit="nas")])
    snapshot = tmp_path / "feed.json"
    assert audit.main(["maintenance", "--log", log, "--snapshot", str(snapshot)]) == 0
    from_network = capsys.readouterr().out

    def _reached_the_network(*_args, **_kwargs):
        raise AssertionError("the --from-snapshot arm fetched the feed")

    monkeypatch.setattr(audit, "fetch_maintenances", _reached_the_network)
    assert audit.main(["maintenance", "--log", log, "--from-snapshot", str(snapshot)]) == 0
    assert capsys.readouterr().out == from_network


@pytest.mark.parametrize(
    "argv",
    [
        ["engine-window", "--from-snapshot", str(FEED)],
        ["maintenance", "--snapshot", "written.json", "--from-snapshot", str(FEED)],
        ["engine-window", "--venue-facing"],
    ],
)
def test_the_feed_flags_are_refused_where_they_would_do_nothing(tmp_path, argv):
    with pytest.raises(SystemExit) as raised:
        audit.main([*argv, "--log", _log(tmp_path, [_row("2026-09-01T01:00:00Z", tags="engine")])])
    assert raised.value.code == 2
