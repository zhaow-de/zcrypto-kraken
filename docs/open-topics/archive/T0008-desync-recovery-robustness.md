---
status: resolved
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

## Resolution

**Resolved 2026-07-27.** Recovery no longer depends on its first attempt succeeding: a bounded retry ladder, escalating once to a full reconnect, then stopping. Spec `00072`; built and drill-validated the same day.

**The design turns on one thing** — retries are driven by desync **state**, never by protocol responses. A snapshot that fails its own checksum produces no error frame: Kraken is satisfied, the protocol succeeded, and the book is still wrong. Only "still desynced N seconds later" can see that. It is also why `req_id` correlation is *not* a substitute — it prevents the race (cause 2) but is structurally blind to the bad snapshot (cause 1). Registered separately as [[T0102]] for its observability value.

**The ladder, measured against real Kraken rather than asserted:**

| rung | drill A (heals) | drill B (exhausts) |
| --- | --- | --- |
| 1 — transition resubscribe | fires **once**; the guard holds, no storm | same |
| 2 — retry ×3 | +23.4 s, +5.002 s, +10.004 s | same |
| 3 — reconnect | not reached; pair healed first | fires at **+20.002 s**, `force_reconnect` reaches `stream()` |
| terminal | — | **no second escalation over the following ~4 min** |

`retries=3, escalations=1, restarts=0`. Desync→escalation **58.3 s** against the spec's predicted ~55 s, inside the ~90 s dead-man budget — the first real timing for this path since the 2026-07-13 root-cause fix took desyncs to zero.

**Review found the bound did not hold, and the escalation itself was the leak.** `note_recovered` cleared the escalation record, so the cooldown bound only a *continuously* desynced pair — while the likeliest healer of an escalated pair is that escalation's own reconnect. Simulated against the real ladder before the fix: a pair desyncing every 10 min escalated **6×/hour against the intended 1**, a flapping pair **51×/hour** — **72** and **~610** reconnects/hour fleet-wide across 12 pairs, against 12. (Ceilings from the state machine, which has no clock and so never charges the reconnect's own downtime; the 6:1 over-run is the finding.) Neither drill could have caught it: drill A never escalated, so there was no record to erase, and drill B held the pair desynced throughout — the one shape where the old code was correct.

**The terminal state was the part worth drilling.** A ladder that cycles turns one stuck pair into a reconnect loop, and every reconnect drops all 12 pairs — strictly worse than the defect. No unit test can establish that in a live process; drill B did.

**Two drill runs failed first, both in the instrument.** Faking only the return value left the book healthy, so the transition guard re-fired rung 1 twice in 0.5 s — the very storm it exists to prevent — while the state-reading recovery loop never engaged. Setting `book.desynced` too, but on a book whose data was valid, let the next update heal it in milliseconds, before the grace elapsed; the daemon stayed healthy and kept writing, which is exactly what made it look like a pass. The knob's unit became a **duration**, because a pair is stuck for a length of time. Generalised in [[T0049]]: a fault injector that does not move the state the system keys on simulates a different fault, convincingly.

**The alert leg**, shipped 2026-07-26 and drill-validated the same morning, remains the escalation path once the ladder gives up — it is what carries a pair the ladder cannot fix.

**Not deployed by this topic.** Capture-daemon code on the unbackfillable path reaches the fleet only via an image build, the ≥24 h secondary canary bake, then the primary re-pin (`capture-deploys.md`). Merged and unrolled is the intended state here; the deploy is its own attended step.
