# B3 trial 2 — the rank tilt of the A2-4h ensemble's long weights on a 540-close momentum score, on the frozen `ohlc-full` set

**Ruling:** the owner, attended, 2026-10-25, after B3 trial 1's REJECT (registry trial 60), asked B3's next step with three options — 1 a park variant (the tilt at another `M` or `k`), 2 the A1-short BTC overlay (master plan §5's B3 whole), 3 closing B3 — said, verbatim: "let's wait for the round-23 review and PR first. after its PR merge, sequentially Option 1 -> 2 -> 3". Read as: trial 2 the park variant, then trial 3 the overlay, then B3 closed, in that order whatever trial 2's verdict; the round-23 PR merged into develop as `22c220677`, this branch's base. The words stand in the decisions log as the entry `[iter-193] B3's next step after trial 1 — the owner's word of 2026-10-25: the tilt at another M or k, then the A1-short overlay, then B3 closed (Decision: 1)`, the heading T0016's B3 arm checks for; the variant — which `M` or `k` — is the loop's pick under that word (D1), recorded beside it as `[iter-193] B3 trial 2's variant — the tilt on a 540-close score, its strength and floor trial 1's, the loop's pick under the owner's word (Decision: 1)`, with the conventions entry, before this spec's hash. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" (the `[iter-181] B2 instrument ruling` entry); the two `[iter-176]` rulings binding every B and C pre-registration, the DSR leg binding at `var_trials` 0.0 and the spent holdout's window never reported as holdout evidence (this set ends 2026-03-31, before it); and the owner's family pick "B3 (Recommended)" under which B3 is worked. Every call past those words and past what specs 00128, 00133, 00137, 00144 and 00147 fix is the loop's, marked **The loop's call** where the loop's controller made it and **Author's call** where this spec's author did. **Iteration:** iter-193, branch `research/iter-193-b3-tilt-slow`. **Topic:** T0016, its B3 arm. **Goal:** pre-register B3's second trial — trial 1's tilt of the adopted A2-4h ensemble's long weights by their rank in the whole basket, its strength `k` = 0.5 and its 8-asset floor unchanged, on the trailing 540-close (90-day) simple return in place of the 180-close one — as numbered decisions with code-level definitions: one committed research subject with its evaluate-only pre-flight twin, both reading trial 1's halves where those take no score window and a block of their own in trial 1's form where they do, registered through `zcrypto research eval --register` and spec 00133's trial-attempts log at B3's count 2. Spec 00147 is this spec's form and its arm A, tilt, costing, limits, bar, matrix and rule, frozen by record 60's `spec_hash`; spec 00146 the form of a family's second trial — its count, the contamination stated against the first trial's result. The landed record spends one trial of Bucket B's shared budget: 10 remain today, 9 after.

## The measured basis

Every figure below was measured on 2026-10-25 in this branch's worktree at develop's `22c220677`, with the trial's code absent — the books program in three parts between 16:29:36Z and 16:35:06Z, the cells program at 16:35:39Z, the count program at 16:36:14Z, the shell checks at 16:36:37Z — with `data/ohlc-full` symlinked read-only from the main checkout's `data/` and the main checkout's `.local/trial-attempts.jsonl` read, never written. They read closes, weights, ranks, positions, limit engagement and turnover only: no return of trial 2's arm B is read — no net-of-cost series, head-to-head or bar leg — and neither subject runs over the real set. The books program's own book function computes each tilted arm's base returns on its way to the positions, since the vol target sizes on them, reads them nowhere else and never calls `run_backtest`, so no tilted arm's return series exists in it; `a2_book_returns`, which it calls for the untilted check, and `_b4_ensemble`, which builds arm A, compute arm A's internally, unread. Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

**The books**, a first program run in three parts — `arms` reading the union the way the subject reads it, arm A by trial 58's own `_b4_ensemble` and each arm's book untilted by the program's own expression of `a2_book_returns`; `540` each arm's book tilted on the 540-close score; `180` the same on trial 1's 180-close score, so that the program's books can be held to record 60's — the tilt written out, never through the trial's code or `cli/alpha/b3.py`, the books kept under `.tmp/` for the second:

```python
import json
import math
import pickle
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.alpha.a2 import _asset_directions_a2
from cli.benchmark.strategies import vol_target
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

part = sys.argv[1]
K, FLOOR = 0.5, 8  # trial 1's values, unchanged; M is the part's: 540 for trial 2, 180 to tie the program to record 60
print("start", part, datetime.now(UTC).isoformat(timespec="seconds"))
reader = ObservedReader(Path("data"))
t0 = time.perf_counter()
h4_ts, h4_prices = subjects._capturing_union(reader, "ohlc-full", 240, None, None, False)
n = len(h4_ts) - 1
print(f"reads {time.perf_counter() - t0:.1f} s; union {len(h4_ts)} stamps, {h4_ts[0]} -> {h4_ts[-1]}, return indices {n}")
fed = _ffill_btc(h4_prices)
configs = [
    A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lb, tv in subjects._B2_A2_ARMS
]
labels = [f"{'-'.join(map(str, c.lookbacks))}@{c.target_vol}" for c in configs]


def scores(m):
    return {a: [None if k < m or p[k] is None or p[k - m] is None else p[k] / p[k - m] - 1 for k in range(n)] for a, p in fed.items()}


def tilt(w, d, s):
    """The tilt at one close, written out here, never through the trial's code: the basket ranked, the longs tilted."""
    basket = [a for a in w if w[a] > 0 and s[a] is not None]
    m = len(basket)
    if m < FLOOR:
        return w, m, 0
    longs = [a for a in basket if d[a] is not None and d[a] > 0]
    if len(longs) < 2:
        return w, m, 0
    order = sorted(basket, key=lambda a: s[a])
    rank, i = {}, 0
    while i < m:
        j = i
        while j + 1 < m and s[order[j + 1]] == s[order[i]]:
            j += 1
        for a in order[i : j + 1]:
            rank[a] = (i + j + 2) / 2
        i = j + 1
    z = {a: (2 * rank[a] - (m + 1)) / (m - 1) for a in basket}
    raw = {a: w[a] * (1 + K * z[a]) for a in longs}
    scale = math.fsum(w[a] for a in longs) / math.fsum(raw.values())
    return w | {a: raw[a] * scale for a in longs}, m, len(longs)


def book(prices, config, score):
    """`a2_book_returns`' positions, its weights tilted at each close by `score` unless it is None; the base returns size
    the vol target and are not read."""
    length = len(prices["BTC"])
    union_ts = list(range(length))
    asset_ts = {a: [k for k, p in enumerate(v) if p is not None] for a, v in prices.items()}
    directions = _asset_directions_a2(prices, union_ts, asset_ts, config=config)
    returns = {a: _asset_returns(v) for a, v in prices.items()}
    w = _inverse_vol_weights(prices, lookback=config.basket_lookback)
    baskets, longs, ratios, unscored = [], [], [], [0] * (length - 1)
    if score is not None:
        out = []
        for k in range(length - 1):
            d = {a: directions[a][k] for a in prices}
            unscored[k] = sum(1 for a in w[k] if w[k][a] > 0 and score[a][k] is None)
            tw, m, t = tilt(w[k], d, {a: score[a][k] for a in prices})
            ratios.extend(tw[a] / w[k][a] for a in w[k] if tw[a] != w[k][a])
            out.append(tw)
            baskets.append(m)
            longs.append(t)
        w = out
    base = []
    for k in range(length - 1):
        total = 0.0
        for a in prices:
            r, d = returns[a][k], directions[a][k]
            if r is None or d is None:
                continue
            total += w[k].get(a, 0.0) * d * r
        base.append(total)
    sized = vol_target(
        base,
        target_vol=config.target_vol / math.sqrt(config.periods_per_year),
        lookback=config.vol_lookback,
        max_leverage=config.max_leverage,
    )
    positions = {a: [w[k].get(a, 0.0) * (directions[a][k] or 0.0) * sized[k] for k in range(length - 1)] for a in prices}
    return positions, baskets, longs, (min(ratios), max(ratios)) if ratios else None, unscored


books = {"h4_ts": h4_ts, "labels": labels}
if part == "arms":
    block = reader.block()
    print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in block.items()})
    print("vouched", reader.vouched_status(), "holes", reader.holes())
    record_58 = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[57])
    eur_58 = {p: h for p, h in record_58["datasets"]["ohlc-full"]["files"].items() if "/EUR/" in p}
    print("the block's files are record 58's ten EUR files, and no other:", block["ohlc-full"]["files"] == eur_58)
    t1 = time.perf_counter()
    books["arm_a"] = subjects._b4_ensemble(fed)
    t2 = time.perf_counter()
    print(f"arm A, _b4_ensemble's three A2 runs, {t2 - t1:.1f} s")
    plain = [book(fed, c, None)[0] for c in configs]
    t3 = time.perf_counter()
    print(f"the program's book untilted, three arms, {t3 - t2:.1f} s")
    print("  each arm's untilted book is a2_book_returns' asset_positions bit for bit:", [p == a2_book_returns(fed, config=c)["asset_positions"] for p, c in zip(plain, configs)])
    books["arms_a"] = plain
else:
    m = int(part)
    t4 = time.perf_counter()
    tilted = [book(fed, c, scores(m)) for c in configs]
    print(f"the program's book tilted at M = {m}, three arms, {time.perf_counter() - t4:.1f} s")
    books["arms_b"] = [t[0] for t in tilted]
    books["baskets"] = {label: t[1] for label, t in zip(labels, tilted)}
    books["longs"] = {label: t[2] for label, t in zip(labels, tilted)}
    books["unscored"] = tilted[0][4]
    for label, t in zip(labels, tilted):
        print(f"  {label}: the tilted weight over the untilted, where it moved, min {t[3][0]!r} max {t[3][1]!r}; weighted assets with no score, summed over the closes, {sum(t[4])}")
    print("the three arms' basket sizes are one list:", books["baskets"][labels[0]] == books["baskets"][labels[1]] == books["baskets"][labels[2]])
Path(f".tmp/iter193/basis/books-{part}.pickle").write_bytes(pickle.dumps(books))
print("end", part, datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole, the parts `arms`, `540` and `180` in turn, uv's five lines creating the worktree's environment opening the first:

```text
Using CPython 3.14.6
Creating virtual environment at: .venv
   Building zcrypto @ file:///home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter193
      Built zcrypto @ file:///home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter193
Installed 65 packages in 196ms
start arms 2026-10-25T16:29:36+00:00
reads 0.4 s; union 27338 stamps, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00, return indices 27337
block ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69 {'ohlc-full': (10, 173373, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)'} holes {}
the block's files are record 58's ten EUR files, and no other: True
arm A, _b4_ensemble's three A2 runs, 64.4 s
the program's book untilted, three arms, 63.3 s
  each arm's untilted book is a2_book_returns' asset_positions bit for bit: [True, True, True]
end arms 2026-10-25T16:32:49+00:00
start 540 2026-10-25T16:32:53+00:00
reads 0.4 s; union 27338 stamps, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00, return indices 27337
the program's book tilted at M = 540, three arms, 64.1 s
  20-50-100@0.12: the tilted weight over the untilted, where it moved, min 0.41324879947753973 max 1.8708552615131389; weighted assets with no score, summed over the closes, 2660
  60-120-240@0.1: the tilted weight over the untilted, where it moved, min 0.42076089875454836 max 1.8495832865619153; weighted assets with no score, summed over the closes, 2660
  60-120-240@0.12: the tilted weight over the untilted, where it moved, min 0.42076089875454836 max 1.8495832865619153; weighted assets with no score, summed over the closes, 2660
the three arms' basket sizes are one list: True
end 540 2026-10-25T16:33:57+00:00
start 180 2026-10-25T16:34:01+00:00
reads 0.4 s; union 27338 stamps, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00, return indices 27337
the program's book tilted at M = 180, three arms, 64.1 s
  20-50-100@0.12: the tilted weight over the untilted, where it moved, min 0.4152870051510151 max 1.8333902574501726; weighted assets with no score, summed over the closes, 0
  60-120-240@0.1: the tilted weight over the untilted, where it moved, min 0.3988876385150849 max 1.7981735434348523; weighted assets with no score, summed over the closes, 0
  60-120-240@0.12: the tilted weight over the untilted, where it moved, min 0.3988876385150849 max 1.7981735434348523; weighted assets with no score, summed over the closes, 0
the three arms' basket sizes are one list: True
end 180 2026-10-25T16:35:06+00:00
```

**The cells**, a second program over the first's books — arm A against record 58's, the program's trial-1 books against record 60's stored engagement, then trial 2's: the limits, the basket per close, the tilted closes per arm, the first engagement, the closes where the books differ and turnover, written out with `cli/alpha/b4.py`'s limit functions, never through the trial's code:

```python
import json
import math
import pickle
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import close_grid
from cli.alpha.b4 import base_exposures, limit_factors, scale_bars

print("start", datetime.now(UTC).isoformat(timespec="seconds"))
arms = pickle.loads(Path(".tmp/iter193/basis/books-arms.pickle").read_bytes())
b540 = pickle.loads(Path(".tmp/iter193/basis/books-540.pickle").read_bytes())
b180 = pickle.loads(Path(".tmp/iter193/basis/books-180.pickle").read_bytes())
h4_ts, labels = arms["h4_ts"], arms["labels"]
close = close_grid(h4_ts)
n = len(close)
assets = list(arms["arm_a"])
legs = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}
lines = Path("docs/reference/trial-registry.jsonl").read_text().splitlines()
record_58, record_60 = json.loads(lines[57]), json.loads(lines[59])


def per_year(flags):
    out = {}
    for k, flag in enumerate(flags):
        out[close[k].year] = out.get(close[k].year, 0) + int(flag)
    return {y: c for y, c in sorted(out.items()) if c}


def limited(positions):
    factors, engaged = limit_factors(base_exposures(positions, legs))
    return scale_bars(positions, factors), engaged, factors


def mean_of(books):
    return {a: [statistics.mean(arm[a][k] for arm in books) for k in range(n)] for a in assets}


arm_a = arms["arm_a"]
print("arm A, _b4_ensemble's, equals the mean of the program's three untilted arms bit for bit:", mean_of(arms["arms_a"]) == arm_a)
turnover_a = book_turnover(arm_a)
print("turnover of arm A", repr(turnover_a), "; record 58's turnover_a", repr(record_58["metrics"]["turnover_a"]))
lim_a, engaged_a, _ = limited(arm_a)
print("arm A after the limits bit-identical:", lim_a == arm_a, {k: sum(v) for k, v in engaged_a.items()})

# M = 180: the program's books against record 60's stored engagement, the tie that the program builds trial 1's arm B.
lim_180, _, _ = limited(mean_of(b180["arms_b"]))
differ_180 = [any(lim_180[a][k] != arm_a[a][k] for a in assets) for k in range(n)]
start_180 = differ_180.index(True)
m60 = record_60["metrics"]
print(
    "M = 180 against record 60: turnover_b", book_turnover(lim_180) == m60["turnover_b"],
    "; tilt_first_engaged", start_180 == m60["tilt_first_engaged"],
    "; stamps_positions_differ", sum(differ_180) == m60["stamps_positions_differ"],
    "; ranked histogram", {str(m): b180["baskets"][labels[0]].count(m) for m in range(11)} == m60["ranked_assets_histogram"][labels[0]],
)

# M = 540: trial 2's arm B.
raw_b = mean_of(b540["arms_b"])
lim_b, engaged_b, factor_b = limited(raw_b)
print("arm B after the limits bit-identical:", lim_b == raw_b, {k: sum(v) for k, v in engaged_b.items()}, "bars scaled", sum(f != 1.0 for f in factor_b))
print(f"arm B: max gross {max(math.fsum(abs(lim_b[a][k]) for a in assets) for k in range(n)):.6f}")
basket = b540["baskets"][labels[0]]
floor = [m >= 8 for m in basket]
first_floor = floor.index(True)
print(f"the basket per return index, histogram {dict(sorted(Counter(basket).items()))}")
print(f"  min {min(basket)}, mean {statistics.fmean(basket):.4f}, max {max(basket)}; 8 or more at {sum(floor)} ({100 * sum(floor) / n:.2f} %), first at return index {first_floor}, close {close[first_floor].isoformat()}; below 8 after it {sum(not f for f in floor[first_floor:])}")
print("  8 or more per close year", per_year(floor))
basket_180 = b180["baskets"][labels[0]]
print(f"  against M = 180's basket: smaller at {sum(x < y for x, y in zip(basket, basket_180))} return indices, larger at {sum(x > y for x, y in zip(basket, basket_180))}; 8 or more at M = 180 and below 8 at M = 540 {sum(y >= 8 > x for x, y in zip(basket, basket_180))}")
unscored = b540["unscored"]
print(f"  a weighted asset with no score at {sum(u > 0 for u in unscored)} return indices, {sum(unscored)} asset-closes, per close year {per_year([u > 0 for u in unscored])}")
for label in labels:
    longs = b540["longs"][label]
    tilted = [t > 0 for t in longs]
    first = tilted.index(True)
    print(f"{label}: tilted at {sum(tilted)} return indices, first {first}, close {close[first].isoformat()}; longs tilted where it tilts, mean {statistics.fmean(t for t in longs if t):.4f}, min {min(t for t in longs if t)}, max {max(longs)}")
    print(f"  tilted per close year {per_year(tilted)}; at 8 or more ranked with fewer than 2 long {sum(f and not t for f, t in zip(floor, tilted))}")
for label, arm_a_i, arm_b_i in zip(labels, arms["arms_a"], b540["arms_b"]):
    print(f"{label}: first return index whose positions differ from the untilted arm's {next((k for k in range(n) if any(arm_b_i[a][k] != arm_a_i[a][k] for a in assets)), n)}")
differ = [any(lim_b[a][k] != arm_a[a][k] for a in assets) for k in range(n)]
start = next((k for k in range(n) if differ[k]), n)
print(f"the ensemble: first return index whose positions differ, {start}, close {close[start].isoformat()}; returns from it {n - start}, {(n - start) / 2190:.2f} years of 2,190; closes {close[start].date()} -> {close[-1].date()}")
print(f"  positions differ at {sum(differ)} return indices, per close year {per_year(differ)}; before the start {sum(differ[:start])}")
untilted = [all(not b540["longs"][label][k] for label in labels) for k in range(n)]
print(f"  from the start, return indices with no arm tilted {sum(untilted[start:])}, of them with positions differing {sum(u and d for u, d in zip(untilted[start:], differ[start:]))}")
turnover_b = book_turnover(lim_b)
added = turnover_b - turnover_a
print(f"turnover A {turnover_a!r} B {turnover_b!r}, B over A {100 * (turnover_b / turnover_a - 1):.2f} %; B - A {added!r}")
print(f"  before the start, B - A {book_turnover({a: lim_b[a][:start] for a in assets}) - book_turnover({a: arm_a[a][:start] for a in assets})!r}")
cost = added * 0.006
print(f"  at 0.006 a side: {cost!r} summed; per bar over the primary read {cost / (n - start)!r} ({cost / (n - start) * 2190:.4f} a year), over the full window {cost / n!r} ({cost / n * 2190:.4f} a year)")
cost_60 = (m60["turnover_b"] - m60["turnover_a"]) * 0.006 / m60["primary_returns"]
print(f"  trial 1's, record 60's stored turnovers over its primary read: {cost_60!r} per bar; trial 2's over trial 1's {cost / (n - start) / cost_60:.4f}")
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-25T16:35:39+00:00
arm A, _b4_ensemble's, equals the mean of the program's three untilted arms bit for bit: True
turnover of arm A 146.18534602048504 ; record 58's turnover_a 146.18534602048504
arm A after the limits bit-identical: True {'gross': 0, 'net': 0, 'margin': 0}
M = 180 against record 60: turnover_b True ; tilt_first_engaged True ; stamps_positions_differ True ; ranked histogram True
arm B after the limits bit-identical: True {'gross': 0, 'net': 0, 'margin': 0} bars scaled 0
arm B: max gross 0.998300
the basket per return index, histogram {0: 540, 1: 4124, 2: 3062, 3: 1098, 4: 2790, 5: 2596, 6: 1401, 7: 249, 8: 1714, 9: 1303, 10: 8460}
  min 0, mean 5.7750, max 10; 8 or more at 11477 (41.98 %), first at return index 15672, close 2020-12-03T12:00:00+00:00; below 8 after it 188
  8 or more per close year {2020: 170, 2021: 2186, 2022: 2190, 2023: 2190, 2024: 2012, 2025: 2189, 2026: 540}
  against M = 180's basket: smaller at 2649 return indices, larger at 0; 8 or more at M = 180 and below 8 at M = 540 6
  a weighted asset with no score at 2649 return indices, 2660 asset-closes, per close year {2013: 329, 2014: 168, 2015: 3, 2016: 24, 2017: 367, 2018: 365, 2019: 344, 2020: 371, 2021: 316, 2022: 360, 2023: 1, 2024: 1}
20-50-100@0.12: tilted at 7734 return indices, first 15672, close 2020-12-03T12:00:00+00:00; longs tilted where it tilts, mean 6.5362, min 2, max 10
  tilted per close year {2020: 144, 2021: 1597, 2022: 1286, 2023: 1634, 2024: 1415, 2025: 1343, 2026: 315}; at 8 or more ranked with fewer than 2 long 3743
60-120-240@0.1: tilted at 7820 return indices, first 15672, close 2020-12-03T12:00:00+00:00; longs tilted where it tilts, mean 6.3848, min 2, max 10
  tilted per close year {2020: 170, 2021: 1684, 2022: 1215, 2023: 1661, 2024: 1444, 2025: 1304, 2026: 342}; at 8 or more ranked with fewer than 2 long 3657
60-120-240@0.12: tilted at 7820 return indices, first 15672, close 2020-12-03T12:00:00+00:00; longs tilted where it tilts, mean 6.3848, min 2, max 10
  tilted per close year {2020: 170, 2021: 1684, 2022: 1215, 2023: 1661, 2024: 1444, 2025: 1304, 2026: 342}; at 8 or more ranked with fewer than 2 long 3657
20-50-100@0.12: first return index whose positions differ from the untilted arm's 15672
60-120-240@0.1: first return index whose positions differ from the untilted arm's 15672
60-120-240@0.12: first return index whose positions differ from the untilted arm's 15672
the ensemble: first return index whose positions differ, 15672, close 2020-12-03T12:00:00+00:00; returns from it 11665, 5.33 years of 2,190; closes 2020-12-03 -> 2026-03-31
  positions differ at 9687 return indices, per close year {2020: 171, 2021: 1904, 2022: 1762, 2023: 1940, 2024: 1805, 2025: 1717, 2026: 388}; before the start 0
  from the start, return indices with no arm tilted 2857, of them with positions differing 879
turnover A 146.18534602048504 B 171.84195562051642, B over A 17.55 %; B - A 25.656609600031373
  before the start, B - A 0.0
  at 0.006 a side: 0.15393965760018824 summed; per bar over the primary read 1.319671303902171e-05 (0.0289 a year), over the full window 5.631183290053343e-06 (0.0123 a year)
  trial 1's, record 60's stored turnovers over its primary read: 2.171062550568289e-05 per bar; trial 2's over trial 1's 0.6078
end 2026-10-25T16:35:43+00:00
```

What they establish:

- **The block.** The ten EUR assets' 240-minute files of `ohlc-full` form the block the record will carry, `compute_hash` `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`: 10 files, 173,373 rows, 2013-09-10 20:00 → 2026-03-31 20:00, `vouched_status` `checked (36 vouched hashes)`, no hole — record 58's ten EUR files and no other, and the `dataset_hash` of records 49 and 60 (the count program below).
- **The union.** 27,338 stamps, 27,337 return indices, records 45–60's.
- **Arm A is record 58's.** `_b4_ensemble(fed)` — trial 58's own function — equals the mean of the program's three untilted arms bit for bit, each of those `a2_book_returns`' `asset_positions` bit for bit, and its turnover is record 58's stored `turnover_a`, 146.18534602048504, to the last digit.
- **The program builds trial 1's arm B.** On trial 1's 180-close score its tilted books, limited, give record 60's stored `turnover_b`, `tilt_first_engaged`, `stamps_positions_differ` and `ranked_assets_histogram` to the last digit, and their tilt's size, 0.4153–1.8334 and 0.3989–1.7982, is spec 00147's: the expression that builds trial 2's arm B below is the one that rebuilds trial 1's record, the score window its one change.
- **The basket on a 540-close score.** Every asset with an inverse-vol weight and a 540-close score is ranked, whatever its direction, so the basket is one list for the three arms. Over the 27,337 return indices it holds 0 to 10 assets, 5.7750 on average (trial 1's 5.8723); it holds 8 or more at 11,477 (41.98 %), first at return index 15,672 (close 2020-12-03 12:00) — trial 1's first — every close of 2022 and 2023, 2,186 in 2021, 2,012 in 2024 and 2,189 in 2025 — and below 8 at 188 return indices after the first.
- **The weighted assets with no score.** A weight needs 180 present closes, a score 540, so for the 360 closes after an asset's weight begins it is weighted and unranked, out of the basket, its weight untouched (spec 00147 D3's "an asset with no close at k or at k − M has no score and is out of the basket", which on trial 1's window decided no close): at 2,649 return indices, 2,660 asset-closes, the basket is smaller than trial 1's and never larger; of the closes trial 1's basket held at 8 or more, 6 fall below 8.
- **The tilted closes.** Where the basket holds 8 or more, the tilt moves weights wherever 2 assets or more are long: on the arm on lookbacks (20, 50, 100) at 7,734 return indices (trial 1's 7,757), 6.5362 longs on average where it does; on the two arms on (60, 120, 240) at 7,820 (trial 1's 7,865), 6.3848 on average; at 3,743 and 3,657 the basket holds 8 or more with fewer than 2 assets long, and nothing tilts.
- **The tilt's size.** Where the tilt moves a weight, the tilted weight lies between 0.4132 and 1.8709 times the untilted on the (20, 50, 100) arm and between 0.4208 and 1.8496 on the other two — the multiplier `1 + k·z` in [0.5, 1.5], the rescale to the longs' sum widening it inside [1/3, 3] (spec 00147 D3).
- **The first engagement.** Every arm first tilts at return index 15,672 (close 2020-12-03 12:00), and every arm's positions first differ from its untilted book's there; so the ensemble's do, and the primary read holds 11,665 return indices, 5.33 years of 2,190, 2020-12-03 → 2026-03-31 — trial 1's span, return index for return index. Before 15,672 arm B's positions are arm A's bit for bit.
- **Where the books differ.** At 9,687 return indices (trial 1's 9,691), per close year from 171 (2020) to 1,940 (2023). From the first engagement on, at 2,857 return indices no arm tilts, and at 879 of those the positions still differ: the vol target reads the last 180 base returns, which a tilt earlier in the window moved (spec 00147 D3).
- **The limits.** No bar of either arm engages §10's gross cap, net band or margin floor: both arms' largest gross exposure is 0.9983, so each comes out of the limits bit-identical.
- **The turnover — the hurdle.** Arm B trades 171.84195562051642 against arm A's 146.18534602048504, 17.55 % more (trial 1's arm B 28.87 %): the added 25.656609600031373 costs, at 0.006 per side, 0.15393965760018824 in per-bar return summed. The books are one to the bit before the first engagement, so all of it falls inside the primary read's 11,665 returns: 1.319671303902171e-05 per bar there (0.0289 a year), the hurdle the deciding head-to-head carries, 0.6078 of trial 1's 2.171062550568289e-05, against 5.631183290053343e-06 per bar (0.0123 a year) spread over the full window's 27,337 — each figure from the two turnovers alone.

**The count, the names and the bar's threshold**, a third program:

```python
import json
import math
import random
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha.killbar import a1_kill_bar, net_of_cost_verdict
from cli.registry import attempts, budget
from cli.research import subjects
from cli.validation import deflated_sharpe_ratio
from tests.retired_subjects import RETIRED_SUBJECTS

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]
landed = attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl"))
c = attempts.reconcile(lines, landed, log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF)
families = ("B1", "B2", "B3", "B4")
print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in families}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])
print("required_n('B3')", c.required_n("B3"), "; B3 records", [(r["trial_id"], r["n_trials_in_family"], r["invocation"]["subject"]) for r in c.records if r["family"] == "B3"])
print("open attempts (a begin with no end):", sorted({x["attempt"] for x in lines if x["kind"] == "begin"} - {x["attempt"] for x in lines if x["kind"] == "end"}))
attempt = max(x["attempt"] for x in lines if x["kind"] == "begin")
begin = next(x for x in lines if x["kind"] == "begin" and x["attempt"] == attempt)
end = next(x for x in lines if x["kind"] == "end" and x["attempt"] == attempt)
took = datetime.fromisoformat(end["timestamp"]) - datetime.fromisoformat(begin["timestamp"])
print(f"attempt {attempt} ({begin['invocation']['subject']}): {took.total_seconds():.0f} s, failed {end['failed']}; log {lines[0]['log_id'][:8]}")
records = [json.loads(x) for x in Path("docs/reference/trial-registry.jsonl").read_text().splitlines()]
print("records whose dataset_hash is ff2e5700...:", [r["trial_id"] for r in records if r["dataset_hash"].startswith("ff2e5700695b")])
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("b3-tilt-slow", "b3-tilt-slow-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("names opening b3:", sorted(x for x in names if x.startswith("b3")), "; retired among them:", sorted(x for x in RETIRED_SUBJECTS if x.startswith("b3")))
for n_obs, n_trials in ((27_337, 1), (27_337, 2)):
    lo, hi = 0.0, 0.1
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if deflated_sharpe_ratio(mid, n_obs, n_trials, 0.0) <= 0.95 else (lo, mid)
    print(f"{n_obs} returns at n_trials {n_trials}, var_trials 0.0: dsr_pass needs a per-period Sharpe above {hi:.6f}, annualised {hi * math.sqrt(2190):.4f}")
rng = random.Random(0)
n = 27_337
book = [rng.gauss(0.0003, 0.01) for _ in range(n)]
bench = [rng.gauss(0.0002, 0.01) for _ in range(n)]
slices = {str(2014 + i): book[i * 2190 : (i + 1) * 2190] for i in range(12)}
bench_slices = {str(2014 + i): bench[i * 2190 : (i + 1) * 2190] for i in range(12)}
t0 = time.perf_counter()
a1_kill_bar(book, bench, n_trials=2, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=book, regime_slices=slices, benchmark_slices=bench_slices, decisive_start=1380, n_resamples=2000)
t1 = time.perf_counter()
net_of_cost_verdict(book, bench, mean_block=30, seed=42, n_resamples=2000)
t2 = time.perf_counter()
print(f"synthetic, {n} Gaussian returns: one a1_kill_bar {t1 - t0:.2f} s, one net_of_cost_verdict {t2 - t1:.2f} s")
```

Its output, whole:

```text
read at 2026-10-25T16:36:14+00:00
{'B1': 5, 'B2': 7, 'B3': 1, 'B4': 2} remain 10 []
required_n('B3') 2 ; B3 records [(60, 1, 'b3-rank-tilt')]
open attempts (a begin with no end): []
attempt 12 (b3-rank-tilt): 264 s, failed None; log 60c9f39c
records whose dataset_hash is ff2e5700...: [49, 60]
b3-tilt-slow equals or opens with a hyphen: [] ; it opens: []
b3-tilt-slow-preflight equals or opens with a hyphen: [] ; it opens: []
names opening b3: ['b3-rank-tilt', 'b3-rank-tilt-preflight'] ; retired among them: []
27337 returns at n_trials 1, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.009949, annualised 0.4656
27337 returns at n_trials 2, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.009949, annualised 0.4656
synthetic, 27337 Gaussian returns: one a1_kill_bar 11.16 s, one net_of_cost_verdict 5.70 s
```

- **The count**: the registry holds one B3 record, trial 60 at count 1, and the trial-attempts log no orphan and no open attempt, so `required_n("B3")` is 2 — B3's true count with this trial, the count it declares (D7); bucket B has spent 15 of 25 (B1 5, B2 7, B3 1, B4 2), 10 remaining, 9 once this trial's record lands.
- **The names**: no registered or retired subject's name equals `b3-tilt-slow` or `b3-tilt-slow-preflight` or opens either with a hyphen, and neither opens one; the names opening `b3` are trial 1's two, neither retired (D8).
- **The DSR leg**: at `var_trials` 0.0 the expected maximum Sharpe is 0 at any count, so at count 2 the leg is the PSR against 0, as at count 1: over the 27,337 returns `dsr_pass` needs an annualised net Sharpe above 0.4656, spec 00147's figure (D7).
- **The run's time**: record 60's `--register` run took 264 s (attempt 12 of log `60c9f39c`). This trial's inputs half — three A2 runs for arm A, three tilted runs for arm B — took 136.75 s as the plan's data-gated case, run on the authoring tree; one `a1_kill_bar` over 27,337 synthetic returns took 11.16 s and one `net_of_cost_verdict` 5.70 s. The trial computes seven bars and two head-to-heads, about 137 + 78 + 11 ≈ 226 s, one process well under 600 s; its pre-flight the inputs half and one bar, about 148 s.

Spec 00147 frozen, and the code path since record 60's run:

```text
$ date -u +%Y-%m-%dT%H:%M:%SZ; sha256sum docs/specs/00147-b3-rank-tilt-design.md; python3 -c 'import json; r = json.loads(open("docs/reference/trial-registry.jsonl").read().splitlines()[59]); print("record", r["trial_id"], r["spec_hash"], r["invocation"]["commit"])'; git log --oneline cd467546499090509ace16951b2c6b5929c5d0f0..22c220677 -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat
2026-10-25T16:36:37Z
4dfe9b63171db3dbe2b9f1a129af3cd8bb7d78046e9d944062f83402b11f1163  docs/specs/00147-b3-rank-tilt-design.md
record 60 4dfe9b63171db3dbe2b9f1a129af3cd8bb7d78046e9d944062f83402b11f1163 cd467546499090509ace16951b2c6b5929c5d0f0
$ git merge-base --is-ancestor cd467546499090509ace16951b2c6b5929c5d0f0 22c220677 && echo ancestor
ancestor
```

- **Spec 00147 is frozen**: its sha256 is record 60's `spec_hash`; it is not edited.
- **The code path since record 60's run** at `cd4675464`, an ancestor of this branch's base: the log to the base prints nothing — no commit has touched it, so the reads, tilt, arm A, limits, costing, bar and rule this trial reuses are record 60's.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial runs under one, the session holding this branch's worktree, `.claude/worktrees/iter193`, on the workstation `zcrypto-ops`, whose main checkout holds the one listed trial-attempts log (`docs/reference/trial-attempt-logs.txt`). No other session runs a bucket-B subject while this branch is open — B1, B2 and B4 are closed and their subjects retired, and B3's trial 1 is recorded — no second machine and no restored or copied log; each of those is spec 00133's to count and refuse, not this spec's to design for.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Both read `data/ohlc-full`, a symlink to the main checkout's frozen, attested set; a run writes nothing under it and makes no network call, and nothing this spec runs has a live writer.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained; this worktree is their one writer while the branch is open. `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and landed-count literal before anything else lands (D9).

## Hypothesis (trial 2, pre-registered by this spec's sha256)

Master plan §5's B3, its tilt alone, on a slower score: a cross-sectional rank on 90-day momentum carries information the per-asset trend signal does not and turns over less than trial 1's 30-day rank — among the ten assets, the ones that rose most over the last 90 days keep outrunning the ones that rose least — so **the adopted A2-4h ensemble with each arm's inverse-vol weights of the assets it holds long tilted at every close by their rank in the whole basket on the trailing 540-close simple return — each long's weight times 1 + 0.5·z, 1.5 times at the basket's top and 0.5 times at its bottom, the longs rescaled to their untilted sum — wherever the basket ranks 8 assets or more, has a higher mean net-of-cost return than the untilted ensemble from the first close the tilt moves a position, net of each asset's own turnover at 0.006 a side.** Arm A is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45–60 built it; arm B trial 1's arm B with its score window `M` = 540 in place of 180, A2's configuration, `k` = 0.5 and the floor 8 unchanged. One knob moves from trial 1, `M`. It is judged by D7's matrix on its own record; what its verdict changes is D10's.

## D1 — the pick: the owner's sequence, its first step the tilt on a 540-close score

- The owner's words, quoted in the Ruling, and the options the owner was offered, as the `[iter-193] B3's next step after trial 1` entry records them: **1, a park variant — the tilt at another `M` or `k`**, spec 00147 D7's and D10's named variant; **2, the A1-short BTC overlay**, master plan §5's B3 whole; **3, closing B3**. The owner's answer takes them in that order, 1 → 2 → 3: this trial is 1, trial 3 — the overlay — the next iteration, then B3's close (D10).
- **The loop's call (Decision: 1 of the `[iter-193] B3 trial 2's variant` entry) — the score at `M` = 540 closes (90 days), `k` and the floor unchanged.** Record 60's stored turnovers put trial 1's added trading cost from its first engagement at 2.171062550568289e-05/bar (the turnover difference 42.20907442063182 at 0.006 a side over 11,665 returns) and its stored net head-to-head at −1.918138730849262e-05/bar, so the tilt's gross outperformance was about +2.53e-06/bar — arithmetic over record 60's stored figures, read after its run: the cost is the lever, and a slower score moves the ranks less (measured: arm B trades 17.55 % more than arm A against trial 1's 28.87 %, its hurdle 0.6078 of trial 1's). One knob moves, so the verdict attributes to the score window.
- The alternatives weighed and set aside: **`k` = 0.25 at `M` = 180** — halves the tilt, its edge and its cost together, the ratio unchanged and the net still negative by the same arithmetic; **`M` = 1,080 (180 days)** — slower still, a half-year score; the slower the score the closer the tilt comes to the inverse-vol weights it tilts, and one slot buys one cell.
- One iteration, one branch, this spec and its plan, one plan review, one task loop; one trial subject with its pre-flight twin, one bar, one matrix, one record. The budget: the landed record spends one of Bucket B's 10 remaining (spec 00133 D5; `BUDGET["B"]` 25, B1 5, B2 7, B3 1 and B4 2 spent); a stop, a refused build or a refusal from the count spends none.

## D2 — the instrument: frozen `ohlc-full`, full history, the ten EUR assets alone

- **The loop's call**: trial 1's instrument, unchanged — `--dataset ohlc-full`, no `--window`, no `--as-of`; the ten EUR assets' 4h union exactly as records 45–60 read it, `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices; no other pair; the decisive window from index 1,380; the arms on `_ffill_btc`'s BTC-only fill, the benchmark on the raw prices. The record's block is the ten files', `ff2e5700…01719a69` (measured), records 49's and 60's.
- The reads are trial 1's `_b3_reads`, unchanged: they refuse, before any book, a window holding fewer than `_DECISIVE_START` + 2 return indices and one none of whose return indices closes in a calendar year the worst-slice leg reads, the stub years left out; and the build refuses `--as-of` before any read: "<subject> evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset".

## D3 — the arms: arm A the adopted ensemble, arm B trial 1's on a 540-close score

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as trial 58 built it and trial 1 read it: `_b4_limited(_b4_ensemble(fed))`, `fed = _ffill_btc(h4_prices)`, the three arms `_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year — measured equal to record 58's arm A, its turnover record 58's to the last digit.
- **Arm B** is trial 1's arm B with its score window moved: each of the three arms' books `b3_book_returns(fed, config=<its A2Config>, score_lookback=540, strength=0.5, floor=8)`, unchanged in `cli/alpha/b3.py`; their equal-weight mean; then the limits. **The tilt at close k is spec 00147 D3's**, every clause unchanged: the ranked set the basket — every asset with an inverse-vol weight above 0 and a momentum score at that close, whatever its direction; `z` its centred ascending rank, ties at their average rank; at a basket of 8 or more and 2 longs or more each long's weight times `1 + k·z`, the longs rescaled to their untilted sum, the flat assets untouched; otherwise every weight untilted. The score is the trailing simple return over 540 closes, `p[k] / p[k − 540] − 1` on the union's BTC-filled closes, known at close k; an asset with no close at k or at k − 540 has no score and is out of the basket — on this window, unlike trial 1's, a clause that decides closes: 2,649 return indices hold a weighted asset with no score (measured).
- **The values** (the loop's call, D1): `M` = 540 closes (90 days); `k` = 0.5 and the floor 8, trial 1's. After the rescale a long's weight lies between 1/3 and 3 times its untilted weight (measured: 0.4132 to 1.8709).
- **Bit for bit until the tilt first moves a position**, as spec 00147 D3 holds it: before the first close with a basket of 8 or more and 2 longs or more, every weight is the untilted dict itself, so arm B's positions are arm A's to the bit; after it they differ at a tilted close and at an untilted one whose vol-target window holds a moved base return (measured: 879 return indices). `tilt_first_engaged` is the first return index at which arm B's limited positions differ from arm A's — 15,672 (close 2020-12-03 12:00, measured), trial 1's.
- **Author's call — the code: trial 1's halves where they take no score window, a block of trial 1's form where they do.** `cli/alpha/b3.py`'s `b3_book_returns` takes the score window as an argument and is called unchanged. Trial 1's `_b3_ensemble`, `_b3_inputs` and `_b3_build` read `M` and the count as the module constants `_B3_SCORE_LOOKBACK` and `_B3_N_TRIALS`, which record 60's replay freezes, so they cannot build this trial and are not changed; the new block holds their three counterparts in their form — `_b3_slow_ensemble`, `_b3_ensemble` on `_B3_SLOW_SCORE_LOOKBACK`; `_b3_slow_inputs`, `_b3_inputs` with it; `_b3_slow_build`, `_b3_build` with it and `_B3_SLOW_N_TRIALS` — the two builders and the two constants. Everything else is trial 1's, read as it is: `_B3Inputs`, `_b3_reads`, `_b3_first_engaged`, `_b3_engagement`, `_b3_metrics`, `_b3_preflight_metrics`, the rule `_b3_rank_tilt_verdict` and the key sets `_B3_METRIC_KEYS` and `_B3_PREFLIGHT_KEYS`; trial 58's `_b4_ensemble`, `_b4_limited`, `_b4_net` and `_b4_arm_a_bar` through them. **Author's call — `k` and the floor read through trial 1's constants**, `_B3_STRENGTH` and `_B3_FLOOR`: "unchanged" is then the code's own statement, and record 60's replay holds both.
- No change to `cli/alpha/*`, `cli/registry/*`, `cli/risk/*`, `cli/costs/*`, `cli/portfolio/*`, any existing function or subject of `cli/research/subjects.py`, or any adopted artifact.

## D4 — the costing: trial 58's, no carry

- The returns: `_asset_returns(fed[a])` for each of the ten assets. Every book is costed by trial 58's `_b4_net(positions, returns, stress=…)` — `net_of_cost` at `stress × 0.006` per side on each asset's own turnover from flat, a missing return read as 0.0, less `shortfall_carry` of the book's BTC shortfall at `stress × 0.0002`, 0.0 at every bar for a long-only book holding no ratio leg: no short, no borrow, no carry. The kill bar's cost-stressed series is `stress` 1.5. Trial 1's `_b3_metrics` calls it unchanged, so arm A's net is record 58's arm A's to the bit.

## D5 — §10's limits: trial 58's wiring on the ten assets alone

- Both arms pass `_b4_limited` — `limit_factors` over `base_exposures(positions, _B4_LEGS)`, the gross cap 1.5 / 2.0, the net band −0.5 … +1.0, the margin floor 2.5, in `cli/risk/limits.py`'s order, one factor per bar. No bar of either arm engages a limit (measured: both arms' largest gross 0.9983), so both come out bit-identical; arm B's engaged bars per limit and close year and arm A's totals are recorded.

## D6 — the contamination, stated in full

- **Trial 2 is designed after trial 1's result.** B3 has one record, trial 60, REJECT: its net head-to-head from the tilt's first engagement, −1.918138730849262e-05/bar at SPA p 1.0, and its turnovers are stored; the split of that figure into the tilt's gross outperformance, about +2.53e-06/bar, and its added trading cost, 2.171062550568289e-05/bar, is arithmetic over those stored figures, read after its run. **The choice of `M` answers trial 1's cost — a look this spec names**: a slower score was chosen because trial 1's cost, not its gross edge, made its loss, and the measured basis confirms the slower score trades less.
- **What the measured hurdle says before the run.** Arm B's added cost over the primary read is 1.319671303902171e-05/bar (measured, from the two turnovers alone), about 5.2 times trial 1's gross figure at `M` = 180; the hypothesis asks whether the 90-day rank's gross edge over the same 11,665 returns clears that, and the author knows no figure of this repository about any tilted book's returns on a 540-close score.
- **The variant was named before trial 1's result, its value chosen after it**: "the tilt at another `M` or `k`" is spec 00147 D7's park variant and D10's next step, set aside in its Out of scope for a later trial; the owner picked it, after trial 1's verdict, as the first of three steps, and the loop chose `M` = 540 among the three cells D1 weighs.
- **The instrument, window, arm A, costing, limits and bar are records 45–60's**, whose arm A clears the bar on this window (record 58's and record 60's `arm_a_passes` 1; its anchors read again at the pre-flight, D9). The primary read's span, 2020-12-03 → 2026-03-31, is trial 1's to the return index, so trial 2 reads no return index trial 1 did not.
- **The DSR counts B3's true trials**: `n_trials` 2, records 60 and this one, `required_n("B3")` measured 2. At `var_trials` 0.0 the count moves no threshold (D7).
- **The master plan's prior, in its own words**: "expected outcome per priors: fails to beat equal-weight; kill quickly if so" — read once by trial 1, whose reject stands; this trial is the owner's next step, not a re-run of trial 1.

## D7 — the bar, the head-to-heads, the matrix and the count

- **The bar**, record 60's call at count 2: `a1_kill_bar(net_b, bench, n_trials=2, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)` on the raw union prices, the stub years 2013 and 2026 out of the slices; the SPA grid blocks {30, 102} × seeds {42, 7, 1234}, the headline cell (30, 42), the five others recorded and never read. At count 2 and `var_trials` 0.0 the DSR leg is the PSR against 0: `dsr_pass` needs an annualised net Sharpe above 0.4656 over the 27,337 returns (measured). **Arm A's headline bar** is the same call on `net_a` at (30, 42), `_b4_arm_a_bar` unchanged, read `passes` 1 at the pre-flight, after the hash (D9). All of it is trial 1's `_b3_metrics`, called with `n_trials=2`.
- **The head-to-heads** (the loop's call, trial 1's): `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)`, primary from the tilt's first engagement — `first` = `tilt_first_engaged`, 15,672, `primary_returns` 11,665 (measured) — and over the full window (`first` 0) beside it; keyed `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_full` and `head_to_head_spa_p_full`. Before the first engagement the two books are one to the bit (D3), so the full-window read adds 15,672 zero differences to the primary's; the primary decides. Refused before any bar: fewer than 2 return indices from the first engagement — a `ValidationError` and so a refused build — which a dead knob, no position ever moved, is too.
- **The matrix** (the loop's call, trial 1's) — rows disjoint and covering every outcome:

| Arm A's bar and the tilt's engagement | Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from the tilt's first engagement) | Verdict |
| --- | --- | --- | --- |
| arm A's `passes` 0, or arm B's positions never differ from arm A's (a dead knob) | any | any | **instrument finding**: no verdict, the slot unspent |
| arm A passes, the tilt engaged | fail | any | **reject** |
| arm A passes, the tilt engaged | pass | mean outperformance > 0 and SPA p < 0.05 | **adopt** the tilt on a 540-close score |
| arm A passes, the tilt engaged | pass | mean outperformance > 0, SPA p ≥ 0.05 | **park** (no variant: the owner's sequence goes on to trial 3, the A1-short BTC overlay) |
| arm A passes, the tilt engaged | pass | mean outperformance ≤ 0 | **reject** |

  Every quantity the matrix reads is a stored key read unrounded: `arm_a_passes`, `stamps_positions_differ`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`. No drawdown leg. The dead knob is read at the pre-flight, before the run (D9); under `--register` the build refuses it before any bar, so the rule's first row stands for a metrics dict alone. **The loop's call — the rule is trial 1's own function**, `_b3_rank_tilt_verdict`, unchanged: every key it reads is one this trial's metrics carry under the same name and meaning, so a rule of this trial's own would type the same five rows a second time. **Author's call — the park row names no variant**: the owner's sequence already names the next trial, whatever this one's verdict (D10).
- **The count**: 2, `_B3_SLOW_N_TRIALS` — B3's true count with this trial, `required_n("B3")` measured 2 from the registry and the trial-attempts log (record 60, no orphan, plus one). Fixed by this spec's hash, never raised in place; spec 00133 D4 refuses a declared count below `required_n`, so a B3 attempt landing elsewhere before this run refuses it, the trial going back to the owner through T0016, a further count a new subject under a new spec.

## D8 — the engagement, the subjects, their record and the build

- **The engagement and the keys are trial 1's** (spec 00147 D8): both subjects' eleven engagement keys from `_b3_engagement`, unchanged — `tilt_first_engaged`, `primary_returns`, `stamps_positions_differ`, `positions_differ_per_year`, `tilted_per_year`, `ranked_assets_histogram`, `ranked_assets_mean`, `turnover_b`, `turnover_b_per_year`, `limit_engaged_per_year`, `arm_a_limit_engaged`; the trial's 44 keys `_B3_METRIC_KEYS` and the pre-flight's 28 `_B3_PREFLIGHT_KEYS` — the engagement's eleven, arm A's seven anchors and arm A's bar's ten.
- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00148-b3-tilt-slow-design.md"`, `_ASSETS`, intervals `(240,)`: the trial `b3-tilt-slow` — `_build_b3_tilt_slow`, `metric_keys=_B3_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_b3_rank_tilt_verdict`, `no_verdict` trial 1's text, "instrument finding: arm A fails the bar this window sets, or the tilt moves no position at any stamp; no verdict, the trial unspent", `family="B3"`, `n_trials=_B3_SLOW_N_TRIALS` — and its evaluate-only twin `b3-tilt-slow-preflight` — `_build_b3_tilt_slow_preflight`, `metric_keys=_B3_PREFLIGHT_KEYS`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). It costs arm A alone and reads no head-to-head; it builds arm B's positions, which its engagement reads. No incumbent: arm A is built in the run.
- **Author's call — the names `b3-tilt-slow` and `b3-tilt-slow-preflight`**: spec 00141 D2's rule — no registered or retired subject's name equals either or opens it with a hyphen, and neither opens one (measured); the `b3` prefix keeps the family's subjects together beside trial 1's two.
- **The family key `B3`** is in `BUCKET_OF` already (spec 00147 D8); `cli/registry/budget.py` is unchanged.
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B3`; `n_trials_in_family` 2; variant `B3-tilt-slow-a2eq-full-v1` (**Author's call**: record 60's form, `<family>-<name>-a2eq-full-v1`); iteration `iter-193`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`; `attempt` the trial-attempts log's; `notes` caller text written before the run (D9).
- **The build in three halves**, spec 00144 D9's form: trial 1's `_b3_reads(subject, reader, dataset, window, accept_holes)` — the union and D2's two window refusals, no compute; `_b3_slow_inputs(reads)` — both arms' limited positions, their engaged bars, each arm's basket sizes and tilted longs and the returns, no return of a book; trial 1's `_b3_metrics` and `_b3_preflight_metrics` from it, at `n_trials=_B3_SLOW_N_TRIALS`. The plan's data-gated case runs the first two over the real set, and its fixture tests run the books on a union shorter than the reads admit. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `RiskError`, `ValidationError` — is a `SubjectError` naming the subject and its window.
- **The files the build touches, a closed list**: `cli/research/subjects.py` — two insertions: the block before `SUBJECTS` (`_B3_SLOW_SCORE_LOOKBACK`, `_B3_SLOW_N_TRIALS`, `_b3_slow_ensemble`, `_b3_slow_inputs`, `_b3_slow_build` and the two builders) and its two `SUBJECTS` entries, no import added and no existing function changed; `README.md`'s `--subject` row; the tests the plan names; after the run, `tests/test_trial_registry_provenance.py`'s landed-count literal. No change to `cli/alpha/*`, `cli/registry/*`, `cli/features/*`, `cli/portfolio/*`, `cli/risk/*`, `cli/costs/*`, `cli/engine/*`, trial 1's subjects, specs 00128, 00133, 00137, 00144 and 00147, record 60 or any adopted artifact.

## D9 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00148-b3-tilt-slow-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append; (3) the data-gated basis test on the run's tree, with the subjects' two fixture rows and record 60's replay, which rebuilds trial 1's stored figures through the reads, arm A, costing, bar, head-to-head and rule code this trial's computes half shares with it; (4) the twin's plain eval, read in this order — (a) the block, `ff2e5700…01719a69`, `ohlc-full` `checked (36 vouched hashes)`; (b) arm A's seven anchors record 60's stored figures to the last digit — its `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown`, `turnover_a`, `benchmark_ann_sharpe_noc` and `benchmark_ann_sharpe_noc_decisive`, and the spot drag its `turnover_a` gives, `turnover_a / 27,337 × 0.006 × 2,190`; (c) the dead knob — arm B's positions differing from arm A's at some return index, `stamps_positions_differ` above 0, read before the engagement so that a dead knob is named as such; (d) the engagement equal to the measured basis — the plan's data-gated literals; (e) arm A's `passes` 1 — a failure of (a)–(e) an instrument finding, the run kept as a reading under iter-193 (`--reading --iteration iter-193 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent; (5) on a pass, the trial's one run, `--register --iteration iter-193 --family B3 --n-trials 2 --variant B3-tilt-slow-a2eq-full-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10); (6) the record's checks and its commit — the registry line, the decisions-log verdict entry and the landed-count literal together, since the tie tests hold only over the three.
- **The hash rule**: before (1), nobody reads or computes trial 2's arm B returns or net-of-cost series, a head-to-head or a bar leg of trial 2's arm B — by code, a program or arithmetic over a stored figure — nor runs `b3-tilt-slow` or its twin over the real set; weights, ranks, positions, exposures, limit engagement and turnover are allowed, and are what the measured basis and the data-gated test hold. `a2_book_returns` and `b3_book_returns` compute each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; no program reads any of them (spec 00145 D8's words). Record 60's replay, which rebuilds trial 1's returns, reads no book on a 540-close score. No net-of-cost return of trial 2's arm B is computed over the real data before the trial's `--register` run.
- **The notes, written before the run** (spec 00137 D10's): the subject over `ohlc-full`, full history; the arms, the tilt and its three values, the costing and the limits; the hypothesis; the count 2 and `var_trials` 0.0; the read from the tilt's first engagement deciding and the full-window read beside it; the contamination D6 states; the pre-flight's figures, quoted — arm A's seven anchors and the bar's `dsr` and SPA p; the park row naming no variant, the owner's sequence going on to trial 3; the matrix pre-registered by this spec's sha256.
- A refusal from the count, a refused build, a stop by the rule under `--register`: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0016's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D10 — what a verdict changes

- **Adopt** is recorded, never deployed, on spec 00147 D10's path: the tilt reweights the ten EUR pairs the engine's book already trades, so its live form is a change to the adopted book's A2 sleeve; its path, the owner's, in order: a P1 combination trial over record 47's book carrying the tilt, outside every bucket's budget, then T0123's promotion path; T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts.
- **Park** and **reject** record the verdict in the record and the decisions log; a reject archives the hypothesis.
- **After any verdict the owner's sequence goes on**: B3 trial 3 — the A1-short BTC overlay, master plan §5's B3 whole — is the next iteration, with its own brainstorm, spec and plan, then B3's close. T0016's B3 arm is rewritten in the branch's topic commit to wait on B3 trial 3 — an activity, its check a `[iter-NNN] B3 trial 3…` or `[iter-NNN] Verdict — B3 trial 3…` heading in the decisions log — and its next-steps bullet names trial 3 and then B3's close. No `[iter-NNN] B3's next step after trial 2` entry is asked of the owner on a verdict: the owner's word of 2026-10-25 already gives it.
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, a refused build or a refusal from the count — spends no trial. **Author's call**: the owner's sequence follows a verdict, and a stop has none, so whether trial 2 runs again once its cause is fixed or the sequence moves on to trial 3 is the owner's; T0016 records what failed and its B3 arm waits on a `[iter-NNN] B3's next step after trial 2` entry, as spec 00147 D10's stop arm waited on trial 1's.
- **Author's call — no retirement in this branch**, against `tests/retired_subjects.py`'s own rule: trial 3 may build on `_b3_reads`, `_b3_metrics`, `_b3_engagement` and `b3_book_returns`, whose cases trial 1's and trial 2's subjects carry, and retiring either pair would deselect from CI the cases that guard those halves; B3's closing branch retires all four.

## Out of scope

Every other B3 knob — `k` other than 0.5, another floor, a score window other than 540 closes, the tilt of the flat assets' weights too, the rank among the longs alone, a score other than the trailing simple return; the A1-short BTC overlay, trial 3, its own iteration; B3's close; a no-slot reading of the rank spread; any window but the frozen set's full history, and `ohlc-rolling`; the tilt on the live path and the combination trial over record 47's book (D10); the C families, T0016's; any change to an existing function, subject, record or spec.
