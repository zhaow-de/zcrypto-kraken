# T0098 Reach-Review Residuals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close [[T0098]] in full per spec `00080`: whole-sibling cleanup on builder failure, `PAIR_KEYS` relocated to `cli/ohlc/fetch.py`, and the byte-identical seam logic extracted to a new `cli/ohlc/seam.py`.

**Architecture:** One behaviour change (Task 1, TDD) and two behaviour-neutral refactors (Tasks 2–3) proven neutral by an unchanged suite plus a byte-identity probe of `zcrypto engine soak-check`. Task 4 is closeout.

**Tech Stack:** Python 3.14 (uv-locked), polars, pytest.

## Global Constraints

- Run everything through uv: `uv run pytest …`, `uv run pre-commit run -a`.
- **Every error-message text stays byte-identical except the one message Task 1 Step 4 extends.** The seam messages are test-pinned on both sides (`seam too thin` / `seam mismatch` in `tests/test_ohlc_reach.py`; `shortfall` / `mismatch` via `EngineError` in `tests/test_engine_store.py`).
- **Tasks 2–3 must not edit any existing test assertion** — additions only. Task 1 adds assertions to one existing test.
- The new message in Task 1 is operator-facing runtime output: plain language, no `T<NNNN>`/spec/phase tokens (`tests/test_internal_terms_not_operator_visible.py` walks `cli/` literals).
- Stage by explicit path (never `git add -A`); Conventional Commits; the branch is `fix/t0098-reach-review-residuals` (exists, spec committed on it).
- The scripted `git commit -m` blocks show subject lines only: every commit ends with the authoring model's `Co-Authored-By:` trailer and gets a different-agent review before push, per `commit-messages.md` (the SDD machinery supplies both).
- The soak-check baseline from `develop`'s tip is already saved at `<scratchpad>/soak-check-before.txt` (17 lines, ends `exit=0`); the scratchpad path is in the orchestrator's session context.

---

### Task 1: Whole-sibling cleanup on builder failure (spec D1 + D2)

**Files:**
- Modify: `cli/data/rebuild.py` (the `rebuild_sets` failure path and the exists-guard message; `import shutil`)
- Test: `tests/test_data_rebuild.py`

**Interfaces:**
- Consumes: `rebuild.rebuild_sets`, `rebuild.RebuildContext(data_root, ohlcvt_source_dir, stamp)`, `rebuild.REBUILDABLE` (existing).
- Produces: no signature changes; `rebuild_sets` now removes the whole minted sibling when the builder raises.

- [ ] **Step 1: Write the failing strand test**

Add to `tests/test_data_rebuild.py`, directly after `test_rebuild_cleans_up_empty_sibling_on_builder_failure`:

```python
def test_rebuild_removes_partial_sibling_on_builder_failure(tmp_path, monkeypatch):
    # A builder that wrote real output before raising must not strand the sibling: the date-stamped
    # name would turn every same-day retry into "sibling already exists" (T0098 sub-item 1).
    def _partial(ctx, out):
        (out / "BTC" / "EUR").mkdir(parents=True)
        (out / "BTC" / "EUR" / "1440.parquet").write_bytes(b"partial")
        raise RuntimeError("fetch 7 of 30 failed")

    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", _partial)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260802")
    with pytest.raises(RuntimeError, match="fetch 7 of 30"):
        rebuild.rebuild_sets(["ohlc-full"], ctx)
    assert not (tmp_path / "ohlc-full-20260802").exists()

    # And the same-day retry now succeeds.
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: (out / "ok").write_text("x"))
    assert rebuild.rebuild_sets(["ohlc-full"], ctx) == [tmp_path / "ohlc-full-20260802"]


def test_rebuild_cleanup_covers_operator_interrupt(tmp_path, monkeypatch):
    # Ctrl-C during a paced REST round is the likeliest mid-build abort; the handler catches
    # BaseException so the sibling is removed before the interrupt propagates. This test is the
    # pin that keeps the handler from being narrowed back to Exception.
    def _interrupted(ctx, out):
        (out / "partial").write_text("x")
        raise KeyboardInterrupt

    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", _interrupted)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260802")
    with pytest.raises(KeyboardInterrupt):
        rebuild.rebuild_sets(["ohlc-full"], ctx)
    assert not (tmp_path / "ohlc-full-20260802").exists()
```

- [ ] **Step 2: Run it — it must FAIL against current code**

Run: `uv run pytest tests/test_data_rebuild.py::test_rebuild_removes_partial_sibling_on_builder_failure tests/test_data_rebuild.py::test_rebuild_cleanup_covers_operator_interrupt -v`
Expected: BOTH FAIL at `assert not (...).exists()` — current code removes only *empty* siblings, and `except Exception` doesn't see `KeyboardInterrupt` at all. If either passes, STOP: the defect doesn't reproduce, report instead of proceeding.

- [ ] **Step 3: Implement the whole-tree cleanup**

In `cli/data/rebuild.py`: add `import shutil` beside `import json`. Replace the failure-path block inside `rebuild_sets`:

```python
        try:
            builder(ctx, out_root)
        except BaseException:
            # A builder that raises mid-run must not strand the sibling: the per-day stamp would
            # make a same-day retry trip the "already exists" guard forever. Everything under
            # out_root was written by the builder call that just raised (the exists-guard fired
            # before mkdir if the dir pre-existed), and every current builder fetches/derives
            # repeatable input, so deleting the whole tree loses nothing. (A future builder
            # consuming unrepeatable input would need its own protection.) BaseException on
            # purpose: an operator's Ctrl-C must clean up exactly like a builder error. A hard
            # kill (SIGKILL, power loss) skips any handler and can still strand -- the
            # exists-guard message names the remedy.
            shutil.rmtree(out_root)
            raise
```

- [ ] **Step 4: Extend the exists-guard message and pin it**

Replace the refusal line in `rebuild_sets`:

```python
        if out_root.exists():
            raise DataSyncError(
                f"data rebuild: sibling already exists: {out_root} -- either a completed sibling "
                "from earlier today, or the leavings of a run killed mid-build (a failed builder "
                "cleans up after itself, but a hard kill cannot); inspect the directory and "
                "remove it to retry"
            )
```

Add to the END of the existing `test_rebuild_refuses_existing_sibling` (do not modify its existing assertion):

```python
    with pytest.raises(DataSyncError, match="remove it to retry"):
        rebuild.rebuild_sets(["ohlc-full"], ctx)
```

- [ ] **Step 5: Run the file's tests + the operator-text guard**

Run: `uv run pytest tests/test_data_rebuild.py tests/test_internal_terms_not_operator_visible.py -v`
Expected: all PASS, including the untouched `test_rebuild_cleans_up_empty_sibling_on_builder_failure` (rmtree covers the empty case).

- [ ] **Step 6: Commit**

```bash
git add cli/data/rebuild.py tests/test_data_rebuild.py
git commit -m "fix(data): a failed rebuild builder removes its whole sibling, not only an empty one"
```

---

### Task 2: Relocate `PAIR_KEYS` to `cli/ohlc/fetch.py` (spec D3)

**Files:**
- Modify: `cli/ohlc/fetch.py`, `cli/engine/store.py`, `cli/ohlc/reach.py`

**Interfaces:**
- Produces: `cli.ohlc.fetch.PAIR_KEYS` (the single binding). `from cli.engine.store import PAIR_KEYS` keeps working everywhere — the store imports and re-exports it; `cli/engine/__init__.py` is untouched.

- [ ] **Step 1: Add the dict to `cli/ohlc/fetch.py`**

Directly after `_TIMEOUT_SECONDS = 15`, insert (comment moves with it, verbatim from the store):

```python
# The ten EUR-quoted assets of data/ohlc-full, transcribed from the snapshot register
# (docs/research/01.1.kraken-snapshot-register.md) -- display asset -> Kraken pair key.
PAIR_KEYS: dict[str, str] = {
    "BTC": "XXBTZEUR",
    "ETH": "XETHZEUR",
    "SOL": "SOLEUR",
    "XRP": "XXRPZEUR",
    "ADA": "ADAEUR",
    "LINK": "LINKEUR",
    "DOGE": "XDGEUR",
    "LTC": "XLTCZEUR",
    "DOT": "DOTEUR",
    "AVAX": "AVAXEUR",
}
```

- [ ] **Step 2: Point the store at it**

In `cli/engine/store.py`: delete the `PAIR_KEYS: dict[str, str] = {…}` block *and its two comment lines*; change `from cli.ohlc.fetch import fetch_ohlc` to `from cli.ohlc.fetch import PAIR_KEYS, fetch_ohlc`. (The store still uses `PAIR_KEYS` itself, so ruff sees a used import; every `from cli.engine.store import PAIR_KEYS` site still resolves.)

- [ ] **Step 3: Point reach at it and delete the inversion comment**

In `cli/ohlc/reach.py`: delete the entire comment block beginning `# The asset -> Kraken REST pair-key mapping's single source of truth.` **and** the line `from cli.engine.store import PAIR_KEYS` below it (12 lines deleted in total); change `from cli.ohlc.fetch import fetch_ohlc` to `from cli.ohlc.fetch import PAIR_KEYS, fetch_ohlc`.

- [ ] **Step 4: Verify single binding + run the touched suites**

Run: `git grep -n "PAIR_KEYS: dict"` → exactly one hit, in `cli/ohlc/fetch.py`.
Run: `uv run pytest tests/test_engine_store.py tests/test_engine_cycle.py tests/test_engine_metrics.py tests/test_engine_soak.py tests/test_ohlc_reach.py tests/test_data_rebuild.py -v`
Expected: all PASS with zero test-file changes.

- [ ] **Step 5: Commit**

```bash
git add cli/ohlc/fetch.py cli/engine/store.py cli/ohlc/reach.py
git commit -m "refactor(ohlc): PAIR_KEYS moves to cli/ohlc/fetch.py, its natural home"
```

---

### Task 3: Extract the seam primitives to `cli/ohlc/seam.py` (spec D4)

**Files:**
- Create: `cli/ohlc/seam.py`
- Modify: `cli/engine/store.py`, `cli/ohlc/reach.py`
- Test: `tests/test_ohlc_seam.py` (new; additions only elsewhere — no edits to existing test files)

**Interfaces:**
- Produces: `cli.ohlc.seam.MIN_SEAM_OVERLAP` (= 6), `drop_in_progress(frame, interval, now)`, `seam_overlap(left, right) -> tuple[int, pl.DataFrame]`. Reach re-imports `MIN_SEAM_OVERLAP` so `tests/test_ohlc_reach.py`'s `from cli.ohlc.reach import MIN_SEAM_OVERLAP` keeps working.

- [ ] **Step 1: Create `cli/ohlc/seam.py`**

```python
"""Seam primitives shared by the REST reach round (`cli/ohlc/reach.py`) and the engine's live
price store (`cli/engine/store.py`): the drop-the-in-progress-candle rule and the seam definition
itself (what counts as overlap, what counts as a mismatch). The guard POLICIES stay with the
callers -- their exception types, message texts, and merge rules differ on purpose -- but a change
to what a seam IS belongs here, where both callers inherit it."""

from __future__ import annotations

from datetime import datetime

import polars as pl

# Shared stamps required before a seam counts as verified: below this the join rests on too few
# agreeing bars to distinguish "the same series" from "coincidentally equal at the boundary".
MIN_SEAM_OVERLAP = 6


def drop_in_progress(frame: pl.DataFrame, interval: int, now: datetime) -> pl.DataFrame:
    """Drop any row whose interval end (stamp + interval minutes) lies after `now` -- Kraken's
    OHLC response always includes the currently-forming candle as its last row; persisting it
    would write a bar that is still changing. A row ending exactly at `now` is complete, so kept."""
    return frame.filter((pl.col("ts") + pl.duration(minutes=interval)) <= now)


def seam_overlap(left: pl.DataFrame, right: pl.DataFrame) -> tuple[int, pl.DataFrame]:
    """Join `left` and `right` on `ts` and return `(overlap_bars, mismatches)`: the shared-stamp
    count, and the shared rows whose closes disagree (right-side columns suffixed `_rest`). This
    is the seam DEFINITION -- both callers' guards read these two values, so a change to what
    counts as agreement lands here and neither copy can drift."""
    shared = left.join(right, on="ts", how="inner", suffix="_rest")
    return shared.height, shared.filter(pl.col("close") != pl.col("close_rest"))
```

- [ ] **Step 2: Rewire the store**

In `cli/engine/store.py`:

- Add `from cli.ohlc.seam import MIN_SEAM_OVERLAP, drop_in_progress, seam_overlap` beside the other `cli.ohlc` imports.
- Delete the `_SEED_MIN_OVERLAP = 6` line and the whole `_drop_in_progress` function.
- In `seed_store`, change `min_overlap=_SEED_MIN_OVERLAP` to `min_overlap=MIN_SEAM_OVERLAP`.
- Change both `_drop_in_progress(to_frame(...), interval, now)` call sites (in `seed_store` and `refresh_store`) to `drop_in_progress(...)`.
- In `_reconcile`, replace the two lines
  `shared = store_frame.join(rest_frame, on="ts", how="inner", suffix="_rest")` / `overlap_bars = shared.height`
  with `overlap_bars, mismatches = seam_overlap(store_frame, rest_frame)`, and delete the later
  `mismatches = shared.filter(pl.col("close") != pl.col("close_rest"))` line. Everything below (both raises, the replace/merge block) is untouched.
- Append one line to `_reconcile`'s docstring: `Sibling: cli/ohlc/reach.py::_merge_or_detach guards the same seam definition under its own policy -- a safety fix here likely applies there too.`

- [ ] **Step 3: Rewire reach**

In `cli/ohlc/reach.py`:

- Add `from cli.ohlc.seam import MIN_SEAM_OVERLAP, drop_in_progress, seam_overlap` beside the other `cli.ohlc` imports.
- Delete the local `MIN_SEAM_OVERLAP = 6` binding *and its three comment lines*, and the whole `_drop_in_progress` function.
- In `_merge_or_detach`, replace
  `shared = canonical.join(rest, on="ts", how="inner", suffix="_rest")` / `overlap_bars = shared.height`
  with `overlap_bars, mismatches = seam_overlap(canonical, rest)`, and delete the later
  `mismatches = shared.filter(pl.col("close") != pl.col("close_rest"))` line. Both raises and the merge block are untouched (the mismatch message still reads `mismatches['close'][0]` / `mismatches['close_rest'][0]`, which the joined subframe carries).
- Change the `_drop_in_progress(to_frame(...), interval, now)` call site to `drop_in_progress(...)`.
- Append one line to `_merge_or_detach`'s docstring: `Sibling: cli/engine/store.py::_reconcile guards the same seam definition under its own policy -- a safety fix here likely applies there too.`

- [ ] **Step 4: Direct tests for the new module**

Create `tests/test_ohlc_seam.py`:

```python
from datetime import UTC, datetime, timedelta

import polars as pl

from cli.ohlc.seam import drop_in_progress, seam_overlap

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


def test_drop_in_progress_drops_forming_candle_keeps_boundary():
    frame = pl.DataFrame(
        {
            "ts": [NOW - timedelta(minutes=120), NOW - timedelta(minutes=60), NOW - timedelta(minutes=30)],
            "close": [1.0, 2.0, 3.0],
        }
    )
    out = drop_in_progress(frame, 60, NOW)
    # -30min ends after NOW -> dropped; -60min ends exactly at NOW -> complete, kept.
    assert out["ts"].to_list() == [NOW - timedelta(minutes=120), NOW - timedelta(minutes=60)]


def test_seam_overlap_counts_shared_stamps_and_flags_close_disagreement():
    left = pl.DataFrame({"ts": [NOW, NOW + timedelta(hours=1)], "close": [1.0, 2.0]})
    right = pl.DataFrame({"ts": [NOW + timedelta(hours=1), NOW + timedelta(hours=2)], "close": [2.5, 3.0]})
    overlap_bars, mismatches = seam_overlap(left, right)
    assert overlap_bars == 1
    assert mismatches.height == 1
    assert mismatches["close"][0] == 2.0
    assert mismatches["close_rest"][0] == 2.5


def test_seam_overlap_clean_seam_has_no_mismatches():
    left = pl.DataFrame({"ts": [NOW], "close": [1.0]})
    right = pl.DataFrame({"ts": [NOW], "close": [1.0]})
    overlap_bars, mismatches = seam_overlap(left, right)
    assert overlap_bars == 1
    assert mismatches.is_empty()
```

- [ ] **Step 5: Verify single definitions + run the suites**

Run: `git grep -nE "def _?drop_in_progress"` → exactly one hit, in `cli/ohlc/seam.py`.
Run: `git grep -nE "MIN_SEAM_OVERLAP = |_SEED_MIN_OVERLAP"` → exactly one binding, in `cli/ohlc/seam.py` (doc mentions in `docs/` are fine; no `cli/` or `tests/` hit besides the binding and its importers).
Run: `uv run pytest tests/test_ohlc_seam.py tests/test_ohlc_reach.py tests/test_engine_store.py tests/test_engine_cycle.py tests/test_engine_soak.py -v`
Expected: all PASS with zero edits to existing test files.

- [ ] **Step 6: Commit**

```bash
git add cli/ohlc/seam.py cli/engine/store.py cli/ohlc/reach.py tests/test_ohlc_seam.py
git commit -m "refactor(ohlc): extract the shared seam primitives to cli/ohlc/seam.py"
```

- [ ] **Step 7: Mutation-proof the extraction (AFTER the commit — the tree must be clean)**

Corrupt the shared comparison, expect BOTH suites' mismatch tests to fail, restore from the commit:

```bash
sed -i 's/pl.col("close") != pl.col("close_rest")/pl.col("open") != pl.col("open_rest")/' cli/ohlc/seam.py
uv run pytest "tests/test_ohlc_reach.py" "tests/test_engine_store.py" -k "mismatch" -v
git checkout -- cli/ohlc/seam.py
uv run pytest "tests/test_ohlc_reach.py" "tests/test_engine_store.py" -k "mismatch" -v
git status --porcelain
```

Expected: the first pytest run FAILS in **both** files' mismatch tests (proving both callers route through `seam_overlap`); the second run is green; `git status` is clean. Read WHICH tests failed — a failure outside the mismatch tests is a finding, not a pass.

---

### Task 4: Closeout — identity proofs, topic archive, changelog

**Files:**
- Modify: `docs/open-topics/T0098-reach-round-review-residuals.md` → `docs/open-topics/archive/` (via `git mv`), `docs/open-topics/README.md`, `docs/iterations-history-phase6.md`

**Interfaces:**
- Consumes: the saved baseline `<scratchpad>/soak-check-before.txt`; Tasks 1–3 committed.

- [ ] **Step 1: The soak-check byte-identity probe (spec D5)**

```bash
( uv run zcrypto engine soak-check > <scratchpad>/soak-check-after.txt 2>&1; echo "exit=$?" >> <scratchpad>/soak-check-after.txt )
diff <scratchpad>/soak-check-before.txt <scratchpad>/soak-check-after.txt && echo IDENTICAL
```

Expected: `IDENTICAL`. Any diff is a behaviour change — STOP and report it; do not rationalise it.

If the baseline file is gone (lost scratchpad), regenerate it at the branch point first: `git worktree add /tmp/00080-base $(git merge-base develop HEAD)`, run the same soak-check capture there, then `git worktree remove /tmp/00080-base`.

- [ ] **Step 2: Full suite**

Run: `uv run pytest`
Expected: green, including the data-dependent regression tests (`data/ohlc-full` is present; ~7 min).

- [ ] **Step 3: Close T0098 per the `topic-ops` skill** (the orchestrator loads it)

Flip `status: resolved`, **delete the `ripe_when:` key**, add a `## Resolution` section naming spec `00080`, the three commits, and the two corrected premises (the manifest signature false for `snapshots`/`universe`; full guard-block unification not a pure refactor — what shipped instead), `git mv` the file to `docs/open-topics/archive/`, and move the index bullet to the category's `### Resolved` with the archived link.

- [ ] **Step 4: Append the iterations-history entry** (`docs/iterations-history-phase6.md`, per the `iteration-closeout` skill — same routing as 00079)

`## 2026-08-02 — reach-review residuals closed (spec 00080, resolves T0098)` with one bullet per landed change, including: the cleanup's hard-kill residual accepted with the message as remedy; `PAIR_KEYS`' single binding now `cli/ohlc/fetch.py` (store re-exports); `cli/ohlc/seam.py` as the seam definition's home with guard policies deliberately left local; the soak-check byte-identity result; and that the next attended engine converge ships this refactor (spec D6).

- [ ] **Step 5: Gate and commit**

```bash
uv run pre-commit run -a
git add docs/open-topics/archive/T0098-reach-round-review-residuals.md docs/open-topics/README.md docs/iterations-history-phase6.md
git commit -m "docs(ops): iter closeout -- reach-review residuals closed (spec 00080, resolves T0098)"
```

(Re-run the gate and re-stage if hooks rewrite; the `git mv` deletion side stages with the archive path.)

- [ ] **Step 6: Memo update (ORCHESTRATOR ONLY — main loop, Edit/Write tools, never staged: the memo is gitignored)**

Per spec D6: record in `docs/memo.local.md` that the next attended engine converge ships this store/soak refactor, and move the T0098 queue item to `DONE ITEMS` with its evidence. Never dispatch this step to a subagent.
