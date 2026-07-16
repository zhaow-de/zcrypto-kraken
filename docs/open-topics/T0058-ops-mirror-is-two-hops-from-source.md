---
status: open
ripe_when: `Reconciler · capture mirror lagging` fires, or a third consumer is added downstream of the ops mirror
---

# The ops mirror is two hops from source, so the reconciler's view is an hour staler

## Context — what

Spec `00054` moved the overlay writer to the ops node. Custody and Role A stayed on the NAS (D3), so the raw mirrors still flow **VPS → NAS → ops**, each hop on its own hourly timer. The reconciler therefore now reasons from a mirror that is, by construction, **one full hourly hop staler** than when it ran on the NAS.

## Why this matters

Measured across the 2026-07-16 cutover:

| | before (reconciler on the NAS) | after (on ops) |
|---|---|---|
| `zcrypto_reconcile_source_lag_seconds` | 4072 s (1.13 h) | 6465 s (1.80 h) |

**Spec `00054`'s D10 predicted this would FALL, and it rose.** That criterion was written on a misunderstanding: it conflated the NAS's *loop-period* problem (the ~103-min cycle, which the move genuinely addresses) with *mirror lag* (which the move necessarily worsens, because it puts the consumer further downstream). The spec's own risk note anticipated exactly this class of error — that the after-picture's attribution was unmeasured.

The consequence is not incorrectness — a staler mirror delays healing, it does not produce wrong verdicts (the pull-failure gate still makes absence uninformative and skips) — but it **eats alert margin**: `Reconciler · capture mirror lagging` fires at `> 10800 s` (3 h) `for: 10m`. Steady-state headroom shrank from ~1.9 h to ~1.2 h. One missed hourly cycle on *either* hop now costs proportionally more, and the threshold was sized when the mirror was one hop from source.

## Findings so far

- Not firing: 1.80 h against a 3 h threshold, on both `source="primary"` and `source="secondary"`.
- The lag is structural, not a fault: ops pulls from the NAS at `:12`; the NAS pulls from the VPSes on its own loop (which was itself running ~103 min, i.e. *worse* than hourly — so the real figure moves as the NAS's loop period settles post-cutover).
- Nothing else consumes the ops mirror on a latency budget today; the panel and both replays are all downstream of the same copy and were already living with it.

## Suggested next steps

- **Re-measure once the NAS's post-cutover loop period settles** (it should fall toward its 60-min floor now that reconcile + backfill are gone). The lag figure above was taken minutes after the cutover, while the NAS's loop was still the old shape — the steady-state number may be materially better.
- Then decide whether 3 h is still the right threshold, or whether it should be re-derived from the *actual* two-hop steady state plus a stated number of tolerable missed cycles. Do not simply raise it to silence a page: the rule exists to catch a host that stopped producing.
- If the margin proves too thin, the options are (a) give ops its own direct pull from the capture VPSes (costs a second rrsync channel per host and puts a third puller on the capture hosts), or (b) tighten the ops pull cadence. Prefer measuring before building either.
- **Correct D10's criterion** wherever it is restated, so the next reader does not chase a "regression" that is the design working as intended.
