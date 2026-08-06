# Capture-host deploys

L2 capture is unbackfillable — mistakes on `zcrypto` (primary) / `zcrypto-red` (secondary) are permanent data loss.

## Canary rule

- **Never re-pin the primary to a capture-image digest whose secondary bake gate has not passed.** The capture role now refuses this mechanically for **capture** re-pins — a primary re-pin whose digest the secondary is not running fails the play (emergency bypass `-e canary_override="<reason>"`, reason-required); the engine role refuses an **engine** re-pin the same way — there is no engine secondary, so the secondary's capture bake IS the engine's gate (same `canary_override`). The gate is event-coverage, sized to the smallest window between the two re-pins (supersedes the fixed ≥24 h bake in older docs). Events, abort signals, checklists, the gate-open Slack reminder, and rollback are the `zcrypto-captures-rollout` skill (`.claude/skills/zcrypto-captures-rollout/SKILL.md`) — load it for every capture-image re-pin; the file is readable even where skill invocation is blocked.
- Skipping **or degrading** the gate (any event unmet, or the prune only in weak `deleted=0` form) requires the user's explicit approval — never silently.

## Deploys

- `site.yml` and `bootstrap.yml` target **both** capture hosts. The primary refuses unless you pass `-e converge_primary=true` — that flag restarts live capture and/or the engine, so mean it. It gates `--tags engine` too (a failed assert drops the host from later plays, so the engine play would silently skip). Secondary only: `--limit zcrypto-red`. Converges need `-e capture_image_digest=sha256:<...>` (no default).
- Pre-stage every converge: verify the change is *in* the pulled image and stage the compose pin — the roles' digest preflights refuse a digest the host has not pulled; the stop→start window contains only stop → migration-if-any → start.
- Converges run `site.yml`; `bootstrap.yml` is first-provision only — both refuse mechanically: `site.yml` refuses an un-tagged run on the live primary (a bare run pulls in the engine play and can restart the LIVE trade engine; only `--tags` naming plays or `--skip-tags engine` satisfy it), `bootstrap.yml` refuses an already-provisioned host without `-e rebootstrap=true`.
- **Adding a capture pair (`capture_pairs` in `group_vars/capture_host/vars.yml`): PRIMARY first, secondary second** — the capture role refuses a secondary-first add (delegated read of the primary's deployed pairs; fail-closed when the primary is unreachable) — secondary-first floods the append-only ledger with false heals, silently on the trades half. A pair-list change is **config, not a digest re-pin** — pass the currently-running digest; no bake owed.
- Verify by outcome after the next hour boundary: every book stream's `<HH>.parquet` begins at `:00:00.0x`, the NAS archive-pull loop's next pull reports `failed=0` (that IS the manifest verification — it hash-verifies every segment hourly), `infra/scripts/continuity.py` (on a pulled copy, never the live dir) shows no new truncated hours. A new stream's genesis hour is annotated and not booked, so it no longer reads as a truncation.
- **A `config.alloy` change ships only with `-e capture_alloy_digest=<currently-running>`** — the drift assert refuses an ordinary converge after a config edit. Config-only, so no bake owed.
- `dropping late event` lines right after any capture restart are healthy (resubscribe replay), not a failure signal.

## Engine converges

The engine runs on the capture primary — everything above applies (the canary gate is the digest running as *capture* on the secondary; there is no engine secondary, and the engine role enforces that gate mechanically), plus:

- **Converge only inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC) — `site.yml` re-asserts the window at task execution time (bypass `-e engine_window_override="<reason>"`), so a backgrounded converge can no longer land late; when the boundary cycle has journaled its completion, the floor is 5 min past that completion — usually earlier than B+30, later only when the cycle ran long (deliberate clearance). A boundary with no journal artifact, or `completed_at` outside `[B, B+30 min]`, zeroes the gate streak; a restart re-runs a missed boundary only within `[B, B+25 min]` **and only while that boundary has NO journal artifact** — a `cycle-<HH>.json` *or* a `failed-cycle-<HH>.json` (a failed cycle writes its sidecar) makes the re-run impossible at any time, so a failed boundary is never retried.
- **Converge only from a tree whose rendered engine config matches the fleet** — verify with `--check --diff`; an exit code cannot catch converging to the wrong state.
- Digests come from `docs/reference/fleet-pins.md` — the roles refuse to replace a running digest the file does not record (bypass `-e pins_override="<reason>"`).
- Pre-flight is mechanized: the engine role refuses a restart without `/opt/zcrypto-capture/logship-secrets.env` (absence crash-loops the engine) and records the `:9102` holder in the play log.
- Verify by outcome: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`. The restart marker is the container's `.State.StartedAt` — never the converge command's return time.

## Ops converges (`zcrypto-ops`)

Compute tier (reconcile/backfill, panel, verify-replay, liquidations) — no canary bake owed.

- **`--limit zcrypto-ops` is mandatory** — a bare `site.yml` still runs the NAS play; `converge.sh` refuses the bare form and previews first. A `daemon.json` diff now refuses to apply without `-e daemon_json_ack=true` — the docker role renders to a probe path and shows the diff before asking (its handler bounces Alloy and the poller); the docker role is shared, so the same ack gates capture-host converges too.
- **Omit `ops_alloy_digest` unless Alloy is the subject — a `config.alloy` edit MAKES it the subject**: pass the currently-running digest; the drift assert refuses otherwise (same on capture).
- **Pull the digest on the host first** — every runner is `--pull never`; the ops role's digest preflight refuses a digest the host has not pulled.
- **Record the running digest in `fleet-pins.md` before converging** — the pins assert refuses otherwise; that row is the only rollback operand (`ops_image_digest` has no repo default).
- **`ops_image_digest` also repins the liquidations compose, which the role never restarts** — the role refuses the repin without `-e liquidations_decision=roll-after|defer`. Prefer `roll-after`: the poller re-fetches a **30 h** window every cycle, so a converge-length restart self-heals within one cycle (verified 2026-07-31); a container down beyond that window does lose data, and the *unbackfillable* framing belongs to the shelved Binance WS recorder, not the running poller.
- **Read a running image's digest from the container, never from the compose file** — `docker inspect --format '{{.Config.Image}}' <name>`. The 2026-07-31 pre-flight found `/etc/zcrypto-ops/alloy/compose.yaml` pinning the **ops** digest as the `grafana/alloy` image (a past converge passed `ops_alloy_digest` the value of `ops_image_digest`); the container was fine, so the damage was armed rather than fired, and any `docker compose up` there would have taken ops telemetry dark. Nothing catches it: the drift assert checksums `config.alloy` and runs only when `ops_alloy_digest` is *omitted*, so passing the wrong digest renders silently and exits 0.
- **Verify by outcome** at the next tick: run `infra/scripts/ops-postverify.sh` — six checks in one command; `(no series)` reads FAIL, never a zero.
- Rollback = re-converge to the recorded digest. Expect `zcrypto_reconcile_healable_gap_seconds_total` to fall, which suppresses the degrading-primary rule for 24 h via its own `resets()` guard.

### Panel generation changes

A `SCHEMA_VERSION` bump makes `_check_generation` refuse until the tree is regenerated; regeneration is delete-and-rebuild, never part of a converge.

- **Regenerate only through `zcrypto-panel-regenerate`** (on the ops host) — it stops the timer, sizes the window from the tree and refuses when the ETA crosses the 02:25 UTC auto-reboot, takes the healthchecks.io pause as a typed gate before anything is deleted, deletes the whole ops-side panel root (out-of-scope subtrees included), rebuilds inside the materialize unit so a stray tick is a no-op, restarts the timer only on success, and prints the un-pause + **conditional** NAS-delete checklist for the halves it cannot reach — follow it as printed; the delete is owed only on a path-changing rebuild (a schema/ladder bump rewrites identical paths and orphans nothing), and a NAS-only file can be an unanchored hour's last copy, so never delete unmeasured.
- A converge during a regeneration window still needs `-e ops_panel_timer_hold=true` — the role's enable-and-start task re-arms the timer otherwise.
- **Regeneration is the point of no return** — the previous image cannot read the new generation and no old tree survives, so rollback is another full rebuild. Take the user's word there, not at the converge.

## Retiring an alert rule

- **Deleting a rule from `infra/grafana/alerts.yaml` does not retire it** — `grafana-push.sh` upserts and never deletes; the removed rule keeps evaluating and emailing. Retiring needs `GRAFANA_PRUNE=1`, and the orphan report must name exactly the uid you mean before you run it.
- **Never prune the superseded rule until its replacement has a verified first sample** — the prune is irreversible, and between it and the first post-converge tick nothing covers the signal at all.
- **Verify that first sample by VALUE, not presence** — `delta()`/`increase()` are blind to a condition already present in a series' first sample, so a fault born in the deploy window is baked into the baseline and never fires. Read the number and triage a nonzero as the page it would otherwise have been.
- Order every rule-replacing deploy: converge → push → verify the value → prune → confirm the old uid 404s.

## Ansible secrets

- **Never run `ansible-inventory --host`, `--list`, or `--graph --vars`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so all three silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext — and `vault-pass.sh` itself now refuses those ancestries. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- Converge via `infra/ansible/scripts/converge.sh` — it requires `--limit`, runs and displays the `--check --diff` preview, and takes a typed confirm of the limit value before the real pass (`run.sh` underneath loads the vaulted deploy key; preview-only: pass `--check`).
