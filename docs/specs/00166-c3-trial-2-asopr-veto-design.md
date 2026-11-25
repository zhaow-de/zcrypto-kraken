# C3 trial 2 — aSOPR's low tail as a veto on the A1 sleeve's long state, the gate's one action trial 1 left unread; the days after that history hold no event of it

Iteration `iter-211`, branch `feat/iter-211-c3-trial-2`, cut from `develop` at `1a4abc4f5` (the merge of #895); bucket C family C3 (`docs/research/00.master-plan.md` §5), topics [T0228](../open-topics/T0228-btc-on-chain-metrics-computed-from-chain-data.md) and [T0016](../open-topics/T0016-bucket-b-c-alpha-families.md).
**Ruled: D1's option 4, no trial** — the owner's pick after `[iter-211] C3's next step after trial 1`, quoted at D1's head: no trial registers under this spec and its sha256 is never taken. The measured basis is what the decision rests on, the hypothesis what D1's option 1 would have tested, and C3's next step the owner's second pick under `## The owner's picks`; the design past D1, for option 1, stands at `ed09c0fed`.

## Intent

Trial 1 turned the one cell reading 10 found with potential into a book and registry trial 65 rejected it — the `[iter-210] Verdict — C3 trial 1 REJECT (registry trial 65, family C3 n=1)` entry, which also says where that reject lies: inside reading 10's own search, every return of it on the history the sleeve was designed and adopted on.
**The days after that history cannot carry a trial.** `ohlc-rolling` as this workstation holds it adds 210 daily returns past `ohlc-full`'s last close, 100 of them inside the spent holdout's window; over them MVRV and MVRV-Z never leave their middle band, the STH supply share sits in its low band nine days in ten, aSOPR is in its low band on 11 days, all with the sleeve flat, and the ratified bar cannot be called on a span that lies wholly in 2026, a stub year its worst-slice leg drops (the measured basis).
**So the trial this spec recommended was a second in-sample one, and it said so**: the gate's other action on the same band — a veto where the sleeve is long — on `asopr|low|long|H7`, the one long-state cell of reading 10 that holds its legs 2, 3 and 4 and misses leg 1; and D1 laid beside it the same veto on a later rolling head, trial 1's rule on the days after alone, and no trial at all.

## The measured basis

Every figure below was measured in this branch's worktree at `2b6ad261d`, with `data/btc-onchain-20261124T162656Z`, `data/ohlc-full` and `data/ohlc-rolling` symlinked from the main checkout's `data/`, read and never written; `data/` in this worktree holds those three names and no other, and no `ohlc-holdout-*` path is read, listed or opened by any program or check below.
The programs read closes, weights, positions, bands, states, counts, exposure and turnover only: **no forward return, no net-of-cost series, no Sharpe and no statistic of any candidate rule's outcome is computed, on any span** — of the veto, of trial 1's rule on the days after, or of arm A over any subset of closes.
`a1_daily_positions` and `full_long_positions` compute a book's base returns on their way to its positions, since the vol target sizes on them, and `_c3_reentry_inputs` builds each asset's close-to-close returns for the costing it does not run here; the programs keep positions and read nothing else of them.
Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

**The rolling set and the days after the history**, a first program:

```python
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.data import rolling
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

print("start", datetime.now(UTC).isoformat(timespec="seconds"))
root = Path("data/ohlc-rolling")
days = rolling.line_days(root)
head = rolling.head(root)
print("ohlc-rolling: lines", len(days), days[0], "->", days[-1], "; head", head.day, head.relpath, head.sha256)
print("pairs", rolling.pairs(root))
chain = rolling.walk_chain(root, head.day)
print("holes on any line to the head:", {line.day.isoformat(): line.holes for line in chain if line.holes})
t0 = time.perf_counter()
verified = rolling.verify(root, head.day)
print(f"verify to the head: line {verified.relpath} {verified.sha256}, {time.perf_counter() - t0:.1f} s")

AS_OF = head.day.isoformat()
rolled = ObservedReader(Path("data"))
t0 = time.perf_counter()
r_ts, r_prices = subjects._capturing_union(rolled, "ohlc-rolling", 1440, None, AS_OF, False)
print(f"the rolling daily union as of {AS_OF}: {len(r_ts)} stamps, {r_ts[0]} -> {r_ts[-1]}, {time.perf_counter() - t0:.1f} s; assets {list(r_prices)}")
frozen = ObservedReader(Path("data"))
f_ts, f_prices = subjects._capturing_union(frozen, "ohlc-full", 1440, None, None, False)
print(f"ohlc-full's daily union: {len(f_ts)} stamps, {f_ts[0]} -> {f_ts[-1]}")
shared = len(f_ts)
print("the shared stamps are one list:", r_ts[:shared] == f_ts, "; the asset order is one:", list(r_prices) == list(f_prices))
for asset in f_prices:
    a, b = f_prices[asset], r_prices[asset][:shared]
    differ = [k for k in range(shared) if a[k] != b[k]]
    print(f"  {asset}: closes differing over the {shared} shared stamps {len(differ)}", "; first", (f_ts[differ[0]].date().isoformat(), a[differ[0]], b[differ[0]]) if differ else None, "; None in the rolling set past them", sum(v is None for v in r_prices[asset][shared:]))
print("stamps past ohlc-full's last:", len(r_ts) - shared, r_ts[shared], "->", r_ts[-1], "; consecutive days:", all((y - x).days == 1 for x, y in zip(r_ts[shared - 1:], r_ts[shared:])))
print("rolling block", compute_hash(rolled.block()), {d: (e["files"], e["rows"], e["span"]) for d, e in rolled.block().items()})
print("rolling vouched", rolled.vouched_status(), "holes", rolled.holes())

both = ObservedReader(Path("data"))
snap = both.read_series("btc-onchain-20261124T162656Z", "BTC/onchain.parquet")
subjects._capturing_union(both, "ohlc-rolling", 1440, None, AS_OF, False)
block = both.block()
print("one reader over the snapshot and the rolling set:", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in block.items()}, both.vouched_status())
print("snapshot", snap.height, snap["ts"][0], "->", snap["ts"][-1])
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-11-25T11:52:11+00:00
ohlc-rolling: lines 28 2026-09-30 -> 2026-10-27 ; head 2026-10-27 index/2026/10/27.json 89ab2d72cfffe52befa7fc767c522e945ebeb3b78bb0f379e25d72f419c812c4
pairs ('ADA/EUR', 'AVAX/EUR', 'BTC/EUR', 'DOGE/EUR', 'DOT/EUR', 'ETH/BTC', 'ETH/EUR', 'LINK/EUR', 'LTC/EUR', 'SOL/BTC', 'SOL/EUR', 'XRP/EUR')
holes on any line to the head: {}
verify to the head: line index/2026/10/27.json 89ab2d72cfffe52befa7fc767c522e945ebeb3b78bb0f379e25d72f419c812c4, 0.1 s
the rolling daily union as of 2026-10-27: 4792 stamps, 2013-09-10 00:00:00+00:00 -> 2026-10-27 00:00:00+00:00, 0.5 s; assets ['ADA', 'AVAX', 'BTC', 'DOGE', 'DOT', 'ETH', 'LINK', 'LTC', 'SOL', 'XRP']
ohlc-full's daily union: 4582 stamps, 2013-09-10 00:00:00+00:00 -> 2026-03-31 00:00:00+00:00
the shared stamps are one list: True ; the asset order is one: True
  ADA: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  AVAX: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  BTC: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  DOGE: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  DOT: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  ETH: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  LINK: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  LTC: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  SOL: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
  XRP: closes differing over the 4582 shared stamps 0 ; first None ; None in the rolling set past them 0
stamps past ohlc-full's last: 210 2026-04-01 00:00:00+00:00 -> 2026-10-27 00:00:00+00:00 ; consecutive days: True
rolling block a5322d4eb8deba2c2b84b3dccbd5189f95de0536ca14ee5b9d2c32c589e89db0 {'ohlc-rolling': ({'index/2026/10/27.json': '89ab2d72cfffe52befa7fc767c522e945ebeb3b78bb0f379e25d72f419c812c4'}, 31132, ['2013-09-10 00:00:00+00:00', '2026-10-27 00:00:00+00:00'])}
rolling vouched {'ohlc-rolling': 'chained (as of 2026-10-27, line 89ab2d72cfff)'} holes {}
one reader over the snapshot and the rolling set: 6af42a08a673569b19633bacfd68c5912927d293dfa03f47af925d26e6021602 {'btc-onchain-20261124T162656Z': (1, 6529, ['2009-01-03 00:00:00+00:00', '2026-11-23 00:00:00+00:00']), 'ohlc-rolling': (1, 31132, ['2013-09-10 00:00:00+00:00', '2026-10-27 00:00:00+00:00'])} {'btc-onchain-20261124T162656Z': 'checked (1 vouched hashes)', 'ohlc-rolling': 'chained (as of 2026-10-27, line 89ab2d72cfff)'}
snapshot 6529 2009-01-03 00:00:00+00:00 -> 2026-11-23 00:00:00+00:00
end 2026-11-25T11:52:12+00:00
```

**Bands, states and events over the days after**, a second program — the inputs by reading 10's own `_c3_reading_inputs`, over the frozen union and over the rolling one:

```python
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cli.alpha import c3 as alpha_c3
from cli.benchmark.strategies import sma_gate
from cli.onchain.series import mvrv_z, priced
from cli.portfolio.crossfreq_system import _dummy_close, _ffill_btc
from cli.registry.observed import ObservedReader
from cli.research import subjects

DATASET = "btc-onchain-20261124T162656Z"
AS_OF = "2026-10-27"
print("start", datetime.now(UTC).isoformat(timespec="seconds"))
line = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
print("the ledger's last line: reading", line["reading_id"], line["iteration"], line["invocation"]["subject"])
metrics = line["metrics"]

frozen = ObservedReader(Path("data"))
_, snapshot, f_ts, f_prices = subjects._c3_reads(frozen, DATASET, "c3-onchain-reading")
f_in = subjects._c3_reading_inputs(snapshot, f_ts, f_prices)
print("the frozen inputs half against reading 10's line: arm", f_in.arm == metrics["arm"], "; counts", f_in.counts == metrics["counts"])

rolled = ObservedReader(Path("data"))
r_ts, r_prices = subjects._capturing_union(rolled, "ohlc-rolling", 1440, None, AS_OF, False)
r_in = subjects._c3_reading_inputs(snapshot, r_ts, r_prices)
shared = len(f_ts)  # 4582 rows; the frozen set's last, 4581, is its forming row
n = len(r_ts) - 1
print(f"rolling as of {AS_OF}: {len(r_ts)} stamps, completed returns {n}; ohlc-full: {shared} stamps, completed returns {shared - 1}")
assets = list(r_in.positions)
print("positions over the frozen set's completed returns, rows 0 ..", shared - 2, "equal to the bit:", all(r_in.positions[a][: shared - 1] == f_in.positions[a][: shared - 1] for a in assets), "; states:", all(r_in.states[a][: shared - 1] == f_in.states[a][: shared - 1] for a in assets))
print("  at the frozen set's forming row", shared - 1, ": positions equal", {a: r_in.positions[a][shared - 1] == f_in.positions[a][shared - 1] for a in assets})
print("bands over the shared rows equal:", {f: r_in.bands[f][:shared] == f_in.bands[f] for f in alpha_c3.FEATURES})

first_new = shared - 1  # return index 4581, the first no record or reading has read
HOLDOUT_LAST = date(2026, 7, 9)
new = range(first_new, n)
in_window = [k for k in new if r_ts[k + 1].date() <= HOLDOUT_LAST]
after = [k for k in new if r_ts[k + 1].date() > HOLDOUT_LAST]
print(f"return indices no record has read: {len(new)}, {first_new} .. {n - 1}, closes {r_ts[first_new + 1].date()} -> {r_ts[n].date()}; closing inside the spent holdout's window {len(in_window)}; after it {len(after)}, closes {r_ts[after[0] + 1].date()} -> {r_ts[after[-1] + 1].date()}")
print(f"  their decisions read the snapshot's days {r_ts[first_new].date()} minus one .. {r_ts[n - 1].date()} minus one; the snapshot's last day {snapshot['ts'][-1].date()}")

print("the sleeve over those", len(new), "return indices:")
print("  asset-closes long per asset", {a: sum(r_in.states[a][k] == "long" for k in new) for a in assets})
any_long = [k for k in new if any(r_in.states[a][k] == "long" for a in assets)]
print("  closes with any asset long", len(any_long), "; inside the window", sum(k in set(in_window) for k in any_long), "; after it", sum(k in set(after) for k in any_long), "; first and last", (r_ts[any_long[0]].date(), r_ts[any_long[-1]].date()) if any_long else None)
d_pf = _ffill_btc({a: list(c) + [_dummy_close(c)] for a, c in r_prices.items()})
gate = sma_gate(d_pf["BTC"], window=200)
print("  BTC above its 200-day SMA at", sum(gate[k] != 0.0 for k in new), "of them; inside the window", sum(gate[k] != 0.0 for k in in_window), "; after it", sum(gate[k] != 0.0 for k in after))
by_month = {}
for k in new:
    m = r_ts[k].strftime("%Y-%m")
    row = by_month.setdefault(m, {"rows": 0, "gate_open": 0, "asset_closes_long": 0})
    row["rows"] += 1
    row["gate_open"] += gate[k] != 0.0
    row["asset_closes_long"] += sum(r_in.states[a][k] == "long" for a in assets)
print("  by decision month", by_month)

print("band days the new return indices read, per feature (lagged one day), low / mid / high / unread:")
for f in alpha_c3.FEATURES:
    b = r_in.bands[f]
    print(f"  {f}: all {[sum(b[k] == x for k in new) for x in ('low', 'mid', 'high', None)]}; inside the window {[sum(b[k] == x for k in in_window) for x in ('low', 'mid', 'high', None)]}; after it {[sum(b[k] == x for k in after) for x in ('low', 'mid', 'high', None)]}")

print("the 16 feature|tail|state triples: events (asset-closes) and event closes, in sample (rows 0 .. 4580) and over the new return indices:")
for f in alpha_c3.FEATURES:
    for tail in alpha_c3.TAILS:
        for state in alpha_c3.STATES:
            flags = {a: alpha_c3.flags(r_in.bands[f], r_in.states[a], tail=tail, in_state=state) for a in assets}
            def count(rows):
                rows = list(rows)
                return sum(flags[a][k] is True for a in assets for k in rows), sum(any(flags[a][k] is True for a in assets) for k in rows)
            sample = count(range(first_new))
            ledger = sum(v["events"] for v in metrics["counts"][f"{f}|{tail}|{state}"].values())
            print(f"  {f}|{tail}|{state}: in sample {sample[0]} at {sample[1]} closes (reading 10's count over its 4582 rows {ledger}); new {count(new)}; inside the window {count(in_window)}; after it {count(after)}")

low_rows = [k for k in new if r_in.bands["asopr"][k] == "low"]
print("aSOPR's low-band days the new return indices read:", [(r_ts[k].date() - timedelta(days=1)).isoformat() for k in low_rows])

# The snapshot's days past the rolling head, which no return index of this head reads: the bands a later head would read.
days, price = [stamp.date() for stamp in snapshot["ts"].to_list()], snapshot["price"].to_list()
own_z = mvrv_z(alpha_c3.from_first_day(days, snapshot["market_cap"].to_list()), snapshot["realized_cap"].to_list())
first_unread = r_ts[n].date() - timedelta(days=1)
past = [i for i, day in enumerate(days) if day >= first_unread]
print(f"the snapshot's days from {first_unread}, which this head's forming row and no return index reads: {len(past)}, to {days[-1]}")
for f in alpha_c3.FEATURES:
    column = alpha_c3.from_first_day(days, own_z if f == "mvrv_z" else snapshot[f].to_list())
    if f in ("mvrv", "mvrv_z", "asopr"):
        column = [value if priced(p) else None for value, p in zip(column, price, strict=True)]
    band = alpha_c3.bands(column)
    by_day = dict(zip(days, band, strict=True))
    print(f"  {f}: its bands by day equal the grid's lagged ones over every row: {alpha_c3.lagged(by_day, r_ts) == r_in.bands[f]}; past the head low / mid / high {[sum(band[i] == x for i in past) for x in ('low', 'mid', 'high')]}")
    if f == "asopr":
        print("    its low days past the head", [days[i].isoformat() for i in past if band[i] == "low"])
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-11-25T11:52:13+00:00
the ledger's last line: reading 10 iter-209 c3-onchain-reading
the frozen inputs half against reading 10's line: arm True ; counts True
rolling as of 2026-10-27: 4792 stamps, completed returns 4791; ohlc-full: 4582 stamps, completed returns 4581
positions over the frozen set's completed returns, rows 0 .. 4580 equal to the bit: True ; states: True
  at the frozen set's forming row 4581 : positions equal {'ADA': True, 'AVAX': True, 'BTC': True, 'DOGE': True, 'DOT': True, 'ETH': True, 'LINK': True, 'LTC': True, 'SOL': True, 'XRP': True}
bands over the shared rows equal: {'mvrv': True, 'mvrv_z': True, 'asopr': True, 'sth_supply_share': True}
return indices no record has read: 210, 4581 .. 4790, closes 2026-04-01 -> 2026-10-27; closing inside the spent holdout's window 100; after it 110, closes 2026-07-10 -> 2026-10-27
  their decisions read the snapshot's days 2026-03-31 minus one .. 2026-10-26 minus one; the snapshot's last day 2026-11-23
the sleeve over those 210 return indices:
  asset-closes long per asset {'ADA': 67, 'AVAX': 67, 'BTC': 67, 'DOGE': 56, 'DOT': 65, 'ETH': 67, 'LINK': 67, 'LTC': 67, 'SOL': 67, 'XRP': 66}
  closes with any asset long 67 ; inside the window 0 ; after it 67 ; first and last (datetime.date(2026, 8, 21), datetime.date(2026, 10, 26))
  BTC above its 200-day SMA at 68 of them; inside the window 0 ; after it 68
  by decision month {'2026-03': {'rows': 1, 'gate_open': 0, 'asset_closes_long': 0}, '2026-04': {'rows': 30, 'gate_open': 0, 'asset_closes_long': 0}, '2026-05': {'rows': 31, 'gate_open': 0, 'asset_closes_long': 0}, '2026-06': {'rows': 30, 'gate_open': 0, 'asset_closes_long': 0}, '2026-07': {'rows': 31, 'gate_open': 0, 'asset_closes_long': 0}, '2026-08': {'rows': 31, 'gate_open': 12, 'asset_closes_long': 108}, '2026-09': {'rows': 30, 'gate_open': 30, 'asset_closes_long': 298}, '2026-10': {'rows': 26, 'gate_open': 26, 'asset_closes_long': 250}}
band days the new return indices read, per feature (lagged one day), low / mid / high / unread:
  mvrv: all [0, 210, 0, 0]; inside the window [0, 100, 0, 0]; after it [0, 110, 0, 0]
  mvrv_z: all [0, 210, 0, 0]; inside the window [0, 100, 0, 0]; after it [0, 110, 0, 0]
  asopr: all [11, 199, 0, 0]; inside the window [9, 91, 0, 0]; after it [2, 108, 0, 0]
  sth_supply_share: all [188, 22, 0, 0]; inside the window [78, 22, 0, 0]; after it [110, 0, 0, 0]
the 16 feature|tail|state triples: events (asset-closes) and event closes, in sample (rows 0 .. 4580) and over the new return indices:
  mvrv|low|long: in sample 4 at 2 closes (reading 10's count over its 4582 rows 4); new (0, 0); inside the window (0, 0); after it (0, 0)
  mvrv|low|flat: in sample 1355 at 279 closes (reading 10's count over its 4582 rows 1355); new (0, 0); inside the window (0, 0); after it (0, 0)
  mvrv|high|long: in sample 1055 at 177 closes (reading 10's count over its 4582 rows 1055); new (0, 0); inside the window (0, 0); after it (0, 0)
  mvrv|high|flat: in sample 98 at 71 closes (reading 10's count over its 4582 rows 98); new (0, 0); inside the window (0, 0); after it (0, 0)
  mvrv_z|low|long: in sample 30 at 15 closes (reading 10's count over its 4582 rows 30); new (0, 0); inside the window (0, 0); after it (0, 0)
  mvrv_z|low|flat: in sample 2263 at 450 closes (reading 10's count over its 4582 rows 2263); new (0, 0); inside the window (0, 0); after it (0, 0)
  mvrv_z|high|long: in sample 1858 at 374 closes (reading 10's count over its 4582 rows 1858); new (0, 0); inside the window (0, 0); after it (0, 0)
  mvrv_z|high|flat: in sample 183 at 145 closes (reading 10's count over its 4582 rows 183); new (0, 0); inside the window (0, 0); after it (0, 0)
  asopr|low|long: in sample 176 at 43 closes (reading 10's count over its 4582 rows 176); new (0, 0); inside the window (0, 0); after it (0, 0)
  asopr|low|flat: in sample 1549 at 309 closes (reading 10's count over its 4582 rows 1549); new (110, 11); inside the window (90, 9); after it (20, 2)
  asopr|high|long: in sample 1244 at 194 closes (reading 10's count over its 4582 rows 1244); new (0, 0); inside the window (0, 0); after it (0, 0)
  asopr|high|flat: in sample 244 at 95 closes (reading 10's count over its 4582 rows 244); new (0, 0); inside the window (0, 0); after it (0, 0)
  sth_supply_share|low|long: in sample 5669 at 941 closes (reading 10's count over its 4582 rows 5669); new (656, 67); inside the window (0, 0); after it (656, 67)
  sth_supply_share|low|flat: in sample 7966 at 1616 closes (reading 10's count over its 4582 rows 7966); new (1224, 134); inside the window (780, 78); after it (444, 56)
  sth_supply_share|high|long: in sample 48 at 12 closes (reading 10's count over its 4582 rows 48); new (0, 0); inside the window (0, 0); after it (0, 0)
  sth_supply_share|high|flat: in sample 0 at 0 closes (reading 10's count over its 4582 rows 0); new (0, 0); inside the window (0, 0); after it (0, 0)
aSOPR's low-band days the new return indices read: ['2026-05-28', '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05', '2026-06-10', '2026-06-25', '2026-06-29', '2026-06-30', '2026-07-13', '2026-08-01']
the snapshot's days from 2026-10-26, which this head's forming row and no return index reads: 29, to 2026-11-23
  mvrv: its bands by day equal the grid's lagged ones over every row: True; past the head low / mid / high [0, 29, 0]
  mvrv_z: its bands by day equal the grid's lagged ones over every row: True; past the head low / mid / high [0, 29, 0]
  asopr: its bands by day equal the grid's lagged ones over every row: True; past the head low / mid / high [8, 21, 0]
    its low days past the head ['2026-11-13', '2026-11-15', '2026-11-16', '2026-11-18', '2026-11-19', '2026-11-20', '2026-11-21', '2026-11-23']
  sth_supply_share: its bands by day equal the grid's lagged ones over every row: True; past the head low / mid / high [27, 2, 0]
end 2026-11-25T11:52:36+00:00
```

**Trial 1's rule over the days after, and what a bar could read there**, a third program — positions by trial 1's own `_c3_reentry_inputs` over the rolling grid, thresholds by `deflated_sharpe_ratio` over counts, no series:

```python
import math
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import NormalDist

from cli.alpha.b1 import book_turnover
from cli.portfolio.record44_legs import STUB_YEARS, calendar_year_slices
from cli.registry.observed import ObservedReader
from cli.research import subjects
from cli.validation import deflated_sharpe_ratio
from cli.validation.dsr import expected_max_sharpe

DATASET = "btc-onchain-20261124T162656Z"
AS_OF = "2026-10-27"
print("start", datetime.now(UTC).isoformat(timespec="seconds"))
reader = ObservedReader(Path("data"))
snapshot = reader.read_series(DATASET, "BTC/onchain.parquet")
r_ts, r_prices = subjects._capturing_union(reader, "ohlc-rolling", 1440, None, AS_OF, False)
# Trial 1's positions half over the rolling grid: both arms' positions; its `returns` field is not read.
inputs = subjects._c3_reentry_inputs(snapshot, r_ts, r_prices)
n = len(inputs.close)
first_new = 4581
assets = list(inputs.arm_a)
new = range(first_new, n)
after = [k for k in new if inputs.close[k].date() > date(2026, 7, 9)]
differ = [k for k in new if any(inputs.arm_b[a][k] != inputs.arm_a[a][k] for a in assets)]
reentered = {a: [inputs.arm_a[a][k] == 0 and inputs.arm_b[a][k] > 0 for k in range(n)] for a in assets}
print(f"trial 1's rule over the {len(new)} return indices no record has read (rolling as of {AS_OF}): events {sum(inputs.fires[a][k] for a in assets for k in new)} at {sum(any(inputs.fires[a][k] for a in assets) for k in new)} closes; re-entered asset-closes {sum(reentered[a][k] for a in assets for k in new)} in {sum(reentered[a][k] and not reentered[a][k - 1] for a in assets for k in new)} entries; closes where the books differ {len(differ)}, {sum(k in set(after) for k in differ)} of them closing after the spent holdout's window")
print("  the first and last differing close:", inputs.close[differ[0]].date(), inputs.close[differ[-1]].date(), "; arm B's largest gross there", max(math.fsum(inputs.arm_b[a][k] for a in assets) for k in differ), "; its mean", math.fsum(math.fsum(inputs.arm_b[a][k] for a in assets) for k in differ) / len(differ))
print("  re-entries open at return index 4581 that the frozen set's last returns began:", sum(reentered[a][first_new] and reentered[a][first_new - 1] for a in assets))
zeros = [0.0] * n
slices = calendar_year_slices(zeros, r_ts)
print("STUB_YEARS", STUB_YEARS, "; calendar_year_slices over the rolling grid keeps years", sorted(slices), "; over the new return indices alone:", calendar_year_slices([0.0] * len(new), r_ts[first_new:]))


def bound(n_obs, n_trials, var_trials):
    lo, hi = 0.0, 2.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if deflated_sharpe_ratio(mid, n_obs, n_trials, var_trials) <= 0.95 else (lo, mid)
    return hi


print("expected max Sharpe at n_trials 2, var_trials 0.0:", expected_max_sharpe(2, 0.0), "; the DSR at counts 1 and 2 is one value at var_trials 0.0:", all(deflated_sharpe_ratio(x / 1000, 4581, 1, 0.0) == deflated_sharpe_ratio(x / 1000, 4581, 2, 0.0) for x in range(1, 200)))
normal = NormalDist()
for label, n_obs in (("the frozen sets' daily returns", 4581), ("the returns no record has read, this head", 210), ("of them after the spent holdout's window", 110), ("the snapshot's days after 2026-03-30", 238)):
    per_period = bound(n_obs, 2, 0.0)
    need = per_period * math.sqrt(365)
    print(f"{n_obs} daily returns ({label}) at n_trials 2, var_trials 0.0: dsr_pass needs a per-period Sharpe above {per_period:.6f}, annualised {need:.4f}")
    for true in (1.3797535717347145, 2 * 1.3797535717347145):
        se = math.sqrt(365 / n_obs)
        print(f"    a book whose true annualised Sharpe is {true:.4f} shows one above it with probability {1 - normal.cdf((need - true) / se):.3f} (normal, standard error sqrt(365 / n) = {se:.4f})")
for power in (0.5, 0.8):
    z = normal.inv_cdf(0.95) + normal.inv_cdf(power)
    days = 365 * (z / 1.3797535717347145) ** 2
    print(f"daily returns for the DSR leg to pass with probability {power} at a true annualised Sharpe of 1.3798: {days:.0f}, {days / 365:.2f} years")
years = 4581 / 365.25
print(f"in sample, {years:.2f} years: asopr|low|flat event closes a year {309 / years:.2f}; asopr|low|long event closes a year {43 / years:.2f}, episodes a year {24 / years:.2f}; low-band closes a year {319 / years:.2f}")
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-11-25T11:52:36+00:00
trial 1's rule over the 210 return indices no record has read (rolling as of 2026-10-27): events 110 at 11 closes; re-entered asset-closes 500 in 40 entries; closes where the books differ 50, 14 of them closing after the spent holdout's window
  the first and last differing close: 2026-04-01 2026-08-09 ; arm B's largest gross there 0.38617545674669895 ; its mean 0.29356626600160907
  re-entries open at return index 4581 that the frozen set's last returns began: 10
STUB_YEARS (2013, 2026) ; calendar_year_slices over the rolling grid keeps years ['2014', '2015', '2016', '2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025'] ; over the new return indices alone: {}
expected max Sharpe at n_trials 2, var_trials 0.0: 0.0 ; the DSR at counts 1 and 2 is one value at var_trials 0.0: True
4581 daily returns (the frozen sets' daily returns) at n_trials 2, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.024309, annualised 0.4644
    a book whose true annualised Sharpe is 1.3798 shows one above it with probability 0.999 (normal, standard error sqrt(365 / n) = 0.2823)
    a book whose true annualised Sharpe is 2.7595 shows one above it with probability 1.000 (normal, standard error sqrt(365 / n) = 0.2823)
210 daily returns (the returns no record has read, this head) at n_trials 2, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.114147, annualised 2.1808
    a book whose true annualised Sharpe is 1.3798 shows one above it with probability 0.272 (normal, standard error sqrt(365 / n) = 1.3184)
    a book whose true annualised Sharpe is 2.7595 shows one above it with probability 0.670 (normal, standard error sqrt(365 / n) = 1.3184)
110 daily returns (of them after the spent holdout's window) at n_trials 2, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.158535, annualised 3.0288
    a book whose true annualised Sharpe is 1.3798 shows one above it with probability 0.183 (normal, standard error sqrt(365 / n) = 1.8216)
    a book whose true annualised Sharpe is 2.7595 shows one above it with probability 0.441 (normal, standard error sqrt(365 / n) = 1.8216)
238 daily returns (the snapshot's days after 2026-03-30) at n_trials 2, var_trials 0.0: dsr_pass needs a per-period Sharpe above 0.107151, annualised 2.0471
    a book whose true annualised Sharpe is 1.3798 shows one above it with probability 0.295 (normal, standard error sqrt(365 / n) = 1.2384)
    a book whose true annualised Sharpe is 2.7595 shows one above it with probability 0.717 (normal, standard error sqrt(365 / n) = 1.2384)
daily returns for the DSR leg to pass with probability 0.5 at a true annualised Sharpe of 1.3798: 519, 1.42 years
daily returns for the DSR leg to pass with probability 0.8 at a true annualised Sharpe of 1.3798: 1185, 3.25 years
in sample, 12.54 years: asopr|low|flat event closes a year 24.64; asopr|low|long event closes a year 3.43, episodes a year 1.91; low-band closes a year 25.43
end 2026-11-25T11:52:48+00:00
```

**The veto's events and books on the frozen sets**, a fourth program — the events by `cli/alpha/c3.py`'s `flags`, arm B by `cli/alpha/b2.py`'s `scale_positions`, never through the trial's code:

```python
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import c3 as alpha_c3
from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import scale_positions
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

DATASET = "btc-onchain-20261124T162656Z"
HOLD = 7
print("start", datetime.now(UTC).isoformat(timespec="seconds"))
line = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
record = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
print("the ledger's last line: reading", line["reading_id"], line["iteration"], line["invocation"]["subject"], line["record_hash"])
print("the registry's last line: trial", record["trial_id"], record["family"], record["verdict"], record["invocation"]["subject"], record["invocation"]["commit"])
reader = ObservedReader(Path("data"))
t0 = time.perf_counter()
provenance, snapshot, daily_ts, daily_prices = subjects._c3_reads(reader, DATASET, "c3-onchain-reading")
inputs = subjects._c3_reading_inputs(snapshot, daily_ts, daily_prices)
print(f"the reads and the reading's inputs half, {time.perf_counter() - t0:.1f} s")
n = len(daily_ts) - 1
block = reader.block()
print("block", compute_hash(block), "; reading 10's:", compute_hash(block) == line["dataset_hash"] and block == line["datasets"], "; trial 65's:", compute_hash(block) == record["dataset_hash"] and block == record["datasets"])
print("vouched", reader.vouched_status(), "holes", reader.holes(), "; as-of line", provenance["as_of_line"])
metrics = line["metrics"]
print("the inputs half against reading 10's line: arm", inputs.arm == metrics["arm"], "; counts", inputs.counts == metrics["counts"])
assets = list(inputs.positions)
rows = n + 1
fires_all = {a: [f is True for f in alpha_c3.flags(inputs.bands["asopr"], inputs.states[a], tail="low", in_state="long")] for a in assets}
ledger = metrics["counts"]["asopr|low|long"]
print("events over the", rows, "position rows", sum(map(sum, fires_all.values())), "; at the forming row", sum(f[n] for f in fires_all.values()), "; reading 10's counts", sum(v["events"] for v in ledger.values()), "; per asset equal", {a: sum(fires_all[a]) for a in assets} == {a: v["events"] for a, v in ledger.items()}, "; its pooled H7 and H30 events", metrics["cells"]["asopr|low|long|H7"]["log"]["pooled"][0], metrics["cells"]["asopr|low|long|H30"]["log"]["pooled"][0])
fires = {a: f[:n] for a, f in fires_all.items()}
arm_a = {a: p[:n] for a, p in inputs.positions.items()}
close = daily_ts[1:]


def years(flags):
    out = {}
    for k, flag in enumerate(flags):
        if flag:
            out[str(close[k].year)] = out.get(str(close[k].year), 0) + 1
    return dict(sorted(out.items()))


event = [any(fires[a][k] for a in assets) for k in range(n)]
low = [b == "low" for b in inputs.bands["asopr"][:n]]
some_long = [any(arm_a[a][k] > 0 for a in assets) for k in range(n)]
print(f"events over the {n} completed returns {sum(map(sum, fires.values()))} at {sum(event)} closes; the low band is read at {sum(low)} closes; the sleeve holds some asset long at {sum(some_long)} closes")
print("  per asset", {a: sum(fires[a]) for a in assets})
print("  events per close year", {y: sum(years(fires[a]).get(y, 0) for a in assets) for y in sorted({str(c.year) for c in close})})
print("  event closes per close year", years(event))
print("  assets firing at an event close: median", statistics.median(sum(fires[a][k] for a in assets) for k in range(n) if event[k]), "max", max(sum(fires[a][k] for a in assets) for k in range(n)), "; assets long and not firing at an event close:", sum(arm_a[a][k] > 0 and not fires[a][k] for a in assets for k in range(n) if event[k]))
runs, k = [], 0
while k < n:
    if event[k]:
        j = k
        while j + 1 < n and event[j + 1]:
            j += 1
        runs.append(j - k + 1)
        k = j + 1
    else:
        k += 1
print(f"  the {sum(event)} event closes fall in {len(runs)} runs, closes per run median {statistics.median(runs)}, mean {statistics.fmean(runs):.2f}, max {max(runs)}")
episodes, last = 0, None
for k in range(n):
    if event[k]:
        if last is None or k - last > HOLD:
            episodes += 1
        last = k
print(f"  event closes more than {HOLD} closes after the one before them open {episodes} episodes")
held = [arm_a[a][k] for a in assets for k in range(n) if fires[a][k]]
gross_a = [math.fsum(arm_a[a][k] for a in assets) for k in range(n)]
print(f"  the sleeve's position in a firing asset: median {statistics.median(held):.6f}, mean {statistics.fmean(held):.6f}, max {max(held):.6f}; its gross at an event close: median {statistics.median(g for g, e in zip(gross_a, event) if e):.6f}, mean {statistics.fmean(g for g, e in zip(gross_a, event) if e):.6f}, max {max(g for g, e in zip(gross_a, event) if e):.6f}")
print("  events before return index 199:", sum(fires[a][k] for a in assets for k in range(199)), "; before 230:", sum(fires[a][k] for a in assets for k in range(230)))


def window_scales(depth):
    """Vetoed through 7 closes counted from the last event close, whatever the sleeve then does."""
    return {a: [depth if any(fires[a][max(0, k - HOLD + 1) : k + 1]) else 1.0 for k in range(n)] for a in assets}


def closed_scales(depth):
    """The same, closed where the sleeve itself turns flat: reentry_positions' rule mirrored."""
    out = {}
    for a in assets:
        left, row = 0, []
        for k, p in enumerate(arm_a[a]):
            if p == 0:
                left = 0
            elif fires[a][k]:
                left = max(left, HOLD)
            row.append(depth if p > 0 and left > 0 else 1.0)
            if p > 0 and left > 0:
                left -= 1
        out[a] = row
    return out


turnover_a = book_turnover(arm_a)
print(f"arm A: turnover {turnover_a!r}; largest gross {max(gross_a):.6f}; asset-closes long {sum(arm_a[a][k] > 0 for a in assets for k in range(n))}; exposure held {math.fsum(arm_a[a][k] for a in assets for k in range(n)):.6f} asset-closes of NAV")
books = {}
for depth in (0.0, 0.5):
    for rule, scales in (("through 7 closes", window_scales(depth)), ("closed where the sleeve turns flat", closed_scales(depth))):
        arm_b = scale_positions(arm_a, scales)
        books[(depth, rule)] = arm_b
        differ = [any(arm_b[a][k] != arm_a[a][k] for a in assets) for k in range(n)]
        first = differ.index(True)
        vetoed = {a: [arm_a[a][k] > 0 and arm_b[a][k] < arm_a[a][k] for k in range(n)] for a in assets}
        count = sum(map(sum, vetoed.values()))
        entries = sum(v[k] and not (k and v[k - 1]) for v in vetoed.values() for k in range(n))
        removed = math.fsum(arm_a[a][k] - arm_b[a][k] for a in assets for k in range(n))
        turnover_b = book_turnover(arm_b)
        gross = [math.fsum(arm_b[a][k] for a in assets) for k in range(n)]
        print(f"depth {depth}; {rule}:")
        print(f"  asset-closes long in arm A and smaller in arm B {count}, entries {entries}, {count / entries:.1f} closes per entry; closes where the books differ {sum(differ)}, first {first}, close {close[first].isoformat()}, {n - first} returns from it")
        print(f"  turnover {turnover_b!r}, over arm A {turnover_b - turnover_a!r}; exposure removed {removed:.6f} asset-closes of NAV, mean {removed / count:.6f}; break-even mean asset return per removed close {-(turnover_b - turnover_a) * 0.006 / removed:.6%}")
        print(f"  largest gross {max(gross):.6f}; a position below 0 at {sum(arm_b[a][k] < 0 for a in assets for k in range(n))} asset-closes; a position above arm A's at {sum(arm_b[a][k] > arm_a[a][k] for a in assets for k in range(n))}")
a_, b_ = books[(0.0, "through 7 closes")], books[(0.0, "closed where the sleeve turns flat")]
print("the two hold rules differ at", sum(a_[a][k] != b_[a][k] for a in assets for k in range(n)), "asset-closes; asset-closes inside an event's 7 closes", sum(any(fires[a][max(0, k - HOLD + 1) : k + 1]) for a in assets for k in range(n)), "; the sleeve flat at", sum(any(fires[a][max(0, k - HOLD + 1) : k + 1]) and arm_a[a][k] == 0 for a in assets for k in range(n)))

chosen = books[(0.0, "through 7 closes")]
vetoed = {a: [arm_a[a][k] > 0 and chosen[a][k] < arm_a[a][k] for k in range(n)] for a in assets}
print("the recommended book, arm B (depth 0, through 7 closes)")
print("  vetoed_per_year", {y: sum(years(vetoed[a]).get(y, 0) for a in assets) for y in sorted({str(c.year) for c in close})})
print("  positions_differ_per_year", years([any(chosen[a][k] != arm_a[a][k] for a in assets) for k in range(n)]))
print("  vetoed per asset", {a: sum(vetoed[a]) for a in assets})
first = next(k for k in range(n) if any(chosen[a][k] != arm_a[a][k] for a in assets))
print("  veto_entries", sum(v[k] and not (k and v[k - 1]) for v in vetoed.values() for k in range(n)), "; gross_max", repr(max(math.fsum(chosen[a][k] for a in assets) for k in range(n))), "; turnover_b", repr(book_turnover(chosen)), "; first engagement", first, close[first].isoformat(), "; arm B is arm A to the bit before it:", all(chosen[a][:first] == arm_a[a][:first] for a in assets))
print("  closes at which arm B holds nothing while arm A holds something:", sum(some_long[k] and not any(chosen[a][k] > 0 for a in assets) for k in range(n)), "; closes at which a veto is open and arm B still holds another asset:", sum(any(vetoed[a][k] for a in assets) and any(chosen[a][k] > 0 for a in assets) for k in range(n)))
print("  exposure_removed", repr(math.fsum(arm_a[a][k] - chosen[a][k] for a in assets for k in range(n))), "; events_per_year summed", sum(map(sum, fires.values())), "; vetoed_per_year summed", sum(map(sum, vetoed.values())))
late = sum(fires[a][k] and k + HOLD > n for a in assets for k in range(n))
print("  events whose 7 closes run past the set's last return:", late)
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-11-25T11:52:49+00:00
the ledger's last line: reading 10 iter-209 c3-onchain-reading ed1bb73e76e3ab32bfc8cbd72212522f571e7d388a096871eb9b0949c05c590c
the registry's last line: trial 65 C3 reject c3-asopr-reentry d308b687c7a5ebaae110f2853ea42814e4b6c754
the reads and the reading's inputs half, 8.2 s
block 19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a ; reading 10's: True ; trial 65's: True
vouched {'btc-onchain-20261124T162656Z': 'checked (1 vouched hashes)', 'ohlc-full': 'checked (36 vouched hashes)'} holes {} ; as-of line {'relpath': 'index/2026/11/23.json', 'sha256': '2d9b2f4529042094111751c8b1f22ec5cd04577be507e2a8911a2e1a228bb5e2'}
the inputs half against reading 10's line: arm True ; counts True
events over the 4582 position rows 176 ; at the forming row 0 ; reading 10's counts 176 ; per asset equal True ; its pooled H7 and H30 events 176 176
events over the 4581 completed returns 176 at 43 closes; the low band is read at 319 closes; the sleeve holds some asset long at 2668 closes
  per asset {'ADA': 15, 'AVAX': 4, 'BTC': 29, 'DOGE': 10, 'DOT': 10, 'ETH': 37, 'LINK': 17, 'LTC': 29, 'SOL': 8, 'XRP': 17}
  events per close year {'2013': 0, '2014': 1, '2015': 11, '2016': 6, '2017': 7, '2018': 20, '2019': 21, '2020': 15, '2021': 43, '2022': 0, '2023': 50, '2024': 2, '2025': 0, '2026': 0}
  event closes per close year {'2014': 1, '2015': 5, '2016': 2, '2017': 2, '2018': 10, '2019': 6, '2020': 4, '2021': 6, '2023': 6, '2024': 1}
  assets firing at an event close: median 3 max 10 ; assets long and not firing at an event close: 0
  the 43 event closes fall in 34 runs, closes per run median 1.0, mean 1.26, max 3
  event closes more than 7 closes after the one before them open 24 episodes
  the sleeve's position in a firing asset: median 0.017844, mean 0.029903, max 0.448134; its gross at an event close: median 0.102456, mean 0.122394, max 0.517983
  events before return index 199: 0 ; before 230: 0
arm A: turnover 46.72757036801258; largest gross 0.764856; asset-closes long 14110; exposure held 547.632244 asset-closes of NAV
depth 0.0; through 7 closes:
  asset-closes long in arm A and smaller in arm B 688, entries 97, 7.1 closes per entry; closes where the books differ 175, first 335, close 2014-08-16T00:00:00+00:00, 4246 returns from it
  turnover 50.32075233684487, over arm A 3.5931819688322904; exposure removed 25.814714 asset-closes of NAV, mean 0.037521; break-even mean asset return per removed close -0.083515%
  largest gross 0.764856; a position below 0 at 0 asset-closes; a position above arm A's at 0
depth 0.0; closed where the sleeve turns flat:
  asset-closes long in arm A and smaller in arm B 683, entries 95, 7.2 closes per entry; closes where the books differ 175, first 335, close 2014-08-16T00:00:00+00:00, 4246 returns from it
  turnover 50.32733538613031, over arm A 3.599765018117729; exposure removed 25.791996 asset-closes of NAV, mean 0.037763; break-even mean asset return per removed close -0.083741%
  largest gross 0.764856; a position below 0 at 0 asset-closes; a position above arm A's at 0
depth 0.5; through 7 closes:
  asset-closes long in arm A and smaller in arm B 688, entries 97, 7.1 closes per entry; closes where the books differ 175, first 335, close 2014-08-16T00:00:00+00:00, 4246 returns from it
  turnover 48.24420880711928, over arm A 1.5166384391066998; exposure removed 12.907357 asset-closes of NAV, mean 0.018761; break-even mean asset return per removed close -0.070501%
  largest gross 0.764856; a position below 0 at 0 asset-closes; a position above arm A's at 0
depth 0.5; closed where the sleeve turns flat:
  asset-closes long in arm A and smaller in arm B 683, entries 95, 7.2 closes per entry; closes where the books differ 175, first 335, close 2014-08-16T00:00:00+00:00, 4246 returns from it
  turnover 48.247500331762, over arm A 1.5199299637494192; exposure removed 12.895998 asset-closes of NAV, mean 0.018881; break-even mean asset return per removed close -0.070716%
  largest gross 0.764856; a position below 0 at 0 asset-closes; a position above arm A's at 0
the two hold rules differ at 5 asset-closes; asset-closes inside an event's 7 closes 844 ; the sleeve flat at 156
the recommended book, arm B (depth 0, through 7 closes)
  vetoed_per_year {'2013': 0, '2014': 3, '2015': 71, '2016': 21, '2017': 44, '2018': 49, '2019': 124, '2020': 35, '2021': 93, '2022': 0, '2023': 244, '2024': 4, '2025': 0, '2026': 0}
  positions_differ_per_year {'2014': 3, '2015': 32, '2016': 8, '2017': 14, '2018': 29, '2019': 31, '2020': 9, '2021': 16, '2023': 31, '2024': 2}
  vetoed per asset {'ADA': 53, 'AVAX': 23, 'BTC': 134, 'DOGE': 25, 'DOT': 29, 'ETH': 143, 'LINK': 57, 'LTC': 120, 'SOL': 40, 'XRP': 64}
  veto_entries 97 ; gross_max 0.7648558752122554 ; turnover_b 50.32075233684487 ; first engagement 335 2014-08-16T00:00:00+00:00 ; arm B is arm A to the bit before it: True
  closes at which arm B holds nothing while arm A holds something: 163 ; closes at which a veto is open and arm B still holds another asset: 12
  exposure_removed 25.814713828926113 ; events_per_year summed 176 ; vetoed_per_year summed 688
  events whose 7 closes run past the set's last return: 0
end 2026-11-25T11:52:57+00:00
```

**The count, the names and record 65's anchors**, a fifth program:

```python
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from cli.registry import budget
from cli.research import subjects
from tests.retired_subjects import RETIRED_SUBJECTS

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
records = [json.loads(x) for x in Path("docs/reference/trial-registry.jsonl").read_text().splitlines()]
readings = [json.loads(x) for x in Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()]
print("BUCKET_OF", budget.BUCKET_OF, "BUDGET", budget.BUDGET)
print("registry", len(records), "records, by family", dict(Counter(r["family"] for r in records)))
by_bucket = Counter(budget.BUCKET_OF[r["family"]] for r in records)
print("records per bucket", dict(by_bucket), "; bucket C's records:", [(r["trial_id"], r["family"], r["n_trials_in_family"], r["verdict"], r["invocation"]["subject"], r["attempt"]["counted"]) for r in records if budget.BUCKET_OF[r["family"]] == "C"])
print("ledger", len(readings), "readings; carrying an attempt:", [r["reading_id"] for r in readings if r.get("attempt") is not None])
print("families the registered subjects declare:", dict(Counter(s.family for s in subjects.SUBJECTS.values() if s.family is not None)), "; C3's:", [(name, s.n_trials) for name, s in subjects.SUBJECTS.items() if s.family == "C3"])
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("c3-asopr-veto", "c3-asopr-veto-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("names opening c3:", sorted(x for x in names if x.startswith("c3")), "; retired among them:", sorted(x for x in RETIRED_SUBJECTS if x.startswith("c3")))
variants = [r.get("variant") for r in records]
print("variant C3-asopr-veto-a1lf-full-v1 in the registry:", "C3-asopr-veto-a1lf-full-v1" in variants, "; trial 65's variant", records[-1]["variant"])
last = records[-1]
m = last["metrics"]
print("trial", last["trial_id"], "arm A and the benchmark:", {k: m[k] for k in ("arm_a_ann_sharpe_noc", "arm_a_ann_sharpe_noc_decisive", "arm_a_max_drawdown", "turnover_a", "arm_a_passes", "benchmark_ann_sharpe_noc", "benchmark_ann_sharpe_noc_decisive", "decisive_start", "n_resamples")})
print("trial", last["trial_id"], "its verdict's figures:", last["verdict"], {k: m[k] for k in ("passes", "head_to_head_mean_outperf_primary", "head_to_head_spa_p_primary", "max_drawdown_reduction_pct", "reentry_first_engaged", "primary_returns", "stamps_positions_differ")})
print("trial", last["trial_id"], "its notes' pre-flight clause:", last["notes"][last["notes"].index("pre-flight:"):last["notes"].index("; the park row")])
```

Its output, whole:

```text
read at 2026-11-25T11:52:57+00:00
BUCKET_OF {'A1': 'A', 'B1': 'B', 'B2': 'B', 'B3': 'B', 'B4': 'B', 'C3': 'C', 'P1': None} BUDGET {'A': 40, 'B': 25, 'C': 10}
registry 65 records, by family {'A1': 40, 'P1': 7, 'B1': 5, 'B2': 7, 'B4': 2, 'B3': 3, 'C3': 1}
records per bucket {'A': 40, None: 7, 'B': 17, 'C': 1} ; bucket C's records: [(65, 'C3', 1, 'reject', 'c3-asopr-reentry', [])]
ledger 10 readings; carrying an attempt: []
families the registered subjects declare: {'B2': 8, 'B1': 3, 'B4': 2, 'B3': 3, 'P1': 2, 'C3': 1} ; C3's: [('c3-asopr-reentry', 1)]
c3-asopr-veto equals or opens with a hyphen: [] ; it opens: []
c3-asopr-veto-preflight equals or opens with a hyphen: [] ; it opens: []
names opening c3: ['c3-asopr-reentry', 'c3-asopr-reentry-preflight', 'c3-onchain-reading'] ; retired among them: ['c3-onchain-reading']
variant C3-asopr-veto-a1lf-full-v1 in the registry: False ; trial 65's variant C3-asopr-reentry-a1lf-full-v1
trial 65 arm A and the benchmark: {'arm_a_ann_sharpe_noc': 1.3797535717347145, 'arm_a_ann_sharpe_noc_decisive': 1.4159389071170758, 'arm_a_max_drawdown': 0.15777579530839503, 'turnover_a': 46.72757036801258, 'arm_a_passes': 1, 'benchmark_ann_sharpe_noc': 1.245474508086168, 'benchmark_ann_sharpe_noc_decisive': 1.2781056074367316, 'decisive_start': 230, 'n_resamples': 2000}
trial 65 its verdict's figures: reject {'passes': 1, 'head_to_head_mean_outperf_primary': -2.0291967351609812e-05, 'head_to_head_spa_p_primary': 0.6786606696651675, 'max_drawdown_reduction_pct': -57.325247779115955, 'reentry_first_engaged': 97, 'primary_returns': 4484, 'stamps_positions_differ': 977}
trial 65 its notes' pre-flight clause: pre-flight: block 19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a, arm A arm_a_ann_sharpe_noc 1.3797535717347145, arm_a_ann_sharpe_noc_decisive 1.4159389071170758, arm_a_max_drawdown_full 0.15777579530839503, turnover_a 46.72757036801258, arm_a_spot_drag_pct_yr 0.022338655120267965, the bar's dsr 0.9999994726590977 and SPA p 0.0069965017491254375, passes 1, the benchmark's Sharpe 1.245474508086168 and decisive 1.2781056074367316 against record 33's 1.2455
```

Trial 65, reading 10, their specs and the code path since, the tier, the triggers, the two lines D1's option 2 rests on, and the arithmetic over the programs' printed figures:

```text
$ date -u +%Y-%m-%dT%H:%M:%SZ; hostname; git rev-parse HEAD; git merge-base HEAD origin/develop; sha256sum docs/specs/00165-c3-trial-1-asopr-reentry-design.md docs/specs/00164-t0228-btc-onchain-design.md; python3 -I -c 'import json; r = json.loads(open("docs/reference/trial-registry.jsonl").read().splitlines()[-1]); print("trial", r["trial_id"], r["spec_hash"], r["invocation"]["commit"]); r = json.loads(open("docs/reference/reading-ledger.jsonl").read().splitlines()[-1]); print("reading", r["reading_id"], r["spec_hash"], r["invocation"]["commit"])'; git merge-base --is-ancestor d308b687c7a5ebaae110f2853ea42814e4b6c754 HEAD && echo ancestor; git log --oneline d308b687c7a5ebaae110f2853ea42814e4b6c754..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research cli/registry cli/onchain cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat; echo "the log's end"
2026-11-25T11:52:57Z
zcrypto-ops
2b6ad261ddeb34bf45da68f120180c3ce810c288
1a4abc4f5b9e416ac3d57fde8d5b5c1af9a2d4d2
2aa047d9d9e3a87427b087a8d7c9079e4916ffa963a3394aaa5d1b9bf0b40aa1  docs/specs/00165-c3-trial-1-asopr-reentry-design.md
89eb8be96d6961b2f4c6240b6b6ce7a8a045768413f0a6087a810fe64067c86e  docs/specs/00164-t0228-btc-onchain-design.md
trial 65 2aa047d9d9e3a87427b087a8d7c9079e4916ffa963a3394aaa5d1b9bf0b40aa1 d308b687c7a5ebaae110f2853ea42814e4b6c754
reading 10 89eb8be96d6961b2f4c6240b6b6ce7a8a045768413f0a6087a810fe64067c86e 88fdf97e14a4ee5076db35468f4b0177d0e7cb31
ancestor
the log's end
$ uv run python infra/scripts/tier.py --paths cli/alpha/c3_veto.py cli/research/subjects.py tests/test_alpha_c3_veto.py tests/test_research_c3_asopr_veto.py tests/test_research_c3_asopr_veto_basis.py tests/test_trial_registry_provenance.py tests/test_research_command.py tests/slow-cases.txt README.md; grep -c -E '^\[iter-[0-9]+\] C3.s next step after trial 1' docs/research/10.phase4-decisions.md; grep -c -E '^\[iter-[0-9]+\] C3.s next step after trial 2' docs/research/10.phase4-decisions.md; ls data; ls docs/specs | tail -1; grep -n 'is frozen: --as-of' cli/research/command.py | cut -c1-140; grep -n '_capturing_union(reader, "ohlc-full"' cli/research/subjects.py | cut -c1-120; cat docs/reference/trial-attempt-logs.txt
tier: full
full tests/test_trial_registry_provenance.py — a test importing cli.registry, read as a non-prose change
full tests/test_research_command.py — a test importing cli.alpha, read as a non-prose change
1
0
btc-onchain-20261124T162656Z
ohlc-full
ohlc-rolling
00166-c3-trial-2-asopr-veto-design.md
391:        raise _abort(f"dataset {dataset!r} is frozen: --as-of and --accept-holes read the rolling dataset alone")
5209:    daily_ts, daily_prices = _capturing_union(reader, "ohlc-full", 1440, None, None, False)
60c9f39c37ec81b4a53396218b690304 zcrypto-ops
$ python3 -I -c '
import math
added, removed = 3.5931819688322904, 25.814714
print("the added trading at 0.006 a side", added * 0.006, "; a bar from the first engagement", added * 0.006 / 4246)
print("the break-even over 7 closes", 7 * added * 0.006 / removed)
print("events an entry", 176 / 97, "; vetoed closes an entry", 688 / 97, "; events an event close", 176 / 43)
print("the veto removes of the sleeve: its exposure", removed / 547.632244, "; its long asset-closes", 688 / 14110, "; the closes at which the books differ", 175 / 4581)
target = 0.12 / math.sqrt(365)
error = target * math.sqrt(175)
need = 1.645 * error + added * 0.006
print("the sleeve target a close", target, "; its standard error over 175 independent closes", error, "; 1.645 of them", 1.645 * error)
print("with the added trading", need, "; a differing close", need / 175, "; a removed asset-close", need / removed, "; over 7 closes", 7 * need / removed)
print("low-band days after 2026-03-30:", 11 + 8, "; the unread days", 210 + 29 - 1)
'
the added trading at 0.006 a side 0.021559091812993744 ; a bar from the first engagement 5.077506314883124e-06
the break-even over 7 closes 0.005846031944841853
events an entry 1.8144329896907216 ; vetoed closes an entry 7.092783505154639 ; events an event close 4.093023255813954
the veto removes of the sleeve: its exposure 0.04713877658379808 ; its long asset-closes 0.04875974486180014 ; the closes at which the books differ 0.038201266099105
the sleeve target a close 0.006281087071082565 ; its standard error over 175 independent closes 0.08309097176613772 ; 1.645 of them 0.13668464855529655
with the added trading 0.1582437403682903 ; a differing close 0.0009042499449616589 ; a removed asset-close 0.006129982318157401 ; over 7 closes 0.04290987622710181
low-band days after 2026-03-30: 19 ; the unread days 238
```

```text
$ ZCRYPTO_RERUN_SLOW=1 uv run pytest -q -p no:cacheprovider "tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-65]" "tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-10]" tests/test_research_c3_asopr_reentry_basis.py tests/test_research_c3_onchain_reading_basis.py tests/test_portfolio_builder.py::test_frozen_figures_regression
......                                                                   [100%]
6 passed in 65.38s (0:01:05)
```

What they establish:

- **The days after the history, as this workstation holds them.** `ohlc-rolling`'s head here is 2026-10-27 — line `index/2026/10/27.json`, sha256 `89ab2d72cfffe52befa7fc767c522e945ebeb3b78bb0f379e25d72f419c812c4`, the 28th line from the base day 2026-09-30, no hole on any line, every listed file hashing to its listing. Its daily union as of that day holds 4,792 stamps, 2013-09-10 → 2026-10-27; over the 4,582 stamps it shares with `ohlc-full` the stamps are one list and every close of every asset is equal; 210 stamps follow, 2026-04-01 → 2026-10-27, consecutive days with no close missing. So 210 return indices, 4581 … 4790, are read by no record and no reading: 100 close inside the spent holdout's window, 2026-04-01 → 2026-07-09, and 110 after it, 2026-07-10 → 2026-10-27. The snapshot runs to 2026-11-23: its 29 days from 2026-10-26 are read by no return index of this head.
- **The frozen history is one history on either set.** Over the frozen set's 4,581 completed returns the sleeve's positions on the rolling union equal `ohlc-full`'s to the bit, its states are equal, and each feature's bands are equal over the 4,582 shared rows; one reader reads the snapshot file by file and the rolling set through its index into one block (`checked (1 vouched hashes)`, `chained (as of 2026-10-27, line 89ab2d72cfff)`).
- **The sleeve over the 210.** Flat in every asset from the first of them to the decision of 2026-08-20; some asset long at each of the 67 closes from the decision of 2026-08-21 to the last, 2026-10-26, seven of the ten assets at all 67 and DOGE, the fewest, at 56; BTC above its 200-day SMA at 68. No close inside the spent holdout's window has an asset long.
- **The bands over the 210.** MVRV and the reading's MVRV-Z are in their middle band on all 210. aSOPR is in its low band on 11 — 2026-05-28, 06-02, 06-03, 06-04, 06-05, 06-10, 06-25, 06-29, 06-30, 07-13 and 08-01, nine read by returns closing inside the window and two after it — and never in its high band. The STH supply share is in its low band on 188 and its middle band on 22: a band that holds for nine days in ten is no tail there.
- **The events over the 210, for the 16 feature, tail and state triples reading 10's 32 cells are built on.** Three have any: `asopr|low|flat`, trial 1's own, 110 events at 11 closes — 90 at 9 inside the window, 20 at 2 after it; `sth_supply_share|low|long`, 656 at 67 closes; `sth_supply_share|low|flat`, 1,224 at 134. The thirteen others have none, `asopr|low|long` among them: aSOPR's 11 low days all fall while the sleeve is flat. In sample each triple's count is reading 10's.
- **Past the head.** Of the snapshot's 29 days from 2026-10-26, aSOPR is in its low band on 8 — 2026-11-13, 11-15, 11-16, 11-18, 11-19, 11-20, 11-21 and 11-23; MVRV and MVRV-Z are in their middle band on all 29 and the STH supply share in its low band on 27. Whether the sleeve is long on those days needs closes this workstation does not hold (*Not measured*).
- **Trial 1's rule over the 210**, from positions: 110 events at 11 closes, 500 re-entered asset-closes in 40 entries, the books differing at 50 closes, 2026-04-01 → 2026-08-09, 14 of them closing after the window; arm B's gross there 0.2936 on average and 0.3862 at most. At return index 4581 all ten assets are in a re-entry the frozen set's last returns began.
- **The ratified bar cannot be called on the days after alone.** `STUB_YEARS` is `(2013, 2026)` (`cli/portfolio/record44_legs.py:31`) and every one of the 210 returns closes in 2026, so `calendar_year_slices` over them is `{}`, and `a1_kill_bar` refuses an empty `regime_slices` (`cli/alpha/killbar.py:52-53`). Over the rolling union whole it keeps the years 2014–2025.
- **The DSR leg on the days after.** At count 2 and `var_trials` 0.0 the expected maximum Sharpe is 0.0 and the DSR is its value at count 1 (measured over 199 Sharpes), so over the frozen sets' 4,581 returns `dsr_pass` needs an annualised Sharpe above 0.4644, trial 1's figure. Over 210 returns it needs 2.1808, over the 110 after the window 3.0288, over 238 — every snapshot day after 2026-03-30 — 2.0471. A book whose true annualised Sharpe is the sleeve's registered 1.3798 would show one above the 210-return threshold with probability 0.272, and one of twice that with 0.670; for the leg to pass at even odds at 1.3798 takes 519 daily returns, 1.42 years, and with probability 0.8, 1,185, 3.25 years. The probabilities are **inferred**, a normal approximation with standard error √(365 / n).
- **How fast the days after accrue.** In sample, over 12.54 years, `asopr|low|flat` has 24.64 event closes a year; `asopr|low|long` has 3.43, in 1.91 episodes.
- **The sets and the block of D1's option 1.** `btc-onchain-20261124T162656Z` — `checked (1 vouched hashes)`, cut from the chain's as-of line `index/2026/11/23.json` (sha256 `2d9b2f4529042094111751c8b1f22ec5cd04577be507e2a8911a2e1a228bb5e2`) — and `ohlc-full` — `checked (36 vouched hashes)` — with no hole form the block `19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a`: reading 10's `dataset_hash` and trial 65's, the blocks equal file for file. `_c3_reading_inputs` over those reads returns reading 10's `arm` and `counts` blocks; the reads and the inputs half took 8.2 s.
- **The veto's events.** The cell's flag — the sleeve long in the asset, aSOPR's band low — is set at 176 asset-closes, none at the forming row: reading 10's count for `asopr|low|long`, asset for asset, and all 176 the events of its pooled rows at both horizons. They fall on 43 closes of the 2,668 at which the sleeve holds some asset long, and of the 319 at which the low band is read. Per asset: ADA 15, AVAX 4, BTC 29, DOGE 10, DOT 10, ETH 37, LINK 17, LTC 29, SOL 8, XRP 17. Events per close year: 2014 1, 2015 11, 2016 6, 2017 7, 2018 20, 2019 21, 2020 15, 2021 43, 2023 50, 2024 2, none in 2013, 2022, 2025 or 2026; event closes per close year: 2014 1, 2015 5, 2016 2, 2017 2, 2018 10, 2019 6, 2020 4, 2021 6, 2023 6, 2024 1. At an event close 3 assets fire at the median and 10 at the most, and no asset the sleeve holds long fails to fire: the band is one value a day, so a low-band close vetoes the whole sleeve. The 43 closes fall in 34 runs, 1 close long at the median and 3 at the longest, and open 24 episodes, an episode beginning at an event close more than 7 closes after the one before it. None falls before return index 230.
- **What the veto removes at an event.** The sleeve's position in a firing asset is 0.017844 at the median, 0.029903 on average and 0.448134 at the most; its gross at an event close 0.102456 at the median, 0.122394 on average and 0.517983 at the most.
- **The four books** — two depths by two hold rules, each against arm A, whose turnover is 46.72757036801258, largest gross 0.764856, long asset-closes 14,110 and exposure held 547.632244 asset-closes of NAV:
  - **Flat, through 7 closes** — 688 asset-closes long in arm A and smaller in arm B, in 97 entries, 7.1 closes an entry; the books differ at 175 closes, first at return index 335 (close 2014-08-16), 4,246 returns from it; turnover 50.32075233684487, 3.5931819688322904 over arm A; exposure removed 25.814714 asset-closes of NAV, 0.037521 a vetoed asset-close.
  - **Flat, closed where the sleeve turns flat** — 683 asset-closes in 95 entries, the same 175 closes; turnover 50.32733538613031; it differs from the first at 5 asset-closes.
  - **Halved, through 7 closes** — the same 688 asset-closes, 97 entries and 175 closes; turnover 48.24420880711928, 1.5166384391066998 over arm A; exposure removed 12.907357.
  - **Halved, closed where the sleeve turns flat** — 683 asset-closes in 95 entries; turnover 48.247500331762.
  - In all four no position of arm B is below 0 or above arm A's, so arm B's largest gross is arm A's.
- **The hurdle**, from positions alone: the added trading costs 3.5931819688322904 × 0.006 = 0.021559091812993744 of NAV over the window, 5.077506314883124e-06 a bar from the first engagement, so the veto pays only if the exposure it removes carried a mean asset return below −0.083515 % a close, −0.5846 % over 7 closes. Halved, the break-even is −0.070501 % a close. The veto removes 4.71 % of the sleeve's exposure, 4.88 % of its long asset-closes, at 3.82 % of the closes.
- **The head-to-head's reach — inferred from counts and a design constant, no series read.** At 163 of the 175 differing closes arm B holds nothing, so the difference a close is, to first order, minus the sleeve's own return there, a book the sleeve sizes to 0.12 / √365 = 0.006281 a close. Were the 175 closes independent their summed difference would carry a standard error near 0.0831 of NAV, so a one-sided 5 % read needs the veto to have saved about 0.137 of NAV and, with its trading, the removed exposure to have lost about 0.158: −0.613 % a removed asset-close, −4.29 % over 7 closes. The closes fall in 24 episodes and are not independent, so the reach is shorter than that. Reading 10's row for the cell gives a summed mean after the events of -0.016629646555238572 over 7 closes, pooled over events of equal weight — another object, as trial 1 showed, whose pooled 0.030735850910887732 became a negative head-to-head.
- **The count.** The registry's 65 records carry seven family keys; bucket C holds one record, trial 65, family C3, `n_trials_in_family` 1, its `attempt.counted` empty, so bucket C has spent 1 of 10.
- **Two lines D1's option 2 rests on**: `research eval` refuses `--as-of` beside a frozen `--dataset` (`cli/research/command.py:391`), and `_c3_reads` names `ohlc-full` (`cli/research/subjects.py:5209`).

Read from the tree, each by its path:

- **The registry's priors on the two treatments**: five de-risk overlays on the A2-4h ensemble at half depth, records 51–54 and 57, all REJECT, read under spec 00128's matrix and spec 00138 D8's form of it (`_b2_verdict`, `cli/research/subjects.py:615`, for record 51 and `_b2_overlay_verdict`, `:2496`, for the four others: an adopt or a park needs a positive head-to-head and `max_drawdown_reduction_pct` above 1e-6); three re-entries, records 55 and 56 on that ensemble and 65 on this sleeve, all REJECT, read under spec 00139 D5's (`_b2_reentry_verdict`, `:2906`, and `_c3_asopr_reentry_verdict`, `:5548`).
- **The budget in code**: `BUCKET_OF` holds `"C3": "C"` and `BUDGET["C"]` is 10 (`cli/registry/budget.py:6-7`).
- **The two rulings binding every C pre-registration** (`[iter-176]`, T0016's findings): the DSR leg binds at every `n_trials`, `var_trials` 0.0 included; and a search may read the spent holdout's window, 2026-04-01 → 2026-07-09, through `ohlc-rolling`, but no result there is reported as holdout or out-of-sample evidence.
- **A reading's nearest cell has been tried once on the owner's word before**: B4 trial 2 (spec 00146; `[iter-190]`, "one more trail on B4, then move on"), a cell its reading's criterion did not name, judged at the matrix's 0.05 on `ohlc-rolling` with its unseen months read beside the matrix in no leg, PARK, registry trial 59.

**Not measured:**

- **Any return of arm B, and any return of arm A, the benchmark or an asset over the vetoed closes or the event closes** — the veto's result under another name.
- **The sleeve's state on the snapshot's 29 days past the rolling head**, and so whether aSOPR's 8 low days of November 2026 are events of this cell, of trial 1's, or of neither: it takes a head past 2026-10-27, a `zcrypto data fetch`, the owner's. Only D1's option 2 rests on it.

## Hypothesis (trial 2 at D1's option 1, never registered)

C3's one question is "marginal value inside the A1 gate" (`00.master-plan.md` §5): coins moved at a loss, read on-chain a day late, mark closes after which the assets the sleeve holds long go on to do worse than after its other long closes, so **the A1 sleeve as records 44 and 47 build it, with every asset it holds long at a daily close where the previous UTC day's aSOPR lies at or below the 10th percentile of its own history from 2011-01-01, read after 365 values, held flat through 7 daily closes counted from the last such close, has a higher mean net-of-cost return than the sleeve alone from the first close the two books differ, net of each asset's own turnover at 0.006 a side.**
Arm A is the sleeve exactly as reading 10 and trial 65 read it; arm B never holds more than arm A in any asset, is long-only and borrows nothing.

## D1 — what trial 2 tests, and on which days (the owner's)

**The owner's pick, 2026-11-25 (by 12:41:29Z), verbatim:** "No trial now (Recommended)". Option 4 below is taken. The question put option 4 first as the controller's recommendation, against this spec's, on option 1's cost lines: its cell missed reading 10's own leg 1, it was chosen after trial 65's verdict was read, and an adopt could not be confirmed forward.

The owner's word takes a slot; what the slot buys is this decision. Three facts frame every option (measured): the 2013–2026 history has been searched by reading 10's 32 cells and read again by trial 65; the days after it are 210 returns on this workstation, on which only trial 1's own triple and the STH supply share's low band, held nine days in ten, have any event; and the ratified bar cannot be called on those days alone. **No option reads a clean day under a bar. The spec recommended spending the slot, on option 1, and laid out option 4 for the owner who reads option 1's cost lines as not worth a branch.**

1. **The veto on reading 10's two frozen sets, whole** — the spec's recommendation.
   - **Hypothesis and arms**: the section above — arm A the sleeve, arm B the sleeve with each long asset held flat for 7 closes after a low-band close.
   - **Data**: `--dataset btc-onchain-20261124T162656Z`, no `--window`, no `--as-of`, `ohlc-full` read by name beside it through `_c3_reads` unchanged: reading 10's invocation and trial 65's, the block `19ee5c23…74f7a` (measured).
   - **Bar**: trial 1's, whole — arm A's bar at the pre-flight, `a1_kill_bar` on arm B against record 33's frozen daily benchmark over 4,581 returns, the head-to-head against arm A from return index 335 over 4,246, the drawdown pair.
   - **Why this test**: the gate can do two things with an on-chain band, spec 00164 D12's leg 3 — re-enter where the sleeve is flat, veto or de-risk where it is long. Trial 65 read the first, on the reading's one cell with potential. The second is unread in book form, and of the ten long-state cells the reading's floor admits, four name a de-risk and one of the four also holds legs 2 and 4: `asopr|low|long|H7` — the same feature and tail as trial 1's, in the sleeve's other state, at the same horizon. With it C3's two records read both of the gate's actions on the one band that showed anything.
   - **Why these days**: the days after hold no event of this cell — 0 of the 210 — so the rolling set as held here would add 210 returns over which arm B is arm A, and move the block and every anchor off reading 10's and trial 65's for nothing read.
   - **What a verdict changes**: a **reject** or a **park** leaves C3's family call with both actions read as books and neither separated from the sleeve; an **adopt** is recorded, never deployed, and cannot be confirmed forward on any horizon this project plans on — the cell fires 3.43 closes a year.
   - **Cost, stated whole**: every return the verdict reads lies in the history the cell was searched on, and the cell missed that search's own leg 1 — its far bounds, -0.1604681447398037 to 0.013083631878674538, include 0 — so the trial stands on the owner's pick here, not on the reading's criterion, and the cell was chosen from the reading's table after trial 65's verdict was read. The books differ at 175 of 4,581 closes, in 24 episodes; the inferred reach says a significant head-to-head needs the removed exposure to have lost about 4.3 % over 7 closes. The same treatment has been rejected five times on another book (records 51–54, 57). A reject or a park is the likely verdict.
2. **The same veto on `ohlc-rolling` as of a later head** — B4 trial 2's instrument (spec 00146 D2, D6).
   - **Hypothesis, arms, bar**: option 1's, the returns running to the as-of day; the returns from index 4581 read apart beside the matrix — `unseen_returns`, `head_to_head_mean_outperf_unseen`, `head_to_head_spa_p_unseen` — in no leg, the spent holdout's window inside them read under `[iter-176]` and never reported as holdout or out-of-sample evidence.
   - **Data**: the snapshot and `ohlc-rolling` as of a named day after 2026-10-27, which this workstation does not hold: a `zcrypto data fetch` before the plan, the owner's, and for any decision after 2026-11-24's, which reads the snapshot's last day, a later snapshot, the owner's freeze — a row whose day the snapshot lacks reads no band and fires nothing, silently, so the trial's reads would have to refuse one.
   - **What it could add**: as of the head here, nothing — the cell has no event on the 210 (measured). A later head reaches aSOPR's 8 low days of 2026-11-13 → 11-23; if the sleeve is still long there they are the cell's first events since 2024, one episode against the 24 in sample (*Not measured*).
   - **Cost**: a host action before a premise can be measured; one episode spent as a no-leg glimpse where option 1 leaves it unread for a later read under its own criterion; `research eval` refuses `--as-of` beside a frozen `--dataset` and `_c3_reads` names `ohlc-full` (measured), so the trial takes the rolling set as its dataset and reads the snapshot by name through a reads function of its own; the block, the anchors against record 65 over the shared span, and every data-gated literal move; and arm A's bar and the kill bar read the adopted sleeve's own returns through the spent window and on to the head.
3. **Trial 1's rule again, on the days after the history alone** — the one instrument with no contamination.
   - **Hypothesis and arms**: trial 1's, unchanged (`_c3_reentry_inputs` runs on the rolling grid as it stands, measured); **data**: the snapshot and `ohlc-rolling` as of 2026-10-27, read from return index 4581.
   - **Bar**: none that is ratified. `a1_kill_bar` refuses the span, its every return in a stub year; the DSR leg alone would ask an annualised 2.1808 over 210 returns, which a book as good as the sleeve shows with probability 0.272; the head-to-head would read 50 differing closes, 14 of them outside the spent window, which `[iter-176]` bars from being reported as out-of-sample (measured).
   - **What a verdict changes**: nothing a matrix can state — a bar invented for 210 returns, on a rule already rejected, and the only clean days this cell has spent. The days after carry the DSR leg at even odds in 1.42 years and with probability 0.8 in 3.25.
4. **No trial: the slot stays unspent.**
   - Bucket C stays at 1 of 10. The on-chain writer adds a day a day whatever is decided, so the clean days accrue at no cost and can be read under their own spec when they can carry a bar.
   - This spec then ends here: its measured basis goes into T0228's findings — the days after the history and what they hold — and C3's next step is asked of the owner again.
   - **Why it is not the recommendation**: the slot is one of nine that no other family can spend — C1 and C2 closed at iter-197 on no-slot readings and C3 is bucket C's last family (T0016) — and option 1 is the one test left that the reading's own table supports in the long state; without it the family call is taken with one of the gate's two actions never read as a book. **Why it is offered**: every cost line under option 1.

Not offered: a trial registered now and run when the chain has grown — the veto's cell fires in 1.91 episodes a year, so its branch would stay open for years; any of the ten flat-state cells that hold legs 2–4 without leg 1 — a second try at the action records 55, 56 and 65 rejected, each on a cell that missed the leg trial 65's cell held; the STH supply share's low band — low on 188 of the 210 newest days, both its long-state cells missing leg 4; and a composite or a new feature — looks reading 10 never made, which belong to a reading before a trial. `ohlc-holdout-2026-07-10` is no option under any: its one look was spent on 2026-07-10, and `[iter-176]` admits its window only through `ohlc-rolling`.

## The owner's picks

- **D1**, 2026-11-25 (by 12:41:29Z), verbatim: "No trial now (Recommended)" — option 4.
- **C3's next step after it**, asked as option 4 says, 2026-11-25 (by 12:43:16Z), verbatim: "Hold, dated trigger (Recommended)" — C3 stays open and spends no slot; T0228's and T0016's trigger becomes the date 2027-09-01, when the returns past `ohlc-full`'s last close reach the 519 the measured basis gives the DSR leg at even odds, and the days after the history are read then under their own spec; the on-chain writer runs on as deployed. The options beside it were C3's close, T0016's Glassnode step and LTC and DOGE.
- **The hold's date, corrected after the branch review**, 2026-11-25 (by 13:05:41Z), verbatim: "2027-12-13, clean days (Recommended)" — the trigger is 2027-12-13, when 522 daily returns after the spent holdout's window carry the DSR leg at even odds at the sleeve's Sharpe.
- All three are entered in the phase-4 decisions log as `[iter-211]` entries.
