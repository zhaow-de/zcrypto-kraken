# Capture-host deploys

L2 capture is unbackfillable — mistakes on `zcrypto` (primary) / `zcrypto-red` (secondary) are permanent data loss.

## Canary rule

- **Never re-pin the primary to a capture-image digest that has not run on the secondary for ≥ 24 h.** Before the primary re-pin, verify on the secondary: running digest == candidate, `StartedAt` ≥ 24 h with `RestartCount` 0, capture green (all pairs flowing, no `quarantined`/`ambiguous`/`merge failed` lines, dead-man pinging).
- Skipping the bake requires the user's explicit approval — never silently. (Design: spec `00050`.)
- At the secondary re-pin, schedule the T+24 h reminder via the Slack MCP (`slack_schedule_message`, survives the session) carrying the verification checklist above — the reminder opens the gate, the human still verifies before the primary re-pin.

## Deploys

- `site.yml` and `bootstrap.yml` target **both** capture hosts. The primary refuses unless you pass `-e converge_primary=true` — that flag restarts live capture and/or the engine, so mean it. It gates `--tags engine` too (a failed assert drops the host from later plays, so the engine play would silently skip). Secondary only: `--limit zcrypto-red`. Converges need `-e capture_image_digest=sha256:<...>` (no default).
- Pre-stage everything (pull digest on the host, verify the change is in the pulled image, stage the compose pin); the stop→start window contains only stop → migration-if-any → start.
- Verify by outcome after the next hour boundary: every book stream's `<HH>.parquet` begins at `:00:00.0x`, manifests verify, `infra/scripts/continuity.py` (on a pulled copy, never the live dir) shows no new truncated hours.
- `dropping late event` lines right after a restart are healthy (resubscribe replay), not a failure signal.

## Maintenance windows

- Current reboot slots: primary 21:25 UTC, secondary 22:25 UTC. When re-deciding: ≥ 1 h from any 4h bar boundary, off the hour boundary, primary in the measured book-traffic trough, ≥ 1 h host separation — measure from the archive, don't guess. (Derivation: spec `00050`; `infra/ansible/roles/base/defaults/main.yml`.)

## SSH

- Root SSH is key-only break-glass; the operator installs the master pubkey manually at bootstrap.
- Day-to-day access: `deploy` user (passwordless sudo) — `ssh zcrypto` / `ssh red` / `ssh nas` / `ssh hp`.

## Ansible secrets

- **Never run `ansible-inventory --host` or `--list`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so both silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- Run playbooks via `infra/ansible/scripts/run.sh` (loads the vaulted deploy key into a throwaway agent). Preview with `--check --diff` before any converge.
