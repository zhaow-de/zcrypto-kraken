# T0003 — D2 Forward-Capture Pipeline (portable, scripted) — Design

**Iteration:** iter-038 · **Phase:** 1 (Data Foundation — the one outstanding exit-bar item) · **Status:** design approved (interactive)
**Master-plan refs:** §8 (capture infrastructure + hardening spec), §6 (sizing), §10 (operational risk / secrets), §12 (Phase-1 exit bar; Phase-6 deployment-host). Open topic: `docs/open-topics/T0003-d2-capture-pipeline.md`.

## Problem & context

T0003 is the **single outstanding item on the Phase-1 exit bar** and the only human-gated Phase-1 deliverable: a 24/7 forward-capture pipeline that streams Kraken public market data (trades + L2 order book / spread) for the universe pairs, so the Phase-2 cost model's per-pair spread term (which needs ≥2 weeks of captured L2) can eventually be calibrated. Nothing is built today — all completed Phase-1 work is historical OHLCVT ingestion.

**The host is provisioned and resized.** `zcrypto.zhaow.me` — Linode 4GB shared, **2 vCPU / 3.8 GB RAM / 79 GB disk**, **Debian 13 (Trixie)**, static IPv4 `172.105.64.43` + IPv6, chrony already running, Docker absent, currently root+password SSH (to be locked down), no vTPM. Root SSH bootstrap access is available from the workstation.

**Two-stage trust model on one box (master-plan §8/§10/§12).** *This iteration = Stage 1 (CAPTURE):* a deliberately-boring, **keyless** host — public WS/REST only, **no API keys ever**. *Deferred to Phase 6 (TRADE):* the same host later gains a least-privilege, no-withdrawal trade key stored via `systemd-creds`, plus egress lockdown / auditd / Kraken-side key scoping — all **out of scope here**, but the base we build now must be the kind a trade key can later land on safely.

**Exit bar (§12, wall-clock-gated, autonomous once deployed):** the daemon runs **≥7 consecutive days with <0.1 % gap time** AND the VPS→workstation→NAS sync is verified end-to-end (all segment hashes match, zero loss) AND the alerting drill passes.

**User decisions (settled interactively):** whole pipeline in one iteration; **containerized** daemon (Docker Compose) with the image delivered via **GHCR**; **deep L2, depth-100** capture ("capture-everything"); **healthchecks.io dead-man's-switch + email** alerting; IaC lives **in this repo** under `infra/`; SSH on **port 10022**, root + password login disabled, a non-root **`deploy`** sudo user for Ansible; **SSH keypairs stored in-repo, ansible-vault-encrypted, with the vault password sops-encrypted to the GPG identity `zhaow.km@gmail.com`** (fingerprint `089D27EE8E61BDC0C3F3C58CA03F69C42E8025A3`); glass-breaking runbook in `infra/README.md`; a healthchecks status badge added to the main `README.md`.

## Goals

Deliver the full T0003 pipeline as **portable, repeatable, idempotent** infrastructure-as-code:

1. **Ansible-managed hardening + config** of the Debian 13 host (dev-sec.io CIS-L1 baseline, SSH on 10022 key-only/no-root, firewall, fail2ban, chrony+NTS, Docker), portable to a re-provisioned host with an inventory/IP change only.
2. **A containerized capture daemon** (`cli/capture/`) streaming Kraken WS v2 trades + L2 book @ depth 100 for the universe pairs → hourly zstd-Parquet segments + SHA-256 manifests → ≥7-day ring buffer.
3. **A workstation pull agent** that rsyncs segments over SSH (pull-only key), verifies hashes, deletes-on-VPS-after-verified, compacts nightly to the NAS.
4. **Monitoring**: healthchecks.io liveness (dead-man's-switch) + disk-watermark + gap-rate alerts, and the exit-bar alerting drill.
5. **A two-layer secrets mechanism** (sops+GPG → ansible-vault) that keeps all key material and the healthchecks API key encrypted in-repo, decryptable only with the user's GPG private key.

## Non-goals

No trade key / execution engine / Kraken account credentials of any kind (Phase 6). No Phase-6 hardening deltas (egress lockdown, auditd, `systemd-creds`, key scoping). No L3 order-by-order book. No Terraform (single host; provisioning stays a one-time human step). No Nautilus dependency for capture (a thin custom WS client; the Nautilus public path is the documented fallback only).

## Architecture

### Repo layout

```
infra/
  README.md                     # overview + the glass-breaking runbook
  ansible/
    ansible.cfg                 # vault_password_file=scripts/vault-pass.sh; inventory; roles_path
    requirements.yml            # devsec.hardening, community.docker, community.general (pinned)
    .sops.yaml                  # creation rule: pgp = 089D27EE...25A3
    vault-password.sops         # the ansible-vault password, sops-encrypted (GPG)
    scripts/
      vault-pass.sh             # sops -d vault-password.sops  (executable; stdout = vault pw)
      run.sh                    # loads the deploy key into a transient ssh-agent, runs a playbook, cleans up
    inventory/hosts.yml         # committed; symbolic capture_host (ansible_host from vault), deploy@10022; workstation=localhost
    group_vars/
      all/vars.yml              # non-secret: depth=100, pair source, paths, healthchecks project id, log/retention
      all/vault.yml             # ansible-vault: deploy + pull-only SSH keys, healthchecks API key, ansible_host (hostname)
    bootstrap.yml               # one-time: root@22 -> deploy sudo user -> SSH 10022/no-root/no-password
    site.yml                    # steady-state converge (capture_host)
    pull.yml                    # workstation pull agent (localhost)
    roles/ base hardening firewall fail2ban chrony docker capture monitoring pull_agent
  docker/
    Dockerfile                  # python:3.14-slim + uv + the cli package
    compose.yaml                # capture service: pinned GHCR digest, bind-mount, limits, restart
cli/capture/
  command.py ws_client.py book.py segment_writer.py gap_monitor.py __init__.py
.github/workflows/capture-image.yml   # build + push image to ghcr.io/zhaow-de/zcrypto-capture
```

`ansible` + `ansible-lint` + `sops` (via a pinned binary or pipx; `sops` is not a Python dep) enter as `uv --dev` where they are Python; a new `ansible-lint` pre-commit hook is scoped to `^infra/`. The existing repo-wide `yamllint` covers the new YAML (with an ignore added for `*.sops`/vault-encrypted/`*.j2`). `cli/capture/` inherits ruff+pytest. `README.md ## Usage` gains the `zcrypto capture` command.

### Secrets mechanism (two layers, self-contained in a public repo)

- **Layer 1 — sops + GPG.** `.sops.yaml` pins the PGP recipient to fingerprint `089D27EE…25A3`. `vault-password.sops` is the ansible-vault password, sops-encrypted; `scripts/vault-pass.sh` runs `sops -d` and prints it. `ansible.cfg` sets `vault_password_file = scripts/vault-pass.sh`, so ansible transparently gets the vault password via the user's GPG agent.
- **Layer 2 — ansible-vault.** `group_vars/all/vault.yml` (vault-encrypted) holds: the `deploy` private key, the pull-only private key, the healthchecks.io **r/w API key** (relocated from `.tmp/healthchecks-api-key`, which is then shredded), and the host's **`ansible_host`** (the hostname `zcrypto.zhaow.me`). `inventory/hosts.yml` names the host **symbolically** (`capture_host`) and carries only non-sensitive connection vars (`ansible_user=deploy`, `ansible_port=10022`); the real address resolves from the vault at runtime. Non-secret config + public keys live in plaintext `vars.yml`.
- **Transient key use.** The `deploy` private key never touches disk in plaintext: `scripts/run.sh` decrypts it from the vault into a **throwaway ssh-agent** for the run, then flushes the agent — `./run.sh <playbook>` is the entrypoint.
- **Result:** the whole repo is cryptographically useless without the user's GPG private key, and **nothing sensitive is committed in plaintext** — the hostname now lives in the vault too (done via the existing ansible-vault mechanism, so no separate sops-for-inventory plumbing).

### Component design

**A. Bootstrap** (`bootstrap.yml`, run once, `root@zcrypto.zhaow.me:22` via the existing root access — supplied at runtime, never stored):
1. Create the `deploy` system user with sudo (a vaulted sudo password, or NOPASSWD scoped to the automation), install its public key, install `python3` (present) + `sudo`.
2. Reconfigure sshd: **add Port 10022** (keep 22 for now), `PermitRootLogin no`, `PasswordAuthentication no`, `PubkeyAuthentication yes`; reload.
3. **Verify `deploy@10022` connects**, then **remove Port 22**, reload. End state: `deploy@10022` only; root + password login disabled. Break-glass remains the Linode Lish console.

**Safety rail (no self-lockout):** every SSH-tightening step runs after the replacement path is verified reachable; the Linode edge firewall already whitelists 22 + 10022 so the host firewall change cannot orphan SSH; Lish is the out-of-band fallback.

**B. Hardening + host config** (`site.yml`, `deploy@10022`, become; all idempotent — `changed=0` on a second run):
- `hardening`: dev-sec.io `devsec.hardening.os_hardening` + `ssh_hardening` (pinned), configured for **port 10022, no-root, key-only, no-password**, modern crypto, plus sysctl (kptr/dmesg restrict, ptrace_scope, rp_filter, syncookies, disable IP forwarding/redirects, `randomize_va_space=2`).
- `firewall`: **two layers, both enforced** — the host **nftables** firewall (Ansible-managed) *and* the **Linode edge firewall** (managed manually in Cloud Manager, whitelisting **22 + 10022** and ICMP). nftables is default-deny inbound, allowing **10022/tcp** (source-restricted where practical), **ICMP echo-request (ping) + ICMPv6 echo-request (ping6)** — matching the already-configured Linode edge firewall — plus the ICMPv6 neighbor-discovery / router-advertisement types IPv6 requires to function, and established/related; outbound open (egress lockdown is a Phase-6 delta). **Opening/closing any future port requires changing *both* layers** — documented in `infra/README.md`.
- `fail2ban`: sshd jail (log-noise suppression; SSH is key-only so this is not load-bearing).
- `chrony`: reconfigure the already-installed chrony for **NTS** (e.g. `time.cloudflare.com … nts`) — accurate, authenticated capture timestamps (data-integrity, not just hygiene).
- `base`: `unattended-upgrades` (security pocket; **auto-reboot 04:00** with clean capture resume — see error handling), timezone UTC, minimal packages; a `nologin` service user `kraken-capture` owning `/var/lib/zcrypto-capture`; and a **logrotate** policy for the **container console log** (`/var/lib/docker/containers/*/*-json.log`) — **daily, compressed, 90-day retention** (`daily`, `rotate 90`, `compress`, `delaycompress`, `copytruncate`, `missingok`, `notifempty`).
- `docker`: install Docker Engine + Compose plugin (via the official Debian repo).

**C. The capture daemon** (`cli/capture/`, Python, runs in the container as `zcrypto capture`):
- `ws_client.py`: a thin Kraken **WS v2** client (`wss://ws.kraken.com/v2`, public, keyless). Subscribes `book` @ **depth 100** and `trade` for the **universe pairs** (the ~10 EUR majors from the point-in-time universe / `cli.universe`; sourced from config so it tracks the universe). Auto-reconnect with exponential backoff.
- `book.py`: maintains per-pair L2 book state from snapshot + updates; **validates Kraken's per-message CRC32 book checksum** every update — a mismatch means desync → drop + resubscribe that pair + log a gap. This is the primary L2 gap-detection mechanism.
- `segment_writer.py`: buffers events and **streams hourly zstd-Parquet segments** (book-updates + trades, separate schemas) to `/var/lib/zcrypto-capture/segments/<pair>/<YYYY>/<MM>/<DD>/<HH>.parquet`, each with a sidecar `.sha256` **manifest**. Streaming/row-group writes (not buffer-then-flush) to bound RAM. zstd level tuned so compression stays within the 2-vCPU budget.
- `gap_monitor.py`: tracks per-pair gap time (reconnect windows, checksum resyncs, missing heartbeats); **trade** gaps are REST-backfilled (`api.kraken.com` Trades endpoint) and logged, **L2** gaps are measured + reported (uncbackfillable, per §8); emits a **healthchecks.io heartbeat** each healthy interval and a metrics/gap line to the log. On sustained gap or disk pressure, alerts.
- Ring buffer: the daemon (with the pull agent's delete-after-verified) keeps ≥7 days of segments; a **disk-watermark guard** stops accepting new segments / alerts before `/` fills (protecting the host, since data shares the root fs — a separate Linode Block Storage volume is a documented future option, not this iteration).
- **Logging:** the daemon logs to **stdout** (the default). Docker captures the **container console** at the host via the `json-file` driver, and host **logrotate** rotates that container log daily/compressed/90-day (above); a Docker `log-opts` `max-size`/`max-file` cap bounds it between rotations. No separate app log file.

**D. Image + deploy** (Docker/GHCR):
- `infra/docker/Dockerfile`: `python:3.14-slim`, `uv sync` the locked env, entrypoint `zcrypto capture`.
- `.github/workflows/capture-image.yml`: on push to `develop`/tags, build + push `ghcr.io/zhaow-de/zcrypto-capture` (public image, since the repo is public — no pull auth needed), output the image **digest**.
- `capture` role: render `compose.yaml` pinned to the **image digest** (a var), bind-mount `/var/lib/zcrypto-capture`, set `restart: unless-stopped` + CPU/memory limits, and supervise via a **systemd unit** (`docker compose up -d` on boot). Redeploys (rare) cause a brief, logged capture gap.

**E. Workstation pull agent** (`pull.yml`, targets `localhost` = the workstation):
- A **pull-only SSH key** with a forced-command (`rrsync`-style, read-only, scoped to the segments dir) authorized on the VPS for the `deploy`/a dedicated `sync` user.
- A **systemd timer** (every 30 min) runs `rsync` over SSH from the VPS segments dir → workstation staging; **verifies each segment against its `.sha256` manifest**; on match, marks it eligible and the VPS-side prune deletes-after-verified; **nightly compaction** moves verified segments to the NAS mount `../zcrypto-kraken-data/` (visible from the workstation). The ≥7-day VPS ring buffer means the workstation can be off for days without loss.

**F. Monitoring + alerting drill**:
- healthchecks.io project `32eaee6f-cb82-4773-9471-4b802136adc1`. The `monitoring` role uses the r/w **API key** (from the vault) to **provision checks** (liveness dead-man's-switch, and optionally disk/gap checks) and retrieve their ping URLs (stored back into the vault / dropped as the container's env). The daemon pings the liveness check only while capture is fresh; a missed ping → healthchecks emails. Disk-watermark + gap-rate breaches ping their own checks / alert. The **alerting drill** = deliberately stop the daemon and confirm the alert fires (exit-bar requirement).
- **Main `README.md` badge** (added with the monitoring commit): `![healthchecks.io](https://img.shields.io/endpoint?url=https%3A%2F%2Fhealthchecks.io%2Fbadge%2F32eaee6f-cb82-4773-9471-4b802136adc1%2FopNhEK_4-2.shields)`.

## Data flow

Kraken WS v2 (public) → per-pair book state (+CRC32 validation) & trades → hourly zstd-Parquet segment + `.sha256` manifest → `/var/lib/zcrypto-capture` ring buffer (≥7 d) → healthchecks heartbeat each healthy interval → workstation rsync pull (30 min, pull-only key) → hash-verify vs manifest → delete-on-VPS-after-verified → nightly compaction → NAS `../zcrypto-kraken-data/`.

## Error handling & safety

- **SSH self-lockout:** the ordered bootstrap (verify new path before disabling the old) + Linode edge firewall (22/10022 both open) + Lish out-of-band console.
- **WS resilience:** exponential-backoff reconnect; CRC32 checksum desync → resubscribe + gap log; trade gaps REST-backfilled, L2 gaps measured/reported.
- **Disk-full:** watermark guard + delete-after-verified ring; capture degrades gracefully (stop-and-alert) rather than filling `/`.
- **Auto-reboot continuity:** unattended-upgrades reboots at 04:00 only with the systemd-supervised container set to resume capture cleanly on boot (the reboot window is a logged sub-0.1 % gap).
- **Idempotency = the done-bar:** `site.yml` reports `changed=0` on a second run.

## Downtime & gap tolerance

Two independent failure domains with very different tolerances (the user asked this be investigated + documented):

**Workstation / pull-side downtime — *no* data gap.** The VPS keeps the ring buffer, so the research workstation can be offline without loss for as long as the VPS accumulates un-pulled segments before its disk forces rotation: `free_disk / daily_compressed_rate`. With ~74 GB free and the depth-100 rate TBD, that is roughly **5–14 days** (≈14 d at 5 GB/day, ≈7 d at 10 GB/day, ≈5 d at 15 GB/day) — pinned after the measurement smoke; the disk-watermark guard alarms before the buffer is exhausted.

**VPS / capture-side downtime — *a* data gap.** *L2 order book is uncbackfillable* (§8): any capture downtime is a permanent L2 gap for that window, so the "max downtime without an L2 gap" is **zero**. The operative ceiling is the exit bar — **<0.1 % over 7 days ≈ 10 minutes/week cumulative** — and for ongoing data quality we stay well under it. *Trades* are REST-backfillable within Kraken's `/Trades` window (paginated by timestamp; short outages self-heal, multi-hour outages may exceed the practical backfill). A single unplanned reboot (Linode maintenance / kernel) is typically **1–5 min** → within budget if rare; the 04:00 unattended-upgrades reboot resumes capture cleanly as a logged sub-minute gap, and the systemd-supervised container auto-restarts on crash. **Phase-6 live-trading impact (deferred):** on the same host, capture downtime coincides with trading downtime — the reduce-only-on-restart + Linode-incident flatten/freeze runbook (§10) bound the *risk*; the cost is missed opportunity + a data gap, not a safety event.

**Pinned after the measurement smoke:** the real daily compressed rate → the exact workstation-downtime tolerance + the disk-watermark thresholds; and a re-confirmation of Kraken's `/Trades` backfill window for the trade side.

## Testing / definition of done

- **Ansible:** `--syntax-check` + `ansible-lint` (pre-commit) → `--check`/`--diff` dry-run → idempotency double-run (`changed=0`).
- **Daemon (pytest, `cli/capture/`):** the segment writer (schema + hourly rotation), manifest SHA-256, CRC32 book-checksum validation, and gap-accounting logic on **synthetic WS frames**; a short **live smoke** against Kraken's public feed (subscribe, validate one checksum, write one segment).
- **End-to-end = the T0003 exit bar** (wall-clock, autonomous once deployed): ≥7 consecutive days <0.1 % gap + verified VPS→workstation→NAS sync (all hashes match, zero loss) + the alerting drill. A short **measurement smoke** (1–2 h at depth-100 on all pairs) runs first to confirm the 2-vCPU/4 GB box holds the real load before the 7-day clock starts.

## `infra/README.md` — glass-breaking runbook (content outline)

Linode **Lish** out-of-band console (bypasses SSH/network) as primary recovery; the exact "locked out → Lish → edit `/etc/ssh/sshd_config` → `systemctl restart ssh`" steps; the **two-firewall model** — host **nftables** *and* the **Linode edge firewall**, where **both** must be changed to open or close a port — with the current port map (SSH on **10022**; edge whitelist = **22 + 10022**), and **22 retained at the edge as a break-glass path** (re-enable sshd on 22 via Lish if 10022 is ever unreachable); the **vault recovery path** (`sops -d` with the GPG key → unlock vault → recover the `deploy` key); **rebuild-from-IaC** (re-provision → `bootstrap.yml` → `run.sh site.yml` → identical host); and key-rotation notes.

## Build sequence (the plan will stage this)

1. **Secrets + bootstrap scaffolding** (sops/`.sops.yaml`, vault, `run.sh`, `bootstrap.yml`) → bootstrap the real host (`deploy@10022`, root/password off). 2. **Hardening + Docker** (`site.yml` roles base/hardening/firewall/fail2ban/chrony/docker) → idempotent. 3. **The daemon + image + GHCR CI + compose deploy** → **measurement smoke** → **go live, start the ≥7-day clock**. 4. **Pull agent** (workstation). 5. **Monitoring + README badge + alerting drill**. Staged so the wall-clock capture starts before the pull/monitoring pieces are finished (the ring buffer absorbs the lag).

**Execution mode:** on the user's go-ahead the plan runs **autonomously** (the interaction was front-loaded for this) — every step is idempotent, verify-before-tighten, and Lish-recoverable, so the real-host bootstrap needs no mid-flight checkpoint; progress is reported per stage, and only a genuinely irreversible surprise pauses for the user.

## Deferred / parked

Phase-6 TRADE deltas (trade key via `systemd-creds` [host-key-backed, no vTPM], egress lockdown, auditd, Kraken key scoping, CrowdSec); a Linode **Block Storage** volume to move captured data off the root fs; depth 500/1000 (config change if load allows).

## Closeout (planned)

On completion: flip `docs/open-topics/T0003-d2-capture-pipeline.md` to `partial` (capture pipeline built; the ≥7-day clean run + verified sync is the wall-clock remainder) or `resolved` once the exit-bar drill passes, and sync the index; append the `iter-038` `docs/iterations-history.md` entry. Engineering/tooling iteration — **not** logged in `.tmp/decisions.md` (per `decisions-log.md`, infra choices are decided-and-proceeded, not research subject-matter).
