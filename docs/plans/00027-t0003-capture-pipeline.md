# T0003 Capture Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development for the code-build tasks. Real-host execution is orchestrated by the controller with verify-before-tighten safety rails (never delegated blindly). Steps use `- [ ]` tracking.

**Goal:** Build + deploy the T0003 D2 capture pipeline per `docs/specs/00027-t0003-capture-pipeline-design.md`, **prioritizing getting depth-100 capture LIVE** on `zcrypto.zhaow.me` (starts the ≥7-day exit-bar clock). Pull agent + monitoring follow.

**Architecture:** `infra/ansible/` (dev-sec.io hardened Debian 13, Docker) + `cli/capture/` (containerized Kraken WS v2 depth-100 capture) + GHCR image + workstation pull + healthchecks.io. Two-layer secrets (sops→GPG `089D27EE…25A3` → ansible-vault). `sops` at `/home/zhaow/go/bin/sops`.

## Global Constraints

- **Reversibility / safety:** all code lands on branch `feat/t0003-capture-pipeline`. Real-host steps are **idempotent + verify-before-tighten**: never disable the current SSH path before the replacement is proven reachable; Linode Lish is the break-glass. **Once capture is LIVE, do not interrupt it** (L2 gaps are unbackfillable) — redeploys are rare + logged.
- **Secrets:** nothing sensitive in plaintext in git. `deploy` + pull-only SSH keys and the healthchecks API key + hostname live in the ansible-vault; the vault password is sops-encrypted to the GPG key. The `deploy` private key is materialized only into a transient ssh-agent by `run.sh`.
- **Repo conventions:** `ansible`+`ansible-lint` as `uv --dev` deps; `ansible-lint` pre-commit hook scoped `^infra/`; existing `yamllint` covers YAML (ignore `*.sops`/vault/`*.j2`); `cli/capture/` gets ruff+pytest; README ## Usage for `zcrypto capture`. Infra iteration ⇒ **not** logged in `.tmp/decisions.md`.
- **Host facts:** Debian 13 (trixie), 2 vCPU / 3.8 GB / 79 GB, chrony present, static IPv4 172.105.64.43 + IPv6, no vTPM. Current SSH: root+password on 22 (to be locked to `deploy`@10022, key-only).

---

### Stage 1 — Secrets scaffolding + bootstrap (controller-built + executed)

**Files:** `infra/ansible/{ansible.cfg,requirements.yml,.sops.yaml,scripts/vault-pass.sh,scripts/run.sh,inventory/hosts.yml,group_vars/all/{vars.yml,vault.yml},bootstrap.yml}`; `pyproject.toml` (dev deps); `.gitignore`.

- [ ] **S1.1** Add `ansible`, `ansible-lint` as `uv --dev` deps; verify `uv run ansible --version`.
- [ ] **S1.2** `.sops.yaml` with `pgp: 089D27EE8E61BDC0C3F3C58CA03F69C42E8025A3`. Generate a strong random ansible-vault password; `sops --encrypt` it → `vault-password.sops` (committed). `scripts/vault-pass.sh` = `exec /home/zhaow/go/bin/sops -d "$(dirname "$0")/../vault-password.sops"`. `ansible.cfg`: `vault_password_file = scripts/vault-pass.sh`, `inventory = inventory/hosts.yml`, host-key-checking off for first bootstrap (accept-new).
- [ ] **S1.3** Generate fresh ed25519 keypairs (`deploy`, `sync`/pull-only). Put the two **private** keys + the healthchecks API key (from `.tmp/healthchecks-api-key`) + `ansible_host: zcrypto.zhaow.me` into `group_vars/all/vault.yml` (ansible-vault-encrypted). Public keys + non-secret config (depth=100, pairs, paths, healthchecks project id) in plaintext `vars.yml`. `inventory/hosts.yml` = symbolic `capture_host` (ansible_user=deploy, ansible_port=10022) + `workstation` (localhost). `scripts/run.sh` loads the deploy key into a throwaway ssh-agent for a run then flushes it. Shred `.tmp/healthchecks-api-key`.
- [ ] **S1.4** `bootstrap.yml` (targets root@22, key supplied at runtime): create `deploy` sudo user + install its pubkey + python3/sudo; set sshd Port 10022 (keep 22), `PermitRootLogin no`, `PasswordAuthentication no`, reload; **verify deploy@10022 reachable**; then remove Port 22, reload.
- [ ] **S1.5 (EXECUTE, controller):** run `bootstrap.yml` against the real host with root@22 (root SSH already works from this workstation). Verify `deploy@10022` works + root/password disabled. **Idempotent re-run = changed≈0.**
- [ ] **S1.6** Commit: `feat(infra): secrets scaffolding + host bootstrap (deploy@10022)`. Review (secrets hygiene + no-lockout ordering) before proceeding.

### Stage 2 — Hardening + Docker (subagent-built, controller-executed)

**Files:** `infra/ansible/{site.yml,roles/{base,hardening,firewall,fail2ban,chrony,docker}/*}`.

- [ ] **S2.1** Build roles: `base` (unattended-upgrades + 04:00 auto-reboot, UTC, `kraken-capture` nologin user, container-log logrotate daily/compress/rotate90/copytruncate); `hardening` (devsec.hardening `os_hardening`+`ssh_hardening` pinned in requirements.yml, configured port 10022/no-root/no-password + sysctl); `firewall` (nftables default-deny, allow 10022/tcp + ICMP echo v4/v6 + ICMPv6 ND/RA + established); `fail2ban` (sshd jail); `chrony` (NTS on the installed chrony); `docker` (Engine + compose plugin from the Debian docker repo). `site.yml` orchestrates them. `ansible-galaxy install -r requirements.yml`.
- [ ] **S2.2 (EXECUTE):** `run.sh site.yml --check --diff` then apply; verify SSH still works (10022), `docker --version`, nftables rules, chrony NTS, **idempotency double-run (changed=0)**.
- [ ] **S2.3** Commit + review (hardening correctness, no-lockout): `feat(infra): dev-sec.io hardening + firewall + docker`.

### Stage 3 — Capture daemon + image + deploy → GO LIVE (subagent-built TDD, controller-deployed)

**Files:** `cli/capture/{__init__,command,ws_client,book,segment_writer,gap_monitor}.py`; `tests/test_capture_*.py`; `infra/docker/{Dockerfile,compose.yaml}`; `.github/workflows/capture-image.yml`; `infra/ansible/roles/capture/*`; `cli/__main__.py` (register `capture`); `README.md` (## Usage).

- [ ] **S3.1 (TDD, subagent):** `cli/capture/` — thin Kraken WS v2 client (`wss://ws.kraken.com/v2`, public): subscribe `book` depth 100 + `trade` for the universe pairs (from `cli.universe`/config); `book.py` maintains per-pair L2 state + **validates Kraken's CRC32 book checksum** (desync → resubscribe + gap log); `segment_writer.py` streams hourly zstd-Parquet segments (`/var/lib/zcrypto-capture/segments/<pair>/…/<HH>.parquet`) + `.sha256` manifest; `gap_monitor.py` tracks gap time + pings healthchecks. `zcrypto capture` command. **TDD on synthetic WS frames** (checksum validation, segment rotation + manifest hash, gap accounting) + a short live smoke. Never-NaN/degenerate.
- [ ] **S3.2** `infra/docker/Dockerfile` (python:3.14-slim + uv + entrypoint `zcrypto capture`); `compose.yaml` (image by pinned GHCR digest, bind-mount `/var/lib/zcrypto-capture`, `restart: unless-stopped`, CPU/mem limits, json-file log-opts cap). `.github/workflows/capture-image.yml` builds+pushes `ghcr.io/zhaow-de/zcrypto-capture` on push, outputs digest. `capture` role: render compose (digest var) + systemd unit (`docker compose up -d` on boot).
- [ ] **S3.3** Review the daemon (correctness-critical: CRC32, gap logic, segment integrity) + the deploy role.
- [ ] **S3.4 (EXECUTE):** push branch → CI builds the image → deploy via `run.sh site.yml` (capture role, pinned digest). **Measurement smoke:** run ~30–60 min, confirm depth-100 load fits the 2-vCPU box (CPU, RAM, disk-rate, no dropped frames/checksum fails). If it fits → **capture is LIVE (clock starts)**. Record the real daily rate → pin the ring-buffer/watermark + workstation-downtime tolerance.
- [ ] **S3.5** Commit + review: `feat(capture): containerized Kraken WS depth-100 capture daemon (LIVE)`.

### Stage 4 — Workstation pull agent (if time; the ring buffer absorbs lag)

- [ ] **S4.1** `pull.yml` (localhost): authorize the pull-only forced-command key on the VPS; systemd timer (30 min) `rsync` VPS segments → workstation staging → hash-verify vs manifest → delete-on-VPS-after-verified → nightly compaction to `../zcrypto-kraken-data/`. Commit + review.

### Stage 5 — Monitoring + README badge + alerting drill (if time)

- [ ] **S5.1** `monitoring` role: provision healthchecks checks via the API key; wire the daemon heartbeat + disk/gap alerts → email; add the healthchecks badge to the **main** `README.md`; run the alerting drill (stop daemon → confirm alert). Commit + review.

### Stage 6 — Closeout

- [ ] **S6.1** Flip `docs/open-topics/T0003-d2-capture-pipeline.md` → `partial` (pipeline built + capture live; the ≥7-day clean run + verified sync is the wall-clock remainder) with `## Done so far`; sync the index. Append the `iter-038` `docs/iterations-history.md` entry. Open follow-up topics for anything deferred (pull/monitoring if not done, the 7-day drill tracking). Merge the PR via `merge-pr` when green.
