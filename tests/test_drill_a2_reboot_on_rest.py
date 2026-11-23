from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra/scripts/drill-a2-reboot-on-rest.sh"


def _record(outcome="pending", state="accepted", filled=0.0, txid="OABC"):
    return {
        "plans": [{"plan_id": "a2-x", "intents": [{"outcome": outcome, "filled_qty": 0.0}]}],
        "submitted": [
            {
                "plan_id": "a2-x",
                "intent_index": 0,
                "state": state,
                "filled_qty": filled,
                "client_order_id": "O-1",
                "events": [{"venue_order_id": txid}] if txid else [],
            }
        ],
    }


def _run(tmp_path, record):
    day = tmp_path / "journal" / "2026-11-23"
    day.mkdir(parents=True)
    if record is not None:
        (day / "exec-1.json").write_text(json.dumps(record))
    marker, fake = tmp_path / "rebooted", tmp_path / "bin"
    fake.mkdir()
    (fake / "systemctl").write_text(f"#!/bin/sh\ntouch {marker}\n")
    (fake / "systemctl").chmod(0o755)
    env = {**os.environ, "JOURNAL": str(tmp_path / "journal"), "PATH": f"{fake}:{os.environ['PATH']}"}
    run = subprocess.run(["bash", str(SCRIPT), "a2-x", "1", "dry"], env=env, capture_output=True, text=True, timeout=60)
    return run, marker.exists()


def test_a_resting_order_with_its_txid_is_the_reboot_and_a_dry_run_reboots_nothing(tmp_path):
    run, rebooted = _run(tmp_path, _record())
    assert run.returncode == 0 and " REST a2-x O-1 OABC" in run.stdout
    assert not rebooted


@pytest.mark.parametrize(
    "record",
    [_record(filled=0.5), _record(outcome="ambiguous"), _record(state="canceled")],
    ids=["row-filled", "intent-ended", "row-terminal"],
)
def test_an_order_that_fills_or_ends_stands_down_without_a_reboot(tmp_path, record):
    run, rebooted = _run(tmp_path, record)
    assert run.returncode == 3 and " STOP a2-x " in run.stdout
    assert not rebooted


@pytest.mark.parametrize(
    "record",
    [_record(txid=None), _record(state="submitted", txid=None), None],
    ids=["no-txid", "not-yet-accepted", "no-record"],
)
def test_an_order_not_yet_resting_waits_out_the_deadline(tmp_path, record):
    run, rebooted = _run(tmp_path, record)
    assert run.returncode == 4 and " TIMEOUT, last: WAIT" in run.stdout
    assert not rebooted
