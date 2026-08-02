# 00081 — the two Stage-6b feeder measurements: gross attribution and the accumulation drift floor

**Goal:** answer [[T0117]] and [[T0118]] with measurements reproducible from committed code — (a) where the book's gross actually goes, stage by stage, so the ~5 % figure behind every placeability number is explained rather than observed; (b) the drift floor Kraken's minimums impose on an accumulation policy, as a function of NAV, so [[T0116]]'s amendment can re-register a tracking band that measures our execution instead of the venue's floors.

## Why both in one iteration

They read the same journal through the same replay, the harness is most of the code, and T0118's sensitivity check consumes T0117's answer directly (a 3× larger book shrinks the relative floor 3×). Owner's scoping call, 2026-08-02.

## Current state, measured (this iteration's probes, 2026-08-02)

**The journal is bigger than the topics say.** 136 cycle records across 23 day-dirs (2026-07-11 → 2026-08-02) on the NAS replica, not the 120/20-day window measured on 07-30. Every headline figure gets **re-measured**, never carried over.

**Replay is sound and cheap.** `replay_cycle` on the newest record reproduces the journaled targets exactly (`0.016488 == 0.016488`). Cost: **0.17 s read + 1.33 s build = 1.5 s/cycle**, so the full 136-cycle sweep is ~3.4 min single-threaded.

**T0117 needs no builder change, and its framing is a false binary.** `CrossfreqSystemResult` already exposes `multipliers` and `sleeve_positions={"B","A1","A2"}`, and `final_targets = multipliers[k] × capped[a][k]` — so every stage is derivable today. The probe on `cycle-12` of 2026-08-02: governor multiplier **0.5**, final gross **1.65 %**, implied pre-governor capped gross **3.30 %**. The governor is genuinely derating (T0117's second branch) **and** that only explains a factor of 2 — 3.3 % is still ~5× below the 15–20 % the naive vol-target arithmetic suggests. A third factor exists; naming it is in scope (owner's call).

**The chain's own constants**, read from the builder: three sleeves combined at fixed ⅓ each; `long_cap 0.20` / `short_cap 0.10`; A1 runs `target_vol=0.12`, the A2 arms carry per-arm targets — so the "10–12 % vol target" is real per sleeve, which is exactly why the combined 3.3 % needs explaining.

**`ordermin` is a base-asset quantity, not EUR** — 20 ADA, 3.9 DOT, 0.001 ETH, 0.00005 BTC, 50 DOGE (`data/snapshots/kraken-refdata-20260707T032900Z.json`, `fetched_at 2026-07-07`). The EUR floor is therefore **time-varying** and must be priced per cycle from the journaled closes, never from a fixed table. `costmin` is €0.45 across the EUR book.

**The minimums come from the snapshot's `universe` block, NOT from `raw.assetpairs`, and the quote MUST be filtered.** Two traps measured here, both of which produce a silently wrong floor rather than an error: (1) **there is no `DOGE/EUR` wsname** in `assetpairs` — Kraken lists it as `XDG/EUR`, so a `<ASSET>/EUR` wsname match fails on DOGE (and needs `XBT/EUR` for BTC); (2) the `universe` block is already normalised to `base`/`quote`/`ordermin`/`costmin` and is the right source — but it also carries **`ETH/BTC` and `SOL/BTC` with `costmin 0.00002`**, BTC-denominated, so keying by `base` without `quote == "EUR"` overwrites ETH's and SOL's EUR floors with a number four orders of magnitude off, read as euros.

## Decisions

**D1 — No builder change; the harness recomputes the middle stages and PROVES the recomputation, against BOTH the in-process build and the journal.** `combined` and `capped` are builder-internal, but `combined = ⅓B + ⅓A1 + ⅓A2` from `sleeve_positions` and `capped = apply_position_caps(combined, …)` reproduce them from public parts — exactly, because `sleeve_positions` stores the already-4h-expanded series and `apply_position_caps` is a pure per-element clip with no cross-asset or prior-row dependence, so the harness reruns the builder's own arithmetic on the builder's own floats in the same order. **Two checks, both per cycle, because they catch different failures:**

- **The internal identity** — `multiplier × capped_recomputed[a] == final_targets[a]` exactly, for every asset. Catches the builder's combination or cap changing under the harness.
- **The journal identity** — the rebuilt forming-row targets equal the **journaled** `record.final_targets` exactly, for the same asset set. Catches what the internal one structurally cannot: a rebuild that is self-consistent but diverges from what the engine actually traded (wrong row, config drift, environment drift). Without it both reports could describe a book that never existed, agreeing with themselves the whole way. `validate_record(record)` runs first, restoring the no-peek and calendar-alignment discipline `replay_cycle` already enforces.

**D2 — The attribution chain is the deliverable, reported per cycle at the forming row.** Five stages plus their ratios: per-sleeve gross (`Σ|B|`, `Σ|A1|`, `Σ|A2|`) → `combined_gross` → `capped_gross` → `final_gross`, alongside `multiplier`, `n_active` (non-zero positions) and whether the caps bound at that row. Ratios between consecutive stages are what answer "where does 15–20 % die".

**D3 — The cancellation term is first-class, because it is the likeliest answer and is invisible otherwise.** `combined_gross` is **not** the mean of the three sleeve grosses: ⅓-weighting nets opposing sleeve positions away asset by asset. Report `combined_gross / mean(sleeve_gross)` explicitly as the **cancellation ratio** — a value near 1 means the sleeves agree and the combination is not where gross is lost; well below 1 means disagreement is the mechanism. Without this the report shows a drop with no named cause and invites the reader to blame the caps.

**D4 — The accumulation replay carries held positions in BASE UNITS, not EUR, and is policy-only.** Holding EUR amounts would need a separate mark-to-market step and would compare a price-stale "held" against a fresh "target" — quantities avoid that entirely, and `ordermin` is natively a quantity, so the floor comparison is direct rather than converted. Per cycle, chronologically:

- `target_qty[a] = (final_targets[a] × NAV) / close[a]` — the journaled forming-row weight, priced at that cycle's journaled close.
- `delta_qty[a] = target_qty[a] − held_qty[a]`.
- Place iff **both** `|delta_qty[a]| ≥ ordermin_base[a]` **and** `|delta_qty[a]| × close[a] ≥ costmin` — the two floors are independent gates, not a max over mixed units.
- On placement `held_qty[a] = target_qty[a]` (full fill at the journaled close); otherwise `held_qty[a]` is unchanged and the unplaced delta persists into the next cycle, which is the accumulation.
- Drift is measured **after** the decision, in EUR at that close: `drift[a] = |target_qty[a] − held_qty[a]| × close[a]`; book drift `Σ_a drift[a]`, reported as a fraction of NAV.

NAV is held constant across the window on purpose: this measures the *placement* floor, not P&L, and a drifting NAV would fold return into a number that must be pure venue-minimum. Mark-to-market falls out for free — a held quantity is simply worth `held_qty × close` at any later cycle. No slippage, no fees, no partial fills: those are the cost model's job, and modelling them here would make the floor read as a cost estimate, which it is not.

**D5 — Sweep NAV rather than baking an FX guess.** §12's ramp is quoted in dollars ("25/50/100 % of the $10k") while the book, the minimums and the sleeve are EUR. Rather than pick a EUR/USD rate that would silently date the answer, report the drift floor as a **function of NAV** over €500 / €1,000 / €2,500 / €5,000 / €10,000, so any funded amount reads off the curve. The €1,000 rung-3 figure is one row of it.

**D6 — The band is reported the way the gate reads it, and the window's thinness is shown rather than smoothed.** The pre-registered band is weekly `|live − sim| ≤ 10 bps of NAV`, so the output aggregates per ISO week in bps of NAV. But the journal spans **exactly 4 ISO weeks — (2026,28) 12 cycles, then 42/42/40** (measured) — and the first is a 2-day partial whose mean is not comparable to a full week's. A "p95 across weeks" over 4 points is the maximum wearing a percentile's name, so: **print all four weekly values with their cycle counts, flag the partial week, and report no weekly p95.** Per-cycle median and p95 over the full 136 points are statistically meaningful and are reported alongside. The band is written from what the four weeks actually show, not from a percentile the sample cannot support.

**D7 — Two `zcrypto engine` subcommands over one module**, matching `soak-check`'s existing shape: `cli/engine/feeders.py` holding `decompose_report` + `accumulation_report`, exposed as `zcrypto engine decompose` and `zcrypto engine accum-replay`, both `--journal-dir`-driven and read-only. README Usage updated in the same change (`readme-usage.md`).

**D8 — The 2026-07-07 minimums stamp is surfaced in the output.** The `fetched_at` date is printed beside the drift table, because [[T0113]]'s sweep will move these numbers and a band quoted at the gate from a stale table is exactly the silent-staleness failure T0113 exists to prevent. The measurement is not blocked on the refresh; it is labelled.

## Non-goals

- No builder change, and no change to any live path — both commands are read-only over a pulled journal replica.
- No executor code: the accumulation policy is **simulated** here; implementing it is [[T0119]]'s work inside [[T0018]]'s iteration.
- No fills/slippage/fee modelling (D4), and no re-derivation of the cost model.
- No amendment text — feeding [[T0116]] is a closeout hand-off, not this spec's output.

## Verification

Each guard proven by constructing its defect; the previous iterations' reviews found ~19 guards that could not fail, so an assertion's existence is not evidence.

- **Both D1 identities are load-bearing and both are proven by construction, not by reading them.** The internal one: perturb the recomputed `combined` (weight ½ instead of ⅓) and it must fail on the first cycle — run the mutation, see it fail, restore (clearing `__pycache__` or setting `PYTHONDONTWRITEBYTECODE=1`, since `1/3`→`1/2` is a same-length edit and the stale-`.pyc` cache key is mtime-seconds + size). The journal one: it is exercised by every one of the 136 records; a record that fails is **reported and counted, never skipped** — a silently-dropped cycle would bias every aggregate.
- **The identity comparison is a pure helper** (`_check_stage_identity`), unit-tested without a builder-reaching stub, so the guard keeps a committed regression test after the branch-time mutation proof is gone.
- **Attribution arithmetic**: on a hand-built fixture with known sleeve positions, the five stages and both ratios equal values computed by hand; a fixture where all three sleeves are identical must give cancellation ratio exactly 1.0, and one where two sleeves oppose must give < 1.
- **The accumulation policy's own edges, each a test**: a delta below `ordermin_base` is not placed and the gap persists to the next cycle; a gap that grows across cycles places on the cycle it crosses the floor; `costmin` binds independently of `ordermin` (a delta clearing the quantity floor but worth < €0.45 is refused, and the converse); drift is measured post-decision (a cycle that places must show drift exactly 0 for that asset, not the pre-placement value).
- **Held state is quantities, and mark-to-market is implicit** (D4): with `held_qty` **fixed and NONZERO** and the close moving between two cycles, the reported drift must move because `target_qty` re-priced. The nonzero part is the whole test — at `held_qty = 0` the drift is `target_qty × close = weight × NAV` and the close **cancels**, so a zero-held fixture is byte-identical under the EUR-denominated design and discriminates nothing. The fixture must let cycle 1 place, then move the close by less than the floor so cycle 2 places nothing and drift is pure re-pricing.
- **The true accumulation invariant, pinned instead of a false one**: every unplaced asset-cycle satisfies `drift_eur_a < max(ordermin_a × close_a, costmin)`. NAV-monotonicity is **not** an invariant and must not be asserted as one — held histories diverge across NAV rungs, so a lower NAV sitting at drift 0 just after placing can beat a higher one carrying a fresh sub-floor residual. Report relative drift across the D5 sweep as an expected observation to eyeball, and investigate an inversion rather than treating it as a proven defect.
- **The aggregate ratio basis is pinned by a two-cycle asymmetric fixture.** Every consecutive-stage ratio is reported as the **median of per-cycle ratios**, never a ratio of medians; with the multiplier varying across the window the two differ materially in T0117's headline number, and a single-cycle fixture cannot tell them apart because they coincide there.
- Full suite green; `uv run pre-commit run -a` clean; both commands' `--help` free of internal tokens (`tests/test_internal_terms_not_operator_visible.py`).

## Risks

- **The measurement may not close T0117's question.** If the cancellation ratio, the caps and the governor together still leave 3.3 % unexplained against 15–20 %, the residual is the naive expectation itself being wrong arithmetic (a per-sleeve vol target is not a book gross target). That is an acceptable and honest outcome — the report names the residual rather than forcing it to zero.
- The drift floor is derived from **shadow** targets, which are what the live book would have traded; if rung 1/2 execution changes the target series materially, the band wants re-deriving. Stated in the output.
- The minimums are a 2026-07-07 snapshot (D8); the figure is correct as of that table and moves with it.
