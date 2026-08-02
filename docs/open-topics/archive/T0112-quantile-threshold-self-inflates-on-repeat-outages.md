---
status: resolved
---

# The derived threshold still self-inflates when a small pool carries repeat outages

## Context — what

Split out of [[T0097]] at spec `00076`'s cold review, which constructed the case rather than reasoning about it. `continuity.py` derives its silence threshold as `max(p99.99(pool) × 10, 5.0)`, and D6 refuses any stream with fewer than 5,002 pooled intervals because below that bound polars' nearest-interpolation `quantile(0.9999)` **is** the maximum — the threshold would be 10× the single worst outage.

That bound buys protection against exactly **one** outage-scale interval. The general condition is `0.0001·(n−1) ≥ k−0.5` for `k` such intervals, i.e. `n ≥ 10000k − 5000`: k=2 needs 15,001 intervals, k=3 needs 25,001. A stream sitting between 5,002 and ~15,000 intervals that carries **two** similar outages therefore passes the D6 gate, has its p99.99 land on the second outage, and under-counts both.

Measured during the review: a 0.6 s-spaced fixture with n=11,389 and two ~200 s outages booked **0.0 s** of silence at a derived threshold of 2,006 s, while the dense arm of the same fixture booked 400.2 s.

## Why this matters

This is the same false-GREEN class T0097 exists about — an instrument reporting no gap while data is missing — surviving in a narrower regime after that topic's fix. It matters less than it sounds and more than nothing:

- **No production stream is anywhere near it.** Measured 2026-07-30 over the full available span: BTC/EUR tolerates 20,491 outage-scale intervals before self-inflating, LINK/EUR 10,508, ETH/BTC 2,197, SOL/BTC 898. The live fleet is three orders of magnitude inside the safe regime.
- **The reachable path is a narrow `--since` window on a slow stream**, or a genuinely thin stream that does not exist today (the T0092 BTC-quoted pairs turned out dense — 36 and 15 rows/second).
- The instrument is the **T0003 exit-bar** gate, so a wrong verdict here is a wrong statement about unbackfillable L2 data.

## Findings so far

- The regime bound `n ≥ 10000k − 5000` is arithmetic, not an estimate, and follows directly from nearest interpolation placing `quantile(0.9999)` at index `round(0.9999·(n−1))`. *(Re-derived at spec `00079`: polars' nearest rounds half **up**, so the k=2 bound is 15,002 rather than 15,001 — immaterial, since the shipped gate supersedes the n-bound entirely.)*
- `MIN_POOL = 5002` is correct for what it claims (k=1) and is pinned by a test that measures polars rather than trusting a comment.
- The robust-quantile alternative (linear interpolation plus one outage-exclusion iteration) was weighed during spec `00076`'s design and **declined** for a regime no production stream occupies, on the grounds that an iterative estimator is harder to explain at 3 a.m. than a refusal.
- The operator's existing evidence is already on screen: `continuity.py` prints `n` and `thresh_s` per row, so a fragile derivation is visible — a `thresh_s` of 2,006 s beside a sub-second stream is self-evidently wrong to a reader who looks.

## Resolution

**Resolved 2026-08-02 by spec `00079`** — not on this topic's `ripe_when` trigger, which was drifting *away* (`n` grows with capture and the two newest streams turned out dense), but on the owner's direction to close it while the reachable path — a narrow `--since` window on a slow stream — still exists. Both sub-items close.

**Detection (sub-item 1), commit `3cb40407`.** A measured stream must now satisfy **both** `p99.99/p99.9 < 10` and `p99.9/p99 < 10`, denominators floored at `RATIO_FLOOR_S = 0.5` (= `5.0 / 10`, the spacing scale below which the existing threshold floor already declares steepness irrelevant, so an ultra-bursty pool with `p99.9 = 0` is not refused for being fast). A stream failing either ratio is `UNMEASURED` and fails the exit bar, exactly like the `MIN_POOL` refusal. Two chained decades because one does not span the range: the first catches p99.99 landing on an outage, and once k reaches ~0.001·n p99.9 is contaminated too and reads ≈1, from where only the second ratio still spans the cliff. The cut is 10.0 because that is the per-decade quantile ratio of a Pareto tail at α=1, the infinite-mean boundary no physical spacing distribution crosses.

The founding defect flips, reproduced against the unmodified pre-fix module first so the defect was shown real before the fix was shown to bite: the carved k=2 fixture derived `thresh_s = 2004.0`, booked `0.0 s` of intra-hour silence and returned `EXIT BAR: PASS` over 401.4 s of genuinely missing data; the k=1 control on the same geometry derives `thresh_s = 6.0`, books 200.4 s and FAILs — so the *second* outage, not the fixture's geometry, is what breaks the instrument. Under the new code the k=2 fixture reports `UNMEASURED` and FAILs.

No false positives on real data: the acceptance run put the new and shipped scripts through the **same** pinned ops image against the NAS archive read-only, and all 20 output lines are identical once the 7-character `tail` slot is removed. All 12 streams measured in both, zero `UNMEASURED` rows, zero refusal notes; real-archive tail-steepness margin is 5× (production streams measure 1.05–1.96 against the cut of 10, contamination 88.8–200).

**Transparency (sub-item 2), commit `ceb927aa`.** The `tail` column ships — the count of pooled intervals reaching p99.99, i.e. how many data points the derived threshold rests on. It is labeled transparency and never a gate, because this iteration **measured that it cannot be one**: at n=11,389 a clean pool and a pool carrying two 200 s outages both have depth 2, since the count at or above p99.99 is a deterministic function of n (≈ the tolerated k, plus one) and not of contamination. That equality is pinned by a test, so promoting depth into a gate requires first deleting the test that disproves it. On a tie-free pool depth is exactly `round(0.0001·(n−1)) + 1`; a large depth on a tie-heavy pool is a tie artifact (a fixture reading 11,999 drops to 2 under 10 ms of jitter).

**The three options this topic suggested are each disposed of, none taken.** (a) Raising `MIN_POOL` to the k=2 bound is a spec `00079` Non-goal — strictly worse than the ratio gate: it refuses more streams and still catches only k=2. (b) The robust-quantile estimator stays declined, for the reason `00076` first gave. (c) Annotating rather than refusing was rejected in `00079` D4: a contaminated threshold's output *is* the false GREEN, so printing `0.0000 %` beside missing data with a caveat attached would print the lie.

**The D6 residual is a conscious drop, recorded here with its bound — not a deferral, and no successor topic exists.** At k ≥ ~0.01·n similar outages p99 itself is contaminated, both ratios read ≈1, and the gate is blind. The boundary was constructed rather than estimated: blindness begins at exactly k=115 for n=11,389, and k=114 is still caught (second ratio 53.4). Accepted on the absurdity of the regime — reaching it requires the measured window to be **77–97 % outage** by wall time (23,000 s of silence against 619–6,764 s of data, depending on spacing shape), which no investigation shape survives unnoticed; the on-screen `n` beside the window's span is the eyeball check. **The truncated-hours count is explicitly NOT a backstop** — the cold review disproved it: it tests `secs > thresh`, so the same contaminated threshold that blinds the gap accounting blinds it too. Missing-hours needs a geometry these mid-hour outages never produce, and `covered_s` is span-derived and cannot disagree with the span. The drop is recorded at the gate in `infra/scripts/continuity.py` as well as here.

**Also landed on the same branch**, since they were found while proving the above: the refusal note now prints whenever *any* stream was refused rather than only when nothing at all was measurable (in production a contaminated stream sits beside measured ones, which is exactly where its reason is least guessable), and its prefix moved from `no measurable segments: ` to `unmeasured: ` (commit `2c73f0f2`) — the earlier wording became false the moment the note could appear beside a TOTAL row aggregating a measured stream.
