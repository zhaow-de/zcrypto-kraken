---
status: partial
ripe_when: the resubscribe-robustness remainder is far less pressing now that the desync *cause* is fixed (desyncs should fall to ~zero); revisit at the next attended capture-maintenance window, or immediately on a recurrence of a stuck-pair desync
---

# Capture daemon — robust book-desync recovery (retry / ack-correlated resubscribe)

## Context — what

The capture daemon recovers from a book checksum desync by calling `resubscribe_book(pair)`, which (after the iter-039 fix, `fix/t0003-resubscribe-desync`) **unsubscribes then re-subscribes** to force a fresh snapshot that rebuilds the book and clears `desynced`. But that recovery is a **single, fire-and-forget attempt**: both WS frames are sent with no correlation to Kraken's responses, and the desync handler only resubscribes on the `not was_desynced` **transition** (deliberately, to avoid the resubscribe storm that trips Kraken's rate limit). So if the one recovery attempt does not take — the forced snapshot itself fails its checksum, or the `subscribe` races ahead of the `unsubscribe` server-side and is rejected — `desynced` stays `True`, the transition guard never re-fires, and the pair is stuck desynced exactly as in the original incident, just one level removed.

## Why this matters

The ≥7-day clean-run exit bar wants <0.1 % gap time. A recovery path that can silently fail on its single attempt is a latent source of long, unrecovered gaps on the high-activity pairs (the ones most prone to desync). Kraken's docs give **no guarantee** that a same-connection unsubscribe-then-subscribe pair is processed strictly in order, so the current fix is *plausibly* but not *provably* race-free. The failure is not fully silent — an open gap withholds healthcheck pings, so the dead-man's switch eventually pages a human — but "page a human" is not "self-heal", and it is the same coarse recovery the daemon had before, for this residual failure class.

## Findings so far

- Surfaced by the iter-039 whole-branch review of the desync hotfix (reviewer: Claude Sonnet 5). The hotfix itself is a strict improvement (a bare re-subscribe could *never* heal; unsubscribe-then-subscribe heals on the common path) and was approved to merge/deploy; this topic is the residual robustness gap it does not close.
- The iter-039 fix also added `unsubscribe_ack`/`unsubscribe_error` classification + an `unsubscribe error:` log line, so a **rejected** unsubscribe is now at least visible in the logs (it previously fell through to `"other"` and was dropped silently) — but nothing yet *acts* on that rejection.

- **2026-07-09 production evidence (two independent probes): the iter-039 fix heals 100 % of desyncs (median ≈ 0.1 s, tail to 1.8 s) — no stuck pair has ever occurred on the current deployment.** Morning check (09:23 UTC, session `70758521…`): **75 desyncs / 75 gap-starts / 75 gap-ends** since container start (2026-07-08 20:33 UTC); zero `unsubscribe error` / `subscribe error` / `Already subscribed`; heal latency over that 75-event subsample: min 2 ms / median 123 ms / max 750 ms; the running container verified (via `docker exec … grep`) to contain the `f3de966` unsubscribe-then-subscribe fix. Live probe (15:44 UTC): **159/159 healed** — BTC 85, ETH 34, DOGE 22, ADA 15, XRP 3 — total `checksum_resync` gap **31.7 s over ~19.2 h** (aggregate ≈ 0.005 %; worst pair BTC 0.031 % — comfortably under the §12 < 0.1 % gap-time bar); all 10 pairs' segment files fresh ≤ 5 min; 10/10 WS reconnects succeeded on attempt 1. Full-log heal latency (all 159): min 1 ms / median 98 ms / **max 1.802 s — 5 heals (3.1 %) exceeded 1 s, every one in the 13:53–15:28 UTC window**, i.e. the latency tail worsened alongside the afternoon rate spike.
- The container's `RestartCount=38` and the 38 `TimeoutError: timed out during opening handshake` tracebacks in its log are **all confined to the 2026-07-08 20:33–21:31 UTC deploy-evening window** (0 since) — the historical crash-loop, resolved that evening; not a live issue.
- **New observation — the desync *rate* is elevated and volatility-correlated**: ~6/hr in the morning window rising to **~19/hr over 12:00–15:44 UTC** (71 events), concentrated on the high-activity pairs, with occasional bursts of 2–3 re-desyncs within ~150 ms of a fresh snapshot (mild thrash; every one healed). Recovery works; the *frequency* — and its co-moving latency tail — is now the open question. (169 consecutive first-attempt recoveries — 159 desync heals + 10 WS reconnects — are reassuring evidence, not proof; the single-attempt structural risk this topic tracks remains.)
- **Cross-ref — spec `00050`'s redundant capture materially de-risks this topic's parked remainder (2026-07-17).** A pair left stuck desynced after a failed one-shot resubscribe presents as a *silent stream on one host* — the exact outage shape the reconciler's **whole-window book splice** heals from the second host: both hosts' books are 100 % CRC-valid, and per-connection message loss cannot be microsecond-synchronised across independent connections, so a **host-local** stuck pair is coverable (spec `00050` §Constraints 1 + 4, which calls this out explicitly). This covers the *data-loss* consequence in the canonical archive; the *live recovery-robustness* work below (retry / ack-correlated resubscribe / reconnect escalation) remains this topic's own — a healed archive is not a healed live book.

## Done so far — the desyncs were OUR bug, and it is fixed (2026-07-13)

**The root-cause question this topic carried — *"why do the high-activity pairs fail checksums this
often — `book.py`'s checksum window vs Kraken's update coalescing at depth-100?"* — is ANSWERED, and
it was neither Kraken nor the network. It was `book.py`.**

`OrderBook` never pruned to the subscribed depth. Kraken only sends deltas for levels **inside** the
depth-N window; a level retained beyond it is one Kraken has stopped reporting, so it goes stale (its
quantity changes, or it is cancelled, and we never hear). When the window later shifts back, that
stale level re-enters our top-10 as a **phantom** and the checksum fails. The daemon calls that a
"desync", resubscribes for a fresh snapshot, and immediately begins re-accumulating.

**Measured, on three independent capture hosts** (the primary plus two throwaway hosts in *different*
datacenters, all running the identical image against the same feed):

| | book size vs Kraken's 100 | CRC failures replaying one real captured hour | with the depth-prune fix |
|---|---|---|---|
| primary (Frankfurt) | **810 bids / 468 asks** | **482** | **0** |
| host B (Frankfurt-2) | 810 / 470 | 117 | **0** |
| host C (Amsterdam) | 745 / 438 | 398 | **0** |

Two things this proves beyond doubt:

- **It is deterministic and ours.** All three hosts began diverging at the *identical microsecond*
  (`14:26:12.365460`, and again at `14:59:10.113215`). Loss cannot be microsecond-synchronised across
  three independent WebSocket connections in two cities — the same message makes every host's book fail.
- **No data was ever lost.** The archived *rows* are Kraken's wire messages and they are complete:
  replaying them with the fix yields a **perfect book, zero failures**. Only the *in-memory*
  reconstruction was wrong. So the archive is sound, and the ~200 "desyncs"/day (and the 0.005 %
  "gap time" they contributed to the §12 exit bar) were **self-inflicted, not real loss**.

**Fix:** `OrderBook` now takes a required `depth` and prunes each side to it after every
snapshot/update, keeping the book congruent with Kraken's window (`cli/capture/book.py`). Two TDD
tests cover it, including the exact phantom-resurfacing scenario. `depth` is deliberately required —
defaulting it would silently reintroduce this.

**Not yet deployed** — ships with the next capture-image rollout.

## Suggested next steps

- **Investigate the underlying desync *rate*** (registered 2026-07-09 from the 09:24 UTC session's dangling follow-up question, per the deferral rule): why do the high-activity pairs fail checksums this often — `book.py`'s checksum window vs Kraken's update coalescing at depth-100? Quantify rate vs message volume from the logs/captured segments; assess whether a different depth or checksum-window handling reduces it. The read-only analysis (logs + code + captured data) is autonomous-safe; any daemon change still deploys via the attended window above.
- **(autonomous)** Make recovery robust to a failed single attempt. Options to weigh: (a) retry `resubscribe_book` with backoff while a pair remains desynced past a grace period / N updates (bounded, so it can't re-storm the rate limit); (b) `req_id`-correlate the resubscribe — wait for the `unsubscribe_ack` before sending the `subscribe`, and treat an `unsubscribe_error`/`subscribe_error` as a signal to retry; (c) escalate to a full reconnect (which re-subscribes everything with fresh snapshots) if a pair stays desynced beyond a threshold. TDD on the WS-client/handler with a fake connection that simulates a rejected/failed recovery.
- **(verification, pending a natural event)** The fix is now **deployed** (2026-07-08, via the CI GHCR image — see T0003 Incident); a 14-min watcher saw no natural desync, so the live self-heal is still unobserved. Watch the **first natural desync** self-heal on the live feed (a `checksum desync … resubscribing` followed by the pair returning to sync, **no** "Already subscribed"/"unsubscribe error") — that is the only real test of the Kraken unsubscribe→subscribe ordering. If it does **not** cleanly self-heal, this topic jumps in priority. The healthcheck dead-man's switch guards it meanwhile.
