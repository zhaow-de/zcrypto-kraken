---
status: partial
ripe_when: 6b produces its first weeks of paired live-vs-simulation cycles with real fills
---

# §12's "Ongoing" register is prose-only — kill criteria, revalidation, decay tests

## Context — what

The master plan's post-go-live regime ("Ongoing — Operate, Monitor, Revalidate") names monthly revalidation on rolling data (registered as trials), quarterly decay tests (CUSUM on live-vs-expected P&L), and **pre-registered production kill criteria** (DD-ladder floor, N-month underperformance beyond CI vs its own simulation) "so the retire-decision is mechanical, not emotional". None of it is registered anywhere — it lives only as plan prose, the same hole [[T0113]] closed for the snapshot register. The kill criteria in particular must exist, with numbers, before capital scales past the first ramp step.

## Why this matters

A retire-decision without pre-registered criteria is taken under drawdown stress by a human reading a losing book — precisely the condition pre-registration exists to remove. And unregistered monthly revalidation means the live system's edge is never re-tested on schedule: decay is discovered by P&L instead of by instrument, months late. The plan says the right things; nothing makes them happen.

## Findings so far

- The revalidation cadence has natural registry mechanics already (trials in the append-only registry, DSR at true trial count) — the gap is the schedule and its trigger, not the instrumentation.
- The kill criteria's numeric inputs exist: the DD ladder is deployed config (the governor's `((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))`), and the validation CI comes from the deployable record's registered verdict. What is missing is the owner-ratified thresholds and where they live so the check is mechanical.
- [[T0049]]'s runbook is the operating surface for recurring routines (it already carries [[T0113]]'s monthly sweep) — the register lands there, not in a new document.

## Done so far

- **The DD kill floor is ratified: 20 % governed drawdown (owner, 2026-08-02; iter-119).** Derived from the deployed ladder in `cli/risk/governor.py` — `((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))`, where the 0.15 rung is terminal-with-re-arm, not a stop — against record 44's registered governed maxDD of **0.1357**. At 20 % the floor is 1.47× that maxDD and sits **5 points past the terminal rung**, so reaching it means the governor already went flat *and* the book lost five further points across re-arm cycles: a state the validated system never entered. 18 % was rejected as inside the ladder's own working range (one failed re-arm cycle reaches it, so the criterion would retire the system for the ladder working as designed); 22 %/25 % were rejected as binding only after 2–10 further points of capital. The floor is expressed against **governed** drawdown deliberately — the same quantity the ladder acts on.
- **The underperformance criterion changed shape, because the obvious statistic cannot fire.** A kill on **live Sharpe** is undecidable at any 6b horizon: with the IID standard error of an annualized Sharpe over `T` years at `sqrt((1 + S²/2)/T)`, the [[T0124]] live-state baseline (governed Sharpe ≈ 0.63 extended / 0.75 registered-window) gives a 95 % half-width of **±2.15 after a full year**, and needs **8.2 years** one-sided or **11.6 years** two-sided to separate from zero at all. Even the 1.5609 headline needs 2.5–3.5 years. So the pre-registration hole was never a missing threshold — it was a statistic that cannot reach significance inside the life of the decision it governs.
- **Ratified statistic: the paired per-cycle live-minus-simulation difference (owner, 2026-08-02).** Both series run the same signal on the same bars, so the common market factor cancels and the residual is execution error alone (fees, slippage, timing) — which is exactly why it is decidable in weeks where the standalone quantity is not. This is the faithful reading of §12's existing "beyond CI vs its own simulation" wording, so **no master-plan amendment is owed**. Rejected: DD-floor-only (blind to a slow bleed that never draws down hard) and a cumulative-path percentile test (calibratable today without fills, but path-dependent — one early bad week biases the comparison for months).

## Suggested next steps

- **(autonomous, monthly — trigger readable from the registry itself)** Re-run revalidation on rolling data and register each run as a trial in `docs/reference/trial-registry.jsonl` (DSR at true trial count), with the same bump-the-stamp discipline as [[T0113]]'s sweep: an unchanged revalidation must still be recorded, or a later reader cannot tell "re-confirmed and identical" from "never re-run". Instrument: the existing registry mechanics plus `soak-check`. Registered here rather than in `infra/runbooks/README.md`: that file's scope is procedures for a **signal that fires at an operator**, and every section owes a checkable `Retire when` — a recurring routine with no live signal behind it would be backlog, which the runbook bans by name. It moves there with [[T0049]]'s runbook build, exactly as [[T0113]]'s monthly ⏱ sweep is registered to.
- **(autonomous, quarterly)** Decay test on the paired live-vs-expected series, same recording discipline. The instrument does not exist: no current tool computes the paired difference, so this needs the harness below first.
- **(autonomous — blocked on 6b fills, not on effort)** Build the paired live-vs-simulation harness and derive the underperformance bound from 6b's first weeks. Cannot be estimated from shadow data, where nothing fills and the paired difference is identically zero by construction. The CUSUM framing from the original plan prose is one candidate detector on top of this series, not a substitute for building the series.
- **(decision, before ramp past 25 %)** Owner ratifies the underperformance **bound** once the harness above yields it. The statistic, window shape, and DD floor are already ratified; this is the one remaining number, and it is deliberately registered with its trigger rather than guessed.
