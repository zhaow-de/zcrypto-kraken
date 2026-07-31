---
status: resolved
---

# The archive verification instruments have measurement defects

## Context — what

Registered 2026-07-23, split out of [[T0092]]'s 15-agent pre-flight audit. The audit set out to check whether adding BTC-quoted capture would break any consumer; what it actually found is that two of the instruments we *verify rollouts with* have defects of their own — independent of T0092, and pre-existing.

Both live in `infra/scripts/continuity.py`, the script `.claude/rules/capture-deploys.md` names as the post-converge outcome check, plus one in the daily `archive verify-replay` run.

## Why this matters

An instrument that reports green while data is missing is the failure class this project has been bitten by repeatedly — and `capture-deploys.md` currently instructs an operator to trust exactly this script after touching an unbackfillable pipeline. The T0092 rollout had to be verified by direct inspection instead, which is fine once but is not a standing answer.

## Findings so far

All measured by the audit's verifier agents, each reproduced rather than argued.

- **Silence detection is self-calibrating, so it can go blind (false GREEN).** `continuity.py:119`: `thresh = max(float(secs.quantile(0.9999) or 0) * 10, 5.0)`. Two mechanisms compound: polars' `Series.quantile` defaults to `interpolation='nearest'`, so below ~5001 samples `quantile(0.9999)` **is** the maximum (crossover measured between n=5001 and n=6000); and the pooled diffs at `:117` include the outage itself, so the outage sets the max and the threshold becomes 10× the outage. Reproduced: an identical 200 s outage counted `200.1 s` on a dense stream and **`0.0 s`** on a thin one (thresholds 18.71 s vs 2273.48 s).
- **A candidate fix was tested and refuted.** Clamping to `min(max(q*10, 5.0), 60.0)` produces 143 windows / 12,359.6 s / **28.61 % phantom gap** on a clean thin stream — an unconditional exit-bar FAIL. `10 × median` measured workable (thin 779.8 s counted, dense unchanged at 200.1 s) while `20 × median` and `10 × p99` both collapse to 0.0 — but the multiplier must be **pinned from real data**, not guessed.
- **The hour-boundary head/tail test is density-blind (false RED).** `continuity.py:106-110` uses a fixed 5 s head threshold and a 1 s tail allowance, while hours are partitioned by message timestamp — so the first row always lands one inter-message interval into the hour. Measured on a 24 h five-stream tree with **zero** injected outages: at 0.2 s spacing `trunc=0`; at 5 s `trunc=6, 0.2155%`; at 25 s `trunc=21, 1.3504%` → footer `EXIT BAR *** FAIL ***`. Any stream slower than ~2.3 s mean spacing fails the exit bar permanently. *(T0092's own streams measured 0.12–0.14 s, so they are far clear of this — the defect is latent, waiting for a genuinely thin stream.)*
- **`archive verify-replay` runs unwindowed, daily, with a CRITICAL alert.** `infra/ansible/roles/ops/templates/verify-replay.sh.j2:32` passes no `--since` and no `--pair`, so it replays the entire canonical archive every day and `cli/archive/command.py:704` exits 1 on a single failed hour → `ops_verify_replay_exit_code` → `alerts.yaml:943-982`, severity **critical**. One bad hour therefore pages every day, forever. The anchoring rule (`cli/archive/replay.py:139-156`) is quote-aware and correct, but any missing hour breaks a pair's chain until the next snapshot — which arrives only on a reconnect or checksum resubscribe.
- **A trap to avoid in the obvious fix:** the panel sweep catches `PanelError` at `materialize.py:308` and routes it to `hours_unanchored`, which exits **0**. Any new cross-contamination guard must raise something else, or it becomes a check that reports success.

## Done so far

**Both ripe-now halves landed 2026-07-28** on `fix/t0097-continuity-report-legs` — the two that were safe *before* the statistic is re-pinned, since neither changes what counts as a gap:

- **The derived threshold is printed.** `continuity.py`'s table gained a `thresh_s` column, so a `0.0000%` now sits beside the number that produced it. The point is immediately visible on two streams of the same hour: 5 s spacing derives a 50 s threshold, 30 s spacing derives 300 s — a 6× difference from the data alone, which is exactly the thing an operator could not previously see in order to disbelieve a zero. The TOTAL row deliberately prints no threshold: it is per pair, and averaging thresholds would invent a number.
- **The empty-window `ZeroDivisionError` is guarded.** `--since` filters per stream long after the empty-tree guard, so a window excluding every hour reached the TOTAL row with nothing to divide by. It now prints `no segments in the requested window` and returns non-zero — and prints **no** `EXIT BAR` line, because nothing was measured and nothing may bank a verdict.

## Resolution

**Resolved 2026-07-30** (spec `00076`, plan `docs/plans/00076-continuity-instruments.md`; commits `fa5f0fa3` spec, `4d428085` plan, `185475d0` cold-review fold-in + [[T0112]] registration, `f9b2b6ee`, `e174febc`, `b47018e0`, `d5a8e122`, `3b5db799` spec correction, `fecd8c96`, `d1aeb13a`, `148ef443`, `bb49e35a`). All three legs closed:

- **The threshold is fitted, not guessed.** A week-of-data fit (340M rows) refuted the topic's own leading candidate — `10 × median` collapses to the 5 s floor, because book updates burst same-millisecond and it books 2,061.7 s of phantom gap on a clean ETH/BTC week. The incumbent `p99.99 × 10` is the fitted winner; `MIN_POOL = 5002` is pinned by a test that measures polars' nearest-interpolation behaviour rather than trusting a comment.
- **The false-GREEN thin-stream blind spot is closed by refusal, not by better measurement.** Any stream sparse enough to self-calibrate into blindness is now exactly a stream `MIN_POOL` declines to score (`UNMEASURED`). Proven against the real pre-fix module on the same fixture: OLD `thresh_s=2040.0, gap_s=4.0, 0.0556% PASS` vs NEW `n=2332, UNMEASURED, FAIL`.
- **The false-RED head/tail test is now boundary-spanning** — hour spacing measures across the hour boundary rather than treating each hour file independently, and a stream's genesis hour is annotated rather than booked — dissolving the false truncation this topic's own findings named, while the real T0036 restart-clobber signature still books.
- **`archive verify-replay` was windowed — and the windowing was REVERTED the same evening.** `ops_verify_replay_window_days` (7 days) reached the runner and was proven in test (a synthetic bad hour trips `checksum_present`, exits 1 unwindowed and 0 windowed), but on real data 1,870 of 2,218 hours reported `anchored=False`: a window cuts the chain-anchoring predecessor set, a fact `verify_replay`'s own docstring already stated. The variable no longer exists. The paging problem it was meant to solve was the alert's *meaning*, not the sweep's scope, and is fixed by spec `00077` (page on NEW breakage, not on exit code); the sweep's runtime cost is [[T0114]].

**Acceptance run** (full 12-stream mirror, before/after merge-base `eef44196`): ETH/BTC 0.1320% → **0.0411%** (genesis 535.7 s head no longer booked, now under the 0.1% bar); SOL/BTC 0.1332% → **0.0410%**; truncations fleet-wide **72 → 60** (only the genesis false-RED removed — every EUR stream 7→6, both BTC-quoted 1→0). BTC/EUR's six surviving booked crossings (3276.0 / 1988.1 / 1890.3 / 270.7 / 126.7 / 83.4 s) are the real restart-clobber events — the 2026-07-08 deploy-day sequence (3276.0 / 1988.1 / 1890.3 s) and the July-13 crash's 270.7 s signature. Real outages are preserved exactly: ETH/BTC's 256.2 s booked intra silence (containing the 210.7 s event) is identical to the pre-implementation fit; BTC/EUR still books its 1550.8 s event inside 1805.9 s of intra silence. Fleet total 0.6131% → **0.4644%**, verdict stays `*** FAIL ***` honestly — the EUR streams carry ~0.49% of REAL gap. The change removed **30,370.1 s of fiction** (12 genesis heads + the retired fixed 1s tail allowance), not real loss.

**One residual split out before archiving, so no live deferred sub-item remains: [[T0112]]** (registered at the cold review) — `MIN_POOL` protects against exactly ONE outage-scale interval (`n ≥ 10000k − 5000` for k of them); no production stream is within three orders of magnitude of the k=2 regime (BTC/EUR 20,491 intervals of margin, LINK/EUR 10,508, ETH/BTC 2,197, SOL/BTC 898).

The genesis-carve-out sentence this topic's own findings put into `.claude/rules/capture-deploys.md` is retired on this same branch (protected-file edit, owner sign-off) now that the instrument annotates the genesis hour itself instead of needing an operator-read exception.
