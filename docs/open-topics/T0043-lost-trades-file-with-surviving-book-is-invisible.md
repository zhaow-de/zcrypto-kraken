---
status: open
ripe_when: a trades segment is ever found missing from a mirror while its book sibling is present (any manual audit, any consumer error), or before the reconciled overlay feeds a paid/production consumer
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

But it is a real gap, and a review (2026-07-14) confirmed there is **no compensating signal** anywhere in the stack:

- `infra/scripts/continuity.py` measures **book-only** gaps by explicit design ("trades legitimately go quiet, so they cannot measure uptime").
- `verify_tree` / the `.sha256` manifests validate only files that **exist** — there is no notion of an *expected* file whose absence is a failure.
- The `trade_deficit` QA path needs the secondary to hold *some* rows to union against, so a both-mirrors-absent hour never reaches it.

## Findings so far

- Fixed and verified in the same change: against 898 real segment finals from the production mirror, the old rule produced 1 false `total_loss`, the new rule produces 0.
- Confirmed at the source (`cli/capture/segment_writer.py`): an hour with zero events for a `(pair, kind)` never becomes `_current_hour`, is never finalized, and produces **no file at all** — never an empty `<HH>.parquet`. So "absent" and "empty" are the same thing on disk, which is precisely why absence alone cannot distinguish silence from loss.
- The counterpart gap for the **book** stream does not exist: book is continuous, so its absence really is darkness, and it is still judged on bracketing alone.

## Suggested next steps

- Decide whether an *expected-file* check is worth building: the capture side knows which `(pair, kind, hour)` it committed (the manifest sidecars exist per final). A cheap version is to assert, per pair+hour, that a `trades` final exists **iff** the capture host actually wrote one — i.e. compare the mirror against the source's own file list rather than against a bracketing heuristic. This turns "absent" into a checkable claim instead of an inference.
- Cheaper interim: have the reconciler emit a **low-severity QA metric** (not a page) counting `(pair, hour)` where the book final exists and the trades final does not, so the rate is at least *observable*. A sudden jump in that rate is the signature of real loss; the steady baseline is just quiet pairs. This is decision-support and needs no verdict.
- Reconsider before the reconciled overlay ever feeds a paid or production consumer (`ripe_when`), since that is the point at which a silent trades hole stops being an archive-quality question and starts being a trading-input question.
