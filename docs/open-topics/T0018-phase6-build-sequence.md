---
status: partial
ripe_when: the shadow-engine iteration is brainstormed (the next attended Phase-6 build session)
---

# Phase-6 build sequence and its cross-iteration constraints

## Context — what

The Phase-6 kickoff (spec `docs/specs/00039-phase6-kickoff-design.md`, iter-079, attended 2026-07-10) fixed a build roadmap spanning several iterations: the **shadow engine** (`cli/engine/` — Nautilus `TradingNode`, REST-fed signals, input-snapshot + intended-order journal, concordance reporter; iteration number open — the 00038 trial took iter-080 and the T0019 fixed-weight trial took iter-081), then **VPS deployment** (engine ansible role + compose + key delivery; iter-082), then the **6b executor** behind the Stage-6a concordance gate. A committed spec is not a durable home for deferred actions (per `open-topics.md` — prose is not registration), so the sequence and its cross-iteration constraints live here.

## Why this matters

Three constraints bind *future* iterations and would otherwise be invisible at pick time:

1. **Cadence-agnostic engine — the trigger FIRED (iter-080): the 00038 trial ADOPTED.** The deployable-system candidate is now **registry record 44** (iter-081; supersedes records 43 and 33) — the cross-frequency combination on the **4h union calendar** with **fixed ⅓ sleeve weights** (T0019's adopted simplification; governed noc Sharpe 1.5609; three sleeves: daily benchmark w·l3 intraday-held, A1-lf weekly v0.12 offset-mean, equal-weight A2-4h ensemble; cap 20/10; governor at daily cadence — no adaptive-weight state to build, journal, or reconcile). The engine builds against record 44 via the **committed builder landed in iter-082** (`cli/portfolio/crossfreq_system.py`: `build_crossfreq_system` verified path + bit-identical `build_crossfreq_system_fast`, frozen-figure regression tests; runbook updated). The daily→4h expansion contract matters here: close-time-shifted boundaries per `expand_daily_positions`' pinned contract (the iter-080 look-ahead finding).
2. **§8 hardening before the key lands (deployment iteration)** — §12's host blocker requires the §8 hardening checklist (firewall, fail2ban, unattended security upgrades, key IP-allowlisting) verified on the VPS **before** the ansible-vault key delivery step runs. A named gate in the deployment plan, not an afterthought.
3. **Store seeding — DONE (iter-083, 2026-07-10)**: the workstation store seeded inside the REST window (all 20 series passed seam QA; overlaps 620 daily / 116 4h bars; 7,040 bars appended, 0 divergent) and stays warm under the soak service. **iter-084's VPS store options**: re-seed via REST while the window lasts (the 4h window now covers from ≈ 2026-03-12, receding daily), **rsync the warm workstation store** (the standing fallback), or the quarterly OHLCVT dump. **VPS disk sizing input**: the journal grows ≈ 0.3 GB/month (append-only, no pruning in Phase 6 — an explicit drop, decisions log `[iter-083]`).
4. **6b executor scope** — order submission + order state machine + reconciliation loop + kill-switch, **plus** §12's weekly tracking-error report in full (fills, fees, rollover accrual, slippage vs the cost model), **cost-model recalibration from real fills**, tiny-live sleeve funding (D3(ii) second half, human money action), and the **D3(iii) T2 tax-probe set** (≥ 1 margin long + ≥ 1 margin short, each held across ≥ 2 rollover events, one closed, one settled) scheduled within the first two 6b weeks so the tax verification (T2 pass or T3 fallback) closes before any ramp past 25 %. T0005's Blockpit T1 check rides alongside.

## Findings so far

- Spec 00039 (kickoff decisions 1–8, the pre-registered go-live criteria incl. the pinned Stage-6a concordance semantics, and the adapter-verification protocol); decisions log `[iter-079]`.
- The go/no-go gate and every ramp step are **D3(vi) human decisions**, conditional on no gate breaches and the DD ladder untouched or correctly handled — never automatic calendar promotions.
- The governor enters live at its true carried state (×0.5).

## Done so far

- **iter-083 (spec/plan `00041`, PR pending)**: the shadow node end-to-end — live price store + seeder (seeded 2026-07-10, seam QA clean), the cycle core (settle-verify both grids, union-aligned snapshots, failed-cycle sidecars, aware-UTC), the Nautilus node wrapper (restart-safe timer arithmetic), the `zcrypto engine` CLI (seed/run/cycle/replay/report), and the **workstation soak running** (systemd user service, linger enabled; first live cycle 2026-07-10 20:00 UTC journaled, fast AND verified replays bit-exact, dev evidence only — the gate clock starts on the VPS).

- **iter-082 (spec/plan `00040`, PR pending)**: the record-44 builder (verified + bit-identical fast path, frozen-figure regression tests, newest-row contract) and the `cli/engine` concordance core (journal contract with no-peek invariants, replay, compare, the ratified 4h gate evaluator); runbook record-44 section. Constraint 1's builder scope is delivered — the node work remains.

## Suggested next steps

- **Shadow engine node (iter-083, next attended session)**: the TradingNode, scheduler, price store + REST append (constraint 3's ≈ Jul 25 window), journal writing, `zcrypto engine` CLI — on iter-082's builder + concordance core. Interface caveat (corrected iter-083): the engine's pinned convention is **aware-UTC everywhere** (spec 00041 §cycle 8); `evaluate_gate` gets an aware `now` and the CLI enforces awareness at every boundary.
- **Deployment (the iteration after)**: honoring constraint 2; starts the 2–3-week Stage-6a clock.
- **6b iteration**: executor + tiny-live start per constraint 4.
