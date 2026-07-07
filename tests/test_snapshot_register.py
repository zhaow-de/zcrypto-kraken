import json
from pathlib import Path

from cli.snapshot.register import build_snapshot, render_markdown

_FIXTURES = Path(__file__).parent / "fixtures"
ASSETPAIRS = json.loads((_FIXTURES / "kraken_assetpairs.json").read_text())
ASSETS = json.loads((_FIXTURES / "kraken_assets.json").read_text())
SYMBOLS = ["BTC/EUR", "DOGE/EUR", "1INCH/EUR"]
FETCHED_AT = "2026-07-07T00:00:00+00:00"


def test_build_snapshot_deterministic_given_fixed_fetched_at():
    a = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    b = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    assert a == b
    assert a["fetched_at"] == FETCHED_AT
    assert len(a["raw_sha256"]) == 64
    assert a["raw"] == {"assetpairs": ASSETPAIRS, "assets": ASSETS}


def test_build_snapshot_hash_changes_with_raw_input():
    a = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    mutated_assets = dict(ASSETS, XXBT=dict(ASSETS["XXBT"], status="disabled"))
    b = build_snapshot(ASSETPAIRS, mutated_assets, SYMBOLS, FETCHED_AT)
    assert a["raw_sha256"] != b["raw_sha256"]


def test_render_markdown_contains_basket_rows_and_provenance_hash():
    snapshot = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    md = render_markdown(snapshot)
    assert "BTC/EUR" in md
    assert "DOGE/EUR" in md
    assert snapshot["raw_sha256"] in md
    assert FETCHED_AT in md
    assert "XBT" in md and "XDG" in md  # alias ledger
