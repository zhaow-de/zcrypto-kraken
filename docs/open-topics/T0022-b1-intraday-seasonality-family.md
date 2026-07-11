---
status: open
ripe_when: live now — the family opened iter-086; each subsequent B1 trial rides a research iteration until the family's verdict or the shared B budget's discipline ends it
---

# B1 — intraday trend + time-of-day/day-of-week seasonality (the family topic)

## Context — what

Split out of the T0016 umbrella per its own rule when B1's prerequisites fired (T0009's protocol legs iter-072; the 15m substrate iter-085 — `data/ohlc-15m`, `basket_sha256 0fed24a6…`). The master plan §5's design brief is binding: **seasonality as conditioning features on the adopted signals** (trade only at favorable windows; scale by intraday-vol state), **never a standalone high-turnover system** — the family lives or dies on maker-fill realism and turnover control, so every verdict is net-of-cost from the first read.

## Why this matters

B1 is the §5 ranked queue's top un-started family — the "genuinely new frequency band" where the residual-alpha probability is concentrated after the A-family kill. Its cheapest failure mode is the classic one: a seasonality overlay that looks good in-sample because the favorable windows were picked on the full sample. Leak-free, fold-internal window estimation is the family's core engineering requirement, pinned in spec 00045.

## Findings so far

- Hypothesis + trial-1 pre-registration: decisions log `[iter-086]` — the conditioning A/B on the adopted A2-4h ensemble (arm A = trials 37–39 equal-weight as adopted; arm B = + hour-of-day/day-of-week favorable-window gating and intraday-vol-state scaling from the 15m substrate), one knob, judged per T0009's revised kill bar vs the frozen B3+vt-dynamic benchmark.
- Substrate QA input (iter-085): AVAX/LINK/DOT recent-year 15m density 88–97% (omitted no-trade slots) — the vol-state features must define behavior on missing 15m bars explicitly.
- Budget: **B = 25 shared across Bucket B** (pre-registered, hard); B1 trials count against it under the family's registry key.

## Suggested next steps

- Execute spec/plan `00045` (harness: leak-free seasonality/vol-state features + conditioning overlay + fold-internal estimation, TDD; then trial 1 as pre-registered).
- Subsequent trials (if trial 1 survives or teaches): vol-state-only arm, window-only arm (attribution split), and the 1h-cadence variant — each a fresh `[iter-NNN]` pre-registration, same registry family key.
- Kill discipline: an honest kill closes this topic (archive with the verdict); budget exhaustion or a family kill-bar hit does the same. Expanding past the shared B budget is a parked human decision, never autonomous.
