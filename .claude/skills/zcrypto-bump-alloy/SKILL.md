---
name: zcrypto-bump-alloy
description: Roll a new Grafana Alloy image digest across the fleet's Alloy containers in canary order. Human-run only — invoke when a newer upstream release than the fleet pin exists.
disable-model-invocation: true
---

# zcrypto-bump-alloy

## What this is

The codified Alloy image bump. Seven hosts run digest-pinned `grafana/alloy` containers, all named `grafana-alloy`, all serving self-metrics on loopback `127.0.0.1:12345`, all logging via the journald driver. A bump is **telemetry-only**: on ops and the capture hosts Alloy is its own compose project, so a bump can never restart the liquidations poller or the unbackfillable capture daemon; on the NAS the apply also bounces `archive-pull` (unavoidable — the role restarts it on every apply). On the cache nodes Alloy is its own compose project as well, apart from Valkey's and Sentinel's, so a bump restarts neither. The `./alloy-data` volume preserves the remote_write WAL + Loki positions across replacement, so a bump does not re-ship the log backlog into the ingest quota.

**No canary bake is owed.** `fleet-deploys.md`'s canary rule is scoped to *capture-image* digests; an Alloy digest is not one. The bump's only hard clocks are alert windows: each host's `Fleet · Alloy dark` dead-man fires after `for: 10m` (+~5 m Prometheus staleness ≈ 15 m effective), and on **ops** the tighter clock is `zcrypto-hcio-watchdog` (~10 m total: `hc_checks_down_total` goes stale ~5 m after Alloy stops shipping, then `vector(999)` + `for: 5m`). Keep each host's dark window under ~8 minutes — normal replacement is seconds.

## Standing cautions (they all transfer)

- Never wrap `infra/ansible/scripts/converge.sh` in `timeout` (`.claude/rules/fleet-deploys.md`).
- Timeout-guard every network command; an empty filtered query is not an absent event — verify by positive trace.
- NAS docker is `/usr/local/bin/docker` (not on sudo's PATH).
- The converge mechanics — the `--check --diff` read, `converge.sh`'s confirm, the pins refusal, `.Config.Image`, the empty-`-e` trap, the STATE-record row, the prune order, verify-by-outcome, the render-only Alloy compose — are `zcrypto-rollout-image`'s *Converge mechanics* block: read it before Step 2.

## The seven hosts — three naming schemes, one map

| host | ssh alias | ansible `--limit` | Cloud `host=` label |
|---|---|---|---|
| ops node | `hp` | `zcrypto-ops` | `ops` |
| NAS | `nas` | `nas` | `nas` |
| cache node 1 | `db1` | `zcrypto-valkey1` | `zcrypto-valkey1` |
| cache node 2 | `db2` | `zcrypto-valkey2` | `zcrypto-valkey2` |
| cache node 3 | `db3` | `zcrypto-valkey3` | `zcrypto-valkey3` |
| capture secondary | `red` | `zcrypto-red` | `zcrypto-red` |
| capture primary | `zcrypto` | `zcrypto` | `zcrypto` |

(`up{host="hp"}` returns silence, not an error — query the Cloud label column only.)

An eighth Alloy runs on `zaccess` as an apt-followed deb — no digest, no pins row, outside this canary order (`docs/reference/fleet.md`'s Hosts bullet; `infra/runbooks/zaccess.md`'s `zaccess-alloy-converge`) — but inside Step 0's config-compatibility question, since the next `apt upgrade` hands it whatever upstream shipped; `Fleet · Alloy dark — Edge` is its detector.

## Step 0 — resolve the release, the digest, and the current baseline

1. Newest release: `timeout 30 gh api repos/grafana/alloy/releases/latest -q '.tag_name + " " + .published_at'`. **Read its release notes** (and any skipped intermediate versions') for config-language breaking changes/deprecations — the notes name the deprecation; only a dry-start against the real binary shows whether OUR configs trip it. If the notes flag config-language changes, dry-start the new image against each of the five `config.alloy` files (NAS `infra/nas/`, ops `roles/ops/files/`, capture `roles/capture/files/`, access `roles/access/files/`, cache `roles/cache/files/`) before touching any host, supplying dummy values for the `sys.env(...)` secrets.
2. Resolve the tag to its **multi-arch index digest**: `timeout 60 docker buildx imagetools inspect grafana/alloy:<tag>` → the top-level `Digest:` line (`sha256:…`). That full-index form is the pin (the current NAS pin is the same shape).
3. Record the **current baseline** before changing anything — the deployed digests live only on the hosts for 6 of 7 (per-converge extra-vars, no repo default): `docker inspect grafana-alloy --format '{{.Config.Image}}'` on `hp`, `nas`, `red`, `zcrypto`, `db1`, `db2`, `db3` — into `docs/reference/fleet-pins.md` (the durable record the *next* bump diffs against, and the rollback reference for this one) — `.Config.Image`, never `.Image` (the block).

## Step 1 — update the repo pins

- **NAS** (the only repo-resident pin): `infra/ansible/host_vars/nas/vars.yml` → `nas_alloy_image: grafana/alloy@sha256:<new>`.
- **ops + capture + cache**: deliberately no repo default (`ops_alloy_digest` / `capture_alloy_digest` / `cache_alloy_digest` are per-converge extra-vars; a converge without them *skips* the Alloy block — that skip is load-bearing, do not "fix" it by adding defaults). Their durable record is `docs/reference/fleet-pins.md`, updated at closeout with what was actually deployed.

## Step 2 — canary order: ops → NAS → cache nodes → capture secondary → capture primary

Telemetry-only, so the order optimizes for verification quality, not blast radius: ops first (fastest independent detectors: the hcio-watchdog and the 6 h `container="alloy"` log canary), NAS second (its apply bundles an archive-pull bounce — verify the pull loop, not just Alloy), the cache nodes third (their set holds nothing unbackfillable), one node per converge, as `converge.sh` refuses their group, then the capture hosts, primary last as always.

Between hosts: wait until the just-bumped host's verification (Step 3) is fully green. No timed bake beyond that.

**A host whose converge would deploy more than Alloy is HELD, and the bump carries on without it.** The converge preview (the block) names every file it would change, and a role that renders a script or an entrypoint can carry a change no Alloy pin implies. Holding a host means three things in the same breath: revert Step 1's pin for it so the repo's desired state matches what the host actually runs, give it its own row in `docs/reference/fleet-pins.md` carrying the old digest and the reason, and say in the commit message what the held converge would have deployed. The NAS is the standing case and its hazard is written where the runner works: `infra/ansible/host_vars/nas/vars.yml` carries the `--slice` constraint note immediately above the capture pin, three lines above the Alloy pin Step 1 edits.

### ops

```bash
cd infra/ansible
./scripts/converge.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<new> --check   # preview only
./scripts/converge.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<new>
# an EMPTY -e …_digest= renders a broken image ref (the block)
ssh hp 'cd /etc/zcrypto-ops/alloy && sudo docker compose up -d'   # role renders only — never starts
# sudo is REQUIRED on every host: alloy-secrets.env is 0600 zcrypto-alloy, so an unprivileged
# `up -d` dies with "permission denied" reading it — before touching the container, so the old one
# keeps running and no dark window opens.
```

### NAS

Pin already updated in Step 1; the apply also restarts `archive-pull` (every apply does).

```bash
./scripts/converge.sh site.yml --limit nas --tags nas --check   # preview only
./scripts/converge.sh site.yml --limit nas --tags nas -e nas_apply_compose=true   # up -d + restart alloy baked in
```

The `.env` render is `no_log`/`diff: false` (it carries a vaulted URL), so the pin change will NOT show in the diff — the changed-files report naming `.env` is the signal.

### cache nodes, `db1` then `db2` then `db3`

`cache_alloy_digest` alone: without `cache_image_digest` the cache role skips its Valkey and Sentinel block, so the bump leaves both daemons as they run.

```bash
ssh db1 "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"
./scripts/converge.sh site.yml --limit zcrypto-valkey1 --tags cache -e 'cache_alloy_digest=sha256:<new>'
ssh db1 'cd /opt/zcrypto-cache/alloy && sudo docker compose up -d'   # the role renders it and does not start it
ssh db1 "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"   # the same two lines
```

Then `db2` (`zcrypto-valkey2`) and `db3` (`zcrypto-valkey3`) the same way, in that order.

### capture secondary, then primary

Pass the **currently-running capture digest** — read it with `ssh red 'sudo docker inspect zcrypto-capture --format {{.Config.Image}}'` and take the `sha256:…` part after the `@` (`.Config.Image`, never `.Image`) — so the capture-compose render stays `changed=false` and its `restart capture service` handler never fires. Passing any other value restarts unbackfillable capture — that is the whole trap.

```bash
# secondary
./scripts/converge.sh site.yml --limit zcrypto-red \
  -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<new>   # previews, then typed confirm
ssh red 'cd /etc/zcrypto-capture/alloy && sudo docker compose up -d'   # role renders only — never starts

# primary — converge_primary is required; --skip-tags engine satisfies site.yml's un-tagged-run refusal.
# Never answer that refusal with -e engine_image_digest: it restarts the LIVE trade engine.
# It also converges cache_link (site.yml's engine play, tag cache-link): a changed zcache0.conf restarts the primary's wg-quick@zcache0, which carries no engine traffic yet.
./scripts/converge.sh site.yml --limit zcrypto --skip-tags engine -e converge_primary=true \
  -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<new>   # previews, then typed confirm
ssh zcrypto 'cd /etc/zcrypto-capture/alloy && sudo docker compose up -d'
```

## Step 3 — verify each host before moving to the next

Container first, on the host:

```bash
docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'
# img == grafana/alloy@<the new digest>, restarts == 0   (.Config.Image, not .Image — see Step 0)
```

Shipping health — **only readable on the host** (`127.0.0.1:12345`; none of these counters is admitted to Cloud):

```bash
curl -s http://127.0.0.1:12345/metrics | grep -E \
  '^prometheus_remote_storage_samples_(failed_total|pending|total)|^loki_write_(sent|dropped)_entries_total'
# failed_total 0, pending 0, samples_total CLIMBING on a second read; sent_entries >= 1, dropped 0
# Leave >60 s between reads and >60 s after the recreate: the scrape interval is 60 s, so a fresh
# container legitimately reports samples_total=0 until its first scrape lands. `pending` briefly
# non-zero is in-flight, not failure — only `failed_total` matters.
```

In Cloud, per host (the positive traces the alert stack itself keys on):

- `count(up{host="<host>"}) >= 1` and the host's `Fleet · Alloy dark` rule back to **Normal** — the canonical proof.
- A **fresh** Loki line for the host — proves the whole journald → `loki.source.journal` → parse → write path end-to-end. (verify end-to-end, not at endpoints: a metric on `:12345` plus a keep-list admitting it does not mean the path between them exists.) **Do not filter on `container="alloy"` in a short window**: Alloy logs at startup and then goes quiet, so `{host=…, container="alloy"}` over 15 m reads empty on a perfectly healthy host that was bumped 30 min ago. Query `{host="<host>", level=~".+"}` (any container) for the liveness proof, and widen to 60 m if you specifically want Alloy's own startup lines.
- The `process_*` families present for the host (the capture, ops and NAS keep-lists admit six, a cache node's two; `tests/test_infra_alloy_series.py` is the authoritative per-host series checklist — read `NAS_REQUIRED` / `OPS_REQUIRED` / `CAPTURE_REQUIRED` there rather than trusting any list copied here).

Host-specific additions:

- **ops**: `zcrypto-hcio-watchdog` back to Normal (it races you); `up{job="liquidations_app"} == 1` (poller untouched, still scraped).
- **NAS**: the next `archive-pull` cycle logs `pull complete … failed=0` for every verified channel (the apply bounced it); `zcrypto_gate_*` series still arriving (the NAS unix exporter's textfile collector scrapes `/textfile/gate.prom`).
- **capture hosts**: `up{job="capture_app"} == 1`; capture container `RestartCount` unchanged and its newest parquet still advancing (`sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | wc -l` > 0) — proving the bump really did not touch the daemon. `up{job="engine_app"}` is a valid check only on the primary; on the secondary it reads 0 permanently by design.
- **cache nodes**: the node's series list is `CACHE_REQUIRED`; `redis_up{host="<host>"}` reads 1 on two series, `job="valkey"` and `job="sentinel"`; the leg's two `docker inspect` reads print the same lines, proving the bump did not touch Valkey or Sentinel.

**Expect `Fleet · a daemon restarted` (`zcrypto-fleet-daemon-restarted`, `job="integrations/self"`) once per host, ~2–3 min after each recreate** — Alloy's own `process_start_time_seconds` moved, and that rule is the bump's own record in the channel; it self-clears within 15 min and needs nothing. A firing that outlives the 15 minutes, or clears and returns with no bump, is a crash loop — under a restart loop `changes(process_start_time_seconds[15m])` never empties, so the instance stays firing rather than firing a second time. The rule selects no cache node, so a cache node's recreate pages nothing.

**Expect `Ops · ERROR logs` to fire on the ops bump, ~35 s after the recreate.** The OUTGOING container logs two `service=remotecfg … err="noop client"` errors as it shuts down (remote config is unused here, so there is nothing to unregister from). The rule's container enumeration includes alloy, with `for: 0s` over a 15 m window, so it fires on the old container's dying breath and self-clears ~15 min later. Confirm it is that and not something real: the lines are timestamped ~200 ms BEFORE the new container's `StartedAt`, and `docker logs grafana-alloy` on the new one shows zero errors. Only ops's ERROR rule enumerates the alloy container; the other six recreates trip nothing.

If a `Fleet · Alloy dark` or exporter-stale page fires because a window ran long: it self-resolves once `up` returns; note it in the Slack thread rather than silencing anything.

## Rollback

Re-pin the previous digest (Step 0's baseline record) and repeat the same converge + `up -d` for the affected host. The `alloy-data` WAL/positions survive both directions; journal readers resume from their cursor (window: `max_age = 48h` — an outage longer than that loses the older journal tail, another reason not to park a half-done bump).

## Closeout

- `docs/reference/fleet-pins.md`: each reached host's alloy row — digest, version, `since` from its `.State.StartedAt`, operand — re-trued per the block. A NAS leg also re-trues `archive-pull | nas`'s `since` from that container, its digest unchanged.
- The prune (the block) is owed once per host the bump actually reached — each after its own row lands.
