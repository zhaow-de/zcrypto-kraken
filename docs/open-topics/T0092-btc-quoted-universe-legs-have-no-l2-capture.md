---
status: partial
ripe_when: the calibration remainder is ripe once the new legs have ≥2 weeks of captured book (≈2026-08-06, matching Phase 2's exit-bar span) — extend the spread calibration to them and re-key `SPREAD_CALIBRATION` from base to full symbol; the docs rewrite is closeout work for that same iteration. The capture half is DONE (2026-07-23)
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

## Suggested next steps

- **(The calibration remainder — this topic's own scope, ripe ≈2026-08-06)** Extend the spread calibration to the two new legs once they have ≥2 weeks of book, and re-key `SPREAD_CALIBRATION` from base to full symbol so `effective_spread_bps` stops resolving a BTC-quoted leg to the EUR leg's number. **Sequence matters:** `cli/data/rebuild.py:156`'s `quote == "EUR"` test currently *protects* — replacing it with a coverage test before the ladder is per-quote would feed a EUR notional into a BTC-denominated ladder, producing a large plausible bps figure that trips the 10 bps cap and drops a universe member as a fake liquidity rejection. Do the ladder first, the lookup second.
- **(Closeout of that same iteration)** Rewrite in place the docs that assert the pre-change world as justification: `docs/reference/data-catalog-full.md:101`, `captured-spread-calibration.md:7,55` (state the `/EUR/` scope as required, not incidental), and the **five** "the BTC legs have no L2 capture" sites — `cli/universe/rules.py:72`, `cli/universe/build.py:23-24`, `cli/data/rebuild.py:93`, `cli/data/rebuild.py:150`, `tests/test_universe_rules.py:160` (plus `tests/test_data_rebuild.py:203`, same clause in a docstring).
- **(Superseded)** The cross-spread sanity bound this topic originally proposed is no longer needed — real capture replaces the order-of-magnitude floor it would have given.
