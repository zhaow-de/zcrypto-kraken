# infra — T0003 capture-pipeline infrastructure-as-code

Portable, scripted provisioning + deployment for the D2 forward-capture pipeline (spec:
`docs/specs/00027-t0003-capture-pipeline-design.md`). Everything here is idempotent and
provider-agnostic: to move the pipeline to a new host you re-provision, point the inventory at the
new address, and re-run — no edits to the config layer.

<!-- mdformat-toc start --slug=github --maxlevel=4 --minlevel=2 -->

- [Layout](#layout)
- [Running it](#running-it)
- [The two-firewall model — IMPORTANT](#the-two-firewall-model-%E2%80%94-important)
- [Break-glass — you are locked out of SSH](#break-glass-%E2%80%94-you-are-locked-out-of-ssh)
- [Rebuild from scratch (portability)](#rebuild-from-scratch-portability)
- [Key rotation](#key-rotation)
- [Deploy image note](#deploy-image-note)

<!-- mdformat-toc end -->

## Layout<a name="layout"></a>

- `ansible/` — the source of truth. `bootstrap.yml` (one-time: root → `deploy@10022`), `site.yml`
  (steady-state converge: hardening → firewall → fail2ban → chrony → docker → capture), and the
  `roles/`. Secrets are two-layer: **sops+GPG** encrypts the ansible-vault password
  (`vault-password.sops.yaml`, GPG recipient `zhaow.km@gmail.com`), and **ansible-vault** encrypts
  the SSH keys + host secrets (`files/*_ed25519`, `group_vars/capture_host/vault.yml`).
- `docker/` — the capture daemon's `Dockerfile` + reference `compose.yaml`. The image is
  `ghcr.io/zhaow-de/zcrypto-capture` (CI: `.github/workflows/capture-image.yml`).

## Running it<a name="running-it"></a>

`site.yml` targets the whole `capture_host` group — the live primary `zcrypto` **and** the secondary `zcrypto-red`. The primary refuses to converge unless you pass `-e converge_primary=true`, because a converge restarts its live, unbackfillable L2 capture (and the engine). Say what you mean:

```bash
cd infra/ansible

# secondary only — the everyday case
./scripts/run.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<...>

# the live primary — restarts capture and/or the engine
./scripts/run.sh site.yml --limit zcrypto -e converge_primary=true -e capture_image_digest=sha256:<...>

# engine deploy — the guard gates this too (a failed assert drops the host from later plays,
# so WITHOUT the flag the engine play silently skips instead of deploying)
./scripts/run.sh site.yml --tags engine -e converge_primary=true -e engine_image_digest=sha256:<...>

# dry-run anything by appending --check --diff
```

`run.sh` loads the vault-encrypted deploy key into a transient ssh-agent, then runs the playbook (needs the GPG key unlocked). **It cannot bootstrap a virgin host** — a fresh box only answers to the operator's master key, which `run.sh` deliberately excludes; run `bootstrap.yml` directly (below).

```bash
# first-time only, on a NEW host, with your master key in the agent (NOT via run.sh):
uv run ansible-playbook bootstrap.yml --limit <new-host> -e ansible_user=root -e ansible_port=22
```

`run.sh` uses `scripts/vault-pass.sh` (`sops -d` → the ansible-vault password) — so a run needs the
GPG private key for `zhaow.km@gmail.com` available/unlocked in your gpg-agent.

## The two-firewall model — IMPORTANT<a name="the-two-firewall-model-%E2%80%94-important"></a>

Inbound is filtered by **two independent layers, and a port must be opened in *both*:**

1. **Host nftables** (`roles/firewall`) — default-drop inbound, allows only **10022/tcp** + ICMP
   (ping v4/v6) + established/related. It manages *only* `table inet filter` (no `flush ruleset`),
   so Docker's own NAT/forward tables survive — do not add a `flush ruleset` back or container
   networking breaks.
2. **Linode Cloud Firewall** (managed by hand in the Linode Cloud Manager) — currently whitelists
   **22 + 10022**. No inbound 443 (the daemon is outbound-only; nothing is served publicly).

To open a new inbound port you must edit `roles/firewall/templates/nftables.conf.j2` **and** add the
rule in the Linode Cloud Manager. Editing only one silently fails.

## Break-glass — you are locked out of SSH<a name="break-glass-%E2%80%94-you-are-locked-out-of-ssh"></a>

SSH is **key-only on port 10022**, root + password login are disabled, and port 22 no longer
listens. If you lose `deploy@10022` access:

1. **Linode Lish console** (out-of-band, bypasses SSH and the network entirely): Linode Cloud
   Manager → your Linode → **Launch LISH Console** (or `ssh <user>@lish-<region>.linode.com`). Log
   in as `root` with the Linode root password (set/reset under the Linode's **Settings → Reset Root
   Password**, requires a reboot).
2. From the Lish root shell, fix whatever broke:
   - **SSH:** `nano /etc/ssh/sshd_config` (+ `/etc/ssh/sshd_config.d/`), then `sshd -t` (validate)
     and `systemctl restart ssh`. To re-enable port 22 temporarily as a fallback, add `Port 22`,
     restart ssh, and add 22 to both firewalls.
   - **Firewall lockout:** `nft flush ruleset` (opens everything — temporary!) or
     `nft -f /etc/nftables.conf` to reload the managed rules; check `nft list ruleset`.
   - **Recover the deploy key** to reach the box from the workstation:
     `cd infra/ansible && sops -d --extract '["vault_password"]' vault-password.sops.yaml` gives the
     vault password (needs the GPG key); `ansible-vault view files/deploy_<host>_ed25519` prints
     that host's private key — the deploy keys are per-machine (`deploy_zcrypto_ed25519`,
     `deploy_zcrypto-red_ed25519`, `deploy_zcrypto-ops_ed25519`; see `files/README.md`).
3. Once back in, re-assert the intended (hardened) state. For the primary that means `./scripts/run.sh site.yml --limit zcrypto -e converge_primary=true -e capture_image_digest=sha256:<...>` — the flag is required, and it restarts live capture, so pick the moment.

## Rebuild from scratch (portability)<a name="rebuild-from-scratch-portability"></a>

1. Provision a fresh host (any provider/distro Ansible + dev-sec.io support; the roles target
   Debian-family here). Ensure the Linode/cloud firewall allows 22 (bootstrap) + 10022.
2. `uv run ansible-playbook bootstrap.yml --limit <host> -e ansible_user=root -e ansible_port=22` — creates `deploy`,
   moves SSH to 10022, disables root/password. Run it directly, not via `run.sh`: a virgin host only
   answers to the operator's master key, which `run.sh`'s throwaway agent excludes.
3. `./scripts/run.sh site.yml --limit <host> -e capture_image_digest=sha256:<...>` — hardens + installs Docker + deploys the capture container.
4. Drop 22 from the cloud firewall once `deploy@10022` is confirmed.

## Key rotation<a name="key-rotation"></a>

Regenerate a keypair, `ansible-vault encrypt` the new private key into `files/`, update the matching
`*_authorized_key` in `group_vars/capture_host/vars.yml`, re-run `site.yml` (installs the new pubkey; the primary needs `-e converge_primary=true`),
verify the new key works, then remove the old key's `authorized_key` entry and re-run.

## Deploy image note<a name="deploy-image-note"></a>

The GHCR CI builds `ghcr.io/zhaow-de/zcrypto-capture` on push. **GHCR packages default to private** —
after the first push, set the package to **Public** in GitHub (Packages → the package → Package
settings → Change visibility) so the keyless host can `docker compose pull` it. Until then the
`capture` role needs `-e capture_image_digest=sha256:<...>` (from the workflow's job summary), or the
image can be built on the host directly (`docker build -f infra/docker/Dockerfile`).
