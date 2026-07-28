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
- Verify by outcome after the next hour boundary: every book stream's `<HH>.parquet` begins at `:00:00.0x`, the NAS archive-pull loop's next pull reports `failed=0` (that IS the manifest verification — it hash-verifies every segment hourly), `infra/scripts/continuity.py` (on a pulled copy, never the live dir) shows no new truncated hours. **Exception — a NEW stream's genesis hour** starts mid-hour by construction: one truncated hour, up to ~3600 s booked gap, first `<HH>.parquet` not at `:00:00.0x` — expected once per new stream, not a failure; `continuity.py` has no genesis carve-out, so read past it.
- `dropping late event` lines right after a restart are healthy (resubscribe replay), not a failure signal.

## Engine converges

The engine runs on the capture primary — everything above applies (the canary gate is the digest running as *capture* on the secondary; there is no engine secondary), plus:

- **Converge only inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC): a boundary with no journal artifact, or `completed_at` outside `[B, B+30 min]`, zeroes the gate streak; a restart re-runs a missed boundary only within `[B, B+25 min]`, never later.
- **Converge only from a tree whose rendered engine config matches the fleet** — verify with `--check --diff`; an exit code cannot catch converging to the wrong state.
- Digests come from `docs/reference/fleet-pins.md`.
- Pre-flight: target port free (`ss -ltnp` — the engine publishes `127.0.0.1:9102`), `/opt/zcrypto-capture/logship-secrets.env` present (absence crash-loops the engine instead of failing the render).
- Verify by outcome: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`. The restart marker is the container's `.State.StartedAt` — never the converge command's return time.

## Ops converges (`zcrypto-ops`)

The compute tier: archive reconcile/backfill, panel materialize, verify-replay, liquidations. Not the unbackfillable capture path, so no canary bake — but it has its own traps, each of which has bitten or was measured about to.

- **`--limit zcrypto-ops` is mandatory.** The ops play has no `converge_primary` guard; a bare `site.yml` fails the capture hosts closed on their digest assert but **still runs the NAS play**. Preview with `--check --diff` and read it: `daemon.json` must be unchanged, or the handler bounces Alloy and the poller mid-cycle. Omit `ops_alloy_digest` unless Alloy is the subject — leaving it undefined skips that block and its secrets render.
- **Pre-pull the digest on the host.** Every runner is `docker run --pull never`, and the role has **no pull task** — miss it and every timer exits 125 at the next tick.
- **Record the running digest in `fleet-pins.md` BEFORE converging.** `ops_image_digest` has no repo default, so that row is the only rollback operand that exists.
- **The ops image is the CAPTURE image repo.** Never read one service's pin as the other's.
- **`ops_image_digest` also repins the liquidations compose, which the role never restarts** — after a converge the file points at the new digest while the container runs the old one, until some later `docker compose up -d` silently rolls a stream that is not backfillable. End every converge with an explicit decision to roll it or not; never leave it undecided.
- **Verify by outcome** at the next tick (:12/:22/:42): `ops_archive_pull_exit_code` and `ops_panel_exit_code` 0, `reconcile.prom` mtime advanced, the reconcile counters **unchanged**, `hc_checks_down_total` 0.
- **Rollback is a re-converge to the recorded digest** — clean, but expect `healable_gap_seconds_total` to fall (old code reads `healed_seconds` where new reads `claimed_seconds`), and a counter decrease suppresses the degrading-primary rule via its own `resets()` guard for a full 24 h.

### Panel generation changes

A `SCHEMA_VERSION` bump makes `_check_generation` refuse until the tree is regenerated, and regeneration is a **delete-and-rebuild**, not a step in a converge:

- **Measured, not estimated: ~2.1 s per MB of input, single-threaded.** Size the window from the actual tree before committing to it; at the 2026-07 universe that was 4,730 hours / 8.8 GB ≈ 5 h 15 m.
- **Three signals fire throughout** — the panel exit-code rule, the ops ERROR-log rule, and the healthchecks.io panel dead-man, which pings only on `rc=0` and is the timer's ONLY liveness signal. Pause it time-boxed and un-pause explicitly.
- **Finish clear of the 02:25 UTC auto-reboot.** `Type=oneshot` has no start timeout, so systemd will not kill a long run — the reboot will.
- **Delete both copies.** The NAS pull is `rsync -a` with no `--delete`, so an ops-side delete never propagates and orphaned hours survive beside the new ones.
- **Stop the timer first, and run the regeneration inside the unit** (`systemctl start …panel-materialize.service`), so a stray trigger is a no-op rather than a second writer into the same tree.
- **The regeneration is the point of no return.** The previous image cannot read the new generation and no copy of the old tree survives, so "rollback" is another full rebuild. Take the user's word at that step, not at the converge.

## Ansible secrets

- **Never run `ansible-inventory --host` or `--list`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so both silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- Run playbooks via `infra/ansible/scripts/run.sh` (loads the vaulted deploy key into a throwaway agent). Preview with `--check --diff` before any converge.
