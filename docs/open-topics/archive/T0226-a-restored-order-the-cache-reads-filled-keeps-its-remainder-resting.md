---
status: resolved
---
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
- The trigger is the engine converge that ships the fix: the attended session needs the fix live and is the owner's to schedule once it is. Its check prints the preflight revision of each successful engine converge on `zcrypto` that contains the fix's commit, `4ba63057e`.

## Resolution

- The engine fix, `docs/specs/00161-restored-remainder-cancelled-design.md` and `docs/plans/00161-restored-remainder-cancelled.md`: the startup pass cancels at Kraken, by its txid, a restored order the ledger holds open that Kraken lists open while the Cache's copy reads closed, whatever the frame's shape, and the re-read pass then books a fill that raced the cancel. Proven on the loopback with the frame with and without `order_qty`, landing before the startup pass's cancel and inside it (`tests/test_cache_restart.py`). It ships on the engine image with T0229's and T0227's fixes, one converge, the fleet's concern.
- Spec 00120 D7's measurement, re-taken on a frame without `order_qty` (spec 00161's measured basis): the pass's cancel still bounds a frame inside it, booked twice on either shape; on a kept reducer the frame rewrites the copy instead, its remainder cancelled at a next start inside the row's two UTC days.
- The loopback's private-socket reconnect cell (spec 00161's measured basis): a reconnect between an order's placement and its frame without `order_qty` leaves the copy open, so only a restored copy is rewritten.
- Live since 2026-11-18: the engine converge onto `512ba1a02ea9`, built from `bc217e613`, rc 0 at 10:08:17Z, its `deploy-log.jsonl` row merged by #869 (`d81f623e0`).
- The attended session, 2026-11-18 12:06–12:11Z in the 12Z gap, on the owner's word "keep both as recommended. And let's do T0226 now": a key for it alone, IP-restricted and deleted after; the owner's USDC/EUR buy `OP4TXU-XOQBB-A3ILBB`, 5, a stop-loss-limit triggered on the last price at 0.9121 with its limit at 0.9132, triggered and filled at 0.9122 in one taker trade `TVKALX-45KED-EI27OI`; the market sell `OD33SV-ZZSPM-GRF3L4` at 0.9121, trade `TPU3YP-6LJ2I-V2GGE6`; the round trip 0.0187 EUR; `docs/reference/rung3/days.md` names it.
- `order_qty`: both `trade` frames carry none; only the orders' `pending_new` frames carry it, as Kraken's documented example has it. The capture was a triggered taker fill and a market fill, not a resting limit's part-fill; the fix holds on either shape (above), so nothing rests on the difference.
- The triggered fill, nautilus_trader #5315's case, replayed on the pinned wheel through `tests/kraken_loopback.py` and `tests/test_cache_restart.py`'s harness: a filled stop-loss-limit is not harmless at a start. Kraken's TradesHistory row for its fill names its type `stop limit`, which the adapter fails to parse, so each start within 720 minutes of the fill aborts at the mass status read; that one field rewritten, the start imports both orders `EXTERNAL` and `FILLED`, with one bounded-fill WARN and no position. While running, the live engine logged five nautilus ERROR lines on the order's frames at 12:07:45Z, under the `engine-nautilus` container, which pages nothing by `config.alloy`'s recorded design, and booked nothing. The restart step's item 3 now says so (`659649ecc`); both defects went to the `nautilus` peer for upstream (`.local/dispatch/2026-11-18-stop-limit-trade-row-nautilus.md`).
