---
status: partial
ripe_when: the reconcile ledger needs another correction or rebuild — that sub-item is STILL LIVE and is now the only thing holding this topic open. The O(ledger)-scan-slowdown leg is RELIEVED (spec 00054 moved the scan off the Atom onto the ops node's i7, 2026-07-16), so the Atom cycle time is no longer the thing to watch
---

# Correcting the reconcile ledger resets the Prometheus counters

## Context — what

`zcrypto_reconcile_residual_gap_seconds_total`, `_healable_gap_seconds_total`, `_spliced_hours_total`, `_union_hours_total`, and the deficit counters are all derived by **summing the whole append-only ledger** (`_totals` in `cli/archive/command.py`) on every cycle. That makes them monotone by construction — as long as the ledger only ever grows. The one operation that breaks the invariant is a **ledger correction**: on 2026-07-14 a false `total_loss` record (a classifier bug, see the T0043 fix) was purged with the owner's approval, dropping `residual_gap_seconds_total` from 6261.8 to 2661.8 s. Prometheus reads any counter decrease as a **reset**, and a bare `increase()` over a window spanning it reports the whole post-reset value as fresh change.

## Why this matters

Two `increase()`-based alert rules read these counters: `Reconciler · residual gap increased` (the permanent-loss page, 1 h window) and `Reconciler · primary gap rate high` (the degrading-host page, 24 h window). Un-guarded, a ledger correction would false-fire **both** — the residual one is the highest-severity alert in the system, so a routine correction would page "permanent L2 loss" on an artifact. That is precisely the "distrust the instrument" failure the project's own rules warn against, and a false page on the most serious alert is how an operator learns to ignore it.

## Findings so far

- **(spec `00054` / OPS-5, 2026-07-16 — the growth leg is RELIEVED; this topic does NOT close.)** The reconciler and the trade-backfill moved off the NAS's 4-core no-AVX Atom onto the ops node's 24-thread i7, so the O(ledger) scan this topic's trigger watched no longer has the Atom tax on it. **Relieving pressure is not fixing the defect.** The correction-marker sub-item is independent of which host runs the code: a ledger correction still resets the Prometheus counters, because `_totals()` derives them from the whole ledger and `Reconciler · residual gap increased` reads that via `increase()`/`resets()`. That sub-item is live and is now the only thing holding this open — closing here would repeat the [[T0051]] mistake of archiving a topic that still carried live work.
- **Measured across the cutover (a live risk that did NOT fire):** `zcrypto_reconcile_residual_gap_seconds_total` held at **2662** while the writer moved hosts and the series changed publisher. The feared false permanent-loss page did not occur — a brand-new series has no prior samples for `increase()` to jump from.
- **The runbook's backup was its own topic — see [[T0057]] — and is FIXED.** The `b22d3e2`-era runbook wrote `reconcile-ledger.jsonl.bak-20260714-220209` *in place*, inside the replicated overlay, where it broke the new ops→NAS channel on a permission mismatch (2026-07-16). Commit `18ec391` rewired the runbook: backups now land in `/var/lib/zcrypto-ops/ledger-corrections` **outside** the replicated tree (see `infra/nas/README.md`'s backup rules), and the in-custody `.bak` was evidence-committed as `infra/nas/ledger-correction-20260714-link-eur.md` — the durable record of what the LINK/EUR `total_loss` correction removed — then deleted from both trees 2026-07-17 (sha-verified first).

- **Already mitigated in the rules** (commit for spec 00050 task 11): both rules now gate on `... and resets(<counter>[<window>]) == 0`, so a correction (which shows up as a reset) is silenced for one window while a genuine, monotone loss still fires. The residual comment in `infra/grafana/alerts.yaml` documents the exact tradeoff: a real loss in the *same* window as a correction is delayed until the reset ages out — rare, bounded, and visible on the dashboard panel regardless.
- The correction itself was done by hand (a one-off Python filter that dropped exactly the matching record, asserted `len(dropped) == 1`, preserved valid JSONL, and backed the original up verbatim as `reconcile-ledger.jsonl.bak-<ts>`). There is no committed procedure for it — it was reconstructed from first principles under time pressure.
- Related property of the same append-only-forever design: `_load_ledger` + `_totals` scan the entire ledger every cycle, so both are O(ledger size). There is no rotation or pruning (unlike the 14-day raw-mirror retention). Over the deployment's life this slowly erodes the reconcile cycle's headroom against the `source-lag` / `exporter-stale` thresholds.

## Done so far

- The two `increase()`-based alert rules are guarded with `resets(...) == 0`, so a ledger correction (which shows as a counter reset) cannot false-page (landed with the Task-11 alert commit; proven live — with the 2026-07-14 correction's reset still in-window, the guarded query read 0 while the bare `increase()` read 2706.9).
- **The correction runbook is written** (`infra/nas/README.md` → "Correcting the reconcile ledger"): back up verbatim; filter by an exact-match predicate with a `len(dropped) == N` assertion; keep one-record-per-line JSONL; expect the two rules to go quiet for one window (the guard working).

## Suggested next steps

- Decide whether a ledger correction should also emit a marker (a `state="correction"` record, or a bump to a dedicated `zcrypto_reconcile_ledger_corrections_total` counter) so the reset has a visible, queryable cause on the timeline rather than being an unexplained discontinuity six months later.

  **Anchor — where it goes if the decision is to emit** (surveyed 2026-08-04 for spec `00084`, so the decision does not have to re-derive it):

  - **Emit site:** `cli/archive/command.py`, `_write_textfile()` — its local `_emit(name, kind, help_, samples)` helper writes every `zcrypto_reconcile_*` family, and a new counter is one more `_emit(...)` call beside `trade_dedup_rows_total`. The value comes from `_totals()`, which already scans the whole ledger, so a `state="correction"` record is counted in the same pass that computes every other total — no second read.
  - **Keep-list: nothing to change.** The ops Alloy keep-regex admits `zcrypto_reconcile_.*` as a wildcard, so a new family under that prefix ships the moment it is emitted. This is the rare case where the T0051 trap does not bite in the published-but-unadmitted direction — it still bites in the other, so no panel may be wired before the family exists.
  - **Dashboard side:** the `Data integrity` board's reconcile row carries "Gap totals — cumulative since ledger genesis" (all-green, no thresholds, described as "a number here is history, not an incident"). The marker belongs **on that panel** as a second series, or as a Grafana annotation query over it — that is the panel whose discontinuities it exists to explain. Spec `00084` deliberately did not wire it, because a panel over a family nothing emits renders empty and reads exactly like a quiet metric.
  - **Why this got sharper, not softer:** `00084` gives the residual and healable panels the alert rule's own `resets(...[24h]) == 0` guard, so after a correction those panels correctly read **zero** instead of a false spike. Correct — and it also makes a correction *invisible* on the board, which is precisely the "unexplained discontinuity six months later" this sub-item was opened about. The marker is now the only thing that would make one legible.
- When the ledger grows large enough to matter (watch the cycle time), design rotation/compaction that preserves the summed totals — e.g. fold everything older than the retention horizon into a single opening `carried_forward` record so `_totals` stays exact while the scanned file stays bounded. Do NOT simply truncate: that would reset every counter.
