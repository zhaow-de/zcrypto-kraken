# B2's ratio columns and liquidations leg on the 4h close grid (design)

**Ruling:** the controller's rulings R1–R9 of 2026-10-19, in `.tmp/b2-00136/decisions.md` of this branch's worktree, made in the attended session on the owner's words "directly run C for B1, then B2‘s data work, then B2 baseline ruling" and, after #738, "yes, start the B2 data work after the merge"; the owner's standing preference that day, "the transient issue shouldn't be over prepared", keeps the design minimal. D1–D6 below are R1–R6, each carrying its ruling's substance — D1 as R1 was amended at 2026-10-19T15:39:57Z, the file's "Amendments after the author's report", which also reads R5 as D5 states it; D3 and D4 as R7 amended them at 2026-10-19T17:04:26Z, after plan review round 1 — coverage the caller's and explicit, R3's frontier refusal and R4's coverage from any coin's final withdrawn, the NAS copy no root — and as R8 amended them again at 2026-10-19T18:32:11Z, after plan review's floor gate: the liquidation emitter pure over one coin's bucket rows, reading them the subject's through `ObservedReader`, R3's data root and R7's refusal of an asserted hour unfinished on disk withdrawn; and D3 and D5 as R9 amended them at 2026-10-19T19:25:37Z, after the floor's cycle-1 scoped read: an empty read refused, and the lines rejecting a plain `binperp_liq_` name scoped to the three notionals; the `.tmp` file is not kept past the branch. **Ceremony:** design-open — D4's coverage rule and D5's naming are new decisions — so this spec and its plan, `zcrypto-plan-review`, subagent-driven execution and the branch trio; branch `research/00136-b2-ratio-liquidation-features`; no iteration serial minted, an infrastructure branch with no trial as spec `00131`'s was (the change index's row for #717 carries no `iter`). **Topic:** T0023, whose `## Suggested next steps` lists this work as two autonomous items, its second and third bullets; the topic stays `partial`, its trigger the owner's instrument ruling. **Goal:** `cli/alpha/b2.py` emits, beside spec `00131`'s funding and OI features, the four Binance ratios read at a union's 4h closes and the liquidations leg — per 4h bar the long, short and total liquidated notional and their imbalance, summed over one coin's Coinalyze buckets as a subject reads them — each leak-free and proven on known answers, so the next B2 pre-registration names its features instead of building them.

## The measured basis

Every command ran on 2026-10-19 between 14:55 and 15:26Z in this branch's worktree at develop's `a5e8bee5a`, with `data/derivatives-oi` and `data/derivatives-funding` each a read-only link to the main checkout's `data/`, and the liquidations tree read in place at `/var/lib/zcrypto-ops/liquidations`, read-only — nothing written, renamed or locked under it while the poller's container appends to it. Stamps, levels and counts only: no return and no performance figure was computed. The ratio program, from the worktree root:

```bash
uv run python - <<'EOF'
from pathlib import Path

import polars as pl

M5, H4 = 300 * 10**6, 4 * 3600 * 10**6
RATIOS = ("count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio")
total = {c: [0, 0, 0, 0] for c in RATIOS}
for d in sorted(p for p in Path("data/derivatives-oi").iterdir() if p.is_dir()):
    f = pl.read_parquet(d / "oi.parquet", columns=["ts", *RATIOS])
    us = f["ts"].dt.epoch("us")
    # spec 00131 D6's regular grid, a mark read only from a row inside the bar it closes (D5).
    grid = pl.DataFrame({"g": pl.int_range(-(-us[0] // H4) * H4, -(-us[-1] // H4) * H4 + 1, H4, eager=True)})
    asof = grid.join_asof(pl.DataFrame({"g": us, "src": us}).with_columns(f.select(RATIOS)), on="g", strategy="backward")
    fresh = asof.filter(pl.col("src") > pl.col("g") - H4)
    counts = []
    for c in RATIOS:
        n = ((f[c] == 0.0).sum(), f[c].null_count(), (fresh[c] == 0.0).sum(), fresh[c].null_count())
        total[c] = [a + b for a, b in zip(total[c], n)]
        counts.append(f"{c} 0.0 {n[0]} null {n[1]:,}, at marks 0.0 {n[2]} null {n[3]:,}")
    print(
        f"{d.name}: {f.height:,} rows {f['ts'][0]} -> {f['ts'][-1]}; off-mark {(us % M5 != 0).sum()}; "
        f"gaps > 300 s {(f['ts'].diff().dt.total_seconds() > 300).sum()}; negative {sum((f[c] < 0).sum() for c in RATIOS)}; "
        f"marks {grid.height:,}, stale {grid.height - fresh.height}; " + "; ".join(counts)
    )
print({c: dict(zip(("0.0 rows", "null rows", "0.0 at marks", "null at marks"), v)) for c, v in total.items()})
EOF
```

Its output, whole:

```text
ADAUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 249; gaps > 300 s 232; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,217, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,180, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,790, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 8 null 37,256, at marks 0.0 1 null 777
AVAXUSDT: 487,959 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 468; gaps > 300 s 474; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,216, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,181, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,790, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 4 null 37,255, at marks 0.0 0 null 777
BTCUSDT: 618,850 rows 2020-09-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 230; gaps > 300 s 353; negative 0; marks 12,907, stale 2; count_toptrader_long_short_ratio 0.0 0 null 92,226, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,192, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,797, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 1 null 37,271, at marks 0.0 0 null 776
DOGEUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 311; gaps > 300 s 284; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,218, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,181, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,790, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 2 null 37,254, at marks 0.0 0 null 777
DOTUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 407; gaps > 300 s 379; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,218, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,180, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,790, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 8 null 37,263, at marks 0.0 0 null 778
ETHUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 175; gaps > 300 s 141; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,219, at marks 0.0 0 null 1,922; sum_toptrader_long_short_ratio 0.0 0 null 92,181, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,789, at marks 0.0 0 null 122; sum_taker_long_short_vol_ratio 0.0 3 null 37,247, at marks 0.0 0 null 776
LINKUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 321; gaps > 300 s 296; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,216, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,179, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,789, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 6 null 37,259, at marks 0.0 2 null 776
LTCUSDT: 487,973 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 231; gaps > 300 s 246; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,213, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,179, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,788, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 8 null 37,258, at marks 0.0 2 null 776
SOLUSDT: 487,998 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 236; gaps > 300 s 217; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 92,217, at marks 0.0 0 null 1,921; sum_toptrader_long_short_ratio 0.0 0 null 92,181, at marks 0.0 0 null 1,920; count_long_short_ratio 0.0 0 null 5,790, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 4 null 37,250, at marks 0.0 1 null 776
XRPUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 222; gaps > 300 s 198; negative 0; marks 10,171, stale 1; count_toptrader_long_short_ratio 0.0 0 null 91,930, at marks 0.0 0 null 1,915; sum_toptrader_long_short_ratio 0.0 0 null 91,893, at marks 0.0 0 null 1,914; count_long_short_ratio 0.0 0 null 5,790, at marks 0.0 0 null 121; sum_taker_long_short_vol_ratio 0.0 1 null 36,965, at marks 0.0 0 null 770
{'count_toptrader_long_short_ratio': {'0.0 rows': 0, 'null rows': 921890, '0.0 at marks': 0, 'null at marks': 19205}, 'sum_toptrader_long_short_ratio': {'0.0 rows': 0, 'null rows': 921527, '0.0 at marks': 0, 'null at marks': 19194}, 'count_long_short_ratio': {'0.0 rows': 0, 'null rows': 57903, '0.0 at marks': 0, 'null at marks': 1211}, 'sum_taker_long_short_vol_ratio': {'0.0 rows': 45, 'null rows': 372278, '0.0 at marks': 6, 'null at marks': 7759}}
```

- **Where the ratios live**: `data/derivatives-oi/<PERP>/oi.parquet`, the OI level's own file — `count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`, `count_long_short_ratio` and `sum_taker_long_short_vol_ratio` beside `ts`, `sum_open_interest` and `sum_open_interest_value` in every row, 5,010,882 rows over the ten perps. The stamps are spec `00131`'s measured basis's, read again here unchanged: BTCUSDT from 2020-09-01, the nine from 2021-12-01, all to 2026-07-22T23:55Z; 2,850 rows off a 5-minute mark; 141 (ETH) to 474 (AVAX) gaps over 300 s per perp; 104,446 marks on spec `00131` D6's regular grids, 11 of them with no row inside the bar they close.
- **Zeros**: only `sum_taker_long_short_vol_ratio` carries `0.0` — 45 rows, spec `00110` D5's count — and at 6 marks it is the bar's last row (ADA 1, LINK 2, LTC 2, SOL 1); the other three carry none, and no ratio is negative.
- **Nulls**: 921,890, 921,527, 57,903 and 372,278 rows across the four columns in the order above; at the marks D2 reads, the bar's last row is null at 19,205, 19,194, 1,211 and 7,759 of the 104,446.

The liquidations program, from the worktree root:

```bash
uv run python - <<'EOF'
import hashlib
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

ROOT = Path("/var/lib/zcrypto-ops/liquidations")
H = timedelta(hours=1)
now = datetime.now(UTC)
# Every coin's hour is final once its start is 31 h behind the poller's sweep (the catalog's lag): the closed hours start before this.
closed_before = now.replace(minute=0, second=0, microsecond=0) - 31 * H
FINAL = re.compile(r"(\d{4})/(\d{2})/(\d{2})/(\d{2})\.parquet")
shapes, finals, mismatched = Counter(), {}, 0
for tree in sorted(ROOT.glob("*/liquidations-1m")):
    coin_finals = {}
    for p in tree.rglob("*"):
        if not p.is_file():
            continue
        m = FINAL.fullmatch(p.relative_to(tree).as_posix())
        shapes["final" if m else "manifest" if p.name.endswith(".parquet.sha256") else p.name] += 1
        if m:
            coin_finals[datetime(*map(int, m.groups()), tzinfo=UTC)] = p
            mismatched += hashlib.sha256(p.read_bytes()).hexdigest() != p.with_name(p.name + ".sha256").read_text().split()[0]
    finals[tree.parent.name] = coin_finals
union = set().union(*finals.values())
first = min(union)
span = [first + k * H for k in range((closed_before - first) // H)]
empty = [h for h in span if h not in union]
bars = [o for o in span if o.hour % 4 == 0 and o + 3 * H in set(span)]
covered = [o for o in bars if all(o + k * H in union for k in range(4))]
print(f"read at {now:%Y-%m-%dT%H:%M:%SZ}; files {dict(shapes)}; manifests not matching their final {mismatched}")
print(f"union of the coins' finals: {len(union)} hours, {first:%Y-%m-%dT%HZ} -> {max(union):%Y-%m-%dT%HZ}; closed span {span[0]:%Y-%m-%dT%HZ} -> {span[-1]:%Y-%m-%dT%HZ}, {len(span)} hours, {len(empty)} with no coin's final")
print(f"4h bars inside the closed span {len(bars)}, {bars[0]:%Y-%m-%dT%HZ} -> {bars[-1]:%Y-%m-%dT%HZ}; every hour held by some coin {len(covered)}")
for coin, coin_finals in finals.items():
    closed = {h: p for h, p in coin_finals.items() if h < closed_before}
    f = pl.concat([pl.read_parquet(p).with_columns(pl.lit(h).alias("hour")) for h, p in sorted(closed.items())])
    per_hour = f.group_by("hour").len()["len"]
    total = f["long_usd"] + f["short_usd"]
    by_bar = f.group_by(pl.col("hour").dt.truncate("4h")).agg((pl.col("long_usd") + pl.col("short_usd")).sum().alias("usd"))
    bar_usd = by_bar.filter(pl.col("hour").is_in(covered))["usd"]
    off_form = (f["symbol"] != f"{coin}USDT_PERP.A") | (f["event_id"] != f["symbol"] + "-" + f["ts"].dt.epoch("s").cast(pl.String))
    print(
        f"{coin}: finals {len(coin_finals)}, {min(coin_finals):%Y-%m-%dT%HZ} -> {max(coin_finals):%Y-%m-%dT%HZ}; closed span: "
        f"{len(closed)} hours held, {len(span) - len(closed)} without a final; {f.height:,} buckets from {f['ts'].min():%Y-%m-%dT%H:%MZ}, "
        f"per held hour {per_hour.min()}-{per_hour.max()} (median {per_hour.median():.0f}); off the minute {(f['ts'].dt.epoch('s') % 60 != 0).sum()}, "
        f"outside the file's hour {(f['ts'].dt.truncate('1h') != f['hour']).sum()}, repeated stamps {f.height - f['ts'].n_unique()}, "
        f"nulls {f.null_count().sum_horizontal().item()}, negative {((f['long_usd'] < 0) | (f['short_usd'] < 0)).sum()}, "
        f"symbol or event_id off form {off_form.sum()}, both legs 0.0 {((f['long_usd'] == 0) & (f['short_usd'] == 0)).sum()}; "
        f"long+short per bucket median {total.median():,.0f} p99 {total.quantile(0.99):,.0f} max {total.max():,.0f} USD; "
        f"covered bars with no bucket {len(covered) - bar_usd.len()}, per covered bar with one median {bar_usd.median():,.0f} max {bar_usd.max():,.0f} USD"
    )
EOF
```

Its output, whole:

```text
read at 2026-10-19T15:25:40Z; files {'final': 19473, 'manifest': 19473}; manifests not matching their final 0
union of the coins' finals: 2333 hours, 2026-07-14T10Z -> 2026-10-19T14Z; closed span 2026-07-14T10Z -> 2026-10-18T07Z, 2302 hours, 0 with no coin's final
4h bars inside the closed span 575, 2026-07-14T12Z -> 2026-10-18T04Z; every hour held by some coin 575
ADA: finals 1982, 2026-07-14T12Z -> 2026-10-19T13Z; closed span: 1960 hours held, 342 without a final; 9,156 buckets from 2026-07-14T12:25Z, per held hour 1-34 (median 3); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 558 p99 98,397 max 1,767,089 USD; covered bars with no bucket 1, per covered bar with one median 37,878 max 2,685,341 USD
AVAX: finals 1563, 2026-07-14T10Z -> 2026-10-19T13Z; closed span: 1538 hours held, 764 without a final; 5,544 buckets from 2026-07-14T10:48Z, per held hour 1-34 (median 2); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 908 p99 137,960 max 988,325 USD; covered bars with no bucket 36, per covered bar with one median 21,654 max 2,413,959 USD
BTC: finals 2315, 2026-07-14T10Z -> 2026-10-19T14Z; closed span: 2284 hours held, 18 without a final; 29,752 buckets from 2026-07-14T10:38Z, per held hour 1-54 (median 12); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 4,819 p99 1,869,476 max 68,253,711 USD; covered bars with no bucket 0, per covered bar with one median 1,928,664 max 217,280,550 USD
DOGE: finals 1985, 2026-07-14T12Z -> 2026-10-19T14Z; closed span: 1957 hours held, 345 without a final; 10,469 buckets from 2026-07-14T12:23Z, per held hour 1-36 (median 4); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 764 p99 304,468 max 3,631,744 USD; covered bars with no bucket 4, per covered bar with one median 62,528 max 11,058,180 USD
DOT: finals 1682, 2026-07-14T12Z -> 2026-10-19T14Z; closed span: 1659 hours held, 643 without a final; 5,520 buckets from 2026-07-14T12:30Z, per held hour 1-24 (median 2); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 404 p99 68,866 max 838,953 USD; covered bars with no bucket 14, per covered bar with one median 11,457 max 955,735 USD
ETH: finals 2322, 2026-07-14T10Z -> 2026-10-19T14Z; closed span: 2291 hours held, 11 without a final; 31,586 buckets from 2026-07-14T10:31Z, per held hour 1-53 (median 12); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 3,491 p99 1,970,235 max 65,227,144 USD; covered bars with no bucket 0, per covered bar with one median 2,041,631 max 189,308,817 USD
LINK: finals 1681, 2026-07-14T10Z -> 2026-10-19T13Z; closed span: 1658 hours held, 644 without a final; 6,250 buckets from 2026-07-14T10:38Z, per held hour 1-31 (median 3); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 700 p99 139,538 max 1,855,632 USD; covered bars with no bucket 16, per covered bar with one median 18,584 max 2,595,387 USD
LTC: finals 1493, 2026-07-14T10Z -> 2026-10-19T13Z; closed span: 1474 hours held, 828 without a final; 4,870 buckets from 2026-07-14T10:49Z, per held hour 1-26 (median 2); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 513 p99 60,968 max 859,810 USD; covered bars with no bucket 25, per covered bar with one median 8,628 max 1,385,007 USD
SOL: finals 2255, 2026-07-14T10Z -> 2026-10-19T14Z; closed span: 2224 hours held, 78 without a final; 18,468 buckets from 2026-07-14T10:38Z, per held hour 1-46 (median 7); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 1,402 p99 572,945 max 8,681,135 USD; covered bars with no bucket 0, per covered bar with one median 298,761 max 32,361,573 USD
XRP: finals 2195, 2026-07-14T10Z -> 2026-10-19T14Z; closed span: 2166 hours held, 136 without a final; 18,175 buckets from 2026-07-14T10:49Z, per held hour 1-51 (median 6); off the minute 0, outside the file's hour 0, repeated stamps 0, nulls 0, negative 0, symbol or event_id off form 0, both legs 0.0 0; long+short per bucket median 1,095 p99 348,900 max 5,240,809 USD; covered bars with no bucket 0, per covered bar with one median 167,287 max 18,686,431 USD
```

- **The tree**: ten coin directories, each `<COIN>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet`; 19,473 finals, each beside its manifest, every manifest matching its final; no part, held spill, merging file or quarantine at the read — the poller's open hours were in its memory. Every row is a bucket on its minute, inside its file's hour, its stamp unrepeated, no null and no negative leg, `symbol` `<COIN>USDT_PERP.A` and `event_id` `<symbol>-<epoch seconds>`, and no bucket has both legs `0.0`.
- **The covered span and its gaps**: the ten trees' finals together run 2026-07-14T10Z → 2026-10-19T14Z, 2,333 hours. The closed span — the hours starting 31 h or more before the read's hour, behind the sweep's cutoff at the read — runs 2026-07-14T10Z → 2026-10-18T07Z, 2,302 hours, and no hour in it lacks every coin's final: every hour was fetched by some poll, which says nothing of what each coin's appends wrote (D4). Its first hour is partial: the earliest bucket is ETH's at 10:31Z, the first cycle's back-fill reach.
- **Each coin's own tree**: inside the closed span the coin holds no final for BTC 18, ETH 11, SOL 78, XRP 136, ADA 342, DOGE 345, DOT 643, LINK 644, AVAX 764 and LTC 828 hours (ADA's, DOGE's and DOT's counts include the two hours before their first final at 12Z). Of the 575 4h bars in the closed span every one has all four hours held by some coin; BTC, ETH, SOL and XRP hold a bucket in every one of them, and ADA misses 1, DOGE 4, DOT 14, LINK 16, LTC 25 and AVAX 36.
- **The notional scale**: 1 to 54 buckets per held hour, the median 12 for BTC and ETH and 2 for AVAX, DOT and LTC; long plus short per bucket, the median 404 (DOT) to 4,819 (BTC) USD, the 99th percentile 60,968 (LTC) to 1,970,235 (ETH), the largest 838,953 (DOT) to 68,253,711 (BTC); per covered bar holding a bucket, the median 8,628 (LTC) to 2,041,631 (ETH) USD and the largest 955,735 (DOT) to 217,280,550 (BTC).
- **The tree's newest finals at the read**: 14Z (BTC, DOGE, DOT, ETH, SOL, XRP) or 13Z (ADA, AVAX, LINK, LTC), at 15:25Z.

The poller's own code and the catalog, each read with `git grep -n` at `a5e8bee5a`:

```bash
git grep -n -e '_FINALIZE_LAG_SECONDS = ' -e 'is advisory (fail-open) and never durable' -e '_CATCHUP_WINDOW_SECONDS = ' -e 'writers = {coin: SegmentWriter' -e 'payload = fetch_liquidation_history(api_key, list(symbol_to_coin)' -e 'finalize_cutoff = datetime.now(UTC)' -- cli/liquidations/coinalyze.py
git grep -n -e 'Segment layout' -e 'is ALWAYS a committed, complete final' -e 'close()` flushes but never finalizes' -e 'STRICTLY OLDER than' -- cli/capture/segment_writer.py
git grep -n -o 'zero-liquidation minutes have no bucket' -- docs/reference/data-catalog-full.md
git grep -l -e ratio_features -- cli tests ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*'
```

```text
cli/liquidations/coinalyze.py:52:# is advisory (fail-open) and never durable -- losing it only costs one window of re-submissions,
cli/liquidations/coinalyze.py:57:_CATCHUP_WINDOW_SECONDS = 30 * 3600
cli/liquidations/coinalyze.py:70:_FINALIZE_LAG_SECONDS = 31 * 3600
cli/liquidations/coinalyze.py:151:    payload = fetch_liquidation_history(api_key, list(symbol_to_coin), frm, now_s, opener=opener)
cli/liquidations/coinalyze.py:258:    finalize_cutoff = datetime.now(UTC) - timedelta(seconds=_FINALIZE_LAG_SECONDS)
cli/liquidations/coinalyze.py:292:    writers = {coin: SegmentWriter(data_dir, coin, "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id") for coin in COINS}
cli/capture/segment_writer.py:288:        **`<HH>.parquet` on disk is ALWAYS a committed, complete final.**
cli/capture/segment_writer.py:290:    It holds because `close()` flushes but never finalizes (a stop mid-hour leaves parts, never a
cli/capture/segment_writer.py:313:    Segment layout: `<base_dir>/<pair>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet`.
cli/capture/segment_writer.py:427:        Finalize every hour STRICTLY OLDER than `cutoff` that currently holds a row — the open hour plus any
docs/reference/data-catalog-full.md:169:zero-liquidation minutes have no bucket
cli/features/__init__.py
cli/features/derivatives.py
tests/test_features_derivatives.py
```

- **One request names every coin**: each cycle's one request names all ten perps (`coinalyze.py:151`), and each coin has its own writer (`:292`); the per-coin bucket watermark is advisory and never durable (`:52`), so nothing on disk records what a poll covered.
- **Finality**: a final on disk is always committed and complete (`segment_writer.py:288`), a stopped writer leaves parts and never a final (`:290`), and the sweep finalizes every hour strictly older than its cutoff (`:427`), the cutoff 31 h behind the clock (`coinalyze.py:258`, `:70`), above the 30 h catch-up window (`:57`). A coin's hour holding buckets is final by rotation as soon as a bucket of a later hour arrives, else by that sweep.
- **Sparse by design**: a minute with no liquidation has no bucket (`data-catalog-full.md:169`), so an hour with none has no final.
- **`ratio_features`' readers**: `cli/features/__init__.py`, `cli/features/derivatives.py` and `tests/test_features_derivatives.py` — no emitter reads it at a union's closes.

## Operating model

- **Processes and machines.** The Coinalyze poller, `zcrypto liquidations-poll`, runs as one container on `zcrypto-ops` — this workstation — and is the liquidations tree's one writer: it holds `.capture.lock` at the tree's root, keeps a coin's open hour in memory (or as parts after a stop), and publishes each (coin, hour) final once, atomically, its manifest first. The NAS replication channel copies the tree with an hourly `rsync -a` pull that keeps whatever a failed pull copied (`cli/archive/command.py:115`, `:193–195`; `infra/nas/pull-entrypoint.sh:141`), so the copy's coins can stand at different snapshots and the copy is no source for a block (D3). Neither emitter reads a file. `liquidation_grid_features` sums one coin's bucket rows that a subject read through `ObservedReader` from a block frozen from the live tree, and rests on none of the poller's timing or file names; the poller's behaviour this spec cites is its code at `a5e8bee5a`, and the freeze reads the image the poller's container runs (D3). `ratio_grid_features`' lists come from `data/derivatives-oi`, a read-only canonical set.
- **The shared state and its unit.** The one state with a writer and readers is the liquidations tree. Its unit is the (coin, hour) final `<COIN>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet`, identified by its path, the same in every copy; once published it is never rewritten — the writer leaves parts found beside a final for a human rather than merging over it — and it leaves only by quarantine to a `.corrupt` name, which a freeze excludes (D3).
- **When an open unit is alive.** A (coin, hour) with no final is open until the writer publishes it: in the writer's memory until a later bucket of that coin rotates it or a sweep more than 31 h after the hour starts finalizes it, or on disk as parts after a stop until a later process's sweep merges them. The sweep runs only in a cycle whose disk check, fetch and appends all succeed, and stops at the first coin whose sweep raises (`cli/liquidations/coinalyze.py:231–271`), so while cycles fail an hour stays unpublished past 31 h; within a cycle the rotation finals are written before the sweep. An open hour in memory leaves nothing on disk — the same nothing a quiet hour and an hour no poll covered leave — so the emitter never infers coverage: it sums the buckets of the hours its caller asserts covered for the coin, an asserted hour with no bucket holding none (D4), and which files the block holds — finals only, no unfinished or quarantined file — is the freeze's to check (D3). An assertion that takes in an hour still in memory reads that coin low there, which nothing on disk shows, and proving the assertion is the caller's.
- **Tests.** Every liquidation test passes synthetic bucket lists; no test, probe or plan step reads, lists or locks `/var/lib/zcrypto-ops/liquidations`, and no test reads a dataset.

## D1 — one spec, two emitters in `cli/alpha/b2.py`; no subject, no registry write, no trial; each decision logged

- `ratio_grid_features(oi_ts, ratios, union_ts)` and `liquidation_grid_features(bucket_ts, long_usd, short_usd, union_ts, covered)` sit in `cli/alpha/b2.py` beside spec `00131`'s emitters, its D7's placement, with the private `_validate_union_marks` and `_rows_at_union_closes` and the constants `_HOUR` and `_LIQUIDATION_COLUMNS`. `cli/features/derivatives.py`, `cli/liquidations/`, `cli/capture/` and `cli/research/subjects.py` are not edited.
- Each returns a dict of named columns, `len(union_ts) - 1` values in each, one per return index at `close_grid(union_ts)`. The names are the emitter's here, where spec `00131` D7 left them to the consumer: the ratio names are `ratio_features`' own (spec `00110` D8), and the liquidation names carry D5's provenance, which a bare list would leave to each consumer to restate. A column's `coverage_by_year` summary stays the consumer's (spec `00131` D7).
- Why: emission infrastructure a pre-registration names, as spec `00131`'s was — no subject, no registry record, no trial. D1–D6 are decisions on phase 4's subject — a feature and a dataset's design, in `iteration-closeout`'s terms — so each takes a `[00136]` entry in `docs/research/10.phase4-decisions.md`, shaped as the six `[00131]` entries `1fe25796f` backfilled there (R1 as amended). The Bybit funding cross-check is out of scope and stays a nice-to-have on T0023.
- If wrong: a module move is mechanical.

## D2 — the ratio columns: each read as a level at a union's closes on the OI rows' regular grid, unmapped

- `ratio_grid_features` passes the four columns through `ratio_features`, which names them `binperp_<column>` and refuses a missing or unknown column, a non-finite value and a list of fewer than two (spec `00110`), then reads each through the OI level's pipeline: spec `00131` D6's regular grid over the rows' own span, its D5 staleness — a row reaches a mark only from inside the bar that mark closes, `mark − 4h < ts ≤ mark`, so a row exactly 4 h old is `None` — its D4 raw stamps, and the exact lookup at each union close.
- The pipeline is `_oi_at_union_closes` with its placeholder mapping lifted out: `_rows_at_union_closes(label, feature, oi_ts, values_name, levels, union_ts)` holds the grid, the bound and the lookup once; `_oi_at_union_closes` maps a `0.0` to `None` (spec `00110` D5) and calls it; `ratio_grid_features` calls it unmapped, with the identity `list` as the feature; and the union's stamp and 4h-mark checks move into `_validate_union_marks`, which D3's emitter shares. A length mismatch names the column, `oi_ts and binperp_<column> must be equal length`.
- A `0.0` is a reading: `sum_taker_long_short_vol_ratio` is `0.0` on 45 rows, an all-sell bar (spec `00110` D5), and at 6 marks it is the bar's last row (the basis) — mapped as an OI placeholder those 6 closes would read `None`. The other three columns carry no zero, and no ratio is negative.
- A null as a bar's last row is `None` at that close, never the row before it — spec `00131` D4's rule, which the as-of over row indices gives, a null replacing the carry. 19,205, 19,194, 1,211 and 7,759 of the 104,446 marks read so (the basis), concentrated in 2022 (spec `00110` D5); the consumer's `coverage_by_year` shows where.
- No window and no new constant: the read is the level, carried through and not transformed (spec `00110` D7's ratio family).
- Why the OI pipeline: the ratios are columns of the OI level's own rows — the same stamps, the same 2,850 off-mark rows, the same gaps and 11 stale marks (the basis) — so spec `00131` D4–D6 carry over unchanged, and one pipeline keeps them one rule.
- If wrong: a mark whose bar's last row is null reads `None` where an earlier row's ratio might have stood; a consumer wanting that fall-back builds it under a trial's pre-registration.

## D3 — liquidations data access: the emitter pure over one coin's bucket rows; reading them the subject's, through `ObservedReader`, from a frozen block

- `liquidation_grid_features(bucket_ts, long_usd, short_usd, union_ts, covered)` takes one coin's bucket rows — each bucket's stamp and its `long_usd` and `short_usd` as the subject read them — as spec `00131`'s emitters take the rows a subject reads; it opens no file and takes no root (R8). Lists of unequal length are refused, naming the three; stamps naive, unsorted or repeated are refused as every emitter's are — a bucket read twice would be summed twice. An empty `bucket_ts` is refused by name: a read that found no file — a path built from `BTCUSDT` against a block laid out by coin, `BTC/` — would otherwise sum to zero at every covered bar, and a coin quiet across a whole block is not a case the leg serves (R9).
- Reading is the subject's, through `ObservedReader` (spec `00086` D1, "the one sanctioned way research reads frozen datasets"), each coin's rows from its own finals in a block frozen from the live tree, so the record's datasets block names the bytes that drove its number. Freezing the block is the pre-registration of the first trial that reads it, and the freeze is where the block is checked — finals only, unfinished and quarantined files excluded, the manifests checked, the block compared with the live tree after the copy, the poller's image read (R8), every bucket on its minute with both legs finite and non-negative — a list T0023's later-trials bullet carries beside D4's proofs of coverage. No frozen copy and no new dataset directory here. The NAS copy is no source for a block: its pull can leave the coins at different snapshots (the Operating model; R7).
- What the emitter takes on trust, and where each is held: that the rows are all the coin's buckets over the union — an empty read refused here (R9), one missing some of the coin's finals or holding another coin's the subject's read to rule out (the bullet above); that each bucket stands on its minute with finite, non-negative legs, and that the block holds the live tree's finals — the freeze's (the bullet above); that the asserted hours were covered — the caller's proof (D4).
- Withdrawn: R3's data root and its tree read, and R7's refusal of an asserted hour unfinished on disk, which a pure emitter has nowhere to apply and which rested on the writer's unfinished file names (R8); and R3's finality frontier (R7) — a frontier from the newest final assumed the cycle that wrote it had swept every coin, but the poller writes a cycle's rotation finals before its sweep and skips the sweep in a cycle that fails (the Operating model), so it could pass an hour a quiet coin still held in memory.
- The truncating-prefix property holds with the caller's assertion truncated as the rows are: the test truncates the buckets and the asserted hours at the cutoff, so the hour after it is neither in the rows nor asserted, and a look-ahead into it still differs.
- If wrong: an asserted hour still held in the writer's memory reads its coin low there; the emitter cannot see it, and the caller's proof of coverage is what stands against it (D4). R8's cost: the first liquidation trial writes the freeze and its read through `ObservedReader`, work any trial reading this tape needs. R9's: a block truly holding no bucket for a coin is refused, and says why.

## D4 — coverage: the caller asserts, per coin, the hours the poller covered; a bar all of whose hours are asserted sums its buckets, zero where none, and any other bar `None`

- `covered` is the hour starts the caller asserts the poller covered for the coin, and a bar `[open, open + 4h)` is covered when all four of its hours are in it. A covered bar sums the coin's buckets, zero where the coin holds none; any other bar reads `None` in all four columns, never zero, even where the coin holds buckets in it (R7). A `covered` stamp naive or off its hour start is refused by name: it equals none of a bar's hour starts, so its bar would read `None` with no error.
- Why the caller's: nothing on disk records what a poll covered for a coin. A final is written only for an hour that held a bucket, so a quiet hour and an uncovered one leave the same nothing, and the per-coin watermark is in memory, never durable (the basis). Coverage inferred from the coins' finals together — R4's rule as the author corrected it, which R7 withdrew — reads a covered zero five ways: a cycle's rotation finals are written before its sweep; a failed cycle skips the sweep; a raising entry leaves the coins after it unwritten while those before it rotate into finals (`cli/liquidations/coinalyze.py:145`, `:247–255`); a coin polled for part of a union, added to or dropped from `COINS`, has no final outside its span; and a NAS pull that fails part-way leaves the coins at different snapshots (D3). A coin's own tree cannot carry it either: over the closed span no hour lacks every coin's final (0 of 2,302) while the coins' own trees lack 11 (ETH) to 828 (LTC) of them, so LTC's own finals would show 828 gap hours that are quiet ones.
- How a caller proves coverage — the poller's success timestamp after its sweep, the journal's failed-cycle runs, two reads a cycle apart, a coin's first and last final — is the first liquidation trial's freeze and pre-registration, a next step on T0023, never this spec's (R7); the block's own checks, the live tree compared after the copy among them, are D3's.
- An assertion that is wrong — an hour asserted that the poller did not cover for the coin, or one still in the writer's memory — reads a zero or a low sum there, which the emitter cannot see (D3).
- A gap's edge hour — an outage that begins or ends inside it — is the caller's to assert or not; asserted, its bar sums the part the poller caught, low, inside D5's lower bound. The closed span's first hour is one (2026-07-14T10Z, its earliest bucket at 10:31Z), its bar opening at 08Z, before any final.
- If wrong: a bar whose coverage the caller cannot prove reads `None` where the poller may have covered it, and the first trial builds its coverage evidence before it reads a bar — work that falls on it anyway (R7's cost).

## D5 — provenance: each liquidation column's name says its stream, and each notional's that it is a lower bound

- The four columns are `binperp_liq_lowerbound_long_usd`, `binperp_liq_lowerbound_short_usd`, `binperp_liq_lowerbound_total_usd` and `binperp_liq_imbalance` (**author's call**; the imbalance's name is R5's as amended): `binperp_` because the books are Binance's USDT-M perps, `<COIN>USDT_PERP.A` in Coinalyze's naming (spec `00110` D8); `liq_` the stream; `lowerbound_` on the three notionals because the stream is a lower-bound proxy, not the tape, the catalog's hard caveat — Binance's own feed has been lossy since 2021, at most the largest liquidation per 1000 ms per symbol (T0023) — and D4's edge hours read low as well.
- Stated once: the three notionals are lower bounds of the notional liquidated on the venue; the imbalance is not a bound — a ratio of two undercounts can sit on either side of the true ratio — so its name carries its stream, `liq_`, and no `lowerbound_` (R5 as amended: "the imbalance's name says its stream, never "lower bound""); its caveat is stated here, not in its name (R9).
- Why in the notionals' names: a notional called `binperp_liq_long_usd` beside the funding and OI columns reads as the venue's liquidation tape, and the name is the one place its lower bound survives every downstream join (spec `00110` D8's reasoning); the imbalance's name carries its stream alone, its caveat the bullet above's (R9).
- If wrong: a rename is mechanical while no trial pins a name.

## D6 — the features: per bar the long, short and total notional and the imbalance; no spike flag

- Per covered bar, over the coin's buckets stamped in `[open, open + 4h)` — a bucket covers its minute and closes 60 s after its stamp, so the 03:59 bucket closes at the 04:00 close and is that bar's, the 04:00 bucket the next bar's: long is the sum of `long_usd`, short the sum of `short_usd`, total their sum, and the imbalance `(long − short) / total`, `+1` when the bar's notional is all `long_usd`, `None` where the total is zero (**author's call**: the sign and the `[−1, 1]` scale).
- The bar is the union's own — its open stamp and its four clock hours — so a union hole skips a bar and never stretches one; the features have no window, so no regular grid is needed.
- No spike flag: a spike is a bar above a threshold on a scale — a multiple of a trailing median, a z-score past a cut, a record over a window — and each threshold is either fitted to the data or a pre-registration a trial makes; the scale is no single number to read one off, the median bucket running 404 to 4,819 USD across the coins and the largest 838,953 to 68,253,711 (the basis). It is left out, and the trial that wants one defines it over these totals under its own pre-registration.
- Why sums and no window: the leg's only history is the live tape since 2026-07-14 — 2,302 closed hours, 575 bars at the read — so spec `00110` D7's 30-day window would spend 180 of them warming; the per-bar sums are the substrate a windowed feature reads, and they take no window constant.
- If wrong: a feature over these sums is a trial's pre-registration, built over this emitter.

## The known answers

Each is a test in `tests/test_alpha_b2.py`, synthetic, beside the existing ones, which stay as they are — no line of the file is removed, so spec `00131`'s OI cases prove the lifted pipeline:

- each ratio reads its bar's last row at the close under its `binperp_` name, the four columns distinct, so a column read in another's place differs;
- a ratio row exactly 4 h old at a mark is `None` and one a second younger is read;
- a `0.0` taker ratio as a bar's last row reads `0.0`, never `None`; a null ratio as a bar's last row reads `None`, never the row before it;
- a missing ratio column is refused (`FeatureError`), and a column longer than the rows is refused by its name;
- the truncating-prefix property for the ratios on spec `00131`'s prefix fixture — its late-stamped row, its stale bars and its missing union open — the inputs truncated at `union_ts[n - 1] + 4h` for every `n`, each column's `None` positions exact;
- on one coin's bucket lists, each read under the hours the test asserts covered: BTC's four columns per bar on a known answer, the 03:59 bucket bar 0's and the 04:00 bucket bar 1's; DOT's bar with no bucket of its own, asserted covered, reads `0.0`, `0.0`, `0.0` and an imbalance of `None`; a bar holding an hour not asserted reads `None` in all four columns for both coins, though BTC holds a bucket in that hour; lists of unequal length, an empty `bucket_ts`, and stamps unsorted or repeated, are refused by name; a union stamp off a 4h mark is refused by name;
- the truncating-prefix property for the liquidations: for every `n`, the emitter over `union_ts[:n + 1]`, the buckets that close at or before `union_ts[n - 1] + 4h` — a bucket closing a minute after its stamp — and the asserted hours closing by that cutoff equals the first `n` values of the full run, the union opening a bar into the rows and missing one open just after a covered bar, so a bar stretched across the hole differs from its prefix, BTC defined at 11 of its 12 closes, each coin's `None` positions exact.

## Out of scope

The spike flag (D6) and every windowed liquidation feature — a z-score, a persistence, a threshold — each a trial's pre-registration. The frozen block of the live tape and its checks, the read through `ObservedReader`, any new dataset directory, and every proof of coverage: the first trial that reads the leg freezes and checks its block, reads it through `ObservedReader` and proves the coverage it asserts, as its pre-registration (D3, D4). The Bybit funding cross-check. Any subject or registry change. The per-year coverage summary, the consumer's (spec `00131` D7). Live serving: the ratios are backtest-only (spec `00110` D9), and no live consumer reads the liquidations leg here.
