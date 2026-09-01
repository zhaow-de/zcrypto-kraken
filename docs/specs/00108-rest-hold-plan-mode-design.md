# 00108 — the `rest-hold` plan mode: an order that stays

Resolves the `rest-hold` build item of [[T0018]], registered in spec `00105` D4. One plan mode, two plan-carried fields, one gauge, one panel — on one branch and one PR, at the Fable review floor (live trade path). The code ships disarmed and reaches the engine only on an attended converge.

**What it is.** A third plan mode beside `execute` and `rest-cancel`, whose order is placed passively, is **not** cancelled when the venue acknowledges it, and rests for a duration the plan author declares. It exists because five drill sections of `infra/runbooks/drills-order-path.md` — A1, A2, E (with its E′ leg), F2 and G — have no subject without it: `rest-cancel` cancels inside the `OrderAccepted` handler, so nothing is resting by the time any induction lands, and that page forbids substitution outright ("an order cancelled a second after it was placed exercises none of what these drills measure").

**The defect this spec exists to prevent.** The one-line version of this change — adding `"rest-hold"` to the mode vocabulary — parses cleanly and then runs the new mode with **full `execute` semantics**: joining the touch, repricing as it moves, and at the fifteen-minute time box crossing the spread with up to three marketable IOCs. On the live trade path. Nothing goes red, because no test pins the vocabulary's membership, and every mode branch in the executor is written `== "rest-cancel"` or `!= "rest-cancel"` — so a third name falls into the `execute` arm at every one of them. A mode whose entire purpose is *never fills, keeps resting* would, written the obvious way, become the most aggressive order path in the system.

## The measured basis

Read from the repo on 2026-09-01 at `develop` `904862a8`:

| fact | where | consequence |
| --- | --- | --- |
| The mode vocabulary is enumerated in exactly one machine-readable place and validated by membership alone | `cli/engine/probeplan.py:23` `_MODES = frozenset({"execute", "rest-cancel"})`; validated at `:92-94` | a third mode is one token away from parsing — and from running as `execute` |
| **No test pins the vocabulary's membership** | absence, over `tests/` — `grep -rn "_MODES" tests/` returns nothing | the miswiring above ships green; D8 makes pinning it the first test |
| The executor consults `mode` at exactly **four** sites, every one written `== "rest-cancel"` or `!= "rest-cancel"` | `cli/engine/executor.py:1111`, `:1237`, `:1965`, `:2050` | a third mode inherits the `execute` arm at all four; D2 makes each explicit about all three modes and turns the two money-line arms around, so the default is the one that cannot cross |
| `falling_back` is set `mode != "rest-cancel"` at the time box | `executor.py:1111`, under the comment "A rest-cancel drill must never execute" | left as-is, a `rest-hold` order fires up to `_MAX_IOC_ATTEMPTS` marketable IOCs at expiry — **the live-money line in this change** |
| `_TIME_BOX = timedelta(minutes=15)`, armed once in `_start_intent` and never re-armed | `executor.py:67`, `:1177` `timebox_at=now + _TIME_BOX`, enforced at `:1108` | too short for E′ (a human phone leg) and A1 (a reboot plus its verify list); D3 replaces it per intent |
| `rest-cancel` cancels inside the `OrderAccepted` handler | `executor.py:1965-1969` — "rest, be acknowledged, come straight back off the book" | there is no window in which an induction can act; this is why no existing mode serves the drills |
| **`_on_cancel_ack`'s unrequested arm re-places the order.** It runs `_reprice` for ANY venue-originated `OrderCanceled` or `OrderExpired` while `phase != "ioc"`, testing nothing about crossing | `executor.py:2056-2064`; `_reprice` at `:1352` resubmits post-only GTC priced off the CURRENT touch, up to `_MAX_REPRICES = 5` | a venue- or operator-initiated cancel of a resting order silently puts a new one back; D5 rules on it, and it is a **fifth** mode site |
| `_REST_CANCEL_OFFSET = 0.05` is a bare module constant, not per-intent | `executor.py:76` | one fixed distance cannot serve A1/F2's "far from the touch" and A2's fill-while-down together; D1 makes it per-intent |
| `PLAN_TTL = timedelta(minutes=60)` is checked against `created_at` when a plan is validated | `probeplan.py:19`, `:192` | it bounds when a plan may **start**, never how long an intent runs — so D3's cap is a fresh decision, not an inherited one |
| The kill file is a gate **input**; it reaches an order only while one is `_active`, through the 5-second tick, and gets exactly one cancel attempt with no retry | `cli/engine/execgate.py`; `executor.py:60` `_TICK_SECONDS = 5.0`, `:1101-1103` | the kill switch works on a resting order — and is drill E's subject — but only while the intent is live |
| `_QUOTE_SILENCE = 30 s`, `_ACK_WAIT = 30 s` | `executor.py:66`, `:73` | both are kept; F2 has no subject without the first |
| **Field-shape refusals live in `_parse_intent`, not in `plan_refusals`** — `leverage`'s own range check is there, and `plan_refusals` carries only plan-level, environment-dependent reasons (TTL, ledgered id, notional cap, margin floor) | `probeplan.py:73-120` against `:158-211` | D1's new refusals are field-shape checks and land at the parse wall beside `leverage` |
| The metrics idiom is a module-level handle wrapped in try/except that logs and continues — a **helper-level** guard, not a caller-level one | `executor.py:197-203` `_inc_order` | anything a publish site computes *around* that call is unprotected, and `on_timer`'s `except` (`:656-662`) drops the plan and nulls `_active`; D6 wraps the whole publish |
| `on_timer` already runs every tick and the adopt pass is guarded to run once | `executor.py:648-652` | the gauge needs no new loop and no venue read |
| Every app-level metric family this repo publishes must be drawn by some panel | `tests/test_dashboards_cover_metrics.py`, assertion (2) | a new gauge forces a panel — the repo refusing to ship a metric nobody can see |
| The remote-write `keep` relabel is an anchored allowlist naming every family by hand, and lists no gauge of this kind | `infra/ansible/roles/capture/files/config.alloy:157` | a new family absent from it never leaves the engine host: the panel would render empty forever |
| Every path that abandons an order the venue may still hold logs at CRITICAL, and a rule already pages on those lines | `executor.py:1447` (`_cancel`'s swallowed raise), `:1996` (`OrderCancelRejected`), `:1425` (`_strand_ambiguous`); `infra/grafana/alerts.yaml:612` `zcrypto-engine-error-logs`, `level=~"ERROR\|CRITICAL"`, `container="engine"`, `for: 0s`, message hoisted onto the page | the orphan condition is already covered on the surface that can see it; D7 declines to add a second rule that cannot |
| Five drill sections are `blocked` on this mode, and substitution is forbidden | `infra/runbooks/drills-order-path.md:13` — "so E, G, F2, A1 and A2 have nothing to act on until a `rest-hold` mode exists" | this mode is the whole precondition of the order-path tier |

## Decisions

### D1 — One mode, two plan-carried fields

The mode vocabulary gains `"rest-hold"`. An intent in that mode carries two new fields, both required for it and both refused on the other two modes:

- **`offset_pct`** — how far passive of the touch the order is priced, **as a percentage: `5.0` means five percent**, converted to a fraction at the pricing site. A1, F2, E and G use a wide value so the order can never fill; A2 uses a tight one so the market reaches it while the engine is down.
- **`hold_minutes`** — how long the order rests.

**The units are load-bearing and the dangerous misreading is the quiet one.** `_REST_CANCEL_OFFSET = 0.05` is a *fraction*, so an author copying that constant's shape would write `offset_pct: 0.05` and get an order **five hundredths of a percent** from the touch — which fills, on a mode built never to. The opposite slip is loud and harmless: `500.0` prices absurdly and never places. So three things, all of them in this change:

1. The percentage reading is fixed in code, at one site, and pinned by a test asserting `offset_pct: 5.0` prices at `0.95 ×` the bid and `1.05 ×` the ask — the same arithmetic `rest-cancel`'s own test pins for its constant.
2. **`probe-plan --check` echoes the resolved distance and duration in words**, on the per-intent line an operator reads before placing anything. `_intent_floor_check` prints `[0] BTC/EUR buy open rest-hold` today and stops; the two fields that decide whether the order can fill are invisible on the one pre-flight surface there is. A line reading `0.05% passive of the touch, holding 45 min` is what makes the slip look wrong to the person about to place it, and a test asserts the rendered `%` for `offset_pct: 0.05` rather than only the `5.0` arithmetic.
3. No numeric floor on `offset_pct` beyond "strictly positive". A2's whole subject is a tight offset the market reaches while the engine is down, and this spec cannot name that drill's lower bound without the drill; a floor picked here would be a number invented to look safe. The echo above is the mitigation, and it is an operator-facing one because the decision is the operator's.

One mode with a parameter rather than two named modes: the drills differ in a *distance* and a *duration*, not in kind, and a vocabulary that grows once per distance wanted is a vocabulary that will grow again.

**The refusals land at the parse wall**, in `_parse_intent`, beside `leverage`'s own range check — not in `plan_refusals`, which carries plan-level reasons that depend on the environment (staleness, the ledger, the notional cap, free collateral) and reports them plurally. Two consequences, both taken deliberately: the first violating field raises and the author sees one reason per round trip, and a malformed hold journals under `plan_id="unparseable"` with `plan={}` like every other shape violation (`executor.py:996-1002`). Both stop the order; the cost is forensic, it is the cost every existing shape refusal already pays, and the compensation is that `_INTENT_KEYS` typo-safety covers the two new keys for free.

The refusals:

- `rest-hold` without both fields, or either field on another mode.
- `hold_minutes` outside **1–60**.
- `offset_pct` not strictly positive — zero or negative prices the order at or through the touch, which the post-only submission path rejects.
- `action` other than `open`. No drill needs a resting close, and a resting reduce-only order is a different animal that should be specified when something wants it.

### D2 — Every mode branch is explicit, and the two that cost money default to the passive arm

The four existing sites become explicit about all three modes, and a fifth is added by D5. **The branches still test the mode NAME** — there is no property to test, and minting a `crosses_at_the_box` attribute over a three-element vocabulary is an abstraction with one reader. What stops the preamble's defect is two deliverables that only work together:

1. **The vocabulary is pinned** (D8's first test). A fourth mode cannot arrive without an edit to `MODES`, and that edit is the moment a reviewer is sent to the rows below.
2. **The two arms where a wrong inheritance would cost money default passive.** `falling_back` is turned around to `mode == "execute"`, so anything that is not `execute` never crosses; cancel-on-ack is already `== "rest-cancel"` and deliberately stays that way, so anything else is left resting. A fourth mode added and nowhere else inherits *no cross at the box*, and an order that rests rather than one that fills.

Stated as the residual risk rather than as a guarantee: the price site's `else` still joins the touch and the unrequested-cancel arm still reprices, so a fourth mode inherits `execute`'s pricing and its re-place behaviour at those two. Neither crosses the spread; both can fill a passive order. The vocabulary pin is the whole mechanism forcing those two rows to be read.

| site | today | with `rest-hold` |
| --- | --- | --- |
| `executor.py:1237` price | 5 % constant, or join the touch | `offset_pct` passive of the touch |
| `executor.py:1111` `falling_back` | `!= "rest-cancel"` ⇒ **True** | **False** — never an IOC, never a cross |
| `executor.py:1965` cancel-on-ack | cancels | **does not cancel** — the mode's whole point |
| `executor.py:2050` outcome | `rest_cancel_ok` | `rest_hold_expired` |
| `executor.py:2064` unrequested cancel | `_reprice` — a new order at a new price | **terminal `rest_hold_venue_canceled`** (D5) |
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

### D5 — A venue-originated cancel ends the intent; it does not re-place the order

**This decision replaces an earlier one that rested on a false premise, and it adds code.** The premise was that `_reprice` is reachable only from crossing surfaces — `_reprice`'s own docstring says so — and that a passive order therefore never reaches the ladder. The docstring describes its two *callers*, not its *reachability*: `_on_cancel_ack`'s unrequested arm (`executor.py:2056-2064`) runs `_reprice` for **any** venue-originated `OrderCanceled` or `OrderExpired` while `phase != "ioc"`, and tests nothing about crossing. Driven directly on this tree — a resting order, `cancel_requested is False`, `phase == "resting"`, then one `OrderCanceled` — the executor submits a **second** post-only GTC priced off the current touch, and will do so up to `_MAX_REPRICES = 5` times.

`rest-hold` is what makes that path matter: `execute` rests at most fifteen minutes and `rest-cancel` milliseconds, while this mode rests up to an hour, during which the venue may cancel for its own reasons and the operator is being *trained* to cancel by hand — F2's operator-action step is a direct cancel in the Kraken web UI.

**The ruling: for `rest-hold`, an unrequested cancel is terminal.** The intent finishes `rest_hold_venue_canceled` (or `partial` if anything filled) and nothing is resubmitted. A resting drill order is the drill's *subject*; re-placing it swaps the subject mid-induction, for a new client-order-id the operator is not watching, at a price the market has moved to — which is exactly the continuity drill G exists to measure. Silently undoing an operator's own cancel is the worst version of the same thing.

**The guard goes in `_on_cancel_ack`, not in `_reprice`.** `_reprice`'s other caller — `_on_rejected` with `due_post_only=True` (`executor.py:2026`) — is a real production surface with a real job: the venue refused the submission because the declared price crossed, so nothing was ever resting, and the recomputed price is `offset_pct` strictly passive of the *current* touch. That recovery is what a tight-offset intent (A2's shape) needs to get resting at all, and a mode check inside `_reprice` would break it. So the property this mode really has, stated exactly:

> An order that has rested is never re-priced. The engine never follows the touch, and it never re-places an order the venue took off the book. The only re-price is the recovery from a synchronous post-only rejection, which replaces an order that never rested.

### D6 — The gauge, its panel, the two things it cannot see, and the road it needs

A mode that deliberately leaves an order resting for up to an hour ships with the instrument that shows it. `zcrypto_exec_resting_order_age_seconds{mode}` — how long the engine's current order has been at the venue, zero when none — published from `on_timer`, from the engine's **own state**. No venue read, no nonce cost. A panel on `infra/grafana/engine-dashboard.json` accompanies it, because the repo's own guard refuses to ship a metric nobody can see.

**Its HELP text must state its two blind spots, or the gauge becomes a false all-clear:**

1. **It is the engine's belief, not venue truth.** Drill F2 is precisely the divergence: the engine attempts one cancel, cannot reach the venue, journals `ambiguous` and drops the plan — while the order may still be resting at Kraken. The gauge reads zero.
2. **Nothing publishes while the engine is down**, which is G, A1 and A2's whole window. That case belongs to the engine-dark alerting, not here.

Both are properties of where the number comes from, so they belong on the surface an operator reads, not in a doc they would have to find.

**The publish must not be able to end a running plan.** `_inc_order`'s try/except guards the metrics *call*; everything a publish site computes around that call — the mode loop, the phase read, the age arithmetic — sits bare inside `on_timer`'s catch-all, whose `except` sets `self._plan = None; self._active = None`. A `NameError` there, on a tick while a real order rests, would drop the plan and leave nothing tracking the order: `_poll` is unreachable with no `_active`, the adopt pass has already run, and a kill file would then sweep nothing. So the whole publish body is wrapped, and a test makes the metrics sink raise and asserts the plan is still running and the intent still resting.

**The series needs admitting before it exists.** `config.alloy`'s remote-write `keep` relabel is an anchored allowlist; a family absent from it is dropped at the engine host and the panel renders empty forever. The family joins that regex and the per-host `required` list in `tests/test_infra_alloy_series.py` — which is silent on omission, so it is a deliberate addition — in this change. The deploy consequence is named here rather than discovered: this is an **Alloy converge on the capture primary**, a second attended converge beside the engine's, under `fleet-deploys.md`'s primary rules, and it goes **first** — a metric admitted before it is published costs nothing, while one published before it is admitted is simply lost.

### D7 — No alert rule, and what covers the condition instead

The rule this spec first proposed — *an order has rested longer than the maximum `hold_minutes` a plan may legally declare* — **cannot be built on this gauge, and is not shipped.** Two independent reasons, both structural:

1. **The ceiling and the legal maximum are the same number.** `_poll` leaves `resting` on the first tick where `now > timebox_at`, and `timebox_at` is `started_at + hold_minutes` capped at 60 minutes; the publish runs after `_pump` in the same tick, so the last non-zero sample is at most 3600 s. A threshold above the cap can never be crossed; a threshold below it fires on every legal 60-minute hold. There is no number that both stays quiet on a lawful drill and speaks on anything else.
2. **The condition the rule was for is the one where the gauge reads zero.** An order orphaned at the venue arrives one of three ways — `_cancel`'s cancel call raising, `OrderCancelRejected`, or `_ACK_WAIT` expiring into `_strand_ambiguous` — and every one of them routes to `_drop_remainder_after_ambiguity` → `_halt_plan`, which nulls `_active`. From that instant the gauge publishes 0.0 for every mode, forever, while the order rests at Kraken. The gauge is the engine's belief, and an engine that has given up on an order believes nothing about it.

A rule that cannot fire is worse than no rule: it reads as coverage on a board and in a runbook index, and the operator learns nothing until they look.

**What covers the orphan is already deployed.** All three paths log at CRITICAL and say so in words — "the order may still rest at the venue", "cancel of %s was REJECTED by the venue -- the order may still rest; the plan stops here", "the plan stops here" — and `zcrypto-engine-error-logs` selects `level=~"ERROR|CRITICAL"` on `container="engine"`, `host="zcrypto"`, `for: 0s`, hoisting the message itself onto the page. The operator's instruction is likewise already on the operating surface: `engine-procedures.md`'s "**`ambiguous` means the order may be live at the venue** — read Kraken's open orders in the web UI and establish what actually reached it before placing anything else on that symbol." Nothing about this mode changes either, and neither needs re-deriving here.

**What a rule would need, if one is ever wanted**, is a series that survives `_active` going None — the age of the oldest exec-ledger row still in `execledger._OPEN_ORDER_STATES` is the honest candidate, since that is what "stuck at the venue" means and it outlives both the intent and the process. That is a different instrument with its own scan cost and its own false-positive surface, and it is not built here: nothing in the drill program is blocked on it, and the condition already reaches a phone.

### D8 — Verification

Each of these is a guard, so each is proven by constructing the defect it names and watching it trip, on a fixture where the defect and correct behaviour differ:

- **The mode vocabulary's membership is pinned.** Its absence is why the preamble's defect would ship green.
- **A `rest-hold` intent driven past its hold submits exactly one order, post-only, and never an IOC.** The live-money guard; the mutation is `falling_back` restored to `mode != "rest-cancel"`.
- **It is not cancelled on acknowledgement** — the exact inverse of `rest-cancel`'s defining test, and the property the drills need.
- **An unrequested `OrderCanceled` on a resting `rest-hold` order submits nothing further** and ends the intent `rest_hold_venue_canceled` — D5's ruling, on the fixture that falsified the old premise.
- **The kill file revokes a resting `rest-hold` order within one tick.**
- **Quote silence still revokes it.**
- **Price is `offset_pct` passive of the touch on both sides**, with `rest-cancel`'s 5 % unchanged.
- **Every plan-wall refusal in D1**, each with its own fixture, plus a well-formed intent that parses — a refusal-only suite is satisfied by a parser that refuses everything.
- **`probe-plan --check` prints the offset and the hold**, asserted on the rendered line for `offset_pct: 0.05`.
- **The gauge reads the resting order's age under its own mode label and returns to zero when it ends** — with a second mode's label asserted zero beside it, so an always-set gauge cannot pass.
- **A raising metrics sink leaves the plan running and the intent resting** — D6's failure-mode guard.

A live drill is not part of this spec's verification: the order-path tier runs at rung 1 on the owner's word, after this mode and `00106` are converged.

## Runbook

`infra/runbooks/engine-procedures.md` gains the `rest-hold` plan shape beside Drill A's — with the units fixed in the sentence beside it — and `rest_hold_expired` and `rest_hold_venue_canceled` join the outcome vocabulary an operator reads back. `infra/runbooks/drills-order-path.md`'s standing note that five drill sections are `blocked` for want of this mode is re-tensed by the PR that lands it — the drills stay blocked on the attended converge, not on the instrument.

## Out of scope

- **`cancel-on-stop` must not be built here.** Drill G exists to measure what Kraken does with a resting order across `systemctl stop`, and that behaviour is unverified in this repo. Building the enhancement first would answer G's question before G runs, and destroy the measurement.
- **`re-cancel-on-reconnect`** — drill F2's result decides whether it is built at all.
- **A ledger-derived stuck-order series and any alert over it** — D7 names what it would take; nothing is blocked on it and the condition already pages.
- **A fresh order-semantics verification pass.** `cli/engine/order-semantics-verified.json` records what a nautilus *version* does; this changes our code, not the adapter's behaviour, so the existing record stands.
- **Any live order.** The mode ships disarmed and reaches the engine only on an attended converge.
