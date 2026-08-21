---
status: partial
ripe_when: the bench_noc substitution is pinned ELEMENTWISE against a committed reference (the topic's own stated precondition for any stage-2/kill-bar re-run) — one comparison script, autonomous; the maker–taker sweep follows immediately behind it.
---

# Trial 43's "unrebuildable" runners were recoverable from a session transcript

## Context — what

[[T0125]] established that registry record 44's ADOPT verdict rests on a comparison against **trial 43**, and that trial 43 could not be rebuilt: its `run_ref` names scratchpad scripts, `git log --all -S"adaptive" -- cli/` returns nothing, and "scratchpads are session-scoped; these are gone."

That was true of the filesystem. It was **not** true of the Claude session transcripts, which record every `Write` and `Edit` tool call verbatim, including full file contents. The iter-080/081 session's transcript was read on 2026-08-21 at 16:05 UTC, all five scripts named in trials 43 and 44's `run_ref` were reconstructed from it, and the stage-1 driver **reproduces trial 43's registered stage-1 figures exactly**.

**The source transcript no longer exists.** `ea685ee3-3fd7-43cd-9007-bf1bbab513c0.jsonl` (dated 2026-07-21) was deleted by the tooling's 30-day retention prune at **16:09 UTC — four minutes after it was read, and 27 minutes before the commit that preserved its contents**. Four transcripts survive locally, all newer than 2026-07-22; the file is nowhere on disk. **This git history is now the only surviving copy of these artifacts, and the replay is permanently unfalsifiable by anyone.**

That is not an aside — it is the topic's own stated hazard ("workstation-local, unbacked, prunable") firing inside the session that documented it, and it is the strongest argument for having committed the bytes rather than a pointer.

## Why this matters

**A conclusion recorded as permanent is not.** [[T0125]] stated (in the wording this branch has since corrected in place) "what remains permanently lost, stated plainly: the counterfactual … Nobody can ever re-read the 43-vs-44 ordering, including at the taker end where the registry itself discloses that the ordering reverses at ×2.0." With the driver reproducing, that measurement is available. The specific question [[T0090]] was blocked on — where in the maker-taker range the ordering reverses — is answerable.

**The owner ruling that closed [[T0125]] is untouched by this, and should stay untouched.** Re-grounding the go/no-go on the reproducible benchmark-relative basis was right on its own merits: it makes the gate independent of any single incumbent comparison. Recovering trial 43 restores an *answer*, not a *dependency* — nothing about the gate should be re-coupled to it.

**The forward guard is still correct.** A transcript is workstation-local, is not backed up, is not git-controlled, and is pruned by the tooling on its own schedule. This recovery was luck. [[T0125]]'s append-time and repo-level `run_ref` guards remain the right mechanism, and nothing here argues for relaxing them.

**Committing the artifacts is what makes the recovery portable.** Until this branch, the only copy lived in one workstation's local transcript — invisible to the other workstation, and lost on any reimage. That is the same fragility class that created the problem.

## Findings so far

- **All five `run_ref` scripts recovered**, by replaying the initial `Write` content and then every `Edit` in recorded order, each `old_string` required to match: **13/13 operations applied, 0 failures** (`crossfreq_run.py` took 1 Write + 7 Edits; the other four 1 Write each, plus 1 Edit on `trial44_write.py`).
- **What that replay does and does not prove.** It proves the recorded Edit chain is self-consistent: a wrong intermediate state makes the next `old_string` unmatchable. It does **not** prove the bytes are what ran — the replay reads only `Write` and `Edit`, so any shell-side mutation (`sed -i`, a heredoc) or any edit after the last recorded one is invisible by construction. **The behavioural reproduction below is the real proof**, and it is the claim to lead with.
- **The recovered code contains exactly what [[T0125]] identified as missing from git**: sleeve-level adaptive inverse-vol weighting — `WEIGHT_WINDOW = 180`, and "sleeve weights: trailing 180 bars through k-1; ANY degenerate -> all 1/3". That is the `ivol180` in the variant string `P1-crossfreq-B3vtdyn+A1lfw012+A2ens4h-ivol180-cap-govD`, and the origin of the row's `weight_warmup_bars` / `weight_zero_vol_fallback_bars`.
- **The same transcript independently records what the scripts printed on 2026-07-10**, which is what makes this recovery rather than reconstruction:

  | source | figure |
  | --- | --- |
  | `crossfreq_run.py` 11:44:42 | governed noc Sharpe **1.5366** full / **1.5319** decisive; maxDD **13.31 %** / 19.46 % pre-gov; cap-breach **1265**; gov-engaged **7290**/27337 |
  | `stage1b_verify.py` 11:47:31 | cost stress ×1.5 **1.3008**, ×2 **1.2400**; "Sharpe 1.5366 >= 1.3263: True … => ADOPT" |
  | `crossfreq_stage2.py` 11:49:37 | fixed-1/3 counterfactual **1.5609** (adaptive 1.5366) |
  | `trial44_run.py` 12:19:27 | **1.5609**/1.5583, maxDD 13.57 %, cap breach **1318**, gov engaged **7302** |

  Every figure matches registry row 43, and trial 44's 1318/7302 matches [[T0125]]'s own re-derivation table.
- **[[T0125]]'s reconstruction objection does not apply, and the distinction is the point.** Its argument is that rebuilding from the variant string "proves only that it was tuned until it did". These are the original bytes, with an independent contemporaneous record of their output — the thing a reconstruction can never have.
- **Re-run 2026-08-21 reproduces the stage-1 headline from committed code.** Scope, stated plainly: only `crossfreq_run_rederived.py` was executed. `crossfreq_stage2.py`, `stage1b_verify.py`, `trial44_run.py` and `trial44_write.py` were **not run**, so they rest on the replay alone. The re-run covers **15 of row 43's 35 metrics**; the 20 uncovered include every SPA cell, `dsr`, `var_trials_4h`, both cost-stress figures, `worst_slice_relative_pass`, and `fixed_third_counterfactual_sharpe_ann = 1.5609` — which is the 43-vs-44 number the measurement sub-item proposes to re-read. Every intermediate gate matched the 2026-07-10 run before the headline did: B 1.2455, A1 1.3798, A2 arms 1.3274 / 1.3017 / 1.3585, expansions 1.2704 / 1.3927, 4h benchmark 1.2128 / 1.2447. Then:

  ```
  governed noc Sharpe: 1.5366 full / 1.5319 decisive (k>=1380)
  maxDD: 13.31% governed / 19.46% pre-governor; cap-breach 1265; gov-engaged 7290/27337
  equal-weight fallback bars: 180 warm-up + 10638 zero-vol degenerate
  ```

  The last line is the strongest single check: **180** and **10638** are the row's `weight_warmup_bars` and `weight_zero_vol_fallback_bars`. They fell out of the computation; nothing was fitted to produce them.
- **Two substitutions were required, both forced by *upstream* artifacts that are also gone, and both self-validating** — recorded in full in the recovered-runners README:
  1. `crossfreq_run.py` cross-checks the A2 arms elementwise against iter-074's `a2_4h_cache.pkl`. The arms are *recomputed* from committed `a2_book_returns`; only that comparison was dropped. Each arm still asserts against its **registered** Sharpe, and all three passed.
  2. The same cache held `bench_noc` as a genuine input. Sourced instead from committed `cli/portfolio/record44_legs.py::benchmark_4h_net_of_cost`, and validated by the script's own pre-existing assert against the **registered** 1.2128 / 1.2447. **That validation is Sharpe-only, and it is sufficient for stage 1 but not beyond**: `bench4h` does not enter the 1.5366 computation at all (it is QA'd and cached), but `crossfreq_stage2.py` and `stage1b_verify.py` consume it, and `benchmark_relative_worst_slice` compares elementwise by year — two series can share a Sharpe and differ per-bar. Anyone taking the measurement sub-item must pin this substitution elementwise first.
- **The registry `dataset_hash` (`45275ebe…`) differs from the local manifest's `basket_sha256` (`70c2728e…`).** These are different recipes, not different data — every upstream gate reproducing exactly is the evidence.
- **Only one session created these artifacts.** Of the eight local transcripts present at the time of the sweep, `ea685ee3` held all 19 `trial43/` file paths; the rest only mention the trial. No original scratchpad survived on disk, and the transcript itself has since been pruned (above).

## Done so far

- **The five recovered originals, two documented recovery variants, and a README are committed** under `docs/reference/trial43-recovered-runners/`, beside the trial registry they are provenance for. Both `ruff.toml` and `.pre-commit-config.yaml` exclude that directory, following the `infra/nas/rrsync` precedent in those same files: a reformat destroys the byte-exactness that is the entire value. Verified byte-identical through a full `pre-commit run -a` with the files staged.
- **`trial44_write.py` is committed but must never be run** — it calls `reg.append(...)` against the append-only, hash-chained registry. It self-guards (`assert len(reg.records) == 43`, and it points at the pre-move path `docs/research/trial-registry.jsonl`), but the README states the hazard rather than relying on that.

- **Both owner rulings are decided (2026-08-21, recovery evaluation delegated to the session): KEEP the recovery, and correct the record in place.** [[T0125]]'s archived file is corrected per option (c) — its four now-false claims rewritten where they stand (context, "permanently unanswerable", "gone for good", and the closing "permanently lost" paragraph), with the ruling and the forward guard untouched, exactly as this topic recommended. The same claim was corrected at its other three live carriers — [[T0090]]'s "NOT POSSIBLE" finding, the master plan's §12 gate-limitations paragraph, and [[T0125]]'s index bullet — while the point-in-time carriers are deliberately left and named: the two 2026-08-03 iterations-history entries and the iter-122 entry in `docs/research/14.phase6-decisions.md` (a changelog and a decisions log are frozen records; the 2026-08-21 entry supersedes them), the hash-chained registry rows 43/44/47 whose `notes` carry the claim (structurally uneditable), and spec `00095`'s "remains unrebuildable" line, which is **immutable** — record 47's `spec_hash` pins that file, and editing it would break the pin verifying the successor record, the exact near-miss [[T0125]]'s own closeout recorded against spec `00038`.
- **The reproduction was independently repeated on a second workstation (2026-08-21, this branch's verification).** Fresh worktree at the recovery commit, `data/ohlc-full` by symlink, 2 min 07 s: every figure identical to registry row 43 — Sharpe 1.5366/1.5319, maxDD 13.31 %/19.46 %, cap-breach 1265, governor 7290/27337, spot drag 3.40 %/yr, criterion flags 1/0, and the discriminating **180 + 10638** fallback bars — with every intermediate gate (B 1.2455, A1 1.3798, arms 1.3274/1.3017/1.3585, bench 1.2128/1.2447, expansions 1.2704/1.3927) landing on its registered value first. Two machines, one recovered instrument, same numbers: the recovery is no longer resting on one workstation's run.
- **The transcript-as-forensic-resource framing has its durable home** — the recovered-runners README's Provenance section states it in full (workstation-local, unbacked, prunable, demonstrated by this very recovery's four-minute escape). Nothing further owed; the "consider" sub-item below is disposed into that text.

## Suggested next steps

- **(the one remaining sub-item) Take the maker–taker measurement [[T0090]] was blocked on.** Precondition first, per this topic's own caveat: pin the `bench_noc` substitution **elementwise** against committed `cli/portfolio/record44_legs.py::benchmark_4h_net_of_cost` — Sharpe-equality is sufficient for stage 1 but `crossfreq_stage2.py` and `stage1b_verify.py` consume the series per-bar, and two series can share a Sharpe and differ elementwise. Then re-run the recovered driver and `trial44_run.py` across the maker→taker cost range and report where the 43-vs-44 ordering crosses (the registry discloses reversal at ×2.0; the open question is where it begins). This is **decision-support, never a gate input** — the go/no-go stays on the benchmark-relative basis per [[T0125]]'s ruling, and nothing re-couples to trial 43. Registered here and queued in the memo; a research session takes it with its own decisions-log entry.
