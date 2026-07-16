---
status: open
ripe_when: the first time `zcrypto_trade_backfill_exit_code` is non-zero on consecutive days (needs T0052's alerting to be visible at all), or before an 11th capture pair is added
---

# A persistent trade-backfill error degrades the daily gate to hourly-forever

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

- Verified by harness at iter-100: rc=1 → stamp not written → retries next cycle (the documented intent, and correct for a transient).
- The step is best-effort: it can never abort the loop or poison the reconcile gate. So this degrades cost and politeness, never integrity.
- `trades_unrecoverable` and `duplicates_cross_hour` are *expected, honest* residuals by design (spec D10: a residual gap is a finding, not a failure) — but today they do not set a non-zero exit; only `errors` does. Worth re-checking that boundary when designing the fix, since "a permanent, expected residual" must not read as "an error to retry".

## Suggested next steps

- **(autonomous, design)** Decide the retry policy. Options: (a) stamp the day regardless of outcome and let [[T0052]]'s alert carry the failure — simplest, restores the daily cost bound, but a transient then waits 24h; (b) bounded retries per day (e.g. stamp after N consecutive failures); (c) distinguish transient (transport/5xx) from permanent (unknown pair, structural residual) and only retry the former. (c) is the most correct and the most code; (a) is one line and defensible given the metric is the real signal.
- **(autonomous, cheap, independent of the above)** Tie `KRAKEN_ALTNAME` to the capture universe so an 11th pair cannot silently trigger this — either derive it, or add an assert/test that the map covers every pair in `capture_pairs` and fails loudly at build time rather than nightly at runtime.
- Depends on [[T0052]] for visibility: until the metrics are alerted, this failure mode is invisible by construction.
