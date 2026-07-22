# Log-shipping rework — direct-ship from the app, docker.sock retired (iter-116)

**Status:** designed and approved in the attended 2026-07-22 brainstorming session; every decision below was made explicitly by the owner.

## Goal

Retire the docker-socket log path fleet-wide. Today every long-lived container's stdout reaches Grafana Cloud via Alloy reading `/var/run/docker.sock` — a root-equivalent credential on internet-facing hosts (the capture role's own comment calls it "a known, accepted residual") and the substrate of the [[T0089]] reader-wedge class (six containers went log-dark for a day; the NAS's GET-only socket proxy was removed 2026-07-14 for severing this same stream every 10 minutes). After this spec: the Python CLI ships its own logs, nothing mounts the socket, and the wedge class is unrepresentable: docker rotates its own log files by rename with rotation-aware readers, and the one remaining follower — the attached `zcrypto-capture.service` stdout stream, which doubles capture's lines into its unit journal — is dockerd's own machinery, not a foreign process holding state across a foreign rotation.

## D1 — Transport: direct-ship from the app (approach A)

The CLI gains an opt-in shipping sink that POSTs its own log records to Grafana Cloud Loki's push API. Four approaches were evaluated:

- **A. Direct-ship from the app — chosen.** No socket, no Alloy in the CLI log path (survives Alloy down/wedged/restarting), fewest moving parts, works on hosts with no Alloy. Costs accepted knowingly: Loki write credentials in app-container env (D5 bounds this to a write-only token), crash loses the in-flight ring (D2 makes stdout the local ground truth), the app owns ~150 lines of retry/batching (D9 tests them).
- **B. journald log driver for every container, Alloy tails the journal — rejected.** Keeps Alloy as the single log-path intermediary and keeps regex level-extraction alive, contradicting both stated goals.
- **C. App pushes to a localhost Alloy receiver (`loki.source.api`) — rejected.** Best credential isolation, but reintroduces the dependency this rework removes: logs stop flowing whenever local Alloy is down, the T0089/T0048 failure neighborhood.
- **D. App writes JSON to a host-mounted file, Alloy tails it (`loki.source.file` + `stage.json`) — rejected, and recorded as the designated fallback.** Strictly better loss envelope (disk-durable + Alloy WAL) and credential isolation, both explicitly waived by the owner. Rejected on the file-lifecycle argument: T0089's root cause was two processes coordinating over a rotating file (writer rotates, reader holds state), and D rebuilds that shape — better primitives, same failure class, on hosts where disk is also watermark-sensitive ([[T0032]]). A also wins on failure visibility: its drops are self-announcing (D3), where a wedged tail in D is silent in precisely the T0089 way. **Fallback trigger:** if the creds-in-env decision or the bounded-loss envelope hardens the other way (e.g. at go-live), D is the successor; the app-side dual-sink work transfers unchanged.

## D2 — stdout is unchanged and remains the local ground truth

The default behavior is untouched: plain-text stdout, exactly today's format. The `--ship-logs` switch is **additive** — it never silences or reformats the console. Consequences, in order:

- Docker's json-file driver keeps capturing stdout under the existing per-container caps for the CLI containers (50m/5 on capture and the engine, 10m/3 on the poller) — nothing new to configure. (The journald-driver containers of D6 have no json.log at all; journald owns their rotation, and `docker logs` still reads them back.)
- **Docker engine becomes the sole owner of that file's lifecycle.** It rotates by rename (reader-safe), the copytruncate logrotate policy is already purged fleet-wide (T0089), and after this spec no *foreign* process reads those files — Alloy's docker source is gone; what remains is dockerd's own rotation-aware follower serving the attached `zcrypto-capture.service` stdout (whose journal twin stays excluded from the journal pipeline to avoid double-ingest) and ad-hoc human `docker logs`. Single writer, single rotator, no cross-process file-lifecycle coordination: the wedge needed a foreign reader, and there is none.
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
- On POST failure: **transport errors, 5xx and 429 are retriable** — hold that one batch (part of the fixed memory bound) and retry with capped backoff 1 s → 30 s; the ring keeps absorbing and dropping meanwhile; retries never multiply (one in-flight batch, one backoff clock). **Any other 4xx is non-retriable: the batch is dropped and counted, announced on the next success.** The case that forces this (cold review): after an outage longer than Loki's out-of-order window (~2 h on Grafana Cloud), the held batch's honest timestamps are rejected with 400 on every retry — retry-forever would wedge shipping permanently and silently, the exact class this spec exists to kill.
- On recovery after any drops: emit one WARNING — to stdout *and* shipped — `log shipping recovered; N lines dropped while unreachable`. A shipping failure is self-announcing; no silent dark window.
- At process exit: flush with a **2 s hard deadline** (daemon thread + atexit), then drop the remainder and report the count to stdout. A one-shot CLI run against a dead Loki is delayed ≤2 s, never hung.
- **Two limits on the self-announcement, and why neither is the safety net** (found by the Task-2 review): (i) a **permanently rejecting endpoint** — a revoked or mistyped token 401/403s every batch, so each is dropped and the recovery WARNING, which fires only on success, never fires; (ii) at `--log-level ERROR` the WARNING is below threshold and is suppressed outright. In both cases stdout is untouched and `close()` still prints the unshipped count to stdout directly, bypassing the logging level. **The actual detector for "logs stopped arriving" is the fleet's own dead-man rules** — `Ops · log pipeline dead` and `Capture · log pipeline dead` (primary and secondary) alert on stream ABSENCE in Loki, whatever the cause, which is exactly the T0089 shape they were built for. So the division of labor is: the app-side announcement is a best-effort convenience that explains *what* was lost when shipping resumes; the dead-man rules are what guarantee someone finds out *that* it stopped. Stated here so a future reader does not mistake the convenience for the guarantee.
- The extreme case in the owner's own words — "the remote logs server is down, our application should still run seamlessly" — costs exactly: one 4096-slot ring, one sleeping thread, one bounded retry timer.

## D4 — Labels and line format: no regex anywhere

- Loki labels: `{host, container, level}` — all low-cardinality. `level` comes from `record.levelname` at the source; **no regex exists anywhere in this path, at ingest or at query**.
- Entry timestamp: `record.created` (true event time, ns-denominated on the wire; float64 epoch precision is ~hundreds of ns — ordering jitter, not a correctness issue). Grafana Cloud Loki accepts out-of-order entries within its window, so retried batches land with honest timestamps.
- The line is the existing, tested `JsonLineFormatter` output verbatim: ts, level, logger, file, line, message, user extras, exception with traceback embedded in the same entry. Keyword search operates on the line; field access at query time is `| json` — a parser, not a regex.
- Dashboard contract (the owner's acceptance bar): filter by host, container, level; keyword search. Label values keep today's scheme (`container` ∈ {capture, engine, liquidations, alloy, …}, `level` uppercase), so existing dashboards and alert rules key on identical selectors.

## D5 — Config surface and credentials

- `--ship-logs` boolean flag in the root callback, beside `--log` / `--log-level`. Applies to any subcommand; only the long-lived service units/compose files pass it (capture, engine, poller). Ops ephemerals and host oneshots stay on the journal path — no change.
- Identity and credentials from env, rendered per host by Ansible: `ZCRYPTO_LOKI_URL`, `ZCRYPTO_LOKI_USERNAME`, `ZCRYPTO_LOKI_PASSWORD`, plus `ZCRYPTO_LOG_HOST` and `ZCRYPTO_LOG_SERVICE` (a container reliably knows neither the host's name nor its compose service name; the compose files do).
- **`ZCRYPTO_LOG_HOST` renders today's exact label values, not the machine hostname**: `{{ base_hostname }}` on the capture hosts (= `zcrypto` / `zcrypto-red`, matching their Alloys' `constants.hostname`), and the **literal `ops` / `nas`** elsewhere — those two hosts' Alloys apply static relabels today, and the ops alert rules hardcode `host="ops"` (the poller ERROR rule is "the only error signal" for it, its own summary says). Label continuity means zero rule re-keying (cold-review C1/I2; re-keying was considered and declined as churn for no gain).
- **One shared logs:write-only token** for the whole fleet — vaulted as `logship_loki_token` in `group_vars/observed/vault.yml` (**created 2026-07-22**, Grafana Cloud access policy `zcrypto-app-logship`, scope `logs:write` only), rendered into a root-owned 0600 env file consumed via compose `env_file`, the exact `alloy-secrets.env` pattern. Distinct from Alloy's `grafana_loki_token` so the app's push can be revoked without blinding fleet telemetry, and the two identities are attributable separately in Grafana Cloud. Only the **token** is new: the push URL and username are stack properties, rendered from the existing `grafana_loki_url` / `grafana_loki_user`. A leak means log-spam/poisoning ability, not read access; revocation = rotating one token. Per-host/per-service tokens were considered and rejected as key sprawl at this fleet size.
- `--ship-logs` with missing env = **hard error at startup** — a deploy bug fails fast at converge/first start, it does not ship silence. Loki being unreachable at runtime is never an error (D3).
- **Vault-gating covers both sides of the render** (cold-review I4): the compose `env_file` reference and `ZCRYPTO_SHIP_LOGS` are wrapped in the same `logship_loki_url is defined` conditional as the secrets render task. A converge landing between the merge and the attended vault step must leave the capture container fully restartable — an unbackfillable host never carries a latent can't-start state.
- This puts a Grafana Cloud credential in the capture/engine container env on the trade-key host for the first time — decided explicitly, bounded to write-only scope, and recorded in [[T0042]]'s egress note (D8).

## D6 — Fleet end-state: three transport rules, zero socket consumers

| Workload | Transport |
|---|---|
| Python CLI containers (capture ×2, engine, liquidations poller) | direct-ship (D3) + plain stdout to the local json.log |
| Non-CLI long-lived containers (Alloy ×4: zcrypto, zcrypto-red, ops, NAS; NAS `zcrypto-archive-pull`) | `logging: driver: journald` → host journal → Alloy journal pipeline |
| Host oneshots (capture-prune, ops ephemeral `zcrypto-*` jobs) | journal → Alloy journal pipeline (unchanged) |

- Deleted on all four Alloys: the `- /var/run/docker.sock:...` bind-mount, the docker-group `group_add` that exists only to open it (on the NAS that entry is `group_add: ["0"]` — root gid, present solely for the socket; it goes too — cold-review I3), and the `discovery.docker` + `loki.source.docker` components that dial it. The socket itself is untouched — it is dockerd's own API endpoint; host tooling and every container are unaffected.
- All four Alloys ship **their own** logs via the journald driver: keep-rules widen to `CONTAINER_NAME=grafana-alloy` (journal field `__journal_container_name`), relabeled `container="alloy"` as today. Level extraction moves to `stage.logfmt` (+ the warn→WARNING / fatal→CRITICAL template), selected by plain `{container="alloy"}` equality — the old line-match selector regex goes too. The line ships **unmodified**: no `stage.output` rewrite, so the trailing logfmt attributes today's template reassembles are simply kept, and a non-logfmt line (panic, traceback) passes through unleveled rather than mangled. Uniform on all four Alloys. The journald driver takes effect on container recreation, which the rollout performs anyway.
- The zcrypto parse stage is deleted **only where the docker path died with nothing left to feed it** — the capture hosts, whose journal carries just the prune unit's bash lines and Alloy's logfmt. It **stays, scoped to the journal path, on ops and the NAS** (cold-review C2): the ops oneshot units and the NAS `archive-pull` wrapper ship Python-*shaped* lines through the journal — the wrapper deliberately mimics the CLI's line shape so it can still log when the Python process inside is killed, "which is precisely when someone needs to know" (its own header comment) — and deleting their parse would strip `level` and permanently blind the rules keyed on it. The honest principle: **the direct-ship path is regex-free; the journal path keeps its one ingest parse.**
- **NAS caveats, measured 2026-07-22 (they falsified a prior):** DSM 7 runs systemd with a live journald (PID 1 = systemd; journalctl reads entries as root), so the journald treatment works there — but the journal is **volatile** (`/run/log/journal/<machine-id>/` populated, `/var/log/journal/` empty), so a NAS reboot loses any unshipped tail; and the NAS Alloy has **no journal pipeline today** — it is a first-time build there (journal source + relabel + the volatile-path mounts `/run/log/journal` + `/etc/machine-id`). The rollout probes the driver with a throwaway container (`docker run --rm --log-driver=journald …`) **before** touching `zcrypto-archive-pull` — custody discipline: the pull container is never the experiment.
- Division of labor, stated: a dead Alloy cannot ship its own death (true on the old path too); Alloy **liveness** belongs to the metrics-side `Fleet · Alloy dark` rules, Alloy **content** to the journal path. No feedback loop: Alloy logs one error per backoff-limited failed push; self-scraping them does not amplify.

## D7 — Rollout: attended, canary-disciplined, and T0089's recovery vehicle

Ordered steps, each verified by a **positive line arriving in Loki** (the T0089 lesson: never verify by absence), with the Alloy-dark and log-dead-man rules watching throughout:

1. **ops** — poller (new image + flag) and Alloy (journald driver) recreated. First live verification of both new paths; clears the poller's wedge.
2. **NAS** — journald-driver probe with a throwaway container first (`docker run --rm --log-driver=journald …`, write-side only); **then a READ probe as the Alloy uid before recreating anything** (review finding, 00068 T6/T7/T8 review Important 4 — the write-side probe alone would have passed while the read side was silently broken): `docker run --rm --user 1031:19 -v /run/log/journal:/host/journal:ro alpine ls /host/journal/` must list the machine-id dir. Then Alloy (with the `group_add: ["19"]` DSM read grant) + `zcrypto-archive-pull` to journald driver, recreated.
3. **Alert-push gate** — do not run `infra/scripts/grafana-push.sh` with pruning enabled (`GRAFANA_PRUNE=1`) until ops and NAS (steps 1-2) have converged and their `discovery.docker` is actually gone. The script's orphan-prune is scoped to the alert folder, and `zcrypto-alloy-docker-sd-wedged` is already absent from `alerts.yaml` (D8) — a pruning push run any earlier, for any unrelated rule change, deletes it fleet-wide while ops/NAS still run `discovery.docker`, leaving nothing to detect that wedge there. Until ops/NAS converge, the live rule staying in Grafana on all four hosts costs nothing; a push needed sooner for an unrelated rule is a conscious, bounded acceptance.
4. **Secondary capture** — new image + flag; **24 h bake per the canary rule** (`capture-deploys.md`); clears its wedge.
5. **Primary capture** — after the bake, `-e converge_primary=true`; clears the last capture wedge.
6. **Engine** — flag added only **after the Stage-6a gate** (earliest ~2026-07-25); a mid-soak restart remains forbidden.

Deploying the new capture image recreates the capture containers, which is the only demonstrated fix for the existing T0089 wedges — this rollout is that topic's recovery vehicle, and its per-step positive-trace verification is T0089's own closure criterion.

## D8 — Alerts and dashboards

- Label parity (D4) means existing rules and dashboard selectors should survive unchanged; each rollout step's attended window **verifies rather than assumes**, and any re-key rides that window (alert pushes are attended per `capture-deploys.md`).
- The `Capture · log pipeline dead` dead-men transfer naturally: they alert on stream absence, and the streams keep their labels.
- The logs dashboard's line display becomes JSON; keyword search is unaffected; `| json` where field display is wanted.
- **`zcrypto-alloy-docker-sd-wedged` retires with its subject** (cold-review): deleting `discovery.docker` fleet-wide ends the `prometheus_sd_*` series the T0048-defect-1 rule watches, leaving it permanently NoData. The rule is removed from `alerts.yaml` in the same change (repo edit now, provisioning push attended), and the two `prometheus_sd_*` entries leave every metrics keep-list plus their pins in `tests/test_infra_alloy_series.py` — a keep-list entry for a series that cannot exist is exactly the admitted-but-unpublished trap T0051 recorded.
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
- **App-level `/metrics` endpoints — a separate iteration (00069), sharing this one's rollout.** [[T0020]]'s remaining core is its own nameable component, and its design has open questions this spec must not reopen (a `/metrics` endpoint serves only long-lived processes, so the file-based textfile path survives for the oneshot jobs — "replace file-based metrics" is true of the daemon half only; plus inventory, bind address on the trade-key host, scrape wiring, series budget, and a possible first runtime dependency). **The rollout discipline that makes two iterations cost one deploy:** do not start the capture/ops/engine rollout between the two merges — land 00068, land 00069, then roll out ONE capture image carrying both, with ONE canary bake and ONE post-gate engine restart. Merges and converges are already decoupled here (`capture-deploys.md`), so this costs nothing but sequencing.

## Cross-topic records (closeout obligations)

- [[T0089]] — this rollout recreates every wedged container; per-step positive-trace verification is the topic's closure criterion.
- [[T0042]] — socket residual closes; egress note updated (D8).
- [[T0020]] — this is observability-stack work; the topic's remaining core (app `/metrics` exporters) is untouched.
