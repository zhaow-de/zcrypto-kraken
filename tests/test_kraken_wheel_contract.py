"""The pinned wheel's Kraken spot client, driven for real against a loopback venue.

The red button, the window reads and the engine's startup read all rest on what the real client does
with Kraken's two pair spellings, and `test_engine_flatten.py`'s FakeClient restates that contract
without checking it: the altname index lives on the client instance, recorded by its own
`request_instruments`. Each test pins one clause on the installed wheel, so the bump that changes
it goes red here before it reaches the venue. Nothing here leaves 127.0.0.1.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from nautilus_trader.model import (
    AccountId,
    AccountType,
    ClientOrderId,
    InstrumentId,
    OrderSide,
    OrderType,
    Price,
    Quantity,
    TimeInForce,
)

from cli.engine import flatten
from tests import kraken_loopback

ACCOUNT = AccountId(flatten.ACCOUNT_ID)
BTC = InstrumentId.from_str("BTC/EUR.KRAKEN")
SOL = InstrumentId.from_str("SOL/EUR.KRAKEN")
BTC_TXID = "OBTCAA-BBBBB-CCCCC1"
SOL_TXID = "OSOLAA-BBBBB-CCCCC2"


@pytest.fixture
def venue():
    with kraken_loopback.serve() as served:
        served.open_orders = {
            BTC_TXID: kraken_loopback.open_order("XBTEUR", price="20000.0", volume="0.00010000"),
            SOL_TXID: kraken_loopback.open_order("SOLEUR", price="50.00", volume="0.06000000"),
        }
        yield served


async def _primed(venue):
    """A client after the red button's own first read, `flatten.read_listing`."""
    client = kraken_loopback.client(venue)
    await flatten.read_listing(client, flatten.Recorder())
    return client


async def _margin_positions(client):
    return await client.request_position_status_reports(
        ACCOUNT, account_type=AccountType.MARGIN, use_spot_position_reports=False, quote_currency=flatten.QUOTE_CURRENCY
    )


@pytest.mark.parametrize("pair", ["XBTEUR", "SOLEUR"])
def test_a_bare_client_s_unscoped_order_read_raises_on_an_order_it_cannot_place(venue, pair):
    """Both spellings: before the listing is cached, no pair resolves, the same-key one included."""
    venue.open_orders = {BTC_TXID: kraken_loopback.open_order(pair, price="1.0", volume="0.06000000")}

    async def run():
        await kraken_loopback.client(venue).request_order_status_reports(ACCOUNT, open_only=True)

    with pytest.raises(RuntimeError, match=f"OpenOrders: instrument not in cache for pair {pair}$"):
        asyncio.run(run())


def test_a_bare_client_s_position_read_raises_on_a_position_it_cannot_place(venue):
    venue.positions = {"TPOSAA-BBBBB-CCCCC1": kraken_loopback.margin_position("XBTEUR", volume="0.06000000")}

    async def run():
        await _margin_positions(kraken_loopback.client(venue))

    with pytest.raises(RuntimeError, match="OpenPositions: instrument not in cache for pair XBTEUR$"):
        asyncio.run(run())


def test_an_open_order_on_a_pair_the_listing_lacks_fails_the_whole_read(venue):
    """Not a dropped row: the read that would have reported the SOL/EUR order raises instead."""
    venue.open_orders["OETHAA-BBBBB-CCCCC3"] = kraken_loopback.open_order("ETHEUR", price="1000.0", volume="0.01000000")

    async def run():
        client = await _primed(venue)
        await client.request_order_status_reports(ACCOUNT, open_only=True)

    with pytest.raises(RuntimeError, match="OpenOrders: instrument not in cache for pair ETHEUR$"):
        asyncio.run(run())


def test_a_closed_order_on_a_pair_the_listing_lacks_drops_out_of_a_read_that_succeeds(venue):
    """The closed half, which the engine's startup read (`read_venue_orders`) rests on: a wheel that
    fails this read instead refuses every plan after each restart with such an order in the lookback."""
    closed_txid, unlisted_txid = "OBTCCL-BBBBB-CCCCC4", "OETHCL-BBBBB-CCCCC5"
    venue.closed_orders[closed_txid] = kraken_loopback.closed_order("XBTEUR", price="21000.0", volume="0.00010000")
    venue.closed_orders[unlisted_txid] = kraken_loopback.closed_order("ETHEUR", price="1000.0", volume="0.01000000")

    async def run():
        client = await _primed(venue)
        return await client.request_order_status_reports(ACCOUNT, open_only=False)

    assert sorted(str(r.venue_order_id) for r in asyncio.run(run())) == sorted([BTC_TXID, SOL_TXID, closed_txid])


@pytest.mark.parametrize("open_only", [True, False])
def test_after_the_listing_is_cached_an_order_resolves_under_either_spelling(venue, open_only):
    """open_only=True is startup reconciliation's read and flatten's; open_only=False is the engine's
    single-report read, which also pages ClosedOrders, where the history is spelled the same way."""
    closed_txid = "OBTCCL-BBBBB-CCCCC4"
    venue.closed_orders = {closed_txid: kraken_loopback.closed_order("XBTEUR", price="21000.0", volume="0.00010000")}
    expected = {BTC_TXID: BTC, SOL_TXID: SOL} | ({} if open_only else {closed_txid: BTC})

    async def run():
        client = await _primed(venue)
        return await client.request_order_status_reports(ACCOUNT, open_only=open_only)

    reports = asyncio.run(run())
    assert {str(r.venue_order_id): r.instrument_id for r in reports} == expected


@pytest.mark.parametrize("pair", ["XBTEUR", "XXBTZEUR"])
def test_after_the_listing_is_cached_a_margin_position_resolves_under_either_spelling(venue, pair):
    venue.positions = {"TPOSAA-BBBBB-CCCCC1": kraken_loopback.margin_position(pair, volume="0.06000000")}

    async def run():
        return await _margin_positions(await _primed(venue))

    reports = asyncio.run(run())
    assert [(r.instrument_id, str(r.position_side), str(r.quantity)) for r in reports] == [(BTC, "LONG", "0.06000000")]


def test_a_scoped_read_skips_the_two_way_spelled_leg_before_resolving_it(venue):
    """Upstream #5067, pinned so the bump that fixes it goes red here: the scoped BTC/EUR read then
    reports its order, and the window reads' scoped contrast line stops reading 0 on BTC/EUR. SOL/EUR,
    whose key and altname agree, is the control that the scoped read works at all."""

    async def run():
        client = await _primed(venue)
        return [
            [str(r.venue_order_id) for r in await client.request_order_status_reports(ACCOUNT, instrument_id=iid, open_only=True)]
            for iid in (BTC, SOL)
        ]

    assert asyncio.run(run()) == [[], [SOL_TXID]]


def test_an_order_report_carries_no_client_order_id(venue):
    """The venue's row carries `cl_ord_id`, and the adapter drops it: a reader matches our orders by
    venue order id, never by the id we sent."""
    venue.open_orders[BTC_TXID] = kraken_loopback.open_order(
        "XBTEUR", price="20000.0", volume="0.00010000", cl_ord_id="FLT260923120000-1"
    )
    assert venue.open_orders[BTC_TXID]["cl_ord_id"] == "FLT260923120000-1"

    async def run():
        client = await _primed(venue)
        return await client.request_order_status_reports(ACCOUNT, open_only=True)

    assert {str(r.venue_order_id): r.client_order_id for r in asyncio.run(run())} == {BTC_TXID: None, SOL_TXID: None}


def _fees(venue) -> dict[str, tuple[Decimal, Decimal]]:
    async def run():
        rows = await kraken_loopback.client(venue).request_instruments()
        return {str(row.id): (row.maker_fee, row.taker_fee) for row in rows}

    return asyncio.run(run())


def _public_fees(venue) -> dict[str, tuple[Decimal, Decimal]]:
    """The first rung of each AssetPairs row's own ladders, in percent there and a fraction on the instrument."""
    wsname = {"XXBTZEUR": "BTC/EUR.KRAKEN", "SOLEUR": "SOL/EUR.KRAKEN"}
    return {
        wsname[key]: (Decimal(str(row["fees_maker"][0][1])) / 100, Decimal(str(row["fees"][0][1])) / 100)
        for key, row in venue.asset_pairs.items()
    }


def test_the_listing_takes_the_account_s_fee_tier_from_trade_volume(venue):
    account_tier = (Decimal(venue.maker_fee_pct) / 100, Decimal(venue.taker_fee_pct) / 100)
    assert account_tier not in _public_fees(venue).values()
    assert _fees(venue) == {"BTC/EUR.KRAKEN": account_tier, "SOL/EUR.KRAKEN": account_tier}


@pytest.mark.parametrize(
    "fault",
    [
        pytest.param({"errors": {"TradeVolume": "EGeneral:Permission denied"}}, id="trade-volume-errors"),
        pytest.param({"trade_volume_answer": {"currency": "ZUSD"}}, id="trade-volume-answer-does-not-parse"),
    ],
)
def test_a_trade_volume_failure_still_yields_the_listing_on_public_fees(venue, fault):
    for name, value in fault.items():
        setattr(venue, name, value)
    assert _fees(venue) == _public_fees(venue)
    assert "TradeVolume" in venue.private_calls


def test_a_trade_volume_answer_missing_a_pair_s_fee_fails_the_whole_listing(venue):
    """The one fee failure that is fatal, and on the red button's first read it is exit 3."""
    venue.trade_volume_omits = {"XXBTZEUR"}
    with pytest.raises(RuntimeError, match="TradeVolume response missing taker fee for XXBTZEUR$"):
        _fees(venue)


@pytest.mark.parametrize(
    ("sent", "on_the_wire"),
    [
        ("FLT260923120000-1", "FLT260923120000-1"),
        ("FLT260923120000-12", "FLT260923120000-12"),
        ("FLT260923120000-123", "OT260923120000-123"),
        ("FIXMINT-spot-20260923T190000Z", "O-20260923T190000Z"),
        ("O-20260823-120000-001-000-1", "O-120000-001-000-1"),
        # The 32-hex shape is Kraken's short UUID and passes whole.
        ("0123456789abcdef0123456789abcdef", "0123456789abcdef0123456789abcdef"),
    ],
)
def test_a_client_order_id_goes_out_verbatim_up_to_18_characters_and_as_o_plus_its_last_17_beyond(venue, sent, on_the_wire):
    async def run():
        client = await _primed(venue)
        await client.submit_order(
            account_id=ACCOUNT,
            instrument_id=SOL,
            client_order_id=ClientOrderId(sent),
            order_side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Quantity.from_str("0.06"),
            time_in_force=TimeInForce.GTC,
            price=Price.from_str("25.00"),
        )

    asyncio.run(run())
    assert [body.get("cl_ord_id") for body in venue.add_orders] == [on_the_wire]
