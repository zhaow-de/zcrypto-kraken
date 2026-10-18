# B1 trial 4 — the volume norm, the entry gate, the two subjects and the gated run — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next. Execution is subagent-driven — the author's call, made unattended, nobody asked. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (Global Constraints, the probe line).

**Goal:** the module `cli/alpha/b1_volume.py` (the hour-of-week volume norm, the confirmed A2 state machine, arm B's positions on arm A's weights and vol scalar, the engagement counts), the ruled subject `b1-volume-confirmation` and its evaluate-only pre-flight twin `b1-volume-confirmation-preflight` built on spec 00133's `Subject.family` and `Subject.n_trials`, and B1's trial 4 registered once spec 00133 has merged, its verdict in the registry, the decisions log, T0022 and T0016.

**Architecture:** the module holds pure functions over lists, as `cli/alpha/b1_rv.py` does, importing `cli.alpha.a1`'s `_map_to_union_index` and `_validate_prices_by_asset`, `cli.alpha.a2`'s `A2Config` and `cli.features.channel_position`, editing none of them. The subjects sit in `cli/research/subjects.py` after trial 3's and reuse its B1 literals, `_capturing_union`, `_b1_refuse_window`, `_b2_over`, `net_of_cost`, `book_turnover`, `benchmark_4h_net_of_cost`, `calendar_year_slices`, `a1_kill_bar`, `reality_check_pvalue` and `net_of_cost_verdict`; the build has spec D11's three halves — `_b1_volume_reads` (reads only, all the basis test calls), `_b1_volume_inputs` (arm A, the confirmations and both arms' directions, no position or return of arm B) and each subject's metrics. The branch is rebased onto spec 00133's branch at its Task 6 (D12's "Where the build sits"), builds there, takes develop back once spec 00133 merges, and runs the trial in its one pull request.

**Tech Stack:** Python 3.14 through uv; polars for the parquet reads; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00134-b1-volume-confirmation-design.md` — binding; D1–D13 are cited by name, and the values below are copied from it verbatim. Spec 00133 (`docs/specs/00133-t0222-trial-attempts-design.md`) and plan 00133 (`docs/plans/00133-trial-attempts.md`), on `research/00133-t0222-abandoned-trials`, give the interfaces this plan consumes, named as plan 00133's Interfaces blocks name them. **Iteration:** iter-178. **Topic:** T0022 under T0016. **Branch:** `research/iter-178-b1-volume-confirmation`, worktree `.claude/worktrees/b1-trial4`. A choice this plan makes that the spec leaves open is marked **Author's call**.

## Global Constraints

- Arm A is records 45, 46 and 48's (D1): `fed = _ffill_btc(h4_prices)`; for each `(lookbacks, target_vol)` in `_B1_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))`, `a2_book_returns(fed, config=A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=_B1_LOOKBACK, basket_lookback=_B1_LOOKBACK, periods_per_year=PPY_4H))`; arm A the per-asset `statistics.mean` of the three `asset_positions` at every return index. `_B1_COST_PER_SIDE`, `_B1_A2_ARMS`, `_B1_LOOKBACK`, `_B1_DECISIVE_START`, `_B1_N_RESAMPLES`, `_B1_FROM_2016` are reused, never restated.
- Arm B (D1): each arm's asset positions `weights_a[k].get(a, 0.0) * (directions_b[a][k] or 0.0) * vt_a[k]`, `weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)` one path for the three arms, `directions_b` that arm's confirmed directions, `vt_a` that arm's `a2_book_returns(...)["vol_target_positions"]`; averaged per asset per stamp as arm A is.
- The gate (D2): an entry event at own bar `j` of lookback `w` is a bar where the channel position reaches the band (1.0) while that lookback's state on arm B's own machine is not already +1; accepted when `confirm[j]` is true, setting +1; rejected otherwise, leaving −1 or the initial 0; `cp[j] <= -band` sets −1 whatever `confirm[j]` says; a config with `short="on"` is refused (`AlphaError`); `confirm_by_asset[asset]` is one flag per own bar, shared by every lookback and every arm.
- The norm (D3): accept when `volume[k] >= L[k] * S[c(k)]`, in float, `>=` exactly, no tolerance; `L[k]` the `statistics.median` of the asset's 180 bars before bar `k`, bar `k` excluded; `c(k) = (b.hour, b.weekday())`, `b = ts[k] + timedelta(hours=4)`; `S[c]` the `statistics.median` of `volume[j] / L[j]` over the cell's earlier bars that have their own level, held at 1 while the cell has fewer than 100 such observations; called with `lookback=_B1_LOOKBACK` (180) and `min_cell_obs=100`.
- Eligibility (D4): the gate runs on each asset's own bars, the union stamps where `fed[a]` holds a price; a BTC fill carries no volume, adds nothing to a level's window or a cell's observations and does not advance the prior-bar count; the warm-up comes first — fewer than 180 prior bars, accepted, a fill among them — and past it a fill never confirms.
- Refusals, never drops (D4, `AlphaError` naming the asset and the stamp): a volume that is not a finite number above 0; a volume present where the close is absent, or absent where the close is present at a stamp other than a BTC fill; stamps not strictly increasing or tz-naive; `stamps` and `volumes` of unequal length; `lookback` or `min_cell_obs` not an int of at least 1.
- Data (D5): `--dataset ohlc-full`, no `--window`, no `--as-of`; the inputs' block `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69` over the ten 240 files, 173,373 rows, span 2013-09-10 20:00 → 2026-03-31 20:00; the union 27,338 stamps, 27,337 return indices; intervals `(240,)`; an `--as-of` read refused with a `SubjectError` before any read; a 240 file polars cannot read, or one with no `volume` column, a `SubjectError` naming `<dataset>/<A>/EUR/240.parquet`.
- Costing (D6): `returns = {a: _asset_returns(fed[a])}`; each arm's net through `net_of_cost(arm, returns, cost_per_side=_B1_COST_PER_SIDE)`, the stressed series at `1.5 * _B1_COST_PER_SIDE`; the benchmark `benchmark_4h_net_of_cost(h4_prices, cost_per_side=_B1_COST_PER_SIDE)` on the raw union prices; the slices `calendar_year_slices(series, h4_ts)`; the from-2016 cut at the first `k` with `h4_ts[k] >= 2016-01-01T00:00Z`; per-year engagement keyed by the bar-start year (D5, D8).
- Dispersion (D7): `per_period_sharpe_4h = sharpe(net_b)`, unannualised; `var_trials = statistics.variance([0.02374, 0.02959, 0.030191886721210086, per_period_sharpe_4h])`; `arm_a_var_trials` the same with `sharpe(net_a)` in arm B's place; held as `_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES = (*_B1_RECORDED_PER_PERIOD_SHARPES, 0.030191886721210086)`.
- The bars (D10, D11): arm B's `a1_kill_bar(net_b, bench, n_trials=4, var_trials=var_trials, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`; arm A's the same with `net_a`, arm A's ×1.5 series and slices and `arm_a_var_trials`; every `a1_kill_bar` call passes `n_trials=_B1_VOLUME_N_TRIALS` (4). The SPA grid, blocks {30, 102} × seeds {42, 7, 1234}: (30, 42) the headline's `spa_p_value`, the other five `reality_check_pvalue([[net_b[k] - bench[k]] for k in range(1380, n)], mean_block=block, n_resamples=2000, seed=seed)["p_value"]`. The head-to-heads `net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=2000)` over the full window and over `[k16:]`.
- The rule is spec D10's code block verbatim, `_b1_volume_confirmation_verdict`; every quantity it reads is a stored key read unrounded; an exact turnover tie rejects.
- The record (D11): family `B1`, `n_trials_in_family` 4, variant `B1-volume-confirm-a2eq-v1`, iteration `iter-178`, seeds (42, 7, 1234), no `--verdict` (D12).
- The subjects (D11): `b1-volume-confirmation`, 43 metric keys, with the rule, `family="B1"`, `n_trials=_B1_VOLUME_N_TRIALS`, and `no_verdict` "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every stamp; no verdict, the trial unspent"; `b1-volume-confirmation-preflight`, 24 keys, seeds (42,), no rule, family or count; both declaring `spec="docs/specs/00134-b1-volume-confirmation-design.md"`.
- The hash rule (D8, D9): no position, return or direction of either arm, no confirmation flag and no bar is computed over the trial's data before Task 5 step 2 takes the spec's sha256. Tasks 2–4 meet `data/ohlc-full` only through `_b1_volume_reads` in `tests/test_research_b1_volume_basis.py::test_the_b1_volume_reads_reproduce_the_measured_basis`; until Task 5 step 2 every other run adds `-m "not data"` and that test runs by node id. No reader, reviewer or plan-review dispatch runs either subject, `_b1_volume_inputs`, the module's functions or a transcription of them over the real set before then; every read's dispatch carries this rule. No return of arm B is computed over the trial's data before Task 5 step 6's register run, the first step to compute one; Task 6 step 7's replay of the landed record recomputes it.
- The gate on spec 00133 (D12): neither subject runs over the trial's data before spec 00133 has merged into develop and develop into this branch; there is no plain eval of `b1-volume-confirmation`, before or after the register run.
- No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b1.py`, `cli/alpha/b1_rv.py`, `cli/alpha/b2.py`, `cli/features/*`, `cli/portfolio/*`, the engine or any adopted artifact (D1). Code citations name a function, never a line: the rebase moves `cli/research/subjects.py`'s lines.
- Never edit `docs/specs/00134-b1-volume-confirmation-design.md` after Task 5 step 2, nor `docs/specs/00045-b1-seasonality-conditioning-design.md` or `docs/specs/00132-b1-hourly-rv-weights-design.md`, whose hashes records pin; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading` over a committed file, except where Task 5 names it. Never `git stash`; a state-changing git command runs alone.
- Data: `data/ohlc-full` alone, a read-only link to the canonical set, never written under; never `data/ohlc-holdout-*`, never `/mnt/zhao-crypto/`; never ssh, a fleet host, `kraken-cli`, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`.
- No operator-read surface — `README.md`, a `SubjectError` or `AlphaError` message, the `no_verdict` text — carries `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` or `D<N>` (`tests/test_internal_terms_not_operator_visible.py`); comments may, under CLAUDE.md's comment rule.
- Every pytest run is `mkdir -p .tmp/plan-00134 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt` (or a file, or `-k`), split into parts each under 600 s, nothing backgrounded; before each commit the direct readers of each changed path run (`bash infra/scripts/consumers.sh --direct <paths>`), never the full suite, which is CI's; a case reading a mount, a holdout set or a set not linked here is deselected by node id and named in the task report.
- Probes: the tier is `full` — measured, `uv run python infra/scripts/tier.py --paths cli/alpha/b1_volume.py cli/research/subjects.py tests/test_research_command.py tests/test_trial_registry_provenance.py docs/reference/trial-registry.jsonl` prints `tier: full`, the two code paths alone `light` (**Author's call**: the tier of the commits' test paths decides, so each task reads `uv run python infra/scripts/tier.py <base>..<head>` over its commit and probes at what it prints). On `full` each new guard — a test function, and each refusal case — is proven through its own case with `infra/scripts/mutate-probe.sh --file <F> --control '<sed>' --mutation '<sed>' -- uv run pytest <node id> -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt` after its task's commit (the script refuses a dirty tree), expected `KILLED`; the mutation substitutes and never deletes a line (`if <cond>:` becomes `if False:`, a call `None`), its site a pattern whose `grep -c` reads 1 or an address whose range holds one, dry-run first through `sed '<expr>' <F> | uv run python -c 'import ast,sys; ast.parse(sys.stdin.read())'`; never through a case `tests/slow-cases.txt` lists — each new case whose own time is 10 s or more (`--durations=0`) joins that list at its sorted place in its task's commit, and the commit records `probe skipped: slow case` naming it. Each verdict line goes in the PR body, naming `infra/scripts/mutate-probe.sh`.
- Commits: one per task that changes the tree (Task 1 adds none; Task 5's record lands in Task 6's commit); never an amend; `uv run pre-commit run -a` re-run until clean, staging what it rewrote by explicit path; the message says what changed and carries the test command's result line, pasted from its run, and ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` — the executing model, so an implementer on another model names its own — and the executing session's `Claude-Session:` line.
- The reads: the trio over Tasks 2–4's range (`pre-review`, `review`, `re-review`, as CLAUDE.md orders them; Task 4 step 5) closes with no open Critical or Important before Task 5 step 2, and nothing the run executes or the record pins changes from that read to the registration unless a read of the change follows (Task 5 step 1); Task 6's commit takes its own `pre-review`, then the read of the delta from the tip the last read covered (Task 6 step 8) before the push that carries it; every `re-review` of these reads — over a fix of Tasks 2–4's read, of Task 5 step 1's, or of Task 6 step 8's — draws on the branch's two (the `re-review` workflow's cap), and a Critical or Important open with none left goes to the owner; the PR is created and edited through `open-pr`, its read line naming the tip read.

## Review Focus

- A BTC fill inside BTC's first 180 bars must accept an entry there, and one past them must reject it — the warm-up ordered before the fill rule, else B differs from A by an artifact of the fill before the norm exists. Test: Task 2, `test_a_btc_fill_is_accepted_in_the_warm_up_and_rejected_after_it`.
- A history shorter than the lookback — a late listing near the set's end, or a short window — must accept every entry, so B's states equal A's there, never a comparison against a level of fewer than 180 bars. Test: Task 2, `test_a_history_shorter_than_the_lookback_accepts_every_entry`.
- After a rejected entry the next band touch is a new event on B's own machine, though A is already +1; counting on A's machine would undercount `entry_events` and `share_rejected`. Test: Task 2, `test_a_rejected_entry_leaves_the_state_an_exit_is_always_taken_and_each_touch_off_plus_1_is_an_event`.
- A windowed evaluation must read each 240 file's volume under the union's own bounds, the second read of the file under the same window, so the norm warms up from the window's first bar (D4). Test: Task 3, `test_b1_volume_reads_its_volumes_under_the_unions_window`.
- The per-year counts must keep every year an asset has a state in, zeros included, drop the year that holds only its last bar, and key a bar at 2015-12-31 20:00 to 2015, its bar-start year. Test: Task 2, `test_entry_events_are_counted_per_bar_start_year_every_year_with_a_state_kept`.

## File structure

- Create `cli/alpha/b1_volume.py` — the norm, the confirmations per asset, the confirmed state machine and directions, arm B's positions, the engagement counts.
- Create `tests/test_alpha_b1_volume.py` — the module's tests, synthetic, every expected value computed by hand.
- Create `tests/test_research_b1_volume_basis.py` — data-gated: the reads against the measured basis, and arm A against record 45's anchors.
- Modify `cli/research/subjects.py` — the literals, the three halves, the two subjects.
- Modify `tests/test_research_command.py` — the fixture, the subjects' tests, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`; `README.md` — the `--subject` row; `tests/slow-cases.txt` — the new slow cases.
- At the run: `docs/reference/trial-registry.jsonl` (or, on a stop, `docs/reference/reading-ledger.jsonl`), `tests/test_trial_registry_provenance.py` (`LANDED_N_TRIALS`), `docs/research/10.phase4-decisions.md`, `docs/open-topics/T0022-b1-intraday-seasonality-family.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md`.

______________________________________________________________________

### Task 1: the branch on spec 00133's built `Subject`, checked (D12's "Where the build sits")

**Files:** none changed. The branch was rebased onto plan 00133's Task 6 commit `cfb4619480ee9a07afc19fbcbf828e46fced701f` and its fix `3068c8a0811fd6d719491a30202f239df926da63` before the plan review, which read that tree; this task checks it and changes nothing.

**Interfaces:**
- Consumes: plan 00133 Task 6's `Subject.family: str | None = None`, `Subject.n_trials: int | None = None`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `test_the_ruled_subjects_declare_their_families_and_trial_counts` and `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count`; plan 00133 Task 4's autouse fixture `_attempts_log_in_tmp_path(tmp_path)` in `tests/conftest.py`; plan 00133 Task 5's autouse module fixture `_attempts_log(tmp_path, monkeypatch, _attempts_log_in_tmp_path) -> Path` in `tests/test_research_command.py`; plan 00133 Task 2's `budget.BUCKET_OF`.
- Produces: nothing; a failed check stops the plan, and the report names it.

- [ ] **Step 1: Check** — each its own call, each read before the next:
  - `git merge-base --is-ancestor 3068c8a0811fd6d719491a30202f239df926da63 HEAD` exits 0.
  - `uv run python -c 'from dataclasses import fields; from cli.research.subjects import SUBJECTS, Subject; names = {f.name for f in fields(Subject)}; assert {"family", "n_trials"} <= names, sorted(names); print(SUBJECTS["b1-hourly-rv"].family, SUBJECTS["b1-hourly-rv"].n_trials)'` prints `B1 3`.
  - `git grep -n -e "def _attempts_log_in_tmp_path" -e "^_RULED_FIXTURES = " -e "^_DECLARED_COUNT = " -- tests/conftest.py tests/test_research_command.py` prints three lines.
  - `mkdir -p .tmp/plan-00134 && uv run pytest tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt` and `uv run pytest tests/test_research_command.py -k "families_and_trial_counts or declares_a_tracked_spec" -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt` pass.

No commit: a check adds none.

______________________________________________________________________

### Task 2: the module — the norm, the gate, arm B's positions, the engagement counts (D2, D3, D4, D8's helpers)

**Files:**
- Create: `cli/alpha/b1_volume.py`
- Create: `tests/test_alpha_b1_volume.py`
- Modify: `tests/slow-cases.txt`, when Step 4 times a case at 10 s or more

**Interfaces:**
- Consumes: `cli.alpha.a1._map_to_union_index`, `cli.alpha.a1._validate_prices_by_asset`, `cli.alpha.a2.A2Config`, `cli.features.channel_position`, `cli.alpha.errors.AlphaError`; nothing of spec 00133.
- Produces, every name imported by Task 3:

```python
def volume_confirmations(stamps: list[datetime], volumes: list[float | None], *, lookback: int, min_cell_obs: int) -> list[bool]: ...
def confirmations_by_asset(fed: dict[str, list[float | None]], h4_prices: dict[str, list[float | None]], union_ts: list[datetime],
                           volumes: dict[str, list[float | None]], *, lookback: int, min_cell_obs: int) -> dict[str, list[bool]]: ...
def donchian_signal_confirmed(prices: list[float], confirm: list[bool], *, window: int, band: float) -> tuple[list[float], list[tuple[int, bool]]]: ...
def asset_directions_confirmed(prices_by_asset: dict[str, list[float | None]], union_ts: list, asset_ts: dict[str, list],
                               confirm_by_asset: dict[str, list[bool]], *, config: A2Config
                               ) -> tuple[dict[str, list[float | None]], dict[str, dict[int, list[tuple[int, bool]]]]]: ...
def a2_positions_on_directions(weights: list[dict[str, float]], directions: dict[str, list[float | None]], scalar: list[float]) -> dict[str, list[float]]: ...
def entry_events_per_year(events: dict[str, dict[int, list[tuple[int, bool]]]], own_stamps: dict[str, list[datetime]]) -> dict[str, dict[str, dict[str, list[int]]]]: ...
def directions_differ_per_year(directions_a: list[dict[str, list[float | None]]], directions_b: list[dict[str, list[float | None]]], union_ts: list[datetime]) -> dict[str, int]: ...
```

- [ ] **Step 1: Write the failing tests** — `tests/test_alpha_b1_volume.py`, whole; every expected value is computed by hand in the comment above it, never on the trial's data:

```python
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.a2 import A2Config, _asset_directions_a2, _donchian_signal, a2_book_returns
from cli.alpha.b1_volume import (
    a2_positions_on_directions,
    asset_directions_confirmed,
    confirmations_by_asset,
    directions_differ_per_year,
    donchian_signal_confirmed,
    entry_events_per_year,
    volume_confirmations,
)
from cli.alpha.errors import AlphaError
from cli.portfolio.crossfreq_system import _ffill_btc

_T0 = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday
_H4, _DAY, _WEEK = timedelta(hours=4), timedelta(days=1), timedelta(days=7)
_SMALL = A2Config(lookbacks=(5, 10, 20), short="off", target_vol=0.12, vol_lookback=12, basket_lookback=8, periods_per_year=2190)
_ADOPTED = tuple(
    A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
)


def _stamps(n: int, step: timedelta = _H4) -> list[datetime]:
    return [_T0 + i * step for i in range(n)]


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


def test_the_level_is_the_median_of_the_prior_bars_and_never_the_bar_itself():
    # lookback 3, the shape at 1: bar 3's level is median(100, 10, 50) = 50 > 20, where median(10, 50, 20) = 20 — bar 3 in
    # its own window — would accept it; bar 4: median(10, 50, 20) = 20, accepted at equality; bar 5: median(50, 20, 20) = 20 > 19.
    volumes = [100.0, 10.0, 50.0, 20.0, 20.0, 19.0]
    assert volume_confirmations(_stamps(6), volumes, lookback=3, min_cell_obs=100) == [True, True, True, False, True, False]
    # lookback 2, an even count, the median the mean of the two middle values: bar 2's level is median(10, 30) = 20 > 15, bar
    # 3's median(30, 15) = 22.5 <= 25; median_low's 10 and 15 would accept every bar.
    assert volume_confirmations(_stamps(4), [10.0, 30.0, 15.0, 25.0], lookback=2, min_cell_obs=100) == [True, True, False, True]


def test_the_hour_of_week_shape_binds_at_min_cell_obs_earlier_observations():
    # Weekly stamps, one cell; lookback 2, min_cell_obs 2. Bar 2: L = 16, no observation, S = 1, 32 >= 16, ratio 2.0. Bar 3:
    # L = 28, one observation, S = 1, 28 >= 28, ratio 1.0. Bar 4: L = 30, S = median(2.0, 1.0) = 1.5, 40 < 45.0, its ratio
    # 4/3 kept though it is rejected. Bar 5: L = 34, S = median(2.0, 1.0, 4/3) = 4/3, 46 >= 45.33. With S held at 1 bar 4
    # would be accepted; the mean, 13/9, would reject bar 5 (46 < 49.11), and so would S without bar 4's ratio (1.5, 46 < 51).
    volumes = [8.0, 24.0, 32.0, 28.0, 40.0, 46.0]
    assert volume_confirmations(_stamps(6, _WEEK), volumes, lookback=2, min_cell_obs=2) == [True, True, True, True, False, True]
    # lookback 1, an even count of ratios: bar 3's L = 30, S = median(1.0, 3.0) = 2.0, 70 >= 60; median_high's 3.0 would
    # reject it.
    assert volume_confirmations(_stamps(4, _WEEK), [10.0, 10.0, 30.0, 70.0], lookback=1, min_cell_obs=2) == [True] * 4
    # Each ratio read against its own L: bars 1 and 2 add 20 / 10 and 40 / 20, so bar 3's L = 40, S = 2.0, 70 < 80; read
    # against E, bar 2's ratio is 40 / 40 = 1.0, S = 1.5 and bar 3 accepted.
    volumes = [10.0, 20.0, 40.0, 70.0]
    assert volume_confirmations(_stamps(4, _WEEK), volumes, lookback=1, min_cell_obs=1) == [True, True, True, False]


@pytest.mark.parametrize(
    "stamps",
    [
        pytest.param([_T0 + w * _WEEK + d * _DAY for w in range(3) for d in range(2)], id="two-weekdays-one-hour"),
        pytest.param([_T0 + w * _WEEK + h * _H4 for w in range(3) for h in range(2)], id="two-hours-one-weekday"),
    ],
)
def test_each_hour_of_week_cell_holds_its_own_ratios(stamps):
    # Two cells alternate, Monday and Tuesday at 04:00 or Monday at 04:00 and 08:00; lookback 2, min_cell_obs 1. Bar 4:
    # L = median(10, 30) = 20, S = its own cell's 1.0, 20 >= 20; a key pooling the two cells, the hour alone on the first row
    # and the weekday alone on the second, would add the other cell's 3.0, S = 2.0.
    volumes = [10.0, 10.0, 10.0, 30.0, 20.0, 20.0]
    assert volume_confirmations(stamps, volumes, lookback=2, min_cell_obs=1) == [True, True, True, True, True, False]


def test_the_warm_up_accepts_every_bar_and_a_missing_volume_after_it_never_confirms():
    # lookback 3: a missing volume is no bar, so the warm-up lasts to index 4; index 5 has no volume; index 6:
    # L = median(10, 20, 30) = 20 <= 25.
    volumes = [None, 10.0, 20.0, None, 30.0, None, 25.0]
    assert volume_confirmations(_stamps(7), volumes, lookback=3, min_cell_obs=100) == [True, True, True, True, True, False, True]


def test_a_history_shorter_than_the_lookback_accepts_every_entry():
    assert volume_confirmations(_stamps(5), [5.0, 1.0, 9.0, 0.5, 3.0], lookback=180, min_cell_obs=100) == [True] * 5


def test_no_flag_reads_a_later_bar():
    stamps, volumes = _stamps(120), [10.0 + 9.0 * math.sin(2.7 * i) for i in range(120)]
    full = volume_confirmations(stamps, volumes, lookback=5, min_cell_obs=1)
    assert any(full[5:]) and not all(full[5:])
    for n in range(1, 121):
        assert volume_confirmations(stamps[:n], volumes[:n], lookback=5, min_cell_obs=1) == full[:n]


@pytest.mark.parametrize(
    ("stamps", "volumes", "over", "match"),
    [
        pytest.param(_stamps(3), [1.0, 0.0, 1.0], {}, "volume must be a finite number above 0", id="zero-volume"),
        pytest.param(_stamps(3), [1.0, -1.0, 1.0], {}, "volume must be a finite number above 0", id="negative-volume"),
        pytest.param(_stamps(3), [1.0, math.nan, 1.0], {}, "volume must be a finite number above 0", id="nan-volume"),
        pytest.param(_stamps(3), [1.0, math.inf, 1.0], {}, "volume must be a finite number above 0", id="inf-volume"),
        pytest.param(_stamps(3), [1.0, True, 1.0], {}, "volume must be a finite number above 0", id="bool-volume"),
        pytest.param([_T0, _T0, _T0 + _H4], [1.0] * 3, {}, "strictly increasing", id="repeated-stamp"),
        pytest.param([_T0.replace(tzinfo=None), _T0 + _H4, _T0 + 2 * _H4], [1.0] * 3, {}, "tz-aware", id="naive-stamp"),
        pytest.param(_stamps(3), [1.0] * 2, {}, "stamps and volumes", id="unequal-lengths"),
        pytest.param(_stamps(3), [1.0] * 3, {"lookback": 0}, "lookback must be an int >= 1", id="lookback-0"),
        pytest.param(_stamps(3), [1.0] * 3, {"lookback": True}, "lookback must be an int >= 1", id="lookback-bool"),
        pytest.param(_stamps(3), [1.0] * 3, {"lookback": 1.5}, "lookback must be an int >= 1", id="lookback-float"),
        pytest.param(_stamps(3), [1.0] * 3, {"min_cell_obs": 0}, "min_cell_obs must be an int >= 1", id="min-cell-obs-0"),
    ],
)
def test_volume_confirmations_refuses_an_input_it_cannot_gate(stamps, volumes, over, match):
    with pytest.raises(AlphaError, match=match):
        volume_confirmations(stamps, volumes, **({"lookback": 2, "min_cell_obs": 2} | over))


_CLOSES = {"BTC": [100.0, None, 100.0, 100.0, None, 100.0, 100.0, 100.0], "ETH": [50.0] * 8}
_VOLUMES = {"BTC": [10.0, None, 20.0, 30.0, None, 40.0, 5.0, 25.0], "ETH": [8.0] * 8}


def test_a_btc_fill_is_accepted_in_the_warm_up_and_rejected_after_it():
    # lookback 2 on BTC's own bars, the fills at 1 (inside the warm-up) and 4 (past it): bar 3: L = median(10, 20) = 15 <= 30;
    # bar 5: L = median(20, 30) = 25 <= 40; bar 6: L = median(30, 40) = 35 > 5; bar 7: L = median(40, 5) = 22.5 <= 25.
    fed = _ffill_btc(_CLOSES)
    assert confirmations_by_asset(fed, _CLOSES, _stamps(8), _VOLUMES, lookback=2, min_cell_obs=100) == {
        "BTC": [True, True, True, True, False, True, False, True],
        "ETH": [True] * 8,
    }


@pytest.mark.parametrize(
    ("closes", "volumes", "match"),
    [
        pytest.param(
            _CLOSES,
            {**_VOLUMES, "BTC": [10.0, 9.0, *_VOLUMES["BTC"][2:]]},
            r"BTC: a volume where the close is absent at 2024-01-01T04:00:00\+00:00",
            id="a-volume-at-a-fill",
        ),
        pytest.param(
            _CLOSES,
            {**_VOLUMES, "ETH": [8.0, 8.0, 8.0, None, 8.0, 8.0, 8.0, 8.0]},
            r"ETH: no volume where the close is present at 2024-01-01T12:00:00\+00:00",
            id="no-volume-at-a-close",
        ),
        pytest.param(
            {**_CLOSES, "ETH": [None, *[50.0] * 7]},
            _VOLUMES,
            r"ETH: a volume where the close is absent at 2024-01-01T00:00:00\+00:00",
            id="a-volume-before-the-listing",
        ),
        pytest.param(
            _CLOSES,
            {**_VOLUMES, "ETH": [8.0, 8.0, 0.0, 8.0, 8.0, 8.0, 8.0, 8.0]},
            r"ETH: volume must be a finite number above 0, got 0.0 at 2024-01-01T08:00:00\+00:00",
            id="a-zero-volume-named-by-asset",
        ),
        pytest.param(
            {**_CLOSES, "ETH": [50.0, 0.0, *[50.0] * 6]},
            _VOLUMES,
            "prices must be None or finite positive numbers",
            id="a-zero-close",
        ),
        pytest.param(_CLOSES, {"BTC": _VOLUMES["BTC"]}, "volumes' assets", id="an-asset-without-volumes"),
    ],
)
def test_confirmations_by_asset_refuses_a_volume_off_its_close(closes, volumes, match):
    with pytest.raises(AlphaError, match=match):
        confirmations_by_asset(_ffill_btc(closes), closes, _stamps(8), volumes, lookback=2, min_cell_obs=100)


_PRICES = [10.0, 11.0, 12.0, 11.0, 12.0, 13.0, 12.0, 13.0]


def test_a_rejected_entry_leaves_the_state_an_exit_is_always_taken_and_each_touch_off_plus_1_is_an_event():
    # window 2: the channel position is +1 at a higher close, -1 at a lower one. Bar 1's entry is rejected, so bar 2's touch
    # is an event on B's own machine (A is already +1); bar 3's exit is taken with its flag false; bars 4 and 5 touch at -1.
    confirm = [True, False, True, False, False, False, True, True]
    assert donchian_signal_confirmed(_PRICES, confirm, window=2, band=1.0) == (
        [0.0, 0.0, 1.0, -1.0, -1.0, -1.0, -1.0],
        [(1, False), (2, True), (4, False), (5, False)],
    )
    # A rise: bar 1's entry is accepted, so bar 2's touch, B already +1, is no event and keeps +1 though its flag is false.
    assert donchian_signal_confirmed([10.0, 11.0, 12.0, 13.0], [True, True, False, True], window=2, band=1.0) == (
        [0.0, 1.0, 1.0],
        [(1, True)],
    )


@pytest.mark.parametrize("window", [2, 3, 5])
def test_every_entry_confirmed_is_the_unconfirmed_state_machine(window):
    prices = [100.0 * (1 + 0.05 * math.sin(k / 3.0)) * 1.002**k for k in range(80)]
    states, events = donchian_signal_confirmed(prices, [True] * 80, window=window, band=1.0)
    assert states == _donchian_signal(prices, window=window, band=1.0)
    assert events and all(accepted for _, accepted in events)


def _btc_directions(confirm: list[bool], *, short: str = "off", assets: tuple[str, ...] = ("BTC",)):
    prices = {"BTC": list(_PRICES)}
    union_ts, asset_ts = _index(prices)
    config = A2Config(lookbacks=(2,), short=short, target_vol=0.1)
    return asset_directions_confirmed(prices, union_ts, asset_ts, dict.fromkeys(assets, confirm), config=config)


def test_the_directions_map_the_confirmed_states_onto_the_union_clipped_at_0():
    directions, events = _btc_directions([True, False, True, False, False, False, True, True])

    assert directions == {"BTC": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]}
    assert events == {"BTC": {2: [(1, False), (2, True), (4, False), (5, False)]}}


@pytest.mark.parametrize(("config", "n"), [(_SMALL, 400), *((config, 600) for config in _ADOPTED)])
def test_with_every_entry_confirmed_the_directions_and_positions_are_arm_as(config, n):
    prices = _union(n)
    union_ts, asset_ts = _index(prices)
    confirm = {asset: [True] * len(ts) for asset, ts in asset_ts.items()}
    book = a2_book_returns(prices, config=config)

    directions, _ = asset_directions_confirmed(prices, union_ts, asset_ts, confirm, config=config)

    assert directions == _asset_directions_a2(prices, union_ts, asset_ts, config=config)
    weights = _inverse_vol_weights(prices, lookback=config.basket_lookback)
    assert a2_positions_on_directions(weights, directions, book["vol_target_positions"]) == book["asset_positions"]


def test_a_rejected_entry_never_lifts_a_direction_above_arm_as():
    prices = _union(400)
    union_ts, asset_ts = _index(prices)
    confirm = {asset: [j % 3 != 1 for j in range(len(ts))] for asset, ts in asset_ts.items()}

    d_b, events = asset_directions_confirmed(prices, union_ts, asset_ts, confirm, config=_SMALL)

    d_a = _asset_directions_a2(prices, union_ts, asset_ts, config=_SMALL)
    pairs = [(d_b[asset][k], d_a[asset][k]) for asset in prices for k in range(len(union_ts) - 1)]
    assert all((b is None) == (a is None) for b, a in pairs)
    assert all(b <= a for b, a in pairs if b is not None) and any(b < a for b, a in pairs if b is not None)
    assert {asset: sorted(by_lookback) for asset, by_lookback in events.items()} == {asset: [5, 10, 20] for asset in prices}
    assert any(not accepted for by_lookback in events.values() for evs in by_lookback.values() for _, accepted in evs)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(
            lambda: donchian_signal_confirmed(_PRICES, [True] * 7, window=2, band=1.0), "7 flags for 8 prices", id="flags-short"
        ),
        pytest.param(lambda: _btc_directions([True] * 8, short="on"), "short='off'", id="short-on"),
        pytest.param(lambda: _btc_directions([True] * 7), "BTC: confirm holds 7 flags for 8 bars", id="an-asset-one-flag-short"),
        pytest.param(lambda: _btc_directions([True] * 8, assets=("ETH",)), "confirm's assets", id="confirm-off-the-assets"),
        pytest.param(
            lambda: a2_positions_on_directions([{}] * 2, {"BTC": [1.0] * 3}, [1.0] * 3), "differ in length", id="weights-short"
        ),
        pytest.param(
            lambda: a2_positions_on_directions([{}] * 3, {"BTC": [1.0] * 2}, [1.0] * 3), "differ in length", id="a-direction-short"
        ),
    ],
)
def test_the_directions_and_positions_refuse_inputs_off_their_shape(call, match):
    with pytest.raises(AlphaError, match=match):
        call()


def test_entry_events_are_counted_per_bar_start_year_every_year_with_a_state_kept():
    # ETH's bar at 2015-12-31 20:00 closes in 2016 and is keyed 2015; its last bar, alone in 2018, has no state.
    eth = [datetime(2015, 12, 31, 16, tzinfo=UTC), datetime(2015, 12, 31, 20, tzinfo=UTC), datetime(2016, 1, 1, tzinfo=UTC)]
    eth += [datetime(2017, 6, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)]
    events = {"ETH": {2: [(1, False), (2, True)], 3: []}}
    assert entry_events_per_year(events, {"ETH": eth}) == {
        "ETH": {
            "2": {"2015": [1, 1], "2016": [1, 0], "2017": [0, 0]},
            "3": {"2015": [0, 0], "2016": [0, 0], "2017": [0, 0]},
        }
    }


def test_directions_differ_per_bar_start_year_counting_each_stamp_once():
    union_ts = [
        datetime(2014, 12, 31, 20, tzinfo=UTC),
        datetime(2015, 12, 31, 16, tzinfo=UTC),
        datetime(2015, 12, 31, 20, tzinfo=UTC),
    ]
    union_ts += [datetime(2016, 1, 1, tzinfo=UTC), datetime(2016, 1, 1, 4, tzinfo=UTC), datetime(2016, 1, 1, 8, tzinfo=UTC)]
    directions_a = [{"BTC": [0.5, 0.0, 1.0, None, 0.5]}, {"BTC": [1.0, 1.0, 1.0, 1.0, 1.0]}]
    directions_b = [{"BTC": [0.5, 0.0, 0.0, None, 0.0]}, {"BTC": [1.0, 1.0, 0.0, 1.0, 1.0]}]
    # Stamp 2, keyed 2015, differs on both arms and counts once; stamp 3's None equals None; 2014 stays, at 0.
    assert directions_differ_per_year(directions_a, directions_b, union_ts) == {"2014": 0, "2015": 1, "2016": 1}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00134 && uv run pytest tests/test_alpha_b1_volume.py -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt`
Expected: collection error, `ModuleNotFoundError: No module named 'cli.alpha.b1_volume'` — the fence, run against the tree at this plan's commit, fails so.

- [ ] **Step 3: Implement `cli/alpha/b1_volume.py`** — a module docstring naming `docs/specs/00134-b1-volume-confirmation-design.md` and stating the stamp convention (a bar's stamp is its open; its cell is that of `ts + 4h`) in a sentence; and:
  - `volume_confirmations`: the refusals first — `lookback`, then `min_cell_obs`, each `f"{name} must be an int >= 1, got {value!r}"` (`type(...)` excluding bool, as `cli.alpha.a1._check_window` does); `f"stamps and volumes differ in length: {len(stamps)} and {len(volumes)}"`; per stamp `f"stamps must be tz-aware, got {t!r} at index {i}"` and `f"stamps must be strictly increasing, violated at {t.isoformat()}"`; per present volume `f"volume must be a finite number above 0, got {v!r} at {t.isoformat()}"`, a bool refused — each on its own `if` line; then spec D3's code block verbatim, its two comments included.
  - `confirmations_by_asset`: `_validate_prices_by_asset(fed)` first, on its own line, so a close of 0 is refused before any later division; `set(volumes) != set(fed)` refused, `f"volumes' assets {sorted(volumes)} are not the prices' {sorted(fed)}"`; per asset and union index the presence check against the raw close, `(volumes[a][k] is None) != (h4_prices[a][k] is None)`, refused as `f"{a}: a volume where the close is absent at {t.isoformat()}"` or `f"{a}: no volume where the close is present at {t.isoformat()}"` (**Author's call**: presence is read against the volume's own row, the raw close, so a BTC fill — a `fed` price with no raw close — carries no volume by construction, which is D4's "absent where the price is present at a stamp other than a BTC fill"); then `volume_confirmations` over the stamps where `fed[a]` holds a price and the volumes there, its `AlphaError` re-raised as `f"{a}: {exc}"` from it.
  - `donchian_signal_confirmed`: `len(confirm) != len(prices)` refused, `f"confirm holds {len(confirm)} flags for {len(prices)} prices"` (one flag per own bar, the last unread); then spec D2's code block verbatim.
  - `asset_directions_confirmed`: refuses a config whose `short` is not `"off"` (`f"the confirmed directions need short='off', got {config.short!r}"`), `set(confirm_by_asset) != set(prices_by_asset)` (`f"confirm's assets {...} are not the prices' {...}"`) and, per asset, `len(confirm_by_asset[asset]) != len(asset_ts[asset])` (`f"{asset}: confirm holds {n} flags for {m} bars"`); then `cli.alpha.a2._asset_directions_a2`'s body with `donchian_signal_confirmed(own_prices, confirm_by_asset[asset], window=w, band=config.band)` in place of `_donchian_signal(...)`, its states mapped, its events kept under `events[asset][w]`, the clip written as `a2` writes it, `ensemble = statistics.mean(values)` then `d.append(max(ensemble, 0.0))`.
  - `a2_positions_on_directions`: refuses, on one `if`, `len(weights) != len(scalar)` or any direction list of another length (`"weights, directions and scalar differ in length"`); returns `{asset: [weights[k].get(asset, 0.0) * (directions[asset][k] or 0.0) * scalar[k] for k in range(len(scalar))] for asset in directions}` — `a2_book_returns`' asset-positions expression, so the identity holds bit for bit.
  - `entry_events_per_year`: per asset, the years `{own_stamps[asset][j].year for j in range(len(own_stamps[asset]) - 1)}` — the bars with a state — each `[0, 0]`, then each event `(j, accepted)` adds 1 to `[0]` and, when rejected, 1 to `[1]` of `str(own_stamps[asset][j].year)`; keys `str(w)` and `str(year)`.
  - `directions_differ_per_year`: `{str(y): 0}` for every bar-start year of `union_ts[:-1]`, then 1 added to `str(union_ts[k].year)` for each return index `k` where `any(da[a][k] != db[a][k] for da, db in zip(directions_a, directions_b) for a in da)`.
  - **Author's call**: five shape refusals, which this step adds to spec D2's and D4's, guard no input the subjects build — `confirmations_by_asset`'s asset set, `donchian_signal_confirmed`'s flag count, `asset_directions_confirmed`'s assets and per-asset flag count, `a2_positions_on_directions`' lengths — since each function's one caller in this plan already ties them; they stay because a longer list or an extra asset would otherwise be read short without a word, its tail or the asset left unread.

- [ ] **Step 4: Run the tests to verify they pass** — Step 2's command with `--durations=0`; expected `44 passed`, and a case at 10 s or more joins `tests/slow-cases.txt` at its sorted place, staged with this task's commit.

- [ ] **Step 5: Consumers, then commit** — `bash infra/scripts/consumers.sh --direct cli/alpha/b1_volume.py` lists the new test file alone; the gate.

```bash
git add cli/alpha/b1_volume.py tests/test_alpha_b1_volume.py
# and tests/slow-cases.txt when Step 4 listed a case
git commit -F - <<'EOF'
feat(alpha): the hour-of-week volume norm, the confirmed A2 entry gate and arm B's positions for B1 trial 4

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: Probes** — `--file cli/alpha/b1_volume.py`, control `s/^def volume_confirmations(/def volume_confirmations_gone(/` (the test module imports it, so every case fails); each mutation a row names is one probe, expected `KILLED`; a row naming several cases is one probe per case. The rows prove that each of these alterations of spec D2's and D3's code blocks fails a case of this file, and claim no other: the level's window holding the bar itself, reading a later bar, or warming up on fewer bars than `lookback`; its median made the mean or `median_low`; the `>=` made `>`; the cell's threshold made `>`; `S`'s median made the mean or `median_high`; `S`'s observations losing a rejected bar's ratio, or each ratio read against `E` in place of its own `L`; the cell key losing its hour or its weekday; the warm-up accepting only a bar with a volume; the fill confirming; a touch while already +1 counted as an event, the flag ignored, the exit gated on the flag, the exit's −1 made 0; an event recorded as accepted whatever its flag. The boundary's `+ timedelta(hours=4)` alone moves no flag: shifting every UTC stamp by 4 h maps the 168 hour-of-week cells one to one. The family "a choice D2/D3's code blocks fix that no case separates from its alternative" is closed on the owner's word, 2026-10-18 — "Admit 3, then close (Recommended)", the option reading "Add the reviewer's three hand-checked cases and three probe rows, then close this guard family: later shapes found in it are dropped explicitly in the PR body, not widened. The norm is the trial's treatment, so a wrong one mis-verdicts trial 4 permanently." — so a further member a later read finds is an explicit drop in the pull request body, never a widening.

| node id under `tests/test_alpha_b1_volume.py::` | mutation |
| -- | -- |
| `test_the_level_is_the_median_of_the_prior_bars_and_never_the_bar_itself` | `s/level = statistics.median(rows\[-lookback:\])/level = statistics.median([*rows[1 - lookback:], v])/`; `statistics.median(rows[-lookback:])` made `statistics.mean(rows[-lookback:])`; `statistics.median(rows[-lookback:])` made `statistics.median_low(rows[-lookback:])`; `v >= level * shape` made `v > level * shape` |
| `test_the_hour_of_week_shape_binds_at_min_cell_obs_earlier_observations` | `len(cell) >= min_cell_obs` made `len(cell) > min_cell_obs`; `statistics.median(cell)` made `statistics.mean(cell)`; `statistics.median(cell)` made `statistics.median_high(cell)`; `cell.append(v / level)` made `cell.append(v / level) if v >= level * shape else None`; `cell.append(v / level)` made `cell.append(v / (level * shape))` |
| `test_each_hour_of_week_cell_holds_its_own_ratios[<row>]` | `(b.hour, b.weekday())` made `(b.hour, 0)` (`two-weekdays-one-hour`), and made `(0, b.weekday())` (`two-hours-one-weekday`) |
| `test_the_warm_up_accepts_every_bar_and_a_missing_volume_after_it_never_confirms` | the fill line's `out.append(False)` made `out.append(True)` |
| `test_a_history_shorter_than_the_lookback_accepts_every_entry` | `if len(rows) < lookback:` made `if len(rows) < min(lookback, 3):` |
| `test_no_flag_reads_a_later_bar` | `s/level = statistics.median(rows\[-lookback:\])/level = statistics.median([x for x in volumes if x is not None][len(rows) + 2 - lookback : len(rows) + 2])/` |
| `test_volume_confirmations_refuses_an_input_it_cannot_gate[<row>]` | each refusal's `if` made `if False:` against each row it refuses: the count check (`lookback-0`, `lookback-bool`, `lookback-float`, `min-cell-obs-0`), the length (`unequal-lengths`), tz (`naive-stamp`), order (`repeated-stamp`), the volume (`zero-volume`, `negative-volume`, `nan-volume`, `inf-volume`, `bool-volume`) |
| `test_a_btc_fill_is_accepted_in_the_warm_up_and_rejected_after_it` | the warm-up line's `out.append(True)` made `out.append(v is not None)` |
| `test_confirmations_by_asset_refuses_a_volume_off_its_close[<row>]` | the presence `if` made `if False:` (`a-volume-at-a-fill`, `no-volume-at-a-close`, `a-volume-before-the-listing`); the re-raise's `f"{a}: {exc}"` made `f"{exc}"` (`a-zero-volume-named-by-asset`); `_validate_prices_by_asset(fed)` made `None` (`a-zero-close`); the asset-set `if` made `if False:` (`an-asset-without-volumes`) |
| `test_a_rejected_entry_leaves_the_state_an_exit_is_always_taken_and_each_touch_off_plus_1_is_an_event` | `if confirm[j]:` made `if True:`; `if held != 1.0:` made `if True:`; `elif cp[j] <= -band:` made `elif cp[j] <= -band and confirm[j]:` |
| `test_every_entry_confirmed_is_the_unconfirmed_state_machine[2]` | `held = -1.0` made `held = 0.0` |
| `test_the_directions_map_the_confirmed_states_onto_the_union_clipped_at_0` | `d.append(max(ensemble, 0.0))` made `d.append(ensemble)` |
| `test_with_every_entry_confirmed_the_directions_and_positions_are_arm_as[<each>]` | `* scalar[k]` made `* scalar[k - 1]` |
| `test_a_rejected_entry_never_lifts_a_direction_above_arm_as` | `events.append((j, confirm[j]))` made `events.append((j, True))` |
| `test_the_directions_and_positions_refuse_inputs_off_their_shape[<row>]` | each refusal's `if` made `if False:` against its rows: `flags-short`, `short-on`, `an-asset-one-flag-short`, `confirm-off-the-assets`, and the positions' one `if` against `weights-short` and `a-direction-short` |
| `test_entry_events_are_counted_per_bar_start_year_every_year_with_a_state_kept` | the event's year read off the bar after it, `own_stamps[asset][j]` made `own_stamps[asset][j + 1]` on the line that keys the count |
| `test_directions_differ_per_bar_start_year_counting_each_stamp_once` | `union_ts[k].year` made `union_ts[k + 1].year` on the line that adds the count |

______________________________________________________________________

### Task 3: the subjects `b1-volume-confirmation` and `b1-volume-confirmation-preflight` (D1, D5–D8, D10, D11)

**Files:**
- Modify: `cli/research/subjects.py` — after trial 3's `SUBJECTS`-feeding names and before `SUBJECTS`; two entries in `SUBJECTS`
- Modify: `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`

**Interfaces:**
- Consumes: this plan's Task 2's seven functions, imported into `subjects` by name (so a test's `monkeypatch.setattr(subjects, …)` reaches them), and `cli.alpha.a2._asset_directions_a2`; plan 00133 Task 6's `Subject.family` and `Subject.n_trials`, `_RULED_FIXTURES`, `_DECLARED_COUNT` and the declared-counts and kill-bar tests; plan 00133 Tasks 4 and 5's `_attempts_log_in_tmp_path` and `_attempts_log`, which hold every `--register` run's attempts log in `tmp_path`; the test module's `_rows`, `_B1_START`, `_B1_BARS`, `_B2_ASSETS`, `_anchor`, `_recording`, `_rolling_set`, `_kept`, `_block_and_metrics`, `_trials`, `_arm_a_flat`, `_B1_UNREADABLE_HISTORIES`, `_B1_HOURLY_RV_ARMS`, `_B1_HOURLY_RV_CELLS`, `_B1_HOURLY_RV_ANCHORS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_b1_hourly_rv_bar_sentinels`.
- Produces:

```python
# cli/research/subjects.py
_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES = (*_B1_RECORDED_PER_PERIOD_SHARPES, 0.030191886721210086)
_B1_VOLUME_N_TRIALS = 4
_B1_VOLUME_MIN_CELL_OBS = 100

class _B1VolumeReads(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    volumes: dict[str, list[float | None]]

class _B1VolumeInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    volumes: dict[str, list[float | None]]
    fed: dict[str, list[float | None]]
    returns: dict[str, list[float | None]]
    weights_a: list[dict[str, float]]
    vt_a: list[list[float]]                                  # per arm of _B1_A2_ARMS
    directions_a: list[dict[str, list[float | None]]]        # per arm
    confirm: dict[str, list[bool]]
    directions_b: list[dict[str, list[float | None]]]        # per arm
    events: list[dict[str, dict[int, list[tuple[int, bool]]]]]  # per arm
    own_stamps: dict[str, list[datetime]]
    arm_a: dict[str, list[float]]

def _b1_volume_reads(reader: ObservedReader, dataset: str, window: tuple[str, str] | None, as_of: str | None, accept_holes: bool, *, subject: str) -> _B1VolumeReads: ...
def _b1_volume_inputs(reads: _B1VolumeReads) -> _B1VolumeInputs: ...
def _b1_volume_arm_a(inputs: _B1VolumeInputs) -> tuple[dict, float, list[float], list[float]]: ...  # bar, arm_a_var_trials, net_a, bench
def _b1_volume_engagement(inputs: _B1VolumeInputs) -> dict: ...  # the six engagement keys
def _b1_volume_metrics(inputs: _B1VolumeInputs) -> dict: ...  # 43 keys
def _b1_volume_preflight_metrics(inputs: _B1VolumeInputs) -> dict: ...  # 24 keys
def _b1_volume_build(subject: str, compute: Callable[[_B1VolumeInputs], dict], reader, dataset, window, as_of, accept_holes) -> dict: ...
def _build_b1_volume_confirmation(reader, dataset, window, as_of=None, accept_holes=False) -> dict: ...
def _build_b1_volume_confirmation_preflight(reader, dataset, window, as_of=None, accept_holes=False) -> dict: ...
def _b1_volume_confirmation_verdict(m: dict) -> str | None: ...
_B1_VOLUME_METRIC_KEYS: frozenset[str]
_B1_VOLUME_PREFLIGHT_KEYS: frozenset[str]
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`. The fixture and the command-path helper go after `_b1_hourly_rv_dataset` and before `_RULED_FIXTURES`, which reads the fixture's name; the module's imports take Task 2's functions and `_asset_directions_a2`:

```python
# BTC's two missing 4h bars: the first among BTC's first 180 bars, where every entry is accepted, the second past them.
_B1_VOLUME_BTC_GAPS = (100, 1_500)


def _b1_volume_dataset(tmp_path: Path, *, start: datetime = _B1_START, bars: int = _B1_BARS) -> Path:
    """Each bar's volume moves on a phase of its own asset's, so the gate rejects entries past the warm-up."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        rows = [
            [*row[:6], f"{10.0 + 9.0 * math.sin(2.7 * k + i)}", row[7]]
            for k, row in enumerate(_rows(bars, phase=i * 0.7, start=int(start.timestamp()), step=4 * 3600))
            if not (asset == "BTC" and k in _B1_VOLUME_BTC_GAPS)
        ]
        write_parquet(to_frame(rows), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    return root


def _b1_volume_args(name: str, tmp_path: Path, *, dataset: str = "ohlc-test") -> list[str]:
    # A ruled subject's command-path cases register into tmp_path: spec 00133 D7 admits no plain eval of a subject with a rule.
    args = ["research", "eval", "--subject", name, "--dataset", dataset]
    if subjects.SUBJECTS[name].verdict is None:
        return args
    flags = ["--register", "--registry", str(tmp_path / "registry.jsonl"), "--ledger", str(tmp_path / "ledger.jsonl")]
    return [*args, *flags, "--iteration", "iter-001", "--family", "B1", "--n-trials", "4"]
```

  **Author's call**: `_b1_volume_args` registers the ruled subject's command-path cases into `tmp_path` rather than running a plain eval, so each case holds at plan 00133's Task 6 commit, where a plain eval still runs; that they hold after its Task 7, which refuses one, is Task 5 step 1's post-merge run of `tests/test_research_command.py` to prove. `_RULED_FIXTURES` gains `"b1-volume-confirmation": _b1_volume_dataset`, `_DECLARED_COUNT` gains `"b1-volume-confirmation": "_B1_VOLUME_N_TRIALS"`, and `test_the_ruled_subjects_declare_their_families_and_trial_counts`' literal gains `"b1-volume-confirmation": ("B1", 4)`. `_CONTRACT_DATASETS` gains both subjects, each `lambda tmp_path, subject: (_b1_volume_dataset(tmp_path), _B1_START)`, and the comment over it names them beside trial 3's: they bring their own fixture, shorter than their declared series, because each row that evaluates them runs arm A's bar, and the trial's arm B's too, over the whole series. `test_each_subject_declares_the_metric_keys_its_build_returns` gains the two `metric_keys` lines. Then, after trial 3's tests:

```python
_B1_VOLUME_SPEC = "docs/specs/00134-b1-volume-confirmation-design.md"
_B1_VOLUME_NO_VERDICT = (
    "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every stamp; no verdict, the trial unspent"
)
_B1_VOLUME_ENGAGEMENT = frozenset(
    {"entry_events", "entry_events_rejected", "share_rejected", "entry_events_per_year", "stamps_directions_differ",
     "stamps_directions_differ_per_year"}
)
# Typed from the spec's key list, never read off the subject.
_B1_VOLUME_METRIC_KEYS = _B1_VOLUME_ENGAGEMENT | {
    "ann_sharpe_noc", "ann_sharpe_noc_decisive", "per_period_sharpe_4h", "arm_a_ann_sharpe_noc", "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc", "benchmark_ann_sharpe_noc_decisive", "var_trials", "dsr_corrected", "dsr_pass", "spa_pass",
    "spa_p_full", "cost_stress_pass", "worst_slice_relative_pass", "passes", "decisive_start", "n_resamples", "arm_a_var_trials",
    "arm_a_passes", "spa_p_decisive_b30_s42", "spa_p_decisive_b30_s7", "spa_p_decisive_b30_s1234", "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7", "spa_p_decisive_b102_s1234", "head_to_head_mean_outperf_full", "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_2016", "head_to_head_spa_p_2016", "max_drawdown", "arm_a_max_drawdown", "spot_drag_pct_yr",
    "arm_a_spot_drag_pct_yr", "turnover_a", "turnover_b", "turnover_reduction_pct", "stamps_positions_differ",
}
_B1_VOLUME_PREFLIGHT_KEYS = _B1_VOLUME_ENGAGEMENT | _B1_HOURLY_RV_ANCHORS | _ARM_A_BAR_KEYS | {"arm_a_var_trials"}


def test_the_b1_volume_subjects_declare_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count():
    trial, preflight = subjects.SUBJECTS["b1-volume-confirmation"], subjects.SUBJECTS["b1-volume-confirmation-preflight"]
    assert (len(_B1_VOLUME_METRIC_KEYS), len(_B1_VOLUME_PREFLIGHT_KEYS)) == (43, 24)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        "b1-volume-confirmation", (240,), _B2_ASSETS, _B1_VOLUME_SPEC, (42, 7, 1234),
    )
    assert trial.build is subjects._build_b1_volume_confirmation and trial.metric_keys == _B1_VOLUME_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b1_volume_confirmation_verdict, _B1_VOLUME_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B1", 4)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        "b1-volume-confirmation-preflight", (240,), _B2_ASSETS, _B1_VOLUME_SPEC, (42,),
    )
    assert preflight.build is subjects._build_b1_volume_confirmation_preflight
    assert preflight.metric_keys == _B1_VOLUME_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


def test_the_b1_volume_dispersion_reads_records_45_46_and_48s_registered_sharpes():
    assert (
        subjects._B1_VOLUME_RECORDED_PER_PERIOD_SHARPES
        == (0.02374, 0.02959, 0.030191886721210086)
        == tuple(_trials()[n]["metrics"]["per_period_sharpe_4h"] for n in (45, 46, 48))
    )
```

  The rule test is trial 3's, `test_the_b1_hourly_rv_rule_maps_its_metrics_to_a_verdict_or_a_stop`, as `test_the_b1_volume_rule_maps_its_metrics_to_a_verdict_or_a_stop` over `subjects._b1_volume_confirmation_verdict`, its dict `_B1_VOLUME_ADOPTING` equal to `_B1_HOURLY_RV_ADOPTING` with `"stamps_directions_differ": 9` in place of `"stamps_weights_differ": 9`, and its sixteen rows the same changes, verdicts and ids, the two stop rows on `stamps_directions_differ` named `the-directions-never-differ` and `the-directions-read-before-passes`. The register test, `test_the_b1_volume_subject_registers_each_metric_from_its_own_call`, has trial 3's register test's two parametrisations and shape; its own build and its fixture checks are these:

```python
    root = _b1_volume_dataset(tmp_path)
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, root, registry)
    h4_ts, h4_prices, volumes = subjects._b1_volume_reads(
        ObservedReader(root), "ohlc-test", None, None, False, subject="b1-volume-confirmation"
    )
    n = len(h4_ts) - 1
    k16 = next(k for k in range(n) if h4_ts[k] >= datetime(2016, 1, 1, tzinfo=UTC))
    fed = _ffill_btc(h4_prices)
    confirm = confirmations_by_asset(fed, h4_prices, h4_ts, volumes, lookback=180, min_cell_obs=100)
    weights_a = _inverse_vol_weights(fed, lookback=180)
    union_idx = list(range(len(h4_ts)))
    asset_ts = {a: [k for k, p in enumerate(fed[a]) if p is not None] for a in _B2_ASSETS}
    books = [a2_book_returns(fed, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_a = [_asset_directions_a2(fed, union_idx, asset_ts, config=config) for config in _B1_HOURLY_RV_ARMS]
    confirmed = [asset_directions_confirmed(fed, union_idx, asset_ts, confirm, config=config) for config in _B1_HOURLY_RV_ARMS]
    directions_b = [directions for directions, _ in confirmed]
    arms_b = [a2_positions_on_directions(weights_a, d, book["vol_target_positions"]) for d, book in zip(directions_b, books)]
    arm_a, arm_b = (
        {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(n)] for a in _B2_ASSETS}
        for arms in ([book["asset_positions"] for book in books], arms_b)
    )
    returns = {a: _asset_returns(fed[a]) for a in _B2_ASSETS}
    net_a, net_b = (net_of_cost(arm, returns, cost_per_side=0.006) for arm in (arm_a, arm_b))
    net_a_x15, net_b_x15 = (net_of_cost(arm, returns, cost_per_side=1.5 * 0.006) for arm in (arm_a, arm_b))
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)

    assert fed["BTC"] != h4_prices["BTC"]
    assert any(not accepted for a in _B2_ASSETS if a != "BTC" for accepted in confirm[a][180:])
    assert directions_b != directions_a and net_b != net_a and net_b[k16:] != net_a[k16:]
    assert book_turnover(arm_b) != book_turnover(arm_a)
    assert all(b <= a for da, db in zip(directions_a, directions_b) for s in _B2_ASSETS for a, b in zip(da[s], db[s]) if a is not None)
    assert all(arm_b[a][k] <= arm_a[a][k] for a in _B2_ASSETS for k in range(n))
```

  and the rest is trial 3's register test from `def kill_bar` to the line before its `expected = {`, with these changes alone: `confirm_calls = _recording(monkeypatch, "confirmations_by_asset", lambda arguments, result: result)` beside the three recordings, and `assert [(arguments["lookback"], arguments["min_cell_obs"]) for arguments, _ in confirm_calls] == [(180, 100)]` beside their assertions; the invocation `--subject b1-volume-confirmation`, `--iteration iter-178 --family B1 --n-trials 4 --variant B1-volume-confirm-a2eq-v1`; the outcome's `_B1_VOLUME_METRIC_KEYS`, `_B1_VOLUME_NO_VERDICT`, `{f"{a}/EUR/240.parquet" for a in _B2_ASSETS}` and `n_trials_in_family == 4`; both variances over `[0.02374, 0.02959, 0.030191886721210086, sharpe(<net>)]` and the bars' `"n_trials": 4`; the `tv_a, tv_b` line dropped. Then `expected = {` with the thirty-six entries from `"ann_sharpe_noc"` to `"turnover_reduction_pct"` as trial 3's writes them, and:

```python
        "stamps_positions_differ": sum(any(arm_b[a][k] != arm_a[a][k] for a in _B2_ASSETS) for k in range(n)),
    }
    own_stamps = {a: [h4_ts[k] for k in asset_ts[a]] for a in _B2_ASSETS}
    per_year = {str(i + 1): entry_events_per_year(events, own_stamps) for i, (_, events) in enumerate(confirmed)}
    counts = [c for arm in per_year.values() for by_asset in arm.values() for by_lookback in by_asset.values() for c in by_lookback.values()]
    events, rejected = sum(c[0] for c in counts), sum(c[1] for c in counts)
    differ = directions_differ_per_year(directions_a, directions_b, h4_ts)
    expected |= {
        "entry_events_per_year": per_year, "entry_events": events, "entry_events_rejected": rejected, "share_rejected": rejected / events,
        "stamps_directions_differ": sum(differ.values()), "stamps_directions_differ_per_year": differ,
    }
    assert set(expected) == _B1_VOLUME_METRIC_KEYS
    assert stored == expected
```

  The pre-flight, the refusals and the windowed read:

```python
def test_the_b1_volume_preflight_reads_arm_a_and_the_entry_events_and_never_builds_arm_bs_positions(tmp_path, monkeypatch):
    root = _b1_volume_dataset(tmp_path)
    trial = subjects.SUBJECTS["b1-volume-confirmation"].build(ObservedReader(root), "ohlc-test", None)

    def arm_b_positions(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions")

    monkeypatch.setattr(subjects, "a2_positions_on_directions", arm_b_positions)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)
    metrics = subjects.SUBJECTS["b1-volume-confirmation-preflight"].build(ObservedReader(root), "ohlc-test", None)

    assert [arguments["n_trials"] for arguments, _ in bars] == [4]
    ints = _ARM_A_BAR_FLAGS | {"entry_events", "entry_events_rejected", "stamps_directions_differ"}
    dicts = {"entry_events_per_year", "stamps_directions_differ_per_year"}
    assert set(metrics) == _B1_VOLUME_PREFLIGHT_KEYS
    assert {key for key, value in metrics.items() if type(value) is int} == ints
    assert {key for key, value in metrics.items() if type(value) is dict} == dicts
    assert {key for key, value in metrics.items() if type(value) is float} == _B1_VOLUME_PREFLIGHT_KEYS - ints - dicts
    assert metrics["stamps_directions_differ"] > 0 and 0 < metrics["entry_events_rejected"] < metrics["entry_events"]
    assert {key: metrics[key] for key in _B1_VOLUME_ENGAGEMENT} == {key: trial[key] for key in _B1_VOLUME_ENGAGEMENT}
    assert (metrics["passes"], metrics["arm_a_var_trials"]) == (trial["arm_a_passes"], trial["arm_a_var_trials"])
    assert {key: metrics[key] for key in _B1_HOURLY_RV_ANCHORS} == {key: trial[key] for key in _B1_HOURLY_RV_ANCHORS}


@pytest.mark.parametrize("name", ["b1-volume-confirmation", "b1-volume-confirmation-preflight"])
def test_a_b1_volume_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)

    result = runner.invoke(app, [*_b1_volume_args(name, tmp_path, dataset="ohlc-rolling"), "--as-of", "2026-10-03"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} evaluates a frozen set's 4h series and their volumes, never the rolling dataset as of a day: drop --as-of" in (
        result.output
    )


def test_b1_volume_names_a_240_file_without_a_volume_column(tmp_path, monkeypatch):
    root = _b1_volume_dataset(tmp_path)
    path = root / "ohlc-test" / "SOL/EUR/240.parquet"
    pl.read_parquet(path).drop("volume").write_parquet(path)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "ohlc-test/SOL/EUR/240.parquet" in result.output and '"volume" not found' in result.output


def _a_volume_set(path: Path, value: float | None) -> datetime:
    frame = pl.read_parquet(path)
    volumes, k = frame["volume"].to_list(), frame.height // 2
    volumes[k] = value
    frame.with_columns(volume=pl.Series(volumes, dtype=frame.schema["volume"])).write_parquet(path)
    return frame["ts"][k]


@pytest.mark.parametrize(
    ("value", "named"),
    [
        pytest.param(0.0, "volume must be a finite number above 0, got 0.0 at ", id="zero-volume"),
        pytest.param(None, "no volume where the close is present at ", id="null-volume"),
    ],
)
def test_b1_volume_refuses_a_volume_it_cannot_gate_naming_the_asset_and_stamp(tmp_path, monkeypatch, value, named):
    root = _b1_volume_dataset(tmp_path)
    stamp = _a_volume_set(root / "ohlc-test" / "ETH/EUR/240.parquet", value)
    _anchor(monkeypatch, root)
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"b1-volume-confirmation over the full history: ETH: {named}{stamp.isoformat()}" in result.output
    assert calls == []


def test_b1_volume_refuses_a_build_whose_arm_a_never_trades(tmp_path, monkeypatch):
    _anchor(monkeypatch, _b1_volume_dataset(tmp_path))
    _arm_a_flat(monkeypatch)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "b1-volume-confirmation over the full history: turnover_a is 0.0" in result.output


@pytest.mark.parametrize("name", ["b1-volume-confirmation", "b1-volume-confirmation-preflight"])
def test_a_b1_volume_build_without_an_entry_event_is_refused(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _b1_volume_dataset(tmp_path))
    real = subjects.asset_directions_confirmed

    def no_events(*args, **kwargs):
        directions, events = real(*args, **kwargs)
        return directions, {asset: dict.fromkeys(by_lookback, []) for asset, by_lookback in events.items()}

    monkeypatch.setattr(subjects, "asset_directions_confirmed", no_events)

    result = runner.invoke(app, _b1_volume_args(name, tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the full history: entry_events is 0, and share_rejected divides by it" in result.output


@pytest.mark.parametrize(("start", "bars", "message"), _B1_UNREADABLE_HISTORIES)
def test_a_b1_volume_history_the_bar_cannot_read_is_refused_before_the_arms_and_the_volume_reads(
    tmp_path, monkeypatch, start, bars, message
):
    _anchor(monkeypatch, _b1_volume_dataset(tmp_path, start=start, bars=bars))
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)
    read_series, read = ObservedReader.read_series, []

    def recording_read(self, dataset, relpath, window=None):
        read.append(relpath)
        return read_series(self, dataset, relpath, window)

    monkeypatch.setattr(ObservedReader, "read_series", recording_read)

    result = runner.invoke(app, _b1_volume_args("b1-volume-confirmation", tmp_path))

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "b1-volume-confirmation over the full history: " in result.output and message in result.output
    assert calls == [] and sorted(read) == sorted(f"{a}/EUR/240.parquet" for a in _B2_ASSETS)


def test_b1_volume_reads_its_volumes_under_the_unions_window(tmp_path, monkeypatch):
    root = _b1_volume_dataset(tmp_path)
    first, last = _B1_START + timedelta(hours=4 * 100), _B1_START + timedelta(hours=4 * (_B1_BARS - 1))
    window = (str(first), str(last))
    read_series, reads = ObservedReader.read_series, []

    def recording_read(self, dataset, relpath, window=None):
        reads.append((relpath, window))
        return read_series(self, dataset, relpath, window)

    monkeypatch.setattr(ObservedReader, "read_series", recording_read)

    h4_ts, h4_prices, volumes = subjects._b1_volume_reads(
        ObservedReader(root), "ohlc-test", window, None, False, subject="b1-volume-confirmation"
    )

    assert sorted(reads) == sorted((f"{a}/EUR/240.parquet", window) for a in _B2_ASSETS for _ in range(2))
    assert (h4_ts[0], h4_ts[-1]) == (first, last)
    assert all([v is not None for v in volumes[a]] == [p is not None for p in h4_prices[a]] for a in _B2_ASSETS)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00134 && uv run pytest tests/test_research_command.py -k "b1_volume or ruled_subjects" -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt`
Expected: each new `b1_volume` case and the kill-bar test's `[b1-volume-confirmation]` row fail on `AttributeError: module 'cli.research.subjects' has no attribute '_b1_volume_reads'` or a sibling name, or on `KeyError: 'b1-volume-confirmation'`; `test_the_ruled_subjects_declare_their_families_and_trial_counts` fails on its literal's `AssertionError`, `SUBJECTS` declaring no `b1-volume-confirmation` yet; the kill-bar test's `[b1-hourly-rv]` and `[b2-funding-derisk]` rows pass.

- [ ] **Step 3: Implement in `cli/research/subjects.py`** — the Produces names, each with the spec's values:
  - The three literals, each with the one-line reason it is a literal (records 45, 46 and 48's registered values, record 48's every digit its writer stored; the family's count at this trial, records 45, 46 and 48 and itself; the thin-cell rule's 100). **Author's call**: the SPA grid is trial 3's `_B1_HOURLY_RV_GRID`, reused — the same six cells in the same order, the headline first — as D10 takes trial 3's form.
  - `_b1_volume_reads`: `if as_of is not None:` on its own line, refusing before any read with `f"{subject} evaluates a frozen set's 4h series and their volumes, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset"`; `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)`; `_b1_refuse_window(subject, h4_ts, window)` on its own line; per asset of `_ASSETS` `reader.read_series(dataset, f"{asset}/EUR/240.parquet", window=window)`, its `ts` and `volume` columns read as `frame["volume"].to_list()` on one line inside the `try`, a `pl.exceptions.PolarsError` a `SubjectError` naming `f"{dataset}/{relpath}: {exc}"`; the volumes mapped onto the union by `ts`, `None` where the asset has no bar.
  - `_b1_volume_inputs`: `fed = _ffill_btc(h4_prices)`; `confirm = confirmations_by_asset(fed, h4_prices, h4_ts, volumes, lookback=_B1_LOOKBACK, min_cell_obs=_B1_VOLUME_MIN_CELL_OBS)` next, its price validation refusing a bad close before `_asset_returns` divides by it; `returns`; `weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)`; `union_idx = list(range(len(h4_ts)))` and `asset_ts`, the indices where `fed[a]` holds a price, as `a2_book_returns` builds them; `own_stamps` the stamps at those indices; per arm of `_B1_A2_ARMS` its `A2Config` (arm A's) bound to a name, `a2_book_returns(fed, config=<it>)` for the positions and `vol_target_positions`, `_asset_directions_a2(fed, union_idx, asset_ts, config=<it>)` and `asset_directions_confirmed(fed, union_idx, asset_ts, confirm, config=<it>)`; `arm_a` the per-asset mean — no position or return of arm B.
  - `_b1_volume_arm_a`: trial 3's `_b1_hourly_rv_arm_a` over these inputs, `arm_a_var_trials = statistics.variance([*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, sharpe(net_a)])`, `n_trials=_B1_VOLUME_N_TRIALS`.
  - `_b1_volume_engagement`: `entry_events_per_year` per arm under `str(i + 1)`; the totals; `if events == 0:` on its own line, a `ValidationError` `"entry_events is 0, and share_rejected divides by it"`; `share_rejected`; `directions_differ_per_year(directions_a, directions_b, h4_ts)` and its sum — D8's six keys.
  - `_b1_volume_metrics`: `turnover_a = book_turnover(arm_a)` and `if turnover_a == 0:` on its own line, a `ValidationError` `f"turnover_a is {turnover_a}, and turnover_reduction_pct divides by it"`, then the engagement — both before any bar; arm A's half; arm B per arm `a2_positions_on_directions(weights_a, directions_b[i], vt_a[i])` on one line, the per-asset mean; `net_b`, `net_b_x15`; `per_period_sharpe_4h = sharpe(net_b)` on its own line; `var_trials = statistics.variance([*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, per_period_sharpe_4h])`; arm B's bar, the five other SPA cells, `k16`, the two head-to-heads; the 43 keys, each from one source as D11 lists them, `stamps_positions_differ` by `_b1_hourly_rv_metrics`' expression, `spot_drag_pct_yr` and `arm_a_spot_drag_pct_yr` as `turnover / n * _B1_COST_PER_SIDE * PPY_4H`.
  - `_b1_volume_preflight_metrics`: the engagement first; arm A's bar from `_b1_volume_arm_a(inputs)`, the trial's own call, its ten keys as `_b1_hourly_rv_preflight_metrics` writes them, flags as int; `arm_a_var_trials`; the seven anchors over `net_a`, `bench` and arm A's turnover.
  - `_b1_volume_build`: the reads, then the inputs and `compute` inside one `try`, `(AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError)` a `SubjectError` `f"{_b2_over(subject, window)}: {exc}"`, as `_b1_hourly_rv_build` does; the two builders over it.
  - `_b1_volume_confirmation_verdict`: spec D10's code block verbatim, under trial 3's comment form naming spec 00134 D10.
  - `_B1_VOLUME_METRIC_KEYS` (43) and `_B1_VOLUME_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {…the seven anchors…, "arm_a_var_trials", …the six engagement keys…}` (24); the two `SUBJECTS` entries exactly as D11 declares them, `no_verdict` the spec's text.

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row's list now ends `…, `b1-hourly-rv-preflight` (…; it has no rule, so its run is kept with `--reading`), `b1-volume-confirmation` (the A2 4h ensemble against the same ensemble with each breakout entry accepted only on a bar whose volume is at or above its hour-of-week norm, exits always taken; the 4h series and their volumes of `--dataset`, a frozen set only) or `b1-volume-confirmation-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar, the entry events and the stamps whose directions differ, with no return of the volume-confirmed book; it has no rule, so its run is kept with `--reading`).`, in the row's own voice and backticks, no internal term.

- [ ] **Step 5: Run them to verify they pass** — Step 2's command, then `tests/test_alpha_b1_volume.py` and `tests/test_research_command.py` whole, `-m "not data"`, in parts each under 600 s; then `uv run pytest tests/test_research_command.py -k "b1_volume or ruled_subjects or b1-volume" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt`, and each new case at 10 s or more joins `tests/slow-cases.txt` at its sorted place, `tests/test_slow_cases.py` then passing; then the direct readers of the four changed paths, `-m "not data"`; then the gate.

- [ ] **Step 6: Commit**

```bash
git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt
git commit -F - <<'EOF'
feat(research): the b1-volume-confirmation subject and its pre-flight twin — both arms, the bar at the family's dispersion and count, the head-to-head and the entry events

<the task's pytest result line, pasted from its run>
<probe skipped: slow case — each listed case, by node id>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 7: Probes** — `--file cli/research/subjects.py`; control `s/^def _b1_volume_confirmation_verdict(/def _b1_volume_confirmation_verdict_gone(/` for the rule test and `s/^def _build_b1_volume_confirmation(/def _build_b1_volume_confirmation_gone(/` for every other (`SUBJECTS` names both, so the module no longer imports); each row one probe per case it names, expected `KILLED`, a case `tests/slow-cases.txt` lists skipped and recorded. The two subjects' `-evaluates` contract rows and shared-defaults rows are new rows of existing tests, neither a test function nor a refusal case, so no new guard (Global Constraints' probe line): they are not probed.

| node id under `tests/test_research_command.py::` | mutation |
| -- | -- |
| `test_the_b1_volume_subjects_declare_the_4h_grid_…` | `metric_keys=_B1_VOLUME_PREFLIGHT_KEYS,` made `metric_keys=_B1_VOLUME_METRIC_KEYS,` |
| `test_the_b1_volume_dispersion_reads_records_45_46_and_48s_registered_sharpes` | `0.030191886721210086)` made `0.0301918867212)` on the literal's line |
| `test_the_b1_volume_rule_maps_…[<id>]`, each within `/^def _b1_volume_confirmation_verdict(/,/^[^ #]/` | `m["turnover_b"] < m["turnover_a"]` made `<=` (`turnover-tied`); `> 0` made `>= 0` (`mean-at-exactly-0`); `m["head_to_head_spa_p_full"] < 0.05` made `<= 0.05` (`p-at-exactly-0.05`); ` and m["spa_p_decisive_b102_s42"] < 0.05` made ` and True` (`block-102-p-at-exactly-0.05`, `row-2-the-block-102-spa-fails`); `m["stamps_directions_differ"] == 0` made `False` (`the-directions-never-differ`); `not m["arm_a_passes"]` made `False` (`arm-a-fails-its-bar`); `head_to_head_mean_outperf_full` made `head_to_head_mean_outperf_2016` (`outperforms-from-2016-alone`); `if not m["passes"]:` made `if False:` (`row-5-arm-b-fails-its-bar`) |
| `test_the_ruled_subjects_declare_their_families_and_trial_counts` | within `/"b1-volume-confirmation": Subject(/,/^    ),/`, `family="B1",` made `family="B2",` |
| `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b1-volume-confirmation]` | within `/^def _b1_volume_metrics(/,/^def /`, `n_trials=_B1_VOLUME_N_TRIALS,` made `n_trials=1 + _B1_VOLUME_N_TRIALS,` |
| `test_a_b1_volume_subject_refuses_as_of_before_any_read[<each>]` | within `/^def _b1_volume_reads(/,/^def /`, `if as_of is not None:` made `if False:` |
| `test_b1_volume_names_a_240_file_without_a_volume_column` | within the same range, `except pl.exceptions.PolarsError as exc:` made `except ZeroDivisionError as exc:` |
| `test_b1_volume_refuses_a_volume_it_cannot_gate_…[<each>]` | within `/^def _b1_volume_build(/,/^def /`, `AlphaError, ` dropped from the caught tuple by substitution |
| `test_b1_volume_refuses_a_build_whose_arm_a_never_trades` | `if turnover_a == 0:` made `if False:` |
| `test_a_b1_volume_build_without_an_entry_event_is_refused[<each>]` | `if events == 0:` made `if False:` |
| `test_a_b1_volume_history_the_bar_cannot_read_is_refused_…[<each>]` | within `/^def _b1_volume_reads(/,/^def /`, the `_b1_refuse_window(` line's call made `None` |
| `test_b1_volume_reads_its_volumes_under_the_unions_window` | within the same range, the volume read's `window=window` made `window=None` |
| `test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b1-volume-confirmation-a-zero-close-on-240]` | within `/^def _b1_volume_inputs(/,/^def /`, `s/^\( *\)fed = _ffill_btc(h4_prices)/\1fed = _ffill_btc(h4_prices); _ = [_asset_returns(fed[a]) for a in _ASSETS]/` (the zero close then a `ZeroDivisionError`, a traceback) |
| `test_the_b1_volume_preflight_reads_…` | a slow case: skipped, recorded in the commit — unless step 5 timed it under 10 s, when within `/^def _b1_volume_arm_a(/,/^def /`, `n_trials=_B1_VOLUME_N_TRIALS,` made `n_trials=1 + _B1_VOLUME_N_TRIALS,` |
| `test_the_b1_volume_subject_registers_each_metric_from_its_own_call[<each>]` | slow cases: skipped, recorded in the commit — unless step 5 timed one under 10 s, when it takes arm B's positions built on arm A's directions: within `/^def _b1_volume_metrics(/,/^def /`, the `a2_positions_on_directions(` line's arm-B directions made arm A's, `directions_b` made `directions_a` |

______________________________________________________________________

### Task 4: the data-gated tests over `ohlc-full` — the measured basis and arm A's anchors (D5, D9)

**Files:**
- Create: `tests/test_research_b1_volume_basis.py` (module-marked `data`)
- Modify: `tests/slow-cases.txt`, when Step 2 times the basis test at 10 s or more

**Interfaces:**
- Consumes: Task 3's `_b1_volume_reads`, `_b1_volume_inputs` and `_B1VolumeInputs`' fields `h4_ts`, `h4_prices`, `returns`, `arm_a`; `tests.skip_gates.nothing_found_under`.
- Produces: `test_the_b1_volume_reads_reproduce_the_measured_basis` — the reads alone, run before the hash; `test_the_b1_volume_arm_a_reproduces_record_45s_arm_a` — arm A, run only after Task 5 step 2's hash. Neither computes a return of arm B; the first computes no direction, no flag and no position.

- [ ] **Step 1: Write the failing tests** — every literal copied from the spec's measured basis, never from a run:

```python
"""B1 trial 4's reads half against spec 00134's measured basis, computing no direction, and arm A against record 45's
anchors at the registry's precision."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import net_of_cost
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_BLOCK_HASH = "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69"
_ROWS = {
    "ADA": 16_446, "AVAX": 9_365, "BTC": 27_332, "DOGE": 13_710, "DOT": 12_306,
    "ETH": 23_292, "LINK": 14_267, "LTC": 26_746, "SOL": 10_486, "XRP": 19_423,
}
# The union index of each stamp `_ffill_btc` fills, its stamp, and BTC's own bars before it.
_FILLS = [
    (6, datetime(2013, 9, 14, 8, tzinfo=UTC), 6),
    (26, datetime(2013, 9, 29, 4, tzinfo=UTC), 25),
    (160, datetime(2013, 11, 3, 8, tzinfo=UTC), 158),
    (235, datetime(2013, 11, 16, 4, tzinfo=UTC), 232),
    (9_340, datetime(2018, 1, 12, 0, tzinfo=UTC), 9_336),
    (9_341, datetime(2018, 1, 12, 16, tzinfo=UTC), 9_336),
]
# Per asset over its own bars: the first with 180 prior bars, the smallest 180-bar median volume, the fewest and the most
# observations in a cell, all of them, the first cell to reach 100 earlier observations, and the last of the 42.
_NORM = {
    "ADA": ((2018, 10, 28, 12), 145253.043832995, 385, 388, 16_266, (2020, 9, 27, 12), (2020, 10, 4, 8)),
    "AVAX": ((2022, 1, 20, 12), 574.973046415, 217, 219, 9_185, (2023, 12, 21, 12), (2023, 12, 30, 0)),
    "BTC": ((2013, 11, 7, 8), 2.0, 645, 647, 27_152, (2015, 10, 8, 8), (2015, 10, 19, 0)),
    "DOGE": ((2020, 1, 21, 12), 174459.3690752, 317, 324, 13_530, (2021, 12, 21, 12), (2022, 2, 5, 0)),
    "DOT": ((2020, 9, 17, 16), 7220.07636406, 288, 289, 12_126, (2022, 8, 18, 16), (2022, 8, 25, 12)),
    "ETH": ((2015, 9, 7, 4), 297.74406141500003, 545, 552, 23_112, (2017, 8, 7, 4), (2017, 9, 16, 0)),
    "LINK": ((2019, 10, 25, 12), 2420.1512037700004, 333, 336, 14_087, (2021, 9, 24, 12), (2021, 10, 10, 4)),
    "LTC": ((2013, 12, 4, 8), 51.778360160000005, 608, 642, 26_566, (2015, 11, 11, 8), (2016, 6, 1, 0)),
    "SOL": ((2021, 7, 17, 20), 2022.8965592499999, 243, 246, 10_306, (2023, 6, 17, 20), (2023, 6, 24, 16)),
    "XRP": ((2017, 6, 17, 12), 316059.421934235, 457, 459, 19_243, (2019, 5, 18, 12), (2019, 6, 1, 4)),
}
_H4 = timedelta(hours=4)


def _utc(parts: tuple[int, ...]) -> datetime:
    return datetime(*parts, tzinfo=UTC)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set's 4h files are absent under data/",
)
def test_the_b1_volume_reads_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader = ObservedReader(_DATA_ROOT)
    h4_ts, h4_prices, volumes = subjects._b1_volume_reads(reader, "ohlc-full", None, None, False, subject="b1-volume-confirmation")

    block = reader.block()
    assert compute_hash(block) == _BLOCK_HASH
    assert (len(block["ohlc-full"]["files"]), block["ohlc-full"]["rows"]) == (10, 173_373)
    assert len(h4_ts) == 27_338
    assert (h4_ts[0], h4_ts[-1]) == (datetime(2013, 9, 10, 20, tzinfo=UTC), datetime(2026, 3, 31, 20, tzinfo=UTC))
    present = {asset: [v is not None for v in vs] == [p is not None for p in h4_prices[asset]] for asset, vs in volumes.items()}
    assert present == dict.fromkeys(_ROWS, True)
    assert {asset: sum(v is not None for v in vs) for asset, vs in volumes.items()} == _ROWS
    filled = [k for k in range(1, len(h4_ts)) if h4_prices["BTC"][k] is None]
    assert [(k, h4_ts[k], sum(p is not None for p in h4_prices["BTC"][:k])) for k in filled] == _FILLS

    for asset, (first, smallest, fewest, most, total, first_bound, last_bound) in _NORM.items():
        own = [(t, v) for t, v in zip(h4_ts, volumes[asset], strict=True) if v is not None]
        cells, bound = Counter(), {}
        for j in range(180, len(own)):
            b = own[j][0] + _H4
            cell = (b.hour, b.weekday())
            if cells[cell] >= 100 and cell not in bound:
                bound[cell] = own[j][0]
            cells[cell] += 1
        assert own[180][0] == _utc(first), asset
        assert min(statistics.median(v for _, v in own[j - 180 : j]) for j in range(180, len(own))) == smallest, asset
        assert (len(cells), sorted({hour for hour, _ in cells})) == (42, [0, 4, 8, 12, 16, 20]), asset
        assert (min(cells.values()), max(cells.values()), sum(cells.values())) == (fewest, most, total), asset
        assert (len(bound), min(bound.values()), max(bound.values())) == (42, _utc(first_bound), _utc(last_bound)), asset


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set's 4h files are absent under data/",
)
def test_the_b1_volume_arm_a_reproduces_record_45s_arm_a():
    reads = subjects._b1_volume_reads(ObservedReader(_DATA_ROOT), "ohlc-full", None, None, False, subject="b1-volume-confirmation")
    inputs = subjects._b1_volume_inputs(reads)
    net_a = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.h4_ts) - 1

    assert n == 27_337
    assert round(sharpe(net_a, periods_per_year=2190), 4) == 1.405
    assert round(sharpe(net_a[1380:], periods_per_year=2190), 4) == 1.3716
    assert round(max_drawdown(net_a), 4) == 0.2154
    assert (round(turnover_a, 2), round(turnover_a / n * 0.006 * 2190, 4)) == (146.19, 0.0703)
    assert round(sharpe(bench, periods_per_year=2190), 4) == 1.2128
    assert round(sharpe(bench[1380:], periods_per_year=2190), 4) == 1.2447
```

  **Author's call**: arm A's anchors are checked at the registry's precision against record 45, D9 (b)'s form, not bit for bit against record 48's unrounded figures, which the spec does not pin.

- [ ] **Step 2: Run the basis test** — alone, by node id; the arm-A test is not run before Task 5 step 2.

Run: `mkdir -p .tmp/plan-00134 && uv run pytest tests/test_research_b1_volume_basis.py::test_the_b1_volume_reads_reproduce_the_measured_basis --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt`
Expected at this task (Task 3 committed): pass — a reads half the measured basis already describes; before Task 3, and against the tree at this plan's commit, `AttributeError: module 'cli.research.subjects' has no attribute '_b1_volume_reads'`. A skip is no pass: `data/ohlc-full` is linked in this worktree. At 10 s or more its node id joins `tests/slow-cases.txt` at its sorted place in this task's commit.

- [ ] **Step 3: Consumers, then commit** — the file's direct readers (`bash infra/scripts/consumers.sh --direct tests/test_research_b1_volume_basis.py`) with `-m "not data"`; the two tree walkers over `tests/` whose subject this file carries, its skip gates and its data mark, `uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt` (no other test file this plan writes adds a skip gate or a data mark); the basis test by node id; `tests/test_slow_cases.py` when the list changed; the gate.

```bash
git add tests/test_research_b1_volume_basis.py
# and tests/slow-cases.txt when Step 2 listed the basis test
git commit -F - <<'EOF'
test(research): B1 trial 4's reads against the measured basis, and arm A against record 45's anchors after the hash

<the basis test's pytest result line, pasted from its run>
<probe skipped: slow case — the basis test, when listed>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 4: Probe** — `--file cli/research/subjects.py`, control `s/^def _b1_volume_reads(/def _b1_volume_reads_gone(/` (the test reads the name at call time), mutation `s/frame\["volume"\]/frame["count"]/` (its `grep -c` 1), against `tests/test_research_b1_volume_basis.py::test_the_b1_volume_reads_reproduce_the_measured_basis`, expected `KILLED` — when Step 2 timed it under 10 s; a listed basis test is not probed, its commit recording `probe skipped: slow case`. The arm-A test cannot run before the hash; Task 5 step 4 times it, and probes it there when it runs under 10 s.

- [ ] **Step 5: The reads over Tasks 2–4** — the trio over `<Task 2's commit>^..HEAD`, as CLAUDE.md orders it: `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two (Global Constraints' reads line); every dispatch carries the hash rule (Global Constraints), and each report names the tip it read, the tip Task 5 step 1 diffs from. Task 5 waits until the trio has closed with no open Critical or Important.

______________________________________________________________________

### Task 5: the run, gated on spec 00133's merge (D9, D12)

**Files:** `docs/reference/trial-registry.jsonl` (or, on a stop, `docs/reference/reading-ledger.jsonl`), appended by the command and committed in Task 6; scratch under `.tmp/plan-00134/`.

**Interfaces:**
- Consumes: plan 00133 Task 7's register path — the refusals before the data, the count and the `begin` line under the log's lock, the `end` line before the print, the plain-eval refusal; plan 00133 Task 3's `attempts-init` log in the main checkout and its row in `docs/reference/trial-attempt-logs.txt`; plan 00133 Task 5's `attempt` block on the record; this plan's Task 3 subjects.
- Produces: one appended registry record (or ledger reading), checked; the pre-flight's output and the run's output under `.tmp/plan-00134/`.

- [ ] **Step 1: The gate** — each its own call:
  - `git fetch origin develop`, then `git cat-file -e origin/develop:docs/open-topics/archive/T0222-a-trial-on-an-unmerged-branch-spends-uncounted.md` exits 0: spec 00133 has merged whole, its topic archived by plan 00133's last task in the pull request that carries its count and its plain-eval refusal. Otherwise stop: the run waits.
  - `git merge --no-edit origin/develop`, alone; a conflict keeps both sides; then `tests/test_alpha_b1_volume.py`, `tests/test_research_command.py`, `tests/test_trial_attempts.py`, `tests/test_trial_registry_provenance.py` and `tests/test_decisions_log_ties.py` pass `-m "not data"`, in parts — the run that proves `_b1_volume_args`' command-path cases under plan 00133's Task 7. A failure in this plan's tests after the merge is fixed by a commit, never an amend.
  - The reads over Tasks 2–4 (Task 4 step 5) have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names in its report> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00134-b1-volume-confirmation-design.md` exits 0; with no report naming a tip, stop: the reads come first. The merge, or a fix, changes it — a read of that diff comes first, its `re-review` within the branch's two (Global Constraints' reads line), and this check then names its tip.
  - Arm A's code path: `git log --oneline 838adb43291183a5bc320fba804be4d4eb777ed0..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/registry/observed.py cli/ohlc` lists Task 2's commit and its fixes alone; any other commit is named in the task report, the anchors at step 5 deciding whether it moved arm A.

- [ ] **Step 2: D12 step 1, the spec hash** — `sha256sum docs/specs/00134-b1-volume-confirmation-design.md`; its value, pasted from that call, is the `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.

- [ ] **Step 3: D12 step 2, the develop check** — `git fetch origin develop`, then `git diff --quiet origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0, so an append chains onto develop's last line; if not, develop is merged first (step 1's checks again). It runs again immediately before step 6's `--register` and before a stop's `--reading`; a failure there is the owner's question before any append.

- [ ] **Step 4: The held-back data tests** (D9's order: after the hash, before the pre-flight's anchors) — `uv run pytest tests/test_research_b1_volume_basis.py --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt` reads `2 passed`, never a skip; then `-m data` over the direct readers of `cli/research/subjects.py` and `cli/alpha/b1_volume.py`, the skip count read, among them `tests/test_b1_records_reproduce.py::test_the_b1_subject_reproduces_its_record[record-46]` passed, never skipped (record 45's case needs `data/ohlc-15m`, not linked here, and is the nightly's). A failure among them is the owner's question before the pre-flight. The arm-A test's own time is noted: at 10 s or more its node id joins `tests/slow-cases.txt` in Task 6's commit, recorded `probe skipped: slow case`; under 10 s it is probed now — `--file cli/research/subjects.py`, control `s/^def _b1_volume_inputs(/def _b1_volume_inputs_gone(/`, mutation within `/^def _b1_volume_inputs(/,/^def /` `in _B1_A2_ARMS` made `in _B1_A2_ARMS[:1]` — expected `KILLED`.

- [ ] **Step 5: D12 step 3, the pre-flights** — `mkdir -p .tmp/plan-00134 && uv run zcrypto research eval --subject b1-volume-confirmation-preflight --dataset ohlc-full > .tmp/plan-00134/preflight.out 2>&1`, then the check, which reads the block, then the seven anchors, then `passes`, then the engagement, and exits 1 on a stop:

```
uv run python - <<'EOF'
import json, sys
from pathlib import Path
from cli.registry.record import compute_hash
out = Path(".tmp/plan-00134/preflight.out").read_text(); run = json.JSONDecoder().raw_decode(out[out.index("{"):])[0]; m = run["metrics"]
block = compute_hash(run["datasets"]); print("block", block)
if block != "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69": sys.exit("the inputs' block differs from the spec's")
anchors = {"arm_a_ann_sharpe_noc": (1.405, 4), "arm_a_ann_sharpe_noc_decisive": (1.3716, 4), "arm_a_max_drawdown": (0.2154, 4),
           "arm_a_spot_drag_pct_yr": (0.0703, 4), "benchmark_ann_sharpe_noc": (1.2128, 4), "benchmark_ann_sharpe_noc_decisive": (1.2447, 4),
           "turnover_a": (146.19, 2)}
off = {k: m[k] for k, (v, d) in anchors.items() if round(m[k], d) != v}
if off: sys.exit(f"arm A does not reproduce record 45's arm A: {off}")
print({k: m[k] for k in ("dsr", "dsr_pass", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes", "arm_a_var_trials")})
if m["passes"] != 1: sys.exit("arm A fails its bar")
years = {}
for by_asset in m["entry_events_per_year"].values():
    for by_lookback in by_asset.values():
        for counts in by_lookback.values():
            for year, (events, rejected) in counts.items():
                e, r = years.get(year, (0, 0)); years[year] = (e + events, r + rejected)
print("entry_events", m["entry_events"], "rejected", m["entry_events_rejected"], "share", m["share_rejected"])
print("years with events and none accepted", sorted(y for y, (e, r) in years.items() if e > 0 and r == e))
print("stamps_directions_differ", m["stamps_directions_differ"], m["stamps_directions_differ_per_year"])
sys.exit(0 if m["stamps_directions_differ"] > 0 else "no direction differs at any stamp: a dead knob")
EOF
```

  Expected now: it cannot run (no subject) — it runs at this step alone. A block that differs, an anchor off, `passes` 0 or `stamps_directions_differ` 0 is D9's or D8's instrument finding — stop: no run, no verdict, the trial unspent. The stop is kept as a reading, after step 3's check: `uv run zcrypto research eval --subject b1-volume-confirmation-preflight --dataset ohlc-full --reading --iteration iter-178 --spec-hash <step 2's sha256> --notes "<what failed, quoted from the check's output; no verdict, the trial unspent>"`; Task 6 records it. A year with events and none accepted stops nothing; it is quoted in the notes and the entry.

- [ ] **Step 6: D12 step 4, the trial** — one run, by the owner or on their word, after step 3's check: `uv run zcrypto research eval --subject b1-volume-confirmation --dataset ohlc-full --register --iteration iter-178 --family B1 --n-trials 4 --variant B1-volume-confirm-a2eq-v1 --spec-hash <step 2's sha256> --notes "<below>" > .tmp/plan-00134/trial4.out 2>&1`, then `cat .tmp/plan-00134/trial4.out`. No `--verdict` and no plain eval, before or after (D12). The notes, written before the run, name only what is fixed before it: `subject b1-volume-confirmation over ohlc-full, full history, no as-of; arm B the A2 4h ensemble with each breakout entry accepted only on a bar whose volume is at or above its hour-of-week norm, exits always taken, on arm A's weights and vol scalar; arm A the same ensemble unchanged, both built in the run; var_trials the sample variance of records 45, 46 and 48's registered per-period Sharpes 0.02374, 0.02959 and 0.030191886721210086 and arm B's, n_trials 4, the DSR leg binding; pre-flight: block ff2e5700…, arm A <the seven anchors>, passes 1, entry_events <n>, rejected <r>, stamps_directions_differ <s>, <years with events and none accepted, or none>; park variants, pre-registered: on the matrix's third row hour-of-day cells only (6) and the mean in place of the median, on its second the block-sensitivity finding; the matrix pre-registered by the spec's sha256 <step 2's value>`. A refusal from the count — an attempt in B1 that never landed, or bucket B spent — comes before the fit or after the print, naming each orphan the count counts or the bucket's spent figure, and the trial goes back to the owner (D12) through T0022: Task 6 runs its refusal arm, with no record and no reading. A stop by the rule writes a reading carrying its attempt, which counts 0.

- [ ] **Step 7: The record's checks** — on a record, each failure the owner's question before Task 6:

```
uv run python - <<'EOF'
import json, sys
from pathlib import Path
from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
SPEC_HASH = "<step 2's sha256>"
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1]); m = r["metrics"]
out = Path(".tmp/plan-00134/trial4.out").read_text(); printed = json.JSONDecoder().raw_decode(out[out.index("{"):])[0]["metrics"]
subject = SUBJECTS["b1-volume-confirmation"]
checks = {
    "spec_hash": r["spec_hash"] == SPEC_HASH,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69",
    "invocation": {k: r["invocation"][k] for k in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
    == {"subject": "b1-volume-confirmation", "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"]) == ("B1", 4, "B1-volume-confirm-a2eq-v1", "iter-178", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
EOF
```

  Expected now: it cannot run — no record exists, and `attempt` is spec 00133's key. `printed` is the first JSON object the run printed, the text after it left unread. `counted` is printed, never checked: a non-empty one, an orphan the count admitted elsewhere in bucket B, is no failure of the run — Task 6's header and T0016's line name it — and goes in the report. On a stop by the rule, the ledger's last line is checked instead: its subject `b1-volume-confirmation`, its outcome the `no_verdict` text, its `attempt` non-null, its `spec_hash` step 2's.

No commit: the appended line lands in Task 6's commit, with the decisions-log header that names it and the literal that pins its subject — `tests/test_decisions_log_ties.py::test_the_committed_decisions_logs_tie_every_verdict_to_its_record` and plan 00133's `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` hold only over the three together (**Author's call**).

______________________________________________________________________

### Task 6: the verdict — the record, the decisions log, T0022, T0016 and on an adopt T0123 (D12, D13)

**Files:**
- Modify: `docs/reference/trial-registry.jsonl` (appended by Task 5), `tests/test_trial_registry_provenance.py`, `docs/research/10.phase4-decisions.md`, `docs/open-topics/T0022-b1-intraday-seasonality-family.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/slow-cases.txt` (when step 4 of Task 5 says so); on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md`; on a stop `docs/reference/reading-ledger.jsonl` in the registry's place; on a refusal from the count, T0022 and the index, and T0016 when the refusal came after the print

**Interfaces:**
- Consumes: plan 00133 Task 8's `LANDED_N_TRIALS: dict[str, int] = {"b1-hourly-rv": 3}` and `test_each_landed_subjects_n_trials_is_frozen_at_its_literal`; plan 00133 Task 9's `(attempts counted: <log8>#<id>, …)` tie in `tie_findings`; this plan's Task 5 record, checked.
- Produces: the records commit.

On a refusal from the count (Task 5 step 6) there is no record and no reading: steps 1, 4, 5, 6 and 8 run, step 4 on its refusal arm, step 6 staging T0022 and the index — and T0016 when the refusal came after the print, `.tmp/plan-00134/trial4.out` holding the run's printed metrics before it — under `docs(open-topics): B1 trial 4 refused by the count; T0022 holds the refusal for the owner`.

- [ ] **Step 1: The PR** — the unpushed range takes its `pre-review`, then the push, its own call, then the PR through `open-pr` (the change-index row at create time), so its number exists for the entry: title `feat(research): iter-178 — B1 trial 4, volume confirmation of the A2 ensemble's breakout entries`.

- [ ] **Step 2: The decisions-log entry**, at the end of the `[iter-178]` entries, written with `iteration-closeout` loaded. The matrix is printed from the spec the record pins, `sed -n '/^| Kill bar/,/^Every quantity/p' docs/specs/00134-b1-volume-confirmation-design.md`, and the row read off the record's stored keys beside its stored verdict. The header: `[iter-178] Verdict — B1 trial 4 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B1 n=4)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry (spec 00133 D10); its text to its first `. ` holds no verdict word but its own. The body: the row that fired with the six keys the matrix reads, unrounded; `var_trials` and its four inputs, `n_trials` 4, the DSR leg (`dsr_corrected`, `dsr_pass`); the pre-flight's block, anchors and `passes`; the engagement proof — `entry_events`, `entry_events_rejected`, `share_rejected`, `stamps_directions_differ`, the years with events and none accepted, `stamps_positions_differ`, `turnover_a`, `turnover_b`, `turnover_reduction_pct`; on a park its variants (the third row: hour-of-day cells only (6), the mean in place of the median; the second: the block-sensitivity finding); on an adopt D13's path. On a stop the entry is `[iter-178] B1 trial 4 — instrument finding, the trial unspent (reading <its id>)`, naming what failed, quoted from the check or the record.

- [ ] **Step 3: The landed subject's literal** — on a record only: `LANDED_N_TRIALS` becomes `{"b1-hourly-rv": 3, "b1-volume-confirmation": 4}` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts becomes the same dict — the subject's first landed record adds its row in the PR that lands it (spec 00133's literal rule). The arm-A data test's id joins `tests/slow-cases.txt` when Task 5 step 4 timed it at 10 s or more.

- [ ] **Step 4: The topics**, per `topic-ops`. T0022's findings take trial 4 — its record id, verdict, the row that fired, `var_trials`, the engagement figures — or, on a stop, the instrument finding and its reading id. Its `ripe_when`, an activity, is rewritten for what remains, each with a check that prints at least 1 once it happens and nothing when this step commits it, run then and its output read, shown matching a sample header in `iteration-closeout`'s form:
  - reject: `an activity: the owner picks B1's next step after trial 4's reject — candidate C, a park variant of trial 3, or closing the family as attributed out — recorded in the decisions log; check: git grep -c -E '^\[iter-[0-9]+\] B1.s next step after trial 4' -- docs/research/10.phase4-decisions.md prints at least 1`;
  - park: the same activity after trial 4's park, its variants (hour-of-day cells only (6); the mean in place of the median; on the second row the block-sensitivity finding) each a new trial of the shared budget, with the same check;
  - adopt: `an activity: the P1 combination trial over record 47's book carrying trial 4's arm B is picked for an iteration; check: git grep -c -E '^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book' -- docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md prints at least 1`, the second log the one `iteration-closeout` routes a combination of sleeves to, and `[^.]*` holding the match to an entry's header, which ends at its first `. `, since step 2's verdict entry names D13's path on the same line; and T0123's `ripe_when` gains `— registry trial <N>, B1 trial 4's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries it adopts`, written in this PR so no tree holds the adopt without it (D13);
  - stop: `an activity: the owner decides B1's next step after trial 4's instrument finding, recorded in the decisions log; check: git grep -c -E '^\[iter-[0-9]+\] B1.s next step after trial 4.s instrument finding' -- docs/research/10.phase4-decisions.md prints at least 1`;
  - refusal from the count: T0022's findings take the refusal as `.tmp/plan-00134/trial4.out` printed it, each orphan or the spent bucket it named, and, when it came after the print, the metrics printed before it, a look no record carries; `an activity: the owner rules on B1's fourth trial after the count refused it — a new subject declaring the count its orphans need, or bucket B's spent budget — recorded in the decisions log; check: git grep -c -E '^\[iter-[0-9]+\] B1 trial 4 after the count.s refusal' -- docs/research/10.phase4-decisions.md prints at least 1`; T0016 unchanged on a refusal before the fit, and after the print its budget line counts what the refusal counted — each orphan it names, or the attempts that never landed in the bucket's spent figure — named on that line.
  T0022's next steps say the same. T0016's budget line reads `B1 spent 4, 21 remain` — less one more for each orphan the record's `attempt.counted` lists, named on that line — and its B1 line under `## Done so far` names trial 4 and its verdict; on a stop T0016 is unchanged, 22 remaining. `uv run python infra/scripts/topics-index.py` re-renders the index.

- [ ] **Step 5: Tests and gate** — the direct readers of each path the commit stages, run as the Global Constraints run them (`consumers.sh --direct`, `-m "not data"`, a mount-reading case deselected by node id and named), `tests/test_decisions_log_ties.py` among them, and `tests/test_slow_cases.py` when the list changed, pass; `uv run pre-commit run -a` until clean.

- [ ] **Step 6: Commit**

```bash
git add docs/reference/trial-registry.jsonl tests/test_trial_registry_provenance.py docs/research/10.phase4-decisions.md docs/open-topics/T0022-b1-intraday-seasonality-family.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md
# and, as the outcome makes them: tests/slow-cases.txt, docs/open-topics/T0123-sleeve-promotion-path.md; on a stop the ledger in the registry's place
git commit -F - <<'EOF'
docs(research): B1 trial 4 registered — <verdict>; T0022 and T0016 after it, the shared B budget at <the remaining figure step 4 wrote on T0016's budget line>

<the tie and provenance tests' pytest result line, pasted from its run>
<probe skipped: slow case — the arm-A data test, when listed>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

  On a stop the subject line is `docs(research): B1 trial 4 — instrument finding, kept as reading <id>; no trial spent, the shared B budget at 22`.

- [ ] **Step 7: The replay case and the probe** — `uv run pytest tests/test_registry_replay.py -k 'trial-<its id>' -q -p no:cacheprovider --basetemp=.tmp/plan-00134/pt` passes (on a stop `-k 'reading-<its id>'`), on the commit, since the case fails on any uncommitted change under the registry and the ledger; a difference goes to the owner before the push. On a record, the literal's probe: `--file cli/research/subjects.py`, control `s/^def _b2_verdict(/def _b2_verdict_gone(/`, mutation `s/^_B1_VOLUME_N_TRIALS = 4/_B1_VOLUME_N_TRIALS = 5/`, against `tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal`, expected `KILLED`.

- [ ] **Step 8: The read and the PR body** — the commit's `pre-review`, then the read of the delta from the tip the last read covered — `review` over `<that tip>..HEAD`, since the commit adds files outside that read's range, and `re-review` over a fix of it, within the branch's two (Global Constraints' reads line) — then the push, its own call; the PR body through `open-pr`: the verdict, the instrument finding or the count's refusal, every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, and the read line naming the tip the delta's read covered, `merge-pr`'s gate refusing any other. Merged on the owner's word through `merge-pr`; before it, `git status --short --ignored` is read, `.tmp/plan-00134` removed, `unlink data/ohlc-full`, and `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the canonical `ohlc-full` still there.
