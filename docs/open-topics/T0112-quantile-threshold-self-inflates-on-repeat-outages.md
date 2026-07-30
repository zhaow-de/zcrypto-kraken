---
status: open
ripe_when: a real `continuity.py` run reports a book stream whose `n` column is under 15,001 — the instrument prints `n` and `thresh_s` on every row, so the trigger is read directly off its own output rather than inferred
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

- The regime bound `n ≥ 10000k − 5000` is arithmetic, not an estimate, and follows directly from nearest interpolation placing `quantile(0.9999)` at index `round(0.9999·(n−1))`.
- `MIN_POOL = 5002` is correct for what it claims (k=1) and is pinned by a test that measures polars rather than trusting a comment.
- The robust-quantile alternative (linear interpolation plus one outage-exclusion iteration) was weighed during spec `00076`'s design and **declined** for a regime no production stream occupies, on the grounds that an iterative estimator is harder to explain at 3 a.m. than a refusal.
- The operator's existing evidence is already on screen: `continuity.py` prints `n` and `thresh_s` per row, so a fragile derivation is visible — a `thresh_s` of 2,006 s beside a sub-second stream is self-evidently wrong to a reader who looks.

## Suggested next steps

- *(autonomous, on the trigger)* When a real run reports a stream with `n < 15001`, re-measure that stream's spacing distribution and decide between: (a) raising `MIN_POOL` to the k=2 bound of 15,001 — cheap, but refuses more streams outright; (b) the declined robust-quantile estimator; (c) annotating rather than refusing, since the `thresh_s` column already exposes the fragility.
- *(autonomous, cheap, independent of the trigger)* Consider printing the **tail depth** — how many pooled intervals sit at or above the p99.99 value — as a direct fragility diagnostic; a depth of 1 means one interval set the threshold. This was not built at `00076` to keep that change's scope to what the owner approved.
