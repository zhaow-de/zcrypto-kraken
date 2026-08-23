---
status: partial
ripe_when: spec `00092`'s continuous order loop is built
---

# Engine config gaps that only bite when orders flow

## Context — what

Three Nautilus node settings are correct for shadow and wrong for live orders, verified in the capability map 2026-07-30: `default_leverage` is unset; `spot_positions_quote_currency` defaults to `"USDT"` on a EUR-quoted book; and the venue open-order / position-discrepancy polling is OFF (`open_check_interval_secs` / `position_check_interval_secs` both `None`). None of the three can misbehave while the node only logs intents — all three can the day it submits.

## Why this matters

The go/no-go gate's "zero unreconciled order/position states" almost certainly needs the discrepancy polling ON to mean anything — with it off, an unreconciled state is not detected, which reads as zero. The USDT default mis-denominates spot position accounting on a EUR book, and an unset `default_leverage` leaves margin-order semantics to a library default nobody chose. Cheap to fix now; expensive to discover as a rung-1 surprise.

## Findings so far

- All three read from the node build path (2026-07-30 capability audit); none is overridden in `zcrypto.toml` or the engine role's rendered config.
- The right values need one decision each, not research: leverage per the margin plan (§12 kickoff D3), quote currency EUR, polling intervals on with values that respect Kraken's rate budget (the REST pacing floor measured in T0053 is the reference for what the budget tolerates).

## Done so far

- **`spot_positions_quote_currency` is set to `"ZEUR"` (iter-119), and the value is the finding.** This topic assumed "quote currency EUR" was a ruling to apply, not research — that was wrong, and the plausible value fails **silently**. The adapter compares this string literally against the instrument's quote-currency `code`. Measured against the real loaded Kraken spot universe (1,592 instruments): **546 carry code `ZEUR`, 0 carry `EUR`**, 31 carry `XXBT`, 814 `ZUSD`. The trap is that the instrument *ID* renders as `ADA/EUR.KRAKEN` — `normalize_spot_symbol` renames the **symbol** — while the quote `Currency` object keeps Kraken's legacy `Z` prefix. So `"EUR"` matches nothing, exactly like the `"USDT"` default it replaces: an empty position report that looks like a flat book. A first implementation did set `"EUR"`, inferring from `normalize_currency_code`'s existence in the adapter without checking whether that path reaches the quote currency; it does not. The pinning test cites the measured histogram rather than any normalization claim, so a future plausible-looking "correction" back to `"EUR"` fails.
- **Recorded, not built for**: the field takes a *single* quote currency, so the EUR book and the `XXBT`-quoted `ETH/BTC` / `SOL/BTC` pairs cannot both be covered by it. Also inert today for a second reason — under `spot_account_type=MARGIN` the adapter takes the `OpenPositions` branch and never reads the field; it becomes live if a CASH fallback or `use_spot_position_reports` ever applies. Set anyway because the failure mode when it does become live is silent.
- **`default_leverage` is deliberately left UNSET — a ruling, not an omission (owner, 2026-08-02).** The adapter treats `None` as cash (no leverage sent), and the node already runs `spot_account_type=AccountType.MARGIN`, which is what enables per-order leverage via `SubmitOrder.params={"leverage": N}`. A global default would silently lever **every** ordinary rebalance of a book §10 caps at 1.5×/2.0× gross; the master plan rules the book's gross cap and does not rule a per-order default. Rung 1's T2 probe still gets its margin long and margin short by passing leverage per order, so nothing downstream is blocked by leaving it unset. This closes the topic's "flag for a decision only if the margin plan leaves leverage genuinely open" branch: it does, and the answer is cash-by-default.

## Suggested next steps

- **(autonomous — owner `00092`, re-deferred there 2026-08-18)** Set `open_check_interval_secs` / `position_check_interval_secs` once a **continuous** order loop's REST call pattern exists, since the intervals are a share of a request budget that pattern defines ([[T0053]]'s measured pacing floor is the reference for what the budget tolerates). Deliberately not guessed now: the go/no-go's "zero unreconciled order/position states" leans on this poll, so a number invented against an unmeasured budget would make the gate read clean by not looking.
  **Why `00090` did not discharge it, stated so the deferral reads as chosen rather than missed.** The old trigger ("the 6b executor iteration defines the node's REST call pattern") arguably fired at `00090` — an executor landed, and it does read venue state. But `00090`'s reconciliation is **post-terminal and startup-time, not a standing poll loop**: it reads at each intent's terminal and once at startup, inside attended probe windows measured in hours, and nothing in it runs between windows at all. That produces no standing request rate to divide a budget against, so an interval set here would be a number chosen against an absent denominator — precisely the invented-against-an-unmeasured-budget failure this sub-item was registered to avoid. `00092`'s cycle-driven loop is the first thing that creates a continuous call pattern, so it is the first place the intervals are computable rather than guessed. `00090` states the same bound in its own words (its `## What this does NOT do` and `## Out of scope`, both naming this topic).
