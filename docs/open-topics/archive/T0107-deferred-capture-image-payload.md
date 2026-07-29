---
status: resolved
---

# The deferred capture-image payload: two fixes waiting on one bake

## Context — what

Two completed-in-repo capture-daemon changes are **not deployed**, and both are waiting on the same thing: a capture-image rollout, which costs a secondary converge, an event-coverage bake of ≥3 rotation hours, and a primary re-pin that restarts live capture.

1. **[[T0102]]'s `req_id` correlation** — resolved and archived, code merged, image never rolled. A failed resubscribe still leaves no correlated trace in production.
2. **[[T0106]]'s log-shipping freshness fix** — **built 2026-07-28**: a new `zcrypto_logship_last_cycle_timestamp_seconds` gauge plus the `zcrypto-logship-worker-stalled` rule. It is a `cli/logging/ship.py` change, so it ships in the same image; the rollout skill's abort-signal row is rewritten to point at it **at the roll**, not before, since the running image does not publish it yet.

Registered 2026-07-28 because neither had a git-tracked home. T0102 is archived, T0106 tracks only its own design, and the deferral's only record was `docs/memo.local.md` — which is **gitignored**, while a committed changelog asserted it was the durable record. That is exactly what `open-topics.md` forbids, and this file is the correction.

## Why this matters

**Not urgency — economics.** A capture rollout ran 2026-07-27/28 (secondary 23:58:41Z, primary 08:04:29Z), and neither change was in it. Rolling again immediately would buy a second live capture restart and a multi-hour bake for an observability improvement. Rolling them *together*, whenever the next image goes out for any reason, costs nothing extra.

The failure this file prevents is the one that already nearly happened: two parked items in two different places, each invisible from the other's context, so the next rollout carries one and rediscovers the other months later.

## Findings so far

- The 2026-07-28 capture image (`sha256:828128f8…4224`) was built from `3b9c1d12` and carries [[T0008]]'s ladder + [[T0101]]'s staleness window. T0102's correlation is **correctly absent** from it — that rollout predates the merge.
- T0102's counters were exported and given an alert rule on the same branch as this registration, so the payload now also carries `zcrypto_capture_resubscribe_errors_total` / `_ack_timeouts_total` and the `zcrypto-capture-resubscribe-failing` rule. **The rule will read no series until this image ships** — Grafana shows it `inactive` on absent data, which is indistinguishable from healthy.
- Rollout mechanics are the `zcrypto-captures-rollout` skill; nothing here changes them.

## Resolution

**The payload rolled 2026-07-29** as `sha256:99faf16514e3…ab44`, built from `3540b0bb`. Secondary `zcrypto-red` 00:52:53Z, primary `zcrypto` 07:36:13Z after a 6 h 43 m bake — three full rotation hours required, prune in the **strong** form (`deleted=210`), every abort signal clear, `continuity.py` on the pulled copy 0 missing / 0 truncated with the worst stream at 0.0123% against the 0.1% bar.

Both payload items were verified **from the image's own surface, never the tag**: [[T0102]]'s `req_id` correlation in `ws_client.py`, and [[T0106]]'s `last_cycle_at` plus its exported gauge.

**All five previously-undelivered series now arrive in Cloud** — the count this topic exists to make true:

| series | series count |
| --- | --- |
| `zcrypto_capture_seconds_since_last_book_message` | 24 (12 pairs × 2 hosts) |
| `zcrypto_capture_venue_status_total` | 2 |
| `zcrypto_capture_resubscribe_errors_total` | 2 |
| `zcrypto_capture_resubscribe_ack_timeouts_total` | 2 |
| `zcrypto_logship_last_cycle_timestamp_seconds` | 2 |

The economics this topic was opened on held: one bake carried both deferred items plus the Alloy config, rather than three separate live-capture restarts.

**The step that would have made it fail silently**, and did have to be run by hand on both hosts: `docker compose up -d` after the converge ([[T0109]]). Before it, the primary's Alloy read host `fda087ea…` against container `e89f00d1…` — the handler had reloaded a stale inode and returned 200. Without that step this roll would have reported green and delivered two of the five.

## Suggested next steps

*(All discharged — see `## Resolution`. The rollout ran 2026-07-29.)*

- ~~Roll both together, verifying the candidate from the image's own surface~~ — done; revision label, T0102's correlation and T0106's gauge all read from the image.
- ~~Rewrite the rollout skill's abort-signal row~~ — done ([[T0106]]).
- ~~Pass `capture_alloy_digest` so the Alloy config installs~~ — done, and followed by the container recreate [[T0109]] showed it also needs.
- ~~Confirm all five undelivered series arrive in Cloud~~ — done; all five present on both hosts.
