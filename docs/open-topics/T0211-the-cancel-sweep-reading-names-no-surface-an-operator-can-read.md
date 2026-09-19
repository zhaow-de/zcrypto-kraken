---
status: open
ripe_when: 'the attended engine start [[T0160]]''s cancel-sweep arm waits for is planned — the occasion that reading is taken on, since an operator following it is who finds it unrunnable; or `cli/engine/executor.py`''s startup adopt pass is next changed, a session already holding what the boot does and logs'
---

# T0160's cancel-sweep reading names no surface an operator can read, and predicts the wrong actor

## Context — what

[[T0160]]'s *What to run when ripe* tells the operator to look for a resting order's `client_order_id` in `cache.orders_open(venue=_VENUE)`, and describes the safe result as the order being present with "a trip cancels it". Two things are wrong with that as an instruction.

**The surface does not exist for an operator.** `orders_open` is a Nautilus Cache method the engine calls in-process; no `zcrypto` subcommand surfaces that list, and the engine is a container the operator reads logs from. The readable evidence is the boot's own `canceling adopted resting order` lines and the venue's own order list afterwards.

**The actor is wrong.** The sentence says a *trip* cancels the adopted order. The *startup adopt pass* cancels it first, at every gate level: the fixture is hand-placed, so no ledger row calls it a resting reducer, and that exemption is the only thing that leaves an adopted order resting. An operator waiting for a kill-switch trip to demonstrate the cancel is waiting for something that has already happened.

## Why this matters

The reading it describes is one-shot and expensive. It needs an attended engine start with a hand-placed order resting at the venue, on an account that only its owner can place orders against, and the boot consumes the fixture. An operator who reaches for a surface that does not exist loses that occasion and cannot retake it until the next converge restarts the engine, which is not schedulable at will.

## Findings so far

- **Three ways an order survives that boot, only one of which is the finding the reading is for.** A cancel that raises logs `cancel of adopted order … raised -- it may still rest at the venue`, so the pass saw it. A startup venue read that fails logs `venue orders could not be read at startup -- retrying on the next tick` and returns having adopted nothing; the pass does not latch, so a retry can still succeed and produce the reading. Only a survivor on a boot that logged neither is the blindness this measures.
- **Registered rather than repaired in passing.** Every replacement drafted on this branch contradicted either the trigger above it or itself: the paragraph needs one careful pass by someone holding the boot's behaviour, not another incremental edit.

## Suggested next steps

- **Rewrite the reading against surfaces an operator has.** Say which read is which, because their polarities are opposite — present is healthy in the log, gone is healthy at the venue — and confusing them inverts the verdict.
- **Replace "a trip cancels it"** with the startup adopt pass, which cancels a hand-placed order armed or not, and say the fixture is consumed either way, so the reading is one-shot per engine start.
