---
status: open
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

## Suggested next steps

- **Rewrite the comment to the measured consequence** — a carried zero sends legs the sizing would have skipped — keeping the refusal itself untouched. It is prose, not behaviour: the `raise` is correct and stays.
- **Check the sibling prose in the same function while it is open**: `_required` and `_as_float`'s refusal reasons are cited in the same sentence, and only the zero-price consequence is known wrong. Read them against the bodies rather than assuming the error is confined.
- **Do not add a test for the comment.** What is wrong is a sentence; the behaviour it describes is already covered where the carried-zero case was driven. A guard here would pin prose, not code.
