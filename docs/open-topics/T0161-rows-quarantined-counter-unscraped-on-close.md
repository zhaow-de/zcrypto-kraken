---
status: partial
ripe_when: 'a spill has happened since the deploy -- `increase(zcrypto_capture_rows_quarantined_total{host=~"zcrypto|zcrypto-red"}[6h])` read by value through `infra/scripts/grafana-query.py`, non-zero on the host whose `.held` file is newer than that host''s container start'
---

# The quarantined-rows counter is blind to the spill that happens as the process dies

## Context — what

`zcrypto-capture-rows-quarantined` watches `increase(zcrypto_capture_rows_quarantined_total{host=~"zcrypto|zcrypto-red"}[6h]) > 0` (`for: 15m`, warning). The counter has **two** increment sites in `cli/capture/segment_writer.py`, and they do not behave alike:

- **`_hold()`'s `flush_rows` cap branch** — the live path, reached when one unconfirmed hour piles up `flush_rows` held rows. The process keeps running, the next scrape publishes the step, and `increase()` reads it correctly. **This half of the detector works.**
- **`close()`'s held-spill loop** — the shutdown path. The increment lands in a process that is exiting. Scrapes are 60 s apart and `stop_grace_period` is set nowhere under `infra/`, so Docker's default applies and the process is normally gone before the next scrape. **A value that is never published cannot be read by any expression, absolute or windowed.**

*(Sites are named by function rather than by line: the two coordinates differ between `develop` and any branch that edits this file above `_hold()`, and citing one without its tree is how this topic's first draft went wrong.)*

Spec `00109` D3 excluded this rule from that spec's fix and **already contains the per-site analysis above**, including that the cap site is not start-correlated so D2's argument does not reach it. D3 is the authority here; this topic exists only because D3 says in terms that it registers no topic for the remaining decision.

## Why this matters

The `.held` sidecar is the quarantine for rows the oracle never corroborated. Its own alert summary says the baseline is zero and any firing is a real event. A shutdown-time spill is exactly the case an operator most wants to know about — it is the one correlated with a capture process stopping near an hour boundary, which is also when a re-pin, a converge or a crash happens.

The failure is silent in the worst direction: the rule reads healthy, so the surface asserts coverage it does not have. Same class as [[T0034]], and as the defect `00109` D2 fixed — an instrument that cannot report the thing it names.

Scope, stated so nobody over-reads this: the metric is **not** wholly blind. Cap-site spills are seen. Only the `close()` path is lost.

## Findings so far

- **There is no CRITICAL log line to promote to a detector, and any plan that assumes one is unbuildable.** Measured: `grep -rni critical cli/capture/` returns exactly one hit — a comment in `command.py` about the Loki rule's `level=~"ERROR|CRITICAL"` selector — and `segment_writer.py` contains none. `_write_part` is the sole writer of a `.held` file, and its only logger call is a `logger.exception` on the **failure** branch, which fires when the spill does not happen. A successful spill emits nothing at any level. `00109` D3 states this outright.
- `stop_grace_period` does not appear anywhere under `infra/` — checked, not assumed. Nothing widens the shutdown window today.
- Scrape interval is 60 s (`infra/ansible/roles/capture/files/config.alloy`).
- Registered 2026-09-02 **on the owner's explicit word**, during `00109`'s execution. **Its first draft claimed a converge-free fix existed; pre-push review falsified that, and the correction is recorded below rather than quietly swapped in.**

## Done so far

The code is on `fix/t0161-quarantined-count-persists`; the converge that deploys it is C7's, never this branch's.

- The count is durable across a restart — `fix(capture): the quarantine count survives the process that spilled the rows`. A JSON file at the writer's own root, written after each spill and read at construction. The rejected alternative is recorded there: seeding from the on-disk `.held` inventory decreases when a spill is redeemed, and a decrease is what an `increase()` reads as a counter reset.
- The branch also killed an over-count it would otherwise have made permanent — `fix(capture): a spill that never reached disk was counted, and this branch was about to make it permanent`. `_write_part` swallows its own failure; both increment sites ran unconditionally after it, so a spill that never landed counted, and the durable seed would have carried that phantom into every later process. `_write_part` reports now and both increments are gated on it.
- `infra/runbooks/capture.md`'s shape 3 no longer tells an operator the counter cannot corroborate a `close()` spill.
- One new failure mode is written beside the seed: the gauge is an unlabelled sum, so a writer seeding 0 beside a sibling that seeds a count takes the sum down without reaching zero, which `increase()` reads as a step. A dropped pair or one unreadable state file can page once, and it self-clears.

### Why the read after C7 is a natural spill, not a constructed one

The rollout's own restart cannot show persistence: the outgoing image wrote no state file, so its first post-deploy scrape is 0 by construction, whatever the fix does. The read has to be a spill made by the NEW image and seen after a later restart.

Constructing that spill inside an attended window is a race, measured rather than argued. Rows are held only while their hour is unconfirmed, and `HourOracle.confirmed_hour` confirms as soon as `HOUR_QUORUM` (2) witnesses reach the hour — a second live stream, or the handicapped clock at `CLOCK_WITNESS_MARGIN` (5 min). Probed: with one stream the hour confirms at 5 min past; with two it confirms as soon as the second emits, 2 s into the hour. The capture hosts run many streams, so the window in which a stop produces a spill is **seconds after an hour boundary**, and a stop that misses it spills nothing — a green that proves only that nothing was tested.

So the trigger is the first natural spill after deploy. A deliberately single-stream window would widen it to 5 minutes, but that means stopping a live stream to make a metric readable, which is not worth inducing a capture fault for.

**Deployed 2026-09-07 by C7** (`06998998e876`, revision `c7067af3`): the secondary at 15:55:10Z, the primary at 19:04:29Z, both verified running the digest with RestartCount 0. What remains is a reading, not work.

## Suggested next steps

- Read the counter by value once a spill has happened; the `ripe_when` above carries the query and the freshness check that makes it non-degenerate. The deploy half is discharged: C7 put this build on `zcrypto-red` at 2026-09-07 15:55:10 and on `zcrypto` at 19:04:29, both reading 0 at the restart — which is the value the freshness check exists to distinguish from a real read, because the outgoing image wrote no state file.
