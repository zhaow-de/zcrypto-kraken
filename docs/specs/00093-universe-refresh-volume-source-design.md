# The universe refresh's volume source

Unblocks [[T0093]] — step 2 of the pre-live universe-refresh cluster ([[T0092]] → [[T0093]] → [[T0025]] → [[T0024]]) — by giving `_refresh_universe` a source that reaches the present for **all twelve** candidate symbols, and by making a narrower source refuse instead of silently shrinking the universe.

The serial is **00093**, not the next free 00089: [[T0018]] has already registered `00089`–`00092` for the 6b executor sequence. Because the serial rule picks *highest + 1*, a gap can never be reached back into, so the reservation is self-enforcing.

## Context — what is actually blocked, and three corrections the topic does not carry

**A rebuild refuses today on every candidate source.** `_require_fresh_ohlc` was executed against a live clock (2026-08-11, budget `UNIVERSE_MAX_OHLC_STALENESS_DAYS = 7`):

| source | stalest daily bar | staleness | verdict |
| --- | --- | --- | --- |
| `data/ohlc-full` | 2026-03-31 | 133 d | REFUSES |
| `hot/ohlc-reach` | 2026-07-22 | 20 d | REFUSES |
| `data/ohlc-holdout-2026-07-10` | 2026-07-09 | 33 d | REFUSES |

So [[T0093]]'s "the reach set's stalest bar is 1 day old" and the memo's "pickable now" were true on 2026-07-23 and are stale prose today. **A fresh reach round is a precondition of the refresh, not an alternative to it.**

**The "a rebuild today selects ELEVEN, dropping AVAX/EUR" figure is a stale-window artifact, not a liquidity finding.** It reproduces exactly — 132,274.82 against a 150,000 floor — but only over `ohlc-full`'s March window (2026-03-02…03-31), because the "trailing 30 days" is the last 30 *rows* of a set frozen at 2026-03-31. On every fresh window AVAX clears comfortably: **208,265.93** on the reach window, **267,840.43** on the holdout. Under a fresh window the thinnest passer is **DOT/EUR at 194,771.98**, ~30 % above the floor. Nobody is near the floor from below, and the counterfactual must not be read as an outcome.

**Therefore the ruling was never "eleven names or twelve" — it is what supplies `ETH/BTC` and `SOL/BTC`.** The reach set is structurally EUR-only: `cli/ohlc/reach.py::_canonical_symbols` globs `*/EUR/{interval}.parquet` and the read and write paths hardcode `"EUR"`, so **no number of re-runs can ever produce the BTC-quoted legs**. Today a naive repoint would crash on `ETH/BTC` with an untyped `FileNotFoundError` from inside polars, escaping `zcrypto data rebuild`'s `except DataSyncError` — the operator gets a traceback, not the clean one-line abort the command promises.

## Decisions

### D1 — Extend the reach round to the BTC-quoted legs

The owner's ruling. Reach becomes quote-aware and mints all twelve legs, so the universe keeps its twelve names and no strategy question is opened.

Feasibility was checked, not assumed: `XETHXXBT` and `SOLXBT` are live pair keys in `data/snapshots/kraken-refdata-20260804T104009Z.json` (under `raw.assetpairs.result`), and `data/ohlc-full` already carries `ETH/BTC` (3,679 daily bars to 2026-03-31) and `SOL/BTC` (1,749), so REST's ~720-bar daily window overlaps the seam and both series come back **continuous** rather than detached.

**The venue spells it `XBT`, we spell it `BTC`.** Those pair keys carry `wsname` `ETH/XBT` and `SOL/XBT`; our internal symbols are `ETH/BTC` and `SOL/BTC`. The mapping is therefore a translation, not a copy, and it is the same `XBT`→`BTC` normalisation the repo already applies elsewhere. A first pass at verifying these keys searched for a `/BTC` suffix and came back empty — an empty result that looked exactly like "the legs do not exist". Any implementation or test that matches on the venue's spelling without normalising will reproduce that false negative.

Rejected: **dropping the two legs for a ten-name universe** (10 ≥ `MIN_NAMES` 8) — it works with the reach set exactly as landed, but it removes the two relative-value legs from the tradeable universe, which is a strategy decision and not one a data-plumbing iteration should take. Rejected: **tape-derived bars** ([[T0065]]) — the most durable source long-term, but the `/BTC` tape is 20 days deep against a 30-row median (blocked until ~2026-08-21) and `cli/tick/materialize.py::derive_bars` has no production caller, so it would delay the cluster by ten-plus days plus implementation. Rejected: **widening the staleness budget** — the topic already rejects it, and the EUR-fresh/BTC-stale hybrid is that same option in disguise, because the guard is per-symbol.

### D2 — `PAIR_KEYS` is re-keyed by full symbol

`cli/ohlc/fetch.py::PAIR_KEYS` is keyed by base today (`"ETH": "XETHZEUR"`), which cannot express two quotes for one base. It becomes symbol-keyed (`"ETH/EUR": "XETHZEUR"`, `"ETH/BTC": "XETHXXBT"`).

The blast radius was measured and is two files: within `cli/`, only `cli/ohlc/reach.py` imports it. **`cli/engine/cycle.py`'s `PAIR_KEYS` is a different symbol** from `cli.engine.store` and is not touched — a grep that does not distinguish them will over-scope this change.

Rejected: keeping the EUR map and adding a second BTC-only map. Smaller diff, but it leaves two maps to keep in sync and makes the symbol no longer the identity — which it already is everywhere else in the codebase.

### D3 — Manifest `series` entries are keyed by full symbol

Forced, not chosen. The reach manifest's entries carry `"symbol": "ADA"` — base only — so adding `ETH/BTC` beside `ETH/EUR` produces two entries both claiming `"ETH"`. Entries become `"ETH/EUR"` / `"ETH/BTC"`.

Incidental benefit worth recording: this moves the reach manifest to the shape every other hot manifest already uses, removing one variant from the zoo [[T0132]] tracks. That is a side effect of a forced change, not a licence to normalise the others here.

### D4 — A source narrower than the candidate set REFUSES

The sharpest finding of the survey: **`escalate` cannot detect a narrower source.** A rebuild whose source covers ten of the twelve candidates yields a ten-name universe with `escalate` still `False` — the exact silent-shrink [[T0093]] exists to prevent, arriving through a different door.

`_refresh_universe` gains a guard that refuses when the source lacks any `CANDIDATE_SYMBOLS` member, raising a `DataSyncError` that **names the missing legs**. This also converts today's untyped `FileNotFoundError`-from-polars into the clean abort the command's contract promises.

The guard is deliberately about **presence of the series**, not about the selection outcome: a symbol the floor legitimately rejects is a selection result and must still flow through `escalate`; a symbol the source never carried is a plumbing fault and must stop the run.

### D5 — Promotion stays manual, and this spec does not automate it

`rebuild_sets` mints a sibling `data/universe-<stamp>/` and never writes `data/universe/`. Making a minted set canonical is a hand copy with no guard, no hash check and no refusal — and it is the one irreversible step in the whole refresh. `zcrypto data push` uses `rsync --ignore-existing` with no `--delete`, so the NAS canonical copy **cannot be updated in place** by a push.

Automating that is real work and is **out of scope here** — this iteration is the volume source and the shrink guard. What this spec does owe is the procedure, prescribed rather than improvised, in **Verification** below. The gap is registered in [[T0093]] rather than left in prose.

## Verification

- **The extended reach round produces twelve continuous legs**, and the two new ones are checked by value rather than by presence: `ETH/BTC` and `SOL/BTC` must come back `status: continuous` with a non-zero `overlap_bars` against the `ohlc-full` seam. A `detached` status on either is a failure of this iteration, not a data caveat to accept.
- **The shrink guard is proven by construction**, per this project's rule that a guard is unproven until the defect it names is constructed and seen to trip it: a source directory missing one candidate leg must raise `DataSyncError` naming that leg — never `FileNotFoundError`, never a silent ten-name universe with `escalate` `False`.
- **The re-key is proven non-vacuous**: a test that all twelve `CANDIDATE_SYMBOLS` resolve to a pair key, and that the engine's unrelated `PAIR_KEYS` is untouched.
- **Selection is re-measured on the fresh window, not asserted**: all twelve legs evaluated, the passing set stated with each median, and the thinnest passer named. The expectation from the last measured window is 12/12 with DOT/EUR thinnest — a different outcome is a finding to report, not a number to adjust.
- **The operational sitting, in order, and it is one sitting**: fresh `zcrypto data rebuild ohlc-reach` → `zcrypto data fetch` to bring it local (`data/ohlc-reach` is absent on the workstation; the promoted set lives only on the read-only NAS) → `zcrypto data rebuild universe` → promotion. Splitting it rebuilds the canonical universe more than once, and every downstream selection reads that artifact.
- **Promotion procedure**, since D5 leaves it manual: record the minted sibling's JSON sha256 before the copy, copy onto `data/universe/`, re-read and confirm the sha256 matches, and only then treat it as canonical. The committed `docs/universe/point-in-time-universe.md` is regenerated by hand — `cli.universe.render_markdown` has no production caller — and its basket-hash line is pinned by `tests/test_universe_provenance.py`, so that test must be run after any edit to it.

## What this does NOT do — bounded claims

- **It does not change any deployed behaviour.** Nothing running reads the universe artifact: capture takes `capture_pairs` from `group_vars`, and the deployed record-44 engine reads a hardcoded asset tuple with no `data/` mount. Rebuilding the artifact is safe *and* inert — changing what is actually traded or captured means separately editing those sources.
- **It does not make the reach set a general replacement for `ohlc-full`.** Reach carries a dump-derived history with a REST-derived tail; this iteration widens its quote coverage and nothing else about its role.
- **It does not close [[T0025]].** That topic's own file says nothing about a universe rebuild — the "pre-live refresh" phrasing lives in [[T0024]], the index, [[T0093]] and the memo, never in T0025, whose actual remainder is the corporate-action ledger. The cluster's framing mis-assigns that work, and this spec does not inherit the mistake.
- **It does not re-derive the retired `data/ohlc` provenance.** Those bytes are gone from disk and from the NAS; the basket hash survives only doc-against-doc, pinned by a test. Treat `docs/reference/data-catalog.md`'s twelve 1440 rows as irreplaceable.
- **It does not fix the 30-row window's calendar ambiguity.** `median_quote_volume` tails 30 *rows*, not 30 calendar days, so a gap silently widens the wall-clock span the phrase "trailing 30-day median" claims. Measured: over the last 365 bars every symbol's maximum gap is 1 day, so the two coincide today — this is recorded as a latent imprecision, not a live defect.

## Out of scope

- Automating promotion, and the fact that `rsync --ignore-existing` cannot update the NAS canonical copy in place (D5) — registered in [[T0093]].
- [[T0025]]'s corporate-action ledger.
- Normalising the other manifest shapes ([[T0132]]).
- The two live Kraken public GETs that `_refresh_universe` spends *before* its guards run, so a failing invocation is not free of network side effects. Recorded as a known wart; no dry-run flag exists.
