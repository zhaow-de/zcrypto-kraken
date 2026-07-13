---
status: open
ripe_when: PR #117 (Role B) is merged to develop and its post-merge CI has published the develop-built `zcrypto-capture` `-compat` image (the NAS currently pins the branch-only digest `dfda2580`)
---

# Re-pin the NAS capture image to the develop-built digest after the Role B merge

## Context — what

The NAS archive-pull stack (`infra/nas/compose.yaml`, deployed at `/volume1/docker/zcrypto-archive/compose.yaml`) pins its capture image to a **branch-built** digest — `ghcr.io/zhaow-de/zcrypto-capture@sha256:dfda2580d105a10267b84b7ea5bdab2a24d76bf87277533fc372d98c258108a6` — produced from `feat/role-b-gate-verify` during the iter-094 deploy shakedown. (The `alloy` and `docker-socket-proxy` images pin **upstream** digests, which are stable and need no re-pin.) Once the branch merges to `develop`, `develop`'s CI builds a fresh `-compat` capture image; the NAS should be re-pinned to that develop-built digest so it runs a reproducible artifact traceable to merged history.

## Why this matters

Reproducibility + supply-chain hygiene: the merge deletes `feat/role-b-gate-verify`, and a branch-only image digest may be garbage-collected once the branch is gone (depending on the GHCR package's retention policy) — which would leave the NAS pinned to an unpullable digest on the next `compose up` / container recreate. Independent of that risk, re-pinning to the develop-built digest keeps the deployed artifact traceable to merged history and pullable.

## Findings so far

- NAS `archive-pull` image = `ghcr.io/zhaow-de/zcrypto-capture@sha256:dfda2580…` (branch build).
- `alloy` = `grafana/alloy@sha256:4f6ddc…`, `docker-socket-proxy` = `ghcr.io/tecnativa/docker-socket-proxy@sha256:1f3a6f…` (upstream digests — keep).

## Suggested next steps

- After the merge, wait for `develop`'s CI to publish the new `zcrypto-capture` `-compat` image, then `docker buildx imagetools inspect ghcr.io/zhaow-de/zcrypto-capture:<develop-tag>` to read its digest.
- On the NAS, edit `/volume1/docker/zcrypto-archive/compose.yaml`'s `archive-pull` `image:` to the new `@sha256:…` digest, then `sudo docker compose up -d archive-pull` to recreate; verify `docker ps` shows it healthy and a pull cycle completes with `mismatch_total 0`.
- No repo change needed: `infra/nas/compose.yaml` intentionally keeps `:latest` with a deploy-time-pin note; this topic only re-pins the *deployed* copy.
