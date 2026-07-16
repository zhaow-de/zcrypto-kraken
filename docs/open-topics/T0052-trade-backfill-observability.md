---
status: open
ripe_when: now — the metrics exist and reach Grafana, so the panels/alert are buildable immediately; the compose line is a one-liner any time infra/nas/compose.yaml is next touched
---

# Trade-backfill has metrics but no dashboard and no dead-man

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

## Suggested next steps

- **(autonomous)** Add a dead-man alert on `zcrypto_trade_backfill_last_success_timestamp` staleness (> ~2 days, since the step is daily), mirroring the gate/reconcile rules in `infra/grafana/alerts.yaml`; pin `notification_settings.receiver: metrics`.
- **(autonomous)** Add a panel to `infra/grafana/zcrypto-dashboard.json` showing last-success age and the exit code, beside the existing gate/reconcile panels.
- **(autonomous, cosmetic)** Add `TRADE_BACKFILL_TEXTFILE: /textfile/trade-backfill.prom` to `infra/nas/compose.yaml`'s `archive-pull` `environment:` block. The script's inline default already covers this, so it changes no behaviour — it keeps the contract visible beside `RECONCILE_TEXTFILE`/`GATE_TEXTFILE` rather than hidden in a shell default.
- **(verification, at the next NAS deploy)** Confirm the three series actually appear in Grafana after the compose recreate — and remember [[T0048]]: a recreated NAS container's logs stop shipping until Alloy is restarted, so restart Alloy after any compose change.
