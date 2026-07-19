---
status: open
ripe_when: before any research consumer reads the live-capture-derived datasets (the L2 panel, canonical trades, or a future trades→bars product) across the early-capture window — concretely, the T0014/T0024 spread calibration (~2026-07-22) should read this map first, and the T0065 reach round must
---

# Capture-era data-hygiene map — which early-capture windows are keep / flag / excise

## Context — what

The capture pipeline's first week (2026-07-08 → ~07-14) was also its bug-fixing week: the unpruned-book phantom desyncs ([[T0008]], fixed 07-13), the restart hour-truncation ([[T0036]], fixed 07-14), the rotation-timestamp trust ([[T0037]], fixed 07-14), the reconnect-503 crash ([[T0035]], fixed 07-14), and the trades losses later repaired by REST backfill ([[T0026]]/[[T0050]], repaired 07-16). Each fix came with its repair/recovery job — but those were run from the *pipeline's* perspective (files complete, manifests verify, CRC clean), not from the *research consumer's* perspective. This topic owns the consumer-side map: for each live-capture-derived dataset and each early window, a **keep / flag / excise** verdict, so research is never unknowingly trained or calibrated on the bug-era tape. Raised by the owner (work journal): *"wrong data is worse than no data — we may need to remove the inconsistent/wrong/unrepairable data before the date."*

## Why this matters

A statement like "everything after 07-08 is present and manifest-clean" is a pipeline claim, not a research claim. The desync-era book hours (07-08 → 07-13) were CRC-*failing* live and healed structurally, but their microstructure content (phantom levels at depth) is exactly what the spread/depth calibration ([[T0014]]/[[T0024]]) reads. If the bug-era windows bias spreads or depth-at-size, the cost model inherits the bias — and that model feeds the 6b go/no-go. The asymmetry the owner named applies: excluding a few days costs sample size; including corrupt days costs correctness silently.

## Findings so far

- The repairs that ARE consumer-grade: trades are REST-verified dense per `trade_id` archive-wide ([[T0050]]: gaps=0 missing=0 duplicates=0 vs the venue's own tape) — the trades stream needs no excision anywhere.
- The open question is the **book/panel side**: the depth-prune fix (07-13) eliminated phantom levels *going forward*; the archived book hours before it contain whatever the unpruned book wrote (structurally valid, CRC-checked against Kraken's own top-10 at the time — the phantom risk is below the checksum window, at depth > 10).
- The 1s L2 panel derives from the reconciled book, so any book-era verdict propagates to the panel hours derived from those windows.

## Suggested next steps

- **(autonomous analysis)** Build the map: per dataset (reconciled book, L2 panel, canonical trades, liquidations) × per window (07-08→07-13 desync era; 07-13→07-14 fix-rollout day; post-07-14 clean era), what bug could have touched it, what the repair proved, and the keep/flag/excise recommendation with evidence (e.g. compare depth-10-vs-100 spread stability across the 07-13 boundary — a discontinuity marks the bias).
- **(quick unblock for the ~07-22 calibration)** If the full map isn't ready in time, the calibration can proceed on post-07-13 data only (~9 days) and note the restriction — the conservative default that needs no verdict.
- **(owner decision)** Any actual excision of archived data is the owner's call (custody is immutable by convention — an excise verdict likely means a documented exclusion list consumed by readers, not deletion).
