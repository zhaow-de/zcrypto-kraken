# 00090 — the rung-1 order path: the first real-money submission

Third of [[T0018]]'s five-spec risk-first sequence, after `00088` (the execution safety envelope, live 2026-08-12) and `00089` (venue truth, live 2026-08-16), and running after `00094` (the twelve-leg pipeline, live 2026-08-16) on the owner's 2026-08-14 sequencing ruling. This is the first spec in the project whose defects cost capital rather than time: every prior spec could be wrong and lose nothing but rework.

The sequence exists so that containment ships before the capability it contains. `00088` built arming, a latching kill switch, a fail-closed venue gate and a post-restart reduce-only hold, and deliberately submitted nothing. `00089` built the frozen `VenueState` and shipped `size_order`, `INSTRUMENT_IDS` and `fx_eur_notional` **pure and production-uncalled**, so that this spec inherits one proven sizing function instead of writing one beside real money. This spec is where the first order is placed, and where `00088`'s guards are proven to *stop* something rather than merely to compute a verdict correctly.

______________________________________________________________________

## D1 — Scope: the commanded probe path only. The model does not drive real money in this spec.

Two readings of "the rung-1 order path" exist in the repo and they describe different builds. §12 says rung 1 **is** the T2 tax-probe set — one margin long plus one margin short, each across ≥2 rollovers, one closed and one settled, ~€10–30. [[T0018]]'s spec table says "maker-first state machine, submission, fill/fee ingestion". A tax probe is a hand-shaped commanded pair; a rebalance path is the model's 4-hourly targets submitted.

**This spec builds the commanded probe only.** The 4-hourly cycle continues to compute targets and journal intent exactly as it does today, and continues to submit nothing. The short leg settles the argument on its own: the deployable emits **no short target at all**, so the probe's short cannot come from the model under any design.

The same risk-first logic that put `00088` before this spec applies again — prove submission, fills, fees, rollovers and reconciliation with orders whose instrument, size and timing are chosen by hand, before a model drives capital on a 4-hourly clock.

Consequences, stated so later specs inherit them rather than rediscover them:

- **[[T0119]]'s `target − held` is NOT implemented here.** [[T0018]]'s spec table assigns it to `00092`; the memo had assigned it to `00090`; [[T0119]] itself names no spec. The table governs. A commanded probe has no need of it, and implementing it would drag the whole held-read design into the money-bearing spec for no rung-1 benefit.
- **The maker-first state machine is not built here** (see D3), so [[T0090]]'s realized maker/taker blend is not measured at rung 1. That topic's `ripe_when` — "rung 1 produces real fills" — was written optimistically: a blend is a ratio over a population of fills across varied book conditions, and rung 1 produces roughly four fills at a time of the owner's choosing. It is an anecdote, not a measurement. The blend becomes measurable when the deployable places ordinary rebalance deltas maker-first over weeks, which is `00092` and the ramp.

## D2 — One submission seam, with the gate and the ledger unavoidable by construction.

All order-placing code lives in a new `cli/engine/submit.py`. Nothing else in `cli/` may call the adapter's submit path.

```
OrderSubmitter(gate: ExecutionGate, ledger_writer, *, max_notional_eur: float)
```

The constructor **evaluates the gate itself** and raises unless the verdict permits. There is no way to obtain an object capable of submitting without a passing evaluation that happened at construction, so freshness is a property of the type rather than a check a caller may forget. The submitter is short-lived by design — constructed per probe invocation, never held across cycles.

`submit()` performs four steps in a fixed order, any failure aborting before the venue is touched:

1. **Constraint check** — `size_order` against the frozen `VenueState`, carrying D8's denomination assertion.
2. **Notional ceiling** — refuse above `max_notional_eur`.
3. **Submit** through the adapter.
4. **Ledger row**, written *before* returning. A failed ledger write fails the submit.

[[T0018]] rules that this spec's cold review must treat "the gate is unavoidable AND the ledger is unavoidable" as **one** first requirement, not something `00088` hands over. That is not rhetorical — both are avoidable today. `write_exec_record` has a single call site, a `_sink` closure installed only by `zcrypto engine run`; `zcrypto engine cycle` installs no sink and therefore writes no exec record at all; and `_update_metrics` **swallows a raising sink** and logs it, so a persistently failing ledger write degrades to a log line nothing alerts on.

**The exec record is written when submission happens, not at cycle completion.** Today's shape is a post-cycle write from the metrics sink. From this spec on, that would mean orders placed plus a process death before completion leaves no forensic trace at all. Submission-time writes remove that window.

**The notional ceiling is doubled deliberately.** Our own cap lives in the submitter; nautilus's `RiskEngineConfig.max_notional_per_order` is set independently on the node. The node passes no `risk_engine` config today, so this ceiling does not exist at any layer. Two layers fail for different reasons: ours catches a wrong *computation*, the framework's catches a wrong *submission* regardless of origin, including paths this spec did not anticipate. Belt-and-braces is usually a smell; for a single scalar bound on the first real-money path it earns its cost. It bounds magnitude only — a correctly-sized order on the wrong instrument or the wrong side is the constraint checks' and reconciliation's problem, not the ceiling's.

## D3 — Market orders, sized off the store's 4h close.

The engine subscribes to **no market data**. There is no quote in the `Cache`; the only price it holds is the store's 4-hourly OHLC close, up to four hours old. Maker-first would therefore drag in a quote subscription or a REST ticker path, plus three parameters [[T0090]] explicitly leaves to executor design: the offset inside the spread, the time-box, and the cross-on-timeout policy.

The probe must **actually fill** — it has to hold positions across ≥2 rollovers and reach a terminal state on each leg. A resting maker order that never fills costs nothing and fails the probe.

At €10–30 a price up to four hours stale moves the notional by a couple of euros, which is irrelevant at this size and material at no size the probe reaches.

**One command invocation places at most one order.** No command opens both legs. A mistyped argument or a sizing defect then costs one order rather than a pair.

## D4 — The probe's shape: a margin long and a margin short, leverage per order.

`--leverage` is a **required argument with no default**. The standing ruling keeps `default_leverage` unset precisely so a global default cannot silently lever every ordinary rebalance, and records that "rung 1's T2 probe passes leverage per order instead". A mandatory argument makes margin a conscious per-order act and leaves the cash-by-default posture intact.

`--notional-eur` is likewise explicit rather than derived. `shadow_nav_eur = 1000.0` is a shadow constant and has no business sizing real money; nothing in `EngineConfig` today distinguishes "the NAV the model sizes against" from "the capital actually at risk", and this spec does not conflate them.

Rollover fees are a **third cost term** that only margin positions incur, charged per 4-hour window and asymmetric between the legs: a short extends the base crypto (BTC 0.01–0.02 %/4h, alts 0.02–0.04 %), while a margin long borrows quote so the fiat rate applies (~0.025 %). The probe's purpose is producing **rollover ledger rows** for the tax pipeline, not merely incurring the cost — so [[T0018]]'s longer phrasing "fill/fee/**rollover** ingestion" governs over the spec table's shorter "fill/fee ingestion".

## D5 — Terminal states: the short is closed by the engine, the long is settled by hand, the residual is disposed.

Close and settle are **distinct venue actions with different mechanics**, recorded in the master plan's one defining sentence: closed = an opposing order with P&L realized in the quote currency; settled = delivering the asset. The fee difference is recorded twice in the repo — trade fees on both open and close, **none on settling in kind**.

**Which leg is settled is a decision, not a coin flip, and no prior doc made it.** Six ratified mentions say "one closed, one settled"; none says which. The asymmetry is mechanical and therefore jurisdiction-independent: settling a **long** repays the borrowed quote from balance and keeps the crypto — no disposal, cost basis carried from the opening price; settling a **short** delivers the borrowed base, and that delivery *is* a disposal. Settling the short would make both legs look like disposals, measuring almost nothing.

**Therefore: settle the long, close the short.** That exercises the maximum treatment difference the probe exists to measure.

**The settle is performed by hand in the Kraken Pro UI.** Kraken exposes settlement as a real API operation (`ordertype=settle-position` on REST `AddOrder` and WS v2 `add_order`) — it is not UI-only — but **nautilus 1.230.0 cannot emit it**, three ways over: `KrakenSpotOrderType` is not exported to pyo3, the submit entrypoint types `order_type` as the generic nine-member `OrderType`, and `command.params` is mined for exactly one key, `leverage`. There is no `tags`/`oflags`/`userref` passthrough to carry it. The alternative — a direct signed REST call inside the submitter — would put a second order path into the one spec whose entire design is that there is exactly one, for a single action performed once whose evidence lands in Kraken's export either way.

**The settled long's residual is then disposed by the engine**, leaving the probe flat. Keeping it as a deferred lot was considered and rejected: an untargeted holding would become `held` for `00092`'s `target − held`, which would compute a delta to unwind it — selling the very lot whose purpose was to remain unsold. It is also invisible today (`use_spot_position_reports=False` means spot balances are not symbol-keyed positions) and would appear for the first time if that flag were ever flipped, which is a latent trap firing on an unrelated config change.

Disposing does not weaken the probe. The ledger still shows two distinct shapes — a settle (no trade, no fee) followed by a separate spot disposal, against the closed leg's single opposing trade — and it adds a test keeping the lot could not run: whether Blockpit computes the disposal's gain from the **original margin open price**, per the cost-basis carry, or from the settle moment. What it gives up is exercising the deferral's eventual realisation across a tax year, which a plumbing-and-classification probe was never going to reach.

## D6 — Reconciliation runs inside the 4-hourly cycle, read-only.

The go/no-go requires zero unreconciled order and position states, and the probe's positions live more than eight hours — across two or three cycle boundaries — to span ≥2 rollovers. Reconciliation's value is proportional to how often it runs.

The cycle is already the fleet's proven 4-hourly heartbeat, with a journaled artifact, a completion window and alerting that fires when it misses. Building a second scheduler on the same cadence would duplicate the most operationally-proven loop in the system. So reconciliation is a **read-only step inside `run_cycle`**: it reads live venue state, compares against what the ledger records as submitted, and writes the result to `exec-<HH>.json`.

**It submits nothing.** Since submission is possible only through D2's module, and that module is constructed only by the probe command, an armed engine cannot place an order at a cycle boundary. Arming during the probe window does not create a second order path.

**Execution artifacts stay structurally disjoint from `cycle-*.json` and `failed-cycle-*.json`.** A divergence must never read as a broken research day — the Stage-6a concordance streak (37 as of 2026-08-16, ratified, bar 14) is scored on those artifacts and must not be disturbed by execution outcomes.

That this addition is genuinely read-only is a **cold-review requirement**, not a footnote: it touches the file whose artifacts the ratified streak depends on, and "read-only" is a claim a reviewer must verify rather than accept.

## D7 — [[T0140]] ruled: the venue record's schema stamp stays provenance-only.

[[T0140]] was left open and deliberately undecided so that this spec would rule it, because the answer depends on a design choice only this spec makes: does reconciliation read the `venue-<HH>.json` payload **structurally**?

**It does not.** D6's reconciliation reads live venue state. The journaled record is read for nothing structurally; it remains a forensic artifact.

The reasoning is not convenience. Reconciliation exists to catch divergence between our intent and the venue's reality. A journaled snapshot is our own prior belief — comparing against it would detect that our record drifted, not that the venue did, so it would pass in exactly the case that matters least and stay silent on the case that matters most.

Therefore **[[T0140]] takes option (b)**: `VENUE_SCHEMA_VERSION` is accepted as provenance, and that is **stated at the constant** so the next reader does not mistake it for an enforced invariant. No `validate_venue_record` is owed. The honest cost: a stale or wrong `venue-<HH>.json` is caught by nothing, because nothing reads it — an argument for option (a) eventually, but not one this spec's needs create.

The same reasoning does **not** transfer to `EXEC_SCHEMA_VERSION`, which this spec is the first to change the meaning of by filling `submitted`. That stamp is out of scope here and stays as it is.

## D8 — [[T0138]] discharged: the denomination guard lands at the sizing call site this spec creates.

`size_order` takes `costmin` as a bare number and assigns denomination-ownership to the caller. This spec **is** that caller — [[T0138]]'s `ripe_when` fires precisely because a production read of `.costmin` now exists.

The guard asserts, at the comparison site, that the notional's denomination matches `constraints.costmin_quote`, and **fails loudly** on mismatch rather than proceeding. A BTC-denominated floor is `0.00002` and a EUR one is `0.45` — four orders of magnitude apart. Compared the wrong way round, the check fails **open**: every order clears a `0.00002` bar, silently, on the live trade path.

The guard belongs beside the comparison, not in `InstrumentConstraints.__post_init__` — a validator there would couple a plain evidence dataclass to a committed constant and reject the deliberately-wrong hand-built states the concordance tests depend on, while guarding the wrong proposition.

Note that the probe's legs are EUR-quoted, so **the guard is not exercised in production by this spec** — it is proven by a constructed defect. That is the correct time to build it regardless: the call site exists now, and the first `/BTC` sizing will arrive in `00092` when nobody is thinking about denomination.

## D9 — `reduce_only` gets a definition, covering both margin and spot.

Nothing in the repo defines what "reducing" means, and `00088` states plainly that "this spec proves the verdict is computed correctly, never that it stops an order — that proof is owed at the first submission and belongs to `00090`."

- For a **margin position**: an order whose signed quantity strictly shrinks `|held|` for that symbol, read from `VenueState.positions`. Zero held means nothing is reducing.
- For a **spot holding**: a sell that shrinks the spot balance. This case exists because D5's residual disposal is a spot sell, and it must remain executable when the gate is latched at `REDUCE_ONLY` after a restart.

Narrow is correct here. The engine latches reduce-only after **every** start, so this predicate gates the probe's first submission following any converge — and `00088`'s ruling that clearing the hold requires a human act is a floor this spec may narrow but must never widen.

## D10 — No venue truth, no orders.

`00089` D7 deliberately left the fail-closed consequence to "the spec where orders exist to refuse". This is that spec: if `venue_state` is `None`, the submitter refuses. A degraded leg — one flagged by `runtime_concordance` — is refused individually rather than failing the whole invocation, since one command places one order.

## D11 — The probe window's obligations.

[[T0018]] registers two window-closing duties this spec owes:

- **Converge `exec_armed` back to false when the probe window closes.** Armed is not a resting state.
- **Treat a restore of the engine state directory as re-arming** — restoring state could otherwise resurrect an armed posture nobody intended.

The operator sequence the restart hold shapes: converge → hold latched → the owner clears it by the documented human act → arm → probe. The probe cannot be run absent-mindedly after a deploy, which is `00088` working as designed.

______________________________________________________________________

## Verification

Every property below is proven by a **constructed defect**, not by assertion — a guard is unproven until the failure it names is seen to trip it.

- **The gate is unavoidable**: no `OrderSubmitter` can be constructed from a refusing verdict; a test attempts it and sees the raise. Grep proves no other module reaches the adapter's submit path.
- **The ledger is unavoidable**: a failing ledger writer fails the submit, and the order does not reach the venue.
- **The ceiling holds at both layers**: an over-cap order is refused by the submitter; with the submitter's check disabled, nautilus's `max_notional_per_order` refuses it.
- **The denomination guard trips**: a `/BTC` leg's `2e-05` floor compared against a EUR notional raises; the matched pair passes.
- **`reduce_only` stops an order**: at `REDUCE_ONLY`, an increasing order is refused and a reducing one is permitted, for both the margin and spot cases.
- **`venue_state is None` refuses.**
- **Reconciliation is read-only**: the cycle's addition is proven not to submit, and its output lands only in `exec-<HH>.json` — `cycle-*.json` is byte-identical with and without it.
- **The Stage-6a streak is undisturbed**: the gate's status, streak and mismatch counters are read before and after the first probe cycle and are unchanged except for the day's ordinary advance.

Rung 1's own acceptance is venue-side and attended: both legs filled, each held across ≥2 rollovers with rollover rows present, the short closed, the long settled and its residual disposed, the account flat, and every artifact reconciled. The T2 verdict — bucket assignment, rollover fees attached as costs, FIFO lots intact, no phantom balances — is read in Blockpit after a re-sync and recorded in the decisions log. Failure triggers the T3 fallback, which is out of scope here.

## Out of scope

- **Model-driven submission and the maker-first state machine** — `00092`, per D1 and D3.
- **[[T0119]]'s `target − held`** — `00092`, per [[T0018]]'s spec table.
- **The weekly tracking-error report and cost recalibration from real fills** — `00091`.
- **[[T0121]]'s limit-breach counter** — its `ripe_when` points at the executor's order/position/PnL families, but a commanded probe exercises no whole-book limit, so there is nothing for the counter to count. It rides `00092`.
- **`EXEC_SCHEMA_VERSION`'s own provenance-versus-validation question** — noted in D7, not ruled here.
- **The T3 Blockpit fallback transform** — triggered by a T2 failure, specified in §11, and not built speculatively.
- **A second order path via direct signed REST** — an **explicit drop**, not a deferral: no topic is owed. If `settle-position` ever needs automating, it arrives with its own spec and its own argument for a second path.
- **After-tax scenario reporting (S-A/S-B)** — §11 promises deployment-relevant returns under both tax scenarios, and nothing implements it anywhere in the repo. That gap predates this spec and is not created by it.

## Human gates

Two money gates must clear before this path is **run**, distinct from it being built: **D3(ii)** tiny-live sleeve funding, and **D3(iii)** probe sign-off scheduling the T2 set within the first two 6b weeks. Landing the code is not the same act as arming the host, and every order-placing invocation takes the owner's explicit word immediately before it runs.
