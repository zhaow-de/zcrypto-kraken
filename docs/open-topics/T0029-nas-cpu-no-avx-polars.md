---
status: partial
ripe_when: before Role B (Increment 2) — resolve whether the NAS's compat runtime can bit-identically replay the VPS's AVX-computed journal targets, or Role B must run on the VPS
---

# NAS CPU has no AVX — the zcrypto image's polars crashes there

## Context — what

The three-tier design (spec `00048`) assumed the NAS could run the *exact* `ghcr.io/zhaow-de/zcrypto-capture` x86_64 image unchanged. **False.** The NAS is an **Intel Atom C3538 (Denverton / Goldmont microarchitecture)** with **no AVX / AVX2 / FMA / BMI1 / BMI2 / LZCNT**. The image's `polars` wheel is compiled for those instructions, so the moment the `zcrypto` CLI imports polars it hits `Illegal instruction (core dumped)`. Discovered during the iter-093 Role A T6 deploy: the NAS `archive-pull` container crash-looped on the first pull. The architecture (x86_64) matches; the microarchitecture does not.

## Why this matters

This blocks **all** three-tier NAS roles, not just Role A:

- **Role A (pull):** `zcrypto archive pull` crashes — the CLI's `cli/__main__.py` eagerly imports `cli.capture.command` (→ polars) at startup, so *any* `zcrypto` subcommand crashes on the NAS.
- **Role B (gate-verify):** `zcrypto engine report`/`replay` uses polars heavily → crashes.
- **Role C (redundant capture):** the capture writer uses polars → crashes.

The VPS is fine (AMD EPYC 7713, has AVX2). Only the NAS is affected.

## Findings so far

- CPU: `Intel(R) Atom(TM) CPU C3538` — `/proc/cpuinfo` shows no `avx`/`fma`/`bmi` flags. Confirmed.
- `POLARS_SKIP_CPU_CHECK` does **not** help — it silences the warning but the illegal AVX instruction still executes and crashes.
- **`polars-lts-cpu` is deprecated** ([polars#26534](https://github.com/pola-rs/polars/issues/26534): "no longer being updated"), stuck at 1.33.1 vs our 1.42.1. The maintainer's replacement is the **`rtcompat`** extra: polars 1.42.1 is now a Python package + a separate Rust *runtime* package (`polars-runtime-32` = AVX; `polars-runtime-compat` = baseline). `pip install polars[rtcompat]` adds the compat runtime — **same polars version**, no downgrade.
- **Empirically verified (2026-07-12):** a default `polars` install loads `_polars_runtime_32` (AVX); `polars[rtcompat]` installs BOTH runtimes but polars then loads **compat even on an AVX CPU** — so a single `[rtcompat]` image would slow the VPS. Uninstalling `polars-runtime-32` leaves a clean compat-only install (import + `read_parquet` verified). → **two variants, same version**, NAS lean (compat-only).

## Done so far

- **Decision (2026-07-12): Option A, done right with `rtcompat`.** Two image variants, same polars 1.42.1: the **default** (multi-arch, `polars-runtime-32`/AVX) for the VPS — **byte-identical to today's image, never touched** — and an amd64 **`-compat`** variant (`polars-runtime-compat`, `-32` removed) for the NAS. Implemented as a `POLARS_RUNTIME` build arg in `infra/docker/Dockerfile` + a 2-entry CI matrix in `.github/workflows/capture-image.yml`. Spec `00048`'s wrong "runs the exact image unchanged" line corrected.

## Suggested next steps

- **(Increment 2, Role B — the residual) Resolve replay determinism across runtimes.** Role B replays the VPS's journaled cycles and must match `worst |diff| 0.00e+00`; the NAS runs the **compat** runtime while the VPS's targets were computed on **AVX** (`-32`), and SIMD-vs-scalar float reductions can differ in the last bits. Options: run Role B **on the VPS** (same runtime → trivially bit-identical), or measure whether the compat-vs-AVX delta stays within `compare_targets`' tolerance. Decide when Role B is built. (Role A's pull and Role C's independent capture don't need cross-runtime bit-identity.)
