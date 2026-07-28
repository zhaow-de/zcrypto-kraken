---
status: open
ripe_when: NOW — the mechanism is read from `cli/logging/ship.py` and confirmed against a live host; nothing waits on an observation. It is deliberately NOT fixed inside the bake it was found in, because changing an abort threshold during a live rollout is the guardrail-weakening this project forbids
---

# The rollout's log-shipping freshness signal reads RED whenever logging is quiet

## Context — what

Found 2026-07-28 while gathering the read-only bake evidence for the capture secondary (`zcrypto-red`, converged 23:58:41Z). The `zcrypto-captures-rollout` skill's abort-signal table lists:

| Signal | Threshold | Where |
| --- | --- | --- |
| `zcrypto_logship_last_success_timestamp_seconds` | stale > ~120 s | `127.0.0.1:9101/metrics` |

Measured on the secondary at 03:45–03:47 UTC: the gauge sat at **2026-07-28T03:38:28Z** — roughly 8 minutes stale — and `zcrypto_logship_shipped_lines_total` was frozen at **2471.0** across three samples 20 s apart. By the table, the bake had tripped an abort signal.

It had not. `cli/logging/ship.py`'s worker loop does `if not self._held: continue` **before** it posts, and `last_ship_success_at` is stamped only inside the `outcome == "ok"` branch. The gauge therefore measures *the last non-empty successful push*, not *the shipper is alive*. A healthy capture daemon is quiet — that is what healthy looks like — so the gauge goes stale in ordinary steady state, on any image, old or new.

Corroborating, same reads: `zcrypto_logship_dropped_lines_total` 0, `shipped_lines_total` 2471 (non-zero and monotone), Alloy `prometheus_remote_storage_samples_failed_total` 0, container `RestartCount` 0, 14 parquet files written in the preceding 3 minutes, zero `quarantined` / `ambiguous` / `merge failed` lines since the converge.

## Why this matters

**A guardrail that reads red in the normal state is worse than no guardrail**, and this one gates an irreversible action. Two failure paths, and the second is the dangerous one:

- An operator following the table **aborts a healthy bake** and rolls back for nothing.
- More likely, having seen it read red on a healthy host once, an operator or a future unattended run **learns to skip the row** — and the row is then silently disabled for the case it exists to catch, a shipper that has genuinely stopped. Nothing in the checklist records that it was ignored.

The same series is scraped into Grafana Cloud (it is in both capture and ops Alloy keep-lists), so any alert rule written against its freshness inherits the defect.

## Findings so far

- The mechanism is in the code, not inferred: `ship.py`'s `_run()` skips the post entirely on an empty buffer, so no timestamp is written.
- `shipped_lines_total` freezing alongside it is the corroboration, not a second symptom: both stop advancing for the same reason.
- The gauge is **absent** until the first successful ship (`if last_success is not None`), so a freshly started daemon publishes no series at all rather than a stale one — a third state the table does not mention.
- Not image-specific, so it says nothing about the candidate digest and is not evidence against the current bake.
- Deliberately not fixed in-place during the bake it was found in: editing an abort threshold mid-rollout is the guardrail-weakening the unattended rules forbid, and `capture-deploys.md` is in the refine-round protected set requiring per-edit sign-off.

## Suggested next steps

- *(decision)* **Pick the honest liveness signal, then rewrite the row.** Candidates, cheapest first: (a) stamp `last_ship_success_at` on an *empty* flush too, so the gauge means "the worker completed a cycle" — one line, but it changes an existing series' meaning, so any rule reading it must be re-checked; (b) publish a separate `zcrypto_logship_last_cycle_timestamp_seconds` and point the abort row at that, leaving the shipping-success gauge alone; (c) drop the freshness row from the table and rely on `dropped_lines_total` plus Alloy's `samples_failed_total`, accepting that a wholly stalled shipper is then invisible until logs resume. (b) is recommended — it separates "the worker is alive" from "Loki accepted something", which are different questions.
- *(autonomous, with whichever option is chosen)* Add the test that pins it: a handler with an empty buffer must still advance whatever the abort row reads, and a handler whose post fails must not.
- *(decision)* **Check whether any Grafana rule reads this series' freshness.** If one does, it has the same false-red and wants the same fix; if none does, record that the only consumer is the rollout checklist.
- *(autonomous)* Note the third state — the series is *absent*, not stale, before the first successful ship — wherever the row lands, since "no data" and "stale" reach an operator differently.
