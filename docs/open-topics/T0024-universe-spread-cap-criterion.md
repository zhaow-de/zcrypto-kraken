---
status: partial
ripe_when: the next universe rebuild — the criterion, its calibration and its measured effect are delivered, but the canonical artifact still carries `spread_cap: "pending-capture"` until `_refresh_universe` runs (a live `AssetPairs` fetch plus a canonical-set write). It rides [[T0025]]'s pre-live refresh, which re-runs selection anyway
---

# Universe selection — spread-cap criterion

## Context — what

The point-in-time universe (`docs/universe/point-in-time-universe.md`, spec `00003`) carries `spread_cap: pending-capture` on every symbol — there is no spread criterion in selection yet, because it needs per-pair top-of-book spread from the L2 capture daemon ([[T0003]]), which is VPS-gated and only recently live. Deferred per the design's non-goals.

## Why this matters

Selection currently filters on margin + median quote volume only; a thin-book pair could clear the €150k/day volume floor yet be untradeable at our sizing due to a wide spread. The spread-cap closes that gap. Shares the captured-L2 dependency with [[T0014]] (the cost-model spread term) — same data, different consumer (a selection filter vs the cost model), so both land off the same synced L2 copy.

## Findings so far

`spread_cap` is a documented placeholder on all 12 symbols (`docs/universe/point-in-time-universe.md` §Spread cap). The captured-spread data lands with T0014's window (≈ 2026-07-22, after T0003's ≥ 2-week capture + the workstation/NAS sync).

## Done so far

**Delivered 2026-07-22 (iter-115, spec `00067`).**

- *Compute per-pair spread* — done by **reusing [[T0014]]'s calibration** rather than re-deriving ("one derivation, two consumers", as this topic asked). That inherits T0014's measurement that the **median top-of-book spread is unusable for BTC/EUR** (tick-quantised; mean ÷ median 11.2× against 0.9–1.3× elsewhere), so this topic's own wording — "median/percentile top-of-book spread" — is superseded: the criterion is priced on the **mean effective spread at size**, at the **€1,400 max-size position the volume floor is already calibrated against**, so the two criteria are commensurable.
- *Add a `spread_cap` criterion to `cli/universe/rules.py`* — done, opt-in (`spreads=None` is byte-identical to before, pinned by a test). Cap **10 bps/side**, derived from the fee stack: a round trip crossing twice at the cap costs ~25 % of the tier-1 round-trip maker fee. Held as an absolute constant, not a live fraction of the tier — at the top tiers maker → 0 % and such a formula degenerates to a cap of zero.
- *Record whether the 12-name selection changes* — **it does not.** Determined offline from the stored refdata snapshot: 12 → 12, `escalate` unchanged, DOT worst at 6.55 bps/side (16.4 % of the RT fee, ~35 % headroom). **The criterion excludes nothing today and that is the honest outcome** — tuning it to bite on the current universe would be fitting the rule to the data it judges. It is a guard for future refreshes.
- *Re-run `build_universe_file`* — **not done, and deliberately**: `_refresh_universe` calls `fetch_public("AssetPairs")` and writes a canonical set. Outside this run's boundary; it rides [[T0025]]'s pre-live refresh.

**The finding that outlasts the criterion:** the cap can only screen **10 of the 12** selected symbols. The capture daemon subscribes to **EUR-quoted pairs only**, so `ETH/BTC` and `SOL/BTC` have no L2 at all; they are recorded `spread_bps: null` and not rejected. `SOL/BTC` sits at 233,595 EUR/day, barely over the volume floor — the blind spot is exactly where the criterion was most wanted. Registered as [[T0092]].

## Suggested next steps

- **(The remainder)** At the next universe rebuild, confirm the artifact carries the `spread_cap` record instead of `"pending-capture"`, and that the two BTC-quoted legs show `spread_bps: null`. Then this closes.
- **(Decide separately)** [[T0092]] — whether the BTC-quoted legs should be captured at all, which is what would let the cap cover the whole universe.
