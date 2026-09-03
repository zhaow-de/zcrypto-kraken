---
name: zcrypto-rollout-image
description: Attended canary rollout of the app-image digest — capture secondary, event-sized bake with abort signals, then capture primary and engine in one shot — with preflight, rollback and verify-by-outcome; plus every tier's image-converge mechanics (engine window, ops, panel regeneration, NAS). User-invoked only.
disable-model-invocation: true
---

# zcrypto-rollout-image

The executable form of the app-image canary rollout: the one image serves capture, engine, ops and the NAS, and this is how a new digest reaches the capture hosts and the engine. L2 capture is unbackfillable — a mistake on either host is permanent data loss. The canary phases are for capture-image digest re-pins; the sections after Phase 5 carry every other image converge on the fleet. A pair-list change is config (primary-first, no bake — below).

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
- Immediate checks: container up with `RestartCount` 0, all pairs subscribed with zero subscribe errors, parquet advancing. `dropping late event` lines right after start are healthy **restart** replay, not a failure — the writer re-seeds its floor from the segments already on disk, and the first subscription's trade snapshot replays prints from before that boundary. **`zcrypto_capture_reconnects_total` reads 0 for this, and that is correct** — a first connect that succeeds increments nothing, so a zero there is never evidence against the benign reading. The same lines *during* a run are reconnect replay, and that is what the counter answers for. Either way, never read how often it happens off a count of these lines.

## Phase 2 — The bake gate: the smallest window that covers the events

**The gate is event-coverage — never a fixed duration: the smallest window between the two re-pins that satisfies all three.** Compute the window, state it for the user's word, then start it:

1. **A clean prune under the new image** — the one recurring writer that mutates the capture dir concurrently with the daemon. Do not wait for 03:17: `sudo systemctl start zcrypto-capture-prune.service` on the just-converged host fires it now. **Read `deleted=N` in the result**: `deleted=0` exercises the scan but never the deletion path (the weak form) — note which form the bake got, and prefer a host/day where the archive age yields a deleting prune.
2. **≥3 full segment-rotation hours** — the first hour's every book `<HH>.parquet` beginning at `:00:00.0x` proves the boundary write; three full hours separate a real trend from the rotation sawtooth. **FULL hours only — hours that BEGIN after the re-pin; the converge's own partial hour never counts** (re-pin at 14:07 → hours 15/16/17 → gate 18:00Z). Counting boundaries instead of full hours reads the gate an hour early.
3. **Every abort signal clear throughout** (table below).

**Gate-close is PASSED.** The three events met with nothing tripped → the primary follows. The gate is hard-capped at the window the events define; nothing after gate-close is owed to the rollout. **The bake qualifies the IMAGE as a runtime** (deps, base layers, entrypoint, memory, shipping) — always — and the capture code when it changed; an engine payload's own proof is its next disarmed boundary cycles, never the bake.

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

After the next hour boundary: every book stream's `<HH>.parquet` begins `:00:00.0x` — read from the **pulled** copy, since the hosts have no parquet reader; the NAS archive-pull's next cycle reports `failed=0` (that IS the manifest verification); `continuity.py` on a pulled copy shows no new truncated hours (read past a new stream's genesis hour). The converge's machine line is already in `docs/reference/deploy-log.jsonl` — `converge.sh` appends it — so the pins row is re-trued **from that line**, never re-typed. **Commit that line in the same change as the row it feeds** — until it is committed, the only record of a production converge lives in a working tree that `git stash`, `git checkout --` and `git clean` all discard, and `mutate-probe.sh` refuses to run beside. Update `docs/reference/fleet-pins.md` in the same change — **the file is a STATE record, not a changelog**: re-true the row (digest, since, operand verified resident) and any standing constraint the converge produced, and put the converge's evidence — every check read, the values quoted, the bake form (`deleted=N`) — in that update's **COMMIT MESSAGE**, never in the file. `git log --follow` on the file is the deploy chronicle; a narrative row goes stale the moment later work lands beside it.

Then prune that host's stale images — `uv run python infra/scripts/prune-host-images.py <host>`, then `--apply` — **after** its row is written, never before, and only for the host that just converged; `--keep <digest12>` for anything pre-staged for the leg still to come.

Read the pull result with `sudo /usr/local/bin/docker logs --since <ts> zcrypto-archive-pull` on the NAS (a container, not a systemd unit; full path — `docker` is off the non-interactive ssh `PATH` there). Allow ~35 min after the hour boundary before the finals appear.

**One PR per rollout, two commits** — the secondary's row, then the primary's and the engine's — merged before any other branch can touch `fleet-pins.md`, `deploy-log.jsonl` or `fleet.md` — same day is the default, not a gate: the converge-and-bake window's minimality is the invariant, the calendar day is not — and **never branch other work from it**: a recording branch that lives for days collects everyone else's commits. **The rollout record is not complete while the two capture hosts differ**: either the primary's leg is done, or the hold and its bound are in the pins row. A gate passed with no primary leg and no bounded hold is an open rollout that reads as finished.

______________________________________________________________________

# The other converges

The canary phases above are for capture-image digest re-pins. The rest of the fleet's image-converge procedure follows; the invariants that must hold before this file is open are in `fleet-deploys.md`.

## Every image converge

- `site.yml` and `bootstrap.yml` target **both** capture hosts. `-e converge_primary=true` also gates `--tags engine` — a failed assert drops the host from later plays, so the engine play silently skips. Secondary only: `--limit zcrypto-red`. Converges need `-e capture_image_digest=sha256:<...>` (no default).
- `bootstrap.yml` is first-provision only; it refuses an already-provisioned host without `-e rebootstrap=true`. `site.yml` refuses an un-tagged run on the live primary — only `--tags` naming plays or `--skip-tags engine` satisfy it.
- **Adding a capture pair** (`capture_pairs` in `group_vars/capture_host/vars.yml`): the capture role reads the primary's deployed pairs and refuses a secondary-first add, fail-closed when the primary is unreachable — secondary-first floods the append-only ledger with false heals, silently on the trades half. Pass the currently-running digest; no bake owed.
- A new stream's genesis hour is annotated and not booked, so it does not read as a truncation in `continuity.py`.

## Shared converge mechanics

This block is duplicated verbatim in `zcrypto-rollout-image` and `zcrypto-bump-alloy` — deliberately, so neither skill depends on the other being loaded. Edit both.

- Converge via `infra/ansible/scripts/converge.sh` — it requires `--limit`, runs and displays the `--check --diff` preview, and takes a typed confirm of the limit value before the real pass (`run.sh` underneath loads the vaulted deploy key; preview-only: pass `--check`). `--limit` is mandatory for ops too: a bare `site.yml` still runs the NAS play; `converge.sh` refuses the bare form.
- Digests come from `docs/reference/fleet-pins.md` — the roles refuse to replace a running digest the file does not record (`-e pins_override="<reason>"` bypasses). Pull the digest on the host first: every runner is `--pull never`, and every role's digest preflight refuses a digest the host has not pulled.
- **Read a running image's digest from the container, never from the compose file** — `docker inspect --format '{{.Config.Image}}' <name>` (`{{.Image}}` is host-dependent and lies under classic storage): a compose file can pin the wrong image while the container runs the right one, and the mistake fires at the next `docker compose up`.
- **A `config.alloy` edit makes Alloy the subject**: pass the currently-running Alloy digest (`capture_alloy_digest` / `ops_alloy_digest`) or the drift assert refuses the converge; omit the flag entirely otherwise — an EMPTY `-e …_digest=` still counts as defined and renders a broken image ref. The drift assert compares the deployed file, not what the running container loaded, so a converge that never recreates the container passes every assert while a new family stays dark: **a new metric family needs the host's keep-regex edit and a first scrape verified by VALUE** — `uv run python infra/scripts/grafana-query.py '<family>{host="<host>"}'`; `(no series)` is FAIL, never a zero.
- A `daemon.json` diff refuses to apply without `-e daemon_json_ack=true` — the docker role renders to a probe path and shows the diff before asking (its handler bounces Alloy and the poller); the role is shared, so the ack gates every host.
- **`fleet-pins.md` is a STATE record.** `converge.sh` appends every real pass to `docs/reference/deploy-log.jsonl`; re-true the row from that line — never from memory — commit the line with the row, and put the converge's evidence (every check read, the values quoted) in the commit message, never in the file. `git log --follow` on the file is the deploy chronicle.
- **Images are removed only by `uv run python infra/scripts/prune-host-images.py <host>`, then `--apply`, after that host's new pins row is written and only for the host that just converged** — a capture host stops appending at 1 GiB free; nothing distinguishes a pre-staged image from a stale one, so `--keep <digest12>` anything staged for a leg still to come.
- Verify by outcome, never by exit code. Ops: `infra/scripts/ops-postverify.sh`, every check in one command. Capture: on the pulled copy, every book stream's `<HH>.parquet` begins at the hour; the NAS pull's next cycle reports `failed=0` (that IS the manifest verification — fresh segments are hash-verified on arrival, and whole-archive coverage completes within 24 pull cycles under the incremental hash scope); `infra/scripts/continuity.py` on a pulled copy, never the live dir, shows no new truncated hours. Engine: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`; the restart marker is the container's `.State.StartedAt`, never the converge command's return time.
- **The ops and capture roles RENDER the Alloy compose file and never restart the container for it** — `render the alloy compose file` carries no `notify:` at all, and even the `config.alloy` render's `reload alloy` handler is an HTTP `POST /-/reload` that never re-reads container env or `memory:` (its own comment says the same about `alloy-secrets.env`). A change to Alloy's `environment` or `memory:` (a cap, GOMEMLIMIT, …) therefore needs `sudo docker compose up -d` in `/etc/zcrypto-ops/alloy` or `/etc/zcrypto-capture/alloy` after the converge — verify on the container: `.State.StartedAt` postdates the render, plus a SCOPED `docker exec grafana-alloy sh -c 'echo $GOMEMLIMIT'` and `docker inspect --format '{{.HostConfig.Memory}}' grafana-alloy` — never `docker inspect --format '{{json .Config.Env}}'`, which prints the Grafana Cloud credentials. No metric-side proof exists: `config.alloy` drops `go_.*` and the keep-list does not re-admit `go_gc_gomemlimit_bytes`.

## Engine converges

The engine runs on the capture primary — the canary phases apply (the gate is the digest running as *capture* on the secondary; there is no engine secondary, and the engine role enforces that gate mechanically), plus:

- **The inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC): once the boundary cycle has journaled its completion, the floor is 5 min past that completion — usually earlier than B+30, later only when the cycle ran long. A boundary with no journal artifact, or `completed_at` outside `[B, B+30 min]`, zeroes the gate streak; a restart re-runs a missed boundary only within `[B, B+25 min]` **and only while that boundary has NO journal artifact** — a `cycle-<HH>.json` *or* a `failed-cycle-<HH>.json` makes the re-run impossible at any time, which is why a failed boundary is never retried.
- **Converge only from a tree whose rendered engine config matches the fleet** — verify with `--check --diff`; an exit code cannot catch converging to the wrong state.
- **An engine re-pin whose revision also touches `roles/capture/files/config.alloy` never converges `--tags engine` alone** — the keep-list and its drift assert live in the *capture* role, so the new families publish unadmitted and silently; run `--tags capture,engine` with `-e capture_image_digest=<currently-running> -e capture_alloy_digest=<currently-running>`, then verify the new family by VALUE at the next scrape (`uv run python infra/scripts/grafana-query.py '<family>{host="zcrypto"}'`). The drift assert compares the deployed file, not what the running container loaded, so a converge that never recreates the container passes every assert while the family stays dark.
- Same-day `--tags capture,engine` on the primary once the secondary's gate closes is the default shape.
- Pre-flight is mechanized: the engine role refuses a restart without `/opt/zcrypto-capture/logship-secrets.env` (absence crash-loops the engine) and records the `:9102` holder in the play log.
- **A basket widening must hand-stage the new legs BEFORE the engine converge — no converge does it.** The store delivery is only-when-absent, guarded on `store/BTC` existing, so it silently SKIPS on a live host and the start guard (which tests every `BASKET` symbol × grid) then refuses to start the engine. `zcrypto engine seed` is workstation-only — the image carries no canonical dataset. Seed on the workstation, copy the new legs to `<engine_state_dir>/store` as `zcrypto-engine:zcrypto-engine` `0640`, and read one back **as the engine's own uid** (`docker inspect --format '{{.Config.User}}' zcrypto-engine`): the guard tests existence only, so a truncated or wrong-owner file passes it.
- **Canonical cannot always seed a new leg** — `data/ohlc-full` is frozen at its last quarterly dump, and a leg whose canonical tail predates Kraken's REST window by more than the overlap cannot be bridged. Seed such a leg REST-only and say so in the pins row; check the gap before planning the window, not at the seam-QA failure.
- Verify by outcome: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`. The restart marker is the container's `.State.StartedAt` — never the converge command's return time.

## Ops converges (`zcrypto-ops`)

Compute tier (reconcile/backfill, panel, verify-replay, liquidations) — no canary bake owed.

- **Record the running digest in `fleet-pins.md` before converging** — the pins assert refuses otherwise; that row is the only rollback operand (`ops_image_digest` has no repo default).
- **`ops_image_digest` also repins the liquidations compose, which the role never restarts** — the role refuses the repin without `-e liquidations_decision=roll-after|defer`. Prefer `roll-after`: the poller re-fetches a **30 h** window every cycle, so a converge-length restart self-heals; a container down longer than that window loses data.
- Rollback = re-converge to the recorded digest. Expect `zcrypto_reconcile_healable_gap_seconds_total` to fall, which suppresses the degrading-primary rule for 24 h via its own `resets()` guard.

### Panel generation changes

A `SCHEMA_VERSION` bump makes `_check_generation` refuse until the tree is regenerated; regeneration is delete-and-rebuild, never part of a converge.

- **Regenerate only through `zcrypto-panel-regenerate`** (on the ops host) and follow its printed checklist — the script documents its own mechanics. Two decisions it leaves to you: the NAS delete is owed only on a path-changing rebuild (a schema/ladder bump rewrites identical paths and orphans nothing), and a NAS-only file can be an unanchored hour's last copy, so never delete unmeasured.
- A converge during a regeneration window still needs `-e ops_panel_timer_hold=true` — the role's enable-and-start task re-arms the timer otherwise; the flag does not *stop* an already-armed timer, so time the converge just after a clean `:22` tick.
- The previous image cannot read the new generation — take the user's word at the regeneration, not at the converge.

## NAS converges (`nas`)

The archive-pull tier — outside the canary regime (no secondary, no bake owed); converges are `--limit nas`, and the pin is `nas_capture_image` in `infra/ansible/host_vars/nas/vars.yml`, the one committed capture-image pin.

- **There is no `nas_alloy_digest`** — the Alloy pin here is `nas_alloy_image`, and the capture/ops currently-running-digest discipline does not transfer: passing it is silently accepted as an unused extra var. The role deploys `infra/nas/config.alloy` unconditionally but restarts Alloy only under `-e nas_apply_compose=true`, which every apply task is gated on; without that flag the converge is render-only and the new config sits on disk unread.

- **Every NAS converge that RECREATES the archive-pull container replays the whole gate-export cold** — the cache is `--cache /tmp/gate-cache.json` and `/tmp` is on none of the container's mounts, so a recreate takes it whatever the fingerprint says. `-e nas_apply_compose=true` with a changed pin or compose recreates; an apply that changes nothing only restarts, and `/tmp` survives a restart. A **fingerprint-invalidating pin** (any change inside the transitive `cli.*` replay closure that `gate_cache.py` digests — e.g. `journal.py`) forces the same replay without a recreate, so `replay_fingerprint()` matching across both images buys nothing when the converge recreates anyway. Budget the better part of an hour, growing with the journal, and size the window from the current figure in `docs/reference/fleet-pins.md`'s standing constraint, re-measured — never a remembered or older figure.
