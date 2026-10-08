# Engine runbooks — the trading engine and its order path

You are here because **an alert fired in Slack**, because **a guard in the code pointed you here**, or because you are running an attended procedure, which now lives in [`engine-procedures.md`](engine-procedures.md) beside this file. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="zcrypto-engine-sleeve-count-changed"></a>

## zcrypto-engine-sleeve-count-changed — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · sleeve composition changed`): the number of the shadow engine's sleeves carrying non-zero exposure stepped up or down within the last 26 hours. Nothing is broken. This alert announces a change in what the book is, not a fault.

### What it means

The book is three sleeves, `B`, `A1`, `A2`, at fixed one-third weights. A flat sleeve contributes zero and re-arms on its own signal, with no deploy and no config change.

A one-sleeve book is a third of that sleeve's own gross, and lower again while `cli/risk/governor.py`'s multiplier is below 1.0: five bars at half after any bar losing the daily limit or more, and a drawdown ladder cutting to 0.5, then 0.25, then flat. A halved book is as likely to be the daily-loss arm as a deep drawdown.

- **The composition changing does not tell you the gross changed.** Measure it, do not scale it. Everything sized against the previous composition (the drift band, the expected order notionals) was derived under a state that no longer holds. Read the series.
- **Order placeability moves with it.** Measure it per leg, and against `ordermin`, a base-unit quantity floor, not `costmin`, a per-leg notional floor. Read the engine's own intended orders in the day's `orders.jsonl`, not the count.

The alert reads `changes(zcrypto_engine_active_sleeves[26h])`, so it fires on a step in either direction: a dormant sleeve arming, or an active one going flat.

It does not fire when the engine goes dark: `noDataState` is `OK`, because engine liveness is the healthchecks.io dead-man's job and [`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale)'s. It does not fire on a failed cycle either: a cycle that never reached the build reports no composition, so both gauges hold their previous values rather than reading as "everything went flat".

### What to do

1. **Identify which sleeve moved, and in which direction.** `uv run python infra/scripts/grafana-query.py 'zcrypto_engine_sleeve_gross'` prints one value per `sleeve` label. Compare against `zcrypto_engine_active_sleeves` over the last few days to see when the step landed. A single 4h cycle's blip and a sustained re-arming are different events; do not act on one cycle.

2. **Do not restart, converge, or "fix" anything.** The sleeve's own signal turned on or off. There is no failure to recover from, and a restart changes nothing about the composition.

3. **Re-derive the numbers that were sized against the old composition** before the next go-live decision reads them: the model-consistency band the gate compares realized performance against, and the expected order notionals versus the venue minimums. Neither updates itself. The command is `uv run zcrypto engine accum-replay --journal-dir <journal> --since <YYYY-MM-DD> --until <YYYY-MM-DD> --nav 1000 --minimums <newest kraken-refdata-*.json>`, and three things decide whether its answer is usable:

   - **Run it over a window that starts well before the composition changed, and slice**, or run it standalone and know what you are getting: the replay initialises held quantity to zero at its first cycle, so a window starting in a low-gross stretch carries a per-asset offset that lasts until that asset's delta first clears both floors (no count command: `cli/engine/feeders.py::accumulation_payload` snaps `held_qty` to target on that delta).
   - **A band the gate can rest on needs at least 3 complete ISO weeks in the new composition.** That is the basis the gate's edge is defined on.
   - **Re-check the minimums stamp in the same pass** and quote which snapshot you used; Kraken moves those without notice.

   **That command is the floor half only.** Read the realized half beside it, or you have re-derived one side of a comparison. `accum-replay` measures what the venue's minimums make unavoidable; what the engine actually held is `uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <YYYY-MM-DD> --until <YYYY-MM-DD>`, which prints both halves per complete ISO week at one NAV. Until the engine has journaled fills the realized column reads *no data*, and that is the honest answer for a series that has not started, never a zero to average in.

4. **Record the transition durably** (date, which sleeve, the gross before and after) as a new row in `docs/reference/sleeve-composition-ledger.md`, which carries the read recipe. This alert ages out with its 26 h window and is not a record; the book's composition history is what a later gate reading depends on.

5. **If the count went down to one or zero**, treat it as information, not an emergency: a long-only sleeve going flat in a downtrend is the risk control working (no count command: `cli/portfolio/crossfreq_system.py` builds A1 and A2 `short="off"`, B non-negative). Zero active sleeves is a flat book, a legitimate state and not a reason to intervene.

### Retire when

`zcrypto-engine-sleeve-count-changed` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_engine_active_sleeves` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`). Either way the rule can no longer fire and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-engine-exec-armed-too-long"></a>

## zcrypto-engine-exec-armed-too-long — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · order submission has been armed for over six hours`): `zcrypto_exec_armed` has read 1 continuously for the whole of the last six hours.

### What it means

The engine may submit orders only when both arming keys are present: the `armed` flag baked into its deployed config, and an arm file the operator places on the engine host. `zcrypto_exec_armed` conflates the two into one 0/1 gauge: remote telemetry can say that the engine is armed, never which key set it. The alert reads `min_over_time(zcrypto_exec_armed{host="zcrypto"}[6h]) > 0.5`, the minimum over the window and not an average, so a single dip to 0 (a disarm at any point) clears the condition; only a gauge that read 1 at every sample for the whole six hours trips it.

Arming is expected only inside an attended probe window, and is normally removed by the operator when that window ends. The alert exists because the failure mode is forgetting to remove it, not the arming itself, so firing does not by itself mean an order was submitted. But an engine left armed for six unattended hours has quietly removed one of the two keys that are supposed to stand between a mistake and real money, which is worth resolving even when nothing downstream has gone wrong yet.

### What to do

1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. This re-evaluates the gate and prints `reasons` and the two arming keys separately; the dashboard and this page can show only that the engine is armed, never which key put it there (no count command: `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons` and ANDs the two keys).
2. **If the probe window is over, remove the arm file.** Deleting it disarms the engine immediately: no deploy, no restart, no engine downtime. `zcrypto_exec_armed` reads 0 on the engine's next gate evaluation — the executor's idle refresh within a minute, or its next tick while a plan runs — and because the rule reads `min_over_time` over the window, a single 0 sample is enough to drop it. The alert clears at the next rule evaluation after that disarmed reading lands, not after six more hours.
3. **If the probe window is still legitimately open, leave it and let the alert ride.** Its `for: 15m` is a pending period before the first page, not a re-arming clock: it stays firing while the condition holds and re-pages at the default notification policy's repeat interval (no count command: the rule in `infra/grafana/alerts.yaml` sets no `repeat_interval` of its own), so expect it to keep paging for the length of a long window; that repetition is intentional.
4. **If you did not expect the engine to be armed at all**, treat this as a live safety-envelope breach: read the engine log and the `exec-status` output together, remove the arm file, and confirm nothing was submitted through the same window. Two places say so: the Engine board's **Execution — what actually happened at the venue** row, where `zcrypto_exec_orders_total{outcome="submitted"}` flat across the window is the answer you want, and the exec ledger's own `submitted` rows for the boundaries the window spans (the ledger read in [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) prints them by value). The ledger is the authority; the board is the fast read.

### Retire when

The engine begins arming continuously as its normal operating mode (order submission goes live and stays live). At that point a duration-based "armed too long" rule fires forever, and this rule must be **replaced** by one shaped for continuous arming, never silenced in place. Until then, `zcrypto-engine-exec-armed-too-long` retires only if it is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-engine-exec-kill-tripped"></a>

## zcrypto-engine-exec-kill-tripped — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the execution kill switch is engaged`): `zcrypto_exec_kill_tripped` has read 1 for the last five minutes.

### What it means

The kill file is present on the engine host, which forces the gate level to 0 (nothing may be submitted) regardless of arming, restart hold, or venue state — it is a refusal that stands whatever the other inputs read, and the gate reports it first in `reasons`. This is a deliberate control, not a fault: the switch exists so a human can refuse all submission immediately, and the alert exists because the failure mode is forgetting the switch is engaged, not the engagement itself. Firing does not mean anything is broken.

### What to do

1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. `reasons` will list `kill_switch` alongside whatever else the gate is currently refusing on — the gauges alone cannot show this (no count command: `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons`).
2. **If the switch was engaged deliberately and the reason still holds**, silence this alert in Grafana for the expected duration rather than letting it keep paging — its `for: 5m` is a pending period before the first page, not a re-arming clock: it stays firing for as long as the file exists and re-pages at the default notification policy's repeat interval (no count command: the rule in `infra/grafana/alerts.yaml` sets no `repeat_interval` of its own).
3. **If the reason no longer holds, remove the kill file on the engine host.** This clears within three minutes at most, with no deploy and no restart for a file placed by hand: the executor's next gate refresh within a minute, then a scrape and the rule's evaluation, a minute each. A file this process wrote on a trip also latches the process, which refuses each plan after it until a restart inside the inter-cycle gap with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits (no count command: `_GATE_REFRESH` in `cli/engine/executor.py` is the idle cadence).
   **One reason carries work you must finish first — a withdrawn fill.** If the reason reads *shows N filled at the venue, less than the M this engine recorded*, the venue has taken back a fill it already reported. Nothing is reversed on that path by design: the ledger keeps the quantity it recorded, so `held`, the fills counter, the fee counter and the position the ladder sizes against all still carry the withdrawn amount. Clearing the kill file is exactly what lets the engine size its next order — against that stale figure. **Reconcile the ledger against venue truth before you clear it.** No code path does this, which is why the file is cleared by hand: the operator who clears it owns the reconciliation.
4. **If you did not expect the kill switch to be engaged**, that is itself the finding — read the engine log for whatever wrote the file before removing it.

### Retire when

`zcrypto-engine-exec-kill-tripped` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-engine-exec-not-evaluated"></a>

## zcrypto-engine-exec-not-evaluated — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the execution gate's heartbeat has stopped: no boundary, plan or trip evaluation in 4h45m`): `time() - zcrypto_exec_last_evaluation_timestamp_seconds{host="zcrypto"}` has read above 17100 s (4h45m) for 10 minutes, or the series is missing entirely.

### What it means

This is the heartbeat for the execution envelope's boundary path, not a reading of any one input. The gate is evaluated at engine start, after every cycle in the boundary sink — roughly four-hourly, beside the exec record that sink writes first — on the executor's tick while a plan runs and when it trips the kill switch, and once a minute on its idle refresh; of the seven gauges `_ExecGauges` publishes — the six gate readings plus this heartbeat, not the other `zcrypto_exec_*` families, which are the executor's own instruments — the six readings are written at every one of those evaluations and the heartbeat at all but the idle refresh, and nowhere else. If the boundary sink's evaluation call is dropped by a regression — anywhere in the cycle path, however unrelated it looks — or its record write keeps failing, which the sink orders before the gauges so that a record never written starves the heartbeat, this heartbeat FREEZES at its last published value while the six readings keep moving on the refresh: the only other writers of the heartbeat are a kill trip and a plan in flight, whose intent-time gate reads reach the same publish hook — and a plan is built and picked up whether or not the engine is armed, since arming is an input to the gate (`armed_in_config`, the arm file) rather than a condition on the plan. Cycle telemetry (`zcrypto_engine_cycle_success`, `zcrypto_engine_cycle_completed_at_seconds`) can keep reading perfectly healthy through this, because nothing about the cycle itself needs to fail for the gate call inside it to be skipped or its record write to raise. Live readings beside a frozen heartbeat are indistinguishable on this dashboard from a healthy boundary — this alert is the only signal that can tell the difference.

`noDataState` is `Alerting` here, deliberately unlike the two rules above: a gate that has NEVER published at all — a fresh converge that never ran, or an exporter that never started — is this rule's worst case, not a state it should stay quiet through. Every other gauge in that group already reads a safe default (0 / disarmed) before the first evaluation, so their own absence is comparatively low-stakes; this heartbeat is the one thing that must page on total silence too.

### What to do

1. **Check whether cycles are still completing** (the cycle-staleness alert, the cycle-age panel above this one on the Engine board). If cycles are also stopped, this is a symptom of the engine being down entirely — follow that alert instead, and expect this one to clear once the engine restarts and evaluates once at startup.
2. **If cycles ARE completing but this still fires**, the boundary sink's gate evaluation has been dropped from the cycle path — a code regression, not an infrastructure problem — or its exec record write has been failing at every boundary: the sink writes the record before it touches the gauges, so a write that raises starves this heartbeat by design, and `metrics sink raised for cycle …` in the engine log is that shape. The other six gate gauges on the board (`zcrypto_exec_gate_level`, `zcrypto_exec_armed`, `zcrypto_exec_kill_tripped`, `zcrypto_exec_restart_hold`, `zcrypto_exec_venue_ok`, `zcrypto_exec_venue_read_failed`) keep moving on the executor's idle refresh, which publishes them with the heartbeat left alone, so they are live while the executor ticks, and `zcrypto engine exec-status` on the host reads the current state before you trust a tile; what is missing is the boundary's exec record, so read the engine journal on the host for the boundary's `exec-*.json` before trusting a window's ledger (set: the writes to the seven gate gauges under `cli/` from outside `_ExecGauges.update`, whose one call publishes the six readings and, except on the idle refresh, the heartbeat; count: `infra/scripts/count-list.sh gate-gauge-writes-outside-the-publish-call`).
3. **Read the current state directly on the engine host**, never from the dashboard, while this is firing: `zcrypto engine exec-status`. It re-evaluates the gate on the spot rather than reading a possibly-stale published value, and it prints `reasons` — that field never reaches a gauge, so there is no dashboard reading it could otherwise be checked against (no count command: the read is an operator action nothing records; `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons`).
4. **Restore evaluation** (a code fix and a redeploy, or a restart if the process itself has wedged without crashing, either one with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits) and confirm the heartbeat panel starts advancing again before considering this resolved — the alert clears itself once a fresh sample lands.

### Retire when

`zcrypto-engine-exec-not-evaluated` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_exec_last_evaluation_timestamp_seconds` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`) — either way the rule can no longer fire and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-engine-exec-venue-diverged"></a>

## zcrypto-engine-exec-venue-diverged — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the engine's read of Kraken's system status has failed for fifteen minutes`): `zcrypto_exec_venue_read_failed{host="zcrypto"}` has read 1 for fifteen minutes, and the Engine board's venue status tile reads READ FAILED beside NOT ONLINE.

### What it means

The engine reads Kraken's public `SystemStatus` over REST at its gate evaluations — once a minute on the executor's idle refresh, on each tick while a plan runs — and its gate refuses to submit unless that read answers `online`. `zcrypto_exec_venue_read_failed` reads 1 while the read itself fails: `unreachable` when the request did not reach Kraken or Kraken's endpoint answered with an HTTP error, `unreadable` when Kraken's answer could not be read, its error envelope among them. Kraken's own word is then unknown to the engine, so its gate reads `venue_not_online` and refuses to submit while Kraken, by its own word, may be trading: under the accumulation loop each intent a boundary's plan starts is refused with that reason, and its leg's gap stands until a later boundary drafts it again.

A Kraken maintenance is a word Kraken answered — `maintenance`, `cancel_only`, `post_only` — and reads 0 here: the capture side pages it from the `status` frames on its own WebSocket ([`capture.md#zcrypto-capture-venue-not-online`](capture.md#zcrypto-capture-venue-not-online)), and this rule stays quiet through it. The capture side does not see the engine's REST read fail, which is why this rule is the engine's alone.

### What to do

1. **Read the gate on the engine host**: `sudo docker exec zcrypto-engine zcrypto engine exec-status`. Its `venue_status` input reads `unreachable` or `unreadable` while the read fails, beside `venue_not_online` in `reasons`; a word Kraken answered there, `online` among them, says the read answers again. The command takes its own read in a fresh process, so it answers for the host's path to Kraken now, not for the engine's last read.
2. **Find the cause on the host's side of the read.** `unreachable` is the host's egress, its DNS, or Kraken's endpoint answering with an HTTP error; `unreadable` is a body the engine could not parse, Kraken's error envelope among them. Kraken's own status page and the capture side's reading say whether Kraken itself is trading.
3. **Let the read answer again.** The gate's next refresh, within a minute of a read that answers, publishes the venue's word, and the page clears at the rule's next evaluation after the 0 lands; no control file needs clearing.
4. **Restart the engine when the process itself is wedged**: `exec-status` in step 1 reads a word Kraken answered while the tile keeps reading READ FAILED past a few minutes. Take the restart inside the inter-cycle gap ([`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) step 4 says how to read where it opens) with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits; the restarted process places reducing orders alone under its restart hold until you clear it.

### Retire when

`zcrypto-engine-exec-venue-diverged` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_exec_venue_read_failed` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`) — either way the rule can no longer fire and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-engine-exec-watchdog-frozen"></a>

## zcrypto-engine-exec-watchdog-frozen — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the execution watchdog has frozen the loop`): `zcrypto_exec_watchdog_frozen{host="zcrypto"}` has read 1 for fifteen minutes.

### What it means

The engine's stale-socket watchdog freezes the accumulation loop when a venue socket, the market-data one or the execution one that carries the fills, stays down past its grace. On the tick it freezes, the engine revokes its active intent with `socket_down`, sends a cancel for each order its Cache holds open, and refuses each new intent with `socket_down` while the freeze stands; its log carries a CRITICAL line at the freeze naming the endpoint and the grace. The grace sits past the execution socket's hourly reconnect, which reports back within seconds, so a freeze is a real cut. A cancel sent into a cut may not reach Kraken, and an intent whose cancel went unanswered ends `ambiguous`: that is why the freeze waits for Kraken's own account before it lifts.

The freeze lifts by itself, with no restart and no deploy, on the tick at which no socket is down and the re-read pass that a socket's return arms has completed with its reads answered: the pass re-reads at Kraken the order rows the engine closed without Kraken's word, re-cancels what still rests, and settles the holdings. A return while the engine is disarmed, `zcrypto_exec_armed{host="zcrypto"}` reading 0, arms no pass, and the ledger decides what follows. With no order row open or `ambiguous`, the return that leaves no socket down lifts the freeze itself, its INFO line ending `the engine is disarmed, so the re-read pass waits for the first tick that reads it armed`, the page clears, and the first tick after the engine reads armed again runs the owed pass. With such a row, an order the cut may have left resting at Kraken, the freeze and its page stand: the CRITICAL `the execution watchdog's freeze stands -- the sockets are back and the engine is disarmed …` names each row, and while the engine stays disarmed you cancel each by hand on Kraken's open-orders page. A hand cancel ends the risk and not the page, which clears when the first armed tick's pass completes, or at a restart.

The freeze is folded into the gate level the engine publishes, so the gate-level tile reads 0 beside it, and a boundary inside the freeze journals `socket_down` among its exec record's `reasons`. `zcrypto engine exec-status` is no read of it: it builds its own gate in a fresh process and shows the gate's six reasons alone, `socket_down` not among them, so it can read `full` through a freeze.

### What to do

1. **Read the freeze in the engine log**: the `Logs` panel on the `zcrypto-logs` board with the container filter at `engine`, or `sudo docker logs --since 2h zcrypto-engine` on the host. The CRITICAL line at the freeze names the endpoint and the grace; a later `socket <endpoint> is back` line says it returned, ending `and none is down` or naming in parentheses the endpoints still counted down.
2. **If the cut is still on, let it run its course.** The `socket <endpoint> is down` line names the socket, and the tell that it is still down is that socket's own: for `kraken-spot-data-streams`, the public market data, capture on the same host is short of Kraken's book too (`zcrypto_capture_seconds_since_last_book_message{host="zcrypto"}` climbing); for `kraken-spot-user-streams`, the execution socket, capture's public book says nothing: nautilus's `Reconnect attempt <n> failed` lines still arriving under `container="engine-nautilus"` say it is still down, and their stopping is no proof of a return, since that stream ships nautilus's `[WARN]` and `[ERROR]` lines alone and drops its `Backing off` lines — read the return on the host, `sudo journalctl -u zcrypto-engine --since -2h | grep -i reconnect`, whose lines keep nautilus's levels below WARN too. The freeze lifts by itself, and the engine needs nothing from you meanwhile, unless it is disarmed over a row the cut left open (what it means, above). An execution socket that stays down while Kraken's public side answers may be its token read refused on the trade key, a permission or nonce error that is the key's to fix and that a restart does not cure. A Kraken outage pages from the capture side as well ([`capture.md#zcrypto-capture-venue-not-online`](capture.md#zcrypto-capture-venue-not-online)); a cut of the host's own network is the host's to fix.
3. **If the sockets are back and the freeze stands, one of four shapes holds it.** A CRITICAL `the execution watchdog's freeze stands -- the sockets are back and the engine is disarmed …` is a disarmed engine holding rows the cut left open: what it means, above, says what to do. The pass's CRITICAL `the re-read pass could not read the ledger or the venue on 3 ticks …` says it spent its budget on the orders: cancel by hand on Kraken's open-orders page what that line names as possibly resting. Its CRITICAL `the re-read pass could not read the venue's holdings on 3 ticks -- the position gauge keeps its reading and the execution watchdog's freeze stands` says it spent its budget on the holdings read, `TradeVolume` with the instrument listing, `OpenPositions` and `BalanceEx` on the trade key, the WARNINGs before it carrying each failed read's error: a permission or nonce error is the key's to fix, and the boundary's draft makes the same read, so the boundary may write `book-unread` too ([`zcrypto-engine-exec-boundary-not-drafted`](#zcrypto-engine-exec-boundary-not-drafted)). After either, the freeze lifts once a later return of a socket arms the pass again and its reads answer — the execution socket's hourly reconnect is one — or at a restart. A stale entry is a `socket <endpoint> is down` line with no `socket <endpoint> is back` after it although that socket came back by its own tell from step 2, capture receiving Kraken's book for the data socket or a reconnect of the execution socket in step 2's host log: restart. Take a restart inside the inter-cycle gap ([`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) step 4 says how to read where it opens) with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits; the restarted process places reducing orders alone under its restart hold until you clear it, under rung 3 by [`engine-procedures.md#rung-3-after-a-restart`](engine-procedures.md#rung-3-after-a-restart).

### Retire when

`zcrypto-engine-exec-watchdog-frozen` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-engine-exec-boundary-not-drafted"></a>

## zcrypto-engine-exec-boundary-not-drafted — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · two consecutive boundaries drafted nothing`): `min_over_time(zcrypto_exec_boundary_not_drafted{host="zcrypto"}[4h30m])` has read above 0.5 for ten minutes, so the gauge read 1 at each scrape of the last four and a half hours.

### What it means

At each 4-hourly boundary the engine drafts that cycle's plan and writes one accumulation record, `accum-<HH>.json` in the journal's day directory beside `cycle-<HH>.json`, whose `status` says what the draft did. `zcrypto_exec_boundary_not_drafted` reads 1 from the write of a record whose status is not `ok` until the next `ok` record's write, and 0 from an engine start. The window clears of 0 samples about 4h30m after the first such write, so the rule fires about 4h40m after it unless an `ok` record lands first, which at the next boundary means within about forty minutes of it: that boundary wrote a non-`ok` record too, or had written none yet, its draft still waiting for nothing to be in flight or its boundary path stopped, and two consecutive boundaries placed nothing. One lost boundary followed by an `ok` one stays quiet.

A failed draft moves no gate gauge, so a pair drafted at `full` pages here alone, and one whose gate is the cause pages beside the gate's own rules, such as the `refused` records a drawdown trip's boundaries write with the gate at `none` under `kill_switch`; the boundary's `exec-<HH>.json` `level` and `reasons` say which. The four statuses it covers: `no-cycle`, the boundary's cycle record absent or failed, so there was nothing to draft from; `book-unread`, the read of Kraken's balances or of its instrument listing beside it failing on each of its three tries, or the draft refusing a basket coin's `held` because the coin sits under an earn or staking code; `window-closed`, the boundary's submission window, three and a half hours from the boundary, closing before the draft could run, since the draft waits for nothing to be in flight; `refused`, the draft's plan refused by the engine, or the draft raising.

What repeats across boundaries while the gate reads `full`: a trade key whose private permission changed, or a nonce poisoned by a hand use of the key, answers each balance read with an error while the public status read keeps the gate at `full`; a Cache the engine cannot read fails the draft's read of the venue's constraints the same way; a basket coin held under an earn or staking code reads `book-unread` at each boundary until the coin moves, because the draft refuses its `held` while the equity mark counts it; a drill plan resting through the window holds the draft back until the window closes.

### What to do

1. **Read the two newest accumulation records on the engine host, by value**: `for f in $(ls /var/lib/zcrypto-engine/journal/*/accum-*.json | tail -2); do python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(sys.argv[1], d['status'], d['plan_id'])" "$f"; done`. Each `status` names which of `no-cycle`, `book-unread`, `window-closed` and `refused` that boundary wrote; `zcrypto_exec_boundary_not_drafted` on the Engine board's accumulation row shows when the 1 began. If the newest record is not from the boundary just past, that boundary has written none yet: a draft still waiting for nothing to be in flight, which writes its record, `window-closed` at the latest, by three and a half hours past its boundary, or a boundary path that stopped; read the engine log at that boundary, and [`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) if no cycle completed there.
2. **Read the cause in the engine log around those two boundaries**, by status:
   - `book-unread`: a WARNING per try carrying the error of the read that failed, the balance read's, where a permission or nonce error is the trade key's, or the instrument listing's; or the draft's refusal of an earn-coded coin, which names the coin and its code.
   - `refused`: the plan entry's reasons in the boundary's `exec-<HH>.json`, or the WARNING naming the exception the draft raised.
   - `window-closed`: what was in flight through the window, such as a drill plan, whose intents the exec records list.
   - `no-cycle`: the cycle's own failure, which [`zcrypto-engine-cycle-failed`](#zcrypto-engine-cycle-failed) or [`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) pages on in its own right.
3. **Apply the cause's own remedy, and let the next boundary draft.** A basket coin under an earn or staking code goes back to spot on Kraken, the act the refusal's text names, and the next boundary reads it as held; a key or nonce error is the key's to fix; a drill plan holding the window is ended with its drill; anything else is the error its WARNING names. The page clears once an `ok` record puts a 0 back in the window.
4. **A restart is for a process that is itself wedged**, taken inside the inter-cycle gap ([`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) step 4 says how to read where it opens) with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits: a failing key or an earn-coded coin answers a restarted process the same way. A restart also clears the page, its 0 landing in the window whatever the cause, and the next page then needs two more undrafted boundaries, up to about 8h40m away: read the record of the first boundary after the restart by value before taking the clear as a fix.
5. **One shape pages after a single undrafted boundary.** The scrape target is the same across restarts, so the samples an engine published before a restart stay in the window, and their 0s keep the rule quiet as before; but an engine whose series has no earlier sample in the window, at its first start with this gauge or after more than four and a half hours down, and whose first draft writes a non-`ok` record before its first scrape, holds no 0 sample at all, and the rule fires ten minutes on. Step 1 then shows one non-`ok` record after the start: act on its cause as above; the page clears at the next `ok` boundary.

### Retire when

`zcrypto-engine-exec-boundary-not-drafted` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-venue-concordance-failed"></a>

## zcrypto-venue-concordance-failed — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · venue concordance failed`): `zcrypto_venue_concordance_failures` read above zero on the most recent cycle — a ratified instrument is missing from the venue's loaded instrument set, or its constraints came back absent or unparseable.

### What it means

The executor's basket and what the venue actually reports have diverged for at least one leg: a delisting, a halted instrument, or a change to the constraint schema the parser does not yet handle are the usual causes. The **cycle** is read-only here: venue truth is journaled, never consulted for the boundary's targets or orders, so the failure changes nothing about what the engine computes. **The order path is not.** An armed engine takes the same `venue_state_from_cache` read at intent time and refuses on it — the whole intent with `no venue truth` when that read raises, the leg with `<symbol> is absent from venue truth` when the state does not carry its symbol — so the delisting this alert names stops that leg's orders while the cycle keeps computing as if nothing had changed.

### What to do

1. Read the newest `venue-<HH>.json` on the engine host for the per-leg failure strings — it names which instrument and why.
2. This is read-only observability of the cycle's targets, so nothing here is auto-remediated (no count command: `tests/test_engine_cycle.py::test_targets_are_identical_with_and_without_venue_state` pins the cycle half; `cli/engine/executor.py` refuses the absent leg at intent time). Do not converge on this alone.
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

Nothing fires this. You are reading `docker logs zcrypto-engine` on the engine host, because a reconnect line caught your eye, or because a Kraken outage is in progress and you are deciding whether the engine is making it worse.

### What it means

The engine's Kraken **data** socket is idle by design while disarmed: nothing is subscribed between intents, and the executor subscribes quotes per intent.

The idle timer is off: `cli/engine/node.py::_data_client_config` sets `ws_idle_timeout_ms=0` by design<!-- spec 00101 D1 -->, so a quiet socket is never timed out; `docs/reference/fleet-pins.md`'s engine row records which revision is deployed. The lines mean:

- **`Read idle timeout: no data received for 10.0s`**: the timer has been turned back on. That is a config regression, not a venue event: the literal `0` was replaced (writing `None` does it, silently). Nothing to do on the host; fix the config and redeploy.
- **`Reconnecting` → `Reconnect succeeded`**, without a preceding `Read idle timeout` or `Heartbeat timeout` line: a real drop. Read it against `zcrypto_capture_reconnects_total{host="zcrypto"}` on the integrity board's "Capture counters — cumulative since process start" panel: both moving means the venue or the host's network moved; the engine alone moving is the engine's problem. The executor's re-read pass follows on its next tick with nothing in flight: it re-reads at the venue each order whose terminal it minted during the drop and cancels what still rests, logging `re-cancelled … after a terminal this engine minted` — the executor's line, the `zcrypto` logger's, reaches Loki where the socket lines above do not; drill F2's procedure reads it.
- **`Heartbeat timeout: no frame received for 90.0s`**: a dead peer, caught by the heartbeat at three intervals. Expect a reconnect to follow.

None of these lines reaches Loki (the engine ships only the `zcrypto` logger), so `docker logs` on the host is the only place they can be read.

**Why the socket's behaviour is capture's problem.** Kraken's edge rate-limits connection attempts to ~150 per rolling 10 minutes per IP and bans the IP for 10 minutes on breach. `ws.kraken.com`, `ws-auth.kraken.com` and `api.kraken.com` resolve to the same edge, and the engine host is the L2 capture primary. A retry storm from the engine's two sockets can take the capture daemon's ability to reconnect with it, and L2 is unbackfillable. The engine's backoff has no knob and crosses that limit about six minutes into a fast-failing outage.

### What to do

- **A Kraken outage in progress and both engine sockets retrying** (`Reconnecting` lines every few seconds, `Reconnect attempt N failed`): **stop the engine** before the retry count nears 150 in ten minutes — the executor's idle gate refresh adds a `SystemStatus` GET a minute against the same edge, up to five connection attempts each in a fast-failing outage, one per resolved address of `api.kraken.com`, which the `Reconnecting` count does not show; and, after a socket's return or a terminal it minted with the sockets up, the executor's re-read pass — a venue read on a client of its own and, for an order still open, a cancel on another, against the same edge, up to three reads per arm, each failed read a `the re-read pass could not read …` line in the engine log, and, on each arm whose reads answered, the population empty or not, a holdings read on a client of its own — three private calls, `TradeVolume` with the instrument listing, `OpenPositions` and `BalanceEx`; an arm whose read failed makes no holdings read. A ban self-renews only while something keeps retrying (no count command: the reconnect cadence is the upstream binary's and the ban the venue's behaviour), so stopping the engine is worth doing after the budget is already breached as well as before. The capture daemon's own reconnect needs the budget more than the disarmed engine does.

  ```bash
  sudo systemctl stop zcrypto-engine     # NOT `docker stop`
  ```

  **`docker stop zcrypto-engine` does not stop the engine.** The unit's `ExecStart` is an attached `docker compose up` with `Restart=always`, `RestartSec=10`: stopping the container makes the compose process return, the unit exit, and systemd start it again ten seconds later, so the retries you were trying to stop resume on their own. `systemctl stop` runs the unit's `ExecStop` (`docker compose down`) and leaves it down.

  **The cost, before you do it:** boundary cycles run at 00/04/08/12/16/20 UTC, and a boundary that passes with no journal artifact zeroes the ratified gate streak. A restart re-runs a missed boundary only within `[B, B+25 min]` and only while that boundary has no `cycle-<HH>.json` *or* `failed-cycle-<HH>.json`. Stopping just after a boundary is nearly free; stopping just before one costs the streak.

  Start it again with `sudo systemctl start zcrypto-engine` once `zcrypto_capture_reconnects_total{host="zcrypto"}` stops moving and no Kraken margin position is open that [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test does not admit, and read the next `cycle-<HH>.json` for `completed_at` inside `[B, B+30 min]` as the all-clear.

- **A single `Reconnecting`/`Reconnect succeeded` pair** with the venue quiet: note it and move on; the heartbeat did its job.

- **Any `Read idle timeout` line at all**: the knob regressed (no count command: `tests/test_engine_node.py` pins `ws_idle_timeout_ms == 0`; the timer is the upstream binary's). Find the change to `cli/engine/node.py::_data_client_config` and redeploy; the builder test that pins it (`test_engine_node.py`) says which value was written.

### Retire when

`ws_idle_timeout_ms=0` is no longer set in `cli/engine/node.py::_data_client_config` (a standing subscription landed and the design's restore rule applied<!-- spec 00101 D5 -->), or the socket lines reach Loki, whichever comes first.

______________________________________________________________________

<a name="zcrypto-engine-cycle-stale"></a>

## zcrypto-engine-cycle-stale — ALERT

### What you are seeing

A **critical** Grafana alert (`Engine · cycles have stopped`): `time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}` above 16500 s (4h35m) for 5 minutes, **or the series is gone entirely**, since `noDataState` is `Alerting`. Panel 11 on the `zcrypto-engine` board is the same number.

16500 is cadence arithmetic, not a generic staleness bar: boundaries are **00/04/08/12/16/20 UTC** and a healthy completion lands inside `[B, B+30 min]`, so the worst legitimate age is 4h30m, reached just before the next cycle lands. Anything past that is a stopped or crash-looping engine, never a slow one.

### What it means

At least one boundary produced **no journal artifact at all**, neither `cycle-<HH>.json` nor `failed-cycle-<HH>.json`. This is not the failed-cycle case: a failed cycle writes its sidecar and still refreshes this gauge, and has its own rule below.

Three shapes produce it, and the order you rule them out matters:

- **The telemetry plane on the primary is dark.** The gauge is seeded at engine startup from the newest journal artifact (falling back to process start), so it is never legitimately absent while the engine runs (no count command: `cli/engine/command.py` sets it from `_seed_cycle_state` at startup); absence means the exporter or the whole plane is gone. `Fleet · Alloy dark — Capture primary` counts the host's series rather than reading this scrape's value, so the two rules do not cover each other.
- **The engine container is stopped or crash-looping.**
- **`run_cycle` raised before journaling the boundary**: a poisoned store, a disk error. The node survives it deliberately and logs `shadow node: run_cycle(<ts>) raised; the boundary stays journal-absent`. The dead-man behaves differently here: a success pings healthchecks.io, a sidecar pings `/fail`, and a *raising* cycle pings **nothing**, so a healthchecks.io alert with no preceding `/fail` reads "the node is up but a cycle raised; suspect the store". A traceback naming a pair, a grid, a bar and a close that is "not a finite positive number" comes from one of three doors: the refresh's own over the store file, when the same traceback names that file and `is not the frame the store readers join`, the sentence that refusal also carries for a stamp off the leg's grid, a null or repeated stamp and a frame whose shape the readers refuse; the same door over the REST fetch, when it names `the REST fetch for <pair>@<grid>` in place of a file, which is a row the venue itself carries and the venue's to answer -- nothing was written, the store is as it was, the next run fetches again, and no store repair or converge reaches it; and the snapshot write, when it names neither, the store readable and the refresh done. Each of the three raises before the boundary is journaled, the boundary's venue record excepted; a re-run refuses the same way at the two doors that read the store, and at the REST door for as long as the venue's answer carries that row -- the REST window reaches 720 bars back, about 120 days on the 4h grid and about two years on the daily -- with no bypass to wave it through, since a door waved through writes into the store the row it refused. The repair for the two doors that read the store is the store's, and on this host it is a re-delivery, not a seed: `zcrypto engine seed` runs on the workstation alone (the image carries no canonical dataset) and over an existing file it replaces a divergent tail inside the REST window and nothing older, so, with the unit still running and nothing on the host touched yet, repair that series in the workstation's `data/engine-store/` first (read the stamp the traceback names; a series moved aside there is re-copied from the canonical and gap-filled from REST by `zcrypto engine seed`, while the newest frozen sibling's last stamp lies inside the 4h REST window of about 120 days, else the next quarterly ingest is minted first; and a seed that refuses naming the REST fetch rather than a file is a row the venue itself carries, the venue's to answer, which writes nothing and which no store repair reaches); then stop the unit and move the store dir aside rather than deleting it (`sudo mv /var/lib/zcrypto-engine/store /var/lib/zcrypto-engine/store.aside-$(date -u +%Y%m%dT%H%MZ)`, beside it under the same owner; unversioned data has no undo, and the host's store is not replicated, so until the purge below the aside dir is the one copy of the pre-repair store, the file the refusal named being what a read of the cause opens), touching nothing else under `/var/lib/zcrypto-engine` (`exec/` stays as it is, so the procedures page's rule for a restored state directory is not entered), then take step 5's attended converge with the engine tag, `-e converge_primary=true`, `-e engine_image_digest=sha256:<digest>` (the full 64-hex value listed under `## Full digests` in `docs/reference/fleet-pins.md`, the one whose first twelve hex are the engine row's digest cell; the row's rollback operand is the previous image, not this one; the role asserts the digest before the store copy, so a converge without it aborts with the unit stopped), `-e cache_proxy_image_digest=sha256:<the running proxy digest>` (`sudo docker inspect --format '{{.Config.Image}}' zcrypto-cache-proxy`, the role's second digest guard) and `-e '{"engine_preflight_override": "<reason>"}'`, with the user's explicit approval asked before the converge (the stopped unit's preview finds the store aside and the preflight refuses on its missing files), inside the inter-cycle gap, with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits, and outside a published Kraken maintenance window checked immediately before (`.claude/rules/fleet-deploys.md`), so the role's copy for an absent store re-delivers it and the play starts the unit itself; before the confirm, read the preview's `engine preflight override — …` line: the repair goes on where the preflight's JSON line fails on `stores_missing` alone — `config` `ok`, `verified` true, `journal` `ok` or `none` — or where the rc is 2 on an image built before the preflight existed, either beside `first-parent merge: True`, and stops at the confirm otherwise, since the one override bypasses each refusal and the approval named the store; after the converge, read its deploy-log row's `preflight`: `rc` 0 with a `line` carrying `"ok": true`, since the real pass delivers the store before the preflight runs, or 2 on an image built before the preflight existed — another answer fails the repair; then take the measurements the converge owes, step 6's all-clear by value the last of them, and purge the aside dir once the refused file has been read — on the host, or copied to the workstation for that read, since the all-clear reads the delivered store and not the aside copy — and that all-clear has landed (`sudo rm -r /var/lib/zcrypto-engine/store.aside-<stamp>`), naming the aside path and the purge in the commit that carries the converge's deploy-log row.

**A missed boundary is not recoverable once B+25 min has passed**, so that UTC day will not be clean and the gate's streak resets at the next day-close.

**And if the engine was armed, a restart does not resume submission on its own**: every engine start writes the restart-hold file, which is cleared only by hand. Read that as a safety property, not a fault.

### What to do

1. **Rule out Alloy-dark FIRST — before touching the engine.** From the workstation:
   ```
   uv run python infra/scripts/grafana-query.py 'count(up{host="zcrypto"}) or on() vector(0)' 'up{job="engine_app",host="zcrypto"}'
   ```
   A `count` of 0, or `(no series)`, means the primary's telemetry plane is dark: follow `Fleet · Alloy dark — Capture primary` and stop here, because every rule scoped to this host is blind (no count command: no entry counts the rules an expr scopes to one host; `infra/grafana/alerts.yaml` holds them). `count` ≥ 1 with `up{job="engine_app"}` at 0 means Alloy is fine and nothing is answering on `127.0.0.1:9102`: the engine container is down. **An empty result is never a zero.**
2. **Read the container, every inspect scoped to one field.** This container carries the live Kraken trade key in its environment; an unscoped inspect prints it (set: the non-comment lines of the non-Markdown files under `infra/`, `.claude/`, `cli/` — the roles, templates, units, hooks and scripts a command runs from — with the counter itself excluded; the Markdown runbooks and skills, where the form appears as the prohibition's own text, are outside it; count: `infra/scripts/count-list.sh engine-env-forms-invoked`).
   ```
   ssh zcrypto
   sudo systemctl status zcrypto-engine --no-pager
   sudo docker inspect --format '{{.State.Status}} started={{.State.StartedAt}} restarts={{.RestartCount}}' zcrypto-engine
   sudo docker logs --since 6h zcrypto-engine | grep -E 'shadow node|run_cycle|Traceback|ERROR|CRITICAL' | tail -40
   ```
   Never `{{json .Config}}`, never `{{json .Config.Env}}`, never `docker exec … env`, never `docker compose config`.
3. **Read the journal artifacts for how far the last boundary got.** `<HH>` is the boundary, never the wall-clock hour (no count command: `cli/engine/cycle.py` names each artifact from `cycle_ts`, the boundary).
   ```
   sudo ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/
   sudo ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/snapshots/
   ```
   A boundary with `snapshots/cycle-<HH>/` but no record raised **after** snapshotting (store or model side); a boundary with no `snapshots/cycle-<HH>/` of its own (the day's `snapshots/` holds the earlier boundaries') raised before its first snapshot file: a store the reader fails to open, a config fault, the refresh's own door refusing the store file or the REST fetch it merges -- the traceback naming that file, or `the REST fetch for <pair>@<grid>` in place of one, with `is not the frame the store readers join` -- or the snapshot write refusing a close the store holds at a present stamp, which the traceback step 2 greps names with its pair, grid, bar and value (the third bullet under *What it means* reads the three and holds the repair for each). A `failed-cycle-<HH>.json` present means this is not your alert: go to the failed-cycle section below.
4. **Restart only if the unit is down or the process is wedged, and only inside the inter-cycle gap, with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits.** A unit that keeps restarting into `Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` is failing on a position the cache never saw, and a restart repeats the failure: the restart rule says how to end it; one restarting into `failed to create cache database backing` is failing on its cache proxy routing no backend, and a restart repeats that too — [`cache.md#zcrypto-cache-proxy-no-backend`](cache.md#zcrypto-cache-proxy-no-backend) is the incident, and `-e engine_cache_enabled=false` on a re-converge with the running digests is the start without the cache. Nothing refuses a hand restart, so the reading is yours: the boundaries are 4-hourly from 00 UTC, the gap opens 5 min past the boundary cycle's journalled `completed_at` -- later than B+30 min when that cycle ran long, and B+30 min only when the journal is unreadable -- and closes 15 min before the next boundary, so `date -u` alone does not say the gap is open; read the boundary's `cycle-<HH>.json` for `completed_at` first (set: deploy-log rows whose `tags` include `engine`, or `cache-link` with a `limit` reaching an `engine_host` member (an empty `limit` reaches every host), since the last refine round closed for the first count; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`, and count: `infra/scripts/count-list.sh engine-rows-on-the-completion-floor` for the successful rows short of B+30 min that carry no `window` record of the floor the play admitted them on, whose admission the log can only infer, a number to watch; whether the unit is down or wedged, and whether a margin position is open, are operator reads nothing records).
   ```
   sudo systemctl restart zcrypto-engine
   ```
   **`docker stop zcrypto-engine` does not stop the engine**: the unit is an attached `docker compose up` with `Restart=always`/`RestartSec=10`, so systemd brings it back ten seconds later; [`engine-data-socket-idle`](#engine-data-socket-idle) has the full treatment and the outage-time reasoning. If now is still within `[B, B+25 min]` and that boundary has no artifact, the restarted node re-runs it by itself; past that nothing catches up, and a `cycle --at` for a lapsed boundary lands outside the 30-minute window, so the day stays unclean either way.
5. **A converge is a separate, attended decision** (`.claude/rules/fleet-deploys.md`): the engine play needs `-e converge_primary=true` and re-asserts the inter-cycle window, and it restarts the live trade engine, so it waits while a Kraken margin position is open that [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test does not admit. Never run `site.yml` un-tagged on the primary (set: deploy-log rows with `limit == "zcrypto"`; count: `infra/scripts/count-list.sh un-tagged-primary-runs`).
6. **All-clear by value**: the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and `uv run python infra/scripts/grafana-query.py 'time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}'` drops below 1800.

### Retire when

`zcrypto-engine-cycle-stale` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_engine_cycle_completed_at_seconds` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`).

______________________________________________________________________

<a name="zcrypto-engine-dark-with-exposure"></a>

## zcrypto-engine-dark-with-exposure — ALERT

### What you are seeing

A **critical** Grafana alert (`Engine · position open at last report and the engine is not reporting`). Two halves, both scoped to the capture primary, and the alert fires only when both hold for 10 minutes:

- **`$A`**: `max(abs(last_over_time(zcrypto_exec_position{host="zcrypto"}[24h]))) or on() vector(0)`, the largest exposure across symbols **at last sight**, over a 24 h lookback. The value on the page is this number, in base units.
- **`$B`**: `min(up{job="engine_app",host="zcrypto"}) or on() vector(0)`, the engine scrape's **value**, not its presence. `engine_app` is a static scrape target, so the `up` series stays present reading 0 when the container dies.

Panel 64 on the `zcrypto-engine` board (`Position by symbol (base units)`) is `$A`'s own series.

The two ways `$B` reaches 0 arrive on different clocks: a dead container at the 60 s scrape interval, a dark Alloy only once the fallback's series goes stale. So the page arriving means the exposure has already been unwatched for something over ten minutes, plus however long the phone sat unread. Step 1 tells you which.

### What it means

**Two routes reach this page, and one of them is a HEALTHY engine.** Telling the routes apart is the first thing you do, not something the rule did for you.

- **The exporter route.** Nothing answers on the engine's metrics port with a position open at its last report. Usually the container is stopped, crash-looping or wedged, the fault the rule exists for; but the exporter is an in-process HTTP server, so a dead metrics thread on an otherwise live, trading engine looks identical from here. Step 2 below is what tells them apart, and it is not optional.
- **The Alloy route.** The capture primary's telemetry plane is dark. The engine is running, may still be trading, and may already have closed the position; you cannot see it (no count command: the position reaches Grafana through `config.alloy`'s `engine_app` scrape alone). Closing a live position here pays spread and fees for a telemetry incident.

**A resolve is not an all-clear.** The 24 h lookback is also this page's horizon: `$A` falls to 0 when the last position reading ages out of it, and the alert clears, while the engine may still be dark and the position still open. It is sized to outlast a full daily ops pass for exactly that reason. If this cleared without you acting, the exposure is still there.

**Dust is not a position.** The gauge carries Kraken's own holdings, and Kraken pays rewards on spot holdings (`docs/reference/kraken-fee-schedule.md`): on 2026-10-01 the reward on a lot held for five minutes left 1.2e-08 SOL at Kraken, which the gauge read as 1e-08, on an account flat apart from such dust once the day's lot was sold. The condition's floor of `0.000001` base units sits under each basket leg's `ordermin` — the smallest is BTC/EUR's 0.00005, in `docs/reference/kraken-snapshot-register.md` — so a reading of that size does not arm this page, while a lot an order can place does. A leg above the floor and under its own `ordermin` — rewards accrued on a lot held for weeks, what a partial sell leaves — does arm it, and is dust all the same: no order can sell it, and it is not flattened. Step 4 is where you tell a lot from dust.

**`zcrypto-engine-cycle-stale` normally fires alongside this one**, and on the same fault. That rule pages on any engine darkness; this one adds *and there is money exposed*, which is what changes the response.

### What to do

1. **Rule out the telemetry plane FIRST — before touching the position.** From the workstation:
   ```
   uv run python infra/scripts/grafana-query.py 'count(up{host="zcrypto"}) or on() vector(0)' 'up{job="engine_app",host="zcrypto"}' 'max(abs(last_over_time(zcrypto_exec_position{host="zcrypto"}[24h])))'
   ```
   `count` ≥ 1 with `up{job="engine_app"}` at 0 ⇒ Alloy is fine and nothing is answering on `127.0.0.1:9102`: the **exporter route**, and `Fleet · Alloy dark — Capture primary` is quiet. A `count` of 0, or `(no series)`, ⇒ the **Alloy route**, and that rule is firing beside this one. **An empty result is never a zero** (no count command: `infra/scripts/grafana-query.py:60` prints `(no series)` for an empty result, not a zero).
2. **Read the engine on the host — on BOTH routes, and before touching the position.** Step 1 names the route; it does not establish that the engine is dark, and neither route's answer is sufficient on its own. On the **exporter** route, `up{job="engine_app"}` at 0 proves only that nothing answers on `127.0.0.1:9102`: the exporter is an **in-process HTTP server**, so a dead metrics thread leaves a live engine trading on. On the **Alloy** route, the discriminator cannot separate a dark plane from a dead host, because both remove the series (no count command: `cli/obs/metrics.py` serves the exporter in-process; the host's series ride Alloy alone).
   ```
   ssh zcrypto
   sudo docker ps --filter name=zcrypto-engine
   sudo docker exec zcrypto-engine zcrypto engine exec-status
   ```
   A running container that answers `exec-status` ⇒ the engine process is there and its gate state is readable, so **the position stands and step 3 does not apply**, whichever route step 1 named. On the Alloy route that is a telemetry incident: follow [`observability.md#zcrypto-alloy-dark-capture-primary`](observability.md#zcrypto-alloy-dark-capture-primary) and stop here. On the exporter route it is the metrics thread that died, not the engine: treat it as engine liveness and read the journal artifacts and container logs through [`#zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) steps 2–4, which own the restart cadence. **`ssh` failing, the container gone, or `exec-status` not answering is what "confirmed dark" means** and is the only path into step 3.
3. **Only once the engine is confirmed dark, and step 4's read has shown a leg an order can sell**, the response is [`drills-order-path.md#drill-b`](drills-order-path.md#drill-b), the flatten procedure: the kill file first, then every resting order cancelled account-wide and the position closed (no count command: the decision is an operator action nothing records; `cli/engine/flatten.py`'s sweep cancels account-wide). It is a separate attended procedure with its own decision-to-flat measurement; it is not part of this page. **Its exit 0 is not proof the book is clear**: confirming open orders on Kraken's own page is a step of the procedure, not a courtesy ([`engine-procedures.md#flat-verdict-reads`](engine-procedures.md#flat-verdict-reads)). That drill also records that closing the position does **not** clear this page while the engine is still dark.
4. **Read what the position actually was before acting on it.** `$A` is the largest absolute leg at last sight; the per-symbol breakdown is panel 64 and the engine's exec ledger on the host. On the exporter route the ledger is authoritative: the gauge stopped at the moment the exporter did. A spot leg under its `ordermin` — the `Ordermin` column of `docs/reference/kraken-snapshot-register.md` — is dust: no order can sell it, and the flatten lists it as `dust_below_venue_minimum` and sends nothing for it. Where each leg on the panel is dust, what is left of this page is engine liveness, which is [`#zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale)'s.
5. **All-clear by value**, not by the alert clearing: `uv run python infra/scripts/grafana-query.py 'up{job="engine_app",host="zcrypto"}' 'max(abs(last_over_time(zcrypto_exec_position{host="zcrypto"}[24h])))'` with `up` back at 1, and the position reading whatever you intended to leave it at.

### Retire when

`zcrypto-engine-dark-with-exposure` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_exec_position` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`), or `engine_app` stops being a static scrape target there: the value read in `$B` exists because nothing removes that target when the container stops.

______________________________________________________________________

<a name="zcrypto-engine-cycle-failed"></a>

## zcrypto-engine-cycle-failed — ALERT

### What you are seeing

A **warning** Grafana alert (`Engine · the last cycle failed`): `zcrypto_engine_cycle_success{host="zcrypto"}` reads 0, with `for: 0s`, so the outcome is already final the instant the gauge reads 0 and there is no pending period to wait through. Panel 12 on the `zcrypto-engine` board is the same gauge, titled so that an **absent** series reads as "no outcome known yet", not as failure.

The gauge stays 0 until a later boundary succeeds, up to 4 hours away. One event, not a condition worsening.

### What it means

The cycle reached a controlled failure path and recorded it as `failed-cycle-<HH>.json` beside the day's records. The sidecar names the reason, and there are exactly two:

- **`refresh_deadline`**: the store's settle-verify refresh could not complete inside the 25-minute reserve after the boundary. Usually the venue's OHLC fetch or the transport under it.
- **`stale_pair`**: one or more pairs' raw series were stale against the boundary invariant, so the build was skipped. The sidecar's `offending_pairs` names them.

The engine is alive: a failed cycle still refreshes `zcrypto_engine_cycle_completed_at_seconds`, which is why the staleness rule cannot see this.

**A re-run cannot make the day clean.** The engine never re-runs a boundary that already has any artifact (`startup_action` refuses on the artifact's existence, independently of the `[B, B+25 min]` window), so no automatic retry is coming. The only re-run path is `zcrypto engine cycle --at <boundary> --replace`, and its record's `completed_at` will sit outside `[B, B+30 min]`, which the gate scores as a late cycle and fails anyway. So the clean-day streak for that UTC day is already gone; re-run only when the boundary's **targets** matter to something downstream, never to repair the score.

The failure logs at WARNING (`run_cycle: <ts> failed (<reason>: <pairs>); sidecar at …`), so it does **not** page `Engine · ERROR logs`; the healthchecks.io check took a `/fail` ping.

One nuance before you chase a fresh failure: the gauge is also **seeded at engine startup** from the newest journal artifact, sidecars included. A restart taken while the newest artifact is a failed cycle re-publishes 0 and re-arms this page with nothing new having failed. Check the sidecar's `cycle_ts` against the container's `StartedAt` before treating it as a new event.

### What to do

1. **Read the sidecar.** Fields are `cycle_ts`, `attempted_at`, `completed_at`, `reason`, `offending_pairs`.
   ```
   ssh zcrypto
   sudo sh -c 'cat /var/lib/zcrypto-engine/journal/$(date -u +%F)/failed-cycle-*.json'
   ```
2. **Read the boundary's own log lines**: `sudo docker logs --since 5h zcrypto-engine | grep -E 'run_cycle|refresh|stale' | tail -40`. A `refresh_deadline` alongside Kraken REST trouble is a venue event: check `https://status.kraken.com` and the capture side's venue-status signal before suspecting the engine. A `stale_pair` naming one pair while everything else is fresh is that pair's feed: check the corporate-action ledger in `docs/reference/` for a symbol change or delisting.
3. **Nothing needs restarting.** The engine attempts the next boundary on its own. A restart here buys nothing and costs the restart hold.
4. **If, and only if, the boundary's targets are needed downstream** (no count command: a re-run is an operator action nothing in the tree records), re-run it attended, inside the inter-cycle gap (`date -u` first; boundaries 00/04/08/12/16/20 UTC):
   ```
   sudo docker exec zcrypto-engine zcrypto engine cycle --at <YYYY-MM-DDTHH:00:00+00:00> --replace
   ```
   Never `--replace` a boundary that carries a success record; that destroys journaled evidence the gate scores.
5. **The same reason at consecutive boundaries is a store or feed problem, not four accidents.** Check the store's freshness (`sudo ls -l /var/lib/zcrypto-engine/store/`) and the capture primary's own health; the engine reads the venue through the same host. A store data-integrity failure has its own documented recovery, an attended action and not a per-cycle retry: on this host the store's re-delivery, the third *What it means* bullet of the cycle-stale section above; `zcrypto engine seed` is the workstation's command.
6. **All-clear by value**: `uv run python infra/scripts/grafana-query.py 'zcrypto_engine_cycle_success{host="zcrypto"}'` reads 1 after the next boundary.

### Retire when

`zcrypto-engine-cycle-failed` is absent from `infra/grafana/alerts.yaml`, or `seed_cycle_success` in `cli/engine/command.py` no longer registers `zcrypto_engine_cycle_success`.

______________________________________________________________________

<a name="zcrypto-engine-error-logs"></a>

## zcrypto-engine-error-logs — ALERT

### What you are seeing

A **warning** Grafana alert (`Engine · ERROR logs`) on the `logs` receiver: at least one ERROR or CRITICAL line from the engine on the capture primary in the last 15 minutes. The message text is on the page: up to **five distinct messages**, 200 characters each, one alert instance per distinct line. Zero is the healthy baseline.

Two properties of the page itself: a storm can carry more lines than the five shown, and the `logs` receiver **disables resolve messages**, so log alerts age out rather than resolving and no all-clear ping is coming.

### What it means

Something went wrong **between** boundaries. The cycle rules see only a boundary's final outcome, so key or API failures, store refresh errors, venue-snapshot failures, order-path exceptions, a raising metrics sink and the node's own `shadow node: run_cycle(…) raised` all surface here first, on the host that holds the live Kraken trade key.

Note what does **not** appear here: a controlled cycle failure logs at WARNING, so a `failed-cycle` sidecar never pages this rule. If you are seeing both, they are two findings. Neither do the nautilus library's own `[WARN]`/`[ERROR]` lines (a rejected order, a failed reconciliation, a lost venue socket): they ship under `container="engine-nautilus"`, which this rule does not select. Read them beside the engine's records whenever an execution-path error is on the page.

### What to do

1. **Read the full lines, not the 200-character hoist.** The `Logs` panel on the `zcrypto-logs` board with the container filter at `engine` and `engine-nautilus`, or on the host `sudo docker logs --since 30m zcrypto-engine | tail -80`, where both writers and the tracebacks share one stream. Count a storm before calling it five errors: `sum(count_over_time({host="zcrypto", container="engine", level=~"ERROR|CRITICAL"}[15m]))`.
2. **Classify by message, and act on the class:**
   - **`shadow node: run_cycle(…) raised`**: a boundary is being lost right now with no artifact written. Go to [`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) step 3 immediately, well before its 4h35m bar can fire.
   - **`shadow node: snapshot_fn() raised`**: venue truth only. The cycle proceeds with `venue_state=None` by design; this cannot cost a boundary (no count command: `cli/engine/node.py::_invoke_cycle` catches it and still runs the cycle). Read it beside [`zcrypto-venue-snapshot-stale`](#zcrypto-venue-snapshot-stale) and [`zcrypto-venue-concordance-failed`](#zcrypto-venue-concordance-failed).
   - **`metrics sink raised …`**: the record and its artifact were already written before the sink ran, so nothing about the cycle is in doubt, though the sink writes the boundary's `exec-<HH>.json` first and a raise there costs that ledger record (no count command: `cli/engine/command.py::_make_exec_sink` writes it before the gauges).
   - **`cancel of adopted order … was REJECTED by the venue`**: the venue refused the startup pass's, or a kill trip's, cancel of an order this process adopted, and the cancel is not re-sent; its intent, where the pass wrote it, reads `revoked` already, and the order may still rest; absent from Kraken's open orders, the venue had already ended it. Cancel it by hand on Kraken's open-orders page where it rests, and read the row's `filled_qty` for what filled before that; no disarm is owed for this line alone (no count command: the line is `_venue_terminal_state`'s in `cli/engine/executor.py`, and the venue's refusal is the venue's act).
   - **`the re-read pass could not read the ledger or the venue on 3 ticks …`**, **`the re-read pass's cancel of … raised or was refused`** or **`the re-cancel of … could not be journaled`**: the executor's re-read pass — run on its next tick with nothing in flight after a socket's return, or after a terminal it minted with no socket held down — re-reads at the venue each row it minted terminal and cancels what still rests, and could not read on three ticks or could not cancel; the order may still rest at Kraken, its row open — `ambiguous`, or `accepted` where the mint landed after the ack deadline stranded the intent. Cancel it by hand on Kraken's open-orders page; a restart — inside the inter-cycle gap and with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits — has its startup pass read the row too (the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names the window). The third line is the pass's cancel returning and the row write after it failing: the order is cancelled at Kraken and its row still open; read the row against Kraken's closed orders, and the pass's next arm or a startup inside the re-attach window settles it. The read's line names each row it could not read for, `<id> (Kraken <txid>)`, and names none when the ledger itself could not be read: the open row's txid is then in the probe window's ledger read. The sweep's other CRITICAL lines, which the pass shares with the startup — an order the venue read has none for, logged once by the pass and on every startup inside the window, a row that could not be reconciled or journaled, a trip — take the execution-path class below. A row the pass did close reads `canceled` with a `recancelled` event, and is read against Kraken's closed orders and positions: the cancel's answer is not read, so a fill between the pass's read and its cancel reaches the row when the stream delivers it, credited with what the Cache holds beyond the row, less than the fill where the cut's own fills did not reach the stream — on an order the startup pass adopted it can then complete the row `filled` — and is on Kraken's page alone when it does not. No disarm is owed for these lines alone (no count command: the lines are `_reread_pass`'s and `_recancel`'s in `cli/engine/executor.py`, and the venue's answer is the venue's act).
   - **`the execution watchdog froze the loop -- socket … down past the 30s grace …`**: the watchdog's freeze, which lifts by itself, `the execution watchdog's freeze lifted …` in the log; [`zcrypto-engine-exec-watchdog-frozen`](#zcrypto-engine-exec-watchdog-frozen) is the section, its rule paging after fifteen minutes frozen. No disarm is owed for this line alone (no count command: the line is `_watch_sockets`'s in `cli/engine/executor.py`, and a cut is the network's act).
   - **`the re-read pass could not read the venue's holdings on 3 ticks …`**: the position gauge keeps its last reading; where the line closes `and the execution watchdog's freeze stands`, [`zcrypto-engine-exec-watchdog-frozen`](#zcrypto-engine-exec-watchdog-frozen) step 3 reads it. No disarm is owed for this line alone (no count command: the line is `_reread_pass`'s in `cli/engine/executor.py`, and the venue's answer is the venue's act).
   - **`RuntimeError: failed to create cache database backing`** under `unhandled exception -- aborting`: the node's `run()` could not open its cache backing — the cache proxy routing no backend, or the set unreachable — and the unit restarts into the same failure ten seconds on, so no start succeeds until the route is back: [`cache.md#zcrypto-cache-proxy-no-backend`](cache.md#zcrypto-cache-proxy-no-backend) is the incident, and an engine that must run before then takes a re-converge with the running digests and `-e engine_cache_enabled=false`, a start without the cache (no count command: the raise is the library's, logged by `cli/__main__.py`'s catch-all).
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
3. **An execution-path error while ARMED is a live money situation.** Read the gate on the host, which prints `reasons` live; it never reaches a gauge, and `zcrypto_exec_armed` conflates the two arming keys into one gauge (no count command: `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons` and ANDs the two keys):
   ```
   sudo docker exec zcrypto-engine zcrypto engine exec-status
   ```
   It prints `level=<none|reduce_only|full>`, a `reasons=` line (`-` means none), then every gate input. **If it reads `level=full`, or anything other than `level=none`, and you do not understand the error, disarm.** Per the arm/disarm procedure in [`engine-procedures.md`](engine-procedures.md#engine-probe-window):
   ```
   sudo rm /var/lib/zcrypto-engine/exec/armed
   ```
   That disarms immediately (no deploy, no restart, no engine downtime) and the gate then reads `level=none`, `reasons=arm_file_absent`. **Removing the arm file is only the first key.** In a probe window the deployed config still says armed until `exec_armed` is converged back to `false`, which [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) requires the same day; do the converge as that procedure describes, inside the inter-cycle gap. Under rung 3's continuous arming the removal is a pause and the config stays armed: [`engine-procedures.md#rung-3-pause`](engine-procedures.md#rung-3-pause), the resume on the owner's word once the error is understood.
4. **Then reconcile what actually happened at the venue**: the exec ledger's `exec-<HH>.json` records for every boundary the window spans (the ledger read in `engine-procedures.md` prints them by value), and `zcrypto_exec_orders_total{outcome="submitted"}` on the Engine board as the fast read (no count command: a reconciliation is an operator action nothing records). The ledger is the authority.
5. **Do not restart on an ERROR line alone.** Restart only when the node loop itself is wedged (no completion at the next boundary), and then only inside the inter-cycle gap and with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits (set: deploy-log rows whose `tags` include `engine`, or `cache-link` with a `limit` reaching an `engine_host` member (an empty `limit` reaches every host), since the last refine round closed; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`; whether the loop is wedged, and whether a margin position is open, are operator reads nothing records).
6. **The same message every boundary is a defect, not an incident to re-triage.** Capture the message and put the work where work lives; this runbook is not the backlog (no count command: the classification is an operator judgement nothing records).

### Retire when

`zcrypto-engine-error-logs` is absent from `infra/grafana/alerts.yaml`, or the engine no longer ships as `container="engine"` (`ZCRYPTO_LOG_SERVICE` in `infra/ansible/roles/engine/templates/compose.yaml.j2`).

______________________________________________________________________

<a name="zcrypto-engine-log-dead"></a>

## zcrypto-engine-log-dead — ALERT

### What you are seeing

A **critical** Grafana alert (`Engine · log pipeline dead`) on the `metrics` receiver: Loki holds **not one line of any level** from `{host="zcrypto", container="engine"}` in the last 6 hours. Panel 103 on the `zcrypto-logs` board carries the count; read it against the threshold of 1, not against its height.

### What it means

**The title names only one of the two states this can be, and the phone shows the title first.** Separate them with the cycle age before doing anything else.

- **The log plane is dead while the engine is fine.** Then `Engine · ERROR logs` is blind, the only rule paging on ERROR lines from the process holding the live trade key sees nothing, until this is fixed (no count command: it is the one `infra/grafana/alerts.yaml` rule selecting the engine's `ERROR|CRITICAL` level).
- **The engine missed a cycle.** The engine is a **burst emitter**: a burst of lines around each 4-hourly boundary and nothing between, so a missed burst empties the window, and `Engine · cycles have stopped` will already have fired on the same fault.

### What to do

1. **Which state? Read the cycle age and the shipper's own gauges together**, from the workstation. **Scope the logship series by `job`**: the capture daemon and the engine both publish them on this host and both carry `host="zcrypto"`, so an unscoped query returns two series and answers about the wrong process:
   ```
   uv run python infra/scripts/grafana-query.py \
     'time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}' \
     'time() - zcrypto_logship_last_cycle_timestamp_seconds{job="engine_app",host="zcrypto"}' \
     'increase(zcrypto_logship_dropped_lines_total{job="engine_app",host="zcrypto"}[6h])'
   ```
   Cycle age above 16500 ⇒ the **engine**: follow [`zcrypto-engine-cycle-stale`](#zcrypto-engine-cycle-stale) and expect this page to clear at the next boundary's burst. Cycle age healthy ⇒ the **log plane**; continue below. `(no series)` on the cycle age is itself the finding: the telemetry plane is dark, not quiet.
2. **Read the two shipper gauges as the two questions they are.** `zcrypto_logship_last_cycle_timestamp_seconds` is liveness: the worker advances it on an idle cycle too, and it stalls only while the worker is stuck retrying or wedged. `zcrypto_logship_dropped_lines_total` is delivery: a permanently rejected batch (a revoked token, a wrong path) still completes a cycle and still advances the liveness gauge, so credential failures show up **only** as dropped lines (no count command: `tests/test_logging_ship_handler.py`'s last-cycle and rejected-batch tests hold both gauges). **Do not use `zcrypto_logship_last_success_timestamp_seconds` for liveness**: it goes stale whenever logging is merely quiet, and it is absent entirely until the first successful ship.
3. **On the host, prove which half is broken:**
   ```
   ssh zcrypto
   sudo docker logs --since 6h zcrypto-engine | wc -l
   sudo docker logs --since 6h zcrypto-engine | grep -iE 'ship|loki|401|403|timeout' | tail
   ```
   A non-zero count means the process is logging and the shipper is what failed; the ship handler's own failures are visible locally only (no count command: the ship handler hands its own failures to `logging.Handler.handleError` at `cli/logging/ship.py:118`, whose stderr write is the stdlib's and reaches no shipper). **Print that count before trusting any conclusion drawn from an empty grep.**
4. **Check whether capture went dark with it.** Both `zcrypto-capture-log-dead-primary` and this rule firing ⇒ the host's push path or Grafana Cloud, not the engine; the two services read Loki creds from the same rendered file. Engine alone ⇒ the engine container or its env.
5. **A credential fix is a converge, never a hand edit**: the engine's Loki env comes from the render, and the file is read at container create, so a rotated token needs the role's converge. That is attended, needs `-e converge_primary=true`, and runs inside the inter-cycle gap only, with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits (set: deploy-log rows whose `tags` include `engine`, or `cache-link` with a `limit` reaching an `engine_host` member (an empty `limit` reaches every host), since the last refine round closed; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`; a hand edit is an operator action nothing records, and whether a margin position is open an operator read nothing records).
6. **All-clear by value**: after the next boundary's burst, the rule's own query returns a count above 0, the threshold being `< 1`: `sum by (host) (count_over_time({host="zcrypto", container="engine", level=~".+"} [6h]))`. Confirm the number; an empty result is not a zero.

### Retire when

`zcrypto-engine-log-dead` is absent from `infra/grafana/alerts.yaml`, or the engine no longer ships as `container="engine"` (`ZCRYPTO_LOG_SERVICE` in `infra/ansible/roles/engine/templates/compose.yaml.j2`). The 6 h window is derived from the 4-hourly loop, not copied from the other log canaries; it changes only when that cadence does.
