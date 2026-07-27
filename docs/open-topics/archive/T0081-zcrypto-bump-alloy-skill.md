---
status: resolved
---

# `/zcrypto-bump-alloy` — a manual skill to roll a new Alloy image across the fleet

## Context — what

All four hosts (NAS, ops, both capture VPSes) run digest-pinned Grafana Alloy containers. Alloy is actively developed upstream, so the fleet periodically wants a version bump. This topic tracks a **manual-only** skill that packages the rollout: compare the pinned version against the newest upstream release; if newer, update the pins and converge host-by-host in canary order.

Deliberately general: the skill keys on "a newer release exists", never on any particular upstream issue or PR landing.

## Why this matters

An Alloy bump is a four-host deploy on infrastructure carrying unbackfillable capture data and the live engine — but it does **not** touch the capture/engine/puller codebase, so it needs no inter-capture-host bake window. Without a codified procedure every bump re-derives the same questions (order, restart discipline, verification); with one it is a routine low-risk operation.

## Findings so far

- Pinning differs by host, and the skill must handle both shapes: the **NAS** pin is repo-resident (`nas_alloy_image` in `infra/ansible/host_vars/nas/vars.yml`, rendered into `.env`); **ops and both capture hosts** run bare `grafana/alloy` images whose digests arrive as per-converge extra-vars with **no repo-recorded default** — so on those hosts the skill's first job is to ADD a repo-resident pin (or durably record the digest it deploys), else the next bump has nothing to compare against. *(Corrected 2026-07-21 at the whole-branch review — the original bullet claimed all four were `.env`-pinned with role equivalents, false for three of four hosts.)*
- Only the NAS role automates restart-after-recreate; ops and the capture hosts are render-only, so the skill must bake the post-recreate restart in. This discharges [[T0048]]'s residual for **Alloy's own recreations only** — the render-only-host residual for app-container recreations remains its own item.
- Canary order for a telemetry-only change: NAS/ops first, then capture secondary, then capture primary.

## Done so far

**(2026-07-23) The skill is built and adversarially reviewed** — `.claude/skills/zcrypto-bump-alloy/SKILL.md`, authored from a 5-surface fact survey of the post-00068/00069 tree and corrected by an adversarial review that verified every command against both trees. Its load-bearing content: canary order ops → NAS → capture secondary → capture primary (ordered for verification quality — telemetry-only, so no 24 h bake is owed; the canary rule is capture-image-scoped); the currently-running-capture-digest requirement on capture converges (via `{{.Config.Image}}`, never `{{.Image}}` — measured host-dependent: equal to the pin only under the containerd image store); the render-only reality on ops/capture (`compose up -d` is the operator's step); the empty-`-e`-counts-as-defined footgun; the alert clocks (per-host `Alloy dark` ≈15 m effective, ops raced by the hcio-watchdog at ~10 m); `docs/reference/fleet-pins.md` as the durable digest record for the three hosts whose pins are converge-time-only (deliberately left that way — the skip-when-absent gate is load-bearing, so no repo defaults were added). Prerequisite pinned: PR #191 merged before the first run.

## Resolution

**Resolved 2026-07-27** by the skill's first real run: Alloy **v1.17.1 → v1.18.0** (`4f6ddc56ffdc` → `491b0578c049`) across all four hosts, in canary order, zero restarts, no protected service touched.

**The run's purpose was to correct what a written procedure gets subtly wrong, and it found four things** — none of which a re-read would have caught:

1. **`docker compose up -d` needs `sudo` on every host.** `alloy-secrets.env` is `0600 zcrypto-alloy`, so the unprivileged form dies with "permission denied" — harmlessly, before touching the container, so the old one keeps running and no dark window opens. The skill's command omitted it.
2. **Every ops recreate trips `Ops · ERROR logs`.** The *outgoing* container logs two `service=remotecfg … err="noop client"` errors on shutdown; the rule is host-wide with `for: 0s` over 15 m, so it fires ~35 s after the recreate and self-clears. Distinguishing it from a real fault takes a specific check — the lines are stamped ~200 ms *before* the new container's `StartedAt`, and the new container's own logs are clean.
3. **Alloy goes quiet after startup**, so the prescribed `{host=…, container="alloy"}` freshness check over 15 m reads empty on a healthy host bumped 30 min earlier. The liveness proof has to accept any container's line.
4. **A fresh container legitimately reports `samples_total=0`** until its first 60 s scrape lands — a too-eager read looks like a dead shipper.

**Verified per host**, container then Cloud: new digest with `RestartCount` 0; `failed_total` 0 and `samples_total` climbing on `127.0.0.1:12345`; `up` present; six `process_*` families; all 48 alert rules back to inactive. Host-specific: the ops liquidations poller still scraped, the NAS's next `archive-pull` cycle logging `checked=9215 ok=9215 failed=0`, and on both capture hosts the daemon's `StartedAt` **unchanged** with parquet still landing in the last 3 minutes.

**The trap the skill exists to prevent was avoided as designed.** Passing each host's currently-running capture digest kept the capture-compose render idempotent — it never appeared in the changed set, so the `restart capture service` handler never fired. On the primary, `--skip-tags engine` kept the engine play out entirely: the live trade engine's `StartedAt` is byte-identical across the whole run.

**No config-language risk, verified rather than assumed.** v1.18.0's two breaking changes are both `otelcol.*` components; the fleet uses only `loki.*` and `prometheus.*`. All three `config.alloy` files were then dry-started against the new binary (`alloy validate`) before any host was touched — worth doing regardless, since the capture config had changed hours earlier.
