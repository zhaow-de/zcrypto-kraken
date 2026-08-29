# Engine runbooks — the trading engine and its order path

You are here because **an alert fired in Slack**, because **a guard in the code pointed you here**, or because you are running the attended probe-window procedure at the end of this file. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-engine-sleeve-count-changed"></a>

## zcrypto-engine-sleeve-count-changed — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · sleeve composition changed`): the number of the shadow engine's sleeves carrying non-zero exposure stepped up or down within the last 26 hours. Nothing is broken. This alert announces a change in **what the book is**, not a fault.

### What it means

The engine's book is three sleeves — `B`, `A1`, `A2` — combined at fixed one-third weights, and the combination is deliberately fixed: the weights do not react to which sleeves are currently earning. A sleeve that is sitting flat contributes zero and costs nothing to carry; it re-arms on its own signal, with no deploy and no config change.

For a long stretch only `A2` has carried exposure, so the live book has been structurally a **one-sleeve book at roughly a sixth of that sleeve's own gross** — one third from the fixed weights, halved again by the exposure governor. Two consequences follow, and both are why this alert exists rather than a dashboard panel:

- **The composition changing does NOT tell you the gross changed — measure it, do not scale it.** This bullet used to say gross moves roughly in proportion to the count (a third sleeve arming being "close to a tripling"); the 2026-08-22 transition falsified that. Each sleeve's gross is its own and they move independently: the count went 1 → 3 while book gross rose only ×1.15, and within fifteen hours it had fallen *below* where it started, because A2's own gross dropped as B and A1 armed. What does hold is the obligation: everything sized against the previous composition — the drift band, the expected order notionals — was derived under a state that no longer holds, and the direction and size of the change are whatever the series says they are. Read them.
- **Order placeability moves with it — measure it per leg, and measure it against `ordermin`.** The intended orders sit under the venue's minimums, which is why so few would clear at small live size. Two corrections from the 2026-08-22 transition, both measured from the engine's own `orders.jsonl`: the binding floor is **`ordermin`** (a base-unit quantity floor, e.g. BTC 5e-05, DOGE 50) and **not** `costmin` (a flat €0.45 on every EUR leg) — at the step nine of ten legs cleared costmin and none cleared ordermin; and a composition change need not spread exposure over more instruments at all — the same ten legs carried weight before and after, so the step made orders *larger*, not smaller. Read the actual intended orders, not the count.

The alert reads `changes(zcrypto_engine_active_sleeves[26h])`, so it fires on a step in **either** direction: a dormant sleeve arming, or an active one going flat. The window is wider than a day, so the page persists long enough to be seen and then ages out on its own.

Two things this alert deliberately does **not** do. It does not fire when the engine goes dark — the series simply stops, and `noDataState` is `OK`, because engine liveness is the healthchecks.io dead-man's job and the cycle-completed staleness rule's, not this one's. And it does not fire on a failed cycle: a cycle that never reached the build reports no composition at all, so both gauges hold their previous values rather than reading as "everything went flat".

### What to do

1. **Identify which sleeve moved, and in which direction.** `uv run python infra/scripts/grafana-query.py 'zcrypto_engine_sleeve_gross'` — one value per `sleeve` label. Compare against `zcrypto_engine_active_sleeves` over the last few days to see when the step landed. A single 4h cycle's blip and a sustained re-arming are different events; do not act on one cycle.

2. **Do not restart, converge, or "fix" anything.** The engine is behaving exactly as designed — the sleeve's own signal turned on or off. There is no failure here to recover from, and a restart changes nothing about the composition.

3. **Re-derive the numbers that were sized against the old composition** before the next go-live decision reads them: the model-consistency band the gate compares realized performance against, and the expected order notionals versus the venue minimums. Both were derived under the previous sleeve count and neither updates itself. The command is `uv run zcrypto engine accum-replay --journal-dir <journal> --since <YYYY-MM-DD> --until <YYYY-MM-DD> --nav 1000 --minimums <newest kraken-refdata-*.json>`, and three things decide whether its answer is usable:

   - **Run it over a window that starts well before the composition changed, and slice**, or run it standalone and know what you are getting: the replay initialises held quantity to zero at its FIRST cycle, so a window starting in a low-gross stretch carries an additive offset that never decays. A live book is never flat.
   - **A band the gate can rest on needs ≥3 COMPLETE ISO weeks in the new composition** — that is the basis the gate's edge is defined on. Anything shorter is the current combined floor, useful for reading today and not for ratifying.
   - **Re-check the minimums stamp in the same pass** and quote which snapshot you used; Kraken moves those without notice.

   **That command is the FLOOR half only — read the realized half beside it, or you have re-derived one side of a comparison.** `accum-replay` measures what the venue's minimums make unavoidable; what the engine actually held is `uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <YYYY-MM-DD> --until <YYYY-MM-DD>`, which prints both halves per complete ISO week at one NAV. The two cannot drift apart by construction — both compute the same drift function, and it is the same one the engine's own weekly trip evaluates. Until the engine has journaled fills the realized column reads *no data*, and that is the honest answer for a series that has not started, never a zero to average in.

4. **Record the transition durably** — date, which sleeve, the gross before and after — as a new row in `docs/reference/sleeve-composition-ledger.md`, which exists for exactly this and carries the read recipe. This alert ages out within a day and is not a record. The book's composition history is what a later gate reading depends on, and the last such transition went unrecorded for months precisely because nothing announced it.

5. **If the count went DOWN to one or zero**, treat it as information, not an emergency: a long-only sleeve going flat in a downtrend is the risk control working. Zero active sleeves means a flat book — no exposure, no turnover — which is a legitimate state and not a reason to intervene.

### Retire when

`zcrypto-engine-sleeve-count-changed` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_engine_active_sleeves` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`) — either way the rule can no longer fire and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-engine-exec-armed-too-long"></a>

## zcrypto-engine-exec-armed-too-long — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · order submission has been armed for over six hours`): `zcrypto_exec_armed` has read 1 continuously for the whole of the last six hours.

### What it means

The engine may submit orders only when BOTH arming keys are present: the `armed` flag baked into its deployed config, and an arm file the operator places on the engine host. `zcrypto_exec_armed` deliberately conflates the two into one 0/1 gauge — remote telemetry can say THAT the engine is armed, never WHICH of the two keys is set. The alert reads `min_over_time(zcrypto_exec_armed[6h]) == 1`: the MINIMUM over the window, not an average, so a single dip to 0 — a disarm at any point — clears the condition; only a gauge that has read 1 at every sample for the whole six hours trips it.

Arming is expected only inside an attended probe window, and is normally removed by the operator when that window ends. This alert exists because the failure mode is forgetting to remove it, not the arming itself — firing does not by itself mean anything went wrong, or that an order was actually submitted: the gate-level reading still needs the kill switch clear, the restart hold cleared, and the venue online before anything could move. But an engine left armed for six unattended hours has quietly removed one of the two keys that are supposed to stand between a mistake and real money, which is worth resolving even when nothing downstream has gone wrong yet.

### What to do

1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. This is the only place `reasons` and the two arming keys are visible separately — the dashboard and this page can show only that the engine is armed, never which key put it there.
2. **If the probe window is over, remove the arm file.** Deleting it disarms the engine immediately — no deploy, no restart, no engine downtime. `zcrypto_exec_armed` reads 0 on the engine's next evaluation (at most one cycle, roughly four hours), and because the rule reads `min_over_time` over the window, a single 0 sample is enough to drop it — the alert clears at the very next rule evaluation after that disarmed reading lands, not after six more hours have to pass.
3. **If the probe window is still legitimately open, leave it and let the alert ride.** It re-fires on the same condition every time `for: 15m` re-qualifies, so expect it to keep paging for the length of a long window; that repetition is intentional, not a bug.
4. **If you did not expect the engine to be armed at all**, treat this as a live safety-envelope breach: read the engine log and the `exec-status` output together, remove the arm file, and confirm nothing was submitted through the same window. Two places say so: the Engine board's **Execution — what actually happened at the venue** row, where `zcrypto_exec_orders_total{outcome="submitted"}` flat across the window is the answer you want, and the exec ledger's own `submitted` rows for the boundaries the window spans (the ledger read in the probe-window procedure below prints them by value). The ledger is the authority; the board is the fast read.

### Retire when

The engine begins arming continuously as its normal operating mode (order submission goes live and stays live). At that point a duration-based "armed too long" rule fires forever, and this rule must be **REPLACED** by one shaped for continuous arming — never silenced in place. Until then, `zcrypto-engine-exec-armed-too-long` retires only if it is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-engine-exec-kill-tripped"></a>

## zcrypto-engine-exec-kill-tripped — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the execution kill switch is engaged`): `zcrypto_exec_kill_tripped` has read 1 for the last five minutes.

### What it means

The kill file is present on the engine host, which forces the gate level to 0 (nothing may be submitted) regardless of arming, restart hold, or venue state — it is the one input that overrides every other reading. This is a deliberate control, not a fault: the switch exists so a human can refuse all submission immediately, and the alert exists because the failure mode is forgetting the switch is engaged, not the engagement itself. Firing does not mean anything is broken.

### What to do

1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. `reasons` will list `kill_switch` alongside whatever else the gate is currently refusing on — remote telemetry alone cannot show this.
2. **If the switch was engaged deliberately and the reason still holds**, silence this alert in Grafana for the expected duration rather than letting it keep paging — it re-fires every time `for: 5m` re-qualifies for as long as the file exists.
3. **If the reason no longer holds, remove the kill file on the engine host.** This clears immediately: no deploy, no restart, no engine downtime.
   **One reason carries work you must finish first — a withdrawn fill.** If the reason reads *shows N filled at the venue, less than the M this engine recorded*, the venue has taken back a fill it already reported. Nothing is reversed on that path by design: the ledger keeps the quantity it recorded, so `held`, the fills counter, the fee counter and the position the ladder sizes against all still carry the withdrawn amount. Clearing the kill file is exactly what lets the engine size its next order — against that stale figure. **Reconcile the ledger against venue truth before you clear it.** No code path does this, which is why the file is cleared by hand: the operator who clears it owns the reconciliation.
4. **If you did not expect the kill switch to be engaged**, that is itself the finding — read the engine log for whatever wrote the file before removing it.

### Retire when

`zcrypto-engine-exec-kill-tripped` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-engine-exec-not-evaluated"></a>

## zcrypto-engine-exec-not-evaluated — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the execution safety gate has stopped being evaluated`): `time() - zcrypto_exec_last_evaluation_timestamp_seconds` has read above 17100 s (4h45m) for 10 minutes, or the series is missing entirely.

### What it means

This is the heartbeat for the whole execution envelope, not a reading of any one input. The gate is evaluated at engine start and again after every cycle, roughly four-hourly, and every one of the six `zcrypto_exec_*` families is only ever updated as a side effect of that evaluation. If the evaluation call is dropped by a regression — anywhere in the cycle path, however unrelated it looks — every one of those six gauges FREEZES at its last published value. Cycle telemetry (`zcrypto_engine_cycle_success`, `zcrypto_engine_cycle_completed_at_seconds`) can keep reading perfectly healthy through this, because nothing about the cycle itself needs to fail for the gate call inside it to be skipped. A stale `disarmed` reading is indistinguishable on this dashboard from a live one — this alert is the only signal that can tell the difference.

`noDataState` is `Alerting` here, deliberately unlike the two rules above: a gate that has NEVER published at all — a fresh converge that never ran, or an exporter that never started — is this rule's worst case, not a state it should stay quiet through. Every other exec gauge already reads a safe default (0 / disarmed) before the first evaluation, so their own absence is comparatively low-stakes; this heartbeat is the one thing that must page on total silence too.

### What to do

1. **Check whether cycles are still completing** (the cycle-staleness alert, the cycle-age panel above this one on the Engine board). If cycles are also stopped, this is a symptom of the engine being down entirely — follow that alert instead, and expect this one to clear once the engine restarts and evaluates once at startup.
2. **If cycles ARE completing but this still fires**, the gate evaluation call has been dropped from the cycle path specifically — a code regression, not an infrastructure problem. Do not trust any of the other five `zcrypto_exec_*` readings on the board until it is fixed: every one of them is frozen at whatever it last read, and a frozen `disarmed` looks identical to a live one.
3. **Read the current state directly on the engine host**, never from the dashboard, while this is firing: `zcrypto engine exec-status`. It re-evaluates the gate on the spot rather than reading a possibly-stale published value, and it is the only place `reasons` is visible at all — that field never reaches Grafana, so there is no dashboard reading it could otherwise be checked against.
4. **Restore evaluation** (a code fix and a redeploy, or a restart if the process itself has wedged without crashing) and confirm the heartbeat panel starts advancing again before considering this resolved — the alert clears itself once a fresh sample lands.

### Retire when

`zcrypto-engine-exec-not-evaluated` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_exec_last_evaluation_timestamp_seconds` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`) — either way the rule can no longer fire and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-venue-concordance-failed"></a>

## zcrypto-venue-concordance-failed — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · venue concordance failed`): `zcrypto_venue_concordance_failures` read above zero on the most recent cycle — a ratified instrument is missing from the venue's loaded instrument set, or its constraints came back absent or unparseable.

### What it means

The executor's basket and what the venue actually reports have diverged for at least one leg: a delisting, a halted instrument, or a change to the constraint schema the parser does not yet handle are the usual causes. This is read-only observability — venue truth is journaled, never consulted for targets or orders, so a concordance failure changes nothing about what the engine does and no order path is affected by it on its own.

### What to do

1. Read the newest `venue-<HH>.json` on the engine host for the per-leg failure strings — it names which instrument and why.
2. This is read-only observability, so nothing here is auto-remediated. Do not converge on this alone.
3. Confirm recovery: the next cycle's `venue-<HH>.json` reads `status: "ok"` with an empty failures list, and `zcrypto_venue_concordance_failures` reads back to 0.

### Retire when

`zcrypto-venue-concordance-failed` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-venue-snapshot-stale"></a>

## zcrypto-venue-snapshot-stale — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · venue snapshot is stale`): no successful venue-truth snapshot has landed in over five hours — one 4h cycle plus slack.

### What it means

The boundary snapshot hook has stopped producing a fresh reading. The cycle itself may still be running and journaling targets fine — venue truth can never block a boundary by design, so a stuck or failing snapshot hook does not by itself mean the engine is down; check cycle liveness separately before assuming otherwise. Note that the gauge is seeded from the newest on-disk venue record at startup, so a routine engine restart alone does not trigger this — something has to actually stop producing.

### What to do

1. Check the engine container is up and cycles are landing — the newest `cycle-<HH>.json` on the engine host.
2. Read the newest `venue-<HH>.json` for a `status: "error"` and its reason.
3. Confirm recovery: the snapshot-age gauge reads within the last cycle interval and the newest `venue-<HH>.json` reads `status: "ok"`.

### Retire when

`zcrypto-venue-snapshot-stale` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="engine-data-socket-idle"></a>

## engine-data-socket-idle — KNOWN LIMITATION

### What you are seeing

Nothing fires this. You are reading `docker logs zcrypto-engine` on the engine host — because a reconnect line caught your eye, or because a Kraken outage is in progress and you are deciding whether the engine is making it worse.

### What it means

The engine's Kraken **data** socket is idle by design while disarmed: nothing is subscribed between intents, and the executor subscribes quotes per intent.

**First check whether the timer is actually off yet.** It is off only on an engine running a digest built from a revision that sets `ws_idle_timeout_ms=0` (spec `00101`); `docs/reference/fleet-pins.md`'s engine row records what is deployed. **Until that converge lands, a continuous `Read idle timeout` → reconnect loop every ~14.8 s is the EXPECTED state, not a regression** — and the crossing named below is then ~4.4 min rather than ~6.3, because the engine's own idle churn is already sitting in the rolling window. With the timer off, the lines mean:

- **`Read idle timeout: no data received for 10.0s`** — the timer has been turned back on. That is a config regression, not a venue event: the literal `0` was replaced (writing `None` does it, silently). Nothing to do on the host; fix the config and redeploy.
- **`Reconnecting` → `Reconnect succeeded`**, without a preceding `Read idle timeout` **or** `Heartbeat timeout` line — a real drop. Read it against `zcrypto_capture_reconnects_total{host="zcrypto"}` on the capture dashboard: both moving means the venue or the host's network moved; the engine alone moving is the engine's problem.
- **`Heartbeat timeout: no frame received for 90.0s`** — a dead peer, caught by the heartbeat at three intervals. Expect a reconnect to follow.

None of these lines reaches Loki — the engine ships only the `zcrypto` logger — so `docker logs` on the host is the only place they can be read.

**Why the socket's behaviour is capture's problem.** Kraken's edge rate-limits connection attempts to ~150 per rolling 10 minutes **per IP**, and bans the IP for 10 minutes on breach. The engine host is the L2 capture primary; `ws.kraken.com`, `ws-auth.kraken.com` and `api.kraken.com` resolve to the same edge. So a retry storm from the engine's two sockets can take the capture daemon's ability to reconnect with it — and L2 is unbackfillable. The engine's failure backoff (≈ 0.7 → 5 s, ~30 attempts per 150 s per socket, no knob to change it) crosses that limit about 6.3 minutes into a fast-failing outage.

### What to do

- **A Kraken outage in progress and both engine sockets retrying** (`Reconnecting` lines every few seconds, `Reconnect attempt N failed`): **stop the engine** before the retry count nears 150 in ten minutes. A ban self-renews only while something keeps retrying, and the capture daemon's own reconnect needs the budget more than the disarmed engine does.

  ```bash
  sudo systemctl stop zcrypto-engine     # NOT `docker stop`
  ```

  **`docker stop zcrypto-engine` does not stop the engine.** The unit's `ExecStart` is an attached `docker compose up` with `Restart=always`, `RestartSec=10`: stopping the container makes the compose process return, the unit exit, and systemd start it again ten seconds later — the retries you were trying to stop resume on their own. `systemctl stop` runs the unit's `ExecStop` (`docker compose down`) and leaves it down.

  **The cost, before you do it:** boundary cycles run at 00/04/08/12/16/20 UTC, and a boundary that passes with no journal artifact zeroes the ratified gate streak. A restart re-runs a missed boundary only within `[B, B+25 min]` and only while that boundary has no `cycle-<HH>.json` *or* `failed-cycle-<HH>.json`. Stopping just after a boundary is nearly free; stopping just before one costs the streak.

  Start it again with `sudo systemctl start zcrypto-engine` once `zcrypto_capture_reconnects_total{host="zcrypto"}` stops moving, and read the next `cycle-<HH>.json` for `completed_at` inside `[B, B+30 min]` as the all-clear.

- **A single `Reconnecting`/`Reconnect succeeded` pair** with the venue quiet — note it and move on; the heartbeat did its job.

- **Any `Read idle timeout` line at all, on an engine whose deployed revision sets `ws_idle_timeout_ms=0`** — the knob regressed. Find the change to `cli/engine/node.py::_data_client_config` and redeploy; the builder test that pins it (`test_engine_node.py`) says which value was written. On an engine that predates that converge the same line is expected — check the pins row first.

### Retire when

`ws_idle_timeout_ms=0` is no longer set in `cli/engine/node.py::_data_client_config` — a standing subscription landed and spec `00101` D5's restore rule applied — or the socket lines reach Loki, whichever comes first.

______________________________________________________________________
