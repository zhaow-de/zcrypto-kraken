---
status: open
---

# The deployable's basket has diverged from the refreshed universe — re-ratify or hold

## Context — what

The engine trades record 44's ratified basket: ten EUR legs, a code constant derived from `cli/ohlc/fetch.py::PAIR_KEYS` in `cli/engine/store.py`, connected to no data artifact. The 2026-08-13 universe refresh (iter-137, `universe-20260813`) selected a different eleven: **DOT/EUR out** (median quote volume 146,957.37 vs the 150,000 floor — a real ~25% decline in three weeks, not a measurement artifact) and **ETH/BTC + SOL/BTC in** (both clear the floor comfortably once FX-normalised). Spec `00089` rules that the traded basket stays record 44's ten legs and makes the divergence *observable* — a repo-side concordance test with DOT `traded-but-deselected` and the two /BTC legs `selected-but-unreachable` as its ruled baseline, each exception citing this topic — but whether the basket ever *changes* is a ratification decision no read-only spec can close. The owner kept it genuinely open ("maybe" the /BTC legs go live during 6b) rather than freezing the basket for the phase.

## Why this matters

Two exposures, opposite in direction. While DOT stays in the basket, the executor can size a name the universe has judged too thin — dormant today (the strategy targets DOT at exactly 0.0, and 6b's rung sizes sit well under the €1,400 footprint the floor was calibrated against), but it does not stay dormant by construction. And while the /BTC legs stay unreachable, the ratified strategy surface is narrower than the selected universe: the two relative-value legs the universe considers tradeable cannot be expressed, because the adapter's single `margin_balance_asset="ZEUR"` cannot cover a XXBT-quoted book beside the EUR one (`cli/engine/node.py` documents this: 31 instruments quote in XXBT, one quote currency only). A "yes" on the /BTC half is therefore not a config edit — it must solve the multi-quote margin problem first.

Un-observed, either divergence could silently widen: that part is closed by `00089`'s concordance surface, which turns any *new* selection shift into a red test. What remains here is purely the decision.

## Findings so far

- The basket-to-universe isolation is deliberate and proved itself 2026-08-13: the refresh changed the artifact and the engine's basket did not move. `00089` writes that property down instead of leaving it implicit.
- DOT's exclusion is marginal (2% below the floor) and the floor is a footprint-sizing rule (a full €1,400 max-size position ≈ 1% of median daily volume). At 6b rung sizes the economic exposure of keeping DOT is nil; the exposure is structural, not financial, until the ramp.
- The /BTC legs' unreachability is architectural: `spot_positions_quote_currency`/`margin_balance_asset` are single-valued, and the EUR book is the ratified one. Any solution (second exec client, account-per-quote, adapter change) is real design work with its own blast radius.
- Record 44 is the ratified deployable; changing the basket re-opens its ratification, not just a constant.

## Suggested next steps

- **(autonomous — feeds the decision)** Survey what a multi-quote margin account actually requires in the current adapter: whether two exec clients with distinct `margin_balance_asset` values can coexist against one venue account, what Kraken's margin engine nets across quote currencies, and what the adapter's OpenPositions branch reports for a XXBT-quoted position. Written up as evidence on this topic, no code.
- **(human — the decision)** Rule each half: DOT — keep trading it against the universe's judgment, retire it from the basket at a chosen ramp point, or hold until the next refresh confirms the decline; /BTC legs — pursue the multi-quote solve during 6b (then re-ratify the deployable with the widened basket) or park them for phase 7. Either ruling lands as a registry re-ratification through the committed builder, never a hand-edit of `PAIR_KEYS`.
- On whichever ruling, update `00089`'s concordance baseline in the same change — the ruled-exceptions list is the mechanical form of this topic's answer, and an edit to one without the other is the drift the test exists to catch.
