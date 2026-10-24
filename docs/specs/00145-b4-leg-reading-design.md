# B4's leg reading — trial 58's books by leg and by cost: each ratio leg alone on the A2-4h ensemble, as trial 58 costed arm B and held to the book's own BTC, and trial 58's head-to-head taken apart, on the frozen `ohlc-full` set

**Ruling:** the owner, attended, 2026-10-23, picking the family after B2's close, verbatim: "B4-legs (Recommended)" (the decisions log's `[iter-188] B2's next step after trial 8 — closed`); then, launching this unattended run, verbatim: "continue working on B4-legs and other research strates. Ignore the wall time clock gate, but do not pick up new topics after 09:00Z". B4 trial 1 (registry trial 58, spec 00144) was rejected (`[iter-189] Verdict — B4 trial 1 REJECT`): arm B passed the kill bar, but its head-to-head against arm A from the first ratio weight was −4.700758514095985e-06/bar (SPA p 0.8500749625187406), and its borrow-unavailable twin's −1.4398882599350185e-06 (p 0.6421789105447276) at a net Sharpe 1.4721 above arm A's 1.4050. The run closes no family — closing is the owner's — so B4's next step after trial 1, T0016's B4 arm, is the loop's pick under that instruction (D1), recorded as `[iter-190] B4's next step after trial 1 — a no-slot reading of trial 58's books by leg and by cost, the loop's pick under the owner's run instruction` in `docs/research/10.phase4-decisions.md` before this spec's hash; a close of B4 is the owner's and is not picked. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" (the `[iter-181] B2 instrument ruling` entry) and the two `[iter-176]` rulings — the DSR leg binding at `var_trials` 0.0, and the spent holdout's window never reported as holdout evidence (this set ends 2026-03-31, before it). Every call past those words and past what specs 00141, 00142 and 00144 fix is the loop's, marked **Author's call** where it is made. **Iteration:** iter-190, branch `research/iter-190-b4-leg-reading`. **Topic:** T0016, its B4 arm. **Goal:** read, before a slot is spent, which leg carried trial 1's loss and whether either leg alone has potential — each ratio leg alone on the A2 ensemble, as trial 58 costed arm B and held to the book's own BTC as its twin was, against arm A — and where the loss sits among trial 58's gross, its trading cost and its carry. Spec 00142 is this spec's form (a no-slot reading: an evaluate-only subject, `--reading` into `docs/reference/reading-ledger.jsonl`, a pre-registered potential criterion read by the closeout's pick and never by code, the contamination stated, the subject retired after), spec 00144 its instrument, books, costing, carry, limits and twin, spec 00141 D8 its criterion's floor-and-legs form. The reading spends none of bucket B's 12 remaining slots.

## The measured basis

Every figure below was measured on 2026-10-24 in this branch's worktree at develop's `3cfa7a68d`, with `data/ohlc-full` symlinked read-only from the main checkout's `data/` and no other set linked: the book programs between 09:04:00Z and 09:09:22Z, the cells program between 09:09:54Z and 09:14:26Z, then the reading's data-gated case, the computes, name and count programs, the count read at 09:32:37Z. They read closes, weights, positions, per-base exposures, the BTC shortfall and the carry it implies, limit engagement and turnover only: no return of any book is read — no cell's or trial 58's net-of-cost series, head-to-head or cost layer — and the reading's subject never runs over the real set. `a2_book_returns` computes each book's base returns on its way to the positions, since its vol target sizes on them; the programs read its `asset_positions` alone. Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

**The books**, a first program run twice — its part `a` building arm A and trial 58's arm B, its part `b` each leg alone beside the ten EUR assets with its book's own weight path — by their own three-arm expression, never through the reading's code, the books kept under `.tmp/` for the second program:

```python
import pickle
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _inverse_vol_weights
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

part = sys.argv[1]
print("start", part, datetime.now(UTC).isoformat(timespec="seconds"))
reader = ObservedReader(Path("data"))
h4_ts, h4_prices = subjects._capturing_union(reader, "ohlc-full", 240, None, None, False)
n = len(h4_ts) - 1
ratios = {}
for leg in ("ETH/BTC", "SOL/BTC"):
    frame = reader.read_series("ohlc-full", f"{leg}/240.parquet")
    by_ts = dict(zip(frame["ts"].to_list(), frame["close"].to_list(), strict=True))
    ratios[leg] = [by_ts.get(t) for t in h4_ts]
fed = _ffill_btc(h4_prices)
configs = [
    A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lb, tv in subjects._B2_A2_ARMS
]


def ensemble(prices):
    arms = [a2_book_returns(prices, config=c)["asset_positions"] for c in configs]
    return {i: [statistics.mean(arm[i][k] for arm in arms) for k in range(n)] for i in prices}


books = {"h4_ts": h4_ts}
if part == "a":
    block = reader.block()
    print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in block.items()}, "vouched", reader.vouched_status())
    t0 = time.perf_counter()
    books["arm_a"] = ensemble(fed)
    t1 = time.perf_counter()
    books["arm_b"] = ensemble(fed | ratios)
    t2 = time.perf_counter()
    print(f"arm A's three A2 runs {t1 - t0:.1f} s, trial 58's arm B's {t2 - t1:.1f} s")
else:
    for leg in ratios:
        priced = fed | {leg: ratios[leg]}
        t0 = time.perf_counter()
        books[leg] = ensemble(priced)
        t1 = time.perf_counter()
        weights = _inverse_vol_weights(priced, lookback=180)
        books[f"{leg} first"] = next((k for k in range(n) if leg in weights[k]), n)
        print(f"{leg} alone: three A2 runs {t1 - t0:.1f} s, its weight path {time.perf_counter() - t1:.1f} s")
Path(f".tmp/iter190/basis/books-{part}.pickle").write_bytes(pickle.dumps(books))
print("end", part, datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole, part `a` and then part `b`:

```text
start a 2026-10-24T09:04:00+00:00
block 9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df {'ohlc-full': (12, 205917, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])} vouched {'ohlc-full': 'checked (36 vouched hashes)'}
arm A's three A2 runs 64.9 s, trial 58's arm B's 75.8 s
end a 2026-10-24T09:06:21+00:00
start b 2026-10-24T09:06:24+00:00
ETH/BTC alone: three A2 runs 72.6 s, its weight path 18.6 s
SOL/BTC alone: three A2 runs 69.1 s, its weight path 17.9 s
end b 2026-10-24T09:09:22+00:00
```

**The cells**, a second program over the first's books — the limits, the twins, the spans, the holding, the shortfall, its carry and turnover, written out with `cli/alpha/b4.py`'s functions, never through the reading's code:

```python
import math
import pickle
import statistics
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import close_grid
from cli.alpha.b4 import base_exposures, borrow_unavailable, limit_factors, scale_bars

print("start", datetime.now(UTC).isoformat(timespec="seconds"))
a = pickle.loads(Path(".tmp/iter190/basis/books-a.pickle").read_bytes())
b = pickle.loads(Path(".tmp/iter190/basis/books-b.pickle").read_bytes())
h4_ts = a["h4_ts"]
assert b["h4_ts"] == h4_ts
close, n = close_grid(h4_ts), len(h4_ts) - 1
legs = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}
eur = [i for i in a["arm_a"]]
first = {leg: b[f"{leg} first"] for leg in legs}
print("first weight", {leg: (k, close[k].isoformat()) for leg, k in first.items()}, "; returns from it", {leg: n - k for leg, k in first.items()})


def first_differ(x, y, instruments):
    return next((k for k in range(n) if any(x[i][k] != y[i][k] for i in instruments)), n)


def limited(positions):
    factors, engaged = limit_factors(base_exposures(positions, legs))
    return scale_bars(positions, factors), engaged, factors


def per_year(flags):
    out = {}
    for k, flag in enumerate(flags):
        out[close[k].year] = out.get(close[k].year, 0) + int(flag)
    return {y: c for y, c in sorted(out.items()) if c}


arm_a, raw_b = a["arm_a"], a["arm_b"]
lim_a, engaged_a, _ = limited(arm_a)
print("arm A after the limits bit-identical:", lim_a == arm_a, {name: sum(f) for name, f in engaged_a.items()})
lim_b, engaged_b, _ = limited(raw_b)
twin_b, _, _ = limited(borrow_unavailable(raw_b, legs, "BTC"))
cells = {}
for leg in legs:
    raw = b[leg]
    zeroed = arm_a | {leg: [0.0] * n}
    print(f"{leg} alone, raw: first index differing from arm A's (its leg at 0.0) {first_differ(raw, zeroed, raw)}; its leg 0.0 before its first weight: {all(p == 0.0 for p in raw[leg][: first[leg]])}; first non-zero leg position {next((k for k in range(n) if raw[leg][k] != 0), n)}")
    carried, engaged_c, factor_c = limited(raw)
    twin_raw = borrow_unavailable(raw, legs, "BTC")
    no_borrow, engaged_t, factor_t = limited(twin_raw)
    cells[leg] = {"carried": (carried, engaged_c, factor_c), "no_borrow": (no_borrow, engaged_t, factor_t)}
    print(f"  the limits leave the raw book bit-identical: carried {carried == raw}, no-borrow {no_borrow == twin_raw}; engaged carried {({k: sum(f) for k, f in engaged_c.items()})}, no-borrow {({k: sum(f) for k, f in engaged_t.items()})}")
eth = b["ETH/BTC"]
shared = list(eth)
sol_first = first["SOL/BTC"]
print(f"ETH/BTC alone against trial 58's arm B, raw, on its eleven instruments: first index differing {first_differ(eth, raw_b, shared)}; trial 58's SOL/BTC 0.0 before SOL/BTC's first weight: {all(p == 0.0 for p in raw_b['SOL/BTC'][:sol_first])}")
print(f"  limited: first index differing {first_differ(cells['ETH/BTC']['carried'][0], lim_b, shared)}; the twins: first index differing {first_differ(cells['ETH/BTC']['no_borrow'][0], twin_b, shared)}")
for leg in legs:
    for funding, (book, _, _) in cells[leg].items():
        print(f"{leg} {funding}: first index differing from arm A (its leg at 0.0) {first_differ(book, arm_a | {leg: [0.0] * n}, book)}")
print("turnover: arm A", repr(book_turnover(arm_a)), "; trial 58's arm B", repr(book_turnover(lim_b)), "its legs'", {leg: book_turnover({leg: lim_b[leg]}) for leg in legs}, "its ten EUR legs'", book_turnover({i: lim_b[i] for i in eur}))
turnover_a, turnover_b = book_turnover(arm_a), book_turnover(lim_b)
rate = 0.0002
years_full = n / 2190
for leg in legs:
    for funding, (book, engaged, factor) in cells[leg].items():
        held = [book[leg][k] != 0 for k in range(n)]
        differ = [any(book[i][k] != (arm_a[i][k] if i in arm_a else 0.0) for i in book) for k in range(n)]
        t = book_turnover(book)
        print(f"{leg} {funding}: held at {sum(held)} return indices, per close year {per_year(held)}; mean position where held {statistics.fmean(book[leg][k] for k in range(n) if held[k]):.6f}, max {max(book[leg]):.6f}")
        print(f"  positions differ from arm A's at {sum(differ)} return indices ({sum(differ[first[leg]:])} from its first weight), per close year {per_year(differ)}")
        print(f"  turnover {t!r}: {100 * (t / turnover_a - 1):.2f} % against arm A's, {100 * (t / turnover_b - 1):.2f} % against trial 58's arm B's; its leg's own {book_turnover({leg: book[leg]}):.4f}, its ten EUR legs' {book_turnover({i: book[i] for i in eur}):.4f}")
        btc = base_exposures(book, legs)["BTC"]
        s = [max(0.0, -x) for x in btc]
        c = [rate * (s[k] + max(0.0, s[k] - (s[k - 1] if k else 0.0))) for k in range(n)]
        short = [x > 0 for x in s]
        carry_year = {}
        for k in range(n):
            carry_year[close[k].year] = carry_year.get(close[k].year, 0.0) + c[k]
        where = [x for x in s if x > 0]
        print(f"  shortfall at {sum(short)} return indices, per close year {per_year(short)}; mean where short {statistics.fmean(where) if where else 0.0:.6g}, max {max(s)!r}, mean over the window {statistics.fmean(s):.6f}")
        print(f"  carry at {rate}: summed {math.fsum(c)!r}; {100 * math.fsum(c) / years_full:.4f} % a year over the window, {100 * math.fsum(c[first[leg]:]) / ((n - first[leg]) / 2190):.4f} % a year from its first weight; per close year {({y: round(v, 6) for y, v in sorted(carry_year.items()) if v})}")
        print(f"  limits engaged {({k: sum(f) for k, f in engaged.items()})}, bars scaled {sum(f != 1.0 for f in factor)}; max per-base gross {max(math.fsum(abs(x[k]) for x in base_exposures(book, legs).values()) for k in range(n)):.6f}")
# Trial 58's carry, apportioned to its legs by their positions at each bar.
btc_b = base_exposures(lim_b, legs)["BTC"]
s = [max(0.0, -x) for x in btc_b]
c = [rate * (s[k] + max(0.0, s[k] - (s[k - 1] if k else 0.0))) for k in range(n)]
share = {leg: 0.0 for leg in legs}
parts = {leg: [] for leg in legs}
for k in range(n):
    total = lim_b["ETH/BTC"][k] + lim_b["SOL/BTC"][k]
    for leg in legs:
        parts[leg].append(c[k] * lim_b[leg][k] / total if total else 0.0)
print("trial 58's carry summed", repr(math.fsum(c)), "; by leg, pro rata to their positions at each bar", {leg: repr(math.fsum(v)) for leg, v in parts.items()}, "; the two summed", repr(math.fsum(parts["ETH/BTC"]) + math.fsum(parts["SOL/BTC"])))
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-24T09:09:54+00:00
first weight {'ETH/BTC': (5442, '2016-04-02T08:00:00+00:00'), 'SOL/BTC': (17079, '2021-07-26T00:00:00+00:00')} ; returns from it {'ETH/BTC': 21895, 'SOL/BTC': 10258}
arm A after the limits bit-identical: True {'gross': 0, 'net': 0, 'margin': 0}
ETH/BTC alone, raw: first index differing from arm A's (its leg at 0.0) 5442; its leg 0.0 before its first weight: True; first non-zero leg position 5612
  the limits leave the raw book bit-identical: carried True, no-borrow True; engaged carried {'gross': 0, 'net': 0, 'margin': 0}, no-borrow {'gross': 0, 'net': 0, 'margin': 0}
SOL/BTC alone, raw: first index differing from arm A's (its leg at 0.0) 17079; its leg 0.0 before its first weight: True; first non-zero leg position 17115
  the limits leave the raw book bit-identical: carried True, no-borrow True; engaged carried {'gross': 0, 'net': 0, 'margin': 0}, no-borrow {'gross': 0, 'net': 0, 'margin': 0}
ETH/BTC alone against trial 58's arm B, raw, on its eleven instruments: first index differing 17079; trial 58's SOL/BTC 0.0 before SOL/BTC's first weight: True
  limited: first index differing 17079; the twins: first index differing 17079
ETH/BTC carried: first index differing from arm A (its leg at 0.0) 5442
ETH/BTC no_borrow: first index differing from arm A (its leg at 0.0) 5442
SOL/BTC carried: first index differing from arm A (its leg at 0.0) 17079
SOL/BTC no_borrow: first index differing from arm A (its leg at 0.0) 17079
turnover: arm A 146.18534602048504 ; trial 58's arm B 157.64827493713167 its legs' {'ETH/BTC': 23.912564023957138, 'SOL/BTC': 6.077390770007466} its ten EUR legs' 127.65832014316521
ETH/BTC carried: held at 11397 return indices, per close year {2016: 644, 2017: 1443, 2018: 696, 2019: 1010, 2020: 1376, 2021: 1582, 2022: 1141, 2023: 1115, 2024: 939, 2025: 1127, 2026: 324}; mean position where held 0.049876, max 0.269606
  positions differ from arm A's at 19477 return indices (19477 from its first weight), per close year {2016: 1434, 2017: 2160, 2018: 1432, 2019: 2001, 2020: 2060, 2021: 2097, 2022: 1820, 2023: 2155, 2024: 1997, 2025: 1926, 2026: 395}
  turnover 156.66817821488746: 7.17 % against arm A's, -0.62 % against trial 58's arm B's; its leg's own 24.8992, its ten EUR legs' 131.7690
  shortfall at 7158 return indices, per close year {2016: 192, 2017: 582, 2018: 544, 2019: 582, 2020: 903, 2021: 1255, 2022: 983, 2023: 727, 2024: 477, 2025: 621, 2026: 292}; mean where short 0.0457127, max 0.26960565778396217, mean over the window 0.011970
  carry at 0.0002: summed 0.06753802151053973; 0.5411 % a year over the window, 0.6755 % a year from its first weight; per close year {2016: 0.001688, 2017: 0.003143, 2018: 0.006144, 2019: 0.006081, 2020: 0.007869, 2021: 0.008174, 2022: 0.007188, 2023: 0.012772, 2024: 0.006037, 2025: 0.004446, 2026: 0.003996}
  limits engaged {'gross': 0, 'net': 0, 'margin': 0}, bars scaled 0; max per-base gross 0.998300
ETH/BTC no_borrow: held at 7981 return indices, per close year {2016: 527, 2017: 1196, 2018: 505, 2019: 672, 2020: 1099, 2021: 970, 2022: 685, 2023: 648, 2024: 655, 2025: 726, 2026: 298}; mean position where held 0.030225, max 0.183697
  positions differ from arm A's at 18759 return indices (18759 from its first weight), per close year {2016: 1428, 2017: 2115, 2018: 1401, 2019: 1902, 2020: 2042, 2021: 1958, 2022: 1757, 2023: 2058, 2024: 1871, 2025: 1832, 2026: 395}
  turnover 145.97954113038912: -0.14 % against arm A's, -7.40 % against trial 58's arm B's; its leg's own 14.2105, its ten EUR legs' 131.7690
  shortfall at 178 return indices, per close year {2016: 1, 2017: 9, 2018: 23, 2019: 4, 2020: 30, 2021: 30, 2022: 26, 2023: 9, 2024: 16, 2025: 6, 2026: 24}; mean where short 4.3027e-18, max 1.3877787807814457e-17, mean over the window 0.000000
  carry at 0.0002: summed 2.905661822261152e-19; 0.0000 % a year over the window, 0.0000 % a year from its first weight; per close year {2016: 0.0, 2017: 0.0, 2018: 0.0, 2019: 0.0, 2020: 0.0, 2021: 0.0, 2022: 0.0, 2023: 0.0, 2024: 0.0, 2025: 0.0, 2026: 0.0}
  limits engaged {'gross': 0, 'net': 0, 'margin': 0}, bars scaled 0; max per-base gross 0.998300
SOL/BTC carried: held at 5682 return indices, per close year {2021: 764, 2022: 920, 2023: 1401, 2024: 1240, 2025: 1072, 2026: 285}; mean position where held 0.028100, max 0.132659
  positions differ from arm A's at 9142 return indices (9142 from its first weight), per close year {2021: 934, 2022: 1867, 2023: 2100, 2024: 1964, 2025: 1880, 2026: 397}
  turnover 147.95819177005933: 1.21 % against arm A's, -6.15 % against trial 58's arm B's; its leg's own 6.7278, its ten EUR legs' 141.2304
  shortfall at 2566 return indices, per close year {2021: 330, 2022: 591, 2023: 370, 2024: 620, 2025: 482, 2026: 173}; mean where short 0.0251643, max 0.10454328164090534, mean over the window 0.002362
  carry at 0.0002: summed 0.013392107217049264; 0.1073 % a year over the window, 0.2859 % a year from its first weight; per close year {2021: 0.001128, 2022: 0.003365, 2023: 0.001298, 2024: 0.004224, 2025: 0.002188, 2026: 0.00119}
  limits engaged {'gross': 0, 'net': 0, 'margin': 0}, bars scaled 0; max per-base gross 0.998300
SOL/BTC no_borrow: held at 4104 return indices, per close year {2021: 514, 2022: 566, 2023: 1104, 2024: 981, 2025: 705, 2026: 234}; mean position where held 0.023171, max 0.114247
  positions differ from arm A's at 8877 return indices (8877 from its first weight), per close year {2021: 891, 2022: 1830, 2023: 2058, 2024: 1871, 2025: 1832, 2026: 395}
  turnover 146.4464868776143: 0.18 % against arm A's, -7.11 % against trial 58's arm B's; its leg's own 5.2161, its ten EUR legs' 141.2304
  shortfall at 46 return indices, per close year {2021: 3, 2022: 14, 2023: 1, 2024: 14, 2025: 6, 2026: 8}; mean where short 3.3186e-18, max 6.938893903907228e-18, mean over the window 0.000000
  carry at 0.0002: summed 5.950101522600449e-20; 0.0000 % a year over the window, 0.0000 % a year from its first weight; per close year {2021: 0.0, 2022: 0.0, 2023: 0.0, 2024: 0.0, 2025: 0.0, 2026: 0.0}
  limits engaged {'gross': 0, 'net': 0, 'margin': 0}, bars scaled 0; max per-base gross 0.998300
trial 58's carry summed 0.08313589330184927 ; by leg, pro rata to their positions at each bar {'ETH/BTC': '0.06755582258742332', 'SOL/BTC': '0.015580070714425956'} ; the two summed 0.08313589330184927
end 2026-10-24T09:14:26+00:00
```

What they establish:

- **The block is record 58's**: `compute_hash` `9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df`, 12 files of `ohlc-full` — the ten EUR 4h files and the two legs' — 205,917 rows, 2013-09-10 20:00 → 2026-03-31 20:00, `vouched_status` `checked (36 vouched hashes)`: the reading reads trial 58's files through trial 58's reads (D2).
- **The first weights.** Each leg enters its own book's inverse-vol path where it entered trial 58's twelve-instrument path: ETH/BTC at return index 5,442 (close 2016-04-02 08:00), SOL/BTC at 17,079 (close 2021-07-26 00:00), 21,895 and 10,258 return indices before the window's end; its first non-zero position at 5,612 and 17,115, trial 58's ensemble's.
- **The spans.** Each leg's two books are arm A's bit for bit until their leg's first weight and differ from it at that index, 5,442 for ETH/BTC's and 17,079 for SOL/BTC's; ETH/BTC's two are trial 58's arm B and twin bit for bit, on their eleven instruments, until SOL/BTC's first weight and differ at 17,079, trial 58's SOL/BTC position 0.0 before it. So ETH/BTC alone is trial 58's arm B on 11,637 of its 21,895 primary returns.
- **The limits** engage on no bar of any of the four books, each coming out of them bit-identical at a largest per-base gross of 0.9983, as trial 58's two did.
- **The holding.** Alone and carried, ETH/BTC holds a position at 11,397 return indices — trial 58's count in every close year — at a mean 0.0499 of NAV where held (trial 58's 0.0480) and at most 0.2696, and SOL/BTC at 5,682 — trial 58's count — at a mean 0.0281 (0.0255) and at most 0.1327: alone, each takes the basket weight the other took in trial 58. Held to the book's own BTC, ETH/BTC holds at 7,981 return indices, at a mean 0.0302, and SOL/BTC at 4,104, at a mean 0.0232; D7's floor, 2,190, admits all four.
- **The BTC shortfall and its carry.** Carried, ETH/BTC's book borrows BTC at 7,158 return indices, a mean 0.0457 of NAV where short and at most 0.2696, its carry 0.067538 summed — 0.5411 % of NAV a year over the window, 0.6755 % a year from its first weight; SOL/BTC's at 2,566, a mean 0.0252 and at most 0.1045, its carry 0.013392 — 0.1073 % and 0.2859 %. Held to the book's BTC, the twins' shortfall is float rounding — at most 1.39e-17, at 178 return indices for ETH/BTC's and 46 for SOL/BTC's — and their carry 2.9e-19 and 6.0e-20 summed; D6's keys count those stamps as the code computes them.
- **The turnover**, against arm A's 146.18534602048504 and trial 58's arm B's 157.64827493713167: ETH/BTC carried 156.66817821488746 (+7.17 % and −0.62 %), its leg's own 24.90; ETH/BTC held to the BTC 145.97954113038912 (−0.14 %, −7.40 %), its leg's 14.21; SOL/BTC carried 147.95819177005933 (+1.21 %, −6.15 %), its leg's 6.73; SOL/BTC held to the BTC 146.4464868776143 (+0.18 %, −7.11 %), its leg's 5.22. The ten EUR legs trade 131.77 beside ETH/BTC alone and 141.23 beside SOL/BTC alone, against trial 58's 127.66.
- **Trial 58 by leg (D5).** Its carry, 0.08313589330184927 summed, apportioned to its legs pro rata to their positions at each bar, falls 0.06755582258742332 to ETH/BTC and 0.015580070714425956 to SOL/BTC, the two summing to it; its legs' own turnover is 23.912564023957138 and 6.077390770007466, its ten EUR legs' 127.65832014316521.

**The inputs half** is the reading's data-gated case, `tests/test_research_b4_leg_reading_basis.py` (the plan's Task 2), run on the authoring tree: `1 passed`, a call of 359.69 s — the reading's own `_b4_reads` and `_b4_leg_inputs` over the real set and its `_b4_leg_engagement`, held to the two programs' figures; trial 58's engagement, `_b4_engagement` of the reading's trial books, held to record 58's twelve stored engagement keys to the bit, and arm A's and arm B's turnover to record 58's `turnover_a` and `turnover_b`.

**The computes half**, a third program: the reading's whole compute — the four cells' nets and head-to-heads, the cost layers and theirs, the Sharpe ratios, drawdowns and per-year means and the engagement (`_b4_leg_metrics`, D4–D6) — over synthetic inputs of its size, the ten EUR assets' and the two legs' random returns over 27,337 return indices and random long positions, each leg held from its first weight on the real set:

```python
import random
import resource
import time
from datetime import UTC, datetime, timedelta

from cli.research import subjects

rng = random.Random(42)
n = 27_337
h4_ts = [datetime(2013, 9, 10, 20, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n + 1)]
first = {"ETH/BTC": 5_442, "SOL/BTC": 17_079}
assets = subjects._ASSETS
returns = {i: [rng.gauss(0.0002, 0.02) for _ in range(n)] for i in (*assets, *first)}
arm_a = {a: [max(0.0, rng.gauss(0.05, 0.05)) for _ in range(n)] for a in assets}
legs = {leg: [0.0 if k < first[leg] else max(0.0, rng.gauss(0.03, 0.05)) for k in range(n)] for leg in first}
arm_b = arm_a | legs
flags = {limit: [False] * n for limit in ("gross", "net", "margin")}
trial = subjects._B4Inputs(h4_ts, {"BTC": [100.0] * (n + 1)}, h4_ts[1:], returns, first, arm_a, arm_b, arm_b, flags, flags)
books = {leg: {"carried": arm_a | {leg: legs[leg]}, "no_borrow": arm_a | {leg: [0.5 * p for p in legs[leg]]}} for leg in first}
engaged = {leg: {"carried": flags, "no_borrow": flags} for leg in first}
inputs = subjects._B4LegInputs(trial, first, books, engaged)
built = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
start = time.perf_counter()
metrics = subjects._b4_leg_metrics(inputs)
elapsed, peak = time.perf_counter() - start, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(f"computes half, {n} synthetic returns: {elapsed:.1f} s, peak RSS {peak:.0f} MiB, {built:.0f} MiB with the inputs built; {len(metrics)} keys")
```

Its output, whole:

```text
computes half, 27337 synthetic returns: 49.6 s, peak RSS 2182 MiB, 100 MiB with the inputs built; 31 keys
```

- **The run's time**: the inputs half's 359.69 s and the computes half's 49.6 s, about 410 s — seven minutes — in one process, peaking at 2,182 MiB in the computes half on a workstation of 62 GiB.

**The name and the count**, a fourth program, run with the subject registered in the authoring tree, and a one-line count over the trial-attempts log, read and never written:

```python
from cli.research.subjects import SUBJECTS
from tests.retired_subjects import RETIRED_SUBJECTS

name = "b4-leg-reading"
others = (set(SUBJECTS) | RETIRED_SUBJECTS) - {name}
print("registered", name in SUBJECTS, "; names it equals or opens with a hyphen:", sorted(o for o in others if name == o or name.startswith(f"{o}-")))
print("names opening with it and a hyphen:", sorted(o for o in others if o.startswith(f"{name}-")))
print("names opening b4:", sorted(o for o in others if o.startswith("b4")))
```

```text
registered True ; names it equals or opens with a hyphen: []
names opening with it and a hyphen: []
names opening b4: ['b4-ratio-legs', 'b4-ratio-legs-preflight']
```

```text
$ uv run python -c 'import json; from pathlib import Path; from datetime import UTC, datetime; from cli.registry import attempts, budget; print("read at", datetime.now(UTC).isoformat(timespec="seconds")); lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans]); print("open attempts:", sorted({x["attempt"] for x in lines if x["kind"] == "begin"} - {x["attempt"] for x in lines if x["kind"] == "end"}))'
read at 2026-10-24T09:32:37+00:00
{'B1': 5, 'B2': 7, 'B4': 1} remain 12 []
open attempts: []
```

- **The name**: no registered or retired subject's name equals `b4-leg-reading` or opens it with a hyphen, and it opens none (D2); the names opening `b4` are trial 58's two, both retired.
- **The count**: bucket B has spent 13 of 25 — B1 5, B2 7, B4 1 — and 12 remain, with no orphan and no open attempt; the reading spends none (D2).

Spec 00144 frozen, and trial 58's code path since record 58's run:

```text
$ sha256sum docs/specs/00144-b4-ratio-legs-design.md; python3 -c 'import json; r = json.loads(open("docs/reference/trial-registry.jsonl").read().splitlines()[57]); print("record", r["trial_id"], r["spec_hash"], r["invocation"]["commit"])'
f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89  docs/specs/00144-b4-ratio-legs-design.md
record 58 f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89 93c0ec7af12323c3cda294481854e9cf878802d6
$ git log --oneline 93c0ec7af12323c3cda294481854e9cf878802d6..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat
```

- **Spec 00144 is frozen**: its sha256 is record 58's `spec_hash`; it is not edited.
- **Trial 58's code path since record 58's run** at `93c0ec7af`: the log prints nothing — no commit has touched it, so the books the reading builds are record 58's, as the data-gated case holds to the bit.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this reading runs under one, the session holding this branch's worktree, `.claude/worktrees/iter190`, on the workstation `zcrypto-ops`. No other session appends to `docs/reference/reading-ledger.jsonl` while this branch is open, and B4 has no other subject to run.
- **The process.** The reading is one `uv run zcrypto research eval` process in this worktree, awaited to its exit — no daemon, timer or concurrent run, and no step reads it as ended while its process lives. It reads `data/ohlc-full`, a symlink to the main checkout's frozen, attested set; it writes nothing under it, makes no network call, and nothing it reads has a live writer.
- **No trial-attempts log.** A subject with no rule registers no trial: `--reading` begins no attempt and its line carries `attempt` `null`, as readings 2–5 do; the trial-attempts log and bucket B's budget are untouched.
- **The reading ledger** — tracked, append-only, hash-chained; this worktree is its one writer while the branch is open. `--reading` refuses a tree with uncommitted changes, so the run's line is committed with its decisions-log entry before anything else lands (D8).

## The question (no hypothesis, no bar)

Trial 1 added both ratio legs to the A2 ensemble at once and recorded one book: it lost to arm A from the first ratio weight, and its borrow-unavailable twin lost less, at a net Sharpe above arm A's. It recorded neither which leg the loss came from nor whether the legs lost gross or through the trades they add and the BTC they borrow. This reading asks both: **does either leg alone, as trial 58 costed arm B or held to the book's own BTC, have a higher mean net-of-cost return than arm A from the close it first takes basket weight; and how does trial 58's head-to-head part among its gross, its trading cost and its carry?** A cell that clears the potential criterion (D7) names the trial it would justify; none clearing it is the evidence the owner's B4 family call reads. The reading tests no hypothesis, has no bar, matrix or verdict, spends no B slot, and changes no verdict of trial 58.

## D1 — the pick: a no-slot reading of trial 58's books by leg and by cost

- **The loop's pick (Decision: 1 of the `[iter-190]` pick entry)**, under the owner's run instruction, among four:
  1. **A no-slot reading of trial 58's books by leg and by cost** — each leg alone on the A2 ensemble, as trial 58 costed it and as its borrow-free twin, and trial 58's arm B taken apart into its gross, its trading cost and its carry; it screens the untried variants before a slot is spent, as iter-186 did for B2, and spends none of bucket B's 12. Chosen.
  2. **Trial 2 on ETH/BTC alone** — the author's park variant of spec 00144; one slot, with no evidence that ETH/BTC carries what trial 1 lost.
  3. **Trial 2 on the symmetric legs** — short the pairs as well, at an ETH or SOL borrow of 0.0004 per 4h (about 88 % a year) on any shortfall, where trial 1's BTC carry, `carry_per_year` summed, was 0.0831 of NAV over the window beside its head-to-head of −4.700758514095985e-06/bar from the first ratio weight; one slot.
  4. **Closing B4** — the owner's call, never the loop's.
- The reading closes nothing: whatever it reads, B4 stays open, and a close is the owner's (D7).

## D2 — the instrument and the subject: trial 58's reads of frozen `ohlc-full`, a reading

- **One reading subject**, `b4-leg-reading` in `cli/research/subjects.py`: `spec="docs/specs/00145-b4-leg-reading-design.md"`, `_ASSETS`, intervals `(240,)` — the legs' files are the build's to read and name, as trial 58's are — `metric_keys=_B4_LEG_KEYS` (D6), seeds `(42,)` — the head-to-heads' seed — and no rule, family or count: `--register` refuses it, its plain eval is admitted, and `--reading --iteration iter-190 --spec-hash <H>` keeps its run on `docs/reference/reading-ledger.jsonl`, spec 00142 D2's form. No incumbent: arm A and every book are built in the run.
- **Author's call — the name `b4-leg-reading`**: spec 00141 D2's rule — a name opening with a registered or retired subject's name and a hyphen makes `tests/test_retired_subjects.py`'s case match count the live subject's cases as the other's, unmarked — so no registered or retired name may equal it or open it with a hyphen, and it may open none: measured, and `b4-ratio-legs`, retired, rules out every `b4-ratio-legs-…` name.
- **The instrument ruling's set, through trial 58's reads**: `--dataset ohlc-full`, no `--window`, no `--as-of`; `_b4_reads(subject, reader, dataset, window, accept_holes)` unchanged — the union `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices, its two window refusals, and the two legs' native 4h closes mapped onto the union's stamps by exact stamp (spec 00144 D2) — so the block is record 58's, `9e0fc8e5…82d7df` (measured).
- The reading spends no slot: bucket B's 12 stay 12 (measured).

## D3 — the books: trial 58's three, and each leg's two

- **Trial 58's books**, by its inputs half unchanged: `_b4_inputs(reads)` — arm A `_b4_limited(_b4_ensemble(fed))`, arm B `_b4_limited(_b4_ensemble(fed | ratios))`, the twin `_b4_limited(borrow_unavailable(<arm B's raw positions>, _B4_LEGS, "BTC"))`, the returns every book is costed on (`_asset_returns(fed[a])` for the ten EUR assets, `ratio_eur_returns(ratios[leg], fed["BTC"])` for the legs) and trial 58's first weights, `fed = _ffill_btc(h4_prices)`. They are record 58's (the basis).
- **Each leg alone**: `raw = _b4_ensemble(fed | {leg: ratios[leg]})` — the three adopted A2 arms (`_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year) run on eleven instruments, the ten EUR assets and that leg after them, and their equal-weight mean — and two books of it, its **funding**: `carried`, `_b4_limited(raw)`, as trial 58 costed arm B, the BTC the leg sells netted against the book's own BTC/EUR position and the shortfall borrowed (spec 00144 D5); and `no_borrow`, `_b4_limited(borrow_unavailable(raw, _B4_LEGS, "BTC"))`, the leg scaled each bar to the book's own BTC as trial 58's twin was (spec 00144 D7). Both pass §10's limits as one factor per bar (spec 00144 D6). The four cells: ETH/BTC carried, ETH/BTC no-borrow, SOL/BTC carried and SOL/BTC no-borrow.
- **The costing**, trial 58's: every book costed by `_b4_net(book, returns, stress=1.0)` — `net_of_cost` at 0.006 a side on each instrument's own turnover from flat, a missing return read as 0.0, less `shortfall_carry` of the book's BTC shortfall at 0.0002 per 4h rollover plus the opening charge on each increase. Arm A's net, `net_a`, is record 58's.
- **The first weight** of each leg is read off its own book's weight path, `_inverse_vol_weights(fed | {leg: ratios[leg]}, lookback=180)`, the first return index whose weights hold the leg. **Author's call — the leg's own book's path**: the one path that book's three arms read (spec 00144 D3's form, never a restated predicate), never trial 58's twelve-instrument path; the two agree on this set (measured: 5,442 and 17,079), since whether a leg holds a weight reads its own returns alone.
- **Bit for bit.** Before a leg enters its book's weight path it carries no weight: every other instrument's weight is the same quotient over the same sum in the same order, the leg's term in the base return, `weights[k].get(leg, 0.0) * d * r`, adds a signed zero, so the vol target and every position are arm A's; the limits engage on no such bar, and `borrow_unavailable` scales a leg holding nothing by 1. So **each leg's two books are arm A's bit for bit before the leg's first weight**, the leg's position 0.0. In the same way SOL/BTC holds no weight in trial 58's books before 17,079, so **ETH/BTC's two books are trial 58's arm B and twin bit for bit, on their eleven instruments, before SOL/BTC's first weight**, trial 58's SOL/BTC position 0.0 there. The plan proves both on a fixture and its data-gated case on this set, where the basis measures each first difference at exactly the first weight named.
- **Author's call — the books built by trial 58's own functions**, `_b4_ensemble`, `_b4_limited`, `borrow_unavailable` and `_b4_net`, unchanged, so a cell differs from trial 58's arm B, or from its twin, in the one leg it drops and in nothing else.
- No change to any existing function, `cli/alpha/*`, `cli/risk/*`, `cli/costs/*`, `cli/portfolio/*` or any adopted artifact.

## D4 — the reads per cell

- **The primary head-to-head**: `net_of_cost_verdict(net[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` — `net` the cell's net (D3), `net_a` arm A's, `first` its leg's first weight, 5,442 for ETH/BTC's cells and 17,079 for SOL/BTC's (measured), 21,895 and 10,258 return indices — its mean outperformance and SPA p: trial 58's head-to-head call (spec 00144 D8) from the cell's own first weight.
- **The full-window pair beside it**: the same call from index 0, which adds the zero differences of the closes before the leg's first weight.
- **The net Sharpe and maximum drawdown** of the cell beside arm A's over the same closes — `sharpe` annualised at 2,190 and `max_drawdown` — over the primary window, from the leg's first weight, and over the full window.
- **Per close year, the mean outperformance**: the mean of `net[k] − net_a[k]` over the year's return indices (`per_year_means`), every close year keyed; before the leg's first weight it is 0.0 exactly.
- **No kill bar**, no matrix and no verdict: a reading has none.
- **Refused before any head-to-head**: fewer than 2 return indices from a leg's first weight, a `ValidationError` and so a refused build.

## D5 — the context rows: trial 58's head-to-head by cost, and each leg's share

- **Trial 58's arm B against arm A from its first ratio weight**, 5,442, record 58's primary start, at three cost layers, both books costed alike at each: **gross**, `net_of_cost(book, returns, cost_per_side=0.0)` — no trading cost, no carry; **net of its trading cost alone**, `net_of_cost(book, returns, cost_per_side=0.006)`; and **net of both**, `_b4_net(book, returns, stress=1.0)`, the two series trial 58's head-to-head read. Each layer through `net_of_cost_verdict(b[5442:], a[5442:], mean_block=30, seed=42, n_resamples=2000)`, its mean outperformance and SPA p. Arm A holds no leg and carries nothing, so its last two layers are one series.
- **The last layer is record 58's figure, reproduced to the bit**: the same call on the same two series as record 58's `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`. A head-to-head's mean is the mean of the per-bar differences, so the gross layer's mean less the trading layer's is the mean trading cost arm B pays beyond arm A per bar from 5,442, and the trading layer's less the last's is arm B's mean carry per bar from it, to rounding; the plan's fixture holds both against the per-bar costs written out.
- **Each leg's share of the carry**: trial 58's per-bar carry apportioned to its legs pro rata to their positions at that bar, `carry[k] × p_leg[k] / (p_ETH/BTC[k] + p_SOL/BTC[k])`, summed over the window. **Author's call**: the borrow is one BTC shortfall the two legs share, so a leg's share of a bar's carry is its part of their combined BTC sale at that bar; the shares sum to the carry (measured: 0.067556 and 0.015580 of 0.083136), where each leg's own carry alone, which the cells record, does not.
- **Each leg's share of the turnover**: each leg's own, `book_turnover` of its positions, and the ten EUR legs' together, beside arm A's (measured: 23.9126, 6.0774 and 127.6583, against arm A's 146.1853).
- These rows locate where trial 1 lost; **no criterion reads them**.

## D6 — the keys, the refusals and the build

- **The 31 keys** (`_B4_LEG_KEYS`):
  - per cell, each `{leg: {funding: value}}` over `ETH/BTC` and `SOL/BTC` and `carried` and `no_borrow`: the reads (D4) — `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `mean_outperf_per_year`, `ann_sharpe_noc_primary`, `ann_sharpe_noc_full`, `max_drawdown_primary`, `max_drawdown_full`; and the engagement, from positions alone — `held_per_year` (the leg's non-zero positions per close year), `positions_differ_per_year` (against arm A's, the leg at 0.0), `turnover`, `shortfall_stamps_per_year` and `shortfall_mean_per_year` (the book's BTC shortfall), `carry_per_year` (summed at 0.0002) and `limit_engaged` (per limit, the engaged bars' total);
  - per leg, `{leg: value}`: `first_weight`, `primary_returns`, `arm_a_ann_sharpe_noc_primary` and `arm_a_max_drawdown_primary`;
  - arm A's and trial 58's, recomputed: `arm_a_ann_sharpe_noc_full`, `arm_a_max_drawdown_full`, `turnover_a` and `turnover_b`, record 58's `arm_a_ann_sharpe_noc`, `arm_a_max_drawdown`, `turnover_a` and `turnover_b`;
  - the context (D5): `context_head_to_head_mean_outperf` and `context_head_to_head_spa_p`, each over `gross`, `net_of_trading` and `net`; `context_carry_by_leg`; and `context_turnover_by_leg`, over `ETH/BTC`, `SOL/BTC` and `EUR`;
  - the constants `mean_block` 30, `seed` 42 and `n_resamples` 2000.
  Every year key is a close year (`close_grid`), every year the closes span keyed.
- **Author's call — the cells nested by leg and funding**, not 64 flat keys: a cell is a (leg, funding) pair, and every per-cell key holds the four cells in one shape; the engagement is computed from positions alone (`_b4_leg_engagement`), so the data-gated case holds it before the hash. **Author's call — the twins' shortfall counted as the code computes it**: it is float rounding (the basis: at most 1.39e-17), and `shortfall_stamps_per_year` counts those stamps as trial 58's code counts its own; a tolerance would be a second definition of the shortfall.
- **Refusals**: `--as-of`, before any read — "b4-leg-reading evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset"; `_b4_reads`' two window refusals and a leg's file it cannot read (`<dataset>/<leg>/240.parquet: …`), unchanged, the first two naming this subject; fewer than 2 return indices from a leg's first weight (D4); and any compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `RiskError`, `ValidationError` — a `SubjectError` naming the subject over its window. The plain eval is admitted.
- **The build in halves**: the inputs, `_b4_leg_inputs(reads)` → `_B4LegInputs(trial, first_weight, books, engaged)`, `trial` D3's `_b4_inputs(reads)` and `books` and `engaged` each `{leg: {funding: …}}`, positions and no return of a book — the half the data-gated case runs; the computes, `_b4_leg_metrics(inputs)` — arm A's net, per cell its net, its two head-to-heads and its Sharpe, drawdown and per-year reads, the cost layers (`_b4_cost_layers`) and their three head-to-heads, the engagement (`_b4_leg_engagement`) and the constants; `_build_b4_leg_reading` refuses `--as-of` and wraps both.
- **The files the build touches, a closed list**: `cli/research/subjects.py` — `_B4LegInputs`, `_b4_leg_inputs`, `_b4_leg_engagement`, `_b4_cost_layers`, `_b4_leg_metrics`, `_build_b4_leg_reading` and `_B4_LEG_KEYS` in one block before `SUBJECTS`, and one `SUBJECTS` entry, no import added and no existing function changed; `README.md`'s `--subject` row; the tests the plan names; after the run, `tests/retired_subjects.py`. No change to `cli/alpha/*`, `cli/risk/*`, `cli/costs/*`, `cli/registry/*`, `cli/portfolio/*`, `cli/engine/*`, trial 58's subjects, specs 00141, 00142 and 00144, record 58 or any adopted artifact.

## D7 — the pre-registered potential criterion, the contamination, and what the reading changes

- **The criterion**, spec 00141 D8's form — a floor and then legs — fixed by this spec's sha256 before any return of a book is read, read by the closeout's pick and never by code: the subject has no rule. **The floor, read before any leg**: the cell's leg holds a non-zero position at 2,190 return indices or more, `held_per_year` summed. **Author's call — the floor at 2,190**: an SPA p over a difference series that moves where the leg moves the book reads few episodes where the leg is held at few closes, and 2,190 is one year of 4h closes, the span of each calendar-year slice the family's kill bar reads; on this set it admits all four cells (the basis: 11,397, 7,981, 5,682 and 4,104), so it decides none here and is fixed before the run as any floor is. A cell under the floor is **unread**: no leg is read of it, and it has no potential. A cell the floor admits has **potential** only if all three legs hold, each read unrounded off its stored keys:
  1. its primary mean outperformance, `head_to_head_mean_outperf_primary`, is above 0;
  2. its primary SPA p, `head_to_head_spa_p_primary`, is below 0.05/4 = 0.0125 — Bonferroni over the four cells at 5 %;
  3. its maximum drawdown from its leg's first weight, `max_drawdown_primary`, is not above arm A's over the same closes, `arm_a_max_drawdown_primary`.
- **Author's call — the drawdown leg over the primary window**: the head-to-head's own window; before the leg's first weight the two books are one, so a full-window drawdown can be arm A's own drawdown from before the leg took weight. **Author's call — Bonferroni over the four cells, though they are not independent** — each leg's two fundings share every bar at which the book's BTC covers the leg, and ETH/BTC alone is trial 58's arm B on 11,637 of its 21,895 primary returns: the count is the design's, fixed before the run, and over correlated cells it is conservative.
- **A cell with potential names the trial a later spec would pre-register**: that leg alone on the A2 ensemble at that funding — carried, its BTC shortfall borrowed at 0.0002 per 4h, or held to the book's own BTC — judged by record 58's bar and its head-to-head from the leg's first weight. It differs from trial 58 in holding one leg, not two, and at the borrow-free funding in sizing the leg to the book's own BTC where trial 58 borrowed the rest; the later spec states how and cites record 58 and this reading. **None with potential** is the evidence the owner's B4 family call — hold or close B4 — reads, beside record 58; the reading closes nothing (D1).
- **The contamination, in full**: the reading reads trial 58's own instrument and books — the frozen union, its arm A, its legs, its costing, its carry, its limits and its twin — and its cells are the data any trial it justifies would be judged on. It was designed with trial 58's result known: arm B lost to arm A from the first ratio weight, and its twin lost less at a net Sharpe above arm A's; the cells were chosen because trial 58 recorded the two legs as one book, and the borrow-free funding because its twin's Sharpe was the one figure of trial 58 above arm A's. The cells are no independent looks: ETH/BTC alone is trial 58's arm B bit for bit on 11,637 of its 21,895 primary returns (D3), so its head-to-head shares more than half its differences with trial 58's, which lost; and each leg's two fundings share every bar at which the book's BTC covers the leg. The context rows add little to record 58: a head-to-head's mean is linear in the per-bar differences, so the layers' means follow from record 58's stored net head-to-head, turnover and carry — arithmetic this spec does not do before its hash — and what the run adds is each layer's SPA p and the reproduction. The correction is over this reading's four cells, not over B4's five looks, record 58 and the four; a trial it justifies is designed from this data, and its spec says so, carries this reading's id beside record 58's, and counts the family's true trials in its DSR — B4's landed record and the one it adds, this reading's four looks included in its design.
- **What it changes**: no verdict of trial 58, no B slot, no record; its figures go to T0016's findings beside its decisions-log entry, and B4's next step after it — the pick reading this criterion, the loop's under a run instruction and else the owner's, a close the owner's — is T0016's B4 arm, rewritten to wait on a `[iter-NNN] B4's next step after the leg reading` entry.

## D8 — the run

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00145-b4-leg-reading-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append; (3) the data-gated basis test on the run's tree; (4) the one run, `uv run zcrypto research eval --subject b4-leg-reading --dataset ohlc-full --reading --iteration iter-190 --spec-hash <(1)> --notes "<written before the run>"`, no plain eval before or after it; (5) the ledger line's checks — its block, record 58's figures reproduced (the net layer's pair to the bit, arm A's full-window Sharpe and drawdown, both turnovers) and the engagement the basis's — its replay, and its commit with the decisions-log entry naming `(reading <N>)`; (6) the subject retired.
- **The hash rule**: before (1), nobody reads or computes any cell's returns or net-of-cost series, any head-to-head, or the context rows' gross or cost split — by the reading's code, by a program, or by D7's arithmetic over record 58's stored figures — nor runs `b4-leg-reading` over the real set; positions, weights, exposures, the shortfall, the carry it implies, limit engagement and turnover are allowed, and are what the basis and the data-gated case hold. `a2_book_returns` computes each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; no program reads any of them (spec 00144 D10's words). The reading's computes half runs before the hash over synthetic inputs alone.
- **The notes, written before the run**: the subject over `ohlc-full`, full history; that it is descriptive, with no bar, verdict or slot, changing no verdict of trial 58; trial 58's books and the four cells — each leg alone beside the ten EUR assets, carried and held to the book's own BTC — with their costing; the reads, the cost layers and the shares; the potential criterion pre-registered by this spec's sha256.
- A refused build keeps no reading; T0016 records it with its line quoted, and the reading's design stands unrun.

## Out of scope

Any trial — a leg alone, the symmetric legs, a further leg or pair, the legs' own vol target or weight cap; a kill bar over a cell; a rule over the reading's figures; a correction over B4's five looks; any other funding — the legs as full margin positions, an ETH or SOL borrow; a reading at another window, on `ohlc-rolling` or at a later as-of; the legs on the live path; bucket B's B3 and the C families, T0016's; any change to an existing function, subject, record or reading.
