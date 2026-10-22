# B2's signal reading — the four trialled 4h-grid crowding signals' forward returns, by tail and by arm A's state, on the frozen `ohlc-full` set

**Ruling:** the owner launched this unattended run, verbatim: "continue pushing the Research strates forward, pick the most relevant tasks. override the wall clock time gate, but do not pick up new topics after 8:00Z. when closing out a research step, try the trials with potential and do not close any family too early." B2's next step after trials 6–7 (T0023's trigger) is therefore the loop's pick, recorded as `[iter-184] B2's next step after trial 7` in `docs/research/10.phase4-decisions.md` (D1); master plan §12 lists no touchpoint for a family's next step, and `[iter-183] B2's next step after trial 5` is the precedent and its form. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" and head-to-head read "From-2021 primary (Recommended)". Iteration `iter-184`, branch `research/iter-184-b2-signal-reading`, topic T0023 under T0016.

## The measured basis

Every figure below but the six-series timing in the last bullet of the third program, which names its own run, was measured on 2026-10-22 between 08:03Z and 08:07Z in this branch's worktree at develop's `74e192562`, with `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily` symlinked read-only from the main checkout's `data/`, the code of plan 00140's Tasks 1–2 in the working tree: positions, signals, counts and the datasets block only — no forward return at any stamp was computed over the real data.

**The decomposition, derived from the records' stored keys** (the motivation of D1). Over the full window each record's `head_to_head_mean_outperf_full` is arm B's mean net-of-cost return less arm A's over the 27,337 return indices, so their summed difference, the net, is that mean × 27,337; `net_of_cost` charges `cost_per_side` × |Δposition| on every position change, so arm B's extra cost is (`turnover_b` − `turnover_a`) × 0.006, and its gross difference the net plus that cost. The program, `uv run python <it>` from the worktree root:

```python
import json

N = 27_337
COST = 0.006
for line in open("docs/reference/trial-registry.jsonl"):
    r = json.loads(line)
    if r["trial_id"] < 51:
        continue
    m = r["metrics"]
    net = m["head_to_head_mean_outperf_full"] * N
    extra = (m["turnover_b"] - m["turnover_a"]) * COST
    print(f"record {r['trial_id']} {r['invocation']['subject']}: net {net:+.3f}, extra cost {extra:.3f}, gross {net + extra:+.3f}")
```

Its output, whole:

```text
record 51 b2-funding-derisk-full: net -0.194, extra cost 0.148, gross -0.046
record 52 b2-oi-derisk: net -0.180, extra cost 0.087, gross -0.092
record 53 b2-ratio-derisk: net -0.264, extra cost 0.231, gross -0.033
record 54 b2-liq-derisk: net -0.062, extra cost 0.039, gross -0.023
record 55 b2-liq-reentry: net -0.054, extra cost 0.160, gross +0.107
record 56 b2-funding-reentry: net -0.364, extra cost 0.710, gross +0.346
```

- Every de-risk (records 51–54) lost gross return as well as net, and both re-entries (records 55–56) gained gross return and lost it, and more, to their extra trading. Those are the signs a positive drift in the assets alone would give: taking exposure off a rising asset loses gross return and putting it on gains it, whatever the signal. The records cannot tell drift from information in the signal; a forward-return contrast at the signals' own closes, inside one state of arm A, can (D6).
- Record 52's gross is −0.0925 unrounded (−0.1797 net, 0.0872 extra cost), printed −0.092; the sum of the rounded net and cost reads −0.093.

**The inputs**, a second program from the worktree root, reading the four signals and arm A through the reading's own inputs half (`_b2_reading_inputs`, D3–D4) and counting each cell's events and others (`_b2_reading_counts`, D7):

```python
from collections import Counter
from datetime import timedelta
from pathlib import Path

from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

reader = ObservedReader(Path("data"))
inputs = subjects._b2_reading_inputs("b2-signal-reading", reader, "ohlc-full", None, False)
close, arm_a, n, assets = inputs.close, inputs.arm_a, len(inputs.close), subjects._ASSETS
block = reader.block()
steps = Counter(str(a.year) for a, b in zip(inputs.h4_ts, inputs.h4_ts[1:]) if b - a != timedelta(hours=4))
print("closes", n, "; union steps other than 4 h, by year:", dict(steps))
print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in sorted(block.items())})
print("vouched", reader.vouched_status())
fed = subjects._ffill_btc(inputs.h4_prices)
for key, signal in inputs.signals.items():
    every = next(k for k in range(n) if all(signal[a][k] is not None for a in assets))
    held = [sum(z is not None for z in signal[a]) for a in assets]
    priceless = sum(z is not None and fed[a][k] is None for a in assets for k, z in enumerate(signal[a]))
    print(f"{key}: every asset's from index {every} ({close[every]}); held per asset {held}; held where the close is missing {priceless}")
print("arm A long", [sum(p > 0 for p in arm_a[a]) for a in assets], "flat", [sum(p == 0 for p in arm_a[a]) for a in assets])
counts = subjects._b2_reading_counts(inputs)
for key in inputs.signals:
    for tail in subjects._B2_READING_TAILS:
        for state in subjects._B2_READING_STATES:
            e = [counts["events_per_asset"][key][tail][state][a] for a in assets]
            o = [counts["others_per_asset"][key][tail][state][a] for a in assets]
            print(f"{key} {tail} {state}: events {sum(e)} {e}; others {sum(o)} {o}")
```

Its output, whole, each list in `_ASSETS`' order (ADA, AVAX, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP):

```text
closes 27337 ; union steps other than 4 h, by year: {'2013': 57, '2016': 1, '2018': 3, '2024': 1, '2025': 1}
block ad140b62ac72cfd6b4931dbe4f529f29d4dd34ef49d86e791c37764d2cf8eee1 {'derivatives-funding': (10, 68281, ['2020-01-01 00:00:00+00:00', '2026-06-30 16:00:00+00:00']), 'derivatives-oi': (10, 5010882, ['2020-09-01 00:00:00+00:00', '2026-07-22 23:55:00+00:00']), 'liquidations-daily': (10, 15048, ['2022-08-25 00:00:00+00:00', '2026-10-20 00:00:00+00:00']), 'ohlc-full': (10, 173373, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)', 'derivatives-funding': 'checked (10 vouched hashes)', 'derivatives-oi': 'checked (10 vouched hashes)', 'liquidations-daily': 'checked (10 vouched hashes)'}
binperp_funding_z30d: every asset's from index 15419 (2020-10-22 08:00:00+00:00); held per asset [13400, 11918, 13512, 12364, 12118, 13512, 13414, 13462, 11741, 13480]; held where the close is missing 4053
binperp_oi_z30d: every asset's from index 18026 (2021-12-30 20:00:00+00:00); held per asset [8584, 8769, 11125, 8769, 8769, 8589, 8769, 8570, 8583, 8589]; held where the close is missing 9
binperp_ratio_max_z30d: every asset's from index 20298 (2023-01-13 12:00:00+00:00); held per asset [5959, 6139, 8694, 6139, 5959, 5959, 6139, 6139, 6139, 6139]; held where the close is missing 9
binperp_liq_long_z30d: every asset's from index 19731 (2022-10-11 00:00:00+00:00); held per asset [7612, 7438, 7606, 7612, 7708, 7606, 7612, 7444, 7618, 7606]; held where the close is missing 9
arm A long [8938, 4680, 17169, 6766, 6640, 13428, 7954, 11958, 6024, 9905] flat [18399, 22657, 10168, 20571, 20697, 13909, 19383, 15379, 21313, 17432]
binperp_funding_z30d above long: events 3486 [372, 164, 402, 326, 347, 454, 336, 458, 210, 417]; others 67196 [6936, 4516, 7887, 6401, 6286, 7723, 7432, 7449, 5789, 6777]
binperp_funding_z30d above flat: events 544 [56, 192, 14, 48, 5, 10, 42, 68, 62, 47]; others 57695 [6036, 7046, 5209, 5589, 5480, 5325, 5604, 5487, 5680, 6239]
binperp_funding_z30d below long: events 1415 [159, 115, 191, 147, 85, 141, 184, 151, 101, 141]; others 69267 [7149, 4565, 8098, 6580, 6548, 8036, 7584, 7756, 5898, 7053]
binperp_funding_z30d below flat: events 3434 [397, 347, 279, 321, 335, 305, 386, 311, 396, 357]; others 54805 [5695, 6891, 4944, 5316, 5150, 5030, 5260, 5244, 5346, 5929]
binperp_oi_z30d above long: events 5256 [455, 410, 586, 771, 351, 540, 604, 515, 380, 644]; others 40519 [3498, 3805, 5892, 3778, 3838, 3951, 4016, 4066, 4250, 3425]
binperp_oi_z30d above flat: events 3036 [362, 406, 283, 103, 616, 271, 179, 212, 426, 178]; others 40305 [4269, 4148, 4364, 4117, 3964, 3827, 3970, 3777, 3527, 4342]
binperp_oi_z30d below long: events 936 [64, 88, 219, 21, 147, 64, 68, 78, 129, 58]; others 44839 [3889, 4127, 6259, 4528, 4042, 4427, 4552, 4503, 4501, 4011]
binperp_oi_z30d below flat: events 2742 [310, 224, 319, 359, 129, 318, 328, 332, 156, 267]; others 40599 [4321, 4330, 4328, 3861, 4451, 3780, 3821, 3657, 3797, 4253]
binperp_ratio_max_z30d above long: events 8193 [782, 827, 1020, 816, 865, 550, 893, 817, 875, 748]; others 26171 [2040, 2367, 4439, 2383, 2118, 2656, 2504, 2564, 2705, 2395]
binperp_ratio_max_z30d above flat: events 3522 [327, 290, 518, 301, 303, 439, 283, 409, 252, 400]; others 25519 [2810, 2655, 2717, 2639, 2673, 2314, 2459, 2349, 2307, 2596]
binperp_ratio_max_z30d below long: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 34364 [2822, 3194, 5459, 3199, 2983, 3206, 3397, 3381, 3580, 3143]
binperp_ratio_max_z30d below flat: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 29041 [3137, 2945, 3235, 2940, 2976, 2753, 2742, 2758, 2559, 2996]
binperp_liq_long_z30d above long: events 2743 [226, 301, 236, 359, 298, 239, 254, 282, 270, 278]; others 38589 [3560, 3583, 4352, 3817, 3714, 4020, 3938, 3919, 4121, 3565]
binperp_liq_long_z30d above flat: events 1761 [157, 172, 171, 156, 241, 169, 165, 197, 179, 154]; others 32769 [3669, 3382, 2847, 3280, 3455, 3178, 3255, 3046, 3048, 3609]
binperp_liq_long_z30d below long: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 41332 [3786, 3884, 4588, 4176, 4012, 4259, 4192, 4201, 4391, 3843]
binperp_liq_long_z30d below flat: events 0 [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; others 34530 [3826, 3554, 3018, 3436, 3696, 3347, 3420, 3243, 3227, 3763]
```

What it establishes:

- **The block is the four sets' files**: `ohlc-full`'s ten 4h files beside the ten files of `derivatives-funding`, `derivatives-oi` and `liquidations-daily`, `compute_hash` `ad140b62ac72cfd6b4931dbe4f529f29d4dd34ef49d86e791c37764d2cf8eee1`, every set `checked` against its vouched hashes; each set is one a landed record already cites (records 51 and 56 the funding set, 52–53 the OI set, 54–55 the daily block), so each is on the hub's `hot/` and the reading needs no push.
- **Each signal is its trial's**: the first close every asset's signal holds is the trials' own — the funding z-score's index 15,419 (2020-10-22 08:00, spec 00139's basis), the OI z-score's 18,026 (2021-12-30 20:00) and the ratios' maximum's 20,298 (2023-01-13 12:00, spec 00138 D4–D5), the liquidation z-score's 19,731 (2022-10-11 00:00, spec 00139's basis) — and the funding signal's upper tail in the long state, 3,486 events beside 67,196 others, is trial 2's engagement, 3,486 of 70,682 (spec 00137's basis).
- **Arm A's states**: 93,462 long asset-stamps and 179,908 flat, their sum 27,337 × 10, none below 0 (`short="off"`).
- **The lower tails of the ratios' maximum and the liquidation z-score hold no event in either state**: the maximum of four z-scores and the z-score of a positive, right-skewed daily notional never read below −2.0 here, so twelve of the 48 cells read no row (D8 keeps the correction over 48). Every other cell holds events in both states, from the funding signal's upper tail in the flat state, 544 (DOT 5, ETH 10, BTC 14), to the ratios' upper tail in the long state, 8,193.
- **The forwards' grid**: 63 of the union's steps are other than 4 h, 61 of them in 2013–2018 and one each in 2024 and 2025; from the funding signal's start on, H closes are 4·H hours except across those two steps (D5). The funding signal is read at 4,053 asset-stamps whose close is missing — AVAX's and SOL's perps trading before their Kraken pairs — which a forward cannot read, so those flagged stamps enter the counts (D7) and no row.

**The chunked contrast's memory and time** (D6), a third program from the worktree root, on synthetic inputs of the reading's size — 27,337 return indices, the ten assets, three forward series, about 3 % of the indices events and 52 % others — at `mean_block=30`, `seed=42`; its first argument picks the chunked contrast at a chunk size or `event_contrast` itself at a count of resamples:

```python
import random
import resource
import sys
import time

from cli.alpha.b2 import event_contrast, event_contrast_chunked
from cli.research.subjects import _ASSETS

mode, size = sys.argv[1], int(sys.argv[2])
rng = random.Random(42)
n = 27_337
flags = {a: [None if u < 0.45 else u > 0.97 for u in (rng.random() for _ in range(n))] for a in _ASSETS}
forwards = {
    f"fwd_logret_{4 * h}h": {a: [None if k + h >= n or rng.random() < 0.02 else rng.gauss(0, 0.02) for k in range(n)] for a in _ASSETS}
    for h in (1, 6, 24)
}
built = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
start = time.perf_counter()
if mode == "chunked":
    out = event_contrast_chunked(flags, forwards, mean_block=30, n_resamples=2000, seed=42, chunk=size)
else:
    out = event_contrast(flags, forwards, mean_block=30, n_resamples=size, seed=42)
elapsed = time.perf_counter() - start
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"{mode} {size}: {elapsed:.1f} s, peak RSS {peak / 1024:.0f} MiB, {built / 1024:.0f} MiB once the inputs were built; {sum(map(len, out.values()))} rows")
```

Run as `chunked 10`, `chunked 100`, `whole 100` and `whole 200`, one process each; their output, whole:

```text
chunked 10: 11.1 s, peak RSS 124 MiB, 105 MiB once the inputs were built; 33 rows
chunked 100: 13.1 s, peak RSS 205 MiB, 105 MiB once the inputs were built; 33 rows
whole 100: 1.5 s, peak RSS 439 MiB, 105 MiB once the inputs were built; 33 rows
whole 200: 4.0 s, peak RSS 731 MiB, 105 MiB once the inputs were built; 33 rows
```

- At the reading's 2,000 resamples the chunked contrast peaks 19 MiB above its inputs at its default chunk of 10, in 11.1 s a cell; at 100 a chunk, 100 MiB above them and slower. `event_contrast` itself rose 334 MiB above its inputs at 100 resamples and 626 MiB at 200, about 2.9 MiB a resample, so about 6 GiB at 2,000 — extrapolated, never run on this workstation, a live fleet host. The program draws at `mean_block=30` and the reading at 102 (D6): the block sets only how often a resample jumps to a fresh start — one `randrange` call more per jump, taken at a 102nd of the indices in place of a 30th — never an array's shape, so the memory above holds at 102 and the time does not grow.
- The program hands the contrast three series and the reading six, D5's two families. The same program at `mean_block=102`, with a second family beside the first — each series the first's shifted by a constant, its `None`s the first's — run as `chunked 10` in a scratch worktree of this branch at 13:28Z, after the window above, read 17.5 s a cell and peaked 29 MiB above its inputs, against 11.1 s and 19 MiB at three series in the next process: sixteen cells at about 17.5 s each and the inputs half's 163 s (the data-gated case, plan 00140 Task 3) put the reading's run near seven and a half minutes.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this reading runs under one, the session holding this branch's worktree, `.claude/worktrees/iter184`, on the workstation `zcrypto-ops`. No other session appends to `docs/reference/reading-ledger.jsonl` while this branch is open.
- **The process.** The reading is one `uv run zcrypto research eval` process in this worktree, awaited to its exit — no daemon, timer or concurrent run, and no step reads it as ended while its process lives. It reads `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily`, symlinks to the main checkout's sets, each frozen and attested; it writes nothing under them, makes no network call, and nothing it reads has a live writer.
- **No trial-attempts log.** A subject with no rule registers no trial: `--reading` begins no attempt and its line carries `attempt` `null`, as reading 2's does; the trial-attempts log and Bucket B's budget are untouched.
- **The reading ledger** — tracked, append-only, hash-chained; this worktree is its one writer while the branch is open. `--reading` refuses a tree with uncommitted changes, so the run's line is committed with its decisions-log entry before anything else lands (D9).

## The question (no hypothesis, no bar)

Six B2 trials on these four signals — two de-risks on the funding z-score's upper tail and one each on the OI, ratio and liquidation signals, two re-entries on the liquidation signal's upper tail and the funding signal's lower — each lost to arm A net of cost, and the decomposition shows each one's gross result carrying the sign exposure alone gives. The reading asks the question beneath them: **after a close at which a signal lies past ±2, and inside one state of arm A — long or flat — does the asset's forward log return differ from its forward return after the other closes at which the signal is read in that state?** A cell that clears the potential criterion (D8) names the trial it would justify; none clearing it is the evidence the owner's family call reads. The reading tests no hypothesis, has no bar, matrix or verdict, spends no B slot, and changes no verdict of trials 2–7.

## D1 — the pick: a reading of the signals before B2's next trial

- **Author's call, under the owner's run instruction** ("try the trials with potential and do not close any family too early"), among three:
  1. **A re-risk mirror trial** — raise arm A's long position to its full-long size (spec 00139's `full_long_sizes`) where a crowding signal fires and arm A is long below that size. Evidence-led on its face, since every de-risk lost return; but the decomposition shows the de-risks' gross losses and the re-entries' gross gains carrying the signs the ensemble's positive drift alone gives, so the mirror most likely buys drift with extra turnover, spending a slot to learn little.
  2. **A reading, no slot: the four trialled 4h-grid signals' forward-return contrast, by tail and by arm A's state**, against a pre-registered potential criterion that names the trial a cell would justify. Chosen: it spends no B slot (14 of 25 remain, T0016), and it decides whether any further B2 trial has potential before one is spent — the run instruction's "try the trials with potential".
  3. **Park the pick to the owner** with the decomposition — B2 open, nothing run. Cheapest; but it leaves the instruction's "try the trials with potential" unexamined.
- The reading closes nothing: whatever it reads, B2 stays open, and a close is the owner's (D8).

## D2 — the instrument and the subject: frozen `ohlc-full`, full history, a reading

- **One reading subject**, `b2-signal-reading` in `cli/research/subjects.py`: `spec="docs/specs/00140-b2-signal-reading-design.md"`, `_ASSETS`, intervals `(240,)`, `metric_keys=_B2_READING_KEYS` (D7), seeds `(42,)` — the draw's seed — and no rule, family or count: `--register` refuses it, its plain eval is admitted, and `--reading --iteration iter-184 --spec-hash <H>` keeps its run on `docs/reference/reading-ledger.jsonl`, as spec 00138 D12 keeps the tape's reading. No incumbent; arm A is built in the run.
- **The instrument ruling's set**: `--dataset ohlc-full`, no `--window`, no `--as-of`; the union `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices, the trials' own. **Author's call — the full history**: every close at which a signal and a forward are read, from each signal's own first close (D4); the owner's From-2021 read governs a trial's head-to-head, not a reading, and only the funding signal holds closes before 2021, from 2020-10-22.

## D3 — arm A's state at the signal's close

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46 and 48–56 built it, by `_b2_overlay_inputs`' own expression — **Author's call: by calling `_b2_overlay_inputs` itself**, with the funding reader `_b2_funding_signal` and the threshold 2.0, so the union, its two window refusals and arm A are that function's, unchanged; its scales, the de-risk's halving at that threshold, are computed and unused. `_b2_reentry_inputs`' arm A is the same expression with its books kept for the full-long size, which the reading does not read.
- **The states**, per asset at return index `k` — the close at which the signal is read and at which arm A takes the position it holds over the next return: **long** where arm A's position is above 0, **flat** where it is 0. Arm A is long-only (`short="off"`), so the two cover every asset-stamp (the basis: 93,462 long, 179,908 flat).
- A re-risk (D8) engages only where arm A is long below its full-long size, which spec 00139's basis measured equal to arm A's position at 30,632 long asset-stamps; the long state does not split the two, and a later spec measures it.

## D4 — the signals and the tails: the four the trials read, each by its trial's reader, past ±2.0

- **The signals**, none new, each read by the function its trial's subject reads it with, over the reading's union:
  - `binperp_funding_z30d` — `_b2_funding_signal(reader, h4_ts)`, trial 7's reader and, by its own docstring, `_b2_inputs`' loop, trial 2's: per perp `funding_grid_feature(..., config=B2Config())` over `derivatives-funding/<PERP>/funding.parquet`, the 90-print (30-day) z-score of the 8-hourly funding rate (trials 2 and 7, specs 00137 and 00139).
  - `binperp_oi_z30d` — `_b2_oi_signal(reader, h4_ts)`, trial 3's: `oi_zscore_grid_feature` over `derivatives-oi/<PERP>/oi.parquet`'s `sum_open_interest`, the 180-mark z-score (spec 00138 D4).
  - `binperp_ratio_max_z30d` — `_b2_ratio_signal(reader, h4_ts)`, trial 4's: `ratio_max_signal(ratio_zscore_grid_features(...))` over the same file's four ratios, their 180-mark z-scores' maximum where all four are read (spec 00138 D5).
  - `binperp_liq_long_z30d` — `_b2_liq_signal(reader, h4_ts)`, trials 5 and 6's: `daily_zscore_grid_feature` over `liquidations-daily/<COIN>/daily.parquet`'s `long_usd`, the 30-day z-score of the day's long-side liquidated notional, a day read from the first close at or after its end (spec 00138 D6).
- **The tails**: **above**, a signal strictly above +2.0; **below**, strictly below −2.0 — the trials' own strict comparisons (`derisk_scales`' `z > threshold`, trial 7's `operator.lt`). **Author's call — one threshold, 2.0, for every signal and both tails**: the lower of the trials' thresholds (2.0 for trials 2 and 7, 2.5 for trials 3–6), for power — the rarer 2.5 tail is a subset of it, and each cell's events stay in the hundreds or more on every signal that holds the tail (the basis). A signal read as `None` flags nothing.

## D5 — the forwards: the log return over 1, 6 and 24 closes on the arms' prices, and the returns the book is credited over them

- At return index `k`, for each asset and each H ∈ {1, 6, 24} closes — 4 hours, a day and four days — the forward is `log(close[k + H] / close[k])`, the closes the union's own at indices `k` and `k + H`, `None` where either is missing or `k + H` passes the union's last close: `_b2_reading_forwards(h4_prices)`, keyed `fwd_logret_4h`, `fwd_logret_24h` and `fwd_logret_96h`. H closes are 4·H hours except across the union's two steps other than 4 h since 2019, one in 2024 and one in 2025 (the basis).
- **Author's call — the arms' prices**: the closes through `_ffill_btc`, the BTC-only forward fill the arms trade on, so the 1-close forward is the log of one plus the very return `net_of_cost` multiplies arm A's position by (`_asset_returns` over the same fill). Every other asset keeps its raw `None`s.
- **The book's units, measured**: beside each log forward the same function returns `fwd_sumret_4h`, `fwd_sumret_24h` and `fwd_sumret_96h` — at return index `k`, the sum of `_b2_returns`' H returns from `k`, the `prices[t + 1] / prices[t] − 1` that `net_of_cost` multiplies a position by, over the same fill, a missing return counted 0 as `net_of_cost` counts it, and `None` exactly where the log forward is `None`, so each cell's events and others are the same closes in both families. It is what a unit held from a close for H closes is credited before cost; where no return is missing, the log forward falls short of it by about half the H returns' summed squares, a gap that grows with H. Leg 4 of the criterion (D8) reads this family, legs 1–3 the log forward.
- A close at or below zero carries no log return; arm A's build refuses one first (`a2_book_returns`' own `AlphaError`), so no forward is read past it.

## D6 — the contrast: events against others in one state, per asset and pooled, with one draw's bounds

- **The cell**, per (signal, tail, state, H): the flags `_b2_reading_flags(signal, arm_a, tail, state)` — `True`, an event, where the signal is past the tail and arm A in the state; `False`, another close, where the signal is read, not past that tail, and arm A in the same state; `None` elsewhere. Per asset with at least two events and two others whose forward is read, and pooled over those assets: `[events, others, mean forward after the events, mean after the others, their difference, the difference's 2.5 % and 97.5 % bounds, its 0.05 % and 99.95 % bounds]` — `event_contrast`'s row (spec 00138 D12) and the two far bounds after it — one such row for each of D5's two families, the summed returns' over the same assets, events and others as the log forward's.
- **The bounds** are the percentiles of the difference over one stationary-bootstrap draw of return indices, `mean_block=102` — the longer of the kill bar's two blocks, 30 and 102, so that the 24-close forwards' overlap is held: forwards at nearby indices share up to 23 of their 24 returns, and 24 consecutive drawn indices stay inside one block with probability (101/102)^23 ≈ 0.80, against (29/30)^23 ≈ 0.46 at 30; the draw keeps two forwards j indices apart together with probability (1 − 1/block)^j, so weighted by the returns they share block 30 would cut about a quarter of that overlap — it keeps 77 % of it, against 92 % at 102 — and narrow the 96-hour bounds — `n_resamples=2000`, `seed=42`; a resample holding no event or no other for a row is skipped for that row. Every cell draws over the same 27,337 indices with the same seed, so every cell reads the same draw and the pooled bounds keep the assets' common closes together.
- **The chunked twin.** `event_contrast` cannot run at this size: it holds the draw as a 2,000 × 27,337 index array and every asset's gathered events, others and forwards at once, about 6 GiB (the basis). `event_contrast_chunked(flags, forwards, *, mean_block, n_resamples, seed, chunk=10)`, new in `cli/alpha/b2.py`, computes the same rows from the same resamples, drawn and read `chunk` at a time: `_bootstrap_chunks` replays `stationary_bootstrap_indices`' generator — `random.Random(seed)`, the same calls in the same order — and yields each chunk of resamples as an index array, and the per-resample sums each chunk adds are the ones `event_contrast` takes row by row, so the rows are equal to the bit, not to a tolerance. It refuses what `event_contrast` refuses, with `stationary_bootstrap_indices`' own messages, and a chunk below 1. **Author's call — the chunk of 10**: memory grows with the chunk and time does not fall (the basis's three-series program: 11.1 s and 19 MiB at 10, 13.1 s and 100 MiB at 100).
- **The known-answer test** (plan 00140 Task 1) holds `event_contrast_chunked`'s first seven entries equal to `event_contrast`'s rows on a small input with two series that keep different assets and a third that keeps none, at chunks of 1, 7, 10, 200 and 500, and its far bounds to the percentiles of the hand-resampled differences.
- **The far bounds' resolution**: at 2,000 resamples the 0.05 % and 99.95 % percentiles lie between the two most extreme resampled differences on each side; a bound there is coarse, and the criterion (D8) reads it as it stands.

## D7 — the keys, the refusals and the build

- **The 29 keys** (`_B2_READING_KEYS`): per signal and horizon, `<signal key>_fwd_logret_<4·H>h` and `<signal key>_fwd_sumret_<4·H>h` — twenty-four keys, D5's two families — each `{"above": {"long": <rows>, "flat": <rows>}, "below": {...}}`, the rows `{<asset>: <row>, …, "pooled": <row>}` over the kept assets and `{}` where a cell keeps none; `events_per_asset` and `others_per_asset`, each `{<signal key>: {<tail>: {<state>: {<asset>: <count>}}}}`, the flags' counts before any forward is read (`_b2_reading_counts`, the basis's figures); and the constants `threshold` 2.0, `mean_block` 102 and `n_resamples` 2000.
- **Refusals**, the re-entry subjects' own: `--as-of`, before any read — "b2-signal-reading evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset"; a file of a signal's set it cannot read, by name, each reader's own (`derivatives-funding/<PERP>/funding.parquet: …`, `derivatives-oi/<PERP>/oi.parquet: …` from the OI or the ratio reader, `liquidations-daily/<COIN>/daily.parquet: …`); `_b2_overlay_inputs`' two window refusals — fewer than `1380 + 2` return indices, or none in a calendar year the worst-slice leg reads — and any compute error, each a `SubjectError` naming the subject over its window. The plain eval is admitted.
- **The build in halves.** The inputs: `_b2_reading_inputs(subject, reader, dataset, window, accept_holes)` — `_b2_overlay_inputs` (D3), then the OI, ratio and liquidation readers over its union — returning `_B2ReadingInputs(h4_ts, h4_prices, close, arm_a, signals)`, no forward return. The computes: `_b2_reading_metrics(inputs)` — the forwards, then per signal, tail and state the flags and one `event_contrast_chunked` call over the six forward series, D5's two families at three horizons, the counts and the constants. `_build_b2_signal_reading` refuses `--as-of` and wraps both halves.
- **The files the build touches, a closed list**: `cli/alpha/b2.py` — the import `random`, `_bootstrap_chunks` and `event_contrast_chunked`; `cli/research/subjects.py` — the import of `event_contrast_chunked`, the constants `_B2_READING_THRESHOLD`, `_B2_READING_TAILS`, `_B2_READING_STATES`, `_B2_READING_HORIZONS`, `_B2_READING_BLOCK` and `_B2_READING_SIGNALS`, `_B2ReadingInputs`, `_b2_reading_inputs`, `_b2_reading_flags`, `_b2_reading_counts`, `_b2_reading_forwards`, `_b2_reading_metrics`, `_build_b2_signal_reading`, `_B2_READING_KEYS` and one `SUBJECTS` entry; no existing function of either file changed; `README.md`'s `--subject` row; the tests the plan names. No change to `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/validation/*`, `cli/engine/*`, `cli/liquidations/*`, specs 00128, 00137, 00138 and 00139, the subjects of trials 1–7 and of readings 1–2, or any adopted artifact.

## D8 — the pre-registered potential criterion, the contamination, and what the reading changes

- **The criterion**, fixed by this spec's sha256 before any forward is read, read by the closeout's pick and never by code — the subject has no rule: a cell has **potential** only if all four hold on its pooled rows, legs 1–3 on the log forward's and leg 4 on the summed returns' (D5):
  1. its 0.05 %–99.95 % bounds exclude 0 — Bonferroni over the 48 pooled cells, 4 signals × 2 tails × 2 states × 3 horizons, at 5 % two-sided. **Author's call — 48, though twelve cells read no row** (the basis's empty lower tails): the count is the design's, fixed before the run, and over the cells that read a row — 36 at most — it is conservative;
  2. |difference| ≥ 0.012 at its horizon — one full-unit round trip at 0.006 per side, the cost the trials paid: the signal's edge over the other closes in its state, the part drift alone does not give, must carry at least that;
  3. its sign maps to an action a long/flat book can take: positive in the flat state → a **re-entry**, positive in the long state → a **re-risk**, negative in the long state → a **de-risk**; a negative difference in the flat state names no action, the book holding no short;
  4. its summed returns' mean after the events, in that action's direction, clears the same round trip — at least +0.012 for a re-entry or a re-risk, at most −0.012 for a de-risk: each action changes the position at the event closes alone, so against arm A a trade entered at the event's close and left H closes later is credited, per unit of position changed, the sum of the H returns `net_of_cost` multiplies it by (D5) — never the difference, nor the log forward — and pays the round trip.
- **A cell with potential names the trial a later spec would pre-register**: that action on that signal past that tail, in that state, held H closes; where the action on that signal and tail is already a rejected trial's (trials 2–7), the later spec states how its hold or size differs and cites the record. **None with potential** is the evidence the owner's family call — hold or close B2 — reads; the loop closes nothing (D1).
- **The contamination, plainly**: the reading reads the trials' own instrument — the frozen union, arm A and the signals six landed records read — and its rows are the data any trial it justifies would be judged on. Such a trial is designed from that data; its spec says so, it carries this reading's id beside its own figures, and its DSR counts the family's true trials — B2's landed records and the one it adds, the reading's look included in the design, never a count that leaves it out.
- **What it changes**: no verdict of trials 2–7, no B slot, no record; its figures go to T0023's findings beside its decisions-log entry, and B2's next step after it — the pick reading this criterion — is T0023's trigger.

## D9 — the run

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00140-b2-signal-reading-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` — before the append; (3) the data-gated basis test on the run's tree; (4) the one run, `uv run zcrypto research eval --subject b2-signal-reading --dataset ohlc-full --reading --iteration iter-184 --spec-hash <(1)> --notes "<written before the run>"`, no plain eval before or after it; (5) the ledger line's checks, its replay and its commit with the decisions-log entry naming `(reading <N>)`.
- **The hash rule**: before (1), nobody computes a forward return over the real data or runs `b2-signal-reading` over the real sets; the basis and the data-gated test hold positions, signals, counts and the block only.
- **The notes, written before the run**: the subject over `ohlc-full`, full history; that it is descriptive, with no bar, verdict or slot, changing no verdict of trials 2–7; the four signals, each its trial's; the tails, the states and the forwards; the contrast and its bounds; the potential criterion pre-registered by this spec's sha256.
- A refused build keeps no reading; T0023 records it with its line quoted, and the reading's design stands unrun.

## Out of scope

Any trial — a re-risk, a de-risk variant, a re-entry or any other — and any threshold, signal, state split or horizon other than D4–D5's; a rule over the reading's figures; the full-long split of the long state (D3); a reading on any instrument but frozen `ohlc-full`, on the 1-minute tape, or at a later as-of; the de-risks' and re-entries' park variants; a live liquidation or funding feed; Bucket B's other families (B3, B4-legs), T0016's; any change to an existing function, subject, record or reading.
