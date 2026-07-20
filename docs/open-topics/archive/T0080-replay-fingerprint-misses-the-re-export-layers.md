---
status: resolved
---

# `replay_fingerprint` misses the re-export layers the fast verdict path binds through

## Context — what

`_REPLAY_CODE_PATHS` (`cli/engine/gate_cache.py`) hand-enumerates the modules whose source bytes are digested into `replay_fingerprint`. Spec `00060` D3 describes that list as *"the modules that determine a replay's result"*. Spec `00064` D9 added `cli/engine/command.py` and `cli/ohlc/dataset.py`, which the invariant claimed but never covered.

**The invariant still does not hold.** The fast verdict path binds several of its names through **package `__init__.py` re-export layers that are not hashed**:

- `cli/portfolio/__init__.py` — `cli/engine/concordance.py:24` imports `build_crossfreq_system_fast` *from `cli.portfolio`*, i.e. through this file, not from the module directly.
- `cli/risk/__init__.py` — binds `apply_position_caps`, called on the fast route at `crossfreq_system.py:635`.
- `cli/engine/errors.py` — defines `EngineJournalError`, the class `_replay_one` keys its verdict classification on.

## Why this matters

It is the same shape as the hole D9 closed, and it is **proven, not theoretical**. In an isolated mirror of the post-D9 tree, editing only `cli/portfolio/__init__.py` to rebind the fast builder to the verified one:

```
build_crossfreq_system_fast = build_crossfreq_system
```

makes `replay_cycle`'s `path == "fast"` branch run the verified daily-oracle builder for **every** replay — a different computation and a different verdict — while:

```
BEFORE  fast-builder bound to: build_crossfreq_system_fast
        replay_fingerprint  : cc08f1e0ddfbfadc46aad5ffa1f4986c53643cc446340b552d359ee0c985cd1b
AFTER   fast-builder bound to: build_crossfreq_system
        replay_fingerprint  : cc08f1e0ddfbfadc46aad5ffa1f4986c53643cc446340b552d359ee0c985cd1b
        tests               : 31 passed
```

**Byte-identical.** A stale cached PASS is served against changed verdict code, on the artifact authorising real-money trading, with the whole suite green. Same exposure via `cli/risk/__init__.py`.

**No live defect** — no such rebinding exists today. As with the 19 findings in [[T0075]], the code is correct and the guarantee is unenforced.

## Findings so far

- Discovered 2026-07-20 by the adversarial correctness lens verifying D9 (spec `00064`), which was told to refute rather than confirm the change. It computed the static transitive `cli.*` import closure of the replay path and diffed it against the hashed tuple.
- Correctly ruled **out** of scope by that same analysis, with reasons: `cli/config.py` (replay runs on the builder's default `CrossfreqSystemConfig` — the journal carries no config), and `cli/features/*` / `cli/backtest/*` (the fast helpers re-implement locally; `a1.py`'s `_asset_returns` / `_inverse_vol_weights` are pure).
- D9 itself was **not** wrong, only incomplete: the fingerprint now does respond to a `_snapshot_reader` `close`→`open` edit (`cc08f1e0…` → `b88361b5…`) where pre-D9 it was byte-identical.

**The structural point, which outlives the specific files.** Every fix so far has enumerated one more module after someone noticed it was missing — the four originals, the six added at review, then these two. Hand-enumeration cannot establish "the modules that determine a replay's result"; it can only ever record the ones somebody thought of. That is why the same class of hole has now been found three separate times in this list. See [[T0075]] for the same fix-the-instance pattern one level down.

## Resolution

**Resolved 2026-07-20** by spec `00065`, same PR that opened this topic. The owner ruled **option 2** — hash the transitive `cli.*` import closure — and it is implemented (`fe16327`, `4e212b6`, `bb72901`).

Measured before designing, because the obvious objection was cost: adding `command.py` as a root costs 8 more modules, not the whole CLI; the walk is ~59 ms against a 55–627 s run, 0.1% of the cheapest case. The same measurement showed the hand-list covered 12 of 61 executing modules (~20%), so the three previous rounds of "add one more module" were converging on nothing.

**Adversarial verification found the first implementation shipped the same hole one level up.** `_resolve_module` mapped a dotted name to its leaf file only, but importing `cli.engine.command` *executes* `cli/__init__.py` and `cli/engine/__init__.py` first. Seven modules ran on every replay unhashed — the four ancestor `__init__.py` files plus the three `cli/ohlc` submodules that became traversable only once `cli/ohlc/__init__.py` was covered, exploitable identically: rebinding `build_crossfreq_system_fast` in `cli/engine/__init__.py` changed every verdict at a **byte-identical** fingerprint with all 64 tests green. Fixed in `bb72901`; ancestors are now resolved explicitly (spec `00065` D10).

**The durable outcome is not the closure — it is the test.** `test_closure_covers_every_module_the_replay_roots_actually_execute` (D11) imports the roots in a clean subprocess, reads `sys.modules`, and asserts the closure is a superset of what actually ran. It enumerates nothing, so it cannot go stale, and it **failed on the first implementation**, which is what makes it the right pin. Measured after the fix: **61 covered, 60 executed, 0 executed-but-uncovered**, 1 harmless over-inclusion.

Spec `00060` D3 was amended at its root (`8a77014`): the wording was the defect as much as the list, and it now points at the superset test with the instruction that if the two disagree, believe the test.

## Suggested next steps

- **(Decide first — this is the whole topic)** Choose between two shapes, then implement:
  1. **Keep enumerating** — add `cli/portfolio/__init__.py`, `cli/risk/__init__.py`, `cli/engine/errors.py`. Three lines, closes the proven holes, near-zero invalidation cost (these files are tiny and change rarely). Does **not** make D3's invariant true, and the next unlisted module repeats this topic a fourth time.
  2. **Hash the transitive import closure** — walk `cli.*` imports from the replay entry points at fingerprint time and digest every reachable module. Makes the invariant *structurally* true rather than aspirationally true, so it cannot silently drift. Costs an import-graph walk per fingerprint (measure it; the current twelve-file read is ~0.3 ms) and needs a deterministic ordering plus a decision on how to treat third-party modules (probably excluded — `numpy`'s version is already digested separately per T0074).

  Recommended: **2**, with **1** as an immediate stopgap if the closure walk is deferred — the proven holes should not stay open while the better design is built.
- **(Either way)** Pin whichever is chosen against the exploit above: rebinding the fast builder in `cli/portfolio/__init__.py` must change `replay_fingerprint`. That test is the guarantee; the module list is just today's implementation of it.
- **(Either way)** Correct spec `00060` D3's wording, or the next reader inherits the same false invariant that produced all three rounds of this. Say what the list actually covers, or make it cover what it says.
- **(Cheap, do it with the change)** If option 1: the `_REPLAY_CODE_PATHS` comment block already states the invariant does not hold and names this topic — update it in the same commit so the code and the topic never disagree.
