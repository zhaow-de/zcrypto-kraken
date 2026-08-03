# Cross-frequency combination (P1 trial 3) — design

**Iteration:** iter-076 (design only — the run is the next loop's first package). **Goal:** fold the A-family's survivors into the combined system as one registered P1 trial: the three adopted A2 native-4h arms (registry trials 37–39) and the admitted A1-lf weekly sleeve (trial 34) beside the deployed benchmark sleeve — under the `[iter-073]` pre-registered DD-aware adopt criterion. Design decisions logged `[iter-076]`.

## Why a design spec first

The fold-in mixes bar frequencies (a 4h sleeve beside two daily sleeves), which the trial-35 construction never had to handle. The semantics below are fixed *before* any number exists, so the run is mechanical.

## Construction

1. **Calendar**: the combination runs on the **4h union calendar** (~27.3k bars). Each **daily** sleeve's per-asset positions are held constant across that day's six 4h bars — a daily book *is* a position held all day; no resampling artifacts, and the 4h sleeve keeps the intraday responsiveness it was adopted for. *\[Precision added during execution (iter-080 pre-run review): "that day" = the real calendar day the daily book earns, i.e. close\[k\]→close\[k+1\]. Both parquet grids stamp bar STARTS (daily close stamped D == 4h close stamped D 20:00), so daily position k is tradable only from d_ts\[k\]+24h and maps to the six 4h return bars with end-stamps in (d_ts\[k\]+24h−4h·…\] — implemented by passing CLOSE-TIME-shifted boundaries (daily_ts+1d, intraday_ts+4h) to `expand_daily_positions`; feeding raw stamps applies position k one day early (look-ahead — inflates the B sleeve's 4h Sharpe ~1.27→~1.76). Guarded by a pre-registered expansion QA: each expanded sleeve's 4h noc Sharpe within \[daily anchor −0.15, +0.10\].\]*
2. **Sleeves (three)**:
   - **B** — the frozen-benchmark sleeve: the daily `w·l3` per-asset positions (record 33's sleeve), intraday-held.
   - **A1** — A1-lf weekly v0.12 (trial 34): the daily 7-offset-mean held positions, intraday-held.
   - **A2** — the **equal-weight ensemble of the three adopted 4h arms** (trials 37–39: (20,50,100)v0.12, (60,120,240)v0.10, (60,120,240)v0.12) — the selection-free default; best-of-3 after seeing results would be post-selection.
3. **Sleeve weights**: rolling **30-day (180-bar)** inverse-vol on each sleeve's own net-of-cost returns through k−1, normalized; **any degenerate window → equal weight** (the `[iter-072]`-amended convention, three-way form: if ANY sleeve's window has zero vol, all three weights fall back to 1/3).
4. **Cap → costing → governor**: combined per-asset positions `c_a = Σ w_s·pos_s_a` → `apply_position_caps` (20 %/10 %) → **full per-asset net-of-cost on the final book** (turnover × 0.006/side at 4h; no shorts → no carry) → the §10 governor evaluated on the combined book's **daily-aggregated** returns — compounded within the day, `∏(1+r_4h)−1` — (§10's constants are day-defined: −3 % *day*, 5-*day* cooldown, 30-*day* re-arm), with day *t*'s multiplier fixed from governed state through day *t−1* only (the governor's own no-look-ahead contract, unchanged) and applied to all six of day *t*'s 4h bars. *\[Precision added during execution (iter-080): a bar's day = date(h_ts\[k+1\]) (true midnight day under bar-start stamps); day_index = DENSE RANKS of present days — the 4h union lacks 3 calendar days in the 2013 stub, and record 33's ratified daily governor counted present bars, so compression is the semantics-consistent choice.\]*

## Verdict protocol (pre-registered; the `[iter-073]` DD-aware criterion binds this trial)

- **QA gates first**: each sleeve reproduces its recorded figures through this driver (bench-4h 1.2128/1.2447; A1-lf 1.3798 on its daily grid before intraday holding; the three 4h arms' 1.3274/1.3017/1.3585); cap + governor + weights engagement evidenced (all three sleeve weights vary; none pinned at 0/1).
- **Adopt iff** — the DD-aware branch: annualized net-of-cost Sharpe within **0.02** of the incumbent record 33's **1.3263** AND maxDD ≥ **1.5 pp lower** than **14.49 %**; — or the Sharpe-primary branch: Sharpe **≥ 1.3263** (inclusive — "as before" per the §9/`[iter-059]` convention) with every ratified-bar leg passing vs the 4h-rebuilt frozen benchmark (decisive k ≥ 1380; SPA at blocks 30 **and** 102; seeds 42/7/1234; benchmark-relative worst-slice, stubs excluded; DSR at the P1 family count with `var_trials` in **4h per-period units**).
- Registry: `family="P1"`, `n_trials_in_family=3`, variant naming the sleeve set; failing both branches → `reject`, record 33 stays the deployable system.

## Out of scope

Running the trial (next loop's first package — compute ≈ 2 h); any governor-constant rescaling to 4h (would re-derive unratified constants); touching record 33 or the deployed system before the trial verdicts.

______________________________________________________________________

## Two ratified-bar details this spec left unpinned — recovered and written down 2026-08-03

Both were recovered by re-derivation, not chosen: each was fixed by requiring it to reproduce record 44's *registered* figures, and each was shown to be discriminating rather than a fit (mutating it breaks the reproduction). They are recorded here because the spec named the legs without specifying these details, and a detail that lives only in a vanished runner is exactly the failure [[T0125]] exists to prevent.

**The SPA grid's headline cell is `(mean_block 30, seed 42)`.** That pair's *full-window* reading is stored as `spa_p_full` and its *decisive-window* reading as `spa_p_decisive` — which is why the registry carries no `spa_grid_b30_s42` key, a gap that otherwise reads as a missing cell. The five `spa_grid_*` keys are the **decisive**-window readings of the remaining cells: (30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234). Four of the five match the decisive reading and **not** the full one, which is what identifies the window; (102, 42) reads identically on both at 1/2001 granularity and so does not discriminate.

**The benchmark-relative worst-slice test** is `benchmark_relative_worst_slice(...)["beats_benchmark_worst"]` in `cli/alpha/killbar.py` — calendar-year slices, 2013 and 2026 stubs excluded, per-period Sharpe fixed by the kill-bar ratification. What the spec left open is **which series and which window**: it is the **governed net over full history**, with each bar's year taken from its **close** stamp. That reproduces record 44's registered notes exactly — book worst slice 2022 at −0.02898802673890783, benchmark worst 2014 at −0.0797494372250268, book smaller drawdown in 6 of 12 slices, none skipped. It is discriminating: on the decisive window the book's worst slice moves to 2014, contradicting the registered note.

The re-derivation itself is committed at `cli/portfolio/record44_legs.py` with tests, so these are re-runnable rather than described.
