# 00079 — `continuity.py` refuses a contaminated tail instead of trusting it

**Goal:** close [[T0112]] in full: a pool whose extreme tail is set by repeat outages is refused (`UNMEASURED`, exit-bar FAIL) instead of silently deriving a threshold 10× the outage and booking 0.0 s of gap — at **every** pool size and **every** outage count up to a named, accepted residual. Plus the tail-depth diagnostic T0112's second sub-item asked for.

## Why now, without the trigger

T0112's `ripe_when` (a real run reporting `n < 15,001`) is drifting **away**: `n` grows with capture, and the two newest streams (T0092) turned out dense. Waiting means the defect stays alive precisely for the case that can still reach it — a narrow `--since` window on a slow stream, which is a legitimate ad-hoc investigation shape. The owner directed: resolve now, handle tail depth anyway, and use synthetic data where the reachable path cannot drive validation.

## Current state, measured (all numbers from this iteration's probes, 2026-08-02)

**The defect (from `00076`'s cold review, reproduced):** `thresh = max(p99.99(pool) × 10, 5.0)`; `MIN_POOL = 5002` guards exactly k=1 outage-scale interval because nearest interpolation puts `quantile(0.9999)` at `round(0.9999·(n−1))`. A pool with n=11,389 and **two** ~200 s outages passes `MIN_POOL`, lands p99.99 **on** the second outage, derives `thresh_s ≈ 2,000`, and books **0.0 s** while the dense arm of the same fixture books 400.2 s.

**Tail depth cannot detect this.** Measured: at n=11,389 the count of intervals ≥ p99.99 is **2 whether the pool is clean or contaminated** — depth is a deterministic function of n (≈ tolerated-k + 1), not of contamination. It is a transparency diagnostic only. (Real streams, for scale: depth 25–390 at n = 240k–3.9M.)

**What does discriminate: tail steepness.** `p99.99 / p99.9` on realistic bursty spacing (same-ms bursts, median = 0 — the T0097-measured shape that already refuted any median-based statistic):

| case | q/p99.9 |
| --- | --- |
| 12 **real** production streams, last 48 h each (n = 240k–3.9M) | **1.05 – 1.96** |
| legit pathological synthetics: pareto α=1.1, lognormal σ=3, bimodal | 3.4 – 4.5 |
| contaminated (k=2 @ n=11,389; k=20 @ n=50,000) | **88.8 – 200** |

Two orders of magnitude of separation, robust across n and k, with the worst *legitimate* case 2.2× under the proposed cut and the mildest *contamination* 9× over it.

## Decisions

**D1 — Two chained tail-steepness ratios, one cut.** A measured stream must satisfy **both** `p99.99/p99.9 < TAIL_RATIO_CUT` and `p99.9/p99 < TAIL_RATIO_CUT`, with `TAIL_RATIO_CUT = 10.0`. The first ratio catches p99.99 landing on an outage (k from 2 up to ~0.001·n, where p99.9 is still bulk); the second extends coverage to p99.9 itself being contaminated (k up to ~0.01·n). Why 10: it is the per-decade quantile ratio of a Pareto tail at α = 1 — the infinite-mean boundary no physical spacing distribution crosses — so legitimately-heavy tails sit well inside (measured ≤ 4.5) while a cliff from same-scale outages jumps to ~100. One constant, same value both decades, explainable at 3 a.m.: *the tail must not steepen more than 10× across a decade of quantiles*.

**D2 — Denominators are floored at 0.5 s, tied to the existing 5.0 s threshold floor.** Ratio = `q_hi / max(q_lo, 0.5)`. An ultra-bursty pool can legitimately have `p99.9 = 0` (same-millisecond bursts), and dividing by it would refuse a healthy stream. 0.5 is not a new magic number: it is `5.0 / 10` — the spacing scale below which the threshold floor already declares steepness irrelevant. Consequence, deliberate: a sub-millisecond stream with two 200 s pauses **is** refused (`200 / 0.5 = 400`) — and should be, because the alternative was scoring it with a 2,000 s threshold.

**D3 — `MIN_POOL = 5002` is unchanged, and both gates are required.** The ratio test runs only on pools that already pass `MIN_POOL` (below it the stream is refused today, unchanged). Nothing T0097 fitted is re-fitted; no currently-measured stream's verdict changes (Verification pins this against the real archive).

**D4 — Refusal is `UNMEASURED` + exit-bar FAIL, exactly like the `MIN_POOL` refusal.** A contaminated threshold's output *is* the false GREEN (0.0000 % beside missing data), so printing it with a caveat would print the lie. The two refusal reasons are distinguishable in the post-table note — the existing `no measurable segments: N stream(s) under the <bound>-interval bound` line gains a sibling naming the steepened-tail count in plain operator language (this is runtime output of an infra script: **in scope** for `operator-facing-text.md`, so no topic/spec tokens).

**D5 — The tail-depth column is printed for every row, labeled as transparency, never as detection.** New column `tail` = count of pooled intervals ≥ the pool's p99.99 value. Depth 2 beside n=11,389 tells the reader "one or two intervals set this threshold" — visible fragility, per T0112's second sub-item. The code comment must state what this spec measured: **depth is provably not a contamination detector** (identical when clean and contaminated), so nobody later "promotes" it into a gate.

**D6 — The residual, named and accepted rather than deferred.** k ≥ ~0.01·n similar outages contaminates p99 itself; both ratios then read ≈ 1 and the gate is blind. Accepted because the regime is absurd for the narrow-window case it would need: at n=11,389 that is ≥ 114 outages of ~200 s — ≥ 6× the window's total wall time — and long before that, the missing/truncated-hour checks (which do not depend on the derived threshold) light up, the pool's own `n` collapses, and `covered_s` visibly disagrees with the span. No production stream is within three orders of magnitude of even the k=2 regime. This is a conscious drop recorded here and in the gate's code comment — not a deferral, per the owner's no-new-topics directive.

**D7 — Validation is split by what each data source can prove.** The reachable real path (a 2-hour `--since` window on ADA/EUR lands in the 5k–15k regime) cannot summon two genuine outages, so: **synthetic fixtures prove the true positives** — the exact k=2 @ n=11,389 construction from `00076`'s cold review (which must flip from `thresh_s ≈ 2,006 / 0.0 s booked` to `UNMEASURED`), plus a k≥0.001·n case that only the second ratio catches; **real data proves the absence of false positives** — the 12-stream measurement above, plus an acceptance run of the NEW code against the full production archive expecting zero refusals and identical verdict columns (`thresh_s`, `gap_s`, `gap%`) for every currently-measured stream — the *lines* differ by the new `tail` column, the *verdicts* must not. Neither source alone is a validation.

## Non-goals

- The robust-quantile estimator (declined at `00076`, still declined — a refusal is explainable; an iterative estimator is not).
- Raising `MIN_POOL` (strictly worse than D1: refuses more, catches less).
- Any change to what counts as silence, the ×10 multiplier, the 5.0 s floor, or the T0097-fitted statistic.
- Scoring-with-caveat output modes (rejected in D4).

## Verification

Every guard proven by constructing its defect — the previous two iterations shipped a combined nineteen guards that could not fail, so reading assertions is not verification.

- **The founding defect flips**: the k=2 @ n=11,389 fixture that today derives `thresh_s ≈ 2,006` and books 0.0 s must report `UNMEASURED` and fail the exit bar. Run against the **pre-change** module first to confirm it reproduces the 2,006/0.0 behaviour (the defect is real), then against the new code (the fix bites).
- **The second ratio is load-bearing**: a fixture with k ≈ 0.002·n outages (p99.9 contaminated, p99.99/p99.9 ≈ 1) passes the first ratio and must be caught by the second; removing the second ratio must fail exactly this test.
- **No false positives on legitimate shapes**: bursty-typical, pareto α=1.1, lognormal σ=3, bimodal fixtures all stay measured (ratios ≤ ~4.5 vs cut 10).
- **The floor (D2)**: an ultra-bursty pool with p99.9 = 0 and a benign p99.99 stays measured; the same pool with a 200 s tail is refused; dividing never raises.
- **Boundary**: n exactly 5002 with a clean tail stays measured (both gates pass independently).
- **Depth is not a detector, pinned as a test**: assert equal depth for the clean and contaminated n=11,389 fixtures — the test that documents WHY depth is not a gate, so its non-use survives review.
- **Verdict-regression on real data (acceptance, host-touching — orchestrator runs it in the main loop)**: the new `continuity.py`, run via the pinned ops image against the NAS archive read-only, reports **all 12 streams measured** with `thresh_s`/`gap_s`/`gap%` identical to the shipped version's output on the same input. This is D3's "nothing changes for currently-measured streams" made into evidence, and D7's no-false-positive half on production data.
- Mutation-proofs: cut widened to 1000 → contaminated fixture passes (test fails); ratios reordered/dropped → named tests fail; depth column removed → its test fails.

## Risks

- **A future legitimately-steep stream** (a venue that batches at exactly one scale) could exceed 10× per decade and be refused. Acceptable: the refusal is loud, names the ratio, and `UNMEASURED` fails the bar — an operator investigates instead of trusting a possibly-poisoned threshold. The margin today is 5× on real streams.
- The ratio depends on polars' nearest interpolation (same dependency the existing bound has); the tests measure polars rather than trusting comments, as `MIN_POOL`'s already do.
- `continuity.py` is consumed by capture-verification runbooks; output gains one column and one refusal note — `capture-deploys.md`'s reference to the script names no column layout, so no rule edit is owed.
