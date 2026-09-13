"""`infra/scripts/pins-converged.py` — the pin rows no deploy-log row converged."""

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

_PINS_HEADER = "| service | host | digest (sha256, first 12) | since (UTC) | rollback operand |\n| --- | --- | --- | --- | --- |\n"


def _pins(tmp_path: pathlib.Path, rows: list[str]) -> pathlib.Path:
    path = tmp_path / "fleet-pins.md"
    path.write_text("# pins\n\n" + _PINS_HEADER + "".join(rows))
    return path


def _log(tmp_path: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    path = tmp_path / "deploy-log.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_a_digest_some_row_converged_is_not_owed(tmp_path):
    log = _log(tmp_path, [{"ts": "x", "rc": 0, "extra_vars": {"capture_digest": "06998998e876aaaa"}}])
    p = _pins(tmp_path, ["| capture | zcrypto | `06998998e876` — revision `c7067af3` | 2026-09-07 | `ac61` |\n"])
    assert pins.unconverged_pins(p, pins.converged_digests(log)) == []


def test_a_digest_no_row_carries_is_owed_and_names_its_row(tmp_path):
    log = _log(tmp_path, [{"ts": "x", "rc": 0, "extra_vars": {"capture_digest": "deadbeefdead"}}])
    p = _pins(tmp_path, ["| engine | zcrypto | `ac6172b9ffb2` — revision `4925e060` | 2026-09-04 | `6ece` |\n"])
    assert pins.unconverged_pins(p, pins.converged_digests(log)) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_a_committed_pin_alone_does_not_count_as_converged(tmp_path):
    """It is read from `host_vars` at record time, so it lands in the row whatever the run deployed."""
    log = _log(tmp_path, [{"ts": "x", "rc": 0, "committed_pins": {"engine": "ac6172b9ffb2"}}])
    p = _pins(tmp_path, ["| engine | zcrypto | `ac6172b9ffb2` | 2026-09-04 | `6ece` |\n"])
    assert pins.unconverged_pins(p, pins.converged_digests(log)) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_a_failed_run_does_not_count_as_converged(tmp_path):
    """A refused run is recorded like a pass; the log already carries one."""
    log = _log(tmp_path, [{"ts": "x", "rc": 99, "extra_vars": {"engine_digest": "ac6172b9ffb2"}}])
    p = _pins(tmp_path, ["| engine | zcrypto | `ac6172b9ffb2` | 2026-09-04 | `6ece` |\n"])
    assert pins.unconverged_pins(p, pins.converged_digests(log)) == [("engine", "zcrypto", "ac6172b9ffb2")]


def test_a_table_whose_digest_column_moved_is_still_read(tmp_path):
    """A reordered table still reads: the column is found by its header."""
    log = _log(tmp_path, [{"ts": "x", "rc": 0, "extra_vars": {"engine_digest": "ac6172b9ffb2"}}])
    path = tmp_path / "fleet-pins.md"
    path.write_text(
        "# pins\n\n| service | digest (sha256, first 12) | host | since (UTC) |\n| --- | --- | --- | --- |\n"
        "| engine | `ac6172b9ffb2` | zcrypto | 2026-09-04 |\n"
    )
    assert pins.unconverged_pins(path, pins.converged_digests(log)) == []


def test_a_table_with_no_digest_column_exits_2_rather_than_counting_zero(tmp_path):
    """The silent failure: a hand edit taking every row out of the count."""
    log = _log(tmp_path, [{"ts": "x", "rc": 0}])
    path = tmp_path / "fleet-pins.md"
    path.write_text("# pins\n\n| service | host | since |\n| --- | --- | --- |\n| engine | zcrypto | 2026 |\n")
    with pytest.raises(SystemExit) as raised:
        pins.unconverged_pins(path, pins.converged_digests(log))
    assert raised.value.code == 2


def test_a_version_pin_is_not_in_the_set(tmp_path):
    """A version pin carries no digest, so counting it would report an owed converge that cannot exist."""
    log = _log(tmp_path, [{"ts": "x", "rc": 0}])
    p = _pins(tmp_path, ["| agentboard | zcrypto-ops | `0.4.23` (npm global) | 2026-08-26 | — |\n"])
    assert pins.unconverged_pins(p, pins.converged_digests(log)) == []


def test_the_var_name_is_never_matched_on(tmp_path):
    """The join is on the digest, so a digest under an unexpected key still counts as converged."""
    log = _log(tmp_path, [{"ts": "x", "rc": 0, "extra_vars": {"some_future_role_digest": "06998998e876"}}])
    p = _pins(tmp_path, ["| capture | zcrypto | `06998998e876` | 2026-09-07 | `ac61` |\n"])
    assert pins.unconverged_pins(p, pins.converged_digests(log)) == []


def test_a_log_that_is_not_jsonl_exits_2_rather_than_counting_zero(tmp_path):
    log = tmp_path / "deploy-log.jsonl"
    log.write_text('{"ts": "x"}\nnot json\n')
    with pytest.raises(SystemExit) as raised:
        pins.converged_digests(log)
    assert raised.value.code == 2


def test_the_real_pair_reads_zero():
    """The repo's own files, which is what the count-list entry runs."""
    root = pathlib.Path(__file__).resolve().parents[1]
    seen = pins.converged_digests(root / "docs/reference/deploy-log.jsonl")
    assert pins.unconverged_pins(root / "docs/reference/fleet-pins.md", seen) == []
