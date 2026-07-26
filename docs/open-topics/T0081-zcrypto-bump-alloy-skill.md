---
status: partial
ripe_when: the first real bump run — PR #191 merged + a release newer than the fleet pin (true today: v1.18.0 vs v1.17.1; deliberately deferred past the 2026-07-29→08-20 absence). The skill itself is BUILT; the run validates it and resolves this topic
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

## Suggested next steps

- **(At the first real bump)** Run the skill end-to-end; whatever the live run corrects in it lands as edits, then this topic resolves. The trigger stands: a release newer than the fleet pin exists (v1.18.0 vs the fleet's v1.17.1 as of 2026-07-23 — deliberately NOT bumped pre-departure; first run post-return unless needed sooner).
