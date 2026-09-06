#!/usr/bin/env python3
"""CLI for the daily operations pass; the `/zcrypto-daily-ops` skill is the procedure and carries
both invocations with their exit codes."""

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
