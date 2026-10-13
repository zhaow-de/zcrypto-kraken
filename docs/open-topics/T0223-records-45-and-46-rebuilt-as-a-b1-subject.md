---
status: open
ripe_when: "an activity: spec 00129's pull request merges into develop — check: `git fetch -q origin && git log origin/develop --first-parent --oneline --grep 'docs/00129-trial-provenance' | wc -l` prints at least 1"
---

# Records 45 and 46 rebuilt as a B1 subject

## Context — what

Records 45 and 46 are B1's trials 1 and 2 (iter-086 and iter-087, both REJECT), registered on 2026-07-11 by scratch runners, `b1_trial1_run.py` and `b1_trial2_run.py`, that no workstation still holds. Their numbers stand in the registry with nothing in the tree that re-derives them. This topic rebuilds them as a research subject under spec 00129's rules, joining its legacy map.

## Why this matters

Their 35 registered metrics each are regression-pinned nowhere, and two live readings rest on them: B2 trial 1's rationale cites record 46's hold-through drift, and T0022's "no live B1 candidate" rests on both. The same class of loss made trial 43's comparison unreproducible until it was recovered from a session transcript (archived T0148).

## Findings so far

- Registered on the owner's word of 2026-10-13 ("register T0223 for the 45/46 rebuild"), after the word "schedule the 45/46 rebuild after 00129".
- The runners are not recoverable: the July session that wrote them is gone from both workstations, read on 2026-10-13 by the old workstation's session (its four surviving transcripts carry no write of either file).
- A pre-guard loss: both records predate the run_ref guard of 2026-08-03, and `tests/test_trial_registry_provenance.py`'s `LEGACY_UNCOMMITTED` (range 33–46) exempts them; record 47 already names committed code.
- The rebuild is legitimate by archived T0125's own test — committed primitives and a construction specified in advance: the overlay is `cli/alpha/b1.py` with `tests/test_alpha_b1.py`, the decision matrix is spec 00045 (the records' `spec_hash`), the driver recipe is plan 00045's prose, and the dataset recipe `cccb8d17` is committed (archived T0065).
- Most of the lost glue is committed since: `b2-funding-derisk`'s arm A is B1's arm A (spec 00128 D5: the three adopted A2 arms, equal weight, 0.006/side), with the kill bar, the head-to-head and `cli/portfolio/record44_legs.py::benchmark_4h_net_of_cost`, the 4h benchmark archived T0148 validated as a substitute.
- Discriminating, non-fitted targets in record 45's notes: 5,506 held stamps, 4,167 scaled boundaries, 7,132 differing stamps; turnover 146.19 → 195.53.

## Suggested next steps

- Build the B1 subject under spec 00129's rules — its declared metric keys, spec 00045's decision matrix as its verdict rule, arm A computed in the same run — for record 45's conditioning arm and record 46's window-only arm.
- Run it over dataset `cccb8d17`'s files: each record's 35 metrics reproduce bit for bit, or the first one that differs is measured and the gap recorded in the topic before anything is claimed.
- On a full reproduction, add the subject to spec 00129's legacy map with a data-gated replay of both records.
