---
status: resolved
---

# The spread calibration is 13.1 days; Phase 2's exit bar says ≥2 weeks

## Context — what

Phase 2 ("Validation Harness & **Cost Model** First") closed on 2026-07-08 with one exit-bar row carried forward, T0003-gated:

> | Cost model validated against ≥2 weeks of captured spreads | **Carried forward — T0003-gated** |

[[T0014]] (iter-114, spec `00066`) delivered that work — the per-pair table, `effective_spread_bps()`, and the combined `round_trip_cost()` helper the same closeout deferred alongside it. But the window it calibrated on is **13.1 days**, not ≥2 weeks: 315 hourly files per pair, `2026-07-08T13:47:33Z … 2026-07-21T15:59:59Z`. The panel trails live capture by the ~7 h settle watermark ([[T0066]]), so the 336th hour lands about a day after the calibration ran.

Everything the bar asks for exists except the literal span.

## Why this matters

Small, but it is the difference between a phase exit bar being **met** and being **nearly met**, and that distinction is exactly the kind that quietly becomes "met" once nobody remembers the shortfall. The Phase-2 closeout table is a permanent artifact; leaving its last carried-forward row ambiguous is how a gate gets inherited as passed.

It is also cheap insurance on the numbers themselves. The day-level standard error of each constant is **1–6 %** (BTC 5.7 %), and BTC/ETH trend downward across the window — so an extra day is not merely bureaucratic, it measurably moves the estimate. The current table is a 13.1-day **benign-regime** estimate: the window sits at the 0th–9.7th percentile of each pair's historical volatility.

## Findings so far

- The exact deficit is **21 hourly files per pair** (315 → 336).
- The recalibration is a single `pl.scan_parquet` over `l2-panel/<BASE>/EUR/panel-1s/**/*.parquet` taking the mean of `(fill_bps_bid_<size> + fill_bps_ask_<size>) / 2` per pair — the procedure is written down in `docs/reference/captured-spread-calibration.md` § *Recalibrating*.
- `tests/test_costs_spread.py` pins the table **and** `CALIBRATION_WINDOW` / `CALIBRATION_HOURS` / `CALIBRATION_MIN_ROWS` together, so the restamp cannot be done silently — the tests fail until the provenance is updated with the values.
- Two instrument checks belong with the re-run (both already scripted in the reference doc): the mean ÷ median ratio per pair, to catch a new pair sitting on a tick-quantisation crossing the way BTC does; and the session band, to confirm a session term is still unwarranted.

## Resolution (2026-07-23)

**Discharged.** The panel reached **353 hourly files per pair** (trigger was 336), so the committed query was re-run over `l2-panel/<BASE>/EUR/panel-1s/**` and the table, the three provenance constants, the reference doc and the Phase-2 closeout were updated together.

- **Window:** `2026-07-08T13:47:33Z … 2026-07-23T05:59:59Z` — **14.68 days**, 353 h/pair, ≥1,260,309 rows/pair (~12.6 M total). Phase 2's last carried-forward exit-bar row now reads **DISCHARGED** in `docs/research/03.phase2-validation-harness-closeout.md`, with the window that discharged it.
- **The constants moved within the stated uncertainty**, so this is arithmetic, not regime. Largest moves: LINK @€100 +5.0 % (2.102 → 2.207), DOT @€100 −2.9 % (3.684 → 3.579), DOT @€10k −1.5 % (12.412 → 12.223); most pairs moved under 2 %. Every move sits inside the day-level standard error the reference doc already records (1–6 %, BTC 5.7 %), so no range replaces the point estimates. The direction is consistent with the earlier finding that BTC/ETH trend downward through the window — both fell again (BTC @€100 0.266 → 0.260, ETH 0.425 → 0.420).
- **Instrument check 1 — mean ÷ median @€100**, to catch a new pair on a tick-quantisation crossing: BTC **1.63×**, SOL 1.23×, ADA 1.08×, everything else 0.97–1.06×. BTC remains the only elevated pair (its €0.10 tick is why the table charges the mean effective spread at size rather than the median), and **no new pair has joined it**.
- **Instrument check 2 — session band**, on the **codified** UTC boundaries (Asia 00–07 / EU 07–15 / US 15–24 — spec `00066` D2, the reference doc's §2, `cli/costs/spread.py`'s docstring): **1.01×–1.10× across all ten pairs, widest LTC 1.099×**. T0014 recorded 1.01×–1.10×, widest **LTC 1.098×** — the same pair, effectively the same number, so **a session term remains unwarranted** and the rejection is re-confirmed rather than assumed. *(A first pass of this check used equal-thirds 00–08/08–16/16–24 and reported a spurious worst of 1.13× on ETH; the review caught it. The conclusion held either way, but only the codified split is an apples-to-apples re-run of T0014's check.)*
- The BTC-quoted legs captured from 2026-07-23 (T0092) are **not** in this window and cannot contaminate it: the panel is EUR-quoted by construction and the query globs `<BASE>/EUR/**`.

- **No registered verdict can move on this — computed, not asserted.** At the €1,400 reference notional on the realistic taker-both-sides stack, the recalibration changes the round-trip cost by at most **0.17 %** (DOT −0.170 %, LINK +0.100 %, everything else under 0.04 %). That is two orders of magnitude below the ×1.37–1.40 cost-basis question [[T0090]] is really about, and consistent with its finding that the fee-tier lever is ~6× the spread term.

`tests/test_costs_spread.py` pins the new table and provenance together, so the next restamp cannot be silent either.
