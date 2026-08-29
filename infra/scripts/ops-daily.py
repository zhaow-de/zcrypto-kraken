#!/usr/bin/env python3
"""CLI for the daily operations pass. The module beside it carries the reads and the classifier.

    uv run python infra/scripts/ops-daily.py report --since 24h [--journal-entry]
    uv run python infra/scripts/ops-daily.py classify --host <host> "<command>"

report exits 0 all-clear, 1 attention, 2 a source could not be read (the report names which).
classify exits 0 autonomous, 3 prepared.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE = Path(__file__).resolve().parent / "ops_daily.py"
_spec = importlib.util.spec_from_file_location("ops_daily", _MODULE)
ops_daily = importlib.util.module_from_spec(_spec)
sys.modules["ops_daily"] = ops_daily
_spec.loader.exec_module(ops_daily)

if __name__ == "__main__":
    raise SystemExit(ops_daily.main(sys.argv[1:]))
