---
status: open
ripe_when: a `both_streams_silent` record reads `undetermined` while `zcrypto_capture_venue_status_total` carries a non-`online` series for that hour — i.e. the two halves demonstrably disagree on a live event, not a historical one. Check with `zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}` rising in the same hour that the status counter shows a state other than `online`; both series are already scraped, so the condition is readable without new instrumentation.
---

# Capture receives venue status but never archives it, so a past hour's status is unknowable

## Context — what

`cli/capture/command.py` handles Kraken's `status` category: it logs the message (`venue status system=%s version=%s effective_time=%s`) and counts it into `zcrypto_capture_venue_status_total{system=...}`. It does **not** write it to a segment. Nothing in the archive records what the venue said its own state was at a given moment.

The reconciler runs at least two hours behind the hour it settles, and Kraken's public `SystemStatus` endpoint reports *current* state only — there is no historical status API. So a reconciler that wants to know whether the venue was in `maintenance` during hour H has no source at all: not the archive, and not the live endpoint.

## Why this matters

Spec `00096`'s discriminator classifies a fleet-dark episode by cross-host agreement. Measured against the two known venue outages, cross-host and venue status turn out to be **complementary — each catches exactly the event the other misses**:

| Signal | 2026-08-06 | 2026-08-20 |
| --- | --- | --- |
| Kraken status page | posted `maintenance` → `cancel_only` → `post_only` → `online` | posted nothing |
| Cross-host agreement (`00096`) | `undetermined` — the only interior evidence is one 200-row resubscribe snapshot on BTC/EUR, zero updates | `venue_silent` — 12/12 pairs byte-identical across a 98 s interior span, 90 updates |

So `00096` ships covering one of the two known cases, with the other correctly reading `undetermined`. Archiving status would close that half — and it is the half that covers the *hard halt*, the case where the venue emits nothing at all and cross-host therefore has no interior evidence to read. That is exactly the shape of a long outage, so the uncovered case is not the rare one.

## Findings so far

- Measured from the live ledger (`/mnt/zhao-crypto/capture-reconciled/reconcile-ledger.jsonl`, 99 records): four `both_streams_silent` records exist, totalling **21,887.369457 s** — which is the **entire** `residual_gap_seconds_total` today (no `total_loss`, no splice residual contributes).
- 2026-07-13 (2,661.788740 s) and 2026-07-27 (2,385.847992 s) book a single window each, so they have no interior span and read `undetermined` under `00096`. 07-13 was a Kraken WS 503 followed by a capture-side restart clobber ([[T0035]] / [[T0036]]) — a **capture defect**, and reading it `undetermined` rather than `venue_silent` is the correct true negative.
- The status counter's own comment records the read: series exist only for values actually seen, so the presence of anything other than `online` is itself the signal. It is a counter in Prometheus, not a row in the archive.
- Making the reconciler query Prometheus was considered and rejected while designing `00096`: a monotonic, unwalkbackable ledger must not depend on soft telemetry that may be unavailable or retention-expired at read time.

## Suggested next steps

- **Decide where archived status should live.** Two candidates, neither costed: a `status` kind alongside `book`/`trades` under the existing segment layout (`<BASE>/<QUOTE>/status/<YYYY>/<MM>/<DD>/<HH>.parquet`), which reuses the whole pull/verify/manifest path but is per-pair for a fleet-wide fact; or a single fleet-level status stream outside the per-pair tree, which models the fact correctly but is a new shape for every consumer of the archive layout to learn.
- **Check whether Kraken's status message carries a timestamp.** `cli/capture/command.py` logs `effective_time` — if that is venue-assigned, an archived status row inherits the same cross-host verifiability that makes `00096`'s discriminator sound, and two hosts recording identical `effective_time` is itself strong evidence. Read the field from a live message before designing around it.
- **Only then decide whether the reconciler consumes it.** Spec `00096` D1 rules that the booking never changes; a status input would extend the *verdict*, never the booked seconds. Re-read that ruling before wiring anything, and keep the verdict advisory.
- **Until this lands, the operator-facing path is the alert triage line** — `00096` D5 points a reader of an `undetermined` verdict at `zcrypto_capture_venue_status_total`. Verify that line survives any rewording of the alert.
