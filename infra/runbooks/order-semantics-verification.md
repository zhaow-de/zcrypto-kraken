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

**This places real orders on a live Kraken account.** Every step below runs in the attending session's main loop, by
hand, in order. Nothing here belongs in a subagent: host- and credential-touching steps die at the
permission gate there.

The harness is committed because the obligation recurs and the probes are only comparable across versions if they are the *same* probes.

______________________________________________________________________

## Verifying order semantics on the live account — PROCEDURE

### 0. What the run costs and what it risks

|  |  |
| -- | -- |
| Money at risk, normal path | probe 5's round-trip only: ~EUR 10 notional, ~EUR 0.16 in fees + spread |
| Money at risk, worst case | one unexpected fill per probe-4 order, each bounded by the harness's per-order ceiling (`--max-notional`, default EUR 15; a value above 50 is refused with `REFUSING:`, never clamped) |

### 1. Pre-flight

Do all of these before the first credentialed run.

#### 1.1 Kraken maintenance window

```
curl -s https://status.kraken.com/api/v2/scheduled-maintenances.json \
  | python3 -c 'import json,sys; [print(m["name"], m["scheduled_for"], [c["name"] for c in m["components"]]) for m in json.load(sys.stdin)["scheduled_maintenances"]]'
```

Abort if a window carrying `WebSocket` or `REST` in `components`, or in its `name`, overlaps your run; an empty `components` array is not an absent impact. An empty feed is never evidence the window is clear: check again immediately before the run (§5). The fleet rule for converges is the same test (`.claude/rules/fleet-deploys.md`).

#### 1.2 The engine's 4-hour boundary

The boundary schedule is `.claude/rules/fleet-deploys.md`'s engine bullet; a healthy completion lands inside `[B, B+30 min]`, as [`engine.md#zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale) derives and §7.2 below reads.

- Run the probes inside the inter-cycle gap: no earlier than B+35 min, finishing well before the next boundary. A full `--probes all --apply` run takes roughly 3–5 minutes.
- Confirm the last boundary journaled (from the workstation):
  ```
  ssh zcrypto 'ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/'
  ```
  You want a `cycle-<HH>.json` for the boundary just past. A `failed-cycle-<HH>.json`, or a missing artifact, means the engine has a problem of its own: stop and deal with that first. Probing the same account while the engine is misbehaving makes both readings unreadable.
- Confirm no reboot is pending, which would restart the engine mid-run:
  ```
  uv run python infra/scripts/grafana-query.py 'node_reboot_required{host="zcrypto"}'
  ```
  Non-zero means a reboot is due: do not run the probes now.

#### 1.3 The key's IP allowlist

This is the step that otherwise fails every run. Spec 00039 decision 3 makes the workstation IP a verification-window-only exception, closed again at §7.3 after every pass, so it is absent when you start:

1. Kraken → Settings → API → `zcrypto-engine` → edit IP restrictions → add the workstation's current public IP (`curl -s https://api.ipify.org`).
2. Note the time. This exception is temporary and closing it is §7.3.

Do not instead run the harness on `zcrypto`: it has no interpreter at the version under test, and a probe process beside the live engine is not worth the convenience.

#### 1.4 The account is funded

The probes need enough EUR for probe 5's ~EUR 10 buy and for the venue to accept the resting margin orders. Check at Kraken → Balances, or read probe 1's account object; what it reports under `spot_account_type=MARGIN` is the adapter's choice on each build, so treat it as a shape to check for on the build in front of you, not one to expect. Wallet truth is the Kraken UI or the raw `Balance` endpoint; record which of the two probe 1 gave you. If the balance is short, fund it before the run, not between probes.

#### 1.5 Open-topics / memo sweep

The sweep of `docs/open-topics/README.md` and `.local/memo.md` for anything that blocks touching the live account is pre-probe step 1 of [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window). Do it, and present the result with the go/no-go.

#### 1.6 Freeze the pin

Decide this first; it can predate everything above. Stop bumping the pin, and keep it stopped until the engine is armed on the version you pass. A nightly channel that moves daily and an arming record matched by exact string (§2.1) are in conflict, and the record does not loosen.

- Freeze before the pass. The version you run the probes against must be the version still pinned when the engine is armed. Land the bump you intend to arm on, then stop.
- A bump in the repo does not touch a running container, so an engine armed on the old version keeps trading on it. What the bump kills is the path forward: the armed converge is refused from that tree, and once an image built from it is deployed the gate refuses to arm too. Nothing warns at the moment of the bump; the refusal arrives at the arming step.
- A bump that lands after a pass is a decision to re-run the pass, at the full attended cost, or to revert the pin. There is no third option: a bump can move fill, cancel, post-only or reconciliation behaviour without moving anything the suite can see (no count command: the adapter's venue behaviour is upstream; the attended probes are what read it).

While the engine is disarmed, bump freely. The freeze starts when the pass is scheduled and ends when the arming window closes. The same rule, read from the arming side, is pre-probe step 3 of [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window).

### 2. Environment: the interpreter under test

Run from a tree whose lockfile already carries the version under test, the bump branch itself, so the harness binds the exact interpreter the engine will run:

```
cd <the bump branch's worktree>
uv sync
PY=./.venv/bin/python
PROBE=infra/scripts/kraken-order-semantics-probe.py
EVID="$HOME/probe-evidence"          # OUTSIDE the repo tree, so no JSON can land in git
mkdir -p "$EVID"
$PY -c 'import nautilus_trader; print(nautilus_trader.__version__)'   # must equal the version under test
```

Run from the worktree root (both paths above are relative to it) and pass `--evidence-dir "$EVID"` on every invocation: the evidence default is the cwd, which inside the repo would drop JSONs into git.

The harness reads the version it demands from `pyproject.toml` at every invocation, so it and the check above cannot disagree, and it refuses to start against an interpreter that does not match. That refusal is the point of the run: clear it with `uv sync`, never with `--expect-nautilus` or `--allow-version-mismatch`.

The credential wrapper (§4) runs both interpreters with `-I`, which isolates Python's own environment and nothing else: `BASH_ENV`, `LD_PRELOAD` and `PATH` stay the operator's own. The wrapper's header comment says what the flag guards.

`$PY $PROBE --help` lists every knob and its default. Three things it does not say are noted where they bind: the `--max-notional` ceiling at §0, `--probe3-basket` at §3, `--order-timeout` at §8.

#### 2.1 What the record records

Settled before the pass, not discovered at it. `cli/engine/order-semantics-verified.json` lists exact, complete version strings, matched exactly: no family match, no prefix. The probes measure one build, and a prefix would make the record vouch for builds no attended run touched. The cost of that exactness is §1.6's freeze.

The string to record is the one the interpreter reports, not the one you read off the pin:

```
$PY -c 'import nautilus_trader; print(nautilus_trader.__version__)'
```

Paste that verbatim. The two guards read different operands: the converge assert compares the pin in the `pyproject.toml` of the tree you converge from, and the runtime gate compares the running interpreter's `nautilus_trader.__version__` inside the container. One entry satisfies both only while those two strings coincide, and they are not automatically the same: the image bakes its version from the pyproject it was built from, so a controller tree ahead of the deployed image makes the converge assert refuse a version the running engine does not have. Pre-probe step 2 of [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) is the check that the running digest and your working tree agree; reconcile the tree rather than reaching for `-e arming_override=...`. Pre-probe step 3 there describes the two guards. `tests/test_nautilus_adapter.py::test_pinned_version` keeps the pin and the installed version coincident; its `_NAUTILUS_PIN` comment carries why the pin uses `===` rather than `==`.

### 3. Step 0: prove the harness before pointing it at money

Two checks, both free, both without credentials.

```
$PY $PROBE --selftest
```

Expect every line `ok`, then `SELFTEST PASSED (<n> checks)`, exit 0. Each check names the rail it exercises. A `FAIL` line means stop: the rails that bound the money are broken.

```
$PY $PROBE --probes 3 --no-exec --evidence-dir "$EVID"
```

Expect the node to start with a data client only, quotes for all 10 EUR pairs within seconds, probe 3 `PASS`, a clean shutdown, exit 0. This is a public-market-data connection: no credentials, no orders, and it proves the node assembly, the WS path, the callback sequence and the teardown before the trade key is anywhere near the process. Leave `--probe3-basket` off: it adds `ETH/BTC` and `SOL/BTC`, and the probe-3 row is only comparable with the recorded passes on the 10 EUR pairs.

A failure here is a harness problem, not an adapter finding. Fix it before §4.

### 4. Credentials

Do not export the key into your shell. Run the harness through the wrapper instead:

```
RUN=infra/scripts/probe-with-vaulted-key.sh
```

`$RUN` decrypts `kraken_trade_api_key` and `kraken_trade_api_secret` from `infra/ansible/group_vars/engine_host/vault.yml` through `infra/ansible/scripts/vault-pass.sh`, the sops+GPG path `infra/README.md` documents, and `execve`s the harness with the two values in the child's environment: never echoed, never written, never on a command line. The program it runs is hardcoded and arguments select nothing, which is what lets the operation be permitted narrowly rather than as a general secrets-reading capability.

From here on, every invocation that needs the key runs as `$RUN <args>` in place of `$PY $PROBE <args>`, the same arguments and nothing else changed. §3's two checks need no credentials and keep using `$PY $PROBE`. So §5.1's dry run is:

```
$RUN --probes all --evidence-dir "$EVID"
```

Rules:

- Never write either value into a file, a history-recorded command, or a subagent prompt (no count command: a history line or a prompt sits outside the tree, and no hook scans for secrets).
- Never run `ansible-inventory --host` / `--list` / `--graph --vars` (set: the non-comment lines of the non-Markdown files under `infra/`, `.claude/`, `cli/` — the roles, templates, units, hooks and scripts a command runs from — with `infra/ansible/scripts/vault-pass.sh`, whose text is the refusal, excluded beside the counter; count: `infra/scripts/count-list.sh ansible-inventory-secret-forms-invoked`): `CLAUDE.md`'s Secrets rule, and `infra/ansible/scripts/vault-pass.sh` refuses those ancestries.
- The harness reads both values, not merely their presence (`exec_client_config()` passes `KRAKEN_SPOT_API_KEY` / `KRAKEN_SPOT_API_SECRET` into `KrakenExecutionClientConfig`), and never stores, logs, prints or writes them; its refusals name the two variables, never their contents (no count command: a property of the harness's own code, which no test asserts).
- Close the shell when the run is done. Nothing sensitive should be in it, and that is the check.

Nonce: the adapter mints finer-than-millisecond nonces (`docs/reference/adapter-verification/1.230.0.md`), so after a harness run a millisecond-nonce REST script on the same key gets `EAPI:Invalid nonce`. Give any sidecar tooling you reach for afterwards `time_ns()` nonces.

### 5. The run

Re-check the maintenance feed (§1.1) and the boundary clock (§1.2) now, then proceed.

#### 5.1 Dry run

Mandatory, and read the output.

```
$RUN --probes all --evidence-dir "$EVID"
```

Probes 1–3 and 6 execute for real (all read-only). Probes 4 and 5 print the exact submission they would make and stop there.

Read every `PLAN` line before continuing. For each one confirm:

- the instrument is `BTC/EUR.KRAKEN` (or whatever you passed to `--pair`),
- `notional=EUR ~10`, comfortably under the printed per-order ceiling,
- 4a/4c: a BUY price ~30 % below the printed mid; 4d: a SELL price ~30 % above it,
- 4b: a BUY price just above the printed ask (it must cross),
- 4c/4d carry `leverage=2`; 4a/4b carry `leverage=None`,
- `client_order_id` carries the harness's `901`/`P6V` tags (`O-<stamp>-901-P6V-<n>`), never the engine's `-001-000-` (no count command: `tests/test_order_semantics_probe.py::test_selftest_passes_with_no_credentials_and_no_network` runs the `--selftest` that proves the shape).

Also read probe 2's row: it lists any pre-existing open order or position that read can see. Anything there must be explained before you place a probe order; a `REVIEW` verdict on probe 2 is a stop sign, not a footnote. An empty row is a floor, not a clear venue: probe 2 reads the startup-reconciliation cache, which is blind on the five pairs §5.4 names, and `--pair` defaults to BTC/EUR, one of them. A leftover from an earlier run, on the pair you are about to trade, is exactly what this row cannot list. Read Kraken → Trade → Open Orders by eye before §5.2 places anything.

Verdicts you should see: 1 `PASS`, 2 `PASS`, 3 `PASS`, 4a–4d `DRY-RUN`, 5 `GATED`, 6 `PASS`. Probe 5 reads `GATED` rather than `DRY-RUN` because its money gate `--probe5` was not given; it still prints the money order it would place, so read that line here rather than meeting it for the first time in the live run.

#### 5.2 Probes 1–4 for real: the zero-fill sweep

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

A `REFUSED` row submitted nothing for that sub-probe. Read the reason (a stale quote, a size under the venue minimum, a distance that quantized under 25 %), fix the input (`--notional`, `--max-quote-age`) and re-run that probe with `--probes <n>`, which re-runs all of its lettered sub-probes; there is no sub-probe selector, and the extra ones are bounded and zero-fill. A refusal is never an adapter result. To hear the adapter's own narration on a re-run, add `--log-level INFO`:

```
$RUN --probes 4 --apply --log-level INFO --evidence-dir "$EVID"
```

#### 5.3 Probe 5: the only step that spends money

Get a second explicit go. Then:

```
$RUN --probes 5 --apply --probe5 --evidence-dir "$EVID"
```

`--probe5` is required on top of `--apply`; without it the row reads `GATED` and nothing is submitted.

Watch for, in order: `BUY filled <qty> @ <px>` → the post-buy balance/position print → the closing `SELL` plan → `market sell @ <px> filled` → verdict `PASS`.

- If the buy fills and the sell does not, the harness prints `POSITION LEFT OPEN` and a note telling you to flatten by hand. Do that immediately at Kraken → Trade, before anything else.
- A note that the closing quantity was "floored … dust will remain" means a sliver of BTC stays in the wallet: the closing leg was rounded down to the pair's lot step (`size_increment`), so the remainder is smaller than one lot step and no order can carry it. That is terminal dust, not a position; record it, do not chase it.
- Whether a spot buy under `spot_account_type=MARGIN` shows an OpenPositions row is per build: read it on the build in front of you and record it in that version's `docs/reference/adapter-verification/` record. Either answer is a pass; probe 5 is judged on the fill and the flat close.

Record the fee from the fill and compare it with `cli/costs/fees.py`'s tier-1 taker rate, 0.80 %/side. A materially different number is a cost-model input, not an adapter failure.

#### 5.4 Probe 6: post-run reconciliation, as a fresh process

```
$RUN --probes 6 --evidence-dir "$EVID"
```

Running it as its own invocation is deliberate: the new node's startup reconciliation reads venue truth rather than the previous process's cache. Probe 6 also runs in-process at the end of every run, but a run that submitted anything cannot force a fresh venue read and marks its own row `REVIEW`; the separate invocation is the one to quote.

Expect `open orders 0 (ours 0, other 0), open positions 0`, `PASS`, exit 0.

That zero is a floor, not a total, and this probe is where it matters most. Startup reconciliation's order read cannot see a row on BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR or ETH/BTC ([`engine-procedures.md#flat-verdict-blind-legs`](engine-procedures.md#flat-verdict-blind-legs)), and `--pair` defaults to BTC/EUR, so the order a run is most likely to have left resting is exactly the one this count cannot include. A PASS here is not on its own evidence the account is clear; §7.1's by-eye read at Kraken is what closes it.

- `ours` non-zero ⇒ verdict FAIL, the open ids printed in probe 6's own rows ⇒ go to §8 now, and expect exit 3 with the cancel-by-hand banner. The final read adopts probe-shaped orders this invocation did not submit, so an earlier run's leftover is counted here, subject to the floor above. FAIL and the banner read the same cache at different moments, so an id can move between them while the node still holds its clients open after the stop.
- `other` non-zero ⇒ `REVIEW` ⇒ something at the venue is not ours. Adjudicate before signing off.

### 6. Exit codes

| Code | Meaning | Action |
| -- | -- | -- |
| 0 | every executed probe passed | proceed to §7 |
| 1 | a probe FAILED or errored, **or** a preflight rail refused the run (message begins `REFUSING:`) | a probe 2/4–6 failure triggers spec 00039 D1's pre-approved fallback; escalate anything else |
| 2 | a probe was refused, **or** the run stopped before its sequence finished | the two need opposite actions; read the paragraph below the table before deciding which |
| 3 | **something was left resting** | §8, immediately |

Exit 2 is two different events. A refusal (`!! REFUSED before the node was built:`, or a probe row whose verdict is `REFUSED`) submitted nothing for that probe: fix the input and re-run it. A run that stopped (an interrupt, an exec client that died, any abnormal exit from the node) may have left a real open position that no order read can see: probe 5's buy filled, its closing sell never ran, and the buy is CLOSED. The harness says so, in the `!!` banner `a fill with no closing leg is an OPEN POSITION` and under *notes requiring a human decision*. Flatten by hand per §8 before re-running anything.

### 7. Post-run reconciliation

#### 7.1 At the venue

Kraken → Trade → Open Orders, and Balances. Both must agree with probe 6's printout. The UI is the
tie-breaker, not the harness.

#### 7.2 Against the live engine

Read the three counters by value from the workstation:

```
uv run python infra/scripts/grafana-query.py \
  'zcrypto_exec_external_events_total{host="zcrypto"}' \
  'zcrypto_exec_kill_tripped{host="zcrypto"}' \
  'zcrypto_exec_position{host="zcrypto"}'
```

- `zcrypto_exec_external_events_total{disposition="unmatched"}` should have risen by roughly the number of order events the probes generated. `(no series)` is a FAIL of the telemetry path, never a zero (no count command: how an operator reads a query's output leaves no record in the tree).
- `zcrypto_exec_kill_tripped` must still be 0. A trip need not be a diverged order — the kill also latches on a weekly tracking-band breach and on a position that could not be read after an intent — but the divergence path is the one the probes could be suspected of, and they structurally cannot reach it: an external event no ledger row vouches for reaches nothing at all (no count command: `tests/test_engine_executor.py::test_an_external_event_the_ledger_does_not_vouch_for_reaches_nothing_at_all`), so investigate any trip as a real event.
- `zcrypto_exec_position` must be unchanged and flat.

Then confirm the engine's next boundary cycle journals normally:

```
ssh zcrypto 'ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/'
```

A `cycle-<HH>.json` with `completed_at` inside `[B, B+30 min]` for the first boundary after the run is the outcome that says the probes cost the engine nothing.

That boundary is normally hours away when you finish, because §1.2 puts the run at B+35 or later, so this check is almost always deferred. Carry it in the record, never in prose: give the version's record an `## Owed checks not discharged by this pass` section naming the exact boundary (`HH:00 UTC` on the run's date) and what would satisfy it, then come back at that boundary, take the reading, and rewrite that bullet as its outcome. The arming step in [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) refuses to arm while any item there is open. Any other reading this section asks for that the run could not take belongs in the same section; an `unmatched` delta with no before-reading is an absolute number, not the rise this section wants.

#### 7.3 Close the IP exception

Mandatory. Kraken → Settings → API → `zcrypto-engine` → edit IP restrictions → remove the workstation IP,
restoring the engine host as the key's only allowlisted host (spec 00039 decision 3's closure step).
Do this in the same session as the run. Then close the credential-bearing shell.

#### 7.4 Write it up

The harness prints the table under `PROBE RESULTS -- paste these rows into docs/reference/adapter-verification/<version>.md` and writes `evidence-<stamp>.json` into `--evidence-dir`. Then sweep the homes of "<version> is unverified" in the same change, or the next reader meets a contradiction:

1. Add the version to `cli/engine/order-semantics-verified.json`, exactly as the interpreter spells it (§2.1). This is the act that says the re-run happened, and the one that clears both guards. Add a version only when its `docs/reference/adapter-verification/<version>.md` record carries a PASS (no count command: the file's own `_never` line and its `_notes` map state the pairing; no test checks it).
2. `tests/test_engine_execgate.py` pins the record's exact contents and fails deliberately the moment you do (1); its assertion message points back at this list. Update it to the new set by hand, not by pasting whatever the diff shows.
3. The arming step in [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window): pre-probe step 4, whose unmatched-external baseline and live-orders-boot caveat both name the version they were taken on.
4. The previous version's `docs/reference/adapter-verification/` record, cross-linked so the series reads as one and neither file claims to be current.

`tests/test_nautilus_adapter.py` is deliberately not on this list: it compares the installed version with the pin, so it stays green across bumps and carries no version string to sweep. Nothing goes red at a bump, by design; the debt is collected at arming, by the converge assert and the runtime gate, each of which blocks the money rather than a test run.

Paste the table; leave the evidence JSON where `--evidence-dir` put it (`$EVID`, outside the repo tree) and never commit it.

The memo must state the exact version the verification now binds to, and every observation this run recorded rather than matched: probe 4b's terminal event, probe 1's balance shape, anything that differs from the last recorded version. The next run has no expected answer for those except what this one writes down.

### 8. If something is left resting

The harness exits 3 and prints, between two 78-character `!` rules, every client order id / venue order id it believes is still working.

1. Kraken → Trade → Open Orders. Cancel each listed order by hand. Do not leave the terminal until they are gone.
2. If a probe-5 buy filled and its sell did not, flatten the position by hand in the same place.
3. After both, re-run `$RUN --probes 6 --evidence-dir "$EVID"` and confirm `open orders 0 (ours 0 …)`, then confirm it a second time on Kraken's own Open Orders page: that count is blind on the five pairs §5.4 names, and a leftover on one of them reads as a clean zero.

Why it matters even though the engine is disarmed: at its next restart the engine's adopt pass reads the resting orders reconciliation put in its cache, finds no ledgered row for a probe order, and cancels it, a silent interaction between two systems in the logs of only one of them. On the five legs where that read is blind ([`engine-procedures.md#flat-verdict-blind-legs`](engine-procedures.md#flat-verdict-blind-legs)) it is not cancelled either; it just keeps working. Both outcomes say the same thing: leave nothing for it to find.

Ctrl-C behaviour: one Ctrl-C is safe. It stops the node, which runs the harness's cancel-everything sweep while the exec client is still connected; the node holds its clients open for `max(10, --order-timeout)` seconds after the stop so those cancels can reach the venue, so raising `--order-timeout` widens that window and the time an interrupt takes to exit. Every later interrupt is swallowed, deliberately, so the sweep always completes. An interrupted run still prints its table and its leftover banner, and exits 2, or 3 if anything survived the sweep. If you must abandon it, `kill -9` the process from another terminal and work this section by hand.

What an interrupt does not do is finish the run. Every probe the sequence had not yet reached is abandoned (the terminal says how many) and their rows never appear, so an interrupted run is never a partial pass to read verdicts out of. Re-run the probes you still owe, as their own invocation.

If the interrupt landed after a fill, you may be holding a position. An interrupted run refuses to submit anything further, so an abort cannot open new exposure on the way out, but it means a filled probe-5 buy has no closing sell. The harness prints every submitted order with a non-zero fill under a flatten-by-hand banner: go to Kraken → Trade and flatten before doing anything else, then step 3 above.
