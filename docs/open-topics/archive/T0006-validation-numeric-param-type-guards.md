---
status: resolved
---

# Harness numeric-param type guards (raise ValidationError, not TypeError)

## Resolution

**Resolved (iter-021, 2026-07-08, PR #26):** the defined scope — the float numeric params (`bootstrap.py` `mean_block`/`alpha`; `dsr.py` `sr`/`var_trials`/`benchmark_sr`/`skew`/`kurtosis`; `pbo.py` `perf_matrix` cells; plus `metrics.py` `risk_free` and `synthetic.py` `beta`/`noise_sd`) — now `isinstance(x, (int, float))`-guard before their `isfinite`/range checks, raising `ValidationError` on a non-numeric type; 11 regression tests. Per this topic's own "Already-hardened (no action)" note, `dsr.py`'s `n_trials`/`n_obs` are deliberately left `isfinite`-only (they feed arithmetic, not `range()`; a non-numeric type there still gives a clear `TypeError`, never NaN) — closed **per defined scope**, not as "the pattern eliminated everywhere."

## Context — what

Across `cli/validation/`, several numeric parameters are validated with a value check (`math.isfinite(x)` and/or a range comparison) but **not a type check**. When a caller passes a non-numeric **type** (e.g. a `str` or `None`) for one of these, `math.isfinite("x")` or `0 < "x" < 1` raises a bare `TypeError` instead of the harness's uniform `ValidationError`. The functions that feed a value into `range()`/`randrange()` (`n_obs`, `n_resamples`, `n_splits`) were already hardened with `isinstance(..., int)` (iter-015 `pbo.py`, iter-016 `bootstrap.py`); this topic covers the remaining **float-typed** numeric params.

## Why this matters

The harness's stated discipline is *never crash weirdly* — every degenerate input should surface as `ValidationError` so callers (and the acceptance suite) can handle it uniformly. A raw `TypeError` from a wrong-typed argument is a discipline leak, not a correctness bug: **none of these paths can return NaN** (they all raise, just with the wrong exception type), so this is robustness/consistency, not a validity hole — hence deferred to a single coherent pass rather than fixed piecemeal.

## Findings so far

Surfaced by the iter-016 whole-branch review (Important #3). Exact scope (params whose guard is value-only, so a non-numeric type raises `TypeError`):

- **`cli/validation/bootstrap.py`** — `mean_block`, `alpha`.
- **`cli/validation/dsr.py`** — `sr`, `var_trials`, `benchmark_sr`, `skew`, `kurtosis` (all guarded by `math.isfinite` only).
- **`cli/validation/pbo.py`** — the `perf_matrix` **cell** type (cells are `isfinite`-checked; a non-numeric cell raises `TypeError`). The `metric` **return** is already guarded (finite check + the raising-metric wrap), so no exposure there.

Already-hardened (no action): `n_obs`, `n_resamples` (`bootstrap.py`), `n_splits` (`pbo.py`), `n_trials`/`n_obs` (`dsr.py` — `isfinite`-guarded; they are used only in arithmetic, not `range()`, so `isfinite` suffices there but a type guard would still be more uniform), `seed` (`bootstrap.py`, already `isinstance(int)`).

## Suggested next steps

- Add an `isinstance(x, int | float)` check **before** the `math.isfinite`/range check for each param listed above, raising `ValidationError` with a clear message (mirror the existing `isinstance(n_splits, int)` / `isinstance(seed, int)` pattern).
- For `pbo.py`, add the type check to the per-cell loop (`isinstance(x, int | float)`) before `math.isfinite(x)`.
- Add one regression test per module passing a `str`/`None` for a covered param and asserting `ValidationError`.
- Do it as **one coherent pass** across `cli/validation/` (not per-iteration), e.g. folded into the Phase-2 acceptance-suite iteration or a dedicated harness-hardening slice; keep the resampling/statistical math untouched.
