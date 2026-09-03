# 00111 — the adapter's blind reads: flatten's cache, and a funding gate that fails open

`zcrypto engine flatten` reports `0 resting order(s)` against an account with two open orders, and the engine's funding gate reads a free balance that overstates available cash by whatever the venue has reserved. Both trace to the same nautilus Kraken adapter, and one of them sits on the arming path rather than the red button.

## The measured basis

Every figure below was measured on the live account on 2026-09-03, not inferred. The fixture is two resting SOL/EUR buy limits placed by hand on 2026-09-01 — `OZRI5U-U7WGD-OYCOMW` (spot) and `OVNLAJ-6PXBH-T4GDXF` (2:1 margin), 0.06 @ 45.95, unfillable ~46 % below market.

**Their existence has three witnesses that do not share a code path**: Kraken's web UI, the owner's `kraken open-orders` CLI, and a nautilus client with its instrument cache populated. That matters because an earlier reading of this same defect was retracted on a control that could not distinguish blind from healthy.

**The fixture is re-confirmed before the branch spends anything, not only at the attended step.** Every decision below inherits this table, and the two limits could have filled or been cancelled since — `kraken open-orders -o json` and `kraken extended-balance -o json` are read-only, need no adapter and no allowlist change, and settle it. A reading that disagrees is a finding that stops the branch, not a number to update in passing.

| read | result | truth |
|---|---|---|
| `request_order_status_reports` (cold cache) | **0 rows**, every parameter shape, both `AccountId`s | 2 open |
| `request_order_status_reports` (cache populated) | **2 rows**, both `ACCEPTED` | 2 open |
| `request_fill_reports` (cache populated) | **6 rows** | **no committed anchor carries this quantity.** `adapter-verification/2.0.0rc4.dev20260825.md` holds 6 unique *order* txids, four of them recorded `filled_qty=0.0`, and no trade or fill id at all — so the matching count is a coincidence, not a witness (D4) |
| `request_account_state` → `locked` | **0.00000000** | Kraken `BalanceEx` `hold_trade` = **2.757** |

**Two independent mechanisms, read from upstream source at `develop` HEAD `bb721205`:**

1. `crates/adapters/kraken/src/http/spot/client.rs`, in `request_order_status_reports`: each open order is looked up by raw symbol against `instruments_cache`, and **the `if let Some(...)` has no `else`** — an unknown symbol drops the order silently, with no warning and a successful empty return. The cache's only writer reachable from Python is `cache_instrument` — `hasattr(KrakenSpotHttpClient, 'cache_instruments')` is **False** on the installed binding, so there is no batch form to reach for; **`request_instruments()` does not populate it**. `cli/engine/command.py` builds a bare `KrakenSpotHttpClient` and never caches, so the cache is empty for flatten's entire run.
2. The same file's cash branch builds `AccountBalance::from_total_and_locked(amount, Decimal::ZERO, currency)` — a **hardcoded zero** for `locked`, so the platform derives `free = total`. The adapter calls `/0/private/Balance` (amounts only) and never `/0/private/BalanceEx`, which is what carries `hold_trade`.

**Why mechanism 2 reaches the arming gate.** `venuestate.py`'s `venue_state_from_cache` builds balances from `account.balances_free()`; `command.py`'s `probe_plan` and `executor.py`'s `_pickup` take `free_zeur` from that; `probeplan.py`'s `plan_refusals` refuses a plan when `margin_required > free_zeur`. An overstated `free_zeur` makes that refusal **less** likely to fire. **The margin floor fails open**, and it does so by exactly the amount already committed to resting orders — largest precisely when the guard matters most. Nothing in `cli/engine/` subtracts commitments: no reference to `locked`, `hold_trade`, `reserved` or equivalent exists.

*(Symbols, not line numbers, throughout: a coordinate is correct only in the tree that produced it, and this project has already lost time to a citation that was right in two trees at two different lines.)*

**A hypothesis disconfirmed, recorded so it is not re-tried.** Flatten reads orders (`read_snapshot`) before it loads the listing (`read_listing`), which looks like the bug. It is not: A/B tested on the live account, cold cache **0 rows**, `request_instruments()` called first **still 0 rows**. Reordering flatten's calls fixes nothing, because that call does not populate the cache. Only `cache_instrument` does.

## Decisions

### D1 — Flatten populates the instrument cache before it reads anything

The fix is flatten's, not a reordering: after fetching the listing, feed it to the client's cache, then read. This is the minimum that makes `request_order_status_reports` and `request_fill_reports` return truth.

**Not** a workaround for an upstream defect we are hiding — the upstream silent-drop is separately reported (see D7). This is our code failing to meet a contract the adapter documents by having a public `cache_instrument` at all.

### D2 — The funding gate fails CLOSED when the free balance is known to be untrustworthy

`plan_refusals` gains a refusal: when the account reports `locked == 0` **and** any order is resting, `free_zeur` cannot be trusted and the plan is refused. This converts a fail-open safety gate into a fail-closed one **without replicating Kraken's reservation semantics**, which are non-obvious — measured, the spot order held 2.757 EUR and the 2:1 margin order held nothing.

**Keyed on the account, never on one currency.** The guard reads the whole locked map (`{currency_code: held}`), not a single `ZEUR`/`EUR` scalar: it refuses when **no** balance reports a hold while an order rests. A per-currency lookup would have to pick a spelling, and the two live surfaces disagree — the instrument quote currency is `ZEUR`, the account's free-cash key is `EUR` (measured, `{'EUR': 99.84}`) — so a wrong pick reads a permanent 0.0 and jams the gate shut with no way to tell that from a real reading. An **empty** map is treated as no balance reporting a hold, which refuses: a read that learned nothing is exactly the untrustworthy input this refusal exists to catch.

**Where it runs.** The refusal has to hold at the live arming gate — `executor._pickup`, which reads the Cache directly and can therefore see both the locked map and the resting-order count at one instant. `zcrypto engine probe-plan --check` is the other `plan_refusals` caller and it can supply neither: it reads a journalled `venue-<HH>.json`, whose `state` carries no holds and no orders. **It does not evaluate this refusal, and says so in its output** — that command's own contract already declares it "Advisory only -- the engine re-validates every plan live before any order", and widening the venue-journal record format to carry both inputs would bump `VENUE_SCHEMA_VERSION`, put three other readers' `schema_version != 2` filters and `validate_venue_record`'s exact key set in the blast radius, and add a rollback hazard on the live trade path. `VenueState` therefore gains `balances_locked` as a live field that `to_payload()` does **not** journal.

**What declining the schema bump leaves open, named rather than implied.** One of those three readers is not advisory: `executor._newest_venue_balances` returns the journalled `state.balances` and `_classify_close` hands it to `_classify_spot_close`, whose `qty <= balance` bound at `REDUCE_ONLY` is on the live trade path — that function's own docstring calls the bound plus the venue's insufficient-funds rejection "the whole guard". Those balances are `account.balances_free()`, the figure mechanism 2 above shows is overstated by whatever the venue holds. So this spec closes the fail-open at `plan_refusals` and **leaves the identically-caused one at `_classify_spot_close` open**, at the stated price of not bumping the schema. It is registered in `T0160` beside the `hold_trade` report that would remove the overstatement at its source; a decision recorded only here would be untracked.

**Rejected: computing held funds ourselves** from open orders. It requires reimplementing venue-specific reservation rules we have exactly one observation of, and a wrong reimplementation fails open again while looking correct.

**Rejected: the engine reading `BalanceEx` directly.** That is a second signed client on the trade key, which is what spec `00090`'s one-key-one-client rule exists to prevent, and `kraken-cli` is a workstation development tool that is never an engine dependency.

**The cost is real and stated**: arming is blocked whenever an order rests, which at RUNG 1 may be exactly when arming is wanted. That is the deliberate trade — a blocked arming is recoverable, an overcommitted plan is not.

### D3 — D2's guard asserts loudly the first time `locked > 0` appears

D2 keys off `locked == 0` as the signal that the number is untrustworthy. If the upstream fix lands, `locked` becomes real and the guard silently stops firing — correct behaviour reached by accident, and invisible.

So: **`locked > 0` on any balance is a loud, logged assertion**, not a silent pass. The upstream release cadence is outside this project's control, so the transition must announce itself rather than be noticed later. The guard is not pinned to an adapter version — a version pin rots as silently as the thing it guards.

**The announcement is evaluated independently of the refusal, never as its `else` branch.** On a map that is wholly zero or wholly positive the two are complementary and the shape makes no difference; the state that separates them is a map carrying **both** a non-finite hold and a real one — there the refusal fires on the broken reading while a balance is genuinely reporting a hold, and the transition still has to announce itself.

**Its stated limit, which no code shape removes.** The signal comes from a balance reporting a hold, and the measurement above says a resting 2:1 margin order holds nothing. So an account whose only resting order is a margin order produces `locked == 0` even after the upstream fix lands: the refusal keeps firing on a reading that has become truthful, and nothing announces it. The fixture's spot leg is what supplies the hold in practice. Recorded rather than engineered around — the alternative is inferring trustworthiness from the absence of a reading, which is the fail-open this whole decision exists to close.

### D4 — Verification is against the live fixture, by value, or it is not verification

The prior version of this defect was retracted on a control that read the same whether the defect was present or not. So:

- Orders: the A/B is **across code versions, not across cache states inside one run** — a post-fix flatten performs exactly one order read, so it has no cold arm of its own, and it prints a count and never a txid. So: the count read through the *deployed* pre-fix flatten (0), the count read through this branch's (2), and both fixture **txids by identity from `kraken-cli`**, the non-adapter witness, taken between the two arms. A count moving against an unchanged witness is the discriminator; either arm alone reads the same whether the defect is present or not. This is also what proves the cache mechanism live, which no reader of this repo can confirm from the compiled wheel.
- **Fills are NOT verified here, deliberately.** Nothing in `cli/` reads them — `request_fill_reports` and `fill_report` appear in no file under `cli/`, `tests/` or `infra/`, and `read_snapshot` is exactly orders, positions, balances — so no run this change makes could produce a fill row, and the committed record carries no fill identity to compare one against (the measured-basis table says what it does hold). D1's claim about `request_fill_reports` stands as a statement about the adapter; it gets no verification leg because this repo executes no fill read.
- Positions: assert the minted margin leg appears **by symbol and side**, against `kraken-cli`'s `positions` read — not against a row count, and not against the adapter's own second opinion.
- The guard: assert it refuses while orders rest, and that `locked > 0` trips D3's assertion.
- **A degenerate fixture proves nothing.** An empty account passing every check is the failure mode this spec exists to close.

### D5 — `request_position_status_reports` is verified HERE, against a real position minted for the purpose

It currently reads 0 with the cache warm — but the account holds no position, only an unfilled margin order, so 0 is the correct answer and carries **no information**. A path that returns the right answer for the wrong reason is exactly the degenerate control this spec exists to stop accepting.

**Flatten's entire close half depends on this path.** If positions are blind the way orders were, `--execute` would cancel the orders, see no positions, and report the account flat with a position still open — the self-confirming failure, on the half that moves money.

So the fixture grows a **filled margin leg** and the attended verification task of `docs/plans/00111-adapter-blind-reads.md` reads both paths before it ships: orders **and positions**. **This change does not ship on an assumption that the cache fix covers positions** — that assumption is untested, and an untested assumption about the close path is how the earlier version of this defect got retracted and then un-retracted. It is equally not tested offline: the test double models the silent drop on the ORDER read, which is the read that was measured, and deliberately leaves the position read ungated, because modelling a cache gate nobody has observed would manufacture the very agreement this decision exists to refuse.

**The verification must run THIS branch's code, and the host wrapper cannot.** `/usr/local/sbin/zcrypto-flatten` runs `{{ engine_image }}@{{ engine_image_digest }}` — the deployed pin, which predates this branch — so a wrapper run exercises flatten without the fix and returns the same empty list the defect returns, indistinguishable from a failed fix. The route is the one the 2026-08-26 pass already used and documented: run from the workstation worktree with the vaulted trade key in the environment, the workstation's public IP temporarily allowlisted on the `zcrypto-engine` key, and the allowlist closed again as a numbered step (spec `00039` decision 3's closure step). The dry run is read-only and shares the key with the running engine, which is the same accepted exposure `zcrypto-flatten`'s own dry-run banner names.

**Cost, stated**: one market-filled margin leg at `ordermin` — roughly EUR 5 of exposure plus ~EUR 0.04 taker fee, and Kraken rollover accruing every 4 h while it is open. The position is closed by the attended task's own `close` step, through the same committed script that minted it; it is not left open.

### D6 — The fixture is minted by a committed script, not by clicking

Click-driven order entry is error-prone and unrepeatable, and this fixture will be re-minted every time the account is flattened. So the mint is a committed script over `kraken-cli`, with:

- **`--validate` as the default and `--execute` opt-in** — the same safety inversion `zcrypto-flatten` uses, and `kraken order buy --validate` ("Validate only, do not submit") makes it a real end-to-end exercise against the live API rather than a simulation.
- **`--cl-ord-id` on every order**, so each fixture leg is identifiable by name rather than by matching txids after the fact. The owner could not tell the spot leg from the 2:1 margin leg in the venue's own list; that is a property of the fixture, not of the venue.
- **`mint` places exactly ONE leg** — the margin leg this decision prices below. The two hand-placed limits are not re-minted here: they already rest, they must survive, and a second executing leg is money nothing authorised. Any other submitted count is a defect, and the script states the number it will submit.
- **A `close` mode carrying the exact netting command**, `--validate` by default like `mint`. Closing the minted leg is the one live-money act with a rollover clock on it, and typing it by hand under that clock is how a netting sell becomes a fresh short. The order is `--reduce-only` so the venue itself refuses to open a position with it.
- **`-o json` throughout**, so verification parses rather than eyeballs.
- **A verify mode reading back through `kraken-cli`** — `positions`, `extended-balance`, `open-orders` — which is the **independent, non-adapter witness**. Every verification in D4 compares the adapter against this, never the adapter against itself.

**`kraken-cli` is a workstation development tool.** It is used for R&D and fixture management before RUNG 3 completes; it is **not available in CI, is never imported by `cli/`, and is never a runtime dependency of the engine.** The script lives beside `infra/scripts/kraken-order-semantics-probe.py` and carries that constraint in its own header.

### D7 — The upstream defects are reported, not patched around silently

Two upstream defects are in evidence: the silent row-drop on a cache miss, and `hold_trade` never being read. The second is owed as a PR to `nautechsystems/nautilus_trader` (the adapter's own margin branch already uses `from_total_and_free` correctly, so the precedent is in-file); whether it has been filed is the topic's to say, never this paragraph's. D1 and D2 stand regardless — upstream lands on its own timeline and RUNG 1 does not wait on it.

**Both are registered in `T0160`, not in this prose.** A deferral whose only home is a spec paragraph is untracked; `T0160` already enumerates the upstream commits that intersect this repo's read path, so it is where these two belong and where their trigger lives — the `hold_trade` report is the same event D3's assertion exists to detect.

### D8 — `px=0.00` on order reports is observed and out of scope

Both fixture orders come back with `price=0.00` where the venue shows 45.95. Irrelevant to a cancel-everything path; it would matter to anything that sizes or prices off a report. Recorded so the next reader does not rediscover it as new, and deliberately not chased here.

## Out of scope

- Any change to `flatten`'s write sequence, exit codes, or confirmation gate — spec `00106` owns those and none of them is implicated.
- The upstream PR itself (D7) — different repository, different conventions, tracked in `T0160`.
- `px=0.00` (D8).
