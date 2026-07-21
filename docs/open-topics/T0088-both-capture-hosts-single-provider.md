---
status: open
ripe_when: the Stage-6b session's live-capital decision (gate call earliest ~2026-07-25) — spec 00050's own acceptance was scoped "revisit before scaling capital", and that revisit is now dated
---

# Both capture hosts sit on one provider — correlated-loss residual

## Context — what

Spec `00050` shipped redundant capture as two Linode VMs — primary Frankfurt, secondary Amsterdam (`infra/ansible/host_vars/zcrypto-red/vars.yml`; the spec's own cost line) — and named **multi-provider diversification** a non-goal: "both hosts are Linode (different regions); accepted residual, revisit before scaling capital." That acceptance lived only in the spec's non-goals prose — this topic registers it (split out by [[T0082]]'s one-shot parked-items review, 2026-07-21).

## Why this matters

L2 capture is unbackfillable; the redundancy exists so no single-host event loses data permanently. A **provider-level** event defeats it: a Linode control-plane incident, a provider-wide network event, or — the sharpest correlation, since the two hosts are at least geographically separated (Frankfurt/Amsterdam) — an **account-level** action (suspension, billing failure, compromise) that takes both VMs at once, since both live under one account. The risk was consciously accepted for the research phase; real capital raises the stakes of a permanent tape hole.

## Findings so far

- The trades stream is materially less exposed than the book: a both-hosts outage window is REST-recoverable for trades ([[T0050]]'s daily backfill heals against Kraken's dense `trade_id` tape); the book/L2 side has no equivalent — a correlated outage is a permanent book gap.
- The reconciler is written primary-plus-one-secondary (00050 non-goal: no N-way), so a third mirror is not a config change; a *replacement* of one host by another provider is the shape that fits the shipped code.

## Suggested next steps

- **(Owner decision, at the 6b session)** Rule the acceptance forward or order diversification: for tiny-live, the accepted residual is plausibly still proportionate (the trades tape self-heals; the book gap risk is bounded by provider reliability); for scaled capital, re-price it.
- **(Autonomous prep, only if diversification is ordered)** Shortlist one alternative provider/facility for the *secondary* (egress cost, latency to Kraken, image compatibility), and route the migration through the capture-rollout discipline ([[T0084]]'s skill when built; canary rule per `capture-deploys.md`).
- **(Cheap hardening, decidable with the owner)** Account-level de-correlation short of a second provider: separate billing method + hardened account auth are worth pricing even if the VMs stay Linode.
