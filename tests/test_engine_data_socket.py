"""The engine's Kraken data socket, measured against a loopback venue.

Offline by construction: the node talks to an HTTP server and a WebSocket server bound to 127.0.0.1
in the probe's own process, so nothing off this machine is reached and this runs in CI.

A child interpreter, like every other node probe here: a node installs process-wide signal handlers
and runs its own Rust runtime, neither of which belongs in the pytest process. The Rust logger
writes to stdout, and the counts are taken from the captured stream.
"""

import subprocess
import sys

# One real AssetPairs entry, trimmed to two fee rungs. `GET /0/public/AssetPairs` is the only
# endpoint the adapter requests before it opens the socket (measured against a path-logging stub);
# the node refuses to start if it 404s, so the fixture must answer it with a parseable body.
_ONE_PAIR = """{
  "XXBTZUSD": {
    "aclass_base": "currency", "aclass_quote": "currency", "altname": "XBTUSD",
    "base": "XXBT", "quote": "ZUSD", "cost_decimals": 5, "costmin": "0.5",
    "execution_venue": "international", "fee_volume_currency": "ZUSD",
    "fees": [[0, 0.4], [10000, 0.35]], "fees_maker": [[0, 0.25], [10000, 0.2]],
    "leverage_buy": [2, 3, 4, 5], "leverage_sell": [2, 3, 4, 5],
    "lot": "unit", "lot_decimals": 8, "lot_multiplier": 1,
    "margin_call": 80, "margin_stop": 40, "ordermin": "0.00005",
    "pair_decimals": 1, "status": "online", "tick_size": "0.1", "wsname": "XBT/USD"
  }
}"""

# The peers the child can script, by mode:
#
#   silent      -- accepts, then says nothing at all. At the adapter default this is the production
#                  defect; at 0 it is the production fix.
#   close_once  -- accepts, waits, closes the connection once, then accepts again and stays silent:
#                  a real drop, with the idle timer off.
#   deaf        -- a raw socket that completes the WebSocket upgrade by hand and then answers
#                  nothing, not even a ping. `websockets` auto-pongs, the one behaviour that must
#                  NOT be present here, so this peer cannot use it.
#
# A raw string: the child's source must carry the backslash escapes literally.
_OFFLINE_PROBE = r"""
import asyncio, base64, hashlib, json, os, socket, sys, threading, time
import http.server, socketserver
import websockets

ONE_PAIR = json.loads(sys.argv[5])
MODE, IDLE, WINDOW, HB = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"error": [], "result": ONE_PAIR}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

http_srv = socketserver.TCPServer(("127.0.0.1", 0), H)
HTTP_PORT = http_srv.server_address[1]
threading.Thread(target=http_srv.serve_forever, daemon=True).start()

WS_PORT = None
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

if MODE == "deaf":
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(8); WS_PORT = srv.getsockname()[1]
    def serve_raw():
        while True:
            c, _ = srv.accept()
            req = b""
            while b"\r\n\r\n" not in req:
                d = c.recv(4096)
                if not d:
                    break
                req += d
            key = ""
            for line in req.decode("latin1").split("\r\n"):
                if line.lower().startswith("sec-websocket-key:"):
                    key = line.split(":", 1)[1].strip()
            acc = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
            c.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                       "Connection: Upgrade\r\nSec-WebSocket-Accept: " + acc + "\r\n\r\n").encode())
            # then silence -- no frames, no pong, socket held open. Only the heartbeat can notice.
    threading.Thread(target=serve_raw, daemon=True).start()
else:
    ready = threading.Event()
    def serve_ws():
        async def handler(conn):
            if MODE == "close_once" and not getattr(serve_ws, "dropped", False):
                serve_ws.dropped = True
                await asyncio.sleep(3)
                await conn.close()
                return
            await asyncio.Future()
        async def main():
            global WS_PORT
            async with websockets.serve(handler, "127.0.0.1", 0) as s:
                WS_PORT = s.sockets[0].getsockname()[1]; ready.set()
                await asyncio.Future()
        asyncio.run(main())
    threading.Thread(target=serve_ws, daemon=True).start()
    ready.wait(10)

from nautilus_trader.adapters.kraken import (KRAKEN, KrakenDataClientConfig, KrakenDataClientFactory,
    KrakenEnvironment, KrakenProductType)
from nautilus_trader.common import Environment, LogLevel
from nautilus_trader.config import LoggerConfig
from nautilus_trader.live import LiveNode
from nautilus_trader.model import TraderId

ws = "ws://127.0.0.1:%d" % WS_PORT
built = (LiveNode.builder(name="p", trader_id=TraderId("P-001"), environment=Environment.LIVE)
    .with_logging(LoggerConfig(stdout_level=LogLevel.INFO)).with_timeout_connection(15)
    .add_data_client(name=KRAKEN, factory=KrakenDataClientFactory(),
        config=KrakenDataClientConfig(product_type=KrakenProductType.SPOT,
            environment=KrakenEnvironment.LIVE, base_url="http://127.0.0.1:%d" % HTTP_PORT,
            ws_public_url=ws, ws_private_url=ws, ws_l3_url=ws,
            ws_idle_timeout_ms=IDLE, heartbeat_interval_secs=HB, timeout_secs=5))
    .build())

def stopper():
    time.sleep(WINDOW); sys.stdout.flush(); os._exit(0)
threading.Thread(target=stopper, daemon=True).start()
try:
    built.run()
except BaseException as exc:
    sys.__stdout__.write("RAISED %s: %s\n" % (type(exc).__name__, exc)); sys.__stdout__.flush()
os._exit(0)
"""


def _run(mode: str, idle_ms: int, window_s: float, heartbeat_s: int) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", _OFFLINE_PROBE, mode, str(idle_ms), str(window_s), str(heartbeat_s), _ONE_PAIR],
        capture_output=True,
        text=True,
        timeout=window_s + 90,
    )
    out = result.stdout + result.stderr
    return {
        "timeouts": out.count("Read idle timeout"),
        "reconnects": out.count("websocket::client: Reconnecting"),
        "succeeded": out.count("Reconnect succeeded"),
        "heartbeats": out.count("Heartbeat timeout"),
        # The positive trace. Not "CONNECTED" -- the node never logs that token, so an assertion on
        # it would fail before measuring anything, and every row would fail for the wrong reason.
        "connected": out.count("Connected: client_id=KRAKEN"),
        "detail": f"exit={result.returncode}\n--- tail ---\n{out[-3000:]}",
    }


def test_the_idle_timer_is_what_produces_the_reconnect_loop():
    """The harness proving itself. At the adapter default, against a peer that simply says nothing,
    the socket must reconnect repeatedly -- that is the production defect spec 00101 removes, and
    until it reproduces here, the next test's green means nothing."""
    r = _run("silent", 10000, 35, 30)
    assert r["connected"] >= 1, f"the socket never connected, so nothing was measured: {r['detail']}"
    assert r["timeouts"] >= 2, f"the defect did not reproduce, so this fixture proves nothing: {r['detail']}"
    assert r["reconnects"] >= 2, f"idle timeouts without reconnects is a different bug: {r['detail']}"


def test_the_shipped_value_stops_the_loop():
    """spec 00101 D1 on the same fixture the defect just reproduced on: with the timer off, a
    silent socket is simply held open."""
    r = _run("silent", 0, 35, 30)
    assert r["connected"] >= 1, f"the socket never connected, so nothing was measured: {r['detail']}"
    assert r["timeouts"] == 0, f"the timer fired with ws_idle_timeout_ms=0: {r['detail']}"
    assert r["reconnects"] == 0, f"the socket reconnected with nothing to trigger it: {r['detail']}"


def test_a_real_drop_still_reconnects_with_the_timer_off():
    """The first true positive. `reconnects == 0` above must mean "nothing went wrong", not "the
    reconnect machinery is inert" -- so a peer that really closes the connection must still produce
    exactly one reconnect."""
    r = _run("close_once", 0, 15, 30)
    assert r["connected"] >= 1, f"the socket never connected, so nothing was measured: {r['detail']}"
    assert r["reconnects"] == 1, f"a real drop must reconnect exactly once: {r['detail']}"
    assert r["succeeded"] == 1, f"the reconnect began but never completed: {r['detail']}"
    assert r["timeouts"] == 0, f"the idle timer fired, so this measured the wrong mechanism: {r['detail']}"


def test_a_dead_peer_is_still_caught_by_the_heartbeat_with_the_timer_off():
    """The second true positive, and the one that pins spec 00101 D1's load-bearing claim: what A
    gives up is detection of a stalled FEED, never detection of a dead PEER. Against a raw socket
    that completes the upgrade and then answers nothing -- not even a ping -- the heartbeat must
    still notice. The interval is shrunk to 2 s here so the test costs seconds instead of minutes;
    production keeps the adapter's 30 s, and the timeout lands at three intervals either way, which
    is where spec 00101's <= 90 s comes from."""
    r = _run("deaf", 0, 15, 2)
    assert r["connected"] >= 1, f"the socket never connected, so nothing was measured: {r['detail']}"
    assert r["heartbeats"] >= 1, f"a dead peer went unnoticed with the idle timer off: {r['detail']}"
    assert r["reconnects"] >= 1, f"the heartbeat fired but no reconnect followed: {r['detail']}"
    assert r["timeouts"] == 0, f"the idle timer fired, so this measured the wrong mechanism: {r['detail']}"
