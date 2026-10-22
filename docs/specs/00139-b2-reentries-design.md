# B2 trials 6–7 — the liquidation-cascade and funding-extreme re-entries on the A2-4h ensemble, on the frozen `ohlc-full` set

**Ruling:** the owner launched this unattended run, 2026-10-21, verbatim: "continue pushing the Research strates forward, pick the most relevant tasks. override the wall clock time gate, but do not pick up new topics after 8:00Z. when closing out a research step, try the trials with potential and do not close any family too early." B2's next step after trials 3–5 (T0023's trigger) is therefore the loop's pick, recorded as `[iter-183] B2's next step after trial 5` in `docs/research/10.phase4-decisions.md`; master plan §12 lists no touchpoint for a family's next trial. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" and head-to-head read "From-2021 primary (Recommended)", read from a later signal's own start (spec 00138 D8). Iteration `iter-183`, branch `research/iter-183-b2-contrarian-reentry`, topic T0023.

## The measured basis

Every figure below was measured on 2026-10-21 between 20:59Z and 21:15Z in this branch's worktree at develop's `fc4a2e8db`, with `data/ohlc-full`, `data/derivatives-funding` and `data/liquidations-daily` symlinked read-only from the main checkout's `data/`: positions and signals only, no return of either arm read.

The trials' program, `uv run python <it>` from the worktree root:

```python
import statistics
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.b2 import B2Config, close_grid, funding_grid_feature
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects


def funding_signal(reader, h4_ts):
    out = {}
    for asset in subjects._ASSETS:
        prints = reader.read_series("derivatives-funding", f"{subjects.PERP_SYMBOLS[asset]}/funding.parquet")
        out[asset] = funding_grid_feature(
            prints["ts"].to_list(), prints["funding_rate"].to_list(), prints["interval_hours"].to_list(), h4_ts, config=B2Config()
        )
    return out


def reentry(arm_a, full_long, fires, hold):
    arm_b = {}
    for a in subjects._ASSETS:
        left, row = 0, []
        for k, p in enumerate(arm_a[a]):
            if p > 0:
                left = 0
            elif fires[a][k]:
                left = max(left, hold)
            row.append(full_long[a][k] if p == 0 and left > 0 and full_long[a][k] > 0 else p)
            if p == 0 and left > 0:
                left -= 1
        arm_b[a] = row
    return arm_b


for name, read_signal, fire, hold in (
    ("trial 6, liquidation z > 2.5, hold 1", subjects._b2_liq_signal, lambda z: z is not None and z > 2.5, 1),
    ("trial 7, funding z < -2.0, hold 6", funding_signal, lambda z: z is not None and z < -2.0, 6),
):
    reader = ObservedReader(Path("data"))
    h4_ts, h4_prices = subjects._capturing_union(reader, "ohlc-full", 240, None, None, False)
    close = close_grid(h4_ts)
    n = len(close)
    signal = read_signal(reader, h4_ts)
    fed = subjects._ffill_btc(h4_prices)
    books = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=subjects._B2_LOOKBACK,
                basket_lookback=subjects._B2_LOOKBACK,
                periods_per_year=subjects.PPY_4H,
            ),
        )
        for lookbacks, target_vol in subjects._B2_A2_ARMS
    ]
    arm_a = {a: [statistics.mean(b["asset_positions"][a][k] for b in books) for k in range(n)] for a in subjects._ASSETS}
    weights = _inverse_vol_weights(fed, lookback=subjects._B2_LOOKBACK)
    full_long = {
        a: [weights[k].get(a, 0.0) * statistics.mean(b["vol_target_positions"][k] for b in books) for k in range(n)]
        for a in subjects._ASSETS
    }
    above = sum(arm_a[a][k] > full_long[a][k] + 1e-12 for a in subjects._ASSETS for k in range(n))
    equal = sum(abs(arm_a[a][k] - full_long[a][k]) <= 1e-12 and arm_a[a][k] > 0 for a in subjects._ASSETS for k in range(n))
    arm_b = reentry(arm_a, full_long, {a: [fire(z) for z in signal[a]] for a in subjects._ASSETS}, hold)
    years = sorted({str(t.year) for t in close})
    per_asset = {a: sum(p == 0 and q > 0 for p, q in zip(arm_a[a], arm_b[a])) for a in subjects._ASSETS}
    per_year = dict.fromkeys(years, 0)
    entries = 0
    for a in subjects._ASSETS:
        for k, (p, q) in enumerate(zip(arm_a[a], arm_b[a])):
            if p == 0 and q > 0:
                per_year[str(close[k].year)] += 1
                entries += k == 0 or arm_b[a][k - 1] == 0
    turnover = {
        label: sum(abs(pos[a][k] - (pos[a][k - 1] if k else 0.0)) for a in subjects._ASSETS for k in range(n))
        for label, pos in (("A", arm_a), ("B", arm_b))
    }
    differ = sum(any(arm_a[a][k] != arm_b[a][k] for a in subjects._ASSETS) for k in range(n))
    defined = next(k for k in range(n) if all(signal[a][k] is not None for a in subjects._ASSETS))
    k21 = next(k for k in range(n) if close[k] >= datetime(2021, 1, 1, tzinfo=UTC))
    start = max(defined, k21)
    print(name)
    print(f"   closes {n}; arm A above the full-long size at {above} asset-stamps, equal to it and long at {equal}")
    print("   block", compute_hash(reader.block()), {d: (len(e["files"]), e["rows"]) for d, e in reader.block().items()})
    print(f"   re-entry asset-stamps {sum(per_asset.values())}, entries {entries}, closes where the books differ {differ}, turnover A {turnover['A']:.2f} B {turnover['B']:.2f}")
    print(f"   per asset {per_asset}")
    print(f"   per close year {per_year}")
    print(f"   every asset's signal from index {defined} ({close[defined]}); 2021 from {k21}; the read opens at {start} ({close[start]}), {n - start} returns")
```

Its output, whole:

```text
trial 6, liquidation z > 2.5, hold 1
   closes 27337; arm A above the full-long size at 0 asset-stamps, equal to it and long at 30632
   block 816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f {'liquidations-daily': (10, 15048), 'ohlc-full': (10, 173373)}
   re-entry asset-stamps 1196, entries 165, closes where the books differ 509, turnover A 146.19 B 172.92
   per asset {'ADA': 114, 'AVAX': 82, 'BTC': 139, 'DOGE': 90, 'DOT': 163, 'ETH': 126, 'LINK': 118, 'LTC': 120, 'SOL': 137, 'XRP': 107}
   per close year {'2013': 0, '2014': 0, '2015': 0, '2016': 0, '2017': 0, '2018': 0, '2019': 0, '2020': 0, '2021': 0, '2022': 155, '2023': 259, '2024': 301, '2025': 307, '2026': 174}
   every asset's signal from index 19731 (2022-10-11 00:00:00+00:00); 2021 from 15843; the read opens at 19731 (2022-10-11 00:00:00+00:00), 7606 returns
trial 7, funding z < -2.0, hold 6
   closes 27337; arm A above the full-long size at 0 asset-stamps, equal to it and long at 30632
   block 3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8 {'derivatives-funding': (10, 68281), 'ohlc-full': (10, 173373)}
   re-entry asset-stamps 8046, entries 780, closes where the books differ 3363, turnover A 146.19 B 264.50
   per asset {'ADA': 963, 'AVAX': 740, 'BTC': 684, 'DOGE': 706, 'DOT': 812, 'ETH': 710, 'LINK': 946, 'LTC': 780, 'SOL': 723, 'XRP': 982}
   per close year {'2013': 0, '2014': 0, '2015': 0, '2016': 0, '2017': 0, '2018': 0, '2019': 0, '2020': 218, '2021': 535, '2022': 2407, '2023': 1463, '2024': 1177, '2025': 1691, '2026': 555}
   every asset's signal from index 15419 (2020-10-22 08:00:00+00:00); 2021 from 15843; the read opens at 15843 (2021-01-01 00:00:00+00:00), 11494 returns
```

What it establishes:

- **The full-long size bounds arm A everywhere and equals it where every arm is long** (0 asset-stamps above it, 30,632 equal and long): an asset's arm-A position is its inverse-vol basket weight × each arm's direction × that arm's vol-target level, averaged over the arms (`cli/alpha/a2.py:114-150`), and every arm shares the weights (`basket_lookback` 180), so with every direction 1 it is the weight × the mean of the three levels — the size a re-entry takes (D3).
- **Each block is a landed record's**: trial 6 reads `ohlc-full`'s ten files beside `liquidations-daily`'s ten, `compute_hash` `816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f`, record 54's `dataset_hash`; trial 7 reads `ohlc-full`'s beside `derivatives-funding`'s ten, `3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8`, record 51's (`docs/reference/trial-registry.jsonl`).
- **Both knobs engage**: trial 6 re-enters 1,196 flat asset-stamps over 165 entries, every asset 82 to 163, every year from 2022, the books differing at 509 closes, arm B's turnover 172.92 against arm A's 146.19; trial 7 re-enters 8,046 over 780 entries, every asset 684 to 982, every year from 2020, differing at 3,363 closes, turnover 264.50.
- **The read's start** is the later of the first close every asset's signal holds and the first close of 2021: trial 6 opens at the signal's, index 19,731 (2022-10-11 00:00), 7,606 returns, trial 5's; trial 7 at 2021's, index 15,843, 11,494 returns, its signal holding from 15,419 (2020-10-22 08:00).

The candidates weighed against each other (D1), a second program from the worktree root, re-entering a flat asset at its full-long size where a trigger fires, held a number of closes counted from the last firing close, that close included:

```python
import statistics
from pathlib import Path

from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _inverse_vol_weights
from cli.registry.observed import ObservedReader
from cli.research import subjects

reader = ObservedReader(Path("data"))
inputs = subjects._b2_inputs(reader, "ohlc-full", None, None, False, subject="candidates")
close, arm_a, funding, n = inputs.close, inputs.arm_a, inputs.binperp_funding_z30d, len(inputs.close)
fed = subjects._ffill_btc(inputs.h4_prices)
levels = [
    a2_book_returns(
        fed,
        config=A2Config(
            lookbacks=lookbacks,
            short="off",
            target_vol=target_vol,
            vol_lookback=subjects._B2_LOOKBACK,
            basket_lookback=subjects._B2_LOOKBACK,
            periods_per_year=subjects.PPY_4H,
        ),
    )["vol_target_positions"]
    for lookbacks, target_vol in subjects._B2_A2_ARMS
]
weights = _inverse_vol_weights(fed, lookback=subjects._B2_LOOKBACK)
full_long = {a: [weights[k].get(a, 0.0) * statistics.mean(lv[k] for lv in levels) for k in range(n)] for a in subjects._ASSETS}
liq = subjects._b2_liq_signal(reader, inputs.h4_ts)


def run(name, trig, hold):
    """Re-enter a flat asset at its full-long size where the trigger fires, staying long `hold` closes from the last firing, that close included."""
    stamps = entries = 0
    added, sizes = 0.0, []
    for a in subjects._ASSETS:
        left, prev_b, prev_a = 0, 0.0, 0.0
        for k in range(n):
            p = arm_a[a][k]
            if p > 0:
                left = 0
            elif trig(a, k):
                left = max(left, hold)
            on = p == 0 and left > 0 and full_long[a][k] > 0
            b = full_long[a][k] if on else p
            if on:
                stamps += 1
                sizes.append(b)
                entries += prev_b == 0
            if p == 0 and left > 0:
                left -= 1
            added += abs(b - prev_b) - abs(p - prev_a)
            prev_b, prev_a = b, p
    size = statistics.mean(sizes)
    hurdle = added * subjects._B2_COST_PER_SIDE / (stamps * size)
    print(
        f"{name}, hold {hold}: re-entry asset-stamps {stamps}, entries {entries}, closes per entry {stamps / entries:.1f}, "
        f"added turnover {added:.2f}, mean size {size:.4f}, break-even mean asset return per re-entered close {100 * hurdle:.3f} %"
    )


turnover_a = sum(abs(arm_a[a][k] - (arm_a[a][k - 1] if k else 0.0)) for a in subjects._ASSETS for k in range(n))
print(f"arm A turnover {turnover_a:.2f}")
for threshold in (2.0, 2.5):
    for hold in (1, 6, 12):
        run(f"funding z < -{threshold}", lambda a, k, t=threshold: funding[a][k] is not None and funding[a][k] < -t, hold)
for threshold in (2.0, 2.5):
    run(f"liquidation z > {threshold}", lambda a, k, t=threshold: liq[a][k] is not None and liq[a][k] > t, 1)
start = next(k for k in range(n) if all(funding[a][k] is not None for a in subjects._ASSETS))
print(f"first close every asset's funding z holds: index {start}, {close[start]}")
```

Its output, whole:

```text
arm A turnover 146.19
funding z < -2.0, hold 1: re-entry asset-stamps 3235, entries 1039, closes per entry 3.1, added turnover 154.54, mean size 0.0702, break-even mean asset return per re-entered close 0.408 %
funding z < -2.0, hold 6: re-entry asset-stamps 8046, entries 780, closes per entry 10.3, added turnover 118.31, mean size 0.0706, break-even mean asset return per re-entered close 0.125 %
funding z < -2.0, hold 12: re-entry asset-stamps 12123, entries 624, closes per entry 19.4, added turnover 95.75, mean size 0.0704, break-even mean asset return per re-entered close 0.067 %
funding z < -2.5, hold 1: re-entry asset-stamps 1971, entries 662, closes per entry 3.0, added turnover 97.38, mean size 0.0695, break-even mean asset return per re-entered close 0.427 %
funding z < -2.5, hold 6: re-entry asset-stamps 5103, entries 511, closes per entry 10.0, added turnover 76.16, mean size 0.0696, break-even mean asset return per re-entered close 0.129 %
funding z < -2.5, hold 12: re-entry asset-stamps 7941, entries 440, closes per entry 18.0, added turnover 67.14, mean size 0.0697, break-even mean asset return per re-entered close 0.073 %
liquidation z > 2.0, hold 1: re-entry asset-stamps 1719, entries 227, closes per entry 7.6, added turnover 35.67, mean size 0.0685, break-even mean asset return per re-entered close 0.182 %
liquidation z > 2.5, hold 1: re-entry asset-stamps 1196, entries 165, closes per entry 7.2, added turnover 26.74, mean size 0.0705, break-even mean asset return per re-entered close 0.190 %
first close every asset's funding z holds: index 15419, 2020-10-22 08:00:00+00:00
```

- **The cost each candidate must clear**: a re-entry's gross return is its size × the asset's return and its cost its turnover × 0.006, so the break-even is independent of the size — the added turnover × 0.006 over the re-entered stamps × their mean size, the mean asset return each re-entered close must carry. The funding trigger re-entered only while it fires flickers, 3.1 closes per entry, and must carry 0.408 % a close; held 6 closes from its last firing close, that close included, it must carry 0.125 %, held 12, 0.067 %. The liquidation trigger at 2.5 must carry 0.190 % a close with no hold of its own: its signal is a day's figure, held over the next day's six closes (D3).

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); these trials run under one, the session holding this branch's worktree, `.claude/worktrees/iter183`, on the workstation `zcrypto-ops`, whose main checkout holds the one listed trial-attempts log (`docs/reference/trial-attempt-logs.txt`). No other session runs a bucket-B subject while this branch is open — the ruled subjects outside this spec are frozen by their landed counts, refused by spec 00133 D4 before their fit — no second machine and no restored or copied log; each of those is spec 00133's to count and refuse, not this spec's to design for.
- **The processes.** Each pre-flight and each trial is one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Trial 6 reads `data/ohlc-full` and `data/liquidations-daily`, trial 7 `data/ohlc-full` and `data/derivatives-funding`, symlinks to the main checkout's sets, each frozen and attested; a run writes nothing under them and makes no network call, and nothing this spec runs has a live writer.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained; this worktree is their one writer while the branch is open. `--register` refuses a tree with uncommitted changes (`cli/research/command.py:326-331`), so each trial's record is committed with its decisions-log entry and landed-count literal before the next runs (D7).

## Hypotheses (trials 6–7, pre-registered by this spec's sha256)

Master plan §5's B2 names "funding extremes and OI/liquidation spikes as short-horizon de-risking / re-entry triggers for the spot book" and, by example, "fade post-liquidation-cascade dislocations": a reading of forced or crowded leveraged positioning against the long side marks a dislocation that overshoots and partly reverts. **Taking a full-long position in an asset the ensemble holds flat, for a day after the trigger, improves the ensemble's net-of-cost performance against the unconditioned ensemble.** Arm A is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46 and 48–54 built it; arm B the same ensemble with the re-entries added. Trials 3–5 halved exposure at crowding and lost return each time (registry trials 52–54); these add exposure at a dislocation, the re-entry half of §5's B2 that no trial has tested. The triggers:

- **Trial 6, the liquidation-cascade re-entry** — a two-and-a-half-sigma day of the asset's long-side liquidated notional, trial 5's signal and threshold, read once the day has ended (D4).
- **Trial 7, the funding-extreme re-entry** — a two-sigma-low 30-day funding z-score, crowded shorts paying longs, trial 2's signal mirrored (D4).

The trials run in that order (D1). Each is judged by its own matrix (D5) on its own record; a verdict or a stop of one changes nothing in the next's pre-registration — this spec's sha256 fixes both before the first runs — and never stops it. What each verdict changes is D8's.

## D1 — the pick: two trials in sequence, the re-entries

- **Author's call, under the owner's run instruction** ("try the trials with potential and do not close any family too early"): of B2's untried candidates — the de-risks' park variants (scale 0.25, threshold 3.0), a further de-risk leg (the funding z < −2 re-risk, the OI log-delta or momentum, a single ratio, another liquidation side or window), the two contrarian re-entries, a trial on the 1-minute tape, or closing the family — this iteration runs the two re-entries, one spec and one branch, the liquidation re-entry first, and closes nothing.
- Why these: the three de-risks lost return at every engagement, their drawdowns 0.41 % lower, 28.9 % higher and 0.76 % lower than arm A's (records 52–54), so their variants, which engage less or scale harder, move the same mechanism; the re-entries test the opposite action — the liquidation one on trial 5's own events, the dislocation §5 names, the funding one on trial 2's signal mirrored. Both clear a break-even within a fraction of a percent a close once each holds a day (the measured basis): the funding re-entry's own flicker, unheld, would ask 0.408 % a close. The liquidation re-entry runs first, the one §5 names by example and the one whose hold its signal sets. A trial on the tape waits on an instrument whose window reaches it (spec 00138 D12); the instrument ruling is the owner's.
- A trial's verdict, or its stop, changes nothing in the other's subject, signal, threshold, hold, count, bar or matrix.
- The budget: each landed record spends one of Bucket B's 16 remaining (spec 00133 D5; `BUDGET["B"]` 25, B1 5 and B2 4 spent); a stop or a refused build spends none.

## D2 — the instrument, its windows and the bar, trial 5's unchanged

- Spec 00138 D2, carried to these trials: `--dataset ohlc-full`, no `--window`, no `--as-of`; the union `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices; the arms on `_ffill_btc`'s BTC-only fill, the benchmark on the raw prices; `decisive_start = 1380`; `calendar_year_slices(series, h4_ts)`; the frozen benchmark `benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`; the kill bar `a1_kill_bar(net_b, bench, n_trials=<the subject's>, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`, the SPA grid blocks {30, 102} × seeds {42, 7, 1234}, the headline cell (30, 42); every net through `net_of_cost` at 0.006 per side, the ×1.5 series at `1.5 × 0.006`.
- `var_trials` 0.0 by the owner's word, so the DSR leg is the PSR against 0 at every count; the count (D5) moves no number of the bar.
- Arm A and its pre-flight are spec 00138 D2's: the three adopted A2 arms (`_B2_A2_ARMS`), `short="off"`, vol and basket lookback 180, 2,190 periods a year, their equal-weight per-asset mean.

## D3 — the treatment: a full-long re-entry where arm A is flat, held a day from the trigger

- At return index `k`, for asset `a`: arm B's position is arm A's where arm A's is above 0; else the full-long size where a re-entry is open; else 0. A re-entry opens at a close where arm A is flat and the trigger fires, stays open through `hold` closes counted from the last close at which it fired, that close included, and closes early where arm A turns long — `reentry_positions(arm_a, full_long, fires, hold=<the trial's>)`, new in `cli/alpha/b2.py`, the measured basis's `reentry` word for word.
- **The full-long size**: `weights[k][a] × mean(levels[k])`, where `weights` is `_inverse_vol_weights(fed, lookback=180)` (`cli/alpha/a1.py:164`) and `levels` the three arms' `vol_target_positions` from the same `a2_book_returns` calls that build arm A — `full_long_sizes(weights, levels, assets)`, new in `cli/alpha/b2.py`. It is the position arm A holds in the asset where every arm's direction is long (the basis: never exceeded, equal at 30,632 long stamps), so a re-entry takes no more risk per asset than the ensemble takes in a trend, and an asset with no basket weight yet re-enters at 0.
- **Author's call — a day from the trigger.** Trial 6's signal is a day's figure read from the first close at or after the day ends (D4), so it fires on each of the next day's six closes and its hold is 1: the re-entry lasts the day after a spike day, longer where the next day fires too (7.2 closes per entry). Trial 7's funding z-score moves with each 8-hourly print, so it fires on the two closes a print spans and its hold is 6, one day from the last firing close (10.3 closes per entry). A longer hold lowers the funding re-entry's break-even further (0.067 % at 12) but holds the trade past the day the dislocation's reversal is argued for; the day is the horizon both share.
- No hold-through: each entry and exit is a trade charged 0.006 per side on the position change, so arm B pays its own turnover and the matrix reads it net of cost. A `None` signal fires nothing. Where arm A is long, arm B is arm A: a re-entry never resizes a position the ensemble holds.

## D4 — the signals and thresholds: trial 5's and trial 2's, at pre-registered constants

- **Trial 6**: `_b2_liq_signal(reader, h4_ts)` (spec 00138 D6), unchanged — per asset the 30-day z-score of the daily long-side liquidated notional from `liquidations-daily/<COIN>/daily.parquet`, `daily_zscore_grid_feature`, a day read from the first close at or after its end; it fires where the z-score is above 2.5 (`_B2_LIQ_REENTRY_THRESHOLD`). **Author's call**: 2.5 is the threshold trial 5's rule picked on this block (spec 00138's completed basis), so the trial reads trial 5's own events with the opposite action; spec 00138 D3's rule measures a share of arm A's long stamps, which a re-entry on flat stamps does not engage, so it is not re-applied. The long side, not the total or the short side: a long-side cascade is the forced sale whose overshoot the re-entry buys; a short squeeze is forced buying, which a long re-entry would chase.
- **Trial 7**: `_b2_funding_signal(reader, h4_ts)`, new in `cli/research/subjects.py` — per asset `funding_grid_feature(..., config=B2Config())` over `derivatives-funding/<PERP>/funding.parquet`, `_b2_inputs`' own loop, the 30-day z-score trial 2 read; it fires where the z-score is below −2.0 (`_B2_FUNDING_REENTRY_THRESHOLD`). **Author's call**: −2.0, spec 00128 D3's threshold mirrored — that spec named the stamps at z < −2 "a later trial's candidate (a re-risk or the contrarian re-entry §5 names)".
- A threshold, a hold or a signal changed after a result is a new trial.

## D5 — the head-to-head, the bar, the drawdown pair, the matrix and the counts

- **The read's start** — the owner's "From-2021 primary" with spec 00138 D8's later-signal rule: the later of the first return index at which every asset's signal is defined and the first closing at or after 2021-01-01 — `_b2_reentry_start(inputs)`, new; trial 6 19,731 (7,606 returns), trial 7 15,843 (11,494), each recorded as `primary_returns`. The head-to-head `net_of_cost_verdict(net_b[start:], net_a[start:], mean_block=30, seed=42, n_resamples=2000)`, primary, keyed `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`; the full window beside it.
- **The drawdown pair**, from the start: `max_drawdown(net_b[start:])`, `max_drawdown(net_a[start:])` and `max_drawdown_reduction_pct = 100 × (A − B) / A`, spec 00138 D8's keys; here a negative reduction is arm B's drawdown above arm A's.
- **Refused before any bar**, spec 00138 D8's two: fewer than 2 return indices from the start, and an arm A that never draws down from it.
- **The matrix — Author's call**: the hypothesis is return, so the drawdown leg bounds a return bought with risk instead of demanding a reduction — arm B adds exposure where arm A holds none, so a drawdown at or below arm A's is not its claim. The bound is a fifth: arm B's drawdown at most 1.2 × arm A's, a reduction of at least −20 %.

| Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from the read's start) | Verdict |
| --- | --- | --- |
| pass | B beats A (mean outperformance > 0 and SPA p < 0.05) and B's maximum drawdown at most 1.2 × A's | **adopt** the re-entry |
| pass | B > A point estimate, and not both SPA p < 0.05 and B's maximum drawdown at most 1.2 × A's | **park** (variant candidates: the threshold one step toward 0 — 2.0 from 2.5, −1.5 from −2.0 — and the size halved) |
| pass | B ≤ A (mean outperformance ≤ 0) | **reject** the re-entry |
| fail | any — arm A having passed the same bar before the run | **reject** |

  The rows are disjoint and cover every outcome; the rule, as the subjects declare it (spec 00129 D4), with the instrument findings its metrics show:

```python
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

- **The counts**: trial 6 5, trial 7 6 (`_B2_LIQ_REENTRY_N_TRIALS`, `_B2_FUNDING_REENTRY_N_TRIALS`) — each the family's `required_n("B2")` when its predecessors have landed records (`cli/registry/attempts.py:496-498`: landed records plus orphans plus one; records 51–54 make trial 6's 5). **Author's call**: fixed by this spec's hash, never raised in place; spec 00133 D4 admits a declared count above `required_n`, so where trial 6 stops unspent trial 7 declares one more than the count needs, a figure no number of its bar reads at `var_trials` 0.0. A refusal from the count (an orphan) sends the trial to T0023: a further count is a new subject under a new spec.

## D6 — the subjects, their records and the build

- **Four subjects** in `cli/research/subjects.py`, all `spec="docs/specs/00139-b2-reentries-design.md"`, `_ASSETS`, intervals `(240,)`: the trials `b2-liq-reentry` and `b2-funding-reentry` — `metric_keys=_b2_overlay_metric_keys(<signal key>)`, the keys `binperp_liq_long_z30d` and `binperp_funding_z30d`, seeds (42, 7, 1234), `verdict=_b2_reentry_verdict`, `no_verdict` trial 2's text word for word ("instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"), `family="B2"`, `n_trials` D5's count — and their evaluate-only twins `b2-liq-reentry-preflight` and `b2-funding-reentry-preflight` — `metric_keys=_b2_overlay_preflight_keys(<signal key>)`, seeds (42,), no rule, family or count, so `--register` refuses them, their plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). No incumbent: arm A is built in the run. Every trial and twin refuses `--as-of` before any read: "<subject> evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset".
- **The keys are the overlays'** — a trial's 42, a twin's 22 — **Author's call**, so the subjects join the overlays' machinery unchanged; `threshold` is the trial's (2.5 or −2.0), and `engaged_per_asset` and `engaged_per_year` count the flat asset-stamps a re-entry holds (`reentry_counts_per_year`, new in `cli/alpha/b2.py`), not long stamps halved; the twin computes them from arm A, the full-long size and the signal, with no return of arm B.
- **The records** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B2`; `n_trials_in_family` the subject's count; variants `B2-liq-reentry-a2eq-full-v1` and `B2-funding-reentry-a2eq-full-v1`; iteration `iter-183`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `816f62f9…30474f` and `3da5e397…fc18a8`; `attempt` the trial-attempts log's; `notes` caller text written before the run (D7).
- **The build in halves.** The inputs: `_b2_reentry_inputs(subject, read_signal, fire, hold, threshold, reader, dataset, window, accept_holes)` — the union and spec 00138's two window refusals (`_b2_overlay_inputs`' own), the signal by its reader, arm A by `_b2_overlay_inputs`' own expression (**Author's call**: repeated, so the books it builds also yield the levels for the full-long size, with no second `a2_book_returns` pass), the full-long size and arm B's positions. The computes: `_b2_reentry_metrics(inputs, *, signal_key, n_trials)` — `_b2_overlay_metrics`' body with `inputs.arm_b` in `scale_positions(arm_a, scales)`'s place, the read's start in `_b2_overlay_start`'s and the re-entry engagement in the overlay engagement's — and `_b2_reentry_preflight_metrics`; a compute error is a `SubjectError` naming the subject and its window. The plan's wiring test proves `_b2_reentry_metrics` against `_b2_overlay_metrics` on one input set.
- **The files the build touches, a closed list**: `cli/alpha/b2.py` — the import `statistics`, which `full_long_sizes` averages the levels with as arm A averages the arms, and the functions `full_long_sizes`, `reentry_positions` and `reentry_counts_per_year`; `cli/research/subjects.py` — the imports, the constants `_B2_LIQ_REENTRY_THRESHOLD`, `_B2_LIQ_REENTRY_HOLD`, `_B2_LIQ_REENTRY_N_TRIALS`, `_B2_FUNDING_REENTRY_THRESHOLD`, `_B2_FUNDING_REENTRY_HOLD` and `_B2_FUNDING_REENTRY_N_TRIALS`, `_B2ReentryInputs`, `_b2_funding_signal`, `_b2_reentry_inputs`, `_b2_reentry_start`, `_b2_reentry_engagement`, `_b2_reentry_metrics`, `_b2_reentry_preflight_metrics`, `_b2_reentry_build`, four `_build_` wrappers, `_b2_reentry_verdict` and four `SUBJECTS` entries; no existing function of either file changed; `README.md`'s `--subject` row; the tests the plan names. No change to `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/engine/*`, `cli/liquidations/*`, specs 00128, 00137 and 00138, the subjects of trials 1–5, or any adopted artifact.

## D7 — the pre-flights and the runs, through spec 00133's trial-attempts log

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00139-b2-reentries-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` — before each append; (3) the data-gated basis tests on the run's tree; then for each trial in D1's order: (4) its pre-flight twin's plain eval, read in this order — (a) the block (trial 6 `816f62f9…`, `liquidations-daily` `checked (10 vouched hashes)`; trial 7 `3da5e397…`, `derivatives-funding` `checked (10 vouched hashes)`), (b) arm A's seven anchors at record 45's stored precision (spec 00137 D7's (b)), (c) `engaged_per_asset`, `engaged_per_year`, `primary_returns` and `threshold` equal to the measured basis (the plan's data-gated literals), and the signal's coverage equal to the inputs half's over the same sets, the data-gated tests holding that half's first close every asset's signal holds to the basis's, (d) the dead knob — the engaged total above 0 — and (e) arm A's `passes` 1; a failure of (a)–(e) is an instrument finding, the run kept as a reading under iter-183 (`--reading --iteration iter-183 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent, and the next trial goes ahead; (5) on a pass, the trial's one run, `--register --iteration iter-183 --family B2 --n-trials <D5's count> --variant <D6's> --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10); (6) the record's checks and its commit — the registry line, the decisions-log verdict entry and the landed-count literal together, since the tie tests hold only over the three — before the next trial's (4).
- **The hash rule**: before (1), nobody computes a return of arm B or a kill bar over the real data; the basis holds positions and signals only.
- **The notes, written before each run** (spec 00137 D10's): the subject over `ohlc-full`, full history; the arms, the signal, the threshold and the hold; the hypothesis; the count and `var_trials` 0.0; the read from its start deciding, the full-window read beside it; the pre-flight's figures, quoted; the park variants; the matrix pre-registered by this spec's sha256.
- A refusal from the count, a refused build or a stop by the rule under `--register`: spec 00137 D10's handling, per trial; none stops the next.

## D8 — what a verdict changes

- **Adopt** is a research-registry fact on the A2 ensemble alone and does not touch the live book: the daily liquidations are Coinalyze's history, fetched once into a frozen block, a lower bound, and the funding set Binance's archive; a live feed for either is a new spec. Deploying follows spec 00138 D11's B1 precedent — a P1 combination trial over record 47's book, outside every bucket's budget; then the live feed's spec; then T0123's promotion path — and T0123's `ripe_when`, which reads any ADOPT, gains the qualification spec 00138 D11 names in the first adopt's records commit, a second adopt adding its record to it.
- **Park** names its variant candidates in the record — the threshold one step toward 0 and the size halved — each a new trial of the shared budget, T0023's to pick.
- **Reject** archives the hypothesis in the record and the decisions log; the next trial runs regardless (D1).
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, or a refused build — spends no trial; T0023 records what failed.
- After the two, B2's next step — a park's variants, a de-risk variant, a further leg, a trial on the tape, or closing the family — is T0023's trigger; a close is the owner's.

## Out of scope

Any hold, hysteresis or extension of a re-entry other than D3's, and any threshold, side, window or signal other than D4's; the de-risks' park variants and further de-risk legs (spec 00138's out-of-scope list); a re-entry on the OI or ratio signals; a trial on the 1-minute tape or on any instrument but frozen `ohlc-full`; a live liquidation or funding feed; Bucket B's other families (B3, B4-legs), T0016's; any change to an existing function, subject or record.
