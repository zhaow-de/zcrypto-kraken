# B4 trial 2 — SOL/BTC alone on the A2-4h ensemble, held to the book's own BTC, on ohlc-rolling as of 2026-10-10: the trial subject and its twin, the data-gated basis test, the conventions before the hash, the gated run and the record, B4's close and T0016 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b4_sol_noborrow_rolling_basis.py docs/research/10.phase4-decisions.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/test_trial_registry_provenance.py tests/retired_subjects.py docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00146-b4-sol-noborrow-rolling-design.md docs/plans/00146-b4-sol-noborrow-rolling.md` prints `tier: full`, for `tests/test_research_command.py` "a test importing cli.alpha", `tests/test_research_b4_sol_noborrow_rolling_basis.py` "a test importing cli.alpha.b1" once Task 2 has created it, `docs/reference/trial-registry.jsonl` and `tests/test_trial_registry_provenance.py` "a test importing cli.registry").

**Goal:** B4's trial 2 (spec 00146) — the adopted A2-4h ensemble on eleven instruments, its ten EUR assets and the venue's SOL/BTC pair held each bar to the book's own BTC, against the ten-asset ensemble, on `ohlc-rolling` as of 2026-10-10: two research subjects in `cli/research/subjects.py`, the trial and its evaluate-only pre-flight twin; the data-gated test of their inputs half; the trial's conventions in the decisions log before the hash; the trial run through spec 00133's trial-attempts log, its verdict or stop in the registry and the decisions log; then, on a verdict, B4's close on the owner's word, T0016 with B3 next, and the subjects' retirement.

**Architecture:** no new module and no change to `cli/alpha/` or `cli/registry/`. `cli/research/subjects.py` gains one block before `SUBJECTS` — `_B4_SOL`, `_B4_SOL_N_TRIALS`, `_B4_SOL_SEEN_TO`, the build in three halves (`_b4_sol_reads`, `_b4_sol_inputs`, `_b4_sol_metrics` / `_b4_sol_preflight_metrics`), `_b4_sol_unseen`, `_b4_sol_engagement`, `_b4_sol_build`, the two builders and the three key sets — and two `SUBJECTS` entries. Trial 58's `_B4Reads`, `_B4Inputs`, `_b4_ensemble`, `_b4_limited`, `_b4_shortfall`, `_b4_net`, `_b4_arm_a_bar`, `_b4_ratio_legs_verdict` and key sets, and `cli/alpha/b4.py`'s functions, are read as they are, and no import is added. The family key `B4` is in `BUCKET_OF` already. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00146-b4-sol-noborrow-rolling-design.md` — binding; D1–D11 are cited by name and the values below are copied from it. It reads spec 00144's books, costing, limits, bar, matrix and rule, frozen by record 58's `spec_hash`, and spec 00145's borrow-free funding, frozen by reading 6's. **Iteration:** iter-191. **Topic:** T0016, its B4 arm. **Branch:** `research/iter-191-b4-sol-noborrow-rolling`, worktree `.claude/worktrees/iter191`, `data/ohlc-rolling` and `data/ohlc-full` linked read-only from the main checkout, and no other set. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: Tasks 1–2's code and tests were written in this worktree beside the staged spec; Task 1's new cases measured red against the base module, in a detached scratch worktree at the base with the test file alone applied (`26 failed, 832 deselected`, each at its call), and green with the code (`26 passed, 850 deselected`), the shared rows the two subjects add green (`19 passed, 857 deselected in 160.27s`); Task 1 step 7's four gate parts green; Task 2's data-gated case `1 passed` with a call of 168.93 s; the slow cases timed; Task 1's 60 probe rows run in a detached scratch worktree on Task 1's tree, committed there, 60 of 60 `KILLED`; on Tasks 1–2's tree committed in that worktree, the conventions entry appended and run through the decisions-log tests, Task 3 step 4's data test and fixture rows (`3 passed in 220.30s`) and record 58's replay (`1 passed in 311.09s`) run with both sets linked, Task 3 step 5's pre-flight check run over a synthetic pre-flight print carrying the real block, and Task 5's close entry, T0016 edits, index and retirement tried, with each outcome's `ripe_when` arm, then reverted. The fences applied to the base as the steps say reproduce every authoring file; the files were restored to the base before this plan was committed. Not run: any `zcrypto research eval` of the two subjects (Task 4), the record's check program beyond a parse, the record's replay and the literal's probe (Task 4), the topic edits as committed (Task 5) and the PR (Task 6).

## Global Constraints

- **The books and the costing** (D2–D5): the union `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)` and SOL/BTC's 4h pair read through the run's `ObservedReader` — `read_rolling(dataset, "SOL/BTC", 240, as_of, window=window, accept_holes=accept_holes)` given an as-of, `read_series(dataset, "SOL/BTC/240.parquet", window=window)` on a frozen set — mapped onto the union's stamps, `None` where the pair has no bar; arm A `_b4_limited(_b4_ensemble(fed))`, arm B `_b4_limited(borrow_unavailable(_b4_ensemble(fed | {"SOL/BTC": ratio}), _B4_LEGS, "BTC"))`, `fed = _ffill_btc(h4_prices)`, returned as trial 58's `_B4Inputs` with arm B in both `arm_b` and `no_borrow`; SOL/BTC's first weight the first return index of `_inverse_vol_weights(fed | {"SOL/BTC": ratio}, lookback=180)` holding it; its EUR return `ratio_eur_returns(ratio, fed["BTC"])`; every book costed by `_b4_net(positions, returns, stress=…)`.
- **The run's invocation** (D2, D10): `--dataset ohlc-rolling --as-of 2026-10-10`, no `--window`, no `--accept-holes`; never `zcrypto data fetch`.
- **The bars** (D8): every `a1_kill_bar` call `n_trials=2, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`, the headline (30, 42); arm A's bar `_b4_arm_a_bar` at (30, 42); the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` at `first` 0, at SOL/BTC's first weight (17,079) and at the cut (27,337), the cut the first return index whose close is after `_B4_SOL_SEEN_TO`, 2026-03-31 20:00Z; refused before any bar: fewer than 2 return indices from the first weight or after the cut.
- **The count** (D8): `_B4_SOL_N_TRIALS = 2`, `required_n("B4")` as the spec measured it, fixed by the spec's hash; at `var_trials` 0.0 the DSR leg is the PSR against 0.
- **The rule** (D8): `_b4_ratio_legs_verdict`, unchanged — `None` when `arm_a_passes` is 0 or SOL/BTC is held at no return index, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0` with `head_to_head_spa_p_primary < 0.05`, `park` on the first with the p at or above 0.05, `reject` otherwise; no park variants; the unseen months in no leg.
- **The record** (D9): family `B4`; `n_trials_in_family` 2; variant `B4-sol-noborrow-a2eq-rolling-v1`; iteration `iter-191`; seeds (42, 7, 1234); 49 metric keys; the block `c05629c70826656ca225857f6b5b682bfc00a737a0feff91f78b57cf70c93295`; the invocation `ohlc-rolling` as of 2026-10-10, `accept_holes` false; no `--verdict`.
- **The pre-flight read** (D10), in this order: (a) the block, the set's vouched status `chained (as of 2026-10-10, line fcb62a79fab7)` and no hole printed (Task 2's `BLOCK` and `VOUCHED`); (b) arm A's three seen-span figures, `arm_a_ann_sharpe_noc_seen`, `arm_a_ann_sharpe_noc_decisive_seen` and `arm_a_max_drawdown_seen`, equal to record 58's stored `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive` and `arm_a_max_drawdown` to the last digit, and `turnover_a` the basis's (Task 2's `TURNOVER_A`); (c) the engagement the measured basis's — Task 2's `ENGAGEMENT`, and `carry_per_year` rounding to nothing at six decimals; (d) SOL/BTC held at some return index; (e) arm A's `passes` 1.
- **The hash rule** (D10): before Task 3 step 2 takes the spec's sha256, nobody reads or computes arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — by code, a program or arithmetic over a stored figure — nor runs `b4-sol-noborrow-rolling` or `b4-sol-noborrow-rolling-preflight` over the real set; positions, weights, exposures, the shortfall, limit engagement and turnover are allowed — what the data-gated test (Task 2) computes, and no return of a book. `a2_book_returns` computes each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; nothing reads them. Reading 6's replay, which rebuilds arm B's returns over the span the two sets share, never runs before Task 4's run. No reader, reviewer or plan-review dispatch runs either subject over the real set before the hash, and every read's dispatch carries this rule. The trial subject is evaluated over the real set once, by Task 4's `--register` run, never as a plain eval; after it, only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with both sets linked.
- **Unchanged** (D9): every existing function of `cli/research/subjects.py` — trial 58's and reading 6's machinery among them — `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/risk/*`, `cli/costs/*`, `cli/validation/*` and `cli/engine/*`; B4's existing subjects, record 58 and reading 6; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/research/subjects.py` from Task 1 on, nothing else; from Task 1 on, `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@')" = 2` and `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@ -[0-9]*,0 ')" = 2` each exit 0 — two hunks, each a pure insertion, so a line changed or added anywhere but at Task 1 step 3's two sites is a third hunk or an impure one. Measured on the authoring tree: `@@ -3966,0 +3967,227 @@` and `@@ -4355,0 +4583,25 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00146-b4-sol-noborrow-rolling-design.md` after Task 3 step 2, nor specs 00128, 00133, 00144 and 00145, nor the spec before then except a fix commit a read of Task 2 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 4 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-rolling` and `data/ohlc-full`, read-only links, never written under; never `zcrypto data fetch`. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The trial, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 3 step 3, Task 4 step 1) and Task 6's `gh` calls, push and `merge-pr` are the exceptions. A data link is removed with `test -L <its absolute path> && unlink <its absolute path>`, never `rm`.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 2 step 6's reads, Tasks 3–4 and Task 6, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the pre-flight, the register, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1 and 5 and Task 2's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00146 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00146/` follows `mkdir -p .tmp/plan-00146 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00146/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `mkdir -p .tmp/plan-00146 && bash infra/scripts/consumers.sh --direct <each changed path> | sort -u > .tmp/plan-00146/T.txt`, never with `2>/dev/null`, whose stderr is where a refusal speaks, and `test -s .tmp/plan-00146/T.txt && uv run pytest $(cat .tmp/plan-00146/T.txt) -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt`, so that an empty list fails closed and never becomes a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every file a commit carries is staged by explicit path — the registry's line by `--register`, the ledger's by `--reading` or by a stop under `--register`, among them, whose one commit is Task 4 step 6's — since the commit and the probe setup's `git write-tree` read the index while the list reads the working tree. Every list holding `tests/test_research_command.py` runs it in four parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms, so that none can pass 600 s: `tests/test_research_command.py -k "not reentry and not b2"` (`--basetemp=.tmp/plan-00146/pt-1`, measured on the authoring tree, Tasks 1–2's code in it, `468 passed, 408 deselected in 203.20s`), `tests/test_research_command.py -k "b2 and not reentry"` (`pt-2`, measured `227 passed, 649 deselected in 312.71s`), `tests/test_research_command.py -k reentry` (`pt-3`, measured `71 passed, 805 deselected in 89.04s`) and the rest of the list, read off `.tmp/plan-00146/T.txt` with that file's line left out (`pt-4`). Every commit message carries the result line of each test command its gate ran, a run over that commit's own tree, and the two trailer lines exactly as the executing session's attribution gives them — `Co-Authored-By:` naming the model that ran the step, and `Claude-Session:`.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00146 &&
  test ! -e .tmp/plan-00146/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00146/probe HEAD &&
  git -C .tmp/plan-00146/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00146/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00146/probe/.tmp
```

  Then, from `.tmp/plan-00146/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. A mutation whose text also stands in an existing function — trial 58's inputs, metrics and engagement share several lines with the new ones — carries the address of its own function's range, `/^def <name>(/,/^def /`, of its entry's, `/"<subject>": Subject(/,/^    ),/`, or of the reused rule's, `/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/`, so its dry run changes one line; a pattern that holds `'` writes it as `.`. After the last verdict, `git worktree remove --force .tmp/plan-00146/probe` — each data link in it unlinked first with `test -L <its absolute path> && unlink <its absolute path>`, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, `ohlc-rolling` and `ohlc-full` still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subjects' names** (D9): `b4-sol-noborrow-rolling` and `b4-sol-noborrow-rolling-preflight`, which no registered or retired subject's name equals or opens with a hyphen, and which open none (the spec's basis). Every new test function's name carries `b4_sol`, which no hyphenated id and no other test's name carries, so `-k b4_sol` selects them alone; the shared rows the two subjects add carry the hyphenated `b4-sol-noborrow-rolling` in their ids.

## Task 1: the trial subject and its pre-flight twin in `cli/research/subjects.py` (D2–D9)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes `cli/research/subjects.py`'s `_capturing_union`, `_b2_over`, `close_grid`, `calendar_year_slices`, `_B4Reads`, `_B4Inputs`, `_b4_ensemble`, `_b4_limited`, `_b4_shortfall`, `_b4_net`, `_b4_arm_a_bar`, `_b4_ratio_legs_verdict`, `_B4_LEGS`, `_B4_CARRY_RATE`, `_B4_ENGAGEMENT_KEYS`, `_B4_METRIC_KEYS`, `_B4_PREFLIGHT_KEYS`, `_ffill_btc`, `_inverse_vol_weights`, `_asset_returns`, `ratio_eur_returns`, `borrow_unavailable`, `per_year_counts`, `per_year_means`, `per_year_sums`, `per_year_positions_differ`, `per_year_turnover`, `per_year_max_drawdown`, `shortfall_carry`, `book_turnover`, `a1_kill_bar`, `net_of_cost_verdict`, `sharpe`, `max_drawdown`, `_B2_LOOKBACK`, `_B2_COST_PER_SIDE`, `PPY_4H`, `_DECISIVE_START`, `_N_RESAMPLES`, `_B2_ARM_A_BAR_KEYS`, `_B2_ARM_A_BAR_FLAGS`, `_ASSETS`, `Subject`, `SubjectError`, `ObservedReader` and the error classes it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_b4_dataset`, `_b4_leg_short_reads`, `_b4_own_books`, `_b4_own_leg_books`, `_rows`, `_B4_ENGAGEMENT_KEYS`, `_B4_METRIC_KEYS`, `_B4_PREFLIGHT_KEYS`, `_B4_SOL_FROM`, `_B2_ASSETS`, `_B2_GRID`, `_EUR_PAIRS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_recording`, `_fake_kill_bar`, `_fake_head_to_head`, `_fake_benchmark`, `_anchor`, `_as_trial`, `_no_close_column`, `_not_parquet`, `HOLE`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`, `runner` and `app`. Produces the two subjects, `_b4_sol_reads`, `_b4_sol_inputs`, `_b4_sol_unseen`, `_b4_sol_engagement` and `_B4_SOL_N_TRIALS`, which Task 2's test and Task 4's literal read.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - `from tests.rolling_fixtures import HOLE, write_chain` becomes `from tests.rolling_fixtures import HOLE, line_bytes, write_chain`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, after its `assert subjects.SUBJECTS["b4-leg-reading"].metric_keys == _B4_LEG_SPEC_KEYS` line:

```python
    assert subjects.SUBJECTS["b4-sol-noborrow-rolling"].metric_keys == _B4_SOL_METRIC_KEYS
    assert subjects.SUBJECTS["b4-sol-noborrow-rolling-preflight"].metric_keys == _B4_SOL_PREFLIGHT_KEYS
```

  - after `test_the_b4_leg_reading_refuses_as_of_before_any_read` and before `def _ruled_signal(`, two blank lines either side:

```python
_B4_SOL_SPEC = "docs/specs/00146-b4-sol-noborrow-rolling-design.md"
_B4_SOL_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or SOL/BTC holds no position at any stamp; no verdict, the "
    "trial unspent"
)
# Spec 00146 D9's keys, typed from the spec as record 58's and their changes, never read off a subject.
_B4_SOL_ENGAGEMENT_KEYS = _B4_ENGAGEMENT_KEYS | {"unseen_returns", "shortfall_max"}
_B4_SOL_METRIC_KEYS = (
    (
        _B4_METRIC_KEYS
        - {"no_borrow_head_to_head_mean_outperf_primary", "no_borrow_head_to_head_spa_p_primary", "no_borrow_ann_sharpe_noc"}
    )
    | _B4_SOL_ENGAGEMENT_KEYS
    | {"head_to_head_mean_outperf_unseen", "head_to_head_spa_p_unseen"}
)
_B4_SOL_PREFLIGHT_KEYS = (
    _B4_PREFLIGHT_KEYS
    | _B4_SOL_ENGAGEMENT_KEYS
    | {"arm_a_ann_sharpe_noc_seen", "arm_a_ann_sharpe_noc_decisive_seen", "arm_a_max_drawdown_seen"}
)
_B4_SOL_SEEN_TO = datetime(2026, 3, 31, 20, tzinfo=UTC)
# `_b4_sol_dataset`'s bars: 2025's last closes come after the frozen benchmark's 1,200-bar gate opens, and 54 return indices
# close after the last close reading 6 read.
_B4_SOL_START = datetime(2025, 5, 15, tzinfo=UTC)
_B4_SOL_BARS = 1_980
_B4_SOL_ROLLING_FROM = datetime(2025, 12, 1, tzinfo=UTC)
_B4_SOL_HOLE = date(2026, 10, 2)


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count(name):
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    assert (len(_B4_SOL_METRIC_KEYS), len(_B4_SOL_PREFLIGHT_KEYS)) == (49, 34)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B4_SOL_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b4_sol_noborrow_rolling and trial.metric_keys == _B4_SOL_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b4_ratio_legs_verdict, _B4_SOL_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B4", 2) == ("B4", subjects._B4_SOL_N_TRIALS)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        f"{name}-preflight",
        (240,),
        _B2_ASSETS,
        _B4_SOL_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b4_sol_noborrow_rolling_preflight
    assert preflight.metric_keys == _B4_SOL_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5
    assert subjects._B4_SOL_SEEN_TO == _B4_SOL_SEEN_TO


# Adopting on every key the rule reads, the full window's and the unseen months' head-to-heads against it, so a rule reading
# either in place of the primary read moves the adopt row.
_B4_SOL_ADOPTING = {
    "arm_a_passes": 1,
    "ratio_held_per_year": {"SOL/BTC": {"2021": 0, "2022": 3}},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "head_to_head_mean_outperf_unseen": -0.001,
    "head_to_head_spa_p_unseen": 0.9,
}
_B4_SOL_NEVER_HELD = {"ratio_held_per_year": {"SOL/BTC": {"2021": 0, "2022": 0}}}


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="outperforms-significantly-from-the-first-weight"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B4_SOL_NEVER_HELD, None, id="sol-btc-never-held"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B4_SOL_NEVER_HELD, "passes": 0}, None, id="holding-read-before-passes"),
        pytest.param({"passes": 0}, "reject", id="arm-b-fails-its-bar"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="p-0.2"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param(
            {
                "head_to_head_mean_outperf_primary": -0.001,
                "head_to_head_mean_outperf_full": 0.001,
                "head_to_head_mean_outperf_unseen": 0.001,
                "head_to_head_spa_p_unseen": 0.01,
            },
            "reject",
            id="mean-negative",
        ),
    ],
)
def test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop(name, change, verdict):
    assert subjects.SUBJECTS[name].verdict({**_B4_SOL_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_reads_map_sol_btcs_closes_onto_a_frozen_union_and_read_no_other_pair(tmp_path, name):
    root = _b4_dataset(tmp_path)
    frames = {i: pl.read_parquet(root / "ohlc-test" / f"{i}/EUR/240.parquet") for i in _B2_ASSETS}
    union = sorted(set().union(*(frame["ts"].to_list() for frame in frames.values())))
    sol = pl.read_parquet(root / "ohlc-test" / "SOL/BTC/240.parquet")
    closes = dict(zip(sol["ts"].to_list(), sol["close"].to_list()))
    reader = ObservedReader(root)

    h4_ts, h4_prices, ratios = subjects._b4_sol_reads(name, reader, "ohlc-test", None, None, False)

    assert h4_ts == union and set(h4_prices) == set(_B2_ASSETS)
    assert ratios == {"SOL/BTC": [closes.get(t) for t in union]}
    assert next(k for k, r in enumerate(ratios["SOL/BTC"]) if r is not None) == _B4_SOL_FROM
    assert set(reader.block()["ohlc-test"]["files"]) == {f"{i}/EUR/240.parquet" for i in _B2_ASSETS} | {"SOL/BTC/240.parquet"}


def _b4_sol_dataset(tmp_path: Path) -> Path:
    """The ten 4h series from `_B4_SOL_START` and SOL/BTC, SOL's prices over BTC's from bar `_B4_SOL_FROM`."""
    root = tmp_path / "data"
    start = int(_B4_SOL_START.timestamp())
    rows = {a: _rows(_B4_SOL_BARS, phase=i * 0.7, start=start, step=4 * 3600) for i, a in enumerate(_B2_ASSETS)}
    for asset, asset_rows in rows.items():
        write_parquet(to_frame(asset_rows), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    ratio = [
        [row[0], *(f"{float(x) / float(q)}" for x, q in zip(row[1:6], btc[1:6])), *row[6:]]
        for row, btc in zip(rows["SOL"], rows["BTC"])
    ]
    write_parquet(to_frame(ratio[_B4_SOL_FROM:]), root / "ohlc-test" / "SOL/BTC/240.parquet")
    return root


def _b4_sol_rolling_set(tmp_path: Path) -> Path:
    """A rolling set of the twelve pairs written by hand: a 15-minute base from `_B4_SOL_ROLLING_FROM` through the base
    day, then three tape days, BTC/EUR and SOL/BTC each with a hole on `_B4_SOL_HOLE`; each pair's closes a wave of its own."""
    root = tmp_path / "data"
    pairs = (*_EUR_PAIRS, "ETH/BTC", "SOL/BTC")
    seam, step = datetime(2026, 10, 1, tzinfo=UTC), timedelta(minutes=15)

    def bars(index: int, start: datetime, end: datetime) -> pl.DataFrame:
        slots = range((start - _B4_SOL_ROLLING_FROM) // step, (end - _B4_SOL_ROLLING_FROM) // step)
        close = [10.0 * (index + 1) * (1.5 + math.sin(i / 389 + index)) for i in slots]
        return pl.DataFrame(
            {
                "ts": [_B4_SOL_ROLLING_FROM + i * step for i in slots],
                **dict.fromkeys(("open", "high", "low", "close", "vwap"), close),
                "volume": [1.0] * len(close),
                "count": [1] * len(close),
            }
        )

    def put(relpath: str, data: bytes | pl.DataFrame) -> str:
        path = root / "ohlc-rolling" / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, pl.DataFrame):
            data.write_parquet(path)
        else:
            path.write_bytes(data)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    base = {f"base/{p}/15.parquet": put(f"base/{p}/15.parquet", bars(i, _B4_SOL_ROLLING_FROM, seam)) for i, p in enumerate(pairs)}
    notes = {"seam": seam.isoformat(), "base_from": "ohlc-15m-fixture"}
    prev = put("index/2026/09/30.json", line_bytes({"day": "2026-09-30", "prev": None, "files": base, "holes": {}, "notes": notes}))
    for offset in range(3):
        start = seam + timedelta(days=offset)
        day, holed = start.date(), {"BTC/EUR", "SOL/BTC"} if start.date() == _B4_SOL_HOLE else set()
        files = {
            f"days/{p}/{day:%Y/%m/%d}.parquet": put(f"days/{p}/{day:%Y/%m/%d}.parquet", bars(i, start, start + timedelta(days=1)))
            for i, p in enumerate(pairs)
            if p not in holed
        }
        line = {"day": day.isoformat(), "prev": prev, "files": files, "holes": dict.fromkeys(sorted(holed), HOLE)}
        prev = put(f"index/{day:%Y/%m/%d}.json", line_bytes(line))
    return root


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_reads_read_the_rolling_set_as_of_the_day_across_its_holes_and_no_other_pair(tmp_path, name):
    root = _b4_sol_rolling_set(tmp_path)
    own = ObservedReader(root)
    frames = {p: own.read_rolling("ohlc-rolling", p, 240, "2026-10-03", accept_holes=True) for p in (*_EUR_PAIRS, "SOL/BTC")}
    by_ts = {p: dict(zip(frame["ts"].to_list(), frame["close"].to_list())) for p, frame in frames.items()}
    union = sorted(set().union(*(by_ts[p] for p in _EUR_PAIRS)))
    reader = ObservedReader(root)

    h4_ts, h4_prices, ratios = subjects._b4_sol_reads(name, reader, "ohlc-rolling", None, "2026-10-03", True)

    assert h4_ts == union and h4_prices == {a: [by_ts[f"{a}/EUR"].get(t) for t in union] for a in _B2_ASSETS}
    assert ratios == {"SOL/BTC": [by_ts["SOL/BTC"].get(t) for t in union]}
    holed = [k for k, t in enumerate(union) if t.date() == _B4_SOL_HOLE]
    assert len(holed) == 6 and all(ratios["SOL/BTC"][k] is None and h4_prices["BTC"][k] is None for k in holed)
    assert sorted(reader.holes()["ohlc-rolling"]) == ["BTC/EUR 2026-10-02", "SOL/BTC 2026-10-02"]
    assert reader.block() == own.block()


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_arms_agree_bit_for_bit_until_sol_btc_takes_weight(monkeypatch, name):
    h4_ts, h4_prices, ratios = _b4_leg_short_reads()
    n = len(h4_ts) - 1
    ensembles = _recording(monkeypatch, "_b4_ensemble", lambda arguments, result: result)

    inputs = subjects._b4_sol_inputs(subjects._B4Reads(h4_ts, h4_prices, {"SOL/BTC": ratios["SOL/BTC"]}))

    (_, raw_a), (_, raw_b) = ensembles
    start = inputs.first_weight["SOL/BTC"]
    differ = [k for k in range(n) if any(raw_b[a][k] != raw_a[a][k] for a in raw_a)]
    assert set(raw_b) == {*raw_a, "SOL/BTC"} and 0 < start < n
    assert differ and differ[0] >= start
    assert all(p == 0.0 for p in raw_b["SOL/BTC"][:start]) and any(p != 0.0 for p in raw_b["SOL/BTC"])


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_inputs_hold_sol_btc_to_the_books_own_btc_and_cost_it_on_its_own_return(name):
    reads = _b4_leg_short_reads()
    h4_ts, h4_prices, ratios = reads
    trial, own = _b4_own_books(*reads), _b4_own_leg_books(*reads)["SOL/BTC"]
    # SOL/BTC outweighs the book's BTC at some stamps of this union, so its book held to the BTC differs from it carried.
    assert own["no_borrow"][0] != own["carried"][0]

    inputs = subjects._b4_sol_inputs(subjects._B4Reads(h4_ts, h4_prices, {"SOL/BTC": ratios["SOL/BTC"]}))

    assert (inputs.h4_ts, inputs.h4_prices, inputs.close) == (h4_ts, h4_prices, [t + timedelta(hours=4) for t in h4_ts[:-1]])
    assert inputs.first_weight == {"SOL/BTC": own["first"]}
    assert inputs.returns == {i: trial["returns"][i] for i in (*h4_prices, "SOL/BTC")}
    assert (inputs.arm_a, inputs.engaged_a) == trial["limited_a"] and (inputs.arm_b, inputs.engaged_b) == own["no_borrow"]
    assert inputs.no_borrow is inputs.arm_b


def _b4_sol_built_inputs(n: int = 1_600) -> subjects._B4Inputs:
    """Books made by hand over `n` return indices whose closes cross the last one reading 6 read — three assets and SOL/BTC,
    arm B short of BTC wherever the leg outweighs its BTC, a missing return on the leg, each limit engaged at a stamp of its
    own — for the metrics alone."""
    h4_ts = [datetime(2025, 8, 1, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n + 1)]
    first = 600

    def wave(k: int, phase: float, depth: float) -> float:
        return depth * (1 + math.sin(k / 11 + phase)) / 2

    arm_a = {a: [wave(k, i, 0.2) for k in range(n)] for i, a in enumerate(("BTC", "ETH", "SOL"))}
    arm_b = {a: [0.9 * p for p in v] for a, v in arm_a.items()}
    arm_b["SOL/BTC"] = [0.0 if k < first else wave(k, 3, 0.15) for k in range(n)]
    returns = {i: [0.01 * math.sin(k / (3 + j) + j) for k in range(n)] for j, i in enumerate(arm_b)}
    returns["SOL/BTC"][first + 7] = None
    engaged_a = {limit: [False] * n for limit in ("gross", "net", "margin")}
    engaged_b = {limit: [k == 900 + j for k in range(n)] for j, limit in enumerate(("gross", "net", "margin"))}
    h4_prices = {"BTC": [100.0 + k for k in range(n + 1)]}
    close = [t + timedelta(hours=4) for t in h4_ts[:-1]]
    return subjects._B4Inputs(h4_ts, h4_prices, close, returns, {"SOL/BTC": first}, arm_a, arm_b, arm_b, engaged_a, engaged_b)


def _b4_sol_own_net(inputs: subjects._B4Inputs, positions: dict, stress: float) -> list[float]:
    """Net of each instrument's turnover at 0.006 a side and of the carry on the BTC its SOL/BTC outweighs, both times
    `stress`."""
    gross = net_of_cost(positions, {i: inputs.returns[i] for i in positions}, cost_per_side=stress * 0.006)
    legs = positions.get("SOL/BTC", [0.0] * len(gross))
    short = [max(0.0, -(b - p)) for b, p in zip(positions["BTC"], legs)]
    carry = [stress * 0.0002 * (s + max(0.0, s - p)) for s, p in zip(short, [0.0, *short[:-1]])]
    return [g - c for g, c in zip(gross, carry)]


def _b4_sol_own_engagement(inputs: subjects._B4Inputs) -> dict:
    close, arm_b, n = inputs.close, inputs.arm_b, len(inputs.close)
    short = [max(0.0, -(b - p)) for b, p in zip(arm_b["BTC"], arm_b["SOL/BTC"])]
    differ = per_year_positions_differ(inputs.arm_a | {"SOL/BTC": [0.0] * n}, arm_b, close)
    return {
        "ratio_first_weight": inputs.first_weight,
        "primary_returns": n - inputs.first_weight["SOL/BTC"],
        "unseen_returns": sum(t > _B4_SOL_SEEN_TO for t in close),
        "ratio_held_per_year": {"SOL/BTC": per_year_counts([p != 0 for p in arm_b["SOL/BTC"]], close)},
        "stamps_positions_differ": sum(differ.values()),
        "positions_differ_per_year": differ,
        "turnover_b": book_turnover(arm_b),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "shortfall_stamps_per_year": per_year_counts([s > 0 for s in short], close),
        "shortfall_mean_per_year": per_year_means(short, close),
        "shortfall_max": max(short),
        "carry_per_year": per_year_sums([0.0002 * (s + max(0.0, s - p)) for s, p in zip(short, [0.0, *short[:-1]])], close),
        "limit_engaged_per_year": {limit: per_year_counts(flags, close) for limit, flags in inputs.engaged_b.items()},
        "arm_a_limit_engaged": {limit: sum(flags) for limit, flags in inputs.engaged_a.items()},
    }


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_trial_reads_each_metric_from_its_own_call(monkeypatch, name):
    inputs = _b4_sol_built_inputs()
    n, close, start = len(inputs.close), inputs.close, inputs.first_weight["SOL/BTC"]
    unseen = next(k for k, t in enumerate(close) if t > _B4_SOL_SEEN_TO)
    net_a, net_b = (_b4_sol_own_net(inputs, book, 1.0) for book in (inputs.arm_a, inputs.arm_b))
    net_a_x15, net_b_x15 = (_b4_sol_own_net(inputs, book, 1.5) for book in (inputs.arm_a, inputs.arm_b))
    # Arm B is short of BTC at some stamps, so the carry moves its net.
    assert net_b != net_of_cost(inputs.arm_b, {i: inputs.returns[i] for i in inputs.arm_b}, cost_per_side=0.006)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b4_sol_metrics(inputs, n_trials=2)

    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    common = {"n_trials": 2, "var_trials": 0.0, "benchmark_net_returns": bench, "decisive_start": 1380, "n_resamples": 2000}
    common |= {"benchmark_slices": calendar_year_slices(bench, inputs.h4_ts)}
    arm_b_bar = {
        "book_net_returns": net_b,
        "cost_stressed_returns": net_b_x15,
        "regime_slices": calendar_year_slices(net_b, inputs.h4_ts),
    }
    assert [arguments for arguments, _ in bars] == [
        common
        | {
            "book_net_returns": net_a,
            "cost_stressed_returns": net_a_x15,
            "regime_slices": calendar_year_slices(net_a, inputs.h4_ts),
            "mean_block": 30,
            "seed": 42,
        },
        *(common | arm_b_bar | {"mean_block": block, "seed": seed} for block, seed in _B2_GRID),
    ]
    reads = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    assert [arguments for arguments, _ in heads] == [
        reads | {"book_net_of_cost": net_b, "benchmark_net_of_cost": net_a},
        reads | {"book_net_of_cost": net_b[start:], "benchmark_net_of_cost": net_a[start:]},
        reads | {"book_net_of_cost": net_b[unseen:], "benchmark_net_of_cost": net_a[unseen:]},
    ]
    bar_a, headline = bars[0][1], bars[1][1]
    full, primary, after = (result for _, result in heads)
    assert metrics == {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=2190),
        "ann_sharpe_noc_decisive": sharpe(net_b[1380:], periods_per_year=2190),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": headline["dsr_pass"],
        "spa_pass": headline["spa_pass"],
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": headline["cost_stress_pass"],
        "worst_slice_relative_pass": headline["worst_slice_pass"],
        "passes": headline["passes"],
        "decisive_start": 1380,
        "n_resamples": 2000,
        "arm_a_passes": bar_a["passes"],
        **{f"spa_p_decisive_b{block}_s{seed}": bars[1 + j][1]["spa_p_value"] for j, (block, seed) in enumerate(_B2_GRID)},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_primary": primary["mean_outperformance"],
        "head_to_head_spa_p_primary": primary["spa_p_value"],
        "head_to_head_mean_outperf_unseen": after["mean_outperformance"],
        "head_to_head_spa_p_unseen": after["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "turnover_a": book_turnover(inputs.arm_a),
        "turnover_a_per_year": per_year_turnover(inputs.arm_a, close),
        **_b4_sol_own_engagement(inputs),
    }
    assert (n - start, n - unseen) == (metrics["primary_returns"], metrics["unseen_returns"]) == (1_000, 143)


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_preflight_reads_arm_a_over_both_spans_and_the_engagement_and_costs_no_other_book(monkeypatch, name):
    inputs = _b4_sol_built_inputs()
    net_a = _b4_sol_own_net(inputs, inputs.arm_a, 1.0)
    seen = next(k for k, t in enumerate(inputs.close) if t > _B4_SOL_SEEN_TO)

    def refused(*args, **kwargs):
        raise AssertionError("the pre-flight read a head-to-head")

    monkeypatch.setattr(subjects, "net_of_cost_verdict", refused)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    costed = _recording(monkeypatch, "_b4_net", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b4_sol_preflight_metrics(inputs, n_trials=2)

    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    ((arguments, bar),) = bars
    assert costed and all(arguments["positions"] is inputs.arm_a for arguments, _ in costed)
    assert arguments["book_net_returns"] == net_a and arguments["n_trials"] == 2
    turnover_a = book_turnover(inputs.arm_a)
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / len(inputs.close) * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        "arm_a_ann_sharpe_noc_seen": sharpe(net_a[:seen], periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive_seen": sharpe(net_a[1380:seen], periods_per_year=2190),
        "arm_a_max_drawdown_seen": max_drawdown(net_a[:seen]),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        **_b4_sol_own_engagement(inputs),
    }


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
def test_the_b4_sol_trial_refuses_fewer_than_2_returns_from_the_first_weight_or_after_the_last_close_read_before_any_bar(
    monkeypatch, name
):
    built = _b4_sol_built_inputs()
    n = len(built.close)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    with pytest.raises(ValidationError) as from_first_weight:
        subjects._b4_sol_metrics(built._replace(first_weight={"SOL/BTC": n - 1}), n_trials=2)
    with pytest.raises(ValidationError) as unseen:
        subjects._b4_sol_metrics(_b4_sol_built_inputs(1_458), n_trials=2)

    assert (
        str(from_first_weight.value)
        == "1 of its return indices follow SOL/BTC's first weight, and the head-to-head from it needs 2"
    )
    assert str(unseen.value) == (
        "1 of its return indices close after 2026-03-31 20:00:00+00:00, and the head-to-head over them needs 2"
    )
    assert bars == [] and heads == []
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    admitted = [
        subjects._b4_sol_metrics(built._replace(first_weight={"SOL/BTC": n - 2}), n_trials=2)["primary_returns"],
        subjects._b4_sol_metrics(_b4_sol_built_inputs(1_459), n_trials=2)["unseen_returns"],
    ]
    assert admitted == [2, 2]


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling"])
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_the_b4_sol_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b4_sol_reads", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-191", "--family", "B4", "--n-trials", "1"]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials 1 is not 2, the count {name} declares and deflates at: pass --n-trials 2"
    )

    result = runner.invoke(
        app, ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-10", *flags]
    )

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.parametrize("name", ["b4-sol-noborrow-rolling", "b4-sol-noborrow-rolling-preflight"])
@pytest.mark.parametrize("spoil", [_no_close_column, _not_parquet], ids=["no-close-column", "not-parquet"])
def test_a_b4_sol_subject_refuses_a_sol_btc_file_it_cannot_read_naming_it(tmp_path, monkeypatch, name, spoil):
    root = _b4_sol_dataset(tmp_path)
    spoil(root / "ohlc-test" / "SOL/BTC/240.parquet")
    _anchor(monkeypatch, root)
    books = _recording(monkeypatch, "_b4_sol_inputs", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "ohlc-test/SOL/BTC/240.parquet: " in result.output and books == []
```

  - `_RULED_FIXTURES` gains `"b4-sol-noborrow-rolling": _b4_sol_dataset,` after `"b4-ratio-legs": _b4_dataset,`; `_DECLARED_COUNT` gains `"b4-sol-noborrow-rolling": "_B4_SOL_N_TRIALS",` after `"b4-ratio-legs": "_B4_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b4-sol-noborrow-rolling": ("B4", 2),` after `"b4-ratio-legs": ("B4", 1),`; `_CONTRACT_DATASETS` gains, after its `"b4-leg-reading"` entry:

```python
    "b4-sol-noborrow-rolling": lambda tmp_path, subject: (_b4_sol_dataset(tmp_path), _B4_SOL_START),
    "b4-sol-noborrow-rolling-preflight": lambda tmp_path, subject: (_b4_sol_dataset(tmp_path), _B4_SOL_START),
```

  **Author's call** — each half on the fixture that moves it, every case but the shared rows in seconds, so each is a probe's target: the declaration, its counts of keys typed as record 58's and their changes; the rule row by row on `_B4_SOL_ADOPTING`, whose full-window and unseen-months pairs stand against the verdict; the reads on a frozen set, `_b4_dataset`, whose ETH/BTC file the reads must leave unread, and on a rolling set, `_b4_sol_rolling_set` — a hand-written chain of the twelve pairs, a 15-minute base from 2025-12-01 and three tape days with a hole on BTC/EUR and SOL/BTC — each read held to a second reader's own `read_rolling` frames, the holes it lists and its block; the books on `_b4_leg_short_reads`, whose BTC SOL/BTC outweighs at some stamps, every field of `_b4_sol_inputs` held to `_b4_own_books`' arm A and returns and `_b4_own_leg_books`' SOL/BTC no_borrow book, the tests' own builds, never the subject's halves, and the bit-identity read off the two ensembles `_b4_ensemble` returns; the metrics and the pre-flight's on `_b4_sol_built_inputs`, books made by hand over 1,600 return indices whose closes cross 2026-03-31 20:00 at index 1,457, arm B short of BTC and each limit engaged at a stamp of its own, under argument-derived stand-ins for the bar, the head-to-head and the benchmark, every call's arguments and every key held to `_b4_sol_own_net` and `_b4_sol_own_engagement`; the two refusals each bound from both sides; the count and the plain eval refused before any read; a SOL/BTC file the build cannot read named. Every new function is parametrised by the subject's name, so `tests/retired_subjects.py`'s hook marks each case `retired` once Task 5 retires the two names. The shared rows — the contract, tracked-spec, shared-defaults and deflation rows, which `_RULED_FIXTURES`, `_DECLARED_COUNT` and `_CONTRACT_DATASETS` reach — run both subjects end to end on `_b4_sol_dataset`, 1,980 bars from 2025-05-15, whose 2025 closes run past the frozen benchmark's 1,200-bar gate, the worst-slice leg's one non-stub year, and 54 of whose return indices close after the cut; `_b4_dataset`, ending in 2021, would refuse the trial's build at the cut.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00146 && uv run pytest tests/test_research_command.py -k "b4_sol or declares_the_metric_keys or ruled_subjects_declare" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt`: collection completes and every selected case fails at its call — on a key `SUBJECTS` lacks, a name `subjects` lacks or a subject the CLI does not know (measured on the base module: `26 failed, 832 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — after `_B4_LEG_KEYS`' closing `)` and before `SUBJECTS: dict[str, Subject] = {`, two blank lines on each side:

```python
# docs/specs/00146 D2-D9: B4's trial 2, SOL/BTC alone beside the ten EUR assets in the adopted A2-4h ensemble, held each close
# to the book's own BTC, on the rolling set as of a day: trial 58's books, costing, limits, bar and rule.
_B4_SOL = "SOL/BTC"
_B4_SOL_N_TRIALS = 2  # docs/specs/00146 D8: B4's true count with this trial, fixed by the spec's hash; another is a new subject
_B4_SOL_SEEN_TO = datetime(2026, 3, 31, 20, tzinfo=UTC)  # docs/specs/00146 D8: the last close reading 6 read


def _b4_sol_reads(
    subject: str,
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> _B4Reads:
    """The union, the window's refusals and SOL/BTC's closes on its stamps, the pair read as the union is — a frozen set
    file by file, the rolling set as of a day — and no compute."""
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
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
    try:
        if as_of is None:
            frame = reader.read_series(dataset, f"{_B4_SOL}/240.parquet", window=window)
        else:
            frame = reader.read_rolling(dataset, _B4_SOL, 240, as_of, window=window, accept_holes=accept_holes)
        closes = dict(zip(frame["ts"].to_list(), frame["close"].to_list(), strict=True))
    except pl.exceptions.PolarsError as exc:
        where = f"{dataset}/{_B4_SOL}/240.parquet" if as_of is None else f"{dataset} {_B4_SOL} at 240 minutes as of {as_of}"
        raise SubjectError(f"{where}: {exc}") from exc
    return _B4Reads(h4_ts, h4_prices, {_B4_SOL: [closes.get(t) for t in h4_ts]})


def _b4_sol_inputs(reads: _B4Reads) -> _B4Inputs:
    """Arm A and arm B in trial 58's shape, arm B — the ten EUR assets and SOL/BTC, the leg held to the book's own BTC — its
    own borrow-free book, so both `arm_b` and `no_borrow`; positions, and no return of a book."""
    h4_ts, h4_prices, ratios = reads
    fed = _ffill_btc(h4_prices)
    priced = fed | ratios
    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))
    arm_b, engaged_b = _b4_limited(borrow_unavailable(_b4_ensemble(priced), _B4_LEGS, "BTC"))
    weights = _inverse_vol_weights(priced, lookback=_B2_LOOKBACK)
    first_weight = {_B4_SOL: next((k for k, w in enumerate(weights) if _B4_SOL in w), len(weights))}
    returns = {a: _asset_returns(fed[a]) for a in h4_prices} | {_B4_SOL: ratio_eur_returns(ratios[_B4_SOL], fed["BTC"])}
    return _B4Inputs(h4_ts, h4_prices, close_grid(h4_ts), returns, first_weight, arm_a, arm_b, arm_b, engaged_a, engaged_b)


def _b4_sol_unseen(close: list[datetime]) -> int:
    """The first return index whose close is past the last one reading 6 read, the length when none is."""
    return next((k for k, t in enumerate(close) if t > _B4_SOL_SEEN_TO), len(close))


def _b4_sol_engagement(inputs: _B4Inputs) -> dict:
    close, arm_b = inputs.close, inputs.arm_b
    shortfall = _b4_shortfall(arm_b)
    differ = per_year_positions_differ(inputs.arm_a | {_B4_SOL: [0.0] * len(close)}, arm_b, close)
    return {
        "ratio_first_weight": inputs.first_weight,
        "primary_returns": len(close) - inputs.first_weight[_B4_SOL],
        "unseen_returns": len(close) - _b4_sol_unseen(close),
        "ratio_held_per_year": {_B4_SOL: per_year_counts([p != 0 for p in arm_b[_B4_SOL]], close)},
        "stamps_positions_differ": sum(differ.values()),
        "positions_differ_per_year": differ,
        "turnover_b": book_turnover(arm_b),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "shortfall_stamps_per_year": per_year_counts([s > 0 for s in shortfall], close),
        "shortfall_mean_per_year": per_year_means(shortfall, close),
        "shortfall_max": max(shortfall),
        "carry_per_year": per_year_sums(shortfall_carry(shortfall, rate=_B4_CARRY_RATE), close),
        "limit_engaged_per_year": {name: per_year_counts(flags, close) for name, flags in inputs.engaged_b.items()},
        "arm_a_limit_engaged": {name: sum(flags) for name, flags in inputs.engaged_a.items()},
    }


def _b4_sol_metrics(inputs: _B4Inputs, *, n_trials: int) -> dict:
    close = inputs.close
    start, unseen = inputs.first_weight[_B4_SOL], _b4_sol_unseen(close)
    if len(close) - start < 2:
        raise ValidationError(
            f"{len(close) - start} of its return indices follow SOL/BTC's first weight, and the head-to-head from it needs 2"
        )
    if len(close) - unseen < 2:
        raise ValidationError(
            f"{len(close) - unseen} of its return indices close after {_B4_SOL_SEEN_TO}, and the head-to-head over them needs 2"
        )
    net_b = _b4_net(inputs.arm_b, inputs.returns, stress=1.0)
    net_b_x15 = _b4_net(inputs.arm_b, inputs.returns, stress=1.5)
    bar_a, net_a, bench = _b4_arm_a_bar(inputs, n_trials=n_trials)
    slices_b, slices_bench = calendar_year_slices(net_b, inputs.h4_ts), calendar_year_slices(bench, inputs.h4_ts)
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
    for label, first in (("full", 0), ("primary", start), ("unseen", unseen)):
        verdict = net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
        head_to_head[f"head_to_head_mean_outperf_{label}"] = verdict["mean_outperformance"]
        head_to_head[f"head_to_head_spa_p_{label}"] = verdict["spa_p_value"]
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
        "arm_a_passes": int(bar_a["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": result["spa_p_value"] for (block, seed), result in grid.items()},
        **head_to_head,
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "turnover_a": book_turnover(inputs.arm_a),
        "turnover_a_per_year": per_year_turnover(inputs.arm_a, close),
        **_b4_sol_engagement(inputs),
    }


def _b4_sol_preflight_metrics(inputs: _B4Inputs, *, n_trials: int) -> dict:
    """Arm A's anchors and bar, its figures over the closes reading 6 read, and the engagement: no return of arm B."""
    bar, net_a, bench = _b4_arm_a_bar(inputs, n_trials=n_trials)
    seen = _b4_sol_unseen(inputs.close)
    turnover_a = book_turnover(inputs.arm_a)
    return {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / len(inputs.close) * _B2_COST_PER_SIDE * PPY_4H,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_seen": sharpe(net_a[:seen], periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive_seen": sharpe(net_a[_DECISIVE_START:seen], periods_per_year=PPY_4H),
        "arm_a_max_drawdown_seen": max_drawdown(net_a[:seen]),
        **{key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)},
        **_b4_sol_engagement(inputs),
    }


def _b4_sol_build(
    subject: str,
    compute: Callable[..., dict],
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    try:
        reads = _b4_sol_reads(subject, reader, dataset, window, as_of, accept_holes)
        return compute(_b4_sol_inputs(reads), n_trials=_B4_SOL_N_TRIALS)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, RiskError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b4_sol_noborrow_rolling(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b4_sol_build("b4-sol-noborrow-rolling", _b4_sol_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b4_sol_noborrow_rolling_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b4_sol_build(
        "b4-sol-noborrow-rolling-preflight", _b4_sol_preflight_metrics, reader, dataset, window, as_of, accept_holes
    )


# docs/specs/00146 D9's keys: record 58's, with no twin, the unseen months' head-to-head, their count and the shortfall's
# largest value added.
_B4_SOL_ENGAGEMENT_KEYS = _B4_ENGAGEMENT_KEYS | {"unseen_returns", "shortfall_max"}
_B4_SOL_METRIC_KEYS = (
    (
        _B4_METRIC_KEYS
        - {"no_borrow_head_to_head_mean_outperf_primary", "no_borrow_head_to_head_spa_p_primary", "no_borrow_ann_sharpe_noc"}
    )
    | _B4_SOL_ENGAGEMENT_KEYS
    | {"head_to_head_mean_outperf_unseen", "head_to_head_spa_p_unseen"}
)
_B4_SOL_PREFLIGHT_KEYS = (
    _B4_PREFLIGHT_KEYS
    | _B4_SOL_ENGAGEMENT_KEYS
    | {"arm_a_ann_sharpe_noc_seen", "arm_a_ann_sharpe_noc_decisive_seen", "arm_a_max_drawdown_seen"}
)
```

  and `SUBJECTS` gains, after its `"b4-leg-reading"` entry and before its closing `}`:

```python
    "b4-sol-noborrow-rolling": Subject(
        "b4-sol-noborrow-rolling",
        (240,),
        _ASSETS,
        _build_b4_sol_noborrow_rolling,
        spec="docs/specs/00146-b4-sol-noborrow-rolling-design.md",
        metric_keys=_B4_SOL_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b4_ratio_legs_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or SOL/BTC holds no position at any stamp; no "
            "verdict, the trial unspent"
        ),
        family="B4",
        n_trials=_B4_SOL_N_TRIALS,
    ),
    "b4-sol-noborrow-rolling-preflight": Subject(
        "b4-sol-noborrow-rolling-preflight",
        (240,),
        _ASSETS,
        _build_b4_sol_noborrow_rolling_preflight,
        spec="docs/specs/00146-b4-sol-noborrow-rolling-design.md",
        metric_keys=_B4_SOL_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` ) or `b4-leg-reading` ( `` becomes `` ), `b4-leg-reading` ( ``, and the row's closing `` its two ratio pairs among them; it has no rule, so its run is kept with `--reading`). | `` becomes:

```markdown
its two ratio pairs among them; it has no rule, so its run is kept with `--reading`), `b4-sol-noborrow-rolling` (the A2 4h ensemble against the same three arms run on eleven instruments, the ten EUR assets and the SOL/BTC ratio pair, long-only, the SOL/BTC position scaled at each 4h close to the book's own BTC so that the pair borrows none; the 4h series of `--dataset` — `ohlc-rolling` with `--as-of`, or a frozen set — the SOL/BTC pair among them, over a history that runs past 2026-03-31) or `b4-sol-noborrow-rolling-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar, the same figures over the closes to 2026-03-31, and the SOL/BTC pair's positions, the BTC it would borrow and the limits it engages, with no return of the eleven-instrument book; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the shared rows measured at 10 s or more on the authoring tree (call time: the shared-defaults rows 48.12 s and 43.08 s, the evaluate rows 24.33 s and 21.06 s, the deflation row 20.76 s):

```text
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b4-sol-noborrow-rolling]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-sol-noborrow-rolling-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-sol-noborrow-rolling-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b4-sol-noborrow-rolling-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b4-sol-noborrow-rolling]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, measured `26 passed, 850 deselected` (about 6 s); then the shared rows, `mkdir -p .tmp/plan-00146 && uv run pytest tests/test_research_command.py -k "b4-sol-noborrow-rolling and not b4_sol" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt`, one plain blocking call, `timeout` 600000 ms (measured `19 passed, 857 deselected in 160.27s`, every row but the five step 5 lists under 1 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' list over the four paths in its four parts (measured on the authoring tree: `468 passed, 408 deselected in 203.20s`, `227 passed, 649 deselected in 312.71s`, `71 passed, 805 deselected in 89.04s`; the other thirty-eight direct readers `4116 passed, 66 deselected in 116.56s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the authoring tree, 60 of 60); the metric-keys lines, the ruled-subjects literal and the contract, shared-defaults, deflation and tracked-spec rows are new rows of existing tests, not new guards, and are not probed:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/^_B4_SOL_N_TRIALS = 2\b/_B4_SOL_N_TRIALS = 3/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/"b4-sol-noborrow-rolling-preflight": Subject(/,/^    ),/s/metric_keys=_B4_SOL_PREFLIGHT_KEYS,/metric_keys=_B4_SOL_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/"b4-sol-noborrow-rolling": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/"b4-sol-noborrow-rolling": Subject(/,/^    ),/s/00146-b4-sol-noborrow-rolling-design/00145-b4-leg-reading-design/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/"b4-sol-noborrow-rolling": Subject(/,/^    ),/s/verdict=_b4_ratio_legs_verdict,/verdict=_b2_overlay_verdict,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/^_B4_SOL_SEEN_TO = datetime(2026, 3, 31, 20, /_B4_SOL_SEEN_TO = datetime(2026, 3, 31, 16, /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/^_B4_SOL_ENGAGEMENT_KEYS = _B4_ENGAGEMENT_KEYS | {"unseen_returns", "shortfall_max"}/_B4_SOL_ENGAGEMENT_KEYS = _B4_ENGAGEMENT_KEYS | {"unseen_returns"}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/^    | {"head_to_head_mean_outperf_unseen", "head_to_head_spa_p_unseen"}/    | {"head_to_head_mean_outperf_unseen"}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/^    | {"arm_a_ann_sharpe_noc_seen", "arm_a_ann_sharpe_noc_decisive_seen", "arm_a_max_drawdown_seen"}/    | {"arm_a_ann_sharpe_noc_seen", "arm_a_max_drawdown_seen"}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_trial_58s_rule_and_a_count[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/"adopt" if m\["head_to_head_spa_p_primary"\] < 0\.05 else "park"/"park"/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[outperforms-significantly-from-the-first-weight-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held/if not any(n for held/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-a-fails-its-bar-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held in m\["ratio_held_per_year"\]\.values() for n in held\.values()):/if not m["arm_a_passes"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[sol-btc-never-held-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held/if not any(n for held/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-a-read-before-passes-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held in m\["ratio_held_per_year"\]\.values() for n in held\.values()):/if not m["arm_a_passes"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[holding-read-before-passes-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/    if not m\["passes"\]:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-b-fails-its-bar-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/m\["head_to_head_spa_p_primary"\] < 0\.05/m["head_to_head_spa_p_primary"] <= 0.05/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[p-at-exactly-0.05-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/"adopt" if m\["head_to_head_spa_p_primary"\] < 0\.05 else "park"/"adopt"/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[p-0.2-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/    if m\["head_to_head_mean_outperf_primary"\] > 0:$/    if m["head_to_head_mean_outperf_primary"] >= 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-at-exactly-0-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/    if m\["head_to_head_mean_outperf_primary"\] > 0:$/    if m["head_to_head_mean_outperf_unseen"] > 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-negative-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation 's/    return _B4Reads(h4_ts, h4_prices, {_B4_SOL: \[closes\.get(t) for t in h4_ts\]})/    return _B4Reads(h4_ts, h4_prices, {_B4_SOL: [*closes.values()][: len(h4_ts)]})/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_reads_map_sol_btcs_closes_onto_a_frozen_union_and_read_no_other_pair[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation 's/            frame = reader\.read_series(dataset, f"{_B4_SOL}\/240\.parquet", window=window)/            frame = reader.read_series(dataset, "ETH\/BTC\/240.parquet", window=window)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_reads_map_sol_btcs_closes_onto_a_frozen_union_and_read_no_other_pair[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation '/^def _b4_sol_reads(/,/^def /s/_capturing_union(reader, dataset, 240, window, as_of, accept_holes)/_capturing_union(reader, dataset, 240, window, None, accept_holes)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_reads_read_the_rolling_set_as_of_the_day_across_its_holes_and_no_other_pair[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation '/^def _b4_sol_reads(/,/^def /s/_capturing_union(reader, dataset, 240, window, as_of, accept_holes)/_capturing_union(reader, dataset, 240, window, as_of, False)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_reads_read_the_rolling_set_as_of_the_day_across_its_holes_and_no_other_pair[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation 's/            frame = reader\.read_rolling(dataset, _B4_SOL, 240, as_of, window=window, accept_holes=accept_holes)/            frame = reader.read_rolling(dataset, _B4_SOL, 240, as_of, window=window, accept_holes=False)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_reads_read_the_rolling_set_as_of_the_day_across_its_holes_and_no_other_pair[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation '/^def _b4_sol_reads(/,/^def /s/        if as_of is None:/        if True:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_reads_read_the_rolling_set_as_of_the_day_across_its_holes_and_no_other_pair[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation '/^def _b4_sol_inputs(/,/^def /s/    weights = _inverse_vol_weights(priced, /    weights = _inverse_vol_weights(fed, /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_arms_agree_bit_for_bit_until_sol_btc_takes_weight[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation '/^def _b4_sol_inputs(/,/^def /s/    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))/    arm_a, engaged_a = _b4_limited(_b4_ensemble(priced))/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_arms_agree_bit_for_bit_until_sol_btc_takes_weight[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation 's/    arm_b, engaged_b = _b4_limited(borrow_unavailable(_b4_ensemble(priced), _B4_LEGS, "BTC"))/    arm_b, engaged_b = _b4_limited(_b4_ensemble(priced))/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_inputs_hold_sol_btc_to_the_books_own_btc_and_cost_it_on_its_own_return[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation '/^def _b4_sol_inputs(/,/^def /s/    fed = _ffill_btc(h4_prices)/    fed = dict(h4_prices)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_inputs_hold_sol_btc_to_the_books_own_btc_and_cost_it_on_its_own_return[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation 's/{_B4_SOL: ratio_eur_returns(ratios\[_B4_SOL\], fed\["BTC"\])}/{_B4_SOL: ratio_eur_returns(ratios[_B4_SOL], h4_prices["BTC"])}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_inputs_hold_sol_btc_to_the_books_own_btc_and_cost_it_on_its_own_return[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation '/^def _b4_sol_inputs(/,/^def /s/    returns = {a: _asset_returns(fed\[a\]) for a in h4_prices}/    returns = {a: _asset_returns(h4_prices[a]) for a in h4_prices}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_inputs_hold_sol_btc_to_the_books_own_btc_and_cost_it_on_its_own_return[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation 's/first_weight = {_B4_SOL: next((k for k, w in enumerate(weights) if _B4_SOL in w), len(weights))}/first_weight = {_B4_SOL: next((k for k, w in enumerate(weights) if w), len(weights))}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_inputs_hold_sol_btc_to_the_books_own_btc_and_cost_it_on_its_own_return[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_inputs(/def _b4_sol_inputs_gone(/' --mutation 's/close_grid(h4_ts), returns, first_weight, arm_a, arm_b, arm_b, engaged_a, engaged_b)/close_grid(h4_ts), returns, first_weight, arm_a, arm_b, dict(arm_b), engaged_a, engaged_b)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_inputs_hold_sol_btc_to_the_books_own_btc_and_cost_it_on_its_own_return[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation 's/    for label, first in (("full", 0), ("primary", start), ("unseen", unseen)):/    for label, first in (("full", 0), ("primary", start), ("unseen", start)):/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_unseen(/def _b4_sol_unseen_gone(/' --mutation 's/    return next((k for k, t in enumerate(close) if t > _B4_SOL_SEEN_TO), len(close))/    return next((k for k, t in enumerate(close) if t >= _B4_SOL_SEEN_TO), len(close))/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation '/^def _b4_sol_metrics(/,/^def /s/    net_b_x15 = _b4_net(inputs\.arm_b, inputs\.returns, stress=1\.5)/    net_b_x15 = _b4_net(inputs.arm_b, inputs.returns, stress=1.0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation '/^def _b4_sol_metrics(/,/^def /s/"arm_a_passes": int(bar_a\["passes"\]),/"arm_a_passes": int(headline["passes"]),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation '/^def _b4_sol_metrics(/,/^def /s/"spa_p_full": headline\["spa_p_value_full"\],/"spa_p_full": headline["spa_p_value"],/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation '/^def _b4_sol_metrics(/,/^def /s/    bar_a, net_a, bench = _b4_arm_a_bar(inputs, n_trials=n_trials)/    bar_a, net_a, bench = _b4_arm_a_bar(inputs, n_trials=1)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation 's/"unseen_returns": len(close) - _b4_sol_unseen(close),/"unseen_returns": len(close) - _b4_sol_unseen(close) - 1,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation 's/"primary_returns": len(close) - inputs\.first_weight\[_B4_SOL\],/"primary_returns": len(close) - inputs.first_weight[_B4_SOL] - 1,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation 's/"ratio_held_per_year": {_B4_SOL: per_year_counts(\[p != 0 for p in arm_b\[_B4_SOL\]\], close)},/"ratio_held_per_year": {_B4_SOL: per_year_counts([p != 0 for p in arm_b["BTC"]], close)},/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation 's/    differ = per_year_positions_differ(inputs\.arm_a | {_B4_SOL: \[0\.0\] \* len(close)}, arm_b, close)/    differ = per_year_positions_differ(arm_b, arm_b, close)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation '/^def _b4_sol_engagement(/,/^def /s/    shortfall = _b4_shortfall(arm_b)/    shortfall = _b4_shortfall(inputs.arm_a)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation 's/"shortfall_max": max(shortfall),/"shortfall_max": min(shortfall),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation '/^def _b4_sol_engagement(/,/^def /s/shortfall_carry(shortfall, rate=_B4_CARRY_RATE)/shortfall_carry(shortfall, rate=2 * _B4_CARRY_RATE)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_engagement(/def _b4_sol_engagement_gone(/' --mutation '/^def _b4_sol_engagement(/,/^def /s/for name, flags in inputs\.engaged_b\.items()},/for name, flags in inputs.engaged_a.items()},/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_reads_each_metric_from_its_own_call[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_preflight_metrics(/def _b4_sol_preflight_metrics_gone(/' --mutation 's/"arm_a_ann_sharpe_noc_seen": sharpe(net_a\[:seen\], periods_per_year=PPY_4H),/"arm_a_ann_sharpe_noc_seen": sharpe(net_a, periods_per_year=PPY_4H),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_preflight_reads_arm_a_over_both_spans_and_the_engagement_and_costs_no_other_book[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_preflight_metrics(/def _b4_sol_preflight_metrics_gone(/' --mutation 's/"arm_a_ann_sharpe_noc_decisive_seen": sharpe(net_a\[_DECISIVE_START:seen\], periods_per_year=PPY_4H),/"arm_a_ann_sharpe_noc_decisive_seen": sharpe(net_a[_DECISIVE_START:], periods_per_year=PPY_4H),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_preflight_reads_arm_a_over_both_spans_and_the_engagement_and_costs_no_other_book[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_preflight_metrics(/def _b4_sol_preflight_metrics_gone(/' --mutation 's/"arm_a_max_drawdown_seen": max_drawdown(net_a\[:seen\]),/"arm_a_max_drawdown_seen": max_drawdown(net_a[seen:]),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_preflight_reads_arm_a_over_both_spans_and_the_engagement_and_costs_no_other_book[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_preflight_metrics(/def _b4_sol_preflight_metrics_gone(/' --mutation '/^def _b4_sol_preflight_metrics(/,/^def /s/    bar, net_a, bench = _b4_arm_a_bar(inputs, n_trials=n_trials)/    bar, net_a, bench = _b4_arm_a_bar(inputs, n_trials=1)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_preflight_reads_arm_a_over_both_spans_and_the_engagement_and_costs_no_other_book[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation '/^def _b4_sol_metrics(/,/^def /s/    if len(close) - start < 2:/    if len(close) - start < 1:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_refuses_fewer_than_2_returns_from_the_first_weight_or_after_the_last_close_read_before_any_bar[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation '/^def _b4_sol_metrics(/,/^def /s/    if len(close) - start < 2:/    if len(close) - start < 3:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_refuses_fewer_than_2_returns_from_the_first_weight_or_after_the_last_close_read_before_any_bar[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation 's/    if len(close) - unseen < 2:/    if len(close) - unseen < 1:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_refuses_fewer_than_2_returns_from_the_first_weight_or_after_the_last_close_read_before_any_bar[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_metrics(/def _b4_sol_metrics_gone(/' --mutation 's/    if len(close) - unseen < 2:/    if len(close) - unseen < 3:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_refuses_fewer_than_2_returns_from_the_first_weight_or_after_the_last_close_read_before_any_bar[b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/"b4-sol-noborrow-rolling": Subject(/,/^    ),/s/verdict=_b4_ratio_legs_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation '/"b4-sol-noborrow-rolling": Subject(/,/^    ),/s/n_trials=_B4_SOL_N_TRIALS,/n_trials=1,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_sol_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation '/^def _b4_sol_reads(/,/^def /s/    except pl\.exceptions\.PolarsError as exc:/    except ZeroDivisionError as exc:/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_sol_subject_refuses_a_sol_btc_file_it_cannot_read_naming_it[no-close-column-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation '/^def _b4_sol_reads(/,/^def /s/    except pl\.exceptions\.PolarsError as exc:/    except ZeroDivisionError as exc:/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_sol_subject_refuses_a_sol_btc_file_it_cannot_read_naming_it[not-parquet-b4-sol-noborrow-rolling-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_sol_reads(/def _b4_sol_reads_gone(/' --mutation 's/        where = f"{dataset}\/{_B4_SOL}\/240\.parquet" if as_of is None else/        where = f"{dataset}\/{_B4_SOL}" if as_of is None else/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_sol_subject_refuses_a_sol_btc_file_it_cannot_read_naming_it[not-parquet-b4-sol-noborrow-rolling]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D2–D9 gives the new code. The declaration: the count, the pre-flight's keys, the seeds, the spec, the reused rule, the cut and each added key (rows 1–9). The rule, row by row, on the reused function (rows 10–19), the last reading the unseen months in place of the primary read. The reads: SOL/BTC's closes by stamp and its own file (rows 20–21); on the rolling set, the as-of and the holes reaching both reads and the pair read through the index (rows 22–25). The inputs: the leg's first weight off its book's own path and arm A on the ten assets (rows 26–27); the hold to the book's BTC, the BTC fill, the leg's EUR return on the filled BTC, the EUR legs' returns, the first weight for the leg itself and arm B in both fields (rows 28–33). The metrics: the unseen read from the cut, the cut strictly after the last close read, the stressed series, arm A's own `passes`, the full-window SPA p and the count reaching arm A's bar (rows 34–39); the engagement's unseen count, primary count, holding, differing stamps, shortfall book, largest shortfall, carry rate and engaged flags (rows 40–47). The pre-flight: each seen-span figure over its own span and the count reaching its bar (rows 48–51). Each refusal's bound from both sides (rows 52–55). The plain eval and the count (rows 56–57). The file refusal's catch on both subjects and its name (rows 58–60).
- [ ] **Step 9: Commit** — `feat(research): B4 trial 2's subjects — SOL/BTC alone on the A2 ensemble, held to the book's own BTC, and its pre-flight twin, read on the rolling set as of a day`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the data-gated basis test, the conventions entry before the hash, the reads (D7, D10)

**Files:** Create `tests/test_research_b4_sol_noborrow_rolling_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 1's `_b4_sol_reads`, `_b4_sol_inputs`, `_b4_sol_unseen` and `_b4_sol_engagement`, and `cli/research/subjects.py`'s `_b4_shortfall` and `_ASSETS`; `cli.alpha.b1.book_turnover`, `cli.alpha.b2`'s `per_year_positions_differ` and `per_year_turnover`, `cli.alpha.b4.per_year_counts`; `cli.registry.observed.ObservedReader`, `cli.registry.record.compute_hash` and `cli.research.command._DATA_ROOT`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance`'s `_trials` and `_readings`. Produces one test and the module names `AS_OF`, `BLOCK`, `VOUCHED`, `RETURN_INDICES`, `SEEN`, `TURNOVER_A` and `ENGAGEMENT`, which Task 3's check programs import. No test computes a return of a book.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, record 58's and reading 6's figures read off the committed record and reading:

```python
"""B4 trial 2's inputs half against spec 00146's measured basis: positions, the BTC shortfall, the limits and turnover, and
no return of a book; over the return indices the rolling set shares with ohlc-full, arm A against record 58's and arm B
against reading 6's SOL/BTC no_borrow cell."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import per_year_positions_differ, per_year_turnover
from cli.alpha.b4 import per_year_counts
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _readings, _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_YEARS = dict.fromkeys(map(str, range(2013, 2027)), 0)
# Copied from the spec's measured basis, never from a run.
AS_OF = "2026-10-10"
BLOCK = "c05629c70826656ca225857f6b5b682bfc00a737a0feff91f78b57cf70c93295"
VOUCHED = {"ohlc-rolling": "chained (as of 2026-10-10, line fcb62a79fab7)"}
RETURN_INDICES = 28_495
SEEN = 27_337
TURNOVER_A = 155.62922308759553
ENGAGEMENT = {
    "ratio_first_weight": {"SOL/BTC": 17_079},
    "primary_returns": 11_416,
    "unseen_returns": 1_158,
    "ratio_held_per_year": {"SOL/BTC": _YEARS | {"2021": 514, "2022": 566, "2023": 1_104, "2024": 981, "2025": 705, "2026": 750}},
    "stamps_positions_differ": 9_904,
    "positions_differ_per_year": _YEARS | {"2021": 891, "2022": 1_830, "2023": 2_058, "2024": 1_871, "2025": 1_832, "2026": 1_422},
    "turnover_b": 156.02775785139957,
    "shortfall_stamps_per_year": _YEARS | {"2021": 3, "2022": 14, "2023": 1, "2024": 14, "2025": 6, "2026": 19},
    "shortfall_max": 6.938893903907228e-18,
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
}


def trial_inputs():
    """The trial's inputs half over the rolling set as of `AS_OF`, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    reads = subjects._b4_sol_reads("b4-sol-noborrow-rolling", reader, "ohlc-rolling", None, AS_OF, False)
    return reader, subjects._b4_sol_inputs(reads)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-rolling/index/2026/10/10.json"),
    reason="the rolling set's line for 2026-10-10 is absent under data/",
)
def test_the_sol_noborrow_inputs_reproduce_the_measured_basis_record_58s_arm_a_and_reading_6s_cell():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    assert compute_hash(reader.block()) == BLOCK and reader.vouched_status() == VOUCHED and reader.holes() == {}
    close = inputs.close
    assert len(close) == RETURN_INDICES and subjects._b4_sol_unseen(close) == SEEN
    record, reading = _trials()[58]["metrics"], _readings()[6]["metrics"]
    seen_a, seen_b = ({i: v[:SEEN] for i, v in book.items()} for book in (inputs.arm_a, inputs.arm_b))
    assert book_turnover(seen_a) == record["turnover_a"]
    assert per_year_turnover(seen_a, close[:SEEN]) == record["turnover_a_per_year"]
    keys = ("turnover", "held_per_year", "shortfall_stamps_per_year", "positions_differ_per_year")
    cell = {key: reading[key]["SOL/BTC"]["no_borrow"] for key in keys}
    assert book_turnover(seen_b) == cell["turnover"]
    assert per_year_counts([p != 0 for p in seen_b["SOL/BTC"]], close[:SEEN]) == cell["held_per_year"]
    shortfall = [s > 0 for s in subjects._b4_shortfall(seen_b)]
    assert per_year_counts(shortfall, close[:SEEN]) == cell["shortfall_stamps_per_year"]
    flat = seen_a | {"SOL/BTC": [0.0] * SEEN}
    assert per_year_positions_differ(flat, seen_b, close[:SEEN]) == cell["positions_differ_per_year"]
    start = ENGAGEMENT["ratio_first_weight"]["SOL/BTC"]
    assert all(inputs.arm_b[a][:start] == inputs.arm_a[a][:start] for a in subjects._ASSETS)
    assert not any(inputs.arm_b["SOL/BTC"][:start]) and inputs.no_borrow is inputs.arm_b
    assert book_turnover(inputs.arm_a) == TURNOVER_A
    engagement = subjects._b4_sol_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert {year: round(v, 6) for year, v in engagement["carry_per_year"].items() if round(v, 6)} == {}
```

  **Author's call** — the case holds the subject's inputs half to the spec's programs, which built the books by their own expression, so the measured figures and the subject's code are two derivations that must agree; arm A over the 27,337 return indices the two sets share to record 58 by its turnover and its turnover per close year, and arm B over them to reading 6's SOL/BTC no_borrow cell by its turnover, holding, shortfall stamps and differing stamps per close year, the stored figures, never a second typing; the integer engagement, the turnovers and the largest shortfall exactly, as the programs printed them, and the carry rounding to nothing at six decimals.
- [ ] **Step 2: Run it** — with `data/ohlc-rolling` linked in this worktree: `mkdir -p .tmp/plan-00146 && uv run pytest tests/test_research_b4_sol_noborrow_rolling_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, a call of 168.93 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b4_sol_noborrow_rolling_basis.py::test_the_sol_noborrow_inputs_reproduce_the_measured_basis_record_58s_arm_a_and_reading_6s_cell
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b4_sol_noborrow_rolling_basis.py tests/slow-cases.txt`; the Global Constraints' list over the two paths (measured `18 passed, 1 deselected in 18.93s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00146 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt`; `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B4 trial 2's inputs half against the measured basis — the rolling block, SOL/BTC's first weight and holding, the shortfall's rounding, the limits, the turnover, the unseen months, record 58's arm A and reading 6's cell over the span they share`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_b4_sol_noborrow_rolling_basis.py::test_the_sol_noborrow_inputs_reproduce_the_measured_basis_record_58s_arm_a_and_reading_6s_cell`, the line `It reads data/ohlc-rolling: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5: The conventions entry, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, **Author's call** the trial's conventions, plan 00145's shape, so that they stand in the log before any return of arm B is read; no pick entry, the owner's pick being the `[iter-190] B4's next step after the leg reading` entry already there:

```markdown
[iter-191] B4 trial 2's conventions, pinned by spec 00146 before its hash (Decision: 1)
  The trial's details are fixed in the spec, reviewed, and frozen by its sha256, its record's `spec_hash`, before any return of arm B is read, or a net-of-cost series, head-to-head or bar leg of arm B computed, over the data; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00144 and 00145 fixed staying theirs. The pick is the owner's, the `[iter-190] B4's next step after the leg reading` entry above.
  1. **As the spec pins them, SOL/BTC alone held to the book's own BTC on the rolling set** — the owner's pick (D1); `ohlc-rolling` as of 2026-10-10, its head on this workstation's mirror, full history, no fetch, no hole in a pair it reads so no `--accept-holes`, the ten EUR assets' union and SOL/BTC's 4h pair read through its index, the subject reading a frozen set file by file as well, the spent holdout's window read under `[iter-176]` and never reported as holdout or out-of-sample evidence (D2); arm A the adopted ensemble, record 58's to the bit over the 27,337 return indices the two sets share, arm B its three A2 arms on eleven instruments with SOL/BTC scaled each bar to the book's own BTC and then §10's limits, arm A's to the bit until SOL/BTC takes basket weight at return index 17,079, its own borrow-free book in trial 58's inputs shape, no twin, trial 58's and reading 6's functions unchanged (D3); trial 58's costing, `_b4_net` at 0.006 a side, the shortfall float rounding, at most 6.94e-18, so no carry is owed, counted as the code computes it with its largest value recorded (D4); §10's limits as trial 58 wired them (D5); the months reading 6 never saw, the 1,158 return indices from 27,337, read beside the matrix and in no leg of it, fewer than 2 of them refusing the build (D6); the contamination stated in full — reading 6 read this cell on `ohlc-full` through 2026-03-31, 10,258 of the primary read's 11,416 return indices, at a primary mean outperformance of 3.827897287865115e-06/bar and SPA p 0.08495752123938032, so that span is no independent look; the trial the owner's pick, not the reading's criterion's; the DSR counting B4's true trials, records 58 and this one (D7); record 58's bar at count 2 and `var_trials` 0.0, the head-to-head from SOL/BTC's first weight deciding, trial 58's matrix through its own rule `_b4_ratio_legs_verdict`, no park variants (D8); the subjects `b4-sol-noborrow-rolling` and `b4-sol-noborrow-rolling-preflight`, the variant `B4-sol-noborrow-a2eq-rolling-v1`, 49 and 34 keys, record 58's with no twin and the unseen months' pair, their count and the shortfall's largest value added, the pre-flight's anchors arm A's figures over the span the sets share, record 58's to the last digit, the build in three halves (D9); no `--verdict`, notes naming only what is fixed before the run (D10); after a verdict, whatever it is, B4 closed on the owner's word and B3 next, an adopt recorded and never deployed, a stop the owner's (D11). Chosen.
  2. **The alternatives each weighed** — a fetch to a later head before the run, which moves the measured basis under the spec; a subject reading the rolling set alone, which the shared contract rows, read on a frozen fixture, could not evaluate; the carried SOL/BTC book as a twin, a second look at reading 6's other SOL/BTC cell the owner's pick did not name; the unseen months as a matrix leg, a second decider over 1,158 return indices; a rule of the trial's own, trial 58's five rows typed again; the pre-flight anchored at record 45's precision over the full window, which no record holds; the shortfall counted with a tolerance, a second definition of it; a count other than B4's true one; a close of B4 on a stop, which has no verdict for the owner's "then move on" to follow.
  Source: spec 00146 (D1–D11), its **Author's call**s and the calls it carries from the owner and specs 00144 and 00145; the owner's words quoted in the `[iter-190] B4's next step after the leg reading` entry above.
```

  staged alone, its gate `mkdir -p .tmp/plan-00146 && uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt` (measured in a scratch worktree over Tasks 1–2's tree, the entry appended, `50 passed`) and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-191] B4 trial 2's conventions, pinned by spec 00146 before its hash`. Neither of T0016's triggers moves: its B4 arm already reads ripe, and its B3 arm greps for `B4.s next step after trial 2 — closed`, which this header does not carry (measured: the check prints 0).
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–2 and the entry — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes or reads arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — through the code, a program or arithmetic over a stored figure — or runs either subject over the real data, or replays reading 6, before the spec's hash, and the data-gated case runs with `ohlc-rolling` linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 3 step 1 diffs from. Task 3 waits until the trio has closed with no open Critical or Important.

## Task 3 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D10)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 2 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00146-b4-sol-noborrow-rolling-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; trial 58's and reading 6's code path since reading 6's run — the spec's basis lists it from that run's commit to the branch's cut — `git log --oneline c4025751a36213d50274879992158f0970e7e00e..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version`, lists Task 1's commit and its fixes alone (measured at the base: nothing); any other commit is named, step 4 deciding whether it moved the inputs half or trial 58's computes.
- [ ] **Step 2: D10 (1), the spec hash** — `sha256sum docs/specs/00146-b4-sol-noborrow-rolling-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D10 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record or a reading another branch's merged PR carries — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0016's — then takes a delta read of the merge in place of re-running step 1: step 1's code-path log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 2 step 6's sentence with its "before the spec's hash" read "before Task 4's run, record 58's replay excepted", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the trial — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. A B4 record another branch landed raises `required_n("B4")` above 2, and the run is then refused before its fit (D8): the trial stops, T0016's. The check has two sites, this step and Task 4 step 1, and both take this path.
- [ ] **Step 4: D10 (3), the data test on the run's tree, with the subjects' two fixture rows and record 58's replay** — with `data/ohlc-rolling` and `data/ohlc-full` linked: `mkdir -p .tmp/plan-00146 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b4_sol_noborrow_rolling_basis.py 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-sol-noborrow-rolling-evaluates]' 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-sol-noborrow-rolling-preflight-evaluates]' 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-58]' -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt > .tmp/plan-00146/basis.out 2>&1`, one background call: `4 passed`, never a skip or an xfail — the fixture rows run the build end to end on the tree a fix of the reads may have changed, and record 58's replay rebuilds trial 58's stored figures through the costing, arm A bar and head-to-head code the trial's computes half shares with it (measured on the scratch tree, the first three `3 passed in 220.30s`, the replay `1 passed in 311.09s`); a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code, the replay's a moved computes half — T0016's, and the run waits. Reading 6's replay is not in this run (the hash rule).
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00146/preflight_check.py`, D10's (a)–(e) in order, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00146 D10's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b4_sol_noborrow_rolling_basis import BLOCK, ENGAGEMENT, TURNOVER_A, VOUCHED
from tests.test_trial_registry_provenance import _trials

out = Path(".tmp/plan-00146/b4-sol-noborrow-rolling-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
holes = [line for line in out.splitlines() if line.startswith("hole: ")]
print("block", compute_hash(block), run["vouched"], "holes", holes)
if compute_hash(block) != BLOCK:
    sys.exit("(a) the inputs' block differs from the spec's")
if run["vouched"] != VOUCHED or holes:
    sys.exit("(a) the set is not read as the spec reads it")
record = _trials()[58]["metrics"]
anchors = {
    "arm_a_ann_sharpe_noc_seen": record["arm_a_ann_sharpe_noc"],
    "arm_a_ann_sharpe_noc_decisive_seen": record["arm_a_ann_sharpe_noc_decisive"],
    "arm_a_max_drawdown_seen": record["arm_a_max_drawdown"],
    "turnover_a": TURNOVER_A,
}
off = {key: (m[key], value) for key, value in anchors.items() if m[key] != value}
if off:
    sys.exit(f"(b) arm A does not reproduce record 58's arm A over the span the sets share: {off}")
off = [key for key, value in ENGAGEMENT.items() if m[key] != value]
off += ["carry_per_year"] * bool({year: round(v, 6) for year, v in m["carry_per_year"].items() if round(v, 6)})
if off:
    sys.exit(f"(c) the engagement differs from the measured basis: {off}")
held = sum(m["ratio_held_per_year"]["SOL/BTC"].values())
print("held", held, "first weight", m["ratio_first_weight"], "primary", m["primary_returns"], "unseen", m["unseen_returns"], "turnover_b", m["turnover_b"])
if not held:
    sys.exit("(d) SOL/BTC holds no position: the dead knob")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00146/record_check.py`, the record's checks, its one argument the spec's sha256:

```python
"""Spec 00146 D9's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b4_sol_noborrow_rolling_basis import AS_OF, BLOCK, ENGAGEMENT

name, spec_hash = "b4-sol-noborrow-rolling", sys.argv[1]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00146/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00146/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block == BLOCK,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-rolling", "window": None, "as_of": AS_OF, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"])
    == ("B4", 2, "B4-sol-noborrow-a2eq-rolling-v1", "iter-191", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": {key: m[key] for key in ENGAGEMENT} == ENGAGEMENT
    and not {year: round(v, 6) for year, v in m["carry_per_year"].items() if round(v, 6)},
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `mkdir -p .tmp/plan-00146 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00146/preflight_check.py .tmp/plan-00146/record_check.py`. The pre-flight check was run on the authoring tree over a synthetic print carrying the real block, read by `_b4_sol_reads` with no compute, the basis's engagement and record 58's arm A figures: it printed the block, the holding, the first weight, the primary and unseen counts and the bar's flags and exited 0, and with `passes` 0 exited 1 on `(e) arm A fails its bar`.

## Task 4 (the controller's): trial 2 — its pre-flight, its run and its record (D8–D10)

`<H>` is Task 3 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 3 step 3 whole, its stop, its merge path and Task 3 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `mkdir -p .tmp/plan-00146 && uv run zcrypto research eval --subject b4-sol-noborrow-rolling-preflight --dataset ohlc-rolling --as-of 2026-10-10 > .tmp/plan-00146/b4-sol-noborrow-rolling-preflight.out 2>&1`, a plain eval of a subject with no rule — the inputs half and one bar, about three minutes (the spec's basis: the inputs half 168.93 s, one bar 11.85 s) — one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00146/preflight_check.py`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(e): D10's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0016's with its line; a refused build — exit 1 with no traceback, its output naming `b4-sol-noborrow-rolling-preflight over the full history: …` or the SOL/BTC pair — prints no metrics, keeps no reading, and is recorded in Task 5's T0016 findings with its line quoted, the trial unspent.
- [ ] **Step 3: On a stop, the reading** — `mkdir -p .tmp/plan-00146 && uv run zcrypto research eval --subject b4-sol-noborrow-rolling-preflight --dataset ohlc-rolling --as-of 2026-10-10 --reading --iteration iter-191 --spec-hash <H> --notes "B4 trial 2's pre-flight (spec 00146 D10): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00146/b4-sol-noborrow-rolling-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `mkdir -p .tmp/plan-00146 && uv run zcrypto research eval --subject b4-sol-noborrow-rolling --dataset ohlc-rolling --as-of 2026-10-10 --register --iteration iter-191 --family B4 --n-trials 2 --variant B4-sol-noborrow-a2eq-rolling-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00146/b4-sol-noborrow-rolling.out 2>&1`, about four and a half minutes (the spec's basis: the inputs half, seven bars and three head-to-heads, about 270 s), one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run, name only what is fixed before it: `subject b4-sol-noborrow-rolling over ohlc-rolling as of 2026-10-10, full history, no hole read; arm A the adopted equal-weight A2 4h ensemble on the ten EUR assets, arm B the same three arms on eleven instruments, the venue's SOL/BTC 4h pair beside them, long-only, A2's configuration unchanged, the SOL/BTC position scaled at each close to the book's own BTC/EUR position so the pair borrows none; the pair's EUR return its BTC-denominated gain converted at the bar's closing BTC/EUR; every instrument charged 0.006 per side on its own turnover, the BTC shortfall float rounding; the section 10 gross cap, net band and margin floor on per-base exposures, one factor per bar; the hypothesis: the eleven-instrument book has a higher mean net-of-cost return than the ten-asset ensemble from the first close SOL/BTC takes basket weight; n_trials 2, B4's true count, var_trials 0.0, the DSR leg binding; the head-to-head from return index 17079 (close 2021-07-26 00:00) decides, the full-window read beside it and the read from return index 27337 (close 2026-04-01 00:00), the months reading 6 never saw, in no matrix leg, the spent holdout's window inside them reported as no holdout or out-of-sample evidence; reading 6 read this cell on ohlc-full through 2026-03-31, 10258 of the primary read's 11416 return indices; pre-flight: block c05629c7..., arm A's figures over the 27337 return indices shared with ohlc-full record 58's, passes 1, SOL/BTC held at 4620 return indices, no limit engaged, turnover_b <its value>; no park variants, B4 closing after this verdict on the owner's word; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, a B4 record landed elsewhere, or bucket B spent — comes before the fit or after the print, naming each orphan, the count or the bucket's figure: no record, no reading; T0016 carries it (Task 5). A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b4-sol-noborrow-rolling"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build ends its attempt failed, counting 0, recorded in T0016 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0016's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00146/record_check.py <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 5 step 2). A failed check stops the task before step 6.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-191] Verdict — B4 trial 2 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B4 n=2)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D8's table (`sed -n '/^| Arm A.s bar and SOL\/BTC/,/^  Every quantity the matrix reads/p' docs/specs/00146-b4-sol-noborrow-rolling-design.md`), with `arm_a_passes`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary` unrounded, the full-window pair beside them; the unseen months' pair and `unseen_returns`, read in no leg, the spent holdout's window inside them named as no holdout or out-of-sample evidence; `n_trials` 2, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); `max_drawdown` beside `arm_a_max_drawdown`; the pre-flight's block, seen-span figures and `passes` from `.tmp/plan-00146/b4-sol-noborrow-rolling-preflight.out`; the engagement — `ratio_first_weight`, `primary_returns`, `ratio_held_per_year`'s total, `stamps_positions_differ`, `turnover_a` beside `turnover_b`, `shortfall_max` and the shortfall's stamps, `limit_engaged_per_year`'s totals; the contamination D7 states, reading 6's figures on the cell beside the primary pair; on an adopt D11's path in its order; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-189] Verdict — B4 trial 1 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b4-sol-noborrow-rolling": 2,` after `"b4-ratio-legs": 1,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B4 trial 2's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries its SOL/BTC leg adopts` (D11), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`. Then `git add` by path of `docs/reference/trial-registry.jsonl`, the record step 4's run appended, `docs/research/10.phase4-decisions.md`, `tests/test_trial_registry_provenance.py` and `tests/slow-cases.txt`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and `docs/open-topics/README.md`; the list over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, both sets linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-rolling /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter191/.tmp/plan-00146/probe/data/ohlc-rolling` and `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter191/.tmp/plan-00146/probe/data/ohlc-full` — the replay reads the rolling set and its skip gate the frozen one — each unlinked after the replay and the probe with `test -L <its absolute path> && unlink <its absolute path>` and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task; then the literal's probe, expected `KILLED` (its two seds dry-run on the authoring tree, each changing one line): `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_sol_noborrow_rolling(/def _build_b4_sol_noborrow_rolling_gone(/' --mutation 's/^_B4_SOL_N_TRIALS = 2\b/_B4_SOL_N_TRIALS = 3/' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit that index, with no `git add` after the setup, as `docs(research): B4 trial 2 registered — <verdict>, SOL/BTC alone held to the book's own BTC on the rolling set, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/ohlc-rolling, and its gate data/ohlc-full: re-run it with both sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b4-sol-noborrow-rolling-preflight` with outcome `null`, or `b4-sol-noborrow-rolling` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones — the entry is `[iter-191] B4 trial 2 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` at its `sorted()` place, the replay rebuilding the run over the real set, as (iii) adds the record's; `git add` by path of `docs/reference/reading-ledger.jsonl`, the reading the run appended, `docs/research/10.phase4-decisions.md` and `tests/slow-cases.txt`, then the record arm's list, pre-commit, probe worktree and replay, with `-k 'reading-<its id>'`; committed as `docs(research): B4 trial 2 — instrument finding, kept as reading <id>; no trial spent` with no literal's probe. On a refusal from the count or a refused build: no commit here; Task 5 records it.

## Task 5: B4's close, T0016, the index and the retirement of both subjects (D11)

**Files:** `docs/research/10.phase4-decisions.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`.

Every figure is read off the committed record or reading and its entry. Task 4's outcome picks the arm: a verdict — adopt, park or reject — takes steps 1–5; no verdict — a stop kept as a reading, a refused build, a refusal from the count, a merge aborted at a develop check, the data test failing or skipping, or any other end Task 4 sends to T0016 — takes the stop arm below in place of steps 1 and 4.

- [ ] **Step 1: The close entry** — on a verdict, with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the entry below with its placeholders filled — `<VERDICT>` the record's verdict in capitals, `<N>` its `trial_id`, `<SPENT>` and `<REMAIN>` step 2's count, and `<ADOPT CLAUSE>` empty but on an adopt, where it is `` Trial 2's ADOPT is recorded, never deployed: its path, the owner's, in order — a P1 combination trial over record 47's book carrying the leg, outside every bucket's budget, then the engine's change, then T0123's promotion path — waits on T0016's B4 arm. `` with its leading space:

```markdown
[iter-191] B4's next step after trial 2 — closed, the owner's word of 2026-10-24 (Decision: 1)
  Said, attended, 2026-10-24, after reading 6 found no cell with potential: "one more trail on B4, then move on"; asked which variant trial 2 tests, answered "SOL/BTC no-borrow, rolling (Recommended)"; asked which family follows, answered "B3 (Recommended)" (the `[iter-190] B4's next step after the leg reading` entry above). "Move on" is read, as that entry records, as B4 closing after trial 2's verdict, whatever it is, and B3 opening; trial 2's verdict is <VERDICT>, registry trial <N> (the `[iter-191] Verdict — B4 trial 2 <VERDICT>` entry above).
  1. **Close the family** — B4 closes on its two trials and one reading: trial 1, the ETH/BTC and SOL/BTC legs added to the A2-4h ensemble, REJECT (registry trial 58); the leg reading, no cell with potential (reading 6); trial 2, SOL/BTC alone held to the book's own BTC on the rolling set, <VERDICT> (registry trial <N>). Chosen, the owner's word.
  2. **A further B4 trial** — SOL/BTC carried, ETH/BTC alone, the symmetric legs or a further pair, each a B slot; the owner's "one more" is spent.
  What the family leaves: the shared Bucket-B budget reads <SPENT> of 25 (B1 5, B2 7, B4 2), <REMAIN> remaining; B3 opens next, the owner's pick, in a later iteration with its own brainstorm, spec and plan; T0016 stays live for B3 and the C families.<ADOPT CLAUSE>
```

  Measured in a scratch worktree, the entry filled for a reject at a sample id and appended after the conventions entry: `tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py` pass (`50 passed`), and T0016's B3 check, `grep -c -E '^\[iter-[0-9]+\] B4.s next step after trial 2 — closed' docs/research/10.phase4-decisions.md`, prints 1 — it printed 0 before.
- [ ] **Step 2: T0016**, per `topic-ops`, each anchor counted unique with `grep -c` before its edit and the heading set (`grep '^#'`) compared before and after:
  - `## Findings so far`: the budget bullet's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` (at this branch's base it printed `{'B1': 5, 'B2': 7, 'B4': 1} remain 12 []`; on trial 2's record, with no orphan, it prints `{'B1': 5, 'B2': 7, 'B4': 2} remain 11 []`): `(B1 spent 5, B2 spent 7, B4 spent 1, 12 remain)` reads `(B1 spent <its B1>, B2 spent <its B2>, B4 spent <its B4>, <its remain> remain)`, each orphan it lists named there; after the `**B4's leg reading (iter-190, spec 00145, reading 6).**` bullet, one bullet `**B4 trial 2 <VERDICT> (iter-191, spec 00146, registry trial <N>).**` — the row that fired and SOL/BTC's holding in one or two sentences, pointing at its decisions-log entry for the figures — and the sentence: B4 closed on the owner's word of 2026-10-24, on its two trials and one reading — the `[iter-191] B4's next step after trial 2 — closed` entry.
  - `## Done so far`: the **B4 opened** bullet's last sentence, `` ..., no slot spent, the subject retired. ``, gains after it `` Trial 2 (iter-191, spec/plan `00146`, registry trial <N>) <VERDICT>: the subjects `b4-sol-noborrow-rolling` and `b4-sol-noborrow-rolling-preflight` and the data-gated basis test `tests/test_research_b4_sol_noborrow_rolling_basis.py`, the subjects retired; **closed at iter-191** on the owner's word of 2026-10-24. ``
  - `## Suggested next steps`: its one bullet, `` - B4 trial 2, the owner's pick of 2026-10-24 (the `[iter-190] B4's next step after the leg reading` entry): … then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``, becomes `` - B3, the owner's next-family pick of 2026-10-24 (the `[iter-190] B4's next step after the leg reading` entry), now that B4 is closed (the `[iter-191] B4's next step after trial 2 — closed` entry): master plan §5's cross-sectional long-only rank tilt with the A1-short overlay, its §10 prerequisite met, opening in a later iteration with its own brainstorm, spec and plan against the shared B budget (<REMAIN> remain); then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``; on an adopt, a bullet beside it: `` - (owner) B4 trial 2's ADOPT (registry trial <N>), recorded, never deployed: its path in order — a P1 combination trial over record 47's book carrying the SOL/BTC leg, outside every bucket's budget, then the engine's change to trade the pair, then T0123's promotion path (spec 00146 D11). ``
  - `ripe_when`: its B4 arm, `` B4: ripe — trial 2 on the owner''s pick of 2026-10-24, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B4.s next step after the leg reading'' docs/research/10.phase4-decisions.md` prints at least 1, then B4 closes; `` (the trailing space included), is removed, and the B3 arm left as it is, which the close entry fires; on an adopt it becomes `` B4: an activity, the P1 combination trial over record 47''s book carrying B4 trial 2''s SOL/BTC leg is picked for an iteration, check: `cat docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md | grep -c -E ''^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book''` prints at least 1; `` instead — in the frontmatter's single quotes, each `'` inside it doubled as written here, the check kept in its own backticks; the other families' arms unchanged.
  Measured in the scratch worktree: the heading set unchanged, the frontmatter parsing to the intended text on the reject arm and on the adopt arm, the B3 check printing 1 on both and the adopt arm's check 0, and `tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_retired_subjects.py` passing (`1116 passed`) with steps 3–4 applied.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the two subjects, so `RETIRED_SUBJECTS` gains `"b4-sol-noborrow-rolling",` and `"b4-sol-noborrow-rolling-preflight",` after `"b4-leg-reading",`, under the comment `# B4's finished trials and the reading beside them.` as it stands. Every test function Task 1 adds is parametrised by the subject's name, so the hook marks each case and no function carries the mark by hand; `test_each_subject_declares_the_metric_keys_its_build_returns` keeps its new lines, the subjects staying in `SUBJECTS`. `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q -p no:cacheprovider | grep -c -E "b4-sol-noborrow-rolling|b4_sol"` prints 0 and the same under `-m retired` prints 43 (measured in the scratch worktree), and `mkdir -p .tmp/plan-00146 && uv run pytest tests/test_retired_subjects.py -q -p no:cacheprovider --basetemp=.tmp/plan-00146/pt` passes.
- [ ] **Step 5: Gate and commit** — `git add` the four paths; the list over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path, `tests/test_research_command.py` in its four parts; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): B4 closed after trial 2 on the owner's word, T0016 to B3 next; trial 2's subjects retired`.

  **The stop arm**: no close entry and no retirement — the owner's "then move on" follows a verdict, and a stop has none (D11), and until the owner's call a trial still to run may evaluate the subjects (`tests/retired_subjects.py`'s own rule). Step 2's Findings bullet is headed `**B4 trial 2, no verdict (iter-191, spec 00146).**`, names the reading by id where one was kept, and quotes whole the line that stopped it — the check's `sys.exit` line, the conflict `git merge` printed, the failure or skip line in `.tmp/plan-00146/basis.out`, the line in `.tmp/plan-00146/b4-sol-noborrow-rolling-preflight.out` or `.tmp/plan-00146/b4-sol-noborrow-rolling.out`, or that run's output's end as Task 4 step 4 quotes it — the trial unspent unless the count lists its attempt as an orphan, which spends the slot; its Done-so-far sentence names no record and ends `no slot spent, its subjects kept.`; the next-steps bullet becomes `` - (owner) B4's next step after trial 2's stop — trial 2 run again once its cause, quoted in Findings, is fixed, or B4 closed unrun — recorded as a `[iter-NNN] B4's next step after trial 2` entry; B3 opens after B4 closes, the owner's next-family pick of 2026-10-24; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``; and the `ripe_when` B4 arm becomes `` B4: an activity, the owner''s call on trial 2''s stop — the trial run again once its cause is fixed, or B4 closed — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B4.s next step after trial 2'' docs/research/10.phase4-decisions.md` prints at least 1; `` (measured in the scratch worktree: the frontmatter parses, the check prints 0, the frontmatter and index tests pass). Steps 3 and 5 run over the two `docs/open-topics/` paths alone, the message ending `no verdict of B4 trial 2, its subjects kept`.

## Task 6 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-191 — B4 trial 2: SOL/BTC no-borrow on rolling` (67 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 4–5's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with `ohlc-rolling`, and for the replay's gate `ohlc-full`, linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the verdict or the stop, the pre-flight's output quoted whole in a fenced block (`.tmp/plan-00146/b4-sol-noborrow-rolling-preflight.out`), every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the owner's ruling the trial and the close run under, quoted, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00146` collected and removed, and each link removed with `test -L <the checkout>/data/<set> && unlink <the checkout>/data/<set>` in this worktree and in each reader's checkout whose `data/` holds it; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-rolling` and `ohlc-full` still there.

Decisions log: the conventions entry (Task 2 step 5), before the hash; the verdict or instrument-finding entry (Task 4 step 6), in its record's commit; B4's close on the owner's word (Task 5 step 1), on a verdict; on a stop, B4's next step after trial 2 is the owner's, its entry a later branch's (T0016's trigger).
