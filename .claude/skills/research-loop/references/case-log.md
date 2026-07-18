# research-loop case log

Why the loop's rules exist — the incidents that minted them. Read this when a rule's rationale matters to a live judgment call; the rules themselves live in `SKILL.md`.

## The PoC's inert gate (false negative, 12 iterations)

A silent sizing-hook bug left the regime gate inert. Backtests ran clean and minted a confident "regime gating doesn't help" that stood for a dozen iterations — caught only when a four-arm A/B returned bit-identical Sharpes. The fix overturned the conclusion; the overturn was the real deliverable. → *Prove the treatment engaged; arms must differ; a dead knob is the default suspicion.*

## The PoC's NaN deflated Sharpe (false positive)

A broken trial register produced a NaN DSR that minted an apparent winner — pure artifact. → *Plausibility-gate every metric; registry invariants are tested code.* Together with the inert gate: the PoC minted one wrong conclusion in each direction, which is why skepticism is symmetric.

## The lost worst-slice flag (iters 045 → 053 — why deferrals must be registered)

iter-045's plan and a `killbar.py` docstring flagged "recalibrate the worst-slice bar against the frozen benchmark's own worst slice" for the first real-data run. Registered nowhere reviewable, the flag was invisible when that run arrived one iteration later (iter-046). The absolute leg then rejected A1-long/flat on a comparison later shown uninformative (iter-049), and iter-053 rediscovered the whole issue the hard way — the frozen benchmark fails the leg itself. Three iterations of verdict debt from one lost one-liner. → *Deferrals must be registered with `ripe_when:`; prose is not registration.*

## The buried Bucket-B deferral (archived T0004)

T0004 was resolved with "15m bars + tick storage folded into the Bucket-B queue" — a live deferral inside an archive file that is never reviewed. It was recovered only by a manual audit (2026-07-09, → T0012). → *Never archive a topic carrying a live deferred sub-item.*

## The over-correction (iter-053 — why corrections are verdicts)

iter-053 "corrected" iter-049's claim that gated-B1 sat out 2014, asserting "it did not sit 2014 out; it lost more" — on the strength of the Sharpe alone (−2.07 vs −1.80). Economically false: gated-B1 was ~87 % flat in 2014 and lost −5.5 % with a 6.0 % drawdown, vs A1-long/flat's −8.4 % / 8.4 % — the worse Sharpe was an exposure-normalization artifact of the very leg under indictment. Caught in pre-merge review and withdrawn. → *Verify P&L / drawdown / exposure before overturning a claim; a false correction poisons the record like a false verdict.*

## The A1 four-PR churn (iters 046–049 — why findings merge settled)

The A1 kill-bar verdict merged without its first-order cost check; net-of-cost reality, cadence/offset effects, and SPA multiplicity each arrived one PR later — one report rewritten across four PRs (#64–#67), then re-scoped again in #71. Each individual correction was honest; the churn was avoidable. → *Ask "which robustness check would most plausibly overturn this?" and run it on the same branch before the PR opens.*

## The A2 family-key call (iters 052–053 — the budget invariant)

A2 is an A/B inside the A family (master plan §5). A new registry key would have restarted `n_trials_in_family` and silently un-capped the shared A=40 budget, so the trials were recorded under `family="A1"` with `variant=A2-donchian` in `notes` — ugly name, correct invariant. → *Variants share the family key; the first-class schema field is T0013.*

## The broken-instrument budget hold (iters 053–054)

Once the worst-slice leg was shown to fail the frozen benchmark itself, spending more of the A family's 8 remaining trials would have bought known-uninformative rows. The loop switched to no-trial-spend harness packages (`benchmark_relative_worst_slice`) and parked resumption on the protocol decision (T0009). → *A broken instrument suspends spending.*

## The Phase 0 → 1 boundary drift

The loop advanced into Phase 1 on a bare "phase complete" note, leaving Phase 0 without its close-out report — fixed retroactively by `01.3.phase0-closeout.md`. → *Never cross a phase boundary without the close-out report* (decisions are now persisted live per iteration, so nothing to drain — but the close-out report is still mandatory).

## The A2 double-division (iters 065–066 — caller-convention drift)

Two probe drivers passed a per-period `target_vol` to `A2Config`, which takes the ANNUALIZED value and divides by √ppy internally — the A2 books ran at ~1/19 scale, and the mis-scaled numbers seeded a decision-critical (and false) "A2 demonstrates non-participation reward" reading headed for the human's T0009 sheet. Caught by the pre-merge review, which empirically pinned the fix by matching the corrected Sharpes to registry records 25/26/29/30 to 4 decimals; the merged iter-065 claims were corrected in place with bracketed notes. → *State unit contracts in the config docstrings and never pre-scale in the caller; a review that re-derives numbers from primary sources catches what a review that reads prose cannot.*

## The silently-dropped protocol item (iter-059)

The combination-trial spec pre-registered "record PSR/DSR (deflation nil at n=1)"; the driver and registry record omitted it, and nothing logged the narrowing. The pre-push review caught it; the figures were computed post-hoc through the identical construction and recorded with the omission disclosed. → *Pre-registered protocol items are a checklist at driver-writing time — walk the spec's protocol section line-by-line before running, and log any deliberate narrowing as a decision.*

## The never-operationalized holdout default (iter-061, T0017)

The Decision Register adopted "holdout = final 12 months at data freeze" as an autonomous default — and no phase ever carved it out. Every backtest from Phase 3 onward consumed the full window, silently burning the pre-registered holdout; the only clean window left is out-of-time data. Surfaced honestly at runbook-drafting time and escalated (T0017). → *Operationalize a register default the moment it is adopted (carve the data, build the ledger, add the guard) — a default that exists only as prose will be violated by everyone who never re-reads it.*
