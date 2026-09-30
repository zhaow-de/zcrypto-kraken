"""A loopback Kraken REST venue for tests that drive the real `KrakenSpotHttpClient`.

It binds 127.0.0.1 only and answers from what a test puts on it, so a test that uses it reaches no
venue and takes no live-venue gate. It records what reached it, so a test can assert what went out
on the wire -- including that nothing did. A path it does not serve answers Kraken's
`EGeneral:Unknown method`, so a test that needs a new endpoint or answer shape adds it here, rather
than reading an empty success or serving Kraken's answers from a server of its own that a
correction to the shape would miss.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import websockets

# Bound here, not at call time: a test that replaces the adapter's attribute to refuse any client
# pointed at the real venue still gets the real class from `client()`.
from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

# Two AssetPairs rows as the venue published them: SOLEUR, whose key and altname agree, and
# XXBTZEUR, spelled XBTEUR on OpenOrders. `kraken_assetpairs.json` carries only the snapshot's
# fields, and the adapter refuses it whole (`missing field aclass_base`).
ASSET_PAIRS_FIXTURE = Path(__file__).parent / "fixtures" / "kraken_assetpairs_mint.json"

# Not a credential: the client signs every private request, and the loopback reads no signature.
API_KEY = "loopback-key"
API_SECRET = base64.b64encode(bytes(64)).decode()

# ClosedOrders' page size, as the adapter pages it.
_PAGE = 50


def open_order(pair: str, *, price: str, volume: str, side: str = "buy", cl_ord_id: str | None = None) -> dict[str, Any]:
    """One OpenOrders row, `pair` spelled as Kraken spells it there -- the altname (`XBTEUR`)."""
    row: dict[str, Any] = {
        "refid": None,
        "userref": 0,
        "status": "open",
        "opentm": 1758600000.0,
        "starttm": 0,
        "expiretm": 0,
        "descr": {
            "pair": pair,
            "type": side,
            "ordertype": "limit",
            "price": price,
            "price2": "0",
            "leverage": "none",
            "order": f"{side} {volume} {pair} @ limit {price}",
            "close": "",
        },
        "vol": volume,
        "vol_exec": "0.00000000",
        "cost": "0.00000",
        "fee": "0.00000",
        "price": "0.00000",
        "stopprice": "0.00000",
        "limitprice": "0.00000",
        "misc": "",
        "oflags": "fciq,post",
    }
    if cl_ord_id is not None:
        row["cl_ord_id"] = cl_ord_id
    return row


def closed_order(
    pair: str,
    *,
    price: str,
    volume: str,
    side: str = "buy",
    status: str = "canceled",
    vol_exec: str = "0.00000000",
    cl_ord_id: str | None = None,
) -> dict[str, Any]:
    """One ClosedOrders row: by default a limit order cancelled unfilled; `status="closed"` with
    `vol_exec` is one that filled."""
    row = open_order(pair, price=price, volume=volume, side=side, cl_ord_id=cl_ord_id)
    row.update(status=status, vol_exec=vol_exec, closetm=1758603600.0, reason="User requested" if status == "canceled" else None)
    return row


def depth(*, bids: Sequence[tuple[str, str]], asks: Sequence[tuple[str, str]] = ()) -> dict[str, Any]:
    """One Depth book, each `(price, volume)` level best first."""
    return {side: [[price, volume, 1758600000] for price, volume in levels] for side, levels in (("bids", bids), ("asks", asks))}


def balance(amount: str, *, hold: str = "0.00000000") -> dict[str, str]:
    """One BalanceEx row. The adapter reports `amount - hold` as free and drops a row whose amount is zero."""
    return {"balance": amount, "hold_trade": hold}


def margin_position(pair: str, *, volume: str, side: str = "buy") -> dict[str, Any]:
    """One OpenPositions row, `pair` spelled however the test needs it."""
    return {
        "ordertxid": "OQCLML-BW3P3-BUCMWZ",
        "posstatus": "open",
        "pair": pair,
        "time": 1758600000.0,
        "type": side,
        "ordertype": "market",
        "cost": "3.00000",
        "fee": "0.00480",
        "vol": volume,
        "vol_closed": "0.00000000",
        "margin": "1.50000",
        "value": "3.01",
        "net": "+0.01",
        "terms": "0.0100% per 4 hours",
        "rollovertm": "1758614400",
        "misc": "",
        "oflags": "",
    }


def trade_row(txid: str, pair: str, *, vol: str, price: str, trade_id: int, side: str = "buy") -> dict[str, Any]:
    """One TradesHistory row for a margin fill of `txid` -- `posstatus` open and a `postxid`; `pair`
    spelled as the AssetPairs key."""
    cost = f"{float(vol) * float(price):.5f}"
    return {
        "ordertxid": txid,
        "postxid": "TPOSLP-AAAAA-BBBBBB",
        "pair": pair,
        "time": 1758600000.0,
        "type": side,
        "ordertype": "limit",
        "price": price,
        "cost": cost,
        "fee": "0.00000",
        "vol": vol,
        "margin": f"{float(cost) / 2:.5f}",
        "leverage": "2",
        "misc": "",
        "trade_id": trade_id,
        "maker": True,
        "posstatus": "open",
    }


@dataclass
class KrakenLoopback:
    """What the venue holds, and what reached it. A test mutates the holdings between reads."""

    asset_pairs: dict[str, Any]
    # AssetPairs rows answered to `aclass_base=tokenized_asset`, which the adapter asks for beside the
    # currency listing. TradeVolume here carries no fee for them, which fails the whole listing: a
    # test serving them refuses TradeVolume through `errors`, and the listing takes public fees.
    tokenized_asset_pairs: dict[str, Any] = field(default_factory=dict)
    open_orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    closed_orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # TradesHistory rows by trade id, paged by `ofs` as the adapter pages them; a fill the private
    # WebSocket never delivered is booked from here at startup reconciliation.
    trades: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Called with the AddOrder form and its txid before the answer is sent.
    on_add_order: Callable[[dict[str, str], str], None] | None = None
    # Called with the CancelOrder form before the answer is sent.
    on_cancel_order: Callable[[dict[str, str]], None] | None = None
    # Depth books by the pair a request names, which the adapter spells as the AssetPairs key. A pair
    # with no book answers `EQuery:Unknown asset pair`, never an empty book.
    books: dict[str, dict[str, Any]] = field(default_factory=dict)
    # BalanceEx rows by the venue's own asset code (`ZEUR`, `SOL`).
    balances: dict[str, dict[str, str]] = field(default_factory=dict)
    # Endpoint name -> the Kraken error string it answers with instead of a result.
    errors: dict[str, str] = field(default_factory=dict)
    # Endpoint name -> seconds its answer waits, for a caller's own bound to fire first.
    stalls: dict[str, float] = field(default_factory=dict)
    # AssetPairs keys TradeVolume leaves out of an otherwise well-formed answer.
    trade_volume_omits: set[str] = field(default_factory=set)
    # A TradeVolume result served verbatim in place of the well-formed one.
    trade_volume_answer: dict[str, Any] | None = None
    # The account's own tier, in percent as TradeVolume states it.
    taker_fee_pct: str = "0.2600"
    maker_fee_pct: str = "0.1600"
    private_calls: list[str] = field(default_factory=list)
    add_orders: list[dict[str, str]] = field(default_factory=list)
    closed_order_forms: list[dict[str, str]] = field(default_factory=list)
    cancel_forms: list[dict[str, str]] = field(default_factory=list)
    # The `count` CancelOrder answers: 1 as Kraken answers a cancel it executed, 0 the other answer a
    # test serves, since which one Kraken gives for a txid already closed is unmeasured.
    cancel_count: int = 1
    base_url: str = ""

    def answer(self, method: str, path: str, query: dict[str, list[str]], form: dict[str, str]) -> tuple[Any, list[str]]:
        name = path.rsplit("/", 1)[-1]
        if path.startswith("/0/private/"):
            self.private_calls.append(name)
        time.sleep(self.stalls.get(name, 0.0))
        if name in self.errors:
            return None, [self.errors[name]]
        if path == "/0/public/AssetPairs":
            tokenized = "tokenized_asset" in query.get("aclass_base", [])
            return (self.tokenized_asset_pairs if tokenized else self.asset_pairs), []
        if path == "/0/public/Depth":
            pair = query.get("pair", [""])[-1]
            if pair not in self.books:
                return None, ["EQuery:Unknown asset pair"]
            return {pair: self.books[pair]}, []
        if path == "/0/private/BalanceEx":
            return dict(self.balances), []
        if path == "/0/private/TradeVolume":
            return self._trade_volume(), []
        if path == "/0/private/OpenOrders":
            return {"open": dict(self.open_orders)}, []
        if path == "/0/private/ClosedOrders":
            self.closed_order_forms.append(form)
            offset = int(form.get("ofs", "0"))
            page = dict(list(self.closed_orders.items())[offset : offset + _PAGE])
            return {"closed": page, "count": len(self.closed_orders)}, []
        if path == "/0/private/OpenPositions":
            return dict(self.positions), []
        if path == "/0/private/GetWebSocketsToken":
            return {"token": "loopback-ws-token", "expires": 900}, []
        if path == "/0/private/TradeBalance":
            return {
                "eb": "1000.0",
                "tb": "1000.0",
                "m": "0.0",
                "uv": "0.0",
                "n": "0.0",
                "c": "0.0",
                "v": "0.0",
                "e": "1000.0",
                "mf": "1000.0",
            }, []
        if path == "/0/private/TradesHistory":
            offset = int(form.get("ofs", "0"))
            page = dict(list(self.trades.items())[offset : offset + _PAGE])
            return {"trades": page, "count": len(self.trades)}, []
        if path == "/0/private/AddOrder":
            self.add_orders.append(form)
            txid = f"OLOOP{len(self.add_orders)}-AAAAA-BBBBBB"
            if self.on_add_order is not None:
                self.on_add_order(form, txid)
            return {"descr": {"order": "loopback"}, "txid": [txid]}, []
        if path == "/0/private/CancelOrder":
            self.cancel_forms.append(form)
            if self.on_cancel_order is not None:
                self.on_cancel_order(form)
            return {"count": self.cancel_count}, []
        return None, ["EGeneral:Unknown method"]

    def _trade_volume(self) -> dict[str, Any]:
        if self.trade_volume_answer is not None:
            return self.trade_volume_answer

        def tier(pct: str) -> dict[str, Any]:
            return {"fee": pct, "minfee": "0.1000", "maxfee": "0.4000", "nextfee": None, "tiervolume": "0", "nextvolume": None}

        keys = [key for key in self.asset_pairs if key not in self.trade_volume_omits]
        return {
            "currency": "ZUSD",
            "volume": "0.0000",
            "fees": {key: tier(self.taker_fee_pct) for key in keys},
            "fees_maker": {key: tier(self.maker_fee_pct) for key in keys},
        }


def _handler(venue: KrakenLoopback) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def _respond(self, form: dict[str, str]) -> None:
            url = urllib.parse.urlsplit(self.path)
            result, error = venue.answer(self.command, url.path, urllib.parse.parse_qs(url.query), form)
            body = json.dumps({"error": error, "result": result} if result is not None else {"error": error}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self._respond({})

        def do_POST(self) -> None:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
            # TradeVolume goes out as JSON; every other private call is form-encoded.
            if raw.startswith("{"):
                form = {key: value if isinstance(value, str) else json.dumps(value) for key, value in json.loads(raw).items()}
            else:
                form = {key: values[-1] for key, values in urllib.parse.parse_qs(raw).items()}
            self._respond(form)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return _Handler


@contextmanager
def serve(asset_pairs: dict[str, Any] | None = None) -> Iterator[KrakenLoopback]:
    """A running loopback venue listing `asset_pairs` (the committed AssetPairs fixture by default)."""
    pairs = json.loads(ASSET_PAIRS_FIXTURE.read_text()) if asset_pairs is None else asset_pairs
    venue = KrakenLoopback(asset_pairs=pairs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(venue))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    venue.base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield venue
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def client(venue: KrakenLoopback) -> KrakenSpotHttpClient:
    """The real client, built as `cli/engine/command.py` builds it, pointed at the loopback."""
    return KrakenSpotHttpClient(API_KEY, API_SECRET, base_url=venue.base_url)


class WsPeer:
    """One WebSocket server on its own event-loop thread, bound to 127.0.0.1, for either socket:
    `send_execution` scripts frames onto the connection that subscribed `executions`; on the data
    socket it sends nothing, since the harness hands the executor its quotes itself."""

    def __init__(self, label: str):
        self.label = label
        self.port: int | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.exec_conn = None
        self.subscribed = threading.Event()
        self.log: list[str] = []
        ready = threading.Event()

        async def handler(conn):
            async for raw in conn:
                self.log.append(f"{time.time():.3f} {label} <- {raw}")
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                method = message.get("method")
                stamp = _ws_stamp()
                if method == "ping":
                    await conn.send(
                        json.dumps({"method": "pong", "req_id": message.get("req_id"), "time_in": stamp, "time_out": stamp})
                    )
                elif method == "subscribe":
                    channel = (message.get("params") or {}).get("channel")
                    answer = {
                        "method": "subscribe",
                        "req_id": message.get("req_id"),
                        "success": True,
                        "result": {"channel": channel, "snapshot": False},
                        "time_in": stamp,
                        "time_out": stamp,
                    }
                    await conn.send(json.dumps(answer))
                    self.log.append(f"{time.time():.3f} {label} -> {json.dumps(answer)}")
                    if channel == "executions":
                        self.exec_conn = conn
                        self.subscribed.set()

        async def main():
            self.loop = asyncio.get_running_loop()
            self._closing = self.loop.create_future()
            async with websockets.serve(handler, "127.0.0.1", 0) as server:
                self.port = server.sockets[0].getsockname()[1]
                ready.set()
                await self._closing

        self._thread = threading.Thread(target=lambda: asyncio.run(main()), daemon=True)
        self._thread.start()
        assert ready.wait(10), f"the {label} WebSocket peer did not start"

    def close(self) -> None:
        """Close the server and its connections, and join the loop's thread."""

        def release() -> None:
            if not self._closing.done():
                self._closing.set_result(None)

        try:
            self.loop.call_soon_threadsafe(release)
        except RuntimeError:  # the loop has already closed
            pass
        self._thread.join(10)

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def send_execution(self, data: dict[str, Any]) -> None:
        """One `executions` update frame carrying `data`, sent to the subscribed connection."""
        frame = {"channel": "executions", "type": "update", "data": [data], "sequence": int(time.time())}
        text = json.dumps(frame)
        self.log.append(f"{time.time():.3f} {self.label} -> {text}")
        asyncio.run_coroutine_threadsafe(self.exec_conn.send(text), self.loop).result(5)


def _ws_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())


def exec_new(txid: str, cl_ord_id: str | None, *, symbol: str, qty: float, price: float, side: str = "buy") -> dict[str, Any]:
    """The `new` execution frame the private socket sends when an order is accepted, in the shape
    upstream's `KrakenWsExecutionData` parses."""
    data = {
        "exec_type": "new",
        "order_id": txid,
        "symbol": symbol,
        "side": side,
        "order_type": "limit",
        "order_qty": qty,
        "limit_price": price,
        "order_status": "new",
        "time_in_force": "GTC",
        "post_only": False,
        "reduce_only": False,
        "timestamp": _ws_stamp(),
        "cum_qty": 0.0,
        "cum_cost": 0.0,
        "avg_price": 0.0,
    }
    if cl_ord_id is not None:
        data["cl_ord_id"] = cl_ord_id
    return data


def exec_trade(
    txid: str,
    cl_ord_id: str | None,
    *,
    symbol: str,
    qty: float,
    price: float,
    last_qty: float,
    cum_qty: float,
    exec_id: str,
    trade_id: int,
    side: str = "buy",
) -> dict[str, Any]:
    """The `trade` execution frame for one fill of `last_qty`, carrying both halves upstream parses: the
    status half (`order_status`, `cum_qty`) and the fill half (`exec_id`, `last_qty`)."""
    data = {
        "exec_type": "trade",
        "order_id": txid,
        "symbol": symbol,
        "side": side,
        "order_type": "limit",
        "order_qty": qty,
        "limit_price": price,
        "order_status": "filled" if cum_qty >= qty else "partially_filled",
        "timestamp": _ws_stamp(),
        "exec_id": exec_id,
        "trade_id": trade_id,
        "last_qty": last_qty,
        "last_price": price,
        "cost": last_qty * price,
        "cum_qty": cum_qty,
        "cum_cost": cum_qty * price,
        "avg_price": price,
        "liquidity_ind": "m",
        "fees": [{"asset": "EUR", "qty": 0.0}],
    }
    if cl_ord_id is not None:
        data["cl_ord_id"] = cl_ord_id
    return data


def exec_canceled(
    txid: str, cl_ord_id: str | None, *, symbol: str, qty: float, price: float, cum_qty: float, side: str = "buy"
) -> dict[str, Any]:
    """The `canceled` execution frame, `cum_qty` the venue's cumulative fill at the cancel."""
    data = {
        "exec_type": "canceled",
        "order_id": txid,
        "symbol": symbol,
        "side": side,
        "order_type": "limit",
        "order_qty": qty,
        "limit_price": price,
        "order_status": "canceled",
        "timestamp": _ws_stamp(),
        "cum_qty": cum_qty,
        "cum_cost": cum_qty * price,
        "avg_price": price,
        "reason": "User requested",
    }
    if cl_ord_id is not None:
        data["cl_ord_id"] = cl_ord_id
    return data


@contextmanager
def serve_with_sockets(asset_pairs: dict[str, Any] | None = None) -> Iterator[tuple[KrakenLoopback, WsPeer, WsPeer]]:
    """`serve` plus the two WebSocket peers a node's data and execution clients connect to."""
    with serve(asset_pairs) as venue:
        data = WsPeer("data")
        try:
            exec_ = WsPeer("exec")
        except BaseException:
            data.close()
            raise
        try:
            yield venue, data, exec_
        finally:
            data.close()
            exec_.close()
