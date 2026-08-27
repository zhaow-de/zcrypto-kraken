# Spec 00101 — the idle data socket: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship spec `00101` Option A hardened — `ws_idle_timeout_ms=0` on the engine's Kraken data client, pinned by guards proven to bite, with the operator section landing in the same change — so the disarmed engine stops spending 27 % of the per-IP Cloudflare connection budget it shares with the L2 capture primary.

**Architecture:** One config literal in `cli/engine/node.py::_data_client_config`. Four guards around it: an interface pin on the adapter semantics the decision rests on (`0` disables, `None` silently means 10000); a builder-level `== 0` pin; a **CI-resident offline harness** that runs a real data node against a loopback Kraken (stub REST + a scripted WebSocket peer) and separates the defect from the fix and from both true positives on one fixture; and an opt-in live row that measures the one property loopback cannot show — that Kraken's own ~60 s inactivity close is held off by the heartbeat with the idle timer off. The runbook gains one KNOWN LIMITATION section. Nothing on the executor, the exec client, or any other config field moves.

**Tech Stack:** Python 3.14 via `uv`; `nautilus-trader` at the pinned 2.x wheel (Rust-backed Kraken adapter); `websockets` 17.0.1 (already a declared dependency) and `http.server` for the loopback venue; pytest; `infra/scripts/mutate-probe.sh` for guard proofs.

## Global Constraints

- `ws_idle_timeout_ms` is the literal `0`. `None` reads back as `10000` and reinstates the loop — spec D1. No test may accept `None` as "off".
- No other field on `KrakenDataClientConfig` changes in production: `heartbeat_interval_secs` stays at the adapter default (30) — spec D1. Test fixtures may shrink it locally; production may not.
- No executor change, no subscription of any kind, no log-level suppression — spec D3, D4.
- The restore-to-default rule is stated in `_data_client_config`'s docstring — spec D5.
- The runbook section lands in the SAME change as the code — spec D6, `spec-plan-locations.md`.
- Every guard is proven on a fixture where defect and correct behaviour differ, and the suite keeps a true positive — `agent-ops.md`.
- **`infra/scripts/mutate-probe.sh` refuses a dirty worktree and restores with `git checkout --`.** Every mutation proof therefore runs **after** the commit it proves, never before. A failed probe is fixed and the commit amended.
- A network-touching test is gated on `ZCRYPTO_LIVE_VENUE_TESTS=1`, never on reachability — `CLAUDE.md`. The offline harness is NOT network-touching and is never gated.
- No new `T<NNNN>` topics. Residuals go to spec D7 and T0155's body.
- Model ceiling for every implementer and task reviewer in this plan: **Opus**. Fable was authorised for the cold spec+plan review only.
- Every commit carries `Co-Authored-By:` and, after its review, `Reviewed-by:` — `commit-messages.md`. Stage by explicit path.
- Branch: `feat/t0155-idle-data-socket`, cut from `8f6370c7` on `deploy/v2-capture-secondary`. Its PR targets that branch, not `develop`, for the same reason the hygiene PR did.

### Log lines this plan counts, verbatim from the shipped binary

Measured on the pinned wheel, not remembered. Any guard that counts a different string is counting nothing:

| Meaning | The line |
| --- | --- |
| the idle timer fired | `Read idle timeout: no data received for <N>s` |
| a reconnect began | `websocket::client: Reconnecting` |
| a reconnect finished | `Reconnect succeeded` |
| a dead peer was caught | `Heartbeat timeout: no frame received for <N>s` |
| the client connected (positive trace) | `Connected: client_id=KRAKEN` |

**There is no `CONNECTED` token in the shipped node.** The uppercase form exists in the binary only as `SocketState`'s variant name and is never logged. A probe asserting on it fails before it measures anything — and the positive-trace assertion is load-bearing: during this plan's own fixture development, a shell quoting bug fed the probe one argument instead of four, and `Connected: client_id=KRAKEN == 0` is what distinguished "the harness broke" from "the socket was quiet".

---

### Task 1: Pin the adapter semantics the whole decision rests on

**Files:**
- Modify: `tests/test_nautilus_interface_pin.py` — the function `test_the_kraken_client_configs_accept_the_arguments_we_pass` and one new test beside it

**Interfaces:**
- Consumes: `KrakenDataClientConfig(ws_idle_timeout_ms=...)` and its `.ws_idle_timeout_ms` property
- Produces: the guarantee later tasks lean on — that `0` and `None` mean what spec D1 says they mean on THIS pinned wheel

- [ ] **Step 1: Add the kwarg to the acceptance test and write the semantics test**

In `test_the_kraken_client_configs_accept_the_arguments_we_pass`, change the data-client construction to:

```python
    KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        ws_idle_timeout_ms=0,
    )
```

Directly below that test, add:

```python
# The two values spec 00101 D1 rests on, measured here rather than remembered: `0` disables the
# idle timer, and `None` is NOT "off" -- it silently falls back to the adapter default and reinstates
# the reconnect loop. A future upstream change to either reading would pass every other test.
def test_ws_idle_timeout_zero_disables_and_none_means_the_default():
    from nautilus_trader.adapters.kraken import KrakenDataClientConfig, KrakenEnvironment, KrakenProductType

    off = KrakenDataClientConfig(product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=0)
    assert off.ws_idle_timeout_ms == 0, "0 must read back as 0 -- that is the literal the engine ships"

    fallback = KrakenDataClientConfig(product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=None)
    assert fallback.ws_idle_timeout_ms == 10000, (
        f"None must read back as the adapter default (10000), not as off: {fallback.ws_idle_timeout_ms!r}"
    )
    assert fallback.ws_idle_timeout_ms != off.ws_idle_timeout_ms, "if these ever coincide, None has become a valid 'off' and D1's literal-0 rule is moot"
```

- [ ] **Step 2: Run both tests — expect PASS (an interface pin is green from the start by construction)**

Run: `uv run pytest tests/test_nautilus_interface_pin.py -k "accept_the_arguments or idle_timeout" -v`
Expected: 2 passed. An interface pin asserts the library, not our code, so it cannot be red first; its bite is proven in Step 4 instead.

- [ ] **Step 3: Commit**

```bash
git add tests/test_nautilus_interface_pin.py
git commit -m "test(engine): pin the two idle-timeout readings spec 00101 rests on

\`ws_idle_timeout_ms=0\` must read back as 0 and \`None\` must read back as the adapter default
(10000), not as off. Both are the measured basis of spec 00101 D1; either reading changing
upstream would pass every other test and silently reinstate the reconnect loop.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

- [ ] **Step 4: Prove the pin bites — it must fail if the kwarg is renamed or the fallback changes**

The tree must be clean here (the commit in Step 3 is what makes it so); the script refuses otherwise and restores with `git checkout --`.

```bash
bash infra/scripts/mutate-probe.sh \
  --file tests/test_nautilus_interface_pin.py \
  --control 's/ws_idle_timeout_ms=0,/ws_idle_timeout_ms=0, bogus_kwarg=1,/' \
  --mutation 's/assert fallback.ws_idle_timeout_ms == 10000/assert fallback.ws_idle_timeout_ms == 0/' \
  -- uv run pytest tests/test_nautilus_interface_pin.py -k "accept_the_arguments or idle_timeout" -q
```

Expected: `mutate-probe: KILLED (control proven, tree restored byte-identically)`. The control shows the acceptance test rejects an unknown kwarg (so a rename would be caught); the mutation shows the semantics test refuses a world where `None` means off.

---

### Task 2: The one-line change, pinned at the builder

**Files:**
- Modify: `cli/engine/node.py` — `_data_client_config` (return value and docstring)
- Modify: `tests/test_engine_node.py` — `test_the_builder_is_given_the_production_client_and_engine_configs`

**Interfaces:**
- Consumes: `_record_assembly(...)` and `recorder.named("add_data_client")[0]["config"]`, both already in the test file
- Produces: the shipped config; `data_client["config"].ws_idle_timeout_ms == 0` as the property every later task assumes

- [ ] **Step 1: Write the failing assertion**

In `test_the_builder_is_given_the_production_client_and_engine_configs`, after `assert isinstance(data_client["config"], KrakenDataClientConfig)`, add:

```python
    # spec 00101 D1: the idle timer is OFF, asserted as the literal 0 -- None reads back as 10000
    # (pinned in test_nautilus_interface_pin.py) and would silently reinstate the reconnect loop.
    # heartbeat_interval_secs is pinned unchanged because it, not the idle timer, is what still
    # catches a dead peer; tests/test_engine_data_socket.py proves that on a loopback peer.
    assert data_client["config"].ws_idle_timeout_ms == 0
    assert data_client["config"].heartbeat_interval_secs == 30
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_engine_node.py -k the_builder_is_given_the_production_client -q`
Expected: 1 failed, `assert 10000 == 0` — the config does not set the knob yet, so it reads the fallback.

- [ ] **Step 3: Make the change and state the two rules in the docstring**

In `cli/engine/node.py`, replace `_data_client_config` with:

```python
def _data_client_config() -> KrakenDataClientConfig:
    """The Kraken data client. The adapter loads the venue's instrument universe itself on connect;
    nothing here selects it, and `test_engine_node.py`'s live instrument-arrival test is what proves
    the twelve `INSTRUMENT_IDS` still land in the Cache.

    `product_type` and `environment` are stated rather than inherited. Both equal the library's
    defaults today, so nothing moves; they are the two fields that select WHICH Kraken venue this
    engine reaches, and an upstream default flip would otherwise land on the live trade path with
    nothing red anywhere. `test_nautilus_interface_pin.py` pins both enums.

    `ws_idle_timeout_ms=0` is spec 00101 D1, and the value is the LITERAL zero: `None` reads back as
    the adapter default and reinstates the reconnect loop while looking like "off". Disarmed, nothing
    is subscribed on this socket, so the timer can only ever detect the absence of data it was never
    sent; a dead peer is still caught by the heartbeat, which is why that field is left alone.
    D5: if a standing subscription ever lands (spec 00101 D3), restore this to the adapter default in
    the same change -- a permanently-subscribed client is the shape that default assumes."""
    return KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        ws_idle_timeout_ms=0,
    )
```

- [ ] **Step 4: Run it — expect PASS**

Run: `uv run pytest tests/test_engine_node.py -k the_builder_is_given_the_production_client -q`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/node.py tests/test_engine_node.py
git commit -m "feat(engine): the data client's idle timer is off, and the builder pins the literal

spec 00101 D1. Disarmed, nothing is subscribed on the Kraken data socket, so the 10 s idle timer
only ever measured the absence of data it was never sent -- one reconnect per 14.8 s, 40 per
rolling 10 min, 27 % of the per-IP Cloudflare connection budget this host shares with the L2
capture primary. The literal 0 is asserted at the builder because None reads back as 10000.
heartbeat_interval_secs is pinned unchanged: it is what still catches a dead peer.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the pin bites against the fallback shape, not merely against absence**

```bash
bash infra/scripts/mutate-probe.sh \
  --file cli/engine/node.py \
  --control 's/        ws_idle_timeout_ms=0,/        ws_idle_timeout_ms=1,/' \
  --mutation 's/        ws_idle_timeout_ms=0,/        ws_idle_timeout_ms=None,/' \
  -- uv run pytest tests/test_engine_node.py -k the_builder_is_given_the_production_client -q
```

Expected: `KILLED (control proven, tree restored byte-identically)`. The control is `1`, not a duplicate keyword: a repeated kwarg is a `SyntaxError` at import, which would "fail" the whole module for a reason unrelated to the assertion under proof — the degenerate control `mutate-probe.sh`'s own header warns about. `1` makes the `== 0` assertion itself do the catching. The mutation is the exact regression D1 names — someone writing `None` for "off".

---

### Task 3: The offline harness — defect, fix, and both true positives on one fixture

**Files:**
- Create: `tests/test_engine_data_socket.py`

**Interfaces:**
- Consumes: `cli.engine.node._node_builder`, `cli.config.EngineConfig`, the adapter's config surface
- Produces: the CI-resident proof that (a) the harness reproduces the defect, (b) the shipped value stops it, (c) with the timer OFF a real drop still reconnects, and (d) with the timer OFF a dead peer is still caught by the heartbeat at three intervals

This is the task the cold review added. Without (c) and (d), `reconnects == 0` at `ws_idle_timeout_ms=0` cannot distinguish a healthy socket from reconnect machinery rendered inert, and spec D1's claim that the heartbeat still catches a dead peer is pinned by nothing.

Everything here is loopback: a stub REST server answering the one endpoint the adapter calls at startup (`GET /0/public/AssetPairs` — measured, not assumed) and a scripted WebSocket peer. No venue, no credentials, no data gate, no opt-in.

- [ ] **Step 1: Create the file with the fixture and the probe**

```python
"""The engine's Kraken data socket, measured against a loopback venue.

spec 00101 D1 turns the adapter's idle timer off. Three claims ride on that and none of them is
visible from a config assertion: that the timer is what produced the reconnect loop, that turning
it off does not also disable reconnection, and that a dead peer is still caught by the heartbeat.
Each is measured here against a WebSocket peer scripted to behave one way, so the defect and the
correct behaviour differ on the same fixture.

Offline by construction: the node talks to an HTTP server and a WebSocket server bound to
127.0.0.1 in the probe's own process. Nothing off this machine is reached, so this runs in CI --
unlike the venue-shaped row in `test_engine_node.py`, which is opt-in.

A child interpreter for the same reason as every other node probe in this repo: a node installs
process-wide signal handlers and runs its own Rust runtime, neither of which belongs in the pytest
process. The Rust logger writes to stdout, and the counts are taken from the captured stream.
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

# argv: mode, idle_ms, window_s, heartbeat_secs.
#
#   silent      -- the peer accepts and then says nothing at all. At the adapter default this is
#                  the production defect; at 0 it is the production fix.
#   close_once  -- the peer accepts, waits, and closes the connection once, then accepts again and
#                  stays silent. A real drop, with the idle timer off.
#   deaf        -- a raw socket that completes the WebSocket upgrade by hand and then answers
#                  nothing, not even a ping. `websockets` auto-pongs, which is exactly the
#                  behaviour that must NOT be present here, so this peer cannot use it.
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
```

- [ ] **Step 2: Add the four rows**

Append to the same file:

```python
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
```

- [ ] **Step 3: Run the four rows — expect PASS, for four different reasons**

Run: `uv run pytest tests/test_engine_data_socket.py -v`
Expected: 4 passed in ~110 s. Reference counts measured while writing this plan, on this wheel:

| row | idle | heartbeat | window | timeouts | reconnects | heartbeat lines | connected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `silent` (defect) | 10000 | 30 | 35 s | 3 | 3 | 0 | 1 |
| `silent` (fix) | 0 | 30 | 35 s | 0 | 0 | 0 | 1 |
| `close_once` | 0 | 30 | 15 s | 0 | 1 | 0 | 1 |
| `deaf` | 0 | 2 | 15 s | 0 | 2 | 2 | 1 |

The `deaf` row's heartbeat line reads `Heartbeat timeout: no frame received for 6.0s` — three intervals, which is the property spec 00101 D1 claims at 30 s. If the defect row FAILS, stop and fix the fixture before believing anything else in this file.

- [ ] **Step 4: Commit**

```bash
git add tests/test_engine_data_socket.py
git commit -m "test(engine): the data socket's four behaviours, measured against a loopback venue

spec 00101 D1's guard set, offline and CI-resident: a stub REST endpoint and a scripted WebSocket
peer, no venue and no credentials. Four rows on one fixture -- the adapter default reproduces the
reconnect loop (the harness proving it bites), the shipped 0 stops it, a peer that really closes
still produces exactly one reconnect, and a raw peer that answers no ping is still caught by the
heartbeat at three intervals. The last two are why 'zero reconnects' can be read as health rather
than as inert machinery.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

### Task 4: The live row — the one property loopback cannot show

**Files:**
- Modify: `tests/test_engine_node.py` — one new module constant `_LIVE_IDLE_PROBE` beside `_INSTRUMENT_ARRIVAL_PROBE`, one new test beside `test_the_twelve_instruments_are_in_the_cache_when_the_strategy_starts`, and the module docstring's "the one test that RUNS a node" clause, which this task makes false

**Interfaces:**
- Consumes: `_kraken_public_reachable()` and the `ZCRYPTO_LIVE_VENUE_TESTS` opt-in, both already in the file; `cli.engine.node._data_client_config` as the injection point
- Produces: spec 00101's Verification row — 180 s keyless at `0`, through three of Kraken's ~60 s inactivity windows

Task 3 proves the mechanism. It cannot prove this: the loopback peer never closes an inactive socket, and **Kraken does, at ~60 s**. What holds the real socket open is the heartbeat ping and Kraken's text `pong` — a venue behaviour no local fixture reproduces. Hence one live row, and only one.

- [ ] **Step 1: Add the probe script**

Beside `_INSTRUMENT_ARRIVAL_PROBE`, add:

```python
# A data-only node against the real venue with the idle timer at argv[2], for a fixed window. The
# override goes through `_data_client_config` itself -- `_node_builder` resolves that module global
# at call time -- so the probe exercises the construction path the engine ships. Keyless: the data
# client is public and the node is exec_enabled=False.
_LIVE_IDLE_PROBE = """
import os, sys, threading, time
from pathlib import Path

from cli.config import EngineConfig
from cli.engine import node as node_mod
from nautilus_trader.adapters.kraken import KrakenDataClientConfig, KrakenEnvironment, KrakenProductType

root = Path(sys.argv[1])
idle_ms = int(sys.argv[2])
window_s = float(sys.argv[3])

node_mod._data_client_config = lambda: KrakenDataClientConfig(
    product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=idle_ms,
)
live = node_mod._node_builder(
    EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=False)
).build()


def stopper():
    time.sleep(window_s)
    sys.stdout.flush()
    os._exit(0)


threading.Thread(target=stopper, daemon=True).start()
live.run()
"""
```

- [ ] **Step 2: Add the test**

Beside `test_the_twelve_instruments_are_in_the_cache_when_the_strategy_starts`, add:

```python
def test_the_shipped_idle_value_survives_krakens_own_inactivity_close(tmp_path):
    """What the loopback fixture in test_engine_data_socket.py cannot show: Kraken closes an
    inactive socket at ~60 s, and a local peer never does. With the idle timer off, the heartbeat
    ping and Kraken's text pong are what hold the socket open -- so 180 s of silence must cross
    three of the venue's inactivity windows without a single reconnect."""
    # Opt-in, not reachability-gated, for the same reason as the instrument-arrival test above: a
    # skip on an unreachable venue would read as coverage.
    if os.environ.get("ZCRYPTO_LIVE_VENUE_TESTS") != "1":
        pytest.skip("needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it")
    if not _kraken_public_reachable():
        pytest.fail("ZCRYPTO_LIVE_VENUE_TESTS=1 was set but Kraken's public endpoint is unreachable")
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", _LIVE_IDLE_PROBE, str(tmp_path), "0", "180"],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    out = result.stdout + result.stderr
    timeouts = out.count("Read idle timeout")
    reconnects = out.count("websocket::client: Reconnecting")
    connected = out.count("Connected: client_id=KRAKEN")
    detail = f"exit={result.returncode} timeouts={timeouts} reconnects={reconnects}\n--- tail ---\n{out[-3000:]}"
    assert connected >= 1, f"the socket never connected, so the window measured nothing: {detail}"
    assert timeouts == 0, f"the idle timer fired at ws_idle_timeout_ms=0: {detail}"
    assert reconnects == 0, f"Kraken's inactivity close was not held off by the heartbeat: {detail}"
```

- [ ] **Step 3: Re-true the module docstring**

The file's opening docstring says "the one test that RUNS a node is the instrument-arrival test, which needs Kraken's public endpoint and skips loudly without it". Step 2 makes it two. Replace that clause with "the two tests that RUN a node against Kraken's public endpoint are the instrument-arrival test and the idle-socket test, and both skip loudly without `ZCRYPTO_LIVE_VENUE_TESTS=1`" — a docstring is a claim about what is below it (`code-prose.md`), and this one is falsified by this task's own change.

- [ ] **Step 4: Run it with the venue — expect PASS**

Run: `ZCRYPTO_LIVE_VENUE_TESTS=1 uv run pytest tests/test_engine_node.py -k survives_krakens_own -v`
Expected: 1 passed, ~3 min wall clock, 0 timeouts and 0 reconnects with ≥ 1 `Connected: client_id=KRAKEN`.

- [ ] **Step 5: Run it without the opt-in — expect SKIP, never a silent pass**

Run: `uv run pytest tests/test_engine_node.py -k survives_krakens_own -v`
Expected: 1 skipped with the message naming the env var.

- [ ] **Step 6: Commit**

```bash
git add tests/test_engine_node.py
git commit -m "test(engine): 180 s of silence against the real venue at ws_idle_timeout_ms=0

The one property the loopback fixture cannot show: Kraken closes an inactive socket at ~60 s and a
local peer never does, so what holds the real socket open is the heartbeat ping and Kraken's text
pong. Opt-in (ZCRYPTO_LIVE_VENUE_TESTS=1), data-only, no credentials read. Measured at write time:
<paste timeouts/reconnects/connected from the run>.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

### Task 5: The operator section lands with the code

**Files:**
- Modify: `infra/runbooks/engine.md` — one new section before `## engine-probe-window — PROCEDURE`
- Modify: `infra/runbooks/README.md` — one index row beside the two `engine-*` PROCEDURE rows

**Interfaces:**
- Consumes: the runbook's section shape (`<a name>`, `## <anchor> — KIND`, `### What you are seeing / What it means / What to do`, `### Retire when`) and its admission rule
- Produces: spec D6 on the operating surface; the "stop the engine" instruction carries the owner's approval of spec 00101

- [ ] **Step 1: Add the section**

Immediately before the line `<a name="engine-probe-window"></a>` in `infra/runbooks/engine.md`, insert:

```markdown
<a name="engine-data-socket-idle"></a>

## engine-data-socket-idle — KNOWN LIMITATION

### What you are seeing

Nothing fires this. You are reading `docker logs zcrypto-engine` on the engine host — because a reconnect line caught your eye, or because a Kraken outage is in progress and you are deciding whether the engine is making it worse.

### What it means

The engine's Kraken **data** socket is idle by design while disarmed: nothing is subscribed between intents, and the executor subscribes quotes per intent.

**First check whether the timer is actually off yet.** It is off only on an engine running a digest built from a revision that sets `ws_idle_timeout_ms=0` (spec `00101`); `docs/reference/fleet-pins.md`'s engine row records what is deployed. **Until that converge lands, a continuous `Read idle timeout` → reconnect loop every ~14.8 s is the EXPECTED state, not a regression** — and the crossing named below is then ~4.4 min rather than ~6.3, because the engine's own idle churn is already sitting in the rolling window. With the timer off, the lines mean:

- **`Read idle timeout: no data received for 10.0s`** — the timer has been turned back on. That is a config regression, not a venue event: the literal `0` was replaced (writing `None` does it, silently). Nothing to do on the host; fix the config and redeploy.
- **`Reconnecting` → `Reconnect succeeded`**, without a preceding `Read idle timeout` **or** `Heartbeat timeout` line — a real drop. Read it against `zcrypto_capture_reconnects_total{host="zcrypto"}` on the capture dashboard: both moving means the venue or the host's network moved; the engine alone moving is the engine's problem.
- **`Heartbeat timeout: no frame received for 90.0s`** — a dead peer, caught by the heartbeat at three intervals. Expect a reconnect to follow.

None of these lines reaches Loki — the engine ships only the `zcrypto` logger — so `docker logs` on the host is the only place they can be read.

**Why the socket's behaviour is capture's problem.** Kraken's edge rate-limits connection attempts to ~150 per rolling 10 minutes **per IP**, and bans the IP for 10 minutes on breach. The engine host is the L2 capture primary; `ws.kraken.com`, `ws-auth.kraken.com` and `api.kraken.com` resolve to the same edge. So a retry storm from the engine's two sockets can take the capture daemon's ability to reconnect with it — and L2 is unbackfillable. The engine's failure backoff (≈ 0.7 → 5 s, ~30 attempts per 150 s per socket, no knob to change it) crosses that limit about 6.3 minutes into a fast-failing outage.

### What to do

- **A Kraken outage in progress and both engine sockets retrying** (`Reconnecting` lines every few seconds, `Reconnect attempt N failed`): **stop the engine** before the retry count nears 150 in ten minutes. A ban self-renews only while something keeps retrying, and the capture daemon's own reconnect needs the budget more than the disarmed engine does.

  ```bash
  sudo systemctl stop zcrypto-engine     # NOT `docker stop`
  ```

  **`docker stop zcrypto-engine` does not stop the engine.** The unit's `ExecStart` is an attached `docker compose up` with `Restart=always`, `RestartSec=10`: stopping the container makes the compose process return, the unit exit, and systemd start it again ten seconds later — the retries you were trying to stop resume on their own. `systemctl stop` runs the unit's `ExecStop` (`docker compose down`) and leaves it down.

  **The cost, before you do it:** boundary cycles run at 00/04/08/12/16/20 UTC, and a boundary that passes with no journal artifact zeroes the ratified gate streak. A restart re-runs a missed boundary only within `[B, B+25 min]` and only while that boundary has no `cycle-<HH>.json` *or* `failed-cycle-<HH>.json`. Stopping just after a boundary is nearly free; stopping just before one costs the streak.

  Start it again with `sudo systemctl start zcrypto-engine` once `zcrypto_capture_reconnects_total{host="zcrypto"}` stops moving, and read the next `cycle-<HH>.json` for `completed_at` inside `[B, B+30 min]` as the all-clear.

- **A single `Reconnecting`/`Reconnect succeeded` pair** with the venue quiet — note it and move on; the heartbeat did its job.
- **Any `Read idle timeout` line at all, on an engine whose deployed revision sets `ws_idle_timeout_ms=0`** — the knob regressed. Find the change to `cli/engine/node.py::_data_client_config` and redeploy; the builder test that pins it (`test_engine_node.py`) says which value was written. On an engine that predates that converge the same line is expected — check the pins row first.

### Retire when

`ws_idle_timeout_ms=0` is no longer set in `cli/engine/node.py::_data_client_config` — a standing subscription landed and spec `00101` D5's restore rule applied — or the socket lines reach Loki, whichever comes first.
```

- [ ] **Step 2: Add the index row**

In `infra/runbooks/README.md`, directly above the `engine-probe-window` row, add:

```markdown
- [`engine-data-socket-idle`](engine.md#engine-data-socket-idle) — KNOWN LIMITATION: the engine's data socket is idle by design while disarmed; what its reconnect lines mean, why they exist only in `docker logs`, and how to stop the engine during a Kraken outage so its retries cannot cost the capture primary its reconnect budget.
```

- [ ] **Step 3: Verify the guards that read these files**

Run: `uv run pytest tests/test_infra_alert_rules.py -k "runbook or index" -q`
Expected: 4 passed — these are the only tests that read `infra/runbooks/`; they check anchor uniqueness and that the index routes to every section and only to real ones. A new section with no index row, or a row pointing at a typo'd anchor, fails here. **`or index` is load-bearing**: the index half is `test_the_index_routes_to_every_section_and_only_to_real_ones`, whose name carries no `runbook`, so a bare `-k runbook` deselects the only test that reads `README.md` and a section with no index row passes it green.

Run: `uv run pytest tests/test_code_prose_citations.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: all passed — the section cites `spec 00101` in prose, which a runbook may (it is read with the repo open), and carries no plan-task number.

Run: `uv run pre-commit run mdformat --files infra/runbooks/engine.md infra/runbooks/README.md`
Expected: Passed, or a rewrite you re-stage.

- [ ] **Step 4: Commit**

```bash
git add infra/runbooks/engine.md infra/runbooks/README.md
git commit -m "docs(runbooks): what the engine's idle data socket's lines mean, and how to stop it

spec 00101 D6, landing with the code it describes. A KNOWN LIMITATION because nothing fires it: an
operator arrives from docker logs on the host, the only place the Rust-side socket lines exist.
The outage response names systemctl, not docker: the unit is an attached 'compose up' with
Restart=always, so 'docker stop' lets systemd restart the engine ten seconds later and the retries
resume. The gate-streak cost of stopping near a boundary is stated in the same paragraph.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

### Task 6: Verify what the diff can reach, and review before push

**Files:** none modified

- [ ] **Step 1: The tests the change reaches, and the full commit gate**

Run: `uv run pytest tests/test_engine_data_socket.py tests/test_engine_node.py tests/test_nautilus_interface_pin.py tests/test_engine_command.py tests/test_infra_alert_rules.py tests/test_code_prose_citations.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: all passed, with the live row skipped (no opt-in set) and the four offline rows RUN, not skipped. A skipped offline row is a defect in this plan's work, not an environment fact.

Run: `uv run pre-commit run -a`
Expected: every hook Passed or Skipped; re-stage and re-run if any hook rewrote a file.

- [ ] **Step 2: Review each commit with a subagent other than its author (Opus ceiling), amend `Reviewed-by:` in the same turn**

Run: `bash infra/scripts/review-trailer-audit.sh deploy/v2-capture-secondary`
Expected: `PASS — every code-kind commit ... carries a Reviewed-by trailer.`

---

### Task 7: Closeout — the topic, the history entry, no decisions-log entry

**Files:**
- Modify: `docs/open-topics/T0155-engine-data-socket-reconnects-every-14s-when-idle.md` — `## Done so far`, `## Suggested next steps`, frontmatter `ripe_when`
- Modify: `docs/open-topics/README.md` — the T0155 bullet
- Modify: `docs/iterations-history-phase6.md` — append the entry

**Interfaces:**
- Consumes: the commits above (cite them by hash copied from `git log`, never from memory)
- Produces: T0155 still `partial`, its code half recorded as done, its remainder narrowed to the attended converge, and spec D7's two residuals written into the body where the eventual closer will see them

- [ ] **Step 1: Re-true T0155**

Under `## Done so far`, append one bullet recording that spec `00101` is implemented on this branch — the literal `0`, the four guards and what each was proven against, the runbook section — with the commit hashes.

Then append a second bullet, headed **Recorded, not deferred — what Option A does not fix** (spec `00101` D7). This is the finding the cold review raised: the residuals live in the spec, and the topic is what its closer reads.

- The **two-socket outage loop** has no adapter knob. Both sockets' failure backoff (≈ 0.7 → 5 s, ~30 attempts per 150 s each) can still exceed Kraken's ~150 per rolling 10 min during a fast-failing outage; A moves the crossing from ≈ T+4.4 min to ≈ T+6.3 min but does not remove it. The only lever is upstream, and it becomes available only when the `nautilus-trader` pin moves — the runbook's stop-the-engine instruction is the standing mitigation until then.
- **Rust-side socket lines never reach Loki** (`_TARGET_LOGGERS = ("zcrypto",)`), so every line the runbook section describes exists only in `docker logs` on the host. A forwarder is viable but is the owner's call, not an autonomous one; it is not owed by this topic.

Neither is a new topic — the standing rule — and neither may be dropped silently when T0155 closes.

Rewrite `**Remainder — implement spec 00101 (A, hardened).**` to `**Remainder — converge spec 00101.**` naming the attended, canary-gated engine converge **before the first armed probe pass**, and the post-converge reads from spec `00101` § Verification (idle-timeout count 0 in the first hour and at 24 h; reconnects per rolling 10 min ≈ 0, from 40; the next `cycle-<HH>.json` inside `[B, B+30 min]`).

Transcribe the converge form from spec `00101` § Deploy **exactly** — it is engine-only, and it entails a capture rollout first:

> `infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<new>`, where the new image must already have baked as **capture** on the secondary: the engine role's canary assert refuses a digest the secondary is not running, and there is no engine secondary.

Set `ripe_when` to `"docs/reference/fleet-pins.md's engine row carries a digest built from a revision that sets ws_idle_timeout_ms=0 in cli/engine/node.py -- the attended, canary-gated engine converge, taken before the first armed probe pass"`. It is anchored on a checkable fact rather than on a branch name, which disappears at merge. Status stays `partial`. Refresh the README bullet's last sentence to match.

- [ ] **Step 2: Append the history entry**

Append to `docs/iterations-history-phase6.md`:

```markdown
## 2026-08-27 — the engine's idle data socket stops spending a connection budget it shares with capture (iter-146)

- **One literal, four guards, one runbook section — spec `00101`.** `ws_idle_timeout_ms=0` on the engine's Kraken data client. Disarmed, nothing is subscribed, so the adapter's 10 s idle timer measured the absence of data it was never sent and reconnected every 14.8 s — 40 attempts per rolling 10 minutes, 27 % of the per-IP Cloudflare budget (~150, 10-minute ban) that the engine host shares with the L2 capture primary and with its own REST order path. The heartbeat, unchanged at 30 s, still catches a dead peer at ≤ 90 s and keeps Kraken's ~60 s inactivity close at bay.
- **The value is pinned as the literal, because `None` means 10000.** An interface pin measures both readings on the pinned wheel; the builder test asserts `== 0` and was proven to refuse `None`.
- **The socket's behaviour is measured, not asserted — and offline.** A loopback venue (stub REST plus a WebSocket peer scripted three ways) runs a real data node in CI and separates four behaviours on one fixture: the adapter default reproduces the reconnect loop, the shipped `0` stops it, a peer that really closes still produces exactly one reconnect, and a raw peer that answers no ping is still caught by the heartbeat at three intervals. The last two are what let "zero reconnects" be read as health rather than as inert machinery. One venue-shaped row stays opt-in for the property loopback cannot show: Kraken closes an inactive socket at ~60 s, and a local peer never does.
- **The decision was challenged before it shipped, and the option space is recorded.** Fourteen options across four lenses, every claim refuted adversarially: every sentinel-subscription form is equivalent on the stakes and re-arms the trigger; every other knob is A in disguise or not viable; dropping either client breaks the boundary concordance. B stays available on its own armed evidence, re-scoped as an executor change. Two of the topic's own claims fell — the mid-order quote-delay story, and a 1 s backoff floor that was the successful-reconnect step, not failure pacing.
- **The cold review caught a runbook instruction that would have failed in the outage it was written for.** `docker stop zcrypto-engine` does not stop the engine: the unit is an attached `docker compose up` with `Restart=always`, so systemd restarts it ten seconds later and the retry storm resumes. The section names `systemctl stop` and says why the other form is wrong, in the same sentence.
- **What A does not fix is recorded where it will be read, not deferred.** The two-socket outage loop has no adapter knob — the only lever is upstream after the pin moves — and Rust-side socket lines never reach Loki. Both live in spec `00101` D7, in the runbook section, and in [[T0155]]'s body, so the topic's eventual closer sees them. No new topic, per the standing rule.
- **The converge is still owed.** [[T0155]] stays `partial`; it closes at the next attended, canary-gated engine converge — engine-only tags, and gated on the new image having baked as capture on the secondary first — verified by the idle-timeout count reading 0 at one hour and at 24 h.
```

- [ ] **Step 3: No decisions-log entry, and say so**

This is an engineering decision about a transport knob, not a subject-matter research decision (`decisions-log.md`'s gate). Nothing is appended to `docs/research/14.phase6-decisions.md`; the closeout commit message states that.

- [ ] **Step 4: Commit the closeout**

```bash
git add docs/open-topics/T0155-engine-data-socket-reconnects-every-14s-when-idle.md docs/open-topics/README.md docs/iterations-history-phase6.md
git commit -m "docs(engine): iter-146 closeout -- spec 00101 implemented, its converge still owed

T0155 stays partial: the code half is done and reviewed on this branch; the attended,
canary-gated engine converge is the remainder, and its ripe_when is anchored on the fleet-pins
engine row rather than on a branch name. D7's two residuals -- the two-socket outage loop with no
adapter knob, and the Rust socket lines that never reach Loki -- are written into the topic body,
so the eventual closer cannot archive over them. No decisions-log entry: a transport knob is an
engineering decision, not a subject-matter one.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage.** D1 → Task 2 (literal, heartbeat unchanged, docstring). D2 → Tasks 1 and 2 (pins proven against `None` and against a kwarg rename). D3, D4 → Global Constraints (nothing touches the executor, no subscription, no `component_levels`). D5 → Task 2's docstring. D6 → Task 5, same change, with the `Retire when` the runbook's admission rule requires. D7 → Task 7 Step 1 writes both residuals into T0155's body and the history entry records them; no new topics. Verification § → Task 1 Step 4, Task 2 Step 6, Task 3 (defect reproduces, fix holds, and **both** true positives — a real drop and a dead peer, offline), Task 4 (keyless 180 s at `0` against the venue). Deploy § → out of this plan by design: the converge is attended and governed by `capture-deploys.md`; Task 7 records it as the owed remainder and transcribes its form verbatim, including the capture bake it depends on.

**Ordering.** Every `mutate-probe.sh` invocation follows the commit it proves, because the script refuses a dirty worktree and restores with `git checkout --`.

**Placeholder scan.** The only angle-bracketed items are the ones the plan cannot know at write time — the authoring model's name in each trailer, Task 4's measured counts, the commit hashes in Task 7, and the digest in the converge form. Task 3's counts are filled in from a real run made while writing this plan.

**Type consistency.** `data_client["config"]` is the `KrakenDataClientConfig` instance in every task; `.ws_idle_timeout_ms` and `.heartbeat_interval_secs` are properties on it. `_OFFLINE_PROBE`'s argv contract (`mode`, `idle_ms`, `window_s`, `heartbeat_s`, `one_pair_json`) matches `_run`'s `subprocess.run` list; `_LIVE_IDLE_PROBE`'s (`root`, `idle_ms`, `window_s`) matches its own. Both count the log strings named in Global Constraints, never `CONNECTED`.
