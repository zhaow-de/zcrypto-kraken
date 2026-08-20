---
name: zcrypto-captures-rollout
description: Attended canary rollout of a capture-image digest across the capture fleet — preflight, secondary converge, event-driven bake with abort signals, primary re-pin, rollback, verify-by-outcome. User-invoked only.
disable-model-invocation: true
---

# zcrypto-captures-rollout

The executable form of the capture-image canary rollout. L2 capture is unbackfillable — a mistake on either host is permanent data loss. Scope: **digest re-pins only**; a pair-list change is config (primary-first, no bake — `capture-deploys.md`), and engine converges are their own section there.

## Ground rules

- **Every host-touching command runs in the main loop as a plain command — never inside a dispatched subagent or background workflow.** The permission gate blocks ssh-sudo there and the step dies where nobody sees the prompt; the user grants access live, at the command.
- **Every irreversible action** — converge, re-pin, restart — takes the user's explicit word at that step, with the blocker sweep (open-topics index + memo) presented alongside (`agent-ops.md`).
- Rollout order: **secondary first, primary last.**
- Digest identity is always `{{.Config.Image}}` — `{{.Image}}` is host-dependent and lies under classic storage.
- Playbooks via `infra/ansible/scripts/run.sh`; preview every converge with `--check --diff`; never run the primary un-tagged; `-e converge_primary=true` restarts live capture — mean it. Vault and inspect-scoping invariants: `capture-deploys.md` and CLAUDE.md `## Secrets`.

## Phase 0 — Preflight

1. Blocker sweep: `docs/open-topics/README.md` + the memo; present the result with the rollout proposal.
2. Candidate digest from CI; **pre-stage everything**: pull the digest on each host, verify the change is *in* the pulled image (run the image's own version/inspection surface — never assume from the tag), stage the compose pin.
3. Record the rollback operand now: the currently-running `{{.Config.Image}}` on both hosts, and confirm that digest is still present locally on both (`docker image ls --digests`) — the rollback path depends on it.
4. `--check --diff` against the fleet from a tree whose rendered config matches it.

## Phase 1 — Secondary converge

- `site.yml --limit zcrypto-red -e capture_image_digest=sha256:<candidate>` — the stop→start window contains only stop → migration-if-any → start.
- Immediate checks: container up with `RestartCount` 0, all pairs subscribed with zero subscribe errors, parquet advancing. `dropping late event` lines right after start are healthy resubscribe replay, not a failure.

## Phase 2 — The bake gate: the smallest window that covers the events

**The gate is event-coverage: the smallest window between the two re-pins that satisfies all three.** Compute the window, state it for the user's word, then start it:

1. **A clean prune under the new image** — the one recurring writer that mutates the capture dir concurrently with the daemon. Do not wait for 03:17: `sudo systemctl start zcrypto-capture-prune.service` on the just-converged host fires it now. **Read `deleted=N` in the result**: `deleted=0` exercises the scan but never the deletion path (the weak form) — note which form the bake got, and prefer a host/day where the archive age yields a deleting prune.
2. **≥3 full segment-rotation hours** — the first hour's every book `<HH>.parquet` beginning at `:00:00.0x` proves the boundary write; three hours are the RSS-slope row's minimal viable duration — two complete rotation cycles plus the current one, separating a real trend from the rotation sawtooth. **FULL hours only — hours that BEGIN after the re-pin; the converge's own partial hour never counts** (re-pin at 14:07 → hours 15/16/17 → gate 18:00Z). Counting boundaries instead of full hours reads the gate an hour early — a measured mistake, 2026-08-18.
3. **Every abort signal clear throughout** (table below).

**The residual, named:** a leak slower than the window can still pass the slope row — re-read both hosts' `process_resident_memory_bytes` against their own earlier samples at ~T+24 h from the secondary converge; a material rise trips Phase 4 on the affected host. **Read the residual as a CURVE, never an endpoint pair** — two points cannot tell a leak from a step, and steps arrive as ~4 h RAMPS: sample THROUGH any step's anniversary band at 4–6 h resolution, and let no deciding read straddle the band (T0131's discharge failed four times on straddling windows before a band-avoiding pair closed it). A step the CONTROL host takes in the same window on the OLD image is environmental, not the build — measured 2026-08-19, +11.04 vs +10.07 MiB in one window.

- **Read the FLOOR, never an instantaneous sample** — `min_over_time(...[1h])` at named hours. The rotation sawtooth spans several MiB and swamps the signal.
- **Compare against the WARM floor, not the converge-time number** — RSS climbs for ~1 h after a restart as buffers fill; the cold sample manufactures a rise that means nothing.
- **Schedule the read against the EVENT BAND, not the clock, and let the band close first.** A leak arrives as a ramp of some width, and its repeat lands ~24 h later at the same clock offset. Measure step 1's width, then take the read entirely PAST that band plus jitter — a read taken inside it sees a trough and reports a plateau. T0131 refused a discharge at 26 flat hours for this reason, and T0136's first close claimed "no second step" from a read sitting inside the band; the band-clearing read found the step exactly where predicted.
- **A flat stretch alone discharges nothing** — the shape does. Two steps of decaying amplitude, each with a flat trough, is a converging allocation (T0136: +4.17 then +1.38, ratio 0.33); equal-or-growing steps are a real leak. One step and a quiet stretch cannot tell them apart, so hold the topic open rather than closing on it.
- **A restart voids the observation** — the counter is process-lifetime. Re-check `RestartCount` at every read and restart the clock if it moved.

Schedule the Slack reminder (`slack_schedule_message` — survives the session) at the **computed gate-open time**, carrying the Phase-3 checklist. The checklist opens the gate, never the reminder itself. **Skipping or degrading the gate — any of the three events unmet, or the prune only in weak form (`deleted=0`) — requires the user's explicit approval — never silently.**

### Abort signals — read on the just-converged host; any one trips the rollback decision

| Signal | Threshold | Where |
| --- | --- | --- |
| `zcrypto_logship_dropped_lines_total` | > 0 (was 0 at converge) | `127.0.0.1:9101/metrics` |
| `zcrypto_logship_last_cycle_timestamp_seconds` | stale > ~120 s | same |
| ~~`zcrypto_logship_last_success_timestamp_seconds`~~ | **not an abort signal** — it stamps only on a successful *non-empty* ship, so it goes stale whenever logging is quiet, which is what healthy looks like. Read it only as corroboration, never as a trip | same |
| `RestartCount` | > 0 on `zcrypto-capture` or `grafana-alloy` | `docker inspect --format '{{.RestartCount}}'` |
| capture stdout | any `quarantined` / `ambiguous` / `merge failed` | `docker logs` |
| newest parquet | `find <data-dir> -name '*.parquet' -mmin -3` returns 0 | host shell |
| RSS slope | materially positive vs the daemon's **own** earlier samples — never cross-host (mem limits differ: primary 2 GiB, secondary 1 GiB) | `/metrics` `process_resident_memory_bytes` |
| prune unit | anything but `Result=success` — read only AFTER the unit has run this bake (event 1 fires it): a never-run oneshot reports `Result=success` by default, which once nearly produced a false pass | `systemctl show -p Result zcrypto-capture-prune.service` |

## Phase 3 — Primary re-pin

Read all eight from the hosts and quote them before asking the user's word:

0. **The candidate is present on the PRIMARY** (`docker image ls --digests`) — re-verify even though Phase 0 pre-staged it; pull now if absent, so the converge's stop→start window never contains a pull.
1. Secondary running digest == candidate (`{{.Config.Image}}`).
2. `StartedAt` ≥ the computed window, `RestartCount` 0.
3. Capture green: all pairs flowing, no `quarantined`/`ambiguous`/`merge failed`.
4. Dead-man green: hc.io pinging; prune `Result=success`.
5. `dropped_lines_total` 0 and `last_success` fresh.
6. Alloy healthy: `prometheus_remote_storage_samples_failed_total` 0 on the host (`127.0.0.1:12345/metrics`), and `uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}' 'hc_check_up{name=~"zcrypto-capture.*"}'` returns **1 for both hosts** and 1 for both capture dead-men. Scoped to the capture checks on purpose: bare `hc_check_up` spans every ops check, and a gate an unrelated failure can block is a gate that gets waved through. Use that script — never improvise the vault decrypt; `(no series)` is not a zero.
7. `continuity.py` on a **pulled** copy (never the live dir) shows no new truncated hours — genesis hours of new streams excepted. It has to be the pulled copy for a second reason too: the capture hosts carry **no parquet reader** (no `pyarrow`, no repo CLI), so a book final cannot be opened on the host at all.
8. The bake's prune form quoted (`deleted=N`) — the weak form (`deleted=0`) needs the user's explicit acceptance here, not a Phase-5 footnote.

Then, on the user's word: converge the primary with `-e converge_primary=true -e capture_image_digest=sha256:<candidate>` and the capture tag discipline per `capture-deploys.md`.

## Phase 4 — Rollback (any abort signal, either host)

The previous-good digest is retained locally (verified in Phase 0), so rollback is a compose re-pin, no registry round-trip, ~2 min, and re-opens no data gap: edit the compose pin back → `sudo docker compose up -d` in the project dir → re-verify the positive traces (container up, ship succeeding, parquet advancing). Then stop and report — a rollback is a finding, not a retry license.

## Phase 5 — Verify by outcome

**Runs after EVERY converge, secondary included — not once at the end**, so `docs/reference/fleet-pins.md` never disagrees with a live host for the length of the bake.

After the next hour boundary: every book stream's `<HH>.parquet` begins `:00:00.0x` — read from the **pulled** copy, since the hosts have no parquet reader; the NAS archive-pull's next cycle reports `failed=0` (that IS the manifest verification); `continuity.py` on a pulled copy shows no new truncated hours (read past a new stream's genesis hour). Update `docs/reference/fleet-pins.md` in the same change — **the file is a STATE record, not a changelog**: re-true the row (digest, since, operand verified resident) and any standing constraint the converge produced, and put the converge's evidence — every check read, the values quoted, the bake form (`deleted=N`) — in that update's **COMMIT MESSAGE**, never in the file. `git log --follow` on the file is the deploy chronicle; a narrative row goes stale the moment later work lands beside it, and a stale "still owed" claim in a pins row is exactly what this convention retired.

Read the pull result with `sudo /usr/local/bin/docker logs --since <ts> zcrypto-archive-pull` on the NAS (a container, not a systemd unit; full path — `docker` is off the non-interactive ssh `PATH` there). Allow ~35 min after the hour boundary before the finals appear.

**The rollout record is not complete while the two capture hosts differ**: either the primary's leg is done, or the hold and its bound are in the pins row. A gate passed with no primary leg and no bounded hold is an open rollout that reads as finished — the state two consecutive rollouts actually left behind before this rule existed.
