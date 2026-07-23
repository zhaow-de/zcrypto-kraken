---
status: open
ripe_when: the PR #191 closeout (rollout Steps 6–7 done) — archive with per-host `docker inspect` evidence that nothing in the fleet mounts `/var/run/docker.sock`; the former go-live boundary questions are mooted by the socket's removal (specs 00068/00069) and the egress remainder lives in T0095
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
- **The capture-host leg fired (2026-07-19, spec 00057 D5, commit `a15b893`).** The first-time `zcrypto-alloy` telemetry stack on both capture VPSes ships Alloy with the **same** direct docker-socket access as the NAS — `/var/run/docker.sock:ro` + `discovery.docker`/`loki.source.docker` (`roles/capture/templates/alloy-compose.yaml.j2`, `roles/capture/files/config.alloy`). On the **primary** this is the materially-worse case this topic anticipated: the primary is the engine host, so the root-equivalent Docker API now sits on the box holding the **live Kraken trade key** (`0600 root:root`, spec 00057 D4). Mitigations retained (defence in depth only): Alloy runs as the non-key-owning `zcrypto-alloy` uid — it cannot read the `0600` trade key or any key through the `/host/root:ro` mount without first escalating the Docker API; the trade key stays `0600 root:root`; and Alloy is its OWN compose project, so an Alloy redeploy never restarts the unbackfillable capture daemon. The residual was **accepted for the capture-host deploy** — the boundary re-decision is deferred to the go-live readiness review (the engine does not trade live today).

- **The socket is being retired outright (specs 00068/00069, rollout in progress).** Measured 2026-07-22/23 during the rollout: `docker.sock` mounts = **0** on the ops Alloy, the NAS Alloy, and both `zcrypto-red` containers; the **primary is the last socket holder**, cleared at rollout Step 6. Container logs now reach Loki via the journald driver + `loki.source.journal`, and the four daemons ship their own JSON logs (`--ship-logs`, 00068 D3) — `discovery.docker`/`loki.source.docker` are deleted from every config. This resolves the topic's core by *removal*, not by re-acceptance: after Step 6 there is no Docker API exposure to bound.

_Related archived record:_ [[T0040]] (docker-socket-proxy denial alert) was closed unbuilt when the proxy was removed; its rider (restore the denial alert with any restored boundary) is mooted with the boundary question itself — no socket, nothing to guard.

## Suggested next steps

- **Archive this topic at the PR #191 closeout** (rollout Steps 6–7 done), with the per-host `docker inspect` evidence that no container mounts `/var/run/docker.sock` anywhere in the fleet. The three boundary-restore paths (NAS proxy, capture-host proxy, archive-pull tee) and the T0040 alert rider are all **mooted by removal** — recorded here, no action.
- ~~Engine-log egress~~ — **split to [[T0095]]** (2026-07-23 grooming), where the owner's ruling is recorded: the egress is *accepted*, live trading included, and the same order/position/PnL detail is wanted as first-class metrics at the dashboards iteration. No go-live gate remains on this subject.
- ~~Upstream filing (`Tecnativa/docker-socket-proxy` streaming-timeout bug)~~ — **dropped (2026-07-23 grooming, owner's call: whichever is simpler)**: after the socket retirement we run zero proxies and zero socket mounts, so there is no environment left to reproduce or verify a patch against, and this repo has no stake in the fix. The two-line diagnosis (route `/containers/<id>/logs?follow=1` like `/events`, `timeout server 0`) stays preserved in the Findings above for anyone who searches.
- **(executed as specs 00068/00069)** The owner's preferred end-state — socket-free integration fleet-wide, `/metrics` over HTTP + the cli shipping its own JSON logs — is the design that shipped; its open question (do docker-stdio-only lines carry signal?) was settled by the 00068 ruling: plain text on console, Docker's own rotation, stdout stays local and is retrieved via `docker logs`.
