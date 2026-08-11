---
status: open
ripe_when: a universe pair undergoes a redenomination / quote-book migration / delisting, or before a live-trading universe refresh. NOTE the universe-refresh leg is BLOCKED by [[T0093]]: `_refresh_universe` fails closed because `ohlc-full` ends 2026-03-31 — measured against that stale window a rebuild would select eleven names (AVAX/EUR below the volume floor), which is why the guard exists; spec `00093` corrected the figure as a stale-window artifact rather than a liquidity finding — on a fresh window all twelve pass, DOT/EUR thinnest. A live-tailed volume source must exist first — quarterly dump ingestion cannot satisfy the staleness budget
---

# Full symbol & corporate-action ledger

## Context — what

iter-002 built an alias ledger (XBT=BTC, XDG=DOGE) sufficient for the current 12-name universe. The master plan (§3) calls for a fuller point-in-time symbol & corporate-action ledger — redenominations, quote-book migrations, listing/delisting dates — to keep universe reconstruction survivorship-correct as the venue evolves. `docs/reference/symbol-corporate-action-ledger.md` holds the current (partial) ledger. Deferred per the design's non-goals.

## Why this matters

Survivorship: the OHLCVT/tick archives drop delisted pairs, and a redenomination or quote-book migration silently breaks a symbol's history if unrecorded. A full ledger keeps point-in-time universe reconstruction honest. Low urgency at 12 stable majors with no corporate action to date; matters before any universe change or the live-trading go-live.

## Findings so far

The alias ledger (XBT=BTC, XDG=DOGE) covers the known cases for the current universe; no redenomination / migration / delisting has hit a selected pair. [[T0002]]

## Suggested next steps

- Extend `docs/reference/symbol-corporate-action-ledger.md` to a full point-in-time record (per pair: aliases, redenominations, quote-book migrations, listing/delisting dates), sourced from Kraken announcements + the quarterly OHLCVT ZIPs (which preserve later-delisted pairs).
- Wire a check into `cli/universe/` (or the data QA) that flags a selected pair whose symbol history carries a corporate action.
