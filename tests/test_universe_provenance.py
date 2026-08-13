"""The universe artifact's provenance hash, pinned to a RUNNABLE recipe (T0065).

`docs/universe/point-in-time-universe.md` cites a `basket sha256` for the OHLC inputs the committed
universe was selected from. Until 2026-08-08 that number's derivation existed only as the doc's own
prose -- exactly the class of gap T0065 names: a hash recipe that is not reproducible from committed
code is provenance in appearance only.

Originally this pinned the two documents directly against each other, on the assumption that the
committed universe is selected from the v0 catalog's series. That assumption held until 2026-08-13,
when spec `00093`'s attended sitting rebuilt the universe from a live-tailed `ohlc-reach-<stamp>`
sibling -- so the doc's hash legitimately stopped being the catalog's, and a single assertion tying
them together could only have stayed green by freezing the universe on a retired dataset. The pin is
therefore SPLIT into the two properties it was conflating (iter-137):

  * the catalog's own numbers still reproduce the v0 basket hash -- `data/ohlc` (the v0 REST seed)
    was retired 2026-07-18 and is gone from disk and from the NAS, so that table is the ONLY
    surviving record of what those twelve series hashed to. Nothing can re-derive it, which is why
    it is pinned against a literal rather than against another document that may legitimately move.
  * the universe doc's cited hash reproduces from the set its OWN provenance names, whichever set
    that is. This is the property that actually protects today's artifact, and it follows the doc
    wherever the source moves next.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"
_CATALOG = _DOCS / "reference" / "data-catalog.md"
_UNIVERSE = _DOCS / "universe" / "point-in-time-universe.md"

# The recipe the universe doc states in prose: sha256 over the sorted {symbol: dataset_hash} map for
# the twelve daily series used for the volume signal. `json.dumps(..., sort_keys=True)` with DEFAULT
# separators -- the compact form does NOT reproduce it, so the separators are load-bearing.
_ROW = re.compile(r"\|\s*(\S+)\s*\|\s*\d+d?h?\s*\((\d+)\)\s*\|\s*\d+\s*\|[^|]*\|[^|]*\|\s*`([0-9a-f]{64})`")

# What the catalog's twelve 1440 rows hashed to when the v0 set was retired. A literal, because the
# set it describes no longer exists anywhere to re-derive it from: this constant plus the table are
# jointly the whole record, and an edit to either without the other is the drift this catches.
_V0_BASKET_SHA256 = "407d2ed8222946111dc8301cf420a456d9a7ebbfc2835610f89a236ed23fd093"


def _v0_daily_map() -> dict[str, str]:
    rows = _ROW.findall(_CATALOG.read_text())
    return {symbol: digest for symbol, interval, digest in rows if interval == "1440"}


def test_the_v0_catalog_table_still_reproduces_its_own_basket_hash():
    """The irreplaceable half. `data/ohlc` is gone from disk and from the NAS, so if a future edit
    perturbs a digest, a symbol name, or the row shape this regex reads, the only surviving record of
    that dataset is silently wrong and nothing else in the repo would notice."""
    daily = _v0_daily_map()
    assert len(daily) == 12, f"expected the twelve volume-signal series, found {len(daily)}"
    # Full display symbols, quote included -- base-only keys collapse ETH/BTC onto ETH and change the
    # digest, so this is not a cosmetic choice.
    assert "ETH/BTC" in daily and "BTC/EUR" in daily

    computed = hashlib.sha256(json.dumps(daily, sort_keys=True).encode()).hexdigest()
    assert computed == _V0_BASKET_SHA256, (
        f"the v0 catalog table no longer reproduces its recorded basket sha256: "
        f"table yields {computed[:12]}, the retired set hashed to {_V0_BASKET_SHA256[:12]}"
    )


def test_the_universe_doc_cites_a_hash_that_reproduces_from_the_set_it_names():
    """The live half, and the one that follows the artifact. The doc names the OHLC set it was built
    from; that set's own manifest carries the basket hash. If the doc is regenerated against a new
    source but its cited hash is not updated in step -- or vice versa -- the artifact cites a basket
    it was not selected from, which is the T0065 failure in its newest costume."""
    text = _UNIVERSE.read_text()
    stated = re.search(r"`([0-9a-f]{64})`", text.split("basket sha256")[1])
    assert stated, "the universe doc no longer states a basket sha256 after that phrase"

    named = re.search(r"`data/(ohlc[\w.-]*)/", text)
    assert named, "the universe doc no longer names the OHLC set its volume signal read"
    manifest = _ROOT / "data" / named.group(1) / "manifest.json"
    if not manifest.exists():
        pytest.skip(f"{manifest} absent -- the set is gitignored and not present on this machine")

    basket = json.loads(manifest.read_text())["basket_sha256"]
    assert basket == stated.group(1), (
        f"the universe doc cites a basket sha256 the set it names does not carry: "
        f"doc says {stated.group(1)[:12]}, {named.group(1)}/manifest.json says {basket[:12]}"
    )


def test_the_compact_json_form_does_not_reproduce_it():
    """Pins the separator choice by showing the near-miss, so a future tidy-up to the compact form
    fails here with an explanation rather than silently changing what the provenance hash means."""
    daily = _v0_daily_map()
    default = hashlib.sha256(json.dumps(daily, sort_keys=True).encode()).hexdigest()
    compact = hashlib.sha256(json.dumps(daily, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert default != compact
