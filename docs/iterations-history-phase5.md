# Iterations history — Phase 5 (Portfolio Assembly & Risk Layer)

Per-iteration changelog for Phase 5. Appended at each iteration's close-out; see `.claude/rules/prose.md`.

## 2026-07-09 — iter-058: §10 drawdown governor as tested code + threshold backtest (Phase 5)

- **`cli/risk/`** — the §10 drawdown ladder is committed code with the ratified constants, so a backtest or an engine composes `drawdown_governor` instead of re-deriving the rungs (spec/plan `00034`).
- **The ladder thresholds are backtested, not merely ratified** — the governor is kept on the frozen bar because it lifts Sharpe while cutting drawdown, and the one-at-a-time sensitivity sweep found no knife-edge; the figures are in `docs/research/13.phase5-decisions.md` `[iter-058]`.
- **Two governor properties bind every later reader**: the 15 % budget is per-cycle under the mechanical re-arm — live restart stays the human's post-mortem call — and the daily −3 % rule is a tail backstop, not a working rung; both carried into `docs/research/12.phase5-system-spec-runbook.md`'s live-governor semantics.
## 2026-07-09 — iter-059: the combination trial — P1 adopt (Phase 5, registry record 33)

- **`cli/risk/limits.py`** — the §10 per-asset cap ships as `apply_position_caps`, a pure pre-trade clip with no redistribution (a limit, not an optimizer), so every later book applies it the same way (spec/plan `00035`).
- **Registry record 33 — the combined system (frozen bar + cap + governor) is ADOPTED** on its pre-registered criteria and becomes the candidate portfolio spec; the verdict, its both-direction SPA and its cost-stress rungs are the record's own.
- **The remaining §10 portfolio limits were left unbuilt on evidence at this point** — gross leverage never binds on this long-only book, so they waited for the first short-carrying or levered sleeve; built as tested code at iter-088 below, with the wiring on T0016.
- **The live-registry acceptance test is no longer pinned to a fixed-size snapshot** — the early records stay asserted verbatim, the count is floored, and later records must be schema v3+, so appending a record no longer edits the test.
- **A pre-registered leg the driver silently dropped was recomputed and recorded in the decisions log, never in the registry** — the registry is append-only, so a record's remediation is an addendum elsewhere.
## 2026-07-09 — iter-060: stress suite on the adopted combined system (Phase 5, no trial spend)

- **`docs/research/11.phase5-stress-suite.md`** — the §12 stress suite for the adopted system is a committed report; its per-rung dispositions are read there rather than re-argued.
- **Two structural costs become standing assumptions of the live system** — a first single-day shock passes through the ladder at full multiplier (gap risk belongs to the §10 operational layer, not the trailing ladder), and a window starting inside a bear pays the overlay's de-risk cost without its compounding benefit — both carried in `docs/research/12.phase5-system-spec-runbook.md`.
- **The borrow-unavailable rung is N/A only while the book never shorts** — it becomes mandatory again for any short-carrying system (T0016).
- **The adopt verdict of record 33 stands after the suite**, so no stress rung is a reason to re-open it.
## 2026-07-09 — iter-061: final system spec, runbook draft & holdout protocol (Phase 5, docs)

- **`docs/research/12.phase5-system-spec-runbook.md`** — the deployable construction, the validation-dossier index and the daily-cycle runbook draft live in one document, so a Phase-6 build reads it instead of reconstructing the system from trial drivers.
- **The register-default holdout was never carved out** — every backtest through record 33 ran the full dataset span, so the only clean holdout is out-of-time data after the freeze; redefining a pre-registered element is human-gated, and the window was registered as T0017 (ratified iter-072).
- **The holdout-look procedure was pre-registered before any number existed** — fresh pull, QA and manifest hash, the two systems on the ratified window, bootstrap CIs, the budgeted-holdout ledger, then the human's go/no-go — under the rule that pulling data is not looking but computing on it is.
## 2026-07-09 — iter-062: registry exact key-set validation (T0015 drained; Phase-5 interlude)

- **`cli/registry/record.py` enforces an exact per-schema-version key set** — a stored record with a surplus or missing key is corruption, so a forged record that is correctly rehashed and rechained still fails to load (T0015 resolved).
- **Two `test_registry_record` fixtures were corrected to the shape the store actually writes**, rather than loosening the check to accept them — a fixture encoding an obsolete contract is fixed, not accommodated.
## 2026-07-09 — iter-063: combined-system builder as committed code (Phase-5 interlude, manufactured package)

- **`cli/portfolio/build_combined_system`** — the adopted system's whole pipeline is one composed, tested function, so the holdout look and the Phase-6 daily cycle build on committed code instead of scratchpad-driver archaeology (spec/plan `00036`).
- **It composes the same building blocks the QA-gated drivers ran** — the same-code-path property is the reproduction guarantee, which is why the cross-package import into the alpha helpers is deliberate.
- **`test_frozen_figures_regression` makes the drivers' QA gate a standing test** — it rebuilds the system from the canonical dataset and asserts record 33's figures, and it skips where that dataset is absent, so it is run locally or it is not coverage.
## 2026-07-09 — iter-064: holdout-procedure dry-run on the research window (Phase-5 interlude)

- **The pre-registered holdout procedure was dry-run in-sample through the committed builder**, so at the event only the window changed; the in-sample reading is the exit bar's *equals* branch (`docs/research/13.phase5-decisions.md` `[iter-064]`).
- **The runbook's CI step names its pairing convention** — paired-index stationary bootstrap, one index draw applied to both series per resample; unpaired resampling of dependent series would be wrong by construction.
## 2026-07-09 — iter-065: the 2026 partial-year-stub probe (T0011 sub-item; feeds T0009)

- **A partial-year stub is not evidence against a book** — in 2026 the benchmarks and the combined system held literal zero exposure, and negative quarter-length windows are common for a healthy book, so the "2026 weakness" reading is exposure-blindness (base rates in `docs/research/13.phase5-decisions.md` `[iter-065]`).
- **The probe's A2 rows are superseded** — the driver passed a per-period `target_vol` to a config that expects the annualized value, running those books far under scale; the corrected 2026 loss is economically real, the exposure and base-rate findings are A2-independent, and no registry record was affected (correction under `[iter-066]`; the unit contract now stated in the config docstrings).
- **T0011 → `partial`** — the probe is done; its remaining items spend reserved trials and stayed gated on T0009 (T0011 resolved at iter-080).
## 2026-07-09 — iter-066: T0009 consequence tables (decision-support; zero trial spend)

- **The absolute worst-slice leg fails everything that trades, including the adopted bar itself**, while the benchmark-relative leg discriminates in both directions and excluding partial-year stubs is near-inert — the consequence evidence T0009's worst-slice decision was made on. Full table (calendar years, end-of-move stamping; (b) = the iter-054 benchmark-relative diagnostic vs the adopted bar):

| Book | (a) absolute | (c) abs, no stubs | (b) bench-rel | (bc) rel, no stubs |
| --- | --- | --- | --- | --- |
| combined (P1, adopted) | FAIL 2018,2022,2023,2025 | FAIL (same) | PASS (DD 8/11) | PASS (DD 8/11) |
| B3+vt-dyn (the bar) | FAIL 2018,2022,2023,2025 | FAIL (same) | — is the bar | — |
| gated-B1 (old bar) | FAIL 2014,2018,2021,2022,2025 | FAIL (same) | FAIL (DD 5/11) | FAIL (DD 5/11) |
| A1-lf weekly v0.10 (S 1.347) | FAIL 2014,2018,2019 | FAIL (same) | PASS (DD 5/11) | PASS (DD 5/11) |
| A1-lf weekly v0.12 (S 1.380) | FAIL 2014,2018,2019 | FAIL (same) | PASS (DD 5/11) | PASS (DD 5/11) |
| A2 lf 10–40 v0.10 / v0.12 | FAIL 2014,2018,2019,2022,2025,2026 | FAIL (−2026) | PASS (DD 5/11) / PASS (DD 4/11) | same |
| A2 lf 20–100 v0.10 / v0.12 | FAIL 2014,2018,2022,2025,2026 | FAIL (−2026) | **FAIL** (DD 5/11) / **FAIL** (DD 2/11) | same |

- **A drawdown-count criterion can in principle favour low-exposure books**, so a worst-slice redesign weighs a P&L or exposure dimension — a design caveat stated without an empirical case.
- **Tightening the DSR threshold from 0.5 to 0.95 flips no recorded verdict**, so it was free to take and binds only future marginal families.
## 2026-07-09 — iter-068: PBO selection-inflation read on the benchmark family (Phase-5 interlude)

- **The adopted bar's top rank is moderately window-dependent while its top cluster is stable** — the CSCV read over the family variants on the table at the bar decision returned PBO = 0.365, so the holdout expectation is the cluster level, not the point estimate (also recorded in `docs/research/13.phase5-decisions.md` `[iter-068]`).
- **A pre-set reporting rule outranked a useful sentence** — the drafted runbook sentence was withdrawn once the review flagged that adding it softened "materially high" after the fact, so the runbook carries no PBO sentence.
## 2026-07-09 — iter-069: A1-long/flat start-date sensitivity (decision-support; feeds T0009)

- **The A1-long/flat weekly edge over the adopted bar is start-date robust** — significant at every start from 2014 through 2022 and stronger with 2014 dropped, so the early-data-artifact doubt resolves against the artifact reading (per-start figures in `docs/research/13.phase5-decisions.md` `[iter-069]`).
- **The readings were recorded into T0009's A1-lf item as decision-support**, with the disposition left to the attended review that ratified the bar (iter-072).
## 2026-07-09 — iter-070: A1-long/flat cost-stress read (completes the T0009 A1-lf package)

- **The A1-lf weekly v0.12 arm keeps its significance under the cost-stress rungs while the v0.10 arm loses it** — the read that made v0.12 the admissible sleeve (figures in `docs/research/13.phase5-decisions.md` `[iter-070]`).
- **T0009's A1-lf decision-support package is complete** — head-to-head, SPA, start-date robustness, drawdown and cost stress all recorded; the disposition was the human's at iter-072.
## 2026-07-09 — iter-071: night-audit sweep and fixes (iters 057–070)

- **A cross-iteration audit is the completeness pass per-PR reviews structurally cannot do** — numbers consistency across documents, a deferral sweep over entries, reports, topic edits and PR bodies, decisions-log supersession hygiene, and repository-state invariants; every finding was dispositioned in the same pass.
- **Two deferrals that lived only in prose became registered work on T0016** — the remaining §10 portfolio limits as tested code, and the borrow-unavailable stress-rung re-run — because an unregistered deferral is not tracked.
## 2026-07-10 — iter-072: the attended protocol review executed — ratified bar, trials 34/35, look prepared

- **The §12 kill bar is ratified and rewritten in the master plan** — benchmark-relative, stub-excluded worst slice; the post-warm-up window decisive with both windows always reported; net-of-cost SPA on both sides; DSR threshold 0.95 — and `a1_kill_bar` implements exactly that, so a verdict is computed rather than argued (T0009 resolved).
- **A1-lf weekly v0.12 is admitted as a second sleeve and A-family trial spending resumes**, so later loops may draw on the reserved budget.
- **The holdout window is ratified as out-of-time, 2026-04-01 → a fresh freeze** (T0017 → `partial`; the look and its ledger followed at iter-073).
- **Registry trials 34 (adopt) and 35 (reject) are on the record** — the two-sleeve combination missed a pre-registered criterion though it was not dominated, so the deployable system and the look's subject stayed record 33.
- **Any degenerate sleeve-weight window is 0.5/0.5 by convention** — the under-specified branch that made two scripts disagree on the same book; records 34/35 pin the pre-amendment `spec_hash`, so a recomputation against the committed spec `00037` mismatches on documentation, not on what was computed.
## 2026-07-10 — iter-073: the holdout look, GO to paper, Phase 5 closed

- **The holdout look is spent — budget 1 → 0, ledger `docs/research/13.phase5-holdout-ledger.md`** — the ratified window was degenerate (both systems at literal zero exposure throughout), so the exit bar's *equals* branch was met trivially and carries no discriminating information (T0017 resolved).
- **The governor enters live at its carried ×0.5 state**, so the live book deploys at half size at the next gate-on (also recorded on T0018).
- **A drawdown-aware combination adopt criterion binds trial 36 onward** — adopt if Sharpe is within 0.02 of the incumbent and maxDD is at least 1.5 pp lower — bound forward, so the trial-35 reject stands with no post-hoc re-read (`docs/research/13.phase5-decisions.md` `[iter-073]`).
- **GO to paper trading, and Phase 5 is closed** — close-out `docs/research/13.phase5-closeout.md`, decisions drained to `13.phase5-decisions.md`; Phase 6 opens with the gate-off shakedown and live capital behind the ramp gates.
______________________________________________________________________

**Continuation — Phase-5 backlog resumed during a later phase's era** (iters 76+, routed here by subject matter per the `iteration-closeout` skill).

______________________________________________________________________

## 2026-07-10 — iter-076: cross-frequency combination design (T0011 → executable)

- **`docs/specs/00038-cross-frequency-combination-design.md`** — the A-family survivors fold into one three-sleeve P1 trial on the 4h union calendar, daily sleeves held intraday, with the governor evaluated at its ratified daily cadence rather than rescaled; an executing loop follows this design.
- **The verdict protocol was pre-registered before any number** — the drawdown-aware criterion binds, else Sharpe-primary against the 4h-rebuilt bar with every ratified leg (`docs/research/13.phase5-decisions.md` `[iter-076]`).
## 2026-07-10 — iter-077: cross-frequency helpers as tested code (de-risking the 00038 trial)

- **`cli/portfolio/crossfreq.py`** — `expand_daily_positions` and `daily_cadence_governor` make the design's index mapping committed, tested code, so a cross-frequency trial no longer hand-rolls its most silently bug-prone step.
- **Day-index gaps are rejected, not documented** — compression semantics would diverge from calendar-faithful behaviour for a gap wider than the cooldown, and the union calendar never produces one, so contiguity is validated instead of assumed.
## 2026-07-10 — iter-080: cross-frequency combination ADOPTED (trial 43) — the deployable candidate changes

- **Registry trial 43 — the three-sleeve cross-frequency combination is ADOPTED and supersedes record 33 as the deployable candidate**; the Phase-6 engine builds against it (T0018).
- **`expand_daily_positions` is contract-pinned to close-time-shifted boundaries** — both parquet grids stamp bar starts, so close-indexed positions are tradable only from a day later; fed raw stamps the helper applied positions a day early, and no verdict had ever run through it.
- **A pre-registered expansion-QA gate guards the mapping in the driver**, and spec `00038` carries the execution-precision amendments (expansion mapping, dense-rank governor days).
- **The win is three-way diversification, not the adaptive weighting** — the fixed-weight counterfactual scored higher, registered as T0019 for a pre-registered trial instead of a post-hoc swap (T0011 resolved).
## 2026-07-10 — iter-081: fixed-weight combination ADOPTED (trial 44) — the deployable candidate simplifies

- **Registry trial 44 — fixed equal sleeve weights are ADOPTED and supersede trial 43 as the deployable candidate**, and the Phase-6 engine gets simpler: no adaptive-weight state to build, journal or reconcile (T0018 names record 44; T0019 resolved).
- **The headline was not blind and the row says so** — it had first been seen as trial 43's verification counterfactual, so the trial's new information is the ratified legs plus registration, pre-registered before the run.
- **The driver reproduced the incumbent's governed series before changing only the weights** — a cross-check gate, so a weight-only claim rests on a weight-only difference.
## 2026-07-11 — iter-088: the §10 portfolio limits as tested code (B4/B3 unblocked)

- **`cli/risk/limits.py` carries the remaining §10 portfolio limits** — the gross-leverage cap, the net-exposure band, and margin level with its self-imposed floor — in the `apply_position_caps` idiom of pure, proportional pre-trade transforms (spec/plan `00046`).
- **Nothing consumes them yet, by design** — the remainder on T0016 is wiring them into whichever short-carrying family harness binds first, in the composition order the module docstring states.
## 2026-08-24 — the frozen holdout stops being the one dataset nothing checks

- **`docs/reference/vouched-dataset-hashes.jsonl`** — a committed sidecar vouches one hash per holdout series, because the freeze process that would emit them has never lived in this repo; its uniform shape needs no per-set manifest knowledge.
- **The read path checks the holdout** — `ObservedReader.read_series` compares every read against the vouched set, which an empty set had made a silent no-op; that data-at-rest guard, not the sync check, is what the gap needed.
- **The fetch check fails closed** — a set that vouches nothing is refused instead of warned about, with `--no-verify` as the explicit escape.
- **`push_hot` verifies before transmitting** — it dry-runs, checks what would leave and refuses unattested content, since a never-overwriting channel cannot correct a node that already holds tampered bytes.
- **The check binds to paths wherever a committed attestation names one** — membership alone passes two swapped series; sets attested only by their own manifest stay on membership deliberately, registered as a waiting consumer on T0132 (T0132 and T0133 both resolved).
