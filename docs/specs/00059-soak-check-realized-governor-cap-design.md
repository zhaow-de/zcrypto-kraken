# Spec 00059 — soak-check: realized governor-engagement + cap-breach as gating metrics (T0072)

## Goal

Promote the soak-check's two remaining structural metrics — **governor-engagement** and **cap-breach** — from null-side *backtest context* to real **realized-vs-backtest gating comparisons**, taking the structural fingerprint from 5 gating metrics to the spec-`00058`-intended **7**.

## Why they were context-only in v1

`00058` gates on metrics computable from the journaled `final_targets` (= `mult × capped`, the weights actually traded). The other two need strategy **internals** the journal doesn't store:

- **cap-breach** is undetectable from `final_targets`: `mult ≤ 1` and `capped ≤ cap`, so `final_targets ≤ cap` on every bar — a breach metric read off the traded weights is trivially always 0. The meaningful signal is `combined` (pre-cap) vs `capped`.
- **governor-engagement** needs the per-bar multiplier `mult[k]`, which the journal does not record separately from the product.

## The unlock — the journal's own snapshots are a complete rebuild input

Each cycle record's 240 `SnapshotEntry` carries the **full price history** through `cycle_ts − 4h` (hash-verified, and `replay_cycle` already rebuilds from it). So one build of `build_crossfreq_system_fast` on the **latest** record's snapshots yields `multipliers`, `day_index`, and `sleeve_positions` for **every** bar in the journal's span — including every scored cycle in the realized window. No live-store dependency, no second data source: the authoritative evidence is the journal itself.

## Decisions

- **D1 — one rebuild, timestamp-keyed.** `realized_internals(latest_record, snapshot_reader)` builds once via `build_crossfreq_system_fast` on the latest record's assembled grids, then maps `h4_ts → index`. **The row for the decision made at cycle `T` is the index `k` where `h4_ts[k] == T − 4h`.** (Verified against the builder: `n_periods = len(h4_ts) − 1`; `final_targets`/`multipliers` carry `n_rows_h = len(h4_ts)` rows; `replay_cycle` reads the forming row `n_periods`, whose stamp is `h4_ts[-1] == cycle_ts − 4h`.) Look the index up **by timestamp**, never positionally. A scored cycle whose `T − 4h` is absent from the grid raises `SoakError` — never a silent skip.

- **D2 — THE KEYSTONE: a window-wide identity proof.** At the resolved index `k` for cycle `T`, the rebuild's `final_targets[a][k]` **must equal the journaled `final_targets[a]` of that same cycle** to `1e-6`, for **every** scored cycle and asset. This is the T0072 analogue of `00058`'s forward-return keystone: any ±1 index shift, grid misalignment, or wrong-record rebuild breaks it loudly across the whole window. Failure ⇒ **VOID** (no verdict), never a degraded result. The test suite must contain a case where an **injected index shift makes this identity FAIL** — a guard that cannot bite is not a guard.

- **D3 — per-bar cap-breach, mirroring the builder.** `combined[a][k] = ⅓(B+A1+A2)` from `sleeve_positions`; `capped = apply_position_caps(combined)`; `breach[k] = any(|capped[a][k] − combined[a][k]| > 1e-15)` — the same predicate the builder uses for its own `cap_breach_bars` (`crossfreq_system.py:636`). **Self-consistency check:** summing `breach` over the completed bars must equal the builder's returned `cap_breach_bars`; a mismatch is an instrument fault ⇒ VOID.

- **D4 — governor-engagement at DAY granularity.** A realized **day** is engaged iff **any** of its scored bars has `mult < 1.0`; realized rate = engaged days / scored days. This matches the governor's daily cadence (it re-decides per day, so bar-granularity would overstate resolution). The report discloses the day-granularity caveat and the realized day count alongside the metric.

- **D5 — the null side.** Governor: `governor_engaged_daily(null.multipliers, null.day_index)` → per-day 0/1 over frozen history. Cap-breach: extend `NullSystem` with a **per-bar `cap_breach` series** (derivable in `build_null`, which already reconstructs `combined`/`capped` in `_net_live_from_result`) — the existing scalar `cap_breach_bars` is retained and used as the D3 cross-check. Null reference = `windowed_null(series, window)` with **window in the metric's own unit**: `L` bars for cap-breach, the realized **day count** for governor. `effective_n = len(null_series)/window`, disclosed as for every other metric.

- **D6 — promote to gating.** `gating_verdicts` becomes 7 keys (`gross`, `net`, `active_frac`, `turnover`, `hhi`, `governor_engagement`, `cap_breach`). The report's "GOVERNOR / CAP CONTEXT — backtest context (not a realized comparison)" block is **removed** and its two rows join the fingerprint table; the null-side rates remain visible as the `median` column. `SoakAnalysis` keeps `null_gov_rate`/`null_cap_rate` for the JSON's continuity.
  **Multiplicity counts only discriminating metrics:** `summarize_panel`'s `n_metrics` (and hence `expected_by_chance = n_metrics × (1 − band)`) counts the metrics that actually produced a verdict, **excluding `"n/a"`** ones. A metric whose band is degenerate or whose rebuild was unavailable cannot contribute a false positive, so counting it would overstate the expected-by-chance baseline. This also makes D7's degraded mode self-consistent: with the rebuild unavailable the line reads `… of 5` automatically, with no special-casing.

- **D6a — near-redundant metrics are disclosed, not silently counted.** On a long-only book `gross ≡ net` (observed live 2026-07-20: both 0.0449), so the two carry almost no independent information, yet the multiplicity line treats every metric as one independent trial. The report therefore prints a one-line note when `|corr|` between the realized `gross` and `net` series is ≥ 0.99 (or trivially when the book has no short exposure), stating that the effective number of independent metrics is lower than the count. No verdict changes — this is disclosure, matching the spec-`00058` discipline of never alarming on worst-of-N.

- **D7 — refusal discipline unchanged.** All of `00058`'s VOID gates still apply and now also cover D2/D3. If the rebuild cannot be performed at all (snapshots absent/corrupt — `EngineError` from the reader), the two new metrics are reported **`n/a` with a stated reason** and the panel counts 5, rather than voiding the whole run: a missing rebuild degrades the fingerprint, it does not invalidate the 5 weight metrics. A rebuild that *runs but disagrees* (D2/D3) is the opposite — that VOIDs, because it means the instrument is lying.

- **D8 — a band that spans the metric's whole attainable domain is `n/a`, not "consistent".** *(Discovered from
  the live run, not designed up front — recorded here so it is a rule, not a code comment.)* The first real
  7-metric run returned `governor_engagement: live=1.0, band=[0.0, 1.0], width=1.0000 → "consistent"`. That band
  covers the entire attainable range of a rate, so **no possible value could ever fall outside it**: the test
  has zero discriminating power and "consistent" is vacuous — yet it was still counted in the multiplicity
  denominator, inflating the reassurance.
  `metric_verdict` already escapes a **zero**-width band ("degenerate discriminator" → `n/a`). A **full**-width
  band is the same failure of discrimination in the opposite direction (over-sensitive vs under-sensitive), and
  gets the same treatment. Implemented as an optional `domain: tuple[float, float]` on `metric_verdict`:
  `n/a` iff the band covers **both** ends (`lo <= min+eps` **and** `hi >= max-eps`) — a one-sided touch keeps
  its power, so `active_frac`'s live band `[0.0074, 1.0]` correctly stays discriminating. `domain=(0,1)` is
  passed for the three **rate** metrics (`active_frac`, `governor_engagement`, `cap_breach`); `gross`/`net`/
  `turnover` are unbounded above and `hhi`'s lower bound is `1/n > 0`, so none of them can reach a full-`[0,1]`
  band and none takes a domain. The computed stats are **retained** on an `n/a` row so its numbers still render,
  and because D6 already excludes `n/a` from the multiplicity denominator, the panel self-corrects (live: "0 of
  6 (~0.6)"). A disclosure states why the metric could not discriminate.

- **D9 — the window statistic is the reference, never the null's global mean.** *(Recorded because the loop got
  this wrong once, mid-iteration.)* Reading the realized governor rate (1.0) against the null's **global**
  engagement rate (0.266) suggested a large divergence and a likely "inconsistent". Judged correctly — against
  the distribution of **same-length window** rates — short windows in the backtest reach 100% engagement often
  enough that `p95 = 1.0`, so 9-of-9 engaged days is unremarkable and the honest verdict is *not* a divergence.
  Comparing a window statistic to a global mean is exactly the error the windowed null exists to prevent; any
  future metric added here is judged against a same-unit, same-window null distribution, never a scalar summary.

## Non-goals

- No change to the forward-return join, the null P&L (`net_live`) derivation, the D4 governor-bias cancellation, the honesty banner, or the vocabulary lock.
- Not the secondary block-bootstrap null ([[T0073]] — still unwired).
- Does not consume holdout budget; reads only the journal, the live store, and the frozen canonical.

## Test list (TDD)

1. **Keystone must-fail** — synthetic journal + snapshots; the window-wide identity holds on correct alignment, and an **injected ±1 index shift makes it FAIL**.
2. **Timestamp-keyed lookup** — a scored cycle whose `T−4h` is missing from the rebuild grid raises `SoakError` (no silent skip).
3. **Cap-breach self-consistency** — per-bar `breach` sums to the builder's `cap_breach_bars`.
4. **Cap-breach is non-degenerate** — a book that breaches the cap pre-capping flags 1 where the traded weights alone would show 0 (proves the metric measures what `final_targets` cannot).
5. **Governor day aggregation** — a day with one sub-1.0 bar is engaged; an all-1.0 day is not; rate = engaged/total days.
6. **Planted-consistent / planted-inconsistent** for both new metrics against a jittered non-degenerate null.
7. **Panel counts only discriminating metrics** — `summarize_panel` over 7 verdicts where all 7 discriminate gives `n_metrics == 7` and `expected_by_chance == 7×(1−band)`; with 2 of them `"n/a"` it gives `n_metrics == 5` and `5×(1−band)` (so D7's degraded mode needs no special-casing).
7a. **Redundancy disclosure** — a realized series whose `gross` and `net` are identical (long-only) triggers the effective-independence note; a book with genuine short exposure (uncorrelated gross/net) does not.
8. **Graceful n/a** — an unreadable-snapshot rebuild yields `n/a` for the two metrics + a reason, does **not** void, and the 5 weight metrics still gate (D7).
9. **Real-data verification** (data-gated) — on the ops journal: all 7 metrics populate, the D2 identity holds across every scored cycle, and D3 self-consistency holds.
10. Vocabulary lock + banner still hold over the new report text — **structurally**, not by convention: any
    free-form string interpolated into the rendered report (currently the internals reason, which carries
    `str(exc)` from an arbitrary `EngineError`/`PortfolioError`) is scrubbed at the render boundary, while the
    JSON keeps the raw text. A planted "passed"/"PROVEN" reason must render scrubbed and survive raw in JSON.
11. **D8 vacuous band** — a `[0,1]`-spanning band on a rate metric yields `n/a` with its computed stats
    retained; a one-sided touch (`lo > 0, hi == 1`, i.e. `active_frac`'s real shape) stays discriminating; no
    `domain` is passed for gross/net/turnover/hhi; the multiplicity denominator drops the `n/a` metric with no
    special-casing.
12. `SoakError` from `realized_internals` **propagates** out of `soak_report` (a genuine inconsistency must not
    be caught into the degrade path) — pinned by a test so a future broad `except` is caught.
