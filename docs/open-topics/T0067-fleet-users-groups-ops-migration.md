---
status: open
ripe_when: OPS-6 (spec 00056) has merged to develop — this iteration branches off develop and finalizes the ops node's identity
---

# Fleet users/groups regularization — ops migration

## Context — what

Execute the **ops-host** phase of the fleet users/groups model ratified in [spec 00057](../specs/00057-fleet-users-groups-design.md): migrate the ops node's entire data path from `deploy` to a new `zcrypto-data` m2m user, and rename `deploy` → `zcrypto-deploy`. Concretely: the poller/reconciler/panel containers run as `zcrypto-data` (not the sudo user); the ops data trees (liquidations, l2-panel, capture-reconciled, hot-out) become `zcrypto-data`-owned; the four m2m forced-command pull keys move `deploy → zcrypto-data` **and become Ansible-provisioned** (they are hand-installed today); the NAS repoints its four sources `deploy@ops → zcrypto-data@ops`; and hot-out becomes `zcrypto-data`-owned with `zhaow` authoring into it via a shared setgid group — finally wiring OPS-6's hot-out *authoring* direction.

## Why this matters

Three defects converge on the ops node today (all measured 2026-07-18): the data-path containers run as `deploy` — **the passwordless-sudo user** — which is exactly the interactive/m2m mixing the model forbids; the D9 pull-export forced-command keys live on `deploy` and are **hand-installed, not Ansible** (violating the "everything on captures/red/ops is Ansible-provisioned" constraint); and `kraken-capture` sits on ops vestigially (created by `base`, no consumer). This iteration lands the ops node in its final, uniform shape and completes the OPS-6 ops-authoring path that was deliberately deferred.

## Findings so far

- Full design + decisions (D1–D8), the current-state facts, and the chosen "Full — `zcrypto-data` serves the pulls" approach are in [spec 00057](../specs/00057-fleet-users-groups-design.md).
- The NAS renames (`zcrypto`→`zcrypto-data`, `zcrypto-dummy`→`zcrypto-alloy`) are **already applied manually** (uid/gid 1000 kept); the ops side is what remains.
- The ops containers share one run-as mapping (`ops_uid/ops_gid` = `deploy`, `roles/ops/tasks/main.yml:153-161`), so switching the poller switches all ops containers at once.
- The live **liquidations** stream is unbackfillable, so the four-channel repoint needs a dual-key transition with near-zero poller downtime.

## Suggested next steps

- Run `superpowers:writing-plans` against spec 00057 for the **ops phase**: an ordered, verify-each-channel-still-pulling migration with the dual-key transition, near-zero poller downtime, and an explicit rollback. Branch off `develop` after OPS-6 merges.
- Include the `deploy → zcrypto-deploy` cutover on ops (home-dir move, sudoers, ssh-config `User`, `ansible_user`, group memberships) and the `authorized_keys` `exclusive: true` cleanup (spec D1).
- Close [[T0068-fleet-users-groups-capture-engine-migration]] is **not** part of this — the capture/engine hosts are a separate later iteration.
