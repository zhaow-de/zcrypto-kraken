---
status: open
ripe_when: before an 11th pair joins `capture_pairs` — that is the moment it breaks, and the change that triggers it will not look related
---

# `KRAKEN_ALTNAME` can silently drift from the capture universe

## Context — what

`cli/trades/rest.py::KRAKEN_ALTNAME` maps each canonical pair to its Kraken REST altname (`BTC/EUR → XBTEUR`, `DOGE/EUR → XDGEUR`, …). A pair absent from that map raises `TradeBackfillError` on **every** backfill attempt for it.

The map lists exactly the 10 pairs in `capture_pairs` (`infra/ansible/group_vars/capture_host/vars.yml`) **today**. Nothing ties the two together — no derivation, no assert, no test. Found by the iter-100 final review; split out of [[T0053]] at its close as that topic's only live sub-item.

## Why this matters

**The trigger will not look related to this file.** Adding an 11th capture pair is a universe/config decision — nobody making it would think to edit a REST altname map in `cli/trades/`. From that moment the new pair's trades never heal, forever, and the `trade_id`-contiguity invariant silently stops holding for it while holding for the other ten.

The blast radius is now **loud rather than silent**, which is why this is not urgent: since [[T0053]], the day is stamped regardless, so it no longer degrades the daily gate into an hourly one; and [[T0052]]'s `zcrypto_trade_backfill_exit_code > 0` rule fires daily. So the failure announces itself — an operator would see a persistent alert. The defect is that the *cause* is non-obvious, and the fix is trivial.

Note the asymmetry that makes it worth closing properly: a pair missing from the map is caught only at **runtime, nightly, on the NAS**, when the cheapest possible check (does the map cover `capture_pairs`?) could fail at build time in CI.

## Findings so far

- The altname mapping is not mechanical — Kraken's names are irregular (`BTC→XBT`, `DOGE→XDG`), so it cannot simply be derived by string munging; the map (or a lookup of Kraken's `AssetPairs`) is genuinely needed.
- `cli/snapshot/assetpairs.py` and `cli/backfill/read.py` already deal in Kraken altnames (`cli/backfill/read.py` maps canonical → OHLCVT dump altname, including the same `XBT`/`XDG` irregularities) — so a single source of truth may already exist to reuse rather than a second map to maintain.
- The universe itself lives in `data/universe/point-in-time-universe.json` and is what `capture` defaults its pairs from; `capture_pairs` in ansible is the deployed list.

## Suggested next steps

- **(autonomous, cheap — the whole point)** Add a test that `KRAKEN_ALTNAME` covers every pair in the capture universe, so the failure lands in CI at the moment the universe changes, not nightly on the NAS months later. Decide which list is authoritative (the universe file vs the ansible `capture_pairs`) and assert against that one.
- **(autonomous, better if it works)** Check whether `cli/backfill/read.py`'s existing canonical→altname mapping can be reused directly, collapsing the two maps into one. If yes, this topic ends with a deletion rather than an addition.
- **(autonomous, alternative)** Fail loudly at startup instead of per-pair at runtime: validate the map against the pairs to be swept before the sweep begins, so the error names the cause ("pair X has no Kraken altname") rather than surfacing as one failing pair among ten.
