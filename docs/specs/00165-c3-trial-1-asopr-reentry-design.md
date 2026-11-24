# C3 trial 1 — aSOPR's low tail as a re-entry for the A1 sleeve's flat state, the one cell reading 10 found with potential, pre-registered on the sets that reading read

Iteration `iter-210`, branch `feat/iter-210-c3-trial-1`, cut from `develop` at `44cfae87f` (the merge of #894), written 2026-11-24 on `zcrypto-ops`; bucket C family C3 (`docs/research/00.master-plan.md` §5), topics [T0228](../open-topics/T0228-btc-on-chain-metrics-computed-from-chain-data.md) and [T0016](../open-topics/T0016-bucket-b-c-alpha-families.md).
**The owner's pick**, verbatim, as the decisions log holds it in `[iter-210] C3's next step after the on-chain reading — the owner's pick on reading 10, which named trial 1 (Decision: 1)`: "write the spec for C3's trial 1 with Fable 5.2" (received by 2026-11-24T19:43:52Z).
Settled by that pick, by spec 00164 D12 and by reading 10: the cell (`asopr|low|flat|H7`), the family key `C3`, the test (`a1_kill_bar` at C3's count and a head-to-head against the sleeve as records 44 and 47 build it, net of 0.006 a side on its own turnover) and the contamination clause — D1–D4, D9, D10, D12.
Seven decisions were open — D5 (the instrument), D6 (the grid and the bar's instrument), D7 (the re-entry's size), D8 (the hold), D11 (how the reading's 32 looks enter the bar), D13 (the matrix's drawdown bound) and D16 (what a verdict changes): each states its options and their costs and marks one **Recommended**. The owner ruled all seven on 2026-11-24, each the option marked Recommended, and each pick is quoted verbatim at its decision's head.
The hypothesis below is written at those options; the plan review closes, and only then is this file's sha256 taken — before any return of arm B is computed (D15's hash rule).
The landed record spends one of bucket C's 10 trials: 10 remain today, 9 after.

## Intent

Reading 10 searched 32 cells for an on-chain band that names a gate action inside the A1 sleeve and found one: on the daily closes at which the sleeve holds an asset flat and the previous UTC day's aSOPR sits in its own low tail, the pooled log forward over 7 daily closes exceeded the flat state's other closes by 0.028296737371482382, Bonferroni far bounds 0.004537514065623878 to 0.05642393137934647, the summed mean after the events 0.030735850910887732 against the 0.012 round trip, 1539 events in 13 calendar years (the `[iter-209] BTC's on-chain regime read inside the A1 gate on btc-onchain-20261124T162656Z (reading 10)` entry; no figure of it is recomputed or extended here).
A forward contrast is not a book: this trial turns the cell into the rule spec 00164 D12 names — a re-entry on that band, in that state, held 7 closes, on the A1 sleeve — and asks whether the sleeve with it beats the sleeve without it net of its own trading, under the family's kill bar.
It is research: nothing ships to a host, no value it writes feeds the engine, and an adopt is recorded, never deployed (D16).

**Where this spec departs from spec 00149's form**, the closest precedent: its choices are laid out for the owner's picks, where spec 00149's were the loop's calls under a standing word; the record's block holds a second set, the frozen on-chain snapshot; the recommended bar is the daily one record 34 ran, where spec 00149's was the 4h one (D6); no stored figure anchors arm A to the last digit, so arm A is anchored by its positions against reading 10's line (D4, D15); the book is long-only, so there is no borrow, no carry, no borrow-unavailable twin and no limit to wire (D9); the matrix carries spec 00139's drawdown bound, a re-entry's (D13); the family key is added (D2); and nothing closes after the verdict (D16).

## The measured basis

Every figure below was measured on 2026-11-24 in this branch's worktree at `80987de07`, with the trial's code absent — the books program between 20:02:40Z and 20:02:57Z, the count program and the shell checks at 20:03:08Z, the tail program at 20:08:09Z, the arithmetic over their printed figures after it — with `data/btc-onchain-20261124T162656Z` and `data/ohlc-full` symlinked from the main checkout's `data/`, read and never written; `data/` in this worktree holds those two names and no other, and no `ohlc-holdout-*` path is read, listed or opened by anything here.
They read closes, weights, vol-target scales, positions, bands, states, counts and turnover only: **no forward return, no net-of-cost series, no Sharpe and no statistic of any re-entry's outcome is computed** — of arm B, of arm A, or of any size's book.
The books program calls `a1_book_returns` and `dynamic_inverse_vol_basket`, which compute a book's base returns on their way to its positions, since the vol target sizes on them, and `build_combined_system`, which computes the benchmark's series; the program keeps positions, scales and one length and reads nothing else of them.
Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

**The books**, a first program — the reads and the inputs by reading 10's own `_c3_reads` and `_c3_reading_inputs`, the events by `cli/alpha/c3.py`'s `flags`, the hold by `cli/alpha/b2.py`'s `reentry_positions`, never through the trial's code:

```python
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import c3 as alpha_c3
from cli.alpha.a1 import A1Config, _asset_returns, _inverse_vol_weights, a1_book_returns
from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import reentry_positions
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.onchain.series import priced
from cli.portfolio.builder import build_combined_system
from cli.portfolio.crossfreq_system import _A1_CADENCE, _block_start, _dummy_close, _ffill_btc
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

DATASET = "btc-onchain-20261124T162656Z"
HOLD = 7
print("start", datetime.now(UTC).isoformat(timespec="seconds"))
line = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
print("the ledger's last line: reading", line["reading_id"], line["iteration"], line["invocation"]["subject"], line["invocation"]["commit"])
reader = ObservedReader(Path("data"))
t0 = time.perf_counter()
provenance, snapshot, daily_ts, daily_prices = subjects._c3_reads(reader, DATASET, "c3-onchain-reading")
inputs = subjects._c3_reading_inputs(snapshot, daily_ts, daily_prices)
print(f"the reads and the reading's inputs half, {time.perf_counter() - t0:.1f} s")
n = len(daily_ts) - 1
print(f"daily union {len(daily_ts)} stamps, {daily_ts[0]} -> {daily_ts[-1]}, completed returns {n}; snapshot {snapshot.height} rows, {snapshot['ts'][0]} -> {snapshot['ts'][-1]}")
block = reader.block()
print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in block.items()})
print("the block is reading 10's:", compute_hash(block) == line["dataset_hash"], block == line["datasets"])
print("vouched", reader.vouched_status(), "holes", reader.holes())
print("as-of line", provenance["as_of_line"])
metrics = line["metrics"]
print(
    "the inputs half against reading 10's line: arm", inputs.arm == metrics["arm"],
    "; counts", inputs.counts == metrics["counts"],
    "; features", {f: {k: v for k, v in b.items() if k != "values"} for f, b in inputs.features.items()} == metrics["features"],
)

assets = list(inputs.positions)
rows = n + 1
fires_all = {a: [f is True for f in alpha_c3.flags(inputs.bands["asopr"], inputs.states[a], tail="low", in_state="flat")] for a in assets}
print("events over the", rows, "position rows", sum(map(sum, fires_all.values())), "; at the forming row", sum(f[n] for f in fires_all.values()), "; reading 10's counts", sum(v["events"] for v in metrics["counts"]["asopr|low|flat"].values()), "; its pooled H7 events", metrics["cells"]["asopr|low|flat|H7"]["log"]["pooled"][0])
fires = {a: f[:n] for a, f in fires_all.items()}
arm_a = {a: p[:n] for a, p in inputs.positions.items()}
close = daily_ts[1:]
per_year_returns = {}
for stamp in close:
    per_year_returns[str(stamp.year)] = per_year_returns.get(str(stamp.year), 0) + 1
print("returns per close year", per_year_returns)
# Record 33's frozen daily benchmark, the series record 34's bar read; built, its length read and no value of it.
print("the daily benchmark's net-of-cost series holds", len(build_combined_system(daily_prices, config=subjects._RECORD33_CONFIG).benchmark_net_of_cost), "returns")


def years(flags):
    out = {}
    for k, flag in enumerate(flags):
        if flag:
            out[str(close[k].year)] = out.get(str(close[k].year), 0) + 1
    return dict(sorted(out.items()))


event = [any(fires[a][k] for a in assets) for k in range(n)]
low = [b == "low" for b in inputs.bands["asopr"][:n]]
print(f"events over the {n} completed returns {sum(map(sum, fires.values()))} at {sum(event)} closes; the low band is read at {sum(low)} of them, every asset with a close long at {sum(low) - sum(event)}")
print("  per asset", {a: sum(fires[a]) for a in assets})
print("  event closes per close year", years(event))
print("  assets firing at an event close: median", statistics.median(sum(fires[a][k] for a in assets) for k in range(n) if event[k]), "max", max(sum(fires[a][k] for a in assets) for k in range(n)))
runs, k = [], 0
while k < n:
    if low[k]:
        j = k
        while j + 1 < n and low[j + 1]:
            j += 1
        runs.append(j - k + 1)
        k = j + 1
    else:
        k += 1
print(f"  the low band's {sum(low)} closes fall in {len(runs)} runs, closes per run median {statistics.median(runs)}, mean {statistics.fmean(runs):.2f}, max {max(runs)}")

# Why the sleeve is flat at an event: BTC's 200-day gate at that close, the sleeve's own read (cli/alpha/a1.py).
d_pf = _ffill_btc({a: list(closes) + [_dummy_close(closes)] for a, closes in daily_prices.items()})
gate = sma_gate(d_pf["BTC"], window=200)
why = {"before the gate's first warm close (k < 199)": 0, "BTC at or below its 200-day SMA": 0, "BTC above it, the asset's own legs": 0}
for a in assets:
    for k in range(n):
        if fires[a][k]:
            why["before the gate's first warm close (k < 199)" if k < 199 else "BTC at or below its 200-day SMA" if gate[k] == 0.0 else "BTC above it, the asset's own legs"] += 1
print("  the sleeve flat at an event:", why)

# The sizes a re-entry could take, from weights and vol-target scales alone.
own = a1_book_returns(d_pf, d_pf["BTC"], config=A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12))
mean7 = lambda series: [statistics.mean(series[_block_start(k, o)] for o in range(_A1_CADENCE)) for k in range(rows)]  # noqa: E731
print("the sleeve's rows are the 7-offset mean of a1_book_returns' positions:", all(mean7(own["asset_positions"][a]) == inputs.positions[a] for a in assets))
weights = _inverse_vol_weights(d_pf, lookback=30)
returns = {a: _asset_returns(d_pf[a]) for a in assets}
# a1_book_returns' own base-return loop with every direction 1.0, against the B sleeve's primitive on the same feed.
looped = []
for k in range(rows):
    total = 0.0
    for a in assets:
        r = returns[a][k]
        if r is not None:
            total += weights[k].get(a, 0.0) * 1.0 * r
    looped.append(total)
basket = dynamic_inverse_vol_basket(d_pf, lookback=30)
print("dynamic_inverse_vol_basket against a1_book_returns' loop with every direction long: equal", basket == looped, "; max abs difference", max(abs(x - y) for x, y in zip(basket, looped, strict=True)))
scale_full = vol_target(basket, target_vol=0.12 / math.sqrt(365), lookback=30, max_leverage=1.0)
scale_own = own["vol_target_positions"]
sizes = {
    "all-long, the sleeve's cadence": {a: mean7([weights[k].get(a, 0.0) * scale_full[k] for k in range(rows)])[:n] for a in assets},
    "the sleeve's own scale, its cadence": {a: mean7([weights[k].get(a, 0.0) * scale_own[k] for k in range(rows)])[:n] for a in assets},
    "all-long, daily": {a: [weights[k].get(a, 0.0) * scale_full[k] for k in range(n)] for a in assets},
}
at_events = [(a, k) for a in assets for k in range(n) if fires[a][k]]
print("the sleeve's own vol-target scale at the event closes: 0 at", sum(scale_own[k] == 0 for k in range(n) if event[k]), "; at its 1.0 cap at", sum(scale_own[k] == 1.0 for k in range(n) if event[k]), "; of", sum(event))
print("the all-long scale at the event closes: 0 at", sum(scale_full[k] == 0 for k in range(n) if event[k]), "; at its 1.0 cap at", sum(scale_full[k] == 1.0 for k in range(n) if event[k]), f"; mean {statistics.fmean(scale_full[k] for k in range(n) if event[k]):.6f}")
for name, size in sizes.items():
    held = [size[a][k] for a, k in at_events]
    print(f"{name}: at the {len(held)} events the size is 0 at {sum(s == 0 for s in held)}, median {statistics.median(held):.6f}, mean {statistics.fmean(held):.6f}, max {max(held):.6f}")


def held_through(size):
    out = {}
    for a in assets:
        left, row = 0, []
        for k, p in enumerate(arm_a[a]):
            if fires[a][k]:
                left = max(left, HOLD)
            row.append(max(p, size[a][k]) if left > 0 else p)
            left = max(0, left - 1)
        out[a] = row
    return out


turnover_a = book_turnover(arm_a)
print(f"arm A: turnover {turnover_a!r}; largest gross {max(math.fsum(arm_a[a][k] for a in assets) for k in range(n)):.6f}; largest position {max(max(arm_a[a]) for a in assets):.6f}; closes with a position above 0.20: {sum(any(arm_a[a][k] > 0.20 for a in assets) for k in range(n))}")
books = {}
for name, size in sizes.items():
    for rule, arm_b in (("closed where the sleeve turns long", reentry_positions(arm_a, size, fires, hold=HOLD)), ("held through", held_through(size))):
        books[(name, rule)] = arm_b
        differ = [any(arm_b[a][k] != arm_a[a][k] for a in assets) for k in range(n)]
        first = differ.index(True)
        reentered = [(a, k) for a in assets for k in range(n) if arm_a[a][k] == 0 and arm_b[a][k] > 0]
        above = sum(arm_a[a][k] > 0 and arm_b[a][k] != arm_a[a][k] for a in assets for k in range(n))
        entries = sum(arm_b[a][k] != arm_a[a][k] and (k == 0 or arm_b[a][k - 1] == arm_a[a][k - 1]) for a in assets for k in range(n))
        added = math.fsum(arm_b[a][k] - arm_a[a][k] for a in assets for k in range(n))
        turnover_b = book_turnover(arm_b)
        gross = [math.fsum(arm_b[a][k] for a in assets) for k in range(n)]
        print(f"{name}; {rule}:")
        print(f"  asset-closes flat in arm A and long in arm B {len(reentered)}, long in both and larger in arm B {above}, entries {entries}, {(len(reentered) + above) / entries:.1f} closes per entry; closes where the books differ {sum(differ)}, first {first}, close {close[first].isoformat()}, {n - first} returns from it")
        print(f"  turnover {turnover_b!r}, over arm A {turnover_b - turnover_a!r}; exposure added {added:.6f} asset-closes of NAV, mean {added / (len(reentered) + above):.6f}; break-even mean asset return per added close {(turnover_b - turnover_a) * 0.006 / added:.6%}")
        print(f"  largest gross {max(gross):.6f}, mean gross where the books differ {statistics.fmean(g for g, d in zip(gross, differ) if d):.6f}; largest position {max(max(arm_b[a]) for a in assets):.6f}; closes with a position above 0.20: {sum(any(arm_b[a][k] > 0.20 for a in assets) for k in range(n))}")

chosen = books[("all-long, the sleeve's cadence", "closed where the sleeve turns long")]
size = sizes["all-long, the sleeve's cadence"]
flat_long = [sum(arm_a[a][k] == 0 and chosen[a][k] > 0 for a in assets) for k in range(n)]
per_year = {}
for k, count in enumerate(flat_long):
    per_year[str(close[k].year)] = per_year.get(str(close[k].year), 0) + count
print("the recommended book, arm B")
print("  reentered_per_year", per_year)
events_per_year = {}
for a in assets:
    for k in range(n):
        if fires[a][k]:
            events_per_year[str(close[k].year)] = events_per_year.get(str(close[k].year), 0) + 1
print("  events_per_year", dict(sorted(events_per_year.items())), "; events_without_size", sum(size[a][k] == 0 for a, k in at_events))
print("  positions_differ_per_year", years([any(chosen[a][k] != arm_a[a][k] for a in assets) for k in range(n)]))
print("  reentry_entries", sum(chosen[a][k] != arm_a[a][k] and (k == 0 or chosen[a][k - 1] == arm_a[a][k - 1]) for a in assets for k in range(n)), "; gross_max", repr(max(math.fsum(chosen[a][k] for a in assets) for k in range(n))), "; a position below 0 at", sum(chosen[a][k] < 0 for a in assets for k in range(n)), "asset-closes")
print("  reentered per asset", {a: sum(arm_a[a][k] == 0 and chosen[a][k] > 0 for k in range(n)) for a in assets})
print("  before return index 199:", sum(flat_long[:199]), "; before 230:", sum(flat_long[:230]))
window = {a: [any(fires[a][max(0, k - HOLD + 1) : k + 1]) for k in range(n)] for a in assets}
print("  asset-closes inside an event's 7 closes:", sum(map(sum, window.values())), "; the sleeve long at", sum(window[a][k] and arm_a[a][k] > 0 for a in assets for k in range(n)), "; flat with no size at", sum(window[a][k] and arm_a[a][k] == 0 and size[a][k] == 0 for a in assets for k in range(n)), "; flat after the sleeve closed the hold at", sum(window[a][k] and arm_a[a][k] == 0 and size[a][k] > 0 and chosen[a][k] == 0 for a in assets for k in range(n)))
first = next(k for k in range(n) if any(chosen[a][k] != arm_a[a][k] for a in assets))
print("  turnover_b", repr(book_turnover(chosen)), "; first engagement", first, "; arm B is arm A to the bit before it:", all(chosen[a][:first] == arm_a[a][:first] for a in assets))

# The snapshot's days no cell of reading 10 read: the low band's days after 2026-03-30, from the feature alone.
days = [stamp.date() for stamp in snapshot["ts"].to_list()]
column = alpha_c3.from_first_day(days, snapshot["asopr"].to_list())
column = [v if priced(p) else None for v, p in zip(column, snapshot["price"].to_list(), strict=True)]
band = alpha_c3.bands(column)
later = {}
for day, b in zip(days, band, strict=True):
    if day.isoformat() > "2026-03-30":
        key = day.strftime("%Y-%m")
        later.setdefault(key, {"days": 0, "low": 0})
        later[key]["days"] += 1
        later[key]["low"] += b == "low"
print("the snapshot's days after 2026-03-30:", sum(v["days"] for v in later.values()), "; in the low band", sum(v["low"] for v in later.values()), later)
print("  of them from 2026-07-10:", sum(d.isoformat() >= "2026-07-10" for d in days), "; in the low band", sum(b == "low" for d, b in zip(days, band, strict=True) if d.isoformat() >= "2026-07-10"))
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-11-24T20:02:40+00:00
the ledger's last line: reading 10 iter-209 c3-onchain-reading 88fdf97e14a4ee5076db35468f4b0177d0e7cb31
the reads and the reading's inputs half, 8.1 s
daily union 4582 stamps, 2013-09-10 00:00:00+00:00 -> 2026-03-31 00:00:00+00:00, completed returns 4581; snapshot 6529 rows, 2009-01-03 00:00:00+00:00 -> 2026-11-23 00:00:00+00:00
block 19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a {'btc-onchain-20261124T162656Z': (1, 6529, ['2009-01-03 00:00:00+00:00', '2026-11-23 00:00:00+00:00']), 'ohlc-full': (10, 29032, ['2013-09-10 00:00:00+00:00', '2026-03-31 00:00:00+00:00'])}
the block is reading 10's: True True
vouched {'btc-onchain-20261124T162656Z': 'checked (1 vouched hashes)', 'ohlc-full': 'checked (36 vouched hashes)'} holes {}
as-of line {'relpath': 'index/2026/11/23.json', 'sha256': '2d9b2f4529042094111751c8b1f22ec5cd04577be507e2a8911a2e1a228bb5e2'}
the inputs half against reading 10's line: arm True ; counts True ; features True
events over the 4582 position rows 1549 ; at the forming row 0 ; reading 10's counts 1549 ; its pooled H7 events 1539
returns per close year {'2013': 108, '2014': 365, '2015': 365, '2016': 366, '2017': 365, '2018': 365, '2019': 365, '2020': 366, '2021': 365, '2022': 365, '2023': 365, '2024': 366, '2025': 365, '2026': 90}
the daily benchmark's net-of-cost series holds 4581 returns
events over the 4581 completed returns 1549 at 309 closes; the low band is read at 319 of them, every asset with a close long at 10
  per asset {'ADA': 153, 'AVAX': 78, 'BTC': 290, 'DOGE': 99, 'DOT': 84, 'ETH': 181, 'LINK': 100, 'LTC': 290, 'SOL': 80, 'XRP': 194}
  event closes per close year {'2013': 2, '2014': 63, '2015': 38, '2017': 1, '2018': 71, '2019': 29, '2020': 13, '2021': 12, '2022': 58, '2023': 6, '2024': 1, '2025': 2, '2026': 13}
  assets firing at an event close: median 4 max 10
  the low band's 319 closes fall in 190 runs, closes per run median 1.0, mean 1.68, max 9
  the sleeve flat at an event: {"before the gate's first warm close (k < 199)": 14, 'BTC at or below its 200-day SMA': 1496, "BTC above it, the asset's own legs": 39}
the sleeve's rows are the 7-offset mean of a1_book_returns' positions: True
dynamic_inverse_vol_basket against a1_book_returns' loop with every direction long: equal False ; max abs difference 5.551115123125783e-17
the sleeve's own vol-target scale at the event closes: 0 at 237 ; at its 1.0 cap at 23 ; of 309
the all-long scale at the event closes: 0 at 0 ; at its 1.0 cap at 0 ; mean 0.150538
all-long, the sleeve's cadence: at the 1549 events the size is 0 at 29, median 0.019409, mean 0.028705, max 0.227859
the sleeve's own scale, its cadence: at the 1549 events the size is 0 at 1259, median 0.000000, mean 0.021618, max 0.748722
all-long, daily: at the 1549 events the size is 0 at 29, median 0.018515, mean 0.027927, max 0.243169
arm A: turnover 46.72757036801258; largest gross 0.764856; largest position 0.678877; closes with a position above 0.20: 224
all-long, the sleeve's cadence; closed where the sleeve turns long:
  asset-closes flat in arm A and long in arm B 4899, long in both and larger in arm B 0, entries 367, 13.3 closes per entry; closes where the books differ 977, first 97, close 2013-12-21T00:00:00+00:00, 4484 returns from it
  turnover 69.84081467289158, over arm A 23.113244304879004; exposure added 143.024898 asset-closes of NAV, mean 0.029195; break-even mean asset return per added close 0.096962%
  largest gross 0.764856, mean gross where the books differ 0.157851; largest position 0.678877; closes with a position above 0.20: 238
all-long, the sleeve's cadence; held through:
  asset-closes flat in arm A and long in arm B 4899, long in both and larger in arm B 49, entries 367, 13.5 closes per entry; closes where the books differ 986, first 97, close 2013-12-21T00:00:00+00:00, 4484 returns from it
  turnover 69.21444271311105, over arm A 22.486872345098476; exposure added 143.681003 asset-closes of NAV, mean 0.029038; break-even mean asset return per added close 0.093903%
  largest gross 0.764856, mean gross where the books differ 0.159055; largest position 0.678877; closes with a position above 0.20: 238
the sleeve's own scale, its cadence; closed where the sleeve turns long:
  asset-closes flat in arm A and long in arm B 1063, long in both and larger in arm B 0, entries 131, 8.1 closes per entry; closes where the books differ 277, first 335, close 2014-08-16T00:00:00+00:00, 4246 returns from it
  turnover 76.55647068913908, over arm A 29.828900321126497; exposure added 121.618936 asset-closes of NAV, mean 0.114411; break-even mean asset return per added close 0.147159%
  largest gross 1.000000, mean gross where the books differ 0.479473; largest position 0.748722; closes with a position above 0.20: 282
the sleeve's own scale, its cadence; held through:
  asset-closes flat in arm A and long in arm B 1063, long in both and larger in arm B 45, entries 142, 7.8 closes per entry; closes where the books differ 284, first 335, close 2014-08-16T00:00:00+00:00, 4246 returns from it
  turnover 76.79277341248084, over arm A 30.065203044468262; exposure added 123.300832 asset-closes of NAV, mean 0.111282; break-even mean asset return per added close 0.146302%
  largest gross 1.000000, mean gross where the books differ 0.479440; largest position 0.748722; closes with a position above 0.20: 284
all-long, daily; closed where the sleeve turns long:
  asset-closes flat in arm A and long in arm B 4899, long in both and larger in arm B 0, entries 367, 13.3 closes per entry; closes where the books differ 977, first 97, close 2013-12-21T00:00:00+00:00, 4484 returns from it
  turnover 71.13840963296775, over arm A 24.41083926495517; exposure added 142.796488 asset-closes of NAV, mean 0.029148; break-even mean asset return per added close 0.102569%
  largest gross 0.764856, mean gross where the books differ 0.157617; largest position 0.678877; closes with a position above 0.20: 238
all-long, daily; held through:
  asset-closes flat in arm A and long in arm B 4899, long in both and larger in arm B 52, entries 368, 13.5 closes per entry; closes where the books differ 985, first 97, close 2013-12-21T00:00:00+00:00, 4484 returns from it
  turnover 70.70238590642731, over arm A 23.97481553841473; exposure added 143.396663 asset-closes of NAV, mean 0.028963; break-even mean asset return per added close 0.100315%
  largest gross 0.764856, mean gross where the books differ 0.158638; largest position 0.678877; closes with a position above 0.20: 238
the recommended book, arm B
  reentered_per_year {'2013': 20, '2014': 374, '2015': 228, '2016': 0, '2017': 7, '2018': 726, '2019': 516, '2020': 243, '2021': 283, '2022': 1700, '2023': 166, '2024': 56, '2025': 140, '2026': 440}
  events_per_year {'2013': 4, '2014': 125, '2015': 76, '2017': 1, '2018': 294, '2019': 146, '2020': 76, '2021': 59, '2022': 580, '2023': 30, '2024': 8, '2025': 20, '2026': 130} ; events_without_size 29
  positions_differ_per_year {'2013': 10, '2014': 189, '2015': 114, '2017': 7, '2018': 183, '2019': 112, '2020': 40, '2021': 52, '2022': 170, '2023': 35, '2024': 7, '2025': 14, '2026': 44}
  reentry_entries 367 ; gross_max 0.7648558752122554 ; a position below 0 at 0 asset-closes
  reentered per asset {'ADA': 483, 'AVAX': 254, 'BTC': 913, 'DOGE': 326, 'DOT': 289, 'ETH': 559, 'LINK': 333, 'LTC': 902, 'SOL': 246, 'XRP': 594}
  before return index 199: 52 ; before 230: 114
  asset-closes inside an event's 7 closes: 5119 ; the sleeve long at 106 ; flat with no size at 114 ; flat after the sleeve closed the hold at 0
  turnover_b 69.84081467289158 ; first engagement 97 ; arm B is arm A to the bit before it: True
the snapshot's days after 2026-03-30: 238 ; in the low band 19 {'2026-03': {'days': 1, 'low': 0}, '2026-04': {'days': 30, 'low': 0}, '2026-05': {'days': 31, 'low': 1}, '2026-06': {'days': 30, 'low': 8}, '2026-07': {'days': 31, 'low': 1}, '2026-08': {'days': 31, 'low': 1}, '2026-09': {'days': 30, 'low': 0}, '2026-10': {'days': 31, 'low': 0}, '2026-11': {'days': 23, 'low': 8}}
  of them from 2026-07-10: 137 ; in the low band 10
end 2026-11-24T20:02:57+00:00
```

What it establishes:

- **The sets and the block.** `btc-onchain-20261124T162656Z` — one file, 6,529 rows, 2009-01-03 → 2026-11-23, `checked (1 vouched hashes)`, cut from the chain's as-of line `index/2026/11/23.json` (sha256 `2d9b2f4529042094111751c8b1f22ec5cd04577be507e2a8911a2e1a228bb5e2`) — and `ohlc-full`'s ten EUR 1440-minute files — 29,032 rows, 2013-09-10 → 2026-03-31, `checked (36 vouched hashes)` — with no hole form the block `19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a`: reading 10's `dataset_hash`, the two blocks equal file for file. The daily union holds 4,582 stamps and 4,581 completed returns; by close year 2013 holds 108 and 2026 holds 90, the two stub years, and every year between is whole.
- **The inputs half is reading 10's.** `_c3_reading_inputs` over those reads returns reading 10's `arm`, `counts` and `features` blocks, each equal to the ledger line's — so the sleeve's rows, its states and aSOPR's bands here are the ones reading 10 read, by the code that produced them. The reads and the inputs half took 8.1 s.
- **The events.** The cell's flag is set at 1,549 asset-closes, none at the forming row — reading 10's count for `asopr|low|flat`, 1,539 of them the events of its pooled 7-close row, the other 10 with their seventh close past the set's last stamp (the third program). They fall on 309 closes; the low band is read at 319 closes, and at 10 of those every asset with a close is long. Per asset: ADA 153, AVAX 78, BTC 290, DOGE 99, DOT 84, ETH 181, LINK 100, LTC 290, SOL 80, XRP 194. Event closes per close year: 2013 2, 2014 63, 2015 38, 2017 1, 2018 71, 2019 29, 2020 13, 2021 12, 2022 58, 2023 6, 2024 1, 2025 2, 2026 13, none in 2016. An event close fires 4 assets at the median and 10 at the most. The low band's 319 closes fall in 190 runs, 1 close long at the median, 1.68 on average, 9 at the longest.
- **What the flat state is at an event.** 1,496 of the 1,549 events have BTC at or below its 200-day SMA, the sleeve's gate closed; 39 have BTC above it, the asset flat on its own trend, weight or scale; 14 fall before the gate's first warm close, return index 199. The re-entry buys inside the regime the gate stands aside from.
- **The sleeve's rows** are the 7-offset block-start mean of `a1_book_returns`' positions at records 44's and 47's configuration, to the bit.
- **The three sizes a re-entry could take** (D7), at the 1,549 events:
  - **All-long, at the sleeve's cadence** — the inverse-vol weight times the vol target of the equal-risk basket itself at the sleeve's 0.12, through the 7-offset mean: 0 at 29 events (an asset the basket does not weight yet), median 0.019409, mean 0.028705, max 0.227859. The all-long scale at the 309 event closes is never 0 and never at its 1.0 cap, 0.150538 on average.
  - **The sleeve's own scale, at its cadence** — spec 00139 D3's rule transcribed: 0 at 1,259 events, median 0, max 0.748722. The sleeve's own vol-target scale is 0 at 237 of the 309 event closes, where the book has been flat for its whole 30-return window and has no volatility to size on, and at its 1.0 cap at 23, where a nearly flat window gives a tiny one.
  - **All-long, daily** — the same weight and scale at each close, no cadence: 0 at 29, median 0.018515, mean 0.027927, max 0.243169.
- **`dynamic_inverse_vol_basket` is not `a1_book_returns`' loop to the bit**: over the same feed with every direction long the two differ by at most 5.551115123125783e-17, so the size is defined on one of them (D7) and the figures above are that definition's.
- **The six books** — three sizes by two hold rules (D8), each against arm A, whose turnover is 46.72757036801258, largest gross 0.764856 and largest single position 0.678877:
  - **All-long at the cadence, closed where the sleeve turns long** — 4,899 asset-closes flat in arm A and long in arm B, in 367 entries, 13.3 closes an entry; the books differ at 977 closes, first at return index 97 (close 2013-12-21), 4,484 returns from it; turnover 69.84081467289158, 23.113244304879004 over arm A; exposure added 143.024898 asset-closes of NAV, 0.029195 a re-entered asset-close; largest gross 0.764856, arm A's own, and 0.157851 on average where the books differ.
  - **The same, held through the sleeve's own entry** — differs from it at 49 asset-closes, where the sleeve is long and the size is larger; turnover 69.21444271311105.
  - **The sleeve's own scale** — 1,063 re-entered asset-closes in 131 entries, first at return index 335 (close 2014-08-16); mean size 0.114411, largest gross 1.000000; turnover 76.55647068913908, 29.828900321126497 over arm A.
  - **All-long, daily** — the cadence's 4,899 asset-closes and 367 entries; turnover 71.13840963296775, 24.41083926495517 over arm A.
- **The recommended book's engagement** — the plan's data-gated literals. `reentry_first_engaged` 97, `primary_returns` 4484, `stamps_positions_differ` 977, `reentry_entries` 367, `events_without_size` 29, `turnover_b` 69.84081467289158, `gross_max` 0.7648558752122554; `reentered_per_year` 2013 20, 2014 374, 2015 228, 2016 0, 2017 7, 2018 726, 2019 516, 2020 243, 2021 283, 2022 1,700, 2023 166, 2024 56, 2025 140, 2026 440; `events_per_year` 2013 4, 2014 125, 2015 76, 2017 1, 2018 294, 2019 146, 2020 76, 2021 59, 2022 580, 2023 30, 2024 8, 2025 20, 2026 130; `positions_differ_per_year` 2013 10, 2014 189, 2015 114, 2017 7, 2018 183, 2019 112, 2020 40, 2021 52, 2022 170, 2023 35, 2024 7, 2025 14, 2026 44; a year one of these lists leaves out counts 0 there, each per-year key carrying every year the closes span. Per asset the re-entered closes are ADA 483, AVAX 254, BTC 913, DOGE 326, DOT 289, ETH 559, LINK 333, LTC 902, SOL 246, XRP 594. Before return index 199, the gate's first warm close, 52 asset-closes are re-entered, and 114 before 230. Of the 5,119 asset-closes inside an event's 7 closes the sleeve is long at 106 and the size is 0 at 114; at none of them is the asset flat, sized and not re-entered. Arm B is arm A to the bit before return index 97, and no position of it is below 0.
- **The hurdle**, from positions alone: the added trading costs 23.113244304879004 × 0.006 = 0.138679465829274 of NAV over the window, 3.0927623958357276e-05 a bar from the first engagement, so a re-entered asset-close must carry a mean asset return of 0.096962 % to pay for itself, 0.6787 % over 7 closes (the arithmetic below) — below the reading's 1.2 % round trip because overlapping events share one entry and one exit, 4.22 events and 13.35 re-entered closes an entry. The own-scale size asks 0.147159 % a close, the daily size 0.102569 %.
- **§10's per-asset cap at the sleeve's level.** Arm A holds a position above 0.20 at 224 closes and arm B at 238, the largest 0.678877 in both: the sleeve alone carries no per-asset cap in records 44 and 47, where the cap binds the combined book (D9).
- **The days no forward has read.** The snapshot holds 238 days after 2026-03-30, the last day reading 10's last index reads; aSOPR is in its low band on 19 of them — one in May, 8 in June, one in July, one in August, 8 in November 2026 — and on 10 of the 137 from 2026-07-10, the first day after the spent holdout's window. In sample the low band is read on 319 closes, 25.4 a year.

**The count, the names and the bar's threshold**, a second program:

```python
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from cli.registry import budget
from cli.research import subjects
from cli.validation import deflated_sharpe_ratio
from cli.validation.dsr import expected_max_sharpe
from tests.retired_subjects import RETIRED_SUBJECTS

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
records = [json.loads(x) for x in Path("docs/reference/trial-registry.jsonl").read_text().splitlines()]
readings = [json.loads(x) for x in Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()]
print("BUCKET_OF", budget.BUCKET_OF, "BUDGET", budget.BUDGET)
print("registry", len(records), "records, by family", dict(Counter(r["family"] for r in records)), "; in no bucket's key:", sorted({r["family"] for r in records} - set(budget.BUCKET_OF)))
print("ledger", len(readings), "readings; carrying an attempt:", [r["reading_id"] for r in readings if r.get("attempt") is not None])
print("families the registered subjects declare:", dict(Counter(s.family for s in subjects.SUBJECTS.values() if s.family is not None)))
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("c3-asopr-reentry", "c3-asopr-reentry-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("names opening c3:", sorted(x for x in names if x.startswith("c3")), "; retired among them:", sorted(x for x in RETIRED_SUBJECTS if x.startswith("c3")))


def bound(n_obs, n_trials, var_trials):
    lo, hi = 0.0, 0.5
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if deflated_sharpe_ratio(mid, n_obs, n_trials, var_trials) <= 0.95 else (lo, mid)
    return hi


for label, n_obs, ppy in (("daily", 4_581, 365), ("4h", 27_337, 2_190)):
    hi = bound(n_obs, 1, 0.0)
    print(f"{n_obs} {label} returns at n_trials 1, var_trials 0.0: expected max Sharpe {expected_max_sharpe(1, 0.0)!r}; dsr_pass needs a per-period Sharpe above {hi:.6f}, annualised {hi * math.sqrt(ppy):.4f}")
print("mean block 17 holds two closes 6 apart in one block with probability", (16 / 17) ** 6, "; mean block 102,", (101 / 102) ** 6)
print("0.05 / 32 =", 0.05 / 32, "; at 2,000 resamples", 2000 * 0.05 / 32, "lie beyond it, at 10,000", 10000 * 0.05 / 32)
```

Its output, whole:

```text
read at 2026-11-24T20:03:08+00:00
BUCKET_OF {'A1': 'A', 'B1': 'B', 'B2': 'B', 'B3': 'B', 'B4': 'B', 'P1': None} BUDGET {'A': 40, 'B': 25, 'C': 10}
registry 64 records, by family {'A1': 40, 'P1': 7, 'B1': 5, 'B2': 7, 'B4': 2, 'B3': 3} ; in no bucket's key: []
ledger 10 readings; carrying an attempt: []
families the registered subjects declare: {'B2': 8, 'B1': 3, 'B4': 2, 'B3': 3, 'P1': 2}
c3-asopr-reentry equals or opens with a hyphen: [] ; it opens: []
c3-asopr-reentry-preflight equals or opens with a hyphen: [] ; it opens: []
names opening c3: ['c3-onchain-reading'] ; retired among them: ['c3-onchain-reading']
4581 daily returns at n_trials 1, var_trials 0.0: expected max Sharpe 0.0; dsr_pass needs a per-period Sharpe above 0.024309, annualised 0.4644
27337 4h returns at n_trials 1, var_trials 0.0: expected max Sharpe 0.0; dsr_pass needs a per-period Sharpe above 0.009949, annualised 0.4656
mean block 17 holds two closes 6 apart in one block with probability 0.6950665164333657 ; mean block 102, 0.942599515347665
0.05 / 32 = 0.0015625 ; at 2,000 resamples 3.125 lie beyond it, at 10,000 15.625
```

- **The count.** The registry's 64 records carry six family keys, each a key of `BUCKET_OF`, and none is a C family's; no reading carries an attempt; and no registered subject declares a C family. So no C3 record exists and, since an attempt's family is its subject's, the trial-attempts log can hold no C3 attempt (the closed-world claims): `required_n("C3")` is 0 + 0 + 1 = 1 once the key exists, and bucket C has spent 0 of 10.
- **The names.** No registered or retired subject's name equals `c3-asopr-reentry` or `c3-asopr-reentry-preflight` or opens either with a hyphen, and neither opens one; the one name opening `c3` is `c3-onchain-reading`, retired.
- **The DSR leg.** At `n_trials` 1 the expected maximum Sharpe is 0.0, so the leg is the PSR against 0: over 4,581 daily returns `dsr_pass` needs an annualised net Sharpe above 0.4644, over 27,337 4h returns above 0.4656 — the same bar on either grid (D6).
- **The blocks.** A stationary bootstrap at mean block 17 keeps two closes 6 apart, one hold's span, in one block with probability 0.695; at 102, reading 10's block, 0.943 (D6).
- **A Bonferroni head-to-head** over 32 looks at 5 % reads p < 0.0015625, which 2,000 resamples resolve with 3.125 draws beyond it and 10,000 with 15.625 (D11).

**The events reading 10's pooled row leaves out**, a third program:

```python
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import c3 as alpha_c3
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.registry.observed import ObservedReader
from cli.research import subjects

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
reader = ObservedReader(Path("data"))
_, snapshot, daily_ts, daily_prices = subjects._c3_reads(reader, "btc-onchain-20261124T162656Z", "c3-onchain-reading")
inputs = subjects._c3_reading_inputs(snapshot, daily_ts, daily_prices)
prices = _ffill_btc(daily_prices)
last = len(daily_ts) - 1
late, holed = 0, 0
for a, held in inputs.states.items():
    flag = alpha_c3.flags(inputs.bands["asopr"], held, tail="low", in_state="flat")
    for k, f in enumerate(flag):
        if f is True and k + 7 > last:
            late += 1
        elif f is True and prices[a][k + 7] is None:
            holed += 1
print("events with no close 7 closes on: past the set's last stamp", late, "; at a hole of the asset", holed, "; the last stamp's index", last)
```

Its output, whole:

```text
read at 2026-11-24T20:08:09+00:00
events with no close 7 closes on: past the set's last stamp 10 ; at a hole of the asset 0 ; the last stamp's index 4581
```

- The 10 events of the 1,549 that the pooled 7-close row does not hold each have their seventh close past the set's last stamp; none sits at a hole of its asset. In the trial each still opens a re-entry, over the returns that remain.

Reading 10, its spec and its code path, the tier, the family key's readers, and the arithmetic over the programs' printed figures:

```text
$ date -u +%Y-%m-%dT%H:%M:%SZ; hostname; git rev-parse HEAD; git merge-base HEAD origin/develop; sha256sum docs/specs/00164-t0228-btc-onchain-design.md; python3 -I -c 'import json; r = json.loads(open("docs/reference/reading-ledger.jsonl").read().splitlines()[-1]); print("reading", r["reading_id"], r["spec_hash"], r["invocation"]["commit"])'; git merge-base --is-ancestor 88fdf97e14a4ee5076db35468f4b0177d0e7cb31 HEAD && echo ancestor; git log --oneline 88fdf97e14a4ee5076db35468f4b0177d0e7cb31..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/onchain cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat
2026-11-24T20:03:08Z
zcrypto-ops
80987de07a6f1007dfc00507e7a0f21858e99686
44cfae87f53ebf6f41d60a2e170c43aa48ae8706
89eb8be96d6961b2f4c6240b6b6ce7a8a045768413f0a6087a810fe64067c86e  docs/specs/00164-t0228-btc-onchain-design.md
reading 10 89eb8be96d6961b2f4c6240b6b6ce7a8a045768413f0a6087a810fe64067c86e 88fdf97e14a4ee5076db35468f4b0177d0e7cb31
ancestor
$ uv run python infra/scripts/tier.py --paths cli/alpha/c3_reentry.py cli/research/subjects.py cli/registry/budget.py tests/test_alpha_c3_reentry.py tests/test_research_c3_asopr_reentry.py tests/test_research_c3_asopr_reentry_basis.py tests/test_trial_registry_provenance.py tests/test_research_command.py README.md; git grep -n 'BUCKET_OF' -- cli | cut -c1-110; git grep -c 'BUCKET_OF' -- tests; ls data
tier: full
full cli/registry/budget.py — under cli/registry/, read as a non-prose change
full tests/test_trial_registry_provenance.py — a test importing cli.registry, read as a non-prose change
full tests/test_research_command.py — a test importing cli.alpha, read as a non-prose change
cli/registry/budget.py:6:BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "B3": "B", "B4":
cli/research/command.py:126:        lines, landed, log_id=log_id, bucket_of=budget.BUCKET_OF, hold=None if fro
cli/research/command.py:320:            if family not in budget.BUCKET_OF:
cli/research/command.py:417:        bucket = budget.BUCKET_OF[family]
cli/research/command.py:424:            count = attempts.reconcile(lines, seen, log_id=log.log_id, bucket_of=b
cli/research/command.py:431:                    lines, seen, log_id=log.log_id, bucket_of=budget.BUCKET_OF, ho
cli/research/command.py:542:        count = attempts.reconcile(lines, settled, log_id=log.log_id, bucket_of=bu
tests/test_research_command.py:10
tests/test_trial_registry_provenance.py:7
btc-onchain-20261124T162656Z
ohlc-full
$ python3 -I -c '
added = 23.113244304879004
print("the added trading at 0.006 a side", added * 0.006, "; a bar from the first engagement", added * 0.006 / 4484)
print("7 closes at the break-even", 7 * (added * 0.006 / 143.024898))
print("events an entry", 1549 / 367, "; re-entered closes an entry", 4899 / 367, "; events with a size", 1549 - 29)
print("low-band closes a year in sample", 319 / (4581 / 365.25))
print("4h returns less daily", 27337 - 4581, "; their ratio", 27337 / 4581)
print("the unseen days", 1 + 100 + 137, "; the holdout window", 30 + 31 + 30 + 9)
'
the added trading at 0.006 a side 0.138679465829274 ; a bar from the first engagement 3.0927623958357276e-05
7 closes at the break-even 0.006787323566592706
events an entry 4.220708446866485 ; re-entered closes an entry 13.348773841961853 ; events with a size 1520
low-band closes a year in sample 25.434348395546824
4h returns less daily 22756 ; their ratio 5.967474350578477
the unseen days 238 ; the holdout window 100
```

- **Reading 10 and its spec are frozen**: spec 00164's sha256 is reading 10's `spec_hash`, and that file is not edited.
- **The code path since reading 10's run** at `88fdf97e1`, an ancestor of this branch's tip: the log to the tip prints nothing — no commit has touched it — so the reads, the sleeve, the bands, the states, the hold, the costing and the bar this trial reuses are the ones reading 10 and records 33, 34, 55 and 56 ran.
- **The tier**: the plan's files review at `full`, on `cli/registry/budget.py` and the two tests that import the registry and the alpha package.
- **The family key's readers**: `cli/registry/budget.py` defines `BUCKET_OF` and `cli/research/command.py` reads it at six sites, no other file under `cli/`; two test files name it.

Read from the tree, each by its path:

- **The sleeve in code**: records 44 and 47 build it at `cli/portfolio/crossfreq_system.py:318-322`, `_A1_CADENCE = 7` at `:77`, `_block_start` at `:214`; `cli/alpha/c3.py:59`'s `a1_daily_positions` is that expression before its 4h expansion, held equal to `build_crossfreq_system(…).sleeve_positions["A1"]` by `tests/test_alpha_c3.py::test_the_arm_expands_to_the_builders_a1_sleeve`.
- **The sleeve's own record is another object**: record 34 (`A1lf-weekly-v012`, adopt, `n_trials_in_family` 33) registered the mean of the seven offsets' net-of-cost series, "not of positions" (`cli/portfolio/record43_book.py:296-300`); records 44 and 47 hold the mean of positions and store no figure of the sleeve alone. Record 34's bar is in the tree as a data-gated regression, `tests/test_portfolio_builder.py::test_trial34_verdict_regression`: the frozen daily benchmark `build_combined_system(prices).benchmark_net_of_cost`, `mean_block=17`, `seed=42`, `decisive_start=230`, `n_resamples=2000`, the slices by close year with 2013 and 2026 out.
- **The hold in code**: `cli/alpha/b2.py:687`'s `reentry_positions`, spec 00139 D3's rule, which records 55 and 56 ran (B2's two re-entries on the A2-4h ensemble, both REJECT: head-to-heads −7.0648411551855595e-06 and −3.627103722074046e-05 a bar); `cli/alpha/b2.py:725`'s `net_of_cost`, `build_crossfreq_system`'s costing loop.
- **The budget in code**: `BUCKET_OF` holds no C key and `BUDGET["C"]` is 10 (`cli/registry/budget.py:6-7`); `--register` refuses a family outside `BUCKET_OF` (`cli/research/command.py:320`); `tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals` asserts both literals, its message naming what a change owes: "a new family joins with its bucket: each lands in a pull request that changes this literal and quotes the ruling".
- **The two rulings binding every C pre-registration** (`[iter-176]`, T0016 line 21): the DSR leg binds at every `n_trials`, `var_trials` 0.0 included; and a search may read the spent holdout's window, 2026-04-01 → 2026-07-09, through `ohlc-rolling`, but no result there is reported as holdout or out-of-sample evidence.
- **A trial a reading's cell named has been judged on the rolling set before**: B4 trial 2 (spec 00146 D2, D6; the owner's pick "SOL/BTC no-borrow, rolling (Recommended)", `[iter-190]`), its unseen months recorded beside the matrix as `unseen_returns`, `head_to_head_mean_outperf_unseen` and `head_to_head_spa_p_unseen`, in no leg of it.

**Not measured — each a premise the plan reads before it is relied on:**

- **Any return of either arm.** Arm A's net-of-cost series, its Sharpe and its bar are read at the pre-flight, after the hash; arm B's by the trial's one run (D15).
- **The daily benchmark's values.** Its length alone is read here; the pre-flight reads its annualised Sharpe against record 33's stored `benchmark_sharpe_full`, 1.2455, within the 0.005 `tests/test_portfolio_builder.py::test_frozen_figures_regression` holds it to (D15).
- **The trial-attempts log.** It lives in the main checkout's `.local/` and is not read here; the count above follows from the registry, the ledger and the subjects. The plan's count program reads `required_n("C3")` and bucket C's spent figure through `attempts.reconcile` once the key exists.
- **The run's time.** The reads and the inputs half take 8.1 s; the bars over 4,581 returns are not timed. Spec 00148's basis timed one `a1_kill_bar` over 27,337 synthetic returns at 11.16 s, 5.97 times this trial's length; the plan times the pre-flight.
- **`ohlc-rolling`** — its head on this workstation, that line's sha256, a hole of a pair the trial would read, and whether its 1440-minute bars equal `ohlc-full`'s over the span the two share: the set is not linked in this worktree, and D5's option 2 rests on all four.
- **The 4h union and the sleeve's expansion onto it**: D6's option 2 rests on spec 00149's basis, 27,338 stamps and 27,337 return indices, not re-read here.
- **Whether BRK's aSOPR of day D reads a block after D's last** is spec 00164 D3's premise, on which reading 10 already rests; it is relied on as reading 10 relied on it and not re-read here.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial is written, planned and run under one, the session holding this branch's worktree, `.claude/worktrees/c3-trial-1`, on `zcrypto-ops` (`hostname`, measured) — the research workstation and the venue-facing ops node at once. No session runs a play, a converge, `ssh` or `docker` for it: the trial touches no host.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Neither makes a network call.
- **What else runs on the host and what it shares with the trial: nothing the trial reads.** The on-chain writer (`zcrypto-onchain-write.timer`, hourly) extends the live vintage chain under the ops data root; the trial reads the frozen snapshot under `data/`, written once by `onchain freeze`, identified by its file's bytes and its manifest's set hash, its provenance naming the chain's as-of line (measured). `data/ohlc-full` is a frozen, attested set. Both are symlinks from this worktree into the main checkout's `data/`; a run writes nothing under either, and each link is unlinked before `git worktree remove`.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1), its id `60c9f39c37ec81b4a53396218b690304` listed for `zcrypto-ops` in `docs/reference/trial-attempt-logs.txt`; an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained. An append chains onto develop's last line, which D15's develop check holds before the run; `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and its `LANDED_N_TRIALS` row before anything else lands.

## Hypothesis (trial 1, pre-registered by this spec's sha256)

C3's one question is "marginal value inside the A1 gate" (`00.master-plan.md` §5): coins moved at a loss, read on-chain a day late, mark closes at which the assets the gate holds flat go on to rise by more than its other flat closes, so **the A1 sleeve as records 44 and 47 build it, with a long re-entry in each asset it holds flat at a daily close where the previous UTC day's aSOPR lies at or below the 10th percentile of its own history from 2011-01-01, read after 365 values — the re-entry sized as the sleeve's own construction sizes a book long in every weighted asset, held 7 daily closes from the last such close and closed where the sleeve itself turns long — has a higher mean net-of-cost return than the sleeve alone from the first close the two books differ, net of each asset's own turnover at 0.006 a side.**
Arm A is the sleeve exactly as reading 10 read it; arm B is long-only and borrows nothing.
It is judged by D13's matrix on its own record; what its verdict changes is D16's.
The statement is written at the options of D5–D8 that the owner's picks took.

## D1 — the pick: C3's trial 1, the cell reading 10 named (the owner's)

- The owner's words are quoted in this spec's head. The option they took, as the `[iter-210]` entry holds it: "**C3's trial 1 under its own spec** — `asopr|low|flat|H7`, aSOPR's low tail as a re-entry for the A1 sleeve's flat state, the one cell reading 10 found with potential, pre-registered in a new spec that adds the family key `C3` to `BUCKET_OF` and tests it as spec 00164 D12 says; T0016's Glassnode step, `_pit` diff first, stands beside it in T0228's next steps. Spends a C slot on a cell designed on the history the A1 sleeve was adopted on." The option set aside was C3's family call on reading 10 alone.
- One iteration, one branch, this spec and its plan (`docs/plans/00165-c3-trial-1-asopr-reentry.md`), one plan review, one task loop; one trial subject with its pre-flight twin, one bar, one matrix, one record.
- The budget: the landed record spends one of bucket C's 10 (`BUDGET["C"]`, none spent, measured); a stop, a refused build or a refusal from the count spends none.

## D2 — the family key `C3` and its count (settled by spec 00164 D12)

- `cli/registry/budget.py`'s `BUCKET_OF` gains `"C3": "C"`, the key spec 00164 D12 says this trial's spec adds; `BUDGET` is unchanged. Spec 00133 D5 names how a key joins — "a new family joins `BUCKET_OF`, with its bucket, in a reviewed PR" — and the asserted literal in `tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals` changes in that same pull request, whose body quotes the owner's pick.
- C1 and C2 gain no key: each opened with a no-slot reading (readings 8 and 7) and has no trial; a key with no subject is a budget line nothing can spend.
- **The count is 1**, `_C3_ASOPR_REENTRY_N_TRIALS`: C3's true count with this trial, `required_n("C3")` = 0 records + 0 orphans + 1 (measured from the registry and the subjects; the plan reads the log's own answer before its review). Fixed by this spec's hash, never raised in place: spec 00133 D4 refuses a declared count below `required_n`, so a C3 attempt landing elsewhere before this run refuses it, and the trial goes back to the owner through T0228 — a further count is a new subject under a new spec.

## D3 — the trigger: the cell's, every constant reading 10's (settled by reading 10)

- **An event** is an asset-close at which the cell's flag is set: at union return index `k` for asset `a`, `alpha_c3.flags(bands["asopr"], states[a], tail="low", in_state="flat")[k] is True` — the sleeve's position in `a` at `k` is 0, `a` has a close at `k`, and the snapshot's `asopr` of day `ts[k] − 1 day` is in its low band.
- **The band** is reading 10's: the day's expanding-percentile rank among its own history from 2011-01-01 at or below 0.10, read once 365 values exist, a day holding a value only where its aSOPR is finite and BRK's price that day is finite and above 0 (`cli/alpha/c3.py`'s `LOW`, `MIN_HISTORY`, `LAG_DAYS`, `FIRST_DAY`, `bands`, `from_first_day`, `lagged`; spec 00164 D6, D7, D12). The lag is one day: the decision at bar `k`'s close, the 00:00Z that ends day `ts[k]`, reads day `ts[k] − 1 day`, closed and confirmed for most of a day.
- **The code is reading 10's, unchanged**: the trial's inputs call `_c3_reads` and `_c3_reading_inputs` (`cli/research/subjects.py:5179`, `:5216`) and take `inputs.bands["asopr"]`, `inputs.states` and `inputs.positions` from them — the inputs half `tests/test_research_c3_onchain_reading.py::test_the_inputs_half_reads_no_forward` holds free of any forward. A state of `None` — an asset with no close at `k` — fires nothing. Measured: 1,549 events at 309 closes.
- **The action and the horizon** are the cell's: a long re-entry (spec 00164 D12's leg 3, "positive in the flat state → a re-entry"), held 7 daily closes (`H7`).
- A band, a lag, a first day, a history length or a horizon changed after a result is a new trial.

## D4 — arm A: the sleeve as records 44 and 47 build it (settled by spec 00164 D12)

- **Arm A** is `alpha_c3.a1_daily_positions(daily_prices)` over the 4,581 completed returns — the A1-lf weekly sleeve, `a1_book_returns` at `A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)` on the BTC-forward-filled daily closes with the builder's dummy close appended, averaged over the seven weekly offsets by `_block_start`; the row the dummy close forms, index 4,581, has no return and is dropped. It is reading 10's arm — the same function over the same bytes, its long and flat counts the ledger line's `arm` block (measured) — and its expansion is the builder's `sleeve_positions["A1"]` (the test named in the basis).
- **No stored figure anchors its returns.** Record 34's 1.3798 is the offsets' mean of net series, another object, and records 44 and 47 store nothing of the sleeve alone (the basis). Arm A is therefore anchored by what it holds — reading 10's `arm` and `counts` blocks, the engagement's literals — and its bar is read at the pre-flight, after the hash (D15).
- No change to `cli/alpha/a1.py`, `cli/alpha/c3.py`, `cli/portfolio/*` or any adopted artifact.

## D5 — the instrument (the owner's)

**The owner's pick, 2026-11-24 (by 20:14:37Z), verbatim:** "Reading 10's sets (Recommended)". The option marked Recommended below is taken.
Which closes the trial's returns come from decides whether any of them lies outside the history the cell was found on.

1. **The two sets reading 10 read, both whole: the frozen snapshot `btc-onchain-20261124T162656Z` and frozen `ohlc-full`** — **Recommended**.
   - `--dataset btc-onchain-20261124T162656Z`, no `--window`, no `--as-of`, `ohlc-full` read by name beside it through `_c3_reads` unchanged: reading 10's invocation. The record's block is reading 10's, `19ee5c23…74f7a` (measured), and every premise this design rests on is measured on it.
   - **Why**: the trial can reject on these sets alone, and the 238 snapshot days after 2026-03-30 — 19 in the low band, 10 of them after the spent holdout's window — stay unread by any forward. They and the days the chain adds are the only ones on which this rule can be read clean, they accrue at about 25 low-band days a year, and read under a criterion fixed beforehand (D16) they are evidence; read now beside a verdict, with no leg, they are a glimpse that spends them.
   - **Cost**: every return the verdict reads lies in the history the cell was found on, so an adopt here says the cell survives its own trading costs in book form, and nothing about an unseen day (D10).
2. **`ohlc-rolling` as of a named day, with the same snapshot** — B4 trial 2's instrument (spec 00146 D2, D6).
   - Full history from 2013-09-10 to the as-of day: the months reading 10 never saw join the bar's and the head-to-head's returns, and are read apart beside the matrix — `unseen_returns`, `head_to_head_mean_outperf_unseen` and `head_to_head_spa_p_unseen` from the first return closing after 2026-03-31, in no leg. The spent holdout's window inside them is read under `[iter-176]`: no figure of the trial is reported as holdout or out-of-sample evidence.
   - **Cost**: the unseen days are spent as a no-leg diagnostic of at most 19 low-band days, 16 of them in June and November 2026; none of its premises is measured here (the basis's *Not measured*: the mirror's head and its line, a hole, the two sets' equality at 1440), so the plan measures each before its review and an inequality over the shared span goes to the owner; `_c3_reads` names `ohlc-full` and is replaced; the block, the anchors against reading 10's line and every data-gated literal move.
3. **The unseen days alone** — the snapshot's days after 2026-03-30 over `ohlc-rolling`, nothing the reading read.
   - The one instrument with no contamination. **Cost**: 19 low-band days today, about 25 a year: no bar of four legs can be read on them for years, and 100 of the 238 days lie in the spent holdout's window, which `[iter-176]` bars from being reported as out-of-sample.

`ohlc-holdout-2026-07-10` is no option under any of the three: its one look was spent on 2026-07-10 (`00.master-plan.md:323`), and `[iter-176]` admits its window only through `ohlc-rolling`.

## D6 — the grid and the bar's instrument (the owner's)

**The owner's pick, 2026-11-24 (by 20:14:37Z), verbatim:** "Daily, record 34's bar (Recommended)". The option marked Recommended below is taken.
Spec 00164 D12 fixes the test — `a1_kill_bar` and a head-to-head against the sleeve — and not the grid its returns are counted on.

1. **The daily union, the bar record 34's** — **Recommended**.
   - **The returns**: `_asset_returns(_ffill_btc(daily_prices)[a])` for each of the ten assets, 4,581 of them, 365 periods a year.
   - **The benchmark**: `build_combined_system(daily_prices, config=_RECORD33_CONFIG).benchmark_net_of_cost` on the raw union closes — record 33's frozen daily benchmark at 0.006 a side, 4,581 returns (measured), the series record 34's bar read.
   - **The bar's constants are record 34's call, never tuned here**: `decisive_start` 230 (the master plan's "k ≥ 230 under B3+vt-dynamic"), `mean_block` 17, `seed` 42, `n_resamples` 2000; the slices `calendar_year_slices(…, daily_ts)`, each return in the year of its close, the stub years 2013 and 2026 out. The SPA grid is blocks {17, 102} × seeds {42, 7, 1234}, the headline cell (17, 42), the five others recorded and never read — 102 being reading 10's block, which keeps one hold's span together with probability 0.943 where 17 keeps it with 0.695 (measured).
   - **Why**: every input of the rule is daily — the sleeve decides on daily closes, the feature is one value a UTC day, the cell's forwards ran over daily closes — and the record's block stays reading 10's own, holding no file reading 10 did not read. It is the bar record 34, the sleeve's own trial, was admitted under.
   - **Cost**: a metrics function of the trial's own on the daily grid, since records 45–62's is 4h; the benchmark's stored anchor is four decimals, record 33's 1.2455, held within 0.005; and the headline block is the shorter of the two.
2. **The 4h union, the form records 44 and 47 hold the sleeve in and every B trial's bar**.
   - Both arms expanded by `expand_daily_positions` on close-time boundaries, as `crossfreq_system.py:342` expands the sleeve; `ohlc-full`'s ten 240-minute files join the block; the benchmark `benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`, `decisive_start` 1380, blocks {30, 102}, 2,190 periods a year, 27,337 returns (records 45–62's; spec 00149's basis).
   - **Gains**: the benchmark is anchored to the last digit by records 58–62 (`benchmark_ann_sharpe_noc` 1.2128451567638199 in record 62); arm A is the builder's `sleeve_positions["A1"]` itself; the bar's code is the B families'.
   - **Cost**: 22,756 returns more in which neither book decides anything, a second price grid no cell of reading 10 read, and a block that is no longer the reading's.

On either grid the DSR leg asks the same: an annualised net Sharpe above 0.4644 daily, 0.4656 at 4h (measured).

## D7 — the re-entry's size (the owner's)

**The owner's pick, 2026-11-24 (by 20:14:37Z), verbatim:** "All-long size, weekly (Recommended)". The option marked Recommended below is taken.
The sleeve is flat where the re-entry acts, so it holds no position to copy: the size is a choice, and it is made here on weights, scales and turnover alone.

1. **The all-long size at the sleeve's cadence** — **Recommended**.
   - **The size**: `full_long_positions(daily_prices)`, new — over `d_pf`, the feed `a1_daily_positions` builds (BTC forward-filled, the dummy close appended): `weights = _inverse_vol_weights(d_pf, lookback=30)`, `scale = vol_target(dynamic_inverse_vol_basket(d_pf, lookback=30), target_vol=0.12 / math.sqrt(365), lookback=30, max_leverage=1.0)`, `daily[a][k] = weights[k].get(a, 0.0) * scale[k]`, and `size[a][k] = statistics.mean(daily[a][_block_start(k, o)] for o in range(7))`.
   - **What it is**: the B sleeve's construction — basket, vol target, inverse-vol weights (`crossfreq_system.py:272-285`) — on the A sleeve's feed, at the A sleeve's 0.12 and its 30-return lookbacks (`A1Config`'s defaults), through the A sleeve's weekly 7-offset cadence: the position the sleeve's own constants give a book long in every weighted asset, so a re-entry takes what the sleeve would hold in the asset in a market it is long across, and never more. No value is chosen here.
   - **Measured**: above 0 at 1,520 of the 1,549 events, 0.019409 at the median and 0.028705 on average; arm B's largest gross is arm A's own 0.764856 and its mean where the books differ 0.157851; 23.113244304879004 of added turnover; the break-even 0.096962 % a re-entered close.
   - **The definition is the primitive's**: `dynamic_inverse_vol_basket` and `a1_book_returns`' own loop differ in the seventeenth decimal (measured), so the size names the first, and the basis's figures are its.
   - **Cost**: a size that is small where the events are — bear markets are volatile, and the all-long scale averages 0.150538 at an event close — so arm B's gross averages 0.157851 of NAV where the books differ.
2. **The sleeve's own vol-target scale** — spec 00139 D3's rule, transcribed: `weights[k] × a1_book_returns(…)["vol_target_positions"][k]` through the same cadence.
   - The one size that reads only what arm A already computes. **Measured, and why it is set aside**: the sleeve's scale is 0 at 237 of the 309 event closes and at its 1.0 cap at 23, so the size is 0 at 1,259 of the 1,549 events and up to 0.748722 in one asset at the rest — a re-entry absent through a long bear and at full leverage on its first day out of one, the vol target's artifact on a flat book (spec 00149's basis measured the same on the A2 ensemble's). Its first engagement is return index 335, its largest gross 1.0, its break-even 0.147159 % a close.
3. **The all-long size, daily** — option 1 without the cadence: `weights[k] × scale[k]` at each close.
   - No averaging function; the same 4,899 asset-closes and 367 entries. **Cost**: it trades the size's daily drift, 24.41083926495517 of added turnover against 23.113244304879004, a break-even of 0.102569 % against 0.096962 %, and sizes a weekly sleeve's re-entry on a clock the sleeve does not keep.

## D8 — the hold (the owner's)

**The owner's pick, 2026-11-24 (by 20:14:37Z), verbatim:** "Spec 00139's rule (Recommended)". The option marked Recommended below is taken.
The cell fixes 7 closes; what it leaves open is what the position does when events overlap and when the sleeve itself turns long inside a hold.

1. **`reentry_positions(arm_a, size, fires, hold=7)`, spec 00139 D3's rule, unchanged** — **Recommended**.
   - At return index `k`, for asset `a`: arm B's position is arm A's where arm A's is above 0; else the size where a re-entry is open and the size is above 0; else 0. A re-entry opens at an event, stays open through 7 closes counted from the last event close, that close included, and closes where the sleeve turns long. So an event at `k` holds the returns `k` … `k + 6`, the 7 closes the cell's forward ran over; events that overlap share one entry and one exit; and where the sleeve is long arm B is the sleeve — a re-entry never resizes a position the sleeve holds.
   - **Measured**: 4,899 re-entered asset-closes in 367 entries, 13.3 an entry; the sleeve is long at 106 of the 5,119 asset-closes inside an event's 7 closes.
   - **Why**: the function exists, is held to a known answer (`tests/test_alpha_b2.py`), and is the one records 55's and 56's replays read; no new code decides a position.
2. **Held through the sleeve's own entry** — while a re-entry is open the position is the larger of the sleeve's and the size, the 7 closes counted whether or not the sleeve turns long.
   - Closer to the forward the cell read, which ran its 7 closes whatever the sleeve then did. **Measured**: it differs from option 1 at 49 asset-closes and trades 69.21444271311105 against 69.84081467289158. **Cost**: a new function for a difference in the third digit of the turnover, and a re-entry that resizes a position the sleeve holds.

Under either option each entry and exit is a trade charged on the position's change (D9).

## D9 — the costing and §10's limits (settled by spec 00164 D12)

- **The costing** is spec 00164 D12's "net of 0.006 a side on its own turnover": `net_of_cost(positions, returns, cost_per_side=0.006)` (`cli/alpha/b2.py:725`) for both arms — each asset's own turnover from flat, a missing return read as 0.0 — and the kill bar's cost-stressed series at 1.5 ×, 0.009.
- **Long-only, nothing borrowed.** Arm A is `short="off"` and a size is never below 0, so no position of arm B is (measured: none), there is no carry, and T0016's borrow-unavailable rung, mandatory the moment a short exists, has nothing to read: no twin, where spec 00149 D6 carried one.
- **§10's whole-book limits are not wired**: arm B's largest gross is 0.7648558752122554 against the 1.5 cap, its net is its gross (measured) and, long-only on spot, it uses no margin, so none of the three can engage; record 34's bar wired none.
- **§10's per-asset caps are not wired**, as records 44 and 47 leave them on the sleeve: the builder applies `apply_position_caps` to the combined book, where the sleeve is a third. Measured and recorded: arm A holds a position above 0.20 at 224 closes, arm B at 238. An adopt's path runs through a combination trial over record 47's book (D16), where the caps bind.

## D10 — the contamination, stated in full

- **The cell was searched for on the data the trial reads.** Reading 10 read 32 cells — four features, two tails, two states, two horizons — over the whole history the A1 sleeve was designed and adopted on, and this trial reads that history again, block for block (measured). Its figures for the cell are known and quoted in the Intent; the pooled rows of the 21 other cells the reading's floor admits are in the decisions log's table, and every cell's rows are in the ledger line. Under D5's recommended option no return the verdict reads lies outside that search.
- **The trial carries the reading's id**: reading 10, `record_hash` `ed1bb73e76e3ab32bfc8cbd72212522f571e7d388a096871eb9b0949c05c590c`, spec 00164 at `89eb8be96d6961b2f4c6240b6b6ce7a8a045768413f0a6087a810fe64067c86e`; the record's notes name both (D15).
- **Nothing of the trigger is chosen here.** The band, its history, the lag and the horizon are reading 10's constants, fixed by spec 00164's hash before any forward was read.
- **The size and the hold are chosen after the reading, on positions.** Their options were laid out on weights, vol-target scales, counts and turnover (the basis); this spec computed no return of a book carrying the re-entry, none is in the registry, the ledger or the tree, and the break-even is turnover arithmetic.
- **The design-informed inputs spec 00164 D12 names stand**: BRK's prices before height 340,000 are exchange data baked into its code and its oracle after them is code written with the price history known; aSOPR's one-hour exclusion is a vendor convention set after seeing the data; the history's values are one run's, point-in-time in content under spec 00164 D3's premise and not in stamp. The first day, 2011-01-01, was the owner's pick after the cross-check's breach and before the reading's hash (`[iter-209]`).
- **The same treatment has been rejected twice on another book**: B2's two re-entries on the A2-4h ensemble, records 55 and 56, with other triggers. They are a prior the spec names, not evidence about this trigger.
- **The DSR counts C3's true trials**: `n_trials` 1 (D2); how the 32 looks enter the bar is D11.
- **The holdout is untouched** under D5's recommended option: `ohlc-full` ends 2026-03-31, and neither `ohlc-rolling` nor `ohlc-holdout-*` is read.

## D11 — how the reading's 32 looks enter the bar (the owner's)

**The owner's pick, 2026-11-24 (by 20:15:32Z), verbatim:** "n_trials 1, looks stated (Recommended)". The option marked Recommended below is taken.
Spec 00164 D12 says a trial the reading names "counts C3's true trials in its DSR with these 32 looks in its design". At `var_trials` 0.0, which `[iter-176]` binds, the count moves no number — the expected maximum Sharpe is 0.0 at any count (measured) — so the sentence can be met in two ways.

1. **`n_trials` 1, `var_trials` 0.0, the bar's legs as ratified; the 32 looks stated, in D10 and in the record's notes** — **Recommended**.
   - **Why**: the reading has already paid for its 32 — the cell cleared far bounds set at the Bonferroni percentiles for 32 cells — and the trial tests a second statistic on the same data; a second Bonferroni counts the one search twice and still buys no independence, which only an unread day supplies (D5, D16). It is the sentence as written: the true count in the DSR, the looks in the design.
   - **Cost**: no number of the bar is harder for the search; the notes and D10 carry it.
2. **The head-to-head's adopt threshold at 0.05 / 32** — adopt needs SPA p < 0.0015625 where the matrix reads 0.05, a park between the two; the head-to-head's `n_resamples` raised to 10,000, where 15.625 draws lie beyond the threshold against 3.125 at 2,000 (measured).
   - The strictest reading. **Cost**: a threshold no other record of this registry was read at, on a p-value whose resolution at 10,000 draws is 0.0001.

Not offered: a declared count of 33, which spec 00133 D4 admits and which would change `n_trials_in_family` and no number of the bar; and a `var_trials` from the 32 cells' dispersion, which would take the net return of 32 rules — 32 more looks — to compute.

## D12 — the bar and the head-to-heads (settled by spec 00164 D12; the constants D6's)

- **The series**: `net_a`, `net_b` at 0.006 and `net_b_x15` at 0.009 (D9); `bench` D6's benchmark.
- **The bar**, at D6's recommended option: `a1_kill_bar(net_b, bench, n_trials=1, var_trials=0.0, mean_block=17, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, daily_ts), benchmark_slices=calendar_year_slices(bench, daily_ts), decisive_start=230, n_resamples=2000)`, the grid's other five cells recorded beside it. **Arm A's headline bar** is the same call on `net_a` and its own 0.009 series at (17, 42), read `passes` 1 at the pre-flight, after the hash (D15).
- **`var_trials` 0.0** is the B families' convention and the value `[iter-176]` names; at count 1 the DSR leg is the PSR against 0 whatever it is (measured).
- **The head-to-heads**: `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=17, seed=42, n_resamples=2000)`, primary from arm B's first engagement — `first` = `reentry_first_engaged`, the first return index at which arm B's positions differ from arm A's, 97, `primary_returns` 4484 (measured) — and over the full window (`first` 0) beside it; keyed `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_full` and `head_to_head_spa_p_full`. Before the first engagement the two books are one to the bit (measured), so the full-window read adds 97 zero differences to the primary's; the primary decides.
- **The drawdown pair**, from the same start: `max_drawdown(net_b[first:])`, `max_drawdown(net_a[first:])` and `max_drawdown_reduction_pct = 100 × (A − B) / A`, spec 00138 D8's pair; a negative reduction is arm B's drawdown above arm A's.
- **Refused before any bar**: fewer than 2 return indices from the first engagement, and an arm A that never draws down from it — each a `ValidationError`, and so a refused build.

## D13 — the matrix and its drawdown bound (the owner's)

**The owner's pick, 2026-11-24 (by 20:15:32Z), verbatim:** "Max DD ≤ 1.2× arm A (Recommended)". The option marked Recommended below is taken.
The rows are spec 00149 D8's, the dead knob read off the re-entry's own engagement; what is open is whether an adopt also answers for the drawdown the re-entry adds.

1. **Spec 00139 D5's bound: an adopt needs arm B's maximum drawdown from the head-to-head's start at most 1.2 × arm A's** — **Recommended**.
   - **Why**: the hypothesis is return, and the re-entry earns it by adding exposure where the sleeve holds none — 1,496 of its 1,549 events with BTC at or below its 200-day SMA (measured). The bound keeps an adopt from being return bought with the drawdown the gate exists to avoid, and it is the leg the registry's two re-entries were read under (`_b2_reentry_verdict`).
   - **Cost**: a fifth is spec 00139's figure, set there for another book; a re-entry that beats the sleeve and breaches it parks.
2. **No drawdown leg** — spec 00149 D8's form: the drawdown pair recorded and never read.
   - The matrix reads the hypothesis and nothing else. **Cost**: an adopt whose drawdown no row has looked at, on the one action that adds risk in a bear.

**The matrix**, at option 1 — rows disjoint and covering every outcome:

| Arm A's bar and the re-entry's engagement | Kill bar (B vs the frozen benchmark) | Head-to-head (B vs A, from arm B's first engagement) | Verdict |
| --- | --- | --- | --- |
| arm A's `passes` 0, or no asset-close re-entered (a dead knob) | any | any | **instrument finding**: no verdict, the slot unspent |
| arm A passes, the re-entry engaged | fail | any | **reject** |
| arm A passes, the re-entry engaged | pass | mean outperformance > 0, SPA p < 0.05, and B's maximum drawdown at most 1.2 × A's | **adopt** the re-entry |
| arm A passes, the re-entry engaged | pass | mean outperformance > 0, and SPA p ≥ 0.05 or B's maximum drawdown above 1.2 × A's | **park** |
| arm A passes, the re-entry engaged | pass | mean outperformance ≤ 0 | **reject** |

Every quantity the matrix reads is a stored key read unrounded: `arm_a_passes`, `reentered_per_year`, `passes`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary` and `max_drawdown_reduction_pct`. The park row names no variant: what follows a verdict is D16's. The subject declares the rule (spec 00129 D4), `_b2_reentry_verdict`'s form with the re-entry's own dead-knob read:

```python
def _c3_asopr_reentry_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["reentered_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        bounded = m["max_drawdown_reduction_pct"] >= -20.0
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 and bounded else "park"
    return "reject"
```

At option 2 the rule loses `bounded`; at D11's option 2 its `0.05` is `0.05 / 32`.

## D14 — the engagement, the subjects, their record and the build

- **The engagement**, eleven keys from positions, events and sizes alone: `reentry_first_engaged`, `primary_returns`, `stamps_positions_differ`, `positions_differ_per_year`, `events_per_year` (the cell's events per close year), `reentered_per_year` (asset-closes flat in arm A and long in arm B — the dead-knob read), `reentry_entries`, `events_without_size`, `turnover_b`, `turnover_b_per_year` and `gross_max`. Every year key is the close year, `daily_ts[k + 1].year`, the rule `calendar_year_slices` cuts the bar's slices by.
- **The trial's 47 keys**: the bar's and the series' 33 — `_B3_METRIC_KEYS` less `_B3_ENGAGEMENT_KEYS` (`cli/research/subjects.py`), on the daily grid: `per_period_sharpe` for its `per_period_sharpe_4h` and the six `spa_p_decisive_b{17,102}_s{42,7,1234}` for its grid — the drawdown pair's three (`max_drawdown_primary`, `arm_a_max_drawdown_primary`, `max_drawdown_reduction_pct`) and the engagement's eleven. **The pre-flight's 28**: the engagement's eleven, arm A's and the benchmark's seven anchors (`arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`) and arm A's bar's ten (`_B2_ARM_A_BAR_KEYS`).
- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00165-c3-trial-1-asopr-reentry-design.md"`, intervals `(1440,)`, assets `()` as `c3-onchain-reading` declares them: the trial `c3-asopr-reentry` — `_build_c3_asopr_reentry`, `metric_keys=_C3_REENTRY_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_c3_asopr_reentry_verdict`, `no_verdict` "instrument finding: arm A fails the bar this window sets, or the re-entry holds no asset at any close; no verdict, the trial unspent", `family="C3"`, `n_trials=_C3_ASOPR_REENTRY_N_TRIALS` — and its evaluate-only twin `c3-asopr-reentry-preflight` — `_build_c3_asopr_reentry_preflight`, `metric_keys=_C3_REENTRY_PREFLIGHT_KEYS`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). The twin costs arm A alone and reads no head-to-head; it builds arm B's positions, and its engagement reads them.
- **Author's call — the names**: spec 00141 D2's rule holds for both (measured), and the `c3` prefix keeps the family's subjects together.
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `C3`; `n_trials_in_family` 1; variant `C3-asopr-reentry-a1lf-full-v1` (**Author's call**: records 60–62's form, `<family>-<name>-<arm A>-full-v1`); iteration `iter-210`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a`; `attempt` the trial-attempts log's; `notes` caller text written before the run (D15).
- **The build in three halves**, spec 00144 D9's form: `_c3_reads`, unchanged — the snapshot, its refusals and the daily union, no compute; `_c3_reentry_inputs(snapshot, daily_ts, daily_prices)` — `_c3_reading_inputs` unchanged, then the events, the size, arm B and the returns both arms are costed on, and no net series of a book; `_c3_reentry_metrics` — the nets, the benchmark, the bars, the head-to-heads and the keys — and `_c3_reentry_preflight_metrics` — arm A's net, the benchmark, arm A's bar and the engagement. The plan's data-gated case runs the first two over the real sets, and its fixture tests run the books on a planted snapshot and union.
- **The refusals**, each a `SubjectError` naming the subject or the file: `--as-of` and `--window`, before any read, in `c3-onchain-reading`'s words for its own; `_c3_reads`' own — an unreadable file or manifest, a snapshot whose days are not consecutive from its first priced day or whose provenance lacks the as-of line's sha256; D12's two; and any compute error (`EVALUATION_ERRORS`).
- **`cli/alpha/c3_reentry.py`, new** — `SLEEVE`, records 44's and 47's `A1Config`, off which the size reads D7's target and lookbacks; `reentry_fires(band, states)`, the cell's flag as booleans per asset; and `full_long_positions(daily_prices)`, D7's size, which refuses an asset order other than the builder's, as `a1_daily_positions` does. The plan's tests hold it to known answers: a flag set only at a flat close under a low band, none at a `None` state; no close's size reading a later close; the size 0 where the basket does not weight the asset; the cadence's mean over the seven block starts; the size equal to the sleeve's own position on a planted book long in every asset through its windows.
- **The files the build touches, a closed list**: `cli/alpha/c3_reentry.py`, new; `cli/registry/budget.py` — the key; `cli/research/subjects.py` — the import, one block before `SUBJECTS` (the constants, `_C3ReentryInputs`, the inputs half, the computes and their helpers, the shared build, the two builders, the rule and the key sets) and two `SUBJECTS` entries, no existing function changed; `README.md`'s `--subject` row; `tests/test_trial_registry_provenance.py` — the `BUCKET_OF` literal and, after the run, the `LANDED_N_TRIALS` row; `tests/test_research_command.py` — the subjects' contract fixtures; `tests/slow-cases.txt` — the ids of the new cases that take 10 s or more; the new tests the plan names. No change to `cli/alpha/a1.py`, `cli/alpha/b2.py`, `cli/alpha/c3.py`, `cli/alpha/killbar.py`, `cli/portfolio/*`, `cli/onchain/*`, `cli/features/*`, `cli/risk/*`, `cli/costs/*`, `cli/engine/*`, the reading's subject, spec 00164, any record, reading or adopted artifact, `zcrypto.toml` (the snapshot is in `authored_sets`), or anything under `infra/`.

## D15 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the owner's picks quoted at D5, D6, D7, D8, D11, D13 and D16; the plan review closed; the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important; nothing this spec pins changed since.
- **The steps**, in order:
  1. The spec hash, `sha256sum docs/specs/00165-c3-trial-1-asopr-reentry-design.md`; this file is never edited after it.
  2. The develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append.
  3. The data-gated basis case on the run's tree, with the subjects' two fixture rows, reading 10's own basis case, which holds its `arm`, `counts` and `features` to the inputs half the trial's own inputs call, reading 10's replay, which rebuilds its figures through that half and the reads, and `tests/test_portfolio_builder.py::test_frozen_figures_regression`, which holds the daily benchmark to record 33's figure. Records 55's and 56's replays, which rebuild B2's re-entries through `reentry_positions` and `net_of_cost`, read `liquidations-daily` and `derivatives-funding`, two sets this branch does not link: they run nightly, and here the branch's diff over `cli/alpha/b2.py`, which prints nothing, holds the two functions unchanged.
  4. The twin's plain eval, `uv run zcrypto research eval --subject c3-asopr-reentry-preflight --dataset btc-onchain-20261124T162656Z`, read in this order — (a) the block, `19ee5c23…74f7a`, both sets `checked`; (b) the events, `events_per_year` summing to 1,549, reading 10's count; (c) the dead knob, a non-zero count in `reentered_per_year`, read before the engagement so that a dead knob is named as such; (d) the engagement equal to the measured basis, the plan's data-gated literals; (e) the benchmark, `benchmark_ann_sharpe_noc` within 0.005 of 1.2455, record 33's `benchmark_sharpe_full` at its regression's tolerance; (f) arm A's `passes` 1 — a failure of (a)–(f) an instrument finding, the run kept as a reading under iter-210 (`--reading --iteration iter-210 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent.
  5. On a pass, the trial's one run: `uv run zcrypto research eval --subject c3-asopr-reentry --dataset btc-onchain-20261124T162656Z --register --iteration iter-210 --family C3 --n-trials 1 --variant C3-asopr-reentry-a1lf-full-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10).
  6. The record's checks and its commit — the registry line, the decisions-log verdict entry `[iter-210] Verdict — C3 trial 1 <ADOPT, PARK or REJECT> (registry trial <N>, family C3 n=1)` and the `LANDED_N_TRIALS` row together, since the tie tests hold only over the three. A check that fails after the record lands stops there: the record stays in place uncommitted, and the owner reads the failing output first.
- **The hash rule**: before (1), nobody reads or computes arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — by code, a program or arithmetic over a stored figure — nor runs `c3-asopr-reentry` or its twin over the real sets; and nobody recomputes, extends or conditions further any forward of reading 10 — a horizon, a tail, a state or an asset subset its line does not hold. Weights, scales, bands, states, events, sizes, positions, exposures and turnover are allowed, and are what the measured basis and the data-gated case hold. `a1_book_returns`, `dynamic_inverse_vol_basket` and `build_combined_system` compute a book's base returns on every call that sizes it; no program reads them. Reading 10's replay, run after the hash, rebuilds that reading's stored figures and no other, and record 33's regression the benchmark's; neither reads a book carrying this re-entry.
- **The notes, written before the run** (spec 00137 D10's): the subject over the snapshot with `ohlc-full` beside it, both whole; arm A and arm B, the trigger and its constants, the size, the hold and the costing; the hypothesis; the count 1 and `var_trials` 0.0; the read from arm B's first engagement deciding, the full-window read and the drawdown pair beside it; the contamination D10 states, naming reading 10, its 32 cells and its `record_hash`; the pre-flight's figures, quoted — arm A's anchors and its bar's `dsr` and SPA p; the park row naming no variant; the matrix pre-registered by this spec's sha256.
- **A refusal from the count, a refused build, a stop by the rule under `--register`**: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0228's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D16 — what a verdict changes (the owner's)

**The owner's pick, 2026-11-24 (by 20:15:32Z), verbatim:** "Recorded; next step yours (Recommended)". The option marked Recommended below is taken.
The owner's pick names this trial and nothing after it; the master plan ties the first paid data dollar to C3 — "Glassnode … if C3 survives its kill bar" (`00.master-plan.md:241`) — while T0016's next step and the `[iter-210]` entry let the Glassnode step, `_pit` diff first, stand beside the trial on reading 10's cell alone. This spec changes neither text; it has to say what its own verdict does.

1. **The verdict is recorded and C3's next step is the owner's pick** — **Recommended**.
   - **Adopt** is recorded, never deployed. The re-entry buys spot in ten pairs the engine's book already trades, on a daily on-chain value the engine does not read, so the live form is a change to the adopted book's A1 sleeve and a new engine input, both the owner's. In order: a read of the days no forward has read — the snapshot's days after 2026-03-30 and every day the chain has added since, over `ohlc-rolling`, under its own spec and a criterion fixed before it, the spent holdout's window inside it never reported as out-of-sample (`[iter-176]`), and under D5's option 2 only the days after that trial's as-of; then a P1 combination trial over record 47's book with the re-entry in its A1 sleeve, outside every bucket's budget, where §10's per-asset caps bind; then T0123's promotion path. T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts.
   - **Park** and **reject** record the verdict in the record and the decisions log; a reject archives the hypothesis.
   - **After a verdict, whatever it is**, C3's next step — a further trial from bucket C's 9, the Glassnode step, LTC and DOGE, or the family's close — is asked of the owner and entered as `[iter-<N>] C3's next step after trial 1`. T0228's and T0016's `ripe_when`, which the `[iter-210]` entry fired, are rewritten in this branch to watch for that entry; T0228's findings and next steps and T0016's budget line (C spent 1, 9 remain) gain the verdict; both subjects stay registered; nothing closes.
   - **No verdict** — a pre-flight stop, the rule's stop under `--register`, a refused build or a refusal from the count — spends no trial; T0228 records what failed, and whether the trial runs again once its cause is fixed is the owner's.
   - **Why**: no word of the owner's sequences C3 past this trial, the family holds 9 untried slots, and a cell's reject is no verdict on on-chain bands at large.
2. **The verdict sequences the family in this branch** — the master plan's sentence taken as the rule.
   - A **reject** closes C3 here, on spec 00146 D11's form: both subjects retired, T0016's findings and next steps rewritten for C3's close, T0228 resolved with nothing bought, LTC and DOGE not started. An **adopt** or a **park** — a pass of the kill bar — opens the Glassnode step.
   - **Cost**: it commits the owner's family call and a data purchase's gate before the result is known, on one cell of 32.

## Closed-world claims and the enumerations that hold them

- **"No C3 trial or attempt exists."** Held by three enumerations in the count program: every registry record's family (six keys, none a C family's), every reading's `attempt` (none), and every registered subject's declared family (none a C family's) — an attempt's family is its subject's, and `cli/research/command.py:320` refuses a `--register` whose family is no key of `BUCKET_OF`. The plan's count program reads the log's own answer.
- **"The family key is read at these sites and no other."** Held by `git grep -n 'BUCKET_OF' -- cli`: `cli/registry/budget.py:6` and six lines of `cli/research/command.py`; under `tests/`, two files (the basis).
- **"The trial reads the sets reading 10 read and no other."** Held by the reader's block, compared with the ledger line's `datasets` (measured equal), and re-read at the pre-flight's (a).
- **"No holdout path is read."** Held by `ls data` in this worktree — two names, neither a holdout's — and by the block.
- **"Arm B is never short and borrows nothing."** Held by a case of the plan's on the fixture and by the data-gated case's count of positions below 0 (measured: none).
- **"The inputs half computes no return of a book."** Held by `_C3ReentryInputs`' field list, pinned by a case (spec 00150's form), beside the case that holds `_c3_reading_inputs` free of a forward.
- **"No existing function changes."** Held by D14's closed file list, by the branch's diff over `cli/` — one added module, the key's line and three pure insertions in `cli/research/subjects.py` — and by reading 10's replay and record 33's regression at the run; records 55's and 56's replays, which read `reentry_positions` and `net_of_cost`, run nightly.

## Tests and guards

The plan reviews at tier `full` (measured); each guard is proven with `infra/scripts/mutate-probe.sh` through its own case.

| Decision | Guard | Where |
| --- | --- | --- |
| D2 | the `BUCKET_OF` literal with `C3` in bucket C; every ruled subject's family a key of it | `tests/test_trial_registry_provenance.py`, `tests/test_research_command.py` |
| D3 | a flag only at a flat close under a low band; none at a `None` state; the events equal to the cell's `flags` | `tests/test_alpha_c3_reentry.py` |
| D7 | the size on a known answer; no later close read; 0 where the basket does not weight the asset; the seven block starts' mean; the builder's asset order | `tests/test_alpha_c3_reentry.py` |
| D8 | `reentry_positions` called with the size, the events and `hold=7` | `tests/test_research_c3_asopr_reentry.py` |
| D9 | both arms costed at 0.006 on their own turnover, the stressed series at 0.009; no position below 0 | `tests/test_research_c3_asopr_reentry.py` |
| D12, D13 | every `a1_kill_bar` call at `n_trials` 1 and `var_trials` 0.0, arm A's among them; the head-to-head from the first engagement; the two refusals; the rule's five rows | `tests/test_research_c3_asopr_reentry.py` |
| D14 | the keys exact and their leaves builtin; the inputs half's fields; the twin ruleless and reading no return of arm B; `--as-of` and `--window` refused before any read | `tests/test_research_c3_asopr_reentry.py`, `tests/test_research_command.py` |
| D3–D8 | the engagement over the real sets equal to the measured basis's literals, on reading 10's block; the events per asset reading 10's counts for the cell; reading 10's `arm` and `counts` by its own basis case | `tests/test_research_c3_asopr_reentry_basis.py`, `tests/test_research_c3_onchain_reading_basis.py` |

## Out of scope

- Every other cell of reading 10 — the 30-close sibling, the high tail, the long state, MVRV, MVRV-Z and the STH supply share — and any further forward read of them.
- Every other knob of this cell's rule: another percentile, history length, lag or first day; another horizon; another size or a fraction of one; a per-asset cap on the sleeve; a re-entry gated on BTC's own SMA; a short.
- A second C3 trial, a no-slot reading, and the read of the unseen days (D16).
- `ohlc-rolling`, a later snapshot and the 4h grid, unless the owner picks D5's option 2 or D6's option 2; `ohlc-holdout-*` under every option.
- The combination trial over record 47's book, the engine's on-chain input and anything on the live path (D16).
- LTC and DOGE, the Glassnode step and any purchase (T0228's, T0016's).
- Any change to the chain, the writer, the node, the ops role or a host; any change to an existing function, subject, record, reading or spec.

## The owner's picks

Each open decision's option marked Recommended, the owner's picks of 2026-11-24 quoted at D5, D6, D7, D8, D11, D13 and D16, and in the phase-4 decisions log's `[iter-210]` entries.
