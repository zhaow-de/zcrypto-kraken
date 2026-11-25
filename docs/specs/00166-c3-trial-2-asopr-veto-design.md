# C3 trial 2 — aSOPR's low tail as a veto on the A1 sleeve's long state, the gate's one action trial 1 left unread, pre-registered on the sets reading 10 read; the days after that history hold no event of it

Iteration `iter-211`, branch `feat/iter-211-c3-trial-2`, cut from `develop` at `1a4abc4f5` (the merge of #895), written 2026-11-25 on `zcrypto-ops`; bucket C family C3 (`docs/research/00.master-plan.md` §5), topics [T0228](../open-topics/T0228-btc-on-chain-metrics-computed-from-chain-data.md) and [T0016](../open-topics/T0016-bucket-b-c-alpha-families.md).
**The owner's pick**, verbatim, as the decisions log holds it in `[iter-211] C3's next step after trial 1 — the owner's pick after registry trial 65 (Decision: 1)`: "merge it once CI is green, then take a slot in C-budget for one more trial" (received by 2026-11-25T10:20:39Z); and on who writes this spec and its plan: "for the trial 2 spec and plan, we use the trial agent strategy. i.e. take Fable for authoring the two docs, and all the rest, incl. reviewers and fixers stay with Opus." (received by 2026-11-25T10:24:34Z).
Settled by that pick, by spec 00133 and by trial 1's branch: the family key `C3` in bucket C, the count 2 and the slot rule — D2.
**Ruled: D1's option 4, no trial.** D1 was put to the owner first, and their pick, quoted at D1's head, leaves the slot unspent: no trial registers under this spec, its sha256 is never taken, and D5, D6, D7, D9, D11 and D14 are moot and were not asked. D2–D4, D8, D10, D12, D13 and the hypothesis stand as written at D1's option 1 — the record of what the trial would have been; the measured basis is what the decision rests on, and C3's next step is the owner's second pick under `## The owner's picks`.

## Intent

Trial 1 turned the one cell reading 10 found with potential into a book and registry trial 65 rejected it: the A1 sleeve with a long re-entry under aSOPR's low tail passed the kill bar and lost to the sleeve alone, `head_to_head_mean_outperf_primary` -2.0291967351609812e-05 a close at `head_to_head_spa_p_primary` 0.6786606696651675, its drawdown past the adopt bound beside it (`max_drawdown_reduction_pct` -57.325247779115955) — the `[iter-210] Verdict — C3 trial 1 REJECT (registry trial 65, family C3 n=1)` entry, which also says where that reject lies: inside reading 10's own search, every return of it on the history the sleeve was designed and adopted on.
The owner's pick spends a second C slot, and this spec's first duty is to show what the slot can buy, on measurement.
**The days after that history cannot carry a trial.** `ohlc-rolling` as this workstation holds it adds 210 daily returns past `ohlc-full`'s last close, 100 of them inside the spent holdout's window; over them MVRV and MVRV-Z never leave their middle band, the STH supply share sits in its low band nine days in ten, aSOPR is in its low band on 11 days, all with the sleeve flat, and the ratified bar cannot be called on a span that lies wholly in 2026, a stub year its worst-slice leg drops (the measured basis).
**So the trial this spec recommends is a second in-sample one, and it says so**: the gate's other action on the same band — a veto where the sleeve is long — on `asopr|low|long|H7`, the one long-state cell of reading 10 that holds its legs 2, 3 and 4 and misses leg 1; and D1 lays beside it the same veto on a later rolling head, trial 1's rule on the days after alone, and no trial at all.
It is research: nothing ships to a host, no value it writes feeds the engine, and an adopt is recorded, never deployed (D14).

**Where this spec departs from spec 00165's form**, its closest precedent: the first open decision is the trial itself, where trial 1's cell was named by the reading's criterion; the cell is one that criterion did not name (D8, D9); the family key exists and the count is 2 (D2); arm A is anchored to the last digit by record 65's stored figures, where trial 1 had none (D4, D13); the action removes exposure, so there is no size to choose and the depth is the open choice (D5); the basis measures the days after the history on `ohlc-rolling`, positions and counts alone; and every replay, regression and data-gated case it names reads only sets this branch links (D13).

## The measured basis

Every figure below was measured on 2026-11-25 in this branch's worktree at `2b6ad261d`, with the trial's code absent — the six test cases between 11:50:26Z and 11:51:32Z, the five programs between 11:52:11Z and 11:52:57Z, the shell checks at 11:52:57Z, the arithmetic over their printed figures after them — with `data/btc-onchain-20261124T162656Z`, `data/ohlc-full` and `data/ohlc-rolling` symlinked from the main checkout's `data/`, read and never written; `data/` in this worktree holds those three names and no other, and no `ohlc-holdout-*` path is read, listed or opened by any program or check below.
The programs read closes, weights, positions, bands, states, counts, exposure and turnover only: **no forward return, no net-of-cost series, no Sharpe and no statistic of any candidate rule's outcome is computed, on any span** — of the veto, of trial 1's rule on the days after, or of arm A over any subset of closes.
The six test cases rebuild reading 10's and trial 65's stored figures and record 33's benchmark and hold each equal to its entry; they pass or fail, and no figure of theirs is printed or read here.
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

The replays and regressions the run leans on (D13), on this tip's tree, clean:

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
- **The four books** — two depths (D5) by two hold rules (D6), each against arm A, whose turnover is 46.72757036801258, largest gross 0.764856, long asset-closes 14,110 and exposure held 547.632244 asset-closes of NAV:
  - **Flat, through 7 closes** — 688 asset-closes long in arm A and smaller in arm B, in 97 entries, 7.1 closes an entry; the books differ at 175 closes, first at return index 335 (close 2014-08-16), 4,246 returns from it; turnover 50.32075233684487, 3.5931819688322904 over arm A; exposure removed 25.814714 asset-closes of NAV, 0.037521 a vetoed asset-close.
  - **Flat, closed where the sleeve turns flat** — 683 asset-closes in 95 entries, the same 175 closes; turnover 50.32733538613031; it differs from the first at 5 asset-closes.
  - **Halved, through 7 closes** — the same 688 asset-closes, 97 entries and 175 closes; turnover 48.24420880711928, 1.5166384391066998 over arm A; exposure removed 12.907357.
  - **Halved, closed where the sleeve turns flat** — 683 asset-closes in 95 entries; turnover 48.247500331762.
  - In all four no position of arm B is below 0 or above arm A's, so arm B's largest gross is arm A's.
- **The recommended book's engagement** — the plan's data-gated literals. `veto_first_engaged` 335, `primary_returns` 4246, `stamps_positions_differ` 175, `veto_entries` 97, `turnover_b` 50.32075233684487, `exposure_removed` 25.814713828926113; `events_per_year` 2014 1, 2015 11, 2016 6, 2017 7, 2018 20, 2019 21, 2020 15, 2021 43, 2023 50, 2024 2, summing to 176; `vetoed_per_year` 2014 3, 2015 71, 2016 21, 2017 44, 2018 49, 2019 124, 2020 35, 2021 93, 2023 244, 2024 4, summing to 688; `positions_differ_per_year` 2014 3, 2015 32, 2016 8, 2017 14, 2018 29, 2019 31, 2020 9, 2021 16, 2023 31, 2024 2; a year one of these lists leaves out counts 0 there, each per-year key carrying every year the closes span. Per asset the vetoed closes are ADA 53, AVAX 23, BTC 134, DOGE 25, DOT 29, ETH 143, LINK 57, LTC 120, SOL 40, XRP 64. Arm B is arm A to the bit before return index 335. At 163 of the 175 closes arm B holds nothing while arm A holds its book, and at the other 12 a veto is open while arm B still holds another asset. Of the 844 asset-closes inside an event's 7 closes the sleeve is itself flat at 156; no event's 7 closes run past the set's last return.
- **The hurdle**, from positions alone: the added trading costs 3.5931819688322904 × 0.006 = 0.021559091812993744 of NAV over the window, 5.077506314883124e-06 a bar from the first engagement, so the veto pays only if the exposure it removes carried a mean asset return below −0.083515 % a close, −0.5846 % over 7 closes. Halved, the break-even is −0.070501 % a close. The veto removes 4.71 % of the sleeve's exposure, 4.88 % of its long asset-closes, at 3.82 % of the closes.
- **The head-to-head's reach — inferred from counts and a design constant, no series read.** At 163 of the 175 differing closes arm B holds nothing, so the difference a close is, to first order, minus the sleeve's own return there, a book the sleeve sizes to 0.12 / √365 = 0.006281 a close. Were the 175 closes independent their summed difference would carry a standard error near 0.0831 of NAV, so a one-sided 5 % read needs the veto to have saved about 0.137 of NAV and, with its trading, the removed exposure to have lost about 0.158: −0.613 % a removed asset-close, −4.29 % over 7 closes. The closes fall in 24 episodes and are not independent, so the reach is shorter than that. Reading 10's row for the cell gives a summed mean after the events of -0.016629646555238572 over 7 closes, pooled over events of equal weight — another object, as trial 1 showed, whose pooled 0.030735850910887732 became a negative head-to-head.
- **The count.** The registry's 65 records carry seven family keys; bucket C holds one record, trial 65, family C3, `n_trials_in_family` 1, its `attempt.counted` empty; no reading carries an attempt; one registered subject declares C3, `c3-asopr-reentry` at count 1. So `required_n("C3")` (`cli/registry/attempts.py:496-498`) is 1 record + the log's C3 orphans + 1: 2 unless the log holds an orphan (*Not measured*), and bucket C has spent 1 of 10.
- **The names.** No registered or retired subject's name equals `c3-asopr-veto` or `c3-asopr-veto-preflight` or opens either with a hyphen, and neither opens one; no record's variant is `C3-asopr-veto-a1lf-full-v1`.
- **Record 65's anchors for arm A and the benchmark**, read from its line: `arm_a_ann_sharpe_noc` 1.3797535717347145, `arm_a_ann_sharpe_noc_decisive` 1.4159389071170758, `arm_a_max_drawdown` 0.15777579530839503, `turnover_a` 46.72757036801258, `arm_a_passes` 1, `benchmark_ann_sharpe_noc` 1.245474508086168, `benchmark_ann_sharpe_noc_decisive` 1.2781056074367316; and from its notes' pre-flight clause, `arm_a_spot_drag_pct_yr` 0.022338655120267965 and arm A's bar's `dsr` 0.9999994726590977 and SPA p 0.0069965017491254375.
- **Trial 65 and reading 10 are frozen**: spec 00165's sha256 is trial 65's `spec_hash` and spec 00164's is reading 10's; neither file is edited.
- **The code path since trial 65's run** at `d308b687c`, an ancestor of this branch's tip: the log to the tip prints nothing, so the reads, the sleeve, the bands, the states, the costing and the bar this trial reuses are the ones trial 65 ran — and trial 65's replay, reading 10's, the two basis files' three cases and record 33's regression pass on this tip, 6 cases in 65.38 s, reading `btc-onchain-20261124T162656Z` and `ohlc-full` and no other set.
- **The tier**: the plan's files review at `full`, on the two tests that import the registry and the alpha package.
- **The triggers**: the decisions log holds one entry matching `C3.s next step after trial 1`, the `[iter-211]` one, so T0228's and T0016's `ripe_when` have fired; it holds none matching `C3.s next step after trial 2`.
- **Two lines D1's option 2 rests on**: `research eval` refuses `--as-of` beside a frozen `--dataset` (`cli/research/command.py:391`), and `_c3_reads` names `ohlc-full` (`cli/research/subjects.py:5209`).

Read from the tree, each by its path:

- **The sleeve in code**: `cli/alpha/c3.py`'s `a1_daily_positions`, records 44's and 47's A1 rows before their 4h expansion, held equal to `build_crossfreq_system(…).sleeve_positions["A1"]` by `tests/test_alpha_c3.py::test_the_arm_expands_to_the_builders_a1_sleeve`; its states by `states`, the cell's flag by `flags`.
- **Trial 1's bar in code**: `cli/research/subjects.py`'s `_c3_reentry_net` (`:5389`), `_c3_reentry_bar` (`:5393`), `_c3_reentry_benchmark` (`:5412`) and `_c3_reentry_arm_a_bar` (`:5417`), which read `returns`, `daily_ts`, `daily_prices` and `arm_a` of their inputs and nothing else; `_C3_REENTRY_DECISIVE_START` 230, `_C3_REENTRY_BLOCKS` (17, 102), `_C3_REENTRY_SEEDS` (42, 7, 1234), `_N_RESAMPLES` 2000, `_B2_COST_PER_SIDE` 0.006.
- **A scaled book in code**: `cli/alpha/b2.py:671`'s `scale_positions`, `p * s` per asset and row, which B2's de-risk overlays ran through.
- **The registry's priors on the two treatments**: five de-risk overlays on the A2-4h ensemble at half depth, records 51–54 and 57, all REJECT, read under spec 00128's matrix and spec 00138 D8's form of it (`_b2_verdict`, `cli/research/subjects.py:615`, for record 51 and `_b2_overlay_verdict`, `:2496`, for the four others: an adopt or a park needs a positive head-to-head and `max_drawdown_reduction_pct` above 1e-6); three re-entries, records 55 and 56 on that ensemble and 65 on this sleeve, all REJECT, read under spec 00139 D5's (`_b2_reentry_verdict`, `:2906`, and `_c3_asopr_reentry_verdict`, `:5548`).
- **The budget in code**: `BUCKET_OF` holds `"C3": "C"` and `BUDGET["C"]` is 10 (`cli/registry/budget.py:6-7`); `tests/test_trial_registry_provenance.py` holds `LANDED_N_TRIALS` at `:40` and asserts it at `:979`, `c3-asopr-reentry` at 1.
- **The two rulings binding every C pre-registration** (`[iter-176]`, T0016's findings): the DSR leg binds at every `n_trials`, `var_trials` 0.0 included; and a search may read the spent holdout's window, 2026-04-01 → 2026-07-09, through `ohlc-rolling`, but no result there is reported as holdout or out-of-sample evidence.
- **A reading's nearest cell has been tried once on the owner's word before**: B4 trial 2 (spec 00146; `[iter-190]`, "one more trail on B4, then move on"), a cell its reading's criterion did not name, judged at the matrix's 0.05 on `ohlc-rolling` with its unseen months read beside the matrix in no leg, PARK, registry trial 59.
- **T0123's trigger** reads any ADOPT past trial 63 on a book other than record 47's (`docs/open-topics/T0123-sleeve-promotion-path.md`'s `ripe_when`).

**Not measured — each a premise the plan reads before it is relied on:**

- **Any return of arm B, and any return of arm A, the benchmark or an asset over the vetoed closes or the event closes** — the veto's result under another name. Arm A's and the benchmark's figures over the whole window are record 65's, replayed and not re-read; arm B's are the trial's one run's (D13).
- **The sleeve's state on the snapshot's 29 days past the rolling head**, and so whether aSOPR's 8 low days of November 2026 are events of this cell, of trial 1's, or of neither: it takes a head past 2026-10-27, a `zcrypto data fetch`, the owner's. Only D1's option 2 rests on it.
- **The trial-attempts log.** It lives in the main checkout's `.local/` and is not read here; the plan's count program reads `required_n("C3")` and bucket C's spent figure through `attempts.reconcile` before its review.
- **The head-to-head's variance.** The reach above is inferred from the vol target; the series is not read.
- **The run's time.** The reads and the inputs half take 8.2 s; trial 65's replay ran inside the 65.38 s the six cases took together; the plan times the pre-flight.
- **Whether BRK's aSOPR of day D reads a block after D's last** is spec 00164 D3's premise, on which reading 10 and trial 65 rest; it is relied on as they relied on it.

## Operating model

- **Sessions.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial is written, planned and run under one, the session holding this branch's worktree, `.claude/worktrees/c3-trial-2`. On the owner's word quoted in the head, the spec and the plan are authored by Claude Fable 5.2 and every other agent — implementers, reviewers, fixers — runs on Opus; a second writer never works in the worktree while one is in it.
- **One machine.** `zcrypto-ops` (`hostname`, measured), the research workstation and the venue-facing ops node at once. No session runs a play, a converge, `ssh`, `docker` or a `zcrypto data fetch` for this trial under D1's option 1: it touches no host and reads no network.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives.
- **What else runs on the host and what it shares with the trial: nothing the trial reads.** The on-chain writer (`zcrypto-onchain-write.timer`, hourly) extends the live vintage chain under the ops data root; the trial reads the frozen snapshot under `data/`, written once by `onchain freeze`, identified by its file's bytes and its manifest's set hash. `data/ohlc-full` is a frozen, attested set. `data/ohlc-rolling` is a chained mirror that a fetch extends by whole lines; it is linked here for the basis alone, read as of 2026-10-27, a read a later line cannot change, and the trial does not read it under option 1. All three are symlinks from this worktree into the main checkout's `data/`; a run writes nothing under any, and each link is unlinked before `git worktree remove`.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1), its id `60c9f39c37ec81b4a53396218b690304` listed for `zcrypto-ops` in `docs/reference/trial-attempt-logs.txt` (measured); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained. An append chains onto develop's last line, which D13's develop check holds before the run; `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and its `LANDED_N_TRIALS` row before anything else lands.

## Hypothesis (trial 2, pre-registered by this spec's sha256)

C3's one question is "marginal value inside the A1 gate" (`00.master-plan.md` §5): coins moved at a loss, read on-chain a day late, mark closes after which the assets the sleeve holds long go on to do worse than after its other long closes, so **the A1 sleeve as records 44 and 47 build it, with every asset it holds long at a daily close where the previous UTC day's aSOPR lies at or below the 10th percentile of its own history from 2011-01-01, read after 365 values, held flat through 7 daily closes counted from the last such close, has a higher mean net-of-cost return than the sleeve alone from the first close the two books differ, net of each asset's own turnover at 0.006 a side.**
Arm A is the sleeve exactly as reading 10 and trial 65 read it; arm B never holds more than arm A in any asset, is long-only and borrows nothing.
It is judged by D11's matrix on its own record; what its verdict changes is D14's.
The statement is written at D1's option 1 and at the options of D5, D6 and D7 marked Recommended. At D1's option 2 it is unchanged and its returns run to the as-of day; at option 3 the hypothesis is trial 1's own, word for word, read from return index 4581; at option 4 none is registered.

## D1 — what trial 2 tests, and on which days (the owner's)

**The owner's pick, 2026-11-25 (by 12:41:29Z), verbatim:** "No trial now (Recommended)". Option 4 below is taken. The question put option 4 first as the controller's recommendation, against this spec's, on option 1's cost lines: its cell missed reading 10's own leg 1, it was chosen after trial 65's verdict was read, and an adopt could not be confirmed forward.

The owner's word takes a slot; what the slot buys is this decision. Three facts frame every option (measured): the 2013–2026 history has been searched by reading 10's 32 cells and read again by trial 65; the days after it are 210 returns on this workstation, on which only trial 1's own triple and the STH supply share's low band, held nine days in ten, have any event; and the ratified bar cannot be called on those days alone. **No option reads a clean day under a bar. The spec recommends spending the slot, on option 1, and lays out option 4 for the owner who reads option 1's cost lines as not worth a branch.**

1. **The veto on reading 10's two frozen sets, whole** — **Recommended**.
   - **Hypothesis and arms**: the section above — arm A the sleeve, arm B the sleeve with each long asset held flat for 7 closes after a low-band close (D3–D6).
   - **Data**: `--dataset btc-onchain-20261124T162656Z`, no `--window`, no `--as-of`, `ohlc-full` read by name beside it through `_c3_reads` unchanged: reading 10's invocation and trial 65's, the block `19ee5c23…74f7a` (measured).
   - **Bar**: trial 1's, whole — arm A's bar at the pre-flight, `a1_kill_bar` on arm B against record 33's frozen daily benchmark over 4,581 returns, the head-to-head against arm A from return index 335 over 4,246, the drawdown pair (D10, D11).
   - **Why this test**: the gate can do two things with an on-chain band, spec 00164 D12's leg 3 — re-enter where the sleeve is flat, veto or de-risk where it is long. Trial 65 read the first, on the reading's one cell with potential. The second is unread in book form, and of the ten long-state cells the reading's floor admits, four name a de-risk and one of the four also holds legs 2 and 4: `asopr|low|long|H7` — the same feature and tail as trial 1's, in the sleeve's other state, at the same horizon. With it C3's two records read both of the gate's actions on the one band that showed anything.
   - **Why these days**: the days after hold no event of this cell — 0 of the 210 — so the rolling set as held here would add 210 returns over which arm B is arm A, and move the block and every anchor off reading 10's and trial 65's for nothing read.
   - **What a verdict changes**: a **reject** or a **park** leaves C3's family call with both actions read as books and neither separated from the sleeve; an **adopt** is recorded, never deployed, and cannot be confirmed forward on any horizon this project plans on — the cell fires 3.43 closes a year (D14).
   - **Cost, stated whole**: every return the verdict reads lies in the history the cell was searched on, and the cell missed that search's own leg 1 — its far bounds, -0.1604681447398037 to 0.013083631878674538, include 0 — so the trial stands on the owner's pick here, not on the reading's criterion, and the cell was chosen from the reading's table after trial 65's verdict was read (D8). The books differ at 175 of 4,581 closes, in 24 episodes; the inferred reach says a significant head-to-head needs the removed exposure to have lost about 4.3 % over 7 closes. The same treatment has been rejected five times on another book (records 51–54, 57). A reject or a park is the likely verdict.
2. **The same veto on `ohlc-rolling` as of a later head** — B4 trial 2's instrument (spec 00146 D2, D6).
   - **Hypothesis, arms, bar**: option 1's, the returns running to the as-of day; the returns from index 4581 read apart beside the matrix — `unseen_returns`, `head_to_head_mean_outperf_unseen`, `head_to_head_spa_p_unseen` — in no leg, the spent holdout's window inside them read under `[iter-176]` and never reported as holdout or out-of-sample evidence.
   - **Data**: the snapshot and `ohlc-rolling` as of a named day after 2026-10-27, which this workstation does not hold: a `zcrypto data fetch` before the plan, the owner's, and for any decision after 2026-11-24's, which reads the snapshot's last day, a later snapshot, the owner's freeze — a row whose day the snapshot lacks reads no band and fires nothing, silently, so the trial's reads would have to refuse one.
   - **What it could add**: as of the head here, nothing — the cell has no event on the 210 (measured). A later head reaches aSOPR's 8 low days of 2026-11-13 → 11-23; if the sleeve is still long there they are the cell's first events since 2024, one episode against the 24 in sample (*Not measured*).
   - **Cost**: a host action before a premise can be measured; one episode spent as a no-leg glimpse where option 1 leaves it unread for a later read under its own criterion; `research eval` refuses `--as-of` beside a frozen `--dataset` and `_c3_reads` names `ohlc-full` (measured), so the trial takes the rolling set as its dataset and reads the snapshot by name through a reads function of its own; the block, the anchors against record 65 over the shared span, and every data-gated literal move; and arm A's bar and the kill bar read the adopted sleeve's own returns through the spent window and on to the head.
3. **Trial 1's rule again, on the days after the history alone** — the one instrument with no contamination.
   - **Hypothesis and arms**: trial 1's, unchanged (`_c3_reentry_inputs` runs on the rolling grid as it stands, measured); **data**: the snapshot and `ohlc-rolling` as of 2026-10-27, read from return index 4581.
   - **Bar**: none that is ratified. `a1_kill_bar` refuses the span, its every return in a stub year; the DSR leg alone would ask an annualised 2.1808 over 210 returns, which a book as good as the sleeve shows with probability 0.272; the head-to-head would read 50 differing closes, 14 of them outside the spent window, which `[iter-176]` bars from being reported as out-of-sample (measured).
   - **What a verdict changes**: nothing a matrix can state — a bar invented for 210 returns, on a rule already rejected, and the only clean days this cell has spent. At 24.64 event closes a year the days after carry the DSR leg at even odds in 1.42 years and with probability 0.8 in 3.25.
4. **No trial: the slot stays unspent.**
   - C3's family call is taken on reading 10 and trial 65; bucket C stays at 1 of 10. The on-chain writer adds a day a day whatever is decided, so the clean days accrue at no cost and can be read under their own spec when they can carry a bar.
   - This spec then ends here: its measured basis goes into T0228's findings — the days after the history and what they hold — and C3's next step is asked of the owner again among the `[iter-211]` entry's other options.
   - **Why it is not the recommendation**: the slot is one of nine that no other family can spend — C1 and C2 closed at iter-197 on no-slot readings and C3 is bucket C's last family (T0016) — and option 1 is the one test left that the reading's own table supports in the long state; without it the family call is taken with one of the gate's two actions never read as a book. **Why it is offered**: every cost line under option 1.

Not offered: a trial registered now and run when the chain has grown — the veto's cell fires in 1.91 episodes a year, so its branch would stay open for years; any of the ten flat-state cells that hold legs 2–4 without leg 1 — a second try at the action records 55, 56 and 65 rejected, each on a cell that missed the leg trial 65's cell held; the STH supply share's low band — low on 188 of the 210 newest days, both its long-state cells missing leg 4; and a composite or a new feature — looks reading 10 never made, which belong to a reading before a trial. `ohlc-holdout-2026-07-10` is no option under any: its one look was spent on 2026-07-10, and `[iter-176]` admits its window only through `ohlc-rolling`.

## D2 — the family key `C3`, the slot and the count (settled)

- `BUCKET_OF` holds `"C3": "C"` since trial 1's branch (`cli/registry/budget.py:6`, measured; spec 00165 D2, on spec 00164 D12 and spec 00133 D5); `BUDGET` is unchanged, and no file under `cli/registry/` changes.
- **The slot**: the landed record spends the second of bucket C's 10 (`BUDGET["C"]`, one spent, measured); a stop, a refused build or a refusal from the count spends none (spec 00133 D4, D7).
- **The count is 2**, `_C3_ASOPR_VETO_N_TRIALS`: C3's true count with this trial, `required_n("C3")` = 1 record + the log's C3 orphans + 1 — the record measured, the orphans expected 0 since record 65 counted none, and read from the log by the plan before its review. Fixed by this spec's hash, never raised in place: spec 00133 D4 refuses a declared count below `required_n`, so a C3 attempt landing elsewhere before this run refuses it, and the trial goes back to the owner through T0228 — a further count is a new subject under a new spec.

## D3 — the trigger: the cell's, every constant reading 10's (settled by reading 10, at D1's option 1)

- **An event** is an asset-close at which the cell's flag is set: at union return index `k` for asset `a`, `alpha_c3.flags(bands["asopr"], states[a], tail="low", in_state="long")[k] is True` — the sleeve's position in `a` at `k` is above 0, `a` has a close at `k`, and the snapshot's `asopr` of day `ts[k] − 1 day` is in its low band.
- **The band** is reading 10's and trial 1's: the day's expanding-percentile rank among its own history from 2011-01-01 at or below 0.10, read once 365 values exist, a day holding a value only where its aSOPR is finite and BRK's price that day is finite and above 0 (`cli/alpha/c3.py`'s `LOW`, `MIN_HISTORY`, `LAG_DAYS`, `FIRST_DAY`, `bands`, `from_first_day`, `lagged`; spec 00164 D6, D7, D12). The lag is one day: the decision at bar `k`'s close, the 00:00Z that ends day `ts[k]`, reads day `ts[k] − 1 day`, closed and confirmed for most of a day.
- **The state is arm A's, never arm B's**: an event is read off the sleeve's own position, so a veto in force changes no later event.
- **The code is reading 10's, unchanged**: the trial's inputs call `_c3_reads` and `_c3_reading_inputs` and take `inputs.bands["asopr"]`, `inputs.states` and `inputs.positions` from them. A state of `None` — an asset with no close at `k` — fires nothing. Measured: 176 events at 43 closes.
- **The action and the horizon** are the cell's: spec 00164 D12's leg 3, "negative in the long state → a veto or de-risk", over 7 daily closes (`H7`). The cell's 30-close sibling holds legs 2 and 3 and misses leg 4; it is not this trial's.
- A band, a lag, a first day, a history length or a horizon changed after a result is a new trial.

## D4 — arm A: the sleeve as records 44 and 47 build it, anchored by record 65 (settled)

- **Arm A** is `alpha_c3.a1_daily_positions(daily_prices)` over the 4,581 completed returns, as spec 00165 D4 states it: reading 10's arm and trial 65's, the same function over the same bytes (measured: reading 10's `arm` and `counts` blocks).
- **Its returns are anchored to the last digit this time.** Record 65 stores arm A's net Sharpe, its decisive Sharpe, its maximum drawdown, its turnover and its bar's `passes`, and the benchmark's two Sharpes, and its notes hold the pre-flight's spot drag, `dsr` and SPA p (measured); trial 65's replay rebuilds the stored ones on this tip. This trial's pre-flight reads each equal to those figures, no tolerance (D13) — at count 2 arm A's `dsr` is its value at count 1 (measured).
- No change to `cli/alpha/a1.py`, `cli/alpha/c3.py`, `cli/alpha/c3_reentry.py`, `cli/portfolio/*` or any adopted artifact.

## D5 — the veto's depth (the owner's)

Reading 10's leg 3 names "a veto or de-risk" and fixes neither; the sleeve holds a position where the veto acts, so the choice is how much of it is given up, made here on positions and turnover alone.

1. **Flat: the vetoed asset's position is 0** — **Recommended**.
   - **Why**: it is the cell's own contrast — the forward after an event against holding nothing — with no constant chosen; and the head-to-head asks one question at any depth, whether the removed exposure lost more than its trading cost, which the full veto reads on twice the exposure the half reads it on.
   - **Measured**: 3.5931819688322904 of added turnover, 25.814714 asset-closes of NAV removed, a break-even of −0.083515 % a removed close; at 163 of the 175 differing closes the book is wholly in cash.
   - **Cost**: the dearer break-even of the two, and a book that is all or nothing on one daily value.
2. **Halved: the vetoed asset's position times 0.5** — `B2Config.derisk_scale`'s value, spec 00128 D3's, the depth records 51–54 and 57 ran at.
   - The registry's own de-risk constant. **Measured**: 1.5166384391066998 of added turnover, 12.907357 removed, a break-even of −0.070501 % a removed close — cheaper a unit removed. **Cost**: half the exposure under test on a rule that engages at 175 closes, and a constant taken from another book's overlay, where five trials at it were rejected.

## D6 — the hold (the owner's)

The cell fixes 7 closes; what it leaves open is what the veto does when events overlap and when the sleeve itself turns flat and long again inside a hold.

1. **Vetoed through 7 closes counted from the last event close, that close included, whatever the sleeve then does** — **Recommended**.
   - `veto_scales(fires, hold=7, depth=…)`, new: at return index `k` for asset `a` the scale is the depth where any of `fires[a][k − 6 … k]` is set, else 1.0; arm B is `scale_positions(arm_a, scales)` (`cli/alpha/b2.py:671`, unchanged). So an event at `k` vetoes the returns `k` … `k + 6`, the 7 closes the cell's forward ran over; events that overlap share one exit; and arm B is arm A to the bit wherever no veto is open, `p * 1.0` being `p`.
   - **Measured**: 688 vetoed asset-closes in 97 entries, 7.1 an entry; the sleeve is itself flat at 156 of the 844 asset-closes inside an event's 7 closes.
   - **Why**: it is the forward the cell read, which ran its 7 closes whatever the sleeve then did; the scale is a function of the events alone, and the position goes through a function the registry's de-risk records already ran.
2. **The same, closed where the sleeve itself turns flat** — spec 00139 D3's rule for a re-entry, mirrored: an asset the sleeve drops and takes up again inside the 7 closes comes back unvetoed.
   - **Measured**: it differs from option 1 at 5 asset-closes, 683 in 95 entries, turnover 50.32733538613031 against 50.32075233684487. **Cost**: a stateful loop for a difference of 5 asset-closes in 688.

Under either option each veto and each release is a trade charged on the position's change (D7).

## D7 — the grid and the bar's instrument (the owner's); the costing and §10 (settled by spec 00164 D12)

The owner picked the grid for trial 1 (`[iter-210] C3's trial 1 (spec 00165 D6)`, "Daily, record 34's bar (Recommended)"); that pick named trial 1, so it is asked again.

1. **The daily union, the bar record 34's, as trial 1** — **Recommended**. C3's two records are read on one bar; the block stays reading 10's and trial 65's; arm A's and the benchmark's figures are record 65's to the digit, which is what lets the pre-flight read them with no tolerance (D4, D13); every input of the rule is daily. **Cost**: spec 00165 D6's — a headline block of 17, the shorter of the two.
2. **The 4h union, the B families' bar** — both arms expanded on close-time boundaries, `ohlc-full`'s 240-minute files in the block, `decisive_start` 1380, blocks {30, 102}, 27,337 returns, 22,756 more than the daily grid's and none of those a close either book decides at (spec 00165 D6 and its basis, not re-read here). **Cost**: the block is no longer reading 10's or trial 65's, record 65 anchors nothing, and none of its premises is measured here.

At option 1:

- **The returns**: `_asset_returns(_ffill_btc(daily_prices)[a])` for each of the ten assets, 4,581 of them, 365 periods a year.
- **The benchmark**: `build_combined_system(daily_prices, config=_RECORD33_CONFIG).benchmark_net_of_cost`, record 33's frozen daily benchmark at 0.006 a side, through `_c3_reentry_benchmark` unchanged.
- **The bar's constants**: `decisive_start` 230, `mean_block` 17, `seed` 42, `n_resamples` 2000; the slices `calendar_year_slices(…, daily_ts)`, the stub years 2013 and 2026 out; the SPA grid blocks {17, 102} × seeds {42, 7, 1234}, the headline cell (17, 42), the five others recorded and never read.
- **The costing** is spec 00164 D12's "net of 0.006 a side on its own turnover": `net_of_cost(positions, returns, cost_per_side=0.006)` for both arms through `_c3_reentry_net` unchanged, and the kill bar's cost-stressed series at 1.5 ×, 0.009.
- **Long-only, nothing borrowed, no limit wired.** Arm A is `short="off"` and a scale lies in [0, 1], so no position of arm B is below 0 or above arm A's (measured: none), its gross never exceeds arm A's 0.7648558752122554 against §10's 1.5 cap, and no borrow-unavailable rung has anything to read. §10's per-asset caps stay off the sleeve as records 44 and 47 leave them (spec 00165 D9); the veto can only lower a position.

## D8 — the contamination, stated in full

- **The cell was searched for on the data the trial reads, and it missed that search's bar.** Reading 10 read 32 cells over the whole history the A1 sleeve was designed and adopted on; this trial reads that history again, block for block (measured). The cell's row is in the decisions log's table: 176 events against 13,930 others in 10 calendar years, difference -0.06256506879502982, far bounds -0.1604681447398037 to 0.013083631878674538, summed mean after the events -0.016629646555238572, legs 1–4 (False, True, True, True), potential False. No figure of it is recomputed or extended here.
- **The cell is not the reading's criterion's.** It is this spec's recommendation at D1 and the owner's pick once taken, as B4 trial 2's was (spec 00146 D7): chosen from that table after trial 65's verdict was read, as the one long-state cell holding legs 2–4.
- **Trial 1's result is known**: the re-entry on the same band lost to the sleeve. It says nothing direct about the long state — the two cells share no event, a state being one or the other — and it is why a pooled forward's size is no forecast of a book's (the measured basis).
- **The trial carries both ids**: reading 10, `record_hash` `ed1bb73e76e3ab32bfc8cbd72212522f571e7d388a096871eb9b0949c05c590c`, spec 00164 at `89eb8be96d6961b2f4c6240b6b6ce7a8a045768413f0a6087a810fe64067c86e`; and trial 65, `record_hash` `f0985286dbf5f3d638878975e5e3fa9803e47101ba34fa3dff4671bc873b11e3`, spec 00165 at `2aa047d9d9e3a87427b087a8d7c9079e4916ffa963a3394aaa5d1b9bf0b40aa1`; the record's notes name all four (D13).
- **Nothing of the trigger is chosen here.** The band, its history, the lag and the horizon are reading 10's constants.
- **The depth and the hold are chosen after the reading and after trial 65, on positions.** Their options were laid out on counts, exposure and turnover (the basis); this spec computed no return of a book carrying the veto, none is in the registry, the ledger or the tree, and the break-even and the reach are arithmetic on turnover, counts and the vol target.
- **The same treatment has been rejected five times on another book**: B2's de-risk overlays on the A2-4h ensemble, records 51–54 and 57, with other triggers at half depth. They are a prior the spec names, not evidence about this trigger.
- **The design-informed inputs spec 00164 D12 names stand**, as spec 00165 D10 lists them: BRK's prices and oracle, aSOPR's one-hour exclusion, the history's values one run's, and the first day, 2011-01-01.
- **The days after the history were counted, not read.** The basis holds their bands, the sleeve's states and positions and trial 1's positions on them; no return of any day after 2026-03-31 was computed, and under D1's option 1 the trial reads none.
- **The holdout is untouched** under option 1: `ohlc-full` ends 2026-03-31, and neither `ohlc-rolling` nor `ohlc-holdout-*` is read by the trial.

## D9 — how reading 10's looks and trial 1 enter the bar (the owner's)

Spec 00164 D12 says a trial the reading names "counts C3's true trials in its DSR with these 32 looks in its design". At `var_trials` 0.0, which `[iter-176]` binds, the count moves no number (measured). For trial 1 the owner took the matrix as ratified with the looks stated, on the ground that the cell had already cleared the reading's Bonferroni bounds (`[iter-210] C3's trial 1 (spec 00165 D11)`). **That ground does not carry**: this cell did not clear them.

1. **`n_trials` 2, `var_trials` 0.0, the matrix's legs as ratified at 0.05; the 32 looks, the missed leg 1 and trial 65 stated, in D8 and in the record's notes** — **Recommended**.
   - **Why**: it is what the registry did the one other time a cell outside its reading's criterion was tried on the owner's word — B4 trial 2, at 0.05, its contamination stated (spec 00146 D7, D8) — and a stricter threshold on a rule that engages at 175 closes makes an adopt unreachable and the slot a formality. What an adopt at 0.05 is worth is said where it is used: recorded, never deployed, in-sample (D14).
   - **Cost**: an adopt here is a nominal 5 % on one of 32 searched cells, read after a first trial; no number of the bar is harder for the search.
2. **The head-to-head's adopt threshold at 0.05 / 32** — adopt needs SPA p < 0.0015625 where the matrix reads 0.05, a park between the two; the head-to-head's `n_resamples` raised to 10,000 (spec 00165 D11's option 2).
   - The cell has to clear as a book the bar it missed as a contrast. **Cost**: a threshold no record of this registry was read at; with the inferred reach above, a verdict that can be a park or a reject and, short of a loss on the removed exposure several times the reading's, nothing else.

Not offered: a declared count of 34, which would change `n_trials_in_family` and no number of the bar; and a `var_trials` from the 32 cells' dispersion, which would take the net return of 32 rules to compute.

## D10 — the bar and the head-to-heads (settled by spec 00164 D12; the constants D7's)

- **The series**: `net_a`, `net_b` at 0.006 and `net_b_x15` at 0.009 (D7); `bench` D7's benchmark.
- **The bar**: `a1_kill_bar(net_b, bench, n_trials=2, var_trials=0.0, mean_block=17, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, daily_ts), benchmark_slices=calendar_year_slices(bench, daily_ts), decisive_start=230, n_resamples=2000)` through `_c3_reentry_bar` unchanged, the grid's other five cells recorded beside it. **Arm A's headline bar** is the same call on `net_a` and its own 0.009 series at (17, 42) through `_c3_reentry_arm_a_bar`, read `passes` 1 at the pre-flight, after the hash (D13).
- **The head-to-heads**: `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=17, seed=42, n_resamples=2000)`, primary from arm B's first engagement — `first` = `veto_first_engaged`, the first return index at which arm B's positions differ from arm A's, 335, `primary_returns` 4246 (measured) — and over the full window (`first` 0) beside it; keyed `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_full` and `head_to_head_spa_p_full`. Before the first engagement the two books are one to the bit (measured); the primary decides.
- **The drawdown pair**, from the same start: `max_drawdown(net_b[first:])`, `max_drawdown(net_a[first:])` and `max_drawdown_reduction_pct = 100 × (A − B) / A`; a negative reduction is arm B's drawdown above arm A's.
- **Refused before any bar**: fewer than 2 return indices from the first engagement, and an arm A that never draws down from it — each a `ValidationError`, and so a refused build.

## D11 — the matrix and its drawdown leg (the owner's)

The rows are trial 1's, the dead knob read off the veto's own engagement. What is open is the drawdown leg: trial 1's bound was set for an action that adds exposure, and the registry read its de-risk overlays under another.

1. **Trial 1's matrix whole: an adopt needs arm B's maximum drawdown from the head-to-head's start at most 1.2 × arm A's** — **Recommended**.
   - **Why**: the hypothesis is return, and C3's two records are then read under one rule, its function trial 1's with the dead-knob key renamed. A veto only removes exposure, so the bound binds only where skipping a recovery deepens the sleeve's drawdown by more than a fifth, and a veto that does that should park.
   - **Cost**: a lenient leg for a risk action — an adopt may leave the drawdown where it was, or a little deeper.
2. **Spec 00138 D8's de-risk leg** — an adopt or a park needs a positive head-to-head and `max_drawdown_reduction_pct` above 1e-6; anything else rejects (`_b2_overlay_verdict`, records 52–54 and 57; record 51 under spec 00128's own form of it).
   - The leg every de-risk record was read under: a de-risk that does not cut the drawdown is no de-risk. **Cost**: the maximum drawdown is one episode of the sleeve's, and the veto acts in 24; where none of them meets it the reduction is 0 to rounding and the verdict is a reject whatever the head-to-head says — the trial's answer would hang on a coincidence of dates the hypothesis does not speak to.
3. **No drawdown leg** — the pair recorded and never read. **Cost**: an adopt no row has checked for the one way a veto can hurt.

**The matrix**, at option 1 — rows disjoint and covering every outcome:

| Arm A's bar and the veto's engagement | Kill bar (B vs the frozen benchmark) | Head-to-head (B vs A, from arm B's first engagement) | Verdict |
| --- | --- | --- | --- |
| arm A's `passes` 0, or no asset-close vetoed (a dead knob) | any | any | **instrument finding**: no verdict, the slot unspent |
| arm A passes, the veto engaged | fail | any | **reject** |
| arm A passes, the veto engaged | pass | mean outperformance > 0, SPA p < 0.05, and B's maximum drawdown at most 1.2 × A's | **adopt** the veto |
| arm A passes, the veto engaged | pass | mean outperformance > 0, and SPA p ≥ 0.05 or B's maximum drawdown above 1.2 × A's | **park** |
| arm A passes, the veto engaged | pass | mean outperformance ≤ 0 | **reject** |

The first row's dead knob never reaches the rule on the trial's own build: with no asset-close vetoed the first engagement leaves no return index, which D10 refuses before any bar, and the pre-flight's (c) names it first (D13).
Every quantity the matrix reads is a stored key read unrounded: `arm_a_passes`, `vetoed_per_year`, `passes`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary` and `max_drawdown_reduction_pct`, the bound read as `max_drawdown_reduction_pct` ≥ −20.0, never as a ratio of the two stored drawdowns. The park row names no variant: what follows a verdict is D14's. The subject declares the rule (spec 00129 D4):

```python
def _c3_asopr_veto_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["vetoed_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        bounded = m["max_drawdown_reduction_pct"] >= -20.0
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 and bounded else "park"
    return "reject"
```

At option 2 the rule is `_b2_overlay_verdict`'s body with `vetoed_per_year` for its `engaged_per_year`; at option 3 it loses `bounded`; at D9's option 2 its `0.05` is `0.05 / 32`.

## D12 — the engagement, the subjects, their record and the build

- **The engagement**, ten keys from positions and events alone: `veto_first_engaged`, `primary_returns`, `stamps_positions_differ`, `positions_differ_per_year`, `events_per_year` (the cell's events per close year), `vetoed_per_year` (asset-closes long in arm A and smaller in arm B — the dead-knob read), `veto_entries`, `exposure_removed` (the sum over assets and closes of arm A's position less arm B's), `turnover_b` and `turnover_b_per_year`. Every year key is the close year, `daily_ts[k + 1].year`, the rule `calendar_year_slices` cuts the bar's slices by. Trial 1's `events_without_size` and `gross_max` have no counterpart: an event holds a position by its definition, and arm B's gross is bounded by arm A's.
- **The trial's 46 keys**: trial 1's 36 of the bar, the series and the drawdown pair (`_C3_REENTRY_METRIC_KEYS` less `_C3_REENTRY_ENGAGEMENT_KEYS`), unchanged in name and meaning, and the engagement's ten. **The pre-flight's 27**: the engagement's ten, arm A's and the benchmark's seven anchors (`arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`) and arm A's bar's ten (`_B2_ARM_A_BAR_KEYS`).
- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00166-c3-trial-2-asopr-veto-design.md"`, intervals `(1440,)`, assets `()` as trial 1's declare them: the trial `c3-asopr-veto` — `_build_c3_asopr_veto`, `metric_keys=_C3_VETO_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_c3_asopr_veto_verdict`, `no_verdict` "instrument finding: arm A fails the bar this window sets, or the veto flattens no asset at any close; no verdict, the trial unspent", `family="C3"`, `n_trials=_C3_ASOPR_VETO_N_TRIALS` — and its evaluate-only twin `c3-asopr-veto-preflight` — `_build_c3_asopr_veto_preflight`, `metric_keys=_C3_VETO_PREFLIGHT_KEYS`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). The twin costs arm A alone and reads no head-to-head; it builds arm B's positions, and its engagement reads them.
- **Author's call — the twin is kept though record 65 anchors arm A**: it is the one run of this trial's own build path over the real sets before the registered run, and its figures are read equal to record 65's, so a wiring fault shows as a stop that spends nothing.
- **Author's call — the names**: spec 00141 D2's rule holds for both (measured), and the `c3-asopr-` prefix sets the trial beside trial 1's; the variant is `C3-asopr-veto-a1lf-full-v1`, record 65's form.
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `C3`; `n_trials_in_family` 2; iteration `iter-211`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a`; `attempt` the trial-attempts log's; `notes` caller text written before the run (D13).
- **The build in three halves**, trial 1's form: `_c3_reads`, unchanged; `_c3_veto_inputs(snapshot, daily_ts, daily_prices)` — `_c3_reading_inputs` unchanged, then the events, the scales, arm B and the returns both arms are costed on, in a tuple of its own, `_C3VetoInputs`, and no net series of a book; `_c3_veto_metrics` — the nets, the benchmark, the bars, the head-to-heads and the keys — and `_c3_veto_preflight_metrics` — arm A's net, the benchmark, arm A's bar and the engagement. **Author's call**: the four helpers trial 1 added are called on that tuple unchanged, in body and signature, since each reads of its argument only fields both tuples carry (read from the tree), so the series trial 65's replay holds are the series this trial's bar reads.
- **The refusals**, each a `SubjectError` naming the subject or the file: `--as-of` and `--window`, before any read, in trial 1's words for its own; `_c3_reads`' own; D10's two; and any compute error (`EVALUATION_ERRORS`).
- **`cli/alpha/c3_veto.py`, new** — `veto_fires(band, states)`, the cell's flag as booleans per asset, and `veto_scales(fires, *, hold, depth)`, D6's scale, which refuses a hold below 1 and a depth outside [0, 1). The plan's tests hold it to known answers: a flag set only at a long close under a low band, none at a `None` state or a flat one; a scale of the depth at the event close and the 6 after it and 1.0 at the seventh; overlapping events sharing one exit; no close's scale reading a later close; an asset another's event does not touch.
- **The files the build touches, a closed list**: `cli/alpha/c3_veto.py`, new; `cli/research/subjects.py` — the import, one block before `SUBJECTS` (the constants, `_C3VetoInputs`, the inputs half, the computes, the shared build, the two builders, the rule and the key sets) and two `SUBJECTS` entries, no existing function changed; `README.md`'s `--subject` row; `tests/test_trial_registry_provenance.py` — after the run, the `LANDED_N_TRIALS` row in its two literals; `tests/test_research_command.py` — the subjects' contract fixtures; `tests/slow-cases.txt` — the ids of the new cases that take 10 s or more; the new tests the plan names; after the verdict, the two topics and their index (D14). No change to `cli/registry/*`, `cli/alpha/a1.py`, `cli/alpha/b2.py`, `cli/alpha/c3.py`, `cli/alpha/c3_reentry.py`, `cli/alpha/killbar.py`, `cli/portfolio/*`, `cli/onchain/*`, `cli/engine/*`, trial 1's or the reading's subjects, specs 00164 and 00165, any record, reading or adopted artifact, `zcrypto.toml`, or anything under `infra/`.

## D13 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the owner's picks quoted at D1, D5, D6, D7, D9, D11 and D14; the plan review closed; the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important; nothing this spec pins changed since.
- **The steps**, in order:
  1. The spec hash, `sha256sum docs/specs/00166-c3-trial-2-asopr-veto-design.md`; this file is never edited after it.
  2. The develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append.
  3. On the run's tree, the trial's data-gated basis case with the subjects' two fixture rows, and the six cases the basis ran: `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-65]`, which rebuilds arm A's stored figures, the benchmark's and trial 65's bar through the helpers this trial calls; `…[reading-10]`, which rebuilds the reading's through the inputs half and the reads; `tests/test_research_c3_asopr_reentry_basis.py` and `tests/test_research_c3_onchain_reading_basis.py`, which hold that half's `arm`, `counts` and `features` and trial 1's positions; and `tests/test_portfolio_builder.py::test_frozen_figures_regression`, which holds the daily benchmark to record 33's figure. **The trial's basis case and each of the six read `btc-onchain-20261124T162656Z` and `ohlc-full`, or `ohlc-full` alone, both linked in this worktree (the six measured: 6 passed); none reads a set it does not link.** `scale_positions` is held by the branch's diff over `cli/alpha/b2.py`, which prints nothing, and by its unit cases in `tests/test_alpha_b2.py`; the replays of records 51–54 and 57, which also run it, read `derivatives-funding`, `derivatives-oi` or `liquidations-daily`, sets this branch does not link, and are not part of this pre-flight — they run nightly.
  4. The twin's plain eval, `uv run zcrypto research eval --subject c3-asopr-veto-preflight --dataset btc-onchain-20261124T162656Z`, read in this order — (a) the block, `19ee5c23…74f7a`, both sets `checked`; (b) the events, `events_per_year` summing to 176, reading 10's count; (c) the dead knob, a non-zero count in `vetoed_per_year`, read before the engagement so that a dead knob is named as such; (d) the engagement equal to the measured basis, the plan's data-gated literals; (e) arm A's and the benchmark's seven anchors equal to record 65's figures in the basis, digit for digit; (f) arm A's `passes` 1, its `dsr` 0.9999994726590977 and its SPA p 0.0069965017491254375 — a failure of (a)–(f) an instrument finding, the run kept as a reading under iter-211 (`--reading --iteration iter-211 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent.
  5. On a pass, the trial's one run: `uv run zcrypto research eval --subject c3-asopr-veto --dataset btc-onchain-20261124T162656Z --register --iteration iter-211 --family C3 --n-trials 2 --variant C3-asopr-veto-a1lf-full-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10).
  6. The record's checks and its commit — the registry line, the decisions-log verdict entry `[iter-211] Verdict — C3 trial 2 <ADOPT, PARK or REJECT> (registry trial <N>, family C3 n=2)` and the `LANDED_N_TRIALS` row together, since the tie tests hold only over the three. A check that fails after the record lands stops there: the record stays in place uncommitted, and the owner reads the failing output first.
- **The hash rule**: before (1), nobody reads or computes arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B, or any return of arm A, the benchmark or an asset over the vetoed closes, the event closes or any other subset chosen by the band — by code, a program or arithmetic over a stored figure — nor runs `c3-asopr-veto` or its twin over the real sets; and nobody recomputes, extends or conditions further any forward of reading 10 or any figure of trial 65. Weights, bands, states, events, scales, positions, exposures and turnover are allowed, and are what the measured basis and the data-gated case hold. `a1_daily_positions` computes a book's base returns on every call that sizes it; no program reads them. Trial 65's replay and reading 10's rebuild those entries' stored figures and no other, and record 33's regression the benchmark's; none reads a book carrying the veto.
- **The notes, written before the run** (spec 00137 D10's): the subject over the snapshot with `ohlc-full` beside it, both whole; C3 trial 2, on the owner's pick of 2026-11-25; arm A and arm B, the trigger and its constants, the depth, the hold and the costing; the hypothesis; the count 2 and `var_trials` 0.0; the read from arm B's first engagement deciding, the full-window read and the drawdown pair beside it; the contamination D8 states — reading 10 and its `record_hash`, its 32 cells, this cell's missed leg 1, trial 65 and its `record_hash`, the cell the owner's pick and not the reading's criterion's; the pre-flight's figures, quoted; the park row naming no variant; the matrix pre-registered by this spec's sha256.
- **A refusal from the count, a refused build, a stop by the rule under `--register`**: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0228's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D14 — what a verdict changes (the owner's)

The owner's word names one more trial and nothing after it. Both topics' `ripe_when` have fired on the `[iter-211]` entry (measured), and this branch is that firing's work; it has to say what its own verdict does and what the two topics then watch.

1. **The verdict is recorded and C3's next step is the owner's pick** — **Recommended**.
   - **Adopt** is recorded, never deployed. The veto sells spot the engine's book already holds, on a daily on-chain value the engine does not read, so the live form is a change to the adopted book's A1 sleeve and a new engine input, both the owner's. No forward read can precede it on a horizon worth naming — the cell has no event on the days after and fires 3.43 closes a year (measured) — so an adopt's path is the owner's to set: a P1 combination trial over record 47's book with the veto in its A1 sleeve, outside every bucket's budget, then T0123's promotion path. T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts.
   - **Park** and **reject** record the verdict in the record and the decisions log; a reject archives the hypothesis.
   - **After a verdict, whatever it is**, C3's next step — a further trial from bucket C's 8, T0016's Glassnode step, LTC and DOGE, or the family's close — is asked of the owner and entered as `[iter-<N>] C3's next step after trial 2`. In this branch, after the record's commit and by the `topic-ops` skill's mechanics: T0228's and T0016's `ripe_when` are rewritten to watch for that entry, their check the same `grep -c -E` with `trial 2` for `trial 1`, which prints 0 today (measured); T0228's findings, done-so-far and first next step and T0016's findings, budget line (C3 spent 2, 8 remain) and first next step gain the verdict and the days after the history as the basis measured them; `docs/open-topics/README.md` is rendered again; all four subjects of C3's two trials stay registered; nothing closes.
   - **No verdict** — a pre-flight stop, the rule's stop under `--register`, a refused build or a refusal from the count — spends no trial; T0228 records what failed, the two `ripe_when` are rewritten the same way, and whether the trial runs again once its cause is fixed is the owner's, entered under that same heading.
   - **Why**: no word of the owner's sequences C3 past this trial, and the family call — with both of the gate's actions then read as books — is the owner's to take on the record, not a spec's to take before it.
2. **The verdict sequences the family in this branch.**
   - A **reject** or a **park** closes C3 here, on spec 00146 D11's form: the four subjects retired, T0016's findings and next steps rewritten for C3's close and bucket C's, T0228 resolved with nothing bought, LTC and DOGE not started. An **adopt** leaves C3 open and asks the owner for its path.
   - **Cost**: it commits the family call before the result is known; B4 closed that way on the owner's own "then move on", and no such word stands here.

## Closed-world claims and the enumerations that hold them

- **"Of reading 10's 32 cells, one long-state cell holds legs 2, 3 and 4."** Held by the table in the `[iter-209] BTC's on-chain regime read inside the A1 gate on btc-onchain-20261124T162656Z (reading 10)` entry: its 22 rows are the cells the floor admits, ten of them long-state, and `asopr|low|long|H7` is the one whose legs read (False, True, True, True); the ten cells with no row fail the floor.
- **"On the days after the history, three of the 16 triples have an event and this cell has none."** Held by the second program's loop over `FEATURES` × `TAILS` × `STATES`, each triple printed with its counts, as of the head 2026-10-27; it says nothing of a later head.
- **"C3 holds one record and no other counted attempt."** Held by the fifth program: every record's family, bucket C's one record with its `attempt.counted`, every reading's `attempt`, every registered subject's declared family. The plan's count program reads the log's own answer.
- **"The trial reads the sets reading 10 and trial 65 read and no other."** Held by the reader's block, compared with the ledger line's and the registry line's `datasets` (measured equal), and re-read at the pre-flight's (a).
- **"No holdout path is read."** Held by `ls data` in this worktree — three names, none a holdout's — and by the block; `ohlc-rolling`, which carries the spent window's bars, is read by the basis for positions and counts and by no trial under D1's option 1.
- **"Arm B never holds more than arm A, is never short and borrows nothing."** Held by a case of the plan's on the fixture and by the data-gated case's two counts (measured: none above arm A's, none below 0).
- **"The inputs half computes no return of a book."** Held by `_C3VetoInputs`' field list, pinned by a case (spec 00150's form), beside the case that holds `_c3_reading_inputs` free of a forward.
- **"No existing function changes."** Held by D12's closed file list, by the branch's diff over `cli/` — one added module and pure insertions in `cli/research/subjects.py` — and by trial 65's replay, reading 10's and record 33's regression at the run.
- **"Every replay, regression and data-gated case this spec names reads only sets this branch links."** Held by the list at D13's step 3 against `ls data`, and by the run that passed here; the replays it sets aside are named with the sets they read.

## Tests and guards

The plan reviews at tier `full` (measured); each guard is proven with `infra/scripts/mutate-probe.sh` through its own case.

| Decision | Guard | Where |
| --- | --- | --- |
| D2 | the trial's declared family `C3` and count 2; `LANDED_N_TRIALS`' row after the run | `tests/test_research_command.py`, `tests/test_trial_registry_provenance.py` |
| D3 | a flag only at a long close under a low band; none at a `None` state or a flat one; the events equal to the cell's `flags` | `tests/test_alpha_c3_veto.py` |
| D5, D6 | the scale on a known answer: the depth through 7 closes from the last event close, 1.0 at the seventh after it; overlaps sharing one exit; no later close read; a hold below 1 and a depth outside [0, 1) refused | `tests/test_alpha_c3_veto.py` |
| D6, D7 | arm B is `scale_positions` of arm A and the scales; both arms costed at 0.006 on their own turnover, the stressed series at 0.009; no position below 0 or above arm A's | `tests/test_research_c3_asopr_veto.py` |
| D10, D11 | every `a1_kill_bar` call at `n_trials` 2 and `var_trials` 0.0, arm A's among them; the head-to-head from the first engagement; the two refusals; the rule's five rows | `tests/test_research_c3_asopr_veto.py` |
| D12 | the keys exact and their leaves builtin; the inputs half's fields; the twin ruleless and reading no return of arm B; `--as-of` and `--window` refused before any read | `tests/test_research_c3_asopr_veto.py`, `tests/test_research_command.py` |
| D3–D6 | the engagement over `btc-onchain-20261124T162656Z` and `ohlc-full` equal to the measured basis's literals, on reading 10's block; the events per asset reading 10's counts for the cell | `tests/test_research_c3_asopr_veto_basis.py` |

## Out of scope

- Every other cell of reading 10 — the 30-close sibling, the high tail, the flat-state cells, MVRV, MVRV-Z and the STH supply share — and any further forward read of them.
- Every other knob of this cell's rule: another percentile, history length, lag or first day; another horizon; a depth other than D5's two; a veto of the whole book on one asset's event, or of one asset on BTC's state alone; a short.
- Trial 1's rule, on any days; a third C3 trial; a no-slot reading; and any read of a return after 2026-03-31, unless the owner picks D1's option 2 or 3.
- `ohlc-rolling` in the trial, a later head, a later snapshot and the 4h grid, unless the owner picks D1's option 2 or 3; `ohlc-holdout-*` under every option.
- The combination trial over record 47's book, the engine's on-chain input and anything on the live path (D14).
- LTC and DOGE, the Glassnode step and any purchase (T0228's, T0016's).
- Any change to the chain, the writer, the node, the ops role or a host; any change to an existing function, subject, record, reading or spec.

## The owner's picks

- **D1**, 2026-11-25 (by 12:41:29Z), verbatim: "No trial now (Recommended)" — option 4; the other six decisions moot, not asked.
- **C3's next step after it**, asked as option 4 says, 2026-11-25 (by 12:43:16Z), verbatim: "Hold, dated trigger (Recommended)" — C3 stays open and spends no slot; T0228's and T0016's trigger becomes the date 2027-09-01, when the returns past `ohlc-full`'s last close reach the 519 the measured basis gives the DSR leg at even odds, and the days after the history are read then under their own spec; the on-chain writer runs on as deployed. The options beside it were C3's close, T0016's Glassnode step and LTC and DOGE.
- Both are entered in the phase-4 decisions log as `[iter-211]` entries.
