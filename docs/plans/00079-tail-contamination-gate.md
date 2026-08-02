# Tail contamination gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `continuity.py` refuses a pool whose extreme tail is set by repeat outages (`UNMEASURED`, exit-bar FAIL) instead of deriving a threshold 10× the outage — spec `00079`, resolving [[T0112]] in full, including the tail-depth diagnostic.

**Architecture:** two chained tail-steepness ratios (`p99.99/p99.9` and `p99.9/p99`, denominators floored at 0.5 s, one cut `TAIL_RATIO_CUT = 10.0`) gate `measured` alongside the unchanged `MIN_POOL`; refusals render exactly like today's `MIN_POOL` refusal with a distinguishable post-table note; a `tail` column (count of intervals ≥ p99.99) is printed for every row as transparency, never as detection.

**Tech Stack:** Python 3.14 (uv), polars, pytest. One production file: `infra/scripts/continuity.py`. One test file: `tests/test_infra_continuity.py`.

## Global Constraints

- Constants (verbatim): `TAIL_RATIO_CUT = 10.0`, `RATIO_FLOOR_S = 0.5` (with a comment tying it to the existing 5.0 s floor: it is `5.0 / 10`, the spacing scale below which the threshold floor already declares steepness irrelevant), `MIN_POOL = 5002` **unchanged**.
- The threshold derivation `max(p99.99 × 10, 5.0)`, the silence semantics, and everything T0097 fitted are untouched.
- Refusal = `UNMEASURED` + exit-bar FAIL, identical treatment to the `MIN_POOL` refusal; the *reason* is distinguishable in the post-table note only.
- `continuity.py`'s runtime output is operator-facing (`.claude/rules/operator-facing-text.md`): no `T0112` / `spec 00079` / `D<N>` tokens in printed strings; tokens live in comments only. `tests/test_internal_terms_not_operator_visible.py` may not cover infra scripts automatically — comply regardless.
- Every guard proven by constructing its defect; assert every mutation anchor occurs exactly once before substituting (`grep -cF`, not ugrep regex); clear `__pycache__` around source mutations — and note `continuity.py` is imported by path in tests, so the stale-`.pyc` hazard from `agent-ops.md` applies doubly: unlink its `__pycache__` before each probe.
- Real numbers for fixtures (from the spec's measured tables, cold-review-corrected): real streams ratio 1.05–1.96; stable legit synthetics 1.00–2.18 over 200 seeds; pareto α=1.1 / lognormal σ=3 **straddle the cut by construction** (median 8.7 / 10.1 — pin seeds, never trust one draw); contaminated 88.8–200. Founding defect, pool-level: the `_bursty` k=2 pool derives `thresh = 2,000.0`; report-level: the CARVED fixture gives `n=11,332`, `thresh_s = 2,004`, intra booked `0.0` (k=1 control: `thresh_s = 6.0`, books `200.4 s`).
- Commit gate `uv run pre-commit run -a`; stage by explicit path; every commit ends `Co-Authored-By: <actual authoring model> <noreply@anthropic.com>`.

---

### Task 1: The two ratio gates

**Files:**
- Modify: `infra/scripts/continuity.py`
- Test: `tests/test_infra_continuity.py` (append; read the file's existing fixture idiom first and reuse it)

**Interfaces:**
- Produces (Task 2 and the tests rely on these exact names):

```python
TAIL_RATIO_CUT = 10.0
RATIO_FLOOR_S = 0.5

def tail_steepness(pool: pl.Series) -> tuple[float, float]:
    """(p99.99/max(p99.9, RATIO_FLOOR_S), p99.9/max(p99, RATIO_FLOOR_S)) — nearest interpolation,
    same as the threshold itself."""
```

- `report()`'s `measured` decision becomes: `n >= MIN_POOL` **and** `max(tail_steepness(pool)) < TAIL_RATIO_CUT`. An unmeasured stream renders exactly as today; the post-table note distinguishes the two reasons (existing under-bound line unchanged; new sibling line for steepened tails, plain operator wording, e.g. `and N stream(s) whose spacing tail steepens more than 10x across a decade — the threshold sample is not trustworthy`).

- [ ] **Step 1: Write the failing tests.** Pool-level (pure function) plus one end-to-end through `report()`:

```python
def _bursty(n, rng):   # T0097's measured shape: same-ms bursts, median = 0
    out = []
    while len(out) < n:
        b = rng.randint(1, 12)
        out.extend([0.0] * (b - 1)); out.append(rng.expovariate(1 / 0.35))
    return out[:n]

def test_founding_defect_k2_is_refused():
    """Pool-level half of the founding defect: n=11,389, two 200 s outages -> the OLD derivation
    yields thresh = 2,000.0 from this exact pool (p99.99 lands ON the outage). The report-level
    reproduction uses the CARVED fixture below, not this pool -- a _bursty pool spans only ~17 min
    of wall time, so through report() the old code books the edge_tail and the 0.0-booked defect
    does not reproduce with it (cold-review finding)."""
    rng = random.Random(11)
    pool = pl.Series(_bursty(11_387, rng) + [200.0, 200.0])
    r1, r2 = tail_steepness(pool)
    assert max(r1, r2) >= TAIL_RATIO_CUT          # the gate condition itself

def test_second_ratio_is_load_bearing():
    """k ~= 0.002*n: p99.99 AND p99.9 both land on outages -> first ratio ~1, only the second
    catches it. Dropping the second ratio must fail exactly this test."""
    rng = random.Random(12)
    n, k = 11_389, 23
    pool = pl.Series(_bursty(n - k, rng) + [200.0] * k)
    r1, r2 = tail_steepness(pool)
    assert r1 < TAIL_RATIO_CUT and r2 >= TAIL_RATIO_CUT

def test_legitimate_heavy_tails_stay_measured():
    # bursty-typical + bimodal: seed-independent properties (1.00-2.18 over 200 seeds).
    # pareto a=1.1 / lognormal sigma=3: PINNED to named seeds verified < 10, with a comment that
    # these families straddle the cut by construction (an unpinned seed fails healthy code ~1 in 3).
    ...

def test_floor_keeps_ultra_bursty_measured_and_catches_its_outages():
    """Both arms exercise the 0.5 floor as the DENOMINATOR (cold-review corrected: a single 200 s
    max cannot be reached by p99.99 above MIN_POOL -- that is MIN_POOL's own design)."""
    benign = pl.Series([0.0] * 11_378 + [2.0] * 11)      # p99.9 = 0, p99.99 = 2.0
    r1, _ = tail_steepness(benign)
    assert r1 == 2.0 / RATIO_FLOOR_S == 4.0              # floored, measured
    dirty = pl.Series([0.0] * 11_387 + [200.0] * 2)      # p99.99 lands on an outage
    r1, _ = tail_steepness(dirty)
    assert r1 == 200.0 / RATIO_FLOOR_S == 400.0          # floored, refused
    assert r1 >= TAIL_RATIO_CUT

def test_boundary_n_5002_clean_stays_measured():
    ...

def test_report_renders_contaminated_stream_unmeasured():
    """End-to-end wiring pin, via the CARVED fixture (the existing full_hour_with_gap idiom): two
    hours filled at 0.6 s spacing with two 200 s windows carved out of hour 0. Old-code behaviour,
    reproduced in step 2: n=11,332, thresh_s=2,004, intra booked 0.0. Five assertions, jointly the
    wiring proof: (a) the printed `n` column >= MIN_POOL (the refusal is NOT the old gate);
    (b) `thresh_s` column == UNMEASURED via _column; (c) `*** FAIL *** (unmeasured streams: 1)`;
    (d) the steepened-tail note present; (e) the under-bound note ABSENT. A k=1 carve control on
    the same geometry stays measured with thresh_s=6.0 booking 200.4 s."""
    ...
```

- [ ] **Step 2: Run the CARVED fixture through the CURRENT code first** and record the reproduced defect (`n=11,332`, `thresh_s=2,004`, intra booked `0.0`) plus the k=1 control (`thresh_s=6.0`, books `200.4 s`, measured) in the test docstring and your report — the defect must be shown real before the fix claims to kill it. Then confirm all new tests fail for the stated reasons.
- [ ] **Step 3: Implement** (`tail_steepness`, the constants, the `measured` conjunction, the note line, **and the D6 residual comment beside the gate** — the spec requires it in the code: blindness begins at k ≈ 0.01·n where p99 itself is contaminated; accepted because that regime is 77–97 % outage by wall time, and the truncated-hours count is NOT a backstop since it uses `secs > thresh`). Surgical: the existing `measured = n >= MIN_POOL` site and the notes block are the only touch points.
- [ ] **Step 4: Green** (`uv run pytest tests/test_infra_continuity.py -q`), then mutation-proofs, each anchor asserted unique: cut → 1000.0 (contamination tests fail); second ratio dropped (its test fails, others pass); ratio tuple reordered (caught — the swapped r1 ≈ 194 trips the k=23 test's `r1 < CUT` half); floor removed (ultra-bursty test fails); **`measured` reverted to `n >= MIN_POOL` alone (the wiring mutant) → exactly `test_report_renders_contaminated_stream_unmeasured` fails**. Restore + re-green after each.
- [ ] **Step 5:** `uv run pre-commit run -a` clean → stage explicit paths → commit `fix(infra): continuity.py refuses a contaminated tail instead of trusting it`.

### Task 2: The tail-depth column

**Files:**
- Modify: `infra/scripts/continuity.py`
- Test: `tests/test_infra_continuity.py` (append)

**Touch points beyond the measured rows** (the `_column`-based tests catch misalignment, but name them): the UNMEASURED row, the TOTAL row, and both `"-" * <width>` separators all gain the new column slot.

**Interfaces:** helper `tail_depth(pool: pl.Series) -> int` = `int((pool >= pool.quantile(0.9999)).sum())`; column `tail` (right-aligned, after `n`) printed for every row with `n > 0` (unmeasured included — fragility is most useful exactly there). Header updated in the same change.

- [ ] **Step 1: Failing tests:**

```python
def test_tail_depth_is_printed_and_correct():
    ...  # known fixture -> exact expected depth in the rendered row

def test_depth_is_provably_not_a_detector():
    """THE test that documents why depth is not a gate: clean and contaminated n=11,389 pools have
    IDENTICAL depth (2). Anyone promoting depth into a gate must delete this test to do it."""
    rng = random.Random(11)
    clean = pl.Series(_bursty(11_389, rng))
    dirty = pl.Series(_bursty(11_387, rng) + [200.0, 200.0])
    assert tail_depth(clean) == tail_depth(dirty) == 2
```

- [ ] **Step 2: Fail → implement → green.** The depth helper is one expression; the code comment beside it states the measured fact (identical clean/contaminated) so the non-use as a gate survives future review.
- [ ] **Step 3: Mutation-proof** the column (drop it → rendering test fails), gate, stage, commit `feat(infra): print the tail depth beside every continuity row`.

### Task 3: Closeout (branch end — verify every claim against the actual branch log first)

**Files:**
- Modify: `docs/open-topics/T0112-quantile-threshold-self-inflates-on-repeat-outages.md` → archive (topic-ops mechanics: `status: resolved`, DELETE `ripe_when:`, `## Resolution` naming spec/commits/measurements, `git mv` to `docs/open-topics/archive/`)
- Modify: `docs/open-topics/README.md` (bullet moves to `### Resolved` in Research-and-development, link repointed to `archive/`)
- Modify: `docs/iterations-history-phase6.md` (new `## <date>` entry — `00076`'s and `00078`'s entries both live here, same routing)

**Input from the orchestrator (host-touching, runs in the main loop, never a subagent):** the acceptance run — the NEW `continuity.py` piped into the pinned ops image against the NAS archive read-only, plus the SHIPPED version on the same input; all 12 streams measured in both; `thresh_s`/`gap_s`/`gap%` identical column-for-column; the new `tail` column present. The orchestrator hands the two outputs to this task as files; the entry quotes the result.

- [ ] **Step 1:** T0112 resolution — all three concerns closed: detection (D1 ratios, founding defect flipped), transparency (D5 depth column), the declined-estimator route explicitly not taken. The D6 residual (k ≥ ~0.01·n) is recorded IN the resolution as a conscious drop with its absurdity bound — not a deferral, no new topic (owner's directive).
- [ ] **Step 2:** Iterations-history entry, written fresh against the branch log: what shipped, the founding-defect flip evidence (2,006 s/0.0 booked → UNMEASURED), the real-data acceptance numbers, the depth-is-not-a-detector finding (measured, pinned as a test), and the validation split (synthetic true-positives / real-data no-false-positives) — the owner's "synthesis data" question answered in one line.
- [ ] **Step 3:** Full gate (`uv run pytest` complete, `uv run pre-commit run -a`), stage by kind, commit `docs(ops): iter closeout — continuity.py tail contamination gate (spec 00079, resolves T0112)`. The memo update is the orchestrator's (gitignored, read-guarded).
