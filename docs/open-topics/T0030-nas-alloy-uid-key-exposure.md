---
status: open
ripe_when: a NAS observability-hardening pass, or before the Stage-6b go-live (any tightening of the NAS's compromise blast radius)
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

## Suggested next steps

- **(autonomous, needs the NAS)** Switch `alloy-data` from the `./alloy-data` bind mount to a **Docker-managed named volume**, then one-time (as root) `chown` that volume's `_data` dir to a **dedicated, non-1000, non-key-owning uid** (e.g. 4747), and set the `alloy` service `user:` to that uid. A named volume sidesteps the DSM bind-mount-ACL bug (docker initializes it writable for the container), and the dedicated uid does not own the `0600` keys, so a compromised Alloy can no longer read them via `/host/root`. Verify: Alloy starts, ships metrics + logs, and the remote_write WAL + Loki positions persist across a container recreate and a NAS reboot.
- Alternatively, drop the `/:/host/root:ro` mount and give the unix exporter's `filesystem` collector a narrower rootfs view — but disk-free reporting needs a broad rootfs, so this is likely worse than the dedicated-uid fix.
