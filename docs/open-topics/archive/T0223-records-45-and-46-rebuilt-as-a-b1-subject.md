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

Delivered by the pull request from `research/00130-b1-records-rebuild` (spec 00130, plan 00130), shaped by the owner's two rulings of 2026-10-14.

- Step 1: two evaluate-only subjects, `b1-conditioning` (record 45) and `b1-window-only` (record 46), in `cli/research/subjects.py`; on the owner's ruling neither carries a verdict rule, so spec 00045's decision matrix is the reproduction test's check, not a subject's rule.
- Step 2: over dataset `cccb8d17`'s files each record reproduces 35 of its 35 metrics at the registered precision, so no gap is recorded; the arms' elementwise match against the lost iter-074 caches stays uncheckable.
- Step 3: `LEGACY_INCUMBENTS` maps 45 and 46 to the two subjects; `tests/test_b1_records_reproduce.py`, data-gated, is their proof in place of spec 00129 D5's exact replay, since a writer that rounded stored them.
- The digests, on the owner's second ruling: `81dc9b44`, `ba47e37e` and `45275ebe` recompute from `data/ohlc-full` as weak digests; `docs/reference/legacy-dataset-pins.jsonl` rates them `reproduced` and spec 00086 D6 is amended in its own text.

No record is written or changed: `LEGACY_UNCOMMITTED` still exempts records 45 and 46, whose `run_ref` names the lost drivers.
