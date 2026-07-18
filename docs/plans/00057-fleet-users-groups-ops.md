# Fleet users/groups regularization — ops phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Tasks 3, 4, 6 are ATTENDED, orchestrator-only** (live host mutation on a home-LAN production node) — never subagent work.

**Goal:** Migrate the ops node's entire machine-to-machine data path from `deploy` (the sudo user) to a new dedicated `zcrypto-data` identity, wire `zhaow`'s hot-out authoring, and rename `deploy → zcrypto-deploy` — landing the ops node in the fleet users/groups model (spec `00057`, phase 1).

**Architecture:** `zcrypto-data` (no sudo, no password; a real `/bin/bash` shell jailed to `rrsync -ro` by the forced-command keys — `nologin` would block the pulls, corrected during execution) becomes the ops node's m2m identity: it runs the data containers (`--user`), owns the data trees, and serves the four NAS pull channels via Ansible-provisioned `rrsync -ro` forced commands. `deploy` leaves the data path entirely and is renamed `zcrypto-deploy` (interactive+sudo only). `zhaow` authors into the `hot-out` outbox via a shared setgid `zcrypto-hot` group. The whole migration is ordered so the live liquidations pull is never lost — the Coinalyze poller back-fills its ~30 h window across a brief restart, and every rsync pull is `--ignore-existing` (a delayed pull catches up, never loses).

**Tech Stack:** Ansible (`ansible.builtin.user`/`group`/`file`, `ansible.posix.authorized_key`), the `ops`/`nas`/`base` roles + `bootstrap.yml`, rootful Docker with `--user`, rsync-over-ssh with `rrsync` forced commands, `infra/ansible/scripts/run.sh` (vaulted deploy-key throwaway agent).

## Global Constraints

- **`zcrypto-data`**: `system: true`, `shell: /bin/bash` (corrected from `nologin` — it must serve the `rrsync -ro` forced-command pulls, which sshd runs via the login shell, so `nologin` swallows them; the `command=`/`restrict` keys keep each jailed to one read-only subtree, and there is no password, so no interactive login is reachable), **no sudo, no tty**; uid/gid auto-assigned (spec D8 — only `zhaow` needs a pinned uid). Runs the data containers via `--user`, never invokes Docker itself.
- **`zhaow`**: uid/gid **1000**, unchanged (spec D7, hard constraint). The ops-role tasks add it to a group only when the account already exists — the pipeline role never *creates* it.
- **`zcrypto-deploy`** (was `deploy`): interactive + sudo, Ansible + human ssh only; **never in the data path**; `authorized_keys` = one key (`exclusive: true`).
- **Everything on captures/red/ops is Ansible-provisioned** (owner constraint). The four sync pull keys stop being hand-installed and become role-managed.
- **Transport is always `rsync --archive --ignore-existing`, never `--delete`** (append-only by construction). The push channel never goes through the rw NFS mount.
- **The ops node never joins `engine_host`, holds no trade key** (spec 00051 D10). No engine concerns here.
- **NEVER** run `ansible-inventory --host`/`--list`; never decrypt/echo/write a secret in cleartext; run playbooks via `infra/ansible/scripts/run.sh`; **preview every converge with `--check --diff`** before applying.
- **The vaulted key files keep their `deploy_<host>` names** (spec D1 — named by purpose, no rename). The NAS **group** `zcrypto` stays un-renamed (spec D6); that host is out of scope here (owner did the NAS renames manually).
- The plan is driven by **spec `00057`**; the open topic `T0067` is the tracking pointer, not the source of truth.

## Current state (measured 2026-07-18, this is what you are migrating FROM)

- `deploy` uid 1001, gid 1001(deploy), groups deploy/sudo/docker — interactive+sudo, the `ansible_user` for ops, and the account the NAS connects to for all four pulls.
- The ops containers (liquidations poller, reconciler/backfill, panel-materialize) run as `ops_uid:ops_gid` = **deploy** (`roles/ops/tasks/main.yml` lines ~153-161, a `getent passwd deploy` → `set_fact`).
- Data trees `deploy`-owned under `/var/lib/zcrypto-ops/`: `liquidations`, `l2-panel`, `capture-reconciled`, `hot-out`.
- Four hand-installed `command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/<root>",restrict` entries in `~deploy/.ssh/authorized_keys` (comments `sync_liquidations` / `sync_panel` / `sync_reconciled` / `zcrypto-sync-hot-pullonly`), plus the interactive `zcrypto-deploy@ops` login key.
- `host_vars/nas/vars.yml`: `nas_liquidations_source` / `nas_panel_source` / `nas_reconciled_source` / `nas_hot_source` all = `"deploy@192.168.100.6:"`.
- `bootstrap.yml` ops play (`hosts: ops_host`, `ansible_user: root` via `-e`) creates `deploy` + sudoers + its authorized key.
- `~/.ssh/config` `Host hp` → `User deploy`, `IdentityFile ~/.ssh/zcrypto-deploy-ops_ed25519`. `host_vars/zcrypto-ops/vars.yml`: `ansible_user: deploy`.
- `kraken-capture` (uid 988) exists vestigially on ops (created by `base`, no consumer) — leave it; its retirement is not in scope (the fleet still uses it on capture hosts).

## File structure

- `infra/ansible/roles/ops/defaults/main.yml` — add `ops_data_user: zcrypto-data`, `ops_hot_group: zcrypto-hot`, `ops_research_user: zhaow`; add the four `ops_sync_*_authorized_key` file-lookup vars.
- `infra/ansible/roles/ops/tasks/main.yml` — create `zcrypto-data` + `zcrypto-hot` + memberships; switch the `ops_uid`/`ops_gid` derivation to `ops_data_user`; switch every data-dir owner to `ops_data_user`; hot-out → `ops_data_user:ops_hot_group 2775`; add four `authorized_key` tasks installing the sync forced commands on `zcrypto-data`.
- `infra/ansible/files/sync_{liquidations,panel,reconciled,hot}_ed25519.pub` — **create** (the four pull-channel public keys, retrieved from the NAS, committed so the role can install them).
- `infra/ansible/host_vars/nas/vars.yml` — the four `nas_*_source` repoint `deploy@ → zcrypto-data@`.
- `infra/ansible/bootstrap.yml` — the ops play provisions `zcrypto-deploy` (name + sudoers path + authorized_key) for virgin hosts.
- `infra/ansible/host_vars/zcrypto-ops/vars.yml` — `ansible_user: zcrypto-deploy`.
- `~/.ssh/config` (workstation-local, not repo-tracked) — `Host hp` → `User zcrypto-deploy`.
- `infra/ops/README.md`, `infra/nas/README.md` — the m2m user is `zcrypto-data`; the four channels are role-provisioned; the admin user is `zcrypto-deploy`.
- `docs/iterations-history-phase1.md`, `docs/open-topics/T0067-…` (closeout).

---

### Task 1: `zcrypto-data` m2m user + `zcrypto-hot` exchange group (ops role)

**Files:**
- Modify: `infra/ansible/roles/ops/defaults/main.yml`
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (add tasks in the unconditional preamble, after the `hot-out` dir task ~line 113)

**Interfaces:**
- Produces: the `zcrypto-data` system user + the `zcrypto-hot` group (both `zhaow` and `zcrypto-data` are members); the `ops_data_user`/`ops_hot_group`/`ops_research_user` default vars that Tasks 3 consume.

- [ ] **Step 1: Add the default vars.** In `roles/ops/defaults/main.yml`, after the `ops_hot_out_subdir: hot-out` line, add:

```yaml
# Fleet users/groups (spec 00057): the machine-to-machine data user. Runs the data containers
# (--user), owns the data trees, serves the NAS pulls via rrsync -ro forced-command keys. No sudo,
# no password; its shell is /bin/bash (nologin would block the forced commands) but the keys are
# command=+restrict-jailed so no interactive login is reachable -- deploy leaves the data path.
ops_data_user: zcrypto-data
# hot-out's two-role handoff group (setgid): zcrypto-data owns + serves; zhaow authors into it.
ops_hot_group: zcrypto-hot
# The interactive-research user (workstation-aligned; created by the research role, NOT this pipeline
# role). Added to ops_hot_group only when it already exists, so this role never creates it.
ops_research_user: zhaow
```

- [ ] **Step 2: Create the user + group + memberships.** In `roles/ops/tasks/main.yml`, immediately after the `ensure the ops hot-out outbox directory exists` task (~line 113), insert:

```yaml
# --- Fleet users/groups (spec 00057, ops phase): the zcrypto-data m2m identity + the hot-out
# authoring bridge. Created in the unconditional preamble (no digest gate) -- these accounts must
# exist before any data ownership or container-user change.
- name: create the zcrypto-data m2m user (no password; real shell jailed to rrsync by the forced-command keys; owns the data + runs the containers)
  ansible.builtin.user:
    name: "{{ ops_data_user }}"
    system: true
    shell: /bin/bash
    create_home: true
    state: present

- name: create the zcrypto-hot exchange group (bridges zcrypto-data + the research user zhaow)
  ansible.builtin.group:
    name: "{{ ops_hot_group }}"
    state: present

- name: add zcrypto-data to the exchange group (owns + serves hot-out; reads zhaow-authored files)
  ansible.builtin.user:
    name: "{{ ops_data_user }}"
    groups: "{{ ops_hot_group }}"
    append: true

- name: probe for the research user (created by the research role; optional to this pipeline role)
  ansible.builtin.command: "getent passwd {{ ops_research_user }}"
  register: ops_research_probe
  failed_when: false
  changed_when: false

- name: add the research user to the exchange group when it exists (authors into hot-out)
  ansible.builtin.user:
    name: "{{ ops_research_user }}"
    groups: "{{ ops_hot_group }}"
    append: true
  when: ops_research_probe.rc == 0
```

- [ ] **Step 3: Preview.** Run: `infra/ansible/scripts/run.sh site.yml --limit zcrypto-ops --tags ops --check --diff`
  Expected: the user/group/membership tasks show `changed`, everything else `ok`; `failed=0`. (The `zcrypto-data` user does not exist yet, so `--check` reports it would be created; the group-membership file tasks may error under `--check` only because the not-yet-created group can't be looked up — that is the known check-mode limitation, resolved by the real run's task order.)

- [ ] **Step 4: Apply.** Run: `infra/ansible/scripts/run.sh site.yml --limit zcrypto-ops --tags ops`
  Expected: `changed` for the user/group/membership tasks, `failed=0`. This is render-only for containers — no payload restart.

- [ ] **Step 5: Verify by outcome.**
  Run: `ssh hp 'id zcrypto-data; getent group zcrypto-hot; id -Gn zhaow | tr " " "\n" | grep -c zcrypto-hot'`
  Expected: `zcrypto-data` exists (`/bin/bash` shell — see the Task-4 correction note; its own gid); `zcrypto-hot` group lists `zcrypto-data` and `zhaow`; the `zhaow` grep prints `1`.

- [ ] **Step 6: Commit.**

```bash
git add infra/ansible/roles/ops/defaults/main.yml infra/ansible/roles/ops/tasks/main.yml
git commit -m "feat(infra): zcrypto-data m2m user + zcrypto-hot group on ops (spec 00057)"
```

---

### Task 2: Ansible-provision the four sync pull keys on `zcrypto-data` (dual with deploy)

**Files:**
- Create: `infra/ansible/files/sync_liquidations_ed25519.pub`, `sync_panel_ed25519.pub`, `sync_reconciled_ed25519.pub`, `sync_hot_ed25519.pub`
- Modify: `infra/ansible/roles/ops/defaults/main.yml` (four `ops_sync_*_authorized_key` lookup vars)
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (four `authorized_key` tasks)
- Modify: `infra/ansible/files/README.md` (inventory the four pub keys)

**Interfaces:**
- Consumes: `ops_data_user` (Task 1), the `zcrypto-hot` group (Task 1).
- Produces: the four `rrsync -ro` forced-command entries in `~zcrypto-data/.ssh/authorized_keys`, matching the roots the NAS pulls. These are ADDED without removing deploy's copies (dual authorization for the Task-4 cutover).

- [ ] **Step 1: Retrieve the four public keys from the NAS and commit them.** The private halves live on the NAS at `/volume1/docker/zcrypto-archive/keys/sync_*`; the `.pub` siblings are there too. Copy each `.pub` into `infra/ansible/files/`:

```bash
for k in liquidations panel reconciled hot; do
  ssh nas "cat /volume1/docker/zcrypto-archive/keys/sync_${k}.pub" > "infra/ansible/files/sync_${k}_ed25519.pub"
done
# sanity: each is a single ed25519 public line
for k in liquidations panel reconciled hot; do
  head -c 11 "infra/ansible/files/sync_${k}_ed25519.pub"; echo "  <- sync_${k}"
done
```
Expected: each prints `ssh-ed25519  <- sync_<name>`. (Public keys are not secret — safe to read and commit.)

- [ ] **Step 2: Add the lookup vars.** In `roles/ops/defaults/main.yml`, after the `ops_research_user` line, add:

```yaml
# Fleet users/groups (spec 00057): the four NAS pull-channel public keys, installed on zcrypto-data
# as rrsync -ro forced commands. Public material only; the private halves live on the NAS (/keys).
ops_sync_liquidations_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/sync_liquidations_ed25519.pub') }}"
ops_sync_panel_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/sync_panel_ed25519.pub') }}"
ops_sync_reconciled_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/sync_reconciled_ed25519.pub') }}"
ops_sync_hot_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/sync_hot_ed25519.pub') }}"
```

- [ ] **Step 3: Add the four authorized_key tasks.** In `roles/ops/tasks/main.yml`, after the membership tasks from Task 1, insert (each pins the exact subtree the NAS pulls; `-ro` = read-only, `restrict` = the fleet's SSH-level idiom):

```yaml
# --- The four NAS pull channels, now role-provisioned on zcrypto-data (spec 00057; they were
# hand-installed on deploy). rrsync -ro pins each to its own subtree -- least-privilege per channel.
- name: install the liquidations pull key (rrsync -ro) on zcrypto-data
  ansible.posix.authorized_key:
    user: "{{ ops_data_user }}"
    exclusive: false
    key: "{{ ops_sync_liquidations_authorized_key }}"
    key_options: 'command="/usr/bin/rrsync -ro {{ ops_data_dir }}/{{ ops_liquidations_subdir | default(''liquidations'') }}",restrict'

- name: install the panel pull key (rrsync -ro) on zcrypto-data
  ansible.posix.authorized_key:
    user: "{{ ops_data_user }}"
    exclusive: false
    key: "{{ ops_sync_panel_authorized_key }}"
    key_options: 'command="/usr/bin/rrsync -ro {{ ops_data_dir }}/{{ ops_panel_subdir }}",restrict'

- name: install the reconciled pull key (rrsync -ro) on zcrypto-data
  ansible.posix.authorized_key:
    user: "{{ ops_data_user }}"
    exclusive: false
    key: "{{ ops_sync_reconciled_authorized_key }}"
    key_options: 'command="/usr/bin/rrsync -ro {{ ops_data_dir }}/{{ ops_reconciled_subdir }}",restrict'

- name: install the hot-out pull key (rrsync -ro) on zcrypto-data
  ansible.posix.authorized_key:
    user: "{{ ops_data_user }}"
    exclusive: false
    key: "{{ ops_sync_hot_authorized_key }}"
    key_options: 'command="/usr/bin/rrsync -ro {{ ops_data_dir }}/{{ ops_hot_out_subdir }}",restrict'
```
Note: `ops_liquidations_subdir` has no default in the role today — add `ops_liquidations_subdir: liquidations` to `defaults/main.yml` beside `ops_panel_subdir` rather than relying on the inline `default('liquidations')`, then reference `{{ ops_liquidations_subdir }}` (keeps the four tasks uniform).

- [ ] **Step 4: Inventory the keys.** Append four rows to `infra/ansible/files/README.md`'s key table, form:
  `| \`sync_liquidations_ed25519.pub\` | NAS (\`/volume1/docker/zcrypto-archive/keys/\`) | ops liquidations pull channel, installed on \`zcrypto-data\` by the ops role |` (and the same for panel/reconciled/hot).

- [ ] **Step 5: Preview + apply + verify.**
  Run: `infra/ansible/scripts/run.sh site.yml --limit zcrypto-ops --tags ops --check --diff` (expect the four authorized_key tasks `changed`, `failed=0`), then without `--check`.
  Verify: `ssh hp 'sudo grep -c "rrsync -ro" ~zcrypto-data/.ssh/authorized_keys'` → **4**. Deploy's keys are untouched (still 5 lines) — dual authorization is now in place.

- [ ] **Step 6: Commit.**

```bash
git add infra/ansible/files/ infra/ansible/roles/ops/defaults/main.yml infra/ansible/roles/ops/tasks/main.yml
git commit -m "feat(infra): the four ops pull keys become Ansible-provisioned on zcrypto-data (spec 00057)"
```

---

### Task 3 (ATTENDED, orchestrator-only): data ownership + container run-as → `zcrypto-data`

**Files:**
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (the `ops_uid`/`ops_gid` derivation; every data-dir owner; the hot-out dir)

**Interfaces:**
- Consumes: `zcrypto-data` (Task 1), `ops_data_user`/`ops_hot_group`.
- Produces: the ops containers run as `zcrypto-data`; all four data trees are `zcrypto-data`-owned; `hot-out` is `zcrypto-data:zcrypto-hot 2775` (setgid).

**Why attended + why this ordering is safe:** the liquidations poller runs continuously as the derived uid; switching the derivation `deploy → zcrypto-data` + chowning its tree means a brief stop→chown→restart. Liquidations missed during the stop are re-fetched by the poller's ~30 h Coinalyze catch-up on restart (OPS-2 design) — **recoverable, not lost.** The reconciler/panel timers are periodic, so their chown lands between fires with no gap. The NAS still pulls as `deploy@` until Task 4, so there is a brief pull *delay* (not loss) between this task and Task 4 — do them in the same window.

- [ ] **Step 1: Switch the container-user derivation.** In `roles/ops/tasks/main.yml`, change the two tasks at ~lines 153-161 from `deploy` to `{{ ops_data_user }}`:

```yaml
- name: look up the zcrypto-data account (the ops containers run as its uid/gid)
  ansible.builtin.getent:
    database: passwd
    key: "{{ ops_data_user }}"

- name: derive the zcrypto-data uid/gid for the container user mapping
  ansible.builtin.set_fact:
    ops_uid: "{{ ansible_facts['getent_passwd'][ops_data_user][1] }}"
    ops_gid: "{{ ansible_facts['getent_passwd'][ops_data_user][2] }}"
```

- [ ] **Step 2: Switch the data-dir owners.** In the same file, change `owner: deploy` / `group: deploy` → `owner: "{{ ops_data_user }}"` / `group: "{{ ops_data_user }}"` on: `ops_data_dir`, `ops_compose_dir`, `ops_textfile_dir`, and the `capture-reconciled` ownership-fix task (the recurse:true one ~line 183). For the **hot-out** dir task, set `owner: "{{ ops_data_user }}"`, `group: "{{ ops_hot_group }}"`, `mode: "2775"` (setgid — zhaow authors, zcrypto-data serves).

- [ ] **Step 3: Preview.** Run: `infra/ansible/scripts/run.sh site.yml --limit zcrypto-ops --tags ops -e ops_image_digest=<current-pin> --check --diff`
  (Retrieve `<current-pin>` from the running poller: `ssh hp 'sudo docker inspect zcrypto-ops-liquidations-1 --format "{{.Image}}"'` — pass that digest so the poller-compose + timers re-render.)
  Expected: the derivation now resolves `zcrypto-data`; the data-dir owner tasks show `changed` (deploy→zcrypto-data); the poller compose + timers re-render with the new `--user`. `failed=0`.

- [ ] **Step 4: Apply — the coordinated switch (attended).**
  1. Stop the poller: `ssh hp 'docker compose -f /etc/zcrypto-ops/compose.yaml down'` (note the time — the catch-up window starts here).
  2. Converge with the digest (chowns the trees, re-renders the compose + timers as `zcrypto-data`): `infra/ansible/scripts/run.sh site.yml --limit zcrypto-ops --tags ops -e ops_image_digest=<current-pin>`.
  3. Start the poller: `ssh hp 'docker compose -f /etc/zcrypto-ops/compose.yaml up -d'`.
  Keep the stop→start window to minutes.

- [ ] **Step 5: Verify by outcome.**
  - `ssh hp 'sudo docker inspect zcrypto-ops-liquidations-1 --format "{{.Config.User}}"'` → the `zcrypto-data` uid:gid (not `1001:1001`).
  - `ssh hp 'ls -ld /var/lib/zcrypto-ops/{liquidations,l2-panel,capture-reconciled,hot-out}'` → all owned `zcrypto-data`; `hot-out` is `drwxrwsr-x zcrypto-data zcrypto-hot` (setgid).
  - `ssh hp 'sudo docker logs --since 5m zcrypto-ops-liquidations-1 2>&1 | grep -iE "back|catch|poll cycle"'` → the catch-up back-fill ran and hourly finals are appearing again. No `EACCES`/permission errors.

- [ ] **Step 6: Commit.**

```bash
git add infra/ansible/roles/ops/tasks/main.yml
git commit -m "feat(infra): ops containers + data owned by zcrypto-data, not deploy (spec 00057)"
```

---

### Task 4 (ATTENDED, orchestrator-only): repoint the NAS pulls to `zcrypto-data@` + drop deploy's keys

**Files:**
- Modify: `infra/ansible/host_vars/nas/vars.yml` (the four `nas_*_source`)
- Modify: `infra/nas/README.md` (the sources are `zcrypto-data@`)

**Interfaces:**
- Consumes: the `zcrypto-data` forced-command keys (Task 2), the `zcrypto-data`-owned data (Task 3).
- Produces: the NAS pulls all four channels as `zcrypto-data@192.168.100.6`; `deploy` is out of the data path.

- [ ] **Step 1: Repoint the sources.** In `host_vars/nas/vars.yml`, change the four `nas_{liquidations,panel,reconciled,hot}_source` from `"deploy@192.168.100.6:"` to `"zcrypto-data@192.168.100.6:"`.

- [ ] **Step 2: Preview.** Run: `infra/ansible/scripts/run.sh site.yml --limit nas --tags nas --check --diff`
  Expected: the rendered `.env` changes the four `*_SOURCE` lines to `zcrypto-data@`; `failed=0`. (The NAS `known_hosts` already pins `192.168.100.6` — no re-pin; the user changes, not the host.)

- [ ] **Step 3: Apply + restart the puller (attended).** Run: `infra/ansible/scripts/run.sh site.yml --limit nas --tags nas -e nas_apply_compose=true` (re-renders `.env` + restarts `archive-pull` so it re-reads the sources; T0048 restarts alloy too).

- [ ] **Step 4: Verify by outcome — every channel still pulling.**
  `ssh nas 'sudo /usr/local/bin/docker logs --since 5m zcrypto-archive-archive-pull-1 2>&1 | grep -iE "liquidations|panel|reconciled|hot|ERROR"'`
  Expected: each of the four channels logs a successful pull (or a clean skip if its `*_SOURCE` were unset — they are set); **no ERROR / permission-denied / host-key failure**. Confirm the liquidations tree on the NAS advanced (a fresh hour appeared) — the unbackfillable-ish channel is confirmed flowing as `zcrypto-data@`.

- [ ] **Step 5: Drop the four forced-command keys from deploy (cleanup, attended).** Now that the NAS connects as `zcrypto-data`, remove the four `rrsync -ro` lines from `~deploy/.ssh/authorized_keys`, leaving only the interactive login key:

```bash
ssh hp 'cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak-pre-uidmigration && \
        grep -v "rrsync -ro" ~/.ssh/authorized_keys > /tmp/ak && mv /tmp/ak ~/.ssh/authorized_keys && \
        echo "deploy authorized_keys lines: $(grep -c . ~/.ssh/authorized_keys)"'
```
Expected: `deploy authorized_keys lines: 1` (only the interactive login remains). Re-verify the NAS pull still flows after (it connects as `zcrypto-data`, unaffected).

- [ ] **Step 6: Commit.**

```bash
git add infra/ansible/host_vars/nas/vars.yml infra/nas/README.md
git commit -m "feat(infra): NAS pulls ops data as zcrypto-data, deploy out of the data path (spec 00057)"
```

---

### Task 5: verify the hot-out authoring handoff (zhaow → hot-out → NAS)

**Files:** none (verification of the Task-1/3 wiring — the OPS-6 authoring direction OPS-6 deferred).

**Interfaces:**
- Consumes: `hot-out` = `zcrypto-data:zcrypto-hot 2775` (Task 3), `zhaow` ∈ `zcrypto-hot` (Task 1), the `sync_hot` pull (Task 4).

- [ ] **Step 1: zhaow authors a test set into hot-out.**
  `ssh zhaow@192.168.100.6 'mkdir -p /var/lib/zcrypto-ops/hot-out/authortest && echo v1 > /var/lib/zcrypto-ops/hot-out/authortest/x.txt && ls -l /var/lib/zcrypto-ops/hot-out/authortest'`
  Expected: the write succeeds (group-write via `zcrypto-hot` + setgid); the file's group is `zcrypto-hot`.

- [ ] **Step 2: zcrypto-data can read it (the NAS pull runs as zcrypto-data).**
  `ssh hp 'sudo -u zcrypto-data cat /var/lib/zcrypto-ops/hot-out/authortest/x.txt'` → `v1`.

- [ ] **Step 3: the NAS pulls it into hot/.** Wait one archive-pull cycle (≤ 1 h, or force a cycle), then `ssh nas 'cat /volume1/ZhaoCrypto/hot/authortest/x.txt'` → `v1`.

- [ ] **Step 4: Clean up the test set** (the one sanctioned deletion — it never entered a registry): remove `authortest` on the ops side (`sudo rm -rf`) and NAS-side. Verify gone.

- [ ] **Step 5: No commit** (verification only; note the result in the closeout).

---

### Task 6 (ATTENDED, orchestrator-only): rename `deploy → zcrypto-deploy`

**Files:**
- Modify: `infra/ansible/bootstrap.yml` (ops play: provision `zcrypto-deploy` for virgin hosts)
- Modify: `infra/ansible/host_vars/zcrypto-ops/vars.yml` (`ansible_user: zcrypto-deploy`)
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (retarget the 5 admin-plane `owner: deploy`/`group: deploy` refs → `zcrypto-deploy`: compose project dir, compose-file render, and the 3 Alloy config items — Task-3 review finding; they'd fail user-lookup on the first post-rename converge otherwise)
- Modify: `~/.ssh/config` (workstation-local: `Host hp` → `User zcrypto-deploy`)
- Modify: `infra/ops/README.md` (the admin user is `zcrypto-deploy`)

**Interfaces:**
- Consumes: nothing from the data path — `deploy` has no running processes now (the containers moved to `zcrypto-data` in Task 3), so `usermod -l` will not be blocked.

**Why last + why safe:** the rename changes the account Ansible/ssh connect *as* to ops. It is done from the **root break-glass** connection (never as `deploy` itself), and only after the containers left `deploy` (Task 3) so `usermod` has no live `deploy` processes. The root break-glass stays available throughout as the safety net.

- [ ] **Step 1: Update `bootstrap.yml`'s ops play** to provision `zcrypto-deploy` (for future virgin hosts): `name: zcrypto-deploy` in the user task, `dest: /etc/sudoers.d/zcrypto-deploy` with content `zcrypto-deploy ALL=(ALL) NOPASSWD:ALL`, and `user: zcrypto-deploy` in the authorized_key task; add `exclusive: true` to that authorized_key task (spec D1 — one key, no drift). Do NOT run it against the live box yet.

- [ ] **Step 2: One-time attended rename on the existing box (as root break-glass).** Confirm no `deploy` processes first, then rename in place (keeps uid 1001, keeps the login key by moving the home):

```bash
ssh root@192.168.100.6 'pgrep -u deploy -a || echo "no deploy processes"; \
  usermod -l zcrypto-deploy deploy && groupmod -n zcrypto-deploy deploy && \
  usermod -d /home/zcrypto-deploy -m zcrypto-deploy && \
  sed "s/^deploy /zcrypto-deploy /" /etc/sudoers.d/deploy > /etc/sudoers.d/zcrypto-deploy && \
  visudo -cf /etc/sudoers.d/zcrypto-deploy && rm /etc/sudoers.d/deploy && \
  id zcrypto-deploy && ls -ld /home/zcrypto-deploy'
```
(If `pgrep -u deploy` shows anything, stop and resolve it before renaming — Task 3 should have left none.)

- [ ] **Step 3: Update the repo's admin-user references to `zcrypto-deploy`.** In `~/.ssh/config`, `Host hp` → `User zcrypto-deploy`. In `host_vars/zcrypto-ops/vars.yml`, `ansible_user: zcrypto-deploy`. In `roles/ops/tasks/main.yml`, retarget the 5 admin-plane `owner: deploy`/`group: deploy` refs → `zcrypto-deploy` (the compose project dir, the compose-file render, and the Alloy project dir / `config.alloy` / alloy compose file) — the only `deploy` owners Task 3 deliberately left admin-plane; after `usermod -l` (Step 2) they'd fail user-lookup on the next converge (Task-3 review finding).

- [ ] **Step 4: Verify by outcome — the box is converge-able as zcrypto-deploy.**
  - `ssh hp 'whoami; sudo -n true && echo "passwordless sudo OK"'` → `zcrypto-deploy` + sudo OK (the ssh alias now lands as `zcrypto-deploy`, the key + sudoers moved with the home).
  - `infra/ansible/scripts/run.sh site.yml --limit zcrypto-ops --tags ops --check --diff` → connects as `zcrypto-deploy`, `failed=0`, no unexpected changes (idempotent — the migration is complete).

- [ ] **Step 5: Commit.**

```bash
git add infra/ansible/bootstrap.yml infra/ansible/host_vars/zcrypto-ops/vars.yml infra/ansible/roles/ops/tasks/main.yml infra/ops/README.md
git commit -m "feat(infra): rename ops admin deploy -> zcrypto-deploy (spec 00057 D1)"
```

Note: `~/.ssh/config` is workstation-local (not repo-tracked) — its edit ships with no commit; record it in the closeout.

---

### Task 7: Closeout

- [ ] **Step 1:** [[T0067]] — flip to `resolved` (the ops phase is complete) and `git mv` to `docs/open-topics/archive/`; sync the index (move the bullet to the category's Resolved subsection, link → `archive/`). Verify no live deferred sub-item remains under it — the capture/engine phase is the separate [[T0068]], not a T0067 residual.
- [ ] **Step 2:** Append the closeout entry to `docs/iterations-history-phase1.md` (`## <YYYY-MM-DD> — iter-<NNN>: fleet users/groups (ops phase) — deploy leaves the data path (spec 00057)`), one bullet per change: `zcrypto-data` m2m identity; the four pulls Ansible-provisioned + repointed with the recoverable-poller-catch-up ordering; the hot-out authoring handoff (the OPS-6-deferred direction, now live); the `deploy → zcrypto-deploy` rename; and the measured before/after (poller catch-up window, each channel confirmed pulling as `zcrypto-data`).
- [ ] **Step 3:** README updates — `infra/ops/README.md` (the m2m user is `zcrypto-data`; the four channels are role-provisioned; admin is `zcrypto-deploy`) and `infra/nas/README.md` (the ops sources are `zcrypto-data@`). No `zcrypto data` CLI surface changed, so no README `## Usage` change.
- [ ] **Step 4:** Final whole-branch review (most capable model), `Reviewed-by:` trailers, push once, PR into `develop`: `feat(infra): iter-<NNN> — fleet users/groups: ops phase (spec 00057)`. `## Follow-ups` references only registered topics ([[T0068]] — the capture/engine phase).

## Self-review

- **Spec coverage:** D1 (`deploy → zcrypto-deploy`, per-phase, one key) → Task 6 + Step 1 `exclusive: true`. D2 (`zcrypto-data` m2m: containers + data + pulls) → Tasks 1/2/3/4. D3/D4 (engine) → N/A on ops. D6 (NAS reuse) → done manually, out of scope. D7 (`zhaow` unchanged) → the ops-role guard never creates/alters it beyond a group append. D8 (`zcrypto-data` uid auto) → `system: true`, no uid pin. The "everything Ansible-provisioned" constraint → Task 2 (the four hand-installed keys become role-managed). The phased-execution split → this is the ops plan; the capture/engine plan is [[T0068]].
- **No placeholders:** every task has exact files, exact Ansible/shell, and a verify-by-outcome. `<current-pin>` is resolved by the given `docker inspect` command; `<NNN>`/`<YYYY-MM-DD>` are the closeout's own iteration/date.
- **Type consistency:** `ops_data_user`/`ops_hot_group`/`ops_research_user` are defined in Task 1 and consumed unchanged in Tasks 2/3; the four `ops_sync_*_authorized_key` vars are defined in Task 2 and consumed in the same task; `ops_uid`/`ops_gid` keep their names, only their source account changes.
- **Live-channel safety:** the ordering (dual keys → data+container switch → NAS repoint → drop deploy keys) never loses data — the poller catch-up covers its brief stop, `--ignore-existing` covers the brief pull delay, and the `deploy` rename runs only after the containers left the account. The root break-glass is the rename's safety net.
