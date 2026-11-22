from __future__ import annotations

import math
import random
import statistics
import urllib.error
from collections.abc import Callable
from datetime import date, timedelta
from urllib.parse import urlsplit

import polars as pl
import pytest

from cli.onchain.brk import BITVIEW_URL, BrkClient, BrkError
from cli.onchain.series import BRK_SERIES, COLUMNS, SCHEMA, mvrv_z, sth_supply_share
from tests.onchain_stub import Answer, FakeBrk, fake_client

D0 = date(2024, 3, 1)


def _caps(n: int) -> tuple[list[float | None], list[float | None]]:
    rng = random.Random(42)
    market = [rng.uniform(1e9, 1e12) for _ in range(n)]
    return market, [cap * rng.uniform(0.3, 0.9) for cap in market]


def test_every_column_has_its_dtype_and_every_brk_column_its_id():
    assert COLUMNS == (
        "ts",
        "last_height",
        "last_hash",
        "price",
        "supply",
        "market_cap",
        "realized_cap",
        "mvrv",
        "nupl",
        "sopr",
        "asopr",
        "sth_sopr",
        "sth_asopr",
        "lth_sopr",
        "sth_supply",
        "lth_supply",
        "sth_mvrv",
        "lth_mvrv",
        "sth_nupl",
        "lth_nupl",
        "mvrv_z",
        "sth_supply_share",
    )
    assert tuple(SCHEMA) == COLUMNS
    assert (SCHEMA["ts"], SCHEMA["last_height"], SCHEMA["last_hash"]) == (pl.Datetime("us", "UTC"), pl.Int64, pl.String)
    assert {column: SCHEMA[column] for column in COLUMNS[3:]} == {column: pl.Float64 for column in COLUMNS[3:]}
    assert BRK_SERIES == {
        "price": "price",
        "supply": "circulating_supply",
        "market_cap": "market_cap",
        "realized_cap": "realized_cap",
        "mvrv": "mvrv",
        "nupl": "nupl",
        "sopr": "sopr_24h",
        "asopr": "adjusted_sopr_24h",
        "sth_sopr": "sth_sopr_24h",
        "sth_asopr": "sth_adjusted_sopr_24h",
        "lth_sopr": "lth_sopr_24h",
        "sth_supply": "sth_supply",
        "lth_supply": "lth_supply",
        "sth_mvrv": "sth_mvrv",
        "lth_mvrv": "lth_mvrv",
        "sth_nupl": "sth_nupl",
        "lth_nupl": "lth_nupl",
    }
    ours = {"ts", "last_height", "last_hash", "mvrv_z", "sth_supply_share"}
    assert tuple(BRK_SERIES) == tuple(column for column in COLUMNS if column not in ours)


def test_mvrv_z_is_the_expanding_sample_std_and_null_before_365():
    market, realized = _caps(400)
    z = mvrv_z(market, realized)
    assert len(z) == 400
    assert z[:364] == [None] * 364
    assert z[364] == (market[364] - realized[364]) / statistics.stdev(market[:365])
    assert z[399] == (market[399] - realized[399]) / statistics.stdev(market[:400])


def test_mvrv_z_never_reads_a_later_day():
    market, realized = _caps(400)
    later = [cap * 10 if index > 379 else cap for index, cap in enumerate(market)]
    z = mvrv_z(market, realized)
    assert z[379] is not None
    assert mvrv_z(later, realized)[:380] == z[:380]


def test_mvrv_z_skips_a_missing_market_cap_in_its_count():
    market, realized = _caps(400)
    market[10], market[11], market[12] = None, 0.0, math.nan
    z = mvrv_z(market, realized)
    assert (z[10], z[11], z[12]) == (None, None, None)
    assert z[366] is None
    counted = market[:10] + market[13:368]
    assert len(counted) == 365
    assert z[367] == (market[367] - realized[367]) / statistics.stdev(counted)


def test_mvrv_z_is_none_where_the_realized_cap_is_not_finite():
    market, realized = _caps(400)
    realized[380], realized[381] = math.nan, None
    z = mvrv_z(market, realized)
    assert (z[380], z[381]) == (None, None)
    assert z[379] is not None and z[382] is not None


def test_the_sth_share():
    shares = sth_supply_share([1.0, None, 3.0, 1.0, 1.0, math.nan], [4.0, 5.0, None, 0.0, math.nan, 2.0])
    assert shares == [0.25, None, None, None, None, None]


def test_the_client_reads_a_series_by_day():
    days = [D0 + timedelta(days=offset) for offset in range(-1, 4)]
    fake = FakeBrk(series={"realized_cap": dict(zip(days, [4.4e11, 4.5e11, None, 4.6e11, 4.7e11], strict=True))})
    read = fake_client(fake).read_days("realized_cap", days[1], days[3])
    assert read == {days[1]: 4.5e11, days[2]: None, days[3]: 4.6e11}


def test_the_series_list_is_read_over_every_page():
    pinned = BRK_SERIES["sth_asopr"]
    ids = [f"series_{index:04d}" for index in range(2499)] + [pinned]
    got = fake_client(FakeBrk(ids=ids)).series_ids()
    assert len(got) == 2500 and got == frozenset(ids) and pinned in got


def test_the_height_reads_page_under_brks_weight_cap():
    days = [date(2009, 1, 3) + timedelta(days=height // 144) for height in range(200_000)]
    client = fake_client(FakeBrk(days=days))
    with pytest.raises(urllib.error.HTTPError) as refused:
        client.opener.open(f"{BITVIEW_URL}/api/series/block_day1/height?start=0&end=160001")
    assert refused.value.code == 400
    assert client.height_days(0, 199_999) == days


def test_the_indexed_height_and_the_tip_are_the_sync_routes():
    fake = FakeBrk(indexed_height=870_000, tip_height=870_012)
    client = fake_client(fake)
    assert (client.indexed_height(), client.node_tip()) == (870_000, 870_012)
    assert [urlsplit(url).path for url in fake.seen] == ["/api/server/sync", "/api/server/sync"]


def _plant(path: str, answer: Answer) -> Callable[[FakeBrk], None]:
    def plant(fake: FakeBrk) -> None:
        fake.planted[path] = answer

    return plant


def _unreachable(fake: FakeBrk) -> None:
    fake.unreachable = True


def _nothing(fake: FakeBrk) -> None:
    pass


@pytest.mark.parametrize(
    ("setup", "call", "route"),
    [
        (_nothing, lambda client: client.block_hash(5), "/api/block-height/5"),
        (_plant("/api/server/sync", Answer(503, b"")), lambda client: client.indexed_height(), "/api/server/sync"),
        (_plant("/api/server/sync", Answer(504, b"")), lambda client: client.node_tip(), "/api/server/sync"),
        (_plant("/api/server/sync", Answer(204, b"")), lambda client: client.node_tip(), "/api/server/sync"),
        (_unreachable, lambda client: client.series_ids(), "/api/series/list"),
        (
            _plant("/api/series/price/day1", Answer(200, b"<html>")),
            lambda client: client.read_days("price", D0, D0),
            "/api/series/price/day1",
        ),
        (_plant("/api/server/sync", Answer(200, b'{"tip_height": 5}')), lambda client: client.indexed_height(), "/api/server/sync"),
        (
            _plant("/api/series/block_day1/height", Answer(200, b'{"start": 0, "data": [5478]}')),
            lambda client: client.height_days(0, 1),
            "/api/series/block_day1/height",
        ),
        (
            _plant("/api/block-height/0", Answer(200, b"not a hash", "text/plain")),
            lambda client: client.block_hash(0),
            "/api/block-height/0",
        ),
    ],
    ids=["404", "503", "504", "204", "unreachable", "unparseable", "missing-key", "short-page", "not-a-hash"],
)
def test_a_non_200_or_unparseable_answer_is_a_brk_error_naming_its_route(setup, call, route):
    fake = FakeBrk(days=[D0], series={"price": {D0: 1.0}})
    setup(fake)
    with pytest.raises(BrkError) as caught:
        call(fake_client(fake))
    assert route in str(caught.value)


_DRIVES: dict[str, Callable[[BrkClient], object]] = {
    "series_ids": lambda client: client.series_ids(),
    "read_days": lambda client: client.read_days("price", D0, D0),
    "height_days": lambda client: client.height_days(0, 1),
    "block_hash": lambda client: client.block_hash(0),
    "indexed_height": lambda client: client.indexed_height(),
    "node_tip": lambda client: client.node_tip(),
}


def test_no_url_the_module_builds_names_a_kraken_host():
    methods = {name for name, member in vars(BrkClient).items() if callable(member) and not name.startswith("_")}
    assert set(_DRIVES) == methods
    host = urlsplit(BITVIEW_URL).hostname
    assert "kraken" not in BITVIEW_URL.lower()
    for name, drive in _DRIVES.items():
        fake = FakeBrk(days=[D0, D0], series={"price": {D0: 1.0}}, indexed_height=1, tip_height=1)
        drive(fake_client(fake))
        assert fake.seen, name
        for url in fake.seen:
            assert urlsplit(url).hostname == host and "kraken" not in url.lower(), url
