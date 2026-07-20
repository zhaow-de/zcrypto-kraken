---
status: partial
ripe_when: a concrete definition exists for what the report's "regime context" section should contain -- i.e. which regime variable (realized vol, trend state, funding, or a dated market-structure event) is worth conditioning a soak verdict on, and what a reader would DO differently on seeing it
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

## Suggested next steps

- **(Autonomous, but blocked on a definition — this is the whole remainder)** Add the report's "regime context" section (spec `00058` report-shape item 9). It is deferred rather than dropped because `00058` **named** the section without specifying its content, and inventing a definition inside an implementation iteration would bake an arbitrary choice into a go/no-go instrument. Before building it, answer: *which* regime variable is worth conditioning a soak verdict on (realized vol, trend state, funding regime, or a dated market-structure event), and *what would a reader do differently* on seeing it? A section that adds context nobody acts on is width, not honesty — and on this instrument, unactionable context reads as evidence. If the answer is "nothing", the honest outcome is to drop report-shape item 9 from `00058` explicitly rather than implement it.
