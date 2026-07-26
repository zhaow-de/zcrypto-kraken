---
status: partial
ripe_when: before the reconciled overlay feeds a paid/production consumer, or before go-live — this is the OPERATIVE leg, date-free but human-reachable. The repaired-real-loss signature (the REST backfill minting a trades hour that did not exist while the pair's book final for that same hour did) is deliberately NOT a trigger clause: it becomes observable only once this topic's own metric is built, so listing it would be the same circular trigger [[T0073]] was just re-pointed off — it is the build's acceptance criterion, not its trigger. Re-pointed 2026-07-23 from "a trades segment is ever found missing from a mirror while its book sibling is present", which iter-100's backfill (spec `00053`) now silently REPAIRS against Kraken's dense `trade_id` tape — an observation the system was deliberately engineered not to produce
---

# A genuinely lost trades file is invisible when its book sibling survives

## Context — what

`is_total_loss` (`cli/archive/settle.py`) used to call any bracketed absence a permanent loss. On 2026-07-14 that fired for LINK/EUR trades hour 02 — ledgered as unrecoverable loss, logged at ERROR (so it paged), and booked 3600 s into the monotone `residual_gap_seconds_total`. It was false: LINK printed 8 trades in hour 01 and 9 in hour 04 and had **zero** in hour 02, while its **book** final for that same hour existed throughout, proving the connection was alive. Book updates are continuous; trades are prints, and a quiet pair genuinely goes an hour without one.

The fix passes the pair's book hours as an `alive_witness`: if the book committed a final for that hour, an absent trades hour means *nobody traded*, not *data was lost*.

**The residual this buys:** a trades segment that is genuinely **lost** (disk error, deletion, a silently-truncated rsync) while its book sibling survives is now classified as "nobody traded" — no ledger entry, no page, no `residual_seconds`. We traded a demonstrated false **positive** for a theoretical false **negative**.

## Why this matters

L2 capture is unbackfillable. A false positive is loud and costs an operator an hour of confusion; a false negative is silent and costs the data forever. That asymmetry is the reason this is written down rather than filed as "fixed and done".

The exposure is narrower than it first looks, and the narrowing is what makes the trade acceptable:

- The reconciler's `available` set for trades is already the **cross-host union** of both mirrors, so the blind spot needs the loss to hit **both** archives independently for the same pair+hour. A loss on one mirror only is still healed by the ordinary union path.
- A single-mirror loss is therefore *repaired*, not merely detected.

At review time (2026-07-14) there was **no compensating signal** anywhere in the stack — `infra/scripts/continuity.py` is book-only by design, `verify_tree`/manifests validate only files that exist, and the `trade_deficit` QA path needs the secondary to hold *some* rows. **Superseded 2026-07-16 (iter-100, spec `00053`): the daily REST trade-backfill IS now that compensating signal for the data itself.** It compares the archive against Kraken's REST tape (dense per-pair `trade_id`, so a hole is *provable*, not inferred), repairs any missing trades, and is staleness/exit-code-alerted ([[T0052]]). A trades hour lost on both mirrors is therefore **detected and repaired within a day** — the false negative no longer costs the data forever.

## Findings so far

- Fixed and verified in the same change: against 898 real segment finals from the production mirror, the old rule produced 1 false `total_loss`, the new rule produces 0.
- Confirmed at the source (`cli/capture/segment_writer.py`): an hour with zero events for a `(pair, kind)` never becomes `_current_hour`, is never finalized, and produces **no file at all** — never an empty `<HH>.parquet`. So "absent" and "empty" are the same thing on disk, which is precisely why absence alone cannot distinguish silence from loss.
- The counterpart gap for the **book** stream does not exist: book is continuous, so its absence really is darkness, and it is still judged on bracketing alone.

## Done so far

- **The data-loss half is closed by iter-100 (spec `00053`, 2026-07-16):** the daily REST trade-backfill detects a missing trades hour against Kraken's dense `trade_id` tape and repairs it, alerted by [[T0052]]'s staleness dead-man + exit-code rules. The expected-file check the first next-step proposed is superseded — REST comparison is strictly stronger (it checks against the venue's truth, not the capture host's own file list).

## Suggested next steps

- **The residual is loss-event *attribution*, not loss:** `is_total_loss` (`cli/archive/settle.py`) still classifies a genuinely lost both-mirrors trades hour as "nobody traded" — no ledger entry, no page — and the backfill then repairs it *silently*, so a real infrastructure loss event (disk error, truncated rsync) leaves no operator-visible trace of ever having happened. Cheap fix when ripe: a **low-severity QA metric** counting `(pair, hour)` where the book final exists, the trades final doesn't, and the backfill later inserted rows for it — that combination is the signature of a repaired real loss, distinguishable from quiet pairs (which the backfill never touches).
- Reconsider before the reconciled overlay ever feeds a paid or production consumer (`ripe_when`), since that is the point at which loss attribution stops being an archive-forensics question and starts being a trading-input-trust question.
