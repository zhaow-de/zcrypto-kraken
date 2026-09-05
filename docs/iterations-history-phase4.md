# Iterations history — Phase 4 (Alpha Research Sprints)

Per-iteration changelog for Phase 4. Appended at each iteration's close-out; see `.claude/rules/prose.md`.

## 2026-07-08 — iter-036: longer-history basket robustness check (Phase-4 prep)

- **`docs/research/04.phase3-benchmark-b2-basket-report.md` carries a longer-history (4 majors, ~9 yr) robustness check** — read it before treating the 10-asset basket's loss as structural, because over that window it was largely a window artifact.
- **The basket premise stayed open, not settled** — the fixed 4-major proxy neither beats single-asset BTC risk-adjusted nor kills the idea, so the honest test was the full dynamic-composition basket (T0007, resolved at iter-044).
## 2026-07-08 — iter-037: BTC short-state check (Phase-4 prep / B4 handback)

- **`docs/research/04.phase3-benchmark-b0-b1-report.md` carries a short-state check on full-history BTC** — consult it before proposing a short overlay: even a well-built confirmed-bear short is a net drag over the sample, so long/flat gated-B1 dominates B4 as the fallback.
- **A short, if ever used, is confirmed-bear-only at reduced size** — the naive gate-flip short is far worse, and the sample holds no prolonged bear for the insurance the design buys to price.
## 2026-07-08 — iter-040: A1 causal feature primitives (Phase 4 kickoff)

- **`cli/features/` exists** (spec/plan `00029`) — the leak-free feature substrate the Phase-4 alpha families build on; a new feature copies its causal alignment (warm-up → `0.0`, `feature[k]` reads only prices at or before `k`).
- **Every feature carries a look-ahead test proven to fail on a deliberately-broken implementation** — the bar a new feature meets before any verdict is read on it.
## 2026-07-08 — iter-041: A1 feature substrate round 2 (Phase 4)

- **`cli/features/` completes A1's per-asset inputs** (spec `00030`) — trend agreement and drawdown state join momentum, channel position and realized vol on the same causal alignment; the BTC regime input stays the existing `sma_gate`.
- **Each new feature's look-ahead test was again confirmed to bite before merge** — the substrate's standing entry bar, not a one-off.
## 2026-07-09 — iter-044: full-history dynamic-composition basket + finding-1 verdict (Phase 4, T0007)

- **`dynamic_inverse_vol_basket` (`cli/benchmark/strategies.py`) is the full-history majors basket** — its composition grows with the majors list and the fixed `inverse_vol_basket` reduces to it exactly; use it, not the fixed-window basket, for any basket-base question.
- **`docs/research/04.phase3-benchmark-b2-dynamic-report.md` carries the finding-1 verdict: the dynamic basket ties single-asset BTC risk-adjusted** — the fixed-window "basket loses" was a window artifact, so a basket base is neither pre-selected nor pre-excluded and A1 carries both bases through its kill bar.
- **T0007 and T0004 resolved** (archived) — the dynamic B3/B4 follow-up this iteration noted was registered as T0010 and run at iter-055.
## 2026-07-09 — iter-045: A1 alpha book assembler + kill-bar harness (Phase 4, no verdict yet)

- **`cli/alpha/a1.py` assembles the A1 book** (spec/plan `00031`) — base × regime × short toggles over a per-asset directional trend book, inverse-vol weighted on the union calendar and vol-targeted; it reduces to gated-BTC on the `btc_only`/`single_gate`/`off` corner.
- **`cli/alpha/killbar.py` is the kill-bar harness** — its legs must all hold, and it is proven on planted-edge and null fixtures before its verdicts count.
- **The DSR leg compares a probability and `var_trials` is per-period** — the leg was inert as first coded and a units mismatch would have rejected every honest variant; honour both contracts at every call site (the threshold was later ratified at 0.95 in T0009).
- **`confirmed_bear` fires on the band plus negative trend agreement, never a bare below-SMA trigger**, and `btc_prices` is validated elementwise against the book's own BTC series.
## 2026-07-09 — iter-046: A1 kill-bar verdict — the first validated Bucket-A survivor (Phase 4)

- **`docs/research/06.phase4-a1-results.md` records A1's literal-kill-bar verdict** — read it with `07.phase4-a1-cost-reality.md` beside it, which corrects its deployment reading net-of-cost.
- **`docs/reference/trial-registry.jsonl` carries the A family's first records** — every family verdict is appended there with its metrics and spec/dataset hashes; the registry, not a report, is the trial budget's ledger.
- **`a1_book_returns` exposes per-asset net positions and the worst-slice leg skips zero-variance slices** — cost stress is charged on honest per-asset turnover, and a fully-gated-out year is neither qualifying nor disqualifying.
- **Deployment and the combination of survivors stay human-gated; the holdout was not touched.**
## 2026-07-09 — iter-047: A1 net-of-cost reality — an honest kill that corrects the iter-046 headline (Phase 4)

- **`docs/research/07.phase4-a1-cost-reality.md` carries A1's net-of-cost head-to-head** — A1's zero-fee edge does not survive the turnover the book requires once spot cost and the short's borrow carry (`cli/costs/margin_carry`) are charged.
- **A zero-fee SPA leg over-credits a high-turnover family against a cheap benchmark** — judge a cost-asymmetric family net-of-cost on both sides; the refinement was escalated and decided in T0009.
- **Registry records are append-only audits of the literal bar** — the band-sweep arms went in as `park` with a net-of-cost metric, and a corrected reading is a new report, never an edit to a record.
## 2026-07-09 — iter-048: cost-optimized A1 — turnover control does not rescue it (Phase 4)

- **`docs/research/07.phase4-a1-cost-reality.md` also carries the rebalance-cadence sweep** — no cadence rescues A1 with the short, and a cadence result is read offset-averaged, never off one arbitrary block-start phase.
- **The short's margin carry, not turnover or diversification, is what makes A1 uncompetitive net-of-cost** — it is a daily borrow holding cost, flat in cadence, which is why a long/flat variant became the next test.
## 2026-07-09 — iter-049: the A1 long/flat capstone — net-of-cost superior, but 2014-fragile (Phase 4)

- **`docs/research/07.phase4-a1-cost-reality.md` closes the A1 investigation with the long/flat capstone** — dropping the short recovers a significant net-of-cost edge, confirming that the borrow carry, not the strategy, was the killer.
- **A1-long/flat's worst-slice rejection was never benchmark-relative** — re-scoped at iter-053 because the leg is Sharpe-based and exposure-blind; read `docs/research/09.phase4-a2-results.md` before quoting that rejection.
- **The pay-the-carry-or-eat-the-tail tradeoff was escalated to the human and decided in T0009** — A1-lf weekly was admitted as a second sleeve; deployment stayed human-gated and the holdout untouched.
## 2026-07-09 — iter-050: harness — a net-of-cost head-to-head verdict helper (Phase 4)

- **`net_of_cost_verdict` (`cli/alpha/killbar.py`) is the net-of-cost head-to-head** — hand it two series each already charged its own realistic cost; `a1_kill_bar` is untouched, so folding it into the pre-registered bar stayed a human call (taken in T0009).
- **The gap it closes is regression-guarded in code** — a book that wins before cost and loses after returns `beats=False`, the exact failure that let A1 through the literal bar.
## 2026-07-09 — iter-051: A2 orientation note (Phase 4 forward-capture)

- **`docs/research/08.phase4-a2-orientation.md` binds the A1-arc lessons onto A2** — judge net-of-cost from the first verdict, budget turnover and the short's borrow carry, and beat the net-of-cost bar rather than the zero-fee one.
- **A2 is an A/B inside the A family, not a new family** — it shares the A trial budget under the same registry key, so a new key would silently un-cap it.
## 2026-07-09 — iter-052: A2 Donchian TSMOM ensemble book (Phase 4, no verdict yet)

- **`cli/alpha/a2.py` is the A2 Donchian TSMOM book** (spec/plan `00033`) — it returns `a1_book_returns`' shape so the cost model and both verdict tools plug in unchanged, and imports A1's union-calendar and weighting helpers rather than copying them.
- **A signal-layer leak test asserts invariance one index further than the book layer** — `signal[k]` reads only prices at or before `k`, so a one-step peek first corrupts the index a `[:k]` assertion cannot see.
- **"Donchian is structurally cheaper" holds only at a matched horizon** — the test says so by name, and A2's real drag against A1's production config had to be measured, not assumed.
- **A2's trials register under the A family key** — a new key would restart the counter and un-cap the shared A budget.
## 2026-07-09 — iter-053: A2 kill-bar verdict — no significant beat, and two instrument findings (Phase 4)

- **`docs/research/09.phase4-a2-results.md` records the daily A2 verdict** — no significant beat apples-to-apples; A2's cheapness premise is confirmed on real data and the short is cost-killed again.
- **The pre-registered worst-slice leg is absolute and exposure-blind — it disqualifies the benchmark itself**, so a whole-family failure on it carries no information; the leg was left untouched and its redesign escalated (decided in T0009).
- **Compare challenger and benchmark on the post-warm-up window** — a benchmark that structurally cannot trade its warm-up hands the challenger a free edge that moves the family SPA across the significance line.
- **A measurement finding forces a retroactive audit of every claim it touched** — reports `07`/`08` and the iter-049 entry were re-scoped in place rather than left standing, and the registry rows stand as literal-bar audits.
- **Follow-ups went to T0009 (protocol) and T0011 (A2 at its native band, the cadence sweep, the 2026 stub probe)** — both since resolved.
## 2026-07-09 — iter-054: benchmark-relative worst-slice diagnostic (Phase 4 harness, no trials spent)

- **`benchmark_relative_worst_slice` (`cli/alpha/killbar.py`) reports each slice's Sharpe, total return and drawdown for book and benchmark** — the exposure blindness the absolute leg cannot see; `a1_kill_bar` stayed byte-identical until the human folded it in (T0009).
- **A broken instrument suspends spending** — the reserved trials were held rather than burned against a bar known not to discriminate, and the contradiction is pinned by `test_benchmark_relative_worst_slice_exposure_blindness`.
## 2026-07-09 — iter-055: T0010 catch-up — dynamic B3/B4; the benchmark family raises its own bar (Phase 4)

- **`docs/research/04.phase3-benchmark-b2-dynamic-report.md` §B3/B4 carries the dynamic gate and short overlays** — the benchmark family raised its own bar with no alpha, and B4 confirms once more that the short's carry kills.
- **B3+vt-dynamic is the frozen benchmark, superseding gated-B1** (the human's call on review) — its exact construction and reference figures are in `docs/research/00.master-plan.md` §9, and every later kill-bar SPA leg compares against it.
- **A basis change re-runs the verdicts that rested on it** — the impacted reports and the entries above were re-read against the candidate bar in the same run, not left to the reader.
- **T0010 resolved** (archived) — a deferral whose trigger had fired and then died in prose, which is why a deferral now lives in an open-topic file rather than a report sentence.
## 2026-07-09 — iter-056: registry schema v3 — first-class variant field (T0013, pre-close drain)

- **Registry `schema_version = 3` adds an optional `variant`** — hash-covered like every field and omitted when `None`; the loader reads v2 and v3 in one file with the chain intact, and a v2 record carrying `variant` is corruption.
- **Budget accounting stays keyed on `family` alone** — a variant never opens a second budget, and the records that encoded one in `notes` are documented in `cli/registry/record.py` and deliberately not backfilled.
- **T0013 resolved; the loader's acceptance of unknown keys registered as T0015.**
## 2026-07-09 — iter-057: Phase-4 close-out (time-box called by the human)

- **`docs/research/10.phase4-closeout.md` is the Phase-4 exit-bar assessment** — closed on the human's time-box call with the queue not exhausted (Buckets B and C never started) and every worked family verdicted.
- **T0016 registers the un-started §5 queue remainder** as one umbrella topic with per-family `ripe_when:` prerequisites — the alternative, leaving it to master-plan prose, is the deferral-loss pattern.
- **A phase close runs a deferral sweep over its reports and history entries** — every hit maps to a registered topic or is dropped with the reason written.
- **`docs/research/10.phase4-decisions.md` is the Phase-4 decisions log** — drained verbatim from the running file at the phase boundary, which is what keeps the next phase's log clean.
- **The Phase-5 autonomous queue is written into the closeout report; the holdout look stays human-gated.**
______________________________________________________________________

**Continuation — Phase-4 backlog resumed during a later phase's era** (iters 74+, routed here by subject matter per the `iteration-closeout` skill).

______________________________________________________________________

## 2026-07-10 — iter-074: A2 at its native 4h band — three adopts, the first family-level beat (T0011)

- **A cross-band verdict rebuilds the frozen benchmark at the challenger's band first** — the 4h rebuild uses a time-preserving parameter mapping and was QA'd before any arm was read.
- **Three A2 native-4h arms adopted, one rejected** — the A family's first multiplicity-corrected beat of the frozen benchmark; the records are in `docs/reference/trial-registry.jsonl` and the arms in T0011.
- **`var_trials` must carry the same periodicity as the Sharpes it deflates** — the third occurrence of the caller-convention trap; mixing bands mechanically rejects everything, and `cli/alpha/killbar.py`'s units contract now spans periodicity too.
- **Adopt requires significance at both the convention and the time-matched block length, plus seed stability** — one block length is not a robust SPA read.
- **The survivors are candidate sleeves whose blocker was the cross-frequency construction design** — registered on T0011 and delivered at iter-080.
## 2026-07-10 — iter-075: the cadence sweep closes the A family at 40/40 (T0011 item 2)

- **The daily breakout-hold sweep closed the A family at its full trial budget** — all three cadence-held arms reject, and no A-family trial can be registered against the spent budget.
- **The ratified benchmark-relative worst-slice leg vetoes an arm holding the project's highest recorded net-of-cost Sharpe** — slow de-risking through choppy years is exactly what the guard exists to catch, and relitigating the protocol is an attended decision.
- **Engagement is verified before results are read** — the cadence demonstrably cut turnover, so the mechanism was real and its tail cost is what killed the arms.
## 2026-07-11 — iter-085: the 15m bar substrate for Bucket B (T0012 resolved)

- **`data/ohlc-15m/` exists** (spec/plan `00044`) — 12 pairs at 15 minutes derived from the 1-minute dumps by `cli/backfill/substrate15m.py`; a B1 trial references its manifest `basket_sha256`, recorded in `docs/reference/data-catalog-full.md` and T0022.
- **The substrate is instrument-proved on three legs** — tick reconciliation, gap/density QA, and the 15m→1h seam against canonical; the QA names the anomaly classes a consuming family must design around.
- **A failed exactness leg is adjudicated stronger, not loosened** — the volume seam's diffs proved to be one-ULP summation order, so the ratified predicate gained an order-immune bar-count equality leg.
- **T0012 resolved** (archived) — 15m Parquet derivation mirroring `ohlc-full`; the tick-level catalog was dropped for want of a consumer and re-opens under its own family topic.
## 2026-07-11 — iter-086: B1 family opened — conditioning overlay harness + trial 1 (honest REJECT)

- **`cli/alpha/b1.py` is the B1 conditioning overlay** (spec/plan `00045`) — the repo's first fold-internal estimator: expanding-annual windows cut at training completion time, thin cells left open, hold-through-unfavorable semantics.
- **T0022 carries the B1 family**, split from the T0016 umbrella when its prerequisites fired; trial 1 is a REJECT recorded in `docs/reference/trial-registry.jsonl`.
- **The trial's information is the mechanism, not the verdict** — the hypothesized turnover reduction inverted, which is why the untested window-only arm stayed a candidate.
- **A stamp belongs to the fold year of its bar-start, not its decision boundary** — the only leak-free reading; a future execution-scheduler consumer keys fold years the same way (`docs/research/10.phase4-decisions.md` `[iter-086]`).
## 2026-07-11 — iter-087: B1 trial 2 (window-only) — reject; both overlay mechanisms attributed

- **B1's second trial REJECTS and closes the conditioning-overlay class on the A2 book** — the window-only arm passes the kill bar purely by inheriting arm A's edge and never beats it head-to-head; recorded in the registry and T0022.
- **Hold-through defers trades rather than eliminating them** — catch-up trades on gate reopen cancel the held-stamp savings while adding drift risk, so a future B1 trial needs a genuinely new hypothesis.
## 2026-07-11 — iter-090: the B2 funding substrate (Binance Vision backfill)

- **`data/derivatives-funding/` exists** (spec/plan `00047`) — the USDT-M perps' realized funding history from checksum-verified Binance Vision monthly dumps via `cli/derivatives/funding.py`; its manifest hash and coverage are recorded in T0023.
- **Funding cadence is not uniform** — a venue's disclosed frequency change is preserved in the `interval_hours` column, and accrued-funding math must read it per row.
- **The Vision fetcher retries transient transport errors with bounded backoff** while 404 and other HTTP errors still propagate, so leading-404 listing detection is unaffected.
- **T0023 → `partial`** — funding delivered, open interest and liquidations still owed.
## 2026-09-03 — iter-091: the B2 feature harness (funding + OI), proven on known answers before any verdict

- **`cli/features/derivatives.py` exists** (spec/plan `00110`) — funding, OI and ratio features as pure functions on lists, re-exported from `cli/features/__init__.py`; they align to the input grid and return `len(input)` with `None` where undefined, unlike the price features, and the substrate is backtest-only because the venue publishes its dumps days late.
- **A windowed function's look-ahead guard is the truncating-prefix property plus full-list assertions** — the appended-future form and an `out[-1]`-only assertion each pass a real defect, and a `SURVIVED` mutation verdict is recorded as one and cross-checked rather than explained away.
- **A `0.0` is a venue hole in the OI levels and a real observation in the taker ratio** — levels map to `None` before validation, the ratio family validates finite-or-null, and the holes' provenance is stated as unestablished.
- **Every feature frame ships a per-year coverage summary** — the ratio columns' nulls concentrate in one bear year at rates an order of magnitude apart, so no single headline null rate describes the substrate.
- **A data-gated test gates on the configured canonical root, never `Path("data/…")`** — the per-checkout path is empty in a worktree and the skip would have been read as coverage; T0023 stays `partial` and carries the substrate→feature emission and the liquidations leg.
