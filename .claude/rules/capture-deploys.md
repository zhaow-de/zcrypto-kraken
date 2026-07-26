# Capture-host deploys

L2 capture is unbackfillable — mistakes on `zcrypto` (primary) / `zcrypto-red` (secondary) are permanent data loss.

## Canary rule

- **Never re-pin the primary to a capture-image digest that has not run on the secondary for ≥ 24 h.** Before the primary re-pin, verify on the secondary: running digest == candidate, `StartedAt` ≥ 24 h with `RestartCount` 0, capture green (all pairs flowing, no `quarantined`/`ambiguous`/`merge failed` lines, dead-man pinging).
- Skipping the bake requires the user's explicit approval — never silently. (Design: spec `00050`.)
- At the secondary re-pin, schedule the T+24 h reminder via the Slack MCP (`slack_schedule_message`, survives the session) carrying the verification checklist above — the reminder opens the gate, the human still verifies before the primary re-pin.

## Deploys

- `site.yml` and `bootstrap.yml` target **both** capture hosts. The primary refuses unless you pass `-e converge_primary=true` — that flag restarts live capture and/or the engine, so mean it. It gates `--tags engine` too (a failed assert drops the host from later plays, so the engine play would silently skip). Secondary only: `--limit zcrypto-red`. Converges need `-e capture_image_digest=sha256:<...>` (no default).
- Pre-stage everything (pull digest on the host, verify the change is in the pulled image, stage the compose pin); the stop→start window contains only stop → migration-if-any → start.
- **Adding a capture pair: PRIMARY first, secondary second** — the reverse of the image-rollout order, and it is not a preference. `site.yml`'s capture play targets both hosts with no `serial:`, so ordering means two `--limit` runs. Secondary-first leaves the reconciler seeing a pair the primary "lost": it heals whole hours from the secondary and books them into the append-only ledger (a 24 h skew × 2 pairs = 172,800 s against a 600 s/24 h alert), and the trades half carries no alert rule at all. Primary-first short-circuits it (`cli/archive/command.py:473,541`) at any spacing. A pair-list change is **config, not a digest re-pin** — pass the currently-running digest and no canary bake is owed. **Pass `--skip-tags engine` on the primary**: the engine play is `hosts: engine_host`, whose only member is `zcrypto`, so a bare `--limit zcrypto` pulls it in and its digest assert fails the host closed — and "fixing" that by adding `-e engine_image_digest=…` would restart the LIVE trade engine. (Derivation: T0092's pre-flight audit; the assert trap is 00069's cold-review I3.)
- Verify by outcome after the next hour boundary: every book stream's `<HH>.parquet` begins at `:00:00.0x`, manifests verify, `infra/scripts/continuity.py` (on a pulled copy, never the live dir) shows no new truncated hours. **Exception — a NEW stream's genesis hour**: it starts mid-hour by construction, so it reads as one truncated hour with up to ~3600 s of booked gap, and its first `<HH>.parquet` does not begin at `:00:00.0x`. Expected once per new stream, not a failure. (`continuity.py:106-108` has no genesis carve-out — [[T0097]].)
- `dropping late event` lines right after a restart are healthy (resubscribe replay), not a failure signal.

## Maintenance windows

- Current reboot slots: primary 21:25 UTC, secondary 22:25 UTC. When re-deciding: ≥ 1 h from any 4h bar boundary, off the hour boundary, primary in the measured book-traffic trough, ≥ 1 h host separation — measure from the archive, don't guess. (Derivation: spec `00050`; `infra/ansible/roles/base/defaults/main.yml`.)

## SSH

- Root SSH is key-only break-glass; the operator installs the master pubkey manually at bootstrap.
- Day-to-day access: `zcrypto-deploy` user (passwordless sudo; renamed from `deploy`, spec 00057 D1) — `ssh zcrypto` / `ssh red` / `ssh nas` / `ssh hp`.

## Secrets — commands that print them in cleartext

- **Never run `ansible-inventory --host` or `--list`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so both silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- **Never read a container's environment on the engine host** — `docker inspect … {{json .Config.Env}}` / `{{json .Config}}`, `docker exec … env`, `docker compose config`: `zcrypto-engine` holds the live Kraken trade key and the Loki push password as env vars. Scope every inspect to the field you need: `.Mounts`, `.State`, `.Config.Image`, `.Config.Entrypoint`, `.RestartCount`.
- **Name the fields in a subagent's dispatch prompt** — an unscoped "gather `docker inspect` evidence" invites the whole-object form.
- Run playbooks via `infra/ansible/scripts/run.sh` (loads the vaulted deploy key into a throwaway agent). Preview with `--check --diff` before any converge.
