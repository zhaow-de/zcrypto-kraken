# B4 trial 1 — the ETH/BTC and SOL/BTC ratio legs added to the A2-4h ensemble as two more instruments, on the frozen `ohlc-full` set

**Ruling:** the owner, attended, 2026-10-23, closing B2 and picking the next family, verbatim: "B4-legs (Recommended)" (the decisions log's `[iter-188] B2's next step after trial 8 — closed`). The owner then launched this unattended run, verbatim: "continue working on B4-legs and other research strates. Ignore the wall time clock gate, but do not pick up new topics after 09:00Z". B4 is worked under T0016; no new topic is registered. B4's first step — this trial, directly — is the loop's pick under that instruction (D1), recorded as the decisions-log entry `[iter-189] B4's first step — trial 1, the two ratio legs added to the A2-4h ensemble as instruments, the loop's pick under the owner's run instruction` before this spec's hash. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" (the `[iter-181] B2 instrument ruling` entry), whose window — the one on which arm A is recorded clearing the ratified bar — this trial reads; and the two `[iter-176]` rulings binding every B and C pre-registration, the DSR leg binding at `var_trials` 0.0 and the spent holdout's window never reported as holdout evidence (this set ends 2026-03-31, before it). Every call past those words and past what specs 00128, 00133, 00137 and 00143 fix is the loop's, marked **Author's call** where it is made. **Iteration:** iter-189, branch `research/iter-189-b4-legs-opening`. **Topic:** T0016, its B4 arm. **Goal:** pre-register B4's first trial — master plan §5's B4, "Trend/momentum applied to the ratio pairs — carry-free "market-neutral" exposure. Cheap to add to A2 as extra instruments; the ratio series are less correlated with the USD legs and behave differently across regimes" — as numbered decisions with code-level definitions: a compute module beside `cli/alpha/b2.py`, one committed research subject with its evaluate-only pre-flight twin, the family key `B4` in bucket B, registered through `zcrypto research eval --register` and spec 00133's trial-attempts log. Spec 00143 is this spec's form (its operating model, hash rule, pre-flight twin and run), spec 00132 the nearest compute precedent (an arm B that differs from arm A inside the A2 ensemble's own book rather than through an overlay), spec 00128 the family-opening form. The landed record spends one trial of Bucket B's shared budget: 13 remain today, 12 after.

## The measured basis

Every figure below was measured on 2026-10-23 in this branch's worktree at develop's `2e7656294`, before the trial's code was written into it — the first program between 23:14:44Z and 23:18:33Z, the second at 23:18:52Z, the shell checks after them — with `data/ohlc-full` symlinked read-only from the main checkout's `data/` and the main checkout's `.local/trial-attempts.jsonl` read, never written. They read closes, weights, positions, per-base exposures, the BTC shortfall and the carry it implies, limit engagement and turnover only: no return of either arm or of the twin is read, and no head-to-head, bar leg or subject runs over the real set. `a2_book_returns` computes each arm's base returns on its way to the positions, since its vol target sizes on them; the programs read its `asset_positions` alone. Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

The positions program — both arms built by their own three-arm expression, the limits, the shortfall and the twin written out in it, never through the trial's code:

```python
import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import close_grid
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects
from cli.risk.limits import apply_gross_leverage_cap, apply_margin_floor, apply_net_exposure_band

print("start", datetime.now(UTC).isoformat(timespec="seconds"))
reader = ObservedReader(Path("data"))
h4_ts, h4_prices = subjects._capturing_union(reader, "ohlc-full", 240, None, None, False)
n, close, at = len(h4_ts) - 1, close_grid(h4_ts), {t: k for k, t in enumerate(h4_ts)}
legs = {"ETH/BTC": "ETH", "SOL/BTC": "SOL"}
ratios = {}
for leg in legs:
    frame = reader.read_series("ohlc-full", f"{leg}/240.parquet")
    ts = frame["ts"].to_list()
    by_ts = dict(zip(ts, frame["close"].to_list(), strict=True))
    ratios[leg] = [by_ts.get(t) for t in h4_ts]
    first = at[ts[0]]
    missed = {}
    for k in range(first, len(h4_ts)):
        if ratios[leg][k] is None:
            missed[h4_ts[k].year] = missed.get(h4_ts[k].year, 0) + 1
    print(f"{leg} 240: rows {len(ts)}, first {ts[0]}, last {ts[-1]}, null closes {frame['close'].null_count()}, stamps no EUR asset has {sum(t not in at for t in ts)}; union stamps from its first: {len(h4_ts) - first}, missed {sum(missed.values())}, per year {dict(sorted(missed.items()))}")
block = reader.block()
print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in block.items()})
print("vouched", reader.vouched_status())
record_57 = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[56])
eur = {p: h for p, h in block["ohlc-full"]["files"].items() if "/EUR/" in p}
print("the ten EUR files' hashes are record 57's ohlc-full files:", eur == record_57["datasets"]["ohlc-full"]["files"])

fed = _ffill_btc(h4_prices)
configs = [
    A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lb, tv in subjects._B2_A2_ARMS
]


def ensemble(prices):
    arms = [a2_book_returns(prices, config=c)["asset_positions"] for c in configs]
    return arms, {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(n)] for a in prices}


_, arm_a = ensemble(fed)
priced = fed | ratios
arms_b, arm_b = ensemble(priced)
stub = subjects._b2_overlay_inputs(
    "basis", lambda r, ts: {a: [None] * (len(ts) - 1) for a in subjects._ASSETS}, 3.0, ObservedReader(Path("data")), "ohlc-full", None, False
)
print("arm A equals _b2_overlay_inputs' arm A bit for bit:", stub.arm_a == arm_a, "; turnover_a", repr(book_turnover(arm_a)), "record 57's", repr(record_57["metrics"]["turnover_a"]))
weights = _inverse_vol_weights(priced, lookback=180)
first_weight = {leg: next((k for k in range(n) if leg in weights[k]), n) for leg in legs}
start = min(first_weight.values())
print("first weight", {leg: (k, close[k].isoformat()) for leg, k in first_weight.items()}, "; primary start", start, "returns from it", n - start)
for leg in legs:
    print(f"  {leg} first non-zero position per A2 arm", [next((k for k in range(n) if arm[leg][k] != 0), n) for arm in arms_b], "ensemble", next((k for k in range(n) if arm_b[leg][k] != 0), n))
print(
    "before the start arm B's EUR positions are arm A's bit for bit:",
    all(arm_b[a][:start] == arm_a[a][:start] for a in subjects._ASSETS),
    "; its ratio positions all 0.0:",
    all(p == 0.0 for leg in legs for p in arm_b[leg][:start]),
)


def base(positions):
    out = {a: list(positions[a]) for a in subjects._ASSETS}
    for leg, asset in legs.items():
        if leg in positions:
            for k in range(n):
                out[asset][k] += positions[leg][k]
                out["BTC"][k] -= positions[leg][k]
    return out


def limited(positions):
    exposures = base(positions)
    gross = apply_gross_leverage_cap(exposures, soft_cap=1.5, hard_cap=2.0)
    net = apply_net_exposure_band(gross, short_bound=-0.5, long_bound=1.0)
    floor = apply_margin_floor(net, floor=2.5)
    engaged = {}
    for name, before, after in (("gross", exposures, gross), ("net", gross, net), ("margin", net, floor)):
        engaged[name] = [any(before[a][k] != after[a][k] for a in before) for k in range(n)]
    factor = [
        1.0
        if all(floor[a][k] == exposures[a][k] for a in exposures)
        else math.fsum(abs(floor[a][k]) for a in floor) / math.fsum(abs(exposures[a][k]) for a in exposures)
        for k in range(n)
    ]
    return {i: [p * f for p, f in zip(positions[i], factor)] for i in positions}, engaged, factor, exposures


def per_year(flags):
    out = {}
    for k, flag in enumerate(flags):
        out[close[k].year] = out.get(close[k].year, 0) + int(flag)
    return {y: c for y, c in sorted(out.items()) if c}


lim_a, engaged_a, factor_a, exp_a = limited(arm_a)
print("arm A: limits engaged", {name: sum(f) for name, f in engaged_a.items()}, "; bit-identical after them:", lim_a == arm_a,
      "; max net exposure", max(math.fsum(exp_a[a][k] for a in exp_a) for k in range(n)))
lim_b, engaged_b, factor_b, exp_b = limited(arm_b)
for name, flags in engaged_b.items():
    print(f"arm B: {name} engaged {sum(flags)} bars, per close year {per_year(flags)}")
print("arm B: bars scaled", sum(f != 1.0 for f in factor_b), "smallest factor", min(factor_b),
      "; max gross", max(math.fsum(abs(exp_b[a][k]) for a in exp_b) for k in range(n)),
      "; max net", max(math.fsum(exp_b[a][k] for a in exp_b) for k in range(n)))
for leg in legs:
    held = [k for k in range(n) if lim_b[leg][k] != 0]
    print(f"{leg}: held at {len(held)} return indices, per close year {per_year([lim_b[leg][k] != 0 for k in range(n)])}, mean position where held {statistics.fmean(lim_b[leg][k] for k in held):.6f}, max {max(lim_b[leg]):.6f}")
arm_a12 = arm_a | {leg: [0.0] * n for leg in legs}
differ = [any(lim_b[i][k] != arm_a12[i][k] for i in lim_b) for k in range(n)]
print("closes where the books differ", sum(differ), "per close year", per_year(differ), "; before the start", sum(differ[:start]))
turnover_a, turnover_b = book_turnover(arm_a), book_turnover(lim_b)
print(f"turnover A {turnover_a!r} B {turnover_b!r}, B over A {100 * (turnover_b / turnover_a - 1):.2f} %; the ratio legs' own {book_turnover({leg: lim_b[leg] for leg in legs}):.4f}")
rate = 0.0002


def shortfall_and_carry(positions, rate):
    btc = base(positions)["BTC"]
    s = [max(0.0, -x) for x in btc]
    c = [rate * (s[k] + max(0.0, s[k] - (s[k - 1] if k else 0.0))) for k in range(n)]
    return s, c


s, c = shortfall_and_carry(lim_b, rate)
held_s = [x for x in s if x > 0]
print(f"shortfall: {len(held_s)} return indices, per close year {per_year([x > 0 for x in s])}, mean where short {statistics.fmean(held_s):.6f}, max {max(s):.6f}, mean over the window {statistics.fmean(s):.6f}")
years_full, years_primary = n / 2190, (n - start) / 2190
carry_year = {}
for k in range(n):
    carry_year[close[k].year] = carry_year.get(close[k].year, 0.0) + c[k]
print(f"carry at {rate}: summed {math.fsum(c):.6f}; {100 * math.fsum(c) / years_full:.4f} % a year over the window, {100 * math.fsum(c[start:]) / years_primary:.4f} % a year from the start; per close year", {y: round(v, 6) for y, v in sorted(carry_year.items()) if v})
twin_raw = dict(arm_b)
scale = [1.0 if arm_b["ETH/BTC"][k] + arm_b["SOL/BTC"][k] == 0 else min(1.0, arm_b["BTC"][k] / (arm_b["ETH/BTC"][k] + arm_b["SOL/BTC"][k])) for k in range(n)]
for leg in legs:
    twin_raw[leg] = [p * f for p, f in zip(arm_b[leg], scale)]
lim_t, engaged_t, _, _ = limited(twin_raw)
st, ct = shortfall_and_carry(lim_t, rate)
print(f"no-borrow twin: legs scaled at {sum(f < 1 for f in scale)} return indices, to zero at {sum(f == 0 for f in scale)}; limits engaged {({name: sum(f) for name, f in engaged_t.items()})}; shortfall max {max(st)!r}, carry summed {math.fsum(ct)!r}; turnover {book_turnover(lim_t)!r}")
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-23T23:14:44+00:00
ETH/BTC 240: rows 22057, first 2016-03-03 04:00:00+00:00, last 2026-03-31 20:00:00+00:00, null closes 0, stamps no EUR asset has 0; union stamps from its first: 22076, missed 19, per year {2018: 2, 2022: 16, 2024: 1}
SOL/BTC 240: rows 10487, first 2021-06-17 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, null closes 0, stamps no EUR asset has 0; union stamps from its first: 10489, missed 2, per year {2021: 1, 2024: 1}
block 9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df {'ohlc-full': (12, 205917, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)'}
the ten EUR files' hashes are record 57's ohlc-full files: True
arm A equals _b2_overlay_inputs' arm A bit for bit: True ; turnover_a 146.18534602048504 record 57's 146.18534602048504
first weight {'ETH/BTC': (5442, '2016-04-02T08:00:00+00:00'), 'SOL/BTC': (17079, '2021-07-26T00:00:00+00:00')} ; primary start 5442 returns from it 21895
  ETH/BTC first non-zero position per A2 arm [5612, 5626, 5626] ensemble 5612
  SOL/BTC first non-zero position per A2 arm [17115, 17140, 17140] ensemble 17115
before the start arm B's EUR positions are arm A's bit for bit: True ; its ratio positions all 0.0: True
arm A: limits engaged {'gross': 0, 'net': 0, 'margin': 0} ; bit-identical after them: True ; max net exposure 0.9982997603001886
arm B: gross engaged 0 bars, per close year {}
arm B: net engaged 0 bars, per close year {}
arm B: margin engaged 0 bars, per close year {}
arm B: bars scaled 0 smallest factor 1.0 ; max gross 0.9982997603001886 ; max net 0.9982997603001886
ETH/BTC: held at 11397 return indices, per close year {2016: 644, 2017: 1443, 2018: 696, 2019: 1010, 2020: 1376, 2021: 1582, 2022: 1141, 2023: 1115, 2024: 939, 2025: 1127, 2026: 324}, mean position where held 0.048000, max 0.252419
SOL/BTC: held at 5682 return indices, per close year {2021: 764, 2022: 920, 2023: 1401, 2024: 1240, 2025: 1072, 2026: 285}, mean position where held 0.025451, max 0.113413
closes where the books differ 19648 per close year {2016: 1434, 2017: 2160, 2018: 1432, 2019: 2001, 2020: 2060, 2021: 2097, 2022: 1919, 2023: 2155, 2024: 2031, 2025: 1962, 2026: 397} ; before the start 0
turnover A 146.18534602048504 B 157.64827493713167, B over A 7.84 %; the ratio legs' own 29.9900
shortfall: 8779 return indices, per close year {2016: 192, 2017: 582, 2018: 544, 2019: 582, 2020: 903, 2021: 1430, 2022: 1273, 2023: 973, 2024: 920, 2025: 1025, 2026: 355}, mean where short 0.045884, max 0.303060, mean over the window 0.014735
carry at 0.0002: summed 0.083136; 0.6660 % a year over the window, 0.8315 % a year from the start; per close year {2016: 0.001688, 2017: 0.003143, 2018: 0.006144, 2019: 0.006081, 2020: 0.007869, 2021: 0.009872, 2022: 0.011097, 2023: 0.013902, 2024: 0.010192, 2025: 0.007084, 2026: 0.006064}
no-borrow twin: legs scaled at 8779 return indices, to zero at 4016; limits engaged {'gross': 0, 'net': 0, 'margin': 0}; shortfall max 2.0816681711721685e-17, carry summed 8.877881069180304e-19; turnover 145.19309348909263
end 2026-10-23T23:18:33+00:00
```

What it establishes:

- **The legs on the union.** ETH/BTC's 240-minute file holds 22,057 rows, 2016-03-03 04:00 → 2026-03-31 20:00, SOL/BTC's 10,487, 2021-06-17 12:00 → 2026-03-31 20:00; neither holds a null close, and neither a bar at a stamp no EUR asset has, so the rule that such a bar is not read (D2) decides no bar of this set. Of the union's stamps from each leg's first bar, ETH/BTC misses 19 (2018 2, 2022 16, 2024 1) and SOL/BTC 2 (2021 1, 2024 1), each a `None` A2 reads as a missing bar.
- **The block.** The ten EUR files and the two legs' files form the block the record will carry, `compute_hash` `9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df`: 12 files of `ohlc-full`, 205,917 rows, 2013-09-10 20:00 → 2026-03-31 20:00, `vouched_status` `checked (36 vouched hashes)` — both legs' frames pass the reader's vouched check. The ten EUR files' hashes are record 57's `ohlc-full` files.
- **Arm A is record 57's.** Built by the program's own three-arm expression, it equals `_b2_overlay_inputs`' arm A — the build of records 54–57 — bit for bit, and its turnover is record 57's stored `turnover_a`, 146.18534602048504, to the last digit.
- **The first weights and the primary start.** Every arm's basket lookback is 180, so one inverse-vol weight path serves the three: ETH/BTC enters it at return index 5,442 (close 2016-04-02 08:00), SOL/BTC at 17,079 (close 2021-07-26 00:00), so the primary read starts at 5,442 and holds 21,895 returns. The first non-zero position follows the legs' Donchian directions: ETH/BTC at 5,612 in the first arm and 5,626 in the other two, SOL/BTC at 17,115 and 17,140.
- **Arm B is arm A before the start.** At every return index before 5,442 arm B's ten EUR positions equal arm A's bit for bit and its two ratio positions are 0.0; the books differ at 19,648 closes, none before the start.
- **The holding.** ETH/BTC holds a non-zero position at 11,397 return indices, per close year from 644 (2016) to 1,582 (2021), at a mean 0.0480 of NAV where held and at most 0.2524; SOL/BTC at 5,682, per close year from 764 (2021) to 1,401 (2023), at a mean 0.0255 and at most 0.1134.
- **The BTC shortfall and its carry.** Where the two legs together outweigh the book's own BTC/EUR position the book borrows the difference: at 8,779 return indices, per close year from 192 (2016) to 1,430 (2021), a mean 0.0459 of NAV where short, at most 0.3031, 0.0147 over the window. At 0.0002 per rollover plus the opening charge on each increase (D5) the carry sums 0.083136 in per-bar return over the 27,337 returns: 0.6660 % of NAV a year over the window, 0.8315 % a year from the primary start, per close year from 0.001688 (2016) to 0.013902 (2023).
- **The limits.** No bar of either arm engages §10's gross cap, net band or margin floor: arm B's largest per-base gross and net exposure is 0.9983, arm A's largest net the same, so arm A comes out of the limits bit-identical and arm B's factor is 1.0 at every bar. The wiring (D6) decides no bar of this trial; it is wired for a book that breaches a limit.
- **The turnover.** Arm B trades 157.64827493713167 against arm A's 146.18534602048504, 7.84 % more: the legs' own 29.99, the ten EUR legs 18.53 less as the legs take basket weight from them. At 0.006 per side the added 11.4629 costs 0.0688 in per-bar return summed over the 27,337 returns, beside the carry's 0.0831 — the cost arm B carries into the head-to-head before any return of its own.
- **The borrow-unavailable twin.** Scaling the legs to the book's own BTC (D7) scales them at the shortfall's 8,779 return indices, to zero at 4,016 where the book holds no BTC; its shortfall is at most 2.08e-17, float rounding, its carry 8.88e-19 summed; it engages no limit, and trades 145.19309348909263.

The count, the name and the run's time, a second program:

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
c = attempts.reconcile(lines, landed, log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF | {"B4": "B"})
print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])
print("required_n('B4')", c.required_n("B4"), "; families in the registry", sorted({r["family"] for r in c.records}))
print("open attempts (a begin with no end):", sorted({x["attempt"] for x in lines if x["kind"] == "begin"} - {x["attempt"] for x in lines if x["kind"] == "end"}))
attempt = max(x["attempt"] for x in lines if x["kind"] == "begin")
begin = next(x for x in lines if x["kind"] == "begin" and x["attempt"] == attempt)
end = next(x for x in lines if x["kind"] == "end" and x["attempt"] == attempt)
took = datetime.fromisoformat(end["timestamp"]) - datetime.fromisoformat(begin["timestamp"])
print(f"attempt {attempt} ({begin['invocation']['subject']}): {took.total_seconds():.0f} s, failed {end['failed']}")
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("b4-ratio-legs", "b4-ratio-legs-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("names opening b4:", sorted(x for x in names if x.startswith("b4")))
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
read at 2026-10-23T23:18:52+00:00
{'B1': 5, 'B2': 7, 'B4': 0} remain 13 []
required_n('B4') 1 ; families in the registry ['A1', 'B1', 'B2', 'P1']
open attempts (a begin with no end): []
attempt 9 (b2-liq-z3-derisk): 244 s, failed None
b4-ratio-legs equals or opens with a hyphen: [] ; it opens: []
b4-ratio-legs-preflight equals or opens with a hyphen: [] ; it opens: []
names opening b4: []
synthetic, 27337 Gaussian returns: one a1_kill_bar 11.08 s, one net_of_cost_verdict 5.65 s
```

- **The count**: the registry holds no B4 record and the trial-attempts log no orphan and no open attempt, so `required_n("B4")` is 1 — this trial — the count it declares (D8); bucket B has spent 12 of 25 (B1 5, B2 7), 13 remaining, 12 once this trial's record lands. The registry's families are A1, B1, B2 and P1: `B4` is no key yet, and the benchmark family's B4 (master plan §9, B3 plus the simplest short extension) never was one (D9).
- **The name**: no registered or retired subject's name equals `b4-ratio-legs` or `b4-ratio-legs-preflight` or opens either with a hyphen, neither opens one, and no name opens `b4` (D9).
- **The run's time**: record 57's `--register` run took 244 s (attempt 9 of log `60c9f39c`). This trial's inputs half — six A2 runs on ten and twelve instruments and a seventh inverse-vol weight path — took 165.14 s as the plan's data-gated case, run on the authoring tree at 23:36:24Z; one `a1_kill_bar` over 27,337 synthetic returns took 11.08 s and one `net_of_cost_verdict` 5.65 s. The trial computes seven bars and three head-to-heads, about 165 + 78 + 17 ≈ 260 s, one process well under 600 s; its pre-flight the inputs half and one bar, about 180 s.

Spec 00143 frozen, and arm A's code path since record 57's run:

```text
$ sha256sum docs/specs/00143-b2-liq-derisk-threshold-design.md; python3 -c 'import json; r = json.loads(open("docs/reference/trial-registry.jsonl").read().splitlines()[56]); print("record", r["trial_id"], r["spec_hash"], r["invocation"]["commit"])'
901d4917d29dd326dc13167a0fff225caf6171b46e4fff52b555d7635f087521  docs/specs/00143-b2-liq-derisk-threshold-design.md
record 57 901d4917d29dd326dc13167a0fff225caf6171b46e4fff52b555d7635f087521 06ceb184748f907f13862bf812ee2c960a80415f
$ git log --oneline 06ceb184748f907f13862bf812ee2c960a80415f..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat
```

- **Spec 00143 is frozen**: its sha256 is record 57's `spec_hash`; it is not edited.
- **Arm A's code path since record 57's run** at `06ceb1847`: the log prints nothing — no commit has touched it, so the arm A this trial builds is record 57's, as the first program measures.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial runs under one, the session holding this branch's worktree, `.claude/worktrees/iter189`, on the workstation `zcrypto-ops`, whose main checkout holds the one listed trial-attempts log (`docs/reference/trial-attempt-logs.txt`). No other session runs a bucket-B subject while this branch is open — B1 and B2 are closed and their subjects retired — no second machine and no restored or copied log; each of those is spec 00133's to count and refuse, not this spec's to design for.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Both read `data/ohlc-full`, a symlink to the main checkout's frozen, attested set; a run writes nothing under it and makes no network call, and nothing this spec runs has a live writer.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained; this worktree is their one writer while the branch is open. `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and landed-count literal before anything else lands (D10).

## Hypothesis (trial 1, pre-registered by this spec's sha256)

Master plan §5's B4: trend on the ratio pairs is exposure the EUR legs do not carry — long ETH or SOL against BTC, not against the euro — and the ratio series behave differently from the EUR legs across regimes, so **the adopted A2-4h ensemble run on twelve instruments — its ten EUR assets and the ETH/BTC and SOL/BTC ratio pairs, each pair held long, base against BTC, while A2's own trend signal holds it — has a higher mean net-of-cost return than the ten-asset ensemble from the first close a ratio leg takes basket weight, net of every instrument's own turnover at 0.006 a side and of the BTC it borrows at 0.0002 per 4h where the legs outweigh the book's own BTC.** Arm A is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46 and 48–57 built it; arm B the same three arms on the twelve instruments, A2's configuration unchanged. There is no knob: the legs enter as A2 enters any instrument, so the trial reads the premise itself. It is judged by D8's matrix on its own record; what its verdict changes is D11's.

**The contamination, stated.** This is B4's first look: no B4 record or reading exists, its count is 1, and the measured basis reads positions, exposures, the shortfall and turnover, never a return. Its instrument, window, arm A, costing and bar are records 45–57's, whose arm A clears the bar on this window (record 45's anchors, read again at the pre-flight); B2's signals are not read. The pick follows B1's and B2's closes, the owner's "B4-legs (Recommended)" naming the family; the author knows the two pairs' history in broad strokes as market history — ETH/BTC's rise into 2017 and its fall through 2019 and again from 2022, SOL/BTC's rise through 2023 — and no figure of this repository about either pair's returns.

## D1 — the pick: B4's first step is trial 1, the two legs as instruments, directly

- The owner's family pick, "B4-legs (Recommended)", and run instruction, quoted in the Ruling; B4 under T0016. **The loop's pick (Decision: 1 of the `[iter-189]` pick entry)**: trial 1 directly, ETH/BTC and SOL/BTC added to the adopted A2-4h ensemble as two more instruments, A2's own configuration unchanged — master plan §5's own form ("cheap to add to A2 as extra instruments"). The trial has no free knob, so a screening reading would have nothing to choose between. One iteration, one branch, this spec and its plan, one plan review, one task loop; one trial subject with its pre-flight twin, one bar, one matrix, one record.
- The alternatives weighed and set aside: **a no-slot reading first** — the ratio legs' forward returns by trend state — which screens one cell with no alternative cell and spends an iteration before the only trial the family's premise names; **a standalone ratio sleeve beside arm A at a fixed weight** — the weight a knob the master plan does not name, and the sleeve alone, market-neutral and low-volatility, cannot clear the frozen benchmark's bar by construction.
- The budget: the landed record spends one of Bucket B's 13 remaining (spec 00133 D5; `BUDGET["B"]` 25, B1 5 and B2 7 spent); a stop, a refused build or a refusal from the count spends none.

## D2 — the instrument and the legs: frozen `ohlc-full`, full history, the venue's own pairs

- `--dataset ohlc-full`, no `--window`, no `--as-of`: B1's and B2's window, 2013-09-10 → 2026-03-31, the one window on which arm A is recorded clearing the ratified bar; the union `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices; the decisive window from index 1,380; the arms on `_ffill_btc`'s BTC-only fill, the benchmark on the raw prices.
- **The legs** are the venue's own pairs, `ETH/BTC/240.parquet` and `SOL/BTC/240.parquet` of the same set (2016-03-03 and 2021-06-17 onward, `docs/reference/data-catalog-full.md`), each read through the same `ObservedReader` under the run's window, none for the trial — `reader.read_series(dataset, "<leg>/240.parquet", window=window)` — and mapped onto the union's stamps by exact stamp, `None` where the pair has no bar; a bar at a stamp no EUR asset has is not read (none exists, measured). The legs are not forward-filled: a missing bar is A2's `None`, as every EUR asset's is. The record's block is the twelve files', `9e0fc8e5…82d7df` (measured).
- **Author's call — the native pairs, not a synthetic cross of the EUR legs.** The native pair is the instrument the universe selects (`docs/universe/point-in-time-universe.md` lists ETH/BTC and SOL/BTC among its twelve) and one trade per rebalance where the cross of ETH/EUR and BTC/EUR pays two fees; its close is the venue's own price, the cross a quotient of two closes that need not share a minute.
- A file of either leg the build cannot parse, or one without a `close` column, is a `SubjectError` naming `<dataset>/<leg>/240.parquet`; a missing file ends in the command's own exit.

## D3 — the arms: arm A the adopted ensemble, arm B its three arms on twelve instruments

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as `_b2_overlay_inputs` builds it: `fed = _ffill_btc(h4_prices)`; for each `(lookbacks, target_vol)` in `_B2_A2_ARMS`, `a2_book_returns(fed, config=A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=180, basket_lookback=180, periods_per_year=2190))["asset_positions"]`; their per-instrument `statistics.mean` at every return index. The subject's `_b4_ensemble(fed)` is that expression; the measured basis shows it equal to `_b2_overlay_inputs`' arm A bit for bit and its turnover record 57's.
- **Arm B** is `_b4_ensemble(fed | ratios)`: the same three arms each run by `a2_book_returns`, unchanged, on twelve instruments — the ten EUR assets and the two legs keyed `ETH/BTC` and `SOL/BTC`, after them — and their equal-weight mean of `asset_positions`. A2 reads each leg's native close for its direction, its inverse-vol weight and the book's vol target, as it reads every instrument. `short="off"` clips every direction at 0, so a ratio position is only ever long the base against BTC.
- **Bit for bit until a leg takes weight.** Before a leg enters `_inverse_vol_weights` — a full 180-return window of returns present at `t`, standard deviation above 0 — it carries no weight: every EUR weight is the same quotient over the same sum in the same order as arm A's, the leg's term in the base return is `0.0 × d × r`, which adds a signed zero, so the base returns, the vol target and every EUR position are arm A's to the bit and the leg's position is 0.0. The plan proves it on a fixture; the basis measures it on this set, to index 5,442.
- **The first weight** of each leg is read off `_inverse_vol_weights(fed | ratios, lookback=180)` — the one path every arm's basket reads, never a restated predicate (spec 00132 D2's form) — and recorded as `ratio_first_weight`: ETH/BTC 5,442, SOL/BTC 17,079 (measured).
- No change to `cli/alpha/a2.py`, `cli/alpha/a1.py`, `cli/alpha/b2.py`, `cli/risk/*`, `cli/costs/*`, `cli/portfolio/*` or any adopted artifact.

## D4 — a ratio leg's EUR return, and the costing

- **The EUR return.** A long ratio position of EUR notional `p` set at close `k` holds `p / E[k]` of the base against `p / B[k]` of BTC sold or borrowed, `E` and `B` the base's and BTC's EUR closes; at close `k + 1` its P&L is `p × (E[k+1]/E[k] − B[k+1]/B[k])`.
- With the pair's native close `R = E / B`, `E[k+1]/E[k] = (R[k+1]/R[k]) × (B[k+1]/B[k])`, so the P&L is `p × (R[k+1]/R[k] − 1) × (B[k+1]/B[k])`: the BTC-denominated gain converted at the bar's closing BTC/EUR. The subject reads `R` native and `B` as `fed["BTC"]`, forward-filled as `_ffill_btc` fills it: `ratio_eur_returns(ratio, quote_eur)` in `cli/alpha/b4.py`, `None` where `R[k]` or `R[k+1]` is `None`, refusing a ratio close neither `None` nor a finite number above 0, a quote close not a finite number above 0, and lists of unequal length, before any division. The plan's test holds it to `p × (r_ETH − r_BTC)` on a cross-consistent fixture.
- The net-of-cost loop reads this return for the two legs and `_asset_returns(fed[a])` for the ten EUR legs; A2's sizing keeps the native return (D3).
- **The costing**: `net_of_cost` of `cli/alpha/b2.py` over the instruments a book holds — 0.006 per side on each instrument's own turnover from flat, the legs on theirs, a missing return read as 0.0 (specs 00128 D5 and 00143, the family's flat rate) — minus the carry (D5), per bar. The kill bar's cost-stressed series is ×1.5 on both, 0.009 per side and the carry at 0.0003. **Author's call — one function, `_b4_net(positions, returns, *, stress)`, costs every book**: arm A, the ten EUR legs, carries no shortfall, so its net is `_b2_overlay_arm_a_bar`'s to the bit (a carry of 0.0 subtracted); arm B and the twin carry theirs.

## D5 — the funding: netted against the book's own BTC, the carry on the shortfall

- **The decomposition.** Each bar's instrument positions decompose into per-base EUR exposures: an EUR leg at `x` adds `x` to its base; `ETH/BTC` at `p` adds `+p` to ETH and `−p` to BTC; `SOL/BTC` at `q` adds `+q` to SOL and `−q` to BTC — `base_exposures(positions, legs)`, in the legs' order.
- **The shortfall.** A ratio leg is carry-free while the book's BTC covers it: the BTC it sells is the book's own. The shortfall `S[k] = max(0, −net_BTC[k])`, `net_BTC[k] = x_BTC[k] − p[k] − q[k]`, is borrowed on margin, the extended currency BTC (`docs/reference/kraken-fee-schedule.md`, "Spot-margin fees — confirmed per-base-currency": a long on margin buys with the borrowed quote, so the quote is extended — BTC, for both pairs), at `margin_rate("BTC", band="high")` = 0.0002 per 4h rollover (`cli/costs/margin.py`) plus the opening charge on each increase: `carry[k] = 0.0002 × (S[k] + max(0, S[k] − S[k−1]))`, `S[−1] = 0` — `quote_shortfall` and `shortfall_carry`. The rate is the constant `_B4_CARRY_RATE = 0.0002`, a test holding it to `margin_rate("BTC", band="high")`: the fee schedule's band moving after this spec's hash is a new trial, never this one's figure.
- Never an alt borrow: the legs are long-only (D3). Arm A holds no leg, so its shortfall is 0.0 at every bar.
- **The options weighed (the conventions entry's)**: (1) this, chosen — master plan §5's "carry-free" holds exactly where the book holds the BTC, and the shortfall is what an operator holding the book would borrow; (2) the symmetric legs, short ETH/BTC and SOL/BTC too — an ETH or SOL shortfall borrowed at 0.0004 per 4h, about 88 % a year, and a mixed short policy A2 has no path for; (3) each ratio leg a full margin position — the whole notional carried at 22–44 % a year (BTC extended at 0.0001–0.0002 per 4h), an implementation no operator holding the book's BTC would choose.

## D6 — §10's limits, wired: T0016's standing remainder

- Both arms' per-base exposures pass `apply_gross_leverage_cap(soft_cap=1.5, hard_cap=2.0)` → `apply_net_exposure_band(short_bound=-0.5, long_bound=1.0)` → `apply_margin_floor(floor=2.5)`, `cli/risk/limits.py`'s module docstring's order with no position caps (the adopted ensemble has none) — `limit_factors(exposures)` in `cli/alpha/b4.py`. Every limit scales a bar whole, so the bar's combined factor is 1.0 where none engages — each leaves an untouched bar bit-identical — and the limited gross over the unlimited where one does; `scale_bars` multiplies that bar's instrument positions by it, and the turnover, the P&L and the shortfall are read from the limited positions. The BTC shortfall is the book's short side in the margin model (`_margin_used`: shorts fully margin-extended).
- Arm A, long-only and at most fully invested, is untouched by construction and comes out bit-identical (measured: its largest net 0.9983, no limit engaged); arm B's engaged bars per limit and close year are recorded (measured: none), and arm A's engaged totals beside them.
- **Author's call — the three calls with their values written out, not `apply_whole_book_limits`** of `cli/portfolio/crossfreq_system.py`, which returns the final book alone and so no limit's engaged bars; the module's test holds the three calls' book to that function's on bars engaging each limit, so the two stacks cannot drift apart unseen.
- T0016's "Standing prerequisites" bullet records the wiring delivered in the branch's topic commit (D11).

## D7 — the borrow-unavailable twin, recorded beside the matrix

- §12's stress list names borrow-unavailable episodes, and T0016's standing prerequisite makes the rung mandatory again the moment a short exists; the BTC shortfall is one. **The twin** is arm B's raw positions with both legs scaled each bar by `min(1, x_BTC / (p + q))`, 1 where `p + q` is 0 — `borrow_unavailable(positions, legs, "BTC")` — then the limits (D6), so its shortfall is zero to float rounding (measured: at most 2.08e-17), costed by `_b4_net` as arm B is.
- Its annualised net Sharpe and its head-to-head against arm A from the primary start — the primary read's mean outperformance and SPA p — go into the record as `no_borrow_ann_sharpe_noc`, `no_borrow_head_to_head_mean_outperf_primary` and `no_borrow_head_to_head_spa_p_primary`. It is not a matrix leg: the trial's premise is the legs as A2 holds them.

## D8 — the bar, the head-to-head, the matrix and the count

- **The bar**, record 57's call: `a1_kill_bar(net_b, bench, n_trials=1, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)` on the raw union prices, the stub years 2013 and 2026 out of the slices; the SPA grid blocks {30, 102} × seeds {42, 7, 1234}, the headline cell (30, 42), the five others recorded and never read. At count 1 and `var_trials` 0.0 the expected maximum Sharpe is 0 and the DSR leg is the PSR against 0: `dsr_pass` needs an annualised net Sharpe above 0.466 over the 27,337 returns (spec 00132's measured basis, 0.4656). **Arm A's headline bar** is the same call on `net_a` at (30, 42), read `passes` 1 at the pre-flight, after the hash (D10).
- **The head-to-heads**: `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` on the full window (`first` 0) and, primary, from `start = min(ratio_first_weight)` — the first return index at which either leg holds a weight in any arm, 5,442 (measured), `primary_returns` 21,895 — keyed `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`; the twin's from the same start (D7). Before the start the two books are one to the bit (D3), so the full-window read adds 5,442 zero differences to the primary's; the primary decides. Refused before any bar: fewer than 2 return indices from the start, a `ValidationError` and so a refused build.
- **The matrix** — rows disjoint and covering every outcome:

| Arm A's bar and the legs' holding | Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from the first ratio weight) | Verdict |
| --- | --- | --- | --- |
| arm A's `passes` 0, or no ratio leg holds a non-zero position at any return index (a dead knob) | any | any | **instrument finding**: no verdict, the trial unspent |
| arm A passes, a leg held | fail | any | **reject** |
| arm A passes, a leg held | pass | mean outperformance > 0 and SPA p < 0.05 | **adopt** the legs |
| arm A passes, a leg held | pass | mean outperformance > 0, SPA p ≥ 0.05 | **park** (variant candidates: ETH/BTC alone; the symmetric legs, D5's option 2) |
| arm A passes, a leg held | pass | mean outperformance ≤ 0 | **reject** |

  Every quantity the matrix reads is a stored key read unrounded: `arm_a_passes`, `ratio_held_per_year`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`. No drawdown leg: B4's premise is return, not de-risking. **Author's call — the park variants**: ETH/BTC alone, its decade of history beside SOL/BTC's five years, and the symmetric legs, short the pairs as well at an ETH or SOL borrow. The rule, as the subject declares it (spec 00129 D4), with its two instrument findings:

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

- **The count**: 1, `_B4_N_TRIALS` — the family's true count with this trial, `required_n("B4")` measured 1 from the registry and the trial-attempts log (no B4 record, no orphan, plus one). **Author's call**: fixed by this spec's hash, never raised in place; spec 00133 D4 refuses a declared count below `required_n`, so a B4 attempt landing elsewhere before this run refuses it, the trial going back to the owner through T0016, a further count a new subject under a new spec.

## D9 — the engagement, the subjects, their record and the build

- **The engagement**, both subjects' twelve keys, computed from positions alone (`_b4_engagement`): `ratio_first_weight` (per leg, D3); `primary_returns`; `ratio_held_per_year` (per leg and close year, the return indices holding a non-zero position — the dead-knob read); `stamps_positions_differ` and `positions_differ_per_year` (arm A's positions, its legs at 0.0, against arm B's); `turnover_b` and `turnover_b_per_year`; `shortfall_stamps_per_year` and `shortfall_mean_per_year` (the BTC shortfall's return indices and its mean over the year's); `carry_per_year` (summed, at 0.0002); `limit_engaged_per_year` (arm B's, per limit and close year); `arm_a_limit_engaged` (arm A's totals per limit). Every year key is a close year (`close_grid`), every year the closes span keyed.
- **The trial's 48 keys**: the engagement's twelve; arm B's `ann_sharpe_noc`, `ann_sharpe_noc_decisive`, `per_period_sharpe_4h`; `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`; `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`; from the headline cell `dsr_corrected`, `dsr_pass`, `spa_pass`, `spa_p_full`, `cost_stress_pass`, `worst_slice_relative_pass`, `passes`; `decisive_start` 1380, `n_resamples` 2000; `arm_a_passes`; the six `spa_p_decisive_b<block>_s<seed>`; the four head-to-head keys (D8); the twin's three (D7); `max_drawdown` and `arm_a_max_drawdown` over the full window and `max_drawdown_per_year` and `arm_a_max_drawdown_per_year` per close year; `turnover_a` and `turnover_a_per_year`. **The pre-flight's 29**: the engagement's twelve; arm A's seven anchors, `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`; and arm A's bar's ten, the keys `b2-arm-a-bar` declares (`dsr`, `dsr_pass`, `spa_p_value`, `spa_p_value_full`, `spa_pass`, `cost_stress_sharpe`, `cost_stress_pass`, `worst_slice_sharpe`, `worst_slice_pass`, `passes`).
- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00144-b4-ratio-legs-design.md"`, `_ASSETS`, intervals `(240,)` — the legs' files are the build's to read and name: the trial `b4-ratio-legs` — `metric_keys=_B4_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_b4_ratio_legs_verdict`, `no_verdict` "instrument finding: arm A fails the bar this window sets, or no ratio leg holds a position at any stamp; no verdict, the trial unspent", `family="B4"`, `n_trials=_B4_N_TRIALS` — and its evaluate-only twin `b4-ratio-legs-preflight` — `metric_keys=_B4_PREFLIGHT_KEYS`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). It costs arm A alone and reads no head-to-head; it builds arm B's positions, which its engagement reads. No incumbent: arm A is built in the run. Both refuse `--as-of` before any read: "<subject> evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset".
- **Author's call — the names `b4-ratio-legs` and `b4-ratio-legs-preflight`**: spec 00141 D2's rule — no registered or retired subject's name equals either or opens it with a hyphen, and neither opens one (measured, and no name opens `b4`).
- **The family key `B4`** — master plan §5's label for this family; the benchmark family's B4 (master plan §9) is no registry key and never was. Spec 00133 D5's rule for a new family: it joins `BUCKET_OF` with its bucket, `"B4": "B"`, in a reviewed pull request quoting the ruling — the owner's "B4-legs (Recommended)" — and `tests/test_trial_registry_provenance.py`'s literal of `BUCKET_OF` changes with it: a guard change, proven by the plan's probe row.
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B4`; `n_trials_in_family` 1; variant `B4-ratio-legs-a2eq-full-v1` (**Author's call**: record 57's form, `<family>-<name>-a2eq-full-v1`); iteration `iter-189`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df`; `attempt` the trial-attempts log's; `notes` caller text written before the run (D10).
- **Author's call — the build in three halves**, spec 00132 D8's form: `_b4_reads(subject, reader, dataset, window, accept_holes)` — the union, the window's refusals and the legs' closes, no compute; `_b4_inputs(reads)` — both arms' limited positions, the twin's, their engaged bars, the first weights and the returns, no return of a book; `_b4_metrics` and `_b4_preflight_metrics` from it. The plan's data-gated case runs the first two over the real set, and its fixture tests run the books on a union shorter than the reads admit. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `RiskError`, `ValidationError` — is a `SubjectError` naming the subject and its window.
- **The files the build touches, a closed list**: `cli/alpha/b4.py`, new — `ratio_eur_returns`, `base_exposures`, `limit_factors`, `scale_bars`, `quote_shortfall`, `shortfall_carry`, `borrow_unavailable` and three per-year helpers; `cli/research/subjects.py` — three insertions: the import of those functions, the B4 block before `SUBJECTS` and its two entries, no existing function changed; `cli/registry/budget.py` — `BUCKET_OF`'s one line; `README.md`'s `--subject` row; the tests the plan names. No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b2.py`, `cli/features/*`, `cli/portfolio/*`, `cli/risk/*`, `cli/costs/*`, `cli/engine/*`, the existing subjects, specs 00128, 00133, 00137 and 00143, or any adopted artifact.

## D10 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00144-b4-ratio-legs-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append; (3) the data-gated basis test on the run's tree; (4) the twin's plain eval, read in this order — (a) the block, `9e0fc8e5…82d7df`, `ohlc-full` `checked (36 vouched hashes)`; (b) arm A's seven anchors at record 45's stored precision (spec 00137 D7's (b)); (c) the engagement equal to the measured basis — the plan's data-gated literals; (d) the dead knob — a ratio leg held at some return index; (e) arm A's `passes` 1 — a failure of (a)–(e) an instrument finding, the run kept as a reading under iter-189 (`--reading --iteration iter-189 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent; (5) on a pass, the trial's one run, `--register --iteration iter-189 --family B4 --n-trials 1 --variant B4-ratio-legs-a2eq-full-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10); (6) the record's checks and its commit — the registry line, the decisions-log verdict entry and the landed-count literal together, since the tie tests hold only over the three.
- **The hash rule**: before (1), nobody reads arm B's or the twin's returns — `book_base_returns`, `net_returns` or `metrics` of `a2_book_returns`' result for arm B — nor computes any net-of-cost series, Sharpe, head-to-head or bar leg of arm B or of the twin, nor runs `b4-ratio-legs` or its twin over the real set; positions, weights, exposures, the shortfall, the carry the shortfall implies, limit engagement and turnover are allowed, and are what the measured basis and the data-gated test hold. `a2_book_returns` computes arm B's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions — the measured basis's and the data-gated test's among them; no program reads any of them. No net-of-cost return of arm B is computed over the real data before the trial's `--register` run, and the trial subject is never run as a plain eval.
- **The notes, written before the run** (spec 00137 D10's): the subject over `ohlc-full`, full history; the arms, the legs, the costing, the funding and the limits; the hypothesis; the count and `var_trials` 0.0; the read from the first ratio weight deciding, the full-window read and the twin beside it; the pre-flight's figures, quoted; the park variants; the matrix pre-registered by this spec's sha256.
- A refusal from the count, a refused build, a stop by the rule under `--register`: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0016's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D11 — what a verdict changes

- **Adopt** is recorded, never deployed: the engine trades EUR pairs only — the venue adapter's position reports take a single quote currency (T0120) and `cli/engine/feeders.py`'s `load_minimums` keeps the universe's `quote == "EUR"` entries alone — so a ratio leg on the live path is an engine change and a go-live decision, both the owner's (master plan §12). Deploying follows the B1 precedent of spec 00138 D11: a P1 combination trial over record 47's book carrying the legs, outside every bucket's budget, then the engine's change, then T0123's promotion path; T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts.
- **Park** names its variant candidates in the record — ETH/BTC alone, and the symmetric legs — each a new trial of the shared budget, put to the owner through T0016.
- **Reject** archives the hypothesis in the record and the decisions log.
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, or a refused build — spends no trial; T0016 records what failed.
- After any verdict, B4's next step — a park variant, a further leg, or closing the family — is the owner's family call, carried as T0016's B4 arm and recorded as a `[iter-NNN] B4's next step after trial 1` entry. T0016 records the §10 wiring delivered (D6) in the branch's topic commit, whatever the outcome.

## Out of scope

The park variants and every other B4 knob — one leg alone, the symmetric legs, the legs as full margin positions, a standalone ratio sleeve at a fixed weight, a synthetic cross of the EUR legs, the legs' own vol target or weight cap, another ratio pair; §10's per-asset position caps, which the adopted ensemble does not carry; a no-slot reading of the legs; any window but the frozen set's full history, and `ohlc-rolling`; the legs on the live path and the combination trial over record 47's book (D11); Bucket B's B3 and the C families, T0016's; any change to an existing function, subject, record or spec.
