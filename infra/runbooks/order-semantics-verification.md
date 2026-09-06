# Order-semantics verification runbook

<a name="order-semantics-verification"></a>

Attended operator procedure for `infra/scripts/kraken-order-semantics-probe.py`, the six-probe protocol re-run demanded by the
**Version re-check rule** ("a fresh ~€0.20 zero-fill + round-trip pass must re-run the
order-semantics probes before the engine trades on the new version" —
`docs/reference/adapter-verification/1.230.0.md`). Nothing trades until the engine is armed by
hand, so it gates **arming**, not merging: the repo may sit on a bumped version indefinitely while
disarmed. It is owed at **every** nautilus-trader bump, before the engine may be armed on that version.

**A pass binds to one exact version string and nothing else** — §1.6 says what that demands of the
pin, and it may need deciding days before anything else here.

**This places real orders on a live Kraken account.** Every step below runs in the main session, by
hand, in order. Nothing here belongs in a subagent: host- and credential-touching steps die at the
permission gate there.

The harness is committed because the obligation recurs and the probes are only comparable across versions if they are the *same* probes.

______________________________________________________________________

## 0. What the run costs and what it risks

|  |  |
| -- | -- |
| Money at risk, normal path | probe 5's round-trip only: ~EUR 10 notional, ~EUR 0.16 in fees + spread — every recorded pass in `docs/reference/adapter-verification/` |
| Money at risk, worst case | one unexpected fill per probe-4 order, each bounded by the harness's per-order ceiling (default EUR 15) |
| Left-resting risk | every submitted client order id is cancelled on each exit path, then re-read after the node stops; exit 3 means one survived, and the terminal prints them to cancel by hand |
| Blast radius on the live engine | none by construction: the engine is disarmed; probe orders reach it as `events.order.EXTERNAL` with no ledgered row, so its filter counts, logs and drops them |

______________________________________________________________________

## 1. Pre-flight — do all of these before the first credentialed run

### 1.1 Kraken maintenance window

```
curl -s https://status.kraken.com/api/v2/scheduled-maintenances.json \
  | python3 -c 'import json,sys; [print(m["name"], m["scheduled_for"], [c["name"] for c in m["components"]]) for m in json.load(sys.stdin)["scheduled_maintenances"]]'
```

Abort if a window carrying `WebSocket` or `REST` **in `components`, or in its `name` (an API, not a ticker)** overlaps your run — an empty `components` array is not an absent impact. An empty feed is never evidence the window is clear: **check again immediately before step 4**.

### 1.2 The engine's 4-hour boundary

The engine cycles at **00/04/08/12/16/20 UTC** and must complete inside `[B, B+30 min]`.

- Run the probes **inside the inter-cycle gap**, i.e. no earlier than B+35 min and finishing well
  before the next boundary. A full `--probes all --apply` run takes roughly 3–5 minutes.
- Confirm the last boundary actually journaled before you start (from the workstation):
  ```
  ssh zcrypto 'ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/'
  ```
  You want a `cycle-<HH>.json` for the boundary just past. A `failed-cycle-<HH>.json`, or a missing
  artifact, means the engine has a problem of its own — **stop and deal with that first**; probing
  the same account while the engine is misbehaving makes both readings unreadable.
- Confirm no reboot is pending, which would restart the engine mid-run:
  ```
  uv run python infra/scripts/grafana-query.py 'node_reboot_required{host="zcrypto"}'
  ```
  Non-zero ⇒ a reboot is due ⇒ do not run the probes now.

### 1.3 The key's IP allowlist — the step that will otherwise fail every run

Spec 00039 decision 3 makes the workstation IP a **verification-window-only** exception, closed again at step 7.3 after every pass — so it is absent when you start:

1. Kraken → Settings → API → `zcrypto-engine` → edit IP restrictions → **add the workstation's
   current public IP** (`curl -s https://api.ipify.org`).
2. Note the time. This exception is temporary and closing it is step 7.

Do not instead run the harness on `zcrypto`: it has no interpreter at the version under test, and
putting a probe process beside the live engine on the same host is not worth the convenience.

### 1.4 The account is funded

The probes need enough EUR to (a) let probe 5 buy ~EUR 10 and (b) let the venue accept the resting margin orders. Check at Kraken → Balances, or let **probe 1** tell you — but what the account object reports under `spot_account_type=MARGIN` is the adapter's choice and is not readable from the wheel, so treat it as a shape to **check for** on the build in front of you, not one to expect. Wallet truth is the Kraken UI or the raw `Balance` endpoint — record which of the two probe 1 gave you.

If the balance is short, fund it *before* the run, not between probes.

### 1.5 Open-topics / memo sweep

Before an irreversible production action, sweep `docs/open-topics/README.md` and
`.local/memo.md` for anything that blocks touching the live account, and present the result with
the go/no-go.

### 1.6 Freeze the pin — decide this first; it can predate everything above

**Stop bumping the pin, and keep it stopped until the engine is armed on the version you pass.**

A nightly channel that moves daily and an arming record matched by exact string are in direct
conflict, and the conflict resolves in exactly one direction — the record does not loosen (§2). So:

- **Freeze before the pass.** The version you run the probes against must be the version that is
  still pinned when the engine is armed. Land the bump you intend to arm on, then stop.
- **Any later bump blocks arming, from the next deploy on.** A bump in the repo does not touch a container that is already running, so an engine armed on the old version keeps trading on it. What the bump kills is the *path forward* — the armed converge is refused from that tree, and once an image built from it is deployed the gate refuses to arm too. Nothing warns you at the moment of the bump; the suite stays green by design, and the refusal arrives at the arming step, which is the worst moment to discover it.
- **A bump that lands after a pass is a decision to re-run the pass**, at the full attended cost, or
  to revert the pin. There is no third option, and "the diff looks harmless" is not one: this
  procedure exists precisely because a bump can move fill, cancel, post-only or reconciliation
  behaviour without moving anything the suite can see.

While the engine is disarmed, bump freely — that is the blessed state the whole design assumes.
The freeze starts when the pass is scheduled and ends when the arming window closes.

______________________________________________________________________

## 2. Environment — the interpreter under test

Run from a tree whose lockfile already carries the version under test — the bump branch itself, so the harness binds the exact interpreter the engine will run:

```
cd <the bump branch's worktree>
uv sync
PY=./.venv/bin/python
PROBE=infra/scripts/kraken-order-semantics-probe.py
EVID="$HOME/probe-evidence"          # OUTSIDE the repo tree, so no JSON can land in git
mkdir -p "$EVID"
$PY -c 'import nautilus_trader; print(nautilus_trader.__version__)'   # must equal the version under test
```

The wrappers pass `-I` to both interpreters, which isolates Python's environment and nothing else: `BASH_ENV`, `LD_PRELOAD` and `PATH` are the operator's own and no flag in those scripts reaches them.

Run from the worktree root (both paths above are relative to it) and pass `--evidence-dir "$EVID"` on every invocation: the evidence default is the cwd, which inside the repo would drop JSONs into git.

The harness reads the version it demands from `pyproject.toml` at every invocation, so it and the check above cannot disagree, and it refuses to start against an interpreter that does not match. That refusal is the point of the run, never a nuisance to bypass: clear it with `uv sync`, never with `--expect-nautilus` or `--allow-version-mismatch`.

### 2.1 What the record records — settled before the pass, not discovered at it

`cli/engine/order-semantics-verified.json` lists **exact, complete version strings, matched exactly** — no family match, no prefix, no "rc4 covers all rc4 nightlies". The probes measure **one build**, so a prefix would make the record vouch for builds no attended run ever touched, which is the only thing the record is for. The cost of that exactness is §1.6's freeze, and it is not up for revisiting at an arming window.

**The string to record is the one the interpreter reports**, not the one you read off the pin:

```
$PY -c 'import nautilus_trader; print(nautilus_trader.__version__)'
```

Paste that verbatim. The two guards read different operands — the converge assert compares the
**pin** in the `pyproject.toml` of the tree you converge *from*, the runtime gate compares the
**running interpreter's** `nautilus_trader.__version__` inside the container — and one entry only
satisfies both while those two strings coincide. They are not automatically the same string: the
image bakes its version from the pyproject it was *built* from, so a controller tree ahead of the
deployed image makes the converge assert refuse a version the running engine does not have. That is
what `engine-procedures.md`'s pre-probe step 2 is for — converge from the revision the running digest was built
from, and the two operands agree by construction. Reaching for `-e arming_override=...` because
"the record obviously contains it" is the wrong move here; reconcile the tree instead.
Keeping them coincident is `tests/test_nautilus_adapter.py::test_pinned_version`'s job; its `_NAUTILUS_PIN` comment carries why the pin must use `===` rather than `==`.

______________________________________________________________________

## 3. Step 0 — prove the harness before pointing it at money

Two checks, both free, both without credentials.

```
$PY $PROBE --selftest
```

**Expect:** every line `ok`, then `SELFTEST PASSED (<n> checks)`, exit 0. Each check names the rail it exercises. A `FAIL` line here means **stop**: the rails that bound the money are broken.

```
$PY $PROBE --probes 3 --no-exec --evidence-dir "$EVID"
```

**Expect:** the node starts with a data client only, quotes arrive for all 10 EUR pairs within seconds, probe 3 reports `PASS`, the node shuts down, exit 0. This is a public-market-data connection: no credentials, no orders, nothing to lose, and it proves the node assembly, the WS path, the callback sequence and the teardown before the trade key is anywhere near the process.

**Failure here is a harness problem, not an adapter finding.** Fix it before step 4.

______________________________________________________________________

## 4. Credentials

**Do not export the key into your shell. Run the harness through the wrapper instead:**

```
RUN=infra/scripts/probe-with-vaulted-key.sh
```

`$RUN` decrypts `kraken_trade_api_key` and `kraken_trade_api_secret` from `infra/ansible/group_vars/engine_host/vault.yml` (T0061 moved them there from `capture_host`) through `infra/ansible/scripts/vault-pass.sh`, the sops+GPG path `infra/README.md` documents, and `execve`s the harness with the two values in the child's environment — never echoed, never written, never on a command line. The program it runs is **hardcoded** and arguments select nothing, which is what lets the operation be permitted narrowly rather than as a general secrets-reading capability.

**From here on, every invocation that needs the key runs as `$RUN <args>` in place of `$PY $PROBE <args>`, the same arguments and nothing else changed.** §3's two checks need no credentials and keep using `$PY $PROBE`. So §5.1's dry run is:

```
$RUN --probes all --evidence-dir "$EVID"
```

Rules, all of them absolute:

- Never write either value into a file, a history-recorded command, or a subagent prompt.
- Never run `ansible-inventory --host` / `--list` / `--graph --vars` — `ansible.cfg` sets
  `vault_password_file`, so all three print the cleartext key.
- The harness reads both **values**, not merely their presence — `exec_client_config()` passes `KRAKEN_SPOT_API_KEY` / `KRAKEN_SPOT_API_SECRET` into `KrakenExecutionClientConfig`, which requires them — and never stores, logs, prints or writes them; its refusals name the two VARIABLES, never their contents.
- Close the shell when the run is done. Nothing sensitive should be in it, and that is the check.

**Nonce warning:** the adapter has been measured minting finer-than-millisecond nonces (`docs/reference/adapter-verification/1.230.0.md`), so after a harness run a millisecond-nonce REST script on the same key gets `EAPI:Invalid nonce` — give any sidecar tooling you reach for afterwards `time_ns()` nonces.

______________________________________________________________________

## 5. The run

Re-check the maintenance feed (§1.1) and the boundary clock (§1.2) **now**, then proceed.

### 5.1 Dry run — mandatory, and read the output

```
$RUN --probes all --evidence-dir "$EVID"
```

Probes 1–3 and 6 execute for real (all read-only). Probes 4 and 5 print the exact submission they
would make and stop there.

**Read every `PLAN` line before continuing.** For each one confirm:

- the instrument is `BTC/EUR.KRAKEN` (or whatever you passed to `--pair`),
- `notional=EUR ~10`, comfortably under the printed per-order ceiling,
- 4a/4c: a BUY price ~30 % **below** the printed mid; 4d: a SELL price ~30 % **above** it,
- 4b: a BUY price just **above** the printed ask (it must cross),
- 4c/4d carry `leverage=2`; 4a/4b carry `leverage=None`,
- every `client_order_id` has the shape `O-<stamp>-901-P6V-<n>` — **never** `…-001-000-…`, which is
  the production engine's.

Also read probe 2's row: it lists any **pre-existing** open order or position that read can see. Anything there must be explained before you place a probe order — a `REVIEW` verdict on probe 2 is a stop sign, not a footnote. **An empty row is a floor, not a clear venue.** Probe 2 reads the startup-reconciliation cache, which cannot see an order resting on BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR or ETH/BTC ([`engine-procedures.md#flat-verdict-blind-legs`](engine-procedures.md#flat-verdict-blind-legs)), and `--pair` defaults to **BTC/EUR** — so a leftover from an earlier run, on the pair you are about to trade, is exactly what this row cannot list. Read Kraken → Trade → Open Orders by eye before §5.2 places anything.

**Verdicts you should see:** 1 `PASS`, 2 `PASS`, 3 `PASS`, 4a–4d `DRY-RUN`, 5 `GATED`, 6 `PASS`. Probe 5 reads `GATED` rather than `DRY-RUN` because its money gate `--probe5` was not given — it still prints the money order it *would* place, so read that line here rather than meeting it for the first time in the live run.

### 5.2 Probes 1–4 for real — the zero-fill sweep

Get the human's explicit go (spec 00039 D4: *every order-placing probe executes attended, on the
human's explicit go immediately before the probe script runs*), then:

```
$RUN --probes 1,2,3,4 --apply --evidence-dir "$EVID"
```

Between the printed probes, watch for:

| Sub-probe | Healthy | What failure looks like |
| -- | -- | -- |
| 4a | `accepted (<venue id>), rested, cancel confirmed; filled_qty=0.0` | any `filled_qty` > 0 — a fill 30 % from market is reportable; `cancel NOT confirmed` — an order is still working, see §8 |
| 4b | `filled_qty=0.0` and a terminal `OrderCanceled` or post-only `OrderRejected` — either passes | `filled_qty` > 0 ⇒ post-only did not hold ⇒ spec 00039 D1's fallback; any *other* `OrderRejected` is FAIL, protection never exercised |
| 4b, alternative | `REVIEW`, "order RESTED instead of being protected" | the quote moved before submission and nothing crossed — protocol artifact, not adapter failure; re-run `--probes 4 --apply` |
| 4c | `accepted … cancel confirmed` with leverage 2 accepted by the venue | a rejection naming leverage ⇒ margin semantics failure ⇒ fallback path |
| 4d | same, for the leveraged **sell** (the short) | as 4c |

A `REFUSED` row submitted nothing for that sub-probe. Read the reason — a stale quote, a size under the venue minimum, a distance that quantized under 25 % — then fix the input (`--notional`, `--max-quote-age`) and re-run that probe with `--probes <n>`, which re-runs all of its lettered sub-probes; there is no sub-probe selector, and the extra ones are bounded and zero-fill. **A refusal is never an adapter result.**

### 5.3 Probe 5 — the only step that spends money

Get a second explicit go. Then, and only then:

```
$RUN --probes 5 --apply --probe5 --evidence-dir "$EVID"
```

`--probe5` is required *on top of* `--apply`; without it the row reads `GATED` and nothing is
submitted.

**Watch for, in order:** `BUY filled <qty> @ <px>` → the post-buy balance/position print → the
closing `SELL` plan → `market sell @ <px> filled` → verdict `PASS`.

- If the **buy fills and the sell does not**, the harness prints
  `POSITION LEFT OPEN` and a note telling you to flatten by hand. Do that immediately at
  Kraken → Trade, before anything else.
- A note about the closing quantity being "floored … dust will remain" means a sliver of BTC stays
  in the wallet. Below the leg's `ordermin` that is terminal dust, not a position — record it, do not
  chase it.
- Whether a spot buy under `spot_account_type=MARGIN` shows an OpenPositions row is **per build**: read it on the build in front of you and record it in that version's `docs/reference/adapter-verification/` record. Either answer is a pass — probe 5 is judged on the fill and the flat close.

Record the fee from the fill and compare it with the rate the cost model charges: `cli/costs/fees.py`'s tier 1 is **0.80 %/side** taker, and each recorded pass measured exactly that. A materially different number is a cost-model input (the calibration T0014 delivered), not an adapter failure.

### 5.4 Probe 6 — post-run reconciliation, as a fresh process

```
$RUN --probes 6 --evidence-dir "$EVID"
```

Running it as its **own invocation** is deliberate: the new node's startup reconciliation reads venue truth rather than the previous process's cache. Probe 6 also runs in-process at the end of every run, but a run that submitted anything cannot force a fresh venue read and marks its own row `REVIEW` — the separate invocation is the one to quote.

**Expect:** `open orders 0 (ours 0, other 0), open positions 0`, `PASS`, exit 0.

**That zero is a floor, not a total, and this probe is where it matters most.** Startup reconciliation's order read cannot see a row on BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR or ETH/BTC ([`engine-procedures.md#flat-verdict-blind-legs`](engine-procedures.md#flat-verdict-blind-legs)), and `--pair` defaults to **BTC/EUR** — so the order a run is most likely to have left resting is exactly the one this count cannot include. A PASS here is not on its own evidence the account is clear; §7.1's by-eye read at Kraken is what closes it.

- `ours` non-zero ⇒ **verdict FAIL**, the open ids printed in probe 6's own rows ⇒ go to §8 now, and expect exit **3** with the cancel-by-hand banner. The final read sweeps every probe-shaped order it can see, including ones this invocation never submitted, so an earlier run's leftover is adopted by startup reconciliation and counted here — subject to the floor above. FAIL and the banner read the same cache at different moments, so an id can legitimately move between them while the node still holds its clients open after the stop.
- `other` non-zero ⇒ `REVIEW` ⇒ something at the venue is not ours. Adjudicate before signing off.

______________________________________________________________________

## 6. Exit codes

| Code | Meaning | Action |
| -- | -- | -- |
| 0 | every executed probe passed | proceed to §7 |
| 1 | a probe FAILED or errored, **or** a preflight rail refused the run (message begins `REFUSING:`) | a probe 2/4–6 failure triggers spec 00039 D1's pre-approved fallback; escalate anything else |
| 2 | a probe was refused, **or** the run stopped before its sequence finished | the two need opposite actions — read the paragraph below the table before deciding which |
| 3 | **something was left resting** | §8, immediately |

**Exit 2 is two different events.** A *refusal* (`!! REFUSED before the node was built:`, or a probe row whose verdict is `REFUSED`) submitted nothing for that probe: fix the input and re-run it. A run that *stopped* — an interrupt, an exec client that died, any abnormal exit from the node — may have left a real **open position** that no order read can see, because probe 5's buy filled, its closing sell never ran, and the buy is CLOSED. The harness says so: the `!!` banner `a fill with no closing leg is an OPEN POSITION`, and the matching line under *notes requiring a human decision*. Flatten by hand per §8 before re-running anything.

______________________________________________________________________

## 7. Post-run reconciliation

### 7.1 At the venue

Kraken → Trade → Open Orders, and Balances. Both must agree with probe 6's printout. The UI is the
tie-breaker, not the harness.

### 7.2 Against the live engine

Read the three counters by value from the workstation:

```
uv run python infra/scripts/grafana-query.py \
  'zcrypto_exec_external_events_total{host="zcrypto"}' \
  'zcrypto_exec_kill_tripped{host="zcrypto"}' \
  'zcrypto_exec_position{host="zcrypto"}'
```

- `zcrypto_exec_external_events_total{disposition="unmatched"}` should have **risen** by roughly the
  number of order events the probes generated. `(no series)` is a FAIL of the telemetry path, never a
  zero.
- `zcrypto_exec_kill_tripped` must still be **0**. A trip means an order the engine's ledger vouches
  for diverged — which probe orders structurally cannot cause, so investigate it as a real event.
- `zcrypto_exec_position` must be unchanged and flat.

Then confirm the engine's **next** boundary cycle journals normally:

```
ssh zcrypto 'ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/'
```

A `cycle-<HH>.json` with `completed_at` inside `[B, B+30 min]` for the first boundary after the run.
That is the outcome that says the probes cost the engine nothing.

**That boundary is normally hours away when you finish**, because §1.2 puts the run at B+35 or later, so this check is almost always deferred. Carry it across the gap in the record, never in prose: give the version's record an **`## Owed checks not discharged by this pass`** section naming the exact boundary (`HH:00 UTC` on the run's date) and what would satisfy it, then come back at that boundary, take the reading, and **rewrite that bullet as its outcome**. The arming step in [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) refuses to arm while any item there is open, which is what makes the deferral bite instead of evaporating. Any other reading this section asks for that the run could not take belongs in the same section — an `unmatched` delta with no before-reading is an absolute number, not the rise this section wants.

### 7.3 Close the IP exception — mandatory

Kraken → Settings → API → `zcrypto-engine` → edit IP restrictions → **remove the workstation IP**,
restoring the engine host as the key's only allowlisted host (spec 00039 decision 3's closure step).
Do this in the same session as the run. Then close the credential-bearing shell.

### 7.4 Write it up

The harness prints the table under `PROBE RESULTS -- paste these rows into docs/reference/adapter-verification/<version>.md` and writes `evidence-<stamp>.json` into `--evidence-dir`. **Then sweep the homes of "<version> is unverified" in the SAME change**, or the next reader meets a contradiction — the act that satisfies the predicate updates none of the others:

1. **Add the version to `cli/engine/order-semantics-verified.json`**, exactly as the interpreter spells it (§2.1) — the act that says the re-run happened, and the one that clears both guards. Never add a version without the `docs/reference/adapter-verification/<version>.md` record carrying its PASS.
2. **`tests/test_engine_execgate.py`**, which pins the record's exact contents and therefore **FAILS deliberately the moment you do (1)** — that failure is the routing for the rest of this list, and its assertion message points back at it. Update it deliberately, never by pasting whatever the diff shows.
3. **The arming step in [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window)** — pre-probe step 4, whose unmatched-external baseline and live-orders-boot caveat both name the version they were taken on.
4. **The previous version's `docs/reference/adapter-verification/` record**, cross-linked so the series reads as one and neither file claims to be current.

**`tests/test_nautilus_adapter.py` is deliberately NOT on this list**: it compares the installed version with the pin, so it stays green across bumps and carries no version string to sweep. Nothing goes red at a bump, by design — the debt is collected at arming, by the converge assert and the runtime gate, each of which blocks the money rather than a test run.

Paste the table; leave the evidence JSON where `--evidence-dir` put it (`$EVID`, outside the repo tree) and never commit it.

The memo update must state the exact version the verification now binds to, and every observation
this run recorded rather than matched — probe 4b's terminal event, probe 1's balance shape, and
anything else that differs from the last recorded version. Those are the deliverable, not a
footnote: the next run has no expected answer for them except what this one writes down.

______________________________________________________________________

## 8. If something is left resting

The harness exits **3** and prints, inside a `!!!!` banner, every client order id / venue order id it
believes is still working.

1. Kraken → Trade → Open Orders. Cancel each listed order **by hand**. Do not leave the terminal
   until they are gone.
2. If a probe-5 buy filled and its sell did not, flatten the position by hand in the same place.
3. Only then, re-run `$RUN --probes 6 --evidence-dir "$EVID"` and confirm `open orders 0 (ours 0 …)` — **and confirm it a second time on Kraken's own Open Orders page**, because that count is blind on the five pairs §5.4 names and a leftover on one of them reads as a clean zero.

Why it matters even though the engine is disarmed: at its next restart the engine's adopt pass reads the resting orders reconciliation put in its cache, finds no ledgered row for a probe order, and **cancels it** — a silent interaction between two systems, in the logs of only one of them. On the five legs where that read is blind ([`engine-procedures.md#flat-verdict-blind-legs`](engine-procedures.md#flat-verdict-blind-legs)) it is not cancelled either — it just keeps working. Both outcomes say the same thing: leave nothing for it to find.

**Ctrl-C behaviour:** one Ctrl-C is safe. It stops the node, which runs the harness's cancel-everything sweep while the exec client is still connected — the node holds its clients open for `--order-timeout` seconds after the stop precisely so those cancels can reach the venue. Every later interrupt is swallowed, deliberately, so the sweep always completes. An interrupted run still prints its table and its leftover banner, and exits **2** — or **3** if anything survived the sweep. If you must abandon it, `kill -9` the process from another terminal and work this section by hand.

**What an interrupt does NOT do is finish the run.** Every probe the sequence had not yet reached is abandoned — the terminal says how many — and their rows never appear, so an interrupted run is never a partial pass to read verdicts out of. Re-run the probes you still owe, as their own invocation.

**If the interrupt landed after a fill, you may be holding a position.** An interrupted run refuses to submit anything further — deliberately, so an abort cannot open new exposure on the way out, but it means a filled probe-5 buy has no closing sell. The harness prints every submitted order with a non-zero fill under a flatten-by-hand banner: go to Kraken → Trade and flatten before doing anything else, then step 3 above.

______________________________________________________________________

## 9. Useful invocations

```
$PY $PROBE --selftest                          # pure rails, no network, no credentials
$PY $PROBE --probes 3 --no-exec --evidence-dir "$EVID"        # public market data only, no credentials
# every line below needs the trade key, so it goes through $RUN (section 4) and never through $PY
# $PROBE; each also assumes EVID is set as in section 2, keeping evidence out of the repo
$RUN --probes all --evidence-dir "$EVID"                # full dry run: 1,2,3,6 real; 4,5 printed
$RUN --probes 1,2,3,4 --apply --evidence-dir "$EVID"    # the zero-fill order sweep
$RUN --probes 5 --apply --probe5 --evidence-dir "$EVID" # the one real fill
$RUN --probes 6 --evidence-dir "$EVID"                  # fresh-process venue reconciliation read
$RUN --probes 4 --apply --log-level INFO --evidence-dir "$EVID"  # re-run probe 4, adapter narrating
```

`--help` lists every knob and its default. What it does not say: `--max-notional` cannot be raised past a hard ceiling of 50 (the harness **refuses**, never clamps); `--probe3-basket` adds `ETH/BTC` and `SOL/BTC`, and leaving it off is what keeps the probe-3 row comparable with the recorded passes; and raising `--order-timeout` widens the interrupt window with it, so an interrupt then costs that much more time before the process exits.
