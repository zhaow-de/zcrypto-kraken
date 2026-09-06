import glob
import json
import os
from pathlib import Path

import pytest

from cli.engine.feeders import load_minimums
from cli.engine.instruments import COSTMIN

# The two /BTC legs: load_minimums's quote == "EUR" filter drops them by design, so they are read
# from the snapshot's `universe` block instead of through that reader.
_BTC_QUOTED_SYMBOLS = ("ETH/BTC", "SOL/BTC")


def test_the_committed_costmin_matches_the_newest_refdata_snapshot():
    """costmin ships as a constant because the Kraken adapter never maps it (min_notional is
    always None) and the engine host carries no snapshot. This is its drift guard: a venue change
    turns this red instead of silently mis-sizing an order."""
    snaps = sorted(glob.glob("data/snapshots/kraken-refdata-*.json"), key=os.path.getmtime)
    if not snaps:
        pytest.skip("no refdata snapshot present (gitignored data root)")
    snapshot_path = Path(snaps[-1])

    minimums, _ = load_minimums(snapshot_path)
    eur_costmin = {f"{base}/EUR": (costmin, "EUR") for base, (_, costmin) in minimums.items() if f"{base}/EUR" in COSTMIN}

    universe = json.loads(snapshot_path.read_text())["universe"]
    btc_costmin = {
        entry["symbol"]: (float(entry["costmin"]), entry["quote"]) for entry in universe if entry["symbol"] in _BTC_QUOTED_SYMBOLS
    }

    assert eur_costmin | btc_costmin == COSTMIN
