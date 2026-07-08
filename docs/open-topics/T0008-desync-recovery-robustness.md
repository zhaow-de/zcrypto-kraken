---
status: open
---

# Capture daemon — robust book-desync recovery (retry / ack-correlated resubscribe)

## Context — what

The capture daemon recovers from a book checksum desync by calling `resubscribe_book(pair)`, which (after the iter-039 fix, `fix/t0003-resubscribe-desync`) **unsubscribes then re-subscribes** to force a fresh snapshot that rebuilds the book and clears `desynced`. But that recovery is a **single, fire-and-forget attempt**: both WS frames are sent with no correlation to Kraken's responses, and the desync handler only resubscribes on the `not was_desynced` **transition** (deliberately, to avoid the resubscribe storm that trips Kraken's rate limit). So if the one recovery attempt does not take — the forced snapshot itself fails its checksum, or the `subscribe` races ahead of the `unsubscribe` server-side and is rejected — `desynced` stays `True`, the transition guard never re-fires, and the pair is stuck desynced exactly as in the original incident, just one level removed.

## Why this matters

The ≥7-day clean-run exit bar wants <0.1 % gap time. A recovery path that can silently fail on its single attempt is a latent source of long, unrecovered gaps on the high-activity pairs (the ones most prone to desync). Kraken's docs give **no guarantee** that a same-connection unsubscribe-then-subscribe pair is processed strictly in order, so the current fix is *plausibly* but not *provably* race-free. The failure is not fully silent — an open gap withholds healthcheck pings, so the dead-man's switch eventually pages a human — but "page a human" is not "self-heal", and it is the same coarse recovery the daemon had before, for this residual failure class.

## Findings so far

- Surfaced by the iter-039 whole-branch review of the desync hotfix (reviewer: Claude Sonnet 5). The hotfix itself is a strict improvement (a bare re-subscribe could *never* heal; unsubscribe-then-subscribe heals on the common path) and was approved to merge/deploy; this topic is the residual robustness gap it does not close.
- The iter-039 fix also added `unsubscribe_ack`/`unsubscribe_error` classification + an `unsubscribe error:` log line, so a **rejected** unsubscribe is now at least visible in the logs (it previously fell through to `"other"` and was dropped silently) — but nothing yet *acts* on that rejection.

## Suggested next steps

- **(autonomous)** Make recovery robust to a failed single attempt. Options to weigh: (a) retry `resubscribe_book` with backoff while a pair remains desynced past a grace period / N updates (bounded, so it can't re-storm the rate limit); (b) `req_id`-correlate the resubscribe — wait for the `unsubscribe_ack` before sending the `subscribe`, and treat an `unsubscribe_error`/`subscribe_error` as a signal to retry; (c) escalate to a full reconnect (which re-subscribes everything with fresh snapshots) if a pair stays desynced beyond a threshold. TDD on the WS-client/handler with a fake connection that simulates a rejected/failed recovery.
- **(verification, pending a natural event)** The fix is now **deployed** (2026-07-08, via the CI GHCR image — see T0003 Incident); a 14-min watcher saw no natural desync, so the live self-heal is still unobserved. Watch the **first natural desync** self-heal on the live feed (a `checksum desync … resubscribing` followed by the pair returning to sync, **no** "Already subscribed"/"unsubscribe error") — that is the only real test of the Kraken unsubscribe→subscribe ordering. If it does **not** cleanly self-heal, this topic jumps in priority. The healthcheck dead-man's switch guards it meanwhile.
