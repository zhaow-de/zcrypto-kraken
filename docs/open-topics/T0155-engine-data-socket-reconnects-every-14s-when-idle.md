---
status: open
ripe_when: "the next attended, canary-gated engine converge window — the trigger this topic was opened on has FIRED and decided the option; what remains is shipping it"
---

# The engine's market-data socket reconnects every ~14 s whenever it is idle

## Context — what

The first v2 engine (converged 2026-08-26 16:40:20Z) holds a Kraken public market-data WebSocket that tears itself down and reconnects roughly every 14.5 seconds, continuously — about **6,000 reconnects per day**. Measured on the host: 33 cycles in the first 8 minutes after the converge.

The loop is:

```
Read idle timeout: no data received for 10.0s
Detected dead connection, transitioning to Reconnect
Backing off for 1s...
Reconnecting -> Reconnect succeeded -> (10 s later, again)
```

Every line is **WARN**. An `ERROR|CRITICAL|Traceback|PanicException` sweep over the same logs returns a clean zero, which is how the first pass over this boot reported it healthy.

**Nothing here is misconfigured.** The chain is:

- The engine's data client holds **no subscriptions** between cycles. That is the design: `cli/engine/executor.py` subscribes per-order (`subscribe_quotes` at intent activation, `unsubscribe_quotes` at completion). The engine is disarmed and has never submitted an order, so it has never subscribed.
- Kraken sends nothing on an idle connection. Measured directly against `wss://ws.kraken.com/v2`: one `status` frame on connect, then **35 s of complete silence** on an unsubscribed socket.
- `ws_idle_timeout_ms` defaults to **10000** and fires. It is doing its job and reporting a true fact — no market data is flowing.

## Why this matters

Not because anything is broken today — the socket is unused while disarmed. Three costs, and the third is the one that bites later:

- **~6,000 connections/day to Kraken from the host that holds the live trade key** (the key is IP-bound to that host). Public-WS connection rate and private-API limits are normally accounted separately, so this is a risk worth naming rather than a demonstrated consequence.
- **The noise masks the signal.** It already hid itself from an ERROR-level grep. Armed, a genuine reconnect during an in-flight order would be one WARN among thousands of identical ones.
- **Arming does not fix it, and raises the stakes.** The duty-cycle arithmetic is in Findings; typical arming removes about 1 % of the reconnects, and the churn then overlaps the order path, where the measured subscribe→first-quote gap is 2.3–2.8 s against a `_QUOTE_WAIT` of 30 s.

## Findings so far

**Every safety-critical path avoids this socket.** Established by reading each one, and this is the reason the topic is not urgent:

| Mechanism | Where it lives | Touches the engine's nautilus WS? |
| --- | --- | --- |
| Venue-status **alerting** (`zcrypto_capture_venue_status_total`) | the capture daemon's OWN client (`cli/capture/ws_client.py`); `grep nautilus cli/capture/*.py` returns nothing | No |
| Venue-status **trade gate** | `cli/engine/venue.py` — REST `api.kraken.com/0/public/SystemStatus`, allowlist of one (`online`) | No |
| Order **submission** | REST — `use_ws_trade=False`, set explicitly (spec `00100` D10) | No |
| Quote **freshness** during an order | executor `_QUOTE_WAIT` / `_QUOTE_SILENCE`, both 30 s, per-instrument | No |

The capture daemon could not hit this bug regardless: its socket carries 12 active subscriptions at a measured max staleness of 0.62 s, so it is never idle for 10 s — and it runs on both capture hosts.

**A first proposed fix was wrong, and the upstream doc says why.** Raising `ws_idle_timeout_ms` above the heartbeat looked correct and measured clean over 200 s (0 timeouts, 0 reconnects at 90000, against 5 in 70 s at the default). It is the failure mode, not the cure. Per the nightly networking doc:

> The separate idle timeout resets only on text or binary application data, so control traffic cannot hide a silent market-data stream.

> A venue that answers the keepalive with a text payload refreshes the idle timeout exactly like real data does, so that window means something only when it sits below the heartbeat interval.

Kraken answers the keepalive with a text payload, which is why the 200 s run looked green: the mechanism was defeating itself. `10 s idle < 30 s heartbeat` is exactly what the doc prescribes. Recorded because the wrong fix is the attractive one and would have shipped looking correct.

**Config surface, measured rather than read from the stubs:**

- `ws_idle_timeout_ms=0` genuinely **disables** detection — 0 timeouts and 0 reconnects over 70 s, matching the doc's "unset (detection off)".
- `ws_idle_timeout_ms=None` **silently falls back to 10000**. Anyone writing `None` intending "off" gets the loop instead.

**Duty cycle if armed** (4-hourly boundary = 240 min; `_TIME_BOX` caps an intent at 15 min; intents run sequentially):

| Scenario | Subscribed | Reconnects/cycle | Cycle still idle |
| --- | --- | --- | --- |
| disarmed (today) | 0 min | 993 | 100 % |
| typical: 3 intents ≈ 1 min | 3 min | 981 | 98.8 % |
| heavy: 8 intents × 2 min | 16 min | 927 | 93.3 % |
| pathological: 12 legs time-boxing | 180 min | 248 | 25 % |

**Reproduction** is keyless and local — the data client is public, so no credentials and no IP whitelisting are needed. A data-only `LiveNode` (`exec_enabled=False` never reads credentials) reproduces the loop exactly: 5 timeouts in 70 s at the default.

## Suggested next steps

**The deferral is discharged: Option A.** The first v2 boundary cycle after the converge journalled `cycle-20.json` with `started_at` 20:01:30.002Z and `completed_at` 20:01:41.862Z (2026-08-26) — 11.9 s, well inside `[B, B+30 min]`. The reconnect loop therefore costs cycle completion nothing: it is churn and noise, not breakage. Ship A; B stays written up as the better end-state, on its own evidence.

- **Option A — set `ws_idle_timeout_ms=0` on the data client** (`cli/engine/node.py::_data_client_config`). One line, no trading-behaviour change, reverts in one line. Gives up socket-level stalled-stream detection, whose *response* is to reconnect — which mid-order delays quotes by a further 3–5 s rather than helping; the executor's 30 s per-instrument guards are what actually govern behaviour and are unaffected. `0` is the network layer's own default; the adapter's 10000 assumes a subscribed client, which this one is not.
- **Option B — hold a permanent subscription** so data always flows and the idle timeout becomes meaningful again. Strictly better end-state on two counts: it removes the 2.3–2.8 s subscribe→first-quote latency from every intent (against `_TICK_SECONDS = 5.0`), and it restores continuous observability of a socket that is otherwise a black box between cycles. Costs a live-trade-path behavioural change that, by the same standard spec `00100` D10 applied to `use_ws_trade`, needs its own evidence rather than riding on a churn fix.

They compose: if B lands, `ws_idle_timeout_ms` is **restored to 10000**, because a permanently-subscribed client is the shape the adapter default assumes. A is the correct setting until B exists, not a step away from it.

- **The deciding input has been read** — `cycle-<HH>.json`'s `completed_at` under `<engine_state_dir>/journal/` on the engine host, against `[B, B+30 min]`. It landed inside the window, so A is sufficient for now. Re-read it after any change here.
- **B's latency benefit cannot be measured until the engine is armed**, which is itself an argument for taking A first and measuring B's payoff rather than assuming it.
- Whichever lands, it ships on an attended, canary-gated engine converge — never a hot edit.
