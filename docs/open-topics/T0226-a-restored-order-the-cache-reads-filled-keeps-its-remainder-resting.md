---
status: open
ripe_when: 'a milestone: rung 3''s first attended week closes; check: `git log --oneline origin/develop --merges --grep=records/rung3-week-1` prints a line'
---

# A restored order the Cache reads filled keeps its remainder resting at Kraken

## Context — what

After a restart with an engine order resting, a part-fill's stream frame landing before the startup pass's cancel rewrites the order in the Cache to the filled quantity and `FILLED`, when the frame carries no `order_qty`. The pass then sends no cancel, no later start cancels it, and later fills on it are rejected with no event. Real `trade` frames probably carry no `order_qty`: Kraken's docs' one example has none and the real `canceled` frames have none, but no real `trade` frame has been captured. Both `2.0.0rc9.dev20261101` and `2.0.0rc9.dev20261106` read the same.

## Why this matters

Rung 3's post-only orders rest up to the 15-minute time box, so a crash inside it reaches this, with a fill in the seconds before the pass's cancel. The remainder rests with no time box and nothing managing it, and only Kraken's open-orders page shows it. The harm is bounded: sizing reads Kraken's book, so the next plan sees what filled. The owner's word of 2026-11-07, verbatim: "handle the unmanged remainder as recommended", which was the runbook's read for entry and this engine fix after the first attended week.

## Findings so far

- Staged on both wheels with `tests/test_cache_restart.py`'s harness: `.local/reads-archive/feat/engine-arm-2.0.0rc9.dev20261106/step3/resting-report.md`, the upstream path in `nautilus-retrace.md` beside it. A frame with `order_qty` double-counts instead, and a frame inside the cancel double-counts on either shape; neither moves sizing.
- `test_a_trade_frame_on_a_restored_open_order_is_booked_twice_by_the_library`, its racing sibling and spec 00120 D7's measurement rest on `tests/kraken_loopback.py`'s `exec_trade`, which carries `order_qty`.
- The read that covers it until then: `infra/runbooks/engine-procedures.md`, the rung-3 restart section's item 4.

## Suggested next steps

- Record a real `trade` frame at the next funded fill, with `kraken ws executions --snap-orders false --snap-trades false -o json` on a key with WebSocket access, to settle `order_qty`; a resting limit's part-fill is the exact case.
- Spec the fix: the startup pass compares Kraken's open rows from `read_venue_orders` with the Cache and cancels at the venue a ledgered row the Cache reads closed. Prove it on the real wheel with a docs-shaped frame, both orderings, and re-measure spec 00120 D7 on that frame.
