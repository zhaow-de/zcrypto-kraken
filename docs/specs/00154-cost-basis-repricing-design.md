# The deployable's cost basis re-priced — record 47's book rebuilt at the fee and spread the owner picks, its registered figures read against the bar it passed

Iteration `iter-200`, family P1, topic [T0214](../open-topics/T0214-cost-basis-re-priced-at-rung-2.md), beside T0090 (archived) and [T0122](../open-topics/T0122-ongoing-register-kill-criteria.md). T0214's decision step, prepared ahead of its trigger: a new P1 subject rebuilds registry record 47's book over the data it was adopted on at a re-priced `fee_per_side` and `spread_per_side`, re-computes its registered figures at that basis and reads them against the benchmark-relative bar record 44 passed and record 47 inherited. The rate is the owner's pick, open in this pair (D3) and written into D3 before the hash; the rule is pre-registered by this spec's sha256, which a new `docs/reference/trial-registry.jsonl` record stores. Serials: iter-200 and 00154 are the next past iter-199 and 00153, both merged (#787).

## The measured basis

Measured 2026-10-30 on `zcrypto-ops`, the workstation, in the branch's worktree over a symlink to the main checkout's `data/ohlc-full`, read-only. Every book below is built at the registered basis, 0.0040 + 0.0020 a side, or at its two registered stress rungs ×1.5 and ×2.0; none at a candidate rate (D9).

- **The deployable** is record 47 (`P1-crossfreq-fixedthird-twelve-leg-basket-btczero`, iter-139, adopted 2026-08-15T00:30:58Z, `n_trials_in_family` 5): `ann_sharpe_noc` 1.5609, `ann_sharpe_noc_decisive` 1.5583, `bench4h_sharpe_full` 1.2128, `bench4h_sharpe_decisive` 1.2447, `cap_breach_bars` 1318, `governor_engaged_bars` 7302, `maxdd` 0.1357, `maxdd_pre_governor` 0.1866, `cost_stress_1_5x_sharpe_ann` 1.3029, `cost_stress_2x_sharpe_ann` 1.2106, `dsr` 1.0, the seven SPA p-values, `var_trials_4h` 1.3058096692086857e-05, `decisive_start` 1380, `n_bars_compared_4h` 27337. `LEGACY_INCUMBENTS` in `cli/research/subjects.py` maps 47 to `record44-crossfreq`, whose `_crossfreq_book` rebuilds that book at the subject's own literal `_RECORD44_CONFIG = CrossfreqSystemConfig(fee_per_side=0.0040, spread_per_side=0.0020)` (`cli/research/subjects.py:243`).
- **The bar it passed** is record 44's, `[iter-081]` in `docs/research/13.phase5-decisions.md`: Sharpe-primary against incumbent trial 43, with every ratified leg passing against the 4h-rebuilt benchmark — SPA at blocks 30 and 102 × seeds 42, 7 and 1234 on the decisive window (record 44's notes: "SPA grid max p 0.0060"), DSR at P1's count with `var_trials` the A1 family's daily per-period Sharpes' variance over 6, the benchmark-relative worst calendar-year slice with the stub years out, and cost stress ×1.5 re-governed. The legs' thresholds are `cli/alpha/killbar.py`'s: `dsr > DSR_PASS_THRESHOLD` (0.95), `spa_p_value < 0.05`, `cost_stress_sharpe > 0`, `beats_benchmark_worst`. Record 47 passed by identity with record 44's book. The incumbent comparison was taken out of the go/no-go's basis by the owner on 2026-08-03 (T0125: the gate rests on the benchmark-relative legs), and T0148's re-read found the 43-against-44 ordering changing sign 117 times over ×0.70–×3.00 of the cost.
- **Known answer 1, the book**: `uv run zcrypto research eval --subject record44-crossfreq --dataset ohlc-full` → `ann_sharpe_noc` 1.560907676587497, `per_period_sharpe_4h` 0.03335455562889141, `ann_sharpe_ungoverned` 1.5404105635409155, `cap_breach_bars` 1318, `governor_engaged_bars` 7302, `n_periods` 27337, span 2013-09-10 00:00 → 2026-03-31 20:00, `vouched: checked (36 vouched hashes)`; 3.4 s wall.
- **Known answer 2, the legs**: `uv run python -m cli.portfolio.record44_legs` (the committed re-derivation, `CrossfreqSystemConfig()` at 0.006 a side, the benchmark charged the same) → `ann_sharpe_noc` 1.560907676587497, `ann_sharpe_noc_decisive` 1.5583341567194398, `bench4h_sharpe_full` 1.2128451567638199, `bench4h_sharpe_decisive` 1.2446890489958136, `cap_breach_bars` 1318, `governor_engaged_bars` 7302, `per_period_sharpe_4h` 0.03335455562889141, `var_trials_4h` 1.3058096692086857e-05, `dsr` 0.9999994822040257 (at its `N_TRIALS_IN_FAMILY` 4), `spa_p_full` 0.001999000499750125, `spa_p_decisive` 0.004497751124437781, `spa_grid_b30_s7` 0.004997501249375313, `spa_grid_b30_s1234` 0.005997001499250375, `spa_grid_b102_s42` 0.00399800099950025, `spa_grid_b102_s7` 0.005997001499250375, `spa_grid_b102_s1234` 0.005997001499250375, `worst_slice_relative_pass` 1 (book worst 2022 −0.02898802673890783, benchmark worst 2014 −0.0797494372250268, 12 slices compared); every SPA cell bit-identical to the registry's; 84.5 s wall.
- **Known answer 3, the stress rungs, the drawdowns, the live state, the order sizes and reading 9's mapping** — the fence below, run from the worktree root with `uv run python`, at 2026-10-30T15:09:44Z, printing:
  - `maxdd 0.1356768814775332 0.18657983630785457` — `max_drawdown` of the governed and the ungoverned net.
  - `stress 1.5 1.3028688330561256` and `stress 2.0 1.2106292366788787` — each a rebuild at `dataclasses.replace(_RECORD44_CONFIG, fee_per_side=0.0040·m, spread_per_side=0.0020·m)`, bit for bit the full-precision values record 47's notes give and `cli/portfolio/record43_book.py`'s re-costed axis (`record44_stress_axis`, `stressed_sharpe`) gives; each rebuild 1.35 s.
  - `live 6885 0.7508603998368656 flat 3680` — the live state, return `k` whose row-`k` sleeve positions hold B and A1 at exactly 0 on every asset and A2 non-zero on one: 6,885 returns at annualized Sharpe 0.7509, the 3,680 fully flat beside them, T0090's registered-basis conditional (0.7509) and T0124's split (6,885 + 3,680 = 10,565), reproduced; the other returns read 1.9424.
  - `changes 98716 … 103.64164853138676 0.9903663033348191 0.9995644069856964` — the per-cycle, per-leg change of the governed target at a €1,000 NAV, rung 3's: median €0.023, 90th percentile €1.19, 99th €9.73, largest €103.64; 99.04 % at or below €10, 99.96 % at or below €50. The engine places a leg's accumulated change once it clears the venue's minimums, so an order is a sum of such changes, bounded by the leg's range under the caps: at most (0.20 + 0.10) × €1,000 = €300.
  - The per-leg share of the turnover the builder charges, `multipliers[k]·|limited[k] − limited[k−1]|` summed over the full build: ADA 0.0652, AVAX 0.0239, BTC 0.3294, DOGE 0.0409, DOT 0.0426, ETH 0.1547, LINK 0.0475, LTC 0.1559, SOL 0.0337, XRP 0.1062; over the 6,885 live-state returns: BTC 0.4579, LTC 0.1192, ETH 0.1009, XRP 0.1028, the other six 0.0252–0.0688.
  - Reading 9's table re-read by weight, each leg the mean of its bid and ask over the span, the fee `0.0040·maker + 0.0080·(1 − maker)` at the weighted maker share and the spread the remainder — equal weights: €100 cost 0.005844297387723215, maker 0.6678294573643411, fee 0.005328682170542635, spread 0.0005156152171805796; €1,000 cost 0.006571755031268408, maker 0.49738372093023253, fee 0.00601046511627907, spread 0.0005612899149893382. By the full build's turnover: €100 0.00537945106143329, maker 0.7540825984783963, fee 0.004983669606086415, spread 0.0003957814553468752; €1,000 0.006046663346358638, maker 0.6053953259659298, fee 0.0055784186961362805, spread 0.00046824465022235733. By the live-state turnover: €100 0.005286940967380295, €1,000 0.0058987671462552484.

```python
import json
from dataclasses import replace

import numpy as np

from cli.portfolio.crossfreq_system import apply_whole_book_limits, build_crossfreq_system_fast
from cli.registry.observed import ObservedReader
from cli.research import command, subjects
from cli.risk import apply_position_caps
from cli.validation.metrics import max_drawdown, sharpe

daily_ts, daily_prices, h4_ts, h4_prices, result = subjects._crossfreq_book(ObservedReader(command._DATA_ROOT), "ohlc-full", None)
n, A, c, sp = result.n_periods, subjects._ASSETS, subjects._RECORD44_CONFIG, result.sleeve_positions
ft, g, mult = result.final_targets, result.governed_net, result.multipliers
print("maxdd", max_drawdown(g), max_drawdown(result.ungoverned_net))
for m in (1.5, 2.0):
    stressed = replace(c, fee_per_side=c.fee_per_side * m, spread_per_side=c.spread_per_side * m)
    print("stress", m, sharpe(build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=stressed).governed_net, periods_per_year=2190))
d = np.array([abs(ft[a][k] - ft[a][k - 1]) * 1000 for a in A for k in range(1, n + 1) if ft[a][k] != ft[a][k - 1]])
print("changes", len(d), np.median(d), np.percentile(d, 90), np.percentile(d, 99), d.max(), np.mean(d <= 10), np.mean(d <= 50))
state = [(any(sp["B"][a][k] for a in A), any(sp["A1"][a][k] for a in A), any(sp["A2"][a][k] for a in A)) for k in range(n)]
live = [k for k in range(n) if state[k] == (False, False, True)]
print("live", len(live), sharpe([g[k] for k in live], periods_per_year=2190), "flat", state.count((False, False, False)))
third = 1 / 3
comb = {a: [third * sp["B"][a][k] + third * sp["A1"][a][k] + third * sp["A2"][a][k] for k in range(n + 1)] for a in A}
lim = apply_whole_book_limits(apply_position_caps(comb, long_cap=c.long_cap, short_cap=c.short_cap))


def shares(ks):
    t = {a: sum(mult[k] * abs(lim[a][k] - (lim[a][k - 1] if k else 0.0)) for k in ks) for a in A}
    return {a: t[a] / sum(t.values()) for a in A}


r9 = json.loads(open("docs/reference/reading-ledger.jsonl").read().splitlines()[-1])
assert r9["reading_id"] == 9
ct = r9["metrics"]["cost_table"]


def leg(a, size, key):
    return (ct[f"{a}/EUR"][f"bid|{size}"]["span"][key] + ct[f"{a}/EUR"][f"ask|{size}"]["span"][key]) / 2


for name, w in (("equal", dict.fromkeys(A, 0.1)), ("turnover", shares(range(n))), ("turnover-live", shares(live))):
    print(name, {a: round(v, 4) for a, v in w.items()})
    for size in ("S0", "S1"):
        cost, maker = (sum(w[a] * leg(a, size, k) for a in A) for k in ("mean_cost", "maker_share"))
        fee = 0.0040 * maker + 0.0080 * (1 - maker)
        print(f"  {size} cost {cost!r} maker {maker!r} fee {fee!r} spread {cost - fee!r}")
```

- **Reading 9** (iter-199, spec 00153, the last line of `docs/reference/reading-ledger.jsonl`): the engine's ladder replayed at the cycle boundaries over 2026-08-01 → 2026-10-25, a side's cost against the mid at the post — a maker fill `s·(fill − mid)/mid + 0.0040`, a fallback `s·(box-end touch − mid)/mid + 0.0080` — the blend over the ten EUR legs weighted equally: €100 0.005844297387723214 a side (95 % interval 0.005733845814134574 to 0.005944583541584537), €1,000 0.006571755031268408 (0.006465195880333121 to 0.006672130869453353), each over 516 boundaries. Every EUR leg's side holds 516 priced posts at each size and none unpriced, so the blend is the plain mean of the twenty leg-side means, which the equal-weight line above re-reads at 0.005844297387723215 and 0.006571755031268408, the €100 figure one ulp from the stored one. Its departures leave the sign of its net bias unread (spec 00153 D2; the `[iter-199]` entry in `docs/research/14.phase6-decisions.md`).
- **Rung 2's own point** (T0214; `docs/reference/rung2-box/days.md`): to 2026-10-25, 25 fills, maker 96.3 % / taker 3.7 % of the priceable notional. The tracking report's proposal over the box is not read: it needs the box's exit, the report's `--until 2026-11-01`, Kraken's ledger export over the box and the journal's copy (`infra/runbooks/engine-procedures.md` § engine-rung-2-box, step 9 items 2 and 3). The report proposes a fee term alone — `cost_blend` in `cli/engine/tracking.py` returns `proposed_fee_per_side`, the notional-weighted fee over the priced fills — and reads no spread.
- **The fee terms**: Kraken tier 1, maker 0.0040 and taker 0.0080 a side (`docs/reference/kraken-fee-schedule.md`); a margin open pays a 2 bps margin-opening fee beside the spot fee, and a margin position its rollover, neither carried by the fee term (T0214's findings); the builder charges `cost_per_side · turnover` and nothing else (`cli/portfolio/crossfreq_system.py`).
- **The shared default is on the live path**: the engine's cycle builds with `CrossfreqSystemConfig()`'s defaults (`build_crossfreq_system_fast(model_daily, model_daily_ts, model_h4, model_h4_ts)`, `cli/engine/cycle.py:677`), the drawdown governor reads the net-of-cost series (`daily_cadence_governor(noc + [0.0], …)`, `cli/portfolio/crossfreq_system.py:713`), the gate cache's `replay_fingerprint` digests `repr(config)` (`cli/engine/gate_cache.py:165`), and the tracking report reads the default's two terms (`cli/engine/tracking.py:348`). Every subject pins its own literal (spec 00129 D5), held by `tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move`.
- **P1's count**: records 33, 35, 43, 44, 47 and 63 — six; this record is the seventh.

## Operating model

- **One machine, one controller.** Candidate (a)'s read, the basis check, the hash and the run are the controller's, on `zcrypto-ops`, in the branch's worktree. Candidate (a) is read by `zcrypto engine tracking-report` over the NAS's copy of the engine journal, `/mnt/zhao-crypto/engine-journal` (a read-only mount), and the ledger export the owner downloads from Kraken; the report writes nothing. `data/ohlc-full` is a symlink to the main checkout's set, read-only, unlinked before the worktree goes. No dispatch links or reads it.
- **One writer of each shared file.** `zcrypto research eval --register` appends one record to the branch's `docs/reference/trial-registry.jsonl` and two lines to the main checkout's `.local/trial-attempts.jsonl` (`cli/registry/attempts.py`), its first before the build and its last before the print; no other process writes either during the run. No daemon, timer, host, venue or live engine is touched, and the engine's builder default is not changed (D10).

## The question and its rule

At the cost the deployable's execution is now measured to pay — the rate the owner picks from D3 — does record 47's book, rebuilt over the in-sample data it was adopted on, still clear the benchmark-relative bar it passed at the registered 0.006 a side? The reading is a re-quote of the same construction on the same data, not out-of-time evidence: a pass re-validates the record at the new basis; a fail is a finding to the owner, never a retirement.

## D1 — the pick of the work: the owner's word

- The owner's word of 2026-10-30, verbatim: "go ahead with 1 and 2 after the box-day copy" — item 1 as put to the owner, verbatim: "Prepare the re-pricing of the deployable's cost basis (T0214). T0214's trigger is 30 euro fills from rung 2; rung 2 had 25 by 10-25, so it could fire within days. The re-pricing is a new registry record that re-validates the deployable at the new rate. I can write its spec now, with reading 9's €100 0.005844 and €1,000 0.006572 as one candidate rate beside the tracking report's. Then it can run the day the trigger fires; picking the rate stays your decision."
- **A new P1 trial, never a reading or an edit in place**, among three: (1) a new registry record of a ruled P1 subject at the picked basis — T0214's decision step and the owner's ruling of 2026-09-25 that the re-pricing is "a new registry record", and §12's cost-basis term "resolves once rung 2's measured blend re-prices the record as a new registry record". Chosen. (2) A no-slot reading — a reading stores no verdict, and the basis the go/no-go reads would rest on no record. (3) Moving `CrossfreqSystemConfig`'s defaults in place — it re-prices the live governor with no validation, and every figure read at the default moves at once (spec 00129 D5).

## D2 — the instrument

- **The book**: record 47's, `build_crossfreq_system_fast` over the ten EUR assets at 1440 and 240 minutes through `_crossfreq_book`'s reads, over `ohlc-full` whole — 2013-09-10 00:00 → 2026-03-31 20:00, no window — at the basis `dataclasses.replace(_RECORD44_CONFIG, fee_per_side=<f>, spread_per_side=<s>)`, `<f>` and `<s>` D3's pick, every other field record 47's. `replace` and never `CrossfreqSystemConfig(…)`: a constructor reads the shared defaults, which a later re-price of the engine's default would move.
- **The stress rungs**: the book rebuilt at `replace(basis, fee_per_side=<f>·m, spread_per_side=<s>·m)` for `m` 1.5 and 2.0, both terms scaled. At the registered basis the rebuild reproduces record 47's two stress figures bit for bit (the measured basis), so a rebuild is the registered stress axis.
- **The benchmark**: `benchmark_4h_net_of_cost(h4_prices, cost_per_side=basis.cost_per_side)` (`cli/portfolio/record44_legs.py`), charged the same float the book is. **Author's call**, among two: (1) the benchmark at the book's basis — record 44's bar charged both at 0.006 a side (`rederive_record44_legs`), so the bar is the same comparison at a new cost. Chosen. (2) The benchmark frozen at 0.006 — it moves the bar by the benchmark's own cost change, crediting the book with a cut its comparator is denied, or charging it one.
- **The instrument check**: the same reads built at the registered basis, `_RECORD44_CONFIG`, give 27,337 returns and an annualized governed Sharpe within 0.00005 of 1.5609 — record 47's book; otherwise the rule gives no verdict (D5).
- **The in-sample guard**: a read holding a 4h bar stamped after 2026-03-31 20:00, or a daily bar after 2026-03-31, is refused before any book is built — the spent holdout window, 2026-04-01 → 2026-07-09, and every later bar stay unread as returns. A window is refused: the book is the full build.

## D3 — the rate: the owner's pick, OPEN

- **What the terms cover.** `fee_per_side` is the venue's trade fee on a fill, maker 0.0040 or taker 0.0080 a side, blended over the share of each; the 2 bps margin-opening fee and the rollover stay outside it and outside the book, as today. `spread_per_side` is what an order gives up against the mid at its post — the crossing, the adverse selection, the slippage. The record's figures read their sum alone (`cost_per_side`); the split says which term a later measurement re-prices — the tracking report proposes against `fee_per_side` alone.
- **Candidate (a), the tracking report over rung 2's box** — `uv run zcrypto engine tracking-report --journal-dir /mnt/zhao-crypto/engine-journal --since 2026-10-05 --until 2026-11-01 --gate-from 2026-W45 --ledger-export <the box's export>.csv`, the exit report's command (runbook step 9 item 2), read once the box has exited on 2026-11-01 and the export is in hand. Its fee term: the venue's own figure — the report's `fees on the matched rows` over the `basis:` line's notional — when the ledger reconciles (status not `FAILED`) and every priced fill is matched, the journal's `fee per side: realized` beside it, since the journal rounds a fill's fee to the cent (T0214); otherwise the journal's figure with the reason stated. Its spread term: 0.0020, the registered headroom — the report reads no spread, and the spread's re-pricing is its own step (T0090's ruling of 2026-09-25). Its population is stated with it — fills, notional, maker and taker shares — and T0214's trigger, 30 euro fills, is read against the fill count. As arithmetic and not a reading: were every fill of rung 2's 96.3 % / 3.7 % blend to 2026-10-25 charged the tier-1 rates, the fee term would be 0.004148 and the basis 0.006148, ×1.025 of 0.006.
- **Candidates (b), reading 9 per size and per weighting.** The sum is reading 9's cost at the size read; the fee term is the replay's blended fee at its maker share, `0.0080 − 0.0040 · maker`; the spread term is the remainder; each sum is the two terms' float sum, `cost_per_side` (the measured basis):

| candidate | `fee_per_side` | `spread_per_side` | sum | of 0.006 |
| --- | --- | --- | --- | --- |
| (b1) €100, legs equal — reading 9's blend | 0.005328682170542635 | 0.0005156152171805796 | 0.005844297387723215 | ×0.974 |
| (b2) €1,000, legs equal — reading 9's blend | 0.00601046511627907 | 0.0005612899149893382 | 0.006571755031268408 | ×1.095 |
| (b3) €100, legs by the book's turnover | 0.004983669606086415 | 0.0003957814553468752 | 0.00537945106143329 | ×0.897 |
| (b4) €1,000, legs by the book's turnover | 0.0055784186961362805 | 0.00046824465022235733 | 0.006046663346358638 | ×1.008 |

- **The size at rung 3.** Rung 3 trades a €1,000 NAV: every per-cycle change of a leg's target is at most €103.64 and 99.96 % are at or below €50, and an order is bounded by its leg's range, €300 (the measured basis). €100 is the read size nearest rung 3's orders, at or above every per-cycle change but the few between €100 and €103.64; €1,000 is above every order rung 3 places. Spec 00153 names why a smaller order's maker share is at least the €100 one at one post; it bounds no cost.
- **The weighting.** Reading 9 weights the ten legs equally; the book charges each leg's cost on its own turnover, and BTC/EUR, ETH/EUR and LTC/EUR carry 64.0 % of it, AVAX/EUR, DOGE/EUR, DOT/EUR and SOL/EUR 14.1 %. The turnover weighting carries no interval: reading 9's bootstrap is over its equal-weight series.
- **What no candidate reads.** Reading 9 is a replay whose net bias is unsigned (spec 00153 D2), at both sides of every boundary whatever the deployable's plan holds; (a) is a live point at rung 2's box sizes, its spread unmeasured. The candidates fall inside the range T0090's table quotes, ×0.7017 to ×1.4033 of 0.006, yet no figure is read off it: the governor re-engages on the net-of-cost series, so a cost between two quoted points can read above or below both (T0090).
- **The pick**: OPEN — written here before the hash as the owner's word, verbatim, the candidate it names or a pair the owner gives by value, and `<f>` and `<s>` as the two literals the subject carries. A pick whose sum is 0.006 re-prices nothing: no run, and T0214 records the basis as standing.

## D4 — the figures, re-computed at the picked basis

- Record 47's registered figures by their registry names, each over the basis build: `ann_sharpe_noc`, `ann_sharpe_noc_decisive` (returns from index 1380), `per_period_sharpe_4h`, `bench4h_sharpe_full`, `bench4h_sharpe_decisive`, `cap_breach_bars`, `governor_engaged_bars`, `maxdd` (the governed net's `max_drawdown`), `maxdd_pre_governor` (the ungoverned net's), `cost_stress_1_5x_sharpe_ann`, `cost_stress_2x_sharpe_ann` (D2's rungs, annualized), `var_trials_4h` (1.3058096692086857e-05, P1's since `[iter-080]`), `dsr`, `spa_p_full`, `spa_p_decisive` and the five `spa_grid_*` cells.
- **The SPA cells** as `rederive_record44_legs` computes them: the outperformance `book − benchmark` a return; the headline cell, mean block 30 and seed 42, over the full series (`spa_p_full`) and over the decisive window (`spa_p_decisive`); the grid cells at blocks 30 and 102 × seeds 7 and 1234, and block 102 × seed 42, each over the decisive window; 2,000 resamples (`cli/portfolio/record44_legs.py`'s `SPA_HEADLINE_BLOCK`, `SPA_HEADLINE_SEED`, `SPA_GRID`, `N_RESAMPLES`).
- **The DSR**: `deflated_sharpe_ratio(per_period_sharpe_4h, 27337, n_trials=7, var_trials=1.3058096692086857e-05)` — P1's true count with this record (D7), skew and kurtosis at their defaults.
- **The worst slice**: `benchmark_relative_worst_slice` over `calendar_year_slices` of the governed book and of the benchmark, each return in its close stamp's year, 2013 and 2026 out.
- **The basis itself**: `fee_per_side`, `spread_per_side` and `cost_per_side` as the record's metrics, so the record states its rate by value.
- Not re-computed: record 47's identity and construction figures (`criterion_identity`, `basket_legs`, the `*_vs_record44` diffs, the union bar counts, `incumbent_trial44_*`) — none depends on the cost.

## D5 — the rule, pre-registered

- **The instrument check first** (D2): 27,337 returns and a Sharpe within 0.00005 of 1.5609 at the registered basis, else no verdict — the data no longer rebuilds record 47's book, an instrument finding kept as a reading with no trial spent.
- **The legs**, each at the picked basis: `dsr_pass` — `dsr` above 0.95; `spa_pass` — the largest of the six decisive-window p-values (`spa_p_decisive` and the five grid cells) below 0.05; `cost_stress_pass` — `cost_stress_1_5x_sharpe_ann` above 0; `worst_slice_relative_pass` — `beats_benchmark_worst`. `passes` — all four.
- **Verdict**: `passes` → `adopt`: record 47's book clears its bar at the re-priced basis, the deployable re-validated there. Any leg failing → `park`: a finding to the owner, by value. Never `reject`: retiring the deployable is the owner's, under T0122's ratified production kill criteria, which this record neither replaces nor moves.
- **The incumbent comparison is not read**: the go/no-go rests on the benchmark-relative legs (T0125), and the 43-against-44 ordering is unstable in the cost (T0148).

## D6 — the reads beside the rule, never in it

- **`registered_basis_returns`, `registered_basis_sharpe`**: the instrument check's two reads.
- **`conditional_live_sharpe`, `conditional_live_bars`**: the governed book's annualized Sharpe over the live-state returns and their count — the returns `k` whose row-`k` sleeve positions hold B and A1 at exactly 0 on every asset and A2 non-zero on at least one, the convention the measured basis reproduces at the registered basis (6,885, 0.7508603998368656). It is the go/no-go's model-consistency baseline (T0124) at the new basis; 0.0 when fewer than 2 such returns exist or they are all equal, read with the count.
- **`multipliers_moved`**: the completed rows `k < n` at which the governor's multiplier at the picked basis differs from the registered basis's — how far the record's book departs from the book the engine trades while its default stays (D10).

## D7 — the family, the count and the record

- **Family P1**, unbudgeted (`cli/registry/budget.py`'s `BUCKET_OF["P1"]` is `None`). `n_trials_in_family` 7: P1's six records and this one. A P1 record landing on `develop` before the run moves the count — a change to this spec before the hash, never after. Seeds 42, 7 and 1234, the SPA cells' (D4), as record 47 carries them; the builds are deterministic.
- **The record** names record 47, the candidate picked and its source in its variant and notes, with the basis by value and this spec's hash.

## D8 — the subject and its refusals

- **A new ruled subject**, `p1-reprice`, in `cli/research/subjects.py`: the `record44-crossfreq` grids and assets, D2's builds at `_RECORD44_CONFIG` and at the basis literal `_P1_REPRICE_CONFIG`, D4's figures, D5's rule and D6's reads, `family="P1"`, `n_trials=7`, `spec` this file. The scoring is a new module, `cli/portfolio/repricing.py`, over the price reads the subject hands it and the two configs, so it is proven on synthetic prices at any basis before the pick exists.
- **It refuses**, each with a `SubjectError` naming the cause: a `--window`; a read holding a bar past the in-sample end (D2), before any book is built — `ohlc-rolling` read as of any day after 2026-03-31, and any set holding the spent holdout window.
- **Proven on known answers before it reads the real set**: each figure against its own computation over a synthetic book at a test basis; the instrument check at its edges; the stress rungs scaling both terms and keeping every other field; the benchmark charged the basis's cost; each leg at its threshold; the live state at its row; a bar one step past the in-sample end refused with no build.

## D9 — the hash rule and the order of work

- **Before this spec's hash nobody computes record 47's book over the real data at any basis but the registered 0.0040 + 0.0020 and its registered stress rungs ×1.5 and ×2.0** — through the code, a program or arithmetic. The subject and its scoring are proven on synthetic prices; candidate (a) is a read of the engine journal and the venue's ledger, never of the book.
- **The order**: the scoring (now); candidate (a)'s read once the box has exited; the owner's pick, written into D3 with the subject's literal; the subject; the whole-branch read; the basis check at the registered basis, the module's own figures against record 47's; the hash; the run with `--register`; the record and its entry; T0214, with T0090's rows re-quoted against the record.

## D10 — what a verdict changes

- **Nothing on the live path.** The engine's cycle and the tracking report keep reading `CrossfreqSystemConfig()`'s defaults, 0.0040 + 0.0020. Moving them to the record's basis is the owner's decision on the record and an engine change of its own: it moves the live governor on `multipliers_moved` rows' worth of history, the gate cache's fingerprint, and every figure read at the default.
- **`adopt`**: the go/no-go's cost-basis term (§12, term (b)) reads this record, its `conditional_live_sharpe` beside the registered 0.7509; T0090's table is re-quoted against it in T0214's file, T0090's rows quoted as they stand and never edited; T0214 is resolved. Whether a pick of (b) — a replay, not rung 2's measured blend — resolves §12's term or leaves it open until rung 3's fills is the owner's, asked with the pick.
- **`park`**: a finding to the owner by value — each failing leg beside its threshold and beside record 47's figure; T0214 stays partial on the owner's ruling; the deployable stands.
- **The instrument finding**: a reading, no trial spent and no count frozen; T0214 records it and names no next run.

## Out of scope

Moving the builder default or any engine, rung or fleet change (D10); the margin-opening fee and the rollover in the cost model; a per-leg or per-size cost in the builder; re-reading the spent holdout window or any bar after 2026-03-31; any read of `data/ohlc-holdout-2026-07-10`; the incumbent comparison against record 43; re-running reading 9 or the tracking report beyond D3's one read; the paired live-minus-simulation harness (T0122).
