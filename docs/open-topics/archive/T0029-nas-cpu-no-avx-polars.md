---
status: resolved
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

- **Decision (2026-07-12): Option A, done right with `rtcompat`.** Two image variants, same polars 1.42.1: the **default** (multi-arch, `polars-runtime-32`/AVX) for the VPS — **its polars runtime untouched** (the shared image also gained rsync/openssh-client and a fixed uid-1000 default user for Role A, but both are inert on the VPS, whose compose overrides `user:` and whose services don't shell out to rsync) — and an amd64 **`-compat`** variant (`polars-runtime-compat`, `-32` removed) for the NAS. Implemented as a `POLARS_RUNTIME` build arg in `infra/docker/Dockerfile` + a 2-entry CI matrix in `.github/workflows/capture-image.yml`. Spec `00048`'s wrong "runs the exact image unchanged" line corrected.

## Resolution — determinism measured, Role B is bit-identical on the NAS (iter-094, 2026-07-12)

The residual is closed by **measurement**, not tolerance-relaxation. Against the 8 VPS-journaled cycles on the **real Atom NAS** (`polars-runtime-compat` + baseline numpy), the **fast path** (the gate path, `zcrypto engine report`/`gate-export`) replays the VPS's AVX-computed targets at **`worst |diff| 0.00e+00` on 8/8 cycles**, matching the AVX control exactly — the exact-rational big-integer builder routes no float reductions through polars/numpy on that path, so it is a genuine cross-runtime *portability* property. (The verified path carries inherent ~`1e-18` same-runtime float noise and is too slow on the Atom, so Role B does not use it.) Role B is deployed + verified live on the NAS: `gate.prom` reports `mismatch_total 0` — the compat replay agrees with the VPS in production. Role B runs on the maximally-independent always-on NAS at the strict `0.00e+00` bar. See spec/plan `00049`, iter-094.
