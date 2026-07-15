---
status: open
ripe_when: before go-live (real money / live trade key on any host running this stack), or before the same Alloy stack is deployed to a capture host
---

# Alloy holds root-equivalent Docker access (accepted 2026-07-14)

## Context — what

On the NAS, Grafana Alloy talks to `/var/run/docker.sock` **directly** (`discovery.docker` + `loki.source.docker` in `infra/nas/config.alloy`). The Docker API is root-equivalent: a client can `POST /containers/create` with `Privileged: true` and a bind-mount of `/`, start it, and own the host. The `:ro` on the socket mount does **not** prevent this — it makes the socket *file* read-only, not the API.

A GET-only `docker-socket-proxy` (tecnativa) previously sat in front of the socket with `POST=0`, which genuinely blocked this (verified: `POST /containers/create` → 403). It was removed on 2026-07-14 by the owner's explicit decision, because it corrupted the logs it existed to carry: HAProxy's `timeout client/server 10m` severed Docker's long-lived `/containers/<id>/logs?follow=1` stream whenever a container went quiet, and Alloy's reconnect (inclusive `since=<second>`) re-ingested the last line each time — so on a quiet container the same line was duplicated into Loki every 10 minutes, forever.

## Why this matters

The blast radius is not confined to the NAS. `/volume1/docker/zcrypto-archive/keys` holds the **rrsync private keys that pull from the capture VPS**. Root on the NAS reaches those keys, and through them the capture host and the unbackfillable L2 archive. The realistic threat is not a targeted attacker on the LAN — it is a supply-chain compromise of the `grafana/alloy` image or an RCE in Alloy itself. Low probability; total consequence.

This is a **deliberately accepted** risk, not an oversight. It is registered here so it is re-examined at the point where the stakes change, rather than being silently inherited.

## Findings so far

- Verified 2026-07-14, before removal: with the proxy in place, `POST /containers/create` through it returned **403**; `GET /volumes` and `GET /secrets` returned 403. The boundary was real and working.
- Mitigation retained: Alloy still runs **non-root** (`user: "1031:1000"` + `group_add: ["0"]` for the socket's group, `infra/nas/compose.yaml`). This preserves T0030's protection — the `0600` rrsync keys are owned by uid 1000, so Alloy's uid 1031 cannot read them through the `/host/root:ro` mount. It is defence in depth only: an attacker who reaches the Docker API can escalate around it.
- The duplication that motivated the removal is real and was measured: 2 lines in Docker vs 5 entries (2 distinct) in Loki over a restart-free window, with the duplicate timestamps matching the tailer's EOF/reconnect times exactly.
- The proxy's own bug was an upstream oversight, not an inherent cost: tecnativa's `haproxy.cfg.template` already special-cases `/events` with `timeout server 0` (a long-lived stream) but routes `/containers/<id>/logs?follow=1` to the default backend, which inherits the 10-minute timeout. **A patched template (two lines) would have kept the boundary and fixed the churn** — that is the option to reconsider if this residual is ever judged unacceptable.

## Suggested next steps

- **Before go-live**, decide whether Alloy should regain a boundary. The cheapest route is the one identified above: vendor `infra/nas/haproxy.cfg.template` = upstream's 80 lines plus `timeout server 0` under `backend dockerbackend` and `timeout client 0` under `frontend dockerfrontend`, mount it over `/usr/local/etc/haproxy/haproxy.cfg.template` (the entrypoint seds that file into `/tmp/haproxy.cfg`), and restore the proxy service in `compose.yaml`. That fixes the duplication *and* keeps `POST=0`.
- If the stack is ever deployed to a **capture host**, re-run this decision there before it ships — that host holds the live Kraken trade key, so the residual is materially worse than on the NAS.
- Consider filing the timeout bug upstream (`Tecnativa/docker-socket-proxy`): `/containers/<id>/logs?follow=1` is a streaming endpoint and should be routed to a backend with `timeout server 0`, exactly as `/events` already is. Filing is a public, irreversible action — draft it first and get the owner's go-ahead.
- Reconsider whether Alloy needs the container-log path at all: if `archive-pull` tee'd its output to a file on a volume Alloy can read as non-root, the socket could be dropped entirely (`loki.source.file`), which is strictly the best end state. Cost: Alloy's own logs would no longer be discoverable, and it touches `pull-entrypoint.sh`.
