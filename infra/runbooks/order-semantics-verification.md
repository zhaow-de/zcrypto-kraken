# Order-semantics verification runbook

<a name="order-semantics-verification"></a>

Attended operator procedure for `infra/scripts/kraken-order-semantics-probe.py`, the six-probe protocol re-run demanded by the
memo's **Version re-check rule** ("a fresh ~€0.20 zero-fill + round-trip pass must re-run the
order-semantics probes before the engine trades on the new version" —
`docs/research/14.phase6-adapter-verification-1.230.0.md`). Nothing trades until the engine is armed by
hand, so it gates **arming**, not merging: the repo may sit on a bumped version indefinitely while
disarmed. It is owed at **every** nautilus-trader bump, before the engine may be armed on that version.

**This places real orders on a live Kraken account.** Every step below runs in the main session, by
hand, in order. Nothing here belongs in a subagent: host- and credential-touching steps die at the
permission gate there.

The harness is committed because the obligation recurs and the probes are only comparable across versions if they are the *same* probes. It prints the memo table ready to paste; the run's evidence JSON stays outside the repo tree.

______________________________________________________________________

## 0. What the run costs and what it risks

|  |  |
| -- | -- |
| Money at risk, normal path | probe 5's round-trip only: ~EUR 10 notional, ~EUR 0.17 in fees + spread (2026-07-10 measured EUR 0.1618) |
| Money at risk, worst case | one unexpected fill per probe-4 order, each bounded by the harness's per-order ceiling (default EUR 15) |
| Left-resting risk | the harness cancels by client order id on every exit path and re-reads the venue; exit code 3 means something survived, and the terminal prints the ids to cancel by hand |
| Blast radius on the live engine | none by construction: the engine is disarmed; probe orders reach it as `events.order.EXTERNAL` with no ledgered row, so its filter counts, logs and drops them |

______________________________________________________________________

## 1. Pre-flight — do all of these before exporting any credential

### 1.1 Kraken maintenance window

```
curl -s https://status.kraken.com/api/v2/scheduled-maintenances.json \
  | python3 -c 'import json,sys; [print(m["name"], m["scheduled_for"], [c["name"] for c in m["components"]]) for m in json.load(sys.stdin)["scheduled_maintenances"]]'
```

Abort if a window carrying `WebSocket` or `REST` overlaps your run. Entries appear only 2–6 days
ahead, so an empty feed a week out proves nothing — **check again immediately before step 4**.

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

Per spec 00039 decision 3 the workstation IP was a **verification-window-only** exception and was
removed when the 2026-07-10 memo landed; the VPS/engine host is the key's only allowlisted host
today. So:

1. Kraken → Settings → API → `zcrypto-engine` → edit IP restrictions → **add the workstation's
   current public IP** (`curl -s https://api.ipify.org`).
2. Note the time. This exception is temporary and closing it is step 7.

Do not instead run the harness on `zcrypto`: it has no 1.231.0 environment, and putting a probe
process beside the live engine on the same host is not worth the convenience.

### 1.4 The account is funded

The probes need enough EUR to (a) let probe 5 buy ~EUR 10 and (b) let the venue accept the resting
margin orders. Check at Kraken → Balances, or let **probe 1** tell you — but read it knowing what it
reports: under `spot_account_type=MARGIN` the account object gives **TradeBalance-derived equity in
`margin_balance_asset`**, not per-asset wallet balances (2026-07-10 Observation 3). Wallet truth is
the Kraken UI or the raw `Balance` endpoint.

If the balance is short, fund it *before* the run, not between probes.

### 1.5 Open-topics / memo sweep

Before an irreversible production action, sweep `docs/open-topics/README.md` and
`docs/memo.local.md` for anything that blocks touching the live account, and present the result with
the go/no-go.

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

Run from the worktree root (both paths above are relative to it) and pass `--evidence-dir "$EVID"` on every invocation: the evidence default is the cwd, which inside the repo would drop JSONs into git.

The harness refuses to start against any other version unless you pass `--expect-nautilus <v>`
explicitly — that refusal is the point of the run, never a nuisance to bypass.

______________________________________________________________________

## 3. Step 0 — prove the harness before pointing it at money

Two checks, both free, both without credentials.

```
$PY $PROBE --selftest
```

**Expect:** every line `ok`, then `SELFTEST PASSED`, exit 0. This exercises the pure rails — the
notional ceiling, the 25 % distance floor, the quote-freshness and crossed-quote refusals, the client
order id collision guard — and proves each one *bites* on the defect it names. A `FAIL` line here
means **stop**: the rails that bound the money are broken.

```
$PY $PROBE --probes 3 --no-exec --evidence-dir "$EVID"
```

**Expect:** the node starts with a data client only (a warning `No exec_clients configuration found`
is correct here), quotes arrive for all 10 EUR pairs within seconds, probe 3 reports `PASS`, the node
shuts down, exit 0. This is a public-market-data connection: no credentials, no orders, nothing to
lose. It proves the node assembly, the WS path, the teardown and the exit path all work before any
key is in the shell.

**Failure here is a harness problem, not an adapter finding.** Fix it before step 4.

______________________________________________________________________

## 4. Credentials

Decrypt the trade key from `infra/ansible/group_vars/engine_host/vault.yml` (T0061 moved it there
from `capture_host`) using the documented sops+GPG → ansible-vault path in `infra/README.md`, and
export it into **this shell only**:

```
export KRAKEN_SPOT_API_KEY='...'
export KRAKEN_SPOT_API_SECRET='...'
```

Rules, all of them absolute:

- Never write either value into a file, a history-recorded command, or a subagent prompt.
- Never run `ansible-inventory --host` / `--list` / `--graph --vars` — `ansible.cfg` sets
  `vault_password_file`, so all three print the cleartext key.
- The harness never reads these values. It checks only that the variables are **present**; the
  Kraken adapter's own factory sources them from the environment.
- Close the shell when the run is done.

**Nonce warning (2026-07-10 Observation 4):** the adapter uses finer-than-millisecond nonces. After
any harness run, millisecond-nonce REST scripts on the same key get `EAPI:Invalid nonce`. Any sidecar
tooling you reach for afterwards must use `time_ns()` nonces.

______________________________________________________________________

## 5. The run

Re-check the maintenance feed (§1.1) and the boundary clock (§1.2) **now**, then proceed.

### 5.1 Dry run — mandatory, and read the output

```
$PY $PROBE --probes all --evidence-dir "$EVID"
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

Also read probe 2's row: it lists any **pre-existing** open order or position at the venue. Anything
there must be explained before you place a probe order — a `REVIEW` verdict on probe 2 is a stop
sign, not a footnote.

**Verdicts you should see:** 1 `PASS`, 2 `PASS`, 3 `PASS`, 4a–4d `DRY-RUN`, 5 `GATED`, 6 `PASS`.
Probe 5 reads `GATED` rather than `DRY-RUN` because `--probe5` without `--apply` is refused at
preflight — but it now prints the money order it *would* place, so read that line here rather than
meeting it for the first time in the live run.

### 5.2 Probes 1–4 for real — the zero-fill sweep

Get the human's explicit go (spec 00039 D4: *every order-placing probe executes attended, on the
human's explicit go immediately before the probe script runs*), then:

```
$PY $PROBE --probes 1,2,3,4 --apply --evidence-dir "$EVID"
```

Between the printed probes, watch for:

| Sub-probe | Healthy | What failure looks like |
| -- | -- | -- |
| 4a | `accepted (<venue id>), rested, cancel confirmed; filled_qty=0.0` | any `filled_qty` > 0 (a fill at 30 % from market is a reportable finding, not noise); `cancel NOT confirmed` (an order is still working — see §8) |
| 4b | `filled_qty=0.0` and a terminal status. At 1.230.0 this was `OrderCanceled` (venue-initiated), **not** `OrderRejected` — either is a pass; **record which** | `filled_qty` > 0 ⇒ post-only protection did not hold. This is an order-semantics failure and per spec 00039 decision 1 it triggers the pre-approved thin-engine fallback |
| 4b, alternative | verdict `REVIEW` with "order RESTED instead of being protected" | the quote moved between pricing and submission so nothing crossed. **Protocol artifact, not an adapter failure** — re-run with `--probes 4 --apply`, which re-runs all of 4a–4d (there is no sub-probe selector; the extra three are bounded and zero-fill) |
| 4c | `accepted … cancel confirmed` with leverage 2 accepted by the venue | a rejection naming leverage ⇒ margin semantics failure ⇒ fallback path |
| 4d | same, for the leveraged **sell** (the short) | as 4c |

A `REFUSED` row is a rail doing its job — nothing was submitted for that sub-probe. Read the reason:
a stale quote, a size under the venue minimum, a distance that quantized under 25 %. Fix the input
(`--notional`, `--max-quote-age`) and re-run that probe with `--probes <n>` (which re-runs all of its lettered sub-probes — there is no sub-probe selector). **A refusal is never an adapter result.**

### 5.3 Probe 5 — the only step that spends money

Get a second explicit go. Then, and only then:

```
$PY $PROBE --probes 5 --apply --probe5 --evidence-dir "$EVID"
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
- Expect the account object *not* to show an OpenPositions row for a spot buy under
  `spot_account_type=MARGIN`; the adapter reports margin positions there. The harness prints this
  reminder inline.

Record the fee from the fill: 2026-07-10 measured **0.80 %/side** against a modelled 0.6 %, inside
the pre-registered 2× band. A materially different number is a cost-model input (T0014), not an
adapter failure.

### 5.4 Probe 6 — post-run reconciliation, as a fresh process

```
$PY $PROBE --probes 6 --evidence-dir "$EVID"
```

Running it as its **own invocation** is deliberate: the new node's startup reconciliation reads venue
truth rather than the previous process's cache. (Probe 6 also runs in-process at the end of a full
run, forcing a mass-status read; the separate invocation is the stronger check and the one to quote.)

**Expect:** `open orders 0 (ours 0, other 0), open positions 0`, `PASS`, exit 0.

- `ours` non-zero ⇒ **verdict FAIL**, and the open ids are printed in probe 6's own rows ⇒ go to §8 now. The exit code is **1** here, not 3: exit 3 is reserved for leftovers this same process still tracks at teardown, and a fresh `--probes 6` invocation tracks none.
- `other` non-zero ⇒ `REVIEW` ⇒ something at the venue is not ours. Adjudicate before signing off.

______________________________________________________________________

## 6. Exit codes

| Code | Meaning | Action |
| -- | -- | -- |
| 0 | every executed probe passed | proceed to §7 |
| 1 | a probe FAILED or errored, **or** a preflight rail refused the invocation before anything started (its message begins `REFUSING:` and no node was built) | read the row; an order-semantics/reconciliation failure (probes 2, 4–6) triggers the pre-approved fallback, anything else is documented and escalated (spec 00039 decision 1) |
| 2 | refused or aborted before/while probing | nothing was submitted for the refused probe; fix the input and re-run that probe |
| 3 | **something was left resting** | §8, immediately |

______________________________________________________________________

## 7. Post-run reconciliation

### 7.1 At the venue

Kraken → Trade → Open Orders, and Balances. Both must agree with probe 6's printout. The UI is the
tie-breaker, not the harness.

### 7.2 Against the live engine

Probe orders reach the engine as `events.order.EXTERNAL` with no ledgered row, so its filter counts,
logs and drops them without acting. Read the counter by value from the workstation:

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

### 7.3 Close the IP exception — mandatory

Kraken → Settings → API → `zcrypto-engine` → edit IP restrictions → **remove the workstation IP**,
restoring the engine host as the key's only allowlisted host (spec 00039 decision 3's closure step).
Do this in the same session as the run. Then close the credential-bearing shell.

### 7.4 Write it up

`kraken-order-semantics-probe.py` prints the table under
`PROBE RESULTS -- paste these rows into this version's docs/research/ verification doc`, and writes
`evidence-<stamp>.json` into `--evidence-dir` (default: the cwd) with the full event stream, every planned order, and every
client order id. **Then sweep the homes of "<version> is unverified" in the SAME change**, or the next reader meets a contradiction — the act that satisfies the predicate updates none of the others: (1) add the version to `cli/engine/order-semantics-verified.json`, which clears BOTH guards at once since they share it; (2) the arming step in `engine.md`; (3) the previous version's `docs/research/` record; (4) the comment in `tests/test_nautilus_adapter.py`; (5) `tests/test_engine_execgate.py`, which pins the record's exact contents. The last two FAIL deliberately at step (1) and are the tripwire that routes the rest.

Paste the table; keep the JSON in the session scratchpad as the 2026-07-10 run did
("the raw evidence JSONs are preserved in the session scratchpad").

The memo update must state the version the verification now binds to, and anything the harness
reported as moved between 1.230.0 and 1.231.0.

______________________________________________________________________

## 8. If something is left resting

The harness exits **3** and prints, inside a `!!!!` banner, every client order id / venue order id it
believes is still working.

1. Kraken → Trade → Open Orders. Cancel each listed order **by hand**. Do not leave the terminal
   until they are gone.
2. If a probe-5 buy filled and its sell did not, flatten the position by hand in the same place.
3. Only then, re-run `$PY $PROBE --probes 6 --evidence-dir "$EVID"` and confirm `open orders 0 (ours 0 …)`.

Why it matters even though the engine is disarmed: at its next restart the engine's adopt pass reads
every resting order at the venue, finds no ledgered row for a probe order, and **cancels it** — a
silent interaction between two systems, in the logs of only one of them. Leave nothing for it to
find.

**Ctrl-C behaviour:** one Ctrl-C is safe — the harness replaces nautilus's own signal handler with
one that unwinds into the cancel-everything teardown while the exec client is still connected.
A *second* Ctrl-C does **not** kill that teardown — the installed handler swallows every later
SIGINT, deliberately, so the cancel sweep always completes. If you must abandon it, `kill -9` the
process from another terminal and go straight to §8 by hand.

______________________________________________________________________

## 9. Useful invocations

```
$PY $PROBE --selftest                          # pure rails, no network, no credentials
$PY $PROBE --probes 3 --no-exec --evidence-dir "$EVID"        # public market data only, no credentials
# every line below assumes EVID is set as in section 2; the flag keeps evidence out of the repo
$PY $PROBE --probes all --evidence-dir "$EVID"                # full dry run: 1,2,3,6 real; 4,5 printed
$PY $PROBE --probes 1,2,3,4 --apply --evidence-dir "$EVID"    # the zero-fill order sweep
$PY $PROBE --probes 5 --apply --probe5 --evidence-dir "$EVID" # the one real fill
$PY $PROBE --probes 6 --evidence-dir "$EVID"                  # fresh-process venue reconciliation read
$PY $PROBE --probes 4 --apply --log-level INFO --evidence-dir "$EVID"  # re-run probe 4, adapter narrating
```

Knobs worth knowing: `--pair` (default `BTC/EUR`), `--notional` (default 10), `--max-notional`
(default 15, hard ceiling 50 — the harness **refuses**, never clamps), `--away` (default 0.30,
protocol floor 0.25), `--max-quote-age` (default 10 s), `--probe3-basket` (also subscribe `ETH/BTC`
and `SOL/BTC`; off by default so the probe-3 row stays comparable with the 2026-07-10 memo).
