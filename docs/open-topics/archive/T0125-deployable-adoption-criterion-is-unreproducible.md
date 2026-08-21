---
status: resolved
---

# The deployable's ADOPT criterion rests on a trial nobody can rebuild

## Context — what

Registry record **44** is the deployable. Its registered verdict is not "beats the benchmark" — it is **ADOPT *vs incumbent trial 43***, recorded in the row itself as "1.5609 ≥ 1.5366". That comparison is the criterion the live book's selection actually rests on.

Trial 43 could not be rebuilt from anything in version control — and on 2026-08-21 its original runners were recovered from a session transcript and verified ([[T0148]]); the paragraphs below are the 2026-08-03 finding as it stood, correct about git and the filesystem, wrong about the transcripts nobody had checked. Discovered 2026-08-03 while working [[T0090]], which had registered the re-read of that ordering as a *"cheap, autonomous"* next step:

- `git log --all -S"adaptive" -- cli/` returns **nothing** — the sleeve-level adaptive weighting was never committed, on any branch.
- Both trials' `run_ref` name **scratchpad** scripts: trial 43 → `iter-080 trial43/crossfreq_run.py + crossfreq_stage2.py + stage1b_verify.py (scratchpad)`, trial 44 → `iter-081 trial43/trial44_run.py + trial44_write.py (scratchpad)`. Scratchpads are session-scoped; these are gone.
- `_inverse_vol_weights` survives, but only for **asset-basket** weighting *inside* a sleeve (the B basket, A1, A2, the legacy builder). It was never wired to **sleeve-level** weights, which is what trial 43 did — its distinguishing metrics are `weight_warmup_bars = 180` and `weight_zero_vol_fallback_bars = 10638`.

The asymmetry is the whole point: **trial 44 IS reproducible from committed code** — the committed builder reproduces its 1.5609 exactly, verified repeatedly (the frozen-figure regression, [[T0124]]'s conditional work, and T0090's cost re-quote all reproduce the registered anchors). Trial 43 is not. So the *object* is reproducible while the *criterion that selected it* is not.

## Why this matters

**Any question that reaches back through the ADOPT comparison was, as ruled here, unanswerable — the instrument did not exist anywhere consulted.** (It was later recovered from a session transcript and behaviourally verified on two machines; [[T0148]] owns that recovery and the re-opened measurement. The re-grounding below neither anticipated nor depends on it.) The concrete one already blocked: T0090 measured that the record's cost basis moves ±30–40 % on the maker-vs-taker decision, and the registry row itself discloses that at ×2.0 the 43-vs-44 ordering **reverses** (1.2106 vs 1.2400). Nobody can check where in the maker-taker range that reversal begins, because half the comparison is gone.

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

## Resolution

**Ruled 2026-08-03 (owner): RE-GROUND the go/no-go on the benchmark-relative basis, and re-derive the remaining legs so the whole basis is measured rather than registry-asserted.** Both were done the same day.

**The re-grounding.** Record 44's registered verdict is ADOPT *vs incumbent trial 43*, and at ruling time that comparison was gone from everywhere anyone had looked (it was later recovered — [[T0148]] — which changes nothing about this re-grounding). But it was never the only thing holding the record up: record 44 also carries **benchmark-relative** legs, and those are reproducible. §12 now states that the gate rests on them. What the missing incumbent removes is the answer to *why this candidate rather than that one*; what it does not touch is *whether this candidate clears the bar* — and the second is what the gate reads.

**The whole kill bar is now MEASURED, not asserted** — re-derived end to end from committed code, with the instrument validated before any leg counted:

| leg | re-derived | registered |
| --- | --- | --- |
| `ann_sharpe_noc` full / decisive | 1.560907676587497 / 1.5583341567194398 | 1.5609 / 1.5583 |
| `bench4h_sharpe` full / decisive | 1.2128451567638199 / 1.2446890489958136 | 1.2128 / 1.2447 |
| `spa_p_full` / `spa_p_decisive` | 0.001999000499750125 / 0.004497751124437781 | **bit-identical** |
| the five `spa_grid_*` cells | all five | **bit-identical** |
| `var_trials_4h` | 1.3058096692086857e-05 | **bit-identical** |
| `per_period_sharpe_4h` | 0.03335455562889141 | **bit-identical** |
| `dsr` | 0.9999994822040257 | 1.0 — the registry stored it rounded |
| `worst_slice_relative_pass` | 1 | 1 |
| `cap_breach_bars` / `governor_engaged_bars` | 1318 / 7302 | **exact** |

Cost-stress (×1.5 → 1.3029, ×2.0 → 1.2106) was reproduced the same day in [[T0090]]'s instrument validation, and the drawdown figures are pinned by the frozen-figure regression at its own 4-dp tolerance — not byte-exactly, which the first draft of this line claimed. Margin over the reproduced benchmark: **+0.3481 full / +0.3136 decisive**.

**Why this re-derivation is legitimate where rebuilding trial 43 is not** — the distinction is the whole point of this topic. Every primitive here is **committed** (`cli/validation/spa.py`, `dsr.py`, `bootstrap.py`, `cli/alpha/killbar.py`, the record-44 builder), and the benchmark's construction was **specified in advance** in the phase-4 history before anything was run — a first attempt using the *wrong* construction missed by 0.06 Sharpe and was discarded rather than adjusted. Trial 43 has neither property: no committed code, and no specification to reproduce against, so a rebuild could only be tuned until it matched.

**The re-derivation is committed, not a scratchpad** — `cli/portfolio/record44_legs.py` with `tests/test_record44_legs.py`, runnable by anyone. Given that this topic exists *because* a scratchpad vanished, landing the answer in another one would have been self-defeating.

**A near-miss worth recording, because it was caused by this very closeout.** The two recovered conventions were first appended to spec `00038` — and review caught that registry records 43 and 44 store `spec_hash a25d7102…`, which is the **sha256 of that spec file**. The append changed it to `914c9fc4…`, silently breaking the pin that verifies the ratified record, inside a commit whose entire subject is the verifiability of that record. Reverted; the conventions live in the committed re-derivation module instead. **A spec named by a registry `spec_hash` is immutable** — the durable home for a recovered convention is runnable code, not the pinned document.

**Two details spec `00038` never pinned are recorded in `cli/portfolio/record44_legs.py`** (recovered by re-derivation, each proved discriminating by mutation): the SPA grid's headline cell is `(mean_block 30, seed 42)`, whose full and decisive readings became `spa_p_full`/`spa_p_decisive` — which is why no `spa_grid_b30_s42` key exists; and the worst-slice test runs on the **governed net over full history**, year taken from each bar's **close** stamp.

**What this ruling treated as permanently lost turned out not to be.** On 2026-08-21 the scratchpad runners behind rows 43 and 44 were recovered verbatim from the iter-080/081 session transcript — read four minutes before the tooling's retention prune destroyed it — and the stage-1 driver reproduces row 43's registered figures exactly, on two independent machines ([[T0148]]). Trial 43's construction is now maintained code — `cli/portfolio/record43_book.py` with tests, exactly as `record44_legs.py` is record 44's — with the recovered original bytes reachable in git history. The 43-vs-44 re-read, including the maker–taker reversal point, is answerable again and registered there. **The re-grounding above stands on its own merits and is not re-coupled to it**: the gate reads the benchmark-relative basis, exactly as ruled.

## Suggested next steps

_(none — resolved. The forward guard is built (`dbe27e0b`), the go/no-go is re-grounded on a reproducible basis, and every leg of that basis is re-derived and committed. The counterfactual this ruling recorded as unrecoverable was later recovered and verified — [[T0148]] owns it — with the re-grounding unaffected.)_
