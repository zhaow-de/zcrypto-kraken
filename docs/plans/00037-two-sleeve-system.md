# Two-Sleeve System + Ratified Kill Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold the T0009-ratified kill bar into `a1_kill_bar` (TDD), register trial 34 (A1-lf weekly v0.12) and trial 35 (the two-sleeve P1 combination), update the protocol docs, and prepare the holdout-look script.

**Architecture:** One committed-code task (the kill-bar fold-in), then orchestrator-run trial drivers per the established scratchpad pattern (QA-gated, pre-registered criteria), then docs/lifecycle. Design fully settled in `docs/specs/00037-two-sleeve-system-design.md` + decisions log `[iter-072]`.

**Tech Stack:** Python 3.14, stdlib; existing `cli` machinery.

## Global Constraints

- The ratified bar exactly: SPA leg **net-of-cost** inputs, evaluated decisively on `[decisive_start:]` (230 for B3+vt-dynamic; full-window figure still reported); worst-slice leg = `benchmark_relative_worst_slice(book_slices, benchmark_slices)["beats_benchmark_worst"]` with stub slices (2013, 2026) excluded by the caller; `DSR_PASS_THRESHOLD = 0.95`; DSR and cost-stress legs stay own-series legs on the full window (they are not head-to-heads).
- `a1_kill_bar`'s result dict: keep every existing key (`spa_p_value` becomes the decisive-window figure); add `spa_p_value_full`, `worst_slice_relative` (the diagnostic's summary fields); `worst_slice_pass` now means the relative leg. Ratification date 2026-07-09 in the docstring.
- New required kwargs `benchmark_slices: dict[str, list[float]]` and optional `decisive_start: int = 0`. All existing callers are tests (update them) — grep confirms no cli-internal callers.
- Ruff 132/double quotes; gate `uv run pre-commit run -a`; commits carry the actual-model trailers.

______________________________________________________________________

### Task 1 (subagent, TDD): the kill-bar fold-in

**Files:** Modify `cli/alpha/killbar.py` (a1_kill_bar + DSR_PASS_THRESHOLD), `tests/test_alpha_killbar.py`.

Update the constant, signature, legs, result dict, and docstring per Global Constraints. TDD: first update/extend the planted-case tests — each leg gets a case at the new criterion (a planted book that passes/fails the 0.95 DSR bar; SPA decisive-window vs full-window divergence via a series whose edge lives only pre-cut; a relative worst-slice pass where the absolute leg would fail — reuse the exposure-blindness fixture idea from `test_benchmark_relative_worst_slice_exposure_blindness`); run to fail; implement; full suite green.

### Task 2 (orchestrator): trial 34 — A1-lf weekly v0.12

Driver per spec: QA (1.3798 / 1.2455 reproduced); DSR at n=33 (`var_trials` = variance of the 32 recorded per-period Sharpes from the registry); ratified legs via `a1_kill_bar` (net-of-cost inputs, `decisive_start=230`, stub-excluded slices both sides); registry append (family `A1`, `variant="A1lf-weekly-v012"`, `n_trials_in_family=33`, dataset-hash check vs record 1).

### Task 3 (orchestrator): trial 35 — the two-sleeve P1 combination

Driver per spec §construction (weight-level, full costing) with the pre-registered criteria (a)–(d); registry append (family `P1`, `variant="B3vtdyn+A1lf-w012+gov+cap"`, `n_trials_in_family=2`). If criterion (c) fails → verdict `reject`, the look's subject stays record 33.

### Task 4 (orchestrator): docs, lifecycle, look script

Master-plan §9/§12 ratified-bar wording (decision-dated); **T0009 → resolved** (archive + index); runbook holdout section (window ratified; look subject per trial 35's verdict); `holdout_look.py` prepared in the scratchpad (fresh pull → QA → two systems via committed code → paired-index CIs → ledger template) — **not executed**; iter-072 history entry; PR.
