# Capture-host deploys

L2 capture is unbackfillable — mistakes on `zcrypto` (primary) / `zcrypto-red` (secondary) are permanent data loss.

## Canary rule

- **Never re-pin the primary to a capture-image digest that has not run on the secondary for ≥ 24 h.** Before the primary re-pin, verify on the secondary: running digest == candidate, `StartedAt` ≥ 24 h with `RestartCount` 0, capture green (all pairs flowing, no `quarantined`/`ambiguous`/`merge failed` lines, dead-man pinging).
- Skipping the bake requires the user's explicit approval — never silently. (Design: spec `00050`.)
- At the secondary re-pin, schedule the T+24 h reminder via the Slack MCP (`slack_schedule_message`, survives the session) carrying the verification checklist above — the reminder opens the gate, the human still verifies before the primary re-pin.

## Deploys

- `site.yml` and `bootstrap.yml` target **both** capture hosts. The primary refuses unless you pass `-e converge_primary=true` — that flag restarts live capture and/or the engine, so mean it. It gates `--tags engine` too (a failed assert drops the host from later plays, so the engine play would silently skip). Secondary only: `--limit zcrypto-red`. Converges need `-e capture_image_digest=sha256:<...>` (no default).
- Pre-stage everything (pull digest on the host, verify the change is in the pulled image, stage the compose pin); the stop→start window contains only stop → migration-if-any → start.
- **Adding a capture pair: PRIMARY first, secondary second** — the reverse of the image-rollout order (two `--limit` runs; the capture play has no `serial:`). Secondary-first makes the reconciler "heal" the new pair's hours from the secondary into the append-only ledger and flood the gap alert — and the trades half carries no alert rule at all, so that damage lands silently; primary-first short-circuits it (`cli/archive/command.py:473,541`) at any spacing. A pair-list change is **config, not a digest re-pin** — pass the currently-running digest; no bake owed. **Pass `--skip-tags engine` on the primary**: a bare `--limit zcrypto` pulls in the engine play (its only host) and the digest assert fails the host closed — "fixing" that with `-e engine_image_digest=…` restarts the LIVE trade engine. (Derivation: T0092 pre-flight audit; 00069 cold-review I3.)
- Verify by outcome after the next hour boundary: every book stream's `<HH>.parquet` begins at `:00:00.0x`, manifests verify, `infra/scripts/continuity.py` (on a pulled copy, never the live dir) shows no new truncated hours. **Exception — a NEW stream's genesis hour**: it starts mid-hour by construction, so it reads as one truncated hour with up to ~3600 s of booked gap, and its first `<HH>.parquet` does not begin at `:00:00.0x`. Expected once per new stream, not a failure. (`continuity.py:106-108` has no genesis carve-out — [[T0097]].)
- `dropping late event` lines right after a restart are healthy (resubscribe replay), not a failure signal.

## Engine converges

The engine runs on the capture primary — everything above applies (the canary bake is the digest running as *capture* on the secondary; there is no engine secondary), plus:

- **Converge only inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC): a boundary with no journal artifact, or `completed_at` outside `[B, B+30 min]`, zeroes the gate streak; a restart re-runs a missed boundary only within `[B, B+25 min]`, never later.
- **Converge only from a tree whose rendered engine config matches the fleet** — verify with `--check --diff`; an exit code cannot catch converging to the wrong state.
- Digests come from `docs/reference/fleet-pins.md`; capture and engine share one image repo but pin **independently** — never read one service's pin as the other's.
- Pre-flight: target port free (`ss -ltnp`), `/opt/zcrypto-capture/logship-secrets.env` present (compose marks it `required: false`, so absence crash-loops the engine instead of failing the render), digest pre-pulled so the stop→start window holds no download.
- Verify by outcome: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`. The restart marker is the container's `.State.StartedAt` — never the converge command's return time.

## Maintenance windows

- **The capture VPSes do NOT reboot themselves** (`Automatic-Reboot "false"`, T0027 / spec `00071`) — patches still auto-install; the reboot is yours. The ops node still auto-reboots at 02:25.
- A pending reboot pages: *Capture · reboot pending (attended)* fires until you do it, from `node_reboot_required` published by the `zcrypto-reboot-check` timer.
- **Reboot order is SECONDARY first, then primary** — the reverse of the image-rollout order and of spec `00050`'s slots. 00050's primary-first was *unattended paging logic* (a failed primary reboot pages while the secondary still captures); attended, with both hosts taking the same kernel, canary logic wins: if the kernel bricks the secondary, the primary is never touched.
- Scheduling is now guidance, not cron: the 21:25 / 22:25 slots remain rendered on-host as a reminder but no longer fire. Pick a time ≥ 1 h from any 4h bar boundary, off the hour boundary, primary in the measured book-traffic trough, ≥ 1 h host separation — measure from the archive, don't guess. On the primary, right after a completed engine cycle, never approaching a boundary. Expect a ~83 s capture gap (measured 2026-07-11); containers self-restart via `restart: unless-stopped` + their systemd units. (Derivation: specs `00050`, `00071`.)

## SSH

- Root SSH is key-only break-glass; the operator installs the master pubkey manually at bootstrap.
- Day-to-day access: `zcrypto-deploy` user (passwordless sudo; spec 00057 D1) — `ssh zcrypto` / `ssh red` / `ssh nas` / `ssh hp`.

## Ansible secrets

- **Never run `ansible-inventory --host` or `--list`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so both silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- Run playbooks via `infra/ansible/scripts/run.sh` (loads the vaulted deploy key into a throwaway agent). Preview with `--check --diff` before any converge.
