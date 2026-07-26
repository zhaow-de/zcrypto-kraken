---
status: resolved
---

# Both capture hosts sit on one provider — correlated-loss residual

## Context — what

Spec `00050` shipped redundant capture as two Linode VMs — primary Frankfurt, secondary Amsterdam (`infra/ansible/host_vars/zcrypto-red/vars.yml`; the spec's own cost line) — and named **multi-provider diversification** a non-goal: "both hosts are Linode (different regions); accepted residual, revisit before scaling capital." That acceptance lived only in the spec's non-goals prose — this topic registers it (split out by [[T0082]]'s one-shot parked-items review, 2026-07-21).

## Why this matters

L2 capture is unbackfillable; the redundancy exists so no single-host event loses data permanently. A **provider-level** event defeats it: a Linode control-plane incident, a provider-wide network event, or — the sharpest correlation, since the two hosts are at least geographically separated (Frankfurt/Amsterdam) — an **account-level** action (suspension, billing failure, compromise) that takes both VMs at once, since both live under one account. The risk was consciously accepted for the research phase; real capital raises the stakes of a permanent tape hole.

## Findings so far

- The trades stream is materially less exposed than the book: a both-hosts outage window is REST-recoverable for trades ([[T0050]]'s daily backfill heals against Kraken's dense `trade_id` tape); the book/L2 side has no equivalent — a correlated outage is a permanent book gap.
- The reconciler is written primary-plus-one-secondary (00050 non-goal: no N-way), so a third mirror is not a config change; a *replacement* of one host by another provider is the shape that fits the shipped code.

## Resolution (2026-07-23 — owner ruling, taken ahead of the 6b gate)

**The acceptance is ruled forward in full: the architecture stays as-is.** The 6b-session decision this topic was parked for was taken early, in the 2026-07-23 grooming session, with fuller information than the original menu had:

- **No engine standby.** Hot/automatic standby was analyzed and declined: two exec-capable NautilusTrader nodes sharing the one Kraken trade key, with no fencing infrastructure anywhere in the fleet and no server-side single-writer guarantee at Kraken, invite split-brain duplicate orders — a strictly worse failure than the hours-of-stale-targets it would prevent; the single-residency key posture (spec 00057 D4) would double its standing surface; and at six decisions/day with bit-identical replay and proven systemd self-recovery (the 2026-07-11 reboot: the boundary cycle re-ran inside its window, gate intact), automatic failover saves minutes against a 4-hour boundary. **Warm standby (attended promotion) was assessed feasible and cheap** — measured during the assessment: the engine has NO data co-location constraint (each cycle fetches its OHLC from Kraken REST with settle-verified refresh, `cli/engine/cycle.py`; the container mounts only its own state dir) and is already the Phase-6 NautilusTrader `TradingNode` (`cli/engine/node.py`), so a standby could live on any host — but the owner declined it as over-engineering for the bounded engine-loss cost (4–8 h of stale targets on governed sizes, journaled recovery proven, vs capture's permanent tape).
- **Diversification dropped.** No second provider, no AWS move for the secondary. The engine/capture decoupling above removed the "two identical full nodes" rationale that had linked the AWS question to the standby question; judged on capture grounds alone, the two-Linode residual (Frankfurt/Amsterdam) is accepted: the trades tape self-heals via [[T0050]]'s REST backfill, and the book-gap exposure is bounded by provider reliability at current stakes.
- **Account-level de-correlation dropped with the rest.** The whole correlated-loss residual — provider-wide events and account-level actions included — is consciously accepted as-is by the owner. A future change in stakes is a new decision to take fresh, not a deferral parked here.

Nothing remains open; no sub-item splits out.
