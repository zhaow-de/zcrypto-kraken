---
status: resolved
---

# The engine publishes the gate's bare level before the boundary folds its holds

## Context — what

At a boundary the engine's metrics sink (`cli/engine/command.py`, `_make_exec_sink`) publishes the gate's own level before `on_boundary` (`cli/engine/executor.py`) republishes it with the three folded holds. A scrape landing between the two reads `zcrypto_exec_gate_level` at 2 under a folded hold, and an `on_boundary` that raises leaves that bare 2 standing for up to 60 s.

## Why this matters

`zcrypto-engine-exec-disarmed-boundary`, the rule #834 lands, reads that level over a span, so a bare 2 under a hold makes it wait one more span before it pages. Spec 00092's D6 has the gate level, D11's rule and the board read one figure, and for that scrape they read two.

## Findings so far

- Found by #834's pre-review and named in its body as an ask; registered on the owner's word of 2026-11-08, "Register T0227 (Recommended)", ripe beside [[T0226]], whose engine fix rolls on an image after the same week.

## Resolution

- Fixed by `92558c1c6` on `fix/t0227-gate-level-folded-once-per-boundary`: `_ExecGauges.update` takes `level`, and the boundary sink (`_make_exec_sink`, `cli/engine/command.py`) passes `level=False`, so it keeps the exec record, the heartbeat and the presence readings and leaves `zcrypto_exec_gate_level` to the executor's evaluations, whose verdict carries the executor's holds (`_fold_holds`). `run()` always wires the executor (`ShadowStrategy`'s `executor_factory`, `cli/engine/node.py`), built at the strategy's start, so every boundary the alert chain fires ends in `on_boundary`'s folded publish; a raise before it leaves the level the last publish set, the idle refresh's folded one at most 60 s before. The catch-up cycle a restart runs inside the passable window precedes the executor and reads `run()`'s startup level, bare, which the restart hold keeps at reduce-only or below.
- Held by `tests/test_engine_executor.py::test_the_boundary_sink_leaves_the_gate_level_to_the_executors_folded_verdict` (the gate's own level full, the folded 0 standing between the sink and `on_boundary`), proven by `infra/scripts/mutate-probe.sh` in `aa5df2b9e`, both arms KILLED, and `::test_on_boundary_publishes_a_hold_that_appeared_between_plans_over_the_full_level_the_gauge_held` (the gauge at 2, a freeze, `on_boundary` publishing 0), proven in `e7405629e`, its arm KILLED.
- `infra/runbooks/engine.md`'s exec-not-evaluated section re-trued in `0bf6df4f6` and `d8b21d479`, the docstrings in `1affb0fcb`.
- The change ships on the engine image with T0229's and T0226's fixes, one engine converge, the fleet's concern (`.claude/rules/fleet-deploys.md`).
