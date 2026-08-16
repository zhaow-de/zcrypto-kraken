---
status: open
ripe_when: a production (non-test) consumer of `InstrumentConstraints.costmin` exists — grep `cli/` for a read of `.costmin`
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

## Suggested next steps

- When `00090` builds the order path, put the guard at the comparison itself: wherever a notional is compared against `constraints.costmin`, assert `constraints.costmin_quote` equals the denomination of that notional, and fail loudly on mismatch rather than proceeding. The assertion belongs beside the comparison, not in the dataclass.
- Prove the guard by constructing the defect, per `agent-ops.md` — a guard is unproven until the defect it names is seen to trip it. Build the mismatched pair (a `/BTC` leg's `costmin` of `2e-05` against a EUR-denominated notional) and confirm it raises; confirm the matched pair passes. Read *which* failure fired, since a red exit can be the guard misfiring on a healthy path.
- Use `fx_eur_notional(symbol, qty, price, btc_eur_close)` (`cli/engine/instruments.py`, landed by `00094` D5 pure and uncalled precisely so `00090` inherits a proven conversion) rather than writing a second conversion beside real money.
