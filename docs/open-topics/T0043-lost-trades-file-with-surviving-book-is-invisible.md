---
status: partial
ripe_when: EITHER the first `hours_repaired_after_loss > 0` in the ops trade-backfill log — the signature is now built, so it is a real, observable trigger rather than the circular one this key used to disclaim — OR before the reconciled overlay feeds a paid/production consumer / before go-live, whichever comes first. The second leg is date-free but human-reachable; the first is the evidence the go-live decision most wants, since it is the only thing that can say how often a real loss actually happens
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

- **The attribution half is closed 2026-07-28 by commit `fbfc8fa2`** (shared carrier with [[T0087]]): `backfill()` now counts `hours_repaired_after_loss` — settled hours with **no** trades final, a **book** final for the same hour proving the connection was alive, and rows on Kraken's dense `trade_id` tape for them. That combination is the signature this topic named, and it is the one a quiet pair cannot produce. It is reported in both summary surfaces and logged at WARNING per pair: the archive is whole again, but the loss event is real and now leaves a trace. Two tests pin the false positive shut — an absent hour with no book witness, and an ordinary in-hour gap whose file exists, both count 0.
- **The data-loss half is closed by iter-100 (spec `00053`, 2026-07-16):** the daily REST trade-backfill detects a missing trades hour against Kraken's dense `trade_id` tape and repairs it, alerted by [[T0052]]'s staleness dead-man + exit-code rules. The expected-file check the first next-step proposed is superseded — REST comparison is strictly stronger (it checks against the venue's truth, not the capture host's own file list).

## Suggested next steps

- *(autonomous code, ATTENDED deploy)* **Export the counter — its only trace today is a journal line.** `infra/ansible/roles/ops/templates/archive-pull.sh.j2` already writes `trade-backfill.prom` (exit code + two timestamps); `hours_repaired_after_loss` belongs beside them as a low-severity QA series, because the sweep exits 0 on it and the next run reports 0, so the evidence lives only until the journal rotates. Two constraints: the deploy is an ops-node converge, and the Alloy keep-regex is an **allow-list** — a published-but-unadmitted series is dropped silently at remote-write.
- *(decision — go-live gate)* **Reconsider `is_total_loss`'s classification itself before the reconciled overlay ever feeds a paid or production consumer** (`ripe_when`), since that is the point at which loss attribution stops being an archive-forensics question and starts being a trading-input-trust question. The counter above makes the repair *visible*; it does not make the classifier able to tell silence from loss at detection time, and it is deliberately downstream of the repair — a loss the REST tape cannot serve is still classified as "nobody traded" and still leaves no trace. What to weigh then: whether the book witness should feed `is_total_loss` directly, at the cost of re-introducing the false positive the 2026-07-14 fix removed (1 in 898 real segment finals).
