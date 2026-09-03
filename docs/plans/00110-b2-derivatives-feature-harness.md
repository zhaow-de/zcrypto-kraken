# B2 derivatives-positioning feature harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ## ✅ The review loop's findings are FOLDED IN (2026-09-03)
>
> Every round's Critical and Important is fixed in this pair. `.tmp/plan-review/00110/` is gitignored and each round OVERWRITES the previous round's fact file, so this block — not that file — is the durable record, and it carries no count read from it. The per-round chronicle is `git log develop..HEAD`, whose commit messages carry each round's changes.
>
> **Round 1** (contract pin, 2026-09-02) refuted eleven premises before the auto-exec time-gate cut the loop:
>
> - **Task 2's look-ahead guard was inert and is replaced.** The old form appended source rows *past the grid's last stamp*, which cannot move any value under any semantics — the pin showed it passing on a deliberate backward-fill defect. The new form truncates: recompute over `grid[:k]` from rows stamped `<= grid[k-1]` and demand the prefix match. **Re-verified on both arms: old guard passes correct AND defect; new guard passes correct and trips the defect at k=2** (the banner first said k=1, from a report rather than a run).
> - **Both planted-signal thresholds asserted `> 3.0`, which no window definition produces.** Spec D7 now pins the semantics (inclusive trailing window ending at `k`, sample stdev, `None` when short or null-bearing, `0.0` at zero variance) and both tests assert the pinned definition's exact value, `2.8460498941515410` — computed, not thresholded.
> - **Task 4 asked null propagation through `_validate_prices`, which raises on `None`.** Task 1 now adds `_validate_levels` (finite, `> 0`, or `None`).
> - **"Matching the convention exactly" was false about length.** The existing five return `len(prices) - 1`, aligned to `returns_from_prices`; these align to the input grid and return `len(input)`. Stated in both artefacts.
> - **Four spec facts corrected**: the 2022 hole is panel-wide (87.3 % in nine symbols, 87.0 % in XRP; panel null 18.4 %, not BTC's diluted 14.9 %); "none before 2022-01-30" is true only within 2022; the B2 quote is master-plan **§5**, not §12; B1's band is **4h only**, so D3's grid choice survives on a different and stated reason.
> - **Two bookkeeping errors**: the spec's claim about the catalog was already discharged by its own commit `523a4034`, and `T0023` is already `partial` so the closeout task's status flip was a no-op — its real work is the `## Done so far` entry and the next-steps trim.
>
> **Round 2** (contract re-pin) found the spec promised a family the plan never built: the ratio carry-through and the `binperp_` prefix (now Task 5), `_validate_levels` declared but never implemented (now Task 1 Step 3b), and D10's panel-start proof mapped to no task (now Task 7 Step 4).
>
> **Round 3** (two lens reviews) found one defect shape running through both artefacts — **a guard whose fixture the defect cannot move**:
>
> - **`[-1]`-only assertions**, in six of the plan's feature tests. At the final index a window that peeks one bar ahead clamps to the correct window, so a look-ahead passes them all. Every one now asserts the **full output list**, and Tasks 3 and 4 each carry the truncating-prefix property over the functions they add — Task 2's covered `align_asof` alone. **Proven on both arms**: four look-ahead defects (a `+1` on the z-score slice end, a forward-summing carry, a centred OI window, a momentum reading `k+1`) each trip the prefix test; two warm-up defects (`0.0` head, copied from `cli/features/momentum.py`) trip the full-list assertions; the causal reference passes all twelve.
> - **`_validate_levels` refused `0.0`, and the substrate publishes it** — 2,329 rows of `sum_open_interest` and 45 of `sum_taker_long_short_vol_ratio`. Spec D5 now rules on both, in opposite directions, and the plan carries the split: OI zeros are venue holes mapped to `None` by `oi_levels_from_raw`, ratios are validated as finite-or-null.
> - **Three claims measured false or unmeasurable**: the ratio docstring's "87.3 % null across 2022" holds for two of the four columns and overstates `count_long_short_ratio` 17×; `coverage_by_year`'s 2-tuple could not carry D6's two timestamps; and Task 7 Step 4's data gate pointed at `data/derivatives-oi`, which is absent here, so the one substrate-reading guard would have skipped on the machine that is its only home.
>
> **Round 4** (scoped to the mechanisms round 3 introduced) found round 3's own repair carrying a false premise and an unrunnable step:
>
> - **The evidential case for `oi_levels_from_raw` was false at population scale.** Round 3 generalised one BTCUSDT row into "on those stamps the account-ratio columns are null". Measured across all ten files: of the 2,329 `sum_open_interest == 0.0` rows, **none** has all four ratio columns null and only **338** have the three account ratios null. The mapping stands on a reason that survives measurement — a zero level is unusable whatever wrote it, because `log(0)` and a division by zero sit on real rows — and spec D5, this plan and `docs/reference/data-catalog-full.md` now say the provenance is not established and that the detection predicate is the zero alone.
> - **Both guard proofs were hand-rolled mutate-and-restore loops, scheduled BEFORE their task's commit.** `agent-ops.md` mandates `infra/scripts/mutate-probe.sh`, which refuses a dirty tree — and whose `git checkout --` restore, run at that point, would have destroyed the task's uncommitted implementation, which no snippet here can regenerate. Each proof now follows its own commit as per-test-scoped probes with a control and a mutation.
> - **The closed-window drift guard pinned one of the two OI columns D5 rules on**, and the two zero sets nest rather than coincide: 101 rows carry a zero `sum_open_interest_value` against a healthy `sum_open_interest`. Both columns are asserted now.
> - **`oi_levels_from_raw`'s mitigation rested on a `_validate_levels` call nothing required or proved.** Task 4 Step 3 mandates the call in all three OI functions, a new test demands `FeatureError` from each on a raw `0.0`, and Step 6's probe (c) proves the calls are live. Folded alongside: `coverage_by_year`'s length-mismatch and empty-year contracts, previously unspecified.


**Goal:** Build the funding + OI feature harness B2 will be measured with, proven on known answers before any verdict counts.

**Architecture:** Pure functions on plain Python lists in `cli/features/derivatives.py`, matching the existing `cli/features/` convention in the three traits that transfer — keyword-only params after the data, a docstring stating the causality property, `_validate_*` raising `FeatureError` — and **deliberately NOT in output length**: the existing five return `len(prices) - 1` because they align to `returns_from_prices`, while these align to the input grid and return `len(input)` with `None` where undefined (spec D7). No polars, no frames, no I/O **inside the module** — the substrate readers already exist in `cli/derivatives/`. Two consequences the plan owns rather than leaves implicit. The glue that turns those readers' frames into these lists, builds the 1h/4h grid, and ships each frame with its `coverage_by_year` summary is **out of scope** (spec D6 / `## Out of scope`) and registered on `T0023` at Task 7 Step 3. And the one test that does read the substrate — Task 7 Step 4's data-gated panel-start and venue-hole assertions — lives in `tests/test_derivatives_oi.py`, outside this module, which is why it can use polars.

**Tech Stack:** Python 3.14, stdlib only for the feature math; pytest.

**Spec:** `docs/specs/00110-b2-derivatives-feature-harness-design.md`

## Global Constraints

- **The fenced blocks are CONTENT, not formatting.** None is commit-gate-clean, so the first `pre-commit run` of each task will rewrite what you pasted and report **Failed**; that is the hook doing its job. Re-run until clean, stage what it rewrote, then commit — never `--no-verify`.

- **Causality is the product.** Every feature at index `k` reads only inputs at index `<= k`. Each function's docstring says so in the house form — `… uses only x[<= k]` is in all five existing `cli/features/` docstrings, the `-> no look-ahead` suffix in one (`momentum.py`); write both here.
- **Every task that adds a windowed function carries its own truncating-prefix test.** For each function `f` it adds and every prefix length `n >= 2`, `f(x[:n], **kw) == f(x, **kw)[:n]`. Task 2's covers `align_asof` and nothing else, so Tasks 3 and 4 each schedule their own — an `[-1]`-only assertion cannot see a look-ahead, because at the final index a window peeking one bar ahead clamps to the correct window. Spec D10.
- **No imputation, ever.** A null input yields a null output (`float | None`). Never 0.0, never a trailing mean. Spec D5.
- **An undefined window is `None`, never `0.0` — a separate rule from the one above.** The head of every windowed output is `None` until the window is full. `cli/features/momentum.py` fills its warm-up with `0.0`; that convention does **not** carry here, because these return `float | None` and a `0.0` z-score reads as *exactly average* rather than *unknown*. Spec D7.
- **A raw `0.0` in `sum_open_interest*` is a venue hole, not a level** — spec D5's shorthand for *a zero in a level column that cannot be used as a level*, naming the effect rather than a confirmed venue incident. Measured: `sum_open_interest` carries **2,329** and `sum_open_interest_value` **2,430**, the first set nested inside the second. It maps to `None` before validation, and **the predicate is the zero alone** — the account-ratio columns do not mark those stamps (spec D5). A `0.0` in `sum_taker_long_short_vol_ratio` is the opposite — a real all-sell bar, 45 measured rows, none of them on a zero-OI stamp — so the ratio family is validated finite-or-null, never positive.
- **Windows are pre-registered at 30 days.** They are function parameters with no defaults baked into the math; the 30-day pre-registration lives in the spec, not in the code. Tuning one is a trial (spec D7).
- **Funding rates are SIGNED.** `_validate_prices` rejects `<= 0` and must not be used for funding. Task 1 adds `_validate_rates`.
- **Emitted column names are prefixed `binperp_`** (spec D8) — these describe Binance perpetuals, not Kraken spot.
- **This harness spends no trial budget.** It registers nothing.
- **A `_validate_*` a task imports is CALLED by every function that consumes it, and a test in that task demands the refusal.** An imported-but-uncalled validator is invisible to the commit gate — `ruff.toml` sets `select = ["I"]`, isort only, so F401 never fires (verified: an unused import passes `ruff check` inside this repo) — and so is not a guard, and the failure is silent where the bad input is still arithmetically valid — a `0.0` level has a mean and a stdev. **The family is every function whose validator call is not pinned by a code snippet here**: Task 3's `funding_zscore` / `funding_sign_persistence` / `funding_accrued_carry` on `_validate_rates`, and Task 4's `oi_log_delta` / `oi_zscore` / `oi_momentum` on `_validate_levels` — six, each covered by its task's refusal test. `ratio_features` is not a member: Task 5 pins its `_validate_rates` call in the snippet. `oi_levels_from_raw` is the one deliberate non-caller (Task 4 Interfaces).
- **Every guard proof runs through `infra/scripts/mutate-probe.sh`, on a clean tree AFTER its task's commit** — never a hand-rolled sed-and-`git checkout` loop (`.claude/rules/agent-ops.md`). The script purges `__pycache__` and exports `PYTHONDONTWRITEBYTECODE=1` (a same-second edit otherwise re-runs a stale `.pyc` and every verdict is a lie), requires the probe to PASS unmutated (rc 7) and the control to FAIL (rc 5), refuses a no-op sed (rc 6), and restores byte-identically. It **refuses a dirty worktree** (rc 3) — hence after the commit, and never before it: its restore is `git checkout --`, which run against an uncommitted implementation destroys the whole task, and no snippet in Tasks 3 or 4 could regenerate it. This shell is zsh: pass the probe command as an ARRAY expanded `"${VAR[@]}"`, never an unquoted scalar, which stays one word and fails the baseline. **Scope every probe with `-k` to ONE test** and check `--collect-only` selects exactly it — a whole-file probe prints `KILLED` without saying which test bit, and the point of each proof here is which one did.

---

### Task 1: Two validators — signed, and positive-nullable

**Files:**
- Modify: `cli/features/_validate.py`
- Create (test): `tests/test_features_validate.py`

**Interfaces:**
- Produces: `_validate_rates(name, values)` — finite floats of ANY sign, or `None`.
- Produces: `_validate_levels(name, values)` — finite floats `> 0`, or `None`. Needed because `_validate_prices` raises on `None` and OI features must propagate it (spec D5).

**`> 0` is deliberate and stays**, even though the substrate publishes 2,329 rows of `sum_open_interest == 0.0`: those are venue holes, and Task 4's `oi_levels_from_raw` maps them to `None` *before* this validator sees them (spec D5). A `0.0` reaching `_validate_levels` is a caller that skipped the mapping — which is exactly what it should refuse. The four **ratio** columns are the opposite case and do **not** use this validator: `sum_taker_long_short_vol_ratio` carries 45 real zeros, so Task 5 gates them with `_validate_rates`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from cli.features._validate import _validate_levels, _validate_rates
from cli.features.errors import FeatureError

def test_validate_rates_accepts_negative_and_none():
    _validate_rates("funding", [-0.0003, 0.0, None, 0.0007])

def test_validate_rates_rejects_nonfinite_and_bool():
    for bad in ([1.0, float("nan")], [1.0, float("inf")], [1.0, True]):
        with pytest.raises(FeatureError):
            _validate_rates("funding", bad)

def test_validate_levels_accepts_positive_and_none_but_not_zero_or_negative():
    """`0.0` is rejected ON PURPOSE. Spec 00110 D5 rules a zero open interest a venue hole, which
    `oi_levels_from_raw` maps to `None` before this runs, so a `0.0` arriving here is a caller that
    skipped the mapping. Do not relax this to `>= 0`: `oi_log_delta` would then take `log(0)` and
    `oi_momentum` would divide by zero."""
    _validate_levels("oi", [100.0, None, 110.0])
    for bad in ([100.0, 0.0], [100.0, -1.0], [100.0, float("nan")]):
        with pytest.raises(FeatureError):
            _validate_levels("oi", bad)
```

`test_validate_rates_accepts_negative_and_none` already carries a `0.0`, so the ratio family's "a zero is a reading" contract needs no extra test here — the guard that bites if Task 5 reaches for the wrong validator is `test_ratio_features_carry_nulls_and_real_zeros_through_untouched`, which feeds `ratio_features` a `0.0`.

- [ ] **Step 2: Run it, expect ImportError / failure**

Run: `uv run pytest tests/test_features_validate.py -v`

- [ ] **Step 3: Implement**

```python
def _validate_rates(name: str, values: list[float | None]) -> None:
    """Signed-value validator: funding rates go negative, so `_validate_prices` (which rejects
    <= 0) must not be used for them. `None` is allowed and propagates (spec 00110 D5)."""
    if not isinstance(values, list) or len(values) < 2:
        raise FeatureError(f"{name} must be a list of >= 2 values, got {values!r}")
    for v in values:
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise FeatureError(f"{name} must be finite numbers or None, got {v!r}")
```

- [ ] **Step 3b: Implement `_validate_levels`**

```python
def _validate_levels(name: str, values: list[float | None]) -> None:
    """Positive-and-nullable: an OI LEVEL is strictly positive, but `_validate_prices` raises on
    `None` and these features must propagate it (spec 00110 D5). The substrate's `0.0` open-interest
    rows are venue holes, not levels; `oi_levels_from_raw` maps them to `None` before this runs, so
    a `0.0` here is a caller that skipped that step. Ratios are NOT levels -- a ratio may
    legitimately be zero, so they are gated by `_validate_rates`."""
    if not isinstance(values, list) or len(values) < 2:
        raise FeatureError(f"{name} must be a list of >= 2 values, got {values!r}")
    for v in values:
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0:
            raise FeatureError(f"{name} must be finite positive numbers or None, got {v!r}")
```

- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): signed and positive-nullable validators, because funding goes negative and OI goes null`

---

### Task 2: As-of alignment, and the look-ahead property test

**Files:**
- Create: `cli/features/derivatives.py`
- Create (test): `tests/test_features_derivatives.py`

**Interfaces:**
- Produces: `align_asof(source_ts, source_values, grid_ts) -> list[float | None]` — for each grid stamp `g`, the value of the latest source row with `ts <= g`, else `None`. Both inputs must be sorted ascending; forward-fill only, never interpolate (spec D2).

- [ ] **Step 1: Write the failing tests — including the guard the spec exists for**

```python
import pytest
from datetime import datetime, timezone

from cli.features.derivatives import align_asof

UTC = timezone.utc
def _t(h): return datetime(2022, 1, 1, h, tzinfo=UTC)

def test_align_asof_forward_fills_and_never_interpolates():
    src_ts = [_t(0), _t(8)]
    src_v = [1.0, 2.0]
    grid = [_t(0), _t(4), _t(8), _t(12)]
    assert align_asof(src_ts, src_v, grid) == [1.0, 1.0, 2.0, 2.0]

def test_align_asof_is_none_before_the_first_source_row():
    assert align_asof([_t(8)], [2.0], [_t(0), _t(8)]) == [None, 2.0]

def test_a_truncated_prefix_reproduces_the_full_run_bit_for_bit():
    """The look-ahead guard (spec D2/D10), in the form that actually bites.

    An earlier draft appended FUTURE source rows beyond the grid's last stamp and asserted the
    result was unchanged. The contract pin showed that test passes on a deliberate backward-fill
    defect (`if t >= g: return x`, which reads the NEXT source row) as readily as on the correct
    implementation, because rows past the grid's end cannot move any value under either semantics.

    This form truncates instead: recompute over `grid[:k]` using only source rows stamped at or
    before `grid[k-1]`, and demand the prefix match the full run's. The defect first mismatches at **k=2** (`[1.0, None]` vs `[1.0, 2.0]`); the correct implementation passes at
    every k. An earlier draft of this docstring said k=1, taken from a review report rather than run."""
    src_ts, src_v = [_t(0), _t(8)], [1.0, 2.0]
    grid = [_t(0), _t(4), _t(8)]
    full = align_asof(src_ts, src_v, grid)
    for k in range(1, len(grid) + 1):
        cutoff = grid[k - 1]
        visible = [(t, v) for t, v in zip(src_ts, src_v) if t <= cutoff]
        prefix = align_asof([t for t, _ in visible], [v for _, v in visible], grid[:k])
        assert prefix == full[:k], f"prefix at k={k} disagrees with the full run"
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_features_derivatives.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

from datetime import datetime

from cli.features.errors import FeatureError


def align_asof(
    source_ts: list[datetime],
    source_values: list[float | None],
    grid_ts: list[datetime],
) -> list[float | None]:
    """As-of forward fill onto a decision grid: out[k] is the value of the latest source row with
    ts <= grid_ts[k], or None before the first such row. Uses only source rows at or before each
    grid stamp -> no look-ahead. Never interpolates: an interpolated value is a number the venue
    never showed (spec 00110 D2)."""
    if len(source_ts) != len(source_values):
        raise FeatureError(
            f"source_ts and source_values must be equal length, got {len(source_ts)} and {len(source_values)}"
        )
    if any(b < a for a, b in zip(source_ts, source_ts[1:])):
        raise FeatureError("source_ts must be sorted ascending")
    if any(b < a for a, b in zip(grid_ts, grid_ts[1:])):
        raise FeatureError("grid_ts must be sorted ascending")
    out: list[float | None] = []
    i = 0
    carried: float | None = None
    for g in grid_ts:
        while i < len(source_ts) and source_ts[i] <= g:
            carried = source_values[i]
            i += 1
        out.append(carried)
    return out
```

- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): as-of alignment, with the look-ahead guard as a property test`

---

### Task 3: Funding features

**Files:**
- Modify: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Consumes: `_validate_rates` from Task 1. **This task owns the import** — put `from cli.features._validate import _validate_rates` in `cli/features/derivatives.py` at Step 3; Task 5 reuses it and adds none of its own.
- Produces: `funding_zscore(rates, *, window)` and `funding_accrued_carry(rates, *, window)` — `list[float | None]`; `funding_sign_persistence(rates)` — `list[int | None]` (a run length is a count). All three are **the same length as the input** and `None` where an input is null; the two windowed forms are additionally `None` until the window is full (spec D7 — these are two different rules; see Global Constraints). `funding_sign_persistence` takes no window and so has no warm-up head.
- **Sign of zero, pinned by spec D7:** sign is drawn from `{-1, 0, +1}`, so a `0.0` print breaks a positive run and starts its own run at 1. 659 of the 68,281 real prints are exactly `0.0`, so this is not a corner case.

- [ ] **Step 1: Write the failing tests**

```python
from cli.features.derivatives import funding_accrued_carry, funding_sign_persistence, funding_zscore
from cli.features.errors import FeatureError

def test_funding_zscore_recovers_a_planted_value():
    """Planted signal (spec D10) under D7's pinned window: inclusive trailing window ending at k,
    sample stdev. Nine identical prints then one outlier scores exactly 2.8460498941515410 --
    verified by computation, not asserted as a threshold. An earlier draft asserted `> 3.0`, which
    no window definition can produce: population stdev gives exactly 3.0, exclusive is undefined.

    The assertion is the FULL list, not `z[-1]`: it pins the length, the nine-`None` warm-up head
    that separates "undefined" from "exactly average", and the value -- and a `[-1]`-only form
    passes under a window that peeks one bar ahead, because at the last index it clamps."""
    rates = [0.0001] * 10 + [0.0009]
    assert funding_zscore(rates, window=10) == [None] * 9 + [0.0, pytest.approx(2.8460498941515410)]

def test_funding_zscore_of_a_constant_series_is_zero_not_spurious():
    assert funding_zscore([0.0001] * 12, window=10) == [None] * 9 + [0.0, 0.0, 0.0]

def test_funding_zscore_propagates_null():
    assert funding_zscore([0.0001] * 10 + [None], window=10) == [None] * 9 + [0.0, None]

def test_sign_persistence_counts_consecutive_same_sign_prints():
    """A zero print is its own sign (spec D7), and a null breaks the run without joining one."""
    assert funding_sign_persistence([0.1, 0.2, 0.0, -0.1, -0.2]) == [1, 2, 1, 1, 2]
    assert funding_sign_persistence([0.1, 0.2, None, -0.1, -0.2]) == [1, 2, None, 1, 2]

def test_accrued_carry_sums_the_window():
    assert funding_accrued_carry([1.0, 2.0, 3.0, 4.0], window=2) == [None, 3.0, 5.0, 7.0]
    assert funding_accrued_carry([1.0, 2.0, None, 4.0, 5.0], window=2) == [None, 3.0, None, None, 9.0]

def test_every_funding_feature_refuses_a_nonfinite_rate():
    """The other half of `_validate_rates` being a guard rather than an import: it must be CALLED,
    by all three. A NaN would otherwise propagate through every arithmetic path silently, and a NaN
    z-score compares unequal to everything -- including itself -- so no downstream assertion catches
    it either. The fixture is otherwise a healthy signed series, so only the NaN can be what fires."""
    for f, kw in ((funding_zscore, {"window": 3}), (funding_sign_persistence, {}), (funding_accrued_carry, {"window": 3})):
        with pytest.raises(FeatureError):
            f([0.0003, float("nan"), 0.0004, 0.0009], **kw)

def test_every_funding_feature_reproduces_itself_on_a_truncated_prefix():
    """The causality guard for this task's three functions (spec D2/D10), in the only form that
    bites. `test_a_truncated_prefix_reproduces_the_full_run_bit_for_bit` has the same property for
    `align_asof`; it covers nothing here.

    Every assertion above is a fixed-input equality, and a window that reads one bar into the
    future agrees with the causal form at the last index -- so recompute over each prefix and
    demand the answers match. The fixture is deliberately non-degenerate: distinct magnitudes,
    both signs, and a zero, so no two candidate window offsets coincide."""
    rates = [0.0003, -0.0001, 0.0004, 0.0, 0.0009, -0.0002, 0.0011, 0.0005]
    cases = (
        (funding_zscore, {"window": 3}),
        (funding_sign_persistence, {}),
        (funding_accrued_carry, {"window": 3}),
    )
    for f, kw in cases:
        full = f(rates, **kw)
        for n in range(2, len(rates) + 1):
            assert f(rates[:n], **kw) == full[:n], f"{f.__name__} disagrees at n={n}"
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement all three**, each with a causality docstring in the house form. Add `from cli.features._validate import _validate_rates` and the `math` / `statistics` imports the z-score needs — `cli/features/derivatives.py` carries only Task 2's `FeatureError` import at this point. **All three CALL `_validate_rates("rates", rates)` as their first statement**, in the house form `cli/features/momentum.py` uses — validators first, before any arithmetic (Global Constraints).
- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): funding z-score, sign persistence and accrued carry`
- [ ] **Step 6: Prove the prefix guard is not inert — AFTER the commit, through `infra/scripts/mutate-probe.sh`** (contract in Global Constraints).

The defect is the forward-summing window: `funding_accrued_carry` must sum the `window` prints **ending at** `k`, so make it sum the `window` prints **starting at** `k`. This task's implementation text is not pinned here, so **derive the sed from the code you just committed** and prove it addresses exactly one line before any verdict counts. **Derive it from the line that SUMS the window, not from the window slice**: the slice is the same expression in `funding_zscore` and `funding_accrued_carry`, so `grep -c` on it prints 2 and the uniqueness check cannot pass, while the summation line is unique to each function. `grep -c '<the summing line you are replacing>' cli/features/derivatives.py` must print `1`.

```bash
uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider --collect-only -k funding_feature_reproduces   # expect exactly 1
uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider --collect-only -k accrued_carry_sums          # expect exactly 1
PREFIX=(uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider -k funding_feature_reproduces)
FIXED=(uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider -k accrued_carry_sums)
infra/scripts/mutate-probe.sh --file cli/features/derivatives.py \
  --control 's/^def funding_accrued_carry(/def funding_accrued_carryz(/' \
  --mutation '<the forward-summing slice, one line, verified by the grep above>' -- "${PREFIX[@]}"
infra/scripts/mutate-probe.sh --file cli/features/derivatives.py \
  --control 's/^def funding_accrued_carry(/def funding_accrued_carryz(/' \
  --mutation '<the same sed>' -- "${FIXED[@]}"
```

Expected: `mutate-probe: KILLED (control proven, tree restored byte-identically)` **both times** — the probes are scoped one test each, so each `KILLED` names the test that bit rather than leaving the pair to share credit. A `SURVIVED` on `PREFIX` means the truncating-prefix property is inert; stop and re-read `test_every_funding_feature_reproduces_itself_on_a_truncated_prefix` rather than weakening it. Then re-run either array on the restored tree and read PASS — that green is the true-positive a permanently-refusing guard would not produce.

---

### Task 4: OI features

**Files:**
- Modify: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Consumes: `_validate_levels` from Task 1. **This task owns the import** — add `from cli.features._validate import _validate_levels` to the `_validate_rates` import Task 3 put in `cli/features/derivatives.py`.
- Produces: `oi_log_delta(levels)`, `oi_zscore(levels, *, window)`, `oi_momentum(levels, *, lookback)` — `list[float | None]`, **the same length as the input**, `None` where an input is null **and** `None` where the window is not yet full (spec D7 — two different rules; see Global Constraints). An OI *level* is strictly positive **and** nullable, which `_validate_prices` cannot express — it raises `FeatureError` on `None` (verified). Task 1 therefore adds `_validate_levels` alongside `_validate_rates`: finite, `> 0`, or `None`.
- Produces: `oi_levels_from_raw(values) -> list[float | None]` — maps the substrate's `0.0` open-interest placeholders to `None` and passes everything else through. Spec D5 rules these not levels: `sum_open_interest` is exactly `0.0` on **2,329** rows and `sum_open_interest_value` on **2,430**, the first set nested inside the second, every symbol represented in both. **The predicate is the zero itself.** What wrote it is not established, and the account ratios do not mark it: of the 2,329 rows **none** has all four ratio columns null and only **338** have the three account ratios null, so a detection keyed on ratio absence would miss **1,991** of them (spec D5). The reason to map rather than keep is arithmetic, not provenance — `oi_log_delta` would take `log(0)` and `oi_momentum` would divide by it — so **without it the harness raises `FeatureError` on its own substrate at first real use**, and the cheapest-looking repair at that point, dropping or filling those rows, is the imputation spec D5 forbids. Mapping to `None` is the opposite of imputation: it removes a reading rather than inventing one. It runs **before** validation and so validates nothing itself — calling `_validate_levels` inside it would reject the very rows it exists to map.

- [ ] **Step 1: Write the failing tests**

```python
import math
from cli.features.derivatives import oi_levels_from_raw, oi_log_delta, oi_momentum, oi_zscore
from cli.features.errors import FeatureError

def test_oi_log_delta_is_the_log_ratio_starts_none_and_propagates_null():
    assert oi_log_delta([100.0, 110.0, None, 120.0]) == [
        None, pytest.approx(math.log(110.0 / 100.0)), None, None
    ]

def test_oi_zscore_recovers_a_planted_spike():
    """Same pinned definition, same arithmetic as the funding case -- and the same full-list
    assertion, which pins the nine-`None` warm-up head a `0.0`-filling implementation would
    replace with `exactly average`."""
    assert oi_zscore([100.0] * 10 + [180.0], window=10) == [None] * 9 + [
        0.0, pytest.approx(2.8460498941515410)
    ]

def test_oi_zscore_propagates_null():
    assert oi_zscore([100.0] * 10 + [None], window=10) == [None] * 9 + [0.0, None]

def test_oi_momentum_pins_its_head_its_base_index_and_its_nulls():
    """Keep every level distinct: `lookback` 1, 2 and 3 then give three different answers, so an
    off-by-one base index cannot hide. A fixture whose head is constant makes them agree."""
    assert oi_momentum([100.0, 110.0, 121.0, 125.0], lookback=2) == [
        None, None, pytest.approx(0.21), pytest.approx(0.13636363636363646)
    ]
    assert oi_momentum([100.0, 110.0, None, 125.0, 140.0], lookback=2) == [
        None, None, None, pytest.approx(0.13636363636363646), None
    ]

def test_oi_levels_from_raw_maps_the_venue_hole_to_null():
    """Spec 00110 D5: a `0.0` open interest is a hole the venue wrote as a zero, not a market with
    no open interest. Without this mapping `_validate_levels` raises on the canonical substrate at
    first real use, and the cheapest-looking repair there is the imputation D5 forbids."""
    assert oi_levels_from_raw([100.0, 0.0, 110.0, None]) == [100.0, None, 110.0, None]

def test_every_oi_feature_refuses_a_raw_zero_instead_of_scoring_it():
    """`oi_levels_from_raw` is a step a caller has to remember, and these three assertions are what
    make forgetting it loud rather than silent. `oi_zscore` is why all three are asserted and not
    just the one where a bad level is obvious: a fabricated zero is a perfectly good number to take
    a mean and a sample stdev over, so an unguarded z-score returns a finite, plausible, large
    negative reading -- exactly what a de-risking trigger acts on. And `FeatureError` specifically:
    a bare `ValueError` out of `log(0)` is the contract failing too, not the contract holding."""
    for f, kw in ((oi_log_delta, {}), (oi_zscore, {"window": 3}), (oi_momentum, {"lookback": 2})):
        with pytest.raises(FeatureError):
            f([100.0, 0.0, 110.0, 120.0], **kw)

def test_every_oi_feature_reproduces_itself_on_a_truncated_prefix():
    """The causality guard for this task's three windowed functions (spec D2/D10). See
    `test_every_funding_feature_reproduces_itself_on_a_truncated_prefix` for why `[-1]` cannot carry
    it. The fixture rises and falls so no two candidate window offsets coincide."""
    levels = [100.0, 104.0, 99.0, 130.0, 128.0, 90.0, 155.0, 151.0]
    cases = (
        (oi_log_delta, {}),
        (oi_zscore, {"window": 3}),
        (oi_momentum, {"lookback": 2}),
    )
    for f, kw in cases:
        full = f(levels, **kw)
        for n in range(2, len(levels) + 1):
            assert f(levels[:n], **kw) == full[:n], f"{f.__name__} disagrees at n={n}"
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement all four**, adding `_validate_levels` to the import Task 3 created. **All three windowed functions CALL `_validate_levels("levels", levels)` as their first statement**, in the house form `cli/features/momentum.py` uses — validators first, before any arithmetic. An imported-but-uncalled validator is invisible to the commit gate — `ruff.toml` sets `select = ["I"]`, isort only, so F401 never fires (verified: an unused import passes `ruff check` inside this repo) — and so is not a guard, and the call in `oi_zscore` is the one that carries `oi_levels_from_raw`'s whole mitigation: a fabricated `0.0` inside a window is a perfectly good number to take a mean and a sample stdev over, so without it the function returns a finite, plausible z-score and raises nothing. `oi_levels_from_raw` is the deliberate exception and validates nothing (see Interfaces).
- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): OI log-delta, z-score, momentum, and the zero-is-a-hole mapping`
- [ ] **Step 6: Prove all three guards bite, on defects that separate them — AFTER the commit, through `infra/scripts/mutate-probe.sh`** (contract in Global Constraints). Neither the implementation nor its line numbers are pinned here, so derive (a)'s and (b)'s mutation seds from the code you committed and prove each addresses exactly one line (`grep -c` prints `1`) before trusting a verdict. (c)'s sed is pinned and deliberately addresses **three** — the call sites, never the import, which reads `_validate_levels,` without a paren.

```bash
uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider --collect-only -k oi_momentum_pins    # expect exactly 1
uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider --collect-only -k oi_feature_reproduces   # expect exactly 1
uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider --collect-only -k oi_feature_refuses      # expect exactly 1
HEAD_T=(uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider -k oi_momentum_pins)
PREFIX=(uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider -k oi_feature_reproduces)
ZERO=(uv run pytest tests/test_features_derivatives.py -q -p no:cacheprovider -k oi_feature_refuses)
CTRL='s/^def oi_momentum(/def oi_momentumz(/'
# (a) the look-ahead: oi_momentum's numerator reads k+1, clamped at the end
infra/scripts/mutate-probe.sh --file cli/features/derivatives.py --control "$CTRL" \
  --mutation '<numerator -> levels[min(len(levels) - 1, k + 1)]>' -- "${PREFIX[@]}"
infra/scripts/mutate-probe.sh --file cli/features/derivatives.py --control "$CTRL" \
  --mutation '<the same sed>' -- "${HEAD_T[@]}"
# (b) the warm-up head: 0.0 where the contract says None -- the cli/features/momentum.py form
infra/scripts/mutate-probe.sh --file cli/features/derivatives.py --control "$CTRL" \
for (b) count over the FUNCTION, not the file — `sed -n '/^def oi_momentum(/,$p' cli/features/derivatives.py | grep -c 'out.append(None)'` must print 1; a bare `out.append(None)` appears in several functions, so a file-wide count cannot be 1.0>' -- "${HEAD_T[@]}"
infra/scripts/mutate-probe.sh --file cli/features/derivatives.py --control "$CTRL" \
  --mutation '<the same sed>' -- "${PREFIX[@]}"
# (c) the validator calls: swap all three for the signed validator, which accepts 0.0
grep -c '_validate_levels(' cli/features/derivatives.py   # expect exactly 3 — the call sites, not the import
infra/scripts/mutate-probe.sh --file cli/features/derivatives.py \
  --control 's/^def oi_zscore(/def oi_zscorez(/' \
  --mutation 's/_validate_levels(/_validate_rates(/' -- "${ZERO[@]}"
```

Expected, in order: **KILLED, KILLED, KILLED, SURVIVED, KILLED** — and **assert each verdict, never read the five lines by eye**. `mutate-probe.sh` ends on `[[ "$verdict" == KILLED || "$verdict" == SURVIVED ]]`, which is true for BOTH, so the script exits 0 whichever way a probe lands: a `SURVIVED` where `KILLED` was expected leaves an inert causality guard behind a green step. Label and grep each one — `echo "== (a) PREFIX"` before the invocation, then pipe it through `| tee /dev/stderr | grep -q 'mutate-probe: KILLED'` (or `SURVIVED` for (d)) so a wrong verdict fails the step. (a) is why the prefix property is not redundant with the full-list assertions; (b)'s `SURVIVED` is the finding, not a failure — a `0.0` head is perfectly causal, so the prefix test is blind to it and the full-list assertions are what catch it. (c) proves the `_validate_levels` calls are live in all three functions at once — its sed carries no line address, so it rewrites every call site. The baseline is half the proof: the probe passes unmutated only if all three already raise `FeatureError` on a `0.0`. The mutation is the other half: `_validate_rates` accepts `0.0`, so the swap makes `oi_zscore` score the fabricated zero silently and turns the other two's refusal into a raw `ValueError`/`ZeroDivisionError`, which is not the contract's `FeatureError` — proving the refusal came from the validator call and not from incidental arithmetic. A `SURVIVED` on (a), (c), or the second (b) probe means the named guard is inert; stop and re-read it rather than weakening it.

---

### Task 5: The ratio family, and the `binperp_` naming

**Files:**
- Modify: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Produces: `ratio_features(ratios: dict[str, list[float | None]]) -> dict[str, list[float | None]]` — carries the four Binance ratio columns through unchanged, re-keyed with the `binperp_` prefix (spec D8). Null-propagating by construction: a carried column is the same list.

This family is small but it is the only **null-bearing** one, so it is what exercises D5's no-imputation rule against the real data shape. It also lands the `binperp_` prefix, which spec D8 requires and which no other task emits.

**The 2022 hole is per-column, not uniform.** Measured panel-wide over 2022's 1,051,199 rows: `count_toptrader_long_short_ratio` **87.24 %** null, `sum_toptrader_long_short_ratio` **87.24 %**, `sum_taker_long_short_vol_ratio` **35.03 %**, `count_long_short_ratio` **5.09 %**. A single "87.3 % in these columns" overstates the hole 17× for `count_long_short_ratio`, which is 94.9 % *present* through 2022 and is the one ratio usable across that regime — the figures belong in spec D5 and here, not in a shipped docstring, where a substrate refresh would rot them silently.

**Ratios are gated by `_validate_rates`, not `_validate_levels`** — `sum_taker_long_short_vol_ratio` is exactly `0.0` on 45 real rows (all-sell bars, every one on a healthy-OI stamp), which the positive-level validator would reject. Spec D5.

- [ ] **Step 1: Write the failing tests**

```python
from cli.features.derivatives import ratio_features

_RATIOS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)

def test_ratio_features_prefix_every_column_with_its_venue():
    out = ratio_features({name: [1.0, 2.0] for name in _RATIOS})
    assert set(out) == {f"binperp_{name}" for name in _RATIOS}

def test_ratio_features_carry_nulls_and_real_zeros_through_untouched():
    """Spec 00110 D5: no imputation. A null in, a null out -- never 0.0, never a trailing mean.
    And a `0.0` in, a `0.0` out: D5 rules a ratio zero a real reading (an all-sell bar), unlike a
    zero in `sum_open_interest`, which is a venue hole."""
    out = ratio_features({name: [1.0, None, 0.0, 3.0] for name in _RATIOS})
    for name in _RATIOS:
        assert out[f"binperp_{name}"] == [1.0, None, 0.0, 3.0]

def test_ratio_features_rejects_an_unknown_column():
    import pytest
    from cli.features.errors import FeatureError
    with pytest.raises(FeatureError):
        ratio_features({"not_a_ratio": [1.0, 2.0]})

def test_ratio_features_rejects_a_dropped_column():
    """The other half of the guard. Without it a caller that lost a column gets a silently smaller
    frame, and `coverage_by_year` reports nothing about a column that is not there."""
    import pytest
    from cli.features.errors import FeatureError
    with pytest.raises(FeatureError):
        ratio_features({name: [1.0, 2.0] for name in _RATIOS[:3]})
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_features_derivatives.py -v`

- [ ] **Step 3: Implement**

```python
_RATIO_COLUMNS: tuple[str, ...] = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


def ratio_features(ratios: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
    """Carry Binance's four ratio columns through under `binperp_` names. No arithmetic and no
    imputation: these columns carry genuine venue gaps, concentrated in one year and differing by
    an order of magnitude between columns, and filling one would manufacture a reading the venue
    never published (spec 00110 D5). Call `coverage_by_year` to see the shape for the substrate in
    hand rather than trusting a figure written here. All four are required: a caller that dropped
    one would otherwise get a silently smaller frame. The prefix is spec D8 -- the features
    describe Binance perpetuals, not the Kraken spot book they will sit beside."""
    unknown = set(ratios) - set(_RATIO_COLUMNS)
    if unknown:
        raise FeatureError(f"unknown ratio column(s): {sorted(unknown)}")
    missing = set(_RATIO_COLUMNS) - set(ratios)
    if missing:
        raise FeatureError(f"missing ratio column(s): {sorted(missing)}")
    for name, values in ratios.items():
        # A ratio is finite or null -- never gated as a positive level: a zero is a real all-sell
        # bar, while a zero OI is a venue hole (spec 00110 D5).
        _validate_rates(name, values)
    return {f"binperp_{name}": list(values) for name, values in ratios.items()}
```

- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): the four ratios carried through under binperp_, nulls intact`

---

### Task 6: Per-year coverage, so a trial cannot run blind

**Files:**
- Modify: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Produces: `YearCoverage(non_null, total, first_non_null, last_non_null)` — a `NamedTuple`, so it still compares equal to a plain tuple in a test — and `coverage_by_year(ts, values) -> dict[int, YearCoverage]`. Spec D6 names four things per column and this carries all four: the count, the two timestamps, and the null fraction, which is **derived** (`1 - non_null / total`) rather than stored, so the two cannot disagree. Two behaviours the widened return type would otherwise leave open: it raises `FeatureError` when `ts` and `values` differ in length — `align_asof`'s rule, and without it a `zip`-based implementation truncates to the shorter input, under-counts `total` and makes the derived fraction wrong with nothing raising — and a year whose `non_null` is `0` reports `None` for both timestamps rather than taking a `min()` over an empty sequence.

**Why the timestamps, and not just the count.** A `(non_null, total)` pair cannot tell a late start from an interior outage — the distinction D5 had to reopen the parquet to settle, and the one deciding whether a 2022 CPCV fold is unusable or merely thin. Without them the round trip to the substrate that D6 exists to remove is still required.

**Nothing in this plan calls `coverage_by_year`.** That is deliberate and recorded: binding the summary to an emitted frame needs the substrate→list read this harness does not do, so spec `## Out of scope` carries it and Task 7 Step 3 registers it on `T0023`. The *shape* is fixed here so the family cannot narrow it later.

- [ ] **Step 1: Write the failing test, built on the real defect this exists to surface**

```python
from datetime import datetime, timezone
from cli.features.derivatives import coverage_by_year

def test_coverage_by_year_separates_a_late_start_from_an_interior_outage():
    """The shape that motivated D6: an overall null rate reads as a nuisance while one year is
    almost entirely missing. Coverage must show the year, not the aggregate -- and within a year,
    the two timestamps, because 2021 and 2022 below have similar counts and opposite meanings.
    2021 runs from January to October with a hole in the middle; 2022 does not start until
    October. A count alone cannot tell them apart."""
    UTC = timezone.utc
    ts = [datetime(y, m, 1, tzinfo=UTC) for y in (2021, 2022, 2023) for m in range(1, 11)]
    vals = [1.0] + [None] * 8 + [1.0] + [None] * 9 + [1.0] + [1.0] * 10
    cov = coverage_by_year(ts, vals)
    assert cov[2021] == (2, 10, datetime(2021, 1, 1, tzinfo=UTC), datetime(2021, 10, 1, tzinfo=UTC))
    assert cov[2022] == (1, 10, datetime(2022, 10, 1, tzinfo=UTC), datetime(2022, 10, 1, tzinfo=UTC))
    assert cov[2023] == (10, 10, datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 10, 1, tzinfo=UTC))
    assert 1 - cov[2022].non_null / cov[2022].total == 0.9

def test_coverage_by_year_rejects_a_length_mismatch_and_reports_an_empty_year():
    """The two contracts the summary's arithmetic rests on. The derived null fraction is only as
    good as `total`, and a `zip`-based implementation truncates to the shorter input and under-counts
    it with nothing raising. And an all-null year has no timestamps to report -- `None` twice, not a
    `min()` over an empty sequence."""
    import pytest
    from cli.features.errors import FeatureError
    UTC = timezone.utc
    ts = [datetime(2021, m, 1, tzinfo=UTC) for m in range(1, 4)]
    with pytest.raises(FeatureError):
        coverage_by_year(ts, [1.0, 2.0])
    assert coverage_by_year(ts, [None, None, None])[2021] == (0, 3, None, None)
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): per-year coverage, because an aggregate null rate hides a missing year`

---

### Task 7: Closeout

- [ ] **Step 1:** Append the iterations-history entry to `docs/iterations-history-phase4.md` (B-family is Phase 4 subject matter) via the `iteration-closeout` skill.
- [ ] **Step 2:** Append the Phase-4 decisions-log entry to `docs/research/10.phase4-decisions.md` for the subject-matter decisions this iteration made (the 2022 coverage finding and its consequence for feature selection).
- [ ] **Step 3:** `T0023` is ALREADY `partial` (set at iter-090) and its `ripe_when` — "the B2 derivatives-positioning family is picked for an iteration" — is satisfied by this branch, so there is no status flip to make. The real work is the `## Done so far` entry recording the harness and trimming `## Suggested next steps`, whose second bullet is exactly this harness, to the remainder. **The remainder now includes one item this branch created**: the substrate→feature emission — reading the two `read_*_series` frames into lists, building the 1h/4h grid, and shipping each frame with its `coverage_by_year` summary (spec D6, `## Out of scope`). Register it as its own `## Suggested next steps` bullet; a deferral whose only home is prose is not tracked (`.claude/rules/open-topics.md`).
- [ ] **Step 4:** Add the data-gated substrate assertions (spec D10) to `tests/test_derivatives_oi.py` — beside the `cli/derivatives/` substrate tests, not in the pure-function module, because they read the substrate.
  - **Gate on the canonical root, which is the NFS mount.** `data/derivatives-oi` is **absent** from this workstation's data root, so the house `Path("data/…").exists()` form would skip here exactly as it skips in CI, and Step 5 would record the skip as coverage. Use `resolve_hot_source(load_config()) / "derivatives-oi"` (`cli/config.py` — returns `<nfs_mount_dir>/hot`), which resolves to `/mnt/zhao-crypto/hot/derivatives-oi`, falling back to `Path("data/derivatives-oi")` if a local copy is ever promoted. `tests/test_data_manifest.py` and `tests/test_engine_soak.py` already gate on `/mnt/zhao-crypto` paths; every fixture currently in `tests/test_derivatives_oi.py` is `tmp_path`, so there is no in-file precedent to copy.
  - **Assert**: (a) the balanced-panel start is 2021-12-01 — BTCUSDT begins 2020-09-01, the other nine on 2021-12-01, so the balanced start is the latest first stamp; (b) `sum_open_interest` has zero nulls (spec D5's density claim); (c) over the closed window `ts < 2026-01-01` — a past window a forward refresh cannot move — `sum_open_interest` is exactly `0.0` on **2,329** rows, `sum_open_interest_value` on **2,430** and `sum_taker_long_short_vol_ratio` on **45**; all three populations sit entirely inside that window, whose 4,426,251 rows are the count the assertions are taken over. **Both OI columns, because D5's two zero sets nest rather than coincide**: 101 rows read a zero notional against a healthy positive `sum_open_interest`, so a guard on the first column alone cannot see the second's hole count move. (c) is what stops D5's venue-hole ruling drifting silently under a re-fetch; (a) and (b) stop a coverage extension doing the same.
  - **Run it and read `passed`, not `skipped`.** A skip is not coverage (`CLAUDE.md`), and this is the only substrate-reading guard in the plan.
- [ ] **Step 5:** Run `uv run pre-commit run -a` and the full reachable test set — including the data-gated family, which CI cannot run. Record Step 4's outcome as `passed`; a `skipped` there means the gate is pointed at the wrong root and Step 4 is not done. Commit.
