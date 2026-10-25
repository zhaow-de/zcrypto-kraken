# B3 trial 1 — a cross-sectional momentum rank tilt of the A2-4h ensemble's long weights on frozen ohlc-full: the compute module, the trial subject and its twin, the family key, the data-gated basis test, the loop's pick before the hash, the gated run and the record, T0016 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b3.py tests/test_alpha_b3.py cli/research/subjects.py cli/registry/budget.py tests/test_research_command.py tests/test_trial_registry_provenance.py README.md tests/slow-cases.txt tests/test_research_b3_rank_tilt_basis.py docs/research/10.phase4-decisions.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00147-b3-rank-tilt-design.md docs/plans/00147-b3-rank-tilt.md` prints `tier: full`, for `tests/test_alpha_b3.py` and `tests/test_research_command.py` "a test importing cli.alpha", `cli/registry/budget.py` "under cli/registry/", `tests/test_trial_registry_provenance.py` "a test importing cli.registry", `tests/test_research_b3_rank_tilt_basis.py` "a test importing cli.alpha.b1" once Task 3 has created it, and `docs/reference/trial-registry.jsonl`).

**Goal:** B3's trial 1 (spec 00147) — the adopted A2-4h ensemble with each arm's inverse-vol weights of the assets it holds long tilted at every close by their rank in the whole basket on the trailing 180-close simple return, where the basket ranks 8 assets or more, against the untilted ensemble, on frozen `ohlc-full`: a compute module `cli/alpha/b3.py`; two research subjects in `cli/research/subjects.py`, the trial and its evaluate-only pre-flight twin; the family key `B3` in `cli/registry/budget.py`'s bucket B; the data-gated test of their inputs half; the loop's pick and the trial's conventions in the decisions log before the hash; the trial run through spec 00133's trial-attempts log, its verdict or stop in the registry and the decisions log; then T0016, B3's next step the owner's.

**Architecture:** `cli/alpha/b3.py` holds pure functions over lists, as `cli/alpha/b4.py` does — the momentum score, the centred ranks, the tilt at one close (the basket ranked, the floor, the longs tilted), and `b3_book_returns`, `a2_book_returns`' body with each close's weights passed through the tilt — importing A2's helpers and editing none. `cli/research/subjects.py` gains three insertions and changes no existing line: the module's import, the B3 block before `SUBJECTS` — `_B3_SCORE_LOOKBACK`, `_B3_STRENGTH`, `_B3_FLOOR`, `_B3_N_TRIALS`, `_B3Inputs`, the build in three halves (`_b3_reads`, `_b3_inputs`, `_b3_metrics` / `_b3_preflight_metrics`), `_b3_ensemble`, `_b3_first_engaged`, `_b3_engagement`, `_b3_build`, the two builders, the rule `_b3_rank_tilt_verdict` and the key sets — and two `SUBJECTS` entries; trial 58's `_b4_ensemble`, `_b4_limited`, `_b4_net` and `_b4_arm_a_bar` are read as they are. `cli/registry/budget.py`'s `BUCKET_OF` gains `"B3": "B"`. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00147-b3-rank-tilt-design.md` — binding; D1–D10 are cited by name and the values below are copied from it. It reads spec 00144's arm A, limits, costing and bar, frozen by record 58's `spec_hash`. **Iteration:** iter-192. **Topic:** T0016, its B3 arm. **Branch:** `research/iter-192-b3-rank-tilt`, worktree `.claude/worktrees/iter192`, `data/ohlc-full` linked read-only from the main checkout, and no other set. A choice this plan makes that the spec leaves open is marked **Author's call**. This version amends the first (commit `b50ebeefd`) with the spec's amendment — the basket ranked, the floor 8, the longs tilted — every fence, literal, test and probe row the amendment reaches re-cut and re-run. Every code fence below was cut from the files the author ran: Tasks 1–3's code and tests were written in this worktree beside the staged spec, then carried, task by task, into a detached scratch worktree at the first plan commit, `b50ebeefd`, its spec tracked; Task 1's tests measured red there against the base module (`1 error` at collection) and green with the module (`23 passed`); Task 2's new cases red against Task 1's tree (`28 failed, 877 deselected`, and the budgets literal `1 failed`) and green with Task 2's code (`28 passed, 895 deselected`), the shared rows the two subjects add green (`19 passed, 904 deselected in 114.86s`); Task 2 step 7's four gate parts green; Task 3's data-gated case `1 passed` with a call of 134.75 s on the authoring tree; the slow cases timed; Task 1's 36 and Task 2's 63 probe rows run in that worktree, each task's tree committed there, 99 of 99 `KILLED`; on Task 3's tree committed there, with `ohlc-full` linked, Task 4 step 4's data test and fixture rows (`3 passed in 169.55s`) and record 58's replay (`1 passed in 301.39s`), Task 3's two decisions-log entries appended and run through the decisions-log tests, Task 4's pre-flight check run over a synthetic pre-flight print carrying the real block, and Task 6's T0016 edits and index tried on each outcome's arm, then reverted. The fences applied to the base as the steps say reproduce every authoring file but for four comments' decision numbers, corrected after those runs to the spec's own — D7 for the count's and the rule's, D8 for the two key sets'; the files were restored to the base before this plan was committed. Not run: any `zcrypto research eval` of the two subjects (Tasks 4–5), the record's check program beyond a parse, the record's replay and the literal's probe (Task 5), the topic edits as committed (Task 6) and the PR (Task 7).

## Global Constraints

- **The books and the costing** (D2–D5): the union `_capturing_union(reader, dataset, 240, window, None, accept_holes)` of the ten EUR assets, no other pair, refused before any book below `_DECISIVE_START` + 2 return indices or with no return index closing outside the stub years, and `--as-of` refused before any read; arm A `_b4_limited(_b4_ensemble(fed))`, arm B `_b4_limited(<the mean of the three arms' b3_book_returns positions>)`, `fed = _ffill_btc(h4_prices)`, the three adopted arms `_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year, each arm's book `b3_book_returns(fed, config=<its A2Config>, score_lookback=180, strength=0.5, floor=8)`; the tilt at a close: the basket — every asset with an inverse-vol weight above 0 and a score, whatever its direction, n of them — ranked, `z = (2·rank − (n + 1)) / (n − 1)` the centred ascending rank of `p[k] / p[k − 180] − 1`, ties at their average rank; where n ≥ 8, each long's — a direction above 0 — weight times `1 + 0.5·z`, the longs rescaled to their untilted sum, the flat assets untouched; below 8, or with fewer than 2 longs, every weight untilted; every book costed by `_b4_net(positions, returns, stress=…)`, `returns = {a: _asset_returns(fed[a])}`, no carry; §10's limits through `_b4_limited`, one factor per bar.
- **The bars** (D7): every `a1_kill_bar` call `n_trials=1, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`, the headline (30, 42); arm A's bar `_b4_arm_a_bar` at (30, 42); the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` at `first` 0 and at the tilt's first engagement, `tilt_first_engaged`, the first return index at which arm B's positions differ from arm A's (15,672); refused before any bar: fewer than 2 return indices from the first engagement.
- **The count** (D7): `_B3_N_TRIALS = 1`, `required_n("B3")` as the spec measured it, fixed by the spec's hash; at `var_trials` 0.0 the DSR leg is the PSR against 0.
- **The rule** (D7): `_b3_rank_tilt_verdict` — `None` when `arm_a_passes` is 0 or `stamps_positions_differ` is 0, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0` with `head_to_head_spa_p_primary < 0.05`, `park` on the first with the p at or above 0.05, `reject` otherwise; the park variants the tilt at another `M` or `k` and the A1-short BTC overlay.
- **The record** (D8): family `B3`; `n_trials_in_family` 1; variant `B3-rank-tilt-a2eq-full-v1`; iteration `iter-192`; seeds (42, 7, 1234); 44 metric keys; the block `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`; no `--verdict`.
- **The pre-flight read** (D9), in this order: (a) the block and `ohlc-full`'s vouched status (Task 3's `BLOCK` and `VOUCHED`); (b) arm A's seven anchors record 58's stored figures to the last digit — `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full` against its `arm_a_max_drawdown`, `turnover_a`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`, and `arm_a_spot_drag_pct_yr` against `turnover_a / 27,337 × 0.006 × 2,190`; (c) the dead knob — `stamps_positions_differ` above 0, read before the engagement; (d) the engagement the measured basis's — Task 3's `ENGAGEMENT`; (e) arm A's `passes` 1.
- **The hash rule** (D9): before Task 4 step 2 takes the spec's sha256, nobody reads or computes arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — by code, a program or arithmetic over a stored figure — nor runs `b3-rank-tilt` or `b3-rank-tilt-preflight` over the real set; weights, ranks, positions, exposures, limit engagement and turnover are allowed — what the data-gated test (Task 3) computes, and no return of a book. `a2_book_returns` and `b3_book_returns` compute each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; nothing reads them. No reader, reviewer or plan-review dispatch runs either subject over the real set before the hash, and every read's dispatch carries this rule. No return of arm B is computed over the real data before the trial's `--register` run, and the trial subject is never run as a plain eval; after it, only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with the set linked.
- **Unchanged** (D8): every existing function of `cli/research/subjects.py` — trial 58's machinery among them — `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b4.py` and the other `cli/alpha/*` modules but the new one; `cli/features/*`, `cli/portfolio/*`, `cli/risk/*`, `cli/costs/*`, `cli/validation/*`, `cli/engine/*`; `cli/registry/*` but `BUCKET_OF`'s line; the existing subjects; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/alpha/b3.py` from Task 1 on and `cli/registry/budget.py` and `cli/research/subjects.py` from Task 2 on, nothing else; from Task 2 on, `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@')" = 3` and `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@ -[0-9]*,0 ')" = 3` each exit 0 — three hunks, each a pure insertion, so a line changed or added anywhere but at Task 2 step 3's three sites is a fourth hunk or an impure one — and `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/registry/budget.py | grep -c '^[-+][^-+]'` prints 2, `BUCKET_OF`'s old line and its new one. Measured on the authoring tree, `subjects.py`'s hunks: `@@ -81,0 +82 @@`, `@@ -4189,0 +4191,301 @@` and `@@ -4603,0 +4906,25 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00147-b3-rank-tilt-design.md` after Task 4 step 2, nor specs 00128, 00133, 00137, 00144 and 00146, nor the spec before then except a fix commit a read of Task 3 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 5 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, a read-only link, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The trial, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 4 step 3, Task 5 step 1) and Task 7's `gh` calls, push and `merge-pr` are the exceptions. A data link is removed with `test -L <its absolute path> && unlink <its absolute path>`, never `rm`.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 6's reads, Tasks 4–5 and Task 7, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the pre-flight, the register, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 6 and Task 3's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00147 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00147/` follows `mkdir -p .tmp/plan-00147 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00147/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `mkdir -p .tmp/plan-00147 && bash infra/scripts/consumers.sh --direct <each changed path> | sort -u > .tmp/plan-00147/T.txt`, never with `2>/dev/null`, whose stderr is where a refusal speaks, and `test -s .tmp/plan-00147/T.txt && uv run pytest $(cat .tmp/plan-00147/T.txt) -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt`, so that an empty list fails closed and never becomes a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every file a commit carries is staged by explicit path — the registry's line by `--register`, the ledger's by `--reading` or by a stop under `--register`, among them, whose one commit is Task 5 step 6's — since the commit and the probe setup's `git write-tree` read the index while the list reads the working tree. Every list holding `tests/test_research_command.py` runs it in four parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms, so that none can pass 600 s: `tests/test_research_command.py -k "not reentry and not b2"` (`--basetemp=.tmp/plan-00147/pt-1`, measured on Task 2's tree in the scratch worktree, `510 passed, 413 deselected in 215.21s`), `tests/test_research_command.py -k "b2 and not reentry"` (`pt-2`, measured `227 passed, 696 deselected in 314.68s`), `tests/test_research_command.py -k reentry` (`pt-3`, measured `71 passed, 852 deselected in 91.16s`) and the rest of the list, read off `.tmp/plan-00147/T.txt` with that file's line left out (`pt-4`). Every commit message carries the result line of each test command its gate ran, a run over that commit's own tree, and the two trailer lines exactly as the executing session's attribution gives them — `Co-Authored-By:` naming the model that ran the step, and `Claude-Session:`.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00147 &&
  test ! -e .tmp/plan-00147/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00147/probe HEAD &&
  git -C .tmp/plan-00147/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00147/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00147/probe/.tmp
```

  Then, from `.tmp/plan-00147/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, or, in `cli/registry/budget.py`, which holds none, the literal the case imports, so it fails at import or at its call. A mutation whose text also stands in an existing function — trial 58's inputs, ensemble, metrics and engagement share several lines with the new ones — carries the address of its own function's range, `/^def <name>(/,/^def /`, of its entry's, `/"<subject>": Subject(/,/^    ),/`, of the rule's, `/^def _b3_rank_tilt_verdict(/,/^_B3_ENGAGEMENT_KEYS/`, or of the key set's, `/^_B3_ENGAGEMENT_KEYS = /,/^)/`, so its dry run changes one line; a pattern that holds `'` writes it as `.`. After the last verdict, `git worktree remove --force .tmp/plan-00147/probe` — each data link in it unlinked first with `test -L <its absolute path> && unlink <its absolute path>`, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, `ohlc-full` still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subjects' names** (D8): `b3-rank-tilt` and `b3-rank-tilt-preflight`, which no registered or retired subject's name equals or opens with a hyphen, and which open none (the spec's basis). Every new test function's name in `tests/test_research_command.py` carries `b3_`, which no hyphenated id and no other test's name carries, so `-k b3_` selects them alone; the shared rows the two subjects add carry the hyphenated `b3-rank-tilt` in their ids.

## Task 1: the compute module `cli/alpha/b3.py` (D3)

**Files:** Create `cli/alpha/b3.py`, `tests/test_alpha_b3.py`.

**Interfaces:** Consumes `cli/alpha/a1.py`'s `_asset_returns`, `_check_window`, `_inverse_vol_weights` and `_validate_prices_by_asset`, `cli/alpha/a2.py`'s `A2Config` and `_asset_directions_a2`, `cli.alpha.errors.AlphaError`, `cli.backtest.run_backtest` and `cli.benchmark.strategies.vol_target`; its tests also `a2_book_returns`. Produces `momentum_scores`, `centred_ranks`, `rank_tilt` and `b3_book_returns`, which Task 2's subjects and tests import.

- [ ] **Step 1: Write the failing tests** — `tests/test_alpha_b3.py`, whole:

```python
import math

import pytest

import cli.alpha.a2 as a2_module
from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.a2 import _asset_directions_a2
from cli.alpha.b3 import b3_book_returns, centred_ranks, momentum_scores, rank_tilt
from cli.alpha.errors import AlphaError

_CONFIG = A2Config(lookbacks=(5, 10), short="off", target_vol=0.12, vol_lookback=20, basket_lookback=20, periods_per_year=2190)


def _prices(n: int = 300) -> dict[str, list[float | None]]:
    """Four assets trending at their own rates through their own waves, ETH missing one close and SOL listing at 40."""
    shapes = {"BTC": (100.0, 1.002, 0.08, 9.0), "ETH": (50.0, 1.003, 0.10, 7.0), "SOL": (20.0, 1.001, 0.12, 11.0)}
    shapes["XRP"] = (1.0, 1.0025, 0.09, 5.0)
    prices = {
        a: [level * growth**k * (1 + depth * math.sin(k / period + i)) for k in range(n)]
        for i, (a, (level, growth, depth, period)) in enumerate(shapes.items())
    }
    prices["ETH"][150] = None
    prices["SOL"][:40] = [None] * 40
    return prices


def test_momentum_scores_read_the_close_lookback_back_and_none_where_either_is_missing():
    prices = [1.0, 2.0, 4.0, None, 8.0, 10.0, 12.0]

    assert momentum_scores(prices, lookback=2) == [None, None, 3.0, None, 1.0, None]
    assert momentum_scores(prices, lookback=2) == momentum_scores([*prices[:6], 99.0], lookback=2)


@pytest.mark.parametrize("lookback", [1, 0, 2.0], ids=["one", "zero", "a-float"])
def test_momentum_scores_refuse_a_lookback_below_2(lookback):
    with pytest.raises(AlphaError, match="lookback must be an int >= 2"):
        momentum_scores([1.0, 2.0, 3.0], lookback=lookback)


def test_centred_ranks_run_from_the_weakest_at_minus_1_to_the_strongest_at_plus_1_ties_at_their_average():
    assert centred_ranks({"BTC": 0.1, "ETH": 0.3, "SOL": 0.2}) == {"BTC": -1.0, "SOL": 0.0, "ETH": 1.0}
    assert centred_ranks({"BTC": 0.1, "ETH": 0.1, "SOL": 0.3, "XRP": -0.2}) == {"XRP": -1.0, "BTC": 0.0, "ETH": 0.0, "SOL": 1.0}
    assert centred_ranks({"BTC": 0.5, "ETH": 0.5}) == {"BTC": 0.0, "ETH": 0.0}


def test_centred_ranks_refuse_fewer_than_2_scores():
    with pytest.raises(AlphaError, match="a rank needs 2 scores or more, got 1"):
        centred_ranks({"BTC": 0.1})


def test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum():
    weights = {"BTC": 0.375, "ETH": 0.25, "SOL": 0.25, "XRP": 0.125}
    directions = {"BTC": 1.0, "ETH": 2 / 3, "SOL": 1 / 3, "XRP": 0.0}
    scores = {"BTC": 0.1, "ETH": 0.3, "SOL": 0.2, "XRP": 0.9}

    tilted, basket, longs = rank_tilt(weights, directions, scores, strength=0.5, floor=4)

    # The flat XRP ranks strongest, so ETH, SOL and BTC take z 1/3, -1/3 and -1: 7/6, 5/6 and 0.5 times, rescaled by
    # 0.875 / 0.6875; XRP's own weight is untouched.
    assert (basket, longs) == (4, 3) and tilted["XRP"] == 0.125
    for asset, times in (("BTC", 0.5), ("SOL", 5 / 6), ("ETH", 7 / 6)):
        assert math.isclose(tilted[asset], weights[asset] * times * 0.875 / 0.6875, rel_tol=1e-12)
    assert math.isclose(math.fsum(tilted[a] for a in ("BTC", "ETH", "SOL")), 0.875, rel_tol=1e-12)
    assert weights == {"BTC": 0.375, "ETH": 0.25, "SOL": 0.25, "XRP": 0.125}


_EIGHT = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC")


@pytest.mark.parametrize(
    ("unscored", "basket", "longs"),
    [pytest.param("LTC", 7, 0, id="seven-in-the-basket"), pytest.param(None, 8, 8, id="eight-in-the-basket")],
)
def test_the_tilt_engages_at_a_basket_of_8_and_not_at_7(unscored, basket, longs):
    weights = dict.fromkeys(_EIGHT, 0.125)
    scores = {a: None if a == unscored else 0.01 * i for i, a in enumerate(_EIGHT)}

    tilted, ranked, moved = rank_tilt(weights, dict.fromkeys(_EIGHT, 1.0), scores, strength=0.5, floor=8)

    assert (ranked, moved) == (basket, longs)
    if not longs:
        assert tilted is weights
    else:
        # Equal weights and every asset long: the rescale is 1, each asset 1 + 0.5 * (2 * rank - 9) / 7 times its weight.
        for rank, asset in enumerate(_EIGHT, 1):
            assert math.isclose(tilted[asset], 0.125 * (1 + 0.5 * (2 * rank - 9) / 7), rel_tol=1e-12)


@pytest.mark.parametrize(
    "directions",
    [
        pytest.param({"BTC": 1.0, "ETH": 0.0, "SOL": 0.0}, id="one-asset-long"),
        pytest.param({"BTC": 1.0, "ETH": None, "SOL": 0.0}, id="a-direction-missing"),
        pytest.param({"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}, id="none-long"),
    ],
)
def test_the_tilt_leaves_a_basket_with_fewer_than_2_longs_untilted(directions):
    weights = {"BTC": 0.5, "ETH": 0.25, "SOL": 0.25}

    tilted, basket, moved = rank_tilt(weights, directions, {"BTC": 0.1, "ETH": 0.2, "SOL": 0.3}, strength=0.5, floor=2)

    assert tilted is weights and (basket, moved) == (3, 0)


def test_the_tilt_ranks_no_asset_without_a_weight_or_a_score():
    weights = {"BTC": 0.5, "ETH": 0.0, "SOL": 0.5}

    tilted, basket, moved = rank_tilt(
        weights, dict.fromkeys(weights, 1.0), {"BTC": 0.1, "ETH": 0.2, "SOL": None}, strength=0.5, floor=2
    )

    assert tilted is weights and (basket, moved) == (1, 0)


def test_the_book_at_strength_0_is_a2s_book_to_the_bit():
    prices = _prices()

    book = b3_book_returns(prices, config=_CONFIG, score_lookback=30, strength=0.0, floor=3)

    assert {key: value for key, value in book.items() if key not in ("ranked", "tilted")} == a2_book_returns(prices, config=_CONFIG)
    assert max(book["tilted"]) >= 2


def test_the_book_is_a2s_book_on_the_tilted_weights(monkeypatch):
    prices = _prices()
    n = len(prices["BTC"]) - 1
    directions = _asset_directions_a2(
        prices, list(range(n + 1)), {a: [k for k, p in enumerate(v) if p is not None] for a, v in prices.items()}, config=_CONFIG
    )
    scores = {a: momentum_scores(v, lookback=30) for a, v in prices.items()}
    tilts = [
        rank_tilt(w, {a: directions[a][k] for a in prices}, {a: scores[a][k] for a in prices}, strength=0.5, floor=3)
        for k, w in enumerate(_inverse_vol_weights(prices, lookback=20))
    ]
    untilted = a2_book_returns(prices, config=_CONFIG)

    book = b3_book_returns(prices, config=_CONFIG, score_lookback=30, strength=0.5, floor=3)

    monkeypatch.setattr(a2_module, "_inverse_vol_weights", lambda prices_by_asset, *, lookback: [w for w, _, _ in tilts])
    assert {key: value for key, value in book.items() if key not in ("ranked", "tilted")} == a2_book_returns(prices, config=_CONFIG)
    assert (book["ranked"], book["tilted"]) == ([basket for _, basket, _ in tilts], [longs for _, _, longs in tilts])
    assert book["asset_positions"] != untilted["asset_positions"]
    assert book["book_base_returns"] != untilted["book_base_returns"]


def test_the_book_at_close_k_reads_no_close_after_k():
    prices = _prices()
    k = 241
    # Each asset's closes after k move by a factor of its own, so a score read past k reorders the ranks at k.
    later = {
        a: [*v[: k + 1], *(None if p is None else p * (1 + 0.3 * i) for p in v[k + 1 :])] for i, (a, v) in enumerate(prices.items())
    }

    book = b3_book_returns(prices, config=_CONFIG, score_lookback=30, strength=0.5, floor=3)
    moved = b3_book_returns(later, config=_CONFIG, score_lookback=30, strength=0.5, floor=3)

    assert all(book["asset_positions"][a][: k + 1] == moved["asset_positions"][a][: k + 1] for a in prices)
    assert (book["ranked"][: k + 1], book["tilted"][: k + 1]) == (moved["ranked"][: k + 1], moved["tilted"][: k + 1])
    assert book["asset_positions"] != moved["asset_positions"]


@pytest.mark.parametrize("strength", [-0.1, 1.0, math.nan, False], ids=["negative", "one", "nan", "a-bool"])
def test_the_book_refuses_a_strength_outside_0_to_1(strength):
    with pytest.raises(AlphaError, match="strength must be a number in"):
        b3_book_returns(_prices(), config=_CONFIG, score_lookback=30, strength=strength, floor=3)


def test_the_book_refuses_a_config_that_is_no_a2_config():
    with pytest.raises(AlphaError, match="config must be an A2Config"):
        b3_book_returns(_prices(), config={"lookbacks": (5, 10)}, score_lookback=30, strength=0.5, floor=3)


def test_the_book_refuses_a_score_lookback_below_2():
    with pytest.raises(AlphaError, match="score_lookback must be an int >= 2"):
        b3_book_returns(_prices(), config=_CONFIG, score_lookback=1, strength=0.5, floor=3)


def test_the_book_refuses_a_floor_below_2():
    with pytest.raises(AlphaError, match="floor must be an int >= 2"):
        b3_book_returns(_prices(), config=_CONFIG, score_lookback=30, strength=0.5, floor=1)
```

  **Author's call** — every case a known answer: the score on a hand series with a missing close, the same with every close after the last read moved; the centred ranks on three scores, on four with a tie and on a two-way tie; the tilt on a basket of four at a floor of 4 — the flat XRP ranked strongest, so the three longs take z 1/3, −1/3 and −1, at 7/6, 5/6 and 0.5 times, rescaled to the longs' sum, XRP's own weight untouched — each figure written from the definition, never from the code; the floor on eight equal weights, all long, a basket of 7 untilted and of 8 tilted at `1 + 0.5·(2·rank − 9)/7` each; fewer than 2 longs untilted, row by row for each condition that leaves an asset flat; an asset with a zero weight or no score out of the basket; the book on a four-asset fixture at a floor of 3 — ETH missing one close, SOL listing at 40 — at strength 0 equal to `a2_book_returns` to the bit, at 0.5 equal to `a2_book_returns` run on the weights `rank_tilt` gives (its weight path replaced through `cli.alpha.a2`'s own name), its basket sizes and tilted counts `rank_tilt`'s and its positions and base returns moved off the untilted book's; no look-ahead, every close after 241 moved by a factor of its own asset, the book's positions, basket sizes and tilted counts to 241 unmoved — the close chosen as one where the basket holds four and a score read one close late reorders it (measured with that mutation in the probe block); the score lookback 30 against the basket's 20, so a book scoring on the basket's lookback fails; each refusal its own row, matched on a phrase only its own message holds.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00147 && uv run pytest tests/test_alpha_b3.py -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt`: collection stops at the import of `cli.alpha.b3` (measured on the base: `1 error`).
- [ ] **Step 3: Implement `cli/alpha/b3.py`**, whole:

```python
"""B3 trial 1's compute (docs/specs/00147-b3-rank-tilt-design.md D3): the A2 book with its long weights tilted at each
close by a cross-sectional momentum rank."""

from __future__ import annotations

import math

from cli.alpha.a1 import _asset_returns, _check_window, _inverse_vol_weights, _validate_prices_by_asset
from cli.alpha.a2 import A2Config, _asset_directions_a2
from cli.alpha.errors import AlphaError
from cli.backtest import run_backtest
from cli.benchmark.strategies import vol_target


def momentum_scores(prices: list[float | None], *, lookback: int) -> list[float | None]:
    """Per return index k, `p[k] / p[k - lookback] - 1`, known at close k; None where either close is missing."""
    _check_window("lookback", lookback)
    return [
        None if k < lookback or prices[k] is None or prices[k - lookback] is None else prices[k] / prices[k - lookback] - 1
        for k in range(len(prices) - 1)
    ]


def centred_ranks(scores: dict[str, float]) -> dict[str, float]:
    """Each score's ascending rank, ties at their average rank, as `(2 * rank - (n + 1)) / (n - 1)`: the weakest -1, the
    strongest +1."""
    n = len(scores)
    if n < 2:
        raise AlphaError(f"a rank needs 2 scores or more, got {n}")
    order = sorted(scores, key=scores.__getitem__)
    out: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        rank = (i + j + 2) / 2
        for asset in order[i : j + 1]:
            out[asset] = (2 * rank - (n + 1)) / (n - 1)
        i = j + 1
    return out


def rank_tilt(
    weights: dict[str, float],
    directions: dict[str, float | None],
    scores: dict[str, float | None],
    *,
    strength: float,
    floor: int,
) -> tuple[dict[str, float], int, int]:
    """The basket — every asset with a weight above 0 and a score — ranked, and when it holds `floor` assets or more,
    each of its longs' weights, a direction above 0, times `1 + strength * z`, rescaled to their untilted sum; every
    other weight as it is, and below the floor or with fewer than 2 longs the weights themselves, a single long's
    rescale being its own weight. Returns the weights, the basket's size and the count of longs tilted."""
    basket = [a for a, w in weights.items() if w > 0 and scores[a] is not None]
    if len(basket) < floor:
        return weights, len(basket), 0
    longs = [a for a in basket if directions[a] is not None and directions[a] > 0]
    if len(longs) < 2:
        return weights, len(basket), 0
    z = centred_ranks({a: scores[a] for a in basket})
    raw = {a: weights[a] * (1 + strength * z[a]) for a in longs}
    scale = math.fsum(weights[a] for a in longs) / math.fsum(raw.values())
    return weights | {a: w * scale for a, w in raw.items()}, len(basket), len(longs)


def b3_book_returns(
    prices_by_asset: dict[str, list[float | None]], *, config: A2Config, score_lookback: int, strength: float, floor: int
) -> dict:
    """`a2_book_returns` with each close's inverse-vol weights passed through `rank_tilt` before the base returns, the vol
    target and the positions read them; `ranked` holds each close's basket size and `tilted` its count of longs tilted."""
    if not isinstance(config, A2Config):
        raise AlphaError(f"config must be an A2Config, got {type(config)!r}")
    _validate_prices_by_asset(prices_by_asset)
    _check_window("score_lookback", score_lookback)
    _check_window("floor", floor)
    if not isinstance(strength, (int, float)) or isinstance(strength, bool) or not 0 <= strength < 1:
        raise AlphaError(f"strength must be a number in [0, 1), got {strength!r}")
    length = len(prices_by_asset["BTC"])

    union_ts = list(range(length))
    asset_ts: dict[str, list] = {
        asset: [k for k, p in enumerate(prices) if p is not None] for asset, prices in prices_by_asset.items()
    }

    directions = _asset_directions_a2(prices_by_asset, union_ts, asset_ts, config=config)
    returns = {asset: _asset_returns(prices) for asset, prices in prices_by_asset.items()}
    scores = {asset: momentum_scores(prices, lookback=score_lookback) for asset, prices in prices_by_asset.items()}
    weights: list[dict[str, float]] = []
    ranked: list[int] = []
    tilted_longs: list[int] = []
    for k, untilted in enumerate(_inverse_vol_weights(prices_by_asset, lookback=config.basket_lookback)):
        tilted, basket, longs = rank_tilt(
            untilted,
            {asset: directions[asset][k] for asset in prices_by_asset},
            {asset: scores[asset][k] for asset in prices_by_asset},
            strength=strength,
            floor=floor,
        )
        weights.append(tilted)
        ranked.append(basket)
        tilted_longs.append(longs)

    book_base_returns: list[float] = []
    for k in range(length - 1):
        total = 0.0
        for asset in prices_by_asset:
            r = returns[asset][k]
            d = directions[asset][k]
            if r is None or d is None:
                continue
            total += weights[k].get(asset, 0.0) * d * r
        book_base_returns.append(total)

    positions = vol_target(
        book_base_returns,
        target_vol=config.target_vol / math.sqrt(config.periods_per_year),
        lookback=config.vol_lookback,
        max_leverage=config.max_leverage,
    )
    asset_positions: dict[str, list[float]] = {
        asset: [weights[k].get(asset, 0.0) * (directions[asset][k] or 0.0) * positions[k] for k in range(length - 1)]
        for asset in prices_by_asset
    }
    backtest = run_backtest(book_base_returns, positions, fee_rate=0.0, periods_per_year=config.periods_per_year)
    return {
        "book_base_returns": book_base_returns,
        "vol_target_positions": positions,
        "asset_positions": asset_positions,
        "net_returns": backtest["net_returns"],
        "metrics": {k: v for k, v in backtest.items() if k != "net_returns"},
        "ranked": ranked,
        "tilted": tilted_longs,
    }
```

- [ ] **Step 4: Run them to verify they pass** — step 2's command, measured `23 passed`.
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b3.py tests/test_alpha_b3.py`; the Global Constraints' list over the two paths (measured: `tests/test_alpha_b3.py` alone, `23 passed`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured in the scratch worktree on Task 1's tree, 36 of 36):

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def momentum_scores(/def momentum_scores_gone(/' --mutation 's/else prices\[k\] \/ prices\[k - lookback\] - 1/else prices[k] \/ prices[k - lookback]/' -- uv run pytest 'tests/test_alpha_b3.py::test_momentum_scores_read_the_close_lookback_back_and_none_where_either_is_missing' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def momentum_scores(/def momentum_scores_gone(/' --mutation 's/None if k < lookback or /None if k < lookback - 1 or /' -- uv run pytest 'tests/test_alpha_b3.py::test_momentum_scores_read_the_close_lookback_back_and_none_where_either_is_missing' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def momentum_scores(/def momentum_scores_gone(/' --mutation 's/^    _check_window("lookback", lookback)$/    pass/' -- uv run pytest 'tests/test_alpha_b3.py::test_momentum_scores_refuse_a_lookback_below_2[one]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def momentum_scores(/def momentum_scores_gone(/' --mutation 's/^    _check_window("lookback", lookback)$/    pass/' -- uv run pytest 'tests/test_alpha_b3.py::test_momentum_scores_refuse_a_lookback_below_2[zero]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def momentum_scores(/def momentum_scores_gone(/' --mutation 's/^    _check_window("lookback", lookback)$/    pass/' -- uv run pytest 'tests/test_alpha_b3.py::test_momentum_scores_refuse_a_lookback_below_2[a-float]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def centred_ranks(/def centred_ranks_gone(/' --mutation 's/^        rank = (i + j + 2) \/ 2$/        rank = i + 1/' -- uv run pytest 'tests/test_alpha_b3.py::test_centred_ranks_run_from_the_weakest_at_minus_1_to_the_strongest_at_plus_1_ties_at_their_average' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def centred_ranks(/def centred_ranks_gone(/' --mutation 's/out\[asset\] = (2 \* rank - (n + 1)) \/ (n - 1)/out[asset] = (2 * rank - n) \/ (n - 1)/' -- uv run pytest 'tests/test_alpha_b3.py::test_centred_ranks_run_from_the_weakest_at_minus_1_to_the_strongest_at_plus_1_ties_at_their_average' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def centred_ranks(/def centred_ranks_gone(/' --mutation 's/order = sorted(scores, key=scores\.__getitem__)/order = sorted(scores, key=scores.__getitem__, reverse=True)/' -- uv run pytest 'tests/test_alpha_b3.py::test_centred_ranks_run_from_the_weakest_at_minus_1_to_the_strongest_at_plus_1_ties_at_their_average' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def centred_ranks(/def centred_ranks_gone(/' --mutation 's/^    if n < 2:$/    if n < 1:/' -- uv run pytest 'tests/test_alpha_b3.py::test_centred_ranks_refuse_fewer_than_2_scores' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/weights\[a\] \* (1 + strength \* z\[a\])/weights[a] * (1 - strength * z[a])/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/^    scale = math\.fsum(weights\[a\] for a in longs) \/ math\.fsum(raw\.values())$/    scale = 1.0/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/z = centred_ranks({a: scores\[a\] for a in basket})/z = centred_ranks({a: scores[a] for a in longs})/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/raw = {a: weights\[a\] \* (1 + strength \* z\[a\]) for a in longs}/raw = {a: weights[a] * (1 + strength * z[a]) for a in basket}/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/and directions\[a\] > 0\]/and directions[a] >= 0]/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/return weights | {a: w \* scale for a, w in raw\.items()}, len(basket), len(longs)/return weights | {a: w * scale for a, w in raw.items()}, len(basket), len(basket)/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/^    if len(basket) < floor:$/    if len(basket) <= floor:/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_engages_at_a_basket_of_8_and_not_at_7[eight-in-the-basket]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/^    if len(basket) < floor:$/    if len(basket) < floor - 1:/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_engages_at_a_basket_of_8_and_not_at_7[seven-in-the-basket]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/and directions\[a\] > 0\]/and directions[a] >= 0]/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_leaves_a_basket_with_fewer_than_2_longs_untilted[one-asset-long]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/ if directions\[a\] is not None and directions\[a\] > 0\]/ if directions[a] > 0]/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_leaves_a_basket_with_fewer_than_2_longs_untilted[a-direction-missing]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/^    if len(longs) < 2:$/    if len(longs) < 1:/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_leaves_a_basket_with_fewer_than_2_longs_untilted[one-asset-long]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/if w > 0 and scores\[a\] is not None\]/if w >= 0 and scores[a] is not None]/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_no_asset_without_a_weight_or_a_score' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def rank_tilt(/def rank_tilt_gone(/' --mutation 's/if w > 0 and scores\[a\] is not None\]/if w > 0]/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_tilt_ranks_no_asset_without_a_weight_or_a_score' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/        max_leverage=config\.max_leverage,/        max_leverage=2.0,/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_at_strength_0_is_a2s_book_to_the_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/^        weights\.append(tilted)$/        weights.append(untilted)/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_is_a2s_book_on_the_tilted_weights' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/^        ranked\.append(basket)$/        ranked.append(2)/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_is_a2s_book_on_the_tilted_weights' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/^        tilted_longs\.append(longs)$/        tilted_longs.append(2)/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_is_a2s_book_on_the_tilted_weights' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/^            floor=floor,$/            floor=5,/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_is_a2s_book_on_the_tilted_weights' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/momentum_scores(prices, lookback=score_lookback)/momentum_scores(prices, lookback=config.basket_lookback)/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_is_a2s_book_on_the_tilted_weights' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def momentum_scores(/def momentum_scores_gone(/' --mutation 's/None if k < lookback or prices\[k\] is None or prices\[k - lookback\] is None else prices\[k\] \/ prices\[k - lookback\] - 1/None if k < lookback or prices[k + 1] is None or prices[k + 1 - lookback] is None else prices[k + 1] \/ prices[k + 1 - lookback] - 1/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_at_close_k_reads_no_close_after_k' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/or not 0 <= strength < 1:/or not -1 <= strength < 1:/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_refuses_a_strength_outside_0_to_1[negative]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/or not 0 <= strength < 1:/or not 0 <= strength <= 1:/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_refuses_a_strength_outside_0_to_1[one]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/or not 0 <= strength < 1:/or strength < 0 or strength >= 1:/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_refuses_a_strength_outside_0_to_1[nan]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/ or isinstance(strength, bool) or / or /' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_refuses_a_strength_outside_0_to_1[a-bool]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/^    if not isinstance(config, A2Config):$/    if False:/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_refuses_a_config_that_is_no_a2_config' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/^    _check_window("score_lookback", score_lookback)$/    pass/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_refuses_a_score_lookback_below_2' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3.py --control 's/^def b3_book_returns(/def b3_book_returns_gone(/' --mutation 's/^    _check_window("floor", floor)$/    pass/' -- uv run pytest 'tests/test_alpha_b3.py::test_the_book_refuses_a_floor_below_2' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D3 gives the module: the score's arithmetic, its first defined index and its refusal on each of three lookbacks (rows 1–5); the ranks' averaging of ties, their scale and their order, and their refusal (rows 6–9); the tilt's sign, its rescale, the rank over the basket and not the longs, the multiplier on the longs and not the basket, the direction above 0, the longs' count returned, the floor from each side, the direction above 0 at a single long, the direction's presence, the longs below 2, and the basket's weight above 0 and score present (rows 10–22); the book's leverage cap, its weights the tilted ones, its basket sizes, its tilted counts, its floor, its score lookback, the score's look-ahead seen by the book, and each refusal (rows 23–36).
- [ ] **Step 7: Commit** — `feat(alpha): B3 trial 1's compute — the trailing momentum score, the centred ranks, the tilt of a close's long weights by their basket rank at a floor of names, and the A2 book on the tilted weights`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the trial subject, its pre-flight twin and the family key `B3` (D2–D8)

**Files:** Modify `cli/research/subjects.py`, `cli/registry/budget.py`, `tests/test_research_command.py`, `tests/test_trial_registry_provenance.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 1's `b3_book_returns`; `cli/research/subjects.py`'s `_capturing_union`, `_b2_over`, `close_grid`, `calendar_year_slices`, `_ffill_btc`, `_asset_returns`, `A2Config`, `_B2_A2_ARMS`, `_B2_LOOKBACK`, `PPY_4H`, `_B2_COST_PER_SIDE`, `_DECISIVE_START`, `_N_RESAMPLES`, `_b4_ensemble`, `_b4_limited`, `_b4_net`, `_b4_arm_a_bar`, `per_year_counts`, `per_year_positions_differ`, `per_year_turnover`, `per_year_max_drawdown`, `book_turnover`, `a1_kill_bar`, `net_of_cost_verdict`, `sharpe`, `max_drawdown`, `_B2_ARM_A_BAR_KEYS`, `_B2_ARM_A_BAR_FLAGS`, `_ASSETS`, `Subject`, `SubjectError`, `ObservedReader` and the error classes it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_b2_dataset`, `_b4_dataset`, `_B2_START`, `_B2_BARS`, `_B2_IN_2026`, `_B2_ASSETS`, `_B2_GRID`, `_B2_FULL_ANCHORS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_recording`, `_fake_kill_bar`, `_fake_head_to_head`, `_fake_benchmark`, `_anchor`, `_as_trial`, `_rolling_set`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`, `runner` and `app`. Produces the two subjects, the constants `_B3_SCORE_LOOKBACK`, `_B3_STRENGTH`, `_B3_FLOOR` and `_B3_N_TRIALS`, the halves `_b3_reads` and `_b3_inputs` and `_b3_engagement`, which Task 3's test reads, and the family key `B3`; the deflation row reads the count by name (`_DECLARED_COUNT`), and Task 5's literal reads it through the trial's `n_trials`.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - after the `from cli.alpha.b2 import (` block's closing `)` and before `from cli.alpha.b4 import`, `from cli.alpha.b3 import b3_book_returns`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, after its `assert subjects.SUBJECTS["b4-sol-noborrow-rolling-preflight"].metric_keys == _B4_SOL_PREFLIGHT_KEYS` line:

```python
    assert subjects.SUBJECTS["b3-rank-tilt"].metric_keys == _B3_METRIC_KEYS
    assert subjects.SUBJECTS["b3-rank-tilt-preflight"].metric_keys == _B3_PREFLIGHT_KEYS
```

  - after `test_a_b4_sol_subject_refuses_a_sol_btc_day_it_cannot_read_on_the_rolling_set_naming_the_pair_and_the_day` and before `def _ruled_signal(`, two blank lines either side:

```python
_B3_SPEC = "docs/specs/00147-b3-rank-tilt-design.md"
_B3_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the tilt moves no position at any stamp; no verdict, the "
    "trial unspent"
)
_B3_ARMS = ("20-50-100@0.12", "60-120-240@0.1", "60-120-240@0.12")
# Spec 00147 D8's keys, typed from the spec, never read off a subject.
_B3_ENGAGEMENT_KEYS = frozenset(
    {
        "tilt_first_engaged",
        "primary_returns",
        "stamps_positions_differ",
        "positions_differ_per_year",
        "tilted_per_year",
        "ranked_assets_histogram",
        "ranked_assets_mean",
        "turnover_b",
        "turnover_b_per_year",
        "limit_engaged_per_year",
        "arm_a_limit_engaged",
    }
)
_B3_METRIC_KEYS = _B3_ENGAGEMENT_KEYS | {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe_4h",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_passes",
    "spa_p_decisive_b30_s42",
    "spa_p_decisive_b30_s7",
    "spa_p_decisive_b30_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_primary",
    "head_to_head_spa_p_primary",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "turnover_a",
    "turnover_a_per_year",
}
_B3_PREFLIGHT_KEYS = _B2_FULL_ANCHORS | _ARM_A_BAR_KEYS | _B3_ENGAGEMENT_KEYS


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    assert (len(_B3_METRIC_KEYS), len(_B3_PREFLIGHT_KEYS)) == (44, 28)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B3_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b3_rank_tilt and trial.metric_keys == _B3_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b3_rank_tilt_verdict, _B3_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B3", 1) == ("B3", subjects._B3_N_TRIALS)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        f"{name}-preflight",
        (240,),
        _B2_ASSETS,
        _B3_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b3_rank_tilt_preflight and preflight.metric_keys == _B3_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5
    assert (subjects._B3_SCORE_LOOKBACK, subjects._B3_STRENGTH, subjects._B3_FLOOR) == (180, 0.5, 8)


# Adopting on every key the rule reads, the full window's head-to-head against it, so a rule reading the full window moves
# the adopt row.
_B3_ADOPTING = {
    "arm_a_passes": 1,
    "stamps_positions_differ": 3,
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
}


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="outperforms-significantly-from-the-first-engagement"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param({"stamps_positions_differ": 0}, None, id="no-position-ever-moved"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({"stamps_positions_differ": 0, "passes": 0}, None, id="engagement-read-before-passes"),
        pytest.param({"passes": 0}, "reject", id="arm-b-fails-its-bar"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="p-0.2"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001}, "reject", id="mean-negative"
        ),
    ],
)
def test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop(name, change, verdict):
    assert subjects.SUBJECTS[name].verdict({**_B3_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_reads_read_the_ten_4h_series_and_no_other_file(tmp_path, name):
    root = _b4_dataset(tmp_path)
    frames = {i: pl.read_parquet(root / "ohlc-test" / f"{i}/EUR/240.parquet") for i in _B2_ASSETS}
    union = sorted(set().union(*(frame["ts"].to_list() for frame in frames.values())))
    closes = {i: dict(zip(frame["ts"].to_list(), frame["close"].to_list())) for i, frame in frames.items()}
    reader = ObservedReader(root)

    h4_ts, h4_prices = subjects._b3_reads(name, reader, "ohlc-test", None, False)

    assert h4_ts == union and h4_prices == {i: [closes[i].get(t) for t in union] for i in _B2_ASSETS}
    assert set(reader.block()["ohlc-test"]["files"]) == {f"{i}/EUR/240.parquet" for i in _B2_ASSETS}


@pytest.mark.parametrize("name", ["b3-rank-tilt", "b3-rank-tilt-preflight"])
@pytest.mark.parametrize(
    ("start", "bars", "cause"),
    [
        pytest.param(
            _B2_START,
            1_382,
            "it holds 1381 return indices, and the kill bar's decisive window opens at index 1380 and needs 2",
            id="one-index-short",
        ),
        pytest.param(
            _B2_IN_2026,
            _B2_BARS,
            "none of its return indices closes in a calendar year the worst-slice leg reads",
            id="inside-2026",
        ),
    ],
)
def test_a_b3_subject_refuses_a_window_it_cannot_evaluate_before_any_book(tmp_path, monkeypatch, name, start, bars, cause):
    _anchor(monkeypatch, _b2_dataset(tmp_path, start=start))
    books = _recording(monkeypatch, "_b3_inputs", lambda arguments, result: result)
    end = start + timedelta(hours=4 * (bars - 1))
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-test", "--window", str(start), str(end)]

    result = runner.invoke(app, [*args, *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the window {start} .. {end}: {cause}" in result.output and books == []


def _b3_own_books(h4_ts: list[datetime], h4_prices: dict) -> dict:
    """The books of the reads, built here through `a2_book_returns`, `b3_book_returns` and the limits, never through the
    subject's halves."""
    n = len(h4_ts) - 1
    fed = _ffill_btc(h4_prices)
    configs = [
        A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
        for lb, tv in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    ]

    def mean(books):
        return {i: [statistics.mean(book[i][k] for book in books) for k in range(n)] for i in fed}

    def limited(positions):
        factors, engaged = limit_factors(dict(positions))
        return {i: [p * f for p, f in zip(v, factors)] for i, v in positions.items()}, engaged

    tilted = [b3_book_returns(fed, config=c, score_lookback=180, strength=0.5, floor=8) for c in configs]
    return {
        "limited_a": limited(mean([a2_book_returns(fed, config=c)["asset_positions"] for c in configs])),
        "limited_b": limited(mean([book["asset_positions"] for book in tilted])),
        "ranked": dict(zip(_B3_ARMS, (book["ranked"] for book in tilted), strict=True)),
        "tilted": dict(zip(_B3_ARMS, (book["tilted"] for book in tilted), strict=True)),
        "returns": {a: _asset_returns(fed[a]) for a in h4_prices},
    }


def _b3_short_reads(n: int = 480) -> tuple[list[datetime], dict]:
    """A 480-stamp union of the ten assets, BTC missing one stamp, SOL listing at 250 and AVAX at 330: the basket holds
    exactly 8 from return index 180 to 429 and 9 after it."""
    h4_ts = [datetime(2017, 1, 1, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n)]
    h4_prices = {
        a: [
            10.0 * (i + 1) * (1 + 0.0004 * (i % 4 + 1)) ** k * (1 + (0.04 + 0.01 * (i % 5)) * math.sin(k / (5 + i) + 0.7 * i))
            for k in range(n)
        ]
        for i, a in enumerate(_B2_ASSETS)
    }
    h4_prices["BTC"][300] = None
    h4_prices["SOL"][:250] = [None] * 250
    h4_prices["AVAX"][:330] = [None] * 330
    return h4_ts, h4_prices


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_arms_agree_bit_for_bit_until_the_tilt_first_moves_a_position(monkeypatch, name):
    reads = _b3_short_reads()
    n = len(reads[0]) - 1
    untilted = _recording(monkeypatch, "_b4_ensemble", lambda arguments, result: result)
    tilted = _recording(monkeypatch, "_b3_ensemble", lambda arguments, result: result)

    inputs = subjects._b3_inputs(reads)

    ((_, raw_a),), ((_, (raw_b, _, longs)),) = untilted, tilted
    differ = [k for k in range(n) if any(raw_b[a][k] != raw_a[a][k] for a in raw_a)]
    first_tilted = min(next(k for k, c in enumerate(counts) if c) for counts in longs.values())
    assert differ and first_tilted <= differ[0] == subjects._b3_first_engaged(inputs) < n - 2
    assert all(raw_b[a][:first_tilted] == raw_a[a][:first_tilted] for a in raw_a)


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits(name):
    reads = _b3_short_reads()
    own = _b3_own_books(*reads)
    # The short union moves the tilt: each arm tilts 2 longs or more at some stamp, so arm B differs from arm A.
    assert all(max(counts) >= 2 for counts in own["tilted"].values()) and own["limited_b"][0] != own["limited_a"][0]

    inputs = subjects._b3_inputs(reads)

    assert (inputs.h4_ts, inputs.h4_prices, inputs.close) == (reads[0], reads[1], [t + timedelta(hours=4) for t in reads[0][:-1]])
    assert inputs.returns == own["returns"] and (inputs.ranked, inputs.tilted) == (own["ranked"], own["tilted"])
    assert (inputs.arm_a, inputs.engaged_a) == own["limited_a"] and (inputs.arm_b, inputs.engaged_b) == own["limited_b"]


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_inputs_pass_both_arms_through_the_limits(monkeypatch, name):
    reads = _b3_short_reads()
    untilted = _recording(monkeypatch, "_b4_ensemble", lambda arguments, result: result)
    tilted = _recording(monkeypatch, "_b3_ensemble", lambda arguments, result: result)
    # A factor below 1 at every bar, so a book the limits never scale keeps its raw positions and fails the comparison.
    _recording(monkeypatch, "limit_factors", lambda arguments, result: ([0.5] * len(result[0]), result[1]))

    inputs = subjects._b3_inputs(reads)

    ((_, raw_a),), ((_, (raw_b, _, _)),) = untilted, tilted
    halved = [{i: [p * 0.5 for p in v] for i, v in book.items()} for book in (raw_a, raw_b)]
    assert [inputs.arm_a, inputs.arm_b] == halved


def _b3_built_inputs(n: int = 1_400) -> subjects._B3Inputs:
    """Books made by hand over `n` return indices — three assets, arm B moving ETH down from index 200, SOL from 300 and BTC
    up from 400, each limit engaged at a stamp of its own, each arm's basket sizes and tilted closes a pattern of its own —
    for the metrics alone."""
    h4_ts = [datetime(2016, 6, 1, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n + 1)]

    def wave(k: int, phase: float, depth: float) -> float:
        return depth * (1 + math.sin(k / 11 + phase)) / 2

    arm_a = {a: [wave(k, i, 0.2) for k in range(n)] for i, a in enumerate(("BTC", "ETH", "SOL"))}
    moved = {"ETH": (200, lambda k: 0.8), "SOL": (300, lambda k: 1 + 0.3 * math.sin(k / 7)), "BTC": (400, lambda k: 1.1)}
    arm_b = {a: [p if k < moved[a][0] else p * moved[a][1](k) for k, p in enumerate(v)] for a, v in arm_a.items()}
    returns = {a: [0.01 * math.sin(k / (3 + j) + j) for k in range(n)] for j, a in enumerate(arm_a)}
    returns["ETH"][207] = None
    engaged_a = {limit: [False] * n for limit in ("gross", "net", "margin")}
    engaged_b = {limit: [k == 900 + j for k in range(n)] for j, limit in enumerate(("gross", "net", "margin"))}
    ranked = {arm: [(k * (j + 1)) % 4 for k in range(n)] for j, arm in enumerate(_B3_ARMS)}
    tilted = {arm: [2 * ((k + j) % 2) for k in range(n)] for j, arm in enumerate(_B3_ARMS)}
    h4_prices = {"BTC": [100.0 + k for k in range(n + 1)]}
    close = [t + timedelta(hours=4) for t in h4_ts[:-1]]
    return subjects._B3Inputs(h4_ts, h4_prices, close, returns, arm_a, arm_b, engaged_a, engaged_b, ranked, tilted)


def _b3_own_net(inputs: subjects._B3Inputs, positions: dict, stress: float) -> list[float]:
    """Net of each asset's turnover at 0.006 a side times `stress`: a long-only book borrows nothing."""
    return net_of_cost(positions, {i: inputs.returns[i] for i in positions}, cost_per_side=stress * 0.006)


def _b3_own_engagement(inputs: subjects._B3Inputs) -> dict:
    close, n = inputs.close, len(inputs.close)
    start = next(k for k in range(n) if any(inputs.arm_b[a][k] != inputs.arm_a[a][k] for a in inputs.arm_a))
    differ = per_year_positions_differ(inputs.arm_a, inputs.arm_b, close)
    return {
        "tilt_first_engaged": start,
        "primary_returns": n - start,
        "stamps_positions_differ": sum(differ.values()),
        "positions_differ_per_year": differ,
        "tilted_per_year": {arm: per_year_counts([c > 0 for c in counts], close) for arm, counts in inputs.tilted.items()},
        "ranked_assets_histogram": {arm: {str(m): counts.count(m) for m in range(4)} for arm, counts in inputs.ranked.items()},
        "ranked_assets_mean": {arm: statistics.fmean(counts) for arm, counts in inputs.ranked.items()},
        "turnover_b": book_turnover(inputs.arm_b),
        "turnover_b_per_year": per_year_turnover(inputs.arm_b, close),
        "limit_engaged_per_year": {limit: per_year_counts(flags, close) for limit, flags in inputs.engaged_b.items()},
        "arm_a_limit_engaged": {limit: sum(flags) for limit, flags in inputs.engaged_a.items()},
    }


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_trial_reads_each_metric_from_its_own_call(monkeypatch, name):
    inputs = _b3_built_inputs()
    close, start = inputs.close, 200
    net_a, net_b = (_b3_own_net(inputs, book, 1.0) for book in (inputs.arm_a, inputs.arm_b))
    net_a_x15, net_b_x15 = (_b3_own_net(inputs, book, 1.5) for book in (inputs.arm_a, inputs.arm_b))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b3_metrics(inputs, n_trials=1)

    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    common = {"n_trials": 1, "var_trials": 0.0, "benchmark_net_returns": bench, "decisive_start": 1380, "n_resamples": 2000}
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
    ]
    bar_a, headline = bars[0][1], bars[1][1]
    full, primary = (result for _, result in heads)
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
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "turnover_a": book_turnover(inputs.arm_a),
        "turnover_a_per_year": per_year_turnover(inputs.arm_a, close),
        **_b3_own_engagement(inputs),
    }
    assert (metrics["tilt_first_engaged"], metrics["primary_returns"]) == (200, 1_200)


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_trial_refuses_fewer_than_2_returns_from_the_tilts_first_engagement_before_any_bar(monkeypatch, name):
    built = _b3_built_inputs()
    n = len(built.close)

    def moved_from(k: int) -> dict:
        return {a: [*built.arm_a[a][:k], *(p + 0.01 for p in built.arm_a[a][k:])] for a in built.arm_a}

    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    for refused, never in ((1, False), (0, True)):
        with pytest.raises(ValidationError) as caught:
            subjects._b3_metrics(built._replace(arm_b=built.arm_a if never else moved_from(n - refused)), n_trials=1)
        assert str(caught.value) == (
            f"{refused} of its return indices follow the tilt's first engagement, and the head-to-head from it needs 2"
        )
    assert bars == []
    admitted = subjects._b3_metrics(built._replace(arm_b=moved_from(n - 2)), n_trials=1)
    assert (admitted["tilt_first_engaged"], admitted["primary_returns"]) == (n - 2, 2)


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
def test_the_b3_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book(monkeypatch, name):
    inputs = _b3_built_inputs()
    net_a = _b3_own_net(inputs, inputs.arm_a, 1.0)

    def refused(*args, **kwargs):
        raise AssertionError("the pre-flight read a head-to-head")

    monkeypatch.setattr(subjects, "net_of_cost_verdict", refused)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    costed = _recording(monkeypatch, "_b4_net", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b3_preflight_metrics(inputs, n_trials=1)

    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    ((arguments, bar),) = bars
    assert costed and all(arguments["positions"] is inputs.arm_a for arguments, _ in costed)
    assert arguments["book_net_returns"] == net_a and arguments["n_trials"] == 1
    turnover_a = book_turnover(inputs.arm_a)
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / len(inputs.close) * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        **_b3_own_engagement(inputs),
    }


@pytest.mark.parametrize("name", ["b3-rank-tilt", "b3-rank-tilt-preflight"])
def test_a_b3_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
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


@pytest.mark.parametrize("name", ["b3-rank-tilt"])
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_the_b3_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b3_reads", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-192", "--family", "B3", "--n-trials", "2"]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials 2 is not 1, the count {name} declares and deflates at: pass --n-trials 1"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []
```

  - `_RULED_FIXTURES` gains `"b3-rank-tilt": _b2_dataset,` after `"b2-ratio-derisk": _b2_overlay_dataset,`; `_DECLARED_COUNT` gains `"b3-rank-tilt": "_B3_N_TRIALS",` after `"b2-ratio-derisk": "_B2_RATIO_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b3-rank-tilt": ("B3", 1),` after `"b2-ratio-derisk": ("B2", 3),`; `_CONTRACT_DATASETS` gains, after its `"b4-sol-noborrow-rolling-preflight"` entry:

```python
    "b3-rank-tilt": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
    "b3-rank-tilt-preflight": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
```

  - in `tests/test_trial_registry_provenance.py`, `test_the_budgets_and_buckets_are_the_master_plans_literals`' `assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "B4": "B", "P1": None}, growth` becomes `assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "B3": "B", "B4": "B", "P1": None}, growth`.

  **Author's call** — each half on the fixture that moves it, every case but the shared rows in seconds, so each is a probe's target: the declaration, its key counts typed from the spec; the rule row by row on `_B3_ADOPTING`, whose full-window pair stands against the verdict; the reads on `_b4_dataset`, whose two ratio files the reads must leave unread, the union and every close held to the files', the block to the ten EUR files; the two window refusals on `_b2_dataset` from each side of the evaluable window, through the command, before any book, for both subjects; the books on `_b3_short_reads`, a 480-stamp union of the ten assets the reads would refuse, its BTC missing one stamp, SOL listing at 250 and AVAX at 330, so the basket holds exactly 8 from return index 180 to 429 and 9 after — a floor read off 9 starts the tilt elsewhere — the bit-identity read off the two ensembles the inputs build, the first differing position at or after every arm's first tilted close and equal to `_b3_first_engaged`, and every field of `_b3_inputs` held to `_b3_own_books`, the test's own build through `a2_book_returns`, `b3_book_returns` and `limit_factors`, never the subject's halves; the limits' wiring with the factor rewritten at every bar, so a book the limits never scale is seen; the metrics and the pre-flight's on `_b3_built_inputs`, books made by hand over 1,400 return indices — arm B moving ETH first, at 200, then SOL and BTC, so a first engagement read off every asset or off one side is seen, each limit engaged at a stamp of its own, each arm's basket sizes and tilted counts a pattern of its own — under argument-derived stand-ins for the bar, the head-to-head and the benchmark, every call's arguments and every key held to `_b3_own_net` and `_b3_own_engagement`, the test's own expressions; the refusal bound from both sides, and at a dead knob; the count and the plain eval refused before any read; `--as-of` refused before any read. Every new function is parametrised by the subject's name, so `tests/retired_subjects.py`'s hook marks each case `retired` once a later branch retires the two names. The shared rows — the contract, tracked-spec, shared-defaults and deflation rows, which `_RULED_FIXTURES`, `_DECLARED_COUNT` and `_CONTRACT_DATASETS` reach — run both subjects end to end on `_b2_dataset`, the trial's arm B and bars among them.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00147 && uv run pytest tests/test_research_command.py -k "b3_ or ruled_subjects_declare or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt`: collection completes and every selected case fails at its call — on a key `SUBJECTS` lacks, a name `subjects` lacks or a subject the CLI does not know (measured on Task 1's tree: `28 failed, 877 deselected`); and `mkdir -p .tmp/plan-00147 && uv run pytest tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt`, measured `1 failed`.
- [ ] **Step 3: Implement in `cli/research/subjects.py` and `cli/registry/budget.py`** — after the `from cli.alpha.b2 import (` block's closing `)` and before `from cli.alpha.b4 import (`:

```python
from cli.alpha.b3 import b3_book_returns
```

  after `_B4_SOL_PREFLIGHT_KEYS`' closing `)` and before `SUBJECTS: dict[str, Subject] = {`, two blank lines on each side:

```python
# docs/specs/00147 D2-D9: B3's trial 1, the adopted A2-4h ensemble's long weights tilted at each close by their rank in the
# basket on trailing momentum, on a frozen set's full history: trial 58's arm A, limits, costing and bar.
_B3_SCORE_LOOKBACK = 180  # docs/specs/00147 D3: M, the closes a momentum score spans; another value is a new trial
_B3_STRENGTH = 0.5  # docs/specs/00147 D3: k, the tilt's strength; another value is a new trial
_B3_FLOOR = 8  # docs/specs/00147 D3: the basket size below which no close tilts, master plan §3's ~8 names to rank
_B3_N_TRIALS = 1  # docs/specs/00147 D7: B3's true count with this trial, fixed by the spec's hash; another is a new subject


class _B3Inputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    returns: dict[str, list[float | None]]
    arm_a: dict[str, list[float]]
    arm_b: dict[str, list[float]]
    engaged_a: dict[str, list[bool]]
    engaged_b: dict[str, list[bool]]
    ranked: dict[str, list[int]]
    tilted: dict[str, list[int]]


def _b3_reads(
    subject: str, reader: ObservedReader, dataset: str, window: tuple[str, str] | None, accept_holes: bool
) -> tuple[list[datetime], dict[str, list[float | None]]]:
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
    return h4_ts, h4_prices


def _b3_ensemble(
    prices: dict[str, list[float | None]],
) -> tuple[dict[str, list[float]], dict[str, list[int]], dict[str, list[int]]]:
    """`_b4_ensemble` with each arm's book tilted; each arm's basket size and count of longs tilted per close, keyed by the
    arm."""
    books = {
        f"{'-'.join(map(str, lookbacks))}@{target_vol}": b3_book_returns(
            prices,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_B2_LOOKBACK,
                basket_lookback=_B2_LOOKBACK,
                periods_per_year=PPY_4H,
            ),
            score_lookback=_B3_SCORE_LOOKBACK,
            strength=_B3_STRENGTH,
            floor=_B3_FLOOR,
        )
        for lookbacks, target_vol in _B2_A2_ARMS
    }
    arms = [book["asset_positions"] for book in books.values()]
    positions = {i: [statistics.mean(arm[i][k] for arm in arms) for k in range(len(prices["BTC"]) - 1)] for i in prices}
    return positions, {arm: book["ranked"] for arm, book in books.items()}, {arm: book["tilted"] for arm, book in books.items()}


def _b3_inputs(reads: tuple[list[datetime], dict[str, list[float | None]]]) -> _B3Inputs:
    """Both arms' positions and the returns they are costed on, and no return of a book."""
    h4_ts, h4_prices = reads
    fed = _ffill_btc(h4_prices)
    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))
    raw_b, ranked, tilted = _b3_ensemble(fed)
    arm_b, engaged_b = _b4_limited(raw_b)
    returns = {a: _asset_returns(fed[a]) for a in h4_prices}
    return _B3Inputs(h4_ts, h4_prices, close_grid(h4_ts), returns, arm_a, arm_b, engaged_a, engaged_b, ranked, tilted)


def _b3_first_engaged(inputs: _B3Inputs) -> int:
    """The first return index at which arm B's positions differ from arm A's, the length when none does."""
    n = len(inputs.close)
    return next((k for k in range(n) if any(inputs.arm_b[a][k] != inputs.arm_a[a][k] for a in inputs.arm_a)), n)


def _b3_engagement(inputs: _B3Inputs) -> dict:
    close, start = inputs.close, _b3_first_engaged(inputs)
    differ = per_year_positions_differ(inputs.arm_a, inputs.arm_b, close)
    return {
        "tilt_first_engaged": start,
        "primary_returns": len(close) - start,
        "stamps_positions_differ": sum(differ.values()),
        "positions_differ_per_year": differ,
        "tilted_per_year": {arm: per_year_counts([c > 0 for c in counts], close) for arm, counts in inputs.tilted.items()},
        "ranked_assets_histogram": {
            arm: {str(m): counts.count(m) for m in range(len(inputs.arm_a) + 1)} for arm, counts in inputs.ranked.items()
        },
        "ranked_assets_mean": {arm: statistics.fmean(counts) for arm, counts in inputs.ranked.items()},
        "turnover_b": book_turnover(inputs.arm_b),
        "turnover_b_per_year": per_year_turnover(inputs.arm_b, close),
        "limit_engaged_per_year": {name: per_year_counts(flags, close) for name, flags in inputs.engaged_b.items()},
        "arm_a_limit_engaged": {name: sum(flags) for name, flags in inputs.engaged_a.items()},
    }


def _b3_metrics(inputs: _B3Inputs, *, n_trials: int) -> dict:
    close, start = inputs.close, _b3_first_engaged(inputs)
    if len(close) - start < 2:
        raise ValidationError(
            f"{len(close) - start} of its return indices follow the tilt's first engagement, and the head-to-head from it needs 2"
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
    for label, first in (("full", 0), ("primary", start)):
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
        **_b3_engagement(inputs),
    }


def _b3_preflight_metrics(inputs: _B3Inputs, *, n_trials: int) -> dict:
    """Arm A's anchors and bar and the engagement: no return of arm B."""
    bar, net_a, bench = _b4_arm_a_bar(inputs, n_trials=n_trials)
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
        **_b3_engagement(inputs),
    }


def _b3_build(
    subject: str,
    compute: Callable[..., dict],
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
        return compute(_b3_inputs(_b3_reads(subject, reader, dataset, window, accept_holes)), n_trials=_B3_N_TRIALS)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, RiskError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b3_rank_tilt(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b3_build("b3-rank-tilt", _b3_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b3_rank_tilt_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b3_build("b3-rank-tilt-preflight", _b3_preflight_metrics, reader, dataset, window, as_of, accept_holes)


# docs/specs/00147 D7's matrix and the two instrument findings its metrics show: a change to it is a new spec and a new
# trial, never an edit here.
def _b3_rank_tilt_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not m["stamps_positions_differ"]:
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"


# docs/specs/00147 D8's keys: the engagement both subjects carry, the trial's and the pre-flight's.
_B3_ENGAGEMENT_KEYS = frozenset(
    {
        "tilt_first_engaged",
        "primary_returns",
        "stamps_positions_differ",
        "positions_differ_per_year",
        "tilted_per_year",
        "ranked_assets_histogram",
        "ranked_assets_mean",
        "turnover_b",
        "turnover_b_per_year",
        "limit_engaged_per_year",
        "arm_a_limit_engaged",
    }
)
_B3_METRIC_KEYS = _B3_ENGAGEMENT_KEYS | {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe_4h",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_passes",
    "spa_p_decisive_b30_s42",
    "spa_p_decisive_b30_s7",
    "spa_p_decisive_b30_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_primary",
    "head_to_head_spa_p_primary",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "turnover_a",
    "turnover_a_per_year",
}
_B3_PREFLIGHT_KEYS = (
    _B2_ARM_A_BAR_KEYS
    | _B3_ENGAGEMENT_KEYS
    | {
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown_full",
        "turnover_a",
        "arm_a_spot_drag_pct_yr",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    }
)
```

  `SUBJECTS` gains, after its `"b4-sol-noborrow-rolling-preflight"` entry and before its closing `}`:

```python
    "b3-rank-tilt": Subject(
        "b3-rank-tilt",
        (240,),
        _ASSETS,
        _build_b3_rank_tilt,
        spec="docs/specs/00147-b3-rank-tilt-design.md",
        metric_keys=_B3_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b3_rank_tilt_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the tilt moves no position at any stamp; no "
            "verdict, the trial unspent"
        ),
        family="B3",
        n_trials=_B3_N_TRIALS,
    ),
    "b3-rank-tilt-preflight": Subject(
        "b3-rank-tilt-preflight",
        (240,),
        _ASSETS,
        _build_b3_rank_tilt_preflight,
        spec="docs/specs/00147-b3-rank-tilt-design.md",
        metric_keys=_B3_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
```

  and in `cli/registry/budget.py`, `BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "B4": "B", "P1": None}` becomes `BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "B3": "B", "B4": "B", "P1": None}`, its comment unchanged (spec 00147 D8: a new family joins with its bucket in a reviewed pull request quoting the ruling, the owner's "B3 (Recommended)").
- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` , over a history that runs past 2026-03-31) or `b4-sol-noborrow-rolling-preflight` ( `` becomes `` , over a history that runs past 2026-03-31), `b4-sol-noborrow-rolling-preflight` ( ``, and the row's closing `` with no return of the eleven-instrument book; it has no rule, so its run is kept with `--reading`). | `` becomes:

```markdown
with no return of the eleven-instrument book; it has no rule, so its run is kept with `--reading`), `b3-rank-tilt` (the A2 4h ensemble against the same three arms with each arm's inverse-vol weights of the assets it holds long tilted at each 4h close by their rank, among every weighted asset, on the trailing 30-day return, the strongest up by half and the weakest down by half, their sum kept, at the closes where 8 assets or more rank; the 4h series of `--dataset`, a frozen set only) or `b3-rank-tilt-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar, and the ranked assets, tilted closes, positions and turnover of the tilt and the limits it engages, with no return of the tilted book; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the shared rows measured at 10 s or more in the scratch worktree on Task 2's tree (call time: the shared-defaults rows 34.98 s and 29.32 s, the evaluate rows 17.75 s and 14.65 s, the deflation row 15.17 s):

```text
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b3-rank-tilt]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-rank-tilt-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-rank-tilt-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b3-rank-tilt-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b3-rank-tilt]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's two commands, measured `28 passed, 895 deselected` (about 9 s) and `1 passed`; then the shared rows, `mkdir -p .tmp/plan-00147 && uv run pytest tests/test_research_command.py -k "b3-rank-tilt and not b3_" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt`, one plain blocking call, `timeout` 600000 ms (measured `19 passed, 904 deselected in 114.86s`, every row but the five step 5 lists under 1 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py cli/registry/budget.py tests/test_research_command.py tests/test_trial_registry_provenance.py README.md tests/slow-cases.txt`; the Global Constraints' list over the six paths in its four parts (measured on Task 2's tree in the scratch worktree: `510 passed, 413 deselected in 215.21s`, `227 passed, 696 deselected in 314.68s`, `71 passed, 852 deselected in 91.16s`; the other forty-two direct readers `4282 passed, 76 deselected in 124.72s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured in the scratch worktree on Task 2's tree, 63 of 63); the metric-keys lines, the ruled-subjects literal and the contract, shared-defaults, deflation and tracked-spec rows are new rows of existing tests, not new guards, and are not probed; the budgets literal is the guard this task changes, and its row is the block's last:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/^_B3_N_TRIALS = 1\b/_B3_N_TRIALS = 2/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/"b3-rank-tilt-preflight": Subject(/,/^    ),/s/metric_keys=_B3_PREFLIGHT_KEYS,/metric_keys=_B3_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/"b3-rank-tilt": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/"b3-rank-tilt": Subject(/,/^    ),/s/00147-b3-rank-tilt-design/00146-b4-sol-noborrow-rolling-design/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/"b3-rank-tilt": Subject(/,/^    ),/s/verdict=_b3_rank_tilt_verdict,/verdict=_b4_ratio_legs_verdict,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/"b3-rank-tilt": Subject(/,/^    ),/s/family="B3",/family="B4",/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/^_B3_SCORE_LOOKBACK = 180 /_B3_SCORE_LOOKBACK = 120 /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/^_B3_STRENGTH = 0\.5 /_B3_STRENGTH = 0.25 /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/^_B3_FLOOR = 8 /_B3_FLOOR = 9 /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^_B3_ENGAGEMENT_KEYS = /,/^)/s/^        "ranked_assets_mean",$/        "ranked_assets_means",/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_rank_tilt_verdict(/,/^_B3_ENGAGEMENT_KEYS/s/"adopt" if m\["head_to_head_spa_p_primary"\] < 0\.05 else "park"/"park"/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[outperforms-significantly-from-the-first-engagement-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not m\["stamps_positions_differ"\]:/if not m["stamps_positions_differ"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-a-fails-its-bar-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not m\["stamps_positions_differ"\]:/if not m["arm_a_passes"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[no-position-ever-moved-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not m\["stamps_positions_differ"\]:/if not m["stamps_positions_differ"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-a-read-before-passes-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not m\["stamps_positions_differ"\]:/if not m["arm_a_passes"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[engagement-read-before-passes-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_rank_tilt_verdict(/,/^_B3_ENGAGEMENT_KEYS/s/    if not m\["passes"\]:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-b-fails-its-bar-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_rank_tilt_verdict(/,/^_B3_ENGAGEMENT_KEYS/s/m\["head_to_head_spa_p_primary"\] < 0\.05/m["head_to_head_spa_p_primary"] <= 0.05/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[p-at-exactly-0.05-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_rank_tilt_verdict(/,/^_B3_ENGAGEMENT_KEYS/s/"adopt" if m\["head_to_head_spa_p_primary"\] < 0\.05 else "park"/"adopt"/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[p-0.2-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_rank_tilt_verdict(/,/^_B3_ENGAGEMENT_KEYS/s/    if m\["head_to_head_mean_outperf_primary"\] > 0:$/    if m["head_to_head_mean_outperf_primary"] >= 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-at-exactly-0-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_rank_tilt_verdict(/,/^_B3_ENGAGEMENT_KEYS/s/    if m\["head_to_head_mean_outperf_primary"\] > 0:$/    if m["head_to_head_mean_outperf_full"] > 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-negative-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_reads(/def _b3_reads_gone(/' --mutation '/^def _b3_reads(/,/^def /s/_capturing_union(reader, dataset, 240, window, None, accept_holes)/_capturing_union(reader, dataset, 1440, window, None, accept_holes)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_reads_read_the_ten_4h_series_and_no_other_file[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_reads(/def _b3_reads_gone(/' --mutation '/^def _b3_reads(/,/^def /s/    if len(close) < _DECISIVE_START + 2:/    if len(close) < _DECISIVE_START + 1:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_a_window_it_cannot_evaluate_before_any_book[one-index-short-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_reads(/def _b3_reads_gone(/' --mutation '/^def _b3_reads(/,/^def /s/    if len(close) < _DECISIVE_START + 2:/    if len(close) < _DECISIVE_START + 1:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_a_window_it_cannot_evaluate_before_any_book[one-index-short-b3-rank-tilt-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_reads(/def _b3_reads_gone(/' --mutation '/^def _b3_reads(/,/^def /s/    if not calendar_year_slices(\[0\.0\] \* len(close), h4_ts):/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_a_window_it_cannot_evaluate_before_any_book[inside-2026-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_reads(/def _b3_reads_gone(/' --mutation '/^def _b3_reads(/,/^def /s/    if not calendar_year_slices(\[0\.0\] \* len(close), h4_ts):/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_a_window_it_cannot_evaluate_before_any_book[inside-2026-b3-rank-tilt-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_inputs(/def _b3_inputs_gone(/' --mutation '/^def _b3_inputs(/,/^def /s/    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))/    arm_a, engaged_a = _b4_limited(_b3_ensemble(fed)[0])/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_arms_agree_bit_for_bit_until_the_tilt_first_moves_a_position[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_inputs(/def _b3_inputs_gone(/' --mutation '/^def _b3_inputs(/,/^def /s/    fed = _ffill_btc(h4_prices)/    fed = dict(h4_prices)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_inputs(/def _b3_inputs_gone(/' --mutation '/^def _b3_inputs(/,/^def /s/    returns = {a: _asset_returns(fed\[a\]) for a in h4_prices}/    returns = {a: _asset_returns(h4_prices[a]) for a in h4_prices}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_ensemble(/def _b3_ensemble_gone(/' --mutation '/^def _b3_ensemble(/,/^def /s/statistics\.mean(arm\[i\]\[k\] for arm in arms) for k in range(len(prices\[.BTC.\]) - 1)/statistics.mean(arm[i][k] for arm in arms[:2]) for k in range(len(prices["BTC"]) - 1)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_ensemble(/def _b3_ensemble_gone(/' --mutation 's/^        f"{.-.\.join(map(str, lookbacks))}@{target_vol}": b3_book_returns(/        f"{lookbacks}": b3_book_returns(/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_ensemble(/def _b3_ensemble_gone(/' --mutation 's/^            score_lookback=_B3_SCORE_LOOKBACK,/            score_lookback=120,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_ensemble(/def _b3_ensemble_gone(/' --mutation 's/^            strength=_B3_STRENGTH,/            strength=0.25,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_ensemble(/def _b3_ensemble_gone(/' --mutation 's/^            floor=_B3_FLOOR,/            floor=9,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_ensemble(/def _b3_ensemble_gone(/' --mutation 's/{arm: book\["tilted"\] for arm, book in books\.items()}/{arm: book["ranked"] for arm, book in books.items()}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_ensemble(/def _b3_ensemble_gone(/' --mutation '/^def _b3_ensemble(/,/^def /s/                basket_lookback=_B2_LOOKBACK,/                basket_lookback=120,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_build_arm_a_untilted_and_arm_b_tilted_each_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_inputs(/def _b3_inputs_gone(/' --mutation '/^def _b3_inputs(/,/^def /s/^    arm_b, engaged_b = _b4_limited(raw_b)$/    arm_b, engaged_b = raw_b, _b4_limited(raw_b)[1]/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_inputs_pass_both_arms_through_the_limits[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_first_engaged(/def _b3_first_engaged_gone(/' --mutation 's/return next((k for k in range(n) if any(inputs\.arm_b\[a\]\[k\] != inputs\.arm_a\[a\]\[k\] for a in inputs\.arm_a)), n)/return next((k for k in range(n) if all(inputs.arm_b[a][k] != inputs.arm_a[a][k] for a in inputs.arm_a)), n)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_first_engaged(/def _b3_first_engaged_gone(/' --mutation 's/return next((k for k in range(n) if any(inputs\.arm_b\[a\]\[k\] != inputs\.arm_a\[a\]\[k\] for a in inputs\.arm_a)), n)/return next((k for k in range(n) if any(inputs.arm_b[a][k] > inputs.arm_a[a][k] for a in inputs.arm_a)), n)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_engagement(/def _b3_engagement_gone(/' --mutation 's/"primary_returns": len(close) - start,/"primary_returns": len(close) - start - 1,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_engagement(/def _b3_engagement_gone(/' --mutation 's/for arm, counts in inputs\.tilted\.items()},/for arm, counts in inputs.ranked.items()},/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_engagement(/def _b3_engagement_gone(/' --mutation 's/for m in range(len(inputs\.arm_a) + 1)}/for m in range(len(inputs.arm_a))}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_engagement(/def _b3_engagement_gone(/' --mutation 's/"ranked_assets_mean": {arm: statistics\.fmean(counts)/"ranked_assets_mean": {arm: max(counts)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_engagement(/def _b3_engagement_gone(/' --mutation 's/"turnover_b": book_turnover(inputs\.arm_b),/"turnover_b": book_turnover(inputs.arm_a),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_engagement(/def _b3_engagement_gone(/' --mutation 's/    differ = per_year_positions_differ(inputs\.arm_a, inputs\.arm_b, close)/    differ = per_year_positions_differ(inputs.arm_b, inputs.arm_b, close)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_engagement(/def _b3_engagement_gone(/' --mutation '/^def _b3_engagement(/,/^def /s/for name, flags in inputs\.engaged_b\.items()},/for name, flags in inputs.engaged_a.items()},/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/    for label, first in (("full", 0), ("primary", start)):/    for label, first in (("full", 0), ("primary", 0)):/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/    net_b = _b4_net(inputs\.arm_b, inputs\.returns, stress=1\.0)/    net_b = _b4_net(inputs.arm_a, inputs.returns, stress=1.0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/    net_b_x15 = _b4_net(inputs\.arm_b, inputs\.returns, stress=1\.5)/    net_b_x15 = _b4_net(inputs.arm_b, inputs.returns, stress=1.0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/"arm_a_passes": int(bar_a\["passes"\]),/"arm_a_passes": int(headline["passes"]),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/"spa_p_full": headline\["spa_p_value_full"\],/"spa_p_full": headline["spa_p_value"],/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/"arm_a_max_drawdown": max_drawdown(net_a),/"arm_a_max_drawdown": max_drawdown(net_b),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/    bar_a, net_a, bench = _b4_arm_a_bar(inputs, n_trials=n_trials)/    bar_a, net_a, bench = _b4_arm_a_bar(inputs, n_trials=2)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_reads_each_metric_from_its_own_call[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/    if len(close) - start < 2:/    if len(close) - start < 1:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_refuses_fewer_than_2_returns_from_the_tilts_first_engagement_before_any_bar[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_metrics(/def _b3_metrics_gone(/' --mutation '/^def _b3_metrics(/,/^def /s/    if len(close) - start < 2:/    if len(close) - start < 3:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_refuses_fewer_than_2_returns_from_the_tilts_first_engagement_before_any_bar[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_preflight_metrics(/def _b3_preflight_metrics_gone(/' --mutation '/^def _b3_preflight_metrics(/,/^def /s/    bar, net_a, bench = _b4_arm_a_bar(inputs, n_trials=n_trials)/    bar, net_a, bench = _b4_arm_a_bar(inputs, n_trials=2)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_preflight_metrics(/def _b3_preflight_metrics_gone(/' --mutation '/^def _b3_preflight_metrics(/,/^def /s/ \* _B2_COST_PER_SIDE \* PPY_4H,/ * 1.5 * _B2_COST_PER_SIDE * PPY_4H,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_preflight_metrics(/def _b3_preflight_metrics_gone(/' --mutation '/^def _b3_preflight_metrics(/,/^def /s/"arm_a_max_drawdown_full": max_drawdown(net_a),/"arm_a_max_drawdown_full": max_drawdown(net_a[1:]),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_preflight_metrics(/def _b3_preflight_metrics_gone(/' --mutation '/^def _b3_preflight_metrics(/,/^def /s/        \*\*_b3_engagement(inputs),/        **_b3_engagement(inputs._replace(engaged_b=inputs.engaged_a)),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_as_of_before_any_read[b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/^def _b3_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_as_of_before_any_read[b3-rank-tilt-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/"b3-rank-tilt": Subject(/,/^    ),/s/verdict=_b3_rank_tilt_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_rank_tilt(/def _build_b3_rank_tilt_gone(/' --mutation '/"b3-rank-tilt": Subject(/,/^    ),/s/n_trials=_B3_N_TRIALS,/n_trials=2,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b3-rank-tilt]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/registry/budget.py --control 's/^BUDGET: dict/BUDGET_gone: dict/' --mutation 's/"B3": "B", //' -- uv run pytest 'tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D2–D8 gives the new code. The declaration: the count, the pre-flight's keys, the seeds, the spec, the rule, the family, `M`, `k`, the floor and an engagement key (rows 1–10). The rule, row by row (rows 11–20), the last reading the full window in place of the primary read. The reads: the 4h grid (row 21) and each window refusal on both subjects (rows 22–25). The inputs: arm A untilted, the BTC fill, the assets' returns on the filled BTC, the arms' mean, the arms' keys, the score lookback, the strength, the floor, the tilted counts, the basket lookback, arm B through the limits (rows 26–36). The first engagement read off any asset and off any difference (rows 37–38). The engagement's primary count, tilted closes read off the tilted counts, histogram, mean, turnover, differing stamps and engaged flags (rows 39–45). The metrics: the primary read from the first engagement, arm B's net, the stressed series, arm A's own `passes`, the full-window SPA p, arm A's drawdown and the count reaching arm A's bar (rows 46–52). The refusal's bound from both sides (rows 53–54). The pre-flight: the count reaching its bar, the spot drag, the drawdown and the engagement's flags (rows 55–58). The `--as-of` refusal on both subjects, the plain eval and the count (rows 59–62). `BUCKET_OF`'s new line (row 63).
- [ ] **Step 9: Commit** — `feat(research): B3 trial 1's subjects — the A2 ensemble's long weights tilted by a cross-sectional momentum rank and their pre-flight twin on a frozen set's full history, and the family key B3 in bucket B`, the message carrying the test result lines, the probe block's commands and verdicts, the owner's ruling the new family joins under, quoted ("B3 (Recommended)"), and the two trailer lines.

## Task 3: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D9)

**Files:** Create `tests/test_research_b3_rank_tilt_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 2's `_b3_reads`, `_b3_inputs` and `_b3_engagement`; `cli.alpha.b1.book_turnover`; `cli.registry.observed.ObservedReader`, `cli.registry.record.compute_hash` and `cli.research.command._DATA_ROOT`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`. Produces one test, its own `trial_inputs()`, and the module names `BLOCK`, `VOUCHED`, `RETURN_INDICES`, `HISTOGRAM` and `ENGAGEMENT`, which Task 4's check programs import. No test computes a return of a book.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, record 58's and record 49's figures read off the committed records:

```python
"""B3 trial 1's inputs half against spec 00147's measured basis: positions, the ranked basket, the tilted closes, the
limits and turnover, and no return of a book."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_YEARS = dict.fromkeys(map(str, range(2013, 2027)), 0)
_SHORT = "20-50-100@0.12"
_LONG = ("60-120-240@0.1", "60-120-240@0.12")
# Copied from the spec's measured basis, never from a run.
BLOCK = "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
_ARMS = (_SHORT, *_LONG)
# The basket is the same at every arm: its weights and scores read no direction.
HISTOGRAM = dict.fromkeys(
    _ARMS,
    {"0": 180, "1": 4_336, "2": 3_182, "3": 760, "4": 2_795, "5": 2_605, "6": 1_389, "7": 607, "8": 1_407, "9": 1_254, "10": 8_822},
)
ENGAGEMENT = {
    "tilt_first_engaged": 15_672,
    "primary_returns": 11_665,
    "stamps_positions_differ": 9_691,
    "positions_differ_per_year": _YEARS
    | {"2020": 171, "2021": 1_904, "2022": 1_762, "2023": 1_944, "2024": 1_805, "2025": 1_717, "2026": 388},
    "tilted_per_year": {
        _SHORT: _YEARS | {"2020": 145, "2021": 1_601, "2022": 1_304, "2023": 1_634, "2024": 1_415, "2025": 1_343, "2026": 315},
        **dict.fromkeys(
            _LONG, _YEARS | {"2020": 171, "2021": 1_690, "2022": 1_253, "2023": 1_661, "2024": 1_444, "2025": 1_304, "2026": 342}
        ),
    },
    "ranked_assets_histogram": HISTOGRAM,
    "ranked_assets_mean": {
        arm: math.fsum(int(m) * c for m, c in counts.items()) / RETURN_INDICES for arm, counts in HISTOGRAM.items()
    },
    "turnover_b": 188.39442044111686,
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
}


def trial_inputs():
    """The trial's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b3_inputs(subjects._b3_reads("b3-rank-tilt", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set is absent under data/",
)
def test_the_rank_tilt_inputs_reproduce_the_measured_basis_and_record_58s_arm_a():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    block = reader.block()
    assert compute_hash(block) == BLOCK == _trials()[49]["dataset_hash"] and reader.vouched_status() == VOUCHED
    assert len(inputs.close) == RETURN_INDICES
    # Arm A is record 58's: its ten EUR files, and its turnover to the last bit.
    record = _trials()[58]
    assert block["ohlc-full"]["files"] == {p: h for p, h in record["datasets"]["ohlc-full"]["files"].items() if "/EUR/" in p}
    assert book_turnover(inputs.arm_a) == record["metrics"]["turnover_a"]
    engagement = subjects._b3_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert {arm: round(mean, 4) for arm, mean in engagement["ranked_assets_mean"].items()} == dict.fromkeys(_ARMS, 5.8723)
```

  **Author's call** — the case holds the subject's inputs half to the spec's books program, which built arm B's three arms by its own expression of `a2_book_returns` with the tilt written out, so the measured figures and the subject's code are two derivations that must agree; the block to record 49's `dataset_hash` and to record 58's ten EUR files, arm A to record 58 by its turnover to the last bit, the stored figures, never a second typing; the integer engagement, arm B's turnover and the ranked means exactly — the means as the histogram's own arithmetic — and the means at the four decimals the basis printed.
- [ ] **Step 2: Run it** — with `data/ohlc-full` linked in this worktree: `mkdir -p .tmp/plan-00147 && uv run pytest tests/test_research_b3_rank_tilt_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, a call of 134.75 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b3_rank_tilt_basis.py::test_the_rank_tilt_inputs_reproduce_the_measured_basis_and_record_58s_arm_a
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b3_rank_tilt_basis.py tests/slow-cases.txt`; the Global Constraints' list over the two paths (measured `18 passed, 1 deselected in 26.62s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00147 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt` (measured `331 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B3 trial 1's inputs half against the measured basis — the block, the first engagement, the ranked basket, the tilted closes per arm, the closes where the books differ, the limits and arm B's turnover, and record 58's arm A`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_b3_rank_tilt_basis.py::test_the_rank_tilt_inputs_reproduce_the_measured_basis_and_record_58s_arm_a`, the line `It reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the loop's pick (spec 00147's Ruling, D1) and then **Author's call** the trial's conventions, plan 00145's form — one commit, both entries — so that both stand in the log before any return of arm B is read:

```markdown
[iter-192] B3's first step — trial 1, the rank tilt alone on the A2-4h ensemble, the loop's pick under the owner's family pick (Decision: 1)
  Said, attended, 2026-10-24, asked which family follows B4: "B3 (Recommended)" (the `[iter-190] B4's next step after the leg reading` entry above); B4 closed on the owner's word (the `[iter-191] B4's next step after trial 2 — closed` entry above). The owner's run instruction of 2026-10-23: "continue working on B4-legs and other research strates. Ignore the wall time clock gate, but do not pick up new topics after 09:00Z". B3 is worked under T0016 and no new topic is registered; its first step is the loop's pick under the owner's family pick. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)" and the two `[iter-176]` rulings.
  1. **Trial 1, the rank tilt alone** — the A2-4h ensemble's long weights tilted at each close by a simple cross-sectional momentum rank over the whole basket, at the closes where 8 assets or more rank, long-only, no borrow and no carry; one knob, so a verdict attributes to the tilt; master plan §5's "kill quickly" is one slot. Spec 00147, count 1: the basket ranks 8 or more at 11,483 of 27,337 return indices, the first at return index 15,672 (close 2020-12-03 12:00), where the tilt first moves a position, 11,665 return indices from it; the books differ at 9,691, and arm B trades 28.87 % more than arm A (spec 00147's measured basis); one B slot, 11 to 10. Chosen.
  2. **Trial 1 as master plan §5 writes B3 whole, the tilt with the A1-short BTC overlay** — two knobs in one trial, a reject unattributable; the overlay carries the borrow the A family measured as a structural ~5 %/yr drag (T0016's first finding) and §12's borrow-unavailable stress rung; the adopted ensemble already goes flat per asset in a downtrend.
  3. **A no-slot reading first** — the within-basket rank spread's forward returns by quantile, screening before a slot (iter-186's and iter-190's form); one cell with no alternative cell to choose between, and an iteration spent before the trial the master plan's own prior expects to kill.

[iter-192] B3 trial 1's conventions, pinned by spec 00147 before its hash (Decision: 1)
  The trial's details are fixed in the spec, reviewed, and frozen by its sha256, its record's `spec_hash`, before any return of arm B is read, or a net-of-cost series, head-to-head or bar leg of arm B computed, over the data; each call below is one the spec pins, the loop's or the author's as the spec marks it, every value the owner or specs 00128, 00133, 00137 and 00144 fixed staying theirs.
  1. **As the spec pins them, the tilt alone at M = 180 closes, k = 0.5 and a basket of 8** — one trial and its pre-flight twin, the loop's pick (D1); frozen `ohlc-full`, full history, the ten EUR assets' 4h union as records 45–58 read it, no other pair, no as-of (D2); arm A the adopted ensemble, record 58's arm A to the bit; arm B the same three A2 arms, at each close the basket — every asset with a weight and a score, whatever its direction — ranked on the trailing simple return over M closes, z each one's centred ascending rank, ties at their average rank, and where the basket holds 8 or more, master plan §3's "Any cross-sectional tilt needs enough names to rank — meaningful below ~8 it is not", each long's weight multiplied by 1 + k·z and the longs rescaled to their untilted sum, the flat assets untouched, fewer than 2 longs untilted, the base returns, the vol target and the positions read off the tilted weights as A2 reads its own; the tilt in a new module, `cli/alpha/b3.py`, `a2_book_returns` unchanged and reproduced to the bit at k = 0 (D3); each asset at 0.006 a side on its own turnover through trial 58's `_b4_net`, no borrow and so no carry (D4); §10's limits as trial 58 wired them, engaging no bar (D5); the contamination stated — B3's first look, its instrument, window, arm A, costing and bar records 45–59's, the master plan's prior "fails to beat equal-weight; kill quickly if so", the prior phases' refuted ML selection and long/short quantile spread not this trial, and the tilt read only from 2020-12-03, where the basket first holds 8 (D6); trial 58's bar at count 1 and `var_trials` 0.0, the head-to-head from the tilt's first engagement, return index 15,672, deciding, the matrix through the trial's own rule `_b3_rank_tilt_verdict`, the park variants the tilt at another M or k and the A1-short BTC overlay, the count fixed by the hash (D7); the family key `B3` in bucket B, the subjects `b3-rank-tilt` and `b3-rank-tilt-preflight`, the variant `B3-rank-tilt-a2eq-full-v1`, 44 and 28 keys, the tilt's engagement recorded, the build in three halves (D8); no `--verdict`, notes naming only what is fixed before the run (D9); an adopt recorded, never deployed, B3's next step the owner's after any verdict, the subjects kept until then (D10). Chosen.
  2. **The alternatives each weighed** — the rank among the longs alone, the loop's first form of the tilt (spec 00147's first version), which met the master plan's ~8-name breadth at 3,574 and 3,244 of the 27,337 closes (13.07 % and 11.87 %) and traded 62.82 % more than arm A, its ranks churning with the long set's membership; the tilt with the A1-short BTC overlay, two knobs in one trial; a score window other than the ensemble's own 180 closes, a free window the master plan does not name; a full-strength tilt, k = 1, which zeroes the weakest asset; the tilt without the rescale, which moves the long book's sum; the full window deciding, which adds 15,672 return indices at which the two books are one to the bit; `_b4_ratio_legs_verdict`, whose holding key the tilt has no counterpart of; a change to `cli/alpha/a2.py`, the adopted code; a borrow-free twin, which a book borrowing nothing does not need; a count raised in place; the subjects retired after the verdict, while a park variant may still run their halves.
  Source: spec 00147 (D1–D10), its **Author's call**s and the calls it carries from the owner and specs 00128, 00133, 00137 and 00144; the owner's words quoted in the pick above.
```

  staged alone, its gate the Global Constraints' list over the staged path with `tests/test_decisions_log_shape.py` and `tests/test_decisions_log_ties.py` by path (measured in the scratch worktree over Task 3's tree, the two entries appended, `50 passed`) — `consumers.sh --direct` names no test reader of the log, its stderr saying `(none -- …)`, so those two are the whole list — and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-192] B3's first step — the loop's pick, trial 1 with the rank tilt alone — and B3 trial 1's conventions, pinned by spec 00147 before its hash`. T0016's B3 trigger as Task 6 rewrites it greps for `B3.s next step after trial 1`, which neither header carries (measured in the scratch worktree, the check prints 0 with the entries appended).
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes or reads arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — through the code, a program or arithmetic over a stored figure — or runs either subject over the real data, before the spec's hash, and the data-gated case runs with `ohlc-full` linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D9)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00147-b3-rank-tilt-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; arm A's code path since record 59's run — the spec's basis lists it from that run's commit to the branch's cut — `git log --oneline 273eaa58ea492220c1faf874cce7123b9599da0b..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1–2's commits and their fixes alone (measured at the base: nothing); any other commit is named, step 4 deciding whether it moved the inputs half or trial 58's computes.
- [ ] **Step 2: D9 (1), the spec hash** — `sha256sum docs/specs/00147-b3-rank-tilt-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D9 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record or a reading another branch's merged PR carries — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0016's — then takes a delta read of the merge in place of re-running step 1: step 1's code-path log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 3 step 6's sentence with its "before the spec's hash" read "before Task 5's run, record 58's replay excepted", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the trial — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. A B3 record another branch landed raises `required_n("B3")` above 1, and the run is then refused before its fit (D7): the trial stops, T0016's. The check has two sites, this step and Task 5 step 1, and both take this path.
- [ ] **Step 4: D9 (3), the data test on the run's tree, with the subjects' two fixture rows and record 58's replay** — with `data/ohlc-full` linked: `mkdir -p .tmp/plan-00147 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b3_rank_tilt_basis.py 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-rank-tilt-evaluates]' 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-rank-tilt-preflight-evaluates]' 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-58]' -q -p no:cacheprovider --basetemp=.tmp/plan-00147/pt > .tmp/plan-00147/basis.out 2>&1`, one background call: `4 passed`, never a skip or an xfail — the fixture rows run the build end to end on the tree a fix of the reads may have changed, and record 58's replay rebuilds trial 58's stored figures through the arm A, costing, bar and head-to-head code the trial's computes half shares with it (measured on the scratch tree, the first three `3 passed in 169.55s`, the replay `1 passed in 301.39s`); a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code, the replay's a moved computes half — T0016's, and the run waits.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00147/preflight_check.py`, D9's (a)–(e) in order, the dead knob read before the engagement, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00147 D9's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b3_rank_tilt_basis import BLOCK, ENGAGEMENT, RETURN_INDICES, VOUCHED
from tests.test_trial_registry_provenance import _trials

out = Path(".tmp/plan-00147/b3-rank-tilt-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if compute_hash(block) != BLOCK:
    sys.exit("(a) the inputs' block differs from the spec's")
if run["vouched"] != VOUCHED:
    sys.exit("(a) the set is not vouched as the spec reads it")
record = _trials()[58]["metrics"]
anchors = {
    "arm_a_ann_sharpe_noc": record["arm_a_ann_sharpe_noc"],
    "arm_a_ann_sharpe_noc_decisive": record["arm_a_ann_sharpe_noc_decisive"],
    "arm_a_max_drawdown_full": record["arm_a_max_drawdown"],
    "turnover_a": record["turnover_a"],
    "arm_a_spot_drag_pct_yr": record["turnover_a"] / RETURN_INDICES * 0.006 * 2190,
    "benchmark_ann_sharpe_noc": record["benchmark_ann_sharpe_noc"],
    "benchmark_ann_sharpe_noc_decisive": record["benchmark_ann_sharpe_noc_decisive"],
}
off = {key: (m[key], value) for key, value in anchors.items() if m[key] != value}
if off:
    sys.exit(f"(b) arm A does not reproduce record 58's arm A: {off}")
print("first engaged", m["tilt_first_engaged"], "primary", m["primary_returns"], "differ", m["stamps_positions_differ"], "turnover_b", m["turnover_b"])
if not m["stamps_positions_differ"]:
    sys.exit("(c) the tilt moves no position: the dead knob")
off = [key for key, value in ENGAGEMENT.items() if m[key] != value]
if off:
    sys.exit(f"(d) the engagement differs from the measured basis: {off}")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00147/record_check.py`, the record's checks, its one argument the spec's sha256:

```python
"""Spec 00147 D8's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b3_rank_tilt_basis import BLOCK, ENGAGEMENT

name, spec_hash = "b3-rank-tilt", sys.argv[1]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00147/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00147/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block == BLOCK,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"])
    == ("B3", 1, "B3-rank-tilt-a2eq-full-v1", "iter-192", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": {key: m[key] for key in ENGAGEMENT} == ENGAGEMENT,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `mkdir -p .tmp/plan-00147 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00147/preflight_check.py .tmp/plan-00147/record_check.py`. The pre-flight check was run in the scratch worktree over a synthetic pre-flight print carrying the real block, read by `_b3_reads` with no compute, the basis's engagement and record 58's arm A figures: it printed the block, the first engagement, the primary count, the differing stamps, arm B's turnover and the bar's flags and exited 0; with `passes` 0 it exited 1 on `(e) arm A fails its bar`, and with `stamps_positions_differ` 0 on `(c) the tilt moves no position: the dead knob`.

## Task 5 (the controller's): trial 1 — its pre-flight, its run and its record (D7–D9)

`<H>` is Task 4 step 2's sha256.

**The notes rule**: every free-text `--notes` this plan passes is written first, in a call of its own, to its own file under `.tmp/plan-00147/` by a quoted heredoc — `mkdir -p .tmp/plan-00147 && cat > <its file> <<'EOF'`, the text on the lines after it, `EOF` alone on the last — and passed as `--notes "$(cat <its file>)"` behind `test -s <its file> &&` in the run's own line: no `'` or `"` in the text can end the argument, and an absent or empty file stops the line before `uv run` starts, never a run with empty notes — its output file not written, nothing spent, the file written again before the line runs again. The sites, the whole of them: step 3's reading, `.tmp/plan-00147/b3-rank-tilt-reading-notes.txt`, and step 4's trial, `.tmp/plan-00147/b3-rank-tilt-notes.txt` — the two `--notes` spec 00147 D9 names, in its steps (4) and (5); no other step of this plan passes one.

- [ ] **Step 1: The develop check** — Task 4 step 3 whole, its stop, its merge path and Task 4 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `mkdir -p .tmp/plan-00147 && uv run zcrypto research eval --subject b3-rank-tilt-preflight --dataset ohlc-full > .tmp/plan-00147/b3-rank-tilt-preflight.out 2>&1`, a plain eval of a subject with no rule — the inputs half and one bar, about two and a half minutes (the spec's basis: the inputs half 134.75 s, one bar 11.10 s) — one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00147/preflight_check.py`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(e): D9's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0016's with its line; a refused build — exit 1 with no traceback, its output naming `b3-rank-tilt-preflight over the full history: …` — prints no metrics, keeps no reading, and is recorded in Task 6's T0016 findings with its line quoted, the trial unspent.
- [ ] **Step 3: On a stop, the reading** — its notes, by the notes rule, in `.tmp/plan-00147/b3-rank-tilt-reading-notes.txt`: `B3 trial 1's pre-flight (spec 00147 D9): <the check's sys.exit line, whole, between single quotes, never a double quote>; no verdict, the trial unspent`; then `mkdir -p .tmp/plan-00147 && test -s .tmp/plan-00147/b3-rank-tilt-reading-notes.txt && uv run zcrypto research eval --subject b3-rank-tilt-preflight --dataset ohlc-full --reading --iteration iter-192 --spec-hash <H> --notes "$(cat .tmp/plan-00147/b3-rank-tilt-reading-notes.txt)" > .tmp/plan-00147/b3-rank-tilt-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `mkdir -p .tmp/plan-00147 && test -s .tmp/plan-00147/b3-rank-tilt-notes.txt && uv run zcrypto research eval --subject b3-rank-tilt --dataset ohlc-full --register --iteration iter-192 --family B3 --n-trials 1 --variant B3-rank-tilt-a2eq-full-v1 --spec-hash <H> --notes "$(cat .tmp/plan-00147/b3-rank-tilt-notes.txt)" > .tmp/plan-00147/b3-rank-tilt.out 2>&1`, about four minutes (the spec's basis: the inputs half, seven bars and two head-to-heads, about 225 s), one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run to `.tmp/plan-00147/b3-rank-tilt-notes.txt` by the notes rule, name only what is fixed before it: `subject b3-rank-tilt over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble on the ten EUR assets, arm B the same three arms with each arm's inverse-vol weights of the assets it holds long tilted at every 4h close by their centred rank in the whole basket, every weighted asset whatever its direction, on the trailing 180-close simple return, each long times 1 + 0.5 z, 1.5 at the basket's top and 0.5 at its bottom, the longs rescaled to their untilted sum, the flat assets untouched, at the closes where the basket ranks 8 assets or more, long-only, A2's configuration otherwise unchanged; every asset charged 0.006 per side on its own turnover, no borrow and no carry; the section 10 gross cap, net band and margin floor, one factor per bar; the hypothesis: the tilted book has a higher mean net-of-cost return than the untilted ensemble from the first close the tilt moves a position; n_trials 1, var_trials 0.0, the DSR leg binding; the head-to-head from return index 15672 (close 2020-12-03 12:00), the tilt's first engagement, decides, the full-window read beside it; the contamination: B3's first look, the instrument, arm A, costing and bar records 45-59's, the master plan's prior "fails to beat equal-weight; kill quickly if so", the design amended before the hash on engagement figures alone from the rank among the longs, which met the master plan's ~8-name breadth at 12-13 % of closes, arm B trading 28.87 % more than arm A; pre-flight: block ff2e5700..., arm A <the seven anchors>, the bar's dsr <its dsr> and SPA p <its spa_p_value>, passes 1, the tilt engaged from return index 15672 with positions differing at 9691 return indices, no limit engaged, turnover_b <its value>; park variants, pre-registered: the tilt at another M or k, the A1-short BTC overlay; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, a B3 record landed elsewhere, or bucket B spent — comes before the fit or after the print, naming each orphan, the count or the bucket's figure: no record, no reading; T0016 carries it (Task 6). A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b3-rank-tilt"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build ends its attempt failed, counting 0, recorded in T0016 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0016's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00147/record_check.py <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 6 step 1). A failed check stops the task before step 6.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-192] Verdict — B3 trial 1 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B3 n=1)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D7's table (`sed -n '/^| Arm A.s bar and the tilt/,/^  Every quantity the matrix reads/p' docs/specs/00147-b3-rank-tilt-design.md`), with `arm_a_passes`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary` unrounded, the full-window pair beside them; `n_trials` 1, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); `max_drawdown` beside `arm_a_max_drawdown`; the pre-flight's block, anchors and `passes` from `.tmp/plan-00147/b3-rank-tilt-preflight.out`; the engagement — `tilt_first_engaged`, `primary_returns`, `stamps_positions_differ`, `ranked_assets_mean`, `turnover_a` beside `turnover_b`, `limit_engaged_per_year`'s totals; the contamination D6 states, pointing at the conventions entry above; on a park its variants; on an adopt D10's path in its order; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-189] Verdict — B4 trial 1 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b3-rank-tilt": 1,` after `"b4-sol-noborrow-rolling": 2,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B3 trial 1's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries its tilt adopts` (D10), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`. Then `git add` by path of `docs/reference/trial-registry.jsonl`, the record step 4's run appended, `docs/research/10.phase4-decisions.md`, `tests/test_trial_registry_provenance.py` and `tests/slow-cases.txt`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and `docs/open-topics/README.md`; the list over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, the set linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter192/.tmp/plan-00147/probe/data/ohlc-full`, unlinked after the replay and the probe with `test -L <its absolute path> && unlink <its absolute path>` and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task; then the literal's probe, expected `KILLED` (its two seds dry-run on the authoring tree, each changing one line): `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_rank_tilt_verdict(/def _b3_rank_tilt_verdict_gone(/' --mutation 's/^_B3_N_TRIALS = 1\b/_B3_N_TRIALS = 2/' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit that index, with no `git add` after the setup, as `docs(research): B3 trial 1 registered — <verdict>, the A2 ensemble's long weights tilted by a cross-sectional momentum rank, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b3-rank-tilt-preflight` with outcome `null`, or `b3-rank-tilt` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones — the entry is `[iter-192] B3 trial 1 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` at its `sorted()` place, the replay rebuilding the run over the real set, as (iii) adds the record's; `git add` by path of `docs/reference/reading-ledger.jsonl`, the reading the run appended, `docs/research/10.phase4-decisions.md` and `tests/slow-cases.txt`, then the record arm's list, pre-commit, probe worktree and replay, with `-k 'reading-<its id>'`; committed as `docs(research): B3 trial 1 — instrument finding, kept as reading <id>; no trial spent` with no literal's probe. On a refusal from the count or a refused build: no commit here; Task 6 records it.

## Task 6: T0016 and the index (D10)

**Files:** `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`.

Every figure is read off the committed record or reading and its entry. Task 5's outcome picks the arm: a verdict other than an adopt — park or reject — takes the verdict arm; an adopt the adopt arm; no verdict — a stop kept as a reading, a refused build, a refusal from the count, a merge aborted at a develop check, the data test failing or skipping, or any other end Task 5 sends to T0016 — the stop arm. **Author's call — no retirement in any arm** (D10): until the owner's call on B3's next step a park variant or the overlay may run through the two subjects' halves at another `M` or `k`, so `tests/retired_subjects.py` is not touched and both subjects' cases stay in CI.

- [ ] **Step 1: T0016**, per `topic-ops`, each anchor counted unique with `grep -c` before its edit and the heading set (`grep '^#'`) compared before and after:
  - `## Findings so far`: the budget bullet's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B3", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` (at this branch's base, with `B3` mapped, it printed `{'B1': 5, 'B2': 7, 'B3': 0, 'B4': 2} remain 11 []`; on trial 1's record, with no orphan, it prints `{'B1': 5, 'B2': 7, 'B3': 1, 'B4': 2} remain 10 []`): `(B1 spent 5, B2 spent 7, B4 spent 2, 11 remain)` reads `(B1 spent <its B1>, B2 spent <its B2>, B3 spent <its B3>, B4 spent <its B4>, <its remain> remain)`, each orphan it lists named there; after the `**B4 trial 2 PARK (iter-191, spec 00146, registry trial 59).**` bullet, one bullet `**B3 trial 1 <VERDICT> (iter-192, spec 00147, registry trial <N>).**` — the row that fired and the tilt's engagement in one or two sentences, pointing at its decisions-log entry for the figures — or, on the stop arm, `**B3 trial 1, no verdict (iter-192, spec 00147).**`, naming the reading by id where one was kept and quoting whole the line that stopped it — the check's `sys.exit` line, the conflict `git merge` printed, which stands in no file, only in the controller's call, and so reaches this task quoted whole in the controller's dispatch of it, the failure or skip line in `.tmp/plan-00147/basis.out`, the line in `.tmp/plan-00147/b3-rank-tilt-preflight.out` or `.tmp/plan-00147/b3-rank-tilt.out`, or that run's output's end as Task 5 step 4 quotes it — the trial unspent unless the count lists its attempt as an orphan, which spends the slot.
  - `## Done so far`: after the **B4 opened** bullet, one blank line and the bullet `` - **B3 opened (iter-192, spec/plan `00147`)** on the owner's family pick of 2026-10-24, its trial 1 the loop's pick under that pick: the module `cli/alpha/b3.py`, the subjects `b3-rank-tilt` and `b3-rank-tilt-preflight`, the data-gated basis test `tests/test_research_b3_rank_tilt_basis.py`, the family key `B3` in bucket B. Trial 1 (registry trial <N>) <VERDICT>; the subjects kept until the owner's call on B3's next step. ``, its last sentence on the stop arm `Trial 1 no verdict, no slot spent, its subjects kept.`, or, where the budget bullet's count lists trial 1's attempt as an orphan, `Trial 1 no verdict, one slot spent by its orphaned attempt, its subjects kept.`
  - `## Suggested next steps`: its one bullet, `` - B3, the owner's next-family pick of 2026-10-24 (the `[iter-190] B4's next step after the leg reading` entry), its §10 prerequisite met; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``, becomes `` - (owner) B3's next step after trial 1 — the owner's family call, reading trial 1's verdict: a park variant (the tilt at another M or k), the A1-short BTC overlay (master plan §5's B3 whole) or closing B3 — recorded as a `[iter-NNN] B3's next step after trial 1` entry; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``; on the adopt arm a bullet after it, `` - (owner) B3 trial 1's ADOPT (registry trial <N>), recorded, never deployed: its path in order — a P1 combination trial over record 47's book carrying the tilt, outside every bucket's budget, then T0123's promotion path (spec 00147 D10). ``; on the stop arm the bullet becomes instead `` - (owner) B3's next step after trial 1's stop — trial 1 run again once its cause, quoted in Findings, is fixed, or B3 closed — recorded as a `[iter-NNN] B3's next step after trial 1` entry; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``
  - `ripe_when`: its B3 arm, `` B3: B4 closed, check: `grep -c -E ''^\[iter-[0-9]+\] B4.s next step after trial 2 — closed'' docs/research/10.phase4-decisions.md` prints at least 1; `` (the trailing space included), becomes on the verdict arm and the adopt arm alike — D10's one entry after any verdict — `` B3: an activity, the owner picks B3''s next step after trial 1 — a park variant, the A1-short overlay or closing the family — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B3.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1; `` and on the stop arm `` B3: an activity, the owner''s call on trial 1''s stop — the trial run again once its cause is fixed, or B3 closed — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B3.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1; `` — in the frontmatter's single quotes, each `'` inside it doubled as written here, the check kept in its own backticks; the other families' arms unchanged.
  Measured in the scratch worktree, each arm applied to the base's T0016 with sample figures and then reverted: the heading set unchanged, the frontmatter parsing to the intended text, each arm's check printing 0 with Task 3's entries appended, and `tests/test_open_topics_frontmatter.py tests/test_topics_index.py` passing (`1111 passed`) with step 2 applied.
- [ ] **Step 2: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 3: Gate and commit** — `git add` the two paths; the list over them with `tests/test_open_topics_frontmatter.py` by path; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0016 after B3 trial 1 — <its verdict or no verdict>, B3's next step the owner's; its subjects kept`.

## Task 7 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-192 — B3 trial 1: the rank tilt on A2` (58 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 5–6's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with `ohlc-full` linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the verdict or the stop, the pre-flight's output quoted whole in a fenced block (`.tmp/plan-00147/b3-rank-tilt-preflight.out`), every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the owner's ruling `BUCKET_OF`'s new family joins under, quoted, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00147` collected and removed, and the link removed with `test -L <the checkout>/data/ohlc-full && unlink <the checkout>/data/ohlc-full` in this worktree and in each reader's checkout whose `data/` holds it; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full` still there.

Decisions log: the loop's pick and the conventions entry (Task 3 step 5), before the hash; the verdict or instrument-finding entry (Task 5 step 6), in its record's commit; B3's next step after trial 1 is the owner's, its entry a later branch's (T0016's trigger).
