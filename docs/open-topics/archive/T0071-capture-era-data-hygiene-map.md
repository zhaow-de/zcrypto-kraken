---
status: resolved
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

## Resolution (2026-07-21, /zcrypto-auto-exec)

**The map is built — `docs/reference/capture-era-data-hygiene-map.md` — and its central finding is a measured refutation of this topic's own premise.** The Context above assumed the desync-era archived book hours "contain whatever the unpruned book wrote." That is false: the archive stores Kraken's wire messages verbatim (`cli/capture/command.py` writes message-level `bids`/`asks`; the in-memory `OrderBook` only *detects*), [[T0008]] states it in bold ("**No data was ever lost.** … Only the *in-memory* reconstruction was wrong. So the archive is sound"), and every book-state product — the L2 panel included — is replay-built through the *fixed* pruning book (iter-098, first materialized 2026-07-15; trades and the reconciled book are unions/splices of the sound wire messages). The 810/468-vs-100 contamination was in-memory only; the 482/117/398→0 replay proves the desync-era tape reconstructs cleanly. *(The pre-review draft of this map inherited the false premise and issued an era-bounded depth EXCISE — the pre-push review killed it against T0008 and the capture code before anything merged.)*

So the map contains **no keep/flag/excise split by content era**: content caveats are era-independent (trades KEEP on [[T0050]]'s density proof; ranks 1–10 venue-CRC-verified; ranks beyond 10 never venue-verified in *any* era, corroborated by the 2,190/2,190 CRC verify-replay; liquidations pipeline-independent), and the era-dependent findings are **structural** — launch-day mess, ~200/day heal pocks, the hash-invisible T0036 truncation class (completeness lives in `continuity.py`, never manifests), the unrecorded single-host window 07-14 04:00:42 → secondary bring-up.

How the original sub-items disposed:

- *Build the map* — done, above. The practical delta runs **opposite** to the informal fallback: the "post-07-13 only (~9 days)" restriction is superseded by full-window admission (from 2026-07-08 13:00) for both the spread and depth legs.
- *Quick unblock* — mooted: [[T0014]]'s next steps now read the map first, full window.
- *Owner decision on excision* — mooted: nothing warrants excision, reader-side or physical.
- The boundary measurement was reframed as an optional **falsification probe** (registered in [[T0014]]): the map predicts *no* depth-metric discontinuity at 2026-07-14 04:00; finding one would contradict the soundness conclusion and reopen this topic.
