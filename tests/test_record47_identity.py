from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cli.engine.cycle import _expand_to_basket, select_model_inputs
from cli.engine.store import BASKET, PAIR_KEYS, read_store_series
from cli.portfolio.crossfreq_system import build_crossfreq_system_fast
from cli.registry import TrialRegistry
from cli.registry.observed import ObservedReader
from cli.research import subjects

pytestmark = pytest.mark.data

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _REPO_ROOT / "data"
_CANONICAL = _DATA_ROOT / "ohlc-full"
_REGISTRY = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"

_RECORD_47 = 47
_DAILY_STAMPS = 4_582
_H4_STAMPS = 27_338
_NET_BARS = 27_337
_CAP_BREACH_BARS = 1318
_GOVERNOR_ENGAGED_BARS = 7302


def _rows(final_targets: dict[str, list[float]]) -> list[dict[str, float]]:
    return [dict(zip(final_targets, values, strict=True)) for values in zip(*final_targets.values(), strict=True)]


@pytest.mark.skipif(not _CANONICAL.is_dir(), reason="data/ohlc-full absent — record 47's identity runs on the data host only")
def test_the_twelve_leg_engine_path_is_record44_crossfreqs_book_on_the_ten_eur_legs():
    digests = {
        f"{symbol}/{interval}.parquet": hashlib.sha256((_CANONICAL / symbol / f"{interval}.parquet").read_bytes()).hexdigest()
        for symbol in PAIR_KEYS
        for interval in (1440, 240)
    }
    record47 = {r.trial_id: r for r in TrialRegistry(_REGISTRY).records}[_RECORD_47]
    assert digests == record47.datasets["ohlc-full"]["files"]
    assert subjects._RECORD44_CONFIG.cost_per_side == 0.006

    raw = {(symbol, interval): read_store_series(_CANONICAL, symbol, interval) for symbol in PAIR_KEYS for interval in (1440, 240)}
    daily_ts, daily_prices = select_model_inputs({symbol: raw[(symbol, 1440)] for symbol in PAIR_KEYS})
    h4_ts, h4_prices = select_model_inputs({symbol: raw[(symbol, 240)] for symbol in PAIR_KEYS})
    engine = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=subjects._RECORD44_CONFIG)
    engine_rows = [_expand_to_basket(row) for row in _rows(engine.final_targets)]

    book_daily_ts, book_daily_prices, book_h4_ts, book_h4_prices, book = subjects._crossfreq_book(
        ObservedReader(_DATA_ROOT), "ohlc-full", None
    )
    book_rows = _rows(book.final_targets)

    lengths = (_DAILY_STAMPS, _H4_STAMPS, _H4_STAMPS, _NET_BARS, _NET_BARS)
    assert (len(daily_ts), len(h4_ts), len(engine_rows), len(engine.governed_net), len(engine.ungoverned_net)) == lengths
    assert (len(book_daily_ts), len(book_h4_ts), len(book_rows), len(book.governed_net), len(book.ungoverned_net)) == lengths

    assert book_daily_ts == daily_ts
    assert book_h4_ts == h4_ts
    assert book_daily_prices == daily_prices
    assert book_h4_prices == h4_prices
    assert book.governed_net == engine.governed_net
    assert book.ungoverned_net == engine.ungoverned_net
    btc_legs = [symbol for symbol in BASKET if symbol.endswith("/BTC")]
    for k, (row, book_row) in enumerate(zip(engine_rows, book_rows, strict=True)):
        assert {s: w for s, w in row.items() if s.endswith("/EUR")} == {f"{base}/EUR": w for base, w in book_row.items()}, k
        assert {s: row[s] for s in btc_legs} == dict.fromkeys(btc_legs, 0.0), k
    assert (engine.cap_breach_bars, engine.governor_engaged_bars) == (_CAP_BREACH_BARS, _GOVERNOR_ENGAGED_BARS)
    assert (book.cap_breach_bars, book.governor_engaged_bars) == (_CAP_BREACH_BARS, _GOVERNOR_ENGAGED_BARS)
