---
status: open
ripe_when: the trade-bar materializer's spec is written (it must answer the same settle-discipline question, T0065's reach round), or any panel hour is ever observed derived from un-healed data
---

# The panel's monotone watermark can permanently capture an un-healed hour (re-mint race)

## Context — what

Spec `00052` D6 materializes panel hours "strictly newer than the per-pair watermark" and explicitly claims *"no extra settle margin is needed: a canonical final is settled by construction."* That claim conflates **settled** (the file is final and hash-verified) with **heal-complete** (the reconciled-first view will not change). The reconciler mints healed book hours at H+2h…H+6h — *after* an hourly panel pass may already have consumed the un-healed primary final. The watermark is monotone and there is no re-mint invalidation, so a panel hour derived from un-healed data is **permanent** (until a generation regen).

## Why this matters

A panel hour materialized from a gappy primary shows honest-looking gaps/unanchored spans **even though the healed canonical has the data** — quietly degrading the exact dataset T0014's spread calibration and T0024's spread-cap are about to consume, with nothing paging. And the race is real, not theoretical: post-T0058 the primary's NFS visibility lag sawtooths **1.7–2.2 h** while the mint floor is **H+2 h** — at the sawtooth trough the panel can see (and consume) the un-healed primary *before* the mint cycle splices it.

## Findings so far

- **Drill evidence (2026-07-17, measured 2026-07-18):** drill hour 15 was minted healed at 17:21:05Z; the panel's hour-15 file was written **17:22:30** — one minute *after* the mint — and holds 3600 gap-free rows (healed-fed). But it was saved by **ordering luck, not design**: the ops cycle happens to run reconcile (:12/:42) before the panel pass, and the NFS lag happened to exceed the mint time. D6's own text denies needing the margin that saved it.
- The race window for **books** is narrow (lag trough 1.7 h vs mint floor 2 h ≈ tens of minutes, only at trough phase). For **trade-derived bars** (the future materializer, [[T0065]]'s reach round) the same design would be broken almost always: trades are heal-complete only after the *next day's* REST backfill (≤ ~28 h) — a chasm, not a race.
- The panel is `f(canonical)`, recomputable: any hour found un-healed-derived can be repaired by re-deriving that hour (or a generation regen). No data is lost — the defect is silent staleness, not loss.

## Suggested next steps

- **Decide the panel's settle discipline explicitly**: either (a) an explicit book-settle watermark — materialize hour H only once `now ≥ H+6h` + one pull cycle (heal-complete by construction; costs ~5 h of panel freshness, which no current consumer needs), or (b) ledger-driven invalidation — the reconcile ledger records every minted pair-hour; re-derive affected panel hours (keeps freshness, adds a rewrite path that must respect consumption-time pinning). Option (a) is the simple, likely-sufficient fix.
- **Audit the existing tree once** (cheap, ops-side): for each `minted` book entry in the reconcile ledger, compare the mint time against the panel hour's mtime; any panel hour written *before* its mint is un-healed-derived — re-derive it and count. The drill period plus any organic splices bound the audit set.
- **Bind the trade-bar materializer to answer the same question in its spec** (settle-lag ≥ the daily trade-backfill, or invalidation) — do not copy the panel's D6 shape ([[T0065]]).
