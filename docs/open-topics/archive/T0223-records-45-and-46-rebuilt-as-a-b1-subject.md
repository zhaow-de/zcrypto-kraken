---
status: resolved
---

# Records 45 and 46 rebuilt as a B1 subject

## Context — what

Records 45 and 46 are B1's trials 1 and 2 (iter-086 and iter-087, both REJECT); their numbers stand in the registry with nothing in the tree that re-derives them. This topic rebuilds them as a research subject under spec 00129's rules, joining its legacy map.

## Why this matters

Their 35 registered metrics each are regression-pinned nowhere, and two live readings rest on them: B2 trial 1's rationale cites record 46's hold-through drift, and T0022's "no live B1 candidate" rests on both. The same class of loss made trial 43's comparison unreproducible until it was recovered from a session transcript (archived T0148).

## Findings so far

- The runners, `b1_trial1_run.py` and `b1_trial2_run.py`, are not recoverable: the July session that wrote them is gone from both workstations.
- A pre-guard loss: both records predate the run_ref guard, and `tests/test_trial_registry_provenance.py`'s `LEGACY_UNCOMMITTED` exempts them.
- The rebuild is legitimate by archived T0125's own test — committed primitives and a construction specified in advance: the overlay is `cli/alpha/b1.py` with `tests/test_alpha_b1.py`, the decision matrix is spec 00045 (the records' `spec_hash`), the driver recipe is plan 00045's prose, and the dataset recipe `cccb8d17` is committed (archived T0065).
- Most of the lost glue is committed since: `b2-funding-derisk`'s arm A is B1's arm A (spec 00128 D5: the three adopted A2 arms, equal weight, 0.006/side), with the kill bar, the head-to-head and `cli/portfolio/record44_legs.py::benchmark_4h_net_of_cost`, the 4h benchmark archived T0148 validated as a substitute.
- Record 45's notes carry discriminating, non-fitted targets — held stamps, scaled boundaries, differing stamps, turnover — for the rebuild to hit.

## Resolution

Delivered by the pull request from `research/00130-b1-records-rebuild` (spec 00130, plan 00130); each of the three suggested steps is answered below, and the owner's two rulings of 2026-10-14 shape the first and add the digests.

- Step 1, the subject: two subjects rather than one, `b1-conditioning` for record 45's conditioning arm and `b1-window-only` for record 46's window-only arm, in `cli/research/subjects.py` (dd15dd0db). Each declares the records' 35 metric keys and seeds (42, 7, 1234) and computes arm A — the three adopted A2 arms, equal weight, 0.006 per side — in the same build as arm B; `b1-conditioning` alone reads `ohlc-15m`, for the vol-state scaler. Neither carries a verdict rule: on the owner's ruling of 2026-10-14 both are evaluate-only, like `record33-combined` and `record44-crossfreq`, standing for their records and never registering, so spec 00045's decision matrix is the reproduction test's check and not a subject's rule.
- Step 2, the run: over dataset `cccb8d17`'s files — the ten EUR assets' `ohlc-full` 240 files, and for record 45 their `ohlc-15m` 15 files as well — each record reproduces 35 of its 35 metrics at the registered precision (spec 00130's measured basis, 2026-10-14), record 45's held stamps, scaled boundaries, differing stamps and turnover among them. Raw equality holds for 14 of record 45's metrics and 12 of record 46's; every other float was rounded by the lost writer (4 decimals unless named, 5 for `dsr_corrected` and `per_period_sharpe_4h`, 2 for the three turnover keys, 9 for `head_to_head_mean_outperf_2016`; ints and per-year dicts exact). No metric differs past that rounding, so no gap is recorded. One anchor stays uncheckable: the arms' elementwise match against the lost iter-074 caches; the arms' and the benchmark's Sharpes reproduce at 4 decimals.
- Step 3, the legacy map: `tests/test_b1_records_reproduce.py` (31bb111e0), marked `data` and gated on `data/ohlc-full` and, for record 45, on `data/ohlc-15m` as well, runs each subject with no window and no as-of and holds its build to the record — the observed block's `compute_hash` pinned, the key set, every metric at its registered precision, and spec 00045's matrix giving the registered reject — beside a case over synthetic metrics, needing no data, that holds all five of the matrix's leaves. `LEGACY_INCUMBENTS` gains `45: "b1-conditioning"` and `46: "b1-window-only"` in the same commit. This test, not spec 00129 D5's exact replay, is the two records' proof, since a writer that rounded stored them.
- The digests, on the owner's word: the second ruling of 2026-10-14 folded the three legacy digests into this branch. `81dc9b44` (the 4h operand of the two records' `cccb8d17`), `ba47e37e` and `45275ebe` recompute from `data/ohlc-full` by the recovered `trial44_write.py`'s manifest recipe, transcribed into `tests/test_legacy_dataset_pins.py` with a data-gated case per digest; `docs/reference/legacy-dataset-pins.jsonl` rates the three `reproduced`, each referent naming the weak digest it rests on — per asset the row count, the first and last stamp and the first and last close, not every byte (f6bbfb9b6) — and spec 00086 D6 is amended in its own text (94ef1e21b).

No record is written or changed: `LEGACY_UNCOMMITTED` still exempts records 45 and 46, whose `run_ref` names the lost drivers.
