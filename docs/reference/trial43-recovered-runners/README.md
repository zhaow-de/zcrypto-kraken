# Trial 43 / 44 scratchpad runners, recovered

These are the scripts registry rows **43** and **44** name in their `run_ref`, recovered verbatim
from a Claude session transcript's `Write`/`Edit` records after the scratchpad itself was gone.
The topic is [[T0148]]; the finding they overturn is [[T0125]]'s "these are gone".

**Their value is that the bytes are the originals.** `ruff.toml` and `.pre-commit-config.yaml` both
exclude this directory so no hook can reformat them — the same guard split used for
`infra/nas/rrsync`, and for the same reason.

## Do not run `trial44_write.py`

It calls `reg.append(...)` against the append-only, hash-chained trial registry — the only such call
in this directory. Four independent things stop it before any write, and naming them makes the claim
checkable rather than reassuring: it loads a missing `trial44_cache.pkl` and dies first; it reads the
pre-move path `docs/research/trial-registry.jsonl`, which no longer exists; it asserts
`len(reg.records) == 43` (there are more now); and its `run_ref` carries the `(scratchpad)` marker
that [[T0125]]'s own append guard rejects outright. Do not run it anyway. The other four only read.

## The files

| file | what it is |
| --- | --- |
| `crossfreq_run.py` | trial 43 stage-1 driver — recovered original (`Write` + 7 `Edit`s replayed) |
| `crossfreq_stage2.py` | trial 43 stage-2 / counterfactual — recovered original |
| `stage1b_verify.py` | trial 43 kill-bar verification — recovered original |
| `trial44_run.py` | trial 44 fixed-weight driver — recovered original |
| `trial44_write.py` | trial 44 registry append — recovered original, **never run** |
| `crossfreq_run_nocache.py` | variant 1 — drops the gone iter-074 elementwise cross-check |
| `crossfreq_run_rederived.py` | variant 2 — variant 1, plus `bench_noc` sourced from committed code |

## Reproducing row 43

    uv run python docs/reference/trial43-recovered-runners/crossfreq_run_rederived.py

Run from the repo root; it reads `data/ohlc-full` by relative path and writes a ~1.8 MB
`trial43_cache.pkl` beside itself (gitignored — do not commit it). Measured 2026-08-21, reproducing
every registered **stage-1** figure. Only this driver has been re-run; the other four rest on the
replay alone, and the run covers 15 of row 43's 35 metrics:

    governed noc Sharpe: 1.5366 full / 1.5319 decisive (k>=1380)
    maxDD: 13.31% governed / 19.46% pre-governor; cap-breach 1265; gov-engaged 7290/27337
    equal-weight fallback bars: 180 warm-up + 10638 zero-vol degenerate

The last line is the strongest check: 180 and 10638 are the row's `weight_warmup_bars` and
`weight_zero_vol_fallback_bars`, and they fall out of the computation rather than being fitted.

## Why the two variants exist

Both substitutions were forced by *upstream* artifacts that were also lost, and both validate
themselves against registered figures rather than against anything recovered:

1. **The A2 arm cross-check** (`a2_4h_cache.pkl`, iter-074). The arms are recomputed from committed
   `a2_book_returns`; only the elementwise comparison against that cache is dropped. The independent
   assert pinning each arm to its **registered** Sharpe is untouched, and all three pass
   (1.3274 / 1.3017 / 1.3585).
2. **`bench_noc`**, which that same cache held as a genuine input. Sourced from committed
   `cli/portfolio/record44_legs.py::benchmark_4h_net_of_cost`, which builds the same frozen 4h
   benchmark, and validated by the script's own pre-existing assert against the **registered**
   1.2128 / 1.2447.

`crossfreq_run.py` — the untouched original — still fails on the missing cache. That is correct and
deliberate: the original is kept as the artifact, not as a runnable.

## Provenance

Source transcript, read 2026-08-21 16:05 UTC and **pruned by the tooling four minutes later**:
`~/.claude/projects/-home-zhaow-Projects-zcrypto-kraken/ea685ee3-3fd7-43cd-9007-bf1bbab513c0.jsonl`.
It *was* the iter-080/081 session — the scripts ran from that session's own scratchpad, the path
`run_ref` records.

| time (UTC) | op | file |
| --- | --- | --- |
| 2026-07-10 11:15:49 | Write | `crossfreq_run.py` |
| 2026-07-10 11:16:28 – 11:42:17 | 7× Edit | `crossfreq_run.py` |
| 2026-07-10 11:46:10 | Write | `crossfreq_stage2.py` |
| 2026-07-10 11:47:23 | Write | `stage1b_verify.py` |
| 2026-07-10 12:16:10 | Write | `trial44_run.py` |
| 2026-07-10 12:20:12 (+1 Edit) | Write | `trial44_write.py` |

Reconstruction: initial `Write` content, then every `Edit` applied in recorded order with each
`old_string` required to match — **13/13 operations, 0 failures**. That proves the recorded Edit
chain is self-consistent (a wrong intermediate state makes the next `old_string` unmatchable). It
does **not** prove these bytes are what ran: the replay reads only `Write` and `Edit`, so a
shell-side mutation or an edit after the last recorded one is invisible by construction. **The
behavioural reproduction above — 180 and 10638 falling out of the computation — is the real proof.**

**The source transcript is gone.** It was pruned by the tooling's 30-day retention at 2026-08-21
16:09 UTC, four minutes after being read and 27 minutes before the commit that preserved these
files. It exists nowhere on disk. **This git history is the only surviving copy, and the replay can
never be independently re-run.**

A transcript is a **forensic** resource, not a provenance mechanism: workstation-local, unbacked,
prunable — as this one demonstrated. [[T0125]]'s `run_ref` guards remain the right answer for
anything written from here on.
