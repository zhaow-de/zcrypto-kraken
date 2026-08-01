# Capture-host deploys

L2 capture is unbackfillable — mistakes on `zcrypto` (primary) / `zcrypto-red` (secondary) are permanent data loss.

## Canary rule

- **Never re-pin the primary to a capture-image digest whose secondary bake gate has not passed.** The gate is event-coverage, sized to the smallest window between the two re-pins (supersedes the fixed ≥24 h bake in older docs). Events, abort signals, checklists, the gate-open Slack reminder, and rollback are the `zcrypto-captures-rollout` skill (`.claude/skills/zcrypto-captures-rollout/SKILL.md`) — load it for every capture-image re-pin; the file is readable even where skill invocation is blocked.
- Skipping **or degrading** the gate (any event unmet, or the prune only in weak `deleted=0` form) requires the user's explicit approval — never silently.

## Deploys

- `site.yml` and `bootstrap.yml` target **both** capture hosts. The primary refuses unless you pass `-e converge_primary=true` — that flag restarts live capture and/or the engine, so mean it. It gates `--tags engine` too (a failed assert drops the host from later plays, so the engine play would silently skip). Secondary only: `--limit zcrypto-red`. Converges need `-e capture_image_digest=sha256:<...>` (no default).
- Pre-stage every converge (pull the digest on the host, verify the change is *in* the pulled image, stage the compose pin); the stop→start window contains only stop → migration-if-any → start.
- Converges run `site.yml`; `bootstrap.yml` is first-provision only. **Never run the primary un-tagged** (`--tags capture`, `--tags engine`, or `--skip-tags engine`): an untagged `--limit zcrypto` pulls in the engine play (its only host) and its digest assert fails the host closed — "fixing" that with `-e engine_image_digest=…` restarts the LIVE trade engine.
- **Adding a capture pair (`capture_pairs` in `group_vars/capture_host/vars.yml`): PRIMARY first, secondary second** — the reverse of the image-rollout order (two `--limit` runs; the capture play has no `serial:`). Secondary-first makes the reconciler "heal" the new pair's hours from the secondary into the append-only ledger and flood the gap alert — and the trades half carries no alert rule at all, so that damage lands silently; primary-first short-circuits it at any spacing. A pair-list change is **config, not a digest re-pin** — pass the currently-running digest; no bake owed.
- Verify by outcome after the next hour boundary: every book stream's `<HH>.parquet` begins at `:00:00.0x`, the NAS archive-pull loop's next pull reports `failed=0` (that IS the manifest verification — it hash-verifies every segment hourly), `infra/scripts/continuity.py` (on a pulled copy, never the live dir) shows no new truncated hours. A new stream's genesis hour is annotated and not booked, so it no longer reads as a truncation.
- **A `config.alloy` change ships only with `-e capture_alloy_digest=<currently-running>`** — the drift assert refuses an ordinary converge after a config edit. Config-only, so no bake owed.
- `dropping late event` lines right after any capture restart are healthy (resubscribe replay), not a failure signal.

## Engine converges

The engine runs on the capture primary — everything above applies (the canary gate is the digest running as *capture* on the secondary; there is no engine secondary), plus:

- **Converge only inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC): a boundary with no journal artifact, or `completed_at` outside `[B, B+30 min]`, zeroes the gate streak; a restart re-runs a missed boundary only within `[B, B+25 min]`, never later.
- **Converge only from a tree whose rendered engine config matches the fleet** — verify with `--check --diff`; an exit code cannot catch converging to the wrong state.
- Digests come from `docs/reference/fleet-pins.md`.
- Pre-flight: target port free (`ss -ltnp` — the engine publishes `127.0.0.1:9102`), `/opt/zcrypto-capture/logship-secrets.env` present (absence crash-loops the engine instead of failing the render).
- Verify by outcome: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`. The restart marker is the container's `.State.StartedAt` — never the converge command's return time.

## Ops converges (`zcrypto-ops`)

Compute tier (reconcile/backfill, panel, verify-replay, liquidations) — no canary bake owed.

- **`--limit zcrypto-ops` is mandatory** — a bare `site.yml` still runs the NAS play. Preview `--check --diff`; `daemon.json` must be unchanged (its handler bounces Alloy and the poller).
- **Omit `ops_alloy_digest` unless Alloy is the subject — a `config.alloy` edit MAKES it the subject**: pass the currently-running digest; the drift assert refuses otherwise (same on capture).
- **Pull the digest on the host first** — every runner is `--pull never` and the role has no pull task; without it every timer exits 125.
- **Record the running digest in `fleet-pins.md` before converging** — `ops_image_digest` has no repo default, so that row is the only rollback operand.
- **`ops_image_digest` also repins the liquidations compose, which the role never restarts** — the file moves, the container does not, so a later `docker compose up` rolls it unobserved. End every converge deciding explicitly whether to roll it, and prefer rolling: the running service is `liquidations-poll` (Coinalyze REST), which re-fetches a **30 h** window every cycle, so a **converge-length** restart self-heals within one cycle — verified 2026-07-31 (`skipped_at_watermark=1363`, zero gap). The bound is that window: a container left down beyond it does lose data, so this licenses the roll, not an indefinite outage. The *unbackfillable* framing belongs to the shelved Binance WS recorder, not to what runs; treating a self-healing restart as dangerous is how the pin gets left armed for someone else to trip.
- **Read a running image's digest from the container, never from the compose file** — `docker inspect --format '{{.Config.Image}}' <name>`. The 2026-07-31 pre-flight found `/etc/zcrypto-ops/alloy/compose.yaml` pinning the **ops** digest as the `grafana/alloy` image (a past converge passed `ops_alloy_digest` the value of `ops_image_digest`); the container was fine, so the damage was armed rather than fired, and any `docker compose up` there would have taken ops telemetry dark. Nothing catches it: the drift assert checksums `config.alloy` and runs only when `ops_alloy_digest` is *omitted*, so passing the wrong digest renders silently and exits 0.
- **Verify by outcome** at the next tick: `ops_archive_pull_exit_code` / `ops_panel_exit_code` 0, `reconcile.prom` mtime advanced, reconcile counters unchanged, `hc_checks_down_total` 0.
- Rollback = re-converge to the recorded digest. Expect `zcrypto_reconcile_healable_gap_seconds_total` to fall, which suppresses the degrading-primary rule for 24 h via its own `resets()` guard.

### Panel generation changes

A `SCHEMA_VERSION` bump makes `_check_generation` refuse until the tree is regenerated; regeneration is delete-and-rebuild, never part of a converge.

- **Size the window from the tree** — ~2.1 s per MB of input, single-threaded. Finish clear of the 02:25 UTC auto-reboot; `Type=oneshot` has no start timeout, so only the reboot kills a long run.
- **Pause the healthchecks.io panel check, time-boxed, and un-pause explicitly** — it pings only on `rc=0`, and it is the timer's only liveness signal. The panel exit-code and ops ERROR-log rules also fire throughout.
- **Delete both copies** — the NAS pull is `rsync -a` with no `--delete`, so an ops-side delete never propagates.
- **Delete out-of-scope subtrees too.** The sweep is `PANEL_QUOTE`-scoped, so a pair outside it survives at the old generation beside the new; `_check_generation`'s tree scan refuses the next materialize until it is gone.
- **Stop the timer BEFORE the converge AND again after** — before, or an in-window tick fires the half-converged unit; again after, because the role's enable-and-start task silently turns it back on. Verify the second stop (`disabled`, `inactive`, absent from `systemctl list-timers`) **before the next tick is due** — read that deadline from `systemctl list-timers`, never assume it is far off. Then run the regeneration inside the unit, so a stray trigger is a no-op rather than a second writer.
- **Regeneration is the point of no return** — the previous image cannot read the new generation and no old tree survives, so rollback is another full rebuild. Take the user's word there, not at the converge.

## Retiring an alert rule

- **Deleting a rule from `infra/grafana/alerts.yaml` does not retire it** — `grafana-push.sh` upserts and never deletes; the removed rule keeps evaluating and emailing. Retiring needs `GRAFANA_PRUNE=1`, and the orphan report must name exactly the uid you mean before you run it.
- **Never prune the superseded rule until its replacement has a verified first sample** — the prune is irreversible, and between it and the first post-converge tick nothing covers the signal at all.
- **Verify that first sample by VALUE, not presence** — `delta()`/`increase()` are blind to a condition already present in a series' first sample, so a fault born in the deploy window is baked into the baseline and never fires. Read the number and triage a nonzero as the page it would otherwise have been.
- Order every rule-replacing deploy: converge → push → verify the value → prune → confirm the old uid 404s.

## Ansible secrets

- **Never run `ansible-inventory --host` or `--list`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so both silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- Run playbooks via `infra/ansible/scripts/run.sh` (loads the vaulted deploy key into a throwaway agent). Preview with `--check --diff` before any converge.
