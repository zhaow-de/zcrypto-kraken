# 00108 — the `rest-hold` plan mode: an order that stays

Resolves the `rest-hold` build item of [[T0018]], registered in spec `00105` D4. One plan mode, two plan-carried fields, one gauge, one panel, one alert rule — on one branch and one PR, at the Fable review floor (live trade path). The code ships disarmed and reaches the engine only on an attended converge.

**What it is.** A third plan mode beside `execute` and `rest-cancel`, whose order is placed passively, is **not** cancelled when the venue acknowledges it, and rests for a duration the plan author declares. It exists because six order-path drills — E, E′, G, F2, A1, A2 — have no subject without it: `rest-cancel` cancels inside the `OrderAccepted` handler, so nothing is resting by the time any induction lands, and `infra/runbooks/drills-order-path.md` forbids substitution outright ("an order cancelled a second after it was placed exercises none of what these drills measure").

**The defect this spec exists to prevent.** The one-line version of this change — adding `"rest-hold"` to `_MODES` — parses cleanly and then runs the new mode with **full `execute` semantics**: joining the touch, repricing as it moves, and at the fifteen-minute time box crossing the spread with up to three marketable IOCs. On the live trade path. Nothing goes red, because no test pins `_MODES`' membership and every mode branch in the executor is written against the *name* `rest-cancel` rather than against a property. A mode whose entire purpose is *never fills, keeps resting* would, written the obvious way, become the most aggressive order path in the system.

## The measured basis

Read from the repo on 2026-08-31 at `develop` `e3d90508`:

| fact | where | consequence |
| --- | --- | --- |
| The mode vocabulary is enumerated in exactly one machine-readable place and validated by membership alone | `cli/engine/probeplan.py:23` `_MODES = frozenset({"execute", "rest-cancel"})`; validated at `:92-94` | a third mode is one token away from parsing — and from running as `execute` |
| **No test pins `_MODES`' membership** | absence, over `tests/` | the miswiring above ships green; D8 makes pinning it the first test |
| The executor consults `mode` at exactly **four** sites, every one written `== "rest-cancel"` or `!= "rest-cancel"` | `cli/engine/executor.py:1111`, `:1237`, `:1965`, `:2050` | a third mode inherits the `execute` arm at all four; D2 rewrites each to decide on a property |
| `falling_back` is set `mode != "rest-cancel"` at the time box | `executor.py:1111`, under the comment "A rest-cancel drill must never execute" | left as-is, a `rest-hold` order fires up to `_MAX_IOC_ATTEMPTS` marketable IOCs at expiry — **the live-money line in this change** |
| `_TIME_BOX = timedelta(minutes=15)`, armed once in `_start_intent` and never re-armed | `executor.py:67`, `:1177` `timebox_at=now + _TIME_BOX`, enforced at `:1108` | too short for E′ (a human phone leg) and A1 (a reboot plus its verify list); D3 replaces it per intent |
| `rest-cancel` cancels inside the `OrderAccepted` handler | `executor.py:1965-1969` — "rest, be acknowledged, come straight back off the book" | there is no window in which an induction can act; this is why no existing mode serves the drills |
| `_REST_CANCEL_OFFSET = 0.05` is a bare module constant, not per-intent | `executor.py:76` | one fixed distance cannot serve A1/F2's "far from the touch" and A2's fill-while-down together; D1 makes it per-intent |
| `PLAN_TTL = timedelta(minutes=60)` is checked against `created_at` when a plan is validated | `probeplan.py:19`, `:192` | it bounds when a plan may **start**, never how long an intent runs — so D3's cap is a fresh decision, not an inherited one |
| The kill file is a gate **input**; it reaches an order only while one is `_active`, through the 5-second tick, and gets exactly one cancel attempt with no retry | `cli/engine/execgate.py`; `executor.py:60` `_TICK_SECONDS = 5.0`, `:1101-1103` | the kill switch works on a resting order — and is drill E's subject — but only while the intent is live |
| `_QUOTE_SILENCE = 30 s`, `_ACK_WAIT = 30 s` | `executor.py:66`, `:73` | both are kept; F2 has no subject without the first |
| `plan_refusals` carries no mode-aware rule | `probeplan.py:158-211` | D1's refusals are the first, and the plan wall is where a malformed hold is stopped |
| The metrics idiom is a module-level handle wrapped in try/except that logs and continues | `executor.py:197-203` `_inc_order` | D6's gauge costs no new failure mode |
| `on_timer` already runs every tick and the adopt pass is guarded to run once | `executor.py:648-652` | the gauge needs no new loop and no venue read |
| Every app-level metric family this repo publishes must be drawn by some panel | `tests/test_dashboards_cover_metrics.py`, assertion (2) | a new gauge forces a panel — the repo refusing to ship a metric nobody can see |
| Six drills are `blocked` on this mode, and substitution is forbidden | `infra/runbooks/drills-order-path.md:13` | this mode is the whole precondition of the order-path tier |

## Decisions

### D1 — One mode, two plan-carried fields

`_MODES` gains `"rest-hold"`. An intent in that mode carries two new fields, both required for it and both refused on the other two modes:

- **`offset_pct`** — how far passive of the touch the order is priced, **as a percentage: `5.0` means five percent**, converted to a fraction at the pricing site. A1, F2, E and G use a wide value so the order can never fill; A2 uses a tight one so the market reaches it while the engine is down.
- **`hold_minutes`** — how long the order rests.

**The units are load-bearing and the dangerous misreading is the quiet one.** `_REST_CANCEL_OFFSET = 0.05` is a *fraction*, so an author copying that constant's shape would write `offset_pct: 0.05` and get an order **five hundredths of a percent** from the touch — which fills, on a mode built never to. The opposite slip is loud and harmless: `500.0` prices absurdly and never places. So the percentage reading is fixed here, stated in the plan-check output beside the value, and pinned by a test asserting `offset_pct: 5.0` prices at `0.95 ×` the bid — the same arithmetic `rest-cancel`'s own test pins for its constant.

One mode with a parameter rather than two named modes: the drills differ in a *distance* and a *duration*, not in kind, and a vocabulary that grows once per distance wanted is a vocabulary that will grow again.

`plan_refusals` gains its first mode-aware rules, all refusing at the plan wall before anything reaches the venue:

- `rest-hold` without both fields, or either field on another mode.
- `hold_minutes` outside **1–60**.
- `offset_pct` not strictly positive — zero or negative prices the order at or through the touch, which the post-only submission path rejects.
- `action` other than `open`. No drill needs a resting close, and a resting reduce-only order is a different animal that should be specified when something wants it.

### D2 — Every mode branch decides on a property, never on a name

The four sites become explicit about all three modes. This is the change that stops the defect in the preamble:

| site | today | with `rest-hold` |
| --- | --- | --- |
| `executor.py:1237` price | 5 % constant, or join the touch | `offset_pct` passive of the touch |
| `executor.py:1111` `falling_back` | `!= "rest-cancel"` ⇒ **True** | **False** — never an IOC, never a cross |
| `executor.py:1965` cancel-on-ack | cancels | **does not cancel** — the mode's whole point |
| `executor.py:2050` outcome | `rest_cancel_ok` | `rest_hold_expired` |
| `executor.py:1177` `timebox_at` | `_TIME_BOX` | `hold_minutes` |

**`:1111` is the line that would cost money.** A reviewer reading this spec should check it first.

### D3 — What ends the hold, and what the cap is for

At `hold_minutes` the order is cancelled and the intent **stops** — it never falls back to the marketable ladder. The terminal outcome is `rest_hold_expired`, joining `rest_cancel_ok` in the vocabulary `infra/runbooks/engine-procedures.md` enumerates for an operator.

The cap of 60 minutes is bounded-by-construction safety: no plan may rest an order indefinitely, and the author sizes the hold to the induction rather than to a constant that must fit both a five-second kill-switch drill and a forty-five-minute reboot. It is not inherited from `PLAN_TTL`, which governs plan staleness at load time; it is chosen here, and 60 keeps a rest-hold intent's pinning of `self._plan` inside the same order of magnitude the plan wall already tolerates.

**While the engine is stopped the timer cannot run.** G, A1 and A2 stop the engine deliberately, so their orders rest at the venue for as long as the induction lasts, and it is the restart's adopt pass that ends them. That is those drills' expectation, not a gap.

### D4 — The safety envelope, kept deliberately

Nothing in this mode weakens an existing bound:

- **The kill file** still revokes a resting order within one 5-second tick. This is drill E's subject, and today that path is exercised only against `execute`; D8 adds the `rest-hold` case.
- **Quote silence** (30 s) still revokes. Waiving it would delete drill F2, whose entire subject *is* that sequence — 30 s of silence, one cancel attempt, no retry, `ambiguous` after `_ACK_WAIT` — and whose result decides whether `re-cancel-on-reconnect` is ever built.
- **`_ACK_WAIT`** is unchanged.
- **The restart adopt pass** is unchanged. A `rest-hold` order is `action: open` and therefore a non-reducer, so the pass attaches it and then cancels it. That is drill G's expectation, and a reducer classification would be a finding rather than a convenience.

### D5 — No touch-following, and no guard needed for it

A `rest-hold` order is priced once, at placement, from the touch at that moment, and nothing moves it afterwards. That is the property the drills need: a stable subject rather than one chasing the market, since a reprice is a cancel and a new order and would break exactly the continuity being measured.

**This decision adds no code.** `_reprice` is not a touch-follower — its own docstring names its two callers as "the venue's synchronous post-only rejection and its accept-then-cancel", both *crossing* surfaces — so a passive order never reaches the ladder at all. A wide `offset_pct` cannot cross; a tight one that does is repriced passively by the existing path and then rests, which is the correct handling rather than a special case. A "never reprice" guard here would be a guard for a door with no production caller, which `.claude/rules/spec-plan-locations.md` forbids. The decision is recorded because the property is load-bearing for the drills and the next reader should know it is inherited rather than enforced.

### D6 — The gauge, its panel, and the two things it cannot see

A mode that deliberately leaves an order resting for up to an hour ships with the instrument that shows it. `zcrypto_exec_resting_order_age_seconds` — the age of the currently resting order, zero when none — published from `on_timer`, through the `_inc_order` idiom, from the engine's **own state**. No venue read, no nonce cost, no new failure mode. A panel on `infra/grafana/engine-dashboard.json` accompanies it, because the repo's own guard refuses to ship a metric nobody can see.

**Its HELP text must state its two blind spots, or the gauge becomes a false all-clear:**

1. **It is the engine's belief, not venue truth.** Drill F2 is precisely the divergence: the engine attempts one cancel, cannot reach the venue, journals `ambiguous` and drops the plan — while the order may still be resting at Kraken. The gauge reads zero.
2. **Nothing publishes while the engine is down**, which is G, A1 and A2's whole window. That case belongs to the engine-dark alerting, not here.

Both are properties of where the number comes from, so they belong on the surface an operator reads, not in a doc they would have to find.

### D7 — The alert rule, and why its push comes last

One rule: **an order has rested longer than the maximum `hold_minutes` a plan may legally declare**, plus one evaluation interval of margin. The threshold is derived from D3's cap rather than from an unmeasured normal range — anything beyond it is definitionally stuck, so no drill has to run before the number can be chosen.

**Its push is sequenced after the engine converge, not with the other Grafana work.** A rule pushed before its metric's first record pages a spurious no-data alert, and the engine — which publishes this family — converges after the fleet's Grafana push. The rule is committed here with the rest; only its push waits.

### D8 — Verification

Each of these is a guard, so each is proven by constructing the defect it names and watching it trip, on a fixture where the defect and correct behaviour differ:

- **`_MODES`' membership is pinned.** Its absence is why the preamble's defect would ship green.
- **A `rest-hold` intent driven past its hold submits exactly one order, post-only, and never an IOC.** The live-money guard; the mutation is `falling_back` restored to `mode != "rest-cancel"`.
- **It is not cancelled on acknowledgement** — the exact inverse of `rest-cancel`'s defining test, and the property the drills need.
- **The kill file revokes a resting `rest-hold` order within one tick.**
- **Quote silence still revokes it.**
- **Price is `offset_pct` passive of the touch on both sides**, with `rest-cancel`'s 5 % unchanged.
- **Every plan-wall refusal in D1**, each with its own fixture.
- **The gauge reads the resting order's age and returns to zero when it ends** — and a true positive beside it, so an always-zero gauge cannot pass.

A live drill is not part of this spec's verification: the order-path tier runs at rung 1 on the owner's word, after this mode and `00106` are converged.

## Runbook

`infra/runbooks/engine-procedures.md` gains the `rest-hold` plan shape beside Drill A's, and `rest_hold_expired` joins the outcome vocabulary an operator reads back. `infra/runbooks/drills-order-path.md`'s standing note that six drills are `blocked` for want of this mode is re-tensed by the PR that lands it — the drills stay blocked on the converge, not on the instrument.

## Out of scope

- **`cancel-on-stop` must not be built here.** Drill G exists to measure what Kraken does with a resting order across `systemctl stop`, and that behaviour is unverified in this repo. Building the enhancement first would answer G's question before G runs, and destroy the measurement.
- **`re-cancel-on-reconnect`** — drill F2's result decides whether it is built at all.
- **A fresh order-semantics verification pass.** `cli/engine/order-semantics-verified.json` records what a nautilus *version* does; this changes our code, not the adapter's behaviour, so the existing record stands.
- **Any live order.** The mode ships disarmed and reaches the engine only on an attended converge.
