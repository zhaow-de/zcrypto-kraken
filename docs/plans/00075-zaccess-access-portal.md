# zaccess Internet Access Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver spec `00075` — G1 (internet SSH to ops), G3 (DSM in a browser), G2 (tmux in a browser) through the Linode bridgehead `zaccess.zhaow.me`, as the fleet's fifth Ansible-managed host.

**Architecture:** One playbook (`site.yml` gains an `access_host` play; the ops play gains an `access_ops` role). WireGuard tunnel `zaccess0` (bridgehead 10.99.0.1 ↔ ops 10.99.0.2, `AllowedIPs 10.99.0.2/32`), `systemd-socket-proxyd` relays (no NAT, no IP forwarding), Caddy mTLS edge with pinned client leaves, native apt-pinned Alloy observability from Phase 2.

**Tech Stack:** Ansible (existing roles `base`/`hardening`/`firewall`/`fail2ban`/`chrony` reused; new roles `access`, `access_ops`), WireGuard, Caddy (upstream apt, pinned), Grafana Alloy (upstream apt, pinned), systemd-socket-proxyd, agentboard (pinned, spike-gated).

## Global Constraints

- Spec `docs/specs/00075-zaccess-access-portal-design.md` governs; decisions cited as D1–D19. **D19: no new open topics from this work package** — a discovered follow-up is fixed in-branch, put in this plan, or explicitly dropped in the closeout.
- One branch (`feat/zaccess-access-portal`), one PR at the end, on the owner's word.
- Every host-touching step runs in the main loop, attended; every converge is previewed `--check --diff`; playbooks run via `infra/ansible/scripts/run.sh` from `infra/ansible/`. **Never** `ansible-inventory --host/--list`.
- Bare `site.yml` runs stay forbidden — every run below is `--limit`-scoped. Nothing here ever touches `capture_host`/`engine_host`/`nas_host`.
- Commit gate `uv run pre-commit run -a`; commits split by kind — code+its proving tests together (`feat(config)`), docs separately (`docs(...)`), `.claude/` rule edits separately (`claude(...)`); every commit reviewed by a different agent before push (trailers per `commit-messages.md`; authoring model today: Claude Fable 5).
- Secrets: new vault material via `uv run ansible-vault encrypt/edit --vault-password-file scripts/vault-pass.sh` (run from `infra/ansible/`); no secret is ever echoed, logged, or committed plaintext; public halves are committed plaintext deliberately.
- Operator-facing text: systemd `Description=`, alert summaries, script `--help` carry no `T<NNNN>`/spec/iter tokens (comments above them do); alert summaries carry `infra/runbooks/README.md` anchors.
- Timeout-guard every network command (`timeout 30 …`); verify by outcome after every converge.

______________________________________________________________________

### Task 1: Firewall role extra-ports seam (byte-identical for capture)

**Files:**

- Modify: `infra/ansible/roles/firewall/templates/nftables.conf.j2`
- Modify: `infra/ansible/roles/firewall/defaults/main.yml`
- Test: `tests/test_infra_firewall_template.py`

**Interfaces:**

- Produces: `firewall_extra_tcp_ports` (list of int/str, default `[]`), `firewall_extra_udp_ports` (list, default `[]`) — consumed by Task 4's `group_vars/access_host/vars.yml`.

- [ ] **Step 1: Capture the pre-seam golden render** — BEFORE touching the template:

```bash
uv run python -c "
import jinja2, pathlib
t = pathlib.Path('infra/ansible/roles/firewall/templates/nftables.conf.j2').read_text()
env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
print(repr(env.from_string(t).render(firewall_ssh_port='10022')))"
```

Paste the printed literal into the test below as `GOLDEN_PRE_SEAM`. (`trim_blocks` + `keep_trailing_newline` mirror Ansible's own Jinja defaults — same reasoning as `tests/test_infra_archive_pull_template.py`.)

- [ ] **Step 2: Write the failing render test:**

```python
"""The firewall template gained optional extra-port lists for the zaccess bridgehead (spec 00075
D8). The capture hosts pass neither variable, so their rendered ruleset must be BYTE-IDENTICAL
to the pre-seam output -- an internet-facing L2 host's firewall must never change as a side
effect of another host's feature."""

from pathlib import Path

import jinja2

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/firewall/templates/nftables.conf.j2"

GOLDEN_PRE_SEAM = "<the literal captured in Step 1>"

BASE = {"firewall_ssh_port": "10022", "firewall_extra_tcp_ports": [], "firewall_extra_udp_ports": []}

def _render(ctx):
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
    return env.from_string(TEMPLATE.read_text()).render(ctx)

def test_capture_render_is_byte_identical_to_pre_seam():
    assert _render(BASE) == GOLDEN_PRE_SEAM

def test_extra_ports_render_accept_rules():
    out = _render({**BASE, "firewall_extra_tcp_ports": [80, 443, 20022],
                   "firewall_extra_udp_ports": [51820]})
    assert "tcp dport { 80, 443, 20022 } accept" in out
    assert "udp dport { 51820 } accept" in out
```

(`GOLDEN_PRE_SEAM` is a measured literal pasted at Step 1 execution, per this repo's convention for measured facts.)

- [ ] **Step 3: Run it — expect FAIL** (StrictUndefined: the current template doesn't reference the new vars, so the byte-identity test passes but `test_extra_ports_render_accept_rules` fails on the missing accepts): `uv run pytest tests/test_infra_firewall_template.py -q`
- [ ] **Step 4: Implement.** In `nftables.conf.j2`, directly under the `# SSH` accept, add:

```jinja
{% if firewall_extra_tcp_ports %}

    # additional exposed TCP services (per-group, spec 00075: Caddy 80/443 + the SSH relay)
    tcp dport { {{ firewall_extra_tcp_ports | join(', ') }} } accept
{% endif %}
{% if firewall_extra_udp_ports %}

    # additional exposed UDP services (per-group, spec 00075: WireGuard)
    udp dport { {{ firewall_extra_udp_ports | join(', ') }} } accept
{% endif %}
```

In `defaults/main.yml` add `firewall_extra_tcp_ports: []` and `firewall_extra_udp_ports: []` with a one-line comment each.

- [ ] **Step 5: Run the test — expect PASS** (byte-identity proves the seam is invisible with empty lists), then `uv run pytest -q` (full suite).
- [ ] **Step 6: Commit** `feat(config): firewall role gains optional extra-port lists` (+ tests in the same commit — they are the change's proof).

### Task 2: Hardening role stale-drop-in parameterization

**Files:**

- Modify: `infra/ansible/roles/hardening/tasks/main.yml` (the `remove the bootstrap's temporary sshd drop-in` task)
- Modify: `infra/ansible/roles/hardening/defaults/main.yml`

**Interfaces:**

- Produces: `hardening_stale_sshd_dropins` (list, default `["10-zcrypto.conf"]`) — `group_vars/access_host` overrides to `["10-zaccess-interim.conf"]` (Task 4).

- [ ] **Step 1: Implement** — replace the single-file removal task with a loop:

```yaml
- name: remove stale sshd drop-ins (orphaned once ssh_hardening owns the whole file)
  ansible.builtin.file:
    path: "/etc/ssh/sshd_config.d/{{ item }}"
    state: absent
  loop: "{{ hardening_stale_sshd_dropins }}"
```

Default in `defaults/main.yml`: `hardening_stale_sshd_dropins: ["10-zcrypto.conf"]` with the existing comment moved above it. The capture hosts' behavior is unchanged by construction (same file, same absent state).

- [ ] **Step 2: Verify** — `uv run pre-commit run -a` clean; grep proves no other reference: `grep -rn "10-zcrypto.conf" infra/ansible/` shows only bootstrap.yml + the new default.
- [ ] **Step 3: Commit** `feat(config): hardening role parameterizes stale sshd drop-in removal`.

### Task 3: Identity + secrets + the client-cert script

**Files:**

- Create: `infra/scripts/zaccess-client-cert.sh`
- Create: `infra/ansible/roles/access/files/pinned-leaves/.gitkeep` (dir exists before first leaf)
- Create (generated, committed): `infra/ansible/files/deploy_zaccess_ed25519` (vault-encrypted) + `.pub`, `infra/ansible/files/zaccess_ca.crt`
- Modify: `infra/ansible/scripts/run.sh` (add the key to the load loop)
- Modify (vault): `infra/ansible/group_vars/all/vault.yml`
- Test: `tests/test_zaccess_client_cert.py`

**Interfaces:**

- Produces vault vars (group_vars/all/vault.yml): `zaccess_wg_bridgehead_private_key`, `zaccess_wg_ops_private_key`, `zaccess_wg_preshared_key` — consumed by Tasks 5/6 templates. CA private key lives as its own vault-encrypted file `infra/ansible/files/zaccess_ca.key.vault` (the script streams it; it is not an Ansible var — nothing renders it).
- Produces: `zaccess-client-cert.sh issue <name> [--days N]` → `roles/access/files/pinned-leaves/<name>.pem` + `~/Downloads/zaccess-<name>.p12` (printed passphrase, then vaulted by the operator step).

- [ ] **Step 1: Write the failing script test** — the script must be testable without the vault: `ZACCESS_CA_KEY_CMD` overrides the default `ansible-vault view` pipeline.

```python
"""zaccess-client-cert.sh (spec 00075 D16): issue pins a leaf; absence of the PEM is revocation.
Tested against a throwaway CA -- the vault pipeline is override-injected, never touched here."""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/zaccess-client-cert.sh"

@pytest.fixture()
def ca(tmp_path):
    key, crt = tmp_path / "ca.key", tmp_path / "ca.crt"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt",
                    "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", key, "-out", crt,
                    "-subj", "/CN=test-ca", "-days", "2"], check=True, capture_output=True)
    return key, crt

def _issue(tmp_path, ca, name, *extra):
    key, crt = ca
    return subprocess.run(
        [str(SCRIPT), "issue", name, "--out-dir", str(tmp_path / "leaves"),
         "--p12-dir", str(tmp_path), *extra],
        env={"PATH": "/usr/bin:/bin", "ZACCESS_CA_KEY_CMD": f"cat {key}",
             "ZACCESS_CA_CRT": str(crt), "ZACCESS_P12_PASS": "test-pass", "HOME": str(tmp_path)},
        capture_output=True, text=True)

def test_issue_creates_pinned_leaf_and_p12(tmp_path, ca):
    r = _issue(tmp_path, ca, "macbook")
    assert r.returncode == 0, r.stderr
    leaf = tmp_path / "leaves/macbook.pem"
    assert leaf.exists() and (tmp_path / "zaccess-macbook.p12").exists()
    verify = subprocess.run(["openssl", "verify", "-CAfile", str(ca[1]), str(leaf)],
                            capture_output=True, text=True)
    assert "OK" in verify.stdout

def test_issue_refuses_overwrite(tmp_path, ca):
    assert _issue(tmp_path, ca, "macbook").returncode == 0
    r = _issue(tmp_path, ca, "macbook")
    assert r.returncode != 0 and "exists" in r.stderr
```

- [ ] **Step 2: Run — expect FAIL** (script missing): `uv run pytest tests/test_zaccess_client_cert.py -q`
- [ ] **Step 3: Write the script** (`chmod +x`):

```bash
#!/usr/bin/env bash
# Issue a pinned mTLS client leaf for the zaccess edge (spec 00075 D16).
#   zaccess-client-cert.sh issue <name> [--days N] [--out-dir DIR] [--p12-dir DIR]
# The CA private key is STREAMED from the vault (never written to disk): default
#   ZACCESS_CA_KEY_CMD="uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/zaccess_ca.key.vault"
# run from infra/ansible/. Revocation is the PEM's absence: delete it from pinned-leaves/ and
# converge. Tests override ZACCESS_CA_KEY_CMD/ZACCESS_CA_CRT/ZACCESS_P12_PASS.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CMD="${1:?usage: issue <name> [--days N]}"; shift
[ "$CMD" = "issue" ] || { echo "unknown command: $CMD" >&2; exit 2; }
NAME="${1:?leaf name required}"; shift
DAYS=365
OUT_DIR="$REPO/infra/ansible/roles/access/files/pinned-leaves"
P12_DIR="${HOME:-/tmp}/Downloads"
while [ $# -gt 0 ]; do case "$1" in
  --days) DAYS="$2"; shift 2;;
  --out-dir) OUT_DIR="$2"; shift 2;;
  --p12-dir) P12_DIR="$2"; shift 2;;
  *) echo "unknown flag: $1" >&2; exit 2;;
esac; done
CA_CRT="${ZACCESS_CA_CRT:-$REPO/infra/ansible/files/zaccess_ca.crt}"
CA_KEY_CMD="${ZACCESS_CA_KEY_CMD:-cd $REPO/infra/ansible && uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/zaccess_ca.key.vault}"
LEAF="$OUT_DIR/$NAME.pem"
[ -e "$LEAF" ] && { echo "refusing: $LEAF exists — revoke (delete) first or pick a new name" >&2; exit 1; }
mkdir -p "$OUT_DIR" "$P12_DIR"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout "$WORK/leaf.key" -out "$WORK/leaf.csr" -subj "/CN=zaccess-$NAME" 2>/dev/null
bash -c "$CA_KEY_CMD" | openssl x509 -req -in "$WORK/leaf.csr" -CA "$CA_CRT" \
  -CAkey /dev/stdin -CAserial "$WORK/ca.srl" -CAcreateserial -days "$DAYS" -out "$LEAF" 2>/dev/null
PASS="${ZACCESS_P12_PASS:-$(openssl rand -base64 18)}"
# -legacy is the documented fallback if macOS Keychain rejects OpenSSL 3's default PBES2 encoding.
openssl pkcs12 -export -in "$LEAF" -inkey "$WORK/leaf.key" -certfile "$CA_CRT" \
  -name "zaccess-$NAME" -out "$P12_DIR/zaccess-$NAME.p12" -passout "pass:$PASS"
PF="$P12_DIR/zaccess-$NAME.p12.pass"
( umask 077; printf '%s\n' "$PASS" > "$PF" )   # never echoed -- the transcript must not carry it
echo "leaf pinned: $LEAF"
echo "bundle:      $P12_DIR/zaccess-$NAME.p12   (passphrase in $PF, mode 0600)"
echo "next: import the .p12, vault bundle+passphrase, DELETE both local files, converge zaccess"
```

- [ ] **Step 4: Run tests — expect PASS.** Also `uv run pre-commit run -a` (shellcheck-class hooks).
- [ ] **Step 5: Generate the real material** (workstation, from `infra/ansible/`; nothing printed but public halves):
  - `ssh-keygen -t ed25519 -f files/deploy_zaccess_ed25519 -N '' -C zaccess-deploy` then `uv run ansible-vault encrypt --vault-password-file scripts/vault-pass.sh files/deploy_zaccess_ed25519`
  - CA: `openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout /dev/stdout -out files/zaccess_ca.crt -subj "/CN=zaccess-client-ca" -days 3650 | uv run ansible-vault encrypt --vault-password-file scripts/vault-pass.sh --output files/zaccess_ca.key.vault -`
  - WG: `wg genkey`/`wg genpsk` ×3, each piped `| uv run ansible-vault encrypt_string --vault-password-file scripts/vault-pass.sh --stdin-name <var>` and the ciphertext pasted into `group_vars/all/vault.yml` (`ansible-vault edit` is interactive — nothing can be piped into it, and `encrypt_string` keeps the private halves off the terminal); derive+record each public key with `wg pubkey` into `group_vars/all/vars.yml` (Task 6 reads them there).
  - Leaf: `infra/scripts/zaccess-client-cert.sh issue macbook`; vault the `.p12` + passphrase into `group_vars/all/vault.yml` (`zaccess_client_p12_b64`, `zaccess_client_p12_pass`); **operator**: import into the MacBook keychain.
- [ ] **Step 6: Wire run.sh** — add `files/deploy_zaccess_ed25519` to the `for k in …` loop.
- [ ] **Step 7: Commit** `feat(config): zaccess identity, CA, and the client-leaf script` (script + tests + pubkeys + vault files + run.sh).

### Task 4: Inventory, group/host vars, bootstrap play — execute Phase 1

**Files:**

- Modify: `infra/ansible/inventory/hosts.yml`, `infra/ansible/bootstrap.yml`
- Create: `infra/ansible/group_vars/access_host/vars.yml`, `infra/ansible/host_vars/zaccess/vars.yml`
- Modify: `infra/ansible/roles/base/…` only if the `base_fleet_hosts` reboot-slot assert needs `zaccess` added — read the var's definition first and extend the list where it lives.

**Interfaces:**

- Produces: host `zaccess` in groups `access_host` + `observed`; `ansible_port: 10022`; group vars consumed by Task 5's play.

- [ ] **Step 1: Inventory** — add under `all.children`:

```yaml
    # The internet bridgehead (spec 00075): access tier only. NEVER engine_host/capture_host —
    # no trade key, no capture data; everything on it is re-issuable.
    access_host:
      hosts:
        zaccess: {}
```

and add `access_host: {}` to `observed.children`.

- [ ] **Step 2: `host_vars/zaccess/vars.yml`:**

```yaml
# host_vars/zaccess — the internet bridgehead (spec 00075): Linode 1 GB, 1 vCPU, 25 GB.
ansible_host: zaccess.zhaow.me
base_hostname: zaccess
# Fleet reboot slots: 21:25 zcrypto, 22:25 zcrypto-red, 02:25 ops. 05:25 is >=1 h from every
# other slot, off the hour boundary, >=1 h from the 4-hourly engine boundaries (04:00/08:00).
base_unattended_upgrades_reboot_time: "05:25"
deploy_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/deploy_zaccess_ed25519.pub') }}"
```

- [ ] **Step 3: `group_vars/access_host/vars.yml`:**

```yaml
# The access tier (spec 00075). Edge host: no docker, no capture, no trade key.
ansible_user: zcrypto-deploy
ansible_port: 10022
# ssh_hardening AllowUsers (D10): no zcrypto-data here — the NAS pull channel does not exist.
hardening_ssh_allow_users: zcrypto-deploy root
# D10/D6: the fleet default force-enables ip_forward for Docker hosts; this host runs no
# containers and no NAT — the CIS default 0 IS the design. Keep only the two kernel keys.
hardening_extra_sysctl:
  kernel.dmesg_restrict: 1
  kernel.yama.ptrace_scope: 1
hardening_stale_sshd_dropins: ["10-zaccess-interim.conf"]
# D8: the four exposed ports beyond sshd. The Linode Cloud Firewall mirrors this list — a
# future addition must open BOTH layers.
firewall_extra_tcp_ports: [80, 443, 20022]
firewall_extra_udp_ports: [51820]
# WireGuard endpoint identity (public halves; privates vaulted in group_vars/all/vault.yml)
zaccess_wg_bridgehead_public_key: "<paste from wg pubkey in Task 3>"
zaccess_wg_ops_public_key: "<paste from wg pubkey in Task 3>"
```

(The two `<paste …>` values are filled at Task 3 Step 5 execution time — they are measured outputs, not placeholders an implementer invents.)

- [ ] **Step 4: Bootstrap play** — append to `bootstrap.yml` (mirrors the ops play: user+key+sudo+python3 only; **no sshd task** — the interim drop-in governs until Phase 2; root is already key-only so this play runs as root@10022):

```yaml
- name: Bootstrap access bridgehead — zcrypto-deploy user only (sshd stays as the interim drop-in left it)
  hosts: access_host
  gather_facts: false
  vars:
    ansible_user: root
    ansible_port: 10022
  tasks:
    - name: zcrypto-deploy sudo user
      ansible.builtin.user: {name: zcrypto-deploy, groups: sudo, shell: /bin/bash, create_home: true}
    - name: passwordless sudo for zcrypto-deploy (automation)
      ansible.builtin.copy:
        dest: /etc/sudoers.d/zcrypto-deploy
        content: "zcrypto-deploy ALL=(ALL) NOPASSWD:ALL\n"
        mode: '0440'
        validate: 'visudo -cf %s'
    - name: install zcrypto-deploy authorized key (exclusive — one key, no drift)
      ansible.posix.authorized_key: {user: zcrypto-deploy, key: "{{ deploy_authorized_key }}", state: present, exclusive: true}
    - name: ensure python3 + sudo
      ansible.builtin.apt: {name: [python3, sudo], state: present, update_cache: true}
```

- [ ] **Step 5 (ATTENDED): Execute** — first confirm root@10022 still answers the operator key (`timeout 30 ssh -o BatchMode=yes -p 10022 root@zaccess.zhaow.me true`), then `timeout 300 ./scripts/run.sh bootstrap.yml --limit zaccess`. Verify through the vaulted deploy key (it lives only in `run.sh`'s throwaway agent, so spell the agent out): `eval $(ssh-agent -s); uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/deploy_zaccess_ed25519 | ssh-add -; timeout 30 ssh -o BatchMode=yes -p 10022 zcrypto-deploy@zaccess.zhaow.me 'sudo -n true && echo DEPLOY-OK'; ssh-agent -k` → `DEPLOY-OK`. A second `run.sh bootstrap.yml --limit zaccess` reports `changed=0` (idempotence).
- [ ] **Step 6: Commit** `feat(config): zaccess joins the inventory; bridgehead bootstrap play`.

### Task 5: The `access` role baseline + native Alloy — execute Phase 2

**Files:**

- Create: `infra/ansible/roles/access/tasks/main.yml`, `handlers/main.yml`, `defaults/main.yml`, `files/config.alloy`, `templates/alloy-env.j2`, `templates/zaccess-probe.sh.j2`, `templates/zaccess-probe.{service,timer}.j2`
- Modify: `infra/ansible/site.yml` (the new play), `tests/test_infra_alloy_series.py`, `infra/grafana/alerts.yaml`, `infra/runbooks/README.md`

**Interfaces:**

- Produces on the host: `alloy` (native, apt-pinned via `access_alloy_version`), `/etc/alloy/config.alloy`, `/etc/default/alloy` (`CONFIG_FILE="/etc/alloy/config.alloy"`, the deb's `CUSTOM_ARGS=""`, and the `GRAFANA_*` creds), probe timer writing `/var/lib/zaccess-textfiles/zaccess.prom`.
- Produces metric names (consumed by alerts + the admission test): `zaccess_wireguard_handshake_age_seconds`, `zaccess_tls_not_after_seconds{target=…}`, plus `up` and the node families.

- [ ] **Step 1: site.yml play** — append after the NAS play:

```yaml
- name: converge the access bridgehead — the internet edge (spec 00075)
  hosts: access_host
  become: true
  pre_tasks:
    - name: note — the bridgehead's charter
      ansible.builtin.debug:
        msg: >-
          Internet edge (spec 00075): no trade key, no capture data, no containers. Everything
          on it is re-issuable (certs re-ACME, keys vaulted) — losing the VPS is re-provisioning,
          not data loss. Never in engine_host/capture_host; ordinary runs are --limit zaccess.
      tags: [always]
  roles:
    - role: base
      tags: [base]
    - role: hardening
      tags: [hardening]
    - role: firewall
      tags: [firewall]
    - role: fail2ban
      tags: [fail2ban]
    - role: chrony
      tags: [chrony]
    - role: access
      tags: [access]
```

- [ ] **Step 2: role `access` — baseline tasks** (`tasks/main.yml`, first block):

```yaml
# The access role (spec 00075): WireGuard server + relays + Caddy edge + native Alloy.
- name: wireguard + probe dependencies
  ansible.builtin.apt: {name: [wireguard-tools], state: present}

- name: grafana apt keyring
  ansible.builtin.get_url:
    url: https://apt.grafana.com/gpg.key
    dest: /etc/apt/keyrings/grafana.asc
    mode: '0644'
- name: grafana apt repo
  ansible.builtin.apt_repository:
    repo: "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main"
    filename: grafana
- name: alloy, pinned (D11 — native, no docker on the edge; pin recorded in fleet-pins.md)
  ansible.builtin.apt:
    name: "alloy={{ access_alloy_version }}"
    state: present
    allow_change_held_packages: false
- name: hold alloy at the pin
  ansible.builtin.dpkg_selections: {name: alloy, selection: hold}

- name: alloy env — CONFIG_FILE + credentials (the deb's unit reads EnvironmentFile=/etc/default/alloy)
  ansible.builtin.template:
    src: alloy-env.j2
    dest: /etc/default/alloy
    owner: root
    group: alloy
    mode: '0640'
  no_log: true   # renders the Grafana Cloud push credentials — keep them out of --diff output
  notify: restart alloy
- name: alloy config — UNGATED copy; every converge ships it, so a hand edit cannot outlive
        the next converge. That is the whole drift remedy: the other tiers carry asserts because
        their copies are digest-gated and an ordinary converge skips them — this one is not.
  ansible.builtin.copy:
    src: config.alloy
    dest: /etc/alloy/config.alloy
    owner: root
    group: alloy
    mode: '0640'
  notify: restart alloy
- name: alloy enabled + started
  ansible.builtin.systemd: {name: alloy, enabled: true, state: started}

- name: textfile dir for the probe
  ansible.builtin.file: {path: /var/lib/zaccess-textfiles, state: directory, mode: '0755'}
- name: probe script
  ansible.builtin.template:
    src: zaccess-probe.sh.j2
    dest: /usr/local/sbin/zaccess-probe
    mode: '0755'
- name: probe service + timer
  ansible.builtin.template:
    src: "zaccess-probe.{{ item }}.j2"
    dest: "/etc/systemd/system/zaccess-probe.{{ item }}"
    mode: '0644'
  loop: [service, timer]
  notify: reload systemd
- name: probe timer enabled
  ansible.builtin.systemd: {name: zaccess-probe.timer, enabled: true, state: started, daemon_reload: true}
```

`handlers/main.yml`: `restart alloy` → `ansible.builtin.systemd: {name: alloy, state: restarted}` (stateless — a restart loses nothing); `reload systemd` → `daemon_reload: true`. `defaults/main.yml`: `access_alloy_version: "<current upstream at execution — record in fleet-pins.md>"`, `access_wg_listen_port: 51820`, `access_acme_email: zhaow.km@gmail.com`. Version bumps (alloy and caddy alike): `dpkg --set-selections` unhold → converge with the new pin → hold is re-applied by the role — note this beside both pins in `fleet-pins.md` at Task 11.

- [ ] **Step 3: `files/config.alloy`** — mirror the ops shape (unix exporter + textfile + scrape + keep + remote_write with `sys.env("…")` credentials — the ops config's exact idiom — read from `/etc/default/alloy`; `alloy-env.j2` renders `CONFIG_FILE`, `CUSTOM_ARGS=""`, and `GRAFANA_PROM_URL/USER/TOKEN` + `GRAFANA_LOKI_*` from the `observed` vault vars). `external_labels = { host = "zaccess" }` (the dark alert and Step 8's verify select on it). Keep-regex (the admission test pins it) — `node_textfile_mtime_seconds`/`node_textfile_scrape_error` are the did-the-timer-RUN discriminators: without them a dead probe timer serves its last gauges forever and the tunnel-stale and cert alerts can never fire (the ops green-when-blind lesson, 2026-07-28):

```
up|node_cpu_seconds_total|node_load1|node_memory_MemAvailable_bytes|node_memory_MemTotal_bytes|node_filesystem_avail_bytes|node_filesystem_size_bytes|node_network_receive_bytes_total|node_network_transmit_bytes_total|node_textfile_mtime_seconds|node_textfile_scrape_error|zaccess_wireguard_handshake_age_seconds|zaccess_tls_not_after_seconds
```

- [ ] **Step 4: probe script template** (`zaccess-probe.sh.j2`) — atomic write + explicit chmod (the `mktemp` 0600 lesson):

```bash
#!/usr/bin/env bash
# Rendered by the `access` role at /usr/local/sbin/zaccess-probe — edit the template, not this.
# Writes zaccess.prom: WireGuard handshake age + edge TLS notAfter per vhost (spec 00075 D11).
set -euo pipefail
OUT=/var/lib/zaccess-textfiles/zaccess.prom
TMP="$(mktemp "${OUT}.XXXX")"; trap 'rm -f "$TMP"' EXIT
{
  hs=$(wg show zaccess0 latest-handshakes 2>/dev/null | awk '{print $2}' | head -1 || true)
  if [ -n "${hs:-}" ] && [ "$hs" -gt 0 ]; then
    echo "# HELP zaccess_wireguard_handshake_age_seconds Seconds since the tunnel peer's last handshake."
    echo "# TYPE zaccess_wireguard_handshake_age_seconds gauge"
    echo "zaccess_wireguard_handshake_age_seconds $(( $(date +%s) - hs ))"
  fi
  for t in tmux nas; do
    na=$(echo | timeout 10 openssl s_client -connect 127.0.0.1:443 -servername "$t.zaccess.zhaow.me" 2>/dev/null \
         | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2) || continue
    [ -n "$na" ] || continue
    echo "zaccess_tls_not_after_seconds{target=\"$t\"} $(date -d "$na" +%s)"
  done
} > "$TMP"
chmod 0644 "$TMP"   # mktemp makes 0600 and mv preserves it — the collector reads as non-root
mv "$TMP" "$OUT"
```

Service/timer: `Type=oneshot`, `OnCalendar=*:2/5:11` (every 5 min), `Description=Access-edge probe writing WireGuard and TLS gauges` (comment above carries the spec token). Absent tunnel/certs → the block simply emits nothing yet (Phase 3/5 light them up).

- [ ] **Step 5: extend the admission test** — add `ACCESS_ALLOY = REPO / "infra/ansible/roles/access/files/config.alloy"` with its expected-series list (`up`, the node families above, the two `zaccess_*` names) in the existing per-host pattern.
- [ ] **Step 6: alerts + runbook** — add to `infra/grafana/alerts.yaml`: `zcrypto-alloy-dark-zaccess`, joining the existing `Fleet · Alloy dark` family's exact two-stage shape (PromQL stage `count(up{host="zaccess"}) or on() vector(0)`, separate threshold stage `< 1` — a single inline string parses as `count(...) or on() (vector(0) < 1)` and never thresholds the live branch; copy an existing family member and change the host), summary → `infra/runbooks/README.md#zaccess-bridgehead-dark` and `zaccess-disk-high` (`node_filesystem_avail_bytes{host="zaccess",mountpoint="/"} / node_filesystem_size_bytes < 0.15`, 30m). Author both runbook sections (four-part shape, `— ALERT`, checkable *Retire when*).
- [ ] **Step 7: Run the full test suite** — PASS; commit `feat(config): the access role — baseline, native alloy, probe, dark+disk alerts` (infra + tests), `docs(runbooks)` separately if mdformat splits kinds.
- [ ] **Step 8 (ATTENDED): converge Phase 2** — preview `timeout 600 ./scripts/run.sh site.yml --limit zaccess --check --diff`, then run. **Lockout-critical**: ssh_hardening rewrites sshd config — keep the current session open, verify a fresh `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me` before closing anything. Verify by outcome: `sshd -T | grep -E "permitrootlogin|passwordauthentication"` (prohibit-password / no), interim drop-in gone, `nft list ruleset | grep -c dport` = 3 lines (ssh + tcp set + udp set), `systemctl is-active alloy fail2ban nftables` all active, and from the workstation `uv run python infra/scripts/grafana-query.py 'up{host="zaccess"}'` → 1.
- [ ] **Step 9 (ATTENDED): push alerts** — `infra/scripts/grafana-push.sh` with the SA token from the vault; read back both rules HTTP 200.

### Task 6: WireGuard both ends + `access_ops` — execute Phase 3

**Files:**

- Create: `infra/ansible/roles/access/templates/zaccess0.conf.j2` (server), task block in `access`
- Create: `infra/ansible/roles/access_ops/{tasks/main.yml,handlers/main.yml,templates/zaccess0.conf.j2,templates/tmux.conf.j2,templates/zaccess-probe-ops.sh.j2,templates/zaccess-probe-ops.{service,timer}.j2}`
- Modify: `infra/ansible/site.yml` (ops play gains the role), `infra/grafana/alerts.yaml`, `infra/runbooks/README.md`

**Interfaces:**

- Consumes: `zaccess_wg_*_public_key` — **moved** to `group_vars/all/vars.yml` (Step 1): one plaintext record both plays read; never duplicated (duplication is drift).
- Produces: `wg-quick@zaccess0` on both hosts; ops probe writes `zaccess_wireguard_handshake_age_seconds` + `zaccess_tls_not_after_seconds{target="nas-dsm"}` into the ops textfile dir (the existing ops unix exporter picks it up — extend the **ops** keep-regex with `zaccess_.*` and the admission test with it).

- [ ] **Step 1: move the two WG public keys** to `group_vars/all/vars.yml` (plaintext record, both plays read them); bridgehead server conf template:

```ini
# Rendered by the `access` role at /etc/wireguard/zaccess0.conf — edit the template.
[Interface]
Address = 10.99.0.1/24
ListenPort = {{ access_wg_listen_port }}
PrivateKey = {{ zaccess_wg_bridgehead_private_key }}

[Peer]
PublicKey = {{ zaccess_wg_ops_public_key }}
PresharedKey = {{ zaccess_wg_preshared_key }}
AllowedIPs = 10.99.0.2/32
```

Task block: template (0600, `no_log: true` on the template task), `systemd: {name: wg-quick@zaccess0, enabled: true, state: started}`, handler `restart wg-quick@zaccess0` on conf change.

- [ ] **Step 2: `access_ops` role** — `ansible.builtin.apt: {name: [wireguard-tools], state: present}` (ops needs `wg-quick`/`wg show` too — the access role installs it only on the bridgehead); WG client conf (`Address = 10.99.0.2/24`, `Endpoint = zaccess.zhaow.me:{{ access_wg_listen_port }}`, `PersistentKeepalive = 25`, `AllowedIPs = 10.99.0.1/32`), unit enabled; managed tmux conf (D15):

```yaml
- name: managed ~/.tmux.conf for zhaow (D15 — hand edits are overwritten by design)
  ansible.builtin.template:
    src: tmux.conf.j2
    dest: /home/zhaow/.tmux.conf
    owner: zhaow
    group: zhaow
    mode: '0644'
  notify: source tmux conf
```

`tmux.conf.j2` = managed header + `set -g mouse on` + `set -g history-limit 10000`. Handler:

```yaml
- name: source tmux conf
  ansible.builtin.command: tmux source-file /home/zhaow/.tmux.conf
  become_user: zhaow
  failed_when: false   # no server running = nothing to apply; the file governs the next start
```

Ops probe script: same shape as the bridgehead's, `wg show zaccess0` + `openssl s_client -connect 192.168.100.5:5001 -servername z-home-storage.zhaow.pro` → `zaccess_tls_not_after_seconds{target="nas-dsm"}`; writes into the existing ops textfile dir — the operand is the `ops` role's `ops_textfile_dir` variable (the path in `roles/ops/files/config.alloy` is the *container-side* mount, not the host path).

- [ ] **Step 3: wire into site.yml ops play** — `- role: access_ops` + `tags: [access]`; extend ops keep-regex + admission test with `zaccess_.*`. **The ops `config.alloy` edit makes Alloy the subject** — the converge must pass `-e ops_alloy_digest=<currently-running>` (rule in `capture-deploys.md`).
- [ ] **Step 4: alert + runbook** — `zaccess-tunnel-stale`: `max(zaccess_wireguard_handshake_age_seconds) > 300` for 10m — **either** end reporting stale fires (`max`), and `PersistentKeepalive=25` makes >300 s genuinely wrong; a fully dark bridgehead is the dark alert's job, not this one's. Summary → runbook anchor.
- [ ] **Step 5: tests + commit** `feat(config): wireguard link + access_ops (probe, managed tmux conf)`.
- [ ] **Step 6 (ATTENDED): converge** — bridgehead `--limit zaccess --tags access`; ops `--limit zcrypto-ops --tags access,ops -e ops_alloy_digest=<running>` — the keep-regex lives in the `ops` role's digest-gated Alloy block, so `--tags access` alone can never ship it (preview both `--check --diff`; the ops preview must show only access_ops resources + the ops role's Alloy config/container tasks — any capture/engine/nas line stops the run). Verify: `wg show zaccess0` on both ends shows a handshake < 3 min old; `grafana-query.py 'zaccess_wireguard_handshake_age_seconds'` returns both hosts; tmux conf untouched-by-diff on the live session (`tmux show -g window-size` unchanged, session dimensions unchanged). Push the alert (attended), read back 200.

### Task 7: SSH relay — execute Phase 4 (G1)

**Files:**

- Create: `infra/ansible/roles/access/templates/zaccess-ssh-proxy.{socket,service}.j2`, task block

- [ ] **Step 1: units** — socket-activated proxyd, dual-family:

```ini
# zaccess-ssh-proxy.socket — rendered by the `access` role.
[Unit]
Description=Public SSH relay socket for the access bridgehead
Requires=wg-quick@zaccess0.service
After=wg-quick@zaccess0.service
[Socket]
ListenStream=0.0.0.0:20022
ListenStream=[::]:20022
BindIPv6Only=ipv6-only
Accept=no
[Install]
WantedBy=sockets.target
```

```ini
# zaccess-ssh-proxy.service — rendered by the `access` role.
[Unit]
Description=Relay accepted SSH connections to the ops node over the tunnel
Requires=zaccess-ssh-proxy.socket wg-quick@zaccess0.service
After=zaccess-ssh-proxy.socket wg-quick@zaccess0.service
[Service]
ExecStart=/usr/lib/systemd/systemd-socket-proxyd 10.99.0.2:22
PrivateTmp=yes
DynamicUser=yes
```

Task: template both, `systemd: {name: zaccess-ssh-proxy.socket, enabled: true, state: started, daemon_reload: true}`.

- [ ] **Step 1b:** these are the repo's first `.socket` units — an operator-visible surface (`Description=` prints in `systemctl status`). Extend `tests/test_internal_terms_not_operator_visible.py`'s unit glob to include `*.socket`/`*.socket.j2` in the same commit, per `operator-facing-text.md` (a new surface joins the list and the test together).

- [ ] **Step 2 (ATTENDED): converge + G1 verify** — `--limit zaccess --tags access`; from the workstation `timeout 30 ssh -p 20022 zhaow@zaccess.zhaow.me hostname` → `zcrypto-ops`; **operator step**: repeat from a genuinely external network (phone hotspot), and from an IPv6-only network if available; record both results in the PR body's test plan.
- [ ] **Step 3: Commit** `feat(config): the public ssh relay — G1 live`.

### Task 8: Caddy + mTLS + certificates — execute Phase 5

**Files:**

- Create: `infra/ansible/roles/access/templates/Caddyfile.j2`, task block (caddy apt repo pinned + hold, same pattern as alloy)
- Modify: `infra/grafana/alerts.yaml`, `infra/runbooks/README.md`

- [ ] **Step 1 (OPERATOR): Route53** — create `tmux.zaccess.zhaow.me` + `nas.zaccess.zhaow.me` A/AAAA → the Linode addresses; verify `host` resolves both; record in `fleet.md` at Task 11 (D18).
- [ ] **Step 2: Caddyfile** (static-page first — D14: mTLS proven before any upstream exists):

```caddyfile
# Rendered by the `access` role at /etc/caddy/Caddyfile — edit the template.
{
	email {{ access_acme_email }}
}

(mtls) {
	tls {
		client_auth {
			mode require_and_verify
			trust_pool file /etc/caddy/zaccess_ca.crt
			verifier leaf {
				{% for leaf in access_pinned_leaves %}
				file /etc/caddy/pinned-leaves/{{ leaf }}
				{% endfor %}
			}
		}
	}
}

tmux.zaccess.zhaow.me {
	import mtls
	respond "zaccess: tmux edge up (no upstream yet)" 200
}

nas.zaccess.zhaow.me {
	import mtls
	respond "zaccess: nas edge up (no upstream yet)" 200
}
```

Tasks: install `caddy={{ access_caddy_version }}` + hold; copy `files/zaccess_ca.crt` + the `pinned-leaves/` dir (`access_pinned_leaves: "{{ lookup('fileglob', role_path ~ '/files/pinned-leaves/*.pem', wantlist=true) | map('basename') | list }}"` in defaults); `validate: caddy validate --adapter caddyfile --config %s` on the template task; handler `reload caddy`. **The `verifier leaf` directive syntax is confirmed against the pinned version's docs before the converge; if it diverges, fix the template — the negative test below is the arbiter that the gate is real.**

- [ ] **Step 3 (ATTENDED): converge + prove the gate** — after ACME issues both certs (Caddy logs): mTLS **negative** test — three assertions together, so a worded 403 page cannot false-pass the load-bearing check: `timeout 30 curl -sv https://tmux.zaccess.zhaow.me/` (no client cert) must (a) exit non-zero, (b) emit **no** `HTTP/` line at all, and (c) show a TLS-level failure (`alert certificate required` or equivalent handshake alert) in the `-v` trace; **positive** test with the leaf+key extracted to temp files → `200`; forced staging renewal (`caddy` reload against the staging CA on a scratch vhost or `--force` renew) succeeds; probe now exports `zaccess_tls_not_after_seconds{target="tmux"|"nas"}` (query it).
- [ ] **Step 4: cert alert + runbook** — `zaccess-cert-expiring`: `min(zaccess_tls_not_after_seconds) - time() < 14*86400` for 1h (covers all targets incl. `nas-dsm`), summary → anchor. Push attended, read back 200.
- [ ] **Step 5: Revocation drill (ATTENDED)** — `zaccess-client-cert.sh issue drill-throwaway` → converge → positive test with the throwaway → delete its PEM → converge → the throwaway is refused at handshake while the macbook leaf still passes. Delete the local drill `.p12`.
- [ ] **Step 6: Commit** `feat(config): caddy mtls edge + cert-expiry alerting — the gate is proven`.

### Task 9: NAS relay — execute Phase 6 (G3)

**Files:**

- Create: `infra/ansible/roles/access_ops/templates/zaccess-nas-proxy.{socket,service}.j2`, task block
- Modify: `infra/ansible/roles/access/templates/Caddyfile.j2` (nas vhost gains its upstream)

- [ ] **Step 1: ops-side units** — socket `ListenStream=10.99.0.2:5001` (`FreeBind=yes` so the unit survives ordering races with the tunnel address; `After=wg-quick@zaccess0.service`), service `ExecStart=/usr/lib/systemd/systemd-socket-proxyd 192.168.100.5:5001`.
- [ ] **Step 2: Caddyfile nas vhost** — replace the static respond:

```caddyfile
nas.zaccess.zhaow.me {
	import mtls
	reverse_proxy https://10.99.0.2:5001 {
		transport http {
			tls_server_name z-home-storage.zhaow.pro
		}
	}
}
```

(Full verification against the Sectigo chain — D7: no `tls_insecure_skip_verify` anywhere.)

- [ ] **Step 3 (ATTENDED): converge both ends + G3 verify** — ops `--limit zcrypto-ops --tags access`, bridgehead `--limit zaccess --tags access`; **operator**: DSM login in a browser through `https://nas.zaccess.zhaow.me` with the client cert; confirm `target="nas-dsm"` gauge live.
- [ ] **Step 4: Commit** `feat(config): the nas relay — G3 live`.

### Task 10: agentboard — execute Phase 7 (G2)

**Files:**

- Create: `infra/ansible/roles/access_ops/templates/zaccess-agentboard.service.j2`, task block
- Modify: `infra/ansible/roles/access_ops/templates/tmux.conf.j2` (the D13/D15 pin), `infra/ansible/roles/access/templates/Caddyfile.j2` (tmux vhost upstream)

- [ ] **Step 1 (SPIKE, gates everything below — D13):** as `zhaow` on ops, install the pinned version into a scratch prefix (`npm install --prefix ~/zaccess-spike @gbasin/agentboard@0.4.5` — its platform package ships a self-contained binary; if it requires Bun at runtime, install pinned Bun for `zhaow` and record it in `fleet-pins.md`). Create a **decoy** long-running session (`tmux new-session -d -s spike-decoy 'sleep infinity'`) — never the real one. Run agentboard with `TMUX_SESSION=agentboard-spike`, `DISCOVER_PREFIXES=spike-`, bound to `127.0.0.1:4041`. **Gate checks**: attach/detach the decoy via the UI; attempt hibernate/kill/resize from every UI affordance; after each, `tmux list-sessions` + `tmux display -t spike-decoy -p '#{window_width}x#{window_height}'` unchanged and `sleep` still running. Any destructive capability against a *discovered* session ⇒ **fallback mode** (agentboard owns only its own session whose pane runs `tmux attach -t zcrypto`) — implement that variant instead. Record the spike verdict in the PR body.
- [ ] **Step 2: production install + the unit.** Install task in `access_ops` (shape settled by the spike — npm-global as `zhaow` with the version pinned, e.g. `npm install -g @gbasin/agentboard@{{ access_ops_agentboard_version }}` via the measured npm path, or pinned Bun if the spike proves the binary needs it); `defaults/main.yml` defines `access_ops_agentboard_version` and `access_ops_agentboard_exec` (the spike-measured absolute binary path — recorded in `fleet-pins.md` with the pin). Delete `~/zaccess-spike` and the decoy session once the spike verdict is recorded. The unit:

```ini
# zaccess-agentboard.service — rendered by the access_ops role. Traceability: spec 00075 D13.
[Unit]
Description=Web terminal bridge onto the operator tmux, tunnel-bound
Requires=wg-quick@zaccess0.service
After=wg-quick@zaccess0.service
[Service]
User=zhaow
Environment=TMUX_SESSION=agentboard
Environment=DISCOVER_PREFIXES=zcrypto
Environment=PORT=4040
Environment=HOST=10.99.0.2
ExecStart={{ access_ops_agentboard_exec }}
Restart=on-failure
[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: tmux pin** — append to `tmux.conf.j2`: `set -g window-size manual` + `set -g default-size 212x56` (D13 risk 2; the change-handler applies it live without reflowing the current window).
- [ ] **Step 4: Caddyfile tmux vhost** — `reverse_proxy 10.99.0.2:4040` (WebSocket works unconfigured in Caddy).
- [ ] **Step 5 (ATTENDED): converge both ends; G2 verify + the tmux non-disruption drill** — browser → `https://tmux.zaccess.zhaow.me` shows the `zcrypto` session; attach/detach repeatedly; `tmux display -p '#{window_width}x#{window_height}'` = 212x56 throughout, pane process untouched, scrollback intact, home-LAN `tmux attach` still works.
- [ ] **Step 6: Commit** `feat(config): agentboard behind the mtls edge — G2 live`.

### Task 11: Closeout

- [ ] **Step 1: drills** — (a) **idempotence**: a second full converge of each host (`--limit zaccess`, `--limit zcrypto-ops --tags access,ops -e ops_alloy_digest=<running>`) reports `changed=0` under `--check --diff`; (b) **reboot durability, both hosts**: reboot the bridgehead (attended) — all three paths return unattended; for ops, read the next 02:25 UTC auto-reboot's aftermath the following morning — all three paths back without intervention (an attended ops reboot works too if sooner is wanted); (c) **tunnel drill**: `systemctl restart wg-quick@zaccess0` on ops (a deleted interface has no self-healer — `wg-quick@` is oneshot; restart-and-observe is the honest drill), confirm the handshake re-establishes, and the stale alert fires and resolves across the gap; a real ISP address change is verified opportunistically — record it in `fleet.md`'s bridgehead section when observed. Record all results in the PR test plan.
- [ ] **Step 2: docs** — `docs/reference/fleet.md`: the bridgehead section (role, addresses, ports, DNS records, ssh alias suggestion, LISH break-glass); `docs/reference/fleet-pins.md`: `access_caddy_version`, `access_alloy_version`, agentboard pin + "every agentboard re-pin is security-relevant, attended, no bake"; `.claude/rules/capture-deploys.md`: an *Access converges* entry (`--limit zaccess`, no bake owed, tmux-conf handler semantics, both-firewall-layers note) — **protected set: present the exact diff for the owner's sign-off before committing**.
- [ ] **Step 3: memo + cleanup** — update `docs/memo.local.md` (DONE ITEMS staging via Edit/Write tools only, read-guard discipline), reconciling any `zaccess.zhaow.pro` mention to `.me`; `rm .tmp/access.md`; delete the local drill/leaf `.p12` + passphrase files after vaulting.
- [ ] **Step 4: iterations-history entry** (the plan's final task per `iterations-history.md`) — `docs/iterations-history-phase6.md`, one entry covering the component; load `iteration-closeout` for the format.
- [ ] **Step 5:** full `uv run pytest` + `uv run pre-commit run -a` clean; all commits trailered + reviewed; **report the branch ready and wait for the owner's word to open the PR** (one PR — D17).
