---
status: open
ripe_when: 'the attended engine start [[T0160]]s cancel-sweep arm waits for is planned — the same occasion that reading is taken on, since an operator following it is who finds it unrunnable; or `cli/engine/executor.py`s startup adopt pass is next changed, a session already holding what the boot does and logs'
---

# T0160's cancel-sweep reading names no surface an operator can read, and predicts the wrong actor

## Context — what

[[T0160]]'s *What to run when ripe* tells the operator to look for a resting order's `client_order_id` in `cache.orders_open(venue=_VENUE)`, and describes the safe result as the order being present with "a trip cancels it". Two things are wrong with that as an instruction, and both were found by reads on the branch that shipped [[T0210]] (PR #566) rather than by anyone running it.

**The surface does not exist for an operator.** `orders_open` appears only inside `cli/engine/executor.py`, on the in-process Nautilus Cache. No `zcrypto` subcommand surfaces that list, and the engine is a container the operator reads logs from. The readable evidence is the boot's own `canceling adopted resting order` lines and the venue's own order list afterwards.

**The actor is wrong.** The sentence says a *trip* cancels the adopted order. At `GateLevel.NONE` — what a disarmed engine evaluates to, and what every converge leaves behind — the *startup adopt pass* already cancels everything it adopted, ledgered reducers included, before any trip. An operator waiting for a kill-switch trip to demonstrate the cancel is waiting for something that has already happened.

## Why this matters

The reading it describes is one-shot and expensive. It needs an attended engine start with a hand-placed order resting at the venue, on an account that only its owner can place orders against, and the boot consumes the fixture. An operator who reaches for a surface that does not exist loses that occasion and cannot retake it until the next converge restarts the engine, which is not schedulable at will.

It also reads as settled. The paragraph is specific and confident, which is exactly the shape that stops a reader checking, and nothing mechanical catches a documented command that names no real surface.

## Findings so far

- **The surface claim is measured.** `grep -rn "orders_open" cli/` returns hits only in `cli/engine/executor.py` — the adopt pass and the kill switch's cancel sweep. No command module reads it, so nothing an operator can run prints that list.
- **The actor claim is measured.** `cli/engine/executor.py` sets `kill_latched` true exactly when the gate evaluates to `GateLevel.NONE`, and the reducer exemption carries `and not kill_latched`; the docstring above states that at level NONE the pass cancels everything, ledgered reducers included. A disarmed boot therefore cancels without any trip.
- **Three ways an order survives that boot, only one of which is the finding the reading is for.** A cancel that raises logs `cancel of adopted order … raised -- it may still rest at the venue`, so the pass saw it. A startup venue read that fails logs `venue orders could not be read at startup -- retrying on the next tick` and returns having adopted nothing; the pass does not latch, so a retry can still succeed and produce the reading. Only a survivor on a boot that logged neither is the blindness this measures.
- **A correct replacement was drafted four times on PR #566 and found wrong four times**, each version contradicting either the trigger above it or itself. That is why this is registered rather than fixed in passing: the paragraph needs one careful pass by someone holding the boot's behaviour, not another incremental edit.

## Suggested next steps

- **Rewrite the reading against surfaces an operator has**: the boot's `canceling adopted resting order` lines for how many orders the pass saw, and the venue's own order list for which legs survived. Say which read is which, because their polarities are opposite — present is healthy in the log, gone is healthy at the venue — and confusing them inverts the verdict.
- **State the three survival causes and how to tell them apart**, using the two CRITICAL lines above as the discriminators rather than the absence of evidence.
- **Replace "a trip cancels it"** with the disarmed startup pass, and say that the fixture is consumed by the boot either way, so the reading is one-shot per engine start.
- **Do it on an occasion that can check it.** The cheapest verification is the attended start itself: whoever takes that window reads the paragraph as written, and whatever they cannot follow is the defect this topic names.
