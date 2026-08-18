---
status: open
ripe_when: order submission stops being an attended-window act — check `grep -n exec_armed infra/ansible/roles/engine/templates/zcrypto.toml.j2` and read the committed default; while it renders `false` the engine is armed only inside a window a human is watching and a restart mid-window is an abort, not a routine event. Ripe the moment that default becomes `true` (continuous arming), or earlier if an exec ledger record is ever observed carrying a non-terminal reduce-only `submitted` row across a container restart — the ledger read in `infra/runbooks/README.md#engine-probe-window` prints the row states, and `docker inspect --format '{{.State.StartedAt}}' zcrypto-engine` gives the restart to compare against
---

# Adopted resting orders: their fills are unobservable after a restart

## Context — what

`ProbeExecutor._adopt_resting_orders` (the startup pass, spec 00090 D10) keeps a venue-resting order alive when the exec ledger carries it as a non-terminal reduce-only row: the order is left resting, the row is preserved, and the row is re-attached to `self._attached` so a fill would have somewhere to land.

That last part does not hold across a restart, and the pass cannot make it hold. In the installed nautilus-trader (1.230.0), `LiveExecutionEngine._generate_order` assigns a reconciled venue order `StrategyId("EXTERNAL")` unless the instrument appears in some strategy's `external_order_claims`; `ExecutionEngine._send_to_strategy` then publishes its events on `events.order.<strategy_id>`, and a `Strategy` subscribes only to its own id's topic. So after a restart, a fill on a preserved resting order reaches no handler in this process: no row append, no `zcrypto_exec_fills_total`, no `zcrypto_exec_fees_eur_total`, no position or realized-PnL move. The order is still real and still fills — it is simply reconciled as venue truth and nowhere else.

The obvious fix is to claim the instrument (set `external_order_claims` on the strategy). That is the thing this topic exists to decide, because it is not free.

## Why this matters

Claiming the twelve basket instruments would route **every** externally-originated order on them into this executor — including the operator's own hand-placed acts. The probe procedure has exactly one such act by design: the manual settle of the BTC/EUR margin long in the Kraken web UI, which the engine's adapter cannot perform. Today that settle reaches the executor's event path not at all, which is precisely what keeps the unknown-order kill trip scoped to genuine surprises. Claim the instrument and the sanctioned settle becomes an unknown order arriving at the fill handler, where the trip latches the kill file, cancels resting orders, refuses every further intent, and pages — during a window whose whole purpose is to complete that settle.

So the two properties are in tension and cannot both be had by claiming alone:

- **Observability**: an adopted order's post-restart fills append to their forensic row and move the execution counters.
- **Scope**: the unknown-order trip fires only on orders nobody sanctioned, so a hand settle cannot latch the kill switch mid-window.

Deferring is cheap *while the probe is attended*: a restart inside a window is already an abort, the operator is present, and venue truth is one Kraken page away. It stops being cheap when arming becomes continuous, because then a restart is a routine event and a silently-unaccounted fill is a permanent hole in the forensic record — the record the reconciliation trip itself is measured against.

## Findings so far

- Measured against the installed library, not assumed: `nautilus_trader/live/execution_engine.py` (the `StrategyId("EXTERNAL")` assignment and its `get_external_order_claim` bypass), `nautilus_trader/execution/engine.pyx` (`topic = f"events.order.{strategy_id}"`), `nautilus_trader/model/identifiers.pyx` (`EXTERNAL_STRATEGY_ID`).
- The docstring of `_adopt_resting_orders` previously claimed the opposite — that a preserved order's later fills append to its row. Corrected in place on the 00090 branch, together with a paragraph in the runbook's arm step telling the operator to read such an order from venue truth instead.
- Behaviour was deliberately left unchanged at 00090 merge time: the routing change is not a merge-gate fix, and making it under the deadline would have traded a scoped kill trip for observability nobody needed inside an attended window.

## Suggested next steps

- **Decide the routing, and record the decision in `docs/research/14.phase6-decisions.md`.** Three candidates, all cheap to state and none yet costed: (a) claim the instruments and re-scope the unknown-order trip so a sanctioned act is exempt — needs a durable definition of "sanctioned" that a restart survives, since an in-memory allowlist is exactly what the restart destroyed; (b) claim nothing and instead reconcile adopted orders from venue truth at startup, writing the missing rows from the venue's own trade history rather than from events; (c) cancel every adopted order unconditionally at startup, giving up the preserved-reducer case entirely in exchange for one rule with no exceptions.
- **Before deciding (a), measure whether the trip can even see a hand settle.** The runbook already records this as unproven on the installed adapter: place a settle in the Kraken web UI during a window with no intent in flight, then read the next `venue-<HH>.json` positions and the engine log for the unknown-order path. A trip that cannot observe the settle today changes the cost of (a) materially, and this measurement is a by-product of the probe window already planned — take it there rather than constructing it separately.
- **Whichever way it goes, the runbook paragraph in the arm step and the `_adopt_resting_orders` docstring are the two surfaces that must move with it** — they currently state the unobservability as the standing fact.
