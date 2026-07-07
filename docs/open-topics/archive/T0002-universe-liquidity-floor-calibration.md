---
status: resolved
---

# Universe liquidity-floor calibration & quote-currency-aware volume (§3 escalation)

## Context — what

iter-005's rule-driven universe finalization (`cli/universe/`) applied §3's rule to the 12-symbol candidate basket and selected only **6 names** (BTC/EUR, ETH/EUR, SOL/EUR, XRP/EUR, ADA/EUR, LTC/EUR), firing the §3 escalation (`escalate: True`, 6 < `MIN_NAMES` 8). Two drivers, both requiring a human/design call:

1. **Thin Kraken-EUR alt liquidity vs the €1M/day floor.** At the (loop-chosen, tunable) €1,000,000/day median-quote-volume floor, LINK (€283k), DOGE (€501k), DOT (€182k), and AVAX all fall below — their Kraken **EUR** pairs are genuinely shallow. This is real, not a bug.
2. **Quote-currency unit mismatch on the BTC-quoted RV legs.** ETH/BTC and SOL/BTC are dropped because their `volume × vwap` is **BTC-denominated**, not comparable to a **EUR** floor — a real correctness gap in the single-currency floor.

## Why this matters

The point-in-time universe file (`docs/universe/point-in-time-universe.md`) is a hard dependency of every backtest. A 6-name basket materially diverges from §3's recommended 10–12, and §3 makes exactly this case (`<8` names / material divergence) a **human decision**, not an autonomous one.

## Findings so far

- Live 30d median quote volume (iter-005): BTC €27.8M, ETH €11.5M, SOL €5.4M, XRP €4.0M, ADA €1.30M, LTC €1.25M (pass); LINK €283k, DOGE €501k, DOT €182k, AVAX <€1M (fail). BTC/EUR–ETH/EUR mandatory legs pass comfortably.
- The finalize-universe machinery + escalation logic are built and tested (iter-005); only the parameters and the cross-quote handling are open.

## Suggested next steps (human decision)

- Calibrate the volume floor, or decide the basket policy: lower the EUR floor; **or** route the thinner alts through their deeper Kraken **USD-quoted** pairs (USD books are deeper than EUR for alts); **or** accept a smaller EUR-only basket (6–8 names); **or** per-quote-currency floors.
- Make the volume floor quote-currency-aware: convert a BTC-quoted leg's volume to EUR via the BTC/EUR price (or apply a BTC-denominated floor to BTC legs) so ETH/BTC & SOL/BTC are judged on real turnover, not a unit artifact.
- Re-run `finalize_universe` with the calibrated parameters and re-generate the universe file.

## Resolution (iter-007, 2026-07-07)

Resolved by **lowering the EUR floor and making the volume metric quote-currency-aware**, grounded in a live EUR-vs-USD-vs-USDT depth + margin-parity + FX/tax analysis (recorded in master-plan §3): USD books are 2–8.5× deeper, but that depth does not bind at ~$10k (a full per-name position is <1% of even the thinnest EUR book) and EUR gives up zero margin capability, while USD adds conversion/FX/§23-tax friction. So:

- **Floor `€1,000,000 → €150,000`/day** (`DEFAULT_MIN_MEDIAN_QUOTE_VOLUME`, commit `9495e2d`) — footprint-based (a full max-size position ≈1% of median daily EUR volume). Admits LINK/DOGE/DOT/AVAX.
- **`quote_volume_in_eur`** FX-normalizes the BTC-quoted RV legs (ETH/BTC → €579,964, SOL/BTC → €233,595) via the BTC/EUR daily close, ending the unit mismatch.
- **Result:** the full §3 target of **12 names** (10 EUR + 2 BTC RV), `escalate=False`. `docs/universe/point-in-time-universe.md` regenerated; findings + the floor decision inserted into master-plan §3.
- **Deferred (not this topic):** routing thin alts via deeper USD pairs is a pre-registered **scaling trigger** (revisit at ~5–10× this account); USDT ruled out entirely (thinnest venue, MiCA-delisted for EEA, breaks AVAX margin). The spread-cap criterion still awaits the L2 capture daemon.
