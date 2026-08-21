# 00097 — the reconcile cycle stops scaling with window byte volume

Resolves [[T0147]]. **Nothing here changes what the reconciler decides, books, mints, or exports about any hour** — same ledger records, same residual seconds, same verdicts, same textfile families (plus one new gauge and one stamp-semantics fix). What changes is the cycle's cost model: from O(window rows) every 30 minutes, re-derived from scratch, to O(new data per tick) with a measured constant.

## Context — the cycle is 76 % of the way to overrunning its own tick

The ops overlay-writer cycle (`zcrypto-archive-pull`, `:12`/`:42` ticks) re-reads every hour's book parquet in its `--window-hours 48` window on both mirrors each cycle and re-derives every gap window from scratch. The ledger's dedupe (`seen` / `_decided`) suppresses re-*booking*, not re-*reading* or re-*deriving*. Measured 2026-08-21 (the T0147 investigation):

- Cycle duration is the daily segment-byte series pushed through a sliding 48 h sum: **315 s** floor on 2026-08-16 ~22:00 (the two ~20 MB/day weekend days in-window), **1,371 s** at the 2026-08-21 08:12Z cycle (the 92 and 129 MB/day vol-spike days in-window, BTC/EUR book bytes as the proxy). The tick is **1,800 s**. Sustained ~150 MB/day — 16 % above 2026-08-20 — overruns it.
- A systemd timer trigger that fires while the unit is still `activating` is dropped, not queued: the cadence silently halves, and nothing pages below `zcrypto-reconcile-exporter-stale`'s 3 h.
- **Where the time goes, profiled on real NAS data** (cProfile, 4-hour window, 103.9 s total, workstation): `PySeries.to_list()` 62.6 s (60 %), `fleet_dark_windows` pure-Python arithmetic 21.0 s, `_primary_silence`/`_message_ts`/31.7 M×`timedelta.total_seconds`/`sorted` ~12.5 s. Actual parquet decode: **2.2 s**. Directory scans: 0.7 s. ~97 % is Python-object timestamp arithmetic; I/O is 2 %.
- The waste is multiplied: per pair-hour, `find_book_gaps` and `find_unwitnessed_gaps` each call `_primary_silence(primary)` and `_message_ts(secondary)`, and `command.py` materializes the same `ts` columns again for the fleet-stamps timeline — the same frames reach Python lists up to five times.

Two independent fixes compose, and the owner ruled both land in this change: **vectorize** the arithmetic (removes ~97 % of the constant) and **skip settled hours** behind a fingerprint cache (removes the scaling). Telemetry lands first so both are measured, not assumed.

## Decisions

### D1 — cycle-duration telemetry, and the end-stamp fix

`reconcile()` captures a start stamp at entry. The exporter emits:

- `zcrypto_reconcile_cycle_duration_seconds` (gauge): wall-clock from cycle start to textfile export.
- `zcrypto_reconcile_last_success_timestamp_seconds` moves from its current near-*start* stamp to the **end-of-cycle** stamp. Measured defect: the 2026-08-21 08:12Z cycle stamped `08:12:16` and completed `08:35:06` — the stamp mis-states a long cycle's completion by its whole duration. End-stamping only ever makes the staleness alert read *fresher*, so it cannot false-fire; the 3 h threshold is unchanged.

HELP text for the new gauge carries no internal tokens (`operator-facing-text.md`; the enforcement test covers `# HELP` lines).

### D2 — one warning rule on the new gauge, pushed after its first live sample

`zcrypto-reconcile-cycle-duration`, **warning**, fires when the instant read of `zcrypto_reconcile_cycle_duration_seconds` is over 1,500 s (a strict `gt` evaluator, matching the file's house idiom; 83 % of the 1,800 s tick). `noDataState: OK` — metric absence is `zcrypto-reconcile-exporter-stale`'s page, and double-paging one failure is the [[T0135]] shape. Consequence at breach is degraded cadence, not loss, which is why warning and not critical. Lifecycle per `capture-deploys.md`: the rule is pushed **after** the first post-converge sample exists, and that first sample is read by **value** (a first cycle at cache-build cost is expected — see D6). A new `infra/runbooks/ops.md` section owns the uid.

### D3 — vectorize the gap arithmetic on int64 microseconds; the API and every artifact stay identical

All hot-path timestamp work moves to int64-microsecond arrays; `.to_list()` leaves the hot loop entirely:

- `_message_ts`: the monotonicity check runs inside polars on the raw column order (`diff() < 0` — same raw-before-dedup semantics, same refusal, same error text); order-preserving dedup stays `unique(maintain_order=True)`; the function returns an array/series, not a `list[datetime]`.
- `_primary_silence`: edges as one int64 array (`hour_start`, message stamps, `hour_end`); `diff` + strict-`>` threshold in integer μs; `Gap` objects constructed **only** for qualifying windows, with boundary-ownership flags derived from index position. The no-primary-message whole-hour Gap branch is unchanged.
- `find_book_gaps` / `find_unwitnessed_gaps`: same partition contract, computing `_primary_silence` **once** per pair-hour and filtering by witness — the up-to-five-fold re-materialization collapses to one.
- `fleet_dark_windows` / `containing_dark_window`: numpy concatenate → unique-sort → clamp to bounds → `diff` → threshold; `containing_dark_window` brackets via `searchsorted`. The H-1 straddle limitation and its comment stay verbatim — this change is forbidden from "fixing" it incidentally.
- `measure_residual` **is touched**: it consumes `_message_ts`'s output, so it converts at its own boundary (`dt_from_us` per mark) — bounded cost, it runs only on gap-carrying hours — with its inclusive-bounds selection and threshold semantics byte-identical. A null `ts` anywhere raises `CaptureError` loudly in the new `_message_ts` (develop refuses a null with a bare `TypeError`; the vectorized path must not silently clamp an `iNaT` away instead).
- Untouched: `Gap`/`DarkWindow` dataclasses (datetime fields), `_inside`, `secondary_covers`, the splice, minting, `classify_dark_episode` (runs only on dark hours; its `(ts, type)` list construction is bounded by that rarity), the ledger schema, every `_emit` family.

**Precision contract**: `ts` is microsecond resolution; an hour's span in μs (≤ 3.6×10⁹) is far below 2⁵³, so `total_seconds()`-float and integer-μs comparisons agree exactly, including at the strict-`>` threshold boundary. D6 proves this on real data rather than arguing it.

### D4 — the skip-cache: an hour is skipped only when re-examination provably cannot say anything new

New sidecar `<reconciled_root>/scan-cache.json`, written atomically (tmp + rename) each cycle. Per hour: `{fingerprint, examined_at, late_at_exam, failures, last_audited}` plus a top-level `algo` salt. `fingerprint` = sha256 over the sorted `(pair, kind, source, size, mtime_ns)` tuples of every final present for that hour **plus the sorted absence set** — the `(pair, kind, source)` triples whose final is missing. Mirror finals are immutable once pulled (written at hour close, hash-verified by the NAS pull), so size+mtime is a sound identity for them.

An hour is **skipped** iff every one of these holds; otherwise it is fully examined exactly as today:

1. A cache entry exists whose `algo` matches. The salt folds in an `ALGO_VERSION` constant (bumped with any examination-logic change; reviewer-enforced) **and** `min_gap_seconds` — a threshold change invalidates every entry.
2. The entry's `fingerprint` equals the current one — any new, changed, or newly-absent file re-examines.
3. `late_at_exam` is true — the recorded examination ran with the hour past `LATE_MINT_HOURS` (6 h), i.e. after the last decision that depends on wall-clock could still change. Hours younger than that are never cached.
4. `failures == 0` for that examination.
5. **No expected file is absent now** — an hour missing any final is re-examined every cycle, because `is_total_loss` bracketing depends on *neighboring* hours' availability, which no single-hour fingerprint can capture. (Not free — an incomplete hour still re-reads its *present* finals each cycle — but sound, and measured at zero such hours in the live window. A pair permanently removed from capture would make every window hour incomplete and silently disable the cache; the runbook names that signature — a stable absence set with `skipped=0` — in its triage list.)

**The cache exists only in `--mint` mode.** A `--detect-only` run neither loads, saves, nor audits it: ad-hoc workstation runs are pure observers, and without this a detect-only examination would write entries the deployed `--mint` cycle then honors — skipping hours whose re-examination *would mint*, violating this decision's own invariant.

Cache miss, corrupt cache, unreadable cache (including a JSON-valid non-object payload), wrong `algo`: the cycle runs **full**, then rebuilds the file — fail-open to *slow*, never to *wrong*. A non-ENOENT `stat` error during fingerprinting (NFS `ESTALE`/`EIO`) records the path as absent — the hour becomes incomplete and uncacheable, and the examination path reports the read error honestly. The first post-converge cycle is a full cycle by construction (no cache exists). **A manual mutation of the reconcile ledger or the overlay deletes `scan-cache.json` in the same act** — the next cycle is deliberately full instead of divergent-then-paged; the runbook and the ledger-correction procedure both say so.

### D5 — the sampled audit: the cache is distrusted a little, every cycle, forever

Every cycle, the **2 least-recently-audited** skippable hours are fully examined *despite* their valid cache entries (deterministic LRU rotation on `last_audited`; no randomness). If an audited hour's re-examination appends **any** ledger record or registers **any** failure, the divergence is logged at ERROR (which pages via the existing ops error-log alert, naming hour and fingerprint), and the **entire cache file is deleted** — the next cycle is full. One divergence means the fingerprint model is wrong somewhere, and a wrong model is not repaired entry-by-entry. This mirrors `verify-replay`'s sampled audit, which exists because that path's cache was once wrong in production. The audit's cost bounds the steady-state cycle: ~4 non-late hours + 2 audit hours examined per tick, everything else fingerprint-checked at `os.stat` cost.

### D6 — proof: golden equivalence on real mirrors, TDD on every guard, benchmark recorded

- **Golden equivalence** (the load-bearing proof): develop's code and this branch's code each replay the same real NAS mirrors from **fresh scratch ledgers** at `--window-hours 72` — a window still containing the real 2026-08-20 dark episode, so `both_streams_silent`, stream-window bookkeeping, and the 00096 classifier run on production data. **All runs pass `--mint` and `--textfile`** — detect-only would exercise neither the splice/mint/`measure_residual` path nor the exporter, exactly where the change's risk lives. Required: ledgers identical except `at` stamps; minted parquet trees identical; textfiles identical except the two timestamp series, `source_lag`, and the new gauge. Run twice for the branch: cold (no cache) and warm (second run against its own cache) — both must match develop's output. All runs start inside the same UTC hour and the diff first asserts the runs examined the same first/last hours — a mismatch there is window drift to re-run, never something to normalize away.
- **TDD unit tests**, each guard constructed and seen to trip plus a production-shaped true positive: vectorized functions against empty frames, a single stamp, a threshold-exact window (strict-`>` on both sides), boundary straddles, and the non-monotonic refusal with its exact error; cache skip honored on unchanged fingerprint; re-examination on size change, mtime change, new file, newly-absent file; a non-late hour never cached; a missing-file hour never skipped; `algo`/threshold change invalidates; audit divergence drops the cache and logs ERROR; corrupt cache file → full cycle; duration gauge emitted and positive; `last_success` stamps at end (later than a mid-cycle marker).
- **Benchmark** before/after on the same window, recorded in T0147's resolution with the profile numbers.

### D7 — rollout order, and what "resolved" requires

**The deployed image is built from `develop` (or `main`), never from a feature branch** — so the merge precedes the rollout, and the work ships as two PRs:

1. **The feature PR**: code, tests, alert YAML, runbook, spec + plan — reviewed at the Fable floor, merged into `develop` on the owner's word. It flips T0147 to `partial`, with the rollout + measured resolution registered in the topic as the remaining sub-item (never left in prose).
2. **Post-merge rollout, attended**: CI builds the develop image → digest pulled on the ops host → `fleet-pins.md` row updated on a fresh branch (converge evidence in that commit's message) → Kraken maintenance-feed check + open-topics/memo blocker sweep → ops converge (`--limit zcrypto-ops`, `-e liquidations_decision=roll-after`, `config.alloy` untouched so no alloy digest) → **the owed liquidations roll** (`docker compose up -d` in `/etc/zcrypto-ops` — the role repins but never restarts that compose; verify the running digest from the container, never the compose file) → **first cycle read by value** (expected: full cache-building cycle at roughly the vectorized-only cost, ~1/20 of 1,371 s) → **second cycle read by value** (expected: O(1) steady state, ~10–20 s) → `grafana-push.sh` the D2 rule → verify the rule sees the live sample. `ops-postverify.sh` after the converge as always.
3. **The closeout PR**: the pins update, T0147 resolved and archived carrying every measurement, and the iterations-history entry — one component: this topic's rollout and closeout.

T0147 is **not** resolved by the feature merge; it is resolved by the second cycle's measured duration and the alert live against it.

## Out of scope

- `classify_dark_episode` and every 00096 semantic — triage only, untouched.
- The splice, minting, `--window-hours`, `SETTLE_HOURS`, `LATE_MINT_HOURS`, and the H-1 straddle limitation.
- Capture-side code, the capture image, and both capture hosts — this converges the ops tier only.
- Any change to what the ledger books or when — enforced by D6's byte-equality, not by intent.
