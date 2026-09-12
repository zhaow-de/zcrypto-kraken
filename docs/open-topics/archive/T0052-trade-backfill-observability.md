---
status: resolved
---

# Trade-backfill has metrics but no dashboard and no dead-man

## Resolution (2026-07-16, iter-100)

**Two rules, because two different things break.** `infra/grafana/alerts.yaml` gains:

- `zcrypto-trade-backfill-stale` — `time() - zcrypto_trade_backfill_last_success_timestamp > 172800` (2 days, tolerating the daily cadence). This is the dead-man: the step stopped succeeding, or stopped running at all. `noDataState: Alerting` — a vanished series IS the failure here.
- `zcrypto-trade-backfill-exit-nonzero` — `zcrypto_trade_backfill_exit_code > 0`: the step ran and recorded errors. `noDataState: OK` deliberately — the dead-man above already owns "stopped running", and alerting on both would double-page one fault.

Both pin `notification_settings.receiver: metrics`. A dashboard row (last-success age + exit code) matches the Reconciler row's style, and `TRADE_BACKFILL_TEXTFILE` is now explicit in `infra/nas/compose.yaml` beside `RECONCILE_TEXTFILE`/`GATE_TEXTFILE` rather than living only in a shell default.

**The exit-code rule became load-bearing the moment [[T0053]] landed**: stamping the day unconditionally removes the retry, so the metric is the *only* signal a failed pass ever produces. That is why this topic was resolved first, in the same PR — an alert added "later" would have left a window where a failing backfill was silent by design.

**Not yet pushed to Grafana.** The rules are committed as-code; `infra/scripts/grafana-push.sh` sends them at the next deploy, and the series only exist after the NAS runs the step. Verify then — and remember [[T0048]]: restart Alloy after any NAS compose recreate, or the container's logs stop shipping.

**Where the four next steps landed.** The dead-man, the exit-code rule and the dashboard row are the two rules and the panel row above, delivered in `feat(config): alert + panel on the trade-backfill metrics (resolves T0052)` (`f2f3b3b4c`); the cosmetic `TRADE_BACKFILL_TEXTFILE` line went into `infra/nas/compose.yaml` in that same commit and left again with the NAS when spec `00054` D2 moved the whole step to the ops node (`a67ddb616`), whose `archive-pull.sh.j2` now writes all three series. The panels moved with the dashboard split and are rows 401-403 of `infra/grafana/data-integrity-dashboard.json` (exit code, last-success age, last-run age).

**The steps this topic carried at its close, kept verbatim with what answered each:**

- **(autonomous)** Add a dead-man alert on `zcrypto_trade_backfill_last_success_timestamp` staleness (> ~2 days, since the step is daily), mirroring the gate/reconcile rules in `infra/grafana/alerts.yaml`; pin `notification_settings.receiver: metrics`. — **ANSWERED:** `infra/grafana/alerts.yaml` carries `- uid: zcrypto-trade-backfill-stale` with `expr: time() - zcrypto_trade_backfill_last_success_timestamp` at 172800 s, `noDataState: Alerting` and `receiver: metrics`; landed in `f2f3b3b4c`, and read from the runbook at `infra/runbooks/ops-node.md`.
- **(autonomous)** Add a panel to `infra/grafana/zcrypto-dashboard.json` showing last-success age and the exit code, beside the existing gate/reconcile panels. — **ANSWERED:** same commit; the panels moved with the dashboard split and are now ids 401 "Job exit codes", 402 "Job last-success age" and 403 "Did it run at all? — last-run age" of `infra/grafana/data-integrity-dashboard.json`.
- **(autonomous, cosmetic)** Add `TRADE_BACKFILL_TEXTFILE: /textfile/trade-backfill.prom` to `infra/nas/compose.yaml`'s `archive-pull` `environment:` block. The script's inline default already covers this, so it changes no behaviour — it keeps the contract visible beside `RECONCILE_TEXTFILE`/`GATE_TEXTFILE` rather than hidden in a shell default. — **ANSWERED, then overtaken:** added in `f2f3b3b4c` and removed again with the step itself when spec `00054` D2 moved the overlay writer to the ops node (`a67ddb616`); the three series are now written by `infra/ansible/roles/ops/templates/archive-pull.sh.j2`.
- **(verification, at the next NAS deploy)** Confirm the three series actually appear in Grafana after the compose recreate — and remember [[T0048]]: a recreated NAS container's logs stop shipping until Alloy is restarted, so restart Alloy after any compose change. — **OVERTAKEN:** there is no NAS compose recreate left for this step to wait on, and the [[T0048]] Alloy-restart caveat went to ops with it (`a67ddb616`). What ops proves is the dead-man series alone, and by transition direction rather than by the page: in drill K (2026-08-31, `docs/reference/drill-log.md`) stopping the ops Alloy took `zcrypto-trade-backfill-stale` to `Alerting` at 08:00:50Z, 10 min 01 s after induction, and a `noDataState: Alerting` rule could only have been Normal beforehand if its series was present and below threshold — so `zcrypto_trade_backfill_last_success_timestamp` was live in Cloud. The other two series are **not** established by that reading: `zcrypto-trade-backfill-exit-nonzero` carries `noDataState: OK`, so its silence during the drill says nothing about `zcrypto_trade_backfill_exit_code`, and `zcrypto_trade_backfill_last_run_timestamp` is read by panel 403 and by no alert rule at all.

## Context — what

The daily trade-backfill step (spec `00053`, iter-100) emits three series from the NAS `archive-pull` loop:

- `zcrypto_trade_backfill_exit_code`
- `zcrypto_trade_backfill_last_run_timestamp`
- `zcrypto_trade_backfill_last_success_timestamp`

They **do** reach Grafana — `infra/nas/config.alloy`'s keep-regex carries `zcrypto_trade_backfill_.*` (that was [[T0051]], fixed in the same PR that introduced the metrics, and verified by parsing the emitted names against the regex). But nothing **watches** them: `grep -rn trade_backfill infra/grafana/` returns nothing. No panel, no alert, no dead-man.

Split out of [[T0051]] at its close (iter-100): T0051's titled scope was the keep-regex and that is genuinely resolved, but two `(autonomous)` sub-items were still live in its next-steps. Per `open-topics.md` an archived file is never re-read, so a deferral left inside one is lost — hence this topic.

## Why this matters

The step is **silent by construction until it is watched**. It runs once a day inside a loop whose other steps *are* alerted, so a reader glancing at the dashboard would reasonably infer the fleet is covered. It is not: if the backfill starts failing — or silently stops running because its stamp file gets stuck — nothing pages, and the trade stream quietly stops converging on the `trade_id`-contiguous invariant that spec `00053` D1 exists to guarantee.

There is a pointed irony worth preserving: [[T0051]]'s own resolution argued that an unwatched metric makes "the dead-man built on it decorative". Right now there is no dead-man at all — the metrics are the raw material for one, nothing more. This is the same shape as the shelved Binance recorder's paused check (a green light over a void feed) and [[T0032]]'s original silent-death: *the absence of an alarm is not the absence of a problem*.

## Findings so far

- Metrics are emitted atomically (tmp + `mv`) by `infra/nas/pull-entrypoint.sh`, gated to one pass per UTC day via a stamp file; the stamp is written **only on success**, so a failure retries next cycle.
- `last_success_timestamp` is written only on a clean exit, which makes it the natural dead-man quantity: staleness > ~2 days means the step has been failing or not running.
- `exit_code` distinguishes: 0 clean, 1 the sweep recorded errors (per-pair fetch/mint/read failures — all isolated, the sweep continues), 2 the primary root is missing.
- The neighbouring gate/reconcile alerts in `infra/grafana/alerts.yaml` are the model to copy; note the receiver split from 2026-07-16 — a metrics-sourced rule pins `receiver: metrics`.
