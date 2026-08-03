---
status: open
ripe_when: the forward guard is ripe NOW and independent of the past gap — it prevents the next occurrence and needs nothing from this one. The acceptance is due before the go/no-go, which is the decision that inherits an adoption criterion nobody can re-examine
---

# The deployable's ADOPT criterion rests on a trial nobody can rebuild

## Context — what

Registry record **44** is the deployable. Its registered verdict is not "beats the benchmark" — it is **ADOPT *vs incumbent trial 43***, recorded in the row itself as "1.5609 ≥ 1.5366". That comparison is the criterion the live book's selection actually rests on.

Trial 43 cannot be rebuilt. Discovered 2026-08-03 while working [[T0090]], which had registered the re-read of that ordering as a *"cheap, autonomous"* next step:

- `git log --all -S"adaptive" -- cli/` returns **nothing** — the sleeve-level adaptive weighting was never committed, on any branch.
- Both trials' `run_ref` name **scratchpad** scripts: trial 43 → `iter-080 trial43/crossfreq_run.py + crossfreq_stage2.py + stage1b_verify.py (scratchpad)`, trial 44 → `iter-081 trial43/trial44_run.py + trial44_write.py (scratchpad)`. Scratchpads are session-scoped; these are gone.
- `_inverse_vol_weights` survives, but only for **asset-basket** weighting *inside* a sleeve (the B basket, A1, A2, the legacy builder). It was never wired to **sleeve-level** weights, which is what trial 43 did — its distinguishing metrics are `weight_warmup_bars = 180` and `weight_zero_vol_fallback_bars = 10638`.

The asymmetry is the whole point: **trial 44 IS reproducible from committed code** — the committed builder reproduces its 1.5609 exactly, verified repeatedly (the frozen-figure regression, [[T0124]]'s conditional work, and T0090's cost re-quote all reproduce the registered anchors). Trial 43 is not. So the *object* is reproducible while the *criterion that selected it* is not.

## Why this matters

**Any question that reaches back through the ADOPT comparison is permanently unanswerable.** Not merely expensive — unanswerable, because the instrument does not exist and cannot be recovered. The concrete one already blocked: T0090 measured that the record's cost basis moves ±30–40 % on the maker-vs-taker decision, and the registry row itself discloses that at ×2.0 the 43-vs-44 ordering **reverses** (1.2106 vs 1.2400). Nobody can check where in the maker-taker range that reversal begins, because half the comparison is gone.

**It is the [[T0065]] failure class, arrived at the worst possible place.** T0065's reproducibility round registered that "record 1 is not reproducible from committed code + manifest alone". That was a research record. This is the **deployable** — the one that takes real capital — and the specific thing that is unreproducible is its selection criterion.

**Reconstruction is a trap, not a remedy.** Rebuilding trial 43 from its registry variant string (`P1-crossfreq-B3vtdyn+A1lfw012+A2ens4h-ivol180-cap-govD`) would produce a plausible number that cannot be validated against anything — the registered figures are the only reference, so a reconstruction that reproduces them proves only that it was tuned until it did, and one that does not is indistinguishable from a faithful rebuild of a differently-behaving original. This project has twice been steered wrong by plausible numbers from unvalidated instruments; a reconstruction here would be a third opportunity, dressed as diligence.

## Findings so far

- The gap is **structural, not clerical**: the registry's `run_ref` field faithfully recorded where the code was. Nothing lied — the convention simply permitted a scratchpad path, and a scratchpad path is not a provenance record.
- The registry's `spec_hash` is *identical* for trials 43 and 44 (`a25d7102…`), because the spec did not change — only the weighting rule did, and that lived in the uncommitted runner. So the hash chain does not detect this either.
- Everything downstream of record 44 that has been re-derived since has reproduced exactly, so there is no evidence of a second, hidden discrepancy — the gap is bounded to the 43-vs-44 comparison.

## Suggested next steps

- **(autonomous — ripe now, independent of the past gap)** Make the next occurrence impossible: a registry entry whose `run_ref` names an uncommitted path should fail a check rather than be recorded. The `run_ref` should resolve to a committed revision plus a path that exists at it. Small, mechanical, and it is the only part of this topic that can actually be fixed.
- **(autonomous)** Record in the trial registry's own documentation which registered records are reproducible from committed code and which are not, so a future reader learns the boundary from the artifact rather than by re-discovering it mid-investigation as happened here.
- **(decision — before the go/no-go, and it must be explicit)** Accept that record 44's adoption criterion cannot be re-examined. The go/no-go already inherits [[T0064]]'s out-of-time-evidence ruling; this is a second inherited limitation of the same kind, and it should be accepted **knowingly** rather than by nobody noticing. The honest framing for that decision: record 44's *own* figures are reproducible and have survived every re-derivation; what is unavailable is the counterfactual that it was chosen against.
- **(explicitly NOT a next step, recorded so it is not proposed later)** Reconstructing trial 43. See *Why this matters* — an unvalidatable rebuild is worse than an acknowledged gap, because it would restore false confidence in a comparison nobody can check.
