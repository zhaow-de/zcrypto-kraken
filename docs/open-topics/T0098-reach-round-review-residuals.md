---
status: open
ripe_when: the next touch of `cli/ohlc/reach.py` or `cli/engine/store.py` for sub-items 2 and 3 (both are refactors with no behavioural change, so they ride an iteration that is already in those files rather than earning their own). Sub-item 1 is ripe when a reach round — or any other `data rebuild` target — actually strands a partial sibling, which is now cheaply observable: the sibling exists with no `manifest.json`
---

# Reach-round review residuals: a stranded partial sibling, and duplicated seam logic

## Context — what

The pre-push review of the REST reach round ([[T0065]], `cli/ohlc/reach.py`) returned nine findings. Six were fixed in the same commit — REST call pacing, a manifest that folded detached content into the basket hash, missing per-series `sha256`, a factually wrong import comment, missing wiring tests, and dead test code. Three were deliberately **not** fixed there, because each would have widened the change beyond the component or touched code that must not move this week. They are registered here rather than left in a review transcript nobody re-reads.

## Why this matters

None of the three affects the data the round produces — the shipped set is correct and its continuity is verified. They are forward-looking: two are maintainability traps that get more expensive the longer two copies drift, and one is an operational papercut that will eventually cost someone a confusing manual cleanup.

## Findings so far

### 1. A mid-run failure strands a partial, unretriable sibling

`rebuild_sets` (`cli/data/rebuild.py`) cleans up a failed builder's output **only when the directory is still empty**. `reach_round` writes symbol-by-symbol and only writes `manifest.json` at the very end, so a failure at (say) fetch 7 of 30 leaves a non-empty sibling with no manifest — and because the sibling name is date-stamped, a same-day retry then trips the `sibling already exists` guard forever, requiring a manual `rm -rf`.

This is a **pre-existing** property of every `data rebuild` target, not something the reach round introduced, which is why it was not fixed inside the reach commit. But the reach round is the first target driven by many sequential network calls, so it is the first with a realistic chance of hitting it. The added REST pacing (3.0 s, the measured floor from T0053) materially reduces the most likely trigger.

**A missing `manifest.json` is a reliable partial-run signature** — every completed reach round writes one as its last act. That makes the condition cheap to detect, and is the natural basis for a fix: either clean up a manifest-less sibling on failure, or make the retry path recognise and replace one.

### 2. Seam-reconciliation logic is duplicated between the reach round and the engine store

`cli/ohlc/reach.py::_drop_in_progress` is functionally identical to `cli/engine/store.py::_drop_in_progress`, and `_merge_or_detach`'s join/overlap/mismatch/merge block mirrors `_reconcile`'s `allow_replace=False` path closely. `MIN_SEAM_OVERLAP = 6` is hardcoded to match `_SEED_MIN_OVERLAP` rather than shared — the reach module's own comment admits the coupling.

Both copies are correct today. The risk is that a future safety fix to one has no path to the other, and this is seam logic guarding an unbackfillable-adjacent dataset. The extraction is a pure refactor, so it should ride an iteration already working in those files — with the caveat in sub-item 3 about *when* `cli/engine/store.py` may be touched.

### 3. `PAIR_KEYS` sits in the engine store, so `cli/ohlc/` imports upward to reach it

The asset → Kraken REST pair-key mapping lives in `cli/engine/store.py` only because that was its first consumer. `cli/engine/store.py` already imports `cli.ohlc.*`, so `cli/ohlc/reach.py` importing it back runs against the dependency direction. Two consequences, both currently benign and both documented at the import site:

- Importing the **submodule** does not dodge the package — Python runs `cli.engine.__init__` first, so the concordance/cycle/journal chain loads regardless. (An earlier comment claimed the opposite; that was measured false and corrected.) It costs nothing in practice because `cli/__main__.py` already imports `cli.engine.command` unconditionally.
- **`cli/ohlc/__init__.py` must never import `cli.ohlc.reach`**, or the package re-enters itself half-initialised via `cli.engine.store` → `cli.ohlc.dataset`. That is a live trap for anyone tidying the package exports.

The fix is to relocate `PAIR_KEYS` into `cli/ohlc/` (its natural home — it is OHLC REST reference data) and have the engine store import it from there, keeping `cli.engine`'s existing re-export intact.

**Why it was not done in the reach commit:** `cli/engine/store.py` feeds the shadow engine, which is mid-Stage-6a-gate with the clock running, and the owner is away 2026-07-29 → 2026-08-20. A no-behaviour-change refactor of gate-path code days before an unattended stretch is the change-freeze class this project rules against. It is safe and small **after** the gate call.

## Suggested next steps

- Sub-item 1: decide between cleaning up a manifest-less sibling on builder failure and making the retry replace one. Prefer whichever keeps `rebuild_sets` honest for **all** targets, since the gap is shared.
- Sub-items 2 and 3 together: one small refactor iteration once the Stage-6a gate is called — relocate `PAIR_KEYS`, extract the shared seam helper, delete both duplicates, and drop the import-direction comment in `cli/ohlc/reach.py` that exists only to describe this problem.
