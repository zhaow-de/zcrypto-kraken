---
status: open
ripe_when: now — measured, not predicted. `docs/reference/captured-spread-calibration.md`'s committed window is `2026-07-23T14:00Z … 2026-08-07T19:00Z`, and the live ledger holds a `both_streams_silent` record for `2026-07-27 07:01:04.071744 → 07:04:22.892410` (2,385.847992 s) inside it — a second frozen-book interval the caveat does not disclose. Discharged by re-reading the caveat and seeing both intervals named.
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

## Suggested next steps

- **Measure the second interval's share the same way the first was measured** — rows and percentage of the window, per pair — so the caveat can state both with the same arithmetic rather than one precisely and one vaguely.
- **Rewrite the caveat to name both intervals**, in place, keeping its existing conclusion. `agent-ops.md`: correct a durable doc by rewriting the narrative, never by appending a retraction below it.
- **While there, check whether any interval predates the window's start** — the sweep that found this looked only inside the committed bounds, so the answer for the predecessor windows the doc also references is unknown.
