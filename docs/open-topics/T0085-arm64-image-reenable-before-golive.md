---
status: open
ripe_when: before the final go-live (the Stage-6b live-capital step) — one CI edit plus one verified multi-arch build; do not leave it to go-live day itself
---

# Re-enable arm64 (multi-platform) capture-image builds before go-live

## Context — what

Multi-platform image building was deliberately disabled in the CI workflow (`.github/workflows/capture-image.yml`) to keep build times short during development. The go-live posture wants the arm64 image back, so the fleet is not silently amd64-only at the moment it matters.

## Why this matters

A disabled build lane is invisible until something needs it — the exact silent-drift shape the fleet's pins-and-labels discipline exists to prevent. Re-enabling is cheap now and rushed later; a first multi-arch build can also surface QEMU/buildx issues that should not be debugged during a go-live window.

## Findings so far

- The workflow builds `default` and `-compat` variants for `linux/amd64` today; arm64 is **commented out, not removed** — `capture-image.yml:33-36` carries the owner's 2026-07-15 note and the exact restore line (`platforms: linux/amd64,linux/arm64`), and the QEMU binfmt step (line ~47) is what makes the cross-build work on the amd64 runner. Re-enabling is uncommenting plus verifying, not re-engineering.

## Suggested next steps

- **(When ripe)** Re-enable the arm64 platform in `capture-image.yml`; verify one full multi-arch build publishes and both digests carry the expected labels (`revision`, `polars-runtime`).
- **(With it)** Confirm no consumer pins assume single-arch manifest digests (the NAS pin comment's "ONE IMAGE, THREE IDENTIFIERS" note covers the manifest-list case).
