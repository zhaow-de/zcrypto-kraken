"""`infra/scripts/pins-converged.py` — the (pin, host) pairs no deploy-log row on that host converged."""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra" / "scripts" / "pins-converged.py"


def _load():
    spec = importlib.util.spec_from_file_location("pins_converged", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pins = _load()

_HEADER = "| service | host | digest (sha256, first 12) | since (UTC) | rollback operand |\n| --- | --- | --- | --- | --- |\n"
PIN = "| engine | zcrypto | `ac6172b9ffb2` — revision `4925e060` | 2026-09-04 | `6ece` |\n"


def _row(
    host: str = "zcrypto", digest: str = "deadbeefdead", *, rc: int = 0, key: str = "extra_vars", applied: bool = False
) -> dict:
    row = {"ts": "2026-09-01T00:00:00Z", "limit": host, "rc": rc, "tags": "", key: {"x_digest": digest}}
    if applied:
        row.setdefault("extra_vars", {})["nas_apply_compose"] = True
    return row


def _owed(tmp_path: pathlib.Path, log_rows: list[dict], pin_rows: list[str], header: str = _HEADER, groups: dict | None = None):
    log = tmp_path / "deploy-log.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in log_rows))
    table = tmp_path / "fleet-pins.md"
    table.write_text("# pins\n\n" + header + "".join(pin_rows))
    return pins.unconverged_pins(table, pins.converged_digests(log, groups or {}))


def test_a_digest_the_hosts_own_successful_row_was_handed_is_not_owed(tmp_path):
    assert _owed(tmp_path, [_row(digest="ac6172b9ffb2aaaa")], [PIN]) == []


def test_a_digest_no_row_carries_is_owed_and_names_its_row(tmp_path):
    assert _owed(tmp_path, [_row()], [PIN]) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_evidence_on_another_host_does_not_cover_this_one(tmp_path):
    row = "| alloy | zcrypto, nas | `491b0578c049` | 2026-09-01 | `4f6d` |\n"
    assert _owed(tmp_path, [_row(digest="491b0578c049")], [row]) == [("alloy", "nas", "491b0578c049")]


def test_a_group_limited_run_evidences_every_host_of_the_group(tmp_path):
    rows = [PIN, "| capture | zcrypto-red | `ac6172b9ffb2` | 2026-09-04 | `6ece` |\n"]
    groups = {"capture_host": {"zcrypto", "zcrypto-red"}}
    assert _owed(tmp_path, [_row("capture_host", "ac6172b9ffb2")], rows, groups=groups) == []
    # with no inventory the limit is taken literally, and no pin row names that host
    assert len(_owed(tmp_path, [_row("capture_host", "ac6172b9ffb2")], rows)) == 2


def test_a_committed_pin_on_a_run_that_applied_the_stack_is_evidence(tmp_path):
    assert _owed(tmp_path, [_row(digest="ac6172b9ffb2", key="committed_pins", applied=True)], [PIN]) == []


def test_a_committed_pin_on_a_render_only_run_is_not(tmp_path):
    log = [_row(digest="ac6172b9ffb2", key="committed_pins")]
    assert _owed(tmp_path, log, [PIN]) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_a_committed_pin_on_a_run_that_skipped_the_nas_role_is_not(tmp_path):
    log = [_row(digest="ac6172b9ffb2", key="committed_pins", applied=True)]
    log[0]["tags"] = "alloy"
    assert _owed(tmp_path, log, [PIN]) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_an_interrupted_pass_does_not_count_as_converged(tmp_path):
    assert _owed(tmp_path, [_row(digest="ac6172b9ffb2", rc=99)], [PIN]) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_a_version_pin_is_not_in_the_set(tmp_path):
    versions = "\n| package | host | version | since (UTC) | notes |\n| --- | --- | --- | --- | --- |\n| agentboard | zcrypto-ops | `0.4.23` | 2026-08-26 | — |\n"
    assert _owed(tmp_path, [_row(digest="ac6172b9ffb2")], [PIN, versions]) == []


def test_the_var_name_is_never_matched_on(tmp_path):
    log = [{"ts": "2026-09-01T00:00:00Z", "limit": "zcrypto", "rc": 0, "extra_vars": {"some_future_role_digest": "ac6172b9ffb2"}}]
    assert _owed(tmp_path, log, [PIN]) == []


def test_a_reordered_table_names_the_right_host_on_the_row_it_owes(tmp_path):
    header = "| service | digest (sha256, first 12) | host | since (UTC) |\n| --- | --- | --- | --- |\n"
    row = "| engine | `ac6172b9ffb2` | zcrypto | 2026-09-04 |\n"
    assert _owed(tmp_path, [_row()], [row], header) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_a_table_with_no_digest_column_exits_2_rather_than_counting_zero(tmp_path):
    header = "| service | host | since |\n| --- | --- | --- |\n"
    with pytest.raises(SystemExit) as raised:
        _owed(tmp_path, [_row()], ["| engine | zcrypto | 2026 |\n"], header)
    assert raised.value.code == 2


def test_a_log_that_is_not_jsonl_exits_2_rather_than_counting_zero(tmp_path):
    log = tmp_path / "deploy-log.jsonl"
    log.write_text('{"ts": "x"}\nnot json\n')
    with pytest.raises(SystemExit) as raised:
        pins.converged_digests(log, {})
    assert raised.value.code == 2


def test_the_inventory_expands_a_group_to_its_hosts_at_any_depth():
    groups = pins.inventory_groups(pathlib.Path(__file__).resolve().parents[1])
    assert groups["capture_host"] == {"zcrypto", "zcrypto-red"} and "nas" in groups["observed"]
    assert groups["cache_host"] == {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"}
    assert groups["cache_host"] <= groups["observed"]


def test_the_real_pair_reads_zero():
    root = pathlib.Path(__file__).resolve().parents[1]
    evidence = pins.converged_digests(root / "docs/reference/deploy-log.jsonl", pins.inventory_groups(root))
    assert pins.unconverged_pins(root / "docs/reference/fleet-pins.md", evidence) == []
