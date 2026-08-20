---
status: resolved
---

# Capture receives venue status but never archives it, so a past hour's status is unknowable

## Context — what

`cli/capture/command.py` handles Kraken's `status` category: it logs the message (`venue status system=%s version=%s effective_time=%s`) and counts it into `zcrypto_capture_venue_status_total{system=...}`. It does **not** write it to a segment. Nothing in the archive records what the venue said its own state was at a given moment.

The reconciler runs at least two hours behind the hour it settles, and Kraken's public `SystemStatus` endpoint reports *current* state only — there is no historical status API. So a reconciler that wants to know whether the venue was in `maintenance` during hour H has no source at all: not the archive, and not the live endpoint.

## Why this matters

**The premise this topic was opened on is false, and the correction is the point.** Three different Kraken sources were collapsed into one phrase, "venue status":

| | Source | Who consumes it here | Readable retroactively? | 2026-08-06 | 2026-08-20 |
| --- | --- | --- | --- | --- | --- |
| A | WebSocket `status` channel | `cli/capture/command.py` — a log line plus `zcrypto_capture_venue_status_total` | only as a Prometheus series or a Loki log line | **announced** | **announced** |
| B | REST `SystemStatus` | `cli/engine/venue.py`, the execution gate | **no — current state only** | unreachable | unreachable |
| C | `status.kraken.com` incident page | a human, by eye | n/a | posted | no incident |

[[T0143]] recorded **C** correctly and narrowly. Spec `00096` promoted that into a claim about **A**, and this topic was opened on the resulting asymmetry — that venue status and cross-host agreement each catch what the other misses. They do not. On 2026-08-20 the WS channel carried the same `maintenance` → `cancel_only` → `post_only` ladder as 2026-08-06, on **both** capture hosts, and `Capture · Kraken reports the venue is not online` fired six instances at 07:07–07:16Z. Status did not miss 2026-08-20; the status *page* did, and that is a different source.

So status **dominates** cross-host on the two known episodes rather than complementing it, and there is no "uncovered half" to register. What remains true is narrower: the only *retroactively readable* form of venue status is the public endpoint, which reports current state only — so a reconciler running two hours or more behind still cannot consume it. That residue is what the Resolution below disposes of.

## Findings so far

- Measured from the live ledger (`/mnt/zhao-crypto/capture-reconciled/reconcile-ledger.jsonl`, 99 records): four `both_streams_silent` records exist, totalling **21,887.369457 s** — which is the **entire** `residual_gap_seconds_total` today (no `total_loss`, no splice residual contributes).
- 2026-07-13 (2,661.788740 s) and 2026-07-27 (2,385.847992 s) book a single window each, so they have no interior span and read `undetermined` under `00096`. 07-13 was a Kraken WS 503 followed by a capture-side restart clobber ([[T0035]] / [[T0036]]) — a **capture defect**, and reading it `undetermined` rather than `venue_silent` is the correct true negative.
- The status counter's own comment records the read: series exist only for values actually seen, so the presence of anything other than `online` is itself the signal. It is a counter in Prometheus, not a row in the archive.
- Making the reconciler query Prometheus was considered and rejected while designing `00096`: a monotonic, unwalkbackable ledger must not depend on soft telemetry that may be unavailable or retention-expired at read time.

- **2026-08-06's two dark windows are adjacent in the ledger** — `07:01:02.604269 → 07:15:07.607301` and `07:15:07.607301 → 07:15:39.761602`, the first ending exactly where the second begins. The interior span `00096` reads is therefore a **zero-length instant**, and no archived status row could fall inside it.
- **The `status` frame carries no venue timestamp.** `cli/capture/command.py` reads only `system`, `version` and `effectiveTime` from it — unlike a book or trade frame, which carries `entry["timestamp"]`. And `effective_time` has been observed only as `None` ([[T0105]]). An archived status row could therefore hold nothing but **local receipt time**.

## Resolution

**Resolved 2026-08-20 as a measured refutation** — `open-topics.md` names that a valid disposition ("fixed, **measured non-issue**, or consciously dropped with the reason written"). Both halves are disposed of, on different grounds.

**The premise is refuted.** The WS `status` channel announced **2 of 2** known venue episodes since counting began; cross-host classifies 1 of 2. There is no complementary half, so the motivation this topic was opened on does not survive.

**The remedy is consciously dropped, on three reasons — two of them measured:**

1. **The mechanism cannot absorb it.** 2026-08-06's interior span is a zero-length instant (above), so no status row could land in it. Feeding status into `00096` would not be an edit to `classify_dark_episode`; it would be a second, independent rule pointed in the one direction D3 forbids.
2. **An archived row would not inherit what makes `00096` sound.** The discriminator works because `ts` is Kraken's *payload* timestamp, so two independent hosts agree by construction. A status row could carry only local receipt time, on which two hosts agreeing proves nothing. This answers this topic's own second next-step, in the negative, from code already in the repo.
3. **No episode class gains information.** An announced episode is already on three surfaces — the counter, the capture log's ladder with per-transition times, and `00096` D6's hygiene-map row. An unannounced episode would leave the archived stream empty. Against that: a new fleet-wide segment kind, the pull/verify/manifest path, and a capture re-pin with a canary bake on the unbackfillable path.

**No successor topic is owed, and none could be well-formed.** `open-topics.md` requires a `ripe_when` derived from measured state and verifiably satisfiable. Every candidate trigger ("a future episode reads `undetermined` **and** the venue was silent") fires precisely when the archived stream would be empty — a trigger that fires only when the remedy provably cannot help.

**The one live sub-item is rehomed, not deleted.** This topic's last next-step was a standing obligation to keep the runbook's status check alive. `infra/runbooks/ops.md`'s residual-gap step 4 now carries it as an **operating imperative** — read the venue's own frames, and if the venue announced it, write the event's row in the hygiene map — rather than as a pointer to this topic's ripeness.

**The residue, kept honest:** the WS ladder survives only within Grafana Cloud metric and Loki retention. The durable record is `00096` D6's hygiene-map row, hand-written per event, which is why step 4 now makes writing it an instruction rather than a suggestion.
