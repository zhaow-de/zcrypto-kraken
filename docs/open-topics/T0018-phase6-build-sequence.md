---
status: open
ripe_when: the shadow-engine iteration is brainstormed (the next attended Phase-6 build session)
---

# Phase-6 build sequence and its cross-iteration constraints

## Context — what

The Phase-6 kickoff (spec `docs/specs/00039-phase6-kickoff-design.md`, iter-079, attended 2026-07-10) fixed a build roadmap spanning several iterations: the **shadow engine** (`cli/engine/` — Nautilus `TradingNode`, REST-fed signals, input-snapshot + intended-order journal, concordance reporter; iter-081, renumbered — the 00038 trial took iter-080), then **VPS deployment** (engine ansible role + compose + key delivery; iter-082), then the **6b executor** behind the Stage-6a concordance gate. A committed spec is not a durable home for deferred actions (per `open-topics.md` — prose is not registration), so the sequence and its cross-iteration constraints live here.

## Why this matters

Three constraints bind *future* iterations and would otherwise be invisible at pick time:

1. **Cadence-agnostic engine — the trigger FIRED (iter-080): the 00038 trial ADOPTED.** The deployable-system candidate is now **registry record 43** — the cross-frequency combination on the **4h union calendar** (governed noc Sharpe 1.5366; three sleeves: daily benchmark w·l3 intraday-held, A1-lf weekly v0.12 offset-mean, equal-weight A2-4h ensemble; 180-bar inverse-vol weights; cap 20/10; governor at daily cadence). The engine builds against record 43: **its construction has no committed builder yet** (it lives in the iter-080 drivers + spec 00038) — a committed, tested crossfreq builder (record 33's `build_combined_system` equivalent) plus the runbook (report 12) update are shadow-engine-iteration scope. Coordinate with **T0019** (fixed-weight simplification candidate) before hardening the builder: an adopted simplification would remove the adaptive-weighting mechanism entirely. The daily→4h expansion contract matters here: close-time-shifted boundaries per `expand_daily_positions`' pinned contract (the iter-080 look-ahead finding).
2. **§8 hardening before the key lands (deployment iteration)** — §12's host blocker requires the §8 hardening checklist (firewall, fail2ban, unattended security upgrades, key IP-allowlisting) verified on the VPS **before** the ansible-vault key delivery step runs. A named gate in the deployment plan, not an afterthought.
3. **6b executor scope** — order submission + order state machine + reconciliation loop + kill-switch, **plus** §12's weekly tracking-error report in full (fills, fees, rollover accrual, slippage vs the cost model), **cost-model recalibration from real fills**, tiny-live sleeve funding (D3(ii) second half, human money action), and the **D3(iii) T2 tax-probe set** (≥ 1 margin long + ≥ 1 margin short, each held across ≥ 2 rollover events, one closed, one settled) scheduled within the first two 6b weeks so the tax verification (T2 pass or T3 fallback) closes before any ramp past 25 %. T0005's Blockpit T1 check rides alongside.

## Findings so far

- Spec 00039 (kickoff decisions 1–8, the pre-registered go-live criteria incl. the pinned Stage-6a concordance semantics, and the adapter-verification protocol); decisions log `[iter-079]`.
- The go/no-go gate and every ramp step are **D3(vi) human decisions**, conditional on no gate breaches and the DD ladder untouched or correctly handled — never automatic calendar promotions.
- The governor enters live at its true carried state (×0.5).

## Suggested next steps

- **Shadow engine (iter-081, next attended session)**: brainstorm + spec per spec 00039 decision 5, honoring constraint 1 (deployable = record 43; committed crossfreq builder + runbook update in scope; check T0019 first).
- **Deployment (iter-082)**: honoring constraint 2; starts the 2–3-week Stage-6a clock.
- **6b iteration**: executor + tiny-live start per constraint 3.
