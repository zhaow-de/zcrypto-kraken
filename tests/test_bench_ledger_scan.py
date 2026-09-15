"""`infra/scripts/bench-ledger-scan.py` times the reconcile ledger's scan at synthetic sizes. The synthetic ledger
is keyed as the writer keys the real one -- each (pair, kind, hour) once, hours advancing so the dedup set grows with
the file -- and each state carries the fields `_totals` reads on its branch. `--repeats` below 1 is refused before
any size runs; each size is measured in a child process that prints its four numbers; the table carries one row per
size, in the order given."""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "bench-ledger-scan.py"
_spec = importlib.util.spec_from_file_location("bench_ledger_scan", _SCRIPT)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

_MINT_FIELDS = {"claimed_seconds", "trades_added", "trades_secondary_deficit", "trades_deduped"}


class _Rng:
    """`random.Random` narrowed to one state, so a record's shape can be read per state."""

    def __init__(self, state: str) -> None:
        self.state = state

    def choice(self, seq):
        return self.state if seq is bench._STATES else seq[0]

    def uniform(self, a, b):
        return a

    def randint(self, a, b):
        return a


def test_every_pair_kind_hour_key_is_emitted_once_and_hours_advance():
    per_hour = bench._PAIRS * len(bench._KINDS)
    records = [bench._record(random.Random(1), n) for n in range(per_hour * 30)]
    keys = [(r["pair"], r["kind"], r["hour"]) for r in records]
    assert len(set(keys)) == len(keys)
    hours = [r["hour"] for r in records]
    assert hours == sorted(hours) and len(set(hours)) == 30
    assert {r["pair"] for r in records[:per_hour]} == {f"PAIR{i}" for i in range(bench._PAIRS)}
    assert {r["kind"] for r in records[:per_hour]} == set(bench._KINDS)
    assert all(r["ts"] == r["hour"] for r in records)


@pytest.mark.parametrize("state", bench._STATES)
def test_each_state_carries_the_fields_its_totals_branch_reads(state):
    rec = bench._record(_Rng(state), 0)
    assert rec["state"] == state and "residual_seconds" in rec
    assert (_MINT_FIELDS <= rec.keys()) == (state in ("minted", "would_mint", "trade_deficit"))
    assert bool(_MINT_FIELDS & rec.keys()) == (state in ("minted", "would_mint", "trade_deficit"))
    assert ("healed_seconds" in rec) == (state == "minted")
    assert ("verdict" in rec) == (state == "both_streams_silent")
    if state == "both_streams_silent":
        assert rec["verdict"] in bench._VERDICTS


def test_write_emits_one_json_record_per_line_and_returns_the_byte_size(tmp_path):
    size = bench._write(tmp_path, 7)
    path = tmp_path / "reconcile-ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 7 and size == path.stat().st_size
    assert all(isinstance(json.loads(line), dict) for line in lines)


def test_the_child_prints_best_load_best_totals_peak_and_the_count(tmp_path, capsys):
    bench._write(tmp_path, 5)
    bench._child(tmp_path, 2)
    fields = capsys.readouterr().out.split()
    assert len(fields) == 4 and fields[3] == "5"
    assert float(fields[0]) >= 0 and float(fields[1]) >= 0 and float(fields[2]) > 0


def test_repeats_below_one_is_refused_before_any_size_runs():
    done = subprocess.run([sys.executable, str(_SCRIPT), "--repeats", "0", "--sizes", "5"], capture_output=True, text=True)
    assert done.returncode == 2 and "--repeats must be >= 1" in done.stderr
    assert "records" not in done.stdout


def test_the_table_carries_one_row_per_size_in_order(tmp_path):
    done = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sizes", "48,24", "--repeats", "1"], capture_output=True, text=True, cwd=tmp_path
    )
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[0].split() == ["records", "MiB", "load", "s", "totals", "s", "total", "s", "%", "of", "cycle", "peak", "MiB"]
    rows = [line.split() for line in lines[1:3]]
    assert [row[0] for row in rows] == ["48", "24"]
    assert all(len(row) == 7 and row[5].endswith("%") for row in rows)
    assert "Memory binds first" in done.stdout
