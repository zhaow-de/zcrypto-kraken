---
status: partial
ripe_when: either alert firing on a REAL stuck pair — and the alert path itself is now drill-validated (2026-07-27), so a firing is trustworthy evidence rather than an unproven signal. Alternatively an owner ruling to build or drop the recovery robustness unconditionally
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

**Deployed 2026-07-14** — the depth-prune fix (`71b72e9`, 2026-07-13) rode the T0036 image (`sha256:63708539…`, built 2026-07-14 03:51 UTC), running on both capture hosts since.

## Done so far — the alert leg (2026-07-26)

**This topic's trigger is now evaluated continuously instead of by hand.** Two rules key on it: *Capture · book desync stuck on a pair* (`min_over_time(zcrypto_capture_book_desynced[15m]) > 0.5`, per pair, paging at 20 min) and *Capture · book resubscribe rate re-elevating* (`increase(...[1d]) > 1.5`, per host).

**`min_over_time`, not the `max_over_time` this topic's own `ripe_when` proposed.** `max` fires on *any* desync inside the window, including the transient the daemon self-heals 234/234 times; `min` requires the pair to have been desynced for the entire window, which is the stuck shape — desynced past its single resubscribe — that the topic actually cares about.

**The `> 1` threshold the topic proposed would have misfired**, caught by review before deploy: `increase()` extrapolates to the window edges, so a *single* increment returns ~1.0007 for any nonzero sample offset. One genuine self-healed venue desync would have paged, asserted a re-elevating rate that was not happening, and stayed firing for a full day. Threshold is 1.5.

**Writing the guard test found four more unwatched fault signals**, so the fix generalized:

- `zcrypto_capture_disk_watermark_breached` — the worst of them. A breach makes the book and trade handlers `continue`/`return` past the writers, so incoming L2 and trades are **discarded**, unbackfillable, while the only signal is the same saturated dead-man. Now `critical`.
- `zcrypto_capture_rows_quarantined_total`, `zcrypto_logship_dropped_lines_total` — measured baseline zero over 7 d, so any nonzero value is a real event.
- `node_scrape_collector_success` — a failed collector makes its whole family absent, and NoData maps to OK on this fleet, so it silently disarms every rule keyed on those series.

**`zcrypto_capture_reconnects_total` was deliberately NOT alerted**, and the measurement is why: 32–35 reconnects per host per week is baseline, not a fault, so a naive rule would page ~5×/day. [[T0035]]'s trigger is a counter *reset* correlated with a `process_start_time_seconds` jump — that needs the correlation, not a raw count, and stays that topic's work.

**The guard is derived, not hand-listed** — 46 admitted series minus 38 explicit exclusions, each carrying its reason. A hand-list cannot catch the *next* unwatched metric, which is the mechanism that let these sit for two months.

## The alert leg is drill-validated (2026-07-27)

The alert shipped 2026-07-26 but had never fired, so nothing established it *would*. Injecting `zcrypto_capture_book_desynced{pair="DRILL"} 1` as a `.prom` on the secondary — through the textfile transport built the same day — exercised the whole path:

| step | observed |
| --- | --- |
| injected 10:29:37 | series reached Grafana Cloud as `zcrypto-red/DRILL` |
| 10:31:00 | rule instance `Pending` |
| 10:36:00 | `Alerting`, Slack paged, summary naming the pair |
| all 24 real pair instances | stayed `Normal` throughout — the rule discriminates |
| `.prom` removed 10:40:33 | instance resolved on its own |

**A caveat that matters for reading a real firing.** The drill fired in 6.4 min, but that is *not* the real latency: `min_over_time` aggregates only the samples present, so a brand-new series satisfies it immediately, leaving just the 5 min hold. A genuine desync flips an **existing** series from 0 to 1, so its 15 min window holds zeros and the summary's stated ~20 min is correct. The drill proves the wiring, not the timing.

**What this does NOT close.** No desync occurred, so `resubscribe_book` never ran and the single-attempt recovery this topic is actually about remains unexercised. The safety net is proven; the defect behind it is not. Deliberately scored that way rather than counted as a validation that did not happen.

## Suggested next steps

- ~~Investigate the underlying desync *rate*~~ **(answered by the root cause above, 2026-07-13):** the ~200/day rate WAS the unpruned book resurfacing phantom levels — replaying a real hour went 482/117/398 CRC failures → **0** with the depth prune, so there is no residual rate question to investigate (any post-fix desync is a genuine venue/network event, handled below).
- **(autonomous — consciously re-deferred 2026-07-19)** Make recovery robust to a failed single attempt. Options to weigh: (a) retry `resubscribe_book` with backoff while a pair remains desynced past a grace period / N updates (bounded, so it can't re-storm the rate limit); (b) `req_id`-correlate the resubscribe — wait for the `unsubscribe_ack` before sending the `subscribe`, and treat an `unsubscribe_error`/`subscribe_error` as a signal to retry; (c) escalate to a full reconnect (which re-subscribes everything with fresh snapshots) if a pair stays desynced beyond a threshold. TDD on the WS-client/handler with a fake connection that simulates a rejected/failed recovery.
- ~~**(verification, pending a natural event)** … a 14-min watcher saw no natural desync, so the live self-heal is still unobserved~~ **— superseded, and it was already superseded when written.** The Kraken unsubscribe→subscribe ordering question this bullet parked is empirically settled **234/234** by the two 2026-07-09 probes recorded above (75/75 and 159/159 first-attempt heals, zero `unsubscribe error`/`subscribe error`/`Already subscribed`). It is left struck rather than deleted because it read as an open question for two weeks after the evidence landed.

- ~~**(autonomous, ripe NOW) Alert on the stuck shape**~~ — **DONE 2026-07-26**, and it grew: the guard test written for it found *four more* unwatched fault signals, so six rules landed rather than one. Detail in `## Done so far`.

- **Why that alert matters more during an unattended stretch than the "loud" framing suggests.** A stuck pair does not merely withhold one pair's data: `gap_monitor.is_healthy()` returns False while **any** pair has an open gap, and the healthcheck loop pings only when it is True — so **one** stuck pair silences that host's dead-man for **all** pairs. The hc.io watchdog then fires and *stays* fired, and while it is saturated a later, worse failure on that host produces no new page. Self-heal by restart is also not guaranteed to arrive: [[T0027]]'s ruling turns off automatic reboots on exactly these two hosts. Data loss stays covered (the 00050 splice heals a host-local silence, and both BTC-quoted legs are two-host after the secondary converge) — the exposure is **operational blindness**, and its cost grows with the length of the unattended window.

- **Trigger evaluated 2026-07-23 — NOT fired, with the window stated.** `zcrypto_capture_book_desynced` = 0 for every pair on both hosts, and `zcrypto_capture_resubscribes_total` = **0** on both. Bounded claim: these counters reset with the process, so this covers 17.6 h on `zcrypto-red` (up since 2026-07-22 21:45 UTC) and 2.2 h on `zcrypto` (recreated 13:08 UTC for [[T0092]]) — it is **not** evidence of zero desyncs since the 07-13 root-cause fix, only that none is open or recent. Blast radius is now **12** pairs, not 10, and the two BTC-quoted legs have no desync observation history at all.
