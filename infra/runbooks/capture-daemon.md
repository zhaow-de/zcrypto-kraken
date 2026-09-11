# Capture daemon — its own guards

Every signal here is the capture daemon reporting on itself: one `zcrypto-capture` container per capture host (`zcrypto` primary, `zcrypto-red` secondary), built from `cli/capture/`, exporting Prometheus metrics on `127.0.0.1:9101` that the host's Alloy scrapes every 60 s and direct-shipping its own ERROR/WARNING/INFO lines to Loki. Its spool is `/var/lib/zcrypto-capture` on the root filesystem, and L2 book capture is unbackfillable — a second not written is gone.

______________________________________________________________________

<a name="zcrypto-capture-book-desync-stuck"></a>

## zcrypto-capture-book-desync-stuck — ALERT

### What you are seeing

A **warning** Grafana alert, `Capture · book desync stuck on a pair`, one instance per `(host, pair)`; the `pair` label names the stuck pair.

`min_over_time(zcrypto_capture_book_desynced{host=~"zcrypto|zcrypto-red"}[15m]) > 0.5`, held `for: 5m`, so you are roughly **20 minutes** into an unbroken desync. `min_over_time`, not `max`: a desync that healed anywhere inside the window puts a 0 in it and never fires. Only the stuck shape pages.

### What it means

**Recovery is a bounded ladder, not one attempt.** The ladder is `cli/capture/desync_recovery.py`, driven by `_desync_recovery_loop` in `cli/capture/command.py` on a `DESYNC_RECOVERY_INTERVAL_SECONDS = 5` tick:

- **Rung 1**, on the transition into desync only (no count command: `cli/capture/command.py`'s `_handle_book_message` gates it on `not was_desynced`): one unsubscribe-then-subscribe for that pair, `checksum desync pair=… - resubscribing` (WARNING).
- **Grace** `DEFAULT_GRACE_SECONDS = 20.0` s.
- **Rung 2**, three retries, `desync recovery: retrying resubscribe pair=…` (WARNING), spaced by `DEFAULT_BACKOFF_SECONDS = (5.0, 10.0, 20.0)` s: the retries fire at 20, 25 and 35 s after the desync, and the last wait of 20 s runs before rung 3.
- **Rung 3**, exactly one `force_reconnect()` at **55 s**: it drops the socket and every pair on it (no count command: `cli/capture/ws_client.py`'s `force_reconnect` closes the one socket all pairs share), and all 12 come back with fresh snapshots, `desync recovery: pair=… still desynced after bounded retries -- forcing a full reconnect` (ERROR).
- **Terminal** for `DEFAULT_COOLDOWN_SECONDS = 3600.0` s.

So a pair still desynced at 15 minutes is post-ladder: a reconnect with a fresh snapshot did not fix it, and it has been in the cooldown for about fourteen minutes. A restart is the next rung, not a first retry.

The cooldown is not permanent. When it expires the ladder re-arms and the pair retries on the very next tick with no help from you (`desynced_at` is deliberately not reset). A pair that heals and re-desyncs inside that hour keeps the escalation record (`note_recovered` deliberately does not clear it), so it gets the transition resubscribe and nothing else until the cooldown expires.

**The blast radius is the whole host, not the pair.** `GapMonitor.is_healthy()` is False while any pair has an open gap, and the healthchecks.io ping (`HEALTHCHECK_INTERVAL_SECONDS = 60`) is gated on it, so this one pair withholds the host's dead-man for all 12. That check (`zcrypto-capture` or `zcrypto-capture-red`) has already gone down and stays down, and nothing worse on this host will produce a new dead-man page while it is saturated.

**The rows keep being written; what the desync costs is certification.** In `_handle_book_message` only a watermark breach skips the writer, so a desynced pair keeps appending every update row. The transition opens a `checksum_resync` gap in `GapMonitor`, so the window is booked into `zcrypto_capture_gap_seconds_total{pair=…}`, and the book replayed across it no longer reconciles against Kraken's checksum. Treat the window as unverified L2 on that pair, not as an empty one.

### What to do

1. **Read the ladder in the log** on the host the page names: `sudo docker logs zcrypto-capture 2>&1 | grep -E "checksum desync|desync recovery"`. Expect the full sequence above. Every record the daemon's own logger emits opens with its own UTC timestamp, so scope by reading the line, never with a bare `--since HH:MM:SS` (`docker logs --since` takes a duration or a full timestamp; the bare form fails to parse and its empty output reads as a clean bill) (no count command: `cli/logging/formatters.py`'s `PlainTextFormatter` stamps UTC; a hand `--since` goes unrecorded).
2. **Rule the venue out** before touching anything. If `zcrypto-capture-venue-not-online` or `zcrypto-capture-venue-state-recurrence` is firing beside this, that is upstream (`capture.md#zcrypto-capture-venue-not-online`), and a restart during a venue event costs a resubscribe and buys nothing.
3. **Ask whether the ladder ever reached a socket.** Rungs are held while the client is disconnected (`desync recovery: client reconnecting, holding pair=…`, DEBUG, not shipped at the default level). If `WS reconnect still failing after N consecutive attempts` (ERROR) is in the log, the fault is the connection, not the book: read the venue rules first.
4. **Restart the daemon, attended.** Restarting is the fix, and a stop drops live, unbackfillable L2 for the seconds it lasts: take it deliberately, one host at a time, never both (set: the capture restarts `deploy-log.jsonl` records — a successful row limited to a capture host or to the `capture_host` group, tagged capture or un-tagged — paired across the two hosts within an hour; count: `infra/scripts/count-list.sh capture-hosts-converged-within-an-hour`; `cli/capture/ws_client.py`'s `_subscribe_all` subscribes the whole pair list on connect). On the named host: `sudo systemctl restart zcrypto-capture` (the unit runs compose attached with `Restart=always`; the alert summary's `docker restart zcrypto-capture` restarts the container underneath it, so prefer the unit). The restart takes a fresh snapshot for every pair and zeroes the daemon's counters.
5. **Never loop restarts, and never hand-fire resubscribes.** Kraken rate-limits subscribes ("Exceeded msg rate"), after which the pair can never resync (no count command: a restart loop or a hand-fired resubscribe leaves no record; the rate limit is the venue's); that self-inflicted cascade is exactly what the transition guard and the bounded ladder exist to prevent.
6. **Confirm the heal by value.** `uv run python infra/scripts/grafana-query.py 'zcrypto_capture_book_desynced{host="<host>"}'`: every series must read 0 (no count command: a live query read at the time; nothing in the tree keeps it). `(no series)` is a FAIL, not a pass: it means the exporter or the scrape is down, which is its own incident. Then the dead-man: `hc_check_up{name="zcrypto-capture"}` (or `zcrypto-capture-red`) back to 1. Then that rows are still landing: on the host, `sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | wc -l` must be greater than 0.
7. **A restart you did not order is itself a finding**: `sudo docker inspect --format '{{.RestartCount}}' zcrypto-capture` and `--format '{{.State.StartedAt}}'`. Scope the inspect to those fields; never `{{json .Config}}` or `{{json .Config.Env}}`, and never `docker exec … env` (set: the non-comment lines of the non-Markdown files under `infra/`, `.claude/`, `cli/` — the roles, templates, units, hooks and scripts a command runs from — with the counter itself excluded; the Markdown runbooks and skills, where the form appears as the prohibition's own text, are outside it; count: `infra/scripts/count-list.sh engine-env-forms-invoked`): this container carries the Loki push password, and on the primary the host also carries the live Kraken trade key.
8. **Afterwards, size the window.** From the `checksum desync` line to the heal is booked gap time on that pair; compare those hours against the peer host's copy before treating anything as lost, and read the reconciler's verdict for them (`ops.md#zcrypto-reconcile-residual-gap`), which cannot answer for hour H until H+2 h, at the next `:12`/`:42` tick (no count command: `cli/archive/settle.py`'s `SETTLE_HOURS = 2` holds each hour back).

### Retire when

`zcrypto-capture-book-desync-stuck` is absent from `infra/grafana/alerts.yaml`, or `cli/capture/desync_recovery.py` no longer exists, at which point the ladder this section describes is gone.

______________________________________________________________________

<a name="zcrypto-capture-resubscribe-rate"></a>

<a name="zcrypto-capture-resubscribe-failing"></a>

## zcrypto-capture-resubscribe — ALERT

### What you are seeing

One of two **warning** Grafana alerts, both 24-hour `increase()` reads held `for: 30m`, both on the integrity board's "Recovery ladder — 24h increase" panel:

- **`zcrypto-capture-resubscribe-rate`**, `Capture · book resubscribe rate re-elevating`: `increase(zcrypto_capture_resubscribes_total{host=~"zcrypto|zcrypto-red"}[1d]) > 1.5`. A host resubscribed a book more than once in a day.
- **`zcrypto-capture-resubscribe-failing`**, `Capture · book resubscribe is failing (recovery degraded)`: `sum by (host) (increase(zcrypto_capture_resubscribe_errors_total{host=~"zcrypto|zcrypto-red"}[1d]) + increase(zcrypto_capture_resubscribe_ack_timeouts_total{host=~"zcrypto|zcrypto-red"}[1d])) > 1.5`. The recovery leg itself is being refused or ignored.

**Which host.** Both rules carry `host` per series, so the page names the host: act on that one.

Neither counter carries a `pair` label.

### What it means

Both counters live in `cli/capture/ws_client.py` and describe the resubscribe leg the desync ladder depends on.

**Rate.** `resubscribes_total` increments in `resubscribe_book()` on every unsubscribe frame sent, rung 1 and each rung-2 retry alike. The alert summary's `Post-2026-07-13` names the date the book was made congruent with Kraken's depth window (T0008), which ended the routine desync churn, so a rate above zero after it is a genuine event rather than the old background. The baseline is zero, so any resubscribe is a genuine venue or network event, and more than one a day means the rate is re-elevating or a pair is flapping desync/heal. A fast flapper is invisible to the stuck-pair gauge at a 60 s scrape; this rule sees it through the counter instead.

**Failing.** Two distinct faults, summed because the response is the same:

- `resubscribe_errors_total`: the venue answered a frame we minted (correlated by `req_id`) with `success` false. Logged `resubscribe reply rejected: <the venue's own message>` at ERROR. The unsubscribe was refused, so no fresh snapshot is coming and the desync recovery did not happen at all.
- `resubscribe_ack_timeouts_total`: the `unsubscribe` ack did not arrive within `_ACK_TIMEOUT_SECONDS = 5.0`; the subscribe is then sent anyway. Logged `resubscribe: no unsubscribe ack for pair=… in 5.0s -- subscribing anyway` at **WARNING**, which reaches no other rule; that is why this one exists beside the ERROR-log rule.

While the failing leg is broken a desynced book cannot heal at all, so expect `zcrypto-capture-book-desync-stuck` next.

**A benign reconnect must not count here.** If a reconnect lands inside the ack window, `_subscribe_after_ack` compares socket identity and returns without sending, because `_subscribe_all` has already resubscribed every pair on the new socket; a duplicate would draw "Already subscribed", which logs at ERROR and counts as a rejection. Repeated rejections whose text is "Already subscribed" therefore point at that guard, not at the venue.

### What to do

1. **Find the pair; neither counter names one.** `uv run python infra/scripts/grafana-query.py 'zcrypto_capture_book_desynced'` for any series currently at 1 (no count command: a live query read at the time; nothing in the tree keeps it), then the log for the rest: `sudo docker logs zcrypto-capture 2>&1 | grep -E "checksum desync|resubscribe"` on the host the page names. The lines carry the pair, and the rejected-reply line carries Kraken's own answer verbatim.
2. **Rule the venue out.** A venue event legitimately produces both of these: check `zcrypto-capture-venue-not-online` and `capture.md#zcrypto-capture-venue-not-online` before concluding anything about the daemon.
3. **Read the reconnect counter beside them**: `zcrypto_capture_reconnects_total{host="<host>"}`. Resubscribes rising in step with reconnects is a connection story; resubscribes rising alone is a book story.
4. **Rate firing with no pair currently desynced: there is nothing to restart.** A flapper heals itself each time. Record the pair and the venue reply. Two or more distinct days of this is a regression to file as work, not a runbook loop.
5. **Failing firing: read the venue's message from the rejected-reply line**, and check whether the ack-timeout counter or the error counter is the one moving (`zcrypto_capture_resubscribe_ack_timeouts_total` vs `zcrypto_capture_resubscribe_errors_total`; the summed alert cannot tell you) (no count command: `infra/grafana/alerts.yaml`'s `zcrypto-capture-resubscribe-failing` expr is one sum). Timeouts alone mean acks are not arriving and the subscribe went out blind; rejections mean the venue said no.
6. **If a pair is also stuck, the stuck-pair section above owns the response**, including the attended restart. These two rules on their own are not a reason to restart a capture daemon.
7. **Never hand-fire a resubscribe to "test" it**: the subscribe rate limit is the thing the whole ladder is bounded against (no count command: a hand-fired resubscribe leaves no record; the rate limit is the venue's).

### Retire when

Both `zcrypto-capture-resubscribe-rate` and `zcrypto-capture-resubscribe-failing` are absent from `infra/grafana/alerts.yaml`. Retiring one leaves the other: they describe the same leg from opposite sides, how often it runs and whether it works.

______________________________________________________________________

<a name="zcrypto-capture-watermark-breached"></a>

## zcrypto-capture-watermark-breached — ALERT

### What you are seeing

A **critical** Grafana alert, `Capture · disk watermark breached -- DISCARDING data`, one instance per host: `max by (host) (zcrypto_capture_disk_watermark_breached{host=~"zcrypto|zcrypto-red"}) > 0.5`, **`for: 0s`**.

`for: 0s` is arithmetic, not impatience: the daemon re-checks every `DISK_WATERMARK_INTERVAL_SECONDS = 30` and Alloy scrapes every 60 s, so a breach is already up to 90 s old before its first `1` sample exists, and that sample means the handlers are already dropping messages.

### What it means

Free space on the spool's filesystem fell below `DEFAULT_MIN_FREE_BYTES = 1 GiB` (`cli/capture/gap_monitor.py`). While breached, `_handle_book_message` `continue`s and `_handle_trade_message` `return`s before reaching the writers: every incoming book and trade message is dropped, while the WebSocket stays connected and healthy-looking. L2 is unbackfillable, so every second breached is permanent loss.

It also withholds the host's healthchecks.io ping, so that dead-man fires and stays fired: saturated, and blind to anything worse on this host. The breached interval is booked as a watermark gap in `GapMonitor`, so the lost time reaches the gap accounting instead of reading clean.

The spool is `/var/lib/zcrypto-capture`, on the root filesystem on both hosts. The 1 GiB watermark sits below `zcrypto-capture-disk-low`'s 10 %-free early warning, so disk-low only fires first when the fill is gradual; a sudden consumer (one pulled capture image — `infra/scripts/prune-host-images.py <host>`'s dry run prints each removable image's size) breaches the watermark with disk-low still green.

**One line is not this alert**: `disk watermark UNMEASURABLE path=… -- treating as not-healthy (probe failing)` means the probe itself raised, a flaky mount. That withholds the ping but does not set this gauge, so this critical rule stays silent and only hc.io speaks.

### What to do

1. **Look before deleting anything.** `ssh <host>`, then `df -h /` and `sudo du -xsh "$(sudo docker info --format '{{.DockerRootDir}}')" /var/log /var/lib/zcrypto-capture /tmp 2>/dev/null | sort -h`.
2. **Free space from the safe pools, in this order.**
   - **Docker image layers first**, usually the entire answer, since every re-pin to a new digest pulls another capture image; the dry run prints each removable image's size and the free space before removal. From your workstation: `uv run python infra/scripts/prune-host-images.py <host>`, then the same command with `--apply`; its `--help` states the keep-set and when to pass `--keep`. Never `docker image prune -a`: it takes the recorded rollback operands (set: the non-comment, non-Markdown lines under `infra/`, `cli/` and `.claude/` invoking `docker rmi`, `docker image rm|prune` or `docker system prune`, the script and counter excluded; count: `infra/scripts/count-list.sh image-removals-outside-the-pruner`; `zcrypto-capture.service`'s `ExecStartPre` pulls the pinned digest at start).
   - **The systemd journal**: `sudo journalctl --vacuum-size=200M`.
   - **On the primary only**, the engine's own journal ring (no count command: `infra/ansible/inventory/hosts.yml`'s `engine_host` holds `zcrypto` alone): `sudo systemctl start zcrypto-engine-journal-prune.service` (idempotent; its daily timer exists on the engine host alone).
3. **Never hand-delete inside `/var/lib/zcrypto-capture`.** The live hour's parts (`<HH>.part####.parquet`) and quarantined spills (`<HH>.held####.parquet`) end in names a careless `*.parquet` sweep eats, an interrupted merge (`<HH>.parquet.merging`) and `*.corrupt*` forensics sit beside them, and every one of them is unbackfillable. If the spool genuinely is the consumer, run the sanctioned prune instead: `sudo systemctl start zcrypto-capture-prune.service`. It deletes only committed finals (`<HH>.parquet`) and their `.sha256` sidecars older than 14 days, and refuses to sweep a system root (no count command: a hand deletion leaves no record; `tests/test_capture_prune.py` pins what the prune takes). Its own timer runs daily at 03:17 UTC.
4. **It self-clears; do not restart the daemon.** Within one 30 s poll of free space crossing back above 1 GiB, the daemon logs `disk watermark cleared path=… free=…` at INFO and resumes writing. A restart buys nothing and costs a fresh resubscribe of every pair on an unbackfillable stream (no count command: `cli/capture/ws_client.py`'s `_subscribe_all` subscribes the whole pair list on connect).
5. **Confirm by value, not by absence.** `uv run python infra/scripts/grafana-query.py 'zcrypto_capture_disk_watermark_breached{host="<host>"}'` must return the series reading 0; `(no series)` is a FAIL: the exporter or the scrape is down, which is its own incident. Then `hc_check_up{name="zcrypto-capture"}` (or `zcrypto-capture-red`) back to 1. Then that rows are landing again: `sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | wc -l` greater than 0.
6. **Then size the loss.** The window runs from the `disk watermark breached path=… free=… min_free_bytes=…` ERROR line to the `disk watermark cleared` INFO line. Read the reconciler's verdict for those hours (`ops.md#zcrypto-reconcile-residual-gap`): a breach on one host only is healable from the peer (no count command: a disk breach is an event on a host, not a set the tree holds), and hour H is not bookable before H+2 h, at the next `:12`/`:42` tick, so an early read answers reassuringly and means nothing.
7. **Finish by asking what filled the disk.** A watermark breach with no image backlog, no journal growth and a healthy prune ring is an unexpected consumer, and finding it is the actual fix.

### Retire when

`zcrypto-capture-watermark-breached` is absent from `infra/grafana/alerts.yaml`, or the book and trade handlers in `cli/capture/command.py` no longer guard on `watermark.breached`, at which point a breach no longer discards data and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-capture-error-logs"></a>

## zcrypto-capture-error-logs — ALERT

### What you are seeing

A **warning** Grafana alert, `Capture · daemon ERROR logs`: one or more ERROR/CRITICAL lines from the capture daemon (`container="capture"`) on a capture host in the last 15 minutes. `for: 0s`; zero is the healthy baseline.

The page carries the line itself in a `msg` label, truncated to 200 characters, alongside `host`. One alert instance per distinct line, and at most five (`topk(5, …)`): a storm carries more lines than you are shown, and the bound is deliberate, because a desync storm mints one distinct line per pair.

This is a Loki rule on the `level` label, set at the source by the daemon's own direct-ship handler (`cli/logging/ship.py`), not a text grep, and Alloy is not in this path at all.

### What it means

The daemon said something is wrong, and the message is the routing. Anything not on this list means read the surrounding lines.

| line (prefix) | where it comes from | what it means, and who owns it |
| -- | -- | -- |
| `disk watermark breached path=… free=… min_free_bytes=…` | `cli/capture/gap_monitor.py` | Capture is discarding every message; the critical watermark alert fires beside this and owns the response. |
| `disk watermark UNMEASURABLE path=… -- treating as not-healthy (probe failing)` | `cli/capture/gap_monitor.py` | Probe raised: gauge not set, so this is the only in-band signal. Check the mount. |
| `resubscribe reply rejected: <venue message>` | `cli/capture/ws_client.py` | The venue refused a resubscribe frame; its own answer is in the line. Resubscribe section above. |
| `desync recovery: pair=… still desynced after bounded retries -- forcing a full reconnect` | `cli/capture/command.py` | Rung 3: all 12 pairs resnapshotted, this pair in a 1 h cooldown. Desync section above. |
| `desync recovery failed for pair=… -- continuing with the rest` | `cli/capture/command.py` | One pair's ladder tick raised; the rest run on and it retries in 5 s. If it persists, file a defect. |
| `resubscribe: sending subscribe failed for pair=…` | `cli/capture/ws_client.py` | The subscribe half never went out, so that pair has no fresh snapshot coming. Expect the stuck-pair alert. |
| `subscribe error: …` / `unsubscribe error: …` | `cli/capture/command.py` | The venue refused a subscription frame outright. Read the message, then the venue rules. |
| `WS reconnect still failing after N consecutive attempts` | `cli/capture/ws_client.py` | Venue or network, not the book: `capture.md#zcrypto-capture-venue-not-online`; it backs off, do not restart. |
| `flush failed — buffer dropped pair=… kind=… hour=…` | `cli/capture/segment_writer.py` | Buffered rows for that hour were lost. Compare the hour against the peer host. |
| `an uncommitted merge is in the way …` / `an interrupted merge beside a committed final — left untouched …` / `parts beside a readable final — ambiguous, left untouched …` / `merge failed …` | `cli/capture/segment_writer.py` | Every byte is on disk; the writer refused an ambiguous recovery rather than guess. Do not hand-edit: the tree is hash-certified and an edit reports as permanent breakage. Compare the hour against the peer host; attended. |
| `… quarantine count …` | `cli/capture/segment_writer.py` | The spill tally, never the rows: seeding 0 can page `capture.md#zcrypto-capture-rows-quarantined` once with nothing spilled. |
| `quarantined unreadable file pair=… path=… dest=…` | `cli/capture/segment_writer.py` | Renamed to `.corrupt*`, never deleted; the parts it came from are untouched. Attended. |
| `ignoring a future-dated segment pair=… path=…` | `cli/capture/segment_writer.py` | Read the host's clock: `capture.md#zcrypto-capture-clock-skew` and `capture.md#bogus-timestamp-hour-rotation`. |
| `could not take the single-instance lock — running UNLOCKED path=…` | `cli/capture/command.py` | Two capture processes could now be writing the same spool. Attended, immediately. |
| `default pairs dropped N non-EUR-quoted universe symbol(s): …` | `cli/capture/command.py` | The deploy path always passes `--pairs`: a hand start, under-collecting against the universe. |

### What to do

1. **Read the `msg` label on the page and route with the table above.** The owning section, not this one, carries the fix.
2. **Widen when the page truncated.** Grafana Explore, Loki: `{host="<host>", container="capture", level=~"ERROR|CRITICAL"}` over the last hour. That is the unbounded read: `topk(5, …)` bounded the page, never the stream (no count command: the `topk` is in `infra/grafana/alerts.yaml`'s `zcrypto-capture-error-logs` expr alone).
3. **Or read it on the host**: `sudo docker logs zcrypto-capture 2>&1 | grep "<a distinctive phrase from the page>"`. Scope by reading the timestamp the daemon's own logger stamps on each record, never with a bare `--since HH:MM:SS` (see the stuck-pair section's step 1) (no count command: `cli/logging/formatters.py`'s `PlainTextFormatter` stamps UTC; a hand `--since` goes unrecorded).
4. **Print the input's line count before trusting any zero.** An empty filtered query is never a proven absence (no count command: trusting a zero is an operator's read nothing in the tree records); require a positive trace first.
5. **Nothing here is fixed by restarting the daemon.** The message names the fix, and a capture-daemon stop is an attended action that costs live, unbackfillable L2.
6. **It self-resolves 15 minutes after the last line.** If you silence it while working, time-box the silence, or the next distinct error during the fix reports nothing.

### Retire when

`zcrypto-capture-error-logs` is absent from `infra/grafana/alerts.yaml`, i.e. the rule was deliberately removed.
