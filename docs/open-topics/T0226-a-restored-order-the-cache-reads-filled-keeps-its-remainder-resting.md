---
status: partial
ripe_when: 'an activity: the owner''s attended session on a key the owner mints, in an inter-cycle gap the owner picks, that records a real Kraken `trade` frame and takes nautilus_trader #5315''s triggered fill, its entry in `docs/reference/rung3/days.md`; check: `grep -c -i "triggered fill" docs/reference/rung3/days.md` prints at least 1'
---

# A restored order the Cache reads filled keeps its remainder resting at Kraken

## Context — what

After a restart with an engine order resting, a part-fill's stream frame landing before the startup pass's cancel rewrites the order in the Cache to the filled quantity and `FILLED`, when the frame carries no `order_qty`. The pass then sends no cancel, no later start cancels it, and later fills on it are rejected with no event. Real `trade` frames probably carry no `order_qty`: Kraken's docs' one example has none and the real `canceled` frames have none, but no real `trade` frame has been captured. Both `2.0.0rc9.dev20261101` and `2.0.0rc9.dev20261106` read the same.

## Why this matters

Rung 3's post-only orders rest up to the 15-minute time box, so a crash inside it reaches this, with a fill in the seconds before the pass's cancel. The remainder rests with no time box, and only Kraken's open-orders page shows it. The harm is bounded: sizing reads Kraken's book, and the open row carries that leg. The owner's word of 2026-11-07, verbatim: "handle the unmanged remainder as recommended", which was the runbook's read for entry and this engine fix after the first attended week.

## Findings so far

- Staged on both wheels with `tests/test_cache_restart.py`'s harness: `.local/reads-archive/feat/engine-arm-2.0.0rc9.dev20261106/step3/resting-report.md`, the upstream path in `nautilus-retrace.md` beside it. A frame with `order_qty` double-counts instead, and a frame inside the cancel double-counts on either shape; neither moves sizing.
- `test_a_trade_frame_on_a_restored_open_order_is_booked_twice_by_the_library` rests on `tests/kraken_loopback.py`'s `exec_trade` with `order_qty`; its reading without `order_qty` is spec 00161's measured basis, `kept-docs`.
- The read that covers it until then: `infra/runbooks/engine-procedures.md`, the rung-3 restart section's item 4.
- The triggered fill for nautilus_trader #5315's capture was dropped from rung 3's run-up on the owner's word of 2026-11-08, verbatim: "ok, drop it, but please ensure it won't be forgotten later". The rung-3 restart section's item 3 calls an owner's closed conditional order harmless at a start on cancelled and hand-built rows alone; a filled one is unread on `2.0.0rc9.dev20261106`.

## Done so far

- The engine fix, `docs/specs/00161-restored-remainder-cancelled-design.md` and `docs/plans/00161-restored-remainder-cancelled.md`: the startup pass cancels at Kraken, by its txid, a restored order the ledger holds open that Kraken lists open while the Cache's copy reads closed, whatever the frame's shape, and the re-read pass then books a fill that raced the cancel. Proven on the loopback with the frame with and without `order_qty`, landing before the startup pass's cancel and inside it (`tests/test_cache_restart.py`). It ships on the engine image with T0229's and T0227's fixes, one converge, the fleet's concern.
- Spec 00120 D7's measurement, re-taken on a frame without `order_qty` (spec 00161's measured basis): the pass's cancel still bounds a frame inside it, booked twice on either shape; on a kept reducer the frame rewrites the copy instead, its remainder cancelled at a next start inside the row's two UTC days.

## Suggested next steps

- Both reads below are one attended session, on the owner's ruling of 2026-11-17. Record a real `trade` frame at the session's fill, with `kraken ws executions --snap-orders false --snap-trades false -o json` on a key with WebSocket access, to settle `order_qty`; a resting limit's part-fill is the exact case.
- Take the triggered fill in an inter-cycle gap after week 1, whose drills and `T0216`'s seven-day read count external events. On the workstation, a new Kraken API key for it alone: create and cancel orders, query open and closed orders and trades, WebSocket; IP-restricted to the workstation; deleted after. It lives in the capture process's environment only, with `KRAKEN_SPOT_API_KEY` and `KRAKEN_SPOT_API_SECRET` unset. Read Kraken's maintenance feed whole first. Place one USDC/EUR buy, minimum size, no `leverage`: a stop-loss-limit whose trigger is the last price and whose limit crosses the ask, recorded on its own executions subscription with snapshots off. Then read QueryOrders, ClosedOrders and TradesHistory, sell the USDC back in the same gap so the equity series sees only the round trip's cost, and read `kraken open-orders -o json` empty. Before the engine next starts, replay the filled rows through the pinned wheel's startup import and `read_venue_orders` at 127.0.0.1, and record the txids in `docs/reference/rung3/days.md` under an entry that names the triggered fill. Its frames settle `order_qty` above, and its filled row tests item 3's "harmless".
- Apart from that session, a loopback reading: whether a private-socket reconnect between an order's placement and its `trade` frame leaves the adapter without the order's quantity, as a restart does — a cell beside the reads archive's `test_live_control` (`.local/reads-archive/feat/engine-arm-2.0.0rc9.dev20261106/step3/resting/test_rest.py`) that drops and restores the execution socket between the acknowledgement and a frame without `order_qty`. A copy rewritten there is one the running process placed, which spec 00161's startup pass never reaches.
