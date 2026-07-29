---
status: resolved
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

## Done so far

Fixed in repo 2026-07-28 on `docs/ops-converge-0728-record` — **option (b)**, the recommended one: a separate series rather than a redefinition.

- `cli/logging/ship.py` publishes `last_cycle_at`, stamped on an idle cycle and on a disposed batch, left alone while pushes are retrying. `last_ship_success_at` keeps its exact former meaning, so no existing consumer shifts under it.
- Seeded at construction, which **eliminates the third state** this topic recorded: the series is present from startup instead of absent until the first ship.
- `cli/obs/metrics.py` exports `zcrypto_logship_last_cycle_timestamp_seconds`; admitted in the capture **and** ops keep-regexes in the same change.
- Three tests pin it: an idle cycle advances it while `last_ship_success_at` stays `None`; a retrying cycle does not advance it; both series are exported distinctly.
- **The open decision is answered by measurement, not judgement**: no Grafana rule reads the old gauge's freshness — before this change, `grep logship infra/grafana/alerts.yaml` returned only the dropped-lines rule (it now also returns the new one added here) — and `tests/test_infra_alert_rules.py`'s exclusion list already records that its staleness is not a fault. Its only consumer was the rollout checklist. A new rule, `zcrypto-logship-worker-stalled` (> 5 min ≈ 300 missed cycles), now carries what that gauge never could.

## Resolution

**Closed 2026-07-29 when the rollout carrying the gauge reached both hosts.**

The remaining sub-item was the abort-signal row, deliberately held until the gauge existed on a host. It now reads `zcrypto_logship_last_cycle_timestamp_seconds`; the old gauge is demoted to corroboration and explicitly marked *not an abort signal*.

**The bake proved the case rather than arguing it.** On `zcrypto-red`, green throughout — 12 pairs flowing, zero errors, `dropped_lines_total` 0 — the two gauges read, at the same instant:

| gauge | staleness |
| --- | --- |
| `last_cycle_timestamp_seconds` | **0 s** |
| `last_success_timestamp_seconds` | **39 min** |

Under the old row that host would have been tripping an abort signal for over half an hour, at a 120 s threshold, while cycling normally every second. That is the false red this topic was opened for, at a magnitude no argument would have conveyed.

Delivered by `sha256:99faf165…ab44` (built from `3540b0bb`): secondary 2026-07-29 00:52:53Z, primary 07:36:13Z. Confirmed arriving in Cloud for both hosts.

## Suggested next steps

- *(ATTENDED, with the image that carries the gauge)* **Rewrite the rollout skill's abort-signal row** to read `zcrypto_logship_last_cycle_timestamp_seconds`, and drop the 120 s threshold that never matched reality. Deliberately not done now: the row describes what an operator reads on a live host, and the running image does not publish this series yet.
- *(ATTENDED, same roll)* Confirm the new gauge and the `zcrypto-logship-worker-stalled` rule are live — the rule reads no data until both the image and the Alloy config land ([[T0109]]), and Grafana shows `inactive` on absent data, which is indistinguishable from healthy.
