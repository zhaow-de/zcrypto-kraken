---
status: partial
---

# The soak report averages a specified HHI sentinel as though it were a measurement

## Context — what

`structural_metrics` (`cli/engine/soak.py:65`) computes a per-bar concentration `hhi = Σ_a (|w_a|/gross)^2` and returns `0.0` for a bar whose gross is at or below `1e-12` — a branch recorded as the design at `docs/plans/00058-soak-check-oos-report.md:52`. That `0.0` is a sentinel, not a measurement: `docs/specs/00059-soak-check-realized-governor-cap-design.md:49` states HHI's lower bound is `1/n > 0`, so no measured bar can produce it, and a reader of one bar can always tell unmeasurable from measured. The site is sound.

`analyze_soak` is not. Its gating loop (`cli/engine/soak.py:998-1010`) takes `_mean(live_series)` over the realized per-bar `hhi` list and hands the null's list to `windowed_null` and `block_bootstrap_null` (`:950-956`), none of which knows the value is out of range. A flat bar inside an otherwise active window contributes `0.0` to the mean and pulls the concentration figure toward *better diversified than anything measured*. `hhi` is one of the seven gating verdicts under spec `00059` D6 (`_METRIC_ROWS`, `soak.py:1201`), so the figure is one the go-live decision reads.

The all-flat case is already detected — `test_analyze_soak_degenerate_zero_exposure` (`tests/test_engine_soak.py:878`) drives six all-zero-weight bars through the branch and asserts `is_degenerate`. The defect is the mixed window: some flat bars among active ones, which nothing flags.

Split out of `T0183` because it is not a member of that family. `T0183`'s members return a value the metric can genuinely take, so nothing downstream can tell the empty case from a measured one; here the site returns a value the metric excludes, and the consumer is what fails to honour that.

## Why this matters

`soak_report` is the instrument the go-live decision reads. A fabricated number there cannot place a trade — `soak_report` is reached only by the offline `soak-check` command and the file places no order — but it can steer whether trades are placed at all. A concentration figure biased toward *well diversified* is the one that says the book is more diversified than it is at exactly the moment someone decides to go live. That makes this worse than `T0183`'s members rather than milder, and it is why it takes its own decision instead of a quiet fix.

Fixing it moves a gating verdict: excluding unmeasurable bars from the aggregate changes that metric's window and its `effective_n`. No HHI figure has been published in any research report or decisions log — the only occurrences under `docs/` are the spec and plan that define it — so nothing recorded is invalidated, but the number a future soak reports will differ from what the current code would have said.

## Findings so far

- The per-bar site is correct and specified; the defect is entirely in aggregation. `bar_hhi` stays `0.0` on empty gross: three consumers need floats, and `windowed_null` slices contiguous windows, so the per-bar lists must stay parallel — `None` is not a drop-in there.
- The meaning-preserving fix is to exclude out-of-range bars from the aggregate rather than average them, which leaves the specified sentinel untouched and changes only what the consumer does with it.
- This is `T0183`'s general form applied to a consumer: a sentinel still produces that family's failure the moment something aggregates it without knowing it is one. The question at this site is not what the empty branch returns but whether every consumer knows the value is out of range.

## Done so far

**The bias is measured, and it sits in the null, not the realized series.** Method: the repo's own `select_clean_segment`, `realized_series`, `build_null`, `structural_metrics` and `windowed_null`, so the bars counted are the bars `analyze_soak` scores. Journal read from the NAS replica mounted at `/mnt/zhao-crypto/engine-journal`, proved byte-identical to the engine host's authoritative copy by a digest over every `cycle-*.json`; price store pulled from the engine host, which has no replica; null built from `data/ohlc-full`. The journal covers 2026-07-11 to 2026-09-08.

- **Realized: the mixed window does not occur.** 359 records, one clean segment, 358 scored bars, none with `gross <= 1e-12`. The smallest gross observed is 0.0124 and the median 0.0563, so the live series is ten orders of magnitude clear of the branch. Both means agree to full precision at 0.218789155877, and the realized figure carries no bias today.
- **Null: 3680 of 27337 bars are sentinels, 13.46% of them.** They are structural rather than scattered — a 181-bar leading run where the system holds nothing, then 77 further runs, the longest 337 bars.
- **The null's concentration mean is 0.323623297632 as shipped and 0.373965003480 over its active bars**, a downward bias of 13.46% relative. `windowed_null` at the realized length of 358 draws 26980 window statistics, of which 13305 — 49.31% — contain at least one sentinel bar; that distribution's mean is 0.325167903 as shipped against 0.370518180 sentinel-free.
- **The verdict barely moves at today's realized value, and that is a coincidence of where it sits.** The realized mean falls at the 30.55th percentile of the shipped windowed null and the 29.99th of the sentinel-free one. It is far below both, so the shift does not change its standing; a realized value nearer the null's centre would not be so lucky.

This reverses the topic's original framing. The consumer defect is real and its size is now known, but it is the null series that carries it, so the defect is in what the realized figure is COMPARED AGAINST rather than in the figure itself.

**Five candidate aggregations were measured and adversarially checked; none survives.** Each was scored on the cached series by one analyst and one reader instructed to break it, on a 1-to-5 scale where 5 is clearly right.

| candidate | after the adversarial read | what kills it |
|---|---|---|
| drop sentinel bars from each series before aggregating | 3 | 77 splices, 41.31% of windows non-contiguous, and a concentrated live book moves from `inconsistent` to `indeterminate` |
| average each window over its active bars only | 1.5 | makes the over-concentration arm unfireable: 6.57% of windows pin at HHI's ceiling of exactly 1.0, so the null's p95 IS the ceiling |
| drop whole windows containing a sentinel | 1 | trades a 13.46% bias for a 36.49% one in the same direction |
| make the sentinel non-finite | 1 | renders a spurious `inconsistent` with a NaN band and invalid JSON, and all 143 soak tests stay green through it |
| change nothing | 1 | the offset is measurably not constant, so the note that would make the keep safe cannot be written without computing the corrected number anyway |

The keep's premise is a constant offset, and the bootstrap arm's p5 offset moves from +0.1188 to +0.0478 across dataset prefixes, so it is not one. The first candidate's band widening is the one to see in full: its upper edge moves from 0.663 to 0.921, its widest window spans 180 calendar days against the realized 60, and `effective_n` under the third candidate re-selects itself toward `n/a` as the soak lengthens.

**Three findings reframe the ruling.**

- **The `0.0` was never decided.** It is a one-line formula under *Signature detail* in `docs/plans/00058-soak-check-oos-report.md`, with no rationale and no alternative considered; the owning spec never mentions the empty case. A ruling here is a first ruling, not a reversal, and `00058`, `00059` and `00061` carry no `spec_hash` in the trial registry, so it lands in the spec that owns it.
- **The non-finite candidate is struck by a decision already on record.** An internal contract violation must abort rather than appear in the verdict column as a data finding.
- **Trimming the null's warm-up is not the fix.** It removes 4.28% of the bias and moves the realized percentile from 30.55 to 30.75, away from where sentinel removal puts it. Worth doing because 181 bars in which the system cannot hold anything are a null of nothing, but it must not be booked as addressing this defect.

**The dominant problem is not the sentinel.** The null spans 2013-09-10 to 2026-03-31 and pools two different strategies. Its first decile is 50.04% sentinel with an active-bar concentration mean of 0.9584 — a near-single-name book held half the time; its last five deciles run 1.90% to 12.29% sentinel with means from 0.1770 to 0.2749. Only the late era resembles the live series, which is active in 358 of 358 bars. The sentinel has been acting as an accidental down-weight on the early era, and every candidate that removes it un-weights a strategy the engine no longer runs: of the windows above the shipped 95th percentile after that correction, 54.7% begin in the null's first decile and none at all in its second half.

**The realized side is live-reachable, so any fix must be symmetric.** 8.36% of full-basket-era null bars are flat and 53.72% of windows of the realized length contain one. Today's clean realized series is luck, not structure.

## Suggested next steps

The measurement that fed the decision is done and recorded above; what remains is the ruling and the fix.

- **Rule on the null's span before ruling on the aggregation** (the owner's). Every candidate above was scored against a null that pools two strategy eras, and the scores move if the null is restricted to the era that resembles the live system. Measuring that is autonomous and uses the cached series. Until it is answered, an aggregation ruling is being made against a reference the live engine does not correspond to.
- **Then rule on the aggregation** (the owner's — it changes a number a go-live decision reads). The recommendation stands and the measurement sharpens where it bites: exclude unmeasurable bars from the mean and from the null series passed to `windowed_null` and `block_bootstrap_null`, with the metric's `effective_n` recomputed over the bars that remain. The null is where the 13.46% sits, and half its windows are affected, so a fix that only guarded the realized mean would change nothing measurable today. The alternative is a conscious keep with the measured bias recorded beside it, which costs a concentration comparison that reads 13% better diversified than the null actually is.
- **Implement with a test that constructs the mixed window** (waits on the ruling): a fixture with active bars and one flat bar, asserting the `hhi` mean equals the mean over the active bars alone and that `effective_n` counts only those — constructed so it fails against today's code — with the all-active and all-flat cases beside it. The measurement says the fixture must exercise the NULL path as well as the realized one, since that is the arm carrying real sentinels.
