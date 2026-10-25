# B4 trial 2 — SOL/BTC alone on the A2-4h ensemble, held to the book's own BTC, on `ohlc-rolling` as of 2026-10-10

**Ruling:** the owner, attended, 2026-10-24, after reading 6 found no cell with potential, verbatim: "one more trail on B4, then move on"; asked which variant trial 2 tests, "SOL/BTC no-borrow, rolling (Recommended)"; asked which family follows, "B3 (Recommended)". It stands in `docs/research/10.phase4-decisions.md` as `[iter-190] B4's next step after the leg reading — one more trial, SOL/BTC alone held to the book's own BTC on the rolling set, then B3, the owner's pick, attended, 2026-10-24 (Decision: 1)`, already on develop, so this spec writes no pick entry, only its conventions entry before its hash. "Move on" is read, as that entry records, as B4 closing after trial 2's verdict, whatever it is, and B3 opening. Standing and unchanged: the two `[iter-176]` rulings — the DSR leg binding at `var_trials` 0.0, and the spent holdout's window, 2026-04-01 → 2026-07-09, open to a search through `ohlc-rolling` and never reported as holdout or out-of-sample evidence. The instrument ruling "Frozen ohlc-full (Recommended)" (`[iter-181]`), under which trial 58 and reading 6 ran, is not this trial's: the owner's pick names the rolling set. Every call past those words and past what specs 00144 and 00145 fix is the author's, marked **Author's call** where it is made. **Iteration:** iter-191, branch `research/iter-191-b4-sol-noborrow-rolling`. **Topic:** T0016, its B4 arm. **Goal:** pre-register B4's trial 2 — the adopted A2-4h ensemble run on eleven instruments, its ten EUR assets and the venue's SOL/BTC pair, SOL/BTC's position held each bar to the book's own BTC, against the ten-asset ensemble — on `ohlc-rolling` as of its head on this workstation's mirror, so that the months past `ohlc-full`'s end, which reading 6 never saw, join the evidence; one committed trial subject with its evaluate-only pre-flight twin, registered through `zcrypto research eval --register` and spec 00133's trial-attempts log; then B4's close and B3 next, the owner's word. Spec 00144 is this spec's form and its books, costing, limits, bar, matrix and rule; spec 00145 the borrow-free funding and the contamination it states; spec 00128 D4–D7 the precedent for a trial read on `ohlc-rolling` as of a day. The landed record spends one trial of Bucket B's shared budget: 12 remain today, 11 after.

## The measured basis

Every figure below was measured on 2026-10-24 in this branch's worktree at develop's `459aed498`, before the trial's code was written into it, with `data/ohlc-rolling` and `data/ohlc-full` symlinked read-only from the main checkout's `data/`, no fetch run, and the main checkout's `.local/trial-attempts.jsonl` read, never written: the set program at 20:37:37Z, the books program between 20:38:01Z and 20:41:50Z, the cells program at 20:42:32Z, the count program at 20:42:55Z, then the DSR program and the shell checks. They read closes, weights, positions, per-base exposures, the BTC shortfall and the carry it implies, limit engagement and turnover only: no return of either arm is read — no net-of-cost series, head-to-head or bar leg — and neither subject runs over the real set. `a2_book_returns` computes each book's base returns on its way to the positions, since its vol target sizes on them; the programs read its `asset_positions` alone. Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

**The set**, a first program:

```python
from datetime import UTC, datetime
from pathlib import Path

from cli.data import rolling

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
root = Path("data/ohlc-rolling")
print("line days", [d.isoformat() for d in rolling.line_days(root)])
head = rolling.head(root)
print("head", head.day, head.relpath, head.sha256)
print("pairs", rolling.pairs(root))
for line in rolling.walk_chain(root, head.day):
    print(line.day, "files", len(line.files), "holes", line.holes, "notes", sorted(line.notes))
```

Its output, whole:

```text
read at 2026-10-24T20:37:37+00:00
line days ['2026-09-30', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10']
head 2026-10-10 index/2026/10/10.json fcb62a79fab7b58626f0cbd96ae40093a6dfc9e6ff51384cf25a5e9759dc44c4
pairs ('ADA/EUR', 'AVAX/EUR', 'BTC/EUR', 'DOGE/EUR', 'DOT/EUR', 'ETH/BTC', 'ETH/EUR', 'LINK/EUR', 'LTC/EUR', 'SOL/BTC', 'SOL/EUR', 'XRP/EUR')
2026-09-30 files 12 holes {} notes ['base_from', 'base_identity_digest', 'seam', 'vwap']
2026-10-01 files 12 holes {} notes []
2026-10-02 files 12 holes {} notes []
2026-10-03 files 12 holes {} notes []
2026-10-04 files 12 holes {} notes []
2026-10-05 files 12 holes {} notes []
2026-10-06 files 12 holes {} notes []
2026-10-07 files 12 holes {} notes []
2026-10-08 files 12 holes {} notes []
2026-10-09 files 12 holes {} notes []
2026-10-10 files 12 holes {} notes []
```

**The books**, a second program run twice — its part `rolling` reading the union of the ten EUR assets and SOL/BTC's 4h pair the way the subject reads them and building arm A and arm B's raw book, its part `full` building trial 58's arm A on `ohlc-full` — by their own three-arm expression, never through the trial's code, the books kept under `.tmp/` for the third program:

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
t0 = time.perf_counter()
if part == "rolling":
    h4_ts, h4_prices = subjects._capturing_union(reader, "ohlc-rolling", 240, None, "2026-10-10", False)
    frame = reader.read_rolling("ohlc-rolling", "SOL/BTC", 240, "2026-10-10", window=None, accept_holes=False)
else:
    h4_ts, h4_prices = subjects._capturing_union(reader, "ohlc-full", 240, None, None, False)
    frame = reader.read_series("ohlc-full", "SOL/BTC/240.parquet")
t1 = time.perf_counter()
ts = frame["ts"].to_list()
by_ts = dict(zip(ts, frame["close"].to_list(), strict=True))
sol = [by_ts.get(t) for t in h4_ts]
at = {t: k for k, t in enumerate(h4_ts)}
missed = {}
for k in range(at[ts[0]], len(h4_ts)):
    if sol[k] is None:
        missed[h4_ts[k].year] = missed.get(h4_ts[k].year, 0) + 1
print(f"reads {t1 - t0:.1f} s; union {len(h4_ts)} stamps, {h4_ts[0]} -> {h4_ts[-1]}, return indices {len(h4_ts) - 1}")
print("first stamp per asset", {a: h4_ts[next(k for k, p in enumerate(v) if p is not None)].isoformat() for a, v in h4_prices.items()})
print(f"SOL/BTC 240: rows {len(ts)}, first {ts[0]}, last {ts[-1]}, null closes {frame['close'].null_count()}, stamps no EUR asset has {sum(t not in at for t in ts)}; union stamps from its first: {len(h4_ts) - at[ts[0]]}, missed {sum(missed.values())}, per year {dict(sorted(missed.items()))}")
block = reader.block()
print("block", compute_hash(block), block, "vouched", reader.vouched_status(), "holes", reader.holes())
fed = _ffill_btc(h4_prices)
n = len(h4_ts) - 1
configs = [
    A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lb, tv in subjects._B2_A2_ARMS
]


def ensemble(prices):
    arms = [a2_book_returns(prices, config=c)["asset_positions"] for c in configs]
    return {i: [statistics.mean(arm[i][k] for arm in arms) for k in range(n)] for i in prices}


books = {"h4_ts": h4_ts, "h4_prices": h4_prices, "sol": sol}
t2 = time.perf_counter()
books["arm_a"] = ensemble(fed)
t3 = time.perf_counter()
print(f"arm A's three A2 runs {t3 - t2:.1f} s")
if part == "rolling":
    priced = fed | {"SOL/BTC": sol}
    books["raw_b"] = ensemble(priced)
    t4 = time.perf_counter()
    weights = _inverse_vol_weights(priced, lookback=180)
    books["first"] = next((k for k in range(n) if "SOL/BTC" in weights[k]), n)
    print(f"arm B's three A2 runs {t4 - t3:.1f} s, its weight path {time.perf_counter() - t4:.1f} s")
Path(f".tmp/iter191/basis/books-{part}.pickle").write_bytes(pickle.dumps(books))
print("end", part, datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole, part `rolling` and then part `full`:

```text
start rolling 2026-10-24T20:38:01+00:00
reads 0.7 s; union 28496 stamps, 2013-09-10 20:00:00+00:00 -> 2026-10-10 20:00:00+00:00, return indices 28495
first stamp per asset {'ADA': '2018-09-28T12:00:00+00:00', 'AVAX': '2021-12-21T12:00:00+00:00', 'BTC': '2013-09-10T20:00:00+00:00', 'DOGE': '2019-12-19T12:00:00+00:00', 'DOT': '2020-08-18T16:00:00+00:00', 'ETH': '2015-08-07T08:00:00+00:00', 'LINK': '2019-09-25T12:00:00+00:00', 'LTC': '2013-09-14T08:00:00+00:00', 'SOL': '2021-06-17T12:00:00+00:00', 'XRP': '2017-05-18T12:00:00+00:00'}
SOL/BTC 240: rows 11645, first 2021-06-17 12:00:00+00:00, last 2026-10-10 20:00:00+00:00, null closes 0, stamps no EUR asset has 0; union stamps from its first: 11647, missed 2, per year {2021: 1, 2024: 1}
block c05629c70826656ca225857f6b5b682bfc00a737a0feff91f78b57cf70c93295 {'ohlc-rolling': {'files': {'index/2026/10/10.json': 'fcb62a79fab7b58626f0cbd96ae40093a6dfc9e6ff51384cf25a5e9759dc44c4'}, 'rows': 196598, 'span': ['2013-09-10 20:00:00+00:00', '2026-10-10 20:00:00+00:00']}} vouched {'ohlc-rolling': 'chained (as of 2026-10-10, line fcb62a79fab7)'} holes {}
arm A's three A2 runs 68.7 s
arm B's three A2 runs 73.0 s, its weight path 18.8 s
end rolling 2026-10-24T20:40:42+00:00
start full 2026-10-24T20:40:46+00:00
reads 0.4 s; union 27338 stamps, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00, return indices 27337
first stamp per asset {'ADA': '2018-09-28T12:00:00+00:00', 'AVAX': '2021-12-21T12:00:00+00:00', 'BTC': '2013-09-10T20:00:00+00:00', 'DOGE': '2019-12-19T12:00:00+00:00', 'DOT': '2020-08-18T16:00:00+00:00', 'ETH': '2015-08-07T08:00:00+00:00', 'LINK': '2019-09-25T12:00:00+00:00', 'LTC': '2013-09-14T08:00:00+00:00', 'SOL': '2021-06-17T12:00:00+00:00', 'XRP': '2017-05-18T12:00:00+00:00'}
SOL/BTC 240: rows 10487, first 2021-06-17 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, null closes 0, stamps no EUR asset has 0; union stamps from its first: 10489, missed 2, per year {2021: 1, 2024: 1}
block 93560d45dc280eb16e8af2c30af508527665c9aaac211b23cf6856383ebe17b1 {'ohlc-full': {'files': {'ADA/EUR/240.parquet': '0646c3579ae296300943cecc472962e642416dd874db486d84546303f398bdd9', 'AVAX/EUR/240.parquet': '3b06646600836928ab5ce54525ae7b48691e2f65859796e35e531317879f22bd', 'BTC/EUR/240.parquet': '1cdfcb3cab6379349c56dce38043cf6a83a34adb5c754eaa303536141c9df0d9', 'DOGE/EUR/240.parquet': '1567307d3b3464f704d1da348b48faf532cee844489562b112eb7df9c2c9cd7b', 'DOT/EUR/240.parquet': '35f4373ec470d56626253ba2427d825dab8862766ad5b7b08e54ca1a12405a89', 'ETH/EUR/240.parquet': 'daf47dd3a323aa4e0ef72e61b8b18293b71cc4be774d4af430833d3d275278f3', 'LINK/EUR/240.parquet': '596ffa28ca7f8435061dbd97ae501d3d6915caba32cb1f4f88198bf180100e8f', 'LTC/EUR/240.parquet': 'c228951dec83ee20159594ca8a2293d2cf70c078e0335458700dc9d369fd5886', 'SOL/BTC/240.parquet': 'ca04363e0cab5f2eab555e507dda8a870989c5d8771b4a27c8f8654c4a28dbaf', 'SOL/EUR/240.parquet': '8f6bccc064a117ccf1c278a226be289f99227acdf71744a8cf732d7f8897ec25', 'XRP/EUR/240.parquet': 'c80e235477a82b9bf513440893d14668b2c6ca962027dc5b4e30f35d4d44abaa'}, 'rows': 183860, 'span': ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00']}} vouched {'ohlc-full': 'checked (36 vouched hashes)'} holes {}
arm A's three A2 runs 63.9 s
end full 2026-10-24T20:41:50+00:00
```

**The cells**, a third program over the second's books — the comparison with trial 58 and reading 6, the limits, arm B held to the book's own BTC, the holding, the shortfall, its carry, turnover and the months reading 6 never saw, written out with `cli/alpha/b4.py`'s functions, never through the trial's code:

```python
import json
import math
import pickle
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import close_grid
from cli.alpha.b4 import base_exposures, borrow_unavailable, limit_factors, scale_bars

print("start", datetime.now(UTC).isoformat(timespec="seconds"))
r = pickle.loads(Path(".tmp/iter191/basis/books-rolling.pickle").read_bytes())
f = pickle.loads(Path(".tmp/iter191/basis/books-full.pickle").read_bytes())
h4_ts, close = r["h4_ts"], close_grid(r["h4_ts"])
n, m = len(h4_ts) - 1, len(f["h4_ts"]) - 1
legs = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}
eur = list(r["arm_a"])
print(f"rolling: {n} return indices, closes {close[0]} -> {close[-1]}; ohlc-full: {m}")
print("the frozen union's stamps are the rolling union's first", m + 1, ":", f["h4_ts"] == h4_ts[: m + 1])
print("every EUR close equal on them:", all(f["h4_prices"][a] == r["h4_prices"][a][: m + 1] for a in eur), "; SOL/BTC's:", f["sol"] == r["sol"][: m + 1])
arm_a, full_a = r["arm_a"], f["arm_a"]
print("arm A's positions over the shared", m, "return indices equal trial 58's arm A bit for bit:", all(arm_a[a][:m] == full_a[a] for a in eur))
print("turnover of arm A over the shared span", repr(book_turnover({a: arm_a[a][:m] for a in eur})), "; trial 58's arm A", repr(book_turnover(full_a)))
record = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[57])["metrics"]
reading = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[5])["metrics"]
print("record 58's turnover_a", repr(record["turnover_a"]))


def limited(positions):
    factors, engaged = limit_factors(base_exposures(positions, legs))
    return scale_bars(positions, factors), engaged, factors


def per_year(flags):
    out = {}
    for k, flag in enumerate(flags):
        out[close[k].year] = out.get(close[k].year, 0) + int(flag)
    return {y: c for y, c in sorted(out.items()) if c}


lim_a, engaged_a, factor_a = limited(arm_a)
print("arm A after the limits bit-identical:", lim_a == arm_a, {k: sum(v) for k, v in engaged_a.items()})
raw_b = r["raw_b"]
first = r["first"]
print(f"SOL/BTC's first weight: return index {first}, close {close[first].isoformat()}; returns from it {n - first}")
zeroed = arm_a | {"SOL/BTC": [0.0] * n}
first_differ = next((k for k in range(n) if any(raw_b[i][k] != zeroed[i][k] for i in raw_b)), n)
print(f"raw arm B: first index differing from arm A (its leg at 0.0) {first_differ}; first non-zero SOL/BTC position {next((k for k in range(n) if raw_b['SOL/BTC'][k] != 0), n)}")
held_raw = borrow_unavailable(raw_b, legs, "BTC")
scaled = [held_raw["SOL/BTC"][k] != raw_b["SOL/BTC"][k] for k in range(n)]
zero = [raw_b["SOL/BTC"][k] != 0 and held_raw["SOL/BTC"][k] == 0 for k in range(n)]
print(f"held to the book's BTC: the leg scaled at {sum(scaled)} return indices, per close year {per_year(scaled)}; to zero at {sum(zero)}")
arm_b, engaged_b, factor_b = limited(held_raw)
print("arm B after the limits bit-identical:", arm_b == held_raw, {k: sum(v) for k, v in engaged_b.items()}, "bars scaled", sum(x != 1.0 for x in factor_b))
exp_b = base_exposures(arm_b, legs)
print(f"arm B: max per-base gross {max(math.fsum(abs(x[k]) for x in exp_b.values()) for k in range(n)):.6f}, max net {max(math.fsum(x[k] for x in exp_b.values()) for k in range(n)):.6f}")
held = [arm_b["SOL/BTC"][k] != 0 for k in range(n)]
where = [arm_b["SOL/BTC"][k] for k in range(n) if held[k]]
print(f"SOL/BTC held at {sum(held)} return indices, per close year {per_year(held)}; mean position where held {statistics.fmean(where):.6f}, max {max(where):.6f}")
differ = [any(arm_b[i][k] != zeroed[i][k] for i in arm_b) for k in range(n)]
print(f"positions differ from arm A's at {sum(differ)} return indices, per close year {per_year(differ)}; before the first weight {sum(differ[:first])}")
s = [max(0.0, -x) for x in exp_b["BTC"]]
c = [0.0002 * (s[k] + max(0.0, s[k] - (s[k - 1] if k else 0.0))) for k in range(n)]
short = [x > 0 for x in s]
print(f"shortfall at {sum(short)} return indices, per close year {per_year(short)}; max {max(s)!r}; carry at 0.0002 summed {math.fsum(c)!r}")
turnover_a, turnover_b = book_turnover(arm_a), book_turnover(arm_b)
print(f"turnover A {turnover_a!r} B {turnover_b!r}, B over A {100 * (turnover_b / turnover_a - 1):.2f} %; the leg's own {book_turnover({'SOL/BTC': arm_b['SOL/BTC']}):.4f}, the ten EUR legs' {book_turnover({a: arm_b[a] for a in eur}):.4f}")
shared = {i: v[:m] for i, v in arm_b.items()}
s_m = [max(0.0, -x) for x in base_exposures(shared, legs)["BTC"]]
print("over the shared span: turnover", repr(book_turnover(shared)), "reading 6's SOL/BTC no_borrow", repr(reading["turnover"]["SOL/BTC"]["no_borrow"]))
print("  held per close year", per_year(held[:m]), "reading 6's", {y: v for y, v in reading["held_per_year"]["SOL/BTC"]["no_borrow"].items() if v})
print("  shortfall stamps", per_year(short[:m]), "reading 6's", {y: v for y, v in reading["shortfall_stamps_per_year"]["SOL/BTC"]["no_borrow"].items() if v})
cut = datetime(2026, 3, 31, 20, tzinfo=UTC)
unseen = next(k for k in range(n) if close[k] > cut)
print(f"unseen: the first return index whose close is after {cut.isoformat()}: {unseen}, close {close[unseen].isoformat()}, h4_ts {h4_ts[unseen].isoformat()}; returns from it {n - unseen}; the frozen set's last stamp {f['h4_ts'][-1].isoformat()}")
print(f"  from it: SOL/BTC held at {sum(held[unseen:])}, positions differ at {sum(differ[unseen:])}, shortfall stamps {sum(short[unseen:])}")
holdout = [datetime(2026, 4, 1, tzinfo=UTC) <= close[k] < datetime(2026, 7, 10, tzinfo=UTC) for k in range(n)]
print(f"  the spent holdout's window 2026-04-01 -> 2026-07-09 by close: {sum(holdout)} return indices, from {close[holdout.index(True)].isoformat()}")
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-24T20:42:32+00:00
rolling: 28495 return indices, closes 2013-09-11 00:00:00+00:00 -> 2026-10-10 20:00:00+00:00; ohlc-full: 27337
the frozen union's stamps are the rolling union's first 27338 : True
every EUR close equal on them: True ; SOL/BTC's: True
arm A's positions over the shared 27337 return indices equal trial 58's arm A bit for bit: True
turnover of arm A over the shared span 146.18534602048504 ; trial 58's arm A 146.18534602048504
record 58's turnover_a 146.18534602048504
arm A after the limits bit-identical: True {'gross': 0, 'net': 0, 'margin': 0}
SOL/BTC's first weight: return index 17079, close 2021-07-26T00:00:00+00:00; returns from it 11416
raw arm B: first index differing from arm A (its leg at 0.0) 17079; first non-zero SOL/BTC position 17115
held to the book's BTC: the leg scaled at 3047 return indices, per close year {2021: 330, 2022: 591, 2023: 370, 2024: 620, 2025: 482, 2026: 654}; to zero at 1777
arm B after the limits bit-identical: True {'gross': 0, 'net': 0, 'margin': 0} bars scaled 0
arm B: max per-base gross 0.998300, max net 0.998300
SOL/BTC held at 4620 return indices, per close year {2021: 514, 2022: 566, 2023: 1104, 2024: 981, 2025: 705, 2026: 750}; mean position where held 0.023860, max 0.114247
positions differ from arm A's at 9904 return indices, per close year {2021: 891, 2022: 1830, 2023: 2058, 2024: 1871, 2025: 1832, 2026: 1422}; before the first weight 0
shortfall at 57 return indices, per close year {2021: 3, 2022: 14, 2023: 1, 2024: 14, 2025: 6, 2026: 19}; max 6.938893903907228e-18; carry at 0.0002 summed 6.817463260588852e-20
turnover A 155.62922308759553 B 156.02775785139957, B over A 0.26 %; the leg's own 6.0697, the ten EUR legs' 149.9581
over the shared span: turnover 146.4464868776143 reading 6's SOL/BTC no_borrow 146.4464868776143
  held per close year {2021: 514, 2022: 566, 2023: 1104, 2024: 981, 2025: 705, 2026: 234} reading 6's {'2021': 514, '2022': 566, '2023': 1104, '2024': 981, '2025': 705, '2026': 234}
  shortfall stamps {2021: 3, 2022: 14, 2023: 1, 2024: 14, 2025: 6, 2026: 8} reading 6's {'2021': 3, '2022': 14, '2023': 1, '2024': 14, '2025': 6, '2026': 8}
unseen: the first return index whose close is after 2026-03-31T20:00:00+00:00: 27337, close 2026-04-01T00:00:00+00:00, h4_ts 2026-03-31T20:00:00+00:00; returns from it 1158; the frozen set's last stamp 2026-03-31T20:00:00+00:00
  from it: SOL/BTC held at 516, positions differ at 1027, shortfall stamps 11
  the spent holdout's window 2026-04-01 -> 2026-07-09 by close: 600 return indices, from 2026-04-01T00:00:00+00:00
end 2026-10-24T20:42:33+00:00
```

What they establish:

- **The set and its head.** `ohlc-rolling` on this workstation's mirror holds lines from its base, 2026-09-30, to 2026-10-10, its head, `index/2026/10/10.json`, sha256 `fcb62a79fab7b58626f0cbd96ae40093a6dfc9e6ff51384cf25a5e9759dc44c4`, its chain walked to the base; no line from the seam to the head names a hole for any of its twelve pairs, so a full-history read of the ten EUR pairs and SOL/BTC meets no hole and takes no `--accept-holes` (D2).
- **The block.** The union of the ten EUR assets' 4h series and SOL/BTC's 4h pair, read through the reader's `read_rolling` as of 2026-10-10, form the block the record will carry, `compute_hash` `c05629c70826656ca225857f6b5b682bfc00a737a0feff91f78b57cf70c93295`: the one as-of line and its sha256, 196,598 rows, 2013-09-10 20:00 → 2026-10-10 20:00, `vouched_status` `chained (as of 2026-10-10, line fcb62a79fab7)`, holes none.
- **The union and the leg.** 28,496 stamps, 28,495 return indices, the closes 2013-09-11 00:00 → 2026-10-10 20:00, every asset first stamped where it is on `ohlc-full`; SOL/BTC's 4h pair holds 11,645 rows, 2021-06-17 12:00 → 2026-10-10 20:00, no null close and no bar at a stamp no EUR asset has; of the union's stamps from its first it misses 2 (2021 1, 2024 1), `ohlc-full`'s two.
- **The frame shared with `ohlc-full`.** `ohlc-full`'s union is the rolling union's first 27,338 stamps, every EUR close and every SOL/BTC close equal on them; arm A's positions over the 27,337 return indices the two share equal trial 58's arm A bit for bit, their turnover record 58's `turnover_a`, 146.18534602048504. Over the same span arm B is reading 6's SOL/BTC no_borrow cell: its turnover is the cell's 146.4464868776143 and its holding and shortfall stamps per close year are the cell's (D3, D7).
- **The first weight.** SOL/BTC enters the eleven-instrument book's inverse-vol weight path at return index 17,079 (close 2021-07-26 00:00), trial 58's and reading 6's, so the primary read holds 11,416 return indices; arm B's raw book is arm A's, its leg at 0.0, to the bit before 17,079 and differs from it there, its first non-zero SOL/BTC position at 17,115.
- **Held to the book's own BTC.** `borrow_unavailable` scales the leg at 3,047 return indices, to zero at 1,777 where the book holds no BTC; the limits leave both arms bit-identical, no limit engaged and no bar scaled, the largest per-base gross and net exposure 0.9983.
- **The holding.** SOL/BTC holds a non-zero position at 4,620 return indices — 2021 514, 2022 566, 2023 1,104, 2024 981, 2025 705, 2026 750 — at a mean 0.0239 of NAV where held and at most 0.1142; the books differ at 9,904 return indices, none before the first weight.
- **The shortfall, float rounding.** The book's BTC net of the leg reads below zero at 57 return indices — 2021 3, 2022 14, 2023 1, 2024 14, 2025 6, 2026 19 — at most 6.938893903907228e-18, and the carry it implies at 0.0002 sums 6.817463260588852e-20 over the window: no carry is owed (D4).
- **The turnover.** Arm B trades 156.02775785139957 against arm A's 155.62922308759553, 0.26 % more: the leg's own 6.0697, the ten EUR legs 149.9581, 5.67 less as the leg takes basket weight from them. At 0.006 per side the added 0.3985 costs 0.0024 in per-bar return summed over the 28,495 returns — the cost arm B carries into the head-to-head before any return of its own.
- **The months reading 6 never saw.** The first return index whose close is after 2026-03-31 20:00 is 27,337 (close 2026-04-01 00:00, its bar `ohlc-full`'s last stamp), and 1,158 return indices close after it; there SOL/BTC is held at 516, the books differ at 1,027 and the shortfall's float rounding reads at 11. Of them, the 600 closing from 2026-04-01 00:00 to 2026-07-09 20:00 are the spent holdout's window (D6). So of the primary read's 11,416 return indices, 10,258 are the ones reading 6's cell read, bit for bit, and 1,158 are new.

**The count, the names and the run's time**, a fourth program:

```python
import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha.killbar import a1_kill_bar, net_of_cost_verdict
from cli.registry import attempts, budget
from cli.research import subjects
from tests.retired_subjects import RETIRED_SUBJECTS

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]
landed = attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl"))
c = attempts.reconcile(lines, landed, log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF)
print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])
print("required_n('B4')", c.required_n("B4"), "; B4 records", [(r["trial_id"], r["n_trials_in_family"]) for r in c.records if r["family"] == "B4"])
print("open attempts (a begin with no end):", sorted({x["attempt"] for x in lines if x["kind"] == "begin"} - {x["attempt"] for x in lines if x["kind"] == "end"}))
attempt = max(x["attempt"] for x in lines if x["kind"] == "begin")
begin = next(x for x in lines if x["kind"] == "begin" and x["attempt"] == attempt)
end = next(x for x in lines if x["kind"] == "end" and x["attempt"] == attempt)
took = datetime.fromisoformat(end["timestamp"]) - datetime.fromisoformat(begin["timestamp"])
print(f"attempt {attempt} ({begin['invocation']['subject']}): {took.total_seconds():.0f} s, failed {end['failed']}")
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("b4-sol-noborrow-rolling", "b4-sol-noborrow-rolling-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("names opening b4:", sorted(x for x in names if x.startswith("b4")), "; retired among them:", sorted(x for x in RETIRED_SUBJECTS if x.startswith("b4")))
rng = random.Random(0)
n = 28_495
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
read at 2026-10-24T20:42:55+00:00
{'B1': 5, 'B2': 7, 'B4': 1} remain 12 []
required_n('B4') 2 ; B4 records [(58, 1)]
open attempts (a begin with no end): []
attempt 10 (b4-ratio-legs): 302 s, failed None
b4-sol-noborrow-rolling equals or opens with a hyphen: [] ; it opens: []
b4-sol-noborrow-rolling-preflight equals or opens with a hyphen: [] ; it opens: []
names opening b4: ['b4-leg-reading', 'b4-ratio-legs', 'b4-ratio-legs-preflight'] ; retired among them: ['b4-leg-reading', 'b4-ratio-legs', 'b4-ratio-legs-preflight']
synthetic, 28495 Gaussian returns: one a1_kill_bar 11.85 s, one net_of_cost_verdict 6.01 s
```

**The DSR leg's threshold**, a fifth program, bisecting the per-period Sharpe at which the bar's DSR leg passes, at its default moments, for trial 58's returns and count and for this trial's:

```python
import math

from cli.validation import deflated_sharpe_ratio

for n_obs, n_trials in ((27_337, 1), (28_495, 2)):
    lo, hi = 0.0, 0.1
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if deflated_sharpe_ratio(mid, n_obs, n_trials, 0.0) <= 0.95 else (lo, mid)
    print(f"{n_obs} returns at n_trials {n_trials}, var_trials 0.0: dsr_pass needs a per-period Sharpe above {hi:.6f}, annualised {hi * math.sqrt(2190):.4f}")
```

```text
27337 returns at n_trials 1, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.009949, annualised 0.4656
28495 returns at n_trials 2, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.009745, annualised 0.4560
```

- **The count**: the registry holds one B4 record, trial 58 at count 1, and the trial-attempts log no orphan and no open attempt, so `required_n("B4")` is 2 — B4's true count with this trial, the count it declares (D8); bucket B has spent 13 of 25 (B1 5, B2 7, B4 1), 12 remaining, 11 once this trial's record lands.
- **The names**: no registered or retired subject's name equals `b4-sol-noborrow-rolling` or `b4-sol-noborrow-rolling-preflight` or opens either with a hyphen, and neither opens one; the names opening `b4` are trial 58's two and reading 6's, all retired (D9).
- **The DSR leg**: at `var_trials` 0.0 the expected maximum Sharpe is 0 at any count (`expected_max_sharpe`'s first branch), so at count 2 the leg is the PSR against 0, as at count 1; over the 28,495 returns `dsr_pass` needs an annualised net Sharpe above 0.4560 — the program's 0.4656 at trial 58's 27,337 returns and count 1 is spec 00144's figure, the check that the bisection reads the bar as that spec did.
- **The run's time**: record 58's `--register` run took 302 s (attempt 10 of log `60c9f39c`). This trial's inputs half — six A2 runs on ten and eleven instruments and an eleven-instrument inverse-vol weight path — took 168.93 s as the plan's data-gated case, run on the authoring tree; one `a1_kill_bar` over 28,495 synthetic returns took 11.85 s and one `net_of_cost_verdict` 6.01 s. The trial computes seven bars and three head-to-heads, about 169 + 83 + 18 ≈ 270 s, one process well under 600 s; its pre-flight the inputs half and one bar, about 181 s.

Specs 00144 and 00145 frozen, and trial 58's and reading 6's code path since reading 6's run:

```text
$ sha256sum docs/specs/00144-b4-ratio-legs-design.md docs/specs/00145-b4-leg-reading-design.md; python3 -c 'import json; r = json.loads(open("docs/reference/trial-registry.jsonl").read().splitlines()[57]); print("record", r["trial_id"], r["spec_hash"], r["invocation"]["commit"]); g = json.loads(open("docs/reference/reading-ledger.jsonl").read().splitlines()[5]); print("reading", g["reading_id"], g["spec_hash"], g["invocation"]["commit"])'; git log --oneline c4025751a36213d50274879992158f0970e7e00e..459aed498 -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat
f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89  docs/specs/00144-b4-ratio-legs-design.md
9485cbbb194a936afe16789d851bb9c980a291e3f984f33869a99d222526bea6  docs/specs/00145-b4-leg-reading-design.md
record 58 f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89 93c0ec7af12323c3cda294481854e9cf878802d6
reading 6 9485cbbb194a936afe16789d851bb9c980a291e3f984f33869a99d222526bea6 c4025751a36213d50274879992158f0970e7e00e
```

- **Specs 00144 and 00145 are frozen**: their sha256s are record 58's and reading 6's `spec_hash`; neither is edited.
- **The code path since reading 6's run** at `c4025751a`: the log to this branch's base prints nothing — no commit has touched it, so the books, costing, limits, bar and rule this trial reuses are record 58's and reading 6's.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial runs under one, the session holding this branch's worktree, `.claude/worktrees/iter191`, on the workstation `zcrypto-ops`, whose main checkout holds the one listed trial-attempts log (`docs/reference/trial-attempt-logs.txt`). No other session runs a bucket-B subject while this branch is open — B1 and B2 are closed and B4's other subjects retired — no second machine and no restored or copied log; each of those is spec 00133's to count and refuse, not this spec's to design for.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Both read `data/ohlc-rolling`, a symlink to the main checkout's mirror of the rolling canonical, as of 2026-10-10: a run writes nothing under it and makes no network call. The mirror changes only through `zcrypto data fetch`, which no step of this spec runs, and a later line a fetch adds leaves the 2026-10-10 line and every byte it commits to unchanged, so the as-of read is the measured basis's whatever the mirror's head.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained; this worktree is their one writer while the branch is open. `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and landed-count literal before anything else lands (D10).

## Hypothesis (trial 2, pre-registered by this spec's sha256)

Master plan §5's B4 on its nearest cell: trend on the SOL/BTC ratio pair is exposure the EUR legs do not carry, and held only where the book's own BTC covers it the leg costs no borrow, so **the adopted A2-4h ensemble run on eleven instruments — its ten EUR assets and the SOL/BTC ratio pair, the pair held long, base against BTC, while A2's own trend signal holds it, its position scaled each bar to the book's own BTC — has a higher mean net-of-cost return than the ten-asset ensemble from the first close SOL/BTC takes basket weight, net of every instrument's own turnover at 0.006 a side, on the rolling set through 2026-10-10.** Arm A is the adopted equal-weight three-arm A2-4h ensemble exactly as trial 58 built it; arm B the same three arms on the eleven instruments, A2's configuration unchanged, held to the book's BTC as reading 6's no_borrow cell. There is no knob: the owner's pick names the leg, the funding and the set. It is judged by D8's matrix on its own record; what its verdict changes is D11's.

## D1 — the pick: the owner's, trial 2 on SOL/BTC held to the book's own BTC, on the rolling set

- The owner's words, quoted in the Ruling, and the options the owner was offered, as the `[iter-190] B4's next step after the leg reading` entry records them: **SOL/BTC no-borrow on the rolling set**, chosen — reading 6's nearest cell, judged where the months past `ohlc-full`'s end join its returns; **SOL/BTC no-borrow on the frozen set**, reading 6's own data, whose head-to-head would reproduce the reading's figure; **the symmetric legs**, short the pairs as well at an ETH or SOL borrow. The next family offered beside it: **B3**, chosen; C3 and C2.
- One iteration, one branch, this spec and its plan, one plan review, one task loop; one trial subject with its pre-flight twin, one bar, one matrix, one record; then B4's close and T0016's B3 arm (D11).
- The budget: the landed record spends one of Bucket B's 12 remaining (spec 00133 D5; `BUDGET["B"]` 25, B1 5, B2 7 and B4 1 spent); a stop, a refused build or a refusal from the count spends none.

## D2 — the instrument: `ohlc-rolling` as of 2026-10-10, full history, no hole

- `--dataset ohlc-rolling --as-of 2026-10-10`, no `--window`, no `--accept-holes`: the set as of its head on this workstation's mirror, the line `index/2026/10/10.json` (sha256 `fcb62a79…dc44c4`), its full history, 2013-09-10 20:00 → 2026-10-10 20:00 — `ohlc-full`'s window and the six months past its end. **Author's call — the as-of day the mirror's head, measured, and no fetch**: the newest day this workstation holds, so the trial reads the most of the months reading 6 never saw that the mirror carries; a fetch before the run would move the measured basis under the spec, so none runs, and the as-of pins the read whatever the mirror's head becomes.
- **No `--accept-holes`**: the flag is carried if and only if the window holds a hole of a pair the trial reads, and no line from the seam to the head names a hole (measured). A hole in a later line is outside the as-of read.
- **The reads** go through the run's `ObservedReader`: the ten EUR assets' union by `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)` — `read_rolling` for each pair's 240-minute grid derived from the set's 15-minute base and day files — and SOL/BTC's 4h pair by `reader.read_rolling(dataset, "SOL/BTC", 240, as_of, window=window, accept_holes=accept_holes)`, mapped onto the union's stamps by exact stamp, `None` where the pair has no bar; a bar at a stamp no EUR asset has is not read (none exists, measured). ETH/BTC is not read. The record's block is the as-of line's, `c05629c7…c93295` (measured), never trial 58's twelve `ohlc-full` files.
- **Author's call — the subject reads either form, as `_capturing_union` does**: given `--as-of`, the rolling set as of that day; given none, a frozen set file by file, SOL/BTC's pair `<dataset>/SOL/BTC/240.parquet` by `read_series` — so the shared contract, defaults and deflation rows, which evaluate every subject on a frozen fixture, run this one end to end. The trial is pre-registered on the rolling set alone (D10's invocation check), and a frozen set ending before 2026-04-01, `ohlc-full` among them, refuses the trial's build (D8).
- A SOL/BTC frame the build cannot parse, or one without a `close` column, is a `SubjectError` naming `<dataset>/SOL/BTC/240.parquet` on a frozen set and `<dataset> SOL/BTC at 240 minutes as of <day>` on the rolling set; a missing pair ends in the command's own exit.
- **The spent holdout's window** inside the read, 2026-04-01 → 2026-07-09 — 600 return indices by close (measured) — is read under the `[iter-176]` ruling: no figure of this trial is reported as holdout or out-of-sample evidence, the adopted system is not re-evaluated on it, and `data/ohlc-holdout-*` is not read.
- **The frame.** The rolling set's base is `ohlc-15m-20261007` copied byte for byte and derived to 240 on read, `ohlc-full` a reconstruction of the same dumps (`docs/reference/data-catalog-full.md`); over the span they share, their unions and every close the trial reads are equal (measured), so arm A there is trial 58's to the bit and arm B reading 6's cell's.

## D3 — the arms: arm A the adopted ensemble, arm B its three arms on eleven instruments, SOL/BTC held to the book's own BTC

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as trial 58 built it: `_b4_limited(_b4_ensemble(fed))`, `fed = _ffill_btc(h4_prices)`, the three arms `_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year, each instrument's equal-weight mean, then §10's limits (D5) — measured equal to trial 58's arm A over the 27,337 return indices the sets share, its turnover there record 58's.
- **Arm B** is `_b4_limited(borrow_unavailable(_b4_ensemble(fed | {"SOL/BTC": ratio}), _B4_LEGS, "BTC"))`: the same three arms run by `a2_book_returns`, unchanged, on eleven instruments — the ten EUR assets and SOL/BTC after them — their equal-weight mean, SOL/BTC's position scaled each bar by `min(1, max(0, x_BTC) / q)`, 1 where the leg holds nothing, so that the BTC it sells never exceeds the book's own BTC/EUR position (spec 00144 D7, reading 6's no_borrow cell, spec 00145 D3), then the limits. `short="off"` clips every direction at 0, so the leg is only ever long SOL against BTC.
- **Bit for bit until the leg takes weight.** Before SOL/BTC enters `_inverse_vol_weights` it carries no weight, every EUR weight is the same quotient over the same sum in the same order as arm A's, and the leg's term in the base return adds a signed zero (spec 00144 D3), so arm B's positions are arm A's to the bit and the leg's 0.0; `borrow_unavailable` scales a leg holding nothing by 1. The plan proves it on a fixture; the basis measures it on this set, to index 17,079.
- **The first weight** is read off arm B's own weight path, `_inverse_vol_weights(fed | {"SOL/BTC": ratio}, lookback=180)`, the first return index whose weights hold the leg — 17,079, close 2021-07-26 00:00 (measured) — recorded as `ratio_first_weight`.
- **Author's call — the inputs in trial 58's shape.** `_b4_sol_inputs(reads)` returns trial 58's `_B4Inputs`, arm B in both `arm_b` and `no_borrow`: trial 58's twin is its arm B held to the book's BTC, and this arm B is that construction, its own borrow-free book; so `_b4_arm_a_bar` builds arm A's bar unchanged. **No twin**: the carried SOL/BTC book, reading 6's other SOL/BTC cell, would be a second look the owner's pick did not name.
- **Author's call — trial 58's and reading 6's functions, unchanged**: `_b4_ensemble`, `_b4_limited`, `borrow_unavailable`, `_b4_shortfall`, `_b4_net`, `_b4_arm_a_bar`, `ratio_eur_returns` and the rule `_b4_ratio_legs_verdict`, so arm B differs from reading 6's SOL/BTC no_borrow cell in the closes it reads past 2026-03-31 and in nothing else. No existing function changes.

## D4 — the costing and the funding: trial 58's, the shortfall float rounding

- **The returns**: `_asset_returns(fed[a])` for the ten EUR assets and `ratio_eur_returns(ratio, fed["BTC"])` for SOL/BTC — the BTC-denominated gain converted at the bar's closing BTC/EUR (spec 00144 D4).
- **The costing**: every book by `_b4_net(positions, returns, stress=…)` — `net_of_cost` at `stress × 0.006` per side on each instrument's own turnover from flat, a missing return read as 0.0, less `shortfall_carry` of the book's BTC shortfall at `stress × 0.0002` per 4h rollover plus the opening charge on each increase (spec 00144 D4, D5). The kill bar's cost-stressed series is `stress` 1.5.
- **The funding**: arm B's shortfall, `quote_shortfall(base_exposures(arm_b, _B4_LEGS), "BTC")`, is float rounding — at most 6.94e-18, at 57 return indices — and its carry sums 6.8e-20 over the window (measured): no carry is owed. **Author's call — the shortfall counted as the code computes it**: `shortfall_stamps_per_year` counts those stamps as reading 6's D6 counted its twins' — a tolerance would be a second definition of the shortfall — and the record adds `shortfall_max`, so the record itself shows the count to be rounding. `_b4_net` subtracts the carry as computed; it moves no figure the matrix reads beyond rounding.
- Arm A holds no leg, so its shortfall is 0.0 at every bar and its net is trial 58's arm A's on the span both sets share.

## D5 — §10's limits: trial 58's wiring

- Both arms' per-base exposures pass `limit_factors` — the gross cap 1.5 / 2.0, the net band −0.5 … +1.0, the margin floor 2.5, in `cli/risk/limits.py`'s order, one factor per bar — through `_b4_limited`, unchanged (spec 00144 D6). No bar of either arm engages a limit (measured: the largest per-base gross and net 0.9983), so both come out bit-identical; arm B's engaged bars per limit and close year and arm A's totals are recorded.

## D6 — the months reading 6 never saw

- **The cut** is the last close reading 6 read, 2026-03-31 20:00Z — `_B4_SOL_SEEN_TO`, a constant — and the first return index whose close is after it, `_b4_sol_unseen(close)`, is 27,337 (close 2026-04-01 00:00), 1,158 return indices from it to the window's end (measured): the returns from `ohlc-full`'s last stamp on.
- **The read**: `net_of_cost_verdict(net_b[unseen:], net_a[unseen:], mean_block=30, seed=42, n_resamples=2000)`, keyed `head_to_head_mean_outperf_unseen` and `head_to_head_spa_p_unseen`, and the count `unseen_returns`. **Author's call — recorded, no matrix leg**: 1,158 return indices with the leg held at 516 is a short read beside the primary's 11,416, and its SPA p is no second decider; it is what the owner's pick added, read beside the deciding window and reported as what it is.
- Within it, the 600 return indices of the spent holdout's window are read under `[iter-176]`: the unseen months are a span reading 6 did not look at, never holdout or out-of-sample evidence.
- **Author's call — fewer than 2 return indices after the cut refuses the build before any bar**, a `ValidationError` and so a refused build, as the primary's refusal does: a set ending before the cut cannot record the trial's keys, and a key the registry would store as missing does not exist.

## D7 — the contamination, stated in full

- Reading 6 read this very cell — SOL/BTC alone beside the ten EUR assets in the three adopted A2 arms, held to the book's own BTC, costed as trial 58 costed arm B — on `ohlc-full` from its first weight to 2026-03-31: a primary mean outperformance of 3.827897287865115e-06/bar at SPA p 0.08495752123938032, a full-window 1.4363891567809324e-06 at 0.07596201899050475, a drawdown from the first weight 0.20494010496059067 against arm A's 0.21543236950723366 and a net Sharpe there 0.23848223317979558 against 0.16429157109957965 (the `[iter-190]` reading-6 entry). Over the span the two sets share arm B is that cell bit for bit (measured), so **the primary window's span through 2026-03-31 — 10,258 of its 11,416 return indices — is no independent look**: its figures there are reading 6's, known before this spec. The 1,158 return indices after it are a look reading 6 did not take, and are the only new evidence the trial reads.
- **The trial is the owner's pick, not the reading's criterion's**: reading 6 found no cell with potential — this one missed only its Bonferroni SPA bound, p 0.085 against 0.0125 — and named no trial; the owner picked it after reading that figure.
- **The DSR counts B4's true trials**: `n_trials` 2, records 58 and this one, `required_n("B4")` measured; reading 6's four looks are stated beside it and are not in the count, as spec 00145 D7 prescribed for a trial designed from the reading.
- Its instrument, arm A, costing, limits, bar and rule are trial 58's, whose arm A cleared the bar on `ohlc-full` (record 58's `arm_a_passes` 1); arm A's bar on this set is read at the pre-flight, after the hash (D10). The author knows trial 58's and reading 6's stored figures as the Ruling and this list quote them, and no return of any book over the rolling set's months past 2026-03-31.

## D8 — the bar, the head-to-heads, the matrix and the count

- **The bar**, record 58's call: `a1_kill_bar(net_b, bench, n_trials=2, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)` on the raw union prices, the stub years 2013 and 2026 out of the slices (`STUB_YEARS`; 2026 is partial on this set too); the SPA grid blocks {30, 102} × seeds {42, 7, 1234}, the headline cell (30, 42), the five others recorded and never read. At count 2 and `var_trials` 0.0 the expected maximum Sharpe is 0 and the DSR leg is the PSR against 0: `dsr_pass` needs an annualised net Sharpe above 0.4560 over the 28,495 returns (measured). **Arm A's headline bar** is the same call on `net_a` at (30, 42), `_b4_arm_a_bar` unchanged, read `passes` 1 at the pre-flight, after the hash (D10).
- **The head-to-heads**: `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` on the full window (`first` 0), primary from `start`, SOL/BTC's first weight — 17,079, `primary_returns` 11,416 (measured) — and from the cut (D6); keyed `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_unseen` and `head_to_head_spa_p_unseen`. Before the start the two books are one to the bit (D3), so the full-window read adds 17,079 zero differences to the primary's; the primary decides. Refused before any bar: fewer than 2 return indices from the start, or after the cut, a `ValidationError` and so a refused build.
- **The matrix** — trial 58's, rows disjoint and covering every outcome:

| Arm A's bar and SOL/BTC's holding | Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from SOL/BTC's first weight) | Verdict |
| --- | --- | --- | --- |
| arm A's `passes` 0, or SOL/BTC holds no non-zero position at any return index (a dead knob) | any | any | **instrument finding**: no verdict, the slot unspent |
| arm A passes, SOL/BTC held | fail | any | **reject** |
| arm A passes, SOL/BTC held | pass | mean outperformance > 0 and SPA p < 0.05 | **adopt** |
| arm A passes, SOL/BTC held | pass | mean outperformance > 0, SPA p ≥ 0.05 | **park** |
| arm A passes, SOL/BTC held | pass | mean outperformance ≤ 0 | **reject** |

  Every quantity the matrix reads is a stored key read unrounded: `arm_a_passes`, `ratio_held_per_year`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`. No drawdown leg, as trial 58's; the unseen months in no leg (D6). **No park variants**: B4 closes after this trial's verdict on the owner's word (D11). **An adopt is recorded, never deployed** (D11). **Author's call — the rule is trial 58's own function**, `_b4_ratio_legs_verdict`, unchanged: the matrix is trial 58's, its `ratio_held_per_year` holding SOL/BTC alone, so a rule of this trial's own would type the same five rows a second time:

```python
def _b4_ratio_legs_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(n for held in m["ratio_held_per_year"].values() for n in held.values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"
```

- **The count**: 2, `_B4_SOL_N_TRIALS` — B4's true count with this trial, `required_n("B4")` measured 2 from the registry and the trial-attempts log (record 58, no orphan, plus one). Fixed by this spec's hash, never raised in place; spec 00133 D4 refuses a declared count below `required_n`, so a B4 attempt landing elsewhere before this run refuses it, the trial going back to the owner through T0016.

## D9 — the engagement, the subjects, their record and the build

- **The engagement**, both subjects' fourteen keys, computed from positions alone (`_b4_sol_engagement`): record 58's twelve — `ratio_first_weight` (`{"SOL/BTC": k}`); `primary_returns`; `ratio_held_per_year` (`{"SOL/BTC": per close year}` — the dead-knob read); `stamps_positions_differ` and `positions_differ_per_year` (arm A's positions, the leg at 0.0, against arm B's); `turnover_b` and `turnover_b_per_year`; `shortfall_stamps_per_year` and `shortfall_mean_per_year`; `carry_per_year` (at 0.0002); `limit_engaged_per_year` (arm B's); `arm_a_limit_engaged` (arm A's totals) — and two added: `unseen_returns` (D6) and `shortfall_max` (D4). Every year key is a close year (`close_grid`), every year the closes span keyed.
- **The trial's 49 keys**: record 58's 48 with its twin's three — `no_borrow_ann_sharpe_noc`, `no_borrow_head_to_head_mean_outperf_primary`, `no_borrow_head_to_head_spa_p_primary` — out (no twin, D3), and the unseen months' pair and the engagement's two added. **The pre-flight's 34**: trial 58's pre-flight's 29 — the engagement's twelve, arm A's seven anchors over the window (`arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`) and arm A's bar's ten — with the engagement's two added and arm A's figures over the closes reading 6 read: `arm_a_ann_sharpe_noc_seen`, `arm_a_ann_sharpe_noc_decisive_seen` and `arm_a_max_drawdown_seen`, its net Sharpe, its decisive net Sharpe from index 1,380 and its maximum drawdown over the return indices before the cut. **Author's call — the seen-span anchors**: no record holds arm A's figures over the rolling window, and over the span both sets share arm A's net is trial 58's arm A's to the bit — its positions are (measured), and its returns and costing are per bar — so the three must equal record 58's stored `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive` and `arm_a_max_drawdown` to the last digit: the pre-flight's anchor in place of trial 58's record-45 anchors.
- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00146-b4-sol-noborrow-rolling-design.md"`, `_ASSETS`, intervals `(240,)` — SOL/BTC's pair is the build's to read and name: the trial `b4-sol-noborrow-rolling` — `metric_keys=_B4_SOL_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_b4_ratio_legs_verdict`, `no_verdict` "instrument finding: arm A fails the bar this window sets, or SOL/BTC holds no position at any stamp; no verdict, the trial unspent", `family="B4"`, `n_trials=_B4_SOL_N_TRIALS` — and its evaluate-only twin `b4-sol-noborrow-rolling-preflight` — `metric_keys=_B4_SOL_PREFLIGHT_KEYS`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). It costs arm A alone and reads no head-to-head; it builds arm B's positions, which its engagement reads. No incumbent: arm A is built in the run.
- **Author's call — the names `b4-sol-noborrow-rolling` and `b4-sol-noborrow-rolling-preflight`**: spec 00141 D2's rule — no registered or retired subject's name equals either or opens it with a hyphen, and neither opens one (measured).
- **The family key `B4`** is in `BUCKET_OF` already (spec 00144 D9); `cli/registry/budget.py` is unchanged.
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B4`; `n_trials_in_family` 2; variant `B4-sol-noborrow-a2eq-rolling-v1` (**Author's call**: record 58's form, `<family>-<name>-a2eq-<set>-v1`); iteration `iter-191`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `c05629c70826656ca225857f6b5b682bfc00a737a0feff91f78b57cf70c93295`; the invocation's `as_of` 2026-10-10 and `accept_holes` false; `attempt` the trial-attempts log's; `notes` caller text written before the run (D10).
- **The build in three halves**, spec 00144 D9's form: `_b4_sol_reads(subject, reader, dataset, window, as_of, accept_holes)` — the union, trial 58's two window refusals and SOL/BTC's closes, no compute; `_b4_sol_inputs(reads)` — both arms' limited positions, their engaged bars, the first weight and the returns, no return of a book; `_b4_sol_metrics` and `_b4_sol_preflight_metrics` from it. The plan's data-gated case runs the first two over the real set, and its fixture tests run the books on a union shorter than the reads admit. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `RiskError`, `ValidationError` — is a `SubjectError` naming the subject and its window.
- **The files the build touches, a closed list**: `cli/research/subjects.py` — one block before `SUBJECTS` (`_B4_SOL`, `_B4_SOL_N_TRIALS`, `_B4_SOL_SEEN_TO`, `_b4_sol_reads`, `_b4_sol_inputs`, `_b4_sol_unseen`, `_b4_sol_engagement`, `_b4_sol_metrics`, `_b4_sol_preflight_metrics`, `_b4_sol_build`, the two builders and the three key sets) and its two `SUBJECTS` entries, no import added and no existing function changed; `README.md`'s `--subject` row; the tests the plan names; after the run, `tests/retired_subjects.py` and `tests/test_trial_registry_provenance.py`'s landed-count literal. No change to `cli/alpha/*`, `cli/registry/*`, `cli/risk/*`, `cli/costs/*`, `cli/portfolio/*`, `cli/engine/*`, B4's existing subjects, specs 00128, 00133, 00144 and 00145, record 58, reading 6 or any adopted artifact.

## D10 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00146-b4-sol-noborrow-rolling-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append; (3) the data-gated basis test on the run's tree; (4) the twin's plain eval, `--dataset ohlc-rolling --as-of 2026-10-10`, read in this order — (a) the block, `c05629c7…c93295`, `ohlc-rolling` `chained (as of 2026-10-10, line fcb62a79fab7)`, no hole printed; (b) arm A's three seen-span figures record 58's to the last digit and `turnover_a` the basis's 155.62922308759553 (D9); (c) the engagement equal to the measured basis — the plan's data-gated literals; (d) the dead knob — SOL/BTC held at some return index; (e) arm A's `passes` 1 — a failure of (a)–(e) an instrument finding, the run kept as a reading under iter-191 (`--reading --iteration iter-191 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent; (5) on a pass, the trial's one run, `--dataset ohlc-rolling --as-of 2026-10-10 --register --iteration iter-191 --family B4 --n-trials 2 --variant B4-sol-noborrow-a2eq-rolling-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10); (6) the record's checks — its block the pre-flight's, its invocation `ohlc-rolling` as of 2026-10-10 with no holes accepted, its labels, keys, verdict and engagement — and its commit: the registry line, the decisions-log verdict entry and the landed-count literal together, since the tie tests hold only over the three.
- **The hash rule**: before (1), nobody reads or computes arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — by code, a program or arithmetic over a stored figure — nor runs `b4-sol-noborrow-rolling` or its twin over the real set; positions, weights, exposures, the shortfall, limit engagement and turnover are allowed, and are what the measured basis and the data-gated test hold. `a2_book_returns` computes each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; no program reads any of them (spec 00145 D8's words). No net-of-cost return of arm B is computed over the real data before the trial's `--register` run, and reading 6's replay, which rebuilds arm B's returns over the span the sets share, is not run before it.
- **The notes, written before the run** (spec 00137 D10's): the subject over `ohlc-rolling` as of 2026-10-10, full history, no holes; the arms, the leg held to the book's BTC, the costing and the limits; the hypothesis; the count and `var_trials` 0.0; the read from SOL/BTC's first weight deciding, the full-window read and the unseen months' read beside it, the latter in no matrix leg and the spent holdout's window inside it no holdout evidence; the contamination, reading 6's look at the cell through 2026-03-31; the pre-flight's figures, quoted; no park variants; the matrix pre-registered by this spec's sha256.
- A refusal from the count, a refused build, a stop by the rule under `--register`: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0016's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D11 — what a verdict changes

- **After a verdict, whatever it is, B4 closes on the owner's word**: the decisions log gains `[iter-191] B4's next step after trial 2 — closed, the owner's word of 2026-10-24 (Decision: 1)`, quoting the owner's words, the heading T0016's B3 arm checks for (`^\[iter-[0-9]+\] B4.s next step after trial 2 — closed`); T0016's B4 bullets record trial 2's verdict and B4 closed on its two trials and one reading; its next step is B3 — the owner's next-family pick, opening in a later iteration with its own brainstorm, spec and plan — then per §5 C2 → C3 → C1; its `ripe_when` loses its B4 arm and keeps its B3 arm, which the close entry fires; the open-topics index is re-rendered; both subjects are retired. Nothing is archived: T0016 stays live for B3 and the C families.
- **Adopt** is recorded, never deployed, for spec 00144 D11's reasons: the engine trades EUR pairs only — the venue adapter's position reports take a single quote currency (T0120) and `cli/engine/feeders.py`'s `load_minimums` keeps the universe's `quote == "EUR"` entries alone — so SOL/BTC on the live path is an engine change and a go-live decision, both the owner's (master plan §12). Its path, the owner's, in order: a P1 combination trial over record 47's book carrying the leg, outside every bucket's budget, then the engine's change, then T0123's promotion path; T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts, and T0016's `ripe_when` keeps a B4 arm for that combination trial alone. B4 closes as a family all the same: no further B4 trial follows.
- **Park** names no variant: B4 closes.
- **Reject** archives the hypothesis in the record and the decisions log.
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, a refused build or a refusal from the count — spends no trial and writes no close entry. **Author's call**: the owner's "then move on" follows a verdict, and a stop has none, so whether trial 2 runs again once its cause is fixed or B4 closes unrun is the owner's; T0016 records what failed and its B4 arm waits on a `[iter-NNN] B4's next step after trial 2` entry, and both subjects are kept.

## Out of scope

Every other B4 trial or variant — ETH/BTC alone, SOL/BTC carried, the symmetric legs, a further pair, the leg's own vol target or weight cap, SOL/BTC no-borrow on the frozen set; a twin beside arm B; the unseen months as a matrix leg; any window but the rolling set's full history as of 2026-10-10, and any as-of day after it; `zcrypto data fetch`; `data/ohlc-holdout-*`; the leg on the live path and the combination trial over record 47's book (D11); B3's design, which opens in a later iteration; any change to an existing function, subject, record, reading or spec.
