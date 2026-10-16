from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLOW_CASES = ROOT / "tests" / "slow-cases.txt"


def _listed() -> set[str]:
    return {line.strip() for line in SLOW_CASES.read_text().splitlines() if line.strip() and not line.startswith("#")}


def _collect(*args: str) -> set[str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "ZCRYPTO_RERUN_SLOW": "1"},  # the marks, not this branch's ledger of passed slow cases
    )
    assert done.returncode in (0, 5), done.stdout + done.stderr
    return {line for line in done.stdout.split("\n\n", 1)[0].splitlines() if "::" in line}


def _files(ids: set[str]) -> list[str]:
    return sorted({nodeid.split("::", 1)[0] for nodeid in ids})


def test_every_listed_case_is_collected():
    listed = _listed()
    stale = listed - _collect(*_files(listed))
    assert not stale, f"no longer collected -- regenerate the list as its header says, or drop the id: {sorted(stale)}"


def test_minus_m_slow_collects_exactly_the_listed_cases_a_non_data_run_holds():
    listed = _listed()
    expected = listed & _collect("-m", "not data", *_files(listed))
    assert _collect("-m", "slow and not data", "tests") == expected
