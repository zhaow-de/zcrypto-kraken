---
status: open
ripe_when: shares T0014's data-span trigger — ≥2 weeks captured, ≈2026-07-22; the spread data itself is already queryable per-second off the ops-node 1s panel (iter-098)
---

# Universe selection — spread-cap criterion

## Context — what

The point-in-time universe (`docs/universe/point-in-time-universe.md`, spec `00003`) carries `spread_cap: pending-capture` on every symbol — there is no spread criterion in selection yet, because it needs per-pair top-of-book spread from the L2 capture daemon ([[T0003]]), which is VPS-gated and only recently live. Deferred per the design's non-goals.

## Why this matters

Selection currently filters on margin + median quote volume only; a thin-book pair could clear the €150k/day volume floor yet be untradeable at our sizing due to a wide spread. The spread-cap closes that gap. Shares the captured-L2 dependency with [[T0014]] (the cost-model spread term) — same data, different consumer (a selection filter vs the cost model), so both land off the same synced L2 copy.

## Findings so far

`spread_cap` is a documented placeholder on all 12 symbols (`docs/universe/point-in-time-universe.md` §Spread cap). The captured-spread data lands with T0014's window (≈ 2026-07-22, after T0003's ≥ 2-week capture + the workstation/NAS sync).

## Suggested next steps

- Compute per-pair median/percentile top-of-book spread off the ops-node 1s panel (reuse T0014's spread calibration — one derivation, two consumers).
- Add a `spread_cap` criterion to `cli/universe/rules.py` (a max-spread floor), re-run `build_universe_file`, and record whether the current 12-name selection changes.
