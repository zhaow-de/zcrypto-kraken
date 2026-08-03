---
status: resolved
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

- **The export is written 2026-07-28** on `docs/ops-converge-0728-record`: `archive-pull.sh.j2` writes `zcrypto_trade_backfill_hours_repaired_after_loss_total` beside the three series already in `trade-backfill.prom`. **Monotone, not a per-run gauge** — a gauge returns to 0 on the next run and erases exactly the evidence this exists to keep — so the previous value is read back and added, mirroring how `last_success` is already carried forward, and it is written on every run including a failed one (omitting a line deletes the series, a shape that already paged once). The run's output is captured to a temp file and replayed to the journal so the count can be parsed out; deliberately not a pipe, since the script sets `set -u` without pipefail and `docker run | tee` would report tee's status, making every failure read as success.
- **No keep-regex edit was owed** — the ops config already admits `zcrypto_trade_backfill_.*`. The name is nonetheless pinned in `OPS_REQUIRED` so narrowing that wildcard fails a test rather than silently dropping the series.
- **The template gained its first render harness** (`tests/test_infra_archive_pull_template.py`), which it lacked despite its own header recording a Jinja comment that once ended a backslash continuation mid-flags and produced valid bash with a broken `if`. It pins bash validity, the carry-forward arithmetic, unconditional writes, and the log parse — the last by running the real `sed` over a line in the CLI's own format, so wording drift on either side fails there.

## Resolution

**Resolved 2026-08-02 on the owner's ruling, taken against measurement rather than deferred again.** Both remaining sub-items closed:

**1. The exporter is deployed and confirmed** (superseding the "next ops converge" step). `c0b4bf3a` shipped it, PR #225 merged it, and two ops converges since have carried it. Read live from Grafana Cloud on 2026-08-02: `zcrypto_trade_backfill_hours_repaired_after_loss_total` = **0** — the series arrives, and in the **5 days** since it began exporting (converge 2026-07-28, first Cloud reading 2026-07-29) no repair-after-loss event has occurred. **Weight that honestly**: the counting logic (`fbfc8fa2`) is also 2026-07-28, so the counter is blind to everything before it — a 5-day zero, not a historical one. The first `ripe_when` leg never fired; what it can say is *not once since it could see*.

**2. The `is_total_loss` classification stays as it is.** The owner's ruling, and the reasoning is that **the asymmetry this topic was opened to protect has since been inverted by other work**. It was opened because a false positive is loud while a false negative is silent *and permanent*. Spec `00053`'s daily REST trade-backfill removed both halves of that: a hole is detected against Kraken's dense `trade_id` tape (provable, not inferred) and repaired within a day. Verified live rather than assumed — the backfill last succeeded 8.1 h before this ruling, and it is guarded by two rules that exist and were read in `alerts.yaml`, not remembered: `zcrypto-trade-backfill-stale` (a 2-day dead-man) and `zcrypto-trade-backfill-exit-nonzero`.

**What inverting the witness would have cost, measured on the current archive rather than quoted from July**: 6,420 book hours carry **10** with no trades sibling — AVAX/EUR 5, DOT/EUR 3, ETH/BTC 1, LINK/EUR 1, every other pair 0. That is **0.156 %**, consistent with the 1-in-898 measured at the original fix, and every one sits on a thinner pair — the signature of a quiet market, not a lost file. Ten pages of known-benign noise on the channel that guards unbackfillable data, and the count grows with each thin pair added to the universe.

**The residual, accepted as a conscious drop rather than parked** (per the owner's no-new-topics directive): a trades hour lost *beyond Kraken's public `/Trades` retention* is **unrepairable** — and it is still classified "nobody traded" by `is_total_loss`. But it is **not traceless**, and the first draft of this resolution wrongly said it was: gap detection is archive-local (`cli/trades/gaps.py` — "a hole in the sequence IS missing data — provable with no REST call"), so such an hour is re-detected on **every** daily run and recurs as `trades_unrecoverable` in the run summary. What it lacks is escalation, not visibility: exit 0, no page, no metric, no ledger entry. Truly traceless only outside the observed id span — before a pair's genesis or at the live tail, where nothing brackets the hole.

The residual's size is known rather than open: spec `00053` D5 records Kraken's retention as deep (*2025 data served, no urgency cliff*). That depth means a **recent** hour can never age into unrepairability — daily archive-local detection catches its loss months before retention could matter. What remains reachable is destruction of an hour **already older than the retention depth**, on both mirrors (bit-rot, deletion, a truncated rsync of the deep archive): unrepairable the moment it happens, no undetected window required, though still re-detected daily as `trades_unrecoverable`. Note the counter reading 0 is *not* evidence about this case: an unrepairable loss never increments it, by construction.

**Checked and benign, recorded so it is not re-chased**: SOL/BTC holds 237 trades hours against 235 book hours. Both streams end at the same hour; the difference is entirely at the start — trades genesis `2026-07-23 11:00`, book genesis `13:00`. Those two hours precede the book stream's first capture, so book's absence there is a beginning, not a hole — exactly the distinction `is_total_loss`'s "before" half exists to make, and `continuity.py` correspondingly reports `missing=0` for that pair.

Spec/plan: none — this iteration is a ruling on measured evidence, with no code change. The measurements are recorded in the closing commit.
