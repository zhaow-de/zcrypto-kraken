# 00076 — The archive verification instruments, re-fitted (T0097)

**Goal:** make `infra/scripts/continuity.py` measure silence and truncation against *measured* stream density instead of density-blind constants, and stop the daily `archive verify-replay` from paging forever on one historical bad hour — closing [[T0097]] in full.

## Why now

T0097's threshold leg was gated on "≥1 week of the T0092 BTC-quoted streams so the statistic is fitted, not guessed". Those streams began 2026-07-23 13:08 UTC; the week completed 2026-07-30, and the fit below was measured that day over the NFS mirror. The verify-replay leg was gated on "ripe when it first pages" — a wait-for-damage trigger retired here by construction instead (see D7).

## Current state, measured 2026-07-30

Over the full available span of four book streams on `/mnt/zhao-crypto/capture-segments` (340M rows):

| stream | hours | rows | median | p99 | p99.99 | max diff | current `thresh_s` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ETH/BTC | 170 | 21,966,496 | 0.000 s | 0.558 s | 3.119 s | 210.709 s | 31.19 s |
| SOL/BTC | 170 | 8,981,406 | 0.002 s | 0.937 s | 2.375 s | 210.316 s | 23.75 s |
| BTC/EUR | 530 | 204,910,012 | 0.000 s | 0.188 s | 0.835 s | 1550.803 s | 8.35 s |
| LINK/EUR | 530 | 105,080,143 | 0.000 s | 0.439 s | 2.443 s | 1550.875 s | 24.43 s |

Boundary crossings (last row of H−1 → first row of H, contiguous hours only):

| stream | n | median | p99 | max |
| --- | --- | --- | --- | --- |
| ETH/BTC | 169 | 0.312 s | 1.927 s | 2.352 s |
| SOL/BTC | 169 | 0.356 s | 2.138 s | 3.446 s |
| BTC/EUR | 529 | 0.094 s | 83.387 s | 3276.000 s |
| LINK/EUR | 529 | 0.307 s | 83.289 s | 3276.195 s |

Three facts follow, and they drive every decision below:

1. **The BTC-quoted streams are dense, not thin** — 36 and 15 rows/second. The ~2.3 s-spacing regime T0097 feared exists nowhere in production; the audit demonstrated it on synthetic trees. The head/tail defect is therefore *latent* for spacing, but **live for genesis hours**: ETH/BTC's genesis books 535.7 s and SOL/BTC's 535.3 s of false gap, and ETH/BTC's week currently reads ~0.13 % — **failing the T0003 exit bar on its genesis hour alone**.
2. **`10 × median` is refuted.** Book updates arrive in same-millisecond bursts, so the median is ~0 on every stream and the candidate collapses to the 5 s floor: 284 counted events / 2,061.7 s of phantom silence on a clean ETH/BTC week (0.34 % — a false FAIL), 221 events / 3,070.8 s on LINK/EUR. `20 × median` collapses identically. `10 × p99` is no better on the EUR streams (5.0 s floor, same 43/221 phantom events).
3. **The incumbent `p99.99 × 10` is the fitted winner on all four streams** — it counts 2–3 events per stream, and those events are the real July outages (the ~210 s event on the BTC-quoted pair, the ~47 s reconnect, the 1550 s EUR events). Its known failure mode is small-sample degeneracy, which D6 refuses rather than patches.

Non-genesis head offsets max 0.972 s (ETH/BTC) and 1.954 s (SOL/BTC), while the EUR streams carry 7 heads above 5 s whose crossings reach 3276 s — genuine restart-clobber signatures that must survive the change.

`archive verify-replay` currently: `ops_verify_replay_exit_code` = 0, and `max_over_time(...[30d])` = 0 — the entire unwindowed archive replays clean, and has for 30 days, including through the T0092 genesis hours of 2026-07-23.

## Decisions

**D1 — One continuous timeline per stream, replacing per-hour independence.** The interval sequence is the pooled intra-hour row diffs *plus* the crossing between temporally adjacent segments. Boundary truncation stops being a special case with its own constant and becomes an ordinary interval judged by the same derived threshold.

**D2 — The threshold formula is unchanged: `max(p99.99(pool) × 10, 5.0)`.** It is now fitted rather than inherited (see Current state). The pool it is computed over changes (D1), which moves it only marginally — crossings are ~0.3 % of the sample on every stream.

**D3 — `trunc` is redefined as boundary crossings above the derived threshold.** This replaces the fixed 5 s head test. It stays density-aware, so a 2 s crossing on a slow stream is no longer a truncation while the EUR streams' 3276 s crossings still are. The column keeps its name and its "MUST be 0" footer semantics.

**D4 — Missing hours are booked once.** For non-adjacent segments, `3600 × missing_hours` is booked as today; the crossing's excess over that span — `excess = crossing_seconds − 3600 × missing_hours`, i.e. the real tail+head silence bracketing the hole — is booked when it exceeds the threshold, and is **never pooled** (pooling known-outage intervals is the self-inflation mechanism T0097 identified). A booked excess counts as one truncation, same as D3.

**D5 — Genesis hours are annotated, never booked.** A stream's earliest hour *present in the tree* begins mid-hour by construction; its head is neither booked as gap nor pooled into the statistic, and the row is marked in the table. Genesis is determined from the unfiltered tree, **before** `--since` filtering, so a window starting after the genesis hour does not promote a later hour into a free pass. Accepted, documented caveat: on a partial pull whose earliest hour is not the true genesis, that one hour's head gets a free pass — bounded to one hour at the window edge, against today's guaranteed false-RED for every new stream.

**D6 — Below the degeneracy bound a stream is `UNMEASURED`, and an unmeasured stream fails the bar.** With polars' default nearest interpolation, `quantile(0.9999)` returns the element at `round(0.9999·(n−1))`, which is the maximum whenever `n ≤ 5001`; the threshold would then be 10× the worst outage — structurally blind. A stream with fewer than **5002** pooled intervals prints `UNMEASURED` in place of its `thresh_s` and `gap%`, keeping its factual columns (`hours`, `missing`, `n`), and **any unmeasured stream inside the window makes the verdict `EXIT BAR: FAIL (unmeasured streams: N)`** — including when *every* stream is unmeasured, where the run prints the FAIL verdict and no TOTAL row (`rc` 0: something was read, and the verdict carries the judgement). An empty tree or an empty `--since` window keeps today's `rc` 1 with **no** verdict line: nothing was measured, so nothing may bank one. A bar that silently ignores an unmeasurable stream is the same false-green shape the topic exists about. An unmeasured stream is **excluded from the TOTAL row's aggregation** and reported in its own count: a partial silence term must never be summed into a number that reads as complete. The bound is derived above and is pinned by a test that measures it empirically rather than trusting this paragraph.

**D6a — What `MIN_POOL` does and does not buy, stated exactly.** The bound guarantees only that `p99.99` is not the *maximum* — it protects against **one** outage-scale interval. Protection against `k` of them needs `0.0001·(n−1) ≥ k−0.5`, i.e. `n ≥ 10000k − 5000` (k=2 → 15,001; k=3 → 25,001). Measured margins on the live pools: BTC/EUR 20,491, LINK/EUR 10,508, ETH/BTC 2,197, SOL/BTC 898 — every production stream is orders of magnitude inside the safe regime. **The residual is real and is registered, not waved away**: a stream whose pool sits between 5,002 and ~15,000 intervals *and* which carries two similar outages still self-inflates its threshold and can under-count them. No machinery is built for it here (the robust-quantile alternative was weighed and declined for a regime no production stream occupies), the instrument's own `n` and `thresh_s` columns are the operator's evidence, and it is split out as its own topic rather than left inside a resolved one.

**D7 — SUPERSEDED 2026-07-30, the same day it shipped. The daily `verify-replay` does NOT run windowed; the change was reverted.** On real data the 7-day window failed 1,870 of 2,218 hours, all `anchored=False`: an hour is chain-anchored only if its predecessor is in the same enumeration, so a window cuts the chain — a fact `verify_replay`'s own docstring already stated and this decision did not read. Anchor-aware windowing was then measured and rejected too (EUR pairs carry 7 anchors in 537 hours, the newest 17 days old, so the lookback grows the healthier capture stays). The original concern — one historical bad hour paging forever — is instead answered by alerting on *newly*-failed hours, built in spec `00077`. The runtime motive is [[T0114]]. Original text follows, for the record:

> **D7 — The daily `verify-replay` runs windowed at 7 days.** `cli/archive/command.py` already implements `--pair` and `--since`; only the deployed runner (`infra/ansible/roles/ops/templates/verify-replay.sh.j2`) passes neither. The template computes a rolling `--since` at 7 days. Rationale: it matches the T0003 exit bar's own 7-day framing, gives a full week to act on a regression, and bounds a permanent hole to 7 days of paging instead of forever. **A hole found this way must be registered durably when triaged** (ledger record or topic) — an alert that ages out is not a record.

**D8 — Old hours falling out of the window are covered by a different instrument, and no weekly full sweep is built.** The hourly archive-pull hash-verifies every segment against its manifest, so corruption-at-rest in old data is caught there and more often; replay coherence for those hours was verified when they were fresh. Building a second, non-paging full sweep is machinery for a risk an existing instrument covers.

**D9 — A chain break on a quiet stream stays an error.** T0097 left this open. The measurement settles it: the unwindowed archive has replayed clean for 30 days across every pair and hour, so the "honest gap" case has never materialized. Nothing is built for it.

**D10 — The window's leading and trailing edges are judged by the derived threshold.** A first in-window hour that is not the genesis hour has no prior segment to cross from; its head is measured against the hour boundary and booked, counting as a truncation, only if it exceeds the threshold. The last in-window hour's tail is treated symmetrically — measured to the hour's end and booked only above the threshold, replacing today's fixed 1 s allowance. A genuine "restarted 40 minutes into the hour" at either edge stays visible; an ordinary start or stop on a slow stream does not fire.

## Non-goals

- No change to what the exit bar's numeric threshold is (`<0.1 %` gap time) — only to what is measured against it.
- No change to `--overlay` isolation: the canonical report still never prints a verdict line (spec `00050`).
- No change to the CLI's `verify-replay` implementation — the flags already exist.
- No robust-quantile machinery (linear interpolation, outage-exclusion iteration): D6 refuses the regime where a *single* outage sets the threshold, and D6a bounds and registers what remains, which is cheaper to explain at 3 a.m. than an iterative estimator.

## Verification

**Synthetic fixtures (unit).** Each constructed defect must be seen to trip the instrument before the fix is trusted:

1. Genesis hour: a stream beginning mid-hour books 0 gap and is annotated (today: ~3600 s + a truncation).
2. Two-density outage: an identical 200 s outage counts equally on a dense and a slow stream, for streams the instrument agrees to score. The fixture must sit inside D6a's safe regime — **one** outage among enough clean hours — because two outages in a ~11 k pool reproduce the false-GREEN *by design*, which is D6a's registered residual and not a defect of this fix.

   **Measured during execution, and it corrects this spec's own framing:** no fixture can make this case discriminate old code from new, because **the thin-stream false-GREEN is closed by refusal, not by better measurement**. The 200.1 s-vs-0.0 s divergence the topic recorded requires a stream sparse enough to self-calibrate its threshold into blindness — and that is exactly a stream D6 now declines to score at all. So this case proves density-independence of booking for *measured* streams; the defect class the topic opened is closed by D6's `UNMEASURED` refusal, and its regression carrier lives there. Of the boundary-model tests, only the genesis case separates old from new behavior (old: 539.6 s booked and one truncation; new: 0.0 s, none, annotated).
3. Restart clobber: last row early in H−1 plus first row late in H produces a crossing above the threshold, counted as one truncation and booked once.
4. Missing hour: `3600` booked, the crossing not double-counted, the crossing not pooled.
5. Degeneracy bound: `quantile(0.9999) == max` measured to hold at `n = 5001` and to fail at `n = 5002`, pinning D6's constant to observed behavior.
6. Small sample: a stream under the bound prints `UNMEASURED` and forces `EXIT BAR: FAIL` even when its measured gap is 0.
7. `--since` leading edge: a non-genesis first in-window hour with a late head is booked; an ordinary one is not (D10).
8. Empty window and empty tree keep their current returns (regression on the two legs already landed in PR #220).
Plus two checks that are not unit tests: the pre-existing `tests/test_continuity_overlay.py` fixtures are 120 rows/hour and would every one become `UNMEASURED` under D6 — they are migrated to dense-enough streams **preserving each test's original property**, since they are this instrument's existing regression carriers; and a one-time execution check that a synthetic canonical tree with one un-replayable hour exits 1 unwindowed and exits 0 when `--since` excludes it (D7's premise, exercising a CLI flag that already ships).

**Real-data acceptance (both directions), run against the NFS mirror before and after:**

- ETH/BTC's week moves from ~0.13 % (FAIL) to ~0.04 % (PASS) — the genesis hour stops being booked.
- The 7 genuine EUR-stream truncations survive as truncations.
- No stream's real counted outages (the ~210 s and ~1550 s events) are lost.

**Template render harness** for the `verify-replay.sh.j2` change: bash validity plus the rendered `--since` argument, following `tests/test_infra_archive_pull_template.py`'s precedent.

**Deploy verification (attended):** after the ops converge, the next daily tick reports `ops_verify_replay_exit_code` 0 with the windowed invocation visible in the unit's resolved `argv[]`.

## Risks

- **The instrument's verdict changes on real data by design.** This is the point (a false FAIL becomes an honest PASS), but it means the before/after acceptance run is the load-bearing check, not the unit tests.
- **D5's free pass** on a partial pull's first hour, as described.
- **D6a's regime residual** — bounded, measured, registered as its own topic; no production stream is within three orders of magnitude of it.
- **D7 narrows what is checked daily.** Named and mitigated by D8; the tradeoff is written into the rule text, not left implicit.
- The change touches the T0003 exit-bar instrument. It does not touch the capture path, the live trade path, or any canonical dataset — the script is read-only over a pulled copy.
