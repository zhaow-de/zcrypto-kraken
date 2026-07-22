# Log-shipping rework — direct-ship from the app, docker.sock retired (iter-116)

**Status:** designed and approved in the attended 2026-07-22 brainstorming session; every decision below was made explicitly by the owner.

## Goal

Retire the docker-socket log path fleet-wide. Today every long-lived container's stdout reaches Grafana Cloud via Alloy reading `/var/run/docker.sock` — a root-equivalent credential on internet-facing hosts (the capture role's own comment calls it "a known, accepted residual") and the substrate of the [[T0089]] reader-wedge class (six containers went log-dark for a day; the NAS's GET-only socket proxy was removed 2026-07-14 for severing this same stream every 10 minutes). After this spec: the Python CLI ships its own logs, nothing mounts the socket, and the wedge class is unrepresentable because no long-lived reader attaches to docker's log files at all.

## D1 — Transport: direct-ship from the app (approach A)

The CLI gains an opt-in shipping sink that POSTs its own log records to Grafana Cloud Loki's push API. Four approaches were evaluated:

- **A. Direct-ship from the app — chosen.** No socket, no Alloy in the CLI log path (survives Alloy down/wedged/restarting), fewest moving parts, works on hosts with no Alloy. Costs accepted knowingly: Loki write credentials in app-container env (D5 bounds this to a write-only token), crash loses the in-flight ring (D2 makes stdout the local ground truth), the app owns ~150 lines of retry/batching (D9 tests them).
- **B. journald log driver for every container, Alloy tails the journal — rejected.** Keeps Alloy as the single log-path intermediary and keeps regex level-extraction alive, contradicting both stated goals.
- **C. App pushes to a localhost Alloy receiver (`loki.source.api`) — rejected.** Best credential isolation, but reintroduces the dependency this rework removes: logs stop flowing whenever local Alloy is down, the T0089/T0048 failure neighborhood.
- **D. App writes JSON to a host-mounted file, Alloy tails it (`loki.source.file` + `stage.json`) — rejected, and recorded as the designated fallback.** Strictly better loss envelope (disk-durable + Alloy WAL) and credential isolation, both explicitly waived by the owner. Rejected on the file-lifecycle argument: T0089's root cause was two processes coordinating over a rotating file (writer rotates, reader holds state), and D rebuilds that shape — better primitives, same failure class, on hosts where disk is also watermark-sensitive ([[T0032]]). A also wins on failure visibility: its drops are self-announcing (D3), where a wedged tail in D is silent in precisely the T0089 way. **Fallback trigger:** if the creds-in-env decision or the bounded-loss envelope hardens the other way (e.g. at go-live), D is the successor; the app-side dual-sink work transfers unchanged.

## D2 — stdout is unchanged and remains the local ground truth

The default behavior is untouched: plain-text stdout, exactly today's format. The `--ship-logs` switch is **additive** — it never silences or reformats the console. Consequences, in order:

- Docker's json-file driver keeps capturing stdout under the existing per-container caps for the CLI containers (50m/5 on capture and the engine, 10m/3 on the poller) — nothing new to configure. (The journald-driver containers of D6 have no json.log at all; journald owns their rotation, and `docker logs` still reads them back.)
- **Docker engine becomes the sole owner of that file's lifecycle.** It rotates by rename (reader-safe), the copytruncate logrotate policy is already purged fleet-wide (T0089), and after this spec nothing attaches a long-lived reader to those files — they are a write-only black box a human opens ad hoc (`docker logs`). Single writer, single rotator, zero coordination: the wedge class needs a reader and there is none.
- A crashing process loses at most the in-memory ring (D3); its final lines survive locally in the json.log. This is why the bounded-drop loss envelope is acceptable.
- Plain text (not JSON) on console was chosen deliberately: `docker logs` stays human-readable for on-host debugging; the JSON payload exists only on the wire.

## D3 — The shipping handler: bounded, non-blocking, self-announcing

New module `cli/logging/ship.py`, stdlib-only (urllib, no new dependencies). A `logging.Handler` subclass:

- `emit()` formats the record and appends to a fixed `collections.deque(maxlen=4096)` — O(1), never blocks, never allocates unboundedly. When full, the **oldest** entry is evicted and a drop counter increments (freshest context survives for the recovery flush; everything is on stdout locally regardless).
- One daemon worker thread drains batches of ≤500 lines or every 1 s, whichever first, and POSTs to `/loki/api/v1/push` (JSON body, basic auth, single **5 s per-operation socket timeout**).
- **Timeout semantics, stated precisely:** `settimeout(5)` bounds every blocking socket call individually — `connect()`, each TLS-handshake read/write, each `send()`, each `recv()` — so accept-then-stall peers (connected but unable to write, or silent after accept) unblock within 5 s per operation. What no stdlib or third-party HTTP client provides is a *total request* deadline: an adversarial peer draining one byte per 4.9 s could stretch a batch almost arbitrarily. DNS resolution (`getaddrinfo`) runs before the socket exists and is governed by the resolver config, not these timeouts. Both residuals are confined to the worker thread — see the structural insulation point below.
- **Deterministic egress:** the opener is built explicitly with `ProxyHandler({})` (env `http_proxy`/`https_proxy` ignored — a stray proxy variable must not reroute log traffic carrying the auth header) and no redirect handler (Loki push never legitimately redirects; a redirect re-sending credentials elsewhere is refused by construction). No connection pooling: one connection per batch has dumber, cleaner failure semantics at ≤1 batch/s.
- **The non-blocking guarantee is structural, not timeout-based:** `emit()` only touches the deque; the POST lives in a separate daemon thread; the exit flush has its own 2 s deadline independent of HTTP state. The absolute worst case — a request that defeats every timeout — costs: shipping stalls, the ring rotates and counts, stdout and process exit are untouched. Timeouts bound how *stale* shipping can get, never app latency.
- **urllib3 evaluated and rejected:** its `Timeout(connect=, read=)` is per-operation too — no total deadline, so the adversarial-trickle residual is unfixed by it; its connection pooling is a liability at this volume (stale keep-alive sockets are where its subtle failures live); its `Retry` machinery would fight the deliberate one-batch/capped-backoff design; and it is a new runtime dependency on the capture image for marginal gain.
- On POST failure: hold that one batch (part of the fixed memory bound) and retry with capped backoff 1 s → 30 s, forever — the ring keeps absorbing and dropping meanwhile. Retries never multiply: one in-flight batch, one backoff clock.
- On recovery after any drops: emit one WARNING — to stdout *and* shipped — "log shipping recovered; N lines dropped". A shipping failure is self-announcing; no silent dark window.
- At process exit: flush with a **2 s hard deadline** (daemon thread + atexit), then drop the remainder and report the count to stdout. A one-shot CLI run against a dead Loki is delayed ≤2 s, never hung.
- The extreme case in the owner's own words — "the remote logs server is down, our application should still run seamlessly" — costs exactly: one 4096-slot ring, one sleeping thread, one bounded retry timer.

## D4 — Labels and line format: no regex anywhere

- Loki labels: `{host, container, level}` — all low-cardinality. `level` comes from `record.levelname` at the source; **no regex exists anywhere in this path, at ingest or at query**.
- Entry timestamp: `record.created` (true event time, nanosecond-precision on the wire). Grafana Cloud Loki accepts out-of-order entries within its window, so retried batches land with honest timestamps.
- The line is the existing, tested `JsonLineFormatter` output verbatim: ts, level, logger, file, line, message, user extras, exception with traceback embedded in the same entry. Keyword search operates on the line; field access at query time is `| json` — a parser, not a regex.
- Dashboard contract (the owner's acceptance bar): filter by host, container, level; keyword search. Label values keep today's scheme (`container` ∈ {capture, engine, liquidations, alloy, …}, `level` uppercase), so existing dashboards and alert rules key on identical selectors.

## D5 — Config surface and credentials

- `--ship-logs` boolean flag in the root callback, beside `--log` / `--log-level`. Applies to any subcommand; only the long-lived service units/compose files pass it (capture, engine, poller). Ops ephemerals and host oneshots stay on the journal path — no change.
- Identity and credentials from env, rendered per host by Ansible: `ZCRYPTO_LOKI_URL`, `ZCRYPTO_LOKI_USERNAME`, `ZCRYPTO_LOKI_PASSWORD`, plus `ZCRYPTO_LOG_HOST` and `ZCRYPTO_LOG_SERVICE` (a container reliably knows neither the host's name nor its compose service name; the compose files do).
- **One shared logs:write-only token** for the whole fleet — a new vault entry, rendered into a root-owned 0600 env file consumed via compose `env_file`, the exact `alloy-secrets.env` pattern. A leak means log-spam/poisoning ability, not read access; revocation = rotating one token. Per-host/per-service tokens were considered and rejected as key sprawl at this fleet size.
- `--ship-logs` with missing env = **hard error at startup** — a deploy bug fails fast at converge/first start, it does not ship silence. Loki being unreachable at runtime is never an error (D3).
- This puts a Grafana Cloud credential in the capture/engine container env on the trade-key host for the first time — decided explicitly, bounded to write-only scope, and recorded in [[T0042]]'s egress note (D8).

## D6 — Fleet end-state: three transport rules, zero socket consumers

| Workload | Transport |
|---|---|
| Python CLI containers (capture ×2, engine, liquidations poller) | direct-ship (D3) + plain stdout to the local json.log |
| Non-CLI long-lived containers (Alloy ×4: zcrypto, zcrypto-red, ops, NAS; NAS `zcrypto-archive-pull`) | `logging: driver: journald` → host journal → Alloy journal pipeline |
| Host oneshots (capture-prune, ops ephemeral `zcrypto-*` jobs, NAS pull units) | journal → Alloy journal pipeline (unchanged) |

- Deleted on all four Alloys: the `- /var/run/docker.sock:...` bind-mount, the docker-group `group_add` that exists only to open it, and the `discovery.docker` + `loki.source.docker` components that dial it. The socket itself is untouched — it is dockerd's own API endpoint; host tooling and every container are unaffected.
- All four Alloys ship **their own** logs via the journald driver: keep-rules widen to `CONTAINER_NAME=grafana-alloy` (journal field `__journal_container_name`), relabeled `container="alloy"` as today, parsed with `stage.logfmt` in place of today's regex — the regex-avoidance principle reaches the journal path too. The journald driver takes effect on container recreation, which the rollout performs anyway.
- The zcrypto regex parse stage in every Alloy config is deleted outright — the app labels its own levels now.
- **NAS caveats, measured 2026-07-22 (they falsified a prior):** DSM 7 runs systemd with a live journald (PID 1 = systemd; journalctl reads entries as root), so the journald treatment works there — but the journal is **volatile** (`/run/log/journal/<machine-id>/` populated, `/var/log/journal/` empty), so a NAS reboot loses any unshipped tail; and the NAS Alloy has **no journal pipeline today** — it is a first-time build there (journal source + relabel + the volatile-path mounts `/run/log/journal` + `/etc/machine-id`). The rollout probes the driver with a throwaway container (`docker run --rm --log-driver=journald …`) **before** touching `zcrypto-archive-pull` — custody discipline: the pull container is never the experiment.
- Division of labor, stated: a dead Alloy cannot ship its own death (true on the old path too); Alloy **liveness** belongs to the metrics-side `Fleet · Alloy dark` rules, Alloy **content** to the journal path. No feedback loop: Alloy logs one error per backoff-limited failed push; self-scraping them does not amplify.

## D7 — Rollout: attended, canary-disciplined, and T0089's recovery vehicle

Ordered steps, each verified by a **positive line arriving in Loki** (the T0089 lesson: never verify by absence), with the Alloy-dark and log-dead-man rules watching throughout:

1. **ops** — poller (new image + flag) and Alloy (journald driver) recreated. First live verification of both new paths; clears the poller's wedge.
2. **NAS** — journald-driver probe with a throwaway container first; then Alloy + `zcrypto-archive-pull` to journald driver, recreated.
3. **Secondary capture** — new image + flag; **24 h bake per the canary rule** (`capture-deploys.md`); clears its wedge.
4. **Primary capture** — after the bake, `-e converge_primary=true`; clears the last capture wedge.
5. **Engine** — flag added only **after the Stage-6a gate** (earliest ~2026-07-25); a mid-soak restart remains forbidden.

Deploying the new capture image recreates the capture containers, which is the only demonstrated fix for the existing T0089 wedges — this rollout is that topic's recovery vehicle, and its per-step positive-trace verification is T0089's own closure criterion.

## D8 — Alerts and dashboards

- Label parity (D4) means existing rules and dashboard selectors should survive unchanged; each rollout step's attended window **verifies rather than assumes**, and any re-key rides that window (alert pushes are attended per `capture-deploys.md`).
- The `Capture · log pipeline dead` dead-men transfer naturally: they alert on stream absence, and the streams keep their labels.
- The logs dashboard's line display becomes JSON; keyword search is unaffected; `| json` where field display is wanted.
- [[T0042]] updates in the closeout: the docker-socket residual **closes** (the socket is mounted into nothing); the engine-log-egress question remains open but changes shape — direct-ship changes the *how*, not the *whether*, and the new note records the write-only token in the engine's env.

## D9 — Testing (TDD; the harness proves itself before its verdicts count)

Unit tests against an in-process fake Loki (`http.server` on a loopback port), no new dependencies:

- Payload shape (streams/labels/values, ns timestamps) and basic-auth header, verified byte-level against the push-API contract.
- Batching: ≤500 lines per POST, 1 s flush cadence.
- Drop-on-full: ring at capacity evicts oldest, counter arithmetic exact, recovery WARNING carries the count.
- Capped backoff: failure schedule 1 s → 30 s, one in-flight batch, no retry multiplication.
- **The non-blocking guarantee, measured:** `emit()` latency bounded (µs-scale) while the endpoint is a black hole; the app thread never waits on the network.
- **Accept-then-silent:** a fake server that accepts the TCP connection and never reads nor responds — the POST unblocks within the per-operation timeout and the worker proceeds to backoff, not hang.
- **Proxy-env immunity:** with `http_proxy`/`https_proxy` pointing at a dead port, the POST still reaches the fake Loki directly — the explicit `ProxyHandler({})` opener is what is under test.
- Exit flush: completes under the 2 s deadline against both a live and a dead endpoint; remainder counted.
- Config: flag with missing env fails at startup with the exact error; env complete → handler attached alongside the untouched console handler.

## Out of scope

- The metrics path — Alloy keeps host metrics and remote_write untouched; this spec moves logs only.
- Any engine restart before the Stage-6a gate.
- Log-based alert redesign beyond continuity (D8's verify-and-re-key only).
- Grafana Cloud retention/usage tuning; the token is assumed provisioned by the owner at rollout (attended step).

## Cross-topic records (closeout obligations)

- [[T0089]] — this rollout recreates every wedged container; per-step positive-trace verification is the topic's closure criterion.
- [[T0042]] — socket residual closes; egress note updated (D8).
- [[T0020]] — this is observability-stack work; the topic's remaining core (app `/metrics` exporters) is untouched.
