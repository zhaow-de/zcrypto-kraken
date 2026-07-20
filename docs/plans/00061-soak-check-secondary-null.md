# soak-check secondary null — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Judge every metric under both the windowed and block-bootstrap nulls and surface instrument-fragility (spec `00061`, [[T0073]]).

**Architecture:** A pure reconciliation function in `cli/engine/soak.py`, called from `analyze_soak`; two new CLI options threaded through `soak_report`. No change to either null primitive — `block_bootstrap_null` already exists and is unit-tested.

## Global Constraints

- Severity order `consistent`(0) < `weakly-consistent`(1) < `inconsistent`(2); `n/a` outside it. Both n/a ⇒ n/a; one n/a ⇒ the discriminating one + disclosure; same ⇒ that label; **adjacent ⇒ the milder** + disclosure; **opposite extremes ⇒ `indeterminate (instrument-fragile)`**.
- The table's numeric columns stay the **windowed** null's; the secondary contributes a **verdict label only**.
- `indeterminate` counts in `n_metrics`, never in `n_outside`, and gets its own summary line.
- `--null` default `both`; `--null windows` must reproduce today's verdicts byte-for-byte.
- The bootstrap seed is fixed and NOT user-exposed (no shopping for a friendlier null).
- Vocabulary lock + banner unchanged. `indeterminate (instrument-fragile)` contains no forbidden word.

---

## Task 1: the reconciliation rule (pure)

**Files:** modify `cli/engine/soak.py`; test `tests/test_engine_soak.py`.

```python
_SEVERITY = {"consistent": 0, "weakly-consistent": 1, "inconsistent": 2}

@dataclass(frozen=True)
class DualVerdict:
    verdict: str            # reconciled label, or "indeterminate (instrument-fragile)"
    primary: str            # windowed null's label
    secondary: str          # bootstrap null's label
    disclosure: str         # "" when the two agree

def reconcile_verdicts(primary: str, secondary: str) -> DualVerdict: ...
```
Implement exactly the D1 branches. Keep it pure — no metric knowledge, no I/O.

- [ ] **Step 1** — one failing test per D1 branch (both n/a; one n/a; identical; adjacent both directions; opposite extremes). Assert the exact reconciled label AND that a disclosure is non-empty precisely when the inputs differ.
- [ ] **Steps 2–4** — fail → implement → pass.
- [ ] **Step 5** — gate; commit `feat(cli): soak-check dual-null verdict reconciliation`.

---

## Task 2: wire both nulls into `analyze_soak` + the CLI options

**Files:** modify `cli/engine/soak.py`, `cli/engine/command.py`; tests in `tests/test_engine_soak.py`, `tests/test_engine_soak_command.py`.

- `analyze_soak(..., *, null_mode: str = "both")`. For each of the 4 `windowed_null(...)` call sites (gating metrics, governor, cap-breach, P&L) also compute `block_bootstrap_null(same_series, same_window)` and reconcile. `MetricVerdict` keeps the **windowed** stats; carry the reconciled label + the secondary label + any disclosure alongside (extend `MetricVerdict` or hold a parallel `dict[str, DualVerdict]` — pick one and say which).
- `null_mode="windows"` ⇒ skip the bootstrap entirely and leave verdicts exactly as today. `"block-bootstrap"` ⇒ use only that null.
- `summarize_panel`: `indeterminate` counts in `n_metrics`, not `n_outside`; add the indeterminate line.
- `render_report`: new column for the secondary verdict; the indeterminate summary line; disclosures appended; state which null mode and which `--path` produced the run.
- `soak-check` gains `--null [windows|block-bootstrap|both]` (default `both`) and `--path [fast|verified]` (default `fast`), threaded through `soak_report` to `build_null` and the identity self-check. Help strings free of internal-tracker tokens.

- [ ] **Step 1** — failing tests: the fragility flag fires on a constructed windowed-says-inconsistent / bootstrap-says-consistent case (and fails if reconciliation is removed); both nulls agree on planted-consistent and planted-inconsistent; `--null windows` reproduces today's verdicts; multiplicity counts indeterminate correctly; determinism across two runs; vocabulary lock + banner hold over the new text.
- [ ] **Steps 2–4** — fail → implement → pass; also run `tests/test_cli_help_hygiene.py`.
- [ ] **Step 5** — gate; commit `feat(cli): soak-check --null/--path and dual-null reporting`.

---

## Task 3 (orchestrator): real-journal verification + closeout

- [ ] Run on the ops mirror with `--null both`; confirm all 7 metrics carry both verdicts, note any indeterminate, and check runtime is within a couple of seconds of today's.
- [ ] Confirm `--null windows` reproduces the pre-change verdicts exactly (diff against the saved baseline).
- [ ] Final whole-branch review; fix wave if needed.
- [ ] Closeout: iter-111 entry; [[T0073]] → `partial` (regime context still deferred, with its reason); PR; merge via `merge-pr` when green.

## Self-Review

- Spec coverage: D1→Task 1; D2/D4/D5→Task 2; D3→Task 2 (`summarize_panel`); D6→Task 2 tests. Test-list 1–2→Task 1/2, 3–7→Task 2, 8→Task 3.
- Grounded: `windowed_null` (soak.py:401), `block_bootstrap_null` (:410), the 4 call sites (:982, :1018, :1025, :1102), `metric_verdict`, `summarize_panel`, `render_report`, `soak_report` — all verified present.
