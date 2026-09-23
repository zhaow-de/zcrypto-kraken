"""The fixture mint's reads, driven through the real `KrakenSpotHttpClient` against the loopback venue.

`test_kraken_fixture_mint.py` drives the same reads through a stub that restates the adapter's
instrument cache; this module reads through the cache itself, so a wheel that changes what the mint's
cache step must do goes red here. Nothing here leaves 127.0.0.1.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from tests import kraken_loopback

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "kraken-fixture-mint.py"
# Its own module name, so this load and `test_kraken_fixture_mint.py`'s do not replace each other in
# `sys.modules`; registered before exec, because `@dataclass` resolves its module there.
_spec = importlib.util.spec_from_file_location("kraken_fixture_mint_loopback", _SCRIPT)
mint = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mint
_spec.loader.exec_module(mint)

PAIR = "SOL/EUR"


@pytest.fixture
def venue():
    """The three ingredients on the mint pair, and an order of the owner's on the pair spelled two ways."""
    with kraken_loopback.serve() as served:
        served.books = {
            "SOLEUR": kraken_loopback.depth(bids=[("85.76", "2.50000000"), ("85.70", "1.00000000")], asks=[("85.80", "3.00000000")])
        }
        served.open_orders = {
            "OSOLAA-BBBBB-CCCCC1": kraken_loopback.open_order("SOLEUR", price="47.16", volume="0.06000000"),
            "OBTCAA-BBBBB-CCCCC2": kraken_loopback.open_order("XBTEUR", price="20000.0", volume="0.00010000"),
        }
        served.positions = {"TPOSAA-BBBBB-CCCCC1": kraken_loopback.margin_position("SOLEUR", volume="0.06000000")}
        served.balances = {"ZEUR": kraken_loopback.balance("100.0000"), "SOL": kraken_loopback.balance("0.50000000")}
        yield served


def test_after_the_cache_step_each_read_returns_what_the_venue_holds(venue):
    async def run():
        client = kraken_loopback.client(venue)
        listing = await mint.read_listing(client)
        best_bid = await mint.read_pair(client, PAIR, listing)
        return best_bid, await mint.read_account(client, PAIR, mint.pair_limits(venue.asset_pairs, PAIR), best_bid)

    best_bid, held = asyncio.run(run())
    assert best_bid == 85.76
    assert sorted(held.resting_pairs) == ["BTC/EUR", "SOL/EUR"]
    assert held.position_pairs == ("SOL/EUR",)
    assert held.non_eur_assets == ("SOL",)


def test_without_the_cache_step_the_book_read_raises(venue):
    """The listing requested on the same client and never cached: the state the mint's first read
    reaches without `read_listing`'s cache loop."""

    async def run():
        client = kraken_loopback.client(venue)
        await mint.read_pair(client, PAIR, await client.request_instruments(pairs=None))

    blocker = "SOL/EUR's order book could not be read: Parse error: instrument not found in cache: SOL/EUR.KRAKEN"
    with pytest.raises(mint.Refusal, match=f"{re.escape(blocker)}$"):
        asyncio.run(run())


def test_the_dry_run_reads_the_minted_fixture_as_complete(venue, monkeypatch, capsys):
    """`_run`'s own order of reads: a read made before the cache step fails the run instead."""
    monkeypatch.setenv(mint.API_KEY_VAR, "not-a-real-key")
    monkeypatch.setenv(mint.API_SECRET_VAR, "not-a-real-secret")
    rc = asyncio.run(
        mint._run(
            argparse.Namespace(pair=PAIR, execute=False),
            client_factory=lambda _key, _secret: kraken_loopback.client(venue),
            listing_factory=lambda: venue.asset_pairs,
        )
    )
    assert rc == 0
    assert f"the fixture is complete for {PAIR}; nothing to mint" in capsys.readouterr().out
