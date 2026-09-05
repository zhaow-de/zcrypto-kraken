---
name: zcrypto-bump-alloy
description: Roll a new Grafana Alloy image digest across the fleet's four Alloy containers (ops, NAS, capture secondary, capture primary) in canary order, with per-host verification and rollback. Human-run only — invoke when a newer upstream release than the fleet pin exists.
disable-model-invocation: true
---

# zcrypto-bump-alloy

## What this is

The codified Alloy image bump. Four hosts run digest-pinned `grafana/alloy` containers, all named `grafana-alloy`, all serving self-metrics on loopback `127.0.0.1:12345`, all logging via the journald driver. A bump is **telemetry-only**: on ops and the capture hosts Alloy is its own compose project, so a bump can never restart the liquidations poller or the unbackfillable capture daemon; on the NAS the apply also bounces `archive-pull` (unavoidable — the role restarts it on every apply). The `./alloy-data` volume preserves the remote_write WAL + Loki positions across replacement, so a bump does not re-ship the log backlog into the ingest quota.

**No canary bake is owed.** `fleet-deploys.md`'s canary rule is scoped to *capture-image* digests; an Alloy digest is not one (same distinction as the codified pair-list bullet there). The bump's only hard clocks are alert windows: each host's `Fleet · Alloy dark` dead-man fires after `for: 10m` (+~5 m Prometheus staleness ≈ 15 m effective), and on **ops** the tighter clock is `zcrypto-hcio-watchdog` (~10 m total: `hc_checks_down_total` goes stale ~5 m after Alloy stops shipping, then `vector(999)` + `for: 5m`). Keep each host's dark window under ~8 minutes — normal replacement is seconds.

## Prerequisite

**Converge only from a tree whose rendered config matches the fleet** — a stale tree silently reverts deployed config (the deploy-tree hazard); `--check --diff` before every apply.

## Standing cautions (they all transfer)

- Converges via `infra/ansible/scripts/converge.sh` — requires `--limit`, shows the `--check --diff` preview, takes a typed confirm (preview-only: pass `--check`); **never wrap it in `timeout`** (it is attended by design, and `timeout` orphans the running `ansible-playbook` child). **Never** `ansible-inventory --host/--list` (prints the vault, incl. the live trade key).
- Timeout-guard every network command; an empty filtered query is not an absent event — verify by positive trace.
- `converge.sh` appends every real pass to `docs/reference/deploy-log.jsonl` — the Alloy digest you passed is on record the moment the pass returns; the `fleet-pins.md` row at closeout is re-trued from that line, never re-typed.
- NAS docker is `/usr/local/bin/docker` (not on sudo's PATH); the NAS play refuses on a non-UTC clock (`tags: [always]` guard).
- **Read the `--check --diff` output before every converge, and stop on any diff you did not intend.** The capture-role converge re-renders the *capture* compose too: if that render shows changes beyond your intent, the tree you are deploying from has drifted against the hosts (hosts deployed from an unmerged branch make a develop-based converge silently revert it). Reconcile first; never converge through an unexplained diff.

## Shared converge mechanics

This block is duplicated verbatim in `zcrypto-rollout-image` and `zcrypto-bump-alloy` — deliberately, so neither skill depends on the other being loaded. Edit both.

- Converge via `infra/ansible/scripts/converge.sh` — it requires `--limit`, runs and displays the `--check --diff` preview, and takes a typed confirm of the limit value before the real pass (`run.sh` underneath loads the vaulted deploy key; preview-only: pass `--check`). `--limit` is mandatory for ops too: a bare `site.yml` still runs the NAS play; `converge.sh` refuses the bare form.
- Digests come from `docs/reference/fleet-pins.md` — the roles refuse to replace a running digest the file does not record (`-e pins_override="<reason>"` bypasses). Pull the digest on the host first: every runner is `--pull never`, and every role's digest preflight refuses a digest the host has not pulled.
- **Read a running image's digest from the container, never from the compose file** — `docker inspect --format '{{.Config.Image}}' <name>` (`{{.Image}}` is host-dependent and lies under classic storage): a compose file can pin the wrong image while the container runs the right one, and the mistake fires at the next `docker compose up`.
- **A `config.alloy` edit makes Alloy the subject**: pass the currently-running Alloy digest (`capture_alloy_digest` / `ops_alloy_digest`) or the drift assert refuses the converge; omit the flag entirely otherwise — an EMPTY `-e …_digest=` still counts as defined and renders a broken image ref. The drift assert compares the deployed file, not what the running container loaded, so a converge that never recreates the container passes every assert while a new family stays dark: **a new metric family needs the host's keep-regex edit and a first scrape verified by VALUE** — `uv run python infra/scripts/grafana-query.py '<family>{host="<host>"}'`; `(no series)` is FAIL, never a zero.
- A `daemon.json` diff refuses to apply without `-e daemon_json_ack=true` — the docker role renders to a probe path and shows the diff before asking (its handler bounces Alloy and the poller); the role is shared, so the ack gates every host.
- **`fleet-pins.md` is a STATE record.** `converge.sh` appends every real pass to `docs/reference/deploy-log.jsonl`; re-true the row from that line — never from memory — commit the line with the row, and put the converge's evidence (every check read, the values quoted) in the commit message, never in the file — a row is its cells plus ONE clause of payload, and `infra/scripts/prose-tripwire.py` flags a longer one. `git log --follow` on the file is the deploy chronicle.
- **Images are removed only by `uv run python infra/scripts/prune-host-images.py <host>`, then `--apply`, after that host's new pins row is written and only for the host that just converged** — a capture host stops appending at 1 GiB free; nothing distinguishes a pre-staged image from a stale one, so `--keep <digest12>` anything staged for a leg still to come.
- Verify by outcome, never by exit code. Ops: `infra/scripts/ops-postverify.sh`, every check in one command. Capture: on the pulled copy, every book stream's `<HH>.parquet` begins where the other host's does (identical first rows), not at a fixed `:00:00.0x`; the NAS pull's next cycle reports `failed=0` (that IS the manifest verification — fresh segments are hash-verified on arrival, and whole-archive coverage completes within 24 pull cycles under the incremental hash scope); `infra/scripts/continuity.py` on a pulled copy, never the live dir, shows no new truncated hours. Engine: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`; the restart marker is the container's `.State.StartedAt`, never the converge command's return time.
- **The ops and capture roles RENDER the Alloy compose file and never restart the container for it** — `render the alloy compose file` carries no `notify:` at all, and even the `config.alloy` render's `reload alloy` handler is an HTTP `POST /-/reload` that never re-reads container env or `memory:` (its own comment says the same about `alloy-secrets.env`). A change to Alloy's `environment` or `memory:` (a cap, GOMEMLIMIT, …) therefore needs `sudo docker compose up -d` in `/etc/zcrypto-ops/alloy` or `/etc/zcrypto-capture/alloy` after the converge — verify on the container: `.State.StartedAt` postdates the render, plus a SCOPED `docker exec grafana-alloy sh -c 'echo $GOMEMLIMIT'` and `docker inspect --format '{{.HostConfig.Memory}}' grafana-alloy` — never `docker inspect --format '{{json .Config.Env}}'`, which prints the Grafana Cloud credentials. No metric-side proof exists: `config.alloy` drops `go_.*` and the keep-list does not re-admit `go_gc_gomemlimit_bytes`.

## The four hosts — three naming schemes, one map

| host | ssh alias | ansible `--limit` | Cloud `host=` label |
|---|---|---|---|
| ops node | `hp` | `zcrypto-ops` | `ops` |
| NAS | `nas` | `nas` | `nas` |
| capture secondary | `red` | `zcrypto-red` | `zcrypto-red` |
| capture primary | `zcrypto` | `zcrypto` | `zcrypto` |

(`up{host="hp"}` returns silence, not an error — query the Cloud label column only.)

## Step 0 — resolve the release, the digest, and the current baseline

1. Newest release: `timeout 30 gh api repos/grafana/alloy/releases/latest -q '.tag_name + " " + .published_at'`. **Read its release notes** (and any skipped intermediate versions') for config-language breaking changes/deprecations — the notes name the deprecation; only a dry-start against the real binary shows whether OUR configs trip it. If the notes flag config-language changes, dry-start the new image against each of the three `config.alloy` files (NAS `infra/nas/`, ops `roles/ops/files/`, capture `roles/capture/files/`) before touching any host, supplying dummy values for the `sys.env(...)` secrets.
2. Resolve the tag to its **multi-arch index digest**: `timeout 60 docker buildx imagetools inspect grafana/alloy:<tag>` → the top-level `Digest:` line (`sha256:…`). That full-index form is the pin (the current NAS pin is the same shape).
3. Record the **current baseline** before changing anything — the deployed digests live only on the hosts for 3 of 4 (per-converge extra-vars, no repo default): `docker inspect grafana-alloy --format '{{.Config.Image}}'` on `hp`, `nas`, `red`, `zcrypto` — into `docs/reference/fleet-pins.md` (the durable record the *next* bump diffs against, and the rollback reference for this one). **Always `.Config.Image` (the `repo@sha256:…` compose asked for), never `.Image`** — the latter equals the pinned digest only under docker's containerd image store (the capture VPSes), and is the local config-blob ID under classic storage (the NAS): a host-dependent trap.

## Step 1 — update the repo pins

- **NAS** (the only repo-resident pin): `infra/ansible/host_vars/nas/vars.yml` → `nas_alloy_image: grafana/alloy@sha256:<new>` — and add/refresh the adjacent comment with the Alloy **version and publish date**.
- **ops + capture**: deliberately no repo default (`ops_alloy_digest` / `capture_alloy_digest` are per-converge extra-vars; a converge without them *skips* the Alloy block — that skip is load-bearing, do not "fix" it by adding defaults). Their durable record is `docs/reference/fleet-pins.md`, updated at closeout with what was actually deployed.

## Step 2 — canary order: ops → NAS → capture secondary → capture primary

Telemetry-only, so the order optimizes for verification quality, not blast radius: ops first (fastest independent detectors: the hcio-watchdog and the 6 h `container="alloy"` log canary), NAS second (its apply bundles an archive-pull bounce — verify the pull loop, not just Alloy), then the capture hosts, primary last as always.

Between hosts: wait until the just-bumped host's verification (Step 3) is fully green. No timed bake beyond that.

### ops

```bash
cd infra/ansible
./scripts/converge.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<new> --check   # preview only
./scripts/converge.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<new>
# NB an EMPTY -e ops_alloy_digest= still counts as defined and renders a broken image ref —
# the same footgun as capture_alloy_digest below; pass a real digest or omit the flag entirely.
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

### capture secondary, then primary

Pass the **currently-running capture digest** — read it with `ssh red 'sudo docker inspect zcrypto-capture --format {{.Config.Image}}'` and take the `sha256:…` part after the `@` (never `{{.Image}}`: correct only under the containerd image store, a config-blob ID elsewhere) — so the capture-compose render stays `changed=false` and its `restart capture service` handler never fires. Passing any other value restarts unbackfillable capture — that is the whole trap.

```bash
# secondary
./scripts/converge.sh site.yml --limit zcrypto-red \
  -e capture_image_digest=<current running capture digest> -e capture_alloy_digest=sha256:<new>   # previews, then typed confirm
ssh red 'cd /etc/zcrypto-capture/alloy && sudo docker compose up -d'   # role renders only — never starts

# primary — converge_primary is required, and --skip-tags engine is LOAD-BEARING
# (bare --limit zcrypto pulls in the engine play, whose digest assert fails the host closed;
#  "fixing" that with -e engine_image_digest would restart the LIVE trade engine)
./scripts/converge.sh site.yml --limit zcrypto --skip-tags engine -e converge_primary=true \
  -e capture_image_digest=<current running capture digest> -e capture_alloy_digest=sha256:<new>   # previews, then typed confirm
ssh zcrypto 'cd /etc/zcrypto-capture/alloy && sudo docker compose up -d'
```

Note `-e capture_alloy_digest=` with an **empty** value counts as *defined* and renders a broken `image: grafana/alloy@` — pass a real digest or omit the flag entirely.

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
- The six `process_*` families present for the host (the keep-lists admit exactly six; `tests/test_infra_alloy_series.py` is the authoritative per-host series checklist — read `NAS_REQUIRED` / `OPS_REQUIRED` / `CAPTURE_REQUIRED` there rather than trusting any list copied here).

Host-specific additions:

- **ops**: `zcrypto-hcio-watchdog` back to Normal (it races you); `up{job="liquidations_app"} == 1` (poller untouched, still scraped).
- **NAS**: the next `archive-pull` cycle logs `pull complete … failed=0` (the apply bounced it); `zcrypto_gate_*` series still arriving (the NAS unix exporter's textfile collector scrapes `/textfile/gate.prom`).
- **capture hosts**: `up{job="capture_app"} == 1`; capture container `RestartCount` unchanged and its newest parquet still advancing (`sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | wc -l` > 0) — proving the bump really did not touch the daemon. `up{job="engine_app"}` is a valid check **only on the primary and only after the engine flip**; on the secondary it reads 0 permanently by design.

**Expect `Fleet · a daemon restarted` (`zcrypto-fleet-daemon-restarted`, `job="integrations/self"`) once per host, ~2–3 min after each recreate** — Alloy's own `process_start_time_seconds` moved, and that rule is the bump's own record in the channel; it self-clears within 15 min and needs nothing. A second firing on the same host with no bump is a crash loop.

**Expect `Ops · ERROR logs` to fire on the ops bump, ~35 s after the recreate.** The OUTGOING container logs two `service=remotecfg … err="noop client"` errors as it shuts down (remote config is unused here, so there is nothing to unregister from). The rule's container enumeration includes alloy, with `for: 0s` over a 15 m window, so it fires on the old container's dying breath and self-clears ~15 min later. Confirm it is that and not something real: the lines are timestamped ~200 ms BEFORE the new container's `StartedAt`, and `docker logs grafana-alloy` on the new one shows zero errors. Only ops's ERROR rule enumerates the alloy container; the other three recreates trip nothing.

If a `Fleet · Alloy dark` or exporter-stale page fires because a window ran long: it self-resolves once `up` returns; note it in the Slack thread rather than silencing anything.

## Rollback

Re-pin the previous digest (Step 0's baseline record) and repeat the same converge + `up -d` for the affected host. The `alloy-data` WAL/positions survive both directions; journal readers resume from their cursor (window: `max_age = 48h` — an outage longer than that loses the older journal tail, another reason not to park a half-done bump).

## Closeout

- `docs/reference/fleet-pins.md`: the new digest, version, publish date, deploy date, per host.
- Prune each bumped host once its row is written — `uv run python infra/scripts/prune-host-images.py <host>`, then `--apply`. All four hosts run Alloy, so this is owed four times, each after that host's row lands.
- Commit + PR per the repo conventions (branch off `develop`, review before push). Note the run in the iterations history only if the bump rode a larger iteration.
