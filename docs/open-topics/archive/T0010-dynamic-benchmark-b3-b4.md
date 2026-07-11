---
status: resolved
---

# Full-history dynamic benchmark B3/B4 (gate × basket, basket + short)

## Resolution

Resolved in **iter-055** (the deferral-audit catch-up run). Both sub-items delivered, `docs/research/04.phase3-benchmark-b2-dynamic-report.md` §"B3 and B4": the self-gated dynamic B3/B4 built with full instrument QA (reproduces the committed fixed-window B3/B4 and iter-044 basket numbers exactly), zero-fee **and** net-of-cost via the per-asset-turnover + margin-carry model — which also **reconciles the Phase-3 carried-forward** basket-cost/§9.6 item. Headline: **B3+vt point-beats gated-B1 net-of-cost (1.245/1.278 vs 1.047/1.074)** — Sharpe edge n.s. (p ≈ 0.27), ~1.8× the drawdown — so the deployable-bar choice (and the frozen-benchmark swap) is escalated as **T0009's first item**. B4 confirms a fourth time that the short's margin carry kills (37.6 %/yr).

## Context — what

iter-044 noted "a full-history dynamic B3 (gate × basket) / B4 (basket + short) once the basket base is in the A1 loop" — a deferral whose trigger fired at iter-045/046 and was then lost in prose (the motivating example for the deferral-registration rule). The fixed-window B3/B4 exist in `docs/research/04.phase3-benchmark-b2-basket-report.md`; the dynamic 2→10 basket base is `dynamic_inverse_vol_basket` (iter-044).

## Why this matters

Completes the benchmark family over the full 2013→2026 horizon so gate and short overlays are characterized on the same base the alpha families use. Benchmarks are **not** registry trials — no budget spend; fully autonomous.

## Findings so far

Fixed-window B3 (200-day self-referential equity gate, long/flat) rescued the raw basket from a loss but stayed below vol-targeting; B4 (short) was disastrous (Sharpe −0.136). Full-history behavior is unknown; the fixed-window story was shown to be window-sensitive (iter-044's finding-1 reversal).

## Suggested next steps

- Build dynamic B3/B4 mirroring the fixed-window method (gate on the basket's own cumulative-equity 200-day average; B4 short below) over the union calendar, zero-fee + net-of-cost, vs gated-B1.
- While at it, reconcile the Phase-3 carried-forward "basket-turnover cost model + §9.6 stress ladder": largely superseded by the per-asset-turnover cost model of iters 046–048 — apply that model to the benchmark basket or record an explicit drop.
