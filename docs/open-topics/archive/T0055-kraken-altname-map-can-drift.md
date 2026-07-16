---
status: resolved
---

# `KRAKEN_ALTNAME` can silently drift from the capture universe

## Resolution (2026-07-16, iter-100) — closed by DELETING the map, not by testing it

**This topic's own second suggestion was the right one: it ends with a deletion.** `cli/backfill/read.py::dump_pair_name` already *derives* the Kraken altname from a canonical `BASE/QUOTE` symbol — it applies the alias table `{"BTC": "XBT", "DOGE": "XDG"}` to both legs and concatenates. The hardcoded `KRAKEN_ALTNAME` dict was a per-pair duplicate of that derivation, verified two ways before touching anything:

- it reproduced **all 10** hardcoded values exactly (`BTC/EUR→XBTEUR`, `DOGE/EUR→XDGEUR`, `ETH/EUR→ETHEUR`, …);
- Kraken's **live REST accepts the derived name**, including for both irregular pairs — probed: `XDGEUR` ok, `XBTEUR` ok (answers under `XXBTZEUR`, which is why the client reads the response key positionally), `AVAXEUR` ok.

So `cli/trades/rest.py` now calls `dump_pair_name` and the dict is gone. **The drift surface shrinks from per-pair to per-aliased-asset** — an 11th capture pair derives automatically and heals with no code change, *unless its base is a newly aliased asset*: `_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}` (`cli/backfill/read.py`) is still a hardcoded table with nothing tying it to anything, and a new alias would derive wrong exactly as the map did. That residual is far smaller (2 entries covering every asset, vs 10 entries covering 10 pairs) and nearly all new pairs — whose Kraken code equals their common ticker — just work. *(Corrected at branch review: the first draft of this text claimed drift was "structurally impossible". It is not; the class is narrowed, not closed. Claiming otherwise is precisely the overstatement this topic existed to prevent, and a future reader would have trusted it.)* That is strictly better than the test this topic originally asked for, which would only have caught the omission *after* someone made it. Pinned by a test that the never-before-seen pair `XYZ/EUR` derives and issues a request; the `TradeBackfillError` contract for a malformed symbol is preserved (a `BackfillError` escaping would have broken `backfill.py`'s per-pair isolation). No circular import.

The general lesson, worth more than the fix: **the duplicate map was never the problem — it was the second copy of a fact.** Deleting a copy beats guarding it.

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
