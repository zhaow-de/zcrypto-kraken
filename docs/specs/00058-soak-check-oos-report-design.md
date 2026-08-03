# Spec 00058 — `zcrypto engine soak-check`: realized-OOS-vs-backtest consistency report (T0064 / WP7)

## Goal

A read-only decision-support command that places the deployed strategy's **realized forward (shadow-soak) behaviour** against its **backtest expectation**, as the stand-in for the never-run out-of-time holdout ([[T0064]]). It is **not validation** and **not the concordance gate** (specs `00039`/`00040` already prove the node reproduces the builder to `|Δweight| ≤ 1e-6`; this asks whether the strategy *generalizes*). Design produced by a 3-lens judge panel (return-distribution / behavioural-fingerprint / adversarial-falsification) → synthesis, 2026-07-19.

**The bare fact this exists to surface** (printed verbatim every run): *trial 44 has ZERO out-of-time holdout evidence — the one budgeted holdout look (budget now 0) tested the SUPERSEDED record 33 in a degenerate `[0,0]` window and discriminated nothing; paper trading is its only genuine OOS test.*

## Why the behavioural-fingerprint lens leads

At `L ≈ 84` 4h cycles (14 days × 6/day) a Sharpe/return statistic has near-zero discriminating power. But **position-derived structural metrics** — exposure, turnover, engagement, concentration — are estimable at that L, and decisively they are computed from **positions, not P&L**, so the spec-`00040`-D4 governor-cost bias (below) cannot touch them. The headline is therefore a table of structural metrics; a P&L line is kept but **non-gating** and honestly caveated.

## Decisions

- **D1 — command.** New `zcrypto engine soak-check`, read-only, core in **`cli/engine/soak.py`**, registered in `cli/engine/command.py`. Reuses `_journal_artifacts`/`_snapshot_reader` (command.py), `journal.from_json`, `store.read_store_series`, `concordance.replay_cycle`, `portfolio.build_crossfreq_system_fast`, `risk.limits.apply_position_caps`. NEVER calls `evaluate_gate` — it points the reader at `zcrypto engine report` for the concordance gate. Distinct name (`soak-check`, not `report`) because "soak" names the evidence source.

- **D2 — realized series (the observation; kept pure).** From the journal's `final_targets` (= `mult × capped` per asset per 4h cycle, the quantity actually traded) × the forward 4h return from the store:
  - Take the **longest contiguous clean 4h run** of success `cycle-*.json` records (boundaries 00/04/08/12/16/20 UTC, no missing boundary, no `failed-cycle-*` sidecar) — the turnover chain and compounded path require gap-freeness.
  - `r_fwd_a(T) = C_a(T)/C_a(T−4h) − 1`, **timestamp-keyed** on `read_store_series(store_dir, a, 240)`, NEVER list-index. Start price `C_a(T−4h)` = this cycle's 240-snapshot last close; end price `C_a(T)` = the **next** cycle's 240-snapshot last close — both hash-verified immutable journal evidence. (This is the off-by-one keystone: D6 test 1.)
  - `gross(T) = Σ_a q_a(T)·r_fwd_a(T)`; `turnover(T) = Σ_a |q_a(T) − q_a(T_prev)|`; `net(T) = gross(T) − fee·turnover(T)`, `fee = 0.006`/side.
  - **First journaled cycle included**, charged from `prev = 0` (the shadow book demonstrably starts flat each cycle per `cycle.py`'s `orders.jsonl`, so its full-entry cost is real). Null windows are **flat-start-normalized** to match.
  - Score only boundaries whose forward bar has a completed store close AND `T+4h ≤ now` (drop the in-progress candle, mirroring `store._drop_in_progress`) — drops the newest 1–2 cycles. `L` = scored count. Realized stats: compounded cumulative net `Π(1+net)−1`, mean net/cycle, per-cycle vol.

- **D3 — the null (adjust the instrument, not the observation).** Rebuild via `build_crossfreq_system_fast` over the frozen canonical `data/ohlc-full` (2013-09-10 → 2026-03-31) — the same code path that produced the journal, so identity holds by construction. Recompute a per-bar **`net_live[k]`** matching the realized accounting exactly: `net_live[k] = mult[k]·gross[k] − fee·Σ_a |mult[k]·capped_a[k] − mult[k−1]·capped_a[k−1]|` (turnover on `|Δ(mult×capped)|`). Reconstruct `capped` from `sleeve_positions` via `apply_position_caps(⅓(B+A1+A2))` — **NOT** by dividing `final_targets` by `multipliers` (guards the `mult==0` division trap).
  - **Primary null:** all contiguous overlapping `L`-bar windows of the metric series (flat-start-normalized); the empirical percentile band is the reference. Effective independent windows ≈ `N_bars/L` (~320 at L≈84) — **disclosed**, so the band is never mistaken for high precision.
  - **Secondary null (robustness):** stationary (Politis–Romano) block bootstrap, mean block = 6 bars (1 governor-day, so intraday compounding + transition clustering survive), B ≈ 10000. Reject an iid Normal/t parametric null. Report both; on disagreement prefer the **more conservative** (less likely to call "inconsistent") and flag it.

- **D4 — the governor P&L bias cancels by construction.** Spec `00040` line 35: `governed_net` under-prices multiplier-transition turnover (`mult·fee·|Δcapped|`), while a live engine trading `final_targets` pays `fee·|Δ(mult×capped)|`. Because the null P&L base is `net_live` (live convention, D3), **both sides use identical accounting and the D4 gap cannot manufacture a spurious "inconsistent."** Separately **quantify + report** the gap: `mean(governed_net − net_live)` bps/cycle over frozen history, and the forward window's multiplier-transition count → print **"bias ACTIVE/INACTIVE this window"** (a 14-day soak may contain 0 transitions → the recosting is a no-op, stated explicitly so a reader never over-attributes).

- **D5 — metrics + verdict.** **Seven structural (D4-immune) metrics**, each judged against its own flat-start windowed null; **plus one NON-gating P&L line**. No single aggregate verdict.
  1. gross exposure `Σ|w|` · 2. net exposure `Σw` · 3. active fraction `#(|w|>1e-9)/10` · 4. per-cycle turnover `Σ|w−w_prev|` · 5. concentration `HHI(|w|/gross)` · 6. **governor-engagement rate at DAY granularity** (effective-n ≈ days ≈ 14, not L) · 7. cap-breach rate. · 8 (non-gating) realized cumulative net + mean net/cycle vs the `net_live` null.
  - **Per-metric two-sided rule** (`--band` default 0.90 → central `[p5,p95]`): live ∈ `[p10,p90]` → **consistent**; ∈ `[p5,p10)∪(p90,p95]` → **weakly consistent (edge)**; outside `[p5,p95]` → **INCONSISTENT — investigate** (two-sided: too-good is also a bug tell, NOT a reject); zero-width band / tiny effective-n → **n/a (undiscriminating)**.
  - Print each row `live | median | band | percentile | effective-n | width | verdict`, then a **multiplicity summary**: "X of 7 outside band (≈0.7 expected by chance at 90%)" — alarm only on corroboration across correlated metrics, never worst-of-N.

- **D6 — falsification guards (VOID/refuse, never a plausible-but-wrong verdict).** Pre-gates that refuse a verdict entirely:
  - **Instrument self-check** — a frozen build reproduces registry **record 44** (figures + tolerances read from `trial-registry.jsonl`, not hardcoded) + the canonical extent.
  - **Identity** — journaled `final_targets == replay_cycle(fast)` to `1e-6` (the concordance invariant, re-asserted).
  - **Reconciliation** — the overlay-repriced null reproduces the builder's returned `governed_net` to `1e-9`.
  - **Degeneracy override** — near-zero exposure window (echoing the record-33 `[0,0]` holdout) → **INDETERMINATE — DEGENERATE WINDOW**, no "consistent" emitted.
  - **Plausibility bounds** — `|r_fwd| ≤ 0.5`/4h; gross ∈ `[0,2]`; rates ∈ `[0,1]`; realizable count == success − unrealized tail. `L < --floor` (30) / non-contiguous run / implausible bar → **"no verdict."**
  - **Vocabulary lock** — never "validated/passed/confirmed/proven"; the banner is always present.

## Report shape (D5/D6 rendered)

Text block (echoed like `report`), lines in order: (1) honesty **banner** (bare fact verbatim); (2) window provenance (first/last `cycle_ts`, `L`, days, gaps/sidecars, dropped tail); (3) self-tests (instrument/identity/reconciliation → VOID on fail); (4) degeneracy gate; (5) structural fingerprint table + multiplicity line; (6) governor/cap block with n≈14 caveat + transition count; (7) D4 gap + ACTIVE/INACTIVE; (8) non-gating P&L block (both nulls, near-vacuous label, caveated Sharpe; "indeterminate (instrument-fragile)" if the two nulls disagree); (9) ~~regime context~~ **— DROPPED 2026-08-03, measured rather than judged (see below)**; (10) honesty footer ("consistent ≠ validated; overfit strategies land in-band most of the time at L≈84").

CLI options: `--journal-dir` (default `config.journal_dir`, accepts a pulled VPS journal), `--store-dir` (default `config.store_dir`), `--canonical-dir` (default `data/ohlc-full`), `--fee-per-side` (0.006), `--band` (0.90), `--floor` (30), `--null [windows|block-bootstrap|both]` (both), `--path [fast|verified]` (fast), `--json PATH` (atomic `.tmp`+`os.replace`, dumps every number). Exit 0 on emit; non-zero only on operational failure or a VOID self-test.

## Non-goals

- Not the concordance/execution-fidelity gate (that is `zcrypto engine report`, specs `00039`/`00040`) — this checks generalization, not reproduction.
- Not a holdout look: it consumes **no** holdout budget, never touches/re-derives `data/ohlc-holdout-*`, and makes no go/no-go call. The T0064 go-live judgment (is trial 44's lack of OOS evidence acceptable on paper / at live capital?) stays human-gated — this tool *informs* it.
- Not "validation." The vocabulary lock + the every-run banner enforce this.

## Test list (TDD — the plan expands each)

1. **off-by-one forward-return-join guard** — synthetic store+journal with hand-computed net; correct join matches, an injected off-by-one makes the snapshot-close cross-check FAIL (guard bites). 2. planted-consistent (a real interior backtest slice replayed as a fake journal → in-band → "consistent"). 3. planted-inconsistent (a metric 3× the band → outside `[p5,p95]` → "INCONSISTENT"). 4. zero-exposure degeneracy → "INDETERMINATE — DEGENERATE WINDOW", no "consistent". 5. flat/zero cycle → exactly zero net. 6. reconciliation VOID on perturbed `capped`. 7. identity VOID on tampered targets. 8. gap segmentation (longest clean segment, no stale-prev span). 9. forward-realizability drops the newest cycle. 10. asset-set drift aborts. 11. flat-start null normalization (first-bar prev=0). 12. vocabulary lock (no "validated/…", banner always present). 13. band-width + effective-n disclosure (incl. governor n≈days). 14. multiplicity summary line present.

______________________________________________________________________

## Report-shape item 9 ("regime context") — DROPPED 2026-08-03

This spec **named** the section without specifying its content, which is why it was deferred rather than built: inventing a definition inside an implementation iteration would have baked an arbitrary choice into a go/no-go instrument. The question it left open was *which regime variable is worth conditioning a soak verdict on*, and the test it had to pass was *what would a reader do differently on seeing it* — because on this instrument, unactionable context reads as evidence.

**It is dropped on a measurement, not a preference.** A two-cell regime split's *smaller* cell holds at most half the bars, and the balanced split is precisely the one that **maximizes that minimum** — so halving the window measures the **best case** available to any split. An unbalanced split is no escape: its majority cell merely reproduces the full-window verdict while its minority cell has even less power, which is not a comparison. On the 23.17-day realized window (L = 140 scored bars), split into two contiguous halves of L = 71 and L = 68 — both of which are the **same regime** by every system-internal measure (governor multiplier 0.5 with zero variance, cap-breach 0, one active sleeve throughout):

| metric | full (L=140) | first half (L=71) | second half (L=68) |
| --- | --- | --- | --- |
| `governor_engagement` | **inconsistent** | **n/a — no discriminating power** | **n/a — no discriminating power** |
| `gross` / `net` | indeterminate | **consistent** | **indeterminate** |
| realized cumulative net | −0.4559 % | **+0.0302 %** | **−0.5514 %** |

*(71 + 68 = 139, not 140: each run independently drops its own newest cycle, which can never score for want of a successor, so the boundary cycle scores only in the full run. For the same reason the halves' P&L does not compose to the full window's — these are three separate runs, not a partition of one.)*

Two conclusions, and the second is the decisive one:

- **Conditioning destroys the only discrimination the instrument makes.** `governor_engagement` is the single metric that reads outside its band at full window; at half window its null band spans the full [0, 1] on *both* halves, so the test has no power at all. Every regime split does this, whichever variable is chosen.
- **Two windows in the same regime already disagree.** `gross`/`net` land on different verdicts and the P&L on opposite signs, with no regime difference between them. So a regime-conditioned section cannot separate a regime effect from sampling variation at any window length this instrument will plausibly read — it would present a split like the one above and invite a reader to see structure in noise.

**The honest residue already ships**, which is why nothing is lost. `soak-check` already states regime state without conditioning any verdict on it: *"realized multiplier was 0.5 on all 140 scored cycles (no variance)"*, *"realized cap-breach was 0 on all 140 scored cycles (no variance)"*, and the sleeve-occupancy count now has its own gauge and alert. That is regime context in the only form that adds information rather than width.

Deferring again was rejected — but on the right leg, and the distinction matters. The measurement only **brackets** the power threshold in (≈70, 140]: it shows cells of ~70 are powerless and does *not* show that the ~90-bar cells a ≥30-day window would give are. The rejection therefore rests on the regimes **not alternating**, which no amount of window length fixes: the governor has been at ×0.5 for the entire soak, carried from the 2025 drawdown, and both dormant sleeves have been flat ~9 months — so a split on either variable leaves **one cell empty at any horizon**, and an empty cell is not a comparison at any L.
