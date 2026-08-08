---
status: resolved
---

# Two universe legs have no L2 capture, so the spread cap cannot screen them

## Context — what

The capture daemon subscribes to **EUR-quoted pairs only**. Verified against the archive: every base under `/mnt/zhao-crypto/capture-reconciled/<BASE>/` has exactly one quote directory, `EUR`, and nothing else.

The point-in-time universe, however, selects **twelve** symbols — ten EUR-quoted plus **`ETH/BTC` and `SOL/BTC`**, the BTC-quoted relative-value legs. Those two have no L2 capture at all, and therefore no spread.

[[T0024]]'s spread cap (spec `00067`) consequently screens 10 of 12. The two uncaptured legs are recorded `spread_bps: null` on their universe entries and are **not** rejected — absence of evidence is not evidence of a wide spread — but they are equally not *checked*.

## Why this matters

The cap exists because "a thin-book pair could clear the €150k/day volume floor yet be untradeable at our sizing". `SOL/BTC` sits at **233,595 EUR/day** median quote volume — barely above the €150k floor, and one of the two symbols the cap cannot see. The gap sits precisely where the criterion was most wanted.

It is not urgent: nothing today suggests those legs are untradeable, they are relative-value legs rather than core exposure, and the cap binds on nothing anywhere in the universe right now. But a criterion that silently covers 10/12 while reading as a universe-wide filter is the "green because we stopped looking" shape, which is why the nulls are surfaced in the artifact rather than hidden.

## Findings so far

- Capture coverage measured 2026-07-22: 10 bases × `EUR` only. Both BTC-quoted legs absent.
- Both legs are genuinely selected members, not candidates: `ETH/BTC` (579,964 EUR/day, max leverage 5) and `SOL/BTC` (233,595 EUR/day, max leverage 4).
- The cost model has the same blind spot for the same reason — `cli/costs/spread.py`'s table is keyed by base and calibrated from EUR pairs, so a BTC-quoted notional resolves to the **EUR** leg's number rather than erroring: `effective_spread_bps("ETH", 1400)` returns ETH/EUR's 0.524, and only the full-symbol form raises. A BTC-quoted leg would get a silently wrong value, not a loud failure; the only thing preventing that today is `_refresh_universe`'s `quote == "EUR"` filter. `round_trip_cost` is a second, unguarded public entry point with no caller yet — any future cost accounting on those legs inherits this gap.
- Adding two subscriptions is not free: it touches a **live, unbackfillable** capture pipeline (the canary rule in `capture-deploys.md` applies), adds two more streams to the reconciler and the panel, and grows the archive. The cost is operational, not analytical.

## Done so far

**(2026-08-08) RESOLVED — the calibration remainder landed, spec `00085`.** The three parts ran in the order this topic insisted on. **The ladder first:** `NOTIONALS_EUR` became `NOTIONALS_BY_QUOTE`, with BTC rungs held as the BTC quantities worth EUR 100/1k/10k at a pinned `BTC_EUR_REFERENCE = 55876.28413495087` measured over its own fixed window, so column identity and the EUR-denominated grid survive. The four EUR-scope guards lifted with it. **Then the regeneration:** ops converged to `65402dc67701` and the whole panel tree was rebuilt 2026-08-07 12:55→22:26Z — 7,836 hours, `hours_unanchored=0`, `errors=0`, and the two `/BTC` subtrees built for the first time. Verified on the tree rather than inferred: all six `fill_bps_*` columns read **100 % non-null** on both legs (ETH/BTC 0.684→1.259 bps @100→@10k, SOL/BTC 0.910→2.672), monotonic in size, where every one was previously null. **Then the calibration and re-key:** `SPREAD_CALIBRATION` is keyed by full symbol with twelve rows over one shared window `2026-07-23T14:00Z…2026-08-07T19:00Z` (365 h, 15.21 days, `min_rows == max_rows == 1,314,000` — zero missing seconds), and `cli/data/rebuild.py`'s quote guard collapsed to plain membership. The re-key is proven load-bearing by mutation probe: reverting to a base lookup is KILLED.

Two findings the work produced, both recorded where they will be read again. The **EUR rows moved materially** across the restamp — 9 of 10 by >2 %, worst −25.01 % (DOT @1k) — against the spec's "under 2 %" estimate, which is corrected in place; the move is attributable to the window, not the pipeline, and a permanent control test holds the superseded values as literals to keep proving that. And the window end is now pinned by a test against Phase 2's **≥2-week exit bar**: the window first drafted for this restamp ran 13.67 days and would have un-discharged that bar with every other assertion still green.


**(2026-07-23) Option (a) taken — the legs are captured.** The owner ruled to capture rather than exempt or drop, on the asymmetry: capturing-and-dropping costs a config line and ~0.1 GB/day, while not-capturing-and-later-needing costs a permanently late start date on 2 of the 12 selected members. L2 book is unbackfillable, so the start date is the entire cost of waiting.

**A 15-agent pre-flight audit ran before the change** (7 consumer surfaces, each independently re-verified, plus a completeness critic). Its headline corrected the premise this topic was written on:

- **The one-quote-dir-per-base observation is NOT a latent assumption anywhere.** Verified empirically — probes drove real two-quote trees through `materialize`, `scan_hours`, `hour_path` and `continuity.report`. Every archive walker globs the quote as its own path level and keys on `BASE/QUOTE` (`cli/archive/reader.py:24,29`; `settle.py:72,81`; `infra/scripts/continuity.py:44,48`), and capture's layout falls out of `base_dir / pair / kind` structurally. Path handling was never the risk.
- **The real blocker was the panel's notional ladder**, which is quote-*denominated* but EUR-*labelled*, with no pair filter on the hourly sweep. The first rationale written here was **wrong and the review corrected it by measurement**: the rungs read as 100/1k/10k *BTC*, and at the 2026-03-31 BTC/EUR close (EUR 58,968.90) the @100 rung alone asks EUR 5.9 M — ~10× ETH/BTC's and ~25× SOL/BTC's entire daily volume — so `_fill_bps` returns None and all six `fill_bps_*` columns go **null**, rather than yielding a plausible wrong number. (The "it wrote a full wrong panel" demonstration was real but ran against the synthetic test fixture, whose prices 99–102 make the @100 rung fillable; it does not generalize to the live pairs.) The fix is unchanged and still right — a dead EUR-labelled ladder on an out-of-scope tree is worth excluding — only its justification needed repair.
- **Two hazards were ruled out by measurement, not argument.** A 15-minute read-only public-WS probe: `ETH/BTC` 8.15 updates/s (longest silence 8.1 s), `SOL/BTC` 7.06 updates/s (longest silence 3.0 s), against `ETH/EUR` 30.2 updates/s as control. That kills (i) the zero-update-book-hour hazard — an hour is 3600 s, so it would need a silence 443× longer than anything observed, and a bracketed absent **book** hour is ledgered `total_loss` → a CRITICAL page plus a permanent append-only record (books are judged with `alive_witness=None` by design, `cli/archive/settle.py:161`, unlike trades); and (ii) the `continuity.py` head/tail artifact, which produces phantom truncations and a permanent exit-bar FAIL above ~2.3 s mean spacing — measured spacing is 0.12–0.14 s, clear by ~17×.
- **Trade-id density verified** for both legs before the change (`spec 00053`'s invariant): one keyless `/Trades` page each returned 1000 rows / 1000 distinct ids / span 1000 — perfectly dense, so the REST backfill path is sound. Its failure mode would have been invisible to Prometheus.

**What landed:**

- `infra/ansible/group_vars/capture_host/vars.yml` — `capture_pairs` 10 → 12.
- **Panel scoped to EUR-quoted pairs** (`cli/panel/primitives.py`'s new `PANEL_QUOTE`): the sweep skips non-EUR pairs (logged once per pair, not per hour), `_affected_pairs` matches that scope so the completion line's `pairs=N` stays truthful, and an explicit `--pair ETH/BTC` now fails loudly instead of exiting 0 having written a wrong panel — which is what it did before the fix, measured. This is the correct scope rather than a compromise: the calibration reads `l2-panel/<BASE>/EUR/**` by design.
- **`_default_pairs` now warns** when the universe's non-EUR symbols are dropped on the no-`--pairs` fallback path (production passes `--pairs` explicitly, so this is a guard against silent under-collection, not a live defect).
- **Two-quote behaviour is pinned** for the first time (`tests/test_archive_reader.py`) — mutation-verified: keying `canonical_segments` on base alone fails it. The audit found **no test anywhere** that wrote a two-quote tree, so this class was entirely unexercised.
- **Converge order inverts to PRIMARY-FIRST** and is recorded in the runbook: secondary-first would make the reconciler see a pair the primary "lost" and heal whole hours into an append-only ledger (172,800 s against a 600 s/24 h alert), with the trades half carrying no alert rule at all. Primary-first short-circuits it for free. No canary bake is owed — this is a config change, not an image re-pin, so the currently-running digest is passed.

**The panel cannot serve the calibration yet, measured 2026-07-28.** A BTC-quoted panel hour holds 19 columns of which **six are null on all but one row across the whole subtree** (`SOL/BTC` has a single non-null `fill_bps_bid_100`; its paired `..._ask_100` is null, and the calibration averages the pair, so it still resolves to nothing) — every `fill_bps_*`, because the ladder walks `price × qty` in the pair's quote currency, so the "@100" rung on `ETH/BTC` asks 100 BTC (~10× its entire daily volume) and `_fill_bps` returns None on insufficient depth. The other 13 are genuine: `spread_bps` 1.01, `imbalance_l1` 0.63, the `depth_qty_*` ladder, and a BTC-denominated `mid`/`microprice`.

`captured-spread-calibration.md`'s query takes the mean of `(fill_bps_bid + fill_bps_ask)/2` — the one family that is null. So extending the calibration needs a **quote-aware ladder** (BTC notionals for BTC-quoted pairs), not just elapsed capture time. The BTC-quoted panel hours written before that change are recomputable from raw, which the NAS retains indefinitely, so nothing is lost by discarding them.

## Suggested next steps

_(none — this topic is resolved. The capture half landed 2026-07-23, the ladder / regeneration / calibration / re-key remainder 2026-08-08, and the docs rewrite with it. The cross-spread sanity bound this topic once proposed was superseded by real capture and is consciously dropped.)_
