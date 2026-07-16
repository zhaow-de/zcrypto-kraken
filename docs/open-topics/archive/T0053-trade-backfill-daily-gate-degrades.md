---
status: resolved
---

# A persistent trade-backfill error degrades the daily gate to hourly-forever

## Resolution (2026-07-16, iter-100)

**Owner's decision: stamp the day unconditionally, and let the metric carry the failure.** Implemented in `infra/nas/pull-entrypoint.sh` — and slightly stronger than specified: the stamp is written *before* the command runs, so even a hard crash consumes the day. The O(archive) scan + REST burst can now never exceed one pass per UTC day, whatever happens. The cost bound D11 exists for is absolute rather than conditional on the pass succeeding.

The consequence is accepted, not overlooked: a transient now waits up to 24 h. That is fine — Kraken serves ~18 months of trade history, so nothing decays while waiting, and [[T0052]]'s two rules (staleness + non-zero exit) are what surface the failure. Rejected as more machinery than the problem warrants: transient-vs-permanent classification (a misclassification would silently re-create the hourly-forever bug) and bounded N-retries (an arbitrary knob that still burns N scans on a permanent error).

**The rate limit is fixed at source too:** `_MIN_INTERVAL_SECONDS` 1.5 → 3.0, with the measurement recorded in the constant's comment so it is not "optimised" back down. 1.5 s was *demonstrably* refused (`EGeneral:Too many requests`) on the live bulk run — one gap of 34 trades, isolated as designed and recovered by the idempotent re-run.

**Still open, deliberately, and now the only live sub-item — split to [[T0055]]:** `KRAKEN_ALTNAME` matches `capture_pairs` today but nothing ties them, so an 11th capture pair still fails every attempt for that pair. With this fix that no longer degrades the gate (the day is stamped regardless) — it degrades to "one pair silently never heals, and the exit-code alert fires daily", which is loud, not silent. That makes it a real but non-urgent defect rather than a cost bomb, so it does not hold this topic open.

## Context — what

The trade-backfill step (spec `00053`, iter-100) runs inside the NAS's **hourly** `archive-pull` loop but is gated to **one pass per UTC day** by a stamp file, and — deliberately — the stamp is written **only on success**, so a transient failure retries on the next cycle.

Found by the iter-100 final review (verified with a shell harness): that retry-on-failure has no backoff and no transient/permanent distinction. `zcrypto archive backfill-trades` exits 1 on **any** recorded error, so a **permanent** error means the stamp is never written and the full pass runs **every hour, forever**.

Each pass is an O(archive) `trade_id` scan across all pairs plus up to hundreds of REST calls at ~1.5 s spacing.

## Why this matters

It defeats the explicit reason the gate is daily. Spec `00053` D11: *"Daily, not hourly… the detector's scan is O(archive), a per-cycle cost [[T0028]] already flags on this host and which this must not compound"* — and there is no urgency, because Kraken serves ~18 months of trade history.

So the failure mode is quiet and self-inflicted: a single permanent error silently converts a deliberate daily job into an hourly one on the Atom, compounding exactly the cost [[T0028]] is about, and hammering a public endpoint on every cycle. Nothing pages today ([[T0052]] — the metrics have no alert), so it would run that way indefinitely, unnoticed.

Concrete permanent triggers that exist right now:

- A pair present in the archive but absent from `KRAKEN_ALTNAME` (`cli/trades/rest.py`) raises `TradeBackfillError` on every attempt. The map lists exactly the 10 pairs in `capture_pairs` (`infra/ansible/group_vars/capture_host/vars.yml`) **today**, but nothing ties the two together — **adding an 11th capture pair triggers this immediately and silently**.
- A residual the D9 invariant re-check keeps flagging (e.g. a gap Kraken genuinely will not serve, or a cross-hour duplicate that per-hour `union_trades` structurally cannot collapse) → `errors` non-empty → exit 1 → stamp never written, every hour, forever.

## Findings so far

- **MEASURED 2026-07-16 (iter-100 bulk run): Kraken rate-limits at the client's 1.5 s spacing.** The first live pass hit `EGeneral:Too many requests` on LINK/EUR gap `5419492..5419527` — one gap of 34 trades, isolated exactly as designed (the other 193 gaps healed; `errors=1`), and recovered in full by the idempotent re-run. So the `_MIN_INTERVAL_SECONDS = 1.5` constant is **too aggressive for a sustained burst** and the steady-state daily pass should not depend on a human noticing and re-running. This is now a concrete, observed trigger for the degradation below — not a hypothetical one.
- **The summary cannot fully account for a fetch-failed gap.** That run printed `missing=17362 recovered=17328 unrecoverable=0 deferred=0` — the 34 are implied only by `errors=1`. The internal `pair_fetch_error_missing` bucket exists (D9's re-check forced it, so the invariant check does not false-positive) but is not printed, so the operator's arithmetic does not close. Same defect class as the found-vs-healed split: a bucket that exists internally but never reaches the human.

- Verified by harness at iter-100: rc=1 → stamp not written → retries next cycle (the documented intent, and correct for a transient).
- The step is best-effort: it can never abort the loop or poison the reconcile gate. So this degrades cost and politeness, never integrity.
- `trades_unrecoverable` and `duplicates_cross_hour` are *expected, honest* residuals by design (spec D10: a residual gap is a finding, not a failure) — but today they do not set a non-zero exit; only `errors` does. Worth re-checking that boundary when designing the fix, since "a permanent, expected residual" must not read as "an error to retry".

## Suggested next steps

- **(autonomous, design)** Decide the retry policy. Options: (a) stamp the day regardless of outcome and let [[T0052]]'s alert carry the failure — simplest, restores the daily cost bound, but a transient then waits 24h; (b) bounded retries per day (e.g. stamp after N consecutive failures); (c) distinguish transient (transport/5xx) from permanent (unknown pair, structural residual) and only retry the former. (c) is the most correct and the most code; (a) is one line and defensible given the metric is the real signal.
- **(autonomous, cheap, independent of the above)** Tie `KRAKEN_ALTNAME` to the capture universe so an 11th pair cannot silently trigger this — either derive it, or add an assert/test that the map covers every pair in `capture_pairs` and fails loudly at build time rather than nightly at runtime.
- Depends on [[T0052]] for visibility: until the metrics are alerted, this failure mode is invisible by construction.
