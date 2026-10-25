# B3 trial 1 — a cross-sectional momentum rank tilt of the A2-4h ensemble's long weights, on the frozen `ohlc-full` set

**Ruling:** the owner, attended, 2026-10-24, asked which family follows B4, verbatim: "B3 (Recommended)" — recorded in the decisions log's `[iter-190] B4's next step after the leg reading` entry; B4 closed on the owner's word in the `[iter-191] B4's next step after trial 2 — closed` entry, which fired T0016's B3 arm. The owner's unattended run instruction of 2026-10-23, verbatim: "continue working on B4-legs and other research strates. Ignore the wall time clock gate, but do not pick up new topics after 09:00Z". B3 is worked under T0016; no new topic is registered. B3's first step — this trial, directly — is the loop's pick under the owner's family pick (D1), recorded as the decisions-log entry `[iter-192] B3's first step — trial 1, the rank tilt alone on the A2-4h ensemble, the loop's pick under the owner's family pick` with the conventions entry, before this spec's hash. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" (the `[iter-181] B2 instrument ruling` entry), whose window is the one on which arm A is recorded clearing the ratified bar; and the two `[iter-176]` rulings binding every B and C pre-registration, the DSR leg binding at `var_trials` 0.0 and the spent holdout's window never reported as holdout evidence (this set ends 2026-03-31, before it). Every call past those words and past what specs 00128, 00133, 00137 and 00144 fix is the loop's, marked **The loop's call** where the loop's controller made it and **Author's call** where this spec's author did. **This version amends the first** (commit `896cede77`), before the hash, on the loop's controller's amendment of 2026-10-25: the first version ranked the assets held long alone, which its measured basis showed meeting the master plan's own breadth line at 12–13 % of closes; this version ranks the whole basket, tilts only at a basket of 8 or more, and applies the tilt to the longs alone (D3), every other call unchanged. **Iteration:** iter-192, branch `research/iter-192-b3-rank-tilt`. **Topic:** T0016, its B3 arm. **Goal:** pre-register B3's first trial — master plan §5's B3, "Cross-sectional momentum tilt, long-only, with BTC-short overlay. … The only variant left with a rationale: a *simple* (no-ML) rank tilt of long weights within the basket, hedged episodically by the A1 short state — i.e., alts are never shorted individually. Small pre-registered budget; expected outcome per priors: fails to beat equal-weight; kill quickly if so" — its tilt alone, as numbered decisions with code-level definitions: a compute module `cli/alpha/b3.py`, one committed research subject with its evaluate-only pre-flight twin, the family key `B3` in bucket B, registered through `zcrypto research eval --register` and spec 00133's trial-attempts log. Spec 00144 is this spec's form — a family's first trial on the adopted ensemble, its arm A, limits, costing, bar and operating model — and spec 00146 the latest form of its pre-flight, notes and close. The landed record spends one trial of Bucket B's shared budget: 11 remain today, 10 after.

## The measured basis

Every figure below was measured on 2026-10-25 in this branch's worktree, its base develop's `624497e22`, with the trial's code absent — the books program between 07:14:52Z and 07:19:14Z, the cells program at 07:19:32Z, the count program at 07:19:45Z, the shell checks at 08:05:45Z — with `data/ohlc-full` symlinked read-only from the main checkout's `data/` and the main checkout's `.local/trial-attempts.jsonl` read, never written. They read closes, weights, ranks, positions, limit engagement and turnover only: no return of either arm is read — no net-of-cost series, head-to-head or bar leg — and neither subject runs over the real set. The books program's own book function computes each tilted arm's base returns on its way to the positions, since the vol target sizes on them, reads them nowhere else and never calls `run_backtest`, so no tilted arm's return series exists in it; `a2_book_returns`, which it calls for arm A and for the untilted check, computes arm A's internally, unread. Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output. The first version's basis — the same programs over the rank among the longs alone — stands in commit `896cede77`; its figures quoted below as the alternative set aside are that basis's.

**The books**, a first program — the union read the way the subject reads it, arm A by trial 58's own `_b4_ensemble`, and each arm's book untilted and tilted by its own expression of `a2_book_returns` with the tilt written out, never through the trial's code, the books kept under `.tmp/` for the second:

```python
import json
import math
import pickle
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

M, K, FLOOR = 180, 0.5, 8  # the amended design's values, fixed before this program ran
print("start", datetime.now(UTC).isoformat(timespec="seconds"))
reader = ObservedReader(Path("data"))
t0 = time.perf_counter()
h4_ts, h4_prices = subjects._capturing_union(reader, "ohlc-full", 240, None, None, False)
n = len(h4_ts) - 1
print(f"reads {time.perf_counter() - t0:.1f} s; union {len(h4_ts)} stamps, {h4_ts[0]} -> {h4_ts[-1]}, return indices {n}")
block = reader.block()
print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in block.items()})
print("vouched", reader.vouched_status(), "holes", reader.holes())
record_58 = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[57])
eur_58 = {p: h for p, h in record_58["datasets"]["ohlc-full"]["files"].items() if "/EUR/" in p}
print("the block's files are record 58's ten EUR files, and no other:", block["ohlc-full"]["files"] == eur_58)
fed = _ffill_btc(h4_prices)
configs = [
    A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lb, tv in subjects._B2_A2_ARMS
]
labels = [f"{'-'.join(map(str, c.lookbacks))}@{c.target_vol}" for c in configs]
score = {a: [None if k < M or p[k] is None or p[k - M] is None else p[k] / p[k - M] - 1 for k in range(n)] for a, p in fed.items()}


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


def book(prices, config, tilted):
    """`a2_book_returns`' positions, its weights tilted at each close where `tilted`; the base returns size the vol target
    and are not read."""
    length = len(prices["BTC"])
    union_ts = list(range(length))
    asset_ts = {a: [k for k, p in enumerate(v) if p is not None] for a, v in prices.items()}
    directions = _asset_directions_a2(prices, union_ts, asset_ts, config=config)
    returns = {a: _asset_returns(v) for a, v in prices.items()}
    w = _inverse_vol_weights(prices, lookback=config.basket_lookback)
    baskets, longs, ratios, unscored = [], [], [], 0
    if tilted:
        out = []
        for k in range(length - 1):
            d = {a: directions[a][k] for a in prices}
            unscored += sum(1 for a in w[k] if w[k][a] > 0 and score[a][k] is None)
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
t1 = time.perf_counter()
books["arm_a"] = subjects._b4_ensemble(fed)
t2 = time.perf_counter()
print(f"arm A, _b4_ensemble's three A2 runs, {t2 - t1:.1f} s")
plain = [book(fed, c, False)[0] for c in configs]
t3 = time.perf_counter()
print(f"the program's book untilted, three arms, {t3 - t2:.1f} s")
print("  each arm's untilted book is a2_book_returns' asset_positions bit for bit:", [p == a2_book_returns(fed, config=c)["asset_positions"] for p, c in zip(plain, configs)])
t4 = time.perf_counter()
tilted = [book(fed, c, True) for c in configs]
t5 = time.perf_counter()
print(f"the program's book tilted, three arms, {t5 - t4:.1f} s")
books["arms_a"] = plain
books["arms_b"] = [t[0] for t in tilted]
books["baskets"] = {label: t[1] for label, t in zip(labels, tilted)}
books["longs"] = {label: t[2] for label, t in zip(labels, tilted)}
for label, t in zip(labels, tilted):
    print(f"  {label}: the tilted weight over the untilted, where it moved, min {t[3][0]!r} max {t[3][1]!r}; weighted assets with no score {t[4]}")
print("the three arms' basket sizes are one list:", books["baskets"][labels[0]] == books["baskets"][labels[1]] == books["baskets"][labels[2]])
Path(".tmp/iter192/basis2/books.pickle").write_bytes(pickle.dumps(books))
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-25T07:14:52+00:00
reads 0.4 s; union 27338 stamps, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00, return indices 27337
block ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69 {'ohlc-full': (10, 173373, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)'} holes {}
the block's files are record 58's ten EUR files, and no other: True
arm A, _b4_ensemble's three A2 runs, 64.7 s
the program's book untilted, three arms, 63.6 s
  each arm's untilted book is a2_book_returns' asset_positions bit for bit: [True, True, True]
the program's book tilted, three arms, 67.0 s
  20-50-100@0.12: the tilted weight over the untilted, where it moved, min 0.4152870051510151 max 1.8333902574501726; weighted assets with no score 0
  60-120-240@0.1: the tilted weight over the untilted, where it moved, min 0.3988876385150849 max 1.7981735434348523; weighted assets with no score 0
  60-120-240@0.12: the tilted weight over the untilted, where it moved, min 0.3988876385150849 max 1.7981735434348523; weighted assets with no score 0
the three arms' basket sizes are one list: True
end 2026-10-25T07:19:14+00:00
```

**The cells**, a second program over the first's books — arm A against record 58's, the limits, the basket per close, the tilted closes per arm, the first engagement, the closes where the books differ and turnover, written out with `cli/alpha/b4.py`'s limit functions, never through the trial's code:

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
b = pickle.loads(Path(".tmp/iter192/basis2/books.pickle").read_bytes())
h4_ts, labels = b["h4_ts"], b["labels"]
close = close_grid(h4_ts)
n = len(close)
assets = list(b["arm_a"])
legs = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}
record_58 = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[57])


def per_year(flags):
    out = {}
    for k, flag in enumerate(flags):
        out[close[k].year] = out.get(close[k].year, 0) + int(flag)
    return {y: c for y, c in sorted(out.items()) if c}


def limited(positions):
    factors, engaged = limit_factors(base_exposures(positions, legs))
    return scale_bars(positions, factors), engaged, factors


arm_a = b["arm_a"]
mean_plain = {a: [statistics.mean(arm[a][k] for arm in b["arms_a"]) for k in range(n)] for a in assets}
print("arm A, _b4_ensemble's, equals the mean of the program's three untilted arms bit for bit:", mean_plain == arm_a)
print("turnover of arm A", repr(book_turnover(arm_a)), "; record 58's turnover_a", repr(record_58["metrics"]["turnover_a"]))
raw_b = {a: [statistics.mean(arm[a][k] for arm in b["arms_b"]) for k in range(n)] for a in assets}
lim_a, engaged_a, factor_a = limited(arm_a)
lim_b, engaged_b, factor_b = limited(raw_b)
print("arm A after the limits bit-identical:", lim_a == arm_a, {k: sum(v) for k, v in engaged_a.items()})
print("arm B after the limits bit-identical:", lim_b == raw_b, {k: sum(v) for k, v in engaged_b.items()}, "bars scaled", sum(f != 1.0 for f in factor_b))
print(f"arm B: max gross {max(math.fsum(abs(lim_b[a][k]) for a in assets) for k in range(n)):.6f}")
basket = b["baskets"][labels[0]]
floor = [m >= 8 for m in basket]
first_floor = floor.index(True)
print(f"the basket per return index, histogram {dict(sorted(Counter(basket).items()))}")
print(f"  min {min(basket)}, mean {statistics.fmean(basket):.4f}, max {max(basket)}; 8 or more at {sum(floor)}, first at return index {first_floor}, close {close[first_floor].isoformat()}; below 8 after it {sum(not f for f in floor[first_floor:])}")
print("  8 or more per close year", per_year(floor))
for label in labels:
    longs = b["longs"][label]
    tilted = [t > 0 for t in longs]
    first = tilted.index(True)
    print(f"{label}: tilted at {sum(tilted)} return indices, first {first}, close {close[first].isoformat()}; longs tilted where it tilts, mean {statistics.fmean(t for t in longs if t):.4f}, min {min(t for t in longs if t)}, max {max(longs)}")
    print(f"  tilted per close year {per_year(tilted)}; at 8 or more ranked with fewer than 2 long {sum(f and not t for f, t in zip(floor, tilted))}")
for label, arm_a_i, arm_b_i in zip(labels, b["arms_a"], b["arms_b"]):
    print(f"{label}: first return index whose positions differ from the untilted arm's {next((k for k in range(n) if any(arm_b_i[a][k] != arm_a_i[a][k] for a in assets)), n)}")
differ = [any(lim_b[a][k] != arm_a[a][k] for a in assets) for k in range(n)]
start = next((k for k in range(n) if differ[k]), n)
print(f"the ensemble: first return index whose positions differ, {start}, close {close[start].isoformat()}; returns from it {n - start}, {(n - start) / 2190:.2f} years of 2,190")
print(f"  positions differ at {sum(differ)} return indices, per close year {per_year(differ)}; before the start {sum(differ[:start])}")
untilted = [all(not b["longs"][label][k] for label in labels) for k in range(n)]
print(f"  from the start, return indices with no arm tilted {sum(untilted[start:])}, of them with positions differing {sum(u and d for u, d in zip(untilted[start:], differ[start:]))}")
turnover_a, turnover_b = book_turnover(arm_a), book_turnover(lim_b)
print(f"turnover A {turnover_a!r} B {turnover_b!r}, B over A {100 * (turnover_b / turnover_a - 1):.2f} %; B - A {turnover_b - turnover_a:.4f}")
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-25T07:19:32+00:00
arm A, _b4_ensemble's, equals the mean of the program's three untilted arms bit for bit: True
turnover of arm A 146.18534602048504 ; record 58's turnover_a 146.18534602048504
arm A after the limits bit-identical: True {'gross': 0, 'net': 0, 'margin': 0}
arm B after the limits bit-identical: True {'gross': 0, 'net': 0, 'margin': 0} bars scaled 0
arm B: max gross 0.998300
the basket per return index, histogram {0: 180, 1: 4336, 2: 3182, 3: 760, 4: 2795, 5: 2605, 6: 1389, 7: 607, 8: 1407, 9: 1254, 10: 8822}
  min 0, mean 5.8723, max 10; 8 or more at 11483, first at return index 15672, close 2020-12-03T12:00:00+00:00; below 8 after it 182
  8 or more per close year {2020: 171, 2021: 2190, 2022: 2190, 2023: 2190, 2024: 2013, 2025: 2189, 2026: 540}
20-50-100@0.12: tilted at 7757 return indices, first 15672, close 2020-12-03T12:00:00+00:00; longs tilted where it tilts, mean 6.5804, min 2, max 10
  tilted per close year {2020: 145, 2021: 1601, 2022: 1304, 2023: 1634, 2024: 1415, 2025: 1343, 2026: 315}; at 8 or more ranked with fewer than 2 long 3726
60-120-240@0.1: tilted at 7865 return indices, first 15672, close 2020-12-03T12:00:00+00:00; longs tilted where it tilts, mean 6.4127, min 2, max 10
  tilted per close year {2020: 171, 2021: 1690, 2022: 1253, 2023: 1661, 2024: 1444, 2025: 1304, 2026: 342}; at 8 or more ranked with fewer than 2 long 3618
60-120-240@0.12: tilted at 7865 return indices, first 15672, close 2020-12-03T12:00:00+00:00; longs tilted where it tilts, mean 6.4127, min 2, max 10
  tilted per close year {2020: 171, 2021: 1690, 2022: 1253, 2023: 1661, 2024: 1444, 2025: 1304, 2026: 342}; at 8 or more ranked with fewer than 2 long 3618
20-50-100@0.12: first return index whose positions differ from the untilted arm's 15672
60-120-240@0.1: first return index whose positions differ from the untilted arm's 15672
60-120-240@0.12: first return index whose positions differ from the untilted arm's 15672
the ensemble: first return index whose positions differ, 15672, close 2020-12-03T12:00:00+00:00; returns from it 11665, 5.33 years of 2,190
  positions differ at 9691 return indices, per close year {2020: 171, 2021: 1904, 2022: 1762, 2023: 1944, 2024: 1805, 2025: 1717, 2026: 388}; before the start 0
  from the start, return indices with no arm tilted 2816, of them with positions differing 842
turnover A 146.18534602048504 B 188.39442044111686, B over A 28.87 %; B - A 42.2091
end 2026-10-25T07:19:35+00:00
```

What they establish:

- **The block.** The ten EUR assets' 240-minute files of `ohlc-full` form the block the record will carry, `compute_hash` `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`: 10 files, 173,373 rows, 2013-09-10 20:00 → 2026-03-31 20:00, `vouched_status` `checked (36 vouched hashes)`, no hole. Its files are record 58's ten EUR files and no other, and its hash is record 49's `dataset_hash` (the count program below), the one block among records 45–58's that holds those ten files alone.
- **The union.** 27,338 stamps, 27,337 return indices, records 45–58's.
- **Arm A is record 58's.** `_b4_ensemble(fed)` — trial 58's own function — equals the mean of the program's three untilted arms bit for bit, each of those `a2_book_returns`' `asset_positions` bit for bit, and its turnover is record 58's stored `turnover_a`, 146.18534602048504, to the last digit.
- **The basket.** Every asset with an inverse-vol weight and a score is ranked, whatever its direction, so the basket is one list for the three arms. Over the 27,337 return indices it holds 0 to 10 assets, 5.8723 on average; it holds 8 or more at 11,483 (42.01 %), first at return index 15,672 (close 2020-12-03 12:00) — every close of 2021, 2022 and 2023, 2,013 in 2024 and 2,189 in 2025 — and below 8 at 182 return indices after the first.
- **Every weighted asset has a score.** At `M` = 180 a weight already needs 180 present closes before the close (`_inverse_vol_weights`' window), so no weighted asset lacks a score: the unranked-for-history clause decides no close of this set.
- **The tilted closes.** Where the basket holds 8 or more, the tilt moves weights wherever 2 assets or more are long: on the arm on lookbacks (20, 50, 100) at 7,757 return indices, 6.5804 longs on average where it does; on the two arms on (60, 120, 240), which share their directions, at 7,865, 6.4127 on average. At 3,726 and 3,618 return indices the basket holds 8 or more with fewer than 2 assets long, and nothing tilts.
- **The tilt's size.** Where the tilt moves a weight, the tilted weight lies between 0.4153 and 1.8334 times the untilted on the (20, 50, 100) arm and between 0.3989 and 1.7982 on the other two — the multiplier `1 + k·z` in [0.5, 1.5], the rescale to the longs' sum widening it inside [1/3, 3] (D3).
- **The first engagement.** Every arm first tilts at return index 15,672 (close 2020-12-03 12:00), the basket's first close at 8, and every arm's positions first differ from its untilted book's there; so the ensemble's do, and the primary read holds 11,665 return indices, 5.33 years of 2,190. Before 15,672 arm B's positions are arm A's bit for bit.
- **Where the books differ.** At 9,691 return indices, per close year from 171 (2020) to 1,944 (2023). From the first engagement on, at 2,816 return indices no arm tilts, and at 842 of those the positions still differ: the vol target reads the last 180 base returns, which a tilt earlier in the window moved (D3).
- **The limits.** No bar of either arm engages §10's gross cap, net band or margin floor: both arms' largest gross exposure is 0.9983, so each comes out of the limits bit-identical.
- **The turnover.** Arm B trades 188.39442044111686 against arm A's 146.18534602048504, 28.87 % more: the added 42.2091 costs, at 0.006 per side, 0.2533 in per-bar return summed. The books are one to the bit before the first engagement, so all of it falls inside the primary read's 11,665 returns: 0.0475 a year there (2.17e-05 per bar), the hurdle the deciding head-to-head carries, against 0.0203 a year spread over the full window's 27,337, beside arm A's own 0.0703 a year over those (record 45's `arm_a_spot_drag_pct_yr` on the same scale) — the cost arm B carries into the head-to-heads before any return of its own, each figure from the two turnovers alone.
- **The first version's form, for comparison** (commit `896cede77`'s basis): ranked among the assets held long alone, the tilt met 8 ranked names at 3,574 and 3,244 of the 27,337 return indices (13.07 % and 11.87 %), first moved a position at return index 573, in 2014, between BTC and LTC, and traded 238.02367495477256, 62.82 % more than arm A, its ranks churning with the long set's membership.

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
c = attempts.reconcile(lines, landed, log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF | {"B3": "B"})
families = ("B1", "B2", "B3", "B4")
print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in families}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])
print("required_n('B3')", c.required_n("B3"), "; families in the registry", sorted({r["family"] for r in c.records}), "; BUCKET_OF", budget.BUCKET_OF)
print("open attempts (a begin with no end):", sorted({x["attempt"] for x in lines if x["kind"] == "begin"} - {x["attempt"] for x in lines if x["kind"] == "end"}))
attempt = max(x["attempt"] for x in lines if x["kind"] == "begin")
begin = next(x for x in lines if x["kind"] == "begin" and x["attempt"] == attempt)
end = next(x for x in lines if x["kind"] == "end" and x["attempt"] == attempt)
took = datetime.fromisoformat(end["timestamp"]) - datetime.fromisoformat(begin["timestamp"])
print(f"attempt {attempt} ({begin['invocation']['subject']}): {took.total_seconds():.0f} s, failed {end['failed']}; log {lines[0]['log_id'][:8]}")
records = [json.loads(x) for x in Path("docs/reference/trial-registry.jsonl").read_text().splitlines()]
print("records whose dataset_hash is ff2e5700...:", [r["trial_id"] for r in records if r["dataset_hash"].startswith("ff2e5700695b")])
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("b3-rank-tilt", "b3-rank-tilt-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("names opening b3:", sorted(x for x in names if x.startswith("b3")))
for n_obs, n_trials in ((27_337, 1),):
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
a1_kill_bar(book, bench, n_trials=1, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=book, regime_slices=slices, benchmark_slices=bench_slices, decisive_start=1380, n_resamples=2000)
t1 = time.perf_counter()
net_of_cost_verdict(book, bench, mean_block=30, seed=42, n_resamples=2000)
t2 = time.perf_counter()
print(f"synthetic, {n} Gaussian returns: one a1_kill_bar {t1 - t0:.2f} s, one net_of_cost_verdict {t2 - t1:.2f} s")
```

Its output, whole:

```text
read at 2026-10-25T07:19:45+00:00
{'B1': 5, 'B2': 7, 'B3': 0, 'B4': 2} remain 11 []
required_n('B3') 1 ; families in the registry ['A1', 'B1', 'B2', 'B4', 'P1'] ; BUCKET_OF {'A1': 'A', 'B1': 'B', 'B2': 'B', 'B4': 'B', 'P1': None}
open attempts (a begin with no end): []
attempt 11 (b4-sol-noborrow-rolling): 309 s, failed None; log 60c9f39c
records whose dataset_hash is ff2e5700...: [49]
b3-rank-tilt equals or opens with a hyphen: [] ; it opens: []
b3-rank-tilt-preflight equals or opens with a hyphen: [] ; it opens: []
names opening b3: []
27337 returns at n_trials 1, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.009949, annualised 0.4656
synthetic, 27337 Gaussian returns: one a1_kill_bar 11.10 s, one net_of_cost_verdict 5.56 s
```

- **The count**: the registry holds no B3 record and the trial-attempts log no orphan and no open attempt, so `required_n("B3")` is 1 — this trial — the count it declares (D7); bucket B has spent 14 of 25 (B1 5, B2 7, B4 2), 11 remaining, 10 once this trial's record lands. The registry's families are A1, B1, B2, B4 and P1: `B3` is no key yet, and the benchmark family's B3 (master plan §9, the frozen bar's "B3+vt-dynamic") is no registry key and never was (D8).
- **The names**: no registered or retired subject's name equals `b3-rank-tilt` or `b3-rank-tilt-preflight` or opens either with a hyphen, neither opens one, and no name opens `b3` (D8).
- **The DSR leg**: at `var_trials` 0.0 the expected maximum Sharpe is 0 at any count, so at count 1 the leg is the PSR against 0: over the 27,337 returns `dsr_pass` needs an annualised net Sharpe above 0.4656, spec 00144's figure (D7).
- **The run's time**: record 59's `--register` run took 309 s (attempt 11 of log `60c9f39c`). This trial's inputs half — three A2 runs for arm A, three tilted runs for arm B — took 134.75 s as the plan's data-gated case, run on the authoring tree; one `a1_kill_bar` over 27,337 synthetic returns took 11.10 s and one `net_of_cost_verdict` 5.56 s. The trial computes seven bars and two head-to-heads, about 135 + 78 + 11 ≈ 225 s, one process well under 600 s; its pre-flight the inputs half and one bar, about 146 s.

Specs 00144 and 00146 frozen, and arm A's code path since record 59's run:

```text
$ sha256sum docs/specs/00144-b4-ratio-legs-design.md docs/specs/00146-b4-sol-noborrow-rolling-design.md; python3 -c 'import json; lines = open("docs/reference/trial-registry.jsonl").read().splitlines(); [print("record", r["trial_id"], r["spec_hash"], r["invocation"]["commit"]) for r in (json.loads(lines[57]), json.loads(lines[58]))]'; git log --oneline 273eaa58ea492220c1faf874cce7123b9599da0b..624497e22 -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat
f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89  docs/specs/00144-b4-ratio-legs-design.md
af90620c9580651ab17e1d5ec6298e5a627fa1dda7d748175929d031be2a6291  docs/specs/00146-b4-sol-noborrow-rolling-design.md
record 58 f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89 93c0ec7af12323c3cda294481854e9cf878802d6
record 59 af90620c9580651ab17e1d5ec6298e5a627fa1dda7d748175929d031be2a6291 273eaa58ea492220c1faf874cce7123b9599da0b
```

- **Specs 00144 and 00146 are frozen**: their sha256s are records 58's and 59's `spec_hash`; neither is edited.
- **The code path since record 59's run** at `273eaa58e`: the log to this branch's base prints nothing — no commit has touched it, so the arm A, limits, costing and bar this trial reuses are records 58's and 59's.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial runs under one, the session holding this branch's worktree, `.claude/worktrees/iter192`, on the workstation `zcrypto-ops`, whose main checkout holds the one listed trial-attempts log (`docs/reference/trial-attempt-logs.txt`). No other session runs a bucket-B subject while this branch is open — B1, B2 and B4 are closed and their subjects retired — no second machine and no restored or copied log; each of those is spec 00133's to count and refuse, not this spec's to design for.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Both read `data/ohlc-full`, a symlink to the main checkout's frozen, attested set; a run writes nothing under it and makes no network call, and nothing this spec runs has a live writer.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained; this worktree is their one writer while the branch is open. `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and landed-count literal before anything else lands (D9).

## Hypothesis (trial 1, pre-registered by this spec's sha256)

Master plan §5's B3, its tilt alone: a simple cross-sectional momentum rank across the basket carries information the per-asset trend signal does not — among the ten assets, the ones that rose most over the last 30 days keep outrunning the ones that rose least — so **the adopted A2-4h ensemble with each arm's inverse-vol weights of the assets it holds long tilted at every close by their rank in the whole basket on the trailing 180-close simple return — each long's weight times 1 + 0.5·z, 1.5 times at the basket's top and 0.5 times at its bottom, the longs rescaled to their untilted sum — wherever the basket ranks 8 assets or more, has a higher mean net-of-cost return than the untilted ensemble from the first close the tilt moves a position, net of each asset's own turnover at 0.006 a side.** Arm A is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45–58 built it; arm B the same three arms with the tilt, A2's configuration unchanged. One knob, the tilt at its pre-registered values, `M` = 180, `k` = 0.5 and a basket of 8. It is judged by D7's matrix on its own record; what its verdict changes is D10's.

## D1 — the pick: B3's first step is trial 1, the tilt alone, directly

- The owner's family pick, "B3 (Recommended)", and run instruction, quoted in the Ruling; B3 under T0016. **The loop's call (Decision: 1 of the `[iter-192]` pick entry)**: trial 1 directly, the A2-4h ensemble's long weights tilted by a simple cross-sectional momentum rank over the whole basket, at the closes where 8 assets or more rank, long-only, no borrow and no carry — one knob, so a verdict attributes to the tilt; master plan §5's "kill quickly" is one slot. One iteration, one branch, this spec and its plan, one plan review, one task loop; one trial subject with its pre-flight twin, one bar, one matrix, one record.
- The alternatives weighed and set aside: **trial 1 as master plan §5 writes B3 whole, the tilt with the A1-short BTC overlay** — two knobs in one trial, a reject unattributable; the overlay carries the borrow the A family measured as a structural ~5 %/yr drag (T0016's first finding) and §12's borrow-unavailable stress rung; the adopted ensemble already goes flat per asset in a downtrend; **a no-slot reading first** — the within-basket rank spread's forward returns by quantile, screening before a slot (iter-186's and iter-190's form) — one cell with no alternative cell to choose between, and an iteration spent before the trial the master plan's own prior expects to kill.
- The budget: the landed record spends one of Bucket B's 11 remaining (spec 00133 D5; `BUDGET["B"]` 25, B1 5, B2 7 and B4 2 spent); a stop, a refused build or a refusal from the count spends none.

## D2 — the instrument: frozen `ohlc-full`, full history, the ten EUR assets alone

- **The loop's call**: `--dataset ohlc-full`, no `--window`, no `--as-of` — the standing instrument ruling's set, 2013-09-10 → 2026-03-31, the one window on which arm A is recorded clearing the ratified bar; the ten EUR assets' 4h union exactly as records 45–58 read it, `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices; no other pair; the decisive window from index 1,380; the arms on `_ffill_btc`'s BTC-only fill, the benchmark on the raw prices. The record's block is the ten files', `ff2e5700…01719a69` (measured), record 49's.
- The reads refuse, before any book, a window holding fewer than `_DECISIVE_START` + 2 return indices and one none of whose return indices closes in a calendar year the worst-slice leg reads, the stub years left out — trial 58's two refusals, in the subject's terms — and `--as-of`, before any read: "<subject> evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset".

## D3 — the arms: arm A the adopted ensemble, arm B its three arms with the tilt

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as trial 58 built it: `_b4_limited(_b4_ensemble(fed))`, `fed = _ffill_btc(h4_prices)`, the three arms `_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year, each asset's equal-weight mean, then §10's limits (D5) — measured equal to record 58's arm A, its turnover record 58's to the last digit.
- **Arm B** is the same three arms, each arm's book built as `a2_book_returns` builds it except that at every close its inverse-vol basket weights are passed through the tilt before the base returns, the vol target and the positions read them; their equal-weight mean, then the limits.
- **The tilt at close k** (the loop's call, the controller's amendment of the first version): **the ranked set is the basket** — every asset with an inverse-vol weight above 0 and a momentum score at that close, whatever its direction, n of them — and `z = (2·rank − (n + 1)) / (n − 1)` is each one's centred ascending rank of the score over that set, ties at their average rank, the strongest `+1` and the weakest `−1`. **The breadth floor**: the tilt engages at a close only when n ≥ 8 — master plan §3's own number, "Any cross-sectional tilt needs enough names to rank — meaningful below ~8 it is not"; below it every weight is untilted. **Applied to the longs alone**: each asset of the basket with a direction above 0 has its weight multiplied by `1 + k·z`, its z from the basket's rank, and the tilted long weights are rescaled so their sum equals their untilted sum — a reallocation within the long book; a flat asset's rank counts in the basket and its weight is untouched; with no asset long nothing tilts. **Author's call — fewer than 2 longs leaves every weight untilted**: a single long's rescale returns its own weight, so the code returns the weights as they are, keeping the book bit-identical where the arithmetic would change only rounding. The score is the trailing simple return over `M` closes, `p[k] / p[k − M] − 1` on the union's BTC-filled closes, known at close k as the weights are; an asset with no close at k or at k − M has no score and is out of the basket.
- **The values** (the loop's call, fixed before any measurement): `M = 180` closes (30 days), the ensemble's own `_B2_LOOKBACK` — no new free window, and inside the 1–4-week band where the cross-sectional crypto momentum literature finds the effect; `k = 0.5`, a half-strength tilt whose multiplier lies in [0.5, 1.5], never zeroing an asset; after the rescale a long's weight lies between 1/3 and 3 times its untilted weight (measured: 0.3989 to 1.8334), long-only by construction; the floor 8, the master plan's. The basket reads no direction, so it is one list for the three arms; each arm tilts its own longs.
- **Bit for bit until the tilt first moves a position.** Before the first close with a basket of 8 or more and 2 longs or more, every weight is the untilted dict itself, so the base returns, the vol target and the positions are arm A's to the bit. From the first tilted close on, arm B's positions differ from arm A's at a close with a tilted weight, and also at a close with none where the vol target's 180-return window holds a base return a tilt moved (measured: 842 return indices); **Author's call — the claim the plan's test holds is therefore the weights' and the books' as they are**: the book at `k = 0` reproduces `a2_book_returns` to the bit, the book at `k = 0.5` is `a2_book_returns` run on the tilted weights to the bit, and arm B's positions equal arm A's before the first tilted close — never "equal at every untilted close", which the vol target makes false.
- **The tilt's first engagement**, `tilt_first_engaged`, is the first return index at which arm B's limited positions differ from arm A's, read off the two books — 15,672 (close 2020-12-03 12:00, measured), the basket's first close at 8 and every arm's first tilted close.
- **Author's call — where the tilt lives**: a new module, `cli/alpha/b3.py`, holding `momentum_scores`, `centred_ranks`, `rank_tilt` and `b3_book_returns` — `a2_book_returns`' body with each close's weights passed through `rank_tilt`, returning `a2_book_returns`' keys, `ranked`, each close's basket size, and `tilted`, each close's count of longs tilted; `cli/alpha/a2.py` and every existing function unchanged, arm A being adopted code. `b3_book_returns` refuses a config that is no `A2Config`, a score lookback or a floor below 2 and a strength outside [0, 1) — at 1 the weakest long's weight would be zeroed — and `centred_ranks` refuses fewer than 2 scores. The plan's tests hold the module to known answers: `k = 0` reproduces `a2_book_returns` to the bit; a planted rank order over a basket with a flat asset in it tilts the longs by their basket ranks inside the longs' sum and leaves the flat asset's weight untouched; ties at their average rank; a basket of 7 untilted and of 8 tilted; fewer than 2 longs untilted; no asset ranked without a weight or a score; no look-ahead in the prices — the score and the ranks read no price after close k, and the book's positions to k are unmoved by any price after k, every close's presence kept: the basket's membership, as arm A's own inverse-vol weights, reads whether close k + 1 exists (A2's `_inverse_vol_weights` drops an asset at k when its k + 1 close is missing), a property both arms share.
- No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b4.py`, `cli/risk/*`, `cli/costs/*`, `cli/portfolio/*` or any adopted artifact.

## D4 — the costing: trial 58's, no carry

- The returns: `_asset_returns(fed[a])` for each of the ten assets. Every book is costed by trial 58's `_b4_net(positions, returns, stress=…)` — `net_of_cost` at `stress × 0.006` per side on each asset's own turnover from flat, a missing return read as 0.0, less `shortfall_carry` of the book's BTC shortfall at `stress × 0.0002` — and a long-only book holding no ratio leg has no shortfall, so its carry is 0.0 at every bar: no short, no borrow, no carry. The kill bar's cost-stressed series is `stress` 1.5. **The loop's call**: trial 58's function unchanged, so arm A's net is record 58's arm A's to the bit.

## D5 — §10's limits: trial 58's wiring on the ten assets alone

- Both arms pass `_b4_limited` — `limit_factors` over `base_exposures(positions, _B4_LEGS)`, which with no ratio leg in the book are its own positions — the gross cap 1.5 / 2.0, the net band −0.5 … +1.0, the margin floor 2.5, in `cli/risk/limits.py`'s order, one factor per bar. No bar of either arm engages a limit (measured: both arms' largest gross 0.9983), so both come out bit-identical; arm B's engaged bars per limit and close year and arm A's totals are recorded.

## D6 — the contamination, stated

- **B3's first look**: no B3 record or reading exists, its count is 1, and the measured basis reads weights, ranks, positions, limit engagement and turnover, never a return.
- **The instrument, window, arm A, costing and bar are records 45–59's**, whose arm A clears the bar on this window (record 58's `arm_a_passes` 1; its anchors read again at the pre-flight, D9). B4's legs and B2's signals are not read.
- **The master plan's prior, in its own words**: "expected outcome per priors: fails to beat equal-weight; kill quickly if so". The prior phases' cross-sectional work (Binance/Qlib, the master plan's opening) refuted ML cross-sectional selection and the long/short quantile spread out of sample; this trial is neither — a rule-based tilt of a long-only basket's weights, no asset shorted.
- **The design was amended before the hash on engagement figures alone**: the first version's rank among the longs met the master plan's breadth line at 12–13 % of closes and traded 62.82 % more than arm A (commit `896cede77`'s basis); the amendment — the basket ranked, the floor 8, the longs tilted — was made on those engagement figures and the master plan's own words, no return of any book read. Its consequence, stated: the tilt is read from 2020-12-03 on, 11,665 return indices, the years 2021–2026, a narrower span than the full window the bar reads.
- **The turnover**: arm B trades 28.87 % more than arm A (measured), a cost at 0.006 per side, before any return of its own, of 0.0475 a year over the primary read's 11,665 returns, where all of it falls, against 0.0203 a year spread over the full window's 27,337 — known before the hash, the cost side of the head-to-heads, the deciding one's the higher.
- The author knows the ten assets' history only as market history, and no figure of this repository about any tilted book's returns.

## D7 — the bar, the head-to-heads, the matrix and the count

- **The bar**, record 58's call: `a1_kill_bar(net_b, bench, n_trials=1, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)` on the raw union prices, the stub years 2013 and 2026 out of the slices; the SPA grid blocks {30, 102} × seeds {42, 7, 1234}, the headline cell (30, 42), the five others recorded and never read. At count 1 and `var_trials` 0.0 the DSR leg is the PSR against 0: `dsr_pass` needs an annualised net Sharpe above 0.4656 over the 27,337 returns (measured). **Arm A's headline bar** is the same call on `net_a` at (30, 42), `_b4_arm_a_bar` unchanged, read `passes` 1 at the pre-flight, after the hash (D9).
- **The head-to-heads** (the loop's call): `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)`, primary from the tilt's first engagement — `first` = `tilt_first_engaged`, 15,672, `primary_returns` 11,665 (measured) — and over the full window (`first` 0) beside it; keyed `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_full` and `head_to_head_spa_p_full`. Before the first engagement the two books are one to the bit (D3), so the full-window read adds 15,672 zero differences to the primary's; the primary decides. Refused before any bar: fewer than 2 return indices from the first engagement — a `ValidationError` and so a refused build — which a dead knob, no position ever moved, is too.
- **The matrix** (the loop's call) — rows disjoint and covering every outcome:

| Arm A's bar and the tilt's engagement | Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from the tilt's first engagement) | Verdict |
| --- | --- | --- | --- |
| arm A's `passes` 0, or arm B's positions never differ from arm A's (a dead knob) | any | any | **instrument finding**: no verdict, the slot unspent |
| arm A passes, the tilt engaged | fail | any | **reject** |
| arm A passes, the tilt engaged | pass | mean outperformance > 0 and SPA p < 0.05 | **adopt** the tilt |
| arm A passes, the tilt engaged | pass | mean outperformance > 0, SPA p ≥ 0.05 | **park** (variant candidates: the tilt at another `M` or `k`; the A1-short BTC overlay) |
| arm A passes, the tilt engaged | pass | mean outperformance ≤ 0 | **reject** |

  Every quantity the matrix reads is a stored key read unrounded: `arm_a_passes`, `stamps_positions_differ`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`. No drawdown leg: B3's premise is return, not de-risking. The dead knob is read at the pre-flight, before the run (D9); under `--register` the build refuses it before any bar, so the rule's first row stands for a metrics dict alone. **Author's call — the park variants**: the tilt at another `M` or `k`, the two knobs the trial fixes beside the master plan's floor, and the A1-short BTC overlay, master plan §5's B3 whole (D1's option 2). **The rule is the trial's own function**: B4's `_b4_ratio_legs_verdict` reads a ratio leg's holding, which the tilt has no counterpart of. The subject declares it (spec 00129 D4), with its two instrument findings:

```python
def _b3_rank_tilt_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not m["stamps_positions_differ"]:
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"
```

- **The count**: 1, `_B3_N_TRIALS` — the family's true count with this trial, `required_n("B3")` measured 1 from the registry and the trial-attempts log (no B3 record, no orphan, plus one). Fixed by this spec's hash, never raised in place; spec 00133 D4 refuses a declared count below `required_n`, so a B3 attempt landing elsewhere before this run refuses it, the trial going back to the owner through T0016, a further count a new subject under a new spec.

## D8 — the engagement, the subjects, their record and the build

- **Author's call — the engagement**, both subjects' eleven keys, computed from positions and ranks alone (`_b3_engagement`): `tilt_first_engaged` and `primary_returns` (D3, D7); `stamps_positions_differ` and `positions_differ_per_year` (arm A's positions against arm B's — the dead-knob read); `tilted_per_year` (per arm, keyed `<lookbacks>@<target_vol>`, the return indices at which the arm's longs are tilted per close year); `ranked_assets_histogram` (per arm, the return indices with 0, 1, … 10 assets in the ranked basket) and `ranked_assets_mean` (per arm, the basket's mean size over every return index), the basket one list for the three arms, so that the record shows it so; `turnover_b` and `turnover_b_per_year` (the tilt's added trading beside the trial's `turnover_a`); `limit_engaged_per_year` (arm B's, per limit and close year) and `arm_a_limit_engaged` (arm A's totals per limit). Every year key is a close year (`close_grid`), every year the closes span keyed.
- **The trial's 44 keys**: record 58's 48 less its two ratio-leg keys (`ratio_first_weight`, `ratio_held_per_year`), its three carry keys (`shortfall_stamps_per_year`, `shortfall_mean_per_year`, `carry_per_year`) and its twin's three (`no_borrow_ann_sharpe_noc`, `no_borrow_head_to_head_mean_outperf_primary`, `no_borrow_head_to_head_spa_p_primary`), with the engagement's four added (`tilt_first_engaged`, `tilted_per_year`, `ranked_assets_histogram`, `ranked_assets_mean`). **The pre-flight's 28**: the engagement's eleven; arm A's seven anchors, `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`; and arm A's bar's ten, the keys `b2-arm-a-bar` declares (`dsr`, `dsr_pass`, `spa_p_value`, `spa_p_value_full`, `spa_pass`, `cost_stress_sharpe`, `cost_stress_pass`, `worst_slice_sharpe`, `worst_slice_pass`, `passes`).
- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00147-b3-rank-tilt-design.md"`, `_ASSETS`, intervals `(240,)`: the trial `b3-rank-tilt` — `metric_keys=_B3_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_b3_rank_tilt_verdict`, `no_verdict` "instrument finding: arm A fails the bar this window sets, or the tilt moves no position at any stamp; no verdict, the trial unspent", `family="B3"`, `n_trials=_B3_N_TRIALS` — and its evaluate-only twin `b3-rank-tilt-preflight` — `metric_keys=_B3_PREFLIGHT_KEYS`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). It costs arm A alone and reads no head-to-head; it builds arm B's positions, which its engagement reads. No incumbent: arm A is built in the run. The tilt's values are the constants `_B3_SCORE_LOOKBACK` 180, `_B3_STRENGTH` 0.5 and `_B3_FLOOR` 8.
- **Author's call — the names `b3-rank-tilt` and `b3-rank-tilt-preflight`**: spec 00141 D2's rule — no registered or retired subject's name equals either or opens it with a hyphen, and neither opens one (measured, and no name opens `b3`).
- **The family key `B3`** (the loop's call) — master plan §5's label for this family; the benchmark family's B3 (master plan §9, the frozen bar's "B3+vt-dynamic") is no registry key and never was (measured: the registry holds A1, B1, B2, B4 and P1). Spec 00133 D5's rule for a new family: it joins `BUCKET_OF` with its bucket, `"B3": "B"`, in a reviewed pull request quoting the ruling — the owner's "B3 (Recommended)" — and `tests/test_trial_registry_provenance.py`'s literal of `BUCKET_OF` changes with it: a guard change, proven by the plan's probe row (spec 00144 D9's form).
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B3`; `n_trials_in_family` 1; variant `B3-rank-tilt-a2eq-full-v1` (record 58's form, `<family>-<name>-a2eq-full-v1`); iteration `iter-192`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`; `attempt` the trial-attempts log's; `notes` caller text written before the run (D9).
- **The build in three halves**, spec 00144 D9's form: `_b3_reads(subject, reader, dataset, window, accept_holes)` — the union and D2's two window refusals, no compute; `_b3_inputs(reads)` — both arms' limited positions, their engaged bars, each arm's basket sizes and tilted longs and the returns, no return of a book; `_b3_metrics` and `_b3_preflight_metrics` from it. The plan's data-gated case runs the first two over the real set, and its fixture tests run the books on a union shorter than the reads admit. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `RiskError`, `ValidationError` — is a `SubjectError` naming the subject and its window.
- **The files the build touches, a closed list**: `cli/alpha/b3.py`, new; `cli/research/subjects.py` — three insertions: the import of `b3_book_returns`, the B3 block before `SUBJECTS` and its two entries, no existing function changed; `cli/registry/budget.py` — `BUCKET_OF`'s one line; `README.md`'s `--subject` row; the tests the plan names. No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b4.py`, `cli/features/*`, `cli/portfolio/*`, `cli/risk/*`, `cli/costs/*`, `cli/engine/*`, the existing subjects, specs 00128, 00133, 00137, 00144 and 00146, or any adopted artifact.

## D9 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00147-b3-rank-tilt-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append; (3) the data-gated basis test on the run's tree, with the subjects' two fixture rows and record 58's replay, which rebuilds trial 58's stored figures through the arm A, costing, bar and head-to-head code this trial's computes half shares with it; (4) the twin's plain eval, read in this order — (a) the block, `ff2e5700…01719a69`, `ohlc-full` `checked (36 vouched hashes)`; (b) arm A's seven anchors record 58's stored figures to the last digit — its `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown`, `turnover_a`, `benchmark_ann_sharpe_noc` and `benchmark_ann_sharpe_noc_decisive`, and the spot drag its `turnover_a` gives, `turnover_a / 27,337 × 0.006 × 2,190`; (c) the dead knob — arm B's positions differing from arm A's at some return index, `stamps_positions_differ` above 0, read before the engagement so that a dead knob is named as such; (d) the engagement equal to the measured basis — the plan's data-gated literals; (e) arm A's `passes` 1 — a failure of (a)–(e) an instrument finding, the run kept as a reading under iter-192 (`--reading --iteration iter-192 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent; (5) on a pass, the trial's one run, `--register --iteration iter-192 --family B3 --n-trials 1 --variant B3-rank-tilt-a2eq-full-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10); (6) the record's checks and its commit — the registry line, the decisions-log verdict entry and the landed-count literal together, since the tie tests hold only over the three.
- **The hash rule**: before (1), nobody reads or computes arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — by code, a program or arithmetic over a stored figure — nor runs `b3-rank-tilt` or its twin over the real set; weights, ranks, positions, exposures, limit engagement and turnover are allowed, and are what the measured basis and the data-gated test hold. `a2_book_returns` and `b3_book_returns` compute each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; no program reads any of them (spec 00145 D8's words). The `M` = 180, `k` = 0.5 and floor 8 values were fixed before the measurements they read, and the measured basis reads engagement only — never a return by `M`, `k` or the floor. No net-of-cost return of arm B is computed over the real data before the trial's `--register` run.
- **The notes, written before the run** (spec 00137 D10's): the subject over `ohlc-full`, full history; the arms, the tilt and its three values, the costing and the limits; the hypothesis; the count and `var_trials` 0.0; the read from the tilt's first engagement deciding and the full-window read beside it; the contamination D6 states; the pre-flight's figures, quoted — arm A's seven anchors and the bar's `dsr` and SPA p; the park variants; the matrix pre-registered by this spec's sha256.
- A refusal from the count, a refused build, a stop by the rule under `--register`: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0016's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D10 — what a verdict changes

- **Adopt** is recorded, never deployed. The tilt reweights the ten EUR pairs the engine's book already trades — `CrossfreqSystemConfig.assets`, the pairs `cli/engine/feeders.py`'s `load_minimums` keeps as its `quote == "EUR"` entries — so it adds no instrument the venue adapter does not hold, unlike a ratio pair; its live form is a change to the adopted book's A2 sleeve, which `build_crossfreq_system_fast` runs in `cli/engine/cycle.py`. Its path, the owner's, in order: a P1 combination trial over record 47's book carrying the tilt, outside every bucket's budget, then T0123's promotion path (spec 00144 D11's form, without its engine change); T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts.
- **Park** names its variant candidates in the record — the tilt at another `M` or `k`, and the A1-short BTC overlay — each a new trial of the shared budget, put to the owner through T0016.
- **Reject** archives the hypothesis in the record and the decisions log.
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, a refused build or a refusal from the count — spends no trial; T0016 records what failed.
- **After any verdict, B3's next step is the owner's family call** — a park variant, the overlay, or closing the family — carried as T0016's B3 arm, rewritten in the branch's topic commit to wait on a `[iter-NNN] B3's next step after trial 1` entry, and recorded as that entry when the owner answers; a close is never the loop's. A stop keeps T0016's B3 arm on the stop — the trial run again once its cause is fixed, or B3 closed — waiting on the same entry.
- **Author's call — no retirement in this branch**, against `tests/retired_subjects.py`'s own rule: until the owner's call, a park variant or the overlay may run through `_b3_reads`, `_b3_inputs` and `b3_book_returns` at another `M` or `k`, and retiring the two subjects would deselect from CI the cases that guard those halves; the branch that records B3's next step retires them or keeps them.

## Out of scope

The park variants and every other B3 knob — the tilt at another `M` or `k`, another floor, the A1-short BTC overlay, a tilt of the flat assets' weights too, the rank among the longs alone, a score other than the trailing simple return; a no-slot reading of the rank spread; any window but the frozen set's full history, and `ohlc-rolling`; the tilt on the live path and the combination trial over record 47's book (D10); the C families, T0016's; any change to an existing function, subject, record or spec.
