---
status: partial
ripe_when: before the go/no-go — that decision inherits an adoption criterion nobody can re-examine, and it must be accepted knowingly rather than by nobody noticing. The forward guard is DONE; what remains is a ruling, not work
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

## Done so far

- **The forward guard is BUILT (2026-08-03, commit `dbe27e0b`) — the only part of this topic that could be fixed.** It is two layers, and the split is deliberate:
  - **Append time** (`cli/registry/record.py::validate_caller_fields`, which `TrialRegistry.append` calls *before* opening the file): `run_ref` is now **required** — a `None` run_ref is strictly worse than a scratchpad one — and must name at least one repo-relative path that **exists**. A `scratchpad` marker raises its own distinct error, because it is the self-declared form of the defect and deserves a precise diagnosis rather than a generic "no path resolved". Absolute paths and `..` escapes are rejected: provenance means a path *inside* the repo. No git and no subprocess here, since this runs on every append.
  - **Repo level** (`tests/test_trial_registry_provenance.py`, where git is guaranteed): every record's `run_ref` must name a **git-tracked** path — the check that actually means "committed".
- **The legacy set is frozen, and the exemption is asserted in BOTH directions.** Trials **33–46** (14 ids, contiguous) are exempt because the registry is append-only and hash-chained, so those records can never be repaired. The test asserts that no record *outside* the set fails **and** that every member genuinely fails today — so the pin cannot quietly decorate a pass and absorb a regression behind it. Widening the frozenset makes a test fail rather than silently pass.
- **The scope is wider than this topic first stated, and the measurement is the finding.** Of 46 records: **14 name scratchpads (33–46, every trial from 33 onward)**, and the other 32 name a `docs/research/*.md` **write-up** rather than the code that produced the run. **Zero records have ever named a committed `.py` runner** — the convention never required one. So this was never about trial 43 specifically; trial 43 is where it first cost something.
- **A trap found in review and closed before it could fire.** The two layers resolved paths differently — the filesystem normalizes `./cli/x.py`, `git ls-files` does not — so a record naming a genuinely committed file in a non-canonical spelling would have passed the append guard and then failed the provenance test **forever**, with no remedy, because an append-only record cannot be edited. Extraction now canonicalizes and a test pins that both layers accept every spelling of the same path.
- **The stored-record path stays lenient on purpose**, and the reason is stronger than "old records must still load": `append` re-validates every stored record under lock, so a strict load path would have bricked **all future appends** to the live registry, not merely reads. Provenance over history is asserted by the repo-level test instead, which operates on the file rather than the API — so even a hand-appended record is caught.

## Suggested next steps

- **(autonomous)** Record in the trial registry's own documentation which registered records are reproducible from committed code and which are not, so a future reader learns the boundary from the artifact rather than by re-discovering it mid-investigation as happened here. The boundary is now measured and pinned in the provenance test, so this is transcription rather than research.
- **(decision — before the go/no-go, and it must be explicit)** Accept that record 44's adoption criterion cannot be re-examined. The go/no-go already inherits [[T0064]]'s out-of-time-evidence ruling; this is a second inherited limitation of the same kind, and it should be accepted **knowingly** rather than by nobody noticing. The honest framing for that decision: record 44's *own* figures are reproducible and have survived every re-derivation; what is unavailable is the counterfactual that it was chosen against.
- **(explicitly NOT a next step, recorded so it is not proposed later)** Reconstructing trial 43. See *Why this matters* — an unvalidatable rebuild is worse than an acknowledged gap, because it would restore false confidence in a comparison nobody can check.
