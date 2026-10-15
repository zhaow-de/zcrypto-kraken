# B2's remaining features on the 4h close grid — the funding sign run and accrued carry, the OI level and its trio (design)

**Ruling:** the controller's rulings R1–R9 of 2026-10-14/15, in `.tmp/t0023/decisions.md` of this branch's worktree, made in the unattended run the owner launched at ~23:09Z ("move ahead on milestone 'Research substrate', start with the most relevant topic first. unattended. disregard the wall clock gate, but do not pick up new topic after 07:30Z"); D1–D7 below are R1–R7, `## Out of scope` is R8, and this header carries R9. **Ceremony (R9):** design-open — D4's and D5's stamp rulings are new decisions — so this spec and its plan, `zcrypto-plan-review`, subagent-driven execution and the branch trio; branch `research/00131-b2-feature-emission`; no iteration serial minted, an infrastructure branch as 00129 and 00130 were, with no trial. **Topic:** T0023, whose `## Suggested next steps` lists this work as autonomous (its second bullet); the topic stays `partial`. **Goal:** `cli/alpha/b2.py` emits, beside the funding z-score spec `00128` D2/D8 delivered, the rest of B2's substrate→feature emission on the 4h close grid — the funding sign run and accrued carry, the OI level, and the OI log-delta, z-score and momentum — each leak-free and proven on known answers, so the next B2 pre-registration names its features instead of building them.

## The measured basis

Every command ran on 2026-10-15 between 00:06 and 00:14Z in this branch's worktree at develop's `f7c447c88`, with `data/derivatives-funding` and `data/derivatives-oi` each linked from the main checkout's `data/`. Stamps, levels and counts only: no return and no feature value was computed. The substrate program, from the worktree root:

```bash
uv run python - <<'EOF'
from datetime import timedelta
from pathlib import Path

import polars as pl

M5, H1, H4 = 300 * 10**6, 3600 * 10**6, 4 * 3600 * 10**6
total = dict.fromkeys(("closes", "stale", "zero_asof", "off_mark", "own_mark_present", "late_own_mark"), 0)
for d in sorted(p for p in Path("data/derivatives-oi").iterdir() if p.is_dir()):
    f = pl.read_parquet(d / "oi.parquet", columns=["ts", "sum_open_interest"])
    us = f["ts"].dt.epoch("us")
    have = set(us.to_list())
    late = [t for t in us.to_list() if t % M5]
    gap = f["ts"].diff()
    i = gap.arg_max()
    # The close grid: every 4h mark after the first row (the first bar's close) up to the last row.
    grid = pl.DataFrame({"g": pl.int_range((us[0] // H4 + 1) * H4, us[-1] + 1, H4, eager=True)})
    asof = grid.join_asof(pl.DataFrame({"g": us, "src": us, "oi": f["sum_open_interest"]}), on="g", strategy="backward")
    stale = asof.filter(pl.col("src") <= pl.col("g") - H4)
    zero_asof = asof.filter((pl.col("src") > pl.col("g") - H4) & (pl.col("oi") == 0.0)).height
    own_mark_present = sum((t - t % M5) in have for t in late)
    late_own_mark = sum((t - t % M5) % H4 == 0 and (t - t % M5) not in have for t in late)
    counts = (grid.height, stale.height, zero_asof, len(late), own_mark_present, late_own_mark)
    for key, n in zip(total, counts):
        total[key] += n
    print(
        f"{d.name}: {f.height:,} rows {f['ts'][0]} -> {f['ts'][-1]}; off-mark {len(late)} at {min(t % M5 for t in late) / 1e6:.0f}-"
        f"{max(t % M5 for t in late) / 1e6:.0f} s past their mark, own mark present {own_mark_present}, "
        f"next mark present {sum((t - t % M5 + M5) in have for t in late)}, a close's own row late {late_own_mark}; "
        f"gaps > 300 s {(gap > timedelta(seconds=300)).sum()}, largest {f['ts'][i - 1]} -> {f['ts'][i]}; "
        f"sum_open_interest == 0.0 {(f['sum_open_interest'] == 0.0).sum()}; closes {grid.height:,}, "
        f"last row >= 4 h old {pl.from_epoch(stale['g'], time_unit='us').dt.to_string('%Y-%m-%dT%H:%MZ').to_list()}, "
        f"last row a 0.0 {zero_asof}"
    )
print(total)
for d in sorted(p for p in Path("data/derivatives-funding").iterdir() if p.is_dir()):
    f = pl.read_parquet(d / "funding.parquet")
    past = f["ts"].dt.epoch("us") % H1
    print(
        f"{d.name}: {f.height:,} prints, {(past != 0).sum()} past the hour, at most {past.max() / 1e6:.3f} s; "
        f"interval_hours != 8: {(f['interval_hours'] != 8).sum()}; largest gap between prints {f['ts'].diff().max()}"
    )
EOF
```

Its output, whole:

```text
ADAUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 249 at 1-262 s past their mark, own mark present 5, next mark present 206, a close's own row late 136; gaps > 300 s 232, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 229; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 7
AVAXUSDT: 487,959 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 468 at 1-262 s past their mark, own mark present 7, next mark present 407, a close's own row late 103; gaps > 300 s 474, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 168; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
BTCUSDT: 618,850 rows 2020-09-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 230 at 1-262 s past their mark, own mark present 5, next mark present 185, a close's own row late 57; gaps > 300 s 353, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 502; closes 12,905, last row >= 4 h old ['2021-02-20T00:00Z', '2024-02-16T20:00Z'], last row a 0.0 14
DOGEUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 311 at 1-262 s past their mark, own mark present 5, next mark present 264, a close's own row late 76; gaps > 300 s 284, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 225; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
DOTUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 407 at 1-262 s past their mark, own mark present 7, next mark present 353, a close's own row late 133; gaps > 300 s 379, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 212; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
ETHUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 175 at 1-262 s past their mark, own mark present 5, next mark present 128, a close's own row late 24; gaps > 300 s 141, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 208; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 5
LINKUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 321 at 1-262 s past their mark, own mark present 8, next mark present 271, a close's own row late 110; gaps > 300 s 296, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 216; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
LTCUSDT: 487,973 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 231 at 1-270 s past their mark, own mark present 6, next mark present 184, a close's own row late 65; gaps > 300 s 246, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 176; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 6
SOLUSDT: 487,998 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 236 at 1-278 s past their mark, own mark present 5, next mark present 191, a close's own row late 83; gaps > 300 s 217, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 197; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 7
XRPUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 222 at 1-262 s past their mark, own mark present 7, next mark present 177, a close's own row late 67; gaps > 300 s 198, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 196; closes 10,169, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 5
{'closes': 104426, 'stale': 11, 'zero_asof': 60, 'off_mark': 2850, 'own_mark_present': 60, 'late_own_mark': 854}
ADAUSDT: 7,063 prints, 3182 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
AVAXUSDT: 6,322 prints, 2973 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
BTCUSDT: 7,119 prints, 3190 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
DOGEUSDT: 6,545 prints, 3057 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
DOTUSDT: 6,422 prints, 3022 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
ETHUSDT: 7,119 prints, 3190 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
LINKUSDT: 7,070 prints, 3184 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
LTCUSDT: 7,094 prints, 3186 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
SOLUSDT: 6,424 prints, 3040 past the hour, at most 0.047 s; interval_hours != 8: 101; largest gap between prints 8:00:00.047000
XRPUSDT: 7,103 prints, 3188 past the hour, at most 0.047 s; interval_hours != 8: 0; largest gap between prints 8:00:00.047000
```

- **The OI substrate's stamps**: BTCUSDT 618,850 rows from 2020-09-01, the other nine 487,959–488,018 from 2021-12-01, all ending 2026-07-22T23:55Z. 2,850 rows sit off a 5-minute mark — 175 (ETH) to 468 (AVAX) per symbol — each 1 s to 262 s past its mark, LTC's latest 270 s and SOL's 278 s. An off-mark row stands in place of its own mark's row: 60 of the 2,850 have a row on their own mark beside them, 2,366 a row on the next mark. 854 are a 4h mark's own row stamped late.
- **Gaps**: 141 (ETH) to 474 (AVAX) gaps over 300 s per symbol; the largest is 10 h 30 min in every symbol, one shared outage, 2024-02-16T13:30Z → 2024-02-17T00:00Z.
- **Staleness on the close grid**: from each symbol's first bar close (the 4h mark after its first row) to its last row, 104,426 closes — BTCUSDT 12,905, each of the nine 10,169. At 11 the last row is 4 h old or more: 2024-02-16T20:00Z in all ten (the outage's last row 13:30Z, 6 h 30 min old), and BTCUSDT's 2021-02-20T00:00Z.
- **Zero placeholders**: `sum_open_interest == 0.0` on 2,329 rows, BTCUSDT's 502 the most — spec `00110` D5's count, unchanged. At 60 closes the last row inside the bar is one — BTCUSDT 14, the nine 4–7.
- **The funding substrate**: 68,281 prints; 31,212 stamped past the hour, the latest 47 ms past it — every print inside the 60 s settlement tolerance spec `00128` D2 rules; SOL's 101 prints at `interval_hours` ≠ 8 the only off-cadence ones. The largest gap between consecutive prints is 8 h 47 ms in every perp: no settlement is missing, so a print carried as-of never spans a missed one.
- **The emission's callers and the grids the committed subjects read**: `git grep -l -e funding_grid_feature -e close_grid -- cli tests ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*'` → `cli/alpha/b2.py`, `cli/research/subjects.py`, `tests/test_alpha_b2.py`. `uv run python -c 'from cli.research.subjects import SUBJECTS; [print(n, s.intervals) for n, s in SUBJECTS.items()]'` → `record44-crossfreq (1440, 240)`, `record33-combined (1440,)`, and `(240,)` for `b2-funding-derisk`, `b2-arm-a-bar`, `b1-conditioning` and `b1-window-only`: no subject reads a 1h series.
- **A union's holes and the arms' warm-up**: spec `00128`'s measured basis counts 12,646 union stamps over trial 1's window, which holds `python3 -c 'from datetime import datetime, timedelta; print((datetime(2026, 6, 30, 20) - datetime(2020, 9, 22)) // timedelta(hours=4) + 1)'` → `12648` 4h marks: two union holes. Spec `00128` D4: the adopted A2 arms hold no position before return index 181, their 180-bar vol and basket lookbacks counting the union's bars.

## D1 — the emission is the 4h close grid only; the 1h grid is dropped

- Every emitter takes the union's 4h bar-open stamps and returns one value per return index, on `close_grid(union_ts)` (`ts[k] + 4h`), the grid spec `00128` D2 rules. No 1h grid is built, and T0023's next step for it closes as dropped, with this reason in the topic.
- Why: spec `00128` D1 calls a same-hour de-risk between 4h boundaries an execution-layer knob and a trial on it its own pre-registration; no hypothesis consumes a 1h grid — closed world: the committed subjects' `intervals`, enumerated in the basis, none of them 60 — and a path no trial reads is untested in use. Spec `00110` D3 named both grids as the harness's reach; it is not edited, and this spec is the record that the 1h emission is not built.
- If wrong: a future 1h hypothesis builds its grid under its own pre-registration, as spec `00128` D1 already requires.

## D2 — one print pipeline for the three funding features

- A private `_funding_on_close_grid(label, feature, prints_ts, prints_rate, prints_interval_hours, union_ts)` holds spec `00128` D2's two rulings once: it refuses unequal lengths and unsorted or tz-naive stamps, truncates each print stamp to its hour and refuses one more than `_STAMP_TOLERANCE` (60 s) past it, maps a print whose `interval_hours` ≠ 8 to `None` (spec `00110` D7: mapped, never dropped), applies `feature` to the print series, and returns `align_asof(normalised, values, close_grid(union_ts))`.
- `funding_grid_feature` (the z-score at `B2Config.z_window`, unchanged in signature and behaviour), `funding_sign_grid_feature` (`funding_sign_persistence`) and `funding_carry_grid_feature` (`funding_accrued_carry` at D3's window) each call it, with the signature `(prints_ts, prints_rate, prints_interval_hours, union_ts)` — the z-score's keeping its `*, config`.
- `feature` is applied to the prints, never to the grid: T0023's load-bearing warning. A grid-fed sign run counts each print once per bar it carries across — twice on the 4h grid — and a grid-fed 90-value carry sums 15 days of 4h bars, each print twice; both are causal, so no truncating-prefix test can see them, and a known answer does (`## The known answers`).
- `funding_grid_feature`'s existing tests are unchanged — no task's diff removes a line of `tests/test_alpha_b2.py` — and green, and each of the pipeline's rulings and refusals is probed against them as well as against the new emitters' cases.
- If wrong: nothing — the refactor is proven by the unchanged tests and the probes on the shared helper.

## D3 — the windows are spec 00110's pre-registration, as module constants

- 30 days, as spec `00110` D7 pre-registered them: `_CARRY_WINDOW = 90` prints at 8 h, `_OI_ZSCORE_WINDOW = 180` and `_OI_MOMENTUM_LOOKBACK = 180` bars at 4 h; the sign run takes no window. They are constants of `cli/alpha/b2.py` beside `_STAMP_TOLERANCE`, not fields of `B2Config`, which is trial 1's overlay configuration and keeps its `z_window` for the z-score alone.
- Why: spec `00110` D7 fixed the windows in days before any result, and changing one after a result is a new trial that spends budget; a field would offer a knob no trial may turn.
- SOL's 101 off-cadence prints: the carry is `None` across them and the 89 prints after them, as the z-score is (spec `00110` D7).
- If wrong: a later trial that wants another window is a new trial anyway.

## D4 — the OI level is `sum_open_interest`, placeholders mapped, as-of on the raw stamps

- The level is `sum_open_interest`, the contract count whose placeholders spec `00110` D5 counts (2,329); `sum_open_interest_value` is the same position priced in USDT, its moves part price, and it carries 101 further zeros on a healthy contract count (spec `00110` D5). `oi_levels_from_raw` runs first (a `0.0` → `None`, spec `00110` D5), then the as-of onto `close_grid(union_ts)` on the RAW stamps, no normalisation: `oi_grid_levels(oi_ts, oi_values, union_ts)`.
- Why no normalisation: a stamp is when the venue measured the level, so `source_ts <= grid_ts` admits no look-ahead as it stands — unlike funding's settlement prints, which spec `00128` D2 truncates to the hour they settle. Measured: 2,850 off-mark rows, each 1–278 s past its mark. Measured beside it: an off-mark row stands in place of its own mark's row (60 of 2,850 have both), so the stamp may as well be a late write of the mark's level; either way the level exists at its stamp, and reading it from the stamp never reads it early. At the 854 closes whose own mark's row is stamped late, the level is the row before it.
- A placeholder that is the last row inside the bar makes the level `None` at that close (60 closes measured), never the level before it: mapping removes a reading, and a fall back to an earlier row would carry one the venue did not show at that stamp (spec `00110` D5's no-imputation rule).
- If wrong: a late row is read one boundary later than its mark, never earlier.

## D5 — staleness: a level reaches only the close of the bar it lies in

- A level reaches a close only if its row's stamp lies inside the bar that close ends, `close − 4h < source_ts ≤ close`; otherwise `None` — a row exactly 4 h old is `None`.
- Why: gaps reach 10 h 30 min in every symbol (one shared outage), and 11 of 104,426 closes find their last row 4 h old or more; without the bound the as-of carry shows a level the venue last showed one or two bars earlier, and `oi_log_delta` reads 0 there, then a jump.
- Funding takes no such bound: a funding print carries legitimately until the next settlement, and none is missing (the largest gap between prints is 8 h 47 ms in every perp; `## Out of scope`).
- If wrong: 11 closes carry `None` where a stale level would have stood, which every OI feature already treats as missing.

## D6 — the OI trio runs on the grid level series

- `oi_log_delta_grid_feature`, `oi_zscore_grid_feature` and `oi_momentum_grid_feature`, each `(oi_ts, oi_values, union_ts)`, are `oi_log_delta(levels)`, `oi_zscore(levels, window=180)` and `oi_momentum(levels, lookback=180)` over `levels = oi_grid_levels(oi_ts, oi_values, union_ts)` — spec `00110`'s grid series, never the raw 5-minute source — with `None` propagating as spec `00110` D7 pins.
- The grid is the union's, so a window counts the union's bars, as the arms' own lookbacks do. Two consequences, stated rather than mechanised: a union hole (two in trial 1's window of 12,648 marks) makes the log-delta at the close after it span 8 h and a 180-bar window span 30 days and 4 h while it holds the hole; and the trio warms inside the union's window — the z-score is `None` at the first 179 return indices, the momentum at the first 180, the log-delta at the first — because the OI rows are read whole but the grid is the union's. On the adopted ensemble the warm-up costs no stamp the book holds: its arms hold no position before return index 181 (spec `00128` D4).
- If wrong: nothing new — these are the harness's own functions, fed as its module docstring orders.

## D7 — placement: `cli/alpha/b2.py`, no subject, no registry write, no trial

- The emitters sit in `cli/alpha/b2.py` beside `funding_grid_feature`, spec `00128` D8's emission module: `funding_sign_grid_feature`, `funding_carry_grid_feature`, `oi_grid_levels`, `oi_log_delta_grid_feature`, `oi_zscore_grid_feature`, `oi_momentum_grid_feature`, and the private `_funding_on_close_grid`. `cli/features/derivatives.py` and `cli/research/subjects.py` are not edited.
- Lists in, one list out, `len(union_ts) - 1` values. A column's `binperp_` name (spec `00110` D8) and its `coverage_by_year(close_grid(union_ts), values)` summary (spec `00110` D6) are the consumer's, as `b2-funding-derisk` names and covers `binperp_funding_z30d` (spec `00128` D8).
- No new subject, no registry write, no trial: the emission is infrastructure the next pre-registration names.
- If wrong: a module move is mechanical.

## The known answers

Each is a test in `tests/test_alpha_b2.py`, synthetic, beside the existing ones, which stay as they are:

- the sign run on the close grid counts prints, never bars — the grid-fed run is a different list on the same fixture; an off-cadence print breaks the run and is `None` at the closes whose latest print it is, a dropped print giving a different list;
- the carry sums the latest 90 prints, `None` one print short of its window; an off-cadence print leaves every window holding it `None`, a dropped print giving a different sum; the window is the literal 90;
- every new funding emitter reads a print 30 ms past its hour as that hour's settlement — its value distinct from the one carried before it at that close — and refuses a print 61 s past it by name;
- the truncating-prefix property for every emitter, spec `00128` D2's form: for every `n`, the emitter over `union_ts[:n + 1]` and only the inputs stamped — for a print, its normalised stamp — at or before `union_ts[n - 1] + timedelta(hours=4)`, that cutoff computed by the test, equals the first `n` values of the full run, the full run defined at least ten times — the inputs truncated, never the grid alone;
- the OI level: a row exactly 4 h old at a close is `None` and one a second younger is read; a row 22 s before a close is read at it and one 30 s after it is not, and is read at the next; a placeholder as the bar's last row is `None` at that close, never the row before it; unsorted or tz-naive stamps and unequal lengths are refused by name;
- the OI trio, each on a fixture of two rows per bar, the earlier 1.5 times the later, so the raw-fed feature differs: the log-delta is bar to bar; a 180-bar window of a flat level and one spike scores `[None] * 179 + [0.0, 179 / √180]`; the momentum reads its base 180 bars back; the two windows are the literal 180.

## Out of scope

The 1h grid (D1). The ratio columns: `ratio_features` stays as spec `00110` built it, and no emitter here carries them. The liquidations leg (T0023's own next step). The Bybit funding cross-check. Any subject or registry change. Live serving: the substrate is backtest-only (spec `00110` D9). Funding staleness: the funding substrate is complete per spec `00110`'s measured basis and this spec's, and a funding print carries legitimately until the next settlement.
