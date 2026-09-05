# Reference-data runbooks — facts a third party owns

You are here because the daily pass's report listed a reminder as **OWED** under `## Reminders`, or a **scheduled reminder came due** in Slack. Nothing is wrong and nothing fired: these routines re-confirm facts nobody here controls, which move without emitting any signal we could alert on. Each section is written to be actioned without opening any other document.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="refdata-sweep-due"></a>

## refdata-sweep-due — SCHEDULED REMINDER

### What you are seeing

The daily pass's report (`ops-daily.py report`) names this reminder under `## Reminders` — `due in N days` or `OVERDUE by N days`, computed every day from the last row of the register's re-confirmation log plus the monthly cadence. A scheduled Slack message in `#zcrypto` may say the same. **The report is the trigger; the Slack message is a convenience ping** — its scheduling cannot be listed or verified from this side, so its absence means nothing and its presence adds nothing. It is not an alert — nothing is wrong. The facts it re-confirms are owned by a third party and move without emitting any signal we could alert on.

### What it means

The master plan marks fees, fee tiers, borrow-rollover rates, pair lists, MiCA status, tax rules and market-data pricing as **externally owned**. A stale one is silent: nothing breaks, nothing fires, and a decision quietly gets taken against last month's numbers. The sweep exists so that "re-confirmed, identical" is distinguishable from "never re-run" — the register's re-confirmation log is that distinction, one row per sweep.

Two facts about the sources decide how to read the result, and both were learned the hard way:

- **Kraken's public endpoint churns constantly and lags reality.** Sweep #1 saw 93 pairs removed and 13 added while all twelve candidates held — so `raw_sha256` changes almost every sweep for reasons touching nothing we depend on. It also still served the **pre-2026-07-09** fee schedule a month after that schedule was superseded.
- **The account's own fee tier needs the live account, but not a human** — authenticated `kraken volume` serves the tier, the 30-day spot and futures volumes and the AoP held value. What stays yours is the full ladder's shape and the AoP qualification ladder.

### What to do

Run `/zcrypto-refdata-sweep` — the skill carries the procedure and the exact code. In short:

1. **Automated half**: re-fetch, re-render, diff the rendered tables (never the hash), append a log row in `docs/reference/kraken-snapshot-register.md`. The stamp moves even on an unchanged sweep.
2. **Fee tier, automated**: `kraken volume --pair BTCUSD -o json` from the workstation — read-only, and never from a remote host (`fleet-deploys.md`). Its per-pair block comes back under the venue altname (`XXBTZUSD`), carrying the taker rate, the maker rate and the next tier; `inputs` carries the 30-day spot and futures volumes and the AoP held value. Unchanged → logged; changed → `docs/reference/kraken-fee-schedule.md` is corrected *and* the re-pricing named (`cli/costs/fees.py` encodes that ladder verbatim); the read unavailable → **Kraken Pro → Fee tab** is the fallback, and only a read that happened at neither is recorded as **not re-read**, never inherited from the previous row.
3. **Attended remainder**: the full ladder's shape if a row looks wrong, and the AoP qualification ladder — which held value grants which tier, the held value itself now arriving with step 2.
4. **Never cost anything off the register's fee columns.** `kraken-fee-schedule.md` owns the level; those columns are a drift detector on the endpoint. If they finally move, reconcile *back* to the fee doc rather than adopting the newer-looking API numbers.
5. **Re-arm the next reminder** — a scheduled Slack message fires once. Scheduling the following month's is part of closing this one out, or the routine silently stops after a single run. The report computes due-ness regardless — the message is a convenience, not what the check rests on.

Out of scope here: MiCA status, tax rules and market-data pricing have no endpoint and are human re-reads belonging to the pre-go/no-go sweep, which lives in `T0085`, not in this cadence.

### Retire when

`docs/reference/kraken-snapshot-register.md` is absent from the repo — the artifact this routine maintains. Until then the cadence outlives any individual reminder, which is why step 4 exists.
