# Engine — attended procedures

Nothing fires these; you run them deliberately, and real money moves. Alert-triggered sections stay in [`engine.md`](engine.md).

<a name="engine-restart-margin-position"></a>

**An engine converge or restart with a Kraken margin position open is admitted by one test, and refused otherwise until the nautilus-trader build the engine runs carries upstream #5065.** Kraken's margin position report carries no entry price, which the node's startup reconciliation needs to rebuild an open position and which #5065 adds; the engine's cache holds its own orders and positions, entry prices included, across a restart, and that is what the test reads. Four reads before any procedure below converges or restarts the engine: the Cache board's proxy row, where `Sentinel checks passing on the most-agreed backend` reads 2 or 3 and `Sessions through the proxy` reads 1 or more; the engine's last boot line in Loki under container `engine`, `cache restore: N order(s), M position(s) restored` with a `cache restore: position <instrument> <quantity> @ <entry price> (<strategy>)` line per open position, under the engine's own strategy or `EXTERNAL` — a fill made while the engine was down beside a restored position shows as a second line under `EXTERNAL`, so an instrument's figure is its lines summed; Kraken's positions page, or `kraken positions -o json` on the workstation, for what is open; and the engine's log under the same container since that boot line for the executor's WARNING `a fill on restored order <id> credits nothing until the venue is read -- the next restart is taken flat`, logged at the fill whatever the venue read after it answers. Until the cache's live proof is recorded in `docs/reference/drill-log.md` — a restart with a restored position open whose boot line reads the position at Kraken's entry price — the test admits the proof window's own restart alone, the window's Step 6 on `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md`; from that entry on, the restart is admitted when every open position is one that boot line counted as restored — its instrument's lines summing to Kraken's figure, none at entry price 0 — or one this engine opened after that boot — the order that opened it this engine's own, placed after that boot, whether it filled while the engine ran or while it was down — no cache outage has fired since that boot, and no restored order has filled since it: a `zcrypto-engine-cache-write-failed`, `zcrypto-cache-proxy-no-backend` or `zcrypto-cache-proxy-no-engine-session` page since the boot line leaves the store behind ([`cache.md#zcrypto-engine-cache-write-failed`](cache.md#zcrypto-engine-cache-write-failed)), and that WARNING marks a fill the library may have booked twice into the cache, which the next start's reconciliation meets as a difference against the venue — a diff fill at the stored price, or a failed start where it crosses zero — without saying whether it did, so either takes the restart flat. Otherwise close the position first or wait: a cold start, a lost database, or a position the cache never saw — opened by hand, or by an order the cache never held — goes one of two ways on 2.0.0rc6.dev20260921, depending on the pair's fill history: the start fails with `Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` and the container restarts into the same failure, or it boots with the position's entry price at 0, where the one reading that goes wrong is the realized-PnL gauge (`zcrypto_exec_realized_pnl_eur`). A start already failing that way is ended by the red button's press ([`#engine-flatten`](#engine-flatten)): it stops the unit and reads the account through its own client, which runs no startup reconciliation. The test ends once the engine runs a pinned build carrying #5065; the converge that puts it there is still a start of the engine and takes the test like any other.

**A spot lot is outside that test, and its restore lines do not sum to what Kraken holds.** On 2.0.0rc6.dev20260921 with `spot_account_type=MARGIN`, a start restores a held spot lot as one line under the engine's own strategy at the lot beside one `EXTERNAL` line at minus it: the adapter reports flat for an open spot position that Kraken's margin positions do not list, and startup reconciliation books the difference under `EXTERNAL`, with no fill made while the engine was down. The instrument's lines then sum to 0 while Kraken's balance holds the lot. The test above reads Kraken's margin positions, and a spot lot is none — `kraken positions -o json` prints `{}` with one held — so it neither admits nor refuses a restart over spot lots. A spot lot's comparison with Kraken is the startup pass's WARNING `the venue holds <quantity> <instrument> where the Cache reads 0.0 -- the position gauge takes the venue's figure at the startup pass`, read against `kraken extended-balance -o json` on the workstation. `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md` records the defect, and [the rung-2 box's restart step](#rung-2-after-a-restart) is the procedure for a restart with spot lots held.

<a name="engine-probe-window"></a>

## engine-probe-window — PROCEDURE

### What you are seeing

You are about to run — or are in the middle of — an attended live-order probe window on the engine. **Nothing has fired**: no alert sent you here and no guard tripped. You opened this because a probe window is being planned or is under way, and this is the only sanctioned way to run one.

Real money moves — roughly €10–30 per leg — on the host that holds the live trade key.

### What it means

The engine's order path submits **only operator-authored probe plans**, and only inside an attended window bounded by two arming keys: the `exec_armed` value baked into the deployed config, and an `armed` file placed on the engine host. Both must be present for anything to be submitted; removing either one disarms it. Where a step's *position* in the sequence matters, the step says what happens if you take it early — that ordering is load-bearing, not ceremonial.

Where everything lives — never guess these:

- **Engine host** `zcrypto` (`ssh zcrypto`); the container is `zcrypto-engine`; the CLI and the rendered config live inside it.
- **A converge that restarted the engine re-owes the proving cycle, whatever the run was tagged** (no count command: the proof is a journal artifact on the engine host and reading it is an operator act nothing in the tree records). Settle it by reading `sudo docker inspect zcrypto-engine --format '{{.State.StartedAt}}'` either side of the run: a `docker`-tagged converge can take the engine with it, so no tag settles it. The disarm step below spells out what that cycle has to look like; its re-owe is one instance of this rule.
- **Control files**: `/var/lib/zcrypto-engine/exec/` — `armed`, `kill`, `restart-hold`, and the plan file `probe-plan.json`. Presence is the whole protocol; contents are informational.
- **Journal**: `/var/lib/zcrypto-engine/journal/<YYYY-MM-DD>/` — `cycle-<HH>.json`, `exec-<HH>.json`, `venue-<HH>.json`.
- **`<HH>` is the 4-hourly cycle boundary** (00/04/08/12/16/20 UTC), never the wall-clock hour (no count command: `_boundary` in `cli/engine/executor.py` floors the hour an exec record is filed under). A record written at 09:14 UTC is `…-08.json`.
- **Rendered config**: `/opt/zcrypto-engine/zcrypto.toml`, rendered by the deploy from `infra/ansible/roles/engine/templates/zcrypto.toml.j2`. Never hand-edit it on the host (no count command: a hand edit on the host is an operator act nothing in the tree records); the next converge overwrites it.

Three reads you will use repeatedly. **Scope every `docker inspect` to one field with `--format`** — this container carries the live trade key in its environment, and an unscoped inspect prints it.

**The gate read** — run it in the container, which is where the CLI and the config are:

```
sudo docker exec zcrypto-engine zcrypto engine exec-status
```

It prints `level=<none|reduce_only|full>`, then a `reasons=` line carrying every condition that restricted the level, comma-separated — a single `-` means none — then every gate input on its own line. It re-evaluates the gate on the spot, and it is the only **live** view of the reasons — they never reach Grafana, and `zcrypto_exec_armed` conflates the two arming keys into one gauge, so no dashboard can tell you which key is missing.

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
        txids = sorted({ev["venue_order_id"] for ev in r["events"] if ev.get("venue_order_id")})
        print(" order", r["client_order_id"], r["state"], "filled_qty", r["filled_qty"], "kraken", ",".join(txids) or "-")
        for ev in r["events"]:
            if ev.get("event") == "fill":
                print("     fill", ev["at"], ev["qty"], "@", ev["px"], "fee", ev["fee"], ev["fee_currency"], ev["liquidity"], ev["trade_id"], "credited", ev.get("credited", "whole"))
            elif ev.get("event") in ("reconciled", "recancelled"):
                print("    ", ev["event"], ev["at"], ev.get("venue_filled_qty", ""), ev.get("venue_order_id", ""))
            elif ev.get("type") == "ambiguous":
                print("     ambiguous", ev["at"], ev["what"])
            elif ev.get("reconciliation"):
                print("    ", ev["type"], ev["at"], "reconciliation: true, minted by this engine")
PY
```

`kraken` is the Kraken txid, or txids, that the row's acceptance and fill events recorded, `-` for a row that recorded none. An `ambiguous` line marks a row whose venue outcome this engine could not establish: a submit that raised, or the startup pass's or the re-read pass's mark on a row it could not match to a venue order ([step 4 of the arm](#adopt-pass-by-txid)); its `what` says which.

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

1. **Sweep for blockers, and present the result together with the arming request.** Read `## Open` and `## Partially done` in `docs/open-topics/README.md`, and grep `.local/memo.md` for anything in flight against the engine. "Ready" without the sweep is not ready.

2. **Confirm the deployed code is the code you tested.** The engine row in `docs/reference/fleet-pins.md` records the digest running on `zcrypto` and the revision it was built from. Confirm the running digest matches — `sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine` — and that your working tree is at that revision. Then run the two guards that catch a drift between the committed cost floors / ratified basket and what the venue reports: `uv run pytest tests/test_costmin_drift.py tests/test_basket_concordance.py` → expect `2 passed`. A failure means the floors or the basket have moved since that image was built; stop, do not arm. **`1 passed, 1 skipped` is NOT a pass** — the drift test skips itself when no refdata snapshot is present under the gitignored data root, so run this in a tree that has one; a skipped drift guard reads green and has checked nothing. Add `-rs` if you want the skip reason spelled out.

3. **STOP unless the engine's nautilus version has its own order-semantics verification.** The adapter's margin/short/post-only and reconciliation semantics are verified by hand, against real orders, once per version — one record per version under `docs/reference/adapter-verification/`, indexed by `cli/engine/order-semantics-verified.json`, which is the file both arming guards read. Each record describes the version it ran on and no other: a bump may change fill, cancel, post-only or reconciliation behaviour without changing anything this repo's tests can see, because the tests never place an order (no count command: the suite's `ZCRYPTO_LIVE_VENUE_TESTS` opt-in tests read the venue and submit nothing). So a bump merges only with its fresh ~€0.20 zero-fill + round-trip pass, and this step checks the version the engine runs against the record.

   Read the version the engine is actually running (scope the exec to this one command — the container carries the live trade key):

   ```
   sudo docker exec zcrypto-engine python -c "import nautilus_trader; print(nautilus_trader.__version__)"
   ```

   Then confirm `docs/reference/adapter-verification/<that version>.md` exists — the file is named for the version string exactly as the interpreter spells it — and records a PASS. If none does, **do not arm**: deploy an image whose build the record verifies, which for this build means its bump, attended pass and write-up merged in one PR first — the harness is `infra/scripts/kraken-order-semantics-probe.py` and the attended procedure is [`order-semantics-verification.md`](order-semantics-verification.md). Never reason that the previous version's PASS "probably still holds" — that is the whole reason this gate exists.

   **This step is enforced mechanically in TWO places, and they are complementary — do not delete either as duplicative of the other.** Both read the same committed record, `cli/engine/order-semantics-verified.json` (it lives under `cli/` because the engine image copies only that directory, so a record under `infra/` would be unreachable from the running engine):

   - **The converge** — the engine Ansible role refuses a converge that would render `exec_armed = true` on a version absent from the record. Bypass `-e '{"arming_override": "<reason>"}'`, reason-required, like `canary_override` and `pins_override`.
   - **The arming** — the execution gate refuses at runtime when the *running* interpreter's `nautilus_trader` is absent from the record: `level=none`, `reasons=…,nautilus_unverified`, journaled into `exec-<HH>.json` like every other reason (no count command: `_load_or_new` in `cli/engine/execledger.py` writes the verdict's reasons whole).

   Neither subsumes the other. Arming takes two keys, and the arm file is placed by hand long after any converge — so a host that converged armed on a verified version and later took a newer image would pass the converge assert and still be arming an unverified adapter; the gate catches exactly that. Conversely the gate cannot stop a converge from *rendering* an armed config. If either fires it is telling you what this step says; do not override it to get a probe window started.

   **A PASS is not the whole gate — read that version's record under `docs/reference/adapter-verification/` and its `## Owed checks not discharged by this pass` section and discharge every open item before arming.** A pass records what the run could measure; anything it could not lands there, and a version whose record still carries an open item is not cleared to arm however green the verdict above it reads. The passes deliberately run inside the inter-cycle gap, so the checks that land there are typically the ones a later clock has to answer — take the reading and write it back into that same section as its outcome, so the record settles rather than accumulating. The record is the inventory; a copy of it here drifts behind it.

4. **On the FIRST arming window for a nautilus version, take the unmatched-external baseline — before anything is thresholded on it.** The external-order observer is registered when the node is built rather than at `on_start`, so events published during the engine's own startup reconciliation can reach it and be counted `unmatched`. That is safe — they are logged and dropped, and nothing is attached to act on yet — but it means `zcrypto_exec_external_events_total{disposition="unmatched"}` may rise at **every healthy boot** (no count command: what startup reconciliation publishes is the stripped nautilus wheel's behaviour), and an alert thresholded as though `unmatched` meant "an operator must act" would page on a clean start.

   Two things, and the order between them is the whole point:

   1. **Measure it.** With the engine **disarmed**, read the counter immediately before and immediately after one clean engine start and record the difference — that difference is the healthy-boot baseline. From the workstation: `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_external_events_total{host="zcrypto"}'`. `(no series)` is a FAIL of the telemetry path, never a zero (no count command: `infra/scripts/grafana-query.py` prints `(no series)` for an empty result, not a zero). Write the number into this version's `docs/reference/adapter-verification/<version>.md` record, beside the probe table, where the next reader of that version will look for it.

      **The baseline belongs to the version, and does not carry across a bump.** It is a property of a process running that wheel, so a reading taken on one version says nothing about the next: look for it in the record of the version you are arming, and take it if it is not there — `2.0.0rc4.dev20260825`'s reading of 0 on a flat account is in that version's record. The step stays written in before/after form because that is the cheaper procedure at a window you are already holding open; either route answers it.

      **What that 0 does NOT cover, and what to do about it here rather than anywhere else:** it was measured on a FLAT account — no open orders, no positions. That is every boot before rung 1 and none after it. **The first disarmed boot that carries live orders or positions is a reading to take**, because startup reconciliation then has something to reconcile and may count it; take it the same way, and write it beside the 0 in that version's record. `2.0.0rc6.dev20260918`'s record holds the live-ORDERS half, and `2.0.0rc6.dev20260921`'s a boot carrying one SPOT lot. A boot carrying a MARGIN position is still unread, and until it exists no threshold may assume such a boot behaves like the boots those records hold.

   2. **No alert is owed on this counter — do not author one.** `unmatched` rising while `zcrypto_exec_armed` is 0 is the obvious candidate and the signal is wrong for it: the counter the rule would gate on counts your own hand-placed orders while the engine is disarmed, so the rule would page on your own account activity, and a rule on a forensic counter is a decision of its own. `zcrypto_exec_armed` is not the obstacle: it follows an arm or a disarm within a minute, on the executor's idle refresh. Visibility is unaffected: engine-dashboard panel 61 plots both dispositions. The full reasoning is in `tests/test_infra_alert_rules.py`'s `NOT_A_FAULT_SIGNAL` entry for this metric.

   For a FUTURE nautilus version the baseline reading in item 1 is still owed; the alert is not.

5. **On the same first window, and only after the baseline above has a number, read how often the engine mints an order's terminal event for itself.** Past its in-flight retry budget the execution engine stops waiting on an unanswered order and publishes that order's `OrderCanceled`, or an `INFLIGHT_TIMEOUT` `OrderRejected`, on its own authority. The executor treats every one of those as an unknown venue outcome: the intent ends `ambiguous`, nothing is resubmitted, and the plan halts; on an order the startup pass adopted, the row reads `ambiguous` instead, until the executor's re-read pass settles it from the venue's own report on its next tick with nothing in flight, or a startup inside the re-attach window where the pass could not read (the `Three terminal outcomes` paragraph below names the window and what the entry records past it), and its intent is the pass's, written before the venue answered, or left `pending` when the pass's ledger or venue read failed or the pass latched the kill switch, when no startup writes it while the latch's cause stands; read Kraken's open orders — an order still resting there is cancelled by hand on that page, and one that is gone was cancelled or filled, which its entry in Kraken's closed orders, the positions page and the row's `filled_qty` tell apart; the pass runs after the mint with the sockets up, or after the sockets' return where the mint fell inside a cut, and cancels what still rests, so read its `re-read pass reads … row(s)` and `re-cancelled …` lines before the hand cancel (drills A1, G and F2 read them). That is the right answer and it is also a **plan-stopping** one, so how often the machinery fires decides how often an attended window ends on a slow venue rather than on a real result (no count command: `_strand_ambiguous` in `cli/engine/executor.py` ends each such intent; the version's record holds the rate, not a count).

   Three readings, none of which needs new instrumentation. From the workstation:

   ```
   uv run python infra/scripts/grafana-query.py 'zcrypto_exec_orders_total{host="zcrypto"}'
   uv run python infra/scripts/grafana-query.py 'zcrypto_exec_external_events_total{host="zcrypto"}'
   ```

   and on the host, the engine's own account of each timeout (scope the read to this one command; a bare `--since HH:MM` does not parse, so pass a duration, and confirm the output is non-empty before reading anything into a quiet grep):

   ```
   sudo docker logs --since 24h zcrypto-engine | grep -c INFLIGHT_TIMEOUT
   ```

   `outcome="ambiguous"` is where a minted terminal on the plan's own order lands, and that is the plan-stopping rate; one on an order the startup pass adopted moves no outcome and is the routine end of an adopt-pass cancel on this wheel, its `was reconciled, not received` line a WARNING, so those lines count the mints on both paths and the outcome counts the ones that stopped a plan, read the same way as the timeout count, with `sudo docker logs --since 24h zcrypto-engine | grep -c 'was reconciled, not received'`; zero is the expected reading where the window had no adopted cancel. `disposition="unmatched"` is where a whole order the engine synthesized to close a position discrepancy lands — it arrives under the reserved external strategy id, matches no ledgered row, and is dropped, which is why this reading is only meaningful **against** the healthy-boot baseline from step 4: without that number a clean start's own reconciliation traffic is indistinguishable from a synthesis. `(no series)` on either family is a FAIL of the telemetry path, never a zero.

   **Zero is the expected reading while nothing has been submitted and no adopted order was cancelled at a startup, and it is still worth taking.** A non-zero one before any order exists, with no adopted cancel behind it, means the machinery is firing on something nobody has modelled — read the log lines and understand them before arming, rather than after. Record the numbers in this version's `docs/reference/adapter-verification/<version>.md` record beside the baseline.

6. **Confirm funding covers the plan, by hand, before the tooling does it for you.** Take the free EUR balance from the venue-truth read — the live balances spell that key **`EUR`**, not `ZEUR`; the engine still tries `ZEUR` first because the adapter's instrument-quote surface does spell the euro that way, so both keys are read and whichever the record carries is used. The plan's total `notional_eur` must be at or under `exec_max_plan_notional_eur` in `/opt/zcrypto-engine/zcrypto.toml` (rendered `100.0`), and `sum(notional ÷ leverage) × 2.5` over the margin intents must fit under that free balance. `probe-plan --check` recomputes both below and refuses on either — this step is so you learn it before the window, not during it.

7. **Only the account owner authors and places a plan.** (no count command: who authors and places a plan is an operator act nothing in the tree records) A plan file the owner did not place does not exist to this process.

8. **Read the account through the second producer, and compare before arming.** The engine reconciles the account through its own Nautilus client at every restart (no count command: `reconciliation=True` in `cli/engine/node.py`; reading the two counts against each other is an operator act nothing records). That client reads the account's orders and positions unscoped and resolves a pair under either of Kraken's spellings, and an open order on a pair its listing does not carry stops the start with `Failed to get mass status from KRAKEN` rather than dropping out of the count. The Kraken CLI reaches the same account by a separate implementation, so a disagreement between the two is the finding and never a tie-breaker. From the workstation only (`kraken-cli` never runs on a remote host (set: the non-Markdown files under `infra/` and `cli/` — roles, compose templates, units, scripts, and the Python that runs on the engine host — with the counter itself excluded; count: `infra/scripts/count-list.sh kraken-cli-on-infra-surfaces`) — CLAUDE.md `## Secrets`): `kraken open-orders -o json`, `kraken extended-balance -o json`, `kraken positions -o json`, `kraken trades-history -o json` — whose readings the step's first run recorded in commit `5e18e4541` — one command's field name and the others' values rather than full shapes — read beside the boot's `Received <n> order(s), <m> fill(s), <k> position(s)` line and the `external`, `open` and `positions` fields of its `Reconciliation complete for KRAKEN` line: `sudo docker logs --since 30m zcrypto-engine 2>&1 | grep -E 'cache restore|Received [0-9]|Reconciliation complete|the venue holds|Unresolved positions|Failed to get mass status|could not be read|fill on restored order|instrument not in cache|order event ignored|Failed to load account|CRITICAL'`, its duration reaching back past the engine's start, which `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine` prints — `30m` straight after a restart, `96h` for a boot four days old — and its output confirmed non-empty before anything is read into it. The narrowing drops the burst of ERROR lines each start of this build logs from the library's cache load, `Failed to load instrument` and `Failed to deserialize currency` for cached instruments outside the basket; they page nothing. On this build under `spot_account_type=MARGIN` neither `<k>` nor the `positions` field counts Kraken's positions: `<k>` also counts one adapter report for each position the engine's cache holds open on a spot instrument, a held lot's long and an `EXTERNAL` offset alike, and `positions` counts the reports reconciliation acted on. Both are recorded beside Kraken's positions read and compared with nothing; the margin comparison is Kraken's own list. The trades the CLI lists compare with the `Received … fill(s)` figure plus the boot's `TradesHistory: instrument not in cache for pair …, skipping trade …` WARN lines, one per trade on a pair the listing no longer carries; the `fills` field of `Reconciliation complete` counts the fills applied to the orders it reconciled, not the history, so it is not the figure to compare. An order the CLI lists that the boot line did not count is looked for in the same log, where the observer logs each external order event it cannot match to a ledgered row (`external order event ignored: …`); an order the log never names is outside the engine's view, and the engine's count alone never arms. `hold_trade` in `extended-balance` is the EUR the venue holds against resting orders. Record the four CLI counts and the held amount beside the boot line in the window's arming record.

#### 2. Arm — two keys, in this order

1. **Read the digest the engine is running**: `sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine`. This converge changes no image — you pass that same digest straight back, so nothing is re-pinned, no secondary bake is owed, and the pins check passes against the row already in `fleet-pins.md`.

2. **Edit one line** in `infra/ansible/roles/engine/templates/zcrypto.toml.j2`: `exec_armed = false` → `exec_armed = true`. There is deliberately **no** `-e` override for this value — arming is a reviewed one-line diff in the repo, not a flag anyone can type on a command line.

3. **Converge, inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC — the play refuses outside it), **with no Kraken margin position open beyond those [the restart rule](#engine-restart-margin-position)'s test admits**:

   ```
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine \
     -e converge_primary=true \
     -e engine_image_digest=sha256:<digest-from-step-1> \
     -e cache_proxy_image_digest=sha256:<the running proxy digest>
   ```

   The proxy digest is read the same way, `sudo docker inspect --format '{{.Config.Image}}' zcrypto-cache-proxy`: the engine role refuses an empty one.

   `converge.sh` runs the `--check --diff` preview first and then takes a typed confirm of the literal string `zcrypto`. **Read the preview**: exactly one line of `/opt/zcrypto-engine/zcrypto.toml` changes, `exec_armed = false` → `exec_armed = true`. Anything else in that diff means your tree does not match the fleet — abort and reconcile the tree first.

4. **The restart latches the reduce-only hold — verify reconciliation before you clear it.** The gate read prints `level=none` and `reasons=arm_file_absent,restart_hold` — those two, in that order. If `config_not_armed` is still in the list the converge did not land the new value; fix that before going on. A third reason `venue_not_online` alongside them is not a fault of this step and not something to fix here: Kraken itself is not `online`, nothing can be submitted until it is, so wait it out and re-read. Then run the venue-truth read and confirm the positions and balances you are starting from — no open positions, EUR only (no count command: the starting account is the venue's state, read by hand at the window).

   <a name="adopt-pass-by-txid"></a>

   **If the restart left an order resting at the venue, its ledger row is preserved and its later fills still land in it.** The startup pass keeps a resting order only when the ledger carries it as a reduce-only row; that row survives and is re-attached. After a restart the venue's resting order is reconciled under an external identity and named by its Kraken txid, because the adapter's order read carries no client order id back — so the pass finds an order's row by the engine's own id first and then by the txid the row recorded when the venue accepted the order (each fill records it as well, for an order whose acceptance never reached the ledger). The engine watches that identity's event stream too, matching each event on it by either id against exactly those re-attached rows, so a fill landing on such an order appends to its row, moves the execution counters, and latches the kill switch on an overfill, the same as a fill on an order this process itself submitted. The row is current state, not only a record of what happened before the restart; Kraken's own open-orders and trades views and the next `venue-<HH>.json` are independent corroboration rather than the only place the fill exists.

   **An order that closed while the engine was down is read at the venue by its txid, in one read at startup.** The node's own startup reconciliation reads open orders only, so an order that filled, was canceled or expired during the downtime is in the engine's cache under no name. When a preserved row names such an order — an open row whose order no longer rests, or a closed row with fills, the kind a withdrawn fill lands on — the pass reads the venue's open and closed orders once, back to an hour before the earliest such row's boundary. It makes that read through a second client on the trade key, before it sends a cancel and before a plan can be picked up, and not at all when no row needs it; it needs the key's *Query Closed Orders & Trades* permission, which the node's own startup read of the trade history already needs. A report it finds for a row takes the same comparison a resting order's figure takes, described below.

   **A failed read of the venue's orders refuses every plan until the engine is restarted.** The rows that needed it are left exactly as they were, none of them is marked, and the kill switch is not tripped: an unread figure is not a divergence. The engine logs one CRITICAL line, `the venue's orders could not be read at startup -- N ledgered row(s) were never compared against venue truth; every plan is refused until the engine is restarted`, and each plan placed after it is journaled `refused` with the reason `the startup reconciliation could not read the venue's orders, so N ledgered row(s) were never compared against venue truth -- restart the engine to retry`, then deleted, which the ledger read shows. The remedy is that restart, inside the inter-cycle gap and with no Kraken margin position open beyond those [the restart rule](#engine-restart-margin-position)'s test admits; the new process reads again.

   **With the engine's cache enabled, a failed read of the orders the cache restored refuses every plan until the engine is restarted too.** Which ledgered rows the cache holds a copy of is then unknown, so the startup pass takes no row's figure from a copy, only from the venue's report. The engine logs one CRITICAL line at start, `the restored orders could not be read at start -- every ledgered row is read at the venue as a restored one, and every plan is refused until the engine is restarted`, and each plan placed after it is journaled `refused` with the reason `the restored orders could not be read at start, so no ledgered row can be told from one the Cache restored -- restart the engine to retry`, then deleted. The remedy is the same restart, under the same conditions; the new process reads the restored orders again.

   **A row the pass cannot match to a venue order is marked `ambiguous`, never guessed at.** That is a row that recorded no txid — written before the engine recorded them, or a `submitting` row whose acceptance never reached the ledger — or one whose events record two txids that disagree, or one whose txid the venue read does not return. With the engine's cache enabled, a row whose order the cache restored from the previous process is read at the venue by the txid of the cache's copy where the row recorded none, or two that disagree, and takes its figure and state from the venue's report alone, never from the copy: it is marked only where no txid exists anywhere, on the row or the copy, or where a read that succeeded does not return the one it is read by. A restored row's intent stays `pending` until a venue read of the running process answers the row; a finished restored order with no fills and no txid anywhere is never answered, its intent `pending` for good: read it against Kraken's closed orders (no count command: such an order is ledger state on the engine host, which nothing in the tree records). An open row takes the state `ambiguous`, the ledger's word for an order that may still be resting, and an `ambiguous` event naming why; a closed row with fills takes the event alone and keeps its state, since what is unestablished there is only whether the venue later withdrew a fill. A row already marked is not marked again, and nothing trips or refuses. The engine cannot manage an order it cannot identify — the pass cancels a resting order it can match to no row, and a fill on such an order is counted `unmatched` with no row write — so settle each marked row by hand:

   1. Read it in the ledger read above: `ambiguous` as the row's state, or an `ambiguous` line under a closed row.
   2. Find its order on Kraken's Open Orders and Closed Orders pages, or with `kraken open-orders -o json` and `kraken closed-orders -o json` on the workstation, matching the `cl_ord_id` — the adapter sends the engine's `O-<date>-<time>-001-000-<n>` id as `O` plus its last 17 characters, `O-<time>-001-000-<n>` for a single-digit `<n>` — and the pair, side and quantity, which break a tie.
   3. If it still rests, cancel it on Kraken's page.
   4. If it filled, compare its executed volume with the row's `filled_qty`: a shortfall is a withdrawn fill, and [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped)'s withdrawn-fill path is the one to work.

   The row ages out of the pass's two-UTC-day window, and nothing clears the mark before then.

   **The startup pass also reconciles every preserved row it can match against the venue's own figure, so a row can move before you ever read it.** A fill that lands while the engine is down reaches no handler — the process is not there to hear it — so the pass compares each preserved row against the quantity the venue reports for that order. **Only a venue figure that is HIGHER writes a quantity into the row**: that difference lands as a `reconciled` event carrying the delta and the venue's total, plus a WARNING log line naming both figures. A difference too small to be real (the two figures are summed differently and can disagree in the last bits) is silent by design, and a venue figure that is *lower* is a divergence rather than a repair: it latches the kill switch, and the paragraph below is where its evidence lives. An order that filled, was canceled or expired while the engine was down is closed at the venue and never appears among the resting orders at all; its row is found through the venue read above and is given its final state (`filled`, `canceled`, `venue_canceled`, `rejected`) right there at startup, with a `reconciled` event beside it only if the venue also reported more filled than the row had — a cancel with no fills, the commonest case, gets the state write and nothing else. So a row that closes with no event stream behind it is this pass, not something you missed. A repair is **not** counted as a fill: `zcrypto_exec_fills_total` and the fee counter do not move for it, because there is no per-fill detail and no fee behind the venue's aggregate. The row is the record.

   **This is also the one thing that can latch the kill switch at boot, before any plan is picked up.** Two divergences trip it, and they leave different evidence. **The venue reporting more filled than the row was ever submitted for** writes the repair into the row first and latches second, so the row carries a `reconciled` event and the kill file names both quantities. **The ledger claiming more filled than the venue reports** — the dangerous direction, since it means the engine believes it reduced more than it did — never repairs the quantity: there is no repair to make, and inventing one would erase the very figure that is in dispute. What it *does* write depends on which row it lands on. On a row still open — an order that could yet be live — nothing goes into the row but its terminal `state`, if the venue's own order has closed, so the kill file is the only place the venue's figure appears. On a row this engine had already **closed** — the shape a withdrawn fill takes, since a withdrawal lands on a completed order — a `withdrawn` event carrying `venue_filled_qty` is appended to the row *first* and the latch follows, leaving the ledgered quantity standing beside it so the two readings sit together. Either way, do not read an unchanged row as evidence nothing happened; `sudo cat /var/lib/zcrypto-engine/exec/kill` names the order — by the engine's id, with `(Kraken <txid>)` beside it when the row recorded one — and both quantities. Neither divergence is compared on a row the pass marked `ambiguous` or left unread after a failed venue read, so neither latch can arm for those; the two paragraphs on them above say what does happen. **One path is worth knowing before you touch a resting order in the Kraken web UI**: `editOrder` is cancel-replace, not an in-place amend — it produces a *different* order under a new Kraken txid, which no row recorded. At the next restart the original's row, if still open, is closed from the venue's report of the original, and the pass cancels the replacement if it still rests, as an order the ledger does not carry — so an edit made to keep an order working ends it at the next restart, with nothing in the UI hinting at it. `amendOrder` is in-place, keeps the txid, and does not have this shape.

   **An event on that stream belonging to no ledgered row — your own hand settle in the Kraken UI is the one that matters — is counted under `zcrypto_exec_external_events_total{disposition="unmatched"}` and logged, and acted on nowhere**: no row write, no fill or order counter, no cancel, and no fill-time trip. That is the filter working as designed for an event with no ledgered row behind it. **A row the pass marked `ambiguous` is a second cause, and there it IS a gap** — its order was never re-attached, so a fill on it lands in this count instead of in the row the ledger holds for it, which is why each marked row is settled by hand above. What it does NOT settle is whether a hand settle produces an order event at all: the engine publishes reconciled orders' events unconditionally, but whether Kraken's settle-position act emits one on the adapter's streams has never been measured — so the counter is the instrument that will answer it at the first settle, not the answer. Read it then (**§6 Verify by outcome, item 6** queries it): a rise means the settle reached this process as an order event and was correctly ignored; a flat counter means it did not, which is worth recording either way. It stays clear of the fill-time trips because it matches no ledgered row. The post-terminal position reconciliation under the settle preconditions below is clear of it for a different reason: its input is this engine's own strategy-scoped position rather than an order event, and a hand settle reaches that position no more than it reaches a ledgered row.

5. **The owner clears the hold**: `sudo rm /var/lib/zcrypto-engine/exec/restart-hold`. Gate read → `level=none`, `reasons=arm_file_absent`.

6. **The owner creates the arm file**: `sudo touch /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=full`, `reasons=-`. A `nautilus_unverified` here instead means the running version has no recorded order-semantics pass and pre-probe step 3 was skipped — stop and go back to it; the gate is refusing on purpose and no control file will clear it. If `venue_not_online` shows up instead, Kraken itself is not `online` — wait it out, since nothing can be submitted until it is. The engine is now armed, and [`engine.md#zcrypto-engine-exec-armed-too-long`](engine.md#zcrypto-engine-exec-armed-too-long) will page if the window outlives six hours — that is the rule working, not a fault.

#### 3. Drill before money — both drills green before any funded plan

Three plan-file mechanics that apply to **every** plan from here on:

- **A plan expires 60 minutes after its own `created_at`**, which must be a timezone-aware ISO timestamp. Author, check and place inside that hour, or the engine refuses it and journals the refusal.
- **Place a plan by renaming it into position — never by writing it in place.** (no count command: a placement is an operator act; `_TICK_SECONDS` in `cli/engine/executor.py` sets the poll) The executor stats the plan path every 5 seconds and reads whatever is there; a file still being written parses as garbage, is journaled as a refusal, and is **deleted**. A `mv` inside the same directory is atomic, so the executor sees either the whole file or no file.
- **A `plan_id` already in the execution ledger for today or yesterday is refused.** Every plan gets a fresh id (no count command: `tests/test_engine_probeplan.py::test_plan_refusals_a_ledgered_plan_id_refuses` holds the refusal).

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
3. Validate it offline — read-only, mutates nothing (no count command: `tests/test_engine_command.py::test_probe_plan_check_mutates_nothing` holds it):
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
   Expect the `submitted`, `accepted` and `canceled` outcomes to have advanced, **every** `zcrypto_exec_fills_total` series still `0`, and `zcrypto_exec_fees_eur_total` still `0` (no count command: the engine's live series at drill time, not a set the tree holds). A number, never `(no series)`.

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

**`offset_pct` is a PERCENTAGE, not a fraction — `5.0` is five percent.** The dangerous slip is the quiet one: `0.05` is five *hundredths* of one percent, about fifteen euro off a thirty-thousand euro bid, and it fills — on the one mode built never to. The opposite slip is loud and harmless, since `500.0` prices absurdly and simply never places. `hold_minutes` is how long the order rests, an integer in 1–60. Both fields are required on `rest-hold` and refused on the other two modes; `action` must be `open`.

The `--check` line carries both back in words on the intent line, and reading it is how the slip is caught before the file is placed — the same line as above with the two fields spliced in:

```
  [0] BTC/EUR buy open rest-hold (5% passive of the touch, holding 45 min): notional 20.00 EUR, costmin <X> EUR
```

**Three terminal outcomes to read back in the ledger, beside Drill A's `rest_cancel_ok`.** `rest_hold_expired` — the hold ran its course: the engine cancelled at `hold_minutes` and the venue acknowledged. `rest_hold_venue_canceled` — the venue or the operator took the order off the book, and the engine deliberately did **not** put a new one back; a completed intent, not a fault, and the reason a hand-cancel in the Kraken web UI ends the drill rather than restarting it under an order id nobody is watching. `revoked` — the kill file, a disarm, quote silence or an engine restart took it mid-rest, so it was revoked rather than held to its expiry, and the plan stops there. After a restart the startup pass writes it, with `the engine restarted while the intent was in flight` as the reason, and writes `not run -- the engine restarted before it ran` on the intents that never placed an order; the pass writes the intent before the venue answers its cancel, so a fill that lands afterwards — racing the cancel, or on an order the cancel did not reach — is on the order's row and not in the intent's `filled_qty`: read the row; a cancel the venue refuses leaves the order resting beside its `revoked` intent, the `cancel of adopted order … was REJECTED by the venue` line at CRITICAL says so, and the hand cancel on Kraken's open-orders page is yours. An intent still `pending` after the pass is one whose order the pass left resting — a reducer it kept, or an order it could not cancel or could not match — or the whole window's, when the pass's ledger or venue read failed or the pass latched the kill switch. A startup inside the re-attach window — the intent's boundary day and the next UTC day (`_exec_records_in_window` in `cli/engine/execledger.py` reads those two day directories, for the intent sweep and the row re-attach alike) — settles the intents a failed read left, a cancel that raised, a reconcile that raised, and an order resting outside the Cache once it is cancelled by hand or closes at the venue; an intent whose row recorded no txid, or whose txid no venue read returns, stays `pending` through later startups too, and one the pass latched the kill switch over is written by no startup while the latch's cause stands. Past the window no startup reads the intent or its row: the window's entry records each intent still `pending`, and its row, beside Kraken's open and closed orders and the positions page read for that order.

**Read `filled_qty`, not the outcome name — the names you can see here do not behave alike.** `rest_hold_expired` and `rest_hold_venue_canceled` are **remapped to `partial`** the instant anything filled, so seeing either name is itself the statement that nothing did. A **fully** filled order reaches none of the three: the intent finishes `filled` the moment its target quantity is met, before any cancel is asked for — so `filled` is the fourth name on this list, and the one that says money moved loudest. **`revoked` is not remapped**: it keeps its name whatever filled, and carries the fill through in `filled_qty`. That state is reachable by design, because a partial on a resting order leaves the remainder working at the touch — so an order that took a fill and was *then* revoked (drill E's kill file landing on a rest-hold order the market had already reached) journals `outcome revoked` with a **non-zero `filled_qty` and a real position behind it**. On a `revoked` intent, `filled_qty` is the only field that answers whether anything reached the book — on one the startup pass wrote, its rows' `filled_qty` summed, since a fill after the pass's write is on the cancelled order's row and not in the intent's figure.

**Drill B — the disarmed refusal: prove the key actually refuses.**

1. `sudo rm /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=none`, `reasons=arm_file_absent`.
2. Place a second `rest-cancel` plan with a **new** `plan_id`, exactly as in drill A steps 1–5.
3. Expect the plan entry to still read `accepted` — the plan-level checks do not read the gate — and **every intent** to read `outcome refused` with `reasons ['arm_file_absent']` (no count command: `_start_intent` in `cli/engine/executor.py` refuses an intent the gate's level does not permit). No order row is created for it, nothing reached the venue, and `zcrypto_exec_orders_total{outcome="refused"}` advances.
4. Re-create the arm file (`sudo touch /var/lib/zcrypto-engine/exec/armed`) and confirm `level=full` before going on.

#### 4. Execute — the funded plans

**Three rules hold for every funded plan below, without exception.**

- **Never drop a funded plan inside the final 60 minutes before a 4-hourly boundary** (00/04/08/12/16/20 UTC). Run `date -u` immediately before placing; if the next boundary is under 60 minutes away, wait for it to pass. The 4-hourly cycle runs synchronously on the node's single event-loop thread and can hold that thread for up to about 25 minutes when a refresh degrades. While it is held no 5-second tick fires, so **none** of the mid-flight revocations — the kill file, a disarm, quote staleness, the intent's own time-box — can act on a resting order. This rule is the only thing keeping a funded order from resting through that window (no count command: a plan's drop time is an operator act, and nothing under `cli/engine/` refuses by it).
- **Every plan is signed off on its own**: the owner reads the `--check` output and personally places the file (no count command: who authors and places a plan is an operator act nothing in the tree records). Drill plans included.
- **Nothing retries itself.** An intent ending `unfilled`, `refused`, `rejected`, `partial` or `ambiguous` stops there (an `execute` intent's `unfilled` follows both ladders, the maker reprices and the bounded IOC attempts, so its `filled_qty` is what its orders got, maker and IOC alike), and so do a `rest-hold` intent's own two terminals — `rest_hold_expired`, the hold run to its end, and `rest_hold_venue_canceled`, the venue's or the operator's own cancel which the engine deliberately does not undo. Those two are completed intents rather than faults, and stopping is what they are supposed to do. **`ambiguous` means the order may be live at the venue** — read Kraken's open orders in the web UI and establish what actually reached it before placing anything else on that symbol.

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

`notional_eur` on a margin closer is **advisory** — the engine sizes the close from the live position and submits it reduce-only, so the same bound is enforced at both ends. A venue rejection of that order halts the intent and surfaces to you, with no retry.

**Step 4 — the settle act: the owner settles the BTC/EUR long by hand in the Kraken web UI, and only when no intent is in flight.**

The engine cannot do this — its adapter has no settle-position order type at all — so this half is yours. Settling in kind repays the borrowed EUR from wallet balance and converts the position into a spot BTC holding; Kraken charges no trade fee on settling in kind.

**Preconditions, and their order is not optional.** Settle only after (a) two rollover events are visible in the ledger export for both positions, and (b) the close intent has reached a **terminal** state in the ledger and no intent is in flight.

**Why those are preconditions and not advice.** The post-terminal reconciliation compares this engine's OWN strategy-scoped position against what its own fills account for, and on both ends reads only this engine's strategy, precisely so an operator's hand settle reaches no trip, no row and no cancel. So a settle cannot latch the kill switch, and the preconditions are not buying you protection from that. What they buy is a readable window: a settle landing beside a live intent on the same symbol moves the account under the one comparison you will later have to read by hand — Kraken's ledger export against the journal — and leaves you unable to say which act produced which row. Wait for the close intent to be terminal with nothing in flight, and every row after it has one author.

**Step 4b — record whether the settle propagated, before you move on.** Neither the trip above nor the disposal below turns on whether a hand-placed settle reaches the engine's position view — but the window is the only place it can be observed, and observing it costs one read. After the settle, read the next `venue-<HH>.json`'s `positions` for the settled instrument — that record IS `cache.positions_open`, so it is the one surface that can answer this — and write the verdict into the probe's decisions-log entry alongside the `unmatched` reading from **§6 Verify by outcome, item 6**: propagated, did not, or the record could not tell. Do **not** read `zcrypto_exec_position` for this: that gauge is written only on a fill (plus a startup seed), so between the settle and the disposal it still shows its pre-settle value whether the settle propagated or not, and reading it here would answer "did not propagate" every time. Nothing downstream depends on the answer — the disposal's `qty` is signed off from the ledger export in step 5, not read from this view — so a surprising result is information, not a stop.

**Step 5 — read the disposal quantity out of the ledger export.** Export the ledger again after the settle and read the BTC amount the settle credited. That figure — not a balance the engine reports, not an estimate — is the disposal plan's `qty`: whether a hand-placed settle propagates live into the engine's balance view is unproven, and a plan-carried quantity is what the engine sizes from — at `level=full` its own balance view can only refuse a figure it can refute, a positive balance smaller than `qty`, never confirm one, so a settle that did not propagate does not block the sell. Floor it to the leg's lot step, which `probe-plan --check` prints; the check refuses a `qty` that is not a multiple of that step, and rounding **up** would put the sell over the balance.

**Step 6 — the disposal plan: the engine sells the residual spot BTC, so the probe ends flat.** Again one intent in its own plan envelope:

```json
{"symbol": "BTC/EUR", "side": "sell", "action": "close", "mode": "execute", "qty": 0.00021}
```

No `leverage` key — its absence is what makes this a spot order — and a spot close carries `qty` instead of `notional_eur`. Same sign-off and the same 60-minute boundary rule as every other funded plan. An over-quantity sell is refused by the engine when its balance view can refute it and rejected by the venue when it cannot — either halts attended; a remainder below the leg's `ordermin` is accepted as terminal dust.

**Step 7 — re-sync the tax depot and record the verdict.** After all three terminal acts — the close, the settle, the disposal — re-sync the Kraken depot in Blockpit and record pass/fail in `docs/research/14.phase6-decisions.md` with the evidence: bucket assignment (derivatives PnL vs spot disposal), rollover fees attached as costs, FIFO lots intact, no phantom balances, and the disposal's gain/loss computed off the basis the settle carried.

**On a FAIL, registering the fallback build item is a step of THIS checklist, executed in the same session as the verdict — never a remembered promise.** Open a topic file under `docs/open-topics/` (file mechanics: the `topic-ops` skill) for the deterministic pre-transform that maps Kraken's ledger and trades exports into Blockpit's manual-import CSV with explicit margin-PnL rows, and queue it in the memo in the same pass — a topic registered but not queued is invisible when work is picked up.

#### 5. Disarm — both keys down, the second one the same day

1. **The owner deletes the arm file**: `sudo rm /var/lib/zcrypto-engine/exec/armed`. This disarms immediately — no deploy, no restart, no engine downtime. Gate read → `level=none`, `reasons=arm_file_absent`.

2. **Converge `exec_armed` back to `false` the same day — not "eventually".** Between deleting the arm file and that converge the deployed config still says armed, so arming is effectively **one** key rather than two: anything that recreates a file at `/var/lib/zcrypto-engine/exec/armed` re-arms the engine with no review and no deploy. Revert the one line in `infra/ansible/roles/engine/templates/zcrypto.toml.j2` and converge with the same command as the arm step (same running digest, same inter-cycle gap). A Kraken margin position still open holds this converge until it is closed, unless [the restart rule](#engine-restart-margin-position)'s test admits it; step 1 has already disarmed the engine, and the one-key exposure above lasts until then. Read the preview: exactly one line changes back. **The changed line re-renders `zcrypto.toml`, so the handler restarts the engine and the deployed digest owes one clean boundary cycle again** -- at the next 4-hourly boundary, a `cycle-<HH>.json` whose `completed_at` falls inside `[B, B+30 min]` with no `failed-cycle-<HH>.json` beside it (no count command: the proof is a journal artifact on the engine host, and the reading of it is an operator act nothing in the tree records).

3. **Confirm both keys are down.** Gate read → `level=none` with `reasons=config_not_armed,arm_file_absent,restart_hold` — three reasons; the restart hold is back because the converge restarted the engine, and that is the correct resting state, so leave it. From the workstation, `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_armed{host="zcrypto"}'` reads `0`.

4. **Treat any restore of the engine state directory as re-arming until proven otherwise.** (no count command: a restore is an operator act nothing in the tree records) The arm file and the plan file both live in `/var/lib/zcrypto-engine/exec/`, which sits inside the directory that is also the backup unit — a restore can bring either one back. After **any** restore of `/var/lib/zcrypto-engine`, and **before the engine starts**, list the directory: `sudo ls -la /var/lib/zcrypto-engine/exec/`. Then act **per file, by name** — a restored control file is not automatically debris, and three of them mean three different things:

   - **`armed` and `probe-plan.json` — delete these two if present, and only these two.** (no count command: a delete after a restore is an operator act nothing in the tree records) They are what a restore re-arms you with. The plan's own 60-minute expiry and the ledger's plan-id dedup are the designed backstops behind this check, not a substitute for running it.
   - **`kill` — this is a FINDING, never something to sweep away.** (no count command: removing it is an operator act; no line under `cli/` unlinks `KILL_FILE`) No code path anywhere clears the kill file; it is a latch a human engaged, and a restore that brings it back is telling you the backup was taken after a trip. `sudo cat /var/lib/zcrypto-engine/exec/kill` prints a timestamp and the reason that tripped it. Read that reason, work [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped), and remove the file only once the reason no longer holds. Deleting it along with the rest destroys the one record of why the system stopped, at the moment it is trying to tell you.
   - **`restart-hold` — leave it.** The engine writes one unconditionally at every start anyway (no count command: `write_restart_hold` runs at each engine start, and nothing under `cli/` removes the hold), and holding at reduce-only until a human clears it is the correct resting state.
   - **`first-fill` — leave it, and never write one by hand.** (no count command: a hand write is an operator act; `_record_series_birth` in `cli/engine/executor.py` holds the dating) The engine writes this once, at the first boundary after its first ever fill, and reads it only to refuse: it is what tells the weekly tracking-error trip that the journal still holds the whole position history it measures against. A restore that brings back a `first-fill` older than the journal now covers is a *correct* refusal, not a fault. Writing or editing one by hand tells the trip a history is present that is not, which is the one way to make it latch the kill switch on a healthy engine. **If it is missing on an engine that has ever filled, that is a finding, not a self-healing state.** Once fills exist the engine cannot establish for itself that its journal's head is intact — a prune that happened to cut at a quiet boundary looks identical to a journal that was never cut at all — so it re-dates itself only while the earliest fill it can see is under a week old — which the healthy path, a record written at the first boundary after the first fill, hours later, satisfies with room to spare. Anything older it refuses to date, and the trip then refuses every week, permanently, with that reason in the log. **That refusal is the correct outcome and no operator action clears it**: the position it would need is not on this host. Do not hand-write a record to make the refusal go away — that is the one move that ends in a latched kill switch on an engine that never misbehaved.

#### 6. Verify by outcome — the window is not closed until every line here reads true

1. **Every intent has a terminal outcome and every order has a terminal state** (no count command: the set is one window's ledger, on the engine host rather than in the tree), from the ledger read: each plan entry `accepted` with empty reasons, each intent carrying an outcome, each order row a terminal `state`.

2. **Every fill carries its fee and its liquidity side** (no count command: the set is one window's ledger, on the engine host rather than in the tree): each `fill` line shows `fee` with a `fee_currency` — both `null` on a fill the venue reported no fee for, a truthful null rather than a dropped row — and `liquidity` reading `MAKER`, `TAKER` or `NO_LIQUIDITY_SIDE`: a word, never a number.

3. **Two rollover rows per position** in the Kraken ledger export — read by hand, and then read again by the standing reader **in the same session, while the hand read still exists**. From the workstation, against a pulled copy of the engine journal:

   ```
   uv run zcrypto engine tracking-report \
     --journal-dir <pulled journal> --since <first window day> --until <last window day> \
     --ledger-export <the export>.csv
   ```

   **The comparison, and the only one that can qualify this reader**: its `rollover fees` figure must equal the total you just read by hand. A standing reader that has never once agreed with the hand read it replaces is unverified, and this window is the only place the two figures exist side by side — record both in the probe's decisions-log entry, equal or not.

   Three readings of the export go in the same entry:

   - **The `rollover fees` figure prints at four decimals, the export's precision for a euro fee.** The reader sums the `fee` column, where the charge lives. A figure that differs from the hand read at four decimals is a finding about the reader, not about the window.
   - **`trade` and `margin` rows are matched by their trade id.** (no count command: `reconcile_ledger` in `cli/engine/tracking.py` holds the two matched types in `_MATCHED_LEDGER_TYPES`) A spot fill writes `trade` rows and a margin open or close writes a `margin` row under the fill's own trade id, with no `trade` row beside it. Read the export's distinct `type` values (`cut -d, -f4 <the export>.csv | sort -u`, allowing for quoting). The types `_NO_FILL_LEDGER_TYPES` names, and the `spend` and `receive` rows of Kraken's small-balance conversion as `dustsweeping`, are counted by type on the `rows with no fill behind them by construction:` line. Those conversion rows were read through `kraken ledgers -o json`, never from a CSV export, so an export that spells them otherwise lands on the `row types this reader places nowhere:` line with any type the reader has not met, and a type appearing there is a decision to record here. The `fees on the matched rows` figure is the venue's own fee total over the journaled fills the export's rows matched — a journaled fill the export carries no row for adds nothing and is not reported, so read the export's first and last `time` against the window's `--since` and `--until` before reading the figure as the window's — a fee charged in EURC counted at par (the venue converts euro to EURC beside the row to charge a margin open's fee, and the journal reports that fill's fee in euro), printed at four decimals to read against the fills' cent-rounded fees in the ledger read; it is not added to the blend, and a `margin` row's `amount`, the realized PnL, is summed nowhere.
   - **A venue repair guarantees an unmatched id, and that `FAILED` is honest.** A `reconciled` event carries no venue trade id, so the journal gives it a synthetic one that no ledger row can ever match. So the block does **not** have to read `ok`: read the named ids against the window's own repairs first. What must be true is that every unmatched id is *explained* — a repair, or account activity you performed by hand — and that none of them is a trade nobody can account for (no count command: the ids are one window's export against its journal, neither of them in the tree). That last case is the one thing this comparison exists to catch, and it is a stop.

   Two reading notes. The block prints how many rows it read at all, so an export that produced nothing cannot read as a window that contained nothing. And do **not** run this with `--simulated-fills`: modelled fills carry no venue trade id, so every real ledger row is unmatched by construction — the command says so, and the block means nothing in that mode.

4. **The settle and then the disposal are visible in venue truth, read from the venue record written after the disarm converge's restart** — that restart is what forces the fresh account read, and it is the verified path. Take the restart time from `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine`, wait for the next 4-hourly boundary to write its record, then run the venue-truth read and confirm `snapshot_at` is later than that restart time. A record written before the restart is corroboration, never the gate (no count command: which record gates is an operator read of files on the engine host).

5. **The probe ends flat**: that record's `positions` carries **twelve** entries — one per basket leg, always, flat or not (no count command: `venue_state_from_cache` in `cli/engine/venuestate.py` writes each leg; the values are one window's) — and every one of them reads `0.0`. Count the keys and read the values: an absent key is not the flat state (a leg missing from the map means the snapshot never measured it, which is a fault to chase), and a non-zero value is not flat however small it looks. Its `balances` are EUR only, with any BTC remainder below the leg's `ordermin` (terminal dust, not a position).

6. **The execution families are live in Grafana Cloud, read by value** from the workstation — a number in every case, never `(no series)` (no count command: `infra/scripts/grafana-query.py` prints `(no series)` for an empty result, not a zero):

   ```
   uv run python infra/scripts/grafana-query.py \
     'zcrypto_exec_orders_total{host="zcrypto"}' \
     'zcrypto_exec_fills_total{host="zcrypto"}' \
     'zcrypto_exec_fees_eur_total{host="zcrypto"}' \
     'zcrypto_exec_position{host="zcrypto"}' \
     'zcrypto_exec_realized_pnl_eur{host="zcrypto"}' \
     'zcrypto_exec_external_events_total{host="zcrypto"}'
   ```

   The last one's **zero is a reading rather than a gap**: both dispositions are registered at startup, so `matched` and `unmatched` must both be present, and `(no series)` on it means the capture keep-regex did not ship rather than that nothing happened. Record `unmatched`'s value against the settle taken in step 4 — that is the measurement of whether a hand settle reaches this process as an order event at all.

7. **Count the journaled gate level across the window's exec records**, on the engine host: `for f in /var/lib/zcrypto-engine/journal/<YYYY-MM-DD>/exec-*.json; do python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['level'])" "$f"; done | sort | uniq -c`. This is the input the weekly tracking-error trip takes its eligibility from, and it is the one reading no other step produces. Every record written outside a window reads `none` (no count command: `evaluate` in `cli/engine/execgate.py` sets `none` while either arming key is down), so what this measures is whether an ARMED window actually journals `full`. If it does not, the restart hold was left set through the window, and the trip is structurally inert even once armed: see `engine-tracking-band` below, and do not set a band until this reads `full`.

8. **Take the week's tracking reading, and record what it produced even when that is nothing.** Nothing schedules this — there is no timer and no unit behind the command, deliberately, so this step *is* the cadence: a window that closes without it leaves no missing artifact for anyone to notice later. From the workstation, against a pulled copy of the journal:

   ```
   uv run zcrypto engine tracking-report \
     --journal-dir <pulled journal> --since <YYYY-MM-DD> --until <YYYY-MM-DD> \
     --gate-from <YYYY-Www>
   ```

   - **`--gate-from` is not optional in practice.** Without it NOTHING is decided whatever the numbers say — every week is measured and none is eligible, which the report states by name in its own footer (no count command: `tests/test_engine_tracking.py::test_a_gate_boundary_is_required_before_any_week_decides` holds it). The week to pass is the first ISO week whose cycles ran under continuous arming, i.e. a fact about the deployment rather than about the journal, which is why the flag asks instead of guessing.
   - **Confirm the boundary landed, because nothing validates it for you.** A week outside the window is accepted silently: one after it decides no week, and one before it counts every week in the window as past the boundary, those before the real one included (no count command: `_rung_by_week` in `cli/engine/command.py` labels each window week against the flag). The report echoes `Gate boundary: weeks from <YYYY-Www> onward count`, notes every week it placed before that boundary, and states in its verdict line how many weeks it decided — read all three against what you intended.
   - **A week the report cannot produce is a refusal to record, never a zero to shrug at.** (no count command: `_tracking_note` in `cli/engine/command.py` labels such weeks; recording them is an operator act) A partial ISO week, a week before the boundary, and a week with no journaled fills each print as measured-but-not-decided or as *no data* — the series not having started is not the same reading as a week of perfect tracking. Write the week labels and their reasons into the probe's decisions-log entry beside the numbers; that record is the only evidence the reading was taken at all.
   - **Before the first fills exist every week reads *no data* and the cost half answers that there are no euro-denominated fills.** (no count command: `_tracking_cell` in `cli/engine/command.py` and `cost_blend` in `cli/engine/tracking.py` print both) That is the correct output, and recording it is what makes the first real reading comparable to something.

9. **The verdict is recorded** in `docs/research/14.phase6-decisions.md`, and on a fail its fallback topic is registered and queued — step 7 above.

### Retire when

`cli/engine/executor.py` no longer picks a plan file up out of the state directory's `exec/` — check with `grep -n PLAN_FILENAME cli/engine/executor.py`, and a run that finds nothing is the signal. At that point the continuous loop that replaces attended probe windows has landed, and this procedure with it.

______________________________________________________________________

<a name="engine-rung-2-box"></a>

## engine-rung-2-box — PROCEDURE

### What you are seeing

You are running — or about to enter — the rung-2 box: four ISO weeks, 2026-W41 to W44, Monday 2026-10-05 to Sunday 2026-11-01, of hand-placed spot plans, each leg sized from the day's boundary record — 12Z, or 16Z on a fallback day. **Nothing has fired**: you opened this because a day's window is due, the box is about to start or end, or something in the box needs a decision.

Real money moves and is held overnight and through weekends: a nine-leg spot book, placed at most EUR 95 a plan, on the host that holds the live trade key. The box is fixed at entry: it is neither extended nor ended early, and a pause inside it moves none of its dates.

### What it means

The box runs on the [probe-window procedure](#engine-probe-window)'s machinery — the same plan files, `--check`, `mv` placement, gate read, ledger read and drills — with a daily cadence in place of single windows. Every step below that reuses one of that procedure's steps names it. What the box changes:

- **The book is nine spot legs, fixed at entry**: BTC/EUR, ETH/EUR, SOL/EUR, XRP/EUR, DOGE/EUR, LTC/EUR, ADA/EUR, AVAX/EUR and DOT/EUR (no count command: a plan's legs are the owner's sign-off; the helper refuses a tenth). No intent carries a `leverage` key, and nothing is shorted.
- **A leg's target is EUR 720 times its weight** in the newest boundary record's `final_targets`. The governor's multiplier is already inside that weight: follow it as published, and re-scale nothing onto fewer legs. A negative weight reads as 0, and that leg is sold whole.
- **A plan is the target minus what Kraken itself says is held** — the balance export taken right before the draft, not the engine's venue record. A difference below the venue's floors, or a buy beyond Kraken's free EUR less 5, is carried to the next window; the decision table names each leg's outcome and why.
- **A sell is capped at the venue record's balance of its coin.** At gate level `full` the engine refuses a spot sell when the newest venue record holds a balance of that coin above zero but below the sell's `qty`, with `the venue record refutes the signed qty` (no count command: `_classify_spot_close` in `cli/engine/executor.py` holds the refusal), and the helper drafts what it admits. That balance is the engine's stored account, not Kraken's holding: [step 5](#rung-2-after-a-restart) item 5 says what it carries, what the helper's lines mean and what raises it. In a box entered on a cleared account and not restarted since, the record carries EUR alone and the cap does not arise.
- **A plan is sells before buys, at most 3 `execute` intents, and at most EUR 95 in all** — its `notional_eur` plus each sell's `qty` × price; the rendered `exec_max_plan_notional_eur` stays 100.0. Its `plan_id` is `r2-<YYYYMMDD>-<n>`. One plan runs at a time: the next is drafted from fresh balance and positions exports once the previous one is terminal, and each plan is checked and placed within 60 minutes of its own `created_at`.
- **An intent that ended `unfilled`, `partial`, `refused` or `rejected` is not re-placed the same day**; the next window's target minus held absorbs it. The helper holds this: it carries each leg a plan drafted earlier today already carried, with the reason `<plan_id> carried it earlier today; never re-placed the same day`, since it cannot see whether that plan filled (no count command: `placed_today` in `cli/engine/draftplan.py` reads the decision log for it). A plan drafted and not placed — refused at `--check`, or expired before its `mv` — is named on the next draft with `--discard <plan_id>`, once the ledger read shows no entry under that id; that frees its legs, and the helper takes a plan drafted today that it has not already discarded. An `ambiguous` or `revoked` intent halts that symbol until Kraken's open orders are read.
- **The plan-drafting helper, the engine CLI's `draft-plan` command, does the arithmetic**: read-only, on the workstation. It reads the copied `cycle-<HH>.json` and `venue-<HH>.json`, your balance and positions exports, the public ticker and the Kraken maintenance feed (read whole). It refuses, with nothing drafted, any input it cannot trust and any day or hour the box does not allow; the `draft-plan` row in `README.md` lists each refusal. The venue record's `positions` are the engine cache's net per instrument, which the helper prints as the table's engine-held column and drafts nothing from ([step 5](#rung-2-after-a-restart) item 4). Under the table the helper names the legs whose engine figure is more than a lot step from Kraken's, in a line opening `engine held is the engine Cache's net`: it is information and no stop, and a reward credited on a held leg is enough to put that leg on it. Kraken's positions export is what shows the account spot only. It emits one plan, sells first, a decision table, and one row per leg to the decision log. It catches what `--check` does not: `--check` compares a buy with `costmin` alone, counts a sell's notional as 0 and reads no balance against a sell (no count command: `_intent_floor_check` and `plan_refusals` in `cli/engine/command.py` and `cli/engine/probeplan.py` are the two checks).
- **The decision log is `data/rung2/decisions.jsonl`** in the checkout the helper runs from — its root, where `zcrypto.toml` sets `data_dir` — and each plan is written beside it as `data/rung2/<plan_id>.json`. The log is the helper's: a line in it that is not JSON makes each later draft refuse, so nothing is added to it by hand (no count command: the log is on the workstation, outside the tree). What the helper does not know — each placed intent's outcome and filled quantity, the window's minutes, a multiplier read, a stop, a week's read — goes in `data/rung2/days.md`, one dated heading a day. `data/` is unversioned: once the log exists — entry day's first draft creates it — copy it aside before each later day's first draft with `cp -p data/rung2/decisions.jsonl data/rung2/decisions.prev.jsonl`, and delete that copy once the exit report is recorded.
- **Arming is the arm file alone.** The host's `/opt/zcrypto-engine/zcrypto.toml` stays `exec_armed = true` through the box, while the tree's template renders `false` and no converge has carried it there. This departs from the probe-window procedure's disarm step 2, which converges the config back to `false` the same day: the ruling accepts the one key that leaves for the box's four weeks, so disarm step 4 holds throughout — after a restore of `/var/lib/zcrypto-engine`, and before the engine starts, delete `armed` and `probe-plan.json` if present. The arm file is placed at the day's first drop and removed when the last plan is terminal, at the latest 55 minutes before the next boundary; a day the helper drafts nothing is a day without it. The restart hold is written at each engine start and cleared by you at [step 5](#rung-2-after-a-restart) item 7.
- **An engine converge inside the box disarms it.** `--tags engine` re-renders the tree's `exec_armed = false` through the task `render the engine zcrypto.toml`, its handler restarts the engine, and the box cannot arm again without an arm PR and its converge; an un-tagged run on the primary is refused unless it skips `engine` (no count command: tags on a run are the operator's; the deploy-log rows below are where they land). `docker` can take the engine with it (the probe-window procedure's *Where everything lives*), and `cache-link`'s changed mesh config restarts `wg-quick@zcache0` under the engine's cache traffic. Checkable after the fact: `docs/reference/deploy-log.jsonl` carries no row dated inside the box whose `limit` reaches `zcrypto` and whose `tags` are empty or name `engine`, `docker` or `cache-link`, and `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine` moved only at your own restarts. The cache nodes' own play, `converge the cache nodes — the engine's Valkey replica set`, restarts Valkey or Sentinel under the engine's cache; [step 10](#rung-2-what-not-to-do) says when it may run.
- **What pages while the book is held.** `zcrypto-engine-dark-with-exposure` is armed while a leg of the position gauge reads above 0.000001 base units — overnight included ([`engine.md#zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure)). The floor is the committed rule's, and holds in Grafana once the alert rules are pushed from `develop`: before that push the rule arms on a reading above 0, reward dust included. `zcrypto-engine-exec-armed-too-long` stays quiet: a window's arm file lasts under three hours. An engine restart posts `Fleet · a daemon restarted` with `job="engine_app"`, the cue for [step 5](#rung-2-after-a-restart); an engine that stays down pages more, which [`engine-clear-stored-account`](#engine-clear-stored-account) step 4 names.

Times are UTC. The owner's local clock moves an hour on 2026-10-25; the windows do not.

### What to do

Where each command runs: the **workstation** is your machine, at the root of the checkout the helper runs from — each command that starts with kraken or uv run, and the ssh and scp that reach the host; the **host** is a shell on `zcrypto` (`ssh zcrypto`) — each command that starts with sudo. `kraken-cli` is workstation-only (CLAUDE.md `## Secrets`).

#### 1. Before entry — four gates by Sun 2026-10-04 20:00Z, and what the proof left owed

1. **The tree's disarm revert is merged** — `exec_armed = false` in `infra/ansible/roles/engine/templates/zcrypto.toml.j2` on `develop` — and not converged: the gate read (the probe-window procedure's) carries no `config_not_armed`.
2. **This entry ruling is recorded** in `docs/research/14.phase6-decisions.md`.
3. **The plan-drafting helper is merged**: the `draft-plan` command's `--help` prints its options.
4. **The reference-data sweep is read**: `docs/reference/kraken-snapshot-register.md` re-rendered by the `zcrypto-refdata-sweep` routine, its verdict read from the rendered tables.
5. **The pre-entry single-lot spot proof did not pass its gate**, and the owner's written change of 2026-10-01 admits the entry in the gate's place; the gate is not re-read as passed: `docs/research/14.phase6-decisions.md`, the entry opening "The pre-entry single-lot spot proof ran live on 2026-10-01", with the day's readings in the `spot-proof` entry of `docs/reference/drill-log.md`. The steps below carry that change.
6. **The engine's stored account is cleared before entry day**, by [`engine-clear-stored-account`](#engine-clear-stored-account), in an inter-cycle gap with the account flat. A stored account that still carries a coin from the proof's restarts puts that coin in the venue record's balances, and SOL, a leg, is expected there at 1e-08: the engine would refuse each SOL sell and the helper carry it ([step 5](#rung-2-after-a-restart) item 5). A coin Kraken holds above zero when it is run, reward dust, is converted inside it, with the engine stopped (its step 5): left at Kraken, the coin is read back by that run's own start. The reading owed is that procedure's step 8: the first venue record written after its start carries `balances` EUR alone. Its start latches the restart hold, which stays latched until entry day (step 2 item 3). It is no slip gate: a box entered without it goes to the owner before the first SOL buy.

**One of gates 1–4 still open at Sun 2026-10-04 20:00Z moves the whole box one week**: W42 to W45, Mon 2026-10-12 to Sun 2026-11-08. Every date below moves with it by a week, and the weekly read's `--gate-from` to `2026-W46`. The helper refuses by the box's calendar, which it derives from `BOX_FIRST_DAY` in `cli/engine/draftplan.py`: a slipped box moves that date to 2026-10-12, and the `draft-plan` row's two dates in `README.md` with it, in one change merged before the new entry day.

#### 2. Entry day — Mon 2026-10-05

1. **Funding has landed**, and no deposit or withdrawal is made during the box (no count command: a transfer is an operator act on Kraken nothing in the tree records). On the workstation `kraken extended-balance -o json` reads EUR and no coin above dust. **Record Kraken's equity now** — the account's total in EUR on Kraken's own balance page — as the entry value [the account stop](#rung-2-account-stop) reads against.
2. **Run the probe-window procedure's pre-probe steps 1–8 once**, at entry, and again after an engine restart or image change — not per window, a recorded deviation from that procedure. Step 3 reads `2.0.0rc6.dev20260921` and that version's record; step 4's reading for a boot over a spot lot is in that record; what step 8 calls the window's arming record is the entry day's heading in `data/rung2/days.md`. Two steps do not fit the box as written:
   - **step 2's working tree at the image's revision**: the checkout the helper runs from is ahead of that revision, the helper having merged after the image was built. In its place, run the command below with `<revision>` the engine row's in `docs/reference/fleet-pins.md`. It is expected to list no commit; a commit it lists has moved a cost floor, the basket or their guards since the image was built — stop, and do not arm:
     ```
     git log --oneline <revision>..HEAD -- tests/test_costmin_drift.py tests/test_basket_concordance.py cli/engine/instruments.py cli/engine/store.py cli/engine/concordance.py cli/engine/feeders.py tests/skip_gates.py docs/universe/point-in-time-universe.md
     ```
   - **step 6's free EUR** is read from item 1's `kraken extended-balance -o json`, `balance` less `hold_trade` under `EUR`, and not from the venue-truth read, whose `EUR` is the engine's stored account ([step 5](#rung-2-after-a-restart) item 5) and not Kraken's EUR wallet.
3. **Arm steps 1–3 do not run**: the host's config is armed already. On the host, read the gate: `level=none`, `reasons=arm_file_absent,restart_hold`. The hold is the one the stored-account clearing's start latched, and `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine` prints that start's time, the one the clearing's entry in `docs/reference/drill-log.md` records; a later time is a start nobody has read, and [step 5](#rung-2-after-a-restart) is worked from its item 3 before going on. Run the venue-truth read: each position `0`, and `balances` EUR alone — a coin there is the stored account's (step 5 item 5) and goes to the owner before a plan buys that coin. Then clear the hold, as step 5 item 7 does: `sudo rm /var/lib/zcrypto-engine/exec/restart-hold`, and the gate read shows `reasons=arm_file_absent`. Item 1's Kraken export is the funding read.
4. **Drills A and B, in spot form, from 12:10Z** (the probe-window procedure's section 3): arm step 6 places the arm file, then drill A's plan without its `leverage` key:
   ```json
   {
     "plan_id": "drill-a-2026-10-05",
     "created_at": "<now, e.g. 2026-10-05T12:12:00+00:00>",
     "intents": [
       {"symbol": "BTC/EUR", "side": "buy", "action": "open", "mode": "rest-cancel", "notional_eur": 20.0}
     ]
   }
   ```
   Read it back as drill A step 6 reads it (`rest_cancel_ok`, `filled_qty 0.0`, one order row `canceled`), then drill B with its own `plan_id`. Drill B step 4 re-creates the arm file when the day's first plan follows inside this window, and is skipped otherwise.
5. **Then the day's window**, [step 3](#rung-2-the-day-s-window) from its item 1.

<a name="rung-2-the-day-s-window"></a>

#### 3. Each day's window — the 12Z record to the arm file's removal

Drops fall in **12:10–13:15Z and 13:30–15:00Z** — none across valkey2's reboot slot at 13:25, none in the hour before 16Z (the probe-window procedure's first execute rule) — and the arm file is gone by **15:05Z**. A plan runs its intents one after another, and an `execute` intent runs up to its 15-minute time box and then its IOC attempts, so a plan of k intents drops by 15:00Z less 15 minutes per intent — **14:45Z for one, 14:30Z for two, 14:15Z for three** — or the arm file's removal at 15:05Z revokes the intent still in flight.

1. **Copy the 12Z records from the host** — on the workstation, into `data/rung2/`, about two minutes after the boundary, and not from the NAS mount, which receives them on its hourly pull, up to an hour later:
   ```
   mkdir -p data/rung2 && ssh zcrypto sudo tar -C /var/lib/zcrypto-engine/journal/<YYYY-MM-DD> -cf - cycle-12.json venue-12.json | tar -C data/rung2 -xf -
   ```
   Both files arrive, or the host's `tar` names the one missing. A cycle not yet journaled is copied again a few minutes later; one that failed writes `failed-cycle-12.json` in place of `cycle-12.json`, and gives this window to [the 16Z fallback](#rung-2-the-16z-fallback).
2. **Read the gate** on the host: `sudo docker exec zcrypto-engine zcrypto engine exec-status` → `level=none`, `reasons=arm_file_absent`, or `level=full`, `reasons=-` where drill B left the arm file in place, on entry day or after a restart's drills. `restart_hold` among the reasons sends you to [step 5](#rung-2-after-a-restart) first; `kill_switch` is [the account stop](#rung-2-account-stop); `config_not_armed` means an engine converge ran inside the box — stop, and take it to the owner, since nothing here re-arms the config.
3. **Read Kraken's equity** on its balance page against the entry value — EUR 60 or more below it is [the account stop](#rung-2-account-stop) — and **take the balance export and the positions export** on the workstation, right before the draft:
   ```
   kraken extended-balance -o json > data/rung2/balance.json && kraken positions -o json > data/rung2/positions.json
   ```
   Kraken's Auto Earn is on (`docs/research/14.phase6-decisions.md`): a `staking` credit on a held coin is part of Kraken's held, which the helper drafts against, and no stop; a draft refused for a balance `outside the spot wallet` goes to the owner.
4. **Draft with the helper** on the workstation, the log copied aside first at the day's first draft once it exists (*What it means*):
   ```
   uv run zcrypto engine draft-plan --cycle data/rung2/cycle-12.json --venue data/rung2/venue-12.json --balances data/rung2/balance.json --positions data/rung2/positions.json
   ```
   A draft with no intent places no arm file — go to item 9, whose `rm` is owed only if an earlier plan placed one (no count command: an arm file's placement is an operator act nothing in the tree records). Otherwise read the decision table before anything else:
   - a leg a plan drafted earlier today already carried reads `carried`, `<plan_id> carried it earlier today; never re-placed the same day` — confirm it against the day's ledger read (item 7);
   - a `FLAGGED` gross line: follow the targets as published all the same, and once the NAS has the day's record, read the multiplier with [step 9](#rung-2-exit-report) item 7's `decompose` command, the day's date as both `--since` and `--until`, and record it in `data/rung2/days.md`;
   - a sell reading `capped at the venue record's b …`, or carried with `the venue record's b … is under the sell qty …`: place what was drafted, and read [step 5](#rung-2-after-a-restart) item 5 — the lines appear from a restart inside the box on.
5. **Copy the plan to the host under the staging name and validate it** — drill A step 2, verbatim, with the helper's `data/rung2/<plan_id>.json` as `plan.json`, then drill A step 3 on the host: `sudo docker exec zcrypto-engine zcrypto engine probe-plan /var/lib/zcrypto-engine/exec/probe-plan.staging.json --check`. Its intent lines are the decision table's placed rows, figure for figure, and its last line `plan ok: <n> intent(s), total notional <x> EUR` counts the buys alone. `plan refused: …` means a fresh draft with `--discard <plan_id>` naming the refused plan, not an edit by hand.
6. **Place the plan** on the host. At the day's first plan, place the arm file first, unless drill B left it in place — arm step 6: `sudo touch /var/lib/zcrypto-engine/exec/armed`, gate read `level=full`, `reasons=-`. Then drill A step 4, after `date -u` reads inside the `drop window` line of the helper's report for this plan (this step's opening paragraph gives its arithmetic): `sudo mv /var/lib/zcrypto-engine/exec/probe-plan.staging.json /var/lib/zcrypto-engine/exec/probe-plan.json`. Within about five seconds `sudo ls -l /var/lib/zcrypto-engine/exec/` shows no `probe-plan.json` (drill A step 5).
7. **Read the ledger by value** on the host — the probe-window procedure's ledger read, `HOURS` covering the window — until each intent carries an outcome and each order row a terminal `state`; a plan that halted shows its later intents `refused`, `not run -- …`. Each fill carries its fee and liquidity side (that procedure's verify item 2). An `ambiguous` or `revoked` intent halts its symbol: on the workstation, read `kraken open-orders -o json` and establish what reached the venue before that symbol is drafted again; one Kraken's orders do not explain is [the account stop](#rung-2-account-stop).
8. **The next plan** starts again at item 3 — fresh balance and positions exports, the helper again, the next `r2-<YYYYMMDD>-<n>` — once the previous plan is terminal, and drops inside its own report's `drop window` line.
9. **Remove the arm file** on the host once the last plan is terminal, by 15:05Z at the latest — disarm step 1: `sudo rm /var/lib/zcrypto-engine/exec/armed`, gate read `level=none`, `reasons=arm_file_absent`. Write the day's entry in `data/rung2/days.md`: each placed intent's outcome and filled quantity, and the window's minutes from the copy to this removal.

<a name="rung-2-the-16z-fallback"></a>

#### 4. The 16Z fallback — the same day, when 12Z could not run or finish

The 16Z boundary's window takes a day whose 12Z window did not run or did not finish — a restart's reads, hold and drills ([step 5](#rung-2-after-a-restart)) can take a 12Z window whole. It places nothing the 12Z window already attempted that day: the helper carries those legs, as step 3 item 4 reads.

1. **Run step 3 from item 1 with the 16Z record**: the same copy with `cycle-16.json` and `venue-16.json` — the helper refuses the 12Z pair once 16Z has passed.
2. **Drops fall in 16:10–17:15Z and 17:30–19:00Z**, clear of valkey3's reboot slot at 17:25 and of the hour before 20Z, a plan of k intents by 19:00Z less 15 minutes per intent — 18:45Z, 18:30Z, 18:15Z — and the arm file is gone by **19:05Z**.
3. **Place the arm file at this window's first drop** (arm step 6), whether or not the 12Z window placed one.

<a name="rung-2-after-a-restart"></a>

#### 5. After an engine restart — the boot, the book, the balances, the hold, the drills

The box plans no engine restart. What restarts the engine inside it is a restart nobody planned — a crash or a start the supervisor healed, a cache failure, a reboot from the provider's side — or the owner's hand, for a sell the venue record's balance holds back (item 5) or a reboot that will not wait ([step 10](#rung-2-what-not-to-do)). `Fleet · a daemon restarted` with `job="engine_app"` is the cue for this step, and the next gate read shows `restart_hold`. The engine host does not reboot itself: its upgrades install unattended and its reboot waits for you (no count command: `base_unattended_upgrades_automatic_reboot` in `infra/ansible/group_vars/capture_host/vars.yml` holds it). A restart you did not take starts at item 3. Where it fell inside a day's window with the arm file in place, the gate reads `level=reduce_only`, `reasons=restart_hold`, and clearing the hold at item 7 would arm the engine ahead of the drills: remove the arm file first — disarm step 1, `sudo rm /var/lib/zcrypto-engine/exec/armed`, gate read `level=none`, `reasons=arm_file_absent,restart_hold` — then read the ledger as [step 3](#rung-2-the-day-s-window) item 7 does. Record each restart in `data/rung2/days.md`, its time and its cause: [step 8](#rung-2-the-last-days) asks whether one happened.

1. **A restart by your own hand takes its reads first.** Inside the inter-cycle gap — from 5 minutes past the boundary record's `completed_at` to 15 minutes before the next boundary, read from the record and not the clock with [`engine-adhoc-key-read`](#engine-adhoc-key-read) step 3's read — with no plan in flight, the arm file removed, and clear of the cache nodes' reboot slots at 09:25, 13:25 and 17:25. On the workstation, read Kraken's maintenance feeds whole with [`order-semantics-verification.md`](order-semantics-verification.md) §1.1's command, `START` the minute you run it and `END` the gap's close, and its output as that section reads it: a `STOP` line holds the restart until that entry has passed (`.claude/rules/fleet-deploys.md`). Take [the restart rule](#engine-restart-margin-position)'s four reads; its `kraken positions -o json`, on the workstation, lists no margin position, since the book holds none, and the paragraph under the rule says what its boot-line read shows for a spot lot.
2. **Restart, on the host, reading the start time either side**:
   ```
   sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine
   sudo systemctl restart zcrypto-engine
   sudo systemctl status zcrypto-engine --no-pager
   sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine
   ```
   The status reads `active (running)`. The second inspect can print `error: no such object` for the first seconds, while the unit pulls its image: run it again after ten seconds, until it prints a time later than the first. A restart that comes straight back is expected to page `Fleet · a daemon restarted` alone — the proxy and cycles pages need the engine down for minutes ([`engine-clear-stored-account`](#engine-clear-stored-account) step 4).
3. **Read the boot.** On the host, pre-probe step 8's read — `sudo docker logs --since 30m zcrypto-engine 2>&1 | grep -E 'cache restore|Received [0-9]|Reconciliation complete|the venue holds|Unresolved positions|Failed to get mass status|could not be read|fill on restored order|instrument not in cache|order event ignored|Failed to load account|CRITICAL'` — with a duration that reaches back past the start, `24h` where the restart was found a day later, and its output non-empty before anything is read into it. For each leg held through the restart it shows one `cache restore: position <instrument> <quantity> @ <entry price> (ShadowStrategy-000)` line at the engine's lot and one `(EXTERNAL)` line at minus it: the engine's own book nets 0 on a lot Kraken holds, which is this build's known behaviour ([the restart rule](#engine-restart-margin-position)'s paragraph on a spot lot) and no mismatch. The comparison with Kraken is the WARNING `the venue holds <q> <leg> where the Cache reads 0.0 -- the position gauge takes the venue's figure at the startup pass`, one per held leg: on the workstation, take a fresh `kraken extended-balance -o json`, where `<q>` is Kraken's balance of that coin to the leg's lot step, and `kraken open-orders -o json`, which lists no order. The same line for a leg that is not held, reading `where the Cache reads 0`, is reward dust Kraken holds on that coin, compared with Kraken's balance like the others, and no stop. A line closing `at the re-read pass` is the same comparison taken again later in the process, with the Cache's figure as it then stands, and no new reading of the boot. No count of reconciliation lines and no `positions=` figure is expected: both depend on what traded since the previous start. A leg sold whole since an earlier restart shows no line, the boot closing the `EXTERNAL` short that sale left.
   - **Known line, no stop.** After a restart taken with DOGE held, each later start logs `Failed to load account KRAKEN-001: Failed to convert value to target type: Unknown currency: XDG` once at ERROR and completes; it pages nothing.
   - **A stop.** An `Unresolved positions` line is a start that failed, and a `could not be read` CRITICAL line refuses each plan until one more restart ([arm step 4](#adopt-pass-by-txid) says what each means): place nothing, and take the line to the owner.
4. **From this restart on the engine's held figures are not used: Kraken's exports are the book.** The venue record's `positions`, the cycle record's `held` and the helper's engine-held column read 0 on a leg held through the restart, and from there the trades since it alone: the quantity bought since on a leg bought, minus the quantity sold on a leg sold. The helper's `engine held is the engine Cache's net` line lists the held legs from here on. Compare nothing with those figures: [the account stop](#rung-2-account-stop)'s holdings comparison changes with this restart, and the exit owes a closing restart ([step 8](#rung-2-the-last-days) item 5).
5. **The venue record's balances are the engine's stored account, not Kraken's holdings.** The cache store holds the account, a start replays it, and that start's read of Kraken is merged into it coin by coin: a restart adds or raises a coin Kraken then holds and drops none, since Kraken's balance read leaves out a coin at zero, and no fill inside a process moves a figure. So from a restart on, the venue record's balances — the `venue b` column of the helper's table — carry each coin at what Kraken held when the engine last started with that coin above zero: the lot held at that restart with its reward credits, whatever was bought or sold since, and reward dust on a coin that was not held. The one start known not to replay the account is the `XDG` one of item 3, and what its record carries is unread: the `venue b` column prints the record as it is. The engine refuses a sell above a positive `b` (*What it means*), and does so through the box: a sell check that reads Kraken's balances itself is an engine change, which comes after the box, the image being frozen through it ([step 10](#rung-2-what-not-to-do)). What raises `b` is a restart taken with the lot held: the start's read puts Kraken's figure for that coin on the account, and the first boundary record written after it carries it — read live on 2026-10-01 for a coin the account did not carry, measured on the offline restart harness for a coin it carried at a lower figure. A restart taken with the coin at 0 at Kraken changes nothing, and neither does a small-balance conversion; what removes a coin Kraken no longer holds is [`engine-clear-stored-account`](#engine-clear-stored-account), on a flat account. Inside the box the restart that raises `b` is the owner's decision ([step 10](#rung-2-what-not-to-do)): it is this step again from item 1, and the leg is then drafted from the first boundary record written after it — the 16Z record in [the 16Z fallback](#rung-2-the-16z-fallback) after a restart in the 12Z gap, for a leg no plan placed that day, or else the next day's 12Z record; at the exit it is [step 8](#rung-2-the-last-days) item 2's. The helper drafts what the engine admits, and the leg's detail says which case it is:
   - `capped at the venue record's b <b>, under the sell qty <qty>; the remaining <left> carries to a later draft …` — the sell is drafted at `b` floored to the lot step, one such sell a day, and the rest waits for a later draft or for that restart;
   - the same opening closed by `the remaining <left> is under ordermin <ordermin>: dust`, on a leg sold whole, or by `the remaining <left> of the sell is under ordermin <ordermin> and is not drafted`, on a partial sell — the sell is drafted at `b` and nothing is owed;
   - `the venue record's b <b> is under the sell qty <qty>, which the engine refuses, and under ordermin <ordermin>, so no part of the sell is placeable …`, which sends its reader to this item — `b` is dust, the reward credited on a coin that was not held at a restart and was bought since. The leg is carried at each draft until `b` rises.
6. **The probe-window procedure's pre-probe steps 1–8 again**, as step 2 item 2 says: step 3 reads the running version against its record, and step 8's counts go beside the new boot line, under the restart's entry in `data/rung2/days.md`.
7. **Clear the hold** on the host, once items 3 to 6 are read — arm step 4's gate read and arm step 5: the gate read shows `level=none`, `reasons=arm_file_absent,restart_hold`; then `sudo rm /var/lib/zcrypto-engine/exec/restart-hold`, and the gate read shows `reasons=arm_file_absent`. Arm step 4's `no open positions, EUR only` is a flat account's reading, not expected here with lots held, and no stop.
8. **Drills A and B in spot form, before the next plan**, as on entry day (step 2 item 4), each with a `plan_id` the ledger does not already hold for today or yesterday. The arm file they need is removed by 55 minutes before the next boundary, and stays down unless a funded plan follows inside the window.

<a name="rung-2-account-stop"></a>

#### 6. The account stop — pause, and resume on the owner's written word

1. **Any one of these stops the box's plans** (no count command: each is an operator read of Kraken, the ledger or the host, and nothing in the tree records the pause):
   - Kraken's equity is EUR 60 or more below the entry value;
   - the kill switch tripped — work [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) beside this;
   - an `ambiguous` or `revoked` outcome that Kraken's open and closed orders do not explain;
   - a trade row in Kraken's ledger export that no journaled fill matches, made by a hand act or the red button;
   - a difference in a leg's holding that the day's rows do not explain. Until the engine restarts inside the box it is read between the engine's held and Kraken's held, the helper's two columns; from a restart on, between Kraken's held and what the plans' fills and Kraken's own ledger rows account for — the leg's Kraken-held figure at the last draft, in the decision log, and the fills placed since, in `data/rung2/days.md`. A `staking` credit on a held coin and the `spend` and `receive` rows of a small-balance conversion are explained rows, neither a hand act nor a stop, though no row of the engine's journal stands behind them: `kraken ledgers -o json` on the workstation lists them.
2. **Place no new plan, and remove the arm file** on the host: `sudo rm /var/lib/zcrypto-engine/exec/armed`. Removing it mid-plan revokes the intent in flight, so read the ledger, and `kraken open-orders -o json` on the workstation, after it.
3. **Record the stop** in `data/rung2/days.md` — the trigger, the reading, the time.
4. **Resume only on the owner's written word** (no count command: the word is the owner's act), recorded beside the stop. A pause moves none of the box's dates.

#### 7. Each Monday from 2026-10-12 — the weekly read

1. **Export Kraken's ledger** (Kraken → History → Export → Ledgers) from 2026-10-05 to the Sunday just closed.
2. **Run the tracking report from the box's first day**, not from the week's: the report takes held from the fills inside its window, so a window that starts mid-box scores a book without the buys before it.
   ```
   uv run zcrypto engine tracking-report \
     --journal-dir /mnt/zhao-crypto/engine-journal --since 2026-10-05 --until <the Sunday just closed> \
     --gate-from 2026-W45 --ledger-export <the export>.csv
   ```
   `--gate-from 2026-W45` places each box week before the boundary, so the report labels each one rung 2 and decides none (the probe-window procedure's verify item 8 says how to read that echo).
3. **Read the drift as description, not a verdict.** It is scored against each record's own NAV of 1000, not EUR 720, and LINK/EUR is not held, so it carries a standing gap — about 28% of the nine legs' gross weight plus LINK's whole weight, as a share of NAV — that is the box's sizing, not tracking error.
4. **Read the ledger reconciliation** as verify item 3 does: each unmatched id explained by a repair or by your own account act, and a trade nobody can account for is [the account stop](#rung-2-account-stop). The `rows with no fill behind them by construction:` line carries the week's reward credits as `staking <n>`: expected rows, read against the legs held that week.
5. **Record the week** in `data/rung2/days.md`: its labels, drift, cost lines and the reconciliation's verdict.

<a name="rung-2-the-last-days"></a>

#### 8. The last days — Sat 10-31 exit, Sun 11-01 reserve, Mon 11-02 disarm

1. **Sat 2026-10-31 — the exit, in the 12Z window.** Step 3 with `--exit` added to item 4's command: every leg's target is 0, so each held leg is sold whole through the engine, its `qty` Kraken's whole balance of the coin, reward credits included, floored to the lot step, and nothing is bought; the report's first line opens `EXIT: every leg's target is 0`. The plan rules hold as on other days: at most 3 sells and EUR 95 a plan, one plan at a time, each from fresh exports. The helper refuses a draft without `--exit` on this day and on Sunday, and refuses `--exit` on an earlier day (no count command: `box_day_refusal` in `cli/engine/draftplan.py` holds both refusals).
2. **An exit sell the venue record's balance holds back** — after a restart inside the box, a leg whose `venue b` is above zero and under Kraken's balance ([step 5](#rung-2-after-a-restart) item 5). Place the sell the helper capped as drafted, at `b`; a leg it carried whole places nothing, and a capped leg whose line closes `: dust` owes nothing more. Once Saturday's last plan is terminal and the arm file is removed, take the balance export again and read what Kraken still holds of each such leg against its `venue b`, which no fill moves. Sunday's draft closes a leg held at or under `b`, or above it by less than its `ordermin` where `b` is at least that `ordermin`; a leg in neither case and at or above its `ordermin` it would cap or carry again. For such a leg, restart the engine with what is left still held, by step 5 from its item 1, in the first inter-cycle gap after that last plan, so that a boundary record written after the restart, which carries Kraken's figures, exists before Sunday's draft:
   - **after the 12Z window's last plan** — the 12Z gap, which closes at 15:45Z. Saturday's 16Z record is the first written after it: a leg no plan placed on Saturday is drafted from it with `--exit`, in [the 16Z fallback](#rung-2-the-16z-fallback), and a capped leg's remainder is Sunday's, drafted from Sunday's 12Z record;
   - **after the 16Z fallback's last plan**, on a Saturday whose exit ran or finished in that fallback — the 16Z gap, from the arm file's removal, by 19:05Z, to 19:45Z. Saturday's 20Z record is the first written after it, and each leg left is Sunday's, drafted from Sunday's 12Z record;
   - **a gap that closed before the restart was taken** does not drop the restart: a later gap, up to Sunday's 08Z gap, which closes at 11:45Z, still puts a boundary record before Sunday's draft.
3. **Sun 2026-11-01 — the reserve window**, 12Z as usual, drafted with `--exit` again, for a Saturday exit sell that ended `unfilled`, `partial`, `refused` or `rejected`, and for the remainder of a capped one. A draft with nothing left to sell places no arm file.
4. **The box ends flat at Kraken.** On the workstation, the balance export shows each of the nine coins below its `ordermin`, and `kraken open-orders -o json` and `kraken positions -o json` list nothing. That is the verdict, and the engine's `positions` are no part of it (item 5). What is left under an `ordermin` is dust no order can sell: a lot-step remainder, or a reward — Auto Earn is on, and a credit can arrive up to a week after a coin was last held. It stays where it is: whether it is converted is the owner's decision, and [step 10](#rung-2-what-not-to-do) says how a conversion is done. A coin left above 0.000001 keeps `zcrypto-engine-dark-with-exposure` armed after the exit ([`engine.md#zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure)).
5. **If the engine restarted inside the box, the exit owes one more restart**, taken once the exit's last sell is terminal. The exit's sells close the engine's own longs and leave each `EXTERNAL` short open, so until that restart the venue record's `positions` read minus what was sold: the offset, and no holding. The next start closes the shorts; what a leg's dust leaves in its restore lines is unread. Item 6's converge restarts the engine and is that restart, unless a reboot of `zcrypto` held back for the box ([step 10](#rung-2-what-not-to-do)) is taken first, after item 4 reads flat. In a box the engine did not restart in, the newest venue record's `positions` carries its twelve entries, each `0` or dust-sized: a spot leg's unsellable remainder is a position in the engine's cache, so it shows in `positions` too, where verify item 5's dust shows in the balances alone.
6. **Then the deferred disarm converge, on Mon 2026-11-02**, the day after the box, so no engine converge falls inside it — the probe-window procedure's disarm step 2 with the tree already reading `false`, inside an inter-cycle gap, the maintenance feeds read whole at planning time and again right before (`.claude/rules/fleet-deploys.md`), its preview changing the one line `exec_armed = true` → `exec_armed = false`. Disarm step 3 then reads three reasons. The venue record written after its restart is the engine's own flat reading, recorded beside item 4's (verify item 4): `positions` each `0` or dust-sized (item 5), and `balances` the stored account's ([step 5](#rung-2-after-a-restart) item 5) — EUR, a coin Kraken still holds as dust, and, after a restart inside the box, the figure a coin held at that restart was left at, which is no holding.

<a name="rung-2-exit-report"></a>

#### 9. The exit report — read in W45, by Fri 2026-11-06

Recorded in `docs/research/14.phase6-decisions.md`, from these readings:

1. **The ruling as fixed at entry**, unchanged.
2. **The tracking report over the box** — step 7's command with `--until 2026-11-01` and the box's whole ledger export.
3. **The fee re-pricing reading** (`docs/open-topics/T0214-cost-basis-re-priced-at-rung-2.md`): the cost basis re-priced from the box's own fills, the population stated, fees from the ledger export. With no taker fill in the box, the record says the taker share is unobserved, and that term stays open until rung 3.
4. **The decision log** — `data/rung2/decisions.jsonl` with `data/rung2/days.md`: each day, each leg, target, Kraken held, engine held, the venue record's balance, placed or carried and why, and the window's minutes. From a restart inside the box on, the engine-held figure is the trades since that restart, recorded and compared with nothing.
5. **The exec-ledger tally and the holdings reconciliation** — the ledger read with `HOURS` reaching back to 2026-10-05: plans, intents by outcome, orders, fills; and, per leg at exit, Kraken's balance against the journal's fills since entry, buys less sells, with the ledger export's `staking` credits and a conversion's `spend` rows accounting for the rest.
6. **The account reconciliation** — Kraken's equity at entry and at exit, fees, and the realized result, from the ledger export, with no deposit or withdrawal between them.
7. **The governor over the box**: `uv run zcrypto engine decompose --journal-dir /mnt/zhao-crypto/engine-journal --since 2026-10-05 --until 2026-11-01`.
8. **The ops log** — the box's entries in `docs/reference/ops-journal/2026-10.md` and `2026-11.md`.
9. **The Blockpit re-sync** — the Kraken depot re-synced, as the probe-window procedure's execute step 7 does it, with pass or fail.

<a name="rung-2-what-not-to-do"></a>

#### 10. What not to do

- **No hand trade in Kraken's web UI** (no count command: a hand act on Kraken is the owner's, and the weekly reconciliation is where it shows). It pauses the box: [the account stop](#rung-2-account-stop).
- **No red button except in an emergency** (no count command: a press is the owner's act). `sudo zcrypto-flatten --execute` ([`engine-flatten`](#engine-flatten)) sells the whole account and stops the engine; it pauses the box like a hand trade.
- **No small-balance conversion on Kraken's site inside the box** (no count command: a conversion is the owner's act on Kraken, and the ledger export is where it shows): it is step 5 of [`engine-clear-stored-account`](#engine-clear-stored-account), done with the engine stopped on a flat account, so reward dust stays where it is until the box has ended.
- **No discretionary engine restart inside the box** (no count command: a restart leaves no row in the tree; `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine` shows the last one) — a pending reboot of `zcrypto` and a package upgrade that restarts the container runtime included. Each is an engine restart with the lots held, and owes what [step 5](#rung-2-after-a-restart) works through, a closing restart at the exit among it. The reboot-pending page keeps firing and waits: the reboot is taken after the exit, once [step 8](#rung-2-the-last-days) item 4 reads flat, where it is also step 8's closing restart, or beside the Mon 2026-11-02 disarm converge — by `docs/reference/fleet.md`'s Reboots either way. The restart a held-back sell needs (step 5 item 5), and a reboot the owner judges will not wait, are the owner's decisions, and each is step 5 from its item 1.
- **No engine-touching converge against `zcrypto`** (no count command: tags are the operator's; the deploy-log check in *What it means* reads them afterwards) — no `--tags engine`, `docker` or `cache-link`, and no un-tagged run. The one converge the box owes is step 8's, on Mon 2026-11-02 after it.
- **A cache-node converge takes one node per run** — the cache play's own charter — **outside the day's window and away from an engine restart** (no count command: a run's limit and time are the operator's; the deploy-log rows record them).
- **PR #646 stays unmerged.** Its nautilus bump is a version the arming record does not list; the engine image and nautilus `2.0.0rc6.dev20260921` are frozen through the box.
- **No edit of `/opt/zcrypto-engine/zcrypto.toml` on the host** (no count command: a hand edit on the host is an operator act nothing in the tree records), and no plan written in place of `probe-plan.json` — a plan is placed by `mv`.

### Retire when

The exit report is recorded in `docs/research/14.phase6-decisions.md` — by Fri 2026-11-06, or Fri 2026-11-13 if the box slipped a week. The box is over; what rung 3 runs is its own procedure.

<a name="engine-tracking-band"></a>

## engine-tracking-band — PROCEDURE

### What you are seeing

You are deciding whether to arm the engine's weekly tracking-error trip, or you are looking at the **Weekly tracking error — last verdict** tile on the engine board and want to know what it is telling you. **Nothing has fired**: if the trip had latched, `zcrypto-engine-exec-kill-tripped` would have paged and [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) is the one to work.

### What it means

At every 4-hourly boundary — after the cycle has journaled, and reading nothing but the journal — the engine scores the **most recently closed ISO week**: what its cycles targeted, against what its own fills say it actually held, as a mean drift in bps of NAV. If that mean exceeds the configured band, the engine latches the kill file, cancels everything resting and refuses every further order until a human clears it.

It exists for the failure no other guard can see: an engine that has quietly **stopped placing orders**. Every other execution guard sits behind an operator-authored plan file, so none of them can fire in a window where nothing is being submitted at all — while the targets keep moving and the book keeps standing still.

Worth knowing before you touch anything:

- **It ships disarmed and stays that way until a band is set.** `tracking_band_bps` is absent from `[zcrypto.engine]`, and with no band nothing can be exceeded. The tile reads `DISARMED`; that is the correct resting state, not a fault.
- **It carries no scoring checkpoint.** The week is re-derived from the journal every four hours (the one file it keeps, `exec/first-fill`, dates the series rather than the score — Disarm step 4 of the probe-window procedure), so a fill journaled late — filed under the boundary its ORDER was filed under, days after the fact — is folded in at the next boundary rather than lost (no count command: `on_boundary` in `cli/engine/executor.py` calls `_evaluate_tracking` at each boundary).
- **It refuses far more often than it decides.** A config not armed for submission and a kill file already latched refuse before any scoring; then a week short of its 42 boundaries, a week that spent any boundary below the `full` gate level, a journal with no model-leg fill in it yet, the week the fill series started in, a week the journal cannot score (a hole in the cycle span, a fill outside the basket, a record that cannot be priced), and a journal whose head no longer reaches the engine's own first-fill record are all `NOT SCORED` (no count command: the refusals are `_refuse_tracking`'s callers in `cli/engine/executor.py`). Each is a deliberate refusal: refusing costs a week of coverage, guessing halts live trading.
- **It has no alert rule of its own, deliberately.** The only value that is a fault — the band breached — latches the kill file, and `zcrypto-engine-exec-kill-tripped` already pages on exactly that (no count command: `tests/test_infra_alert_rules.py`'s `NOT_A_FAULT_SIGNAL` entry for `zcrypto_exec_tracking_state` holds it). A rule here would double-page one event and would page on nothing else.
- **It stops scoring for good once the journal's head is pruned, and that is by design.** What it measures is cumulative from the engine's first ever fill, while the journal prune deletes whole day-dirs at `engine_journal_retention_days` (60). Once the day holding that first fill ages out, the position bought before the horizon is simply not on this host, and a week scored without it reads several hundred bps high — a latched kill file on an engine that never misbehaved. The engine records the date of its first fill once, in `exec/first-fill`, and from the moment that date falls off the journal it refuses every week with that reason in the log (no count command: `_score_closed_week` in `cli/engine/executor.py` refuses on `birth != first_fill`). **There is no operator action that restores it**: the fills are gone. Raising the retention, or journalling the position alongside the cycle's `closes`, is the fix, and both are changes to make deliberately rather than in an incident.

### What to do

**If the tile reads `OUTSIDE BAND`** — the kill file is latched and the alert has already paged. Work [`engine.md#zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped). `sudo cat /var/lib/zcrypto-engine/exec/kill` names the week, the mean it measured and the band it was measured against; that text is the only record of why the engine stopped, so read it before removing anything. The engine will not re-score while the file is present, so the first reason stays exactly as it was written.

**If the tile reads `NOT SCORED` and you expected a verdict** — the reason is in the engine log, one line per boundary: `sudo docker logs --since 5h zcrypto-engine | grep 'not scored'` (a bare `--since HH:MM` does not parse; pass a duration or a full timestamp, and confirm the log lines you got are non-empty before reading anything into a quiet grep). One of those lines reads `the evaluation itself raised` and carries a Python traceback underneath it: that is the measurement failing rather than declining, it means the same NOT SCORED on the tile, and it is a defect to report rather than an operational state to work.

**If the tile is absent entirely** — no boundary has been *reached* since this process started, or the family is not shipping. (An unscored boundary still publishes a state, so "not scored" is never why the tile is missing.) Read it by value from the workstation: `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_tracking_state{host="zcrypto"}'`. `(no series)` after a boundary has passed is a keep-regex failure, not a quiet engine.

**To arm it** — three preconditions, in this order, and none of them is optional:

1. **A window has journaled `full`.** Run the count in the probe-window procedure's verify step above. Every exec record written outside an armed window reads `level: "none"`, and the restart hold is written at every engine start and cleared only by hand (no count command: `evaluate` and `write_restart_hold` in `cli/engine/execgate.py` set `none` and latch the hold; nothing under `cli/` clears it) — so a week spent held reads `reduce_only` at best, and any week with a boundary below `full` is refused as `NOT SCORED` rather than scored. A week the engine could actually trade must be able to show 42 records reading `full`; if it cannot, the hold-clearing step is what changes, before any band is set.
2. **A band exists that real weeks have been measured against.** `uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <first day> --until <last day>` on the workstation prints each week's realized mean beside the floor the venue's own minimums impose. The band is a number chosen from those readings and recorded in `docs/research/14.phase6-decisions.md`, never one invented here (no count command: where a band's number came from is an owner's act nothing counts).
3. **The band is deployed as config.** `tracking_band_bps` is read from `[zcrypto.engine]` in the rendered `/opt/zcrypto-engine/zcrypto.toml`; the engine role's template does not render the key today, so arming means adding it there — one line, reviewed like the `exec_armed` line beside it — and converging inside a 4-hourly inter-cycle gap, with no Kraken margin position open beyond those [the restart rule](#engine-restart-margin-position)'s test admits. Verify by outcome at the next boundary: the tile moves off `DISARMED`, and `grafana-query.py` reads a number rather than `(no series)`.

Three standing conditions once it IS armed, each of which silently changes what a scored week means:

- **A verdict needs 42 CONSECUTIVE boundaries at `full` — seven unbroken armed days.** No attended probe window is anywhere near that long, and `zcrypto-engine-exec-armed-too-long` pages after six unbroken hours armed. So an operator who satisfies all three preconditions above and arms during ordinary attended windows gets `NOT SCORED` forever, correctly. **Verdicts only ever arrive in continuous-trading mode** (no count command: `_WEEK_BOUNDARIES` in `cli/engine/executor.py` is 42, and `infra/grafana/alerts.yaml`'s armed-too-long expr reads `[6h]`), and that alert's threshold is the thing to revisit first when that mode arrives — before the band, not after.
- **Disarm the band across a `shadow_nav_eur` change only while a cycle record predating the journal's `nav` key is still inside the scoring window.** (no count command: `realized_drift` in `cli/engine/tracking.py` falls back to the live scalar for such a record) Each cycle is now scored under the NAV journaled with it (`cli/engine/tracking.py`'s `cycle_nav`); older records fall back to the live scalar, and for those a converge still re-prices a week that closed under the old value — halving NAV roughly doubles every reading of a week nobody traded differently, straight into a latched kill file.
- **Disarm the band across a basket widening.** The trip demands every model leg's target in every record it reads, so the first record written under a wider basket makes every earlier one un-scoreable (no count command: `_stage` in `cli/engine/executor.py` refuses a record whose targets are not the model's legs). The refusal is the safe direction, but it lasts until the whole scored span post-dates the widening — a full week — and reads as a broken trip if nobody expects it.

**To disarm it** — remove the key and converge, under [the restart rule](#engine-restart-margin-position)'s test like any converge. Nothing else clears it; the disarmed state is the absent key.

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

**Proven live on `2.0.0rc6.dev20260921`, 2026-09-24** (`docs/reference/adapter-verification/2.0.0rc6.dev20260921.md`, *The window as run*): the reduce-only market close, at leverage 2 on a position opened at 2, and the five account reads, by the [read-only dry run](#flatten-read-only-dry-run). A closer whose leverage differs from the position's is unmeasured (`MARGIN_LEVERAGE` in `cli/engine/flatten.py`). The drill program's decision-to-flat drill is a separate measurement.

<a name="flat-verdict-reads"></a>

**What the flat verdict reads.** The command caches the venue's whole listing first and reads open orders and positions unscoped, under either of Kraken's spellings of a pair; a read that fails before the cancel is named in the plan, the account-wide cancel still goes out, and the run ends at exit 2, never 0. Exit 0 means the order, position and balance reads before the cancel and the final read each came back whole — not that they held every row: an open-order or balance row the adapter cannot parse drops out of its read without failing it. **Confirm it on Kraken's own pages all the same — step 4**; if an order is still resting there, press the button again, which sends the account-wide cancel again.

### What to do

1. **Read the plan first. It sends nothing.**

```
sudo zcrypto-flatten
```

It prints how many orders rest with one line under the count per order — pair, side, volume and venue txid — every position it would close with its side and quantity, every balance it would sell with an estimate at the taker rate, every balance below the venue's minimum that it will list and not send, and every balance no EUR or BTC pair can carry. The count is every order the read resolved and parsed ([what the flat verdict reads](#flat-verdict-reads)): when the order read fails, the plan prints that failure in place of the count, says the account-wide cancel reaches the unread orders, and says a press could not end at exit 0; a position read it had to take pair by pair is named the same way. It exits 0 once the plan is printed, and changes nothing — a failed open-order or position read the plan names still ends at 0, so a 0 does not say the reads came back; 3 if the venue is not online or a read the plan cannot do without failed (the listing, the balances, or the positions even pair by pair), 1 if the plan could not be printed, both of them having changed nothing either. Its reads share the trade key with a running engine, so one engine order or cancel may be rejected around them; the engine reconciles that at its next 4-hourly boundary.

2. **Press it.**

```
sudo zcrypto-flatten --execute
```

The kill file is written, the engine is stopped, the plan is printed again from a fresh read, and it asks you to type `FLATTEN`. Anything else aborts and nothing is sent. It reads the word from the terminal, never from a pipe, and there is no flag that skips it.

3. **Read the exit code.** It is the whole verdict, and it never reads a single leg's answer (no count command: `exit_code` in `cli/engine/flatten.py` reads the final snapshot and the write failures, not a leg).

| code | what it means | what to do |
| -- | -- | -- |
| **0** | no resting order, no open position, nothing sellable left, on reads before the cancel and a final read that each came back whole ([what the flat verdict reads](#flat-verdict-reads)) | go to step 4 |
| **1** | refused with nothing sent, the refusal naming which gate stopped it | nothing was sent; fix what it named and run it again |
| **2** | something is still open, or the account-wide cancel failed, or a read after the cancel that the sweep acts on failed, or a read before it could not see everything | go to step 5 |
| **3** | the venue could not be reached or read **before anything was sent** — a failed open-order read is not this: it goes on and ends at 2 | nothing was sent; the account is as it was |

4. **Confirm it by eye on Kraken.** Open orders, open positions and balances on Kraken's own pages: exit 0 rests on the command's own reads, which leave out an order or balance row the adapter could not parse ([what the flat verdict reads](#flat-verdict-reads)). The engine stays stopped and the kill file stays in place until you decide otherwise — that is what stops anything re-opening. A stopped engine pages, the unit's stop taking the cache proxy down with it: [`engine-clear-stored-account`](#engine-clear-stored-account) step 4 names the pages, which say the engine is down, as the press meant.

5. **On exit 2, read the record.** It is `/var/lib/zcrypto-engine/exec/flatten-<timestamp>.json`, and the command prints its path. Each leg carries what was sent and what the venue answered.

- **Every leg answered without an error, and something is still listed?** (no count command: the legs are one run's record, on the engine host rather than in the tree) The venue may simply not have settled yet — the final read is taken immediately. **Run it again**; a second run finds less to do and does it. A second exit 2 naming the same residual is real.
- **A leg reads `unclosable_below_minimum`?** That label is what *this command* read before it sent anything: the position was smaller than the pair's minimum order size. It is never read off the venue's answer (no count command: `_send` in `cli/engine/flatten.py` labels from the pre-send size; the settle is the venue's own), so **read the `error` beside it in the record first.** No `error` at all means the quantity floored to nothing and there was never an order to send. An `error` naming a rate limit, a temporary lockout or any other passing condition is a refusal that may not be about the size at all — **run the command again**, and judge the label on what the second run answers. An `error` that keeps saying the order is too small is the real case: no order can clear that remainder; only Kraken's own settle-position action in the web UI can, and the adapter cannot send it.
- **A balance reads `no_eur_or_btc_pair`?** The venue lists no EUR and no BTC pair for it, so this command cannot sell it (no count command: `cli/engine/flatten.py` sets this label where the listing carries neither pair). Sell it by hand on Kraken against whatever pair exists.
- **A leg reads `dust_below_venue_minimum`?** Nothing is wrong. The venue would reject that order, and a balance that small is not exposure.
- **A leg reads `no_reference_price`?** No book price backed it: either it surfaced after the plan was priced — no book is read once the cancel has gone out — or its own book could not be read, or answered no usable price. It was sent anyway, sized on the venue's quantity floor alone. The order still went out; the label asks nothing of you, and what the venue answered beside it is the answer.
- **A position reads `pair_not_listed`?** The venue's listing carries no pair for it, so nothing could be sized and no order was sent — everything else was still cancelled, closed and sold. Close that position by hand on Kraken.
- **A position reads `unrecognised_position_side`?** The venue answered a side this command cannot derive a close from (no count command: `cli/engine/flatten.py` files such a row as unclosable and builds no leg for it), so nothing was sent for that row — everything else was still cancelled, closed and sold. Read the row on Kraken's own positions page and close it there; the side it shows is the finding.
- **A residual reads `resting_order`, `sellable_balance` or `unjudgeable: …`?** These describe the final read rather than a decision made before sending: an order still working, a balance still above the venue's minimums, and a balance whose pair's constraints could not be read back. The first two mean the sweep did not finish the job — run it again. The third means that balance could not be judged at all: check it by hand on Kraken.
- **The record says a read after the cancel failed?** The account may have moved and the run stopped where it stood. Read Kraken's own pages, then run it again.
- **The record names `orders_unread`, `positions_unreadable` or `position_unread`?** A read could not see everything, so the run ended at 2 whatever else it found. The ones taken before the cancel are in `snapshot_before.unread`, the final reads' among the `residuals`. `orders_unread`: the open-order read before the cancel failed, and the account-wide cancel went out regardless, reaching the orders nobody read. `positions_unreadable`: the whole-account position read failed and each basket pair was read on its own. `position_unread`: a basket pair whose own read failed, or one the listing does not carry. Which positions got a closer is not in these names: the closers are sized by a separate position read after the cancel, whose own per-pair misses the record does not list, and a basket position Kraken spells by its altname is not seen by a read taken pair by pair. The `error` beside each says why; a row on a pair the listing does not carry fails a whole read this way. Read Kraken's own Open Orders and Positions pages, close by hand what is still open there, then run it again.

6. **Do not clear the kill file to restart the engine until you have decided the reason no longer holds**, nor while a Kraken margin position is open that [the restart rule](#engine-restart-margin-position)'s test does not admit. Clearing it is the same procedure as for any other latched halt (no count command: every latch is the one `KILL_FILE` of `cli/engine/execgate.py`), in [`engine.md`](engine.md#zcrypto-engine-exec-kill-tripped).

<a name="flatten-read-only-dry-run"></a>

### The read-only dry run that proves the five reads

Not part of a press — nothing is sent.

1. **After the engine converge that carries the wrapper, never before.** (no count command: the dry run's order against the converge is an operator act) `/usr/local/sbin/zcrypto-flatten` reaches the host with that converge and not earlier.
2. **With the engine running or stopped, and a NON-EUR spot balance the command can sell.** A dry run neither stops the unit nor reads whether it runs. Not while the engine is starting: its one startup read of the venue's orders is never retried, and a dry run on the same key can have it refused for its nonce, which refuses every plan until a restart. `spot_legs` skips the euro, skips a zero free balance, and skips a code it cannot resolve to a listed `/EUR` or `/BTC` pair — and the book read, the fifth shape, is made only for a leg. With no leg at all — nothing sellable and no margin position open — four of the five are proven while the row would say five. If the account has none, `infra/scripts/mint-with-vaulted-key.sh` mints one. It mints every ingredient the account is missing — the sellable balance, a resting order and a margin position — and there is no way to ask for only one (no count command: `spot_legs` in `cli/engine/flatten.py`; `infra/scripts/kraken-fixture-mint.py` takes `--pair` and `--execute` alone, with no cancel path), so read the printed plan for what it will actually send. Nothing unwinds them: the script has no cancel path, so the resting order and the position stay in the account until a real press closes them or someone closes them by hand on Kraken's own pages — and while that margin position is open the engine is neither converged nor restarted, since a position the mint opened is one the engine's cache never saw and [the restart rule](#engine-restart-margin-position)'s test refuses. It is attended, run from a workstation rather than on the host, and prints its plan without sending anything until `--execute` and a typed word; it places orders and cannot cancel them, so read the plan before confirming. The key it uses is IP-bound: `order-semantics-verification.md` section 1.3 adds the workstation's address and section 7.3 removes it again — the removal is mandatory, not an afterthought.
3. **On the engine host, through the wrapper:**

```
sudo zcrypto-flatten
```

4. **Record it**, in the shape drill G's extra reading uses: discharged into `docs/reference/adapter-verification/<the running version>.md` beside that version's probe table, as a row proving the five read shapes against the real venue. A plan that prints `a read above failed` is not that row, whatever its exit: run the dry run again once the read comes back, and record that run. When a margin position is present, record what the positions read returned **against a position known to be there** — a position seen is the whole proof. Record the client order ids in the same row, as an observation: the minter's ids are 17 characters, `FIXMINT-<R|M|S><ddHHMMSS>` — R for the resting leg, M the margin leg, S the spot leg, then the run's UTC day and time — which the adapter sends as they are, and each `sent` line the minter prints names a leg's id beside the venue txid it was accepted under. Quote each leg's id and txid from those lines, and the `cl_ord_id` Kraken shows for it — `kraken open-orders -o json` on the workstation for the resting leg, `kraken closed-orders -o json` for the two market legs, which are closed before the run ends — and note whether each came back unchanged.

<a name="flatten-dry-run-before-converge"></a>

### A dry run of an image before its converge

The wrapper runs the digest it was rendered with, the one the engine runs now. To read the account through an image a converge is about to deploy, before the engine depends on it, run the wrapper's own `docker run` line by hand with only the digest changed. It sends nothing and touches neither the engine nor its kill file. It does not replace the dry run above, which runs through the wrapper the converge renders. The commands below are typed in a shell on the engine host, opened with ssh's `-t`, because the `docker run` line takes `-it`.

1. **Stage the image**: `sudo docker pull ghcr.io/zhaow-de/zcrypto-capture@sha256:<the digest to converge>`. Staging is not a converge: nothing restarts, and the engine converge refuses a digest the host has not pulled anyway (`preflight — refuse a digest the host has not pulled` in `infra/ansible/roles/engine/tasks/main.yml`). The staged image stays on the host until `infra/scripts/prune-host-images.py` removes it, and on this host its disk is capture's too (`docs/reference/fleet.md`'s Storage topology).
2. **Read the wrapper's values**: `sudo grep -E '^(STATE_DIR|IMAGE|OWNER)=' /usr/local/sbin/zcrypto-flatten`. `IMAGE` names the digest the engine runs now; `STATE_DIR` and `OWNER` go into the line below as they stand.
3. **Run the wrapper's `docker run` line with the new digest**, inside the gap [`engine-adhoc-key-read`](#engine-adhoc-key-read) step 3 defines, since its reads share the trade key with the running engine:

```
sudo docker run --rm -it --network host --user <OWNER> \
  --env-file /opt/zcrypto-engine/engine.env \
  -v <STATE_DIR>:<STATE_DIR> \
  -v /opt/zcrypto-engine/zcrypto.toml:/app/zcrypto.toml:ro \
  --entrypoint zcrypto \
  ghcr.io/zhaow-de/zcrypto-capture@sha256:<the digest to converge> \
  engine flatten --state-dir <STATE_DIR>
```

`--env-file /opt/zcrypto-engine/engine.env` carries the trade key into the container: pass it as that path, and do not print the file or the container's environment. Leave `--execute` off: a press goes through the wrapper, which latches the kill file and stops the engine first.

4. **Read it as step 1 of the procedure above reads the plan**, the same lines and exit codes. The nautilus-trader version it ran is `sudo docker run --rm --entrypoint python ghcr.io/zhaow-de/zcrypto-capture@sha256:<the digest to converge> -c "import nautilus_trader; print(nautilus_trader.__version__)"`, a run that takes no key.

### Retire when

`flatten` is no longer a subcommand of `zcrypto engine` in `cli/engine/command.py`, or `/usr/local/sbin/zcrypto-flatten` is no longer rendered by the engine role.

______________________________________________________________________

<a name="engine-adhoc-key-read"></a>

## engine-adhoc-key-read — PROCEDURE

### What you are seeing

**Nothing fired.** You need a one-off read that only the live trade key can answer — an account read, a short script against the venue — on the host that holds it. No order is sent, but the key is shared with a running engine, so the read is not consequence-free.

### What it means

The trade key material lives only in `/opt/zcrypto-engine/engine.env` (0600, root-only), which the rendered compose pulls into the engine container as `env_file`. So **an ad-hoc read that needs the trade key runs inside the engine image**, with `--env-file /opt/zcrypto-engine/engine.env` — the shape `/usr/local/sbin/zcrypto-flatten` already uses, in `infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2`.

**The `--entrypoint` override is load-bearing, not decoration.** The image's own ENTRYPOINT (`infra/docker/Dockerfile`) is a launcher that builds its own argument list and execs `zcrypto capture`; it never reads what follows the image name, so without an override the read does not run — a capture daemon starts on the engine host instead. Its VALUE is whatever you are running, not a copy of flatten's `zcrypto`: a `zcrypto` subcommand takes `--entrypoint zcrypto`, a plain script takes `--entrypoint python`.

The two controller-side vaulted-key wrappers, `infra/scripts/probe-with-vaulted-key.sh` and `infra/scripts/mint-with-vaulted-key.sh`, each exec ONE fixed harness that places orders. Neither is a credential path for a read.

### What to do

1. **Take the image from the RUNNING container, never from a pins row.** (no count command: where the image is read from is an operator act nothing in the tree records)

```
ssh zcrypto sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine
```

It returns `repo@sha256:<full>`. A rollback re-pins a host without re-truing any row in `docs/reference/fleet-pins.md`, so a row can name an image the host is not running. `.Config.Image` is one of the narrow fields CLAUDE.md `## Secrets` allows here — never widen the format to the whole object.

2. **Drive it from the workstation, not on the host**, with `IMAGE` set to what step 1 returned:

```
ssh zcrypto sudo docker run --rm -i --env-file /opt/zcrypto-engine/engine.env --entrypoint python "$IMAGE" - < script.py
```

ssh forwards local stdin into the container, so the script never lands on the engine host and nothing is left to delete. A mount, or a redirect typed inside an ssh session, means copying it there first.

3. **Run it inside the engine play's own window.** The read shares the trade key with the still-running engine, so one engine order or cancel may be rejected around it; the engine reconciles that at its next 4-hourly boundary. The window is the one `site.yml`'s `engine window — refuse a converge outside the inter-cycle gap` asserts: start at least 30 min after a boundary (00/04/08/12/16/20 UTC) and finish at least 15 min before the next. The 30 min is the FALLBACK floor. Once the boundary's cycle has journaled `completed_at` into `/var/lib/zcrypto-engine/journal/<YYYY-MM-DD>/cycle-<HH>.json`, the assert substitutes 5 min past that completion — it does not take the earlier of the two, so a cycle that ran past B+25 min puts the floor *after* B+30. Read the journal rather than treating B+30 as always safe (no count command: the `engine window` assert in `infra/ansible/site.yml` holds the substitution).

```
sudo python3 - <<'PY'
import json, pathlib
from datetime import datetime, timedelta
root = pathlib.Path("/var/lib/zcrypto-engine/journal")
p = max(root.glob("*/cycle-*.json"), key=lambda q: q.stat().st_mtime)
d = json.loads(p.read_text())
print(p, "cycle_ts", d["cycle_ts"])
print("  completed_at:", d["completed_at"])
print("  the gap opens:", (datetime.fromisoformat(d["completed_at"]) + timedelta(minutes=5)).isoformat())
PY
```

On the host, it prints the newest cycle record with its `cycle_ts` and `completed_at`, and that time plus five minutes, which is where the gap opens. A `cycle_ts` that is not the boundary just passed means that boundary's cycle has not journaled: it is still running, or it failed and `sudo ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/` lists `failed-cycle-<HH>.json`, and the gap then opens at the fallback floor, 30 minutes past the boundary.

### Retire when

The engine no longer takes the trade key as container environment — i.e. the engine role no longer renders `engine.env` to `/opt/zcrypto-engine/engine.env`.

______________________________________________________________________

<a name="engine-clear-stored-account"></a>

## engine-clear-stored-account — PROCEDURE

### What you are seeing

**Nothing fired.** The engine refuses a spot sell with `the venue record refutes the signed qty` — or, under the restart hold, `the venue record's balance does not cover the signed qty` — while Kraken holds the quantity, and the newest `venue-<HH>.json` lists under `balances` a coin Kraken holds none of, or holds more of: the venue-truth read of [`engine-probe-window`](#engine-probe-window) prints that record, and `kraken extended-balance -o json` on the workstation prints Kraken's side. Dust left by a staking reward and a coin held at one engine start and sold since both read this way.

**This page covers one state: the account flat at Kraken, the arm file off, the gate at `level=none`.** That is the state the procedure was measured in. With a spot lot held it is not run from this page: the clear is one more engine restart, and what a cleared account reads at a start over a held lot is unmeasured. Inside the rung-2 box a stale figure on a held leg is [the restart step](#rung-2-after-a-restart)'s — a start taken with the lot held raises that coin's stored figure to Kraken's — and the stale figure of a coin not held waits for a flat book.

### What it means

The engine keeps its Kraken account in the cache as a list of account events, the key `trader-SHADOW-001:accounts:KRAKEN-001`: each start appends what Kraken's balance read returned, and the next start replays the whole list. Kraken's read leaves out a coin whose balance is zero and the replay keeps each coin's newest figure, so a coin the account once carried stays at that figure after it is sold or converted, through each later restart. The boundary cycle writes the account's balances into the venue record, and the spot-sell check (`_classify_spot_close` in `cli/engine/executor.py`) refuses a sell when the record shows a positive balance under the sell quantity. Deleting the list while the engine is stopped makes the next start build the account from Kraken's read alone. The orders, the positions, the ledger and the journal are not touched, and a balance Kraken really holds comes back at that start, at Kraken's figure — so a small balance still at Kraken is converted first, with the engine stopped (step 5).

The delete is a write, and the cache admits writes from the `engine` user alone; the operator's `vk` function on a cache node is the read-only one. That user's password is the `ZCRYPTO_CACHE_PASSWORD` line of `/opt/zcrypto-engine/engine.env`. The block below reads the line inside one Python process on the engine host and sends it in one `AUTH` through the engine's own cache proxy, so it reaches no argument list, no output and no shell history; a refused `AUTH` prints the server's error word and nothing after it. The process runs in the proxy container's network namespace, where the proxy listens on loopback, so the write lands on the node the Sentinels name as the primary, the one the engine loads from.

### What to do

1. **Admit the run.** On the workstation, never on a host (no count command: `infra/scripts/count-list.sh kraken-cli-on-infra-surfaces` counts the tree's own surfaces, and a command typed on a host leaves no record there): `kraken open-orders -o json` lists no order, `kraken positions -o json` prints `{}`, and the balance export, `kraken extended-balance -o json`, shows no lot held — the positions read prints `{}` with a spot lot held too, so the balance export is the one that says so. Write down each coin the export shows above zero: this run's own start would read it back into the new account, so step 5 converts it first, with the engine stopped, and with no coin above zero step 5 is skipped. Kraken's small-balance conversion takes a balance worth under about 1 USD, once per 24 hours (`docs/reference/kraken-fee-schedule.md`): a coin worth more is a lot held, which this page does not cover, and with a coin written down a conversion made less than 24 hours earlier holds the run until Kraken takes the next. On the host: the gate read prints `level=none`, and `sudo ls -l /var/lib/zcrypto-engine/exec/` lists no `armed` and no `probe-plan.json`. Then [the restart rule](#engine-restart-margin-position)'s four reads; the inter-cycle gap as step 3 of [`engine-adhoc-key-read`](#engine-adhoc-key-read) reads it off the journal; and the Kraken maintenance feed, read whole with [`order-semantics-verification.md`](order-semantics-verification.md) §1.1's command for an entry that reaches the stop or the start. The feed is read again immediately before step 7's start and before each further stop or restart this page leads to; an entry that reaches the act holds it, and an engine that is down then stays down until the entry has passed.

2. **Paste the block into a shell on `zcrypto`, once per login.** It defines two variables holding the Python text and the function's text, and the function `acct`; it runs nothing.

```bash
IFS= read -r -d '' ACCT_PY <<'PY'
import json, socket, sys, time

sys.tracebacklimit = 0
MODE = sys.argv[1] if len(sys.argv) > 1 else ""
OPT, BAD = {}, []
for a in sys.argv[2:]:
    name, sep, value = a.partition("=")
    if sep and value and name == "key" and name not in OPT:
        OPT[name] = value
    else:
        BAD.append(a)
ADDR = "127.0.0.1"
ENV_FILE = "/opt/zcrypto-engine/engine.env"
KEY = OPT.get("key", "trader-SHADOW-001:accounts:KRAKEN-001")
ASIDE = "aside:" + KEY
NAME = "ZCRYPTO_CACHE_PASSWORD="
CONN = []


class Refused(Exception):
    pass


def enc(*words):
    out = b"*%d\r\n" % len(words)
    for w in words:
        b = w if isinstance(w, bytes) else str(w).encode()
        out += b"$%d\r\n%s\r\n" % (len(b), b)
    return out


def dec(r):
    line = r.readline()
    if not line.endswith(b"\r\n"):
        raise ConnectionError
    kind, body = line[:1], line[1:-2]
    if kind == b"+":
        return body.decode()
    if kind == b"-":
        raise Refused(body.decode("ascii", "replace"))
    if kind == b":":
        return int(body)
    if kind == b"$":
        n = int(body)
        return None if n < 0 else r.read(n + 2)[:-2]
    if kind == b"*":
        n = int(body)
        return None if n < 0 else [dec(r) for _ in range(n)]
    raise ConnectionError


def connect():
    secret = ""
    with open(ENV_FILE) as f:
        for line in f:
            if line.startswith(NAME):
                secret = line[len(NAME):].rstrip("\n")
    if not secret:
        raise Refused("the env file carries no cache password line")
    last, deadline = "no attempt", time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            s = socket.create_connection((ADDR, 6379), timeout=max(0.5, min(5, deadline - time.monotonic())))
            r = s.makefile("rb")
            s.sendall(enc("AUTH", "engine", secret))
            try:
                dec(r)
            except Refused as e:
                # The first word alone: a server's error text can repeat the arguments it was sent.
                raise Refused("AUTH refused (%s)" % str(e).split(" ")[0]) from None
            s.settimeout(10)
            CONN[:] = [s, r]
            return
        except OSError as e:
            last = type(e).__name__
            time.sleep(max(0, min(1, deadline - time.monotonic())))
    raise Refused("nothing answered on %s:6379 in 30 s (%s)" % (ADDR, last))


def cmd(*words):
    CONN[0].sendall(enc(*words))
    return dec(CONN[1])


def text(reply):
    return reply.decode("utf-8", "replace") if isinstance(reply, bytes) else reply


def primary(required):
    info = dict(l.split(":", 1) for l in text(cmd("INFO", "replication")).splitlines() if ":" in l)
    server = dict(l.split(":", 1) for l in text(cmd("INFO", "server")).splitlines() if ":" in l)
    print("answering: role %s, version %s, replicas connected %s" % (info.get("role"), server.get("valkey_version", server.get("redis_version")), info.get("connected_slaves")))
    for k in sorted(info):
        if k.startswith("slave") and "=" in info[k]:
            print("  %s %s" % (k, info[k]))
    if required and info.get("role") != "master":
        raise Refused("the node answering is not the primary: nothing changed")


def show(key):
    if not cmd("EXISTS", key):
        print("  %s: absent" % key)
        return
    kind = cmd("TYPE", key)
    if kind != "list":
        print("  %s: type %s" % (key, kind))
        return
    rows = cmd("LRANGE", key, "0", "-1")
    print("  %s: list, %d entries" % (key, len(rows)))
    merged = {}
    for i, raw in enumerate(rows):
        try:
            d = json.loads(raw)
            bal = dict((b["currency"], b["total"].split(" ")[0]) for b in d["balances"])
            print("    [%d] %s %s" % (i, d.get("ts_event"), " ".join("%s=%s" % kv for kv in sorted(bal.items())) or "no balances"))
            for c, v in bal.items():
                merged[c] = "%s (entry %d)" % (v, i)
        except Exception:
            print("    [%d] not read as an account event, %d bytes" % (i, len(raw)))
    print("    newest figure per currency: %s" % (", ".join("%s %s" % kv for kv in sorted(merged.items())) or "none"))


def do_list():
    primary(False)
    cursor, keys = "0", set()
    while True:
        cursor, batch = cmd("SCAN", cursor, "COUNT", "1000")
        cursor = text(cursor)
        keys.update(text(k) for k in batch)
        if cursor == "0":
            break
    keys = sorted(keys)
    kinds = []
    for at in range(0, len(keys), 500):
        chunk = keys[at:at + 500]
        CONN[0].sendall(b"".join(enc("TYPE", k) for k in chunk))
        kinds += [dec(CONN[1]) for _ in chunk]
    groups, singles = {}, []
    for k, kind in zip(keys, kinds):
        parts = k.split(":")
        if k.startswith("trader-") and len(parts) > 2 and parts[1] in ("currencies", "instruments", "orders", "positions"):
            groups[(":".join(parts[:2]) + ":*", kind)] = groups.get((":".join(parts[:2]) + ":*", kind), 0) + 1
        else:
            singles.append((k, kind))
    print("%d keys" % len(keys))
    for (g, kind), n in sorted(groups.items()):
        print("  %6d %-6s %s" % (n, kind, g))
    for k, kind in singles:
        print("  %6d %-6s %s" % (1, kind, k))
    accounts = [k for k in keys if ":accounts:" in k and not k.startswith("aside:")]
    print("%d key(s) carrying :accounts:" % len(accounts))
    for k in accounts:
        show(k)
    asides = [k for k in keys if k.startswith("aside:")]
    print("%d aside copy(ies), each an earlier clear's" % len(asides))
    for k in asides:
        show(k)
    if KEY not in keys:
        print("NOTE: %s is absent" % KEY)


def do_check():
    primary(False)
    show(KEY)
    show(ASIDE)


def do_clear():
    primary(True)
    kind = cmd("TYPE", KEY)
    if kind != "list":
        raise Refused("%s is type %s, not a list: nothing changed" % (KEY, kind))
    before = cmd("LRANGE", KEY, "0", "-1")
    if cmd("EXISTS", ASIDE):
        if cmd("TYPE", ASIDE) != "list" or cmd("LRANGE", ASIDE, "0", "-1") != before:
            raise Refused("%s exists and differs from the key: nothing changed" % ASIDE)
        print("the aside copy is already there and identical")
    else:
        print("COPY -> %s" % cmd("COPY", KEY, ASIDE))
        if cmd("LRANGE", ASIDE, "0", "-1") != before:
            raise Refused("the aside copy differs from the key: the key is untouched")
    print("%s: %d entries, identical to the key" % (ASIDE, len(before)))
    print("DEL -> %s" % cmd("DEL", KEY))
    print("EXISTS %s -> %s" % (KEY, cmd("EXISTS", KEY)))
    print("replicas acknowledging -> %s" % cmd("WAIT", "2", "5000"))
    print("CLEARED")


def do_restore():
    primary(True)
    if cmd("TYPE", ASIDE) != "list":
        raise Refused("no aside copy at %s: nothing changed" % ASIDE)
    want = cmd("LRANGE", ASIDE, "0", "-1")
    print("COPY REPLACE -> %s" % cmd("COPY", ASIDE, KEY, "REPLACE"))
    if cmd("LRANGE", KEY, "0", "-1") != want:
        raise Refused("the restored key differs from the aside copy")
    print("%s: %d entries, identical to the aside copy, which stays" % (KEY, len(want)))
    print("replicas acknowledging -> %s" % cmd("WAIT", "2", "5000"))
    print("RESTORED")


def do_drop():
    primary(True)
    if not cmd("EXISTS", ASIDE):
        raise Refused("no aside copy at %s: nothing changed" % ASIDE)
    if cmd("TYPE", KEY) != "list":
        raise Refused("%s is absent, so the aside copy is the one copy left: nothing changed" % KEY)
    print("DEL -> %s" % cmd("DEL", ASIDE))
    print("EXISTS %s -> %s" % (ASIDE, cmd("EXISTS", ASIDE)))
    print("replicas acknowledging -> %s" % cmd("WAIT", "2", "5000"))
    print("DROPPED")


MODES = {"list": do_list, "check": do_check, "clear": do_clear, "restore": do_restore, "drop": do_drop}
try:
    if BAD:
        raise Refused("not understood: %s -- after the mode, key=<name> alone, one word: nothing changed" % " ".join(BAD))
    if MODE not in MODES or ":accounts:" not in KEY or KEY.startswith("aside:"):
        raise Refused("usage: list | check | clear | restore | drop, then optional key=<name with :accounts:>")
    connect()
    MODES[MODE]()
except Refused as e:
    print("REFUSED: %s" % e)
    sys.exit(1)
except BaseException as e:
    print("FAILED: %s" % type(e).__name__)
    sys.exit(2)
PY
IFS= read -r -d '' ACCT_SH <<'SH'
acct() {
  local pid rc
  case "${1:-}" in
    clear|restore)
      if sudo docker inspect --format '{{.State.Status}}' zcrypto-engine >/dev/null 2>&1; then
        echo "REFUSED: a zcrypto-engine container exists; $1 runs with the unit stopped"
        return 1
      fi ;;
  esac
  pid="$(sudo docker inspect --format '{{.State.Pid}}' zcrypto-cache-proxy 2>/dev/null)"
  if ! [ "${pid:-0}" -gt 0 ] 2>/dev/null; then
    echo "REFUSED: no running zcrypto-cache-proxy container"
    return 1
  fi
  printf '%s\n' "$ACCT_PY" | sudo nsenter -t "$pid" -n python3 - "$@"
  rc=$?
  case "${1:-}" in
    clear|restore)
      if sudo docker inspect --format '{{.State.Status}}' zcrypto-engine >/dev/null 2>&1; then
        echo "WARNING: a zcrypto-engine container exists now -- it was started while $1 ran and may have loaded the account first: stop the unit, then acct check"
      fi ;;
  esac
  return $rc
}
SH
eval "$ACCT_SH"
```

`declare -f acct >/dev/null && echo ok` prints `ok`, and `printf '%s' "$ACCT_PY$ACCT_SH" | sha256sum` prints `b8da39812c0d0697a806d31b260533de9511e5462ef33ff393a05c729e1050b5`: a paste that lost or changed a line of either text prints another digest and is pasted again. `clear` and `restore` refuse while a `zcrypto-engine` container exists, and while `acct` runs no `systemctl` line is typed in a second terminal. `drop` refuses while the key is absent and compares nothing: once the key exists it deletes the aside copy whatever that copy holds, so step 3's reading of the two entry lists is the check that comes before it.

3. **Read the store while the engine runs**: `acct list`. It prints the node that answered — `role master` and two `slave` lines, each `state=online` — then the keys by group and type, then each key carrying `:accounts:` entry by entry, oldest first, with the balances each start read and the newest figure per currency, which is what the next start will replay, then the aside copies. Expect one account key, `trader-SHADOW-001:accounts:KRAKEN-001`, a list, and `0 aside copy(ies)`. A second account key, or one that is not a list: stop here. A key under another name: pass it as `key=<name>` to each call below. An aside copy is what an earlier clear left behind, and `acct clear` refuses over one that differs from the key, so it is deleted before this run goes on. Where the key's entries open with the copy's own — a clear that did not delete, or a restore — the copy holds nothing the key lacks, whatever a start since has added, and `acct drop` deletes it here. Where they do not, the copy is a finished clear's way back, and step 9 says when it is deleted.

4. **Stop the engine, and bring the proxy back alone at once.** The unit's stop removes the proxy with the engine. A stopped engine pages, and nothing is silenced: `Cache · proxy has no backend` (critical) once the proxy has been absent for two minutes; `Engine · cycles have stopped` (critical) from about five minutes after the stop, because that rule alerts on its series being absent — its runbook section reads the page as a boundary that left no record, which is not what happened here; `Engine · the execution gate's heartbeat has stopped` (warning) from about ten minutes, the same way; `Engine · position open at last report and the engine is not reporting` (critical) after ten minutes down when a leg of the position gauge last read above the rule's floor of 0.000001 base units ([`engine.md#zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure)); and `Fleet · a daemon restarted` (warning) after the start. The two absent-series pages clear by themselves once the engine runs: the new process publishes both gauges at its start.

```
sudo systemctl stop zcrypto-engine
sudo docker compose -f /opt/zcrypto-engine/compose.yaml up -d cache-proxy
```

The first returns within the engine's twenty-second stop grace; the second prints `Container zcrypto-cache-proxy  Started` and names no `zcrypto-engine` container. `acct check` then prints the key as step 3 did and the aside copy `absent`; its first answer can take a few seconds, the time the proxy's checks need to pass twice, and `REFUSED: nothing answered … in 30 s` is the proxy routing no backend. An `nsenter:` line and no `answering:` line is the namespace not entered: nothing was sent to the store, and step 7 starts the engine on it as it was.

5. **Convert each coin step 1 wrote down; with none written down, go to step 6.** The owner runs Kraken's "Convert small balances" on Kraken's site, from each of those coins into EUR (no count command: a conversion is the owner's act on Kraken, and the ledger export is where it shows). It is confirmed with the engine stopped and at no time while the engine runs: a conversion Kraken books as a trade while the engine runs leaves an `EXTERNAL` position in the engine's book that a restart does not close. Then, on the workstation, the balance export is read back: each of those coins at zero or gone from it. `kraken ledgers -o json` lists what Kraken booked — `spend` and `receive` rows with subtype `dustsweeping` and no trade is the booking `docs/reference/kraken-fee-schedule.md` records — and the rows' ledger ids go into the run's entry (step 8). A coin the read-back still shows above zero was not converted, and step 7's start will read it back into the account. Steps 6 and 7 go on all the same, so that the boundary's cycle runs, and the run then goes to the owner with step 8's record, which carries that coin. A conversion not yet confirmed when the gap's close nears is left unconfirmed, as step 6 leaves an unfinished clear.

6. **Clear**: `acct clear`. It prints `COPY -> 1`, the aside copy's entry count `identical to the key`, `DEL -> 1`, `EXISTS trader-SHADOW-001:accounts:KRAKEN-001 -> 0`, `replicas acknowledging -> 2` and `CLEARED`. A line opening `REFUSED:` names what stopped it and what state it left: before `COPY` nothing changed; after `COPY` and before `DEL` the key is whole and the aside copy exists, and a second `acct clear` goes on from there. `NOREPLICAS` is the primary refusing a write while no replica follows it within ten seconds — [`cache.md#zcrypto-cache-replicas-short`](cache.md#zcrypto-cache-replicas-short) — and `replicas acknowledging -> 1` is one replica behind, which the Cache board names; the engine is started once both read `lag=0` or `lag=1` in `acct check`. `FAILED: KeyboardInterrupt` is Ctrl-C, `FAILED: TimeoutError` a command the primary held past ten seconds, and a dropped ssh session prints nothing. After each of the three — a new login pastes the block again — `acct check` says where the clear stopped: the key and no aside copy, nothing was done; the key and an aside copy, copied and not deleted; no key and an aside copy, done. `acct clear` goes on from the first two. A `WARNING: a zcrypto-engine container exists now` line means the unit was started while `acct clear` ran, and that engine may hold the old list in memory: stop it as in step 4 and go on from what `acct check` prints. Whatever is unfinished when the gap's close nears, 15 minutes before the next boundary, is left, a refused delete not retried: step 7 starts the engine on the store as `acct check` shows it, the key whole or cleared, so that the boundary's cycle runs, and a maintenance entry that reaches the start still holds it (step 1).

7. **Start the engine**, once the maintenance feed has been read again and the balance export shows no coin above zero — step 5's read-back, or a fresh `kraken extended-balance -o json` where step 5 was skipped. A coin it shows that step 1 did not, a reward credited since, goes through step 5 before this start; a coin step 5 left unconverted does not hold the start (step 5's last case). The proxy is taken down first so the unit starts both as it does at each start:

```
sudo docker compose -f /opt/zcrypto-engine/compose.yaml down
sudo systemctl start zcrypto-engine
```

Read the boot line where the restart rule at the head of this page reads it, on the Logs board under container `engine`: `cache restore: 0 order(s), 0 position(s) restored`, and no `the venue holds … where the Cache reads …` WARNING — that line is a leg's coin Kraken held at this start, now in the new account (step 5's last case). Read the start's time, `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine`, and record it in the run's entry (step 8): the procedure that places the next plan compares the engine's start with it. The start latches the restart hold; leave it latched — the procedure that places the next plan clears it and takes what its own steps ask after a restart. From this start on nothing is confirmed on Kraken's conversion page: step 5 says why.

8. **Verify.** `acct check` prints the key as a new list whose entries carry EUR and no coin, and the aside copy with its old entries. The key `absent` after the start means the engine loaded the old list before the delete landed: restart it once more inside the gap, under step 1's reads, and record that start's time in place of step 7's. The decisive read is the first venue record written after the start, at the next 4-hourly boundary: its `balances` carry EUR alone. A coin in the new list or in that record is one Kraken held at the start — step 5's last case, or a reward credited between the read-back and the start — and the run goes to the owner with it. **Record the run as an entry in `docs/reference/drill-log.md`**, in the shape that log's head gives and under a scenario id of its own, as the `spot-proof` entry has: the stop's and the start's times, the boot line, both `acct check` readings, that venue record's `balances`, each page by name and time, and step 5's ledger ids.

9. **Delete the aside copy** once that record reads right: `acct drop`, which prints `DEL -> 1` and `DROPPED`, and refuses while the key itself is absent. Until then the way back is: stop the engine and bring the proxy up as in step 4, `acct restore`, then step 7; the next start replays the old list as before the clear.

### Retire when

`_classify_spot_close` in `cli/engine/executor.py` no longer reads the venue record's balances. `persist_account_events` in `_cache_config` (`cli/engine/node.py`) is no such condition: with it off the stored account is still kept and replayed, as the offline restart harness measured.
