---
status: resolved
---

# The spread calibration discloses one of the two frozen-book intervals inside its own window

## Context — what

`docs/reference/captured-spread-calibration.md` carries an explicit caveat that a venue-dark interval sits inside its measurement window and is **not** excluded from the means:

> **A 17-minute frozen-book interval is inside this window and is NOT excluded from the means.** Kraken's first observed venue maintenance, 2026-08-06 07:01–07:18Z …

That disclosure is correct and deliberate. It is also incomplete: the window runs `2026-07-23T14:00Z … 2026-08-07T19:00Z`, and the reconcile ledger holds a **second** `both_streams_silent` record inside it — `2026-07-27 07:01:04.071744 → 07:04:22.892410`, booked 2,385.847992 s. [[T0104]] confirms that on exactly that date the L2 panel fabricates a carried-forward frozen book across such a gap, which is the mechanism the caveat is warning about.

## Why this matters

The caveat exists so a reader can judge how much of the calibration rests on fabricated rows. Disclosing one interval and not the other understates that exposure, and it does so in a **living reference doc** that downstream work reads as settled — [[T0014]]'s spread calibration feeds the universe spread-cap and the cost model.

The stakes are bounded and worth stating plainly: the caveat's *conclusion* — "disclosed rather than trimmed; do not shorten the window" — is unaffected either way, and the second interval is roughly a fifth the length of the first. This is an accuracy defect in a disclosure, not a reason to distrust the calibration.

## Findings so far

- **Verified from repo state alone**: the committed window bounds, the caveat's text, and the 2026-07-27 ledger record. No host access needed to reproduce any of it.
- The 2026-07-27 episode is one of the two *unannounced* WS-service-restart events ([[T0101]]), which is likely why it was missed — it produced no venue-status alert to notice, unlike 2026-08-06.
- The `stale_seconds` column [[T0104]] added is what lets a consumer filter fabricated rows; the caveat predates nothing, it simply counted one event.

- **Measured exhaustively from the panel, not inferred**: counting rows with `stale_seconds > 30` across all 365 window-hours × 12 pairs (4,380 files, none missing), **exactly two** hours carry any frozen row — 2026-07-27 07Z (2,078 rows, 173.2/pair) and 2026-08-06 07Z (10,226 rows, 852.2/pair), totalling 1,025.3 per pair, **0.0780 %** of the window.
- **The disclosed percentage was accidentally right and wrongly attributed.** The caveat's "~1,020 s is 0.078 %" came from the venue's announced 17-minute span for 2026-08-06; measured against the frozen rows the panel actually holds, that interval alone is 852.2 s (0.0649 %) and it is the **pair** of intervals that sums to 0.078 %.
- Both intervals are Kraken maintenances beginning within seconds of 07:01 UTC, published days ahead ([[T0145]]) — which is also why 2026-07-27 raised no venue alert to notice at the time.

## Resolution

**Resolved 2026-08-21.** The caveat in `docs/reference/captured-spread-calibration.md` now names both intervals, with the arithmetic measured the same way for each, and the narrative rewritten in place rather than corrected by an appended note (`agent-ops.md`).

All three of this topic's next-steps are discharged:

- **The second interval was measured the same way as the first** — better than that, both were re-measured by the same method, and the method was changed to the honest one. The caveat previously quoted the venue's *announced* span; it now quotes the panel's own frozen rows, which is what the caveat is actually about. That is why 2026-08-06's share fell from 0.078 % to 0.0649 % while the pair's total landed on 0.0780 %.
- **The caveat is rewritten to name both**, keeping its conclusion untouched: disclosed rather than trimmed, because ending the window before 2026-08-06 would cost the ≥2-week exit bar (spec `00085` D4).
- **The question of intervals predating the window is answered**: 2026-07-13 is the only earlier episode, ten days before this window opens, so it cannot touch these means. The caveat says so. The *superseded* windows that may have contained it are not re-examined — they are historical figures with no live consumer, and re-deriving them would be archaeology. An explicit drop, not a deferral.

**What did not change, deliberately:** the calibration's numbers, its conclusion, and the window itself. The defect was a disclosure that understated its own exposure by naming one of two intervals — an accuracy fix to a caveat, never a reason to distrust the calibration. The exhaustive sweep is the part that makes this a resolution rather than a patch: with exactly two frozen hours in 365 and no files missing, there is no third interval left to find.
