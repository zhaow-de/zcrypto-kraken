---
status: resolved
---

# Costmin denomination guard at the sizing call site

## Context — what

Spec `00094` D4 made every instrument's minimum-cost floor carry its own denomination: `InstrumentConstraints.costmin_quote`, populated from `COSTMIN[symbol][1]`, so the ten EUR legs read `"EUR"` and the two `/BTC` legs read `"BTC"`. That makes the denomination **knowable**. Nothing yet makes it **checked**: `size_order` takes `costmin` as a bare number, and D4 assigns denomination-ownership to the caller — a caller that does not exist until `00090` builds the real order path. This topic holds the guard that must land at that call site.

## Why this matters

A BTC-denominated floor is `0.00002`; a EUR-denominated one is `0.45` — four orders of magnitude apart, in a comparison against a notional. Compared the wrong way round, the floor either passes everything (a BTC floor against a EUR notional: every order clears a `0.00002` bar) or blocks everything. The first form is the dangerous one, because it is silent and it fails **open** on the live trade path: undersized orders reach the venue and are rejected there, or worse, sized nonsense is submitted. The failure is unreachable today — no production reader of `costmin_quote` exists and `runtime_concordance` is deliberately blind to it (D5a) — so it will bite exactly once, at the moment `00090` first sizes a `/BTC` order.

## Findings so far

- **The field is guarded only on the production population path.** `venue_state_from_cache` derives `costmin_quote=COSTMIN[symbol][1]` (`cli/engine/venuestate.py`), and hardcoding `"EUR"` there fails two tests. A **hand-built** `InstrumentConstraints` may lie freely: a twelve-leg `VenueState` with a blanket `costmin_quote="EUR"` yields `runtime_concordance(...).ok is True`, and the lie is journaled into the venue record verbatim. Measured during `00094` Task 3's review, twice, by two independent reviewers.
- **`runtime_concordance` will never be the right home for it.** It iterates only the three Cache-supplied constraints (`ordermin`, `lot_step`, `tick_size`); costmin's correctness is `tests/test_costmin_drift.py`'s job by design, because a broken costmin failing concordance would hold `00089` D6's alert red forever (the T0135 lesson).
- **A `__post_init__` validator is the wrong shape**, not merely a costly one: it would couple a plain evidence dataclass to a committed constant and reject the deliberately-wrong hand-built states the concordance tests depend on (`_valid_state(**{"BTC/EUR": broken})`). It also guards the wrong proposition — the defect is not "`costmin_quote` disagrees with `COSTMIN`", it is "a consumer compared a BTC floor against a EUR notional."
- **The seam is already documented** at `cli/engine/instruments.py`'s `size_order`: it takes `costmin` as a plain number and never a `(value, quote)` pair — the caller owns denomination. Documentation, not enforcement.
- `tests/test_engine_venuestate.py`'s `_XBT_LEG_ATTRS` distinctness is now load-bearing rather than decorative — `test_the_xbt_legs_freeze_their_own_cache_constraints` reads all three Cache-supplied values back for both `/BTC` legs, so a reader that reused the EUR fixture values or defaulted them fails. Landed with `00094`; do not redo it.
- `cli/engine/feeders.py::load_minimums` filters `quote == "EUR"` **by design** and must keep doing so; the two BTC-quoted floors are read from the snapshot's `universe` block in the drift test, never through that reader.

## Resolution

**Resolved 2026-08-18 (iter-140, spec/plan `00090` D8) — the guard landed at the comparison, exactly where this topic said it belonged, and the defect it names was constructed and seen to trip it.**

`cli/engine/executor.py::size_probe_order` is the order path's single sizing call site: every probe intent is sized there, on the Cache-fresh constraints and the committed `COSTMIN`, through the one proven `size_order`. Its first act — before any comparison reaches `size_order` — is `if constraints.costmin_quote != "EUR": raise EngineError(...)`, naming the symbol, the offending denomination, and the remedy (`convert through fx_eur_notional before sizing a non-EUR-quoted leg`). The `__post_init__` shape this topic ruled out was not revisited: the guard is a call-site refusal, so the concordance tests' deliberately-wrong hand-built states are untouched and `InstrumentConstraints` stays a plain evidence dataclass.

The guard is proven, not merely present. `tests/test_engine_executor.py::test_the_mismatched_denomination_raises_and_names_the_defect` builds this topic's own construction — an `ETH/BTC` leg's `costmin=2e-05, costmin_quote="BTC"` against a EUR notional — and asserts on `match="cross-denomination"`, so it reads *which* failure fired rather than accepting any red. The matched EUR pair sizes through unchanged, and the **fail-open direction is pinned separately**: `test_a_below_costmin_result_names_the_floor` drives a matched EUR pair that clears `ordermin` and falls under the EUR costmin floor, asserting the reason names `costmin` — so a costmin drop to `0.0`, the silent pass-everything failure this topic exists to prevent, cannot survive the suite.

The refusal reaches the operator surface too: `zcrypto engine probe-plan --check` refuses the comparison outright when a leg's `costmin` is not EUR-denominated, rather than validating an intent the node would then raise on.

`fx_eur_notional` stays pure and uncalled — the rung-1 probe's notionals are all EUR and all its legs EUR-quoted, so the live path is the matched case; the guard is what forces a future `/BTC`-leg notional through that conversion instead of a second one written beside real money.

Commits: `da9a2c71` (the sizing seam and the guard), `0a1ed02d` (the fail-open-direction proof), `5c5485c3` (the CLI validator's matching refusal). **The code has landed and is green; nothing is deployed and no order has ever been submitted** — the guard's live exercise is the probe window, which the `engine-probe-window` runbook section gates.
