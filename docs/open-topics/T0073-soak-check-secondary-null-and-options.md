---
status: open
ripe_when: the soak-check gate produces populated verdicts (L >= floor) and a robustness cross-check on the primary windowed null is wanted
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

## Suggested next steps

- **(Autonomous)** Wire `block_bootstrap_null` into `analyze_soak`: compute each metric's verdict under both nulls; when the two disagree on the verdict label, flag that metric "indeterminate (instrument-fragile)"; otherwise prefer the more conservative (less likely to call "inconsistent"). Apply at least to the non-gating P&L line, and to the gating metrics if the dual verdict is wanted there.
- **(Autonomous)** Add the `--null [windows|block-bootstrap|both]` (default `both`) and `--path [fast|verified]` CLI options and thread them through `soak_report`.
- **(Autonomous)** Add the "regime context" report section (report-shape item 9).
- **(Autonomous)** Tests: the two nulls agree on planted-consistent/inconsistent, and the disagreement flag fires on a constructed borderline case.
