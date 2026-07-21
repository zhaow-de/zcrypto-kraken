---
status: open
ripe_when: a Grafana Alloy release newer than the fleet's pinned version exists — human-checked at any convenient moment, and the skill is always human-run
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

## Suggested next steps

- **(When ripe)** Write the skill: check pinned vs newest release; update pins; converge in canary order with the restart baked in; verify per host by outcome (Alloy up, series shipping — reuse `tests/test_infra_alloy_series.py`'s pins as the checklist source so skill and tests never drift).
- **(With it)** `disable-model-invocation: true` — human-triggered only.
