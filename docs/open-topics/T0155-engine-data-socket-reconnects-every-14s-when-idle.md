---
status: partial
ripe_when: "docs/reference/fleet-pins.md's engine row carries a digest built from a revision that sets ws_idle_timeout_ms=0 in cli/engine/node.py -- the attended, canary-gated engine converge, taken before the first armed probe pass"
---

# The engine's market-data socket reconnects every ~14 s whenever it is idle

## Context — what

The first v2 engine (converged 2026-08-26 16:40:20Z) holds a Kraken public market-data WebSocket that tears itself down and reconnects roughly every **14.8 seconds**, continuously — 40 per rolling 10 minutes, about **5,760 per day** (measured 2026-08-27 over a 20-minute window). The first reading on the host was 33 cycles in the 8 minutes after the converge.

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

- **The reconnects draw on a per-IP connection budget shared with the L2 capture primary and with the engine's own REST order path — demonstrated, not named.** Kraken's guide: Cloudflare limits connection attempts to ~150 per rolling 10 minutes per IP and bans the IP for 10 minutes on breach. `ws.kraken.com`, `ws-auth.kraken.com` and `api.kraken.com` resolve to the same five edge addresses, and the rendered `zcrypto.toml` has `exec_enabled = true`, so the disarmed engine holds two sockets behind that edge. Measured: **40 attempts per rolling 10 min — 27 % of the budget — permanently, doing nothing.** In an outage the failure backoff (loopback-measured 0.7 → ~4.9 s cap, ~30 attempts/150 s per socket) crosses 150 at ≈ T+4.4 min today and ≈ T+6.3 min under Option A; the capture daemon then cannot reconnect either. Spec `00101` records the arithmetic.
- **The noise masks the signal, measured:** 2,886 WARN in a 6 h window ≈ 11,500 WARN/day, and the two real handshake failures in that window (`expected 101 Switching Protocols`, 07:17:11Z and 09:22:11Z) were each one line among them. None of it reaches Loki — `cli/logging/config.py` ships only the `zcrypto` logger — so the loop, a real reconnect and a retry storm are `docker logs`-on-host only.
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

## Done so far

- **The option is DECIDED: A.** The topic was opened deferring the choice until the first v2 boundary cycle showed whether the loop affects cycle completion. It does not. `cycle-20.json` records `started_at` 20:01:30.002Z and `completed_at` 20:01:41.862Z (2026-08-26) — 11.86 s against a 30-minute budget — so the reconnect loop is churn and noise, not breakage. The deciding input was read where it lives: `cycle-<HH>.json`'s `completed_at` under `<engine_state_dir>/journal/` on the engine host. Re-read it after any change here.
- **The decision was challenged and stands, on stronger grounds than it was made.** On 2026-08-27 the option space was searched under the shared-budget constraint — fourteen options across four independent lenses (network layer, capture safety, trade path, operability), every load-bearing claim attacked by a skeptic. Every sentinel-subscription variant (B, one basket leg, one foreign pair, a trades sentinel) measured viable and *equivalent to A on the stakes that matter* — idle draw to ~0, outage draw untouched — while re-arming a 10 s reconnect trigger and placing a standing stream on the order path's socket. Everything else fell: idle above the heartbeat is A in disguise (the text pong refreshes the window); `subscribe_instruments` is not a sentinel (the timer fired 10.0 s after the subscribe); `TUNGSTENITE` changes nothing; log suppression hides the signal; dropping either client breaks the boundary concordance, which reads both clients' cache. The re-decision and its measured basis are **spec `00101`**, which now owns the delivery.
- **Both options are written up with measurements** (below), so shipping is a transcription rather than a re-derivation, and B remains available on its own evidence rather than as a fallback — re-scoped by the spec as an executor change, since the executor's `unsubscribe_quotes` at intent end targets the same actor a standing subscription would.
- **Spec `00101` is IMPLEMENTED — the code half of this topic is done.** The literal `ws_idle_timeout_ms=0` on the engine's Kraken data client (`cli/engine/node.py::_data_client_config`, `8a64a9dd`), with `heartbeat_interval_secs` pinned unchanged at 30 s beside it because that, not the idle timer, is what still catches a dead peer. Four guards, each proven against the defect it names: the interface pin measures BOTH readings on the pinned wheel — `0` disables detection, `None` silently falls back to 10000 (`41e03f01`, re-trued to name the test that proves the disabling in `7349d91a`); the builder test asserts `== 0` and was proven to refuse `None` (`8a64a9dd`); a loopback venue separates four behaviours offline and in CI — the adapter default reproduces the reconnect loop, the shipped `0` stops it, a peer that really closes still yields exactly one reconnect, and a raw peer that answers no ping is still caught by the heartbeat at three intervals (`45f45a0f`); and one opt-in venue-shaped row (`ZCRYPTO_LIVE_VENUE_TESTS=1`) holds 180 s of silence against `ws.kraken.com` for the one property loopback cannot show — Kraken closes an inactive socket at ~60 s and a local peer never does (`26b71d74`). The operating surface landed with the code: `infra/runbooks/engine.md`'s `engine-data-socket-idle` section reads what each socket line means and names `systemctl stop`, never `docker stop`, for an outage — the unit is an attached `docker compose up` with `Restart=always` (`f87b0943`). Spec and plan: `11c861ee`, `b0ecdffd`, `4f077163`.
- **Recorded, not deferred — what Option A does not fix** (spec `00101` D7). Neither is a new topic, per the standing rule, and neither may be dropped silently when this topic closes:
  - **The two-socket outage loop has no adapter knob.** Both sockets' failure backoff (≈ 0.7 → 5 s, ~30 attempts per 150 s each) can still exceed Kraken's ~150 connection attempts per rolling 10 min during a fast-failing outage; A moves the crossing from ≈ T+4.4 min to ≈ T+6.3 min but does not remove it. The adapter surfaces nothing reconnect-shaped, so the only lever is upstream — exposing the reconnect knobs the binary already carries — and it becomes available only when the `nautilus-trader` pin moves (spec `00100` D11 holds it frozen until the engine is armed). Until then the runbook section's stop-the-engine instruction is the standing mitigation.
  - **Rust-side socket lines never reach Loki.** `cli/logging/config.py` ships only the `zcrypto` logger (`_TARGET_LOGGERS = ("zcrypto",)`), so every line the runbook section describes — a real reconnect, a handshake failure, a retry storm — exists only in `docker logs` on the engine host. A `SocketStateChanged` forwarder is measured viable on this wheel, but it is a separate component and the owner's call, not an autonomous one; it is not owed by this topic.


## Suggested next steps

**Remainder — converge spec `00101`.** The code half is done (above); what is left is the attended, canary-gated engine converge that carries it to the fleet, taken **before the first armed probe pass**. The form is engine-only, transcribed from spec `00101` § Deploy:

> `infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<new>`, where the new image must already have baked as **capture** on the secondary: the engine role's canary assert refuses a digest the secondary is not running, and there is no engine secondary.

The post-converge reads are spec `00101` § Verification, on the engine host since the container's `StartedAt`: `Read idle timeout` count **0** in the first hour and again at 24 h; reconnect events per rolling 10 min **≈ 0**, from 40; the next `cycle-<HH>.json` landing inside `[B, B+30 min]`. **A is SHIPPED** — see `## Done so far`. Both write-ups stay below only as the comparison B's own evidence is measured against; neither is a pending action.

- **Option A (shipped) — `ws_idle_timeout_ms=0` on the data client** (`cli/engine/node.py::_data_client_config`). One line, reverts in one line; no code change on the trade path, with one narrow armed-availability change, safety unchanged: socket-level detection of a feed that stops while the transport stays healthy. That case cannot arise from a quiet market — a subscribed socket is refreshed by Kraken's 1/s heartbeat channel, so the earlier claim that the timer "mid-order delays quotes by a further 3–5 s" was wrong — and mid-intent the executor's own guards govern anyway: `_QUOTE_WAIT` refuses an intent with no quote in 30 s and advances the plan, `_QUOTE_SILENCE` revokes one whose quotes stop and halts it. A dead peer is still caught by the heartbeat at ≤ 90 s. `0` is the network layer's own default; the adapter's 10000 assumes a subscribed client, which this one is not.
- **Option B — hold a permanent subscription** so data always flows and the idle timeout becomes meaningful again. Better end-state on one count that holds — it removes the 2.3–2.8 s subscribe→first-quote latency from every intent (against `_TICK_SECONDS = 5.0`) — and one that is thinner than it looks: what it restores is the heartbeat channel's 1/s frame, so the idle timer then catches only a dead heartbeat generator with a live pong; a data stall with the heartbeat flowing is invisible under every option. Costs a live-trade-path behavioural change that, by the same standard spec `00100` D10 applied to `use_ws_trade`, needs its own evidence rather than riding on a churn fix — and it is an **executor** change, not a config one: the executor's `unsubscribe_quotes` at intent end targets the same actor and topic, and that collision is unmeasured.

They compose: if B lands, `ws_idle_timeout_ms` is **restored to 10000**, because a permanently-subscribed client is the shape the adapter default assumes. A is the correct setting until B exists, not a step away from it.

- **B's latency mechanism is keyless-measurable; its value to fills is armed-only** — which is still the argument for taking A first and measuring B's payoff rather than assuming it.
- Whichever lands, it ships on an attended, canary-gated engine converge — never a hot edit.
