# Fleet users/groups regularization — capture/engine phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Tasks 5, 7, 8 are ATTENDED, orchestrator-only** — they mutate the LIVE, UNBACKFILLABLE capture hosts (`zcrypto`/`zcrypto-red`) and the trade-key host; never subagent work. Tasks 1–4 are code-only (subagent-able); they are **committed but NOT applied to any host** until the attended windows.

**Goal:** Migrate the capture/engine hosts (`zcrypto` primary, `zcrypto-red` secondary) onto the fleet users/groups model (spec `00057`, phase 2): rename `kraken-capture → zcrypto-data` (uid 999 kept) and `kraken-engine → zcrypto-engine` (uid 997 kept), move the capture/journal pull-export forced-command keys off `deploy` onto `zcrypto-data` + Ansible-provision them, rename `deploy → zcrypto-deploy`, and stand up `zcrypto-alloy` on the capture hosts for the first time — with **zero capture gap**, secondary-first canary discipline.

**Architecture:** All identity moves are **in-place `usermod -l`/`groupmod -n` renames that preserve the uid/gid** (no account is recreated — a bare Ansible name-change would allocate a fresh uid and orphan the uid-999/997-owned data). Because the capture container's `--user` is numeric-but-name-derived (getent), keeping uid 999/997 leaves the on-disk data and container mapping valid; the rename is metadata + a compose re-render + a restart, done in the host's maintenance window (resubscribe-with-replay, not a data gap). `zcrypto-data` becomes the m2m identity (runs the capture container, owns the capture data, serves the NAS pulls via the `rrsync-shell` wrapper + `command=`/`restrict` forced-command keys — Debian, so the wrapper works, unlike the NAS). `zcrypto-engine` keeps its own confined nologin account (defense-in-depth; the trade key stays isolated at the compose/root layer, D4 — behavior-preserving). `zcrypto-alloy` lands under the uniform telemetry pattern, accepting the D5 residual (T0042). `deploy → zcrypto-deploy` leaves the admin account interactive-only (one key, `exclusive: true`).

**Tech Stack:** Ansible (`ansible.builtin.user`/`group`/`file`, `ansible.posix.authorized_key`, `getent`), the `base`/`capture`/`engine`/`docker`/`hardening` roles + `bootstrap.yml` + `site.yml`, rootful Docker with numeric `--user`, rsync-over-ssh with `rrsync` forced commands + the `files/rrsync-shell` wrapper, Grafana Alloy (docker.sock telemetry), `infra/ansible/scripts/run.sh` (vaulted deploy-key throwaway agent), one-time attended `usermod`/`groupmod` over the root break-glass / `zcrypto-deploy` connection.

## Global Constraints

- **Canary discipline (`fleet-deploys.md`).** Migrate `zcrypto-red` (secondary) fully, **bake it**, and only then touch `zcrypto` (primary). The primary converge restarts live capture **and** the engine — it **refuses without `-e converge_primary=true`** (`site.yml:29-41` assert, `tags:[always]`, keyed on `engine_host` membership) and needs `-e capture_image_digest=sha256:<...>` (+ `-e engine_image_digest=sha256:<...>` for the engine play; both have no default and are role-asserted). Secondary converges with just `--limit zcrypto-red -e capture_image_digest=<...>`.
- **Maintenance windows:** secondary `zcrypto-red` **22:25 UTC**, primary `zcrypto` **21:25 UTC** (`host_vars/<host>/vars.yml` reboot slots — measured troughs). Do each host's whole cutover inside its window.
- **uid/gid preservation is mandatory and is NOT expressible by the Ansible `user:` module** (no `uid:` is pinned anywhere today; `system: true` auto-allocated 999/997). Every rename is a one-time attended `usermod -l <new> <old>` + `groupmod -n <new> <old>` on the host, done **before** the converge that references the new name. A bare `base_capture_user: zcrypto-data` change WITHOUT the prior `usermod` would create a new uid and orphan `/var/lib/zcrypto-capture`.
- **L2 capture is unbackfillable.** A container *restart* (resubscribe-with-replay; `dropping late event` lines are healthy) is fine; a *gap* is permanent loss. Verify after every primary/secondary converge by outcome: each book stream's `<HH>.parquet` begins at `:00:00.0x`, manifests verify, `infra/scripts/continuity.py` (on a pulled copy) shows no new truncated hours.
- **The trade key stays isolated at the compose/root layer (D4).** `engine.env` is `0600 root:root` at `/opt/zcrypto-engine`, delivered via compose `env_file` — unreadable by `zcrypto-engine` (the renamed run-as user) before or after. **Never** introduce a trade-key var into `capture_host` (depth-2 child of `observed`) — it would override `engine_host` and leak to `zcrypto-red`. **Never** run `ansible-inventory --host`/`--list` (ansible.cfg auto-decrypts the vault → cleartext trade key).
- **`zcrypto-data` serves pulls → it needs a login-capable shell.** Its shell becomes `/usr/local/sbin/rrsync-shell` (the wrapper — Debian, works; `nologin` swallows the forced command → `account not available`). `zcrypto-engine` stays `nologin` (it only runs the engine container; it serves no pull). The `command=`/`restrict` keys keep every key jailed to one read-only subtree — no interactive login is reachable despite the real shell.
- **`zcrypto-data`'s uid is per-host and that is fine (D8):** 999 on the capture hosts (inherited from `kraken-capture`), 1000 on the NAS, a system uid on ops. The name is shared fleet-wide; the container `--user` is always getent-derived, so nothing hardcodes it. **Do not "harmonize" the uid.**
- **Dual-key / delayed-repoint transition (never a pull gap):** the export key is **added** to `zcrypto-data` while `deploy`'s copy stays (`exclusive: false`); the NAS repoints `deploy@ → zcrypto-data@` and is verified pulling; only then is `deploy` renamed and its residual export key dropped. Every rsync pull is `--archive --ignore-existing` (a delayed pull catches up, never loses).
- **sshd `AllowUsers` gates the pull BEFORE the forced command — the capture-host-specific trap the ops phase never hit.** The capture hosts run the `hardening` role (the ops play does NOT — that is why ops never touched this); it sets sshd `AllowUsers` from `hardening_ssh_allow_users` (default `deploy root`, `roles/hardening/defaults/main.yml:2`, applied `roles/hardening/tasks/main.yml:36`). `root` is the key-only **break-glass** every attended `usermod` step depends on — **never drop it.** Splitting admin (`zcrypto-deploy`) from the m2m pull (`zcrypto-data`) means the pull user **must be in `AllowUsers`** or the NAS's `zcrypto-data@` pull is denied at session setup (mirror stalls → loss once prune deletes local finals). Use a transitional superset `hardening_ssh_allow_users: zcrypto-data zcrypto-deploy deploy root` (add the pull user, pre-list the renamed admin, KEEP `deploy` until it's renamed, KEEP `root`); a listed-but-absent user is a harmless no-op, so this one shared value is valid for both hosts in every rename state. Drop the stale `deploy` opportunistically at a later scheduled converge (not a dedicated window — it's cosmetic once `bootstrap.yml` only creates `zcrypto-deploy`).
- **The `deploy → zcrypto-deploy` identity flip is per-host and deferred to each host's post-rename step — never front-loaded** (the ops-phase lesson). `ansible_user` + `docker_deploy_user` stay `deploy` through the pre-rename converge; the flip to `zcrypto-deploy` is a **per-host `host_vars/<host>/vars.yml` override** applied only *after* that host's `usermod -l deploy zcrypto-deploy`. Front-loading them in shared `group_vars`/role defaults breaks the pre-rename converge (ansible connects as a nonexistent `zcrypto-deploy`; the `docker` role's `user:` task — no `state:` → `present` — stub-creates it, so the later `usermod -l` collides "already exists") and, once `hardening` runs, locks the live `deploy` out (only `root` break-glass survives). Only `bootstrap.yml` (virgin-host provisioning) carries the `zcrypto-deploy` name up-front. Between the secondary's rename (Task 5) and the primary's (Task 7) the two hosts are in different states — per-host `host_vars` is what keeps the shared `capture_host` group converge-able for both.
- **Everything on captures is Ansible-provisioned** (owner constraint) — the export keys stop being on `deploy` and become role-managed on `zcrypto-data`. **Preview every converge with `--check --diff`** (subject to the getent check-mode limitation below); run via `infra/ansible/scripts/run.sh`.
- **Branch:** all commits land on **`feat/fleet-users-groups`** — **no new PR** (folds into the existing branch / PR #148). Closeout docs are authored at closeout, not during planning.
- The plan is driven by **spec `00057`**; open topic **`T0068`** is the tracking pointer, not the source of truth.

## Current state (measured 2026-07-19, this is what you migrate FROM)

- **Users, no uid pinned in code:** `kraken-capture` uid **999** (created by `base` role, `roles/base/tasks/main.yml:81-96`, `base_capture_user: kraken-capture`, `shell: /usr/sbin/nologin`, home `/var/lib/zcrypto-capture`); `kraken-engine` uid **997** (created by `engine` role itself, `roles/engine/tasks/main.yml:125-132`, nologin, home `/var/lib/zcrypto-engine`); `deploy` (sudo, `bootstrap.yml:24-33`, `group_vars/capture_host/vars.yml: ansible_user: deploy`).
- **Capture container run-as:** numeric `user: {{ capture_uid }}:{{ capture_gid }}` (`roles/capture/templates/compose.yaml.j2:9`), derived by `getent kraken-capture` (`roles/capture/tasks/main.yml:5-13`). The capture data dir `/var/lib/zcrypto-capture` is created **twice**: `base` (var `base_capture_user`) and `capture` role with a **LITERAL** `owner: kraken-capture`/`group: kraken-capture` (`roles/capture/tasks/main.yml:23-29`).
- **Engine:** run-as `{{ engine_uid }}:{{ engine_gid }}` (`getent kraken-engine`). State dirs `/var/lib/zcrypto-engine/{,store,journal}` owned `kraken-engine:kraken-engine 0750` (`roles/engine/tasks/main.yml:155-165`). Trade key: `engine.env` `0600 root:root` at `/opt/zcrypto-engine` via compose `env_file` (`roles/engine/tasks/main.yml:213-230`, `group_vars/engine_host/vault.yml`, `engine_host = {zcrypto}`). Compose project dir + `zcrypto-engine.service` are **already** named `zcrypto-engine` — only the service *account* is `kraken-engine`.
- **Export forced-command keys, on `deploy` today (Ansible-managed):** capture — `roles/capture/tasks/main.yml:75-80`, `user: deploy`, `command="/usr/bin/rrsync -ro /var/lib/zcrypto-capture",restrict`, key `sync_capture_authorized_key` (primary `files/sync_capture_ed25519.pub`; secondary override `files/sync_capture_red_ed25519.pub`, `host_vars/zcrypto-red/vars.yml:27`); + `deploy` added to `kraken-capture` group for traversal (`:82-93`). Journal — `roles/engine/tasks/main.yml:293-298`, `user: deploy`, `command="/usr/bin/rrsync -ro /var/lib/zcrypto-engine/journal",restrict`, key `sync_authorized_key` (`files/sync_ed25519.pub`); + `deploy` added to `kraken-engine` group (`:300-310`). All three pubkeys are already committed in `files/`.
- **NAS pulls (the consumer):** `host_vars/nas/vars.yml`: `nas_capture_source: "deploy@zcrypto.zhaow.me:"` (`:93`), `nas_journal_source: "deploy@zcrypto.zhaow.me:"` (`:95`), `nas_capture_red_source: "deploy@zcrypto-red.zhaow.me:"` (`:96`), port `nas_archive_ssh_port: 10022` (`:94`). Rendered into the NAS `.env` as `CAPTURE_SOURCE`/`JOURNAL_SOURCE`/`CAPTURE_RED_SOURCE`/`ARCHIVE_SSH_PORT` (`roles/nas/templates/env.j2:9-12`). (The home-LAN ops channels already use `zcrypto-data@`; these three VPS channels are the only ones still on `deploy`.) `env.j2` has **no** per-channel port var for journal/capture-red — do not invent one; verify `infra/nas/pull-entrypoint.sh` for how capture-red's port resolves before touching ports.
- **Alloy:** capture hosts run **none** today (the capture play has no `alloy` role; capture/engine compose mount no `docker.sock`). `zcrypto`/`zcrypto-red` are **already** in the `observed` group (`inventory/hosts.yml:11-15`) so `group_vars/observed/vault.yml`'s six `GRAFANA_*` creds resolve — but membership deploys nothing (`observed` is a claim-only container group). The `docker` role runs in the capture play, so the `docker` group exists.
- **sshd `AllowUsers` (capture hosts only):** the `hardening` role sets `AllowUsers` from `hardening_ssh_allow_users: deploy root` (`roles/hardening/defaults/main.yml:2`, applied `roles/hardening/tasks/main.yml:36`) — enforced at session setup **before** `authorized_keys`/the forced command. `root` is the intended key-only break-glass. The engine role's §8 gate asserts `allowusers …\bdeploy\b` (`roles/engine/tasks/main.yml:114`) as a guard on it (it matches a single name — it will NOT catch a missing `zcrypto-data`). The `deploy_*` pubkey file comments already read `zcrypto-deploy@…`; only the OS account name + var references change. `roles/docker/defaults/main.yml:1 docker_deploy_user: deploy` (its `user:` task has no `state:` → defaults to `present`, so a var-flip on an absent account *creates* it). The ops node runs no `hardening` role, so the ops phase never touched `AllowUsers`.

## File structure

- `roles/base/defaults/main.yml` + `roles/base/tasks/main.yml` — `base_capture_user: kraken-capture → zcrypto-data`; the capture-user task's `shell` → `{{ base_capture_shell }}` (new default `/usr/local/sbin/rrsync-shell`).
- `roles/capture/tasks/main.yml` — getent key + `set_fact` keys + the **literal** data-dir owner/group → `zcrypto-data`; **deploy the wrapper** (copy `files/rrsync-shell`); the export `authorized_key` `user: deploy → zcrypto-data`; drop the `deploy`-in-`kraken-capture`-group task.
- `roles/engine/tasks/main.yml` — every `kraken-engine` literal → `zcrypto-engine` (user task, getent, `set_fact` keys, state-dir owner/group, store-copy owner/group); the journal export `authorized_key` `user: deploy → zcrypto-data` + add `zcrypto-data` to the `zcrypto-engine` group + a **journal group-read** grant; the §8 `allowusers` assert `deploy → zcrypto-deploy`.
- `roles/hardening/defaults/main.yml` — `hardening_ssh_allow_users: deploy root → zcrypto-data zcrypto-deploy deploy root` (transitional superset — add the pull user, pre-list the renamed admin, KEEP `deploy` + `root`); the engine §8 assert (`roles/engine/tasks/main.yml:114`) updated to tolerate the superset.
- `bootstrap.yml` (capture play) — provision `zcrypto-deploy` for **virgin hosts only** (name, `sudoers.d/zcrypto-deploy`, authorized_key `user:` + `exclusive: true`), mirroring the ops play (`bootstrap.yml:64-73`). It does not rename the live account — the running hosts are renamed by `usermod` in Tasks 5/7.
- `host_vars/zcrypto-red/vars.yml` + `host_vars/zcrypto/vars.yml` — **per-host, added at each cutover (Task 5/7 Step 6, post-`usermod`):** `ansible_user: zcrypto-deploy` + `docker_deploy_user: zcrypto-deploy`. NOT in the shared `group_vars`/role defaults — those stay `deploy` so the pre-rename converge connects, and the two hosts can differ mid-migration.
- **New Alloy** — `roles/capture/tasks/main.yml` (an `alloy_digest`-gated block lifted from `roles/ops/tasks/main.yml:332-471`), `roles/capture/templates/alloy-compose.yaml.j2` + `alloy-secrets.env.j2` (lift from ops), `roles/capture/files/config.alloy` (**authored fresh** — host label `zcrypto`/`zcrypto-red`, capture-relevant series; `copy:` not `template:`), capture defaults for `capture_alloy_dir`/`capture_alloy_image`/`capture_rrsync_shell`.
- `host_vars/nas/vars.yml` — `nas_capture_source` + `nas_journal_source` + `nas_capture_red_source` `deploy@ → zcrypto-data@`.
- `~/.ssh/config` (workstation-local, not repo-tracked) — the `zcrypto`/`red` aliases' `User → zcrypto-deploy` (if they pin a user).
- `infra/README.md` / a capture README + `infra/nas/README.md` — the capture m2m user is `zcrypto-data`, admin is `zcrypto-deploy`, the three VPS sources are `zcrypto-data@`; the DSM/NAS forced-command-only note is already recorded.
- `docs/iterations-history-phase1.md`, `docs/open-topics/T0068-…` (closeout), `docs/open-topics/T0042-…` (D5 residual acceptance).

---

### Task 1: Rename the capture account → `zcrypto-data` with the rrsync-only shell (base + capture roles) — code only

**Files:**
- Modify: `infra/ansible/roles/base/defaults/main.yml`, `infra/ansible/roles/base/tasks/main.yml`
- Modify: `infra/ansible/roles/capture/defaults/main.yml`, `infra/ansible/roles/capture/tasks/main.yml`

**Interfaces:**
- Produces: the capture role references `zcrypto-data` (getent key + literal owner), deploys `files/rrsync-shell` to `/usr/local/sbin/rrsync-shell`, and installs the capture export key on `zcrypto-data` (dual with `deploy` until the NAS repoint). Consumed live by Tasks 5/7.
- Note: **not applied to any host** — validated by the attended converges (Task 5 first). A `--check` before the host's `usermod` reports the getent for `zcrypto-data` failing; that is the known check-mode limitation (the real run, after `usermod`, resolves it).

- [ ] **Step 1: Rename the base var + parametrize the shell.** In `roles/base/defaults/main.yml` change `base_capture_user: kraken-capture` → `base_capture_user: zcrypto-data` and add `base_capture_shell: /usr/local/sbin/rrsync-shell`. In `roles/base/tasks/main.yml:81-88`, change the capture-user task's `shell: /usr/sbin/nologin` → `shell: "{{ base_capture_shell }}"` (add a comment: *the capture user now also SERVES the NAS pulls — spec 00057 — so it needs the rrsync-only wrapper, not nologin; the wrapper file is deployed by the capture role in the same converge*).

- [ ] **Step 2: Deploy the wrapper in the capture role.** In `roles/capture/tasks/main.yml`, **before** the getent task (`:5`), insert (mirrors `roles/ops/tasks/main.yml:126-133`; add a `capture_rrsync_shell: /usr/local/sbin/rrsync-shell` default in `roles/capture/defaults/main.yml`):

```yaml
# Fleet users/groups (spec 00057): zcrypto-data (renamed from kraken-capture, uid kept) SERVES the
# NAS capture pull via an rrsync forced-command key, so it needs a login-capable shell. DSM rejects a
# custom shell, but these hosts are Debian, so the same rrsync-only wrapper the ops node uses works.
- name: install the rrsync-only login shell for zcrypto-data (spec 00057)
  ansible.builtin.copy:
    src: "{{ playbook_dir }}/files/rrsync-shell"
    dest: "{{ capture_rrsync_shell }}"
    owner: root
    group: root
    mode: "0755"
```

- [ ] **Step 3: Retarget the getent + set_fact + literal owner to `zcrypto-data`.** In `roles/capture/tasks/main.yml`: the getent `key: kraken-capture` (`:8`) → `key: zcrypto-data`; the two `set_fact` refs `ansible_facts['getent_passwd']['kraken-capture']` (`:12-13`) → `['zcrypto-data']`; the data-dir task's **literal** `owner: kraken-capture`/`group: kraken-capture` (`:27-28`) → `owner: zcrypto-data`/`group: zcrypto-data`. Also update the now-stale `kraken-capture` strings in **task names + comments** (`roles/base/tasks/main.yml:81,90`; `roles/capture/tasks/main.yml:5,10`) so converged output/logs don't name a retired identity — cosmetic, but keep it consistent.

- [ ] **Step 4: Move the capture export key to `zcrypto-data`; drop the deploy-in-group hack.** Rewrite `roles/capture/tasks/main.yml:75-93`:

```yaml
# The capture data export the NAS pulls now lands on zcrypto-data (the m2m data user, spec 00057),
# not the admin `deploy`. exclusive:false ADDS it; deploy's old copy is dropped by a one-time step
# AFTER the NAS repoints (Task 5/8) — dual authorization so the pull never drops. zcrypto-data OWNS
# the 0750 capture dir now, so the old `deploy`-in-kraken-capture-group traversal hack is gone.
- name: install the sync_capture pubkey as a forced-command entry on zcrypto-data (segments read-only)
  ansible.posix.authorized_key:
    user: zcrypto-data
    exclusive: false
    key: "{{ sync_capture_authorized_key }}"
    key_options: 'command="/usr/bin/rrsync -ro {{ capture_data_dir }}",restrict'
```

- [ ] **Step 5: Verify parse + commit.** Run `infra/ansible/scripts/run.sh site.yml --list-tags` (parses the tree without touching hosts; expect no error). Do **not** converge.

```bash
git add infra/ansible/roles/base infra/ansible/roles/capture
git commit -m "feat(infra): capture account -> zcrypto-data with rrsync-only shell, export key off deploy (spec 00057)"
```

---

### Task 2: Rename the engine account → `zcrypto-engine`; journal export → `zcrypto-data` (engine role) — code only

**Files:**
- Modify: `infra/ansible/roles/engine/tasks/main.yml`

**Interfaces:**
- Consumes: `zcrypto-data` (Task 1). Produces: the engine role references `zcrypto-engine`; the journal export key is on `zcrypto-data` with `zcrypto-data ∈ zcrypto-engine` group + the journal group-readable. Only `zcrypto` (engine_host) runs this.

- [ ] **Step 1: Rename every `kraken-engine` literal → `zcrypto-engine`.** In `roles/engine/tasks/main.yml`: the user task `name: kraken-engine` (`:125`); the getent `key: kraken-engine` (`:134`); the `set_fact` derivation keys `engine_passwd['kraken-engine']` (`:143-152`); the three state-dir `owner: kraken-engine`/`group: kraken-engine` (`:155-165`); the store-copy owner/group (`~:184-193`); and the `add deploy to the kraken-engine group` task's `groups: kraken-engine` (`:300-310`). Keep `shell: /usr/sbin/nologin` (the engine user serves no pull). Paths/unit/compose are already `zcrypto-engine` — no change. Also update the stale `kraken-engine` strings in task names/comments (`:4,122-123`) for consistency (cosmetic).

- [ ] **Step 2: Move the journal export key to `zcrypto-data` + grant traversal & read.** Rewrite `roles/engine/tasks/main.yml:293-310`:

```yaml
# The journal export the NAS pulls now lands on zcrypto-data (the m2m data user, spec 00057), not the
# admin `deploy`. zcrypto-data is not the journal's owner (zcrypto-engine is), so it joins the
# zcrypto-engine group to TRAVERSE the 0750 dirs; and the journal files must be group-READABLE for the
# rrsync -ro pull. exclusive:false — deploy's old copy is dropped after the NAS repoints (Task 7/8).
- name: install the sync pubkey as a forced-command entry on zcrypto-data (journal read-only)
  ansible.posix.authorized_key:
    user: zcrypto-data
    exclusive: false
    key: "{{ sync_authorized_key }}"
    key_options: 'command="/usr/bin/rrsync -ro {{ engine_state_dir }}/journal",restrict'

- name: add zcrypto-data to the zcrypto-engine group (traverse the 0750 journal subtree for the pull)
  ansible.builtin.user:
    name: zcrypto-data
    groups: zcrypto-engine
    append: true
  when: not (ansible_check_mode and not engine_account_known)
  vars:
    engine_account_known: "{{ ((ansible_facts['getent_passwd'] | default({}))['zcrypto-engine'] | default(none)) is not none }}"

- name: ensure the journal subtree is group-readable (zcrypto-data pulls it as rrsync -ro)
  ansible.builtin.file:
    path: "{{ engine_state_dir }}/journal"
    state: directory
    recurse: true
    mode: g+rX
```

  Note: confirm the engine writes journal files world/group-readable already; the `g+rX` grant makes the pull deterministic regardless. `recurse: true` + `mode: g+rX` only ADDS the group-read/traverse bit (capital `X` = dirs + already-executable), never strips.

- [ ] **Step 3: Retarget the sshd AllowUsers assert.** In `roles/engine/tasks/main.yml:114` (§8 gate), change the `allowusers .*\bdeploy\b` regex and its `fail_msg` `deploy → zcrypto-deploy`. (The actual `AllowUsers` line is set by the `hardening` role — handled in Task 3; this is only the engine-side assert that guards it.)

- [ ] **Step 4: Assert the trade key stays isolated (verification note, no code).** Confirm `engine.env` is `0600 root:root` via compose `env_file` (`:213-230`) — the rename changes only the compose `user:` uid mapping, which still cannot read a `0600 root` file. Record this in the task's commit body.

- [ ] **Step 5: Parse + commit.** `infra/ansible/scripts/run.sh site.yml --list-tags` (no error).

```bash
git add infra/ansible/roles/engine
git commit -m "feat(infra): engine account -> zcrypto-engine (uid kept), journal export off deploy onto zcrypto-data (spec 00057)"
```

---

### Task 3: Prep the `deploy → zcrypto-deploy` split — virgin bootstrap + `AllowUsers` superset (NOT the live flip) — code only

**Files:**
- Modify: `infra/ansible/bootstrap.yml` (capture play), `infra/ansible/roles/hardening/defaults/main.yml`, `infra/ansible/roles/engine/tasks/main.yml` (§8 assert)

**Interfaces:**
- Produces: virgin capture hosts get `zcrypto-deploy` (one key, `exclusive: true`); the sshd `AllowUsers` **superset** admits the new pull user `zcrypto-data` **and** pre-lists `zcrypto-deploy` while keeping `deploy` + `root`. **Does NOT flip `ansible_user`/`docker_deploy_user`** — those are per-host, applied only after each host's `usermod` (Task 5/7 Step 6). Front-loading them breaks the pre-rename converge (see Global Constraints).

- [ ] **Step 1: Bootstrap → `zcrypto-deploy` (virgin hosts only).** In `bootstrap.yml`'s capture play (`:24-33`), mirror the already-done ops play (`:64-73`): `name: zcrypto-deploy` in the user task; `dest: /etc/sudoers.d/zcrypto-deploy` with `zcrypto-deploy ALL=(ALL) NOPASSWD:ALL`; `user: zcrypto-deploy` + `exclusive: true` on the authorized_key task (spec D1 — one key, no drift). `bootstrap.yml` is not run against the live hosts in this migration — the running boxes are renamed by `usermod` (Tasks 5/7); this only fixes future from-scratch rebuilds.

- [ ] **Step 2: `AllowUsers` superset — add the pull user, keep `deploy` + `root`.** Find the source: `grep -rn "ssh_allow_users\|allow_users" infra/ansible/roles/hardening` (the var is `hardening_ssh_allow_users`, underscore — `grep -i allowusers` finds nothing). In `roles/hardening/defaults/main.yml:2`, change `hardening_ssh_allow_users: deploy root` → `hardening_ssh_allow_users: zcrypto-data zcrypto-deploy deploy root`. Rationale (comment it): `zcrypto-data` = the new m2m pull user the NAS connects as (sshd gates it BEFORE the forced command); `zcrypto-deploy` pre-listed so the post-rename admin connects; `deploy` kept until it is renamed on each host; `root` is the key-only break-glass (**never drop**). A listed-but-absent user is a harmless no-op, so this one value is correct for both hosts in every rename state.

- [ ] **Step 3: Make the engine §8 `AllowUsers` assert tolerate the superset.** In `roles/engine/tasks/main.yml:114`, the gate asserts `allowusers …\bdeploy\b`. Update it to assert the sshd config's `AllowUsers` **contains `zcrypto-data` AND `zcrypto-deploy`** (the two users the fleet actually needs post-migration) rather than the single literal `deploy`, and fix its `fail_msg`. It must not fail on the superset.

- [ ] **Step 4: Parse + commit.** `infra/ansible/scripts/run.sh site.yml --list-tags` (no error).

```bash
git add infra/ansible/bootstrap.yml infra/ansible/roles/hardening/defaults/main.yml infra/ansible/roles/engine/tasks/main.yml
git commit -m "feat(infra): capture-host virgin bootstrap -> zcrypto-deploy + AllowUsers admits zcrypto-data (spec 00057 D1)"
```

---

### Task 4: First-time `zcrypto-alloy` on the capture hosts (new Alloy stack) — code only

**Files:**
- Create: `infra/ansible/roles/capture/templates/alloy-compose.yaml.j2`, `infra/ansible/roles/capture/templates/alloy-secrets.env.j2`, `infra/ansible/roles/capture/files/config.alloy`
- Modify: `infra/ansible/roles/capture/tasks/main.yml` (an `alloy_digest`-gated block), `infra/ansible/roles/capture/defaults/main.yml`

**Interfaces:**
- Consumes: the `observed` group creds (already resolve on capture hosts), the `docker` group (exists). Produces: a rendered-but-not-started Alloy stack per capture host; `zcrypto-alloy` dedicated nologin user. Started attended in Tasks 5/7.

- [ ] **Step 1: Lift the ops Alloy templates.** Copy `roles/ops/templates/alloy-compose.yaml.j2` → `roles/capture/templates/alloy-compose.yaml.j2` and `roles/ops/templates/alloy-secrets.env.j2` → `roles/capture/templates/alloy-secrets.env.j2`, renaming `ops_alloy_uid`/`ops_alloy_gid`/`ops_docker_gid`/`ops_journal_gid`/`ops_alloy_image`/`ops_textfile_dir` → `capture_*` equivalents. The secrets template (the six `GRAFANA_*` from `group_vars/observed/vault.yml`) is identical. Capture has **no** textfile-collector gate metric — drop the `{{ ops_textfile_dir }}:/textfile:ro` mount.

- [ ] **Step 2: Author `roles/capture/files/config.alloy` FRESH.** It is `copy:` (contains Go `{{ }}` — never `template:`). Base it on `roles/ops/files/config.alloy` but set the host label to `{{ constants }}`-free literal per host — since `copy:` can't vary per host, use one config with the host discovered at runtime (Alloy's `constants.hostname` / `sys.env("HOSTNAME")`), OR two files selected by a `capture_alloy_config` var defaulting per host. Pipelines: the docker log tailer (the capture container) + the systemd-journal source; the keep-list is the capture-relevant series (drop the ops `zcrypto_ops_*` / poller series). Do NOT ship a gate/textfile scrape (capture hosts have none).

- [ ] **Step 3: Add the `alloy_digest`-gated deploy block** to `roles/capture/tasks/main.yml` (lift `roles/ops/tasks/main.yml:332-471`, `when: capture_alloy_digest is defined`): create `zcrypto-alloy` (`system: true`, `shell: /usr/sbin/nologin`, `create_home: false`, non-key-owning — the load-bearing rationale: Alloy mounts `/:/host/root:ro`, so it must own nothing key-adjacent); getent `zcrypto-alloy` → uid/gid, getent group `docker` → gid, getent group `systemd-journal` → gid; ensure `capture_alloy_dir`, `copy` config.alloy, render `alloy-compose.yaml.j2` → `compose.yaml`. **Own these admin-plane files `owner: root group: root`** — the ops block owns them `zcrypto-deploy`, which does **not exist** at this converge (before the deploy rename) and would fail user-lookup; `root:root` also matches the capture role's own `/opt/zcrypto-capture` + compose convention. Only `capture_alloy_dir/alloy-data` and the rendered `alloy-secrets.env` (`0600`, `no_log`, `diff: false`) are owned `zcrypto-alloy`. Add defaults `capture_alloy_dir: /etc/zcrypto-capture/alloy`, `capture_alloy_image: grafana/alloy` (no `capture_alloy_digest` default — passed per run).

- [ ] **Step 4: Preview (parse only) + commit.** `infra/ansible/scripts/run.sh site.yml --list-tags`; optionally `ansible-lint` the new templates.

```bash
git add infra/ansible/roles/capture
git commit -m "feat(infra): first-time zcrypto-alloy telemetry stack on the capture hosts (spec 00057 D5)"
```

---

### Task 5 (ATTENDED, orchestrator-only): migrate the SECONDARY `zcrypto-red` (window 22:25 UTC)

**Files:** none new (applies Tasks 1–4 live to `zcrypto-red`; workstation `~/.ssh/config` edit).

**Interfaces:** Consumes Tasks 1–4. Produces: `zcrypto-red` fully on the `zcrypto-*` model, capture green, Alloy shipping, the NAS pulling capture-red as `zcrypto-data@`.

**Why attended + safe:** `usermod -l` keeps uid 999 so the capture data + numeric container mapping stay valid; the converge restarts capture once (resubscribe-replay); the NAS repoints before `deploy` is renamed so the pull never targets a vanished account; the root break-glass is the safety net for the admin rename.

- [ ] **Step 1: Pre-flight.** Confirm the window, capture currently green (`ssh red 'sudo docker logs --since 10m <capture-ctr> 2>&1 | grep -iE "quarantined|ambiguous|merge failed"'` → none), and you have the current capture image digest: `ssh red 'sudo docker inspect <capture-ctr> --format "{{.Image}}"'`.

- [ ] **Step 2: In-place rename, uid kept (root break-glass).** `ssh root@zcrypto-red`:

```bash
pgrep -u kraken-capture -a || echo "no kraken-capture host procs (the container runs as uid 999, not a host login)"
usermod -l zcrypto-data kraken-capture && groupmod -n zcrypto-data kraken-capture
usermod -s /usr/local/sbin/rrsync-shell zcrypto-data      # wrapper deployed by the converge below; shell attr set now
id zcrypto-data       # expect uid=999 gid=999(zcrypto-data)
```

  (The wrapper file does not exist until Step 3's converge; setting the shell attribute first is safe — no SSH-as-zcrypto-data happens until after the converge.)

- [ ] **Step 3: Converge `zcrypto-red`** (deploys the wrapper, retargets container run-as to the uid-999 `zcrypto-data`, chowns the data dir label, installs the capture export key on `zcrypto-data` **dual** with `deploy`, applies the `AllowUsers` superset so `zcrypto-data@` can serve the pull, renders the Alloy stack). **This converge connects as `ansible_user: deploy`** — still valid (`deploy` not renamed until Step 5, and it stays in `AllowUsers`). Preview then apply:

```bash
infra/ansible/scripts/run.sh site.yml --limit zcrypto-red -e capture_image_digest=<current> -e capture_alloy_digest=<alloy-digest> --check --diff
infra/ansible/scripts/run.sh site.yml --limit zcrypto-red -e capture_image_digest=<current> -e capture_alloy_digest=<alloy-digest>
```

  Verify: `ssh red 'sudo docker inspect <capture-ctr> --format "{{.Config.User}}"'` → `999:999`; capture data dir owned `zcrypto-data`; `sudo grep -c "rrsync -ro" ~zcrypto-data/.ssh/authorized_keys` → 1; capture green after restart (`:00:00.0x` boundary on the next hour, no `quarantined`/`merge failed`).

- [ ] **Step 4: Repoint the NAS capture-red source + verify (dual-key cutover).** In `host_vars/nas/vars.yml`, `nas_capture_red_source: "deploy@zcrypto-red.zhaow.me:" → "zcrypto-data@zcrypto-red.zhaow.me:"`. `infra/ansible/scripts/run.sh site.yml --limit nas --tags nas --check --diff` then `-e nas_apply_compose=true`. Verify the NAS pulls capture-red as `zcrypto-data@`: `ssh nas 'sudo /usr/local/bin/docker logs --since 5m zcrypto-archive-archive-pull-1 2>&1 | grep -iE "capture.?red|ERROR|denied"'` → a clean pull, no error. Confirm a fresh capture-red hour landed on the NAS.

- [ ] **Step 5: Drop `deploy`'s residual capture-red export key, then rename `deploy → zcrypto-deploy` (root break-glass).** Now that the NAS pulls as `zcrypto-data`:

```bash
ssh root@zcrypto-red 'cp ~deploy/.ssh/authorized_keys ~deploy/.ssh/authorized_keys.bak-t0068 && \
  grep -v "rrsync -ro" ~deploy/.ssh/authorized_keys > /tmp/ak && mv /tmp/ak ~deploy/.ssh/authorized_keys && \
  chown deploy: ~deploy/.ssh/authorized_keys && grep -c . ~deploy/.ssh/authorized_keys'   # expect 1 (interactive key only)
ssh root@zcrypto-red 'pgrep -u deploy -a || echo "no deploy procs"; \
  usermod -l zcrypto-deploy deploy && groupmod -n zcrypto-deploy deploy && \
  usermod -d /home/zcrypto-deploy -m zcrypto-deploy && \
  sed "s/^deploy /zcrypto-deploy /" /etc/sudoers.d/deploy > /etc/sudoers.d/zcrypto-deploy && \
  visudo -cf /etc/sudoers.d/zcrypto-deploy && rm /etc/sudoers.d/deploy && id zcrypto-deploy'
```

- [ ] **Step 6: Flip Ansible/ssh to `zcrypto-deploy` — PER-HOST — re-converge, first-start Alloy.** Create `host_vars/zcrypto-red/vars.yml` entries `ansible_user: zcrypto-deploy` and `docker_deploy_user: zcrypto-deploy` (per-host override — the shared `group_vars`/role default stay `deploy` so the not-yet-migrated primary still converges). Update the workstation `~/.ssh/config` `red` alias `User → zcrypto-deploy`. Confirm: `ssh red 'whoami; sudo -n true && echo sudo-ok'` → `zcrypto-deploy`. Re-converge idempotently as `zcrypto-deploy` (now in `AllowUsers` from Task 3's superset; `docker_deploy_user` now resolves): `infra/ansible/scripts/run.sh site.yml --limit zcrypto-red -e capture_image_digest=<current> -e capture_alloy_digest=<alloy-digest> --check --diff` → `failed=0`, no unexpected changes. Start Alloy: `ssh red 'cd /etc/zcrypto-capture/alloy && sudo docker compose up -d'`.

- [ ] **Step 7: Verify by outcome.** Capture green (continuity clean on a pulled copy); Alloy shipping (`ssh red 'sudo docker logs --since 3m <alloy-ctr> 2>&1 | grep -iE "error|remote_write|loki"'` → writes flowing, no auth error; confirm the `zcrypto-red` host appears in Grafana). Note the `~/.ssh/config` edit + the outcomes for the closeout.

- [ ] **Step 8: Commit the NAS repoint + the secondary's identity override.**

```bash
git add infra/ansible/host_vars/nas/vars.yml infra/ansible/host_vars/zcrypto-red/vars.yml
git commit -m "feat(infra): zcrypto-red on zcrypto-* identities; NAS pulls capture-red as zcrypto-data@ (spec 00057, secondary cutover)"
```

---

### Task 6: Bake the secondary (the canary gate)

**Files:** none (verification-only hold before the primary).

- [ ] **Step 1:** Hold ≥ the agreed bake (per `fleet-deploys.md`, ≥ 24 h for an image re-pin; for this identity-only change a shorter owner-approved bake is acceptable — record the chosen duration). During the bake, confirm `zcrypto-red`: capture green (no `quarantined`/`ambiguous`/`merge failed`; `:00:00.0x` boundaries; continuity clean), the NAS capture-red pull flowing as `zcrypto-data@` each cycle, Alloy still shipping, `RestartCount` 0 on capture + Alloy.
- [ ] **Step 2:** Only on a clean bake, proceed to Task 7. A regression on the secondary is a **stop** — diagnose before touching the primary. (No primary touch on a red canary — `fleet-deploys.md`.)

---

### Task 7 (ATTENDED, orchestrator-only): migrate the PRIMARY `zcrypto` (window 21:25 UTC, `converge_primary=true`)

**Files:** none new (applies Tasks 1–4 live to `zcrypto`, incl. the engine; workstation `~/.ssh/config`).

**Interfaces:** Consumes Tasks 1–4 + a clean secondary bake. Produces: `zcrypto` fully on the model — capture + engine + Alloy — with the NAS pulling capture & journal as `zcrypto-data@`.

**Why the extra ceremony:** `zcrypto` carries the live capture **and** the (currently non-trading) engine + trade key. The converge restarts both — hence `-e converge_primary=true` + both image digests. The engine restart is benign (no live trading, owner-confirmed); the trade key stays unreadable by `zcrypto-engine` (D4).

- [ ] **Step 1: Pre-flight.** Window confirmed; capture green; get both digests: `ssh zcrypto 'sudo docker inspect <capture-ctr> --format "{{.Image}}"; sudo docker inspect <engine-ctr> --format "{{.Image}}"'`. Confirm the engine is not mid-anything critical (no live trading).

- [ ] **Step 2: In-place renames, uids kept (root break-glass).** `ssh root@zcrypto`:

```bash
usermod -l zcrypto-data kraken-capture && groupmod -n zcrypto-data kraken-capture
usermod -s /usr/local/sbin/rrsync-shell zcrypto-data
usermod -l zcrypto-engine kraken-engine && groupmod -n zcrypto-engine kraken-engine   # stays nologin
id zcrypto-data      # uid=999
id zcrypto-engine    # uid=997
```

- [ ] **Step 3: Converge the primary** (capture + engine plays; deploys wrapper, retargets both container run-as by uid, installs BOTH export keys on `zcrypto-data` dual with `deploy`, grants journal group-read + `zcrypto-data ∈ zcrypto-engine`, applies the `AllowUsers` superset, renders Alloy). **Connects as `ansible_user: deploy`** — still valid (`deploy` not renamed until Step 5). Preview then apply:

```bash
infra/ansible/scripts/run.sh site.yml --limit zcrypto -e converge_primary=true -e capture_image_digest=<cap> -e engine_image_digest=<eng> -e capture_alloy_digest=<alloy> --check --diff
infra/ansible/scripts/run.sh site.yml --limit zcrypto -e converge_primary=true -e capture_image_digest=<cap> -e engine_image_digest=<eng> -e capture_alloy_digest=<alloy>
```

  Verify: capture container `999:999`, engine container `997:997`; `~zcrypto-data/.ssh/authorized_keys` has **2** `rrsync -ro` lines (capture + journal); `zcrypto-data` ∈ `zcrypto-engine` group; the journal subtree group-readable; `engine.env` still `0600 root:root` and **unreadable** by `zcrypto-engine` (`ssh root@zcrypto 'sudo -u zcrypto-engine cat /opt/zcrypto-engine/engine.env; echo rc=$?'` → permission denied). Capture green after restart; engine back up (`docker logs`).

- [ ] **Step 4: Repoint the NAS capture + journal sources + verify.** In `host_vars/nas/vars.yml`, `nas_capture_source` and `nas_journal_source` `deploy@zcrypto.zhaow.me: → zcrypto-data@zcrypto.zhaow.me:`. NAS converge (`--tags nas --check --diff` then `-e nas_apply_compose=true`). Verify both channels pull as `zcrypto-data@` (capture hour advances; journal pull clean → `gate-export` still runs on the NAS): `ssh nas 'sudo /usr/local/bin/docker logs --since 5m zcrypto-archive-archive-pull-1 2>&1 | grep -iE "capture|journal|gate|ERROR|denied"'`.

- [ ] **Step 5: Drop `deploy`'s residual export keys, rename `deploy → zcrypto-deploy` (root break-glass).** Same as Task 5 Step 5 (the primary's `deploy` carries BOTH the capture and journal export keys — the `grep -v "rrsync -ro"` drops both), then `usermod -l`/sudoers rename.

- [ ] **Step 6: Flip Ansible/ssh to `zcrypto-deploy` — PER-HOST — re-converge, first-start Alloy.** Create `host_vars/zcrypto/vars.yml` entries `ansible_user: zcrypto-deploy` + `docker_deploy_user: zcrypto-deploy`; update the `~/.ssh/config` `zcrypto` alias `User → zcrypto-deploy`; `ssh zcrypto 'whoami; sudo -n true'` → `zcrypto-deploy`. Idempotent re-converge as `zcrypto-deploy` `--check --diff` (`-e converge_primary=true` + all three digests) → `failed=0`, no unexpected changes. `ssh zcrypto 'cd /etc/zcrypto-capture/alloy && sudo docker compose up -d'`.

- [ ] **Step 7: Verify by outcome.** Capture continuity clean (pulled copy); engine journal advancing + `gate-export` green on the NAS; Alloy shipping (`zcrypto` in Grafana); no `RestartCount` churn. Note the outcomes for the closeout.

- [ ] **Step 8: Commit the NAS repoint + the primary's identity override.** Now that both hosts are on `zcrypto-deploy`, also drop the stale `deploy` from the `AllowUsers` superset (`roles/hardening/defaults/main.yml` → `zcrypto-data zcrypto-deploy root`) — this rides *this* primary converge (already a `converge_primary` run), so it needs no extra window; re-run Step 6's re-converge if the edit lands after it.

```bash
git add infra/ansible/host_vars/nas/vars.yml infra/ansible/host_vars/zcrypto/vars.yml infra/ansible/roles/hardening/defaults/main.yml
git commit -m "feat(infra): zcrypto on zcrypto-* identities; NAS pulls capture+journal as zcrypto-data@; drop stale deploy from AllowUsers (spec 00057, primary cutover)"
```

---

### Task 8 (ATTENDED): record the D5 telemetry residual acceptance

**Files:** Modify `docs/open-topics/T0042-alloy-holds-root-equivalent-docker-access.md`

**Interfaces:** Consumes: Alloy live on `zcrypto` (Task 7). Produces: the on-the-record D5 acceptance (spec 00057 D5 / T0068 says record it at deploy time).

- [ ] **Step 1:** Append to `T0042` a dated note: `zcrypto-alloy` now runs on the engine host `zcrypto` under the uniform telemetry pattern; the docker-access residual therefore reaches the trade-key domain on this host; the owner **accepts it for uniformity/simplicity** (non-root `zcrypto-alloy` owning nothing key-adjacent is the mitigation), rather than special-casing the engine host. Link the Task-7 commit. Keep `T0042`'s status per its own lifecycle (this is an acceptance record, not a resolution).

- [ ] **Step 2: Commit.** `git add docs/open-topics/T0042-… && git commit -m "docs(open-topics): record the D5 engine-host Alloy residual acceptance (spec 00057)"`

---

### Task 9: Closeout

- [ ] **Step 1:** `[[T0068]]` — flip to `resolved`, `git mv` to `docs/open-topics/archive/`, sync the index (move the bullet to `## Live trading preparation` → `### Resolved`? — it is a Research/infra host-migration; place it in the same category as `T0067` was: **Research and development** → `### Resolved`, link → `archive/`). Confirm no live deferred sub-item remains (the D5 record is Task 8; nothing else is parked under it).
- [ ] **Step 2:** Append the closeout to `docs/iterations-history-phase1.md` (`## <YYYY-MM-DD> — iter-<NNN>: fleet users/groups (capture/engine phase) — captures onto zcrypto-* (spec 00057)`): the `kraken-* → zcrypto-*` uid-preserving renames; the capture + journal exports Ansible-provisioned on `zcrypto-data` + NAS repointed with the dual-key/no-gap ordering; first-time `zcrypto-alloy` (D5 residual accepted, T0042); `deploy → zcrypto-deploy`; the secondary-first canary + the measured outcomes (capture continuity clean both hosts, engine journal + gate-export green, Alloy shipping).
- [ ] **Step 3:** README updates — `infra/README.md` (or a capture README) + `infra/nas/README.md`: capture m2m user is `zcrypto-data`, admin is `zcrypto-deploy`, the three VPS pull sources are `zcrypto-data@`, and the capture hosts run Alloy. No `zcrypto` CLI surface changed → no README `## Usage` change.
- [ ] **Step 4:** Final whole-branch review (most capable model) over the T0068 commits; amend `Reviewed-by:` trailers on the code commits (Tasks 1–4, 5-Step-8, 7-Step-8, 8). **No new PR** — the work is on `feat/fleet-users-groups`; when that branch is next pushed/merged (PR #148), its aggregated `Co-Authored-By:`/`Reviewed-by:` and `## Follow-ups` (registered topics only) cover this phase too.

## Self-review

- **Spec coverage:** D1 (`deploy → zcrypto-deploy`, one key `exclusive: true`) → Task 3 + Task 5/7 rename. D2 (`zcrypto-data` m2m: capture container + data + serves pulls, real wrapper shell) → Tasks 1/5/7. D3 (`zcrypto-engine` dedicated, renamed) → Task 2. D4 (trade key isolated at compose/root, behavior-preserving) → Task 2 Step 4 + Task 7 Step 3 verify. D5 (`zcrypto-alloy` uniform, accepted residual) → Tasks 4/7/8. D6/D7 (NAS/`zhaow`) → out of scope (no `zhaow` on capture hosts; NAS only repointed). D8 (`zcrypto-data` uid per-host = 999 here) → preserved by `usermod -l`, never pinned. Everything-Ansible-provisioned → Tasks 1/2 move the keys onto role-managed `zcrypto-data`. Secondary-first canary → Tasks 5→6→7.
- **No placeholders:** exact files + `file:line` anchors + exact `usermod`/converge/verify commands. `<current>`/`<cap>`/`<eng>`/`<alloy>` are resolved by the given `docker inspect` (image digests are per-run inputs, never defaulted). `<NNN>`/`<YYYY-MM-DD>` are the closeout's own.
- **Type/name consistency:** `base_capture_user`/`base_capture_shell`/`capture_rrsync_shell`/`capture_alloy_*` defined in Tasks 1/4 and consumed there; the `zcrypto-data`/`zcrypto-engine`/`zcrypto-deploy` names are used identically across roles; the getent-derived `capture_uid`/`engine_uid` keep their names, only the account they resolve changes.
- **Live-capture safety:** every rename is uid-preserving `usermod` (no data orphaning); the container `--user` stays numeric-999/997; the dual-key + NAS-repoint-before-deploy-rename ordering means the pull never targets a vanished account; `--ignore-existing` covers any pull delay; secondary bakes before the primary; the root break-glass is the admin-rename safety net; the primary converge is gated on `converge_primary=true`.
- **sshd `AllowUsers` + deferred identity flip (branch-review criticals, folded in):** the capture hosts run the `hardening` role (the ops node did not — the gap the ops phase never hit), so the pull user `zcrypto-data` is added to `AllowUsers` (superset, `root` break-glass kept) BEFORE the NAS repoint, else the `zcrypto-data@` pull is denied at sshd → mirror stall → loss. The `deploy → zcrypto-deploy` flip (`ansible_user`/`docker_deploy_user`) is a **per-host `host_vars`** edit applied only after each host's `usermod`, never front-loaded — otherwise the pre-rename converge connects as a nonexistent account, the `docker` role stub-creates it (later `usermod -l` collides), and `hardening` locks out the live `deploy`. The Alloy admin-plane files are `root:root` (not the not-yet-existing `zcrypto-deploy`). The `converge_primary` assert anchor is `site.yml:29-41`.
- **Known limitation:** a pre-`usermod` `--check` reports the `zcrypto-data`/`zcrypto-engine` getent failing (the account still has its old name) — resolved by the real run's step order (rename → converge), same as the ops phase's check-mode note.
