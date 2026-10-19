# B1 trial 5 — the hourly exit check, the two subjects and the gated run — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next. Execution is subagent-driven — the author's call, made unattended, nobody asked. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths` over every path the File structure names prints `tier: full`, for `tests/test_research_command.py`, `docs/reference/trial-registry.jsonl` and `tests/test_trial_registry_provenance.py`).

**Goal:** the module `cli/alpha/b1_exit.py` (the breach test, A2's state machine with the hourly exit check and its early and false events, the interior closes, arm B's slot directions and positions on arm A's weights and vol scalar, the interval's price paths, the split costing, the engagement counts), the ruled subject `b1-hourly-channel-exits` and its evaluate-only pre-flight twin `b1-hourly-channel-exits-preflight`, the data-gated basis and arm-A tests, and B1's trial 5 registered once through spec 00133's trial-attempts log, its verdict in the registry, the decisions log, T0022 and T0016 — and on an adopt T0123's qualified trigger and the engine-design topic.

**Architecture:** the module holds pure functions over lists, as `cli/alpha/b1_volume.py` does, importing `cli.alpha.a1`'s `_map_to_union_index` and `_validate_prices_by_asset`, `cli.alpha.a2`'s `A2Config` and `cli.features.channel_position`, editing none of them; D2's `new_low` and `donchian_signal_hourly_exit` and D3's `net_of_cost_hourly` are the spec's code blocks verbatim. The subjects sit in `cli/research/subjects.py` after trial 4's and reuse trial 3's reads half `_b1_hourly_rv_reads` unchanged (D5), the B1 literals, `_B1_HOURLY_RV_GRID`, `_b2_over`, `net_of_cost`, `book_turnover`, `benchmark_4h_net_of_cost`, `calendar_year_slices`, `a1_kill_bar`, `reality_check_pvalue` and `net_of_cost_verdict`; the build has D11's three halves — the reads, `_b1_hourly_exit_inputs` (arm A, the interior closes, both arms' directions, the exit events and the price paths, no position or return of arm B) and each subject's metrics. Spec 00133 is on the branch's first-parent line (D12's gate), so the module, the subjects, the run's record and its verdict land in this branch's one pull request.

**Tech Stack:** Python 3.14 through uv; polars for the parquet reads; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00135-b1-hourly-channel-exits-design.md` — binding; D1–D13 are cited by name, and the values below are copied from it verbatim. Spec 00133's trial-attempts log is merged on develop (pull request #730, `64d416754`); this plan names its interfaces as the code at `aa50f1ad5` gives them, in each task's Interfaces block. **Iteration:** iter-179. **Topic:** T0022 under T0016. **Branch:** `research/iter-179-b1-hourly-channel-exits`, worktree `.claude/worktrees/iter179`. A choice this plan makes that the spec leaves open is marked **Author's call**.

## Global Constraints

- Arm A is records 45, 46, 48 and 49's (D1): `fed = _ffill_btc(h4_prices)`; for each `(lookbacks, target_vol)` in `_B1_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))`, `a2_book_returns(fed, config=A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=_B1_LOOKBACK, basket_lookback=_B1_LOOKBACK, periods_per_year=PPY_4H))`; arm A the per-asset `statistics.mean` of the three `asset_positions` at every return index. `_B1_COST_PER_SIDE`, `_B1_A2_ARMS`, `_B1_LOOKBACK`, `_B1_DECISIVE_START`, `_B1_N_RESAMPLES`, `_B1_FROM_2016` and the SPA grid `_B1_HOURLY_RV_GRID` are reused, never restated.
- Arm B (D1): each arm's position on asset `a` in slot `i` of return index `k` is `weights_a[k].get(a, 0.0) * d_b[a][k][i] * vt_a[k]` — `0.0` in place of `d_b[a][k][i]` where `d_b[a][k]` is `None` — with `weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)`, one path for the three arms, and `vt_a` that arm's `a2_book_returns(...)["vol_target_positions"]`; averaged per asset per slot over the three arms as arm A is. With every interior hourly close absent, B's four slot states, slot directions, slot positions and net equal A's exactly.
- The check (D2): A2's 4h rule on `own_prices`, the non-`None` prices of `fed[a]`, `band` 1.0; the breach is `channel_position`'s expression on the last `w − 1` four-hour closes `own_prices[j+2−w .. j]` with the hourly close `h` in `close[j+1]`'s place, `hi > lo and 2 * (h - lo) / (hi - lo) - 1 <= -band`; the interior closes of the interval after own bar `j` are the closes of the hourly bars opening at `own_ts[j+1]`, `own_ts[j+1] + 1h` and `own_ts[j+1] + 2h` (offsets 1–3); at the first interior close in time order that breaches while the lookback is at +1 its state becomes −1 for the rest of the interval; a lookback at −1 or at its initial 0 is not checked; a missing interior hour is skipped; at `close[j+1]` the 4h rule runs from B's state; an exit event `(j, offset)` is early when `new_low(prior, own_prices[j+1], band=band)`, false otherwise; a config with `short="on"` is refused (`AlphaError`).
- Slots, paths and cost (D3): return index `k` has four slots, slot 0 from `close[k]` to the first interior close, slot `i` from the interior close at offset `i`; `P0 = fed[a][k]`, `P_i` the close of the hourly bar opening at `h4_ts[k+1] + (i − 1)h` or `P_{i−1}` where that hour is missing, `P4 = fed[a][k+1]`, no path where `fed[a][k]` or `fed[a][k+1]` is `None`; the gross `Σ_i p_i · (P_{i+1} − P_i) / P0`, an interval whose four slot positions are equal `p0 * (P4 / P0 - 1)`; every position change, at a boundary and at an interior close, charged `cost_per_side · |Δp|`, never rescaled by its drift; `turnover_b` is `book_turnover` over each asset's slot positions flattened in time order from flat, `turnover_b_intra` is `Σ_a Σ_k Σ_{i=1..3} |p_i − p_{i−1}|`; the ×1.5 series is the same function at `1.5 * _B1_COST_PER_SIDE`.
- Refusals, never drops (D4, `AlphaError` naming the asset and the stamp): an hourly close that is not a finite number above 0; hourly stamps not strictly increasing, tz-naive or off the hour; an hourly bar whose 240 bar the asset's own series lacks; hourly stamps and closes of unequal length; an `interior` list whose length is not the price series'. BTC's six forward-filled stamps are bars of the state machine's series; an interval ending at one holds no interior close.
- Data (D5): `--dataset ohlc-full`, no `--window`, no `--as-of`; the reads are `_b1_hourly_rv_reads(reader, dataset, window, as_of, accept_holes, subject=subject)`, called unchanged; the inputs' block `8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1` over the ten 240 and ten 60 files, 855,305 rows, span 2013-09-10 20:00 → 2026-03-31 23:00; the union 27,338 stamps, 27,337 return indices; intervals `(240, 60)`; the decisive window from return index 1380; the from-2016 cut at the first `k` with `h4_ts[k] ≥ 2016-01-01T00:00Z`; a per-year figure keyed by the bar-start year `h4_ts[k].year`, an exit event by the bar-start year of the own bar `j` that opens its interval.
- Costing (D6): `returns = {a: _asset_returns(fed[a])}`; arm A's net `net_of_cost(arm_a, returns, cost_per_side=_B1_COST_PER_SIDE)` and its ×1.5 series at `1.5 * _B1_COST_PER_SIDE`; arm B's two through `net_of_cost_hourly` at the same two costs; the benchmark `benchmark_4h_net_of_cost(h4_prices, cost_per_side=_B1_COST_PER_SIDE)` on the raw union prices; the slices `calendar_year_slices(series, h4_ts)`.
- Dispersion (D7): `per_period_sharpe_4h = sharpe(net_b)`, unannualised; `var_trials = statistics.variance([0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177, per_period_sharpe_4h])`; `arm_a_var_trials` the same with `sharpe(net_a)` in arm B's place; held as `_B1_EXIT_RECORDED_PER_PERIOD_SHARPES = (*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, 0.03028127927651177)`; `expected_max_sharpe(5, 1.0)` is `1.192594001014789`.
- Engagement (D8): `exit_events_per_year` is `{arm: {asset: {lookback: {year: [events, early, false]}}}}`, the arm `"1"`–`"3"` in `_B1_A2_ARMS` order, every year in which the asset has a state value present, zeros included; `exit_events`, `exit_events_early`, `exit_events_false` its totals, `share_false = exit_events_false / exit_events`, a build with no exit event refused (`ValidationError`); `hourly_closes_directions_differ` counts the hourly closes `(k, i)`, offset 0 included, at which any arm's clipped slot direction on any asset differs from arm A's direction at `k`, `None` equal to `None`, and `hourly_closes_directions_differ_per_year` every bar-start year of the union's return indices, zeros included; the dead knob is `hourly_closes_directions_differ == 0`; `stamps_positions_differ` counts the return indices at which any asset's arm-B position in any slot differs from arm A's; `turnover_reduction_pct = 100 * (turnover_a - turnover_b) / turnover_a`.
- The bars (D10): arm B's `a1_kill_bar(net_b, bench, n_trials=5, var_trials=var_trials, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`; arm A's the same with `net_a`, arm A's ×1.5 series and slices and `arm_a_var_trials`; every `a1_kill_bar` call passes `n_trials=_B1_EXIT_N_TRIALS` (5). The SPA grid, blocks {30, 102} × seeds {42, 7, 1234}: (30, 42) the headline's `spa_p_value`, the other five `reality_check_pvalue([[net_b[k] - bench[k]] for k in range(1380, n)], mean_block=block, n_resamples=2000, seed=seed)["p_value"]`. The head-to-heads `net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=2000)` over the full window and over `[k16:]`. The drawdown pair over the full series, `max_drawdown_reduction_pct = 100 * (drawdown_a - drawdown_b) / drawdown_a`, B's drawdown below A's when it exceeds 1e-6; a build whose arm A never draws down, or never trades, refused (`ValidationError`).
- A step that copies a spec code block verbatim copies the one fenced `python` block under that decision's `## D<n>` heading of `docs/specs/00135-b1-hourly-channel-exits-design.md`, its comments included — D2's (`new_low`, `donchian_signal_hourly_exit`) and D3's (`net_of_cost_hourly`) in Task 1 step 3, D10's (`_b1_hourly_exit_verdict`) in Task 2 step 3. The rule, `_b1_hourly_exit_verdict`, reads every quantity as a stored key unrounded and reads no turnover.
- The record (D11): family `B1`, `n_trials_in_family` 5, variant `B1-hourly-exit-a2eq-v1`, iteration `iter-179`, seeds (42, 7, 1234), no `--verdict` (D12).
- The subjects (D11): `b1-hourly-channel-exits`, 46 metric keys, with the rule, `family="B1"`, `n_trials=_B1_EXIT_N_TRIALS`, and `no_verdict` "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every hourly close; no verdict, the trial unspent"; `b1-hourly-channel-exits-preflight`, 25 keys, seeds (42,), no rule, family or count; both intervals `(240, 60)`, both declaring `spec="docs/specs/00135-b1-hourly-channel-exits-design.md"`.
- The hash rule (D8, D9): no position, return or direction of either arm, no state, no exit event and no bar is computed over the trial's data before Task 4 step 2 takes the spec's sha256. Tasks 1–3 meet `data/ohlc-full` only through `tests/test_research_b1_hourly_exit_basis.py::test_the_b1_hourly_exit_reads_reproduce_the_measured_basis` — the reads half and `interior_closes_by_asset`, stamps and closes alone; until Task 4 step 2 every other run adds `-m "not data"` and that test runs by node id. No reader, reviewer or plan-review dispatch runs either subject, `_b1_hourly_exit_inputs`, or the module's state machine, directions, positions, paths or costing over the real set before then; every read's dispatch carries this rule. No return of arm B is computed over the trial's data before Task 4 step 6's register run, the first step to compute one. There is no plain eval of `b1-hourly-channel-exits`, before or after it (D12).
- No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b1.py`, `cli/alpha/b1_rv.py`, `cli/alpha/b1_volume.py`, `cli/alpha/b2.py`, `cli/features/*`, `cli/portfolio/*`, `cli/engine/*`, any existing function of `cli/research/subjects.py` or any adopted artifact (D1). Code citations name a function, never a line.
- Never edit `docs/specs/00135-b1-hourly-channel-exits-design.md` after Task 4 step 2, nor `docs/specs/00045-b1-seasonality-conditioning-design.md`, `docs/specs/00132-b1-hourly-rv-weights-design.md` or `docs/specs/00134-b1-volume-confirmation-design.md`, whose hashes records pin; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading` over a committed file, except where Task 4 names it. Never `git stash`; a state-changing git command runs alone.
- Data: `data/ohlc-full` alone, a read-only link to the canonical set, never written under; never `data/ohlc-holdout-*`, never `/mnt/zhao-crypto/`; never ssh, a fleet host, `kraken-cli`, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`.
- Tests: every pytest run is `mkdir -p .tmp/plan-00135 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt` (or a file, or `-k`), split into parts each under 600 s, nothing backgrounded. Before each commit, as the implementer contract (`.claude/skills/zcrypto-plan-review/references/implementer-contract.md`) has it: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path>)` and `[ -n "$T" ] && uv run pytest $T <the changed file's own test> -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt`, never a bare `uv run pytest`; a case reading a mount, a holdout set or a set not linked here is deselected by node id and named in the task report. A commit message's test result line is a run over that commit's own tree.
- Probes: the tier is `full` — `tier.py --paths cli/alpha/b1_exit.py cli/research/subjects.py` prints `tier: light`, and **Author's call**: the commit's own test paths decide, each task reading `uv run python infra/scripts/tier.py HEAD..<its probe commit>` (below), which prints `full` for Tasks 1–3, each changing a test that imports `cli.alpha` or `cli.registry`. On `full` each new guard — a test function, and each refusal case — is proven through its own case, before its commit and on the commit's own tree: stage, `T=$(git write-tree)`, `git worktree add --detach .tmp/plan-00135/probe HEAD`, `git -C .tmp/plan-00135/probe read-tree -u --reset "$T"`, `git -C .tmp/plan-00135/probe commit -q -m "test: probe $T"`, and from that worktree, per row, `infra/scripts/mutate-probe.sh --file <F> --control '<sed>' --mutation '<sed>' -- uv run pytest <node id> -q -p no:cacheprovider --basetemp=.tmp/pt`, expected `KILLED`. The mutation substitutes and never deletes a line (`if <cond>:` becomes `if False:`, a call `None`), its site a pattern whose `grep -c` reads 1 or an address whose range holds one, dry-run first through `sed '<expr>' <F> | uv run python -c 'import ast,sys; ast.parse(sys.stdin.read())'`; a row given in words names the alteration, and the implementer writes its `sed` against the code it wrote. Never through a case `tests/slow-cases.txt` lists: each new case whose own time is 10 s or more (`--durations=0`) joins that list at its sorted place in its task's commit, recorded `probe skipped: slow case` with its node id. The task's commit message carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):` and each probe's command with its verdict line, naming `infra/scripts/mutate-probe.sh`; the probe worktree is removed before the commit — a data link in it unlinked first — and `git rev-parse HEAD^{tree}` after the commit prints `<T>`.
- Commits: one per task that changes the tree (Task 4 adds none; its record lands in Task 5's commit, and `open-pr`'s change-index row takes Task 5 step 9's own), each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: <the executing session's URL>`; an implementer on another model names its own.
- The reads: the trio over Tasks 1–3's range (`pre-review`, `review`, `re-review`, as CLAUDE.md orders them; Task 3 step 7) closes with no open Critical or Important before Task 4 step 2, and nothing the run executes or the record pins changes from that read to the registration unless a read of the change follows (Task 4 step 1); Task 5's commits take their own `pre-review`, then the read of the delta from the tip the last read covered (Task 5 step 9) before the push that carries it; every `re-review` of these reads draws on the branch's two (the `re-review` workflow's cap), and a Critical or Important open with none left goes to the owner; the PR is created and edited through `open-pr`, its read line naming the tip read.

## Review Focus

- A `--window` whose start is off the 4h grid keeps, in the windowed hourly read, the leading hours of a 240 bar the windowed 240 read drops: the run must end in D4's refusal naming the hourly bar, never a traceback or a silent drop. Test: Task 2, `test_a_b1_hourly_exit_window_off_the_4h_grid_is_refused_naming_an_hourly_bar_its_240_read_lacks`.
- A windowed evaluation must read the 60 files under the same bounds as the 240 files (D4), so the state machine warms up from the window's first bar; a subject that passed its window to one grid alone would check hours outside it; the window's end reads the last interval short, as D4 discloses. Test: Task 2, `test_b1_hourly_exit_reads_both_grids_under_the_window`.
- With no exit, arm B's turnover — four slots a return index, flattened in time order from flat — equals arm A's exactly (D3), so a subject flattening the slots in another order moves `turnover_reduction_pct` and `spot_drag_pct_yr` with no knob engaged. Test: Task 2, `test_the_b1_hourly_exit_subject_registers_each_metric_from_its_own_call`, its `turnover_b` and `turnover_reduction_pct` keys on a fixture with exits — a slow case (Task 2 step 7).
- Trial 4's runsheet reused with `--n-trials 4`, or a plain eval of the trial subject — the one look D12 forbids — must be refused before any read. Test: Task 2, `test_b1_hourly_exit_refuses_a_plain_eval_and_another_count_before_any_read`.
- A flat prior window that the hourly close falls below is no longer flat: `channel_position` over the `w` closes with the hourly close in place reads −1, and the exit fires; a breach read off the prior window alone would see it flat and skip the exit. Test: Task 1, `test_new_low_is_the_channels_own_test_at_its_ties_and_its_band`, its `new_low([10.0, 10.0], 9.0, band=1.0)`.

## File structure

- Create `cli/alpha/b1_exit.py` — the breach test, the hourly-exit state machine, the interior closes, the slot directions and positions, the price paths, the split costing and the engagement counts.
- Create `tests/test_alpha_b1_exit.py` — the module's tests, synthetic, every expected value computed by hand.
- Create `tests/test_research_b1_hourly_exit_basis.py` — data-gated: the reads and the interior closes against the measured basis; arm A against records 48 and 49, run after the hash.
- Modify `cli/research/subjects.py` — the two literals, the inputs half, both subjects' metrics, the build, the rule, the two key sets and the two `SUBJECTS` entries.
- Modify `tests/test_research_command.py` — the shared 4h aggregation, the fixture, the subjects' tests, `_RULED_FIXTURES`, `_DECLARED_COUNT`, the families literal, `_CONTRACT_DATASETS`, the metric-keys test; `README.md` — the `--subject` row; `tests/slow-cases.txt` — the new slow cases.
- At the run: `docs/reference/trial-registry.jsonl` (or, on a stop, `docs/reference/reading-ledger.jsonl`), `tests/test_trial_registry_provenance.py` (`LANDED_N_TRIALS`), `docs/research/10.phase4-decisions.md`, `docs/open-topics/T0022-b1-intraday-seasonality-family.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and the engine-design topic D13 registers.

______________________________________________________________________

### Task 1: the module — the breach test, the hourly exit check, slot directions and positions, price paths, the split costing, the engagement counts (D1's identity, D2, D3, D4, D8's helpers)

**Files:**
- Create: `cli/alpha/b1_exit.py`
- Create: `tests/test_alpha_b1_exit.py`

**Interfaces:**
- Consumes: `cli.alpha.a1._map_to_union_index`, `cli.alpha.a1._validate_prices_by_asset`, `cli.alpha.a2.A2Config`, `cli.features.channel_position`, `cli.alpha.errors.AlphaError`; nothing of spec 00133.
- Produces, every name imported by Task 2, the basis test reading `interior_closes_by_asset`:

```python
def new_low(prior: list[float], close: float, *, band: float) -> bool: ...
def donchian_signal_hourly_exit(prices: list[float], interior: list[tuple[float | None, float | None, float | None]], *, window: int,
                                band: float) -> tuple[list[tuple[float, float, float, float]], list[tuple[int, int, bool]]]: ...
def interior_closes_by_asset(fed: dict[str, list[float | None]], h4_prices: dict[str, list[float | None]], union_ts: list[datetime],
                             hourly: dict[str, tuple[list[datetime], list[float]]]
                             ) -> dict[str, list[tuple[float | None, float | None, float | None]]]: ...
def asset_directions_hourly_exit(prices_by_asset: dict[str, list[float | None]], union_ts: list, asset_ts: dict[str, list],
                                 interior_by_asset: dict[str, list[tuple[float | None, float | None, float | None]]], *, config: A2Config
                                 ) -> tuple[dict[str, list[tuple[float, float, float, float] | None]],
                                            dict[str, dict[int, list[tuple[int, int, bool]]]]]: ...
def a2_slot_positions(weights: list[dict[str, float]], slot_directions: dict[str, list[tuple[float, float, float, float] | None]],
                      scalar: list[float]) -> dict[str, list[tuple[float, float, float, float]]]: ...
def price_paths(fed: dict[str, list[float | None]], interior_by_asset: dict[str, list[tuple[float | None, float | None, float | None]]]
                ) -> dict[str, list[tuple[float, float, float, float, float] | None]]: ...
def net_of_cost_hourly(slot_positions: dict[str, list[tuple[float, float, float, float]]],
                       paths: dict[str, list[tuple[float, float, float, float, float] | None]], *, cost_per_side: float) -> list[float]: ...
def intra_turnover(slot_positions: dict[str, list[tuple[float, float, float, float]]]) -> float: ...
def exit_events_per_year(events: dict[str, dict[int, list[tuple[int, int, bool]]]], own_stamps: dict[str, list[datetime]]
                         ) -> dict[str, dict[str, dict[str, list[int]]]]: ...
def hourly_closes_differ_per_year(directions_a: list[dict[str, list[float | None]]],
                                  slot_directions_b: list[dict[str, list[tuple[float, float, float, float] | None]]],
                                  union_ts: list[datetime]) -> dict[str, int]: ...
```

- [ ] **Step 1: Write the failing tests** — `tests/test_alpha_b1_exit.py`, whole; every expected value is computed by hand in the comment above it, never on the trial's data. Task 2's register test builds its expected metrics by calling eight of these functions — `interior_closes_by_asset`, `asset_directions_hourly_exit`, `a2_slot_positions`, `price_paths`, `net_of_cost_hourly`, `intra_turnover`, `exit_events_per_year` and `hourly_closes_differ_per_year` — so it checks the subject's wiring alone, and each of the eight has a case here whose value is worked by hand:

```python
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.alpha.a2 import A2Config, _asset_directions_a2, _donchian_signal, a2_book_returns
from cli.alpha.b1 import book_turnover
from cli.alpha.b1_exit import (
    a2_slot_positions,
    asset_directions_hourly_exit,
    donchian_signal_hourly_exit,
    exit_events_per_year,
    hourly_closes_differ_per_year,
    interior_closes_by_asset,
    intra_turnover,
    net_of_cost_hourly,
    new_low,
    price_paths,
)
from cli.alpha.b2 import net_of_cost
from cli.alpha.errors import AlphaError
from cli.features import channel_position
from cli.portfolio.crossfreq_system import _ffill_btc

_T0 = datetime(2024, 1, 1, tzinfo=UTC)
_H1, _H4 = timedelta(hours=1), timedelta(hours=4)
_SMALL = A2Config(lookbacks=(5, 10, 20), short="off", target_vol=0.12, vol_lookback=12, basket_lookback=8, periods_per_year=2190)
_ADOPTED = tuple(
    A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
)
_NONE3 = (None, None, None)


def _union(n: int) -> dict[str, list[float | None]]:
    prices = {
        asset: [100.0 * 1.001**k * (1 + 0.05 * math.sin(k / 7.0 + i * 0.7)) for k in range(n)]
        for i, asset in enumerate(("BTC", "ETH", "SOL"))
    }
    prices["ETH"][:30] = [None] * 30
    prices["SOL"][50] = None
    return prices


def _index(prices: dict[str, list[float | None]]) -> tuple[list[int], dict[str, list[int]]]:
    n = len(prices["BTC"])
    return list(range(n)), {asset: [k for k, p in enumerate(ps) if p is not None] for asset, ps in prices.items()}


def test_new_low_is_the_channels_own_test_at_its_ties_and_its_band():
    # A close at the window's low reads 2 * 0 / 2 - 1 = -1 and breaches; a flat window reads 0; 10.5 in [10, 12] reads -0.5,
    # past band 0.5 and short of band 1.0; a close below the prior low widens the window down to itself, a flat one too.
    assert new_low([10.0, 12.0, 11.0], 10.0, band=1.0)
    assert not new_low([10.0, 10.0], 10.0, band=1.0)
    assert not new_low([10.0, 12.0], 10.5, band=1.0) and new_low([10.0, 12.0], 10.5, band=0.5)
    assert new_low([10.0, 12.0], 9.0, band=1.0) and new_low([10.0, 10.0], 9.0, band=1.0)


@pytest.mark.parametrize(("window", "band"), [(2, 1.0), (5, 1.0), (20, 1.0), (5, 0.6)])
def test_new_low_agrees_with_the_channel_position_at_every_whole_window(window, band):
    prices = [100.0 * (1 + 0.05 * math.sin(k / 3.0)) * 0.999**k for k in range(200)]
    cp = channel_position(prices, window=window)
    agree = [new_low(prices[m + 1 - window : m], prices[m], band=band) for m in range(window - 1, len(cp))]
    assert agree == [cp[m] <= -band for m in range(window - 1, len(cp))]
    assert any(agree) and not all(agree)


_PRICES = [10.0, 11.0, 12.0, 13.0, 12.5, 14.0, 15.0, 13.0]
_INTERIOR = [
    (1.0, 1.0, 1.0),  # own bar 0's: read by no interval
    (9.0, 9.0, 9.0),  # interval 0 -> 1: the lookback at its initial 0, unchecked
    (9.0, None, None),  # 1 -> 2: still 0
    (12.5, 10.9, 12.8),  # 2 -> 3: level min(11, 12) = 11; 10.9 breaches at offset 2; 13 makes no new low, a false exit
    (None, 12.0, 11.0),  # 3 -> 4: re-entered at 13, level 12; offset 1 missing; 12.0 ties the low; 11.0 no second exit
    (11.0, None, 10.0),  # 4 -> 5: B held at -1 from the exit, unchecked
    (14.5, 14.8, 14.9),  # 5 -> 6: +1 at 14, level 12.5, no breach
    (14.6, 13.9, 13.5),  # 6 -> 7: level 14; 13.9 breaches at offset 2; 13 is a new 3-bar low, an early exit
]


def test_the_exit_check_sets_minus_1_at_the_first_breach_from_plus_1_and_the_4h_rule_continues_from_bs_state():
    # Window 3: arm A's states are 0, 0, then +1 from bar 2 on (bar 4's 12.5 reads 0 in [12, 13] and holds). B holds its exit's
    # -1 through bar 4 and re-enters on bar 5's new high.
    states, exits = donchian_signal_hourly_exit(_PRICES, _INTERIOR, window=3, band=1.0)

    assert _donchian_signal(_PRICES, window=3, band=1.0) == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert states == [
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0),
        (1.0, 1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0, -1.0),
        (-1.0, -1.0, -1.0, -1.0),
        (1.0, 1.0, 1.0, 1.0),
        (1.0, 1.0, -1.0, -1.0),
    ]
    assert exits == [(2, 2, False), (3, 2, False), (6, 2, True)]


@pytest.mark.parametrize("window", [2, 3, 5])
def test_with_no_interior_close_the_states_are_the_4h_rules(window):
    prices = [100.0 * (1 + 0.05 * math.sin(k / 3.0)) * 1.002**k for k in range(80)]
    states, exits = donchian_signal_hourly_exit(prices, [_NONE3] * 80, window=window, band=1.0)
    assert states == [(s, s, s, s) for s in _donchian_signal(prices, window=window, band=1.0)]
    assert exits == []


@pytest.mark.parametrize(("config", "n"), [(_SMALL, 400), *((config, 600) for config in _ADOPTED)])
def test_with_no_interior_close_arm_bs_directions_positions_and_net_are_arm_as(config, n):
    prices = _union(n)
    union_ts, asset_ts = _index(prices)
    interior = {asset: [_NONE3] * len(ts) for asset, ts in asset_ts.items()}
    book = a2_book_returns(prices, config=config)

    directions, events = asset_directions_hourly_exit(prices, union_ts, asset_ts, interior, config=config)
    slots = a2_slot_positions(
        _inverse_vol_weights(prices, lookback=config.basket_lookback), directions, book["vol_target_positions"]
    )

    d_a = _asset_directions_a2(prices, union_ts, asset_ts, config=config)
    assert directions == {asset: [None if d is None else (d, d, d, d) for d in d_a[asset]] for asset in prices}
    assert all(evs == [] for by_lookback in events.values() for evs in by_lookback.values())
    assert slots == {asset: [(p, p, p, p) for p in ps] for asset, ps in book["asset_positions"].items()}
    returns = {asset: _asset_returns(ps) for asset, ps in prices.items()}
    net_b = net_of_cost_hourly(slots, price_paths(prices, interior), cost_per_side=0.006)
    assert net_b == net_of_cost(book["asset_positions"], returns, cost_per_side=0.006)
    assert intra_turnover(slots) == 0.0
    assert book_turnover({asset: [p for s in ps for p in s] for asset, ps in slots.items()}) == book_turnover(
        book["asset_positions"]
    )


def _dips(prices: dict[str, list[float | None]]) -> dict[str, list[tuple[float | None, float | None, float | None]]]:
    # Each own bar's three interior closes off its predecessor's close, the second missing on every seventh bar.
    out = {}
    for asset, ps in prices.items():
        own = [p for p in ps if p is not None]
        out[asset] = [_NONE3] + [
            (own[j - 1] * 0.998, None if j % 7 == 3 else own[j - 1] * 0.985, own[j] * 0.999) for j in range(1, len(own))
        ]
    return out


def test_an_exit_never_lifts_arm_bs_state_or_direction_above_arm_as_and_both_kinds_of_exit_occur():
    prices = _union(400)
    union_ts, asset_ts = _index(prices)
    interior = _dips(prices)

    d_b, events = asset_directions_hourly_exit(prices, union_ts, asset_ts, interior, config=_SMALL)

    for asset, ps in prices.items():
        own = [p for p in ps if p is not None]
        for w in _SMALL.lookbacks:
            states, _ = donchian_signal_hourly_exit(own, interior[asset], window=w, band=1.0)
            assert all(max(slots) <= a for slots, a in zip(states, _donchian_signal(own, window=w, band=1.0), strict=True))

    d_a = _asset_directions_a2(prices, union_ts, asset_ts, config=_SMALL)
    pairs = [(d_b[asset][k], d_a[asset][k]) for asset in prices for k in range(len(union_ts) - 1)]
    assert all((b is None) == (a is None) for b, a in pairs)
    assert all(max(b) <= a for b, a in pairs if b is not None) and any(min(b) < a for b, a in pairs if b is not None)
    assert {asset: sorted(by_lookback) for asset, by_lookback in events.items()} == {asset: [5, 10, 20] for asset in prices}
    assert {early for by_lookback in events.values() for evs in by_lookback.values() for _, _, early in evs} == {True, False}


def test_the_directions_map_each_slots_mean_over_the_lookbacks_onto_the_union_clipped_at_0():
    # Window 2's level is the previous close: its exits are (1, 1) false, (2, 2) false, (3, 2) early on 12.5 < 13 and (6, 1)
    # early. Return index 1 reads mean(1, 0) = 0.5 then mean(-1, 0) = -0.5, clipped to 0; index 4 holds both lookbacks at -1.
    prices = {"BTC": list(_PRICES)}
    union_ts, asset_ts = _index(prices)
    config = A2Config(lookbacks=(2, 3), short="off", target_vol=0.1)

    directions, events = asset_directions_hourly_exit(prices, union_ts, asset_ts, {"BTC": _INTERIOR}, config=config)

    assert directions == {
        "BTC": [
            (0.0, 0.0, 0.0, 0.0),
            (0.5, 0.0, 0.0, 0.0),
            (1.0, 1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0, 1.0),
            (1.0, 0.0, 0.0, 0.0),
        ]
    }
    assert events == {
        "BTC": {2: [(1, 1, False), (2, 2, False), (3, 2, True), (6, 1, True)], 3: [(2, 2, False), (3, 2, False), (6, 2, True)]}
    }


def test_an_interval_no_return_index_maps_still_runs_the_check_and_its_state_carries():
    # ETH misses union stamp 4, so its own interval 3 -> 4 spans union 3 -> 5 and maps to no return index; its false exit
    # there still holds the lookback at -1 into return index 5, where arm A is long.
    prices = {"BTC": [100.0] * 9, "ETH": [*_PRICES[:4], None, *_PRICES[4:]]}
    union_ts, asset_ts = _index(prices)
    interior = {"BTC": [_NONE3] * 9, "ETH": _INTERIOR}
    config = A2Config(lookbacks=(3,), short="off", target_vol=0.1)

    directions, _ = asset_directions_hourly_exit(prices, union_ts, asset_ts, interior, config=config)

    assert directions["ETH"][3:6] == [None, None, (0.0, 0.0, 0.0, 0.0)]
    assert _asset_directions_a2(prices, union_ts, asset_ts, config=config)["ETH"][3:6] == [None, None, 1.0]


def test_a2_slot_positions_scale_each_slots_own_direction_by_the_weight_and_scalar_at_its_index():
    # Index 0: BTC 0.5 * (1, 1, 0.5, 0) * 2 = (1, 1, 0.5, 0), ETH unweighted; index 1: BTC's None direction reads 0, ETH
    # 0.5 * (0, 1, 1, 1) * 4 = (0, 2, 2, 2). A slot read off another slot's direction moves BTC at 0 and ETH at 1.
    weights = [{"BTC": 0.5}, {"BTC": 0.25, "ETH": 0.5}]
    directions = {"BTC": [(1.0, 1.0, 0.5, 0.0), None], "ETH": [(1.0, 0.5, 0.5, 0.0), (0.0, 1.0, 1.0, 1.0)]}
    assert a2_slot_positions(weights, directions, [2.0, 4.0]) == {
        "BTC": [(1.0, 1.0, 0.5, 0.0), (0.0, 0.0, 0.0, 0.0)],
        "ETH": [(0.0, 0.0, 0.0, 0.0), (0.0, 2.0, 2.0, 2.0)],
    }


def test_net_of_cost_hourly_splits_each_interval_at_its_interior_closes_in_units_of_the_boundary_close():
    # BTC at 0: (0.5 * 4 - 0.5 * 8 + 0.25 * 2 + 0.25 * 4) / 64 = -0.0078125, traded 0.5 + 0.25; at 1 the equal slots earn
    # 0.25 * (99 / 66 - 1) = 0.125, whatever the path between; at 2 no path, its sale of 0.25 still charged. ETH at 1:
    # (0.5 * -4 + 0.25 * 8) / 32 = 0, traded 0.5 + 0.25; at 2: 0.5 * (55 / 44 - 1) = 0.125, traded 0.25. Cost 0.0625 a side.
    slots = {
        "BTC": [(0.5, 0.5, 0.25, 0.25), (0.25, 0.25, 0.25, 0.25), (0.0, 0.0, 0.0, 0.0)],
        "ETH": [(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.5, 0.25), (0.5, 0.5, 0.5, 0.5)],
    }
    paths = {
        "BTC": [(64.0, 68.0, 60.0, 62.0, 66.0), (66.0, 66.0, 70.0, 64.0, 99.0), None],
        "ETH": [(32.0, 32.0, 32.0, 32.0, 32.0), (32.0, 36.0, 40.0, 36.0, 44.0), (44.0, 44.0, 44.0, 44.0, 55.0)],
    }
    assert net_of_cost_hourly(slots, paths, cost_per_side=0.0625) == [-0.0546875, 0.078125, 0.09375]
    # The trades at interior closes alone: BTC's 0.25 at offset 2 of index 0, ETH's 0.5 and 0.25 at offsets 2 and 3 of index 1.
    assert intra_turnover(slots) == 1.0


def test_a_price_path_carries_the_previous_close_over_a_missing_hour_and_reads_the_bar_that_ends_its_interval():
    fed = {"BTC": [64.0, 66.0, 70.0, 72.0], "ETH": [None, 50.0, 52.0, 51.0], "SOL": [10.0, None, 11.0, 12.0]}
    interior = {
        "BTC": [(1.0, 1.0, 1.0), (65.0, None, 67.0), _NONE3, (71.0, 73.0, 72.5)],
        "ETH": [(9.0, 9.0, 9.0), (50.5, None, 51.5), _NONE3],
        "SOL": [(9.0, 9.0, 9.0), (10.5, 10.6, 10.7), (11.5, None, None)],
    }
    assert price_paths(fed, interior) == {
        "BTC": [(64.0, 65.0, 65.0, 67.0, 66.0), (66.0, 66.0, 66.0, 66.0, 70.0), (70.0, 71.0, 73.0, 72.5, 72.0)],
        "ETH": [None, (50.0, 50.5, 50.5, 51.5, 52.0), (52.0, 52.0, 52.0, 52.0, 51.0)],
        "SOL": [None, None, (11.0, 11.5, 11.5, 11.5, 12.0)],
    }


_UNION = [_T0 + k * _H4 for k in range(4)]
_H4_CLOSES = {"BTC": [64.0, None, 66.0, 67.0], "ETH": [None, 50.0, 52.0, 51.0]}


def _hourly(**over: tuple[list[datetime], list]) -> dict[str, tuple[list[datetime], list]]:
    btc = [0, 1, 2, 3, 8, 10, 11, 12, 13, 14, 15]
    eth = [5, 6, 7, 8, 9, 10, 11, 12]
    return {
        "BTC": ([_T0 + h * _H1 for h in btc], [63.0, 63.5, 63.8, 64.0, 65.0, 65.5, 66.0, 66.5, 66.7, 66.9, 67.0]),
        "ETH": ([_T0 + h * _H1 for h in eth], [49.5, 49.8, 50.0, 50.5, 51.0, 51.5, 52.0, 51.8]),
    } | over


def test_interior_closes_are_the_first_three_hourly_closes_of_each_own_bar():
    # BTC's bar 1 is a fill, with no hourly bar; its bar 2 misses 09:00, its 11:00 close is the fourth, never read. ETH's own
    # bars start at union 1, whose 04:00 hour is missing.
    assert interior_closes_by_asset(_ffill_btc(_H4_CLOSES), _H4_CLOSES, _UNION, _hourly()) == {
        "BTC": [(63.0, 63.5, 63.8), _NONE3, (65.0, None, 65.5), (66.5, 66.7, 66.9)],
        "ETH": [(None, 49.5, 49.8), (50.5, 51.0, 51.5), (51.8, None, None)],
    }


def _eth(hours: list[float], closes: list) -> dict[str, tuple[list[datetime], list]]:
    return {"ETH": ([_T0 + timedelta(hours=h) for h in hours], closes)}


_ETH_HOURS, _ETH_CLOSES = [5, 6, 7, 8, 9, 10, 11, 12], [49.5, 49.8, 50.0, 50.5, 51.0, 51.5, 52.0, 51.8]


@pytest.mark.parametrize(
    ("hourly", "h4", "match"),
    [
        *(
            pytest.param(
                _eth(_ETH_HOURS, [49.5, bad, *_ETH_CLOSES[2:]]),
                _H4_CLOSES,
                rf"ETH: hourly close must be a finite number above 0, got {re_bad} at 2024-01-01T06:00:00\+00:00",
                id=name,
            )
            for name, bad, re_bad in (
                ("zero-close", 0.0, "0.0"),
                ("negative-close", -1.0, "-1.0"),
                ("nan-close", math.nan, "nan"),
                ("inf-close", math.inf, "inf"),
                ("none-close", None, "None"),
                ("bool-close", True, "True"),
            )
        ),
        pytest.param(
            _eth([5, 6, 6, 8, 9, 10, 11, 12], _ETH_CLOSES),
            _H4_CLOSES,
            r"ETH: hourly stamps must be strictly increasing, violated at 2024-01-01T06:00:00\+00:00",
            id="repeated-stamp",
        ),
        pytest.param(
            {"ETH": ([_T0.replace(tzinfo=None) + timedelta(hours=5), *_hourly()["ETH"][0][1:]], _ETH_CLOSES)},
            _H4_CLOSES,
            "ETH: hourly stamps must be tz-aware",
            id="naive-stamp",
        ),
        pytest.param(
            _eth([5, 6.5, 7, 8, 9, 10, 11, 12], _ETH_CLOSES),
            _H4_CLOSES,
            r"ETH: hourly stamp off the hour at 2024-01-01T06:30:00\+00:00",
            id="off-the-hour",
        ),
        pytest.param(
            _eth(_ETH_HOURS, _ETH_CLOSES[:-1]), _H4_CLOSES, "ETH: hourly stamps and closes differ in length: 8 and 7", id="unequal"
        ),
        pytest.param(
            _eth([1, *_ETH_HOURS], [49.0, *_ETH_CLOSES]),
            _H4_CLOSES,
            r"ETH: an hourly bar at 2024-01-01T01:00:00\+00:00 lies in a 4h bar the 240 series lacks",
            id="a-bar-the-240-lacks",
        ),
        pytest.param(
            {"BTC": ([_T0 + h * _H1 for h in (0, 5)], [63.0, 64.0])},
            _H4_CLOSES,
            r"BTC: an hourly bar at 2024-01-01T05:00:00\+00:00 lies in a 4h bar the 240 series lacks",
            id="a-bar-in-a-fills-span",
        ),
        pytest.param(
            {},
            {**_H4_CLOSES, "ETH": [None, 50.0, 0.0, 51.0]},
            "prices must be None or finite positive numbers",
            id="a-zero-4h-close",
        ),
        pytest.param({"ETH": None}, _H4_CLOSES, "hourly's assets", id="an-asset-without-hourly-bars"),
    ],
)
def test_interior_closes_refuse_an_hourly_series_the_check_cannot_read(hourly, h4, match):
    series = {k: v for k, v in (_hourly() | hourly).items() if v is not None}
    with pytest.raises(AlphaError, match=match):
        interior_closes_by_asset(_ffill_btc(h4), h4, _UNION, series)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(
            lambda: asset_directions_hourly_exit(
                {"BTC": list(_PRICES)},
                list(range(8)),
                {"BTC": list(range(8))},
                {"BTC": _INTERIOR[:-1]},
                config=A2Config(lookbacks=(3,), short="off", target_vol=0.1),
            ),
            "BTC: interior holds 7 triples for 8 prices",
            id="interior-short",
        ),
        pytest.param(
            lambda: asset_directions_hourly_exit(
                {"BTC": list(_PRICES)},
                list(range(8)),
                {"BTC": list(range(8))},
                {"BTC": _INTERIOR},
                config=A2Config(lookbacks=(3,), short="on", target_vol=0.1),
            ),
            "short='off'",
            id="short-on",
        ),
        pytest.param(
            lambda: asset_directions_hourly_exit(
                {"BTC": list(_PRICES)},
                list(range(8)),
                {"BTC": list(range(8))},
                {"ETH": _INTERIOR},
                config=A2Config(lookbacks=(3,), short="off", target_vol=0.1),
            ),
            "interior's assets",
            id="interior-off-the-assets",
        ),
        pytest.param(
            lambda: a2_slot_positions([{}] * 2, {"BTC": [(1.0,) * 4] * 3}, [1.0] * 3), "differ in length", id="weights-short"
        ),
        pytest.param(
            lambda: a2_slot_positions([{}] * 3, {"BTC": [(1.0,) * 4] * 2}, [1.0] * 3), "differ in length", id="a-direction-short"
        ),
    ],
)
def test_the_state_machine_directions_and_positions_refuse_inputs_off_their_shape(call, match):
    with pytest.raises(AlphaError, match=match):
        call()


def test_exit_events_are_counted_per_bar_start_year_early_and_false_every_year_with_a_state_kept():
    # ETH's bar at 2015-12-31 20:00 closes in 2016 and is keyed 2015; its last bar, alone in 2018, has no state.
    eth = [datetime(2015, 12, 31, 16, tzinfo=UTC), datetime(2015, 12, 31, 20, tzinfo=UTC), datetime(2016, 1, 1, tzinfo=UTC)]
    eth += [datetime(2017, 6, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)]
    events = {"ETH": {2: [(1, 2, True), (2, 1, False)], 3: []}}
    assert exit_events_per_year(events, {"ETH": eth}) == {
        "ETH": {
            "2": {"2015": [1, 1, 0], "2016": [1, 0, 1], "2017": [0, 0, 0]},
            "3": {"2015": [0, 0, 0], "2016": [0, 0, 0], "2017": [0, 0, 0]},
        }
    }


def test_hourly_closes_differ_per_bar_start_year_counting_each_close_once():
    union_ts = [
        datetime(2014, 12, 31, 20, tzinfo=UTC),
        datetime(2015, 12, 31, 16, tzinfo=UTC),
        datetime(2015, 12, 31, 20, tzinfo=UTC),
    ]
    union_ts += [datetime(2016, 1, 1, tzinfo=UTC), datetime(2016, 1, 1, 4, tzinfo=UTC), datetime(2016, 1, 1, 8, tzinfo=UTC)]
    directions_a = [{"BTC": [0.5, 0.0, 1.0, None, 0.5]}, {"BTC": [1.0, 1.0, 1.0, None, 1.0]}]
    directions_b = [
        {"BTC": [(0.5, 0.5, 0.5, 0.5), (0.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0), None, (0.0, 0.0, 0.0, 0.0)]},
        {"BTC": [(1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0), (1.0, 0.0, 1.0, 1.0), None, (1.0, 1.0, 1.0, 1.0)]},
    ]
    # Index 2, keyed 2015, differs at offsets 1 and 2, offset 1 on both arms, counted once; index 3's None equals None.
    assert hourly_closes_differ_per_year(directions_a, directions_b, union_ts) == {"2014": 0, "2015": 2, "2016": 4}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00135 && uv run pytest tests/test_alpha_b1_exit.py -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt`
Expected: collection error, `ModuleNotFoundError: No module named 'cli.alpha.b1_exit'` — the fence, run against the tree at this plan's commit, fails so.

- [ ] **Step 3: Implement `cli/alpha/b1_exit.py`** — a module docstring naming `docs/specs/00135-b1-hourly-channel-exits-design.md` and stating the slot convention in a sentence (slot 0 runs from the boundary close to the interval's first interior close, slot `i` from the interior close at offset `i`); and:
  - `new_low`: spec D2's code block verbatim.
  - `donchian_signal_hourly_exit`: spec D2's code block verbatim, its comment included.
  - `interior_closes_by_asset`: `_validate_prices_by_asset(fed)` first, on its own line, so a bad close is refused before any later division; `set(hourly) != set(fed)` refused, `f"hourly's assets {sorted(hourly)} are not the prices' {sorted(fed)}"`; per asset `f"{a}: hourly stamps and closes differ in length: {len(stamps)} and {len(closes)}"`; per hourly row, in this order, each on its own `if` line: `f"{a}: hourly stamps must be tz-aware, got {h!r} at index {i}"`, `f"{a}: hourly stamps must be strictly increasing, violated at {h.isoformat()}"`, `f"{a}: hourly stamp off the hour at {h.isoformat()}"`, `f"{a}: hourly close must be a finite number above 0, got {c!r} at {h.isoformat()}"` (a bool refused), and `f"{a}: an hourly bar at {h.isoformat()} lies in a 4h bar the 240 series lacks"`. An hourly bar's 4h bar opens at its stamp floored to 4h on the epoch grid, `datetime.fromtimestamp(int(h.timestamp()) // 14_400 * 14_400, UTC)`, the floor trial 3's basis test reads; it lies in the asset's series when `h4_prices[a]` holds a close at that union stamp; the bars opening 0, 1 and 2 hours into it fill slots 0–2 of that own bar's triple, the one 3 hours in, the 4h close itself, none. One triple per own bar of `fed[a]`, `None` where the hour is missing. **Author's call**: the 240 series a bar must lie in is the raw `h4_prices[a]`, so an hourly bar in the span of a BTC fill — a 4h bar the 240 file lacks — is refused as the files' disagreement D4 names, never read as the fill's interior; it cannot fire on the frozen set (measured, 0 at each of the six fills).
  - `asset_directions_hourly_exit`: refuses a config whose `short` is not `"off"` (`f"the hourly-exit directions need short='off', got {config.short!r}"`) and `set(interior_by_asset) != set(prices_by_asset)` (`f"interior's assets {sorted(interior_by_asset)} are not the prices' {sorted(prices_by_asset)}"`); then `cli.alpha.a2._asset_directions_a2`'s body, each asset's `own_prices` followed by `if len(interior_by_asset[asset]) != len(own_prices):` on its own line, refused as `f"{asset}: interior holds {len(interior_by_asset[asset])} triples for {len(own_prices)} prices"` — D4's `interior` length refusal, here because this loop knows the asset and D2's block is copied verbatim — and `donchian_signal_hourly_exit(own_prices, interior_by_asset[asset], window=w, band=config.band)` in place of `_donchian_signal(...)`, its four-slot states mapped by `_map_to_union_index`, its events kept under `events[asset][w]`; per return index `None` wherever any lookback's mapping is `None`, else `tuple(max(statistics.mean(v[i] for v in values), 0.0) for i in range(4))` — the clip as `a2` writes it, per slot.
  - `a2_slot_positions`: refuses, on one `if`, `len(weights) != len(scalar)` or any direction list of another length (`"weights, slot directions and scalar differ in length"`); returns `{asset: [tuple(weights[k].get(asset, 0.0) * (0.0 if d[k] is None else d[k][i]) * scalar[k] for i in range(4)) for k in range(len(scalar))] for asset, d in slot_directions.items()}` — `a2_book_returns`' asset-positions expression per slot, so the identity holds bit for bit.
  - `price_paths`: per asset and return index `k`, `None` where `fed[a][k]` or `fed[a][k + 1]` is `None`, else `(P0, P1, P2, P3, P4)` per D3 — the interior closes those of the own bar at union index `k + 1`, the own index being the count of the asset's present prices at union indices `0..k`.
  - `net_of_cost_hourly`: spec D3's code block verbatim.
  - `intra_turnover`: `Σ_a Σ_k Σ_{i=1..3} |p_i − p_{i−1}|` over the slot tuples.
  - `exit_events_per_year`: per asset, the years `{own_stamps[asset][j].year for j in range(len(own_stamps[asset]) - 1)}` — the bars with a state — each `[0, 0, 0]`; each event `(j, offset, early)` adds 1 to `[0]` and to `[1]` when early, `[2]` when false, of `str(own_stamps[asset][j].year)`; keys `str(w)` and `str(year)`.
  - `hourly_closes_differ_per_year`: `{str(t.year): 0 for t in union_ts[:-1]}`, then for each return index `k` and offset `i` in 0–3, 1 added to `str(union_ts[k].year)` when, for any arm and asset, `(db[a][k] is None) != (da[a][k] is None) or (db[a][k] is not None and db[a][k][i] != da[a][k])`, so a `None` on both sides is equal and never subscripted — as every slot read of a value that may be `None` is guarded in this step: `a2_slot_positions` reads `0.0` for a `None` direction, `price_paths` returns `None` before it indexes a missing price, and `net_of_cost_hourly` skips a `None` path.
  - **Author's call**: the asset-set refusals of `interior_closes_by_asset` and `asset_directions_hourly_exit` and `a2_slot_positions`' length refusal guard no input the subjects build, since each function's one caller ties them; they stay because an extra asset or a longer list would otherwise be read short without a word.

- [ ] **Step 4: Run the tests to verify they pass** — Step 2's command with `--durations=0`; expected `41 passed` (the file ran in 1.4 s against a transcription of Step 3; a case at 10 s or more would join `tests/slow-cases.txt`).

- [ ] **Step 5: Stage, consumers, gate** — `git add tests/test_alpha_b1_exit.py cli/alpha/b1_exit.py`; `bash infra/scripts/consumers.sh --direct cli/alpha/b1_exit.py tests/test_alpha_b1_exit.py` lists the new test file alone, which Step 4 ran; `uv run pre-commit run -a` until clean, its rewrites staged, then Step 4 again over the staged tree.

- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree (Global Constraints' probe line); `--file cli/alpha/b1_exit.py`, control `s/^def new_low(/def new_low_gone(/` (the test module imports it, so every case fails); each mutation a row names is one probe, expected `KILLED`; a row naming several cases is one probe per case.

| node id under `tests/test_alpha_b1_exit.py::` | mutation |
| -- | -- |
| `test_new_low_is_the_channels_own_test_at_its_ties_and_its_band` | `- 1 <= -band` made `- 1 < -band`; `lo, hi = min(min(prior), close), max(max(prior), close)` made `lo, hi = min(prior), max(prior)`; `return hi > lo and ` made `return ` |
| `test_new_low_agrees_with_the_channel_position_at_every_whole_window[5-0.6]` | `- 1 <= -band` made `- 1 <= -1.0` |
| `test_the_exit_check_sets_minus_1_at_the_first_breach_from_plus_1_and_the_4h_rule_continues_from_bs_state` | `if held == 1.0 and h is not None:` made `if held != 0.0 and h is not None:`; the exit's own `held = -1.0`, the one inside the offset loop (`s/^\( \{20\}\)held = -1.0/\1held = 0.0/`), made `held = 0.0`; `exits.append((j, offset, new_low(prior, prices[j + 1], band=band)))` made `exits.append((j, offset, not new_low(prior, prices[j + 1], band=band)))`; `prior = prices[j + 2 - window : j + 1]` made `prior = prices[j + 1 - window : j + 1]`; `enumerate(interior[j + 1], start=1)` made `enumerate(interior[j], start=1)` |
| `test_with_no_interior_close_the_states_are_the_4h_rules[3]` | `if cp[j] >= band:` made `if cp[j] > band:` |
| `test_with_no_interior_close_arm_bs_directions_positions_and_net_are_arm_as[<each>]` | `if ps[0] == ps[1] == ps[2] == ps[3]:` made `if False:` (the legs' sum differs from `p0 * (P4 / P0 - 1)` in the last bits at most indices) |
| `test_an_exit_never_lifts_arm_bs_state_or_direction_above_arm_as_and_both_kinds_of_exit_occur` | the exit event's `new_low(prior, prices[j + 1], band=band)` made `False` |
| `test_the_directions_map_each_slots_mean_over_the_lookbacks_onto_the_union_clipped_at_0` | the per-slot clip `max(<the slot's mean>, 0.0)` made `<the slot's mean>` |
| `test_an_interval_no_return_index_maps_still_runs_the_check_and_its_state_carries` | `if held == 1.0 and h is not None:` made `if False:` |
| `test_a2_slot_positions_scale_each_slots_own_direction_by_the_weight_and_scalar_at_its_index` | within `/^def a2_slot_positions(/,/^def /`, `d[k][i]` made `d[k][0]`, and made `d[k][3]` |
| `test_net_of_cost_hourly_splits_each_interval_at_its_interior_closes_in_units_of_the_boundary_close` | `(path[s + 1] - path[s]) / path[0]` made `(path[s + 1] - path[s]) / path[s]`; `for p in ps:` made `for p in ps[:1]:`; in `intra_turnover`, the offsets `1..3` read as `1..2` |
| `test_a_price_path_carries_the_previous_close_over_a_missing_hour_and_reads_the_bar_that_ends_its_interval` | a missing hour carried as `P0` in place of the previous close; the interior closes read off the own bar at union index `k` in place of `k + 1` |
| `test_interior_closes_are_the_first_three_hourly_closes_of_each_own_bar` | the hourly bar opening 0 hours into its 4h bar stored as `None` |
| `test_interior_closes_refuse_an_hourly_series_the_check_cannot_read[<row>]` | each refusal's `if` made `if False:` against each row it refuses: the close (`zero-close`, `negative-close`, `nan-close`, `inf-close`, `none-close`, `bool-close`), the order (`repeated-stamp`), tz (`naive-stamp`), the hour (`off-the-hour`), the length (`unequal`), the 4h bar (`a-bar-the-240-lacks`, `a-bar-in-a-fills-span`), the asset set (`an-asset-without-hourly-bars`); `_validate_prices_by_asset(fed)` made `None` (`a-zero-4h-close`) |
| `test_the_state_machine_directions_and_positions_refuse_inputs_off_their_shape[<row>]` | each refusal's `if` made `if False:` against its rows: `interior-short`, `short-on`, `interior-off-the-assets`, and the positions' one `if` against `weights-short` and `a-direction-short` |
| `test_exit_events_are_counted_per_bar_start_year_early_and_false_every_year_with_a_state_kept` | the event's year read off the bar after it, `own_stamps[asset][j]` made `own_stamps[asset][j + 1]` on the line that keys the count |
| `test_hourly_closes_differ_per_bar_start_year_counting_each_close_once` | `union_ts[k].year` made `union_ts[k + 1].year` on the line that adds the count |

- [ ] **Step 7: Commit**

```bash
git commit -F - <<'EOF'
feat(alpha): the hourly exit check on the A2 ensemble's own channel, arm B's slot positions and the split costing for B1 trial 5

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 2: the subjects `b1-hourly-channel-exits` and `b1-hourly-channel-exits-preflight` (D1, D5–D8, D10, D11)

**Files:**
- Modify: `cli/research/subjects.py` — after trial 4's `SUBJECTS`-feeding names and before `SUBJECTS`; two entries at the end of `SUBJECTS`
- Modify: `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`

**Interfaces:**
- Consumes: Task 1's `a2_slot_positions`, `asset_directions_hourly_exit`, `exit_events_per_year`, `hourly_closes_differ_per_year`, `interior_closes_by_asset`, `intra_turnover`, `net_of_cost_hourly` and `price_paths`, imported into `subjects` by name (so a test's `monkeypatch.setattr(subjects, …)` reaches them); trial 3's `_B1HourlyRVReads` and `_b1_hourly_rv_reads`; trial 4's `_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES`; spec 00133 as `aa50f1ad5` holds it: `Subject.family: str | None = None` and `Subject.n_trials: int | None = None`; `cli/research/command.py`'s `eval_subject`, which refuses a plain eval of a subject with a rule before any read, `--register` of a subject without one, and an `--n-trials` other than `Subject.n_trials`, counts `attempts.Count.required_n(family)` and the bucket against `budget.BUCKET_OF` and `budget.BUDGET` before the fit, writes the trial-attempts log's `begin` line before the fit and its `end` line before the print, and keeps a rule's `None` as a reading carrying its attempt; in the tests, `tests/conftest.py`'s autouse `_attempts_log_in_tmp_path(tmp_path)`, the module's autouse `_attempts_log(tmp_path, monkeypatch, _attempts_log_in_tmp_path) -> Path`, `_as_trial(name, tmp_path)`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `test_the_ruled_subjects_declare_their_families_and_trial_counts` and `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count`; and the module's `_B1_START`, `_B1_BARS`, `_B2_ASSETS`, `_anchor`, `_recording`, `_rolling_set`, `_kept`, `_block_and_metrics`, `_trials`, `_arm_a_flat`, `_B1_HOURLY_RV_BTC_GAPS`, `_B1_HOURLY_RV_ARMS`, `_B1_HOURLY_RV_CELLS`, `_B1_HOURLY_RV_ANCHORS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_b1_hourly_rv_bar_sentinels`.
- Produces:

```python
# cli/research/subjects.py
_B1_EXIT_RECORDED_PER_PERIOD_SHARPES = (*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, 0.03028127927651177)
_B1_EXIT_N_TRIALS = 5

class _B1HourlyExitInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    fed: dict[str, list[float | None]]
    returns: dict[str, list[float | None]]
    weights_a: list[dict[str, float]]
    vt_a: list[list[float]]                                                      # per arm of _B1_A2_ARMS
    directions_a: list[dict[str, list[float | None]]]                            # per arm
    interior: dict[str, list[tuple[float | None, float | None, float | None]]]
    directions_b: list[dict[str, list[tuple[float, float, float, float] | None]]]  # per arm
    events: list[dict[str, dict[int, list[tuple[int, int, bool]]]]]              # per arm
    own_stamps: dict[str, list[datetime]]
    paths: dict[str, list[tuple[float, float, float, float, float] | None]]
    arm_a: dict[str, list[float]]

def _b1_hourly_exit_inputs(reads: _B1HourlyRVReads) -> _B1HourlyExitInputs: ...
def _b1_hourly_exit_arm_a(inputs: _B1HourlyExitInputs) -> tuple[dict, float, list[float], list[float]]: ...  # bar, arm_a_var_trials, net_a, bench
def _b1_hourly_exit_engagement(inputs: _B1HourlyExitInputs) -> dict: ...  # D8's seven keys
def _b1_hourly_exit_metrics(inputs: _B1HourlyExitInputs) -> dict: ...  # 46 keys
def _b1_hourly_exit_preflight_metrics(inputs: _B1HourlyExitInputs) -> dict: ...  # 25 keys
def _b1_hourly_exit_build(subject: str, compute: Callable[[_B1HourlyExitInputs], dict], reader, dataset, window, as_of, accept_holes) -> dict: ...
def _build_b1_hourly_exit(reader, dataset, window, as_of=None, accept_holes=False) -> dict: ...
def _build_b1_hourly_exit_preflight(reader, dataset, window, as_of=None, accept_holes=False) -> dict: ...
def _b1_hourly_exit_verdict(m: dict) -> str | None: ...
_B1_EXIT_METRIC_KEYS: frozenset[str]
_B1_EXIT_PREFLIGHT_KEYS: frozenset[str]
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - the imports take Task 1's eight functions, `from cli.alpha.b1_exit import (a2_slot_positions, asset_directions_hourly_exit, exit_events_per_year, hourly_closes_differ_per_year, interior_closes_by_asset, intra_turnover, net_of_cost_hourly, price_paths)` before the `cli.alpha.b1_rv` import, and `from cli.validation.dsr import expected_max_sharpe` after the `cli.validation` import;
  - `_b1_hourly_rv_dataset`'s 4h aggregation, from `buckets: dict[int, list[list]] = {}` to the end of its `h4 = [...]`, moves verbatim into `_h4_bars(hourly)` after it, and its 240 write becomes `write_parquet(to_frame(_h4_bars(hourly)), …)`. **Author's call**: the two fixtures share one aggregation, so each 4h close is its bucket's last present hourly close by one code path; trial 3's fixture writes the same bytes;
  - the fixture, after `_b1_volume_args` and before `_RULED_FIXTURES`, which reads its name — a slow cycle, so the 4h series makes new channel lows as well as highs (measured on a transcription of Task 1, closes alone: 486 exit events over the three arms, 23 early and 463 false, and 5,711 hourly closes whose directions differ, 1,098 of them in 2016);
  - `_RULED_FIXTURES` gains `"b1-hourly-channel-exits": _b1_hourly_exit_dataset`, `_DECLARED_COUNT` gains `"b1-hourly-channel-exits": "_B1_EXIT_N_TRIALS"`, and the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b1-hourly-channel-exits": ("B1", 5)`; `_CONTRACT_DATASETS` gains both subjects, each `lambda tmp_path, subject: (_b1_hourly_exit_dataset(tmp_path), _B1_START)`; `test_each_subject_declares_the_metric_keys_its_build_returns` gains `assert subjects.SUBJECTS["b1-hourly-channel-exits"].metric_keys == _B1_EXIT_METRIC_KEYS` and the pre-flight's line over `_B1_EXIT_PREFLIGHT_KEYS`.

```python
def _h4_bars(hourly: list[list]) -> list[list]:
    """Each 4h bucket's bar from its present hourly rows: the first open, their high and low, the last close."""
    buckets: dict[int, list[list]] = {}
    for row in hourly:
        buckets.setdefault(row[0] // 14_400 * 14_400, []).append(row)
    return [
        [
            ts,
            rows[0][1],
            f"{max(float(r[2]) for r in rows)}",
            f"{min(float(r[3]) for r in rows)}",
            rows[-1][4],
            rows[-1][5],
            f"{sum(float(r[6]) for r in rows)}",
            sum(r[7] for r in rows),
        ]
        for ts, rows in buckets.items()
    ]


def _b1_hourly_exit_dataset(tmp_path: Path, *, start: datetime = _B1_START, bars: int = _B1_BARS) -> Path:
    """Hourly closes on a slow cycle, so the 4h series makes new channel lows as well as highs, each 4h bucket's second
    hourly close dipped by a size of its asset's own, so an hourly close breaches a channel its 4h close then holds or
    breaks; the 4h series aggregated from the present hourly rows. BTC misses the two 4h buckets of
    `_B1_HOURLY_RV_BTC_GAPS`, which `_ffill_btc` fills, and every other asset single hours."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        hourly = []
        for k in range(bars * 4):
            if (k // 4 in _B1_HOURLY_RV_BTC_GAPS) if asset == "BTC" else (k % (89 + 2 * i) == 5):
                continue
            close = 100.0 * (1 + 0.25 * math.sin(k / 400.0 + i)) * (1 + 0.03 * math.sin(k / 9.0 + 0.7 * i))
            close *= 1 - 0.004 * (i + 1) if k % 4 == 1 else 1.0
            ts = int(start.timestamp()) + k * 3600
            hourly.append([ts, f"{close}", f"{close * 1.01}", f"{close * 0.99}", f"{close}", f"{close}", "10", 3])
        write_parquet(to_frame(hourly), root / "ohlc-test" / f"{asset}/EUR/60.parquet")
        write_parquet(to_frame(_h4_bars(hourly)), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    return root
```

  Then, after `test_b1_volume_reads_its_volumes_under_the_unions_window` and before `_declared_series`:

```python
_B1_EXIT_SPEC = "docs/specs/00135-b1-hourly-channel-exits-design.md"
_B1_EXIT_NO_VERDICT = (
    "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every hourly close; no verdict, the "
    "trial unspent"
)
_B1_EXIT_ENGAGEMENT = frozenset(
    {"exit_events", "exit_events_early", "exit_events_false", "share_false", "exit_events_per_year",
     "hourly_closes_directions_differ", "hourly_closes_directions_differ_per_year"}
)
# Typed from the spec's key list, never read off the subject.
_B1_EXIT_METRIC_KEYS = _B1_EXIT_ENGAGEMENT | {
    "ann_sharpe_noc", "ann_sharpe_noc_decisive", "per_period_sharpe_4h", "arm_a_ann_sharpe_noc", "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc", "benchmark_ann_sharpe_noc_decisive", "var_trials", "dsr_corrected", "dsr_pass", "spa_pass",
    "spa_p_full", "cost_stress_pass", "worst_slice_relative_pass", "passes", "decisive_start", "n_resamples", "arm_a_var_trials",
    "arm_a_passes", "spa_p_decisive_b30_s42", "spa_p_decisive_b30_s7", "spa_p_decisive_b30_s1234", "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7", "spa_p_decisive_b102_s1234", "head_to_head_mean_outperf_full", "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_2016", "head_to_head_spa_p_2016", "max_drawdown", "arm_a_max_drawdown", "max_drawdown_reduction_pct",
    "spot_drag_pct_yr", "arm_a_spot_drag_pct_yr", "turnover_a", "turnover_b", "turnover_b_intra", "turnover_reduction_pct",
    "stamps_positions_differ",
}
_B1_EXIT_PREFLIGHT_KEYS = _B1_EXIT_ENGAGEMENT | _B1_HOURLY_RV_ANCHORS | _ARM_A_BAR_KEYS | {"arm_a_var_trials"}


def test_the_b1_hourly_exit_subjects_declare_both_grids_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count():
    trial, preflight = subjects.SUBJECTS["b1-hourly-channel-exits"], subjects.SUBJECTS["b1-hourly-channel-exits-preflight"]
    assert (len(_B1_EXIT_METRIC_KEYS), len(_B1_EXIT_PREFLIGHT_KEYS)) == (46, 25)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        "b1-hourly-channel-exits",
        (240, 60),
        _B2_ASSETS,
        _B1_EXIT_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b1_hourly_exit and trial.metric_keys == _B1_EXIT_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b1_hourly_exit_verdict, _B1_EXIT_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B1", 5)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        "b1-hourly-channel-exits-preflight",
        (240, 60),
        _B2_ASSETS,
        _B1_EXIT_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b1_hourly_exit_preflight
    assert preflight.metric_keys == _B1_EXIT_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


def test_the_b1_hourly_exit_dispersion_reads_records_45_46_48_and_49s_registered_sharpes_and_deflates_at_five_trials():
    assert (
        subjects._B1_EXIT_RECORDED_PER_PERIOD_SHARPES
        == (0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177)
        == tuple(_trials()[n]["metrics"]["per_period_sharpe_4h"] for n in (45, 46, 48, 49))
    )
    assert expected_max_sharpe(subjects._B1_EXIT_N_TRIALS, 1.0) == 1.192594001014789


# Adopting on every key the rule reads, while trading more than arm A, which it does not read; each row moves the keys it names.
_B1_EXIT_ADOPTING = {
    "arm_a_passes": 1,
    "hourly_closes_directions_differ": 9,
    "passes": 1,
    "spa_p_decisive_b102_s42": 0.01,
    "head_to_head_mean_outperf_full": 0.001,
    "head_to_head_spa_p_full": 0.01,
    "max_drawdown_reduction_pct": 5.0,
    "turnover_a": 140.0,
    "turnover_b": 150.0,
}


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-passes-outperforms-significantly-at-both-blocks-and-draws-down-less"),
        pytest.param({"spa_p_decisive_b102_s42": 0.2}, "park", id="row-2-the-block-102-spa-fails"),
        pytest.param({"head_to_head_spa_p_full": 0.2}, "park", id="row-3-outperforms-insignificantly-and-draws-down-less"),
        pytest.param({"head_to_head_mean_outperf_full": -0.001}, "reject", id="row-4-underperforms"),
        pytest.param({"max_drawdown_reduction_pct": -5.0}, "reject", id="row-4-draws-down-more"),
        pytest.param({"passes": 0}, "reject", id="row-5-arm-b-fails-its-bar"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="reduction-at-exactly-1e-6"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6}, "adopt", id="reduction-past-1e-6"),
        pytest.param({"head_to_head_mean_outperf_full": 0.0}, "reject", id="mean-at-exactly-0"),
        pytest.param({"head_to_head_spa_p_full": 0.05}, "park", id="p-at-exactly-0.05"),
        pytest.param({"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.0499}, "adopt", id="both-p-at-0.0499"),
        pytest.param(
            {"head_to_head_spa_p_full": 0.0499, "spa_p_decisive_b102_s42": 0.05}, "park", id="block-102-p-at-exactly-0.05"
        ),
        pytest.param(
            {"head_to_head_mean_outperf_full": -0.001, "head_to_head_mean_outperf_2016": 0.001},
            "reject",
            id="outperforms-from-2016-alone",
        ),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param({"hourly_closes_directions_differ": 0}, None, id="the-directions-never-differ"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({"hourly_closes_directions_differ": 0, "passes": 0}, None, id="the-directions-read-before-passes"),
    ],
)
def test_the_b1_hourly_exit_rule_maps_its_metrics_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b1_hourly_exit_verdict({**_B1_EXIT_ADOPTING, **change}) == verdict


@pytest.mark.parametrize(
    ("arm_b_passes", "arm_a_passes"),
    [pytest.param(True, False, id="arm-a-fails-so-the-rule-stops"), pytest.param(False, 7, id="arm-b-fails-so-the-rule-rejects")],
)
def test_the_b1_hourly_exit_subject_registers_each_metric_from_its_own_call(tmp_path, monkeypatch, arm_b_passes, arm_a_passes):
    root = _b1_hourly_exit_dataset(tmp_path)
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, root, registry)
    h4_ts, h4_prices, hourly = subjects._b1_hourly_rv_reads(
        ObservedReader(root), "ohlc-test", None, None, False, subject="b1-hourly-channel-exits"
    )
    n = len(h4_ts) - 1
    k16 = next(k for k in range(n) if h4_ts[k] >= datetime(2016, 1, 1, tzinfo=UTC))
    fed = _ffill_btc(h4_prices)
    interior = interior_closes_by_asset(fed, h4_prices, h4_ts, hourly)
    weights_a = _inverse_vol_weights(fed, lookback=180)
    union_idx = list(range(len(h4_ts)))
    asset_ts = {a: [k for k, p in enumerate(fed[a]) if p is not None] for a in _B2_ASSETS}
    books = [a2_book_returns(fed, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_a = [_asset_directions_a2(fed, union_idx, asset_ts, config=config) for config in _B1_HOURLY_RV_ARMS]
    exits = [asset_directions_hourly_exit(fed, union_idx, asset_ts, interior, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_b = [directions for directions, _ in exits]
    arms_b = [a2_slot_positions(weights_a, d, book["vol_target_positions"]) for d, book in zip(directions_b, books)]
    arm_a = {a: [statistics.mean(book["asset_positions"][a][k] for book in books) for k in range(n)] for a in _B2_ASSETS}
    arm_b = {a: [tuple(statistics.mean(arm[a][k][i] for arm in arms_b) for i in range(4)) for k in range(n)] for a in _B2_ASSETS}
    returns, paths = {a: _asset_returns(fed[a]) for a in _B2_ASSETS}, price_paths(fed, interior)
    net_a, net_a_x15 = (net_of_cost(arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    net_b, net_b_x15 = (net_of_cost_hourly(arm_b, paths, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)

    assert fed["BTC"] != h4_prices["BTC"]
    assert net_b != net_a and net_b[k16:] != net_a[k16:]
    pairs = [(a, b) for da, db in zip(directions_a, directions_b) for s in _B2_ASSETS for a, b in zip(da[s], db[s])]
    assert all((a is None) == (b is None) for a, b in pairs)
    assert all(max(b) <= a for a, b in pairs if a is not None) and any(min(b) < a for a, b in pairs if a is not None)
    assert all(max(arm_b[a][k]) <= arm_a[a][k] for a in _B2_ASSETS for k in range(n))

    def kill_bar(arguments, result):
        book = arguments["book_net_returns"]
        cell = "A" if book == net_a else "B" if book == net_b else None
        if cell is None:
            return result
        return result | _b1_hourly_rv_bar_sentinels(cell, passes=arm_a_passes if cell == "A" else arm_b_passes)

    spa_sentinels = {cell: 0.51 + i / 100 for i, cell in enumerate(_B1_HOURLY_RV_CELLS)}

    def spa(arguments, result):
        p = spa_sentinels.get((arguments["mean_block"], arguments["seed"]))
        return result if p is None else result | {"p_value": p}

    def head_to_head(arguments, result):
        p = {n: 0.41, n - k16: 0.42}.get(len(arguments["book_net_of_cost"]))
        return result if p is None else result | {"spa_p_value": p}

    kill_calls = _recording(monkeypatch, "a1_kill_bar", kill_bar)
    spa_calls = _recording(monkeypatch, "reality_check_pvalue", spa)
    verdict_calls = _recording(monkeypatch, "net_of_cost_verdict", head_to_head)
    hourly_calls = _recording(monkeypatch, "net_of_cost_hourly", lambda arguments, result: result)
    result = runner.invoke(
        app,
        ["research", "eval", "--subject", "b1-hourly-channel-exits", "--dataset", "ohlc-test", "--register", "--registry"]
        + [str(registry), "--ledger", str(ledger), "--iteration", "iter-179", "--family", "B1", "--n-trials", "5"]
        + ["--variant", "B1-hourly-exit-a2eq-v1"],
    )

    assert result.exit_code == 0, result.output
    if arm_a_passes:
        (record,) = [json.loads(line) for line in registry.read_text().splitlines()]
        assert set(record["metrics"]) == _B1_EXIT_METRIC_KEYS
        assert set(record["datasets"]["ohlc-test"]["files"]) == {f"{a}/EUR/{i}.parquet" for a in _B2_ASSETS for i in (240, 60)}
        assert record["n_trials_in_family"] == 5
        assert record["verdict"] == "reject"
        assert not ledger.exists()
        stored = record["metrics"]
    else:
        assert f"no verdict — {_B1_EXIT_NO_VERDICT}: recorded reading 1; no trial spent" in result.output
        assert not registry.exists()
        (reading,) = _kept(ledger)
        assert reading["outcome"] == _B1_EXIT_NO_VERDICT
        assert reading["metrics"] == _block_and_metrics(result.output)["metrics"]
        stored = reading["metrics"]

    var_b = statistics.variance([0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177, sharpe(net_b)])
    var_a = statistics.variance([0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177, sharpe(net_a)])
    bar = {
        "benchmark_net_returns": bench,
        "n_trials": 5,
        "mean_block": 30,
        "seed": 42,
        "benchmark_slices": calendar_year_slices(bench, h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    assert len(kill_calls) == 2
    assert {"A" if arguments["book_net_returns"] == net_a else "B": arguments for arguments, _ in kill_calls} == {
        "B": bar
        | {
            "book_net_returns": net_b,
            "var_trials": var_b,
            "cost_stressed_returns": net_b_x15,
            "regime_slices": calendar_year_slices(net_b, h4_ts),
        },
        "A": bar
        | {
            "book_net_returns": net_a,
            "var_trials": var_a,
            "cost_stressed_returns": net_a_x15,
            "regime_slices": calendar_year_slices(net_a, h4_ts),
        },
    }
    assert [arguments["cost_per_side"] for arguments, _ in hourly_calls] == [0.006, 1.5 * 0.006]
    decisive = [[net_b[k] - bench[k]] for k in range(1380, n)]
    assert sorted(
        (arguments for arguments, _ in spa_calls), key=lambda arguments: (arguments["mean_block"], arguments["seed"])
    ) == [
        {"perf_matrix": decisive, "mean_block": block, "n_resamples": 2000, "seed": seed}
        for block, seed in sorted(_B1_HOURLY_RV_CELLS[1:])
    ]
    head_to_head_call = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    assert [arguments for arguments, _ in verdict_calls] == [
        {"book_net_of_cost": net_b, "benchmark_net_of_cost": net_a} | head_to_head_call,
        {"book_net_of_cost": net_b[k16:], "benchmark_net_of_cost": net_a[k16:]} | head_to_head_call,
    ]
    full, from_2016 = (outcome for _, outcome in verdict_calls)
    assert full["mean_outperformance"] != from_2016["mean_outperformance"]

    bars = {"A" if arguments["book_net_returns"] == net_a else "B": outcome for arguments, outcome in kill_calls}
    grid = {(arguments["mean_block"], arguments["seed"]): outcome["p_value"] for arguments, outcome in spa_calls}
    turnover_a = book_turnover(arm_a)
    turnover_b = book_turnover({a: [p for slots in arm_b[a] for p in slots] for a in _B2_ASSETS})
    expected = {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=2190),
        "ann_sharpe_noc_decisive": sharpe(net_b[1380:], periods_per_year=2190),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        "var_trials": var_b,
        "dsr_corrected": bars["B"]["dsr"],
        "dsr_pass": int(bars["B"]["dsr_pass"]),
        "spa_pass": int(bars["B"]["spa_pass"]),
        "spa_p_full": bars["B"]["spa_p_value_full"],
        "cost_stress_pass": int(bars["B"]["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bars["B"]["worst_slice_pass"]),
        "passes": int(bars["B"]["passes"]),
        "decisive_start": 1380,
        "n_resamples": 2000,
        "arm_a_var_trials": var_a,
        "arm_a_passes": int(bars["A"]["passes"]),
        "spa_p_decisive_b30_s42": bars["B"]["spa_p_value"],
        **{f"spa_p_decisive_b{block}_s{seed}": grid[(block, seed)] for block, seed in _B1_HOURLY_RV_CELLS[1:]},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_reduction_pct": 100 * (max_drawdown(net_a) - max_drawdown(net_b)) / max_drawdown(net_a),
        "spot_drag_pct_yr": turnover_b / n * 0.006 * 2190,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_b_intra": intra_turnover(arm_b),
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_positions_differ": sum(any(p != arm_a[a][k] for a in _B2_ASSETS for p in arm_b[a][k]) for k in range(n)),
    }
    own_stamps = {a: [h4_ts[k] for k in asset_ts[a]] for a in _B2_ASSETS}
    per_year = {str(i + 1): exit_events_per_year(events, own_stamps) for i, (_, events) in enumerate(exits)}
    counts = [
        c
        for arm in per_year.values()
        for by_asset in arm.values()
        for by_lookback in by_asset.values()
        for c in by_lookback.values()
    ]
    events, early, false = (sum(c[i] for c in counts) for i in range(3))
    differ = hourly_closes_differ_per_year(directions_a, directions_b, h4_ts)
    expected |= {
        "exit_events_per_year": per_year,
        "exit_events": events,
        "exit_events_early": early,
        "exit_events_false": false,
        "share_false": false / events,
        "hourly_closes_directions_differ": sum(differ.values()),
        "hourly_closes_directions_differ_per_year": differ,
    }
    assert set(expected) == _B1_EXIT_METRIC_KEYS
    assert stored == expected


def test_the_b1_hourly_exit_preflight_reads_arm_a_and_the_exits_and_never_builds_arm_bs_positions_or_returns(tmp_path, monkeypatch):
    root = _b1_hourly_exit_dataset(tmp_path)
    trial = subjects.SUBJECTS["b1-hourly-channel-exits"].build(ObservedReader(root), "ohlc-test", None)

    def arm_b(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions or returns")

    monkeypatch.setattr(subjects, "a2_slot_positions", arm_b)
    monkeypatch.setattr(subjects, "net_of_cost_hourly", arm_b)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    metrics = subjects.SUBJECTS["b1-hourly-channel-exits-preflight"].build(ObservedReader(root), "ohlc-test", None)

    assert [arguments["n_trials"] for arguments, _ in bars] == [5]
    ints = _ARM_A_BAR_FLAGS | {"exit_events", "exit_events_early", "exit_events_false", "hourly_closes_directions_differ"}
    dicts = {"exit_events_per_year", "hourly_closes_directions_differ_per_year"}
    assert set(metrics) == _B1_EXIT_PREFLIGHT_KEYS
    assert {key for key, value in metrics.items() if type(value) is int} == ints
    assert {key for key, value in metrics.items() if type(value) is dict} == dicts
    assert {key for key, value in metrics.items() if type(value) is float} == _B1_EXIT_PREFLIGHT_KEYS - ints - dicts
    assert metrics["hourly_closes_directions_differ"] > 0
    assert 0 < metrics["exit_events_early"] < metrics["exit_events"] == metrics["exit_events_early"] + metrics["exit_events_false"]
    assert {key: metrics[key] for key in _B1_EXIT_ENGAGEMENT} == {key: trial[key] for key in _B1_EXIT_ENGAGEMENT}
    assert (metrics["passes"], metrics["arm_a_var_trials"]) == (trial["arm_a_passes"], trial["arm_a_var_trials"])
    assert {key: metrics[key] for key in _B1_HOURLY_RV_ANCHORS} == {key: trial[key] for key in _B1_HOURLY_RV_ANCHORS}


def _b1_hourly_exit_args(name: str, tmp_path: Path, *, dataset: str = "ohlc-test") -> list[str]:
    return ["research", "eval", "--subject", name, "--dataset", dataset, *_as_trial(name, tmp_path)]


@pytest.mark.parametrize("name", ["b1-hourly-channel-exits", "b1-hourly-channel-exits-preflight"])
def test_a_b1_hourly_exit_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)

    result = runner.invoke(app, [*_b1_hourly_exit_args(name, tmp_path, dataset="ohlc-rolling"), "--as-of", "2026-10-03"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} evaluates a frozen set's 4h and hourly series, never the rolling dataset as of a day: drop --as-of" in (
        result.output
    )


def _an_hourly_close_set(path: Path, value: float | None) -> datetime:
    frame = pl.read_parquet(path)
    closes, k = frame["close"].to_list(), frame.height // 2
    closes[k] = value
    frame.with_columns(close=pl.Series(closes, dtype=frame.schema["close"])).write_parquet(path)
    return frame["ts"][k]


@pytest.mark.parametrize(
    ("value", "shown"), [pytest.param(0.0, "0.0", id="zero-close"), pytest.param(None, "None", id="null-close")]
)
def test_b1_hourly_exit_refuses_an_hourly_close_it_cannot_check_naming_the_asset_and_stamp(tmp_path, monkeypatch, value, shown):
    root = _b1_hourly_exit_dataset(tmp_path)
    stamp = _an_hourly_close_set(root / "ohlc-test" / "ETH/EUR/60.parquet", value)
    _anchor(monkeypatch, root)
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)

    result = runner.invoke(app, _b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        "b1-hourly-channel-exits over the full history: ETH: hourly close must be a finite number above 0, got "
        f"{shown} at {stamp.isoformat()}"
    ) in result.output
    assert calls == []


def test_b1_hourly_exit_refuses_an_hourly_bar_in_a_4h_bar_its_240_file_lacks(tmp_path, monkeypatch):
    root = _b1_hourly_exit_dataset(tmp_path)
    path = root / "ohlc-test" / "ETH/EUR/240.parquet"
    frame = pl.read_parquet(path)
    dropped = frame["ts"][frame.height // 2]
    frame.filter(pl.col("ts") != dropped).write_parquet(path)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, _b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"b1-hourly-channel-exits over the full history: ETH: an hourly bar at {dropped.isoformat()} lies in a 4h bar the 240 "
        "series lacks"
    ) in result.output


def _arm_a_never_draws_down(monkeypatch) -> None:
    monkeypatch.setattr(subjects, "max_drawdown", lambda returns: 0.0)


@pytest.mark.parametrize(
    ("freeze", "named"),
    [
        pytest.param(_arm_a_flat, "turnover_a is 0.0", id="arm-a-never-trades"),
        pytest.param(_arm_a_never_draws_down, "arm_a_max_drawdown is 0.0", id="arm-a-never-draws-down"),
    ],
)
def test_b1_hourly_exit_refuses_a_build_whose_arm_a_never_trades_or_never_draws_down(tmp_path, monkeypatch, freeze, named):
    _anchor(monkeypatch, _b1_hourly_exit_dataset(tmp_path))
    freeze(monkeypatch)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    result = runner.invoke(app, _b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "b1-hourly-channel-exits over the full history: " in result.output and named in result.output
    assert bars == []


@pytest.mark.parametrize("name", ["b1-hourly-channel-exits", "b1-hourly-channel-exits-preflight"])
def test_a_b1_hourly_exit_build_without_an_exit_event_is_refused(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _b1_hourly_exit_dataset(tmp_path))
    real = subjects.asset_directions_hourly_exit

    def no_exits(*args, **kwargs):
        directions, events = real(*args, **kwargs)
        return directions, {asset: dict.fromkeys(by_lookback, []) for asset, by_lookback in events.items()}

    monkeypatch.setattr(subjects, "asset_directions_hourly_exit", no_exits)

    result = runner.invoke(app, _b1_hourly_exit_args(name, tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the full history: exit_events is 0, and share_false divides by it" in result.output


@pytest.mark.parametrize(
    ("flags", "refused"),
    [
        pytest.param(
            [],
            "b1-hourly-channel-exits declares a verdict rule, so every run of it is a trial: run it with --register",
            id="plain-eval",
        ),
        pytest.param(
            ["--register", "--iteration", "iter-179", "--family", "B1", "--n-trials", "4"],
            "--n-trials 4 is not 5, the count b1-hourly-channel-exits declares and deflates at: pass --n-trials 5",
            id="trial-4s-count",
        ),
    ],
)
def test_b1_hourly_exit_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, flags, refused):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b1_hourly_rv_reads", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", "b1-hourly-channel-exits", "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


def test_b1_hourly_exit_reads_both_grids_under_the_window(tmp_path, monkeypatch):
    root = _b1_hourly_exit_dataset(tmp_path)
    window = (str(_B1_START + timedelta(hours=4 * 100)), str(_B1_START + timedelta(hours=4 * (_B1_BARS - 1))))
    read_series, reads = ObservedReader.read_series, []

    def recording_read(self, dataset, relpath, window=None):
        reads.append((relpath, window))
        return read_series(self, dataset, relpath, window)

    def stop(reads):
        raise ValidationError("stopped after the reads")

    monkeypatch.setattr(ObservedReader, "read_series", recording_read)
    monkeypatch.setattr(subjects, "_b1_hourly_exit_inputs", stop)

    with pytest.raises(subjects.SubjectError, match="stopped after the reads"):
        subjects.SUBJECTS["b1-hourly-channel-exits"].build(ObservedReader(root), "ohlc-test", window)

    assert sorted(reads) == sorted((f"{a}/EUR/{i}.parquet", window) for a in _B2_ASSETS for i in (240, 60))


def test_a_b1_hourly_exit_window_off_the_4h_grid_is_refused_naming_an_hourly_bar_its_240_read_lacks(tmp_path, monkeypatch):
    _anchor(monkeypatch, _b1_hourly_exit_dataset(tmp_path))
    start, end = _B1_START + timedelta(hours=2), _B1_START + timedelta(hours=4 * (_B1_BARS - 1))

    result = runner.invoke(app, [*_b1_hourly_exit_args("b1-hourly-channel-exits", tmp_path), "--window", str(start), str(end)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"b1-hourly-channel-exits over the window {start} .. {end}: ADA: an hourly bar at {start.isoformat()} lies in a 4h "
        "bar the 240 series lacks"
    ) in result.output
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00135 && uv run pytest tests/test_research_command.py -k "b1_hourly_exit or ruled_subjects or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt`
Expected (Task 1 committed): `38 failed, 3 passed` — each new `b1_hourly_exit` case, the kill-bar test's `[b1-hourly-channel-exits]` row and the metric-keys test fail on `AttributeError: module 'cli.research.subjects' has no attribute '_b1_hourly_exit_verdict'` or a sibling name, on `KeyError: 'b1-hourly-channel-exits'`, or on the command's unknown-subject refusal; the families test fails on its literal's `AssertionError`; the kill-bar test's three other rows pass. Against the tree at this plan's commit the module's import of `cli.alpha.b1_exit` stops collection.

- [ ] **Step 3: Implement in `cli/research/subjects.py`** — the Produces names, each with the spec's values; the imports take Task 1's eight functions:
  - The two literals, each with the one-line reason it is a literal (records 45, 46, 48 and 49's registered values, record 49's every digit its writer stored; the family's count at this trial, records 45, 46, 48 and 49 and itself), under a comment naming spec 00135 as trial 4's names spec 00134.
  - `_b1_hourly_exit_inputs`: `fed = _ffill_btc(h4_prices)`; `interior = interior_closes_by_asset(fed, h4_prices, h4_ts, hourly)` next, its price validation and D4's refusals coming before `_asset_returns` divides by a close; `returns`; `weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)`; `union_idx = list(range(len(h4_ts)))`, `asset_ts` the indices where `fed[a]` holds a price, as `a2_book_returns` builds them, `own_stamps` the stamps at those indices; per arm of `_B1_A2_ARMS` its `A2Config` (arm A's) bound to a name, `a2_book_returns(fed, config=<it>)` for the positions and `vol_target_positions`, `_asset_directions_a2(fed, union_idx, asset_ts, config=<it>)` and `asset_directions_hourly_exit(fed, union_idx, asset_ts, interior, config=<it>)`; `paths = price_paths(fed, interior)`; `arm_a = {a: [statistics.mean(arm[a][k] for arm in positions_a) for k in range(n)] for a in _ASSETS}`, `_b1_volume_inputs`' expression — no position or return of arm B.
  - `_b1_hourly_exit_arm_a`: `_b1_volume_arm_a`'s body over these inputs with `arm_a_var_trials = statistics.variance([*_B1_EXIT_RECORDED_PER_PERIOD_SHARPES, sharpe(net_a)])` and `n_trials=_B1_EXIT_N_TRIALS`.
  - `_b1_hourly_exit_engagement`: `exit_events_per_year(events, inputs.own_stamps)` per arm under `str(i + 1)`; the three totals; `if events == 0:` on its own line, a `ValidationError` `"exit_events is 0, and share_false divides by it"`; `share_false`; `differ = hourly_closes_differ_per_year(inputs.directions_a, inputs.directions_b, inputs.h4_ts)` and its sum — D8's seven keys.
  - `_b1_hourly_exit_metrics`: `turnover_a = book_turnover(arm_a)` and `drawdown_a = max_drawdown(net_of_cost(arm_a, inputs.returns, cost_per_side=_B1_COST_PER_SIDE))`, then `if turnover_a == 0 or drawdown_a == 0:` on its own line, a `ValidationError` `f"turnover_a is {turnover_a} and arm_a_max_drawdown is {drawdown_a}, and turnover_reduction_pct and max_drawdown_reduction_pct divide by them"` — **Author's call**: the drawdown is read off a second computation of the arm-A half's `net_a`, so neither refusal waits on a kill bar; then the engagement — all before any bar; arm A's half; arm B, `arms = [a2_slot_positions(inputs.weights_a, inputs.directions_b[i], inputs.vt_a[i]) for i in range(len(_B1_A2_ARMS))]` on one line and `arm_b = {a: [tuple(statistics.mean(arm[a][k][i] for arm in arms) for i in range(4)) for k in range(n)] for a in _ASSETS}`; `net_b` and `net_b_x15` through `net_of_cost_hourly(arm_b, inputs.paths, cost_per_side=…)`; `per_period_sharpe_4h = sharpe(net_b)` on its own line; `var_trials = statistics.variance([*_B1_EXIT_RECORDED_PER_PERIOD_SHARPES, per_period_sharpe_4h])`; arm B's bar, the five other SPA cells over `_B1_HOURLY_RV_GRID`, `k16`, the two head-to-heads, as `_b1_volume_metrics` computes them; `turnover_b = book_turnover({a: [p for slots in arm_b[a] for p in slots] for a in _ASSETS})`; `drawdown_b = max_drawdown(net_b)`; the 46 keys, each from one source as D11 lists them — `"max_drawdown": drawdown_b`, `"arm_a_max_drawdown": drawdown_a`, `"max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a`, `"turnover_b_intra": intra_turnover(arm_b)`, `spot_drag_pct_yr` and `arm_a_spot_drag_pct_yr` as `turnover / n * _B1_COST_PER_SIDE * PPY_4H`, `"stamps_positions_differ": sum(any(p != arm_a[a][k] for a in _ASSETS for p in arm_b[a][k]) for k in range(n))`, the engagement's seven.
  - `_b1_hourly_exit_preflight_metrics`: the engagement first; arm A's bar from `_b1_hourly_exit_arm_a(inputs)`, the trial's own call, its ten keys as `_b1_volume_preflight_metrics` writes them, flags as int; `arm_a_var_trials`; the seven anchors over `net_a`, `bench` and arm A's turnover.
  - `_b1_hourly_exit_build`: `reads = _b1_hourly_rv_reads(reader, dataset, window, as_of, accept_holes, subject=subject)`, then the inputs and `compute` inside one `try`, `(AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError)` a `SubjectError` `f"{_b2_over(subject, window)}: {exc}"`, as `_b1_volume_build` does; the two builders over it.
  - `_b1_hourly_exit_verdict`: spec D10's code block verbatim, under trial 4's comment form naming spec 00135 D10.
  - `_B1_EXIT_METRIC_KEYS` (46, D11's list) and `_B1_EXIT_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {…the seven anchors…, "arm_a_var_trials", …D8's seven engagement keys…}` (25), under a comment naming spec 00135 D11; the two `SUBJECTS` entries exactly as D11 declares them, `no_verdict` the spec's text.

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row's list, which now ends `` …, `b1-volume-confirmation` (…) or `b1-volume-confirmation-preflight` (…; it has no rule, so its run is kept with `--reading`). ``, ends `` …, `b1-volume-confirmation-preflight` (…; it has no rule, so its run is kept with `--reading`), `b1-hourly-channel-exits` (the A2 4h ensemble against the same ensemble with each breakout's long state also ended at the first hourly close inside a 4h interval that breaches the level at which that interval's close would be a new channel low; the 4h and hourly series of `--dataset`, a frozen set only) or `b1-hourly-channel-exits-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar, the hourly exits and the hourly closes whose directions differ, with no return of the hourly-exit book; it has no rule, so its run is kept with `--reading`). ``, in the row's own voice and backticks, no internal term.

- [ ] **Step 5: Run them to verify they pass** — Step 2's command, expected `41 passed`; then, timed, in two parts each under 600 s, `uv run pytest tests/test_research_command.py -k "b1_hourly_exit or ruled_subjects or b1-hourly-channel-exits" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt` and the same with `-k "b1_hourly_rv or b1-hourly-rv"`, and each new case at 10 s or more joins `tests/slow-cases.txt` at its sorted place, `tests/test_slow_cases.py` then passing; the rest of the file runs in Step 6. Measured against a transcription, the two parts at about 5 and 4 minutes: the register test's two rows, the pre-flight test, the kill-bar row `[b1-hourly-channel-exits]`, the contract rows `[b1-hourly-channel-exits-evaluates]`, `[b1-hourly-channel-exits-preflight-evaluates]`, `[b1-hourly-channel-exits-btc-absent-at-the-first-stamp-on-60]` and `[b1-hourly-channel-exits-preflight-btc-absent-at-the-first-stamp-on-60]` and the shared-defaults rows `[b1-hourly-channel-exits]` and `[b1-hourly-channel-exits-preflight]` ran at 12–28 s; the two `never_trades_or_never_draws_down` rows and the two `without_an_exit_event` rows at about 9 s, which this step's own timing decides; trial 3's cases pass over the shared aggregation.

- [ ] **Step 6: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the direct readers of the four paths, `-m "not slow and not data"`, in parts; `uv run pre-commit run -a` until clean, its rewrites staged.

- [ ] **Step 7: Probes** — on the staged tree, in the probe worktree; `--file cli/research/subjects.py`; control `s/^def _b1_hourly_exit_verdict(/def _b1_hourly_exit_verdict_gone(/` (`SUBJECTS` names it, so the module no longer imports and every case fails); each row one probe per case it names, expected `KILLED`; a case `tests/slow-cases.txt` lists is skipped and recorded. The contract rows and shared-defaults rows of the two subjects are new rows of existing tests, neither a test function nor a refusal case, so no new guard, and they are not probed — the zero-close row aside, which holds D11's validation order.

| node id under `tests/test_research_command.py::` | mutation |
| -- | -- |
| `test_the_b1_hourly_exit_subjects_declare_both_grids_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count` and `test_each_subject_declares_the_metric_keys_its_build_returns` | `metric_keys=_B1_EXIT_PREFLIGHT_KEYS,` made `metric_keys=_B1_EXIT_METRIC_KEYS,` |
| `test_the_b1_hourly_exit_dispersion_reads_records_45_46_48_and_49s_registered_sharpes_and_deflates_at_five_trials` | `0.03028127927651177)` made `0.0302812792765)` on the `_B1_EXIT_RECORDED_PER_PERIOD_SHARPES = ` line |
| `test_the_b1_hourly_exit_rule_maps_its_metrics_to_a_verdict_or_a_stop[<id>]`, each within `/^def _b1_hourly_exit_verdict(/,/^[^ #]/` | `m["max_drawdown_reduction_pct"] > 1e-6` made `>= 1e-6` (`reduction-at-exactly-1e-6`), and made `> 1e-5` (`reduction-past-1e-6`); ` and m["max_drawdown_reduction_pct"] > 1e-6` made ` and m["turnover_b"] < m["turnover_a"]` (`row-1-passes-outperforms-significantly-at-both-blocks-and-draws-down-less`), and made ` and True` (`row-4-draws-down-more`); `m["head_to_head_mean_outperf_full"] > 0` made `>= 0` (`mean-at-exactly-0`); `m["head_to_head_spa_p_full"] < 0.05` made `<= 0.05` (`p-at-exactly-0.05`); ` and m["spa_p_decisive_b102_s42"] < 0.05` made ` and True` (`block-102-p-at-exactly-0.05`, `row-2-the-block-102-spa-fails`); `m["hourly_closes_directions_differ"] == 0` made `False` (`the-directions-never-differ`); `not m["arm_a_passes"]` made `False` (`arm-a-fails-its-bar`); `head_to_head_mean_outperf_full` made `head_to_head_mean_outperf_2016` (`outperforms-from-2016-alone`); `if not m["passes"]:` made `if False:` (`row-5-arm-b-fails-its-bar`) |
| `test_the_ruled_subjects_declare_their_families_and_trial_counts` | within `/"b1-hourly-channel-exits": Subject(/,/^    ),/`, `family="B1",` made `family="B2",` |
| `test_b1_hourly_exit_refuses_a_plain_eval_and_another_count_before_any_read[<id>]`, each within `/"b1-hourly-channel-exits": Subject(/,/^    ),/` | `verdict=_b1_hourly_exit_verdict,` made `verdict=None,` (`plain-eval`); `n_trials=_B1_EXIT_N_TRIALS,` made `n_trials=4,` (`trial-4s-count`) |
| `test_a_b1_hourly_exit_subject_refuses_as_of_before_any_read[<each>]` | within `/^def _b1_hourly_rv_reads(/,/^def /`, `if as_of is not None:` made `if False:` |
| `test_b1_hourly_exit_reads_both_grids_under_the_window` | within `/^def _b1_hourly_exit_build(/,/^def /`, `_b1_hourly_rv_reads(reader, dataset, window,` made `_b1_hourly_rv_reads(reader, dataset, None,` |
| `test_b1_hourly_exit_refuses_an_hourly_close_it_cannot_check_naming_the_asset_and_stamp[<each>]`, `test_b1_hourly_exit_refuses_an_hourly_bar_in_a_4h_bar_its_240_file_lacks` and `test_a_b1_hourly_exit_window_off_the_4h_grid_is_refused_naming_an_hourly_bar_its_240_read_lacks` | within `/^def _b1_hourly_exit_build(/,/^def /`, `AlphaError, ` dropped from the caught tuple by substitution (the refusal then the command's own compute-error exit, `<subject> over <span> of ohlc-test: <message> (AlphaError raised at …)`, which the asserted `<subject> over <span>: ` text does not match) |
| `test_b1_hourly_exit_refuses_a_build_whose_arm_a_never_trades_or_never_draws_down[<each>]` | `if turnover_a == 0 or drawdown_a == 0:` made `if False:` |
| `test_a_b1_hourly_exit_build_without_an_exit_event_is_refused[<each>]` | within `/^def _b1_hourly_exit_engagement(/,/^def /`, `if events == 0:` made `if False:` |
| `test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b1-hourly-channel-exits-a-zero-close-on-240]` | within `/^def _b1_hourly_exit_inputs(/,/^def /`, `s/^\( *\)fed = _ffill_btc(h4_prices)/\1fed = _ffill_btc(h4_prices); _ = [_asset_returns(fed[a]) for a in _ASSETS]/` (the zero close then a `ZeroDivisionError`, a traceback) |
| `test_the_b1_hourly_exit_subject_registers_each_metric_from_its_own_call[<each>]`, `test_the_b1_hourly_exit_preflight_reads_arm_a_and_the_exits_and_never_builds_arm_bs_positions_or_returns`, `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b1-hourly-channel-exits]` | slow cases: skipped, recorded — unless Step 5 timed one under 10 s, when the register rows take, within `/^def _b1_hourly_exit_metrics(/,/^def /`, the `net_b = ` line's `cost_per_side=_B1_COST_PER_SIDE` made `cost_per_side=0.0`; the pre-flight `n_trials=_B1_EXIT_N_TRIALS,` made `n_trials=1 + _B1_EXIT_N_TRIALS,` within `/^def _b1_hourly_exit_arm_a(/,/^def /`; and the kill-bar row the same within `/^def _b1_hourly_exit_metrics(/,/^def /` |

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(research): the b1-hourly-channel-exits subject and its pre-flight twin — both arms, the bar at the family's dispersion and count, the head-to-head, the drawdown pair and the exit events

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>
<probe skipped: slow case — each listed case, by node id>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 3: the data-gated tests over `ohlc-full` — the measured basis and arm A's anchors (D5, D9)

**Files:**
- Create: `tests/test_research_b1_hourly_exit_basis.py` (module-marked `data`)
- Modify: `tests/slow-cases.txt`, when Step 2 times the basis test at 10 s or more

**Interfaces:**
- Consumes: Task 1's `interior_closes_by_asset`; Task 2's `_b1_hourly_exit_inputs` and `_B1HourlyExitInputs`' fields `h4_ts`, `h4_prices`, `returns`, `arm_a`; trial 3's `_b1_hourly_rv_reads`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`.
- Produces: `test_the_b1_hourly_exit_reads_reproduce_the_measured_basis` — the reads and the interior closes alone, run before the hash; `test_the_b1_hourly_exit_arm_a_reproduces_records_48_and_49s_arm_a` — arm A, run only after Task 4 step 2's hash. Neither computes a return of arm B; the first computes no state, no direction, no position and no return of either arm.

- [ ] **Step 1: Write the failing tests** — every literal copied from the spec's measured basis, never from a run:

```python
"""B1 trial 5's reads half and interior hourly closes against spec 00135's measured basis, computing no state, and arm A
against records 48 and 49's stored figures, run only after the spec's hash."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b1_exit import interior_closes_by_asset
from cli.alpha.b2 import net_of_cost
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_BLOCK_HASH = "8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1"
_H1, _H4 = timedelta(hours=1), timedelta(hours=4)
_LAST_HOUR = datetime(2026, 3, 31, 23, tzinfo=UTC)
# Per asset, from the spec's measured basis: hourly rows, first hour, missing hours of the grid to the last, those inside a
# present 240 bar's span; over each 240 bar after the first, the count holding 0..3 interior hourly closes; the union-adjacent
# intervals and those holding all three; the 240 bars holding the hourly bar 3h in.
_BASIS = {
    "ADA": (65_623, (2018, 9, 28, 13), 172, 161, {0: 3, 1: 10, 2: 92, 3: 16_340}, (16_444, 16_340), 16_407),
    "AVAX": (37_157, (2021, 12, 21, 15), 316, 303, {0: 2, 1: 10, 2: 183, 3: 9_169}, (9_362, 9_169), 9_274),
    "BTC": (108_786, (2013, 9, 10, 23), 1_255, 542, {0: 28, 1: 111, 2: 98, 3: 27_094}, (27_326, 27_093), 27_197),
    "DOGE": (53_237, (2019, 12, 19, 14), 1_829, 1_603, {0: 42, 1: 266, 2: 512, 3: 12_889}, (13_660, 12_881), 13_279),
    "DOT": (49_181, (2020, 8, 18, 17), 50, 43, {0: 1, 1: 5, 2: 18, 3: 12_281}, (12_305, 12_281), 12_295),
    "ETH": (92_294, (2015, 8, 7, 11), 1_055, 874, {0: 25, 1: 139, 2: 305, 3: 22_822}, (23_260, 22_817), 23_079),
    "LINK": (56_518, (2019, 9, 25, 13), 589, 550, {0: 8, 1: 53, 2: 263, 3: 13_942}, (14_259, 13_939), 14_111),
    "LTC": (99_565, (2013, 9, 14, 8), 10_395, 7_419, {0: 269, 1: 1_353, 2: 2_019, 3: 23_104}, (26_383, 23_057), 24_861),
    "SOL": (41_918, (2021, 6, 17, 15), 43, 26, {1: 4, 2: 9, 3: 10_472}, (10_483, 10_472), 10_480),
    "XRP": (77_653, (2017, 5, 18, 15), 92, 39, {0: 4, 1: 3, 2: 12, 3: 19_403}, (19_420, 19_403), 19_417),
}
# The union index of each stamp `_ffill_btc` fills, and its stamp.
_FILLS = [
    (6, datetime(2013, 9, 14, 8, tzinfo=UTC)),
    (26, datetime(2013, 9, 29, 4, tzinfo=UTC)),
    (160, datetime(2013, 11, 3, 8, tzinfo=UTC)),
    (235, datetime(2013, 11, 16, 4, tzinfo=UTC)),
    (9_340, datetime(2018, 1, 12, 0, tzinfo=UTC)),
    (9_341, datetime(2018, 1, 12, 16, tzinfo=UTC)),
]
# Records 48 and 49's arm A and benchmark, stored unrounded.
_ARM_A = {
    "arm_a_ann_sharpe_noc": 1.404998307684581,
    "arm_a_ann_sharpe_noc_decisive": 1.3716011675660076,
    "arm_a_max_drawdown": 0.2154323695072342,
    "turnover_a": 146.18534602048504,
    "arm_a_spot_drag_pct_yr": 0.07026650498259404,
    "benchmark_ann_sharpe_noc": 1.2128451567638199,
    "benchmark_ann_sharpe_noc_decisive": 1.2446890489958136,
}


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/60.parquet"),
    reason="the frozen ohlc-full set's hourly files are absent under data/",
)
def test_the_b1_hourly_exit_reads_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader = ObservedReader(_DATA_ROOT)
    h4_ts, h4_prices, hourly = subjects._b1_hourly_rv_reads(
        reader, "ohlc-full", None, None, False, subject="b1-hourly-channel-exits"
    )
    block = reader.block()
    assert compute_hash(block) == _BLOCK_HASH
    assert (len(block["ohlc-full"]["files"]), block["ohlc-full"]["rows"]) == (20, 855_305)
    assert (len(h4_ts), h4_ts[0], h4_ts[-1]) == (
        27_338,
        datetime(2013, 9, 10, 20, tzinfo=UTC),
        datetime(2026, 3, 31, 20, tzinfo=UTC),
    )
    assert sum(later - earlier != _H4 for earlier, later in zip(h4_ts, h4_ts[1:])) == 63
    assert [(k, h4_ts[k]) for k, p in enumerate(h4_prices["BTC"]) if p is None] == _FILLS

    # Its refusals are D4's: every hourly row clean, on the hour, increasing and inside a 240 bar of its asset.
    fed = _ffill_btc(h4_prices)
    interior = interior_closes_by_asset(fed, h4_prices, h4_ts, hourly)
    btc_own = {t: j for j, t in enumerate(h4_ts)}
    assert [interior["BTC"][btc_own[t]] for _, t in _FILLS] == [(None, None, None)] * 6

    for asset, (rows, first, missing, inside, present, (adjacent, adjacent_all), fourth) in _BASIS.items():
        stamps, closes = hourly[asset]
        by_hour = dict(zip(stamps, closes, strict=True))
        bars = [(k, t, p) for k, (t, p) in enumerate(zip(h4_ts, h4_prices[asset])) if p is not None]
        own = {t: j for j, t in enumerate(t for t, p in zip(h4_ts, fed[asset]) if p is not None)}
        held = [sum(c is not None for c in interior[asset][own[t]]) for _, t, _ in bars[1:]]
        pairs = [t1 for (k0, _, _), (k1, t1, _) in zip(bars, bars[1:]) if k1 == k0 + 1]
        assert (len(stamps), stamps[0], stamps[-1]) == (rows, datetime(*first, tzinfo=UTC), _LAST_HOUR), asset
        assert (int((_LAST_HOUR - stamps[0]) / _H1) + 1 - rows, 4 * len(bars) - rows) == (missing, inside), asset
        assert Counter(held) == present, asset
        assert (len(pairs), sum(None not in interior[asset][own[t]] for t in pairs)) == (adjacent, adjacent_all), asset
        # The seam: the hourly bar 3h in closes at the 240 close, and so does the last present hourly bar of every 240 bar.
        assert sum(t + 3 * _H1 in by_hour for _, t, _ in bars) == fourth, asset
        assert all([by_hour[t + i * _H1] for i in range(4) if t + i * _H1 in by_hour][-1:] == [p] for _, t, p in bars), asset


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/60.parquet"),
    reason="the frozen ohlc-full set's hourly files are absent under data/",
)
def test_the_b1_hourly_exit_arm_a_reproduces_records_48_and_49s_arm_a():
    reads = subjects._b1_hourly_rv_reads(
        ObservedReader(_DATA_ROOT), "ohlc-full", None, None, False, subject="b1-hourly-channel-exits"
    )
    inputs = subjects._b1_hourly_exit_inputs(reads)
    net_a = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.h4_ts) - 1

    assert n == 27_337
    assert {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
    } == _ARM_A
    assert all({key: _trials()[record]["metrics"][key] for key in _ARM_A} == _ARM_A for record in (48, 49))
```

  **Author's call**: the basis test reads the interior closes through `interior_closes_by_asset`, so the module's offsets and 4h floor are tied to the counts the spec measured, and its D4 refusals, none firing, prove on the frozen set what the spec measured of every hourly row; it reads no `count` column, which the reads half does not carry, and leaves out the spec's per-asset lowest year and the counts of intervals spanning more than 4h, disclosures no step reads. Arm A is checked bit for bit against records 48 and 49's unrounded figures, which the spec's measured basis quotes — an expectation only the run after the hash can check (D9), resting on four premises read before it: no commit since record 49's `bf515702a` touches a package or file an arm-A build reads (the spec's measured basis), `uv.lock`, `pyproject.toml` or `.python-version` — the paths Task 4 step 1 reads again; the reads' block is record 48's `dataset_hash` (the basis test above); records 48 and 49 store the same unrounded arm-A values (the arm-A test's last line); and `_b1_hourly_exit_inputs`' arm-A expression is `_b1_volume_inputs`' (Task 2 step 3). A failure at Task 4 step 4 is therefore the inputs half's, and the owner's question there; D9 (b)'s registry-precision check is the pre-flight's, Task 4 step 5.

- [ ] **Step 2: Run the basis test** — alone, by node id; the arm-A test is not run before Task 4 step 2.

Run: `mkdir -p .tmp/plan-00135 && uv run pytest tests/test_research_b1_hourly_exit_basis.py::test_the_b1_hourly_exit_reads_reproduce_the_measured_basis --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt`
Expected (Tasks 1 and 2 committed): pass — measured at 3.9 s against a transcription of Task 1 with `data/ohlc-full` linked; against the tree at this plan's commit, `ModuleNotFoundError: No module named 'cli.alpha.b1_exit'`. A skip is no pass: `data/ohlc-full` is linked in this worktree. At 10 s or more its node id joins `tests/slow-cases.txt` at its sorted place in this task's commit.

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b1_hourly_exit_basis.py`; the file's direct readers (`bash infra/scripts/consumers.sh --direct tests/test_research_b1_hourly_exit_basis.py`) with `-m "not data"`; the two tree walkers whose subject this file carries, its skip gates and its data mark, `uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt`; the basis test by node id; `tests/test_slow_cases.py` when the list changed; `uv run pre-commit run -a` until clean.

- [ ] **Step 4: Probe** — on the staged tree, in the probe worktree, with `data/ohlc-full` linked into it (`ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full .tmp/plan-00135/probe/data/ohlc-full`, `-n` so a link already there is refused, never followed into the canonical set) and unlinked before its removal: `--file cli/alpha/b1_exit.py`, control `s/^def interior_closes_by_asset(/def interior_closes_by_asset_gone(/` (the test module imports it), mutation the hourly bar opening 0 hours into its 4h bar stored as `None`, against `tests/test_research_b1_hourly_exit_basis.py::test_the_b1_hourly_exit_reads_reproduce_the_measured_basis`, expected `KILLED` — when Step 2 timed it under 10 s; a listed basis test is not probed, its commit recording `probe skipped: slow case`. The arm-A test cannot run before the hash: this commit names it as unprobed before the hash, and Task 4 step 4 times it.

- [ ] **Step 5: Commit**

```bash
git commit -F - <<'EOF'
test(research): B1 trial 5's reads and interior closes against the measured basis, and arm A against records 48 and 49 after the hash

<the basis test's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<the basis test's infra/scripts/mutate-probe.sh command, then its verdict line — or probe skipped: slow case, by node id>
The basis test reads data/ohlc-full: re-run it, and its probe, with the frozen set linked into the worktree (ln -sn) and unlinked before the worktree's removal; unlinked, it skips and the probe reads SURVIVED.
The arm-A test runs only after the spec's hash (D9): its probe, or its slow-case record, is Task 5's commit's.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: The scratch** — `git worktree list` names no probe worktree; `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the canonical `ohlc-full` still there.

- [ ] **Step 7: The reads over Tasks 1–3** — the trio over `<Task 1's commit>^..HEAD`, as CLAUDE.md orders it: `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two (Global Constraints' reads line); every dispatch carries the hash rule (Global Constraints) — in a `review` or `re-review` `drive` as one sentence in words, since a drive names no path: nothing runs over the real data before the spec's hash but the measured-basis case, re-run with the frozen full set linked into the reader's worktree and unlinked before its removal, since unlinked the case skips and its probe reads `SURVIVED`; each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

______________________________________________________________________

### Task 4: the run, through spec 00133's trial-attempts log (D9, D12)

**Files:** `docs/reference/trial-registry.jsonl` (or, on a stop, `docs/reference/reading-ledger.jsonl`), appended by the command and committed in Task 5; scratch under `.tmp/plan-00135/`.

**Interfaces:**
- Consumes: `cli/research/command.py`'s `eval_subject` register path as Task 2 names it; the trial-attempts log `.local/trial-attempts.jsonl` in the main checkout, its row `60c9f39c37ec81b4a53396218b690304 zcrypto-ops` in `docs/reference/trial-attempt-logs.txt`; the record's `attempt` block (`id`, `begin`, `log`, `absorbs`, `counted`); this plan's Task 2 subjects and Task 3 tests.
- Produces: one appended registry record (or ledger reading), checked; the pre-flight's output and the run's output under `.tmp/plan-00135/`.

- [ ] **Step 1: The gate** — each its own call, each read before the next:
  - The reads over Tasks 1–3 (Task 3 step 7) have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names in its report> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00135-b1-hourly-channel-exits-design.md` exits 0; with no report naming a tip, stop: the reads come first. A fix or a merge of develop changes it — a read of that diff comes first, its `re-review` within the branch's two, and this check then names its tip.
  - Arm A's code path since record 49's run: `git log --oneline bf515702a748ecba29d7405e31fa2d5fa9438fb3..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry/observed.py cli/ohlc uv.lock pyproject.toml .python-version` lists Tasks 1 and 2's commits and their fixes alone; any other commit is named in the task report, step 4's arm-A test deciding whether it moved arm A.

- [ ] **Step 2: D12 step 1, the spec hash** — `sha256sum docs/specs/00135-b1-hourly-channel-exits-design.md`; its value, pasted from that call, is the `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.

- [ ] **Step 3: D12 step 2, the develop check** — `git fetch origin develop`, then `git diff --quiet origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0, so an append chains onto develop's last line; if not, develop is merged first (`git merge --no-edit origin/develop`, alone, then step 1's checks again). It runs again immediately before step 6's `--register` and before a stop's `--reading`; a failure there is the owner's question before any append.

- [ ] **Step 4: The held-back data tests** (D9's order: after the hash, before the pre-flight's anchors) — `uv run pytest tests/test_research_b1_hourly_exit_basis.py --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00135/pt` reads `2 passed`, never a skip; then `-m data` over the direct readers of `cli/research/subjects.py` and `cli/alpha/b1_exit.py`, in parts, each with `--deselect 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-1]' --deselect 'tests/test_research_b2_basis.py::test_the_b2_inputs_reproduce_the_measured_basis_and_arm_a_is_the_builders_a2_sleeve'` — both read `ohlc-rolling` and `derivatives-funding`, which Global Constraints keep unlinked here, the replay failing on their absence and the basis case skipping — the skip count read, `tests/test_b1_records_reproduce.py::test_the_b1_subject_reproduces_its_record[record-46]` among them passed, never skipped, record 45's case the one skip (it needs `data/ohlc-15m`, unlinked here too); the PR body drops the three explicitly (Task 5 step 9). A failure among them is the owner's question before the pre-flight. The arm-A test's own time is noted for Task 5: at 10 s or more it is slow-listed (Task 5 step 3), under 10 s probed (Task 5 step 7).

- [ ] **Step 5: D12 step 3, the pre-flight** — `mkdir -p .tmp/plan-00135 && uv run zcrypto research eval --subject b1-hourly-channel-exits-preflight --dataset ohlc-full > .tmp/plan-00135/preflight.out 2>&1` — a plain eval of a subject with no rule, which spec 00133 D7 admits — then the check, which reads the block, then the seven anchors, then `passes`, then the engagement, and exits 1 on a stop:

```
uv run python - <<'EOF'
import json, sys
from pathlib import Path
from cli.registry.record import compute_hash
out = Path(".tmp/plan-00135/preflight.out").read_text(); run = json.JSONDecoder().raw_decode(out[out.index("{"):])[0]; m = run["metrics"]
block = compute_hash(run["datasets"]); print("block", block)
if block != "8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1": sys.exit("the inputs' block differs from the spec's")
anchors = {"arm_a_ann_sharpe_noc": (1.405, 4), "arm_a_ann_sharpe_noc_decisive": (1.3716, 4), "arm_a_max_drawdown": (0.2154, 4),
           "arm_a_spot_drag_pct_yr": (0.0703, 4), "benchmark_ann_sharpe_noc": (1.2128, 4), "benchmark_ann_sharpe_noc_decisive": (1.2447, 4),
           "turnover_a": (146.19, 2)}
off = {k: m[k] for k, (v, d) in anchors.items() if round(m[k], d) != v}
if off: sys.exit(f"arm A does not reproduce record 45's arm A: {off}")
print({k: m[k] for k in ("dsr", "dsr_pass", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes", "arm_a_var_trials")})
if m["passes"] != 1: sys.exit("arm A fails its bar")
years = {}
for by_asset in m["exit_events_per_year"].values():
    for by_lookback in by_asset.values():
        for counts in by_lookback.values():
            for year, count in counts.items():
                years[year] = [a + b for a, b in zip(years.get(year, [0, 0, 0]), count)]
print("exit_events", m["exit_events"], "early", m["exit_events_early"], "false", m["exit_events_false"], "share_false", m["share_false"])
print("per bar-start year [events, early, false]", dict(sorted(years.items())))
print("hourly_closes_directions_differ", m["hourly_closes_directions_differ"], m["hourly_closes_directions_differ_per_year"])
sys.exit(0 if m["hourly_closes_directions_differ"] > 0 else "no direction differs at any hourly close: a dead knob")
EOF
```

  Expected now: it cannot run (no subject) — it runs at this step alone. A block that differs, an anchor off, `passes` 0 or `hourly_closes_directions_differ` 0 is D9's or D8's instrument finding — stop: no run, no verdict, the trial unspent. The stop is kept as a reading, after step 3's check: `uv run zcrypto research eval --subject b1-hourly-channel-exits-preflight --dataset ohlc-full --reading --iteration iter-179 --spec-hash <step 2's sha256> --notes "<what failed, quoted from the check's output; no verdict, the trial unspent>"`; Task 5 records it. A refused build is the command's own refusal of the subject's build: the output ends in `<subject> over the full history: …`, a refusal the build raises, or `<subject> over the full history of ohlc-full: … (<class> raised at …)`, an evaluation error the command catches, and holds no `Traceback (most recent call last):`. A pre-flight whose build refuses so — D8's no-exit refusal among them — prints no metrics: the check is not run and no reading is kept, the `--reading` re-run refusing alike before any append (D9), and Task 5 runs its arm for a refused build. Any other exit 1 of the eval — a traceback, or a refusal before the build such as `dataset 'ohlc-full' is absent: …` where the link is missing — is a code or environment fault, never D9's instrument finding, and the owner's question before step 6.

- [ ] **Step 6: D12 step 4, the trial** — one run, by the owner or on their word, after step 3's check: `uv run zcrypto research eval --subject b1-hourly-channel-exits --dataset ohlc-full --register --iteration iter-179 --family B1 --n-trials 5 --variant B1-hourly-exit-a2eq-v1 --spec-hash <step 2's sha256> --notes "<below>" > .tmp/plan-00135/trial5.out 2>&1`, then `cat .tmp/plan-00135/trial5.out`. No `--verdict` and no plain eval, before or after (D12). The notes, written before the run, name only what is fixed before it: `subject b1-hourly-channel-exits over ohlc-full, full history, no as-of; arm B the A2 4h ensemble with each lookback's long state also set to -1 at the first hourly close inside a 4h interval that breaches the level at which that interval's 4h close would be a new channel low, re-entering on the 4h rule alone, on arm A's weights and vol scalar, each hourly trade charged 0.006 per side; arm A the same ensemble unchanged, both built in the run; the hypothesis: arm B has a higher mean net-of-cost return than arm A at 0.006 per side (SPA p < 0.05, full window) and a lower maximum drawdown; var_trials the sample variance of records 45, 46, 48 and 49's registered per-period Sharpes 0.02374, 0.02959, 0.030191886721210086 and 0.03028127927651177 and arm B's, n_trials 5, the DSR leg binding; pre-flight: block 8216f4db…, arm A <the seven anchors>, passes 1, exit_events <n> (early <e>, false <f>), hourly_closes_directions_differ <d>; park variants, pre-registered: on the matrix's third row the check at 15m, on its second the block-sensitivity finding; the matrix pre-registered by the spec's sha256 <step 2's value>`. A refusal from the count — an attempt in B1 that never landed, or bucket B spent — comes before the fit or after the print, naming each orphan the count counts or the bucket's spent figure, and the trial goes back to the owner through T0022 (D12): Task 5 runs its refusal arm, with no record and no reading. A stop by the rule writes a reading carrying its attempt, which counts 0. A refused build, as step 5 defines it, ends its attempt failed, which counts 0 (D9): no record and no reading, and Task 5 runs its arm for it once `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b1-hourly-channel-exits"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'` prints the attempt's id beside a list holding its `failed` text, since an exception the command does not catch writes no `end` line. A traceback, a refusal other than the count's and step 5's, or `open` printed by that check is a code or environment fault, never D9's instrument finding, and the owner's question before Task 5: an open attempt counts against B1 and bucket B until a run with the same arguments and spec hash absorbs it (spec 00133 D3).

- [ ] **Step 7: The record's checks** — on a record, each failure the owner's question before Task 5:

```
uv run python - <<'EOF'
import json, sys
from pathlib import Path
from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
SPEC_HASH = "<step 2's sha256>"
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1]); m = r["metrics"]
out = Path(".tmp/plan-00135/trial5.out").read_text(); printed = json.JSONDecoder().raw_decode(out[out.index("{"):])[0]["metrics"]
subject = SUBJECTS["b1-hourly-channel-exits"]
checks = {
    "spec_hash": r["spec_hash"] == SPEC_HASH,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == "8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1",
    "invocation": {k: r["invocation"][k] for k in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
    == {"subject": "b1-hourly-channel-exits", "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"]) == ("B1", 5, "B1-hourly-exit-a2eq-v1", "iter-179", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
EOF
```

  Expected now: it cannot run — `.tmp/plan-00135/trial5.out` does not exist. It reads the registry's last line, so it runs only after step 6 appended one. `printed` is the first JSON object the run printed, the text after it left unread. `counted` is printed, never checked: a non-empty one, an orphan the count admitted elsewhere in bucket B, is no failure of the run — Task 5's header and T0016's line name it — and goes in the report. On a stop by the rule, the ledger's last line is checked instead: its subject `b1-hourly-channel-exits`, its outcome the `no_verdict` text, its `attempt` non-null, its `spec_hash` step 2's.

No commit: the appended line lands in Task 5's commit, with the decisions-log header that names it and the literal that pins its subject — `tests/test_decisions_log_ties.py::test_the_committed_decisions_logs_tie_every_verdict_to_its_record` and `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` hold only over the three together.

______________________________________________________________________

### Task 5: the verdict — the record, the decisions log, T0022, T0016 and on an adopt T0123 and the engine-design topic (D12, D13)

**Files:**
- Modify: `docs/reference/trial-registry.jsonl` (appended by Task 4), `tests/test_trial_registry_provenance.py`, `docs/research/10.phase4-decisions.md`, `docs/open-topics/T0022-b1-intraday-seasonality-family.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/slow-cases.txt` (when Task 4 step 4 says so); on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and the new engine-design topic; on a stop `docs/reference/reading-ledger.jsonl` in the registry's place and no literal; on a refusal from the count, T0022 and the index, and T0016 when the refusal came after the print; on a refused build, the decisions log, T0022 and the index; `docs/reference/change-index.md` in step 9's own commit

**Interfaces:**
- Consumes: `tests/test_trial_registry_provenance.py`'s `LANDED_N_TRIALS: dict[str, int] = {"b1-hourly-rv": 3, "b1-volume-confirmation": 4}` and `test_each_landed_subjects_n_trials_is_frozen_at_its_literal`; `tests/test_decisions_log_ties.py`'s `(registry trial N` and `(attempts counted: <log8>#<id>, …)` ties; this plan's Task 4 record, checked.
- Produces: the records commit and step 9's change-index row commit.

On a refusal from the count (Task 4 step 6) there is no record and no reading: steps 1, 4, 5, 6, 8 and 9 run, step 4 on its refusal arm, step 6 staging T0022 and the index — and T0016 when the refusal came after the print, `.tmp/plan-00135/trial5.out` holding the run's printed metrics before it — under `docs(open-topics): B1 trial 5 refused by the count; T0022 holds the refusal for the owner`.

On a refused build, as Task 4 step 5 defines it and, under `--register`, step 6's attempt check confirms, there is no record and no reading: Task 5 runs its stop arm with the refusal line, quoted from `.tmp/plan-00135/preflight.out` or `.tmp/plan-00135/trial5.out`, where a stop quotes the check or the record — the decisions-log header `[iter-179] B1 trial 5 — instrument finding, the run refused; the trial unspent`, which names no verdict and so takes no tie; T0022's findings the refusal line; no ledger staged and no replay case; the subject line `docs(research): B1 trial 5 — instrument finding, the run refused; no trial spent, the shared B budget at 21`.

- [ ] **Step 1: The PR's title** — `feat(research): iter-179 — B1 trial 5: hourly channel exits on A2`, 65 characters, under `open-pr`'s cap of 72. The PR is created in step 9, after step 8's commit: the consumer union `open-pr` runs before the first push then reads the record committed, never an uncommitted line, and the change-index row is committed before the read that covers it.

- [ ] **Step 2: The decisions-log entry**, at the end of the `[iter-179]` entries, written with `iteration-closeout` loaded. The matrix is printed from the spec the record pins, `sed -n '/^| Kill bar/,/^Every quantity/p' docs/specs/00135-b1-hourly-channel-exits-design.md`, and the row read off the record's stored keys beside its stored verdict. The header: `[iter-179] Verdict — B1 trial 5 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B1 n=5)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry (spec 00133 D10); its text to its first `. ` holds no verdict word but its own. The body: the row that fired with the five keys the matrix reads (`passes`, `spa_p_decisive_b102_s42`, `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `max_drawdown_reduction_pct`), unrounded, and `max_drawdown` beside `arm_a_max_drawdown`; `var_trials` and its five inputs, `n_trials` 5, the DSR leg (`dsr_corrected`, `dsr_pass`); the pre-flight's block, anchors and `passes`, read from `.tmp/plan-00135/preflight.out`; the engagement proof — `exit_events`, `exit_events_early`, `exit_events_false`, `share_false`, `hourly_closes_directions_differ`, the per-year spread, `stamps_positions_differ`, `turnover_a`, `turnover_b`, `turnover_b_intra`, `turnover_reduction_pct`; on a park its variant (the third row: the check at 15m; the second: the block-sensitivity finding), each a new trial of the shared budget whose adoption path goes to the owner; on an adopt D13's path in its order. On a stop the entry is `[iter-179] B1 trial 5 — instrument finding, the trial unspent (reading <its id>)`, naming what failed, quoted from the check or the record.

- [ ] **Step 3: The landed subject's literal** — on a record only: `LANDED_N_TRIALS` becomes `{"b1-hourly-rv": 3, "b1-volume-confirmation": 4, "b1-hourly-channel-exits": 5}` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts becomes the same dict — the subject's first landed record adds its row in the PR that lands it. `tests/test_research_b1_hourly_exit_basis.py::test_the_b1_hourly_exit_arm_a_reproduces_records_48_and_49s_arm_a` joins `tests/slow-cases.txt` at its sorted place, recorded `probe skipped: slow case`, when Task 4 step 4 timed it at 10 s or more.

- [ ] **Step 4: The topics**, per `topic-ops`. T0022's findings take trial 5 — its record id, verdict, the row that fired, `var_trials`, the engagement figures — or, on a stop, the instrument finding and its reading id. Its `ripe_when`, an activity, is rewritten for what remains, with a check that prints at least 1 once it happens and nothing when this step commits it, run then and its output read, shown matching a sample header in `iteration-closeout`'s form:
  - reject — with it the survey's three candidates are spent (D13): `an activity: the owner picks B1's next step after trial 5's reject — a park variant of trial 3, or closing the family as attributed out — recorded in the decisions log; check: git grep -c -E '^\[iter-[0-9]+\] B1.s next step after trial 5' -- docs/research/10.phase4-decisions.md prints at least 1`;
  - park: the same activity after trial 5's park, its variant (on the third row the check at 15m; on the second the block-sensitivity finding) a new trial of the shared budget and its adoption path the owner's to rule, with the same check;
  - adopt: `an activity: the P1 combination trial over record 47's book carrying trial 5's arm B is picked for an iteration; check: git grep -c -E '^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book' -- docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md prints at least 1`, the second log the one `iteration-closeout` routes a combination of sleeves to, `[^.]*` holding the match to an entry's header, which ends at its first `. `; T0123's `ripe_when` gains `— registry trial <N>, B1 trial 5's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries it adopts`, written in this commit so no tree holds the adopt without it (D13); and the engine-design topic is registered through `topic-ops` — the next free serial, its queue line through `zcrypto-marco` as `topic-ops` prescribes — for an intra-cycle exit path and a 60 grid in the engine's store, the engine's cycle orders ending by about B+3h47 after their boundary and its store holding the 1440 and 240 grids alone (`cli/engine/executor.py`'s `_SUBMISSION_WINDOW`, `cli/engine/store.py`'s `GRID_INTERVALS`), its `ripe_when` the evaluation statement D13's **Author's call** fixes: `an evaluation statement: the P1 combination trial over record 47's book that carries B1 trial 5's arm B (registry trial <N>) reaches ADOPT in docs/reference/trial-registry.jsonl`;
  - stop: `an activity: the owner decides B1's next step after trial 5's instrument finding, recorded in the decisions log; check: git grep -c -E '^\[iter-[0-9]+\] B1.s next step after trial 5.s instrument finding' -- docs/research/10.phase4-decisions.md prints at least 1`;
  - refusal from the count: T0022's findings take the refusal as `.tmp/plan-00135/trial5.out` printed it, each orphan or the spent bucket it named, and, when it came after the print, the metrics printed before it and each named orphan's metrics as its `end` line in the trial-attempts log holds them, looks no record carries; `an activity: the owner rules on B1's fifth trial after the count refused it — a new subject under a new spec declaring the count its orphans need, or bucket B's spent budget — recorded in the decisions log; check: git grep -c -E '^\[iter-[0-9]+\] B1 trial 5 after the count.s refusal' -- docs/research/10.phase4-decisions.md prints at least 1`; T0016 unchanged on a refusal before the fit, and after the print its budget line counts what the refusal counted, named on that line.
  T0022's next steps say the same. On a verdict, T0016's budget line reads `B1 spent 5, 20 remain` — less one more for each orphan the record's `attempt.counted` lists, named on that line — and its B1 line under `## Done so far` names trial 5 (iter-179, spec/plan `00135`, registry trial <N>) and its verdict; on a stop T0016 is unchanged, 21 remaining. On any verdict but an adopt T0123 is untouched. `uv run python infra/scripts/topics-index.py` re-renders the index.

- [ ] **Step 5: Tests and gate** — the direct readers of each path the commit stages, run as the Global Constraints run them (`consumers.sh --direct`, `-m "not slow and not data"`, a mount-reading case deselected by node id and named), `tests/test_decisions_log_ties.py` among them, and `tests/test_slow_cases.py` when the list changed, pass; `uv run pre-commit run -a` until clean, its rewrites staged.

- [ ] **Step 6: Stage** — `git add docs/reference/trial-registry.jsonl tests/test_trial_registry_provenance.py docs/research/10.phase4-decisions.md docs/open-topics/T0022-b1-intraday-seasonality-family.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md`, and, as the outcome makes them, `tests/slow-cases.txt`, `docs/open-topics/T0123-sleeve-promotion-path.md` and the new topic's file; on a stop the ledger in the registry's place.

- [ ] **Step 7: The replay case and the probes, on the staged tree** — in the probe worktree (Global Constraints' probe line), `data/ohlc-full` linked into it by Task 3 step 4's `ln -sn` and unlinked before its removal: `uv run pytest tests/test_registry_replay.py -k 'trial-<its id>' -q -p no:cacheprovider --basetemp=.tmp/pt` passes (on a stop `-k 'reading-<its id>'`) — run there because the case fails on any uncommitted change under the registry and the ledger — its result line for the message, a difference the owner's question before the commit; on a record, the literal's probe, `--file cli/research/subjects.py`, control `s/^def _b2_verdict(/def _b2_verdict_gone(/`, mutation `s/^_B1_EXIT_N_TRIALS = 5/_B1_EXIT_N_TRIALS = 6/`, against `tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal`, expected `KILLED`; when Task 4 step 4 timed it under 10 s, the arm-A data test's probe, `--file cli/research/subjects.py`, control `s/^def _b1_hourly_exit_inputs(/def _b1_hourly_exit_inputs_gone(/`, mutation within `/^def _b1_hourly_exit_inputs(/,/^def /` `in _B1_A2_ARMS:` made `in _B1_A2_ARMS[:1]:`, against `tests/test_research_b1_hourly_exit_basis.py::test_the_b1_hourly_exit_arm_a_reproduces_records_48_and_49s_arm_a`, expected `KILLED`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
docs(research): B1 trial 5 registered — <verdict>; T0022 and T0016 after it, the shared B budget at <the remaining figure step 4 wrote on T0016's budget line>

<the tie and provenance tests' pytest result line, and the replay case's, pasted from their runs over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<the literal's infra/scripts/mutate-probe.sh command, then its verdict line; the arm-A test's, or probe skipped: slow case with its node id>
The replay case and the arm-A test read data/ohlc-full: re-run them, and the arm-A probe, with the frozen set linked into the worktree (ln -sn) and unlinked before the worktree's removal; unlinked, they skip, so neither their result lines nor the probe's verdict reproduce.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

  On a stop the subject line is `docs(research): B1 trial 5 — instrument finding, kept as reading <id>; no trial spent, the shared B budget at 21`, with no literal and no literal probe.

- [ ] **Step 9: The read, the PR and the merge** — the change-index row through `open-pr`'s Step 4, step 1's title, its own commit; then the `pre-review` of this task's commits, then the read of the delta from the tip the last read covered — `review` over `<that tip>..HEAD`, since the commit adds files outside that read's range, and `re-review` over a fix of it, within the branch's two (Global Constraints' reads line), each `drive` carrying one sentence in words: the data-gated cases the messages record run with the frozen full set linked into the reader's worktree and unlinked before its removal, since unlinked they skip and neither their result lines nor a probe's verdict reproduce — then the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR created through `open-pr`, its body: the verdict, the instrument finding or the count's refusal, every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of `tests/test_b1_records_reproduce.py::test_the_b1_subject_reproduces_its_record[record-45]`, `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-1]` and `tests/test_research_b2_basis.py::test_the_b2_inputs_reproduce_the_measured_basis_and_arm_a_is_the_builders_a2_sleeve` — the first reads `data/ohlc-15m`, the other two `data/ohlc-rolling` and `data/derivatives-funding`, which Global Constraints keep unlinked here, and D1 changes no existing function of `cli/research/subjects.py` — and the read line naming the tip the delta's read covered, `merge-pr`'s gate refusing any other. Merged on the owner's word through `merge-pr`; before it, `git status --short --ignored` is read, `.tmp/plan-00135` removed, `unlink data/ohlc-full`, and `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the canonical `ohlc-full` still there. Decisions log: the verdict entry above, written after the run.
