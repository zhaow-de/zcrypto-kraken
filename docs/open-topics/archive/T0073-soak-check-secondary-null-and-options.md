---
status: resolved
---

# soak-check: wire the secondary block-bootstrap null + `--null`/`--path` options + regime context

## Context — what

`zcrypto engine soak-check` (spec `00058`) v1 builds its reference distribution from a single **primary windowed null** (`windowed_null`: all overlapping L-bar windows of the metric series). The spec's D3 also specified a **secondary null** — a stationary (Politis-Romano) block bootstrap — reported alongside the primary, with a "prefer the more conservative on disagreement" rule and an "indeterminate (instrument-fragile)" flag when the two nulls disagree. The block-bootstrap primitive (`block_bootstrap_null`) is **built and unit-tested** in `cli/engine/soak.py` but **not wired** into `analyze_soak`/`soak_report`.

Also descoped from v1 vs spec `00058`: the `--null [windows|block-bootstrap|both]` and `--path [fast|verified]` CLI options, and the report's "regime context" section (item 9 of the report shape).

## Why this matters

The primary windowed null's overlapping windows share observations, so it understates the true sampling variance; the block bootstrap resamples independent paths and is a genuine robustness cross-check. Without it, a borderline verdict has no second opinion. This strengthens mainly the **non-gating P&L line** and borderline structural verdicts — it does **not** affect the honesty contract or the primary gating verdicts (all correctly fed by the primary windowed null), which is why it was a safe v1 descope.

## Findings so far

- `block_bootstrap_null(series, window, *, n, mean_block, seed, reducer)` exists, is deterministic (seeded `numpy.random.default_rng`), has real stationary-block structure, and is unit-tested (`test_block_bootstrap_deterministic_and_centered`). Its docstring flags it as the intentionally-unwired secondary-null primitive.
- Only `windowed_null` currently drives every gating verdict and the P&L verdict in `analyze_soak`.
- The v1 descope decision + rationale are recorded in the phase-6 ledger and the PR #154 description.

## Done so far

Landed in **iter-111** (spec `00061`, PR into `develop`; see `docs/iterations-history-phase6.md`):

- `block_bootstrap_null` is wired into `analyze_soak`. Every metric is judged under **both** nulls and reconciled by the explicit D1 severity rule (identical / adjacent-takes-the-milder / opposite-extremes-`indeterminate (instrument-fragile)` / exactly-one-`n/a`), with each disagreement disclosed verbatim.
- `--null [windows|block-bootstrap|both]` (default `both`) and `--path [fast|verified]` landed and are threaded through `soak_report`. `--null windows` reproduces the pre-change verdicts, numerics, panel line and disclosures exactly — verified side-by-side against `develop` on the real journal — so the second construction is strictly additive.
- Tests: the five reconciliation branches, both-nulls-agree on planted-consistent/inconsistent, determinism, the vacuous-band interaction, and the column→construction attribution pinned **positionally** (mutation-tested: swapping the two labels, or attributing a verdict to a construction that never ran, must fail).
- **First real finding:** on the ops journal mirror `gross` and `net` read windowed `consistent` / bootstrap `weakly-consistent`. The windowed band is 2.25× wider on `gross` (width 0.2899 vs 0.1288), and the same live value sits at the 35.6th percentile under one construction and the 6.5th under the other — the overlapping-window variance understatement, measured rather than assumed.

## Resolution

**Ruled 2026-08-03 (owner): report-shape item 9 is DROPPED, and it was dropped on a measurement rather than a judgement.** The remainder was never code — it was the definition spec `00058` left open: *which* regime variable is worth conditioning a soak verdict on, and *what would a reader do differently* on seeing it. The answer is none, and the experiment that settles it is the one any regime split performs anyway: halve the window.

On the 23.17-day realized window (L = 140), split into contiguous halves of L = 71 and L = 68 — both the **same regime** by every system-internal measure (governor multiplier 0.5 with zero variance, cap-breach 0, one active sleeve throughout):

| metric | full (L=140) | first half (L=71) | second half (L=68) |
| --- | --- | --- | --- |
| `governor_engagement` | **inconsistent** | **n/a — no discriminating power** | **n/a — no discriminating power** |
| `gross` / `net` | indeterminate | **consistent** | **indeterminate** |
| realized cumulative net | −0.4559 % | **+0.0302 %** | **−0.5514 %** |

*(71 + 68 = 139, not 140: each run independently drops its own newest cycle, which can never score for want of a successor, so the boundary cycle scores only in the full run. For the same reason the halves' P&L does not compose to the full window's — these are three separate runs, not a partition of one.)*

- **Conditioning destroys the only discrimination the instrument makes.** `governor_engagement` is the single metric outside its band at full window; at half window its null band spans the full [0, 1] on *both* halves. Every split does this, whichever variable is chosen.
- **Two windows in the same regime already disagree** — different verdicts on `gross`/`net`, opposite-signed P&L. So a regime section cannot separate a regime effect from sampling variation, and would invite a reader to see structure in noise. That is exactly the failure this topic's own test names: unactionable context reads as evidence.

**The honest residue already ships**, so nothing is lost: `soak-check` states regime state without conditioning any verdict on it — *"realized multiplier was 0.5 on all 140 scored cycles (no variance)"*, the same for cap-breach, and sleeve occupancy now has its own gauge and alert ([[T0124]]). Deferring a third time was rejected: a discriminating split needs roughly the full-window bar count *per cell*, and the regimes are not alternating — the governor has been ×0.5 for the whole soak and both dormant sleeves have been flat ~9 months, so the trigger would not fire on any horizon that matters. This topic had already been re-pointed **twice** for triggers that could not fire.

The drop is recorded in `docs/specs/00058-soak-check-oos-report-design.md` with the measurement, so the spec no longer reads as owing a section.

## Suggested next steps

_(none — resolved. The secondary null, `--null`/`--path` and the severity reconciliation landed in iter-111; report-shape item 9 is dropped with its measurement recorded in spec `00058`.)_
