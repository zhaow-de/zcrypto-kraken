---
status: resolved
---

# NAS Alloy runs as uid 1000 and can read the rrsync pull keys via /host/root

## Context — what

Role B's NAS Grafana Alloy container (spec `00049`, iter-094) runs as **uid 1000** (`zcrypto`), not the upstream image's built-in `alloy` uid 473. 473 was the first choice (a non-root user activated only by an explicit `user:` override), but on Synology DSM it does not work: 473 is not a DSM-recognized user, so the DSM ACL on the persistent `./alloy-data` bind mount denies it write and Alloy crash-loops (`mkdir /var/lib/alloy/…: permission denied`). uid 1000 is a real DSM user with write access, and is still non-root, so the §8 "don't run as root" posture holds — **but uid 1000 also owns the `0600` rrsync pull keys** (`/volume1/docker/zcrypto-archive/keys/sync_capture`, `…/sync_journal`), and Alloy mounts `/:/host/root:ro`. So a *compromised* Alloy could `cat` those keys, which uid 473 (owning nothing on the box) could not.

## Why this matters

Defense-in-depth (§8). The 00043 §8 precedent that Role B leans on — "a non-root Alloy can't read `0600 root:root` files through the rootfs mount" — assumed the secrets are **root-owned**; here they are owned by the *same* uid Alloy runs as, so that precedent does not actually cover this case. The exposure was reviewed and **accepted as a named residual** (iter-094 deploy-fix review): the keys are **read-only, `rrsync -ro` path-jailed pull keys** (a leak yields unauthorized read-only pulls of already-archived data — no write, no shell, no lateral movement), the Alloy image is Grafana-signed + digest-pinned, and 473 is a hard DSM blocker. This topic tracks closing the residual so the accepted-but-non-ideal state is not permanent.

## Findings so far

- uid 473 cannot write the DSM-ACL'd `alloy-data` bind mount (the ACL grants host-uid write but is **not honored inside the container**, which sees only the underlying POSIX mode) — confirmed live during the iter-094 deploy.
- uid 1000 writes it fine (real DSM user) and Alloy is stable + shipping, but owns the pull keys.
- The residual is documented in `infra/nas/compose.yaml` (the `NAMED RESIDUAL (§8)` comment on the `alloy` service `user:`) and `infra/nas/README.md`.

## Resolution (iter-094, 2026-07-13)

Resolved in the same PR (iter-094, `feat/role-b-gate-verify` → #117) by running Alloy as a **dedicated, non-key-owning DSM user** rather than reusing uid 1000. The human created `zcrypto-dummy` (**uid 1031, gid 1000** — the `zcrypto` group) on the NAS — a real DSM user (so it can write the DSM-ACL'd `alloy-data` mount, which uid 473 could not) that is **not the owner** of the `0600` rrsync pull keys (uid 1000 is). `infra/nas/compose.yaml` now pins the `alloy` service to `user: "1031:1000"`; the deploy chowns `alloy-data` to `1031:1000` + `chmod 0775`.

`zcrypto-dummy`'s primary group is 1000 (`zcrypto`), which **is** the group that owns the keys — so the protection rests on the keys being `0600` (owner-only; the group has no read bit), not on group isolation. A dedicated non-1000 gid would be marginally stronger defense-in-depth (protection independent of file mode), but the keys are `0600` and that is enforced + verified, so uid 1031 cannot read them as owner (it isn't the owner) or as group (0600 grants the group nothing). Keep the keys `0600`.

This keeps the bind mount (no switch to a named volume needed — the dedicated real-user uid was the missing piece, not the volume type) and preserves the requested host metrics (the `/:/host/root:ro` mount stays, so the unix exporter still reports disk-free across the full rootfs).

**Verified live on the NAS** (iter-094 deploy shakedown, container `User=[1031:1000] running rc=0`): Alloy ships metrics (`prometheus_remote_storage_samples_failed_total 0`, `samples_total 134`) and logs (`loki_write_sent_entries_total ≥1`, all `dropped_entries_total 0`), and reads `gate.prom` (0664, other-readable). The T0030 proof, re-run with the real key-owning gid 1000: as `1031:1000`, reading `/host/root/volume1/docker/zcrypto-archive/keys/sync_journal` → **permission denied** — a compromised Alloy cannot read the pull keys through the rootfs mount. The §8 "non-root Alloy can't read the secrets via `/host/root`" precedent now holds for real, since Alloy's uid no longer owns them.
