# B2 trials 6–7 — the liquidation-cascade and funding-extreme re-entries on frozen ohlc-full, the gated runs and the verdicts — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b2.py tests/test_alpha_b2.py cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b2_reentries_basis.py docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/test_trial_registry_provenance.py tests/retired_subjects.py docs/research/10.phase4-decisions.md docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00139-b2-reentries-design.md` prints `tier: full`, for `tests/test_alpha_b2.py` "a test importing cli.alpha.b1", `tests/test_research_command.py` "a test importing cli.alpha", `docs/reference/trial-registry.jsonl` and `tests/test_trial_registry_provenance.py`, and, once Task 3 has created it, `tests/test_research_b2_reentries_basis.py` "a test importing cli.features.derivatives").

**Goal:** B2's trials 6 and 7 (spec 00139) — three emitters in `cli/alpha/b2.py`; four research subjects in `cli/research/subjects.py` — two trials and their evaluate-only pre-flight twins; the data-gated test of their inputs half; the two trials run in order through spec 00133's trial-attempts log — each verdict or stop in the registry and the decisions log, then T0023, T0016 and the loop's pick recorded.

**Architecture:** no new module. `cli/alpha/b2.py` gains `full_long_sizes`, `reentry_positions` and `reentry_counts_per_year`, and the import `statistics`. `cli/research/subjects.py` gains one re-entry machinery — `_B2ReentryInputs`, `_b2_funding_signal`, `_b2_reentry_inputs` (the union, arm A by `_b2_overlay_inputs`' expression with its books kept, the full-long size, the fires and arm B), `_b2_reentry_start`, `_b2_reentry_engagement`, `_b2_reentry_metrics` (`_b2_overlay_metrics`' body with arm B, the start and the engagement the re-entry's), `_b2_reentry_preflight_metrics`, `_b2_reentry_build`, four thin `_build_` wrappers and the rule `_b2_reentry_verdict` — and four `SUBJECTS` entries. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00139-b2-reentries-design.md` — binding; D1–D8 are cited by name and the values below are copied from it. It copies spec 00138's instrument, bar, arms and costing, frozen (records 52–54's and reading 2's `spec_hash`). **Iteration:** iter-183. **Topic:** T0023 under T0016. **Branch:** `research/iter-183-b2-contrarian-reentry`, worktree `.claude/worktrees/iter183`, `data/ohlc-full`, `data/derivatives-funding` and `data/liquidations-daily` linked read-only from the main checkout. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: the code and tests of Tasks 1–3 were written in this worktree, their tests run green (`11 passed, 136 deselected` for Task 1's re-entry cases, `38 passed, 636 deselected` and `56 passed, 618 deselected` for Task 2 step 6's two parts, `2 passed` for Task 3's data-gated cases, each about 95 s), the cli diff measured, the slow cases timed, and Tasks 1–2's twenty-eight probe rows run in a detached scratch worktree on that tree, twenty-eight of twenty-eight `KILLED`; the files were then restored to the base before this plan was committed. Not run: Task 3's probes beyond its slow cases (none), the check programs beyond a parse (Task 4 step 5), any `zcrypto research eval` (Tasks 5–6), the replays and the literal probes (Tasks 5–6), the topic edits (Task 7) and the PR (Task 8).

## Global Constraints

- **The signals, thresholds and holds** (D3, D4): trial 6 — `_b2_liq_signal(reader, h4_ts)` per coin over `liquidations-daily/<COIN>/daily.parquet`, key `binperp_liq_long_z30d`, fires where the z-score is above `_B2_LIQ_REENTRY_THRESHOLD = 2.5` (`operator.gt`), `_B2_LIQ_REENTRY_HOLD = 1`; trial 7 — `_b2_funding_signal(reader, h4_ts)` per perp over `derivatives-funding/<PERP>/funding.parquet`, `funding_grid_feature(..., config=B2Config())`, key `binperp_funding_z30d`, fires below `_B2_FUNDING_REENTRY_THRESHOLD = -2.0` (`operator.lt`), `_B2_FUNDING_REENTRY_HOLD = 6`; the full-long size `full_long_sizes(_inverse_vol_weights(fed, lookback=180), [the three books' vol_target_positions], _ASSETS)`; arm B `reentry_positions(arm_a, full_long, fires, hold=<the trial's>)`.
- **The bars** (D2, D5): every `a1_kill_bar` call `n_trials=<the subject's count>, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, the headline (30, 42); arm A's bar the same call at (30, 42) on `net_a`; the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` for `("full", 0)` and `("primary", start)`, `start` `_b2_reentry_start(inputs)`, the later of the first return index every asset's signal holds and the first closing at or after 2021-01-01; the drawdown pair from `start`; refused before any bar: fewer than 2 return indices from `start`, or arm A never drawing down from it.
- **The counts** (D5): `_B2_LIQ_REENTRY_N_TRIALS = 5`, `_B2_FUNDING_REENTRY_N_TRIALS = 6`, fixed by the spec's hash; at `var_trials` 0.0 neither moves a figure of the bar.
- **The rule** (D5): `_b2_reentry_verdict` — `None` when `arm_a_passes` is 0 or no year holds an engaged stamp, `reject` on a failed bar, on `head_to_head_mean_outperf_primary > 0` `adopt` where `head_to_head_spa_p_primary < 0.05` and `max_drawdown_reduction_pct >= -20.0`, else `park`; `reject` otherwise.
- **The records** (D6): family `B2`; `n_trials_in_family` the count; variants `B2-liq-reentry-a2eq-full-v1` and `B2-funding-reentry-a2eq-full-v1`; iteration `iter-183`; seeds (42, 7, 1234); 42 metric keys, `threshold` among them; the blocks `816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f` (trial 6) and `3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8` (trial 7); no `--verdict`.
- **The pre-flight read** (D7), in this order: (a) the block and its signal set's vouched status (Task 3's `VOUCHED`); (b) arm A's seven anchors at record 45's precision — `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown_full` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703, the benchmark's 1.2128 and 1.2447 at four decimals, `turnover_a` 146.19 at two; (c) `engaged_per_asset`, `engaged_per_year`, `primary_returns` and `threshold` the measured basis's (Task 3's literals), and the signal's coverage the inputs half's recomputed over the same sets, a cross-check of the twin's path against Task 3's, whose cases hold the first index every asset's signal holds to the basis's; (d) the engaged total above 0; (e) arm A's `passes` 1.
- **The hash rule** (D7): before Task 4 step 2 takes the spec's sha256, nobody computes arm A's bar or any return of arm B over the trials' data; the data-gated test (Task 3) computes arm A's positions, the signals, the full-long size, arm B's positions and turnover and the engagement — the basis's own measures — and no bar; no reader, reviewer or plan-review dispatch runs any of the four subjects over the real sets before the hash, and every read's dispatch carries this rule. No return of arm B is computed over a trial's data before that trial's `--register` run, and no trial subject is ever run as a plain eval.
- **Unchanged** (D6): every existing function of `cli/alpha/b2.py`, `cli/research/subjects.py`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/engine/*` and `cli/liquidations/*`; the subjects of trials 1–5; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/alpha/b2.py` from Task 1 on and `cli/research/subjects.py` from Task 2 on, nothing else; `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/ | grep -c '^-[^-]'` prints 0 — both files gain lines and lose none. Measured on the authoring tree, the hunks: `cli/alpha/b2.py`'s `@@ -3,0 +4 @@` and `@@ -464,0 +466,49 @@`; `cli/research/subjects.py`'s `@@ -9,0 +10 @@`, `@@ -60,0 +62 @@`, `@@ -70,0 +73,2 @@`, `@@ -2450,0 +2455,344 @@` and `@@ -2831,0 +3180,50 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00139-b2-reentries-design.md` after Task 4 step 2, nor specs 00128, 00137 and 00138, nor the spec before then except a fix commit a read of Task 3 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Tasks 5–6 name it. Never `git stash`; no amend; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, `data/derivatives-funding` and `data/liquidations-daily`, read-only links, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, ssh or a fleet host, docker, `kraken-cli`, the vault, the network, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 6's reads, Tasks 4–6 and Task 8's steps 2–4, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data tests, the pre-flights, the registers, the replays), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 7, Task 3's steps 1–5 and Task 8's step 1.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00139 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt` (or a file, or `-k`). An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00139/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt`, never a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Three of the implementer's `T` runs hold `tests/test_research_command.py` whole: Task 1 step 5's, measured under 600 s and run as one call, and Task 2 step 7's and Task 7 step 5's, each in Task 2 step 7's three parts, its two `-k` halves measured there; the controller's, Tasks 5–6 step 6's, run in the background. A commit message's test result line is a run over that commit's own tree.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
test ! -e .tmp/plan-00139/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00139/probe HEAD &&
  git -C .tmp/plan-00139/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00139/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00139/probe/.tmp
```

  Then, from `.tmp/plan-00139/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. After the last verdict, `git worktree remove --force .tmp/plan-00139/probe` — a data link in it unlinked first, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, each set it linked still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

## Task 1: the three emitters in `cli/alpha/b2.py` (D3, D6)

**Files:** Modify `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

**Interfaces:** Produces `full_long_sizes(weights, levels, assets) -> dict[str, list[float]]`, `reentry_positions(asset_positions, full_long, fires, *, hold) -> dict[str, list[float]]` and `reentry_counts_per_year(asset_positions, reentered, close_ts) -> dict[str, int]`; each refuses with `AlphaError` what it cannot pair, through the module's `_check_lengths` and `_check_paired`.

- [ ] **Step 1: Write the failing tests** — in `tests/test_alpha_b2.py`, the `from cli.alpha.b2 import (` block gains `full_long_sizes,` after `event_contrast,` and `reentry_counts_per_year,` and `reentry_positions,` after `ratio_zscore_grid_features,`; after `test_per_year_max_drawdown_reads_each_year_from_its_own_peak` and before `_POS = {"BTC": [0.4, 0.2], "ETH": [0.3, 0.6]}`:

```python
def test_full_long_sizes_is_the_shared_weight_times_the_mean_of_the_arms_levels():
    # The arms' levels average to 0.6, 0.4 (its median 0.3) and 0.6; ETH carries no weight at index 1, and no asset at index 2.
    weights = [{"BTC": 0.6, "ETH": 0.4}, {"BTC": 1.0}, {}]
    levels = [[0.9, 0.3, 0.6], [0.6, 0.9, 0.6], [0.3, 0.0, 0.6]]
    sizes = full_long_sizes(weights, levels, ("BTC", "ETH"))
    assert sizes == {"BTC": pytest.approx([0.36, 0.4, 0.0]), "ETH": pytest.approx([0.24, 0.0, 0.0])}


# BTC long at 0-1 and 7, flat between, firing while long at 1 and 7 and flat at 2-3, its full-long size moving at every
# flat close; ETH long at 0 and 3, firing while long at 3 and flat at 1 and 6, its full-long size 0 at indices 2 and 6.
_REENTRY_ARM_A = {"BTC": [0.4, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3], "ETH": [0.2, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0]}
_REENTRY_FULL = {"BTC": [0.5, 0.5, 0.45, 0.55, 0.5, 0.6, 0.4, 0.5], "ETH": [0.6, 0.6, 0.0, 0.6, 0.6, 0.6, 0.0, 0.6]}
_REENTRY_FIRES = {
    "BTC": [False, True, True, True, False, False, False, True],
    "ETH": [False, True, False, True, False, False, True, False],
}


@pytest.mark.parametrize(
    ("hold", "expected"),
    [
        pytest.param(
            1,
            {"BTC": [0.4, 0.4, 0.45, 0.55, 0.0, 0.0, 0.0, 0.3], "ETH": [0.2, 0.6, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0]},
            id="hold-1-open-only-where-it-fires",
        ),
        pytest.param(
            3,
            {"BTC": [0.4, 0.4, 0.45, 0.55, 0.5, 0.6, 0.0, 0.3], "ETH": [0.2, 0.6, 0.0, 0.5, 0.0, 0.0, 0.0, 0.6]},
            id="hold-3-open-three-closes-from-the-last-firing",
        ),
    ],
)
def test_reentry_positions_take_the_full_long_size_where_arm_a_is_flat_through_the_hold(hold, expected):
    # A firing while long opens nothing, a re-entry takes the size of its own close, a zero full-long size takes nothing and
    # still counts toward the hold, a second firing restarts the hold, and arm A turning long closes a re-entry.
    assert reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, _REENTRY_FIRES, hold=hold) == expected


def test_reentry_counts_per_year_counts_flat_asset_stamps_arm_b_holds_and_never_a_long_one():
    reentered = {"BTC": [0.4, 0.4, 0.5, 0.0, 0.3, 0.3], "ETH": [0.2, 0.2, 0.2, 0.5, 0.5, 0.6]}
    assert reentry_counts_per_year(_ARM_A, reentered, _CLOSE) == {"2020": 1, "2021": 1}


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(lambda: full_long_sizes([{}], [], ("BTC",)), "at least one arm", id="no-levels"),
        pytest.param(
            lambda: full_long_sizes([{}, {}], [[0.5]], ("BTC",)), r"levels\[0\] has length 1, expected 2", id="levels-length"
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, _REENTRY_FIRES, hold=0),
            "hold must be an int >= 1",
            id="hold-0",
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, _REENTRY_FIRES, hold=True),
            "hold must be an int >= 1",
            id="hold-bool",
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, {"BTC": _REENTRY_FIRES["BTC"]}, hold=1),
            "same assets",
            id="fires-assets",
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL | {"ETH": [0.6] * 7}, _REENTRY_FIRES, hold=1),
            r"full_long\['ETH'\] has length 7, expected 8",
            id="full-long-length",
        ),
        pytest.param(lambda: reentry_counts_per_year(_ARM_A, _ARM_B, _CLOSE[:5]), "expected 5", id="counts-close-length"),
    ],
)
def test_the_reentry_functions_refuse_inputs_they_cannot_pair(call, match):
    with pytest.raises(AlphaError, match=match):
        call()
```

- [ ] **Step 2: Run them to verify they fail** — `uv run pytest tests/test_alpha_b2.py -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt`: an `ImportError` on `full_long_sizes`, collection stopping.
- [ ] **Step 3: Implement** — in `cli/alpha/b2.py`, `import statistics` after `import math`, and after `scale_positions`:

```python
def full_long_sizes(weights: list[dict[str, float]], levels: list[list[float]], assets: Collection[str]) -> dict[str, list[float]]:
    """Per asset, the position the A2 ensemble holds where every arm's direction is long: the arms' shared inverse-vol weight
    times the mean of their vol-target levels (docs/specs/00139 D3); an asset the basket does not weight yet takes 0."""
    if not levels:
        raise AlphaError("levels must hold at least one arm's vol-target levels")
    n = _check_lengths({"weights": weights} | {f"levels[{i}]": level for i, level in enumerate(levels)})
    return {
        asset: [weights[k].get(asset, 0.0) * statistics.mean(level[k] for level in levels) for k in range(n)] for asset in assets
    }


def reentry_positions(
    asset_positions: dict[str, list[float]], full_long: dict[str, list[float]], fires: dict[str, list[bool]], *, hold: int
) -> dict[str, list[float]]:
    """Arm A's position where it is long; else the full-long size while a re-entry is open. One opens at a close where arm
    A is flat and `fires` is set, stays open through `hold` closes counted from the last close that fired, that close
    included, and closes early where arm A turns long (docs/specs/00139 D3)."""
    if not isinstance(hold, int) or isinstance(hold, bool) or hold < 1:
        raise AlphaError(f"hold must be an int >= 1, got {hold!r}")
    n = _check_paired("asset_positions", asset_positions, "full_long", full_long)
    _check_paired("asset_positions", asset_positions, "fires", fires, n)
    out: dict[str, list[float]] = {}
    for asset, positions in asset_positions.items():
        left, row = 0, []
        for k, p in enumerate(positions):
            if p > 0:
                left = 0
            elif fires[asset][k]:
                left = max(left, hold)
            row.append(full_long[asset][k] if p == 0 and left > 0 and full_long[asset][k] > 0 else p)
            if p == 0 and left > 0:
                left -= 1
        out[asset] = row
    return out


def reentry_counts_per_year(
    asset_positions: dict[str, list[float]], reentered: dict[str, list[float]], close_ts: list[datetime]
) -> dict[str, int]:
    """Asset-stamps flat in arm A and long in arm B, per close year (docs/specs/00139 D6)."""
    _check_paired("asset_positions", asset_positions, "reentered", reentered, len(close_ts))
    counts = dict.fromkeys((str(t.year) for t in close_ts), 0)
    for asset in asset_positions:
        for k, (p, q) in enumerate(zip(asset_positions[asset], reentered[asset])):
            if p == 0 and q > 0:
                counts[str(close_ts[k].year)] += 1
    return counts
```

- [ ] **Step 4: Run them to verify they pass** — `uv run pytest tests/test_alpha_b2.py -k "full_long or reentry" -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt` (measured `11 passed, 136 deselected`), then the whole file.
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b2.py tests/test_alpha_b2.py`; the Global Constraints' `T` over the two paths, one call (measured on the authoring tree as two: `tests/test_research_command.py` `523 passed, 67 deselected in 424.83s`, the other seven `189 passed, 11 deselected in 2.58s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`:

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def full_long_sizes(/def full_long_sizes_gone(/' --mutation 's/weights\[k\]\.get(asset, 0\.0) \* statistics\.mean(level\[k\] for level in levels)/weights[k].get(asset, 0.0) * statistics.median(level[k] for level in levels)/' -- uv run pytest tests/test_alpha_b2.py::test_full_long_sizes_is_the_shared_weight_times_the_mean_of_the_arms_levels -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def reentry_positions(/def reentry_positions_gone(/' --mutation 's/^                left = max(left, hold)$/                left = max(left, hold + 1)/' -- uv run pytest 'tests/test_alpha_b2.py::test_reentry_positions_take_the_full_long_size_where_arm_a_is_flat_through_the_hold[hold-1-open-only-where-it-fires]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def reentry_positions(/def reentry_positions_gone(/' --mutation 's/^                left = 0$/                left = left/' -- uv run pytest 'tests/test_alpha_b2.py::test_reentry_positions_take_the_full_long_size_where_arm_a_is_flat_through_the_hold[hold-3-open-three-closes-from-the-last-firing]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def reentry_positions(/def reentry_positions_gone(/' --mutation 's/row.append(full_long\[asset\]\[k\] if p == 0/row.append(full_long[asset][k - 1] if p == 0/' -- uv run pytest 'tests/test_alpha_b2.py::test_reentry_positions_take_the_full_long_size_where_arm_a_is_flat_through_the_hold[hold-3-open-three-closes-from-the-last-firing]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def reentry_positions(/def reentry_positions_gone(/' --mutation 's/^                left = max(left, hold)$/                left = hold if left == 0 else left/' -- uv run pytest 'tests/test_alpha_b2.py::test_reentry_positions_take_the_full_long_size_where_arm_a_is_flat_through_the_hold[hold-3-open-three-closes-from-the-last-firing]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def reentry_positions(/def reentry_positions_gone(/' --mutation 's/^            if p == 0 and left > 0:$/            if p == 0 and left > 0 and full_long[asset][k] > 0:/' -- uv run pytest 'tests/test_alpha_b2.py::test_reentry_positions_take_the_full_long_size_where_arm_a_is_flat_through_the_hold[hold-1-open-only-where-it-fires]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def reentry_counts_per_year(/def reentry_counts_per_year_gone(/' --mutation 's/^            if p == 0 and q > 0:$/            if q > 0:/' -- uv run pytest tests/test_alpha_b2.py::test_reentry_counts_per_year_counts_flat_asset_stamps_arm_b_holds_and_never_a_long_one -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def full_long_sizes(/def full_long_sizes_gone(/' --mutation 's/^    if not levels:$/    if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_reentry_functions_refuse_inputs_they_cannot_pair[no-levels]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def reentry_positions(/def reentry_positions_gone(/' --mutation 's/ or hold < 1:$/ or hold < 0:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_reentry_functions_refuse_inputs_they_cannot_pair[hold-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  The re-entry fixture moves every clause D3 gives `reentry_positions`, each in an expected value or a probe row above: arm A's position where it is long (BTC 0–1 and 7, ETH 0 and 3); the size of the close itself (BTC's size moving at every flat close, the `[k - 1]` row); 0 where nothing is open (BTC 4–6 at hold 1); a firing while long opening nothing (ETH's at 3, whose hold would reach 4); the hold counted with its firing close (the `hold + 1` row) and from the last firing close (BTC's firings at 2 and 3, the restart row at hold 3); a zero size still counted toward the hold (ETH's firing at 6, the zero-size row at hold 1); arm A turning long closing it (ETH's at 3, the reset row). The `full_long[asset][k] > 0` condition alone moves nothing: a zero size appends 0.0 either way, so no row probes it. Of Task 3's figures over the real sets, arm B's turnover (`TURNOVER_B`) is the one the size moves.

- [ ] **Step 7: Commit** — `feat(alpha): the B2 re-entry's full-long size, its positions held a day from the trigger, and their per-year count`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the four subjects in `cli/research/subjects.py` (D3–D6)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 1's three functions; `cli/research/subjects.py`'s `_capturing_union`, `_b2_over`, `_b2_returns`, `_b2_liq_signal`, `_b2_overlay_arm_a_bar`, `_b2_overlay_metric_keys`, `_b2_overlay_preflight_keys`, `_B2_A2_ARMS`, `_B2_LOOKBACK`, `_B2_COST_PER_SIDE`, `_B2_ARM_A_BAR_KEYS`, `_B2_ARM_A_BAR_FLAGS`, `_DECISIVE_START`, `_N_RESAMPLES`, `_FROM_2021`, `_ASSETS`, `PPY_4H`, `SubjectError`, `Subject` and the names it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_anchor`, `_as_trial`, `_rolling_set`, `_recording`, `_fake_kill_bar`, `_fake_benchmark`, `_fake_head_to_head`, `_not_parquet`, `_b2_overlay_dataset`, `_B2_START`, `_B2_FALLS`, `_B2_FUNDING_FROM`, `_B2_PRINTS`, `_B2_SPIKE_PRINTS`, `_B2_NEVER_SPIKES`, `_B2_SPOILT`, `_B2_ASSETS`, `_B2_OVERLAY_FROM_BAR`, `_B2_OVERLAY_NO_VERDICT`, `_B2_OVERLAY_NEVER_ENGAGED`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_overlay_metric_keys`, `_overlay_preflight_keys`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`. Produces the four subjects, `_b2_reentry_inputs`, `_b2_reentry_engagement` and `_b2_funding_signal`, which Task 3's data-gated test imports.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - `import operator` after `import math`; the `from cli.alpha.b2 import (` block gains `funding_grid_feature,` after `derisk_scales,` and `reentry_counts_per_year,` and `reentry_positions,` after `ratio_zscore_grid_features,`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, before its last line:

```python
    for name, (signal_key, *_) in _B2_REENTRIES.items():
        assert subjects.SUBJECTS[name].metric_keys == _overlay_metric_keys(signal_key)
        assert subjects.SUBJECTS[f"{name}-preflight"].metric_keys == _overlay_preflight_keys(signal_key)
```

  - after `test_each_b2_overlay_reads_its_signal_off_its_own_columns` and before `def _ruled_signal(`:

```python
_B2_REENTRY_SPEC = "docs/specs/00139-b2-reentries-design.md"
# Spec 00139's two trials: each signal's key, threshold, comparison, hold and count, typed from the spec, never read off a
# subject.
_B2_REENTRIES = {
    "b2-liq-reentry": ("binperp_liq_long_z30d", 2.5, operator.gt, 1, 5),
    "b2-funding-reentry": ("binperp_funding_z30d", -2.0, operator.lt, 6, 6),
}


def _reentry_signal(name: str):
    return {"b2-liq-reentry": subjects._b2_liq_signal, "b2-funding-reentry": subjects._b2_funding_signal}[name]


def _b2_reentry_dataset(
    tmp_path: Path, *, start: datetime = _B2_START, flat: bool = False, from_bar: int = _B2_OVERLAY_FROM_BAR
) -> Path:
    """`_b2_overlay_dataset`'s sets and a `derivatives-funding` set whose 8h prints open 47 days before `_B2_START`; every perp
    but one dips far below its usual rate inside the second fall, each from its own print, so each re-entry takes flat stamps
    on several assets and none on `_B2_NEVER_SPIKES`."""
    root = _b2_overlay_dataset(tmp_path, start=start, flat=flat, from_bar=from_bar)
    stamps = [_B2_FUNDING_FROM + timedelta(hours=8 * j) for j in range(_B2_PRINTS)]
    second_fall = _B2_START + timedelta(hours=4 * _B2_FALLS[1][0])
    for i, asset in enumerate(_B2_ASSETS):
        rates = [0.0001 * (1 + 0.5 * math.sin(j + i)) for j in range(_B2_PRINTS)]
        if asset != _B2_NEVER_SPIKES:
            first = stamps.index(second_fall + timedelta(hours=8 * i))
            rates[first : first + _B2_SPIKE_PRINTS] = [-0.003] * _B2_SPIKE_PRINTS
        frame = pl.DataFrame(
            {"ts": stamps, "funding_rate": rates, "interval_hours": [8] * _B2_PRINTS},
            schema={"ts": pl.Datetime("us", "UTC"), "funding_rate": pl.Float64, "interval_hours": pl.Int64},
        )
        write_parquet(frame, root / "derivatives-funding" / PERP_SYMBOLS[asset] / "funding.parquet")
    return root


def _reentry_inputs(name: str, root: Path):
    _, threshold, fire, hold, _ = _B2_REENTRIES[name]
    return subjects._b2_reentry_inputs(
        name, _reentry_signal(name), fire, hold, threshold, ObservedReader(root), "ohlc-test", None, False
    )


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_each_b2_reentry_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    signal_key, _, _, _, count = _B2_REENTRIES[name]
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    builder = f"_build_{name.replace('-', '_')}"
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B2_REENTRY_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is getattr(subjects, builder) and trial.metric_keys == _overlay_metric_keys(signal_key)
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_reentry_verdict, _B2_OVERLAY_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", count)
    assert (preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == ((240,), _B2_ASSETS, _B2_REENTRY_SPEC, (42,))
    assert preflight.build is getattr(subjects, f"{builder}_preflight")
    assert preflight.metric_keys == _overlay_preflight_keys(signal_key)
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


@pytest.mark.parametrize("name", sorted({*_B2_REENTRIES, *(f"{name}-preflight" for name in _B2_REENTRIES)}))
def test_each_b2_reentry_subject_builds_on_the_specs_signal_comparison_hold_threshold_and_count(monkeypatch, name):
    trial = name.removesuffix("-preflight")
    signal_key, threshold, fire, hold, count = _B2_REENTRIES[trial]
    compute = subjects._b2_reentry_metrics if name == trial else subjects._b2_reentry_preflight_metrics
    builds = []
    monkeypatch.setattr(subjects, "_b2_reentry_build", lambda *arguments: builds.append(arguments) or {})
    reader, window = object(), ("2024-01-01", "2024-06-30")

    subjects.SUBJECTS[name].build(reader, "ohlc-test", window, as_of="2026-10-03", accept_holes=True)

    instrument = (name, signal_key, _reentry_signal(trial), fire, hold, threshold, compute, count)
    assert builds == [(*instrument, reader, "ohlc-test", window, "2026-10-03", True)]


# Adopting on every key the rule reads, its drawdown a twentieth above arm A's; the full-window head-to-head and the
# block-102 cell set against the verdict, so a rule reading either in place of the primary read or the headline cell moves
# the first row.
_B2_REENTRY_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2013": 0, "2023": 4},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "spa_p_decisive_b102_s42": 0.9,
    "max_drawdown_reduction_pct": -5.0,
}


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-outperforms-significantly-a-twentieth-more-drawdown"),
        pytest.param({"head_to_head_spa_p_primary": 0.0499}, "adopt", id="row-1-p-at-0.0499"),
        pytest.param({"max_drawdown_reduction_pct": -20.0}, "adopt", id="row-1-drawdown-at-exactly-1.2-times"),
        pytest.param({"max_drawdown_reduction_pct": 5.0}, "adopt", id="row-1-drawdown-below-arm-as"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="row-2-p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="row-2-outperforms-insignificantly"),
        pytest.param({"max_drawdown_reduction_pct": -20.001}, "park", id="row-2-significant-but-drawdown-past-1.2-times"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": 1e-12, "head_to_head_spa_p_primary": 0.9, "max_drawdown_reduction_pct": -80.0},
            "park",
            id="row-2-a-hair-above-arm-a",
        ),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="row-3-mean-at-exactly-0"),
        pytest.param({"head_to_head_mean_outperf_primary": -0.001}, "reject", id="row-3-underperforms-from-the-start"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001, "head_to_head_spa_p_full": 0.01},
            "reject",
            id="row-3-outperforms-over-the-full-window-alone",
        ),
        pytest.param({"passes": 0}, "reject", id="row-4-arm-b-fails-its-bar"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_OVERLAY_NEVER_ENGAGED, None, id="the-re-entry-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_OVERLAY_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
    ],
)
def test_the_b2_reentry_rule_maps_the_matrix_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b2_reentry_verdict({**_B2_REENTRY_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_a_b2_reentrys_inputs_add_the_full_long_size_where_arm_a_is_flat_and_its_signal_fires(tmp_path, monkeypatch, name):
    _, threshold, fire, hold, _ = _B2_REENTRIES[name]
    sizes = _recording(monkeypatch, "full_long_sizes", lambda arguments, result: result)
    reentries = _recording(monkeypatch, "reentry_positions", lambda arguments, result: result)
    root = _b2_reentry_dataset(tmp_path)

    inputs = _reentry_inputs(name, root)

    overlay = subjects._b2_overlay_inputs(name, _reentry_signal(name), 2.5, ObservedReader(root), "ohlc-test", None, False)
    assert (inputs.h4_ts, inputs.close, inputs.arm_a, inputs.signal) == (
        overlay.h4_ts,
        overlay.close,
        overlay.arm_a,
        overlay.signal,
    )
    fed = _ffill_btc(inputs.h4_prices)
    levels = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=180,
                basket_lookback=180,
                periods_per_year=2190,
            ),
        )["vol_target_positions"]
        for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    ]
    ((size_arguments, full_long),) = sizes
    assert size_arguments == {"weights": _inverse_vol_weights(fed, lookback=180), "levels": levels, "assets": _B2_ASSETS}
    ((reentry_arguments, arm_b),) = reentries
    fires = {a: [z is not None and fire(z, threshold) for z in inputs.signal[a]] for a in _B2_ASSETS}
    assert reentry_arguments == {"asset_positions": inputs.arm_a, "full_long": full_long, "fires": fires, "hold": hold}
    assert (inputs.full_long, inputs.arm_b, inputs.threshold) == (full_long, arm_b, threshold)
    reentered = {a: sum(p == 0 and q > 0 for p, q in zip(inputs.arm_a[a], arm_b[a])) for a in _B2_ASSETS}
    assert reentered[_B2_NEVER_SPIKES] == 0 < sum(reentered.values())


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_a_b2_reentrys_metrics_are_the_overlays_with_its_positions_its_start_and_its_engagement(tmp_path, monkeypatch, name):
    signal_key, threshold, _, _, count = _B2_REENTRIES[name]
    inputs = _reentry_inputs(name, _b2_reentry_dataset(tmp_path))
    start = subjects._b2_reentry_start(inputs)
    k21 = next(k for k, t in enumerate(inputs.close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    defined = next(k for k in range(len(inputs.close)) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS))
    assert start == max(defined, k21) and 0 < start < len(inputs.close) - 2
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b2_reentry_metrics(inputs, signal_key=signal_key, n_trials=count)

    assert set(metrics) == _overlay_metric_keys(signal_key) and {arguments["n_trials"] for arguments, _ in bars} == {count}
    # The overlays' metrics over the same arm A and signal, their arm B, start and engagement the re-entry's:
    # `_b2_overlay_metrics`' own test proves that body.
    overlay = subjects._B2OverlayInputs(inputs.h4_ts, inputs.h4_prices, inputs.close, inputs.arm_a, inputs.signal, {}, threshold)
    monkeypatch.setattr(subjects, "scale_positions", lambda positions, scales: inputs.arm_b)
    monkeypatch.setattr(subjects, "_b2_overlay_start", lambda _: start)
    monkeypatch.setattr(subjects, "_b2_overlay_engagement", lambda _, key: subjects._b2_reentry_engagement(inputs, key))
    assert subjects._b2_overlay_metrics(overlay, signal_key=signal_key, n_trials=count) == metrics
    assert metrics["primary_returns"] == len(inputs.close) - start and metrics["threshold"] == threshold


def test_where_no_signal_fires_a_b2_reentrys_arm_b_is_arm_a_bit_for_bit(tmp_path, monkeypatch):
    inputs = _reentry_inputs("b2-liq-reentry", _b2_reentry_dataset(tmp_path))
    n = len(inputs.close)
    calm = {a: [0.0] * n for a in _B2_ASSETS}
    quiet = {a: [False] * n for a in _B2_ASSETS}
    inputs = inputs._replace(signal=calm, arm_b=reentry_positions(inputs.arm_a, inputs.full_long, quiet, hold=1))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b2_reentry_metrics(inputs, signal_key="binperp_liq_long_z30d", n_trials=5)

    assert [arguments["book_net_of_cost"] == arguments["benchmark_net_of_cost"] for arguments, _ in head_to_heads] == [True] * 2
    assert (
        metrics["stamps_positions_differ"],
        metrics["turnover_b"],
        metrics["max_drawdown"],
        metrics["max_drawdown_reduction_pct"],
    ) == (0, metrics["turnover_a"], metrics["arm_a_max_drawdown"], 0.0)
    k21 = next(k for k, t in enumerate(inputs.close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert metrics["primary_returns"] == n - k21 and set(metrics["engaged_per_year"].values()) == {0}


@pytest.mark.parametrize(("left", "refused"), [(0, True), (1, True), (2, False)])
def test_a_b2_reentry_refuses_fewer_than_2_returns_from_its_start(tmp_path, monkeypatch, left, refused):
    inputs = _reentry_inputs("b2-liq-reentry", _b2_reentry_dataset(tmp_path))
    n = len(inputs.close)
    inputs = inputs._replace(signal={a: [None] * (n - left) + [0.0] * left for a in _B2_ASSETS})
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    cause = (
        f"{left} of its return indices lie from the read's start, every asset's binperp_liq_long_z30d held and 2021 begun, and "
        "the head-to-head from it needs 2"
    )

    try:
        subjects._b2_reentry_metrics(inputs, signal_key="binperp_liq_long_z30d", n_trials=5)
        raised = ""
    except ValidationError as exc:
        raised = str(exc)

    assert (raised == cause) is refused


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_a_b2_reentrys_preflight_reads_arm_a_and_the_engagement_and_never_a_return_of_arm_b(tmp_path, monkeypatch, name):
    signal_key, threshold, fire, hold, count = _B2_REENTRIES[name]
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    reads = _recording(monkeypatch, "_b2_reentry_inputs", lambda arguments, result: result)
    nets = _recording(monkeypatch, "net_of_cost", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS[f"{name}-preflight"].build(ObservedReader(_b2_reentry_dataset(tmp_path)), "ohlc-test", None)

    ((read, inputs),) = reads
    assert (read["subject"], read["read_signal"], read["fire"], read["hold"], read["threshold"]) == (
        f"{name}-preflight",
        _reentry_signal(name),
        fire,
        hold,
        threshold,
    )
    assert [arguments["asset_positions"] is inputs.arm_a for arguments, _ in nets] == [True, True]
    returns = {a: _asset_returns(_ffill_btc(inputs.h4_prices)[a]) for a in _B2_ASSETS}
    net_a, net_a_x15 = (net_of_cost(inputs.arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.close)
    start = subjects._b2_reentry_start(inputs)
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
    reentered = {a: sum(p == 0 and q > 0 for p, q in zip(inputs.arm_a[a], inputs.arm_b[a])) for a in _B2_ASSETS}
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        "engaged_per_asset": reentered,
        "engaged_per_year": reentry_counts_per_year(inputs.arm_a, inputs.arm_b, inputs.close),
        f"{signal_key}_coverage": {
            a: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(inputs.close, inputs.signal[a]).items()}
            for a in _B2_ASSETS
        },
        "primary_returns": n - start,
        "threshold": threshold,
    }
    assert set(metrics) == _overlay_preflight_keys(signal_key) and 0 < start < n - 2
    assert sum(reentered.values()) == sum(metrics["engaged_per_year"].values()) > 0
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0


@pytest.mark.parametrize("name", sorted({*_B2_REENTRIES, *(f"{name}-preflight" for name in _B2_REENTRIES)}))
def test_a_b2_reentry_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
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


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_a_b2_reentry_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    count = _B2_REENTRIES[name][4]
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_reentry_inputs", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-183", "--family", "B2", "--n-trials", str(count + 1)]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials {count + 1} is not {count}, the count {name} declares and deflates at: pass --n-trials {count}"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.parametrize(
    ("from_bar", "cause"),
    [
        pytest.param(
            1_458,
            "0 of its return indices lie from the read's start, every asset's binperp_liq_long_z30d held and 2021 begun, and the "
            "head-to-head from it needs 2",
            id="no-index-from-the-start",
        ),
        pytest.param(
            1_452,
            "arm A never draws down from the read's start, so max_drawdown_reduction_pct divides by zero",
            id="arm-a-never-draws-down-from-the-start",
        ),
    ],
)
def test_a_b2_reentry_trial_refuses_a_start_it_cannot_evaluate_before_any_bar(tmp_path, monkeypatch, from_bar, cause):
    _anchor(monkeypatch, _b2_reentry_dataset(tmp_path, from_bar=from_bar))
    kill_bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    args = ["research", "eval", "--subject", "b2-liq-reentry", "--dataset", "ohlc-test", *_as_trial("b2-liq-reentry", tmp_path)]

    result = runner.invoke(app, args)

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"b2-liq-reentry over the full history: {cause}" in result.output
    assert kill_bars == []


@pytest.mark.parametrize(
    ("name", "relpath", "spoil", "cause"),
    [
        pytest.param(
            "b2-liq-reentry",
            "liquidations-daily/SOL/daily.parquet",
            lambda path: pl.read_parquet(path).drop("long_usd").write_parquet(path),
            '"long_usd" not found',
            id="liquidation-daily",
        ),
        pytest.param(
            "b2-funding-reentry-preflight",
            f"derivatives-funding/{_B2_SPOILT}/funding.parquet",
            _not_parquet,
            "File out of specification",
            id="funding-preflight",
        ),
    ],
)
def test_a_b2_reentry_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it(
    tmp_path, monkeypatch, name, relpath, spoil, cause
):
    root = _b2_reentry_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output


@pytest.mark.parametrize("name", sorted(_B2_REENTRIES))
def test_each_b2_reentry_reads_its_signal_off_its_own_columns(tmp_path, name):
    root = _b2_reentry_dataset(tmp_path)
    h4_ts, _ = subjects._capturing_union(ObservedReader(root), "ohlc-test", 240, None, None, False)
    expected = {}
    for asset in _B2_ASSETS:
        if name == "b2-liq-reentry":
            daily = pl.read_parquet(root / "liquidations-daily" / asset / "daily.parquet")
            expected[asset] = daily_zscore_grid_feature(daily["ts"].to_list(), daily["long_usd"].to_list(), h4_ts)
        else:
            prints = pl.read_parquet(root / "derivatives-funding" / PERP_SYMBOLS[asset] / "funding.parquet")
            columns = (prints[c].to_list() for c in ("ts", "funding_rate", "interval_hours"))
            expected[asset] = funding_grid_feature(*columns, h4_ts, config=B2Config())

    signal = _reentry_signal(name)(ObservedReader(root), h4_ts)

    assert signal == expected
    _, threshold, fire, _, _ = _B2_REENTRIES[name]
    assert sum(v is not None and fire(v, threshold) for v in signal["BTC"]) > 0
```

  - `_RULED_FIXTURES` gains `"b2-funding-reentry": _b2_reentry_dataset,` after `"b2-funding-derisk-full": _b2_dataset,` and `"b2-liq-reentry": _b2_reentry_dataset,` after `"b2-liq-derisk": _b2_overlay_dataset,`; `_DECLARED_COUNT` gains `"b2-funding-reentry": "_B2_FUNDING_REENTRY_N_TRIALS",` after `"b2-funding-derisk-full": "_B2_FULL_N_TRIALS",` and `"b2-liq-reentry": "_B2_LIQ_REENTRY_N_TRIALS",` after `"b2-liq-derisk": "_B2_LIQ_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b2-funding-reentry": ("B2", 6),` after `"b2-funding-derisk-full": ("B2", 1),` and `"b2-liq-reentry": ("B2", 5),` after `"b2-liq-derisk": ("B2", 4),`; `_CONTRACT_DATASETS` gains, after its `"b2-liq-tape-reading"` entry:

```python
    "b2-liq-reentry": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
    "b2-liq-reentry-preflight": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
    "b2-funding-reentry": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
    "b2-funding-reentry-preflight": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),
```

  **Author's call** — the wiring test proves `_b2_reentry_metrics` against `_b2_overlay_metrics` itself, run on the same arm A and signal with `scale_positions` returning the re-entry's arm B, `_b2_overlay_start` the re-entry's start and `_b2_overlay_engagement` the re-entry's engagement, under argument-derived stand-ins for the bars, the benchmark and the head-to-heads: equal dicts prove D6's "`_b2_overlay_metrics`' body" with those three substituted, `_b2_overlay_metrics`' own test proving that body; the fixture `_b2_reentry_dataset` adds to `_b2_overlay_dataset`'s sets a funding set whose every perp but `_B2_NEVER_SPIKES` dips to −0.003 for six prints inside the second fall, so each re-entry takes flat stamps on several assets and none on `_B2_NEVER_SPIKES` (measured on the authoring tree: the liquidation re-entry on ADA, DOGE, DOT, ETH, LINK, LTC and SOL, the funding one on DOT, ETH, LINK, LTC and SOL); the start refusals ride `from_bar` 1,458 and 1,452, measured to leave the liquidation signal's read 0 return indices and 2 with arm A never drawing down; the read's start moves a day at a time with `from_bar`, so the 1-index row is a direct call on `_b2_reentry_metrics` with a signal defined on the last return index alone. The instrument a subject runs on — its signal reader, comparison, hold and threshold, beside its signal key, compute and count — is fixed by the spec's D3–D5 and written in this plan's code in three places: the four `_build_` wrappers, the tests' `_B2_REENTRIES` and Task 3's `_TRIGGERS` and `THRESHOLD`; the builders' test holds every wrapper, trial and twin alike, to `_B2_REENTRIES`, Task 3's cases hold `_TRIGGERS` and `THRESHOLD` to the measured basis, and the pre-flight's (c) holds the twin's wrapper, and through the builders' test its trial's, to the same basis before the trial's `--register`. Its threshold and hold are written in words in six more, which no test, data case or pre-flight step holds, a read against D3–D4 their only check: the Global Constraints' first item, the README row (step 4), the conventions entry (Task 3 step 5), the two trials' notes (Tasks 5–6 step 4), each its record's `notes` once the run appends it, and Task 8's entry; the notes are the controller's to read against D3–D4 before each run.

- [ ] **Step 2: Run them to verify they fail** — `uv run pytest tests/test_research_command.py -k "reentry" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt`: collection completes and every selected case fails at its call, on a name `subjects` lacks — `_b2_reentry_verdict`, `_b2_funding_signal`, `_B2_LIQ_REENTRY_N_TRIALS`, a key of `SUBJECTS` — or on a subject the CLI does not know (measured on the authoring tree: `48 failed, 590 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — `import operator` after `import math`; the `from cli.alpha.b2 import (` block gains `full_long_sizes,` after `event_contrast,` and `reentry_counts_per_year,` and `reentry_positions,` after `ratio_zscore_grid_features,`; after `_b2_overlay_preflight_keys` and before the comment `# docs/specs/00138 D12: the 1-minute tape's event study, read on ohlc-rolling: a frozen set misses the tape's span.`:

```python
# docs/specs/00139 D3-D6: B2's trials 6-7, a full-long re-entry where arm A is flat, held a day from its trigger.
_B2_LIQ_REENTRY_THRESHOLD = 2.5
_B2_LIQ_REENTRY_HOLD = 1
_B2_LIQ_REENTRY_N_TRIALS = 5  # docs/specs/00139 D5: each count fixed by the spec's hash; a different one is a new subject
_B2_FUNDING_REENTRY_THRESHOLD = -2.0
_B2_FUNDING_REENTRY_HOLD = 6
_B2_FUNDING_REENTRY_N_TRIALS = 6


class _B2ReentryInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    arm_a: dict[str, list[float]]
    signal: dict[str, list[float | None]]
    full_long: dict[str, list[float]]
    arm_b: dict[str, list[float]]
    threshold: float


def _b2_funding_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    """Trial 2's funding z-score, `_b2_inputs`' own loop, read whole (docs/specs/00139 D4)."""
    config = B2Config()
    signal = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/funding.parquet"
        try:
            prints = reader.read_series("derivatives-funding", relpath)
            signal[asset] = funding_grid_feature(
                prints["ts"].to_list(), prints["funding_rate"].to_list(), prints["interval_hours"].to_list(), h4_ts, config=config
            )
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-funding/{relpath}: {exc}") from exc
    return signal


def _b2_reentry_inputs(
    subject: str,
    read_signal: Callable[[ObservedReader, list[datetime]], dict[str, list[float | None]]],
    fire: Callable[[float, float], bool],
    hold: int,
    threshold: float,
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    accept_holes: bool,
) -> _B2ReentryInputs:
    """Arm A's positions, the signal, the full-long size and arm B's positions, and no return of either arm: the
    pre-flight reads this half alone."""
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
    # `_b2_overlay_inputs`' arm A, its books kept for the levels the full-long size reads.
    fed = _ffill_btc(h4_prices)
    books = [
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
        )
        for lookbacks, target_vol in _B2_A2_ARMS
    ]
    arm_a = {a: [statistics.mean(book["asset_positions"][a][k] for book in books) for k in range(len(h4_ts) - 1)] for a in _ASSETS}
    weights = _inverse_vol_weights(fed, lookback=_B2_LOOKBACK)
    full_long = full_long_sizes(weights, [book["vol_target_positions"] for book in books], _ASSETS)
    fires = {a: [z is not None and fire(z, threshold) for z in signal[a]] for a in _ASSETS}
    arm_b = reentry_positions(arm_a, full_long, fires, hold=hold)
    return _B2ReentryInputs(h4_ts, h4_prices, close, arm_a, signal, full_long, arm_b, threshold)


def _b2_reentry_start(inputs: _B2ReentryInputs) -> int:
    """The later of the first return index every asset's signal holds and the first closing at or after 2021-01-01, the
    length where either is missing (docs/specs/00139 D5)."""
    n = len(inputs.close)
    defined = next((k for k in range(n) if all(inputs.signal[a][k] is not None for a in _ASSETS)), n)
    k21 = next((k for k, t in enumerate(inputs.close) if t >= _FROM_2021), n)
    return max(defined, k21)


def _b2_reentry_engagement(inputs: _B2ReentryInputs, signal_key: str) -> dict:
    arm_a, arm_b, close = inputs.arm_a, inputs.arm_b, inputs.close
    return {
        "engaged_per_asset": {a: sum(p == 0 and q > 0 for p, q in zip(arm_a[a], arm_b[a])) for a in _ASSETS},
        "engaged_per_year": reentry_counts_per_year(arm_a, arm_b, close),
        f"{signal_key}_coverage": {
            asset: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(close, values).items()}
            for asset, values in inputs.signal.items()
        },
        "primary_returns": len(close) - _b2_reentry_start(inputs),
        "threshold": inputs.threshold,
    }


def _b2_reentry_metrics(inputs: _B2ReentryInputs, *, signal_key: str, n_trials: int) -> dict:
    """`_b2_overlay_metrics`' body with arm B the re-entry's positions, the read's start the re-entry's and the
    engagement the re-entered stamps (docs/specs/00139 D6)."""
    arm_a, arm_b, close = inputs.arm_a, inputs.arm_b, inputs.close
    start = _b2_reentry_start(inputs)
    if len(close) - start < 2:
        raise ValidationError(
            f"{len(close) - start} of its return indices lie from the read's start, every asset's {signal_key} held and 2021 "
            "begun, and the head-to-head from it needs 2"
        )
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
        raise ValidationError("arm A never draws down from the read's start, so max_drawdown_reduction_pct divides by zero")
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
    engagement = _b2_reentry_engagement(inputs, signal_key)
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


def _b2_reentry_preflight_metrics(inputs: _B2ReentryInputs, *, signal_key: str, n_trials: int) -> dict:
    """Arm A's anchors and bar and the engagement (docs/specs/00139 D6): no return of arm B."""
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
        **_b2_reentry_engagement(inputs, signal_key),
    }


def _b2_reentry_build(
    subject: str,
    signal_key: str,
    read_signal: Callable[[ObservedReader, list[datetime]], dict[str, list[float | None]]],
    fire: Callable[[float, float], bool],
    hold: int,
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
        inputs = _b2_reentry_inputs(subject, read_signal, fire, hold, threshold, reader, dataset, window, accept_holes)
        return compute(inputs, signal_key=signal_key, n_trials=n_trials)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b2_liq_reentry(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_reentry_build(
        "b2-liq-reentry",
        "binperp_liq_long_z30d",
        _b2_liq_signal,
        operator.gt,
        _B2_LIQ_REENTRY_HOLD,
        _B2_LIQ_REENTRY_THRESHOLD,
        _b2_reentry_metrics,
        _B2_LIQ_REENTRY_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_liq_reentry_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_reentry_build(
        "b2-liq-reentry-preflight",
        "binperp_liq_long_z30d",
        _b2_liq_signal,
        operator.gt,
        _B2_LIQ_REENTRY_HOLD,
        _B2_LIQ_REENTRY_THRESHOLD,
        _b2_reentry_preflight_metrics,
        _B2_LIQ_REENTRY_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_funding_reentry(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_reentry_build(
        "b2-funding-reentry",
        "binperp_funding_z30d",
        _b2_funding_signal,
        operator.lt,
        _B2_FUNDING_REENTRY_HOLD,
        _B2_FUNDING_REENTRY_THRESHOLD,
        _b2_reentry_metrics,
        _B2_FUNDING_REENTRY_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_funding_reentry_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_reentry_build(
        "b2-funding-reentry-preflight",
        "binperp_funding_z30d",
        _b2_funding_signal,
        operator.lt,
        _B2_FUNDING_REENTRY_HOLD,
        _B2_FUNDING_REENTRY_THRESHOLD,
        _b2_reentry_preflight_metrics,
        _B2_FUNDING_REENTRY_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


# docs/specs/00139 D5's matrix: the head-to-head from the read's start decides, the drawdown bounded at 1.2 x arm A's; a
# change to it is a new spec and a new trial, never an edit here.
def _b2_reentry_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["engaged_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        bounded = m["max_drawdown_reduction_pct"] >= -20.0
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 and bounded else "park"
    return "reject"
```

  and `SUBJECTS` gains, after its `"b2-liq-tape-reading"` entry:

```python
    "b2-liq-reentry": Subject(
        "b2-liq-reentry",
        (240,),
        _ASSETS,
        _build_b2_liq_reentry,
        spec="docs/specs/00139-b2-reentries-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_liq_long_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_reentry_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_LIQ_REENTRY_N_TRIALS,
    ),
    "b2-liq-reentry-preflight": Subject(
        "b2-liq-reentry-preflight",
        (240,),
        _ASSETS,
        _build_b2_liq_reentry_preflight,
        spec="docs/specs/00139-b2-reentries-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_liq_long_z30d"),
        seeds=(42,),
    ),
    "b2-funding-reentry": Subject(
        "b2-funding-reentry",
        (240,),
        _ASSETS,
        _build_b2_funding_reentry,
        spec="docs/specs/00139-b2-reentries-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_funding_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_reentry_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_FUNDING_REENTRY_N_TRIALS,
    ),
    "b2-funding-reentry-preflight": Subject(
        "b2-funding-reentry-preflight",
        (240,),
        _ASSETS,
        _build_b2_funding_reentry_preflight,
        spec="docs/specs/00139-b2-reentries-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_funding_z30d"),
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `) or \`b2-liq-tape-reading\` (` becomes `), \`b2-liq-tape-reading\` (`, and the row's closing `` `--reading`). | `` becomes:

```markdown
`--reading`), `b2-liq-reentry` (the A2 4h ensemble against the same ensemble taking an asset it holds flat at the position it would hold were every arm long, for the day after a day whose 30-day z-score of long-side liquidated notional exceeds 2.5; the 4h series of `--dataset`, a frozen set only, and the `liquidations-daily` set read whole), `b2-liq-reentry-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the flat stamps the re-entry takes, with no return of the re-entered book; it has no rule, so its run is kept with `--reading`), `b2-funding-reentry` (the same comparison re-entering for a day from the last 4h close at which the asset's 30-day funding z-score reads below -2; the 4h series of `--dataset`, a frozen set only, and the `derivatives-funding` set's ten funding files read whole) or `b2-funding-reentry-preflight` (that comparison's instrument check, as `b2-liq-reentry-preflight`'s; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the cases measured at 10 s or more on the authoring tree (setup counted with the call; the shared-default, evaluate and deflate rows are the existing tests' new rows):

```text
tests/test_research_command.py::test_a_b2_reentry_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[arm-a-never-draws-down-from-the-start]
tests/test_research_command.py::test_a_b2_reentrys_inputs_add_the_full_long_size_where_arm_a_is_flat_and_its_signal_fires[b2-funding-reentry]
tests/test_research_command.py::test_a_b2_reentrys_inputs_add_the_full_long_size_where_arm_a_is_flat_and_its_signal_fires[b2-liq-reentry]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-funding-reentry]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-liq-reentry]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-funding-reentry-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-funding-reentry-preflight-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-liq-reentry-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-liq-reentry-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-funding-reentry-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-funding-reentry]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-reentry-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-reentry]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — the selection `-k "reentry or ruled_subjects or declares_the_metric_keys"` in two parts, each one plain blocking call, `timeout` 600000 ms: `uv run pytest tests/test_research_command.py -k "reentry and every" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt-1` (measured `38 passed, 636 deselected` in 3 min 38 s), then `uv run pytest tests/test_research_command.py -k "(reentry or ruled_subjects or declares_the_metric_keys) and not (reentry and every)" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt-2` (measured `56 passed, 618 deselected` in 4 min 4 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' `T` over the four paths in three parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms: `tests/test_research_command.py -k "not reentry"` (`--basetemp=.tmp/plan-00139/pt-1`, measured on the authoring tree `523 passed, 151 deselected in 420.94s`), `tests/test_research_command.py -k reentry` (`pt-2`, measured `71 passed, 603 deselected in 89.33s`) and the other thirty-one direct readers (`pt-3`, measured `4114 passed, 50 deselected in 119.46s`); `uv run pre-commit run -a` until clean; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`; the shared-default, evaluate, deflate, contract and tracked-spec rows are new rows of existing tests, not new guards, and are not probed; the slow cases each recorded `probe skipped: slow case`:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_reentry(/def _build_b2_liq_reentry_gone(/' --mutation 's/^        n_trials=_B2_LIQ_REENTRY_N_TRIALS,$/        n_trials=_B2_FUNDING_REENTRY_N_TRIALS,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_reentry_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-liq-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_reentry(/def _build_b2_funding_reentry_gone(/' --mutation '/^def _build_b2_funding_reentry(/,/^def /s/        operator.lt,/        operator.gt,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_reentry_subject_builds_on_the_specs_signal_comparison_hold_threshold_and_count[b2-funding-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_reentry(/def _build_b2_funding_reentry_gone(/' --mutation '/^def _build_b2_funding_reentry(/,/^def /s/        _B2_FUNDING_REENTRY_HOLD,/        _B2_LIQ_REENTRY_HOLD,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_reentry_subject_builds_on_the_specs_signal_comparison_hold_threshold_and_count[b2-funding-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_reentry(/def _build_b2_funding_reentry_gone(/' --mutation '/^def _build_b2_funding_reentry(/,/^def /s/        _b2_funding_signal,/        _b2_liq_signal,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_reentry_subject_builds_on_the_specs_signal_comparison_hold_threshold_and_count[b2-funding-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_reentry(/def _build_b2_liq_reentry_gone(/' --mutation '/^def _build_b2_liq_reentry(/,/^def /s/        _B2_LIQ_REENTRY_HOLD,/        _B2_FUNDING_REENTRY_HOLD,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_reentry_subject_builds_on_the_specs_signal_comparison_hold_threshold_and_count[b2-liq-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_reentry(/def _build_b2_liq_reentry_gone(/' --mutation '/^def _build_b2_liq_reentry(/,/^def /s/        _B2_LIQ_REENTRY_THRESHOLD,/        _B2_FUNDING_REENTRY_THRESHOLD,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_reentry_subject_builds_on_the_specs_signal_comparison_hold_threshold_and_count[b2-liq-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_verdict(/def _b2_reentry_verdict_gone(/' --mutation 's/^        bounded = m\["max_drawdown_reduction_pct"\] >= -20.0$/        bounded = m["max_drawdown_reduction_pct"] > -20.0/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_reentry_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-drawdown-at-exactly-1.2-times]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_verdict(/def _b2_reentry_verdict_gone(/' --mutation 's/head_to_head_spa_p_primary"\] < 0.05 and bounded/head_to_head_spa_p_primary"] <= 0.05 and bounded/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_reentry_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-2-p-at-exactly-0.05]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_verdict(/def _b2_reentry_verdict_gone(/' --mutation 's/^    if m\["head_to_head_mean_outperf_primary"\] > 0:$/    if m["head_to_head_mean_outperf_primary"] >= 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_reentry_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-mean-at-exactly-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_verdict(/def _b2_reentry_verdict_gone(/' --mutation '/^def _b2_reentry_verdict(/,/^    return "reject"$/s/not any(m\["engaged_per_year"\]/not all(m["engaged_per_year"]/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_reentry_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-a-twentieth-more-drawdown]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_metrics(/def _b2_reentry_metrics_gone(/' --mutation '/^def _b2_reentry_metrics(/,/^def /s/    net_b = net_of_cost(arm_b, returns, cost_per_side=cost)/    net_b = net_of_cost(arm_a, returns, cost_per_side=cost)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_reentrys_metrics_are_the_overlays_with_its_positions_its_start_and_its_engagement[b2-liq-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_start(/def _b2_reentry_start_gone(/' --mutation 's/^    return max(defined, k21)$/    return min(defined, k21)/' -- uv run pytest tests/test_research_command.py::test_where_no_signal_fires_a_b2_reentrys_arm_b_is_arm_a_bit_for_bit -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_metrics(/def _b2_reentry_metrics_gone(/' --mutation '/^def _b2_reentry_metrics(/,/^def /s/    if len(close) - start < 2:/    if len(close) - start < 1:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_reentry_refuses_fewer_than_2_returns_from_its_start[1-True]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_reentry_preflight(/def _build_b2_funding_reentry_preflight_gone(/' --mutation '/^def _build_b2_funding_reentry_preflight(/,/^def /s/        _B2_FUNDING_REENTRY_HOLD,/        _B2_LIQ_REENTRY_HOLD,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_reentrys_preflight_reads_arm_a_and_the_engagement_and_never_a_return_of_arm_b[b2-funding-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_build(/def _b2_reentry_build_gone(/' --mutation '/^def _b2_reentry_build(/,/^def /s/    if as_of is not None:/    if as_of is None:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_reentry_subject_refuses_as_of_before_any_read[b2-funding-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_reentry(/def _build_b2_liq_reentry_gone(/' --mutation 's/^        n_trials=_B2_LIQ_REENTRY_N_TRIALS,$/        n_trials=_B2_FUNDING_REENTRY_N_TRIALS,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_reentry_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-liq-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_metrics(/def _b2_reentry_metrics_gone(/' --mutation '/^def _b2_reentry_metrics(/,/^def /s/    if len(close) - start < 2:/    if len(close) - start < 0:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_reentry_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[no-index-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_funding_signal(/def _b2_funding_signal_gone(/' --mutation '/^def _b2_funding_signal(/,/^def /s/raise SubjectError(f"derivatives-funding\/{relpath}: {exc}") from exc/raise SubjectError(f"derivatives-funding: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_reentry_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[funding-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_funding_signal(/def _b2_funding_signal_gone(/' --mutation '/^def _b2_funding_signal(/,/^def /s/    config = B2Config()/    config = B2Config(z_window=30)/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_reentry_reads_its_signal_off_its_own_columns[b2-funding-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 9: Commit** — `feat(research): B2 trials 6–7's subjects — the liquidation-cascade and funding-extreme re-entries and their pre-flight twins on a frozen set's full history`, the message carrying the test result lines, each probe's command and verdict, each `probe skipped: slow case` and the two trailer lines.

## Task 3: the data-gated basis test, the conventions entry and the reads (D5, D7)

**Files:** Create `tests/test_research_b2_reentries_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 2's `_b2_reentry_inputs`, `_b2_reentry_engagement`, `_b2_funding_signal` and `_b2_liq_signal`; `tests.skip_gates.nothing_found_under`. Produces two tests and the module names `BLOCK`, `VOUCHED`, `START`, `THRESHOLD`, `ENGAGED_PER_ASSET`, `ENGAGED_PER_YEAR`, `TURNOVER_B`, `SIGNAL_KEY`, `reentry_inputs()` and `coverage()`, which Task 4's check programs import. No test computes a bar or a return of either arm.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis:

```python
"""B2 trials 6-7's inputs half against spec 00139's measured basis: no bar, and no return of either arm."""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.features.derivatives import coverage_by_year
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; each case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
_RETURN_INDICES = 27_337
BLOCK = {
    "b2-liq-reentry": "816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f",
    "b2-funding-reentry": "3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8",
}
VOUCHED = {
    "b2-liq-reentry": {"liquidations-daily": "checked (10 vouched hashes)"},
    "b2-funding-reentry": {"derivatives-funding": "checked (10 vouched hashes)"},
}
# The read's start: its return index and close, and the returns from it.
START = {
    "b2-liq-reentry": (19_731, datetime(2022, 10, 11, tzinfo=UTC), 7_606),
    "b2-funding-reentry": (15_843, datetime(2021, 1, 1, tzinfo=UTC), 11_494),
}
# The first return index every asset's signal holds.
_SIGNAL_FROM = {"b2-liq-reentry": 19_731, "b2-funding-reentry": 15_419}
THRESHOLD = {"b2-liq-reentry": 2.5, "b2-funding-reentry": -2.0}
ENGAGED_PER_ASSET = {
    "b2-liq-reentry": {
        "ADA": 114,
        "AVAX": 82,
        "BTC": 139,
        "DOGE": 90,
        "DOT": 163,
        "ETH": 126,
        "LINK": 118,
        "LTC": 120,
        "SOL": 137,
        "XRP": 107,
    },
    "b2-funding-reentry": {
        "ADA": 963,
        "AVAX": 740,
        "BTC": 684,
        "DOGE": 706,
        "DOT": 812,
        "ETH": 710,
        "LINK": 946,
        "LTC": 780,
        "SOL": 723,
        "XRP": 982,
    },
}
ENGAGED_PER_YEAR = {
    "b2-liq-reentry": dict.fromkeys(map(str, range(2013, 2022)), 0)
    | {"2022": 155, "2023": 259, "2024": 301, "2025": 307, "2026": 174},
    "b2-funding-reentry": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 218, "2021": 535, "2022": 2_407, "2023": 1_463, "2024": 1_177, "2025": 1_691, "2026": 555},
}
# Arm B's turnover: a re-entry's size moves it, never the counts above.
TURNOVER_B = {"b2-liq-reentry": 172.92, "b2-funding-reentry": 264.50}
SIGNAL_KEY = {"b2-liq-reentry": "binperp_liq_long_z30d", "b2-funding-reentry": "binperp_funding_z30d"}
_TRIGGERS = {
    "b2-liq-reentry": (subjects._b2_liq_signal, operator.gt, 1),
    "b2-funding-reentry": (subjects._b2_funding_signal, operator.lt, 6),
}


def reentry_inputs(name: str):
    """A re-entry's inputs half over the real sets, with the reader that read them."""
    read_signal, fire, hold = _TRIGGERS[name]
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_reentry_inputs(name, read_signal, fire, hold, THRESHOLD[name], reader, "ohlc-full", None, False)


def coverage(inputs) -> dict[str, dict[str, list[int]]]:
    return {
        asset: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(inputs.close, values).items()}
        for asset, values in inputs.signal.items()
    }


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set or the frozen daily liquidations block is absent under data/",
)
def test_the_liquidation_reentry_reproduces_the_measured_basis():
    _check("b2-liq-reentry")


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet"),
    reason="the frozen ohlc-full set or the derivatives-funding set is absent under data/",
)
def test_the_funding_reentry_reproduces_the_measured_basis():
    _check("b2-funding-reentry")


def _check(name: str) -> None:
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reentry_inputs(name)
    assert compute_hash(reader.block()) == BLOCK[name]
    assert {d: s for d, s in reader.vouched_status().items() if d != "ohlc-full"} == VOUCHED[name]
    index, first, returns = START[name]
    assert (len(inputs.close), inputs.close[index], _RETURN_INDICES - index) == (_RETURN_INDICES, first, returns)
    signal = inputs.signal
    assert next(k for k in range(_RETURN_INDICES) if all(signal[a][k] is not None for a in subjects._ASSETS)) == _SIGNAL_FROM[name]
    arm_a, full_long = inputs.arm_a, inputs.full_long
    assert sum(arm_a[a][k] > full_long[a][k] + 1e-12 for a in subjects._ASSETS for k in range(_RETURN_INDICES)) == 0
    assert (
        sum(
            abs(arm_a[a][k] - full_long[a][k]) <= 1e-12 and arm_a[a][k] > 0
            for a in subjects._ASSETS
            for k in range(_RETURN_INDICES)
        )
        == 30_632
    )
    assert subjects._b2_reentry_engagement(inputs, SIGNAL_KEY[name]) == {
        "engaged_per_asset": ENGAGED_PER_ASSET[name],
        "engaged_per_year": ENGAGED_PER_YEAR[name],
        f"{SIGNAL_KEY[name]}_coverage": coverage(inputs),
        "primary_returns": returns,
        "threshold": THRESHOLD[name],
    }
    assert round(subjects.book_turnover(inputs.arm_b), 2) == TURNOVER_B[name]
```

- [ ] **Step 2: Run it** — with `data/ohlc-full`, `data/derivatives-funding` and `data/liquidations-daily` linked in this worktree: `uv run pytest tests/test_research_b2_reentries_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt`, one plain blocking call, `timeout` 600000 ms: `2 passed`, never a skip (measured on the authoring tree, about 95 s a case). Both cases join `tests/slow-cases.txt` at their `sorted()` places:

```text
tests/test_research_b2_reentries_basis.py::test_the_funding_reentry_reproduces_the_measured_basis
tests/test_research_b2_reentries_basis.py::test_the_liquidation_reentry_reproduces_the_measured_basis
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_reentries_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths; the two tree walkers its skip gates and data mark meet, `uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt`; `uv run pre-commit run -a` until clean. No probe: both cases are slow, each recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B2 trials 6–7's inputs half against the measured basis — the blocks, the full-long bound, the starts, the engagement and arm B's turnover`.
- [ ] **Step 5: The conventions entry** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`:

```markdown
[iter-183] B2 trials 6–7's conventions, pinned by spec 00139 before its hash (Decision: 1)
  The two re-entry trials' details are fixed in the spec, reviewed, and frozen by its sha256, every record's `spec_hash`, before any return of arm B or any kill bar is computed over the data; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00128, 00133, 00137 and 00138 fixed staying theirs.
  1. **As the spec pins them** — the two re-entries in one spec, the liquidation one first (D1); a re-entry takes an asset arm A holds flat at its full-long size — the arms' shared inverse-vol weight times the mean of their vol-target levels, the position arm A holds where every arm is long — and never resizes a position arm A holds (D3); it lasts a day from its trigger: hold 1 on the daily liquidation signal, whose day is read over the next day's six closes, hold 6 on the 8-hourly funding z-score (D3); trial 6 fires on trial 5's signal above trial 5's threshold, 2.5, the long side, trial 7 on trial 2's funding z-score below −2.0, spec 00128's threshold mirrored (D4); the read from the later of the signal's own start and 2021-01-01, the owner's From-2021 primary with spec 00138 D8's later-signal rule (D5); a return-led matrix, arm B's drawdown bounded at 1.2 × arm A's for an adopt, the park variants the threshold one step toward 0 and the size halved (D5); the counts 5 and 6 fixed by the hash (D5); the overlays' 42 and 22 keys, the engagement counting re-entered flat stamps, arm A by `_b2_overlay_inputs`' expression with its books kept (D6); no `--verdict`, and notes naming only what is fixed before each run, spec 00133 D7's and spec 00137 D10's (D7); an adopt deployed on spec 00138 D11's B1 precedent (D8). Chosen.
  2. **The alternatives each weighed** — the de-risks' park variants or a further de-risk leg; the funding re-entry unheld (0.408 % a close to break even) or held 12 closes; a hold, hysteresis or minimum on the liquidation re-entry; a size of half the full-long size or of arm A's last long position; spec 00138 D3's engagement rule re-applied to flat stamps, or 2.0 on the liquidation signal; the total or the short side; the de-risks' drawdown leg (arm B's below arm A's), or no drawdown leg; a count raised in place; metric keys of the re-entry's own.
  Source: spec 00139 (D1, D3–D8), its **Author's call**s and the calls it carries from the owner and specs 00133, 00137 and 00138; the owner's run instruction of 2026-10-21 quoted in its ruling.
```

  staged alone, its gate `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt` and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-183] B2 trials 6–7's conventions, pinned by spec 00139 before its hash`.
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 and the conventions entry — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing runs a bar or arm B's return over the real data before the spec's hash, and the data-gated cases run with the frozen full set, the funding set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data tests and the check programs (D7)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00139-b2-reentries-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; arm A's code path since record 54's run, `git log --oneline 16dbc5cf0..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/derivatives cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1's and 2's commits and their fixes alone; any other commit is named, step 4's data tests deciding whether it moved arm A.
- [ ] **Step 2: D7 (1), the spec hash** — `sha256sum docs/specs/00139-b2-reentries-design.md`; its value, pasted from that call, is every run's `--spec-hash` and every record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D7 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0; if not, develop is merged first (`git merge --no-edit origin/develop`, alone, then step 1's checks again). It runs again before each trial's pre-flight (Tasks 5–6 step 1).
- [ ] **Step 4: D7 (3), the data tests on the run's tree** — `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_reentries_basis.py -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt > .tmp/plan-00139/basis.out 2>&1`, one background call: every case passed, never a skip; a failure is an instrument finding before the first pre-flight, T0023's.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00139/preflight_check.py`, D7's (a)–(e) in order, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00139 D7's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b2_reentries_basis import (
    BLOCK,
    ENGAGED_PER_ASSET,
    ENGAGED_PER_YEAR,
    SIGNAL_KEY,
    START,
    THRESHOLD,
    VOUCHED,
    coverage,
    reentry_inputs,
)

name = sys.argv[1]
out = Path(f".tmp/plan-00139/{name}-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if compute_hash(block) != BLOCK[name]:
    sys.exit("(a) the inputs' block differs from the spec's")
if {d: s for d, s in run["vouched"].items() if d != "ohlc-full"} != VOUCHED[name]:
    sys.exit("(a) the signal's set is not vouched as the spec reads it")
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
key = SIGNAL_KEY[name]
basis = {
    "engaged_per_asset": ENGAGED_PER_ASSET[name],
    "engaged_per_year": ENGAGED_PER_YEAR[name],
    f"{key}_coverage": coverage(reentry_inputs(name)[1]),
    "primary_returns": START[name][2],
    "threshold": THRESHOLD[name],
}
off = [k for k, value in basis.items() if m[k] != value]
if off:
    sys.exit(f"(c) the engagement, the start or the threshold differs from the measured basis, or the coverage from the inputs half's: {off}")
print("engaged", sum(m["engaged_per_asset"].values()), m["engaged_per_year"], "primary_returns", m["primary_returns"], "threshold", m["threshold"])
if not any(m["engaged_per_asset"].values()):
    sys.exit("(d) the re-entry engages no stamp: the dead knob")
print({k: m[k] for k in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00139/record_check.py`, the record's checks:

```python
"""Spec 00139 D6's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_reentries_basis import ENGAGED_PER_YEAR, SIGNAL_KEY, START, THRESHOLD, TURNOVER_B, coverage, reentry_inputs

name, spec_hash = sys.argv[1], sys.argv[2]
labels = {"b2-liq-reentry": (5, "B2-liq-reentry-a2eq-full-v1"), "b2-funding-reentry": (6, "B2-funding-reentry-a2eq-full-v1")}[name]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00139/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00139/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
key = SIGNAL_KEY[name]
invocation = {k: r["invocation"][k] for k in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
expected = (ENGAGED_PER_YEAR[name], coverage(reentry_inputs(name)[1]), START[name][2], THRESHOLD[name], TURNOVER_B[name])
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"]) == ("B2", *labels, "iter-183", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": (m["engaged_per_year"], m[f"{key}_coverage"], m["primary_returns"], m["threshold"], round(m["turnover_b"], 2))
    == expected,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00139/preflight_check.py .tmp/plan-00139/record_check.py`.

## Task 5 (the controller's): trial 6 — the liquidation-cascade re-entry, its pre-flight, its run and its record (D3, D4, D7)

`<H>` is Task 4 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 4 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `uv run zcrypto research eval --subject b2-liq-reentry-preflight --dataset ohlc-full > .tmp/plan-00139/b2-liq-reentry-preflight.out 2>&1`, a plain eval of a subject with no rule, one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00139/preflight_check.py b2-liq-reentry`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(e): D7's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0023's with its line; a refused build — exit 1 with no traceback, its output naming the subject over the full history or a file of `liquidations-daily` — prints no metrics, keeps no reading, and is recorded in Task 7's T0023 findings with its line quoted, the trial unspent; Task 6 runs regardless.
- [ ] **Step 3: On a stop, the reading** — `uv run zcrypto research eval --subject b2-liq-reentry-preflight --dataset ohlc-full --reading --iteration iter-183 --spec-hash <H> --notes "B2 trial 6's pre-flight (spec 00139 D7): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00139/b2-liq-reentry-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `uv run zcrypto research eval --subject b2-liq-reentry --dataset ohlc-full --register --iteration iter-183 --family B2 --n-trials 5 --variant B2-liq-reentry-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00139/b2-liq-reentry.out 2>&1`, one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run, name only what is fixed before it: `subject b2-liq-reentry over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble taking an asset it holds flat at its full-long size (its inverse-vol weight times the mean of the arms' vol-target levels) while the asset's 30-day z-score of daily long-side liquidated notional (Coinalyze's daily history, frozen as liquidations-daily, a day read from the first close at or after its end) exceeds 2.5, held one close from the last firing close, that close included, every position change charged 0.006 per side; the hypothesis: the re-entry improves the ensemble's net-of-cost performance against the unconditioned ensemble; n_trials 5, var_trials 0.0, the DSR leg binding; the head-to-head from the later of the first close every asset's signal holds and 2021-01-01 (index 19731, 2022-10-11 00:00) decides, the full-window read beside it, arm B's drawdown bounded at 1.2 times arm A's for an adopt; pre-flight: block 816f62f9…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: threshold 2.0, the size halved; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, or bucket B spent — comes before the fit or after the print, naming each orphan or the bucket's figure: no record, no reading; T0023 carries it (Task 7) and Task 6 runs. A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b2-liq-reentry"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build ends its attempt failed, counting 0, recorded in T0023 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0023's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00139/record_check.py b2-liq-reentry <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 7 step 2). A failed check stops the task before step 6.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-183] Verdict — B2 trial 6 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B2 n=5)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D5's table, with `passes`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary` and `max_drawdown_reduction_pct` unrounded, `max_drawdown` beside `arm_a_max_drawdown`, the full-window pair beside them; `n_trials` 5, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); the pre-flight's block, anchors and `passes`; the engagement proof — `engaged_per_year`, `primary_returns`, `threshold`, `stamps_positions_differ`, `turnover_a` beside `turnover_b`; on a park its variants; on an adopt D8's path in its order; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-182] Verdict — B2 trial 5 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b2-liq-reentry": 5,` after `"b2-liq-derisk": 4,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B2 trial 6's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries it adopts` (D8), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`, staged with it. Then `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a` until clean. In the probe worktree, `data/ohlc-full` and `data/liquidations-daily` linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00139/probe/data/<set>` and unlinked before its removal: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task; then the literal's probe, expected `KILLED`: `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reentry_verdict(/def _b2_reentry_verdict_gone(/' --mutation 's/^_B2_LIQ_REENTRY_N_TRIALS = 5 /_B2_LIQ_REENTRY_N_TRIALS = 6 /' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit, `git add` by path of the registry, the provenance test, the decisions log, the slow-cases file and on an adopt T0123 and the index, as `docs(research): B2 trial 6 registered — <verdict>, the liquidation-cascade re-entry on the A2 ensemble, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/ohlc-full and data/liquidations-daily: re-run it with the two sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b2-liq-reentry-preflight` with outcome `null`, or `b2-liq-reentry` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones — the entry is `[iter-183] B2 trial 6 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` when its replay's call runs 10 s or more; the replay `-k 'reading-<its id>'`; committed as `docs(research): B2 trial 6 — instrument finding, kept as reading <id>; no trial spent` with no probe. On a refusal from the count or a refused build: no commit here; Task 7 records it.

## Task 6 (the controller's): trial 7 — the funding-extreme re-entry (D3, D4, D7)

Task 5's steps with these values, each command written out: the subject `b2-funding-reentry`, its twin `b2-funding-reentry-preflight`, the outputs `.tmp/plan-00139/b2-funding-reentry-preflight.out`, `.tmp/plan-00139/b2-funding-reentry-reading.out` and `.tmp/plan-00139/b2-funding-reentry.out`; the count `--n-trials 6`; the variant `B2-funding-reentry-a2eq-full-v1`; "B2 trial 7" in every note, entry and message; the sets `data/ohlc-full` and `data/derivatives-funding`; the notes `subject b2-funding-reentry over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble taking an asset it holds flat at its full-long size (its inverse-vol weight times the mean of the arms' vol-target levels) from a close at which the asset's 30-day funding z-score (Binance's 8-hourly prints, the derivatives-funding set) reads below -2.0, held six closes from the last firing close, that close included, every position change charged 0.006 per side; the hypothesis: the re-entry improves the ensemble's net-of-cost performance against the unconditioned ensemble; n_trials 6, var_trials 0.0, the DSR leg binding; the head-to-head from the later of the first close every asset's signal holds and 2021-01-01 (index 15843, 2021-01-01 00:00) decides, the full-window read beside it, arm B's drawdown bounded at 1.2 times arm A's for an adopt; pre-flight: block 3da5e397…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: threshold -1.5, the size halved; the matrix pre-registered by the spec's sha256 <H>`; the entry `[iter-183] Verdict — B2 trial 7 <ADOPT, PARK or REJECT> (registry trial <N>, family B2 n=6)`; `"b2-funding-reentry": 6,` after `"b2-liq-reentry": 5,` (or after `"b2-liq-derisk": 4,` where trial 6 landed no record); on an adopt T0123's qualification naming B2 trial 7, once only — a second adopt adds its record to the same qualification; the replay with `data/ohlc-full` and `data/derivatives-funding` linked; the literal's probe `--mutation 's/^_B2_FUNDING_REENTRY_N_TRIALS = 6$/_B2_FUNDING_REENTRY_N_TRIALS = 7/'`, every other argument Task 5's; committed as `docs(research): B2 trial 7 registered — <verdict>, the funding-extreme re-entry on the A2 ensemble, registry trial <N>`, or on a stop as Task 5's stop arm with "B2 trial 7" and `b2-funding-reentry`.

## Task 7: T0023, T0016, the index and the retirement of the four subjects (D8)

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py`.

- [ ] **Step 1: T0023**, per `topic-ops`, every figure read off the committed records, readings and entries: `## Findings so far` gains one bullet per trial — `**B2 trial 6 <VERDICT> (iter-183, spec 00139, registry trial <N>).**` with the row that fired and the engagement in one or two sentences, pointing at its decisions-log entry for the figures, or the instrument finding or the refused line, the trial unspent; trial 7 alike; an outcome with no line in the registry or the ledger — a fault, a refused build or a refusal from the count (Tasks 5–6 steps 2 and 4) — quoted whole from its run's output, `.tmp/plan-00139/<subject>-preflight.out` or `.tmp/plan-00139/<subject>.out`; `## Done so far` gains **B2 trials 6–7 (iter-183, spec/plan 00139)**, naming `full_long_sizes`, `reentry_positions` and `reentry_counts_per_year` in `cli/alpha/b2.py`, the four subjects and the data-gated basis test, and the records by id; `## Suggested next steps` replaces `(owner) B2's next step after trials 3–5` with `(owner) B2's next step after trials 6–7` — the verdicts in one clause; a park's variants, a de-risk variant (scale 0.25, threshold 3.0), the de-risks' and the re-entries' further legs, a trial on the tape, a follow-up the reading's figures invite (the daily history reconciled with the tape, the reading at a later as-of or over a longer span, a per-side reading), or closing the family — recorded as a `[iter-NNN] B2's next step after trial 7` entry; on an adopt, D8's path; `ripe_when` — on no adopt: `an activity: the owner picks B2's next step after trials 6–7 — a park variant, a further leg, or closing the family — recorded in the decisions log; check: grep -c -E '^\[iter-[0-9]+\] B2.s next step after trial 7' docs/research/10.phase4-decisions.md prints at least 1`; on an adopt: `an activity: the P1 combination trial over record 47's book carrying B2 trial <k>'s arm B is picked for an iteration; check: cat docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md | grep -c -E '^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book' prints at least 1`, `<k>` the adopting trial's number. The check is run as committed and prints 0.
- [ ] **Step 2: T0016** — its budget line's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` (run when this plan was written, it printed `{'B1': 5, 'B2': 4} remain 16 []`): the line reads `B1 spent <its B1>, B2 spent <its B2>, <its remain> remain`, each orphan it lists named on that line; its B2 line names trials 6–7 (iter-183, spec/plan `00139`) with their records and verdicts.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the four subjects, so `RETIRED_SUBJECTS` gains, after `"b2-liq-tape-reading",`, `"b2-liq-reentry"`, `"b2-liq-reentry-preflight"`, `"b2-funding-reentry"` and `"b2-funding-reentry-preflight"`, and every test function of `tests/test_research_command.py` specific to them and named by no parameter carries `@pytest.mark.retired` — those Task 2 adds whose parameters take no subject name as a value: `test_the_b2_reentry_rule_maps_the_matrix_to_a_verdict_or_a_stop`, `test_where_no_signal_fires_a_b2_reentrys_arm_b_is_arm_a_bit_for_bit`, `test_a_b2_reentry_refuses_fewer_than_2_returns_from_its_start` and `test_a_b2_reentry_trial_refuses_a_start_it_cannot_evaluate_before_any_bar`; `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q` collects no case naming a re-entry subject.
- [ ] **Step 5: Gate and commit** — `git add` the five paths; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path, in Task 2 step 7's three parts: `tests/test_research_command.py -k "not reentry"` (`pt-1`), `tests/test_research_command.py -k reentry` (`pt-2`) and the rest (`pt-3`); `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0023 and T0016 after B2 trials 6–7; the four subjects retired`.

## Task 8: the loop's pick in the decisions log, the read and the PR

- [ ] **Step 1: The decisions-log entry** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`:

```markdown
[iter-183] B2's next step after trial 5 — the two contrarian re-entries as one spec with two trials in sequence, the loop's pick under the owner's run instruction, 2026-10-21 (Decision: 3)
  The owner launched an unattended run, verbatim: "continue pushing the Research strates forward, pick the most relevant tasks. override the wall clock time gate, but do not pick up new topics after 8:00Z. when closing out a research step, try the trials with potential and do not close any family too early." T0023's trigger after trials 3–5 (records 52–54, each REJECT) named the owner's pick; master plan §12 lists no touchpoint for a family's next trial, so the run picked, a close excluded by the instruction. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)" and the head-to-head read "From-2021 primary (Recommended)", read from a later signal's own start.
  1. **The de-risks' park variants or a further de-risk leg** — the scale 0.25, the threshold 3.0, the OI log-delta or momentum, a single ratio, another liquidation side or window. Cheap, the machinery in place; but every de-risk lost return at each engagement, their drawdowns 0.41 % lower, 28.9 % higher and 0.76 % lower than arm A's (records 52–54), so a variant moves the same mechanism.
  2. **Bucket B's next family, B4-legs then B3** — T0016's §5 order. A new family with its own prior; but it leaves B2's re-entry half, which §5 names, untested, and opens a new design while B2 stands open.
  3. **The two contrarian re-entries, one spec, two trials in sequence** — spec 00139: a full-long position where arm A is flat, for a day after a long-side liquidation spike day (z above 2.5) or a funding z-score below −2.0, on trial 2's instrument and bar, counts 5 and 6, a return-led matrix with a 1.2× drawdown bound. The opposite action to the three rejects on their own signals, the dislocation §5 names; up to two B slots, 16 to 14. Chosen: the only untried B2 mechanism with a distinct hypothesis, each trial clearing a break-even within a fraction of a percent a close once held a day (spec 00139's measured basis).
```

  Its gate `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00139/pt` and `uv run pre-commit run -a`; committed as `docs(research): [iter-183] B2's next step after trial 5 — the loop's pick under the owner's run instruction, the two contrarian re-entries`.
- [ ] **Step 2 (the controller's): The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-183 — B2 trials 6–7: liquidation, funding re-entry` (71 characters by `printf '%s' <it> | wc -m`, at the cap or under), its own commit.
- [ ] **Step 3 (the controller's): The read** — the `pre-review` of Tasks 5–8's commits, then `review` over `<the tip the last read covered>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated cases and replays the messages record run with the frozen full set, the funding set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 4 (the controller's): The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the two verdicts or stops, each pre-flight's output quoted whole in a fenced block, every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the delta's read covered. Merged through `merge-pr` under the run's licence; before it, `git status --short --ignored` read, `.tmp/plan-00139` collected and removed, and `unlink data/ohlc-full`, `unlink data/derivatives-funding` and `unlink data/liquidations-daily` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the three sets still there.

Decisions log: the conventions entry (Task 3 step 5), before the hash; the verdict or instrument-finding entries (Tasks 5–6 step 6), each in its record's commit; and this task's `[iter-183] B2's next step after trial 5`.
