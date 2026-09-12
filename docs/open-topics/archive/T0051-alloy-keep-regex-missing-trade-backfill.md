---
status: resolved
---

# Alloy keep-regex missing the trade-backfill metric prefix

## Resolution

**Fixed in the same PR that introduced the metrics (spec `00053`, iter-100)** — the keep-regex in
`infra/nas/config.alloy` now carries `zcrypto_trade_backfill_.*`, so all three series reach Grafana.
Opened by the Task-6 implementer (correctly: a report-only note would have been invisible), but
parking it was the wrong disposition: a `keep`-action regex silently drops anything unlisted, so the
metrics would not merely have been undashboarded — they would not have existed, and the dead-man
built on them would have been decorative. CLAUDE.md Rule 4 makes observability part of done, not a
follow-up. Verified mechanically: every `zcrypto_*` name the entrypoint emits is matched by the
regex (checked by parsing both files, not by eye).

**The steps this topic carried at its close, kept verbatim with what answered each** — the titled scope itself stands in `infra/nas/config.alloy`, whose `write_relabel_config` keep list carries `zcrypto_trade_backfill_.*` today beside `zcrypto_gate_.*`, `zcrypto_reconcile_.*` and `zcrypto_archive_pull_.*`:

_(All that remained of THIS topic's titled scope — the keep-regex — is done; see Resolution above.
The two other sub-items originally listed here were **not** done at close, and an archived file is
never re-read, so they were split into their own topics rather than stranded here:_

- _the compose `TRADE_BACKFILL_TEXTFILE` line + the missing dashboard/alert/dead-man → [[T0052]];_ — **ANSWERED:** [[T0052]] is `status: resolved` with its own iter-100 Resolution — `zcrypto-trade-backfill-stale` and `zcrypto-trade-backfill-exit-nonzero` in `infra/grafana/alerts.yaml`, a dashboard row, and `TRADE_BACKFILL_TEXTFILE` made explicit beside `RECONCILE_TEXTFILE`/`GATE_TEXTFILE` rather than living only in a shell default. That was in `infra/nas/compose.yaml` at the time; spec `00054` has since moved the overlay writer to the ops node (`a67ddb616`), so the line no longer lives on the NAS at all.
- _the daily-gate degradation those metrics would have revealed → [[T0053]].)_ — **ANSWERED:** [[T0053]] is `status: resolved` the same day — the UTC day is stamped unconditionally *before* the command runs, so a failing run cannot re-arm the gate, and the metric carries the failure. That step too moved with spec `00054`: it is `infra/ansible/roles/ops/templates/archive-pull.sh.j2` now, not `infra/nas/pull-entrypoint.sh`. Its own residual (`KRAKEN_ALTNAME` versus `capture_pairs`) was split again to [[T0055]], also resolved, rather than left in it.

## Context — what

Spec `00053` Task 6 added a daily-gated `zcrypto archive backfill-trades` step to
`infra/nas/pull-entrypoint.sh`, emitting `zcrypto_trade_backfill_exit_code`,
`zcrypto_trade_backfill_last_run_timestamp`, and `zcrypto_trade_backfill_last_success_timestamp` to
a Prometheus textfile (`TRADE_BACKFILL_TEXTFILE`, defaults `/textfile/trade-backfill.prom`).
`infra/nas/config.alloy`'s `write_relabel_config` keep-regex (the line ending
`...|zcrypto_gate_.*|zcrypto_reconcile_.*`) does not list a `zcrypto_trade_backfill_.*` alternative,
so every series from the new textfile is silently dropped before remote_write — the exact caveat
already called out for `RECONCILE_TEXTFILE` in `infra/nas/README.md`'s env-var contract table.

Neither `infra/nas/compose.yaml` (no `TRADE_BACKFILL_TEXTFILE` entry — the script falls back to its
own inline default) nor `infra/nas/config.alloy` were in Task 6's scope (`docs/plans/00053-rest-trade-backfill.md`
lists only `pull-entrypoint.sh` + `README.md`), and no later task in that plan touches either file.

## Why this matters

Without the regex update, the new metrics reach the NAS textfile-collector directory but never
reach Grafana Cloud — no dashboard panel or alert rule can ever see them, and a stuck/failing daily
backfill (e.g. `zcrypto_trade_backfill_last_success_timestamp` going stale) would be invisible the
same way a dropped series always is: silently, with no scrape error to flag it.

## Findings so far

- `infra/nas/config.alloy` line ~66: `regex = "...|zcrypto_gate_.*|zcrypto_reconcile_.*"`, `action = "keep"`.
- `infra/nas/compose.yaml` sets `RECONCILE_TEXTFILE`/`GATE_TEXTFILE` explicitly but has no
  `TRADE_BACKFILL_TEXTFILE` entry; the script (`pull-entrypoint.sh`) uses an inline
  `${TRADE_BACKFILL_TEXTFILE:-/textfile/trade-backfill.prom}` default, matching the
  `ARCHIVE_PULL_INTERVAL`/`RECONCILE_WINDOW_HOURS` inline-default pattern already used there.
- `docs/plans/00053-rest-trade-backfill.md` Task 8 (Closeout) does not mention `config.alloy` or
  `compose.yaml` either — this is a genuine plan gap, not a deferred task.
