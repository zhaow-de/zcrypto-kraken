---
status: open
ripe_when: NOW for the two printout/guard halves (autonomous, no behaviour change); the threshold re-pin needs ≥1 week of the T0092 BTC-quoted streams so the statistic is fitted to real thin-stream spacing rather than guessed; `verify-replay` windowing is ripe the first time `ops_verify_replay_exit_code` pages
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

## Suggested next steps

- **(Ripe NOW, doc-only — recorded 2026-07-23)** `continuity.py:106-108` has **no carve-out for a stream's genesis hour**: a newly added pair's first hour begins mid-hour by construction, so `head` is hundreds-to-thousands of seconds ⇒ one truncated hour and up to ~3600 s of booked gap, printed under a footer that says "MUST be 0". This is a *certain* false-RED on deploy day for every new stream, distinct from the thin-stream blinding below (T0092's streams are far clear of that at 0.12–0.14 s spacing, but every stream has a genesis hour). Noted in `capture-deploys.md`'s verify-by-outcome bullet; the durable fix is the boundary-spanning measurement in the next item, which dissolves it.
- **(Autonomous, ripe NOW — no behaviour change)** Print the derived per-pair `thresh` in `continuity.py`'s table, so a `0.0000%` sits next to the threshold that produced it and an operator can disbelieve the zero. This is the half of the fix that is safe before the statistic is re-pinned.
- **(Autonomous, ripe NOW)** Guard `continuity.py:135`'s `ZeroDivisionError`: `--since` filters per-stream at `:87` and never re-triggers the empty-tree guard at `:77`, so a window with no data divides by zero. Reproduced. Return non-zero with a clear message instead.
- **(Needs ≥1 week of T0092's streams)** Re-pin the silence statistic from measured thin-stream spacing — `10 × median` is the current best candidate, but fit it, do not guess it. Then fix the head/tail test by measuring spacing **across** the hour boundary (last row of H−1 → first row of H is just another interval) rather than treating each hour file independently, so boundary truncation falls out as ordinary intra-stream silence while the real T0036 restart-clobber signature is still caught.
- **(Ripe when it first pages)** Window the daily `verify-replay` (a `--since` of a few days) so one historical bad hour cannot page forever, and decide whether a chain break on a quiet stream should be an error or an honest gap.
- **(Whenever `capture-deploys.md` is next edited)** Its outcome check currently names `continuity.py` unconditionally; note the thin-stream caveat until the re-pin lands.
