import json
from pathlib import Path

from cli.ohlc.ingest import ingest_basket

_FIXTURES = Path(__file__).parent / "fixtures"
ROWS = json.loads((_FIXTURES / "kraken_ohlc_xxbtzeur_1440.json").read_text())["result"]["XXBTZEUR"]
FETCHED_AT = "2026-07-07T00:00:00+00:00"


def _fetch_fn(pair_key, interval):
    return ROWS


def test_ingest_basket_writes_tree_and_returns_manifest(tmp_path):
    pair_keys = {"BTC/EUR": "XXBTZEUR", "ETH/EUR": "XETHZEUR"}
    intervals = [1440, 60]

    manifest = ingest_basket(pair_keys, intervals, tmp_path, FETCHED_AT, fetch_fn=_fetch_fn)

    assert manifest["fetched_at"] == FETCHED_AT
    assert len(manifest["series"]) == 4
    for symbol in pair_keys:
        for interval in intervals:
            assert (tmp_path / symbol / f"{interval}.parquet").exists()

    entry = next(s for s in manifest["series"] if s["symbol"] == "BTC/EUR" and s["interval"] == 1440)
    assert entry["rows"] == len(ROWS)
    assert entry["first_ts"] == "2024-07-17T00:00:00+00:00"
    assert entry["last_ts"] == "2024-07-22T00:00:00+00:00"
    assert len(entry["dataset_hash"]) == 64


def test_ingest_basket_deterministic_given_fixed_fetched_at(tmp_path_factory):
    pair_keys = {"BTC/EUR": "XXBTZEUR"}
    intervals = [1440]

    manifest_a = ingest_basket(pair_keys, intervals, tmp_path_factory.mktemp("a"), FETCHED_AT, fetch_fn=_fetch_fn)
    manifest_b = ingest_basket(pair_keys, intervals, tmp_path_factory.mktemp("b"), FETCHED_AT, fetch_fn=_fetch_fn)

    assert manifest_a == manifest_b
