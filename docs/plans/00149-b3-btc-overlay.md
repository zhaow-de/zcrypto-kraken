# B3 trial 3 — the rank tilt of the A2-4h ensemble's long weights hedged episodically by a BTC short while A1's confirmed-bear state holds, on frozen ohlc-full, then B3 closed: the compute, the trial subject and its twin, the data-gated basis test, the loop's pick before the hash, the gated run and the record, B3's close — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b3_overlay.py tests/test_alpha_b3_overlay.py cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b3_btc_overlay_basis.py docs/research/10.phase4-decisions.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/test_trial_registry_provenance.py tests/retired_subjects.py docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00149-b3-btc-overlay-design.md docs/plans/00149-b3-btc-overlay.md` prints `tier: full`, for `tests/test_alpha_b3_overlay.py` "a test importing cli.alpha.errors", `tests/test_research_command.py` "a test importing cli.alpha", `tests/test_research_b3_btc_overlay_basis.py` "a test importing cli.alpha.b1" once Task 3 has created it, `docs/reference/trial-registry.jsonl`, and `tests/test_trial_registry_provenance.py` "a test importing cli.registry").

**Goal:** B3's trial 3 (spec 00149) — trial 1's rank tilt of the adopted A2-4h ensemble's long weights, record 60's, with a BTC short of half the book's long gross at every close A1's confirmed-bear state holds on BTC, netted against the book's own BTC and the rest borrowed, against the untilted, unhedged ensemble, on frozen `ohlc-full`: a compute module `cli/alpha/b3_overlay.py`; two research subjects in `cli/research/subjects.py`, the trial and its evaluate-only pre-flight twin, reading trial 1's reads, ensemble and metrics; the data-gated test of their inputs half; the loop's pick and the trial's conventions in the decisions log before the hash; the trial run through spec 00133's trial-attempts log at B3's count 3, its verdict or stop in the registry and the decisions log; then B3 closed on the owner's word, the third step of its sequence — the close entry, every B3 subject retired, T0016 rewritten.

**Architecture:** one new module and no change to an existing function. `cli/alpha/b3_overlay.py`, new: `btc_short_state` (A1's `_btc_market_bear` and `trend_agreement` combined as A1's `confirmed_bear` combines them, on BTC alone), `overlay_short` (a fraction of the book's long gross where the state holds) and `with_btc_short` (the short sold out of the book's BTC, netted, or floored at 0 for the borrow-free twin). `cli/research/subjects.py` gains three insertions and changes no existing line: the module's import, the block before `SUBJECTS` — `_B3_OVERLAY_WINDOW`, `_B3_OVERLAY_BAND`, `_B3_OVERLAY_LOOKBACKS`, `_B3_OVERLAY_FRACTION`, `_B3_OVERLAY_N_TRIALS`, `_B3OverlayInputs`, `_b3_overlay_inputs`, `_b3_overlay_engagement`, `_b3_overlay_metrics`, `_b3_overlay_preflight_metrics`, `_b3_overlay_build`, the two builders, the rule `_b3_btc_overlay_verdict` and the three key sets — and two `SUBJECTS` entries. Trial 1's `_B3Inputs`, `_b3_reads`, `_b3_ensemble`, `_b3_first_engaged`, `_b3_engagement`, `_b3_metrics`, `_b3_preflight_metrics`, `_B3_METRIC_KEYS` and `_B3_PREFLIGHT_KEYS`, and trial 58's `_b4_ensemble`, `_b4_limited`, `_b4_shortfall`, `_b4_net`, `_b4_arm_a_bar` and `_B4_CARRY_RATE` are read as they are. The family key `B3` is in `BUCKET_OF` already. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00149-b3-btc-overlay-design.md` — binding; D1–D11 are cited by name and the values below are copied from it. It reads spec 00147's tilt, arm A, costing, limits, bar and matrix, frozen by record 60's `spec_hash`, and spec 00144's borrow, carry and limits on a book that borrows, frozen by record 58's. **Iteration:** iter-194. **Topic:** T0016, its B3 arm. **Branch:** `research/iter-194-b3-btc-overlay`, worktree `.claude/worktrees/iter194`, `data/ohlc-full` linked read-only from the main checkout, and no other set. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: Tasks 1–3's code and tests were written in this worktree, then carried into a detached scratch worktree at the base, `63c197fff`, with a placeholder spec file committed beside them; there Task 1's tests measured green (`17 passed`) and, with the module aside, red at collection (`1 error`); Task 2's cases measured red with the base's `cli/research/subjects.py` and the module aside (`24 failed, 961 deselected`, each at its call) and green on the code (`24 passed, 979 deselected`), the shared rows the two subjects add green (`19 passed, 984 deselected in 116.63s`); the four gate parts of Task 2's list green on the authoring tree, Task 3's basis test among its files; the 97 probe rows of Tasks 1 and 2 run on that tree, 97 of 97 `KILLED`; with `ohlc-full` linked, Task 3's data-gated case `1 passed` with a call of 145.45 s on the authoring tree, and Task 4 step 4's data test and fixture rows (`3 passed in 180.25s`) and records 60's and 58's replays (`1 passed` each, calls of 261.82 s and 302.38 s); Task 3 step 5's two entries appended and run through the decisions-log tests; Task 4 step 5's pre-flight check run over synthetic pre-flight prints carrying the real block; and Task 6's close — the entry, the retirement, T0016's edits on the verdict arm with sample figures and the stop and adopt arms' `ripe_when` — tried and run through the topic, index, retirement and log tests, then reverted. The fences applied to the base as the steps say reproduce every authoring file (checked by a program over the base's files); the files were restored to the base before this plan was committed. Not run: any `zcrypto research eval` of the two subjects (Task 5), the record's check program beyond a parse, the record's replay and the literal's probe (Task 5), the close as committed (Task 6) and the PR (Task 7).

## Global Constraints

- **The books and the costing** (D2–D6): the union `_capturing_union(reader, dataset, 240, window, None, accept_holes)` of the ten EUR assets through trial 1's `_b3_reads`, no other pair, refused before any book below `_DECISIVE_START` + 2 return indices or with no return index closing outside the stub years, and `--as-of` refused before any read; arm A `_b4_limited(_b4_ensemble(fed))`; arm B `_b4_limited(with_btc_short(raw_b, short, borrow=True))`, `raw_b` trial 1's `_b3_ensemble(fed)` — each arm's `b3_book_returns(fed, config=<its A2Config>, score_lookback=180, strength=0.5, floor=8)`, their mean — `short = overlay_short(raw_b, state, fraction=0.5)`, `state = btc_short_state(fed["BTC"], window=1200, band=0.0, lookbacks=(120, 360, 720))`; the twin `_b4_limited(with_btc_short(raw_b, short, borrow=False))`; `fed = _ffill_btc(h4_prices)`; every book costed by `_b4_net(positions, returns, stress=…)`, `returns = {a: _asset_returns(fed[a])}`, the carry on the netted BTC's short part at `stress × 0.0002`; §10's limits through `_b4_limited`, one factor per bar, the per-asset caps unwired.
- **The bars** (D8): trial 1's `_b3_metrics` at `n_trials=3` — every `a1_kill_bar` call `n_trials=3, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`, the headline (30, 42); arm A's bar `_b4_arm_a_bar` at (30, 42); the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` at `first` 0 and at arm B's first engagement, `tilt_first_engaged`, the first return index at which arm B's positions differ from arm A's (1,230), and the twin's from the same start; refused before any bar: fewer than 2 return indices from the first engagement.
- **The count** (D8): `_B3_OVERLAY_N_TRIALS = 3`, `required_n("B3")` as the spec measured it, fixed by the spec's hash; at `var_trials` 0.0 the DSR leg is the PSR against 0.
- **The rule** (D8): `_b3_btc_overlay_verdict` — `None` when `arm_a_passes` is 0 or `overlay_per_year` counts no close, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0` with `head_to_head_spa_p_primary < 0.05`, `park` on the first with the p at or above 0.05, `reject` otherwise; the park row names no variant, B3 closing after the verdict.
- **The record** (D9): family `B3`; `n_trials_in_family` 3; variant `B3-btc-overlay-a2eq-full-v1`; iteration `iter-194`; seeds (42, 7, 1234); 54 metric keys; the block `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`; no `--verdict`.
- **The pre-flight read** (D10), in this order: (a) the block and `ohlc-full`'s vouched status (Task 3's `BLOCK` and `VOUCHED`); (b) arm A's seven anchors record 61's stored figures to the last digit — `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full` against its `arm_a_max_drawdown`, `turnover_a`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`, and `arm_a_spot_drag_pct_yr` against `turnover_a / 27,337 × 0.006 × 2,190`; (c) the dead knob — a non-zero count in `overlay_per_year`, read before the engagement; (d) the engagement the measured basis's — Task 3's `ENGAGEMENT`, and its `TILT` keys record 60's; (e) arm A's `passes` 1.
- **The hash rule** (D10): before Task 4 step 2 takes the spec's sha256, nobody reads or computes trial 3's arm B or its twin's returns or net-of-cost series, a head-to-head or a bar leg of either — by code, a program or arithmetic over a stored figure — nor runs `b3-btc-overlay` or `b3-btc-overlay-preflight` over the real set; weights, ranks, positions, the short state, the short, exposures, the BTC borrowed, the carry it implies, limit engagement and turnover are allowed — what the data-gated test (Task 3) computes, and no return of a book. `a2_book_returns` and `b3_book_returns` compute each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; nothing reads them. Records 60's and 58's replays rebuild trials 1's and 58's stored figures and read no book carrying the short. No reader, reviewer or plan-review dispatch runs either new subject over the real set before the hash, and every read's dispatch carries this rule. No return of trial 3's arm B is computed over the real data before the trial's `--register` run, and the trial subject is never run as a plain eval; after it, only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with the set linked.
- **Unchanged** (D3, D9): every existing function and subject of `cli/research/subjects.py` — trial 1's and trial 58's machinery among them — `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b3.py`, `cli/alpha/b4.py`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/risk/*`, `cli/costs/*`, `cli/validation/*` and `cli/engine/*`; records 58, 60 and 61; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-status $(git merge-base HEAD origin/develop) -- cli/` prints `A	cli/alpha/b3_overlay.py` from Task 1 on and `M	cli/research/subjects.py` beside it from Task 2 on, nothing else; from Task 2 on, `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@')" = 3` and `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@ -[0-9]*,0 ')" = 3` each exit 0 — three hunks, each a pure insertion, so a line changed or added anywhere but at Task 2 step 3's three sites is a fourth hunk or an impure one. Measured on the authoring tree: `@@ -82,0 +83 @@`, `@@ -4574,0 +4576,140 @@` and `@@ -5038,0 +5180,25 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00149-b3-btc-overlay-design.md` after Task 4 step 2, nor specs 00128, 00133, 00137, 00144, 00147 and 00148, nor the spec before then except a fix commit a read of Task 3 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 5 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, a read-only link, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The trial, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 4 step 3, Task 5 step 1) and Task 7's `gh` calls, push and `merge-pr` are the exceptions. A data link is removed with `test -L <its absolute path> && unlink <its absolute path>`, never `rm`.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 6's reads, Tasks 4–5 and Task 7, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the pre-flight, the register, the replays), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 6 and Task 3's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00149 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00149/` follows `mkdir -p .tmp/plan-00149 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00149/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `mkdir -p .tmp/plan-00149 && bash infra/scripts/consumers.sh --direct <each changed path> 2> .tmp/plan-00149/T.err | sort -u > .tmp/plan-00149/T.txt`, `.tmp/plan-00149/T.err` read before the list is used — never `2>/dev/null`, whose stderr is where a refusal speaks — and `test -s .tmp/plan-00149/T.txt && uv run pytest $(cat .tmp/plan-00149/T.txt) -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt`, so that an empty list fails closed and never becomes a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every file a commit carries is staged by explicit path — the registry's line by `--register`, the ledger's by `--reading` or by a stop under `--register`, among them, whose one commit is Task 5 step 6's — since the commit and the probe setup's `git write-tree` read the index while the list reads the working tree. Every list holding `tests/test_research_command.py` runs it in four parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms, so that none can pass 600 s: `tests/test_research_command.py -k "not reentry and not b2"` (`--basetemp=.tmp/plan-00149/pt-1`, measured on the authoring tree in the scratch worktree, `580 passed, 423 deselected in 241.30s`), `tests/test_research_command.py -k "b2 and not reentry"` (`pt-2`, measured `227 passed, 776 deselected in 312.01s`), `tests/test_research_command.py -k reentry` (`pt-3`, measured `71 passed, 932 deselected in 88.68s`) and the rest of the list, read off `.tmp/plan-00149/T.txt` with that file's line left out (`pt-4`). Every commit message carries the result line of each test command its gate ran, a run over that commit's own tree, and the two trailer lines exactly as the executing session's attribution gives them — `Co-Authored-By:` naming the model that ran the step, and `Claude-Session:`.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00149 &&
  test ! -e .tmp/plan-00149/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00149/probe HEAD &&
  git -C .tmp/plan-00149/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00149/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00149/probe/.tmp
```

  Then, from `.tmp/plan-00149/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. A mutation whose text also stands in an existing function — trial 1's and trial 58's functions share many lines with the new ones — carries the address of its own function's range, `/^def <name>(/,/^def /`, of the rule's, `/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/`, or of its entry's, `/"<subject>": Subject(/,/^    ),/`, so its dry run changes one line; no pattern holds a `'`. After the last verdict, `git worktree remove --force .tmp/plan-00149/probe` — each data link in it unlinked first with `test -L <its absolute path> && unlink <its absolute path>`, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, `ohlc-full` still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subjects' names** (D9): `b3-btc-overlay` and `b3-btc-overlay-preflight`, which no registered or retired subject's name equals or opens with a hyphen, and which open none (the spec's basis). Every new test function in `tests/test_research_command.py` carries `b3_overlay` in its name, which no hyphenated id and no other test's name there carries, so `-k b3_overlay` selects them alone in that file; the rows trial 1's `--as-of` function gains and the shared rows the two subjects add carry the hyphenated `b3-btc-overlay` in their ids.

## Task 1: the compute module `cli/alpha/b3_overlay.py` (D3)

**Files:** Create `cli/alpha/b3_overlay.py`, `tests/test_alpha_b3_overlay.py`.

**Interfaces:** Consumes `cli/alpha/a1.py`'s `_btc_market_bear` and `_check_window`, `cli/alpha/b4.py`'s `_check_lengths`, `cli.features.trend_agreement` and `AlphaError`; in the tests, `cli/alpha/b4.py`'s `quote_shortfall` and `shortfall_carry`. Produces `btc_short_state`, `overlay_short` and `with_btc_short`, which Task 2's block imports.

- [ ] **Step 1: Write the failing tests** — `tests/test_alpha_b3_overlay.py`, whole:

```python
import copy

import pytest

from cli.alpha.b3_overlay import btc_short_state, overlay_short, with_btc_short
from cli.alpha.b4 import quote_shortfall, shortfall_carry
from cli.alpha.errors import AlphaError

# On a 4-close SMA with trend agreement over 2 and 3 closes: the close at 3 above its SMA with its trend down, at 5 on its
# SMA, at 6 and 7 below it with the trend down — 7 within a band of 0.1 of it — and at 8 below it with the trend split.
_BTC = [20.0, 19.0, 5.0, 15.0, 16.0, 12.0, 8.0, 11.0, 9.0, 11.0, 12.0, 13.0]
_STATE = [False] * 6 + [True] * 2 + [False] * 3
_BOOK = {
    "BTC": [0.125, 0.25, 0.0, 0.375],
    "ETH": [0.25, 0.0, 0.0, 0.125],
    "SOL": [0.125, 0.25, 0.0, 0.0],
    "XRP": [-0.0625, 0.0, 0.0, 0.0],
}


@pytest.mark.parametrize(
    ("band", "state"),
    [
        pytest.param(0.0, _STATE, id="band-0"),
        pytest.param(0.1, [False] * 6 + [True] + [False] * 4, id="band-0.1-drops-the-close-within-it"),
    ],
)
def test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative(band, state):
    assert btc_short_state(_BTC, window=4, band=band, lookbacks=(2, 3)) == state


def test_the_state_at_a_close_reads_no_later_close():
    full = btc_short_state(_BTC, window=4, band=0.0, lookbacks=(2, 3))
    for cut in range(1, len(_BTC)):
        planted = _BTC[:cut] + [100.0] * (len(_BTC) - cut)
        assert btc_short_state(planted, window=4, band=0.0, lookbacks=(2, 3))[:cut] == full[:cut]


@pytest.mark.parametrize(
    ("window", "band", "match"),
    [
        pytest.param(1, 0.0, "window must be an int >= 2", id="window-1"),
        pytest.param(4, -0.01, "band must be a number in", id="band-below-0"),
        pytest.param(4, 1.0, "band must be a number in", id="band-1"),
        pytest.param(4, False, "band must be a number in", id="band-a-bool"),
        pytest.param(4, "0.1", "band must be a number in", id="band-a-string"),
    ],
)
def test_btc_short_state_refuses_a_window_or_band_a1_would_refuse(window, band, match):
    with pytest.raises(AlphaError, match=match):
        btc_short_state(_BTC, window=window, band=band, lookbacks=(2, 3))


def test_the_short_is_the_fraction_of_the_books_long_gross_where_the_state_holds_and_0_elsewhere():
    # Long gross 0.5, 0.5, 0.0 and 0.5, XRP's short not counted; the state holds at 0, 2 and 3, the book flat at 2.
    assert overlay_short(_BOOK, [True, False, True, True], fraction=0.5) == [0.25, 0.0, 0.0, 0.25]
    assert overlay_short(_BOOK, [True, False, True, True], fraction=0.25) == [0.125, 0.0, 0.0, 0.125]


@pytest.mark.parametrize(
    ("fraction", "state", "match"),
    [
        pytest.param(0, [True] * 4, "fraction must be a number in", id="fraction-0"),
        pytest.param(0.51, [True] * 4, "fraction must be a number in", id="fraction-above-half"),
        pytest.param("0.5", [True] * 4, "fraction must be a number in", id="fraction-a-string"),
        pytest.param(0.5, [True] * 3, "3 states for positions of 4 return indices", id="a-state-short"),
    ],
)
def test_overlay_short_refuses_a_fraction_above_half_or_a_state_of_another_length(fraction, state, match):
    with pytest.raises(AlphaError, match=match):
        overlay_short(_BOOK, state, fraction=fraction)


def test_the_short_is_netted_against_the_books_btc_and_no_alt_is_shorted():
    unchanged = copy.deepcopy(_BOOK)

    borrowed = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=True)
    held = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=False)

    assert borrowed == _BOOK | {"BTC": [-0.125, 0.25, 0.0, 0.125]}
    assert held == _BOOK | {"BTC": [0.0, 0.25, 0.0, 0.125]}
    assert _BOOK == unchanged and all(borrowed[a] is not _BOOK[a] and held[a] is not _BOOK[a] for a in _BOOK)


def test_only_the_btc_the_book_does_not_hold_is_borrowed_and_carried():
    borrowed = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=True)
    held = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=False)

    # At 0 the short outweighs the book's 0.125 of BTC by 0.125; at 3 the book's 0.375 covers it.
    assert quote_shortfall(borrowed, "BTC") == [0.125, 0.0, 0.0, 0.0]
    assert shortfall_carry(quote_shortfall(borrowed, "BTC"), rate=0.0002) == [0.0002 * 0.25, 0.0, 0.0, 0.0]
    assert quote_shortfall(held, "BTC") == [0.0] * 4


@pytest.mark.parametrize(
    ("book", "short", "match"),
    [
        pytest.param({a: v for a, v in _BOOK.items() if a != "BTC"}, [0.0] * 4, "the book holds no BTC", id="no-btc"),
        pytest.param(_BOOK, [0.0] * 3, "3 shorts for positions of another length", id="a-short-short"),
    ],
)
def test_with_btc_short_refuses_a_book_without_btc_or_a_short_of_another_length(book, short, match):
    with pytest.raises(AlphaError, match=match):
        with_btc_short(book, short, borrow=True)
```

  **Author's call** — known answers, each a clause of D3: the state on a 12-close BTC series at a 4-close SMA and trend agreement over 2 and 3 closes, written out by hand in the fixture's comment — the close at 3 above its SMA with its trend down (the SMA's leg deciding), at 5 on its SMA, at 6 and 7 below it with the trend down, at 8 below it with the trend split (the trend's leg deciding), and a band of 0.1 dropping 7, inside it; no close's state moved by any later close, every prefix planted with a far later price; the refusals A1Config's own bounds give the window and the band, a bool and a string band among them; the short at the fraction of the long gross where the state holds — 0.25 of a long gross of 0.5 at 0.5, a negative position not counted, a flat book shorting nothing — and 0 elsewhere, at two fractions so a constant is seen; the fraction refused outside (0, 0.5] and as a string, and a state of another length; the short netted against the book's BTC, the alts the same values in new lists, the borrow-free form floored at 0; the carry on the BTC the book does not hold alone — at the close the book's 0.375 covers the short, no carry; a book with no BTC and a short of another length refused.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00149 && uv run pytest tests/test_alpha_b3_overlay.py -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt`: collection stops at the import of `cli.alpha.b3_overlay` (measured in the scratch worktree with the module aside: `1 error`).
- [ ] **Step 3: Implement `cli/alpha/b3_overlay.py`**, whole:

```python
"""B3 trial 3's compute (docs/specs/00149-b3-btc-overlay-design.md D3): A1's confirmed-bear short state on BTC and the BTC
short a long book carries while it holds, alts never shorted.

A position is a fraction of NAV in EUR notional held over return index k, from close k to close k + 1."""

from __future__ import annotations

import math
from collections.abc import Mapping

from cli.alpha.a1 import _btc_market_bear, _check_window
from cli.alpha.b4 import _check_lengths
from cli.alpha.errors import AlphaError
from cli.features import trend_agreement


def btc_short_state(btc: list[float], *, window: int, band: float, lookbacks: tuple[int, ...]) -> list[bool]:
    """Per return index k, A1's confirmed bear read on BTC alone at close k: below its `window`-close SMA by `band`, and
    its trend agreement over `lookbacks` below 0."""
    _check_window("window", window)
    if not isinstance(band, (int, float)) or isinstance(band, bool) or not 0.0 <= band < 1.0:
        raise AlphaError(f"band must be a number in [0.0, 1.0), got {band!r}")
    agreement = trend_agreement(btc, lookbacks=list(lookbacks))
    bear = _btc_market_bear(btc, window=window, band=band)
    return [b == 1.0 and a < 0 for b, a in zip(bear, agreement, strict=True)]


def overlay_short(positions: Mapping[str, list[float]], state: list[bool], *, fraction: float) -> list[float]:
    """Per return index, `fraction` of the book's long gross where the state holds, else 0.0."""
    if not isinstance(fraction, (int, float)) or not 0 < fraction <= 0.5:
        raise AlphaError(f"fraction must be a number in (0, 0.5], got {fraction!r}")
    n = _check_lengths(positions)
    if len(state) != n:
        raise AlphaError(f"{len(state)} states for positions of {n} return indices")
    return [fraction * math.fsum(max(0.0, p[k]) for p in positions.values()) if state[k] else 0.0 for k in range(n)]


def with_btc_short(positions: Mapping[str, list[float]], short: list[float], *, borrow: bool) -> dict[str, list[float]]:
    """The book with `short` sold out of its BTC, netted against the BTC the book holds; with `borrow` False the BTC is
    floored at 0, so the book sells only the BTC it holds. Every other instrument as it is."""
    if "BTC" not in positions:
        raise AlphaError("the book holds no BTC to carry the short")
    if len(short) != _check_lengths(positions):
        raise AlphaError(f"{len(short)} shorts for positions of another length")
    btc = [p - s for p, s in zip(positions["BTC"], short, strict=True)]
    if not borrow:
        btc = [max(0.0, p) for p in btc]
    return {i: btc if i == "BTC" else list(v) for i, v in positions.items()}
```

- [ ] **Step 4: Run them to verify they pass** — step 2's command, measured `17 passed`.
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b3_overlay.py tests/test_alpha_b3_overlay.py`; the Global Constraints' list over the two paths, whatever it names — `tests/test_alpha_b3_overlay.py` on this task's tree (measured `17 passed`), and `tests/test_research_command.py`'s four parts if the list names it; `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured in the scratch worktree on the authoring tree, 26 of 26):

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/b == 1.0 and a < 0 for b, a/a < 0 for b, a/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative[band-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/b == 1.0 and a < 0 for b, a/b == 1.0 for b, a/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative[band-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/b == 1.0 and a < 0 for b, a/b == 1.0 and a <= 0 for b, a/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative[band-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/_btc_market_bear(btc, window=window, band=band)/_btc_market_bear(btc, window=window, band=0.0)/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative[band-0.1-drops-the-close-within-it]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/_btc_market_bear(btc, window=window, band=band)/_btc_market_bear(btc, window=window + 1, band=band)/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative[band-0.1-drops-the-close-within-it]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/trend_agreement(btc, lookbacks=list(lookbacks))/trend_agreement(btc, lookbacks=list(lookbacks)[-1:])/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative[band-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/    bear = _btc_market_bear(btc, window=window, band=band)/    bear = [*_btc_market_bear(btc, window=window, band=band)[1:], 0.0]/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_state_at_a_close_reads_no_later_close' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/    _check_window("window", window)/    _check_window("window", max(window, 2))/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_btc_short_state_refuses_a_window_or_band_a1_would_refuse[window-1]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/not 0.0 <= band < 1.0/not -1.0 <= band < 1.0/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_btc_short_state_refuses_a_window_or_band_a1_would_refuse[band-below-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/not 0.0 <= band < 1.0/not 0.0 <= band <= 1.0/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_btc_short_state_refuses_a_window_or_band_a1_would_refuse[band-1]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/ or isinstance(band, bool) or / or /' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_btc_short_state_refuses_a_window_or_band_a1_would_refuse[band-a-bool]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def btc_short_state(/def btc_short_state_gone(/' --mutation 's/if not isinstance(band, (int, float)) or isinstance(band, bool) or /if isinstance(band, bool) or /' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_btc_short_state_refuses_a_window_or_band_a1_would_refuse[band-a-string]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def overlay_short(/def overlay_short_gone(/' --mutation 's/fraction \* math.fsum(max(0.0, p\[k\])/0.5 * math.fsum(max(0.0, p[k])/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_short_is_the_fraction_of_the_books_long_gross_where_the_state_holds_and_0_elsewhere' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def overlay_short(/def overlay_short_gone(/' --mutation 's/math.fsum(max(0.0, p\[k\]) for p/math.fsum(p[k] for p/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_short_is_the_fraction_of_the_books_long_gross_where_the_state_holds_and_0_elsewhere' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def overlay_short(/def overlay_short_gone(/' --mutation 's/ if state\[k\] else 0.0 for k/ if not state[k] else 0.0 for k/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_short_is_the_fraction_of_the_books_long_gross_where_the_state_holds_and_0_elsewhere' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def overlay_short(/def overlay_short_gone(/' --mutation 's/not 0 < fraction <= 0.5/not 0 <= fraction <= 0.5/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_overlay_short_refuses_a_fraction_above_half_or_a_state_of_another_length[fraction-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def overlay_short(/def overlay_short_gone(/' --mutation 's/not 0 < fraction <= 0.5/not 0 < fraction <= 1.0/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_overlay_short_refuses_a_fraction_above_half_or_a_state_of_another_length[fraction-above-half]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def overlay_short(/def overlay_short_gone(/' --mutation 's/if not isinstance(fraction, (int, float)) or not 0/if not 0/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_overlay_short_refuses_a_fraction_above_half_or_a_state_of_another_length[fraction-a-string]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def overlay_short(/def overlay_short_gone(/' --mutation 's/    if len(state) != n:/    if False:/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_overlay_short_refuses_a_fraction_above_half_or_a_state_of_another_length[a-state-short]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def with_btc_short(/def with_btc_short_gone(/' --mutation 's/btc = \[p - s for p, s in/btc = [p + s for p, s in/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_short_is_netted_against_the_books_btc_and_no_alt_is_shorted' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def with_btc_short(/def with_btc_short_gone(/' --mutation 's/        btc = \[max(0.0, p) for p in btc\]/        btc = list(btc)/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_short_is_netted_against_the_books_btc_and_no_alt_is_shorted' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def with_btc_short(/def with_btc_short_gone(/' --mutation 's/    if not borrow:/    if borrow:/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_short_is_netted_against_the_books_btc_and_no_alt_is_shorted' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def with_btc_short(/def with_btc_short_gone(/' --mutation 's/btc if i == "BTC" else list(v) for i, v/btc if i == "BTC" else v for i, v/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_the_short_is_netted_against_the_books_btc_and_no_alt_is_shorted' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def with_btc_short(/def with_btc_short_gone(/' --mutation 's/btc = \[p - s for p, s in zip(positions\["BTC"\], short, strict=True)\]/btc = [-s for p, s in zip(positions["BTC"], short, strict=True)]/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_only_the_btc_the_book_does_not_hold_is_borrowed_and_carried' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def with_btc_short(/def with_btc_short_gone(/' --mutation 's/    if "BTC" not in positions:/    if False:/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_with_btc_short_refuses_a_book_without_btc_or_a_short_of_another_length[no-btc]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b3_overlay.py --control 's/^def with_btc_short(/def with_btc_short_gone(/' --mutation 's/    if len(short) != _check_lengths(positions):/    if False:/' -- uv run pytest 'tests/test_alpha_b3_overlay.py::test_with_btc_short_refuses_a_book_without_btc_or_a_short_of_another_length[a-short-short]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D3 gives the module. The state: the SMA's leg, the trend's leg and a split trend read as down (rows 1–3), the band (row 4), the window — seen on the band-0.1 case, where a 5-close SMA keeps the close at 7 below its band (row 5; aimed first at the band-0 case, whose state a 5-close SMA leaves unchanged, it SURVIVED there, and was moved to this case) — a horizon dropped (row 6), a one-close look-ahead (row 7) and the window's and band's refusals (rows 8–12). The short: its fraction, a negative position counted and the state inverted (rows 13–15), and its refusals (rows 16–19). The netting: the short added, the twin not floored, the borrow flag inverted and the alts aliased (rows 20–23), the short not netted against the book's BTC (row 24) and the two refusals (rows 25–26). **Author's call — the clauses no row moves**: `overlay_short`'s and `with_btc_short`'s `_check_lengths` is B4's function, guarded by B4's cases; `btc_short_state`'s validation of the prices and the horizons is `trend_agreement`'s, guarded by the features' cases.
- [ ] **Step 7: Commit** — `feat(alpha): B3 trial 3's compute — A1's confirmed-bear state read on BTC, a BTC short at a fraction of a book's long gross while it holds, and the short netted against the book's own BTC`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the trial subject and its pre-flight twin in `cli/research/subjects.py` (D2–D9)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 1's three functions; `cli/research/subjects.py`'s `_B3Inputs`, `_b3_reads`, `_b3_ensemble`, `_b3_first_engaged`, `_b3_metrics`, `_b3_preflight_metrics`, `_B3_METRIC_KEYS`, `_B3_PREFLIGHT_KEYS`, `_b4_ensemble`, `_b4_limited`, `_b4_shortfall`, `_b4_net`, `_B4_CARRY_RATE`, `_ffill_btc`, `_asset_returns`, `close_grid`, `per_year_counts`, `per_year_means`, `per_year_sums`, `shortfall_carry`, `net_of_cost_verdict`, `sharpe`, `PPY_4H`, `_N_RESAMPLES`, `_b2_over`, `_ASSETS`, `Subject`, `SubjectError`, `ObservedReader` and the error classes it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, trial 1's `_B3_ARMS`, `_B3_METRIC_KEYS`, `_B3_PREFLIGHT_KEYS`, `_b3_short_reads`, `_b3_built_inputs` and `_b3_own_net`, and `_b2_dataset`, `_B2_START`, `_B2_ASSETS`, `_recording`, `_anchor`, `_fake_kill_bar`, `_fake_head_to_head`, `_fake_benchmark`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`, `runner` and `app`. Produces the two subjects, `_b3_overlay_inputs`, `_b3_overlay_engagement` and `_B3_OVERLAY_N_TRIALS`, which Task 3's test and Task 5's literal read.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - the import `from cli.alpha.a1 import _asset_returns, _inverse_vol_weights` becomes `from cli.alpha.a1 import _asset_returns, _btc_market_bear, _inverse_vol_weights`, and `from cli.features import trend_agreement` joins the imports directly above `from cli.features.derivatives import coverage_by_year, funding_zscore`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, after its `assert subjects.SUBJECTS["b3-tilt-slow-preflight"].metric_keys == _B3_PREFLIGHT_KEYS` line:

```python
    assert subjects.SUBJECTS["b3-btc-overlay"].metric_keys == _B3_METRIC_KEYS | _B3_OVERLAY_ENGAGEMENT_KEYS | _B3_OVERLAY_TWIN_KEYS
    assert subjects.SUBJECTS["b3-btc-overlay-preflight"].metric_keys == _B3_PREFLIGHT_KEYS | _B3_OVERLAY_ENGAGEMENT_KEYS
```

  - the `name` parametrization of `test_a_b3_subject_refuses_as_of_before_any_read`, `@pytest.mark.parametrize("name", ["b3-rank-tilt", "b3-rank-tilt-preflight", "b3-tilt-slow", "b3-tilt-slow-preflight"])`, becomes:

```python
@pytest.mark.parametrize(
    "name",
    [
        "b3-rank-tilt",
        "b3-rank-tilt-preflight",
        "b3-tilt-slow",
        "b3-tilt-slow-preflight",
        "b3-btc-overlay",
        "b3-btc-overlay-preflight",
    ],
)
```

  - after `test_the_b3_slow_trial_refuses_a_plain_eval_and_another_count_before_any_read` and before `def _ruled_signal(`, two blank lines either side:

```python
_B3_OVERLAY_SPEC = "docs/specs/00149-b3-btc-overlay-design.md"
_B3_OVERLAY_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the overlay shorts no BTC at any stamp; no verdict, the "
    "trial unspent"
)
# Spec 00149 D8's keys added to trial 1's, typed from the spec, never read off a subject.
_B3_OVERLAY_ENGAGEMENT_KEYS = frozenset(
    {
        "short_state_per_year",
        "overlay_per_year",
        "overlay_first_engaged",
        "shortfall_stamps_per_year",
        "shortfall_mean_per_year",
        "shortfall_max",
        "carry_per_year",
    }
)
_B3_OVERLAY_TWIN_KEYS = frozenset(
    {"no_borrow_ann_sharpe_noc", "no_borrow_head_to_head_mean_outperf_primary", "no_borrow_head_to_head_spa_p_primary"}
)


@pytest.mark.parametrize("name", ["b3-btc-overlay"])
def test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state(name):
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    assert (len(trial.metric_keys), len(preflight.metric_keys)) == (54, 35)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B3_OVERLAY_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b3_btc_overlay
    assert trial.metric_keys == _B3_METRIC_KEYS | _B3_OVERLAY_ENGAGEMENT_KEYS | _B3_OVERLAY_TWIN_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b3_btc_overlay_verdict, _B3_OVERLAY_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B3", 3) == ("B3", subjects._B3_OVERLAY_N_TRIALS)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        f"{name}-preflight",
        (240,),
        _B2_ASSETS,
        _B3_OVERLAY_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b3_btc_overlay_preflight
    assert preflight.metric_keys == _B3_PREFLIGHT_KEYS | _B3_OVERLAY_ENGAGEMENT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5
    assert (
        subjects._B3_OVERLAY_WINDOW,
        subjects._B3_OVERLAY_BAND,
        subjects._B3_OVERLAY_LOOKBACKS,
        subjects._B3_OVERLAY_FRACTION,
    ) == (1200, 0.0, (120, 360, 720), 0.5)


# Adopting on every key the rule reads, the full window's head-to-head against it, so a rule reading the full window moves
# the adopt row.
_B3_OVERLAY_ADOPTING = {
    "arm_a_passes": 1,
    "overlay_per_year": {"2016": 0, "2017": 3},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
}


@pytest.mark.parametrize("name", ["b3-btc-overlay"])
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="outperforms-significantly-from-the-first-engagement"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param({"overlay_per_year": {"2016": 0, "2017": 0}}, None, id="the-overlay-never-shorts"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({"overlay_per_year": {"2016": 0, "2017": 0}, "passes": 0}, None, id="the-overlay-read-before-passes"),
        pytest.param({"passes": 0}, "reject", id="arm-b-fails-its-bar"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="p-0.2"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001}, "reject", id="mean-negative"
        ),
    ],
)
def test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop(name, change, verdict):
    assert subjects.SUBJECTS[name].verdict({**_B3_OVERLAY_ADOPTING, **change}) == verdict


@pytest.mark.parametrize(
    ("name", "compute"),
    [("b3-btc-overlay", "_b3_overlay_metrics"), ("b3-btc-overlay-preflight", "_b3_overlay_preflight_metrics")],
)
def test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count(
    monkeypatch, name, compute
):
    reader, window, reads, inputs = object(), ("2021-01-01", "2025-12-31"), object(), object()
    calls = []

    def read(*args, **kwargs):
        calls.append(("_b3_reads", args, kwargs))
        return reads

    def build(*args, **kwargs):
        calls.append(("_b3_overlay_inputs", args, kwargs))
        return inputs

    def computed(*args, **kwargs):
        calls.append((compute, args, kwargs))
        return {"built": name}

    monkeypatch.setattr(subjects, "_b3_reads", read)
    monkeypatch.setattr(subjects, "_b3_overlay_inputs", build)
    monkeypatch.setattr(subjects, compute, computed)

    built = subjects.SUBJECTS[name].build(reader, "ohlc-test", window, None, True)

    assert built == {"built": name}
    assert calls == [
        ("_b3_reads", (name, reader, "ohlc-test", window, True), {}),
        ("_b3_overlay_inputs", (reads,), {}),
        (compute, (inputs,), {"n_trials": 3}),
    ]


def _b3_overlay_short_state(monkeypatch) -> tuple[int, tuple[int, ...]]:
    """A1's state on a 40-close SMA and trend agreement over 5, 10 and 20 closes, so that on `_b3_short_reads` it holds
    from return index 59, arm B's book holds nothing long until 181, the overlay first shorts at 191 and the tilt first
    moves a position at 300."""
    monkeypatch.setattr(subjects, "_B3_OVERLAY_WINDOW", 40)
    monkeypatch.setattr(subjects, "_B3_OVERLAY_LOOKBACKS", (5, 10, 20))
    return 40, (5, 10, 20)


def _b3_overlay_own_books(h4_ts: list[datetime], h4_prices: dict, *, window: int, lookbacks: tuple[int, ...]) -> dict:
    """The books of the reads with the BTC short, built here through `a2_book_returns`, `b3_book_returns`, A1's two state
    functions and the limits, never through the subject's halves or `cli/alpha/b3_overlay.py`."""
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
    raw_b = mean([book["asset_positions"] for book in tilted])
    bear = _btc_market_bear(fed["BTC"], window=window, band=0.0)
    agreement = trend_agreement(fed["BTC"], lookbacks=list(lookbacks))
    state = [b == 1.0 and t < 0 for b, t in zip(bear, agreement)]
    short = [0.5 * math.fsum(max(0.0, raw_b[i][k]) for i in raw_b) if state[k] else 0.0 for k in range(n)]
    netted = [p - s for p, s in zip(raw_b["BTC"], short)]
    return {
        "limited_a": limited(mean([a2_book_returns(fed, config=c)["asset_positions"] for c in configs])),
        "limited_b": limited(raw_b | {"BTC": netted}),
        "no_borrow": limited(raw_b | {"BTC": [max(0.0, p) for p in netted]})[0],
        "state": state,
        "short": short,
        "ranked": dict(zip(_B3_ARMS, (book["ranked"] for book in tilted), strict=True)),
        "tilted": dict(zip(_B3_ARMS, (book["tilted"] for book in tilted), strict=True)),
        "returns": {a: _asset_returns(fed[a]) for a in h4_prices},
    }


@pytest.mark.parametrize("name", ["b3-btc-overlay"])
def test_the_b3_overlay_arms_agree_bit_for_bit_until_the_overlay_first_shorts_and_no_alt_is_shorted(monkeypatch, name):
    _b3_overlay_short_state(monkeypatch)
    reads = _b3_short_reads()
    n = len(reads[0]) - 1

    inputs = subjects._b3_overlay_inputs(reads)

    trial = inputs.trial
    first = next(k for k, s in enumerate(inputs.short) if s > 0)
    first_tilted = min(next(k for k, c in enumerate(counts) if c) for counts in trial.tilted.values())
    differ = [k for k in range(n) if any(trial.arm_b[a][k] != trial.arm_a[a][k] for a in trial.arm_a)]
    assert any(inputs.state[:first]) and differ[0] == first == subjects._b3_first_engaged(trial) == 191 < first_tilted == 300
    assert all(trial.arm_b[a][:first] == trial.arm_a[a][:first] for a in trial.arm_a)
    assert min(trial.arm_b["BTC"]) < 0 and all(p >= 0 for a, v in trial.arm_b.items() if a != "BTC" for p in v)


@pytest.mark.parametrize("name", ["b3-btc-overlay"])
def test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits(monkeypatch, name):
    window, lookbacks = _b3_overlay_short_state(monkeypatch)
    reads = _b3_short_reads()
    own = _b3_overlay_own_books(*reads, window=window, lookbacks=lookbacks)
    # Non-vacuity: the short borrows BTC at some closes, so the twin and arm B differ.
    assert own["no_borrow"] != own["limited_b"][0] and any(own["short"])

    inputs = subjects._b3_overlay_inputs(reads)

    trial = inputs.trial
    assert (trial.h4_ts, trial.h4_prices, trial.close) == (reads[0], reads[1], [t + timedelta(hours=4) for t in reads[0][:-1]])
    assert trial.returns == own["returns"] and (trial.ranked, trial.tilted) == (own["ranked"], own["tilted"])
    assert (trial.arm_a, trial.engaged_a) == own["limited_a"] and (trial.arm_b, trial.engaged_b) == own["limited_b"]
    assert (inputs.no_borrow, inputs.state, inputs.short) == (own["no_borrow"], own["state"], own["short"])


@pytest.mark.parametrize("name", ["b3-btc-overlay"])
def test_the_b3_overlay_inputs_pass_both_arms_and_the_twin_through_the_limits(monkeypatch, name):
    _b3_overlay_short_state(monkeypatch)
    reads = _b3_short_reads()
    untilted = _recording(monkeypatch, "_b4_ensemble", lambda arguments, result: result)
    shorted = _recording(monkeypatch, "with_btc_short", lambda arguments, result: result)
    # A factor below 1 at every bar, so a book the limits never scale keeps its raw positions and fails the comparison.
    _recording(monkeypatch, "limit_factors", lambda arguments, result: ([0.5] * len(result[0]), result[1]))

    inputs = subjects._b3_overlay_inputs(reads)

    ((_, raw_a),) = untilted
    borrowed, held = (result for arguments, result in sorted(shorted, key=lambda call: not call[0]["borrow"]))
    halved = [{i: [p * 0.5 for p in v] for i, v in book.items()} for book in (raw_a, borrowed, held)]
    assert [inputs.trial.arm_a, inputs.trial.arm_b, inputs.no_borrow] == halved


def _b3_overlay_built_inputs() -> subjects._B3OverlayInputs:
    """Trial 1's hand-made books with arm B's BTC moved below 0 from return index 500 to 699 and the twin's floored there,
    the state and the short each a pattern of their own, the short's first at 300 — for the metrics alone."""
    trial = _b3_built_inputs()
    n = len(trial.close)
    arm_b = trial.arm_b | {"BTC": [p - 0.3 if 500 <= k < 700 else p for k, p in enumerate(trial.arm_b["BTC"])]}
    no_borrow = arm_b | {"BTC": [max(0.0, p) for p in arm_b["BTC"]]}
    state = [k % 5 < 2 for k in range(n)]
    short = [0.1 + 0.001 * (k % 7) if k % 5 == 0 and k >= 300 else 0.0 for k in range(n)]
    return subjects._B3OverlayInputs(trial._replace(arm_b=arm_b), no_borrow, state, short)


def _b3_overlay_own_engagement(inputs: subjects._B3OverlayInputs) -> dict:
    close = inputs.trial.close
    shortfall = [max(0.0, -p) for p in inputs.trial.arm_b["BTC"]]
    opened = [max(0.0, s - p) for s, p in zip(shortfall, [0.0, *shortfall[:-1]])]
    return {
        "short_state_per_year": per_year_counts(inputs.state, close),
        "overlay_per_year": per_year_counts([s > 0 for s in inputs.short], close),
        "overlay_first_engaged": next(k for k, s in enumerate(inputs.short) if s > 0),
        "shortfall_stamps_per_year": per_year_counts([s > 0 for s in shortfall], close),
        "shortfall_mean_per_year": per_year_means(shortfall, close),
        "shortfall_max": max(shortfall),
        "carry_per_year": per_year_sums([0.0002 * (s + o) for s, o in zip(shortfall, opened)], close),
    }


@pytest.mark.parametrize("name", ["b3-btc-overlay"])
def test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short(
    monkeypatch, name
):
    inputs = _b3_overlay_built_inputs()
    trial, start = inputs.trial, 200
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    trial_1s = subjects._b3_metrics(trial, n_trials=3)
    heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b3_overlay_metrics(inputs, n_trials=3)

    net_a, net_t = (_b3_own_net(trial, book, 1.0) for book in (trial.arm_a, inputs.no_borrow))
    reads = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    assert [arguments for arguments, _ in heads][2:] == [
        reads | {"book_net_of_cost": net_t[start:], "benchmark_net_of_cost": net_a[start:]}
    ]
    twin = heads[2][1]
    assert metrics == {
        **trial_1s,
        "no_borrow_ann_sharpe_noc": sharpe(net_t, periods_per_year=2190),
        "no_borrow_head_to_head_mean_outperf_primary": twin["mean_outperformance"],
        "no_borrow_head_to_head_spa_p_primary": twin["spa_p_value"],
        **_b3_overlay_own_engagement(inputs),
    }
    assert (metrics["tilt_first_engaged"], metrics["overlay_first_engaged"]) == (200, 300)


@pytest.mark.parametrize("name", ["b3-btc-overlay-preflight"])
def test_the_b3_overlay_preflight_reads_trial_1s_preflight_and_the_short_and_costs_no_other_book(monkeypatch, name):
    inputs = _b3_overlay_built_inputs()

    def refused(*args, **kwargs):
        raise AssertionError("the pre-flight read a head-to-head")

    monkeypatch.setattr(subjects, "net_of_cost_verdict", refused)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    trial_1s = subjects._b3_preflight_metrics(inputs.trial, n_trials=3)
    costed = _recording(monkeypatch, "_b4_net", lambda arguments, result: result)

    metrics = subjects._b3_overlay_preflight_metrics(inputs, n_trials=3)

    assert costed and all(arguments["positions"] is inputs.trial.arm_a for arguments, _ in costed)
    assert metrics == trial_1s | _b3_overlay_own_engagement(inputs)


@pytest.mark.parametrize("name", ["b3-btc-overlay"])
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_the_b3_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    flags = [] if plain else ["--register", "--iteration", "iter-194", "--family", "B3", "--n-trials", "2"]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials 2 is not 3, the count {name} declares and deflates at: pass --n-trials 3"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output
```

  - `_RULED_FIXTURES` gains `"b3-btc-overlay": _b2_dataset,` after `"b3-tilt-slow": _b2_dataset,`; `_DECLARED_COUNT` gains `"b3-btc-overlay": "_B3_OVERLAY_N_TRIALS",` after `"b3-tilt-slow": "_B3_SLOW_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b3-btc-overlay": ("B3", 3),` after `"b3-tilt-slow": ("B3", 2),`; `_CONTRACT_DATASETS` gains, after its `"b3-tilt-slow-preflight"` entry:

```python
    "b3-btc-overlay": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
    "b3-btc-overlay-preflight": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
```

  **Author's call** — new guards where the code is new, trial 1's where it is trial 1's, every new case in seconds so each is a probe's target: the declaration — the 54 and 35 keys as trial 1's with the overlay's seven and the twin's three, typed from the spec, the spec, seeds, rule, `no_verdict`, family, count and the state's and the short's four constants; the rule's rows on `_B3_OVERLAY_ADOPTING`, the dead knob the overlay's, read before `passes`; the builders on stand-ins for trial 1's reads, the new inputs and the new computes, so the subject name each passes, its arguments in order, the inputs half it builds and the compute and count it calls are each seen; the `--as-of` rows reaching `_b3_overlay_build`'s own check; the books on trial 1's `_b3_short_reads`, a 480-stamp union the reads would refuse, with the state's SMA and horizons patched to 40 and (5, 10, 20) closes so that the state holds on it — from return index 59, the book flat until 181, the short first moving a position at 191, the tilt at 300 — so that a constant read past the patch, the 1,200-close SMA among them, empties the state; the bit-identity read off the inputs to that first short, the first engagement the short's, and no alt below 0; every field of `_b3_overlay_inputs` held to `_b3_overlay_own_books`, the test's own build through `a2_book_returns`, `b3_book_returns`, A1's two state functions and `limit_factors`, never the subject's halves or the module; the limits' wiring on arm A, arm B and the twin with the factor rewritten at every bar; the metrics on trial 1's `_b3_built_inputs` with arm B's BTC moved below 0 from 500 to 699, the state and the short patterns of their own, held to trial 1's `_b3_metrics` and `_b3_preflight_metrics` at the count, the twin's head-to-head from the first engagement and the overlay's seven keys computed by the test's own hand — the shortfall and its carry with the opening charge written out; the plain eval and the count refused before any read. The reads, trial 1's metrics and engagement and the tilted ensemble are trial 1's functions, guarded by trial 1's cases, which these subjects call unchanged. Every new function is parametrised by the subject's name, so `tests/retired_subjects.py`'s hook marks each case `retired` once Task 6 retires the names. The shared rows — the contract, tracked-spec, shared-defaults and deflation rows, which `_RULED_FIXTURES`, `_DECLARED_COUNT` and `_CONTRACT_DATASETS` reach — run both subjects end to end on `_b2_dataset`, the trial's arm B and bars among them.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00149 && uv run pytest tests/test_research_command.py -k "b3_overlay or ruled_subjects_declare or declares_the_metric_keys or (b3_subject_refuses_as_of and b3-btc-overlay)" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt`: collection completes and every selected case fails at its call — on a key `SUBJECTS` lacks, a name `subjects` lacks or a subject the CLI does not know (measured on the base's `cli/research/subjects.py`: `24 failed, 961 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — after `from cli.alpha.b3 import b3_book_returns` and before `from cli.alpha.b4 import (`, the line `from cli.alpha.b3_overlay import btc_short_state, overlay_short, with_btc_short`; after `_build_b3_tilt_slow_preflight`'s body and before `SUBJECTS: dict[str, Subject] = {`, two blank lines on each side:

```python
# docs/specs/00149 D2-D8: B3's trial 3, trial 1's tilt with a BTC short while A1's confirmed-bear state holds on BTC: trial
# 1's reads, ensemble, metrics and engagement, trial 58's arm A, limits, costing and bar.
_B3_OVERLAY_WINDOW = 1200  # docs/specs/00149 D3: A1's 200-day SMA in 4h closes; another value is a new trial
_B3_OVERLAY_BAND = 0.0  # docs/specs/00149 D3: A1's short band, records 15-16's; another value is a new trial
_B3_OVERLAY_LOOKBACKS = (120, 360, 720)  # docs/specs/00149 D3: A1's 20, 60 and 120 days in 4h closes
_B3_OVERLAY_FRACTION = 0.5  # docs/specs/00149 D3: the short, a fraction of the book's long gross; another is a new trial
_B3_OVERLAY_N_TRIALS = 3  # docs/specs/00149 D7: B3's true count with this trial, fixed by the spec's hash; another is a new subject


class _B3OverlayInputs(NamedTuple):
    trial: _B3Inputs
    no_borrow: dict[str, list[float]]
    state: list[bool]
    short: list[float]


def _b3_overlay_inputs(reads: tuple[list[datetime], dict[str, list[float | None]]]) -> _B3OverlayInputs:
    """`_b3_inputs` with arm B carrying the BTC short, its borrow-free twin beside it, and no return of a book."""
    h4_ts, h4_prices = reads
    fed = _ffill_btc(h4_prices)
    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))
    raw_b, ranked, tilted = _b3_ensemble(fed)
    state = btc_short_state(fed["BTC"], window=_B3_OVERLAY_WINDOW, band=_B3_OVERLAY_BAND, lookbacks=_B3_OVERLAY_LOOKBACKS)
    short = overlay_short(raw_b, state, fraction=_B3_OVERLAY_FRACTION)
    arm_b, engaged_b = _b4_limited(with_btc_short(raw_b, short, borrow=True))
    no_borrow, _ = _b4_limited(with_btc_short(raw_b, short, borrow=False))
    returns = {a: _asset_returns(fed[a]) for a in h4_prices}
    trial = _B3Inputs(h4_ts, h4_prices, close_grid(h4_ts), returns, arm_a, arm_b, engaged_a, engaged_b, ranked, tilted)
    return _B3OverlayInputs(trial, no_borrow, state, short)


def _b3_overlay_engagement(inputs: _B3OverlayInputs) -> dict:
    close, short = inputs.trial.close, inputs.short
    shortfall = _b4_shortfall(inputs.trial.arm_b)
    return {
        "short_state_per_year": per_year_counts(inputs.state, close),
        "overlay_per_year": per_year_counts([s > 0 for s in short], close),
        "overlay_first_engaged": next((k for k, s in enumerate(short) if s > 0), len(close)),
        "shortfall_stamps_per_year": per_year_counts([s > 0 for s in shortfall], close),
        "shortfall_mean_per_year": per_year_means(shortfall, close),
        "shortfall_max": max(shortfall),
        "carry_per_year": per_year_sums(shortfall_carry(shortfall, rate=_B4_CARRY_RATE), close),
    }


def _b3_overlay_metrics(inputs: _B3OverlayInputs, *, n_trials: int) -> dict:
    trial = inputs.trial
    metrics = _b3_metrics(trial, n_trials=n_trials)
    start = _b3_first_engaged(trial)
    net_a = _b4_net(trial.arm_a, trial.returns, stress=1.0)
    net_t = _b4_net(inputs.no_borrow, trial.returns, stress=1.0)
    verdict = net_of_cost_verdict(net_t[start:], net_a[start:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
    return {
        **metrics,
        "no_borrow_ann_sharpe_noc": sharpe(net_t, periods_per_year=PPY_4H),
        "no_borrow_head_to_head_mean_outperf_primary": verdict["mean_outperformance"],
        "no_borrow_head_to_head_spa_p_primary": verdict["spa_p_value"],
        **_b3_overlay_engagement(inputs),
    }


def _b3_overlay_preflight_metrics(inputs: _B3OverlayInputs, *, n_trials: int) -> dict:
    """Trial 1's pre-flight figures and the overlay's engagement: no return of arm B or of its twin."""
    return {**_b3_preflight_metrics(inputs.trial, n_trials=n_trials), **_b3_overlay_engagement(inputs)}


def _b3_overlay_build(
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
        return compute(_b3_overlay_inputs(_b3_reads(subject, reader, dataset, window, accept_holes)), n_trials=_B3_OVERLAY_N_TRIALS)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, RiskError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b3_btc_overlay(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b3_overlay_build("b3-btc-overlay", _b3_overlay_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b3_btc_overlay_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b3_overlay_build(
        "b3-btc-overlay-preflight", _b3_overlay_preflight_metrics, reader, dataset, window, as_of, accept_holes
    )


# docs/specs/00149 D7's matrix and the two instrument findings its metrics show: a change to it is a new spec and a new
# trial, never an edit here.
def _b3_btc_overlay_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["overlay_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"


# docs/specs/00149 D8's keys: trial 1's, the overlay's engagement and the borrow-free twin's.
_B3_OVERLAY_ENGAGEMENT_KEYS = frozenset(
    {
        "short_state_per_year",
        "overlay_per_year",
        "overlay_first_engaged",
        "shortfall_stamps_per_year",
        "shortfall_mean_per_year",
        "shortfall_max",
        "carry_per_year",
    }
)
_B3_OVERLAY_METRIC_KEYS = (
    _B3_METRIC_KEYS
    | _B3_OVERLAY_ENGAGEMENT_KEYS
    | {"no_borrow_ann_sharpe_noc", "no_borrow_head_to_head_mean_outperf_primary", "no_borrow_head_to_head_spa_p_primary"}
)
_B3_OVERLAY_PREFLIGHT_KEYS = _B3_PREFLIGHT_KEYS | _B3_OVERLAY_ENGAGEMENT_KEYS
```

  `SUBJECTS` gains, after its `"b3-tilt-slow-preflight"` entry and before its closing `}`:

```python
    "b3-btc-overlay": Subject(
        "b3-btc-overlay",
        (240,),
        _ASSETS,
        _build_b3_btc_overlay,
        spec="docs/specs/00149-b3-btc-overlay-design.md",
        metric_keys=_B3_OVERLAY_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b3_btc_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay shorts no BTC at any stamp; no "
            "verdict, the trial unspent"
        ),
        family="B3",
        n_trials=_B3_OVERLAY_N_TRIALS,
    ),
    "b3-btc-overlay-preflight": Subject(
        "b3-btc-overlay-preflight",
        (240,),
        _ASSETS,
        _build_b3_btc_overlay_preflight,
        spec="docs/specs/00149-b3-btc-overlay-design.md",
        metric_keys=_B3_OVERLAY_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` ) or `b3-tilt-slow-preflight` ( `` becomes `` ), `b3-tilt-slow-preflight` ( ``, and the row's closing `` the figures `b3-rank-tilt-preflight` reads; it has no rule, so its run is kept with `--reading`). | `` becomes:

```markdown
the figures `b3-rank-tilt-preflight` reads; it has no rule, so its run is kept with `--reading`), `b3-btc-overlay` (`b3-rank-tilt`'s comparison with the tilted book also short BTC, at half its long gross, while BTC closes below its 200-day average and its 20-, 60- and 120-day trends mostly point down, the short netted against the book's own BTC and the rest borrowed at the margin rate; the 4h series of `--dataset`, a frozen set only) or `b3-btc-overlay-preflight` (that comparison's instrument check, the figures `b3-rank-tilt-preflight` reads beside the short's; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the shared rows measured at 10 s or more on the authoring tree (call time: the shared-defaults rows 35.94 s and 29.53 s, the evaluate rows 18.10 s and 14.82 s, the deflation row 15.49 s):

```text
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b3-btc-overlay]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-btc-overlay-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-btc-overlay-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b3-btc-overlay-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b3-btc-overlay]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, measured `24 passed, 979 deselected` (about 8 s; the inputs cases 3.62 s, 1.84 s and 1.81 s, every other under 1 s); then the shared rows, `mkdir -p .tmp/plan-00149 && uv run pytest tests/test_research_command.py -k "b3-btc-overlay and not b3_" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt`, one plain blocking call, `timeout` 600000 ms (measured `19 passed, 984 deselected in 116.63s`, every row but the five step 5 lists under 1 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' list over the four paths in its four parts (measured on the authoring tree in the scratch worktree: `580 passed, 423 deselected in 241.30s`, `227 passed, 776 deselected in 312.01s`, `71 passed, 932 deselected in 88.68s`; the other direct readers with `tests/test_alpha_b3_overlay.py`, `4156 passed, 73 deselected in 126.51s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured in the scratch worktree on the authoring tree, 71 of 71); the metric-keys lines, the ruled-subjects literal and the contract, shared-defaults, deflation and tracked-spec rows are new rows of existing tests, not new guards, and are not probed; the two `--as-of` rows, new rows of an existing test, reach `_b3_overlay_build`'s own check and are probed (rows 35–36):

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/^_B3_OVERLAY_N_TRIALS = 3\b/_B3_OVERLAY_N_TRIALS = 4/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/^_B3_OVERLAY_WINDOW = 1200 /_B3_OVERLAY_WINDOW = 200 /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/^_B3_OVERLAY_BAND = 0.0 /_B3_OVERLAY_BAND = 0.05 /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/^_B3_OVERLAY_LOOKBACKS = (120, 360, 720) /_B3_OVERLAY_LOOKBACKS = (20, 60, 120) /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/^_B3_OVERLAY_FRACTION = 0.5 /_B3_OVERLAY_FRACTION = 0.25 /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/00149-b3-btc-overlay-design/00148-b3-tilt-slow-design/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay-preflight": Subject(/,/^    ),/s/00149-b3-btc-overlay-design/00148-b3-tilt-slow-design/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/verdict=_b3_btc_overlay_verdict,/verdict=_b3_rank_tilt_verdict,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/family="B3",/family="B4",/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/metric_keys=_B3_OVERLAY_METRIC_KEYS,/metric_keys=_B3_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay-preflight": Subject(/,/^    ),/s/metric_keys=_B3_OVERLAY_PREFLIGHT_KEYS,/metric_keys=_B3_PREFLIGHT_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/^        _build_b3_btc_overlay,$/        _build_b3_rank_tilt,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay-preflight": Subject(/,/^    ),/s/^        _build_b3_btc_overlay_preflight,$/        _build_b3_rank_tilt_preflight,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/or the overlay shorts no BTC at any stamp; no /or the overlay shorts no BTC; no /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/^        "shortfall_max",$/        "shortfall_peak",/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/| {"no_borrow_ann_sharpe_noc", "no_borrow_head_to_head_mean_outperf_primary", /| {"no_borrow_head_to_head_mean_outperf_primary", /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_pair_declares_trial_1s_keys_with_the_overlays_its_own_spec_rule_and_count_and_a1s_state[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/ or not any(m\["overlay_per_year"\].values()):/:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[the-overlay-never-shorts-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/if not m\["arm_a_passes"\] or not any/if not any/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-a-fails-its-bar-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/    if not m\["passes"\]:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[arm-b-fails-its-bar-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/< 0.05 else/<= 0.05 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[p-at-exactly-0.05-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/\["head_to_head_mean_outperf_primary"\] > 0:/["head_to_head_mean_outperf_primary"] >= 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-at-exactly-0-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/m\["head_to_head_mean_outperf_primary"\] > 0:/m["head_to_head_mean_outperf_full"] > 0:/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[mean-negative-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/return "adopt" if m\["head_to_head_spa_p_primary"\] < 0.05 else "park"/return "park" if m["head_to_head_spa_p_primary"] < 0.05 else "adopt"/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[outperforms-significantly-from-the-first-engagement-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_btc_overlay_verdict(/def _b3_btc_overlay_verdict_gone(/' --mutation '/^def _b3_btc_overlay_verdict(/,/^_B3_OVERLAY_ENGAGEMENT_KEYS/s/m\["head_to_head_spa_p_primary"\] < 0.05/m["head_to_head_spa_p_full"] < 0.05/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_rule_maps_its_metrics_to_a_verdict_or_a_stop[outperforms-significantly-from-the-first-engagement-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation 's/_b3_overlay_build("b3-btc-overlay", _b3_overlay_metrics,/_b3_overlay_build("b3-rank-tilt", _b3_overlay_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-_b3_overlay_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation 's/_b3_overlay_build("b3-btc-overlay", _b3_overlay_metrics,/_b3_overlay_build("b3-btc-overlay", _b3_overlay_preflight_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-_b3_overlay_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation 's/        "b3-btc-overlay-preflight", _b3_overlay_preflight_metrics,/        "b3-btc-overlay", _b3_overlay_preflight_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-preflight-_b3_overlay_preflight_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation 's/        "b3-btc-overlay-preflight", _b3_overlay_preflight_metrics,/        "b3-btc-overlay-preflight", _b3_overlay_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-preflight-_b3_overlay_preflight_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation 's/, n_trials=_B3_OVERLAY_N_TRIALS)$/, n_trials=_B3_N_TRIALS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-_b3_overlay_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation 's/, n_trials=_B3_OVERLAY_N_TRIALS)$/, n_trials=_B3_N_TRIALS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-preflight-_b3_overlay_preflight_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation 's/return compute(_b3_overlay_inputs(_b3_reads(/return compute(_b3_inputs(_b3_reads(/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-_b3_overlay_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation '/^def _b3_overlay_build(/,/^def /s/_b3_reads(subject, reader, dataset, window, accept_holes)/_b3_reads(subject, reader, dataset, window, False)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-_b3_overlay_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation '/^def _b3_overlay_build(/,/^def /s/_b3_reads(subject, reader, dataset, window, accept_holes)/_b3_reads(subject, reader, dataset, None, accept_holes)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_overlay_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-btc-overlay-_b3_overlay_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation '/^def _b3_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_as_of_before_any_read[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_build(/def _b3_overlay_build_gone(/' --mutation '/^def _b3_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_as_of_before_any_read[b3-btc-overlay-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation '/^def _b3_overlay_inputs(/,/^def /s/    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))/    arm_a, engaged_a = _b4_limited(_b3_ensemble(fed)[0])/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation '/^def _b3_overlay_inputs(/,/^def /s/    fed = _ffill_btc(h4_prices)/    fed = dict(h4_prices)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation '/^def _b3_overlay_inputs(/,/^def /s/    returns = {a: _asset_returns(fed\[a\]) for a in h4_prices}/    returns = {a: _asset_returns(h4_prices[a]) for a in h4_prices}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation '/^def _b3_overlay_inputs(/,/^def /s/    raw_b, ranked, tilted = _b3_ensemble(fed)/    raw_b, ranked, tilted = _b3_slow_ensemble(fed)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/btc_short_state(fed\["BTC"\], window=/btc_short_state(h4_prices["BTC"], window=/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/window=_B3_OVERLAY_WINDOW, band=/window=1200, band=/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/band=_B3_OVERLAY_BAND, lookbacks=/band=0.05, lookbacks=/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/lookbacks=_B3_OVERLAY_LOOKBACKS)/lookbacks=(120, 360, 720))/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/fraction=_B3_OVERLAY_FRACTION)/fraction=0.25)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/    short = overlay_short(raw_b, state, /    short = overlay_short(_b4_ensemble(fed), state, /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/with_btc_short(raw_b, short, borrow=True)/with_btc_short(raw_b, short, borrow=False)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/with_btc_short(raw_b, short, borrow=False)/with_btc_short(raw_b, short, borrow=True)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/    return _B3OverlayInputs(trial, no_borrow, state, short)/    return _B3OverlayInputs(trial, no_borrow, state, [0.0] * len(short))/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_build_arm_a_and_arm_b_with_the_short_and_its_twin_each_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/    arm_b, engaged_b = _b4_limited(with_btc_short(raw_b, short, borrow=True))/    arm_b, engaged_b = _b4_limited(with_btc_short(raw_b, [0.0] * len(short), borrow=True))/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_arms_agree_bit_for_bit_until_the_overlay_first_shorts_and_no_alt_is_shorted[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/^    arm_b, engaged_b = _b4_limited(with_btc_short(raw_b, short, borrow=True))$/    arm_b, engaged_b = with_btc_short(raw_b, short, borrow=True), _b4_limited(with_btc_short(raw_b, short, borrow=True))[1]/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_pass_both_arms_and_the_twin_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation 's/^    no_borrow, _ = _b4_limited(with_btc_short(raw_b, short, borrow=False))$/    no_borrow = with_btc_short(raw_b, short, borrow=False)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_pass_both_arms_and_the_twin_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_inputs(/def _b3_overlay_inputs_gone(/' --mutation '/^def _b3_overlay_inputs(/,/^def /s/^    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))$/    arm_a, engaged_a = _b4_ensemble(fed), _b4_limited(_b4_ensemble(fed))[1]/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_inputs_pass_both_arms_and_the_twin_through_the_limits[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_metrics(/def _b3_overlay_metrics_gone(/' --mutation 's/^    start = _b3_first_engaged(trial)$/    start = 0/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_metrics(/def _b3_overlay_metrics_gone(/' --mutation 's/    net_t = _b4_net(inputs.no_borrow, trial.returns, stress=1.0)/    net_t = _b4_net(trial.arm_b, trial.returns, stress=1.0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_metrics(/def _b3_overlay_metrics_gone(/' --mutation 's/    metrics = _b3_metrics(trial, n_trials=n_trials)/    metrics = _b3_metrics(trial, n_trials=1)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_metrics(/def _b3_overlay_metrics_gone(/' --mutation 's/"no_borrow_head_to_head_mean_outperf_primary": verdict\["mean_outperformance"\],/"no_borrow_head_to_head_mean_outperf_primary": verdict["spa_p_value"],/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_metrics(/def _b3_overlay_metrics_gone(/' --mutation '/^def _b3_overlay_metrics(/,/^def /s/"no_borrow_ann_sharpe_noc": sharpe(net_t, periods_per_year=PPY_4H),/"no_borrow_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_metrics(/def _b3_overlay_metrics_gone(/' --mutation '/^def _b3_overlay_metrics(/,/^def /s/net_t\[start:\], net_a\[start:\]/net_t, net_a/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation 's/"short_state_per_year": per_year_counts(inputs.state, close),/"short_state_per_year": per_year_counts([s > 0 for s in short], close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation 's/"overlay_per_year": per_year_counts(\[s > 0 for s in short\], close),/"overlay_per_year": per_year_counts(inputs.state, close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation 's/"overlay_first_engaged": next((k for k, s in enumerate(short) if s > 0)/"overlay_first_engaged": next((k for k, s in enumerate(short) if s >= 0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation 's/    shortfall = _b4_shortfall(inputs.trial.arm_b)/    shortfall = _b4_shortfall(inputs.no_borrow)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation '/^def _b3_overlay_engagement(/,/^def /s/"shortfall_max": max(shortfall),/"shortfall_max": max(short),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation '/^def _b3_overlay_engagement(/,/^def /s/shortfall_carry(shortfall, rate=_B4_CARRY_RATE)/shortfall_carry(shortfall, rate=0.0001)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation '/^def _b3_overlay_engagement(/,/^def /s/"shortfall_mean_per_year": per_year_means(shortfall, close),/"shortfall_mean_per_year": per_year_sums(shortfall, close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_engagement(/def _b3_overlay_engagement_gone(/' --mutation '/^def _b3_overlay_engagement(/,/^def /s/"shortfall_stamps_per_year": per_year_counts(\[s > 0 for s in shortfall\], close),/"shortfall_stamps_per_year": per_year_counts([s >= 0 for s in shortfall], close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_reads_trial_1s_metrics_the_twins_head_to_head_from_the_first_engagement_and_the_short[b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_preflight_metrics(/def _b3_overlay_preflight_metrics_gone(/' --mutation 's/    return {\*\*_b3_preflight_metrics(inputs.trial, n_trials=n_trials), \*\*_b3_overlay_engagement(inputs)}/    return {**_b3_metrics(inputs.trial, n_trials=n_trials), **_b3_overlay_engagement(inputs)}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_preflight_reads_trial_1s_preflight_and_the_short_and_costs_no_other_book[b3-btc-overlay-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_overlay_preflight_metrics(/def _b3_overlay_preflight_metrics_gone(/' --mutation 's/    return {\*\*_b3_preflight_metrics(inputs.trial, n_trials=n_trials), \*\*_b3_overlay_engagement(inputs)}/    return {**_b3_preflight_metrics(inputs.trial, n_trials=n_trials)}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_preflight_reads_trial_1s_preflight_and_the_short_and_costs_no_other_book[b3-btc-overlay-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/verdict=_b3_btc_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation '/"b3-btc-overlay": Subject(/,/^    ),/s/n_trials=_B3_OVERLAY_N_TRIALS,/n_trials=2,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b3-btc-overlay]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D3, D8 and D9 give the new code. The declaration: the count, the state's window, band and horizons, the short's fraction, each subject's spec, the seeds, the rule, the family, each subject's keys, each builder, the `no_verdict` text, an engagement key and a twin key (rows 1–17). The rule: the overlay's dead knob, arm A's bar, arm B's bar, the p's bound, the mean's bound, the primary read, the adopt and park returns and the primary's p (rows 18–25). The builders: each passing its own subject's name and its own compute, the count each passes, the inputs half the build calls, and the window and the holes flag reaching the reads (rows 26–34). The `--as-of` refusal on both subjects (rows 35–36). The inputs: arm A untilted, the BTC fill, the assets' returns on the filled BTC, trial 1's ensemble, the state on the filled BTC, its window, band and horizons read through the constants, the fraction, the short sized on arm B's book, each book's borrow flag and the short kept (rows 37–49), the bit-identity to the first short (row 50), and arm B, the twin and arm A through the limits (rows 51–53). The metrics: the twin's start, its book, the count trial 1's metrics are called at, the twin's keys and its full-window read (rows 54–59). The engagement: the state's and the short's counts, the first short, the shortfall's book, its maximum, the carry's rate, its mean and its count (rows 60–67). The pre-flight: trial 1's pre-flight in place of its metrics, and the overlay's keys kept (rows 68–69). The plain eval and the count (rows 70–71). **Author's call — the clauses no row moves.** `_b3_overlay_build`'s compute-error clause, D9's `SubjectError` naming the subject and its window: the contract rows' spoilt fixtures raise through it, and their check, `<name> over the full history`, holds as well against the command's own refusal of an evaluation error, as trial 1's and trial 2's clauses were measured; either way the run exits 1, an open attempt ending failed and counting 0, and Task 5 step 4 quotes the line into T0016. `_b3_overlay_metrics`' own `net_a`, trial 58's `_b4_net` on arm A, is held through the twin's head-to-head in row 54's case. The three tilted arms' `A2Config` clauses are trial 1's `_b3_ensemble`'s, unchanged and guarded by trial 1's rows.
- [ ] **Step 9: Commit** — `feat(research): B3 trial 3's subjects — trial 1's rank tilt of the A2 ensemble's long weights with a BTC short while A1's confirmed-bear state holds, and its pre-flight twin, on a frozen set's full history`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 3: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D10)

**Files:** Create `tests/test_research_b3_btc_overlay_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 2's `_b3_overlay_inputs` and `_b3_overlay_engagement` and trial 1's `_b3_reads` and `_b3_engagement`; `cli.alpha.b1.book_turnover`; `cli.registry.observed.ObservedReader`, `cli.registry.record.compute_hash` and `cli.research.command._DATA_ROOT`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`. Produces one test, its own `trial_inputs()`, and the module names `BLOCK`, `VOUCHED`, `RETURN_INDICES`, `TILT`, `ENGAGEMENT` and `NO_BORROW`, which Task 4's check programs import. No test computes a return of a book.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, records 58's, 60's and 61's figures read off the committed records:

```python
"""B3 trial 3's inputs half against spec 00149's measured basis."""

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
_NONE = dict.fromkeys(_YEARS, 0.0)
# Copied from the spec's measured basis, never from a run.
BLOCK = "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
# Trial 1's tilt, unchanged: its engagement is record 60's stored figures, read off the record.
TILT = ("tilted_per_year", "ranked_assets_histogram", "ranked_assets_mean")
ENGAGEMENT = {
    "tilt_first_engaged": 1_230,
    "primary_returns": 26_107,
    "stamps_positions_differ": 12_493,
    "positions_differ_per_year": _YEARS
    | {
        "2014": 332,
        "2015": 457,
        "2018": 801,
        "2019": 668,
        "2020": 419,
        "2021": 1_934,
        "2022": 1_826,
        "2023": 2_021,
        "2024": 1_848,
        "2025": 1_792,
        "2026": 395,
    },
    "turnover_b": 216.05774709807375,
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
    "short_state_per_year": _YEARS
    | {
        "2014": 1_038,
        "2015": 1_096,
        "2018": 1_522,
        "2019": 806,
        "2020": 331,
        "2021": 421,
        "2022": 1_900,
        "2023": 270,
        "2024": 414,
        "2025": 660,
        "2026": 495,
    },
    "overlay_per_year": _YEARS
    | {
        "2014": 332,
        "2015": 457,
        "2018": 801,
        "2019": 668,
        "2020": 248,
        "2021": 252,
        "2022": 1_540,
        "2023": 194,
        "2024": 307,
        "2025": 421,
        "2026": 350,
    },
    "overlay_first_engaged": 1_230,
    "shortfall_stamps_per_year": _YEARS
    | {"2018": 623, "2019": 544, "2020": 217, "2021": 199, "2022": 1_437, "2023": 178, "2024": 307, "2025": 415, "2026": 339},
    "shortfall_mean_per_year": _NONE
    | {
        "2018": 0.008849321558105853,
        "2019": 0.009562699914014232,
        "2020": 0.004447907274989879,
        "2021": 0.0011967031387723332,
        "2022": 0.02383134038097913,
        "2023": 0.0037384793611536823,
        "2024": 0.009359009965511707,
        "2025": 0.005135563259268716,
        "2026": 0.05735237611576036,
    },
    "shortfall_max": 0.2907872334820236,
    "carry_per_year": _NONE
    | {
        "2018": 0.004150086469044866,
        "2019": 0.004381962309770746,
        "2020": 0.0021500975698908443,
        "2021": 0.0005914662643196171,
        "2022": 0.010977979120356715,
        "2023": 0.001849522542579138,
        "2024": 0.004532077251367467,
        "2025": 0.0024507149403084714,
        "2026": 0.006488353705264844,
    },
}
NO_BORROW = {"differ_from_arm_b": 4_259, "turnover": 191.899092913884}


def trial_inputs():
    """The trial's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b3_overlay_inputs(subjects._b3_reads("b3-btc-overlay", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set is absent under data/",
)
def test_the_btc_overlay_inputs_reproduce_the_measured_basis_record_60s_tilt_and_record_58s_arm_a():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    trial = inputs.trial
    block = reader.block()
    assert compute_hash(block) == BLOCK == _trials()[60]["dataset_hash"] and reader.vouched_status() == VOUCHED
    assert len(trial.close) == RETURN_INDICES
    record = _trials()[58]
    assert block["ohlc-full"]["files"] == {p: h for p, h in record["datasets"]["ohlc-full"]["files"].items() if "/EUR/" in p}
    assert book_turnover(trial.arm_a) == record["metrics"]["turnover_a"]
    engagement = subjects._b3_engagement(trial) | subjects._b3_overlay_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert {key: engagement[key] for key in TILT} == {key: _trials()[60]["metrics"][key] for key in TILT}
    differ = sum(any(inputs.no_borrow[a][k] != trial.arm_b[a][k] for a in trial.arm_b) for k in range(RETURN_INDICES))
    assert {"differ_from_arm_b": differ, "turnover": book_turnover(inputs.no_borrow)} == NO_BORROW
    assert min(inputs.no_borrow["BTC"]) == 0.0 and all(min(v) >= 0.0 for a, v in trial.arm_b.items() if a != "BTC")
```

  **Author's call** — the case holds the subject's inputs half to the spec's books and cells programs, which built arm B by trial 1's `b3_book_returns`, the state by A1's two functions and the short and its netting written out, and were themselves held to records 58 and 60 — two derivations that must agree; the block to record 60's `dataset_hash` and to record 58's ten EUR files, arm A to record 58 by its turnover, and the tilt's three keys to record 60's stored figures, never a second typing; the integer engagement, arm B's and the twin's turnover, the shortfall's maximum and its per-year means and carry exactly; no BTC of the twin below 0 and no alt of arm B.
- [ ] **Step 2: Run it** — with `data/ohlc-full` linked in this worktree: `mkdir -p .tmp/plan-00149 && uv run pytest tests/test_research_b3_btc_overlay_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, a call of 145.45 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b3_btc_overlay_basis.py::test_the_btc_overlay_inputs_reproduce_the_measured_basis_record_60s_tilt_and_record_58s_arm_a
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b3_btc_overlay_basis.py tests/slow-cases.txt`; the Global Constraints' list over the two paths (measured on the authoring tree in the scratch worktree, `18 passed, 1 deselected in 18.68s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00149 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt` (measured `334 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B3 trial 3's inputs half against the measured basis — the block, the short state, the first short, the BTC borrowed and its carry, the closes where the books differ, the limits, arm B's and the twin's turnover, record 60's tilt and record 58's arm A`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_b3_btc_overlay_basis.py::test_the_btc_overlay_inputs_reproduce_the_measured_basis_record_60s_tilt_and_record_58s_arm_a`, the line `It reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the loop's pick of the variant (D1) and then **Author's call** the trial's conventions, plan 00148's form — one commit, the two entries — so that both stand in the log before any return of trial 3's arm B is read; no owner's entry, the owner's word standing in the `[iter-193] B3's next step after trial 1` entry:

```markdown
[iter-194] B3 trial 3's variant — trial 1's tilt with the A1-short BTC overlay, the loop's pick under the owner's word (Decision: 1)
  The owner's sequence of 2026-10-25 (the `[iter-193] B3's next step after trial 1` entry above) takes the A1-short BTC overlay second, after trial 2's verdict (registry trial 61, the `[iter-193] Verdict — B3 trial 2 REJECT` entry above), and B3's close third; which tilt the overlay goes on is the loop's pick, made before spec 00149's hash.
  1. **Trial 1's tilt with the overlay** — arm B trial 1's arm B, M = 180 closes, k = 0.5 and the floor 8, `b3_book_returns` as record 60 ran it, with a BTC short of half the book's long gross while A1's confirmed-bear state holds on BTC: master plan §5's B3 as written, its tilt the one spec 00147 fixed before any B3 result was read; spec 00149, count 3: the short first moves a position at return index 1,230 (close 2014-05-01 04:00), 26,107 return indices from it, the books differing at 12,493, BTC borrowed at 4,259 at a carry of 0.32 % a year, arm B trading 216.06 against arm A's 146.19 (spec 00149's measured basis); one B slot, 9 to 8. Chosen.
  2. **Trial 2's tilt with the overlay** — M = 540, a value chosen after trial 1's look, which compounds the contamination; its gross edge was no larger, about +2.37e-06/bar against +2.53e-06, arithmetic over records 60's and 61's stored figures.
  3. **The overlay alone on arm A** — isolates the short, but is not B3 and asks the A family's question, whose budget is spent, 40 of 40.

[iter-194] B3 trial 3's conventions, pinned by spec 00149 before its hash (Decision: 1)
  The trial's details are fixed in the spec, reviewed, and frozen by its sha256, its record's `spec_hash`, before any return of trial 3's arm B or its twin is read, or a net-of-cost series, head-to-head or bar leg of either computed, over the data; each call below is one the spec pins, the loop's or the author's as the spec marks it, every value the owner or specs 00128, 00133, 00137, 00144, 00147 and 00148 fixed staying theirs.
  1. **As the spec pins them, trial 1's tilt with a BTC short while A1's confirmed-bear state holds** — the owner's sequence, its second step, the tilt the loop's pick (D1); frozen `ohlc-full`, full history, the ten EUR assets' 4h union as records 45–61 read it, no other pair, no as-of, trial 1's reads (D2); arm A the adopted ensemble, record 58's arm A to the bit; arm B trial 1's arm B, record 60's, with the short: the state A1's confirmed bear read on BTC alone — its close below its 200-day SMA (1,200 closes), band 0.0, and its trend agreement over 20, 60 and 120 days (120, 360 and 720 closes) below 0 — at the A family's configuration, read off the A1 records and spec 00031 and never tuned, holding at 8,953 of 27,337 return indices; the short half the book's long gross at the close, the book flat at 3,383 of the state's closes, so that the short hedges what the book holds and the book is never net short, set beside half of NAV and half the vol target's scale, each measured; the short netted against the book's own BTC, the rest borrowed; the overlay in a new module, `cli/alpha/b3_overlay.py`, no existing function changed (D3); trial 58's costing, `_b4_net` at 0.006 a side less the carry on the borrowed BTC at 0.0002 per 4h with the opening charge, 0.32 % a year measured (D4); §10's limits as trial 58 wired them on the book with the short, engaging no bar, the per-asset caps unwired as records 58–61 left them, the netted short above 0.10 at 397 return indices (D5); the borrow-unavailable twin, the short floored at the book's own BTC, recorded as record 58's three `no_borrow_*` keys beside the matrix (D6); the contamination stated in full — trial 3 designed after trials 1's and 2's rejects, their net head-to-heads and cost arithmetic recorded, the overlay named before any B3 result and its state and size chosen after them on engagement figures alone, 11,665 of the primary read's 26,107 returns the span records 60 and 61 read, the A family's ~5 %/yr carry a prior named, the DSR counting B3's true trials (D7); trial 1's bar at count 3 and `var_trials` 0.0, B3's convention, the head-to-head from arm B's first engagement, return index 1,230, deciding, trial 1's matrix through a rule of the trial's own reading the overlay's engagement for the dead knob, the park row naming no variant (D8); trial 1's eleven engagement keys and the overlay's seven, 54 and 35 keys, the subjects `b3-btc-overlay` and `b3-btc-overlay-preflight`, the variant `B3-btc-overlay-a2eq-full-v1`, the build in three halves (D9); no `--verdict`, notes naming only what is fixed before the run (D10); an adopt recorded, never deployed, B3 closed after any verdict on the owner's word, every B3 subject retired at the close, a stop the owner's (D11). Chosen.
  2. **The alternatives each weighed** — trial 2's tilt under the overlay, or the overlay alone; the state on daily closes, at bar-count windows, or at the band 0.05 A1's sweep favoured; the short at half of NAV, at half the vol target's scale, or capped at §10's per-asset 0.10; trial 1's rule, whose dead knob the tilt alone satisfies; `var_trials` at B1's family dispersion, which reads arm B's Sharpe before the run; the subjects kept after the close.
  Source: spec 00149 (D1–D11), its **Author's call**s and the calls it carries from the owner and specs 00128, 00133, 00137, 00144, 00147 and 00148; the owner's words quoted in the `[iter-193] B3's next step after trial 1` entry above.
```

  Staged alone, its gate the Global Constraints' list over the staged path with `tests/test_decisions_log_shape.py` and `tests/test_decisions_log_ties.py` by path (measured in the scratch worktree over the authoring tree, the two entries appended, `50 passed`) — `consumers.sh --direct` names no test reader of the log, its stderr saying `(none -- …)`, so those two are the whole list — and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-194] the loop's pick of B3 trial 3's variant — trial 1's tilt with the A1-short BTC overlay — and B3 trial 3's conventions, pinned by spec 00149 before its hash`. Neither heading holds a verdict word, and neither is a heading T0016's B3 arm or Task 6's stop arm greps for (measured: the stop arm's check prints 0 with the entries appended).
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes or reads trial 3's arm B or its twin's returns or net-of-cost series, a head-to-head or a bar leg of either — through the code, a program or arithmetic over a stored figure — or runs either new subject over the real data, before the spec's hash, and the data-gated case runs with `ohlc-full` linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D10)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00149-b3-btc-overlay-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; the code path since record 61's run — the spec's basis lists it from that run's commit to the branch's cut — `git log --oneline 1431ef7b2b3cc2b70cd4851b1726d33b6624995a..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1–2's commits and their fixes alone (measured at the base: nothing); any other commit is named, step 4 deciding whether it moved the inputs half or the computes trial 3 reuses.
- [ ] **Step 2: D10 (1), the spec hash** — `sha256sum docs/specs/00149-b3-btc-overlay-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D10 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record or a reading another branch's merged PR carries — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0016's — then takes a delta read of the merge in place of re-running step 1: step 1's code-path log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 3 step 6's sentence with its "before the spec's hash" read "before Task 5's run, records 60's and 58's replays excepted", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the trial — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. A B3 record another branch landed raises `required_n("B3")` above 3, and the run is then refused before its fit (D8): the trial stops, T0016's. The check has two sites, this step and Task 5 step 1, and both take this path.
- [ ] **Step 4: D10 (3), the data test on the run's tree, with the subjects' two fixture rows and records 60's and 58's replays** — with `data/ohlc-full` linked: `mkdir -p .tmp/plan-00149 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b3_btc_overlay_basis.py 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-btc-overlay-evaluates]' 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-btc-overlay-preflight-evaluates]' 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-60]' 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-58]' -q -p no:cacheprovider --basetemp=.tmp/plan-00149/pt > .tmp/plan-00149/basis.out 2>&1`, one background call: `5 passed`, never a skip or an xfail — the fixture rows run the build end to end on the tree a fix of the reads may have changed, record 60's replay rebuilds trial 1's stored figures through the reads, tilted ensemble, arm A, costing, bar, head-to-head and metrics this trial's halves call, and record 58's through the carry on a borrowed BTC, the limits on a book that borrows and the twin's head-to-head (measured on the authoring tree in the scratch worktree, the first three `3 passed in 180.25s`, the replays `1 passed` each, calls of 261.82 s and 302.38 s); a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code, a replay's a moved computes half — T0016's, and the run waits.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00149/preflight_check.py`, D10's (a)–(e) in order, the dead knob read before the engagement, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00149 D10's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b3_btc_overlay_basis import BLOCK, ENGAGEMENT, RETURN_INDICES, TILT, VOUCHED
from tests.test_trial_registry_provenance import _trials

out = Path(".tmp/plan-00149/b3-btc-overlay-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if compute_hash(block) != BLOCK:
    sys.exit("(a) the inputs' block differs from the spec's")
if run["vouched"] != VOUCHED:
    sys.exit("(a) the set is not vouched as the spec reads it")
record = _trials()[61]["metrics"]
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
    sys.exit(f"(b) arm A does not reproduce record 61's arm A: {off}")
shorted, borrowed = sum(m["overlay_per_year"].values()), sum(m["shortfall_stamps_per_year"].values())
print(f"first engaged {m['tilt_first_engaged']} primary {m['primary_returns']} differ {m['stamps_positions_differ']}")
print(f"shorted {shorted} borrowed {borrowed} shortfall_max {m['shortfall_max']} turnover_b {m['turnover_b']}")
if not any(m["overlay_per_year"].values()):
    sys.exit("(c) the overlay shorts no BTC: the dead knob")
tilt = _trials()[60]["metrics"]
off = [key for key, value in ENGAGEMENT.items() if m[key] != value] + [key for key in TILT if m[key] != tilt[key]]
if off:
    sys.exit(f"(d) the engagement differs from the measured basis: {off}")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00149/record_check.py`, the record's checks, its one argument the spec's sha256:

```python
"""Spec 00149 D9's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b3_btc_overlay_basis import BLOCK, ENGAGEMENT, TILT
from tests.test_trial_registry_provenance import _trials

name, spec_hash = "b3-btc-overlay", sys.argv[1]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00149/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00149/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
tilt = _trials()[60]["metrics"]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block == BLOCK,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"])
    == ("B3", 3, "B3-btc-overlay-a2eq-full-v1", "iter-194", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": {key: m[key] for key in ENGAGEMENT} == ENGAGEMENT and all(m[key] == tilt[key] for key in TILT),
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `mkdir -p .tmp/plan-00149 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00149/preflight_check.py .tmp/plan-00149/record_check.py`. The pre-flight check was run in the scratch worktree over a synthetic pre-flight print carrying the real block, read by `_b3_reads` with no compute, the basis's engagement, record 60's tilt keys and record 61's arm A figures: it printed the block, the first engagement, the primary count, the differing stamps, the shorted and borrowed counts, the shortfall's maximum, arm B's turnover and the bar's flags and exited 0; with `passes` 0 it exited 1 on `(e) arm A fails its bar`, and with `overlay_per_year` counting no close on `(c) the overlay shorts no BTC: the dead knob`.

## Task 5 (the controller's): trial 3 — its pre-flight, its run and its record (D8–D10)

`<H>` is Task 4 step 2's sha256.

**The notes rule**: every free-text `--notes` this plan passes is written first, in a call of its own, to its own file under `.tmp/plan-00149/` by a quoted heredoc — `mkdir -p .tmp/plan-00149 && cat > <its file> <<'EOF'`, the text on the lines after it, `EOF` alone on the last — and passed as `--notes "$(cat <its file>)"` behind `test -s <its file> &&` in the run's own line: no `'` or `"` in the text can end the argument, and an absent or empty file stops the line before `uv run` starts, never a run with empty notes — its output file not written, nothing spent, the file written again before the line runs again. The sites, the whole of them: step 3's reading, `.tmp/plan-00149/b3-btc-overlay-reading-notes.txt`, and step 4's trial, `.tmp/plan-00149/b3-btc-overlay-notes.txt` — the two `--notes` spec 00149 D10 names, in its steps (4) and (5); no other step of this plan passes one.

- [ ] **Step 1: The develop check** — Task 4 step 3 whole, its stop, its merge path and Task 4 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `mkdir -p .tmp/plan-00149 && uv run zcrypto research eval --subject b3-btc-overlay-preflight --dataset ohlc-full > .tmp/plan-00149/b3-btc-overlay-preflight.out 2>&1`, a plain eval of a subject with no rule — the inputs half and one bar, about two and a half minutes (the spec's basis: the inputs half 145.45 s, one bar 11.16 s) — one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00149/preflight_check.py`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(e): D10's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0016's with its line; a refused build — exit 1 with no traceback, its output naming `b3-btc-overlay-preflight over the full history: …` — prints no metrics, keeps no reading, and is recorded in Task 6's T0016 findings with its line quoted, the trial unspent.
- [ ] **Step 3: On a stop, the reading** — its notes, by the notes rule, in `.tmp/plan-00149/b3-btc-overlay-reading-notes.txt`: `B3 trial 3's pre-flight (spec 00149 D10): <the check's sys.exit line, whole, between single quotes, never a double quote>; no verdict, the trial unspent`; then `mkdir -p .tmp/plan-00149 && test -s .tmp/plan-00149/b3-btc-overlay-reading-notes.txt && uv run zcrypto research eval --subject b3-btc-overlay-preflight --dataset ohlc-full --reading --iteration iter-194 --spec-hash <H> --notes "$(cat .tmp/plan-00149/b3-btc-overlay-reading-notes.txt)" > .tmp/plan-00149/b3-btc-overlay-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `mkdir -p .tmp/plan-00149 && test -s .tmp/plan-00149/b3-btc-overlay-notes.txt && uv run zcrypto research eval --subject b3-btc-overlay --dataset ohlc-full --register --iteration iter-194 --family B3 --n-trials 3 --variant B3-btc-overlay-a2eq-full-v1 --spec-hash <H> --notes "$(cat .tmp/plan-00149/b3-btc-overlay-notes.txt)" > .tmp/plan-00149/b3-btc-overlay.out 2>&1`, about four minutes (the spec's basis: the inputs half, seven bars and three head-to-heads, about 240 s; records 60's and 61's runs 264 s and 262 s), one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run to `.tmp/plan-00149/b3-btc-overlay-notes.txt` by the notes rule, name only what is fixed before it: `subject b3-btc-overlay over ohlc-full, full history, no as-of; B3 trial 3, the second step of the owner's sequence of 2026-10-25 after trial 1's reject - the tilt at another M or k, then the A1-short overlay, then B3 closed - trial 2 having rejected too; arm A the adopted equal-weight A2 4h ensemble on the ten EUR assets, arm B trial 1's arm B - each arm's inverse-vol weights of the assets it holds long tilted at every 4h close by their centred rank in the whole basket on the trailing 180-close simple return, each long times 1 + 0.5 z, the longs rescaled to their untilted sum, where the basket ranks 8 assets or more - with a BTC short of half the book's long gross at every close BTC closes below its 1200-close (200-day) SMA, band 0.0, with its trend agreement over 120, 360 and 720 closes (20, 60 and 120 days) below 0, A1's confirmed-bear state read on BTC at the A family's configuration; the short netted against the book's own BTC and the rest borrowed at 0.0002 per 4h rollover plus the opening charge on each increase; alts never shorted; every asset charged 0.006 per side on its own turnover; the section 10 gross cap, net band and margin floor, one factor per bar, the per-asset caps unwired; the hypothesis: the tilted, hedged book has a higher mean net-of-cost return than the untilted, unhedged ensemble from the first close the two books differ; n_trials 3, B3's true count, var_trials 0.0, the DSR leg binding; the head-to-head from return index 1230 (close 2014-05-01 04:00), arm B's first engagement, the short's, decides, the full-window read and the borrow-unavailable twin - the short floored at the book's own BTC - beside it; the contamination: designed after trials 1's and 2's rejects (registry trials 60 and 61), their net head-to-heads -1.92e-05 and -1.08e-05 per bar, the overlay named by the master plan and spec 00147 before any B3 result, its state and size chosen after them on engagement figures alone, 11665 of the primary read's 26107 returns the span records 60 and 61 read, the A family's ~5 %/yr short carry a prior, arm B here borrowing BTC at 4259 return indices at a measured carry of 0.32 % a year and trading 216.06 against arm A's 146.19; pre-flight: block ff2e5700..., arm A <the seven anchors>, the bar's dsr <its dsr> and SPA p <its spa_p_value>, passes 1, the short above 0 at 5570 return indices from return index 1230, BTC borrowed at 4259, no limit engaged, turnover_b <its value>; the park row names no variant, B3 closing after the verdict on the owner's word; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, a B3 record landed elsewhere, or bucket B spent — comes before the fit or after the print, naming each orphan, the count or the bucket's figure: no record, no reading; T0016 carries it (Task 6). A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; b = [x["attempt"] for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b3-btc-overlay"]; print(b[-1], [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == b[-1]] or "open") if b else print("none")'`: `none` — no begin line names the subject — is a refusal before the attempt opened, recorded in T0016 with the run's last line, the trial unspent; a refused build ends its attempt failed, counting 0, recorded in T0016 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0016's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00149/record_check.py <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 6 step 3). A failed check — this one, the record's replay in step 6, or on step 6's stop arm the reading's line check and its replay — stops the task where it stands: what the run appended, the record or the reading, stays in place uncommitted and nothing is committed; the controller hands the owner the failing check's output quoted whole, and what becomes of the record or reading is the owner's word, Task 6 waiting on it.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-194] Verdict — B3 trial 3 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B3 n=3)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D8's table (`sed -n '/^| Arm A.s bar and the overlay/,/^  Every quantity the matrix reads/p' docs/specs/00149-b3-btc-overlay-design.md`), with `arm_a_passes`, `overlay_per_year` summed, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary` unrounded, the full-window pair beside them; `n_trials` 3, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); `max_drawdown` beside `arm_a_max_drawdown`; the twin's three keys; the pre-flight's block, anchors and `passes` from `.tmp/plan-00149/b3-btc-overlay-preflight.out`; the engagement — `tilt_first_engaged`, `overlay_first_engaged`, `primary_returns`, `stamps_positions_differ`, `short_state_per_year`, `overlay_per_year` and `shortfall_stamps_per_year` summed, `shortfall_max`, `carry_per_year` summed, `turnover_a` beside `turnover_b`, `limit_engaged_per_year`'s totals; beside records 60 and 61, their `head_to_head_mean_outperf_primary` and `turnover_b`, stored; the contamination D7 states, pointing at the conventions entry above; on an adopt D11's path in its order; on any verdict B3 closing after it (Task 6); on a reject the hypothesis as the notes word it, archived — in the form of `[iter-193] Verdict — B3 trial 2 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b3-btc-overlay": 3,` after `"b3-tilt-slow": 2,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B3 trial 3's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries its tilt and its BTC short adopts` (D11), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`. Then `git add` by path of `docs/reference/trial-registry.jsonl`, the record step 4's run appended, `docs/research/10.phase4-decisions.md`, `tests/test_trial_registry_provenance.py` and `tests/slow-cases.txt`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and `docs/open-topics/README.md`; the list over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, the set linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter194/.tmp/plan-00149/probe/data/ohlc-full`, unlinked after the replay and the probe with `test -L <its absolute path> && unlink <its absolute path>` and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt`, one background call: `1 passed`, never a skip, its result line and call time for the message — a difference or a skip is a failed check, step 5's stop; then the literal's probe, expected `KILLED` (its two seds dry-run on the authoring tree, each changing one line): `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_btc_overlay(/def _build_b3_btc_overlay_gone(/' --mutation 's/^_B3_OVERLAY_N_TRIALS = 3\b/_B3_OVERLAY_N_TRIALS = 4/' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit that index, with no `git add` after the setup, as `docs(research): B3 trial 3 registered — <verdict>, the A2 ensemble's long weights tilted by a cross-sectional momentum rank and hedged by a BTC short while A1's confirmed-bear state holds, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b3-btc-overlay-preflight` with outcome `null`, or `b3-btc-overlay` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones, a line off any of them a failed check, step 5's stop — the entry is `[iter-194] B3 trial 3 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` at its `sorted()` place, the replay rebuilding the run over the real set, as (iii) adds the record's; `git add` by path of `docs/reference/reading-ledger.jsonl`, the reading the run appended, `docs/research/10.phase4-decisions.md` and `tests/slow-cases.txt`, then the record arm's list, pre-commit, probe worktree and replay, with `-k 'reading-<its id>'`, `1 passed`, never a skip; committed as `docs(research): B3 trial 3 — instrument finding, kept as reading <id>; no trial spent` with no literal's probe. On a refusal from the count or a refused build: no commit here; Task 6 records it.

## Task 6: B3's close — the entry, the retirement, T0016 and the index (D11)

**Files:** `docs/research/10.phase4-decisions.md`, `tests/retired_subjects.py`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`.

Every figure is read off the committed record or reading and its entry. Task 5's outcome picks the arm: a verdict other than an adopt — park or reject — takes the verdict arm; an adopt the adopt arm; no verdict — a stop kept as a reading, a refused build, a refusal from the count, a merge aborted at a develop check, the data test or a replay failing or skipping, or any other end Task 5 sends to T0016 — the stop arm. The verdict arm and the adopt arm close B3, on the owner's word (D11); the stop arm closes nothing, writes no close entry and retires no subject.

- [ ] **Step 1: The close entry** (the verdict arm and the adopt arm) — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, below Task 5's verdict entry, every `<…>` read off the record and its verdict entry, the budget off step 3's count:

```markdown
[iter-194] B3 closed — the third step of the owner's sequence of 2026-10-25, after trial 3's verdict (Decision: 1)
  The owner's words, attended, 2026-10-25, as the `[iter-193] B3's next step after trial 1` entry above records them — at 2026-10-25T15:32:38Z: "let's wait for the round-23 review and PR first. after its PR merge, sequentially Option 1 -> 2 -> 3"; at the session's restart, 2026-10-25T16:23:14Z: "session restarted, continue the work until all the 3 options finished" — read there as B3 trial 2, then B3 trial 3, then B3 closed, whatever each verdict; trial 3's verdict is <ADOPT, PARK or REJECT>, registry trial <N> (the `[iter-194] Verdict — B3 trial 3 <ADOPT, PARK or REJECT>` entry above).
  1. **Close the family** — B3 closes on its three trials: trial 1, the A2 ensemble's long weights tilted by a cross-sectional momentum rank on a 180-close score, REJECT (registry trial 60); trial 2, the tilt on a 540-close score, REJECT (registry trial 61); trial 3, trial 1's tilt with a BTC short while A1's confirmed-bear state holds, <ADOPT, PARK or REJECT> (registry trial <N>). Chosen, the owner's word.
  2. **A further B3 trial** — another tilt, another short state or size, each a B slot; the owner's sequence is spent.
  What the family leaves: the shared Bucket-B budget reads <spent> of 25 (B1 <B1>, B2 <B2>, B3 <B3>, B4 <B4>), <remain> remaining; every B3 subject retired; T0016's next steps per §5's ranking, C2 → C3 → C1.
```

  On the adopt arm the last line gains, before `; every B3 subject retired`, `; trial 3's ADOPT recorded, never deployed, its P1 combination trial over record 47's book the owner's (spec 00149 D11)`. **Author's call — the heading holds no verdict word**: `tests/test_decisions_log_ties.py` reads a heading holding a verdict word beside the word `trial` as a verdict on a trial with no tie (measured in the scratch worktree: the entry with sample figures passes the decisions-log tests).
- [ ] **Step 2: The retirement** (the verdict arm and the adopt arm) — in `tests/retired_subjects.py`, after the line `        "b4-sol-noborrow-rolling-preflight",` and before `    }`:

```python
        # B3's finished trials.
        "b3-rank-tilt",
        "b3-rank-tilt-preflight",
        "b3-tilt-slow",
        "b3-tilt-slow-preflight",
        "b3-btc-overlay",
        "b3-btc-overlay-preflight",
```

  **Author's call** (D11) — spec 00146 D11's settlement for B4, measured: B4's close added its last two subjects to `RETIRED_SUBJECTS` in its topic commit, every B4 subject retired and none removed from `SUBJECTS`; so here every B3 subject, their code kept for records 60's, 61's and this record's replays. `tests/test_alpha_b3_overlay.py` names no subject and stays in CI.
- [ ] **Step 3: T0016**, per `topic-ops`, each anchor counted unique with `grep -c` before its edit and the heading set (`grep '^#'`) compared before and after:
  - `## Findings so far`: the budget bullet's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B3", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` (at this branch's base it printed `{'B1': 5, 'B2': 7, 'B3': 2, 'B4': 2} remain 9 []`; on trial 3's record, with no orphan, it prints `{'B1': 5, 'B2': 7, 'B3': 3, 'B4': 2} remain 8 []`): `(B1 spent 5, B2 spent 7, B3 spent 2, B4 spent 2, 9 remain)` reads `(B1 spent <its B1>, B2 spent <its B2>, B3 spent <its B3>, B4 spent <its B4>, <its remain> remain)`, each orphan it lists named there; after the `**B3 trial 2 REJECT (iter-193, spec 00148, registry trial 61).**` bullet, one bullet `**B3 trial 3 <VERDICT> (iter-194, spec 00149, registry trial <N>).**` — the row that fired and the short's engagement in one or two sentences, pointing at its decisions-log entry for the figures — or, on the stop arm, `**B3 trial 3, no verdict (iter-194, spec 00149).**`, naming the reading by id where one was kept and quoting whole the line that stopped it — the check's `sys.exit` line, the conflict `git merge` printed, which stands in no file, only in the controller's call, and so reaches this task quoted whole in the controller's dispatch of it, the failure or skip line in `.tmp/plan-00149/basis.out`, the line in `.tmp/plan-00149/b3-btc-overlay-preflight.out` or `.tmp/plan-00149/b3-btc-overlay.out`, or that run's output's end as Task 5 step 4 quotes it — the trial unspent unless the count lists its attempt as an orphan, which spends the slot.
  - `## Done so far`: the **B3 opened** bullet's last sentence, `` the subjects `b3-tilt-slow` and `b3-tilt-slow-preflight` and the data-gated basis test `tests/test_research_b3_tilt_slow_basis.py`; every B3 subject kept until B3 closes. ``, becomes on the verdict arm and the adopt arm `` the subjects `b3-tilt-slow` and `b3-tilt-slow-preflight` and the data-gated basis test `tests/test_research_b3_tilt_slow_basis.py`. Trial 3 (iter-194, spec/plan `00149`, registry trial <N>) <VERDICT>, trial 1's tilt with the A1-short BTC overlay, the second: the module `cli/alpha/b3_overlay.py`, the subjects `b3-btc-overlay` and `b3-btc-overlay-preflight` and the data-gated basis test `tests/test_research_b3_btc_overlay_basis.py`; every B3 subject retired; **closed at iter-194** on the owner's word of 2026-10-25. ``; on the stop arm `` the subjects `b3-tilt-slow` and `b3-tilt-slow-preflight` and the data-gated basis test `tests/test_research_b3_tilt_slow_basis.py`. Trial 3 (iter-194, spec/plan `00149`), trial 1's tilt with the A1-short BTC overlay, the second: the module `cli/alpha/b3_overlay.py`, the subjects `b3-btc-overlay` and `b3-btc-overlay-preflight` and the data-gated basis test `tests/test_research_b3_btc_overlay_basis.py`; no verdict, no slot spent, every B3 subject kept. ``, or, where the budget bullet's count lists trial 3's attempt as an orphan, `` …; no verdict, one slot spent by its orphaned attempt, every B3 subject kept. ``
  - `## Standing prerequisites …`: on the verdict arm and the adopt arm, `B4 trial 1 records the rung for its BTC shortfall (the `no_borrow_*` keys of registry trial 58).` becomes `B4 trial 1 records the rung for its BTC shortfall (the `no_borrow_*` keys of registry trial 58), B3 trial 3 for its BTC short (registry trial <N>'s).`
  - `## Suggested next steps`: its one bullet, `` - B3 trial 3, the A1-short BTC overlay (master plan §5's B3 whole), the next step of the owner's sequence of 2026-10-25 (the `[iter-193] B3's next step after trial 1` entry); then B3 closed, the sequence's last step; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``, becomes on the verdict arm and the adopt arm `` - B3 closed on the owner's sequence of 2026-10-25 (the `[iter-194] B3 closed` entry); per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``; on the adopt arm a bullet after it, `` - (owner) B3 trial 3's ADOPT (registry trial <N>), recorded, never deployed: its path in order — a P1 combination trial over record 47's book carrying the tilt and the BTC short, outside every bucket's budget, then T0123's promotion path (spec 00149 D11). ``; on the stop arm the bullet becomes instead `` - (owner) B3's next step after trial 3's stop — trial 3 run again once its cause, quoted in Findings, is fixed, or B3 closed unrun — recorded as a `[iter-NNN] B3's next step after trial 3's stop` entry; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``
  - `ripe_when`: its B3 arm, `` B3: an activity, B3 trial 3 — the A1-short BTC overlay, the next step of the owner''s sequence of 2026-10-25 — ripe once trial 2''s verdict is recorded, check: `grep -c -E ''^\[iter-[0-9]+\] Verdict — B3 trial 2 '' docs/research/10.phase4-decisions.md` prints at least 1; `` (the trailing space included), is removed on the verdict arm — the C3, C2 and C1 arms as they stand; becomes on the adopt arm `` B3: an activity, the owner''s call on the P1 combination trial over record 47''s book carrying B3 trial 3''s ADOPT, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B3 trial 3.s combination trial'' docs/research/10.phase4-decisions.md` prints at least 1; `` (spec 00149 D11, spec 00146 D11's form); and on the stop arm `` B3: an activity, the owner''s call on trial 3''s stop — the trial run again once its cause is fixed, or B3 closed unrun — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B3.s next step after trial 3.s stop'' docs/research/10.phase4-decisions.md` prints at least 1; `` — in the frontmatter's single quotes, each `'` inside it doubled as written here, the check kept in its own backticks, its `.` standing for the apostrophe a shell's single quotes cannot hold; the other families' arms unchanged.
  **Author's call — each arm's check reads a heading no entry carries yet**: measured in the scratch worktree, the stop arm's and the adopt arm's checks print 0 on the log with Task 3's entries appended; each arm applied to the base's T0016 and then reverted — the verdict arm with sample figures, the close entry and the retirement, the stop and adopt arms' `ripe_when` alone — kept the heading set, parsed to the intended frontmatter text and, with step 4 applied, passed `tests/test_open_topics_frontmatter.py tests/test_topics_index.py` (`1111 passed` on the stop and adopt arms) and, on the verdict arm, those with `tests/test_retired_subjects.py tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py` (`1166 passed`).
- [ ] **Step 4: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 5: Gate and commit** — `git add` the step's paths by name — `docs/research/10.phase4-decisions.md`, `tests/retired_subjects.py`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md` and `docs/open-topics/README.md` on the verdict and adopt arms, the last two on the stop arm; the Global Constraints' list over them, `tests/test_research_command.py` in its four parts if the list names it, with `tests/test_open_topics_frontmatter.py`, `tests/test_retired_subjects.py`, `tests/test_decisions_log_shape.py` and `tests/test_decisions_log_ties.py` by path; `uv run pre-commit run -a` until clean; committed on the verdict and adopt arms as `docs(open-topics): B3 closed after trial 3 on the owner's word, T0016 to the C families; every B3 subject retired`, its message naming no guard added or changed and so no probe, and on the stop arm as `docs(open-topics): T0016 after B3 trial 3's stop — no verdict, B3's next step the owner's; its subjects kept`.

## Task 7 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-194 — B3 trial 3: the BTC overlay, B3 closed` (65 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 5–6's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replays the messages record run with `ohlc-full` linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the verdict or the stop and B3's close, the pre-flight's output quoted whole in a fenced block (`.tmp/plan-00149/b3-btc-overlay-preflight.out`), every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the owner's two statements of the sequence the trial and the close run under, each quoted with its stamp as the `[iter-193] B3's next step after trial 1` entry carries them, and the session transcript named as the source of both quotes and their stamps, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00149` collected and removed, and the link removed with `test -L <the checkout>/data/ohlc-full && unlink <the checkout>/data/ohlc-full` in this worktree and in each reader's checkout whose `data/` holds it; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full` still there.

Decisions log: the loop's pick of trial 3's variant and the conventions entry (Task 3 step 5), before the hash; the verdict or instrument-finding entry (Task 5 step 6), in its record's commit; after a verdict, B3's close entry (Task 6 step 1), the owner's word of 2026-10-25 its source — on a stop, B3's next step is the owner's, its entry a later branch's (T0016's trigger).
