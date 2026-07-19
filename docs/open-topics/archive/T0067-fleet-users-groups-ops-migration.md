---
status: resolved
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

## Resolution

Landed in **iter-104** (branch `feat/fleet-users-groups`, plan `docs/plans/00057-fleet-users-groups-ops.md`), all seven tasks executed + verified live on the ops node:

- **`zcrypto-data` m2m user + `zcrypto-hot` exchange group** created (Ansible); `zhaow` (uid 1000) added to `zcrypto-hot`.
- **The four NAS pull keys are now role-provisioned** on `zcrypto-data` (committed pubs in `infra/ansible/files/`) with `rrsync -ro` per-subtree jails.
- **Data ownership + container run-as → `zcrypto-data`**: the poller/reconciler/panel containers run `--user zcrypto-data`; the data trees (`liquidations`, `l2-panel`, `capture-reconciled`, `hot-out`, `textfile`) are `zcrypto-data`-owned; `hot-out` is `zcrypto-data:zcrypto-hot 2775` (setgid). Verified end-to-end: an hourly parquet was written as `zcrypto-data` with no `EACCES`.
- **NAS repointed** its four sources `deploy@ → zcrypto-data@` and pulled all four channels cleanly (`checked=830/2450/407, failed=0`); `deploy`'s four hand-installed keys dropped (5 → 1 interactive).
- **hot-out authoring handoff verified**: `zhaow` authors → `zcrypto-data` serves → NAS pulls (the OPS-6-deferred direction, now live).
- **`deploy → zcrypto-deploy` rename** done over the root break-glass (uid 1001 kept); the converge is idempotent (`changed=0`) as `zcrypto-deploy`.

Two design corrections surfaced + fixed: `zcrypto-data`'s shell must be `/bin/bash` (not `nologin`, which structurally blocks the `rrsync` forced commands — the keys stay jailed by `command=`/`restrict`); and the 5 admin-plane `owner: deploy` role refs had to retarget to `zcrypto-deploy` or the first post-rename converge would fail. Follow-ups registered: [[T0069-gate-export-cpu-cost]] (a slow gate-export step observed in the NAS loop). The capture/engine hosts are the separate [[T0068-fleet-users-groups-capture-engine-migration]], deliberately not part of this.
