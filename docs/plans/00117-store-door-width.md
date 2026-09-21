# The store door holds a frame to its whole width — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `seed_store` and `refresh_store` refuse a store frame, `seed_store` a canonical before copying it and both the REST fetch before the merge, when it is not the whole of `FRAME_SCHEMA` in order, non-empty, with no null or repeated stamp, every stamp on the leg's epoch-anchored grid and every present close finite and positive, naming the file, the pair, the grid, the first difference and one recovery per host, a refused fetch named as the venue's with no store repair; the three code carriers that named the workstation command route by host, the seam's absent-close refusal routes by the side that holds the null and `seed_store` claims a fresh copy only when it copied one, and the soak's off-grid refusal carries the same recovery and names the daily row's scratch store; the engine host's repair moves the store aside, converges with the flag and the digest, and purges the aside copy once the refused file has been read and the all-clear by value has landed, in the runbook, the engine role's comment and `fail_msg`, and spec 00042; spec 00115 D2 is amended to the host read that settled it; T0199 is resolved.

**Architecture:** One `_frame_differences(frame, interval)` in `cli/engine/store.py` returning the first failing arm's differences, and `_require_store_frame` raising them with the recovery `frozen` picks, replacing `_require_joinable_ts` at its three call sites; `_require_rest_frame` raises the same differences over the REST fetch, in both readers between `drop_in_progress` and `_reconcile`, in the venue's name; four module constants hold the store recovery, the canonical recovery, the REST refusal and the host routing, and `refresh_store`'s two hints and `run`'s bind-mount refusal in `cli/engine/command.py` end with the routing. `_reconcile` takes two hints beside `mismatch_hint` and its absent-close refusal picks one by side, over the absent rows; its seam and merge, `read_store_series`' checks, `cli/ohlc/seam.py` and `cli/ohlc/dataset.py` do not change. `realized_series`' off-grid refusal in `cli/engine/soak.py` imports the store recovery and names the daily row's scratch store, and `run_cycle`'s docstring gains the move-aside clause. Two cycle fixtures stop writing what the door refuses. The host carriers are prose: the engine role's delivery comment and `fail_msg`, spec 00042's item 4 with a `## Spec amendments` section, the cycle-stale bullet of `infra/runbooks/engine.md`, the workstation row of `docs/reference/fleet.md` and spec 00115's D2 with its own `## Spec amendments` section. The topic is resolved and archived.

**Tech Stack:** Python 3.14, pytest, polars 1.44.2 (`FRAME_SCHEMA`, `dt.epoch`, `is_infinite`, `with_row_index`); `infra/scripts/mutate-probe.sh` for the guard verdicts; `topic-ops` for the closeout; the universal test of `zcrypto-refine-rules` governs the runbook and fleet pages Task 3 edits, through the `guidance-guard` commit-msg hook.

**Spec:** `docs/specs/00117-store-door-width-design.md`

## Global Constraints

- The source change is confined to `cli/engine/store.py` (the `cli.ohlc.dataset` import line, the seven constants, `_frame_differences`, `_require_store_frame`, its three call sites, `_require_rest_frame` and its two, `_reconcile`'s two hint parameters and the hint and the side list its absent-close refusal reads off the absent rows, both callers' hint lines and three docstring clauses in `read_store_series`), the `cli.engine.store` import line and the bind-mount refusal in `cli/engine/command.py`, the `cli.engine.store` import line and the off-grid refusal's text in `cli/engine/soak.py`, one docstring clause in `cli/engine/cycle.py`, and one docstring line and the keys comment in `cli/ohlc/reach.py`. `_reconcile`'s seam and merge, `read_store_series`' checks, `_on_grid`, `cli/ohlc/seam.py`, `cli/ohlc/dataset.py` (spec 00116 D4 and T0200's ruling) and `run_cycle`'s code do not change (spec D1, D2, D6).
- The refusal's message is `<fn_name>: <path> is not the frame the store readers join for <pair>@<interval> -- <differences>; <recovery>`, the differences spelled as `_read_canonical` in `cli/ohlc/reach.py` spells them and the close arm as spec 00116 D1's message spells it (spec D1, D2, D4). No string literal added under `cli/`, `infra/ansible/`, `infra/runbooks/` or `docs/reference/` names a spec, a decision or a topic: `tests/test_internal_terms_not_operator_visible.py` reads every string literal under `cli/`, every ansible task name and every runbook page. Provenance goes in the comment beside the code and in the commit message.
- `None` is admitted as a close (spec D2); the filter reads `is_not_null()` before anything else. The grid is `interval` minutes from the Unix epoch, both grids (spec D3).
- The REST fetch's refusal carries `_REST_REFUSED` and nothing else: it names the fetch rather than a file, prescribes no store repair and no edit, and carries neither `_STORE_RECOVERY` nor `_HOST_REDELIVERY`, which its cases pin (spec D1, D4). The store-file recovery is one text, `_STORE_RECOVERY`, for every arm, and the in-place `ts` recast prescription and the words `promote the verified sibling` leave `cli/engine/store.py` — the word `recast` stays in `_CANONICAL_RECOVERY`, which says why a recast is the wrong repair for a canonical, and the store refusals carry none of it, which their cases pin (spec D4, D5); every refusal text naming `zcrypto engine seed` carries `_HOST_REDELIVERY` and ends with it, except `realized_series`' refusal, whose scratch-store sentence follows it, and `run_cycle`'s docstring, which routes by host in its own words (spec D6).
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend, the tree clean: Task 1 Step 8 and Task 2 Step 6 are those steps. The probe never runs while a pytest run is in flight in the same checkout.
- Every commit is green over the changed modules' consumers, the union of `grep -rlE 'engine\.store|engine import store' tests/test_*.py`, `grep -rlE 'engine\.command|engine import command' tests/test_*.py`, `grep -rlE 'engine\.soak|engine import soak' tests/test_*.py`, `grep -rlE 'engine\.cycle|engine import cycle' tests/test_*.py` and `grep -rlE 'ohlc\.reach' tests/test_*.py` as they read when this plan was written: `uv run pytest -q tests/test_basket_concordance.py tests/test_config.py tests/test_data_command.py tests/test_data_manifest.py tests/test_data_rebuild.py tests/test_engine_command.py tests/test_engine_concordance.py tests/test_engine_cycle.py tests/test_engine_execledger.py tests/test_engine_feeders.py tests/test_engine_flatten.py tests/test_engine_gate_cache.py tests/test_engine_gate_export_cache.py tests/test_engine_gate_export.py tests/test_engine_instruments.py tests/test_engine_metrics.py tests/test_engine_node.py tests/test_engine_soak_command.py tests/test_engine_soak.py tests/test_engine_store.py tests/test_engine_stub_fidelity.py tests/test_engine_venuestate.py tests/test_error_paths_are_logged.py tests/test_ohlc_reach.py tests/test_ops_daily_soak.py tests/test_ops_daily.py`; `uv run pre-commit run -a` is clean; the full suite is CI's, on the pull request.
- `uv run pre-commit run -a` runs the pre-commit stage alone: `guidance-guard`, `message-citations` and `staged-kind` run at commit-msg. The first refuses a universal word (every, never, always, only, any, cannot) in the prose of a list item on a page under `infra/runbooks/` or in `docs/reference/fleet.md` with no count entry, so the texts Task 3 writes there carry none outside code spans; the second refuses a commit message whose `path:line`, `path::symbol` or `T<NNNN>` resolves nowhere, so the messages below cite symbols that exist at that commit and topics that exist on either side of it.
- No step reaches a host or a venue, and no step re-reads the spec's measured basis, which the controller read before this plan. No converge is part of this change (spec D7).
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. An existing file's lines are left as they are, except where a step replaces them.
- The four tasks land in order on one branch and merge together: Task 2's hints use the constants Task 1 defines, Task 3's texts describe the door and the routing Tasks 1 and 2 deliver, and Task 4's Resolution names all three, so no task is committed on a branch that lacks the ones before it and none is split off to its own PR.
- A commit message ends with these two trailers, the model name being the executing model's own (`Claude Fable 5.1`, `Claude Opus 5`, ...):

```
Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd
```

---

## File structure

- Modify `cli/engine/store.py` — `FRAME_SCHEMA` imported; `_HOST_REDELIVERY`, `_STORE_RECOVERY`, `_CANONICAL_RECOVERY`, `_REST_REFUSED`; `_frame_differences` and `_require_store_frame` replace `_require_joinable_ts` at its three call sites; `_require_rest_frame` runs in both readers after `drop_in_progress`; `read_store_series`' docstring names the new door (Task 1); `_ABSENT_REST_HINT`, `_FRESH_COPY`, `_RESEED_REFUSED`; `_reconcile` picks an absent-close hint by side; `refresh_store`'s hints route by host and `seed_store`'s claim a fresh copy only over one (Task 2).
- Modify `cli/ohlc/reach.py` — `_read_canonical`'s sibling line names `_require_store_frame`, and its keys comment drops the topic path Task 4 archives (Task 1).
- Modify `tests/test_engine_store.py` — three existing cases re-pinned; a deviation fixture, five width cases and the REST-fetch case (Task 1); two REST-side lines re-pinned; the routed-hints case, the side case and the fresh-copy case (Task 2).
- Modify `tests/test_engine_cycle.py` — `_spoil` spoils past the door; the calendar pin's `/BTC`-only stamp moves onto the grid as an EUR gap; `_BTC_ONLY_OFFSET` goes (Task 1).
- Modify `cli/engine/command.py` — `_HOST_REDELIVERY` imported; `run`'s bind-mount refusal routes by host (Task 2).
- Modify `tests/test_engine_command.py` — the missing-BTC-legs case pins the routed clause (Task 2).
- Modify `cli/engine/soak.py` — `_STORE_RECOVERY` imported; the off-grid refusal carries it and names the daily row's scratch store (Task 2).
- Modify `cli/engine/cycle.py` — `run_cycle`'s docstring carries the move-aside clause (Task 2).
- Modify `tests/test_engine_soak.py` — the zoned-stamp case (Task 1); the interior off-grid case pins the recovery (Task 2).
- Modify `infra/ansible/roles/engine/tasks/main.yml` — the store-delivery comment and the assert's `fail_msg` (Task 3).
- Modify `docs/specs/00042-vps-deployment-design.md` — item 4's repair sentence, and a `## Spec amendments` section (Task 3).
- Modify `infra/runbooks/engine.md` — the cycle-stale bullet on a raising `run_cycle`: the aside destination, the play starting the unit, the purge point (Task 3).
- Modify `docs/reference/fleet.md` — the workstation row's notes cell (Task 3).
- Modify `docs/specs/00115-soak-verdict-reader-design.md` — D2's last sentence, and a `## Spec amendments` section (Task 4).
- Modify `docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` — resolved, moved to `docs/open-topics/archive/` (Task 4).
- Modify `docs/open-topics/README.md` — re-rendered by `infra/scripts/topics-index.py` (Task 4).

---

### Task 1: The door holds a frame to its whole width and names one recovery

**Files:**
- Modify: `cli/engine/store.py` (the line `from cli.ohlc.dataset import read_parquet, to_frame, write_parquet`; the whole of `_require_joinable_ts`, from `def _require_joinable_ts(` to the blank lines before `def seed_store(`; the three calls of `_require_joinable_ts` in `seed_store` and `refresh_store`; the two `rest_frame = drop_in_progress(` lines, one in each reader; the clause `(`_require_joinable_ts` above owns the exact dtype)` in `read_store_series`' docstring)
- Modify: `cli/ohlc/reach.py` (the line `    Sibling: `cli/engine/store.py::_require_joinable_ts` holds the engine store's files under its own policy.` in `_read_canonical`'s docstring; the two comment lines above `        stamps = frame["ts"]`, from `        # The keys only:` to the line ending `are open (docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md).`)
- Test: `tests/test_engine_store.py` (three existing assertion blocks; the fixture and five cases appended at the end of the file)
- Test: `tests/test_engine_cycle.py` (`_spoil` and its three calls; the `_BTC_ONLY_INSERT_AT` block, `_real_rows`, `_real_store_rows`, `_standalone_ten_asset_targets` and `test_a_btc_stamp_the_eur_legs_lack_moves_no_eur_window`)
- Test: `tests/test_engine_soak.py` (the `from datetime import` line; one case appended at the end of the file)

**Interfaces:**
- Consumes: `FRAME_SCHEMA` from `cli/ohlc/dataset.py`; `EngineError`, `pl`, `Path` already imported in `cli/engine/store.py`; in the test module `_write_full_universe`, `_canonical_rows`, `_good_fetch_fn`, `_good_rest_rows`, `_fetch_override`, `_grid_ref`, `_store_path`, `read_parquet`, `write_parquet`, `to_frame`, `GRID_INTERVALS`, `N_CANON`, `FAR_FUTURE`, `seed_store`, `refresh_store`, `read_store_series`, `EngineError`, `pl`, `pytest`, `timedelta`, `Path`, all existing; in `tests/test_engine_soak.py` `soak`, `CycleRecord`, `select_clean_segment`, `datetime`, `timedelta`, existing.
- Produces: `_frame_differences(frame, interval) -> list[str]`, `_require_store_frame(frame, path, pair, interval, fn_name, *, frozen) -> None`, `_require_rest_frame(frame, pair, interval, fn_name) -> None`, and the four module constants `_HOST_REDELIVERY`, `_STORE_RECOVERY`, `_CANONICAL_RECOVERY`, `_REST_REFUSED`, the first two of which Task 2 uses.

- [ ] **Step 1: Re-pin the three existing cases, append the fixture, the five width cases and the REST-fetch case to `tests/test_engine_store.py`, and pin the grid predicate on a zoned stamp in `tests/test_engine_soak.py`**

In `test_the_store_readers_that_join_refuse_an_unjoinable_ts_column`, replace the nine lines from `    assert reader in str(exc.value) and str(path) in str(exc.value)` through `    ) in str(exc.value)` (the block that pins the recast text) with:

```python
    msg = str(exc.value)
    assert f"{reader}: {path} is not the frame the store readers join for ADA/EUR@240 -- ts is {dtype}, not " in msg
    # Pinned because an earlier wording here prescribed an in-place recast, which no other arm of the door has.
    assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    assert "any bar past the canonical's tail that REST no longer reaches" in msg
    assert "on the engine host the store is re-delivered, not seeded" in msg and "zcrypto-engine-cycle-stale" in msg
    assert "recast" not in msg
```

In `test_seed_store_names_the_canonical_when_the_copy_is_what_is_broken`, replace the line `    assert "then promote the verified sibling into the canonical name" in str(exc.value)` with:

```python
    assert "nothing was copied to the store; a canonical is the data pipeline's to republish" in str(exc.value)
```

In `test_the_store_readers_refuse_a_frame_they_cannot_read_or_price`, replace the line `    assert ("cannot read" if wreck == "corrupt bytes" else "types close as") in str(exc.value)` with:

```python
    assert ("cannot read" if wreck == "corrupt bytes" else "close is String, not Float64") in str(exc.value)
```

Append at the end of the file, after `test_seed_store_refuses_a_canonical_it_cannot_read_before_copying_it`:

```python
# Every deviation below survives a `write_parquet`/`read_parquet` round trip, which is why the door is needed; each is
# what an operator would read off the refusal, so the cases assert the first difference by its text.
def _deviated(frame: pl.DataFrame, how: str) -> pl.DataFrame:
    stamp = frame["ts"][3]
    at_stamp = pl.col("ts") == stamp
    return {
        "open Float32": lambda: frame.with_columns(pl.col("open").cast(pl.Float32)),
        "count Int32": lambda: frame.with_columns(pl.col("count").cast(pl.Int32)),
        "close Float32": lambda: frame.with_columns(pl.col("close").cast(pl.Float32)),
        "an extra column": lambda: frame.with_columns(pl.lit(1).alias("extra")),
        "another order": lambda: frame.select(["ts", "close", "open", "high", "low", "vwap", "volume", "count"]),
        "no rows": lambda: frame.head(0),
        "a null stamp": lambda: frame.with_columns(pl.when(at_stamp).then(None).otherwise(pl.col("ts")).alias("ts")),
        "a repeated stamp": lambda: pl.concat([frame, frame.slice(3, 1)]).sort("ts"),
        "an off-grid stamp": lambda: frame.with_columns(
            pl.when(at_stamp).then(pl.col("ts") + pl.duration(minutes=7)).otherwise(pl.col("ts")).alias("ts")
        ),
        "nan": lambda: frame.with_columns(pl.when(at_stamp).then(float("nan")).otherwise(pl.col("close")).alias("close")),
        "inf": lambda: frame.with_columns(pl.when(at_stamp).then(float("inf")).otherwise(pl.col("close")).alias("close")),
        "0.0": lambda: frame.with_columns(pl.when(at_stamp).then(0.0).otherwise(pl.col("close")).alias("close")),
        "-1.0": lambda: frame.with_columns(pl.when(at_stamp).then(-1.0).otherwise(pl.col("close")).alias("close")),
        "a null close": lambda: frame.with_columns(pl.when(at_stamp).then(None).otherwise(pl.col("close")).alias("close")),
    }[how]()


def _first_difference(how: str, interval: int) -> str:
    ref, step = _grid_ref(interval)
    stamp = ref + 3 * step
    return {
        "open Float32": "open is Float32, not Float64",
        "count Int32": "count is Int32, not Int64",
        "close Float32": "close is Float32, not Float64",
        "an extra column": "extra is not a column of it",
        "another order": "the columns are in another order (ts, close, open, high, low, vwap, volume, count)",
        "no rows": "it has no rows",
        "a null stamp": "ts is null in 1 row(s)",
        "a repeated stamp": "1 row(s) repeat a stamp another row carries",
        "an off-grid stamp": f"1 stamp(s) are off the {interval}-minute grid, the first {(stamp + timedelta(minutes=7)).isoformat()}",
        "nan": f"close[3] at {stamp.isoformat()} is nan, not a finite positive number (1 such close(s))",
        "inf": f"close[3] at {stamp.isoformat()} is inf, not a finite positive number (1 such close(s))",
        "0.0": f"close[3] at {stamp.isoformat()} is 0.0, not a finite positive number (1 such close(s))",
        "-1.0": f"close[3] at {stamp.isoformat()} is -1.0, not a finite positive number (1 such close(s))",
    }[how]


def _deviate_store_file(store_dir: Path, symbol: str, interval: int, how: str) -> Path:
    path = _store_path(store_dir, symbol, interval)
    write_parquet(_deviated(read_parquet(path), how), path)
    return path


def _run_reader(reader: str, store_dir: Path, canonical_dir: Path, fetch_fn=_good_fetch_fn) -> None:
    if reader == "refresh_store":
        refresh_store(store_dir, pairs={"ADA/EUR": "ADAEUR"}, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)
    else:
        seed_store(store_dir, canonical_dir, fetch_fn=fetch_fn, clock=lambda: FAR_FUTURE)


def _assert_store_refusal(exc: EngineError, reader: str, path: Path, interval: int, how: str) -> None:
    msg = str(exc)
    assert f"{reader}: {path} is not the frame the store readers join for ADA/EUR@{interval} -- " in msg
    assert _first_difference(how, interval) in msg
    assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    assert "any bar past the canonical's tail that REST no longer reaches" in msg
    assert "on the engine host the store is re-delivered, not seeded" in msg and "zcrypto-engine-cycle-stale" in msg
    assert "recast" not in msg


@pytest.mark.parametrize("how", ["open Float32", "count Int32", "close Float32", "an extra column", "another order"])
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_a_frame_off_the_schema(tmp_path, reader, how):
    """Each of these passes the seam and dies at `_reconcile`'s concat as a bare polars error today; the door names it."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _deviate_store_file(store_dir, "ADA/EUR", 240, how)

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir)

    _assert_store_refusal(exc.value, reader, path, 240, how)


@pytest.mark.parametrize("how", ["no rows", "a null stamp", "a repeated stamp", "an off-grid stamp"])
@pytest.mark.parametrize("interval", GRID_INTERVALS)
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_unsound_stamps(tmp_path, reader, interval, how):
    """No rows was the seam's shortfall; a null or repeated stamp and an interior off-grid stamp were carried into the
    store by both readers and refused later or never, so these are the frames the door newly refuses."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _deviate_store_file(store_dir, "ADA/EUR", interval, how)

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir)

    _assert_store_refusal(exc.value, reader, path, interval, how)
    assert read_parquet(path).equals(_deviated(to_frame(_canonical_rows(interval)), how))  # refused, not rewritten


@pytest.mark.parametrize("how", ["nan", "inf", "0.0", "-1.0"])
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_an_unusable_present_close(tmp_path, reader, how):
    """The predicate is the snapshot write's: a present close finite and positive. Row 3 is outside the REST overlap,
    where the seam cannot see it and the cycle's journal refused it, boundary after boundary."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    path = _deviate_store_file(store_dir, "ADA/EUR", 240, how)

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir)

    _assert_store_refusal(exc.value, reader, path, 240, how)


@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_admit_a_null_close_at_an_unshared_stamp(tmp_path, reader):
    """A null close is an absent bar, admitted at the door as it is at the journal write; the seam refuses one on a
    SHARED stamp, and row 3 is not shared with the REST fetch."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    _deviate_store_file(store_dir, "ADA/EUR", 240, "a null close")

    _run_reader(reader, store_dir, canonical_dir)

    ts, closes = read_store_series(store_dir, "ADA/EUR", 240)
    assert closes[3] is None and len(ts) == N_CANON + 3


@pytest.mark.parametrize("how", ["an extra column", "no rows", "a null stamp", "a repeated stamp", "an off-grid stamp", "nan"])
def test_seed_store_refuses_a_deviated_canonical_before_copying_it(tmp_path, how):
    """One case per arm: the canonical is held to the whole width before the copy, named as the file that is broken,
    with the data pipeline's recovery and no store file left for the next run to refuse under the store's."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    broken = _deviate_store_file(canonical_dir, "ADA/EUR", 240, how)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_good_fetch_fn, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert f"seed_store: {broken} is not the frame the store readers join for ADA/EUR@240 -- " in msg
    assert _first_difference(how, 240) in msg
    assert str(_store_path(store_dir, "ADA/EUR", 240)) not in msg
    assert "nothing was copied to the store; a canonical is the data pipeline's to republish" in msg
    assert "data rebuild ohlc-full --no-push" in msg and "dataset_hash" in msg
    assert "move this leg aside" not in msg and "recast the column in place" not in msg
    assert _store_path(store_dir, "ADA/EUR", 1440).exists()  # the legs before the refused one are seeded and written
    assert not _store_path(store_dir, "ADA/EUR", 240).exists()


@pytest.mark.parametrize("how", ["an off-grid stamp", "-1.0"])
@pytest.mark.parametrize("reader", ["refresh_store", "seed_store"])
def test_the_store_readers_refuse_a_rest_row_the_venue_carries(tmp_path, reader, how):
    """The door runs over the REST fetch too, before the merge: a venue row off the grid or with an unusable close
    would otherwise become resident, and the seed prescribed for the refused file would fill it back from the same
    window at every re-seed. The refusal is the venue's -- it names the fetch, not a file -- and writes nothing."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    _write_full_universe(canonical_dir, _canonical_rows)
    _write_full_universe(store_dir, _canonical_rows)
    rest = _good_rest_rows(240)
    last = len(rest) - 1  # the newest completed bar, past the store tail, so no seam arm sees it
    ref, step = _grid_ref(240)
    stamp = ref + (N_CANON + 2) * step
    if how == "an off-grid stamp":
        rest[last][0] += 7 * 60
        difference = f"1 stamp(s) are off the 240-minute grid, the first {(stamp + timedelta(minutes=7)).isoformat()}"
    else:
        rest[last][4] = "-1.0"
        difference = f"close[{last}] at {stamp.isoformat()} is -1.0, not a finite positive number (1 such close(s))"

    with pytest.raises(EngineError) as exc:
        _run_reader(reader, store_dir, canonical_dir, _fetch_override("ADAEUR", 240, rest))

    msg = str(exc.value)
    assert f"{reader}: the REST fetch for ADA/EUR@240 is not the frame the store readers join -- " in msg
    assert difference in msg
    assert "there is no store repair" in msg and "the next run fetches again" in msg
    assert "move this leg aside" not in msg and "zcrypto engine seed" not in msg
    path = _store_path(store_dir, "ADA/EUR", 240)
    assert read_parquet(path).equals(to_frame(_canonical_rows(240)))  # the fetch is refused, the leg as it was
```

Run: `uv run pytest -q tests/test_engine_store.py -k "off_the_schema or unsound_stamps or unusable_present_close or null_close_at_an_unshared or deviated_canonical or rest_row_the_venue_carries or unjoinable_ts_column or copy_is_what_is_broken or cannot_read_or_price"`
Expected: `55 failed, 4 passed`; the four passing are the two `admit_a_null_close_at_an_unshared_stamp` cases and the two `corrupt bytes` arms; the failures are `DID NOT RAISE` (the four REST-fetch cases among them, whose row the merge writes today), a bare `polars.exceptions.SchemaError`/`ShapeError` or an `assert ... in msg` on the recast-era text.

In `tests/test_engine_soak.py` replace the line `from datetime import UTC, datetime, timedelta` with `from datetime import UTC, datetime, timedelta, timezone` and append at the end of the file:

```python
def test_the_clean_segment_judges_a_zoned_stamp_by_its_instant():
    """`_on_grid` reads the instant, not the local hour: an aware +02:00 stamp on the UTC grid enters the clean
    segment, and one on the +02:00 wall clock's own 4h marks, off the UTC grid, does not."""

    def _bare(cycle_ts):
        return CycleRecord(
            schema_version=1,
            cycle_ts=cycle_ts,
            snapshots=(),
            final_targets={},
            started_at=cycle_ts,
            completed_at=cycle_ts + timedelta(minutes=1),
            code_version="test",
            builder_path="fast",
        )

    plus_two = timezone(timedelta(hours=2))
    on_grid = [_bare(datetime(2026, 7, 16, 2 + 4 * k, tzinfo=plus_two)) for k in range(3)]  # 00/04/08 UTC
    off_grid = [_bare(datetime(2026, 7, 16, 4 * k, tzinfo=plus_two)) for k in range(3)]  # 22/02/06 UTC
    assert [soak._on_grid(r.cycle_ts) for r in on_grid] == [True, True, True]
    assert [soak._on_grid(r.cycle_ts) for r in off_grid] == [False, False, False]
    assert [r.cycle_ts for r in select_clean_segment(on_grid)] == [r.cycle_ts for r in on_grid]
    assert select_clean_segment(off_grid) == []
```

Run: `uv run pytest -q tests/test_engine_soak.py -k zoned_stamp`
Expected: `1 passed`: `_on_grid` reads the instant already and the case pins it, so a later reading of the local hour fails here; Step 8's tenth probe, the one over `cli/engine/soak.py`, proves the pin bites.

- [ ] **Step 2: The door in `cli/engine/store.py`**

Replace the line `from cli.ohlc.dataset import read_parquet, to_frame, write_parquet` with:

```python
from cli.ohlc.dataset import FRAME_SCHEMA, read_parquet, to_frame, write_parquet
```

Replace the whole of `_require_joinable_ts`, from the line `def _require_joinable_ts(frame: pl.DataFrame, path: Path, pair: str, interval: int, fn_name: str, *, frozen: bool) -> None:` through the line `    )` that closes its `raise EngineError(`, with:

```python
_HOST_REDELIVERY = (
    "on the engine host the store is re-delivered, not seeded: infra/runbooks/engine.md's zcrypto-engine-cycle-stale "
    "section holds the procedure, and `zcrypto engine seed` is the workstation's command"
)
_STORE_RECOVERY = (
    "on the workstation move this leg aside (outside the store) and run `zcrypto engine seed`, which copies the "
    "canonical for the absent file and fills the gap from REST; what is lost is any bar past the canonical's tail that "
    "REST no longer reaches, and when the canonical's tail is itself outside the REST window the seed refuses on its own "
    f"shortfall until the next quarterly ingest is minted; {_HOST_REDELIVERY}"
)
_CANONICAL_RECOVERY = (
    "nothing was copied to the store; a canonical is the data pipeline's to republish: rebuild the set "
    "(`zcrypto data rebuild ohlc-full --no-push` mints the newer stamped sibling the seed reads once it is whole) rather "
    "than recast this file, whose `dataset_hash` a recast changes and nothing in this tree re-vouches"
)
_REST_REFUSED = (
    "nothing from this fetch is written, so there is no store repair: the store holds what it held before the fetch, "
    "the next run fetches again, and a row that returns is the venue's to answer, not the store's"
)


def _frame_differences(frame: pl.DataFrame, interval: int) -> list[str]:
    """What keeps `frame` from being the frame the store readers join, the first arm that fails in the order a later arm
    presumes the earlier: the whole of `FRAME_SCHEMA` (each dtype, no other column), its column order, then the keys (rows,
    no null stamp, no repeated stamp, each stamp on the leg's epoch-anchored `interval` grid), then the value (a present
    close finite and positive; `None` is an absent bar and passes). Empty when nothing differs."""
    differs = [
        f"{column} is {frame.schema[column]}, not {dtype}" if column in frame.schema else f"{column} is absent"
        for column, dtype in FRAME_SCHEMA.items()
        if frame.schema.get(column) != dtype
    ]
    differs += [f"{column} is not a column of it" for column in frame.schema if column not in FRAME_SCHEMA]
    if differs:
        return differs
    if frame.columns != list(FRAME_SCHEMA):
        return [f"the columns are in another order ({', '.join(frame.columns)})"]
    if frame.is_empty():
        return ["it has no rows"]
    stamps = frame["ts"]
    if stamps.null_count():
        return [f"ts is null in {stamps.null_count()} row(s)"]
    if stamps.n_unique() != frame.height:
        return [f"{frame.height - stamps.n_unique()} row(s) repeat a stamp another row carries"]
    off_grid = frame.filter(pl.col("ts").dt.epoch("s") % (interval * 60) != 0)
    if off_grid.height:
        return [f"{off_grid.height} stamp(s) are off the {interval}-minute grid, the first {off_grid['ts'][0].isoformat()}"]
    unusable = frame.with_row_index().filter(
        pl.col("close").is_not_null() & (pl.col("close").is_nan() | pl.col("close").is_infinite() | (pl.col("close") <= 0))
    )
    if unusable.height:
        k, stamp, close = unusable["index"][0], unusable["ts"][0], unusable["close"][0]
        return [f"close[{k}] at {stamp.isoformat()} is {close!r}, not a finite positive number ({unusable.height} such close(s))"]
    return []


def _require_store_frame(frame: pl.DataFrame, path: Path, pair: str, interval: int, fn_name: str, *, frozen: bool) -> None:
    """Refuse a frame the store readers cannot join, merge or price, before the seam, the concat or the snapshot write
    gets it: `_frame_differences` is the check, and `frozen` picks the recovery, which is why the caller says which file
    it handed over. `seed_store` runs this over the canonical BEFORE the copy, so a refused canonical leaves no store
    file for the next run to refuse under the store's recovery; `to_frame` writes exactly this schema, so no schema or
    order arm refuses a frame this tree wrote, and an off-grid stamp or an unusable close in a venue's own row is
    refused at `_require_rest_frame` below, in the fetch that carries it, before a merge makes it resident. Sibling:
    `cli/ohlc/reach.py::_read_canonical` holds a canonical the same way for the reach."""
    differs = _frame_differences(frame, interval)
    if differs:
        raise EngineError(
            f"{fn_name}: {path} is not the frame the store readers join for {pair}@{interval} -- {'; '.join(differs)}; "
            f"{_CANONICAL_RECOVERY if frozen else _STORE_RECOVERY}"
        )


def _require_rest_frame(frame: pl.DataFrame, pair: str, interval: int, fn_name: str) -> None:
    """Hold the REST fetch to the same width before the merge makes one of its rows resident: a stamp off the grid or
    an unusable present close in the venue's own row is what `to_frame` admits, and one in the store would be refused
    at every later boundary and written back by every re-seed, the seed filling the gap from this same window. The
    refusal is the venue's, so it names the fetch rather than a file and prescribes no repair and no edit. The schema,
    order and stamp-set arms cannot fire on a frame `to_frame` wrote, so what this catches is the grid arm and the
    value arm; an empty fetch is left to the seam, whose shortfall names it with its own recovery."""
    if frame.is_empty():
        return
    differs = _frame_differences(frame, interval)
    if differs:
        raise EngineError(
            f"{fn_name}: the REST fetch for {pair}@{interval} is not the frame the store readers join -- "
            f"{'; '.join(differs)}; {_REST_REFUSED}"
        )
```

Then rename the three call sites: `grep -c '_require_joinable_ts(' cli/engine/store.py` prints `3` once `_require_joinable_ts`'s own block above has been replaced by the fence (`4` on the tree before that, the `def` line matching beside the three calls) and, after the replacement of every `_require_joinable_ts(` by `_require_store_frame(` on those three lines, `0`.

Then the REST door's two call sites: `grep -c 'rest_frame = drop_in_progress(' cli/engine/store.py` prints `2`, one line in `seed_store` and one in `refresh_store`, each followed by a blank line and that reader's own `_reconcile(` call. Below the one in `seed_store`, the one above `            overlap_bars, replaced, merged = _reconcile(`, insert:

```python
            _require_rest_frame(rest_frame, pair, interval, "seed_store")
```

and below the one in `refresh_store`, the one above `            _, _, merged = _reconcile(`, the same line with `"refresh_store"`. `grep -c '_require_rest_frame(rest_frame' cli/engine/store.py` then prints `2`. In `read_store_series`' docstring replace `(`_require_joinable_ts` above owns the exact dtype)` with `(`_require_store_frame` above owns the exact dtype)`, and the two paragraphs that send a reader chasing the grid and the value to the soak, the five lines from `    It reads TYPES, never the stamps' values:` through the line ending `What is refused is anything outside `int`/`float`, which`, with:

```python
    It reads TYPES, never the stamps' values: a stamp off the leg's grid passes here and is refused at the door
    above, which every reader that joins runs over the file first; `realized_series` in `cli/engine/soak.py` refuses
    one on the 4h leg it scores, the second reader, over a store no door of this module read -- the daily row's
    scratch copy.

    A non-finite close is NOT refused here either: the door above refuses it in a store file, and `realized_series`
    drops the cycle it would score and names the bar and the value on the report's `dropped_tail` line. What is
    refused here is anything outside `int`/`float`, which
```

In `cli/ohlc/reach.py` replace the docstring line `    Sibling: `cli/engine/store.py::_require_joinable_ts` holds the engine store's files under its own policy.` with `    Sibling: `cli/engine/store.py::_require_store_frame` holds the engine store's files under its own policy.`, and the two comment lines above `        stamps = frame["ts"]`, whose second ends `are open (docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md).` — Task 4 archives that file, so the path stops resolving, and D1 and D2 close the two classes it calls open for the store, which the reach's own door keeps admitting (spec `## Out of scope`) — with:

```python
        # The keys only: a null close on a shared stamp is refused at the seam below, and a non-finite close or a
        # null on an unshared stamp is admitted here, this command joining the canonical rather than pricing it.
```

Then `grep -rc '_require_joinable_ts' cli/` prints `0` for every file, and `grep -rc 'docs/open-topics/' cli/` prints `0` for every file.

Run: `uv run pytest -q tests/test_engine_store.py`
Expected: `76 passed`.

- [ ] **Step 3: The two cycle fixtures stop writing what the door refuses**

Run: `uv run pytest -q tests/test_engine_cycle.py`
Expected: `13 failed, 55 passed`: the eleven `unusable_present_close` cases fail because `refresh_store` now refuses the spoiled file at the boundary's refresh (`is not the frame the store readers join`), and `test_a_btc_stamp_the_eur_legs_lack_moves_no_eur_window` and `test_real_builder_round_trips_through_replay_cycle` fail because the `/BTC`-only stamp is off the grid (`1 stamp(s) are off the 1440-minute grid`).

Replace the whole of `_spoil`, from `def _spoil(store_dir: Path, symbol: str, interval: int, bars: dict[int, float]) -> dict[int, datetime]:` through `    return {bar: stamps[bar] for bar in bars}`, with:

```python
def _spoil(monkeypatch, store_dir: Path, symbol: str, interval: int, bars: dict[int, float]) -> dict[int, datetime]:
    """Hand `run_cycle` the closes at `bars` (row index -> value) in one series as `read_store_series` returns them,
    past the store door, which refuses each of these values in the file at the refresh: the write door is then the one
    refusal left on the path, the shape of a value that reached the read without passing that door. Returns each row's
    stamp, read off the file."""
    base, quote = symbol.split("/")
    stamps = read_parquet(store_dir / base / quote / f"{interval}.parquet")["ts"].to_list()
    real = cycle.read_store_series

    def spoiled(root: Path, sym: str, iv: int) -> tuple[list[datetime], list[float | None]]:
        ts, closes = real(root, sym, iv)
        if (sym, iv) == (symbol, interval):
            for bar, value in bars.items():
                closes[bar] = value
        return ts, closes

    monkeypatch.setattr(cycle, "read_store_series", spoiled)
    return {bar: stamps[bar] for bar in bars}
```

Its three calls gain `monkeypatch` as the first argument: `    stamp = _spoil(config.store_dir, symbol, interval, {bar: bad})[bar]` becomes `    stamp = _spoil(monkeypatch, config.store_dir, symbol, interval, {bar: bad})[bar]`; `    _spoil(config.store_dir, "ETH/BTC", 240, {1: float("nan"), 2: float("nan")})` becomes `    _spoil(monkeypatch, config.store_dir, "ETH/BTC", 240, {1: float("nan"), 2: float("nan")})`; `    daily_stamp = _spoil(config.store_dir, "XRP/EUR", 1440, {1: 0.0})[1]` becomes `    daily_stamp = _spoil(monkeypatch, config.store_dir, "XRP/EUR", 1440, {1: 0.0})[1]`. `grep -c '_spoil(monkeypatch, ' tests/test_engine_cycle.py` prints `4`, the renamed def line and its three calls.

Replace the four lines

```python
# An interior stamp near the tail. Near the tail is load-bearing: an all-None row further back
# washes out of the builder's windows, and the pin would sit green either way (measured).
_BTC_ONLY_INSERT_AT = -5
_BTC_ONLY_OFFSET = {1440: timedelta(hours=5), 240: timedelta(hours=1)}  # off both grids, so no EUR leg has it
```

with:

```python
# An interior stamp near the tail that the two /BTC legs carry and the ten EUR legs skip: on the grid, since the
# store door refuses a stamp off it. Near the tail is load-bearing: an all-None row further back washes out of the
# builder's windows, and the pin would sit green either way (measured).
_BTC_ONLY_INSERT_AT = -5
```

Replace the whole of `_real_rows` with:

```python
def _real_rows(symbol: str, interval: int, *, eur_gap: bool = False) -> list[list]:
    ts = list(_REAL_DAILY_TS if interval == 1440 else _REAL_H4_TS)
    closes = _real_closes(symbol, len(ts), 1 if interval == 1440 else 6)
    if eur_gap:
        at = len(ts) + _BTC_ONLY_INSERT_AT
        ts, closes = ts[:at] + ts[at + 1 :], closes[:at] + closes[at + 1 :]
    return [_row(t, c) for t, c in zip(ts, closes)]
```

In `_real_store_rows` replace the line `        (symbol, interval): _real_rows(symbol, interval, btc_only_stamp=btc_only_stamp and symbol in BTC_SYMBOLS)` with `        (symbol, interval): _real_rows(symbol, interval, eur_gap=btc_only_stamp and symbol in EUR_SYMBOLS)`.

Replace the first six lines of `_standalone_ten_asset_targets`, from `def _standalone_ten_asset_targets() -> dict[str, float]:` through `    result = build_crossfreq_system_fast(daily, list(_REAL_DAILY_TS), h4, list(_REAL_H4_TS))`, with:

```python
def _standalone_ten_asset_targets(*, eur_gap: bool = False) -> dict[str, float]:
    """build_crossfreq_system_fast over the ten EUR series ALONE, base-keyed: the model exactly as it
    exists today, with nothing else in the room; `eur_gap` skips the stamp `_real_rows` skips."""
    daily_ts, h4_ts = list(_REAL_DAILY_TS), list(_REAL_H4_TS)
    daily = {s.split("/")[0]: _real_closes(s, _REAL_N_DAILY, 1) for s in EUR_SYMBOLS}
    h4 = {s.split("/")[0]: _real_closes(s, _REAL_N_H4, 6) for s in EUR_SYMBOLS}
    if eur_gap:
        for ts, closes in ((daily_ts, daily), (h4_ts, h4)):
            at = len(ts) + _BTC_ONLY_INSERT_AT
            del ts[at]
            for series in closes.values():
                del series[at]
    result = build_crossfreq_system_fast(daily, daily_ts, h4, h4_ts)
```

In `test_a_btc_stamp_the_eur_legs_lack_moves_no_eur_window`, replace its docstring and body down to the `standalone = ` line, the text from `    """The calendar pin (spec 00094 D2): a fixture whose twelve-symbol stamp union differs from the` through `    standalone = _standalone_ten_asset_targets()`, with:

```python
    """The calendar pin (spec 00094 D2): a fixture whose twelve-symbol stamp union differs from the
    ten-EUR union -- one on-grid stamp per grid the /BTC legs carry and the EUR legs skip -- leaves every
    EUR target identical to the standalone build over the same ten EUR series."""
    config = _real_env(tmp_path, monkeypatch)
    rows_by = _real_store_rows(btc_only_stamp=True)
    _write_store(config.store_dir, rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    # The perturbation really did reach the pipeline: the twelve-symbol union carries the stamp the
    # EUR legs skip (so the journaled snapshots do too), and the contraction is what drops it again.
    raw = {symbol: read_store_series(config.store_dir, symbol, 240) for symbol in ASSETS}
    assert len({t for ts, _ in raw.values() for t in ts}) == _REAL_N_H4
    assert len(select_model_inputs(raw)[0]) == _REAL_N_H4 - 1
    snapshots = {(e.pair, e.grid): e for e in from_json(result.record_path.read_text()).snapshots}
    assert snapshots[("BTC/EUR", "240")].n_bars == _REAL_N_H4

    standalone = _standalone_ten_asset_targets(eur_gap=True)
```

`grep -c '_BTC_ONLY_OFFSET' tests/test_engine_cycle.py` prints `0`; `test_real_builder_round_trips_through_replay_cycle` and the `_tiny_series` cases are untouched.

Run: `uv run pytest -q tests/test_engine_cycle.py`
Expected: `68 passed`.

- [ ] **Step 4: The consumers**

Run the consumer command of the Global Constraints.
Expected: every test passed or skipped by a data gate, none failed.

- [ ] **Step 5: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite (ruff's import sort may reorder the `cli.ohlc.dataset` line) until clean, then stage what it rewrote.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/store.py cli/ohlc/reach.py tests/test_engine_store.py tests/test_engine_cycle.py tests/test_engine_soak.py
git commit -m "fix(engine): the store door holds a frame to its whole width and names one recovery

\`_require_store_frame\` replaces \`_require_joinable_ts\` at its three call sites in \`cli/engine/store.py\`
over \`_frame_differences\`, which returns the first failing arm's differences in the order a later
arm presumes the earlier: the whole of \`FRAME_SCHEMA\` with no other column, the column order, no
rows, a null stamp, a repeated stamp, a stamp off the leg's epoch-anchored grid on either interval,
and a present close that is not a finite positive number, \`None\` admitted as an absent bar. The
message names the file, the pair, the grid and the differences the way \`_read_canonical\` in
\`cli/ohlc/reach.py\` does, and the recovery \`frozen\` picks: for a store file one text for every arm,
move the leg aside on the workstation and run \`zcrypto engine seed\`, which copies the canonical for
the absent file and fills the gap from REST, the loss any bar past the canonical's tail that REST
no longer reaches, then the engine host's re-delivery by the runbook; for a canonical, nothing was
copied and the set is the data pipeline's to republish. The in-place ts recast text and the
promotion clause leave the tree. \`seed_store\` holds the canonical to the same width before the copy,
as it held the two dtypes.

\`_require_rest_frame\` holds the REST fetch to that same width in both readers, after
\`drop_in_progress\` and before the merge, since a row the venue's own answer carries that the door
refuses would otherwise be written and then refused at every later boundary, and the seed the store
recovery prescribes would fill it back from the same window at every re-seed. Only the grid and the
value arms can fire there, \`to_frame\` being the fetch's writer, and an empty fetch is left to the
seam's shortfall; the refusal names the fetch rather than a file and carries \`_REST_REFUSED\` alone:
nothing from this fetch is written, there is no store repair, the next run fetches again, and a row
that returns is the venue's to answer.

Cases: two readers over five schema deviations, four key deviations on both grids with the file
asserted unchanged, four values, a null close at an unshared stamp admitted, six deviated canonicals
refused before the copy with no store file written, two readers over a REST fetch carrying an
off-grid row and one carrying a negative close, with the leg asserted as it was, the three earlier
pins re-pinned on the one recovery. Two cycle fixtures stop writing what the door refuses:
\`_spoil\` hands the snapshot-write
cases their values past the door, and the calendar pin's /BTC-only stamp moves onto the grid as a
stamp the EUR legs skip, the standalone build over the same skipped series. The soak's grid predicate,
which the door's grid arm mirrors, is pinned on a zoned stamp: an aware +02:00 stamp on the UTC
grid enters the clean segment and one on its own wall clock's marks does not.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

- [ ] **Step 7: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 8: Prove the guards with eleven probes, then record their verdicts by a message-only amend**

The control changes the join phrase every width case asserts. The nine mutations over the door remove the schema arm, the column-order arm, the no-rows arm, the null-stamp arm, the repeated-stamp arm and the grid arm, admit a zero close, narrow the value filter so the null close the door admits is refused, and remove the canonical check before the copy -- the repeated stamp and the off-grid stamp, the two shapes nothing in the tree stops today, each get their own; the tenth comments out the REST door in both readers, under the same control and the four cases that arm owns; and the eleventh, over `cli/engine/soak.py`, makes `_on_grid` read the local hour, its control inverting the predicate:

```bash
K="off_the_schema or unsound_stamps or unusable_present_close or null_close_at_an_unshared or deviated_canonical or unjoinable_ts_column"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/if frame.schema.get(column) != dtype/if False/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/if frame.columns != list(FRAME_SCHEMA):/if False:/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/if frame.is_empty():/if False:/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/if stamps.null_count():/if False:/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/if stamps.n_unique() != frame.height:/if False:/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/if off_grid.height:/if False:/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/(pl.col("close") <= 0)/(pl.col("close") < 0)/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/pl.col("close").is_not_null() &/pl.col("close").is_null() |/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/_require_store_frame(canonical_frame, canonical_path, pair, interval, "seed_store", frozen=True)/pass/' \
  -- uv run pytest -q tests/test_engine_store.py -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/is not the frame the store readers join/is not the frame the store readers use/' \
  --mutation 's/^            _require_rest_frame(/            pass  # _require_rest_frame(/' \
  -- uv run pytest -q tests/test_engine_store.py -k rest_row_the_venue_carries
infra/scripts/mutate-probe.sh --file cli/engine/soak.py \
  --control 's/== timedelta(0)/!= timedelta(0)/' \
  --mutation 's/return (ts - _EPOCH) % timedelta(hours=4) == timedelta(0)/return ts.hour % 4 == 0 and ts.minute == 0/' \
  -- uv run pytest -q tests/test_engine_soak.py -k zoned_stamp
```

Expected: each run ends `KILLED` with `control proven`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/store.py`, control the join phrase of the
message changed so every width case's match fails; through `-k "off_the_schema or unsound_stamps or
unusable_present_close or null_close_at_an_unshared or deviated_canonical or unjoinable_ts_column"`:
the schema arm removed, KILLED, control proven; the column-order arm removed, KILLED, control
proven; the no-rows arm removed, KILLED, control proven; the null-stamp arm removed, KILLED, control
proven; the repeated-stamp arm removed, KILLED, control proven; the grid arm removed, KILLED,
control proven; a zero close admitted, KILLED, control proven; the value filter narrowed to refuse
an admitted null close, KILLED, control proven; the canonical check before the copy removed, KILLED,
control proven; the REST door commented out in both readers, through `-k rest_row_the_venue_carries`
under the same control, KILLED, control proven; over `cli/engine/soak.py`, control the grid predicate
inverted, `_on_grid` reading the local hour through `-k zoned_stamp`: KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 2: The three carriers route the repair by host, and the seam's absent close by side

**Files:**
- Modify: `cli/engine/store.py` (three constants after `_CANONICAL_RECOVERY`; `_reconcile`'s signature tail, docstring and absent-close `raise`; the `shortfall_hint=` and `mismatch_hint=` lines of both `_reconcile(` calls)
- Modify: `cli/engine/command.py` (the line `from cli.engine.store import BASKET, GRID_INTERVALS, PAIR_KEYS, _store_path, seed_store`; the two-line message of `run`'s `raise _abort(` over `missing`)
- Modify: `cli/engine/soak.py` (the line `from cli.engine.store import BASKET, GRID_INTERVALS, _store_path, read_store_series`; the `raise EngineError(` of `realized_series`' off-grid refusal)
- Modify: `cli/engine/cycle.py` (the last line of `run_cycle`'s docstring)
- Test: `tests/test_engine_store.py` (two assertion lines replaced in each of the two REST-side absent-close cases, one of them an insert; three cases appended at the end of the file)
- Test: `tests/test_engine_command.py` (`test_run_aborts_when_the_store_holds_every_eur_leg_but_neither_btc_leg`, two assertions appended)
- Test: `tests/test_engine_soak.py` (`test_realized_series_refuses_an_interior_off_grid_stamp_on_a_non_btc_leg`, three assertions appended)

**Interfaces:**
- Consumes: `_HOST_REDELIVERY` and `_STORE_RECOVERY` from Task 1; `_rows_from`, `DAILY_START`, `N_CANON`, `_canonical_rows`, `_write_full_universe`, `_good_fetch_fn`, `_good_rest_rows`, `_fetch_override`, `read_store_series` in `tests/test_engine_store.py`, `_run_env`, `runner`, `app`, `_output` in `tests/test_engine_command.py`, existing.
- Produces: `_ABSENT_REST_HINT`, `_FRESH_COPY`, `_RESEED_REFUSED`; `_reconcile(..., absent_store_hint, absent_rest_hint)`, whose two callers are its only ones (`grep -rn '_reconcile(' cli/ tests/` names the definition and those two).

- [ ] **Step 1: The routed cases, the side cases and the re-pinned REST-side lines**

In `tests/test_engine_store.py`, `test_refresh_store_refuses_an_absent_close_on_a_shared_stamp`, replace the line `    assert "zcrypto engine seed" in msg`, the one followed by `    _, closes = read_store_series(store_dir, "BTC/EUR", 1440)`, with:

```python
    assert "no store repair" in msg and "zcrypto engine seed" not in msg  # the null is the fetch's, not the store's
```

and, in the same case, its line `    assert f"overlap mismatch for BTC/EUR@1440 at {stamp}" in msg` with:

```python
    assert "overlap mismatch for BTC/EUR@1440" in msg and f"the REST fetch (first at {stamp})" in msg
```

In `test_seed_store_reseed_refuses_an_absent_close_and_keeps_the_store_close`, after the line `    assert "absent on the REST fetch" in msg` insert:

```python
    assert "fresh canonical copy" not in msg  # the store pre-existed: nothing was copied
```

and replace that case's line `    assert f"overlap mismatch for BTC/EUR@1440 at {stamp}" in msg` with:

```python
    assert "overlap mismatch for BTC/EUR@1440" in msg and f"the REST fetch (first at {stamp})" in msg
```

Append at the end of the file:

```python
@pytest.mark.parametrize("fault", ["shortfall", "mismatch"])
def test_refresh_store_hints_route_the_repair_by_host(tmp_path, fault):
    """`refresh_store` runs at each boundary on the engine host, where `zcrypto engine seed` does not exist."""
    store_dir = tmp_path / "store"
    write_parquet(to_frame(_rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)), _store_path(store_dir, "BTC/EUR", 1440))
    if fault == "shortfall":
        rest = _rows_from(DAILY_START, timedelta(days=1), 100, 5)
    else:
        rest = _rows_from(DAILY_START, timedelta(days=1), N_CANON - 3, 3)
        for row in rest:
            row[4] = str(float(row[4]) + 500.0)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: rest, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "on the engine host the store is re-delivered, not seeded" in msg and "zcrypto-engine-cycle-stale" in msg
    assert "`zcrypto engine seed` is the workstation's command" in msg
    if fault == "shortfall":
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    else:
        assert "whose re-seed over an existing file replaces the disagreeing tail inside the REST window" in msg


@pytest.mark.parametrize("side", ["store", "rest", "both"])
def test_refresh_store_routes_an_absent_close_by_the_side_that_holds_it(tmp_path, side):
    """The absent-close refusal runs whatever `allow_replace` is, so a null on the store tail is a refused store file a
    plain re-seed refuses again, and a null in the REST fetch is nothing the store repairs. Under `both` the REST null
    is the earlier row, so a side or a stamp read off the first absent row alone sends the store's own null to the
    fetch's hint, at a stamp whose store close is present."""
    store_dir = tmp_path / "store"
    rows = _rows_from(DAILY_START, timedelta(days=1), 0, N_CANON)
    rest = _rows_from(DAILY_START, timedelta(days=1), N_CANON - 3, 4)
    if side == "store":
        rows[N_CANON - 2][4] = None
    elif side == "rest":
        rest[1][4] = None
    else:
        rest[0][4] = None
        rows[N_CANON - 1][4] = None
    write_parquet(to_frame(rows), _store_path(store_dir, "BTC/EUR", 1440))
    store_stamp = DAILY_START + timedelta(days=N_CANON - 1 if side == "both" else N_CANON - 2)
    rest_stamp = DAILY_START + timedelta(days=N_CANON - 3 if side == "both" else N_CANON - 2)

    with pytest.raises(EngineError) as exc:
        refresh_store(store_dir, pairs={"BTC/EUR": "XXBTZEUR"}, fetch_fn=lambda pk, iv: rest, clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "overlap mismatch for BTC/EUR@1440" in msg
    if side == "rest":
        assert f"absent on the REST fetch (first at {rest_stamp})" in msg and "no store repair" in msg
        assert "move this leg aside" not in msg and "zcrypto engine seed" not in msg
    else:
        assert f"the store tail (first at {store_stamp})" in msg and "a re-seed over this file refuses again" in msg
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
        assert "on the engine host the store is re-delivered, not seeded" in msg
    if side == "both":
        assert f"absent on the store tail (first at {store_stamp}) and the REST fetch (first at {rest_stamp})" in msg
        assert "@1440 at " not in msg  # one headline stamp cannot be true of two sides absent at different rows
    _, closes = read_store_series(store_dir, "BTC/EUR", 1440)
    assert len(closes) == N_CANON  # refused, not rewritten


@pytest.mark.parametrize("case", ["existing store", "fresh copy", "fresh copy rest null"])
def test_seed_store_claims_a_fresh_copy_for_an_absent_close_only_when_it_copied(tmp_path, case):
    """Over an existing store the seed copies nothing, so its refusal of a null on the store tail must not call the
    file a fresh canonical copy: the leg is a refused store file, moved aside before the seed that does copy. On a
    fresh copy the claim holds on either side, the canonical's own null and a null the REST fetch brings."""
    canonical_dir = tmp_path / "canonical"
    store_dir = tmp_path / "store"
    rest_null = case == "fresh copy rest null"

    def _nulled(interval: int) -> list[list]:
        rows = _canonical_rows(interval)
        if interval == 1440 and not rest_null:
            rows[N_CANON - 4][4] = None
        return rows

    _write_full_universe(canonical_dir, _nulled)
    if case == "existing store":
        _write_full_universe(store_dir, _nulled)
    rest = _good_rest_rows(1440)
    if rest_null:
        rest[2][4] = None
    stamp = DAILY_START + timedelta(days=N_CANON - 4)

    with pytest.raises(EngineError) as exc:
        seed_store(store_dir, canonical_dir, fetch_fn=_fetch_override("ADAEUR", 1440, rest), clock=lambda: FAR_FUTURE)

    msg = str(exc.value)
    assert "overlap mismatch for ADA/EUR@1440" in msg
    if rest_null:
        assert f"absent on the REST fetch (first at {stamp})" in msg
        assert "this is a fresh canonical copy" in msg and "no store repair" in msg
        assert "move this leg aside" not in msg
    elif case == "existing store":
        assert f"absent on the store tail (first at {stamp})" in msg
        assert "fresh canonical copy" not in msg
        assert "the re-seed replaced nothing, because the seam refused" in msg
        assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    else:
        assert f"absent on the store tail (first at {stamp})" in msg
        assert "this is a fresh canonical copy" in msg and "whose copy already landed" in msg
        assert "move this leg aside (outside the store) and rebuild the set" in msg
```

In `tests/test_engine_command.py`, `test_run_aborts_when_the_store_holds_every_eur_leg_but_neither_btc_leg`, after the line `    assert str(tmp_path / "store") in out` append:

```python
    # `run` is the node's own entry point, so its recovery is the host's, never the workstation's command.
    assert "on the engine host the store is re-delivered, not seeded" in out and "zcrypto-engine-cycle-stale" in out
    assert "`zcrypto engine seed` is the workstation's command" in out
```

In `tests/test_engine_soak.py`, `test_realized_series_refuses_an_interior_off_grid_stamp_on_a_non_btc_leg`, after the line `    assert "BTC/EUR" not in msg` insert:

```python
    assert "move this leg aside (outside the store) and run `zcrypto engine seed`" in msg
    assert "on the engine host the store is re-delivered, not seeded" in msg
    assert "the scratch leg is not the one to move" in msg
```

Run: `uv run pytest -q tests/test_engine_store.py -k "route_the_repair or absent_close or fresh_copy"`
Expected: `10 failed`: the two routed cases on the routed clause, the two re-pinned REST-side cases on the workstation command, the fresh-copy claim and the per-side stamp, the three side cases and the three fresh-copy cases on the hints and that stamp.
Run: `uv run pytest -q tests/test_engine_command.py -k neither_btc_leg`
Expected: `1 failed`, on the routed clause.
Run: `uv run pytest -q tests/test_engine_soak.py -k off_grid_stamp_on_a_non_btc_leg`
Expected: `1 failed`, on the move-aside recovery.

- [ ] **Step 2: The hints, the side arm and the refusals**

In `cli/engine/store.py`, after the `)` that closes `_REST_REFUSED`, the last of Task 1's four constants, insert:

```python
_ABSENT_REST_HINT = (
    "the REST fetch carries the absent close, so there is no store repair: the next run fetches again, and a fetch "
    "that returns it again is the venue's row to read, not the store's"
)
_FRESH_COPY = "this is a fresh canonical copy, so a disagreement with REST is a data-integrity error"
_RESEED_REFUSED = "the re-seed replaced nothing, because the seam refused before the replace"
```

In `_reconcile`, replace the six lines from `    shortfall_hint: str,` through the docstring's last line, `    Sibling: cli/ohlc/reach.py::_merge_or_detach guards the same seam definition under its own policy."""`, with:

```python
    shortfall_hint: str,
    mismatch_hint: str,
    absent_store_hint: str,
    absent_rest_hint: str,
) -> tuple[int, int, pl.DataFrame]:
    """Returns `(overlap_bars, replaced_tail_rows, merged_frame)` positionally. `mismatch_hint` ends a price
    disagreement's refusal; an absent close at a shared stamp is refused whatever `allow_replace` is, ending with
    `absent_store_hint` when the store side holds one among the absent rows (the leg is then a refused store file)
    and with `absent_rest_hint` when the REST fetch alone does (nothing in the store is wrong); each side is read over
    all the absent rows and carries its own first absent stamp, since the first row's side and stamp are that row's
    alone and the two sides can be absent at different rows.

    Sibling: cli/ohlc/reach.py::_merge_or_detach guards the same seam definition under its own policy."""
```

and, in the `absent.height` branch, the eleven lines from `        stamp = absent["ts"][0]` through the `        )` that closes its `raise EngineError(`, whose last f-string reads `f"re-seed replaces a store close with it; {mismatch_hint}"`, with:

```python
        sides = [
            f"{name} (first at {absent.filter(pl.col(column).is_null())['ts'][0]})"
            for name, column in (("the store tail", "close"), ("the REST fetch", "close_rest"))
            if absent[column].null_count()
        ]
        hint = absent_store_hint if absent["close"].null_count() else absent_rest_hint
        raise EngineError(
            f"{fn_name}: overlap mismatch for {pair}@{interval} — a shared stamp's close is absent on "
            f"{' and '.join(sides)}, and an absent close is a disagreement whatever the other side carries, so no "
            f"re-seed replaces a store close with it; {hint}"
        )
```

The `stamp` the branch read off the absent set's first row goes with it: each side carries the first stamp at which that side is absent, so the operator who opens the store leg at the stamp the refusal names finds the null there. One headline stamp is the first absent row's, whose side is that row's alone, so on a mixed overlap it names a stamp where the accused store side holds a finite close -- the read D7 makes a precondition of purging the aside copy. The price-disagreement branch below keeps its own `stamp = mismatches["ts"][0]`, one row and one side.

In `seed_store`, replace the three lines from `                shortfall_hint="use the quarterly OHLCVT dump",` through the `            )` that closes its `_reconcile(` call with:

```python
                shortfall_hint="use the quarterly OHLCVT dump",
                mismatch_hint=_FRESH_COPY,
                absent_store_hint=(
                    f"{_FRESH_COPY} in the canonical, whose copy already landed: move this leg aside (outside the store) "
                    "and rebuild the set (`zcrypto data rebuild ohlc-full --no-push` mints the newer stamped sibling the "
                    "next seed reads once it is whole)"
                    if not store_existed
                    else f"{_RESEED_REFUSED}, and a re-seed over this file refuses the same absent close -- {_STORE_RECOVERY}"
                ),
                absent_rest_hint=f"{_FRESH_COPY if not store_existed else _RESEED_REFUSED}; {_ABSENT_REST_HINT}",
            )
```

In `refresh_store`, replace the three lines from ``                shortfall_hint="the store is catastrophically stale, run `zcrypto engine seed` to re-seed it",`` through the `            )` that closes its `_reconcile(` call with:

```python
                shortfall_hint=f"the store is catastrophically stale, past the REST window's reach -- {_STORE_RECOVERY}",
                mismatch_hint=(
                    "the store tail may be poisoned -- on the workstation run `zcrypto engine seed`, whose re-seed over "
                    f"an existing file replaces the disagreeing tail inside the REST window; {_HOST_REDELIVERY}"
                ),
                absent_store_hint=(
                    f"the store tail holds the absent close, which a re-seed over this file refuses again -- {_STORE_RECOVERY}"
                ),
                absent_rest_hint=_ABSENT_REST_HINT,
            )
```

In `cli/engine/command.py` replace the line `from cli.engine.store import BASKET, GRID_INTERVALS, PAIR_KEYS, _store_path, seed_store` with:

```python
from cli.engine.store import _HOST_REDELIVERY, BASKET, GRID_INTERVALS, PAIR_KEYS, _store_path, seed_store
```

and, in `run`, the two lines

```python
            f"basket series a cycle reads: {', '.join(missing)} -- a node without a complete store is always "
            "misconfigured; fix the bind-mount or run `zcrypto engine seed`"
```

with:

```python
            f"basket series a cycle reads: {', '.join(missing)} -- a node without a complete store is always "
            f"misconfigured; fix the bind-mount, or have the converge deliver the store, whose copy runs for an absent "
            f"store alone: {_HOST_REDELIVERY}"
```

In `cli/engine/soak.py` replace the line `from cli.engine.store import BASKET, GRID_INTERVALS, _store_path, read_store_series` with:

```python
from cli.engine.store import _STORE_RECOVERY, BASKET, GRID_INTERVALS, _store_path, read_store_series
```

and, in `realized_series`, the off-grid refusal's seven lines from `            raise EngineError(` through `            )`, whose last string reads `"infra/runbooks/engine.md's zcrypto-engine-cycle-stale section says"`, with:

```python
            raise EngineError(
                f"realized_series: the store's 240 leg for {asset} holds {len(off_grid)} stamp(s) off the 4h grid "
                f"(00/04/08/12/16/20 UTC), the first {off_grid[0].isoformat()} -- the stamps are the wrong instants, not "
                f"a short store; {_STORE_RECOVERY}; if this run is the daily row's, the store is the newest record's "
                "snapshots copied aside, union-aligned across the basket, so the stamp was in a leg of the host store at "
                "that cycle and the scratch leg is not the one to move"
            )
```

In `cli/engine/cycle.py`, in `run_cycle`'s docstring, replace the line ``    re-delivery, on the workstation `zcrypto engine seed`."""`` with:

```python
    re-delivery, on the workstation `zcrypto engine seed`, the refused leg moved aside first where the refusal says
    so."""
```

Run: `uv run pytest -q tests/test_engine_store.py tests/test_engine_command.py`
Expected: `149 passed`.
Run: `uv run pytest -q tests/test_engine_soak.py`
Expected: `180 passed` where `data/ohlc-full/BTC/EUR/240.parquet` is present, `177 passed, 3 skipped` where it is absent -- the three skips are that file's own `skipif` gates, which read `canonical data/ohlc-full absent`, and none of them is this change's.
Run: `uv run pytest -q tests/test_engine_soak_command.py`
Expected: `40 passed`.

- [ ] **Step 3: The consumers**

Run the consumer command of the Global Constraints.
Expected: every test passed or skipped by a data gate, none failed.

- [ ] **Step 4: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite (ruff may reorder the two `cli.engine.store` imports) until clean, then stage what it rewrote.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/store.py cli/engine/command.py cli/engine/soak.py cli/engine/cycle.py tests/test_engine_store.py tests/test_engine_command.py tests/test_engine_soak.py
git commit -m "fix(engine): the store's workstation-command carriers route the repair by host, and the seam's absent close by side

\`refresh_store\` runs at every boundary on the engine host, where \`zcrypto engine seed\` does not
exist, and \`run\` is the node's own entry point: each of the three texts that prescribed the
workstation command now ends with \`_HOST_REDELIVERY\`, on the engine host the store is re-delivered,
not seeded, by the procedure infra/runbooks/engine.md's cycle-stale section holds. The shortfall
hint carries the door's store recovery whole, since a store with no shared stamp against REST is
refused by the seed's own six-stamp seam and the leg has to be moved aside; the mismatch hint, which
ends a price disagreement, keeps the plain seed, whose re-seed replaces the disagreeing tail; \`run\`'s
bind-mount refusal says the converge delivers a store for an absent one.

An absent close at a shared stamp is refused whatever \`allow_replace\` is, so a null on the store
tail is a file a plain re-seed refuses again, and \`seed_store\` over an existing store called it a
fresh canonical copy though nothing was copied. \`_reconcile\` takes \`absent_store_hint\` and
\`absent_rest_hint\` beside \`mismatch_hint\` and picks by the side that holds the null, each side
named with the first stamp at which that side is absent rather than the absent set's first stamp,
which on a mixed overlap is the other side's: the store side carries the store recovery, the leg
moved aside and the seed, and \`seed_store\` says the re-seed replaced nothing because the seam
refused; the REST side names the fetch and prescribes no store repair. The fresh-copy claim is made
only when the seed copied one. \`realized_series\`' off-grid refusal carries the same store recovery,
imported, and says that under the daily row the store is the
record's snapshots copied aside, so the scratch leg is not the one to move; \`run_cycle\`'s docstring
carries the move-aside clause.

Cases: the two \`refresh_store\` hints under a disjoint and a disagreeing REST fetch, the null on the
store tail and on the REST side under \`refresh_store\`, the null on the store tail under \`seed_store\`
over an existing store and over a fresh copy, the two REST-side cases re-pinned, the missing-BTC-legs
refusal of \`run\`, the soak's interior off-grid refusal asserting the recovery.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

- [ ] **Step 6: Prove the guards with five probes, then record their verdicts by a message-only amend**

```bash
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/catastrophically stale/hopelessly stale/' \
  --mutation 's/shortfall_hint=f"the store is catastrophically stale, past the REST window.s reach -- {_STORE_RECOVERY}",/shortfall_hint="the store is catastrophically stale, run `zcrypto engine seed` to re-seed it",/' \
  -- uv run pytest -q tests/test_engine_store.py -k "route_the_repair or zero_overlap_is_distinct or overlap_mismatch_raises"
infra/scripts/mutate-probe.sh --file cli/engine/command.py \
  --control 's/{_HOST_REDELIVERY}/{_HOST_REDELIVERY[:40]}/' \
  --mutation 's/store alone: {_HOST_REDELIVERY}"/store alone: run `zcrypto engine seed`"/' \
  -- uv run pytest -q tests/test_engine_command.py -k neither_btc_leg
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/absent on /missing on /' \
  --mutation 's/hint = absent_store_hint if \(.*\) else absent_rest_hint/hint = absent_rest_hint if \1 else absent_store_hint/' \
  -- uv run pytest -q tests/test_engine_store.py -k "absent_close or fresh_copy"
infra/scripts/mutate-probe.sh --file cli/engine/store.py \
  --control 's/absent on /missing on /' \
  --mutation 's/^                    if not store_existed$/                    if True/' \
  -- uv run pytest -q tests/test_engine_store.py -k "absent_close or fresh_copy"
infra/scripts/mutate-probe.sh --file cli/engine/soak.py \
  --control 's/off the 4h grid/off the four-hour grid/' \
  --mutation 's/a short store; {_STORE_RECOVERY}; if this run/a short store; if this run/' \
  -- uv run pytest -q tests/test_engine_soak.py -k off_grid_stamp_on_a_non_btc_leg
```

Expected: each run ends `KILLED` with `control proven`. Then replace the `PROBE_VERDICT` line by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/store.py`, control `catastrophically stale`
respelled, the shortfall hint reverted to the bare workstation command through `-k "route_the_repair
or zero_overlap_is_distinct or overlap_mismatch_raises"`: KILLED, control proven; over
`cli/engine/command.py`, control the routed clause truncated to forty characters, the bind-mount
refusal reverted to the bare workstation command through `-k neither_btc_leg`: KILLED, control proven;
over `cli/engine/store.py`, control `absent on` respelled, through `-k "absent_close or fresh_copy"`:
the absent-close sides swapped, KILLED, control proven; the fresh-copy claim made over an existing
store, KILLED, control proven; over `cli/engine/soak.py`, control `off the 4h grid` respelled, the
store recovery dropped from the off-grid refusal through `-k off_grid_stamp_on_a_non_btc_leg`: KILLED,
control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 3: The host's repair in the role, the spec, the runbook and the fleet page

**Files:**
- Modify: `infra/ansible/roles/engine/tasks/main.yml` (the eight comment lines from `# Store delivery, only when absent:` through `# ... -- then start the unit.`; the two `fail_msg` lines under `- name: assert the delivered store is readable and non-empty`)
- Modify: `docs/specs/00042-vps-deployment-design.md` (the last sentence of item 4; a section appended at the end)
- Modify: `infra/runbooks/engine.md` (four clauses of the cycle-stale bullet that begins ``- **`run_cycle` raised before journaling the boundary**``: the aside destination, the bullet's end, the sentence that identifies what raised, and the workstation-repair parenthesis)
- Modify: `docs/reference/fleet.md` (the notes cell of the `| workstation |` row)

**Interfaces:**
- Consumes: Tasks 1 and 2, whose door and routing the texts describe.
- Produces: nothing code reads; the `guidance-guard` commit-msg hook reads the runbook and fleet pages; `tests/test_internal_terms_not_operator_visible.py` reads the ansible task names and the runbook page.

- [ ] **Step 1: The engine role's delivery comment and `fail_msg`**

`grep -c '^# VPS store-poisoning repair' infra/ansible/roles/engine/tasks/main.yml` prints `1`. Replace the eight comment lines, from `# Store delivery, only when absent: converges never clobber a live store. Run a delivering converge` through `# the engine play silently skips, and the only-when-absent copy re-delivers -- then start the unit.`, with:

```yaml
# Store delivery, only when absent: converges never clobber a live store. Run a delivering converge
# after the workstation's `zcrypto engine seed` has returned, never beside it: a mid-write copy could
# deliver a truncated parquet.
#
# VPS store repair, since `zcrypto engine seed` is workstation-only and the image carries no
# canonical dataset (infra/runbooks/engine.md, zcrypto-engine-cycle-stale, holds the procedure):
# repair the leg in the workstation's data/engine-store/ first, since that is the source this copy
# delivers and a re-run delivers it again; then stop the unit, move the store dir aside beside
# itself rather than deleting it (unversioned data has no undo), re-run the engine-tagged converge
# with `-e converge_primary=true` and the digest, inside the inter-cycle gap and outside a published
# Kraken maintenance window -- the flag is required or the guard drops this host and the engine play
# silently skips -- so the only-when-absent copy re-delivers the workstation's data/engine-store/ and
# this play starts the unit; the aside dir is purged once the refused file has been read and the
# runbook's all-clear by value has landed. A seed or a boundary that refuses naming the REST fetch
# rather than a file is a row the venue itself carries: it is the venue's to answer, nothing was
# written, and no store repair or converge reaches it.
```

`grep -c 'poisoned-store runbook above' infra/ansible/roles/engine/tasks/main.yml` prints `1`. Replace the two lines under `    fail_msg: >-`, `      The delivered store looks incomplete (BTC/EUR/240.parquet missing or empty) — follow the` and `      poisoned-store runbook above: stop the unit, rm -rf the store, re-run --tags engine, start.`, with:

```yaml
      The delivered store looks incomplete (BTC/EUR/240.parquet missing or empty). This copy came from
      the workstation's data/engine-store/, so repair it there first (move that leg aside, outside the
      store, then zcrypto engine seed, on the workstation) -- a re-run delivers the same source again,
      and a seed that refuses naming the REST fetch rather than a file is a row the venue itself
      carries, which is the venue's to answer and no store repair reaches. Then, the unit still
      stopped, move this delivered copy aside too (a second store.aside-<stamp>, purged with the
      first) and re-run this converge with --tags engine, -e converge_primary=true and
      -e engine_image_digest=sha256:<full digest>, inside the inter-cycle gap and outside a published
      Kraken maintenance window checked immediately before: infra/runbooks/engine.md's
      zcrypto-engine-cycle-stale section holds the whole repair.
```

`grep -c 'rm -rf' infra/ansible/roles/engine/tasks/main.yml` prints `0`.

- [ ] **Step 2: Spec 00042's item 4, amended**

`grep -c 'rm -rf /var/lib/zcrypto-engine/store' docs/specs/00042-vps-deployment-design.md` prints `1`. In item 4 replace the text from `**Run the delivering converge away from a 4h-boundary+30-min window**` to the end of the line, which ends `stop the unit → `rm -rf /var/lib/zcrypto-engine/store` → re-run `site.yml --tags engine` (the only-when-absent copy re-delivers) → start.`, with:

```
**Run the delivering converge after the workstation's `zcrypto engine seed` has returned, never beside it** (a mid-write copy could deliver a truncated parquet), inside the inter-cycle gap and outside a published Kraken maintenance window, and read-verify one file after delivery. **VPS store repair (the code's `engine seed` repair is workstation-only — the image has no canonical dataset), amended 2026-09-21 by spec 00117 D7 and D8:** stop the unit → move the store dir aside beside itself, never delete it → re-run `site.yml --tags engine` with `-e converge_primary=true` and the digest (the only-when-absent copy re-delivers and the play starts the unit) → purge the aside dir once the refused file has been read and the runbook's all-clear by value has landed; `infra/runbooks/engine.md`'s cycle-stale section holds the procedure.
```

The replaced span carries the boundary-window rule and its reason, the workstation soak rewriting the store inside that window — a soak that no longer writes that directory, the daily pass's `soak-check` reading a scratch store `derive_soak_store` builds under its own temp root — so it goes with the repair sentence rather than standing beside a repair that reads by the seed's return.

Append at the end of the file, after the `## Out of scope` paragraph, a blank line and:

```
## Spec amendments

- 2026-09-21, spec 00117 D7 and D8: item 4's delivery-timing sentence (away from a 4h-boundary+30-min window, the workstation soak rewriting the store inside it) is replaced by the seed-return ordering, that soak no longer writing `data/engine-store/` (the daily pass reads a scratch store derived from the journal), and its store-poisoning runbook (`rm -rf` the store, `site.yml --tags engine`, start) by the move-aside repair, the converge carrying `-e converge_primary=true` and the digest (spec 00082's guard postdates this spec), the play starting the unit itself, and the aside copy purged once the refused file has been read and the runbook's all-clear by value has landed. `docs/specs/00043-observability-design.md`'s metrics-flip window cites the replaced timing as the store delivery's rule; that flip is outside this change and its own timing is untouched.
```

`grep -c 'rm -rf /var/lib' docs/specs/00042-vps-deployment-design.md` prints `0`; `grep '^#' docs/specs/00042-vps-deployment-design.md` ends with `## Out of scope` then `## Spec amendments`.

- [ ] **Step 3: The cycle-stale bullet**

`grep -cF 'so stop the unit, move the store dir aside rather than deleting it (unversioned data has no undo),' infra/runbooks/engine.md` prints `1`. Replace that clause, inside the one-line bullet, with:

```
so stop the unit, move the store dir aside rather than deleting it (`sudo mv /var/lib/zcrypto-engine/store /var/lib/zcrypto-engine/store.aside-$(date -u +%Y%m%dT%H%MZ)`, beside it under the same owner; unversioned data has no undo, and the host's store is not replicated, so until the purge below the aside dir is the one copy of the pre-repair store, the file the refusal named being what a read of the cause opens), touching nothing else under `/var/lib/zcrypto-engine` (`exec/` stays as it is, so the procedures page's rule for a restored state directory is not entered),
```

`grep -cF "so the role's copy for an absent store re-delivers it, and start the unit." infra/runbooks/engine.md` prints `1`. Replace that clause, the bullet's end, with:

```
so the role's copy for an absent store re-delivers it and the play starts the unit itself; then take the measurements the converge owes, step 6's all-clear by value the last of them, and purge the aside dir once the refused file has been read — on the host, or copied to the workstation for that read, since the all-clear reads the delivered store and not the aside copy — and that all-clear has landed (`sudo rm -r /var/lib/zcrypto-engine/store.aside-<stamp>`), naming the aside path and the purge in the commit that carries the converge's deploy-log row.
```

`grep -cF 'is the snapshot write refusing to journal what the store holds at that stamp' infra/runbooks/engine.md` prints `1`. Replace the sentence that carries it, in the same bullet, from `A traceback naming a pair, a grid, a bar and a close that is "not a finite positive number"` through `and a re-run over the same store refuses the same way.`, with:

```
A traceback naming a pair, a grid, a bar and a close that is "not a finite positive number" comes from one of three doors: the refresh's own over the store file, when the same traceback names that file and `is not the frame the store readers join`, the sentence that refusal also carries for a stamp off the leg's grid, a null or repeated stamp and a frame whose shape the readers refuse; the same door over the REST fetch, when it names `the REST fetch for <pair>@<grid>` in place of a file, which is a row the venue itself carries and the venue's to answer -- nothing was written, the store is as it was, the next run fetches again, and no store repair or converge reaches it; and the snapshot write, when it names neither, the store readable and the refresh done. Each of the three raises before the boundary is journaled, the boundary's venue record excepted; a re-run refuses the same way at the two doors that read the store, and at the REST door for as long as the fetch carries that row.
```

That sentence is the bullet's identification of what raised, and after Task 1 the refresh's two doors are the earliest of the three and read a resident value the snapshot write used to be the first to see: `refresh_store` is `run_cycle`'s step 1, so a store file carrying an unusable close, an off-grid stamp or an unsound stamp set is refused there, before any snapshot, and so is a fetch carrying one, and the boundary raises with no sidecar and no `/fail` ping — the shape this bullet already tells the operator to read as "suspect the store", which the REST arm is the one reading of that is not the store's at all.

The same bullet's workstation-repair clause, which sends the operator to `zcrypto engine seed` for the moved-aside series, gains the reading that seed can now return: `grep -cF 'else the next quarterly ingest is minted first)' infra/runbooks/engine.md` prints `1`, and that text, the end of the clause's parenthesis, becomes:

```
else the next quarterly ingest is minted first; and a seed that refuses naming the REST fetch rather than a file is a row the venue itself carries, the venue's to answer, which writes nothing and which no store repair reaches)
```

None of the three texts carries a universal word (every, never, always, only, any, cannot) outside a code span: `uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/engine.md` prints nothing.

- [ ] **Step 4: The fleet page's workstation row**

`grep -cF 'are the retired pre-VPS engine state, not live data' docs/reference/fleet.md` prints `1`. In the `| workstation |` row replace the cell text `` `data/engine-store` and `data/engine-journal` are the retired pre-VPS engine state, not live data `` with:

```
`data/engine-store` is the source the engine role copies to `zcrypto` for an absent store, refreshed by `zcrypto engine seed` before a re-delivery, stale otherwise; `data/engine-journal` is retired
```

The cell is 197 characters: `tests/test_fleet_contracts.py` refuses a cell past 200, and the page holds state, so the reading behind the wording (the legs' last stamps, the files' mtime) stays in the spec's measured basis, not here. `uv run python infra/scripts/guidance-guard.py --uncounted docs/reference/fleet.md` prints nothing.

The words the cell drops for `data/engine-store`, "the retired pre-VPS engine state", are cited by two documents outside this change — `docs/plans/00112-soak-null-reference-span.md` (which cites the row by line) and `docs/specs/00112-soak-null-reference-span-design.md` — for the reading that the workstation's copy is not the live node's store. That reading survives the rewording, in "the source the engine role copies" and "stale otherwise", and the replication half they lean on is the page's own not-replicated bullet, so both are left as they are and this is the drop's record: no task edits them, and nothing in the tree resolves a `path:line` citation inside a document.

- [ ] **Step 5: The guards and the commit gate**

Run: `uv run pytest -q tests/test_internal_terms_not_operator_visible.py tests/test_guidance_refs_resolve.py tests/test_message_citations.py tests/test_fleet_contracts.py`
Expected: every test passed (`728 passed` on the plan's scratch copy).

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. The commit-msg hooks run at Step 6.

- [ ] **Step 6: Commit**

```bash
git add infra/ansible/roles/engine/tasks/main.yml docs/specs/00042-vps-deployment-design.md infra/runbooks/engine.md docs/reference/fleet.md
git commit -m "docs(engine): the host's store repair moves the store aside in every carrier and purges it after the read and the all-clear

The engine role's delivery comment and its assert's fail_msg, spec 00042's item 4 and the
cycle-stale bullet of infra/runbooks/engine.md say the same repair: stop the unit, move the store
dir aside beside itself, re-run the engine-tagged converge with -e converge_primary=true and the
digest inside the inter-cycle gap and outside a published Kraken maintenance window, the
only-when-absent copy re-delivering the workstation's data/engine-store/ and the play starting the
unit itself, and purge the aside dir once the refused file has been read and the runbook's
all-clear by value has landed, that all-clear being the last measurement the page prescribes and
the first that reads the delivered store end to end, though it reads the delivered store and not
the aside copy. The rm -rf text leaves all three carriers; the fail_msg stops
pointing at a source comment ansible never prints, carries the flag and the digest it lacked, and
leads with the workstation source it re-delivers, since it fires where the copy has just run, so the
dir it says to move aside is that incomplete delivered copy, a second aside dir purged with the
first, and the unit it names is one this play never started; the
cycle-stale bullet now reads a traceback naming a close that is not a finite positive number as one
of three doors, the refresh's own over the store file when it also names that file and the join
sentence, and the same door over the REST fetch when it names the fetch in place of a file; the role
comment, the fail_msg and the bullet each say that a row the venue itself carries is the venue's to
answer, not the store's, so nothing was written and no store repair or converge reaches it;
spec 00042 is unpinned by both registry counts and is amended in place, the amendment listed under
a new Spec amendments section. The fleet page's workstation row says data/engine-store is the
delivery source the seed refreshes before a re-delivery and stale otherwise, not retired state and not
a live copy: the role's defaults name it as the source, and nothing but a workstation seed writes it.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

---

### Task 4: T0199 resolved and archived

**Files:**
- Modify: `docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` (the two front-matter lines; everything from `## Done so far` to the end of the file), then `git mv` it to `docs/open-topics/archive/`
- Modify: `docs/open-topics/README.md` (rendered, never edited by hand)
- Modify: `docs/specs/00115-soak-verdict-reader-design.md` (the last sentence of D2; a section appended at the end)

**Interfaces:**
- Consumes: Tasks 1 to 3, which the Resolution names, so this task's commit follows Task 3's on the branch; `docs/open-topics/archive/T0201-store-type-door-cannot-see-a-wrong-instant.md`'s Resolution, whose host read spec 00115 D2 is amended to.
- Produces: nothing code reads; `tests/test_open_topics_frontmatter.py` reads the topic file and the index.

- [ ] **Step 1: Resolve T0199**

In `docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md`: change `status: partial` (line 2) to `status: resolved`; delete the `ripe_when:` line (line 3, one line). `grep -c '^## Done so far' docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` prints `1`. Replace everything from the `## Done so far` heading to the end of the file, that section and `## Suggested next steps` with its five bullets, with:

```
## Resolution

Resolved on branch `fix/t0199-t0201-store-refusals`, on the owner's rulings of 2026-09-20 and 2026-09-21, the first half in the commits below `## Done so far` once held and the door's width by spec `00117` and the same PR.

- Ruling (1), an absent close is a disagreement: `seam_overlap` in `cli/ohlc/seam.py` keeps a shared row whose close is null on either side among the mismatches, and both callers refuse it before their mismatch branches, naming the stamp and the side -- `_merge_or_detach` in `cli/ohlc/reach.py` as an `OHLCError`, `_reconcile` in `cli/engine/store.py` as an `EngineError` whatever `allow_replace` is. On `develop` the seam's filter dropped the null from the mismatches, so it was read as agreement and never replaced anything; the refusal is what keeps the new filter's null out of `allow_replace`'s replace. `to_frame` and `write_parquet` in `cli/ohlc/dataset.py` are untouched: a REST-only row with a null close stays admitted as an absent bar, because spec `00116` D2 admits `None` at the engine's own write and [[T0200]]'s ruling keeps the shared writer as it is.
- Ruling (3), the report line: `RealizedSeries.dropped_reasons` names, per skipped cycle, a PRESENT non-finite close -- the cycle, the asset, the stamp and the value; `render_report` prints the entries under `dropped_tail` and `_json_payload` carries them in `provenance`. An absent close or a missing stamp is the short store the STORE-BOUND block already describes and gets no line, and no `dropped_tail > 0` trigger was added.
- Ruling (2), the door's width (spec `00117` D1 to D5): `_require_store_frame` in `cli/engine/store.py`, over `_frame_differences`, holds a store frame and the canonical before it is copied to the whole of `FRAME_SCHEMA` in order, non-empty, with no null or repeated stamp, every stamp on the leg's epoch-anchored grid on both intervals, and every present close finite and positive as spec `00116` D1 holds the snapshot write, `None` admitted; the refusal names the file, the pair, the grid and the first difference the way `_read_canonical` does, and one recovery per host: a store file is moved aside on the workstation and `zcrypto engine seed` copies the canonical and fills the gap from REST, the loss any bar past the canonical's tail REST no longer reaches; a canonical is the data pipeline's to republish and nothing is copied. The in-place ts recast text and its seam clause left the tree. The enumeration behind the claim that every newly refused frame already failed downstream or is a shape no writer produces is the spec's D10, the test fixture crossed with the writer census; the two shapes nothing stopped, a repeated stamp and an interior off-grid stamp, are what the width closes, the second being the live-path case `select_model_inputs` admitted, refused now at the boundary's own refresh when the stamp is already in the file. The same door holds the REST fetch before the merge, in both readers: a row the venue's own answer carries that the door refuses -- a stamp off the grid, an unusable present close -- would otherwise become resident and be written back by every re-seed, and the refusal of it names the fetch rather than a file, writes nothing and prescribes no store repair and no edit, because it is the venue's row to answer (spec `00117` D1, D3, D4).
- The carriers route by host, and the seam's absent close by side (spec `00117` D6): `refresh_store`'s shortfall and mismatch hints and `run`'s bind-mount refusal end with the engine host's re-delivery, the runbook's procedure, and name `zcrypto engine seed` as the workstation's command; `_reconcile`'s absent-close refusal, which runs whatever `allow_replace` is, ends with the store recovery when the store tail holds the null and with the fetch's own hint, no store repair, when the REST fetch alone does, and `seed_store` calls the file a fresh canonical copy only when it copied one; `run_cycle`'s docstring and `realized_series`' off-grid refusal carry the move-aside too, the soak's saying that under the daily row the store is the record's snapshots copied aside and the scratch leg is not the one to move.
- The engine host's repair (spec `00117` D7 and D8): the cycle-stale bullet of `infra/runbooks/engine.md` names the aside destination beside the store, the converge that re-delivers the workstation's `data/engine-store/` with `-e converge_primary=true` and the digest and starts the unit itself, and the purge of the aside dir once the refused file has been read and the all-clear by value has landed; the engine role's delivery comment and `fail_msg` and spec `00042`'s item 4, amended in place as an unpinned spec, say the same and the `rm -rf` text left all three; `docs/reference/fleet.md`'s workstation row says `data/engine-store/` is the delivery source the seed refreshes before a re-delivery, stale otherwise. No converge was part of the change.
- [[T0201]], the wrong-instant store frame, is resolved on the same branch: the soak's realized leg refuses a stamp off the 4h grid as a plain `EngineError`, and the store door now holds both grids at the write's readers; the host read its last step asked for settled spec `00115` D2's equality, and that spec's D2 is amended in place to say so (spec `00117` D11).
```

Then `grep '^#' docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` prints the H1, `## Context — what`, `## Why this matters`, `## Findings so far` and `## Resolution`, in that order and nothing else. Then:

```bash
git mv docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md docs/open-topics/archive/
git add docs/open-topics/archive/T0199-store-nan-drops-a-tail-instead-of-refusing.md
```

The `git add` is the remedy the repo's `git-mv-guard` hook prints after a `git mv` of an edited file, whose staged rename would otherwise carry the pre-edit content until Step 5 stages the path.

- [ ] **Step 2: Spec 00115's D2, amended to the host read**

`grep -cF "it is the owner's to run, the branch does not wait on it, and it is carried as a next step of [[T0201]], the topic whose own trigger reads that store's last bar." docs/specs/00115-soak-verdict-reader-design.md` prints `1`. In D2 replace that sentence, the paragraph's last, with:

```
that read was taken and settles it, as [[T0201]]'s Resolution records (amended 2026-09-21 by spec 00117 D11): on every `240` and `1440` leg the journaled closes equalled the live store's at their stamps, with no extra or missing stamp at or before `last_ts` and no off-grid stamp.
```

Append at the end of the file, after the `## Out of scope` bullets, a blank line and:

```
## Spec amendments

- 2026-09-21, spec 00117 D11: D2's clause calling the equality between the journaled closes and the engine host's store unsettled is replaced by the host read [[T0201]]'s Resolution records, which settled it.
```

`grep '^#' docs/specs/00115-soak-verdict-reader-design.md` ends with `## Out of scope` then `## Spec amendments`; `grep -c 'is carried as a next step' docs/specs/00115-soak-verdict-reader-design.md` prints `0`.

- [ ] **Step 3: Re-render the index and run the guards**

Run: `uv run python infra/scripts/topics-index.py`
Expected: `docs/open-topics/README.md` changes; T0199 moves from `## Partially done` to `## Resolved` with its link under `archive/`.

Run: `uv run pytest -q tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_internal_terms_not_operator_visible.py tests/test_guidance_refs_resolve.py`
Expected: every test passed (`1734 passed` on the plan's scratch copy).

- [ ] **Step 4: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 5: Commit**

```bash
git add docs/open-topics/README.md docs/open-topics/archive/T0199-store-nan-drops-a-tail-instead-of-refusing.md docs/specs/00115-soak-verdict-reader-design.md
git commit -m "docs(topics): T0199 resolved, the store door's width and the host's repair recorded, spec 00115 D2 settled

The topic's Done so far becomes its Resolution: the seam's absent close and the report line from the
branch's first half, the door's width over the store file, the canonical and the REST fetch, its one
recovery per host and the venue's own refusal, the carriers routed by host and the
seam's absent close by side, the host repair's carriers from spec 00117 and this PR, with the
enumeration behind the live-path claim named, and T0201's closing on the same branch. The first
bullet no longer implies that a REST null replaced a store close on develop: the old filter dropped
it from the mismatches, so it was read as agreement. The trigger is deleted, the file archived and
the index re-rendered. Spec 00115 D2's last sentence, which called the journaled-closes equality
unsettled, is amended in place to the host read T0201's Resolution records, 00115 being unpinned by
all three registry counts, with a Spec amendments section listing it.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

- [ ] **Step 6: The pull request carries the read the live-path claim rests on**

No test on this branch opens `/var/lib/zcrypto-engine/store`, the corpus the door judges twenty-four times a boundary, and the claim that the width refuses nothing that works today is measured over the two corpora the repo holds plus that read. The read spec D7 names was taken on 2026-09-21, read-only and with no fence run against the host: the store pulled to the workstation as a copy, its 24 legs held to the door's arms with this repo's `read_parquet` and `FRAME_SCHEMA`, 0 refused, and the copy deleted after the read (spec `00117`, `## The measured basis`). The PR body, edited through the `open-pr` skill, which owns this PR's create and its body edits, states that read, its date and its verdict, so the branch ships the premise it rests on. This step re-takes nothing: it copies the verdict the spec records. The converge that later restarts the engine on that store re-takes the read immediately before it, since the store gains rows at every boundary, and records its verdict with the deploy-log row — `.claude/rules/fleet-deploys.md`'s concern, not this change's.

---

## Self-review

- Spec coverage: D1 (the arms in order, the canonical before the copy, the REST fetch before the merge, `read_store_series` untouched) is Task 1 Step 2 and the `off_the_schema`, `unsound_stamps`, `deviated_canonical` and `rest_row_the_venue_carries` cases; D2 is the `unusable_present_close` cases and the `admit_a_null_close` case; D3 is the `an off-grid stamp` arm over both grids and the calendar pin re-modelled in Step 3; D4 and D5 are the three constants and the three re-pinned cases; D6 is Task 2 whole, the side arm its Step 2 and the side, fresh-copy and soak cases its Step 1; D7 is Task 3 Steps 3 and 4 and, for the read the converge owes and the branch took, Task 4 Step 6; D8 is Task 3 Steps 1 and 2; D9 is Task 1 Steps 1 and 3 and Task 2 Step 1, the zoned case in Task 1 Step 1; D10's enumeration is the `_deviated` fixture of Task 1 Step 1; D11 is Task 4 Step 2. The measured basis is the spec's and no task re-measures it.
- Placeholders: `PROBE_VERDICT` is the one token, replaced in Task 1 Step 8 and Task 2 Step 6 and checked to be gone; `<model>` in the trailers is the executing model's own name, a Global Constraint; `<stamp>` and `<full digest>` in the prose are the operator's own values, named beside them.
- Names: `FRAME_SCHEMA`, `read_parquet`, `to_frame`, `write_parquet`, `seam_overlap`, `drop_in_progress`, `EngineError`, `_store_path`, `_reconcile`, `seed_store`, `refresh_store`, `read_store_series`, `resolve_canonical_root`, `_read_canonical`, `_on_grid`, `aggregate_minutes`, `cycle.read_store_series`, `build_crossfreq_system_fast`, `select_model_inputs`, `from_json`, `_real_env`, `_real_store_rows`, `_real_closes`, `_row`, `_write_store`, `_tail_fetch`, `_clock`, `ASSETS`, `EUR_SYMBOLS`, `BTC_SYMBOLS`, `_REAL_N_H4`, `_REAL_N_DAILY`, `_REAL_DAILY_TS`, `_REAL_H4_TS`, `_BTC_ONLY_INSERT_AT`, `_run_env`, `runner`, `app`, `_output`, `_good_rest_rows`, `_fetch_override`, `soak._on_grid`, `CycleRecord`, `select_clean_segment`, `derive_soak_store` exist where the tasks say; `_frame_differences`, `_require_store_frame`, `_require_rest_frame`, `_HOST_REDELIVERY`, `_STORE_RECOVERY`, `_CANONICAL_RECOVERY`, `_REST_REFUSED`, `_ABSENT_REST_HINT`, `_FRESH_COPY`, `_RESEED_REFUSED`, `absent_store_hint`, `absent_rest_hint`, `_deviated`, `_first_difference`, `_deviate_store_file`, `_run_reader`, `_assert_store_refusal` are this plan's; `_BTC_ONLY_OFFSET` and `_require_joinable_ts` leave the tree.
- Order: Task 2's hints use Task 1's constants, Task 3's texts describe Tasks 1 and 2, Task 4's Resolution names all three, and a Global Constraint holds the four in order on one branch.
- Fences run: every code fence above was applied in order on a scratch copy of the tree at `4d51700b0` under `git init`, and each `Run:` line's `Expected:` is that run's summary line; the eleven probes those two steps then held ran through `infra/scripts/mutate-probe.sh` on that copy, each `KILLED (control proven, tree restored byte-identically)`; the prose edits of Tasks 3 and 4 ran there too, with their guards green as their steps say. The fences the first review round changed — the door's and `read_store_series`' docstrings, the reach's keys comment, `_reconcile`'s side list and hint, the absent-REST text, the two wrapped `refresh_store` hints, the soak refusal's hedged sentence and the side case's third arm — were re-applied on a copy of that same post-fence tree and their `Expected:` lines re-read from those runs, as were the second round's — `_reconcile`'s per-side stamps, the two re-pinned stamp assertions, the side case's stamps, the fresh-copy case's third arm and the deviated-canonical case's daily-leg assertion. The four probes the two review rounds added to Task 1 Step 8 (the value filter narrowed, the column-order, no-rows and repeated-stamp arms removed) had their controls and their kills read by direct execution on those copies, and are earned through the script at implementation like the eleven. The floor round's fences — `_require_rest_frame`, its constant, its two call sites, the `_run_reader` parameter, the REST-fetch case and the three prose carriers of Task 3 — were applied on a copy of the checkout at `38fb88ed8` with every other fence of Tasks 1 and 2 already on it, and every `Expected:` line this plan carries for `tests/test_engine_store.py`, `tests/test_engine_cycle.py`, `tests/test_engine_command.py`, `tests/test_engine_soak.py`, `tests/test_engine_soak_command.py` and the consumer union was re-read from those runs; the REST door's probe ran there too, in-repo under `git init`, `KILLED (control proven, tree restored byte-identically)`.
