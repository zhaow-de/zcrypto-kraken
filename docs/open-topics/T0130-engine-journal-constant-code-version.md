---
status: open
ripe_when: the next engine-image build for any other reason — the fix rides it as a passenger, never spends its own converge. The 2026-08-06 re-pin was verified minutes after landing and the owner ruled the traceability gap does not justify restarting the live trade engine again on its own.
---

# The engine journal records `code_version: 0.0.0` on every cycle

## Context — what

Every `cycle-<HH>.json` the engine journals carries a `code_version` field, and it is a constant `0.0.0` on every cycle regardless of the image that produced it. Measured across the 2026-08-06 re-pin boundary: `cycle-00.json` (built from `f67afb80`, digest `c7ed09020fe1`) and `cycle-04.json` (built from `7762da47`, digest `ccedc9dd6bf4`) both read `0.0.0`.

## Why this matters

The journal is the engine's durable per-cycle record, and it cannot answer "which build produced this cycle?" — during an incident that answer gets reconstructed from converge timestamps and `docs/reference/fleet-pins.md` instead of being read off the artifact itself. The gap only bites retrospectively, which is exactly when it is most expensive: the reconstruction crosses two records that were written for other purposes, and a cycle near a converge boundary is ambiguous by timestamp alone.

## Findings so far

- The field exists and is populated, so the write path is wired — only the value source is inert. Whatever feeds it never learned the real version (likely a packaging default: the container runs the repo without an installed version stamp the code can read).
- `fleet-pins.md` + the container's `.State.StartedAt` currently answer the question by join, and did so successfully for the 2026-08-06 verification — the workaround exists, it is just not on the artifact.
- Discovered during the iter-127 engine converge verification (2026-08-06), where cycle-00/cycle-04 straddled a build change and read identically.

## Suggested next steps

- Make `code_version` carry something build-identifying: the image digest (first 12) or the git commit the image was built from — both are known at build time; the digest is what `fleet-pins.md` rows key on, so it joins cleanly. Find where the journal writer sources the field and feed it from the image label / an env baked at build rather than the package version, which the container evidently cannot resolve.
- Ship it as a passenger on the next engine-image build (the `ripe_when`), then verify on the first post-converge cycle that the journal value matches the running container's `{{.Config.Image}}` digest.
