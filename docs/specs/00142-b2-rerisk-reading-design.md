# B2's re-risk reading — the twelve crowding signals' forward returns where arm A is long below its full-long size, by tail, on the frozen `ohlc-full` set

**Ruling:** the owner launched this unattended run, verbatim: "continue pushing the Research strates forward, pick the most relevant tasks. override the wall clock time gate, but do not pick up new topics after 8:00Z. when closing out a research step, try the trials with potential and do not close any family too early." Reading 4 found no cell with potential (`[iter-185] B2's eight untested crowding signals read for forward returns by tail and by arm A's state on frozen ohlc-full (reading 4)`), as reading 3 before it, so B2's next step after the second signal reading — T0023's trigger — is the loop's pick, recorded as `[iter-186] B2's next step after the second signal reading` in `docs/research/10.phase4-decisions.md` (D1); a close of B2 is the owner's and is not picked. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)". Iteration `iter-186`, branch `research/iter-186-b2-rerisk-reading`, topic T0023 under T0016. Spec 00141 is this spec's precedent and its form — its D5, D6 and D8 are carried here, each change named where it is made — and spec 00139 D3's full-long size bounds the state this reading reads.

## The measured basis

Every figure below was measured on 2026-10-23 in this branch's worktree at develop's `8555c905e`, with `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily` symlinked read-only from the main checkout's `data/`, the code of plan 00142's Tasks 1–2 in the working tree: positions, the full-long size, signals, counts and the datasets block over the real sets, and the computes half over synthetic inputs only — no forward return at any stamp was computed over the real data. The first program ran between 06:13:25Z and 06:19:18Z, the second between 06:19:36Z and 06:22:33Z, the third at 06:22:33Z.

**The inputs**, a first program from the worktree root, reading the twelve signals, arm A and its full-long size through the reading's own inputs half (`_b2_rerisk_inputs`, D3–D4) — its full-long half timed through a wrapper — and counting each pair's events and others in the state with `_b2_rerisk_counts` (D7), and beside them the events at the full-long size, where no re-risk acts:

```python
import resource
import statistics
import time
from pathlib import Path

from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

rebuilt = []
full_long_sizes = subjects._b2_full_long


def timed(h4_prices):
    start = time.perf_counter()
    out = full_long_sizes(h4_prices)
    rebuilt.append(time.perf_counter() - start)
    return out


subjects._b2_full_long = timed
start = time.perf_counter()
reader = ObservedReader(Path("data"))
inputs = subjects._b2_rerisk_inputs("b2-rerisk-reading", reader, "ohlc-full", None, False)
close, arm_a, full, n, assets = inputs.close, inputs.arm_a, inputs.full_long, len(inputs.close), subjects._ASSETS
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"inputs read in {time.perf_counter() - start:.0f} s, the full-long size's books rebuilt in {rebuilt[0]:.0f} s of it, peak RSS {peak / 1024:.0f} MiB; closes {n}")
block = reader.block()
print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in sorted(block.items())})
print("vouched", reader.vouched_status())
tol = subjects._B2_RERISK_TOLERANCE
pairs = {a: list(zip(arm_a[a], full[a])) for a in assets}
print("arm A long", [sum(p > 0 for p, _ in pairs[a]) for a in assets], "flat", [sum(p == 0 for p, _ in pairs[a]) for a in assets])
below = [sum(0 < p < f - tol for p, f in pairs[a]) for a in assets]
at = [sum(p > 0 and abs(f - p) <= tol for p, f in pairs[a]) for a in assets]
above = sum(p > f + tol for a in assets for p, f in pairs[a])
print(f"long below the full-long size {sum(below)} {below}; long at it {sum(at)} {at}; above it {above}")
near = max(abs(f - p) for a in assets for p, f in pairs[a] if p > 0 and abs(f - p) <= tol)
gap = min(f - p for a in assets for p, f in pairs[a] if 0 < p < f - tol)
print(f"at it, the largest |full-long - arm A| {near:.3e}; below it, the smallest gap {gap:.3e}")
ratio = [p / f for a in assets for p, f in pairs[a] if 0 < p < f - tol]
print("below it, arm A over its full-long size: median", round(statistics.median(ratio), 4), "quartiles", [round(q, 4) for q in statistics.quantiles(ratio, n=4)])
fed = subjects._ffill_btc(inputs.h4_prices)
for key, signal in inputs.signals.items():
    every = next(k for k in range(n) if all(signal[a][k] is not None for a in assets))
    priceless = sum(signal[a][k] is not None and fed[a][k] is None and 0 < arm_a[a][k] < full[a][k] - tol for a in assets for k in range(n))
    print(f"{key}: every asset's from index {every} ({close[every]}); read below the full-long size where the close is missing {priceless}")
counts = subjects._b2_rerisk_counts(inputs)
for key, signal in inputs.signals.items():
    for tail in subjects._B2_READING_TAILS:
        e = [counts["events_per_asset"][key][tail]["below_full"][a] for a in assets]
        o = [counts["others_per_asset"][key][tail]["below_full"][a] for a in assets]
        able = sum(x >= 2 and y >= 2 for x, y in zip(e, o))
        past = (lambda z: z > 2.0) if tail == "above" else (lambda z: z < -2.0)
        at_full = sum(signal[a][k] is not None and past(signal[a][k]) and arm_a[a][k] > 0 and abs(full[a][k] - arm_a[a][k]) <= tol for a in assets for k in range(n))
        print(f"{key} {tail}: events {sum(e)} {e}; others {sum(o)} {o}; assets with two of each {able}; events at the full-long size {at_full}")
```

Its output, whole, each list in `_ASSETS`' order (ADA, AVAX, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP):

```text
inputs read in 352 s, the full-long size's books rebuilt in 82 s of it, peak RSS 450 MiB; closes 27337
block ad140b62ac72cfd6b4931dbe4f529f29d4dd34ef49d86e791c37764d2cf8eee1 {'derivatives-funding': (10, 68281, ['2020-01-01 00:00:00+00:00', '2026-06-30 16:00:00+00:00']), 'derivatives-oi': (10, 5010882, ['2020-09-01 00:00:00+00:00', '2026-07-22 23:55:00+00:00']), 'liquidations-daily': (10, 15048, ['2022-08-25 00:00:00+00:00', '2026-10-20 00:00:00+00:00']), 'ohlc-full': (10, 173373, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)', 'derivatives-funding': 'checked (10 vouched hashes)', 'derivatives-oi': 'checked (10 vouched hashes)', 'liquidations-daily': 'checked (10 vouched hashes)'}
arm A long [8938, 4680, 17169, 6766, 6640, 13428, 7954, 11958, 6024, 9905] flat [18399, 22657, 10168, 20571, 20697, 13909, 19383, 15379, 21313, 17432]
long below the full-long size 62830 [6075, 3289, 10781, 4874, 4884, 8260, 5483, 8296, 4104, 6784]; long at it 30632 [2863, 1391, 6388, 1892, 1756, 5168, 2471, 3662, 1920, 3121]; above it 0
at it, the largest |full-long - arm A| 1.110e-16; below it, the smallest gap 1.072e-03
below it, arm A over its full-long size: median 0.3333 quartiles [0.1998, 0.3333, 0.6157]
binperp_funding_z30d: every asset's from index 15419 (2020-10-22 08:00:00+00:00); read below the full-long size where the close is missing 0
binperp_oi_z30d: every asset's from index 18026 (2021-12-30 20:00:00+00:00); read below the full-long size where the close is missing 0
binperp_ratio_max_z30d: every asset's from index 20298 (2023-01-13 12:00:00+00:00); read below the full-long size where the close is missing 0
binperp_liq_long_z30d: every asset's from index 19731 (2022-10-11 00:00:00+00:00); read below the full-long size where the close is missing 0
binperp_oi_log_delta_z30d: every asset's from index 18027 (2021-12-31 00:00:00+00:00); read below the full-long size where the close is missing 0
binperp_oi_momentum_z30d: every asset's from index 18206 (2022-01-29 20:00:00+00:00); read below the full-long size where the close is missing 0
binperp_count_toptrader_long_short_ratio_z30d: every asset's from index 20298 (2023-01-13 12:00:00+00:00); read below the full-long size where the close is missing 0
binperp_sum_toptrader_long_short_ratio_z30d: every asset's from index 20298 (2023-01-13 12:00:00+00:00); read below the full-long size where the close is missing 0
binperp_count_long_short_ratio_z30d: every asset's from index 18324 (2022-02-18 12:00:00+00:00); read below the full-long size where the close is missing 0
binperp_sum_taker_long_short_vol_ratio_z30d: every asset's from index 18994 (2022-06-10 04:00:00+00:00); read below the full-long size where the close is missing 0
binperp_liq_short_z30d: every asset's from index 19731 (2022-10-11 00:00:00+00:00); read below the full-long size where the close is missing 0
binperp_liq_total_z30d: every asset's from index 19731 (2022-10-11 00:00:00+00:00); read below the full-long size where the close is missing 0
binperp_funding_z30d above: events 1059 [98, 44, 97, 157, 102, 86, 97, 159, 58, 161]; others 47109 [4902, 3245, 5031, 4717, 4775, 4973, 5223, 5433, 4021, 4789]; assets with two of each 10; events at the full-long size 2427
binperp_funding_z30d below: events 1210 [130, 106, 151, 116, 80, 128, 145, 142, 85, 127]; others 46958 [4870, 3183, 4977, 4758, 4797, 4931, 5175, 5450, 3994, 4823]; assets with two of each 10; events at the full-long size 205
binperp_oi_z30d above: events 2648 [272, 170, 292, 370, 279, 296, 261, 239, 219, 250]; others 30754 [2711, 2930, 3733, 3181, 3180, 2861, 3190, 3120, 3136, 2712]; assets with two of each 10; events at the full-long size 2608
binperp_oi_z30d below: events 677 [24, 72, 134, 21, 73, 46, 68, 58, 123, 58]; others 32725 [2959, 3028, 3891, 3530, 3386, 3111, 3383, 3301, 3232, 2904]; assets with two of each 10; events at the full-long size 259
binperp_ratio_max_z30d above: events 5036 [421, 472, 587, 512, 650, 369, 557, 491, 547, 430]; others 19237 [1630, 1802, 2604, 1854, 1825, 1832, 1976, 2032, 1896, 1786]; assets with two of each 10; events at the full-long size 3157
binperp_ratio_max_z30d below: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 24273 [2051, 2274, 3191, 2366, 2475, 2201, 2533, 2523, 2443, 2216]; assets with two of each 0; events at the full-long size 0
binperp_liq_long_z30d above: events 1483 [124, 150, 125, 181, 194, 128, 142, 162, 128, 149]; others 27771 [2591, 2577, 2776, 2801, 3017, 2689, 2977, 2899, 2836, 2608]; assets with two of each 10; events at the full-long size 1260
binperp_liq_long_z30d below: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 29254 [2715, 2727, 2901, 2982, 3211, 2817, 3119, 3061, 2964, 2757]; assets with two of each 0; events at the full-long size 0
binperp_oi_log_delta_z30d above: events 876 [88, 92, 98, 111, 75, 77, 94, 74, 92, 75]; others 32502 [2892, 3006, 3923, 3438, 3381, 3078, 3354, 3282, 3262, 2886]; assets with two of each 10; events at the full-long size 560
binperp_oi_log_delta_z30d below: events 700 [67, 63, 102, 74, 72, 70, 69, 57, 72, 54]; others 32678 [2913, 3035, 3919, 3475, 3384, 3085, 3379, 3299, 3282, 2907]; assets with two of each 10; events at the full-long size 370
binperp_oi_momentum_z30d above: events 2234 [196, 161, 306, 313, 257, 163, 249, 243, 169, 177]; others 28280 [2579, 2802, 3280, 2836, 2841, 2735, 2952, 2825, 2841, 2589]; assets with two of each 10; events at the full-long size 1840
binperp_oi_momentum_z30d below: events 945 [94, 93, 96, 51, 84, 99, 116, 86, 131, 95]; others 29569 [2681, 2870, 3490, 3098, 3014, 2799, 3085, 2982, 2879, 2671]; assets with two of each 10; events at the full-long size 474
binperp_count_toptrader_long_short_ratio_z30d above: events 1688 [185, 206, 253, 130, 206, 111, 164, 173, 154, 106]; others 23295 [2041, 2127, 2981, 2274, 2426, 2135, 2405, 2419, 2363, 2124]; assets with two of each 10; events at the full-long size 759
binperp_count_toptrader_long_short_ratio_z30d below: events 725 [62, 36, 72, 46, 51, 81, 102, 83, 144, 48]; others 24258 [2164, 2297, 3162, 2358, 2581, 2165, 2467, 2509, 2373, 2182]; assets with two of each 10; events at the full-long size 533
binperp_sum_toptrader_long_short_ratio_z30d above: events 2419 [183, 220, 177, 289, 385, 170, 294, 241, 243, 217]; others 23939 [2127, 2223, 3152, 2289, 2386, 2301, 2416, 2486, 2375, 2184]; assets with two of each 10; events at the full-long size 2635
binperp_sum_toptrader_long_short_ratio_z30d below: events 578 [20, 30, 147, 24, 63, 90, 53, 59, 69, 23]; others 25780 [2290, 2413, 3182, 2554, 2708, 2381, 2657, 2668, 2549, 2378]; assets with two of each 10; events at the full-long size 132
binperp_count_long_short_ratio_z30d above: events 1976 [193, 231, 303, 180, 165, 163, 196, 176, 210, 159]; others 31406 [2804, 2847, 3768, 3322, 3231, 2931, 3196, 3271, 3183, 2853]; assets with two of each 10; events at the full-long size 596
binperp_count_long_short_ratio_z30d below: events 1241 [159, 109, 67, 105, 144, 89, 161, 150, 131, 126]; others 32141 [2838, 2969, 4004, 3397, 3252, 3005, 3231, 3297, 3262, 2886]; assets with two of each 10; events at the full-long size 701
binperp_sum_taker_long_short_vol_ratio_z30d above: events 1436 [105, 128, 184, 132, 137, 129, 152, 170, 172, 127]; others 30700 [2686, 2756, 3794, 3115, 3043, 2981, 3187, 3198, 3114, 2826]; assets with two of each 10; events at the full-long size 361
binperp_sum_taker_long_short_vol_ratio_z30d below: events 11 [0, 3, 1, 1, 1, 1, 2, 0, 2, 0]; others 32125 [2791, 2881, 3977, 3246, 3179, 3109, 3337, 3368, 3284, 2953]; assets with two of each 3; events at the full-long size 9
binperp_liq_short_z30d above: events 1517 [167, 156, 116, 124, 196, 137, 208, 201, 106, 106]; others 27737 [2548, 2571, 2785, 2858, 3015, 2680, 2911, 2860, 2858, 2651]; assets with two of each 10; events at the full-long size 1746
binperp_liq_short_z30d below: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 29254 [2715, 2727, 2901, 2982, 3211, 2817, 3119, 3061, 2964, 2757]; assets with two of each 0; events at the full-long size 0
binperp_liq_total_z30d above: events 1054 [106, 85, 69, 131, 129, 80, 134, 121, 92, 107]; others 28200 [2609, 2642, 2832, 2851, 3082, 2737, 2985, 2940, 2872, 2650]; assets with two of each 10; events at the full-long size 1669
binperp_liq_total_z30d below: events 6 [0, 0, 0, 0, 0, 6, 0, 0, 0, 0]; others 29248 [2715, 2727, 2901, 2982, 3211, 2811, 3119, 3061, 2964, 2757]; assets with two of each 1; events at the full-long size 0
```

What it establishes:

- **The block is reading 3's**: `ohlc-full`'s ten 4h files beside the ten files of `derivatives-funding`, `derivatives-oi` and `liquidations-daily`, `compute_hash` `ad140b62ac72cfd6b4931dbe4f529f29d4dd34ef49d86e791c37764d2cf8eee1` — reading 3's own block (spec 00140's basis) — every set `checked` against its vouched hashes, so each is on the hub's `hot/` and the reading needs no push. The funding set is read because the funding z-score is one of the twelve (D4).
- **Arm A's states are reading 3's**: 93,462 long asset-stamps and 179,908 flat, per asset the figures specs 00140's and 00141's bases printed.
- **The full-long split**: of the 93,462 long asset-stamps, 62,830 lie below arm A's full-long size and 30,632 at it — spec 00139's basis's figure — and none above it. At the full-long size arm A differs from it by at most 1.110e-16, and below it by at least 1.072e-03, so a tolerance of 1e-12 parts the two by orders of magnitude on each side (D3). Below it, arm A holds a median third of its full-long size (quartiles 0.1998, 0.3333 and 0.6157), so a re-risk there would add a median two-thirds of that size.
- **Each signal's span is its reading's**: the first close every asset's signal holds is spec 00140's for reading 3's four and spec 00141's for reading 4's eight, from the funding z-score's index 15,419 (2020-10-22 08:00) to the toptrader ratios' 20,298 (2023-01-13 12:00).
- **No signal is read below the full-long size where the close is missing**: zero asset-stamps on every signal — the funding signal's 4,053 such stamps (spec 00140's basis) fall where arm A is flat, its asset having no close to hold.
- **Most of the near-miss cells' events fall at the full-long size, where no re-risk acts**: of the long-state events behind readings 3's and 4's nearest cells (D1) — every one above +2.0 — the funding z-score's lie 2,427 at the full-long size and 1,059 below it, the long side's 1,260 and 1,483, the short side's 1,746 and 1,517, and the total's 1,669 and 1,054: 7,102 of 12,215 at the size, where raising arm A to it changes nothing, beside the 5,113 below it this reading reads.
- **The cells**: nine of the 72 read no row — the lower tails of the ratios' maximum, the long side and the short side, at all three horizons, holding no event below the full-long size (as none in either state, specs 00140's and 00141's bases). Two signal-tail pairs, six cells, hold few: the taker ratio's lower tail, 11 events (three assets with two of each), and the total's, six, all ETH's; their six cells fall under D8's floor before any forward is read — a pooled row's events never exceed its pair's, nor its kept assets the assets with two of each — so they are unread. Every other pair holds two events and two others on all ten assets, from the summed toptrader ratio's lower tail, 578 events, to the ratios' maximum's upper tail, 5,036. So 63 cells can read a pooled row, each where its events' forwards are read, and the floor admits 57 of them at most.

**The computes half**, a second program from the worktree root: the reading's whole compute — the forwards, the one draw, the 24 contrasts, the counts and the constants (`_b2_rerisk_metrics`, D7) — on synthetic inputs of its size: ten assets' prices over 27,338 closes, a random walk with asset i missing its first 1,000 × i closes; a full-long size of 0.1 throughout, arm A at it at about 11 % of the asset-stamps and at half of it at about 23 % — the real 30,632 and 62,830 of 273,370; twelve signals drawn from a standard normal from index 18,000 on:

```python
import math
import random
import resource
import time

from cli.research import subjects

rng = random.Random(42)
n = 27_337
assets = subjects._ASSETS
prices = {}
for i, a in enumerate(assets):
    level, path = 100.0, []
    for k in range(n + 1):
        level *= math.exp(rng.gauss(0.0002, 0.02))
        path.append(None if k < 1000 * i else level)
    prices[a] = path
full_long = {a: [0.1] * n for a in assets}
arm_a = {a: [0.1 if u < 0.11 else 0.05 if u < 0.34 else 0.0 for u in (rng.random() for _ in range(n))] for a in assets}
signals = {key: {a: [None if k < 18_000 else rng.gauss(0, 1) for k in range(n)] for a in assets} for key in subjects._B2_RERISK_SIGNALS}
inputs = subjects._B2ReriskInputs([None] * (n + 1), prices, [None] * n, arm_a, full_long, signals)
built = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
start = time.perf_counter()
metrics = subjects._b2_rerisk_metrics(inputs)
elapsed, peak = time.perf_counter() - start, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
rows = sum(len(by_state) for key in metrics if "_fwd_" in key for by_tail in metrics[key].values() for by_state in by_tail.values())
print(f"computes half: {elapsed:.0f} s, peak RSS {peak:.0f} MiB, {built:.0f} MiB with the inputs built; {len(metrics)} keys, {rows} rows")
```

Its output, whole:

```text
computes half: 176 s, peak RSS 431 MiB, 145 MiB with the inputs built; 79 keys, 1584 rows
```

- The computes half takes 176 s and peaks 286 MiB above its inputs; with the inputs half's 352 s and 450 MiB (the first program), the reading's run is near 528 s, about nine minutes, against reading 4's seven (spec 00141's basis). The inputs half reads every signal reading 3 and reading 4 read, and its full-long half — the three books rebuilt (D3) — takes 82 s of its 352.

**The name**, a third program from the worktree root, with the subject registered (D2):

```python
from cli.research.subjects import SUBJECTS
from tests.retired_subjects import RETIRED_SUBJECTS

name = "b2-rerisk-reading"
others = (set(SUBJECTS) | RETIRED_SUBJECTS) - {name}
print("registered", name in SUBJECTS, "; names it equals or opens with a hyphen:", sorted(o for o in others if name == o or name.startswith(f"{o}-")))
print("names opening with it and a hyphen:", sorted(o for o in others if o.startswith(f"{name}-")))
```

Its output, whole:

```text
registered True ; names it equals or opens with a hyphen: []
names opening with it and a hyphen: []
```

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this reading runs under one, the session holding this branch's worktree, `.claude/worktrees/iter186`, on the workstation `zcrypto-ops`. No other session appends to `docs/reference/reading-ledger.jsonl` while this branch is open.
- **The process.** The reading is one `uv run zcrypto research eval` process in this worktree, awaited to its exit — no daemon, timer or concurrent run, and no step reads it as ended while its process lives. It reads `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily`, symlinks to the main checkout's sets, each frozen and attested; it writes nothing under them, makes no network call, and nothing it reads has a live writer.
- **No trial-attempts log.** A subject with no rule registers no trial: `--reading` begins no attempt and its line carries `attempt` `null`, as readings 2–4 do; the trial-attempts log and Bucket B's budget are untouched.
- **The reading ledger** — tracked, append-only, hash-chained; this worktree is its one writer while the branch is open. `--reading` refuses a tree with uncommitted changes, so the run's line is committed with its decisions-log entry before anything else lands (D9).

## The question (no hypothesis, no bar)

Readings 3 and 4 found no cell with potential among B2's twelve crowding signals, each read by tail inside arm A's long or flat state. Their nearest cells were re-risks at 96 hours with arm A long — the funding z-score above +2.0 (reading 3, the one cell meeting its second leg), the long side's liquidation z-score above +2.0 (reading 3, its fourth leg), and the short side's and the total's above +2.0 (reading 4, legs 2–4) — but their long state mixed the closes where arm A already holds its full-long size, where a re-risk adds nothing, with those below it (the basis: 7,102 of those cells' 12,215 events at the size). This reading asks their question in the one state a re-risk can act in: **after a close at which a signal lies past ±2 and arm A is long below its full-long size, does the asset's forward log return differ from its forward return after the other closes at which the signal is read in that state?** A cell that clears the potential criterion (D8) names the trial it would justify; none clearing it is the evidence the owner's family call reads. The reading tests no hypothesis, has no bar, matrix or verdict, spends no B slot, and changes no verdict of trials 2–7 nor readings 3's and 4's findings.

## D1 — the pick: a third no-slot reading, over the re-risk's own state

- **Author's call, under the owner's run instruction** ("try the trials with potential and do not close any family too early"), among four:
  1. **Variants of the trials already run** — a de-risk at another scale or threshold, the re-entries' park variants; each spends a B slot (14 of 25 remain), and neither reading shows a de-risk or re-entry cell with potential.
  2. **A third no-slot reading over the re-risk's own state** — the twelve signals of readings 3 and 4 by tail where arm A is long below its full-long size, the one state a re-risk can act in. Both readings' nearest cells are re-risks at 96 hours above +2.0 with arm A long, but most of their events fall where arm A already holds its full-long size, where no re-risk acts (the basis). Spends no slot and screens the re-risk where it can engage before a slot is spent. Chosen.
  3. **A re-risk trial spent directly on a near-miss** — one of 14 slots on a cell neither reading admitted under its criterion.
  4. **The 1-minute tape, or a close of B2** — an instrument ruling and a family call, both the owner's.
- The reading closes nothing: whatever it reads, B2 stays open, and a close is the owner's (D8).

## D2 — the instrument and the subject: frozen `ohlc-full`, full history, a reading

- **One reading subject**, `b2-rerisk-reading` in `cli/research/subjects.py`: `spec="docs/specs/00142-b2-rerisk-reading-design.md"`, `_ASSETS`, intervals `(240,)`, `metric_keys=_B2_RERISK_KEYS` (D7), seeds `(42,)` — the draw's seed — and no rule, family or count: `--register` refuses it, its plain eval is admitted, and `--reading --iteration iter-186 --spec-hash <H>` keeps its run on `docs/reference/reading-ledger.jsonl`, spec 00141 D2's form. No incumbent; arm A and its full-long size are built in the run.
- **Author's call — the name `b2-rerisk-reading`**: spec 00141 D2's rule — a name opening with a registered or retired subject's name and a hyphen makes `tests/test_retired_subjects.py`'s case match count the live subject's cases as the other's, unmarked — so no registered or retired name may equal it or open it with a hyphen, and it may open none; the basis's third program measures both empty.
- **The instrument ruling's set**: `--dataset ohlc-full`, no `--window`, no `--as-of`; the union `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices, the trials' and readings 3's and 4's own. The full history, as readings 3 and 4 read it: every close at which a signal and a forward are read, from each signal's own first close.

## D3 — arm A, its full-long size and the state

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46 and 48–56 and readings 3–4 built it, by calling `_b2_overlay_inputs` itself (spec 00140 D3) with the threshold 2.0, so the union, its two window refusals and arm A are that function's, unchanged; its scales are computed and unused. **Author's call — the funding reader handed to it**, `_b2_funding_signal`, reading 3's own call: the funding z-score is one of the twelve signals (D4), so the reader the overlay is handed reads no set the reading would not, and the block is reading 3's (the basis).
- **The full-long size**, spec 00139 D3's, per asset and return index: `full_long_sizes(weights, levels, _ASSETS)`, `weights` being `_inverse_vol_weights(fed, lookback=180)` and `levels` the three arms' `vol_target_positions` from `a2_book_returns` over `fed = _ffill_btc(h4_prices)` with `_B2_A2_ARMS`' three configs — `_b2_reentry_inputs`' own calls; it is the position arm A holds where every arm's direction is long, so arm A never exceeds it (the basis: none above it).
- **Author's call — how the inputs reach the books**: `_b2_overlay_inputs` builds the three books and returns only arm A, their averaged asset positions, and no existing function changes (D7); so `_b2_full_long(h4_prices)`, new, rebuilds them over the union's prices `_b2_overlay_inputs` returns — the same prices and configs, so the same deterministic books — and takes their `vol_target_positions` for the size, at a measured 82 s of the inputs half's 352 s (the basis). Weighed: `_b2_reentry_inputs` itself, which keeps its books, but builds arm A by its own copy of the expression and an arm B from a fire rule and a hold no reading has, where arm A here is readings 3's and 4's `_b2_overlay_inputs` call; and `_b2_overlay_inputs` returning its books, a change to an existing function.
- **The state, one**: **below full-long**, per asset at return index `k` — the close at which the signal is read and at which arm A takes the position it holds over the next return — where arm A's position `p` and its full-long size `f` satisfy `0 < p < f − 1e-12`. **Author's call — the tolerance 1e-12**, the one spec 00139's basis compared arm A with its full-long size at: arm A equals its size only to rounding where every arm is long (the basis: within 1.110e-16 there, and at least 1.072e-03 below it elsewhere), so `p < f` with no tolerance would flag rounding as a state. The basis: 62,830 asset-stamps below the size, 30,632 at it, 179,908 flat.
- **Author's call — this state alone**: a re-risk raises arm A to its full-long size and acts only below it; at the size it changes nothing, and in the flat state it is a re-entry, which readings 3 and 4 read. In this state a negative difference names a de-risk (D8), the long state's de-risk read on the part of it below the size.
- **The flags**: `_b2_rerisk_flags(signal, arm_a, full_long, tail)`, new — `True`, an event, where the signal is past the tail and arm A is below its full-long size; `False`, another close, where the signal is read, not past that tail, and arm A is below the size; `None` elsewhere, the closes at the size and the flat ones among them. Reading 3's `_b2_reading_flags` is unchanged.

## D4 — the signals and the tails: the twelve readings 3 and 4 read, each by its reader, past ±2.0

- **The signals**, none new, each read by the function its reading reads it with, over the reading's union, keyed in this order, which the keys and the contrasts take:
  - reading 3's four (spec 00140 D4): `binperp_funding_z30d` — `_b2_funding_signal`, handed to `_b2_overlay_inputs` (D3); `binperp_oi_z30d` — `_b2_oi_signal`; `binperp_ratio_max_z30d` — `_b2_ratio_signal`; `binperp_liq_long_z30d` — `_b2_liq_signal`;
  - reading 4's eight (spec 00141 D4): `binperp_oi_log_delta_z30d` — `_b2_oi_log_delta_signal`; `binperp_oi_momentum_z30d` — `_b2_oi_momentum_signal`; `binperp_count_toptrader_long_short_ratio_z30d`, `binperp_sum_toptrader_long_short_ratio_z30d`, `binperp_count_long_short_ratio_z30d` and `binperp_sum_taker_long_short_vol_ratio_z30d` — `_b2_ratio_signals`; `binperp_liq_short_z30d` and `binperp_liq_total_z30d` — `_b2_liq_side_signals`.
- Each signal's span is its reading's (the basis).
- **The tails**, readings 3's and 4's: **above**, strictly above +2.0; **below**, strictly below −2.0, one threshold for every signal and both tails, `_B2_READING_THRESHOLD`. A signal read as `None` flags nothing.

## D5 — the forwards: reading 3's, unchanged

- Spec 00141 D5 whole, through `_b2_reading_forwards(h4_prices)` unchanged: at return index `k`, for each asset and H ∈ {1, 6, 24} closes, the log forward `log(close[k + H] / close[k])` on `_ffill_btc`'s prices, keyed `fwd_logret_4h`, `fwd_logret_24h` and `fwd_logret_96h`, and beside it the sum of `_b2_returns`' H returns from `k`, a missing return counted 0 and `None` exactly where the log forward is, keyed `fwd_sumret_4h`, `fwd_sumret_24h` and `fwd_sumret_96h` — what a unit held from a close for H closes is credited before cost. Leg 4 of the criterion (D8) reads the summed returns, legs 1–3 the log forward.

## D6 — the contrast: events against others below full-long, per asset and pooled, with reading 4's draw's bounds at this reading's Bonferroni percentiles

- **The cell**, per (signal, tail, H) in the one state: the flags `_b2_rerisk_flags(signal, arm_a, full_long, tail)`; per asset with at least two events and two others whose forward is read, and pooled over those assets, `[events, others, mean forward after the events, mean after the others, their difference, the difference's 2.5 % and 97.5 % bounds, its far low and far high bounds]`, one such row for each of D5's two families over the same assets, events and others — spec 00141 D6's row.
- **The far bounds are the Bonferroni percentiles**: 12 signals × 2 tails × 1 state × 3 horizons = 72 pooled cells, so 5 % two-sided over 72 cells puts the far bounds at the 2.5/72 % ≈ 0.0347 % and 100 − 2.5/72 % ≈ 99.9653 % percentiles, `_B2_RERISK_FAR`, where reading 4's 2.5/96 % and 100 − 2.5/96 % were its 96 cells'.
- **The draw**, one for every cell: `stationary_bootstrap_blocks(27_337, mean_block=102, n_resamples=40_000, seed=42)` (spec 00141 D6), reading 3's block for the 24-close forwards' overlap — the very resamples reading 4 drew, its arguments being reading 4's. Then per signal and tail one `event_contrast_blocks(flags, forwards, blocks, far=_B2_RERISK_FAR)` call over the six forward series, 24 calls; the rows' first five entries are `event_contrast_chunked`'s to the bit and the four bounds that contrast's to rounding (spec 00141's basis).
- **Author's call — 40,000 resamples, reading 4's draw**: numpy's percentile interpolates at index (N − 1) × q / 100 of the N usable resampled differences, sorted; at q = 2.5/72 and N = 40,000 that index is 39,999 × 2.5 / 7,200 = 13.8885, so the far low bound lies between the 14th and 15th smallest resampled differences and the far high bound, at 39,985.1115, between the 15th and 14th largest — at least thirteen resampled differences beyond each. 28,801 is the least count that puts the index at 10 or more; 40,000 keeps reading 4's draw whole, at the computes half's 176 s (the basis). A thin cell's pooled row may skip resamples holding no event, and its index falls with its usable count; the row records its events and others, never its usable count. The thin cells the basis names fall under D8's floor and are unread.

## D7 — the keys, the refusals and the build

- **The 79 keys** (`_B2_RERISK_KEYS`): per signal and horizon, `<signal key>_fwd_logret_<4·H>h` and `<signal key>_fwd_sumret_<4·H>h` — 72 keys, D5's two families — each `{"above": {"below_full": <rows>}, "below": {"below_full": <rows>}}`, the rows `{<asset>: <row>, …, "pooled": <row>}` over the kept assets and `{}` where a cell keeps none; `events_per_asset` and `others_per_asset`, each `{<signal key>: {<tail>: {"below_full": {<asset>: <count>}}}}`, the flags' counts before any forward is read (`_b2_rerisk_counts`, the basis's figures); and the constants `threshold` 2.0, `full_long_tolerance` 1e-12, `mean_block` 102, `n_resamples` 40000 and `far_percentiles` `[2.5 / 72, 100 − 2.5 / 72]`.
- **Author's call — the state level kept, `below_full`, and the tolerance recorded**: readings 3's and 4's rows sit under `{tail: {state: …}}`, so the line keeps that shape and names the state it reads, and the check programs read it as theirs; `full_long_tolerance` stands beside `threshold`, the state's bound as the threshold is the tails'.
- **Refusals**, reading 3's (spec 00140 D7): `--as-of`, before any read — "b2-rerisk-reading evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset"; a file of a signal's set it cannot read, by name, each reader's own (`derivatives-funding/<PERP>/funding.parquet: …` from the funding reader, `derivatives-oi/<PERP>/oi.parquet: …` from the OI, ratio, log-delta and momentum readers, `liquidations-daily/<COIN>/daily.parquet: …` from the long-side and side readers); `_b2_overlay_inputs`' two window refusals and any compute error, each a `SubjectError` naming the subject over its window. The plain eval is admitted.
- **The build in halves.** The inputs: `_b2_rerisk_inputs(subject, reader, dataset, window, accept_holes)` — `_b2_overlay_inputs` on `_b2_funding_signal` (D3), `_b2_full_long` over its prices, then the other seven readers over its union — returning `_B2ReriskInputs(h4_ts, h4_prices, close, arm_a, full_long, signals)`, new, no forward return. The computes: `_b2_rerisk_metrics(inputs)` — the forwards, the one draw, then per signal and tail the flags and one `event_contrast_blocks` call over the six forward series, the counts and the constants. `_build_b2_rerisk_reading` refuses `--as-of` and wraps both halves.
- **The files the build touches, a closed list**: `cli/research/subjects.py` — the constants `_B2_RERISK_STATE`, `_B2_RERISK_TOLERANCE`, `_B2_RERISK_SIGNALS` and `_B2_RERISK_FAR`, `_B2ReriskInputs`, `_b2_full_long`, `_b2_rerisk_inputs`, `_b2_rerisk_flags`, `_b2_rerisk_counts`, `_b2_rerisk_metrics`, `_build_b2_rerisk_reading`, `_B2_RERISK_KEYS` and one `SUBJECTS` entry, no import added; no existing function changed, readings 3's and 4's readers, `_b2_reading_forwards` and constants read as they are; `README.md`'s `--subject` row; the tests the plan names. No change to `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/validation/*`, `cli/engine/*`, `cli/liquidations/*`, specs 00128, 00131 and 00137–00141, the subjects of trials 1–7 and of readings 1–4, or any adopted artifact.

## D8 — the pre-registered potential criterion, the contamination, and what the reading changes

- **The criterion**, spec 00141 D8's floor and four legs, leg 1 at this reading's Bonferroni bounds and legs 3–4 in this state's actions, fixed by this spec's sha256 before any forward is read, read by the closeout's pick and never by code — the subject has no rule. **The floor, read before any leg**: a cell's log-forward rows hold at least 2 assets beside `pooled` — its kept assets (D7) — and its pooled row at least 100 events, the summed returns' rows holding the same assets and events (D6). A cell under the floor is **unread**, as is a cell with no row: no leg is read of it and it has no potential — by the basis's counts, before any forward is read, the six cells of the taker ratio's and the total's lower tails. A cell the floor admits has **potential** only if all four legs hold on its pooled rows, legs 1–3 on the log forward's and leg 4 on the summed returns' (D5):
  1. its far bounds — the 2.5/72 % and 100 − 2.5/72 % percentiles (D6) — exclude 0: Bonferroni over the 72 pooled cells, 12 signals × 2 tails × 1 state × 3 horizons, at 5 % two-sided. **Author's call — 72, though nine cells read no row and six fall under the floor** (the basis's empty and thin lower tails): the count is the design's, fixed before the run, and over the cells the floor admits — 57 at most — it is conservative;
  2. |difference| ≥ 0.012 at its horizon — one full-unit round trip at 0.006 per side, the cost the trials paid;
  3. its sign maps to an action in this state, every sign naming one: positive → a **re-risk**, arm A's position raised to its full-long size; negative → a **de-risk**, arm A's position cut;
  4. its summed returns' mean after the events, per unit of exposure added or removed, clears the same round trip in that action's direction — at least +0.012 for a re-risk, at most −0.012 for a de-risk: each unit the action adds at the event's close, or takes off, is credited or spared the H returns `net_of_cost` multiplies it by (D5) and pays 0.006 a side, whatever the gap between arm A and its full-long size, so the leg reads the summed returns' mean itself, never scaled by that gap.
- **The floor, carried from spec 00141 D8 unchanged**: 2 kept assets and 100 events, a far bound off a few events being no Bonferroni guard; here 100 parts the basis's pairs where their counts part — the thin two hold 11 and 6 events, every other 578 or more — so the floor, read off the counts alone before any forward is read, leaves those two lower tails unread.
- **A cell with potential names the trial a later spec would pre-register**: that action on that signal past that tail, at the closes where arm A is long below its full-long size, held H closes — a re-risk raising arm A to that size, or a de-risk cutting it. Where the signal is a part of a trialled one — a single ratio of trial 4's maximum, the total holding trial 5's long side — or the action on a trialled signal's family is a rejected trial's (the de-risks, trials 2–5), the later spec states how its signal, state, hold or size differs and cites the record. **None with potential** is the evidence the owner's family call — hold or close B2 — reads, beside readings 3's and 4's and trials 2–7's; the reading closes nothing (D1).
- **The contamination, in full**: the reading reads the trials' own instrument — the frozen union, arm A and the signals six landed records and readings 3 and 4 read — and its rows are the data any trial it justifies would be judged on. It was designed with readings 3's and 4's results known: no cell of either had potential, and this reading's state was chosen because both readings' nearest cells were re-risks at 96 hours with arm A long. Its twelve signals are theirs, its events the part of their long-state events below the full-long size and its others the same part of their others, so its cells are no independent look. The correction is over this reading's 72 cells: across the three readings' 216 — 48, 96 and 72 — the far bounds would lie at the 2.5/216 % percentiles, which this reading does not compute, so a cell meeting leg 1 here is read with that stated. A trial it justifies is designed from that data; its spec says so, carries all three readings' ids beside its own figures, and its DSR counts the family's true trials — B2's landed records and the one it adds, the three readings' looks included in its design.
- **What it changes**: no verdict of trials 2–7, no finding of readings 3 and 4, no B slot, no record; its figures go to T0023's findings beside its decisions-log entry, and B2's next step after it — the pick reading this criterion — is T0023's trigger.

## D9 — the run

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00142-b2-rerisk-reading-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` — before the append; (3) the data-gated basis test on the run's tree; (4) the one run, `uv run zcrypto research eval --subject b2-rerisk-reading --dataset ohlc-full --reading --iteration iter-186 --spec-hash <(1)> --notes "<written before the run>"`, no plain eval before or after it; (5) the ledger line's checks, its replay and its commit with the decisions-log entry naming `(reading <N>)`.
- **The hash rule**: before (1), nobody computes a forward return over the real data or runs `b2-rerisk-reading` over the real sets; the basis and the data-gated test hold positions, the full-long size, signals, counts and the block only.
- **The notes, written before the run**: the subject over `ohlc-full`, full history; that it is descriptive, with no bar, verdict or slot, changing no verdict of trials 2–7 nor readings 3's and 4's findings; the twelve signals, each by its reader; the state, the tails and the forwards; the contrast, its one draw and its bounds; the potential criterion pre-registered by this spec's sha256.
- A refused build keeps no reading; T0023 records it with its line quoted, and the reading's design stands unrun.

## Out of scope

Any trial — a re-risk, a de-risk, a re-entry or any other — and any threshold, signal, state split or horizon other than D3–D5's; the closes at the full-long size read on their own, and the flat state read again; a rule over the reading's figures; a correction computed over the three readings' cells; a reading on any instrument but frozen `ohlc-full`, on the 1-minute tape, or at a later as-of; a live liquidation, OI or funding feed; Bucket B's other families (B3, B4-legs), T0016's; any change to an existing function, subject, record or reading.
