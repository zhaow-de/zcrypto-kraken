from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra/scripts/drill-a2-reboot-on-rest.sh"


def _record(outcome="pending", state="accepted", filled=0.0, txid="OABC", plan_id="a2-x"):
    return {
        "plans": [{"plan_id": plan_id, "intents": [{"outcome": outcome, "filled_qty": 0.0}]}],
        "submitted": [
            {
                "plan_id": plan_id,
                "intent_index": 0,
                "state": state,
                "filled_qty": filled,
                "client_order_id": "O-1",
                "events": [{"venue_order_id": txid}] if txid else [],
            }
        ],
    }


def _run(tmp_path, *records, mode="dry"):
    day = tmp_path / "journal" / "2026-11-23"
    day.mkdir(parents=True)
    for i, record in enumerate(records):
        path = day / f"exec-{i}.json"
        path.write_text(json.dumps(record))
        os.utime(path, (1_000_000 + i, 1_000_000 + i))
    # PATH holds the fake systemctl and the three tools the script runs, so no real systemctl is reachable.
    marker, bin_ = tmp_path / "rebooted", tmp_path / "bin"
    bin_.mkdir()
    for tool in ("date", "python3", "sleep"):
        (bin_ / tool).symlink_to(shutil.which(tool))
    (bin_ / "systemctl").write_text(f'#!/bin/sh\necho "$*" > {marker}\n')
    (bin_ / "systemctl").chmod(0o755)
    env = {**os.environ, "JOURNAL": str(tmp_path / "journal"), "PATH": str(bin_)}
    run = subprocess.run(
        [shutil.which("bash"), str(SCRIPT), "a2-x", "1", mode], env=env, capture_output=True, text=True, timeout=60
    )
    return run, marker.read_text().strip() if marker.exists() else None


def test_live_reboots_the_moment_the_order_rests(tmp_path):
    run, reboot = _run(tmp_path, _record(), mode="live")
    assert run.returncode == 0 and " REST a2-x O-1 OABC" in run.stdout
    assert reboot == "reboot"


def test_a_dry_run_prints_the_rest_and_reboots_nothing(tmp_path):
    run, reboot = _run(tmp_path, _record())
    assert run.returncode == 0 and " REST a2-x O-1 OABC" in run.stdout
    assert reboot is None


def test_a_boundary_record_written_after_the_plans_does_not_hide_it(tmp_path):
    run, _ = _run(tmp_path, _record(), _record(plan_id="r3-20261123-20"))
    assert run.returncode == 0 and " REST a2-x O-1 OABC" in run.stdout


@pytest.mark.parametrize(
    "record",
    [_record(filled=0.5), _record(outcome="ambiguous"), _record(state="venue_canceled"), _record(state="ambiguous")],
    ids=["row-filled", "intent-ended", "row-terminal", "row-ambiguous"],
)
def test_an_order_that_fills_or_ends_stands_down_without_a_reboot(tmp_path, record):
    run, reboot = _run(tmp_path, record, mode="live")
    assert run.returncode == 3 and " STOP a2-x " in run.stdout
    assert reboot is None


@pytest.mark.parametrize(
    "records",
    [(_record(txid=None),), (_record(state="submitting", txid=None),), (_record(plan_id="r3-20261123-20"),), ()],
    ids=["accepted-no-txid", "submitting", "no-plan", "no-record"],
)
def test_an_order_not_yet_resting_waits_out_the_deadline(tmp_path, records):
    run, reboot = _run(tmp_path, *records, mode="live")
    assert run.returncode == 4 and " TIMEOUT, last: WAIT" in run.stdout
    assert reboot is None
