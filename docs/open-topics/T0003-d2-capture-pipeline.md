---
status: partial
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

## Done so far

Iteration **iter-038** (interactive design → unattended build; spec `docs/specs/00027-t0003-capture-pipeline-design.md`, plan `docs/plans/00027-t0003-capture-pipeline.md`) built and **deployed the pipeline LIVE**:

- **Host provisioned + hardened.** The human provisioned a Linode (Debian 13, resized to 2 vCPU / 4 GB / 80 GB, `zcrypto.zhaow.me`); `infra/ansible/` then bootstrapped a `deploy` sudo user, moved SSH to **10022** (root + password login disabled, no self-lockout — verified), and applied dev-sec.io `os_hardening`+`ssh_hardening` (CIS-L1), nftables (default-drop inbound, 10022 + ICMP; manages only its own table so Docker NAT survives), fail2ban, chrony **NTS**, unattended-upgrades (04:00 reboot), and Docker.
- **Capture daemon LIVE.** `cli/capture/` — a thin Kraken WS v2 client (book **depth-100** + trades, all 10 EUR majors), per-pair L2 book with **CRC32 checksum validation** (verified vs Kraken's documented example + 3874 live checksums, zero mismatches), hourly **zstd-Parquet segments + sha256 manifests**, gap accounting, disk watermark. Containerized (`infra/docker/`, on-host build tonight; GHCR CI shipped) and running via compose (`restart: unless-stopped` + docker-enabled → survives the 04:00 reboot): **19 % CPU / 74 MiB, 0 errors, all 10 pairs flowing**. The **≥7-day exit-bar clock started 2026-07-08 ~13:39 UTC.**
- **Liveness monitoring.** A healthchecks.io dead-man's-switch check is provisioned + wired (`HEALTHCHECK_URL`, status **up**) → emails on a missed ping; status badge added to the README.
- **Secrets.** Two-layer: sops+GPG-encrypted ansible-vault password; vault-encrypted deploy + pull-only SSH keys, hostname, and healthchecks key — nothing plaintext in the public repo.

## Incident — 2026-07-08: unrecoverable book desync (code fix landed; deploy is human-gated)

**What happened.** At ~14:47 UTC (iter-039, discovered by live monitoring) the high-activity pairs desynced and **could not heal**: 193 `checksum desync … resubscribing` warnings in ~1 min (DOGE 312 / BTC 147 / ETH 102 log lines over the window), every resubscribe answered by Kraken with `{'error': 'Already subscribed'}`, and the healthcheck stopped pinging (the monitor correctly withholds pings while unhealthy → the dead-man's switch would email). Trades unaffected; only the desynced pairs' **book** segments during the window are checksum-invalid.

**Root cause.** `CaptureClient.resubscribe_book` (recovery from a checksum desync) sent a bare `subscribe` for the still-active book channel. Kraken rejects re-subscribe of an active channel with "Already subscribed" and sends **no** fresh snapshot — so `ingest_snapshot` (which is what rebuilds the book and clears `desynced`) never runs, and a book that desyncs once stays desynced until the whole connection drops. The earlier iter-038 fix stopped the resubscribe *storm* (only fires on the desync transition) but did not make the resubscribe actually *work*.

**Fix (landed, not yet deployed).** `resubscribe_book` now **unsubscribes then re-subscribes** (new `build_unsubscribe_message` helper), which forces the fresh snapshot that heals the book; also added `unsubscribe_ack`/`unsubscribe_error` classification + logging so a rejected recovery is no longer silent. TDD (`tests/test_capture_ws_client.py`). On branch `fix/t0003-resubscribe-desync` → PR into `develop`. **The running daemon still has the old code and, as of hand-off, is stuck desynced on the high-activity pairs.** The fix heals on the common path; a residual robustness gap (a single fire-and-forget recovery attempt can still leave a pair stuck) is tracked as [T0008](T0008-desync-recovery-robustness.md).

**Beware quiet logs.** Because iter-038 made the desync warning fire only on the *transition* into desync, a pair that is **stuck** desynced logs nothing further — the `checksum desync` spam stops even though the pair is still broken. Confirmed at hand-off: 0 new desync warnings and 0 reconnects in the trailing minutes, yet the healthcheck was still withholding pings. **The true health signal is the withheld healthcheck ping (→ healthchecks.io check goes DOWN), not the absence of log warnings.**

**Why the deploy is parked (not done autonomously):** restarting / redeploying the *live* capture container is a production action (auto-mode correctly blocked the restart) — it is the human-gated sub-item; the code fix (reversible, on a branch) was the autonomously-resolvable half and is done.

## Suggested next steps

Remainder (the wall-clock drill + the sync/alerting half):

- **(HUMAN — urgent, do first) Recover the currently-stuck daemon**, then deploy the fix:
  1. **Immediate recovery** (clears the stuck desync via fresh snapshots — loses only a few seconds of buffer, segments flush every few seconds): `ssh -p 10022 deploy@zcrypto.zhaow.me` then `sudo docker restart zcrypto-capture-capture-1`. Verify: `sudo docker logs --since 2m zcrypto-capture-capture-1 2>&1 | grep -c desync` should fall to ~0 and the healthchecks.io check should return to **up** within a couple minutes.
  2. **Permanent fix** — merge PR `fix/t0003-resubscribe-desync` into `develop`, then rebuild the on-host image from the updated code and recreate the container (the iter-038 on-host build path: tar the repo build context to the host → `sudo docker build -f infra/docker/Dockerfile -t zcrypto-capture:local .` in `/opt/zcrypto-capture` → `sudo docker compose -f /opt/zcrypto-capture/compose.yaml up -d`). After recreate, confirm a **deliberate** desync now self-heals (watch for a `checksum desync … resubscribing` followed by the pair returning to sync, no "Already subscribed" errors).
- **(autonomous)** **Workstation pull service** — install rsync on the host, a pull-only forced-command (`rrsync`-restricted) SSH key, a workstation systemd timer that rsyncs the VPS ring buffer → hash-verifies each segment vs its manifest → deletes-on-VPS-after-verified → nightly compaction to the NAS `../zcrypto-kraken-data/`. (The VPS ring buffer holds ≥7 days, so this can lag without loss — but build it before the ~74 GB disk fills.)
- **(autonomous)** **Full monitoring role** — beyond the liveness heartbeat, wire disk-watermark + gap-rate alerts, and run the **alerting drill** (stop the daemon → confirm the alert fires) that the exit bar requires.
- **(autonomous)** **The ≥7-day clean-run** — let it run ≥7 consecutive days; verify \<0.1 % gap time + zero segment loss + all hashes match end-to-end → satisfies this slice of the Phase-1 exit bar (then flip to `resolved`).
- **(autonomous, smaller)** GHCR package **public-visibility** so the CI-pull deploy flow works (tonight used an on-host build — a GitHub-UI toggle is the one human step for the registry path); wire the `ansible-lint` pre-commit hook (scoped `^infra/`) + the repo-wide `name[casing]` cleanup; add REST trade-backfill to the daemon (deferred this pass — gaps are logged, not backfilled).
