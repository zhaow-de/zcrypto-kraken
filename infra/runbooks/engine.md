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

______________________________________________________________________

<a name="zcrypto-engine-cycle-stale"></a>

## zcrypto-engine-cycle-stale — ALERT

### What you are seeing

A **critical** Grafana alert (`Engine · cycles have stopped`): `time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}` above 16500 s (4h35m) for 5 minutes, **or the series is gone entirely** — `noDataState` is `Alerting`. Panel 11 on the `zcrypto-engine` board is the same number.

16500 is cadence arithmetic, not a generic staleness bar: boundaries are **00/04/08/12/16/20 UTC** and a healthy completion lands inside `[B, B+30 min]`, so the worst legitimate age is 4h30m, reached just before the next cycle lands. Anything past that is a stopped or crash-looping engine, never a slow one.

### What it means

At least one boundary produced **no journal artifact at all** — neither `cycle-<HH>.json` nor `failed-cycle-<HH>.json`. This is not the failed-cycle case: a failed cycle writes its sidecar and still refreshes this gauge, and has its own rule below.

Three shapes produce it, and the order you rule them out matters:

- **The telemetry plane on the primary is dark.** The gauge is seeded at engine startup from the newest journal artifact (falling back to process start), so it is never legitimately absent while the engine runs — absence means the exporter or the whole plane is gone. `Fleet · Alloy dark — Capture primary` reads `count(up{host="zcrypto"})`, which stays ≥ 1 while Alloy is up even though the engine's own scrape target reads 0, so the two rules do **not** cover each other. The accepted cost is named in the rule: a genuine Alloy-dark event on the primary double-pages.
- **The engine container is stopped or crash-looping.**
- **`run_cycle` raised before writing anything** — a poisoned store, a disk error. The node survives it deliberately and logs `shadow node: run_cycle(<ts>) raised; the boundary stays journal-absent`. Note the dead-man behaves differently here: a success pings healthchecks.io, a sidecar pings `/fail`, and a *raising* cycle pings **nothing** — so a healthchecks.io alert with no preceding `/fail` reads "the node is up but a cycle raised; suspect the store".

**A missed boundary is not recoverable once B+25 min has passed**, so that UTC day will not be clean and the gate's streak resets at the next day-close.

**And if the engine was armed, a restart does not resume submission on its own**: every engine start writes the restart-hold file, which is cleared only by hand. Read that as a safety property, not a fault.

### What to do

1. **Rule out Alloy-dark FIRST — before touching the engine.** From the workstation:
   ```
   uv run python infra/scripts/grafana-query.py 'count(up{host="zcrypto"}) or on() vector(0)' 'up{job="engine_app",host="zcrypto"}'
   ```
   A `count` of 0, or `(no series)`, means the primary's telemetry plane is dark: follow `Fleet · Alloy dark — Capture primary` and stop here, because every rule scoped to this host is blind. `count` ≥ 1 with `up{job="engine_app"}` at 0 means Alloy is fine and nothing is answering on `127.0.0.1:9102` — the engine container is down. **An empty result is never a zero.**
2. **Read the container, every inspect scoped to one field.** This container carries the live Kraken trade key in its environment; an unscoped inspect prints it.
   ```
   ssh zcrypto
   sudo systemctl status zcrypto-engine --no-pager
   sudo docker inspect --format '{{.State.Status}} started={{.State.StartedAt}} restarts={{.RestartCount}}' zcrypto-engine
   sudo docker logs --since 6h zcrypto-engine | grep -E 'shadow node|run_cycle|Traceback|ERROR|CRITICAL' | tail -40
   ```
   Never `{{json .Config}}`, never `{{json .Config.Env}}`, never `docker exec … env`, never `docker compose config`.
3. **Read the journal artifacts for how far the last boundary got.** `<HH>` is the boundary, never the wall-clock hour.
   ```
   sudo ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/
   sudo ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/snapshots/
   ```
   A boundary with `snapshots/cycle-<HH>/` but no record raised **after** snapshotting (store or model side); no snapshots dir at all raised before the refresh got that far (store unreadable, config). A `failed-cycle-<HH>.json` present means this is not your alert — go to the failed-cycle section below.
4. **Restart only if the unit is down or the process is wedged, and only inside the inter-cycle gap.** The boundaries are fixed at 00/04/08/12/16/20 UTC, so the gap is from roughly B+30 min to the next boundary; run `date -u` first and do not start a restart with a boundary minutes away.
   ```
   sudo systemctl restart zcrypto-engine
   ```
   **`docker stop zcrypto-engine` does not stop the engine** — the unit is an attached `docker compose up` with `Restart=always`/`RestartSec=10`, so systemd brings it back ten seconds later; [`engine-data-socket-idle`](#engine-data-socket-idle) has the full treatment and the outage-time reasoning. If now is still within `[B, B+25 min]` and that boundary has no artifact, the restarted node re-runs it by itself; past that nothing catches up, and a `cycle --at` for a lapsed boundary lands outside the 30-minute window, so the day stays unclean either way.
5. **A converge is a separate, attended decision** — the engine play needs `-e converge_primary=true` and re-asserts the inter-cycle window, and it restarts the live trade engine. Never run `site.yml` un-tagged on the primary.
6. **All-clear by value**: the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and `uv run python infra/scripts/grafana-query.py 'time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}'` drops below 1800.

### Retire when

`zcrypto-engine-cycle-stale` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_engine_cycle_completed_at_seconds` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`).

______________________________________________________________________

<a name="zcrypto-engine-cycle-failed"></a>

## zcrypto-engine-cycle-failed — ALERT

### What you are seeing

A **warning** Grafana alert (`Engine · the last cycle failed`): `zcrypto_engine_cycle_success{host="zcrypto"}` reads 0, with `for: 0s` — the outcome is already final the instant the gauge reads 0, so there is no pending period to wait through. Panel 12 on the `zcrypto-engine` board is the same gauge, titled so that an **absent** series reads as "no outcome known yet", not as failure.

The gauge stays 0 until a later boundary succeeds, up to 4 hours away. One event, not a condition worsening.

### What it means

The cycle reached a controlled failure path and recorded it as `failed-cycle-<HH>.json` beside the day's records. The sidecar names the reason, and there are exactly two:

- **`refresh_deadline`** — the store's settle-verify refresh could not complete inside the 25-minute reserve measured from the boundary. Usually the venue's OHLC fetch or the transport under it.
- **`stale_pair`** — one or more pairs' raw series were stale against the boundary invariant, so the build was skipped. The sidecar's `offending_pairs` names them.

The engine is alive: this gauge was refreshed by the failure itself. That is exactly why liveness cannot cover this and the two rules exist separately — the metrics sink runs after every cycle, success or failure, and refreshes `cycle_completed_at` unconditionally, so an engine whose every cycle fails on schedule keeps `Engine · cycles have stopped` silent forever.

**A re-run cannot make the day clean, and this is the thing to be sure of at 03:00.** The engine never re-runs a boundary that already has any artifact — `startup_action` refuses on the artifact's existence, independently of the `[B, B+25 min]` window — so `cycle_success == 0` implies the sidecar exists implies no automatic retry will ever happen. The only re-run path is `zcrypto engine cycle --at <boundary> --replace`, and its record's `completed_at` will sit outside `[B, B+30 min]`, which the gate scores as a late cycle and fails anyway. So the clean-day streak for that UTC day is already gone; re-run only when the boundary's **targets** matter to something downstream, never to repair the score.

The failure logs at WARNING (`run_cycle: <ts> failed (<reason>: <pairs>); sidecar at …`), so it does **not** page `Engine · ERROR logs`; the healthchecks.io check took a `/fail` ping.

One nuance worth knowing before you chase a fresh failure: the gauge is also **seeded at engine startup** from the newest journal artifact, sidecars included. A restart taken while the newest artifact is a failed cycle re-publishes 0 and re-arms this page with nothing new having failed — check the sidecar's `cycle_ts` against the container's `StartedAt` before treating it as a new event.

### What to do

1. **Read the sidecar.** Fields are `cycle_ts`, `attempted_at`, `completed_at`, `reason`, `offending_pairs`.
   ```
   ssh zcrypto
   sudo sh -c 'cat /var/lib/zcrypto-engine/journal/$(date -u +%F)/failed-cycle-*.json'
   ```
2. **Read the boundary's own log lines**: `sudo docker logs --since 5h zcrypto-engine | grep -E 'run_cycle|refresh|stale' | tail -40`. A `refresh_deadline` alongside Kraken REST trouble is a venue event — check `https://status.kraken.com` and the capture side's venue-status signal before suspecting the engine. A `stale_pair` naming one pair while everything else is fresh is that pair's feed; check the corporate-action ledger in `docs/reference/` for a symbol change or delisting.
3. **Nothing needs restarting.** The engine attempts the next boundary on its own. A restart here buys nothing and costs the restart hold.
4. **If — and only if — the boundary's targets are needed downstream**, re-run it attended, inside the inter-cycle gap (`date -u` first; boundaries 00/04/08/12/16/20 UTC):
   ```
   sudo docker exec zcrypto-engine zcrypto engine cycle --at <YYYY-MM-DDTHH:00:00+00:00> --replace
   ```
   `--replace` **deletes** the boundary's sidecar, its record and its `snapshots/cycle-<HH>/` tree before re-running; without the flag an already-journaled boundary is refused outright. Never `--replace` a boundary that carries a success record — that destroys journaled evidence the gate scores.
5. **The same reason at consecutive boundaries is a store or feed problem, not four accidents.** Check the store's freshness (`sudo ls -l /var/lib/zcrypto-engine/store/`) and the capture primary's own health — the engine reads the venue through the same host. A store data-integrity failure has its own documented recovery (`zcrypto engine seed`), which is an attended action, not a per-cycle retry.
6. **All-clear by value**: `uv run python infra/scripts/grafana-query.py 'zcrypto_engine_cycle_success{host="zcrypto"}'` reads 1 after the next boundary.

### Retire when

`zcrypto-engine-cycle-failed` is absent from `infra/grafana/alerts.yaml`, or `seed_cycle_success` in `cli/engine/command.py` no longer registers `zcrypto_engine_cycle_success`.

______________________________________________________________________

<a name="zcrypto-engine-error-logs"></a>

## zcrypto-engine-error-logs — ALERT

### What you are seeing

A **warning** Grafana alert (`Engine · ERROR logs`) on the `logs` receiver: at least one ERROR or CRITICAL line from the engine on the capture primary in the last 15 minutes. The message text is on the page — up to **five distinct messages**, 200 characters each, one alert instance per distinct line. Zero is the healthy baseline.

Two properties of the page itself: a storm can carry more lines than the five shown, and the `logs` receiver **disables resolve messages** — log alerts age out rather than resolving, so no all-clear ping is coming.

### What it means

Something went wrong **between** boundaries. The cycle rules see only a boundary's final outcome, so key or API failures, store refresh errors, venue-snapshot failures, order-path exceptions, a raising metrics sink (`metrics sink raised for cycle … -- continuing`) and the node's own `shadow node: run_cycle(…) raised` all surface here first — on the host that holds the live Kraken trade key.

Note what does **not** appear here: a controlled cycle failure logs at WARNING, so a `failed-cycle` sidecar never pages this rule. If you are seeing both, they are two findings.

### What to do

1. **Read the full lines, not the 200-character hoist.** Panel 102 on the `zcrypto-logs` board filtered to `container="engine"`, or on the host `sudo docker logs --since 30m zcrypto-engine | tail -80` — tracebacks are in the same stream. Count a storm before calling it five errors: `sum(count_over_time({host="zcrypto", container="engine", level=~"ERROR|CRITICAL"}[15m]))`.
2. **Classify by message, and act on the class:**
   - **`shadow node: run_cycle(…) raised`** — a boundary is being lost right now with no artifact written. Go to [`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) step 3 immediately, well before its 4h35m bar can fire.
   - **`shadow node: snapshot_fn() raised`** — venue truth only. The cycle proceeds with `venue_state=None` by design; this cannot cost a boundary. Read it beside [`zcrypto-venue-snapshot-stale`](#zcrypto-venue-snapshot-stale) and [`zcrypto-venue-concordance-failed`](#zcrypto-venue-concordance-failed).
   - **`metrics sink raised …`** — telemetry only; the record and its artifact were already written before the sink ran, so nothing about the cycle is in doubt.
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch — this is the execution path, and it is the one to act on now.** Continue at step 3.
3. **An execution-path error while ARMED is a live money situation.** Read the gate on the host, which is the only place `reasons` exists at all — it never reaches Grafana, and `zcrypto_exec_armed` conflates the two arming keys into one gauge:
   ```
   sudo docker exec zcrypto-engine zcrypto engine exec-status
   ```
   It prints `level=<none|reduce_only|full>`, a `reasons=` line (`-` means none), then every gate input. **If it reads `level=full` — or anything other than `level=none` — and you do not understand the error, disarm.** Per the arm/disarm procedure in [`engine-procedures.md`](engine-procedures.md#engine-probe-window):
   ```
   sudo rm /var/lib/zcrypto-engine/exec/armed
   ```
   That disarms immediately — no deploy, no restart, no engine downtime — and the gate then reads `level=none`, `reasons=arm_file_absent`. **Removing the arm file is only the first key.** The deployed config still says armed until `exec_armed` is converged back to `false`, which the procedure requires **the same day**: until then anything that recreates that file re-arms the engine with no review. Do the converge as that procedure describes, inside the inter-cycle gap.
4. **Then reconcile what actually happened at the venue** — the exec ledger's `exec-<HH>.json` records for every boundary the window spans (the ledger read in `engine-procedures.md` prints them by value), and `zcrypto_exec_orders_total{outcome="submitted"}` on the Engine board as the fast read. The ledger is the authority.
5. **Do not restart on an ERROR line alone.** Restart only when the node loop itself is wedged — no completion at the next boundary — and then only inside the inter-cycle gap.
6. **The same message every boundary is a defect, not an incident to re-triage.** Capture the message and put the work where work lives; this runbook is not the backlog.

### Retire when

`zcrypto-engine-error-logs` is absent from `infra/grafana/alerts.yaml`, or the engine no longer ships as `container="engine"` (`ZCRYPTO_LOG_SERVICE` in `infra/ansible/roles/engine/templates/compose.yaml.j2`).

______________________________________________________________________

<a name="zcrypto-engine-log-dead"></a>

## zcrypto-engine-log-dead — ALERT

### What you are seeing

A **critical** Grafana alert (`Engine · log pipeline dead`) on the `logs` receiver: Loki holds **not one line of any level** from `{host="zcrypto", container="engine"}` in the last 6 hours. Panel 103 on the `zcrypto-logs` board carries the count; read it against the threshold of 1, not against its height.

### What it means

**The title names only one of the two states this can be, and the phone shows the title first.** Separate them with the cycle age before doing anything else.

- **The log plane is dead while the engine is fine.** Then `Engine · ERROR logs` is blind — the only error channel for the process holding the live trade key sees nothing — until this is fixed.
- **The engine missed a cycle.** The engine is a **burst emitter**: roughly eleven lines within ~90 s of each 4-hourly boundary and nothing between, so a missed burst empties the window. This is an accepted, named cost of the window's sizing rather than a defect: `Engine · cycles have stopped` fires first and correctly on the `metrics` receiver (about B+40m to B+1h10m), and this rule follows at about B+2h01m saying the log pipeline is dead when it is fine.

The 6 h window is sized to the cycle and **tolerates exactly zero missed cycles**: 6 h against a 4.00 h period is 2 h of slack, and the measured rolling 6 h count never fell below 11 (max 34) over 12.6 days. Do not tighten it toward the ERROR rule's 15 minutes — they watch different things.

### What to do

1. **Which state? Read the cycle age and the shipper's own gauges together**, from the workstation. **Scope the logship series by `job`** — the capture daemon and the engine both publish them on this host and both carry `host="zcrypto"`, so an unscoped query returns two series and answers about the wrong process:
   ```
   uv run python infra/scripts/grafana-query.py \
     'time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}' \
     'time() - zcrypto_logship_last_cycle_timestamp_seconds{job="engine_app",host="zcrypto"}' \
     'increase(zcrypto_logship_dropped_lines_total{job="engine_app",host="zcrypto"}[6h])'
   ```
   Cycle age above 16500 ⇒ the **engine**: follow [`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) and expect this page to clear at the next boundary's burst. Cycle age healthy ⇒ the **log plane**; continue below. `(no series)` on the cycle age is itself the finding — the telemetry plane is dark, not quiet.
2. **Read the two shipper gauges as the two questions they are.** `zcrypto_logship_last_cycle_timestamp_seconds` is liveness — the worker advances it on an idle cycle too, and it stalls only while the worker is stuck retrying or wedged. `zcrypto_logship_dropped_lines_total` is delivery — a permanently rejected batch (a revoked token, a wrong path) still completes a cycle and still advances the liveness gauge, so credential failures show up **only** as dropped lines. **Do not use `zcrypto_logship_last_success_timestamp_seconds` for liveness**: it goes stale whenever logging is merely quiet, and it is absent entirely until the first successful ship.
3. **On the host, prove which half is broken:**
   ```
   ssh zcrypto
   sudo docker logs --since 6h zcrypto-engine | wc -l
   sudo docker logs --since 6h zcrypto-engine | grep -iE 'ship|loki|401|403|timeout' | tail
   ```
   A non-zero count means the process is logging and the shipper is what failed — the ship handler's own failures are visible locally only. **Print that count before trusting any conclusion drawn from an empty grep.**
4. **Check whether capture went dark with it.** Both `zcrypto-capture-log-dead-primary` and this rule firing ⇒ the host's push path or Grafana Cloud, not the engine — the two services read Loki creds from the same rendered file. Engine alone ⇒ the engine container or its env.
5. **A credential fix is a converge, never a hand edit** — the engine's Loki env comes from the render, and the file is read at container create, so a rotated token needs the role's converge. That is attended, needs `-e converge_primary=true`, and runs inside the inter-cycle gap only.
6. **All-clear by value**: after the next boundary's burst, the rule's own query returns at least 11 — `sum by (host) (count_over_time({host="zcrypto", container="engine", level=~".+"} [6h]))`. Confirm the number; an empty result is not a zero.

### Retire when

`zcrypto-engine-log-dead` is absent from `infra/grafana/alerts.yaml`, or the engine no longer ships as `container="engine"` (`ZCRYPTO_LOG_SERVICE` in `infra/ansible/roles/engine/templates/compose.yaml.j2`). The 6 h window retires only with a re-measured cadence — it is derived from the 4-hourly loop, not copied from the other log canaries.
