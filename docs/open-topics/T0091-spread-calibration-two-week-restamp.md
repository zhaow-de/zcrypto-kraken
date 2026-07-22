---
status: open
ripe_when: the `l2-panel` reaches 336 hourly files per pair (≈2026-07-22 20:00 UTC, allowing for the ~7 h settle watermark) — then one re-run of the committed query plus a provenance restamp discharges Phase 2's last carried-forward exit-bar row
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

## Suggested next steps

- **(Autonomous, small)** When the panel reaches 336 h/pair: re-run the calibration, update `SPREAD_CALIBRATION` and the three provenance constants together, restamp `docs/reference/captured-spread-calibration.md`, and re-run the two instrument checks.
- **(With it)** Record in `docs/research/03.phase2-validation-harness-closeout.md` that the carried-forward row is now discharged, with the window that discharged it — the closeout table is where a future reader checks.
- **(Judgement, worth one line)** If the recalibrated constants move by more than the ~1–6 % day-level standard error, that is a signal about regime rather than about arithmetic; say so rather than silently overwriting, and consider whether the reference doc should carry a range instead of a point.
