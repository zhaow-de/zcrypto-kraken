---
status: resolved
---

# Fleet users/groups regularization — capture/engine hosts

## Context — what

Execute the **capture/engine-host** phase of the fleet users/groups model ([spec 00057](../specs/00057-fleet-users-groups-design.md)) on `zcrypto` and `zcrypto-red`: rename `kraken-capture` → `zcrypto-data` and `kraken-engine` → `zcrypto-engine`; move their pull-export forced commands (capture, capture-red, journal) to `zcrypto-data` and Ansible-provision them; rename `deploy` → `zcrypto-deploy`; and **deploy `zcrypto-alloy` to the capture hosts for the first time** (they run no Alloy today — telemetry there is designed via the `observed` group but not yet provisioned).

## Why this matters

These are the highest-ceremony hosts: `zcrypto`/`zcrypto-red` carry the **live, unbackfillable L2 capture stream**, and `zcrypto` additionally holds the **live Kraken trade key**. The migration finalizes the fleet on the uniform `zcrypto-*` model, but it must move the capture daemons' run-as identity and the trade-key-adjacent accounts without a capture gap.

## Why this matters — the accepted telemetry residual (spec 00057 D5)

Provisioning `zcrypto-alloy` on `zcrypto` means Alloy lands on the engine host under the same uniform telemetry pattern used everywhere. That carries the docker-access residual already tracked and accepted in [T0042](T0042-alloy-holds-root-equivalent-docker-access.md), which on this host also reaches the trade-key domain. The owner **accepts it for uniformity/simplicity** (non-root `zcrypto-alloy` as the mitigation, one Alloy shape fleet-wide) rather than special-casing the engine host. Record the acceptance explicitly at deploy time so it is a conscious decision on the record — the residual's specifics live in T0042.

## Findings so far

- Full design + decisions in [spec 00057](../specs/00057-fleet-users-groups-design.md).
- Capture hosts run **no Alloy container and no `docker.sock` mount today** (measured 2026-07-18 on `zcrypto`); the shared Grafana creds live in `group_vars/observed/vault.yml`, so the plumbing to deploy Alloy there exists.
- The trade key is isolated at the compose/root layer (spec 00057 D4), so the `kraken-engine → zcrypto-engine` rename is behavior-preserving; the residual above is the telemetry-access path (T0042), not the container's run-as user.

## Resolution

The capture/engine migration landed in full at iter-105 (see `docs/iterations-history-phase1.md`): the `kraken-capture → zcrypto-data` and `kraken-engine → zcrypto-engine` renames, the pull-export key move with Ansible provisioning, `deploy → zcrypto-deploy`, and the first `zcrypto-alloy` deployment to both capture hosts — sequenced per `fleet-deploys.md`'s canary discipline, with no capture gap.

In the tree: `infra/ansible/roles/base/tasks/main.yml:81` creates the `zcrypto-data` system user (rrsync-only shell, home = its state dir), with the capture-hosts-only guard at `:91-95` documenting the name collision the rename introduced (the ops node owns its own `zcrypto-data` via the `ops` role). Spec `00057` D1 is the ratifying decision.

The one deferral this topic carried — record the spec `00057` D5 telemetry residual acceptance — was **honoured, not lost**: [[T0042]] is live (`status: open`) and carries the 2026-07-19 capture-host acceptance including the primary/trade-key case.

*(Recorded 2026-07-20. The work landed at close but the evidence was never written into this file, so the topic read as unstarted — see `.claude/rules/open-topics.md`.)*

## Suggested next steps (historical — all landed, see Resolution above)

- After [[T0067-fleet-users-groups-ops-migration]] lands, run `superpowers:writing-plans` for the **capture/engine phase**: the `kraken-* → zcrypto-*` renames, the pull-export-key move + Ansible-provisioning, `deploy → zcrypto-deploy`, and the first `zcrypto-alloy` deployment to the capture hosts — sequenced to avoid a capture gap and per the primary/secondary canary discipline (`fleet-deploys.md`).
- At the `zcrypto` Alloy deploy, write the D5 residual acceptance into the record (extend/annotate `T0042`).
