---
status: open
ripe_when: the iter-080 shadow-engine iteration is brainstormed (the next attended Phase-6 build session)
---

# Phase-6 build sequence and its cross-iteration constraints

## Context — what

The Phase-6 kickoff (spec `docs/specs/00039-phase6-kickoff-design.md`, iter-079, attended 2026-07-10) fixed a build roadmap spanning several iterations: **iter-080** shadow engine (`cli/engine/` — Nautilus `TradingNode`, REST-fed signals, input-snapshot + intended-order journal, concordance reporter), **iter-081** VPS deployment (engine ansible role + compose + key delivery), then the **6b executor** behind the Stage-6a concordance gate. A committed spec is not a durable home for deferred actions (per `open-topics.md` — prose is not registration), so the sequence and its cross-iteration constraints live here.

## Why this matters

Three constraints bind *future* iterations and would otherwise be invisible at pick time:

1. **Cadence-agnostic engine (iter-080)** — the deployable book is registry record 33 (daily) today, but the pending **00038 cross-frequency trial** (tonight's research loop) may adopt a 4h-calendar system. The engine takes the deployable registry record as input, never a hardcoded cadence. Check the 00038 verdict before designing iter-080.
2. **§8 hardening before the key lands (iter-081)** — §12's host blocker requires the §8 hardening checklist (firewall, fail2ban, unattended security upgrades, key IP-allowlisting) verified on the VPS **before** the ansible-vault key delivery step runs. A named gate in the deployment plan, not an afterthought.
3. **6b executor scope** — order submission + order state machine + reconciliation loop + kill-switch, **plus** §12's weekly tracking-error report in full (fills, fees, rollover accrual, slippage vs the cost model), **cost-model recalibration from real fills**, tiny-live sleeve funding (D3(ii) second half, human money action), and the **D3(iii) T2 tax-probe set** (≥ 1 margin long + ≥ 1 margin short, each held across ≥ 2 rollover events, one closed, one settled) scheduled within the first two 6b weeks so the tax verification (T2 pass or T3 fallback) closes before any ramp past 25 %. T0005's Blockpit T1 check rides alongside.

## Findings so far

- Spec 00039 (kickoff decisions 1–8, the pre-registered go-live criteria incl. the pinned Stage-6a concordance semantics, and the adapter-verification protocol); decisions log `[iter-079]`.
- The go/no-go gate and every ramp step are **D3(vi) human decisions**, conditional on no gate breaches and the DD ladder untouched or correctly handled — never automatic calendar promotions.
- The governor enters live at its true carried state (×0.5).

## Suggested next steps

- **iter-080**: brainstorm + spec the shadow engine per spec 00039 decision 5, honoring constraint 1 (read the 00038 trial verdict first).
- **iter-081**: deployment iteration honoring constraint 2; starts the 2–3-week Stage-6a clock.
- **6b iteration**: executor + tiny-live start per constraint 3.
