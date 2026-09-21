# The journal's snapshot write refuses an unusable close — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `run_cycle` refuses to journal a snapshot holding a present close that is not a finite positive number, before the first snapshot file is written, naming the pair, the grid, the bar, the stamp and the value; `zcrypto engine seed` reads the canonical the repair needs; the operator page names the host's real repair; T0200 is resolved.

**Architecture:** One pre-pass inside `_journal_snapshots` in `cli/engine/cycle.py` over the union-aligned closes it is about to hash, collecting the offenders and raising `EngineError` once before the write loop; the raise propagates the way the forming-row guard's does, so the node logs it and the boundary stays journal-absent. No record field, no schema change, no change to the shared parquet writer. `seed` in `cli/engine/command.py` resolves its canonical through `resolve_canonical_root` over the configured data root. The cycle-stale runbook's bullet and its step 3 carry the reading and the host's re-delivery repair; the topic is resolved and archived, and T0199's file records what this decided for the shared helper.

**Tech Stack:** Python 3.14, pytest, polars (to spoil a store frame below the engine's own writer, which refuses a NaN); `infra/scripts/mutate-probe.sh` for the guard verdicts; `topic-ops` for the closeout; the universal test of `zcrypto-refine-rules` governs the runbook page Task 3 edits, through the `guidance-guard` commit-msg hook.

**Spec:** `docs/specs/00116-snapshot-write-refuses-unusable-close-design.md`

## Global Constraints

- The source change is confined to `_journal_snapshots`, the forming-row guard's comment and `run_cycle`'s docstring in `cli/engine/cycle.py` (Task 1), and to `seed`, the `cli.config` import line and the `CANONICAL_DIR` block at the module top of `cli/engine/command.py` (Task 2). `cli/engine/journal.py` (spec D3: no `SnapshotEntry` field, no `SCHEMA_VERSION` step), `cli/ohlc/dataset.py` (spec D4: `write_parquet` untouched) and `cli/engine/store.py` do not change. `soak-check`'s `--canonical-dir` default stays `CANONICAL_DIR` at `data/ohlc-full`, and Task 2 pins it (spec D8).
- The refusal's message names the pair as `<symbol>@<interval>`, the bar as `close[<k>]`, the stamp in ISO 8601, the value as its `repr`, the count of unusable closes and of series holding one, and what was not written: no snapshot, record, sidecar or orders (spec D1); the venue record of step 0 is on disk before the refusal, so the message never says nothing was written. It carries no topic id, spec serial or decision number: `tests/test_internal_terms_not_operator_visible.py` reads every non-docstring string literal under `cli/` and `infra/scripts/`, and every page under `infra/runbooks/`. Provenance goes in the comment beside the code, which no walker reads, and in the commit message.
- `None` is admitted by the refusal (spec D2); the predicate reads `close is not None` before anything else.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend, the tree clean. The probe never runs while a pytest run is in flight in the same checkout.
- Every commit is green over the changed files' consumers, the union of `grep -rlE 'engine\.cycle|run_cycle' tests/test_*.py` and `grep -rlE 'engine\.command|engine import command' tests/test_*.py` as they read when this plan was written: `uv run pytest -q tests/test_engine_command.py tests/test_engine_concordance.py tests/test_engine_cycle.py tests/test_engine_execledger.py tests/test_engine_executor.py tests/test_engine_feeders.py tests/test_engine_gate_cache.py tests/test_engine_gate_export_cache.py tests/test_engine_gate_export.py tests/test_engine_journal.py tests/test_engine_metrics.py tests/test_engine_node.py tests/test_engine_soak_command.py tests/test_engine_soak.py tests/test_engine_stub_fidelity.py tests/test_error_paths_are_logged.py tests/test_ops_daily.py tests/test_ops_daily_soak.py`; `uv run pre-commit run -a` is clean; the full suite is CI's, on the pull request.
- `uv run pre-commit run -a` runs the pre-commit stage alone: `guidance-guard` and `message-citations` run at commit-msg, on `git commit`. The former refuses a universal word (every, never, always, only, any, cannot) in the prose of a list item on a page under `infra/runbooks/` with no count entry, so the runbook text Task 3 writes carries none outside code spans; the latter refuses a commit message whose `path:line`, `path::symbol` or `T<NNNN>` resolves nowhere.
- No step reaches a host, a venue or a mount: the spec's measured basis was read by the controller before this plan, and nothing here re-reads it; Task 2's tests monkeypatch the resolver and the config.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. An existing file's lines are left as they are, except where a step replaces them.
- No string literal added to `infra/runbooks/engine.md`, `docs/reference/data-catalog-full.md` or `cli/engine/` names a spec, a decision or a topic.
- Task 3 lands after Task 2: its runbook text and T0200's Resolution say the seed reads the sibling, which is Task 2's deliverable, so Task 3 is never committed on a branch that lacks Task 2's commit.
- A commit message ends with these two trailers, the model name being the executing model's own (`Claude Fable 5.1`, `Claude Opus 5`, ...):

```
Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd
```

---

## File structure

- Modify `cli/engine/cycle.py` — `_journal_snapshots` gains the pre-pass and its raise; the forming-row guard's comment names the door one step earlier; `run_cycle`'s docstring routes a store fault's recovery by host (Task 1).
- Modify `tests/test_engine_cycle.py` — `import polars as pl` and one parametrised case beside the forming-row guard's cases (Task 1).
- Modify `cli/engine/command.py` — `seed` resolves its canonical through `resolve_canonical_root` over the configured data root and refuses in its own voice; `CANONICAL_DIR` keeps `soak-check`'s null reference (Task 2).
- Modify `tests/test_engine_command.py` — `_patch_config` takes a `data_dir`; the seed summary case follows the resolver and pins `CANONICAL_DIR`; the seed error case resolves a canonical first; two refusal cases (Task 2).
- Modify `docs/reference/data-catalog-full.md` — the `engine-store` bullet's account of the seed's canonical (Task 2).
- Modify `infra/runbooks/engine.md` — the `zcrypto-engine-cycle-stale` › What it means bullet on a raising `run_cycle` is re-led and gains the reading and the repair; What to do step 3's artifact-state line gains the third cause (Task 3).
- Modify `docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md` — resolved, moved to `docs/open-topics/archive/` (Task 3).
- Modify `docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` — the one-door paragraph records what T0200 decided for the shared helper; the `write_parquet` arm leaves its trigger and its first next step (Task 3).
- Modify `docs/open-topics/README.md` — re-rendered by `infra/scripts/topics-index.py` (Task 3).

---

### Task 1: The snapshot write refuses an unusable present close before the first file

**Files:**
- Modify: `cli/engine/cycle.py` (`_journal_snapshots`, the function whose first line is `rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"`; the comment block above `model_closes = {}` in `run_cycle`; and `run_cycle`'s docstring)
- Test: `tests/test_engine_cycle.py` (the imports, and one case inserted directly above the line `# --- the limit-bound verdict ---------------------------------------------------------------------`)

**Interfaces:**
- Consumes: `_env`, `_tail_fetch`, `_clock`, `CYCLE_TS`, `run_cycle`, `EngineError`, `read_parquet` from the test module's existing imports and helpers; `GRID_INTERVALS`, `PAIR_KEYS`, `math`, `EngineError` already imported in `cli/engine/cycle.py`.
- Produces: `_journal_snapshots(journal_dir, cycle_ts, aligned)` with the same signature and return, raising `EngineError` before any write when a present close is not a finite positive number. `tests/test_ops_daily_soak.py::_journal_a_cycle_from` calls it directly and keeps working over a clean store.

- [ ] **Step 1: Add the polars import and the failing case to `tests/test_engine_cycle.py`**

In the import block, directly above `import pytest`, add:

```python
import polars as pl
```

Directly above the line `# --- the limit-bound verdict ---------------------------------------------------------------------`, insert:

```python
@pytest.mark.parametrize(("symbol", "interval", "bar"), [("ETH/BTC", 240, 2), ("XRP/EUR", 1440, 1)])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 0.0, -5.0])
def test_an_unusable_present_close_refuses_the_cycle_before_any_snapshot_is_written(
    tmp_path, monkeypatch, symbol, interval, bar, bad
):
    """The journal's snapshot write is the door: a present close the replay's validator would refuse is refused
    before the first snapshot file exists, naming the pair, the grid, the bar, the stamp and the value.

    `ETH/BTC` is a leg no builder input reads and both bars sit outside the refresh overlap (the last two rows), so
    nothing else on the path refuses either value; with the stubbed builder the EUR leg's mid-series bar is the
    same. Both legs have files written before them -- the daily grid goes first and `XRP/EUR` is its last leg, and
    `ETH/BTC` sits mid-way through the 4h pass -- so a check that moved into the write loop would leave files
    behind on both halves."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    base, quote = symbol.split("/")
    path = config.store_dir / base / quote / f"{interval}.parquet"
    frame = read_parquet(path)
    closes = frame["close"].to_list()
    stamp = frame["ts"].to_list()[bar]
    closes[bar] = bad
    # `to_frame` refuses a NaN, so the store is spoiled below the engine's own writer, the way a torn or foreign
    # writer would leave it.
    frame.with_columns(pl.Series("close", closes, dtype=pl.Float64)).write_parquet(path)

    with pytest.raises(EngineError) as excinfo:
        run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    message = str(excinfo.value)
    assert f"{symbol}@{interval}" in message
    assert f"close[{bar}]" in message
    assert stamp.isoformat() in message
    assert repr(bad) in message
    assert "1 unusable close at a present stamp in 1 series" in message
    day_dir = config.journal_dir / "2026-07-10"
    # Refused before the FIRST file: no snapshot directory, no record, no sidecar, no orders. The venue record of
    # step 0 is already there and stays.
    assert not (day_dir / "snapshots").exists()
    assert not (day_dir / "cycle-08.json").exists()
    assert not (day_dir / "failed-cycle-08.json").exists()
    assert not (day_dir / "orders.jsonl").exists()
    assert (day_dir / "venue-08.json").exists()


```

- [ ] **Step 2: Run the case to verify it fails**

Run: `uv run pytest -q tests/test_engine_cycle.py -k unusable_present_close`
Expected: `10 failed`, each with `Failed: DID NOT RAISE EngineError` (the stubbed builder accepts the value and the cycle succeeds).

- [ ] **Step 3: Add the pre-pass to `_journal_snapshots`, the line to the forming-row guard's comment, and the recovery clause to `run_cycle`'s docstring**

In `cli/engine/cycle.py`, replace the first line of `_journal_snapshots`'s body:

```python
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
```

with:

```python
    # Every series is read through the refusal before the first file is written, so a refused boundary leaves no
    # snapshot directory: a present close the replay's validator would refuse is refused here, where the cycle
    # still holds the frame and has published nothing (spec 00116 D1). `None` is a union absence and is admitted
    # (D2); the type door is `read_store_series`'s, so nothing but a float or an int reaches this predicate, which
    # is the one the forming-row guard below holds at the forming row alone. The offenders are collected before
    # the raise: a torn write spoils a span, and one traceback names the first bar and the extent.
    offenders = []
    for interval in GRID_INTERVALS:
        union_ts, prices = aligned[interval]
        for symbol in PAIR_KEYS:
            for k, close in enumerate(prices[symbol]):
                if close is not None and (not math.isfinite(close) or close <= 0):
                    offenders.append((symbol, interval, k, union_ts[k], close))
    if offenders:
        symbol, interval, k, stamp, close = offenders[0]
        n_series = len({(s, i) for s, i, *_ in offenders})
        raise EngineError(
            f"the snapshot for {symbol}@{interval} cannot be journaled: close[{k}] at {stamp.isoformat()} is {close!r}, "
            f"not a finite positive number -- the store holds {len(offenders)} unusable close"
            f"{'' if len(offenders) == 1 else 's'} at a present stamp in {n_series} series; no snapshot, record, sidecar "
            "or orders were written and no target was published"
        )
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
```

Then, in `run_cycle`, directly below the comment line

```python
    # boundary's `_previous_success` silently globs past.
```

insert:

```python
    #
    # The journal write one step earlier refuses these values at every bar, `None` excepted, so on the live path the
    # arm this guard can reach is the `None` one; the others stay for what a stub or a replay hands it.
```

Then, in `run_cycle`'s docstring, replace the two lines

```python
    EngineError -- poisoned tail / catastrophic staleness) propagates, and its documented recovery is
    `zcrypto engine seed`, not a per-cycle retry."""
```

with

```python
    EngineError -- poisoned tail / catastrophic staleness, the journal's own refusal of an unusable close) propagates,
    and its documented recovery is the store's, not a per-cycle retry: on the engine host the cycle-stale runbook's
    re-delivery, on the workstation `zcrypto engine seed`."""
```

- [ ] **Step 4: Run the case, then the changed files' consumers**

Run: `uv run pytest -q tests/test_engine_cycle.py -k unusable_present_close`
Expected: `10 passed`

Run: the Global Constraints' consumer command.
Expected: every test passed; the skips are the files' existing live-venue and dataset gates, none new; `test_union_alignment_journals_none_at_absences_and_replays_clean` among the passes, which is the `None`-admitted case.

- [ ] **Step 5: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed. A run that rewrites a file reports Failed and leaves the rewrite unstaged: re-run until clean, then stage what it rewrote.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/cycle.py tests/test_engine_cycle.py
git commit -m "fix(engine): the snapshot write refuses an unusable present close before the first file

\`_journal_snapshots\` wrote whatever close the store held at a stamp outside the refresh overlap into
the snapshot and packed it into \`content_hash\`; on an EUR leg the builder's validator refused the
cycle afterwards, leaving twenty-four snapshot files no record names, and on a BTC-quoted leg,
which no builder input reads, the cycle succeeded and published a target over it. On the owner's
ruling of 2026-09-20 (T0200) the write walks every close of every grid before the first file,
collects the offenders and refuses once, naming the first as an \`EngineError\` with the pair, the
grid, the bar, the stamp and the value, and the count of closes and series; \`None\` at a union
absence is admitted; no record field, no schema step, the shared parquet writer untouched. The
raise propagates as the forming-row guard's does: the node logs it and the boundary stays
journal-absent, no snapshot directory, record, sidecar or orders, the venue record of step 0 the
one thing under it. The forming-row guard's comment says the door one step earlier reaches these
values first, and \`run_cycle\`'s docstring routes a store fault's recovery by host, since the seed
it named is the workstation's command.

Case: ten values by leg and grid, the BTC-quoted 4h leg and the EUR daily leg written last in its
pass, both outside the refresh overlap, each refused with the message's names and counts and with
no snapshot directory, record, sidecar or orders on disk beside the venue record.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

- [ ] **Step 7: Prove the guard with two probes, then record their verdicts by a message-only amend**

The tree is clean after Step 6 (the script refuses a dirty one). The first probe removes the refusal; the second makes it refuse `None`, which the absence case catches:

```bash
infra/scripts/mutate-probe.sh --file cli/engine/cycle.py \
  --control 's/close\[{k}\] at /bar {k} at /' \
  --mutation 's/if close is not None and (not math.isfinite(close) or close <= 0):/if False:/' \
  -- uv run pytest -q tests/test_engine_cycle.py -k unusable_present_close
infra/scripts/mutate-probe.sh --file cli/engine/cycle.py \
  --control 's/close\[{k}\] at /bar {k} at /' \
  --mutation 's/if close is not None and (not math.isfinite(close) or close <= 0):/if close is None or not math.isfinite(close) or close <= 0:/' \
  -- uv run pytest -q tests/test_engine_cycle.py -k "unusable_present_close or none_at_absences"
```

Expected: each run ends `KILLED` with `control proven`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/cycle.py`, control the message's bar spelling
changed so the case's match fails; mutation one, the refusal removed, through `-k unusable_present_close`:
KILLED, control proven; mutation two, the predicate refusing `None` as well, through
`-k "unusable_present_close or none_at_absences"`: KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 2: The seed reads the canonical the repair needs

**Files:**
- Modify: `cli/engine/command.py` (the `from cli.config import ...` line, `CANONICAL_DIR` at the module top, and `seed`, the command whose docstring begins `Seed/refresh the live price store`)
- Modify: `tests/test_engine_command.py` (`_patch_config`, `test_seed_prints_per_pair_overlap_summary`, `test_seed_engine_error_is_a_clean_exit_1`, and two cases appended directly below the latter)
- Modify: `docs/reference/data-catalog-full.md` (the `- **`engine-store`**` bullet under the machine-state section)

**Interfaces:**
- Consumes: `resolve_canonical_root(data_root: Path) -> Path` from `cli/data/rebuild.py`, raising `DataSyncError` from `cli/data/errors.py` when no whole frozen set resolves; `resolve_data_dir(flag_value, cfg) -> Path` from `cli/config.py`, raising `ConfigError` when `data_dir` is unset; `seed_store(store_dir, canonical_dir)` from `cli/engine/store.py`; `_load_app_config`, `_abort`, `ConfigError`, `runner`, `app`, `_patch_config`, `_output`, `SeedReport`, `SeedEntry`, `EngineError`, `AppConfig` from the command module and the test module's existing imports.
- Produces: `zcrypto engine seed` seeding from the root the resolver names under the configured `data_dir` and printing it; `CANONICAL_DIR` unchanged for `soak-check`; `_patch_config(monkeypatch, tmp_path, *, data_dir=None)`.

- [ ] **Step 1: Give `_patch_config` a `data_dir`, change the seed summary case and add the two refusal cases in `tests/test_engine_command.py`**

Replace the first two lines of `_patch_config`

```python
def _patch_config(monkeypatch, tmp_path: Path) -> EngineConfig:
    """Point load_config (as cli.engine.command sees it) at tmp-dir engine paths."""
```

with

```python
def _patch_config(monkeypatch, tmp_path: Path, *, data_dir: Path | None = None) -> EngineConfig:
    """Point load_config (as cli.engine.command sees it) at tmp-dir engine paths; `data_dir` stays unset unless a
    case reads it."""
```

and, in the same function, `        data_dir=None,` with `        data_dir=data_dir,`.

In `test_seed_prints_per_pair_overlap_summary`, replace

```python
    engine_cfg = _patch_config(monkeypatch, tmp_path)
```

with

```python
    engine_cfg = _patch_config(monkeypatch, tmp_path, data_dir=Path("data"))
```

and replace

```python
    calls = []
    monkeypatch.setattr(command, "seed_store", lambda store_dir, canonical_dir: calls.append((store_dir, canonical_dir)) or report)

    result = runner.invoke(app, ["engine", "seed"])

    assert result.exit_code == 0, _output(result)
    assert calls == [(engine_cfg.store_dir, Path("data/ohlc-full"))]
    out = _output(result)
```

with

```python
    calls = []
    roots = []
    monkeypatch.setattr(command, "seed_store", lambda store_dir, canonical_dir: calls.append((store_dir, canonical_dir)) or report)
    # The seed reads the newest whole frozen sibling under the configured data root, never the unstamped set by
    # name: the resolver answers for it. A fixed relative root, so no digit of a tmp path can satisfy the summary
    # assertions below.
    monkeypatch.setattr(
        "cli.data.rebuild.resolve_canonical_root", lambda data_root: roots.append(data_root) or Path("data/ohlc-full-20260920")
    )

    result = runner.invoke(app, ["engine", "seed"])

    assert result.exit_code == 0, _output(result)
    assert roots == [Path("data")]
    assert calls == [(engine_cfg.store_dir, Path("data/ohlc-full-20260920"))]
    # `soak-check`'s null reference is the unstamped set and stays so: the seed no longer reads this constant, so
    # nothing else in the suite holds its value.
    assert command.CANONICAL_DIR == Path("data/ohlc-full")
    out = _output(result)
    assert "ohlc-full-20260920" in out
```

In `test_seed_engine_error_is_a_clean_exit_1`, whose store stub raises the `EngineError` the case is about, the seed must first resolve a canonical, so replace

```python
    _patch_config(monkeypatch, tmp_path)

    def boom(store_dir, canonical_dir):
```

with

```python
    _patch_config(monkeypatch, tmp_path, data_dir=Path("data"))
    monkeypatch.setattr("cli.data.rebuild.resolve_canonical_root", lambda data_root: Path("data/ohlc-full-20260920"))

    def boom(store_dir, canonical_dir):
```

Directly below `test_seed_engine_error_is_a_clean_exit_1` (after its last assertion and the two blank lines that follow it), insert:

```python
def test_seed_refuses_when_no_whole_frozen_set_resolves(tmp_path, monkeypatch):
    """The resolver's refusal is the seed's, in the seed's own voice: a missing or partial frozen set aborts the
    command before any store file is touched, the resolver's message after the seed's own."""
    from cli.data.errors import DataSyncError

    _patch_config(monkeypatch, tmp_path, data_dir=Path("data"))
    calls = []
    monkeypatch.setattr(
        command, "seed_store", lambda store_dir, canonical_dir: calls.append((store_dir, canonical_dir)) or SeedReport(entries=())
    )

    def refuse(data_root):
        raise DataSyncError("data rebuild: ohlc-reach needs a frozen ohlc-full set to join, none found under data")

    monkeypatch.setattr("cli.data.rebuild.resolve_canonical_root", refuse)

    result = runner.invoke(app, ["engine", "seed"])

    assert result.exit_code == 1
    out = _output(result)
    assert "engine seed: no canonical dataset to seed from" in out
    assert "none found under data" in out
    assert isinstance(result.exception, SystemExit)
    assert calls == []


def test_seed_refuses_without_a_configured_data_dir(tmp_path, monkeypatch):
    """No `data_dir` in the config is the same refusal: the seed cannot name a canonical without a data root."""
    _patch_config(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        command, "seed_store", lambda store_dir, canonical_dir: calls.append((store_dir, canonical_dir)) or SeedReport(entries=())
    )

    result = runner.invoke(app, ["engine", "seed"])

    assert result.exit_code == 1
    out = _output(result)
    assert "engine seed: no canonical dataset to seed from" in out
    assert "no data_dir configured" in out
    assert calls == []


```

- [ ] **Step 2: Run the three cases to verify they fail**

Run: `uv run pytest -q tests/test_engine_command.py -k "seed_prints_per_pair or seed_refuses"`
Expected: `3 failed`: the summary case on `assert roots == [Path("data")]` (`[] == [PosixPath('data')]`), both refusal cases on `assert result.exit_code == 1` (`assert 0 == 1`: the seed never calls the resolver nor reads `data_dir`, seeds from the stub and prints its summary).

- [ ] **Step 3: Resolve the seed's canonical in `cli/engine/command.py`**

Replace the import line

```python
from cli.config import AppConfig, ConfigError, EngineConfig, load_config
```

with

```python
from cli.config import AppConfig, ConfigError, EngineConfig, load_config, resolve_data_dir
```

Replace the module-level line

```python
CANONICAL_DIR = Path("data/ohlc-full")
```

with

```python
# `soak-check`'s null reference: the frozen unstamped set, whose span is an instrument of the null. The seed does not
# read this name -- it resolves the newest whole frozen sibling under the configured data root, the one a REST
# gap-fill can seam with.
CANONICAL_DIR = Path("data/ohlc-full")
```

Replace `seed`'s body from its docstring to the first `typer.echo`:

```python
    """Seed/refresh the live price store from the canonical dataset plus a Kraken REST gap-fill
    (idempotent; also the documented repair for a poisoned store tail)."""
    config = _load_engine_config()
    try:
        report = seed_store(config.store_dir, CANONICAL_DIR)
    except EngineError as exc:
        raise _abort(str(exc)) from exc
    typer.echo(f"seeded {config.store_dir} from {CANONICAL_DIR} + REST gap-fill; seam QA per pair x grid:")
```

with

```python
    """Seed/refresh the live price store from the newest whole frozen ohlc-full sibling under the configured data
    root, or the unstamped set when there is none, plus a Kraken REST gap-fill (idempotent; also the documented
    repair for a poisoned store tail). A workstation command: the engine image carries no canonical dataset."""
    # Imported here: the resolver lives with the rebuild tree, which the engine's own startup has no use for.
    from cli.data.errors import DataSyncError
    from cli.data.rebuild import resolve_canonical_root

    app_config = _load_app_config()
    try:
        canonical_dir = resolve_canonical_root(resolve_data_dir(None, app_config))
    except (ConfigError, DataSyncError) as exc:
        # The resolver's remedies are written for `data rebuild`; the seed says whose refusal this is first.
        raise _abort(f"engine seed: no canonical dataset to seed from -- {exc}") from exc
    store_dir = app_config.engine.store_dir
    try:
        report = seed_store(store_dir, canonical_dir)
    except EngineError as exc:
        raise _abort(str(exc)) from exc
    typer.echo(f"seeded {store_dir} from {canonical_dir} + REST gap-fill; seam QA per pair x grid:")
```

- [ ] **Step 4: Run the cases, the module's import on a bare interpreter, then the consumers**

Run: `uv run pytest -q tests/test_engine_command.py -k "seed_prints_per_pair or seed_refuses"`
Expected: `3 passed`

Run: `uv run python -c "import cli.engine.command as m; print(m.CANONICAL_DIR)"`
Expected: `data/ohlc-full`

Run: the Global Constraints' consumer command.
Expected: every test passed; the skips are the files' existing live-venue and dataset gates, none new.

- [ ] **Step 5: Amend the data catalog's account of the seed's canonical**

`grep -c '^- \*\*`engine-store`\*\* — rebuildable from the hot cluster on demand' docs/reference/data-catalog-full.md` prints `1`. In that one-line bullet, replace the text

```
`engine seed` reads canonical only where a store file is absent, and `data/ohlc-full` is frozen at its last quarterly dump (2026-03-31) while Kraken's REST 4h window reaches back only to ~2026-04-17. The two `/BTC` legs' **4h** grids were therefore seeded **REST-only** at the twelve-leg widening — 720 bars from 2026-04-17, no canonical tail behind them — while every `/EUR` leg and both `/BTC` **daily** grids are canonical-backed (REST reaches 2024-08-25 on the daily grid). Harmless to the model today because `select_model_inputs` contracts to the ten `/EUR` legs, so no `/BTC` datum reaches it — but a loop that starts consuming a `/BTC` series must not assume history before 2026-04-17 exists, and a re-seed reproduces the same hole until the quarterly dump is republished.
```

with

```
`engine seed` reads the canonical only where a store file is absent, and its canonical is the newest whole frozen `ohlc-full` sibling under the configured data root, or the unstamped set when there is none (`resolve_canonical_root`, the root `ohlc-reach` joins), so on a checkout carrying the 2026-06-30 sibling a series moved aside is re-copied from a set whose tail the REST window overlaps. The two `/BTC` legs' **4h** grids were seeded **REST-only** at the twelve-leg widening — 720 bars from 2026-04-17, when the unstamped set ended 2026-03-31 and the REST window had receded past it — while every `/EUR` leg and both `/BTC` **daily** grids were canonical-backed from the start (REST reaches 2024-08-25 on the daily grid). Harmless to the model today because `select_model_inputs` contracts to the ten `/EUR` legs, so no `/BTC` datum reaches it — but a loop that starts consuming a `/BTC` series must not assume history before 2026-04-17 exists in the store as it stands; a re-seed of that series from the 2026-06-30 sibling carries the full tail.
```

- [ ] **Step 6: The commit gate, then commit**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

```bash
git add cli/engine/command.py tests/test_engine_command.py docs/reference/data-catalog-full.md
git commit -m "fix(engine): the seed reads the newest whole frozen ohlc-full sibling under the configured data root

\`zcrypto engine seed\` pinned its canonical at the unstamped \`data/ohlc-full\`, frozen at 2026-03-31,
while Kraken's 4h REST window now begins 2026-05-24, so a seed of an absent 4h series had no
shared stamp to seam on and was refused: the workstation repair the cycle-stale page names for an
unusable close could not run for a 4h leg. The seed resolves its canonical through the same
function \`data rebuild ohlc-reach\` joins with, over the data root \`zcrypto.toml\` configures, the
newest whole stamped sibling or the unstamped set when there is none; a refusal from the config or
the resolver aborts in the seed's own voice with the refusing message after it, since the
resolver's remedies are written for \`data rebuild\`; the seed prints the root it read.
\`soak-check\`'s null reference keeps the unstamped set, its span the null's instrument, and a case
pins the constant now that the seed no longer reads it. The data catalog's \`engine-store\` bullet
says which canonical the seed reads and what a re-seed of a BTC-quoted 4h leg carries.

Cases: the seed summary follows the resolver's root under the configured data dir and prints it;
a resolver refusal and an unset data dir are each a clean exit 1 in the seed's voice with no store
call.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

---

### Task 3: The operator reading, the topic's closeout and what T0199 is told

**Files:**
- Modify: `infra/runbooks/engine.md` (under `## zcrypto-engine-cycle-stale — ALERT`: the `### What it means` bullet that begins ``- **`run_cycle` raised before writing anything**``, and the `### What to do` step 3 line that begins `   A boundary with`)
- Modify: `docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md`, then `git mv` it to `docs/open-topics/archive/`
- Modify: `docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` (the `ripe_when:` line, the paragraph under `## Findings so far` that begins `**This topic and [[T0200]] are one door.**`, and the first bullet under `## Suggested next steps`)
- Modify: `docs/open-topics/README.md` (rendered, never edited by hand)

**Interfaces:**
- Consumes: Task 1's refusal and its message shape; Task 2's seed, which the runbook text and the Resolution describe, so this task's commit follows Task 2's on the branch.
- Produces: nothing code reads; `tests/test_open_topics_frontmatter.py` reads the two topic files and the index; the `guidance-guard` commit-msg hook reads the runbook page.

- [ ] **Step 1: Re-lead and extend the runbook bullet, and rewrite its step 3**

`grep -c '^- \*\*`run_cycle` raised before writing anything\*\*: a poisoned store, a disk error\.' infra/runbooks/engine.md` prints `1`. Replace that lead, the text ``- **`run_cycle` raised before writing anything**: a poisoned store, a disk error.``, with ``- **`run_cycle` raised before journaling the boundary**: a poisoned store, a disk error.`` (the venue record of step 0 precedes the raise, so "writing anything" overstated it). The same bullet ends with the text `reads "the node is up but a cycle raised; suspect the store".` Append to the same line, after that full stop, one space and:

```
A traceback naming a pair, a grid, a bar and a close that is "not a finite positive number" is the snapshot write refusing to journal what the store holds at that stamp, before it journaled anything but the boundary's venue record: the store is readable and the refresh completed, and a re-run over the same store refuses the same way. The repair is the store's, and on this host it is a re-delivery, not a seed: `zcrypto engine seed` runs on the workstation alone (the image carries no canonical dataset) and over an existing file it replaces a divergent tail inside the REST window and nothing older, so stop the unit, move the store dir aside rather than deleting it (unversioned data has no undo), repair that series in the workstation's `data/engine-store/` first (read the stamp the traceback names; a series moved aside there is re-copied from the canonical and gap-filled from REST by `zcrypto engine seed`), then take step 5's attended converge with the engine tag, `-e converge_primary=true` and `-e engine_image_digest=sha256:<digest>` (the engine row of `docs/reference/fleet-pins.md`; the role asserts the digest before the store copy, so a converge without it aborts with the unit stopped), inside the inter-cycle gap and outside a published Kraken maintenance window checked immediately before (`.claude/rules/fleet-deploys.md`), so the role's copy for an absent store re-delivers it, and start the unit.
```

`grep -c '^   A boundary with `snapshots/cycle-<HH>/` but no record raised' infra/runbooks/engine.md` prints `1`. Replace that whole line (it begins with three spaces and ends `go to the failed-cycle section below.`) with:

```
   A boundary with `snapshots/cycle-<HH>/` but no record raised **after** snapshotting (store or model side); no snapshots dir at all raised before the first snapshot file: the refresh did not get that far (store unreadable, config), or the snapshot write refused a close the store holds at a present stamp, which the traceback step 2 greps names with its pair, grid, bar and value (the third bullet under *What it means*, with the repair). A `failed-cycle-<HH>.json` present means this is not your alert: go to the failed-cycle section below.
```

Neither text carries a universal word (every, never, always, only, any, cannot) outside a code span: the commit-msg hook refuses one on this page.

- [ ] **Step 2: Resolve T0200**

In `docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md`: change `status: open` to `status: resolved`; delete the `ripe_when:` line (one line in this file); replace the `## Suggested next steps` heading and its three bullets, everything from that heading to the end of the file, with:

```
## Resolution

Resolved by spec `00116` and the PR that carries it: the refusal lives at the engine's own write. `_journal_snapshots` in `cli/engine/cycle.py` walks every close of every grid before the first snapshot file is written and refuses a present close that is not a finite positive number as an `EngineError` naming the pair, the grid, the bar index, the stamp and the value, so a refused boundary leaves no snapshot directory, no record, no sidecar and no orders beside the venue record of step 0; `None` at a union absence is admitted. No `SnapshotEntry` field was added and the shared `write_parquet` is untouched, which answers the third next step, since the door is the engine's and reaches no other package, and records for [[T0199]] that its helper arm is not the place. The read-side refusal from [[T0193]] stays for records written before the door. The abort's shape is the raise, as the forming-row guard's; the operator reading is the cycle-stale runbook's bullet and its step 3, naming the host's repair as a re-delivery by the engine-tagged converge, since `zcrypto engine seed` is the workstation's command; and that seed reads the newest whole frozen `ohlc-full` sibling under the configured data root, the same PR's earlier commit, without which a 4h leg could not be re-seeded. Measured before the change over the NAS journal mirror on 2026-09-21: 433 records, 9,508 snapshot files, 0 unusable present closes among 156,359,450 close rows, so no record on disk is refused by the read for this reason. The owner's ruling of 2026-09-20 in chat set the placement and the shape.
```

Then `grep '^#' docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md` prints the H1, `## Context — what`, `## Why this matters`, `## Findings so far` and `## Resolution`, in that order and nothing else. Then:

```bash
git mv docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md docs/open-topics/archive/
```

- [ ] **Step 3: Tell T0199 what was decided for the shared helper, and close that arm in its trigger and its first next step**

`grep -c '^\*\*This topic and \[\[T0200\]\] are one door\.\*\*' docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` prints `1`. That paragraph ends `so whichever is decided first records what it decided for the other.` Append to the same line, after that full stop, one space and:

```
Decided first by [[T0200]], resolved by spec `00116`: the helper is not the door; the engine's own snapshot write refuses an unusable present close before its first file, and the shared `write_parquet` stays as it is, so this fork's helper arm is closed and its other halves stand.
```

In the file's `ripe_when:` line (line 3, one line), delete the text `, or the shared `write_parquet` in `cli/ohlc/dataset.py`` so the clause reads `-- `seed_store` or its door `_require_joinable_ts` in `cli/engine/store.py` -- to `seam_overlap``.

Replace the first bullet under `## Suggested next steps`, the three wrapped lines

```
- Decide where the refusal belongs: at `write_parquet` (an engine, OHLC, backfill and derivatives blast radius, and it
  would refuse a frame a research path may legitimately hold), or as a distinguishing REASON on the report's
  `dropped_tail` line, which changes no writer.
```

with the one line

```
- Decide whether the refusal's second home is a distinguishing REASON on the report's `dropped_tail` line, which changes no writer; the `write_parquet` arm is closed (spec `00116` D4: the engine's own snapshot write refuses, the shared helper stays).
```

- [ ] **Step 4: Re-render the index and run the guards**

Run: `uv run python infra/scripts/topics-index.py`
Expected: `docs/open-topics/README.md` changes; T0200 moves from `## Open` to `## Resolved` with its link under `archive/`; T0199's bullet carries the shortened trigger.

Run: `uv run pytest -q tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_internal_terms_not_operator_visible.py tests/test_guidance_refs_resolve.py`
Expected: every test passed.

- [ ] **Step 5: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. The commit-msg hooks run at Step 6.

- [ ] **Step 6: Commit**

```bash
git add infra/runbooks/engine.md docs/open-topics/README.md docs/open-topics/archive/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md
git commit -m "docs(topics): T0200 resolved at the engine's own write, the cycle-stale page names the refusal and the host's repair

The runbook's bullet on a raising \`run_cycle\`, re-led as raised before journaling the boundary,
says what a traceback naming a pair, a grid, a bar and a close that is not a finite positive number
means and names the repair as it is on the host: a re-delivery by the attended engine-tagged
converge, with the digest and inside both of the fleet rule's gates, after the store dir is moved
aside, since \`zcrypto engine seed\` is the workstation's command and reaches nothing older than the
REST window; step 3's artifact-state line gains the cause the door adds, a boundary with no
snapshots directory whose store reads fine. T0200 is resolved and archived with the door's
placement, the shape the spec settled and the mirror's reading of 2026-09-21; T0199's one-door
paragraph records that the shared writer is not the door, and its trigger and first next step drop
that arm.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

---

## Self-review

- Spec coverage: D1 (the pre-pass, the collect-then-raise-once shape and its counts) and D2 are Task 1 Step 3 and its case; D3 and D4 are the Global Constraint confining the source change; D5 changes nothing and the case's docstring says which refusal is the only one on its path; D6 is what Task 1's raise inherits from `_invoke_cycle`, unchanged, the case asserts the venue record it names, and Task 1 Step 3 routes `run_cycle`'s docstring as D6 says; D7 is Task 3 Step 1, both edits, the digest and both gates; D8 is Task 2, the configured data root, the seed's own voice, the pinned constant and the catalog. The measured basis is the spec's and no task re-measures it.
- Placeholders: `PROBE_VERDICT` is the one token, replaced in Task 1 Step 7 and checked to be gone; `<model>` in the trailers is the executing model's own name, a Global Constraint; `<digest>` in the runbook text is the operator's read of the fleet pins, named beside it.
- Names: `_journal_snapshots`, `EngineError`, `read_parquet`, `_env`, `_tail_fetch`, `_clock`, `CYCLE_TS` are the test module's and the cycle module's existing names; `resolve_canonical_root`, `DataSyncError`, `resolve_data_dir`, `ConfigError`, `seed_store`, `_abort`, `_load_app_config`, `_patch_config`, `runner`, `app`, `_output`, `SeedReport` exist where Task 2 says; no task introduces a module-level name.
- Order: Task 3's texts describe Task 2's seed, and a Global Constraint holds Task 3 behind Task 2.
