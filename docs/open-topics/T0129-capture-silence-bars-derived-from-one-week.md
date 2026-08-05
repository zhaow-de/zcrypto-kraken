---
status: open
ripe_when: a read of `count_over_time(zcrypto_capture_seconds_since_last_book_message[30d])` returns ≥ ~42000 on both capture hosts — a genuinely full 30-day window (43200 samples at one per 60 s, less scrape misses). One Grafana query against data already being collected, run by `infra/scripts/grafana-query.py`. At the 2026-08-05 derivation it returned 10435 / 10838, so the trigger sits ~23 days out from then — but it is measured rather than dated, so a capture outage or a gauge re-ship pushes it back on its own.
---

# Both capture silence bars are derived from one week of data, not thirty days

## Context — what

`zcrypto-capture-all-streams-silent` (fleet-wide, `min by (host) (…) > 120`, critical) and `zcrypto-capture-stream-silent` (per-pair, `> 300`, warning) were both derived on 2026-08-05 from `max_over_time(zcrypto_capture_seconds_since_last_book_message[30d])`. The `[30d]` selector was read as thirty days of evidence. It is not: `zcrypto_capture_seconds_since_last_book_message` only started reaching Grafana Cloud with the 2026-07-29 capture converges (secondary 00:52:53Z, primary 07:36:13Z, image `99faf16514e3` — `docs/reference/fleet-pins.md`), so the selector maxed over the series' entire life and no more. `count_over_time(…[30d])` at the same moment returned **10435** samples on the primary and **10838** on the secondary — at one sample per 60 s, **7.24 d** and **7.53 d**.

Both bars stay where they are. What is owed is the re-derivation once the window the derivation claimed actually exists.

## Why this matters

The margins read one way against a month and another against a week. The fleet-wide 120 is 4× the worst simultaneous silence ever observed (30.261266 s) — a comfortable factor against a month of production, a materially thinner one against seven days that contain exactly **one** such event. A tail that appears once a fortnight has not yet had a chance to appear. The per-pair 300 is the safer of the two (≈25× the binding natural maximum of 12.068981 s), but it rests on the same base.

The rules sit on the unbackfillable capture path, where both error directions cost: a bar set too low pages on natural quiet and trains the operator to ignore the one signal that catches a total blackout; too high and permanent L2 loss runs longer before anyone is told.

## Findings so far

- **Sample counts, measured 2026-08-05 13:32 UTC** via `infra/scripts/grafana-query.py`: `count_over_time(zcrypto_capture_seconds_since_last_book_message[30d])` = **10435** (`zcrypto`, all 12 pairs identical) / **10838** (`zcrypto-red`). Scrape interval 60 s (`infra/ansible/roles/capture/files/config.alloy`) ⇒ 7.24 d / 7.53 d. A full 30 d would be 43200.
- **The fleet-wide event is real and is not a converge artefact.** `max_over_time(min by (host) (…)[30d:1m])` = **30.261266** on the primary, 3.596756 on the secondary. A 6 h bisection localizes it to **2026-07-29 19:14–01:14 UTC**, ≥ 11.6 h after the primary's 07:36:13Z converge; the adjacent 6 h windows max 0.117604, 0.197723 and 0.136539 s. Cause still unexplained.
- **The twelve primary per-pair maxima are one simultaneous event, provably.** They span 30.261266–31.591118 s, and the min-by-host maximum equals AVAX/EUR's per-pair maximum **to the digit** (30.261266) — so at that instant no pair was delivering. That is a stronger statement than the min-by-host argument alone, which only shows *some* simultaneous silence.
- **The binding natural per-pair maximum is the primary's, not the secondary's.** Excluding the event day (`max_over_time(…[6d])`): primary AVAX/EUR **12.068981 s**, above the secondary's worst of ETH/BTC **11.125801 s**. It matches the 12.196 s worst natural intra-hour spacing `BOOK_STALENESS_SECONDS` records in `cli/capture/command.py`.
- **Daily min-by-host maxima over the whole life** (primary): 30.261266 (07-29), then 2.6418, 1.013259, 0.18049, 1.068947, 4.328992, 10.380023. Every day but the event day sits between 0.18 s and 10.4 s.
- **What 30 s is in the daemon, since the per-pair bar's warrant leans on it**: `_staleness_loop` calls `monitor.start_silence` and nothing else — no resubscribe, no reconnect. `_desync_recovery_loop` (the only path that resubscribes or forces a reconnect) skips every pair whose book is not `desynced`, and `gap_monitor.is_healthy()` deliberately ignores silence, so a silent-but-synced stream does not even withhold the dead-man ping. It never self-heals at any age.

## Suggested next steps

- *(autonomous, when the trigger fires)* Re-run the derivation on the full window and record both outcomes, including "unchanged": `count_over_time(zcrypto_capture_seconds_since_last_book_message[30d])` first (to confirm the window is genuinely full), then `max_over_time(zcrypto_capture_seconds_since_last_book_message[30d])` per pair per host and `max_over_time(min by (host) (zcrypto_capture_seconds_since_last_book_message)[30d:1m])`. Exclude any interval containing a known fleet-wide event before reading the *natural* per-pair maximum — the 2026-07-29 event is the reason the raw per-pair maxima were misread once already.
- *(autonomous, same pass)* If either bar moves, move every surface that carries it in the same commit: the evaluator in `infra/grafana/alerts.yaml`, that rule's `for`, its summary's stated notice period, the D11 row in `docs/specs/00084-dashboards-and-notifications-design.md`, and `data-integrity-dashboard.json` panel 102 (both its threshold step and its description). The per-pair number lives on four surfaces and the panel is the one previously missed.
- *(autonomous, same pass)* Re-check whether the 2026-07-29 fleet-wide silence has a sibling. A second instance turns an unexplained one-off into a distribution with a shape, which is what the 4× margin is currently standing in for; a full month with no repeat is itself the evidence that the margin can be reasoned about rather than guessed.
