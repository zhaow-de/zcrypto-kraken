# B4 trial 1 — the ETH/BTC and SOL/BTC ratio legs on the A2-4h ensemble on frozen ohlc-full: the compute module, the trial subject and its twin, the family key, the data-gated basis test, the loop's pick before the hash, the gated run and the record — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b4.py tests/test_alpha_b4.py cli/research/subjects.py cli/registry/budget.py tests/test_research_command.py tests/test_trial_registry_provenance.py README.md tests/slow-cases.txt tests/test_research_b4_ratio_legs_basis.py docs/research/10.phase4-decisions.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/retired_subjects.py docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00144-b4-ratio-legs-design.md` prints `tier: full`, for `tests/test_alpha_b4.py` "a test importing cli.alpha.errors", `cli/registry/budget.py` "under cli/registry/", `tests/test_research_command.py` "a test importing cli.alpha", `tests/test_trial_registry_provenance.py` "a test importing cli.registry", `tests/test_research_b4_ratio_legs_basis.py` "a test importing cli.alpha.b1" and `docs/reference/trial-registry.jsonl`).

**Goal:** B4's trial 1 (spec 00144) — the venue's ETH/BTC and SOL/BTC pairs added to the adopted A2-4h ensemble as two more instruments: a compute module `cli/alpha/b4.py`; two research subjects in `cli/research/subjects.py`, the trial and its evaluate-only pre-flight twin; the family key `B4` in `cli/registry/budget.py`'s bucket B; the data-gated test of their inputs half; the loop's pick and the trial's conventions in the decisions log before the hash; the trial run through spec 00133's trial-attempts log, its verdict or stop in the registry and the decisions log; then T0016.

**Architecture:** `cli/alpha/b4.py` holds pure functions over lists, as `cli/alpha/b2.py` does — a ratio leg's EUR return, the per-base exposures a book decomposes into, §10's three whole-book limits as one factor per bar, the quote's shortfall and its carry, the legs held to the book's own quote, three per-year helpers — importing `cli/risk/limits.py`'s three limits and editing nothing. `cli/research/subjects.py` gains three insertions and changes no existing line: the module's import, the B4 block before `SUBJECTS` — `_B4_LEGS`, `_B4_CARRY_RATE`, `_B4_N_TRIALS`, the build in three halves (`_b4_reads`, `_b4_inputs`, `_b4_metrics` / `_b4_preflight_metrics`), the cost function `_b4_net`, arm A's bar, the engagement, the two builders, the rule `_b4_ratio_legs_verdict` and the key sets — and two `SUBJECTS` entries. `cli/registry/budget.py`'s `BUCKET_OF` gains `"B4": "B"`. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00144-b4-ratio-legs-design.md` — binding; D1–D11 are cited by name and the values below are copied from it. **Iteration:** iter-189. **Topic:** T0016, its B4 arm. **Branch:** `research/iter-189-b4-legs-opening`, worktree `.claude/worktrees/iter189`, `data/ohlc-full` linked read-only from the main checkout, and no other set. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: Tasks 1–3's code and tests were written in this worktree beside the staged spec; Task 1's tests measured red against the base (`1 error` at collection) and green with the module (`22 passed`); Task 2's new cases red against the base module (`31 failed, 764 deselected`, and the budgets literal `1 failed`) and green with it (`31 passed, 782 deselected`), the shared rows the two subjects add green (`19 passed, 794 deselected` in 133.59 s); Task 2 step 7's three gate parts green; Task 3's data-gated case `1 passed` with a call of 165.14 s; the slow cases timed; Task 1's 28 and Task 2's 43 probe rows run in a detached scratch worktree, each tree committed there, 71 of 71 `KILLED`; Task 3's two decisions-log entries appended in that worktree and run through the decisions-log tests; Task 6's retirement and T0016's rewritten trigger tried there, then reverted; and Task 4's pre-flight check run over a synthetic pre-flight print carrying the real block. The files were then restored to the base before this plan was committed. Not run: any `zcrypto research eval` of the two subjects (Tasks 4–5), the record's check program beyond a parse, the replay and the literal probe (Task 5), the topic edits as committed (Task 6) and the PR (Task 7).

## Global Constraints

- **The legs and the books** (D2–D7): the legs `ETH/BTC/240.parquet` and `SOL/BTC/240.parquet` of `--dataset`, read through the run's `ObservedReader` and mapped onto the ten EUR assets' union stamps, `None` where a pair has no bar; arm A `_b4_ensemble(fed)`, arm B `_b4_ensemble(fed | ratios)`, the three adopted arms `_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year, each instrument's equal-weight mean; a leg's EUR return `ratio_eur_returns(ratio, fed["BTC"])`; every book costed by `_b4_net(positions, returns, stress=…)`, `net_of_cost` at `stress × 0.006` per side minus `shortfall_carry(<the BTC shortfall>, rate=stress × 0.0002)`; both arms through `_b4_limited`, §10's gross cap 1.5 / 2.0, net band −0.5 … +1.0 and margin floor 2.5 on the per-base exposures as one factor per bar; the twin `_b4_limited(borrow_unavailable(<arm B's raw positions>, _B4_LEGS, "BTC"))`.
- **The bars** (D8): every `a1_kill_bar` call `n_trials=1, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`, the headline (30, 42); arm A's bar the same call at (30, 42) on `net_a`; the head-to-heads `net_of_cost_verdict(<book>[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` for arm B at `first` 0 and at `start`, and for the twin at `start`, `start = min(ratio_first_weight)`, 5,442; refused before any bar: fewer than 2 return indices from `start`.
- **The count** (D8): `_B4_N_TRIALS = 1`, `required_n("B4")` as the spec measured it, fixed by the spec's hash; at `var_trials` 0.0 the DSR leg is the PSR against 0.
- **The rule** (D8): `_b4_ratio_legs_verdict` — `None` when `arm_a_passes` is 0 or no leg is held at any return index (`ratio_held_per_year` all 0), `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0` with `head_to_head_spa_p_primary < 0.05`, `park` on the first with the p at or above 0.05, `reject` otherwise; the park variants ETH/BTC alone and the symmetric legs.
- **The record** (D9): family `B4`; `n_trials_in_family` 1; variant `B4-ratio-legs-a2eq-full-v1`; iteration `iter-189`; seeds (42, 7, 1234); 48 metric keys; the block `9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df`; no `--verdict`.
- **The pre-flight read** (D10), in this order: (a) the block and `ohlc-full`'s vouched status (Task 3's `BLOCK` and `VOUCHED`); (b) arm A's seven anchors at record 45's precision — `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown_full` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703, the benchmark's 1.2128 and 1.2447 at four decimals, `turnover_a` 146.19 at two; (c) the engagement the measured basis's — Task 3's `ENGAGEMENT`, `TURNOVER_B` at two decimals and `CARRY_PER_YEAR` at six; (d) a leg held at some return index; (e) arm A's `passes` 1.
- **The hash rule** (D10): before Task 4 step 2 takes the spec's sha256, nobody computes or reads arm B's or the twin's returns — `book_base_returns`, `net_returns` or `metrics` of `a2_book_returns`' result for arm B, any net-of-cost series, Sharpe, head-to-head or bar leg of arm B or of the twin — nor runs `b4-ratio-legs` or `b4-ratio-legs-preflight` over the real set; positions, weights, exposures, the shortfall, the carry it implies, limit engagement and turnover are allowed — what the data-gated test (Task 3) computes, and no return of a book. `a2_book_returns` computes arm B's base returns internally to size its positions; nothing reads them. No reader, reviewer or plan-review dispatch runs either subject over the real set before the hash, and every read's dispatch carries this rule. No return of arm B is computed over the real data before the trial's `--register` run, and the trial subject is never run as a plain eval.
- **Unchanged** (D9): every existing function of `cli/research/subjects.py`; `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b2.py` and the other `cli/alpha/*` modules but the new one; `cli/features/*`, `cli/portfolio/*`, `cli/risk/*`, `cli/costs/*`, `cli/validation/*`, `cli/engine/*`; `cli/registry/*` but `BUCKET_OF`'s line; the existing subjects; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/alpha/b4.py` from Task 1 on and `cli/registry/budget.py` and `cli/research/subjects.py` from Task 2 on, nothing else; from Task 2 on, `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@')" = 3` and `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@ -[0-9]*,0 ')" = 3` each exit 0 — three hunks, each a pure insertion, so a line changed or added anywhere but at Task 2 step 3's three sites is a fourth hunk or an impure one — and `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/registry/budget.py | grep -c '^[-+][^-+]'` prints 2, `BUCKET_OF`'s old line and its new one. Measured on the authoring tree, `subjects.py`'s hunks: `@@ -81,0 +82,12 @@`, `@@ -3415,0 +3428,351 @@` and `@@ -3770,0 +4134,25 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00144-b4-ratio-legs-design.md` after Task 4 step 2, nor specs 00128, 00133, 00137 and 00143, nor the spec before then except a fix commit a read of Task 3 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 5 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, a read-only link, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The trial, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 4 step 3, Task 5 step 1) and Task 7's `gh` calls, push and `merge-pr` are the exceptions.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 6's reads, Tasks 4–5 and Task 7, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the pre-flight, the register, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 6 and Task 3's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00144 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00144/` follows `mkdir -p .tmp/plan-00144 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00144/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && mkdir -p .tmp/plan-00144 && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt`, never a bare `uv run pytest` and never `consumers.sh` with `2>/dev/null`, whose stderr is where a refusal speaks; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every file a commit carries is staged by explicit path, a line a run appended among them — the registry's by `--register`, the ledger's by `--reading` or by a stop under `--register`, whose one commit is Task 5 step 6's, in either arm — since the commit and the probe setup's `git write-tree` read the index while `T` reads the working tree. Every `T` holding `tests/test_research_command.py` runs it in three parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms: `tests/test_research_command.py -k "not reentry"` (`--basetemp=.tmp/plan-00144/pt-1`, measured on the authoring tree, Tasks 1–3's code in it, `639 passed, 174 deselected in 496.84s`), `tests/test_research_command.py -k reentry` (`pt-2`, measured `71 passed, 742 deselected in 89.92s`) and the rest of `T` (`pt-3`). Every commit message carries the result line of each test command its gate ran, a run over that commit's own tree, and the two trailer lines exactly as the executing session's attribution gives them — `Co-Authored-By:` naming the model that ran the step, and `Claude-Session:`.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00144 &&
  test ! -e .tmp/plan-00144/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00144/probe HEAD &&
  git -C .tmp/plan-00144/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00144/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00144/probe/.tmp
```

  Then, from `.tmp/plan-00144/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, or, in `cli/registry/budget.py`, which holds none, the literal the case imports, so it fails at import or at its call. A mutation whose text also stands elsewhere in the file carries the address of its own function's or entry's range — `/^def <name>(/,/^def /`, `/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/` or `/"<subject>": Subject(/,/^    ),/` — so its dry run changes one line; a pattern that holds `'` writes it as `.`. After the last verdict, `git worktree remove --force .tmp/plan-00144/probe` — a data link in it unlinked first, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, `ohlc-full` still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subjects' names** (D9): `b4-ratio-legs` and `b4-ratio-legs-preflight`, which no registered or retired subject's name equals or opens with a hyphen, and which open none (the spec's basis). Every new test function's name carries `b4_`, which no hyphenated id carries, so `-k b4_` selects them alone; the shared rows the two subjects add carry the hyphenated `b4-ratio-legs` in their ids.

## Task 1: the compute module `cli/alpha/b4.py` (D4–D7, D9)

**Files:** Create `cli/alpha/b4.py`, `tests/test_alpha_b4.py`.

**Interfaces:** Consumes `cli.alpha.errors.AlphaError` and `cli.risk.limits`' `apply_gross_leverage_cap`, `apply_net_exposure_band` and `apply_margin_floor`; its tests also `cli.portfolio.crossfreq_system.apply_whole_book_limits`. Produces `ratio_eur_returns`, `base_exposures`, `limit_factors` (with `LIMITS`, the engaged flags' keys `gross`, `net`, `margin`), `scale_bars`, `quote_shortfall`, `shortfall_carry`, `borrow_unavailable`, `per_year_counts`, `per_year_sums` and `per_year_means`, which Task 2's subjects and tests import.

- [ ] **Step 1: Write the failing tests** — `tests/test_alpha_b4.py`, whole:

```python
import math
from datetime import UTC, datetime

import pytest

from cli.alpha.b4 import (
    base_exposures,
    borrow_unavailable,
    limit_factors,
    per_year_counts,
    per_year_means,
    per_year_sums,
    quote_shortfall,
    ratio_eur_returns,
    scale_bars,
    shortfall_carry,
)
from cli.alpha.errors import AlphaError
from cli.portfolio.crossfreq_system import apply_whole_book_limits

_LEGS = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}


def test_a_ratio_legs_eur_return_is_the_bases_return_less_the_quotes():
    eth = [100.0, 110.0, 99.0, 120.0, 132.0, 126.0]
    btc = [50.0, 52.0, 60.0, 54.0, 48.0, 50.0]
    ratio = [e / b for e, b in zip(eth, btc)]
    ratio[3] = None

    got = ratio_eur_returns(ratio, btc)

    assert [k for k, r in enumerate(got) if r is None] == [2, 3]
    for k in (0, 1, 4):
        assert math.isclose(0.3 * got[k], 0.3 * (eth[k + 1] / eth[k] - btc[k + 1] / btc[k]), rel_tol=1e-12, abs_tol=1e-15)


@pytest.mark.parametrize(
    ("ratio", "quote", "match"),
    [
        pytest.param([0.5, 0.0, 0.5], [1.0, 1.0, 1.0], "the ratio's closes", id="a-ratio-close-of-0"),
        pytest.param([0.5, -0.5, 0.5], [1.0, 1.0, 1.0], "the ratio's closes", id="a-negative-ratio-close"),
        pytest.param([0.5, math.nan, 0.5], [1.0, 1.0, 1.0], "the ratio's closes", id="a-nan-ratio-close"),
        pytest.param([0.5, 0.5, 0.5], [1.0, None, 1.0], "the quote's EUR closes", id="a-missing-quote-close"),
        pytest.param([0.5, 0.5, 0.5], [1.0, 0.0, 1.0], "the quote's EUR closes", id="a-quote-close-of-0"),
        pytest.param([0.5, 0.5, 0.5], [1.0, math.inf, 1.0], "the quote's EUR closes", id="an-infinite-quote-close"),
        pytest.param([0.5, 0.5], [1.0, 1.0, 1.0], "equal in number", id="unequal-lengths"),
    ],
)
def test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by(ratio, quote, match):
    with pytest.raises(AlphaError, match=match):
        ratio_eur_returns(ratio, quote)


def test_base_exposures_nets_each_leg_into_its_base_and_its_quote():
    book = {"BTC": [0.5, 0.125, 0.0], "ETH": [0.25, 0.0, 0.0], "SOL": [0.0, 0.25, 0.0]}
    legs = {"ETH/BTC": [0.125, 0.25, 0.0], "SOL/BTC": [0.0625, 0.0, 0.0]}

    assert base_exposures(book | legs, _LEGS) == {
        "BTC": [0.3125, -0.125, 0.0],
        "ETH": [0.375, 0.25, 0.0],
        "SOL": [0.0625, 0.25, 0.0],
    }
    assert base_exposures(book, _LEGS) == book
    assert legs == {"ETH/BTC": [0.125, 0.25, 0.0], "SOL/BTC": [0.0625, 0.0, 0.0]}


@pytest.mark.parametrize(
    ("positions", "match"),
    [
        pytest.param({"BTC": [0.5], "ETH": [0.5], "ETH/BTC": [0.25]}, "SOL/BTC's base SOL", id="a-legs-base-absent"),
        pytest.param({"ETH": [0.5], "SOL": [0.5], "ETH/BTC": [0.25]}, "ETH/BTC's base ETH and quote BTC", id="the-quote-absent"),
        pytest.param({"BTC": [0.5, 0.5], "ETH": [0.5], "SOL": [0.5]}, "equal in number", id="unequal-lengths"),
    ],
)
def test_base_exposures_refuses_a_book_it_cannot_decompose(positions, match):
    with pytest.raises(AlphaError, match=match):
        base_exposures(positions, _LEGS)


def test_limit_factors_leave_an_untouched_bar_at_one_and_engage_each_limit_in_its_order():
    # Bar 0 breaches nothing; 1 the gross cap and then the net band; 2 the net band alone; 3 the margin floor alone; 4 the
    # gross cap, which leaves the net band inside, and then the margin floor.
    exposures = {
        "BTC": [0.5, 1.0, 0.5, -0.5, -0.9],
        "ETH": [0.25, 0.5, 0.375, 0.5, 1.05],
        "SOL": [0.0, 0.5, 0.375, 0.5, 1.05],
    }

    factors, engaged = limit_factors(exposures)

    assert factors[0] == 1.0
    for got, want in zip(factors[1:], (0.5, 0.8, 0.7, 0.5 * 1.4 / 1.95)):
        assert math.isclose(got, want, rel_tol=1e-12)
    assert engaged == {
        "gross": [False, True, False, False, True],
        "net": [False, True, True, False, False],
        "margin": [False, False, False, True, True],
    }
    scaled, stack = scale_bars(exposures, factors), apply_whole_book_limits(exposures)
    assert [scaled[a][0] for a in exposures] == [exposures[a][0] for a in exposures]
    assert all(math.isclose(scaled[a][k], stack[a][k], rel_tol=1e-12) for a in exposures for k in range(5))


def test_the_shortfall_and_its_carry_charge_each_rollover_and_each_increase():
    exposures = {"BTC": [0.25, -0.5, -0.25, -0.75, 0.0], "ETH": [0.5] * 5}

    shortfall = quote_shortfall(exposures, "BTC")

    assert shortfall == [0.0, 0.5, 0.25, 0.75, 0.0]
    assert shortfall_carry(shortfall, rate=0.0002) == [0.0, 0.0002 * 1.0, 0.0002 * 0.25, 0.0002 * 1.25, 0.0]
    assert shortfall_carry([0.5, 0.5], rate=0.0002) == [0.0002 * 1.0, 0.0002 * 0.5]


@pytest.mark.parametrize("rate", [-0.0002, math.nan], ids=["negative", "nan"])
def test_shortfall_carry_refuses_a_rate_it_cannot_charge(rate):
    with pytest.raises(AlphaError, match="rate must be"):
        shortfall_carry([0.5], rate=rate)


def test_borrow_unavailable_holds_the_legs_short_to_the_books_own_quote():
    book = {"BTC": [0.5, 0.25, 0.0, 0.5, 0.5], "ETH": [0.125] * 5, "SOL": [0.0] * 5}
    legs = {"ETH/BTC": [0.25, 0.25, 0.25, 0.0, 0.125], "SOL/BTC": [0.25, 0.25, 0.0, 0.0, 0.125]}

    held = borrow_unavailable(book | legs, _LEGS, "BTC")

    assert held == book | {"ETH/BTC": [0.25, 0.125, 0.0, 0.0, 0.125], "SOL/BTC": [0.25, 0.125, 0.0, 0.0, 0.125]}
    assert quote_shortfall(base_exposures(held, _LEGS), "BTC") == [0.0] * 5
    assert quote_shortfall(base_exposures(book | legs, _LEGS), "BTC") == [0.0, 0.25, 0.25, 0.0, 0.0]


def test_borrow_unavailable_refuses_a_book_without_the_quote():
    with pytest.raises(AlphaError, match="holds no BTC instrument"):
        borrow_unavailable({"ETH": [0.5], "ETH/BTC": [0.25]}, _LEGS, "BTC")


_CLOSES = [datetime(2015, 12, 31, 16, tzinfo=UTC), datetime(2015, 12, 31, 20, tzinfo=UTC), datetime(2016, 1, 1, tzinfo=UTC)]


def test_the_per_year_helpers_key_each_value_by_its_close_year():
    assert per_year_counts([False, False, True], _CLOSES) == {"2015": 0, "2016": 1}
    assert per_year_sums([0.25, 0.5, 2.0], _CLOSES) == {"2015": 0.75, "2016": 2.0}
    assert per_year_means([0.25, 0.5, 2.0], _CLOSES) == {"2015": 0.375, "2016": 2.0}


@pytest.mark.parametrize(
    ("helper", "values"),
    [(per_year_counts, [True, False]), (per_year_sums, [0.5, 0.5]), (per_year_means, [0.5, 0.5])],
    ids=["counts", "sums", "means"],
)
def test_the_per_year_helpers_refuse_values_and_closes_of_unequal_length(helper, values):
    with pytest.raises(AlphaError, match="for 3 closes"):
        helper(values, _CLOSES)
```

  **Author's call** — every case a hand-computed known answer: the EUR return held to the decomposed `p × (r_ETH − r_BTC)` on a cross-consistent fixture with a missing ratio close; the decomposition's dyadic book, exact, and a book holding no leg returned as it is; the limits on five bars — one untouched, one breaching the gross cap and then the net band, one the net band alone, one the margin floor alone (`_margin_floor_scale`'s second branch, 1.4 / 2.0), and one breaching the gross cap so that the net band is left inside and the margin floor still breached — so the engaged flags pin the order, and the stack's book held to `apply_whole_book_limits`' on every bar; the carry's rollover and opening charge on a shortfall that rises, falls and rises; the twin's scale at a bar the legs fit inside the book's BTC, one they outweigh it, one the book holds none and one with no leg; each refusal its own row, matched on a phrase only its own message holds.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_alpha_b4.py -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt`: collection stops at the import of `cli.alpha.b4` (measured on the base: `1 error`).
- [ ] **Step 3: Implement `cli/alpha/b4.py`**, whole:

```python
"""B4 trial 1 (docs/specs/00144-b4-ratio-legs-design.md): a ratio leg's EUR return (D4), the per-base exposures an
instrument book decomposes into and the quote's shortfall and its carry (D5), §10's limits as one factor per bar (D6), the
legs held to the book's own quote (D7) and the per-year engagement counts (D9).

A position is a fraction of NAV in EUR notional held over return index k, from close k to close k + 1."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from datetime import datetime

from cli.alpha.errors import AlphaError
from cli.risk.limits import apply_gross_leverage_cap, apply_margin_floor, apply_net_exposure_band

LIMITS = ("gross", "net", "margin")


def _check_price(name: str, k: int, p: float | None, *, missing: bool) -> None:
    if p is None and missing:
        return
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or p <= 0:
        raise AlphaError(f"{name} must hold finite numbers above 0{' or None' if missing else ''}, got {p!r} at index {k}")


def ratio_eur_returns(ratio: list[float | None], quote_eur: list[float]) -> list[float | None]:
    """Per unit of EUR notional set at the bar's open, `(R[k+1]/R[k] - 1) * (Q[k+1]/Q[k])`: the gain in the quote's units
    converted at the bar's closing quote price, which equals the base's EUR return less the quote's; None where the ratio
    has no close at either end."""
    if len(ratio) != len(quote_eur):
        raise AlphaError(f"the ratio's {len(ratio)} closes and the quote's {len(quote_eur)} must be equal in number")
    for k, (r, q) in enumerate(zip(ratio, quote_eur)):
        _check_price("the ratio's closes", k, r, missing=True)
        _check_price("the quote's EUR closes", k, q, missing=False)
    return [
        None if ratio[k] is None or ratio[k + 1] is None else (ratio[k + 1] / ratio[k] - 1) * (quote_eur[k + 1] / quote_eur[k])
        for k in range(len(ratio) - 1)
    ]


def _check_lengths(positions: Mapping[str, list[float]]) -> int:
    lengths = {len(v) for v in positions.values()}
    if len(lengths) != 1:
        raise AlphaError(f"every instrument's positions must be equal in number, got lengths {sorted(lengths)}")
    return lengths.pop()


def base_exposures(positions: Mapping[str, list[float]], legs: Mapping[str, tuple[str, str]]) -> dict[str, list[float]]:
    """A leg `(base, quote)` at `p` adds `+p` to its base and `-p` to its quote; any other instrument is its own base."""
    _check_lengths(positions)
    out = {i: list(v) for i, v in positions.items() if i not in legs}
    for leg, (base, quote) in legs.items():
        if base not in out or quote not in out:
            raise AlphaError(f"{leg}'s base {base} and quote {quote} must each be an instrument of the book")
        if leg not in positions:
            continue
        for k, p in enumerate(positions[leg]):
            out[base][k] += p
            out[quote][k] -= p
    return out


def limit_factors(exposures: dict[str, list[float]]) -> tuple[list[float], dict[str, list[bool]]]:
    """§10's gross cap, net band and margin floor at their ratified values, in `cli/risk/limits.py`'s order with no position
    caps: each scales a bar whole, so the bar's factor is 1.0 where none engages, else the limited gross over the unlimited;
    and each limit's engaged bars."""
    n = _check_lengths(exposures)
    gross = apply_gross_leverage_cap(exposures, soft_cap=1.5, hard_cap=2.0)
    net = apply_net_exposure_band(gross, short_bound=-0.5, long_bound=1.0)
    floor = apply_margin_floor(net, floor=2.5)
    engaged = {
        name: [any(before[a][k] != after[a][k] for a in before) for k in range(n)]
        for name, before, after in zip(LIMITS, (exposures, gross, net), (gross, net, floor), strict=True)
    }
    factors = [
        1.0
        if all(floor[a][k] == exposures[a][k] for a in exposures)
        else math.fsum(abs(floor[a][k]) for a in floor) / math.fsum(abs(exposures[a][k]) for a in exposures)
        for k in range(n)
    ]
    return factors, engaged


def scale_bars(positions: Mapping[str, list[float]], factors: list[float]) -> dict[str, list[float]]:
    if _check_lengths(positions) != len(factors):
        raise AlphaError(f"{len(factors)} factors for positions of another length")
    return {i: [p * f for p, f in zip(v, factors)] for i, v in positions.items()}


def quote_shortfall(exposures: Mapping[str, list[float]], quote: str) -> list[float]:
    """What the book borrows of `quote`: its net exposure's short part, the book's own holding netted first."""
    return [max(0.0, -e) for e in exposures[quote]]


def shortfall_carry(shortfall: list[float], *, rate: float) -> list[float]:
    """Each bar's rollover on the amount borrowed, plus the opening charge on what the bar adds to it:
    `rate * (S[k] + max(0, S[k] - S[k-1]))`, nothing borrowed before the first bar."""
    if not math.isfinite(rate) or rate < 0:
        raise AlphaError(f"rate must be a finite number >= 0, got {rate!r}")
    previous = [0.0, *shortfall[:-1]]
    return [rate * (s + max(0.0, s - p)) for s, p in zip(shortfall, previous)]


def borrow_unavailable(
    positions: Mapping[str, list[float]], legs: Mapping[str, tuple[str, str]], quote: str
) -> dict[str, list[float]]:
    """The legs on `quote` scaled each bar by `min(1, holding / their sum)`, the holding the book's own `quote` instrument,
    1 where the legs hold nothing: their short of the quote never exceeds what the book holds of it."""
    n = _check_lengths(positions)
    on_quote = [leg for leg, (_, q) in legs.items() if q == quote and leg in positions]
    if quote not in positions:
        raise AlphaError(f"the book holds no {quote} instrument to cover its legs")
    scales = []
    for k in range(n):
        total = sum(positions[leg][k] for leg in on_quote)
        scales.append(1.0 if total == 0 else min(1.0, max(0.0, positions[quote][k]) / total))
    return {i: [p * s for p, s in zip(v, scales)] if i in on_quote else list(v) for i, v in positions.items()}


def per_year_counts(flags: list[bool], close_ts: list[datetime]) -> dict[str, int]:
    """True flags per close year, every year the closes span keyed."""
    if len(flags) != len(close_ts):
        raise AlphaError(f"{len(flags)} flags for {len(close_ts)} closes")
    counts = dict.fromkeys((str(t.year) for t in close_ts), 0)
    for flag, t in zip(flags, close_ts):
        counts[str(t.year)] += int(flag)
    return counts


def _by_year(values: list[float], close_ts: list[datetime]) -> dict[str, list[float]]:
    if len(values) != len(close_ts):
        raise AlphaError(f"{len(values)} values for {len(close_ts)} closes")
    out: dict[str, list[float]] = {}
    for v, t in zip(values, close_ts):
        out.setdefault(str(t.year), []).append(v)
    return out


def per_year_sums(values: list[float], close_ts: list[datetime]) -> dict[str, float]:
    return {year: math.fsum(vs) for year, vs in _by_year(values, close_ts).items()}


def per_year_means(values: list[float], close_ts: list[datetime]) -> dict[str, float]:
    return {year: statistics.fmean(vs) for year, vs in _by_year(values, close_ts).items()}
```

- [ ] **Step 4: Run them to verify they pass** — step 2's command, measured `22 passed`.
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b4.py tests/test_alpha_b4.py`; the Global Constraints' `T` over the two paths (measured: `tests/test_alpha_b4.py` alone, `22 passed`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the authoring tree, 28 of 28):

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/ - 1) \* (quote_eur\[k + 1\] \/ quote_eur\[k\])/ - 1)/' -- uv run pytest tests/test_alpha_b4.py::test_a_ratio_legs_eur_return_is_the_bases_return_less_the_quotes -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/^        _check_price("the ratio.s closes", k, r, missing=True)/        pass/' -- uv run pytest 'tests/test_alpha_b4.py::test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by[a-ratio-close-of-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/^        _check_price("the ratio.s closes", k, r, missing=True)/        pass/' -- uv run pytest 'tests/test_alpha_b4.py::test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by[a-negative-ratio-close]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/^        _check_price("the ratio.s closes", k, r, missing=True)/        pass/' -- uv run pytest 'tests/test_alpha_b4.py::test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by[a-nan-ratio-close]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/^        _check_price("the quote.s EUR closes", k, q, missing=False)/        pass/' -- uv run pytest 'tests/test_alpha_b4.py::test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by[a-missing-quote-close]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/^        _check_price("the quote.s EUR closes", k, q, missing=False)/        pass/' -- uv run pytest 'tests/test_alpha_b4.py::test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by[a-quote-close-of-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/^        _check_price("the quote.s EUR closes", k, q, missing=False)/        pass/' -- uv run pytest 'tests/test_alpha_b4.py::test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by[an-infinite-quote-close]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def ratio_eur_returns(/def ratio_eur_returns_gone(/' --mutation 's/^    if len(ratio) != len(quote_eur):/    if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by[unequal-lengths]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def base_exposures(/def base_exposures_gone(/' --mutation 's/^            out\[quote\]\[k\] -= p/            out[quote][k] += p/' -- uv run pytest tests/test_alpha_b4.py::test_base_exposures_nets_each_leg_into_its_base_and_its_quote -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def base_exposures(/def base_exposures_gone(/' --mutation 's/^        if base not in out or quote not in out:/        if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_base_exposures_refuses_a_book_it_cannot_decompose[a-legs-base-absent]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def base_exposures(/def base_exposures_gone(/' --mutation 's/^        if base not in out or quote not in out:/        if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_base_exposures_refuses_a_book_it_cannot_decompose[the-quote-absent]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def base_exposures(/def base_exposures_gone(/' --mutation '/^def base_exposures(/,/^def /s/^    _check_lengths(positions)$/    pass/' -- uv run pytest 'tests/test_alpha_b4.py::test_base_exposures_refuses_a_book_it_cannot_decompose[unequal-lengths]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def limit_factors(/def limit_factors_gone(/' --mutation 's/floor=2\.5)/floor=2.0)/' -- uv run pytest tests/test_alpha_b4.py::test_limit_factors_leave_an_untouched_bar_at_one_and_engage_each_limit_in_its_order -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def limit_factors(/def limit_factors_gone(/' --mutation 's/long_bound=1\.0)/long_bound=1.25)/' -- uv run pytest tests/test_alpha_b4.py::test_limit_factors_leave_an_untouched_bar_at_one_and_engage_each_limit_in_its_order -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def limit_factors(/def limit_factors_gone(/' --mutation 's/zip(LIMITS, (exposures, gross, net), (gross, net, floor), strict=True)/zip(LIMITS, (exposures, exposures, net), (gross, net, floor), strict=True)/' -- uv run pytest tests/test_alpha_b4.py::test_limit_factors_leave_an_untouched_bar_at_one_and_engage_each_limit_in_its_order -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def shortfall_carry(/def shortfall_carry_gone(/' --mutation 's/return \[rate \* (s + max(0\.0, s - p)) for/return [rate * s for/' -- uv run pytest tests/test_alpha_b4.py::test_the_shortfall_and_its_carry_charge_each_rollover_and_each_increase -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def quote_shortfall(/def quote_shortfall_gone(/' --mutation 's/max(0\.0, -e)/max(0.0, e)/' -- uv run pytest tests/test_alpha_b4.py::test_the_shortfall_and_its_carry_charge_each_rollover_and_each_increase -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def shortfall_carry(/def shortfall_carry_gone(/' --mutation 's/^    if not math\.isfinite(rate) or rate < 0:/    if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_shortfall_carry_refuses_a_rate_it_cannot_charge[negative]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def shortfall_carry(/def shortfall_carry_gone(/' --mutation 's/^    if not math\.isfinite(rate) or rate < 0:/    if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_shortfall_carry_refuses_a_rate_it_cannot_charge[nan]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def borrow_unavailable(/def borrow_unavailable_gone(/' --mutation 's/min(1\.0, max(0\.0, positions\[quote\]\[k\]) \/ total)/max(0.0, positions[quote][k]) \/ total/' -- uv run pytest tests/test_alpha_b4.py::test_borrow_unavailable_holds_the_legs_short_to_the_books_own_quote -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def borrow_unavailable(/def borrow_unavailable_gone(/' --mutation 's/ if i in on_quote else list(v) / if i not in on_quote else list(v) /' -- uv run pytest tests/test_alpha_b4.py::test_borrow_unavailable_holds_the_legs_short_to_the_books_own_quote -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def borrow_unavailable(/def borrow_unavailable_gone(/' --mutation 's/^    if quote not in positions:/    if False:/' -- uv run pytest tests/test_alpha_b4.py::test_borrow_unavailable_refuses_a_book_without_the_quote -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def per_year_counts(/def per_year_counts_gone(/' --mutation 's/^        counts\[str(t\.year)\] += int(flag)/        counts[str(t.year)] += 1/' -- uv run pytest tests/test_alpha_b4.py::test_the_per_year_helpers_key_each_value_by_its_close_year -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def per_year_sums(/def per_year_sums_gone(/' --mutation 's/^    return {year: math\.fsum(vs) for/    return {year: max(vs) for/' -- uv run pytest tests/test_alpha_b4.py::test_the_per_year_helpers_key_each_value_by_its_close_year -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def per_year_means(/def per_year_means_gone(/' --mutation 's/^    return {year: statistics\.fmean(vs) for/    return {year: max(vs) for/' -- uv run pytest tests/test_alpha_b4.py::test_the_per_year_helpers_key_each_value_by_its_close_year -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def per_year_counts(/def per_year_counts_gone(/' --mutation 's/^    if len(flags) != len(close_ts):/    if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_the_per_year_helpers_refuse_values_and_closes_of_unequal_length[counts]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def per_year_sums(/def per_year_sums_gone(/' --mutation 's/^    if len(values) != len(close_ts):/    if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_the_per_year_helpers_refuse_values_and_closes_of_unequal_length[sums]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b4.py --control 's/^def per_year_means(/def per_year_means_gone(/' --mutation 's/^    if len(values) != len(close_ts):/    if False:/' -- uv run pytest 'tests/test_alpha_b4.py::test_the_per_year_helpers_refuse_values_and_closes_of_unequal_length[means]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 7: Commit** — `feat(alpha): B4 trial 1's compute — a ratio leg's EUR return, the per-base exposures, the section 10 limits as one factor per bar, the BTC shortfall's carry and the legs held to the book's own BTC`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the trial subject, its pre-flight twin and the family key `B4` (D2–D9)

**Files:** Modify `cli/research/subjects.py`, `cli/registry/budget.py`, `tests/test_research_command.py`, `tests/test_trial_registry_provenance.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 1's functions; `cli/research/subjects.py`'s `_capturing_union`, `_b2_over`, `_ffill_btc`, `_asset_returns`, `_inverse_vol_weights`, `a2_book_returns`, `A2Config`, `_B2_A2_ARMS`, `_B2_LOOKBACK`, `PPY_4H`, `_B2_COST_PER_SIDE`, `_DECISIVE_START`, `_N_RESAMPLES`, `close_grid`, `net_of_cost`, `per_year_positions_differ`, `per_year_turnover`, `per_year_max_drawdown`, `book_turnover`, `benchmark_4h_net_of_cost`, `calendar_year_slices`, `a1_kill_bar`, `net_of_cost_verdict`, `sharpe`, `max_drawdown`, `_B2_ARM_A_BAR_KEYS`, `_B2_ARM_A_BAR_FLAGS`, `_ASSETS`, `Subject`, `SubjectError` and `ObservedReader`, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_b2_ohlc_rows`, `_B2_START`, `_B2_ASSETS`, `_B2_GRID`, `_B2_FULL_ANCHORS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_recording`, `_fake_kill_bar`, `_fake_head_to_head`, `_fake_benchmark`, `_anchor`, `_as_trial`, `_rolling_set`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`, `runner` and `app`. Produces the two subjects, the constants `_B4_LEGS`, `_B4_CARRY_RATE` and `_B4_N_TRIALS`, the halves `_b4_reads` and `_b4_inputs` and `_b4_engagement`, which Task 3's test reads, and the family key `B4`; the deflation row reads the count by name (`_DECLARED_COUNT`), and Task 5's literal reads it through the trial's `n_trials`.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - after the `from cli.alpha.b2 import (` block's closing `)` and before `from cli.alpha.errors import AlphaError`, `from cli.alpha.b4 import base_exposures, limit_factors, per_year_counts, per_year_means, per_year_sums`; after `from cli.benchmark.errors import BenchmarkError`, `from cli.costs.margin import margin_rate`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, after its `for name, (signal_key, *_) in _B2_LIQ_Z3.items():` loop and before its `assert subjects.SUBJECTS["b2-liq-tape-reading"]` line:

```python
    assert subjects.SUBJECTS["b4-ratio-legs"].metric_keys == _B4_METRIC_KEYS
    assert subjects.SUBJECTS["b4-ratio-legs-preflight"].metric_keys == _B4_PREFLIGHT_KEYS
```

  - after `test_the_b2_liq_z3_trial_refuses_a_plain_eval_and_another_count_before_any_read` and before `def _ruled_signal(`, two blank lines either side:

```python
_B4_SPEC = "docs/specs/00144-b4-ratio-legs-design.md"
_B4_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or no ratio leg holds a position at any stamp; no verdict, the "
    "trial unspent"
)
_B4_LEGS = {"ETH/BTC": "ETH", "SOL/BTC": "SOL"}
# Spec 00144 D9's keys, typed from the spec, never read off a subject.
_B4_ENGAGEMENT_KEYS = frozenset(
    {
        "ratio_first_weight",
        "primary_returns",
        "ratio_held_per_year",
        "stamps_positions_differ",
        "positions_differ_per_year",
        "turnover_b",
        "turnover_b_per_year",
        "shortfall_stamps_per_year",
        "shortfall_mean_per_year",
        "carry_per_year",
        "limit_engaged_per_year",
        "arm_a_limit_engaged",
    }
)
_B4_METRIC_KEYS = _B4_ENGAGEMENT_KEYS | {
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
    "no_borrow_head_to_head_mean_outperf_primary",
    "no_borrow_head_to_head_spa_p_primary",
    "no_borrow_ann_sharpe_noc",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "turnover_a",
    "turnover_a_per_year",
}
_B4_PREFLIGHT_KEYS = _B2_FULL_ANCHORS | _ARM_A_BAR_KEYS | _B4_ENGAGEMENT_KEYS
# The fixture's ETH/BTC misses this union stamp and holds a bar at a stamp 2 hours past the next, which no EUR asset has;
# SOL/BTC lists at bar `_B4_SOL_FROM`.
_B4_ETH_MISSES = 700
_B4_SOL_FROM = 300


def _b4_dataset(tmp_path: Path, *, start: datetime = _B2_START) -> Path:
    """`_b2_dataset`'s ten 4h series and the two ratio legs, each its base's prices over BTC's."""
    root = tmp_path / "data"
    rows = {asset: _b2_ohlc_rows(i * 0.7, start, False) for i, asset in enumerate(_B2_ASSETS)}
    for asset, asset_rows in rows.items():
        write_parquet(to_frame(asset_rows), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    for leg, first in (("ETH/BTC", 0), ("SOL/BTC", _B4_SOL_FROM)):
        ratio = [
            [row[0], *(f"{float(x) / float(q)}" for x, q in zip(row[1:6], btc[1:6])), *row[6:]]
            for row, btc in zip(rows[_B4_LEGS[leg]], rows["BTC"])
        ][first:]
        if leg == "ETH/BTC":
            off_grid = [ratio[_B4_ETH_MISSES + 1][0] + 2 * 3600, "1e6", "1e6", "1e6", "1e6", "1e6", "10", 3]
            ratio = [
                *ratio[:_B4_ETH_MISSES],
                *ratio[_B4_ETH_MISSES + 1 : _B4_ETH_MISSES + 2],
                off_grid,
                *ratio[_B4_ETH_MISSES + 2 :],
            ]
        write_parquet(to_frame(ratio), root / "ohlc-test" / f"{leg}/240.parquet")
    return root


def _b4_short_reads(n: int = 480) -> tuple[list[datetime], dict, dict]:
    """A union shorter than any the reads admit, for the books alone: BTC, ETH and SOL, BTC missing one stamp, ETH/BTC their
    cross from the first stamp with one missing, SOL/BTC from stamp 150."""
    h4_ts = [datetime(2017, 1, 1, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n)]
    shapes = {"BTC": (100.0, 1.001, 0.05, 7.0, 0.0), "ETH": (50.0, 1.002, 0.06, 5.0, 1.0), "SOL": (20.0, 1.0005, 0.08, 9.0, 2.0)}
    h4_prices = {
        a: [level * growth**k * (1 + depth * math.sin(k / period + phase)) for k in range(n)]
        for a, (level, growth, depth, period, phase) in shapes.items()
    }
    ratios = {leg: [p / q for p, q in zip(h4_prices[base], h4_prices["BTC"])] for leg, base in _B4_LEGS.items()}
    ratios["ETH/BTC"][400] = None
    ratios["SOL/BTC"][:150] = [None] * 150
    h4_prices["BTC"][300] = None
    return h4_ts, h4_prices, ratios


def _b4_own_books(h4_ts: list[datetime], h4_prices: dict, ratios: dict) -> dict:
    """The books of the reads, built here, never through the subject's halves."""
    n = len(h4_ts) - 1
    fed = _ffill_btc(h4_prices)
    priced = fed | ratios
    configs = [
        A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
        for lb, tv in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    ]

    def ensemble(prices):
        books = [a2_book_returns(prices, config=c)["asset_positions"] for c in configs]
        return {i: [statistics.mean(book[i][k] for book in books) for k in range(n)] for i in prices}

    legs = {leg: (base, "BTC") for leg, base in _B4_LEGS.items()}

    def limited(positions):
        factors, engaged = limit_factors(base_exposures(positions, legs))
        return {i: [p * f for p, f in zip(v, factors)] for i, v in positions.items()}, engaged

    raw_a, raw_b = ensemble(fed), ensemble(priced)
    covered = [
        1.0
        if raw_b["ETH/BTC"][k] + raw_b["SOL/BTC"][k] == 0
        else min(1.0, raw_b["BTC"][k] / (raw_b["ETH/BTC"][k] + raw_b["SOL/BTC"][k]))
        for k in range(n)
    ]
    weights = _inverse_vol_weights(priced, lookback=180)
    btc = fed["BTC"]
    return {
        "limited_a": limited(raw_a),
        "limited_b": limited(raw_b),
        "no_borrow": limited(raw_b | {leg: [p * c for p, c in zip(raw_b[leg], covered)] for leg in _B4_LEGS})[0],
        "first": {leg: next((k for k, w in enumerate(weights) if leg in w), n) for leg in _B4_LEGS},
        "returns": {a: _asset_returns(fed[a]) for a in h4_prices}
        | {
            leg: [None if r[k] is None or r[k + 1] is None else (r[k + 1] / r[k] - 1) * (btc[k + 1] / btc[k]) for k in range(n)]
            for leg, r in ratios.items()
        },
    }


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
def test_the_b4_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    assert (len(_B4_METRIC_KEYS), len(_B4_PREFLIGHT_KEYS)) == (48, 29)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B4_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b4_ratio_legs and trial.metric_keys == _B4_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b4_ratio_legs_verdict, _B4_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B4", 1) == ("B4", subjects._B4_N_TRIALS)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        f"{name}-preflight",
        (240,),
        _B2_ASSETS,
        _B4_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b4_ratio_legs_preflight and preflight.metric_keys == _B4_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5
    assert subjects._B4_CARRY_RATE == margin_rate("BTC", band="high") == 0.0002
    assert subjects._B4_LEGS == {leg: (base, "BTC") for leg, base in _B4_LEGS.items()}


# Adopting on every key the rule reads, the full window's head-to-head against it, so a rule reading the full window moves
# the adopt row; one leg held in one year, so a rule reading `all` stops it.
_B4_ADOPTING = {
    "arm_a_passes": 1,
    "ratio_held_per_year": {"ETH/BTC": {"2016": 0, "2017": 3}, "SOL/BTC": {"2016": 0, "2017": 0}},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
}
_B4_NEVER_HELD = {"ratio_held_per_year": {"ETH/BTC": {"2016": 0, "2017": 0}, "SOL/BTC": {"2016": 0, "2017": 0}}}


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="outperforms-significantly-from-the-first-weight"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B4_NEVER_HELD, None, id="no-leg-ever-held"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B4_NEVER_HELD, "passes": 0}, None, id="holding-read-before-passes"),
        pytest.param({"passes": 0}, "reject", id="arm-b-fails-its-bar"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="p-0.2"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001}, "reject", id="mean-negative"
        ),
    ],
)
def test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop(name, change, verdict):
    assert subjects.SUBJECTS[name].verdict({**_B4_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
def test_the_b4_reads_map_each_legs_closes_onto_the_union_and_read_no_other_stamp(tmp_path, name):
    root = _b4_dataset(tmp_path)
    frames = {i: pl.read_parquet(root / "ohlc-test" / f"{i}/EUR/240.parquet") for i in _B2_ASSETS}
    union = sorted(set().union(*(frame["ts"].to_list() for frame in frames.values())))
    reader = ObservedReader(root)

    h4_ts, h4_prices, ratios = subjects._b4_reads(name, reader, "ohlc-test", None, False)

    assert h4_ts == union and set(h4_prices) == set(_B2_ASSETS)
    for leg in _B4_LEGS:
        frame = pl.read_parquet(root / "ohlc-test" / f"{leg}/240.parquet")
        closes = dict(zip(frame["ts"].to_list(), frame["close"].to_list()))
        assert ratios[leg] == [closes.get(t) for t in union]
    assert next(k for k, r in enumerate(ratios["SOL/BTC"]) if r is not None) == _B4_SOL_FROM
    assert ratios["ETH/BTC"][_B4_ETH_MISSES] is None and max(r for r in ratios["ETH/BTC"] if r is not None) < 1e6
    assert set(reader.block()["ohlc-test"]["files"]) == {f"{i}/EUR/240.parquet" for i in _B2_ASSETS} | {
        f"{leg}/240.parquet" for leg in _B4_LEGS
    }


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
def test_the_b4_arms_agree_bit_for_bit_until_a_ratio_leg_takes_weight(monkeypatch, name):
    reads = _b4_short_reads()
    n = len(reads[0]) - 1
    ensembles = _recording(monkeypatch, "_b4_ensemble", lambda arguments, result: result)

    inputs = subjects._b4_inputs(subjects._B4Reads(*reads))

    (_, raw_a), (_, raw_b) = ensembles
    start = min(inputs.first_weight.values())
    differ = [k for k in range(n) if any(raw_b[a][k] != raw_a[a][k] for a in raw_a)]
    assert 0 < start == inputs.first_weight["ETH/BTC"] < inputs.first_weight["SOL/BTC"] < n
    assert differ and differ[0] >= start
    assert all(p == 0.0 for leg in _B4_LEGS for p in raw_b[leg][:start])
    assert any(p != 0.0 for leg in _B4_LEGS for p in raw_b[leg])


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
def test_the_b4_inputs_build_each_book_and_cost_each_leg_on_its_own_return(name):
    reads = _b4_short_reads()
    own = _b4_own_books(*reads)
    # The short union moves each book the inputs build: both legs held, the book short of BTC at some stamps, so the
    # no-borrow book differs from arm B.
    assert all(any(p != 0 for p in own["limited_b"][0][leg]) for leg in _B4_LEGS)
    assert own["no_borrow"] != own["limited_b"][0]

    inputs = subjects._b4_inputs(subjects._B4Reads(*reads))

    assert (inputs.h4_ts, inputs.h4_prices, inputs.close) == (reads[0], reads[1], [t + timedelta(hours=4) for t in reads[0][:-1]])
    assert inputs.first_weight == own["first"] and inputs.returns == own["returns"]
    assert (inputs.arm_a, inputs.engaged_a) == own["limited_a"] and (inputs.arm_b, inputs.engaged_b) == own["limited_b"]
    assert inputs.no_borrow == own["no_borrow"]


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
def test_the_b4_books_scale_each_bar_by_the_limits_factor_of_their_per_base_exposures(monkeypatch, name):
    positions = {"BTC": [0.5, 0.25, 0.0], "ETH": [0.25, 0.0, 0.125], "SOL": [0.0, 0.0, 0.0]}
    positions |= {"ETH/BTC": [0.25, 0.5, 0.125], "SOL/BTC": [0.0, 0.25, 0.0]}
    calls = _recording(monkeypatch, "limit_factors", lambda arguments, result: ([1.0, 0.5, 1.0], result[1]))

    limited, engaged = subjects._b4_limited(positions)

    ((arguments, (_, flags)),) = calls
    assert arguments["exposures"] == base_exposures(positions, {leg: (base, "BTC") for leg, base in _B4_LEGS.items()})
    assert limited == {i: [v[0], v[1] * 0.5, v[2]] for i, v in positions.items()} and engaged is flags


def _b4_built_inputs(n: int = 1_400) -> subjects._B4Inputs:
    """Books made by hand over `n` return indices — three assets and both legs, arm B short of BTC wherever the legs
    outweigh its BTC, a missing return on each leg, each limit engaged at a stamp of its own — for the metrics alone."""
    h4_ts = [datetime(2016, 6, 1, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n + 1)]
    first = {"ETH/BTC": 200, "SOL/BTC": 600}

    def wave(k: int, phase: float, depth: float) -> float:
        return depth * (1 + math.sin(k / 11 + phase)) / 2

    arm_a = {a: [wave(k, i, 0.2) for k in range(n)] for i, a in enumerate(("BTC", "ETH", "SOL"))}
    arm_b = {a: [0.9 * p for p in v] for a, v in arm_a.items()}
    arm_b |= {leg: [0.0 if k < first[leg] else wave(k, 3 + i, 0.15) for k in range(n)] for i, leg in enumerate(first)}
    no_borrow = arm_b | {leg: [0.5 * p for p in arm_b[leg]] for leg in first}
    returns = {i: [0.01 * math.sin(k / (3 + j) + j) for k in range(n)] for j, i in enumerate(arm_b)}
    for leg in first:
        returns[leg][first[leg] + 7] = None
    engaged_a = {limit: [False] * n for limit in ("gross", "net", "margin")}
    engaged_b = {limit: [k == 900 + j for k in range(n)] for j, limit in enumerate(("gross", "net", "margin"))}
    h4_prices = {"BTC": [100.0 + k for k in range(n + 1)]}
    close = [t + timedelta(hours=4) for t in h4_ts[:-1]]
    return subjects._B4Inputs(h4_ts, h4_prices, close, returns, first, arm_a, arm_b, no_borrow, engaged_a, engaged_b)


def _b4_own_net(inputs: subjects._B4Inputs, positions: dict, stress: float) -> list[float]:
    """Net of each instrument's turnover at 0.006 a side and of the carry on the BTC its legs outweigh, both times `stress`."""
    n = len(inputs.close)
    gross = net_of_cost(positions, {i: inputs.returns[i] for i in positions}, cost_per_side=stress * 0.006)
    held = (
        positions["BTC"]
        if "ETH/BTC" not in positions
        else [positions["BTC"][k] - positions["ETH/BTC"][k] - positions["SOL/BTC"][k] for k in range(n)]
    )
    short = [max(0.0, -x) for x in held]
    carry = [stress * 0.0002 * (s + max(0.0, s - p)) for s, p in zip(short, [0.0, *short[:-1]])]
    return [g - c for g, c in zip(gross, carry)]


def _b4_own_engagement(inputs: subjects._B4Inputs) -> dict:
    close, arm_b, n = inputs.close, inputs.arm_b, len(inputs.close)
    held = [arm_b["BTC"][k] - arm_b["ETH/BTC"][k] - arm_b["SOL/BTC"][k] for k in range(n)]
    short = [max(0.0, -x) for x in held]
    differ = per_year_positions_differ(inputs.arm_a | {leg: [0.0] * n for leg in _B4_LEGS}, arm_b, close)
    return {
        "ratio_first_weight": inputs.first_weight,
        "primary_returns": n - min(inputs.first_weight.values()),
        "ratio_held_per_year": {leg: per_year_counts([p != 0 for p in arm_b[leg]], close) for leg in _B4_LEGS},
        "stamps_positions_differ": sum(differ.values()),
        "positions_differ_per_year": differ,
        "turnover_b": book_turnover(arm_b),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "shortfall_stamps_per_year": per_year_counts([s > 0 for s in short], close),
        "shortfall_mean_per_year": per_year_means(short, close),
        "carry_per_year": per_year_sums([0.0002 * (s + max(0.0, s - p)) for s, p in zip(short, [0.0, *short[:-1]])], close),
        "limit_engaged_per_year": {limit: per_year_counts(flags, close) for limit, flags in inputs.engaged_b.items()},
        "arm_a_limit_engaged": {limit: sum(flags) for limit, flags in inputs.engaged_a.items()},
    }


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
def test_the_b4_trial_reads_each_metric_from_its_own_call(monkeypatch, name):
    inputs = _b4_built_inputs()
    n, close, start = len(inputs.close), inputs.close, min(inputs.first_weight.values())
    net_a, net_b, net_t = (_b4_own_net(inputs, book, 1.0) for book in (inputs.arm_a, inputs.arm_b, inputs.no_borrow))
    net_a_x15, net_b_x15 = (_b4_own_net(inputs, book, 1.5) for book in (inputs.arm_a, inputs.arm_b))
    # Arm B is short of BTC at some stamps, so the carry moves its net.
    assert net_b != net_of_cost(inputs.arm_b, {i: inputs.returns[i] for i in inputs.arm_b}, cost_per_side=0.006)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b4_metrics(inputs, n_trials=1)

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
        reads | {"book_net_of_cost": net_t[start:], "benchmark_net_of_cost": net_a[start:]},
    ]
    bar_a, headline = bars[0][1], bars[1][1]
    full, primary, no_borrow = (result for _, result in heads)
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
        "no_borrow_head_to_head_mean_outperf_primary": no_borrow["mean_outperformance"],
        "no_borrow_head_to_head_spa_p_primary": no_borrow["spa_p_value"],
        "no_borrow_ann_sharpe_noc": sharpe(net_t, periods_per_year=2190),
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "turnover_a": book_turnover(inputs.arm_a),
        "turnover_a_per_year": per_year_turnover(inputs.arm_a, close),
        **_b4_own_engagement(inputs),
    }
    assert n - start == metrics["primary_returns"] == 1_200


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
def test_the_b4_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book(monkeypatch, name):
    inputs = _b4_built_inputs()
    net_a = _b4_own_net(inputs, inputs.arm_a, 1.0)

    def refused(*args, **kwargs):
        raise AssertionError("the pre-flight read a head-to-head")

    monkeypatch.setattr(subjects, "net_of_cost_verdict", refused)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    costed = _recording(monkeypatch, "_b4_net", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b4_preflight_metrics(inputs, n_trials=1)

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
        **_b4_own_engagement(inputs),
    }


@pytest.mark.parametrize("name", ["b4-ratio-legs", "b4-ratio-legs-preflight"])
def test_a_b4_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
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


@pytest.mark.parametrize("name", ["b4-ratio-legs"])
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_the_b4_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b4_reads", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-189", "--family", "B4", "--n-trials", "2"]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials 2 is not 1, the count {name} declares and deflates at: pass --n-trials 1"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


def _no_close_column(path: Path) -> None:
    pl.read_parquet(path).drop("close").write_parquet(path)


def _not_parquet(path: Path) -> None:
    path.write_bytes(b"not a parquet file")


@pytest.mark.parametrize("name", ["b4-ratio-legs", "b4-ratio-legs-preflight"])
@pytest.mark.parametrize("leg", sorted(_B4_LEGS))
@pytest.mark.parametrize("spoil", [_no_close_column, _not_parquet], ids=["no-close-column", "not-parquet"])
def test_a_b4_subject_refuses_a_ratio_legs_file_it_cannot_read_naming_it(tmp_path, monkeypatch, name, leg, spoil):
    root = _b4_dataset(tmp_path)
    spoil(root / "ohlc-test" / f"{leg}/240.parquet")
    _anchor(monkeypatch, root)
    books = _recording(monkeypatch, "_b4_inputs", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"ohlc-test/{leg}/240.parquet: " in result.output and books == []
```

  - `_RULED_FIXTURES` gains `"b4-ratio-legs": _b4_dataset,` after `"b2-ratio-derisk": _b2_overlay_dataset,`; `_DECLARED_COUNT` gains `"b4-ratio-legs": "_B4_N_TRIALS",` after `"b2-ratio-derisk": "_B2_RATIO_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b4-ratio-legs": ("B4", 1),` after `"b2-ratio-derisk": ("B2", 3),`; `_CONTRACT_DATASETS` gains, after its `"b2-liq-z3-derisk-preflight"` entry:

```python
    "b4-ratio-legs": lambda tmp_path, subject: (_b4_dataset(tmp_path), _B2_START),
    "b4-ratio-legs-preflight": lambda tmp_path, subject: (_b4_dataset(tmp_path), _B2_START),
```

  - in `tests/test_trial_registry_provenance.py`, `test_the_budgets_and_buckets_are_the_master_plans_literals`' `assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "P1": None}, growth` becomes `assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "B4": "B", "P1": None}, growth`.

  **Author's call** — the tests hold each half on the fixture that moves it, and every one but the shared rows runs in seconds, so each is a probe's target: the reads on `_b4_dataset` — `_b2_dataset`'s ten 4h series and the two legs as their bases' prices over BTC's, ETH/BTC missing one union stamp and holding a bar 2 hours off the grid, SOL/BTC listing at bar 300 — through the subject's own reader, the legs' closes held to the files' by stamp and the block to the twelve files; the books on `_b4_short_reads`, a 480-stamp union the reads would refuse (the kill bar's decisive window needs 1,382 return indices), its BTC missing one stamp so `_ffill_btc` moves the legs' EUR returns and the EUR legs' own: the bit-identity read off the two ensembles `_b4_ensemble` returns, the first divergence at or after the first weight, and every field of `_b4_inputs` held to `_b4_own_books`, the test's own build through `a2_book_returns` and Task 1's functions, never the subject's halves; the limits' wiring on a five-instrument book with the factor rewritten at one bar, so the scale and the per-base exposures it reads are each seen; the metrics and the pre-flight's on `_b4_built_inputs`, books made by hand over 1,400 return indices with arm B short of BTC and each limit engaged at a stamp of its own, under argument-derived stand-ins for the bar, the head-to-head and the benchmark, every call's arguments and every key held to `_b4_own_net` and `_b4_own_engagement`, the test's own expressions; the rule row by row. Every new function is parametrised by the subject's name, so `tests/retired_subjects.py`'s hook marks each case `retired` once Task 6 retires the two names. The shared rows — the contract, tracked-spec, shared-defaults and deflation rows, which `_RULED_FIXTURES`, `_DECLARED_COUNT` and `_CONTRACT_DATASETS` reach — run both subjects end to end on `_b4_dataset`, the trial's arm B, twin and bars among them.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_research_command.py -k "b4_ or ruled_subjects_declare or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt`: collection completes and every selected case fails at its call — on a key `SUBJECTS` lacks, a function `subjects` lacks, or the families literal `SUBJECTS` does not yet hold (measured on the authoring tree against the base module: `31 failed, 764 deselected`); and `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt`, measured `1 failed`.
- [ ] **Step 3: Implement in `cli/research/subjects.py` and `cli/registry/budget.py`** — after the `from cli.alpha.b2 import (` block's closing `)`:

```python
from cli.alpha.b4 import (
    base_exposures,
    borrow_unavailable,
    limit_factors,
    per_year_counts,
    per_year_means,
    per_year_sums,
    quote_shortfall,
    ratio_eur_returns,
    scale_bars,
    shortfall_carry,
)
```

  after `_B2_RERISK_KEYS`' closing `)` and before `SUBJECTS: dict[str, Subject] = {`, two blank lines either side:

```python
# docs/specs/00144 D2-D9: B4's trial 1, the ETH/BTC and SOL/BTC ratio legs added to the adopted A2-4h ensemble as two more
# instruments, on a frozen set's full history.
_B4_LEGS = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}
_B4_CARRY_RATE = 0.0002  # docs/specs/00144 D5: margin_rate("BTC", band="high"), the extended currency's rollover per 4h
_B4_N_TRIALS = 1  # docs/specs/00144 D8: fixed by the spec's hash; a different count is a new subject


class _B4Reads(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    ratios: dict[str, list[float | None]]


def _b4_reads(subject: str, reader: ObservedReader, dataset: str, window: tuple[str, str] | None, accept_holes: bool) -> _B4Reads:
    """The union, the window's refusal and the two legs' closes on its stamps, and no compute."""
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
    ratios = {}
    for leg in _B4_LEGS:
        relpath = f"{leg}/240.parquet"
        try:
            frame = reader.read_series(dataset, relpath, window=window)
            closes = dict(zip(frame["ts"].to_list(), frame["close"].to_list(), strict=True))
        except pl.exceptions.PolarsError as exc:
            raise SubjectError(f"{dataset}/{relpath}: {exc}") from exc
        # A bar at a stamp no EUR asset has is not read (docs/specs/00144 D2).
        ratios[leg] = [closes.get(t) for t in h4_ts]
    return _B4Reads(h4_ts, h4_prices, ratios)


class _B4Inputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    returns: dict[str, list[float | None]]
    first_weight: dict[str, int]
    arm_a: dict[str, list[float]]
    arm_b: dict[str, list[float]]
    no_borrow: dict[str, list[float]]
    engaged_a: dict[str, list[bool]]
    engaged_b: dict[str, list[bool]]


def _b4_ensemble(prices: dict[str, list[float | None]]) -> dict[str, list[float]]:
    arms = [
        a2_book_returns(
            prices,
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
    return {i: [statistics.mean(arm[i][k] for arm in arms) for k in range(len(prices["BTC"]) - 1)] for i in prices}


def _b4_limited(positions: dict[str, list[float]]) -> tuple[dict[str, list[float]], dict[str, list[bool]]]:
    factors, engaged = limit_factors(base_exposures(positions, _B4_LEGS))
    return scale_bars(positions, factors), engaged


def _b4_inputs(reads: _B4Reads) -> _B4Inputs:
    """Both arms' positions, the twin's and the returns they are costed on, and no return of a book: the pre-flight reads
    this half alone."""
    h4_ts, h4_prices, ratios = reads
    fed = _ffill_btc(h4_prices)
    priced = fed | ratios
    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))
    raw_b = _b4_ensemble(priced)
    arm_b, engaged_b = _b4_limited(raw_b)
    no_borrow, _ = _b4_limited(borrow_unavailable(raw_b, _B4_LEGS, "BTC"))
    weights = _inverse_vol_weights(priced, lookback=_B2_LOOKBACK)
    first_weight = {leg: next((k for k, w in enumerate(weights) if leg in w), len(weights)) for leg in _B4_LEGS}
    returns = {a: _asset_returns(fed[a]) for a in h4_prices} | {leg: ratio_eur_returns(ratios[leg], fed["BTC"]) for leg in _B4_LEGS}
    return _B4Inputs(h4_ts, h4_prices, close_grid(h4_ts), returns, first_weight, arm_a, arm_b, no_borrow, engaged_a, engaged_b)


def _b4_shortfall(positions: dict[str, list[float]]) -> list[float]:
    return quote_shortfall(base_exposures(positions, _B4_LEGS), "BTC")


def _b4_net(positions: dict[str, list[float]], returns: dict[str, list[float | None]], *, stress: float) -> list[float]:
    """Net of each instrument's own turnover at the family's rate and of the BTC shortfall's carry, both times `stress`."""
    net = net_of_cost(positions, {i: returns[i] for i in positions}, cost_per_side=stress * _B2_COST_PER_SIDE)
    carry = shortfall_carry(_b4_shortfall(positions), rate=stress * _B4_CARRY_RATE)
    return [x - c for x, c in zip(net, carry, strict=True)]


def _b4_arm_a_bar(inputs: _B4Inputs, *, n_trials: int) -> tuple[dict, list[float], list[float]]:
    net_a = _b4_net(inputs.arm_a, inputs.returns, stress=1.0)
    net_a_x15 = _b4_net(inputs.arm_a, inputs.returns, stress=1.5)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=_B2_COST_PER_SIDE)
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


def _b4_engagement(inputs: _B4Inputs) -> dict:
    close, arm_b = inputs.close, inputs.arm_b
    shortfall = _b4_shortfall(arm_b)
    differ = per_year_positions_differ(inputs.arm_a | {leg: [0.0] * len(close) for leg in _B4_LEGS}, arm_b, close)
    return {
        "ratio_first_weight": inputs.first_weight,
        "primary_returns": len(close) - min(inputs.first_weight.values()),
        "ratio_held_per_year": {leg: per_year_counts([p != 0 for p in arm_b[leg]], close) for leg in _B4_LEGS},
        "stamps_positions_differ": sum(differ.values()),
        "positions_differ_per_year": differ,
        "turnover_b": book_turnover(arm_b),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "shortfall_stamps_per_year": per_year_counts([s > 0 for s in shortfall], close),
        "shortfall_mean_per_year": per_year_means(shortfall, close),
        "carry_per_year": per_year_sums(shortfall_carry(shortfall, rate=_B4_CARRY_RATE), close),
        "limit_engaged_per_year": {name: per_year_counts(flags, close) for name, flags in inputs.engaged_b.items()},
        "arm_a_limit_engaged": {name: sum(flags) for name, flags in inputs.engaged_a.items()},
    }


def _b4_metrics(inputs: _B4Inputs, *, n_trials: int) -> dict:
    close, start = inputs.close, min(inputs.first_weight.values())
    if len(close) - start < 2:
        raise ValidationError(
            f"{len(close) - start} of its return indices follow a ratio leg's first weight, and the head-to-head from it needs 2"
        )
    net_b = _b4_net(inputs.arm_b, inputs.returns, stress=1.0)
    net_b_x15 = _b4_net(inputs.arm_b, inputs.returns, stress=1.5)
    net_t = _b4_net(inputs.no_borrow, inputs.returns, stress=1.0)
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
    for prefix, book, label, first in (
        ("", net_b, "full", 0),
        ("", net_b, "primary", start),
        ("no_borrow_", net_t, "primary", start),
    ):
        verdict = net_of_cost_verdict(book[first:], net_a[first:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
        head_to_head[f"{prefix}head_to_head_mean_outperf_{label}"] = verdict["mean_outperformance"]
        head_to_head[f"{prefix}head_to_head_spa_p_{label}"] = verdict["spa_p_value"]
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
        "no_borrow_ann_sharpe_noc": sharpe(net_t, periods_per_year=PPY_4H),
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "turnover_a": book_turnover(inputs.arm_a),
        "turnover_a_per_year": per_year_turnover(inputs.arm_a, close),
        **_b4_engagement(inputs),
    }


def _b4_preflight_metrics(inputs: _B4Inputs, *, n_trials: int) -> dict:
    """Arm A's anchors and bar and the engagement: no return of arm B or of the twin."""
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
        **_b4_engagement(inputs),
    }


def _b4_build(
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
        return compute(_b4_inputs(_b4_reads(subject, reader, dataset, window, accept_holes)), n_trials=_B4_N_TRIALS)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, RiskError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b4_ratio_legs(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b4_build("b4-ratio-legs", _b4_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b4_ratio_legs_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b4_build("b4-ratio-legs-preflight", _b4_preflight_metrics, reader, dataset, window, as_of, accept_holes)


# docs/specs/00144 D8's matrix and the two instrument findings its metrics show: a change to it is a new spec and a new
# trial, never an edit here.
def _b4_ratio_legs_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(n for held in m["ratio_held_per_year"].values() for n in held.values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"


# docs/specs/00144 D9's keys: the engagement both subjects carry, the trial's and the pre-flight's.
_B4_ENGAGEMENT_KEYS = frozenset(
    {
        "ratio_first_weight",
        "primary_returns",
        "ratio_held_per_year",
        "stamps_positions_differ",
        "positions_differ_per_year",
        "turnover_b",
        "turnover_b_per_year",
        "shortfall_stamps_per_year",
        "shortfall_mean_per_year",
        "carry_per_year",
        "limit_engaged_per_year",
        "arm_a_limit_engaged",
    }
)
_B4_METRIC_KEYS = _B4_ENGAGEMENT_KEYS | {
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
    "no_borrow_head_to_head_mean_outperf_primary",
    "no_borrow_head_to_head_spa_p_primary",
    "no_borrow_ann_sharpe_noc",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "turnover_a",
    "turnover_a_per_year",
}
_B4_PREFLIGHT_KEYS = (
    _B2_ARM_A_BAR_KEYS
    | _B4_ENGAGEMENT_KEYS
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

  `SUBJECTS` gains, after its `"b2-liq-z3-derisk-preflight"` entry and before its closing `}`:

```python
    "b4-ratio-legs": Subject(
        "b4-ratio-legs",
        (240,),
        _ASSETS,
        _build_b4_ratio_legs,
        spec="docs/specs/00144-b4-ratio-legs-design.md",
        metric_keys=_B4_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b4_ratio_legs_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or no ratio leg holds a position at any stamp; no "
            "verdict, the trial unspent"
        ),
        family="B4",
        n_trials=_B4_N_TRIALS,
    ),
    "b4-ratio-legs-preflight": Subject(
        "b4-ratio-legs-preflight",
        (240,),
        _ASSETS,
        _build_b4_ratio_legs_preflight,
        spec="docs/specs/00144-b4-ratio-legs-design.md",
        metric_keys=_B4_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
```

  and in `cli/registry/budget.py`, `BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "P1": None}` becomes `BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "B4": "B", "P1": None}`, its comment unchanged (spec 00144 D9: a new family joins with its bucket in a reviewed pull request quoting the ruling, the owner's "B4-legs (Recommended)").
- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `) or \`b2-liq-z3-derisk-preflight\` (` becomes `), \`b2-liq-z3-derisk-preflight\` (`, and the row's closing `` with no return of the halved book; it has no rule, so its run is kept with `--reading`). | `` becomes:

```markdown
with no return of the halved book; it has no rule, so its run is kept with `--reading`), `b4-ratio-legs` (the A2 4h ensemble against the same three arms run on twelve instruments, the ten EUR assets and the ETH/BTC and SOL/BTC ratio pairs, long-only, the BTC a ratio position sells netted against the book's own BTC and the rest borrowed at the BTC rollover; the 4h series of `--dataset`, a frozen set only, its two ratio pairs among them) or `b4-ratio-legs-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the ratio pairs' positions, the BTC they borrow and the limits they engage, with no return of the twelve-instrument book; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the shared rows measured at 10 s or more on the authoring tree (call time):

```text
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b4-ratio-legs]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-ratio-legs-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-ratio-legs-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b4-ratio-legs-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b4-ratio-legs]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's two commands, measured `31 passed, 782 deselected` (about 6 s) and `1 passed`; then the shared rows, `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_research_command.py -k "b4-ratio-legs and not b4_" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt`, one plain blocking call, `timeout` 600000 ms (measured `19 passed, 794 deselected` in 133.59 s, the shared-defaults rows 40.41 s and 34.23 s, the evaluates rows 21.05 s and 17.22 s, the deflation row 17.80 s, every other under 1 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py cli/registry/budget.py tests/test_research_command.py tests/test_trial_registry_provenance.py README.md tests/slow-cases.txt`; the Global Constraints' `T` over the six paths in its three parts (measured on the authoring tree: `639 passed, 174 deselected in 496.84s`, `71 passed, 742 deselected in 89.92s`; the other thirty-nine direct readers `4281 passed, 70 deselected in 117.81s`, Task 3's data-marked file among them and deselected); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the authoring tree, 43 of 43); the shared-defaults, evaluate, deflate, contract, tracked-spec and metric-keys rows and the ruled-subjects literal are new rows of existing tests, not new guards, and are not probed; the budgets literal is the guard this task changes, and its row is the block's last:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/"b4-ratio-legs-preflight": Subject(/,/^    ),/s/metric_keys=_B4_PREFLIGHT_KEYS,/metric_keys=_B4_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/^_B4_CARRY_RATE = 0\.0002/_B4_CARRY_RATE = 0.0001/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/^_B4_N_TRIALS = 1\b/_B4_N_TRIALS = 2/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/"adopt" if m\["head_to_head_spa_p_primary"\] < 0\.05 else "park"/"park"/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[outperforms-significantly-from-the-first-weight-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held/if not any(n for held/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-a-fails-its-bar-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held in m\["ratio_held_per_year"\]\.values() for n in held\.values()):/if not m["arm_a_passes"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[no-leg-ever-held-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held/if not any(n for held/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-a-read-before-passes-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/if not m\["arm_a_passes"\] or not any(n for held in m\["ratio_held_per_year"\]\.values() for n in held\.values()):/if not m["arm_a_passes"]:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[holding-read-before-passes-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/    if not m\["passes"\]:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-b-fails-its-bar-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/m\["head_to_head_spa_p_primary"\] < 0\.05/m["head_to_head_spa_p_primary"] <= 0.05/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[p-at-exactly-0.05-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/"adopt" if m\["head_to_head_spa_p_primary"\] < 0\.05 else "park"/"adopt"/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[p-0.2-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/    if m\["head_to_head_mean_outperf_primary"\] > 0:$/    if m["head_to_head_mean_outperf_primary"] >= 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-at-exactly-0-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_ratio_legs_verdict(/,/^_B4_ENGAGEMENT_KEYS/s/    if m\["head_to_head_mean_outperf_primary"\] > 0:$/    if m["head_to_head_mean_outperf_full"] > 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-negative-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/^        ratios\[leg\] = \[closes\.get(t) for t in h4_ts\]/        ratios[leg] = [*closes.values()][: len(h4_ts)]/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_reads_map_each_legs_closes_onto_the_union_and_read_no_other_stamp[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_inputs(/,/^def /s/weights = _inverse_vol_weights(priced, /weights = _inverse_vol_weights(fed, /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_arms_agree_bit_for_bit_until_a_ratio_leg_takes_weight[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))/    arm_a, engaged_a = _b4_limited(_b4_ensemble(priced))/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_inputs_build_each_book_and_cost_each_leg_on_its_own_return[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/    no_borrow, _ = _b4_limited(borrow_unavailable(raw_b, _B4_LEGS, "BTC"))/    no_borrow, _ = _b4_limited(raw_b)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_inputs_build_each_book_and_cost_each_leg_on_its_own_return[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/ratio_eur_returns(ratios\[leg\], fed\["BTC"\])/ratio_eur_returns(ratios[leg], h4_prices["BTC"])/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_inputs_build_each_book_and_cost_each_leg_on_its_own_return[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_inputs(/,/^def /s/returns = {a: _asset_returns(fed\[a\]) for a in h4_prices}/returns = {a: _asset_returns(h4_prices[a]) for a in h4_prices}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_inputs_build_each_book_and_cost_each_leg_on_its_own_return[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/    factors, engaged = limit_factors(base_exposures(positions, _B4_LEGS))/    factors, engaged = limit_factors(positions)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_books_scale_each_bar_by_the_limits_factor_of_their_per_base_exposures[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_limited(/,/^def /s/    return scale_bars(positions, factors), engaged/    return positions, engaged/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_books_scale_each_bar_by_the_limits_factor_of_their_per_base_exposures[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/    carry = shortfall_carry(_b4_shortfall(positions), rate=stress \* _B4_CARRY_RATE)/    carry = shortfall_carry(_b4_shortfall(positions), rate=_B4_CARRY_RATE)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_net(/,/^def /s/    return \[x - c for x, c in zip(net, carry, strict=True)\]/    return net/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_metrics(/,/^def /s/close, start = inputs\.close, min(inputs\.first_weight\.values())/close, start = inputs.close, max(inputs.first_weight.values())/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/        ("no_borrow_", net_t, "primary", start),/        ("no_borrow_", net_b, "primary", start),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/    net_b_x15 = _b4_net(inputs\.arm_b, inputs\.returns, stress=1\.5)/    net_b_x15 = _b4_net(inputs.arm_b, inputs.returns, stress=1.0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_metrics(/,/^def /s/"arm_a_passes": int(bar_a\["passes"\]),/"arm_a_passes": int(headline["passes"]),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_metrics(/,/^def /s/"spa_p_full": headline\["spa_p_value_full"\],/"spa_p_full": headline["spa_p_value"],/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_metrics(/,/^def /s/"arm_a_max_drawdown": max_drawdown(net_a),/"arm_a_max_drawdown": max_drawdown(net_b),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/    shortfall = _b4_shortfall(arm_b)/    shortfall = _b4_shortfall(inputs.arm_a)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/for name, flags in inputs\.engaged_b\.items()},/for name, flags in inputs.engaged_a.items()},/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/"primary_returns": len(close) - min(inputs\.first_weight\.values()),/"primary_returns": len(close) - max(inputs.first_weight.values()),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation 's/"no_borrow_ann_sharpe_noc": sharpe(net_t, /"no_borrow_ann_sharpe_noc": sharpe(net_b, /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_reads_each_metric_from_its_own_call[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_arm_a_bar(/,/^def /s/    net_a = _b4_net(inputs\.arm_a, inputs\.returns, stress=1\.0)/    net_a = _b4_net(inputs.arm_b, inputs.returns, stress=1.0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_preflight_metrics(/,/^def /s/ \* _B2_COST_PER_SIDE \* PPY_4H,/ * 1.5 * _B2_COST_PER_SIDE * PPY_4H,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_preflight_reads_arm_a_and_the_engagement_and_costs_no_other_book[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_subject_refuses_as_of_before_any_read[b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_subject_refuses_as_of_before_any_read[b4-ratio-legs-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/"b4-ratio-legs": Subject(/,/^    ),/s/verdict=_b4_ratio_legs_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/"b4-ratio-legs": Subject(/,/^    ),/s/n_trials=_B4_N_TRIALS,/n_trials=2,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_reads(/,/^def /s/        except pl\.exceptions\.PolarsError as exc:/        except ZeroDivisionError as exc:/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_subject_refuses_a_ratio_legs_file_it_cannot_read_naming_it[no-close-column-ETH/BTC-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_reads(/,/^def /s/        except pl\.exceptions\.PolarsError as exc:/        except ZeroDivisionError as exc:/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_subject_refuses_a_ratio_legs_file_it_cannot_read_naming_it[not-parquet-SOL/BTC-b4-ratio-legs]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_ratio_legs(/def _build_b4_ratio_legs_gone(/' --mutation '/^def _b4_reads(/,/^def /s/        except pl\.exceptions\.PolarsError as exc:/        except ZeroDivisionError as exc:/' -- uv run pytest 'tests/test_research_command.py::test_a_b4_subject_refuses_a_ratio_legs_file_it_cannot_read_naming_it[not-parquet-ETH/BTC-b4-ratio-legs-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/registry/budget.py --control 's/^BUDGET: dict/BUDGET_gone: dict/' --mutation 's/"B4": "B", //' -- uv run pytest tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 9: Commit** — `feat(research): B4 trial 1's subjects — the ETH/BTC and SOL/BTC legs on the A2 ensemble and their pre-flight twin on a frozen set's full history, and the family key B4 in bucket B`, the message carrying the test result lines, the probe block's commands and verdicts, the owner's ruling the new family joins under, quoted ("B4-legs (Recommended)"), and the two trailer lines.

## Task 3: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D10)

**Files:** Create `tests/test_research_b4_ratio_legs_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 2's `_b4_reads`, `_b4_inputs`, `_b4_engagement` and `_ASSETS`; `cli.alpha.b1.book_turnover`; `cli.registry.observed.ObservedReader`, `cli.registry.record.compute_hash` and `cli.research.command._DATA_ROOT`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`. Produces one test, its own `trial_inputs()`, and the module names `BLOCK`, `VOUCHED`, `RETURN_INDICES`, `ENGAGEMENT`, `TURNOVER_B` and `CARRY_PER_YEAR`, which Task 4's check programs import. No test computes a bar or a return of a book.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, record 57's figures read off the committed record:

```python
"""B4 trial 1's inputs half against spec 00144's measured basis: positions, exposures, the shortfall, its carry and
turnover, and no return of a book."""

from __future__ import annotations

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
# Copied from the spec's measured basis, never from a run.
BLOCK = "9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
ENGAGEMENT = {
    "ratio_first_weight": {"ETH/BTC": 5_442, "SOL/BTC": 17_079},
    "primary_returns": 21_895,
    "ratio_held_per_year": {
        "ETH/BTC": _YEARS
        | {
            "2016": 644,
            "2017": 1_443,
            "2018": 696,
            "2019": 1_010,
            "2020": 1_376,
            "2021": 1_582,
            "2022": 1_141,
            "2023": 1_115,
            "2024": 939,
            "2025": 1_127,
            "2026": 324,
        },
        "SOL/BTC": _YEARS | {"2021": 764, "2022": 920, "2023": 1_401, "2024": 1_240, "2025": 1_072, "2026": 285},
    },
    "stamps_positions_differ": 19_648,
    "positions_differ_per_year": _YEARS
    | {
        "2016": 1_434,
        "2017": 2_160,
        "2018": 1_432,
        "2019": 2_001,
        "2020": 2_060,
        "2021": 2_097,
        "2022": 1_919,
        "2023": 2_155,
        "2024": 2_031,
        "2025": 1_962,
        "2026": 397,
    },
    "shortfall_stamps_per_year": _YEARS
    | {
        "2016": 192,
        "2017": 582,
        "2018": 544,
        "2019": 582,
        "2020": 903,
        "2021": 1_430,
        "2022": 1_273,
        "2023": 973,
        "2024": 920,
        "2025": 1_025,
        "2026": 355,
    },
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
}
# Arm B's turnover at two decimals, and the carry per close year at six.
TURNOVER_B = 157.65
CARRY_PER_YEAR = {
    "2016": 0.001688,
    "2017": 0.003143,
    "2018": 0.006144,
    "2019": 0.006081,
    "2020": 0.007869,
    "2021": 0.009872,
    "2022": 0.011097,
    "2023": 0.013902,
    "2024": 0.010192,
    "2025": 0.007084,
    "2026": 0.006064,
}


def trial_inputs():
    """The trial's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b4_inputs(subjects._b4_reads("b4-ratio-legs", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "ohlc-full/*/BTC/240.parquet"),
    reason="the frozen ohlc-full set or its two ratio legs are absent under data/",
)
def test_the_ratio_legs_inputs_reproduce_the_measured_basis_and_record_57s_arm_a():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    block = reader.block()
    assert compute_hash(block) == BLOCK and reader.vouched_status() == VOUCHED
    assert len(inputs.close) == RETURN_INDICES
    # Arm A is record 57's: the same ten files, and its turnover to the last bit.
    record = _trials()[57]
    assert {p: h for p, h in block["ohlc-full"]["files"].items() if "/EUR/" in p} == record["datasets"]["ohlc-full"]["files"]
    assert book_turnover(inputs.arm_a) == record["metrics"]["turnover_a"]
    start = min(ENGAGEMENT["ratio_first_weight"].values())
    assert all(inputs.arm_b[a][:start] == inputs.arm_a[a][:start] for a in subjects._ASSETS)
    engagement = subjects._b4_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert round(engagement["turnover_b"], 2) == TURNOVER_B
    assert {year: round(v, 6) for year, v in engagement["carry_per_year"].items() if v} == CARRY_PER_YEAR
```

  **Author's call** — the case holds the subject's inputs half to the spec's first program, which built both arms by its own expression and the limits, the shortfall and the twin written out, so the measured figures and the subject's code are two derivations that must agree; arm A to record 57 by its ten files and its turnover to the last bit, the stored figure, never a second typing; the integer engagement exactly, the turnover at the two decimals and the carry at the six the basis printed.
- [ ] **Step 2: Run it** — with `data/ohlc-full` linked in this worktree: `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_research_b4_ratio_legs_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, a call of 165.14 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b4_ratio_legs_basis.py::test_the_ratio_legs_inputs_reproduce_the_measured_basis_and_record_57s_arm_a
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b4_ratio_legs_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths (measured `18 passed, 1 deselected in 18.55s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt` (measured `327 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B4 trial 1's inputs half against the measured basis — the block, the first weights, the legs' holding, the BTC shortfall and its carry, the limits and arm B's turnover, and record 57's arm A`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_b4_ratio_legs_basis.py::test_the_ratio_legs_inputs_reproduce_the_measured_basis_and_record_57s_arm_a`, the line `It reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the loop's pick (spec 00144's Ruling, D1) and then **Author's call** the trial's conventions, plan 00143's shape, so that both stand in the log before any return of arm B is read:

```markdown
[iter-189] B4's first step — trial 1, the two ratio legs added to the A2-4h ensemble as instruments, the loop's pick under the owner's run instruction (Decision: 1)
  Said, attended, 2026-10-23, after B2's close, asked which family comes next: "B4-legs (Recommended)" (the `[iter-188]` entry above). Then, launching this unattended run: "continue working on B4-legs and other research strates. Ignore the wall time clock gate, but do not pick up new topics after 09:00Z". B4 is worked under T0016 and no new topic is registered; its first step is the loop's pick under that instruction. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)" and the two `[iter-176]` rulings.
  1. **Trial 1 directly: ETH/BTC and SOL/BTC added to the adopted A2-4h ensemble as two more instruments, A2's own configuration unchanged** — master plan §5's own form ("cheap to add to A2 as extra instruments"); no free knob, so a screening reading would have nothing to choose between. Spec 00144, count 1: the legs take basket weight from return index 5,442 (ETH/BTC) and 17,079 (SOL/BTC) of 27,337, hold a position at 11,397 and 5,682, the book borrows BTC at 8,779 at a carry of 0.67 % of NAV a year, and arm B trades 7.84 % more than arm A (spec 00144's measured basis); one B slot, 13 to 12. Chosen.
  2. **A no-slot reading first** — the ratio legs' forward returns by trend state; it screens one cell with no alternative cell and spends an iteration before the only trial the family's premise names.
  3. **A standalone ratio sleeve beside arm A at a fixed weight** — the weight is a knob the master plan does not name, and the sleeve alone, market-neutral and low-volatility, cannot clear the frozen benchmark's bar by construction.

[iter-189] B4 trial 1's conventions, pinned by spec 00144 before its hash (Decision: 1)
  The trial's details are fixed in the spec, reviewed, and frozen by its sha256, its record's `spec_hash`, before any return of arm B or of its borrow-unavailable twin, head-to-head or bar leg of arm B is computed over the data; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00128, 00133, 00137 and 00143 fixed staying theirs.
  1. **As the spec pins them, the BTC a ratio leg sells netted against the book's own BTC and the shortfall carried** — one trial and its pre-flight twin, the loop's pick (D1); the venue's own ETH/BTC and SOL/BTC 4h pairs of frozen `ohlc-full`, full history, mapped onto the ten EUR assets' union stamps, not a synthetic cross (D2); arm A the adopted ensemble, record 57's to the bit, arm B its three A2 arms on twelve instruments, long-only, arm A's to the bit until a leg takes basket weight (D3); a leg's EUR return its BTC-denominated gain converted at the bar's closing BTC/EUR, every instrument at 0.006 a side on its own turnover, one cost function for every book (D4); each position decomposed into per-base exposures, the BTC the legs take beyond the book's own borrowed at 0.0002 per 4h rollover plus the opening charge on each increase, never an alt borrow (D5); §10's gross cap, net band and margin floor on both arms' per-base exposures as one factor per bar, the three calls with their engaged bars rather than the builder's stack (D6); the borrow-unavailable twin recorded beside the matrix (D7); record 57's bar at count 1 and `var_trials` 0.0, the head-to-head from the first ratio weight deciding, the matrix through `_b4_ratio_legs_verdict`, the author's park variants ETH/BTC alone and the symmetric legs, the count fixed by the hash (D8); the family key `B4` in bucket B, the subjects `b4-ratio-legs` and `b4-ratio-legs-preflight`, the variant `B4-ratio-legs-a2eq-full-v1`, 48 and 29 keys, the build in three halves (D9); no `--verdict`, notes naming only what is fixed before the run (D10); an adopt recorded, never deployed (D11). Chosen.
  2. **The symmetric legs, short ETH/BTC and SOL/BTC too** — an ETH or SOL shortfall borrowed at 0.0004 per 4h, about 88 % a year, and a mixed short policy A2 has no path for.
  3. **Each ratio leg a full margin position** — the whole notional carried at 22–88 % a year, an implementation no operator holding the book's BTC would choose.
  4. **The other alternatives weighed** — a synthetic cross of the EUR legs, two fees per rebalance where the pair pays one and not the instrument the universe selects; `apply_whole_book_limits` in place of the three calls, which returns no limit's engaged bars; the full window deciding, which adds the 5,442 return indices at which the two books are one to the bit; a drawdown leg in the matrix, which B4's premise does not name; a count raised in place.
  Source: spec 00144 (D1–D11), its **Author's call**s and the calls it carries from the owner and specs 00128, 00133, 00137 and 00143; the owner's words quoted in the pick above.
```

  staged alone, its gate `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt` (measured in a scratch worktree, the two entries appended, `50 passed`) and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-189] B4's first step — the loop's pick, trial 1 with the two ratio legs as instruments — and B4 trial 1's conventions, pinned by spec 00144 before its hash`. T0016's B4 trigger after trial 1 greps for `B4.s next step after trial 1`, which neither header carries (measured in the scratch worktree, the check prints 0 with the entries appended).
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes or reads arm B's or the twin's returns, a head-to-head or a bar leg of either, or runs either subject over the real data, before the spec's hash, and the data-gated case runs with the frozen full set linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D10)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00144-b4-ratio-legs-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; arm A's code path since this branch's cut — the spec's basis lists it from record 57's run to the cut — `git log --oneline 2e7656294..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1–2's commits and their fixes alone; any other commit is named, step 4's data test deciding whether it moved the inputs half.
- [ ] **Step 2: D10 (1), the spec hash** — `sha256sum docs/specs/00144-b4-ratio-legs-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D10 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record or a reading another branch's merged PR carries — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0016's — then takes a delta read of the merge in place of re-running step 1: step 1's arm-A log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 3 step 6's sentence with its "before the spec's hash" read "before Task 5's run", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the trial — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. A B4 record another branch landed raises `required_n("B4")` above 1, and the run is then refused before its fit (D8): the trial stops, T0016's, a further count a new subject under a new spec. The check has two sites, this step and Task 5 step 1, and both take this path.
- [ ] **Step 4: D10 (3), the data test on the run's tree** — `mkdir -p .tmp/plan-00144 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b4_ratio_legs_basis.py -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt > .tmp/plan-00144/basis.out 2>&1`, one background call: `1 passed`, never a skip; a failure is an instrument finding before the pre-flight, T0016's.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00144/preflight_check.py`, D10's (a)–(e) in order, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00144 D10's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b4_ratio_legs_basis import BLOCK, CARRY_PER_YEAR, ENGAGEMENT, TURNOVER_B, VOUCHED

out = Path(".tmp/plan-00144/b4-ratio-legs-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if compute_hash(block) != BLOCK:
    sys.exit("(a) the inputs' block differs from the spec's")
if run["vouched"] != VOUCHED:
    sys.exit("(a) the set is not vouched as the spec reads it")
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
off = [key for key, value in ENGAGEMENT.items() if m[key] != value]
off += ["turnover_b"] * (round(m["turnover_b"], 2) != TURNOVER_B)
off += ["carry_per_year"] * ({year: round(v, 6) for year, v in m["carry_per_year"].items() if v} != CARRY_PER_YEAR)
if off:
    sys.exit(f"(c) the engagement differs from the measured basis: {off}")
held = {leg: sum(years.values()) for leg, years in m["ratio_held_per_year"].items()}
print("held", held, "first weight", m["ratio_first_weight"], "primary_returns", m["primary_returns"], "turnover_b", m["turnover_b"])
if not any(held.values()):
    sys.exit("(d) no ratio leg holds a position: the dead knob")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00144/record_check.py`, the record's checks, its one argument the spec's sha256:

```python
"""Spec 00144 D9's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b4_ratio_legs_basis import CARRY_PER_YEAR, ENGAGEMENT, TURNOVER_B

name, spec_hash = "b4-ratio-legs", sys.argv[1]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00144/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00144/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"])
    == ("B4", 1, "B4-ratio-legs-a2eq-full-v1", "iter-189", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": {key: m[key] for key in ENGAGEMENT} == ENGAGEMENT
    and round(m["turnover_b"], 2) == TURNOVER_B
    and {year: round(v, 6) for year, v in m["carry_per_year"].items() if v} == CARRY_PER_YEAR,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `mkdir -p .tmp/plan-00144 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00144/preflight_check.py .tmp/plan-00144/record_check.py`. The pre-flight check was run on the authoring tree over a synthetic print carrying the real block, read from the twelve files with no compute, and the basis's engagement: it printed the block, the holding, the first weights, the primary returns and the bar's flags and exited 0, and with `passes` 0 exited 1 on `(e) arm A fails its bar`.

## Task 5 (the controller's): trial 1 — its pre-flight, its run and its record (D8–D10)

`<H>` is Task 4 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 4 step 3 whole, its stop, its merge path and Task 4 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `mkdir -p .tmp/plan-00144 && uv run zcrypto research eval --subject b4-ratio-legs-preflight --dataset ohlc-full > .tmp/plan-00144/b4-ratio-legs-preflight.out 2>&1`, a plain eval of a subject with no rule — the inputs half and one bar, about three minutes (the spec's basis: the inputs half 165.14 s, one bar 11.08 s) — one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00144/preflight_check.py`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(e): D10's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0016's with its line; a refused build — exit 1 with no traceback, its output naming `b4-ratio-legs-preflight over the full history: …` or a file of either leg — prints no metrics, keeps no reading, and is recorded in Task 6's T0016 findings with its line quoted, the trial unspent.
- [ ] **Step 3: On a stop, the reading** — `mkdir -p .tmp/plan-00144 && uv run zcrypto research eval --subject b4-ratio-legs-preflight --dataset ohlc-full --reading --iteration iter-189 --spec-hash <H> --notes "B4 trial 1's pre-flight (spec 00144 D10): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00144/b4-ratio-legs-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `mkdir -p .tmp/plan-00144 && uv run zcrypto research eval --subject b4-ratio-legs --dataset ohlc-full --register --iteration iter-189 --family B4 --n-trials 1 --variant B4-ratio-legs-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00144/b4-ratio-legs.out 2>&1`, about four and a half minutes (the spec's basis: the inputs half, seven bars and three head-to-heads, about 260 s), one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run, name only what is fixed before it: `subject b4-ratio-legs over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble on the ten EUR assets, arm B the same three arms on twelve instruments, the venue's ETH/BTC and SOL/BTC 4h pairs beside them, long-only, A2's configuration unchanged; a leg's EUR return its BTC-denominated gain converted at the bar's closing BTC/EUR; every instrument charged 0.006 per side on its own turnover; the BTC the legs sell netted against the book's own BTC/EUR position and the shortfall borrowed at 0.0002 per 4h rollover plus the opening charge on each increase; the section 10 gross cap, net band and margin floor on per-base exposures, one factor per bar; the hypothesis: the twelve-instrument book has a higher mean net-of-cost return than the ten-asset ensemble from the first close a ratio leg takes basket weight; n_trials 1, var_trials 0.0, the DSR leg binding; the head-to-head from return index 5442 (close 2016-04-02 08:00) decides, the full-window read and the borrow-unavailable twin beside it; pre-flight: block 9e0fc8e5…, arm A <the seven anchors>, passes 1, ETH/BTC held at 11397 and SOL/BTC at 5682 return indices, BTC borrowed at 8779, no limit engaged, turnover_b <its value>; park variants, pre-registered: ETH/BTC alone, the symmetric legs; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, a B4 record landed elsewhere, or bucket B spent — comes before the fit or after the print, naming each orphan, the count or the bucket's figure: no record, no reading; T0016 carries it (Task 6). A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b4-ratio-legs"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build ends its attempt failed, counting 0, recorded in T0016 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0016's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00144/record_check.py <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 6 step 2). A failed check stops the task before step 6.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-189] Verdict — B4 trial 1 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B4 n=1)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D8's table (`sed -n '/^| Arm A.s bar and the legs/,/^  Every quantity the matrix reads/p' docs/specs/00144-b4-ratio-legs-design.md`), with `arm_a_passes`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary` unrounded, the full-window pair beside them; `n_trials` 1, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); the twin's three keys; `max_drawdown` beside `arm_a_max_drawdown`; the pre-flight's block, anchors and `passes` from `.tmp/plan-00144/b4-ratio-legs-preflight.out`; the engagement — `ratio_first_weight`, `primary_returns`, `ratio_held_per_year`'s totals per leg, `stamps_positions_differ`, `turnover_a` beside `turnover_b`, the shortfall's stamps and `carry_per_year`'s total, `limit_engaged_per_year`'s totals; on a park its variants; on an adopt D11's path in its order; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-187] Verdict — B2 trial 8 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b4-ratio-legs": 1,` after `"b2-liq-z3-derisk": 7,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B4 trial 1's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries its legs adopts` (D11), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`. Then `git add` by path of `docs/reference/trial-registry.jsonl`, the record step 4's run appended, `docs/research/10.phase4-decisions.md`, `tests/test_trial_registry_provenance.py` and `tests/slow-cases.txt`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and `docs/open-topics/README.md`; `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, `data/ohlc-full` linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full .tmp/plan-00144/probe/data/ohlc-full`, unlinked after the replay and the probe and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task; then the literal's probe, expected `KILLED` (its two seds dry-run on the authoring tree, each changing one line): `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_ratio_legs_verdict(/def _b4_ratio_legs_verdict_gone(/' --mutation 's/^_B4_N_TRIALS = 1\b/_B4_N_TRIALS = 2/' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit that index, with no `git add` after the setup, as `docs(research): B4 trial 1 registered — <verdict>, the ETH/BTC and SOL/BTC legs on the A2 ensemble, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b4-ratio-legs-preflight` with outcome `null`, or `b4-ratio-legs` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones — the entry is `[iter-189] B4 trial 1 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` at its `sorted()` place, the replay rebuilding the run over the real set, as (iii) adds the record's; `git add` by path of `docs/reference/reading-ledger.jsonl`, the reading the run appended, `docs/research/10.phase4-decisions.md` and `tests/slow-cases.txt`, then the record arm's `T`, pre-commit, probe worktree and replay, with `-k 'reading-<its id>'`; committed as `docs(research): B4 trial 1 — instrument finding, kept as reading <id>; no trial spent` with no literal's probe. On a refusal from the count or a refused build: no commit here; Task 6 records it.

## Task 6: T0016, the index and the retirement of both subjects (D9, D11)

**Files:** `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`.

On an outcome Tasks 4–5 send to T0016 with no line in the registry or the ledger — a merge aborted at a develop check (Task 4 step 3, Task 5 step 1); the data test failing or skipping (Task 4 step 4); at the pre-flight a traceback, a refusal before the build or a refused build (Task 5 step 2); at the trial a refusal from the count, a refused build, or any other `failed` text, `open` or `<id> [None]` (Task 5 step 4) — step 1's Findings bullet, headed `**B4 trial 1, no record (iter-189, spec 00144).**`, and its Done so far bullet name no record, and the Findings bullet quotes whole the line that stopped it — the conflict `git merge` printed, the failure or skip line in `.tmp/plan-00144/basis.out`, the line in `.tmp/plan-00144/b4-ratio-legs-preflight.out` or `.tmp/plan-00144/b4-ratio-legs.out`, or that run's output's end as Task 5 step 4 quotes it — the trial unspent unless step 1's count lists its attempt as an orphan, which spends the slot; the budget line naming that orphan; and step 3 does not run on any of them, since until the owner's call through T0016 a trial still to run may evaluate the subjects (`tests/retired_subjects.py`'s own rule), so step 4 stages the two `docs/open-topics/` paths alone and its message ends `no record of B4 trial 1, its subjects kept`.

- [ ] **Step 1: T0016**, per `topic-ops`, every figure read off the committed record or reading and its entry:
  - `## Findings so far`: the budget bullet's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` (at this branch's base, with `B4` mapped, it printed `{'B1': 5, 'B2': 7, 'B4': 0} remain 13 []`; on trial 1's record, with no orphan, it prints `{'B1': 5, 'B2': 7, 'B4': 1} remain 12 []`): `(B1 spent 5, B2 spent 7, 13 remain)` reads `(B1 spent <its B1>, B2 spent <its B2>, B4 spent <its B4>, <its remain> remain)`, each orphan it lists named there; a bullet `**B4 trial 1 <VERDICT> (iter-189, spec 00144, registry trial <N>).**` — the row that fired, the legs' holding and the BTC shortfall in one or two sentences, pointing at its decisions-log entry for the figures, or the instrument finding, the trial unspent, or the line that stopped it as the arm above quotes it.
  - `## Done so far`: a bullet **B4 opened (iter-189, spec/plan `00144`)** on the owner's family pick of 2026-10-23, its trial 1 the loop's pick under the owner's run instruction, naming the module `cli/alpha/b4.py`, the subjects `b4-ratio-legs` and `b4-ratio-legs-preflight`, the data-gated basis test `tests/test_research_b4_ratio_legs_basis.py`, the family key `B4` in bucket B, and the record by id with its verdict.
  - `## Standing prerequisites …`: the §10 bullet's ``**Remainder: wiring** into whichever family harness binds them first (B4-legs/B3's opening iteration) — composition order caps → gross → net → margin floor per the module docstring.`` becomes ``**Wiring DELIVERED (iter-189, spec/plan `00144`)**: B4's harness, `cli/alpha/b4.py`'s `limit_factors`, passes a book's per-base exposures through gross → net → margin floor at §10's values as one factor per bar and records each limit's engaged bars; per-asset position caps, which the A2 ensemble does not carry, are not wired.``; the borrow-unavailable bullet gains ``B4 trial 1 records the rung for its BTC shortfall (the `no_borrow_*` keys of registry trial <N>).`` — on a stop with no record, both unchanged.
  - `## Suggested next steps`: `- Order per §5 ranking (B1 and B2 closed): B4-legs, the next family on the owner's pick of 2026-10-23 → B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).` becomes ``- (owner) B4's next step after trial 1 — the owner's family call, a further trial or closing the family, reading trial 1's verdict: a park's variants (ETH/BTC alone; the symmetric legs, short the pairs at an ETH or SOL borrow), a further leg or pair, the legs' own vol target or weight cap, or a close of B4 — recorded as a `[iter-NNN] B4's next step after trial 1` entry; then per §5 ranking: B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).``; on an adopt, the deploy path in its order (D11) beside it: a P1 combination trial over record 47's book carrying the legs, outside every bucket's budget, then the engine's change to trade the ratio pairs, the owner's, then T0123's promotion path.
  - `ripe_when`: its B4 arm `B4-legs and B3: the §10 portfolio-limits code lands` becomes, on no adopt, ``B4: an activity, the owner picks B4''s next step after trial 1 — a further trial or closing the family — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B4.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1; B3: the §10 portfolio-limits code lands``; on an adopt, ``B4: an activity, the P1 combination trial over record 47''s book carrying B4 trial 1''s legs is picked for an iteration, or the owner records B4''s next step after trial 1, check: `cat docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md | grep -c -E ''^\[iter-[0-9]+\] ([^.]*combination trial over record 47.s book|B4.s next step after trial 1)''` prints at least 1; B3: the §10 portfolio-limits code lands`` — the whole value moved from double to single quotes, each `'` inside it doubled (as written here), the check kept in its own backticks; the other families' arms unchanged. Measured in the scratch worktree on the no-adopt arm: the frontmatter parses to the intended text, `tests/test_open_topics_frontmatter.py tests/test_topics_index.py` pass (`1111 passed`), and the check, run as committed, prints 0.
- [ ] **Step 2: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 3: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the two subjects, so `RETIRED_SUBJECTS` gains, after `"b2-liq-z3-derisk-preflight",`, the comment `# B4's finished trials.` and `"b4-ratio-legs",` and `"b4-ratio-legs-preflight",`. Every test function Task 2 adds is parametrised by the subject's name, so the hook marks each case and no function carries the mark by hand; `test_each_subject_declares_the_metric_keys_its_build_returns` keeps its new lines, the subjects staying in `SUBJECTS`. `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q -p no:cacheprovider | grep -c -E "b4-ratio-legs|b4_"` prints 0 and the same under `-m retired` prints 48 (measured in the scratch worktree), and `mkdir -p .tmp/plan-00144 && uv run pytest tests/test_retired_subjects.py -q -p no:cacheprovider --basetemp=.tmp/plan-00144/pt` passes (measured `5 passed`).
- [ ] **Step 4: Gate and commit** — `git add` the three paths; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path, in its three parts; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0016 after B4 trial 1, the section 10 wiring delivered; its two subjects retired`.

## Task 7 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-189 — B4 trial 1: the ratio legs on A2` (59 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 5–6's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with the frozen full set linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the verdict or the stop, the pre-flight's output quoted whole in a fenced block (`.tmp/plan-00144/b4-ratio-legs-preflight.out`), every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the owner's ruling `BUCKET_OF`'s new family joins under, quoted, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00144` collected and removed, and `unlink data/ohlc-full` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full` still there.

Decisions log: the loop's pick and the conventions entry (Task 3 step 5), before the hash; the verdict or instrument-finding entry (Task 5 step 6), in its record's commit; B4's next step after trial 1 is the owner's, its entry a later branch's (T0016's trigger).
