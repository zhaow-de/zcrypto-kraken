# The journal's snapshot write refuses an unusable close — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `run_cycle` refuses to journal a snapshot holding a present close that is not a finite positive number, before the first snapshot file is written, naming the pair, the grid, the bar, the stamp and the value; T0200 is resolved.

**Architecture:** One pre-pass inside `_journal_snapshots` in `cli/engine/cycle.py` over the union-aligned closes it is about to hash, raising `EngineError` before the write loop; the raise propagates the way the forming-row guard's does, so the node logs it and the boundary stays journal-absent. No record field, no schema change, no change to the shared parquet writer. The runbook's cycle-stale bullet gains the reading, the topic is resolved and archived, and T0199's file records what this decided for their shared helper.

**Tech Stack:** Python 3.14, pytest, polars (only to spoil a store frame below the engine's own writer, which refuses a NaN); `infra/scripts/mutate-probe.sh` for the guard verdicts; `topic-ops` for the closeout.

**Spec:** `docs/specs/00116-snapshot-write-refuses-unusable-close-design.md`

## Global Constraints

- The source change is confined to `_journal_snapshots` in `cli/engine/cycle.py`. `cli/engine/journal.py` (spec D3: no `SnapshotEntry` field, no `SCHEMA_VERSION` step) and `cli/ohlc/dataset.py` (spec D4: `write_parquet` untouched) do not change.
- The refusal's message names the pair as `<symbol>@<interval>`, the bar as `close[<k>]`, the stamp in ISO 8601 and the value as its `repr`, and carries no topic id, spec serial or decision number: `tests/test_internal_terms_not_operator_visible.py` walks every Python file's operator-visible strings. Provenance goes in the comment beside the code and in the commit message.
- `None` is admitted by the refusal (spec D2); the predicate reads `close is not None` before anything else.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend, the tree clean. The probe never runs while a pytest run is in flight in the same checkout.
- Every commit is green over the changed files' consumers, `uv run pytest -q tests/test_engine_cycle.py tests/test_engine_node.py tests/test_engine_command.py tests/test_engine_metrics.py tests/test_ops_daily_soak.py`, and `uv run pre-commit run -a` is clean; the full suite is CI's, on the pull request.
- No step reaches a host, a venue or a mount: the spec's measured basis was read by the controller before this plan, and nothing here re-reads it.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. An existing file's lines are left as they are.
- No string literal added to `infra/runbooks/engine.md` or to `cli/engine/cycle.py`'s messages names a spec, a decision or a topic.
- A commit message ends with these two trailers, the model name being the executing model's own (`Claude Fable 5.1`, `Claude Opus 5`, ...):

```
Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd
```

---

## File structure

- Modify `cli/engine/cycle.py` — `_journal_snapshots` gains the pre-pass and its raise (Task 1).
- Modify `tests/test_engine_cycle.py` — `import polars as pl` and one parametrised case beside the forming-row guard's cases (Task 1).
- Modify `infra/runbooks/engine.md` — the `zcrypto-engine-cycle-stale` › What it means bullet on a raising `run_cycle` gains one sentence (Task 2).
- Modify `docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md` — resolved, moved to `docs/open-topics/archive/` (Task 2).
- Modify `docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` — the one-door paragraph records what T0200 decided for the shared helper (Task 2).
- Modify `docs/open-topics/README.md` — re-rendered by `infra/scripts/topics-index.py` (Task 2).

---

### Task 1: The snapshot write refuses an unusable present close before the first file

**Files:**
- Modify: `cli/engine/cycle.py` (`_journal_snapshots`, the function whose first line is `rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"`)
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
@pytest.mark.parametrize(("symbol", "interval", "bar"), [("ETH/BTC", 240, 2), ("ADA/EUR", 1440, 1)])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 0.0, -5.0])
def test_an_unusable_present_close_refuses_the_cycle_before_any_snapshot_is_written(
    tmp_path, monkeypatch, symbol, interval, bar, bad
):
    """The journal's snapshot write is the door: a present close the replay's validator would refuse is refused
    before the first snapshot file exists, naming the pair, the grid, the bar, the stamp and the value.

    `ETH/BTC` is a leg no builder input reads and both bars sit outside the refresh overlap (the last two rows), so
    nothing else on the path refuses either value; with the stubbed builder the EUR leg's mid-series bar is the
    same, and the daily grid is covered through it."""
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
    day_dir = config.journal_dir / "2026-07-10"
    # Refused before the FIRST file: no snapshot directory, no record, no sidecar, no orders.
    assert not (day_dir / "snapshots").exists()
    assert not (day_dir / "cycle-08.json").exists()
    assert not (day_dir / "failed-cycle-08.json").exists()
    assert not (day_dir / "orders.jsonl").exists()


```

- [ ] **Step 2: Run the case to verify it fails**

Run: `uv run pytest -q tests/test_engine_cycle.py -k unusable_present_close`
Expected: `10 failed`, each with `Failed: DID NOT RAISE EngineError` (the stubbed builder accepts the value and the cycle succeeds).

- [ ] **Step 3: Add the pre-pass to `_journal_snapshots`**

In `cli/engine/cycle.py`, replace the first line of `_journal_snapshots`'s body:

```python
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
```

with:

```python
    # Every series is read through the refusal before the first file is written, so a refused boundary leaves no
    # snapshot directory: a present close the replay's validator would refuse is refused here, where the cycle
    # still holds the frame and has published nothing (spec 00116 D1). `None` is a union absence and is admitted
    # (D2); the type door is `read_store_series`'s, so nothing but a float or an int reaches this predicate.
    for interval in GRID_INTERVALS:
        union_ts, prices = aligned[interval]
        for symbol in PAIR_KEYS:
            for k, close in enumerate(prices[symbol]):
                if close is not None and (not math.isfinite(close) or close <= 0):
                    raise EngineError(
                        f"the snapshot for {symbol}@{interval} cannot be journaled: close[{k}] at "
                        f"{union_ts[k].isoformat()} is {close!r}, not a finite positive number -- the store holds an "
                        "unusable close at a present stamp; nothing was journaled and no target was published"
                    )
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
```

- [ ] **Step 4: Run the case, then the changed files' consumers**

Run: `uv run pytest -q tests/test_engine_cycle.py -k unusable_present_close`
Expected: `10 passed`

Run: `uv run pytest -q tests/test_engine_cycle.py tests/test_engine_node.py tests/test_engine_command.py tests/test_engine_metrics.py tests/test_ops_daily_soak.py`
Expected: every test passed, the only two skips `tests/test_engine_node.py`'s live-venue gates; `test_union_alignment_journals_none_at_absences_and_replays_clean` among the passes, which is the `None`-admitted case.

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
ruling of 2026-09-20 (T0200) the write walks every close of every grid before the first file and
refuses a present close that is not a finite positive number as an \`EngineError\` naming the pair,
the grid, the bar, the stamp and the value; \`None\` at a union absence is admitted; no record field,
no schema step, the shared parquet writer untouched. The raise propagates as the forming-row
guard's does: the node logs it and the boundary stays journal-absent with nothing under it.

Case: ten values by leg and grid, the BTC-quoted 4h leg and the EUR daily leg outside the refresh
overlap, each refused with the message's five names and no snapshot directory, record, sidecar or
orders on disk.

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

### Task 2: The operator reading, the topic's closeout and what T0199 is told

**Files:**
- Modify: `infra/runbooks/engine.md` (the bullet under `## zcrypto-engine-cycle-stale — ALERT` › `### What it means` that begins ``- **`run_cycle` raised before writing anything**``)
- Modify: `docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md`, then `git mv` it to `docs/open-topics/archive/`
- Modify: `docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` (the paragraph under `## Findings so far` that begins `**This topic and [[T0200]] are one door.**`)
- Modify: `docs/open-topics/README.md` (rendered, never edited by hand)

**Interfaces:**
- Consumes: Task 1's refusal and its message shape.
- Produces: nothing code reads; `tests/test_open_topics_frontmatter.py` reads the two topic files and the index.

- [ ] **Step 1: Extend the runbook bullet**

`grep -c '^- \*\*`run_cycle` raised before writing anything\*\*' infra/runbooks/engine.md` prints `1`. That bullet ends with the text `reads "the node is up but a cycle raised; suspect the store".` Append to the same line, after that full stop, one space and:

```
A traceback whose message names a pair, a grid, a bar and a close that is "not a finite positive number" is the cycle refusing to journal what the store holds at that stamp, before it wrote anything: the repair is the store's, the seed the poisoned-store case takes, and every re-run over the unrepaired store refuses the same way.
```

- [ ] **Step 2: Resolve T0200**

In `docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md`: change `status: open` to `status: resolved`; delete the `ripe_when:` line (the whole line, including its continuation, is one line in this file); replace the `## Suggested next steps` heading and its three bullets, everything from that heading to the end of the file, with:

```
## Resolution

Resolved by spec `00116` and the PR that carries it: the refusal lives at the engine's own write. `_journal_snapshots` in `cli/engine/cycle.py` walks every close of every grid before the first snapshot file is written and refuses a present close that is not a finite positive number as an `EngineError` naming the pair, the grid, the bar index, the stamp and the value, so a refused boundary leaves no snapshot directory, no record, no sidecar and no orders; `None` at a union absence is admitted. No `SnapshotEntry` field was added and the shared `write_parquet` is untouched, which answers the third next step, since the door is the engine's and reaches no other package, and records for [[T0199]] that its helper arm is not the place. The read-side refusal from [[T0193]] stays for records written before the door. The abort's shape is the raise, as the forming-row guard's, and the operator reading is the cycle-stale runbook's existing bullet, extended. Measured before the change over the NAS journal mirror on 2026-09-21: 433 records, 9,508 snapshot files, 0 unusable present closes among 156,359,450 close rows, so no record on disk is refused by the read for this reason. The owner's ruling of 2026-09-20 in chat set the placement and the shape.
```

Then `grep '^#' docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md` prints the H1, `## Context — what`, `## Why this matters`, `## Findings so far` and `## Resolution`, in that order and nothing else. Then:

```bash
git mv docs/open-topics/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md docs/open-topics/archive/
```

- [ ] **Step 3: Tell T0199 what was decided for the shared helper**

`grep -c '^\*\*This topic and \[\[T0200\]\] are one door\.\*\*' docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md` prints `1`. That paragraph ends `so whichever is decided first records what it decided for the other.` Append to the same line, after that full stop, one space and:

```
Decided first by [[T0200]], resolved by spec `00116`: the helper is not the door; the engine's own snapshot write refuses an unusable present close before its first file, and the shared `write_parquet` stays as it is, so this fork's helper arm is closed and its other halves stand.
```

- [ ] **Step 4: Re-render the index and run the guards**

Run: `uv run python infra/scripts/topics-index.py`
Expected: `docs/open-topics/README.md` changes; T0200 moves from `## Open` to `## Resolved` with its link under `archive/`.

Run: `uv run pytest -q tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_internal_terms_not_operator_visible.py tests/test_guidance_refs_resolve.py`
Expected: every test passed.

- [ ] **Step 5: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 6: Commit**

```bash
git add infra/runbooks/engine.md docs/open-topics/README.md docs/open-topics/archive/T0200-journal-snapshot-metadata-carries-no-finiteness-claim.md docs/open-topics/T0199-store-nan-drops-a-tail-instead-of-refusing.md
git commit -m "docs(topics): T0200 resolved at the engine's own write, the cycle-stale reading names the refusal

The runbook's bullet on a raising \`run_cycle\` says what a message naming a pair, a grid, a bar and
a close that is not a finite positive number means and where the repair is. T0200 is resolved and
archived with the door's placement, the shape the spec settled and the mirror's reading of
2026-09-21; T0199's one-door paragraph records that the shared writer is not the door, so its
helper arm is closed and its other halves stand.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QL5VMcRChTfVeL5fwZb9rd"
```

---

## Self-review

- Spec coverage: D1 and D2 are Task 1 Step 3 and its case; D3 and D4 are the Global Constraint confining the source change; D5 changes nothing and the case's docstring says which refusal is the only one on its path; D6 is what Task 1's raise inherits from `_invoke_cycle`, unchanged; D7 is Task 2 Step 1. The measured basis is the spec's and no task re-measures it.
- Placeholders: `PROBE_VERDICT` is the one token, replaced in Task 1 Step 7 and checked to be gone; `<model>` in the trailers is the executing model's own name, a Global Constraint.
- Names: `_journal_snapshots`, `EngineError`, `read_parquet`, `_env`, `_tail_fetch`, `_clock`, `CYCLE_TS` are the test module's and the cycle module's existing names; nothing new is named across tasks.
