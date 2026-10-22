# B2's second signal reading — the eight untested crowding signals' forward returns on frozen ohlc-full, by tail and by arm A's state: the block contrast, the reading subject, its run and its entry — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b2.py tests/test_alpha_b2.py cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b2_second_signal_reading_basis.py docs/reference/reading-ledger.jsonl tests/retired_subjects.py docs/research/10.phase4-decisions.md docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00141-b2-signal-reading-2-design.md docs/plans/00141-b2-signal-reading-2.md` prints `tier: full`, for `tests/test_alpha_b2.py` "a test importing cli.alpha.b1", `tests/test_research_command.py` "a test importing cli.alpha", and, once Task 3 has created it, `tests/test_research_b2_second_signal_reading_basis.py` "a test importing cli.registry.observed").

**Goal:** B2's second signal reading (spec 00141) — the OI log-delta's and momentum's z-scores on the OI grid, the stationary-bootstrap draw held as its blocks and the block contrast in `cli/alpha/b2.py`; one reading subject, `b2-second-signal-reading`, in `cli/research/subjects.py`; the data-gated test of its inputs; the owner's pick and the reading's conventions in the decisions log before the hash; the reading's one run, kept on the reading ledger and replayed; its finding, T0023, T0016 and the subject's retirement.

**Architecture:** no new module. `cli/alpha/b2.py` gains `oi_log_delta_zscore_grid_feature` and `oi_momentum_zscore_grid_feature`, each through `_oi_at_union_closes`; `BootstrapBlocks` and `stationary_bootstrap_blocks`, which replays `stationary_bootstrap_indices`' draws and holds each resample as its blocks; `event_contrast_blocks`, `event_contrast_chunked`'s rows from those blocks with its far bounds at the percentiles it is given; and the imports `array` and `NamedTuple`. `cli/research/subjects.py` gains one reading machinery — the constants, four readers (`_b2_oi_log_delta_signal`, `_b2_oi_momentum_signal`, `_b2_ratio_signals`, `_b2_liq_side_signals`), `_b2_reading_2_inputs`, `_b2_reading_2_metrics`, `_build_b2_second_signal_reading` and `_B2_READING_2_KEYS`, reading 3's `_B2ReadingInputs`, `_b2_reading_flags`, `_b2_reading_counts` and `_b2_reading_forwards` read as they are — and one `SUBJECTS` entry. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; numpy; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00141-b2-signal-reading-2-design.md` — binding; D1–D9 are cited by name and the values below are copied from it. It reads spec 00140's instrument, arm A, tails, states, forwards and criterion and spec 00138's ratio and daily-liquidation readers, all frozen (records 52–56's and readings 2–3's `spec_hash`). **Iteration:** iter-185. **Topic:** T0023 under T0016. **Branch:** `research/iter-185-b2-signal-reading-2`, worktree `.claude/worktrees/iter185`, `data/ohlc-full`, `data/derivatives-oi` and `data/liquidations-daily` linked read-only from the main checkout (and `data/derivatives-funding`, linked and unread). A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: the code and tests of Tasks 1–3 were written in this worktree and run green (`18 passed, 160 deselected` for Task 1's new cases and `178 passed` for its file, `13 passed, 705 deselected` for Task 2 step 6's selection and `2 passed` for its two fixture rows, `1 passed` for Task 3's data-gated case in 180 s), their red readings taken in a detached worktree at the base (Task 1 an `ImportError` on `event_contrast_blocks` at collection, Task 2 `13 failed, 696 deselected` over Task 1's code), the gates and the cli diff measured, the slow cases timed, Task 3 step 5's two entries run through the decisions-log tests in a detached scratch worktree (`50 passed`), Task 6 step 4's retirement collected there (no case of the subject under `-m "not retired"`, 21 under `-m retired`, `tests/test_retired_subjects.py` `5 passed`), Tasks 1–2's sixty-five probe rows run in a detached scratch worktree on that tree, sixty-five of sixty-five `KILLED`, and Task 4's two programs parsed and run over a synthetic ledger line in scratch (every check true and exit 0, a wrong spec hash exit 1; the print 96 lines, nine `no row`); the files were then restored to the base before this plan was committed. Not run: the reading itself and its replay (Task 5), the topic edits (Task 6 steps 1–3) and the PR (Task 7).

## Global Constraints

- **The signals, tails, states and forwards** (D3–D5): `_b2_reading_2_inputs` runs `_b2_overlay_inputs(subject, _b2_oi_log_delta_signal, 2.0, reader, dataset, window, accept_holes)` for the union, its two window refusals and arm A, then `_b2_oi_momentum_signal`, `_b2_ratio_signals` and `_b2_liq_side_signals` over its `h4_ts`, keyed in this order `binperp_oi_log_delta_z30d`, `binperp_oi_momentum_z30d`, `binperp_count_toptrader_long_short_ratio_z30d`, `binperp_sum_toptrader_long_short_ratio_z30d`, `binperp_count_long_short_ratio_z30d`, `binperp_sum_taker_long_short_vol_ratio_z30d`, `binperp_liq_short_z30d` and `binperp_liq_total_z30d`; the OI pair the 180-mark z-scores, through `funding_zscore` at `_OI_ZSCORE_WINDOW`, of `oi_log_delta` and of `oi_momentum` at `_OI_MOMENTUM_LOOKBACK` on the OI grid; the ratios trial 4's own `ratio_zscore_grid_features` singly; the liquidation pair `daily_zscore_grid_feature` over `short_usd` and over `long_usd + short_usd`; the tails, states and forwards reading 3's, through `_b2_reading_flags` at `_B2_READING_THRESHOLD = 2.0` (above, z > 2.0; below, z < −2.0; long, arm A above 0; flat, arm A at 0) and `_b2_reading_forwards` (`fwd_logret_4h`, `fwd_logret_24h`, `fwd_logret_96h`, `fwd_sumret_4h`, `fwd_sumret_24h`, `fwd_sumret_96h`), unchanged.
- **The contrast** (D6): one draw, `stationary_bootstrap_blocks(len(inputs.close), mean_block=102, n_resamples=40_000, seed=42)`, then per signal, tail and state one `event_contrast_blocks(flags, forwards, blocks, far=(2.5 / 96, 100 - 2.5 / 96))` call over the six forward series, 32 in all; a row is `[events, others, mean after the events, mean after the others, difference, 2.5 %, 97.5 %, far low, far high]`, its first five entries `event_contrast_chunked`'s to the bit and its four bounds that contrast's to rounding.
- **The keys** (D7): 54 — `<signal key>_fwd_logret_<4·H>h` and `<signal key>_fwd_sumret_<4·H>h` for each signal and horizon, `events_per_asset`, `others_per_asset`, `threshold` 2.0, `mean_block` 102, `n_resamples` 40000, `far_percentiles` `[2.5 / 96, 100 - 2.5 / 96]`; the counts the measured basis's (Task 3's literals).
- **The criterion** (D8): read by Task 5's entry off the pooled rows, never by code; the subject has no rule, and no program of this plan judges a cell. Its floor and four legs are written in words in two places beside D8, which a read against D8 alone checks — the conventions entry (Task 3 step 5) and the run's notes (Task 5 step 2) — and the pooled-rows print (Task 4 step 5) carries every entry the floor and the legs read — the log forward's kept assets and events, its far bounds and difference, and the summed returns' mean after the events — beside the others. Every statement of a bound names its family, the log forward's or the summed returns'.
- **The hash rule** (D9): before Task 4 step 2 takes the spec's sha256, nobody computes a forward return over the real data or runs `b2-second-signal-reading` over the real sets; the data-gated test (Task 3) computes positions, signals, counts and the block, and no forward; no reader, reviewer or plan-review dispatch runs the subject over the real sets before the hash, and every read's dispatch carries this rule. The subject is evaluated over the real sets once, by Task 5's `--reading` run, never as a plain eval; after that run it is rebuilt over them only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with the sets linked, as Task 5 step 5 and Task 7 step 2's reads run it.
- **Unchanged** (D7): every existing function of `cli/alpha/b2.py` and `cli/research/subjects.py` — reading 3's machinery among them — `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/validation/*`, `cli/engine/*` and `cli/liquidations/*`; the subjects of trials 1–7 and of readings 1–3; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/alpha/b2.py` from Task 1 on and `cli/research/subjects.py` from Task 2 on, nothing else; `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/ | grep -c '^-[^-]'` prints 0 — both files gain lines and lose none. Measured on the authoring tree, the hunks: `cli/alpha/b2.py`'s `@@ -5,0 +6 @@`, `@@ -10,0 +12 @@`, `@@ -244,0 +247,24 @@` and `@@ -506,0 +533,106 @@`; `cli/research/subjects.py`'s `@@ -61,0 +62 @@`, `@@ -66,0 +68,2 @@`, `@@ -76,0 +80 @@`, `@@ -3064,0 +3069,149 @@` and `@@ -3376,0 +3530,9 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00141-b2-signal-reading-2-design.md` after Task 4 step 2, nor specs 00128, 00131 and 00137–00140, nor the spec before then except a fix commit a read of Task 3 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 5 names it — and this plan never runs `--register`. Never `git stash`; no amend; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, `data/derivatives-oi` and `data/liquidations-daily`, read-only links, never written under; `data/derivatives-funding` is linked and the reading never reads it. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The reading, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 4 step 3, Task 5 step 1) and Task 7's `gh` calls, push and `merge-pr` are the exceptions.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 6's reads, Tasks 4–5 and Task 7, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the reading, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 6 and Task 3's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00141 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00141/` follows `mkdir -p .tmp/plan-00141 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00141/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && mkdir -p .tmp/plan-00141 && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt`, never a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every `T` holding `tests/test_research_command.py` runs it in three parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms: `tests/test_research_command.py -k "not reentry"` (`--basetemp=.tmp/plan-00141/pt-1`, measured on the authoring tree, Tasks 1–2's code in it, `557 passed, 161 deselected in 456.09s`), `tests/test_research_command.py -k reentry` (`pt-2`, measured `71 passed, 647 deselected in 89.27s`) and the rest of `T` (`pt-3`). A commit message's test result line is a run over that commit's own tree.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00141 &&
  test ! -e .tmp/plan-00141/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00141/probe HEAD &&
  git -C .tmp/plan-00141/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00141/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00141/probe/.tmp
```

  Then, from `.tmp/plan-00141/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. After the last verdict, `git worktree remove --force .tmp/plan-00141/probe` — a data link in it unlinked first, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, each set it linked still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subject's name** (D2): `b2-second-signal-reading`, so its case ids open with a name no other subject's opens; reading 3's own case ids include `b2-signal-reading-2-bar-window` (its 2-bar-window row), so no selection or count of this plan keys on `b2-signal-reading-2`, which names this branch, the spec and the plan alone.

## Task 1: the OI change's and momentum's z-scores, the block draw and the block contrast in `cli/alpha/b2.py` (D4, D6)

**Files:** Modify `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

**Interfaces:** Produces `oi_log_delta_zscore_grid_feature(oi_ts, oi_values, union_ts)` and `oi_momentum_zscore_grid_feature(oi_ts, oi_values, union_ts) -> list[float | None]`; `BootstrapBlocks(n_obs, starts, lengths, firsts)`, a `NamedTuple` of the draw's 32-bit arrays; `stationary_bootstrap_blocks(n_obs, *, mean_block, n_resamples, seed) -> BootstrapBlocks`, refusing with `stationary_bootstrap_indices`' own `ValidationError` what that function refuses; and `event_contrast_blocks(flags, forwards, blocks, *, far) -> dict[str, dict[str, list[float]]]`, refusing with `AlphaError` what it cannot pair, through the module's `_check_lengths` and `_check_paired`, a draw over another count of indices, and `far` other than a tuple of two numbers 0 ≤ low < high ≤ 100.

- [ ] **Step 1: Write the failing tests** — in `tests/test_alpha_b2.py`, the `from cli.alpha.b2 import (` block gains `event_contrast_blocks,` after `event_contrast,`, `oi_log_delta_zscore_grid_feature,` after `oi_log_delta_grid_feature,`, `oi_momentum_zscore_grid_feature,` after `oi_momentum_grid_feature,` and `stationary_bootstrap_blocks,` after `scale_positions,`; and at the end of the file, after `test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1`:

```python
def test_the_oi_log_delta_zscore_is_taken_over_180_grid_log_deltas_and_reads_warm_at_a_late_union():
    # Each level twice the last, then four times it: every grid log-delta log(2), then log(4); each bar's earlier row, 1.5
    # times its level, is never read. A union opening at the last two marks reads them warm.
    oi_ts, oi_values, union_ts = _oi_on_the_grid([2.0**k for k in range(181)] + [2.0**182])
    spike = [0.0, pytest.approx(179 / math.sqrt(180))]
    assert oi_log_delta_zscore_grid_feature(oi_ts, oi_values, union_ts) == [None] * 180 + spike
    assert oi_log_delta_zscore_grid_feature(oi_ts, oi_values, union_ts[180:]) == spike


def test_the_oi_momentum_zscore_is_taken_over_180_grid_momenta_and_reads_warm_at_a_late_union():
    # Each level twice the last, then four times it: every 180-bar momentum the same, then the last about twice it.
    oi_ts, oi_values, union_ts = _oi_on_the_grid([2.0**k for k in range(360)] + [2.0**361])
    spike = [0.0, pytest.approx(179 / math.sqrt(180))]
    assert oi_momentum_zscore_grid_feature(oi_ts, oi_values, union_ts) == [None] * 359 + spike
    assert oi_momentum_zscore_grid_feature(oi_ts, oi_values, union_ts[359:]) == spike


@pytest.mark.parametrize(
    ("n_obs", "mean_block", "n_resamples", "seed"),
    [(30, 3, 25, 7), (16, 1, 4, 2), (1, 2, 3, 5), (40, 1000, 6, 9)],
    ids=["short-blocks", "every-index-fresh", "one-index", "long-blocks-wrapping"],
)
def test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks(n_obs, mean_block, n_resamples, seed):
    blocks = stationary_bootstrap_blocks(n_obs, mean_block=mean_block, n_resamples=n_resamples, seed=seed)

    bounds = [*blocks.firsts.tolist(), len(blocks.starts)]
    spans = [zip(blocks.starts[a:b].tolist(), blocks.lengths[a:b].tolist()) for a, b in zip(bounds, bounds[1:])]
    resamples = [[(start + step) % n_obs for start, length in span for step in range(length)] for span in spans]
    assert blocks.n_obs == n_obs
    assert resamples == stationary_bootstrap_indices(n_obs, mean_block=mean_block, n_resamples=n_resamples, seed=seed)
    # Four bytes an entry: the reading's draw holds about 10.8 million blocks.
    assert {values.dtype.itemsize for values in (blocks.starts, blocks.lengths, blocks.firsts)} == {4}


@pytest.mark.parametrize(
    ("change", "match"),
    [
        pytest.param({"n_obs": 0}, "n_obs must be an int >= 1, got 0", id="no-index"),
        pytest.param({"mean_block": 0.5}, "mean_block must be finite and >= 1, got 0.5", id="block-under-1"),
        pytest.param({"n_resamples": 0}, "n_resamples must be an int >= 1, got 0", id="no-resample"),
    ],
)
def test_the_block_draw_refuses_what_the_stationary_bootstrap_refuses(change, match):
    arguments = {"n_obs": 3, "mean_block": 2, "n_resamples": 10, "seed": 1} | change
    with pytest.raises(ValidationError, match=match):
        stationary_bootstrap_blocks(**arguments)
    with pytest.raises(ValidationError, match=match):
        stationary_bootstrap_indices(**arguments)


def _bounds_at(rows: list[tuple[list, list]], draws: list[list[int]], low: float, high: float) -> list[float]:
    """The percentiles `low` and `high`, as fractions, by hand, of the differences over the resamples holding an event and
    another."""
    diffs = []
    for idx in draws:
        ev = [values[k] for flags, values in rows for k in idx if flags[k] is True and values[k] is not None]
        ot = [values[k] for flags, values in rows for k in idx if flags[k] is False and values[k] is not None]
        if ev and ot:
            diffs.append(sum(ev) / len(ev) - sum(ot) / len(ot))
    diffs.sort()
    return [_percentile(diffs, low), _percentile(diffs, high)]


def test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given():
    forwards = {"ret": _CHUNKED_RET, "late": _CHUNKED_LATE, "none": {a: [None] * 16 for a in _CHUNKED_FLAGS}}
    blocks = stationary_bootstrap_blocks(16, mean_block=3, n_resamples=200, seed=7)

    out = event_contrast_blocks(_CHUNKED_FLAGS, forwards, blocks, far=(0.05, 99.95))

    chunked = event_contrast_chunked(_CHUNKED_FLAGS, forwards, mean_block=3, n_resamples=200, seed=7)
    assert {series: list(rows) for series, rows in out.items()} == {series: list(rows) for series, rows in chunked.items()}
    for series, rows in out.items():
        for name, row in rows.items():
            assert row[:5] == chunked[series][name][:5], (series, name)
            assert row[5:] == pytest.approx(chunked[series][name][5:], rel=1e-12, abs=1e-15), (series, name)
    assert {type(v) for rows in out.values() for row in rows.values() for v in row} <= {int, float}
    draws = stationary_bootstrap_indices(16, mean_block=3, n_resamples=200, seed=7)
    at_one = event_contrast_blocks(_CHUNKED_FLAGS, forwards, blocks, far=(1, 99))
    for name, members in (("ETH", ["ETH"]), ("pooled", ["BTC", "ETH"])):
        rows = [(_CHUNKED_FLAGS[a], _CHUNKED_RET[a]) for a in members]
        assert at_one["ret"][name][7:] == pytest.approx(_bounds_at(rows, draws, 0.01, 0.99), rel=1e-12, abs=1e-15), name


@pytest.mark.parametrize(
    ("change", "match"),
    [
        pytest.param({"n_obs": 4}, "blocks draw over 4 indices and the flags hold 3", id="another-draw"),
        pytest.param({"far": [0.05, 99.95]}, "got [0.05, 99.95]", id="far-a-list"),
        pytest.param({"far": (0.05, 50, 99.95)}, "got (0.05, 50, 99.95)", id="far-three"),
        pytest.param({"far": (False, 99.95)}, "got (False, 99.95)", id="far-a-bool"),
        pytest.param({"far": (-0.05, 99.95)}, "got (-0.05, 99.95)", id="far-below-0"),
        pytest.param({"far": (99.95, 99.95)}, "got (99.95, 99.95)", id="far-not-rising"),
        pytest.param({"far": (0.05, 100.05)}, "got (0.05, 100.05)", id="far-above-100"),
        pytest.param({"forwards": {"ret": {"BTC": [0.1]}}}, "forwards['ret']['BTC'] has length 1, expected 3", id="forward-length"),
    ],
)
def test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward(change, match):
    arguments = {"flags": {"BTC": [True, False, True]}, "forwards": {"ret": {"BTC": [0.1, 0.2, 0.3]}}, "far": (0.05, 99.95)}
    arguments |= {key: value for key, value in change.items() if key != "n_obs"}
    blocks = stationary_bootstrap_blocks(change.get("n_obs", 3), mean_block=2, n_resamples=10, seed=1)
    with pytest.raises(AlphaError, match=re.escape(match)):
        event_contrast_blocks(blocks=blocks, **arguments)
```

- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00141 && uv run pytest tests/test_alpha_b2.py -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt`: an `ImportError` on `event_contrast_blocks`, collection stopping.
- [ ] **Step 3: Implement** — in `cli/alpha/b2.py`, `from array import array` after `import statistics` and `from typing import NamedTuple` after `from functools import partial`; after `oi_momentum_grid_feature`:

```python
def oi_log_delta_zscore_grid_feature(
    oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]
) -> list[float | None]:
    """The log-delta's trailing z-score over the OI z-score's window, both taken on the OI grid, never at the union's
    closes (docs/specs/00141 D4)."""

    def zscore(levels: list[float | None]) -> list[float | None]:
        return funding_zscore(oi_log_delta(levels), window=_OI_ZSCORE_WINDOW)

    return _oi_at_union_closes("log-delta z-score", zscore, oi_ts, oi_values, union_ts)


def oi_momentum_zscore_grid_feature(
    oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]
) -> list[float | None]:
    """The momentum's trailing z-score over the OI z-score's window, both taken on the OI grid, never at the union's
    closes (docs/specs/00141 D4)."""

    def zscore(levels: list[float | None]) -> list[float | None]:
        return funding_zscore(oi_momentum(levels, lookback=_OI_MOMENTUM_LOOKBACK), window=_OI_ZSCORE_WINDOW)

    return _oi_at_union_closes("momentum z-score", zscore, oi_ts, oi_values, union_ts)
```

  and after `event_contrast_chunked` and before `_check_lengths`:

```python
class BootstrapBlocks(NamedTuple):
    """A stationary-bootstrap draw held as its blocks: resample r's blocks run from `firsts[r]` to the next resample's
    first, and block b covers `lengths[b]` consecutive indices from `starts[b]`, mod `n_obs`."""

    n_obs: int
    starts: np.ndarray
    lengths: np.ndarray
    firsts: np.ndarray


def stationary_bootstrap_blocks(n_obs: int, *, mean_block: float, n_resamples: int, seed: int) -> BootstrapBlocks:
    """`stationary_bootstrap_indices`' resamples, each as its blocks: its generator's calls in its order, a fresh start
    opening a block and a step to the next index lengthening it (docs/specs/00141 D6)."""
    # `stationary_bootstrap_indices`' own refusals, `event_contrast_chunked`'s two calls.
    stationary_bootstrap_indices(n_obs, mean_block=1, n_resamples=1, seed=seed)
    stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=n_resamples, seed=seed)
    rng = random.Random(seed)
    uniform, fresh = rng.random, rng.randrange
    p = 1 / mean_block
    starts, opens, firsts = array("i"), array("i"), array("i")
    for _ in range(n_resamples):
        firsts.append(len(starts))
        starts.append(fresh(n_obs))
        opens.append(0)
        for j in range(1, n_obs):
            if uniform() < p:
                starts.append(fresh(n_obs))
                opens.append(j)
    opened, first = np.frombuffer(opens, dtype=np.intc), np.frombuffer(firsts, dtype=np.intc)
    lengths = np.empty_like(opened)
    lengths[:-1] = opened[1:]
    lengths[first[1:] - 1] = lengths[-1] = n_obs
    lengths -= opened
    return BootstrapBlocks(n_obs, np.frombuffer(starts, dtype=np.intc), lengths, first)


def event_contrast_blocks(
    flags: dict[str, list[bool | None]],
    forwards: dict[str, dict[str, list[float | None]]],
    blocks: BootstrapBlocks,
    *,
    far: tuple[float, float],
) -> dict[str, dict[str, list[float]]]:
    """`event_contrast_chunked`'s rows over `blocks`' resamples, the far bounds at the percentiles `far`: a resample's
    counts and sums are read off running totals at its blocks' ends, so it costs its blocks, never its indices; its counts
    are the gathered ones exactly and its sums theirs to rounding (docs/specs/00141 D6)."""
    n = _check_lengths({f"flags[{asset!r}]": values for asset, values in flags.items()})
    for series, by_asset in forwards.items():
        _check_paired("flags", flags, f"forwards[{series!r}]", by_asset, n)
    if blocks.n_obs != n:
        raise AlphaError(f"blocks draw over {blocks.n_obs} indices and the flags hold {n}")
    numbers = isinstance(far, tuple) and len(far) == 2 and all(type(q) in (int, float) for q in far)
    if not numbers or not 0 <= far[0] < far[1] <= 100:
        raise AlphaError(f"far must be two percentiles, 0 <= low < high <= 100, got {far!r}")
    kept = {}
    for series, by_asset in forwards.items():
        for asset, flag in flags.items():
            values = by_asset[asset]
            event = np.array([f is True and v is not None for f, v in zip(flag, values)])
            other = np.array([f is False and v is not None for f, v in zip(flag, values)])
            if event.sum() >= 2 and other.sum() >= 2:
                kept[series, asset] = (event, other, np.array([0.0 if v is None else v for v in values]))
    column = {key: 4 * j for j, key in enumerate(kept)}
    n_resamples = len(blocks.firsts)
    totals = np.zeros((n_resamples, 4 * len(kept)))
    if kept:
        running = np.zeros((n + 1, 4 * len(kept)))
        for key, (event, other, x) in kept.items():
            running[1:, column[key] : column[key] + 4] = np.column_stack((event, other, x * event, x * other))
        np.cumsum(running, axis=0, out=running)
        bounds = np.append(blocks.firsts, len(blocks.starts))
        for r in range(n_resamples):
            starts = blocks.starts[bounds[r] : bounds[r + 1]]
            ends = starts + blocks.lengths[bounds[r] : bounds[r + 1]]
            sums = running[np.minimum(ends, n)] - running[starts]
            wrapped = ends > n
            sums[wrapped] += running[ends[wrapped] - n]
            totals[r] = sums.sum(axis=0)
    out: dict[str, dict[str, list[float]]] = {}
    for series in forwards:
        assets = [asset for asset in flags if (series, asset) in kept]
        rows = {}
        for name, members in [*((asset, [asset]) for asset in assets), ("pooled", assets)]:
            if not members:
                continue
            read = [kept[series, asset] for asset in members]
            n_event = sum(int(event.sum()) for event, _, _ in read)
            n_other = sum(int(other.sum()) for _, other, _ in read)
            mean_event = sum(float(x[event].sum()) for event, _, x in read) / n_event
            mean_other = sum(float(x[other].sum()) for _, other, x in read) / n_other
            at = [column[series, asset] for asset in members]
            boot_events = sum(totals[:, j] for j in at)
            boot_others = sum(totals[:, j + 1] for j in at)
            usable = (boot_events > 0) & (boot_others > 0)
            if not usable.any():
                continue
            boot_event_means = sum(totals[:, j + 2] for j in at)[usable] / boot_events[usable]
            boot_other_means = sum(totals[:, j + 3] for j in at)[usable] / boot_others[usable]
            low, high = np.percentile(boot_event_means - boot_other_means, [2.5, 97.5])
            far_low, far_high = np.percentile(boot_event_means - boot_other_means, list(far))
            diff = mean_event - mean_other
            rows[name] = [n_event, n_other, mean_event, mean_other, diff, float(low), float(high), float(far_low), float(far_high)]
        out[series] = rows
    return out
```

- [ ] **Step 4: Run them to verify they pass** — `mkdir -p .tmp/plan-00141 && uv run pytest tests/test_alpha_b2.py -k "zscore_is_taken or block_draw or block_contrast" -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt` (measured `18 passed, 160 deselected`), then the whole file (measured `178 passed`).
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b2.py tests/test_alpha_b2.py`; the Global Constraints' `T` over the two paths in its three parts (the rest of `T`, the other seven direct readers, measured `220 passed, 11 deselected in 2.79s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`:

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_zscore_grid_feature(/def oi_log_delta_zscore_grid_feature_gone(/' --mutation 's/return funding_zscore(oi_log_delta(levels), window=_OI_ZSCORE_WINDOW)/return funding_zscore(oi_log_delta(levels), window=_OI_ZSCORE_WINDOW + 1)/' -- uv run pytest tests/test_alpha_b2.py::test_the_oi_log_delta_zscore_is_taken_over_180_grid_log_deltas_and_reads_warm_at_a_late_union -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_zscore_grid_feature(/def oi_log_delta_zscore_grid_feature_gone(/' --mutation 's/return funding_zscore(oi_log_delta(levels), /return funding_zscore(levels, /' -- uv run pytest tests/test_alpha_b2.py::test_the_oi_log_delta_zscore_is_taken_over_180_grid_log_deltas_and_reads_warm_at_a_late_union -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_zscore_grid_feature(/def oi_log_delta_zscore_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("log-delta z-score", zscore, oi_ts, oi_values, union_ts)/return funding_zscore(oi_log_delta_grid_feature(oi_ts, oi_values, union_ts), window=_OI_ZSCORE_WINDOW)/' -- uv run pytest tests/test_alpha_b2.py::test_the_oi_log_delta_zscore_is_taken_over_180_grid_log_deltas_and_reads_warm_at_a_late_union -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_zscore_grid_feature(/def oi_momentum_zscore_grid_feature_gone(/' --mutation 's/lookback=_OI_MOMENTUM_LOOKBACK), window=_OI_ZSCORE_WINDOW)/lookback=_OI_MOMENTUM_LOOKBACK - 1), window=_OI_ZSCORE_WINDOW)/' -- uv run pytest tests/test_alpha_b2.py::test_the_oi_momentum_zscore_is_taken_over_180_grid_momenta_and_reads_warm_at_a_late_union -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_zscore_grid_feature(/def oi_momentum_zscore_grid_feature_gone(/' --mutation 's/lookback=_OI_MOMENTUM_LOOKBACK), window=_OI_ZSCORE_WINDOW)/lookback=_OI_MOMENTUM_LOOKBACK), window=_OI_ZSCORE_WINDOW + 1)/' -- uv run pytest tests/test_alpha_b2.py::test_the_oi_momentum_zscore_is_taken_over_180_grid_momenta_and_reads_warm_at_a_late_union -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_zscore_grid_feature(/def oi_momentum_zscore_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("momentum z-score", zscore, oi_ts, oi_values, union_ts)/return funding_zscore(oi_momentum_grid_feature(oi_ts, oi_values, union_ts), window=_OI_ZSCORE_WINDOW)/' -- uv run pytest tests/test_alpha_b2.py::test_the_oi_momentum_zscore_is_taken_over_180_grid_momenta_and_reads_warm_at_a_late_union -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation '/^def stationary_bootstrap_blocks(/,/^def /s/^    p = 1 \/ mean_block$/    p = 1 \/ (mean_block + 1)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks[short-blocks]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation 's/^        for j in range(1, n_obs):$/        for j in range(2, n_obs):/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks[short-blocks]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation 's/^                opens.append(j)$/                opens.append(j - 1)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks[short-blocks]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation 's/^    lengths\[first\[1:\] - 1\] = lengths\[-1\] = n_obs$/    lengths[first[1:]] = lengths[-1] = n_obs/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks[long-blocks-wrapping]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation 's/^    lengths\[first\[1:\] - 1\] = lengths\[-1\] = n_obs$/    lengths[first[1:] - 1] = lengths[-1] = n_obs - 1/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks[one-index]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation 's/np.frombuffer(starts, dtype=np.intc), lengths, first)/np.frombuffer(starts, dtype=np.intc).astype(np.int64), lengths, first)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks[every-index-fresh]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation 's/stationary_bootstrap_indices(n_obs, mean_block=1, n_resamples=1, seed=seed)/stationary_bootstrap_indices(n_obs + 1, mean_block=1, n_resamples=1, seed=seed)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_refuses_what_the_stationary_bootstrap_refuses[no-index]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation '/^def stationary_bootstrap_blocks(/,/^def /s/stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=n_resamples, seed=seed)/stationary_bootstrap_indices(1, mean_block=1, n_resamples=n_resamples, seed=seed)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_refuses_what_the_stationary_bootstrap_refuses[block-under-1]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def stationary_bootstrap_blocks(/def stationary_bootstrap_blocks_gone(/' --mutation '/^def stationary_bootstrap_blocks(/,/^def /s/stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=n_resamples, seed=seed)/stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=1, seed=seed)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_draw_refuses_what_the_stationary_bootstrap_refuses[no-resample]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/sums = running\[np.minimum(ends, n)\] - running\[starts\]/sums = running[np.minimum(ends, n - 1)] - running[starts]/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/sums\[wrapped\] += running\[ends\[wrapped\] - n\]/sums[wrapped] += running[ends[wrapped] - n + 1]/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/starts = blocks.starts\[bounds\[r\] : bounds\[r + 1\]\]/starts = blocks.starts[bounds[r] + 1 : bounds[r + 1] + 1]/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/totals\[r\] = sums.sum(axis=0)/totals[r] = sums[1:].sum(axis=0)/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/np.column_stack((event, other, x \* event, x \* other))/np.column_stack((other, event, x * event, x * other))/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/np.column_stack((event, other, x \* event, x \* other))/np.column_stack((event, other, x * other, x * event))/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/running\[1:, column\[key\] : column\[key\] + 4\]/running[:-1, column[key] : column[key] + 4]/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/np.cumsum(running, axis=0, out=running)/np.cumsum(running, axis=1, out=running)/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/^    n_resamples = len(blocks.firsts)$/    n_resamples = len(blocks.firsts) - 1/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation '/^def event_contrast_blocks(/,/^def /s/            if event.sum() >= 2 and other.sum() >= 2:/            if event.sum() >= 1 and other.sum() >= 2:/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation '/^def event_contrast_blocks(/,/^def /s/            if event.sum() >= 2 and other.sum() >= 2:/            if event.sum() >= 2 and other.sum() >= 1:/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation '/^def event_contrast_blocks(/,/^def /s/            usable = (boot_events > 0) & (boot_others > 0)/            usable = (boot_events > 0) \& (boot_others >= 0)/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation '/^def event_contrast_blocks(/,/^def /s/            usable = (boot_events > 0) & (boot_others > 0)/            usable = (boot_events >= 0) \& (boot_others > 0)/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation '/^def event_contrast_blocks(/,/^def /s/            if not members:/            if members is None:/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/boot_event_means = sum(totals\[:, j + 2\] for j in at)/boot_event_means = sum(totals[:, j + 3] for j in at)/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/np.percentile(boot_event_means - boot_other_means, list(far))/np.percentile(boot_event_means - boot_other_means, [0.05, 99.95])/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation '/^def event_contrast_blocks(/,/^def /s/float(low), float(high), float(far_low), float(far_high)\]/low, high, far_low, far_high]/' -- uv run pytest tests/test_alpha_b2.py::test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/^    if blocks.n_obs != n:$/    if blocks.n_obs < n:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[another-draw]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/numbers = isinstance(far, tuple) and/numbers = isinstance(far, (tuple, list)) and/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[far-a-list]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/ and len(far) == 2 and / and len(far) >= 2 and /' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[far-three]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/all(type(q) in (int, float) for q in far)/all(isinstance(q, (int, float)) for q in far)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[far-a-bool]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/ not 0 <= far\[0\] < far\[1\] <= 100:/ not -1 <= far[0] < far[1] <= 100:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[far-below-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/ not 0 <= far\[0\] < far\[1\] <= 100:/ not 0 <= far[0] <= far[1] <= 100:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[far-not-rising]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation 's/ not 0 <= far\[0\] < far\[1\] <= 100:/ not 0 <= far[0] < far[1] <= 101:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[far-above-100]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_blocks(/def event_contrast_blocks_gone(/' --mutation '/^def event_contrast_blocks(/,/^def /s/_check_paired("flags", flags, f"forwards\[{series!r}\]", by_asset, n)/_check_paired("flags", flags, f"forwards[{series!r}]", flags, n)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward[forward-length]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D4 or D6 gives the new code. The OI pair: each z-score's window (the two `+ 1` window rows) and the momentum's lookback (the `- 1` row), the z-score taken of the log-delta and never of the level (the `funding_zscore(levels, ` row), and each taken on the OI grid, never at the union's closes (the two `oi_..._grid_feature(oi_ts, oi_values, union_ts)` rows, read by each test's late union). The draw: the fresh start's probability (the `mean_block + 1` row), each step's own draw (the `range(2, n_obs)` row), the block's opening position (the `j - 1` row), the resamples' boundaries (the `lengths[first[1:]]` row, the wrapping draw's several resamples), the last block's length (the `n_obs - 1` row, the one-index draw) and the four-byte entries (the `astype(np.int64)` row, the itemsize assertion alone); each refusal row its own call, the index count by the first `stationary_bootstrap_indices` call alone and the block and the resample count by the second alone. The contrast: the running totals read at each block's end (the `n - 1` row), a block wrapping past the last index (the `- n + 1` row), each resample's own blocks (the `bounds[r] + 1` row) and all of them (the `sums[1:]` row), events beside others and their sums beside each other (the two column-swap rows), the totals' leading zero row and their running axis (the `running[:-1, …]` and `axis=1` rows), every resample read (the `len(blocks.firsts) - 1` row), an asset kept per series on both counts (the two `>= 1` rows), a resample holding no event or no other skipped on either side (the two `>= 0` rows), a series keeping no asset left `{}` (the `is None` row), the sums column the means read (the `j + 3` row), the far percentiles it is given (the `[0.05, 99.95]` row, read at `(1, 99)`) and the builtin leaves (the `float()` row); each refusal row its own clause — the draw's index count, `far`'s type, its length, its numbers' type, its low bound at 0, its rising order and its high bound at 100 — and the forwards' lengths. The comparison `ends > n` carries no row: a block ending exactly at the last index adds the running total's zero row either way, so no one-line change of it moves a sum.

- [ ] **Step 7: Commit** — `feat(alpha): the OI change's and momentum's z-scores on the OI grid, the stationary-bootstrap draw held as its blocks, and the block contrast at the far percentiles it is given`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the reading subject in `cli/research/subjects.py` (D2–D7)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 1's `oi_log_delta_zscore_grid_feature`, `oi_momentum_zscore_grid_feature`, `stationary_bootstrap_blocks` and `event_contrast_blocks`; `cli/research/subjects.py`'s `_b2_overlay_inputs`, `_B2OverlayInputs`, `_B2ReadingInputs`, `_b2_reading_flags`, `_b2_reading_counts`, `_b2_reading_forwards`, `_B2_READING_THRESHOLD`, `_B2_READING_TAILS`, `_B2_READING_STATES`, `_B2_READING_HORIZONS`, `_B2_READING_BLOCK`, `_B2_RATIO_COLUMNS`, `_B2_LIQ_SET`, `_b2_over`, `_ASSETS`, `SubjectError`, `Subject` and the names it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_anchor`, `_rolling_set`, `_not_parquet`, `_b2_overlay_dataset`, `_B2_START`, `_B2_ASSETS`, `_B2_SPOILT`, `_B2_OVERLAY_RATIOS` and `_CONTRACT_DATASETS`. Produces the subject and `_b2_reading_2_inputs`, which Task 3's data-gated test reads.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - the `from cli.alpha.b2 import (` block gains `oi_log_delta_zscore_grid_feature,` and `oi_momentum_zscore_grid_feature,` before `oi_zscore_grid_feature,`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, as its last line, `    assert subjects.SUBJECTS["b2-second-signal-reading"].metric_keys == _B2_READING_2_SPEC_KEYS`;
  - after `test_the_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it` and before `def _ruled_signal(`:

```python
_B2_READING_2_SPEC = "docs/specs/00141-b2-signal-reading-2-design.md"
# Spec 00141's eight signals, in the order its keys and its contrasts take them, typed from the spec, never read off the
# subject.
_B2_READING_2_SIGNAL_KEYS = (
    "binperp_oi_log_delta_z30d",
    "binperp_oi_momentum_z30d",
    "binperp_count_toptrader_long_short_ratio_z30d",
    "binperp_sum_toptrader_long_short_ratio_z30d",
    "binperp_count_long_short_ratio_z30d",
    "binperp_sum_taker_long_short_vol_ratio_z30d",
    "binperp_liq_short_z30d",
    "binperp_liq_total_z30d",
)
_B2_READING_2_SPEC_KEYS = frozenset(
    {
        *(
            f"{key}_fwd_{kind}_{hours}h"
            for key in _B2_READING_2_SIGNAL_KEYS
            for kind in ("logret", "sumret")
            for hours in (4, 24, 96)
        ),
        "events_per_asset",
        "others_per_asset",
        "threshold",
        "mean_block",
        "n_resamples",
        "far_percentiles",
    }
)


def test_the_second_signal_reading_declares_the_4h_grid_its_keys_and_no_rule():
    reading = subjects.SUBJECTS["b2-second-signal-reading"]
    assert (reading.name, reading.intervals, reading.assets, reading.spec, reading.seeds) == (
        "b2-second-signal-reading",
        (240,),
        _B2_ASSETS,
        _B2_READING_2_SPEC,
        (42,),
    )
    assert reading.build is subjects._build_b2_second_signal_reading and reading.metric_keys == _B2_READING_2_SPEC_KEYS
    assert (reading.verdict, reading.no_verdict, reading.incumbent, reading.family, reading.n_trials) == (None,) * 5


def test_the_second_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_untested_signal_by_its_reader(monkeypatch):
    calls = []
    overlay = subjects._B2OverlayInputs(["ts"], {"BTC": [1.0]}, ["close"], {"BTC": [0.0]}, {"BTC": [-3.0]}, {"BTC": [0.5]}, 2.0)
    monkeypatch.setattr(subjects, "_b2_overlay_inputs", lambda *arguments: calls.append(arguments) or overlay)
    ratios = {key: f"ratio {key}" for key in _B2_READING_2_SIGNAL_KEYS[2:6]}
    sides = {key: f"side {key}" for key in _B2_READING_2_SIGNAL_KEYS[6:]}
    readers = {"_b2_oi_momentum_signal": "momentum", "_b2_ratio_signals": ratios, "_b2_liq_side_signals": sides}
    for name, out in readers.items():
        monkeypatch.setattr(subjects, name, lambda reader, h4_ts, name=name, out=out: calls.append((name, reader, h4_ts)) or out)
    reader, window = object(), ("2024-01-01", "2024-06-30")

    inputs = subjects._b2_reading_2_inputs("b2-second-signal-reading", reader, "ohlc-test", window, True)

    assert calls == [
        ("b2-second-signal-reading", subjects._b2_oi_log_delta_signal, 2.0, reader, "ohlc-test", window, True),
        *((name, reader, ["ts"]) for name in readers),
    ]
    signals = dict(zip(_B2_READING_2_SIGNAL_KEYS[:2], (overlay.signal, "momentum"))) | ratios | sides
    assert inputs == subjects._B2ReadingInputs(overlay.h4_ts, overlay.h4_prices, overlay.close, overlay.arm_a, signals)
    assert list(inputs.signals) == list(_B2_READING_2_SIGNAL_KEYS)


def _untested_signals(root: Path, h4_ts: list[datetime], reader: str) -> dict:
    """`reader`'s signals off the fixture's files by the grid features, each keyed by its signal and asset."""
    expected: dict[str, dict] = {}
    for asset in _B2_ASSETS:
        oi = pl.read_parquet(root / "derivatives-oi" / PERP_SYMBOLS[asset] / "oi.parquet")
        daily = pl.read_parquet(root / "liquidations-daily" / asset / "daily.parquet")
        marks, levels = oi["ts"].to_list(), oi["sum_open_interest"].to_list()
        days, longs, shorts = daily["ts"].to_list(), daily["long_usd"].to_list(), daily["short_usd"].to_list()
        if reader == "oi-log-delta":
            columns = {_B2_READING_2_SIGNAL_KEYS[0]: oi_log_delta_zscore_grid_feature(marks, levels, h4_ts)}
        elif reader == "oi-momentum":
            columns = {_B2_READING_2_SIGNAL_KEYS[1]: oi_momentum_zscore_grid_feature(marks, levels, h4_ts)}
        elif reader == "ratios":
            columns = ratio_zscore_grid_features(marks, {column: oi[column].to_list() for column in _B2_OVERLAY_RATIOS}, h4_ts)
        else:
            columns = {
                _B2_READING_2_SIGNAL_KEYS[6]: daily_zscore_grid_feature(days, shorts, h4_ts),
                _B2_READING_2_SIGNAL_KEYS[7]: daily_zscore_grid_feature(days, [a + b for a, b in zip(longs, shorts)], h4_ts),
            }
        for key, values in columns.items():
            expected.setdefault(key, {})[asset] = values
    return expected


_UNTESTED_READERS = {
    "oi-log-delta": lambda reader, h4_ts: {_B2_READING_2_SIGNAL_KEYS[0]: subjects._b2_oi_log_delta_signal(reader, h4_ts)},
    "oi-momentum": lambda reader, h4_ts: {_B2_READING_2_SIGNAL_KEYS[1]: subjects._b2_oi_momentum_signal(reader, h4_ts)},
    "ratios": lambda reader, h4_ts: subjects._b2_ratio_signals(reader, h4_ts),
    "liquidation-sides": lambda reader, h4_ts: subjects._b2_liq_side_signals(reader, h4_ts),
}


@pytest.mark.parametrize("reader", sorted(_UNTESTED_READERS))
def test_each_untested_signal_reader_reads_its_signals_off_their_own_columns(tmp_path, reader):
    root = _b2_overlay_dataset(tmp_path)
    h4_ts, _ = subjects._capturing_union(ObservedReader(root), "ohlc-test", 240, None, None, False)

    signals = _UNTESTED_READERS[reader](ObservedReader(root), h4_ts)

    assert signals == _untested_signals(root, h4_ts, reader)
    assert all(any(v is not None for v in by_asset["BTC"]) for by_asset in signals.values())


def test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows(monkeypatch):
    # Thirty closes on every asset, arm A long at the even indices, each signal read from its own index and swinging
    # through both tails.
    prices = {a: [100.0 * (1 + 0.01 * i) * 1.003**k for k in range(30)] for i, a in enumerate(_B2_ASSETS)}
    arm_a = {a: [0.1 if k % 2 == 0 else 0.0 for k in range(29)] for a in _B2_ASSETS}
    signals = {
        key: {a: [None if k < j else 3.0 * math.sin(k + i + j) for k in range(29)] for i, a in enumerate(_B2_ASSETS)}
        for j, key in enumerate(_B2_READING_2_SIGNAL_KEYS)
    }
    inputs = subjects._B2ReadingInputs([], prices, ["close"] * 29, arm_a, signals)
    draws, calls = [], []
    monkeypatch.setattr(subjects, "stationary_bootstrap_blocks", lambda n_obs, **kwargs: draws.append((n_obs, kwargs)) or "draw")

    def contrast(flags, forwards, blocks, **kwargs):
        calls.append((flags, forwards, blocks, kwargs))
        return {series: {"pooled": [len(calls), index]} for index, series in enumerate(forwards)}

    monkeypatch.setattr(subjects, "event_contrast_blocks", contrast)

    metrics = subjects._b2_reading_2_metrics(inputs)

    assert draws == [(29, {"mean_block": 102, "n_resamples": 40_000, "seed": 42})]
    forwards = subjects._b2_reading_forwards(inputs.h4_prices)
    cells = [(key, tail, state) for key in _B2_READING_2_SIGNAL_KEYS for tail in ("above", "below") for state in ("long", "flat")]
    far = (2.5 / 96, 100 - 2.5 / 96)
    assert calls == [
        (subjects._b2_reading_flags(inputs.signals[key], inputs.arm_a, tail, state), forwards, "draw", {"far": far})
        for key, tail, state in cells
    ]
    for call, (key, tail, state) in enumerate(cells, start=1):
        for index, series in enumerate(f"fwd_{kind}_{hours}h" for kind in ("logret", "sumret") for hours in (4, 24, 96)):
            assert metrics[f"{key}_{series}"][tail][state] == {"pooled": [call, index]}
    assert set(metrics) == _B2_READING_2_SPEC_KEYS
    assert (metrics["threshold"], metrics["mean_block"], metrics["n_resamples"]) == (2.0, 102, 40_000)
    assert metrics["far_percentiles"] == list(far)
    counts = subjects._b2_reading_counts(inputs)
    assert (metrics["events_per_asset"], metrics["others_per_asset"]) == (counts["events_per_asset"], counts["others_per_asset"])


def test_the_second_signal_reading_refuses_as_of_before_any_read(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the reading read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", "b2-second-signal-reading", "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, args)

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        "b2-second-signal-reading evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass "
        "a frozen --dataset"
    ) in result.output


@pytest.mark.parametrize(
    ("relpath", "spoil", "cause"),
    [
        pytest.param(f"derivatives-oi/{_B2_SPOILT}/oi.parquet", _not_parquet, "File out of specification", id="oi"),
        pytest.param(
            f"derivatives-oi/{_B2_SPOILT}/oi.parquet",
            lambda path: pl.read_parquet(path).drop("sum_taker_long_short_vol_ratio").write_parquet(path),
            '"sum_taker_long_short_vol_ratio" not found',
            id="ratio",
        ),
        pytest.param(
            "liquidations-daily/SOL/daily.parquet",
            lambda path: pl.read_parquet(path).drop("short_usd").write_parquet(path),
            '"short_usd" not found',
            id="liquidation-short",
        ),
        pytest.param(
            "liquidations-daily/BTC/daily.parquet",
            lambda path: pl.read_parquet(path).drop("long_usd").write_parquet(path),
            '"long_usd" not found',
            id="liquidation-long",
        ),
    ],
)
def test_the_second_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it(
    tmp_path, monkeypatch, relpath, spoil, cause
):
    root = _b2_overlay_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-second-signal-reading", "--dataset", "ohlc-test"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output
```

  - `_CONTRACT_DATASETS` gains, after its `"b2-signal-reading"` entry, `    "b2-second-signal-reading": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),` — `_b2_overlay_dataset` holds the two sets the reading reads beside `ohlc-test`.

  **Author's call** — the inputs and wiring tests run `_b2_reading_2_inputs` and `_b2_reading_2_metrics` under stand-ins for `_b2_overlay_inputs`, the three later readers, the draw and the contrast, reading the cells' order, arguments and keys off sentinels, since the real build over the fixture takes about 30 s (the evaluate row) and would make each a slow case no probe reaches; each reader's own columns are proven by the readers test, its four rows the real readers over the fixture against the grid features over the same files, and the file-refusal and contract rows run the real readers through the subject. Reading 3's flags, counts and forwards are its own retired cases', unchanged and run nightly by `infra/scripts/data-gated-run.py`; the wiring test reads each as its oracle. The reading's instrument — its eight readers, threshold, tails, states, horizons, two forward families, block, resamples, far percentiles and seed — is written in this plan's code in three places: the subject's constants and calls (with step 8's probe rows that match them); the tests' literals (`_B2_READING_2_SIGNAL_KEYS`, `_B2_READING_2_SPEC_KEYS`, the readers' oracle, the wiring test's arguments and series); and the check programs (Task 4 step 5) — `reading_check.py`'s `constants`, its `cells`' tails, states and hours and its two families' keys, and `pooled_rows.py`'s signal keys, tails, states, hours and families — Task 3's data-gated counts holding the inputs half to the measured basis. It is written in words in five more, which a read against D3–D8 alone checks: the Global Constraints' first three items, the README row (step 4), the pick's option 2 and the conventions entry (Task 3 step 5) and the run's notes (Task 5 step 2).

- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00141 && uv run pytest tests/test_research_command.py -k "second_signal_reading or untested_signal or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt`: collection completes and every selected case fails at its call, on a name `subjects` lacks — `_b2_reading_2_inputs`, `_b2_oi_log_delta_signal`, a key of `SUBJECTS` — or on a subject the CLI does not know (measured over Task 1's code: `13 failed, 696 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — the `from cli.alpha.b2 import (` block gains `event_contrast_blocks,` after `event_contrast,`, `oi_log_delta_zscore_grid_feature,` and `oi_momentum_zscore_grid_feature,` before `oi_zscore_grid_feature,`, and `stationary_bootstrap_blocks,` after `scale_positions,`; after `_B2_READING_KEYS` and before `SUBJECTS: dict[str, Subject] = {`:

```python
# docs/specs/00141 D2-D7: B2's second signal reading, the eight crowding signals no trial read, by reading 3's tails, states
# and forwards; no rule, no slot.
_B2_READING_2_SIGNALS = (
    "binperp_oi_log_delta_z30d",
    "binperp_oi_momentum_z30d",
    "binperp_count_toptrader_long_short_ratio_z30d",
    "binperp_sum_toptrader_long_short_ratio_z30d",
    "binperp_count_long_short_ratio_z30d",
    "binperp_sum_taker_long_short_vol_ratio_z30d",
    "binperp_liq_short_z30d",
    "binperp_liq_total_z30d",
)
_B2_READING_2_RESAMPLES = 40_000
# Bonferroni at 5 % two-sided over the 96 pooled cells: 8 signals, 2 tails, 2 states, 3 horizons.
_B2_READING_2_FAR = (2.5 / 96, 100 - 2.5 / 96)


def _b2_oi_log_delta_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    signal = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/oi.parquet"
        try:
            rows = reader.read_series("derivatives-oi", relpath)
            signal[asset] = oi_log_delta_zscore_grid_feature(rows["ts"].to_list(), rows["sum_open_interest"].to_list(), h4_ts)
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-oi/{relpath}: {exc}") from exc
    return signal


def _b2_oi_momentum_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    signal = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/oi.parquet"
        try:
            rows = reader.read_series("derivatives-oi", relpath)
            signal[asset] = oi_momentum_zscore_grid_feature(rows["ts"].to_list(), rows["sum_open_interest"].to_list(), h4_ts)
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-oi/{relpath}: {exc}") from exc
    return signal


def _b2_ratio_signals(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, dict[str, list[float | None]]]:
    """Trial 4's four ratio z-scores, each a signal of its own under its z-score's name (docs/specs/00141 D4)."""
    signals: dict[str, dict[str, list[float | None]]] = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/oi.parquet"
        try:
            rows = reader.read_series("derivatives-oi", relpath)
            ratios = {column: rows[column].to_list() for column in _B2_RATIO_COLUMNS}
            for key, values in ratio_zscore_grid_features(rows["ts"].to_list(), ratios, h4_ts).items():
                signals.setdefault(key, {})[asset] = values
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-oi/{relpath}: {exc}") from exc
    return signals


def _b2_liq_side_signals(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, dict[str, list[float | None]]]:
    """The short side's daily notional and the day's total, each z-scored as trial 5's long side is (docs/specs/00141
    D4)."""
    signals: dict[str, dict[str, list[float | None]]] = {"binperp_liq_short_z30d": {}, "binperp_liq_total_z30d": {}}
    for asset in _ASSETS:
        relpath = f"{asset}/daily.parquet"
        try:
            rows = reader.read_series(_B2_LIQ_SET, relpath)
            days, longs, shorts = rows["ts"].to_list(), rows["long_usd"].to_list(), rows["short_usd"].to_list()
            totals = [a + b for a, b in zip(longs, shorts)]
            signals["binperp_liq_short_z30d"][asset] = daily_zscore_grid_feature(days, shorts, h4_ts)
            signals["binperp_liq_total_z30d"][asset] = daily_zscore_grid_feature(days, totals, h4_ts)
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"{_B2_LIQ_SET}/{relpath}: {exc}") from exc
    return signals


def _b2_reading_2_inputs(
    subject: str, reader: ObservedReader, dataset: str, window: tuple[str, str] | None, accept_holes: bool
) -> _B2ReadingInputs:
    """Reading 3's inputs on the eight signals, the first handed to `_b2_overlay_inputs` for its arm A: never a forward
    return, so the basis test reads the data before the spec's hash (docs/specs/00141 D3, D4, D7)."""
    overlay = _b2_overlay_inputs(subject, _b2_oi_log_delta_signal, _B2_READING_THRESHOLD, reader, dataset, window, accept_holes)
    signals = {
        "binperp_oi_log_delta_z30d": overlay.signal,
        "binperp_oi_momentum_z30d": _b2_oi_momentum_signal(reader, overlay.h4_ts),
        **_b2_ratio_signals(reader, overlay.h4_ts),
        **_b2_liq_side_signals(reader, overlay.h4_ts),
    }
    return _B2ReadingInputs(overlay.h4_ts, overlay.h4_prices, overlay.close, overlay.arm_a, signals)


def _b2_reading_2_metrics(inputs: _B2ReadingInputs) -> dict:
    forwards = _b2_reading_forwards(inputs.h4_prices)
    blocks = stationary_bootstrap_blocks(
        len(inputs.close), mean_block=_B2_READING_BLOCK, n_resamples=_B2_READING_2_RESAMPLES, seed=42
    )
    contrast: dict[str, dict] = {}
    for key, signal in inputs.signals.items():
        for tail in _B2_READING_TAILS:
            for state in _B2_READING_STATES:
                flags = _b2_reading_flags(signal, inputs.arm_a, tail, state)
                rows = event_contrast_blocks(flags, forwards, blocks, far=_B2_READING_2_FAR)
                for series, by_name in rows.items():
                    contrast.setdefault(f"{key}_{series}", {}).setdefault(tail, {})[state] = by_name
    return {
        **contrast,
        **_b2_reading_counts(inputs),
        "threshold": _B2_READING_THRESHOLD,
        "mean_block": _B2_READING_BLOCK,
        "n_resamples": _B2_READING_2_RESAMPLES,
        "far_percentiles": list(_B2_READING_2_FAR),
    }


def _build_b2_second_signal_reading(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    subject = "b2-second-signal-reading"
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
            "frozen --dataset"
        )
    try:
        return _b2_reading_2_metrics(_b2_reading_2_inputs(subject, reader, dataset, window, accept_holes))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


# docs/specs/00141 D7's keys of the reading.
_B2_READING_2_KEYS = frozenset(
    {
        *(
            f"{key}_fwd_{kind}_{4 * horizon}h"
            for key in _B2_READING_2_SIGNALS
            for kind in ("logret", "sumret")
            for horizon in _B2_READING_HORIZONS
        ),
        "events_per_asset",
        "others_per_asset",
        "threshold",
        "mean_block",
        "n_resamples",
        "far_percentiles",
    }
)
```

  and `SUBJECTS` gains, after its `"b2-signal-reading"` entry:

```python
    "b2-second-signal-reading": Subject(
        "b2-second-signal-reading",
        (240,),
        _ASSETS,
        _build_b2_second_signal_reading,
        spec="docs/specs/00141-b2-signal-reading-2-design.md",
        metric_keys=_B2_READING_2_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` `--reading`) or `b2-signal-reading` ( `` becomes `` `--reading`), `b2-signal-reading` ( ``, and the row's closing `` `--reading`). | `` becomes:

```markdown
`--reading`) or `b2-second-signal-reading` (the same reading over the eight crowding signals no B2 comparison read — the open-interest log-change and 30-day momentum z-scores, each of the four long/short-ratio z-scores singly, and the daily short-side and total liquidation z-scores — its far bounds at the Bonferroni percentiles over its 96 cells, from 40,000 resamples; the 4h series of `--dataset`, a frozen set only, and the `derivatives-oi` and `liquidations-daily` sets read whole; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the cases measured at 10 s or more on the authoring tree (setup counted with the call; the evaluate and shared-default rows are the existing tests' new rows): the readers test's `ratios` row 18.9 s, the file refusal's `ratio` row 18.3 s, `liquidation-long` row 19.8 s and `liquidation-short` row 20.0 s, the evaluate row 29.9 s and the shared-default row 59.1 s:

```text
tests/test_research_command.py::test_each_untested_signal_reader_reads_its_signals_off_their_own_columns[ratios]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-second-signal-reading-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-second-signal-reading]
tests/test_research_command.py::test_the_second_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[liquidation-long]
tests/test_research_command.py::test_the_second_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[liquidation-short]
tests/test_research_command.py::test_the_second_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[ratio]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, one plain blocking call, `timeout` 600000 ms (measured `13 passed, 705 deselected in 91.50s`); then the subject's two slow fixture rows, the cases that run its build end to end, which step 2's `-k` does not select (their names carry `b2-second-signal-reading`, hyphenated) and every commit gate's `-m "not slow and not data"` deselects, each reading the test fixture alone (`_anchor`): `mkdir -p .tmp/plan-00141 && ZCRYPTO_RERUN_SLOW=1 uv run pytest 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-second-signal-reading-evaluates]' 'tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-second-signal-reading]' -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt`, one plain blocking call, `timeout` 600000 ms (measured `2 passed in 89.18s`).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' `T` over the four paths in its three parts (the rest of `T`, the other thirty-three direct readers, measured `4114 passed, 56 deselected in 121.34s`); `uv run pre-commit run -a` until clean; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`; the metric-keys line, the contract, shared-default and tracked-spec rows are new rows of existing tests, not new guards, and are not probed; the slow cases each recorded `probe skipped: slow case`:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_second_signal_reading(/def _build_b2_second_signal_reading_gone(/' --mutation '/^    "b2-second-signal-reading": Subject(/,/^    ),$/s/        seeds=(42,),/        seeds=(42, 7),/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_second_signal_reading(/def _build_b2_second_signal_reading_gone(/' --mutation '/^    "b2-second-signal-reading": Subject(/,/^    ),$/s/        spec="docs\/specs\/00141-b2-signal-reading-2-design.md",/        spec="docs\/specs\/00140-b2-signal-reading-design.md",/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_second_signal_reading(/def _build_b2_second_signal_reading_gone(/' --mutation '/^_B2_READING_2_SIGNALS = ($/,/^)$/s/    "binperp_liq_total_z30d",/    "binperp_liq_sum_z30d",/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_second_signal_reading(/def _build_b2_second_signal_reading_gone(/' --mutation '/^_B2_READING_2_KEYS = frozenset($/,/^)$/s/        "far_percentiles",/        "far_percentile",/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_inputs(/def _b2_reading_2_inputs_gone(/' --mutation 's/    overlay = _b2_overlay_inputs(subject, _b2_oi_log_delta_signal, /    overlay = _b2_overlay_inputs(subject, _b2_oi_momentum_signal, /' -- uv run pytest tests/test_research_command.py::test_the_second_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_untested_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_inputs(/def _b2_reading_2_inputs_gone(/' --mutation 's/        "binperp_oi_momentum_z30d": _b2_oi_momentum_signal(reader, overlay.h4_ts),/        "binperp_oi_momentum_z30d": _b2_oi_log_delta_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_untested_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_inputs(/def _b2_reading_2_inputs_gone(/' --mutation 's/        \*\*_b2_ratio_signals(reader, overlay.h4_ts),/        **_b2_liq_side_signals(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_untested_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_inputs(/def _b2_reading_2_inputs_gone(/' --mutation '/^def _b2_reading_2_inputs(/,/^def /s/return _B2ReadingInputs(overlay.h4_ts, overlay.h4_prices, /return _B2ReadingInputs(overlay.h4_ts, overlay.scales, /' -- uv run pytest tests/test_research_command.py::test_the_second_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_untested_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_oi_log_delta_signal(/def _b2_oi_log_delta_signal_gone(/' --mutation 's/oi_log_delta_zscore_grid_feature(rows\["ts"\].to_list(), rows\["sum_open_interest"\].to_list(), h4_ts)/oi_log_delta_zscore_grid_feature(rows["ts"].to_list(), rows["sum_open_interest_value"].to_list(), h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_each_untested_signal_reader_reads_its_signals_off_their_own_columns[oi-log-delta]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_oi_momentum_signal(/def _b2_oi_momentum_signal_gone(/' --mutation 's/signal\[asset\] = oi_momentum_zscore_grid_feature(/signal[asset] = oi_log_delta_zscore_grid_feature(/' -- uv run pytest 'tests/test_research_command.py::test_each_untested_signal_reader_reads_its_signals_off_their_own_columns[oi-momentum]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_liq_side_signals(/def _b2_liq_side_signals_gone(/' --mutation 's/rows\["long_usd"\].to_list(), rows\["short_usd"\].to_list()$/rows["short_usd"].to_list(), rows["long_usd"].to_list()/' -- uv run pytest 'tests/test_research_command.py::test_each_untested_signal_reader_reads_its_signals_off_their_own_columns[liquidation-sides]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_liq_side_signals(/def _b2_liq_side_signals_gone(/' --mutation 's/totals = \[a + b for a, b in zip(longs, shorts)\]/totals = [a - b for a, b in zip(longs, shorts)]/' -- uv run pytest 'tests/test_research_command.py::test_each_untested_signal_reader_reads_its_signals_off_their_own_columns[liquidation-sides]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_liq_side_signals(/def _b2_liq_side_signals_gone(/' --mutation 's/= daily_zscore_grid_feature(days, shorts, h4_ts)/= daily_zscore_grid_feature(days, longs, h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_each_untested_signal_reader_reads_its_signals_off_their_own_columns[liquidation-sides]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/^_B2_READING_2_RESAMPLES = 40_000$/_B2_READING_2_RESAMPLES = 20_000/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/^_B2_READING_2_FAR = (2.5 \/ 96, 100 - 2.5 \/ 96)$/_B2_READING_2_FAR = (2.5 \/ 48, 100 - 2.5 \/ 48)/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/len(inputs.close), mean_block=_B2_READING_BLOCK, /len(inputs.close) - 1, mean_block=_B2_READING_BLOCK, /' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/len(inputs.close), mean_block=_B2_READING_BLOCK, /len(inputs.close), mean_block=30, /' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/n_resamples=_B2_READING_2_RESAMPLES, seed=42$/n_resamples=_B2_READING_2_RESAMPLES, seed=7/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation '/^def _b2_reading_2_metrics(/,/^def /s/                flags = _b2_reading_flags(signal, inputs.arm_a, tail, state)/                flags = _b2_reading_flags(signal, inputs.arm_a, tail, "long")/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/rows = event_contrast_blocks(flags, forwards, blocks, far=_B2_READING_2_FAR)/rows = event_contrast_blocks(flags, forwards, blocks, far=(0.05, 99.95))/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation '/^def _b2_reading_2_metrics(/,/^def /s/contrast.setdefault(f"{key}_{series}", {}).setdefault(tail, {})\[state\] = by_name/contrast.setdefault(f"{key}_{series}", {}).setdefault(state, {})[tail] = by_name/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/        "n_resamples": _B2_READING_2_RESAMPLES,/        "n_resamples": _N_RESAMPLES,/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_2_metrics(/def _b2_reading_2_metrics_gone(/' --mutation 's/        "far_percentiles": list(_B2_READING_2_FAR),/        "far_percentiles": [0.05, 99.95],/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_second_signal_reading(/def _build_b2_second_signal_reading_gone(/' --mutation '/^def _build_b2_second_signal_reading(/,/^def /s/    if as_of is not None:/    if as_of is None:/' -- uv run pytest tests/test_research_command.py::test_the_second_signal_reading_refuses_as_of_before_any_read -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_oi_log_delta_signal(/def _b2_oi_log_delta_signal_gone(/' --mutation '/^def _b2_oi_log_delta_signal(/,/^def /s/raise SubjectError(f"derivatives-oi\/{relpath}: {exc}") from exc/raise SubjectError(f"derivatives-oi {relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_the_second_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[oi]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  The readers test's `ratios` row and the file refusal's `ratio`, `liquidation-short` and `liquidation-long` rows are slow cases, recorded `probe skipped: slow case`: the ratio reader's columns are proven by that slow row alone, its wiring by the inputs test's rows. The file refusal's `oi` row has its own, the log-delta reader naming the file it cannot read. Each declaration row moves one value the spec fixes — the seeds, the spec, a signal key, a constant key; each inputs row one reader or field; each OI reader row its own column or grid feature; each liquidation-side row one clause of D4 — the short side read from its own column, the total the two sides' sum, the short z-score over the short side; each wiring row one argument of the draw or the contrast or one key the metrics carry.

- [ ] **Step 9: Commit** — `feat(research): B2's second signal reading — the eight untested crowding signals' forward returns by tail and by arm A's state on a frozen set's full history`, the message carrying the test result lines, each probe's command and verdict, each `probe skipped: slow case` and the two trailer lines.

## Task 3: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D8, D9)

**Files:** Create `tests/test_research_b2_second_signal_reading_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 2's `_b2_reading_2_inputs` and reading 3's `_b2_reading_counts`; `tests.skip_gates.nothing_found_under`. Produces one test and the module names `BLOCK`, `VOUCHED`, `EVENTS`, `OTHERS` and `per_asset()`, which Task 4's check program imports. No test computes a forward return.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis:

```python
"""B2's second signal reading's inputs against spec 00141's measured basis; no forward return."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
BLOCK = "bfbaff14b7aaa0d673fb0ab2012fc0d5c2d2118d258ad720e9ef6120c6ca8f6a"
VOUCHED = {
    "ohlc-full": "checked (36 vouched hashes)",
    "derivatives-oi": "checked (10 vouched hashes)",
    "liquidations-daily": "checked (10 vouched hashes)",
}
_RETURN_INDICES = 27_337
# Per signal, the first return index every asset's signal holds, and its close.
SIGNAL_FROM = {
    "binperp_oi_log_delta_z30d": (18_027, datetime(2021, 12, 31, tzinfo=UTC)),
    "binperp_oi_momentum_z30d": (18_206, datetime(2022, 1, 29, 20, tzinfo=UTC)),
    "binperp_count_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_sum_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_count_long_short_ratio_z30d": (18_324, datetime(2022, 2, 18, 12, tzinfo=UTC)),
    "binperp_sum_taker_long_short_vol_ratio_z30d": (18_994, datetime(2022, 6, 10, 4, tzinfo=UTC)),
    "binperp_liq_short_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
    "binperp_liq_total_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
}
# Arm A's long and flat asset-stamps, and below them each cell's events and others, per asset in `subjects._ASSETS`' order.
ARM_A_LONG = (8_938, 4_680, 17_169, 6_766, 6_640, 13_428, 7_954, 11_958, 6_024, 9_905)
ARM_A_FLAT = (18_399, 22_657, 10_168, 20_571, 20_697, 13_909, 19_383, 15_379, 21_313, 17_432)
EVENTS = {
    "binperp_oi_log_delta_z30d": {
        "above": {
            "long": (135, 149, 168, 170, 105, 129, 170, 147, 138, 125),
            "flat": (118, 116, 104, 90, 131, 97, 91, 83, 112, 78),
        },
        "below": {
            "long": (97, 101, 182, 95, 100, 107, 103, 82, 108, 95),
            "flat": (104, 82, 116, 83, 86, 112, 90, 85, 84, 99),
        },
    },
    "binperp_oi_momentum_z30d": {
        "above": {
            "long": (369, 316, 496, 620, 307, 280, 515, 441, 274, 456),
            "flat": (324, 347, 242, 347, 457, 307, 256, 197, 386, 284),
        },
        "below": {
            "long": (143, 97, 243, 63, 197, 152, 123, 94, 172, 135),
            "flat": (254, 243, 259, 238, 173, 310, 199, 209, 149, 271),
        },
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (289, 316, 398, 217, 286, 113, 271, 236, 194, 127),
            "flat": (73, 77, 297, 80, 60, 204, 52, 170, 94, 139),
        },
        "below": {
            "long": (96, 77, 127, 105, 66, 124, 130, 131, 249, 153),
            "flat": (93, 83, 30, 93, 81, 20, 132, 29, 62, 96),
        },
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (504, 503, 457, 525, 569, 362, 594, 516, 507, 517),
            "flat": (82, 99, 98, 63, 57, 147, 78, 120, 28, 87),
        },
        "below": {
            "long": (32, 30, 195, 27, 92, 107, 56, 63, 85, 23),
            "flat": (241, 149, 172, 206, 155, 213, 252, 221, 207, 191),
        },
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {
            "long": (272, 340, 420, 247, 240, 168, 252, 218, 244, 171),
            "flat": (127, 128, 359, 84, 177, 228, 119, 198, 135, 221),
        },
        "below": {
            "long": (206, 184, 101, 215, 166, 132, 232, 225, 203, 278),
            "flat": (134, 144, 23, 86, 125, 29, 192, 33, 120, 92),
        },
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {
            "long": (129, 152, 278, 158, 149, 177, 175, 201, 223, 155),
            "flat": (233, 167, 180, 175, 214, 170, 196, 152, 138, 194),
        },
        "below": {
            "long": (0, 6, 1, 2, 1, 1, 4, 0, 4, 1),
            "flat": (2, 3, 4, 0, 1, 3, 1, 0, 5, 2),
        },
    },
    "binperp_liq_short_z30d": {
        "above": {
            "long": (321, 341, 318, 348, 320, 275, 381, 366, 312, 281),
            "flat": (134, 139, 120, 138, 142, 187, 111, 102, 132, 109),
        },
        "below": {
            "long": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        },
    },
    "binperp_liq_total_z30d": {
        "above": {
            "long": (249, 259, 238, 383, 250, 220, 267, 267, 305, 285),
            "flat": (128, 154, 145, 162, 229, 194, 122, 152, 180, 141),
        },
        "below": {
            "long": (0, 0, 0, 0, 0, 6, 0, 0, 0, 0),
            "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        },
    },
}
OTHERS = {
    "binperp_oi_log_delta_z30d": {
        "above": {
            "long": (3_814, 4_063, 6_306, 4_376, 4_080, 4_359, 4_447, 4_431, 4_489, 3_943),
            "flat": (4_512, 4_437, 4_541, 4_129, 4_449, 3_999, 4_057, 3_904, 3_839, 4_438),
        },
        "below": {
            "long": (3_852, 4_111, 6_292, 4_451, 4_085, 4_381, 4_514, 4_496, 4_519, 3_973),
            "flat": (4_526, 4_471, 4_529, 4_136, 4_494, 3_984, 4_058, 3_902, 3_867, 4_417),
        },
    },
    "binperp_oi_momentum_z30d": {
        "above": {
            "long": (3_314, 3_691, 5_266, 3_482, 3_488, 3_841, 3_815, 3_790, 3_911, 3_390),
            "flat": (3_678, 3_696, 4_042, 3_601, 3_798, 3_262, 3_464, 3_243, 3_113, 3_560),
        },
        "below": {
            "long": (3_540, 3_910, 5_519, 4_039, 3_598, 3_969, 4_207, 4_137, 4_013, 3_711),
            "flat": (3_748, 3_800, 4_025, 3_710, 4_082, 3_259, 3_521, 3_231, 3_350, 3_573),
        },
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (2_796, 2_937, 5_104, 3_020, 2_943, 3_138, 3_162, 3_214, 3_470, 3_076),
            "flat": (3_161, 2_989, 3_075, 3_002, 3_030, 2_684, 2_834, 2_699, 2_561, 2_977),
        },
        "below": {
            "long": (2_989, 3_176, 5_375, 3_132, 3_163, 3_127, 3_303, 3_319, 3_415, 3_050),
            "flat": (3_141, 2_983, 3_342, 2_989, 3_009, 2_868, 2_754, 2_840, 2_593, 3_020),
        },
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (2_705, 2_884, 5_228, 2_925, 2_814, 3_254, 3_070, 3_162, 3_298, 2_823),
            "flat": (3_208, 3_013, 3_271, 2_986, 3_059, 2_736, 2_757, 2_701, 2_666, 3_072),
        },
        "below": {
            "long": (3_177, 3_357, 5_490, 3_423, 3_291, 3_509, 3_608, 3_615, 3_720, 3_317),
            "flat": (3_049, 2_963, 3_197, 2_843, 2_961, 2_670, 2_583, 2_600, 2_487, 2_968),
        },
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {
            "long": (3_741, 3_906, 6_257, 4_294, 3_959, 4_288, 4_310, 4_473, 4_552, 4_122),
            "flat": (4_513, 4_279, 4_172, 4_028, 4_277, 3_789, 3_972, 3_764, 3_722, 4_139),
        },
        "below": {
            "long": (3_807, 4_062, 6_576, 4_326, 4_033, 4_324, 4_330, 4_466, 4_593, 4_015),
            "flat": (4_506, 4_263, 4_508, 4_026, 4_329, 3_988, 3_899, 3_929, 3_737, 4_268),
        },
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {
            "long": (3_641, 3_974, 6_249, 4_142, 3_769, 4_354, 4_343, 4_421, 4_495, 3_984),
            "flat": (3_980, 3_690, 4_011, 3_508, 3_671, 3_462, 3_449, 3_389, 3_307, 3_830),
        },
        "below": {
            "long": (3_770, 4_120, 6_526, 4_298, 3_917, 4_530, 4_514, 4_622, 4_714, 4_138),
            "flat": (4_211, 3_854, 4_187, 3_683, 3_884, 3_629, 3_644, 3_541, 3_440, 4_022),
        },
    },
    "binperp_liq_short_z30d": {
        "above": {
            "long": (3_465, 3_543, 4_270, 3_828, 3_692, 3_984, 3_811, 3_835, 4_079, 3_562),
            "flat": (3_692, 3_415, 2_898, 3_298, 3_554, 3_160, 3_309, 3_141, 3_095, 3_654),
        },
        "below": {
            "long": (3_786, 3_884, 4_588, 4_176, 4_012, 4_259, 4_192, 4_201, 4_391, 3_843),
            "flat": (3_826, 3_554, 3_018, 3_436, 3_696, 3_347, 3_420, 3_243, 3_227, 3_763),
        },
    },
    "binperp_liq_total_z30d": {
        "above": {
            "long": (3_537, 3_625, 4_350, 3_793, 3_762, 4_039, 3_925, 3_934, 4_086, 3_558),
            "flat": (3_698, 3_400, 2_873, 3_274, 3_467, 3_153, 3_298, 3_091, 3_047, 3_622),
        },
        "below": {
            "long": (3_786, 3_884, 4_588, 4_176, 4_012, 4_253, 4_192, 4_201, 4_391, 3_843),
            "flat": (3_826, 3_554, 3_018, 3_436, 3_696, 3_347, 3_420, 3_243, 3_227, 3_763),
        },
    },
}


def per_asset(cells: dict) -> dict:
    """A cell table keyed by asset, as `_b2_reading_counts` returns it."""
    return {
        key: {
            tail: {state: dict(zip(subjects._ASSETS, counts)) for state, counts in by_state.items()}
            for tail, by_state in by_tail.items()
        }
        for key, by_tail in cells.items()
    }


def reading_inputs():
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_reading_2_inputs("b2-second-signal-reading", reader, "ohlc-full", None, False)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-oi set or the frozen daily liquidations block is absent under data/",
)
def test_the_second_signal_readings_inputs_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reading_inputs()
    assert compute_hash(reader.block()) == BLOCK
    assert reader.vouched_status() == VOUCHED
    assert len(inputs.close) == _RETURN_INDICES
    assert list(inputs.signals) == list(SIGNAL_FROM)
    for key, (index, first) in SIGNAL_FROM.items():
        signal = inputs.signals[key]
        assert next(k for k in range(_RETURN_INDICES) if all(signal[a][k] is not None for a in subjects._ASSETS)) == index, key
        assert inputs.close[index] == first, key
    assert tuple(sum(p > 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_LONG
    assert tuple(sum(p == 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_FLAT
    assert subjects._b2_reading_counts(inputs) == {"events_per_asset": per_asset(EVENTS), "others_per_asset": per_asset(OTHERS)}
```

- [ ] **Step 2: Run it** — with the three sets linked in this worktree: `mkdir -p .tmp/plan-00141 && uv run pytest tests/test_research_b2_second_signal_reading_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, 180 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b2_second_signal_reading_basis.py::test_the_second_signal_readings_inputs_reproduce_the_measured_basis
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_second_signal_reading_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths (measured `18 passed, 1 deselected in 17.78s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00141 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt` (measured `323 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B2's second signal reading's inputs against the measured basis — the block, the signals' starts, arm A's states and each cell's events and others`.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the owner's pick (spec 00141 D1) and then **Author's call** the reading's conventions, plan 00140's shape, so that the criterion stands in the log before any forward is read:

```markdown
[iter-185] B2's next step after the signal reading — a second no-slot reading over the untested signals, the owner's pick, attended, 2026-10-22 (Decision: 2)
  Said, attended, 2026-10-22: "go with the second reading on the untested signals". T0023's trigger after reading 3 — `[iter-184] B2's four crowding signals read for forward returns by tail and by arm A's state on frozen ohlc-full (reading 3)`, in which no cell had potential under spec 00140's criterion — named the pick of B2's next step; the controller set out B2's untried candidates as four options, and the owner picked the second. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)".
  1. **Variants of the trials already run** — a de-risk at another scale or threshold, the re-entries' park variants, a re-risk. Reading 3 mostly answers them: no tail of the four trialled signals, in either of arm A's states, shows a forward-return difference its pre-registered bounds separate from 0.
  2. **A second no-slot reading over the signals reading 3 did not test** — spec 00141: the OI log-delta and momentum z-scores in place of the OI level's, each of the four long/short ratios singly in place of their maximum, and the daily short-side and total liquidation z-scores beside the long side's, by reading 3's tails, states, forwards and criterion, its first leg at the Bonferroni bounds over 96 cells. Spends no B slot (14 of 25 remain) and screens these signals before a trial is spent on one. Chosen.
  3. **The 1-minute tape** — a different instrument; no frozen set's window reaches the tape block (spec 00138 D12), so a trial on it waits on an instrument ruling, the owner's.
  4. **Close B2 for B3 or B4-legs** — T0016's next families; spends nothing more on B2 and leaves its untested signals unread.

[iter-185] B2's second signal reading's conventions, pinned by spec 00141 before its hash (Decision: 1)
  The reading's details are fixed in the spec, reviewed, and frozen by its sha256, the reading's `spec_hash`, before any forward return is computed over the data; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00131 and 00137–00140 fixed staying theirs.
  1. **As the spec pins them** — one reading subject, `b2-second-signal-reading`, named so that no registered subject's name opens it, with no rule, family or count, kept with `--reading` and spending no B slot, over frozen `ohlc-full`'s full history (D2); arm A by calling `_b2_overlay_inputs` itself on the OI log-delta's reader, so the reading reads no set its signals do not, its states long (above 0) and flat (0) at the signal's close (D3); the eight crowding signals no trial read — the 180-mark z-scores of the OI log-delta and of the 30-day OI momentum, taken on the OI grid through `funding_zscore` since both are signed, each of the four long/short-ratio z-scores trial 4's maximum reads, singly and each on its own coverage, and the 30-day z-scores of the daily short-side and total liquidated notional, read as trial 5's long side is — and reading 3's one threshold for both tails, strictly above 2.0 and below −2.0 (D4); reading 3's forwards unchanged, the log return over 1, 6 and 24 closes and the simple returns summed over them (D5); per cell, the events against the other read closes in the same state, per asset and pooled, `event_contrast_chunked`'s row with its far bounds at 2.5/96 % and 100 − 2.5/96 %, the Bonferroni percentiles over 96 cells, from one stationary-bootstrap draw at mean block 102, 40,000 resamples and seed 42, drawn once as its blocks by `stationary_bootstrap_blocks` and read by `event_contrast_blocks` off running totals at the blocks' ends — its first five entries `event_contrast_chunked`'s to the bit and its bounds equal to that contrast's to rounding — each far bound between the 11th and 12th most extreme resampled differences where every resample is usable (D6); 54 keys and reading 3's refusals (D7); the potential criterion — read first, a floor of at least 2 kept assets and 100 events on the log return's pooled row, a cell under it unread, as the counts leave the nine cells of the total's lower tail with arm A long and of the taker ratio's lower tail; then on the log return's pooled row its far bounds excluding 0, Bonferroni over 96 cells though nine read no row and nine fall under the floor, the difference at least 0.012 in size and a sign a long/flat book can act on, and on the summed returns' pooled row the mean after the events at least +0.012 for a re-entry or a re-risk and at most −0.012 for a de-risk — read by the closeout's pick and never by code, the contamination stated — the trials' instrument, reading 3's results known when the reading was designed, and its correction over its own 96 cells, not both readings' 144 — a cell with potential naming its trial and none the evidence for the owner's family call (D8); one run after the hash, no plain eval before or after it (D9). Chosen.
  2. **The alternatives each weighed** — the name `b2-signal-reading-2`, which the retired `b2-signal-reading` opens; reading 3's funding reader for arm A, reading into the block a set no signal comes from; the OI log-delta and momentum z-scored at the union's closes; `oi_zscore` for a signed series; a single ratio read only where all four are; a bit-equal twin of `event_contrast_chunked` taking the far percentiles, about 3.1 hours at 40,000 resamples, past the nightly suite's three-hour cut-off; 2,000 resamples, the far bounds between the two most extreme; every cell with a row read, a pooled row of one asset's six events among them; a Bonferroni count over both readings' 144 cells; a rule over the criterion.
  Source: spec 00141 (D1–D9), its **Author's call**s and the calls it carries from the owner and specs 00131 and 00137–00140; the owner's word quoted in its ruling.
```

  staged alone, its gate `mkdir -p .tmp/plan-00141 && uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt` (measured on the authoring tree, the two entries appended, `50 passed`) and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-185] B2's next step after the signal reading — the owner's pick, a second no-slot reading — and its conventions, pinned by spec 00141 before its hash`. The pick's header is what T0023's `ripe_when` greps for (`B2.s next step after the signal reading`); Task 6 gives T0023 its next trigger.
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes a forward return or runs the reading over the real data before the spec's hash, and the data-gated case runs with the frozen full set, the OI set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D9)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00141-b2-signal-reading-2-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it; arm A's code path since reading 3's run (its ledger line's `invocation.commit`, `e6c318f32`), `git log --oneline e6c318f32..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/derivatives cli/liquidations cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1's and 2's commits and their fixes alone (measured at the base: nothing); any other commit is named, step 4's data test deciding whether it moved the inputs.
- [ ] **Step 2: D9 (1), the spec hash** — `sha256sum docs/specs/00141-b2-signal-reading-2-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the reading's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D9 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record another branch's merged PR carries; the operating model gives the reading ledger no other writer while this branch is open, so a line there stops the task, T0023's — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0023's — then takes a delta read of the merge in place of re-running step 1: step 1's arm-A log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 3 step 6's sentence with its "before the spec's hash" read "before Task 5's run", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the reading — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. The check has two sites, this step and Task 5 step 1, and both take this path.
- [ ] **Step 4: D9 (3), the data test on the run's tree, with the subject's two fixture rows** — `mkdir -p .tmp/plan-00141 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_second_signal_reading_basis.py` followed by Task 2 step 6's two quoted node ids, then `-q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt > .tmp/plan-00141/basis.out 2>&1`, one background call: `3 passed`, never a skip — the fixture rows run the build end to end on the tree a fix of the reads may have changed; a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code — T0023's, and the run waits.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00141/reading_check.py`, the ledger line's checks:

```python
"""Spec 00141's reading, read off the ledger's last line against the run's print and the measured basis: exit 0 when
every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_second_signal_reading_basis import BLOCK, EVENTS, OTHERS, VOUCHED, per_asset

spec_hash = sys.argv[1]
r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(".tmp/plan-00141/b2-second-signal-reading.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
events, others = per_asset(EVENTS), per_asset(OTHERS)
cells = [(key, tail, state, hours) for key in EVENTS for tail in ("above", "below") for state in ("long", "flat") for hours in (4, 24, 96)]
rows = {cell: m[f"{cell[0]}_fwd_logret_{cell[3]}h"][cell[1]][cell[2]] for cell in cells}
book = {cell: m[f"{cell[0]}_fwd_sumret_{cell[3]}h"][cell[1]][cell[2]] for cell in cells}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "invocation": invocation
    == {"subject": "b2-second-signal-reading", "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["iteration"], r["outcome"], r["attempt"]) == ("iter-185", None, None),
    "keys": set(m) == SUBJECTS["b2-second-signal-reading"].metric_keys,
    "printed": printed["metrics"] == m,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == BLOCK and printed["vouched"] == VOUCHED,
    "constants": (m["threshold"], m["mean_block"], m["n_resamples"], m["far_percentiles"]) == (2.0, 102, 40000, [2.5 / 96, 100 - 2.5 / 96]),
    "counts": (m["events_per_asset"], m["others_per_asset"]) == (events, others),
    "cells": len(cells) == 96,
    "rows": all(len(row) == 9 for table in (rows, book) for by_name in table.values() for row in by_name.values()),
    "ordered": all(row[7] <= row[5] <= row[6] <= row[8] for table in (rows, book) for by_name in table.values() for row in by_name.values()),
    "paired": all(
        list(book[cell]) == list(by_name) and all(book[cell][name][:2] == row[:2] for name, row in by_name.items())
        for cell, by_name in rows.items()
    ),
    "bounded": all(
        by_name[a][0] <= events[key][tail][state][a] and by_name[a][1] <= others[key][tail][state][a]
        for (key, tail, state, _), by_name in rows.items()
        for a in by_name
        if a != "pooled"
    ),
    "pooled": {cell for cell, by_name in rows.items() if "pooled" in by_name}
    <= {cell for cell in cells if any(events[cell[0]][cell[1]][cell[2]].values())},
}
print(r["reading_id"], checks)
sys.exit(0 if all(checks.values()) else 1)
```

  and `.tmp/plan-00141/pooled_rows.py`, the print Task 5's entry reads the criterion off:

```python
"""The reading's 96 pooled cells off the ledger's last line, one a line: the signal, tail, state and horizon, then the
log forward's kept assets and its pooled row's events, others, difference and far low and far high bounds and the summed
returns' mean after the events, or `no row`; it judges none of them."""

import json
from pathlib import Path

m = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])["metrics"]
signals = (
    "binperp_oi_log_delta_z30d",
    "binperp_oi_momentum_z30d",
    "binperp_count_toptrader_long_short_ratio_z30d",
    "binperp_sum_toptrader_long_short_ratio_z30d",
    "binperp_count_long_short_ratio_z30d",
    "binperp_sum_taker_long_short_vol_ratio_z30d",
    "binperp_liq_short_z30d",
    "binperp_liq_total_z30d",
)
for key in signals:
    for tail in ("above", "below"):
        for state in ("long", "flat"):
            for hours in (4, 24, 96):
                rows = m[f"{key}_fwd_logret_{hours}h"][tail][state]
                row = rows.get("pooled")
                book = m[f"{key}_fwd_sumret_{hours}h"][tail][state].get("pooled")
                print(key, tail, state, f"{hours}h", "no row" if row is None else [len(rows) - 1, row[0], row[1], row[4], row[7], row[8], book[2]])
```

  Each is written with `mkdir -p .tmp/plan-00141 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00141/reading_check.py .tmp/plan-00141/pooled_rows.py`. **Author's call — the `pooled` check a subset, not an equality**: a cell whose events hold no asset with two events and two others whose forward is read keeps no pooled row, which the counts alone cannot decide before the run — three triples, nine cells, hold few events (spec 00141's basis) — so the check refuses a pooled row in a cell with no event, and the print shows any other cell reading `no row`, which Task 5's entry names.

## Task 5 (the controller's): the reading — its run, its line, its replay and its entry (D8, D9)

`<H>` is Task 4 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 4 step 3 whole, its stop, its merge path and Task 4 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The run** — one run, no plain eval before or after it: `mkdir -p .tmp/plan-00141 && uv run zcrypto research eval --subject b2-second-signal-reading --dataset ohlc-full --reading --iteration iter-185 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00141/b2-second-signal-reading.out 2>&1`, about seven minutes (the spec's basis), one background call, `cat` at its notification. The notes, written before the run, name only what is fixed before it: `subject b2-second-signal-reading over ohlc-full, full history, no as-of; descriptive, no bar, no verdict, no B slot, changing no verdict of B2 trials 2-7 nor reading 3's finding; the eight crowding signals no trial read - the 180-mark z-scores of the open-interest log-change and of its 30-day momentum on the OI grid, each of the four long/short-ratio z-scores singly, and the 30-day z-scores of the daily short-side and total liquidated notional; per signal, tail (above 2.0, below -2.0) and arm A state at the close (long, flat), per asset and pooled: the forward 1-, 6- and 24-close log returns on the arms' prices, and the simple returns summed over the same closes, after the closes past the tail, against the other closes where the signal is read in the same state; stationary-bootstrap 2.5/97.5 % bounds and far bounds at the Bonferroni percentiles over 96 cells, 2.5/96 % and 100 - 2.5/96 %, mean block 102, 40000 resamples, seed 42, one draw shared by every cell; the potential criterion - read first, a floor on the log returns' pooled row of at least 2 kept assets and 100 events, a cell under it unread; then on the log returns' pooled row the far bounds excluding 0, the difference at least 0.012 in size and a sign a long/flat book can act on, and on the summed returns' pooled row the mean after the events at least +0.012 for a re-entry or a re-risk and at most -0.012 for a de-risk - read by the closeout's pick, never by code; pre-registered by the spec's sha256 <H>`. A refused build — exit 1 with no traceback, naming `b2-second-signal-reading over the full history: …` or a file of `derivatives-oi` or `liquidations-daily` — keeps no reading and is recorded in T0023 with its line quoted (Task 6), the reading's design standing unrun; a refusal before the build reads anything — the tree (`… has uncommitted changes …`), the spec hash (`--spec-hash … is not …`) or the dataset's presence (`dataset 'ohlc-full' is absent …`, `… is missing N series …`) — keeps nothing and computes nothing: its cause fixed, the same command runs again, still the one run; a traceback, a signal or a ledger refusal stops the task, T0023's with the end of the run's output quoted whole.
- [ ] **Step 3: The reading's checks** — `uv run python .tmp/plan-00141/reading_check.py <H>` exits 0; a failed check stops the task before step 4.
- [ ] **Step 4: The pooled rows** — `uv run python .tmp/plan-00141/pooled_rows.py`, its 96 lines the entry's source.
- [ ] **Step 5: The records commit** — (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-185] B2's eight untested crowding signals read for forward returns by tail and by arm A's state on frozen ohlc-full (reading <its reading_id>)`, its header to its first `. ` holding no verdict word; the body: the subject, the set and the block `bfbaff14…c6ca8f6a`; that the reading is descriptive, spends no slot and changes no verdict nor reading 3's finding (D2, D8); the cells under the floor, each unread — those step 4's print shows with fewer than 2 kept assets or 100 events, the nine of the basis's three thin triples among them — and for each of the criterion's four legs, the cells the floor admits that meet it — signal, tail, state and horizon — read off step 4's print; the pooled rows, the log forward's and the summed returns', nine entries each unrounded, read off the reading's ledger line, of every such cell meeting the first leg, each bound named by its family; the cells with potential, each with the trial it names — the action on that signal past that tail, in that state, held H closes, and, where the signal is a part of a trialled one or the action a rejected trial's, which — or, where none has potential, that no cell has it and that this is the evidence the owner's family call reads; the cells that read no row, the basis's nine and any other the print shows; the caveats — the far bounds between the 11th and 12th most extreme of 40,000 resampled differences where every resample is usable, a thin cell's usable count unrecorded, and equal to the chunked contrast's to rounding; the rows counting the closes with a forward and `events_per_asset` every flagged close; and the contamination D8 states, its correction over this reading's 96 cells and not both readings' 144 among it; in the form of reading 3's `[iter-184]` entry; (ii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<its id>]` at its `sorted()` place, the replay rebuilding the whole reading. Then `git add` by path of the ledger, the decisions log and the slow-cases file; `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, the three sets linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00141/probe/data/<set>`, unlinked after the replay and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'reading-<its id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task. Commit that index, with no `git add` after the setup, as `docs(research): B2's second signal reading — the eight untested crowding signals' forward returns on ohlc-full, kept as reading <id>; no trial spent`, the message carrying the tie tests' result line, the replay's with its call time, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<id>]`, the line `The replay reads data/ohlc-full, data/derivatives-oi and data/liquidations-daily: re-run it with the three sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes. The entry adds no guard: no probe.

## Task 6: T0023, T0016, the index and the retirement of the subject (D8)

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py`.

On a refused build (Task 5 step 2) no reading exists: Task 5's steps 3–5 do not run, so no finding entry lands, and this task runs without a reading. Every sentence of Tasks 6–7 that assumes a reading changes, and these are all of them: step 1's Findings bullet, headed `**B2's second signal reading (iter-185, spec 00141).**`, quotes the refused line; its Done-so-far bullet names no reading; its next-step bullet keeps every candidate it lists, its words from `reading spec 00141's potential criterion` through `beside the criterion` reading `reading the refused build, quoted in Findings, the design unrun; beside it`, with no arm for a reading in which no cell has potential, and its trigger's `reading spec 00141's potential criterion` becomes `reading the refusal`, its check unchanged; step 2's B2 line names the second signal reading refused, with no reading id; step 4 does not run, since a later run still evaluates the subject (`tests/retired_subjects.py`'s own rule), so step 5 stages the three `docs/open-topics/` paths alone and its message ends `the reading refused, its subject kept`; Task 7 step 2's `drive` names the data-gated case alone, no replay; and Task 7 step 3's body quotes the refused line in place of the pooled rows and names no cell.

- [ ] **Step 1: T0023**, per `topic-ops`, every figure read off the committed reading and its entry: `## Findings so far` gains one bullet — `**B2's second signal reading (iter-185, spec 00141, reading <N>).**` — in one or two sentences, the cells with potential and the trial each names, or that none has potential, pointing at its decisions-log entry for the figures; or, on a refused build, its line quoted whole from `.tmp/plan-00141/b2-second-signal-reading.out`; `## Done so far` gains **B2's second signal reading (iter-185, spec/plan 00141)**, naming `oi_log_delta_zscore_grid_feature`, `oi_momentum_zscore_grid_feature`, `stationary_bootstrap_blocks` and `event_contrast_blocks` in `cli/alpha/b2.py`, the subject `b2-second-signal-reading` and the data-gated basis test `tests/test_research_b2_second_signal_reading_basis.py`, and the reading by id; `## Suggested next steps` replaces `(the loop's pick under a run instruction, else the owner's; a close is the owner's) B2's next step after the signal reading` with `(the loop's pick under a run instruction, else the owner's; a close is the owner's) B2's next step after the second signal reading` — reading spec 00141's potential criterion: a trial a cell with potential names, each its own pre-registration against the shared B budget carrying D8's contamination, or, with none, the owner's family call, hold or close B2; beside the criterion the pick reads every candidate still untried, and the bullet drops none — the replaced bullet's own: a de-risk variant (scale 0.25, threshold 3.0), the de-risks' and the re-entries' further legs, a trial on the tape, a follow-up reading 2's figures invite (the daily history reconciled with the tape, the reading at a later as-of or over a longer span, a per-side reading), the re-entries' park variants (the threshold one step toward 0, the size halved), the full-long split of arm A's long state that a re-risk reads, and a reading at another threshold, signal, horizon or state split, on another instrument, on the tape or at a later as-of; and the options the owner's pick set aside (spec 00141 D1): the 1-minute tape and a close for B3 or B4-legs — recorded as a `[iter-NNN] B2's next step after the second signal reading` entry; `ripe_when`: ``an activity: B2's next step after the second signal reading is picked, reading spec 00141's potential criterion, recorded in the decisions log; check: `grep -c -E '^\[iter-[0-9]+\] B2.s next step after the second signal reading' docs/research/10.phase4-decisions.md` prints at least 1``, in the frontmatter's quoting, the check kept in its own backticks. The check is run as committed and prints 0.
- [ ] **Step 2: T0016** — its budget line's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` — the reading spends none (measured at this branch's base: `{'B1': 5, 'B2': 6} remain 14 []`, T0016's line `B1 spent 5, B2 spent 6, 14 remain`): the line reads `B1 spent <its B1>, B2 spent <its B2>, <its remain> remain`, each orphan it lists named on that line; its B2 line names the second signal reading (iter-185, spec/plan `00141`, reading <N>), no slot spent.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the reading's subject, so `RETIRED_SUBJECTS` gains `"b2-second-signal-reading",` after `"b2-signal-reading",`, its comment `# B2's finished trials and the readings beside them.` unchanged; and every test function of `tests/test_research_command.py` specific to the subject and named by no parameter carries `@pytest.mark.retired` as its first decorator — all six Task 2 adds: `test_the_second_signal_reading_declares_the_4h_grid_its_keys_and_no_rule`, `test_the_second_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_untested_signal_by_its_reader`, `test_each_untested_signal_reader_reads_its_signals_off_their_own_columns`, `test_the_second_signal_reading_hands_every_cell_one_shared_draw_and_keys_its_rows`, `test_the_second_signal_reading_refuses_as_of_before_any_read` and `test_the_second_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it`; Task 1's cases test functions of `cli/alpha/b2.py` and stay. `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q -p no:cacheprovider | grep -c -E "second.signal.reading|untested_signal"` prints 0 and the same under `-m retired` prints 21 (measured on the authoring tree), and `mkdir -p .tmp/plan-00141 && uv run pytest tests/test_retired_subjects.py -q -p no:cacheprovider --basetemp=.tmp/plan-00141/pt` passes (measured `5 passed`).
- [ ] **Step 5: Gate and commit** — `git add` the five paths; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path, in its three parts; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0023 and T0016 after B2's second signal reading; the reading's subject retired`.

## Task 7 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-185 — B2 second signal reading: untested signals` (69 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 5–6's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with the frozen full set, the OI set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the reading's pooled rows as step 4 of Task 5 printed them, in a fenced block, with the cells under the floor, the cells the floor admits meeting each leg of the criterion and those with potential, or none; every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00141` collected and removed, and `unlink data/ohlc-full`, `unlink data/derivatives-funding`, `unlink data/derivatives-oi` and `unlink data/liquidations-daily` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the four sets still there.

Decisions log: the owner's pick and the conventions entry (Task 3 step 5), before the hash; the reading's finding entry (Task 5 step 5), in its line's commit.
