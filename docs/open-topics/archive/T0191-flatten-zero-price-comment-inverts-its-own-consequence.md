---
status: resolved
---

# The zero-price refusal's comment inverts the consequence it exists to justify

## Context — what

`read_book_price` (`cli/engine/flatten.py:359-365`) refuses a top-of-book price of zero or less, and the comment above the `raise` explains why. Its explanation is backwards. It says a carried zero "would flow into `plan.prices` and make every notional read as nothing -- below every `costmin`, so `size_leg` lists every basket leg as dust and `judge_final`, one predicate at the same price, agrees: the account reported flat at exit 0 with the whole spot book still held." The failure it describes is a silent no-send.

Measured, the opposite happens. A carried zero yields `send=True ref=None est=None`, byte-identical to the refusal path, and the `DOT 0.001` dust case flips `send=False` to `send=True` under a carried zero. A zero makes the button send MORE, not less — the dust legs it would otherwise skip become legs it sends.

## Why this matters

This is the red button's own prose, on the refusal that guards it. A reader deciding whether the refusal is load-bearing — or whether it can be relaxed for a venue that legitimately reports zero — is told the failure mode is a silent no-send, and would weigh the trade against the wrong risk. The real one is unintended sends on legs the sizing would have skipped.

The tree also contradicts itself as of the `test_engine_flatten.py` docstring pass: the test file's corrected docstring now states the measured behaviour, and this comment states its inverse. Whichever a reader opens first is the one they believe.

## Findings so far

- The measurement is the flatten docstring branch's, driven rather than reasoned: a carried zero gives `send=True ref=None est=None`, indistinguishable from the refusal path, and the `DOT 0.001` case flips `send=False` to `send=True`.
- Two independent readers reached it from different directions — the scoped read of the fix commit, which drove the carried-zero case, and the whole-branch read, which found the comment only because it was holding the implementation while reading the corrected test docstring.
- **Not folded into the branch that found it.** `cli/engine/flatten.py` is inside `replay_fingerprint`'s import closure, and that branch is a test-docstring pass whose whole property is that it changes no file the fingerprint reads; `branch-workflow.md` also puts one component in one PR. This is ordinary queued work needing only its own branch, not a deferral on a precondition — `gate_cache.load_cache` rejects the cache once on a `replay_fp` mismatch and re-caches, so the cost is a single cold replay on the next gate run however many closure files changed, and it is shared with any other `cli/` change landing in the same window.

## Resolution

**Resolved by PR #478** (`docs/t0191-flatten-zero-price-comment`, two commits), which rewrote the comment and left the code alone.

- **The comment states what a carried zero does.** `_tick_floored` maps `0.0` to `None` before any notional exists, so `_size` passes `costmin=0.0` and the notional floor is DISABLED rather than tripped. A leg the notional floor listed `dust_below_venue_minimum` at a real price is then sized on `ordermin` alone and SENT; a balance under `ordermin` is dust at a real price and dust unpriced, so the send does not flip for it. Both arms are pinned already: `tests/test_engine_flatten.py:544` and `:562-563`.
- **The refusal's real justification replaced the phantom one.** Refusing changes no send — the caller catches `FlattenUnreachable`, logs at ERROR and sizes the leg on the quantity floor alone, which is byte-identical to the carried-zero path. What it buys is a named, logged unreachable in place of a silently unpriced leg. That is what a reader weighing whether the refusal can be relaxed now weighs.
- **The sibling prose was read against the bodies, and one was also wrong.** `_as_float` was described as rejecting "only the non-finite"; it rejects a non-number first, since `float(value)` raises before the finiteness test. Corrected in the same sentence. `_required`'s "rejects only `None`" is accurate as written and was left.
- **`_tick_floored`'s docstring is NOT swept, and that is a decision rather than an omission.** It makes the same notional-cascade claim, but about its OWN counterfactual return — "left at 0.0 every notional reads as nothing" — an antecedent it controls, so the claim holds: `size_order(0.001, 0.0, ordermin=0.0001, costmin=0.45, ...)` is `BelowMinimum('notional 0.0 ... is below costmin 0.45')`. `read_book_price` had inherited the sentence into a place where the antecedent is false. The sentence was true where it was written and false where it was copied. The Fable read adds the bound worth keeping: that docstring's "the balance is judged dust" holds for `COSTMIN` pairs only — measured dust on DOT/EUR and ETH/BTC, sent on a pair carrying no committed costmin, where `classify_balance` judges on `ordermin` alone (`tests/test_engine_flatten.py:557`).
- **No test was added**, as this topic directed: what was wrong was a sentence, and the behaviour is covered at `tests/test_engine_flatten.py:810`. The `raise` is untouched.

The killed sentence survives in two places, both deliberately: `infra/scripts/prose-tripwire-baseline.txt`, where it is a row's identity key rather than prose, and `docs/plans/00106-engine-flatten.md`, a point-in-time record.
