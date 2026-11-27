# Ledger correction evidence — 2026-11-26 venue halt booked as loss (both streams silent, hour 08)

The durable record of a correction made to the append-only `reconcile-ledger.jsonl` on `zcrypto-ops` (`/var/lib/zcrypto-ops/capture-reconciled/`) on 2026-11-26, committed on the branch that removes its cause (spec `00167`, the deferred booking). The procedure is "Correcting the reconcile ledger (T0044)" in `README.md` beside this file; where this correction departed from it is the last section.

## The record before the correction (verbatim)

```json
{"state": "both_streams_silent", "pair": "*", "kind": "book", "hour": "2026-11-26T08:00:00+00:00", "pairs": ["ADA/EUR", "AVAX/EUR", "BTC/EUR", "DOGE/EUR", "DOT/EUR", "ETH/BTC", "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/BTC", "SOL/EUR", "XRP/EUR"], "windows": [{"start": "2026-11-26 08:01:05.653845+00:00", "end": "2026-11-26 08:02:57.207297+00:00", "seconds": 111.553452}, {"start": "2026-11-26 08:02:57.218016+00:00", "end": "2026-11-26 08:04:48.119231+00:00", "seconds": 110.901215}], "stream_windows": {"ADA/EUR": [{"start": "2026-11-26 08:01:05.465485+00:00", "end": "2026-11-26 08:02:57.207297+00:00", "seconds": 111.741812}, {"start": "2026-11-26 08:02:57.207297+00:00", "end": "2026-11-26 08:05:01.017134+00:00", "seconds": 123.809837}], "AVAX/EUR": [{"start": "2026-11-26 08:01:05.195195+00:00", "end": "2026-11-26 08:02:57.218016+00:00", "seconds": 112.022821}, {"start": "2026-11-26 08:02:57.218016+00:00", "end": "2026-11-26 08:04:54.627463+00:00", "seconds": 117.409447}], "BTC/EUR": [{"start": "2026-11-26 08:01:05.653845+00:00", "end": "2026-11-26 08:04:52.716504+00:00", "seconds": 227.062659}], "DOGE/EUR": [{"start": "2026-11-26 08:01:05.347704+00:00", "end": "2026-11-26 08:02:57.214025+00:00", "seconds": 111.866321}, {"start": "2026-11-26 08:02:57.214025+00:00", "end": "2026-11-26 08:04:48.119231+00:00", "seconds": 110.905206}], "DOT/EUR": [{"start": "2026-11-26 08:01:05.333017+00:00", "end": "2026-11-26 08:02:57.208523+00:00", "seconds": 111.875506}, {"start": "2026-11-26 08:02:57.208523+00:00", "end": "2026-11-26 08:05:01.098886+00:00", "seconds": 123.890363}], "ETH/BTC": [{"start": "2026-11-26 08:01:05.149917+00:00", "end": "2026-11-26 08:04:51.001814+00:00", "seconds": 225.851897}], "ETH/EUR": [{"start": "2026-11-26 08:01:05.571243+00:00", "end": "2026-11-26 08:02:57.211955+00:00", "seconds": 111.640712}, {"start": "2026-11-26 08:02:57.211955+00:00", "end": "2026-11-26 08:04:51.758616+00:00", "seconds": 114.546661}], "LINK/EUR": [{"start": "2026-11-26 08:01:05.507393+00:00", "end": "2026-11-26 08:02:57.211445+00:00", "seconds": 111.704052}, {"start": "2026-11-26 08:02:57.211445+00:00", "end": "2026-11-26 08:04:52.874276+00:00", "seconds": 115.662831}], "LTC/EUR": [{"start": "2026-11-26 08:01:05.249953+00:00", "end": "2026-11-26 08:02:57.208028+00:00", "seconds": 111.958075}, {"start": "2026-11-26 08:02:57.208028+00:00", "end": "2026-11-26 08:04:56.339612+00:00", "seconds": 119.131584}], "SOL/BTC": [{"start": "2026-11-26 08:01:05.058938+00:00", "end": "2026-11-26 08:02:57.213558+00:00", "seconds": 112.15462}, {"start": "2026-11-26 08:02:57.213558+00:00", "end": "2026-11-26 08:04:58.034280+00:00", "seconds": 120.820722}], "SOL/EUR": [{"start": "2026-11-26 08:01:05.383248+00:00", "end": "2026-11-26 08:02:57.209733+00:00", "seconds": 111.826485}, {"start": "2026-11-26 08:02:57.209733+00:00", "end": "2026-11-26 08:04:54.002221+00:00", "seconds": 116.792488}], "XRP/EUR": [{"start": "2026-11-26 08:01:05.652936+00:00", "end": "2026-11-26 08:02:57.207649+00:00", "seconds": 111.554713}, {"start": "2026-11-26 08:02:57.207649+00:00", "end": "2026-11-26 08:04:55.168326+00:00", "seconds": 117.960677}]}, "residual_seconds": 2752.189489, "halt_seconds": 0.0, "verdict": "venue_silent", "interior_updates": 16, "interior_snapshots": 0, "interior_seconds": 0.010719, "pairs_agreeing": 10, "pairs_skipped": 0, "divergent_pairs": [], "streams_carried": 12, "windows_bracketed": 2, "trades_inside": 0, "trade_id_holes": 0, "quiet_seconds": 294.863762, "at": "2026-11-26T10:12:05.582491+00:00"}
```

Line 590 of 602: 3531 bytes, sha256 prefix `7fa4b26ad2bd3759`, the prefix the correction script printed for the line before it wrote. The text above was rebuilt on 2026-11-27 from the live line (read at 18:22:11Z) by reversing the correction's one byte replacement, and matches that prefix and length.

## What changed

Three fields of that one record, by one exact byte replacement, and no other byte of the file:

- `residual_seconds`: `2752.189489` → `0.0`
- `halt_seconds`: `0.0` → `2752.189489`
- `verdict`: `"venue_silent"` → `"venue_halt"`

The line after: 3529 bytes, sha256 prefix `29dbf4860ad9176f`; its `at` stays `2026-11-26T10:12:05.582491+00:00`, the first look's.

## Why it was changed

At its 10:12Z cycle the reconciler decided the fleet-dark hour 08 — two fleet windows from 08:01:05.653845Z to 08:04:48.119231Z — as loss. Every halt proof held (`streams_carried` 12, `windows_bracketed` 2, `trades_inside` 0, `trade_id_holes` 0, `quiet_seconds` 294.863762), but DOT/EUR's and SOL/BTC's hour-08 trades finals were on neither mirror yet, and a pair with no trades final vetoes the halt. A pair's trades final closes only at its next print, so a quiet pair's final can reach the NAS after the hour settles: here the NAS pull that carried the two came after the 10:12Z cycle.

A read-only re-run of the reconciler with both late trades finals present, at 2026-11-26T10:54:09Z, decided the same record as `venue_halt`, `halt_seconds` 2752.189489, `residual_seconds` 0.0: against the live record it differed in `at`, `halt_seconds`, `residual_seconds` and `verdict` alone, 22 keys each. The halt was provable; the loss was the race.

Asked 2026-11-26T10:49:46Z, verbatim but for "[the venue's]", the venue's name, which `tests/test_deploy_log_audit.py` keeps out of `infra/nas/`: "Zebra's daily pass found that the reconciler booked 2,752.2 s of hour 08 today as permanent capture loss (the residual-gap alert has been firing since 10:13Z). The silence was [the venue's] 08:01-08:16Z maintenance; it was booked as loss only because two pairs' hour-08 trades files (DOT/EUR, SOL/BTC) had not reached the NAS yet when the booking ran. Both files exist now and show neither pair traded inside the silence. The runbook says a booking can only be corrected by a deliberate, approved ledger edit. Do you want it corrected?" The owner's answer by 10:51:44Z, verbatim: "Prepare the edit, show me first (Recommended)".

Asked 2026-11-26T10:55:31Z, verbatim: "The hour-08 correction is prepared and I confirmed zebra's finding: re-running the reconciler read-only with both late trades files present books the same hour as a venue halt, and the re-run's record differs from the live one in exactly three fields. The edit changes line 590 of the reconcile ledger on this workstation: residual_seconds 2752.189489 -> 0.0, halt_seconds 0.0 -> 2752.189489, verdict venue_silent -> venue_halt; the other 601 lines stay byte for byte, the ledger is copied aside first, and the script refuses if the ledger changed since I read it. Effect: at the next reconciler cycle the loss counter drops from 80298.085 to 77545.896 s; the residual-gap alert reads that drop as a reset, goes quiet, and by design cannot page for a NEW loss for the next 24 hours. Apply it?" The owner's answer by 10:56:46Z, verbatim: "Apply it now (Recommended)".

## The ledger and its backup

- Before: sha256 `f1c588fa1f27ffc426e5d3feff029d1c7c2b8ac880309f73032208b80f6cd8b9`, 236649 bytes, 602 lines.
- After, written 2026-11-26T10:56:56Z, owner `zcrypto-data` and mode 0664 kept: sha256 `ecb7c3c62005e4fced0b9c3bdc8e808dc3b52a02d424098eafdef28c034fe5b4`, 236647 bytes, 602 lines, line 590 alone differing; the same sha256 read again on 2026-11-27 at 18:22:11Z.
- The backup: the before file, copied aside verbatim as `reconcile-ledger.jsonl.aside-20261126-hour08` (sha256 `f1c588fa…`, 236649 bytes), deleted at 11:12:53Z after the verification below. This file is its durable record.

## Verification by value

The textfile after the 11:12:17Z cycle: `zcrypto_reconcile_residual_gap_seconds_total 77545.89574299999` and `zcrypto_reconcile_venue_halt_seconds_total 2752.189489`, from `80298.08523199998` and `0` before. Prometheus at 11:12:46Z read the same two values and `resets(zcrypto_reconcile_residual_gap_seconds_total[24h])` = 1, so the residual-gap rule's `resets(...) == 0` guard could page no new loss until that reset aged out of its window, at about 2026-11-27T11:12Z.

## Where it departed from the procedure

- The copy-aside was written inside `capture-reconciled/`, against the backup rule: it lay there from 10:56:56Z until it was moved off the overlay at 10:57:07Z; the NAS custody copy's root, listed 2026-11-27 at 18:23:23Z, holds no such file.
- `scan-cache.json` was not deleted in the same act. No hour was skipped for it: the cache skips an hour only from an entry its late examination wrote, and hour 08 reached its late deadline at 14:00Z, after the edit.
- This record was committed on 2026-11-27, a day after the edit.
