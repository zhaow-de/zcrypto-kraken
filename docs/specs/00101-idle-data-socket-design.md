# 00101 — the engine's idle data socket: stop paying a shared connection budget for nothing

The v2 engine's public market-data WebSocket reconnects every ~14.8 s whenever nothing is subscribed, which — disarmed — is always. T0155 opened the question, deferred it to the first boundary cycle, and decided Option A on the evidence that cycles complete. This spec re-decides on a fact the topic did not have: the reconnects draw on a **per-IP connection budget that the engine shares with the L2 capture primary and with its own REST order path**, and exceeding it bans the IP for ten minutes. Under that constraint the option space was searched fully (fourteen options, four independent lenses, each claim adversarially refuted); Option A survives as the only change that removes the idle draw without touching the trade path, and it ships hardened.

## The governing principle

**The engine must never be the reason the capture primary cannot reconnect.** L2 capture is unbackfillable; the engine's disarmed socket is unused. Any behaviour of the unused socket that can consume the budget the capture daemon needs is a defect in the engine, whatever the socket's own health looks like. The socket's own detection guarantees are secondary to that, and are weighed only after it is satisfied.

## The measured basis

Everything below was measured on 2026-08-27 on the engine host or read from a primary source; nothing is inferred from the topic's earlier prose.

**The loop.** 81 reconnect events in 20 min = one per **14.8 s**; **4,094 since the converge** (16.8 h at that rate); **40 per rolling 10 minutes**. Each event is five log lines, two of them WARN (`Read idle timeout: no data received for 10.0s`, `Backing off for 1s`) — 2,886 WARN in a 6 h window, ≈ **11,500 WARN/day**. The engine ran four boundary cycles through it at 10.89–12.11 s against a 30-minute budget, and its RSS floor (352.9 MiB, decaying steps) sits 230 MiB below the v1 engine's plateau on the same host: the loop costs neither the cycle nor memory.

**Kraken's rules, verbatim** (`docs.kraken.com/api/docs/guides/spot-ws-intro`): *"Cloudflare imposes a connection/re-connection rate limit — per Internet Protocol (IP) address — of approximately 150 attempts per rolling 10 minutes. If the reconnection rate limit is exceeded, the IP address is banned for 10 minutes."* Also: *"The server closes any open websocket connection within approximately one minute of inactivity"*; *"Any, for example a ping, request can be used to keep the connection alive"*; *"After maintenance or extended downtime: attempt to reconnect no more quickly than once every five (5) seconds."* The heartbeat channel is *"automatically generated on subscription to any channel"* — never on an unsubscribed socket.

**One IP, one budget, three consumers.** `ws.kraken.com`, `ws-auth.kraken.com` and `api.kraken.com` all resolve to the same five Cloudflare edge addresses (`104.17.185–189.205`, no AAAA). The engine host is the capture primary. The rendered `zcrypto.toml` has `exec_enabled = true`, so the disarmed engine holds **two** Cloudflare-fronted sockets, and its REST order path, `SystemStatus` gate and boundary OHLC fetches sit behind the same edge. Idle churn is therefore **27 % of a budget shared with unbackfillable capture and with the order path — permanently, doing nothing.**

**Failure pacing, measured, not assumed.** The 4,084 `Backing off for 1s` lines are the *successful-reconnect* step. Against a loopback server answering non-101, the backoff escalates 0.7 → 0.9 → 1.3 → 1.75 → 2.8 → 3.95 → ~4.9 s cap, each followed by a fixed 1 s step: **~30 attempts in 150 s** per socket, below Kraken's 5 s post-downtime rule for the first ~23 s of every outage. Worst-case fast-fail outage: ≈ 106 attempts per socket per rolling 10 min, **two sockets ≈ 212 > 150**. With capture's own ≤ 15, the window reaches 150 at **≈ T+4.5 min today** (40 idle attempts already in the trailing window) and **≈ T+6.5 min with Option A**. The adapter exposes no reconnect knob (`heartbeat_interval_secs`, `ws_idle_timeout_ms`, `timeout_secs`, `transport_backend`, `max_requests_per_second`, `proxy_url` — nothing reconnect-shaped); the binary carries them, but only the Betfair config surfaces them.

**What the idle timer actually guards.** nautilus's nightly networking doc: the heartbeat window *"counts frames rather than data, so a keepalive reply refreshes it"*, and *"sending a heartbeat establishes that the peer answers it, so the interval alone is enough to say when silence means the connection is gone."* Dead-peer detection therefore exists **without** the idle timer, at three heartbeat intervals (≤ 90 s). The idle timer adds only *"a feed which stopped flowing while the transport stays healthy"* — refreshed by any text frame, and Kraken answers the keepalive with a text `pong`, so the window *"means something only when it sits below the heartbeat interval"* **and only while something is subscribed**. On the disarmed engine nothing is, so the timer detects the absence of data it was never sent.

**Config surface, measured.** `ws_idle_timeout_ms=0` genuinely disables the timer — 190 s keyless, 0 timeouts, 0 reconnects, one `Connected: client_id=KRAKEN` as the positive trace, through three of Kraken's ~60 s inactivity windows, the heartbeat keeping the socket alive. `None` silently falls back to 10000. `subscribe_instruments(KRAKEN)` is **not** a sentinel — the timer fired 10.0 s after "Subscribed KRAKEN instruments". `transport_backend=TUNGSTENITE` changes nothing (4/4 timeouts on both backends).

**What cannot be removed.** The boundary concordance calls `venue_state_from_cache(self.cache, …)`: it reads instruments from the node cache the data client populates, and the account the exec client populates. Without the data client every boundary degrades to `venue_state=None`; without the exec client it raises `no account cached for venue`. Both sockets stay open disarmed; that is structural.

**Where the evidence lives.** `cli/logging/config.py` ships only the `zcrypto` logger to Loki (`_TARGET_LOGGERS = ("zcrypto",)`). The reconnect loop, a real reconnect, and both observed `Sockudo handshake failed … expected 101 Switching Protocols` errors (07:17:11Z, 09:22:11Z; ~1 KB non-101 responses, consistent with a Cloudflare interstitial, unproven) exist in `docker logs` on the host only.

## Decisions

### D1 — `ws_idle_timeout_ms=0`, as a literal, and nothing else changes

`cli/engine/node.py::_data_client_config` sets `ws_idle_timeout_ms=0`. The value is the literal `0`: `None` reads back as 10000 and reinstates the loop while looking like "off". Nothing else on the config moves — `heartbeat_interval_secs` stays at the adapter's 30, so Kraken's ~60 s inactivity close is kept at bay by the ping and a dead peer is still caught at ≤ 90 s.

This is the only knob-level change that removes the idle draw. The alternatives at the same surface were measured and fall: raising the idle window above the heartbeat, or dropping the heartbeat below the window, both let the text `pong` refresh the timer — the same behaviour as `0`, behind a value that reads as armed; a window under the heartbeat but longer than 10 s halves the churn and keeps a trigger that fires only when nothing is subscribed.

What A gives up is stated exactly, because the topic overstated it: socket-level detection of a feed that stops while the transport stays healthy, which on this engine matters only mid-intent, where the executor's own per-instrument guards govern — `_QUOTE_WAIT` refuses an intent that receives no quote within 30 s and advances the plan; `_QUOTE_SILENCE` revokes one whose quotes stop for 30 s and halts it. Neither depends on the socket layer. The one case A never self-heals is a heartbeat generator dead while the pong still answers; it has never been observed, and an attended restart clears it.

### D2 — the value is pinned by tests that are proven to bite

`tests/test_engine_node.py`'s builder test asserts `data_client["config"].ws_idle_timeout_ms == 0`, and `tests/test_nautilus_interface_pin.py`'s kwarg-acceptance test carries `ws_idle_timeout_ms` so an upstream rename fails loudly rather than silently reverting to the default. Both are proven at write time against the defect they name: the `== 0` assertion must fail when the config passes `None` (the fallback shape), not merely when the kwarg is absent.

### D3 — no standing subscription; B stays available on its own evidence, re-scoped

Every sentinel-subscription form was measured: B as written (all twelve legs), one quote subscription on a basket leg, one on a foreign pair, one `subscribe_trades` sentinel. All stop the idle loop; none changes the outage draw; all put a standing stream on the socket the order path's quotes ride and re-arm a 10 s reconnect trigger that spends connection attempts on heartbeat hiccups where A spends none. The detection they restore is thinner than the topic claimed — a subscribed socket is refreshed by Kraken's 1/s heartbeat channel, so the idle timer catches only a dead heartbeat generator with a live pong, and a market-data stall with the heartbeat flowing is invisible under every option.

B is therefore not rejected; it is held to spec 00100 D10's standard and re-scoped honestly: it is an **executor** change, because the executor's `unsubscribe_quotes` at intent end targets the same actor and topic as a standing subscription would, and that collision is unmeasured. A basket-leg sentinel is worse still — the first intent on that leg unsubscribes it.

### D4 — no log suppression

`LoggerConfig(component_levels=…)` exists and could silence `nautilus_network::websocket::client`. Rejected: it hides the signal and leaves the budget exposure untouched. After D1 the surviving lines are the ones an operator needs to read.

### D5 — the restore rule

If a standing subscription ever lands under D3's evidence, `ws_idle_timeout_ms` is restored to the adapter default, because a permanently-subscribed client is the shape that default assumes. The docstring on `_data_client_config` states this, so the two decisions cannot drift apart silently.

### D6 — the operating-surface imperative lands with the code

`infra/runbooks/engine.md` gains one KNOWN LIMITATION section — the shape its README's admission rule requires, `Retire when` included — in the same change as D1, stating what the socket's log lines mean once it is idle by design: a `Read idle timeout` line means the knob has regressed; `Reconnecting` / `Reconnect succeeded` at INFO is a real drop, to be read against `zcrypto_capture_reconnects_total{host="zcrypto"}` for whether the venue or the host moved; `Heartbeat timeout: no frame received` is a dead peer. And the human response to a WebSocket retry storm coinciding with a Kraken outage: stop the engine, because a Cloudflare ban self-renews only while something keeps retrying, and the capture daemon needs the budget more. That last sentence is the owner's to approve before it lands; it is written here so the approval is of a text, not of an idea.

### D7 — what this spec does not fix, recorded where it will be read

Three things survive A and are recorded in T0155's body and this spec rather than as new topics:

- **The two-socket outage loop.** No knob on the adapter config paces failed reconnects; the only lever is upstream — exposing the reconnect knobs the binary already carries — and that waits for the pin to move (spec 00100 D11: the pin stops moving before arming).
- **Rust-side log lines never reach Loki.** A real reconnect, a handshake failure, and a retry storm are visible only in `docker logs` on the host. The cheap route to observability is a `SocketStateChanged` forwarder through the `zcrypto` logger, measured viable on this wheel (`CONNECTED`/`DISCONNECTED` for `kraken-spot-data-streams`). It is a separate component, opened on the owner's word.
- **Detection latency.** A fully silent peer is caught at ≤ 90 s rather than 10 s. Mid-intent the executor's guards act first; between cycles nothing consumes the socket.

## Verification

- **Unit, proven to bite:** the `== 0` pin fails against `None`; the interface pin fails if the kwarg is dropped.
- **Keyless, local:** a data-only `LiveNode` (`exec_enabled=False`) at `ws_idle_timeout_ms=0` runs ≥ 180 s with 0 `Read idle timeout` and 0 `Reconnecting` lines — the existing 190 s run is the reference (0 timeouts, 0 reconnects, 1 `CONNECTED`).
- **Post-converge, by outcome:** `docker logs` on the engine host, since the container's `StartedAt` — `Read idle timeout` count **0** in the first hour and at 24 h; reconnect events per rolling 10 min **≈ 0** (from 40); WARN/day from ≈ 11,500 to the residual real-event count; the next `cycle-HH.json` lands inside `[B, B+30 min]`; engine RSS floor compared against its own pre-converge samples, never cross-host.
- **The guard's true positive, offline and CI-resident:** with the timer OFF, a real drop must still reconnect and a dead peer must still be caught. Both are provoked against a loopback WebSocket peer, never the venue — a server that accepts and then closes once yields exactly one `Reconnecting` → `Reconnect succeeded`; a raw-handshake peer that answers no ping yields `Heartbeat timeout: no frame received` and then a reconnect. Without these, `reconnects == 0` at `ws_idle_timeout_ms=0` cannot distinguish a healthy socket from reconnect machinery rendered inert, and D1's claim that the heartbeat still catches a dead peer is pinned by nothing.

## Deploy

A is an engine re-pin and follows `capture-deploys.md` in full: attended, inside the 4-hourly inter-cycle gap, verified at the next boundary. The form is the engine-only one `site.yml` documents — `--limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<new>` — and `engine_image_digest` is the operand that moves. The combined `--tags capture,engine` form is not owed here: it belongs to a revision touching `roles/capture/files/config.alloy`, and this one does not.

**The one-line change entails a capture rollout first.** The engine role's canary assert refuses a re-pin whose digest the secondary is not running *as capture* — there is no engine secondary, so that bake IS the engine's gate. Shipping this therefore means: build the image, re-pin the secondary's capture to it, let the bake gate pass, let the primary follow, and only then converge the engine onto it. That is `capture-deploys.md`'s ordinary rollout, and it is the real cost of a one-line config change on this fleet.

It ships **before** the first armed probe pass, never during it — the change is disarmed-only in effect, and the arming record (00100 D11) is reconciled against the moving pin.

## Out of scope

- Option B and every sentinel variant (D3) — own evidence, own PR, executor-scoped.
- The socket-state observability forwarder (D7) — own component, owner's word.
- The upstream reconnect-knob issue (D7) — after the pin moves.
- The executor's per-intent subscribe/unsubscribe pattern and its 2.3–2.8 s subscribe→first-quote latency — a B-shaped question, unchanged here.
