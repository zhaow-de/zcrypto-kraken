# B2's second signal reading — the eight untested crowding signals' forward returns, by tail and by arm A's state, on the frozen `ohlc-full` set

**Ruling:** the owner, attended, 2026-10-22, verbatim: "go with the second reading on the untested signals" — the answer to the controller's account of B2's untried candidates after reading 3 found no cell with potential (`[iter-184] B2's four crowding signals read for forward returns by tail and by arm A's state on frozen ohlc-full (reading 3)`), recorded as `[iter-185] B2's next step after the signal reading` in `docs/research/10.phase4-decisions.md` (D1), the entry T0023's trigger greps for. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)". Iteration `iter-185`, branch `research/iter-185-b2-signal-reading-2`, topic T0023 under T0016. Spec 00140 is this spec's precedent and its form: its D3–D6 and D8 are carried here, each change named where it is made.

## The measured basis

Every figure below was measured on 2026-10-22 in this branch's worktree at develop's `3bb3dce68` — the first program between 20:41Z and 20:44Z, after the subject took its name (D2), the other two between 19:52Z and 20:01Z on the same code under the earlier name, which neither reads — with `data/ohlc-full`, `data/derivatives-oi` and `data/liquidations-daily` symlinked read-only from the main checkout's `data/` (and `data/derivatives-funding`, linked and unread), the code of plan 00141's Tasks 1–2 in the working tree: positions, signals, counts and the datasets block over the real sets, and the contrast and the computes half over synthetic inputs only — no forward return at any stamp was computed over the real data.

**The inputs**, a first program from the worktree root, reading the eight signals and arm A through the reading's own inputs half (`_b2_reading_2_inputs`, D3–D4) and counting each cell's events and others with reading 3's `_b2_reading_counts` (D7):

```python
import resource
import time
from pathlib import Path

from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

start = time.perf_counter()
reader = ObservedReader(Path("data"))
inputs = subjects._b2_reading_2_inputs("b2-second-signal-reading", reader, "ohlc-full", None, False)
close, arm_a, n, assets = inputs.close, inputs.arm_a, len(inputs.close), subjects._ASSETS
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"inputs read in {time.perf_counter() - start:.0f} s, peak RSS {peak / 1024:.0f} MiB; closes {n}")
block = reader.block()
print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in sorted(block.items())})
print("vouched", reader.vouched_status())
fed = subjects._ffill_btc(inputs.h4_prices)
for key, signal in inputs.signals.items():
    every = next(k for k in range(n) if all(signal[a][k] is not None for a in assets))
    firsts = [next(k for k in range(n) if signal[a][k] is not None) for a in assets]
    held = [sum(z is not None for z in signal[a]) for a in assets]
    priceless = sum(z is not None and fed[a][k] is None for a in assets for k, z in enumerate(signal[a]))
    print(f"{key}: every asset's from index {every} ({close[every]}); each asset's from {firsts}; held per asset {held}; held where the close is missing {priceless}")
print("arm A long", [sum(p > 0 for p in arm_a[a]) for a in assets], "flat", [sum(p == 0 for p in arm_a[a]) for a in assets])
counts = subjects._b2_reading_counts(inputs)
for key in inputs.signals:
    for tail in subjects._B2_READING_TAILS:
        for state in subjects._B2_READING_STATES:
            e = [counts["events_per_asset"][key][tail][state][a] for a in assets]
            o = [counts["others_per_asset"][key][tail][state][a] for a in assets]
            able = sum(x >= 2 and y >= 2 for x, y in zip(e, o))
            print(f"{key} {tail} {state}: events {sum(e)} {e}; others {sum(o)} {o}; assets with two of each {able}")
```

Its output, whole, each list in `_ASSETS`' order (ADA, AVAX, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP):

```text
inputs read in 178 s, peak RSS 419 MiB; closes 27337
block bfbaff14b7aaa0d673fb0ab2012fc0d5c2d2118d258ad720e9ef6120c6ca8f6a {'derivatives-oi': (10, 5010882, ['2020-09-01 00:00:00+00:00', '2026-07-22 23:55:00+00:00']), 'liquidations-daily': (10, 15048, ['2022-08-25 00:00:00+00:00', '2026-10-20 00:00:00+00:00']), 'ohlc-full': (10, 173373, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)', 'derivatives-oi': 'checked (10 vouched hashes)', 'liquidations-daily': 'checked (10 vouched hashes)'}
binperp_oi_log_delta_z30d: every asset's from index 18027 (2021-12-31 00:00:00+00:00); each asset's from [18027, 18027, 15291, 18027, 18027, 18027, 18027, 18027, 18027, 18027]; held per asset [8579, 8765, 11119, 8765, 8765, 8584, 8765, 8565, 8578, 8584]; held where the close is missing 9
binperp_oi_momentum_z30d: every asset's from index 18206 (2022-01-29 20:00:00+00:00); each asset's from [18206, 18206, 15470, 18206, 18206, 18206, 18206, 18206, 18206, 18206]; held per asset [7685, 8050, 10046, 8050, 8050, 7690, 8050, 7671, 7684, 7690]; held where the close is missing 1
binperp_count_toptrader_long_short_ratio_z30d: every asset's from index 20298 (2023-01-13 12:00:00+00:00); each asset's from [20298, 20298, 15290, 20298, 20298, 20298, 20298, 20298, 20298, 20298]; held per asset [6319, 6319, 8874, 6319, 6319, 6139, 6319, 6319, 6319, 6319]; held where the close is missing 9
binperp_sum_toptrader_long_short_ratio_z30d: every asset's from index 20298 (2023-01-13 12:00:00+00:00); each asset's from [20298, 20298, 15290, 20298, 20298, 20298, 20298, 20298, 20298, 20298]; held per asset [6499, 6499, 9054, 6499, 6499, 6499, 6499, 6499, 6499, 6499]; held where the close is missing 9
binperp_count_long_short_ratio_z30d: every asset's from index 18324 (2022-02-18 12:00:00+00:00); each asset's from [18324, 18324, 15290, 18324, 18324, 18324, 18324, 18324, 18324, 18324]; held per asset [8653, 8653, 11208, 8653, 8653, 8473, 8653, 8653, 8653, 8653]; held where the close is missing 9
binperp_sum_taker_long_short_vol_ratio_z30d: every asset's from index 18994 (2022-06-10 04:00:00+00:00); each asset's from [18994, 18994, 15290, 18994, 18994, 18994, 18994, 18994, 18994, 18994]; held per asset [7983, 7983, 10718, 7983, 7803, 8163, 8163, 8163, 8163, 8163]; held where the close is missing 9
binperp_liq_short_z30d: every asset's from index 19731 (2022-10-11 00:00:00+00:00); each asset's from [19725, 19635, 19731, 19725, 19629, 19731, 19725, 19713, 19719, 19731]; held per asset [7612, 7438, 7606, 7612, 7708, 7606, 7612, 7444, 7618, 7606]; held where the close is missing 9
binperp_liq_total_z30d: every asset's from index 19731 (2022-10-11 00:00:00+00:00); each asset's from [19725, 19635, 19731, 19725, 19629, 19731, 19725, 19713, 19719, 19731]; held per asset [7612, 7438, 7606, 7612, 7708, 7606, 7612, 7444, 7618, 7606]; held where the close is missing 9
arm A long [8938, 4680, 17169, 6766, 6640, 13428, 7954, 11958, 6024, 9905] flat [18399, 22657, 10168, 20571, 20697, 13909, 19383, 15379, 21313, 17432]
binperp_oi_log_delta_z30d above long: events 1436 [135, 149, 168, 170, 105, 129, 170, 147, 138, 125]; others 44308 [3814, 4063, 6306, 4376, 4080, 4359, 4447, 4431, 4489, 3943]; assets with two of each 10
binperp_oi_log_delta_z30d above flat: events 1020 [118, 116, 104, 90, 131, 97, 91, 83, 112, 78]; others 42305 [4512, 4437, 4541, 4129, 4449, 3999, 4057, 3904, 3839, 4438]; assets with two of each 10
binperp_oi_log_delta_z30d below long: events 1070 [97, 101, 182, 95, 100, 107, 103, 82, 108, 95]; others 44674 [3852, 4111, 6292, 4451, 4085, 4381, 4514, 4496, 4519, 3973]; assets with two of each 10
binperp_oi_log_delta_z30d below flat: events 941 [104, 82, 116, 83, 86, 112, 90, 85, 84, 99]; others 42384 [4526, 4471, 4529, 4136, 4494, 3984, 4058, 3902, 3867, 4417]; assets with two of each 10
binperp_oi_momentum_z30d above long: events 4074 [369, 316, 496, 620, 307, 280, 515, 441, 274, 456]; others 37988 [3314, 3691, 5266, 3482, 3488, 3841, 3815, 3790, 3911, 3390]; assets with two of each 10
binperp_oi_momentum_z30d above flat: events 3147 [324, 347, 242, 347, 457, 307, 256, 197, 386, 284]; others 35457 [3678, 3696, 4042, 3601, 3798, 3262, 3464, 3243, 3113, 3560]; assets with two of each 10
binperp_oi_momentum_z30d below long: events 1419 [143, 97, 243, 63, 197, 152, 123, 94, 172, 135]; others 40643 [3540, 3910, 5519, 4039, 3598, 3969, 4207, 4137, 4013, 3711]; assets with two of each 10
binperp_oi_momentum_z30d below flat: events 2305 [254, 243, 259, 238, 173, 310, 199, 209, 149, 271]; others 36299 [3748, 3800, 4025, 3710, 4082, 3259, 3521, 3231, 3350, 3573]; assets with two of each 10
binperp_count_toptrader_long_short_ratio_z30d above long: events 2447 [289, 316, 398, 217, 286, 113, 271, 236, 194, 127]; others 32860 [2796, 2937, 5104, 3020, 2943, 3138, 3162, 3214, 3470, 3076]; assets with two of each 10
binperp_count_toptrader_long_short_ratio_z30d above flat: events 1246 [73, 77, 297, 80, 60, 204, 52, 170, 94, 139]; others 29012 [3161, 2989, 3075, 3002, 3030, 2684, 2834, 2699, 2561, 2977]; assets with two of each 10
binperp_count_toptrader_long_short_ratio_z30d below long: events 1258 [96, 77, 127, 105, 66, 124, 130, 131, 249, 153]; others 34049 [2989, 3176, 5375, 3132, 3163, 3127, 3303, 3319, 3415, 3050]; assets with two of each 10
binperp_count_toptrader_long_short_ratio_z30d below flat: events 719 [93, 83, 30, 93, 81, 20, 132, 29, 62, 96]; others 29539 [3141, 2983, 3342, 2989, 3009, 2868, 2754, 2840, 2593, 3020]; assets with two of each 10
binperp_sum_toptrader_long_short_ratio_z30d above long: events 5054 [504, 503, 457, 525, 569, 362, 594, 516, 507, 517]; others 32163 [2705, 2884, 5228, 2925, 2814, 3254, 3070, 3162, 3298, 2823]; assets with two of each 10
binperp_sum_toptrader_long_short_ratio_z30d above flat: events 859 [82, 99, 98, 63, 57, 147, 78, 120, 28, 87]; others 29469 [3208, 3013, 3271, 2986, 3059, 2736, 2757, 2701, 2666, 3072]; assets with two of each 10
binperp_sum_toptrader_long_short_ratio_z30d below long: events 710 [32, 30, 195, 27, 92, 107, 56, 63, 85, 23]; others 36507 [3177, 3357, 5490, 3423, 3291, 3509, 3608, 3615, 3720, 3317]; assets with two of each 10
binperp_sum_toptrader_long_short_ratio_z30d below flat: events 2007 [241, 149, 172, 206, 155, 213, 252, 221, 207, 191]; others 28321 [3049, 2963, 3197, 2843, 2961, 2670, 2583, 2600, 2487, 2968]; assets with two of each 10
binperp_count_long_short_ratio_z30d above long: events 2572 [272, 340, 420, 247, 240, 168, 252, 218, 244, 171]; others 43902 [3741, 3906, 6257, 4294, 3959, 4288, 4310, 4473, 4552, 4122]; assets with two of each 10
binperp_count_long_short_ratio_z30d above flat: events 1776 [127, 128, 359, 84, 177, 228, 119, 198, 135, 221]; others 40655 [4513, 4279, 4172, 4028, 4277, 3789, 3972, 3764, 3722, 4139]; assets with two of each 10
binperp_count_long_short_ratio_z30d below long: events 1942 [206, 184, 101, 215, 166, 132, 232, 225, 203, 278]; others 44532 [3807, 4062, 6576, 4326, 4033, 4324, 4330, 4466, 4593, 4015]; assets with two of each 10
binperp_count_long_short_ratio_z30d below flat: events 978 [134, 144, 23, 86, 125, 29, 192, 33, 120, 92]; others 41453 [4506, 4263, 4508, 4026, 4329, 3988, 3899, 3929, 3737, 4268]; assets with two of each 10
binperp_sum_taker_long_short_vol_ratio_z30d above long: events 1797 [129, 152, 278, 158, 149, 177, 175, 201, 223, 155]; others 43372 [3641, 3974, 6249, 4142, 3769, 4354, 4343, 4421, 4495, 3984]; assets with two of each 10
binperp_sum_taker_long_short_vol_ratio_z30d above flat: events 1819 [233, 167, 180, 175, 214, 170, 196, 152, 138, 194]; others 36297 [3980, 3690, 4011, 3508, 3671, 3462, 3449, 3389, 3307, 3830]; assets with two of each 10
binperp_sum_taker_long_short_vol_ratio_z30d below long: events 20 [0, 6, 1, 2, 1, 1, 4, 0, 4, 1]; others 45149 [3770, 4120, 6526, 4298, 3917, 4530, 4514, 4622, 4714, 4138]; assets with two of each 4
binperp_sum_taker_long_short_vol_ratio_z30d below flat: events 21 [2, 3, 4, 0, 1, 3, 1, 0, 5, 2]; others 38095 [4211, 3854, 4187, 3683, 3884, 3629, 3644, 3541, 3440, 4022]; assets with two of each 6
binperp_liq_short_z30d above long: events 3263 [321, 341, 318, 348, 320, 275, 381, 366, 312, 281]; others 38069 [3465, 3543, 4270, 3828, 3692, 3984, 3811, 3835, 4079, 3562]; assets with two of each 10
binperp_liq_short_z30d above flat: events 1314 [134, 139, 120, 138, 142, 187, 111, 102, 132, 109]; others 33216 [3692, 3415, 2898, 3298, 3554, 3160, 3309, 3141, 3095, 3654]; assets with two of each 10
binperp_liq_short_z30d below long: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 41332 [3786, 3884, 4588, 4176, 4012, 4259, 4192, 4201, 4391, 3843]; assets with two of each 0
binperp_liq_short_z30d below flat: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 34530 [3826, 3554, 3018, 3436, 3696, 3347, 3420, 3243, 3227, 3763]; assets with two of each 0
binperp_liq_total_z30d above long: events 2723 [249, 259, 238, 383, 250, 220, 267, 267, 305, 285]; others 38609 [3537, 3625, 4350, 3793, 3762, 4039, 3925, 3934, 4086, 3558]; assets with two of each 10
binperp_liq_total_z30d above flat: events 1607 [128, 154, 145, 162, 229, 194, 122, 152, 180, 141]; others 32923 [3698, 3400, 2873, 3274, 3467, 3153, 3298, 3091, 3047, 3622]; assets with two of each 10
binperp_liq_total_z30d below long: events 6 [0, 0, 0, 0, 0, 6, 0, 0, 0, 0]; others 41326 [3786, 3884, 4588, 4176, 4012, 4253, 4192, 4201, 4391, 3843]; assets with two of each 1
binperp_liq_total_z30d below flat: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 34530 [3826, 3554, 3018, 3436, 3696, 3347, 3420, 3243, 3227, 3763]; assets with two of each 0
```

What it establishes:

- **The block is three sets' files**: `ohlc-full`'s ten 4h files beside the ten files of `derivatives-oi` and `liquidations-daily`, `compute_hash` `bfbaff14b7aaa0d673fb0ab2012fc0d5c2d2118d258ad720e9ef6120c6ca8f6a`, every set `checked` against its vouched hashes; each set is one reading 3's block already cites (`ad140b62…cf8eee1`, spec 00140's basis), so each is on the hub's `hot/` and the reading needs no push. `derivatives-funding` is not read: no signal of this reading comes from it, and arm A is built from `ohlc-full` alone (D3).
- **Each signal's span**: the OI log-delta's z-score is held on every asset from index 18,027 (2021-12-31 00:00), one close after reading 3's OI z-score (18,026, spec 00140's basis), the log-delta taking one mark before its window; the OI momentum's from 18,206 (2022-01-29 20:00), 179 closes later, the 180-mark lookback before its window; the two toptrader ratios' from 20,298 (2023-01-13 12:00), the ratios' maximum's own start, the pair dark through 2022; `count_long_short_ratio`'s from 18,324 (2022-02-18 12:00) and `sum_taker_long_short_vol_ratio`'s from 18,994 (2022-06-10 04:00), each held where its own column is; the short side's and the total's from 19,731 (2022-10-11 00:00), the long side's start, on the long side's own days, the held counts per asset equal to reading 3's long side's. BTC's OI-file signals open years earlier (indices 15,290–15,470), its OI rows starting 2020-09-01.
- **Arm A's states are reading 3's**: 93,462 long asset-stamps and 179,908 flat, per asset the figures spec 00140's basis printed, though `_b2_overlay_inputs` is handed another signal's reader (D3).
- **The cells**: nine of the 96 read no row — the short side's lower tail in both states and the total's in the flat state, at all three horizons, holding no event: the z-score of a positive, right-skewed daily notional rarely reads below −2.0. Three cells hold few: the total's lower tail with arm A long, six events, all ETH's; the taker ratio's lower tail, 20 events with arm A long (four assets with two of each) and 21 flat (six). Every other cell holds two events and two others on all ten assets, from the summed toptrader ratio's lower tail with arm A long, 710 events, to its upper tail, 5,054. So 87 cells can read a pooled row, each where its events' forwards are read.
- **Held where the close is missing**: nine asset-stamps on every signal but the momentum's one, against the funding signal's 4,053 in reading 3; a flagged stamp there enters the counts (D7) and no row (D5).

**The contrast's memory and time** (D6), a second program from the worktree root, on synthetic inputs of the reading's size — 27,337 return indices, the ten assets, six forward series in D5's two families (the second family the first shifted by a constant, its `None`s the first's), about 3 % of the indices events and 52 % others — at `mean_block=102`, `seed=42`; its first argument picks the block contrast alone or beside `event_contrast_chunked` over the same resamples, its second the count of resamples:

```python
import random
import resource
import sys
import time

from cli.alpha.b2 import event_contrast_blocks, event_contrast_chunked, stationary_bootstrap_blocks
from cli.research.subjects import _ASSETS

mode, n_resamples = sys.argv[1], int(sys.argv[2])
rng = random.Random(42)
n = 27_337
flags = {a: [None if u < 0.45 else u > 0.97 for u in (rng.random() for _ in range(n))] for a in _ASSETS}
logret = {h: {a: [None if k + h >= n or rng.random() < 0.02 else rng.gauss(0, 0.02) for k in range(n)] for a in _ASSETS} for h in (1, 6, 24)}
forwards = {f"fwd_logret_{4 * h}h": logret[h] for h in (1, 6, 24)} | {
    f"fwd_sumret_{4 * h}h": {a: [None if v is None else v + 0.001 for v in logret[h][a]] for a in _ASSETS} for h in (1, 6, 24)
}
built = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
start = time.perf_counter()
blocks = stationary_bootstrap_blocks(n, mean_block=102, n_resamples=n_resamples, seed=42)
drawn, after = time.perf_counter() - start, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
start = time.perf_counter()
out = event_contrast_blocks(flags, forwards, blocks, far=(0.05, 99.95))
cell, peak = time.perf_counter() - start, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(f"blocks {n_resamples}: draw {drawn:.1f} s, {len(blocks.starts)} blocks; one cell {cell:.1f} s; peak RSS {built:.0f} MiB with the inputs built, {after:.0f} after the draw, {peak:.0f} after the cell")
if mode == "compare":
    start = time.perf_counter()
    chunked = event_contrast_chunked(flags, forwards, mean_block=102, n_resamples=n_resamples, seed=42)
    print(f"chunked {n_resamples}: one cell {time.perf_counter() - start:.1f} s")
    same = {s: list(r) for s, r in out.items()} == {s: list(r) for s, r in chunked.items()}
    exact = all(out[s][k][:5] == chunked[s][k][:5] for s in out for k in out[s])
    worst = max(abs(a - b) / abs(b) for s in out for k in out[s] for a, b in zip(out[s][k][5:], chunked[s][k][5:]))
    print(f"rows {sum(map(len, out.values()))}, same names {same}, first five entries equal {exact}, worst relative difference of a bound {worst:.1e}")
```

Run as `blocks 40000` and `compare 2000`, one process each; their output, whole:

```text
blocks 40000: draw 25.2 s, 10756066 blocks; one cell 6.1 s; peak RSS 136 MiB with the inputs built, 262 after the draw, 365 after the cell
blocks 2000: draw 1.3 s, 536498 blocks; one cell 0.6 s; peak RSS 136 MiB with the inputs built, 144 after the draw, 215 after the cell
chunked 2000: one cell 17.6 s
rows 66, same names True, first five entries equal True, worst relative difference of a bound 1.3e-14
```

- At the reading's 40,000 resamples the draw is taken once in 25.2 s and holds 10,756,066 blocks, 126 MiB above the inputs, and a cell reads it in 6.1 s, 103 MiB above the draw.
- Over the same 2,000 resamples the block contrast keeps the chunked contrast's assets and series, its rows' first five entries to the bit and its four bounds within a relative 1.3e-14 of the chunked contrast's; the chunked contrast took 17.6 s a cell against the block contrast's 0.6 s.
- The chunked contrast at 40,000 resamples, extrapolated from that 17.6 s and never run: 352 s a cell, 11,264 s — about 3.1 hours — for the 32 contrasts the reading draws (D6), past the three hours after which `infra/scripts/data-gated-run.py` kills the nightly suite (its `--timeout` default, `3 * 3600` s, the unit passing none), a cut-off the reading's replay case (`tests/test_registry_replay.py`) would meet alone.

**The computes half**, a third program from the worktree root: the reading's whole compute — the forwards, the one draw, the 32 contrasts, the counts and the constants (`_b2_reading_2_metrics`, D7) — on synthetic inputs of its size: ten assets' prices over 27,338 closes, a random walk with asset i missing its first 1,000 × i closes; arm A long at about a third of the asset-stamps; eight signals drawn from a standard normal from index 18,000 on:

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
arm_a = {a: [0.1 if rng.random() < 0.34 else 0.0 for _ in range(n)] for a in assets}
signals = {key: {a: [None if k < 18_000 else rng.gauss(0, 1) for k in range(n)] for a in assets} for key in subjects._B2_READING_2_SIGNALS}
inputs = subjects._B2ReadingInputs([None] * (n + 1), prices, [None] * n, arm_a, signals)
built = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
start = time.perf_counter()
metrics = subjects._b2_reading_2_metrics(inputs)
elapsed, peak = time.perf_counter() - start, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
rows = sum(len(by_state) for key in metrics if "_fwd_" in key for by_tail in metrics[key].values() for by_state in by_tail.values())
print(f"computes half: {elapsed:.0f} s, peak RSS {peak:.0f} MiB, {built:.0f} MiB with the inputs built; {len(metrics)} keys, {rows} rows")
```

Its output, whole:

```text
computes half: 226 s, peak RSS 410 MiB, 123 MiB with the inputs built; 54 keys, 2112 rows
```

- The computes half takes 226 s and peaks 287 MiB above its inputs; with the inputs half's 178 s and 419 MiB (the first program), the reading's run is near 404 s, about seven minutes, against reading 3's seven and a half (spec 00140's basis).

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this reading runs under one, the session holding this branch's worktree, `.claude/worktrees/iter185`, on the workstation `zcrypto-ops`. No other session appends to `docs/reference/reading-ledger.jsonl` while this branch is open.
- **The process.** The reading is one `uv run zcrypto research eval` process in this worktree, awaited to its exit — no daemon, timer or concurrent run, and no step reads it as ended while its process lives. It reads `data/ohlc-full`, `data/derivatives-oi` and `data/liquidations-daily`, symlinks to the main checkout's sets, each frozen and attested; it writes nothing under them, makes no network call, and nothing it reads has a live writer.
- **No trial-attempts log.** A subject with no rule registers no trial: `--reading` begins no attempt and its line carries `attempt` `null`, as readings 2 and 3 do; the trial-attempts log and Bucket B's budget are untouched.
- **The reading ledger** — tracked, append-only, hash-chained; this worktree is its one writer while the branch is open. `--reading` refuses a tree with uncommitted changes, so the run's line is committed with its decisions-log entry before anything else lands (D9).

## The question (no hypothesis, no bar)

Reading 3 found no cell with potential among B2's four trialled signals. The crowding signals no trial read remain: the open interest's change and momentum where reading 3 read its level, each long/short ratio where it read their maximum, the short side and the total of the day's liquidations where it read the long side. This reading asks reading 3's question of them: **after a close at which a signal lies past ±2, and inside one state of arm A — long or flat — does the asset's forward log return differ from its forward return after the other closes at which the signal is read in that state?** A cell that clears the potential criterion (D8) names the trial it would justify; none clearing it is the evidence the owner's family call reads. The reading tests no hypothesis, has no bar, matrix or verdict, spends no B slot, and changes no verdict of trials 2–7 nor reading 3's finding.

## D1 — the pick: a second reading, over the signals reading 3 did not test

- **The owner's pick**, attended, among the controller's four:
  1. **Variants of the trials already run** — a de-risk at another scale or threshold, the re-entries' park variants, a re-risk; reading 3 mostly answers them, no tail of the four trialled signals in either of arm A's states showing a forward difference its pre-registered bounds separate from 0.
  2. **Different signals reading 3 did not test** — the OI log-delta or momentum in place of the OI z-score, a single long/short ratio in place of the four ratios' maximum, another liquidation side or the total — screened first by a second no-slot reading. Chosen: "go with the second reading on the untested signals".
  3. **The 1-minute tape** — a different instrument, whose window no frozen set reaches (spec 00138 D12).
  4. **Close B2** for B3 or B4-legs, T0016's next families.
- The reading closes nothing: whatever it reads, B2 stays open, and a close is the owner's (D8).

## D2 — the instrument and the subject: frozen `ohlc-full`, full history, a reading

- **One reading subject**, `b2-second-signal-reading` in `cli/research/subjects.py`: `spec="docs/specs/00141-b2-signal-reading-2-design.md"`, `_ASSETS`, intervals `(240,)`, `metric_keys=_B2_READING_2_KEYS` (D7), seeds `(42,)` — the draw's seed — and no rule, family or count: `--register` refuses it, its plain eval is admitted, and `--reading --iteration iter-185 --spec-hash <H>` keeps its run on `docs/reference/reading-ledger.jsonl`, spec 00140 D2's form. No incumbent; arm A is built in the run.
- **Author's call — the name `b2-second-signal-reading`**, not `b2-signal-reading-2`: a name opening with the retired `b2-signal-reading` and a hyphen makes `tests/test_retired_subjects.py`'s case match — a case id whose parameter equals a retired name or opens with it and a hyphen — count the live subject's cases as the retired one's, unmarked, and `test_a_retired_subjects_cases_are_marked_and_deselected_under_not_retired` fails — measured on the authoring tree under that name, where the subject module's other direct test readers ran `1 failed, 4113 passed, 56 deselected`, that case the one failure; no registered name opens this one, and it opens no other.
- **The instrument ruling's set**: `--dataset ohlc-full`, no `--window`, no `--as-of`; the union `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices, the trials' and reading 3's own. The full history, as reading 3 reads it (spec 00140 D2): every close at which a signal and a forward are read, from each signal's own first close; no signal here holds a close before 2021 but BTC's, whose OI file opens 2020-09-01.

## D3 — arm A's state at the signal's close

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46 and 48–56 and reading 3 built it, by calling `_b2_overlay_inputs` itself (spec 00140 D3), with the threshold 2.0, so the union, its two window refusals and arm A are that function's, unchanged; its scales are computed and unused.
- **Author's call — the OI log-delta's reader handed to `_b2_overlay_inputs`**, `_b2_oi_log_delta_signal` (D4), in place of reading 3's `_b2_funding_signal`: arm A's expression reads the union's prices alone, never the signal, so its positions are reading 3's (the basis: the same long and flat counts per asset), and the funding reader would read into the block a set no signal of this reading comes from. The first of the eight signals is the overlay's `signal`, as the funding z-score was reading 3's.
- **The states**, per asset at return index `k`: **long** where arm A's position is above 0, **flat** where it is 0 — spec 00140 D3's, reading 3's 93,462 long and 179,908 flat asset-stamps.

## D4 — the signals and the tails: the eight no trial read, each standardized as the trialled ones are, past ±2.0

- **Standardized as the trialled signals are**: each signal is a trailing 30-day z-score on its native grid — the 180-mark z-score on the OI file's regular 4h grid (`_oi_marks`) that trial 3's OI z-score is, read at the union's closes by exact lookup, or the 30-day z-score of a daily series that trial 5's liquidation z-score is, a day read from the first close at or after its end — so ±2.0 means here what it meant in reading 3.
- **The signals**, keyed in this order, which the keys and the contrasts take:
  - `binperp_oi_log_delta_z30d` — `_b2_oi_log_delta_signal(reader, h4_ts)`, new: per perp `oi_log_delta_zscore_grid_feature` over `derivatives-oi/<PERP>/oi.parquet`'s `sum_open_interest`, new in `cli/alpha/b2.py`: through `_oi_at_union_closes`, the pipeline of trial 3's `oi_zscore_grid_feature`, the 4h log-delta `oi_log_delta` of the grid level and its trailing z-score over `_OI_ZSCORE_WINDOW`, 180 marks, both on the grid and never at the union's closes.
  - `binperp_oi_momentum_z30d` — `_b2_oi_momentum_signal(reader, h4_ts)`, new: `oi_momentum_zscore_grid_feature`, new, the same pipeline over `oi_momentum` at spec 00131's 180-mark lookback, `_OI_MOMENTUM_LOOKBACK`, the 30-day change in the level, then its 180-mark z-score.
  - `binperp_count_toptrader_long_short_ratio_z30d`, `binperp_sum_toptrader_long_short_ratio_z30d`, `binperp_count_long_short_ratio_z30d`, `binperp_sum_taker_long_short_vol_ratio_z30d` — `_b2_ratio_signals(reader, h4_ts)`, new: per perp trial 4's own `ratio_zscore_grid_features` over the same file's four ratio columns (`_B2_RATIO_COLUMNS`), each z-score a signal of its own under the name that function gives it, where trial 4 and reading 3 read only their maximum and only where all four are read.
  - `binperp_liq_short_z30d`, `binperp_liq_total_z30d` — `_b2_liq_side_signals(reader, h4_ts)`, new: per coin `daily_zscore_grid_feature` — trial 5's — over `liquidations-daily/<COIN>/daily.parquet`'s `short_usd`, and over each day's `long_usd + short_usd`; the backfill refuses a non-finite or negative leg (`cli/liquidations/coinalyze.py`), so the day's total is the plain sum.
- **Author's call — the OI change and momentum z-scored through `funding_zscore`**: `oi_zscore` refuses a value at or below zero (`_validate_levels`), and a log-delta or a momentum is signed; `funding_zscore` is the same trailing sample-standard-deviation z-score, `None` until its window is full and wherever the window holds a `None`, a flat window scoring 0.0 — the one trial 4's ratios are z-scored with — at the OI z-score's window. Its coverage is the basis's: from 2021-12-31 00:00 and 2022-01-29 20:00 on every asset.
- **Author's call — the four ratios each on its own coverage**: each is read where its own column is, so `count_long_short_ratio` and `sum_taker_long_short_vol_ratio` open in 2022, months before the toptrader pair (the basis), where a single ratio read only where all four are would be the maximum's window under another name.
- **The tails**, reading 3's (spec 00140 D4): **above**, strictly above +2.0; **below**, strictly below −2.0, one threshold for every signal and both tails, through reading 3's `_b2_reading_flags` unchanged. A signal read as `None` flags nothing.

## D5 — the forwards: reading 3's, unchanged

- Spec 00140 D5 whole, through `_b2_reading_forwards(h4_prices)` unchanged: at return index `k`, for each asset and H ∈ {1, 6, 24} closes, the log forward `log(close[k + H] / close[k])` on `_ffill_btc`'s prices, keyed `fwd_logret_4h`, `fwd_logret_24h` and `fwd_logret_96h`, and beside it the sum of `_b2_returns`' H returns from `k`, a missing return counted 0 and `None` exactly where the log forward is, keyed `fwd_sumret_4h`, `fwd_sumret_24h` and `fwd_sumret_96h` — what a unit held from a close for H closes is credited before cost. Leg 4 of the criterion (D8) reads the summed returns, legs 1–3 the log forward.

## D6 — the contrast: events against others in one state, per asset and pooled, with one draw's bounds at the Bonferroni percentiles

- **The cell**, spec 00140 D6's, per (signal, tail, state, H): the flags `_b2_reading_flags(signal, arm_a, tail, state)`; per asset with at least two events and two others whose forward is read, and pooled over those assets, `[events, others, mean forward after the events, mean after the others, their difference, the difference's 2.5 % and 97.5 % bounds, its far low and far high bounds]`, one such row for each of D5's two families over the same assets, events and others.
- **The far bounds are the Bonferroni percentiles**: 8 signals × 2 tails × 2 states × 3 horizons = 96 pooled cells, so 5 % two-sided over 96 cells puts the far bounds at the 2.5/96 % ≈ 0.026 % and 100 − 2.5/96 % ≈ 99.974 % percentiles, `_B2_READING_2_FAR`, where reading 3's 0.05 % and 99.95 % were its 48 cells'.
- **The draw**, one for every cell: the stationary bootstrap of the 27,337 return indices at `mean_block=102`, reading 3's block for the 24-close forwards' overlap (spec 00140 D6), `seed=42`, **40,000 resamples**. `stationary_bootstrap_blocks(n_obs, *, mean_block, n_resamples, seed)`, new in `cli/alpha/b2.py`, draws it once: it replays `stationary_bootstrap_indices`' generator — `random.Random(seed)`, the same calls in the same order — and holds each resample as its blocks, a block opened at each fresh start and lengthened by each step to the next index mod `n_obs`, four bytes an entry (`BootstrapBlocks`: `starts`, `lengths`, `firsts`); its resamples, unrolled, are `stationary_bootstrap_indices`' own. It refuses what that function refuses, with its messages.
- **The block contrast.** `event_contrast_blocks(flags, forwards, blocks, *, far)`, new in `cli/alpha/b2.py`, computes each cell's rows from that draw: per resample, each kept asset's event and other counts and their forwards' sums are read off running totals at its blocks' ends — about 269 blocks a resample at block 102, never its 27,337 indices — and a resample holding no event or no other for a row is skipped for that row, `event_contrast_chunked`'s rule. The rows' first five entries are computed as `event_contrast_chunked` computes them, equal to the bit; the resampled counts are the gathered ones exactly, and the resampled sums equal the gathered ones to rounding, so the four bounds equal the chunked contrast's within a relative 1.3e-14 on synthetic inputs of the reading's size (the basis). It refuses a draw over another count of indices, `far` other than a tuple of two numbers 0 ≤ low < high ≤ 100, and what `event_contrast_chunked` refuses of the flags and forwards, with its messages.
- **Author's call — the block contrast in place of a bit-equal twin of `event_contrast_chunked` taking the far percentiles as an argument**: the twin at 40,000 resamples would take about 3.1 hours (the basis, extrapolated), past the nightly suite's three-hour cut-off, which the reading's replay case would reach alone; the block contrast's whole computes half takes 226 s. The price is the bounds' last bits: equal to the chunked contrast's to rounding, not to the bit, which no leg of the criterion (D8) reads.
- **Author's call — 40,000 resamples, so the far bounds are resolved**: numpy's percentile interpolates at index (N − 1) × q / 100 of the N usable resampled differences, sorted; at q = 2.5/96 and N = 40,000 that index is 39,999 × 2.5 / 9,600 = 10.4164, so the far low bound lies between the 11th and 12th smallest resampled differences and the far high bound, at 39,988.5836, between the 12th and 11th largest — at least ten resampled differences beyond each — where at 2,000 resamples the index is 0.5206, between the two most extreme, reading 3's coarse bounds. 38,401 is the least count that puts the index at 10 or more; 40,000 is the round count above it. A thin cell's pooled row (the basis: the total's lower tail with arm A long, ETH's six events) may skip resamples holding no event, and its index falls with its usable count; the row records its events and others, never its usable count.
- **The known-answer tests** (plan 00141 Task 1): the draw unrolled equal to `stationary_bootstrap_indices`' resamples over four draws — short blocks, every index a fresh start, one index, and long blocks wrapping past the last index; the block contrast's rows on spec 00140's three-series fixture equal to `event_contrast_chunked`'s at (0.05, 99.95), the first five entries to the bit and the bounds within a relative 1e-12 (an absolute 1e-15 near 0), and its far bounds at (1, 99) equal to the hand-resampled differences' percentiles.

## D7 — the keys, the refusals and the build

- **The 54 keys** (`_B2_READING_2_KEYS`): per signal and horizon, `<signal key>_fwd_logret_<4·H>h` and `<signal key>_fwd_sumret_<4·H>h` — 48 keys, D5's two families — each `{"above": {"long": <rows>, "flat": <rows>}, "below": {...}}`, the rows `{<asset>: <row>, …, "pooled": <row>}` over the kept assets and `{}` where a cell keeps none; `events_per_asset` and `others_per_asset`, each `{<signal key>: {<tail>: {<state>: {<asset>: <count>}}}}`, the flags' counts before any forward is read (`_b2_reading_counts`, the basis's figures); and the constants `threshold` 2.0, `mean_block` 102, `n_resamples` 40000 and `far_percentiles` `[2.5 / 96, 100 − 2.5 / 96]`.
- **Refusals**, reading 3's (spec 00140 D7): `--as-of`, before any read — "b2-second-signal-reading evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset"; a file of a signal's set it cannot read, by name, each reader's own (`derivatives-oi/<PERP>/oi.parquet: …` from the OI log-delta, OI momentum or ratio reader, `liquidations-daily/<COIN>/daily.parquet: …` from the side reader); `_b2_overlay_inputs`' two window refusals and any compute error, each a `SubjectError` naming the subject over its window. The plain eval is admitted.
- **The build in halves.** The inputs: `_b2_reading_2_inputs(subject, reader, dataset, window, accept_holes)` — `_b2_overlay_inputs` on `_b2_oi_log_delta_signal` (D3), then the momentum, ratio and side readers over its union — returning reading 3's `_B2ReadingInputs(h4_ts, h4_prices, close, arm_a, signals)`, no forward return. The computes: `_b2_reading_2_metrics(inputs)` — the forwards, the one draw, then per signal, tail and state the flags and one `event_contrast_blocks` call over the six forward series, the counts and the constants. `_build_b2_second_signal_reading` refuses `--as-of` and wraps both halves.
- **The files the build touches, a closed list**: `cli/alpha/b2.py` — the imports `array` and `NamedTuple`, `oi_log_delta_zscore_grid_feature`, `oi_momentum_zscore_grid_feature`, `BootstrapBlocks`, `stationary_bootstrap_blocks` and `event_contrast_blocks`; `cli/research/subjects.py` — the imports of `event_contrast_blocks`, `oi_log_delta_zscore_grid_feature`, `oi_momentum_zscore_grid_feature` and `stationary_bootstrap_blocks`, the constants `_B2_READING_2_SIGNALS`, `_B2_READING_2_RESAMPLES` and `_B2_READING_2_FAR`, `_b2_oi_log_delta_signal`, `_b2_oi_momentum_signal`, `_b2_ratio_signals`, `_b2_liq_side_signals`, `_b2_reading_2_inputs`, `_b2_reading_2_metrics`, `_build_b2_second_signal_reading`, `_B2_READING_2_KEYS` and one `SUBJECTS` entry; no existing function of either file changed, reading 3's `_B2ReadingInputs`, `_b2_reading_flags`, `_b2_reading_counts`, `_b2_reading_forwards` and its constants read as they are; `README.md`'s `--subject` row; the tests the plan names. No change to `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/validation/*`, `cli/engine/*`, `cli/liquidations/*`, specs 00128, 00131 and 00137–00140, the subjects of trials 1–7 and of readings 1–3, or any adopted artifact.

## D8 — the pre-registered potential criterion, the contamination, and what the reading changes

- **The criterion**, spec 00140 D8's four legs in form, fixed by this spec's sha256 before any forward is read, read by the closeout's pick and never by code — the subject has no rule: a cell has **potential** only if all four hold on its pooled rows, legs 1–3 on the log forward's and leg 4 on the summed returns' (D5):
  1. its far bounds — the 2.5/96 % and 100 − 2.5/96 % percentiles (D6) — exclude 0: Bonferroni over the 96 pooled cells, 8 signals × 2 tails × 2 states × 3 horizons, at 5 % two-sided. **Author's call — 96, though nine cells read no row** (the basis's empty lower tails): the count is the design's, fixed before the run, and over the cells that read a row — 87 at most — it is conservative;
  2. |difference| ≥ 0.012 at its horizon — one full-unit round trip at 0.006 per side, the cost the trials paid;
  3. its sign maps to an action a long/flat book can take: positive in the flat state → a **re-entry**, positive in the long state → a **re-risk**, negative in the long state → a **de-risk**; a negative difference in the flat state names no action;
  4. its summed returns' mean after the events, in that action's direction, clears the same round trip — at least +0.012 for a re-entry or a re-risk, at most −0.012 for a de-risk.
- **A cell with potential names the trial a later spec would pre-register**: that action on that signal past that tail, in that state, held H closes. Where the signal is a part of a trialled one — a single ratio of trial 4's maximum, the total holding trial 5's long side — or the action on a trialled signal's family is a rejected trial's (trials 2–7), the later spec states how its signal, hold or size differs and cites the record. **None with potential** is the evidence the owner's family call — hold or close B2 — reads, beside reading 3's and trials 2–7's; the reading closes nothing (D1).
- **The contamination, plainly**: the reading reads the trials' own instrument — the frozen union and arm A that six landed records and reading 3 read — and its rows are the data any trial it justifies would be judged on. It was designed with reading 3's results known: no cell of the four trialled signals had potential, and this reading's signals were chosen after it, as the ones it did not test (D1), several drawn from the same series as reading 3's — the OI change and momentum from the OI level whose z-score it read, the single ratios the parts of its maximum, the total holding its long side. The correction is over this reading's 96 cells: across both readings' 144 the far bounds would lie at the 2.5/144 % percentiles, which this reading does not compute, so a cell meeting leg 1 here is read with that stated. A trial either reading justifies is designed from that data; its spec says so, carries both readings' ids beside its own figures, and its DSR counts the family's true trials — B2's landed records and the one it adds, both readings' looks included in its design.
- **What it changes**: no verdict of trials 2–7, no finding of reading 3, no B slot, no record; its figures go to T0023's findings beside its decisions-log entry, and B2's next step after it — the pick reading this criterion — is T0023's trigger.

## D9 — the run

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00141-b2-signal-reading-2-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` — before the append; (3) the data-gated basis test on the run's tree; (4) the one run, `uv run zcrypto research eval --subject b2-second-signal-reading --dataset ohlc-full --reading --iteration iter-185 --spec-hash <(1)> --notes "<written before the run>"`, no plain eval before or after it; (5) the ledger line's checks, its replay and its commit with the decisions-log entry naming `(reading <N>)`.
- **The hash rule**: before (1), nobody computes a forward return over the real data or runs `b2-second-signal-reading` over the real sets; the basis and the data-gated test hold positions, signals, counts and the block only.
- **The notes, written before the run**: the subject over `ohlc-full`, full history; that it is descriptive, with no bar, verdict or slot, changing no verdict of trials 2–7 nor reading 3's finding; the eight signals, each by its reader; the tails, the states and the forwards; the contrast, its one draw and its bounds; the potential criterion pre-registered by this spec's sha256.
- A refused build keeps no reading; T0023 records it with its line quoted, and the reading's design stands unrun.

## Out of scope

Any trial — a re-risk, a de-risk, a re-entry or any other — and any threshold, signal, state split or horizon other than D4–D5's; the signals reading 3 read, read again; a rule over the reading's figures; a correction computed over both readings' cells; the full-long split of the long state (spec 00140 D3); a reading on any instrument but frozen `ohlc-full`, on the 1-minute tape, or at a later as-of; a live liquidation, OI or funding feed; Bucket B's other families (B3, B4-legs), T0016's; any change to an existing function, subject, record or reading.
