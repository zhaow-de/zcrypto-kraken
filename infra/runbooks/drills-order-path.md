# Order-path drills — induce the fault where money is at stake

Nothing fires these; you open this page deliberately, inside an attended live-order probe window, to break the order path on purpose and prove that what the engine does next is what an operator can account for. Real money is exposed on every one of them. The telemetry-tier drills — the ones where no money moves — live in [`drills-telemetry.md`](drills-telemetry.md), and the window these are fitted around is [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window).

**Say the letters with the page name attached, because two pages use the same ones.** The probe window carries its own **Drill A** (the rest-cancel drill) and its own **Drill B** (the disarmed refusal), and both are run there, before any funded plan, as part of arming. They are not this page's A1, A2 or B. Nothing collides in a link — the anchors differ — but the letters an operator says out loud do, and "drill B is done" means opposite things on the two pages.

**Every section below is one drill, and every drill has the same seven parts**: *What this proves* · *Preconditions* · *Induce* · *Must fire* · *Operator action* · *Record* · *Retire when*. Read all seven before touching anything: on this page the *Preconditions* are what stand between a drill and a live position nobody planned.

## Standing rules — these bind every section below

- **Every drill here runs inside an attended probe window**, never beside one. The window's pre-probe checklist, its two arming keys and its own two drills come first, in [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window). Only the account owner authors and places a plan, and no funded plan is dropped inside the final 60 minutes before a 4-hourly boundary (00/04/08/12/16/20 UTC) — run `date -u` immediately before.
- **Never induce inside a published Kraken maintenance window.** Read `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json` at planning time **and again immediately before each induction**; the entries that matter carry `WebSocket` or `REST` in `components` **or in the entry's `name`** — an empty `components` array is not an absent impact (measured 2026-09-02: *"Scheduled maintenance for Kraken Prime REST, WebSocket, and FIX API"* ships `components: []`), and they appear only 2–6 days ahead.
- **A drill whose instrument is not on the host yet is `blocked`, and the two instruments this page was missing are now both built — neither of the two is deployed.** **The `rest-hold` plan mode IS built** (spec `00108`, `cli/engine/probeplan.py` declares `execute`, `rest-cancel` and `rest-hold`): an order priced `offset_pct` passive of the touch, deliberately **not** cancelled when the venue acknowledges it, resting for the `hold_minutes` its author declares — which is what `rest-cancel` cannot give, since it cancels on that acknowledgement. So E, G, F2, A1 and A2 have a subject at last; the plan shape and its two fields are with Drill A's in [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window). What they wait on is the **engine converge** that puts that code on the host. **B's command IS built** (spec `00106`, `cli/engine/flatten.py`) and carries its own procedure at [`engine-procedures.md#engine-flatten`](engine-procedures.md#engine-flatten); what B waits on is that same engine converge, which puts `/usr/local/sbin/zcrypto-flatten` on the host. **No `rest-hold` order has ever been placed at Kraken** — the mode is proven by unit tests and one offline `--check` read, so the first live one will be a drill's. Each affected section states the gap in its own *Preconditions*; read it there rather than from any count here. Record **`blocked`** with that reason, never `fail`, and never run with a substitute plan mode: an order cancelled a second after it was placed exercises none of what these drills measure.
- **One induction at a time. Revert it and verify the revert BY VALUE before the next one starts.** An instrument is never widened: each *Induce* names exactly what to do, and anything heavier is a different act with a different blast radius.
- **The engine's own money guards are not suspended for a drill.** A kill trip during one of these is real — resting orders cancelled, every further intent refused, and nothing continues until a human reads and removes the file. Work [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) when that happens; do not treat it as drill noise.
- **A window that stays armed past six hours pages** [`zcrypto-engine-exec-armed-too-long`](engine.md#zcrypto-engine-exec-armed-too-long) (warning, `metrics`). That is the rule working, not a fault — but a drill held for hours, D above all, is held inside a window that will reach it.
- **The four statuses are fixed at `pass`, `fail`, `partial`, `blocked`**, and every run gets an entry in `docs/reference/drill-log.md`. The heading is `## <YYYY-MM-DD> — <scenario id> — <status>` and the body is one paragraph of labelled clauses: *host* · *induction* · *time-to-alert* · *channels* · *operator action* · *follow-ups*. Where a Slack path is involved the *time-to-alert* clause carries the rule's `activeAt` and the Slack message. It carries a **device** timestamp where that route's device leg is this drill's to measure — which on this page is the usual case, drill D above all, whose whole subject is when an operator learns of unwatched exposure; where another drill measures the same route, it names that drill and carries none, because two readings of one route measure it once.

## How every bound on this page was derived

A bound is derived or it is not written. Nothing below is an estimate.

- **A Grafana rule's bound is its own `for`, quoted from `infra/grafana/alerts.yaml`, plus its own group's evaluation interval.** This page names rules from **three** groups, and the group is a field on each rule in that file: the engine rules are `zcrypto-gate`; `zcrypto-fleet-daemon-restarted`, `zcrypto-alloy-dark-capture-primary`, `zcrypto-fleet-memory-headroom` and `zcrypto-hcio-watchdog` are `zcrypto-fleet`; `zcrypto-capture-all-streams-silent` and `zcrypto-capture-stream-silent` are `zcrypto-capture`.
- **Every rule group evaluates at 60 s.** That number is in neither `infra/grafana/alerts.yaml` nor `infra/scripts/grafana-push.sh` — it was read from Grafana's provisioning rule-group endpoint (`/api/v1/provisioning/folder/<folder uid>/rule-groups/<group>`, the `interval` field) for all eight groups on 2026-08-31. Re-read it there rather than trusting this line: it is a setting in the stack, and nothing in this repo changes when it moves — and **re-read the interval of the group the rule you are re-deriving actually belongs to**, since the three above can move independently of each other.
- **The engine's exporter is scraped every 60 s** — `scrape_interval` on the `engine_app` job in `infra/ansible/roles/capture/files/config.alloy` — so a gauge whose value changes on the host is at most one scrape old in Grafana Cloud.
- **Add ~5 minutes of Prometheus staleness wherever the condition cannot go true until the series goes stale.** That covers every rule here that pages by `noDataState: Alerting` once the engine's exporter is gone, and the Alloy route of `zcrypto-engine-dark-with-exposure`. Without that term those bounds understate the real notice by a third.
- **The gate's own gauges publish only when the gate is EVALUATED, and that cadence is not constant.** While a plan is running the executor evaluates on every 5-second tick and publishes the verdict from each one; with no plan running it evaluates at engine start and at each 4-hourly boundary. So every kill-switch bound below assumes a plan is resting, and that assumption is why E's preconditions demand one — a kill file placed on an idle engine can wait four hours to reach Grafana at all.
- **A healthchecks.io dead-man's bound is that check's own `timeout` + `grace`.** Only D reaches one, and the numbers for `zcrypto-engine-shadow` are quoted in [`drills-telemetry.md#drill-j-prime`](drills-telemetry.md#drill-j-prime) rather than re-derived here.

<a name="drill-a1"></a>

## Drill A1 — the primary reboots with an order resting, no fill — PROCEDURE

### What this proves

That an attended reboot of the capture primary — the host that also runs the engine — leaves the order path in a state an operator can account for: the capture gap healed from the secondary, the reduce-only hold latched, and the resting opener cancelled by the startup adopt pass.

What it does **not** prove is what the venue did with the order across the stop. That question is G's, whose stop is engine-only and therefore readable while the engine is down; here the host goes with it.

### Preconditions

- The window open per [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window), the engine armed, and no intent in flight.
- **A far-from-touch order resting** — the `rest-hold` gate in the standing rules. Not runnable without it; record `blocked`.
- **The secondary read whole by value immediately before**, because it is what heals the gap this reboot opens:
  ```
  uv run python infra/scripts/grafana-query.py 'up{job="capture_app",host="zcrypto-red"}' 'min(zcrypto_capture_seconds_since_last_book_message{host="zcrypto-red"})'
  ```
  `up` reads 1 and the silence gauge reads under 120 s — the threshold `zcrypto-capture-all-streams-silent` itself carries. Anything else and the reboot is postponed: both hosts dark at once is L2 that nothing recovers.
- **The secondary-first ordering in `docs/reference/fleet.md` § Reboots does not apply and must not be followed here.** That ordering is for a fleet-wide reboot round, where a bricked kernel must land on the expendable host first. This drill reboots the primary alone and the secondary is deliberately left running — rebooting it too would remove the healer.
- Everything else in that § Reboots bullet list holds in full: ≥ 1 h from any 4h bar boundary, off the hour, in the primary's measured book-traffic trough, and **right after a completed engine cycle**.

### Induce

The attended reboot of the primary, exactly as `docs/reference/fleet.md` § Reboots writes it — nothing heavier, and no substitute instrument. Expect a ~83 s capture gap; both containers self-restart.

### Must fire

- [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) (warning, `metrics`) — `changes(process_start_time_seconds{…}[15m]) > 0` with `for: 2m`, and **three** of that rule's targets live on this host: `capture_app`, `engine_app` and Alloy's own `integrations/self`. It lands ≈2–3 min after the host is back. Expected, named in the entry, never chased.
- **Nothing else, on an ~83 s reboot**, and each silence is derived rather than hoped for: [`zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale) needs ~5 min staleness + `for: 5m` + 60 s ≈ 11 min; [`zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) needs ≈12 min and on A1 has nothing to page about anyway, since no fill landed and its position node reads 0; [`zcrypto-alloy-dark-capture-primary`](observability.md#zcrypto-alloy-dark-capture-primary) needs `for: 10m` plus the same staleness; and both capture-silence rules carry `noDataState: OK`, so a host whose series have gone away leaves them Normal rather than firing.
- **A reboot long enough to page any of those is a finding about the reboot**, recorded as such, and not a result of this drill.

### Operator action

The reboot's own verify-by-outcome list in `docs/reference/fleet.md` § Reboots is owed first and in full. Then the four order-path readings, in this order:

1. **The gate, by value** — the hold must be latched:
   ```
   sudo docker exec zcrypto-engine zcrypto engine exec-status
   ```
   Expect `level=reduce_only` with `restart_hold` among the reasons. The engine writes that hold unconditionally at every start and nothing clears it but a human.
2. **The adopt pass ran and cancelled the opener**:
   ```
   sudo docker logs --since 30m zcrypto-engine | grep -E 'adopted resting order'
   ```
   A `canceling adopted resting order …` line names the order; a `… is a ledgered reducer -- left resting and re-attached` line means the row was classified a reducer and kept, which on an opener is a finding.
3. **The ledger**, with the probe window's ledger read — the order's row carries a terminal `state` and `filled_qty 0.0`, and no `fill` lines at all.
4. **Kraken's own open-orders view**, by hand. The engine's belief and the venue's are two readings, and this drill is one of the few places they can be compared cheaply.

Clear the hold only if the window continues, per the probe window's own step.

### Record

Entry `A1`. Beyond the standard clauses: the measured reboot gap in seconds, the venue's state for the order when the host came back, and whether the reconciler booked the window's capture gap and then healed it from the secondary.

**A1's entry is written after the reconciler has had its chance, not beside the reboot.** It books hour H only at the first `:12`/`:42` tick after H+2 h, so until that tick the gap reading is *pending*, not clean — and none of the four statuses means "verdict pending". Write the entry once, afterwards.

### Retire when

`_adopt_resting_orders` is absent from `cli/engine/executor.py` — at which point a restart no longer classifies resting orders and there is nothing here to exercise — or the engine no longer shares a host with capture, at which point a primary reboot is not an engine event at all.

<a name="drill-a2"></a>

## Drill A2 — the primary reboots and a fill lands while it is down — PROCEDURE

### What this proves

That a fill the engine was not present to hear is reconciled into its ledger at startup, and that the operator is left holding a **real position** they can account for. This is the scenario the account owner named, and its exposure is rung-1 money rather than a drill artefact.

Specifically: the startup pass compares each preserved row against the quantity the venue reports, and **only a venue figure that is HIGHER writes anything** — a `reconciled` event carrying the delta and the venue's total, plus a WARNING naming both figures. A repair is **not** counted as a fill: `zcrypto_exec_fills_total` and the fee counter do not move for it, because there is no per-fill detail and no fee behind the venue's aggregate.

### Preconditions

- A1's preconditions in full, with one difference: the plan is priced **marketable**, so a fill is expected rather than avoided. That is real money at probe size, and the position it leaves is the input to D and to B.
- **Know before you start that `matched` will read 0 here, and that this is not a finding.** A fill applied during the node's own startup reconciliation is published *before* the adopt pass has attached a single row, so it counts `unmatched` by design. The by-value `zcrypto_exec_external_events_total{disposition="matched"}` reading that proves Kraken echoes `cl_ord_id` belongs to G, where the cancel ack arrives after the rows are attached — booking A2's 0 as that measurement would record a failure of something A2 never tested.

### Induce

The same attended reboot as A1, with the marketable order resting when the host goes down.

### Must fire

A1's set, unchanged — `zcrypto-fleet-daemon-restarted` and nothing else on an ~83 s reboot.

**In particular [`zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) does not fire on a healthy reboot**, even though a position is now open: its scrape node needs 10 unbroken minutes below 1 and a reboot never reaches that. D is the drill where it does fire, and A2's end state is D's input.

### Operator action

1. **Read the repair, by value.** In the ledger, the row carries a `reconciled` event with the delta and the venue's total; in the log, `sudo docker logs --since 30m zcrypto-engine | grep -E 'reconciled against the venue'` names both figures.
2. **Confirm the repair moved no fill counters** — from the workstation, `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_fills_total{host="zcrypto"}' 'zcrypto_exec_fees_eur_total{host="zcrypto"}'` against their pre-reboot values. A number, never `(no series)`.
3. **Read venue truth** with the probe window's venue-truth read, and Kraken's own positions view beside it. The position is real; decide deliberately whether it stands for D or is closed now.
4. **A venue figure LOWER than the ledger's is the dangerous direction and latches the kill switch** — nothing is repaired, and `sudo cat /var/lib/zcrypto-engine/exec/kill` names the order and both quantities. That is [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped)'s withdrawn-fill path, not a drill outcome to clear and move past.

### Record

Entry `A2`: the venue's figure, the ledgered figure, the delta, that the fill counters did **not** move, and the position left open in base units. The `matched` reading is recorded as *0, by design* with a pointer to G, or the entry teaches the next reader that the adapter failed a test nobody ran.

### Retire when

`_reconcile_adopted_rows` is absent from `cli/engine/executor.py`, or the engine no longer shares a host with capture.

<a name="drill-b"></a>

## Drill B — the red button — PROCEDURE

### What this proves

**Decision-to-flat**: how long it takes, in wall-clock minutes, from an operator deciding to close everything to the account actually being flat. That number is the one an operator needs before they can promise anything about a bad afternoon, and nothing in this system has ever produced it.

### Preconditions

- **B waits on the converge, not on the build.** `zcrypto engine flatten` shipped with spec `00106`; the host-facing wrapper is rendered by `infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2` to `/usr/local/sbin/zcrypto-flatten`, and the procedure is [`engine-procedures.md#engine-flatten`](engine-procedures.md#engine-flatten). Until an **engine converge carrying 00106** reaches the host, the wrapper is absent and a run booked against B is **`blocked`** with *that* reason — "wrapper not yet deployed", never "not built", and never `fail`, which would assert a red button that did not work.
- The subject is a real position and a real balance: A2's end state, or D's, plus a small spot balance. Flattening an already-flat account measures nothing.
- The window open and attended, with the owner present. This is the one drill whose whole point is a human deciding.

### Induce

The flatten command, per [`engine-procedures.md#engine-flatten`](engine-procedures.md#engine-flatten) — **`sudo zcrypto-flatten` reads the plan, `sudo zcrypto-flatten --execute` presses it** (the wrapper is what an operator types; `zcrypto engine flatten` is the in-container form). **That section is the authority on how to run it**; this section owns only the drill around it — the clock starts at the decision and stops when venue truth reads flat.

### Must fire

**Do not expect [`zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) — and its absence is not a finding.** The wrapper's order is kill file first, then `systemctl stop` on the unit, then a proof it is `inactive` (`zcrypto-flatten.sh.j2`). The engine's exporter is therefore gone within a scrape or two of the kill file being written, so the rule never accumulates its `for:` and the page does not arrive. Record what the wrapper itself prints as the timeline instead: the clock starts at the decision and stops when venue truth reads flat.

**Against a running but idle engine the page does not arrive either — the wrapper's stop removes the exporter the same way — and its absence proves nothing. **That holds only once the stop has SUCCEEDED**: if the unit is still active after `STOP_WAIT_SECONDS` the wrapper exits 1 with the kill already latched and the engine still running, and a page arriving from *that* state is the rule's designed true positive — work it, do not read it as drill noise.** The gate publishes only when it is evaluated, and with no plan running the next evaluation is the 4-hourly boundary — so the gauge the rule reads has not moved yet. Read the kill file on the host instead of waiting for a page.

**Against a dark engine — B run as D's response — nothing pages at all.** There is no exporter to publish the gauge. And `zcrypto-engine-dark-with-exposure`, already firing, **does not clear when the position closes**: its position node reads the largest exposure over a 24 h lookback of a gauge the dark engine is not publishing, so a hand-flattened account leaves that node exactly where it was. It clears when the engine is back and publishing zeros, or when the last reading ages out of the lookback — and the second of those is not an all-clear, as that section says in those words.

### Operator action

The measurement *is* the operator action: note the decision time, run the procedure the command lands with, and stop the clock on venue truth reading flat — positions empty and balances EUR-only, read with the probe window's venue-truth read rather than from anything the engine reports about itself.

The kill file the flatten placed **stays** until a human clears it. Read it (`sudo cat /var/lib/zcrypto-engine/exec/kill`) before removing it, exactly as after any other trip.

### Record

Entry `B`: decision-to-flat in minutes, what was open when the clock started, what each leg cost to close, and anything the procedure could not close on its own.

### Retire when

Retire when `flatten` is absent from `cli/engine/command.py` again, i.e. the red button was replaced rather than never built.

<a name="drill-d"></a>

## Drill D — the engine goes dark with a position open — PROCEDURE

### What this proves

That the one alert nothing else covers actually pages a phone — a non-zero position at last sight with the engine's scrape gone — and how long an operator stays unaware of an unwatched position. Every other drill on this page is about an engine that is still answering.

### Preconditions

- **A2's end state**: a real position open, read by value from the ledger and from venue truth immediately before. A flat account cannot trip this rule and the run would be `blocked`.
- The window attended and the phone in hand — the page arriving is the deliverable, not the rule's internal state.
- **The telemetry plane read green by value immediately before**, because this rule fires on two routes and only one of them is this drill's:
  ```
  uv run python infra/scripts/grafana-query.py 'count(up{host="zcrypto"}) or on() vector(0)' 'up{job="engine_app",host="zcrypto"}'
  ```
  Both read 1. A primary whose Alloy is already dark makes the page unattributable, and the run would book a telemetry incident's `activeAt` as its own measurement. **An empty result is never a zero.**
- **Never induce this drill by stopping the primary's Alloy.** That is the rule's other route, and the primary's Alloy is not an instrument any drill on either page may touch.

### Induce

On the engine host (`ssh zcrypto`), stop the engine and hold — engine only, never a reboot, never the Alloy beside it:

```
sudo systemctl stop zcrypto-engine
```

**Hold past ≈12 min so the drill's own page lands**, and past ≈16 min only if the gate-evaluation rule below is being timed too. Do **not** hold to six hours to see the log-dead rule: that is six hours of a real open position with nothing watching it.

### Must fire

**Three pages inside a sixteen-minute hold, on three clocks, and only the second is D's own** — plus two more that arrive only if the hold runs for hours.

- [`zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale) (critical, `metrics`) **first, at ≈11 min**. It is an instant read of a gauge the stopped container no longer publishes, so it pages by NoData: ~5 min staleness + `for: 5m` + 60 s.
- [`zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) (critical, `metrics`) at **≈12 min** — the **exporter** route, and the only one this drill induces. Its scrape node reads the scrape's *value* on a static target, so the `up` series stays present reading 0 within one 60 s scrape of the container going away; + `for: 10m` + 60 s. No staleness term applies on this route.
- On the **other** route — the primary's Alloy going dark, which no drill induces — the same rule takes **≈16 min**: the series is taken away rather than set to 0, so the fallback that supplies the 0 cannot do so until the series goes stale (~5 min), + `for: 10m` + 60 s. Both numbers are derived the same way in that runbook section, and **the difference between them is how long the exposure has actually been unwatched** — quote whichever route the run induced.
- [`zcrypto-engine-exec-not-evaluated`](engine.md#zcrypto-engine-exec-not-evaluated) (warning, `metrics`) at **≈16 min** — the gate's last-evaluation stamp goes stale with the container and that rule also pages by NoData: ~5 min + `for: 10m` + 60 s.
- [`zcrypto-engine-log-dead`](engine.md#zcrypto-engine-log-dead) (critical, `logs`) only past **6 h** — its `[6h]` count window, `for: 0s`, + 60 s. A shorter hold leaves it quiet, and that silence is not a clean bill.
- The engine's own dead-man `zcrypto-engine-shadow` goes down at its `timeout` + `grace` = **4 h 35 m** (quoted in [`drills-telemetry.md#drill-j-prime`](drills-telemetry.md#drill-j-prime)), bringing `zcrypto-hcio-watchdog` ≈7 min behind it. Both are far outside any sane hold here.
- **Two rules stay quiet and prove nothing by it**: `zcrypto-venue-snapshot-stale` and `zcrypto-fleet-memory-headroom` both carry `noDataState: OK`, so a series that has gone away leaves them Normal.

### Operator action

**The drill is what the responder does with the page, so work it from the page and not from here.** Open [`engine.md#zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) from the notification, on the phone, and follow it from the top — ruling out the plane first, then reading the engine directly, and only then reaching for B. Whether the responder stops at the discriminator or reaches B is the finding; prompting them from this page destroys it.

Then restore:

```
sudo systemctl start zcrypto-engine
```

and confirm by value: `up{job="engine_app",host="zcrypto"}` back at 1, the position gauge publishing again, and `sudo docker exec zcrypto-engine zcrypto engine exec-status` showing the restart hold re-latched.

**Expect [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) on the restore** (warning, `metrics`): it reads `changes(process_start_time_seconds{…}[15m]) > 0` with `for: 2m`, and a 12-minute hold puts the return inside that window. Name it in the entry; never chase it.

### Record

Entry `D`, with the three timestamps on the Slack path — the rule's `activeAt`, the Slack message, and the phone. Beyond those: **which pages arrived and in what order**, the measured time-to-page against the ≈12 min bound and which route it was, and — the thing this drill exists for — **which page the responder acted on first, and whether they stopped at the discriminator or went on to flatten.** A run that only records that the rule fired has measured the rule and not the response.

### Retire when

`zcrypto-engine-dark-with-exposure` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_exec_position` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`).

<a name="drill-e"></a>

## Drill E — the kill switch, and E′ the phone-reachable halt — PROCEDURE

### What this proves

Three things, and the third is the one nothing today establishes.

1. That a hand-placed kill file revokes a resting order within the executor's 5-second tick and drops the gate to `level=none`.
2. That the alert half reaches Slack inside its bound, so a switch left engaged is noticed rather than forgotten — which is the failure mode that rule exists for.
3. **As E′: that the halt is reachable at all from outside the workstation.** The master plan asks for a halt an operator can reach from anywhere; whether the fleet's access path actually delivers one from a phone has never been tried.

### Preconditions

- The window open, the engine armed, and **a plan resting** — the `rest-hold` gate in the standing rules. Without a resting order the kill file revokes nothing and only the alert half is exercised.
- **`zcrypto_exec_kill_tripped` reads 0 by value immediately before**:
  ```
  uv run python infra/scripts/grafana-query.py 'zcrypto_exec_kill_tripped{host="zcrypto"}'
  ```
  A kill file already present means the alert is already firing, and the `activeAt` this run reads belongs to an earlier trip. Not 0 ⇒ clear the existing file first (reading it, per [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped)), or record **`blocked`**.
- **The plan must be resting when the file lands, and that is a bound, not a preference.** The gate publishes only when it is evaluated; with no plan running the next evaluation is the 4-hourly boundary, so a kill file placed on an idle engine can wait hours to reach Grafana and the measured page time would be an artefact of the cycle clock.
- **For E′ only**: the phone in hand with an ssh client installed on it. A device with no client is `blocked` — the induction never landed. A device with a client that the access path *refuses* is E′'s **finding**, recorded `fail`; that is the question E′ was run to answer.

### Induce

On the engine host, place the file. Presence is the whole protocol; contents are informational.

```
sudo touch /var/lib/zcrypto-engine/exec/kill
```

**A hand-placed file is empty, and an engine-written one is not** — the engine records the reason that tripped it. That difference is what step 3 of the operator action reads, and it is the only thing distinguishing this drill's file from a real trip found later.

<a name="drill-e-prime"></a>

#### E′ — the phone-reachable halt

**Read E′'s own precondition above before starting** — it is the last bullet of *Preconditions*, and it is what decides `blocked` from `fail`: no ssh client on the device means the induction never landed; a client the access path refuses is E′'s finding.

The same placement, made from the phone: an ssh client on the device, the fleet's own access path, and the one-line command above unchanged. Nothing about the engine changes — what is being timed is the human half, from the moment of decision to the gate reading `level=none`, with every step taken on the device and none on the workstation. Record the device and the client **by name**: the answer is a property of that pair, and a later reader cannot infer it.

### Must fire

- [`zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) (warning, `metrics`) at **≈7 min**. Derived: the executor evaluates the gate on its 5-second tick while a plan is running and publishes the verdict from every evaluation, so the gauge reads 1 within one tick; + one 60 s scrape + `for: 5m` + the 60 s group interval. A value read on a series that is present throughout, so no staleness term applies.
- **Nothing else.** `zcrypto-engine-cycle-stale` and `zcrypto-engine-dark-with-exposure` both need the exporter to be gone, and the engine is running and answering throughout this drill.
- Not a page, but the reading that says the revocation happened: the intent journals `revoked` and its order row reaches a terminal `state`.

### Operator action

1. **Within about five seconds the gate reads `level=none`.** This read is E′'s stop-clock:
   ```
   sudo docker exec zcrypto-engine zcrypto engine exec-status
   ```
   `reasons` lists `kill_switch` alongside whatever else the gate is refusing on.
2. **The resting order is revoked**, not merely refused: read the ledger with the probe window's ledger read and confirm the intent's `revoked` outcome and the row's terminal state. A row still open means the cancel is outstanding at the venue — read Kraken's open orders before concluding anything.
3. **Reset is a hand act, and it starts with reading the file, not removing it**:
   ```
   sudo cat /var/lib/zcrypto-engine/exec/kill
   ```
   Empty ⇒ this drill's own file. Carrying a reason ⇒ the engine tripped itself while you were here, and [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) is the section to work — a withdrawn fill in particular needs the ledger reconciled against venue truth **before** the file goes. Then `sudo rm /var/lib/zcrypto-engine/exec/kill` and confirm `exec-status` is back to `level=full`.
4. **The page clears well after the reset, and that lag is the gauge's cadence rather than a stuck alert.** A gauge holds its last published value, and the gate publishes only when it is evaluated — so with the plan already gone the next publish is the 4-hourly boundary. `exec-status` re-evaluates on the spot but runs in its own process and publishes nothing. Read the reset from `exec-status`; do not wait on the alert to confirm it, and do not re-place the file because the page is still up.

### Record

Two entries, `E` and `E′`.

`E` carries the measured file-to-`level=none` interval, the measured file-to-Slack interval against the ≈7 min bound, and the ledger row's terminal state. `E′` carries the **device and client by name**, the decision-to-`level=none` time, and whether the access path worked at all — a refusal there is E′'s result, written as the finding it is rather than as a failed setup.

### Retire when

`KILL_FILE` is absent from `cli/engine/execgate.py` — at which point the file is no longer the halt — or `zcrypto-engine-exec-kill-tripped` is absent from `infra/grafana/alerts.yaml`, which retires the alert half alone and leaves the rest of this section standing.

<a name="drill-f2"></a>

## Drill F2 — the engine loses its socket with an order resting — PROCEDURE

### What this proves

What the executor does when the venue becomes unreachable **from the engine's side** with an order resting — and, above all, that the order may still be resting at Kraken afterwards with nothing in this process able to reach it.

The expected sequence, from `cli/engine/executor.py`: on the first tick after 30 s of quote silence the cancel is attempted **exactly once** — no retry, no fallback; it cannot reach the venue, so within a further 30 s the intent is journaled `ambiguous` with a CRITICAL line and the plan's remainder is dropped. About sixty seconds end to end, and at the end of it the venue's state is unknown to the engine by construction.

### Preconditions

- The window open, the engine armed, and a resting plan — the `rest-hold` gate.
- **The order is priced far from the touch.** It may survive the whole drill at the venue; a marketable one can fill while the engine is blind to it, which is A2's scenario arriving on a path with no reboot to explain it.
- **Read the engine container's network by value before disconnecting it.** The compose project is `/opt/zcrypto-engine` and its template declares no `networks:` key, so the network is that project's default — but confirm the name on the host rather than typing it from this page:
  ```
  sudo docker network ls --filter name=zcrypto-engine
  ```
- **Write the reconnect command down before running the disconnect.** A revert that exists only in your head is one interruption away from a live engine with no venue.

### Induce

On the engine host, disconnect the engine container from that network:

```
sudo docker network disconnect <the network> zcrypto-engine
```

The container is bridge-networked with `127.0.0.1:9102:9102` published (`infra/ansible/roles/engine/templates/compose.yaml.j2`), so `disconnect` applies to it — unlike the fleet's host-networked Alloy containers, which Docker refuses to disconnect from any network.

### Must fire

- **Nothing at all, on a hold under ~11 minutes — and that is a coverage finding, not a quiet fleet.** Every rule that would notice keys on the exporter or on the log stream, and all of them are slower than the entire behaviour this drill measures.
- Past **≈11 min**, [`zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale) (critical, `metrics`): the disconnect removes the published-port endpoint, so the scrape fails and the cycle gauge goes stale — NoData at ~5 min + `for: 5m` + 60 s.
- [`zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) stays quiet **if and only if nothing filled**: its position node reads the largest exposure at last sight, which is 0 on a flat account. If the order filled before the socket went, this run has become D on a shorter clock and that page lands at ≈12 min.
- **The engine's CRITICAL line does not reach Loki while the socket is down**, so [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) cannot fire during the hold. The engine ships its own logs in-process straight to Grafana Cloud rather than through Alloy; with no network the ship handler retries against a bounded in-memory ring and evicts the oldest lines once it is full, so whether the line arrives on reconnect depends on how long the hold ran. **Read it from the host, never from Loki.**

### Operator action

1. **During the hold, watch the intent reach `ambiguous`.** `docker exec` needs no network, so both reads still work:
   ```
   sudo docker logs --since 30m zcrypto-engine | grep -E 'ambiguous|no venue answer'
   ```
   and `sudo docker exec zcrypto-engine zcrypto engine exec-status`.
2. **Reconnect**: `sudo docker network connect <the network> zcrypto-engine`, then `up{job="engine_app",host="zcrypto"}` back at 1 by value.
3. **Read Kraken's open orders by hand.** The order may still be resting there and **nothing in this engine will cancel it**: the intent is terminal, so a hand-placed kill file sweeps nothing.
4. **Clear it deliberately** — either a restart, whose adopt pass cancels non-reducer openers, or a direct cancel in the Kraken web UI. Note the wall-clock time it rested, from the disconnect to the cancel.

**If the property you wanted is "the order dies with the socket", that is re-cancel-on-reconnect** — a build item in `T0018`, never an expectation to write against this drill.

### Record

Entry `F2`: how long the order rested at the venue, whether the intent journaled `ambiguous` inside the derived ~60 s, which page fired if any, and how the order was finally cleared. A hold too short for any rule to fire is recorded as exactly that — `pass` on the executor's behaviour with the coverage gap named — never as an untested alert path.

### Retire when

`_ACK_WAIT` or `_QUOTE_SILENCE` is absent from `cli/engine/executor.py`, or the engine container stops being bridge-networked in `infra/ansible/roles/engine/templates/compose.yaml.j2` — at which point `docker network disconnect` is no longer the instrument and the induction has to be re-derived before the drill is re-run.

<a name="drill-g"></a>

## Drill G — restart with an order resting, and the reduce-only hold — PROCEDURE

### What this proves

Three things, in the order they can be observed, and the first is unverified anywhere in this repo today.

1. **What the venue does with a resting GTC order across an engine stop.** `ExecStop` is a compose down and nothing cancels resting openers before the process exits, so the answer is Kraken's, not the engine's — and it is readable only while the engine is down.
2. That the restart latches the reduce-only hold.
3. That the adopt pass **attaches every matched row first and only then cancels the opener**. That ordering is what puts a fill landing during the stop into its own row rather than into nothing.

**G is the measurement cancel-on-stop is waiting on.** That enhancement is ruled only once G says what the venue actually does, so do not "fix" the behaviour first and then run the drill against the fix.

### Preconditions

- The window open, the engine armed, a resting plan — the `rest-hold` gate.
- **The stop lands inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC). Run `date -u` first: a stop that kills a running cycle costs that boundary's record and confuses everything this drill measures.
- No intent in flight beyond the resting one.

### Induce

On the engine host, stop the unit — engine only, no reboot and no converge:

```
sudo systemctl stop zcrypto-engine
```

**Read Kraken's open orders in the web UI while the engine is down.** That reading is deliverable 1 and it is unrepeatable: once the engine is back, the adopt pass has already acted on whatever was there. Then start it again:

```
sudo systemctl start zcrypto-engine
```

### Must fire

- **Nothing, if the engine is back inside ~11 minutes.** All three of the rules D lists need longer, and G's stop is deliberately short.
- **On the restart, [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted)** (warning, `metrics`) at ≈2–3 min — `changes(process_start_time_seconds{…}[15m]) > 0` with `for: 2m`, and the engine is one of that rule's targets. Unlike an Alloy drill, waiting it out is not an option here: the restart *is* the drill. Name it in the entry.

### Operator action

1. **While down**: Kraken's open orders, by hand. Record whether the order is present and in what state — that is deliverable 1, and no later reading recovers it.
2. **After the start**: `sudo docker exec zcrypto-engine zcrypto engine exec-status` reads `level=reduce_only` with `restart_hold` among the reasons.
3. **The adopt pass's own line**, by value:
   ```
   sudo docker logs --since 30m zcrypto-engine | grep -c 'canceling adopted resting order'
   ```
4. **The ledger**, with the probe window's ledger read: the row's `events` for the cancel, and — if a fill raced it — a `fill` line beside it in the same row.

### Record

Entry `G`, and **one reading beyond the log's clauses**, discharged into `docs/reference/adapter-verification/<the running version>.md` beside that version's probe table:

```
uv run python infra/scripts/grafana-query.py 'zcrypto_exec_external_events_total{host="zcrypto", disposition="matched"}'
```

**The `disposition="matched"` selector is the whole reading, not tidiness.** Both label children are registered at engine startup, so an unselected query returns two series — and in a window that already ran A2 the `unmatched` one reads non-zero **by design**, since a fill applied during startup reconciliation is published before any row is attached. Reading the pair without the selector is how a 1 that belongs to A2's fill gets written into the adapter-verification record as a proven `cl_ord_id` echo while `matched` sat at 0 and owed the two-artefact rule below.

- **1 is the expected value.** The adopt pass's own cancel ack arrives on the external stream and keys back through the row the pass attached, and the matched counter is incremented before the fill branch runs.
- **2 under a fill racing the cancel.** Either value proves Kraken echoes the client order id across a restart, which is the question this reading exists to answer.
- **0 has two causes, and neither may be written down without the two artefacts that tell them apart.** Either Kraken did not echo the client order id, **or** the cancel's ack never reached the external stream at all — how nautilus routes a strategy-issued cancel on an order tagged external is unmeasured in this repo, and if that is the answer it is an engine-side defect on the live trade path rather than a fact about the venue. The artefacts are the `canceling adopted resting order` line above and the row's own `events`: a line with no matching cancel event on the row says the cancel was issued and its acknowledgement went nowhere; no line at all says nothing was cancelled and the reading is about a different question entirely. **Record a 0 as "0, cause undetermined" until both have been read.**
- `(no series)` is a FAIL of the telemetry path and never a zero — both dispositions are registered at engine startup, so the family is present on a healthy engine whatever the counts.

### Retire when

`_adopt_resting_orders` is absent from `cli/engine/executor.py` — at which point a restart no longer classifies or cancels resting orders, and every one of this drill's three deliverables is about a path that no longer exists.
