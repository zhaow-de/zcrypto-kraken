# B3 trial 3 — the rank tilt of the A2-4h ensemble's long weights hedged episodically by a BTC short while A1's confirmed-bear state holds, on the frozen `ohlc-full` set, then B3 closed

**Ruling:** the owner, attended, 2026-10-25, after B3 trial 1's REJECT (registry trial 60), asked B3's next step with three options — 1 a park variant (the tilt at another `M` or `k`), 2 the A1-short BTC overlay (master plan §5's B3 whole), 3 closing B3 — answered, verbatim, at 2026-10-25T15:32:38Z: "let's wait for the round-23 review and PR first. after its PR merge, sequentially Option 1 -> 2 -> 3"; and at the session's restart, 2026-10-25T16:23:14Z: "session restarted, continue the work until all the 3 options finished". The words stand in the decisions log as the entry `[iter-193] B3's next step after trial 1 — the owner's word of 2026-10-25: the tilt at another M or k, then the A1-short overlay, then B3 closed (Decision: 1)`, read there as "B3 trial 2 the park variant, then B3 trial 3 the overlay, then B3 closed, in that order whatever trial 2's verdict". Option 1 ran as B3 trial 2, REJECT (registry trial 61, the `[iter-193] Verdict — B3 trial 2 REJECT` entry). This spec is option 2 and then option 3: B3 trial 3, the overlay, and after its verdict, whatever it is, B3's close in this branch (D11) — no new owner's entry is asked for either. Which overlay trial 3 runs — over which tilt — is the loop's pick under that word (D1), recorded as `[iter-194] B3 trial 3's variant — trial 1's tilt with the A1-short BTC overlay, the loop's pick under the owner's word (Decision: 1)` with the conventions entry, before this spec's hash. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" (the `[iter-181] B2 instrument ruling` entry); the two `[iter-176]` rulings binding every B and C pre-registration, the DSR leg binding at `var_trials` 0.0 and the spent holdout's window never reported as holdout evidence (this set ends 2026-03-31, before it); and the owner's family pick "B3 (Recommended)" under which B3 is worked. Every call past those words and past what specs 00128, 00133, 00137, 00144, 00147 and 00148 fix is the loop's, marked **The loop's call** where the loop's controller made it and **Author's call** where this spec's author did. **Iteration:** iter-194, branch `research/iter-194-b3-btc-overlay`. **Topic:** T0016, its B3 arm. **Goal:** pre-register B3's third trial — master plan §5's B3 whole, "a *simple* (no-ML) rank tilt of long weights within the basket, hedged episodically by the A1 short state — i.e., alts are never shorted individually": trial 1's tilt of the adopted A2-4h ensemble's long weights, unchanged, with a BTC short of half the book's long gross at every close A1's confirmed-bear state holds on BTC, netted against the book's own BTC and the rest borrowed — as numbered decisions with code-level definitions: a compute module `cli/alpha/b3_overlay.py`, one committed research subject with its evaluate-only pre-flight twin, registered through `zcrypto research eval --register` and spec 00133's trial-attempts log at B3's count 3; then B3 closed. Spec 00147 is this spec's arm A, tilt, costing, limits, bar and matrix, frozen by record 60's `spec_hash`; spec 00148 its latest form — the pre-flight check program, the notes rule, the stops; spec 00144 the borrow, its carry, the borrow-unavailable rung and §10's limits wired into a book that shorts, frozen by record 58's; spec 00146 the form of a family's close. The landed record spends one trial of Bucket B's shared budget: 9 remain today, 8 after.

## The measured basis

Every figure below was measured on 2026-10-26 in this branch's worktree at develop's `63c197fff`, with the trial's code absent — the books program between 00:21:35Z and 00:23:53Z, the cells program at 00:28:18Z, the count program at 00:28:43Z; the shell checks, at 01:28:19Z, read spec files, the registry and the git log alone — with `data/ohlc-full` symlinked read-only from the main checkout's `data/` and the main checkout's `.local/trial-attempts.jsonl` read, never written. They read closes, weights, ranks, positions, the short state, limit engagement, turnover, the BTC borrowed and the carry it implies only: no return of trial 3's arm B is read — no net-of-cost series, head-to-head or bar leg — and neither subject runs over the real set. The books program calls `b3_book_returns`, which computes each tilted arm's base returns on its way to the positions, since the vol target sizes on them; the program keeps each arm's positions and the vol target's scale and reads nothing else, and `_b4_ensemble`, which builds arm A, computes arm A's internally, unread. An exploratory read of the same books by the author ran between the books program and the cells program — the state's closes and spells, the book's long gross, BTC and scale at them, and the three readings' engagement, turnover and carry, the quantities the cells program prints, and no return. Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

**The books**, a first program — the union read the way the subject reads it, arm A by trial 58's own `_b4_ensemble`, trial 1's arm B by `cli/alpha/b3.py`'s `b3_book_returns` at record 60's values, and A1's confirmed-bear legs on BTC by `cli/alpha/a1.py`'s `_btc_market_bear` and `cli/features`' `trend_agreement`, never through the trial's code — the books kept under `.tmp/` for the second:

```python
import json
import pickle
import time
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha import A2Config
from cli.alpha.a1 import _btc_market_bear
from cli.alpha.b3 import b3_book_returns
from cli.features import trend_agreement
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

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
print("BTC filled at every close:", all(p is not None for p in fed["BTC"]))
t1 = time.perf_counter()
arm_a = subjects._b4_ensemble(fed)
t2 = time.perf_counter()
print(f"arm A, _b4_ensemble's three A2 runs, {t2 - t1:.1f} s")
configs = [
    A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lb, tv in subjects._B2_A2_ARMS
]
labels = [f"{'-'.join(map(str, c.lookbacks))}@{c.target_vol}" for c in configs]
# Trial 1's arm B as record 60 ran it: each arm's b3_book_returns at M = 180, k = 0.5, floor 8; positions and the vol
# target's scale kept, no return read.
tilted = [b3_book_returns(fed, config=c, score_lookback=180, strength=0.5, floor=8) for c in configs]
t3 = time.perf_counter()
print(f"trial 1's three tilted arms, b3_book_returns, {t3 - t2:.1f} s")
btc = fed["BTC"]
# A1's confirmed-bear short state on BTC at the A family's configuration in days (spec 00031, A1Config's defaults, records
# 15-16): a 200-day SMA, band 0.0, trend agreement over 20, 60 and 120 days; six 4h closes a day.
bear = _btc_market_bear(btc, window=1200, band=0.0)
agree = trend_agreement(btc, lookbacks=[120, 360, 720])
t4 = time.perf_counter()
print(f"the short state on BTC, _btc_market_bear and trend_agreement, {t4 - t3:.1f} s")
books = {
    "h4_ts": h4_ts,
    "labels": labels,
    "arm_a": arm_a,
    "arms_b": [t["asset_positions"] for t in tilted],
    "scales": [t["vol_target_positions"] for t in tilted],
    "ranked": {label: t["ranked"] for label, t in zip(labels, tilted)},
    "tilted": {label: t["tilted"] for label, t in zip(labels, tilted)},
    "bear": bear,
    "agree": agree,
}
Path(".tmp/iter194/basis/books.pickle").write_bytes(pickle.dumps(books))
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole, uv's five lines creating the worktree's environment opening it:

```text
Using CPython 3.14.6
Creating virtual environment at: .venv
   Building zcrypto @ file:///home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter194
      Built zcrypto @ file:///home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter194
Installed 65 packages in 256ms
start 2026-10-26T00:21:35+00:00
reads 0.4 s; union 27338 stamps, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00, return indices 27337
block ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69 {'ohlc-full': (10, 173373, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)'} holes {}
the block's files are record 58's ten EUR files, and no other: True
BTC filled at every close: True
arm A, _b4_ensemble's three A2 runs, 64.6 s
trial 1's three tilted arms, b3_book_returns, 63.9 s
the short state on BTC, _btc_market_bear and trend_agreement, 8.4 s
end 2026-10-26T00:23:53+00:00
```

**The cells**, a second program over the first's books — arm A and trial 1's arm B against records 58 and 60, the short state, what arm B holds while it holds, the three readings of the short's size, and the chosen reading's engagement, written out with `cli/alpha/b4.py`'s limit, shortfall, carry and per-year functions, never through the trial's code:

```python
import json
import math
import pickle
import statistics
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import close_grid
from cli.alpha.b4 import (
    base_exposures,
    limit_factors,
    per_year_counts,
    per_year_means,
    per_year_sums,
    quote_shortfall,
    scale_bars,
    shortfall_carry,
)

print("start", datetime.now(UTC).isoformat(timespec="seconds"))
books = pickle.loads(Path(".tmp/iter194/basis/books.pickle").read_bytes())
h4_ts, labels = books["h4_ts"], books["labels"]
close = close_grid(h4_ts)
n = len(close)
arm_a = books["arm_a"]
assets = list(arm_a)
legs = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}
lines = Path("docs/reference/trial-registry.jsonl").read_text().splitlines()
m58, m60 = json.loads(lines[57])["metrics"], json.loads(lines[59])["metrics"]


def limited(positions):
    factors, engaged = limit_factors(base_exposures(positions, legs))
    return scale_bars(positions, factors), engaged


def first_differ(book):
    return next((k for k in range(n) if any(book[a][k] != arm_a[a][k] for a in assets)), n)


def years(flags):
    return {y: c for y, c in per_year_counts(flags, close).items() if c}


turnover_a = book_turnover(arm_a)
print("arm A's turnover is record 58's turnover_a:", turnover_a == m58["turnover_a"], repr(turnover_a))
print("arm A holds an asset above 0.20 of NAV at", sum(any(arm_a[a][k] > 0.20 for a in assets) for k in range(n)), "return indices")
raw_b = {a: [statistics.mean(arm[a][k] for arm in books["arms_b"]) for k in range(n)] for a in assets}
tilt_b, _ = limited(raw_b)
print(
    "trial 1's arm B against record 60: turnover_b", book_turnover(tilt_b) == m60["turnover_b"],
    "; tilt_first_engaged", first_differ(tilt_b) == m60["tilt_first_engaged"],
    "; stamps_positions_differ", sum(any(tilt_b[a][k] != arm_a[a][k] for a in assets) for k in range(n)) == m60["stamps_positions_differ"],
)

# A1's confirmed-bear short state on BTC, the books program's two series combined as A1's _asset_directions combines them.
state = [b == 1.0 and t < 0 for b, t in zip(books["bear"], books["agree"], strict=True)]
first_state = state.index(True)
episodes, k = [], 0
while k < n:
    if state[k]:
        j = k
        while j + 1 < n and state[j + 1]:
            j += 1
        episodes.append(j - k + 1)
        k = j + 1
    else:
        k += 1
print(f"the short state holds at {sum(state)} return indices ({100 * sum(state) / n:.2f} %), first {first_state}, close {close[first_state].isoformat()}")
print("  per close year", years(state))
print(f"  in {len(episodes)} spells, closes per spell median {statistics.median(episodes)}, mean {statistics.fmean(episodes):.2f}, max {max(episodes)}")
print("  the SMA's leg alone at", sum(b == 1.0 for b in books["bear"]), "; the trend agreement's alone at", sum(t < 0 for t in books["agree"]))

# What arm B's book holds while the state holds: its long gross, its BTC, and the vol target's scale.
gross = [math.fsum(max(0.0, p[k]) for p in raw_b.values()) for k in range(n)]
scale = [statistics.fmean(s[k] for s in books["scales"]) for k in range(n)]
on = [k for k in range(n) if state[k]]
held = [gross[k] for k in on]
print(f"arm B's long gross at the state's {len(on)} closes: 0 at {sum(g == 0 for g in held)}, min {min(held):.6f}, median {statistics.median(held):.6f}, mean {statistics.fmean(held):.6f}, max {max(held):.6f}")
print(f"  off the state, from index 1380: mean {statistics.fmean(gross[k] for k in range(1380, n) if not state[k]):.6f}")
print(f"  its BTC at the state's closes: 0 at {sum(raw_b['BTC'][k] == 0 for k in on)}, mean {statistics.fmean(raw_b['BTC'][k] for k in on):.6f}, max {max(raw_b['BTC'][k] for k in on):.6f}")
print(f"  the vol target's scale, the arms' mean, at the state's closes: 0 at {sum(scale[k] == 0 for k in on)}, mean {statistics.fmean(scale[k] for k in on):.6f}")


def overlaid(short, borrow):
    book = {a: list(v) for a, v in raw_b.items()}
    book["BTC"] = [b - s for b, s in zip(raw_b["BTC"], short, strict=True)]
    if not borrow:
        book["BTC"] = [max(0.0, b) for b in book["BTC"]]
    return book


readings = {
    "half the book's long gross": [0.5 * g if s else 0.0 for g, s in zip(gross, state, strict=True)],
    "half of NAV": [0.5 if s else 0.0 for s in state],
    "half the vol target's scale": [0.5 * c if s else 0.0 for c, s in zip(scale, state, strict=True)],
}
for name, short in readings.items():
    book, engaged = limited(overlaid(short, True))
    shortfall = quote_shortfall(base_exposures(book, legs), "BTC")
    carry = math.fsum(shortfall_carry(shortfall, rate=0.0002))
    start = first_differ(book)
    sized = [s for s in short if s > 0]
    owed = [s for s in shortfall if s > 0]
    turnover = book_turnover(book)
    print(f"{name}: the short above 0 at {len(sized)} return indices, min {min(sized):.6f} mean {statistics.fmean(sized):.6f} max {max(sized):.6f}")
    print(f"  netted, BTC borrowed at {len(owed)}, min {min(owed):.6g} mean {statistics.fmean(owed):.6f} max {max(owed)!r}; above 0.10 of NAV at {sum(s > 0.10 for s in owed)}")
    print(f"  limits engaged {({k2: sum(v) for k2, v in engaged.items()})}; first return index differing from arm A {start}, close {close[start].isoformat()}, {n - start} returns, {(n - start) / 2190:.2f} years")
    print(f"  turnover {turnover!r}, over arm A {turnover - turnover_a!r}, over trial 1's arm B {turnover - m60['turnover_b']!r}")
    print(f"  at 0.006 a side over arm A {(turnover - turnover_a) * 0.006 / (n - start):.6e} per bar from the first difference; the carry {carry!r} summed, {carry / (n - start):.6e} per bar, {carry / (n - start) * 2190:.6f} a year")

# The chosen reading: arm B's engagement, the literals of the plan's data-gated case.
short = readings["half the book's long gross"]
arm_b, engaged_b = limited(overlaid(short, True))
no_borrow, _ = limited(overlaid(short, False))
start = first_differ(arm_b)
differ = [any(arm_b[a][k] != arm_a[a][k] for a in assets) for k in range(n)]
shortfall = quote_shortfall(base_exposures(arm_b, legs), "BTC")
print("the chosen reading, arm B")
print("  tilt_first_engaged", start, "primary_returns", n - start, "stamps_positions_differ", sum(differ))
print("  positions_differ_per_year", years(differ))
print("  before the tilt's first engagement, 15672, differing at", sum(differ[:15672]), "; the overlay's first", next(k for k, s in enumerate(short) if s > 0))
print("  overlay_per_year", years([s > 0 for s in short]))
print("  short_state_per_year", years(state))
print("  shortfall_stamps_per_year", years([s > 0 for s in shortfall]))
print("  shortfall_max", repr(max(shortfall)))
print("  shortfall_mean_per_year", per_year_means(shortfall, close))
print("  carry_per_year", per_year_sums(shortfall_carry(shortfall, rate=0.0002), close))
print("  limit_engaged_per_year", {k2: sum(v) for k2, v in engaged_b.items()}, "arm B's largest gross", f"{max(math.fsum(abs(arm_b[a][k]) for a in assets) for k in range(n)):.6f}", "largest net", f"{max(math.fsum(arm_b[a][k] for a in assets) for k in range(n)):.6f}", "smallest net", f"{min(math.fsum(arm_b[a][k] for a in assets) for k in range(n)):.6f}")
print("  turnover_b", repr(book_turnover(arm_b)))
print("  the no-borrow twin differs from arm B at", sum(any(no_borrow[a][k] != arm_b[a][k] for a in assets) for k in range(n)), "return indices; its turnover", repr(book_turnover(no_borrow)), "; its BTC below 0 at", sum(p < 0 for p in no_borrow["BTC"]))
print("  an asset other than BTC below 0 in arm B at", sum(arm_b[a][k] < 0 for a in assets if a != "BTC" for k in range(n)), "return indices")
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-26T00:28:18+00:00
arm A's turnover is record 58's turnover_a: True 146.18534602048504
arm A holds an asset above 0.20 of NAV at 2236 return indices
trial 1's arm B against record 60: turnover_b True ; tilt_first_engaged True ; stamps_positions_differ True
the short state holds at 8953 return indices (32.75 %), first 1199, close 2014-04-26T00:00:00+00:00
  per close year {'2014': 1038, '2015': 1096, '2018': 1522, '2019': 806, '2020': 331, '2021': 421, '2022': 1900, '2023': 270, '2024': 414, '2025': 660, '2026': 495}
  in 200 spells, closes per spell median 4.0, mean 44.77, max 593
  the SMA's leg alone at 10761 ; the trend agreement's alone at 11561
arm B's long gross at the state's 8953 closes: 0 at 3383, min 0.000000, median 0.022913, mean 0.080801, max 0.810825
  off the state, from index 1380: mean 0.178028
  its BTC at the state's closes: 0 at 5654, mean 0.028776, max 0.810825
  the vol target's scale, the arms' mean, at the state's closes: 0 at 388, mean 0.650768
half the book's long gross: the short above 0 at 5570 return indices, min 0.001660 mean 0.064938 max 0.405412
  netted, BTC borrowed at 4259, min 5.71734e-05 mean 0.041273 max 0.2907872334820236; above 0.10 of NAV at 397
  limits engaged {'gross': 0, 'net': 0, 'margin': 0}; first return index differing from arm A 1230, close 2014-05-01T04:00:00+00:00, 26107 returns, 11.92 years
  turnover 216.05774709807375, over arm A 69.8724010775887, over trial 1's arm B 27.663326656956883
  at 0.006 a side over arm A 1.605831e-05 per bar from the first difference; the carry 0.03757226017290271 summed, 1.439164e-06 per bar, 0.003152 a year
half of NAV: the short above 0 at 8953 return indices, min 0.500000 mean 0.500000 max 0.500000
  netted, BTC borrowed at 8923, min 0.0551304 mean 0.393807 max 0.40000000000000013; above 0.10 of NAV at 8919
  limits engaged {'gross': 0, 'net': 0, 'margin': 8048}; first return index differing from arm A 1199, close 2014-04-26T00:00:00+00:00, 26138 returns, 11.94 years
  turnover 347.8685274238959, over arm A 201.68318140341086, over trial 1's arm B 159.47410698277903
  at 0.006 a side over arm A 4.629654e-05 per bar from the first difference; the carry 0.7183360726504704 summed, 2.748244e-05 per bar, 0.060187 a year
half the vol target's scale: the short above 0 at 8565 return indices, min 0.052993 mean 0.340124 max 0.500000
  netted, BTC borrowed at 8451, min 0.0176643 mean 0.284522 max 0.40000000000000013; above 0.10 of NAV at 7457
  limits engaged {'gross': 0, 'net': 0, 'margin': 3496}; first return index differing from arm A 1199, close 2014-04-26T00:00:00+00:00, 26138 returns, 11.94 years
  turnover 299.26200921805, over arm A 153.07666319756498, over trial 1's arm B 110.86758877693316
  at 0.006 a side over arm A 3.513888e-05 per bar from the first difference; the carry 0.4915412380137397 summed, 1.880562e-05 per bar, 0.041184 a year
the chosen reading, arm B
  tilt_first_engaged 1230 primary_returns 26107 stamps_positions_differ 12493
  positions_differ_per_year {'2014': 332, '2015': 457, '2018': 801, '2019': 668, '2020': 419, '2021': 1934, '2022': 1826, '2023': 2021, '2024': 1848, '2025': 1792, '2026': 395}
  before the tilt's first engagement, 15672, differing at 2506 ; the overlay's first 1230
  overlay_per_year {'2014': 332, '2015': 457, '2018': 801, '2019': 668, '2020': 248, '2021': 252, '2022': 1540, '2023': 194, '2024': 307, '2025': 421, '2026': 350}
  short_state_per_year {'2014': 1038, '2015': 1096, '2018': 1522, '2019': 806, '2020': 331, '2021': 421, '2022': 1900, '2023': 270, '2024': 414, '2025': 660, '2026': 495}
  shortfall_stamps_per_year {'2018': 623, '2019': 544, '2020': 217, '2021': 199, '2022': 1437, '2023': 178, '2024': 307, '2025': 415, '2026': 339}
  shortfall_max 0.2907872334820236
  shortfall_mean_per_year {'2013': 0.0, '2014': 0.0, '2015': 0.0, '2016': 0.0, '2017': 0.0, '2018': 0.008849321558105853, '2019': 0.009562699914014232, '2020': 0.004447907274989879, '2021': 0.0011967031387723332, '2022': 0.02383134038097913, '2023': 0.0037384793611536823, '2024': 0.009359009965511707, '2025': 0.005135563259268716, '2026': 0.05735237611576036}
  carry_per_year {'2013': 0.0, '2014': 0.0, '2015': 0.0, '2016': 0.0, '2017': 0.0, '2018': 0.004150086469044866, '2019': 0.004381962309770746, '2020': 0.0021500975698908443, '2021': 0.0005914662643196171, '2022': 0.010977979120356715, '2023': 0.001849522542579138, '2024': 0.004532077251367467, '2025': 0.0024507149403084714, '2026': 0.006488353705264844}
  limit_engaged_per_year {'gross': 0, 'net': 0, 'margin': 0} arm B's largest gross 0.998300 largest net 0.998300 smallest net 0.000000
  turnover_b 216.05774709807375
  the no-borrow twin differs from arm B at 4259 return indices; its turnover 191.899092913884 ; its BTC below 0 at 0
  an asset other than BTC below 0 in arm B at 0 return indices
end 2026-10-26T00:28:20+00:00
```

What they establish:

- **The block.** The ten EUR assets' 240-minute files of `ohlc-full` form the block the record will carry, `compute_hash` `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`: 10 files, 173,373 rows, 2013-09-10 20:00 → 2026-03-31 20:00, `vouched_status` `checked (36 vouched hashes)`, no hole — record 58's ten EUR files and no other, and the `dataset_hash` of records 49, 60 and 61 (the count program below). The union holds 27,338 stamps, 27,337 return indices, records 45–61's, and BTC is filled at every close by `_ffill_btc`.
- **Arm A is record 58's, trial 1's arm B record 60's.** Arm A's turnover is record 58's stored `turnover_a`, 146.18534602048504, to the last digit; the three tilted arms' mean, limited, gives record 60's stored `turnover_b`, `tilt_first_engaged` and `stamps_positions_differ` to the last digit — so the books the overlay goes on are the books records 58 and 60 ran.
- **The short state.** A1's confirmed bear on BTC — BTC's close below its 1,200-close (200-day) SMA, band 0.0, and BTC's trend agreement over 120, 360 and 720 closes (20, 60 and 120 days) below 0 — holds at 8,953 of the 27,337 return indices (32.75 %), first at return index 1,199 (close 2014-04-26 00:00), the SMA's first warm close; per close year 2014 1,038, 2015 1,096, 2018 1,522, 2019 806, 2020 331, 2021 421, 2022 1,900, 2023 270, 2024 414, 2025 660, 2026 495, and none in 2013, 2016 and 2017. It holds in 200 spells, 4 closes long at the median, 44.77 on average, 593 at the longest: at band 0.0 the state flickers at the SMA, as A1's records ran it (`docs/research/07.phase4-a1-cost-reality.md`'s band sweep). The SMA's leg alone holds at 10,761 return indices, the trend's alone at 11,561.
- **What the book holds while the state holds.** Arm B's book — trial 1's tilted ensemble before the limits — holds nothing long at 3,383 of the 8,953 state closes; its long gross there is 0.0229 at the median, 0.0808 on average and 0.8108 at most, against 0.1780 on average off the state from return index 1,380. Its BTC is 0 at 5,654 of them, 0.0288 on average. The vol target's scale, the three arms' mean, is 0 at 388 of them and 0.6508 on average: a book flat for its whole 180-return window has no volatility to size on, and a nearly flat one sizes at its 1.0 cap.
- **The three readings of the short's size** (D3), each at the state's closes, netted against the book's BTC and passed through §10's limits:
  - **Half the book's long gross** — the short above 0 at 5,570 return indices, 0.0649 on average and 0.4054 at most; BTC borrowed at 4,259, 0.0413 on average and 0.2907872334820236 at most, above §10's 0.10 per-asset short at 397; no limit engaged; the first difference from arm A at return index 1,230 (close 2014-05-01 04:00), 26,107 returns from it, 11.92 years; turnover 216.05774709807375, 69.8724010775887 over arm A's and 27.663326656956883 over trial 1's arm B; the added trading at 0.006 a side 1.605831e-05 per bar from the first difference; the carry 0.03757226017290271 summed, 1.439164e-06 per bar, 0.003152 a year. Chosen (D3).
  - **Half of NAV** — the short 0.5 at all 8,953 state closes; BTC borrowed at 8,923, 0.3938 on average, the margin floor holding it to 0.4 and engaging at 8,048 return indices; turnover 347.8685274238959, 201.68 over arm A's; the carry 0.060187 a year — the A family's structural ~5 %/yr drag again.
  - **Half the vol target's scale** — the long state's gross were every weighted asset long; the short above 0 at 8,565, 0.3401 on average; BTC borrowed at 8,451, the margin floor engaging at 3,496; turnover 299.26200921805; the carry 0.041184 a year.
- **The chosen reading's engagement** — the plan's data-gated literals. Arm B's positions first differ from arm A's at return index 1,230, where the overlay first shorts, 14,442 return indices before the tilt's first engagement at 15,672: the head-to-head's start moves from trial 1's 2020-12-03 to 2014-05-01, and the primary read holds 26,107 return indices, 11.92 years of 2,190. The books differ at 12,493 return indices, 2,506 of them before 15,672, per close year 2014 332, 2015 457, 2018 801, 2019 668, 2020 419, 2021 1,934, 2022 1,826, 2023 2,021, 2024 1,848, 2025 1,792, 2026 395. The overlay shorts at 5,570 return indices (`overlay_per_year`: 2014 332, 2015 457, 2018 801, 2019 668, 2020 248, 2021 252, 2022 1,540, 2023 194, 2024 307, 2025 421, 2026 350); the book's own BTC covers the whole short in 2014 and 2015, and BTC is borrowed at 4,259 (`shortfall_stamps_per_year`: 2018 623, 2019 544, 2020 217, 2021 199, 2022 1,437, 2023 178, 2024 307, 2025 415, 2026 339), at most 0.2907872334820236 (`shortfall_max`). No §10 limit engages; arm B's largest gross and net are 0.9983 and its smallest net 0 — the short never exceeds half the longs, so the book is never net short — and no asset but BTC is ever below 0. Arm B trades 216.05774709807375; the borrow-free twin differs from arm B at the 4,259 borrowed return indices, trades 191.899092913884 and never holds BTC below 0.
- **The hurdle.** From the first difference, arm B's added trading over arm A costs 1.605831e-05 per bar at 0.006 a side — the tilt's 42.20907442063182 of turnover over record 60's arm A, all of it from 15,672, and the overlay's 27.663326656956883 — and the borrow 1.439164e-06 per bar, 1.75e-05 per bar together over the 26,107 returns, each figure from positions alone.
- **§10's per-asset caps.** Arm A holds an asset above §10's 0.20 per-asset long at 2,236 return indices, and arm B's netted BTC short exceeds the 0.10 per-asset short at 397: the per-asset caps are not wired in records 58–61, and are not here (D5).

**The count, the names and the bar's threshold**, a third program:

```python
import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path

from cli.registry import attempts, budget
from cli.research import subjects
from cli.validation import deflated_sharpe_ratio
from cli.validation.dsr import expected_max_sharpe
from tests.retired_subjects import RETIRED_SUBJECTS

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]
landed = attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl"))
c = attempts.reconcile(lines, landed, log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF)
families = ("B1", "B2", "B3", "B4")
print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in families}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])
print("required_n('B3')", c.required_n("B3"), "; B3 records", [(r["trial_id"], r["n_trials_in_family"], r["invocation"]["subject"]) for r in c.records if r["family"] == "B3"])
print("open attempts (a begin with no end):", sorted({x["attempt"] for x in lines if x["kind"] == "begin"} - {x["attempt"] for x in lines if x["kind"] == "end"}))
for attempt in sorted({x["attempt"] for x in lines if x["kind"] == "begin"})[-2:]:
    begin = next(x for x in lines if x["kind"] == "begin" and x["attempt"] == attempt)
    end = next(x for x in lines if x["kind"] == "end" and x["attempt"] == attempt)
    took = datetime.fromisoformat(end["timestamp"]) - datetime.fromisoformat(begin["timestamp"])
    print(f"attempt {attempt} ({begin['invocation']['subject']}): {took.total_seconds():.0f} s, failed {end['failed']}; log {lines[0]['log_id'][:8]}")
records = [json.loads(x) for x in Path("docs/reference/trial-registry.jsonl").read_text().splitlines()]
print("records whose dataset_hash is ff2e5700...:", [r["trial_id"] for r in records if r["dataset_hash"].startswith("ff2e5700695b")])
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("b3-btc-overlay", "b3-btc-overlay-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("names opening b3:", sorted(x for x in names if x.startswith("b3")), "; retired among them:", sorted(x for x in RETIRED_SUBJECTS if x.startswith("b3")))
b3 = {r["trial_id"]: r["metrics"]["per_period_sharpe_4h"] for r in records if r["family"] == "B3"}
dispersion = statistics.variance(b3.values())
print("B3's registered per-period Sharpes", b3, "; their sample variance", repr(dispersion))


def bound(n_obs, n_trials, var_trials):
    lo, hi = 0.0, 0.1
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if deflated_sharpe_ratio(mid, n_obs, n_trials, var_trials) <= 0.95 else (lo, mid)
    return hi


for n_trials, var_trials in ((3, 0.0), (3, dispersion)):
    hi = bound(27_337, n_trials, var_trials)
    print(f"27337 returns at n_trials {n_trials}, var_trials {var_trials!r}: expected max Sharpe {expected_max_sharpe(n_trials, var_trials)!r}; dsr_pass needs a per-period Sharpe above {hi:.6f}, annualised {hi * math.sqrt(2190):.4f}")
```

Its output, whole:

```text
read at 2026-10-26T00:28:43+00:00
{'B1': 5, 'B2': 7, 'B3': 2, 'B4': 2} remain 9 []
required_n('B3') 3 ; B3 records [(60, 1, 'b3-rank-tilt'), (61, 2, 'b3-tilt-slow')]
open attempts (a begin with no end): []
attempt 12 (b3-rank-tilt): 264 s, failed None; log 60c9f39c
attempt 13 (b3-tilt-slow): 262 s, failed None; log 60c9f39c
records whose dataset_hash is ff2e5700...: [49, 60, 61]
b3-btc-overlay equals or opens with a hyphen: [] ; it opens: []
b3-btc-overlay-preflight equals or opens with a hyphen: [] ; it opens: []
names opening b3: ['b3-rank-tilt', 'b3-rank-tilt-preflight', 'b3-tilt-slow', 'b3-tilt-slow-preflight'] ; retired among them: []
B3's registered per-period Sharpes {60: 0.02682474166459608, 61: 0.028244206924263538} ; their sample variance 1.0074408117014038e-06
27337 returns at n_trials 3, var_trials 0.0: expected max Sharpe 0.0; dsr_pass needs a per-period Sharpe above 0.009949, annualised 0.4656
27337 returns at n_trials 3, var_trials 1.0074408117014038e-06: expected max Sharpe 0.0008559713948315; dsr_pass needs a per-period Sharpe above 0.010805, annualised 0.5056
```

- **The count**: the registry holds two B3 records, trials 60 and 61 at counts 1 and 2, and the trial-attempts log no orphan and no open attempt, so `required_n("B3")` is 3 — B3's true count with this trial, the count it declares (D8); bucket B has spent 16 of 25 (B1 5, B2 7, B3 2, B4 2), 9 remaining, 8 once this trial's record lands.
- **The names**: no registered or retired subject's name equals `b3-btc-overlay` or `b3-btc-overlay-preflight` or opens either with a hyphen, and neither opens one; the names opening `b3` are trials 1's and 2's four, none retired (D9).
- **The DSR leg**: at `var_trials` 0.0 the expected maximum Sharpe is 0 at any count, so at count 3 the leg is the PSR against 0: over the 27,337 returns `dsr_pass` needs an annualised net Sharpe above 0.4656, spec 00147's figure. B3's two registered per-period Sharpes, 0.02682474166459608 and 0.028244206924263538, have a sample variance of 1.0074408117014038e-06; at that `var_trials` the expected maximum Sharpe at count 3 is 0.0008559713948315 and the bound 0.5056 (D8).
- **The run's time**: records 60's and 61's `--register` runs took 264 s and 262 s (attempts 12 and 13 of log `60c9f39c`). This trial's inputs half — three A2 runs for arm A, trial 1's three tilted runs, the state — took 145.45 s as the plan's data-gated case, run on the authoring tree; spec 00148's basis measured one `a1_kill_bar` over 27,337 synthetic returns at 11.16 s and one `net_of_cost_verdict` at 5.70 s. The trial computes seven bars and three head-to-heads, about 145 + 78 + 17 ≈ 240 s, one process well under 600 s; its pre-flight the inputs half and one bar, about 157 s.

Specs 00144, 00147 and 00148 frozen, and the code path since record 61's run:

```text
$ date -u +%Y-%m-%dT%H:%M:%SZ; sha256sum docs/specs/00144-b4-ratio-legs-design.md docs/specs/00147-b3-rank-tilt-design.md docs/specs/00148-b3-tilt-slow-design.md; python3 -c 'import json; lines = open("docs/reference/trial-registry.jsonl").read().splitlines(); [print("record", r["trial_id"], r["spec_hash"], r["invocation"]["commit"]) for r in (json.loads(lines[57]), json.loads(lines[59]), json.loads(lines[60]))]'; git log --oneline 1431ef7b2b3cc2b70cd4851b1726d33b6624995a..63c197fff -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version | cat
2026-10-26T01:28:19Z
f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89  docs/specs/00144-b4-ratio-legs-design.md
4dfe9b63171db3dbe2b9f1a129af3cd8bb7d78046e9d944062f83402b11f1163  docs/specs/00147-b3-rank-tilt-design.md
379c83c67738663b4cae139a9e7d7dad2f62dec3ea363e5a94b3a22f3e43203a  docs/specs/00148-b3-tilt-slow-design.md
record 58 f1b49bb75bf56ea805c9111ada3418cc9a8d620ad7d75c7fb52389322258db89 93c0ec7af12323c3cda294481854e9cf878802d6
record 60 4dfe9b63171db3dbe2b9f1a129af3cd8bb7d78046e9d944062f83402b11f1163 cd467546499090509ace16951b2c6b5929c5d0f0
record 61 379c83c67738663b4cae139a9e7d7dad2f62dec3ea363e5a94b3a22f3e43203a 1431ef7b2b3cc2b70cd4851b1726d33b6624995a
$ git merge-base --is-ancestor 1431ef7b2b3cc2b70cd4851b1726d33b6624995a 63c197fff && echo ancestor; git merge-base --is-ancestor cd467546499090509ace16951b2c6b5929c5d0f0 63c197fff && echo ancestor; git log --oneline 93c0ec7af12323c3cda294481854e9cf878802d6..63c197fff -- cli/alpha/b4.py cli/costs cli/risk | cat
ancestor
ancestor
```

- **Specs 00144, 00147 and 00148 are frozen**: their sha256s are records 58's, 60's and 61's `spec_hash`; none is edited.
- **The code path since record 61's run** at `1431ef7b2`, an ancestor of this branch's base, as record 60's `cd4675464` is: the log to the base prints nothing — no commit has touched it — and nor does the log of `cli/alpha/b4.py`, `cli/costs` and `cli/risk` since record 58's run at `93c0ec7af`, so the reads, tilt, arm A, limits, costing, carry, bar and metrics code this trial reuses are records 58's, 60's and 61's.

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial runs under one, the session holding this branch's worktree, `.claude/worktrees/iter194`, on the workstation `zcrypto-ops`, whose main checkout holds the one listed trial-attempts log (`docs/reference/trial-attempt-logs.txt`). No other session runs a bucket-B subject while this branch is open — B1, B2 and B4 are closed and their subjects retired, and B3's trials 1 and 2 are recorded — no second machine and no restored or copied log; each of those is spec 00133's to count and refuse, not this spec's to design for.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Both read `data/ohlc-full`, a symlink to the main checkout's frozen, attested set; a run writes nothing under it and makes no network call, and nothing this spec runs has a live writer.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained; this worktree is their one writer while the branch is open. `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and landed-count literal before anything else lands (D10).

## Hypothesis (trial 3, pre-registered by this spec's sha256)

Master plan §5's B3 whole: a cross-sectional rank tilt of the long book, hedged episodically by the A1 short state, beats the book it tilts — the tilt reallocating the longs toward the basket's strongest names, the BTC short taking part of the long book's market exposure off in a confirmed bear — so **the adopted A2-4h ensemble with trial 1's tilt of each arm's long weights (their rank in the whole basket on the trailing 180-close simple return, each long times 1 + 0.5·z, the longs rescaled to their untilted sum, wherever the basket ranks 8 assets or more) and, at every close BTC sits below its 200-day SMA with its 20-, 60- and 120-day trend agreement below 0, a BTC short of half the book's long gross — netted against the book's own BTC, the rest borrowed at the margin rate — has a higher mean net-of-cost return than the untilted, unhedged ensemble from the first close the two books differ, net of each asset's own turnover at 0.006 a side and of the BTC it borrows at 0.0002 per 4h.** Arm A is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45–61 built it; arm B trial 1's arm B, record 60's, with the short. Alts are never shorted. It is judged by D8's matrix on its own record; what its verdict changes, and B3's close, are D11's.

## D1 — the pick: the owner's sequence, its second step the overlay over trial 1's tilt, its third B3's close

- The owner's words, quoted in the Ruling, and the options the owner was offered, as the `[iter-193] B3's next step after trial 1` entry records them: **1, a park variant — the tilt at another `M` or `k`**, run as trial 2, REJECT (registry trial 61); **2, the A1-short BTC overlay**, master plan §5's B3 whole — this trial; **3, closing B3** — after this trial's verdict, in this branch (D11). The sequence runs 1 → 2 → 3 whatever each verdict: this trial and the close are the owner's word, and no new owner's entry is asked for either.
- **The loop's call (Decision: 1 of the `[iter-194] B3 trial 3's variant` entry) — trial 1's tilt with the overlay.** Arm B is trial 1's arm B — `M` = 180 closes, `k` = 0.5, the floor 8, `b3_book_returns` as record 60 ran it — with a BTC short while A1's short state holds: master plan §5's B3 as written, its tilt the one spec 00147 fixed before any B3 result was read.
- The alternatives weighed and set aside: **trial 2's tilt with the overlay** — `M` = 540, a value chosen after trial 1's look, which compounds the contamination, and whose gross edge was no larger (about +2.37e-06/bar against +2.53e-06, arithmetic over records 60's and 61's stored figures); **the overlay alone on arm A** — isolates the short, but is not B3 and asks the A family's question, whose budget is spent (40 of 40).
- One iteration, one branch, this spec and its plan, one plan review, one task loop; one trial subject with its pre-flight twin, one bar, one matrix, one record; then B3's close. The budget: the landed record spends one of Bucket B's 9 remaining (spec 00133 D5; `BUDGET["B"]` 25, B1 5, B2 7, B3 2 and B4 2 spent); a stop, a refused build or a refusal from the count spends none.

## D2 — the instrument: frozen `ohlc-full`, full history, the ten EUR assets alone

- **The loop's call**: trials 1's and 2's instrument, unchanged — `--dataset ohlc-full`, no `--window`, no `--as-of`; the ten EUR assets' 4h union exactly as records 45–61 read it, `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices; no other pair; the decisive window from index 1,380; the arms and the short state on `_ffill_btc`'s BTC-only fill, the benchmark on the raw prices. The record's block is the ten files', `ff2e5700…01719a69` (measured), records 49's, 60's and 61's.
- The reads are trial 1's `_b3_reads`, unchanged: they refuse, before any book, a window holding fewer than `_DECISIVE_START` + 2 return indices and one none of whose return indices closes in a calendar year the worst-slice leg reads, the stub years left out; and the build refuses `--as-of` before any read: "<subject> evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset".

## D3 — the arms: arm A the adopted ensemble, arm B trial 1's with the BTC short

- **Arm A** is the adopted equal-weight three-arm A2-4h ensemble exactly as trial 58 built it and trials 1 and 2 read it: `_b4_limited(_b4_ensemble(fed))`, `fed = _ffill_btc(h4_prices)`, the three arms `_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year — measured equal to record 58's arm A, its turnover record 58's to the last digit.
- **Arm B** is trial 1's arm B with the short: `raw_b`, trial 1's `_b3_ensemble(fed)` — each arm's `b3_book_returns(fed, config=<its A2Config>, score_lookback=180, strength=0.5, floor=8)`, their equal-weight mean, unchanged — then `with_btc_short(raw_b, short, borrow=True)`, then the limits: `_b4_limited(...)`. The tilt is spec 00147 D3's, every clause unchanged; arm B's book before the short, limited, is record 60's arm B to the last digit of its turnover and first engagement (measured).
- **Author's call — the short state: A1's confirmed bear, read on BTC alone, at the A family's configuration in days.** Master plan §5's A1 short state — "enter short at confirmed bear (price < slow SMA − band, negative multi-horizon momentum)" — is A1's `confirmed_bear`, which `cli/alpha/a1.py` computes per asset as BTC's `_btc_market_bear` and the asset's own `trend_agreement` below 0; B3's overlay shorts BTC alone, so the state is that test on BTC: at return index k, BTC's close below its SMA by the band, `_btc_market_bear(btc, window=1200, band=0.0)[k] == 1.0`, and BTC's `trend_agreement(btc, lookbacks=[120, 360, 720])[k] < 0`, both read at close k — `btc_short_state(fed["BTC"], window=1200, band=0.0, lookbacks=(120, 360, 720))`. The values are read off the A1 records and spec 00031, never tuned here: spec 00031's and `docs/research/06.phase4-a1-results.md`'s 200-day BTC SMA, `A1Config`'s trend lookbacks of 20, 60 and 120 days, and the band 0.0 that records 15 and 16 — A1's two adopted `confirmed_bear` variants — ran at, the A1Config default; at six 4h closes a day, 1,200 closes and 120, 360 and 720. The band sweep of records 17–24 found 0.05 better on A1's own zero-fee returns; taking it would pick a value on A1's results, so the adopted records' value stands. **The alternatives set aside**: the state on daily closes resampled from the union, applied to the next day's six 4h closes — A1's own bars, but a resample the subject would carry and a state that changes once a day where the book trades every close; the A1 windows as 4h bar counts, a 200-close (33-day) SMA, as A2's 4h trials carried A2's daily lookbacks — a fast average, not the master plan's "slow SMA".
- **Author's call — the short's size: half the book's long gross at the close.** Master plan §5's A1 sizes the short state "at reduced size (≤0.5× the long-state exposure)"; in B3 the short hedges the long book ("hedged episodically by the A1 short state — i.e., alts are never shorted individually"), so the long exposure it is sized against is what the book holds long at that close: `short[k] = 0.5 × Σ_i max(0, raw_b[i][k])` where the state holds, 0.0 elsewhere — `overlay_short(raw_b, state, fraction=0.5)`. Measured, what decides it: the book is flat at 3,383 of the 8,953 state closes and long 0.0808 on average, so a short sized on the book's own longs hedges what is held and shorts nothing where nothing is held; the book's net exposure stays at or above half its long gross, never short; and the short lies inside what the vol target sized. It engages: the short is above 0 at 5,570 return indices. **The alternatives set aside, each measured**: **half of NAV** — a 0.5 BTC short at every state close whatever the book holds, a directional BTC bet beside a flat book, its own volatility outside the vol target, the margin floor cutting it at 8,048 return indices and its carry 6.02 % a year, the A family's structural drag; **half the vol target's scale** — the long state's gross were every weighted asset long, A1's literal "long-state exposure", which on a flat book is the vol target's artifact: 1.0 where a nearly flat window gives a tiny volatility, 0 where a wholly flat one gives none (388 state closes), so the short is near 0.5 in a bear whatever the book holds; the margin floor engaging at 3,496 and the carry 4.12 % a year.
- **Author's call — netted against the book's own BTC, the rest borrowed**: the short is sold out of the book's BTC position, `btc[k] = raw_b["BTC"][k] − short[k]`, every other asset untouched — `with_btc_short(raw_b, short, borrow=True)`; where the book holds BTC the short first sells it, and only what the book does not hold is borrowed, B4 trial 1's `quote_shortfall` of the netted position (spec 00144 D5). One BTC position carries both, so its turnover is the one position's and its borrow the one position's short part.
- **Bit for bit until the short first moves a position.** Before the first close at which the state holds while the book holds a long, `short` is 0.0, `btc − 0.0` is `btc` itself, and trial 1's tilted book is arm A's to the bit before 15,672 (spec 00147 D3): arm B's positions are arm A's to the bit to return index 1,230 (measured). After it they differ at a close the short or the tilt moves, and at one whose vol-target window holds a moved base return; the short is applied after each arm's vol target and moves no base return. `tilt_first_engaged`, trial 1's key, is by its definition the first return index at which arm B's limited positions differ from arm A's — here 1,230 (close 2014-05-01 04:00), the short's, 14,442 return indices before the tilt's own first engagement; the record keeps the key's name and its definition, and carries `overlay_first_engaged` beside it (D9).
- **Author's call — the code: a new module for the overlay, a block of trial 1's form in `cli/research/subjects.py`, and no existing function changed.** `cli/alpha/b3_overlay.py`, new: `btc_short_state` (the state, from `_btc_market_bear` and `trend_agreement` unchanged; it refuses a window below 2 and a band outside [0.0, 1.0), A1Config's own bounds), `overlay_short` (the size; it refuses a fraction outside (0, 0.5], the master plan's at most half, and a state of another length) and `with_btc_short` (the netting and its borrow-free form; it refuses a book with no BTC and a short of another length). The plan's tests hold it to known answers: a planted bear at a 4-close SMA, its trend leg and its SMA leg each deciding a close, and a band dropping a close inside it; no close's state reading a later close; the short at the fraction of the long gross where the state holds and 0 elsewhere, a negative position not counted, a flat book shorting nothing; the short netted against the book's BTC, no alt moved, the borrow-free form floored at 0; the carry on the BTC the book does not hold alone. Trial 1's `cli/alpha/b3.py`, trial 58's `cli/alpha/b4.py` and A1's `cli/alpha/a1.py` are unchanged — records 58's, 60's and 61's replays read them.
- No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b3.py`, `cli/alpha/b4.py`, `cli/risk/*`, `cli/costs/*`, `cli/portfolio/*`, any existing function or subject of `cli/research/subjects.py`, or any adopted artifact.

## D4 — the costing: trial 58's, the borrowed BTC carried

- The returns: `_asset_returns(fed[a])` for each of the ten assets. Every book is costed by trial 58's `_b4_net(positions, returns, stress=…)` — `net_of_cost` at `stress × 0.006` per side on each asset's own turnover from flat, a missing return read as 0.0, less `shortfall_carry` of the book's BTC shortfall at `stress × 0.0002`: `0.0002 × (S[k] + max(0, S[k] − S[k−1]))`, `S` the netted BTC position's short part, `quote_shortfall(base_exposures(positions, _B4_LEGS), "BTC")` — the 4h rollover on what is borrowed and the opening charge on each increase, at `margin_rate("BTC", band="high")` (`cli/costs/margin.py`), B4 trial 1's costing of its BTC shortfall (spec 00144 D4, D5). **Author's call — trial 58's function unchanged**: arm A borrows nothing, so its net is record 58's arm A's to the bit, and arm B's carry is the one the function already computes on a book whose BTC goes short. The kill bar's cost-stressed series is `stress` 1.5, the carry at 0.0003. Measured: the carry sums 0.0376 over the window, 1.44e-06 per bar over the primary read, 0.32 % a year.

## D5 — §10's limits: trial 58's wiring, on the book with the short

- Both arms pass `_b4_limited` — `limit_factors` over `base_exposures(positions, _B4_LEGS)`, the BTC exposure the netted position, the gross cap 1.5 / 2.0, the net band −0.5 … +1.0, the margin floor 2.5 (the BTC short fully margin-extended, `_margin_used`), in `cli/risk/limits.py`'s order, one factor per bar (spec 00144 D6). No bar of either arm engages a limit (measured: arm B's largest gross 0.9983, its net between 0 and 0.9983), so both come out of the limits bit-identical; arm B's engaged bars per limit and close year and arm A's totals are recorded.
- **Author's call — §10's per-asset caps unwired, as records 58–61 left them**: `apply_whole_book_limits`' stack takes the per-asset caps as the caller's, applied on the combined book where the A2 sleeve is one part, and spec 00144 D6 wired the three whole-book limits alone for a sleeve that carries none; wiring the long cap would move arm A off record 58's (arm A holds an asset above 0.20 at 2,236 return indices, measured), and wiring the short cap alone would be a second sizing rule. Measured and recorded: the netted BTC short exceeds the 0.10 per-asset short at 397 return indices, at most 0.2908 (`shortfall_max`). An adopt's path runs through the P1 combination trial over record 47's book (D11), where the per-asset caps bind.

## D6 — the borrow-unavailable twin, recorded beside the matrix

- §12's stress list names borrow-unavailable episodes, and T0016's standing prerequisite makes the rung mandatory again the moment a short exists; the overlay's borrowed BTC is one. **Author's call — the twin is arm B with the short floored at the book's own BTC**: `_b4_limited(with_btc_short(raw_b, short, borrow=False))`, the BTC position `max(0, btc − short)` — the short sells only the BTC the book holds — so its shortfall is 0 and its carry 0 at every bar; it differs from arm B at the 4,259 borrowed return indices and trades 191.899092913884 (measured). It is spec 00144 D7's rung on this book: `borrow_unavailable` scales ratio legs against their quote, which the overlay is not.
- Its annualised net Sharpe and its head-to-head against arm A from the primary start go into the record as record 58's three keys, `no_borrow_ann_sharpe_noc`, `no_borrow_head_to_head_mean_outperf_primary` and `no_borrow_head_to_head_spa_p_primary`. It is not a matrix leg: the trial's premise is the overlay as B3 writes it, borrowing.

## D7 — the contamination, stated in full

- **Trial 3 is designed after trials 1 and 2 rejected.** B3 has two records, both REJECT: trial 1's net head-to-head from its first engagement −1.918138730849262e-05/bar and trial 2's −1.0826780098476824e-05/bar, each at SPA p 1.0, their turnovers stored; the split of each into the tilt's gross outperformance (about +2.53e-06 and +2.37e-06/bar) and its added trading (2.17e-05 and 1.32e-05/bar) is arithmetic over those stored figures, recorded in their verdict entries. Trial 3's tilt is trial 1's: from return index 15,672 on, 11,665 of the primary read's 26,107 returns are the span both records read, where the tilt's figures are known.
- **The overlay was named before any B3 result, its state and size chosen after them.** Master plan §5 names it, spec 00147's D1 set it aside for a later trial and its D7 named it a park variant, before trial 1's result; the owner picked it, after trials 1's and 2's verdicts, as the second of three steps; the state's values are the A1 records', and the size was chosen on the engagement figures above — positions, the long gross the state meets, the borrow, the limits and the carry, no return of any book carrying the short.
- **The instrument, window, arm A, costing, limits and bar are records 45–61's**, whose arm A clears the bar on this window (records 58's, 60's and 61's `arm_a_passes` 1; its anchors read again at the pre-flight, D10).
- **The A family's findings are a prior the spec names**: A1's `confirmed_bear` short, per asset at half the long-state size, "rescues the worst regime" — 2014's Sharpe from −0.092 to +0.019 for the equal-risk basket (`docs/research/06.phase4-a1-results.md`) — and its borrow carry is "a structural ~5 %/yr drag" that no cadence removes (`docs/research/07.phase4-a1-cost-reality.md`, T0016's first finding). This trial's short is sized on a book mostly flat in bears, its measured carry 0.32 % a year. The author knows no figure of this repository about any book carrying a BTC short on A1's state over this set's 4h union.
- **The DSR counts B3's true trials**: `n_trials` 3, records 60 and 61 and this one, `required_n("B3")` measured 3.
- **The master plan's prior, in its own words**: "expected outcome per priors: fails to beat equal-weight; kill quickly if so" — read twice by trials 1 and 2, whose rejects stand; this trial is the owner's second step, then B3 closes.

## D8 — the bar, the head-to-heads, the matrix and the count

- **The bar**, records 60's and 61's call at count 3: `a1_kill_bar(net_b, bench, n_trials=3, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)` on the raw union prices, the stub years 2013 and 2026 out of the slices; the SPA grid blocks {30, 102} × seeds {42, 7, 1234}, the headline cell (30, 42), the five others recorded and never read. **Arm A's headline bar** is the same call on `net_a` at (30, 42), `_b4_arm_a_bar` unchanged, read `passes` 1 at the pre-flight, after the hash (D10). All of it is trial 1's `_b3_metrics`, called with `n_trials=3`, unchanged.
- **Author's call — `var_trials` 0.0, B3's own convention.** Records 60 and 61 ran at 0.0, as B2's seven trials and B4's two did (spec 00128 D6's value, which every B2 and B4 trial spec carried); at 0.0 the DSR leg is the PSR against 0, `dsr_pass` needing an annualised net Sharpe above 0.4656 over the 27,337 returns at count 3 (measured), the `[iter-176]` ruling binding it. The alternative is B1's convention, the owner's answer for B1's trials 3–5 alone (the `[iter-177]`, `[iter-178]` and `[iter-179]` entries): the family's dispersion, two-pass, over its registered per-period Sharpes and arm B's — over records 60's and 61's alone a variance of 1.0074408117014038e-06 and a bound of 0.5056 (measured); it would read arm B's own Sharpe, a return the hash rule forbids before the run, and move B3's bar between its trials, so that trial 3's verdict would not be read on the bar trials 1's and 2's were.
- **The head-to-heads** (the loop's call, trial 1's): `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)`, primary from arm B's first engagement — `first` = `tilt_first_engaged`, 1,230, `primary_returns` 26,107 (measured) — and over the full window (`first` 0) beside it; keyed `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_full` and `head_to_head_spa_p_full`; the twin's from the same start (D6). Before the first engagement the two books are one to the bit (D3), so the full-window read adds 1,230 zero differences to the primary's; the primary decides. Refused before any bar: fewer than 2 return indices from the first engagement — trial 1's `ValidationError`, and so a refused build.
- **The matrix** (the loop's call, trial 1's) — rows disjoint and covering every outcome:

| Arm A's bar and the overlay's engagement | Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from arm B's first engagement) | Verdict |
| --- | --- | --- | --- |
| arm A's `passes` 0, or the overlay shorts BTC at no return index (a dead knob) | any | any | **instrument finding**: no verdict, the slot unspent |
| arm A passes, the overlay engaged | fail | any | **reject** |
| arm A passes, the overlay engaged | pass | mean outperformance > 0 and SPA p < 0.05 | **adopt** the tilt with the overlay |
| arm A passes, the overlay engaged | pass | mean outperformance > 0, SPA p ≥ 0.05 | **park** (no variant: B3 closes after this trial on the owner's word) |
| arm A passes, the overlay engaged | pass | mean outperformance ≤ 0 | **reject** |

  Every quantity the matrix reads is a stored key read unrounded: `arm_a_passes`, `overlay_per_year`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`. No drawdown leg: B3's premise is return. The dead knob is read at the pre-flight, before the run (D10). **Author's call — a rule of the trial's own, in trial 1's form**: trial 1's `_b3_rank_tilt_verdict` reads the dead knob off `stamps_positions_differ`, arm B's positions against arm A's, which trial 1's tilt alone satisfies from 15,672 — a dead overlay would pass it, and the record would judge trial 1 a second time; the trial's rule reads the overlay's engagement in its place, every other row trial 1's. The tilt's engagement is record 60's, held by the data-gated case and the pre-flight's (d). **Author's call — the park row names no variant**: B3 closes after this trial (D11). The subject declares it (spec 00129 D4):

```python
def _b3_btc_overlay_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["overlay_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"
```

- **The count**: 3, `_B3_OVERLAY_N_TRIALS` — B3's true count with this trial, `required_n("B3")` measured 3 from the registry and the trial-attempts log (records 60 and 61, no orphan, plus one). Fixed by this spec's hash, never raised in place; spec 00133 D4 refuses a declared count below `required_n`, so a B3 attempt landing elsewhere before this run refuses it, the trial going back to the owner through T0016, a further count a new subject under a new spec.

## D9 — the engagement, the subjects, their record and the build

- **The engagement**: trial 1's eleven keys from `_b3_engagement`, unchanged — `tilt_first_engaged` (D3's reading), `primary_returns`, `stamps_positions_differ`, `positions_differ_per_year`, `tilted_per_year`, `ranked_assets_histogram`, `ranked_assets_mean`, `turnover_b`, `turnover_b_per_year`, `limit_engaged_per_year`, `arm_a_limit_engaged` — and **Author's call** the overlay's seven, from positions and the state alone (`_b3_overlay_engagement`): `short_state_per_year` (the state's closes per close year), `overlay_per_year` (the closes the short is above 0 — the dead-knob read), `overlay_first_engaged` (the first of them, the length when none), and record 58's and 59's four on the netted BTC, `shortfall_stamps_per_year`, `shortfall_mean_per_year`, `shortfall_max` and `carry_per_year` (at 0.0002). Every year key is a close year (`close_grid`), every year the closes span keyed. The tilt's three — `tilted_per_year`, `ranked_assets_histogram` and `ranked_assets_mean` — are record 60's stored figures (measured: the tilted books are record 60's).
- **The trial's 54 keys**: trial 1's 44 (spec 00147 D8), the overlay's seven and the twin's three (D6). **The pre-flight's 35**: trial 1's pre-flight's 28 — the engagement's eleven, arm A's seven anchors (`arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`) and arm A's bar's ten — and the overlay's seven.
- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00149-b3-btc-overlay-design.md"`, `_ASSETS`, intervals `(240,)`: the trial `b3-btc-overlay` — `_build_b3_btc_overlay`, `metric_keys=_B3_OVERLAY_METRIC_KEYS`, seeds (42, 7, 1234), `verdict=_b3_btc_overlay_verdict`, `no_verdict` "instrument finding: arm A fails the bar this window sets, or the overlay shorts no BTC at any stamp; no verdict, the trial unspent", `family="B3"`, `n_trials=_B3_OVERLAY_N_TRIALS` — and its evaluate-only twin `b3-btc-overlay-preflight` — `_build_b3_btc_overlay_preflight`, `metric_keys=_B3_OVERLAY_PREFLIGHT_KEYS`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). It costs arm A alone and reads no head-to-head; it builds arm B's and the twin's positions; its engagement reads arm B's. No incumbent: arm A is built in the run.
- **Author's call — the names `b3-btc-overlay` and `b3-btc-overlay-preflight`**: spec 00141 D2's rule — no registered or retired subject's name equals either or opens it with a hyphen, and neither opens one (measured); the `b3` prefix keeps the family's subjects together.
- **The family key `B3`** is in `BUCKET_OF` already (spec 00147 D8); `cli/registry/budget.py` is unchanged.
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B3`; `n_trials_in_family` 3; variant `B3-btc-overlay-a2eq-full-v1` (**Author's call**: records 60's and 61's form, `<family>-<name>-a2eq-full-v1`); iteration `iter-194`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`; `attempt` the trial-attempts log's; `notes` caller text written before the run (D10).
- **The build in three halves**, spec 00144 D9's form: trial 1's `_b3_reads(subject, reader, dataset, window, accept_holes)` — the union and D2's two window refusals, no compute; `_b3_overlay_inputs(reads)` — trial 1's `_B3Inputs` with arm B carrying the short, the twin's positions, the state and the short, no return of a book; `_b3_overlay_metrics` — trial 1's `_b3_metrics` on those inputs at `n_trials=_B3_OVERLAY_N_TRIALS`, the twin's three keys and the overlay's seven — and `_b3_overlay_preflight_metrics` — trial 1's `_b3_preflight_metrics` and the overlay's seven. The plan's data-gated case runs the first two over the real set, and its fixture tests run the books on a union shorter than the reads admit, at a shorter SMA and trend horizon so that the state holds on it. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `RiskError`, `ValidationError` — is a `SubjectError` naming the subject and its window.
- **The files the build touches, a closed list**: `cli/alpha/b3_overlay.py`, new; `cli/research/subjects.py` — three insertions: the import of the module's three functions, the block before `SUBJECTS` (`_B3_OVERLAY_WINDOW`, `_B3_OVERLAY_BAND`, `_B3_OVERLAY_LOOKBACKS`, `_B3_OVERLAY_FRACTION`, `_B3_OVERLAY_N_TRIALS`, `_B3OverlayInputs`, `_b3_overlay_inputs`, `_b3_overlay_engagement`, `_b3_overlay_metrics`, `_b3_overlay_preflight_metrics`, `_b3_overlay_build`, the two builders, the rule and the three key sets) and its two `SUBJECTS` entries, no existing function changed; `README.md`'s `--subject` row; the tests the plan names; after the run, `tests/test_trial_registry_provenance.py`'s landed-count literal; at B3's close, `tests/retired_subjects.py`. No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b3.py`, `cli/alpha/b4.py`, `cli/registry/*`, `cli/features/*`, `cli/portfolio/*`, `cli/risk/*`, `cli/costs/*`, `cli/engine/*`, trials 1's and 2's subjects, specs 00128, 00133, 00137, 00144, 00147 and 00148, records 58, 60 and 61 or any adopted artifact.

## D10 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00149-b3-btc-overlay-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append; (3) the data-gated basis test on the run's tree, with the subjects' two fixture rows and records 60's and 58's replays — record 60's rebuilding trial 1's stored figures through the reads, tilted ensemble, arm A, costing, bar, head-to-head and metrics code this trial's halves call, record 58's through the carry on a borrowed BTC, the limits on a book that borrows and the twin's head-to-head; (4) the twin's plain eval, read in this order — (a) the block, `ff2e5700…01719a69`, `ohlc-full` `checked (36 vouched hashes)`; (b) arm A's seven anchors records 60's and 61's stored figures to the last digit — `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown`, `turnover_a`, `benchmark_ann_sharpe_noc` and `benchmark_ann_sharpe_noc_decisive`, and the spot drag its `turnover_a` gives, `turnover_a / 27,337 × 0.006 × 2,190`; (c) the dead knob — the short above 0 at some return index, a non-zero count in `overlay_per_year`, read before the engagement so that a dead knob is named as such; (d) the engagement equal to the measured basis — the plan's data-gated literals, and the tilt's three keys record 60's; (e) arm A's `passes` 1 — a failure of (a)–(e) an instrument finding, the run kept as a reading under iter-194 (`--reading --iteration iter-194 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent; (5) on a pass, the trial's one run, `--register --iteration iter-194 --family B3 --n-trials 3 --variant B3-btc-overlay-a2eq-full-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10); (6) the record's checks and its commit — the registry line, the decisions-log verdict entry and the landed-count literal together, since the tie tests hold only over the three. A check that fails after the record lands stops there: the record stays in place uncommitted, and the owner reads the failing output first.
- **The hash rule**: before (1), nobody reads or computes trial 3's arm B returns or net-of-cost series, a head-to-head or a bar leg of arm B or of its twin — by code, a program or arithmetic over a stored figure — nor runs `b3-btc-overlay` or its twin over the real set; weights, ranks, positions, the short state, the short, exposures, the BTC borrowed, the carry it implies, limit engagement and turnover are allowed, and are what the measured basis and the data-gated test hold. `a2_book_returns` and `b3_book_returns` compute each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; no program reads any of them (spec 00145 D8's words). Records 60's and 58's replays rebuild trials 1's and 58's returns and read no book carrying the short. No net-of-cost return of trial 3's arm B is computed over the real data before the trial's `--register` run.
- **The notes, written before the run** (spec 00137 D10's): the subject over `ohlc-full`, full history; the arms, the tilt and its values, the short state and its values, the short's size, the netting and the borrow, the costing and the limits; the hypothesis; the count 3 and `var_trials` 0.0; the read from arm B's first engagement deciding, the full-window read and the twin beside it; the contamination D7 states; the pre-flight's figures, quoted — arm A's seven anchors and the bar's `dsr` and SPA p; the park row naming no variant, B3 closing after the verdict; the matrix pre-registered by this spec's sha256.
- A refusal from the count, a refused build, a stop by the rule under `--register`: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0016's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D11 — what a verdict changes, and B3's close

- **Adopt** is recorded, never deployed, on spec 00147 D10's path: the tilt reweights the ten EUR pairs the engine's book already trades, and the short is a BTC/EUR margin position the engine's book does not carry, so the live form is a change to the adopted book's A2 sleeve and its short path, both the owner's (master plan §12); in order: a P1 combination trial over record 47's book carrying the tilt and the overlay, outside every bucket's budget, then T0123's promotion path; T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts.
- **Park** and **reject** record the verdict in the record and the decisions log; a reject archives the hypothesis.
- **After a verdict, whatever it is, B3 closes on the owner's word** — the sequence's third step, in this branch after the record's commit: the decisions log gains `[iter-194] B3 closed — the third step of the owner's sequence of 2026-10-25, after trial 3's verdict (Decision: 1)`, quoting the owner's words as the `[iter-193]` entry records them, its options the close and a further B3 trial, and what the family leaves — the shared Bucket-B budget read off the bucket refusal's count. T0016 is rewritten as spec 00146 D11 rewrote it for B4: its findings gain trial 3's verdict; its B3 Done-so-far bullet records trial 3 and B3 closed on its three trials; its next steps are §5's ranking, C2 → C3 → C1; its `ripe_when` loses its B3 arm and keeps the C3, C2 and C1 arms as they stand; the open-topics index is re-rendered. **Author's call — every B3 subject retired at the close**, spec 00146 D11's settlement for B4's (measured: B4's close added its last two subjects to `tests/retired_subjects.py`, every B4 subject retired and none removed from `SUBJECTS`): `b3-rank-tilt`, `b3-rank-tilt-preflight`, `b3-tilt-slow`, `b3-tilt-slow-preflight`, `b3-btc-overlay` and `b3-btc-overlay-preflight` join `RETIRED_SUBJECTS`, so CI deselects their cases and the nightly runs them; their code stays, which records 60's, 61's and this record's replays read. Nothing is archived: T0016 stays live for the C families.
- **On an adopt** B3 closes as a family all the same — no further B3 trial follows — and T0016's `ripe_when` keeps a B3 arm for the combination trial alone, as spec 00146 D11 kept B4's.
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, a refused build or a refusal from the count — spends no trial and writes no close entry. **Author's call**: the owner's sequence follows a verdict, and a stop has none, so whether trial 3 runs again once its cause is fixed or B3 closes unrun is the owner's; T0016 records what failed and its B3 arm waits on an `[iter-NNN] B3's next step after trial 3's stop` entry, and every B3 subject is kept.

## Out of scope

Every other B3 knob — trial 2's 540-close tilt with the overlay, the overlay alone on arm A, another short state (a band other than 0.0, another SMA or trend horizon, the state on daily closes), another size (half of NAV, the vol target's scale, another fraction), the short capped at §10's per-asset 0.10, an alt short; a further B3 trial after this one; a no-slot reading; any window but the frozen set's full history, and `ohlc-rolling`; the overlay on the live path and the combination trial over record 47's book (D11); the C families, T0016's; any change to an existing function, subject, record or spec.
