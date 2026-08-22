---
status: open
ripe_when: a universe pair undergoes a redenomination, quote-book migration or delisting; or a live-trading universe refresh is about to run.
---

# Full symbol & corporate-action ledger

## Context — what

iter-002 built an alias ledger (XBT=BTC, XDG=DOGE) sufficient for the current 12-name universe. The master plan (§3) calls for a fuller point-in-time symbol & corporate-action ledger — redenominations, quote-book migrations, listing/delisting dates — to keep universe reconstruction survivorship-correct as the venue evolves. `docs/reference/symbol-corporate-action-ledger.md` holds the current (partial) ledger. Deferred per the design's non-goals.

## Why this matters

Survivorship: the OHLCVT/tick archives drop delisted pairs, and a redenomination or quote-book migration silently breaks a symbol's history if unrecorded. A full ledger keeps point-in-time universe reconstruction honest. Low urgency at 12 stable majors with no corporate action to date; matters before any universe change or the live-trading go-live.

## Findings so far

- **This ledger gates nothing, and the 2026-08-13 refresh proved it.** That pre-live refresh ran and published `data/universe-20260813/` without it (iter-137, PR #293), so the sequenced cluster that listed the ledger as a prerequisite was disproved by its own event. An earlier `ripe_when` here claimed the universe-refresh leg was blocked — first by [[T0093]] (resolved 2026-08-13), then by a re-cited condition that was also wrong: `resolve_ohlc_source` reads the newest stamped `ohlc-reach-<stamp>` and falls back to `ohlc-full` only when no stamped sibling exists, so a check against `ohlc-full` inspects a directory the refresh does not consult. What a refresh actually needs is a reach round inside `UNIVERSE_MAX_OHLC_STALENESS_DAYS` — a routine rerun, not a blocker on this topic.

The alias ledger (XBT=BTC, XDG=DOGE) covers the known cases for the current universe; no redenomination / migration / delisting has hit a selected pair. [[T0002]]

## Suggested next steps

- Extend `docs/reference/symbol-corporate-action-ledger.md` to a full point-in-time record (per pair: aliases, redenominations, quote-book migrations, listing/delisting dates), sourced from Kraken announcements + the quarterly OHLCVT ZIPs (which preserve later-delisted pairs).
- Wire a check into `cli/universe/` (or the data QA) that flags a selected pair whose symbol history carries a corporate action.
