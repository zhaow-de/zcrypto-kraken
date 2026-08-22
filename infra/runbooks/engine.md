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
3. **Re-derive the numbers that were sized against the old composition** before the next go-live decision reads them: the model-consistency band the gate compares realized performance against, and the expected order notionals versus the venue minimums. Both were derived under the previous sleeve count and neither updates itself.
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

<a name="engine-probe-window"></a>

## engine-probe-window — PROCEDURE

### What you are seeing

You are about to run — or are in the middle of — an attended live-order probe window on the engine. **Nothing has fired**: no alert sent you here and no guard tripped. You opened this because a probe window is being planned or is under way, and this is the only sanctioned way to run one.

Real money moves — roughly €10–30 per leg — on the host that holds the live trade key.

### What it means

The engine's order path submits **only operator-authored probe plans**, and only inside an attended window bounded by two arming keys: the `exec_armed` value baked into the deployed config, and an `armed` file placed on the engine host. Both must be present for anything to be submitted; removing either one disarms it. Every step below exists because its omission has a named failure, and where a step's *position* in the sequence matters, the step says what happens if you take it early — that ordering is load-bearing, not ceremonial.

Where everything lives — never guess these:

- **Engine host** `zcrypto` (`ssh zcrypto`); the container is `zcrypto-engine`; the CLI and the rendered config live inside it.
- **Control files**: `/var/lib/zcrypto-engine/exec/` — `armed`, `kill`, `restart-hold`, and the plan file `probe-plan.json`. Presence is the whole protocol; contents are informational.
- **Journal**: `/var/lib/zcrypto-engine/journal/<YYYY-MM-DD>/` — `cycle-<HH>.json`, `exec-<HH>.json`, `venue-<HH>.json`.
- **`<HH>` is the 4-hourly cycle boundary** (00/04/08/12/16/20 UTC), never the wall-clock hour. A record written at 09:14 UTC is `…-08.json`.
- **Rendered config**: `/opt/zcrypto-engine/zcrypto.toml`, rendered by the deploy from `infra/ansible/roles/engine/templates/zcrypto.toml.j2`. Never hand-edit it on the host; the next converge overwrites it.

Three reads you will use repeatedly. **Scope every `docker inspect` to one field with `--format`** — this container carries the live trade key in its environment, and an unscoped inspect prints it.

**The gate read** — run it in the container, which is where the CLI and the config are:

```
sudo docker exec zcrypto-engine zcrypto engine exec-status
```

It prints `level=<none|reduce_only|full>`, then a `reasons=` line carrying every condition that restricted the level, comma-separated — a single `-` means none — then every gate input on its own line. It re-evaluates the gate on the spot, and it is the only **live** view of the reasons — they never reach Grafana, and `zcrypto_exec_armed` conflates the two arming keys into one gauge, so no dashboard can tell you which key is missing. The reasons of *past* evaluations are journaled into the execution record, which the ledger read below prints; what you cannot get anywhere but here is the reading for right now.

**The ledger read** — always by value, never by presence, and over **every** record the window spans. There is one execution record per 4-hourly boundary, so a window that crosses a boundary keeps writing into a new file: reading only the newest one goes blind to everything before the crossing, and a terminal-state check run against it would pass on rows it never looked at. `HOURS` is the knob — set it to cover the whole window, and widen it rather than trust an empty result.

```
sudo python3 - <<'PY'
import json, pathlib, time
root = pathlib.Path("/var/lib/zcrypto-engine/journal")
HOURS = 24
cutoff = time.time() - HOURS * 3600
paths = sorted(q for q in root.glob("*/exec-*.json") if q.stat().st_mtime >= cutoff)
print(f"{len(paths)} execution record(s) in the last {HOURS}h")
if not paths:
    print("  NOTHING MATCHED -- widen HOURS; an empty read is not a clean window")
for p in paths:
    d = json.loads(p.read_text())
    print(p, "level=", d["level"], "reasons=", d["reasons"])
    for e in d.get("plans", []):
        print(" plan", e["plan_id"], e["disposition"], e["reasons"])
        for i in e["intents"]:
            print("   intent", i["index"], i["outcome"], i["reasons"], "filled_qty", i["filled_qty"])
    for r in d["submitted"]:
        print(" order", r["client_order_id"], r["state"], "filled_qty", r["filled_qty"])
        for ev in r["events"]:
            if ev.get("event") == "fill":
                print("     fill", ev["qty"], "@", ev["px"], "fee", ev["fee"], ev["fee_currency"], ev["liquidity"], ev["trade_id"])
PY
```

**The venue-truth read** — positions, balances and the instrument constraints the engine last saw:

```
sudo python3 - <<'PY'
import json, pathlib
root = pathlib.Path("/var/lib/zcrypto-engine/journal")
p = max(root.glob("*/venue-*.json"), key=lambda q: q.stat().st_mtime)
d = json.loads(p.read_text())
print(p, "status", d["status"])
if d["status"] != "ok":
    print("  error:", d.get("error"))
else:
    print("  snapshot_at:", d["state"]["snapshot_at"])
    print("  positions:", d["state"]["positions"])
    print("  balances:", d["state"]["balances"])
PY
```

### What to do

#### 1. Pre-probe — before anything touches the host

1. **Sweep for blockers, and present the result together with the arming request.** Read `### Open` and `### Partially done` in `docs/open-topics/README.md`, and grep `docs/memo.local.md` for anything in flight against the engine. "Ready" without the sweep is not ready.
2. **Confirm the deployed code is the code you tested.** The engine row in `docs/reference/fleet-pins.md` records the digest running on `zcrypto` and the revision it was built from. Confirm the running digest matches — `sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine` — and that your working tree is at that revision. Then run the two guards that catch a drift between the committed cost floors / ratified basket and what the venue reports: `uv run pytest tests/test_costmin_drift.py tests/test_basket_concordance.py` → expect `2 passed`. A failure means the floors or the basket have moved since that image was built; stop, do not arm.
3. **Confirm funding covers the plan, by hand, before the tooling does it for you.** Take the free EUR balance from the venue-truth read — the live balances spell that key **`EUR`** (measured: `{'EUR': 99.84}`), not `ZEUR`; the engine still tries `ZEUR` first because the adapter's instrument-quote surface does spell the euro that way, so both keys are read and whichever the record carries is used. The plan's total `notional_eur` must be at or under `exec_max_plan_notional_eur` in `/opt/zcrypto-engine/zcrypto.toml` (rendered `100.0`), and `sum(notional ÷ leverage) × 2.5` over the margin intents must fit under that free balance. `probe-plan --check` recomputes both below and refuses on either — this step is so you learn it before the window, not during it.
4. **Only the account owner authors and places a plan.** A plan file the owner did not place does not exist to this process.

#### 2. Arm — two keys, in this order

1. **Read the digest the engine is running**: `sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine`. This converge changes no image — you pass that same digest straight back, so nothing is re-pinned, no secondary bake is owed, and the pins check passes against the row already in `fleet-pins.md`.

2. **Edit one line** in `infra/ansible/roles/engine/templates/zcrypto.toml.j2`: `exec_armed = false` → `exec_armed = true`. There is deliberately **no** `-e` override for this value — arming is a reviewed one-line diff in the repo, not a flag anyone can type on a command line.

3. **Converge, inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC — the play refuses outside it):

   ```
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine \
     -e converge_primary=true \
     -e engine_image_digest=sha256:<the digest from step 1>
   ```

   `converge.sh` runs the `--check --diff` preview first and then takes a typed confirm of the literal string `zcrypto`. **Read the preview**: exactly one line of `/opt/zcrypto-engine/zcrypto.toml` changes, `exec_armed = false` → `exec_armed = true`. Anything else in that diff means your tree does not match the fleet — abort and reconcile the tree first.

4. **The restart latches the reduce-only hold — verify reconciliation before you clear it.** The gate read prints `level=none` and `reasons=arm_file_absent,restart_hold` — those two, in that order. If `config_not_armed` is still in the list the converge did not land the new value; fix that before going on. A third reason `venue_not_online` alongside them is not a fault of this step and not something to fix here: Kraken itself is not `online`, nothing can be submitted until it is, so wait it out and re-read. Then run the venue-truth read and confirm the positions and balances you are starting from — no open positions, EUR only.

   **If the restart left an order resting at the venue, its ledger row is preserved and its later fills still land in it.** The startup pass keeps a resting order only when the ledger carries it as a reduce-only row; that row survives and is re-attached. After a restart the venue's resting order is reconciled under an external identity, and the engine subscribes to that identity's event stream too — matching every event on it against exactly those re-attached rows — so a fill landing on such an order appends to its row, moves the execution counters, and latches the kill switch on an overfill, the same as a fill on an order this process itself submitted. The row is current state, not only a record of what happened before the restart; Kraken's own open-orders and trades views and the next `venue-<HH>.json` are independent corroboration rather than the only place the fill exists.

   **The startup pass also reconciles every preserved row against the venue's own figure, so a row can move before you ever read it.** A fill that lands while the engine is down reaches no handler — the process is not there to hear it — so the pass compares each preserved row against the quantity the venue reports for that order. **Only a venue figure that is HIGHER writes anything into the row**: that difference lands as a `reconciled` event carrying the delta and the venue's total, plus a WARNING log line naming both figures. A difference too small to be real (the two figures are summed differently and can disagree in the last bits) is silent by design, and a venue figure that is *lower* writes no event at all — it is a divergence, not a repair, and it goes straight to the kill switch described below. An order that filled, was canceled or expired while the engine was down is closed at the venue and never appears among the resting orders at all; its row is still found and is given its final state (`filled`, `canceled`, `venue_canceled`, `rejected`) right there at startup, with a `reconciled` event beside it only if the venue also reported more filled than the row had — a cancel with no fills, the commonest case, gets the state write and nothing else. So a row that closes with no event stream behind it is this pass, not something you missed. A repair is **not** counted as a fill: `zcrypto_exec_fills_total` and the fee counter do not move for it, because there is no per-fill detail and no fee behind the venue's aggregate. The row is the record.

   **This is also the one thing that can latch the kill switch at boot, before any plan is picked up.** Two divergences trip it, and they leave different evidence. **The venue reporting more filled than the row was ever submitted for** writes the repair into the row first and latches second, so the row carries a `reconciled` event and the kill file names both quantities. **The ledger claiming more filled than the venue reports** — the dangerous direction, since it means the engine believes it reduced more than it did — writes **nothing** into the row and latches immediately: there is no repair to make, and inventing one would erase the very figure that is in dispute. Do not read an unchanged row as evidence nothing happened; `sudo cat /var/lib/zcrypto-engine/exec/kill` names the order and both quantities in either case, and it is the only place the venue's figure is recorded on that direction. **One false-fire path is worth knowing before you touch a resting order in the Kraken web UI**: `editOrder` is cancel-replace, not an in-place amend — it produces a *different* order, and a replacement echoing the same client order id presents zero fills against a row that has them, which is exactly the ledger-ahead-of-the-venue trip. It would latch at the next restart rather than when you clicked, with nothing in the UI hinting at it, and the row it latched over will look untouched. `amendOrder` is in-place and does not have this shape.

   **An event on that stream belonging to no ledgered row — your own hand settle in the Kraken UI is the one that matters — is counted under `zcrypto_exec_external_events_total{disposition="unmatched"}` and logged, and acted on nowhere**: no row write, no fill or order counter, no cancel, and no fill-time trip. That is the filter working as designed, not a gap. What it does NOT settle is whether a hand settle produces an order event at all: the engine publishes reconciled orders' events unconditionally, but whether Kraken's settle-position act emits one on the adapter's streams has never been measured — so the counter is the instrument that will answer it at the first settle, not the answer. Read it then (**§6 Verify by outcome, item 6** queries it): a rise means the settle reached this process as an order event and was correctly ignored; a flat counter means it did not, which is worth recording either way. It stays clear of the fill-time trips because it matches no ledgered row — which changes nothing about the position-reconciliation trip described under the settle preconditions below, whose input is the venue's position rather than an order event.

5. **The owner clears the hold**: `sudo rm /var/lib/zcrypto-engine/exec/restart-hold`. Gate read → `level=none`, `reasons=arm_file_absent`.

6. **The owner creates the arm file**: `sudo touch /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=full`, `reasons=-`. If `venue_not_online` shows up instead, Kraken itself is not `online` — wait it out, since nothing can be submitted until it is. The engine is now armed, and the `zcrypto-engine-exec-armed-too-long` alert above will page if the window outlives six hours — that is the rule working, not a fault.

#### 3. Drill before money — both drills green before any funded plan

Three plan-file mechanics that apply to **every** plan from here on:

- **A plan expires 60 minutes after its own `created_at`**, which must be a timezone-aware ISO timestamp. Author, check and place inside that hour, or the engine refuses it and journals the refusal.
- **Place a plan by renaming it into position — never by writing it in place.** The executor stats the plan path every 5 seconds and reads whatever is there; a file still being written parses as garbage, is journaled as a refusal, and is **deleted**. A `mv` inside the same directory is atomic, so the executor sees either the whole file or no file.
- **A `plan_id` already in the execution ledger for today or yesterday is refused.** Every plan gets a fresh id.

**Drill A — the rest-cancel drill: the whole machine, zero fills, zero fees.**

1. Author the plan on the workstation. `mode: rest-cancel` prices its order well away from the touch and cancels it the moment the venue acknowledges — a resting, untouched order costs nothing.
   ```json
   {
     "plan_id": "drill-a-2026-08-18",
     "created_at": "2026-08-18T09:05:00+00:00",
     "intents": [
       {"symbol": "BTC/EUR", "side": "buy", "action": "open", "mode": "rest-cancel", "notional_eur": 20.0, "leverage": 2}
     ]
   }
   ```
2. Copy it to the engine host, into the state directory the container also sees, under a **staging** name:
   ```
   scp plan.json zcrypto:/tmp/probe-plan.json
   ssh zcrypto
   sudo install -o zcrypto-engine -g zcrypto-engine -m 0640 /tmp/probe-plan.json /var/lib/zcrypto-engine/exec/probe-plan.staging.json
   rm /tmp/probe-plan.json
   ```
3. Validate it offline — read-only, mutates nothing:
   ```
   sudo docker exec zcrypto-engine zcrypto engine probe-plan /var/lib/zcrypto-engine/exec/probe-plan.staging.json --check
   ```
   Expect the gate verdict, a `venue snapshot: <timestamp>` line, then one line per intent — indented two spaces, `  [0] BTC/EUR buy open rest-cancel: notional 20.00 EUR, costmin <X> EUR` — and a last line `plan ok: 1 intent(s), total notional 20.00 EUR`. Any refusal exits non-zero as `plan refused: <every reason, semicolon-separated>` — fix the plan; do not place it. The check is **advisory**: the engine re-validates every plan live before any order, so a clean check is not a permission.
4. Place it atomically: `sudo mv /var/lib/zcrypto-engine/exec/probe-plan.staging.json /var/lib/zcrypto-engine/exec/probe-plan.json`.
5. Within about five seconds the executor journals the plan and **deletes the file**. Confirm: `sudo ls -l /var/lib/zcrypto-engine/exec/` shows no `probe-plan.json`.
6. Read the ledger by value. Expect the plan entry `accepted` with empty reasons; its intent `outcome rest_cancel_ok` with `filled_qty 0.0`; one order row ending `state canceled` with `filled_qty 0.0` and **no** `fill` lines at all.
7. Read the counters by value from the workstation, allowing a minute for the scrape and remote write:
   ```
   uv run python infra/scripts/grafana-query.py 'zcrypto_exec_orders_total{host="zcrypto"}' 'zcrypto_exec_fills_total{host="zcrypto"}' 'zcrypto_exec_fees_eur_total{host="zcrypto"}'
   ```
   Expect the `submitted`, `accepted` and `canceled` outcomes to have advanced, **every** `zcrypto_exec_fills_total` series still `0`, and `zcrypto_exec_fees_eur_total` still `0`. A number, never `(no series)`.

**Drill B — the disarmed refusal: prove the key actually refuses.**

1. `sudo rm /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=none`, `reasons=arm_file_absent`.
2. Place a second `rest-cancel` plan with a **new** `plan_id`, exactly as in drill A steps 1–5.
3. Expect the plan entry to still read `accepted` — the plan-level checks do not read the gate — and **every intent** to read `outcome refused` with `reasons ['arm_file_absent']`. No order row is created for it, nothing reached the venue, and `zcrypto_exec_orders_total{outcome="refused"}` advances.
4. Re-create the arm file (`sudo touch /var/lib/zcrypto-engine/exec/armed`) and confirm `level=full` before going on.

#### 4. Execute — the funded plans

**Three rules hold for every funded plan below, without exception.**

- **Never drop a funded plan inside the final 60 minutes before a 4-hourly boundary** (00/04/08/12/16/20 UTC). Run `date -u` immediately before placing; if the next boundary is under 60 minutes away, wait for it to pass. The 4-hourly cycle runs synchronously on the node's single event-loop thread and can hold that thread for up to about 25 minutes when a refresh degrades. While it is held no 5-second tick fires, so **none** of the mid-flight revocations — the kill file, a disarm, quote staleness, the intent's own time-box — can act on a resting order. This rule is the only thing keeping a funded order from resting through that window.
- **Every plan is signed off on its own**: the owner reads the `--check` output and personally places the file. Drill plans included.
- **Nothing retries itself.** An intent ending `unfilled`, `refused`, `rejected`, `partial` or `ambiguous` stops there. **`ambiguous` means the order may be live at the venue** — read Kraken's open orders in the web UI and establish what actually reached it before placing anything else on that symbol.

**Step 1 — the open plan, both positions in one plan.** A BTC/EUR margin long and an ETH/EUR margin short, leverage 2, €10–30 each:

```json
{
  "plan_id": "open-2026-08-18",
  "created_at": "2026-08-18T09:35:00+00:00",
  "intents": [
    {"symbol": "BTC/EUR", "side": "buy",  "action": "open", "mode": "execute", "notional_eur": 20.0, "leverage": 2},
    {"symbol": "ETH/EUR", "side": "sell", "action": "open", "mode": "execute", "notional_eur": 20.0, "leverage": 2}
  ]
}
```

The short is on ETH and not on BTC on purpose: an opposing leveraged order on a pair that already holds a margin position **closes** that position instead of opening a second one, so a BTC/EUR short beside the BTC/EUR long would leave you with one position and one rollover stream instead of two.

Monitor with the ledger read (each fill carries `qty`, `px`, `fee`, `fee_currency`, `liquidity`, `trade_id`) and the Engine board's **Execution — what actually happened at the venue** row.

**Step 2 — hold at least about 9 hours.** Rollover recurs every 4 hours a position is open, so ~9 h of wall clock buys two rollover events per position. Confirm both are visible in the Kraken ledger export (Kraken → History → Export → Ledgers) before closing anything.

**Step 3 — the close plan: the ETH/EUR short only, closed by the engine.** One intent, wrapped in the same plan envelope as above (a fresh `plan_id`, a fresh `created_at`, an `intents` list):

```json
{"symbol": "ETH/EUR", "side": "buy", "action": "close", "mode": "execute", "notional_eur": 20.0, "leverage": 2}
```

`notional_eur` on a margin closer is **advisory** — the engine sizes the close from the live position and submits it reduce-only, so the same bound is enforced at both ends. This is the first live use of reduce-only anywhere in this system: a venue rejection halts the intent and surfaces to you, with no retry.

**Step 4 — the settle act: the owner settles the BTC/EUR long by hand in the Kraken web UI, and only when no intent is in flight.**

The engine cannot do this — its adapter has no settle-position order type at all — so this half is yours. Settling in kind repays the borrowed EUR from wallet balance and converts the position into a spot BTC holding; Kraken charges no trade fee on settling in kind.

**Preconditions, and their order is not optional.** Settle only after (a) two rollover events are visible in the ledger export for both positions, and (b) the close intent has reached a **terminal** state in the ledger and no intent is in flight.

**The consequence of settling early — which is why those are preconditions and not advice.** One of the engine's automatic kill trips is deliberately **not** scoped to the engine's own orders: after an intent reaches a terminal state, the executor compares the venue's position in **that intent's instrument** against what its own fills account for, and trips on any difference larger than one lot step. A hand settle is, by construction, position movement the engine's fills do not account for — so a settle landing while an intent on the same symbol is running **can** trip it. It is not a certainty: the comparison is per-instrument, so a settle beside a *different* symbol's intent reaches it not at all, and whether a hand-placed settle propagates into the engine's position view in the first place is itself unproven on the installed adapter. That unpredictability is the point — you cannot reason your way to which side you will land on mid-window. And a trip is not recoverable inside one: the kill file latches, resting orders are canceled, every further intent is refused, the `zcrypto-engine-exec-kill-tripped` alert pages, and nothing continues until a human reads and deletes `/var/lib/zcrypto-engine/exec/kill`. Waiting for the close intent to be terminal with nothing in flight is what removes the question entirely — the preconditions are the protection here, not the trip.

**Step 4b — record whether the settle propagated, before you move on.** The preconditions above route *around* the question of whether a hand-placed settle reaches the engine's position view, deliberately — but the window is the only place it can be observed, and observing it costs one read. After the settle, read the next `venue-<HH>.json`'s `positions` for the settled instrument — that record IS `cache.positions_open`, so it is the one surface that can answer this — and write the verdict into the probe's decisions-log entry alongside the `unmatched` reading from **§6 Verify by outcome, item 6**: propagated, did not, or the record could not tell. Do **not** read `zcrypto_exec_position` for this: that gauge is written only on a fill (plus a startup seed), so between the settle and the disposal it still shows its pre-settle value whether the settle propagated or not, and reading it here would answer "did not propagate" every time. Nothing downstream depends on the answer — that is what the preconditions bought — so a surprising result is information, not a stop.

**Step 5 — read the disposal quantity out of the ledger export.** Export the ledger again after the settle and read the BTC amount the settle credited. That figure — not a balance the engine reports, not an estimate — is the disposal plan's `qty`: whether a hand-placed settle propagates live into the engine's balance view is unproven, and a plan-carried quantity removes the dependency entirely. Floor it to the leg's lot step, which `probe-plan --check` prints; the check refuses a `qty` that is not a multiple of that step, and rounding **up** would put the sell over the balance.

**Step 6 — the disposal plan: the engine sells the residual spot BTC, so the probe ends flat.** Again one intent in its own plan envelope:

```json
{"symbol": "BTC/EUR", "side": "sell", "action": "close", "mode": "execute", "qty": 0.00021}
```

No `leverage` key — its absence is what makes this a spot order — and a spot close carries `qty` instead of `notional_eur`. Same sign-off and the same 60-minute boundary rule as every other funded plan. An over-quantity sell is rejected by the venue and halts attended; a remainder below the leg's `ordermin` is accepted as terminal dust.

**Step 7 — re-sync the tax depot and record the verdict.** After all three terminal acts — the close, the settle, the disposal — re-sync the Kraken depot in Blockpit and record pass/fail in `docs/research/14.phase6-decisions.md` with the evidence: bucket assignment (derivatives PnL vs spot disposal), rollover fees attached as costs, FIFO lots intact, no phantom balances, and the disposal's gain/loss computed off the basis the settle carried.

**On a FAIL, registering the fallback build item is a step of THIS checklist, executed in the same session as the verdict — never a remembered promise.** Open a topic file under `docs/open-topics/` (convention: `.claude/rules/open-topics.md`; file mechanics: the `topic-ops` skill) for the deterministic pre-transform that maps Kraken's ledger and trades exports into Blockpit's manual-import CSV with explicit margin-PnL rows, and queue it in the memo in the same pass — a topic registered but not queued is invisible when work is picked up.

#### 5. Disarm — both keys down, the second one the same day

1. **The owner deletes the arm file**: `sudo rm /var/lib/zcrypto-engine/exec/armed`. This disarms immediately — no deploy, no restart, no engine downtime. Gate read → `level=none`, `reasons=arm_file_absent`.
2. **Converge `exec_armed` back to `false` the same day — not "eventually".** Between deleting the arm file and that converge the deployed config still says armed, so arming is effectively **one** key rather than two: anything that recreates a file at `/var/lib/zcrypto-engine/exec/armed` re-arms the engine with no review and no deploy. Revert the one line in `infra/ansible/roles/engine/templates/zcrypto.toml.j2` and converge with the same command as the arm step (same running digest, same inter-cycle gap). Read the preview: exactly one line changes back.
3. **Confirm both keys are down.** Gate read → `level=none` with `reasons=config_not_armed,arm_file_absent,restart_hold` — three reasons; the restart hold is back because the converge restarted the engine, and that is the correct resting state, so leave it. From the workstation, `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_armed{host="zcrypto"}'` reads `0`.
4. **Treat any restore of the engine state directory as re-arming until proven otherwise.** The arm file and the plan file both live in `/var/lib/zcrypto-engine/exec/`, which sits inside the directory that is also the backup unit — a restore can bring either one back. After **any** restore of `/var/lib/zcrypto-engine`, and **before the engine starts**, list the directory: `sudo ls -la /var/lib/zcrypto-engine/exec/`. Then act **per file, by name** — a restored control file is not automatically debris, and three of them mean three different things:
   - **`armed` and `probe-plan.json` — delete these two if present, and only these two.** They are what a restore re-arms you with. The plan's own 60-minute expiry and the ledger's plan-id dedup are the designed backstops behind this check, not a substitute for running it.
   - **`kill` — this is a FINDING, never something to sweep away.** No code path anywhere clears the kill file; it is a latch a human engaged, and a restore that brings it back is telling you the backup was taken after a trip. `sudo cat /var/lib/zcrypto-engine/exec/kill` prints a timestamp and the reason that tripped it. Read that reason, work the `zcrypto-engine-exec-kill-tripped` section above, and remove the file only once the reason no longer holds. Deleting it along with the rest destroys the one record of why the system stopped, at the moment it is trying to tell you.
   - **`restart-hold` — leave it.** The engine writes one unconditionally at every start anyway, and holding at reduce-only until a human clears it is the correct resting state.

#### 6. Verify by outcome — the window is not closed until every line here reads true

1. **Every intent has a terminal outcome and every order has a terminal state**, from the ledger read: each plan entry `accepted` with empty reasons, each intent carrying an outcome, each order row a terminal `state`.

2. **Every fill carries its fee and its liquidity side**: each `fill` line shows `fee` with a `fee_currency`, and `liquidity` reading the word `maker` or `taker` — never a number.

3. **Two rollover rows per position** in the Kraken ledger export.

4. **The settle and then the disposal are visible in venue truth, read from the venue record written after the disarm converge's restart** — that restart is what forces the fresh account read, and it is the verified path. Take the restart time from `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine`, wait for the next 4-hourly boundary to write its record, then run the venue-truth read and confirm `snapshot_at` is later than that restart time. A record written before the restart is corroboration, never the gate.

5. **The probe ends flat**: that record's `positions` carries **twelve** entries — one per basket leg, always, flat or not — and every one of them reads `0.0`. Count the keys and read the values: an absent key is not the flat state (a leg missing from the map means the snapshot never measured it, which is a fault to chase), and a non-zero value is not flat however small it looks. Its `balances` are EUR only, with any BTC remainder below the leg's `ordermin` (terminal dust, not a position).

6. **The execution families are live in Grafana Cloud, read by value** from the workstation — a number in every case, never `(no series)`:

   ```
   uv run python infra/scripts/grafana-query.py \
     'zcrypto_exec_orders_total{host="zcrypto"}' \
     'zcrypto_exec_fills_total{host="zcrypto"}' \
     'zcrypto_exec_fees_eur_total{host="zcrypto"}' \
     'zcrypto_exec_position{host="zcrypto"}' \
     'zcrypto_exec_realized_pnl_eur{host="zcrypto"}' \
     'zcrypto_exec_external_events_total{host="zcrypto"}'
   ```

   The last one is the only family here whose **zero is a reading rather than a gap**: both dispositions are registered at startup, so `matched` and `unmatched` must both be present, and `(no series)` on it means the capture keep-regex did not ship rather than that nothing happened. Record `unmatched`'s value against the settle taken in step 4 — that is the measurement of whether a hand settle reaches this process as an order event at all.

7. **The verdict is recorded** in `docs/research/14.phase6-decisions.md`, and on a fail its fallback topic is registered and queued — step 7 above.

### Retire when

`cli/engine/executor.py` no longer picks a plan file up out of the state directory's `exec/` — check with `grep -n PLAN_FILENAME cli/engine/executor.py`, and a run that finds nothing is the signal. At that point the continuous loop that replaces attended probe windows has landed, and this procedure with it.
