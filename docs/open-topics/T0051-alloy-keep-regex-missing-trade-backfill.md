---
status: open
ripe_when: the next NAS Alloy config change, or before the trade-backfill dashboard/alerting is built
---

# Alloy keep-regex missing the trade-backfill metric prefix

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

## Suggested next steps

- **(autonomous)** Add a `zcrypto_trade_backfill_.*` alternative to the keep-regex in
  `infra/nas/config.alloy` (one-line change, same file/line as the existing `zcrypto_reconcile_.*`
  entry).
- **(autonomous)** Add a `TRADE_BACKFILL_TEXTFILE: /textfile/trade-backfill.prom` line to
  `infra/nas/compose.yaml`'s `archive-pull` service `environment:` block, matching
  `RECONCILE_TEXTFILE`/`GATE_TEXTFILE`'s fixed-path pattern (currently the script's inline default
  covers this, but an explicit compose entry keeps the contract visible the way the neighboring
  vars are).
- **(autonomous)** Once wired, add trade-backfill panels/alerts to
  `infra/grafana/zcrypto-dashboard.json` / `infra/grafana/alerts.yaml` (e.g. a dead-man on
  `zcrypto_trade_backfill_last_success_timestamp` staleness, mirroring the gate/reconcile alerts) —
  this is genuinely new scope, not just re-plumbing existing metrics.
