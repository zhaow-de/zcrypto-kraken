---
status: resolved
---

# Both capture silence bars are derived from one week of data, not thirty days

## Context — what

`zcrypto-capture-all-streams-silent` (fleet-wide, `min by (host) (…) > 120`, critical) and `zcrypto-capture-stream-silent` (per-pair, `> 300`, warning) were both derived on 2026-08-05 from `max_over_time(zcrypto_capture_seconds_since_last_book_message[30d])`. The `[30d]` selector was read as thirty days of evidence. It is not: `zcrypto_capture_seconds_since_last_book_message` only started reaching Grafana Cloud with the 2026-07-29 capture converges (secondary 00:52:53Z, primary 07:36:13Z, image `99faf16514e3` — `docs/reference/fleet-pins.md`), so the selector maxed over the series' entire life and no more. `count_over_time(…[30d])` at the same moment returned **10435** samples on the primary and **10838** on the secondary — at one sample per 60 s, **7.24 d** and **7.53 d**.

Both bars stay where they are. What is owed is a DECISION, not a wait: the window the derivation claimed cannot exist on this platform (see the retention ceiling below), so the re-derivation can only ever run against the 14 days actually retained.

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

- **The 42,000-sample threshold was unreachable from the start, and the series had already plateaued when this topic read it as progress.** A full 30 d is 43,200 samples at one per 60 s. The readings: 10,435 / 10,838 at the 2026-08-05 derivation, 20,188 on 2026-08-23 — recorded here as "tracking as designed" — and **20,169 on 2026-08-26, which is LOWER**. It was not tracking; it had hit a ceiling and the window was sliding. Measured the same day: `[14d]` = **20,160**, an exactly complete 14 days, while `[21d]` and `[30d]` both return 20,169 — the same ~14 days plus 9 stragglers at the boundary.
- **The cause is the plan, not the fleet: Grafana Cloud's free tier retains a maximum of 14 days.** No `[30d]` selector can ever return more than ~20,160 samples here, so `>= 42000` could never fire and the "genuinely full 30 d window" this topic was waiting for does not exist. The alert rule's own comment came close — "THE BASE IS ONE WEEK, NOT A MONTH, which the `[30d]` selector hides" — but assumed the window would fill in time. It cannot.

## Resolution

**Resolved 2026-08-28.** The bars were re-derived against the full 14 d the platform retains, and **neither moves**. The value of the exercise turned out not to be the re-derivation.

**The window is complete and the ceiling is confirmed a second time.** `count_over_time(...[14d])` = **20159 / 20158** of a possible 20160; `[30d]` returns **20202** — the same ~14 days plus 42 boundary stragglers. The 2026-08-26 reading reproduces.

**Both bars stand, and the margin is larger than the topic feared, not thinner.** Over the 13 retained days containing no venue window the fleet-wide minimum peaked at **6.134482 s** and the binding per-pair reading at **14.160757 s** (`zcrypto-red` SOL/BTC, with no capture restart within 26 h — checked, because four secondary restarts fall inside the window). So 120 is ~20× its natural envelope and 300 is ~20× its own.

**This topic's central premise was wrong, and correcting it is the durable outcome.** "The platform retains 14 days, so a fuller base never arrives" is true of **this gauge** and false of **the phenomenon**. The parquet archive holds the whole capture era at full resolution and `infra/scripts/gap_distribution.py` measures book silence from it — the instrument that produced the repo's own **14.78 s** single-host natural maximum (AVAX, 7,847,932 messages, 2026-07-14, [[T0039]]). The gauge and the archive **agree**, which is what makes these bars trustworthy; the window length never was the thing to wait for. A future re-derivation starts at the archive, and prefers it: a 60 s scrape censors short silences and is biased low.

**The claim "the tail grew" is withdrawn.** 14.160757 s < 14.78 s: the envelope has been ~15 s since July. The earlier comparison was against 12.068981 s, a different and smaller quantity, which is also why the per-pair margin was recorded as ~25× when it is ~20×.

**What was actually broken was the prose, on four surfaces.** [[T0145]] identified the fleet-dark class as published Kraken maintenance on 2026-08-21, but "no natural cause produces it" / "cause unexplained" went on being read in `infra/grafana/alerts.yaml`, `docs/specs/00084-...`, the data-integrity board's panel 102 and the operator-visible alert summary. All four are corrected, and the correspondence is now measured rather than asserted: **every firing in either rule's operational life — 2026-08-06 and 2026-08-20, both hosts — fell inside an announced "Kraken Website and API Maintenance" window, and no unexplained crossing has ever been observed.**

**Both rules gained the runbook sections they never had**, opening with "read the venue calendar first"; and `infra/runbooks/capture.md`'s venue-halt step 4, which told the operator these firings were "not something to respond to separately", no longer does.

**A finding this work surfaced, fixed in the same branch on the owner's ruling:** `execErrState: Alerting` was uniform across all 75 rules and undiscussed. On these two it produced **264 execution-error instances against 52 genuine ones (83.5 %)** between 2026-08-05 and 08-28 — Grafana Cloud failing to reach its own Prometheus — and the page was not merely noisy but **false**, asserting a total capture blackout the query never ran to observe. These two rules now carry `execErrState: OK`, pinned by tests with a guard refusing a third rule to join; the other 73 keep `Alerting`, so datasource trouble is still reported.

**Nothing is deferred.** The one improvement consciously NOT made — a single dedicated owner for "the alerting datasource is unreadable", which would make the other 73 rules' `Alerting` redundant rather than merely loud — is recorded in the runbook's own `### Retire when`, and leaves nothing unwatched in the meantime.
