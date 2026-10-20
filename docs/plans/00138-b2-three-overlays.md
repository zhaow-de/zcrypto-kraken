# B2 trials 3–5 — the three overlays on frozen ohlc-full, the frozen liquidations block, the gated runs and the verdicts — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Execution is subagent-driven — the owner's "one SDD loop". Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b2.py tests/test_alpha_b2.py cli/research/subjects.py tests/test_research_command.py tests/test_research_b2_overlays_basis.py README.md tests/slow-cases.txt docs/reference/vouched-dataset-hashes.jsonl docs/reference/data-catalog-full.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/test_trial_registry_provenance.py tests/retired_subjects.py` prints `tier: full`, for `tests/test_alpha_b2.py` "a test importing cli.alpha.b1", `tests/test_research_command.py` "a test importing cli.alpha", `docs/reference/trial-registry.jsonl` and `tests/test_trial_registry_provenance.py`).

**Goal:** B2's trials 3, 4 and 5 (spec 00138) — three emitters in `cli/alpha/b2.py`, the frozen block of the live liquidations tape with its attestation and coverage proof, six research subjects (three trials and their evaluate-only pre-flight twins) in `cli/research/subjects.py`, the data-gated test of their inputs half, and the three trials run in order through spec 00133's trial-attempts log — each verdict or stop in the registry or the ledger and the decisions log, then T0023, T0016 and the owner's pick recorded.

**Architecture:** no new module and no change to an existing function. `cli/alpha/b2.py` gains `ratio_zscore_grid_features`, `ratio_max_signal` and `liquidation_zscore_grid_feature` over spec 00131's and spec 00136's pipelines. `cli/research/subjects.py` gains one overlay machinery — `_B2OverlayInputs`, `_b2_overlay_inputs` (the union, arm A by `_b2_inputs`' expression, the signal, the scales), `_b2_overlay_metrics` (`_b2_full_metrics`' body with the signal's own start in `k21`'s place) and `_b2_overlay_preflight_metrics` — three signal readers and six thin `_build_` wrappers. The freeze is two controller programs; nothing under `cli/` writes the block.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00138-b2-three-overlays-design.md` — binding; D1–D11 are cited by name and the values below are copied from it. It copies spec 00137's instrument, bar, arms and costing and spec 00128's matrix, both frozen (record 51's and reading 1's `spec_hash`). **Iteration:** iter-182. **Topic:** T0023 under T0016. **Branch:** `research/iter-182-b2-three-overlays`, worktree `.claude/worktrees/iter182`, `data/ohlc-full`, `data/derivatives-funding` and `data/derivatives-oi` linked read-only from the main checkout; Task 2 links `data/liquidations-frozen`. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was extracted from this file and run against the tree in task order in a detached scratch worktree before this plan was committed — the commands against their `Expected`, each `-k` filter's collect count, each probe row's two seds matching exactly one line of the code the fences write and each probe run to its verdict, seventy-four of seventy-four `KILLED`; Task 2's two programs ran against the live tree read-only with their writes redirected into scratch, and its eleven sidecar lines stood in for Task 2 under Tasks 3 and 4. Not run: any `zcrypto research eval` (Tasks 6–8), the data-gated test beyond `--collect-only` (Task 4 step 2), the check programs beyond a parse and a synthetic print (Task 5 step 5), the replays and the literal probes beyond their seds (Tasks 6–8), the topic edits (Task 9 steps 1–3) and the PR (Task 10).

## Global Constraints

- **The signals and thresholds** (D3–D6): OI — `oi_zscore_grid_feature(rows["ts"], rows["sum_open_interest"], h4_ts)` per asset over `derivatives-oi/<PERP>/oi.parquet` read whole, key `binperp_oi_z30d`, threshold `_B2_OI_THRESHOLD = 2.5`; ratios — `ratio_max_signal(ratio_zscore_grid_features(rows["ts"], {the four columns}, h4_ts))` over the same files, key `binperp_ratio_max_z30d`, `_B2_RATIO_THRESHOLD = 2.5`; liquidations — `liquidation_zscore_grid_feature(ts, long_usd, short_usd, h4_ts, covered)` per coin over `liquidations-frozen/<COIN>/buckets.parquet` with `covered` from `liquidations-frozen/covered-hours.parquet`, key `binperp_liq_total_z30d`, `_B2_LIQ_THRESHOLD = 2.0`; every scale `derisk_scales(signal, config=B2Config(z_threshold=<threshold>))`, arm B `scale_positions(arm_a, scales)`.
- **The bars** (D2, D8): every `a1_kill_bar` call `n_trials=<the subject's count>, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, the headline (30, 42); arm A's bar the same call at (30, 42) on `net_a`; the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` for `("full", 0)` and `("primary", start)`, `start` `_b2_overlay_start(inputs)`, the first return index every asset's signal holds; the drawdown pair from `start`; refused before any bar: fewer than 2 return indices from `start`, or arm A never drawing down from it.
- **The counts** (D8): `_B2_OI_N_TRIALS = 2`, `_B2_RATIO_N_TRIALS = 3`, `_B2_LIQ_N_TRIALS = 4`, fixed by the spec's hash; at `var_trials` 0.0 none moves a figure of the bar.
- **The rule** (D8): `_b2_overlay_verdict` — `None` when `arm_a_passes` is 0 or no year holds an engaged stamp, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0`, `max_drawdown_reduction_pct > 1e-6` and `head_to_head_spa_p_primary < 0.05`, `park` on the first two with the p at or above 0.05, `reject` otherwise.
- **The records** (D9): family `B2`; `n_trials_in_family` the count; variants `B2-oi-derisk-a2eq-full-v1`, `B2-ratio-derisk-a2eq-full-v1`, `B2-liq-derisk-a2eq-full-v1`; iteration `iter-182`; seeds (42, 7, 1234); 41 metric keys; the OI and ratio records' `dataset_hash` `69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf`; no `--verdict`.
- **The pre-flight read** (D10), in this order: (a) the block; (b) arm A's seven anchors at record 45's precision — `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown_full` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703, the benchmark's 1.2128 and 1.2447 at four decimals, `turnover_a` 146.19 at two; (c) `engaged_per_asset`, `engaged_per_year`, the signal's coverage and `primary_returns` the measured basis's; (d) the engaged total above 0; (e) arm A's `passes` 1.
- **The hash rule** (D10): before Task 5 step 2 takes the spec's sha256, nobody computes arm A's bar or any position or return of arm B over the trial's data; the data-gated test (Task 4) computes arm A's positions, its net, its seven anchors, the signals and the engagement — the basis's own measures — and no bar; no reader, reviewer or plan-review dispatch runs any of the six subjects over the real sets before the hash, and every read's dispatch carries this rule. No return of arm B is computed over the trial's data before that trial's `--register` run, and no trial subject is ever run as a plain eval.
- **Unchanged** (D9): every existing function of `cli/alpha/b2.py`, `cli/research/subjects.py`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/engine/*` and `cli/liquidations/*`, the subjects of trials 1 and 2, and any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/alpha/b2.py` from Task 1 on and `cli/research/subjects.py` from Task 3 on, nothing else; `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/ | grep -c '^-[^-]'` prints 0 — pure insertions: measured on the transcription, `cli/alpha/b2.py`'s hunks `@@ -37,0 +38,3 @@` and `@@ -293,0 +297,35 @@`, `cli/research/subjects.py`'s `@@ -58,0 +59 @@`, `@@ -59,0 +61 @@`, `@@ -63,0 +66,2 @@`, `@@ -1992,0 +1997,436 @@` and `@@ -2161,0 +2602,75 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00138-b2-three-overlays-design.md` after Task 5 step 2, nor specs 00128 and 00137; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Tasks 6–8 name it. Never `git stash`; no amend; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, `data/derivatives-oi` and, from Task 2, `data/liquidations-frozen`, read-only links, never written under; `data/derivatives-funding` only where an existing test reads it. The live tree `/var/lib/zcrypto-ops/liquidations` is read by Task 2's two programs alone, read-only. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, ssh, docker, a fleet host, `kraken-cli`, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 2, Task 4 step 7's reads, Tasks 5–8 and Task 10's steps 2–4, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the freeze's second read, the data tests, the pre-flights, the registers, the replays), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 3 and 9, Task 4's steps 1–6 and Task 10's step 1.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00138 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` (or a file, or `-k`). An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file or node id into parts that cannot, each its own `--basetemp=.tmp/plan-00138/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`, never a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. A commit message's test result line is a run over that commit's own tree.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
test ! -e .tmp/plan-00138/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00138/probe HEAD &&
  git -C .tmp/plan-00138/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00138/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00138/probe/.tmp
```

  Then, from `.tmp/plan-00138/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. After the last verdict, `git worktree remove --force .tmp/plan-00138/probe` — a data link in it unlinked first. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **Commits**: one per task that changes the tree, two for Task 4 (the test, then step 6's conventions entry), one per trial for Tasks 6–8, two for Task 10 (the decisions-log entry, then the change-index row); Task 5 adds none, a merge of develop aside. Each ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: <the executing session's URL>`; an implementer on another model names its own.
- **The reads**: the trio over the branch through Task 4 (`pre-review`, `review`, `re-review`, as CLAUDE.md orders them; Task 4 step 7) closes with no open Critical or Important before Task 5 step 2, and nothing the runs execute or the records pin changes from that read to the registrations unless a read of the change follows; Tasks 6–10's commits take their own `pre-review`, then the read of the delta from the tip the last read covered (Task 10 step 3) before the push that carries it; the PR is created and edited through `open-pr`, its read line naming the tip read.

## Review Focus

- The ratio signal must read the four z-scores' maximum only where all four are defined, never the maximum of those defined. Test: Task 1, `test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read`.
- A liquidation bar the freeze does not assert covered must darken every z-score window holding it, never read as a zero total. Test: Task 1, `test_an_uncovered_bar_leaves_every_liquidation_zscore_window_holding_it_none`.
- An overlay trial's metrics must be trial 2's with only the start and the count moved, the threshold reaching the scales. Test: Task 3, `test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count`.
- The liquidations twin must evaluate, never refuse, when no close carries its signal, so D10's dead-knob stop is kept as a reading. Test: Task 3, `test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero`.
- A frozen liquidations file whose content moved since the freeze must be refused at the read, through the sidecar's path binding. Test: Task 4, `test_the_liquidations_block_is_attested_and_its_signal_holds_no_close_of_the_union` (`vouched_status` `checked (11 vouched hashes)`), `ObservedReader`'s existing path-bound check (`tests/test_data_vouched_sidecar.py::test_the_sidecar_arms_the_read_guard_and_a_tampered_frame_is_refused`) its refusal.

## File structure

- Modify `cli/alpha/b2.py` — two window constants and three functions (Task 1); `tests/test_alpha_b2.py` — their tests.
- Create `data/liquidations-frozen/` in the main checkout (gitignored) and link it; modify `docs/reference/vouched-dataset-hashes.jsonl` — eleven lines; `docs/reference/data-catalog-full.md` — the block's entry (Task 2).
- Modify `cli/research/subjects.py` — the overlay machinery before `SUBJECTS`, six entries at its end; `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt` (Task 3).
- Create `tests/test_research_b2_overlays_basis.py` (data-gated); modify `tests/slow-cases.txt`, `docs/research/10.phase4-decisions.md` (Task 4).
- At the runs: `docs/reference/trial-registry.jsonl`, `docs/reference/reading-ledger.jsonl`, `tests/test_trial_registry_provenance.py`, `docs/research/10.phase4-decisions.md`, `tests/slow-cases.txt` (Tasks 6–8); `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` (Task 9); `docs/research/10.phase4-decisions.md`, `docs/reference/change-index.md` (Task 10). Scratch under `.tmp/plan-00138/`.

______________________________________________________________________

### Task 1: the three emitters — the ratio z-scores, their maximum, the liquidation z-score (D5, D6)

**Files:**
- Modify: `cli/alpha/b2.py` — two constants after `_OI_MOMENTUM_LOOKBACK = 180`; three functions after `liquidation_grid_features` and before `_check_lengths`
- Modify: `tests/test_alpha_b2.py`

**Interfaces:**
- Consumes: `cli/alpha/b2.py` as `a9c8be5d1` holds it — `_rows_at_union_closes(label, feature, oi_ts, values_name, levels, union_ts)`, `ratio_features` (imported from `cli.features.derivatives`, which names the four columns `binperp_<column>` and validates them finite or null), `liquidation_grid_features(bucket_ts, long_usd, short_usd, union_ts, covered)`, `_check_lengths`, `funding_zscore` and `oi_zscore` (imported), `partial`, `Collection`; in the tests, `_hours`, `DAY0`, `_RATIO_COLUMNS`, `_each_ratio`, `_oi_prefix_fixture`.
- Produces:

```python
# cli/alpha/b2.py
_RATIO_ZSCORE_WINDOW = 180
_LIQUIDATION_ZSCORE_WINDOW = 180

def ratio_zscore_grid_features(oi_ts: list[datetime], ratios: dict[str, list[float | None]], union_ts: list[datetime]) -> dict[str, list[float | None]]: ...  # binperp_<column>_z30d
def ratio_max_signal(z_columns: dict[str, list[float | None]]) -> list[float | None]: ...
def liquidation_zscore_grid_feature(bucket_ts: list[datetime], long_usd: list[float], short_usd: list[float], union_ts: list[datetime], covered: Collection[datetime]) -> list[float | None]: ...
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_alpha_b2.py`, the `from cli.alpha.b2 import (` block gains `liquidation_zscore_grid_feature,` after `liquidation_grid_features,` and `ratio_max_signal,` and `ratio_zscore_grid_features,` after `ratio_grid_features,`; `from cli.features.derivatives import funding_zscore` goes before `from cli.features.errors import FeatureError`; and at the end of the file:

```python


def _ratios_on_the_grid(marks: int) -> tuple[list[datetime], dict[str, list[float | None]], list[datetime]]:
    """Column i holds 1.0 at every mark but mark 180 + i, where it holds 2.0, each level the later of two rows inside its
    bar, the earlier 1.5 times it: a z-score over the raw rows, or a column read in another's place, differs."""
    union_ts = _hours(*range(0, 4 * (marks + 1), 4))
    oi_ts, ratios = [], {name: [] for name in _RATIO_COLUMNS}
    for k in range(marks):
        close = union_ts[k] + timedelta(hours=4)
        oi_ts += [close - timedelta(minutes=10), close - timedelta(minutes=5)]
        for i, name in enumerate(_RATIO_COLUMNS):
            level = 2.0 if k == 180 + i else 1.0
            ratios[name] += [1.5 * level, level]
    return oi_ts, ratios, union_ts


def test_each_ratio_zscore_scores_its_own_columns_level_over_180_grid_marks():
    spike, after = pytest.approx(179 / math.sqrt(180)), pytest.approx(-1 / math.sqrt(180))
    expected = {
        f"binperp_{name}_z30d": [None] * 179 + [0.0] * (1 + i) + [spike] + [after] * (3 - i)
        for i, name in enumerate(_RATIO_COLUMNS)
    }
    assert ratio_zscore_grid_features(*_ratios_on_the_grid(184)) == expected


def test_a_zero_taker_ratio_is_scored_where_an_oi_level_gate_would_refuse_it():
    oi_ts, ratios, union_ts = _ratios_on_the_grid(181)
    ratios["sum_taker_long_short_vol_ratio"] = [0.0] * len(oi_ts)
    features = ratio_zscore_grid_features(oi_ts, ratios, union_ts)
    assert features["binperp_sum_taker_long_short_vol_ratio_z30d"] == [None] * 179 + [0.0, 0.0]


def test_a_null_ratio_leaves_every_zscore_window_holding_its_mark_none():
    oi_ts, ratios, union_ts = _ratios_on_the_grid(181)
    ratios["count_long_short_ratio"][1] = None
    # Bar 0's later row is null: fallen back to its earlier row, 1.5, the first window would score.
    assert ratio_zscore_grid_features(oi_ts, ratios, union_ts)["binperp_count_long_short_ratio_z30d"] == [None] * 180 + [0.0]


def test_the_ratio_and_liquidation_windows_are_the_pre_registered_180_marks_and_bars():
    assert (b2._RATIO_ZSCORE_WINDOW, b2._LIQUIDATION_ZSCORE_WINDOW) == (180, 180)


def test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_zscores_bit_for_bit():
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    ratios = _each_ratio([None if v == 0.0 else v / 100 for v in oi_values]) | {
        "sum_taker_long_short_vol_ratio": [v / 100 for v in oi_values]
    }
    full = ratio_zscore_grid_features(oi_ts, ratios, union_ts)
    # Exact: a stale level read in place of None, or a null fallen back to its row's predecessor, defines more closes.
    assert {name: sum(v is not None for v in values) for name, values in full.items()} == {
        f"binperp_{name}_z30d": 22 for name in _RATIO_COLUMNS
    }
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = ratio_zscore_grid_features(
            [oi_ts[i] for i in visible], {name: [values[i] for i in visible] for name, values in ratios.items()}, union_ts[: n + 1]
        )
        assert prefix == {name: values[:n] for name, values in full.items()}, f"prefix at n={n} disagrees with the full run"


def test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read():
    columns = {"a": [1.0, 3.0, None, -0.5], "b": [2.0, -1.0, 4.0, None], "c": [0.0, 0.0, 0.0, 0.0]}
    # Their mean reads 1.0 and 0.667 at the first two, their minimum 0.0 and -1.0, the read ones' maximum 4.0 and 0.0 at
    # the last two.
    assert ratio_max_signal(columns) == [2.0, 3.0, None, None]


@pytest.mark.parametrize(
    ("columns", "match"),
    [({}, "z_columns is empty"), ({"a": [1.0], "b": [1.0, 2.0]}, "b has length 2, expected 1")],
    ids=["no-column", "unequal-length"],
)
def test_ratio_max_signal_refuses_no_column_or_columns_of_unequal_length(columns, match):
    with pytest.raises(AlphaError, match=match):
        ratio_max_signal(columns)


def _liquidations_on_the_union(
    long_usd: list[float], short_usd: list[float], *, uncovered: int | None = None
) -> tuple[list[datetime], list[float], list[float], list[datetime], list[datetime]]:
    """One bucket per union bar, a minute after its open; every hour asserted covered but `uncovered`."""
    union_ts = _hours(*range(0, 4 * (len(long_usd) + 1), 4))
    bucket_ts = [t + timedelta(minutes=1) for t in union_ts[:-1]]
    covered = [t for t in _hours(*range(4 * len(long_usd))) if uncovered is None or t != DAY0 + timedelta(hours=uncovered)]
    return bucket_ts, long_usd, short_usd, union_ts, covered


def test_the_liquidation_zscore_scores_each_bars_total_over_180_union_bars_never_one_leg():
    # The long leg spikes at bar 179 and the short at bar 180: their total spikes at both, each leg at one.
    long_usd = [50.0] * 179 + [150.0, 50.0]
    short_usd = [50.0] * 180 + [150.0]
    feature = liquidation_zscore_grid_feature(*_liquidations_on_the_union(long_usd, short_usd))
    assert feature == funding_zscore([100.0] * 179 + [200.0, 200.0], window=180)
    assert feature[179:] == [
        pytest.approx(179 / math.sqrt(180)),
        pytest.approx((178 / 180) / math.sqrt(2 * 178 / (180 * 179))),
    ]


def test_an_uncovered_bar_leaves_every_liquidation_zscore_window_holding_it_none():
    # Hour 2 lies in bar 0: read as a zero total, the first window would score.
    feature = liquidation_zscore_grid_feature(*_liquidations_on_the_union([100.0] * 181, [0.0] * 181, uncovered=2))
    assert feature == [None] * 180 + [0.0]


def test_a_truncated_prefix_of_the_buckets_reproduces_the_liquidation_zscore_bit_for_bit():
    long_usd = [100.0 + (37 * k) % 23 for k in range(200)]
    bucket_ts, long_usd, short_usd, union_ts, covered = _liquidations_on_the_union(long_usd, [1.0] * 200, uncovered=29)
    # The union misses bar 100's open: stretched across the hole, bar 99 would sum bar 100's bucket.
    del union_ts[100]
    full = liquidation_zscore_grid_feature(bucket_ts, long_usd, short_usd, union_ts, covered)
    # Exact: hour 29 is bar 7's, so every window holding return index 7 is None.
    assert len(full) == len(union_ts) - 1 and [j for j, v in enumerate(full) if v is not None] == list(range(187, len(full)))
    # From n = 2: `funding_zscore` refuses a list of one total.
    for n in range(2, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        prefix_covered = [t for t in covered if t + timedelta(hours=1) <= cutoff]
        k = sum(t + timedelta(minutes=1) <= cutoff for t in bucket_ts)
        prefix = liquidation_zscore_grid_feature(bucket_ts[:k], long_usd[:k], short_usd[:k], union_ts[: n + 1], prefix_covered)
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"
```

  **Author's call** — the known answers are hand values (`179 / sqrt(180)`, `-1 / sqrt(180)`, `(178 / 180) / sqrt(2 · 178 / (180 · 179))`), the first liquidation assertion pinning `funding_zscore`'s own answer beside them; each column of `_ratios_on_the_grid` spikes at a different mark and each bar's earlier row is 1.5 times its last, so a column read in another's place or a z-score over the raw rows differs; the prefix tests follow spec 00131's and spec 00136's, the liquidation one from `n = 2` because `funding_zscore` refuses a list of one value.

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00138 && uv run pytest tests/test_alpha_b2.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`
Expected: the module fails to collect, `ImportError: cannot import name 'liquidation_zscore_grid_feature' from 'cli.alpha.b2'`, `1 error` (measured on the transcription)

- [ ] **Step 3: Implement in `cli/alpha/b2.py`** — after `_OI_MOMENTUM_LOOKBACK = 180`:

```python
# Pre-registered 30-day windows (docs/specs/00138 D5, D6), not knobs: a change to one is a new trial.
_RATIO_ZSCORE_WINDOW = 180
_LIQUIDATION_ZSCORE_WINDOW = 180
```

  and after `liquidation_grid_features` and before `def _check_lengths(`:

```python
def ratio_zscore_grid_features(
    oi_ts: list[datetime], ratios: dict[str, list[float | None]], union_ts: list[datetime]
) -> dict[str, list[float | None]]:
    """Each ratio's trailing z-score over its level on the OI rows' regular grid, read at a union's closes
    (docs/specs/00138 D5): `funding_zscore` is the finite-or-null trailing z-score, where `oi_zscore`'s positive-level gate
    would refuse a `0.0` taker ratio."""
    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)
    return {
        f"{name}_z30d": _rows_at_union_closes(f"{name} z-score", zscore, oi_ts, name, values, union_ts)
        for name, values in ratio_features(ratios).items()
    }


def ratio_max_signal(z_columns: dict[str, list[float | None]]) -> list[float | None]:
    """The columns' maximum at each index, None wherever any column is None (docs/specs/00138 D5)."""
    if not z_columns:
        raise AlphaError("z_columns is empty: the signal reads at least one column")
    n = _check_lengths(z_columns)
    columns = list(z_columns.values())
    return [None if any(column[k] is None for column in columns) else max(column[k] for column in columns) for k in range(n)]


def liquidation_zscore_grid_feature(
    bucket_ts: list[datetime],
    long_usd: list[float],
    short_usd: list[float],
    union_ts: list[datetime],
    covered: Collection[datetime],
) -> list[float | None]:
    """The trailing z-score of one coin's per-bar total over the union's own bars (docs/specs/00138 D6): a bar
    `liquidation_grid_features` reads None leaves every window holding it None, and the window counts bars, never hours."""
    totals = liquidation_grid_features(bucket_ts, long_usd, short_usd, union_ts, covered)["binperp_liq_lowerbound_total_usd"]
    return funding_zscore(totals, window=_LIQUIDATION_ZSCORE_WINDOW)
```

- [ ] **Step 4: Run them to verify they pass** — Step 2's command. Expected: `125 passed`; and `uv run pytest tests/test_alpha_b2.py -k "ratio_zscore or ratio_signal or ratio_max_signal or liquidation_zscore or ratio_and_liquidation_windows or zero_taker_ratio_is_scored or null_ratio_leaves" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` prints `11 passed, 114 deselected`.

- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b2.py tests/test_alpha_b2.py`; the Global Constraints' `T` over the two paths, run as they run it (measured on the transcription: `tests/test_alpha_b1_exit.py`, `tests/test_alpha_b2.py`, `tests/test_research_b1_hourly_exit_basis.py`, `tests/test_research_b1_volume_basis.py`, `tests/test_research_b2_basis.py`, `tests/test_research_b2_full_basis.py` and `tests/test_research_command.py`, `577 passed, 57 deselected` in 3 min 39 s); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.

- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the transcription, fourteen of fourteen):

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/        f"{name}_z30d": _rows_at_union_closes(/        name: _rows_at_union_closes(/' -- uv run pytest 'tests/test_alpha_b2.py::test_each_ratio_zscore_scores_its_own_columns_level_over_180_grid_marks' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)/    zscore = list/' -- uv run pytest 'tests/test_alpha_b2.py::test_each_ratio_zscore_scores_its_own_columns_level_over_180_grid_marks' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)/    zscore = partial(oi_zscore, window=_RATIO_ZSCORE_WINDOW)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_zero_taker_ratio_is_scored_where_an_oi_level_gate_would_refuse_it' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/oi_ts, name, values, union_ts)/oi_ts, name, [1.5 if v is None else v for v in values], union_ts)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_null_ratio_leaves_every_zscore_window_holding_its_mark_none' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation 's/^_RATIO_ZSCORE_WINDOW = 180/_RATIO_ZSCORE_WINDOW = 179/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_and_liquidation_windows_are_the_pre_registered_180_marks_and_bars' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation 's/^_LIQUIDATION_ZSCORE_WINDOW = 180/_LIQUIDATION_ZSCORE_WINDOW = 179/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_and_liquidation_windows_are_the_pre_registered_180_marks_and_bars' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)/    zscore = lambda v: funding_zscore(v[1:] + v[-1:], window=_RATIO_ZSCORE_WINDOW)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_zscores_bit_for_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/ else max(column\[k\] for column in columns)/ else min(column[k] for column in columns)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/None if any(column\[k\] is None for column in columns) else max(column\[k\] for column in columns)/None if all(column[k] is None for column in columns) else max(column[k] for column in columns if column[k] is not None)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/    if not z_columns:/    if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_ratio_max_signal_refuses_no_column_or_columns_of_unequal_length[no-column]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/    n = _check_lengths(z_columns)/    n = len(next(iter(z_columns.values())))/' -- uv run pytest 'tests/test_alpha_b2.py::test_ratio_max_signal_refuses_no_column_or_columns_of_unequal_length[unequal-length]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_zscore_grid_feature(/def liquidation_zscore_grid_feature_gone(/' --mutation '/^def liquidation_zscore_grid_feature(/,/^def /s/)\["binperp_liq_lowerbound_total_usd"\]$/)["binperp_liq_lowerbound_long_usd"]/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_liquidation_zscore_scores_each_bars_total_over_180_union_bars_never_one_leg' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_zscore_grid_feature(/def liquidation_zscore_grid_feature_gone(/' --mutation '/^def liquidation_zscore_grid_feature(/,/^def /s/    return funding_zscore(totals, window=_LIQUIDATION_ZSCORE_WINDOW)/    return funding_zscore([0.0 if v is None else v for v in totals], window=_LIQUIDATION_ZSCORE_WINDOW)/' -- uv run pytest 'tests/test_alpha_b2.py::test_an_uncovered_bar_leaves_every_liquidation_zscore_window_holding_it_none' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_zscore_grid_feature(/def liquidation_zscore_grid_feature_gone(/' --mutation '/^def liquidation_zscore_grid_feature(/,/^def /s/    return funding_zscore(totals, window=_LIQUIDATION_ZSCORE_WINDOW)/    return funding_zscore(totals[1:] + totals[-1:], window=_LIQUIDATION_ZSCORE_WINDOW)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_buckets_reproduces_the_liquidation_zscore_bit_for_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 7: Commit**

```bash
git commit -F - <<'EOF'
feat(alpha): the B2 ratio z-scores, their all-four maximum and the liquidation total's z-score over the union's bars

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 2 (the controller's): the frozen liquidations block, its attestation and its coverage proof (D7)

**Files:** create `/home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen/` (gitignored) and the link `data/liquidations-frozen` in this worktree; modify `docs/reference/vouched-dataset-hashes.jsonl` (eleven lines appended) and `docs/reference/data-catalog-full.md`; scratch `.tmp/plan-00138/freeze-read-1.json`, `.tmp/plan-00138/freeze.out`, `.tmp/plan-00138/freeze-check.out`.

**Interfaces:**
- Consumes: the live tree `/var/lib/zcrypto-ops/liquidations`, read-only — `<COIN>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet` finals, each beside `<HH>.parquet.sha256` whose first token is its bytes' sha256 (spec 00136's measured basis); `cli.ohlc.dataset.dataset_hash` and `write_parquet`; the sidecar's line shape (`dataset`, `dataset_sha256`, `first_ts`, `last_ts`, `relpath`, `rows`), which `cli/data/sync.py`'s `_sidecar_by_dataset` reads.
- Produces: the block — `<COIN>/buckets.parquet` for the ten coins and `covered-hours.parquet`, eleven files — and its eleven sidecar lines; `freeze.out` holding the coverage proof (D7): per coin its first and last final, the closed span and its holes, the asserted hours; `freeze-check.out` the second read.

- [ ] **Step 1: The gate** — each its own call: `git status --short` prints nothing; `test ! -e /home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen` and `test ! -e data/liquidations-frozen` each exit 0; `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/vouched-dataset-hashes.jsonl` exits 0, so develop has appended nothing to the sidecar since this branch's base.

- [ ] **Step 2: The freeze** — from this worktree's root, one call, about 15 s (measured on a transcription writing to scratch: 10 s):

```bash
mkdir -p .tmp/plan-00138 && uv run python - > .tmp/plan-00138/freeze.out 2>&1 <<'EOF'
import hashlib
import json
import math
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.ohlc.dataset import dataset_hash, write_parquet

LIVE = Path("/var/lib/zcrypto-ops/liquidations")
OUT = Path("/home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen")
SIDECAR = Path("docs/reference/vouched-dataset-hashes.jsonl")
READ = Path(".tmp/plan-00138/freeze-read-1.json")
COINS = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")
H = timedelta(hours=1)
FILE = re.compile(r"(\d{4})/(\d{2})/(\d{2})/(\d{2})\.(parquet|parquet\.sha256|.+)")
if OUT.exists():
    sys.exit(f"{OUT} exists: a freeze never writes over one")
if sorted(d.name for d in LIVE.iterdir() if d.is_dir()) != sorted(COINS):
    sys.exit("the live tree's coin directories are not the ten")
now = datetime.now(UTC)
closed_before = now.replace(minute=0, second=0, microsecond=0) - 31 * H
finals, digests, stray = {}, {}, []
for coin in COINS:
    tree = LIVE / coin / "liquidations-1m"
    finals[coin], digests[coin] = {}, {}
    for p in sorted(q for q in tree.rglob("*") if q.is_file()):
        m = FILE.fullmatch(p.relative_to(tree).as_posix())
        hour = datetime(*map(int, m.groups()[:4]), tzinfo=UTC) if m else None
        if hour is None or hour >= closed_before:
            if hour is None:
                stray.append(f"{coin}/{p.relative_to(tree)}")
            continue
        if m.group(5) == "parquet":
            manifest = p.with_name(p.name + ".sha256").read_text().split()[0]
            if hashlib.sha256(p.read_bytes()).hexdigest() != manifest:
                sys.exit(f"{coin}/{p.relative_to(tree)}: its bytes do not hash to its manifest")
            finals[coin][hour], digests[coin][hour.isoformat()] = p, manifest
        elif m.group(5) != "parquet.sha256":
            stray.append(f"{coin}/{p.relative_to(tree)}")
if stray:
    sys.exit(f"files neither a final nor its manifest, outside an hour or inside the closed span: {stray}")
held = set().union(*(set(f) for f in finals.values()))
first = min(held)
span = [first + k * H for k in range((closed_before - first) // H)]
holes = [h for h in span if h not in held]
asserted = [h for h in span[1:] if h in held]
written = {}
for coin in COINS:
    frame = pl.concat([pl.read_parquet(p).with_columns(pl.lit(h).alias("hour")) for h, p in sorted(finals[coin].items())]).sort("ts")
    stamps = frame["ts"].dt.epoch("s")
    legs = [*frame["long_usd"].to_list(), *frame["short_usd"].to_list()]
    faults = {
        "off the minute": int((stamps % 60 != 0).sum()),
        "outside its file's hour": int((frame["ts"].dt.truncate("1h") != frame["hour"]).sum()),
        "repeated stamps": frame.height - frame["ts"].n_unique(),
        "nulls": int(frame.null_count().sum_horizontal().item()),
        "non-finite or negative legs": sum(not math.isfinite(x) or x < 0 for x in legs),
        "symbol or event_id off form": int(
            ((frame["symbol"] != f"{coin}USDT_PERP.A") | (frame["event_id"] != frame["symbol"] + "-" + stamps.cast(pl.String))).sum()
        ),
    }
    if any(faults.values()):
        sys.exit(f"{coin}: {faults}")
    written[f"{coin}/buckets.parquet"] = frame.drop("hour")
written["covered-hours.parquet"] = pl.DataFrame({"ts": asserted}, schema={"ts": pl.Datetime("us", "UTC")})
lines = []
for relpath, frame in written.items():
    write_parquet(frame, OUT / relpath)
    back = pl.read_parquet(OUT / relpath)
    row = {
        "dataset": "liquidations-frozen",
        "dataset_sha256": dataset_hash(back),
        "first_ts": str(back["ts"][0]),
        "last_ts": str(back["ts"][-1]),
        "relpath": relpath,
        "rows": back.height,
    }
    lines.append(json.dumps(row))
with SIDECAR.open("a", encoding="utf-8") as sidecar:
    sidecar.write("".join(f"{line}\n" for line in lines))
READ.parent.mkdir(parents=True, exist_ok=True)
READ.write_text(json.dumps({"read_at": now.isoformat(), "closed_before": closed_before.isoformat(), "digests": digests}))
print(f"read at {now:%Y-%m-%dT%H:%M:%SZ}; closed span {span[0]:%Y-%m-%dT%HZ} -> {span[-1]:%Y-%m-%dT%HZ}, {len(span)} hours, holes {[f'{h:%Y-%m-%dT%HZ}' for h in holes]}")
print(f"asserted hours {len(asserted)}, {asserted[0]:%Y-%m-%dT%HZ} -> {asserted[-1]:%Y-%m-%dT%HZ}")
for coin in COINS:
    hours = sorted(finals[coin])
    print(f"{coin}: finals {len(hours)}, {hours[0]:%Y-%m-%dT%HZ} -> {hours[-1]:%Y-%m-%dT%HZ}, buckets {written[f'{coin}/buckets.parquet'].height}")
print("\n".join(lines))
EOF
echo "exit $?"; cat .tmp/plan-00138/freeze.out
```

  Exit 0 prints the read's time, the closed span and its holes, the asserted hours, each coin's finals, first and last, and buckets, and the eleven sidecar lines it appended. Any `sys.exit` — a target that exists, a coin directory missing, a final whose bytes miss its manifest, a stray file in the span, a bucket fault — wrote nothing, and is the owner's question with its line quoted.

- [ ] **Step 3: The second read** — at least 300 s after step 2's read, as its own background call, acted on at its notification:

```bash
uv run python - > .tmp/plan-00138/freeze-check.out 2>&1 <<'EOF'
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

LIVE = Path("/var/lib/zcrypto-ops/liquidations")
READ = Path(".tmp/plan-00138/freeze-read-1.json")
first = json.loads(READ.read_text())
closed_before = datetime.fromisoformat(first["closed_before"])
elapsed = (datetime.now(UTC) - datetime.fromisoformat(first["read_at"])).total_seconds()
if elapsed < 300:
    sys.exit(f"{elapsed:.0f} s since the first read: the second waits a poll cycle, 300 s")
now = {}
for coin in first["digests"]:
    tree = LIVE / coin / "liquidations-1m"
    now[coin] = {}
    for p in tree.rglob("*.parquet.sha256"):
        y, m, d, h = (int(x) for x in [*p.relative_to(tree).parts[:3], p.name.split(".")[0]])
        hour = datetime(y, m, d, h, tzinfo=UTC)
        if hour < closed_before:
            now[coin][hour.isoformat()] = p.read_text().split()[0]
if now != first["digests"]:
    changed = {coin: sorted(set(now[coin].items()) ^ set(first["digests"][coin].items())) for coin in now if now[coin] != first["digests"][coin]}
    sys.exit(f"the live tree's closed span changed since the copy: {changed}")
print(f"{elapsed:.0f} s after the copy, the live tree's closed span holds the same {sum(map(len, now.values()))} finals and manifests")
EOF
echo "exit $?"; cat .tmp/plan-00138/freeze-check.out
```

  Exit 0 prints that the closed span's finals and manifests are unchanged since the copy. An exit on the 300 s floor is re-run later. An exit on a changed span means a final reached the span after the copy: `rm -r /home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen` (the block this task wrote, no other) and `git checkout -- docs/reference/vouched-dataset-hashes.jsonl`, each its own call, then steps 2 and 3 once more; a second change is the owner's question.

- [ ] **Step 4: Link and read back** — `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen data/liquidations-frozen` (`-n`, so an existing link is refused, never followed); then `uv run python -c 'from pathlib import Path; from cli.registry.observed import ObservedReader; r = ObservedReader(Path("data")); [r.read_series("liquidations-frozen", p) for p in ["covered-hours.parquet", *(f"{c}/buckets.parquet" for c in ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"))]]; print(r.vouched_status(), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in r.block().items()})'` prints `{'liquidations-frozen': 'checked (11 vouched hashes)'}` and the eleven files.

- [ ] **Step 5: The catalog entry** — in `docs/reference/data-catalog-full.md`, after the `### Binance liquidations, 1-minute buckets` section and before `## private`, one line per paragraph and list item, the bracketed values read off `freeze.out`:

```markdown
### Binance liquidations, frozen block (`data/liquidations-frozen/`, the live tape's closed span to <the last asserted hour>; written once)

- **Producer:** the freeze of spec/plan `00138` (D7, Task 2): one read-only copy of the live tree's (coin, hour) finals of every hour starting 31 h or more before its read at <the read's time>, each final's bytes checked against its manifest, every bucket checked, the tree read again a poll cycle later and found unchanged over that span.
- **Schema:** `<COIN>/buckets.parquet` — the coin's closed-span finals concatenated in stamp order, the live schema `ts, symbol, long_usd, short_usd, event_id`; `covered-hours.parquet` — one `ts` column, the hours asserted covered for every coin: each hour of the closed span but its first, partial one that some coin's final holds (<n> hours, <first> → <last>).
- **Attestation:** eleven path-bound lines in `docs/reference/vouched-dataset-hashes.jsonl`, each file's `dataset_hash`, which `ObservedReader` checks on every read; no manifest. Never rewritten: a re-freeze is a new name under a new spec.
- **Caveats:** the live stream's lower bound, and the coverage assertion's own (spec `00138` D7): a coin reads low at a bar where a poll raised on its entry in every cycle that fetched the hour, or where a sweep was skipped past 31 h. Local to this workstation's data root; not on the hub.
- **Consumers:** `b2-liq-derisk` and its pre-flight (spec `00138` D6); on `ohlc-full` no union bar reaches it.
```

- [ ] **Step 6: Gate** — `git add docs/reference/vouched-dataset-hashes.jsonl docs/reference/data-catalog-full.md`; `T` over the two paths (`tests/test_data_vouched_sidecar.py` and `tests/test_manifest_conformance.py`, measured on the transcription with the eleven lines a trial freeze into scratch wrote: `18 passed, 5 deselected`); `uv run pre-commit run -a` until clean.

- [ ] **Step 7: Commit**

```bash
git commit -F - <<'EOF'
feat(data): the frozen liquidations block — the live tape's closed span in eleven files, attested in the sidecar and catalogued

<freeze.out, whole>
<freeze-check.out, whole>
<step 4's read-back line>
<the gate's pytest result line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 3: the six subjects — three trials and their pre-flight twins (D8, D9)

**Files:**
- Modify: `cli/research/subjects.py` — the `from cli.alpha.b2 import (` block; the overlay machinery after `_B2_FULL_PREFLIGHT_KEYS` and before `SUBJECTS`; six entries at the end of `SUBJECTS`
- Modify: `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`

**Interfaces:**
- Consumes: Task 1's three functions; `cli/research/subjects.py` as `a9c8be5d1` holds it — `_capturing_union`, `_b2_over`, `_b2_returns`, `_b2_slices`, `_b2_full_metrics(inputs)`, `_B2Inputs`, `_B2_METRIC_KEYS`, `_B2_FULL_PREFLIGHT_KEYS`, `_B2_ARM_A_BAR_KEYS`, `_B2_ARM_A_BAR_FLAGS`, `_B2_COST_PER_SIDE`, `_B2_A2_ARMS`, `_B2_LOOKBACK`, `_DECISIVE_START`, `_N_RESAMPLES`, `_FROM_2021`, `_B2_FULL_N_TRIALS`, `_ASSETS`, `PPY_4H`, `SubjectError`, `Subject`, and the names it imports (`a1_kill_bar`, `net_of_cost_verdict`, `net_of_cost`, `scale_positions`, `derisk_scales`, `B2Config`, `benchmark_4h_net_of_cost`, `calendar_year_slices`, `per_year_engaged_counts`, `per_year_positions_differ`, `per_year_turnover`, `per_year_max_drawdown`, `book_turnover`, `coverage_by_year`, `close_grid`, `max_drawdown`, `sharpe`, `a2_book_returns`, `A2Config`, `_ffill_btc`, `statistics`, `PERP_SYMBOLS`, `pl`), each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; `cli/research/command.py`'s `eval_subject` (spec 00133: a plain eval of a ruled subject refused before any read, `--n-trials` other than `Subject.n_trials` refused, a count below `required_n` refused, a dirty tree refused under `--register`); in the tests, `_anchor`, `_as_trial`, `_rolling_set`, `_recording`, `_block_and_metrics`, `_b2_ohlc_rows`, `_fake_kill_bar`, `_fake_benchmark`, `_fake_head_to_head`, `_B2_START`, `_B2_BARS`, `_B2_FALLS`, `_B2_FUNDING_FROM`, `_B2_NEVER_SPIKES`, `_B2_SPOILT`, `_B2_ASSETS`, `_B2_METRIC_KEYS`, `_B2_FULL_PREFLIGHT_KEYS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`.
- Produces:

```python
# cli/research/subjects.py
_B2_OI_N_TRIALS = 2; _B2_RATIO_N_TRIALS = 3; _B2_LIQ_N_TRIALS = 4
_B2_OI_THRESHOLD = 2.5; _B2_RATIO_THRESHOLD = 2.5; _B2_LIQ_THRESHOLD = 2.0
_B2_LIQ_SET = "liquidations-frozen"
class _B2OverlayInputs(NamedTuple): h4_ts, h4_prices, close, arm_a, signal, scales
def _b2_oi_signal(reader, h4_ts) -> dict[str, list[float | None]]: ...
def _b2_ratio_signal(reader, h4_ts) -> dict[str, list[float | None]]: ...
def _b2_liq_signal(reader, h4_ts) -> dict[str, list[float | None]]: ...
def _b2_overlay_inputs(subject, read_signal, threshold, reader, dataset, window, accept_holes) -> _B2OverlayInputs: ...
def _b2_overlay_start(inputs) -> int: ...
def _b2_overlay_arm_a_bar(inputs, *, n_trials) -> tuple[dict, list[float], list[float]]: ...
def _b2_overlay_engagement(inputs, signal_key) -> dict: ...
def _b2_overlay_metrics(inputs, *, signal_key, n_trials) -> dict: ...  # 41 keys
def _b2_overlay_preflight_metrics(inputs, *, signal_key, n_trials) -> dict: ...  # 21 keys
def _b2_overlay_build(subject, signal_key, read_signal, threshold, compute, n_trials, reader, dataset, window, as_of, accept_holes) -> dict: ...
def _build_b2_oi_derisk(...), _build_b2_oi_derisk_preflight(...), _build_b2_ratio_derisk(...), _build_b2_ratio_derisk_preflight(...), _build_b2_liq_derisk(...), _build_b2_liq_derisk_preflight(...) -> dict
def _b2_overlay_verdict(m: dict) -> str | None: ...
def _b2_overlay_metric_keys(signal_key: str) -> frozenset[str]: ...
def _b2_overlay_preflight_keys(signal_key: str) -> frozenset[str]: ...
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - the `from cli.alpha.b2 import (` block gains `liquidation_zscore_grid_feature,` after `derisk_scales,`, `oi_zscore_grid_feature,` after `net_of_cost,`, and `ratio_max_signal,` and `ratio_zscore_grid_features,` after `per_year_turnover,`;
  - `from cli.data import sync` goes after `from cli.benchmark.errors import BenchmarkError`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` ends with:

```python
    for name, (signal_key, _, _) in _B2_OVERLAYS.items():
        assert subjects.SUBJECTS[name].metric_keys == _overlay_metric_keys(signal_key)
        assert subjects.SUBJECTS[f"{name}-preflight"].metric_keys == _overlay_preflight_keys(signal_key)
```

  - after `test_the_b2_full_subject_refuses_a_funding_file_it_cannot_read_naming_it` and before the comment `# Records 45 and 46's metric keys (docs/specs/00130 D3), pinned against the committed records below.`:

```python
_B2_OVERLAY_SPEC = "docs/specs/00138-b2-three-overlays-design.md"
_B2_OVERLAY_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"
)
# Spec 00138's three trials: each signal's key, threshold and count, typed from the spec, never read off a subject.
_B2_OVERLAYS = {
    "b2-oi-derisk": ("binperp_oi_z30d", 2.5, 2),
    "b2-ratio-derisk": ("binperp_ratio_max_z30d", 2.5, 3),
    "b2-liq-derisk": ("binperp_liq_total_z30d", 2.0, 4),
}
_B2_OVERLAY_RATIOS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
_B2_OVERLAY_FROM_BAR = 300
_B2_OVERLAY_SPIKE_BARS = 12


def _overlay_metric_keys(signal_key: str) -> frozenset[str]:
    moved = {"head_to_head_mean_outperf_2021", "head_to_head_spa_p_2021", "binperp_funding_z30d_coverage"}
    return frozenset(_B2_METRIC_KEYS - moved) | {
        "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_primary",
        "primary_returns",
        f"{signal_key}_coverage",
    }


def _overlay_preflight_keys(signal_key: str) -> frozenset[str]:
    return (_B2_FULL_PREFLIGHT_KEYS - {"binperp_funding_z30d_coverage"}) | {"primary_returns", f"{signal_key}_coverage"}


def _overlay_signal(name: str):
    return {
        "b2-oi-derisk": subjects._b2_oi_signal,
        "b2-ratio-derisk": subjects._b2_ratio_signal,
        "b2-liq-derisk": subjects._b2_liq_signal,
    }[name]


@pytest.fixture(autouse=True)
def _liquidations_block_unattested(monkeypatch):
    """The committed sidecar attests the frozen block by its set's name, so a fixture's synthetic `liquidations-frozen`
    would be refused as the block changed: the read guard stays as inert over it as over every other fixture set, and the
    data-gated basis test reads the attested block itself."""
    attested = sync._sidecar_by_dataset()
    monkeypatch.setattr(
        sync, "_sidecar_by_dataset", lambda: {name: s for name, s in attested.items() if name != "liquidations-frozen"}
    )


def _b2_overlay_dataset(
    tmp_path: Path, *, start: datetime = _B2_START, flat: bool = False, from_bar: int = _B2_OVERLAY_FROM_BAR
) -> Path:
    """`_b2_dataset`'s ten 4h series, a `derivatives-oi` set and a liquidations block, each running 30 days past the
    union: BTC's OI rows open 47 days before it, every other asset's and the liquidations' covered hours at bar
    `from_bar`; every asset but one spikes in its OI level, one of its four ratios and its long notional for twelve bars
    inside the second fall, each from its own bar, so each overlay de-risks each asset at its own stamps."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        write_parquet(to_frame(_b2_ohlc_rows(i * 0.7, start, flat)), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    opens, end = start + timedelta(hours=4 * from_bar), start + timedelta(hours=4 * _B2_BARS, days=30)
    hours = [opens + timedelta(hours=h) for h in range((end - opens) // timedelta(hours=1))]
    write_parquet(
        pl.DataFrame({"ts": hours}, schema={"ts": pl.Datetime("us", "UTC")}), root / "liquidations-frozen" / "covered-hours.parquet"
    )
    for i, asset in enumerate(_B2_ASSETS):
        spike = start + timedelta(hours=4 * (_B2_FALLS[1][0] + 2 * i))

        def hot(t: datetime) -> bool:
            return asset != _B2_NEVER_SPIKES and spike <= t < spike + timedelta(hours=4 * _B2_OVERLAY_SPIKE_BARS)

        first = _B2_FUNDING_FROM if asset == "BTC" else opens
        marks = [first + timedelta(hours=4 * j) for j in range((end - first) // timedelta(hours=4))]
        columns = {
            "ts": marks,
            "sum_open_interest": [2_000.0 if hot(t) else 1_000.0 + 10 * math.sin(j / 3 + i) for j, t in enumerate(marks)],
            "sum_open_interest_value": [1e7] * len(marks),
        }
        for c, ratio in enumerate(_B2_OVERLAY_RATIOS):
            columns[ratio] = [3.0 if hot(t) and c == i % 4 else 1.0 + 0.05 * math.sin(j / 5 + i + c) for j, t in enumerate(marks)]
        schema = {"ts": pl.Datetime("us", "UTC")} | dict.fromkeys(list(columns)[1:], pl.Float64)
        write_parquet(pl.DataFrame(columns, schema=schema), root / "derivatives-oi" / PERP_SYMBOLS[asset] / "oi.parquet")
        stamps = [t + timedelta(minutes=1) for t in hours]
        buckets = {
            "ts": stamps,
            "symbol": [f"{asset}USDT_PERP.A"] * len(stamps),
            "long_usd": [1e5 if hot(t) else 100.0 + 50 * math.sin(k / 7 + i) for k, t in enumerate(hours)],
            "short_usd": [80.0 + 40 * math.cos(k / 5 + i) for k in range(len(hours))],
            "event_id": [f"{asset}USDT_PERP.A-{int(t.timestamp())}" for t in stamps],
        }
        schema = {
            "ts": pl.Datetime("us", "UTC"),
            "symbol": pl.String,
            "long_usd": pl.Float64,
            "short_usd": pl.Float64,
            "event_id": pl.String,
        }
        write_parquet(pl.DataFrame(buckets, schema=schema), root / "liquidations-frozen" / asset / "buckets.parquet")
    return root


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    signal_key, _, count = _B2_OVERLAYS[name]
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    builder = f"_build_{name.replace('-', '_')}"
    assert (len(_overlay_metric_keys(signal_key)), len(_overlay_preflight_keys(signal_key))) == (41, 21)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B2_OVERLAY_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is getattr(subjects, builder) and trial.metric_keys == _overlay_metric_keys(signal_key)
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_overlay_verdict, _B2_OVERLAY_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", count)
    assert (preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == ((240,), _B2_ASSETS, _B2_OVERLAY_SPEC, (42,))
    assert preflight.build is getattr(subjects, f"{builder}_preflight")
    assert preflight.metric_keys == _overlay_preflight_keys(signal_key)
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


# Adopting on every key the rule reads, the full-window head-to-head and the block-102 cell set against the verdict, so a
# rule reading either in place of the primary read or the headline cell moves the first row.
_B2_OVERLAY_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2013": 0, "2023": 4},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "spa_p_decisive_b102_s42": 0.9,
    "max_drawdown_reduction_pct": 5.0,
}
_B2_OVERLAY_NEVER_ENGAGED = {"engaged_per_year": {"2013": 0, "2023": 0}}


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-outperforms-significantly-from-the-start-and-draws-down-less"),
        pytest.param({"head_to_head_spa_p_primary": 0.0499}, "adopt", id="row-1-p-at-0.0499"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6}, "adopt", id="row-1-reduction-past-1e-6"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="row-2-outperforms-insignificantly-from-the-start"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="row-2-p-at-exactly-0.05"),
        pytest.param({"head_to_head_mean_outperf_primary": -0.001}, "reject", id="row-3-underperforms-from-the-start"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="row-3-mean-at-exactly-0"),
        pytest.param({"max_drawdown_reduction_pct": -5.0}, "reject", id="row-3-draws-down-more"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="row-3-reduction-at-exactly-1e-6"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001, "head_to_head_spa_p_full": 0.01},
            "reject",
            id="row-3-outperforms-over-the-full-window-alone",
        ),
        pytest.param({"passes": 0}, "reject", id="row-4-arm-b-fails-its-bar"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_OVERLAY_NEVER_ENGAGED, None, id="the-overlay-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_OVERLAY_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
    ],
)
def test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b2_overlay_verdict({**_B2_OVERLAY_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count(tmp_path, monkeypatch, name):
    signal_key, threshold, count = _B2_OVERLAYS[name]
    scalings = _recording(monkeypatch, "derisk_scales", lambda arguments, result: result)
    reader = ObservedReader(_b2_overlay_dataset(tmp_path))
    inputs = subjects._b2_overlay_inputs(name, _overlay_signal(name), threshold, reader, "ohlc-test", None, False)
    start = next(k for k in range(len(inputs.close)) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS))
    assert 0 < start < len(inputs.close) - 2
    assert [(arguments["z_by_asset"], arguments["config"]) for arguments, _ in scalings] == [
        (inputs.signal, B2Config(z_threshold=threshold))
    ]
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b2_overlay_metrics(inputs, signal_key=signal_key, n_trials=count)

    assert set(metrics) == _overlay_metric_keys(signal_key) and {arguments["n_trials"] for arguments, _ in bars} == {count}
    # Trial 2's metrics over the same positions and signal, its from-2021 read moved to this signal's start and its count to
    # this trial's: `_b2_full_metrics`' own test proves it against a hand computation.
    monkeypatch.setattr(subjects, "_FROM_2021", inputs.close[start])
    monkeypatch.setattr(subjects, "_B2_FULL_N_TRIALS", count)
    trial_2 = subjects._b2_full_metrics(subjects._B2Inputs(*inputs))
    renamed = {
        "head_to_head_mean_outperf_2021": "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_2021": "head_to_head_spa_p_primary",
        "binperp_funding_z30d_coverage": f"{signal_key}_coverage",
    }
    assert {renamed.get(key, key): value for key, value in trial_2.items()} | {
        "primary_returns": len(inputs.close) - start
    } == metrics


def test_where_no_signal_crosses_its_threshold_a_b2_overlays_arm_b_is_arm_a_bit_for_bit(tmp_path, monkeypatch):
    reader = ObservedReader(_b2_overlay_dataset(tmp_path))
    inputs = subjects._b2_overlay_inputs("b2-oi-derisk", subjects._b2_oi_signal, 2.5, reader, "ohlc-test", None, False)
    calm = {a: [0.0] * len(inputs.close) for a in _B2_ASSETS}
    inputs = inputs._replace(signal=calm, scales=derisk_scales(calm, config=B2Config(z_threshold=2.5)))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b2_overlay_metrics(inputs, signal_key="binperp_oi_z30d", n_trials=2)

    assert [arguments["book_net_of_cost"] == arguments["benchmark_net_of_cost"] for arguments, _ in head_to_heads] == [True] * 2
    assert (
        metrics["stamps_positions_differ"],
        metrics["turnover_b"],
        metrics["max_drawdown"],
        metrics["max_drawdown_reduction_pct"],
    ) == (
        0,
        metrics["turnover_a"],
        metrics["arm_a_max_drawdown"],
        0.0,
    )
    assert metrics["primary_returns"] == len(inputs.close) and set(metrics["engaged_per_year"].values()) == {0}


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b(tmp_path, monkeypatch, name):
    signal_key, threshold, count = _B2_OVERLAYS[name]
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    def arm_b(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions")

    monkeypatch.setattr(subjects, "scale_positions", arm_b)
    reads = _recording(monkeypatch, "_b2_overlay_inputs", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS[f"{name}-preflight"].build(ObservedReader(_b2_overlay_dataset(tmp_path)), "ohlc-test", None)

    ((read, inputs),) = reads
    assert (read["subject"], read["read_signal"], read["threshold"]) == (f"{name}-preflight", _overlay_signal(name), threshold)
    returns = {a: _asset_returns(_ffill_btc(inputs.h4_prices)[a]) for a in _B2_ASSETS}
    net_a, net_a_x15 = (net_of_cost(inputs.arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.close)
    start = next((k for k in range(n) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS)), n)
    ((arguments, bar),) = bars
    assert arguments == {
        "book_net_returns": net_a,
        "benchmark_net_returns": bench,
        "n_trials": count,
        "var_trials": 0.0,
        "mean_block": 30,
        "seed": 42,
        "cost_stressed_returns": net_a_x15,
        "regime_slices": calendar_year_slices(net_a, inputs.h4_ts),
        "benchmark_slices": calendar_year_slices(bench, inputs.h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    engaged = {a: sum(p > 0 and s < 1 for p, s in zip(inputs.arm_a[a], inputs.scales[a])) for a in _B2_ASSETS}
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        "engaged_per_asset": engaged,
        "engaged_per_year": per_year_engaged_counts(inputs.arm_a, inputs.scales, inputs.close),
        f"{signal_key}_coverage": {
            a: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(inputs.close, inputs.signal[a]).items()}
            for a in _B2_ASSETS
        },
        "primary_returns": n - start,
    }
    assert set(metrics) == _overlay_preflight_keys(signal_key) and 0 < start < n - 2
    assert sum(engaged.values()) == sum(metrics["engaged_per_year"].values()) > 0
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0


def test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero(tmp_path, monkeypatch):
    # The liquidations block opening where the union ends, as the frozen block opens after ohlc-full's last close.
    root = _b2_overlay_dataset(tmp_path, from_bar=_B2_BARS)
    _anchor(monkeypatch, root)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-liq-derisk-preflight", "--dataset", "ohlc-test"])

    assert result.exit_code == 0, result.output
    metrics = _block_and_metrics(result.output)["metrics"]
    assert (metrics["primary_returns"], set(metrics["engaged_per_year"].values()), set(metrics["engaged_per_asset"].values())) == (
        0,
        {0},
        {0},
    )
    assert {count for years in metrics["binperp_liq_total_z30d_coverage"].values() for count, _ in years.values()} == {0}


@pytest.mark.parametrize("name", sorted({*_B2_OVERLAYS, *(f"{name}-preflight" for name in _B2_OVERLAYS)}))
def test_a_b2_overlay_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, [*args, *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"{name} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen "
        "--dataset"
    ) in result.output


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    count = _B2_OVERLAYS[name][2]
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_overlay_inputs", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-182", "--family", "B2", "--n-trials", str(count + 1)]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials {count + 1} is not {count}, the count {name} declares and deflates at: pass --n-trials {count}"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.parametrize(
    ("name", "from_bar", "cause"),
    [
        pytest.param(
            "b2-oi-derisk",
            1_460,
            "1 of its return indices carry every asset's binperp_oi_z30d, and the head-to-head from the signal's own start needs 2",
            id="oi-one-index-from-the-start",
        ),
        pytest.param(
            "b2-liq-derisk",
            1_460,
            "0 of its return indices carry every asset's binperp_liq_total_z30d, and the head-to-head from the signal's own "
            "start needs 2",
            id="liquidations-no-index-from-the-start",
        ),
        pytest.param(
            "b2-oi-derisk",
            1_459,
            "arm A never draws down from the signal's own start, so max_drawdown_reduction_pct divides by zero",
            id="oi-arm-a-never-draws-down-from-the-start",
        ),
    ],
)
def test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar(tmp_path, monkeypatch, name, from_bar, cause):
    _anchor(monkeypatch, _b2_overlay_dataset(tmp_path, from_bar=from_bar))
    kill_bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the full history: {cause}" in result.output
    assert kill_bars == []


def _not_parquet(path: Path) -> None:
    path.write_bytes(b"not a parquet file")


@pytest.mark.parametrize(
    ("name", "relpath", "spoil", "cause"),
    [
        pytest.param("b2-oi-derisk", f"derivatives-oi/{_B2_SPOILT}/oi.parquet", _not_parquet, "File out of specification", id="oi"),
        pytest.param(
            "b2-ratio-derisk-preflight",
            f"derivatives-oi/{_B2_SPOILT}/oi.parquet",
            lambda path: pl.read_parquet(path).drop("count_long_short_ratio").write_parquet(path),
            '"count_long_short_ratio" not found',
            id="ratio",
        ),
        pytest.param(
            "b2-liq-derisk",
            "liquidations-frozen/SOL/buckets.parquet",
            lambda path: pl.read_parquet(path).drop("long_usd").write_parquet(path),
            '"long_usd" not found',
            id="liquidation-buckets",
        ),
        pytest.param(
            "b2-liq-derisk-preflight",
            "liquidations-frozen/covered-hours.parquet",
            _not_parquet,
            "File out of specification",
            id="covered-hours",
        ),
    ],
)
def test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it(
    tmp_path, monkeypatch, name, relpath, spoil, cause
):
    root = _b2_overlay_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_each_b2_overlay_reads_its_signal_off_its_own_columns(tmp_path, name):
    root = _b2_overlay_dataset(tmp_path)
    h4_ts, _ = subjects._capturing_union(ObservedReader(root), "ohlc-test", 240, None, None, False)
    covered = pl.read_parquet(root / "liquidations-frozen" / "covered-hours.parquet")["ts"].to_list()
    expected = {}
    for asset in _B2_ASSETS:
        oi = pl.read_parquet(root / "derivatives-oi" / PERP_SYMBOLS[asset] / "oi.parquet")
        buckets = pl.read_parquet(root / "liquidations-frozen" / asset / "buckets.parquet")
        if name == "b2-oi-derisk":
            expected[asset] = oi_zscore_grid_feature(oi["ts"].to_list(), oi["sum_open_interest"].to_list(), h4_ts)
        elif name == "b2-ratio-derisk":
            ratios = {column: oi[column].to_list() for column in _B2_OVERLAY_RATIOS}
            expected[asset] = ratio_max_signal(ratio_zscore_grid_features(oi["ts"].to_list(), ratios, h4_ts))
        else:
            columns = (buckets["ts"].to_list(), buckets["long_usd"].to_list(), buckets["short_usd"].to_list())
            expected[asset] = liquidation_zscore_grid_feature(*columns, h4_ts, covered)

    signal = _overlay_signal(name)(ObservedReader(root), h4_ts)

    assert signal == expected
    assert sum(v is not None and v > _B2_OVERLAYS[name][1] for v in signal["BTC"]) > 0
```

  - `_RULED_FIXTURES` gains, after `"b2-funding-derisk-full": _b2_dataset,`:

```python
    "b2-liq-derisk": _b2_overlay_dataset,
    "b2-oi-derisk": _b2_overlay_dataset,
    "b2-ratio-derisk": _b2_overlay_dataset,
```

  - `_DECLARED_COUNT` gains, after `"b2-funding-derisk-full": "_B2_FULL_N_TRIALS",`:

```python
    "b2-liq-derisk": "_B2_LIQ_N_TRIALS",
    "b2-oi-derisk": "_B2_OI_N_TRIALS",
    "b2-ratio-derisk": "_B2_RATIO_N_TRIALS",
```

  - the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains, after `"b2-funding-derisk-full": ("B2", 1),`:

```python
        "b2-liq-derisk": ("B2", 4),
        "b2-oi-derisk": ("B2", 2),
        "b2-ratio-derisk": ("B2", 3),
```

  - `_CONTRACT_DATASETS` gains, after its `"b2-funding-derisk-full-preflight"` entry:

```python
    "b2-oi-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-oi-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-ratio-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-ratio-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
```

  **Author's call** — the wiring test proves `_b2_overlay_metrics` against `_b2_full_metrics` itself, run on the same positions and signal with `_FROM_2021` moved to the signal's start and `_B2_FULL_N_TRIALS` to the subject's count, under argument-derived stand-ins for the bars, the benchmark and the head-to-heads: equal dicts, keys renamed, prove D9's "trial 2's body with the start in `k21`'s place", `_b2_full_metrics`' own test proving that body, while the recorded `derisk_scales` call proves the threshold reaches the scales; the fixture `_b2_overlay_dataset` writes every set all three overlays read, BTC's rows opening before the union and every other asset's at bar 300, as the real panel opens, so each signal's start falls inside the union and BTC engages before it; the autouse `_liquidations_block_unattested` drops the committed sidecar's attestation of `liquidations-frozen` inside this module alone — the sidecar binds a set by its name, so Task 2's lines would refuse every fixture's synthetic block, and the data-gated basis test reads the attested block itself, while `tests/test_registry_replay.py` imports none of it; the start refusals ride `from_bar` 1,460 and 1,459, measured on the transcription to leave the OI signal 1 and 2 return indices and the liquidations' none.

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00138 && uv run pytest tests/test_research_command.py -k "b2_overlay or b2-oi-derisk or b2-ratio-derisk or b2-liq-derisk or ruled_subjects or declares_the_metric_keys" -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`
Expected: `53 failed, 458 deselected` (measured on the transcription): the 48 new cases, the families and metric-keys tests and the count-tie rows of the three trials, each on what Step 3 adds; the six subjects' rows of the contract, tracked-spec and shared-defaults tests are not collected until `SUBJECTS` holds them

- [ ] **Step 3: Implement in `cli/research/subjects.py`** — the `from cli.alpha.b2 import (` block gains `liquidation_zscore_grid_feature,` after `funding_grid_feature,`, `oi_zscore_grid_feature,` after `net_of_cost,`, and `ratio_max_signal,` and `ratio_zscore_grid_features,` after `per_year_turnover,`; after `_B2_FULL_PREFLIGHT_KEYS`' closing `}` and before `SUBJECTS: dict[str, Subject] = {`:

```python
# docs/specs/00138 D3-D10: B2's trials 3-5, spec 00128's half-scale de-risk on three signals of their own, each on a frozen
# set's full history with trial 2's bars, the head-to-head read from the first close every asset's signal is defined.
_B2_OI_N_TRIALS = 2  # docs/specs/00138 D8: each count fixed by the spec's hash; a different one is a new subject
_B2_RATIO_N_TRIALS = 3
_B2_LIQ_N_TRIALS = 4
_B2_OI_THRESHOLD = 2.5
_B2_RATIO_THRESHOLD = 2.5
_B2_LIQ_THRESHOLD = 2.0
_B2_LIQ_SET = "liquidations-frozen"
_B2_RATIO_COLUMNS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


class _B2OverlayInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    arm_a: dict[str, list[float]]
    signal: dict[str, list[float | None]]
    scales: dict[str, list[float]]


def _b2_oi_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    signal = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/oi.parquet"
        try:
            rows = reader.read_series("derivatives-oi", relpath)
            signal[asset] = oi_zscore_grid_feature(rows["ts"].to_list(), rows["sum_open_interest"].to_list(), h4_ts)
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-oi/{relpath}: {exc}") from exc
    return signal


def _b2_ratio_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    signal = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/oi.parquet"
        try:
            rows = reader.read_series("derivatives-oi", relpath)
            ratios = {column: rows[column].to_list() for column in _B2_RATIO_COLUMNS}
            signal[asset] = ratio_max_signal(ratio_zscore_grid_features(rows["ts"].to_list(), ratios, h4_ts))
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-oi/{relpath}: {exc}") from exc
    return signal


def _b2_liq_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    """The hours the freeze asserts covered are every coin's (docs/specs/00138 D6, D7)."""
    try:
        covered = reader.read_series(_B2_LIQ_SET, "covered-hours.parquet")["ts"].to_list()
    except pl.exceptions.PolarsError as exc:
        raise SubjectError(f"{_B2_LIQ_SET}/covered-hours.parquet: {exc}") from exc
    signal = {}
    for asset in _ASSETS:
        relpath = f"{asset}/buckets.parquet"
        try:
            rows = reader.read_series(_B2_LIQ_SET, relpath)
            columns = (rows["ts"].to_list(), rows["long_usd"].to_list(), rows["short_usd"].to_list())
            signal[asset] = liquidation_zscore_grid_feature(*columns, h4_ts, covered)
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"{_B2_LIQ_SET}/{relpath}: {exc}") from exc
    return signal


def _b2_overlay_inputs(
    subject: str,
    read_signal: Callable[[ObservedReader, list[datetime]], dict[str, list[float | None]]],
    threshold: float,
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    accept_holes: bool,
) -> _B2OverlayInputs:
    """Arm A's positions, the signal and its scales, and no return of arm B: the pre-flight reads this half alone."""
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, None, accept_holes)
    close = close_grid(h4_ts)
    if len(close) < _DECISIVE_START + 2:
        raise SubjectError(
            f"{_b2_over(subject, window)}: it holds {len(close)} return indices, and the kill bar's decisive window opens at index "
            f"{_DECISIVE_START} and needs 2"
        )
    if not calendar_year_slices([0.0] * len(close), h4_ts):
        raise SubjectError(
            f"{_b2_over(subject, window)}: none of its return indices closes in a calendar year the worst-slice leg reads, the "
            "stub years left out"
        )
    signal = read_signal(reader, h4_ts)
    # `_b2_inputs`' arm A, built here because that half also reads the funding set.
    fed = _ffill_btc(h4_prices)
    arms = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_B2_LOOKBACK,
                basket_lookback=_B2_LOOKBACK,
                periods_per_year=PPY_4H,
            ),
        )["asset_positions"]
        for lookbacks, target_vol in _B2_A2_ARMS
    ]
    arm_a = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(len(h4_ts) - 1)] for a in _ASSETS}
    return _B2OverlayInputs(h4_ts, h4_prices, close, arm_a, signal, derisk_scales(signal, config=B2Config(z_threshold=threshold)))


def _b2_overlay_start(inputs: _B2OverlayInputs) -> int:
    """The first return index at which every asset's signal is defined, the length when none is (docs/specs/00138 D8)."""
    signal = inputs.signal
    return next((k for k in range(len(inputs.close)) if all(signal[a][k] is not None for a in _ASSETS)), len(inputs.close))


def _b2_overlay_arm_a_bar(inputs: _B2OverlayInputs, *, n_trials: int) -> tuple[dict, list[float], list[float]]:
    cost = _B2_COST_PER_SIDE
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(inputs.arm_a, returns, cost_per_side=cost)
    net_a_x15 = net_of_cost(inputs.arm_a, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    bar = a1_kill_bar(
        net_a,
        bench,
        n_trials=n_trials,
        var_trials=0.0,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_a_x15,
        regime_slices=calendar_year_slices(net_a, inputs.h4_ts),
        benchmark_slices=calendar_year_slices(bench, inputs.h4_ts),
        decisive_start=_DECISIVE_START,
        n_resamples=_N_RESAMPLES,
    )
    return bar, net_a, bench


def _b2_overlay_engagement(inputs: _B2OverlayInputs, signal_key: str) -> dict:
    arm_a, scales, close = inputs.arm_a, inputs.scales, inputs.close
    return {
        "engaged_per_asset": {a: sum(p > 0 and s < 1 for p, s in zip(arm_a[a], scales[a])) for a in _ASSETS},
        "engaged_per_year": per_year_engaged_counts(arm_a, scales, close),
        f"{signal_key}_coverage": {
            asset: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(close, values).items()}
            for asset, values in inputs.signal.items()
        },
        "primary_returns": len(close) - _b2_overlay_start(inputs),
    }


def _b2_overlay_metrics(inputs: _B2OverlayInputs, *, signal_key: str, n_trials: int) -> dict:
    arm_a, scales, close = inputs.arm_a, inputs.scales, inputs.close
    start = _b2_overlay_start(inputs)
    if len(close) - start < 2:
        raise ValidationError(
            f"{len(close) - start} of its return indices carry every asset's {signal_key}, and the head-to-head from the "
            "signal's own start needs 2"
        )
    arm_b = scale_positions(arm_a, scales)
    cost = _B2_COST_PER_SIDE
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(arm_a, returns, cost_per_side=cost)
    net_b = net_of_cost(arm_b, returns, cost_per_side=cost)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    slices_b, slices_bench = calendar_year_slices(net_b, inputs.h4_ts), calendar_year_slices(bench, inputs.h4_ts)
    drawdown_b = max_drawdown(net_b[start:])
    drawdown_a = max_drawdown(net_a[start:])
    if drawdown_a == 0:
        raise ValidationError("arm A never draws down from the signal's own start, so max_drawdown_reduction_pct divides by zero")
    grid = {
        (block, seed): a1_kill_bar(
            net_b,
            bench,
            n_trials=n_trials,
            var_trials=0.0,
            mean_block=block,
            seed=seed,
            cost_stressed_returns=net_b_x15,
            regime_slices=slices_b,
            benchmark_slices=slices_bench,
            decisive_start=_DECISIVE_START,
            n_resamples=_N_RESAMPLES,
        )
        for block in (30, 102)
        for seed in (42, 7, 1234)
    }
    headline = grid[(30, 42)]
    head_to_head = {}
    for label, first in (("full", 0), ("primary", start)):
        verdict = net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
        head_to_head[f"head_to_head_mean_outperf_{label}"] = verdict["mean_outperformance"]
        head_to_head[f"head_to_head_spa_p_{label}"] = verdict["spa_p_value"]
    positions_differ = per_year_positions_differ(arm_a, arm_b, close)
    engagement = _b2_overlay_engagement(inputs, signal_key)
    del engagement["engaged_per_asset"]
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(net_b[_DECISIVE_START:], periods_per_year=PPY_4H),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_DECISIVE_START:], periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_DECISIVE_START:], periods_per_year=PPY_4H),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": int(headline["dsr_pass"]),
        "spa_pass": int(headline["spa_pass"]),
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": int(headline["cost_stress_pass"]),
        "worst_slice_relative_pass": int(headline["worst_slice_pass"]),
        "passes": int(headline["passes"]),
        "decisive_start": _DECISIVE_START,
        "n_resamples": _N_RESAMPLES,
        "arm_a_passes": int(_b2_overlay_arm_a_bar(inputs, n_trials=n_trials)[0]["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": result["spa_p_value"] for (block, seed), result in grid.items()},
        **head_to_head,
        "max_drawdown": drawdown_b,
        "arm_a_max_drawdown": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        "turnover_a": book_turnover(arm_a),
        "turnover_b": book_turnover(arm_b),
        "stamps_positions_differ": sum(positions_differ.values()),
        "positions_differ_per_year": positions_differ,
        "turnover_a_per_year": per_year_turnover(arm_a, close),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        **engagement,
    }


def _b2_overlay_preflight_metrics(inputs: _B2OverlayInputs, *, signal_key: str, n_trials: int) -> dict:
    """Arm A's anchors and bar and the engagement (docs/specs/00138 D9): no position or return of arm B."""
    bar, net_a, bench = _b2_overlay_arm_a_bar(inputs, n_trials=n_trials)
    turnover_a = book_turnover(inputs.arm_a)
    return {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / len(inputs.close) * _B2_COST_PER_SIDE * PPY_4H,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_DECISIVE_START:], periods_per_year=PPY_4H),
        **{key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)},
        **_b2_overlay_engagement(inputs, signal_key),
    }


def _b2_overlay_build(
    subject: str,
    signal_key: str,
    read_signal: Callable[[ObservedReader, list[datetime]], dict[str, list[float | None]]],
    threshold: float,
    compute: Callable[..., dict],
    n_trials: int,
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
            "frozen --dataset"
        )
    try:
        inputs = _b2_overlay_inputs(subject, read_signal, threshold, reader, dataset, window, accept_holes)
        return compute(inputs, signal_key=signal_key, n_trials=n_trials)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b2_oi_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-oi-derisk",
        "binperp_oi_z30d",
        _b2_oi_signal,
        _B2_OI_THRESHOLD,
        _b2_overlay_metrics,
        _B2_OI_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_oi_derisk_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-oi-derisk-preflight",
        "binperp_oi_z30d",
        _b2_oi_signal,
        _B2_OI_THRESHOLD,
        _b2_overlay_preflight_metrics,
        _B2_OI_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_ratio_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-ratio-derisk",
        "binperp_ratio_max_z30d",
        _b2_ratio_signal,
        _B2_RATIO_THRESHOLD,
        _b2_overlay_metrics,
        _B2_RATIO_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_ratio_derisk_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-ratio-derisk-preflight",
        "binperp_ratio_max_z30d",
        _b2_ratio_signal,
        _B2_RATIO_THRESHOLD,
        _b2_overlay_preflight_metrics,
        _B2_RATIO_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_liq_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-liq-derisk",
        "binperp_liq_total_z30d",
        _b2_liq_signal,
        _B2_LIQ_THRESHOLD,
        _b2_overlay_metrics,
        _B2_LIQ_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_liq_derisk_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-liq-derisk-preflight",
        "binperp_liq_total_z30d",
        _b2_liq_signal,
        _B2_LIQ_THRESHOLD,
        _b2_overlay_preflight_metrics,
        _B2_LIQ_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


# docs/specs/00138 D8's matrix, spec 00128's with the head-to-head read from the signal's own start, and the two instrument
# findings its metrics show: a change to it is a new spec and a new trial, never an edit here.
def _b2_overlay_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["engaged_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0 and m["max_drawdown_reduction_pct"] > 1e-6:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"


# docs/specs/00138 D9's keys: trial 2's, the head-to-head's from-2021 pair read from the signal's own start, each signal's
# coverage in the funding z-score's place, and the returns from that start.
def _b2_overlay_metric_keys(signal_key: str) -> frozenset[str]:
    moved = {"head_to_head_mean_outperf_2021", "head_to_head_spa_p_2021", "binperp_funding_z30d_coverage"}
    return (_B2_METRIC_KEYS - moved) | {
        "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_primary",
        "primary_returns",
        f"{signal_key}_coverage",
    }


def _b2_overlay_preflight_keys(signal_key: str) -> frozenset[str]:
    return (_B2_FULL_PREFLIGHT_KEYS - {"binperp_funding_z30d_coverage"}) | {"primary_returns", f"{signal_key}_coverage"}
```

  and at the end of `SUBJECTS`, after the `"b2-funding-derisk-full-preflight"` entry:

```python
    "b2-oi-derisk": Subject(
        "b2-oi-derisk",
        (240,),
        _ASSETS,
        _build_b2_oi_derisk,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_oi_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_OI_N_TRIALS,
    ),
    "b2-oi-derisk-preflight": Subject(
        "b2-oi-derisk-preflight",
        (240,),
        _ASSETS,
        _build_b2_oi_derisk_preflight,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_oi_z30d"),
        seeds=(42,),
    ),
    "b2-ratio-derisk": Subject(
        "b2-ratio-derisk",
        (240,),
        _ASSETS,
        _build_b2_ratio_derisk,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_ratio_max_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_RATIO_N_TRIALS,
    ),
    "b2-ratio-derisk-preflight": Subject(
        "b2-ratio-derisk-preflight",
        (240,),
        _ASSETS,
        _build_b2_ratio_derisk_preflight,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_ratio_max_z30d"),
        seeds=(42,),
    ),
    "b2-liq-derisk": Subject(
        "b2-liq-derisk",
        (240,),
        _ASSETS,
        _build_b2_liq_derisk,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_liq_total_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_LIQ_N_TRIALS,
    ),
    "b2-liq-derisk-preflight": Subject(
        "b2-liq-derisk-preflight",
        (240,),
        _ASSETS,
        _build_b2_liq_derisk_preflight,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_liq_total_z30d"),
        seeds=(42,),
    ),
```

  **Author's call** — the wrappers read each count and threshold constant at call time, so the shared count-tie test's raise of a constant reaches every bar; the twin passes its trial's count to arm A's bar, as trial 2's twin did, a figure no number reads at `var_trials` 0.0.

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row's list, which now ends `` …, `b2-funding-derisk-full` (…) or `b2-funding-derisk-full-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`). | ``, ends instead:

```markdown
…, `b2-funding-derisk-full` (the A2 4h ensemble against the same ensemble halved per asset while that asset's 30-day funding z-score exceeds 2; the 4h series of `--dataset`, a frozen set only, and the `derivatives-funding` set's ten funding files read whole), `b2-funding-derisk-full-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`), `b2-oi-derisk` (the A2 4h ensemble against the same ensemble halved per asset while that asset's 30-day open-interest z-score exceeds 2.5; the 4h series of `--dataset`, a frozen set only, and the `derivatives-oi` set's ten files read whole), `b2-oi-derisk-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`), `b2-ratio-derisk` (the same comparison with the largest of the asset's four 30-day long/short-ratio z-scores above 2.5, read only where all four are; the 4h series of `--dataset`, a frozen set only, and the `derivatives-oi` set's ten files read whole), `b2-ratio-derisk-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`), `b2-liq-derisk` (the same comparison with the asset's per-bar liquidated notional more than two standard deviations above its trailing 180-bar mean; the 4h series of `--dataset`, a frozen set only, and the `liquidations-frozen` set read whole) or `b2-liq-derisk-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: Run them to verify they pass** — first, timed, in three parts, each its own plain call after the previous one's exit, since the whole runs about 11 min: with `F` the filter `b2_overlay or b2-oi-derisk or b2-ratio-derisk or b2-liq-derisk or ruled_subjects or declares_the_metric_keys`, `uv run pytest tests/test_research_command.py -k "shared_defaults_move and ($F)" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt-1`, then the same with `-k "evaluates_its_fixture and ($F)"` and `--basetemp=.tmp/plan-00138/pt-2`, then with `-k "($F) and not shared_defaults_move and not evaluates_its_fixture"` and `--basetemp=.tmp/plan-00138/pt-3` — collecting 6, 42 and 64 cases, 112 in all (measured on the transcription at about 202, 202 and 261 s, every case passing): each row at 10 s or more joins `tests/slow-cases.txt` at its `sorted()` place — on the transcription these eighteen:

```text
tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-ratio-derisk]
tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-ratio-derisk]
tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-ratio-derisk]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-liq-derisk]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-oi-derisk]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-ratio-derisk]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-liq-derisk-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-liq-derisk-preflight-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-oi-derisk-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-oi-derisk-preflight-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-ratio-derisk-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-ratio-derisk-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-derisk-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-derisk]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-oi-derisk-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-oi-derisk]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-ratio-derisk-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-ratio-derisk]
```

  the run's own timing deciding, a row the run puts at 10 s or more beyond them listed too (the six spoilt-file contract rows of the ratio pair measured 9.8–9.9 s), one below it left off. Then Step 2's command, expected `89 passed, 476 deselected` (measured on the transcription in 3 min 8 s) with the eighteen listed, each row moved between the lists moving one case between the counts; `uv run pytest tests/test_slow_cases.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` passes.

- [ ] **Step 6: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the direct readers in two parts, the second after the first's exit — `tests/test_research_command.py` alone, `--basetemp=.tmp/plan-00138/pt-1` (measured `497 passed, 68 deselected` in 6 min 45 s), and the other readers of the four paths, `--basetemp=.tmp/plan-00138/pt-2` (measured `4112 passed, 42 deselected` in 1 min 52 s), each `-m "not slow and not data"`; `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.

- [ ] **Step 7: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the transcription, sixty of sixty); the contract, tracked-spec, shared-defaults and count-tie rows of the six subjects are new rows of existing tests, not new guards, and are not probed; the ratio rows of the wiring, pre-flight and signal tests are slow, each recorded `probe skipped: slow case` with its node id:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-oi-derisk-preflight": Subject(/,/^    ),/s/metric_keys=_b2_overlay_preflight_keys("binperp_oi_z30d"),/metric_keys=_b2_overlay_metric_keys("binperp_oi_z30d"),/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-ratio-derisk": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-liq-derisk": Subject(/,/^    ),/s/n_trials=_B2_LIQ_N_TRIALS,/n_trials=_B2_RATIO_N_TRIALS,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_OI_N_TRIALS = 2 /_B2_OI_N_TRIALS = 1 /' -- uv run pytest 'tests/test_research_command.py::test_the_ruled_subjects_declare_their_families_and_trial_counts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/m\["head_to_head_mean_outperf_primary"\] > 0/m["head_to_head_mean_outperf_full"] > 0/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-outperforms-over-the-full-window-alone]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if m\["head_to_head_spa_p_primary"\] < 0.05 else/if m["head_to_head_spa_p_full"] < 0.05 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-from-the-start-and-draws-down-less]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/< 0.05 else "park"/< 0.05 and m["spa_p_decisive_b102_s42"] < 0.05 else "park"/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-from-the-start-and-draws-down-less]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/< 0.05 else/<= 0.05 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-2-p-at-exactly-0.05]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/< 0.05 else/< 0.0499 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-p-at-0.0499]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/else "park"/else "reject"/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-2-outperforms-insignificantly-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/_primary"\] > 0 and/_primary"] >= 0 and/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-mean-at-exactly-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/_primary"\] > 0 and/_primary"] > -1 and/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-underperforms-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/> 1e-6/>= 1e-6/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-reduction-at-exactly-1e-6]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/> 1e-6/> 1e-5/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-reduction-past-1e-6]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/ and m\["max_drawdown_reduction_pct"\] > 1e-6/ and True/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-draws-down-more]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/    if not m\["passes"\]:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-4-arm-b-fails-its-bar]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if not m\["arm_a_passes"\] or/if False or/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[arm-a-fails-its-bar]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/ or not any(m\["engaged_per_year"\].values()):/ or False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[the-overlay-never-engages]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if not m\["arm_a_passes"\] or not any/if not m["arm_a_passes"] and not any/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[arm-a-read-before-passes]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if not m\["arm_a_passes"\] or not any/if not m["arm_a_passes"] and not any/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[engagement-read-before-passes]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    for label, first in (("full", 0), ("primary", start)):/    for label, first in (("full", 0), ("primary", 0)):/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/^            n_trials=n_trials,$/            n_trials=1,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    drawdown_b = max_drawdown(net_b\[start:\])/    drawdown_b = max_drawdown(net_b)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/        "turnover_b": book_turnover(arm_b),/        "turnover_b": book_turnover(arm_a),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    slices_b, slices_bench = calendar_year_slices(net_b, inputs.h4_ts), calendar_year_slices(bench, inputs.h4_ts)/    slices_b, slices_bench = _b2_slices(net_b, inputs.h4_ts), _b2_slices(bench, inputs.h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/        "arm_a_passes": int(_b2_overlay_arm_a_bar(inputs, n_trials=n_trials)\[0\]\["passes"\]),/        "arm_a_passes": int(headline["passes"]),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_inputs(/,/^def /s/config=B2Config(z_threshold=threshold)/config=B2Config()/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_arm_a_bar(/,/^def /s/        regime_slices=calendar_year_slices(net_a, inputs.h4_ts),/        regime_slices=_b2_slices(net_a, inputs.h4_ts),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_start(/,/^def /s/if all(signal\[a\]\[k\] is not None for a in _ASSETS)/if any(signal[a][k] is not None for a in _ASSETS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    arm_b = scale_positions(arm_a, scales)/    arm_b = scale_positions(arm_a, {a: [0.5] * len(close) for a in scales})/' -- uv run pytest 'tests/test_research_command.py::test_where_no_signal_crosses_its_threshold_a_b2_overlays_arm_b_is_arm_a_bit_for_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_preflight_metrics(/,/^def /s/        "arm_a_max_drawdown_full": max_drawdown(net_a),/        "arm_a_max_drawdown_full": max_drawdown(bench),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_preflight_metrics(/,/^def /s/turnover_a \/ len(inputs.close)/turnover_a \/ len(inputs.h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_engagement(/,/^def /s/p > 0 and s < 1/p > 0 and s <= 1/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_engagement(/,/^def /s/        "primary_returns": len(close) - _b2_overlay_start(inputs),/        "primary_returns": len(close),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _build_b2_oi_derisk_preflight(/,/^def /s/        _B2_OI_THRESHOLD,/        _B2_LIQ_THRESHOLD,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _build_b2_liq_derisk_preflight(/,/^def /s/        _b2_liq_signal,/        _b2_oi_signal,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_start(/,/^def /s/for a in _ASSETS)), len(inputs.close))/for a in _ASSETS)), 0)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-liq-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-oi-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-ratio-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-liq-derisk": Subject(/,/^    ),/s/verdict=_b2_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-oi-derisk": Subject(/,/^    ),/s/verdict=_b2_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-ratio-derisk": Subject(/,/^    ),/s/verdict=_b2_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-liq-derisk": Subject(/,/^    ),/s/n_trials=_B2_LIQ_N_TRIALS,/n_trials=5,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-oi-derisk": Subject(/,/^    ),/s/n_trials=_B2_OI_N_TRIALS,/n_trials=3,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-ratio-derisk": Subject(/,/^    ),/s/n_trials=_B2_RATIO_N_TRIALS,/n_trials=4,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    if len(close) - start < 2:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[oi-one-index-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    if len(close) - start < 2:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[liquidations-no-index-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    if drawdown_a == 0:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[oi-arm-a-never-draws-down-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_oi_signal(/,/^def /s/raise SubjectError(f"derivatives-oi\/{relpath}: {exc}") from exc/raise SubjectError(f"oi\/{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[oi]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_ratio_signal(/,/^def /s/raise SubjectError(f"derivatives-oi\/{relpath}: {exc}") from exc/raise SubjectError(f"oi\/{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[ratio]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_liq_signal(/,/^def /s/raise SubjectError(f"{_B2_LIQ_SET}\/{relpath}: {exc}") from exc/raise SubjectError(f"{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[liquidation-buckets]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_liq_signal(/,/^def /s/raise SubjectError(f"{_B2_LIQ_SET}\/covered-hours.parquet: {exc}") from exc/raise SubjectError(f"covered-hours.parquet: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[covered-hours]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_oi_signal(/,/^def /s/rows\["sum_open_interest"\].to_list()/rows["sum_open_interest_value"].to_list()/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_liq_signal(/,/^def /s/rows\["short_usd"\].to_list())/rows["long_usd"].to_list())/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_OI_THRESHOLD = 2.5/_B2_OI_THRESHOLD = 2.0/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_LIQ_THRESHOLD = 2.0/_B2_LIQ_THRESHOLD = 2.5/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(research): B2 trials 3–5's subjects — the OI, ratio and liquidation overlays and their pre-flight twins on a frozen set's full history

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>
probe skipped: slow case — tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-ratio-derisk]
probe skipped: slow case — tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-ratio-derisk]
probe skipped: slow case — tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-ratio-derisk]

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 4: the data-gated basis test, the conventions entry, the reads (D9, D10's (c))

**Files:**
- Create: `tests/test_research_b2_overlays_basis.py` (module-marked `data`)
- Modify: `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 6's own commit

**Interfaces:**
- Consumes: Task 3's `_b2_overlay_inputs`, `_b2_oi_signal`, `_b2_ratio_signal`, `_b2_liq_signal`, `_b2_overlay_engagement`, `_b2_returns`, `_ASSETS`; Task 2's block and sidecar lines; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`.
- Produces: three tests sharing one module-scoped read; the module names `_CLOSES_PER_YEAR`, `_START`, `ENGAGED_PER_ASSET`, `ENGAGED_PER_YEAR` and `coverage()`, which Task 5's check programs import. No test computes a bar or a position or return of arm B.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, never from a run:

```python
"""B2 trials 3-5's inputs half on the frozen ohlc-full set against spec 00138's measured basis -- the OI and ratio signals'
coverage, start and engagement, the liquidations block's attestation and its signal at no close of the union -- and arm A
against records 50 and 51's stored figures: no bar, and no position or return of arm B."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import B2Config, derisk_scales, net_of_cost
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the basis test's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_SIDECAR = Path(__file__).resolve().parents[1] / "docs" / "reference" / "vouched-dataset-hashes.jsonl"
# Copied from the spec's measured basis, never from a run.
_BLOCK_HASH = "69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf"
_RETURN_INDICES = 27_337
_CLOSES_PER_YEAR = {
    "2013": 509,
    "2014": 2_190,
    "2015": 2_190,
    "2016": 2_195,
    "2017": 2_190,
    "2018": 2_183,
    "2019": 2_190,
    "2020": 2_196,
    "2021": 2_190,
    "2022": 2_190,
    "2023": 2_190,
    "2024": 2_195,
    "2025": 2_189,
    "2026": 540,
}
# Per overlay: the first close every asset's signal holds, the returns from it, and per asset the closes holding the
# signal in each close year that holds any.
_START = {
    "b2-oi-derisk": (datetime(2021, 12, 30, 20, tzinfo=UTC), 9_311),
    "b2-ratio-derisk": (datetime(2023, 1, 13, 12, tzinfo=UTC), 7_039),
}
_OI_NINE = {"2021": 7, "2022": 2_008, "2023": 2_010, "2025": 2_189, "2026": 540}
_RATIO_NINE = {"2023": 1_755, "2024": 1_835, "2025": 2_009, "2026": 540}
_HELD = {
    "b2-oi-derisk": {
        "ADA": _OI_NINE | {"2024": 1_830},
        "AVAX": _OI_NINE | {"2024": 2_015},
        "BTC": {"2020": 553, "2021": 2_010, "2022": 2_008, "2023": 2_010, "2024": 1_815, "2025": 2_189, "2026": 540},
        "DOGE": _OI_NINE | {"2024": 2_015},
        "DOT": _OI_NINE | {"2024": 2_015},
        "ETH": _OI_NINE | {"2024": 1_835},
        "LINK": _OI_NINE | {"2024": 2_015},
        "LTC": _OI_NINE | {"2024": 1_816},
        "SOL": _OI_NINE | {"2024": 1_829},
        "XRP": _OI_NINE | {"2024": 1_835},
    },
    "b2-ratio-derisk": {
        "ADA": _RATIO_NINE | {"2023": 1_575},
        "AVAX": _RATIO_NINE,
        "BTC": _RATIO_NINE | {"2020": 553, "2021": 2_002},
        "DOGE": _RATIO_NINE,
        "DOT": _RATIO_NINE | {"2023": 1_575},
        "ETH": _RATIO_NINE | {"2025": 1_829},
        "LINK": _RATIO_NINE,
        "LTC": _RATIO_NINE,
        "SOL": _RATIO_NINE,
        "XRP": _RATIO_NINE,
    },
}
ENGAGED_PER_ASSET = {
    "b2-oi-derisk": {
        "ADA": 210,
        "AVAX": 224,
        "BTC": 262,
        "DOGE": 489,
        "DOT": 159,
        "ETH": 237,
        "LINK": 333,
        "LTC": 319,
        "SOL": 181,
        "XRP": 371,
    },
    "b2-ratio-derisk": {
        "ADA": 411,
        "AVAX": 381,
        "BTC": 515,
        "DOGE": 436,
        "DOT": 459,
        "ETH": 224,
        "LINK": 492,
        "LTC": 435,
        "SOL": 418,
        "XRP": 385,
    },
}
ENGAGED_PER_YEAR = {
    "b2-oi-derisk": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 31, "2021": 40, "2022": 556, "2023": 636, "2024": 639, "2025": 725, "2026": 158},
    "b2-ratio-derisk": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 39, "2021": 116, "2022": 0, "2023": 1_394, "2024": 1_236, "2025": 1_139, "2026": 232},
}
_SIGNAL_KEY = {"b2-oi-derisk": "binperp_oi_z30d", "b2-ratio-derisk": "binperp_ratio_max_z30d"}
# Records 48-51's arm A and benchmark, stored unrounded; record 51 keys arm_a_max_drawdown as its from-2021 read's.
ARM_A = {
    "arm_a_ann_sharpe_noc": 1.404998307684581,
    "arm_a_ann_sharpe_noc_decisive": 1.3716011675660076,
    "arm_a_max_drawdown": 0.2154323695072342,
    "turnover_a": 146.18534602048504,
    "arm_a_spot_drag_pct_yr": 0.07026650498259404,
    "benchmark_ann_sharpe_noc": 1.2128451567638199,
    "benchmark_ann_sharpe_noc_decisive": 1.2446890489958136,
}


def coverage(name: str) -> dict[str, dict[str, list[int]]]:
    """A signal's per-asset, per-close-year `[non_null, total]` as the basis measured it."""
    return {
        asset: {year: [held.get(year, 0), total] for year, total in _CLOSES_PER_YEAR.items()} for asset, held in _HELD[name].items()
    }


@pytest.fixture(scope="module")
def _reads():
    reader = ObservedReader(_DATA_ROOT)
    oi = subjects._b2_overlay_inputs("b2-oi-derisk", subjects._b2_oi_signal, 2.5, reader, "ohlc-full", None, False)
    ratio = subjects._b2_ratio_signal(reader, oi.h4_ts)
    by_overlay = {
        "b2-oi-derisk": oi,
        "b2-ratio-derisk": oi._replace(signal=ratio, scales=derisk_scales(ratio, config=B2Config(z_threshold=2.5))),
    }
    return by_overlay, reader.block()


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet"),
    reason="the frozen ohlc-full set or the derivatives-oi set is absent under data/",
)
def test_the_oi_and_ratio_signals_reproduce_the_measured_basis(_reads):
    assert _DATA_ROOT == research_command._DATA_ROOT
    by_overlay, block = _reads
    assert compute_hash(block) == _BLOCK_HASH
    assert {dataset: (len(entry["files"]), entry["rows"], entry["span"]) for dataset, entry in block.items()} == {
        "derivatives-oi": (10, 5_010_882, ["2020-09-01 00:00:00+00:00", "2026-07-22 23:55:00+00:00"]),
        "ohlc-full": (10, 173_373, ["2013-09-10 20:00:00+00:00", "2026-03-31 20:00:00+00:00"]),
    }
    for name, inputs in by_overlay.items():
        first, returns = _START[name]
        assert (len(inputs.close), inputs.close[_RETURN_INDICES - returns]) == (_RETURN_INDICES, first), name
        assert subjects._b2_overlay_engagement(inputs, _SIGNAL_KEY[name]) == {
            "engaged_per_asset": ENGAGED_PER_ASSET[name],
            "engaged_per_year": ENGAGED_PER_YEAR[name],
            f"{_SIGNAL_KEY[name]}_coverage": coverage(name),
            "primary_returns": returns,
        }, name


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-frozen/*/buckets.parquet"),
    reason="the frozen ohlc-full set, the derivatives-oi set or the frozen liquidations block is absent under data/",
)
def test_the_liquidations_block_is_attested_and_its_signal_holds_no_close_of_the_union(_reads):
    inputs = _reads[0]["b2-oi-derisk"]
    reader = ObservedReader(_DATA_ROOT)
    signal = subjects._b2_liq_signal(reader, inputs.h4_ts)
    block = reader.block()["liquidations-frozen"]
    attested = {
        row["relpath"]: row for row in map(json.loads, _SIDECAR.read_text().splitlines()) if row["dataset"] == "liquidations-frozen"
    }
    files = {"covered-hours.parquet", *(f"{asset}/buckets.parquet" for asset in subjects._ASSETS)}
    assert set(reader.block()) == {"liquidations-frozen"} and set(block["files"]) == set(attested) == files
    assert block["rows"] == sum(row["rows"] for row in attested.values())
    assert reader.vouched_status() == {"liquidations-frozen": "checked (11 vouched hashes)"}
    # The block's first asserted hour opens after the union's last close: the 4h grid engages no stamp.
    assert datetime.fromisoformat(attested["covered-hours.parquet"]["first_ts"]) > inputs.close[-1]
    held = inputs._replace(signal=signal, scales=derisk_scales(signal, config=B2Config(z_threshold=2.0)))
    engagement = subjects._b2_overlay_engagement(held, "binperp_liq_total_z30d")
    assert (engagement["primary_returns"], set(engagement["engaged_per_asset"].values())) == (0, {0})
    assert set(engagement["engaged_per_year"].values()) == {0}
    assert engagement["binperp_liq_total_z30d_coverage"] == {
        asset: {year: [0, total] for year, total in _CLOSES_PER_YEAR.items()} for asset in subjects._ASSETS
    }


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet"),
    reason="the frozen ohlc-full set or the derivatives-oi set is absent under data/",
)
def test_the_overlays_arm_a_reproduces_records_50_and_51s_arm_a(_reads):
    inputs = _reads[0]["b2-oi-derisk"]
    net_a = net_of_cost(inputs.arm_a, subjects._b2_returns(inputs.h4_prices), cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a = book_turnover(inputs.arm_a)

    assert {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / _RETURN_INDICES * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
    } == ARM_A
    assert {key: _trials()[50]["metrics"][key] for key in ARM_A} == ARM_A
    shared = (
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "turnover_a",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    )
    assert {key: _trials()[51]["metrics"][key] for key in shared} == {key: ARM_A[key] for key in shared}
```

  **Author's call**: one `_b2_overlay_inputs` read builds arm A once, the ratio signal and the scales riding its union through `_b2_ratio_signal` and `derisk_scales` — the same function the OI read runs, at the same threshold — since each arm-A build costs about a minute; the liquidations test reads the block through its own reader, so the block it checks is the block's alone; its literals are the sidecar's, the one source the freeze wrote.

- [ ] **Step 2: Run it** — the three sets linked in this worktree: `mkdir -p .tmp/plan-00138 && uv run pytest tests/test_research_b2_overlays_basis.py --durations=4 -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`, one plain blocking call, `timeout` 600000 ms: `3 passed`, never a skip; `--collect-only` on the transcription: `3 tests collected`. Each node id at 10 s or more (setup counted with the first) joins `tests/slow-cases.txt` at its `sorted()` place, and `tests/test_slow_cases.py` passes.

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_overlays_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths; the two tree walkers its skip gates and data mark meet, `uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` (measured on the transcription `320 passed`); `uv run pre-commit run -a` until clean.

- [ ] **Step 4: Probes** — none for a listed slow case, each recorded `probe skipped: slow case`; a case step 2 measures under 10 s is probed as the Global Constraints have it, its row `--file tests/test_research_b2_overlays_basis.py --control 's/^def coverage(/def coverage_gone(/'` with a mutation substituting one literal it asserts.

- [ ] **Step 5: Commit**

```bash
git commit -F - <<'EOF'
test(research): B2 trials 3–5's inputs half against the measured basis, the frozen liquidations block's attestation, and arm A against records 50 and 51

<the test's pytest result line, pasted from its run over this tree>

<probe skipped: slow case — each listed node id>
They read data/ohlc-full, data/derivatives-oi and data/liquidations-frozen: re-run them with the three sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, they skip.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: The conventions entry** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`:

```markdown
[iter-182] B2 trials 3–5's conventions, pinned by spec 00138 before its hash (Decision: 1)
  The three trials' details are fixed in the spec, reviewed, and frozen by its sha256, every record's and reading's `spec_hash`, before any position or return of arm B and any kill bar is computed over the trials' data; each call below is one the spec marks as the author's, every value the owner or specs 00128 and 00137 fixed staying theirs.
  1. **As the spec pins them** — the trials run OI, ratios, liquidations, the owner's listing and the substrates' reach (D1); each signal takes the one of spec 00128's two thresholds, 2.0 and 2.5, whose engagement share is nearer trial 2's 4.93 %: OI 2.5 (6.08 % against 11.48 %), ratios 2.5 (12.09 % against 23.84 %), liquidations 2.0 on the tape's own bars (4.67 % against 3.52 %) (D3); the OI leg on the trio's z-score, its one reading on the same scale on every asset (D4); one ratio overlay, not one per ratio, on the four z-scores' maximum where all four are read (D5); the liquidation spike as the per-bar total's 180-bar z-score over the union's bars (D6); the frozen block as one file per coin beside the asserted hours, its coverage asserted for every coin from the one-request fetch, the 31 h finalize lag and a second read a poll cycle later (D7); the head-to-head from the first close every asset's signal holds (D8); the counts 2, 3 and 4 fixed by the hash, a stopped predecessor leaving the next one above what the count needs (D8); the variants `B2-<signal>-derisk-a2eq-full-v1`, and arm A by `_b2_inputs`' expression rather than `_b2_inputs` itself (D9); no `--verdict`, and notes naming only what is fixed before each run (D10); an adopt deployed on the B1 precedent, T0123's trigger qualified in its record's commit and the live feed on T0023 (D11). Chosen.
  2. **The alternatives each weighed** — the trials in another order; 2.0 for every signal, or a threshold fitted per signal; the log-delta or the momentum, or a per-asset cut on either; four ratio trials, four B slots for one of the owner's three; the four z-scores' mean, minimum, or the maximum of whichever are defined; a regular grid or a quantile cut for the liquidation spike; the freeze as the tree of finals, about 19,700 files in a record's block; coverage inferred from each coin's own finals; the next calendar-year boundary as the start; a count raised in place; another variant scheme; `_b2_inputs` called, the funding set entering the OI and ratio records' blocks unread; a `--verdict` asserted; notes reading results into the record; T0123 left reading any ADOPT.
  Source: spec 00138's **Author's call**s (D1, D3–D11); the owner's words of 2026-10-20 quoted in its ruling.
```

  staged alone, its gate `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-182] B2 trials 3–5's conventions, pinned by spec 00138 before its hash`.

- [ ] **Step 7 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–4 and the conventions entry — as CLAUDE.md orders it: `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every dispatch carries the hash rule — in a `review` or `re-review` `drive` as one sentence in words: nothing runs a bar or arm B over the real data before the spec's hash, and the data-gated cases run with the frozen full set, the OI set and the frozen liquidations block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip. Each report names the tip it read, the tip Task 5 step 1 diffs from. Task 5 waits until the trio has closed with no open Critical or Important.

______________________________________________________________________

### Task 5 (the controller's): the gate, the spec hash, the develop check, the data tests and the check programs (D10)

**Files:** scratch under `.tmp/plan-00138/`.

- [ ] **Step 1: The gate** — each check its own call, each read before the next:
  - The reads through Task 4 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00138-b2-three-overlays-design.md docs/research/10.phase4-decisions.md docs/reference/vouched-dataset-hashes.jsonl` exits 0; with no report naming a tip, stop: the reads come first.
  - The conventions entry against the spec at that tip, `grep -n "Author's call" docs/specs/00138-b2-three-overlays-design.md`: each call the entry names reads as the spec makes it; where a fix moved one, the entry is corrected in its own `docs(research)` commit and the first check runs again after a read of it.
  - Arm A's code path since record 51's run: `git log --oneline 044b14d3c0e8e5a247fe70bf25b30f7eb7a65196..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry/observed.py cli/ohlc cli/derivatives uv.lock pyproject.toml .python-version` lists `e8c8e374b` and `358e6da11` (the spec's measured basis), Tasks 1's and 3's commits and their fixes alone; any other commit is named, step 4's data tests deciding whether it moved arm A.
- [ ] **Step 2: D10 (1), the spec hash** — `sha256sum docs/specs/00138-b2-three-overlays-design.md`; its value, pasted from that call, is every run's `--spec-hash` and every record's and reading's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D10 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0: develop has appended nothing since this branch's base, so each append chains onto the branch's own last line; if not, develop is merged first (`git merge --no-edit origin/develop`, alone, then step 1's checks again). It runs again before each trial's pre-flight (Tasks 6–8 step 1).
- [ ] **Step 4: D10 (3), the data tests on the run's tree** — `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_overlays_basis.py tests/test_data_vouched_sidecar.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt > .tmp/plan-00138/basis.out 2>&1`, one background call, reads every case passed, never a skip; a failure is the owner's question before the first pre-flight.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00138/preflight_check.py`, D10's (a)–(e) in order, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00138 D10's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import _ASSETS
from tests.test_research_b2_overlays_basis import _CLOSES_PER_YEAR, _START, ENGAGED_PER_ASSET, ENGAGED_PER_YEAR, coverage

name = sys.argv[1]
signal_key = {"b2-oi-derisk": "binperp_oi_z30d", "b2-ratio-derisk": "binperp_ratio_max_z30d", "b2-liq-derisk": "binperp_liq_total_z30d"}[name]
out = Path(f".tmp/plan-00138/{name}-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if name == "b2-liq-derisk":
    sidecar = Path("docs/reference/vouched-dataset-hashes.jsonl").read_text().splitlines()
    attested = {row["relpath"] for row in map(json.loads, sidecar) if row["dataset"] == "liquidations-frozen"}
    union = block.get("ohlc-full", {})
    if not (
        set(block) == {"ohlc-full", "liquidations-frozen"}
        and (len(union["files"]), union["rows"], union["span"]) == (10, 173_373, ["2013-09-10 20:00:00+00:00", "2026-03-31 20:00:00+00:00"])
        and set(block["liquidations-frozen"]["files"]) == attested
        and len(attested) == 11
        and run["vouched"]["liquidations-frozen"] == "checked (11 vouched hashes)"
    ):
        sys.exit("(a) the inputs' block is not the frozen union beside the attested liquidations block")
elif compute_hash(block) != "69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf":
    sys.exit("(a) the inputs' block differs from the spec's")
anchors = {
    "arm_a_ann_sharpe_noc": (1.405, 4),
    "arm_a_ann_sharpe_noc_decisive": (1.3716, 4),
    "arm_a_max_drawdown_full": (0.2154, 4),
    "arm_a_spot_drag_pct_yr": (0.0703, 4),
    "benchmark_ann_sharpe_noc": (1.2128, 4),
    "benchmark_ann_sharpe_noc_decisive": (1.2447, 4),
    "turnover_a": (146.19, 2),
}
off = {key: m[key] for key, (value, digits) in anchors.items() if round(m[key], digits) != value}
if off:
    sys.exit(f"(b) arm A does not reproduce record 45's arm A: {off}")
if name == "b2-liq-derisk":
    basis = {
        "engaged_per_asset": dict.fromkeys(_ASSETS, 0),
        "engaged_per_year": dict.fromkeys(_CLOSES_PER_YEAR, 0),
        f"{signal_key}_coverage": {asset: {year: [0, total] for year, total in _CLOSES_PER_YEAR.items()} for asset in _ASSETS},
        "primary_returns": 0,
    }
else:
    basis = {
        "engaged_per_asset": ENGAGED_PER_ASSET[name],
        "engaged_per_year": ENGAGED_PER_YEAR[name],
        f"{signal_key}_coverage": coverage(name),
        "primary_returns": _START[name][1],
    }
off = [key for key, value in basis.items() if m[key] != value]
if off:
    sys.exit(f"(c) the engagement, the coverage or the start differs from the measured basis: {off}")
print("engaged", sum(m["engaged_per_asset"].values()), m["engaged_per_year"], "primary_returns", m["primary_returns"])
if not any(m["engaged_per_asset"].values()):
    sys.exit("(d) the overlay engages no stamp: the dead knob")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00138/record_check.py`, the record's checks:

```python
"""Spec 00138 D9's record, read off the registry's last line against the run's print and the measured basis: exit 0 when
every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_overlays_basis import _START, ENGAGED_PER_YEAR, coverage

name, spec_hash = sys.argv[1], sys.argv[2]
signal_key = {"b2-oi-derisk": "binperp_oi_z30d", "b2-ratio-derisk": "binperp_ratio_max_z30d"}[name]
labels = {"b2-oi-derisk": (2, "B2-oi-derisk-a2eq-full-v1"), "b2-ratio-derisk": (3, "B2-ratio-derisk-a2eq-full-v1")}[name]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00138/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == "69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf",
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"]) == ("B2", *labels, "iter-182", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": (m["engaged_per_year"], m[f"{signal_key}_coverage"], m["primary_returns"])
    == (ENGAGED_PER_YEAR[name], coverage(name), _START[name][1]),
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00138/preflight_check.py .tmp/plan-00138/record_check.py`.

______________________________________________________________________

### Task 6 (the controller's): trial 3 — the OI leg, its pre-flight, its run and its record (D4, D10)

Every step's command is read here and run in its step, never before; `<H>` is Task 5 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 5 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `uv run zcrypto research eval --subject b2-oi-derisk-preflight --dataset ohlc-full > .tmp/plan-00138/b2-oi-derisk-preflight.out 2>&1`, a plain eval of a subject with no rule, about 3–4 min, one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00138/preflight_check.py b2-oi-derisk`. Exit 0: step 4. One of the check's five `sys.exit` lines: D10's instrument finding, step 3. A traceback from the check, a pre-flight a signal ended, or a refusal before the build (`dataset 'ohlc-full' is absent: …`) is a code or environment fault and the owner's question; a refused build — exit 1 with no traceback, its output ending `b2-oi-derisk-preflight over the full history: …` or naming `derivatives-oi/<PERP>/oi.parquet: …` or `ohlc-full/<ASSET>/EUR/240.parquet: …` first — prints no metrics, keeps no reading, and is recorded in Task 9's T0023 findings with its line quoted, the trial unspent; Task 7 runs regardless.
- [ ] **Step 3: On a stop, the reading** — `uv run zcrypto research eval --subject b2-oi-derisk-preflight --dataset ohlc-full --reading --iteration iter-182 --spec-hash <H> --notes "B2 trial 3's pre-flight (spec 00138 D10): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00138/b2-oi-derisk-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `uv run zcrypto research eval --subject b2-oi-derisk --dataset ohlc-full --register --iteration iter-182 --family B2 --n-trials 2 --variant B2-oi-derisk-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00138/b2-oi-derisk.out 2>&1`, about 5–6 min, one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run, name only what is fixed before it: `subject b2-oi-derisk over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble at half its position on an asset while that asset's 180-mark open-interest z-score (sum_open_interest on the regular 4h grid, read at the close) exceeds 2.5, no hold-through, every position change charged 0.006 per side; the hypothesis: the half-scale improves the ensemble's net-of-cost performance through a lower drawdown at the engaged stamps, against the unconditioned ensemble; n_trials 2, var_trials 0.0, the DSR leg binding; the head-to-head from the first close every asset's signal holds (index 18026, 2021-12-30 20:00) decides, the full-window read beside it; pre-flight: block 69d7e9d6…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: scale 0.25, threshold 3.0; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, or bucket B spent — comes before the fit or after the print, naming each orphan or the bucket's figure: no record, no reading; T0023 carries it to the owner (Task 9) and Task 7 runs. A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b2-oi-derisk"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build of the window or a set ends its attempt failed, counting 0, recorded in T0023 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` is the owner's question before Task 7, quoted whole with the end of the run's output.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00138/record_check.py b2-oi-derisk <H>` exits 0; its printed `counted` is read, never checked, and named on T0016's line (Task 9) when non-empty. A failed check is the owner's question before step 6.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-182] Verdict — B2 trial 3 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B2 n=2)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D8's table (`sed -n '/^| Kill bar/,/^  The rows are disjoint/p' docs/specs/00138-b2-three-overlays-design.md`), with `passes`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary` and `max_drawdown_reduction_pct` unrounded, `max_drawdown` beside `arm_a_max_drawdown`, the full-window pair beside them; `n_trials` 2, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); the pre-flight's block, anchors and `passes` from `.tmp/plan-00138/b2-oi-derisk-preflight.out`; the engagement proof — `engaged_per_year`, `primary_returns`, `stamps_positions_differ`, `turnover_a` beside `turnover_b`; on a park its variants; on an adopt D11's path in its order; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-181] Verdict — B2 trial 2 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b2-oi-derisk": 2,` after `"b2-funding-derisk-full": 1,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B2 trial 3's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries it adopts`, in this commit (D11). Then `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a` until clean. In the probe worktree (Global Constraints' probe line), `data/ohlc-full` and `data/derivatives-oi` linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00138/probe/data/<set>` and unlinked before its removal: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference, or a call under 10 s, the owner's question; then the literal's probe, expected `KILLED`: `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_OI_N_TRIALS = 2 /_B2_OI_N_TRIALS = 3 /' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit, `git add` by path of the registry, the provenance test, the decisions log, the slow-cases file and on an adopt T0123:

```bash
git commit -F - <<'EOF'
docs(research): B2 trial 3 registered — <verdict>, the OI de-risk on the A2 ensemble, registry trial <N>

<the tie and provenance tests' pytest result line, and the replay case's with its call time>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<the literal's infra/scripts/mutate-probe.sh command, then its verdict line>
probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]
The replay reads data/ohlc-full and data/derivatives-oi: re-run it with the two sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b2-oi-derisk-preflight` with outcome `null`, or `b2-oi-derisk` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones — the entry is `[iter-182] B2 trial 3 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]`; the replay `-k 'reading-<its id>'`; committed as `docs(research): B2 trial 3 — instrument finding, kept as reading <id>; no trial spent` with no probe. On a refusal from the count or a refused build: no commit here; Task 9 records it.

______________________________________________________________________

### Task 7 (the controller's): trial 4 — the ratio leg, its pre-flight, its run and its record (D5, D10)

Task 6's steps with these values, each command written out: the subject `b2-ratio-derisk`, its twin `b2-ratio-derisk-preflight`, the outputs `.tmp/plan-00138/b2-ratio-derisk-preflight.out`, `.tmp/plan-00138/b2-ratio-derisk-reading.out` and `.tmp/plan-00138/b2-ratio-derisk.out`; the count `--n-trials 3`; the variant `B2-ratio-derisk-a2eq-full-v1`; "B2 trial 4" in every note, entry and message.

- [ ] **Step 1: The develop check** — Task 5 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `uv run zcrypto research eval --subject b2-ratio-derisk-preflight --dataset ohlc-full > .tmp/plan-00138/b2-ratio-derisk-preflight.out 2>&1`, one background call (about 5 min: the ratio z-scores run over four columns), then `uv run python .tmp/plan-00138/preflight_check.py b2-ratio-derisk`, read as Task 6 step 2 reads its own.
- [ ] **Step 3: On a stop, the reading** — `uv run zcrypto research eval --subject b2-ratio-derisk-preflight --dataset ohlc-full --reading --iteration iter-182 --spec-hash <H> --notes "B2 trial 4's pre-flight (spec 00138 D10): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00138/b2-ratio-derisk-reading.out 2>&1`.
- [ ] **Step 4: The trial** — `uv run zcrypto research eval --subject b2-ratio-derisk --dataset ohlc-full --register --iteration iter-182 --family B2 --n-trials 3 --variant B2-ratio-derisk-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00138/b2-ratio-derisk.out 2>&1`, one background call; the notes: `subject b2-ratio-derisk over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble at half its position on an asset while the largest of that asset's four 180-mark long/short-ratio z-scores, read only where all four are defined, exceeds 2.5, no hold-through, every position change charged 0.006 per side; the hypothesis: the half-scale improves the ensemble's net-of-cost performance through a lower drawdown at the engaged stamps, against the unconditioned ensemble; n_trials 3, var_trials 0.0, the DSR leg binding; the head-to-head from the first close every asset's signal holds (index 20298, 2023-01-13 12:00) decides, the full-window read beside it; pre-flight: block 69d7e9d6…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: scale 0.25, threshold 3.0; the matrix pre-registered by the spec's sha256 <H>`; every other exit read as Task 6 step 4 reads its own, the attempt check naming `b2-ratio-derisk`.
- [ ] **Step 5: The record's checks** — `uv run python .tmp/plan-00138/record_check.py b2-ratio-derisk <H>` exits 0.
- [ ] **Step 6: The records commit** — Task 6 step 6's three edits with `[iter-182] Verdict — B2 trial 4 <ADOPT, PARK or REJECT> (registry trial <N>, family B2 n=3)`, `"b2-ratio-derisk": 3,` after `"b2-oi-derisk": 2,` (or after `"b2-funding-derisk-full": 1,` where trial 3 landed no record), and the replay row; on an adopt T0123's qualification naming B2 trial 4, once only — a second adopt adds its record to the same qualification; the replay with the same two sets linked; the literal's probe `--mutation 's/^_B2_RATIO_N_TRIALS = 3$/_B2_RATIO_N_TRIALS = 4/'`, every other argument Task 6's; committed as `docs(research): B2 trial 4 registered — <verdict>, the ratio de-risk on the A2 ensemble, registry trial <N>`, or on a stop as Task 6's stop arm with "B2 trial 4" and `b2-ratio-derisk`.

______________________________________________________________________

### Task 8 (the controller's): trial 5 — the liquidations leg, its pre-flight and its expected stop (D6, D10)

The spec states the outcome before the hash: the block opens after `ohlc-full`'s last close, so (d) fails — the engaged total is 0 — and the run is a reading, the trial unspent.

- [ ] **Step 1: The develop check** — Task 5 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `uv run zcrypto research eval --subject b2-liq-derisk-preflight --dataset ohlc-full > .tmp/plan-00138/b2-liq-derisk-preflight.out 2>&1`, one background call, then `uv run python .tmp/plan-00138/preflight_check.py b2-liq-derisk`, expected to exit on `(d) the overlay engages no stamp: the dead knob` after (a)–(c) pass. An exit at (a)–(c) is an instrument finding on its own line, a stop all the same; an exit 0 contradicts the measured basis and is the owner's question before any run.
- [ ] **Step 3: The reading** — `uv run zcrypto research eval --subject b2-liq-derisk-preflight --dataset ohlc-full --reading --iteration iter-182 --spec-hash <H> --notes "B2 trial 5's pre-flight (spec 00138 D6, D10): <the check's sys.exit line, quoted>; the frozen liquidations block opens after ohlc-full's last close, so the overlay engages no stamp; no verdict, the trial unspent" > .tmp/plan-00138/b2-liq-derisk-reading.out 2>&1`, one background call; no `--register` run of `b2-liq-derisk`.
- [ ] **Step 4: The reading's checks** — `uv run python -c 'import json, sys; from pathlib import Path; r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1]); out = Path(".tmp/plan-00138/b2-liq-derisk-reading.out").read_text(); printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]; ok = (r["invocation"]["subject"], r["invocation"]["dataset"], r["outcome"], r["spec_hash"], r["iteration"], r["metrics"] == printed, r["metrics"]["primary_returns"], sum(r["metrics"]["engaged_per_asset"].values())) == ("b2-liq-derisk-preflight", "ohlc-full", None, sys.argv[1], "iter-182", True, 0, 0); print(r["reading_id"], ok); sys.exit(0 if ok else 1)' <H>` exits 0.
- [ ] **Step 5: The records commit** — the entry `[iter-182] B2 trial 5 — instrument finding, the trial unspent (reading <its reading_id>)`: the check's line, quoted; the block's span against the union's (`first_ts` of `covered-hours.parquet` in the sidecar against 2026-03-31 20:00) and the zero engagement; arm A's anchors and `passes` as printed; the block's eleven attested files — the coverage proof's figures from Task 2's commit; that the trial is unspent and the block stands for the first instrument whose window reaches the tape (D6). `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<its id>]`; `T` over the staged paths with the two decisions-log tests and `tests/test_slow_cases.py`; `uv run pre-commit run -a`; in the probe worktree with `data/ohlc-full` and `data/liquidations-frozen` linked, the replay `-k 'reading-<its id>'` passes; committed as `docs(research): B2 trial 5 — instrument finding, kept as reading <id>; no trial spent` with the replay's line and call time and `probe skipped: slow case` for its node id.

______________________________________________________________________

### Task 9: T0023, T0016, the index and the retirement of the six subjects (D11)

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py`.

**Interfaces:** Consumes the registry's and the ledger's lines Tasks 6–8 committed and their decisions-log entries; `topic-ops`; `infra/scripts/topics-index.py`.

- [ ] **Step 1: T0023**, per `topic-ops`, every figure read off the committed records, readings and entries:
  - `## Findings so far` gains one bullet per trial — `**B2 trial 3 <VERDICT> (iter-182, spec 00138, registry trial <N>).**` with the row that fired and the engagement in one or two sentences, or `**B2 trial 3 — instrument finding (iter-182, spec 00138, reading <R>).**` with what failed; trials 4 and 5 alike, trial 5's naming the block's span against the union's — and one for the frozen block: its eleven files, the closed span and asserted hours, the attestation.
  - `## Done so far` gains a bullet, **B2 trials 3–5 (iter-182, spec/plan 00138)**, naming the ratio z-scores, their all-four maximum and the liquidation z-score in `cli/alpha/b2.py`, the frozen liquidations block `data/liquidations-frozen/` with its coverage proof, the six subjects and the data-gated basis test, and the records and readings by id.
  - `## Suggested next steps`: the item `(owner) B2's next step after trial 2's reject` is replaced by `(owner) B2's next step after trials 3–5` — <the verdicts in one clause>; a park's variants, a further leg, or closing the family — the owner's pick, recorded as a `[iter-NNN] B2's next step after trial 5` entry; the later-trials item drops the OI leg and the four ratio columns, keeps the funding variants, and says the liquidations leg waits on an instrument whose window reaches the frozen block, which re-proves its coverage; on an adopt, the live feed's spec after the combination trial (D11).
  - `ripe_when` — on no adopt: `an activity: the owner picks B2's next step after trials 3–5 — a park variant, a further leg, or closing the family — recorded in the decisions log; check: grep -c -E '^\[iter-[0-9]+\] B2.s next step after trial 5' docs/research/10.phase4-decisions.md prints at least 1`; on an adopt: `an activity: the P1 combination trial over record 47's book carrying B2 trial <k>'s arm B is picked for an iteration; check: cat docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md | grep -c -E '^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book' prints at least 1`. The check is run as committed and prints 0.
- [ ] **Step 2: T0016** — its budget line reads `B1 spent 5, B2 spent <1 + the records Tasks 6 and 7 landed>, <19 − those records> remain`, less one for each orphan a record's `attempt.counted` lists, named on that line; its B2 line under `## Done so far` names trials 3–5 (iter-182, spec/plan `00138`) with their records or readings and verdicts.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, as `tests/retired_subjects.py`'s own rule has it: no trial still to run evaluates the six subjects, so `RETIRED_SUBJECTS` gains, after `"b2-funding-derisk-full-preflight",`:

```python
        # B2's trials 3-5 and their pre-flights.
        "b2-oi-derisk",
        "b2-oi-derisk-preflight",
        "b2-ratio-derisk",
        "b2-ratio-derisk-preflight",
        "b2-liq-derisk",
        "b2-liq-derisk-preflight",
```

  and `@pytest.mark.retired` goes above `test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop`'s `@pytest.mark.parametrize(` and above `def test_where_no_signal_crosses_its_threshold_a_b2_overlays_arm_b_is_arm_a_bit_for_bit(` and `def test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero(` — the three overlay functions no parameter names a subject in. Measured on the transcription: `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q` prints `164/565 tests collected (401 deselected)` with no overlay case kept, and `tests/test_retired_subjects.py` `5 passed`.
- [ ] **Step 5: Gate and commit** — `git add docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md tests/retired_subjects.py tests/test_research_command.py`; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0023 and T0016 after B2 trials 3–5; the six subjects retired` with the result line. The retirement adds names to an existing guard's data and no guard: no probe.

______________________________________________________________________

### Task 10: the owner's pick in the decisions log, the read and the PR

- [ ] **Step 1: The decisions-log entry** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`:

```markdown
[iter-182] B2's next step after trial 2 — the OI leg, the four ratio columns and a liquidations trial as one spec with three trials in sequence, the owner's pick, attended, 2026-10-20 (Decision: 3)
  Said: "continue working on T0023 for the B2's next steps: the OI leg, the four ratio columns, and a liquidations trial". Asked how to shape the three, answered: "One spec, three trials in sequence (Recommended)" — one iteration and branch, one spec and plan naming three subjects with one bar and matrix each, one plan review, one task loop; the trials run one after another, each registering its own record, a reject of one never stopping the next; the liquidations trial also does the frozen block's coverage proof spec 00136 left to it. Standing from trial 2 and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)", the treatment "Unchanged (Recommended)" and the head-to-head read "From-2021 primary (Recommended)", the read opening at a later signal's own start. The options are T0023's after trial 2's reject, record 51, with the work's two shapes.
  1. **Close the family** — archive T0023 on its two trials: the funding de-risk, the family's lead hypothesis, measured where arm A clears the bar and rejected. Spends no trial and none of a spec, plan, review and run cycle; leaves the OI, ratio and liquidation legs, whose substrates and emitters specs 00131 and 00136 built, untested, and the 19 B slots to B3 and B4.
  2. **Three separate iterations** — a spec, plan, plan review, task loop and pull request per leg, each pre-registered after the one before it has run. A later design could take in an earlier result — the look one spec rules out — at the price of three review cycles and branches for three overlays sharing their instrument, bar, arms and matrix.
  3. **One spec, three trials in sequence** — spec 00138 pre-registers the OI leg, one ratio overlay and the liquidations leg on trial 2's instrument and bar, each its own subject, count and record, run OI, ratios, liquidations, every design fixed by one hash before the first runs; one review cycle and one branch. Spends up to three B slots, 19 to 16, and carries a liquidations trial the frozen instrument cannot reach, its pre-flight's refusal recorded as such. Chosen.
```

  Its gate `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` and `uv run pre-commit run -a`; committed as `docs(research): [iter-182] B2's next step after trial 2 — the owner's pick, one spec with three trials in sequence`. T0023's trigger before Task 9 read this entry's header, which now prints 1 on that check; Task 9 already moved the topic to its next trigger.
- [ ] **Step 2 (the controller's): The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-182 — B2 trials 3–5: OI, ratio, liquidation de-risk` (72 characters by `wc -m`, at `open-pr`'s cap), its own commit.
- [ ] **Step 3 (the controller's): The read** — the `pre-review` of Tasks 6–10's commits, then `review` over `<the tip the last read covered>..HEAD`, since the commits add files outside that read's range, and `re-review` over a fix of it within the branch's two, each `drive` carrying one sentence in words: the data-gated cases and replays the messages record run with the frozen full set, the OI set and the frozen liquidations block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 4 (the controller's): The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the three verdicts or stops, each pre-flight's output quoted whole in a fenced block (`.tmp/plan-00138/*-preflight.out`), the freeze's output, every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the delta's read covered. Merged on the owner's word through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00138` removed, and `unlink data/ohlc-full`, `unlink data/derivatives-oi`, `unlink data/derivatives-funding` and `unlink data/liquidations-frozen` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full`, `derivatives-oi`, `derivatives-funding` and `liquidations-frozen` still there.

Decisions log: the conventions entry (Task 4 step 6), before the hash; the verdict or instrument-finding entries (Tasks 6–8 step 6, Task 8 step 5), each in its record's commit; and this task's `[iter-182] B2's next step after trial 2`.
