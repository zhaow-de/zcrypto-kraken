---
status: resolved
---

# The margin floor reads a free-margin figure refreshed only at connect

## Context — what

The engine refuses a plan whose margin floor exceeds `free_zeur` (`cli/engine/probeplan.py:223`), read from the venue state's `balances` (`cli/engine/command.py:2192`, `cli/engine/executor.py:2772`). That `EUR` row is Kraken's TradeBalance account summary in EUR from the MARGIN account (`cli/engine/node.py:561-562`, filled at `cli/engine/venuestate.py:126`): free margin, with the coins counted as collateral. Under rung 3 it stood still across the fills and stepped only at drill G's restart, so it is refreshed only when the engine connects. The figures are in `docs/reference/rung3/days.md`'s entry for 2026-11-12, which reaches `develop` with the week's records.

## Why this matters

1. **The figure goes stale between connects.** The floor is checked against free margin as it stood at the last connect, so a plan can pass on margin Kraken no longer has, or be refused on margin it does have.
2. **The spec's wording is not the decided basis.** The owner's decision of 2026-09-23 (`docs/research/14.phase6-decisions.md:841`) names free margin the right measure for `free_zeur`, as the code has it, while spec 00090 still writes the floor as `sum(notional_i / leverage_i) × 2.5 ≤ free ZEUR balance` (`docs/specs/00090-rung-1-order-path-design.md:68`); no test pins the basis.

Rung 3's loop is spot-only, so neither gap has bitten yet. Both matter the first time a plan carries a margin intent.

## Findings so far

- Measured on the pinned wheel against the loopback, the engine's own node started twice (spec `00162`'s measured basis): the venue record's `EUR` is TradeBalance's `mf`, read once a process at the connect; with the loopback's `mf` moved at a fill, the record's figure stayed where the connect put it, and the next start read the moved one. The execution client's account summary is built from the same answer, `e` its total and `m` its locked part.

## Resolution

- Fixed by `dca8fc5bd`: the pickup of a plan carrying a margin open, a leveraged `open`, reads Kraken's free margin, TradeBalance's `mf` for `ZEUR`, on the engine's bare client (`read_free_margin`, `cli/engine/executor.py`), and measures the margin floor, summed over its margin opens, against it (`margin_floor_refusals`, `cli/engine/probeplan.py`), never the Cache's account summary from the execution client's connect; a read that fails refuses the plan's margin opens alone, none of its closes or spot intents, and a plan with none — spot, or margin closes alone — reads nothing and has no floor, the owner's basis of 2026-09-23 taken to the intents that extend margin. `probe-plan --check` measures the floor against the venue record's figure, advisory as before.
- Held by `tests/test_engine_executor.py::test_a_fill_between_connects_moves_the_free_margin_the_next_plans_floor_is_measured_against` (Kraken's figure moved between two pickups in one process and the Cache's not, the second plan judged on the moved one), `::test_the_margin_floor_reads_krakens_free_margin_at_the_pickup_and_never_the_caches_account` (the basis, both directions), `::test_a_free_margin_read_that_fails_refuses_the_margin_opens_naming_the_read_and_runs_a_close_or_a_spot_open`, `::test_a_margin_open_the_gate_refuses_keeps_the_gates_reason_over_a_failed_free_margin_read`, `::test_a_failed_free_margin_read_still_takes_the_mixed_inventory_check_under_the_cache` and `::test_a_spot_only_plan_reads_no_free_margin`, proven by `infra/scripts/mutate-probe.sh`'s thirty arms in `374bdc32b`.
- The wording: spec `00090`'s margin floor reads free margin, amended in `7647f2648`; `infra/runbooks/engine-procedures.md`'s probe-window funding step names Kraken's free margin and the figure `probe-plan --check` reads, in `ab91cc943`.
- The change ships on the engine image with T0229's, T0226's and T0227's fixes, one engine converge, the fleet's concern (`.claude/rules/fleet-deploys.md`).
