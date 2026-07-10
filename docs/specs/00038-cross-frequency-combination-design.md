# Cross-frequency combination (P1 trial 3) — design

**Iteration:** iter-076 (design only — the run is the next loop's first package). **Goal:** fold the A-family's survivors into the combined system as one registered P1 trial: the three adopted A2 native-4h arms (registry trials 37–39) and the admitted A1-lf weekly sleeve (trial 34) beside the deployed benchmark sleeve — under the `[iter-073]` pre-registered DD-aware adopt criterion. Design decisions logged `[iter-076]`.

## Why a design spec first

The fold-in mixes bar frequencies (a 4h sleeve beside two daily sleeves), which the trial-35 construction never had to handle. The semantics below are fixed *before* any number exists, so the run is mechanical.

## Construction

1. **Calendar**: the combination runs on the **4h union calendar** (~27.3k bars). Each **daily** sleeve's per-asset positions are held constant across that day's six 4h bars — a daily book *is* a position held all day; no resampling artifacts, and the 4h sleeve keeps the intraday responsiveness it was adopted for.
2. **Sleeves (three)**:
   - **B** — the frozen-benchmark sleeve: the daily `w·l3` per-asset positions (record 33's sleeve), intraday-held.
   - **A1** — A1-lf weekly v0.12 (trial 34): the daily 7-offset-mean held positions, intraday-held.
   - **A2** — the **equal-weight ensemble of the three adopted 4h arms** (trials 37–39: (20,50,100)v0.12, (60,120,240)v0.10, (60,120,240)v0.12) — the selection-free default; best-of-3 after seeing results would be post-selection.
3. **Sleeve weights**: rolling **30-day (180-bar)** inverse-vol on each sleeve's own net-of-cost returns through k−1, normalized; **any degenerate window → equal weight** (the `[iter-072]`-amended convention, three-way form: if ANY sleeve's window has zero vol, all three weights fall back to 1/3).
4. **Cap → costing → governor**: combined per-asset positions `c_a = Σ w_s·pos_s_a` → `apply_position_caps` (20 %/10 %) → **full per-asset net-of-cost on the final book** (turnover × 0.006/side at 4h; no shorts → no carry) → the §10 governor evaluated on the combined book's **daily-aggregated** returns — compounded within the day, `∏(1+r_4h)−1` — (§10's constants are day-defined: −3 % *day*, 5-*day* cooldown, 30-*day* re-arm), with day *t*'s multiplier fixed from governed state through day *t−1* only (the governor's own no-look-ahead contract, unchanged) and applied to all six of day *t*'s 4h bars.

## Verdict protocol (pre-registered; the `[iter-073]` DD-aware criterion binds this trial)

- **QA gates first**: each sleeve reproduces its recorded figures through this driver (bench-4h 1.2128/1.2447; A1-lf 1.3798 on its daily grid before intraday holding; the three 4h arms' 1.3274/1.3017/1.3585); cap + governor + weights engagement evidenced (all three sleeve weights vary; none pinned at 0/1).
- **Adopt iff** — the DD-aware branch: annualized net-of-cost Sharpe within **0.02** of the incumbent record 33's **1.3263** AND maxDD ≥ **1.5 pp lower** than **14.49 %**; — or the Sharpe-primary branch: Sharpe **≥ 1.3263** (inclusive — "as before" per the §9/`[iter-059]` convention) with every ratified-bar leg passing vs the 4h-rebuilt frozen benchmark (decisive k ≥ 1380; SPA at blocks 30 **and** 102; seeds 42/7/1234; benchmark-relative worst-slice, stubs excluded; DSR at the P1 family count with `var_trials` in **4h per-period units**).
- Registry: `family="P1"`, `n_trials_in_family=3`, variant naming the sleeve set; failing both branches → `reject`, record 33 stays the deployable system.

## Out of scope

Running the trial (next loop's first package — compute ≈ 2 h); any governor-constant rescaling to 4h (would re-derive unratified constants); touching record 33 or the deployed system before the trial verdicts.
