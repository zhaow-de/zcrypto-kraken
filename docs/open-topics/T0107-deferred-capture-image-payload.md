---
status: open
ripe_when: the next capture-image rollout for ANY reason — this is a payload, not a trigger of its own. Also ripe on its own if a resubscribe is ever observed failing in production, since [[T0102]]'s correlation is the thing that would explain it and it is not deployed
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

## Suggested next steps

- *(ATTENDED, at the next capture rollout)* Roll both together. Before the bake, confirm the candidate image contains **both**: T0102's `note_reply` correlation and whichever [[T0106]] fix landed. Verify from the image's own surface, never from the tag.
- *(ATTENDED, with the roll)* Rewrite the rollout skill's abort-signal row to read `zcrypto_logship_last_cycle_timestamp_seconds` and drop the 120 s threshold — [[T0106]]'s remainder, deliberately held until the gauge exists on the host.
- *(ATTENDED, with the roll — REQUIRED, not optional)* **Pass `capture_alloy_digest` so the Alloy config actually installs.** Measured 2026-07-28 ([[T0109]]): the Alloy block is gated `when: capture_alloy_digest is defined` and ordinary converges omit it, so the repo's keep-regex has never reached either host. Rolling the image **without** this leaves both resubscribe counters admitted in the repo and dropped in production — the image ships, the series do not, and the new alert rule reads no data exactly as if nothing were wrong.
- *(ATTENDED, with the roll)* After the primary re-pin, confirm **all five** currently-undelivered series arrive in Grafana Cloud — `zcrypto_capture_resubscribe_errors_total`, `_ack_timeouts_total`, and `zcrypto_logship_last_cycle_timestamp_seconds` from this roll, plus the two it does *not* introduce but the same converge unblocks, `zcrypto_capture_seconds_since_last_book_message` and `zcrypto_capture_venue_status_total`. An unadmitted series is dropped silently at remote-write, and the alert rule watching it stays green forever on no data.
