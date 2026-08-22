"""Re-derivation of registry record 43's stage-1 book — the incumbent record 44's ADOPT is measured
against — from committed code. This module IS trial 43's instrument, exactly as `record44_legs.py`
is record 44's; nothing else needs to be pointed at.

Construction per docs/specs/00038-cross-frequency-combination-design.md (pre-registered): three
sleeves on the 4h union calendar — B (daily benchmark w*l3, intraday-held), A1 (A1-lf weekly v0.12
7-offset-mean positions, intraday-held), A2 (equal-weight ensemble of trials 37-39's native-4h arms)
— rolling 180-bar inverse-vol sleeve weights through k-1 (ANY degenerate window -> all 1/3), cap
20%/10%, full per-asset costing at 0.006/side, §10 governor at daily cadence. The adaptive sleeve
weighting is the `ivol180` of the variant string and the sole construction difference from record
44, which fixes the three weights at 1/3.

Run: `uv run python -m cli.portfolio.record43_book` (~3 min 05 s measured: ~2 min 07 s of it the
stage-1 derivation, where the three A2 arms and the two daily sleeves dominate, then record 44's
build and the ~1 min 1151-point cost sweep). It takes no tuning knobs and reads only frozen inputs — re-running it is
the whole point. Every QA gate the original driver ran is kept as an assert AND returned in the
result's `qa` block, so a caller checks them without re-reading this file.

## Provenance — recovered, not reconstructed

Trial 43's `run_ref` names scratchpad scripts that were believed permanently lost. On 2026-08-21 all
five were recovered VERBATIM from the iter-080/081 session transcript's `Write`/`Edit` records; the
transcript itself was destroyed by the tooling's 30-day retention prune four minutes after being
read and 27 minutes before the commit that preserved the bytes, so it can never be re-read. The
recovered stage-1 driver then reproduced row 43's registered figures exactly on two machines —
including `weight_warmup_bars` 180 and `weight_zero_vol_fallback_bars` 10638, which fall out of the
computation rather than being fitted. That behavioural reproduction, not the replay, is the proof.

This module is a faithful port of the recovered `crossfreq_run_rederived.py` — variant 2, the one
that reproduced — with two substitutions it already carried, both forced by upstream artifacts also
lost and both self-validating against REGISTERED figures: the A2 arms are recomputed from committed
`a2_book_returns` (only iter-074's elementwise cache cross-check is dropped; each arm still asserts
against its registered Sharpe), and the 4h benchmark comes from committed
`record44_legs.benchmark_4h_net_of_cost`. Importing that one constructor is why the substitution no
longer needs an elementwise pin: there is exactly one benchmark constructor in the repo now, so
there is no substituted series to compare against.

The original bytes stay reachable in git history — the deletion commit sits on top of the recovery,
and this repo merges with merge commits. Retrieve them by PATH, which is stable across rebases:

    git log --all --full-history --diff-filter=A -- 'docs/reference/trial43-recovered-runners/*'
    git show <that-commit>:docs/reference/trial43-recovered-runners/<file>

`--full-history` is load-bearing, not decoration: without it git's default history simplification
prunes the add-commit once the path is absent from the tip tree, the command prints NOTHING, and a
reader concludes the bytes are gone. Verified on merged develop — the plain form returns empty, this
form returns the recovery commit. Check what you retrieve against the sha256s below.

sha256 of the five recovered ORIGINALS (the authenticity anchor now that they are not in HEAD):

    crossfreq_run.py      5a1b1eb085ce09709baba98d07d0c12b1ebe73e1e7e9acea704ffaa41af2eeed
    crossfreq_stage2.py   a23a22442c471caf9e9a0208dd507f6789613e60b8e760a1247df5661e2e7100
    stage1b_verify.py     ec254492f51fe260e3f3a881e31a9f8334dcc2a698aa95b3694040edaa6478f6
    trial44_run.py        16eb59a54a78e7d76b5fa361e668ce15981a08e34db404a1758e1f948ad11846
    trial44_write.py      124df24519927bb917c98a72a1dd8b513b4e5eb965dc2071745e05cea3f3cf85

and of the two derived recovery variants, the second of which this module ports:

    crossfreq_run_nocache.py    32b33a3dee7126db0b7d2cbf4d09da9b620bc9b36e6c91e4b76d001632ca6759
    crossfreq_run_rederived.py  c8c2dfe1dbb67011f0465cc8b4f0a3c2d6448fc6471247f7e4dd3502ae8ed4a8

`trial44_write.py` must never be run: it calls `append()` against the append-only, hash-chained
registry.

## Scope — what is ported here and what is not

Ported: stage 1 — the three sleeves, their QA gates, the combination and the headline figures —
plus, from `crossfreq_stage2.py`, the one detail its cost-stress rungs turn on (`noc[k] - turn[k] *
extra`, re-governed through the same daily cadence) and the 43-vs-44 cost sweep built on it.

NOT ported, and deliberately: the REST of `crossfreq_stage2.py` — the ratified kill bar it exists
for (SPA grid, DSR, benchmark-relative worst slice, the ADOPT line) — and all of
`stage1b_verify.py`, which is the independent stage-1 reproduction against the now-vanished cache
plus the win-structure probes (the fixed-1/3 counterfactual, sleeve correlations, the per-year
table); and trial 44's two drivers, whose instrument already exists as `record44_legs.py`. Those
five live in git history at the shas above. (The two scripts' roles are easy to invert from their
names: stage2 carries the stress and the verdict, stage1b the reproduction and the counterfactual.)

What does NOT change: registry rows 43 and 44 keep their `run_ref` "(scratchpad)" wording forever —
the registry is append-only and hash-chained, so the row cannot be edited to point here. T0125's
frozen-set exemption for those legacy rows stands; the forward `run_ref` guard is unaffected. And
the go/no-go gate stays re-grounded on the benchmark-relative basis: re-reading the 43-vs-44
ordering with this module is decision-support, never a gate input.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from cli.alpha import A1Config, A2Config, a1_book_returns, a2_book_returns

# Deliberate cross-package import of a1's private helpers, for the same reason crossfreq_system.py
# and the recovered driver import them: the sleeves must run the SAME code path the registered trial
# ran, and a reimplementation could silently diverge.
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.portfolio import build_combined_system
from cli.portfolio.crossfreq import daily_cadence_governor, expand_daily_positions
from cli.portfolio.crossfreq_system import (
    CrossfreqSystemConfig,
    apply_whole_book_limits,
    build_crossfreq_system_fast,
)

# One benchmark constructor for both records — see the provenance note above. DATA_ROOT and
# REGISTRY_PATH are re-exported through this module so its tests gate on the same paths.
from cli.portfolio.record44_legs import DATA_ROOT, REGISTRY_PATH, benchmark_4h_net_of_cost, load_union
from cli.registry import TrialRegistry
from cli.risk import apply_position_caps
from cli.validation import max_drawdown, sharpe

ASSETS = CrossfreqSystemConfig().assets
COST_PER_SIDE = 0.006
PPY_4H = 2190
PPY_DAILY = 365
DECISIVE_START = 1380
WEIGHT_WINDOW = 180  # 30 days of 4h bars
LONG_CAP = 0.20
SHORT_CAP = 0.10

# B sleeve: record 33's benchmark sleeve on the DAILY calendar, the builder recipe verbatim.
B_BASKET_LOOKBACK = 30
B_GATE_WINDOW = 200
B_TARGET_VOL_ANNUAL = 0.10
B_MAX_LEVERAGE = 1.0

A1_CADENCE = 7  # weekly rebalance, held across the block; the sleeve is the 7 offsets' mean

# Trials 37-39's adopted 4h arms -> each one's recorded full-window net-of-cost Sharpe.
A2_ARMS = {
    ((20, 50, 100), 0.12): 1.3274,
    ((60, 120, 240), 0.10): 1.3017,
    ((60, 120, 240), 0.12): 1.3585,
}
A2_LOOKBACK = 180  # vol_lookback = basket_lookback = 180 for every adopted arm

# Anchors every QA gate asserts against — each one a figure an EARLIER trial registered, which is
# what makes them independent of anything recovered.
QA_BENCH_DAILY = 1.2455
QA_A1LF_BOOK = 1.3798
QA_BENCH_4H = (1.2128, 1.2447)  # full / decisive
QA_SHARPE_TOLERANCE = 0.005
QA_BUILDER_TOLERANCE = 1e-12
# Expansion inflation detector: an expanded daily sleeve's 4h Sharpe must sit near its daily anchor.
# Small drift from intraday compounding and cost timing is expected; a +0.5-style jump is the
# look-ahead signature that raw bar-start stamps produce (B 1.27 -> 1.76, caught in pre-run review).
QA_EXPANSION_BAND = (-0.15, 0.10)

# The registered cost-stress rungs, and the sweep that reads between them.
COST_STRESS_RUNGS = (1.5, 2.0)
SWEEP_LOW = 0.70  # below the measured maker end, so the whole realistic band is swept, not argued
# Far above any executable cost, because the question is stability rather than a level: a sweep that
# stops at the last registered rung reports its own ceiling as a horizon (measured: at x2.0 record 43
# leads, and record 44 leads again at 34 of the 51 points between x2.0 and x3.0).
SWEEP_HIGH = 3.0
# Fine enough that a lead is not missed between steps: at 0.01 the ordering looked settled above
# x1.8534, and 0.002 finds record 44 leading again at x1.874 by +0.0016 — twice the smallest margin
# the coarse grid counted, so the miss was resolution, not noise.
SWEEP_STEP = 0.002
SWEEP_REFINE_TO = 0.001
# The measured maker/taker execution band, as per-side cost: tier-1 maker fee plus the calibrated
# spread reads 42.1 bps at EUR 1k and 44.2 at EUR 10k; taker 82.1 and 84.2. Against the 0.006 basis
# those are the multipliers below — the range the live book can actually occupy.
REALISTIC_BAND = (0.421 / 0.6, 0.842 / 0.6)

# The pre-registered adoption criteria, read against record 33.
RECORD33_SHARPE = 1.3263
RECORD33_MAXDD = 0.1449
DD_AWARE_SHARPE_TOLERANCE = 0.02
DD_AWARE_MAXDD_MARGIN = 0.015


def btc_forward_filled(prices: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
    """The registered feed map's second grid: BTC forward-filled, every other asset's Nones kept.

    BTC alone because it is the regime series `a1_book_returns` gates on — a None there would drop
    the gate, while the other assets' Nones are meaningful absence the book primitives handle.
    """
    btc = list(prices["BTC"])
    last = None
    for i in range(len(btc)):
        if btc[i] is None:
            btc[i] = last
        else:
            last = btc[i]
    out = dict(prices)
    out["BTC"] = btc
    return out


def asset_return_grid(prices_ff: dict[str, list[float | None]]) -> dict[str, list[float]]:
    """Per-asset per-bar returns over the BTC-ffilled prices, absent bars costed as 0.0."""
    return {a: [r if r is not None else 0.0 for r in _asset_returns(prices_ff[a])] for a in ASSETS}


def net_of_cost(positions: dict[str, list[float]], returns: dict[str, list[float]], n: int) -> tuple[list[float], list[float]]:
    """Per-bar (net-of-cost return, turnover) for a per-asset position book, starting flat.

    Turnover is summed per asset against the previous bar's position (bar 0 charged full entry) and
    priced at `COST_PER_SIDE`; the gross is the position-weighted asset return.
    """
    net: list[float] = []
    turnover_series: list[float] = []
    prev = dict.fromkeys(ASSETS, 0.0)
    for k in range(n):
        gross, turnover = 0.0, 0.0
        for a in ASSETS:
            p = positions[a][k]
            gross += p * returns[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        turnover_series.append(turnover)
        net.append(gross - turnover * COST_PER_SIDE)
    return net, turnover_series


def position_turnover(positions: dict[str, list[float]], n: int, *, assets: tuple[str, ...] = ASSETS) -> list[float]:
    """Per-bar turnover of a per-asset position book, starting flat (bar 0 charged full entry).

    The same accumulation `net_of_cost` performs inline; separate here because the cost-stress axis
    needs a book's turnover without its returns — record 44's builder publishes positions and nets
    but no turnover series of its own.
    """
    out: list[float] = []
    prev = dict.fromkeys(assets, 0.0)
    for k in range(n):
        turnover = 0.0
        for a in assets:
            p = positions[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        out.append(turnover)
    return out


def build_b_sleeve(daily_prices: dict[str, list[float | None]]) -> tuple[dict[str, list[float]], list[float]]:
    """B sleeve on the DAILY calendar: (per-asset positions, own net-of-cost series).

    Dynamic inverse-vol basket at 30 -> 200d SMA gate on the basket's own equity -> vol target
    0.10/sqrt(365) at 30 -> inverse-vol weights at 30, charged per-asset turnover. The net-of-cost
    series takes the BASKET's gross (l3 * basket), not the per-asset sum: that is what makes it
    comparable elementwise to the committed builder's `benchmark_net_of_cost`.
    """
    n = len(next(iter(daily_prices.values()))) - 1
    basket = dynamic_inverse_vol_basket(daily_prices, lookback=B_BASKET_LOOKBACK)
    equity = [1.0]
    for r in basket:
        equity.append(equity[-1] * (1 + r))
    gate = sma_gate(equity, window=B_GATE_WINDOW)
    vt = vol_target(
        basket,
        target_vol=B_TARGET_VOL_ANNUAL / math.sqrt(PPY_DAILY),
        lookback=B_BASKET_LOOKBACK,
        max_leverage=B_MAX_LEVERAGE,
    )
    l3 = [gate[k] * vt[k] for k in range(n)]
    weights = _inverse_vol_weights(daily_prices, lookback=B_BASKET_LOOKBACK)
    positions = {a: [weights[k].get(a, 0.0) * l3[k] for k in range(n)] for a in ASSETS}

    net: list[float] = []
    prev = dict.fromkeys(ASSETS, 0.0)
    for k in range(n):
        turnover = 0.0
        for a in ASSETS:
            p = positions[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        net.append(l3[k] * basket[k] - turnover * COST_PER_SIDE)
    return positions, net


def a1_offset_books(daily_prices_ff: dict[str, list[float | None]]) -> list[dict[str, list[float]]]:
    """A1-lf weekly v0.12 held positions, one book per rebalance offset (7 of them).

    Offset o rebalances on days o, o+7, o+14, … and holds through the block; days before the first
    rebalance hold day 0's position, as the registered trial did.
    """
    n = len(daily_prices_ff["BTC"]) - 1
    config = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
    positions = a1_book_returns(daily_prices_ff, daily_prices_ff["BTC"], config=config)["asset_positions"]

    def block_start(k: int, offset: int) -> int:
        return 0 if k < offset else offset + A1_CADENCE * ((k - offset) // A1_CADENCE)

    return [{a: [positions[a][block_start(k, o)] for k in range(n)] for a in ASSETS} for o in range(A1_CADENCE)]


def a1_offset_mean_positions(offset_books: list[dict[str, list[float]]], n: int) -> dict[str, list[float]]:
    """The A1 sleeve itself: the 7 offset books' per-asset mean."""
    return {a: [statistics.mean(book[a][k] for book in offset_books) for k in range(n)] for a in ASSETS}


def a1_offset_mean_book(offset_books: list[dict[str, list[float]]], daily_returns: dict[str, list[float]], n: int) -> list[float]:
    """Trial 34's recorded book — the mean of the 7 offsets' net-of-cost SERIES, not of positions.

    Distinct from the sleeve above and QA'd against 1.3798: averaging books and averaging positions
    are different objects, and it is the book average that trial 34 registered.
    """
    offset_nets = [net_of_cost(book, daily_returns, n)[0] for book in offset_books]
    return [statistics.mean(net[k] for net in offset_nets) for k in range(n)]


def build_a2_sleeve(h4_prices_ff: dict[str, list[float | None]]) -> tuple[dict[str, list[float]], dict[tuple, float]]:
    """A2 sleeve on the 4h calendar: (equal-weight per-asset mean of the three arms, arm Sharpes).

    Each arm is recomputed from committed `a2_book_returns` and asserted against its REGISTERED
    full-window Sharpe before it may join the ensemble.
    """
    n = len(h4_prices_ff["BTC"]) - 1
    arm_positions: dict[tuple, dict[str, list[float]]] = {}
    arm_sharpes: dict[tuple, float] = {}
    for (lookbacks, target_vol), recorded in A2_ARMS.items():
        config = A2Config(
            lookbacks=lookbacks,
            short="off",
            target_vol=target_vol,
            vol_lookback=A2_LOOKBACK,
            basket_lookback=A2_LOOKBACK,
            periods_per_year=PPY_4H,
        )
        out = a2_book_returns(h4_prices_ff, config=config)
        positions = out["asset_positions"]
        net: list[float] = []
        prev = dict.fromkeys(ASSETS, 0.0)
        for k in range(n):
            turnover = 0.0
            for a in ASSETS:
                p = positions[a][k]
                turnover += abs(p - prev[a])
                prev[a] = p
            net.append(out["net_returns"][k] - turnover * COST_PER_SIDE)
        arm_sharpe = sharpe(net, periods_per_year=PPY_4H)
        assert abs(arm_sharpe - recorded) < QA_SHARPE_TOLERANCE, (
            f"arm {(lookbacks, target_vol)} Sharpe {arm_sharpe:.4f} != recorded {recorded}"
        )
        arm_positions[(lookbacks, target_vol)] = positions
        arm_sharpes[(lookbacks, target_vol)] = arm_sharpe
    sleeve = {a: [statistics.mean(arm[a][k] for arm in arm_positions.values()) for k in range(n)] for a in ASSETS}
    return sleeve, arm_sharpes


def sleeve_weights(sleeve_nets: list[list[float]]) -> tuple[list[tuple[float, ...]], int, int]:
    """Rolling inverse-vol sleeve weights: (weights, warm-up bars, zero-vol fallback bars).

    Bar k reads the trailing WEIGHT_WINDOW bars through k-1 — never its own — and normalizes the
    reciprocal population stdevs. Before bar WEIGHT_WINDOW there is no window; from there on, ANY
    degenerate sleeve (zero vol) takes the WHOLE bar to equal thirds, not just that sleeve's weight.
    """
    n = len(sleeve_nets[0])
    weights: list[tuple[float, ...]] = []
    warmup_bars = 0
    zero_vol_bars = 0
    equal = (1 / 3, 1 / 3, 1 / 3)
    for k in range(n):
        if k < WEIGHT_WINDOW:
            weights.append(equal)
            warmup_bars += 1
            continue
        vols = [statistics.pstdev(net[k - WEIGHT_WINDOW : k]) for net in sleeve_nets]
        if any(v <= 0.0 for v in vols):
            weights.append(equal)
            zero_vol_bars += 1
            continue
        inverse = [1 / v for v in vols]
        total = sum(inverse)
        weights.append(tuple(x / total for x in inverse))
    return weights, warmup_bars, zero_vol_bars


def dense_day_index(h4_ts: list[datetime], n: int) -> list[int]:
    """Governor day ordinals for the 4h return bars: dense ranks of each bar's CLOSE date.

    Return bar k spans close-times (h4_ts[k] + 4h, h4_ts[k+1] + 4h], whose midnight-bounded calendar
    day is date(h4_ts[k+1]) — stamps are bar starts. DENSE ranks, not true ordinals: the 4h union
    misses three calendar days in the 2013 stub, and record 33's ratified daily governor counted
    PRESENT bars, so compression is the semantics-consistent choice — and dense ranks satisfy the
    helper's contiguity guard by construction.
    """
    seen: dict = {}
    return [seen.setdefault(h4_ts[k + 1].date(), len(seen)) for k in range(n)]


def stressed_ungoverned(ungoverned_net: list[float], turnover: list[float], *, cost_multiplier: float) -> list[float]:
    """The registered cost-stress axis: the x1.0 book's own ungoverned net, charged the EXTRA
    per-side cost on its own turnover — `noc[k] - turn[k] * 0.006 * (m - 1)`.

    Positions, sleeve weights, caps and limits are NOT rebuilt. That is what the registered
    `cost_stress_*` figures mean (both drivers wrote exactly this, then re-governed), and for the
    adaptive-weight book the distinction is load-bearing: a rebuild at a higher cost moves the
    sleeve net-of-cost series, hence the weights, hence a different book — which is a different
    question from "what does THIS book earn when execution costs more".
    """
    extra = COST_PER_SIDE * (cost_multiplier - 1.0)
    return [ungoverned_net[k] - turnover[k] * extra for k in range(len(ungoverned_net))]


def stressed_governed_net(axis: dict, *, cost_multiplier: float) -> list[float]:
    """A stress axis re-costed at `cost_multiplier` and RE-GOVERNED through the daily cadence.

    `axis` carries `ungoverned_net`, `turnover` and `day_index`. A day index one row longer than the
    net series is record 44's builder convention (it governs `noc + [0.0]` over its forming row);
    the pad is reproduced here so both books are governed exactly as their own instrument does.
    """
    n = len(axis["ungoverned_net"])
    day_index = axis["day_index"]
    stressed = stressed_ungoverned(axis["ungoverned_net"], axis["turnover"], cost_multiplier=cost_multiplier)
    multipliers = daily_cadence_governor(stressed + [0.0] * (len(day_index) - n), day_index)
    return [multipliers[k] * stressed[k] for k in range(n)]


def stressed_sharpe(axis: dict, *, cost_multiplier: float) -> float:
    """Annualized net-of-cost Sharpe of a book re-costed at `cost_multiplier` and re-governed."""
    return sharpe(stressed_governed_net(axis, cost_multiplier=cost_multiplier), periods_per_year=PPY_4H)


def record44_stress_axis(
    daily_ts: list[datetime],
    daily_prices: dict[str, list[float | None]],
    h4_ts: list[datetime],
    h4_prices: dict[str, list[float | None]],
) -> dict:
    """Record 44's book on the same stress axis, from the committed builder — no knobs, frozen config.

    `CrossfreqSystemResult` publishes final targets already multiplied by the governor and no
    turnover series, so the pre-governor book is recomputed from the builder's own sleeve positions
    through the verified path's own layers (fixed 1/3 -> per-asset caps -> whole-book limits) — the
    same three calls `apply_whole_book_limits` exists to keep out-of-builder recomputations honest.
    `governed_net_builder` is carried along so a caller can check the x1.0 identity elementwise.
    """
    config = CrossfreqSystemConfig()
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    sleeves = result.sleeve_positions
    n_rows = len(result.day_index)
    third = 1 / 3
    combined = {
        a: [third * sleeves["B"][a][k] + third * sleeves["A1"][a][k] + third * sleeves["A2"][a][k] for k in range(n_rows)]
        for a in config.assets
    }
    limited = apply_whole_book_limits(apply_position_caps(combined, long_cap=config.long_cap, short_cap=config.short_cap))
    return {
        "ungoverned_net": result.ungoverned_net,
        "turnover": position_turnover(limited, result.n_periods, assets=config.assets),
        "day_index": result.day_index,
        "governed_net_builder": result.governed_net,
    }


def stress_anchors(axis43: dict, axis44: dict, *, registry_path: Path = REGISTRY_PATH) -> dict:
    """Both books at x1.0 and the two registered rungs, asserted against every figure the registry
    stores for them. This is the gate: no swept point means anything until all six reproduce.
    """
    registered = {r.trial_id: r.metrics for r in TrialRegistry(registry_path).records}
    measured: dict[int, dict[float, float]] = {}
    for trial_id, axis in ((43, axis43), (44, axis44)):
        row = registered[trial_id]
        want = {1.0: row["ann_sharpe_noc"], 1.5: row["cost_stress_1_5x_sharpe_ann"], 2.0: row["cost_stress_2x_sharpe_ann"]}
        measured[trial_id] = {m: stressed_sharpe(axis, cost_multiplier=m) for m in (1.0, *COST_STRESS_RUNGS)}
        for multiplier, registered_value in want.items():
            got = measured[trial_id][multiplier]
            assert round(got, 4) == registered_value, (
                f"record {trial_id} at x{multiplier} reads {got!r}, registered {registered_value!r} — "
                f"the stress axis does not reproduce the record; STOP rather than tune"
            )
    return measured


def bisect_sign_change(diff_at, low: float, high: float, *, refine_to: float = SWEEP_REFINE_TO) -> tuple[float, float, float]:
    """Narrow a bracket whose ends have opposite `diff_at` signs to `refine_to` wide.

    Returns (low, high, midpoint). Deliberately NOT a root-finder's contract: cost -> Sharpe is a
    jagged step function here (the governor re-engages on the net-of-cost series), so there is no
    smooth root to converge on — what is true is that the ordering flips somewhere inside the
    returned bracket, and the bracket is as narrow as asked.
    """
    if diff_at(low) <= 0.0 or diff_at(high) >= 0.0:
        raise ValueError(f"bracket [{low}, {high}] does not straddle a positive-to-negative flip")
    while high - low > refine_to:
        mid = (low + high) / 2
        if diff_at(mid) > 0.0:
            low = mid
        else:
            high = mid
    return low, high, (low + high) / 2


def crossing_43v44(
    axis43: dict,
    axis44: dict,
    *,
    low: float = SWEEP_LOW,
    high: float = SWEEP_HIGH,
    step: float = SWEEP_STEP,
    refine_to: float = SWEEP_REFINE_TO,
) -> dict:
    """A census of the 43-vs-44 ordering across per-side cost — the measurement record 44's ADOPT
    criterion was never re-read at.

    Gated on `stress_anchors` before a single swept point is computed. `diff` is record 44 minus
    record 43, so a positive reading is record 44 leading, as its ADOPT verdict claims.

    **The output is a census, not a crossing, because a crossing is not what the data supports.**
    Cost -> Sharpe is a jagged step function here — the drawdown governor re-engages on the
    net-of-cost series — so the sign changes dozens of times and BOTH books still lead somewhere
    near the ceiling. Any "beyond x the ordering has reversed" reading is therefore an artifact of
    where the grid stops and how finely it steps, which is why `last_flip_on_grid` is named for
    exactly what it is and carries its own grid parameters. What the sweep licenses instead:
    neither book holds a durable lead anywhere in the swept range, so record 44's x1.0 margin is a
    point convention rather than a regime.

    Reported: the flip census, each book's lead counts and extremes, the highest multiplier at
    which each still leads, and the same statistics restricted to the measured execution band.
    """
    anchors = stress_anchors(axis43, axis44)
    x1_governed = stressed_governed_net(axis44, cost_multiplier=1.0)
    builder = axis44["governed_net_builder"]
    x1_max_diff = max(abs(x1_governed[k] - builder[k]) for k in range(len(builder)))
    assert x1_max_diff < QA_BUILDER_TOLERANCE, f"record 44 at x1.0 diverges from its builder: max diff {x1_max_diff}"

    def diff_at(multiplier: float) -> float:
        return stressed_sharpe(axis44, cost_multiplier=multiplier) - stressed_sharpe(axis43, cost_multiplier=multiplier)

    n_steps = int(round((high - low) / step))
    grid = []
    for i in range(n_steps + 1):
        multiplier = round(low + i * step, 10)
        s43 = stressed_sharpe(axis43, cost_multiplier=multiplier)
        s44 = stressed_sharpe(axis44, cost_multiplier=multiplier)
        grid.append((multiplier, s43, s44, s44 - s43))

    flips = [(grid[i][0], grid[i + 1][0]) for i in range(len(grid) - 1) if (grid[i][3] > 0.0) != (grid[i + 1][3] > 0.0)]
    leads_44 = [row for row in grid if row[3] > 0.0]
    leads_43 = [row for row in grid if row[3] <= 0.0]
    if not leads_44 or not leads_43:
        raise ValueError("one book leads at every swept point — the ordering is stable on this grid, so report THAT")

    # The last sign change ON THIS GRID, kept for reporting and labelled as such. Bisected only when
    # it runs 44-leading -> 43-leading, which is the direction the bracket helper is written for.
    last_flip = flips[-1]
    refined: tuple[float, float] | None = None
    bisected: float | None = None
    if diff_at(last_flip[0]) > 0.0 > diff_at(last_flip[1]):
        bracket_low, bracket_high, bisected = bisect_sign_change(diff_at, *last_flip, refine_to=refine_to)
        refined = (bracket_low, bracket_high)

    widest_43 = min(grid, key=lambda row: row[3])
    widest_44 = max(grid, key=lambda row: row[3])
    band_low, band_high = REALISTIC_BAND
    in_band = [row for row in grid if band_low <= row[0] <= band_high]
    maker_half = [row for row in in_band if row[0] <= 1.0]
    band_43_leads = [row for row in in_band if row[3] <= 0.0]
    return {
        "grid": grid,
        "anchors": anchors,
        "sweep_parameters": {"low": low, "high": high, "step": step},
        "flip_brackets": flips,
        "flip_count": len(flips),
        "points": len(grid),
        "lead_counts": {43: len(leads_43), 44: len(leads_44)},
        "highest_lead_multiplier": {43: max(row[0] for row in leads_43), 44: max(row[0] for row in leads_44)},
        "max_lead": {43: (widest_43[0], widest_43[3]), 44: (widest_44[0], widest_44[3])},
        "min_abs_diff": min(abs(row[3]) for row in grid),
        # Named for what it is: the last sign change on THIS grid at THIS step, not a horizon.
        "last_flip_on_grid": {"bracket": last_flip, "refined_bracket": refined, "bisected": bisected},
        "realistic_band": REALISTIC_BAND,
        "band": {
            "points": len(in_band),
            "lead_counts": {43: len(band_43_leads), 44: len(in_band) - len(band_43_leads)},
            "43_lead_points": [(row[0], row[3]) for row in band_43_leads],
            "min_diff": min(row[3] for row in in_band),
            "max_diff": max(row[3] for row in in_band),
            "flip_brackets": [pair for pair in flips if pair[1] >= band_low and pair[0] <= band_high],
            "maker_half": {
                "range": (band_low, 1.0),
                "points": len(maker_half),
                "lead_counts": {
                    43: sum(1 for row in maker_half if row[3] <= 0.0),
                    44: sum(1 for row in maker_half if row[3] > 0.0),
                },
                "44_lead_points": [(row[0], row[3]) for row in maker_half if row[3] > 0.0],
            },
        },
        "record44_x1_max_abs_diff_vs_builder": x1_max_diff,
    }


def rederive_record43_book(
    daily_ts: list[datetime],
    daily_prices: dict[str, list[float | None]],
    h4_ts: list[datetime],
    h4_prices: dict[str, list[float | None]],
) -> dict:
    """Trial 43's stage-1 figures, keyed by their registry names, plus the `qa` block.

    Every QA gate the registered driver ran is asserted here in the order it ran them — a sleeve
    that does not reproduce its recorded anchor stops the derivation before any headline exists —
    and each gate's measured value is also returned under `qa`, so a caller checks the gates rather
    than trusting that they ran.
    """
    n_daily = len(daily_ts) - 1
    n_4h = len(h4_ts) - 1
    daily_prices_ff = btc_forward_filled(daily_prices)
    h4_prices_ff = btc_forward_filled(h4_prices)
    daily_returns = asset_return_grid(daily_prices_ff)
    h4_returns = asset_return_grid(h4_prices_ff)

    # ---- B sleeve, QA'd elementwise against the committed builder and against 1.2455 ----
    b_daily, b_daily_net = build_b_sleeve(daily_prices)
    builder_bench = build_combined_system(daily_prices).benchmark_net_of_cost
    assert len(builder_bench) == n_daily, f"builder length {len(builder_bench)} != {n_daily}"
    builder_max_diff = max(abs(b_daily_net[k] - builder_bench[k]) for k in range(n_daily))
    assert builder_max_diff < QA_BUILDER_TOLERANCE, f"B sleeve diverges from committed builder: max diff {builder_max_diff}"
    b_daily_sharpe = sharpe(b_daily_net, periods_per_year=PPY_DAILY)
    assert abs(b_daily_sharpe - QA_BENCH_DAILY) < QA_SHARPE_TOLERANCE, (
        f"daily bench Sharpe {b_daily_sharpe:.4f} != {QA_BENCH_DAILY}"
    )

    # ---- A1 sleeve, QA'd against trial 34's recorded book ----
    offset_books = a1_offset_books(daily_prices_ff)
    a1_daily = a1_offset_mean_positions(offset_books, n_daily)
    a1lf_book_sharpe = sharpe(a1_offset_mean_book(offset_books, daily_returns, n_daily), periods_per_year=PPY_DAILY)
    assert abs(a1lf_book_sharpe - QA_A1LF_BOOK) < QA_SHARPE_TOLERANCE, f"A1-lf book Sharpe {a1lf_book_sharpe:.4f} != {QA_A1LF_BOOK}"

    # ---- A2 sleeve (native 4h), each arm QA'd against its registered Sharpe ----
    a2_4h, a2_arm_sharpes = build_a2_sleeve(h4_prices_ff)

    # ---- the 4h benchmark comparator, QA'd against its registered readings ----
    bench_4h = benchmark_4h_net_of_cost(h4_prices, cost_per_side=COST_PER_SIDE)
    bench_full = sharpe(bench_4h, periods_per_year=PPY_4H)
    bench_decisive = sharpe(bench_4h[DECISIVE_START:], periods_per_year=PPY_4H)
    assert abs(bench_full - QA_BENCH_4H[0]) < QA_SHARPE_TOLERANCE and abs(bench_decisive - QA_BENCH_4H[1]) < QA_SHARPE_TOLERANCE, (
        f"4h benchmark figures {bench_full:.4f}/{bench_decisive:.4f} != {QA_BENCH_4H}"
    )

    # ---- expand the daily sleeves to 4h on CLOSE-TIME boundaries ----
    # Both grids stamp bar STARTS; closes materialize at stamp + interval (daily close stamped D ==
    # 4h close stamped D 20:00). A close-indexed daily book's position k is decidable only at the
    # daily bar-k CLOSE and earns close[k] -> close[k+1] — calendar day k+1. Passing raw stamps to
    # expand_daily_positions applies position k one day EARLY (look-ahead), so BOTH ts lists shift
    # to close time and the helper's interval rule operates on decision times.
    daily_ts_close = [t + timedelta(days=1) for t in daily_ts]
    h4_ts_close = [t + timedelta(hours=4) for t in h4_ts]
    b_4h = expand_daily_positions(b_daily, daily_ts_close, h4_ts_close)
    a1_4h = expand_daily_positions(a1_daily, daily_ts_close, h4_ts_close)
    tail_zeroed_bars = sum(1 for k in range(n_4h) if h4_ts_close[k + 1] > daily_ts_close[-1])

    # ---- sleeve own net-of-cost series: the weight inputs, and the expansion QA ----
    sleeve_nets = [net_of_cost(pos, h4_returns, n_4h)[0] for pos in (b_4h, a1_4h, a2_4h)]
    expansion_sharpes = {}
    for name, net, anchor in (("B", sleeve_nets[0], QA_BENCH_DAILY), ("A1", sleeve_nets[1], QA_A1LF_BOOK)):
        expanded = sharpe(net, periods_per_year=PPY_4H)
        low, high = anchor + QA_EXPANSION_BAND[0], anchor + QA_EXPANSION_BAND[1]
        assert low <= expanded <= high, (
            f"{name} expanded 4h Sharpe {expanded:.4f} outside [{low:.3f}, {high:.3f}] — mapping suspect"
        )
        expansion_sharpes[name] = expanded

    # ---- weights -> combine -> cap -> cost -> govern ----
    weights, warmup_bars, zero_vol_bars = sleeve_weights(sleeve_nets)
    combined = {
        a: [weights[k][0] * b_4h[a][k] + weights[k][1] * a1_4h[a][k] + weights[k][2] * a2_4h[a][k] for k in range(n_4h)]
        for a in ASSETS
    }
    capped = apply_position_caps(combined, long_cap=LONG_CAP, short_cap=SHORT_CAP)
    cap_breach_bars = sum(1 for k in range(n_4h) if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in ASSETS))

    ungoverned_net, turnover_series = net_of_cost(capped, h4_returns, n_4h)
    day_index = dense_day_index(h4_ts, n_4h)
    multipliers = daily_cadence_governor(ungoverned_net, day_index)
    governed_net = [multipliers[k] * ungoverned_net[k] for k in range(n_4h)]

    # ---- headline + engagement evidence ----
    ann_sharpe = sharpe(governed_net, periods_per_year=PPY_4H)
    maxdd = max_drawdown(governed_net)
    by_sleeve = list(zip(*weights, strict=True))
    weight_stats = [{"min": min(w), "max": max(w), "mean": statistics.mean(w)} for w in by_sleeve]
    for i, stats in enumerate(weight_stats):
        assert stats["max"] - stats["min"] > 1e-6, f"sleeve {i} weight never varies"
        assert stats["max"] < 1.0 - 1e-9 and stats["min"] > 0.0, f"sleeve {i} weight pinned at 0/1"

    dd_aware = abs(ann_sharpe - RECORD33_SHARPE) <= DD_AWARE_SHARPE_TOLERANCE and maxdd <= RECORD33_MAXDD - DD_AWARE_MAXDD_MARGIN
    return {
        "ann_sharpe_noc": ann_sharpe,
        "ann_sharpe_noc_decisive": sharpe(governed_net[DECISIVE_START:], periods_per_year=PPY_4H),
        "bench4h_sharpe_full": bench_full,
        "bench4h_sharpe_decisive": bench_decisive,
        "maxdd": maxdd,
        "maxdd_pre_governor": max_drawdown(ungoverned_net),
        "cap_breach_bars": cap_breach_bars,
        "governor_engaged_bars": sum(1 for m in multipliers if m < 1.0),
        "weight_warmup_bars": warmup_bars,
        "weight_zero_vol_fallback_bars": zero_vol_bars,
        "spot_drag_pct_yr": statistics.mean(turnover_series) * COST_PER_SIDE * PPY_4H,
        "criterion_dd_aware": int(dd_aware),
        "criterion_sharpe_primary": int(ann_sharpe >= RECORD33_SHARPE),
        # Everything the registered cost-stress axis needs from this book, so a sweep re-costs the
        # book that was just QA-gated rather than rebuilding one of its own.
        "stress_axis": {
            "ungoverned_net": ungoverned_net,
            "turnover": turnover_series,
            "day_index": day_index,
        },
        "qa": {
            "n_4h_bars": n_4h,
            "b_sleeve_max_abs_diff_vs_builder": builder_max_diff,
            "b_sleeve_daily_sharpe": b_daily_sharpe,
            "a1lf_book_sharpe": a1lf_book_sharpe,
            "a2_arm_sharpes": a2_arm_sharpes,
            "expansion_sharpes": expansion_sharpes,
            "tail_zeroed_bars": tail_zeroed_bars,
            "weight_stats": weight_stats,
        },
    }


def main() -> None:
    registered = {r.trial_id: r.metrics for r in TrialRegistry(REGISTRY_PATH).records}[43]
    daily_ts, daily_prices = load_union(1440)
    h4_ts, h4_prices = load_union(240)
    print(f"union bars: daily {len(daily_ts)}  4h {len(h4_ts)}")
    book = rederive_record43_book(daily_ts, daily_prices, h4_ts, h4_prices)
    axis43 = book.pop("stress_axis")
    qa = book.pop("qa")
    width = max(len(k) for k in book)
    print(f"{'figure':<{width}}  {'re-derived':<24}  {'registered':<24}  verdict")
    for key, value in book.items():
        want = registered.get(key)
        if want is None:
            verdict = "(not registered)"
        elif isinstance(value, int) and isinstance(want, (int, float)):
            verdict = "MATCH" if value == want else "MISMATCH"
        else:
            # Same rounding check the test asserts on, so the printed verdict cannot disagree with it.
            verdict = "MATCH" if value == want else ("~match (4dp)" if round(value, 4) == want else "MISMATCH")
        print(f"{key:<{width}}  {value!r:<24}  {want!r:<24}  {verdict}")
    print(f"\nQA gates: {qa}")

    print("\nsweeping the two records' ordering across per-side cost...", flush=True)
    axis44 = record44_stress_axis(daily_ts, daily_prices, h4_ts, h4_prices)
    sweep = crossing_43v44(axis43, axis44)
    for trial_id, anchors in sweep["anchors"].items():
        print(f"  anchors record {trial_id}: " + "  ".join(f"x{m} {value!r}" for m, value in anchors.items()))
    print(f"  record 44 at x1.0 vs its own builder: max abs diff {sweep['record44_x1_max_abs_diff_vs_builder']!r}")
    print(f"{'x cost':>7}  {'per side':>9}  {'record 43':>10}  {'record 44':>10}  {'44 - 43':>9}")
    for multiplier, s43, s44, diff in sweep["grid"]:
        if round(multiplier * 1000) % 100 == 0:  # coarse rows; the full grid is in the returned dict
            print(f"{multiplier:7.2f}  {multiplier * COST_PER_SIDE:9.4%}  {s43:10.4f}  {s44:10.4f}  {diff:+9.4f}")
    params = sweep["sweep_parameters"]
    counts, highest = sweep["lead_counts"], sweep["highest_lead_multiplier"]
    print(
        f"\nswept x{params['low']}-x{params['high']} step {params['step']}: {sweep['points']} points, "
        f"{sweep['flip_count']} sign changes"
    )
    print(
        f"record 43 leads at {counts[43]} points (widest {sweep['max_lead'][43][1]:+.4f} at x{sweep['max_lead'][43][0]}, "
        f"highest x{highest[43]}); record 44 leads at {counts[44]} (widest {sweep['max_lead'][44][1]:+.4f} at "
        f"x{sweep['max_lead'][44][0]}, highest x{highest[44]})"
    )
    print("NEITHER book holds a durable lead anywhere in the swept range — both still lead near the ceiling.")
    last = sweep["last_flip_on_grid"]
    where = f" -> x{last['bisected']:.4f}" if last["bisected"] is not None else " (upward, so no downward bracket to bisect)"
    print(f"last sign change on THIS grid, at THIS step: {last['bracket']}{where} — a grid artifact, not a horizon")
    band = sweep["band"]
    band_low, band_high = sweep["realistic_band"]
    print(
        f"\nmeasured execution band x{band_low:.4f}-x{band_high:.4f} "
        f"({band_low * COST_PER_SIDE:.4%}-{band_high * COST_PER_SIDE:.4%} per side): {band['points']} points, "
        f"record 43 leads at {band['lead_counts'][43]}, record 44 at {band['lead_counts'][44]}, "
        f"{len(band['flip_brackets'])} sign changes, margins {band['min_diff']:+.4f} to {band['max_diff']:+.4f}"
    )
    maker = band["maker_half"]
    print(
        f"maker half x{maker['range'][0]:.4f}-x{maker['range'][1]:.2f}: {maker['points']} points, "
        f"record 43 leads at {maker['lead_counts'][43]}, record 44 at {maker['lead_counts'][44]}"
    )


if __name__ == "__main__":
    main()
