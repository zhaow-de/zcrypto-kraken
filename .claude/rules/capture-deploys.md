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

## Reboots

- **The capture VPSes never reboot themselves** — patches still auto-install; *Capture · reboot pending (attended)* — a Grafana rule paging Slack, not the dead-man domain — fires until you reboot. The ops node still auto-reboots at 02:25. The on-host 21:25 / 22:25 times no longer fire but are kept on purpose — they are the measured slots that already satisfy the Schedule bullet, and the base role's window-collision assert still reads their host_vars, so never delete them as dead config.
- **Reboot SECONDARY first, then primary** — the same canary order as an image rollout: if the kernel bricks the secondary, the primary is never touched.
- Schedule: ≥ 1 h from any 4h bar boundary, off the hour boundary, primary in the measured book-traffic trough, ≥ 1 h host separation, and on the primary right after a completed engine cycle. Measure from the archive, don't guess.
- Expect a ~83 s capture gap; both containers self-restart.

## Ansible secrets

- **Never run `ansible-inventory --host` or `--list`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so both silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- Run playbooks via `infra/ansible/scripts/run.sh` (loads the vaulted deploy key into a throwaway agent). Preview with `--check --diff` before any converge.
