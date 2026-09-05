# Engine — attended procedures

Nothing fires these; you run them deliberately, and real money moves. Alert-triggered sections stay in [`engine.md`](engine.md).

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

1. **Sweep for blockers, and present the result together with the arming request.** Read `### Open` and `### Partially done` in `docs/open-topics/README.md`, and grep `.local/memo.md` for anything in flight against the engine. "Ready" without the sweep is not ready.

2. **Confirm the deployed code is the code you tested.** The engine row in `docs/reference/fleet-pins.md` records the digest running on `zcrypto` and the revision it was built from. Confirm the running digest matches — `sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine` — and that your working tree is at that revision. Then run the two guards that catch a drift between the committed cost floors / ratified basket and what the venue reports: `uv run pytest tests/test_costmin_drift.py tests/test_basket_concordance.py` → expect `2 passed`. A failure means the floors or the basket have moved since that image was built; stop, do not arm. **`1 passed, 1 skipped` is NOT a pass** — the drift test skips itself when no refdata snapshot is present under the gitignored data root, so run this in a tree that has one; a skipped drift guard reads green and has checked nothing. Add `-rs` if you want the skip reason spelled out.

3. **STOP unless the engine's nautilus version has its own order-semantics verification.** The adapter's margin/short/post-only and reconciliation semantics are verified by hand, against real orders, once per version — one record per version under `docs/reference/adapter-verification/`, indexed by `cli/engine/order-semantics-verified.json`, which is the file both arming guards read. Each record describes the version it ran on and no other: a bump may change fill, cancel, post-only or reconciliation behaviour without changing anything this repo's tests can see, because the tests never place an order. So the fresh ~€0.20 zero-fill + round-trip pass is a precondition of **arming**, not of merging a bump — the repo may sit on a newer version indefinitely while disarmed, and this is the step where that debt comes due.

   Read the version the engine is actually running (scope the exec to this one command — the container carries the live trade key):

   ```
   sudo docker exec zcrypto-engine python -c "import nautilus_trader; print(nautilus_trader.__version__)"
   ```

   Then confirm `docs/reference/adapter-verification/<that version>.md` exists — the file is named for the version string exactly as the interpreter spells it — and records a PASS. If none does, **do not arm**: run the order-semantics probes on that version first and write them up in a new record there — the harness is `infra/scripts/kraken-order-semantics-probe.py` and the attended procedure is [`order-semantics-verification.md`](order-semantics-verification.md). Never reason that the previous version's PASS "probably still holds" — that is the whole reason this gate exists.

   **This step is enforced mechanically in TWO places, and they are complementary — do not delete either as duplicative of the other.** Both read the same committed record, `cli/engine/order-semantics-verified.json` (it lives under `cli/` because the engine image copies only that directory, so a record under `infra/` would be unreachable from the running engine):

   - **The converge** — the engine Ansible role refuses a converge that would render `exec_armed = true` on a version absent from the record. Bypass `-e arming_override="<reason>"`, reason-required, like `canary_override` and `pins_override`.
   - **The arming** — the execution gate refuses at runtime when the *running* interpreter's `nautilus_trader` is absent from the record: `level=none`, `reasons=…,nautilus_unverified`, journaled into `exec-<HH>.json` like every other reason.

   Neither subsumes the other. Arming takes two keys, and the arm file is placed by hand long after any converge — so a host that converged armed on a verified version and later took a newer image would pass the converge assert and still be arming an unverified adapter; the gate catches exactly that. Conversely the gate cannot stop a converge from *rendering* an armed config. If either fires it is telling you what this step says; do not override it to get a probe window started.

   **For `2.0.0rc4.dev20260825` — the version the engine now deploys on — the re-run HAS happened**: attended 2026-08-26, PASS on all six probes, recorded in `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`, and the version is in the record — so both guards clear it and the engine may be armed on it. The cost was EUR 0.16 in commissions and the account's own balance moved 99.6772 → 99.5173 across the money leg — a drop of 0.1599 against an expected 0.16001, consistent but not exact; the record carries the residual. (`1.230.0` and `1.231.0` remain in the record as the passes that really ran; neither is deployable now.)

   **A PASS is not the whole gate — read that record's `## Owed checks not discharged by this pass` section and discharge every open item before arming.** A pass records what the run could measure; anything it could not lands there, and a version whose record still carries an open item is not cleared to arm however green the verdict above it reads. The passes deliberately run at B+35 or later, so the checks that land there are typically the ones a later clock has to answer — take the reading and write it back into that same section as its outcome, so the record settles rather than accumulating. The record is the inventory; a copy of it here drifts behind it.

   **The pin is FROZEN at that string until the engine is armed on it.** The record does exact membership, so a bump is a decision to re-run the pass at its full attended cost or to revert — and nothing warns at the moment of the bump. The next bump owes its own pass: the harness is `infra/scripts/kraken-order-semantics-probe.py` and the procedure is [`order-semantics-verification.md`](order-semantics-verification.md).

   **No test will route you here — these two refusals are the tripwire.** The suite asserts only that the installed version equals the version `pyproject.toml` pins; that check stays green across every bump, deliberately, because an assertion that went red on routine pin moves became noise and got rubber-stamped, which is how a tripwire dies. So a green suite is not a claim that the running version may be traded on, and it never was one. What blocks an unverified version is the pair above, and each blocks the money rather than a test run: the converge refuses to render an armed config, and the gate refuses to arm. Meeting one of them *is* the routing — read it as this step, not as a fault to clear.

4. **On the FIRST arming window for a nautilus version, take the unmatched-external baseline — before anything is thresholded on it.** The external-order observer is registered when the node is built rather than at `on_start`, so events published during the engine's own startup reconciliation can reach it and be counted `unmatched`. That is safe — they are logged and dropped, and nothing is attached to act on yet — but it means `zcrypto_exec_external_events_total{disposition="unmatched"}` may rise at **every healthy boot**, and an alert thresholded as though `unmatched` meant "an operator must act" would page on a clean start.

   Two things, and the order between them is the whole point:

   1. **Measure it.** With the engine **disarmed**, read the counter immediately before and immediately after one clean engine start and record the difference — that difference is the healthy-boot baseline. From the workstation: `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_external_events_total{host="zcrypto"}'`. `(no series)` is a FAIL of the telemetry path, never a zero. Write the number into this version's `docs/reference/adapter-verification/<version>.md` record, beside the probe table, where the next reader of that version will look for it.

      **For `2.0.0rc4.dev20260825` this is TAKEN: the baseline is 0.** Recovered from the metric's own history rather than from a live pair — a counter resets on restart, so what decides the question is the new process's value once startup reconciliation has run, and it held 0 for 22.1 h across zero restarts. The step stays written in before/after form because that is the cheaper procedure at a window you are already holding open; either route answers it.

      **What that 0 does NOT cover, and what to do about it here rather than anywhere else:** it was measured on a FLAT account — no open orders, no positions. That is every boot before rung 1 and none after it. **The first disarmed boot that carries live orders or positions is a reading to take**, because startup reconciliation then has something to reconcile and may count it; take it the same way, and write it beside the 0 in that version's record. Until it exists, no threshold may assume a boot on a live account behaves like this one.

   2. **The alert was DECIDED AGAINST on 2026-08-27 — do not author one.** Both gating preconditions above are satisfied (the baseline is 0, the family has had records since 2026-08-23), so this step would otherwise now read as owed. It is not. The candidate was `unmatched` rising while `zcrypto_exec_armed` is 0, and the framing is right but the sensor is not: that gauge is published only when the gate is EVALUATED — engine start and each 4-hourly cycle while disarmed — so it is stale in both directions, reading 0 for hours after you arm and 1 for hours after you disarm. The rule would page on your own attended work and stay mute through the hour after you walk away. Visibility is unaffected: engine-dashboard panel 61 plots both dispositions. The full reasoning, and the one change that would make a rule viable, are in `tests/test_infra_alert_rules.py`'s `NOT_A_FAULT_SIGNAL` entry for this metric.

   For a FUTURE nautilus version the baseline reading in item 1 is still owed; the alert is not.

5. **On the same first window, and only after the baseline above has a number, read how often the engine mints an order's terminal event for itself.** Past its in-flight retry budget the execution engine stops waiting on an unanswered order and publishes that order's `OrderCanceled`, or an `INFLIGHT_TIMEOUT` `OrderRejected`, on its own authority. The executor treats every one of those as an unknown venue outcome: the intent ends `ambiguous`, nothing is resubmitted, and the plan halts. That is the right answer and it is also a **plan-stopping** one, so how often the machinery fires decides how often an attended window ends on a slow venue rather than on a real result — and that rate has never been measured on this venue.

   Three readings, none of which needs new instrumentation. From the workstation:

   ```
   uv run python infra/scripts/grafana-query.py 'zcrypto_exec_orders_total{host="zcrypto"}'
   uv run python infra/scripts/grafana-query.py 'zcrypto_exec_external_events_total{host="zcrypto"}'
   ```

   and on the host, the engine's own account of each timeout (scope the read to this one command; a bare `--since HH:MM` does not parse, so pass a duration, and confirm the output is non-empty before reading anything into a quiet grep):

   ```
   sudo docker logs --since 24h zcrypto-engine | grep -c INFLIGHT_TIMEOUT
   ```

   `outcome="ambiguous"` is where a minted terminal lands. `disposition="unmatched"` is where a whole order the engine synthesized to close a position discrepancy lands — it arrives under the reserved external strategy id, matches no ledgered row, and is dropped, which is why this reading is only meaningful **against** the healthy-boot baseline from step 4: without that number a clean start's own reconciliation traffic is indistinguishable from a synthesis. `(no series)` on either family is a FAIL of the telemetry path, never a zero.

   **Zero is the expected reading while nothing has been submitted, and it is still worth taking.** A non-zero one before any order exists means the machinery is firing on something nobody has modelled — read the log lines and understand them before arming, rather than after. Record the three numbers in this version's `docs/reference/adapter-verification/<version>.md` record beside the baseline.

6. **Confirm funding covers the plan, by hand, before the tooling does it for you.** Take the free EUR balance from the venue-truth read — the live balances spell that key **`EUR`** (measured at the 2026-08-26 pass: `{'EUR': '99.51730000 EUR'}`), not `ZEUR`; the engine still tries `ZEUR` first because the adapter's instrument-quote surface does spell the euro that way, so both keys are read and whichever the record carries is used. The plan's total `notional_eur` must be at or under `exec_max_plan_notional_eur` in `/opt/zcrypto-engine/zcrypto.toml` (rendered `100.0`), and `sum(notional ÷ leverage) × 2.5` over the margin intents must fit under that free balance. `probe-plan --check` recomputes both below and refuses on either — this step is so you learn it before the window, not during it.

7. **Only the account owner authors and places a plan.** A plan file the owner did not place does not exist to this process.

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

   **If the restart left an order resting at the venue, its ledger row is preserved and its later fills still land in it.** The startup pass keeps a resting order only when the ledger carries it as a reduce-only row; that row survives and is re-attached. After a restart the venue's resting order is reconciled under an external identity, and the engine watches that identity's event stream too — matching every event on it against exactly those re-attached rows — so a fill landing on such an order appends to its row, moves the execution counters, and latches the kill switch on an overfill, the same as a fill on an order this process itself submitted. The row is current state, not only a record of what happened before the restart; Kraken's own open-orders and trades views and the next `venue-<HH>.json` are independent corroboration rather than the only place the fill exists.

   <a name="adopt-pass-blind-legs"></a>

   **That holds on the seven legs Kraken spells one way, and on the other five none of it happens.** The startup pass classifies whatever the venue's open-order read returns, and that read is the one the flatten procedure's [third limit](#flat-verdict-blind-legs) describes: the adapter looks an open order up by a spelling its instrument cache does not carry, drops the row, and returns success. So on **BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR and ETH/BTC** an order the previous process left resting is not in that read at all — it is not adopted, its row is not re-attached, it is not reconciled against the venue's figure, and it is not cancelled, with no line logged for any of those. Its later fills then match no re-attached row: they are counted `unmatched` and acted on nowhere — no row write, no execution counters, no overfill trip. **A restart is not a way to clear such an order**; cancel it on Kraken's own page, and read that page rather than the pass's log lines before you conclude nothing is resting.

   **A resting order is not the only thing that read misses on those five legs — it misses that order in every state it can be in.** The same lookup is how each preserved ledger row finds the order it names, so a row whose order filled, was canceled or expired while the engine was down is not found either: it is given no final state, no `reconciled` event and no WARNING, and neither of the two boot-time kill latches described two paragraphs below can arm for it. **An unchanged row, a quiet log and an absent kill file are what a blind leg looks like, and also what a clean startup looks like** — the only thing that separates them is Kraken's own closed-orders and trades pages, so read those for these five legs before you accept the quiet as clean. This follows from the read the pass uses and not from a startup anyone has watched: no reconciliation of a closed order has been measured on any leg. This is the same deliberately unfixed limit registered on \[[T0160]\] — do not delete either paragraph in a docs pass.

   **The startup pass also reconciles every preserved row it can resolve against the venue's own figure, so a row can move before you ever read it.** A fill that lands while the engine is down reaches no handler — the process is not there to hear it — so the pass compares each preserved row against the quantity the venue reports for that order. **Only a venue figure that is HIGHER writes anything into the row**: that difference lands as a `reconciled` event carrying the delta and the venue's total, plus a WARNING log line naming both figures. A difference too small to be real (the two figures are summed differently and can disagree in the last bits) is silent by design, and a venue figure that is *lower* writes no event at all — it is a divergence, not a repair, and it goes straight to the kill switch described below. An order that filled, was canceled or expired while the engine was down is closed at the venue and never appears among the resting orders at all; on the seven legs the read resolves, its row is still found and is given its final state (`filled`, `canceled`, `venue_canceled`, `rejected`) right there at startup, with a `reconciled` event beside it only if the venue also reported more filled than the row had — a cancel with no fills, the commonest case, gets the state write and nothing else. On the five above the row is not found, so none of that happens and nothing says so. So a row that closes with no event stream behind it is this pass, not something you missed. A repair is **not** counted as a fill: `zcrypto_exec_fills_total` and the fee counter do not move for it, because there is no per-fill detail and no fee behind the venue's aggregate. The row is the record.

   **This is also the one thing that can latch the kill switch at boot, before any plan is picked up.** Two divergences trip it, and they leave different evidence. **The venue reporting more filled than the row was ever submitted for** writes the repair into the row first and latches second, so the row carries a `reconciled` event and the kill file names both quantities. **The ledger claiming more filled than the venue reports** — the dangerous direction, since it means the engine believes it reduced more than it did — never repairs the quantity: there is no repair to make, and inventing one would erase the very figure that is in dispute. What it *does* write depends on which row it lands on. On a row still open — an order that could yet be live — nothing goes into the row but its terminal `state`, if the venue's own order has closed, so the kill file is the only place the venue's figure appears. On a row this engine had already **closed** — the shape a withdrawn fill takes, since a withdrawal lands on a completed order — a `withdrawn` event carrying `venue_filled_qty` is appended to the row *first* and the latch follows, leaving the ledgered quantity standing beside it so the two readings sit together. Either way, do not read an unchanged row as evidence nothing happened; `sudo cat /var/lib/zcrypto-engine/exec/kill` names the order and both quantities in every case the pass can resolve — which on **BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR and ETH/BTC** is no case at all, since neither divergence is ever compared there and both latches stay silent. **One false-fire path is worth knowing before you touch a resting order in the Kraken web UI**: `editOrder` is cancel-replace, not an in-place amend — it produces a *different* order, and a replacement echoing the same client order id presents zero fills against a row that has them, which is exactly the ledger-ahead-of-the-venue trip. It would latch at the next restart rather than when you clicked, with nothing in the UI hinting at it, and the row it latched over will look untouched. `amendOrder` is in-place and does not have this shape.

   **An event on that stream belonging to no ledgered row — your own hand settle in the Kraken UI is the one that matters — is counted under `zcrypto_exec_external_events_total{disposition="unmatched"}` and logged, and acted on nowhere**: no row write, no fill or order counter, no cancel, and no fill-time trip. That is the filter working as designed for an event with no ledgered row behind it. **On the five legs above it has a second cause and there it IS a gap** — a fill on an order the previous process left resting there matches no re-attached row either, so it lands in this count instead of in the row the ledger holds for it. What it does NOT settle is whether a hand settle produces an order event at all: the engine publishes reconciled orders' events unconditionally, but whether Kraken's settle-position act emits one on the adapter's streams has never been measured — so the counter is the instrument that will answer it at the first settle, not the answer. Read it then (**§6 Verify by outcome, item 6** queries it): a rise means the settle reached this process as an order event and was correctly ignored; a flat counter means it did not, which is worth recording either way. It stays clear of the fill-time trips because it matches no ledgered row — which changes nothing about the position-reconciliation trip described under the settle preconditions below, whose input is the venue's position rather than an order event.

5. **The owner clears the hold**: `sudo rm /var/lib/zcrypto-engine/exec/restart-hold`. Gate read → `level=none`, `reasons=arm_file_absent`.

6. **The owner creates the arm file**: `sudo touch /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=full`, `reasons=-`. A `nautilus_unverified` here instead means the running version has no recorded order-semantics pass and pre-probe step 3 was skipped — stop and go back to it; the gate is refusing on purpose and no control file will clear it. If `venue_not_online` shows up instead, Kraken itself is not `online` — wait it out, since nothing can be submitted until it is. The engine is now armed, and the `zcrypto-engine-exec-armed-too-long` alert above will page if the window outlives six hours — that is the rule working, not a fault.

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

**The third mode, `rest-hold` — not authored here, but authored against this shape.** Nothing in the probe window uses it; the order-path drills do ([`drills-order-path.md`](drills-order-path.md)), and its plan is the shape above plus two fields:

```json
{
  "plan_id": "drill-a1-2026-09-01",
  "created_at": "2026-09-01T09:05:00+00:00",
  "intents": [
    {"symbol": "BTC/EUR", "side": "buy", "action": "open", "mode": "rest-hold", "notional_eur": 20.0, "leverage": 2, "offset_pct": 5.0, "hold_minutes": 45}
  ]
}
```

**The `BTC/EUR` above is the plan's SHAPE, and for four of the drills it is the wrong pair.** A1, A2, F2 and G all turn on what the startup pass does with the order across a restart, and BTC/EUR is one of the five legs where that pass never sees it ([the restart's blind legs](#adopt-pass-blind-legs)) — the drill would produce no adopt line and no repair line, cancel nothing, compare nothing, and read as a defect. Author those four on a leg Kraken spells one way: SOL/EUR, ADA/EUR, DOT/EUR, LINK/EUR, DOGE/EUR, AVAX/EUR or SOL/BTC.

**`offset_pct` is a PERCENTAGE, not a fraction — `5.0` is five percent.** The dangerous slip is the quiet one: `0.05` is five *hundredths* of one percent, about fifteen euro off a thirty-thousand euro bid, and it fills — on the one mode built never to. The opposite slip is loud and harmless, since `500.0` prices absurdly and simply never places. `hold_minutes` is how long the order rests, an integer in 1–60. Both fields are required on `rest-hold` and refused on the other two modes; `action` must be `open`.

The `--check` line carries both back in words on the intent line, and reading it is how the slip is caught before the file is placed — the same line as above with the two fields spliced in:

```
  [0] BTC/EUR buy open rest-hold (5% passive of the touch, holding 45 min): notional 20.00 EUR, costmin <X> EUR
```

**Three terminal outcomes to read back in the ledger, beside Drill A's `rest_cancel_ok`.** `rest_hold_expired` — the hold ran its course: the engine cancelled at `hold_minutes` and the venue acknowledged. `rest_hold_venue_canceled` — the venue or the operator took the order off the book, and the engine deliberately did **not** put a new one back; a completed intent, not a fault, and the reason a hand-cancel in the Kraken web UI ends the drill rather than restarting it under an order id nobody is watching. `revoked` — the kill file, a disarm or quote silence took it mid-rest, so it was revoked rather than held to its expiry, and the plan stops there.

**Read `filled_qty`, not the outcome name — the names you can see here do not behave alike.** `rest_hold_expired` and `rest_hold_venue_canceled` are **remapped to `partial`** the instant anything filled, so seeing either name is itself the statement that nothing did. A **fully** filled order reaches none of the three: the intent finishes `filled` the moment its target quantity is met, before any cancel is asked for — so `filled` is the fourth name on this list, and the one that says money moved loudest. **`revoked` is not remapped**: it keeps its name whatever filled, and carries the fill through in `filled_qty`. That state is reachable by design, because a partial on a resting order leaves the remainder working at the touch — so an order that took a fill and was *then* revoked (drill E's kill file landing on a rest-hold order the market had already reached) journals `outcome revoked` with a **non-zero `filled_qty` and a real position behind it**. On a `revoked` intent, `filled_qty` is the only field that answers whether anything reached the book.

**Drill B — the disarmed refusal: prove the key actually refuses.**

1. `sudo rm /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=none`, `reasons=arm_file_absent`.
2. Place a second `rest-cancel` plan with a **new** `plan_id`, exactly as in drill A steps 1–5.
3. Expect the plan entry to still read `accepted` — the plan-level checks do not read the gate — and **every intent** to read `outcome refused` with `reasons ['arm_file_absent']`. No order row is created for it, nothing reached the venue, and `zcrypto_exec_orders_total{outcome="refused"}` advances.
4. Re-create the arm file (`sudo touch /var/lib/zcrypto-engine/exec/armed`) and confirm `level=full` before going on.

#### 4. Execute — the funded plans

**Three rules hold for every funded plan below, without exception.**

- **Never drop a funded plan inside the final 60 minutes before a 4-hourly boundary** (00/04/08/12/16/20 UTC). Run `date -u` immediately before placing; if the next boundary is under 60 minutes away, wait for it to pass. The 4-hourly cycle runs synchronously on the node's single event-loop thread and can hold that thread for up to about 25 minutes when a refresh degrades. While it is held no 5-second tick fires, so **none** of the mid-flight revocations — the kill file, a disarm, quote staleness, the intent's own time-box — can act on a resting order. This rule is the only thing keeping a funded order from resting through that window.
- **Every plan is signed off on its own**: the owner reads the `--check` output and personally places the file. Drill plans included.
- **Nothing retries itself.** An intent ending `unfilled`, `refused`, `rejected`, `partial` or `ambiguous` stops there, and so do a `rest-hold` intent's own two terminals — `rest_hold_expired`, the hold run to its end, and `rest_hold_venue_canceled`, the venue's or the operator's own cancel which the engine deliberately does not undo. Those two are completed intents rather than faults, and stopping is what they are supposed to do. **`ambiguous` means the order may be live at the venue** — read Kraken's open orders in the web UI and establish what actually reached it before placing anything else on that symbol.

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
   - **`kill` — this is a FINDING, never something to sweep away.** No code path anywhere clears the kill file; it is a latch a human engaged, and a restore that brings it back is telling you the backup was taken after a trip. `sudo cat /var/lib/zcrypto-engine/exec/kill` prints a timestamp and the reason that tripped it. Read that reason, work [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped), and remove the file only once the reason no longer holds. Deleting it along with the rest destroys the one record of why the system stopped, at the moment it is trying to tell you.
   - **`restart-hold` — leave it.** The engine writes one unconditionally at every start anyway, and holding at reduce-only until a human clears it is the correct resting state.
   - **`first-fill` — leave it, and never write one by hand.** The engine writes this once, at the first boundary after its first ever fill, and reads it only to refuse: it is what tells the weekly tracking-error trip that the journal still holds the whole position history it measures against. A restore that brings back a `first-fill` older than the journal now covers is a *correct* refusal, not a fault. Writing or editing one by hand tells the trip a history is present that is not, which is the one way to make it latch the kill switch on a healthy engine. **If it is missing on an engine that has ever filled, that is a finding, not a self-healing state.** Once fills exist the engine cannot establish for itself that its journal's head is intact — a prune that happened to cut at a quiet boundary looks identical to a journal that was never cut at all — so it re-dates itself only while the earliest fill it can see is hours old, which is what the healthy path produces. Anything older it refuses to date, and the trip then refuses every week, permanently, with that reason in the log. **That refusal is the correct outcome and no operator action clears it**: the position it would need is not on this host. Do not hand-write a record to make the refusal go away — that is the one move that ends in a latched kill switch on an engine that never misbehaved.

#### 6. Verify by outcome — the window is not closed until every line here reads true

1. **Every intent has a terminal outcome and every order has a terminal state**, from the ledger read: each plan entry `accepted` with empty reasons, each intent carrying an outcome, each order row a terminal `state`.

2. **Every fill carries its fee and its liquidity side**: each `fill` line shows `fee` with a `fee_currency`, and `liquidity` reading the word `maker` or `taker` — never a number.

3. **Two rollover rows per position** in the Kraken ledger export — read by hand, and then read again by the standing reader **in the same session, while the hand read still exists**. From the workstation, against a pulled copy of the engine journal:

   ```
   uv run zcrypto engine tracking-report \
     --journal-dir <pulled journal> --since <first window day> --until <last window day> \
     --ledger-export <the export>.csv
   ```

   **The comparison, and the only one that can qualify this reader**: its `rollover fees` figure must equal the total you just read by hand. A standing reader that has never once agreed with the hand read it replaces is unverified, and this window is the only place the two figures exist side by side — record both in the probe's decisions-log entry, equal or not.

   This is also the first real export the reader has ever seen, so it is where three shipped assumptions get settled. Record what you find for each, in the same entry:

   - **`rollover fees 0.00` against a nonzero hand read means the charge lives in `amount`, not `fee`.** The reader sums the `fee` column; which column a real rollover row carries the charge in was never verified, and this by-value comparison is exactly what catches it. A zero here is a finding about the reader, not about the window.
   - **Only `trade` rows are matched today.** Read the export's distinct `type` values (`cut -d, -f4 <the export>.csv | sort -u`, allowing for quoting). The `row types this reader places nowhere:` line names every type it consumed nothing from and how many — `margin` above all, which a margin position writes carrying the *same* `refid` as its trade. If `margin` appears, the match widens; that decision is yours to record here, not the reader's to guess.
   - **A venue repair guarantees an unmatched id, and that `FAILED` is honest.** A `reconciled` event carries no venue trade id, so the journal gives it a synthetic one that no ledger row can ever match. So the block does **not** have to read `ok`: read the named ids against the window's own repairs first. What must be true is that every unmatched id is *explained* — a repair, or account activity you performed by hand — and that none of them is a trade nobody can account for. That last case is the one thing this comparison exists to catch, and it is a stop.

   Two reading notes. The block prints how many rows it read at all, so an export that produced nothing cannot read as a window that contained nothing. And do **not** run this with `--simulated-fills`: modelled fills carry no venue trade id, so every real ledger row is unmatched by construction — the command says so, and the block means nothing in that mode.

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

7. **Count the journaled gate level across the window's exec records**, on the engine host: `for f in /var/lib/zcrypto-engine/journal/<YYYY-MM-DD>/exec-*.json; do python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['level'])" "$f"; done | sort | uniq -c`. This is the input the weekly tracking-error trip takes its eligibility from, and it is the one reading no other step produces. Every record written outside a window reads `none` — as all 66 of them did before the first window — so what this measures is whether an ARMED window actually journals `full`. If it does not, the restart hold was left set through the window, and the trip is structurally inert even once armed: see `engine-tracking-band` below, and do not set a band until this reads `full`.

8. **Take the week's tracking reading, and record what it produced even when that is nothing.** Nothing schedules this — there is no timer and no unit behind the command, deliberately, so this step *is* the cadence: a window that closes without it leaves no missing artifact for anyone to notice later. From the workstation, against a pulled copy of the journal:

   ```
   uv run zcrypto engine tracking-report \
     --journal-dir <pulled journal> --since <YYYY-MM-DD> --until <YYYY-MM-DD> \
     --gate-from <YYYY-Www>
   ```

   - **`--gate-from` is not optional in practice.** Without it NOTHING is decided whatever the numbers say — every week is measured and none is eligible, which the report states by name in its own footer. The week to pass is the first ISO week whose cycles ran under continuous arming, i.e. a fact about the deployment rather than about the journal, which is why the flag asks instead of guessing.
   - **Confirm the boundary landed, because nothing validates it for you.** A week outside the window is accepted silently — safe in the fail-closed direction, since a wrong week decides fewer weeks and never more, but unremarked. The report echoes `Gate boundary: weeks from <YYYY-Www> onward count`, notes every week it placed before that boundary, and states in its verdict line how many weeks it decided — read all three against what you intended.
   - **A week the report cannot produce is a refusal to record, never a zero to shrug at.** A partial ISO week, a week before the boundary, and a week with no journaled fills each print as measured-but-not-decided or as *no data* — the series not having started is not the same reading as a week of perfect tracking. Write the week labels and their reasons into the probe's decisions-log entry beside the numbers; that record is the only evidence the reading was taken at all.
   - **Today every week reads *no data* and the cost half answers that there are no euro-denominated fills.** That is the correct output before the first fills exist, and recording it is what makes the first real reading comparable to something.

9. **The verdict is recorded** in `docs/research/14.phase6-decisions.md`, and on a fail its fallback topic is registered and queued — step 7 above.

### Retire when

`cli/engine/executor.py` no longer picks a plan file up out of the state directory's `exec/` — check with `grep -n PLAN_FILENAME cli/engine/executor.py`, and a run that finds nothing is the signal. At that point the continuous loop that replaces attended probe windows has landed, and this procedure with it.

______________________________________________________________________

<a name="engine-tracking-band"></a>

## engine-tracking-band — PROCEDURE

### What you are seeing

You are deciding whether to arm the engine's weekly tracking-error trip, or you are looking at the **Weekly tracking error — last verdict** tile on the engine board and want to know what it is telling you. **Nothing has fired**: if the trip had latched, `zcrypto-engine-exec-kill-tripped` would have paged and [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) is the one to work.

### What it means

At every 4-hourly boundary — after the cycle has journaled, and reading nothing but the journal — the engine scores the **most recently closed ISO week**: what its cycles targeted, against what its own fills say it actually held, as a mean drift in bps of NAV. If that mean exceeds the configured band, the engine latches the kill file, cancels everything resting and refuses every further order until a human clears it.

It exists for the failure no other guard can see: an engine that has quietly **stopped placing orders**. Every other execution guard sits behind an operator-authored plan file, so none of them can fire in a window where nothing is being submitted at all — while the targets keep moving and the book keeps standing still.

Four things about it are worth knowing before you touch anything:

- **It ships disarmed and stays that way until a band is set.** `tracking_band_bps` is absent from `[zcrypto.engine]`, and with no band nothing can be exceeded. The tile reads `DISARMED`; that is the correct resting state, not a fault.
- **It carries no state of its own.** There is no checkpoint, no marker file. The week is re-derived from the journal every four hours, so a fill journaled late — filed under the boundary its ORDER was filed under, days after the fact — is folded in at the next boundary rather than lost.
- **It refuses far more often than it decides.** A week short of its 42 boundaries, a week that spent any boundary below the `full` gate level, the week the fill series started in, a week whose records do not carry the prices they were traded at, and a journal whose oldest boundary already carries a fill are all `NOT SCORED`. Each is a deliberate refusal: refusing costs a week of coverage, guessing halts live trading.
- **It has no alert rule of its own, deliberately.** The only value that is a fault — the band breached — latches the kill file, and `zcrypto-engine-exec-kill-tripped` already pages on exactly that. A rule here would double-page one event and would page on nothing else.
- **It stops scoring for good once the journal's head is pruned, and that is by design.** What it measures is cumulative from the engine's first ever fill, while the journal prune deletes whole day-dirs at `engine_journal_retention_days` (60). Once the day holding that first fill ages out, the position bought before the horizon is simply not on this host, and a week scored without it reads several hundred bps high — a latched kill file on an engine that never misbehaved. The engine records the date of its first fill once, in `exec/first-fill`, and from the moment that date falls off the journal it refuses every week with that reason in the log. **There is no operator action that restores it**: the fills are gone. Raising the retention, or journalling the position alongside the cycle's `closes`, is the fix, and both are changes to make deliberately rather than in an incident.

### What to do

**If the tile reads `OUTSIDE BAND`** — the kill file is latched and the alert has already paged. Work [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped). `sudo cat /var/lib/zcrypto-engine/exec/kill` names the week, the mean it measured and the band it was measured against; that text is the only record of why the engine stopped, so read it before removing anything. The engine will not re-score while the file is present, so the first reason stays exactly as it was written.

**If the tile reads `NOT SCORED` and you expected a verdict** — the reason is in the engine log, one line per boundary: `sudo docker logs --since 5h zcrypto-engine | grep 'not scored'` (a bare `--since HH:MM` does not parse; pass a duration or a full timestamp, and confirm the log lines you got are non-empty before reading anything into a quiet grep). One of those lines reads `the evaluation itself raised` and carries a Python traceback underneath it: that is the measurement failing rather than declining, it means the same NOT SCORED on the tile, and it is a defect to report rather than an operational state to work.

**If the tile is absent entirely** — no boundary has been *reached* since this process started, or the family is not shipping. (An unscored boundary still publishes a state, so "not scored" is never why the tile is missing.) Read it by value from the workstation: `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_tracking_state{host="zcrypto"}'`. `(no series)` after a boundary has passed is a keep-regex failure, not a quiet engine.

**To arm it** — three preconditions, in this order, and none of them is optional:

1. **A window has journaled `full`.** Run the count in the probe-window procedure's verify step above. Every exec record written outside an armed window reads `level: "none"`, and the restart hold is written at every engine start and cleared only by hand — so a week spent held reads as fully armed while the engine never traded, which is exactly the state that would latch the kill file on a healthy engine. A week the engine could actually trade must be able to show 42 records reading `full`; if it cannot, the hold-clearing step is what changes, before any band is set.
2. **A band exists that real weeks have been measured against.** `uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <first day> --until <last day>` on the workstation prints each week's realized mean beside the floor the venue's own minimums impose. The band is a number chosen from those readings and recorded in `docs/research/14.phase6-decisions.md`, never one invented here.
3. **The band is deployed as config.** `tracking_band_bps` is read from `[zcrypto.engine]` in the rendered `/opt/zcrypto-engine/zcrypto.toml`; the engine role's template does not render the key today, so arming means adding it there — one line, reviewed like the `exec_armed` line beside it — and converging inside a 4-hourly inter-cycle gap. Verify by outcome at the next boundary: the tile moves off `DISARMED`, and `grafana-query.py` reads a number rather than `(no series)`.

Three standing conditions once it IS armed, each of which silently changes what a scored week means:

- **A verdict needs 42 CONSECUTIVE boundaries at `full` — seven unbroken armed days.** No attended probe window is anywhere near that long, and `zcrypto-engine-exec-armed-too-long` pages after six unbroken hours armed. So an operator who satisfies all three preconditions above and arms during ordinary attended windows gets `NOT SCORED` forever, correctly. **Verdicts only ever arrive in continuous-trading mode**, and that alert's threshold is the thing to revisit first when that mode arrives — before the band, not after.
- **Disarm the band across a `shadow_nav_eur` change only while a cycle record predating the journal's `nav` key is still inside the scoring window.** Each cycle is now scored under the NAV journaled with it (`cli/engine/tracking.py`'s `cycle_nav`, T0150); older records fall back to the live scalar, and for those a converge still re-prices a week that closed under the old value — halving NAV roughly doubles every reading of a week nobody traded differently, straight into a latched kill file.
- **Disarm the band across a basket widening.** The trip demands every model leg's target in every record it reads, so the first record written under a wider basket makes every earlier one un-scoreable. The refusal is the safe direction, but it lasts until the whole scored span post-dates the widening — a full week — and reads as a broken trip if nobody expects it.

**To disarm it** — remove the key and converge. Nothing else clears it; the disarmed state is the absent key.

### Retire when

`tracking_band_bps` is absent from `cli/config.py` — i.e. the trip was replaced rather than merely disarmed.

______________________________________________________________________

<a name="engine-flatten"></a>

## engine-flatten — PROCEDURE

### What you are seeing

**Nothing fired.** You are here because the book has to be flat within minutes — a crash, a provider-level event, an engine that is dead with positions open — and you have decided to close everything at market rather than wait.

Real money moves, at whatever price the market gives. This closes the **whole account**: every resting order, every margin position, every non-EUR balance, including coin the engine never bought.

### What it means

`sudo zcrypto-flatten` runs one command in a one-off container built from the same image digest the engine runs, so the venue adapter pressing the button is the one that was verified. With `--execute` it first writes the engine's kill file, then stops the engine unit and waits for it to be gone, and only then reads the account and asks you to type a word.

**What it does**: writes the kill file · stops the engine · cancels every resting order account-wide · closes every margin position with a reduce-only market order · sells every non-EUR balance at market, in two passes so a coin with no EUR pair is sold to BTC and the BTC is then sold to EUR · writes a record of every request and every answer.

**What it does not do**: it does not clear the kill file, does not restart the engine, does not touch the engine's execution ledger, and does not close anything partially — it is the whole account or nothing.

**Three limits it carries today.** The reduce-only market close on a margin position has never been sent live from this repository on any order type; the first real press through this wrapper — on a position minted for the purpose against the current pin, with a margin leg wherever `ordermin` allows — is where that is first proven, and until its `docs/reference/adapter-verification/` row records it, treat a margin close as unverified and read Kraken's own positions page afterwards by eye. The drill program's decision-to-flat drill is a later, separate measurement and does not lift this caveat. And the five account reads have been proven against the live venue only once the [read-only dry run](#flatten-read-only-dry-run) recorded in `docs/reference/adapter-verification/` has been run through this wrapper; until that row exists, a live `--execute` is being run against read shapes nothing has confirmed.

<a name="flat-verdict-blind-legs"></a>

**And the third: the flat verdict is blind on five pairs — exit 0 can be a false all-clear.** The venue adapter caches its instruments under Kraken's `AssetPairs` key (`XXBTZEUR`) and looks an open order up by the pair name the order itself carries, which is the altname (`XBTEUR`); on a miss it drops the row and returns success with no warning. Five of the twelve traded legs — **BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR, ETH/BTC** — are spelled both ways, so an order resting on one of them is absent from every open-order read this command makes: the dry-run preview's count, and the final read the exit code is derived from.

**The cancel is not affected.** It is one account-wide cancel that names no pair, and it does reach an order on those five legs. What is affected is the verdict, which is why the mitigation is real rather than hopeful: **confirm open orders on Kraken's own page after every press — step 4, and this is why it is not optional — and if one is still resting, press the button again.** The second press sends the account-wide cancel again.

This is a known, deliberately unfixed limit (registered on \[[T0160]\]), not a defect to report — the tidy-looking correction, "the read should be complete", is a change to the adapter's instrument cache and is exactly what has been deferred. Do not delete this paragraph in a docs pass.

### What to do

1. **Read the plan first. It sends nothing.**

```
sudo zcrypto-flatten
```

It prints the resting orders it can see — a floor, not an inventory: the count omits any order on the five pairs [the third limit](#flat-verdict-blind-legs) names, though the cancel still reaches them — every position it would close with its side and quantity, every balance it would sell with an estimate at the taker rate, every balance below the venue's minimum that it will list and not send, and every balance no EUR or BTC pair can carry. It exits 0 and changes nothing — 3 if the venue could not be read, 1 if the plan could not be printed, both of them having changed nothing either. Its reads run beside the still-running engine and share the trade key with it, so one engine order or cancel may be rejected around them; the engine reconciles that at its next 4-hourly boundary.

2. **Press it.**

```
sudo zcrypto-flatten --execute
```

The kill file is written, the engine is stopped, the plan is printed again from a fresh read, and it asks you to type `FLATTEN`. Anything else aborts and nothing is sent. It reads the word from the terminal, never from a pipe, and there is no flag that skips it.

3. **Read the exit code.** It is the whole verdict, and it never reads a single leg's answer.

| code | what it means | what to do |
| -- | -- | -- |
| **0** | no resting order, no open position, nothing sellable left — and blind to the five pairs [the third limit](#flat-verdict-blind-legs) names | go to step 4, which is what catches that |
| **1** | refused with nothing sent, the refusal naming which gate stopped it | nothing was sent; fix what it named and run it again |
| **2** | something is still open, or the account-wide cancel failed, or a read after the cancel failed | go to step 5 |
| **3** | the venue could not be reached or read **before anything was sent** | nothing was sent; the account is as it was |

4. **Confirm it by eye on Kraken.** Open orders and open positions on Kraken's own pages. The engine stays stopped and the kill file stays in place until you decide otherwise — that is what stops anything re-opening.

5. **On exit 2, read the record.** It is `/var/lib/zcrypto-engine/exec/flatten-<timestamp>.json`, and the command prints its path. Each leg carries what was sent and what the venue answered.

- **Every leg answered without an error, and something is still listed?** The venue may simply not have settled yet — the final read is taken immediately. **Run it again**; a second run finds less to do and does it. A second exit 2 naming the same residual is real.
- **A leg reads `unclosable_below_minimum`?** That label is what *this command* read before it sent anything: the position was smaller than the pair's minimum order size. It is never read off the venue's answer, so **read the `error` beside it in the record first.** No `error` at all means the quantity floored to nothing and there was never an order to send. An `error` naming a rate limit, a temporary lockout or any other passing condition is a refusal that may not be about the size at all — **run the command again**, and judge the label on what the second run answers. An `error` that keeps saying the order is too small is the real case: no order can clear that remainder; only Kraken's own settle-position action in the web UI can, and the adapter cannot send it.
- **A balance reads `no_eur_or_btc_pair`?** The venue lists no EUR and no BTC pair for it, so this command cannot sell it. Sell it by hand on Kraken against whatever pair exists.
- **A leg reads `dust_below_venue_minimum`?** Nothing is wrong. The venue would reject that order, and a balance that small is not exposure.
- **A leg reads `no_reference_price`?** No book price backed it: either it surfaced after the plan was priced — no book is read once the cancel has gone out — or its own book could not be read, or answered no usable price. It was sent anyway, sized on the venue's quantity floor alone. The order still went out; the label asks nothing of you, and what the venue answered beside it is the answer.
- **A position reads `pair_not_listed`?** The venue's listing carries no pair for it, so nothing could be sized and no order was sent — everything else was still cancelled, closed and sold. Close that position by hand on Kraken.
- **A position reads `unrecognised_position_side`?** The venue answered a side this command cannot derive a close from, so nothing was sent for that row — everything else was still cancelled, closed and sold. Read the row on Kraken's own positions page and close it there; the side it shows is the finding.
- **A residual reads `resting_order`, `sellable_balance` or `unjudgeable: …`?** These describe the final read rather than a decision made before sending: an order still working, a balance still above the venue's minimums, and a balance whose pair's constraints could not be read back. The first two mean the sweep did not finish the job — run it again. The third means that balance could not be judged at all: check it by hand on Kraken.
- **The record says a read after the cancel failed?** The account may have moved and the run stopped where it stood. Read Kraken's own pages, then run it again.

6. **Do not clear the kill file to restart the engine until you have decided the reason no longer holds.** Clearing it is the same procedure as for any other latched halt, in [`engine.md`](engine.md#zcrypto-engine-exec-kill-tripped).

<a name="flatten-read-only-dry-run"></a>

### The read-only dry run that proves the five reads

Not part of a press — nothing is sent. This is what produces the record the SECOND of the three limits above waits on — the first waits on the row the first real press writes, and the third is deliberately unfixed and waits on nothing, so its by-eye confirmation after a press stays mandatory.

1. **After the engine converge that carries the wrapper, never before.** `/usr/local/sbin/zcrypto-flatten` reaches the host with that converge and not earlier.
2. **With the engine running and a NON-EUR spot balance the command can sell.** `spot_legs` skips the euro, skips a zero free balance, and skips a code it cannot resolve to a listed `/EUR` or `/BTC` pair — and the book read, the fifth shape, is made only for a leg. With no leg at all — nothing sellable and no margin position open — four of the five are proven while the row would say five. If the account has none, `infra/scripts/mint-with-vaulted-key.sh` mints one. It mints every ingredient the account is missing — the sellable balance, a resting order and a margin position — and there is no way to ask for only one, so read the printed plan for what it will actually send. Nothing unwinds them: the script has no cancel path, so the resting order and the position stay in the account until a real press closes them or someone closes them by hand on Kraken's own pages. It is attended, run from a workstation rather than on the host, and prints its plan without sending anything until `--execute` and a typed word; it places orders and cannot cancel them, so read the plan before confirming. The key it uses is IP-bound: `order-semantics-verification.md` section 1.3 adds the workstation's address and section 7.3 removes it again — the removal is mandatory, not an afterthought.
3. **On the engine host, through the wrapper:**

```
sudo zcrypto-flatten
```

4. **Record it**, in the shape drill G's extra reading uses: discharged into `docs/reference/adapter-verification/<the running version>.md` beside that version's probe table, as a row proving the five read shapes against the real venue. When a margin position is present, record what the positions read returned **against a position known to be there** — that is the first time this read has been exercised with something to find, and a position seen is the whole proof. Record the venue's own handling of the client order ids in the same row: the ids the minter sends are longer than any this repository has measured the venue accepting, and none has ever been read back from the venue, so quote each id verbatim, both as the minter sent it and as Kraken's own order pages show it — the resting leg's id under Open Orders, the two market legs' under Closed Orders, since those are IOC and are gone before the run ends — and note whether each was accepted, refused, or came back shortened.

That row is the operand \[[T0160]\]'s bump sub-item evaluates — it is the operand that completes that trigger, so it is live, not a stale record to tidy away.

### Retire when

`flatten` is no longer a subcommand of `zcrypto engine` in `cli/engine/command.py`, or `/usr/local/sbin/zcrypto-flatten` is no longer rendered by the engine role.
