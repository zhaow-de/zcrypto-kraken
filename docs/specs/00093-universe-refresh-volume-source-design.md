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

Feasibility was checked, not assumed: `XETHXXBT` and `SOLXBT` are live pair keys in `data/snapshots/kraken-refdata-20260804T104009Z.json` (under `raw.assetpairs`), and `data/ohlc-full` already carries `ETH/BTC` (3,679 daily bars to 2026-03-31) and `SOL/BTC` (1,749), so REST's ~720-bar daily window overlaps the seam and both series come back **continuous** rather than detached.

**The venue spells it `XBT`, we spell it `BTC`.** Those pair keys carry `wsname` `ETH/XBT` and `SOL/XBT`; our internal symbols are `ETH/BTC` and `SOL/BTC`. The mapping is therefore a translation, not a copy, and it is the same `XBT`→`BTC` normalisation the repo already applies elsewhere. A first pass at verifying these keys searched for a `/BTC` suffix and came back empty — an empty result that looked exactly like "the legs do not exist". Any implementation or test that matches on the venue's spelling without normalising will reproduce that false negative.

Rejected: **dropping the two legs for a ten-name universe** (10 ≥ `MIN_NAMES` 8) — it works with the reach set exactly as landed, but it removes the two relative-value legs from the tradeable universe, which is a strategy decision and not one a data-plumbing iteration should take. Rejected: **tape-derived bars** ([[T0065]]) — the most durable source long-term, but the `/BTC` tape is 20 days deep against a 30-row median (blocked until ~2026-08-21) and `cli/tick/materialize.py::derive_bars` has no production caller, so it would delay the cluster by ten-plus days plus implementation. Rejected: **widening the staleness budget** — the topic already rejects it, and the EUR-fresh/BTC-stale hybrid is that same option in disguise, because the guard is per-symbol.

### D2 — `PAIR_KEYS` is re-keyed by full symbol

`cli/ohlc/fetch.py::PAIR_KEYS` is keyed by base today (`"ETH": "XETHZEUR"`), which cannot express two quotes for one base. It becomes symbol-keyed (`"ETH/EUR": "XETHZEUR"`, `"ETH/BTC": "XETHXXBT"`).

**The blast radius reaches the engine, and an earlier draft of this decision said it did not.** `cli/engine/store.py` does `from cli.ohlc.fetch import PAIR_KEYS` and re-exports it to `cycle.py`, `soak.py` and the package root; `seed_store`/`refresh_store` iterate it into `root/<key>/EUR/<interval>.parquet`. Re-keying it unqualified would silently widen the engine's basket from ten EUR legs to twelve, produce paths like `root/ETH/BTC/EUR/1440.parquet`, and break a test that pins the BTC-quoted legs as deliberately **excluded**. The false claim came from a grep piped through `head`, which dropped the `store.py` import line — the truncated-sweep failure this project has a rule against.

So the engine keeps a **derived** view rather than the map itself: `cli/engine/store.py` builds `{base: key for symbol, key in PAIR_KEYS.items() if symbol.endswith("/EUR")}`. One source of truth, the engine basket provably unchanged at ten legs, and a test pinning the derivation so a future BTC-quoted leg cannot leak into the engine silently.

Rejected: a separate literal map in `store.py`. Fully decoupled and simplest to reason about, but it duplicates ten pair keys that will drift the first time a venue key changes.

Rejected: keeping the EUR map and adding a second BTC-only map. Smaller diff, but it leaves two maps to keep in sync and makes the symbol no longer the identity — which it already is everywhere else in the codebase.

### D3 — Manifest `series` entries are keyed by full symbol

Forced, not chosen. The reach manifest's entries carry `"symbol": "ADA"` — base only — so adding `ETH/BTC` beside `ETH/EUR` produces two entries both claiming `"ETH"`. Entries become `"ETH/EUR"` / `"ETH/BTC"`.

Incidental benefit worth recording: this moves the reach manifest to the shape every other hot manifest already uses, removing one variant from the zoo [[T0132]] tracks. That is a side effect of a forced change, not a licence to normalise the others here.

### D4 — A source narrower than the candidate set REFUSES

The sharpest finding of the survey: **`escalate` cannot detect a narrower source.** A rebuild whose source covers ten of the twelve candidates yields a ten-name universe with `escalate` still `False` — the exact silent-shrink [[T0093]] exists to prevent, arriving through a different door.

`_refresh_universe` gains a guard that refuses when the source lacks any `CANDIDATE_SYMBOLS` member, raising a `DataSyncError` that **names the missing legs**. This also converts today's untyped `FileNotFoundError`-from-polars into the clean abort the command's contract promises.

The guard is deliberately about **presence of the series**, not about the selection outcome: a symbol the floor legitimately rejects is a selection result and must still flow through `escalate`; a symbol the source never carried is a plumbing fault and must stop the run.

### D4a — The SOURCE is resolved newest-wins too, symmetrically with D5

**The additive-transport problem D5 solves for the artifact applies identically to the source, and an earlier draft solved only one end.** `_require_ohlc_full` hardcodes `data_root / "ohlc-full"`, so nothing points the rebuild at a fresh set — and a fresh reach round lands as `ohlc-reach-<stamp>`, which nothing resolves, for exactly the reason D5 describes: `--ignore-existing` means the promoted `ohlc-reach/` on the hub is frozen at 2026-07-22 forever. Without this decision the attended sitting refuses at its rebuild step no matter how fresh the round was, and D4's guard would only ever guard `ohlc-full`, which always carries all twelve legs and therefore can never trip it.

Source resolution becomes the same rule as the artifact's: **newest `ohlc-reach-<stamp>` sibling wins, falling back to `ohlc-full`**. One concept at both ends, no new mechanism, and D4's guard then applies to the *resolved* root — where a ten-of-twelve reach set is a real possibility rather than a hypothetical.

Rejected: an explicit `--source` flag. Auditable per run, but it puts a load-bearing choice in a hand-typed argument and an omitted flag silently selects the stale default. Rejected: copying the fresh set onto a fixed local path at the sitting. No resolver code, but it reintroduces the mutable-fixed-name problem D5 exists to remove, one layer down, and leaves the hub copy un-updatable anyway.

### D5 — The canonical universe artifact is published as a STAMPED SET, resolved newest-wins

**The problem is not that promotion is unguarded — it is that an additive-only transport cannot express a second version of a fixed filename.** `zcrypto data push` is `rsync --archive --ignore-existing`, never `--delete`, and that is a deliberate spec-`00056` property: a sync can never clobber an edit. But `cli/capture/command.py::UNIVERSE_RELATIVE_PATH` is the fixed `universe/point-in-time-universe.json`. So a same-named artifact **can never be updated on the hub**: after a hand promotion, the local copy carries the new universe while the hub keeps saying `pending-capture` — silently, indefinitely, and every host that fetches gets the stale one. Automating the local copy would not touch that.

So the artifact stops being one mutable file and becomes a series of immutable ones, which is what the transport was built for:

- **Each refresh publishes its own set**, `universe-<stamp>/point-in-time-universe.json`. This is not a new naming concept — `rebuild_sets` *already* mints exactly that sibling; today it is discarded by a hand copy. Now it is the artifact.
- **Publication is `push_hot`'s existing `extra_sets` parameter.** No change to `authored_sets`, no new transport mechanism, and the push stays purely additive — a new set name can never collide with an existing one, so `--ignore-existing` is no longer an obstacle but the correct semantics.
- **Resolution is newest-wins**: the reader takes the highest-stamped `universe-*/point-in-time-universe.json`. The stamp is `%Y%m%d`, so lexicographic order *is* chronological — no date parsing, no tie-break.
- **The legacy `universe/` set is the fallback**, used only when no stamped set exists, so nothing breaks between this landing and the first stamped publish. It is frozen at its 2026-07-07 content and left in `authored_sets`, where re-pushing an unchanging directory is a no-op.
- **`_default_pairs` is the only runtime reader** and is not on the production path — the capture container gets `--pairs` from `CAPTURE_PAIRS`, set from `capture_pairs` in `group_vars`. So the resolver's blast radius is a fallback path plus tests.

The result is that promotion stops being an irreversible hand step at all: publishing is additive, every prior universe stays readable, and "which one is canonical" becomes a resolution rule rather than an act.

Rejected: **deleting the hub copy so a same-named push lands.** One line, keeps one filename, and converts a structural guarantee into per-operator discipline — the invariant exists precisely so no operation reaches into the hub to remove data. Rejected: **stamping the filename inside a single `universe/` set.** This IS transport-viable — `--ignore-existing` skips only files that already exist, so new stamped filenames land through the ordinary authored-sets push — so the rejection rests on the artifact move alone and should be read no more strongly than that: it fights the grain — the rebuild mints directories, so it would need the file lifted out of its sibling into a shared set, adding a move the directory form does not need. Rejected: **a guarded `promote` command that still writes one fixed path.** It makes the smaller problem (an unverified local copy) safe while leaving the larger one (hub divergence) untouched, which is worse than either fixing or naming it, because it looks like a solution.

### D6 — The committed Markdown stays single and git-versioned

`docs/universe/point-in-time-universe.md` is git-tracked, so git already supplies the history that D5's stamping supplies for the JSON; a second stamping scheme there would duplicate it. It stays one file, regenerated by hand (`cli.universe.render_markdown` has no production caller), and its `as_of` must name the stamp of the artifact it describes — that correspondence is the only thing tying the human record to the machine one.

Its basket-hash line is pinned by `tests/test_universe_provenance.py` against `docs/reference/data-catalog.md`, doc-against-doc, because the `data/ohlc` bytes that hash was derived from are gone from disk and from the NAS. That test must be run after any edit to the Markdown, and the data-catalog rows it reads are irreplaceable.

## Verification

- **The extended reach round produces twelve continuous legs**, and the two new ones are checked by value rather than by presence: `ETH/BTC` and `SOL/BTC` must come back `status: continuous` with a non-zero `overlap_bars` against the `ohlc-full` seam. A `detached` status on either is a failure of this iteration, not a data caveat to accept.
- **The shrink guard is proven by construction**, per this project's rule that a guard is unproven until the defect it names is constructed and seen to trip it: a source directory missing one candidate leg must raise `DataSyncError` naming that leg — never `FileNotFoundError`, never a silent ten-name universe with `escalate` `False`.
- **The re-key is proven non-vacuous**: a test that all twelve `CANDIDATE_SYMBOLS` resolve to a pair key, and that the engine's unrelated `PAIR_KEYS` is untouched.
- **Selection is re-measured on the fresh window, not asserted**: all twelve legs evaluated, the passing set stated with each median, and the thinnest passer named. The expectation from the last measured window is 12/12 with DOT/EUR thinnest — a different outcome is a finding to report, not a number to adjust.
- **The resolver is proven by construction, and a newer-but-incomplete set is LOUD**: with two stamped sets present the newer wins; with none present the legacy `universe/` is used; and a newer stamped directory lacking its artifact must produce an audible signal — an ERROR log at minimum, a refusal preferred — never a quiet fall-back to an older universe. Quiet fall-back is the same silent-shrink class as D4, and a test that asserts the quiet behaviour would pin the defect rather than the guard. Note the benign transient this must tolerate deliberately: during an in-flight fetch the directory can exist for seconds before its file lands.
- **Publication is proven additive**: pushing a stamped set twice creates nothing the second time, and pushing a NEW stamp never modifies a previously published one. Assert on rsync's own itemised output, not on the absence of an error.
- **The operational sitting, in order, and it is one sitting**: fresh `zcrypto data rebuild ohlc-reach` → `zcrypto data fetch` to bring it local (`data/ohlc-reach` is absent on the workstation; the promoted set lives only on the read-only NAS) → `zcrypto data rebuild universe` → publish the stamped set. Splitting it rebuilds the canonical universe more than once, and every downstream selection reads that artifact.
- **The Markdown's `as_of` matches the stamp it describes**, and `tests/test_universe_provenance.py` is run after any edit to it (D6).

## What this does NOT do — bounded claims

- **It does not change any deployed behaviour — but only because D2 keeps the engine's basket derived and pinned.** Re-keying `PAIR_KEYS` without that derivation WOULD change deployed behaviour at the next engine converge, by widening the engine's asset basket. That is the decision doing the work, not a property of the change. Beyond it, nothing running reads the universe artifact: capture takes `capture_pairs` from `group_vars`, and the deployed record-44 engine reads a hardcoded asset tuple with no `data/` mount. Rebuilding the artifact is safe *and* inert — changing what is actually traded or captured means separately editing those sources.
- **It does not make the reach set a general replacement for `ohlc-full`.** Reach carries a dump-derived history with a REST-derived tail; this iteration widens its quote coverage and nothing else about its role.
- **It does not close [[T0025]].** That topic's own file says nothing about a universe rebuild — the "pre-live refresh" phrasing lives in [[T0024]], the index, [[T0093]] and the memo, never in T0025, whose actual remainder is the corporate-action ledger. The cluster's framing mis-assigns that work, and this spec does not inherit the mistake.
- **It does not re-derive the retired `data/ohlc` provenance.** Those bytes are gone from disk and from the NAS; the basket hash survives only doc-against-doc, pinned by a test. Treat `docs/reference/data-catalog.md`'s twelve 1440 rows as irreplaceable.
- **It does not retire the legacy `universe/` set.** That directory stays, frozen, as the resolver's fallback and as an `authored_sets` member whose re-push is a no-op. Removing it once a stamped set is published and verified is a deferred action with a trigger, so it is registered as a remainder on [[T0093]] rather than left as prose here.
- **It does not add a freshness guard on the universe artifact itself.** The resolver takes the newest stamp however old that is; nothing refuses a year-old universe. The staleness guard in this iteration is on the OHLC source, not on the published selection.
- **It does not fix the 30-row window's calendar ambiguity.** `median_quote_volume` tails 30 *rows*, not 30 calendar days, so a gap silently widens the wall-clock span the phrase "trailing 30-day median" claims. Measured: over the last 365 bars every symbol's maximum gap is 1 day, so the two coincide today — this is recorded as a latent imprecision, not a live defect.

## Out of scope

- [[T0025]]'s corporate-action ledger.
- Normalising the other manifest shapes ([[T0132]]).
- The two live Kraken public GETs that `_refresh_universe` spends *before* its guards run, so a failing invocation is not free of network side effects. Recorded as a known wart; no dry-run flag exists.
