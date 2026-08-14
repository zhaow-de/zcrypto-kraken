import glob
import os
from pathlib import Path

import pytest

from cli.engine.feeders import load_minimums
from cli.engine.instruments import COSTMIN_EUR


def test_the_committed_costmin_matches_the_newest_refdata_snapshot():
    """costmin ships as a constant because the Kraken adapter never maps it (min_notional is
    always None) and the engine host carries no snapshot. This is its drift guard: a venue change
    turns this red instead of silently mis-sizing an order."""
    snaps = sorted(glob.glob("data/snapshots/kraken-refdata-*.json"), key=os.path.getmtime)
    if not snaps:
        pytest.skip("no refdata snapshot present (gitignored data root)")
    minimums, _ = load_minimums(Path(snaps[-1]))
    assert {b: c for b, (_, c) in minimums.items() if b in COSTMIN_EUR} == COSTMIN_EUR
