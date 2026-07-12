---
status: open
ripe_when: LIVE BLOCKER now — the three-tier NAS deploy (spec 00048) cannot run until the image strategy is chosen
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
- **`polars-lts-cpu`** is polars' drop-in wheel compiled without AVX2 (works on Goldmont); same API, marginally slower on modern CPUs.

## Suggested next steps — choose the image strategy (human decision)

- **(A) A second `polars-lts-cpu` image variant for the NAS** (VPS keeps the standard AVX image). Pro: **no VPS touch** — the capture daemon is never disturbed. Con: a two-variant CI build to maintain.
- **(B) One `polars-lts-cpu` image everywhere** (swap `polars` → `polars-lts-cpu` in `pyproject.toml`, rebuild the single image, redeploy both). Pro: one image, simplest. Con: requires a **careful VPS redeploy** (a digest bump that restarts the capture container — a brief, budgeted gap like the incident recovery) + marginally slower polars on the VPS (negligible: capture is I/O-bound, the engine is light compute).
- **(C) Make Role A polars-free + lazy-load the CLI** (a dedicated `python -m cli.archive` entrypoint that never imports capture/engine/polars, and a polars-free `verify_manifest`). Pro: Role A deploys **now** on the current image, no rebuild, no VPS touch. Con: only fixes Role A — Roles B/C still need (A) or (B) later, so it defers the real fix.

Whichever is chosen, correct spec `00048`'s "x86_64 is load-bearing / runs the exact image unchanged" line.
