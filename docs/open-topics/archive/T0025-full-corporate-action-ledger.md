---
status: resolved
---

# Full symbol & corporate-action ledger

## Context — what

iter-002 built an alias ledger (XBT=BTC, XDG=DOGE) sufficient for the current 12-name universe. The master plan (§3) calls for a fuller point-in-time symbol & corporate-action ledger — redenominations, quote-book migrations, listing/delisting dates — to keep universe reconstruction survivorship-correct as the venue evolves. `docs/reference/symbol-corporate-action-ledger.md` holds the current (partial) ledger. Deferred per the design's non-goals.

## Why this matters

Survivorship: the OHLCVT/tick archives drop delisted pairs, and a redenomination or quote-book migration silently breaks a symbol's history if unrecorded. A full ledger keeps point-in-time universe reconstruction honest. Low urgency at 12 stable majors with no corporate action to date; matters before any universe change or the live-trading go-live.

## Findings so far

- **This ledger gates nothing, and the 2026-08-13 refresh proved it.** That pre-live refresh ran and published `data/universe-20260813/` without it (iter-137, PR #293), so the sequenced cluster that listed the ledger as a prerequisite was disproved by its own event. An earlier `ripe_when` here claimed the universe-refresh leg was blocked — first by [[T0093]] (resolved 2026-08-13), then by a re-cited condition that was also wrong: `resolve_ohlc_source` reads the newest stamped `ohlc-reach-<stamp>` and falls back to `ohlc-full` only when no stamped sibling exists, so a check against `ohlc-full` inspects a directory the refresh does not consult. What a refresh actually needs is a reach round inside `UNIVERSE_MAX_OHLC_STALENESS_DAYS` — a routine rerun, not a blocker on this topic.

The alias ledger (XBT=BTC, XDG=DOGE) covers the known cases for the current universe; no redenomination / migration / delisting has hit a selected pair. [[T0002]]

- **The refresh leg was REMOVED from the trigger 2026-08-23, because it fired and was answered.** The trigger used to read "…or a live-trading universe refresh is about to run". That leg fired on 2026-08-13: the refresh ran, published `data/universe-20260813/`, and needed nothing from this ledger — the finding above. A trigger that fires and is adjudicated to *no* every time is not a trigger; leaving it in only guarantees the next refresh re-derives the same answer. What remains is the leg that would actually make this work live: a selected pair changing identity underneath us. Verified 2026-08-23 against Kraken's published delistings — none touches the twelve selected pairs, so it has not fired.

## Resolution

**Resolved 2026-08-28.** The trigger is retired rather than waited on: detection moved onto `/zcrypto-refdata-sweep`, the routine that already runs monthly and mandatorily before the go/no-go, so the event this topic was parked for is now caught by something that runs whether or not anyone remembers this file.

**Two of the three trigger legs are watched, twice over.**

- **Delisting** — `sweep_refusals` refuses when a selected pair is absent from `AssetPairs` (the day it happens), and `scan_delistings` reads the venue's own announcements, published **93–116 days ahead** for an asset delisting — a funding-rail discontinuation can arrive after it takes effect, so a hit's own dates decide whether it is a planning input. Both run at step 3 of the sweep, which now *refuses* rather than rendering a table for someone to diff by eye.
- **Redenomination** — reaches us as an altname drift, and `sweep_refusals` compares every selected asset against `_COMMON_TO_KRAKEN`, the same constant the wsname lookup tolerates spellings from, so the check and the parser cannot disagree about what the alias is.

**The third leg is NOT watched, and that is a decision rather than an oversight.** A quote-book migration is reported by no endpoint, so there is nothing to compare; it is named as an accepted gap in `cli/snapshot/register.py`, in the sweep's step 3, and here. If a source ever appears, this is the paragraph that says why there wasn't one.

**The point-in-time record exists, and building it corrected the ledger.** `docs/reference/symbol-corporate-action-ledger.md` now carries per-pair first/last bar for all twelve pairs — the half of this topic that was never event-gated at all and had been waiting on a trigger for no reason. Measuring it disproved a claim the ledger had been carrying: the DOT 1:100 redenomination is **in** our price history, in bar one's `open`/`high` on 2020-08-18, invisible to the close-based audit because the whole transition completes inside the first bar at every resolution. The transferable half is now a maintenance rule — hand-read bar one of every newly admitted pair — because `price_discontinuities` is structurally blind to that class, not merely unlucky.

**Proven, not asserted**: every check is a constructed defect on real data with an unmutated control that must stay silent — the archived 2026-08-04 snapshot for the refusals, the live 50-entry feed for the delisting scan. The control matters as much as the trip: Kraken delists constantly and almost none of it is ours, so a scan that flags everything is one nobody reads.

**Review found three things worth recording** (Fable floor, this branch): the scan missed announcements that name assets only in the body — the live feed contains one — and case-insensitive body matching would have fired `LINK` on "the link below"; the sweep's step 3 could not run verbatim, and the hand-repair it invited could judge a stale snapshot and report a false clean on the go/no-go; and the DOT bullet stated a unit attribution the arithmetic does not support (1:100 predicts ~261 EUR, observed 29–45 is 11.1–17.2x), which would have armed a 1/100 "correction" turning 29.00 into 0.29.
