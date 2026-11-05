# The engine holds a quantity against Kraken's current ordermin

Branch `feat/00156-boundary-ordermin`, cut from `develop` 9844ecf4a on 2026-11-05, for topic T0224, on the owner's word of the same day, given before the exit report that is the topic's trigger had merged: "after the TLS fix's merge, please check if we can resolve T0224 earlier, I'd like to have it ready before rung-3 starts." The owner chose the source and the rollout's order in one line, of which the last clause answers two questions of the rung 2 exit report: "boundary's listing, hold the bulk rollout, Q2 and Q5 as recommended".

## The measured basis

- **The fault.** The 2026-10-30 ETH/EUR sell of 0.00109968 cleared the engine's 0.001 floor, the Cache instrument's `min_quantity`, and Kraken's 0.002 refused it as `volume minimum not met`; it ended `ambiguous` and halted its plan. On 2026-10-31 `zcrypto engine probe-plan --check` printed ETH 0.001, LTC 0.1 and XRP 1.65, the floors before the move, as the topic's findings record.
- **How floors move.** Reference-data sweep #4 (2026-10-31, the log in `docs/reference/kraken-snapshot-register.md`) found `ordermin` moved on eight of the twelve legs since #3 (2026-10-01), four raised and four lowered; `costmin` did not move.
- **The listing carries the venue's floor.** Read on 2026-11-05 on the pinned `nautilus-trader` 2.0.0rc9.dev20261101: `KrakenSpotHttpClient(api_key=None, api_secret=None).request_instruments()` answered 1824 rows, 1470 `CurrencyPair`s and 354 `TokenizedAsset`s, and each leg's `min_quantity` equalled public `AssetPairs`' `ordermin` on all twelve: ADA/EUR 20, AVAX/EUR 0.5, BTC/EUR 0.00006, DOGE/EUR 50 (Kraken's `XDG/EUR`), DOT/EUR 3.9, ETH/BTC 0.002, ETH/EUR 0.002, LINK/EUR 0.35, LTC/EUR 0.08, SOL/BTC 0.05, SOL/EUR 0.05, XRP/EUR 4. The engine's record `/mnt/zhao-crypto/engine-journal/2026-11-05/venue-12.json`, `state.instruments`, matched all twelve as well, its Cache having loaded at the last restart: no leg has drifted today, and nothing in the engine reads a floor between two starts.
- **The library refuses at the Cache's floor.** A SELL of 0.00109968 on the listing's ETH/EUR instrument, floor 0.002, submitted through the wheel's `BacktestEngine`, with the risk engine unconfigured as the engine's is (`cli/engine/node.py` names no risk engine config), came back `OrderDenied`, reason `QUANTITY_BELOW_MINIMUM: effective=0.00109968, min=0.002`. The same on a loopback `LiveNode` from `cli/engine/node.py::_node_builder`: the listing lowered from 0.06 to 0.03 with nothing refreshed, a SELL of 0.04 came back `OrderDenied`, `QUANTITY_BELOW_MINIMUM: effective=0.04000000, min=0.06`.
- **A start takes the venue's floor over the stored instrument.** Three processes of `tests/test_cache_restart.py`'s harness on one `valkey-server` store, the venue's ETH/EUR `ordermin` moved between them, read `venue_state_from_cache` at `on_start` and at the window's end: 0.002 and 0.002, then 0.001 and 0.001, then 0.005 and 0.005, with `trader-SHADOW-001:instruments:ETH/EUR.KRAKEN` in the store.
- **A running process can refresh it too, and the risk engine follows.** The wheel's Python `Cache` (`nautilus_trader/common/__init__.pyi`) offers `instrument()` and no instrument write, and `KrakenDataClientConfig` (`nautilus_trader/adapters/kraken/__init__.pyi`) has no instrument-refresh option, but `Strategy.request_instrument(instrument_id, client_id=ClientId("KRAKEN"))` writes its answer to the Cache. On that loopback `LiveNode`: the row moved to 0.03, the floor read 0.03000000 after the call and a SELL of 0.04 came back `OrderSubmitted`; the row moved to 0.30, the floor read 0.30000000 and a SELL of 0.10 came back `OrderDenied`. On real Kraken, public endpoints and no credentials, a strategy in a node requested all twelve legs: every answer inside 3.9 s, each leg's floor unchanged, no line at WARNING or above. No real floor moved in that read. The answer arrives after the call, so it is no synchronous read inside a draft.
- **What a lowered floor is worth.** The last sweep's lowered EUR legs, the gap between their two floors at the closes of the engine's cycle record for 2026-11-05 16Z: SOL/EUR 0.06 → 0.05 is 0.80 EUR, LINK/EUR 0.55 → 0.35 is 1.91 EUR, LTC/EUR 0.1 → 0.08 is 0.92 EUR.

## Operating model

- **Machines and processes.** One engine process, the one `zcrypto-engine` service of `infra/ansible/roles/engine/templates/compose.yaml.j2`, on `zcrypto`. The floors live in its memory alone: `ProbeExecutor._venue_book`, written by the executor and read by the executor and by `ShadowStrategy._snapshot_venue_state`, on the node's one actor thread. No file, lock or second writer is added. `zcrypto engine draft-plan` and `zcrypto engine probe-plan --check` are separate processes that read the boundary's venue record and hold no state of their own.
- **When a floor is read.** A book is read at the startup pass, at each re-read pass (a mint or a socket's return arms it), and, with `accumulation_enabled` on, at each boundary's draft. With the loop off a boundary reads no book, so the floors stand from the last pass; an operator's plan is then held against those. Before the first read of a process, the startup pass's own window, the Cache's connect-time floors stand alone.
- **What a restart does.** The floors are not persisted. At a start the connect's answer replaces the stored instrument (the measured basis), so a floor Kraken lowered reaches the Cache then, and the startup pass reads the listing again.
- **The venue record's freshness.** `on_alert_logic` runs the snapshot, then the cycle, and only then `on_boundary`, so a boundary's venue record carries the floors of the read before that boundary's own: with the loop on, one boundary old. The helpers can therefore print a floor up to one read behind the engine's; the engine's own check at submission reads the newest, and that check is the one that stops an order.

## D1 — the boundary's listing is the source

`read_venue_book` already calls `request_instruments()` on its own client at each read, using the answer only to resolve margin rows. It keeps each `INSTRUMENT_IDS` leg's `min_quantity` as `VenueBook.ordermin`, a dict keyed by symbol, last among the fields and empty by default, so a book built with no listing reads as no floors. The source is the owner's choice over public `AssetPairs`, one more venue call and a second failure path, and over committed floors under a drift guard, which keep today's failure: a move between two sweeps still gets through.

## D2 — the floor held is the higher of the Cache's and the listing's

`held_ordermin(cached, listed)` in `cli/engine/venuestate.py` is the one rule: the Cache's floor when the listing names none, else the larger of the two.

- **A raised floor holds from the next book read.** The engine's own check refuses or carries the quantity, and the order is never sent. This is the 2026-10-30 fault.
- **A lowered floor holds from the next engine start.** Holding the listing's lower figure at once would pass a quantity between the two floors to the library, whose risk engine denies it (the measured basis), so the same leg would end `rejected` at every boundary until a restart. Holding the Cache's until then leaves that remainder as dust, which is today's behaviour, and every image converge restarts the engine anyway.

The owner ruled on the lowered floor on 2026-11-05 with the refresh in view: "Wait for restart (Recommended)". The option not taken asks the library to reload a leg with `Strategy.request_instrument` when the listing's floor is under the Cache's: the lower floor would hold within one read and a failed reload would leave the higher one, at about ten more lines; it would replace an instrument mid-run on the live engine, unattended, only when Kraken lowers a floor, on a path no real moved floor can be read through at will, and what it would free was under 2 EUR per leg on the last sweep (the measured basis). Bypassing the risk engine was not offered: it takes every pre-trade check off a live path for the sake of dust.

The topic's second harm, "a lowered one leaves as dust a remainder Kraken would take", is therefore bounded by the next start, by the owner's choice: a known limit, not an open follow-up, and nothing further is planned for it.

## D3 — one overlay, every reader

`venue_state_from_cache(cache, *, clock, listed=None)` sets each leg's `InstrumentConstraints.ordermin` through `held_ordermin`. Every reader of a floor reads that state, so each follows without a change of its own: `size_order` through `_ActiveIntent.constraints`, `_classify_spot_close`, `_mixed_inventory_refusals` and `_draft_table`. The executor's two calls off a held book pass `self.listed_ordermin()`, and the boundary's call, which precedes the book's adoption, passes the book it just read. `ShadowStrategy._snapshot_venue_state` passes the executor's newest, so the venue record, and through it `draft-plan` and `probe-plan --check`, carry the floor the engine holds. `_is_flat_dust`, the one reader that takes the Cache's figure directly, goes through `held_ordermin` with the book in hand. The record's `ordermin` field keeps its name and type, so no reader of the format changes and no deploy order applies.

## D4 — a leg without a floor stands on the Cache's, loudly

A leg the listing leaves out, or lists with no positive `min_quantity`, is logged at WARNING per read, naming the symbol, and left out of `VenueBook.ordermin`, so that leg's Cache floor stands. A listing absent or empty already raises in `read_venue_book`, and at a boundary that ends `book-unread` with no draft; that path is unchanged.

## D5 — two cases hold the two premises

A `nautilus-trader` bump could break either premise with every other offline test still green. That the adapter's `min_quantity` is Kraken's `ordermin`: `tests/test_engine_node.py` gains one case behind `ZCRYPTO_LIVE_VENUE_TESTS`, comparing the floors `read_venue_book` would keep with public `AssetPairs`' `ordermin` on all twelve legs, which fails, never skips, when the flag is set and the venue is unreachable, as its neighbours do. That a start takes the venue's floor over the stored instrument, which D2's lowered half rests on: `tests/test_cache_restart.py` gains one case, two processes on one store with the venue's floor moved between them.

## D6 — the rollout rides the held bulk image

No converge of its own: this lands on `develop` and the engine takes it with the bulk image, in its inter-cycle gap, outside a Kraken window, as `.claude/rules/fleet-deploys.md` has it. After the engine's first start on it, the first venue record's `state.instruments` is read against public `AssetPairs` on the twelve legs, by value. A lowered floor since the Cache's load cannot show in that read, the start having just reloaded it, so the read proves the path and not a move.

## Out of scope

- `lot_step`, `tick_size` and `costmin`. The orders' lot and tick stay the Cache's; T0224 is the minimum alone, and `costmin` stays the committed constant under `tests/test_costmin_drift.py`.
- `zcrypto engine flatten`, which reads its own listing row (`cli/engine/flatten.py`) and places through a bare client, past the Cache.
- `cli/engine/feeders.py`, which reads a committed snapshot for research.
- A log line when a floor moves: an explicit drop. The venue record carries the held floor by value at each boundary, a leg's journal reason names the floor it was held against, and the monthly sweep compares `AssetPairs` with the register.
