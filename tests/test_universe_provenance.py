"""The universe artifact's provenance hash, pinned to a RUNNABLE recipe (T0065)."""

import hashlib
import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"
_CATALOG = _DOCS / "reference" / "data-catalog.md"
_UNIVERSE = _DOCS / "universe" / "point-in-time-universe.md"

# The recipe the universe doc states in prose: sha256 over the sorted {symbol: dataset_hash} map for the
# daily volume-signal series -- `json.dumps(..., sort_keys=True)` with DEFAULT separators, not compact ones.
_ROW = re.compile(r"\|\s*(\S+)\s*\|\s*\d+d?h?\s*\((\d+)\)\s*\|\s*\d+\s*\|[^|]*\|[^|]*\|\s*`([0-9a-f]{64})`")

# What the catalog's 1440 rows hashed to when the v0 set was retired. A literal, because the set it describes
# no longer exists anywhere to re-derive it from: this constant plus the table are jointly the whole record.
_V0_BASKET_SHA256 = "407d2ed8222946111dc8301cf420a456d9a7ebbfc2835610f89a236ed23fd093"


def _v0_daily_map() -> dict[str, str]:
    rows = _ROW.findall(_CATALOG.read_text())
    return {symbol: digest for symbol, interval, digest in rows if interval == "1440"}


def test_the_v0_catalog_table_still_reproduces_its_own_basket_hash():
    """The irreplaceable half: perturb a digest, a symbol name, or the row shape this regex reads and
    the only surviving record of the retired v0 set is silently wrong."""
    daily = _v0_daily_map()
    assert len(daily) == 12, f"expected the twelve volume-signal series, found {len(daily)}"
    # Full display symbols, quote included -- base-only keys collapse ETH/BTC onto ETH and change the digest.
    assert "ETH/BTC" in daily and "BTC/EUR" in daily

    computed = hashlib.sha256(json.dumps(daily, sort_keys=True).encode()).hexdigest()
    assert computed == _V0_BASKET_SHA256, (
        f"the v0 catalog table no longer reproduces its recorded basket sha256: "
        f"table yields {computed[:12]}, the retired set hashed to {_V0_BASKET_SHA256[:12]}"
    )


def test_the_universe_doc_cites_a_hash_that_reproduces_from_the_set_it_names():
    """The live half: if the doc is regenerated against a new source but its cited hash is not updated
    in step -- or vice versa -- the artifact cites a basket it was not selected from (T0065)."""
    text = _UNIVERSE.read_text()
    stated = re.search(r"`([0-9a-f]{64})`", text.split("basket sha256")[1])
    assert stated, "the universe doc no longer states a basket sha256 after that phrase"

    named = re.search(r"`data/(ohlc[\w.-]*)/", text)
    assert named, "the universe doc no longer names the OHLC set its volume signal read"
    manifest = _ROOT / "data" / named.group(1) / "manifest.json"
    if not manifest.exists():
        pytest.skip(f"{manifest} absent -- the set is gitignored and not present on this machine")

    # The set now DECLARES which digest identifies it (spec 00099): reach's identity is its continuous
    # subset, so reading one named key would be wrong for one of the two sets `resolve_ohlc_source` names.
    from cli.data.manifest import ManifestError, read_manifest

    try:
        basket = read_manifest(manifest).identity_digest
    except ManifestError:  # a tree fetched from the hub is still legacy until converted
        basket = json.loads(manifest.read_text())["basket_sha256"]
    assert basket == stated.group(1), (
        f"the universe doc cites a basket sha256 the set it names does not carry: "
        f"doc says {stated.group(1)[:12]}, {named.group(1)}/manifest.json says {basket[:12]}"
    )


def test_the_compact_json_form_does_not_reproduce_it():
    """Pins the separator choice by showing the near-miss: a tidy-up to the compact form would
    silently change what the provenance hash means."""
    daily = _v0_daily_map()
    default = hashlib.sha256(json.dumps(daily, sort_keys=True).encode()).hexdigest()
    compact = hashlib.sha256(json.dumps(daily, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert default != compact
