# B2 trial 2 — the two subjects on frozen ohlc-full, the gated run and the verdict — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next. Execution is subagent-driven — the author's call, made unattended, nobody asked. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/research/subjects.py tests/test_research_command.py tests/test_research_b2_full_basis.py README.md tests/slow-cases.txt` prints `tier: full` for `tests/test_research_command.py`, "a test importing cli.alpha"; the run's paths, `docs/reference/trial-registry.jsonl` and `tests/test_trial_registry_provenance.py`, print `full` too).

**Goal:** the ruled subject `b2-funding-derisk-full` and its evaluate-only pre-flight twin `b2-funding-derisk-full-preflight` in `cli/research/subjects.py`, the data-gated test of the inputs half and arm A over the frozen `ohlc-full` and `derivatives-funding` sets, and B2's trial 2 registered once through spec 00133's trial-attempts log, its verdict in the registry, the decisions log, T0023 and T0016 — and on an adopt T0123's qualified trigger.

**Architecture:** no new module and no change to an existing function. The two subjects reuse `_b2_inputs` (the union, the funding z-score, arm A's positions and the scales), `_b2_build` (the compute-error naming), `_b2_returns`, `_b2_verdict` and `_B2_METRIC_KEYS` unchanged; what is new is a frozen-set as-of refusal in front of `_b2_build`, arm A's bar and the trial's metrics on `calendar_year_slices` (2013 and 2026 dropped, 2020 kept), the engagement read the twin prints and the data test pins, and the twin's anchors. Spec 00133 is on the branch's first-parent line (D10's gate), so the subjects, the run's record and its verdict land in this branch's one pull request.

**Tech Stack:** Python 3.14 through uv; polars for the parquet reads; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00137-b2-trial-2-ohlc-full-design.md` — binding; D1–D11 are cited by name and the values below are copied from it verbatim; it copies spec 00128's D2, D3, D5, D6, D7 and D9, which `docs/specs/00128-b2-family-opening-design.md` holds and reading 1's `spec_hash` freezes. Spec 00133's trial-attempts log is merged on develop (pull request #730, `64d416754`); this plan names its interfaces as the code at `457f12a59` gives them, in each task's Interfaces block. **Iteration:** iter-181. **Topic:** T0023 under T0016. **Branch:** `research/iter-181-b2-trial-2-ohlc-full`, worktree `.claude/worktrees/iter181`, `data/ohlc-full` and `data/derivatives-funding` linked read-only from the main checkout. A choice this plan makes that the spec leaves open is marked **Author's call**.

## Global Constraints

- The inputs (D2, D3, D6): `_b2_inputs(reader, dataset, window, None, accept_holes, subject=subject)`, called unchanged — the 4h union through `_capturing_union`, the ten funding files read whole through `reader.read_series("derivatives-funding", f"{PERP_SYMBOLS[asset]}/funding.parquet")`, `funding_grid_feature` at `B2Config()` (threshold 2.0, scale 0.5, window 90), arm A the per-asset `statistics.mean` of the three `_B2_A2_ARMS` arms' `asset_positions` on `_ffill_btc(h4_prices)`, `scales = derisk_scales(feature, config=B2Config())`; arm B `scale_positions(arm_a, scales)`; every net through `net_of_cost` at `_B2_COST_PER_SIDE` (0.006) and the ×1.5 series at `1.5 * _B2_COST_PER_SIDE`, over `_b2_returns(h4_prices)`; the benchmark `benchmark_4h_net_of_cost(h4_prices, cost_per_side=_B2_COST_PER_SIDE)` on the raw union prices.
- The slices (D5): `calendar_year_slices(series, h4_ts)` for arm B, arm A and the benchmark, `STUB_YEARS = (2013, 2026)` dropped, 2020 kept; `_b2_slices`, which drops 2020, is never called by either new subject.
- The bars (D8): arm B's six cells `a1_kill_bar(net_b, bench, n_trials=_B2_FULL_N_TRIALS, var_trials=0.0, mean_block=block, seed=seed, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=_DECISIVE_START, n_resamples=_N_RESAMPLES)` for `block` in (30, 102) and `seed` in (42, 7, 1234), the headline the cell (30, 42); arm A's bar the same call at (30, 42) with `net_a`, arm A's ×1.5 series and arm A's slices; `_B2_FULL_N_TRIALS = 1`, `_DECISIVE_START` 1380, `_N_RESAMPLES` 2000; the head-to-heads `net_of_cost_verdict(net_b[start:], net_a[start:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)` for `("full", 0)` and `("2021", k21)`, `k21` the first return index whose close is at or after `_FROM_2021`; the drawdown pair `max_drawdown(net_b[k21:])`, `max_drawdown(net_a[k21:])`, `max_drawdown_reduction_pct = 100 * (drawdown_a - drawdown_b) / drawdown_a`, a build whose arm A never draws down from 2021 refused before any bar (`ValidationError` `"arm A never draws down from 2021-01-01T00:00Z, so max_drawdown_reduction_pct divides by zero"`).
- The matrix (D8): `_b2_verdict`, reused unchanged as the trial's `verdict` — the from-2021 read decides, the headline cell alone carries the bar, block 102 is recorded and never read; adopt on `passes`, `head_to_head_mean_outperf_2021 > 0`, `max_drawdown_reduction_pct > 1e-6` and `head_to_head_spa_p_2021 < 0.05`, park on the first three with the p at or above 0.05, reject otherwise or on a failed bar, `None` (a stop) when `arm_a_passes` is 0 or no year holds an engaged stamp.
- The record (D9): family `B2`, `n_trials_in_family` 1, variant `B2-funding-derisk-a2eq-full-v1`, iteration `iter-181`, seeds (42, 7, 1234), the metric keys exactly `_B2_METRIC_KEYS`' 40, `dataset_hash` `3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8`, no `--verdict` (D10).
- The subjects (D9): `b2-funding-derisk-full` — intervals `(240,)`, `_ASSETS`, `spec="docs/specs/00137-b2-trial-2-ohlc-full-design.md"`, `metric_keys=_B2_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_b2_verdict`, `no_verdict` `"instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"`, `family="B2"`, `n_trials=_B2_FULL_N_TRIALS`; `b2-funding-derisk-full-preflight` — the same intervals, assets and spec, `metric_keys=_B2_FULL_PREFLIGHT_KEYS` (20), seeds (42,), no rule, family or count. Both refuse `--as-of` before any read with `SubjectError` `f"{subject} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset"`.
- The pre-flight (D7), read in this order: (a) the block `3da5e397…`; (b) the seven anchors at record 45's stored precision — `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown_full` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703, the benchmark's 1.2128 and 1.2447 at four decimals, `turnover_a` 146.19 at two; (c) `engaged_per_asset`, `engaged_per_year` and `binperp_funding_z30d_coverage` exactly the measured basis; (d) arm A's `passes` 1.
- The hash rule (D7, D10): before Task 3 step 2 takes the spec's sha256, nobody computes arm A's bar or any position or return of arm B over the trial's data; the data-gated tests compute arm A's positions, its net and its seven anchors, the feature and the engagement — what the spec's measured basis already measured — and no bar, and no reader, reviewer or plan-review dispatch runs either subject over the real sets; every read's dispatch carries this rule. No return of arm B is computed over the trial's data before Task 3 step 6's register run. There is no plain eval of `b2-funding-derisk-full`, before or after it (D10).
- Unchanged (D9): every existing function of `cli/research/subjects.py`, `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/engine/*`, the subjects `b2-funding-derisk` and `b2-arm-a-bar`, and any adopted artifact; `git diff -U0 457f12a59 -- cli/research/subjects.py | grep -c '^-[^-]'` prints 0 after every task. Code citations name a function, never a line.
- Never edit `docs/specs/00137-b2-trial-2-ohlc-full-design.md` after Task 3 step 2, nor `docs/specs/00128-b2-family-opening-design.md`; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading` over a committed file, except where Task 3 names it. Never `git stash`; no amend; a state-changing git command runs alone, the probe setup below excepted.
- Data: `data/ohlc-full` and `data/derivatives-funding` alone, read-only links to the canonical sets, never written under; never `data/ohlc-holdout-*`, never `/mnt/zhao-crypto/`; never ssh, a fleet host, `kraken-cli`, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`.
- Tests: every pytest run is `mkdir -p .tmp/plan-00137 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00137/pt` (or a file, or `-k`), split into parts each under 600 s, nothing backgrounded. Every command that can pass 120 s — a pytest part, an eval of Task 3 (steps 5 and 6) and the replay case (Task 4 step 7) among them — is one foreground call with the Bash tool's timeout at 600000 ms, never its 120000 ms default: a kill mid-run loses the run, and under `--register` leaves its attempt open (Task 3 step 6). Before each commit, as `.claude/skills/zcrypto-plan-review/references/implementer-contract.md` has it: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00137/pt`, never a bare `uv run pytest` — `-m "not data"` because the data-gated readers of `cli/research/subjects.py` read sets not linked here (`ohlc-rolling`, `ohlc-15m`) or replay recorded bars, and the hash rule keeps every bar off the real sets until Task 3; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`, since `tests/conftest.py`'s ledger deselects a slow case already passed on the branch. A commit message's test result line is a run over that commit's own tree.
- Probes: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged:

```bash
test ! -e .tmp/plan-00137/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00137/probe HEAD &&
  git -C .tmp/plan-00137/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00137/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00137/probe/.tmp
```

  The block runs as one call — `$TREE` lives only in that call's shell — and prints the tree's hash; its lines are chained, so a refused `worktree add` never lets `read-tree` and `commit` run against the branch's own worktree, and a probe tree an earlier attempt left stops it at `test ! -e` until `git worktree remove --force .tmp/plan-00137/probe` removes it. Then, from `.tmp/plan-00137/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` so the case fails at import or at its call. After the last verdict, `git worktree remove --force .tmp/plan-00137/probe` — a data link in it unlinked first. The task's commit carries in its message `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- Commits: one per task that changes the tree, and two for Task 2 (the test, then step 6's conventions entry) and for Task 4 (the records commit, then step 8's change-index row); Task 3 adds none, its record landing in Task 4's records commit; each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: <the executing session's URL>`; an implementer on another model names its own.
- The reads: the trio over the branch through Task 2 (`pre-review`, `review`, `re-review`, as CLAUDE.md orders them; Task 2 step 6) closes with no open Critical or Important before Task 3 step 2, and nothing the run executes or the record pins changes from that read to the registration unless a read of the change follows (Task 3 step 1); Task 4's commits take their own `pre-review`, then the read of the delta from the tip the last read covered (Task 4 step 8) before the push that carries it; every `re-review` draws on the branch's two, and a Critical or Important open with none left goes to the owner; the PR is created and edited through `open-pr`, its read line naming the tip read.

## Review Focus

- `--as-of` handed to either subject on the rolling set must be refused by the subject before any read, never evaluated on another instrument: the command requires `--as-of` for `ohlc-rolling` and refuses it for a frozen set, so the subject's own refusal is the one door. Test: Task 1, `test_a_b2_full_subject_refuses_as_of_before_any_read`.
- The trial run as a plain eval — the one look D10 forbids — or at a count other than 1 must be refused before any read. Test: Task 1, `test_b2_full_refuses_a_plain_eval_and_another_count_before_any_read`.
- A funding file the build cannot read under the new subject must end in a refusal naming `derivatives-funding/<PERP>/funding.parquet`, never a traceback: the subject reuses `_b2_inputs`, whose own tests run it under `b2-funding-derisk` alone. Test: Task 1, `test_the_b2_full_subject_refuses_a_funding_file_it_cannot_read_naming_it`.
- A window closing fewer than two return indices from 2021 must be refused in the full subject's own name before any bar, so a windowed run of the trial never prints a head-to-head over one return. Test: Task 1, `test_the_b2_full_subject_refuses_a_window_it_cannot_evaluate_before_any_bar[one-index-into-2021]`.
- An asset whose perp never spikes must appear in `engaged_per_asset` at 0, never be dropped, since D7 (c) compares the twin's dict with the basis key for key. Test: Task 1, `test_the_b2_full_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b`, its `engaged_per_asset[_B2_NEVER_SPIKES] == 0`.

## File structure

- Modify `cli/research/subjects.py` — the constant `_B2_FULL_N_TRIALS`, five functions, two `_build_` wrappers, the key set `_B2_FULL_PREFLIGHT_KEYS` and the two `SUBJECTS` entries, after `_B1_EXIT_PREFLIGHT_KEYS` and before `SUBJECTS`.
- Modify `tests/test_research_command.py` — the subjects' tests, `_RULED_FIXTURES`, `_DECLARED_COUNT`, the families literal, `_CONTRACT_DATASETS`, the metric-keys test; `README.md` — the `--subject` row; `tests/slow-cases.txt` — the new slow cases.
- Create `tests/test_research_b2_full_basis.py` — data-gated: the inputs half against the measured basis, and arm A against records 45 and 50.
- At the run: `docs/reference/trial-registry.jsonl` (or, on a stop, `docs/reference/reading-ledger.jsonl`), `tests/test_trial_registry_provenance.py` (`LANDED_N_TRIALS`), `docs/research/10.phase4-decisions.md`, `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md`.

______________________________________________________________________

### Task 1: the subjects `b2-funding-derisk-full` and `b2-funding-derisk-full-preflight` (D5–D9)

**Files:**
- Modify: `cli/research/subjects.py` — the Produces names after `_B1_EXIT_PREFLIGHT_KEYS` and before `SUBJECTS`; two entries at the end of `SUBJECTS`
- Modify: `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`

**Interfaces:**
- Consumes: `cli/research/subjects.py` as `457f12a59` holds it — `_B2Inputs` (`h4_ts`, `h4_prices`, `close`, `arm_a`, `binperp_funding_z30d`, `scales`), `_b2_inputs(reader, dataset, window, as_of, accept_holes, *, subject) -> _B2Inputs`, `_b2_build(subject, compute, reader, dataset, window, as_of, accept_holes) -> dict`, `_b2_returns(h4_prices)`, `_b2_metrics(inputs) -> dict`, `_b2_verdict(m) -> str | None`, `_B2_METRIC_KEYS`, `_B2_ARM_A_BAR_KEYS`, `_B2_ARM_A_BAR_FLAGS`, `_B2_COST_PER_SIDE`, `_DECISIVE_START`, `_N_RESAMPLES`, `_FROM_2021`, `_ASSETS`, `PPY_4H`, `SubjectError`, and the names it imports (`a1_kill_bar`, `net_of_cost_verdict`, `net_of_cost`, `scale_positions`, `benchmark_4h_net_of_cost`, `calendar_year_slices`, `per_year_engaged_counts`, `per_year_positions_differ`, `per_year_turnover`, `per_year_max_drawdown`, `book_turnover`, `coverage_by_year`, `max_drawdown`, `sharpe`), each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; spec 00133 as `457f12a59` holds it: `Subject.family: str | None = None` and `Subject.n_trials: int | None = None`; `cli/research/command.py`'s `eval_subject`, which refuses a plain eval of a subject with a rule before any read, `--register` of a subject without one and an `--n-trials` other than `Subject.n_trials`, counts `attempts.Count.required_n(family)` and the bucket against `budget.BUCKET_OF` and `budget.BUDGET` (`"B2": "B"`, `"B": 25`) before the fit, writes the trial-attempts log's `begin` line before the fit and its `end` line before the print, and keeps a rule's `None` as a reading carrying its attempt; in the tests, `tests/conftest.py`'s autouse `_attempts_log_in_tmp_path(tmp_path)`, the module's autouse `_attempts_log`, `_anchor`, `_as_trial`, `_rolling_set`, `_recording`, `_b2_dataset`, `_b2_eval`, `_B2_START`, `_B2_BARS`, `_B2_GRID`, `_B2_FLAGS`, `_B2_ASSETS`, `_B2_SPOILT`, `_B2_NEVER_SPIKES`, `_B2_FROM_MAY_2020`, `_B2_METRIC_KEYS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`, `test_the_ruled_subjects_declare_their_families_and_trial_counts`, `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count`, `test_each_subject_declares_the_metric_keys_its_build_returns`.
- Produces:

```python
# cli/research/subjects.py
_B2_FULL_N_TRIALS = 1

def _b2_full_arm_a_bar(inputs: _B2Inputs) -> tuple[dict, list[float], list[float]]: ...  # bar, net_a, bench
def _b2_full_engagement(inputs: _B2Inputs) -> dict: ...  # engaged_per_asset, engaged_per_year, binperp_funding_z30d_coverage
def _b2_full_metrics(inputs: _B2Inputs) -> dict: ...  # _B2_METRIC_KEYS' 40
def _b2_full_preflight_metrics(inputs: _B2Inputs) -> dict: ...  # _B2_FULL_PREFLIGHT_KEYS' 20
def _b2_full_build(subject: str, compute: Callable[[_B2Inputs], dict], reader, dataset, window, as_of, accept_holes) -> dict: ...
def _build_b2_funding_derisk_full(reader, dataset, window, as_of=None, accept_holes=False) -> dict: ...
def _build_b2_funding_derisk_full_preflight(reader, dataset, window, as_of=None, accept_holes=False) -> dict: ...
_B2_FULL_PREFLIGHT_KEYS: frozenset[str]
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - the `from cli.alpha.b2 import (` block gains `B2Config,` and `derisk_scales,` before `net_of_cost,` (ruff's order); every other name the block reads is imported or defined already.
  - `_RULED_FIXTURES` gains `"b2-funding-derisk-full": _b2_dataset,` after its `"b2-funding-derisk"` entry; `_DECLARED_COUNT` gains `"b2-funding-derisk-full": "_B2_FULL_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b2-funding-derisk-full": ("B2", 1),`; `_CONTRACT_DATASETS` gains, after `"b2-arm-a-bar"`, `"b2-funding-derisk-full"` and `"b2-funding-derisk-full-preflight"`, each `lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START)`; `test_each_subject_declares_the_metric_keys_its_build_returns` ends with `assert subjects.SUBJECTS["b2-funding-derisk-full"].metric_keys == _B2_METRIC_KEYS` and `assert subjects.SUBJECTS["b2-funding-derisk-full-preflight"].metric_keys == _B2_FULL_PREFLIGHT_KEYS`.
  - After `test_the_b2_subject_refuses_a_window_its_benchmark_never_trades_naming_it` and before the comment `# Records 45 and 46's metric keys (docs/specs/00130 D3), pinned against the committed records below.`:

```python
_B2_FULL_SPEC = "docs/specs/00137-b2-trial-2-ohlc-full-design.md"
_B2_FULL_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"
)
_B2_FULL_ANCHORS = frozenset(
    {
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown_full",
        "turnover_a",
        "arm_a_spot_drag_pct_yr",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    }
)
_B2_FULL_ENGAGEMENT = frozenset({"engaged_per_asset", "engaged_per_year", "binperp_funding_z30d_coverage"})
# Spec 00137 D9's twenty keys of the pre-flight, typed from the spec, never read off the subject.
_B2_FULL_PREFLIGHT_KEYS = _B2_FULL_ANCHORS | _ARM_A_BAR_KEYS | _B2_FULL_ENGAGEMENT


def test_the_b2_full_subjects_declare_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count():
    trial, preflight = subjects.SUBJECTS["b2-funding-derisk-full"], subjects.SUBJECTS["b2-funding-derisk-full-preflight"]
    assert (len(_B2_METRIC_KEYS), len(_B2_FULL_PREFLIGHT_KEYS)) == (40, 20)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        "b2-funding-derisk-full",
        (240,),
        _B2_ASSETS,
        _B2_FULL_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b2_funding_derisk_full and trial.metric_keys == _B2_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_verdict, _B2_FULL_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", 1) == ("B2", subjects._B2_FULL_N_TRIALS)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        "b2-funding-derisk-full-preflight",
        (240,),
        _B2_ASSETS,
        _B2_FULL_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b2_funding_derisk_full_preflight
    assert preflight.metric_keys == _B2_FULL_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


# Adopting on every key the rule reads, the full-window head-to-head and the block-102 cell set against the verdict, so a
# rule reading either in place of the from-2021 read or the headline cell moves the first row.
_B2_FULL_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2013": 0, "2021": 4},
    "passes": 1,
    "head_to_head_mean_outperf_2021": 0.001,
    "head_to_head_spa_p_2021": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "spa_p_decisive_b102_s42": 0.9,
    "max_drawdown_reduction_pct": 5.0,
}
_B2_FULL_NEVER_ENGAGED = {"engaged_per_year": {"2013": 0, "2021": 0}}


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-outperforms-significantly-from-2021-and-draws-down-less"),
        pytest.param({"head_to_head_spa_p_2021": 0.0499}, "adopt", id="row-1-p-at-0.0499"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6}, "adopt", id="row-1-reduction-past-1e-6"),
        pytest.param({"head_to_head_spa_p_2021": 0.2}, "park", id="row-2-outperforms-insignificantly-from-2021"),
        pytest.param({"head_to_head_spa_p_2021": 0.05}, "park", id="row-2-p-at-exactly-0.05"),
        pytest.param({"head_to_head_mean_outperf_2021": -0.001}, "reject", id="row-3-underperforms-from-2021"),
        pytest.param({"head_to_head_mean_outperf_2021": 0.0}, "reject", id="row-3-mean-at-exactly-0"),
        pytest.param({"max_drawdown_reduction_pct": -5.0}, "reject", id="row-3-draws-down-more"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="row-3-reduction-at-exactly-1e-6"),
        pytest.param(
            {"head_to_head_mean_outperf_2021": -0.001, "head_to_head_mean_outperf_full": 0.001, "head_to_head_spa_p_full": 0.01},
            "reject",
            id="row-3-outperforms-over-the-full-window-alone",
        ),
        pytest.param({"passes": 0}, "reject", id="row-4-arm-b-fails-its-bar"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_FULL_NEVER_ENGAGED, None, id="the-overlay-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_FULL_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
    ],
)
def test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop(change, verdict):
    assert subjects.SUBJECTS["b2-funding-derisk-full"].verdict({**_B2_FULL_ADOPTING, **change}) == verdict


def _fingerprint(*parts) -> bytes:
    return hashlib.sha256(repr(parts).encode()).digest()


def _fake_kill_bar(
    book_net_returns,
    benchmark_net_returns,
    *,
    n_trials,
    var_trials,
    mean_block,
    seed,
    cost_stressed_returns,
    regime_slices,
    benchmark_slices,
    decisive_start=0,
    n_resamples=1000,
):
    """`a1_kill_bar`'s signature, each value a function of every argument: two builds making the same calls get the same
    results, and a key read off another call or another key differs; the flags are ints other than 0 and 1."""
    d = _fingerprint(
        book_net_returns,
        benchmark_net_returns,
        n_trials,
        var_trials,
        mean_block,
        seed,
        cost_stressed_returns,
        regime_slices,
        benchmark_slices,
        decisive_start,
        n_resamples,
    )
    floats = ("dsr", "spa_p_value", "spa_p_value_full", "cost_stress_sharpe", "worst_slice_sharpe")
    return (
        {key: d[i] / 256 + i for i, key in enumerate(floats)}
        | {key: 2 + d[10 + i] for i, key in enumerate(_B2_FLAGS)}
        | {"passes": 2 + d[20]}
    )


def _fake_benchmark(h4_prices, *, cost_per_side):
    d = _fingerprint(h4_prices, cost_per_side)
    return [(d[k % 32] - 128) / 1e5 for k in range(len(h4_prices["BTC"]) - 1)]


def _fake_head_to_head(book_net_of_cost, benchmark_net_of_cost, *, mean_block, seed, n_resamples=2000):
    d = _fingerprint(book_net_of_cost, benchmark_net_of_cost, mean_block, seed, n_resamples)
    return {
        "spa_p_value": d[0] / 256,
        "beats": False,
        "book_sharpe": 0.0,
        "benchmark_sharpe": 0.0,
        "mean_outperformance": d[1] - 128,
    }


def test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept(tmp_path, monkeypatch):
    inputs = subjects._b2_inputs(
        ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", None, None, False, subject="b2-funding-derisk-full"
    )
    n = len(inputs.close)
    k21 = next(k for k, t in enumerate(inputs.close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert (n, k21) == (_B2_BARS - 1, 551)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    full = subjects._b2_full_metrics(inputs)

    assert set(full) == _B2_METRIC_KEYS
    assert sorted((arguments["mean_block"], arguments["seed"]) for arguments, _ in bars) == sorted([*_B2_GRID, (30, 42)])
    for arguments, _ in bars:
        assert (arguments["n_trials"], arguments["var_trials"], arguments["decisive_start"], arguments["n_resamples"]) == (
            1,
            0.0,
            1380,
            2000,
        )
        assert list(arguments["regime_slices"]) == list(arguments["benchmark_slices"]) == ["2020", "2021"]
    assert [len(arguments["book_net_of_cost"]) for arguments, _ in head_to_heads] == [n, n - k21]
    # Spec 00128's metrics, `_b2_slices` read as the stub years alone and at the full subject's count: the full subject must
    # not call `_b2_slices` itself.
    monkeypatch.setattr(subjects, "_b2_slices", calendar_year_slices)
    monkeypatch.setattr(subjects, "_B2_N_TRIALS", subjects._B2_FULL_N_TRIALS)
    assert subjects._b2_metrics(inputs) == full


def test_where_no_z_score_is_defined_the_b2_full_subjects_arm_b_is_arm_a_bit_for_bit(tmp_path, monkeypatch):
    inputs = subjects._b2_inputs(
        ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", None, None, False, subject="b2-funding-derisk-full"
    )
    dark = {a: [None] * len(inputs.close) for a in _B2_ASSETS}
    inputs = inputs._replace(binperp_funding_z30d=dark, scales=derisk_scales(dark, config=B2Config()))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    full = subjects._b2_full_metrics(inputs)

    assert [arguments["book_net_of_cost"] == arguments["benchmark_net_of_cost"] for arguments, _ in head_to_heads] == [True] * 2
    assert (full["stamps_positions_differ"], full["turnover_b"], full["max_drawdown"], full["max_drawdown_reduction_pct"]) == (
        0,
        full["turnover_a"],
        full["arm_a_max_drawdown"],
        0.0,
    )
    assert set(full["engaged_per_year"].values()) == {0}


def test_the_b2_full_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b(tmp_path, monkeypatch):
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    def arm_b(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions")

    monkeypatch.setattr(subjects, "scale_positions", arm_b)
    reads = _recording(monkeypatch, "_b2_inputs", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS["b2-funding-derisk-full-preflight"].build(ObservedReader(_b2_dataset(tmp_path)), "ohlc-test", None)

    ((_, inputs),) = reads
    returns = {a: _asset_returns(_ffill_btc(inputs.h4_prices)[a]) for a in _B2_ASSETS}
    net_a, net_a_x15 = (net_of_cost(inputs.arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.close)
    ((arguments, bar),) = bars
    assert arguments == {
        "book_net_returns": net_a,
        "benchmark_net_returns": bench,
        "n_trials": 1,
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
        "binperp_funding_z30d_coverage": {
            a: {
                str(year): [c.non_null, c.total]
                for year, c in coverage_by_year(inputs.close, inputs.binperp_funding_z30d[a]).items()
            }
            for a in _B2_ASSETS
        },
    }
    assert set(metrics) == _B2_FULL_PREFLIGHT_KEYS
    assert sum(engaged.values()) == sum(metrics["engaged_per_year"].values()) > 0
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0


@pytest.mark.parametrize("name", ["b2-funding-derisk-full", "b2-funding-derisk-full-preflight"])
def test_a_b2_full_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
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


@pytest.mark.parametrize(
    ("flags", "refused"),
    [
        pytest.param(
            [],
            "b2-funding-derisk-full declares a verdict rule, so every run of it is a trial: run it with --register",
            id="plain-eval",
        ),
        pytest.param(
            ["--register", "--iteration", "iter-181", "--family", "B2", "--n-trials", "2"],
            "--n-trials 2 is not 1, the count b2-funding-derisk-full declares and deflates at: pass --n-trials 1",
            id="another-count",
        ),
    ],
)
def test_b2_full_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, flags, refused):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_inputs", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-funding-derisk-full", "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.parametrize(
    ("bars", "cause"),
    [
        pytest.param(
            1_471,
            "1 of its return indices close at or after 2021-01-01T00:00Z, and the from-2021 head-to-head needs 2",
            id="one-index-into-2021",
        ),
        pytest.param(
            1_472,
            "arm A never draws down from 2021-01-01T00:00Z, so max_drawdown_reduction_pct divides by zero",
            id="arm-a-never-draws-down-from-2021",
        ),
    ],
)
def test_the_b2_full_subject_refuses_a_window_it_cannot_evaluate_before_any_bar(tmp_path, monkeypatch, bars, cause):
    _anchor(monkeypatch, _b2_dataset(tmp_path, start=_B2_FROM_MAY_2020))
    args = _b2_eval(_B2_FROM_MAY_2020, bars)
    args[args.index("b2-funding-derisk")] = "b2-funding-derisk-full"
    kill_bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    result = runner.invoke(app, [*args, *_as_trial("b2-funding-derisk-full", tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"b2-funding-derisk-full over the window {args[-2]} .. {args[-1]}: {cause}" in result.output
    assert kill_bars == []


def test_the_b2_full_subject_refuses_a_funding_file_it_cannot_read_naming_it(tmp_path, monkeypatch):
    root = _b2_dataset(tmp_path)
    (root / "derivatives-funding" / _B2_SPOILT / "funding.parquet").write_bytes(b"not a parquet file")
    _anchor(monkeypatch, root)
    args = ["research", "eval", "--subject", "b2-funding-derisk-full", "--dataset", "ohlc-test"]

    result = runner.invoke(app, [*args, *_as_trial("b2-funding-derisk-full", tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"derivatives-funding/{_B2_SPOILT}/funding.parquet" in result.output
    assert "File out of specification" in result.output
```

  **Author's call** — the wiring test runs `_b2_full_metrics` and `_b2_metrics` under the same argument-derived stand-ins for `a1_kill_bar`, `benchmark_4h_net_of_cost` and `net_of_cost_verdict`, with `_b2_slices` read as `calendar_year_slices` only for the second, so equal dicts prove D9's "the 40 keys as `_b2_metrics` computes them, with `calendar_year_slices` in place of `_b2_slices`" key for key — `_b2_metrics`' own register test proving its keys against a hand computation — while the recorded calls prove the counts, the windows and 2020 kept; the identity test is D6's "Identity, held by a test", run through the subject with every z-score `None`; the stand-ins keep the wiring, identity and pre-flight tests under 10 s (6.6–6.8 s each, measured on a transcription), so they are probed rather than slow-listed, the real bars running in the contract and shared-defaults rows.

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00137 && uv run pytest tests/test_research_command.py -k "b2_full or b2-funding-derisk-full or ruled_subjects or declares_the_metric_keys" -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00137/pt`
Expected: `29 failed, 413 deselected` — the 26 new cases fail on a `KeyError` naming either subject, an `AttributeError` naming `_b2_full_metrics`, or, the `[plain-eval]` and `[another-count]` rows, on their assertion, the command refusing an unknown subject; the families and metric-keys tests on theirs, and the kill-bar row `[b2-funding-derisk-full]` on its `AttributeError` naming `_B2_FULL_N_TRIALS`; the contract and tracked-spec rows of the two subjects are not collected until `SUBJECTS` holds them.

- [ ] **Step 3: Implement in `cli/research/subjects.py`** — the Produces names, after `_B1_EXIT_PREFLIGHT_KEYS` and before `SUBJECTS`, under a comment naming spec 00137 D9 (the trial on a frozen set's full history, spec 00128's arms, bars, matrix and keys, its slices `calendar_year_slices`' stub years alone):
  - `_B2_FULL_N_TRIALS = 1`, its one-line reason a comment: spec 00133 D4's count, no B2 record and no orphan when the trial was pre-registered.
  - `_b2_full_arm_a_bar`: `_b2_arm_a_bar`'s body with `calendar_year_slices` for both slices and `n_trials=_B2_FULL_N_TRIALS`, returning `(bar, net_a, bench)`. **Author's call**: the net and the benchmark travel with the bar, so the twin's anchors read the series the bar read, as B1's `_b1_hourly_rv_arm_a` returns them.
  - `_b2_full_engagement`: `{"engaged_per_asset": {a: sum(p > 0 and s < 1 for p, s in zip(arm_a[a], scales[a])) for a in _ASSETS}, "engaged_per_year": per_year_engaged_counts(arm_a, scales, close), "binperp_funding_z30d_coverage": …}`, the coverage built as `_b2_metrics` builds it — from arm A's positions, the scales and the feature alone. **Author's call**: one source for the three keys both subjects print, which the data test pins against the basis.
  - `_b2_full_metrics`: `_b2_metrics`' body with exactly four substitutions — `slices_b, slices_bench = calendar_year_slices(net_b, inputs.h4_ts), calendar_year_slices(bench, inputs.h4_ts)` on one line in place of the `_b2_slices` pair; `n_trials=_B2_FULL_N_TRIALS,` in the grid's call; `"arm_a_passes": int(_b2_full_arm_a_bar(inputs)[0]["passes"]),`; and `engaged_per_year` and `binperp_funding_z30d_coverage` read off one `engagement = _b2_full_engagement(inputs)`; the drawdown refusal stays before the grid, so no bar runs on a refused build.
  - `_b2_full_preflight_metrics`: `bar, net_a, bench = _b2_full_arm_a_bar(inputs)`; `turnover_a = book_turnover(inputs.arm_a)`; the seven anchors — `sharpe(net_a, periods_per_year=PPY_4H)`, the same over `net_a[_DECISIVE_START:]`, `"arm_a_max_drawdown_full": max_drawdown(net_a)`, `turnover_a`, `turnover_a / len(inputs.close) * _B2_COST_PER_SIDE * PPY_4H`, and the benchmark's two Sharpes; the bar's ten keys as `_b2_arm_a_bar_metrics` writes them, flags as int; `**_b2_full_engagement(inputs)` — no call of `scale_positions`.
  - `_b2_full_build`: `if as_of is not None:` on its own line, the Global Constraints' `SubjectError`; then `return _b2_build(subject, compute, reader, dataset, window, None, accept_holes)`. The two `_build_` wrappers call it with `"b2-funding-derisk-full"` and `_b2_full_metrics`, `"b2-funding-derisk-full-preflight"` and `_b2_full_preflight_metrics`. **Author's call**: the refusal sits in front of `_b2_build`, which D9 keeps unchanged and which calls `_b2_inputs` itself.
  - `_B2_FULL_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {…the seven anchors…, "engaged_per_asset", "engaged_per_year", "binperp_funding_z30d_coverage"}` under a comment naming spec 00137 D9; the two `SUBJECTS` entries exactly as the Global Constraints declare them, after `"b1-hourly-channel-exits-preflight"`.

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row's list, which now ends `` …, `b1-hourly-channel-exits` (…) or `b1-hourly-channel-exits-preflight` (…; it has no rule, so its run is kept with `--reading`). ``, ends `` …, `b1-hourly-channel-exits-preflight` (…; it has no rule, so its run is kept with `--reading`), `b2-funding-derisk-full` (the A2 4h ensemble against the same ensemble halved per asset while that asset's 30-day funding z-score exceeds 2; the 4h series of `--dataset`, a frozen set only, and the `derivatives-funding` set's ten funding files read whole) or `b2-funding-derisk-full-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`). ``, no internal term.

- [ ] **Step 5: Run them to verify they pass** — first, timed, `uv run pytest tests/test_research_command.py -k "b2_full or b2-funding-derisk-full" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00137/pt`: each row at 10 s or more joins `tests/slow-cases.txt` at its sorted place — measured on a transcription at 33.1, 20.2, 17.1, 14.7 and 10.9 s, the five `test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-funding-derisk-full]` and `[b2-funding-derisk-full-preflight]`, `test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-funding-derisk-full-evaluates]` and `[b2-funding-derisk-full-preflight-evaluates]`, and `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-funding-derisk-full]`; the run's own timing decides, the list kept sorted as `sorted()` orders it. Then Step 2's command, expected `42 passed, 418 deselected` with those five listed, each row the run lists beyond them or leaves off moving one case between the two counts; `tests/test_slow_cases.py` passes. The window test's `[arm-a-never-draws-down-from-2021]` row measured 8.8–9.1 s: at 10 s or more on this run it joins the list too, its probe row then recorded `probe skipped: slow case`.

- [ ] **Step 6: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the direct readers in two parts — `tests/test_research_command.py` alone (measured `410 passed, 50 deselected` in 3 min 34 s) and the other readers of the four paths (measured `4122 passed, 39 deselected` in 2 min), each `-m "not slow and not data"`; `uv run pre-commit run -a` until clean, its rewrites staged.

- [ ] **Step 7: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`; the contract, tracked-spec and shared-defaults rows of the two subjects are new rows of existing tests, not new guards, and are not probed:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/"b2-funding-derisk-full-preflight": Subject(/,/^    ),/s/metric_keys=_B2_FULL_PREFLIGHT_KEYS,/metric_keys=_B2_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_subjects_declare_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/"b2-funding-derisk-full-preflight": Subject(/,/^    ),/s/metric_keys=_B2_FULL_PREFLIGHT_KEYS,/metric_keys=_B2_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_each_subject_declares_the_metric_keys_its_build_returns' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/"b2-funding-derisk-full": Subject(/,/^    ),/s/family="B2",/family="B1",/' -- uv run pytest 'tests/test_research_command.py::test_the_ruled_subjects_declare_their_families_and_trial_counts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/"b2-funding-derisk-full": Subject(/,/^    ),/s/verdict=_b2_verdict,/verdict=_b1_hourly_exit_verdict,/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-from-2021-and-draws-down-less]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/m\["head_to_head_mean_outperf_2021"\] > 0/m["head_to_head_mean_outperf_full"] > 0/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-3-outperforms-over-the-full-window-alone]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/if m\["head_to_head_spa_p_2021"\] < 0.05 else/if m["head_to_head_spa_p_full"] < 0.05 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-from-2021-and-draws-down-less]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/< 0.05 else "park"/< 0.05 and m["spa_p_decisive_b102_s42"] < 0.05 else "park"/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-from-2021-and-draws-down-less]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/m\["head_to_head_spa_p_2021"\] < 0.05/m["head_to_head_spa_p_2021"] <= 0.05/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-2-p-at-exactly-0.05]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/m\["head_to_head_mean_outperf_2021"\] > 0/m["head_to_head_mean_outperf_2021"] >= 0/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-3-mean-at-exactly-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/m\["max_drawdown_reduction_pct"\] > 1e-6/m["max_drawdown_reduction_pct"] >= 1e-6/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-3-reduction-at-exactly-1e-6]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/m\["max_drawdown_reduction_pct"\] > 1e-6/m["max_drawdown_reduction_pct"] > 1e-5/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-1-reduction-past-1e-6]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/ and m\["max_drawdown_reduction_pct"\] > 1e-6/ and True/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-3-draws-down-more]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/if not m\["passes"\]:/if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[row-4-arm-b-fails-its-bar]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/if not m\["arm_a_passes"\] or/if False or/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[arm-a-fails-its-bar]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_verdict(/,/^[^ #]/s/ or not any(m\["engaged_per_year"\].values()):/ or False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_rule_maps_spec_00128s_matrix_to_a_verdict_or_a_stop[the-overlay-never-engages]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/slices_b, slices_bench = calendar_year_slices(net_b, inputs.h4_ts), calendar_year_slices(bench, inputs.h4_ts)/slices_b, slices_bench = _b2_slices(net_b, inputs.h4_ts), _b2_slices(bench, inputs.h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/n_trials=_B2_FULL_N_TRIALS,/n_trials=2,/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/("2021", k21)/("2021", 0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/"arm_a_passes": int(_b2_full_arm_a_bar(inputs)\[0\]\["passes"\]),/"arm_a_passes": int(headline["passes"]),/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/drawdown_b = max_drawdown(net_b\[k21:\])/drawdown_b = max_drawdown(net_b)/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/"turnover_b": book_turnover(arm_b),/"turnover_b": book_turnover(arm_a),/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_arm_a_bar(/,/^def /s/regime_slices=calendar_year_slices(net_a, inputs.h4_ts),/regime_slices=_b2_slices(net_a, inputs.h4_ts),/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_metrics_are_b2_metrics_on_calendar_year_slices_at_one_trial_2020_kept' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_metrics(/def _b2_full_metrics_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/arm_b = scale_positions(arm_a, scales)/arm_b = scale_positions(arm_a, {a: [0.5] * len(close) for a in scales})/' -- uv run pytest 'tests/test_research_command.py::test_where_no_z_score_is_defined_the_b2_full_subjects_arm_b_is_arm_a_bit_for_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_preflight_metrics(/def _b2_full_preflight_metrics_gone(/' --mutation '/^def _b2_full_preflight_metrics(/,/^def /s/"arm_a_max_drawdown_full": max_drawdown(net_a),/"arm_a_max_drawdown_full": max_drawdown(bench),/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_preflight_metrics(/def _b2_full_preflight_metrics_gone(/' --mutation '/^def _b2_full_preflight_metrics(/,/^def /s/turnover_a \/ len(inputs.close)/turnover_a \/ len(inputs.h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_preflight_metrics(/def _b2_full_preflight_metrics_gone(/' --mutation '/^def _b2_full_preflight_metrics(/,/^def /s/turnover_a = book_turnover(inputs.arm_a)/turnover_a = book_turnover(scale_positions(inputs.arm_a, inputs.scales))/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_preflight_metrics(/def _b2_full_preflight_metrics_gone(/' --mutation '/^def _b2_full_engagement(/,/^def /s/p > 0 and s < 1/p > 0 and s <= 1/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_build(/def _b2_full_build_gone(/' --mutation '/^def _b2_full_build(/,/^def /s/if as_of is not None:/if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_full_subject_refuses_as_of_before_any_read[b2-funding-derisk-full]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_build(/def _b2_full_build_gone(/' --mutation '/^def _b2_full_build(/,/^def /s/if as_of is not None:/if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_full_subject_refuses_as_of_before_any_read[b2-funding-derisk-full-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/"b2-funding-derisk-full": Subject(/,/^    ),/s/verdict=_b2_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_b2_full_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/"b2-funding-derisk-full": Subject(/,/^    ),/s/n_trials=_B2_FULL_N_TRIALS,/n_trials=2,/' -- uv run pytest 'tests/test_research_command.py::test_b2_full_refuses_a_plain_eval_and_another_count_before_any_read[another-count]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_refuse_window(/,/^def /s/if from_2021 < 2:/if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_subject_refuses_a_window_it_cannot_evaluate_before_any_bar[one-index-into-2021]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_full_metrics(/,/^def /s/if drawdown_a == 0:/if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_subject_refuses_a_window_it_cannot_evaluate_before_any_bar[arm-a-never-draws-down-from-2021]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_funding_derisk_full(/def _build_b2_funding_derisk_full_gone(/' --mutation '/^def _b2_inputs(/,/^def /s/raise SubjectError(f"derivatives-funding\/{relpath}: {exc}") from exc/raise SubjectError(f"funding\/{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_full_subject_refuses_a_funding_file_it_cannot_read_naming_it' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(research): the b2-funding-derisk-full subject and its pre-flight twin — spec 00128's arms, bars and matrix on a frozen set's full history, 2020 a slice

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>
<probe skipped: slow case — each listed row, by node id>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 2: the data-gated test over `ohlc-full` and `derivatives-funding` — the measured basis and arm A's anchors (D4, D7)

**Files:**
- Create: `tests/test_research_b2_full_basis.py` (module-marked `data`)
- Modify: `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 6's own commit

**Interfaces:**
- Consumes: Task 1's `_b2_full_engagement(inputs) -> dict`; `_b2_inputs`, `_b2_returns`, `_ASSETS`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`.
- Produces: `test_the_b2_full_inputs_reproduce_the_measured_basis` and `test_the_b2_full_arm_a_reproduces_records_45_and_50s_arm_a`, sharing one module-scoped read; the module names `ENGAGED_PER_ASSET`, `ENGAGED_PER_YEAR`, `ARM_A` and `coverage()`, which Task 3's checks import. Neither test computes a bar or a position or return of arm B.

- [ ] **Step 1: Write the failing test** — every literal copied from the spec's measured basis, never from a run:

```python
"""B2 trial 2's inputs half on the frozen ohlc-full set and the funding set against spec 00137's measured basis, and arm A
against records 45 and 50's stored figures: no bar, and no position or return of arm B."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import net_of_cost
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost, calendar_year_slices
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
# Copied from the spec's measured basis, never from a run.
_BLOCK_HASH = "3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8"
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
# Per asset: the closes holding a z-score, the first of them, and those in 2020.
_Z = {
    "ADA": (13_400, (2020, 2, 18, 8), 1_906),
    "AVAX": (11_918, (2020, 10, 22, 8), 424),
    "BTC": (13_512, (2020, 1, 30, 16), 2_018),
    "DOGE": (12_364, (2020, 8, 9, 0), 870),
    "DOT": (12_118, (2020, 9, 19, 0), 624),
    "ETH": (13_512, (2020, 1, 30, 16), 2_018),
    "LINK": (13_414, (2020, 2, 16, 0), 1_920),
    "LTC": (13_462, (2020, 2, 8, 0), 1_968),
    "SOL": (11_741, (2020, 10, 13, 8), 478),
    "XRP": (13_480, (2020, 2, 5, 0), 1_986),
}
_SOL_2022 = 1_959
ENGAGED_PER_ASSET = {
    "ADA": 372,
    "AVAX": 164,
    "BTC": 402,
    "DOGE": 326,
    "DOT": 347,
    "ETH": 454,
    "LINK": 336,
    "LTC": 458,
    "SOL": 210,
    "XRP": 417,
}
ENGAGED_PER_YEAR = dict.fromkeys(map(str, range(2013, 2020)), 0) | {
    "2020": 780,
    "2021": 1_189,
    "2022": 8,
    "2023": 572,
    "2024": 908,
    "2025": 27,
    "2026": 2,
}
# Records 48-50's arm A and benchmark, stored unrounded.
ARM_A = {
    "arm_a_ann_sharpe_noc": 1.404998307684581,
    "arm_a_ann_sharpe_noc_decisive": 1.3716011675660076,
    "arm_a_max_drawdown": 0.2154323695072342,
    "turnover_a": 146.18534602048504,
    "arm_a_spot_drag_pct_yr": 0.07026650498259404,
    "benchmark_ann_sharpe_noc": 1.2128451567638199,
    "benchmark_ann_sharpe_noc_decisive": 1.2446890489958136,
}


def coverage() -> dict[str, dict[str, list[int]]]:
    """`binperp_funding_z30d_coverage` as the basis measured it: no z-score before 2020, every close from 2021 bar SOL's
    2022 stretch."""
    out = {}
    for asset, (_, _, in_2020) in _Z.items():
        held = dict.fromkeys(map(str, range(2013, 2020)), 0) | {"2020": in_2020}
        if asset == "SOL":
            held["2022"] = _SOL_2022
        out[asset] = {year: [held.get(year, total), total] for year, total in _CLOSES_PER_YEAR.items()}
    return out


@pytest.fixture(scope="module")
def _reads():
    reader = ObservedReader(_DATA_ROOT)
    inputs = subjects._b2_inputs(reader, "ohlc-full", None, None, False, subject="b2-funding-derisk-full")
    return inputs, reader.block()


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet"),
    reason="the frozen ohlc-full set or the derivatives-funding set is absent under data/",
)
def test_the_b2_full_inputs_reproduce_the_measured_basis(_reads):
    assert _DATA_ROOT == research_command._DATA_ROOT
    inputs, block = _reads
    assert compute_hash(block) == _BLOCK_HASH
    assert {dataset: (len(entry["files"]), entry["rows"], entry["span"]) for dataset, entry in block.items()} == {
        "derivatives-funding": (10, 68_281, ["2020-01-01 00:00:00+00:00", "2026-06-30 16:00:00+00:00"]),
        "ohlc-full": (10, 173_373, ["2013-09-10 20:00:00+00:00", "2026-03-31 20:00:00+00:00"]),
    }
    h4_ts, close, z = inputs.h4_ts, inputs.close, inputs.binperp_funding_z30d
    assert (len(h4_ts), h4_ts[0], h4_ts[-1]) == (
        27_338,
        datetime(2013, 9, 10, 20, tzinfo=UTC),
        datetime(2026, 3, 31, 20, tzinfo=UTC),
    )
    assert sum(later - earlier != timedelta(hours=4) for earlier, later in zip(h4_ts, h4_ts[1:])) == 63
    assert (len(close), close[0], close[-1]) == (
        _RETURN_INDICES,
        datetime(2013, 9, 11, tzinfo=UTC),
        datetime(2026, 3, 31, 20, tzinfo=UTC),
    )
    assert h4_ts[1380] == datetime(2014, 5, 26, tzinfo=UTC)
    k21 = next(k for k, t in enumerate(close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert (k21, _RETURN_INDICES - k21) == (15_843, 11_494)
    assert dict(Counter(str(t.year) for t in close)) == _CLOSES_PER_YEAR
    assert list(calendar_year_slices([0.0] * _RETURN_INDICES, h4_ts)) == [str(year) for year in range(2014, 2026)]

    for asset, (defined, first, _) in _Z.items():
        held = [k for k in range(_RETURN_INDICES) if z[asset][k] is not None]
        assert (len(held), close[held[0]], close[held[-1]]) == (defined, datetime(*first, tzinfo=UTC), close[-1]), asset
    assert subjects._b2_full_engagement(inputs) == {
        "engaged_per_asset": ENGAGED_PER_ASSET,
        "engaged_per_year": ENGAGED_PER_YEAR,
        "binperp_funding_z30d_coverage": coverage(),
    }
    assert (sum(p > 0 for positions in inputs.arm_a.values() for p in positions), sum(map(len, inputs.arm_a.values()))) == (
        93_462,
        273_370,
    )
    assert {s for scales in inputs.scales.values() for s in scales} == {0.5, 1.0}

    # Where the overlay can act: no z-score before index 13,825, all ten from 15,419, from k21 all ten bar SOL's stretch.
    any_z = [any(z[a][k] is not None for a in z) for k in range(_RETURN_INDICES)]
    all_z = [all(z[a][k] is not None for a in z) for k in range(_RETURN_INDICES)]
    assert (any_z.index(True), any_z.count(False), any_z[1380:].count(False)) == (13_825, 13_825, 12_445)
    assert (all_z.index(True), all_z[k21:].count(True)) == (15_419, 11_263)
    sol = [close[k] for k in range(k21, _RETURN_INDICES) if z["SOL"][k] is None]
    assert (len(sol), sol[0], sol[-1]) == (231, datetime(2022, 11, 9, 20, tzinfo=UTC), datetime(2022, 12, 18, 4, tzinfo=UTC))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet"),
    reason="the frozen ohlc-full set or the derivatives-funding set is absent under data/",
)
def test_the_b2_full_arm_a_reproduces_records_45_and_50s_arm_a(_reads):
    inputs, _ = _reads
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
    assert {key: round(value, 2 if key == "turnover_a" else 4) for key, value in ARM_A.items()} == {
        key: _trials()[45]["metrics"][key] for key in ARM_A
    }
```

  **Author's call**: the two tests share one module-scoped `_b2_inputs` read, since each read costs about 76 s; the basis test reads the engagement through Task 1's `_b2_full_engagement`, so the counts D7 (c) compares are the twin's own and the test is red before Task 1; the arm-A test reads only code `457f12a59` already holds — the spec's measured basis ran the same expressions — so it passes on either side of Task 1, and what it guards is the instrument, not new code. It checks arm A bit for bit against record 50's unrounded anchors and at record 45's stored precision, computing no bar (D7's (d) is the pre-flight's, Task 3 step 5).

- [ ] **Step 2: Run them** — `mkdir -p .tmp/plan-00137 && uv run pytest tests/test_research_b2_full_basis.py --durations=4 -q -p no:cacheprovider --basetemp=.tmp/plan-00137/pt`, the two sets linked in this worktree: `2 passed` (measured on a transcription in 2 min 1 s: the shared read's setup 75.9 s, the arm-A test's call 45.2 s); with Task 1's `cli/research/subjects.py` held back at `457f12a59`, the basis test fails on `AttributeError: module 'cli.research.subjects' has no attribute '_b2_full_engagement'` and the arm-A test passes. A skip is no pass. Both node ids join `tests/slow-cases.txt` at their sorted places, after `tests/test_research_b2_basis.py`'s, and `tests/test_slow_cases.py` passes.

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_full_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two staged paths, run as they run it; the new file, which that run's `-m "not slow and not data"` deselects, by node id with `ZCRYPTO_RERUN_SLOW=1`; the two tree walkers its skip gates and data mark meet, `uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00137/pt` (measured `317 passed`); `uv run pre-commit run -a` until clean.

- [ ] **Step 4: Probes** — none: both cases are slow (76 s and 45 s), so the commit records `probe skipped: slow case` for each node id.

- [ ] **Step 5: Commit**

```bash
git commit -F - <<'EOF'
test(research): B2 trial 2's inputs half against the measured basis, and arm A against records 45 and 50

<the two tests' pytest result line, pasted from its run over this tree>

probe skipped: slow case — tests/test_research_b2_full_basis.py::test_the_b2_full_inputs_reproduce_the_measured_basis
probe skipped: slow case — tests/test_research_b2_full_basis.py::test_the_b2_full_arm_a_reproduces_records_45_and_50s_arm_a
Both read data/ohlc-full and data/derivatives-funding: re-run them with the two sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, they skip.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: The conventions' entry, then the reads over the branch** — first, with `iteration-closeout` loaded, the entry `[iter-181] B2 trial 2's conventions, pinned by spec 00137 before its hash (Decision: 1)` at the end of `docs/research/10.phase4-decisions.md`, in the form of `[iter-179] B1 trial 5's conventions, pinned by spec 00135 before its hash`: option 1, the spec's **Author's call**s as it pins them (`grep -n "Author's call" docs/specs/00137-b2-trial-2-ohlc-full-design.md`), chosen; option 2, the alternatives each weighs; staged alone, the Global Constraints' gate over it and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-181] B2 trial 2's conventions, pinned by spec 00137 before its hash`. Then the trio over the whole branch, `develop..HEAD` — the spec, the two ruling entries, this plan and that entry among its commits — as CLAUDE.md orders it: `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two (Global Constraints' reads line); every dispatch carries the hash rule — in a `review` or `re-review` `drive` as one sentence in words, since a drive names no path: nothing runs a bar or arm B over the real data before the spec's hash, and the data-gated cases run with the frozen full set and the funding set linked into the reader's worktree and unlinked before its removal, since unlinked they skip. Each report names the tip it read, the tip Task 3 step 1 diffs from. Task 3 waits until the trio has closed with no open Critical or Important.

______________________________________________________________________

### Task 3: the run, through spec 00133's trial-attempts log (D7, D10)

**Files:** `docs/reference/trial-registry.jsonl` (or, on a stop, `docs/reference/reading-ledger.jsonl`), appended by the command and committed in Task 4; scratch under `.tmp/plan-00137/`.

**Interfaces:**
- Consumes: `cli/research/command.py`'s `eval_subject` register path as Task 1 names it; the trial-attempts log `.local/trial-attempts.jsonl` in the main checkout, its row `60c9f39c37ec81b4a53396218b690304 zcrypto-ops` in `docs/reference/trial-attempt-logs.txt`; the record's `attempt` block (`id`, `begin`, `log`, `absorbs`, `counted`); Task 1's subjects; Task 2's `ENGAGED_PER_ASSET`, `ENGAGED_PER_YEAR` and `coverage()`.
- Produces: one appended registry record (or ledger reading), checked; the pre-flight's output and the run's output under `.tmp/plan-00137/`.

Every step's command is read here, never run before its step: the run is the task loop's, after the plan review.

- [ ] **Step 1: The gate** — each its own call, each read before the next:
  - The reads through Task 2 (Task 2 step 6) have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names in its report> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00137-b2-trial-2-ohlc-full-design.md` exits 0; with no report naming a tip, stop: the reads come first. A fix or a merge of develop changes it — a read of that diff comes first, its `re-review` within the branch's two, and this check then names its tip.
  - Arm A's code path since record 50's run: `git log --oneline eb45b37883604c8c793cbff6e0756aefe7bcd2ef..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry/observed.py cli/ohlc cli/derivatives uv.lock pyproject.toml .python-version` lists the spec's six spec-00136 commits (its measured basis), `eb77ed063` (the dev-dependency ruff bump, `pyproject.toml` and `uv.lock` alone) and `9ad6a0794` (the merge of develop that carried it into spec 00136's branch), and Task 1's commit and its fixes alone; any other commit is named in the task report, step 4's data tests deciding whether it moved arm A.

- [ ] **Step 2: D10 step 1, the spec hash** — `sha256sum docs/specs/00137-b2-trial-2-ohlc-full-design.md`; its value, pasted from that call, is the `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.

- [ ] **Step 3: D10 step 2, the develop check** — `git fetch origin develop`, then `git diff --quiet origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0, so an append chains onto develop's last line; if not, develop is merged first (`git merge --no-edit origin/develop`, alone, then step 1's checks again). It runs again immediately before step 6's `--register` and before a stop's `--reading`; a failure there is the owner's question before any append.

- [ ] **Step 4: The data tests on the run's tree** — `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_full_basis.py -q -p no:cacheprovider --basetemp=.tmp/plan-00137/pt` reads `2 passed`, never a skip; a failure is the owner's question before the pre-flight.

- [ ] **Step 5: D10 step 3, the pre-flight** — `mkdir -p .tmp/plan-00137 && uv run zcrypto research eval --subject b2-funding-derisk-full-preflight --dataset ohlc-full > .tmp/plan-00137/preflight.out 2>&1` — a plain eval of a subject with no rule, which spec 00133 D7 admits, about 2–3 min — then, on its exit 0, the check, which reads D7's (a), (b), (c) and (d) in that order and exits 1 on a stop with one of its four `sys.exit` messages:

```
uv run python - <<'EOF'
import json, sys
from pathlib import Path
from cli.registry.record import compute_hash
from tests.test_research_b2_full_basis import ENGAGED_PER_ASSET, ENGAGED_PER_YEAR, coverage
out = Path(".tmp/plan-00137/preflight.out").read_text(); run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]; m = run["metrics"]
block = compute_hash(run["datasets"]); print("block", block)
if block != "3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8": sys.exit("the inputs' block differs from the spec's")
anchors = {"arm_a_ann_sharpe_noc": (1.405, 4), "arm_a_ann_sharpe_noc_decisive": (1.3716, 4), "arm_a_max_drawdown_full": (0.2154, 4),
           "arm_a_spot_drag_pct_yr": (0.0703, 4), "benchmark_ann_sharpe_noc": (1.2128, 4), "benchmark_ann_sharpe_noc_decisive": (1.2447, 4),
           "turnover_a": (146.19, 2)}
off = {k: m[k] for k, (v, d) in anchors.items() if round(m[k], d) != v}
if off: sys.exit(f"arm A does not reproduce record 45's arm A: {off}")
basis = {"engaged_per_asset": ENGAGED_PER_ASSET, "engaged_per_year": ENGAGED_PER_YEAR, "binperp_funding_z30d_coverage": coverage()}
off = [k for k, v in basis.items() if m[k] != v]
if off: sys.exit(f"the engagement or the coverage differs from the measured basis: {off}")
print("engaged", sum(m["engaged_per_asset"].values()), m["engaged_per_year"])
print({k: m[k] for k in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "arm A fails its bar")
EOF
```

  A block that differs, an anchor off, an engagement or coverage off the basis, or `passes` 0 is D7's instrument finding — stop: no run, no verdict, the trial unspent. A stop is the check exiting on exactly one of its four `sys.exit` messages; a traceback from the check, or a pre-flight killed before it exits, is an environment fault, never a stop, and the owner's question before step 6. The stop is kept as a reading, after step 3's check, the same build and about as long: `uv run zcrypto research eval --subject b2-funding-derisk-full-preflight --dataset ohlc-full --reading --iteration iter-181 --spec-hash <step 2's sha256> --notes "<what failed, quoted from the check's output; no verdict, the trial unspent>"`; Task 4 records it. A refused build — exit 1 with no `Traceback (most recent call last):`, its output ending in a refusal raised inside the build, one of four shapes: `b2-funding-derisk-full-preflight over the full history: …` (the window, or a compute error), `… over the full history of ohlc-full: … (<class> raised at …)`, or the set or file the build read named first, `derivatives-funding…: …` or `ohlc-full…: …` (`derivatives-funding/<PERP>/funding.parquet: …`, `ohlc-full/<ASSET>/EUR/240.parquet: …`) — prints no metrics: the check is not run and no reading is kept, the `--reading` re-run refusing alike (D7), and Task 4 runs its arm for a refused build. Any other exit 1 — a traceback, or a refusal before the build such as `dataset 'ohlc-full' is absent: …` where a link is missing — is a code or environment fault, never D7's finding, and the owner's question before step 6.

- [ ] **Step 6: D10 step 4, the trial** — one run, by the owner or on their word, after step 3's check: `uv run zcrypto research eval --subject b2-funding-derisk-full --dataset ohlc-full --register --iteration iter-181 --family B2 --n-trials 1 --variant B2-funding-derisk-a2eq-full-v1 --spec-hash <step 2's sha256> --notes "<below>" > .tmp/plan-00137/trial2.out 2>&1`, then `cat .tmp/plan-00137/trial2.out`; the run takes about 4–5 min. No `--verdict` and no plain eval, before or after (D10). The notes, written before the run, name only what is fixed before it: `subject b2-funding-derisk-full over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble at half its position on an asset while that asset's 30-day funding z-score, as-of at the 4h close on prints truncated to their hour, exceeds +2, no hold-through, every position change charged 0.006 per side; the hypothesis: the half-scale improves the ensemble's net-of-cost performance through a lower drawdown at the engaged stamps, against the unconditioned ensemble; n_trials 1, var_trials 0.0, the DSR leg binding; the head-to-head from 2021-01-01 decides, the full-window read recorded beside it; pre-flight: block 3da5e397…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: threshold 2.5, scale 0.25, the z < -2 re-risk; the matrix pre-registered by the spec's sha256 <step 2's value>`. A refusal from the count — a B2 attempt that never landed, or bucket B spent — comes before the fit or after the print, naming each orphan or the bucket's spent figure, and the trial goes back to the owner through T0023 (D10): Task 4 runs its refusal arm, with no record and no reading. A stop by the rule writes a reading carrying its attempt, which counts 0. On any exit but a record, the count's refusal or the rule's stop — a refused build, a traceback, a run killed before it exits — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b2-funding-derisk-full"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`. A refused build ends its attempt failed, which counts 0: no record and no reading, Task 4 running its arm for it once that check prints the attempt's id beside a list holding its `failed` text. A traceback, another refusal, or `open` printed by that check is a code or environment fault and the owner's question before Task 4 and before any re-run: an open attempt — a run killed mid-fit leaves one — counts against B2 and bucket B until a run with the same arguments and spec hash absorbs it (spec 00133 D3), and that run's record then fails step 7's `attempt` check.

- [ ] **Step 7: The record's checks** — on a record, each failure the owner's question before Task 4:

```
uv run python - <<'EOF'
import json, sys
from pathlib import Path
from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_full_basis import ENGAGED_PER_YEAR, coverage
SPEC_HASH = "<step 2's sha256>"
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1]); m = r["metrics"]
out = Path(".tmp/plan-00137/trial2.out").read_text(); printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
subject = SUBJECTS["b2-funding-derisk-full"]
checks = {
    "spec_hash": r["spec_hash"] == SPEC_HASH,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == "3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8",
    "invocation": {k: r["invocation"][k] for k in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
    == {"subject": "b2-funding-derisk-full", "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"]) == ("B2", 1, "B2-funding-derisk-a2eq-full-v1", "iter-181", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": (m["engaged_per_year"], m["binperp_funding_z30d_coverage"]) == (ENGAGED_PER_YEAR, coverage()),
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
EOF
```

  It reads the registry's last line, so it runs only after step 6 appended one; `printed` is the first JSON object the run printed. `counted` is printed, never checked: a non-empty one, an orphan the count admitted elsewhere in bucket B, is no failure of the run — Task 4's header and T0016's line name it. On a stop by the rule, the ledger's last line is checked instead: its subject `b2-funding-derisk-full`, its outcome the `no_verdict` text, its `attempt` non-null, its `spec_hash` step 2's.

No commit: the appended line lands in Task 4's commit, with the decisions-log header that names it and the literal that pins its subject — `tests/test_decisions_log_ties.py::test_the_committed_decisions_logs_tie_every_verdict_to_its_record` and `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` hold only over the three together.

______________________________________________________________________

### Task 4: the verdict — the record, the decisions log, T0023, T0016 and on an adopt T0123 (D10, D11)

**Files:**
- Modify: `docs/reference/trial-registry.jsonl` (appended by Task 3), `tests/test_trial_registry_provenance.py`, `docs/research/10.phase4-decisions.md`, `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`; on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md`; on a stop `docs/reference/reading-ledger.jsonl` in the registry's place and no literal; on a refusal from the count, T0023 and the index, and T0016 when the refusal came after the print; on a refused build, the decisions log, T0023 and the index; `docs/reference/change-index.md` in step 8's own commit

**Interfaces:**
- Consumes: `tests/test_trial_registry_provenance.py`'s `LANDED_N_TRIALS: dict[str, int] = {"b1-hourly-rv": 3, "b1-volume-confirmation": 4, "b1-hourly-channel-exits": 5}` and `test_each_landed_subjects_n_trials_is_frozen_at_its_literal`; `tests/test_decisions_log_ties.py`'s `(registry trial N` and `(attempts counted: <log8>#<id>, …)` ties; Task 3's record, checked.
- Produces: the records commit and step 8's change-index row commit.

On a refusal from the count there is no record and no reading: steps 1, 4, 5 and 6 run, step 4 on its refusal arm, staging T0023 and the index — and T0016 when the refusal came after the print — then step 7's commit with no replay case and no probe, under `docs(open-topics): B2 trial 2 refused by the count; T0023 holds the refusal for the owner`, then step 8. On a refused build there is no record and no reading: steps 1, 2, 4, 5 and 6 run on their stop arm, with the refusal line quoted from `.tmp/plan-00137/preflight.out` or `.tmp/plan-00137/trial2.out` — the decisions-log header `[iter-181] B2 trial 2 — instrument finding, the run refused; the trial unspent`, which names no verdict and takes no tie; T0023's findings the refusal line; no ledger staged — then step 7's commit with no replay case and no probe, under the subject line `docs(research): B2 trial 2 — instrument finding, the run refused; no trial spent, the shared B budget at 20`, then step 8.

- [ ] **Step 1: The PR's title** — `feat(research): iter-181 — B2 trial 2: funding de-risk on ohlc-full`, 67 characters, under `open-pr`'s cap of 72. The PR is created in step 8, after step 7's commit.

- [ ] **Step 2: The decisions-log entry**, at the end of `docs/research/10.phase4-decisions.md`, after the two `[iter-181]` entries, written with `iteration-closeout` loaded. The matrix is printed from the spec the record pins, `sed -n '/^| Kill bar/,/^Every quantity/p' docs/specs/00137-b2-trial-2-ohlc-full-design.md`, and the row read off the record's stored keys beside its stored verdict. The header: `[iter-181] Verdict — B2 trial 2 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B2 n=1)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry (spec 00133 D10); its text to its first `. ` holds no verdict word but its own. The body: the row that fired with the four keys the matrix reads (`passes`, `head_to_head_mean_outperf_2021`, `head_to_head_spa_p_2021`, `max_drawdown_reduction_pct`), unrounded, `max_drawdown` beside `arm_a_max_drawdown` (the from-2021 read's), and the full-window `head_to_head_mean_outperf_full` and `head_to_head_spa_p_full` beside them; `n_trials` 1, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); the six SPA cells, `spa_p_decisive_b102_s42` among them, recorded and unread; the pre-flight's block, anchors and `passes`, read from `.tmp/plan-00137/preflight.out`; the engagement proof — `engaged_per_year`, `stamps_positions_differ` and `positions_differ_per_year`, `turnover_a` beside `turnover_b`, and the per-year drawdown pairs; on a park its variants (threshold 2.5, scale 0.25, the z < −2 re-risk), each a new trial of the shared budget whose adoption path goes to the owner; on an adopt D11's path in its order. On a stop the entry is `[iter-181] B2 trial 2 — instrument finding, the trial unspent (reading <its id>)`, naming what failed, quoted from the check or the record.

- [ ] **Step 3: The landed subject's literal** — on a record only: `LANDED_N_TRIALS` becomes `{"b1-hourly-rv": 3, "b1-volume-confirmation": 4, "b1-hourly-channel-exits": 5, "b2-funding-derisk-full": 1}` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts becomes the same dict — the subject's first landed record adds its row in the PR that lands it.

- [ ] **Step 4: The topics**, per `topic-ops`. T0023's `ripe_when` names the instrument ruling the first `[iter-181]` entry discharged, and is rewritten for what the verdict leaves, an activity with a check that prints at least 1 once it happens and 0 when this step commits it, run then and its output read, shown matching a sample header in `iteration-closeout`'s form:
  - reject: `an activity: the owner picks B2's next step after trial 2's reject — the OI leg, the z < −2 re-risk, a liquidations trial, or closing the family — recorded in the decisions log; check: grep -c -E '^\[iter-[0-9]+\] B2.s next step after trial 2' docs/research/10.phase4-decisions.md prints at least 1`;
  - park: the same activity after trial 2's park, its variants (threshold 2.5, scale 0.25, the z < −2 re-risk) each a new trial of the shared budget and its adoption path the owner's to rule, with the same check;
  - adopt: `an activity: the P1 combination trial over record 47's book carrying B2 trial 2's arm B is picked for an iteration; check: cat docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md | grep -c -E '^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book' prints at least 1`, the second log the one `iteration-closeout` routes a combination of sleeves to; T0123's `ripe_when` gains `— registry trial <N>, B2 trial 2's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries it adopts`, written in this commit so no tree holds the adopt without it (D11's **Author's call**, as spec 00135 D13 did for B1);
  - stop: `an activity: the owner decides B2's next step after trial 2's instrument finding, recorded in the decisions log; check: grep -c -E '^\[iter-[0-9]+\] B2.s next step after trial 2.s instrument finding' docs/research/10.phase4-decisions.md prints at least 1`;
  - refusal from the count: T0023's findings take the refusal as `.tmp/plan-00137/trial2.out` printed it, each orphan or the spent bucket it named, and, when it came after the print, the metrics printed before it, a look no record carries; `an activity: the owner rules on B2's second trial after the count refused it — a new subject under a new spec declaring the count its orphans need, or bucket B's spent budget — recorded in the decisions log; check: grep -c -E '^\[iter-[0-9]+\] B2 trial 2 after the count.s refusal' docs/research/10.phase4-decisions.md prints at least 1`; T0016 unchanged on a refusal before the fit, and after the print its budget line counts what the refusal counted, named on that line.
  T0023's `## Findings so far` takes trial 2 — its record id, verdict, the row that fired, the engagement figures — or, on a stop, the instrument finding and its reading id; its `## Suggested next steps` drop the instrument-ruling item and say what the verdict leaves (D11's rows): on an adopt, the live funding feed's spec after the combination trial (D11's **Author's call**: a next step of T0023, no new topic); on a park, the three variants; on a reject, the family's OI, ratio and liquidation legs; the later-trials and Bybit items stay. On a verdict, T0016's budget line reads `B1 spent 5, B2 spent 1, 19 remain` — less one more for each orphan the record's `attempt.counted` lists, named on that line — and its B2 line under `## Done so far` names trial 2 (iter-181, spec/plan `00137`, registry trial <N>) and its verdict; on a stop T0016 is unchanged, 20 remaining. On any verdict but an adopt T0123 is untouched. `uv run python infra/scripts/topics-index.py` re-renders the index.

- [ ] **Step 5: Tests and gate** — the direct readers of each path the commit stages, run as the Global Constraints run them, `tests/test_decisions_log_ties.py`, `tests/test_decisions_log_shape.py` and `tests/test_open_topics_frontmatter.py` among them, pass; `uv run pre-commit run -a` until clean, its rewrites staged.

- [ ] **Step 6: Stage** — `git add docs/reference/trial-registry.jsonl tests/test_trial_registry_provenance.py docs/research/10.phase4-decisions.md docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md`; on a stop the ledger in the registry's place.

- [ ] **Step 7: The replay case and the probe, on the staged tree, then the commit** — in the probe worktree (Global Constraints' probe line), `data/ohlc-full` and `data/derivatives-funding` linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00137/probe/data/<set>` (`-n`, so a link already there is refused, never followed into the canonical set) and unlinked before its removal: `uv run pytest tests/test_registry_replay.py -k 'trial-<its id>' -q -p no:cacheprovider --basetemp=.tmp/pt` passes (on a stop `-k 'reading-<its id>'`) — run there because the case fails on any uncommitted change under the registry and the ledger — its result line for the message, a difference the owner's question before the commit; on a record, the literal's probe: `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_verdict(/def _b2_verdict_gone(/' --mutation 's/^_B2_FULL_N_TRIALS = 1/_B2_FULL_N_TRIALS = 2/' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`, expected `KILLED`. Then:

```bash
git commit -F - <<'EOF'
docs(research): B2 trial 2 registered — <verdict>; T0023 and T0016 after it, the shared B budget at <the remaining figure step 4 wrote on T0016's budget line>

<the tie and provenance tests' pytest result line, and the replay case's, pasted from their runs over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<the literal's infra/scripts/mutate-probe.sh command, then its verdict line>
The replay case reads data/ohlc-full and data/derivatives-funding: re-run it with the two sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

  On a stop the subject line is `docs(research): B2 trial 2 — instrument finding, kept as reading <id>; no trial spent, the shared B budget at 20`, with no literal and no probe.

- [ ] **Step 8: The read, the PR and the merge** — the change-index row through `open-pr`'s Step 4, step 1's title, its own commit; then the `pre-review` of this task's commits, then the read of the delta from the tip the last read covered — `review` over `<that tip>..HEAD`, since the commit adds files outside that read's range, and `re-review` over a fix of it, within the branch's two (Global Constraints' reads line), each `drive` carrying one sentence in words: the data-gated cases the messages record run with the frozen full set and the funding set linked into the reader's worktree and unlinked before its removal, since unlinked they skip — then the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR created through `open-pr`, its body: the verdict, the instrument finding or the count's refusal, every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of the data-gated cases that read sets not linked here (`tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-1]` and `tests/test_research_b2_basis.py::test_the_b2_inputs_reproduce_the_measured_basis_and_arm_a_is_the_builders_a2_sleeve`, which read `data/ohlc-rolling`, and `tests/test_b1_records_reproduce.py::test_the_b1_subject_reproduces_its_record[record-45]`, which reads `data/ohlc-15m`) — and the read line naming the tip the delta's read covered, `merge-pr`'s gate refusing any other. Merged on the owner's word through `merge-pr`; before it, `git status --short --ignored` is read, `.tmp/plan-00137` removed, `unlink data/ohlc-full` and `unlink data/derivatives-funding`, and `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the two canonical sets still there. Decisions log: the conventions entry (Task 2 step 6), before the hash, and the verdict entry above, written after the run.
