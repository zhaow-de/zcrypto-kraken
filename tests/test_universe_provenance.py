"""The universe artifact's provenance hash, pinned to a RUNNABLE recipe (T0065).

`docs/universe/point-in-time-universe.md` cites a `basket sha256` for the OHLC inputs the committed
universe was selected from. Until 2026-08-08 that number's derivation existed only as the doc's own
prose -- exactly the class of gap T0065 names: a hash recipe that is not reproducible from committed
code is provenance in appearance only.

This test makes it executable, and it pins TWO documents against each other: the hash in the universe
doc and the per-series table in the data catalog. Either drifting alone turns this red, which is the
point -- the artifact and the table that explains it cannot silently disagree.

Deliberately NOT parameterised over the live tree: `data/ohlc` (the v0 REST seed) was retired
2026-07-18 and is gone from disk and from the NAS, so the catalog table is now the ONLY surviving
record of what those twelve series hashed to. That is also why this recipe was worth recovering
rather than re-deriving -- there is nothing left to re-derive it from.
"""

import hashlib
import json
import re
from pathlib import Path

_DOCS = Path(__file__).resolve().parent.parent / "docs"
_CATALOG = _DOCS / "reference" / "data-catalog.md"
_UNIVERSE = _DOCS / "universe" / "point-in-time-universe.md"

# The recipe the universe doc states in prose: sha256 over the sorted {symbol: dataset_hash} map for
# the twelve daily series used for the volume signal. `json.dumps(..., sort_keys=True)` with DEFAULT
# separators -- the compact form does NOT reproduce it, so the separators are load-bearing.
_ROW = re.compile(r"\|\s*(\S+)\s*\|\s*\d+d?h?\s*\((\d+)\)\s*\|\s*\d+\s*\|[^|]*\|[^|]*\|\s*`([0-9a-f]{64})`")


def _v0_daily_map() -> dict[str, str]:
    rows = _ROW.findall(_CATALOG.read_text())
    return {symbol: digest for symbol, interval, digest in rows if interval == "1440"}


def test_the_universe_artifacts_basket_hash_reproduces_from_the_catalog():
    """The load-bearing one: the doc's cited hash must fall out of the catalog's own numbers."""
    stated = re.search(r"`([0-9a-f]{64})`", _UNIVERSE.read_text().split("basket sha256")[1])
    assert stated, "the universe doc no longer states a basket sha256 after that phrase"

    daily = _v0_daily_map()
    assert len(daily) == 12, f"expected the twelve volume-signal series, found {len(daily)}"
    # Full display symbols, quote included -- base-only keys collapse ETH/BTC onto ETH and change the
    # digest, so this is not a cosmetic choice.
    assert "ETH/BTC" in daily and "BTC/EUR" in daily

    computed = hashlib.sha256(json.dumps(daily, sort_keys=True).encode()).hexdigest()
    assert computed == stated.group(1), (
        f"the universe artifact's basket sha256 no longer reproduces from the catalog table: "
        f"doc says {stated.group(1)[:12]}, catalog yields {computed[:12]}"
    )


def test_the_compact_json_form_does_not_reproduce_it():
    """Pins the separator choice by showing the near-miss, so a future tidy-up to the compact form
    fails here with an explanation rather than silently changing what the provenance hash means."""
    daily = _v0_daily_map()
    default = hashlib.sha256(json.dumps(daily, sort_keys=True).encode()).hexdigest()
    compact = hashlib.sha256(json.dumps(daily, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert default != compact
