---
status: open
---

# D2 forward-capture pipeline (VPS daemon → workstation sync → NAS)

## Context — what

Phase 1's goal (master-plan §12) is *"immutable, QA'd, versioned research datasets **+ the D2 capture pipeline running end-to-end (VPS daemon → workstation sync → NAS)**"*, and its exit bar requires *"capture daemon ≥7 consecutive days with \<0.1% gap time **and** VPS→workstation→NAS sync verified end-to-end (all segment hashes match, zero segment loss, alerting drill passed)."* Per §8 the daemon is a hardened Linode VPS running a WebSocket L2/trade capture service (systemd, NTP, hourly hashed segments, ≥7-day ring buffer, gap monitoring, REST trade-backfill), paired with a workstation pull service (scheduled rsync/rclone, hash verification, delete-after-verified-sync, nightly NAS compaction, alerting). **None of this is built** — the completed Phase-1 work is all historical-OHLCVT ingestion; there is no forward-running capture.

## Why this matters

This is a **hard, explicit Phase-1 exit-bar gate** and the only source of the project's own captured L2 order-book history — one of the four residual-alpha buckets the master plan bets on (§1: "Kraken-specific data … own captured L2 books") and the input to the per-pair spread term of the Phase-2 cost model (§12 Phase-2 loop: "per-pair spread from captured L2"; §8 data plan). Its 7-consecutive-day green-run requirement is an inherent **wall-clock** gate that cannot be short-circuited: even once the VPS exists, it needs a week of clean capture. The sooner the daemon is live, the sooner that week starts and the sooner captured-spread calibration (a Phase-2 exit-bar item) has real data.

## Findings so far

- **Human-gated at the front.** The master plan (§Phase 1 kickoff) is explicit: *"VPS account provisioning is a one-time D3(i)-style account action on your side; everything after credentials exist is autonomous."* So provisioning the Linode (account, SSH keys, region, size) is a human action; hardening + daemon deployment + the pull service are autonomous once credentials exist.
- **No API keys needed.** §8/§12 state Phases 1–5 run with **no API keys** — the capture daemon streams **public** WS market data (trades + L2 book), so it does not touch the read-only key (T0000) or any trade-scoped key.
- **NAS target exists.** Cold storage is the NFS mount `../zcrypto-kraken-data/` (27 TB free); the OHLCVT dumps already live under `kraken-ohlcvt-updates/`, so the sync destination and `backup_dir` convention (`../zcrypto-kraken-data/zcrypto`, README) are settled.
- **Adapter groundwork done.** The NautilusTrader Kraken **public-data** WS path was verified keyless in iter-003 (`docs/research/01.2.nautilus-kraken-adapter-memo.md`) — a candidate capture transport, though a thin custom WS client may be simpler for pure capture.
- The Phase-2 validation harness is proven on **synthetic** data (master-plan §Phase 2) and has **no dependency** on this pipeline, so parking it does not block Phase 2/3/4 research on historical data.

## Suggested next steps

- **(human)** Provision a Linode VPS (region near Kraken's venue, small instance); create SSH credentials; hand off host + key.
- **(autonomous, once credentials exist)** Harden the VPS (systemd, NTP, firewall, unattended-upgrades); implement the capture daemon per §8 (WS v2 trades + L2 book, hourly hashed segments, ≥7-day ring buffer, gap monitor, REST trade-backfill on reconnect gaps).
- **(autonomous)** Implement the workstation pull service (scheduled rsync/rclone, per-segment hash verify, delete-after-verified-sync, nightly NAS compaction) with alerting; run the alerting drill.
- **(autonomous)** Let it run ≥7 consecutive days; verify \<0.1% gap time + zero segment loss + all hashes match → satisfies this slice of the Phase-1 exit bar.
