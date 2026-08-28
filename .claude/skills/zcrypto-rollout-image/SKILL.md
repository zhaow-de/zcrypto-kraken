---
name: zcrypto-rollout-image
description: Attended canary rollout of the app-image digest — capture secondary, event-sized bake with abort signals, then capture primary and engine in one shot — with preflight, rollback and verify-by-outcome. User-invoked only.
disable-model-invocation: true
---

# zcrypto-rollout-image

The executable form of the app-image canary rollout: the one image serves capture, engine, ops and the NAS, and this is how a new digest reaches the capture hosts and the engine. L2 capture is unbackfillable — a mistake on either host is permanent data loss. Scope: **digest re-pins only**; a pair-list change is config (primary-first, no bake — `fleet-deploys.md`), and engine converges are their own section there.

## Ground rules

- **Every host-touching command runs in the main loop as a plain command — never inside a dispatched subagent or background workflow.** The permission gate blocks ssh-sudo there and the step dies where nobody sees the prompt; the user grants access live, at the command.
- **Every irreversible action** — converge, re-pin, restart — takes the user's explicit word at that step, with the blocker sweep (open-topics index + memo) presented alongside (`agent-ops.md`).
- Rollout order: **secondary first, primary last.**
- Digest identity is always `{{.Config.Image}}` — `{{.Image}}` is host-dependent and lies under classic storage.
- Converges via `infra/ansible/scripts/converge.sh` — it requires `--limit`, shows the `--check --diff` preview, and takes a typed confirm before the real pass (preview-only: pass `--check`); never wrap it in `timeout` (attended by design; the orphaned child would converge unsupervised); never run the primary un-tagged; `-e converge_primary=true` restarts live capture — mean it. Vault and inspect-scoping invariants: `fleet-deploys.md` and CLAUDE.md `## Secrets`.

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
2. **≥3 full segment-rotation hours** — the first hour's every book `<HH>.parquet` beginning at `:00:00.0x` proves the boundary write; three full hours separate a real trend from the rotation sawtooth. **FULL hours only — hours that BEGIN after the re-pin; the converge's own partial hour never counts** (re-pin at 14:07 → hours 15/16/17 → gate 18:00Z). Counting boundaries instead of full hours reads the gate an hour early.
3. **Every abort signal clear throughout** (table below).

**Gate-close is PASSED.** The three events met with nothing tripped → the primary follows. The gate is hard-capped at the window the events define; nothing after gate-close is owed to the rollout.

**Memory is not a gate event.** `zcrypto-fleet-memory-headroom`, `zcrypto-fleet-memory-leak` and `zcrypto-fleet-daemon-restarted` watch every daemon continuously and fleet-wide — before, during and after any rollout — so a bake owes no RSS read at T+anything, and no read is ever "voided" by the next converge. During the bake, the headroom rule firing on the just-converged host is an abort signal (table below). A leak page days later names the image through `docs/reference/fleet-pins.md`'s `since` column and `docs/reference/deploy-log.jsonl`, and the rollback operand is in the same row.

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
| `zcrypto-fleet-memory-headroom` | any instance on the just-converged host | the rule's state in Grafana / Slack — the RSS row used to be a hand-read slope; the rule reads it against the container limit |
| prune unit | anything but `Result=success` — read only AFTER the unit has run this bake (event 1 fires it): a never-run oneshot reports `Result=success` by default | `systemctl show -p Result zcrypto-capture-prune.service` |

## Phase 3 — Primary re-pin

Read all eight from the hosts and quote them before asking the user's word:

0. **The candidate is present on the PRIMARY** (`docker image ls --digests`) — re-verify even though Phase 0 pre-staged it; pull now if absent, so the converge's stop→start window never contains a pull.
1. Secondary running digest == candidate (`{{.Config.Image}}`).
2. `StartedAt` ≥ the computed window, `RestartCount` 0.
3. Capture green: all pairs flowing, no `quarantined`/`ambiguous`/`merge failed`.
4. Dead-man green: hc.io pinging; prune `Result=success`.
5. `dropped_lines_total` 0 and `last_cycle` fresh (stale > ~120 s is the trip); `last_success` is corroboration only, per the abort table.
6. Alloy healthy: `prometheus_remote_storage_samples_failed_total` 0 on the host (`127.0.0.1:12345/metrics`), and `uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}' 'hc_check_up{name=~"zcrypto-capture.*"}'` returns **1 for both hosts** and 1 for both capture dead-men. Scoped to the capture checks on purpose: bare `hc_check_up` spans every ops check. Use that script — never improvise the vault decrypt; `(no series)` is not a zero.
7. `continuity.py` on a **pulled** copy (never the live dir) shows no new truncated hours — genesis hours of new streams excepted. The capture hosts carry **no parquet reader** (no `pyarrow`, no repo CLI), so a book final cannot be opened on the host at all.
8. The bake's prune form quoted (`deleted=N`) — the weak form (`deleted=0`) needs the user's explicit acceptance here, not a Phase-5 footnote.

Then, on the user's word: converge the primary with `-e converge_primary=true -e capture_image_digest=sha256:<candidate>` and the capture tag discipline per `fleet-deploys.md`.

## Phase 4 — Rollback (any abort signal, either host)

The previous-good digest is retained locally (verified in Phase 0), so rollback is a compose re-pin, no registry round-trip, ~2 min, and re-opens no data gap: edit the compose pin back → `sudo docker compose up -d` in the project dir → re-verify the positive traces (container up, ship succeeding, parquet advancing). Then stop and report — a rollback is a finding, not a retry license.

## Phase 5 — Verify by outcome

**Runs after EVERY converge, secondary included — not once at the end**, so `docs/reference/fleet-pins.md` never disagrees with a live host for the length of the bake.

After the next hour boundary: every book stream's `<HH>.parquet` begins `:00:00.0x` — read from the **pulled** copy, since the hosts have no parquet reader; the NAS archive-pull's next cycle reports `failed=0` (that IS the manifest verification); `continuity.py` on a pulled copy shows no new truncated hours (read past a new stream's genesis hour). The converge's machine line is already in `docs/reference/deploy-log.jsonl` — `converge.sh` appends it — so the pins row is re-trued **from that line**, never re-typed. Update `docs/reference/fleet-pins.md` in the same change — **the file is a STATE record, not a changelog**: re-true the row (digest, since, operand verified resident) and any standing constraint the converge produced, and put the converge's evidence — every check read, the values quoted, the bake form (`deleted=N`) — in that update's **COMMIT MESSAGE**, never in the file. `git log --follow` on the file is the deploy chronicle; a narrative row goes stale the moment later work lands beside it.

Then prune that host's stale images — `uv run python infra/scripts/prune-host-images.py <host>`, then `--apply` — **after** its row is written, never before, and only for the host that just converged; `--keep <digest12>` for anything pre-staged for the leg still to come.

Read the pull result with `sudo /usr/local/bin/docker logs --since <ts> zcrypto-archive-pull` on the NAS (a container, not a systemd unit; full path — `docker` is off the non-interactive ssh `PATH` there). Allow ~35 min after the hour boundary before the finals appear.

**One PR per rollout, two commits** — the secondary's row, then the primary's and the engine's — merged within the day, and **never branch other work from it**: a recording branch that lives for days collects everyone else's commits. **The rollout record is not complete while the two capture hosts differ**: either the primary's leg is done, or the hold and its bound are in the pins row. A gate passed with no primary leg and no bounded hold is an open rollout that reads as finished.
