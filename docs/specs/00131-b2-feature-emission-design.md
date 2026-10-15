# B2's remaining funding and OI features on the 4h close grid — the funding sign run and accrued carry, the OI level and its trio (design)

**Ruling:** the controller's rulings R1–R11 of 2026-10-14/15, in `.tmp/t0023/decisions.md` of this branch's worktree, made in the unattended run the owner launched at ~23:09Z ("move ahead on milestone 'Research substrate', start with the most relevant topic first. unattended. disregard the wall clock gate, but do not pick up new topic after 07:30Z"); D1–D7 below are R1–R7, D6 as R10 (2026-10-15T00:48:36Z) revised R6's grid and R10a (2026-10-15T01:13:31Z) confirmed its end and the off-mark refusal, D2 and D5 as R11 (2026-10-15T02:36:57Z) amended R2 and R8: a print is read only to its next settlement, `## Out of scope` is R8 less funding staleness, and this header carries R9; each decision carries its ruling's substance, and the `.tmp` file is not kept past the branch. **Ceremony (R9):** design-open — D4's and D5's stamp rulings are new decisions — so this spec and its plan, `zcrypto-plan-review`, subagent-driven execution and the branch trio; branch `research/00131-b2-feature-emission`; no iteration serial minted, an infrastructure branch as 00129 and 00130 were, with no trial. **Topic:** T0023, whose `## Suggested next steps` lists this work as autonomous (its second bullet); the topic stays `partial`. **Goal:** `cli/alpha/b2.py` emits, beside the funding z-score spec `00128` D2/D8 delivered, the rest of B2's funding and OI substrate→feature emission on the 4h close grid — the funding sign run and accrued carry, the OI level, and the OI log-delta, z-score and momentum — each leak-free and proven on known answers, so the next B2 pre-registration names its features instead of building them.

## The measured basis

Every command ran on 2026-10-15 between 00:06 and 00:54Z, the funding tail's at 02:30Z, in this branch's worktree at develop's `f7c447c88`, with `data/derivatives-funding` and `data/derivatives-oi` each linked from the main checkout's `data/`. Stamps, levels and counts only: no return and no feature value was computed. The substrate program, from the worktree root, its OI grid D6's regular grid (re-run at 00:53Z when R10 ruled it):

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
    # The regular close grid: every 4h mark from the first at or after the first row to the first at or after the last.
    grid = pl.DataFrame({"g": pl.int_range(-(-us[0] // H4) * H4, -(-us[-1] // H4) * H4 + 1, H4, eager=True)})
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
ADAUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 249 at 1-262 s past their mark, own mark present 5, next mark present 206, a close's own row late 136; gaps > 300 s 232, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 229; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 7
AVAXUSDT: 487,959 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 468 at 1-262 s past their mark, own mark present 7, next mark present 407, a close's own row late 103; gaps > 300 s 474, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 168; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
BTCUSDT: 618,850 rows 2020-09-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 230 at 1-262 s past their mark, own mark present 5, next mark present 185, a close's own row late 57; gaps > 300 s 353, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 502; closes 12,907, last row >= 4 h old ['2021-02-20T00:00Z', '2024-02-16T20:00Z'], last row a 0.0 14
DOGEUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 311 at 1-262 s past their mark, own mark present 5, next mark present 264, a close's own row late 76; gaps > 300 s 284, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 225; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
DOTUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 407 at 1-262 s past their mark, own mark present 7, next mark present 353, a close's own row late 133; gaps > 300 s 379, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 212; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
ETHUSDT: 488,016 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 175 at 1-262 s past their mark, own mark present 5, next mark present 128, a close's own row late 24; gaps > 300 s 141, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 208; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 5
LINKUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 321 at 1-262 s past their mark, own mark present 8, next mark present 271, a close's own row late 110; gaps > 300 s 296, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 216; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 4
LTCUSDT: 487,973 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 231 at 1-270 s past their mark, own mark present 6, next mark present 184, a close's own row late 65; gaps > 300 s 246, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 176; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 6
SOLUSDT: 487,998 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 236 at 1-278 s past their mark, own mark present 5, next mark present 191, a close's own row late 83; gaps > 300 s 217, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 197; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 7
XRPUSDT: 488,018 rows 2021-12-01 00:00:00+00:00 -> 2026-07-22 23:55:00+00:00; off-mark 222 at 1-262 s past their mark, own mark present 7, next mark present 177, a close's own row late 67; gaps > 300 s 198, largest 2024-02-16 13:30:00+00:00 -> 2024-02-17 00:00:00+00:00; sum_open_interest == 0.0 196; closes 10,171, last row >= 4 h old ['2024-02-16T20:00Z'], last row a 0.0 5
{'closes': 104446, 'stale': 11, 'zero_asof': 60, 'off_mark': 2850, 'own_mark_present': 60, 'late_own_mark': 854}
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
- **Staleness on the regular close grid**: D6's grid — every 4h mark from the first at or after a symbol's first row to the first at or after its last — holds 104,446 marks, BTCUSDT 12,907 and each of the nine 10,171 (R5's 104,426 counted from the first bar's close to the last mark at or before the last row, 20 marks fewer). At 11 the last row is 4 h old or more: 2024-02-16T20:00Z in all ten (the outage's last row 13:30Z, 6 h 30 min old), and BTCUSDT's 2021-02-20T00:00Z.
- **Zero placeholders**: `sum_open_interest == 0.0` on 2,329 rows, BTCUSDT's 502 the most — spec `00110` D5's count, unchanged. At 60 marks the last row inside the bar is one — BTCUSDT 14, the nine 4–7.
- **The funding substrate**: 68,281 prints; 31,212 stamped past the hour, the latest 47 ms past it — every print inside the 60 s settlement tolerance spec `00128` D2 rules; SOL's 101 prints at `interval_hours` ≠ 8 the only off-cadence ones. The largest gap between consecutive prints is 8 h 47 ms in every perp: no settlement is missing between a perp's first print and its last, so consecutive prints truncated to their hour lie at most 8 h apart.
- **The funding substrate's tail**: `uv run python -c 'import glob, polars as pl; [print(p.split("/")[-2], pl.read_parquet(p, columns=["ts"])["ts"][-1]) for p in sorted(glob.glob("data/derivatives-funding/*/funding.parquet"))]'` → `2026-06-30 16:00:00.005000+00:00` for each of the ten perps: the last print, 22 days before the OI substrate's last row (2026-07-22T23:55Z).
- **The emission's callers and the grids the committed subjects read**: `git grep -l -e funding_grid_feature -e close_grid -- cli tests ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*'` → `cli/alpha/b2.py`, `cli/research/subjects.py`, `tests/test_alpha_b2.py`. `uv run python -c 'from cli.research.subjects import SUBJECTS; [print(n, s.intervals) for n, s in SUBJECTS.items()]'` → `record44-crossfreq (1440, 240)`, `record33-combined (1440,)`, and `(240,)` for `b2-funding-derisk`, `b2-arm-a-bar`, `b1-conditioning` and `b1-window-only`: no subject reads a 1h series.
- **A union's holes and the arms' warm-up**, what R10 keeps out of the OI features (D6): spec `00128`'s measured basis counts 12,646 union stamps over trial 1's window, which holds `python3 -c 'from datetime import datetime, timedelta; print((datetime(2026, 6, 30, 20) - datetime(2020, 9, 22)) // timedelta(hours=4) + 1)'` → `12648` 4h marks: two union holes. Spec `00128` D4: the adopted A2 arms hold no position before return index 181, their 180-bar vol and basket lookbacks counting the union's bars.

## D1 — the emission is the 4h close grid only; the 1h grid is dropped

- Every emitter takes the union's 4h bar-open stamps and returns one value per return index, at `close_grid(union_ts)` (`ts[k] + 4h`), the grid spec `00128` D2 rules — the OI emitters computing on their own regular 4h grid and reading it at those closes (D6). No 1h grid is built, and T0023's next step for it closes as dropped, with this reason in the topic.
- Why: spec `00128` D1 calls a same-hour de-risk between 4h boundaries an execution-layer knob and a trial on it its own pre-registration; no hypothesis consumes a 1h grid — closed world: the committed subjects' `intervals`, enumerated in the basis, none of them 60 — and a path no trial reads is untested in use. Spec `00110` D3 named both grids as the harness's reach; it is not edited, and this spec is the record that the 1h emission is not built.
- If wrong: a future 1h hypothesis builds its grid under its own pre-registration, as spec `00128` D1 already requires.

## D2 — one print pipeline for the three funding features

- A private `_funding_on_close_grid(label, feature, prints_ts, prints_rate, prints_interval_hours, union_ts)` holds spec `00128` D2's two rulings and D5's settlement bound once: it refuses unequal lengths and unsorted or tz-naive stamps, truncates each print stamp to its hour and refuses one more than `_STAMP_TOLERANCE` (60 s) past it, maps a print whose `interval_hours` ≠ 8 to `None` (spec `00110` D7: mapped, never dropped), applies `feature` to the print series, and reads it as-of at `close_grid(union_ts)`, a print reaching a close only before the next settlement is due (D5).
- `funding_grid_feature` (the z-score at `B2Config.z_window`, unchanged in signature, and in behaviour at every close less than a settlement past its as-of print, as every close inside a series is — D5), `funding_sign_grid_feature` (`funding_sign_persistence`) and `funding_carry_grid_feature` (`funding_accrued_carry` at D3's window) each call it, with the signature `(prints_ts, prints_rate, prints_interval_hours, union_ts)` — the z-score's keeping its `*, config`.
- `feature` is applied to the prints, never to the grid: T0023's load-bearing warning. A grid-fed sign run counts each print once per bar it carries across — twice on the 4h grid — and a grid-fed 90-value carry sums 15 days of 4h bars, each print twice; both are causal, so no truncating-prefix test can see them, and a known answer does (`## The known answers`).
- `funding_grid_feature`'s existing tests are unchanged — no task's diff removes a line of `tests/test_alpha_b2.py` — and green, and each of the pipeline's rulings and refusals is probed against them as well as against the new emitters' cases — the settlement bound (D5), which no existing case reaches, against a new case of each emitter.
- If wrong: nothing — the refactor is proven by the unchanged tests and the probes on the shared helper.

## D3 — the windows are spec 00110's pre-registration, as module constants

- 30 days, as spec `00110` D7 pre-registered them: `_CARRY_WINDOW = 90` prints at 8 h, `_OI_ZSCORE_WINDOW = 180` and `_OI_MOMENTUM_LOOKBACK = 180` bars at 4 h; the sign run takes no window. They are constants of `cli/alpha/b2.py` beside `_STAMP_TOLERANCE`, not fields of `B2Config`, which is trial 1's overlay configuration and keeps its `z_window` for the z-score alone.
- Why: spec `00110` D7 fixed the windows in days before any result, and changing one after a result is a new trial that spends budget; a field would offer a knob no trial may turn.
- SOL's 101 off-cadence prints: the carry is `None` across them and the 89 prints after them, as the z-score is (spec `00110` D7).
- If wrong: a later trial that wants another window is a new trial anyway.

## D4 — the OI level is `sum_open_interest`, placeholders mapped, as-of on the raw stamps

- The level is `sum_open_interest`, the contract count whose placeholders spec `00110` D5 counts (2,329); `sum_open_interest_value` is the same position priced in USDT, its moves part price, and it carries 101 further zeros on a healthy contract count (spec `00110` D5). `oi_levels_from_raw` runs first (a `0.0` → `None`, spec `00110` D5), then the as-of onto D6's regular grid on the RAW stamps, no normalisation; `oi_grid_levels(oi_ts, oi_values, union_ts)` reads that level at the union's closes.
- Why no normalisation: a stamp is when the venue measured the level, so `source_ts <= grid_ts` admits no look-ahead as it stands — unlike funding's settlement prints, which spec `00128` D2 truncates to the hour they settle. Measured: 2,850 off-mark rows, each 1–278 s past its mark. Measured beside it: an off-mark row stands in place of its own mark's row (60 of 2,850 have both), so the stamp may as well be a late write of the mark's level; either way the level exists at its stamp, and reading it from the stamp never reads it early. At the 854 marks whose own row is stamped late, the level is the row before it.
- A placeholder that is the last row inside the bar makes the level `None` at that mark (60 marks measured), never the level before it: mapping removes a reading, and a fall back to an earlier row would carry one the venue did not show at that stamp (spec `00110` D5's no-imputation rule). Every z-score window holding such a mark is `None` with it.
- If wrong: a late row is read one boundary later than its mark, never earlier.

## D5 — staleness: a level reaches only the close of the bar it lies in, a print only the closes before the next settlement

- A level reaches a mark of D6's grid only if its row's stamp lies inside the bar that mark closes, `mark − 4h < source_ts ≤ mark`; otherwise `None` — a row exactly 4 h old is `None`.
- Why: gaps reach 10 h 30 min in every symbol (one shared outage), and 11 of the regular grids' 104,446 marks find their last row 4 h old or more; without the bound the as-of carry shows a level the venue last showed one or two bars earlier, and `oi_log_delta` reads 0 there, then a jump.
- Funding takes the same bound at its settlement interval: a print reaches a close only if `close − 8h < hour`, `hour` the print's stamp truncated to its hour (D2); otherwise `None` — a print exactly 8 h old is `None`, since the next settlement is due at that close. Inside a series no close is that far from its print, since consecutive truncated prints lie at most 8 h apart (the basis), so the bound changes no value there; past a series' last print — every perp's is 2026-06-30T16:00Z, 22 days before the OI substrate's last row — the as-of carry would show that print as current for as long as a union runs on.
- If wrong: 11 marks carry `None` where a stale level would have stood, and every z-score window holding one is `None` with it — the 30 days from 2024-02-16T20:00Z in every symbol and from 2021-02-20T00:00Z in BTCUSDT — and the momentum at that mark and 180 marks after it; a funding close past a series' last print reads `None` where a carried print would have stood.

## D6 — the OI level and its trio on a regular 4h grid over the OI substrate's own span, read at the union's closes

- The grid (R10): every 4h mark — a multiple of 4 h from 1970-01-01T00:00Z, the marks every Kraken 4h bar opens and closes on — from the first at or after the series' first row to the first at or after its last row. R10 says "to its last row", and R10a settles it: the last mark is the close of the bar holding the last row, because ending at the last mark at or before it would make the close after a series' newest row read `None` in a run whose rows stop there and a level in a run whose rows go on — a value decided by rows stamped after it, which the truncating-prefix test refuses. A mark past that end could only find a row 4 h old or more, which D5 makes `None` anyway, so the end hides no level.
- On that grid: the level (D4, D5), then `oi_log_delta(levels)`, `oi_zscore(levels, window=180)` and `oi_momentum(levels, lookback=180)` — spec `00110`'s grid series, never the raw 5-minute source — with `None` propagating as spec `00110` D7 pins. `oi_grid_levels`, `oi_log_delta_grid_feature`, `oi_zscore_grid_feature` and `oi_momentum_grid_feature`, each `(oi_ts, oi_values, union_ts)`, run through one private pipeline `_oi_at_union_closes(label, feature, oi_ts, oi_values, union_ts)`, which holds D4, D5 and this decision once, as `_funding_on_close_grid` holds spec `00128` D2's rulings.
- The lookup: each union close `ts[k] + 4h` reads the grid's value at that mark exactly; a close before the span's first mark or after its last reads `None`, and so does every close of an empty series; a union stamp off a 4h mark is refused by name, since its close would match no mark and read `None` silently. A series spanning fewer than two marks reaches the harness's own length rule (`FeatureError`) in a trio emitter, as a funding series of fewer than two prints does.
- Why (R10): spec `00110` pins a 30-day window as 30 days. On the union's own grid a union hole (two in trial 1's window of 12,648 marks) would stretch the log-delta at the close after it to 8 h and a 180-bar window to 30 days and 4 h, and every trial window would re-warm the trio inside itself — the z-score `None` at its first 179 return indices, the momentum at its first 180. The funding features run over the print series whole; the OI features over their own series whole is the same treatment, and a union opening 30 days or more into the OI span reads them warm from its first close, save where a `None` level (D4, D5) lies in a window. The level alone is the same on either grid, since D4 and D5 read only the bar a mark closes.
- If wrong: one grid construction and a lookup; no feature value moves at a stamp both grids share outside the warm-up and the holes.

## D7 — placement: `cli/alpha/b2.py`, no subject, no registry write, no trial

- The emitters sit in `cli/alpha/b2.py` beside `funding_grid_feature`, spec `00128` D8's emission module: `funding_sign_grid_feature`, `funding_carry_grid_feature`, `oi_grid_levels`, `oi_log_delta_grid_feature`, `oi_zscore_grid_feature`, `oi_momentum_grid_feature`; the private `_funding_on_close_grid`, `_oi_at_union_closes`, `_oi_marks` and `_mark_at_or_after`; and the constants `_EPOCH`, `_SETTLEMENT_INTERVAL`, `_CARRY_WINDOW`, `_OI_ZSCORE_WINDOW` and `_OI_MOMENTUM_LOOKBACK`. `cli/features/derivatives.py` and `cli/research/subjects.py` are not edited.
- Lists in, one list out, `len(union_ts) - 1` values. A column's `binperp_` name (spec `00110` D8) and its `coverage_by_year(close_grid(union_ts), values)` summary (spec `00110` D6) are the consumer's, as `b2-funding-derisk` names and covers `binperp_funding_z30d` (spec `00128` D8).
- No new subject, no registry write, no trial: the emission is infrastructure the next pre-registration names.
- If wrong: a module move is mechanical.

## The known answers

Each is a test in `tests/test_alpha_b2.py`, synthetic, beside the existing ones, which stay as they are:

- the sign run on the close grid counts prints, never bars — the grid-fed run is a different list on the same fixture; an off-cadence print breaks the run and is `None` at the closes whose latest print it is, a dropped print giving a different list;
- the carry sums the latest 90 prints, `None` one print short of its window; an off-cadence print leaves every window holding it `None`, a dropped print giving a different sum; the window is the literal 90;
- every new funding emitter reads a print 30 ms past its hour as that hour's settlement — its value distinct from the one carried before it at that close — and refuses a print 61 s past it by name;
- every funding emitter reads its last print at the closes before the next settlement is due and `None` from that close on, and refuses by name each check's silent shape — an intervals list longer than the prints, a repeated print stamp, a repeated union stamp;
- the truncating-prefix property for every emitter, spec `00128` D2's form: for every `n`, the emitter over `union_ts[:n + 1]` and only the inputs stamped — for a print, its normalised stamp — at or before `union_ts[n - 1] + timedelta(hours=4)`, that cutoff computed by the test, equals the first `n` values of the full run, the full run defined at least ten times — the inputs truncated, never the grid alone;
- the OI level: a row exactly 4 h old at a mark is `None` and one a second younger is read; a row 22 s before a close is read at it and one 30 s after it is not, and is read at the next; a placeholder as the bar's last row is `None` at that close, never the row before it; a union close before or after the rows' span reads `None`, as does every close of an empty series; a union stamp off a 4h mark, unsorted, repeated or tz-naive stamps and unequal lengths either way are refused by name;
- the OI trio, each on a fixture of two rows per bar, the earlier 1.5 times the later, so the raw-fed feature differs: the log-delta is bar to bar; a 180-bar window of a flat level and one spike scores `[None] * 179 + [0.0, 179 / √180]`; the momentum reads its base 180 bars back; the two windows are the literal 180; a union hole leaves the next log-delta a single 4 h step; a union opening inside the rows' span reads the z-score warm at its first close; a placeholder as a bar's last row leaves every z-score window holding its mark `None`; and the prefix fixture's union opens 30 bars into the rows' span, misses one open and closes one bar past the rows, each trio emitter's defined count on it exact, since a level that should be `None` reaching the feature is causal and only the count sees it.

## Out of scope

The 1h grid (D1). The ratio columns: `ratio_features` stays as spec `00110` built it, no emitter here carries them, and their emission stays a next step on T0023. The liquidations leg (T0023's own next step). The Bybit funding cross-check. Any subject or registry change. Live serving: the substrate is backtest-only (spec `00110` D9).
