---
status: resolved
---

# The engine journal records `code_version: 0.0.0` on every cycle

## Context — what

Every `cycle-<HH>.json` the engine journals carries a `code_version` field, and it is a constant `0.0.0` on every cycle regardless of the image that produced it. Measured across the 2026-08-06 re-pin boundary: `cycle-00.json` (built from `f67afb80`, digest `c7ed09020fe1`) and `cycle-04.json` (built from `7762da47`, digest `ccedc9dd6bf4`) both read `0.0.0`.

## Why this matters

The journal is the engine's durable per-cycle record, and it cannot answer "which build produced this cycle?" — during an incident that answer gets reconstructed from converge timestamps and `docs/reference/fleet-pins.md` instead of being read off the artifact itself. The gap only bites retrospectively, which is exactly when it is most expensive: the reconstruction crosses two records that were written for other purposes, and a cycle near a converge boundary is ambiguous by timestamp alone.

## Findings so far

- The field exists and is populated, so the write path is wired — only the value source is inert. **Measured, not a packaging default (spec `00089` D8):** no release has ever been cut, so `0.0.0` is the true installed version everywhere — `.cz.toml`, `pyproject.toml`, and the README badge all agree — and `importlib.metadata` reports it faithfully; a semver that has never moved simply cannot identify a build. CI already stamps the git sha as an `org.opencontainers.image.revision` OCI label, but a label sits outside the container and is invisible to the running process, which is the actual gap.
- `fleet-pins.md` + the container's `.State.StartedAt` currently answer the question by join, and did so successfully for the 2026-08-06 verification — the workaround exists, it is just not on the artifact.
- Discovered during the iter-127 engine converge verification (2026-08-06), where cycle-00/cycle-04 straddled a build change and read identically.

## Resolution

Fixed on branch `feat/t0018-venue-truth` (spec/plan `00089`, D8): the GitHub Actions workflow now passes the build sha as `GIT_REVISION` (`ci(build): bake the git revision into the image as ZCRYPTO_BUILD_REVISION`, `b1909607`); the Dockerfile exports it as `ENV ZCRYPTO_BUILD_REVISION` after the `uv sync` layer, so a per-commit-changing arg does not cache-bust the dependency install; and `cli/engine/cycle.py::_code_version()` composes `<package version>+<sha12>` when that env var is present, bare version otherwise — landed in `feat(engine): the venue_state seam -- journaled first, never consulted` (`e5a2b55d`), which also makes the new `venue-HH.json` (spec `00089`) carry the same composed value from birth alongside `cycle-HH.json`.

**Acceptance is by value at the next converge, not at merge** — this fix has not yet deployed. The first `cycle-HH.json`/`venue-HH.json` written under the re-pinned image must read `0.0.0+<sha12>` with the sha matching that image's own `org.opencontainers.image.revision` label; per `capture-deploys.md` and spec `00089`'s deploy section, that reading is the closing evidence and is recorded here once the converge runs.
